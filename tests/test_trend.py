"""Trend tests: the three votes, the agreement they sum to, and what the label costs.

Two claims are pinned harder than the rest because their failures are silent. **No label is
ever taken off two components**, because a bar whose slope cannot be measured still has a
knowable price and stack, and letting those two decide would manufacture a trend out of a
warm-up. And **asking for the label must not switch on the raw moving-average values**, the
66 MB -> 595 MB memory switch: that is enforced by building the averages inside
``trend_grid`` and dropping them there, and the tests below state it as a property of a
prepared dataset rather than as an intention.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, sessions, sweep, trend
from nqbt.context import ContextError, ContextSpec
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal, run_deadcat
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams
from nqbt.trend import (
    ALL_TRENDS,
    N_COMPONENTS,
    UNDEFINED,
    Trend,
    TrendComponent,
    TrendError,
)

FAST = 20
SLOW = 50
SLOPE = 5
UNANIMOUS = 3

KEY = trend.key(FAST, SLOW, SLOPE)
OTHER = trend.key(10, SLOW, SLOPE)

PARAMS_CLASSES = [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams]

# 18:01 ET on a Sunday: the first bar of the session that ends on Monday the 8th.
FIRST_OPEN = "2024-01-07 23:01"


def votes_of(close, fast, slow, slope_lookback: int = SLOPE):
    """The vote block and agreement score for three series given directly, not via averages."""
    return trend.components(
        np.asarray(close, dtype=np.float64),
        np.asarray(fast, dtype=np.float64),
        np.asarray(slow, dtype=np.float64),
        slope_lookback,
    )


# -- the three components ------------------------------------------------------


def test_each_component_votes_on_the_fact_it_names() -> None:
    close = [10.0, 10.0, 10.0, 10.0]
    fast = [9.0, 9.0, 11.0, 11.0]
    slow = [11.0, 9.0, 11.0, 9.0]
    votes, _ = votes_of(close, fast, slow, slope_lookback=1)

    np.testing.assert_array_equal(votes[TrendComponent.PRICE_VS_SLOW], [-1, 1, -1, 1])
    np.testing.assert_array_equal(votes[TrendComponent.STACK], [-1, 0, 0, 1])
    # Slope reads slow against itself one bar back; bar 0 is inside the warm-up.
    np.testing.assert_array_equal(votes[TrendComponent.SLOW_SLOPE], [0, -1, 1, -1])


def test_exact_equality_votes_neither_way() -> None:
    flat = np.full(8, 100.0)
    votes, agreement = votes_of(flat, flat, flat, slope_lookback=2)
    assert not votes.any(), "nothing is above or below anything, so nothing may vote"
    np.testing.assert_array_equal(agreement[2:], np.zeros(6))


def test_the_slope_reads_back_exactly_the_lookback() -> None:
    # Rises for four bars then holds: with a 3-bar slope the last rise is still visible for
    # three bars after it, and flat only once the whole window sits on the plateau.
    slow = np.array([1.0, 2.0, 3.0, 4.0, 4.0, 4.0, 4.0, 4.0])
    votes, _ = votes_of(slow, slow, slow, slope_lookback=3)
    np.testing.assert_array_equal(votes[TrendComponent.SLOW_SLOPE], [0, 0, 0, 1, 1, 1, 0, 0])


def test_the_warm_up_is_the_slope_lookback_and_no_longer() -> None:
    rising = np.arange(1.0, 21.0)
    _, agreement = votes_of(rising, rising, rising, slope_lookback=SLOPE)
    assert np.isnan(agreement[:SLOPE]).all()
    assert np.isfinite(agreement[SLOPE:]).all(), "the averages emit from bar 0; nothing else warms up"


def test_price_and_stack_are_still_measured_through_the_warm_up() -> None:
    close = np.full(6, 10.0)
    fast = np.full(6, 12.0)
    slow = np.full(6, 8.0)
    votes, agreement = votes_of(close, fast, slow, slope_lookback=4)

    assert (votes[TrendComponent.PRICE_VS_SLOW] == 1).all()
    assert (votes[TrendComponent.STACK] == 1).all()
    assert not votes[TrendComponent.SLOW_SLOPE][:4].any(), "there is nothing to measure yet"
    assert np.isnan(agreement[:4]).all(), "and no score may be built out of the other two"


def test_no_label_is_taken_from_two_components() -> None:
    """The failure this prevents is a warm-up bar reading UP on price and stack alone."""
    close = np.full(6, 10.0)
    fast = np.full(6, 12.0)
    slow = np.full(6, 8.0)
    _, agreement = votes_of(close, fast, slow, slope_lookback=4)
    labels = trend.label(agreement, min_agreement=2)
    np.testing.assert_array_equal(labels[:4], np.full(4, UNDEFINED))


# -- the label -----------------------------------------------------------------


def scores(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


def test_unanimity_is_the_default_and_one_dissenting_component_is_mixed() -> None:
    labels = trend.label(scores(3.0, 1.0, -1.0, -3.0), UNANIMOUS)
    np.testing.assert_array_equal(labels, [Trend.UP, Trend.MIXED, Trend.MIXED, Trend.DOWN])


def test_both_agreement_boundaries_fall_in_the_outer_bands() -> None:
    """The opposite of ``regime`` and ``volume``, and deliberately so.

    ``min_agreement`` counts components that must agree rather than cutting a continuum, so
    exactly that many agreeing is the case the parameter names.
    """
    labels = trend.label(scores(-2.0, -1.0, 0.0, 1.0, 2.0), min_agreement=2)
    np.testing.assert_array_equal(
        labels,
        [Trend.DOWN, Trend.MIXED, Trend.MIXED, Trend.MIXED, Trend.UP],
    )


def test_a_lower_agreement_admits_a_majority_the_higher_one_calls_mixed() -> None:
    score = scores(2.0, -2.0)
    np.testing.assert_array_equal(trend.label(score, 3), [Trend.MIXED, Trend.MIXED])
    np.testing.assert_array_equal(trend.label(score, 2), [Trend.UP, Trend.DOWN])


def test_an_undefined_score_is_labelled_undefined_and_not_folded_into_mixed() -> None:
    labels = trend.label(scores(np.nan, 0.0), UNANIMOUS)
    assert labels[0] == UNDEFINED
    assert labels[1] == Trend.MIXED


@pytest.mark.parametrize("min_agreement", [0, -1, N_COMPONENTS + 1])
def test_an_agreement_no_bar_could_reach_or_every_bar_reaches_is_refused(min_agreement) -> None:
    with pytest.raises(TrendError, match="trend_min_agreement"):
        trend.validate_min_agreement(min_agreement)


# -- the mask ------------------------------------------------------------------


def test_a_mask_admits_exactly_the_trends_it_names() -> None:
    mask = trend.trends_mask([Trend.UP, Trend.DOWN])
    assert trend.trends_in(mask) == (Trend.DOWN, Trend.UP)
    assert trend.describe_mask(mask) == "DOWN+UP"


def test_the_everything_mask_is_the_three_trends_and_nothing_else() -> None:
    assert trend.trends_in(ALL_TRENDS) == tuple(Trend)
    assert trend.trends_mask(Trend) == ALL_TRENDS
    assert ALL_TRENDS == 7


@pytest.mark.parametrize("mask", [0, -1, ALL_TRENDS + 1])
def test_an_impossible_mask_is_refused(mask) -> None:
    with pytest.raises(TrendError):
        trend.validate_mask(mask)


def test_the_gate_and_the_labels_agree_on_every_bar_for_every_mask() -> None:
    score = np.concatenate([scores(np.nan), np.arange(-3.0, 4.0)])
    labels = trend.label(score, min_agreement=2)
    for mask in range(1, ALL_TRENDS + 1):
        gate = trend.gate(score, mask, min_agreement=2)
        expected = np.array(
            [state != UNDEFINED and bool(mask & (1 << state)) for state in labels],
        )
        np.testing.assert_array_equal(gate, expected, err_msg=f"mask {mask}")


def test_an_undefined_bar_passes_no_mask_including_the_everything_mask() -> None:
    """Why each signal skips the conjunction entirely at ``ALL_TRENDS`` rather than ANDing it."""
    score = scores(np.nan, 0.0)
    for mask in range(1, ALL_TRENDS + 1):
        assert not trend.gate(score, mask, UNANIMOUS)[0], f"mask {mask}"


# -- the key -------------------------------------------------------------------


@pytest.mark.parametrize(("fast", "slow"), [(50, 50), (60, 50)])
def test_a_fast_period_that_is_not_shorter_is_refused(fast, slow) -> None:
    with pytest.raises(TrendError, match="not shorter"):
        trend.key(fast, slow, SLOPE)


def test_a_period_below_one_is_refused() -> None:
    with pytest.raises(TrendError, match="trend_fast_period"):
        trend.key(0, SLOW, SLOPE)


def test_a_zero_bar_slope_is_refused_as_a_comparison_with_itself() -> None:
    with pytest.raises(TrendError, match="slope lookback"):
        trend.key(FAST, SLOW, 0)


def test_a_key_carries_the_three_things_a_label_is_determined_by() -> None:
    assert trend.key(FAST, SLOW, SLOPE) == (FAST, SLOW, SLOPE)


# -- the grid ------------------------------------------------------------------


def walk(n: int = 4000, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 16000.0 + np.cumsum(rng.normal(0, 1.0, n))


def test_the_grid_holds_one_deduplicated_row_per_key() -> None:
    grid = trend.trend_grid(walk(), [KEY, OTHER, KEY])
    assert grid.keys == (OTHER, KEY), "sorted and deduplicated"
    assert grid.agreement.shape == (2, 4000)
    assert grid.votes.shape == (2, N_COMPONENTS, 4000)
    assert len(grid) == 4000, "the length is the bars, not the keys"


def test_a_grid_row_is_the_standalone_series_for_that_key() -> None:
    close = walk()
    grid = trend.trend_grid(close, [KEY, OTHER])
    alone = trend.trend_grid(close, [KEY])
    np.testing.assert_array_equal(grid.agreement_for(KEY), alone.agreement_for(KEY))
    np.testing.assert_array_equal(grid.votes_for(KEY), alone.votes_for(KEY))


def test_one_component_can_be_read_back_out_of_the_vote_block() -> None:
    grid = trend.trend_grid(walk(), [KEY])
    for component in TrendComponent:
        np.testing.assert_array_equal(
            grid.component_for(KEY, component),
            grid.votes_for(KEY)[int(component)],
        )


def test_reading_a_key_the_grid_was_not_built_for_names_what_it_holds() -> None:
    grid = trend.trend_grid(walk(), [KEY])
    with pytest.raises(KeyError, match="built for"):
        grid.agreement_for(OTHER)


def test_a_grid_with_no_keys_is_refused() -> None:
    with pytest.raises(TrendError, match="no trend labels"):
        trend.trend_grid(walk(), [])


def test_a_grid_gate_and_a_grid_label_read_the_same_row() -> None:
    grid = trend.trend_grid(walk(), [KEY, OTHER])
    labels = grid.labels_for(KEY, UNANIMOUS)
    gate = grid.gate_for(KEY, Trend.UP.bit, UNANIMOUS)
    np.testing.assert_array_equal(gate, labels == Trend.UP)


def test_an_empty_series_produces_an_empty_grid() -> None:
    grid = trend.trend_grid(np.array([], dtype=np.float64), [KEY])
    assert len(grid) == 0
    assert grid.labels_for(KEY, UNANIMOUS).size == 0


# -- what the label says -------------------------------------------------------


def test_a_monotonic_rise_is_up_throughout_and_its_mirror_is_down() -> None:
    rising = np.arange(1000.0, 2000.0)
    up = trend.trend_grid(rising, [KEY]).labels_for(KEY, UNANIMOUS)
    down = trend.trend_grid(rising[::-1].copy(), [KEY]).labels_for(KEY, UNANIMOUS)
    assert (up[SLOPE:] == Trend.UP).all()
    assert (down[SLOPE:] == Trend.DOWN).all()


def test_the_label_reads_the_shape_rather_than_the_level() -> None:
    """Every component is a comparison, so a shift or a positive rescale cannot move one."""
    close = walk()
    plain = trend.trend_grid(close, [KEY]).labels_for(KEY, UNANIMOUS)
    shifted = trend.trend_grid(close + 5000.0, [KEY]).labels_for(KEY, UNANIMOUS)
    scaled = trend.trend_grid(close * 3.0, [KEY]).labels_for(KEY, UNANIMOUS)
    np.testing.assert_array_equal(plain, shifted)
    np.testing.assert_array_equal(plain, scaled)


def test_a_drift_is_labelled_up_and_the_same_noise_without_it_is_not() -> None:
    """The label has to separate the two, or it is not a trend label.

    One noise series, run with and without a drift added, so the only thing that differs
    between the two arms is the trend itself.
    """
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1.0, 8000)
    drifting = trend.trend_grid(16000.0 + np.cumsum(noise + 0.5), [KEY]).labels_for(KEY, UNANIMOUS)
    driftless = trend.trend_grid(16000.0 + np.cumsum(noise), [KEY]).labels_for(KEY, UNANIMOUS)

    assert (drifting == Trend.UP).mean() > 0.95
    assert (driftless == Trend.UP).mean() < 0.5
    up_against_down = (driftless == Trend.UP).mean() - (driftless == Trend.DOWN).mean()
    assert abs(up_against_down) < 0.15, "a driftless walk must not lean either way"


# -- the dataset ---------------------------------------------------------------


def bars(days: int = 12, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range(FIRST_OPEN, periods=days * 24 * 60, freq="min", tz="UTC")
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


def prepared(**spec: object) -> context.Dataset:
    return context.prepare(
        bars(),
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), **spec),
        bar_minutes=1,
    )


def test_the_trend_labels_are_absent_when_nothing_asked_for_them() -> None:
    assert prepared().trends is None


def test_reading_a_trend_label_nobody_declared_names_the_spec_field_to_set() -> None:
    data = prepared()
    reads = (
        lambda: data.trend_gate(KEY, ALL_TRENDS, UNANIMOUS),
        lambda: data.trend_values(KEY),
        lambda: data.trend_labels(KEY, UNANIMOUS),
        lambda: data.trend_components(KEY),
    )
    for read in reads:
        with pytest.raises(ContextError, match="trend_keys"):
            read()


def test_the_trend_labels_are_present_and_counted_when_the_spec_asks() -> None:
    plain = prepared()
    asked = prepared(trend_keys=(KEY,))
    assert asked.trend_values(KEY).shape == (len(asked),)
    assert asked.trend_labels(KEY, UNANIMOUS).shape == (len(asked),)
    assert asked.trend_components(KEY).shape == (N_COMPONENTS, len(asked))
    assert asked.trend_gate(KEY, Trend.UP.bit, UNANIMOUS).dtype == np.bool_
    assert asked.nbytes > plain.nbytes, "the labels must be counted in what a worker is handed"


def test_asking_for_a_trend_label_does_not_switch_on_the_raw_moving_averages() -> None:
    """The 66 MB -> 595 MB switch, enforced rather than intended.

    ``trend_grid`` builds its own averages over its own two periods and drops them with the
    labels kept, so the shared grids a parallel worker is handed stay boolean-only.
    """
    data = prepared(trend_keys=(KEY,))
    assert data.spec.trend_keys == (KEY,)
    assert not data.spec.needs_ma_values
    assert all(grid.values is None for grid in data.mas.values())
    with pytest.raises(ValueError, match="keep_values"):
        data.ma_values("ema", 11)


def test_a_trend_label_costs_the_labels_rather_than_the_average_values() -> None:
    plain = prepared()
    labelled = prepared(trend_keys=(KEY,))
    values = prepared(needs_ma_values=True)
    n = len(plain)

    assert labelled.nbytes - plain.nbytes == labelled.trends.nbytes
    assert labelled.trends.nbytes == n * (8 + N_COMPONENTS), "one float64 score and three votes"
    assert labelled.nbytes < values.nbytes, "the label is cheaper than keeping three MA series"


def test_the_union_of_two_specs_keeps_both_sets_of_keys() -> None:
    merged = ContextSpec(trend_keys=(KEY,)) | ContextSpec(trend_keys=(OTHER,))
    assert merged.trend_keys == (OTHER, KEY)
    assert (ContextSpec() | ContextSpec()).trend_keys == ()


# -- the sweepable entry filter ------------------------------------------------

TREND_AXES = {
    "trend_filter",
    "trend_fast_period",
    "trend_slow_period",
    "trend_slope_lookback",
    "trend_min_agreement",
}


@pytest.mark.parametrize(
    "archetype",
    [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER],
)
def test_every_archetype_can_sweep_every_trend_axis(archetype) -> None:
    assert TREND_AXES <= archetype.sweepable, archetype.name


@pytest.mark.parametrize(
    "archetype",
    [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER],
)
def test_no_archetype_asks_a_sweep_for_a_trend_label_by_default(archetype) -> None:
    grid = sweep.Grid(archetype=archetype, base=archetype.params_cls())
    assert grid.required_context().trend_keys == (), archetype.name


def test_a_grid_asks_for_the_labels_only_when_some_combination_narrows_the_trends() -> None:
    assert sweep.Grid.of(trend_filter=[ALL_TRENDS]).required_context().trend_keys == ()
    narrowed = sweep.Grid.of(trend_filter=[Trend.DOWN.bit, ALL_TRENDS])
    assert narrowed.required_context().trend_keys == (KEY,)
    assert len(narrowed) == 2


def test_a_swept_pair_reaches_the_context_spec_once_per_distinct_label() -> None:
    grid = sweep.Grid.of(
        trend_filter=[Trend.DOWN.bit],
        trend_fast_period=[10, 20],
        trend_slope_lookback=[5, 10],
    )
    assert len(grid) == 4
    assert grid.required_context().trend_keys == (
        trend.key(10, SLOW, 5),
        trend.key(10, SLOW, 10),
        trend.key(20, SLOW, 5),
        trend.key(20, SLOW, 10),
    )


def test_a_swept_pair_that_inverts_is_refused_rather_than_silently_ordered() -> None:
    grid = sweep.Grid.of(trend_filter=[Trend.DOWN.bit], trend_fast_period=[20, 60])
    with pytest.raises(TrendError, match="not shorter"):
        grid.required_context()


@pytest.mark.parametrize("axis", sorted(TREND_AXES - {"trend_filter"}))
def test_sweeping_a_trend_axis_that_no_filter_reads_is_refused(axis) -> None:
    """``ALL_TRENDS`` is 7, so a truthiness test would read the filter as switched on."""
    values = [1, 2] if axis == "trend_min_agreement" else [5, 10]
    with pytest.raises(sweep.SweepError, match="trend_filter"):
        sweep.Grid.of(**{axis: values})


@pytest.mark.parametrize(
    ("signal_fn", "params_cls"),
    [
        (deadcat_signal, DeadCatParams),
        (pullback_signal, PullBackAndGoParams),
        (crossover_signal, EmaCrossoverParams),
    ],
)
def test_the_filter_narrows_a_signal_to_the_trends_it_admits(signal_fn, params_cls) -> None:
    spec = ContextSpec(
        ma_keys=conditions.ma_keys(ema=(9, 11, 21), sma=(60, 80, 155, 175)),
        atr_periods=(14,),
        trend_keys=(KEY,),
        needs_ma_values=True,
    )
    data = context.prepare(bars(), spec, bar_minutes=1)
    labels = data.trend_labels(KEY, UNANIMOUS)
    unfiltered = signal_fn(data, params_cls(bars_required_to_trade=20))
    assert unfiltered.any(), "the fixture must produce signals for the narrowing to mean anything"

    # Exclude whichever trend the archetype signals in most, so the mask is guaranteed to bite
    # rather than depending on which direction the fixture happens to favour.
    dominant = max(Trend, key=lambda t: int((unfiltered & (labels == t)).sum()))
    admitted = {t for t in Trend if t is not dominant}
    filtered = signal_fn(
        data,
        params_cls(bars_required_to_trade=20, trend_filter=trend.trends_mask(admitted)),
    )

    assert filtered.sum() < unfiltered.sum()
    assert not (filtered & ~unfiltered).any(), "a filter may only remove signals"
    assert set(labels[filtered]) <= admitted


def test_the_default_filter_is_exactly_no_filter() -> None:
    """What makes these five fields free to add to a reconciled archetype.

    ``ALL_TRENDS`` skips the conjunction entirely, so an unfiltered run is bit-for-bit the run
    that predates the fields -- the claim the trade-log gate checks at full scale.
    """
    data = prepared(trend_keys=(KEY,))
    params = DeadCatParams(bars_required_to_trade=20)
    explicit = DeadCatParams(bars_required_to_trade=20, trend_filter=ALL_TRENDS)
    assert np.array_equal(deadcat_signal(data, params), deadcat_signal(data, explicit))
    pd.testing.assert_frame_equal(
        run_deadcat(data, params),
        run_deadcat(data, explicit),
        check_exact=True,
    )


def test_the_three_trend_filters_partition_every_measured_signal() -> None:
    """Stratification, not selection -- over the bars a slope could be measured for."""
    data = prepared(trend_keys=(KEY,))
    whole = deadcat_signal(data, DeadCatParams(bars_required_to_trade=20))
    parts = [deadcat_signal(data, DeadCatParams(bars_required_to_trade=20, trend_filter=t.bit)) for t in Trend]
    labels = data.trend_labels(KEY, UNANIMOUS)
    measured = whole & (labels != UNDEFINED)

    assert whole.any(), "nothing is decomposed if the fixture signals nothing"
    assert sum(int(part.sum()) for part in parts) == int(measured.sum())
    assert np.array_equal(np.logical_or.reduce(parts), measured)


def test_a_filtered_run_enters_only_inside_the_admitted_trends() -> None:
    frame = bars()
    data = context.prepare(
        frame,
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), trend_keys=(KEY,)),
        bar_minutes=1,
    )
    mask = trend.trends_mask([Trend.MIXED, Trend.DOWN])
    log = run_deadcat(data, DeadCatParams(bars_required_to_trade=20, trend_filter=mask))
    assert not log.empty, "nothing is being checked if the filtered run trades nothing"

    # An entry order lives one bar, so the entry bar is always the one *after* the signal and
    # the filter has to be checked against the bar before each fill, not the fill itself.
    labels = data.trend_labels(KEY, UNANIMOUS)
    entered = frame.index.get_indexer(pd.DatetimeIndex(log["entry_time"]))
    assert (entered > 0).all(), "every entry must be locatable for the check to mean anything"
    assert set(labels[entered - 1]) <= {Trend.MIXED, Trend.DOWN}


# -- the parameters ------------------------------------------------------------


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_an_impossible_filter_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(TrendError):
        params_cls(trend_filter=0)
    with pytest.raises(TrendError):
        params_cls(trend_filter=ALL_TRENDS + 1)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_a_degenerate_pair_slope_or_agreement_is_refused_at_construction(params_cls) -> None:
    # Checked whatever the filter, so a nonsense value cannot ride along inertly until the
    # filter is swept onto it.
    with pytest.raises(TrendError, match="not shorter"):
        params_cls(trend_fast_period=SLOW, trend_slow_period=SLOW)
    with pytest.raises(TrendError, match="slope lookback"):
        params_cls(trend_slope_lookback=0)
    with pytest.raises(TrendError, match="trend_min_agreement"):
        params_cls(trend_min_agreement=N_COMPONENTS + 1)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_key_says_which_label_the_combination_reads(params_cls) -> None:
    params = params_cls(trend_fast_period=10, trend_slope_lookback=15)
    assert params.trend_key == trend.key(10, SLOW, 15)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_trend_parameters_reach_the_results_row(params_cls) -> None:
    # They are parameters, so they ride in ``as_dict`` like every other one -- which is what
    # stops two rows of a trend sweep being indistinguishable in the results table.
    row = params_cls(trend_filter=Trend.UP.bit, trend_slope_lookback=15).as_dict()
    assert row["trend_filter"] == Trend.UP.bit
    assert row["trend_fast_period"] == FAST
    assert row["trend_slow_period"] == SLOW
    assert row["trend_slope_lookback"] == 15
    assert row["trend_min_agreement"] == UNANIMOUS
