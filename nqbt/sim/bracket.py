"""The bracket engine every archetype's exits go through, in one copy that must not be forked.

One stop, up to four R-multiple targets, an ambiguity policy for the bar that holds both, and a
forced exit at the session close, resolved identically for every archetype and either side. A
new archetype writes the entry half only. Each rule and its evidence: ``docs/nt8-fidelity.md``;
the design: ``nqbt/README.md`` § "sim/bracket.py".
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

    ``force_flat`` marks bars at or past the exit-on-session-close cutoff.
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

    ``filled_at_open`` is false for an entry that filled intrabar, which keeps the gapped-stop
    rule off its entry bar -- ``docs/nt8-fidelity.md``, "A stop fills at the open when the bar
    gaps through it".
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
    """Convert slippage to a price, from the tick count the NinjaScript expresses it in."""
    return costs.slippage_ticks * costs.tick_size


@njit(cache=True)
def extend_excursion(excursion: Excursion, high: float, low: float) -> Excursion:
    """Extend the water marks by one more bar."""
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
    targets were reached first; targets fill at their own price with no slippage; anything still
    open after a targets-first bar leaves at the stop on that same bar; and force-flat is last.
    Called by both the in-position path and the entry-bar path.
    """
    n_legs = legs.is_open.size
    direction = trade.direction
    open_px = bars.open_[i]
    adverse_px, favourable_px = sided(bars.low[i], bars.high[i], direction)
    slippage = slippage_points(costs)
    # The position was held from this bar's open unless it filled intrabar on this very bar.
    held_from_bar_open = i > trade.entry_bar or trade.filled_at_open

    # The stop fills at the open when the bar gapped through it, otherwise at its own price.
    stop_fill = stop
    if held_from_bar_open and direction * open_px < direction * stop:
        stop_fill = open_px

    stop_hit = direction * adverse_px <= direction * stop
    any_target_hit = False
    nearest_target = 0.0
    for leg in range(n_legs):
        if legs.is_open[leg] and not np.isnan(legs.target[leg]):  # noqa: SIM102 - needs a continue guard; #146
            if limit_filled(favourable_px, legs.target[leg], fills.fill_limit_on_touch, direction):
                if not any_target_hit or abs(legs.target[leg] - open_px) < abs(nearest_target - open_px):
                    nearest_target = legs.target[leg]

                any_target_hit = True
    ambiguous = stop_hit and any_target_hit
    targets_first = ambiguous and targets_reached_first(open_px, stop, nearest_target, fills.ambiguity_policy)

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

    still_open = False
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
def flatten_position(
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    legs: Legs,
    leg_exit: LegExit,
    excursion: Excursion,
    costs: Costs,
) -> int:
    """Close every still-open leg at one price for one reason. Returns the new row count.

    The writer for a market order flattening the whole position. Not a fill rule: the caller
    decides the bar, the price and the reason.
    """
    for leg in range(legs.is_open.size):
        if not legs.is_open[leg]:
            continue

        written = write_leg(out, written, trade, legs, leg, leg_exit, excursion, costs)
        if written < 0:
            return -1

        legs.is_open[leg] = False

    return written


@njit(cache=True)
def hold_expired(entry_bar: int, i: int, max_hold_bars: int) -> bool:
    """Return whether bar ``i``'s close is where the maximum-hold-time exit is submitted.

    Off at ``0``. The order goes in at the close of bar ``entry_bar + max_hold_bars`` and fills
    at the next bar's open -- ``docs/nt8-fidelity.md``, "The maximum hold time, and why it is its
    own exit code".
    """
    return max_hold_bars > 0 and i - entry_bar >= max_hold_bars


@njit(cache=True)
def entry_bracket(
    high: float,
    low: float,
    close: float,
    entry_offset: float,
    stop_offset: float,
    direction: float,
) -> tuple[float, float, float]:
    """Compute one signal bar's order arithmetic: trigger, initial stop, planned risk.

    The trigger is the *favourable* side of the signal bar, capped by whichever of it and
    ``close +/- entry_offset`` is further favourable still; the stop sits ``stop_offset``
    beyond the *adverse* side. ``direction`` is ``+1.0`` long / ``-1.0`` short.

    Shared by the jitted loop and by ``explain.py`` -- ``docs/roadmap.md`` §M20a.
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
def stop_entry_fill(
    bars: Bars,
    i: int,
    trigger: float,
    slippage: float,
    direction: float,
) -> tuple[bool, float]:
    """Return whether a resting stop-market entry fills on bar ``i``, and at what price.

    A market order once triggered, so a gap through the trigger fills at the open; otherwise the
    bar's favourable extreme has to reach it and the fill is the trigger. Shared by OpeningRange's
    stop entries and EmaPullback's confirmation entry -- ``docs/nt8-fidelity.md``, "Fill".
    """
    if direction * bars.open_[i] >= direction * trigger:
        return True, bars.open_[i] + direction * slippage

    _, touch = sided(bars.low[i], bars.high[i], direction)
    if direction * touch >= direction * trigger:
        return True, trigger + direction * slippage

    return False, 0.0


NO_BRACKET_FLOOR = 0.0
"""The floor value that switches :func:`atr_bracket_distance` off, which every port passes."""


@njit(cache=True)
def atr_bracket_distance(atr_value: float, multiple: float, floor_points: float) -> float:
    """Return how far an ATR multiple puts a bracket level from what it is measured against.

    ``floor_points`` is a per-contract dollar floor already converted on the instrument by
    :meth:`nqbt.instruments.Instrument.dollars_to_points`, and :data:`NO_BRACKET_FLOOR`
    switches it off. The one ATR sizing in the codebase -- ``docs/roadmap.md`` § "ATR-multiple
    brackets and the dollar floor".
    """
    return max(atr_value * multiple, floor_points)


@njit(cache=True)
def swing_stop(
    bars: Bars,
    signal_bar: int,
    lookback: int,
    offset: float,
    direction: float,
) -> float:
    """Return a structural stop: the adverse extreme of the last ``lookback`` completed bars, offset.

    The window ends at ``signal_bar`` and includes it. ``offset`` is a price rather than a tick
    count, and pushes the stop *beyond* the extreme. Not floored. Shared by EmaCrossover's swing
    mode and ElasticBand's :data:`~nqbt.sim.types.STOP_SWING`.
    """
    start = signal_bar - lookback + 1
    start = max(start, 0)
    extreme = 0.0
    for j in range(start, signal_bar + 1):
        adverse, _ = sided(bars.low[j], bars.high[j], direction)
        if j == start or direction * adverse < direction * extreme:
            extreme = adverse

    return extreme - direction * offset


@njit(cache=True)
def tightened_stop(stop: float, candidate: float, direction: float) -> float:
    """Return whichever of the two is nearer the market, which is the one ratchet in the codebase.

    A ``nan`` candidate leaves the stop alone -- ``docs/nt8-fidelity.md``, "Ratchet reads the
    just-closed bar".
    """
    if direction * candidate > direction * stop:
        return candidate

    return stop


@njit(cache=True)
def avoid_round_number(
    stop: float,
    spacing: float,
    offset: float,
    tick_size: float,
    direction: float,
) -> float:
    """Push a stop that lands exactly on a multiple of ``spacing`` further from the entry.

    ``spacing`` is a price -- 25 points, say -- and a spacing of ``0`` switches the rule off.
    Only an exact landing moves. Meaningless on a back-adjusted series -- ``docs/roadmap.md``
    § "The build spec's three loose ends".
    """
    if spacing <= 0.0:
        return stop

    remainder = stop - spacing * np.floor(stop / spacing + 0.5)
    if abs(remainder) >= 0.5 * tick_size:
        return stop

    return stop - direction * offset


@njit(cache=True)
def sided(low: float, high: float, direction: float) -> tuple[float, float]:
    """Return which raw price is adverse and which is favourable for this direction."""
    if direction > 0.0:
        return low, high

    return high, low


AMBIGUITY_WORST_CASE = 0
AMBIGUITY_NEAREST_TO_OPEN = 1
AMBIGUITY_BEST_CASE = 2
"""NT8's guess, and the two outcomes it is guessing between.

Only ``AMBIGUITY_NEAREST_TO_OPEN`` reproduces NT8, and it is the only one anything is ranked on;
the other two are for ``nqbt/disambiguate.py`` -- ``docs/roadmap.md`` §M28.4."""


@njit(cache=True)
def targets_reached_first(open_px: float, stop_px: float, target_px: float, policy: int) -> bool:
    """Return whether price reached the target first, on a bar holding both the stop and a target.

    ``AMBIGUITY_NEAREST_TO_OPEN`` reproduces NT8; the other two answer always-no and always-yes
    -- ``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the open".
    """
    if policy == AMBIGUITY_NEAREST_TO_OPEN:
        return abs(open_px - target_px) < abs(stop_px - open_px)

    return policy == AMBIGUITY_BEST_CASE


@njit(cache=True)
def limit_filled(favourable_px: float, limit: float, on_touch: bool, direction: float) -> bool:
    """Return whether a limit order at ``limit`` fills, given the bar's favourable-side extreme.

    Unless ``on_touch``, price has to trade through the limit -- ``docs/nt8-fidelity.md``, "Limit
    orders must trade *through*, not touch".
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
    """Check the optional pre-trade gate on the furthest target's R multiple, off at ``minimum`` of 0.

    Every target is in R, so the check passes for the whole rule set or for none of it.
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

    direction = trade.direction
    quantity = legs.quantity[leg]
    # Positive when the trade made money, whichever side it was on.
    pnl_per_unit = (leg_exit.price - trade.entry_price) * direction
    gross = pnl_per_unit * quantity * costs.point_value
    commission = costs.commission_per_contract * quantity
    net = gross - commission

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
