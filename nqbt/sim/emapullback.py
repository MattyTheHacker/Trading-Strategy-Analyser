"""EmaPullback archetype: buy the first pullback into the trend the two averages define.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule is written
down rather than reconciled -- ``docs/nt8-fidelity.md`` §M34 names the NinjaScript each would
become. The design and the alternatives rejected: ``docs/findings/m34-ema-pullback-spec.md``.

The market entry reuses :func:`nqbt.sim.crossover.simulate_crossover` itself, not a fork of it:
the entry is the same market-on-next-open, the side comes from the same
:func:`~nqbt.sim.crossover.regime_direction`, and the stop is the shared loop's level mode
reading the slow average. The confirmation entry is a stop order resting beyond the signal bar,
so it is its own entry loop over the same bracket engine -- ``docs/nt8-fidelity.md`` §M39.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, crossover, filters
from nqbt.sim.types import STOP_MIN_TICKS, TOUCH_ANY, TOUCH_WICK

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import EmaPullbackParams
    from nqbt.trades import LegMatrix


def pullback_averages(data: Dataset, params: EmaPullbackParams) -> tuple[FloatArray, FloatArray]:
    """The fast and slow average values this combination reads.

    Read out of the shared grid, which is built with ``needs_ma_values`` for this archetype.
    """
    return (
        data.ma_values(params.fast_kind, params.fast_period),
        data.ma_values(params.slow_kind, params.slow_period),
    )


def extension_run(
    adverse: FloatArray,
    fast: FloatArray,
    slow: FloatArray,
    direction: float,
) -> IntArray:
    """Unbroken bars spent entirely beyond the fast average, as the *next* bar reads it.

    A bar that reaches the average ends the run, so the count a touch bar reads is the one the
    bar before it carried -- ``docs/nt8-fidelity.md`` §M34.
    """
    beyond: BoolArray = (direction * (adverse - fast) > 0.0) & (direction * (fast - slow) > 0.0)
    counts: IntArray = conditions.consecutive_true(beyond)
    behind: IntArray = np.zeros(counts.size, dtype=np.int64)
    behind[1:] = counts[:-1]

    return behind


def touch_shape(close: FloatArray, fast: FloatArray, direction: float, touch_mode: int) -> BoolArray:
    """Where the signal bar had to close, in whichever of the three touch modes is selected.

    A close exactly on the average is a close *through* it: one sign multiplier means the long
    and short arms have to be the same rule -- ``docs/nt8-fidelity.md`` §M34.
    """
    if touch_mode == TOUCH_ANY:
        return np.ones(close.size, dtype=np.bool_)

    if touch_mode == TOUCH_WICK:
        return np.asarray(direction * (close - fast) > 0.0)

    return np.asarray(direction * (close - fast) <= 0.0)


def side_signal(
    data: Dataset,
    fast: FloatArray,
    slow: FloatArray,
    params: EmaPullbackParams,
    direction: float,
) -> BoolArray:
    """One side's entry bars: an extension away from the fast average, then a bar back to it.

    ``require_turn`` adds the reaction: the signal bar's own body has to have turned back into
    the trend, which is :func:`nqbt.conditions.closed_towards`'s doji boundary.
    """
    adverse: FloatArray = data.low if direction == trades.LONG else data.high
    trending: BoolArray = np.asarray(direction * (fast - slow) > 0.0)
    touched: BoolArray = np.asarray(direction * (adverse - fast) <= 0.0)
    intact: BoolArray = np.asarray(direction * (data.close - slow) > 0.0)
    if params.require_slow_intact:
        intact &= direction * (adverse - slow) > 0.0

    if params.require_turn:
        intact &= conditions.closed_towards(data.open, data.close, direction)

    run: IntArray = extension_run(adverse, fast, slow, direction)

    return (
        trending
        & touched
        & intact
        & touch_shape(data.close, fast, direction, params.touch_mode)
        & (run >= params.min_bars_extended)
    )


def emapullback_signal(data: Dataset, params: EmaPullbackParams) -> BoolArray:
    """Bars whose close schedules an entry for the next bar's open."""
    fast, slow = pullback_averages(data, params)
    signal: BoolArray = np.zeros(len(data), dtype=np.bool_)
    if params.trade_long:
        signal |= side_signal(data, fast, slow, params, trades.LONG)

    if params.trade_short:
        signal |= side_signal(data, fast, slow, params, trades.SHORT)

    return filters.apply_context_filters(signal, data, params)


def trailed_level(
    data: Dataset,
    slow: FloatArray,
    params: EmaPullbackParams,
) -> tuple[FloatArray, float]:
    """The average the stop trails and its offset in ticks.

    The average is :data:`~nqbt.sim.crossover.NO_TRAIL` while the trail is off. On the slow
    average both are the initial stop's own, so an average that has not moved leaves the stop
    where it was placed -- ``docs/nt8-fidelity.md`` §M34.
    """
    if not params.trail_ma_stop:
        return crossover.NO_TRAIL, float(params.trail_offset_ticks)

    if params.trail_on_slow:
        return slow, float(params.stop_offset_ticks)

    return data.ma_values(params.trail_ma_kind, params.trail_ma_period), float(params.trail_offset_ticks)


class ConfirmationSeries(NamedTuple):
    """The per-bar series :func:`simulate_confirmation` reads beside the bars."""

    direction_at: FloatArray
    """Which side the averages are on -- :func:`nqbt.sim.crossover.regime_direction`."""

    stop_level: FloatArray
    """The slow average, which the protective stop is placed on."""

    trail_ma: FloatArray
    """The average the stop trails, and :data:`~nqbt.sim.crossover.NO_TRAIL` while it does not."""


class ConfirmationRules(NamedTuple):
    """The scalar rule set :func:`simulate_confirmation` reads, one field per parameter."""

    entry_offset_ticks: float
    stop_offset_ticks: float
    entry_order_lifetime_bars: int
    trail_ma_stop: bool
    trail_offset_ticks: float
    tp_multiplier: float
    bars_required: int
    exit_on_trend_flip: bool
    block_entry_at_session_close: bool
    max_hold_bars: int


@njit(cache=True)
def confirmation_bracket(
    bars: bracket.Bars,
    signal_bar: int,
    series: ConfirmationSeries,
    rules: ConfirmationRules,
    tick_size: float,
) -> tuple[float, float, float, float]:
    """One signal bar's order arithmetic: side, trigger, initial stop, planned risk.

    The trigger sits ``entry_offset_ticks`` beyond the signal bar's favourable extreme and the
    stop ``stop_offset_ticks`` beyond the slow average at that bar, so the whole bracket is known
    when the order is submitted and risk is measured from the trigger rather than the fill.
    """
    direction = series.direction_at[signal_bar]
    _, favourable = bracket.sided(bars.low[signal_bar], bars.high[signal_bar], direction)
    trigger = favourable + direction * rules.entry_offset_ticks * tick_size
    stop = series.stop_level[signal_bar] - direction * rules.stop_offset_ticks * tick_size

    return direction, trigger, stop, direction * (trigger - stop)


@njit(cache=True)
def simulate_confirmation(  # noqa: C901, PLR0912, PLR0915 - one branch per rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    series: ConfirmationSeries,
    leg_quantities: IntArray,
    target_r: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: ConfirmationRules,
    out: FloatArray,
) -> int:
    """Run the confirmation entry over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close submits a stop order beyond that bar's extreme, live for
    the next ``entry_order_lifetime_bars`` bars. The exits are the market entry's: the stop,
    the targets, the trail, the trend-flip exit and the maximum hold time.

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = bars.close.size
    n_legs = leg_quantities.size
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size
    trail_offset = rules.trail_offset_ticks * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit = False
    pending_exit_reason = trades.EXIT_SIGNAL
    pending_until = -1  # the last bar the resting order is live on; -1 while none rests
    pending_direction = 0.0
    pending_trigger = 0.0
    pending_stop = 0.0

    d = 0.0
    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, False)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        leg_quantities,
    )

    for i in range(n):
        # ---- exits ------------------------------------------------------------------
        if in_position and pending_exit:
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
            excursion = bracket.extend_excursion(excursion, bars.high[i], bars.low[i])
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

        # ---- the resting entry order, tested against this bar ------------------------
        elif i <= pending_until:
            # A force-flat bar is tested for a fill like any other; the session-close handler
            # runs after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            filled, fill = bracket.stop_entry_fill(bars, i, pending_trigger, slippage, pending_direction)
            if filled:
                d = pending_direction
                trade_id += 1
                risk = d * (pending_trigger - pending_stop)
                trade = bracket.OpenTrade(
                    trade_id=trade_id,
                    entry_bar=i,
                    entry_price=fill,
                    initial_stop=pending_stop,
                    risk=risk,
                    direction=d,
                    # Entered intrabar: the position did not exist at this bar's open.
                    filled_at_open=False,
                )
                stop = pending_stop
                excursion = bracket.Excursion(bars.high[i], bars.low[i])
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    if np.isnan(target_r[leg]):
                        legs.target[leg] = np.nan
                    else:
                        raw = pending_trigger + d * risk * target_r[leg] * rules.tp_multiplier
                        legs.target[leg] = (
                            bracket.round_to_tick(raw, costs.tick_size) if fills.round_targets else raw
                        )

                # The entry bar can reach the stop as well, and resolves like any other.
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

            # A fill ends the order, and so does the session-close handler.
            if filled or bars.force_flat[i]:
                pending_until = -1

        pending_exit = False

        # ---- close of bar i: trail the stop, then decide the next bar's orders --------
        if in_position and rules.trail_ma_stop:
            stop = bracket.tightened_stop(stop, series.trail_ma[i] - d * trail_offset, d)

        if in_position and rules.exit_on_trend_flip and series.direction_at[i] != d:
            pending_exit = True
            pending_exit_reason = trades.EXIT_SIGNAL

        if in_position and not pending_exit and bracket.hold_expired(trade.entry_bar, i, rules.max_hold_bars):
            pending_exit = True
            pending_exit_reason = trades.EXIT_TIME_LIMIT

        # Flat at this close, not flat by the next open: a stop entry submitted beside a pending
        # exit is an entry against an open position -- ``docs/nt8-fidelity.md`` §M39.
        if in_position or i < rules.bars_required or not signal[i]:
            continue

        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue

        direction, trigger, candidate_stop, candidate_risk = confirmation_bracket(
            bars,
            i,
            series,
            rules,
            costs.tick_size,
        )
        # NT8 ignores an entry on the other side of an order still working on this bar.
        if i <= pending_until and direction != pending_direction:
            continue

        if candidate_risk < min_risk or direction * trigger <= direction * bars.close[i]:
            continue

        pending_until = i + rules.entry_order_lifetime_bars
        pending_direction = direction
        pending_trigger = trigger
        pending_stop = candidate_stop

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


def confirmation_rules(params: EmaPullbackParams, trail_offset_ticks: float) -> ConfirmationRules:
    """The confirmation loop's rule set for one combination."""
    return ConfirmationRules(
        entry_offset_ticks=float(params.entry_offset_ticks),
        stop_offset_ticks=float(params.stop_offset_ticks),
        entry_order_lifetime_bars=params.entry_order_lifetime_bars,
        trail_ma_stop=params.trail_ma_stop,
        trail_offset_ticks=trail_offset_ticks,
        tp_multiplier=params.tp_multiplier,
        bars_required=params.bars_required_to_trade,
        exit_on_trend_flip=params.exit_on_trend_flip,
        block_entry_at_session_close=params.block_entry_at_session_close,
        max_hold_bars=params.max_hold_bars,
    )


def market_rules(params: EmaPullbackParams, trail_offset_ticks: float) -> crossover.CrossoverRules:
    """The shared crossover loop's rule set for one combination, in its level-stop mode."""
    return crossover.CrossoverRules(
        use_level_stop=True,
        # The three fields the other two stop modes read, and this archetype exposes neither.
        use_atr_stop=False,
        atr_stop_multiple=0.0,
        min_bracket_points=0.0,
        swing_lookback=1,
        stop_offset_ticks=float(params.stop_offset_ticks),
        trail_ma_stop=params.trail_ma_stop,
        trail_offset_ticks=trail_offset_ticks,
        # No round-number avoidance: an average is a statistic rather than a level the
        # market traded at -- ``docs/nt8-fidelity.md`` §M34.
        round_number_points=0.0,
        round_number_offset_ticks=0.0,
        tp_multiplier=params.tp_multiplier,
        bars_required=params.bars_required_to_trade,
        exit_on_opposite_cross=params.exit_on_trend_flip,
        block_entry_at_session_close=params.block_entry_at_session_close,
        max_hold_bars=params.max_hold_bars,
    )


def emapullback_legs(
    data: Dataset,
    params: EmaPullbackParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the side
    and the stop level are *not* overridden, so a drawn bar is taken on whichever side the
    averages were on and stopped at the slow one. Under the confirmation entry a drawn bar
    submits the same stop order a signal bar would.
    """
    fast, slow = pullback_averages(data, params)
    direction_at: FloatArray = crossover.regime_direction(fast, slow)
    signal = emapullback_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    targets: FloatArray = np.asarray(params.target_r_multiples, dtype=np.float64)
    trail, trail_offset_ticks = trailed_level(data, slow, params)
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)
    bars = bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat)
    costs = bracket.Costs(
        tick_size=instrument.tick_size,
        point_value=instrument.point_value,
        commission_per_contract=params.commission_per_contract,
        slippage_ticks=params.slippage_ticks,
    )
    fills = bracket.FillRules(
        fill_limit_on_touch=params.fill_limit_on_touch,
        ambiguity_policy=params.ambiguity_policy,
        round_targets=params.round_targets,
    )

    count: int
    if params.confirm_entry:
        count = simulate_confirmation(
            bars,
            signal,
            ConfirmationSeries(direction_at, slow, trail),
            quantities,
            targets,
            costs,
            fills,
            confirmation_rules(params, trail_offset_ticks),
            out,
        )
    else:
        count = crossover.simulate_crossover(
            bars,
            signal,
            direction_at,
            crossover.CrossoverSeries(crossover.NO_ATR, trail, slow),
            quantities,
            targets,
            costs,
            fills,
            market_rules(params, trail_offset_ticks),
            out,
        )

    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_emapullback(
    data: Dataset,
    params: EmaPullbackParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = emapullback_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
