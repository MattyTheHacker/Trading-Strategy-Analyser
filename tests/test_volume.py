"""Volume tests: the three forms, the bar-of-session baseline, and the entry filter.

Two claims are pinned harder than the rest because their failures look like findings rather
than like errors. **The baseline is per bar of session**, because a plain rolling average over
adjacent bars marks every cash-open bar heavy and every overnight bar thin -- a table that
reads as a discovery and is a clock. Every test of that states both halves: what this module
does, and what the naive normalisation would have done instead. And **no bar contributes to
its own baseline**, because a normalisation that reads the present is a lookahead that quietly
flatters every stratification taken through it.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, sessions, sweep, timeofday, volume
from nqbt.context import ContextError, ContextSpec
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal, run_deadcat
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams
from nqbt.volume import (
    ALL_STATES,
    MIN_BASELINE_SESSIONS,
    NO_ROLLING,
    UNDEFINED,
    VolumeError,
    VolumeForm,
    VolumeState,
)

THIN = 0.7
HEAVY = 1.5
BASELINE = 20

PARAMS_CLASSES = [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams]

PER_BAR = volume.key(VolumeForm.PER_BAR, 30, BASELINE)
ROLLING = volume.key(VolumeForm.ROLLING, 30, BASELINE)
SESSION_TO_DATE = volume.key(VolumeForm.SESSION_TO_DATE, 30, BASELINE)

# 18:01 ET on a Sunday: the first bar of the session that ends on Monday the 8th.
FIRST_OPEN = "2024-01-07 23:01"


def stamps(days: int = 35) -> pd.DatetimeIndex:
    """One minute bar per minute for ``days`` calendar days, breaks and weekends included."""
    return pd.date_range(FIRST_OPEN, periods=days * 24 * 60, freq="min", tz="UTC")


def clock(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Trading day, in-session flag and bar-of-session index for one series of stamps."""
    info = sessions.classify(index)
    labels = timeofday.classify(index, bar_minutes=1, info=info)
    return info.trading_day, info.in_session, labels.bar_of_session


def grid_of(counts: np.ndarray, index: pd.DatetimeIndex, *keys: volume.VolumeKey) -> volume.VolumeGrid:
    trading_day, in_session, bar_of_session = clock(index)
    return volume.volume_grid(counts, trading_day, in_session, bar_of_session, keys or (PER_BAR,))


def hump(index: pd.DatetimeIndex) -> np.ndarray:
    """Volume that depends on **nothing but the time of day**, identical every session.

    A Gaussian peak over the cash open on a flat overnight floor -- the shape that makes a
    rolling average over adjacent bars produce a table of findings out of a clock.
    """
    _, _, bar_of_session = clock(index)
    minutes = np.where(bar_of_session >= 0, bar_of_session, 0).astype(np.float64)
    return 100.0 + 3900.0 * np.exp(-0.5 * ((minutes - 905.0) / 30.0) ** 2)


# -- the three absolute forms --------------------------------------------------


def test_the_per_bar_form_is_the_count_itself_inside_a_session_and_zero_outside() -> None:
    index = stamps(12)
    _, in_session, _ = clock(index)
    counts = np.arange(index.size, dtype=np.float64) % 97 + 1.0
    absolute = grid_of(counts, index, PER_BAR).absolute_for(PER_BAR)
    np.testing.assert_array_equal(absolute[in_session], counts[in_session])
    assert np.all(absolute[~in_session] == 0.0), "a stray print is not this bar's volume either"


def test_the_rolling_form_sums_the_trailing_window_and_is_undefined_before_it_fills() -> None:
    index = stamps(12)
    counts = np.arange(index.size, dtype=np.float64) % 97 + 1.0
    absolute = grid_of(counts, index, ROLLING).absolute_for(ROLLING)

    assert np.all(np.isnan(absolute[:29])), "a window that has not filled has not been measured"
    _, in_session, _ = clock(index)
    traded = np.where(in_session, counts, 0.0)
    for i in (29, 500, index.size - 1):
        assert absolute[i] == pytest.approx(traded[i - 29 : i + 1].sum())


def test_the_session_to_date_form_restarts_at_every_open() -> None:
    index = stamps(12)
    trading_day, in_session, bar_of_session = clock(index)
    counts = np.arange(index.size, dtype=np.float64) % 97 + 1.0
    absolute = grid_of(counts, index, SESSION_TO_DATE).absolute_for(SESSION_TO_DATE)

    frame = pd.DataFrame({"day": trading_day, "count": counts, "cumulative": absolute})[in_session]
    for _, session in frame.groupby("day"):
        np.testing.assert_allclose(session["cumulative"], session["count"].cumsum())
    assert np.all(np.isnan(absolute[~in_session])), "a bar in no session has no session to date"


def test_an_out_of_session_print_is_not_session_volume() -> None:
    """NT8 building bars against an ETH template would never form one, so no sum counts it."""
    index = stamps(12)
    _, in_session, _ = clock(index)
    quiet = np.where(in_session, 5.0, 0.0)
    loud = np.where(in_session, 5.0, 1e6)

    for key in (PER_BAR, ROLLING, SESSION_TO_DATE):
        np.testing.assert_array_equal(
            grid_of(quiet, index, key).absolute_for(key),
            grid_of(loud, index, key).absolute_for(key),
            err_msg=key.form.name,
        )


def test_a_one_bar_rolling_window_is_refused_as_the_per_bar_form_under_another_name() -> None:
    with pytest.raises(VolumeError, match="one-bar window is VolumeForm.PER_BAR"):
        volume.validate_rolling_bars(1)


def test_an_unknown_form_names_the_ones_that_exist() -> None:
    with pytest.raises(VolumeError, match="PER_BAR=0"):
        volume.validate_form(9)


# -- the baseline: a clock is not a signal -------------------------------------


def test_a_pure_time_of_day_shape_produces_no_state_at_all() -> None:
    """The claim the module exists for, with the failure it prevents stated beside it.

    Volume here is a function of the bar of session and of nothing else, so **nothing is
    unusual anywhere**. Against the bar-of-session baseline every measured bar is NORMAL;
    against a trailing average of adjacent bars the same series manufactures both extremes.
    """
    index = stamps(35)
    counts = hump(index)
    labels = grid_of(counts, index, PER_BAR).labels_for(PER_BAR, THIN, HEAVY)
    measured = labels[labels != UNDEFINED]

    assert measured.size > 0, "nothing is being checked if every bar is undefined"
    assert set(np.unique(measured)) == {VolumeState.NORMAL}

    naive = counts / pd.Series(counts).rolling(60).median().shift(1).to_numpy()
    manufactured = volume.label(naive, THIN, HEAVY)
    assert (manufactured == VolumeState.THIN).any()
    assert (manufactured == VolumeState.HEAVY).any()


def test_the_baseline_is_the_median_of_the_same_bar_of_session_over_prior_sessions() -> None:
    rng = np.random.default_rng(4)
    n_sessions, n_indices, window = 40, 9, 6
    session_id = np.repeat(np.arange(n_sessions), n_indices)
    bar_of_session = np.tile(np.arange(n_indices), n_sessions)
    counts = rng.integers(0, 500, size=session_id.size).astype(np.float64)

    # Holes, because the archive has them and a hole must not shift anything.
    kept = rng.random(session_id.size) >= 0.15
    session_id, bar_of_session, counts = session_id[kept], bar_of_session[kept], counts[kept]

    got = volume.relative_to_bar_of_session(counts, session_id, bar_of_session, window, min_observations=3)

    want = np.full(counts.size, np.nan)
    for i in range(counts.size):
        prior = counts[
            (session_id >= session_id[i] - window)
            & (session_id < session_id[i])
            & (bar_of_session == bar_of_session[i])
        ]
        if prior.size >= 3 and np.median(prior) > 0:
            want[i] = counts[i] / np.median(prior)
    np.testing.assert_allclose(got, want, equal_nan=True)


def test_no_bar_contributes_to_its_own_baseline() -> None:
    """The lookahead pin. Rewriting one session may not move that session's own ratios.

    Stated as a property rather than as a transcript: whatever the last session's volume
    becomes, the *earlier* sessions are untouched and the last session's own baseline is the
    one it had, so its ratio scales exactly with what was written into it.
    """
    index = stamps(35)
    trading_day, in_session, bar_of_session = clock(index)
    counts = np.where(in_session, 250.0, 0.0)
    last = trading_day == trading_day[in_session][-1]

    doubled = np.where(last, counts * 2.0, counts)
    before = volume.volume_grid(counts, trading_day, in_session, bar_of_session, [PER_BAR])
    after = volume.volume_grid(doubled, trading_day, in_session, bar_of_session, [PER_BAR])

    plain = before.relative_for(PER_BAR)
    changed = after.relative_for(PER_BAR)
    earlier = in_session & ~last
    np.testing.assert_allclose(changed[earlier], plain[earlier], equal_nan=True)

    final = in_session & last & np.isfinite(plain)
    assert final.any(), "the last session must be labelled for this to check anything"
    np.testing.assert_allclose(changed[final], plain[final] * 2.0)


def test_the_first_sessions_are_undefined_rather_than_measured_over_too_few() -> None:
    index = stamps(35)
    trading_day, in_session, _ = clock(index)
    labels = grid_of(np.where(in_session, 250.0, 0.0), index, PER_BAR).labels_for(PER_BAR, THIN, HEAVY)

    days = pd.Series(trading_day)[in_session].unique()
    for day in days[:MIN_BASELINE_SESSIONS]:
        assert np.all(labels[trading_day == day] == UNDEFINED), day
    assert (labels[trading_day == days[MIN_BASELINE_SESSIONS]] != UNDEFINED).any()


def test_a_bar_of_session_whose_prior_sessions_traded_nothing_is_undefined_not_infinite() -> None:
    session_id = np.repeat(np.arange(10), 3)
    bar_of_session = np.tile(np.arange(3), 10)
    counts = np.where(bar_of_session == 0, 0.0, 100.0)
    relative = volume.relative_to_bar_of_session(counts, session_id, bar_of_session, 5)
    assert np.all(np.isnan(relative[bar_of_session == 0]))
    assert np.all(relative[(bar_of_session == 1) & (session_id >= 5)] == 1.0)


def test_a_bar_in_no_session_gets_no_baseline() -> None:
    index = stamps(12)
    _, in_session, _ = clock(index)
    relative = grid_of(np.full(index.size, 250.0), index, PER_BAR).relative_for(PER_BAR)
    assert np.all(np.isnan(relative[~in_session]))


def test_a_step_in_absolute_volume_washes_out_of_the_baseline_after_the_window() -> None:
    """What a contract roll does. Prices are back-adjusted; volume is not, and should not be.

    The step is real and belongs in the absolute series. It reaches relative volume for the
    length of the baseline window and then leaves, which is why a discontinuity there is
    dated by the roll rather than by the market.
    """
    index = stamps(60)
    trading_day, in_session, bar_of_session = clock(index)
    days = pd.Series(trading_day)[in_session].unique()
    roll = days[len(days) // 2]

    stepped = np.where(in_session, np.where(trading_day >= roll, 1000.0, 100.0), 0.0)
    relative = volume.volume_grid(stepped, trading_day, in_session, bar_of_session, [PER_BAR]).relative_for(
        PER_BAR,
    )

    on_roll = relative[in_session & (trading_day == roll) & np.isfinite(relative)]
    settled = relative[in_session & (trading_day == days[len(days) // 2 + BASELINE]) & np.isfinite(relative)]
    assert on_roll.size and settled.size
    assert np.allclose(on_roll, 10.0), "the incoming contract is ten times the outgoing one"
    assert np.allclose(settled, 1.0), "and a baseline window later it is simply normal"


def test_a_baseline_shorter_than_the_floor_is_refused() -> None:
    with pytest.raises(VolumeError, match=f"span >= {MIN_BASELINE_SESSIONS} sessions"):
        volume.validate_baseline_sessions(MIN_BASELINE_SESSIONS - 1)


def test_an_empty_series_produces_an_empty_baseline() -> None:
    empty = np.array([], dtype=np.float64)
    assert volume.relative_to_bar_of_session(empty, empty, empty, BASELINE).size == 0


def test_a_series_with_no_session_at_all_is_undefined_throughout() -> None:
    counts = np.full(50, 250.0)
    out_of_session = np.full(50, UNDEFINED, dtype=np.int64)
    relative = volume.relative_to_bar_of_session(counts, out_of_session, out_of_session, BASELINE)
    assert np.all(np.isnan(relative))


# -- relative volume is what makes one threshold mean one thing ----------------


def test_relative_volume_is_invariant_to_the_scale_of_the_root() -> None:
    """NQ and MNQ trade different counts for the same exposure; the ratio does not care.

    This is what an absolute threshold cannot do, and the reason there is no absolute filter
    to sweep -- ``docs/roadmap.md`` §M10.2.
    """
    index = stamps(35)
    counts = hump(index) + np.arange(index.size) % 13
    base = grid_of(counts, index, PER_BAR).labels_for(PER_BAR, THIN, HEAVY)
    for scale in (0.1, 10.0, 1000.0):
        scaled = grid_of(counts * scale, index, PER_BAR).labels_for(PER_BAR, THIN, HEAVY)
        np.testing.assert_array_equal(scaled, base, err_msg=str(scale))


def test_a_secular_trend_moves_the_absolute_series_and_barely_moves_the_relative_one() -> None:
    """Absolute volume carries *when in history* a bar happened; relative volume removes it.

    That is the cross-check absolute is kept for and the reason only relative is filtered on.
    The removal is not perfect and the residual is worth stating: a trailing median lags a
    rising trend, so the whole relative series sits above 1 rather than scattering about it.
    """
    index = stamps(60)
    _, in_session, _ = clock(index)
    tenfold = np.where(in_session, 250.0 * np.linspace(1.0, 10.0, index.size), 0.0)
    grid = grid_of(tenfold, index, PER_BAR)

    measured = np.isfinite(grid.relative_for(PER_BAR))
    assert measured.any()
    absolute = grid.absolute_for(PER_BAR)[measured]
    relative = grid.relative_for(PER_BAR)[measured]

    assert absolute.max() / absolute.min() > 4.0, "the era is in the absolute series"
    assert relative.max() / relative.min() < 1.5, "and mostly not in the relative one"
    assert np.all(relative > 1.0), "what is left of it is a level, not a shape"


# -- the thresholds and the three labels ---------------------------------------


def test_both_threshold_boundaries_fall_in_the_normal_band() -> None:
    # Strictly below is thin and strictly above is heavy, so the band is closed at both ends
    # and no bar can satisfy two of the three.
    labels = volume.label(np.array([THIN - 1e-9, THIN, HEAVY, HEAVY + 1e-9]), THIN, HEAVY)
    assert list(labels) == [
        VolumeState.THIN,
        VolumeState.NORMAL,
        VolumeState.NORMAL,
        VolumeState.HEAVY,
    ]


def test_equal_thresholds_collapse_the_band_onto_the_boundary() -> None:
    labels = volume.label(np.array([0.99, 1.0, 1.01]), 1.0, 1.0)
    assert list(labels) == [VolumeState.THIN, VolumeState.NORMAL, VolumeState.HEAVY]


def test_an_undefined_ratio_is_labelled_undefined_and_not_folded_into_the_band() -> None:
    assert volume.label(np.array([np.nan]), THIN, HEAVY)[0] == UNDEFINED


def test_thresholds_that_cross_are_refused_rather_than_silently_ordered() -> None:
    with pytest.raises(VolumeError, match="would put a bar in both states"):
        volume.label(np.array([1.0]), 2.0, 0.5)


@pytest.mark.parametrize(("thin", "heavy"), [(-0.1, 1.5), (0.7, -1.0)])
def test_a_negative_threshold_is_refused(thin, heavy) -> None:
    with pytest.raises(VolumeError, match=">= 0"):
        volume.label(np.array([1.0]), thin, heavy)


def test_there_is_no_upper_bound_on_a_threshold() -> None:
    # Relative volume is a ratio to a median, so it is unbounded above -- unlike an
    # efficiency ratio, whose thresholds are refused outside 0..1.
    assert volume.label(np.array([50.0]), 0.7, 100.0)[0] == VolumeState.NORMAL


# -- the mask ------------------------------------------------------------------


def test_a_mask_admits_exactly_the_states_it_names() -> None:
    mask = volume.states_mask([VolumeState.THIN, VolumeState.HEAVY])
    assert volume.states_in(mask) == (VolumeState.THIN, VolumeState.HEAVY)
    assert volume.describe_mask(mask) == "THIN+HEAVY"


def test_the_everything_mask_is_the_three_states_and_nothing_else() -> None:
    assert volume.states_in(ALL_STATES) == tuple(VolumeState)
    assert volume.states_mask(VolumeState) == ALL_STATES


@pytest.mark.parametrize("mask", [0, ALL_STATES + 1, -1])
def test_an_impossible_mask_is_refused(mask) -> None:
    with pytest.raises(VolumeError):
        volume.validate_mask(mask)


# -- the gate, and the one rule it shares with the labels ----------------------


def test_the_gate_and_the_labels_agree_on_every_bar_for_every_mask() -> None:
    """The filter's bit arithmetic and the label must name the same state.

    They agree only while each :class:`VolumeState` sits at the bit position its value names.
    """
    index = stamps(35)
    relative = grid_of(hump(index) + np.arange(index.size) % 31, index, PER_BAR).relative_for(PER_BAR)
    labels = volume.label(relative, THIN, HEAVY)
    for mask in range(1, ALL_STATES + 1):
        admitted = [int(s) for s in volume.states_in(mask)]
        assert np.array_equal(
            volume.gate(relative, mask, THIN, HEAVY),
            np.isin(labels, admitted),
        ), volume.describe_mask(mask)


def test_an_undefined_bar_passes_no_mask_including_the_everything_mask() -> None:
    # The same asymmetry ``timeofday`` and ``regime`` have, and the reason a signal must skip
    # the gate entirely at the default rather than ANDing it.
    index = stamps(12)
    relative = grid_of(np.full(index.size, 250.0), index, PER_BAR).relative_for(PER_BAR)
    undefined = np.isnan(relative)
    assert undefined.any()
    assert not volume.gate(relative, ALL_STATES, THIN, HEAVY)[undefined].any()


# -- the key and the grid ------------------------------------------------------


def test_a_form_that_reads_no_window_drops_it_from_its_key() -> None:
    """So that sweeping the window alongside a per-bar form builds one series, not four."""
    for form in (VolumeForm.PER_BAR, VolumeForm.SESSION_TO_DATE):
        assert volume.key(form, 5, BASELINE) == volume.key(form, 500, BASELINE)
        assert volume.key(form, 5, BASELINE).rolling_bars == NO_ROLLING
    assert volume.key(VolumeForm.ROLLING, 5, BASELINE) != volume.key(VolumeForm.ROLLING, 500, BASELINE)


def test_the_grid_holds_one_deduplicated_row_per_key() -> None:
    index = stamps(12)
    grid = grid_of(np.full(index.size, 250.0), index, PER_BAR, ROLLING, PER_BAR)
    assert grid.keys == (PER_BAR, ROLLING)
    assert len(grid) == index.size
    assert grid.relative.shape == (2, index.size)


def test_a_grid_row_is_the_standalone_series_for_that_key() -> None:
    index = stamps(12)
    trading_day, in_session, bar_of_session = clock(index)
    counts = np.arange(index.size, dtype=np.float64) % 97 + 1.0
    together = volume.volume_grid(counts, trading_day, in_session, bar_of_session, [PER_BAR, ROLLING])
    for key in (PER_BAR, ROLLING):
        alone = volume.volume_grid(counts, trading_day, in_session, bar_of_session, [key])
        np.testing.assert_array_equal(together.relative_for(key), alone.relative_for(key))


def test_reading_a_key_the_grid_was_not_built_for_names_what_it_holds() -> None:
    index = stamps(12)
    grid = grid_of(np.full(index.size, 250.0), index, PER_BAR)
    with pytest.raises(KeyError, match="built for"):
        grid.relative_for(ROLLING)


def test_a_grid_with_no_keys_is_refused() -> None:
    index = stamps(12)
    trading_day, in_session, bar_of_session = clock(index)
    with pytest.raises(VolumeError, match="no volume series supplied"):
        volume.volume_grid(np.zeros(index.size), trading_day, in_session, bar_of_session, [])


def test_a_grid_gate_and_a_grid_label_read_the_same_row() -> None:
    index = stamps(35)
    grid = grid_of(hump(index) + np.arange(index.size) % 31, index, PER_BAR, ROLLING)
    labels = grid.labels_for(ROLLING, THIN, HEAVY)
    gated = grid.gate_for(ROLLING, VolumeState.HEAVY.bit, THIN, HEAVY)
    assert np.array_equal(gated, labels == VolumeState.HEAVY)


def test_the_sessions_are_numbered_in_order_and_a_stray_print_belongs_to_none() -> None:
    index = stamps(12)
    trading_day, in_session, _ = clock(index)
    ids = volume.session_ids(trading_day, in_session)
    assert np.all(ids[~in_session] == UNDEFINED)
    assert np.all(np.diff(ids[in_session]) >= 0)
    assert ids[in_session].max() + 1 == pd.Series(trading_day)[in_session].nunique()


def test_numbering_a_series_with_no_session_gives_every_bar_no_session() -> None:
    days = np.array(["2024-01-08"] * 4, dtype="datetime64[D]")
    assert np.all(volume.session_ids(days, np.zeros(4, dtype=bool)) == UNDEFINED)


# -- the dataset ---------------------------------------------------------------


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


def prepared(**spec: object) -> context.Dataset:
    return context.prepare(
        bars(),
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), **spec),
        bar_minutes=1,
    )


def test_the_volume_series_are_absent_when_nothing_asked_for_them() -> None:
    assert prepared().volumes is None


def test_reading_volume_nobody_declared_names_the_spec_field_to_set() -> None:
    data = prepared()
    reads = (
        lambda: data.volume_gate(PER_BAR, ALL_STATES, THIN, HEAVY),
        lambda: data.volume_values(PER_BAR),
        lambda: data.relative_volume(PER_BAR),
        lambda: data.volume_labels(PER_BAR, THIN, HEAVY),
    )
    for read in reads:
        with pytest.raises(ContextError, match="volume_keys"):
            read()


def test_the_volume_series_are_present_and_counted_when_the_spec_asks() -> None:
    plain = prepared()
    asked = prepared(volume_keys=(PER_BAR,))
    assert asked.volume_values(PER_BAR).shape == (len(asked),)
    assert asked.relative_volume(PER_BAR).shape == (len(asked),)
    assert asked.volume_labels(PER_BAR, THIN, HEAVY).shape == (len(asked),)
    assert asked.volume_gate(PER_BAR, VolumeState.HEAVY.bit, THIN, HEAVY).dtype == np.bool_
    assert asked.nbytes > plain.nbytes, "the series must be counted in what a worker is handed"


def test_asking_for_volume_builds_the_clock_its_baseline_is_taken_over() -> None:
    # Relative volume is defined per bar of session, so the two cannot be requested apart.
    data = prepared(volume_keys=(PER_BAR,))
    assert data.time_of_day is not None
    np.testing.assert_array_equal(data.bar_of_session(), data.time_of_day.bar_of_session)


def test_the_union_of_two_specs_keeps_both_sets_of_keys() -> None:
    merged = ContextSpec(volume_keys=(PER_BAR,)) | ContextSpec(volume_keys=(ROLLING,))
    assert merged.volume_keys == (PER_BAR, ROLLING)
    assert (ContextSpec() | ContextSpec()).volume_keys == ()


# -- the sweepable entry filter ------------------------------------------------

VOLUME_AXES = {
    "volume_filter",
    "volume_form",
    "volume_rolling_bars",
    "volume_baseline_sessions",
    "volume_thin_below",
    "volume_heavy_above",
}


@pytest.mark.parametrize(
    "archetype",
    [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER],
)
def test_every_archetype_can_sweep_every_volume_axis(archetype) -> None:
    assert VOLUME_AXES <= archetype.sweepable, archetype.name


def test_a_grid_asks_for_the_series_only_when_some_combination_narrows_the_states() -> None:
    assert sweep.Grid.of().required_context().volume_keys == ()
    assert sweep.Grid.of(volume_filter=[ALL_STATES]).required_context().volume_keys == ()
    narrowed = sweep.Grid.of(volume_filter=[VolumeState.HEAVY.bit, ALL_STATES])
    assert narrowed.required_context().volume_keys == (PER_BAR,)
    assert len(narrowed) == 2


def test_a_swept_form_reaches_the_context_spec_once_per_distinct_series() -> None:
    grid = sweep.Grid.of(
        volume_filter=[VolumeState.HEAVY.bit],
        volume_form=[int(f) for f in VolumeForm],
        volume_rolling_bars=[15, 30],
    )
    keys = grid.required_context().volume_keys
    assert len(grid) == 6, "three forms against two windows"
    assert keys == (
        PER_BAR,
        volume.key(VolumeForm.ROLLING, 15, BASELINE),
        ROLLING,
        SESSION_TO_DATE,
    ), "the window only multiplies the form that reads it"


@pytest.mark.parametrize("axis", sorted(VOLUME_AXES - {"volume_filter"}))
def test_sweeping_a_volume_axis_that_no_filter_reads_is_refused(axis) -> None:
    """``ALL_STATES`` is 7, so a truthiness test would read the filter as switched on."""
    values = [0.5, 1.5] if axis in {"volume_thin_below", "volume_heavy_above"} else [10, 20]
    with pytest.raises(sweep.SweepError, match="volume_filter"):
        sweep.Grid.of(**{axis: values})


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
        volume_keys=(PER_BAR,),
        needs_ma_values=True,
    )
    data = context.prepare(bars(), spec, bar_minutes=1)
    mask = volume.states_mask([VolumeState.NORMAL, VolumeState.HEAVY])

    unfiltered = signal_fn(data, params_cls(bars_required_to_trade=20))
    filtered = signal_fn(data, params_cls(bars_required_to_trade=20, volume_filter=mask))

    assert unfiltered.any(), "the fixture must produce signals for the narrowing to mean anything"
    assert filtered.sum() < unfiltered.sum()
    assert not (filtered & ~unfiltered).any(), "a filter may only remove signals"
    labels = data.volume_labels(PER_BAR, THIN, HEAVY)
    assert set(labels[filtered]) <= {VolumeState.NORMAL, VolumeState.HEAVY}


def test_the_default_filter_is_exactly_no_filter() -> None:
    """What makes these six fields free to add to a reconciled archetype.

    ``ALL_STATES`` skips the conjunction entirely, so an unfiltered run is bit-for-bit the run
    that predates the fields -- the claim the trade-log gate checks at full scale.
    """
    data = prepared(volume_keys=(PER_BAR,))
    params = DeadCatParams(bars_required_to_trade=20)
    explicit = DeadCatParams(bars_required_to_trade=20, volume_filter=ALL_STATES)
    assert np.array_equal(deadcat_signal(data, params), deadcat_signal(data, explicit))
    pd.testing.assert_frame_equal(
        run_deadcat(data, params),
        run_deadcat(data, explicit),
        check_exact=True,
    )


def test_the_three_volume_filters_partition_every_measured_signal() -> None:
    """Stratification, not selection -- over the bars a baseline could be taken for.

    The warm-up sessions and the out-of-session strays pass no filter, so they are dropped by
    all three arms and the decomposition is of the measured signal rather than of the whole.
    """
    data = prepared(volume_keys=(PER_BAR,))
    whole = deadcat_signal(data, DeadCatParams(bars_required_to_trade=20))
    parts = [deadcat_signal(data, DeadCatParams(bars_required_to_trade=20, volume_filter=s.bit)) for s in VolumeState]
    labels = data.volume_labels(PER_BAR, THIN, HEAVY)
    measured = whole & (labels != UNDEFINED)

    assert whole.any(), "nothing is decomposed if the fixture signals nothing"
    assert sum(int(part.sum()) for part in parts) == int(measured.sum())
    assert np.array_equal(np.logical_or.reduce(parts), measured)
    assert not any((part & (labels == UNDEFINED)).any() for part in parts)


def test_a_filtered_run_enters_only_inside_the_admitted_states() -> None:
    frame = bars()
    data = context.prepare(
        frame,
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), volume_keys=(PER_BAR,)),
        bar_minutes=1,
    )
    mask = volume.states_mask([VolumeState.NORMAL, VolumeState.HEAVY])
    log = run_deadcat(data, DeadCatParams(bars_required_to_trade=20, volume_filter=mask))
    assert not log.empty, "nothing is being checked if the filtered run trades nothing"

    # An entry order lives one bar, so the entry bar is always the one *after* the signal and
    # the filter has to be checked against the bar before each fill, not the fill itself.
    labels = data.volume_labels(PER_BAR, THIN, HEAVY)
    entered = frame.index.get_indexer(pd.DatetimeIndex(log["entry_time"]))
    assert (entered > 0).all(), "every entry must be locatable for the check to mean anything"
    assert set(labels[entered - 1]) <= {VolumeState.NORMAL, VolumeState.HEAVY}


# -- the parameters ------------------------------------------------------------


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_an_impossible_filter_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(VolumeError):
        params_cls(volume_filter=0)
    with pytest.raises(VolumeError):
        params_cls(volume_filter=ALL_STATES + 1)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_a_degenerate_window_form_or_threshold_pair_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(VolumeError, match="one-bar window"):
        params_cls(volume_rolling_bars=1)
    with pytest.raises(VolumeError, match="sessions"):
        params_cls(volume_baseline_sessions=2)
    with pytest.raises(VolumeError, match="unknown volume form"):
        params_cls(volume_form=7)
    with pytest.raises(VolumeError, match="both states"):
        params_cls(volume_thin_below=2.0, volume_heavy_above=0.5)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_rolling_window_is_checked_whatever_the_form(params_cls) -> None:
    # Otherwise a nonsense value rides along inertly until the form is swept onto it.
    with pytest.raises(VolumeError, match="one-bar window"):
        params_cls(volume_form=int(VolumeForm.PER_BAR), volume_rolling_bars=0)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_key_says_which_series_the_combination_reads(params_cls) -> None:
    params = params_cls(volume_form=int(VolumeForm.ROLLING), volume_rolling_bars=45)
    assert params.volume_key == volume.key(VolumeForm.ROLLING, 45, BASELINE)


@pytest.mark.parametrize("params_cls", PARAMS_CLASSES)
def test_the_volume_parameters_reach_the_results_row(params_cls) -> None:
    # They are parameters, so they ride in ``as_dict`` like every other one -- which is what
    # stops two rows of a volume sweep being indistinguishable in the results table.
    row = params_cls(volume_filter=VolumeState.HEAVY.bit, volume_rolling_bars=45).as_dict()
    assert row["volume_filter"] == VolumeState.HEAVY.bit
    assert row["volume_form"] == int(VolumeForm.PER_BAR)
    assert row["volume_rolling_bars"] == 45
    assert row["volume_baseline_sessions"] == BASELINE
    assert row["volume_thin_below"] == THIN
    assert row["volume_heavy_above"] == HEAVY
