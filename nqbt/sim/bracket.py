"""The bracket engine every archetype's exits go through.

One stop, up to four R-multiple targets, an ambiguity policy for the bar that holds both,
and a forced exit at the session close -- resolved identically whichever archetype opened
the position and whichever side it is on. **This is the fidelity-critical code**: every
rule the NT8 reconciliations validated lives here, so a second copy is a second place for
Tier 1 and Tier 2 to drift.

Extracted during M18 rather than before or after it, deliberately. Before, the only shapes
available were DeadCatBounce and its mirror, which is one example wearing a second as a
disguise; after, duplicated fill semantics would have shipped. EMA crossover is the second
real shape -- a market-on-next-open entry with no trigger price, an ATR stop with no
structural swing to anchor to, and a signal exit -- and the split falls where those differ
from DeadCatBounce: the **entry** half is per-archetype and the **bracket** half is not.

Everything here is an ``@njit(cache=True)`` device function, which Numba inlines into the
calling loop at no cost, so the extraction is free at runtime as well as in the trade log.
``entry_bracket`` is the exception in kind rather than in mechanism: it is a stop-market
entry's arithmetic, shared by ``simulate_deadcat`` and by ``explain.py`` so that the audit
trail is by construction the arithmetic under audit.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from nqbt.trades import (
    C_AMBIGUOUS,
    C_BARS_HELD,
    C_COMMISSION,
    C_DIRECTION,
    C_ENTRY_BAR,
    C_ENTRY_PRICE,
    C_EXIT_BAR,
    C_EXIT_PRICE,
    C_EXIT_REASON,
    C_GROSS_PNL,
    C_INITIAL_STOP,
    C_LEG,
    C_MAE,
    C_MFE,
    C_NET_PNL,
    C_QUANTITY,
    C_R_MULTIPLE,
    C_RISK_POINTS,
    C_TARGET_PRICE,
    C_TRADE_ID,
    EXIT_SESSION_CLOSE,
    EXIT_STOP,
    EXIT_TARGET,
    N_COLUMNS,
)


@njit(cache=True)
def resolve_brackets(
    out: np.ndarray,
    written: int,
    trade_id: int,
    entry_bar: int,
    i: int,
    entry_price: float,
    initial_stop: float,
    stop: float,
    risk: float,
    leg_open: np.ndarray,
    leg_target: np.ndarray,
    leg_quantities: np.ndarray,
    run_high: float,
    run_low: float,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    must_flatten: bool,
    slippage: float,
    point_value: float,
    commission_per_contract: float,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    direction: float,
    held_from_bar_open: bool,
) -> tuple[int, bool]:
    """Resolve one bar against the live stop and targets, closing whatever leaves.

    Returns the new write count and whether the position is still open. A write count of
    ``-1`` means ``out`` overflowed and the caller must abandon the run.

    **This is the fidelity-critical code**, and until M20a it existed twice: once for a bar
    while in a position and once, textually independently, for the bar an entry filled on.
    The two were behaviourally equivalent -- the entry-bar copy dropped the ``leg_open``
    guards because every leg had just been opened, which makes them no-ops rather than a
    difference -- but every rule the 1143/1144 NT8 reconciliation validated appeared in
    both, so there were two places for Tier 1 and Tier 2 to drift and the reconciliation
    only ever covered one of them.

    Unified here specifically so that M15 could multiply one copy by its direction sign
    instead of two. The short-only byte-identity gate cannot catch a sign applied
    inconsistently across two copies, because at ``d = -1`` both reduce to today's code
    whether or not they agree at ``d = +1``.

    Order of resolution, which is the part that carries the evidence: the stop takes the
    whole position unless the ambiguity policy says the targets were reached first; targets
    fill at their own price with no slippage, being limit orders; anything still open after
    a targets-first bar leaves at the stop on that same bar; and force-flat is last, so a
    position that reached a target and then ran out of session records both.

    **A bar that opens already past the stop fills at its open, not at the stop price.** A
    stop order is a market order once triggered, so when the bar gaps through it there is no
    trade available at the stop level and the fill is the first price there is. The entry
    path has always modelled this for the *entry* order (see ``open_[i]`` gapping through
    ``pending_trigger`` in :func:`simulate_deadcat`); it simply never reached the exit side,
    which made every gapped stop exit optimistic -- worth $222.50 of a $292.50 result over
    the 1,664 legs of the MNQ 03-24 PullBackAndGo reconciliation, where NT8's exit price
    equals the exit bar's open on 115 of the 116 disagreeing stop fills.

    ``held_from_bar_open`` is what keeps that rule off the entry bar. The position did not
    exist at that bar's open, so a bar whose open sits past the initial stop says nothing:
    price still had to travel up through the trigger to open the position at all, and only
    then could it come back to the stop -- which it reaches at the stop price, not the open.
    """
    n_legs = leg_open.size
    adverse_px, favourable_px = sided(low_px, high_px, direction)

    # The stop fills at the open when the bar gapped through it, otherwise at its own price.
    stop_fill = stop
    if held_from_bar_open and direction * open_px < direction * stop:
        stop_fill = open_px

    stop_hit = direction * adverse_px <= direction * stop
    any_target_hit = False
    nearest_target = 0.0
    for leg in range(n_legs):
        if leg_open[leg] and not np.isnan(leg_target[leg]):
            if limit_filled(favourable_px, leg_target[leg], fill_limit_on_touch, direction):
                if not any_target_hit or abs(leg_target[leg] - open_px) < abs(nearest_target - open_px):
                    nearest_target = leg_target[leg]
                any_target_hit = True
    ambiguous = stop_hit and any_target_hit
    targets_first = ambiguous and targets_reached_first(open_px, stop, nearest_target, ambiguity_policy)

    if stop_hit and not targets_first:
        # The whole position leaves at the stop, adverse slippage meaning a worse fill.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    i,
                    entry_price,
                    fill,
                    initial_stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    EXIT_STOP,
                    risk,
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    ambiguous,
                    direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False
        return written, False

    for leg in range(n_legs):
        if leg_open[leg] and not np.isnan(leg_target[leg]):
            if limit_filled(favourable_px, leg_target[leg], fill_limit_on_touch, direction):
                # Limit order: fills at its price, never worse, no slippage.
                written = write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    i,
                    entry_price,
                    leg_target[leg],
                    initial_stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    EXIT_TARGET,
                    risk,
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    ambiguous,
                    direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False

    if targets_first:
        # The inferred path reached the targets first and the stop on the way back,
        # so whatever is still open leaves on this same bar.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    i,
                    entry_price,
                    fill,
                    initial_stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    EXIT_STOP,
                    risk,
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    ambiguous,
                    direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False

    still_open = False
    for leg in range(n_legs):
        if leg_open[leg]:
            still_open = True
            break

    if still_open and must_flatten:
        fill = close_px - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    i,
                    entry_price,
                    fill,
                    initial_stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    EXIT_SESSION_CLOSE,
                    risk,
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    ambiguous,
                    direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False
        still_open = False

    return written, still_open


@njit(cache=True)
def entry_bracket(
    high: float,
    low: float,
    close: float,
    entry_offset: float,
    stop_offset: float,
    direction: float,
) -> tuple[float, float, float]:
    """One signal bar's order arithmetic: trigger, initial stop, planned risk.

    Public because ``explain.py`` calls it too, and that is the whole point. This used to
    be written out twice, and the two copies disagreed: the audit trail took the trigger to
    be simply ``Low[0]``, dropping the ``Close[0] - 2 ticks`` cap that the simulation
    applies. The cap binds on roughly a third of signals over a whole window, so
    ``nqbt run --explain`` -- the tool a human uses to tick a trade off against a chart
    before trusting anything downstream -- reported the wrong ``trigger``, ``risk_points``,
    ``risk_ticks`` and ``fill_type`` on that share of its rows, while agreeing on the stop,
    which is what made it look right on inspection.

    So: one implementation, called from both places, and the audit trail is by
    construction the arithmetic under audit. Do not inline either copy back.

    ``direction`` is ``+1.0`` long / ``-1.0`` short (see ``nqbt.trades.LONG``/``SHORT``).
    A short entry's trigger is the *favourable* side of the signal bar -- the low -- capped
    by whichever of it and ``close - 2 ticks`` is further favourable still; the stop sits
    ``stop_offset`` beyond the *adverse* side, the high. A long entry mirrors this exactly:
    favourable is the high, adverse the low, and the close-based cap adds rather than
    subtracts. At ``direction = -1.0`` every line below reduces to the short-only formula
    this function used to be.
    """
    adverse, favourable = sided(low, high, direction)
    close_based = close + direction * entry_offset
    trigger = favourable
    if direction * close_based > direction * trigger:
        trigger = close_based
    stop = adverse - direction * stop_offset
    risk = direction * (trigger - stop)
    return trigger, stop, risk


@njit(cache=True)
def sided(low: float, high: float, direction: float) -> tuple[float, float]:
    """Which raw price is adverse and which is favourable for this direction.

    Short (``direction < 0``): adverse is the high -- price rising against the position --
    and favourable is the low. Long is the mirror image. Centralised here because it is
    the one piece of the generalisation that is a data selection rather than an arithmetic
    substitution: no multiplication by ``direction`` picks between two different arrays.
    """
    if direction > 0.0:
        return low, high
    return high, low


AMBIGUITY_WORST_CASE = 0
AMBIGUITY_NEAREST_TO_OPEN = 1


@njit(cache=True)
def targets_reached_first(open_px: float, stop_px: float, target_px: float, policy: int) -> bool:
    """On a bar holding both the stop and a target, did price reach the target first?

    Bar-close OHLC cannot say, so this is an assumption and it is worth being explicit
    about which one.

    ``AMBIGUITY_WORST_CASE`` always answers no: the stop takes the whole position and
    Tier 1 stays pessimistic regardless of what really happened.

    ``AMBIGUITY_NEAREST_TO_OPEN`` reproduces NT8. Price starts the bar at the open and
    reaches the nearer level first. Checked against a real NT8 trade list, this called all
    seven ambiguous bars correctly, including two up bars where the stop was nearer and
    NT8 stopped the whole position out -- which a bar-direction rule gets wrong.

    When the targets go first the stop still takes the remaining legs later in the same
    bar, which is exactly what NT8's trade list shows.
    """
    if policy == AMBIGUITY_NEAREST_TO_OPEN:
        return abs(open_px - target_px) < abs(stop_px - open_px)
    return False


@njit(cache=True)
def limit_filled(favourable_px: float, limit: float, on_touch: bool, direction: float) -> bool:
    """Whether a limit order at ``limit`` fills, given the bar's favourable-side extreme.

    NT8 runs with ``IsFillLimitOnTouch = false`` -- set in the strategy's ``SetDefaults``
    and left unchecked in the Strategy Analyzer -- so price merely *reaching* the limit
    is not a fill. It has to trade through. Measured against a real NT8 trade list, every
    single disagreement about a target fill was a bar whose low equalled the target
    exactly, so this distinction is worth a tick of pedantry.

    A short's target sits below entry, so ``favourable_px`` is the bar's low and the target
    fills once price falls to or through it. A long's target sits above entry, so
    ``favourable_px`` is the high and the comparison flips -- exactly what multiplying by
    ``direction`` does. At ``direction = -1.0`` this reduces to the short-only form.
    """
    if on_touch:
        return direction * favourable_px >= direction * limit
    return direction * favourable_px > direction * limit


@njit(cache=True)
def round_to_tick(price: float, tick_size: float) -> float:
    """Snap a price onto the tick grid, as ``RoundToTickSize`` does in NinjaScript."""
    return np.floor(price / tick_size + 0.5) * tick_size


@njit(cache=True)
def passes_reward_risk(target_r: np.ndarray, minimum: float) -> bool:
    """Optional pre-trade gate on the furthest target's R multiple.

    Off by default (``minimum`` of 0). Because every target is expressed in R, the check
    is independent of price -- it either passes for the rule set or never does.
    """
    if minimum <= 0.0:
        return True
    best = 0.0
    for k in range(target_r.size):
        if not np.isnan(target_r[k]) and target_r[k] > best:
            best = target_r[k]
    return best >= minimum


@njit(cache=True)
def write_leg(
    out: np.ndarray,
    written: int,
    trade_id: int,
    leg: int,
    entry_bar: int,
    exit_bar: int,
    entry_price: float,
    exit_price: float,
    initial_stop: float,
    target_price: float,
    quantity: int,
    reason: float,
    risk: float,
    run_high: float,
    run_low: float,
    point_value: float,
    commission_per_contract: float,
    ambiguous: bool,
    direction: float,
) -> int:
    """Append one leg exit. Returns the new row count, or -1 if ``out`` is full."""
    if written >= out.shape[0]:
        return -1

    # Positive when the trade made money: (exit - entry) for a long, (entry - exit) for a
    # short, which is exactly what multiplying by direction gives.
    pnl_per_unit = (exit_price - entry_price) * direction
    gross = pnl_per_unit * quantity * point_value
    commission = commission_per_contract * quantity
    net = gross - commission

    out[written, C_TRADE_ID] = trade_id
    out[written, C_LEG] = leg + 1
    out[written, C_ENTRY_BAR] = entry_bar
    out[written, C_EXIT_BAR] = exit_bar
    out[written, C_ENTRY_PRICE] = entry_price
    out[written, C_EXIT_PRICE] = exit_price
    out[written, C_INITIAL_STOP] = initial_stop
    out[written, C_TARGET_PRICE] = target_price
    out[written, C_QUANTITY] = quantity
    out[written, C_DIRECTION] = direction
    out[written, C_EXIT_REASON] = reason
    out[written, C_GROSS_PNL] = gross
    out[written, C_COMMISSION] = commission
    out[written, C_NET_PNL] = net
    out[written, C_R_MULTIPLE] = pnl_per_unit / risk if risk > 0.0 else np.nan
    out[written, C_RISK_POINTS] = risk
    # run_high/run_low are tracked unconditionally regardless of direction, so whichever
    # one is adverse (worse for this side) is picked out by taking whichever term is
    # larger -- the other term is negative or smaller by construction.
    out[written, C_MAE] = max(direction * (entry_price - run_high), direction * (entry_price - run_low))
    out[written, C_MFE] = max(direction * (run_high - entry_price), direction * (run_low - entry_price))
    out[written, C_BARS_HELD] = exit_bar - entry_bar
    out[written, C_AMBIGUOUS] = 1.0 if ambiguous else 0.0
    return written + 1


def allocate_output(n_signals: int, n_legs: int = 4) -> np.ndarray:
    """Preallocate the result matrix.

    Every filled signal writes at most one row per leg, and fills can only be fewer than
    signals, so ``n_signals * n_legs`` is a safe upper bound.
    """
    return np.zeros((max(int(n_signals) * n_legs, 1), N_COLUMNS), dtype=np.float64)
