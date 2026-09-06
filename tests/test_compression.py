"""Compression tests: the two width forms, the trailing rank, and the entry filter.

Two claims are pinned harder than the rest because their failures look like findings rather
than like errors. **No bar contributes to its own rank**, because a compression measure that
reads the bar it is about to trade is the fictional edge ``docs/roadmap.md`` §M19 names as the
second easiest in the project to manufacture; the truncation test is what says so, rather than
a comment claiming it. And **the rank is what makes a raw threshold mean one thing**, because
neither raw width has a unit -- every test of a threshold states the widths it is cutting as
well, so a cut that stopped being comparable would show up as a table rather than as a pass.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, compression, conditions, context, sessions, sweep
from nqbt.compression import (
    ALL_STATES,
    MIN_BASELINE_BARS,
    MIN_PERIOD,
    UNDEFINED,
    Compression,
    CompressionError,
    CompressionForm,
)
from nqbt.context import ContextError, ContextSpec
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal, run_deadcat
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

COMPRESSED = 0.25
EXPANDED = 0.75
BASELINE = 50
PERIOD = 20

PARAMS_CLASSES = [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams]
ARCHETYPES = [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER]

BANDWIDTH = compression.key(CompressionForm.BANDWIDTH, PERIOD, BASELINE)
RANGE_TO_ATR = compression.key(CompressionForm.RANGE_TO_ATR, PERIOD, BASELINE)

# 18:01 ET on a Sunday: the first bar of the session that ends on Monday the 8th.
FIRST_OPEN = "2024-01-07 23:01"


def stamps(days: int = 12) -> pd.DatetimeIndex:
    """One minute bar per minute for ``days`` calendar days, breaks and weekends included."""
    return pd.date_range(FIRST_OPEN, periods=days * 24 * 60, freq="min", tz="UTC")


def bars(days: int = 12, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = stamps(days)
    n = index.size
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


def widening(n: int = 400, step: float = 0.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bars whose range grows monotonically: high, low and close for an unambiguous ordering."""
    close = np.full(n, 100.0)
    half = step * np.arange(1, n + 1)

    return close + half, close - half, close


# -- the two width forms -------------------------------------------------------


def test_bandwidth_is_two_standard_deviations_over_the_basis() -> None:
    basis = np.array([100.0, 200.0, 400.0])
    stddev = np.array([1.0, 2.0, 4.0])
    np.testing.assert_allclose(
        compression.bandwidth(basis, stddev),
        [0.02, 0.02, 0.02],
        err_msg="a band twice as wide around a price twice as high is the same compression",
    )


def test_bandwidth_is_undefined_where_there_is_no_basis_to_divide_by() -> None:
    basis = np.array([100.0, 0.0, np.nan, -100.0])
    stddev = np.array([1.0, 1.0, 1.0, 1.0])
    measured = compression.bandwidth(basis, stddev)
    assert measured[0] == pytest.approx(0.02)
    assert np.isnan(measured[1:]).all(), "a zero, missing or negative midline is not a scale"


def test_the_bandwidth_multiple_is_a_scale_factor_and_not_an_axis() -> None:
    """Why ``BANDWIDTH_MULTIPLE`` is a constant: it cannot move a rank or a quantile."""
    basis = np.full(200, 100.0)
    stddev = np.abs(np.random.default_rng(3).normal(1.0, 0.3, 200))
    one = compression.trailing_rank(compression.bandwidth(basis, stddev), MIN_BASELINE_BARS)
    doubled = compression.trailing_rank(2.0 * compression.bandwidth(basis, stddev), MIN_BASELINE_BARS)
    np.testing.assert_array_equal(one, doubled)


def test_range_to_atr_reads_near_one_when_every_bar_repeats_the_same_range() -> None:
    """A window that went nowhere is its own bar's range wide; a trending one is many."""
    n = 300
    flat_high = np.full(n, 101.0)
    flat_low = np.full(n, 99.0)
    flat_close = np.full(n, 100.0)
    flat = compression.range_to_atr(flat_high, flat_low, flat_close, PERIOD)

    drift = np.arange(n, dtype=np.float64)
    trending = compression.range_to_atr(flat_high + drift, flat_low + drift, flat_close + drift, PERIOD)

    assert flat[-1] == pytest.approx(1.0)
    assert trending[-1] > 5.0, "a window that trended is many ATRs wide"


def test_range_to_atr_is_undefined_through_its_own_warm_up() -> None:
    high, low, close = widening(100)
    measured = compression.range_to_atr(high, low, close, PERIOD)
    assert np.isnan(measured[: PERIOD - 1]).all(), "a window that has not filled has not been measured"
    assert np.isfinite(measured[PERIOD:]).all()


# -- the trailing rank ---------------------------------------------------------


def test_the_rank_is_one_when_a_bar_is_the_widest_of_its_window_and_zero_when_narrowest() -> None:
    rising = np.arange(200, dtype=np.float64)
    assert compression.trailing_rank(rising, MIN_BASELINE_BARS)[-1] == pytest.approx(1.0)
    assert compression.trailing_rank(-rising, MIN_BASELINE_BARS)[-1] == pytest.approx(0.0)


def test_a_flat_series_ranks_at_a_half_rather_than_at_either_extreme() -> None:
    """A tie counts as half, so a stretch with no variation is normal rather than compressed."""
    flat = np.full(200, 3.0)
    ranked = compression.trailing_rank(flat, MIN_BASELINE_BARS)
    measured = ranked[np.isfinite(ranked)]
    assert measured.size > 0
    np.testing.assert_allclose(measured, 0.5)


def test_the_rank_is_undefined_until_a_full_window_of_measured_values_sits_behind_it() -> None:
    values = np.arange(200, dtype=np.float64)
    values[:5] = np.nan
    ranked = compression.trailing_rank(values, MIN_BASELINE_BARS)

    assert np.isnan(ranked[:MIN_BASELINE_BARS]).all()
    assert np.isnan(ranked[MIN_BASELINE_BARS : 5 + MIN_BASELINE_BARS]).all(), (
        "a warm-up hole must not shorten the window a rank is taken over"
    )
    assert np.isfinite(ranked[5 + MIN_BASELINE_BARS :]).all()


def test_no_bar_contributes_to_its_own_rank() -> None:
    """The lookahead claim, pinned by truncation rather than asserted in a docstring.

    Every rank computed over a prefix must equal the rank the whole series gives that bar. A
    window that included the current bar, or that read forward, would move when the tail is
    removed.
    """
    rng = np.random.default_rng(11)
    values = np.abs(rng.normal(1.0, 0.4, 400))
    whole = compression.trailing_rank(values, BASELINE)
    for cut in (120, 250, 399):
        prefix = compression.trailing_rank(values[:cut], BASELINE)
        np.testing.assert_array_equal(
            prefix,
            whole[:cut],
            err_msg=f"the rank at bar {cut - 1} moved when the bars after it were removed",
        )


def test_a_rank_that_could_not_fail_this_way_is_worth_having() -> None:
    """The gate above can fail: a window that reaches one bar forward breaks it immediately."""
    values = np.arange(200, dtype=np.float64)
    lookahead = np.concatenate([compression.trailing_rank(values, MIN_BASELINE_BARS)[1:], [np.nan]])
    honest = compression.trailing_rank(values[:150], MIN_BASELINE_BARS)
    assert not np.array_equal(lookahead[:150], honest)


# -- labels, masks and thresholds ----------------------------------------------


def test_both_threshold_boundaries_fall_in_the_normal_band() -> None:
    ranks = np.array([0.0, 0.24, COMPRESSED, 0.5, EXPANDED, 0.76, 1.0])
    labels = compression.label(ranks, COMPRESSED, EXPANDED)
    np.testing.assert_array_equal(
        labels,
        [
            Compression.COMPRESSED,
            Compression.COMPRESSED,
            Compression.NORMAL,
            Compression.NORMAL,
            Compression.NORMAL,
            Compression.EXPANDED,
            Compression.EXPANDED,
        ],
    )


def test_an_unranked_bar_is_undefined_rather_than_a_fourth_state() -> None:
    labels = compression.label(np.array([np.nan, 0.5]), COMPRESSED, EXPANDED)
    assert labels[0] == UNDEFINED
    assert labels[1] == Compression.NORMAL


def test_an_undefined_bar_passes_no_mask_including_the_one_that_admits_everything() -> None:
    ranks = np.array([np.nan, 0.5])
    passed = compression.gate(ranks, ALL_STATES, COMPRESSED, EXPANDED)
    assert not passed[0], "which is why a signal skips the gate entirely at ALL_STATES"
    assert passed[1]


def test_equal_thresholds_collapse_the_normal_band_onto_the_boundary() -> None:
    labels = compression.label(np.array([0.4, 0.5, 0.6]), 0.5, 0.5)
    np.testing.assert_array_equal(
        labels,
        [Compression.COMPRESSED, Compression.NORMAL, Compression.EXPANDED],
    )


def test_a_mask_round_trips_through_states_in() -> None:
    wanted = (Compression.COMPRESSED, Compression.EXPANDED)
    assert compression.states_in(compression.states_mask(wanted)) == wanted
    assert compression.describe_mask(ALL_STATES) == "COMPRESSED+NORMAL+EXPANDED"


def test_thresholds_fitted_as_quantiles_cut_the_shares_they_name() -> None:
    ranks = np.linspace(0.0, 1.0, 1001)
    low, high = compression.thresholds_from_quantiles(ranks, 0.2, 0.8)
    labels = compression.label(ranks, low, high)
    assert (labels == Compression.COMPRESSED).mean() == pytest.approx(0.2, abs=0.01)
    assert (labels == Compression.EXPANDED).mean() == pytest.approx(0.2, abs=0.01)


def test_a_raw_threshold_cuts_the_rank_and_says_nothing_about_the_width() -> None:
    """Why the rank exists at all -- ``docs/roadmap.md`` §M19.1.

    The same number is a quarter of the bars against the rank and every one of them against
    the width, because a width has no unit to have a threshold in. How close to a quarter
    depends on how autocorrelated the width is, so this pins the neighbourhood rather than a
    figure; the measured spread across roots, resolutions, forms and periods is in §M19.1.
    """
    rng = np.random.default_rng(7)
    log_width = np.zeros(4000)
    for i in range(1, log_width.size):
        log_width[i] = 0.97 * log_width[i - 1] + rng.normal(0, 0.1)
    width = 0.002 * np.exp(log_width)

    ranks = compression.trailing_rank(width, BASELINE)
    measured = np.isfinite(ranks)
    share_of_rank = (ranks[measured] < COMPRESSED).mean()
    share_of_width = (width[measured] < COMPRESSED).mean()

    assert 0.10 < share_of_rank < 0.45, f"a rank cut at {COMPRESSED} took {share_of_rank:.3f}"
    assert share_of_width == 1.0, "and the same number against the width took every bar"


# -- validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "fragment"),
    [
        (lambda: compression.validate_mask(0), "admits no state"),
        (lambda: compression.validate_mask(1 << 5), "outside 0..7"),
        (lambda: compression.validate_mask(-1), "outside 0..7"),
        (lambda: compression.validate_form(9), "unknown compression form"),
        (lambda: compression.validate_period(MIN_PERIOD - 1), "must span >= 2 bars"),
        (lambda: compression.validate_baseline_bars(MIN_BASELINE_BARS - 1), "must span >= 20 bars"),
        (lambda: compression.validate_thresholds(-0.1, 0.5), "must lie in 0..1"),
        (lambda: compression.validate_thresholds(0.5, 1.5), "must lie in 0..1"),
        (lambda: compression.validate_thresholds(0.8, 0.2), "which would put a bar in both"),
        (lambda: compression.validate_quantiles(0.9, 0.1), "which would cross the thresholds"),
        (lambda: compression.validate_quantiles(1.2, 0.1), "must lie in 0..1"),
        (lambda: compression.validate_quantiles(0.1, 1.2), "must lie in 0..1"),
    ],
)
def test_an_impossible_argument_raises_and_says_which(call, fragment) -> None:
    with pytest.raises(CompressionError, match=fragment):
        call()


def test_a_quantile_of_nothing_measured_raises_rather_than_returning_nan() -> None:
    with pytest.raises(CompressionError, match="every bar is undefined"):
        compression.thresholds_from_quantiles(np.full(10, np.nan), 0.2, 0.8)


def test_a_grid_with_no_keys_raises() -> None:
    high, low, close = widening()
    with pytest.raises(CompressionError, match="no compression series supplied"):
        compression.compression_grid(high, low, close, ())


def test_a_bandwidth_key_without_a_band_grid_says_where_the_band_comes_from() -> None:
    high, low, close = widening()
    with pytest.raises(CompressionError, match="needs a band grid"):
        compression.compression_grid(high, low, close, (BANDWIDTH,))


# -- the grid ------------------------------------------------------------------


def test_the_grid_deduplicates_and_sorts_its_keys() -> None:
    high, low, close = widening()
    grid = compression.compression_grid(high, low, close, (RANGE_TO_ATR, RANGE_TO_ATR))
    assert grid.keys == (RANGE_TO_ATR,)
    assert len(grid) == close.size


def test_reading_a_series_the_grid_was_not_built_for_says_what_it_holds() -> None:
    high, low, close = widening()
    grid = compression.compression_grid(high, low, close, (RANGE_TO_ATR,))
    with pytest.raises(KeyError, match="is not in this grid"):
        grid.rank_for(compression.key(CompressionForm.RANGE_TO_ATR, PERIOD, BASELINE + 1))


def test_the_grid_reports_the_bytes_a_worker_is_handed() -> None:
    high, low, close = widening()
    grid = compression.compression_grid(high, low, close, (RANGE_TO_ATR,))
    assert grid.nbytes == grid.width.nbytes + grid.rank.nbytes


def test_a_key_names_its_form_and_both_windows() -> None:
    assert compression.describe_key(RANGE_TO_ATR) == f"range_to_atr_{PERIOD}_{BASELINE}"


# -- the dataset ---------------------------------------------------------------


def prepared(**spec: object) -> context.Dataset:
    return context.prepare(
        bars(),
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), **spec),
        bar_minutes=1,
    )


def test_the_compression_series_are_absent_when_nothing_asked_for_them() -> None:
    assert prepared().compressions is None


def test_reading_compression_nobody_declared_names_the_spec_field_to_set() -> None:
    data = prepared()
    reads = (
        lambda: data.compression_gate(RANGE_TO_ATR, ALL_STATES, COMPRESSED, EXPANDED),
        lambda: data.compression_width(RANGE_TO_ATR),
        lambda: data.compression_rank(RANGE_TO_ATR),
        lambda: data.compression_labels(RANGE_TO_ATR, COMPRESSED, EXPANDED),
    )
    for read in reads:
        with pytest.raises(ContextError, match="compression_keys"):
            read()


def test_a_bandwidth_key_implies_the_band_period_behind_it() -> None:
    """The band is shared rather than re-derived -- ``docs/roadmap.md`` §M26."""
    spec = ContextSpec(compression_keys=(BANDWIDTH,))
    assert spec.band_periods == (), "the caller declared no band of its own"
    assert spec.band_periods_needed() == (PERIOD,)

    data = context.prepare(bars(), spec, bar_minutes=1)
    assert data.band is not None
    np.testing.assert_array_equal(
        data.compression_width(BANDWIDTH),
        compression.bandwidth(data.band_basis(PERIOD), data.band_stddev(PERIOD)),
    )


def test_a_range_form_implies_no_band_at_all() -> None:
    spec = ContextSpec(compression_keys=(RANGE_TO_ATR,))
    assert spec.band_periods_needed() == ()
    assert context.prepare(bars(), spec, bar_minutes=1).band is None


def test_a_declared_band_period_survives_beside_an_implied_one() -> None:
    spec = ContextSpec(band_periods=(9,), compression_keys=(BANDWIDTH,))
    assert spec.band_periods_needed() == (9, PERIOD)


def test_two_specs_merge_their_compression_keys() -> None:
    merged = ContextSpec(compression_keys=(BANDWIDTH,)) | ContextSpec(compression_keys=(RANGE_TO_ATR,))
    assert merged.compression_keys == tuple(sorted((BANDWIDTH, RANGE_TO_ATR)))
    assert (ContextSpec() | ContextSpec()).compression_keys == ()


def test_the_grid_is_counted_in_what_a_worker_is_handed() -> None:
    bare = prepared()
    withheld = prepared(compression_keys=(RANGE_TO_ATR,))
    assert withheld.nbytes > bare.nbytes


# -- the sweep and the archetypes ----------------------------------------------


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_a_grid_that_never_filters_builds_no_compression_series(archetype) -> None:
    grid = sweep.Grid(axes={"compression_filter": [ALL_STATES]}, archetype=archetype)
    assert grid.required_context().compression_keys == ()


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_a_grid_that_filters_declares_every_series_it_could_read(archetype) -> None:
    grid = sweep.Grid(
        axes={
            "compression_filter": [Compression.COMPRESSED.bit, ALL_STATES],
            "compression_form": [int(f) for f in CompressionForm],
            "compression_period": [PERIOD],
            "compression_baseline_bars": [BASELINE],
        },
        archetype=archetype,
    )
    assert set(grid.required_context().compression_keys) == {BANDWIDTH, RANGE_TO_ATR}


def test_sweeping_a_compression_axis_with_the_filter_off_is_refused() -> None:
    """The axes cost runtime and change nothing while the filter admits every state."""
    with pytest.raises(sweep.SweepError, match="compression_period"):
        sweep.Grid(
            axes={"compression_period": [10, PERIOD], "compression_baseline_bars": [BASELINE]},
            archetype=archetypes.DEADCATBOUNCE,
        )


def test_the_compression_axes_are_live_once_the_filter_is_set() -> None:
    grid = sweep.Grid(
        axes={
            "compression_filter": [Compression.COMPRESSED.bit],
            "compression_period": [10, PERIOD],
            "compression_baseline_bars": [BASELINE],
        },
        archetype=archetypes.DEADCATBOUNCE,
    )
    assert grid.dead_axes() == {}


@pytest.mark.parametrize(
    ("signal_fn", "params_cls"),
    [
        (deadcat_signal, DeadCatParams),
        (pullback_signal, PullBackAndGoParams),
        (crossover_signal, EmaCrossoverParams),
    ],
)
def test_the_filter_narrows_a_signal_to_the_states_it_admits(signal_fn, params_cls) -> None:
    spec = ContextSpec(
        ma_keys=conditions.ma_keys(ema=(9, 11, 21), sma=(60, 80, 155, 175)),
        atr_periods=(14,),
        compression_keys=(RANGE_TO_ATR,),
        needs_ma_values=True,
    )
    data = context.prepare(bars(), spec, bar_minutes=1)
    mask = compression.states_mask([Compression.NORMAL, Compression.EXPANDED])
    settings = {
        "bars_required_to_trade": 20,
        "compression_form": int(CompressionForm.RANGE_TO_ATR),
        "compression_period": PERIOD,
        "compression_baseline_bars": BASELINE,
    }

    unfiltered = signal_fn(data, params_cls(**settings))
    filtered = signal_fn(data, params_cls(**settings, compression_filter=mask))

    assert unfiltered.any(), "the fixture must produce signals for the narrowing to mean anything"
    assert filtered.sum() < unfiltered.sum()
    assert not (filtered & ~unfiltered).any(), "a filter may only remove signals"
    labels = data.compression_labels(RANGE_TO_ATR, COMPRESSED, EXPANDED)
    assert set(labels[filtered]) <= {Compression.NORMAL, Compression.EXPANDED}


def test_the_default_filter_is_exactly_no_filter() -> None:
    """What makes these six fields free to add to a reconciled archetype.

    ``ALL_STATES`` skips the conjunction entirely, so an unfiltered run is bit-for-bit the run
    that predates the fields -- the claim the trade-log gate checks at full scale.
    """
    data = prepared(compression_keys=(RANGE_TO_ATR,))
    params = DeadCatParams(bars_required_to_trade=20)
    explicit = DeadCatParams(bars_required_to_trade=20, compression_filter=ALL_STATES)
    assert np.array_equal(deadcat_signal(data, params), deadcat_signal(data, explicit))
    pd.testing.assert_frame_equal(run_deadcat(data, params), run_deadcat(data, explicit))


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_every_compression_field_is_validated_whatever_the_filter_admits(params_cls) -> None:
    """A nonsense window must not ride along inertly until a sweep turns its filter on."""
    with pytest.raises(CompressionError, match="must span >= 2 bars"):
        params_cls(compression_period=1)

    with pytest.raises(CompressionError, match="must span >= 20 bars"):
        params_cls(compression_baseline_bars=2)

    with pytest.raises(CompressionError, match="unknown compression form"):
        params_cls(compression_form=9)

    with pytest.raises(CompressionError, match="which would put a bar in both"):
        params_cls(compression_compressed_below=0.9, compression_expanded_above=0.1)


def test_a_grid_fits_thresholds_to_one_series_own_ranks() -> None:
    """The stratification path: a cut stated as a share of the bars this series actually has.

    Fitted thresholds hit their share where a raw pair only approaches it, which is the whole
    reason ``thresholds_for`` exists beside the raw cut.
    """
    frame = bars()
    grid = compression.compression_grid(
        frame["high"].to_numpy(),
        frame["low"].to_numpy(),
        frame["close"].to_numpy(),
        (RANGE_TO_ATR,),
    )
    low_cut, high_cut = grid.thresholds_for(RANGE_TO_ATR, 0.25, 0.75)

    assert 0.0 <= low_cut <= high_cut <= 1.0
    labels = grid.labels_for(RANGE_TO_ATR, low_cut, high_cut)
    measured = labels[labels != UNDEFINED]
    assert (measured == Compression.COMPRESSED).mean() == pytest.approx(0.25, abs=0.02)
    assert (measured == Compression.EXPANDED).mean() == pytest.approx(0.25, abs=0.02)
