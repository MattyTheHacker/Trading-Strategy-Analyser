"""FailedBreak archetype: buy the close back inside a range whose edge was just traded through.

``TIER1_ONLY``; its rules and the NinjaScript each would become: ``docs/nt8-fidelity.md`` §M66.
The design: ``docs/findings/m66-failed-break-spec.md``.

The prices a trade reads are all fixed at its signal bar, so a drawn bar can carry them at the
same distances from its own close -- ``docs/nt8-fidelity.md``, "A drawn bar carries a real
signal's geometry".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import sessionrange, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    FB_LEVEL_YESTERDAY,
    FB_LEVELS,
    FB_RANGE_KEYS,
    FB_TARGET_MID_OPPOSITE,
    FB_TARGET_OPPOSITE_NEXT,
    FB_TARGET_R,
    STOP_MIN_TICKS,
)

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IndexArray, IntArray, OffsetArray
    from nqbt.context import Dataset
    from nqbt.sim.types import FailedBreakParams
    from nqbt.trades import LegMatrix

NO_SIGNAL = -1
""":attr:`Geometry.row_of_bar` on a bar that submits nothing."""

_NOT_YET_INSIDE = 0
_INSIDE = 1
_SWEPT = 2


class Geometry(NamedTuple):
    """The prices each signal's trade reads, one row per signal, and which bar submits which."""

    row_of_bar: IndexArray
    """Per bar: the row it submits, or :data:`NO_SIGNAL`."""

    extreme: FloatArray
    """Per row: the furthest price the sweep traded, which the stop sits beyond."""

    level: FloatArray
    """Per row: the swept level, which a close back beyond exits on."""

    targets: FloatArray
    """``[n_rows, n_legs]``: each leg's target price, ``nan`` for no target. Unread under R targets."""


class FailedBreakRules(NamedTuple):
    """The rule set :func:`simulate_failedbreak` reads, one field per parameter."""

    direction: float
    exit_on_rebreak: bool
    stop_offset: float
    round_number_points: float
    round_number_offset: float
    use_r_targets: bool
    tp_multiplier: float
    bars_required: int
    block_entry_at_session_close: bool
    max_hold_bars: int
    early_exit: bracket.EarlyExit = bracket.EARLY_EXIT_OFF
    breakeven: bracket.Breakeven = bracket.BREAKEVEN_OFF
    stop_tightening: bracket.StopTightening = bracket.STOP_TIGHTENING_OFF


class LevelSeries(NamedTuple):
    """One level's range as this session may read it: per session the edges, per bar the flag."""

    high: FloatArray
    low: FloatArray
    armed: BoolArray


@njit(cache=True)
def scan_recoveries(  # noqa: C901 - one branch per state, in bar order
    low: FloatArray,
    high: FloatArray,
    close: FloatArray,
    seconds: FloatArray,
    armed: BoolArray,
    session_id: IndexArray,
    level: FloatArray,
    direction: float,
    max_sweep_seconds: float,
) -> tuple[BoolArray, FloatArray]:
    """Return, per bar, whether it closes a sweep back inside the level, and the sweep's extreme.

    ``level`` is per session. A level has to be closed inside before it can be swept, and both
    the trade through it and the close back are strict -- ``docs/nt8-fidelity.md`` §M66.
    """
    n = close.size
    fired = np.zeros(n, dtype=np.bool_)
    extremes = np.full(n, np.nan, dtype=np.float64)
    state = _NOT_YET_INSIDE
    current_session = -1
    started = 0.0
    extreme = 0.0

    for i in range(n):
        if not armed[i]:
            continue

        session = session_id[i]
        if session != current_session:
            current_session = session
            state = _NOT_YET_INSIDE

        swept = level[session]
        adverse, _ = bracket.sided(low[i], high[i], direction)
        back_inside = direction * (close[i] - swept) > 0.0
        if state == _NOT_YET_INSIDE:
            if back_inside:
                state = _INSIDE

            continue

        if state == _INSIDE:
            if direction * (adverse - swept) >= 0.0:
                continue

            started = seconds[i]
            extreme = adverse
            state = _SWEPT
        elif direction * (adverse - extreme) < 0.0:
            extreme = adverse

        if not back_inside:
            continue

        state = _INSIDE
        if seconds[i] - started <= max_sweep_seconds:
            fired[i] = True
            extremes[i] = extreme

    return fired, extremes


def level_series(data: Dataset, level: int) -> LevelSeries:
    """Return one level's range as a session may read it.

    ``yesterday`` is the previous session's cash range, readable from this session's first bar and
    not at all across a roll. The other two are this session's own, once their window has closed.
    """
    key: sessionrange.RangeKey = FB_RANGE_KEYS[level]
    if level != FB_LEVEL_YESTERDAY:
        return LevelSeries(data.range_high(key), data.range_low(key), data.range_armed(key))

    new_contract: BoolArray = data.range_new_contract()
    high: FloatArray = sessionrange.previous_session(data.range_high(key), new_contract)
    low: FloatArray = sessionrange.previous_session(data.range_low(key), new_contract)

    return LevelSeries(high, low, np.isfinite(low)[data.range_session_id()])


def edges(series: LevelSeries, direction: float) -> tuple[FloatArray, FloatArray]:
    """Return a level's two edges per session, the one a sweep goes through first."""
    if direction == trades.LONG:
        return series.low, series.high

    return series.high, series.low


def first_target(series: LevelSeries, params: FailedBreakParams) -> FloatArray:
    """Return, per session, the first target a level scheme sets: the midpoint or the opposite edge."""
    if params.target_mode == FB_TARGET_MID_OPPOSITE:
        return (series.high + series.low) / 2.0

    _, opposite = edges(series, params.direction)

    return opposite


def next_levels(
    data: Dataset, params: FailedBreakParams, signal_bars: OffsetArray, beyond: FloatArray
) -> FloatArray:
    """Return, per signal, the nearest opposing edge of the other two ranges past ``beyond``, or ``nan``.

    A range is read only where it is readable at the signal bar.
    """
    direction: float = params.direction
    session_of: IndexArray = data.range_session_id()[signal_bars]
    nearest: FloatArray = np.full(signal_bars.size, np.inf, dtype=np.float64)
    for level in FB_LEVELS:
        if level == params.level:
            continue

        series: LevelSeries = level_series(data, level)
        _, opposing = edges(series, direction)
        candidate: FloatArray = direction * opposing[session_of]
        usable: BoolArray = series.armed[signal_bars] & (candidate > direction * beyond)
        nearest = np.where(usable, np.minimum(nearest, candidate), nearest)

    return np.where(np.isfinite(nearest), direction * nearest, np.nan)


def signal_targets(
    data: Dataset, params: FailedBreakParams, series: LevelSeries, signal_bars: OffsetArray
) -> FloatArray:
    """Return each signal's target prices, ``[n_signals, n_legs]``."""
    n_legs: int = len(params.target_levels)
    targets: FloatArray = np.full((signal_bars.size, n_legs), np.nan, dtype=np.float64)
    if params.target_mode == FB_TARGET_R:
        return targets

    session_of: IndexArray = data.range_session_id()[signal_bars]
    first: FloatArray = first_target(series, params)[session_of]
    targets[:, 0] = first
    if params.target_mode == FB_TARGET_OPPOSITE_NEXT:
        targets[:, 1] = next_levels(data, params, signal_bars, first)
    else:
        targets[:, 1] = edges(series, params.direction)[1][session_of]

    return targets


def first_per_session(signal: BoolArray, session_id: IndexArray, cap: int) -> BoolArray:
    """Return ``signal`` keeping each session's first ``cap`` signals, or all of them at ``0``."""
    if cap == 0:
        return signal

    at: OffsetArray = np.flatnonzero(signal)
    sessions: IndexArray = session_id[at]
    starts: OffsetArray = np.flatnonzero(np.concatenate(([True], sessions[1:] != sessions[:-1])))
    counts: IntArray = np.diff(np.concatenate((starts, [at.size])))
    order_in_session: IntArray = np.arange(at.size) - np.repeat(starts, counts)
    kept: BoolArray = np.zeros(signal.size, dtype=np.bool_)
    kept[at[order_in_session < cap]] = True

    return kept


def recoveries(data: Dataset, params: FailedBreakParams, series: LevelSeries) -> tuple[BoolArray, FloatArray]:
    """Return the bars that signal, narrowed and capped, and each bar's sweep extreme.

    The cap comes last, so it counts the signals the filters admit: under a midday filter the first
    signal is the first of midday.
    """
    swept, _ = edges(series, params.direction)
    session_id: IndexArray = data.range_session_id()
    fired, extremes = scan_recoveries(
        data.low,
        data.high,
        data.close,
        data.bar_seconds(),
        series.armed,
        session_id,
        swept,
        params.direction,
        params.max_sweep_minutes * bracket.SECONDS_PER_MINUTE,
    )
    if params.target_mode != FB_TARGET_R:
        fired &= params.direction * (first_target(series, params)[session_id] - data.close) > 0.0

    narrowed: BoolArray = filters.apply_context_filters(
        fired, data, params, lambda: failedbreak_long_side(data, params)
    )

    return first_per_session(narrowed, session_id, params.max_signals_per_session), extremes


def failedbreak_signal(data: Dataset, params: FailedBreakParams) -> BoolArray:
    """Flag bars whose close schedules an entry for the next bar's open."""
    signal, _ = recoveries(data, params, level_series(data, params.level))

    return signal


def matched_sources(data: Dataset, real: BoolArray, drawn: BoolArray) -> tuple[OffsetArray, OffsetArray]:
    """Pair each drawn bar with a real signal at its minute of session, in time order within it.

    Returns both sides in the drawn bars' time order.
    """
    real_bars: OffsetArray = np.flatnonzero(real)
    drawn_bars: OffsetArray = np.flatnonzero(drawn)
    minutes: IntArray = data.minutes_of_session()
    real_order: OffsetArray = real_bars[np.argsort(minutes[real_bars], kind="stable")]
    drawn_order: OffsetArray = drawn_bars[np.argsort(minutes[drawn_bars], kind="stable")]
    if not np.array_equal(minutes[real_order], minutes[drawn_order]):
        msg: str = (
            "a drawn signal has to hold the real signal's count at every minute of session, or its "
            "bars have no real signals to take a stop and targets from; draw it with "
            "randomentry.matched_random_signal"
        )
        raise ValueError(msg)

    back_to_time: OffsetArray = np.argsort(drawn_order, kind="stable")

    return drawn_order[back_to_time], real_order[back_to_time]


def geometry_of(data: Dataset, params: FailedBreakParams, signal: BoolArray | None) -> Geometry:
    """Return the prices each signal reads, moved by each drawn bar's distance from its real signal."""
    series: LevelSeries = level_series(data, params.level)
    real, extremes = recoveries(data, params, series)
    submitted: OffsetArray
    sources: OffsetArray
    if signal is None or not (signal & ~real).any():
        submitted = sources = np.flatnonzero(real if signal is None else signal)
    else:
        submitted, sources = matched_sources(data, real, signal)

    shift: FloatArray = data.close[submitted] - data.close[sources]
    session_of: IndexArray = data.range_session_id()[sources]
    swept, _ = edges(series, params.direction)
    row_of_bar: IndexArray = np.full(len(data), NO_SIGNAL, dtype=np.int32)
    row_of_bar[submitted] = np.arange(submitted.size, dtype=np.int32)

    return Geometry(
        row_of_bar=row_of_bar,
        extreme=extremes[sources] + shift,
        level=swept[session_of] + shift,
        targets=signal_targets(data, params, series, sources) + shift[:, np.newaxis],
    )


@njit(cache=True)
def submitted_stop(
    extreme: float,
    rules: FailedBreakRules,
    costs: bracket.Costs,
    fills: bracket.FillRules,
) -> float:
    """Return the stop a signal submits: the cushion beyond its extreme, on the grid, off a round number."""
    stop = extreme - rules.direction * rules.stop_offset
    if fills.round_targets:
        stop = bracket.round_to_tick(stop, costs.tick_size)

    return bracket.avoid_round_number(
        stop,
        rules.round_number_points,
        rules.round_number_offset,
        costs.tick_size,
        rules.direction,
    )


@njit(cache=True)
def simulate_failedbreak(  # noqa: C901, PLR0912, PLR0915 - one branch per rule, in bar order
    bars: bracket.Bars,
    geometry: Geometry,
    sizing: bracket.Sizing,
    target_r: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: FailedBreakRules,
    out: FloatArray,
) -> int:
    """Run one combination over one dataset, writing one row per leg exit.

    A signal bar's close schedules a market entry for the next open, sized by that bar's ``sizing``
    row. A market exit is decided at a close and fills at the next open.

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = bars.close.size
    n_legs = sizing.quantities.shape[1]
    d = rules.direction
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit_reason = bracket.NO_MARKET_EXIT
    pending_bar = -1
    swept_level = 0.0

    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, False)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0, 0, 0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        np.zeros(n_legs, dtype=np.int64),
    )

    for i in range(n):
        # ---- exits ------------------------------------------------------------------
        if in_position and pending_exit_reason != bracket.NO_MARKET_EXIT:
            # Submitted at the close of bar i-1 and filled at this bar's first price, so the
            # excursion stays where it was.
            written = bracket.flatten_position(
                out,
                written,
                trade,
                legs,
                bracket.LegExit(i, bars.open_[i] - d * slippage, pending_exit_reason, False),
                excursion,
                costs,
            )
            if written < 0:
                return -1

            in_position = False
        elif in_position:
            excursion = bracket.extend_excursion(excursion, bars.high[i], bars.low[i], i)
            written, in_position = bracket.resolve_brackets(
                out,
                written,
                trade,
                stop,
                legs,
                excursion,
                bars,
                i,
                costs,
                fills,
            )
            if written < 0:
                return -1

        # ---- the entry order fills at this bar's open, unconditionally ---------------
        if pending_bar >= 0 and pending_bar == i - 1:
            # A force-flat bar is filled like any other; the session-close handler runs
            # after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            row = geometry.row_of_bar[pending_bar]
            fill = bars.open_[i] + d * slippage
            candidate_stop = submitted_stop(geometry.extreme[row], rules, costs, fills)
            candidate_risk = d * (fill - candidate_stop)
            # A stop at or through the price it protects is not a stop order --
            # ``docs/nt8-fidelity.md`` §M18.
            if candidate_risk >= min_risk:
                trade_id += 1
                trade = bracket.OpenTrade(
                    trade_id=trade_id,
                    entry_bar=i,
                    entry_price=fill,
                    initial_stop=candidate_stop,
                    risk=candidate_risk,
                    direction=d,
                    stop_entry=False,
                )
                stop = candidate_stop
                swept_level = geometry.level[row]
                excursion = bracket.start_excursion(bars.high[i], bars.low[i], i)
                bracket.size_legs(legs, sizing, pending_bar)
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    raw = (
                        fill + d * candidate_risk * target_r[leg] * rules.tp_multiplier
                        if rules.use_r_targets
                        else geometry.targets[row, leg]
                    )
                    if np.isnan(raw):
                        legs.target[leg] = np.nan
                    else:
                        legs.target[leg] = (
                            bracket.round_to_tick(raw, costs.tick_size) if fills.round_targets else raw
                        )

                written, in_position = bracket.resolve_brackets(
                    out,
                    written,
                    trade,
                    stop,
                    legs,
                    excursion,
                    bars,
                    i,
                    costs,
                    fills,
                )
                if written < 0:
                    return -1

            pending_bar = -1

        # ---- close of bar i: move the stop, then decide the next bar's orders --------
        pending_exit_reason = bracket.NO_MARKET_EXIT
        if in_position:
            breakeven = bracket.breakeven_level(rules.breakeven, trade, bars, i, costs, fills)
            stop = bracket.tightened_stop(stop, breakeven, d)
            timed = bracket.tightening_level(
                rules.stop_tightening, trade, trade.initial_stop, bars, i, costs, fills
            )
            stop = bracket.tightened_stop(stop, timed, d)
            pending_exit_reason = (
                trades.EXIT_SIGNAL
                if rules.exit_on_rebreak and d * (bars.close[i] - swept_level) < 0.0
                else bracket.market_exit_reason(
                    trade, bars, excursion, i, rules.max_hold_bars, rules.early_exit
                )
            )

        if in_position or i < rules.bars_required or geometry.row_of_bar[i] == NO_SIGNAL:
            continue

        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue

        pending_bar = i

    # Anything still open when the series runs out is liquidated at the last bar.
    if in_position:
        last = n - 1
        written = bracket.flatten_position(
            out,
            written,
            trade,
            legs,
            bracket.LegExit(last, bars.close[last] - d * slippage, trades.EXIT_END_OF_DATA, False),
            excursion,
            costs,
        )
        if written < 0:
            return -1

    return written


def failedbreak_long_side(data: Dataset, params: FailedBreakParams) -> BoolArray:
    """Return the bars one combination would enter long: every one or none, since the side is a parameter."""
    return np.full(len(data), params.direction == trades.LONG, dtype=np.bool_)


def failedbreak_legs(
    data: Dataset,
    params: FailedBreakParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm, and is either
    inside the real signal or matched to it minute by minute -- ``docs/nt8-fidelity.md``, "A drawn
    bar carries a real signal's geometry".
    """
    filters.check_price_basis(data, params.round_number_points)
    geometry: Geometry = geometry_of(data, params, signal)
    sizing: bracket.Sizing = filters.confluence_sizing(data, params, failedbreak_long_side(data, params))
    out: FloatArray = bracket.allocate_output(geometry.extreme.size, sizing.quantities.shape[1])

    count: int = simulate_failedbreak(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        geometry,
        sizing,
        np.asarray(params.target_levels, dtype=np.float64),
        bracket.Costs(
            tick_size=instrument.tick_size,
            point_value=instrument.point_value,
            commission_per_contract=params.commission_per_contract,
            slippage_ticks=params.slippage_ticks,
        ),
        bracket.FillRules(
            fill_limit_on_touch=params.fill_limit_on_touch,
            ambiguity_policy=params.ambiguity_policy,
            round_targets=params.round_targets,
        ),
        FailedBreakRules(
            direction=params.direction,
            exit_on_rebreak=params.exit_on_rebreak,
            stop_offset=params.stop_offset_ticks * instrument.tick_size,
            round_number_points=params.round_number_points,
            round_number_offset=params.round_number_offset_ticks * instrument.tick_size,
            use_r_targets=params.target_mode == FB_TARGET_R,
            tp_multiplier=params.tp_multiplier,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
            max_hold_bars=params.max_hold_bars,
            early_exit=filters.early_exit(data, params),
            breakeven=filters.breakeven(data, params),
            stop_tightening=filters.stop_tightening(data, params),
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_failedbreak(
    data: Dataset,
    params: FailedBreakParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = failedbreak_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
