"""EmaPullback archetype: buy the first pullback into the trend the two averages define.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule is written
down rather than reconciled -- ``docs/nt8-fidelity.md`` §M34 names the NinjaScript each would
become. The design and the alternatives rejected: ``docs/findings/m34-ema-pullback-spec.md``.

Reuses :func:`nqbt.sim.crossover.simulate_crossover` itself, not a fork of it: the entry is the
same market-on-next-open, the side comes from the same :func:`~nqbt.sim.crossover.regime_direction`,
and the stop is the shared loop's level mode reading the slow average.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nqbt import conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, crossover, filters
from nqbt.sim.types import TOUCH_ANY, TOUCH_WICK

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
    averages were on and stopped at the slow one.
    """
    fast, slow = pullback_averages(data, params)
    direction_at: FloatArray = crossover.regime_direction(fast, slow)
    signal = emapullback_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    targets: FloatArray = np.asarray(params.target_r_multiples, dtype=np.float64)
    trail: FloatArray = (
        data.ma_values(params.trail_ma_kind, params.trail_ma_period)
        if params.trail_ma_stop
        else crossover.NO_TRAIL
    )
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = crossover.simulate_crossover(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        direction_at,
        crossover.CrossoverSeries(crossover.NO_ATR, trail, slow),
        quantities,
        targets,
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
        crossover.CrossoverRules(
            use_level_stop=True,
            # The three fields the other two stop modes read, and this archetype exposes neither.
            use_atr_stop=False,
            atr_stop_multiple=0.0,
            min_bracket_points=0.0,
            swing_lookback=1,
            stop_offset_ticks=float(params.stop_offset_ticks),
            trail_ma_stop=params.trail_ma_stop,
            trail_offset_ticks=float(params.trail_offset_ticks),
            # No round-number avoidance: an average is a statistic rather than a level the
            # market traded at -- ``docs/nt8-fidelity.md`` §M34.
            round_number_points=0.0,
            round_number_offset_ticks=0.0,
            tp_multiplier=params.tp_multiplier,
            bars_required=params.bars_required_to_trade,
            exit_on_opposite_cross=params.exit_on_trend_flip,
            block_entry_at_session_close=params.block_entry_at_session_close,
            max_hold_bars=params.max_hold_bars,
        ),
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
