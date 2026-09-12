"""The bracket engine every archetype's exits go through.

One stop, up to four R-multiple targets, an ambiguity policy for the bar that holds both, and a
forced exit at the session close -- resolved identically whichever archetype opened the
position and whichever side it is on. **This is the fidelity-critical code**: every rule the
NT8 reconciliations validated lives here, so a second copy is a second place for Tier 1 and
Tier 2 to drift. **Do not fork it.** Each rule and its evidence: ``docs/nt8-fidelity.md``.

The split is the entry half against the bracket half -- a new archetype writes only the first.
Everything here is an ``@njit(cache=True)`` device function, which Numba inlines into the
calling loop at no cost.

The ``NamedTuple`` blobs below are what the loops pass each other in place of long positional
lists. They have to live in an importable module for ``cache=True`` to reuse its disk cache --
``docs/roadmap.md`` §M20c.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

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

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray


class Bars(NamedTuple):
    """The per-bar series every loop indexes, held together so one bar cannot be split.

    ``force_flat`` rides with the OHLC because it is a fact about the bar rather than about a
    strategy: it marks bars at or past the exit-on-session-close cutoff. Keeping it here is
    what stops the bracket engine being handed a different bar's flag than the one it is
    resolving.
    """

    open_: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    force_flat: BoolArray


class Costs(NamedTuple):
    """What one contract costs to trade, and the grid its prices sit on.

    ``slippage_ticks`` is a tick count, as every NinjaScript expresses it;
    :func:`slippage_points` is the one place it becomes a price.
    """

    tick_size: float
    point_value: float
    commission_per_contract: float
    slippage_ticks: float


class FillRules(NamedTuple):
    """The three NT8 settings that decide how a price level becomes a fill.

    Each one and the evidence behind it: ``docs/nt8-fidelity.md``.
    """

    fill_limit_on_touch: bool
    ambiguity_policy: int
    round_targets: bool


class OpenTrade(NamedTuple):
    """The position as it opened -- fixed for its whole life, whatever the stop does after.

    ``filled_at_open`` is false for an entry that filled intrabar, which is what keeps the
    gapped-stop rule off its entry bar: the position did not exist at that bar's open.
    ``docs/nt8-fidelity.md``, "A stop fills at the open when the bar gaps through it".
    """

    trade_id: int
    entry_bar: int
    entry_price: float
    initial_stop: float
    risk: float
    direction: float
    filled_at_open: bool


class Legs(NamedTuple):
    """The three parallel per-leg arrays, one entry per leg.

    Mutated through the arrays -- ``legs.is_open[leg] = False`` -- never by rebinding, which a
    tuple would not allow.
    """

    is_open: BoolArray
    target: FloatArray
    quantity: IntArray


class Excursion(NamedTuple):
    """The high- and low-water marks the position has reached, which MAE and MFE come from."""

    run_high: float
    run_low: float


class LegExit(NamedTuple):
    """Where, at what and why one leg left."""

    bar: int
    price: float
    reason: float
    ambiguous: bool


@njit(cache=True)
def slippage_points(costs: Costs) -> float:
    """Slippage as a price, from the tick count the NinjaScript expresses it in."""
    return costs.slippage_ticks * costs.tick_size


@njit(cache=True)
def extend_excursion(excursion: Excursion, high: float, low: float) -> Excursion:
    """The water marks after one more bar."""
    return Excursion(max(excursion.run_high, high), min(excursion.run_low, low))


@njit(cache=True)
def resolve_brackets(  # noqa: C901, PLR0912 - one branch per NT8 exit rule, in the order they resolve
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    stop: float,
    legs: Legs,
    excursion: Excursion,
    bars: Bars,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> tuple[int, bool]:
    """Resolve bar ``i`` against the live stop and targets, closing whatever leaves.

    Returns the new write count and whether the position is still open. A write count of ``-1``
    means ``out`` overflowed and the caller must abandon the run.

    Order of resolution: the stop takes the whole position unless the ambiguity policy says the
    targets were reached first; targets fill at their own price with no slippage, being limit
    orders; anything still open after a targets-first bar leaves at the stop on that same bar;
    and force-flat is last, so a position that reached a target and then ran out of session
    records both.

    Called by both the in-position path and the entry-bar path; **do not fork it again**.
    """
    n_legs: int = legs.is_open.size
    direction: float = trade.direction
    open_px: float = bars.open_[i]
    adverse_px: float
    favourable_px: float
    adverse_px, favourable_px = sided(bars.low[i], bars.high[i], direction)
    slippage: float = slippage_points(costs)
    # The position was held from this bar's open unless it filled intrabar on this very bar.
    held_from_bar_open: bool = i > trade.entry_bar or trade.filled_at_open

    # The stop fills at the open when the bar gapped through it, otherwise at its own price.
    stop_fill: float = stop
    if held_from_bar_open and direction * open_px < direction * stop:
        stop_fill = open_px

    stop_hit: bool = direction * adverse_px <= direction * stop
    any_target_hit: bool = False
    nearest_target: float = 0.0
    for leg in range(n_legs):
        if legs.is_open[leg] and not np.isnan(legs.target[leg]):  # noqa: SIM102 - needs a continue guard; #146
            if limit_filled(favourable_px, legs.target[leg], fills.fill_limit_on_touch, direction):
                if not any_target_hit or abs(legs.target[leg] - open_px) < abs(nearest_target - open_px):
                    nearest_target = legs.target[leg]

                any_target_hit = True

    ambiguous: bool = stop_hit and any_target_hit
    targets_first: bool = ambiguous and targets_reached_first(open_px, stop, nearest_target, fills.ambiguity_policy)

    if stop_hit and not targets_first:
        # The whole position leaves at the stop, adverse slippage meaning a worse fill.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_STOP, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False
        return written, False

    for leg in range(n_legs):
        if legs.is_open[leg] and not np.isnan(legs.target[leg]):  # noqa: SIM102 - needs a continue guard; #146
            if limit_filled(favourable_px, legs.target[leg], fills.fill_limit_on_touch, direction):
                # Limit order: fills at its price, never worse, no slippage.
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, legs.target[leg], EXIT_TARGET, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False

    if targets_first:
        # The inferred path reached the targets first and the stop on the way back,
        # so whatever is still open leaves on this same bar.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_STOP, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False

    still_open: bool = False
    for leg in range(n_legs):
        if legs.is_open[leg]:
            still_open = True
            break

    if still_open and bars.force_flat[i]:
        fill = bars.close[i] - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_SESSION_CLOSE, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False
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

    The trigger is the *favourable* side of the signal bar, capped by whichever of it and
    ``close +/- entry_offset`` is further favourable still; the stop sits ``stop_offset``
    beyond the *adverse* side. ``direction`` is ``+1.0`` long / ``-1.0`` short.

    Shared by the jitted loop and by ``explain.py``, so the audit trail is by construction the
    arithmetic under audit. **Do not inline either copy back** -- ``docs/roadmap.md`` §M20a.
    """
    adverse: float
    favourable: float
    adverse, favourable = sided(low, high, direction)
    close_based: float = close + direction * entry_offset
    trigger: float = favourable
    if direction * close_based > direction * trigger:
        trigger = close_based

    stop: float = adverse - direction * stop_offset
    risk: float = direction * (trigger - stop)

    return trigger, stop, risk


NO_BRACKET_FLOOR: float = 0.0  # The floor value that turns :func:`atr_bracket_distance` off, which every port passes.


@njit(cache=True)
def atr_bracket_distance(atr_value: float, multiple: float, floor_points: float) -> float:
    """How far an ATR multiple puts a bracket level from what it is measured against.

    ``floor_points`` is a per-contract dollar floor already converted on the instrument by
    :meth:`nqbt.instruments.Instrument.dollars_to_points`, and :data:`NO_BRACKET_FLOOR`
    switches it off. The one ATR sizing in the codebase -- ``docs/roadmap.md`` § "ATR-multiple
    brackets and the dollar floor".
    """
    return max(atr_value * multiple, floor_points)


@njit(cache=True)
def swing_stop(bars: Bars, signal_bar: int, lookback: int, offset: float, direction: float) -> float:
    """A structural stop: the adverse extreme of the last ``lookback`` completed bars, offset.

    The window ends at ``signal_bar`` and includes it, and never reads the bar the fill happens
    on. ``offset`` is a price rather than a tick count, and pushes the stop *beyond* the extreme
    so it does not sit exactly on the level it protects. **Not floored** -- a structural level
    widened to clear a cost floor stops being the level it is.

    Shared by EmaCrossover's swing mode and ElasticBand's :data:`~nqbt.sim.types.STOP_SWING`.
    **Do not fork it.**
    """
    start: int = signal_bar - lookback + 1
    start = max(start, 0)
    extreme: float = 0.0
    for j in range(start, signal_bar + 1):
        adverse, _ = sided(bars.low[j], bars.high[j], direction)
        if j == start or direction * adverse < direction * extreme:
            extreme = adverse

    return extreme - direction * offset


@njit(cache=True)
def sided(low: float, high: float, direction: float) -> tuple[float, float]:
    """Which raw price is adverse and which is favourable for this direction.

    The one piece of the direction generalisation that is a data selection rather than an
    arithmetic substitution, which is why it is a function rather than a multiplication.
    """
    if direction > 0.0:
        return low, high

    return high, low


AMBIGUITY_WORST_CASE: int = 0
AMBIGUITY_NEAREST_TO_OPEN: int = 1


@njit(cache=True)
def targets_reached_first(open_px: float, stop_px: float, target_px: float, policy: int) -> bool:
    """On a bar holding both the stop and a target, did price reach the target first?

    Bar-close OHLC cannot say, so this is an assumption. ``AMBIGUITY_NEAREST_TO_OPEN``
    reproduces NT8; ``AMBIGUITY_WORST_CASE`` always answers no, which is *more* pessimistic
    than NT8 rather than equal to it. Evidence: ``docs/nt8-fidelity.md``, "Ambiguous bars
    resolve to whichever level is nearer the open".
    """
    if policy == AMBIGUITY_NEAREST_TO_OPEN:
        return abs(open_px - target_px) < abs(stop_px - open_px)

    return False


@njit(cache=True)
def limit_filled(favourable_px: float, limit: float, on_touch: bool, direction: float) -> bool:
    """Whether a limit order at ``limit`` fills, given the bar's favourable-side extreme.

    NT8 runs with ``IsFillLimitOnTouch = false``, so price merely *reaching* the limit is not a
    fill -- it has to trade through. See ``docs/nt8-fidelity.md``, "Limit orders must trade
    *through*, not touch".
    """
    if on_touch:
        return direction * favourable_px >= direction * limit

    return direction * favourable_px > direction * limit


@njit(cache=True)
def round_to_tick(price: float, tick_size: float) -> float:
    """Snap a price onto the tick grid, as ``RoundToTickSize`` does in NinjaScript."""
    return float(np.floor(price / tick_size + 0.5) * tick_size)


@njit(cache=True)
def passes_reward_risk(target_r: FloatArray, minimum: float) -> bool:
    """Optional pre-trade gate on the furthest target's R multiple, off at ``minimum`` of 0.

    Every target is expressed in R, so the check is independent of price: it either passes for
    the rule set or never does.
    """
    if minimum <= 0.0:
        return True

    best: float = 0.0
    for k in range(target_r.size):
        if not np.isnan(target_r[k]) and target_r[k] > best:
            best = target_r[k]

    return best >= minimum


@njit(cache=True)
def write_leg(
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    legs: Legs,
    leg: int,
    leg_exit: LegExit,
    excursion: Excursion,
    costs: Costs,
) -> int:
    """Append one leg exit. Returns the new row count, or -1 if ``out`` is full."""
    if written >= out.shape[0]:
        return -1

    direction: float = trade.direction
    quantity: int = legs.quantity[leg]
    pnl_per_unit: float = (leg_exit.price - trade.entry_price) * direction  # always positive for a winning trade
    gross: float = pnl_per_unit * quantity * costs.point_value
    commission: float = costs.commission_per_contract * quantity
    net: float = gross - commission

    out[written, C_TRADE_ID] = trade.trade_id
    out[written, C_LEG] = leg + 1
    out[written, C_ENTRY_BAR] = trade.entry_bar
    out[written, C_EXIT_BAR] = leg_exit.bar
    out[written, C_ENTRY_PRICE] = trade.entry_price
    out[written, C_EXIT_PRICE] = leg_exit.price
    out[written, C_INITIAL_STOP] = trade.initial_stop
    out[written, C_TARGET_PRICE] = legs.target[leg]
    out[written, C_QUANTITY] = quantity
    out[written, C_DIRECTION] = direction
    out[written, C_EXIT_REASON] = leg_exit.reason
    out[written, C_GROSS_PNL] = gross
    out[written, C_COMMISSION] = commission
    out[written, C_NET_PNL] = net
    out[written, C_R_MULTIPLE] = pnl_per_unit / trade.risk if trade.risk > 0.0 else np.nan
    out[written, C_RISK_POINTS] = trade.risk
    # run_high/run_low are tracked regardless of direction, so the adverse one is whichever
    # term is larger; the other is negative or smaller by construction.
    out[written, C_MAE] = max(
        direction * (trade.entry_price - excursion.run_high),
        direction * (trade.entry_price - excursion.run_low),
    )
    out[written, C_MFE] = max(
        direction * (excursion.run_high - trade.entry_price),
        direction * (excursion.run_low - trade.entry_price),
    )
    out[written, C_BARS_HELD] = leg_exit.bar - trade.entry_bar
    out[written, C_AMBIGUOUS] = 1.0 if leg_exit.ambiguous else 0.0

    return written + 1


def allocate_output(n_signals: int, n_legs: int = 4) -> FloatArray:
    """Preallocate the result matrix.

    Every filled signal writes at most one row per leg, and fills can only be fewer than
    signals, so ``n_signals * n_legs`` is a safe upper bound.
    """
    return np.zeros((max(int(n_signals) * n_legs, 1), N_COLUMNS), dtype=np.float64)
