"""SqueezeBreakout archetype: rest a stop beyond a compressed window's extreme, one side at a time.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule below is
written down rather than reconciled -- ``docs/nt8-fidelity.md`` §M19.2 names the NinjaScript each
would become, and ``docs/findings/m19-2-squeeze-breakout-spec.md`` carries the design.

The entry is OpeningRange's breakout with its level taken from a rolling window rather than from
a session's opening range, so it runs through
:func:`nqbt.sim.openingrange.simulate_openingrange` with **one level row per bar**. Only the
signal and the levels are this module's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nqbt import compression, conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters, openingrange
from nqbt.sim.types import ORB_ENTRY_BREAKOUT, ORB_STOP_ATR

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IndexArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import SqueezeBreakoutParams
    from nqbt.trades import LegMatrix

NO_UPPER_CUT = 1.0
"""The expanded threshold handed to the compression gate: the squeeze reads the lower cut alone."""

UNCAPPED = 0
"""The shared loop's per-session entry cap, switched off: a level row here is a bar, not a session."""


def squeeze_signal(data: Dataset, params: SqueezeBreakoutParams) -> BoolArray:
    """Bars that may submit an entry order: those whose window has been squeezed for long enough.

    The squeeze is :data:`nqbt.compression.Compression.COMPRESSED` cut at ``squeeze_below``, so
    it is the compression filter's own rule rather than a second copy of it.
    """
    squeezed: BoolArray = data.compression_gate(
        params.squeeze_key,
        compression.Compression.COMPRESSED.bit,
        params.squeeze_below,
        NO_UPPER_CUT,
    )
    if params.min_squeeze_bars > 1:
        squeezed = conditions.consecutive_true(squeezed) >= params.min_squeeze_bars

    return filters.apply_context_filters(squeezed, data, params)


def squeeze_levels(data: Dataset, params: SqueezeBreakoutParams) -> openingrange.RangeSeries:
    """The window this combination trades, as one level row per bar.

    A bar is armed wherever its window is complete, which is every bar past the first
    ``squeeze_period - 1`` whether or not it is squeezed -- the random-entry arm draws bars the
    signal did not choose, and each still has a level to rest at.
    """
    high: FloatArray = data.window_high(params.squeeze_period)
    low: FloatArray = data.window_low(params.squeeze_period)
    n: int = len(data)
    row_of_bar: IndexArray = np.arange(n, dtype=np.int32)

    return openingrange.RangeSeries(
        armed=np.isfinite(high) & np.isfinite(low),
        session_id=row_of_bar,
        high=high,
        low=low,
        scale=np.ones(n, dtype=np.float64),
        atr=data.atr_values(params.atr_period) if params.stop_mode == ORB_STOP_ATR else openingrange.NO_ATR,
    )


def entry_bound(data: Dataset, levels: openingrange.RangeSeries, signal: BoolArray, direction: float) -> int:
    """How many entries this combination can possibly fill -- what the output is sized from.

    A fill needs an armed signal bar followed by a bar reaching that bar's level, so those pairs
    bound it. The signal's own count is far looser, because a squeeze holds for many bars and
    breaks on few of them.
    """
    long: bool = direction > 0.0
    level: FloatArray = (levels.high if long else levels.low)[:-1]
    favourable: FloatArray = (data.high if long else data.low)[1:]
    reached: BoolArray = (direction * favourable >= direction * level) | (
        direction * data.open[1:] >= direction * level
    )

    return int(np.count_nonzero(signal[:-1] & levels.armed[:-1] & reached))


def squeeze_legs(
    data: Dataset,
    params: SqueezeBreakoutParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the
    direction is a parameter rather than a series, so a drawn bar is taken on the same side.
    """
    signal = squeeze_signal(data, params) if signal is None else signal
    levels: openingrange.RangeSeries = squeeze_levels(data, params)
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    targets: FloatArray = np.asarray(params.target_levels, dtype=np.float64)
    out: FloatArray = bracket.allocate_output(
        entry_bound(data, levels, signal, params.direction),
        quantities.size,
    )

    count: int = openingrange.simulate_openingrange(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        levels,
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
        openingrange.OpeningRangeRules(
            direction=params.direction,
            entry_mode=ORB_ENTRY_BREAKOUT,
            entry_offset=params.entry_offset_ticks * instrument.tick_size,
            break_confirm=0.0,
            retest_offset=0.0,
            stop_mode=params.stop_mode,
            stop_offset=params.stop_offset_ticks * instrument.tick_size,
            stop_range_fraction=params.stop_range_fraction,
            atr_stop_multiple=params.atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(params.min_bracket_dollars),
            target_mode=params.target_mode,
            tp_multiplier=params.tp_multiplier,
            scale_target=False,
            scale_stop=False,
            max_entries_per_session=UNCAPPED,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
            max_hold_bars=params.max_hold_bars,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; entry_bound's fill bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_squeeze(
    data: Dataset,
    params: SqueezeBreakoutParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = squeeze_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
