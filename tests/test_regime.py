"""Market-regime tests: the efficiency ratio, the three labels, and the entry filter.

Two things are pinned harder than the rest because their failures look like results rather
than like errors. **The warm-up**, because a bar the lookback cannot reach back from must not
acquire a label -- silently calling it consolidating would put unmeasured bars into a
stratification cell and make the counts add up anyway. And **the bit arithmetic against the
enum**: the filter tests ``1 << regime`` while a stratification reads the label itself, so the
two agree only while :class:`nqbt.regime.Regime`'s values and its bit positions stay the same
numbers.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, regime, sessions, sweep
from nqbt.context import ContextError, ContextSpec
from nqbt.regime import ALL_REGIMES, UNDEFINED, Regime, RegimeError
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal, run_deadcat
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

LOWER = 0.3
UPPER = 0.5

PARAMS_CLASSES = [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams]


def ramp(n: int = 50, step: float = 1.0) -> np.ndarray:
    """Build a straight line: every window's net move equals its path length."""
    return 100.0 + step * np.arange(n, dtype=np.float64)


def zigzag(n: int = 50, step: float = 1.0) -> np.ndarray:
    """Build an alternating one-step saw: net zero over any even window."""
    return 100.0 + step * (np.arange(n) % 2).astype(np.float64)


# -- the ratio itself ----------------------------------------------------------


def test_a_straight_line_scores_one_and_a_perfect_zigzag_scores_zero() -> None:
    # The two ends of the scale, and the reason the ratio needs no normalising constant.
    assert np.allclose(regime.efficiency_ratio(ramp(), 10)[10:], 1.0)
    assert np.allclose(regime.efficiency_ratio(zigzag(), 10)[10:], 0.0)


def test_the_ratio_stays_inside_zero_and_one_on_a_random_walk() -> None:
    rng = np.random.default_rng(11)
    walk = 16000.0 + np.cumsum(rng.normal(0, 5.0, 4000))
    for lookback in (2, 5, 20, 200):
        ratio = regime.efficiency_ratio(walk, lookback)
        measured = ratio[np.isfinite(ratio)]
        assert measured.size > 0
        assert measured.min() >= 0.0
        assert measured.max() <= 1.0


def test_a_window_that_never_moved_scores_zero_rather_than_dividing_by_zero() -> None:
    ratio = regime.efficiency_ratio(np.full(20, 100.0), 5)
    assert np.all(ratio[5:] == 0.0), "a dead-flat window is the extreme of consolidation"


def test_the_warm_up_is_undefined_rather_than_measured_over_a_short_window() -> None:
    """The pin the label's fourth state exists for.

    An expanding warm-up would emit a ratio of exactly 1.0 at the second bar -- numerator and
    denominator are the same quantity there -- and label the start of every dataset
    DIRECTIONAL.
    """
    ratio = regime.efficiency_ratio(ramp(), 10)
    assert np.all(np.isnan(ratio[:10]))
    assert np.isfinite(ratio[10])


def test_the_ratio_ignores_direction_level_and_scale() -> None:
    # |net| over sum|diff| is invariant under all three, which is what makes one pair of
    # thresholds meaningful across contracts and across price history.
    rng = np.random.default_rng(3)
    walk = 16000.0 + np.cumsum(rng.normal(0, 5.0, 500))
    base = regime.efficiency_ratio(walk, 20)
    for transformed in (-walk, walk + 5000.0, walk * 2.0):
        np.testing.assert_allclose(regime.efficiency_ratio(transformed, 20), base, equal_nan=True)


def test_a_series_shorter_than_its_lookback_is_undefined_throughout() -> None:
    assert np.all(np.isnan(regime.efficiency_ratio(ramp(5), 10)))


def test_an_empty_series_produces_an_empty_ratio() -> None:
    assert regime.efficiency_ratio(np.array([], dtype=np.float64), 5).size == 0


def test_a_lookback_of_one_is_refused_rather_than_reading_one_everywhere() -> None:
    with pytest.raises(RegimeError, match="lookback must be >= 2"):
        regime.efficiency_ratio(ramp(), 1)


# -- the thresholds and the three labels ---------------------------------------


def test_both_threshold_boundaries_fall_in_the_unclassifiable_band() -> None:
    # Strictly below is consolidating and strictly above is directional, so the band is
    # closed at both ends and no bar can satisfy two of the three.
    labels = regime.label(np.array([LOWER - 1e-9, LOWER, UPPER, UPPER + 1e-9]), LOWER, UPPER)
    assert list(labels) == [
        Regime.CONSOLIDATING,
        Regime.UNCLASSIFIABLE,
        Regime.UNCLASSIFIABLE,
        Regime.DIRECTIONAL,
    ]


def test_equal_thresholds_collapse_the_band_onto_the_boundary() -> None:
    labels = regime.label(np.array([0.39, 0.4, 0.41]), 0.4, 0.4)
    assert list(labels) == [Regime.CONSOLIDATING, Regime.UNCLASSIFIABLE, Regime.DIRECTIONAL]


def test_an_undefined_ratio_is_labelled_undefined_and_not_folded_into_the_band() -> None:
    assert regime.label(np.array([np.nan]), LOWER, UPPER)[0] == UNDEFINED


def test_every_measured_bar_gets_exactly_one_of_the_three_labels() -> None:
    rng = np.random.default_rng(7)
    ratio = regime.efficiency_ratio(16000.0 + np.cumsum(rng.normal(0, 5.0, 2000)), 20)
    labels = regime.label(ratio, LOWER, UPPER)
    assert set(np.unique(labels[np.isfinite(ratio)])) <= set(Regime)
    assert np.all(labels[~np.isfinite(ratio)] == UNDEFINED)


def test_thresholds_that_cross_are_refused_rather_than_silently_ordered() -> None:
    with pytest.raises(RegimeError, match="would put a bar in both regimes"):
        regime.label(np.array([0.5]), 0.7, 0.2)


@pytest.mark.parametrize(("lower", "upper"), [(-0.1, 0.5), (0.3, 1.5)])
def test_a_threshold_outside_zero_to_one_is_refused(lower, upper) -> None:
    with pytest.raises(RegimeError, match=r"must lie in 0\.\.1"):
        regime.label(np.array([0.5]), lower, upper)


# -- the mask ------------------------------------------------------------------


def test_a_mask_admits_exactly_the_regimes_it_names() -> None:
    mask = regime.regimes_mask([Regime.CONSOLIDATING, Regime.DIRECTIONAL])
    assert regime.regimes_in(mask) == (Regime.CONSOLIDATING, Regime.DIRECTIONAL)
    assert regime.describe_mask(mask) == "CONSOLIDATING+DIRECTIONAL"


def test_the_everything_mask_is_the_three_regimes_and_nothing_else() -> None:
    assert regime.regimes_in(ALL_REGIMES) == tuple(Regime)
    assert regime.regimes_mask(Regime) == ALL_REGIMES


@pytest.mark.parametrize("mask", [0, ALL_REGIMES + 1, -1])
def test_an_impossible_mask_is_refused(mask) -> None:
    with pytest.raises(RegimeError):
        regime.validate_mask(mask)


# -- the gate, and the one rule it shares with the labels ----------------------


def test_the_gate_and_the_labels_agree_on_every_bar_for_every_mask() -> None:
    """The filter's bit arithmetic and the label must name the same regime.

    They agree only while each :class:`Regime` sits at the bit position its value names.
    """
    rng = np.random.default_rng(21)
    ratio = regime.efficiency_ratio(16000.0 + np.cumsum(rng.normal(0, 5.0, 3000)), 20)
    labels = regime.label(ratio, LOWER, UPPER)
    for mask in range(1, ALL_REGIMES + 1):
        admitted = [int(r) for r in regime.regimes_in(mask)]
        assert np.array_equal(
            regime.gate(ratio, mask, LOWER, UPPER),
            np.isin(labels, admitted),
        ), regime.describe_mask(mask)


def test_an_undefined_bar_passes_no_mask_including_the_everything_mask() -> None:
    # The same asymmetry ``timeofday`` has for an out-of-session bar, and the reason a signal
    # must skip the gate entirely at the default rather than ANDing it.
    warm_up = regime.gate(regime.efficiency_ratio(ramp(), 10), ALL_REGIMES, LOWER, UPPER)[:10]
    assert not warm_up.any()


# -- the grid ------------------------------------------------------------------


def test_the_grid_holds_one_deduplicated_row_per_lookback() -> None:
    grid = regime.efficiency_ratio_grid(ramp(100), [20, 5, 20])
    assert grid.lookbacks.tolist() == [5, 20]
    assert len(grid) == 100
    assert grid.values_for(5).shape == (100,)


def test_a_grid_row_is_the_standalone_ratio_at_that_lookback() -> None:
    close = ramp(100) + zigzag(100)
    grid = regime.efficiency_ratio_grid(close, [5, 20])
    for lookback in (5, 20):
        np.testing.assert_array_equal(
            grid.values_for(lookback),
            regime.efficiency_ratio(close, lookback),
        )


def test_reading_a_lookback_the_grid_was_not_built_for_names_what_it_holds() -> None:
    grid = regime.efficiency_ratio_grid(ramp(100), [20])
    with pytest.raises(KeyError, match=r"built for \[20\]"):
        grid.values_for(21)


def test_a_grid_with_no_lookbacks_is_refused() -> None:
    with pytest.raises(RegimeError, match="no lookbacks supplied"):
        regime.efficiency_ratio_grid(ramp(100), [])


def test_a_grid_gate_and_a_grid_label_read_the_same_row() -> None:
    grid = regime.efficiency_ratio_grid(ramp(100) + zigzag(100), [20])
    labels = grid.labels_for(20, LOWER, UPPER)
    gated = grid.gate_for(20, Regime.DIRECTIONAL.bit, LOWER, UPPER)
    assert np.array_equal(gated, labels == Regime.DIRECTIONAL)


# -- the dataset ---------------------------------------------------------------


def bars(n: int = 1400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    stamps = pd.date_range("2024-01-07 23:01", periods=n, freq="min", tz="UTC")
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
        index=stamps,
    )
    frame["trading_day"] = sessions.classify(stamps).trading_day

    return frame


def prepared(**spec: object) -> context.Dataset:
    return context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), **spec))


def test_the_ratios_are_absent_when_nothing_asked_for_them() -> None:
    assert prepared().regimes is None


def test_reading_ratios_nobody_declared_names_the_spec_field_to_set() -> None:
    data = prepared()
    reads = (
        lambda: data.regime_gate(20, ALL_REGIMES, LOWER, UPPER),
        lambda: data.regime_values(20),
        lambda: data.regime_labels(20, LOWER, UPPER),
    )
    for read in reads:
        with pytest.raises(ContextError, match="regime_lookbacks"):
            read()


def test_the_ratios_are_present_and_counted_when_the_spec_asks() -> None:
    plain = prepared()
    asked = prepared(regime_lookbacks=(20,))
    assert asked.regime_values(20).shape == (len(asked),)
    assert asked.regime_labels(20, LOWER, UPPER).shape == (len(asked),)
    assert asked.regime_gate(20, Regime.DIRECTIONAL.bit, LOWER, UPPER).dtype == np.bool_
    assert asked.nbytes > plain.nbytes, "the ratios must be counted in what a worker is handed"


def test_the_union_of_two_specs_keeps_both_lookbacks() -> None:
    assert (ContextSpec(regime_lookbacks=(20,)) | ContextSpec(regime_lookbacks=(5,))).regime_lookbacks == (
        5,
        20,
    )
    assert (ContextSpec() | ContextSpec()).regime_lookbacks == ()


# -- the sweepable entry filter ------------------------------------------------


@pytest.mark.parametrize(
    "archetype",
    [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER],
)
def test_every_archetype_can_sweep_every_regime_axis(archetype) -> None:
    axes = {"regime_filter", "regime_lookback", "regime_consolidating_below", "regime_directional_above"}
    assert axes <= archetype.sweepable, archetype.name


def test_a_grid_asks_for_the_ratios_only_when_some_combination_narrows_the_regimes() -> None:
    assert sweep.Grid.of().required_context().regime_lookbacks == ()
    assert sweep.Grid.of(regime_filter=[ALL_REGIMES]).required_context().regime_lookbacks == ()
    narrowed = sweep.Grid.of(regime_filter=[Regime.DIRECTIONAL.bit, ALL_REGIMES])
    assert narrowed.required_context().regime_lookbacks == (20,)
    assert len(narrowed) == 2


def test_a_swept_lookback_reaches_the_context_spec() -> None:
    grid = sweep.Grid.of(regime_filter=[Regime.DIRECTIONAL.bit], regime_lookback=[5, 20])
    assert grid.required_context().regime_lookbacks == (5, 20)


@pytest.mark.parametrize(
    "axis",
    ["regime_lookback", "regime_consolidating_below", "regime_directional_above"],
)
def test_sweeping_a_regime_axis_that_no_filter_reads_is_refused(axis) -> None:
    """``ALL_REGIMES`` is 7, so a truthiness test would have read the filter as switched on.

    Without the mask's off value being stated, this grid would have run every combination
    twice for identical rows.
    """
    values = [5, 20] if axis == "regime_lookback" else [0.2, 0.4]
    with pytest.raises(sweep.SweepError, match="regime_filter"):
        sweep.Grid.of(**{axis: values})


@pytest.mark.parametrize(
    ("signal_fn", "params_cls"),
    [
        (deadcat_signal, DeadCatParams),
        (pullback_signal, PullBackAndGoParams),
        (crossover_signal, EmaCrossoverParams),
    ],
)
def test_the_filter_narrows_a_signal_to_the_regimes_it_admits(signal_fn, params_cls) -> None:
    spec = ContextSpec(
        ma_keys=conditions.ma_keys(ema=(9, 11, 21), sma=(60, 80, 155, 175)),
        atr_periods=(14,),
        regime_lookbacks=(20,),
        needs_ma_values=True,
    )
    data = context.prepare(bars(), spec)
    mask = regime.regimes_mask([Regime.CONSOLIDATING, Regime.UNCLASSIFIABLE])

    unfiltered = signal_fn(data, params_cls(bars_required_to_trade=20))
    filtered = signal_fn(data, params_cls(bars_required_to_trade=20, regime_filter=mask))

    assert unfiltered.any(), "the fixture must produce signals for the narrowing to mean anything"
    assert filtered.sum() < unfiltered.sum()
    assert not (filtered & ~unfiltered).any(), "a filter may only remove signals"
    labels = data.regime_labels(20, LOWER, UPPER)
    assert set(labels[filtered]) <= {Regime.CONSOLIDATING, Regime.UNCLASSIFIABLE}


def test_the_default_filter_is_exactly_no_filter() -> None:
    """What makes these four fields free to add to a reconciled archetype.

    ``ALL_REGIMES`` skips the conjunction entirely, so an unfiltered run is bit-for-bit the
    run that predates the fields -- the claim the trade-log gate checks at full scale.
    """
    data = prepared(regime_lookbacks=(20,))
    params = DeadCatParams(bars_required_to_trade=20)
    explicit = DeadCatParams(bars_required_to_trade=20, regime_filter=ALL_REGIMES)
    assert np.array_equal(deadcat_signal(data, params), deadcat_signal(data, explicit))
    pd.testing.assert_frame_equal(
        run_deadcat(data, params),
        run_deadcat(data, explicit),
        check_exact=True,
    )


def test_the_three_regime_filters_partition_every_measured_signal() -> None:
    """Stratification, not selection -- but only over the bars the ratio could measure.

    The warm-up is what makes this different from the session phases, which every in-session
    bar belongs to. Undefined bars pass no filter, so they are dropped by all three arms and
    the decomposition is of the measured signal rather than of the whole.
    """
    data = prepared(regime_lookbacks=(20,))
    whole = deadcat_signal(data, DeadCatParams(bars_required_to_trade=20))
    parts = [deadcat_signal(data, DeadCatParams(bars_required_to_trade=20, regime_filter=r.bit)) for r in Regime]
    labels = data.regime_labels(20, LOWER, UPPER)
    measured = whole & (labels != UNDEFINED)

    assert whole.any(), "nothing is decomposed if the fixture signals nothing"
    assert sum(int(part.sum()) for part in parts) == int(measured.sum())
    assert np.array_equal(np.logical_or.reduce(parts), measured)
    assert not any((part & (labels == UNDEFINED)).any() for part in parts)


def test_a_filtered_run_enters_only_inside_the_admitted_regimes() -> None:
    frame = bars()
    data = context.prepare(
        frame,
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), regime_lookbacks=(20,)),
    )
    mask = regime.regimes_mask([Regime.CONSOLIDATING, Regime.UNCLASSIFIABLE])
    log = run_deadcat(data, DeadCatParams(bars_required_to_trade=20, regime_filter=mask))
    assert not log.empty, "nothing is being checked if the filtered run trades nothing"

    # The entry bar is the one *after* the signal, so the check is on the signal's regime.
    labels = pd.Series(data.regime_labels(20, LOWER, UPPER), index=frame.index)
    signalled = labels.reindex(pd.DatetimeIndex(log["entry_time"]), method="ffill")
    assert set(signalled) <= {Regime.CONSOLIDATING, Regime.UNCLASSIFIABLE}


# -- the parameters ------------------------------------------------------------


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_an_impossible_filter_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(RegimeError):
        params_cls(regime_filter=0)
    with pytest.raises(RegimeError):
        params_cls(regime_filter=ALL_REGIMES + 1)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_a_degenerate_lookback_or_threshold_pair_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(RegimeError, match="lookback"):
        params_cls(regime_lookback=1)
    with pytest.raises(RegimeError, match="both regimes"):
        params_cls(regime_consolidating_below=0.8, regime_directional_above=0.2)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_regime_parameters_reach_the_results_row(params_cls) -> None:
    # They are parameters, so they ride in ``as_dict`` like every other one -- which is what
    # stops two rows of a regime sweep being indistinguishable in the results table.
    row = params_cls(regime_filter=Regime.DIRECTIONAL.bit, regime_lookback=30).as_dict()
    assert row["regime_filter"] == Regime.DIRECTIONAL.bit
    assert row["regime_lookback"] == 30
    assert row["regime_consolidating_below"] == 0.3
    assert row["regime_directional_above"] == 0.5
