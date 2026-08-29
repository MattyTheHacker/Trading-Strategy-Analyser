"""Time-of-day labelling tests: session phase, bar of session, and the entry filter.

The two things worth pinning hardest are the ones whose failures look like noise rather
than like errors. **Eastern time**, because a UTC-bucketed cash open is split across two
buckets for half the year and still returns a plausible-looking table. And the
**end-of-bar convention**, because a boundary one minute out is invisible in aggregate and
wrong at exactly the edges the labels exist to isolate.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, resample, sessions, sweep, timeofday
from nqbt.context import ContextError, ContextSpec
from nqbt.sim.crossover import crossover_signal
from nqbt.sim.pullback import pullback_signal
from nqbt.sim.runner import deadcat_signal, run_deadcat
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams
from nqbt.timeofday import ALL_PHASES, OUT_OF_SESSION, SessionPhase

CASH_OPEN = SessionPhase.CASH_OPEN


def idx(*stamps: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(stamps), utc=True))


def session_index(open_utc: str, minutes: int = 1380) -> pd.DatetimeIndex:
    """One full session's 1-minute bars, stamped end-of-bar from its first."""
    return pd.date_range(open_utc, periods=minutes, freq="min", tz="UTC")


# The two 2024 US transitions. The session that opens on each of these Sundays is the first
# one at the new offset -- no session spans a transition, because the market is shut.
SPRING_FORWARD_OPEN = "2024-03-10 22:01"  # 18:01 EDT (-4)
FALL_BACK_OPEN = "2024-11-03 23:01"  # 18:01 EST (-5)
WINTER_OPEN = "2024-01-07 23:01"  # 18:01 EST (-5)


# -- the phase boundaries ------------------------------------------------------


def test_every_phase_covers_exactly_the_eastern_hours_it_is_named_for() -> None:
    stamps = session_index(SPRING_FORWARD_OPEN)
    eastern = stamps.tz_convert(sessions.EASTERN)
    phase = timeofday.classify(stamps).phase

    spans = {
        SessionPhase.OVERNIGHT: ("18:01", "03:00"),
        SessionPhase.LONDON: ("03:01", "07:00"),
        SessionPhase.PRE_OPEN: ("07:01", "09:30"),
        SessionPhase.CASH_OPEN: ("09:31", "10:30"),
        SessionPhase.MIDDAY: ("10:31", "14:00"),
        SessionPhase.AFTERNOON: ("14:01", "16:00"),
        SessionPhase.CLOSE: ("16:01", "17:00"),
    }
    for expected, (first, last) in spans.items():
        stamped = eastern[phase == expected]
        assert stamped[0].strftime("%H:%M") == first, expected.name
        assert stamped[-1].strftime("%H:%M") == last, expected.name

    assert set(np.unique(phase)) == set(SessionPhase), "a session must use every phase"


def test_a_bar_is_labelled_by_the_minute_it_covers_not_the_minute_it_is_stamped() -> None:
    # Stamps are end-of-bar, so 09:30 ET covers 09:29-09:30 and is still the pre-open. The
    # first bar of the cash open is the one stamped 09:31. Off by one here is the M13 trap.
    phase = timeofday.classify(idx("2024-03-11 13:30", "2024-03-11 13:31")).phase
    assert list(phase) == [SessionPhase.PRE_OPEN, SessionPhase.CASH_OPEN]


def test_phase_ordering_matches_the_session_clock() -> None:
    # The integer values are the ordering, which is what lets a stratification sort by them.
    phase = timeofday.classify(session_index(SPRING_FORWARD_OPEN)).phase
    assert np.all(np.diff(phase) >= 0)


# -- Eastern time, not UTC -----------------------------------------------------


@pytest.mark.parametrize(
    ("open_utc", "utc_hour_of_cash_open"),
    [(WINTER_OPEN, 14), (SPRING_FORWARD_OPEN, 13)],
)
def test_the_cash_open_is_one_bucket_on_both_sides_of_a_dst_transition(
    open_utc,
    utc_hour_of_cash_open,
) -> None:
    """The pin the whole module exists for.

    The same Eastern hour lands in :attr:`SessionPhase.CASH_OPEN` in both sessions, while
    its **UTC hour differs by one** -- so a UTC-bucketed version of this label would split
    the most distinctive hour of the day across two buckets for half the year and read as
    noise rather than as a bug.
    """
    stamps = session_index(open_utc)
    phase = timeofday.classify(stamps).phase
    eastern = stamps.tz_convert(sessions.EASTERN)

    cash = phase == SessionPhase.CASH_OPEN
    assert cash.sum() == 60
    assert eastern[cash][0].strftime("%H:%M") == "09:31"
    assert eastern[cash][-1].strftime("%H:%M") == "10:30"
    # The premise: UTC really has moved, so the test above is not a tautology.
    assert set(stamps[cash].hour) <= {utc_hour_of_cash_open, utc_hour_of_cash_open + 1}
    assert stamps[cash][0].hour == utc_hour_of_cash_open


def test_bucketing_on_utc_would_split_the_cash_open_and_this_does_not() -> None:
    """States the failure being avoided rather than only the behaviour that avoids it."""
    winter = session_index(WINTER_OPEN)
    summer = session_index(SPRING_FORWARD_OPEN)

    winter_cash = winter[timeofday.classify(winter).phase == SessionPhase.CASH_OPEN]
    summer_cash = summer[timeofday.classify(summer).phase == SessionPhase.CASH_OPEN]

    # Same Eastern minutes on both sides...
    assert [t.strftime("%H:%M") for t in winter_cash.tz_convert(sessions.EASTERN)] == [
        t.strftime("%H:%M") for t in summer_cash.tz_convert(sessions.EASTERN)
    ]
    # ...and different UTC minutes, which is what a UTC bucket would have separated.
    assert {t.strftime("%H:%M") for t in winter_cash} != {t.strftime("%H:%M") for t in summer_cash}


def test_both_2024_transitions_are_covered_not_only_the_spring_one() -> None:
    for open_utc in (SPRING_FORWARD_OPEN, FALL_BACK_OPEN):
        stamps = session_index(open_utc)
        tod = timeofday.classify(stamps)
        assert set(np.unique(tod.phase)) == set(SessionPhase), open_utc
        assert tod.bar_of_session[0] == 0
        assert tod.bar_of_session[-1] == 1379


# -- bar of session ------------------------------------------------------------


def test_bar_of_session_runs_from_zero_to_the_session_length() -> None:
    tod = timeofday.classify(session_index(WINTER_OPEN))
    assert tod.bar_minutes == 1
    assert list(tod.bar_of_session[:3]) == [0, 1, 2]
    assert tod.bar_of_session[-1] == timeofday.session_minutes() - 1


def test_bar_of_session_is_clock_derived_so_a_missing_bar_does_not_shift_it() -> None:
    """The property #41's relative volume depends on.

    An ordinal count of the bars actually present would renumber everything after a hole,
    so index ``k`` would mean a different time of day in different sessions -- which is the
    exact confound relative volume is meant to divide out.
    """
    full = session_index(WINTER_OPEN)
    holed = full.delete([10, 11, 12])

    labels = dict(zip(full, timeofday.classify(full).bar_of_session, strict=True))
    for stamp, value in zip(holed, timeofday.classify(holed).bar_of_session, strict=True):
        assert value == labels[stamp]


def test_bar_of_session_is_the_resample_bucket_at_the_same_resolution() -> None:
    # One definition of the session clock, not two: a 5-minute bar's index is the index of
    # the 5-minute bucket it is.
    stamps = session_index(WINTER_OPEN)[4::5]
    bucket, _ = resample.bucket_index(stamps, 5)
    assert np.array_equal(timeofday.classify(stamps, bar_minutes=5).bar_of_session, bucket)


def test_bar_size_is_inferred_from_the_index_when_not_given() -> None:
    assert timeofday.infer_bar_minutes(session_index(WINTER_OPEN)) == 1
    assert timeofday.infer_bar_minutes(session_index(WINTER_OPEN)[4::5]) == 5
    # The mode, not the minimum or the mean: the maintenance break and the archive's holes
    # are gaps between sessions, not bar sizes.
    two_sessions = session_index(WINTER_OPEN).append(session_index("2024-01-08 23:01"))
    assert timeofday.infer_bar_minutes(two_sessions) == 1
    assert timeofday.infer_bar_minutes(idx("2024-01-08 00:00")) == 1


def test_a_coarse_resolution_gives_fewer_bars_of_session() -> None:
    stamps = session_index(WINTER_OPEN)[14::15]
    tod = timeofday.classify(stamps, bar_minutes=15)
    assert tod.bar_minutes == 15
    assert list(tod.bar_of_session[:3]) == [0, 1, 2]
    assert tod.bar_of_session[-1] == timeofday.session_minutes() // 15 - 1


# -- out of session ------------------------------------------------------------


@pytest.mark.parametrize(
    ("stamp", "why"),
    [
        ("2024-03-09 15:44:00", "Saturday morning stray print"),
        ("2024-03-11 21:30:00", "inside the 17:00-18:00 maintenance break (17:30 EDT)"),
    ],
)
def test_a_bar_outside_any_session_gets_no_phase_and_no_index(stamp, why) -> None:
    tod = timeofday.classify(idx(stamp))
    assert tod.phase[0] == OUT_OF_SESSION, why
    assert tod.bar_of_session[0] == OUT_OF_SESSION, why
    assert tod.phase_bits[0] == 0, why


def test_an_out_of_session_bar_passes_no_mask_including_all_phases() -> None:
    # Which is why an archetype skips the gate entirely at ALL_PHASES rather than ANDing
    # it: the no-op has to be *no filter*, or switching the filter on to "every phase"
    # would quietly drop the strays and move a result.
    tod = timeofday.classify(idx("2024-03-09 15:44:00"))
    assert not tod.gate(ALL_PHASES)[0]
    assert not tod.gate(CASH_OPEN.bit)[0]


# -- masks ---------------------------------------------------------------------


def test_all_phases_admits_every_phase_and_nothing_else() -> None:
    assert timeofday.phases_in(ALL_PHASES) == tuple(SessionPhase)
    assert timeofday.phases_mask(SessionPhase) == ALL_PHASES


def test_a_mask_round_trips_through_its_phases() -> None:
    mask = timeofday.phases_mask([CASH_OPEN, SessionPhase.MIDDAY])
    assert timeofday.phases_in(mask) == (CASH_OPEN, SessionPhase.MIDDAY)
    assert timeofday.describe_mask(mask) == "CASH_OPEN+MIDDAY"
    assert mask == CASH_OPEN.bit | SessionPhase.MIDDAY.bit


@pytest.mark.parametrize("mask", [0, -1, ALL_PHASES + 1, 1 << 12])
def test_an_impossible_mask_raises_rather_than_silently_admitting_nothing(mask) -> None:
    with pytest.raises(timeofday.TimeOfDayError):
        timeofday.validate_mask(mask)


def test_phase_boundaries_are_validated_against_the_template_they_are_read_with() -> None:
    # A template opening somewhere else reorders the boundaries relative to its own open,
    # and a set that no longer ascends would mislabel whole phases through searchsorted
    # without raising anything.
    shifted = sessions.SessionTemplate(name="noon open", open_time=pd.Timestamp("12:00").time())
    with pytest.raises(timeofday.TimeOfDayError):
        timeofday.phase_start_minutes(shifted)


def test_the_forced_exit_phase_is_named_so_a_caller_can_exclude_it() -> None:
    # #16's flatten falls in the last phase by construction, so its exits are decided by
    # the clock. Naming it is what lets a stratification say so rather than report it as a
    # market finding.
    assert timeofday.FORCED_EXIT_PHASE is SessionPhase.CLOSE
    stamps = session_index(WINTER_OPEN)
    tod = timeofday.classify(stamps)
    flat = sessions.force_flat_mask(sessions.classify(stamps))
    assert set(tod.phase[flat]) == {timeofday.FORCED_EXIT_PHASE}


# -- what prepare builds -------------------------------------------------------


def bars(n: int = 1400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    stamps = session_index(WINTER_OPEN, n)
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


def test_time_of_day_is_absent_when_nothing_asked_for_it() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    assert data.time_of_day is None


def test_reading_time_of_day_nobody_declared_names_the_spec_field_to_set() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    for read in (lambda: data.phase_gate(ALL_PHASES), data.phase_values, data.bar_of_session):
        with pytest.raises(ContextError, match="needs_time_of_day"):
            read()


def test_time_of_day_is_present_and_counted_when_the_spec_asks() -> None:
    plain = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    asked = context.prepare(
        bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_time_of_day=True)
    )
    assert asked.phase_values().shape == (len(asked),)
    assert asked.bar_of_session().shape == (len(asked),)
    assert asked.phase_gate(CASH_OPEN.bit).dtype == np.bool_
    assert asked.nbytes > plain.nbytes, "the labels must be counted in what a worker is handed"


def test_prepare_takes_the_bar_size_it_is_given_rather_than_inferring_one() -> None:
    frame = bars()
    stated = context.prepare(frame, ContextSpec(needs_time_of_day=True), bar_minutes=5)
    assert stated.time_of_day is not None
    assert stated.time_of_day.bar_minutes == 5


def test_the_union_of_two_specs_keeps_the_time_of_day_request() -> None:
    asked = ContextSpec(needs_time_of_day=True)
    assert (asked | ContextSpec()).needs_time_of_day
    assert (ContextSpec() | asked).needs_time_of_day
    assert not (ContextSpec() | ContextSpec()).needs_time_of_day


# -- the sweepable entry filter ------------------------------------------------


@pytest.mark.parametrize(
    "archetype",
    [archetypes.DEADCATBOUNCE, archetypes.PULLBACKANDGO, archetypes.EMACROSSOVER],
)
def test_every_archetype_can_sweep_the_phase_filter(archetype) -> None:
    assert "phase_filter" in archetype.sweepable, archetype.name


def test_a_grid_asks_for_the_labels_only_when_some_combination_narrows_the_phases() -> None:
    assert not sweep.Grid.of().required_context().needs_time_of_day
    assert not sweep.Grid.of(phase_filter=[ALL_PHASES]).required_context().needs_time_of_day
    narrowed = sweep.Grid.of(phase_filter=[CASH_OPEN.bit, ALL_PHASES])
    assert narrowed.required_context().needs_time_of_day
    assert len(narrowed) == 2


@pytest.mark.parametrize(
    ("signal_fn", "params_cls"),
    [
        (deadcat_signal, DeadCatParams),
        (pullback_signal, PullBackAndGoParams),
        (crossover_signal, EmaCrossoverParams),
    ],
)
def test_the_filter_narrows_a_signal_to_the_phases_it_admits(signal_fn, params_cls) -> None:
    frame = bars()
    spec = ContextSpec(
        ma_keys=conditions.ma_keys(ema=(9, 11, 21), sma=(60, 80, 155, 175)),
        atr_periods=(14,),
        needs_time_of_day=True,
        needs_ma_values=True,
    )
    data = context.prepare(frame, spec)

    unfiltered = signal_fn(data, params_cls(bars_required_to_trade=20))
    mask = timeofday.phases_mask([CASH_OPEN, SessionPhase.MIDDAY])
    filtered = signal_fn(data, params_cls(bars_required_to_trade=20, phase_filter=mask))

    assert unfiltered.any(), "the fixture must produce signals for the narrowing to mean anything"
    assert filtered.sum() < unfiltered.sum()
    assert not (filtered & ~unfiltered).any(), "a filter may only remove signals"
    assert set(data.phase_values()[filtered]) <= {CASH_OPEN, SessionPhase.MIDDAY}


def test_the_default_filter_is_exactly_no_filter() -> None:
    """What makes this field free to add to a reconciled archetype.

    ``ALL_PHASES`` skips the conjunction entirely, so an unfiltered run is bit-for-bit the
    run that predates the field -- which is the claim the trade-log gate checks at full
    scale and this one pins in a test.
    """
    frame = bars()
    data = context.prepare(
        frame,
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), needs_time_of_day=True),
    )
    params = DeadCatParams(bars_required_to_trade=20)
    assert np.array_equal(
        deadcat_signal(data, params),
        deadcat_signal(data, DeadCatParams(bars_required_to_trade=20, phase_filter=ALL_PHASES)),
    )
    # And the whole simulation, not only the signal.
    pd.testing.assert_frame_equal(
        run_deadcat(data, params),
        run_deadcat(data, DeadCatParams(bars_required_to_trade=20, phase_filter=ALL_PHASES)),
        check_exact=True,
    )


def test_a_filtered_run_enters_only_inside_the_admitted_phases() -> None:
    frame = bars()
    data = context.prepare(
        frame,
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), needs_time_of_day=True),
    )
    mask = timeofday.phases_mask([SessionPhase.OVERNIGHT, SessionPhase.LONDON])
    log = run_deadcat(data, DeadCatParams(bars_required_to_trade=20, phase_filter=mask))
    assert not log.empty, "nothing is being checked if the filtered run trades nothing"

    # The entry bar is the one *after* the signal, so the check is on the signal's phase.
    phase = pd.Series(data.phase_values(), index=frame.index)
    signalled = phase.reindex(pd.DatetimeIndex(log["entry_time"]), method="ffill")
    assert set(signalled) <= {SessionPhase.OVERNIGHT, SessionPhase.LONDON}


@pytest.mark.parametrize("params_cls", [DeadCatParams, PullBackAndGoParams, EmaCrossoverParams])
def test_an_impossible_filter_is_refused_at_construction(params_cls) -> None:
    with pytest.raises(timeofday.TimeOfDayError):
        params_cls(phase_filter=0)
    with pytest.raises(timeofday.TimeOfDayError):
        params_cls(phase_filter=ALL_PHASES + 1)


def test_the_filter_reaches_the_results_row() -> None:
    # It is a parameter, so it rides in ``as_dict`` like every other one -- which is what
    # stops two rows of a phase sweep being indistinguishable in the results table.
    assert DeadCatParams(phase_filter=CASH_OPEN.bit).as_dict()["phase_filter"] == CASH_OPEN.bit


def test_a_session_too_short_for_the_last_phase_raises() -> None:
    # Every boundary still ascends, so this is the check the ascending one cannot make: a
    # template whose close arrives before the last phase begins would label bars into a
    # phase the session never reaches.
    stub = sessions.SessionTemplate(name="three-hour session", close_time=pd.Timestamp("21:00").time())
    with pytest.raises(timeofday.TimeOfDayError, match="past the"):
        timeofday.phase_start_minutes(stub)


def test_boundaries_that_stop_ascending_raise_rather_than_mislabel(monkeypatch) -> None:
    monkeypatch.setattr(
        timeofday,
        "PHASE_STARTS",
        (
            (SessionPhase.OVERNIGHT, pd.Timestamp("18:00").time()),
            (SessionPhase.LONDON, pd.Timestamp("18:00").time()),
        ),
    )
    with pytest.raises(timeofday.TimeOfDayError, match="ascend"):
        timeofday.phase_start_minutes()


def test_a_bar_size_below_one_minute_raises() -> None:
    with pytest.raises(timeofday.TimeOfDayError, match="bar_minutes"):
        timeofday.bar_index_from_minutes(np.array([1, 2]), 0)


def test_inferring_a_bar_size_from_repeated_stamps_falls_back_to_one_minute() -> None:
    assert timeofday.infer_bar_minutes(idx("2024-01-08 00:00", "2024-01-08 00:00")) == 1


def test_the_labels_are_aligned_to_the_index_they_came_from() -> None:
    stamps = session_index(WINTER_OPEN)
    assert len(timeofday.classify(stamps)) == len(stamps)


def test_the_seven_single_phase_filters_partition_the_unfiltered_signal() -> None:
    """Stratification, not selection: every signal lands in exactly one phase.

    The property that makes "profit factor by phase" a decomposition of the whole rather
    than seven overlapping subsets whose trade counts do not add up. Measured on real MNQ
    too -- see ``docs/roadmap.md`` § M10.4.
    """
    data = context.prepare(
        bars(),
        ContextSpec(ma_keys=conditions.ma_keys(ema=(11,), sma=(80, 155)), needs_time_of_day=True),
    )
    whole = deadcat_signal(data, DeadCatParams(bars_required_to_trade=20))
    parts = [
        deadcat_signal(data, DeadCatParams(bars_required_to_trade=20, phase_filter=p.bit))
        for p in SessionPhase
    ]
    assert sum(int(part.sum()) for part in parts) == int(whole.sum())
    assert np.array_equal(np.logical_or.reduce(parts), whole)
