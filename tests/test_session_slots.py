"""The half-hour slot filter: the fine cut of the session clock, on every archetype.

A slot is labelled the way a phase is, by the minute a bar's body occupies, in Eastern time, and
every phase is a run of whole slots -- ``docs/nt8-fidelity.md``, "Entries in one half-hour slot of
the session".
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import time
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, sessions, sweep, timeofday
from nqbt.archetypes import Tier2Status
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, active_context_filters
from nqbt.timeofday import ALL_SLOTS, SLOT_MINUTES, SessionPhase
from tests.test_confluence_sizing import EVERY_CLASS, TRADING, bars, prepared
from tools import campaign_sweep
from tools.campaign_sweep import CASH_PHASES, EVERY_DIMENSION, SLOT, STRATUM_SETS, check_slot_request, strata

if TYPE_CHECKING:
    from nqbt.archetypes import ArchetypeParams

__all__ = ["bars"]

WINTER_OPEN = "2024-01-07 23:00"
"""18:00 EST, the open of a session at UTC-5."""

SUMMER_OPEN = "2024-03-10 22:00"
"""18:00 EDT, the first session after the spring transition, at UTC-4."""

CAMPAIGN_BAR_SIZES = (1, 2, 5, 10, 15)

EVERY_OTHER_SLOT = sum(timeofday.slot_bit(slot) for slot in range(0, timeofday.SLOTS_PER_SESSION, 2))
"""Half the session in alternate slots, so a filtered signal both keeps and drops bars."""


def session_bars(open_utc: str, bar_minutes: int) -> pd.DatetimeIndex:
    """Build one full session's bars at ``bar_minutes``, stamped end-of-bar from the open."""
    start = pd.Timestamp(open_utc, tz="UTC") + pd.Timedelta(minutes=bar_minutes)

    return pd.date_range(start, periods=timeofday.session_minutes() // bar_minutes, freq=f"{bar_minutes}min")


def eastern(stamps: pd.DatetimeIndex) -> list[str]:
    return [f"{stamp:%H:%M}" for stamp in stamps.tz_convert(sessions.EASTERN)]


# -- the slots ---------------------------------------------------------------------------------


def test_a_session_is_forty_six_slots_from_the_open() -> None:
    assert timeofday.SLOTS_PER_SESSION == 46
    assert ALL_SLOTS == (1 << 46) - 1
    assert timeofday.slot_start(0) == time(18, 0)
    assert timeofday.slot_start(45) == time(16, 30)


def test_the_cash_hours_are_thirteen_slots_from_the_cash_open_to_the_cash_close() -> None:
    starts = [
        f"{timeofday.slot_start(slot):%H%M}"
        for slot in timeofday.slots_in(timeofday.phase_slots(CASH_PHASES))
    ]
    assert starts == [f"{hour:02d}{minute:02d}" for hour in range(9, 16) for minute in (0, 30)][1:]
    assert len(starts) == 13


def test_every_phase_is_a_run_of_whole_slots_and_together_they_are_the_session() -> None:
    covered = 0
    for phase in SessionPhase:
        slots = timeofday.slots_in(timeofday.phase_slots(phase.bit))
        assert slots == tuple(range(slots[0], slots[-1] + 1))
        assert not covered & timeofday.phase_slots(phase.bit), "two phases claim one slot"
        covered |= timeofday.phase_slots(phase.bit)

    assert covered == ALL_SLOTS


def test_minutes_past_the_open_count_from_the_template_open_across_midnight() -> None:
    assert timeofday.minutes_past_open(time(18, 0)) == 0
    assert timeofday.minutes_past_open(time(9, 30)) == 930
    assert timeofday.minutes_past_open(time(17, 0)) == 1380


@pytest.mark.parametrize("slot", [-1, 46])
def test_a_slot_outside_the_session_has_no_bit(slot: int) -> None:
    with pytest.raises(timeofday.TimeOfDayError, match="outside the session"):
        timeofday.slot_bit(slot)


@pytest.mark.parametrize("mask", [0, -1, ALL_SLOTS + 1, 1 << 46])
def test_an_impossible_slot_mask_raises_rather_than_silently_admitting_nothing(mask: int) -> None:
    with pytest.raises(timeofday.TimeOfDayError):
        timeofday.validate_slot_mask(mask)


def test_a_slot_mask_round_trips_through_its_slots() -> None:
    mask = timeofday.slot_bit(3) | timeofday.slot_bit(31) | timeofday.slot_bit(45)
    assert timeofday.slots_in(mask) == (3, 31, 45)


def test_a_phase_boundary_inside_a_slot_is_refused_rather_than_split(monkeypatch: pytest.MonkeyPatch) -> None:
    starts = dict(timeofday.PHASE_STARTS) | {SessionPhase.CASH_OPEN: time(9, 45)}
    monkeypatch.setattr(timeofday, "PHASE_STARTS", tuple(starts.items()))
    with pytest.raises(timeofday.TimeOfDayError, match="slot boundary"):
        timeofday.phase_slots(SessionPhase.MIDDAY.bit)


# -- the gate ----------------------------------------------------------------------------------


@pytest.mark.parametrize("bar_minutes", CAMPAIGN_BAR_SIZES)
@pytest.mark.parametrize("open_utc", [WINTER_OPEN, SUMMER_OPEN])
def test_every_phase_gate_is_the_slot_gate_over_that_phases_slots(open_utc: str, bar_minutes: int) -> None:
    """The phase labels are what the entry window reconciled against, so the slots inherit that."""
    clock = timeofday.classify(session_bars(open_utc, bar_minutes), bar_minutes=bar_minutes)
    for phase in SessionPhase:
        assert np.array_equal(clock.slot_gate(timeofday.phase_slots(phase.bit)), clock.gate(phase.bit)), phase


@pytest.mark.parametrize("bar_minutes", CAMPAIGN_BAR_SIZES)
def test_the_slots_partition_the_session(bar_minutes: int) -> None:
    clock = timeofday.classify(session_bars(WINTER_OPEN, bar_minutes), bar_minutes=bar_minutes)
    hits = sum(
        clock.slot_gate(timeofday.slot_bit(slot)).astype(int) for slot in range(timeofday.SLOTS_PER_SESSION)
    )
    assert np.array_equal(hits, np.ones(len(clock), dtype=int))


@pytest.mark.parametrize(
    ("bar_minutes", "last_of_0930", "first_of_1000"),
    [(1, "10:00", "10:01"), (5, "10:00", "10:05"), (15, "10:00", "10:15")],
)
def test_a_bar_belongs_to_the_slot_its_body_falls_in(
    bar_minutes: int, last_of_0930: str, first_of_1000: str
) -> None:
    """Stamped at its close, so the bar stamped 10:00 is the 09:30 slot's last, as under the phases."""
    stamps = session_bars(WINTER_OPEN, bar_minutes)
    clock = timeofday.classify(stamps, bar_minutes=bar_minutes)
    in_0930 = eastern(stamps[clock.slot_gate(timeofday.slot_bit(31))])
    in_1000 = eastern(stamps[clock.slot_gate(timeofday.slot_bit(32))])
    assert in_0930[-1] == last_of_0930
    assert in_1000[0] == first_of_1000


def test_a_slot_is_the_same_eastern_half_hour_on_both_sides_of_a_dst_transition() -> None:
    picked = []
    for open_utc in (WINTER_OPEN, SUMMER_OPEN):
        stamps = session_bars(open_utc, 1)
        picked.append(stamps[timeofday.classify(stamps, bar_minutes=1).slot_gate(timeofday.slot_bit(31))])

    winter, summer = picked
    assert (
        eastern(winter)
        == eastern(summer)
        == [f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(571, 601)]
    )
    assert [stamp.hour for stamp in winter] != [stamp.hour for stamp in summer], "the UTC hours must differ"


def test_an_out_of_session_bar_passes_no_slot_including_all_slots() -> None:
    stamps = pd.DatetimeIndex(pd.to_datetime(["2024-01-13 15:00", "2024-01-08 15:00"], utc=True))
    clock = timeofday.classify(stamps, bar_minutes=1)
    assert clock.slot_gate(ALL_SLOTS).tolist() == [False, True]


@pytest.mark.parametrize("bar_minutes", [4, 20, 60])
def test_a_bar_size_straddling_the_slots_is_refused(bar_minutes: int) -> None:
    assert SLOT_MINUTES % bar_minutes
    clock = timeofday.classify(session_bars(WINTER_OPEN, bar_minutes), bar_minutes=bar_minutes)
    with pytest.raises(timeofday.TimeOfDayError, match="straddle"):
        clock.slot_gate(timeofday.slot_bit(31))


# -- the parameter -----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_every_parameter_class_carries_the_slot_filter_off(cls: type[ArchetypeParams]) -> None:
    assert cls().slot_filter == ALL_SLOTS


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize("mask", [0, ALL_SLOTS + 1])
def test_an_impossible_slot_filter_is_refused_at_construction(cls: type[ArchetypeParams], mask: int) -> None:
    with pytest.raises(timeofday.TimeOfDayError):
        cls(slot_filter=mask)  # type: ignore[call-arg]  # every params class takes its fields as keywords


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_a_slot_outside_every_admitted_phase_is_refused_rather_than_trading_nothing(
    cls: type[ArchetypeParams],
) -> None:
    cash_open = timeofday.slot_bit(31)
    assert cls(slot_filter=cash_open, phase_filter=SessionPhase.CASH_OPEN.bit).slot_filter == cash_open  # type: ignore[call-arg]  # every params class takes its fields as keywords
    with pytest.raises(timeofday.TimeOfDayError, match="trade nothing"):
        cls(slot_filter=cash_open, phase_filter=SessionPhase.OVERNIGHT.bit)  # type: ignore[call-arg]  # every params class takes its fields as keywords


def test_a_counted_slot_outside_the_phase_is_one_gate_of_several_and_not_refused() -> None:
    """At least one of the phase and the slot is a bar in either, so it trades."""
    either = EmaCrossoverParams(
        phase_filter=SessionPhase.CASH_OPEN.bit, slot_filter=timeofday.slot_bit(40), confluence_required=1
    )
    assert either.confluence_required == 1
    with pytest.raises(timeofday.TimeOfDayError, match="trade nothing"):
        EmaCrossoverParams(phase_filter=SessionPhase.CASH_OPEN.bit, slot_filter=timeofday.slot_bit(40))


def test_the_slot_filter_counts_as_an_active_filter() -> None:
    assert active_context_filters(DeadCatParams()) == 0
    assert active_context_filters(DeadCatParams(slot_filter=timeofday.slot_bit(31))) == 1


def test_a_grid_asks_for_the_clock_only_when_some_combination_narrows_the_slots() -> None:
    assert not sweep.Grid.of(slot_filter=[ALL_SLOTS]).required_context().needs_time_of_day
    narrowed = sweep.Grid.of(slot_filter=[timeofday.slot_bit(31), ALL_SLOTS])
    assert narrowed.required_context().needs_time_of_day
    assert len(narrowed) == 2


def test_a_slot_filtered_row_leaves_the_reconciled_port() -> None:
    """No NinjaScript as ported has the filter, so a combination using it is not the port any more."""
    for archetype in (archetypes.DEADCATBOUNCE, archetypes.INSIDEBARTRAILING):
        assert archetype.tier2 is Tier2Status.RECONCILED
        narrowed = dataclasses.replace(archetype.params_cls(), slot_filter=timeofday.slot_bit(31))
        assert archetype.tier2_for(narrowed) is Tier2Status.TIER1_ONLY


# -- the signal --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_slot_filter_keeps_exactly_the_signals_in_its_slots(bars: pd.DataFrame, name: str) -> None:
    archetype = archetypes.get(name)
    filtered = dataclasses.replace(TRADING[name], slot_filter=EVERY_OTHER_SLOT)
    data = prepared(bars, filtered, archetype)
    unfiltered = archetype.signal(data, TRADING[name])
    expected = unfiltered & data.slot_gate(EVERY_OTHER_SLOT)

    assert np.array_equal(archetype.signal(data, filtered), expected)
    assert expected.any()
    assert expected.sum() < unfiltered.sum()


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_default_slot_filter_reads_no_clock(bars: pd.DataFrame, name: str) -> None:
    """At every slot the gate is skipped, so a dataset without the clock still signals."""
    archetype = archetypes.get(name)
    data = prepared(bars, TRADING[name], archetype)
    assert TRADING[name].slot_filter == ALL_SLOTS
    assert data.time_of_day is None
    assert archetype.signal(data, TRADING[name]).any()


def test_the_cash_slots_partition_the_cash_phases_signal(bars: pd.DataFrame) -> None:
    """Stratification, not selection: every cash-hours signal lands in exactly one slot."""
    archetype = archetypes.DEADCATBOUNCE
    cash = dataclasses.replace(TRADING["DeadCatBounce"], phase_filter=CASH_PHASES)
    data = prepared(bars, cash, archetype)
    whole = archetype.signal(data, cash)
    parts = [
        archetype.signal(
            data, dataclasses.replace(TRADING["DeadCatBounce"], slot_filter=axes["slot_filter"][0])
        )
        for _, axes in strata(SLOT)
    ]
    assert whole.any()
    assert sum(int(part.sum()) for part in parts) == int(whole.sum())
    assert np.array_equal(np.logical_or.reduce(parts), whole)


# -- the stratum -------------------------------------------------------------------------------


def test_the_slot_stratum_is_the_thirteen_cash_slots_named_by_their_eastern_start() -> None:
    cells = list(strata(SLOT))
    assert [name for name, _ in cells] == [
        f"slot={timeofday.slot_start(slot):%H%M}"
        for slot in timeofday.slots_in(timeofday.phase_slots(CASH_PHASES))
    ]
    assert cells[0][0] == "slot=0930"
    assert cells[-1][0] == "slot=1530"
    assert all(len(axes["slot_filter"]) == 1 for _, axes in cells)


@pytest.mark.parametrize("resolutions", [[20], [2, 5, 60]])
def test_a_slot_run_at_a_bar_size_straddling_the_slots_is_refused_before_it_starts(
    resolutions: list[int],
) -> None:
    with pytest.raises(SystemExit, match="straddle"):
        check_slot_request(argparse.Namespace(strata=SLOT, resolutions=resolutions))


def test_the_sweep_refuses_a_straddling_slot_run_before_it_plans_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def planned(_: argparse.Namespace) -> int:
        msg = "the sweep got past its checks"
        raise AssertionError(msg)

    monkeypatch.setattr(campaign_sweep, "planned_combinations", planned)
    with pytest.raises(SystemExit, match="straddle"):
        campaign_sweep.main(["campaign_sweep.py", "--split", "--strata", SLOT, "--resolutions", "5", "20"])


def test_a_slot_run_at_the_campaign_bar_sizes_and_other_strata_at_any_go_ahead() -> None:
    check_slot_request(argparse.Namespace(strata=SLOT, resolutions=list(CAMPAIGN_BAR_SIZES)))
    check_slot_request(argparse.Namespace(strata="phase", resolutions=[20, 60]))


def test_the_slot_stratum_stays_out_of_every_set_already_run_or_pre_registered() -> None:
    """A finer cut of the phases' clock, so ``all`` and every every-dimension set leave it out."""
    assert SLOT not in EVERY_DIMENSION
    assert STRATUM_SETS[SLOT] == (SLOT,)
    assert [name for name, sets in STRATUM_SETS.items() if SLOT in sets] == [SLOT]
