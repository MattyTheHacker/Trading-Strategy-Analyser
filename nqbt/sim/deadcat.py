"""DeadCatBounce archetype: short an inverted hammer into an established downtrend.

Ported from ``ninjatrader-scripts/Strategies/DeadCatBounce.cs``, which is the source of
truth. Where the C# is ambiguous the resolution is recorded below rather than guessed at
silently, because these choices move trade counts far more than any parameter does.

**Order lifetime.** ``EnterShortStopMarket`` under NT8's managed approach is *not* GTC
despite ``TimeInForce.Gtc`` on the strategy: an unfilled entry is cancelled at the close of
the following bar. A signal at the close of bar ``t`` therefore places an order live for
bar ``t+1`` only.

**Trigger.** ``min(Low[0], Close[0] - 2 ticks)``, not simply the bar's low. An inverted
hammer closes near its low by construction, so the close-based term binds on about a third
of signals and drags the trigger 1-2 ticks under the low, which is enough to turn a
marginal fill into no fill at all.

**Fill.** On bar ``t+1``, a gap through the trigger fills at the open; otherwise a trade
down to the trigger fills at the trigger. No touch, no fill, order gone.

**Exit precedence.** Bar-close OHLC cannot say whether a bar hit the stop or a target
first, so ``ambiguity_policy`` decides. NT8 fills whichever level sits nearer the bar's
open, verified against a real trade list where that rule called all seven ambiguous bars
correctly. The alternative is a blanket worst case, which is more pessimistic than NT8 and
therefore breaks Tier 1 / Tier 2 parity in the safe direction. Either way the bar is
flagged ``ambiguous_bar`` so the cost of the assumption stays measurable.

**Limit fills.** ``IsFillLimitOnTouch = false`` in the NinjaScript, so a profit target
needs price to trade *through* it, not merely reach it. Every disagreement with NT8 about
a target fill came from a bar whose low equalled the target to the tick.

**Ratchet.** At the close of each bar in a position the stop becomes
``High[0] + 2 ticks`` -- the just-closed bar's high -- if that is tighter, never looser,
shared across all four legs. The stop set at the close of bar ``i`` is live during bar
``i+1``. ``ratchet_lag`` exposes the older ``High[1]`` variant, which holds trades about a
third longer.

**Targets.** Each leg's target is rounded onto the tick grid, as ``RoundToTickSize`` does
in the NinjaScript: a 1.5x multiple of an odd tick count otherwise lands on a half tick.

**Same-bar stop-out.** A stop can fire on the bar the entry filled: the entry is at the
bar's low and the stop above it, so a wide enough bar reaches both.
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
    EXIT_END_OF_DATA,
    EXIT_SESSION_CLOSE,
    EXIT_STOP,
    EXIT_TARGET,
    N_COLUMNS,
)


@njit(cache=True)
def simulate_deadcat(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signal: np.ndarray,
    force_flat: np.ndarray,
    leg_quantities: np.ndarray,
    target_r: np.ndarray,
    tick_size: float,
    point_value: float,
    stop_offset_ticks: float,
    entry_offset_ticks: float,
    tp_multiplier: float,
    max_risk_ticks: float,
    commission_per_contract: float,
    slippage_ticks: float,
    bars_required: int,
    min_reward_risk: float,
    ratchet_lag: int,
    ratchet_offset_ticks: float,
    block_entry_at_session_close: bool,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    direction: float,
    round_targets: bool,
    out: np.ndarray,
) -> int:
    """Run one bracket archetype over one dataset, writing one row per leg exit.

    Shared by DeadCatBounce and PullBackAndGo.cs -- both are a stop order in the trade
    direction, a ratcheting stop, and up to four R-multiple targets with the last leg a
    runner. ``signal`` is the precomputed conjunction of every active entry filter, and
    ``force_flat`` marks bars at or past the exit-on-session-close cutoff. ``direction`` is
    ``+1.0`` long / ``-1.0`` short (see ``nqbt.trades.LONG``/``SHORT``); DeadCatBounce
    always calls this with ``SHORT``, since the NinjaScript has no long variant.

    ``ratchet_offset_ticks`` is separate from ``stop_offset_ticks`` because the two C#
    strategies genuinely differ here, not just in direction: ``DeadCatBounce.cs`` ratchets
    to ``High[0] + 2 ticks`` every bar, reapplying the same offset used for the initial
    stop, while ``PullBackAndGo.cs`` ratchets to a bare ``Low[1]`` with no offset at all.
    ``run_deadcat`` passes ``stop_offset_ticks`` here to reproduce its behaviour exactly;
    ``run_pullbackandgo`` passes ``0``.

    ``round_targets`` exists for the same reason: ``DeadCatBounce.cs`` rounds every target
    onto the tick grid via ``RoundToTickSize``, but ``PullBackAndGo.cs`` does not call it at
    all, so its targets are ported un-rounded even though that can land on a half tick --
    matching the C# text rather than assuming symmetry. Whether NT8 silently snaps such a
    price at submission is a live-platform question M15.5's reconciliation has to settle,
    not something to guess at here.

    Returns the number of rows written to ``out``; a negative return means ``out`` was too
    small.
    """
    n = close.size
    n_legs = leg_quantities.size
    slippage = slippage_ticks * tick_size
    stop_offset = stop_offset_ticks * tick_size
    entry_offset = entry_offset_ticks * tick_size
    ratchet_offset = ratchet_offset_ticks * tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1  # bar whose signal placed the order now resting
    pending_trigger = 0.0
    pending_stop = 0.0

    entry_price = 0.0
    entry_bar = 0
    stop = 0.0
    risk = 0.0
    initial_stop = 0.0
    run_high = 0.0
    run_low = 0.0

    leg_open = np.zeros(n_legs, dtype=np.bool_)
    leg_target = np.zeros(n_legs, dtype=np.float64)

    for i in range(n):
        # ---- exits, using the stop and targets set at the close of bar i-1 ----------
        if in_position:
            if run_high < high[i]:
                run_high = high[i]
            if run_low > low[i]:
                run_low = low[i]

            written, in_position = _resolve_brackets(
                out, written, trade_id, entry_bar, i,
                entry_price, initial_stop, stop, risk,
                leg_open, leg_target, leg_quantities, run_high, run_low,
                open_[i], high[i], low[i], close[i], force_flat[i],
                slippage, point_value, commission_per_contract,
                fill_limit_on_touch, ambiguity_policy, direction,
            )
            if written < 0:
                return -1

        # ---- a resting entry order lives for exactly this one bar -------------------
        # pending_bar >= 0 matters at i == 0: the sentinel -1 would otherwise equal
        # i - 1 there too. The short-only loop never noticed, because a zero-initialised
        # pending_trigger makes `open_[i] <= pending_trigger` false for any real price and
        # the touch test below is never reached; direction generalises the comparison to
        # `direction * open_[i] >= direction * pending_trigger`, which a long's positive
        # price satisfies against that same zero trigger immediately.
        elif pending_bar >= 0 and pending_bar == i - 1:
            filled = False
            fill = 0.0
            # A bar at or past the flatten cutoff cancels a resting order rather than
            # letting it fill: no new position may open once the account rules require
            # being flat. force_flat[i] here, not block_entry_at_session_close -- that
            # flag only stops a *new* signal being accepted on a force-flat bar, and does
            # not reach an order that rested from the bar before.
            if not force_flat[i]:
                if direction * open_[i] >= direction * pending_trigger:
                    fill = open_[i] + direction * slippage  # gapped through the trigger
                    filled = True
                else:
                    _, touch = _sided(low[i], high[i], direction)
                    if direction * touch >= direction * pending_trigger:
                        fill = pending_trigger + direction * slippage
                        filled = True

            if filled:
                trade_id += 1
                entry_price = fill
                entry_bar = i
                initial_stop = pending_stop
                stop = pending_stop
                risk = direction * (pending_trigger - pending_stop)
                run_high = high[i]
                run_low = low[i]
                for leg in range(n_legs):
                    leg_open[leg] = True
                    if np.isnan(target_r[leg]):
                        leg_target[leg] = np.nan
                    else:
                        # RoundToTickSize in DeadCatBounce.cs: a 1.5x multiple of an odd
                        # tick count lands on a half tick, which no exchange accepts.
                        # PullBackAndGo.cs never calls it -- see round_targets in the
                        # docstring -- so this must stay conditional, not assumed.
                        raw = pending_trigger + direction * risk * target_r[leg] * tp_multiplier
                        leg_target[leg] = _round_to_tick(raw, tick_size) if round_targets else raw

                # The entry bar can reach the stop as well: entry sits at the signal
                # bar's low, the stop above the signal bar's high. Same resolution as any
                # other bar -- the `leg_open` guards inside are simply no-ops here, since
                # every leg was opened a few lines above.
                written, in_position = _resolve_brackets(
                    out, written, trade_id, entry_bar, i,
                    entry_price, initial_stop, stop, risk,
                    leg_open, leg_target, leg_quantities, run_high, run_low,
                    open_[i], high[i], low[i], close[i], force_flat[i],
                    slippage, point_value, commission_per_contract,
                    fill_limit_on_touch, ambiguity_policy, direction,
                )
                if written < 0:
                    return -1

            pending_bar = -1  # filled, cancelled at the flatten point, or just missed -- gone

        # ---- close of bar i: ratchet, or look for a new signal ----------------------
        if in_position:
            ref = i - ratchet_lag
            if ref >= 0:
                adverse_ref, _ = _sided(low[ref], high[ref], direction)
                new_stop = adverse_ref - direction * ratchet_offset
                if direction * new_stop > direction * stop:
                    stop = new_stop
        elif i >= bars_required and signal[i] and not (
            block_entry_at_session_close and force_flat[i]
        ):
            trigger, candidate_stop, candidate_risk = entry_bracket(
                high[i], low[i], close[i], entry_offset, stop_offset, direction
            )
            # MaxRiskPerTrade is expressed in ticks, not dollars.
            too_risky = candidate_risk > max_risk_ticks * tick_size
            if (
                candidate_risk > 0.0
                and not too_risky
                and _passes_reward_risk(target_r, min_reward_risk)
            ):
                pending_bar = i
                pending_trigger = trigger
                pending_stop = candidate_stop

    # The series can stop mid-session, so anything still open is liquidated at the last
    # bar rather than dropped -- an untracked open position would silently lose its P&L.
    if in_position:
        last = n - 1
        exit_fill = close[last] - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = _write(
                    out, written, trade_id, leg, entry_bar, last, entry_price, exit_fill,
                    initial_stop, leg_target[leg], leg_quantities[leg],
                    EXIT_END_OF_DATA, risk, run_high, run_low, point_value,
                    commission_per_contract, False, direction,
                )
                if written < 0:
                    return -1

    return written


@njit(cache=True)
def _resolve_brackets(
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
    """
    n_legs = leg_open.size
    adverse_px, favourable_px = _sided(low_px, high_px, direction)

    stop_hit = direction * adverse_px <= direction * stop
    any_target_hit = False
    nearest_target = 0.0
    for leg in range(n_legs):
        if leg_open[leg] and not np.isnan(leg_target[leg]):
            if _limit_filled(favourable_px, leg_target[leg], fill_limit_on_touch, direction):
                if not any_target_hit or abs(leg_target[leg] - open_px) < abs(
                    nearest_target - open_px
                ):
                    nearest_target = leg_target[leg]
                any_target_hit = True
    ambiguous = stop_hit and any_target_hit
    targets_first = ambiguous and _targets_reached_first(
        open_px, stop, nearest_target, ambiguity_policy
    )

    if stop_hit and not targets_first:
        # The whole position leaves at the stop, adverse slippage meaning a worse fill.
        fill = stop - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = _write(
                    out, written, trade_id, leg, entry_bar, i, entry_price, fill,
                    initial_stop, leg_target[leg], leg_quantities[leg],
                    EXIT_STOP, risk, run_high, run_low, point_value,
                    commission_per_contract, ambiguous, direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False
        return written, False

    for leg in range(n_legs):
        if leg_open[leg] and not np.isnan(leg_target[leg]):
            if _limit_filled(favourable_px, leg_target[leg], fill_limit_on_touch, direction):
                # Limit order: fills at its price, never worse, no slippage.
                written = _write(
                    out, written, trade_id, leg, entry_bar, i, entry_price,
                    leg_target[leg], initial_stop, leg_target[leg],
                    leg_quantities[leg], EXIT_TARGET, risk, run_high, run_low,
                    point_value, commission_per_contract, ambiguous, direction,
                )
                if written < 0:
                    return -1, False
                leg_open[leg] = False

    if targets_first:
        # The inferred path reached the targets first and the stop on the way back,
        # so whatever is still open leaves on this same bar.
        fill = stop - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = _write(
                    out, written, trade_id, leg, entry_bar, i, entry_price, fill,
                    initial_stop, leg_target[leg], leg_quantities[leg],
                    EXIT_STOP, risk, run_high, run_low, point_value,
                    commission_per_contract, ambiguous, direction,
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
                written = _write(
                    out, written, trade_id, leg, entry_bar, i, entry_price, fill,
                    initial_stop, leg_target[leg], leg_quantities[leg],
                    EXIT_SESSION_CLOSE, risk, run_high, run_low, point_value,
                    commission_per_contract, ambiguous, direction,
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
    applies. Since the cap binds on about half of all signals, ``nqbt run --explain`` --
    the tool a human uses to tick a trade off against a chart before trusting anything
    downstream -- reported the wrong ``trigger``, ``risk_points``, ``risk_ticks`` and
    ``fill_type`` on half its rows, while agreeing on the stop, which is what made it look
    right on inspection.

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
    adverse, favourable = _sided(low, high, direction)
    close_based = close + direction * entry_offset
    trigger = favourable
    if direction * close_based > direction * trigger:
        trigger = close_based
    stop = adverse - direction * stop_offset
    risk = direction * (trigger - stop)
    return trigger, stop, risk


@njit(cache=True)
def _sided(low: float, high: float, direction: float) -> tuple[float, float]:
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
def _targets_reached_first(
    open_px: float, stop_px: float, target_px: float, policy: int
) -> bool:
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
def _limit_filled(favourable_px: float, limit: float, on_touch: bool, direction: float) -> bool:
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
def _round_to_tick(price: float, tick_size: float) -> float:
    """Snap a price onto the tick grid, as ``RoundToTickSize`` does in NinjaScript."""
    return np.floor(price / tick_size + 0.5) * tick_size


@njit(cache=True)
def _passes_reward_risk(target_r: np.ndarray, minimum: float) -> bool:
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
def _write(
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
