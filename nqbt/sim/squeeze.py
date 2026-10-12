"""SqueezeBreakout archetype: rest a stop beyond a compressed window's extreme, one side at a time.

``TIER1_ONLY``; its rules and the NinjaScript each would become: ``docs/nt8-fidelity.md``
§M19.2. The design: ``docs/findings/m19-2-squeeze-breakout-spec.md``.

OpeningRange's breakout with its level taken from a rolling window, run through
:func:`nqbt.sim.openingrange.simulate_openingrange` with **one level row per bar**. Only the
signal and the levels are this module's.

The latched squeeze trades the window frozen when the squeeze ends instead, and hands the loop
**one row per latch**: ``docs/nt8-fidelity.md``, "The latched squeeze".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import compression, conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters, openingrange
from nqbt.sim.types import ORB_ENTRY_BREAKOUT, ORB_STOP_ATR

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IndexArray, OffsetArray
    from nqbt.context import Dataset
    from nqbt.sim.types import SqueezeBreakoutParams
    from nqbt.trades import LegMatrix

NO_UPPER_CUT = 1.0
"""The expanded threshold handed to the compression gate: the squeeze reads the lower cut alone."""

UNCAPPED = 0
"""The shared loop's per-session entry cap, switched off: a level row here is a bar, not a session."""

ONE_PER_LATCH = 1
"""The shared loop's per-session entry cap under a latch, whose bars share one row: a fill ends it."""


class Latch(NamedTuple):
    """The bars a latched order is submitted at, and the level row each bar reads."""

    submits: BoolArray
    row_of_bar: IndexArray
    """The release bar for a bar inside a latch, and the bar itself everywhere else."""


@njit(cache=True)
def scan_latches(
    squeezed: BoolArray,
    window_high: FloatArray,
    window_low: FloatArray,
    close: FloatArray,
    force_flat: BoolArray,
    latch_bars: int,
    direction: float,
) -> tuple[BoolArray, IndexArray]:
    """Return, per bar, whether a latched order is submitted at its close, and the row it reads.

    A latch opens on the first bar the squeeze no longer holds, frozen at the bar before, and
    ends after ``latch_bars`` closes, when the squeeze holds again, on a force-flat bar, or at a
    close strictly beyond the frozen window's other side.
    """
    n = squeezed.size
    submits = np.zeros(n, dtype=np.bool_)
    row_of_bar = np.arange(n, dtype=np.int32)
    release = -1
    left = 0

    for i in range(n):
        if squeezed[i]:
            left = 0
            continue

        if i > 0 and squeezed[i - 1]:
            release = i
            left = latch_bars

        if left == 0:
            continue

        other_side, _ = bracket.sided(window_low[release - 1], window_high[release - 1], direction)
        if force_flat[i] or direction * close[i] < direction * other_side:
            left = 0
            continue

        submits[i] = True
        row_of_bar[i] = release
        left -= 1

    return submits, row_of_bar


def squeezed_bars(data: Dataset, params: SqueezeBreakoutParams) -> BoolArray:
    """Flag bars whose window has been squeezed for at least ``min_squeeze_bars``, before any filter.

    The squeeze is :data:`nqbt.compression.Compression.COMPRESSED` cut at ``squeeze_below``, so
    it is the compression filter's own rule rather than a second copy of it.
    """
    squeezed: BoolArray = data.compression_gate(
        params.squeeze_key,
        compression.Compression.COMPRESSED.bit,
        params.squeeze_below,
        NO_UPPER_CUT,
    ).copy()
    if params.min_squeeze_bars > 1:
        squeezed = conditions.consecutive_true(squeezed) >= params.min_squeeze_bars

    return squeezed


def latch_of(data: Dataset, params: SqueezeBreakoutParams) -> Latch:
    """Return the latches one combination opens: :func:`scan_latches` over its squeeze and window."""
    submits, row_of_bar = scan_latches(
        squeezed_bars(data, params),
        data.window_high(params.squeeze_period),
        data.window_low(params.squeeze_period),
        data.close,
        data.force_flat,
        params.latch_bars,
        params.direction,
    )

    return Latch(submits, row_of_bar)


def squeeze_signal(data: Dataset, params: SqueezeBreakoutParams, latch: Latch | None = None) -> BoolArray:
    """Flag bars that may submit an entry order: squeezed ones, or under a latch the latched ones.

    ``latch`` is :func:`latch_of`'s, where the caller has it already; it is read, never narrowed.
    """
    entries: BoolArray
    if params.latch_bars:
        entries = (latch if latch is not None else latch_of(data, params)).submits.copy()
    else:
        entries = squeezed_bars(data, params)

    return filters.apply_context_filters(entries, data, params, lambda: squeeze_long_side(data, params))


def frozen_at_release(window: FloatArray, latch: Latch) -> FloatArray:
    """Return ``window`` with each latch's own row holding the window at the bar before its release."""
    releases: OffsetArray = np.flatnonzero(latch.submits & (latch.row_of_bar == np.arange(window.size)))
    frozen: FloatArray = window.copy()
    frozen[releases] = window[releases - 1]

    return frozen


def squeeze_levels(
    data: Dataset, params: SqueezeBreakoutParams, latch: Latch | None = None
) -> openingrange.RangeSeries:
    """Return the window this combination trades, as one level row per bar, or per latch under one.

    A bar is armed wherever the row it reads is complete, which outside a latch is every bar past
    the first ``squeeze_period - 1`` whether or not it is squeezed -- the random-entry arm draws
    bars the signal did not choose, and each still has a level to rest at. ``latch`` is
    :func:`latch_of`'s, where the caller has it already.
    """
    high: FloatArray = data.window_high(params.squeeze_period)
    low: FloatArray = data.window_low(params.squeeze_period)
    n: int = len(data)
    row_of_bar: IndexArray = np.arange(n, dtype=np.int32)
    if params.latch_bars:
        latch = latch if latch is not None else latch_of(data, params)
        high, low, row_of_bar = (
            frozen_at_release(high, latch),
            frozen_at_release(low, latch),
            latch.row_of_bar,
        )

    return openingrange.RangeSeries(
        armed=(np.isfinite(high) & np.isfinite(low))[row_of_bar],
        session_id=row_of_bar,
        high=high,
        low=low,
        scale=np.ones(n, dtype=np.float64),
        atr=data.atr_values(params.atr_period) if params.stop_mode == ORB_STOP_ATR else openingrange.NO_ATR,
    )


def entry_bound(data: Dataset, levels: openingrange.RangeSeries, signal: BoolArray, direction: float) -> int:
    """Return how many entries this combination can possibly fill -- what the output is sized from.

    A fill needs an armed signal bar followed by a bar reaching that bar's level, so those pairs
    bound it. The signal's own count is far looser, because a squeeze holds for many bars and
    breaks on few of them.
    """
    long: bool = direction > 0.0
    level: FloatArray = (levels.high if long else levels.low)[levels.session_id[:-1]]
    favourable: FloatArray = (data.high if long else data.low)[1:]
    reached: BoolArray = (direction * favourable >= direction * level) | (
        direction * data.open[1:] >= direction * level
    )

    return int(np.count_nonzero(signal[:-1] & levels.armed[:-1] & reached))


def squeeze_long_side(data: Dataset, params: SqueezeBreakoutParams) -> BoolArray:
    """Return the bars one combination would enter long: every one or none, since the side is a parameter."""
    return np.full(len(data), params.direction == trades.LONG, dtype=np.bool_)


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
    latch: Latch | None = latch_of(data, params) if params.latch_bars else None
    signal = squeeze_signal(data, params, latch) if signal is None else signal
    levels: openingrange.RangeSeries = squeeze_levels(data, params, latch)
    sizing: bracket.Sizing = filters.confluence_sizing(data, params, squeeze_long_side(data, params))
    targets: FloatArray = np.asarray(params.target_levels, dtype=np.float64)
    out: FloatArray = bracket.allocate_output(
        entry_bound(data, levels, signal, params.direction),
        sizing.quantities.shape[1],
    )

    count: int = openingrange.simulate_openingrange(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        levels,
        sizing,
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
            max_entries_per_session=ONE_PER_LATCH if params.latch_bars else UNCAPPED,
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
