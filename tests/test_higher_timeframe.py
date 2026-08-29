"""Higher-timeframe moving averages: the projection, and the lookahead it exists to refuse.

**One test here matters more than the rest.** A coarse bar covering 18:15-18:20 is not knowable
until 18:20, so every fine bar inside it must read the bar *before* -- and a projection that
leaks the current one manufactures a spectacular and entirely fictional edge that no summary
statistic would show. ``test_a_bar_inside_an_unfinished_coarse_bar_cannot_read_it`` builds a
series whose current coarse close is the only thing that could flip the label, and pins the
label that does not flip.

The projection is checked against an explicit loop over the coarse stamps rather than against a
second ``searchsorted``, because a test that re-derives the answer the implementation's own way
cannot catch the implementation being wrong.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, higher_timeframe, indicators, resample, sessions, sweep
from nqbt.context import ContextError, ContextSpec
from nqbt.higher_timeframe import (
    ALL_SIDES,
    UNDEFINED,
    HigherTimeframeError,
    Side,
)
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

COARSE = 5
PERIOD = 1
"""An EMA of 1 is the coarse close itself, so every expected value below is readable by eye."""

KEY = higher_timeframe.key(COARSE, PERIOD)
OTHER = higher_timeframe.key(COARSE, 3)

PARAMS_CLASSES = [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams]

# 18:01 ET on a Sunday: the first bar of the session that ends on Monday the 8th. Bucket b of a
# 5-minute grid anchored to that open therefore covers positions 5b..5b+4 of what follows.
FIRST_OPEN = "2024-01-07 23:01"

LEAKY_CLOSES = [100.0] * 15 + [120.0, 120.0, 120.0, 120.0, 150.0]
"""Three flat buckets, then one whose *close alone* is above the fine closes before it.

Positions 15-18 sit inside bucket 3 and must read bucket 2's average, 100.0, which puts their
close of 120.0 ABOVE it. Bucket 3's own average is 150.0, which would put them BELOW -- so the
label at those four bars is the leak, stated as a value rather than as an intention.
"""

INSIDE_UNFINISHED = slice(15, 19)
LAST_COMPLETED_AVERAGE = 100.0
LEAKED_AVERAGE = 150.0


def minute_bars(closes: list[float], first_open: str = FIRST_OPEN) -> pd.DataFrame:
    """1-minute bars carrying the given closes, from the first bar of an ETH session."""
    index = pd.date_range(first_open, periods=len(closes), freq="min", tz="UTC")
    close = np.asarray(closes, dtype=np.float64)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.ones(close.size),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


def random_bars(days: int = 12, seed: int = 5) -> pd.DataFrame:
    """A drifting series long enough for a 60-minute average to mean something."""
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


def last_completed(coarse_stamps: pd.DatetimeIndex, values, stamps: pd.DatetimeIndex):
    """The projection by an explicit loop: the last coarse value stamped at or before each bar."""
    out = []
    for stamp in stamps:
        seen = [v for s, v in zip(coarse_stamps, values, strict=True) if s <= stamp]
        out.append(seen[-1] if seen else np.nan)
    return np.asarray(out, dtype=np.float64)


# -- the lookahead ------------------------------------------------------------


def test_a_bar_inside_an_unfinished_coarse_bar_cannot_read_it() -> None:
    grid = higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [KEY])

    np.testing.assert_array_equal(
        grid.values_for(KEY)[INSIDE_UNFINISHED],
        np.full(4, LAST_COMPLETED_AVERAGE),
    )
    np.testing.assert_array_equal(grid.labels_for(KEY)[INSIDE_UNFINISHED], np.full(4, Side.ABOVE))
    assert LEAKY_CLOSES[15] < LEAKED_AVERAGE, "the fixture must make the leak flip the label"


def test_a_gate_on_the_leaked_side_admits_none_of_those_bars() -> None:
    grid = higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [KEY])

    admitted = grid.gate_for(KEY, Side.BELOW.bit)

    assert not admitted[INSIDE_UNFINISHED].any(), "reading the unfinished bucket would signal here"


def test_a_coarse_bar_is_readable_from_the_bar_that_closes_alongside_it() -> None:
    grid = higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [KEY])

    # Position 19 closes bucket 3, so bucket 3 is complete and its own close is the average.
    assert grid.values_for(KEY)[19] == LEAKED_AVERAGE
    assert grid.labels_for(KEY)[19] == Side.AT


def test_no_bar_reads_an_average_stamped_after_it() -> None:
    bars = random_bars()
    coarse = resample.resample(bars[["close"]], 60)
    values = indicators.nt8_ema(coarse["close"].to_numpy(np.float64), 20)

    projected = higher_timeframe.project(
        pd.DatetimeIndex(coarse.index),
        values,
        pd.DatetimeIndex(bars.index),
    )

    np.testing.assert_array_equal(
        projected,
        last_completed(pd.DatetimeIndex(coarse.index), values, pd.DatetimeIndex(bars.index)),
    )


def test_bars_before_the_first_coarse_close_are_undefined() -> None:
    grid = higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [KEY])

    # Bucket 0 covers positions 0-4 and closes on the last of them.
    assert np.isnan(grid.values_for(KEY)[:4]).all()
    np.testing.assert_array_equal(grid.labels_for(KEY)[:4], np.full(4, UNDEFINED))
    assert not np.isnan(grid.values_for(KEY)[4])


def test_an_undefined_bar_passes_no_mask_including_all_sides() -> None:
    grid = higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [KEY])

    assert not grid.gate_for(KEY, ALL_SIDES)[:4].any()


# -- the average is the coarse one --------------------------------------------


def test_the_average_is_computed_on_coarse_bars_not_projected_from_fine_ones() -> None:
    bars = random_bars()
    grid = higher_timeframe.higher_timeframe_grid(bars, [higher_timeframe.key(60, 20)])
    coarse = resample.resample(bars[["close"]], 60)
    by_hand = indicators.nt8_ema(coarse["close"].to_numpy(np.float64), 20)

    projected = grid.values_for(higher_timeframe.key(60, 20))
    on_coarse_closes = pd.Series(projected, index=bars.index).reindex(coarse.index).to_numpy()

    np.testing.assert_allclose(on_coarse_closes, by_hand)
    fine = indicators.nt8_ema(bars["close"].to_numpy(np.float64), 20)
    assert not np.allclose(projected[-1], fine[-1]), "a 60-minute average is not the 1-minute one"


def test_the_side_is_the_fine_close_against_the_coarse_average() -> None:
    labelled = higher_timeframe.label(
        np.array([9.0, 10.0, 11.0, 12.0]),
        np.array([10.0, 10.0, 10.0, np.nan]),
    )

    np.testing.assert_array_equal(labelled, [Side.BELOW, Side.AT, Side.ABOVE, UNDEFINED])


def test_one_resample_serves_every_period_at_the_same_resolution(monkeypatch) -> None:
    calls: list[int] = []
    real = resample.resample

    def counted(frame, minutes, **kwargs):
        calls.append(minutes)
        return real(frame, minutes, **kwargs)

    monkeypatch.setattr(resample, "resample", counted)
    higher_timeframe.higher_timeframe_grid(
        random_bars(),
        [higher_timeframe.key(60, 20), higher_timeframe.key(60, 50), higher_timeframe.key(30, 20)],
    )

    assert sorted(calls) == [30, 60]


def test_the_coarse_average_is_the_same_whatever_resolution_the_strategy_runs_on() -> None:
    bars = random_bars()
    five = resample.resample(bars, 5)
    key = higher_timeframe.key(60, 20)

    on_one = higher_timeframe.higher_timeframe_grid(bars, [key], bar_minutes=1)
    on_five = higher_timeframe.higher_timeframe_grid(five, [key], bar_minutes=5)

    at_five_minute_stamps = pd.Series(on_one.values_for(key), index=bars.index).reindex(five.index).to_numpy()
    np.testing.assert_array_equal(at_five_minute_stamps, on_five.values_for(key))


def test_the_filter_survives_the_resolution_axis() -> None:
    grid = sweep.Grid.of(
        DeadCatParams(higher_timeframe_filter=Side.BELOW.bit, higher_timeframe_period=20),
    )

    table, _ = sweep.sweep_axes(random_bars(), grid, resolutions=(1, 5))

    assert list(table["resolution"]) == [1, 5]
    assert set(table["higher_timeframe_filter"]) == {Side.BELOW.bit}


# -- the mask -----------------------------------------------------------------


def test_a_mask_round_trips_through_the_sides_it_admits() -> None:
    mask = higher_timeframe.sides_mask([Side.BELOW, Side.ABOVE])

    assert higher_timeframe.sides_in(mask) == (Side.BELOW, Side.ABOVE)
    assert higher_timeframe.describe_mask(mask) == "BELOW+ABOVE"


def test_all_sides_admits_every_side() -> None:
    assert higher_timeframe.sides_in(ALL_SIDES) == tuple(Side)


@pytest.mark.parametrize("mask", [0, -1, ALL_SIDES + 1])
def test_an_impossible_mask_is_refused(mask: int) -> None:
    with pytest.raises(HigherTimeframeError):
        higher_timeframe.validate_mask(mask)


def test_a_one_minute_higher_timeframe_is_refused_as_the_existing_gate() -> None:
    with pytest.raises(HigherTimeframeError, match="existing moving-average gate"):
        higher_timeframe.key(1, 20)


def test_a_period_below_one_is_refused() -> None:
    with pytest.raises(HigherTimeframeError, match="higher_timeframe_period"):
        higher_timeframe.key(5, 0)


@pytest.mark.parametrize("minutes", [5, 7])
def test_a_resolution_that_is_not_a_proper_multiple_of_the_bars_is_refused(minutes: int) -> None:
    with pytest.raises(HigherTimeframeError, match="proper multiple"):
        higher_timeframe.higher_timeframe_grid(
            minute_bars(LEAKY_CLOSES),
            [higher_timeframe.key(minutes, 3)],
            bar_minutes=5,
        )


def test_an_empty_key_set_is_refused_rather_than_building_an_empty_grid() -> None:
    with pytest.raises(HigherTimeframeError, match="no higher-timeframe averages"):
        higher_timeframe.higher_timeframe_grid(minute_bars(LEAKY_CLOSES), [])


def test_projecting_values_that_do_not_match_the_coarse_stamps_is_refused() -> None:
    bars = minute_bars(LEAKY_CLOSES)
    coarse = resample.resample(bars[["close"]], COARSE)

    with pytest.raises(HigherTimeframeError, match="coarse stamps"):
        higher_timeframe.project(
            pd.DatetimeIndex(coarse.index),
            np.zeros(coarse.index.size + 1),
            pd.DatetimeIndex(bars.index),
        )


# -- the grid -----------------------------------------------------------------


def test_the_grid_sorts_and_deduplicates_its_keys() -> None:
    grid = higher_timeframe.higher_timeframe_grid(random_bars(), [OTHER, KEY, KEY])

    assert grid.keys == (KEY, OTHER)
    assert len(grid) == grid.values.shape[1]  # noqa: PD011 - a grid attribute, not a Series


def test_reading_a_key_the_grid_was_not_built_for_says_what_it_holds() -> None:
    grid = higher_timeframe.higher_timeframe_grid(random_bars(), [KEY])

    with pytest.raises(KeyError, match="built for"):
        grid.values_for(OTHER)


def test_the_grid_costs_nine_bytes_a_bar_for_each_average() -> None:
    bars = random_bars()
    grid = higher_timeframe.higher_timeframe_grid(bars, [KEY, OTHER])

    assert grid.nbytes == 2 * len(bars) * (8 + 1)


# -- the dataset --------------------------------------------------------------


def prepared(**spec: object) -> context.Dataset:
    return context.prepare(
        random_bars(),
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), **spec),
        bar_minutes=1,
    )


def test_the_averages_are_absent_when_nothing_asked_for_them() -> None:
    assert prepared().higher_timeframes is None


def test_reading_an_average_nobody_declared_names_the_spec_field_to_set() -> None:
    data = prepared()
    reads = (
        lambda: data.higher_timeframe_gate(KEY, ALL_SIDES),
        lambda: data.higher_timeframe_values(KEY),
        lambda: data.higher_timeframe_labels(KEY),
    )
    for read in reads:
        with pytest.raises(ContextError, match="higher_timeframe_keys"):
            read()


def test_declaring_an_average_builds_exactly_it() -> None:
    data = prepared(higher_timeframe_keys=(KEY,))

    assert data.higher_timeframes is not None
    assert data.higher_timeframes.keys == (KEY,)
    assert data.higher_timeframe_labels(KEY).size == len(data)


def test_asking_for_an_average_does_not_switch_on_the_raw_moving_average_values() -> None:
    data = prepared(higher_timeframe_keys=(KEY,))

    assert not data.spec.needs_ma_values
    assert all(g.values is None for g in data.mas.values())  # noqa: PD011 - grid attribute


def test_the_average_grid_is_counted_in_what_a_worker_is_handed() -> None:
    without = prepared()
    with_average = prepared(higher_timeframe_keys=(KEY,))

    assert with_average.nbytes - without.nbytes == with_average.higher_timeframes.nbytes


def test_two_specs_merge_their_averages() -> None:
    merged = ContextSpec(higher_timeframe_keys=(OTHER,)) | ContextSpec(higher_timeframe_keys=(KEY,))

    assert merged.higher_timeframe_keys == (KEY, OTHER)


# -- the sweep ----------------------------------------------------------------


def test_nothing_is_built_while_every_combination_admits_every_side() -> None:
    spec = archetypes.moving_average_context(
        {
            "higher_timeframe_filter": [ALL_SIDES],
            "higher_timeframe_minutes": [5, 60],
            "higher_timeframe_period": [20],
        },
    )

    assert spec.higher_timeframe_keys == ()


def test_a_filtering_combination_builds_every_resolution_and_period_it_might_read() -> None:
    spec = archetypes.moving_average_context(
        {
            "higher_timeframe_filter": [ALL_SIDES, Side.BELOW.bit],
            "higher_timeframe_minutes": [5, 60],
            "higher_timeframe_period": [20, 50],
        },
    )

    assert spec.higher_timeframe_keys == (
        higher_timeframe.key(5, 20),
        higher_timeframe.key(5, 50),
        higher_timeframe.key(60, 20),
        higher_timeframe.key(60, 50),
    )


def test_sweeping_the_resolution_while_the_filter_is_off_is_refused_as_a_dead_axis() -> None:
    with pytest.raises(sweep.SweepError, match="higher_timeframe_minutes"):
        sweep.Grid.of(higher_timeframe_minutes=[5, 60])


def test_the_axes_come_alive_once_the_filter_admits_one_side() -> None:
    grid = sweep.Grid.of(
        higher_timeframe_filter=[Side.BELOW.bit],
        higher_timeframe_minutes=[5, 60],
    )

    assert grid.dead_axes() == {}
    assert len(grid) == 2


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_every_archetype_defaults_to_admitting_every_side(params_cls) -> None:
    params = params_cls()

    assert params.higher_timeframe_filter == ALL_SIDES
    assert params.higher_timeframe_key == higher_timeframe.key(
        params.higher_timeframe_minutes,
        params.higher_timeframe_period,
    )


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_a_nonsense_resolution_is_refused_even_while_the_filter_is_inert(params_cls) -> None:
    with pytest.raises(HigherTimeframeError):
        params_cls(higher_timeframe_minutes=1)


SIGNALS = [
    (DeadCatParams, deadcat_signal),
    (PullBackAndGoParams, pullback_signal),
    (EmaCrossoverParams, crossover_signal),
]


@pytest.mark.parametrize(("params_cls", "signal_of"), SIGNALS)
def test_the_filter_narrows_a_signal_to_the_side_it_admits(params_cls, signal_of) -> None:
    bars = random_bars()
    key = higher_timeframe.key(60, 20)
    grid = sweep.Grid.of(params_cls(higher_timeframe_filter=Side.BELOW.bit, higher_timeframe_period=20))
    data = sweep.prepare_for(bars, grid, bar_minutes=1)

    unfiltered = signal_of(data, params_cls())
    filtered = signal_of(data, grid.base)

    assert filtered.sum() < unfiltered.sum(), "the fixture must have signals on both sides"
    np.testing.assert_array_equal(filtered, unfiltered & (data.higher_timeframe_labels(key) == Side.BELOW))


def test_a_signal_reading_an_undeclared_average_raises_rather_than_dropping_the_gate() -> None:
    data = prepared()

    with pytest.raises(ContextError, match="higher_timeframe_keys"):
        deadcat_signal(data, DeadCatParams(higher_timeframe_filter=Side.BELOW.bit))
