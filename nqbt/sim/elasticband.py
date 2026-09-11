"""ElasticBand archetype: fade an extension, target the middle. The first mean reversion here.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule below is
written down rather than reconciled -- ``docs/nt8-fidelity.md`` §M26 names the NinjaScript each
would become, and ``docs/roadmap.md`` §M26 carries the design and the three exit schemes.

The entry is EmaCrossover's mechanism -- market on the next open, no trigger price -- and the
geometry is the inverted one: **the target is a level rather than an R multiple**, so
``r_multiple`` here compares with nothing else in the registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    BAND_VWAP,
    SHAPE_ANY,
    SHAPE_RECLAIM,
    SHAPE_REJECTION,
    SHAPE_REVERSAL,
    STOP_ATR,
    STOP_BAND,
    STOP_EXCURSION,
    STOP_MIN_TICKS,
    STOP_SWING,
    TARGET_STRETCH,
    TRIGGER_RECOVERY,
)

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import ElasticBandParams
    from nqbt.trades import LegMatrix

NO_ATR = np.zeros(0, dtype=np.float64)
"""Stand-in for the ATR array outside :data:`STOP_ATR`, where the loop never indexes it.

Numba needs an array of the right dtype whether or not the branch reading it runs.
"""


class BandSeries(NamedTuple):
    """The derived per-bar series this archetype reads, beyond the OHLC in :class:`bracket.Bars`.

    Held together so one bar's band cannot be read against another's, and so the jitted loop
    takes a blob rather than a positional list -- ``docs/roadmap.md`` §M20c.
    """

    basis: FloatArray
    stddev: FloatArray
    excursion_extreme: FloatArray
    atr: FloatArray
    """Empty outside :data:`STOP_ATR`, where the loop never indexes it."""


class ElasticBandRules(NamedTuple):
    """The scalar rule set :func:`simulate_elasticband` reads, one field per parameter."""

    stop_mode: int
    atr_stop_multiple: float
    min_bracket_points: float
    stop_offset: float
    catastrophe_distance: float
    swing_lookback: int
    entry_std: float
    band_stop_std: float
    target_mode: int
    tp_multiplier: float
    bars_required: int
    exit_on_invalidation: bool
    max_hold_bars: int
    block_entry_at_session_close: bool


@njit(cache=True)
def run_extreme(low: FloatArray, high: FloatArray, beyond: BoolArray, direction_at: FloatArray) -> FloatArray:
    """The adverse extreme of the unbroken run of bars outside the band ending at each bar.

    The lowest low of a run below the band, the highest high of a run above it, and ``nan``
    on a bar that is not outside at all. One pass, reset whenever the run breaks or changes
    side -- this is the reference :data:`STOP_EXCURSION` hangs its stop off.
    """
    n = low.size
    out = np.empty(n, dtype=np.float64)
    extreme = np.nan
    side = 0.0
    for i in range(n):
        if not beyond[i]:
            extreme = np.nan
            side = 0.0
            out[i] = np.nan
            continue

        d = direction_at[i]
        if side != d:
            # A new run, or the same run reading the other side of the basis.
            extreme = low[i] if d > 0.0 else high[i]
            side = d
        elif d > 0.0:
            extreme = min(extreme, low[i])
        else:
            extreme = max(extreme, high[i])

        out[i] = extreme

    return out


@njit(cache=True)
def _protective_stop(
    bars: bracket.Bars,
    band: BandSeries,
    signal_bar: int,
    fill: float,
    direction: float,
    rules: ElasticBandRules,
) -> float:
    """Where the protective stop goes, in whichever of the five schemes is selected.

    All five read the **signal** bar and the bars before it, never the bar the fill happens
    on. Only :data:`STOP_ATR` is floored, because only it is a distance rather than a level --
    ``docs/nt8-fidelity.md`` §M26.
    """
    if rules.stop_mode == STOP_SWING:
        return bracket.swing_stop(bars, signal_bar, rules.swing_lookback, rules.stop_offset, direction)

    if rules.stop_mode == STOP_ATR:
        distance = bracket.atr_bracket_distance(
            float(band.atr[signal_bar]),
            rules.atr_stop_multiple,
            rules.min_bracket_points,
        )
        return fill - direction * distance

    if rules.stop_mode == STOP_EXCURSION:
        return float(band.excursion_extreme[signal_bar]) - direction * rules.stop_offset

    if rules.stop_mode == STOP_BAND:
        # A stretch level like the targets, signed away from the basis instead of towards it.
        level = rules.entry_std + rules.band_stop_std

        return float(band.basis[signal_bar]) - direction * level * float(band.stddev[signal_bar])

    return fill - direction * rules.catastrophe_distance


@njit(cache=True)
def _leg_target(
    level: float,
    basis: float,
    stddev: float,
    fill: float,
    risk: float,
    direction: float,
    rules: ElasticBandRules,
) -> float:
    """One leg's target price, in whichever coordinate its mode expresses it.

    A stretch level is a position on the band, signed towards the target, so ``0.0`` is the
    basis for both sides. An R multiple is a distance from the fill, **capped at the basis** --
    a target past the mean is not a mean-reversion target.
    """
    if rules.target_mode == TARGET_STRETCH:
        return basis + direction * level * stddev

    raw = fill + direction * risk * level * rules.tp_multiplier
    if direction * (raw - basis) > 0.0:
        return basis

    return raw


@njit(cache=True)
def simulate_elasticband(  # noqa: C901, PLR0912, PLR0915 - one branch per rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    direction_at: FloatArray,
    band: BandSeries,
    leg_quantities: IntArray,
    target_levels: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: ElasticBandRules,
    out: FloatArray,
) -> int:
    """Run the elastic band over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close schedules an entry for the next bar's open and
    ``direction_at`` gives the side to fade on every bar -- ``LONG`` below the basis. The two
    are separate so the random-entry arm can substitute only the first.

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = bars.close.size
    n_legs = leg_quantities.size
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit = False
    pending_exit_reason = trades.EXIT_SIGNAL
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, True)
    stop = 0.0
    entry_extreme = 0.0
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

        pending_exit = False

        # ---- the entry order fills at this bar's open, unconditionally ---------------
        if not in_position and pending_bar >= 0 and pending_bar == i - 1:
            # A force-flat bar is filled like any other; the session-close handler runs
            # after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            d = pending_direction
            fill = bars.open_[i] + d * slippage
            candidate_stop = _protective_stop(bars, band, pending_bar, fill, d, rules)
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
                    filled_at_open=True,
                )
                stop = candidate_stop
                entry_extreme = band.excursion_extreme[pending_bar]
                excursion = bracket.Excursion(bars.high[i], bars.low[i])
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    if np.isnan(target_levels[leg]):
                        legs.target[leg] = np.nan
                    else:
                        # Both the basis and the dispersion are the signal bar's.
                        raw = _leg_target(
                            target_levels[leg],
                            band.basis[pending_bar],
                            band.stddev[pending_bar],
                            fill,
                            candidate_risk,
                            d,
                            rules,
                        )
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

        # ---- close of bar i: schedule the next bar's orders --------------------------
        if in_position and rules.exit_on_invalidation and d * (bars.close[i] - entry_extreme) < 0.0:
            # The close went further than the excursion the trade faded: the range broke and
            # held, which is the mean-reversion definition of being wrong.
            pending_exit = True
            pending_exit_reason = trades.EXIT_SIGNAL

        # After the invalidation, which would have closed the position on this bar anyway.
        if in_position and not pending_exit and bracket.hold_expired(trade.entry_bar, i, rules.max_hold_bars):
            pending_exit = True
            pending_exit_reason = trades.EXIT_TIME_LIMIT

        if (
            i >= rules.bars_required
            and signal[i]
            and not in_position
            and not (rules.block_entry_at_session_close and bars.force_flat[i])
        ):
            pending_bar = i
            pending_direction = direction_at[i]

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


def lagged(series: FloatArray, lag: int) -> FloatArray:
    """``series`` shifted ``lag`` bars later, with ``nan`` where nothing has been read yet.

    ``lag=0`` is the series itself. The head is ``nan`` rather than a repeated first value so
    that a bar with no band cannot signal -- every comparison against it is false.
    """
    if lag == 0:
        return series

    out: FloatArray = np.full(series.size, np.nan, dtype=np.float64)
    if lag < series.size:
        out[lag:] = series[:-lag]

    return out


def band_series(data: Dataset, params: ElasticBandParams) -> tuple[FloatArray, FloatArray, FloatArray]:
    """The basis, dispersion and extension this combination reads, at its band lag.

    One coordinate system, two windows: a rolling ``band_period`` under :data:`BAND_BOLLINGER`
    and the session so far under :data:`BAND_VWAP`.
    """
    lag: int = params.band_lag
    if params.band_source == BAND_VWAP:
        return (
            lagged(data.vwap_band_basis(), lag),
            lagged(data.vwap_band_stddev(), lag),
            lagged(data.vwap_band_stretch(), lag),
        )

    period: int = params.band_period

    return (
        lagged(data.band_basis(period), lag),
        lagged(data.band_stddev(period), lag),
        lagged(data.band_stretch(period), lag),
    )


def vwap_band_warmed_up(data: Dataset, params: ElasticBandParams) -> BoolArray:
    """Bars whose VWAP band has enough of its own session behind it to be a band.

    The lag is added to the requirement rather than applied to the counter, which also keeps a
    lagged read inside the session it was anchored in.
    """
    return np.asarray(data.vwap_band_age() >= params.vwap_min_session_bars + params.band_lag)


def fade_direction(stretch: FloatArray) -> FloatArray:
    """Which side a bar would be faded on: ``LONG`` below the basis, ``SHORT`` at or above it.

    Defined on **every** bar rather than only on signal bars, so the random-entry arm can drop
    a signal anywhere and still know which way the trade would have been taken.
    """
    return np.where(stretch < 0.0, trades.LONG, trades.SHORT).astype(np.float64)


def beyond_band(stretch: FloatArray, params: ElasticBandParams) -> BoolArray:
    """Bars whose close sits at least ``entry_std`` standard deviations from the basis."""
    return np.abs(stretch) >= params.entry_std


def returned_inside(stretch: FloatArray, params: ElasticBandParams) -> BoolArray:
    """Bars whose close came back inside the band and stayed on the side it stretched to.

    ``recovery_fraction`` of ``1.0`` is the band edge itself and anything less is a depth. A
    close exactly on the basis passes on neither side, which is the symmetry one sign
    multiplier asks for -- ``docs/nt8-fidelity.md`` §M26.6.
    """
    distance: FloatArray = np.abs(stretch)
    depth: float = params.recovery_fraction * params.entry_std

    return np.asarray((distance < params.entry_std) & (distance <= depth) & (stretch != 0.0))


def outside_run_length(outside: BoolArray, *, ends_before: bool) -> IntArray:
    """The unbroken run of bars outside the band that each bar's trigger reads.

    ``ends_before`` is :data:`TRIGGER_RECOVERY`'s: the run ended at the bar before the signal,
    so the count the signal bar reads is the one that bar carried -- ``docs/roadmap.md`` §M26.6.
    """
    counts: IntArray = conditions.consecutive_true(outside)
    if not ends_before:
        return counts

    behind: IntArray = np.zeros(counts.size, dtype=np.int64)
    behind[1:] = counts[:-1]

    return behind


def closed_towards_basis(open_: FloatArray, close: FloatArray, direction: FloatArray) -> BoolArray:
    """Bars whose body runs the way the fade would trade -- green below the basis, red above.

    A doji runs neither way and passes on neither side, which is the symmetric boundary this
    archetype's one sign multiplier asks for -- ``docs/nt8-fidelity.md`` §M26.5.
    """
    return np.asarray(direction * (close - open_) > 0.0)


def swept_and_reclaimed(data: Dataset, direction: FloatArray) -> BoolArray:
    """Bars that took out the previous bar's extreme against the fade and closed back past it.

    The sweep-and-recovery shape rather than a body that happened to turn, which is what makes
    it a failed break of the level -- ``docs/roadmap.md`` §M26.5. The extreme is
    :class:`nqbt.conditions.BarGeometry`'s, already built for every dataset.
    """
    swept: BoolArray = np.where(
        direction > 0.0,
        data.geometry.made_new_low,
        data.geometry.made_new_high,
    )

    return swept & (direction * (data.close - lagged(data.close, 1)) > 0.0)


def closed_off_extreme(data: Dataset, direction: FloatArray, fraction: float) -> BoolArray:
    """Bars whose close sits at least ``fraction`` of their range back from the stretched extreme.

    A zero-range bar never qualifies, which is the boundary
    :func:`nqbt.conditions.inverted_hammer` already takes for a body of zero.
    """
    span: FloatArray = data.high - data.low
    recovered: FloatArray = np.where(
        direction > 0.0,
        data.close - data.low,
        data.high - data.close,
    )

    return (span > 0.0) & (recovered >= fraction * span)


def signal_bar_shape(data: Dataset, direction: FloatArray, params: ElasticBandParams) -> BoolArray:
    """Which bars pass the candle requirement :attr:`ElasticBandParams.signal_shape` names.

    All-true at :data:`SHAPE_ANY`, the one value that reads nothing off the bar at all --
    which is why :func:`elasticband_signal` skips the conjunction there rather than ANDing it.
    """
    if params.signal_shape == SHAPE_REVERSAL:
        return closed_towards_basis(data.open, data.close, direction)

    if params.signal_shape == SHAPE_RECLAIM:
        return swept_and_reclaimed(data, direction)

    if params.signal_shape == SHAPE_REJECTION:
        return closed_off_extreme(data, direction, params.rejection_close_fraction)

    return np.ones(len(data), dtype=np.bool_)


def one_sided_bars(data: Dataset, direction: FloatArray, lookback: int) -> IntArray:
    """How many of the last ``lookback`` bars closed the way the move into the band was going.

    Bodies rather than closes against the previous close, and they need not be consecutive --
    which is what separates this from :attr:`ElasticBandParams.min_bars_outside`.
    """
    ran_down: IntArray = conditions.rolling_count(np.asarray(data.close < data.open), lookback)
    ran_up: IntArray = conditions.rolling_count(np.asarray(data.close > data.open), lookback)

    return np.where(direction > 0.0, ran_down, ran_up)


def elasticband_signal(data: Dataset, params: ElasticBandParams) -> BoolArray:
    """Bars whose close schedules an entry for the next bar's open.

    Where the extension is: it has lasted ``min_bars_outside`` unbroken bars on one side, it
    clears ``entry_std``, and it is under ``max_entry_std`` where that ceiling is on. The
    ceiling gates the bar the extension is measured on only -- a bar past it interrupts the
    trade, not the run.

    Which bar of that extension signals: ``entry_trigger``. :data:`TRIGGER_EXTENDED` takes a
    bar still outside and :data:`TRIGGER_RECOVERY` the one that closes back inside after the
    run has ended, so under the second the extension is the *previous* bar's.

    What the bars look like: ``signal_shape`` asks the signal bar's own candle to have turned
    and ``min_one_sided_bars`` asks the move into the band to have been one-sided.
    """
    _, _, stretch = band_series(data, params)
    beyond: BoolArray = beyond_band(stretch, params)
    direction: FloatArray = fade_direction(stretch)
    recovery: bool = params.entry_trigger == TRIGGER_RECOVERY
    triggered: BoolArray = returned_inside(stretch, params) if recovery else beyond
    extension: FloatArray = lagged(stretch, 1) if recovery else stretch

    long_run: BoolArray = beyond & (direction == trades.LONG)
    short_run: BoolArray = beyond & (direction == trades.SHORT)
    signal: BoolArray = np.zeros(len(data), dtype=np.bool_)
    if params.trade_long:
        counted_long: IntArray = outside_run_length(long_run, ends_before=recovery)
        signal |= triggered & (direction == trades.LONG) & (counted_long >= params.min_bars_outside)

    if params.trade_short:
        counted_short: IntArray = outside_run_length(short_run, ends_before=recovery)
        signal |= triggered & (direction == trades.SHORT) & (counted_short >= params.min_bars_outside)

    if params.max_entry_std > 0.0:
        signal &= np.abs(extension) <= params.max_entry_std

    if params.band_source == BAND_VWAP:
        signal &= vwap_band_warmed_up(data, params)

    if params.signal_shape != SHAPE_ANY:
        signal &= signal_bar_shape(data, direction, params)

    if params.min_one_sided_bars > 0:
        counted: IntArray = one_sided_bars(data, direction, params.one_sided_lookback)
        signal &= counted >= params.min_one_sided_bars

    return filters.apply_context_filters(signal, data, params)


def elasticband_legs(
    data: Dataset,
    params: ElasticBandParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the side
    is *not* overridden, so a drawn bar is faded on whichever side of the basis it sat.
    """
    basis, stddev, stretch = band_series(data, params)
    direction_at: FloatArray = fade_direction(stretch)
    extremes: FloatArray = run_extreme(
        data.low,
        data.high,
        beyond_band(stretch, params),
        direction_at,
    )
    if params.entry_trigger == TRIGGER_RECOVERY:
        # The signal bar is back inside the band, so the run it fades is the one that ended at
        # the bar before it and `run_extreme` reads `nan` on the bar itself.
        extremes = lagged(extremes, 1)

    signal = elasticband_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    levels: FloatArray = np.asarray(params.target_levels, dtype=np.float64)
    atr: FloatArray = data.atr_values(params.atr_period) if params.stop_mode == STOP_ATR else NO_ATR
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = simulate_elasticband(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        direction_at,
        BandSeries(basis=basis, stddev=stddev, excursion_extreme=extremes, atr=atr),
        quantities,
        levels,
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
        ElasticBandRules(
            stop_mode=params.stop_mode,
            atr_stop_multiple=params.atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(params.min_bracket_dollars),
            stop_offset=params.stop_offset_ticks * instrument.tick_size,
            catastrophe_distance=params.catastrophe_stop_ticks * instrument.tick_size,
            swing_lookback=params.swing_lookback,
            entry_std=params.entry_std,
            band_stop_std=params.band_stop_std,
            target_mode=params.target_mode,
            tp_multiplier=params.tp_multiplier,
            bars_required=params.bars_required_to_trade,
            exit_on_invalidation=params.exit_on_invalidation,
            max_hold_bars=params.max_hold_bars,
            block_entry_at_session_close=params.block_entry_at_session_close,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_elasticband(
    data: Dataset,
    params: ElasticBandParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = elasticband_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
