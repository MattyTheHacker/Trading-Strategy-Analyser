"""Tests for the passed-target probe reader.

Each price check runs against three readings -- the measured rule, the target's own price and the
open -- and each trial set holds a long and a short.
"""

import itertools
import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt.sim import bracket
from nqbt.trades import EXIT_STOP
from tools import reconcile_passed_target as rpt
from tools.reconcile_order_lifetime import EXECUTION, ORDER_UPDATE, SUBMIT, read_run

if TYPE_CHECKING:
    from pathlib import Path

EVENT_COLUMNS = [
    "kind",
    "trial",
    "bar",
    "bar_utc",
    "bar_local",
    "signal_name",
    "from_entry_signal",
    "order_id",
    "order_action",
    "order_type",
    "stop_price",
    "limit_price",
    "quantity",
    "filled",
    "average_fill_price",
    "execution_price",
    "order_state",
    "event_utc",
    "event_local",
    "error",
    "comment",
    "is_last_bar_of_session",
]

BAR_COLUMNS = [
    "bar",
    "utc",
    "local",
    "is_first_bar_of_session",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "market_position",
    "position_quantity",
    "is_last_bar_of_session",
]

CONFIG = {
    "stage": "Terminated",
    "is_exit_on_session_close_strategy": True,
    "exit_on_session_close_seconds": 30,
    "entries_per_direction": 1,
    "entry_handling": "AllEntries",
    "stop_target_handling": "PerEntryExecution",
    "calculate": "OnBarClose",
    "order_fill_resolution": "Standard",
    "is_fill_limit_on_touch": False,
    "slippage": 0,
    "bars_required_to_trade": 0,
}

LONG = "probeLong"
SHORT = "probeShort"


def bar(
    index: int, open_: float, close: float, *, high: float | None = None, low: float | None = None
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(BAR_COLUMNS, "")
    row.update(
        bar=index,
        open=open_,
        high=max(open_, close) + 0.25 if high is None else high,
        low=min(open_, close) - 0.25 if low is None else low,
        close=close,
        volume=10,
        market_position="Flat",
        position_quantity=0,
        is_first_bar_of_session=0,
        is_last_bar_of_session=0,
    )

    return row


def event(kind: str, trial: int, reported_bar: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(EVENT_COLUMNS, "")
    row.update(kind=kind, trial=trial, bar=reported_bar, quantity=1, is_last_bar_of_session=0)
    row.update(overrides)

    return row


def target_set(trial: int, at_bar: int, entry: str, price: float) -> dict[str, object]:
    return event(
        rpt.TARGET_SET, trial, at_bar, from_entry_signal=entry, order_type="Limit", limit_price=price
    )


def entry_fill(trial: int, reported_bar: int, entry: str, price: float) -> dict[str, object]:
    return event(
        EXECUTION,
        trial,
        reported_bar,
        signal_name=entry,
        order_type="Market",
        order_state="Filled",
        execution_price=price,
    )


def target_fill(trial: int, reported_bar: int, entry: str, limit: float, price: float) -> dict[str, object]:
    return event(
        EXECUTION,
        trial,
        reported_bar,
        signal_name=rpt.PROFIT_TARGET,
        from_entry_signal=entry,
        order_type="Limit",
        limit_price=limit,
        order_state="Filled",
        execution_price=price,
    )


def write_run(
    tmp_path: Path,
    events: list[dict[str, object]],
    bars: list[dict[str, object]],
    *,
    config: bool = False,
    before_stops: bool = False,
) -> Path:
    """Write a synthetic probe run and return the path to its events file.

    ``before_stops`` writes the event log a probe wrote before it had a ``stop_price`` column.
    """
    events_path = tmp_path / "SYN_s1_events.csv"
    columns = [column for column in EVENT_COLUMNS if not (before_stops and column == "stop_price")]
    pd.DataFrame(events, columns=columns).to_csv(events_path, sep=";", index=False)
    pd.DataFrame(bars, columns=BAR_COLUMNS).to_csv(tmp_path / "SYN_s1_bars.csv", sep=";", index=False)
    if config:
        pd.DataFrame([CONFIG]).to_csv(tmp_path / "SYN_s1_config.csv", sep=";", index=False)

    return events_path


# Scenario 1. A long sent at bar 0's close with its target a point under that close, and a short
# sent at bar 1's close with its target a point over it. Each entry fills at the next bar's
# open, past its target, and every open differs from the one before it so the lag is decidable.
# No bar reaches either target, so the rule fills the long at its bar's low and the short at
# its bar's high.
ENTRY_BAR_BARS = [bar(0, 100.0, 100.0), bar(1, 100.25, 100.5), bar(2, 100.5, 100.75), bar(3, 100.75, 100.75)]
LONG_TARGET = 99.0
SHORT_TARGET = 101.5

READINGS = {
    "rule": ((100.0, 101.0), (100.25, 101.0)),
    "target": ((LONG_TARGET, SHORT_TARGET), (LONG_TARGET, SHORT_TARGET)),
    "open": ((100.25, 100.5), (100.5, 100.75)),
}
"""The long's and the short's fill under each reading, on the entry bar and on the bar after."""


def entry_bar_events(reading: str = "rule", *, lag: int = 1, target_lag: int = 0) -> list[dict[str, object]]:
    """Build the two scenario-1 trials, each target filling at the price ``reading`` names.

    ``lag`` is how far the entry callbacks report behind their fill bar, and ``target_lag`` how
    many bars after its entry the target filled.
    """
    long_fill, short_fill = READINGS[reading][target_lag]

    return [
        target_set(1, 0, LONG, LONG_TARGET),
        event("SUBMIT", 1, 0, signal_name=LONG),
        entry_fill(1, 1 - lag, LONG, 100.25),
        target_fill(1, 1 - lag + target_lag, LONG, LONG_TARGET, long_fill),
        target_set(2, 1, SHORT, SHORT_TARGET),
        event("SUBMIT", 2, 1, signal_name=SHORT),
        entry_fill(2, 2 - lag, SHORT, 100.5),
        target_fill(2, 2 - lag + target_lag, SHORT, SHORT_TARGET, short_fill),
    ]


@pytest.mark.parametrize(
    ("reading", "key"), [("rule", "at_bar_extreme"), ("target", "other"), ("open", "at_open")]
)
def test_a_target_passed_at_the_entry_is_read_at_the_price_it_filled_at(
    tmp_path: Path, reading: str, key: str
) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(reading), ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert counts["trials"]["entries"] == 2
    assert counts["trials"]["passed"] == 2  # the short is passed only if its side is read
    assert counts["on_entry_bar"][key] == 2
    assert sum(counts["on_entry_bar"].values()) == 2
    assert sum(counts["on_a_later_bar"].values()) == 0


def test_a_passed_target_its_bar_reaches_fills_at_its_own_price(tmp_path: Path) -> None:
    bars = [bar(0, 100.0, 100.0), bar(1, 100.25, 100.5, low=98.75), bar(2, 100.5, 100.75, high=101.75)]
    run = read_run(write_run(tmp_path, entry_bar_events("target"), bars))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert counts["on_entry_bar"] == {"at_limit": 2, "at_bar_extreme": 0, "at_open": 0, "other": 0}


@pytest.mark.parametrize(("reading", "follows"), [("rule", True), ("target", False), ("open", False)])
def test_report_passes_a_run_only_when_every_fill_follows_the_rule(
    tmp_path: Path, reading: str, *, follows: bool
) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(reading), ENTRY_BAR_BARS))
    assert rpt.report(run) is follows


def test_a_passed_target_filling_a_bar_later_is_told_from_one_filling_on_the_entry_bar(
    tmp_path: Path,
) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(target_lag=1), ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert sum(counts["on_entry_bar"].values()) == 0
    assert counts["on_a_later_bar"] == {"at_limit": 0, "at_bar_extreme": 2, "at_open": 0, "other": 0}


def test_a_passed_target_filling_later_is_not_read_as_a_resting_one(tmp_path: Path) -> None:
    """It sat behind the previous close, so the bar it filled on did not gap through it."""
    run = read_run(write_run(tmp_path, entry_bar_events(target_lag=1), ENTRY_BAR_BARS))
    resting = rpt.gapped_while_resting(rpt.trials(run), run.bars)
    assert resting == {
        "gapped": {"at_limit": 0, "at_bar_extreme": 0, "at_open": 0, "other": 0},
        "control": {"at_limit": 0, "at_bar_extreme": 0, "at_open": 0, "other": 0},
    }


def test_a_target_the_entry_did_not_pass_is_left_out(tmp_path: Path) -> None:
    """Bar 1 opens below the long's target, so the target is still ahead of the fill."""
    events = [target_set(1, 0, LONG, 100.5), entry_fill(1, 0, LONG, 100.25)]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]
    assert counts["entries"] == 1
    assert counts["passed"] == 0


def test_a_passed_target_that_never_filled_is_counted(tmp_path: Path) -> None:
    events = [
        target_set(1, 0, LONG, LONG_TARGET),
        entry_fill(1, 0, LONG, 100.25),
        event(EXECUTION, 1, 2, signal_name="probeExit", order_state="Filled", execution_price=100.75),
    ]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert counts["trials"]["passed"] == 1
    assert counts["trials"]["not_filled"] == 1
    assert counts["trials"]["rejected"] == 0
    assert sum(counts["on_entry_bar"].values()) + sum(counts["on_a_later_bar"].values()) == 0


def test_a_rejected_passed_target_is_told_from_one_left_unfilled(tmp_path: Path) -> None:
    events = [
        target_set(1, 0, LONG, LONG_TARGET),
        entry_fill(1, 0, LONG, 100.25),
        event(ORDER_UPDATE, 1, 0, signal_name=rpt.PROFIT_TARGET, order_state=rpt.REJECTED),
    ]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]
    assert counts["rejected"] == 1
    assert counts["not_filled"] == 0


def test_a_target_filled_before_its_entry_is_counted_rather_than_dropped(tmp_path: Path) -> None:
    events = [
        target_set(1, 0, LONG, LONG_TARGET),
        entry_fill(1, 1, LONG, 100.5),
        target_fill(1, 0, LONG, LONG_TARGET, 100.25),
    ]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]["filled_before_entry"] == 1
    assert rpt.report(run) is False


def test_a_fill_neither_passed_nor_resting_is_still_held_to_the_rule(tmp_path: Path) -> None:
    """Bar 1 trades through the long's 100.5 target, so a fill at 100.25 is not the rule's."""
    events = [
        target_set(1, 0, LONG, 100.5),
        entry_fill(1, 0, LONG, 100.25),
        target_fill(1, 0, LONG, 100.5, 100.25),
    ]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]["passed"] == 0
    assert rpt.report(run) is False


def test_every_target_tied_to_its_trials_entry_is_attributed(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(), ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 0


def test_a_target_naming_another_entry_is_caught_and_fails_the_report(tmp_path: Path) -> None:
    events = entry_bar_events()
    events[3]["from_entry_signal"] = SHORT
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 1
    assert rpt.report(run) is False


def test_a_target_in_a_trial_with_no_entry_is_caught(tmp_path: Path) -> None:
    events = [*entry_bar_events(), target_fill(3, 2, LONG, LONG_TARGET, 100.75)]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 1


def test_the_lag_is_a_clean_plus_one_when_every_entry_is_the_next_bars_open(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(), ENTRY_BAR_BARS))
    counts = rpt.measure_lag(run)
    assert counts == {"fills": 2, "reported": 0, "reported_plus_one": 2, "both": 0, "neither": 0}
    assert rpt.lag_is_clean(counts)


def test_a_callback_naming_the_bar_it_filled_on_is_not_read_as_lagging(tmp_path: Path) -> None:
    """The other candidate reading, which must not pass as a clean +1."""
    run = read_run(write_run(tmp_path, entry_bar_events(lag=0), ENTRY_BAR_BARS))
    counts = rpt.measure_lag(run)
    assert counts["reported"] == 2
    assert not rpt.lag_is_clean(counts)
    assert rpt.report(run) is False


def test_an_entry_two_equal_opens_explain_decides_nothing(tmp_path: Path) -> None:
    bars = [bar(0, 100.25, 100.0), bar(1, 100.25, 100.5)]
    run = read_run(write_run(tmp_path, [entry_fill(1, 0, LONG, 100.25)], bars))
    counts = rpt.measure_lag(run)
    assert counts["both"] == 1
    assert not rpt.lag_is_clean(counts)


def test_an_entry_no_open_explains_fails_the_lag_check(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, [entry_fill(1, 0, LONG, 100.125)], ENTRY_BAR_BARS))
    counts = rpt.measure_lag(run)
    assert counts["neither"] == 1
    assert not rpt.lag_is_clean(counts)


def test_a_run_with_no_entry_fills_does_not_pass_the_lag_check(tmp_path: Path) -> None:
    """A probe that traded nothing has measured nothing, and must not read as clean."""
    run = read_run(write_run(tmp_path, [target_set(1, 0, LONG, LONG_TARGET)], ENTRY_BAR_BARS))
    assert not rpt.lag_is_clean(rpt.measure_lag(run))


# Scenario 2. A long entered at bar 1's open has its target moved to a tick over bar 1's close;
# bar 2 opens three ticks over that and never trades back, so the target is gapped through and
# the rule fills it at bar 2's low. A short entered at bar 3's open has its target moved to a
# tick under bar 3's close; bar 4 opens short of it and trades through, which is the control.
RESTING_BARS = [
    bar(0, 100.0, 100.0),
    bar(1, 100.25, 100.0),
    bar(2, 101.0, 101.0),
    bar(3, 100.75, 100.5),
    bar(4, 100.5, 100.25, low=100.0),
]
GAPPED_TARGET = 100.25
CONTROL_TARGET = 100.25


GAPPED_FILLS = {"rule": 100.75, "target": GAPPED_TARGET, "open": 101.0}


def resting_events(reading: str = "rule") -> list[dict[str, object]]:
    """Build the two scenario-2 trials, the gapped target filling at the price ``reading`` names."""
    return [
        target_set(1, 0, LONG, 2100.0),
        entry_fill(1, 0, LONG, 100.25),
        target_set(1, 1, LONG, GAPPED_TARGET),
        target_fill(1, 1, LONG, GAPPED_TARGET, GAPPED_FILLS[reading]),
        target_set(2, 2, SHORT, 51.0),
        entry_fill(2, 2, SHORT, 100.75),
        target_set(2, 3, SHORT, CONTROL_TARGET),
        target_fill(2, 3, SHORT, CONTROL_TARGET, CONTROL_TARGET),
    ]


@pytest.mark.parametrize(
    ("reading", "key"), [("rule", "at_bar_extreme"), ("target", "other"), ("open", "at_open")]
)
def test_a_gapped_through_target_is_read_at_the_price_it_filled_at(
    tmp_path: Path, reading: str, key: str
) -> None:
    run = read_run(write_run(tmp_path, resting_events(reading), RESTING_BARS))
    resting = rpt.gapped_while_resting(rpt.trials(run), run.bars)
    assert resting["gapped"][key] == 1
    assert sum(resting["gapped"].values()) == 1
    assert resting["control"] == {"at_limit": 1, "at_bar_extreme": 0, "at_open": 0, "other": 0}


def test_a_gapped_through_target_its_bar_trades_back_to_fills_at_its_own_price(tmp_path: Path) -> None:
    bars = [*RESTING_BARS[:2], bar(2, 101.0, 101.0, low=100.0), *RESTING_BARS[3:]]
    run = read_run(write_run(tmp_path, resting_events("target"), bars))
    gapped = rpt.gapped_while_resting(rpt.trials(run), run.bars)["gapped"]
    assert gapped == {"at_limit": 1, "at_bar_extreme": 0, "at_open": 0, "other": 0}


def test_a_control_fill_outside_its_bar_fails_the_report(tmp_path: Path) -> None:
    """Bar 4 never trades down to the short's target, so a fill there names the wrong bar."""
    bars = [*RESTING_BARS[:4], bar(4, 100.5, 100.75, low=100.5)]
    run = read_run(write_run(tmp_path, resting_events(), bars))
    control = rpt.gapped_while_resting(rpt.trials(run), run.bars)["control"]
    assert control == {"at_limit": 0, "at_bar_extreme": 0, "at_open": 0, "other": 1}
    assert rpt.report(run) is False


def test_an_out_of_reach_target_at_the_entry_is_not_read_as_passed(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, resting_events(), RESTING_BARS))
    assert rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]["passed"] == 0


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"at_limit": 0, "at_bar_extreme": 0, "at_open": 0, "other": 0}, "no instances in this run"),
        (
            {"at_limit": 2, "at_bar_extreme": 1, "at_open": 0, "other": 0},
            "all 3 at the nearest price the bar traded",
        ),
        (
            {"at_limit": 0, "at_bar_extreme": 3, "at_open": 0, "other": 0},
            "all 3 at the nearest price the bar traded",
        ),
        ({"at_limit": 0, "at_bar_extreme": 2, "at_open": 0, "other": 1}, "1 of 3 break the rule"),
        ({"at_limit": 1, "at_bar_extreme": 0, "at_open": 2, "other": 0}, "2 of 3 break the rule"),
    ],
)
def test_the_verdict_passes_a_set_only_when_every_fill_follows_the_rule(
    counts: dict[str, int], expected: str
) -> None:
    assert rpt.verdict(counts) == expected


def test_report_reads_a_run_with_its_config(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, resting_events(), RESTING_BARS, config=True))
    assert run.config is not None
    assert rpt.report(run) is True


def test_main_reports_usage_when_given_no_export() -> None:
    assert rpt.main(["reconcile_passed_target.py"]) == 2


def test_main_returns_zero_on_a_run_whose_lag_is_clean(tmp_path: Path) -> None:
    path = write_run(tmp_path, entry_bar_events(), ENTRY_BAR_BARS)
    assert rpt.main(["reconcile_passed_target.py", str(path)]) == 0


def test_main_returns_one_on_a_run_whose_lag_is_not(tmp_path: Path) -> None:
    path = write_run(tmp_path, entry_bar_events(lag=0), ENTRY_BAR_BARS)
    assert rpt.main(["reconcile_passed_target.py", str(path)]) == 1


# Scenarios 3 and 4, the limit entries. A buy limit a tick under bar 0's close meets bar 1
# opening below it and never trading back up, so the rule fills it at bar 1's high. Its exit
# fills at bar 2's open. A sell limit a tick over bar 2's close is then left for bar 3 to trade
# up through, which is the control, and its exit fills at bar 4's open.
LIMIT_BARS = [
    bar(0, 100.0, 100.0),
    bar(1, 99.25, 99.5, high=99.5),
    bar(2, 99.5, 99.75),
    bar(3, 99.75, 100.25, high=100.5),
    bar(4, 100.0, 100.0),
]
GAPPED_LIMIT_FILLS = {"rule": 99.5, "limit": 99.75, "open": 99.25}


def limit_sent(trial: int, at_bar: int, entry: str, price: float) -> list[dict[str, object]]:
    """Build a limit entry's submission and the order update that acknowledges it."""
    return [
        event(SUBMIT, trial, at_bar, signal_name=entry, order_type="Limit", limit_price=price),
        event(ORDER_UPDATE, trial, at_bar, signal_name=entry, order_type="Limit", order_state="Working"),
    ]


def limit_fill(trial: int, reported_bar: int, entry: str, limit: float, price: float) -> dict[str, object]:
    return event(
        EXECUTION,
        trial,
        reported_bar,
        signal_name=entry,
        order_type="Limit",
        limit_price=limit,
        order_state="Filled",
        execution_price=price,
    )


def probe_exit(trial: int, reported_bar: int, price: float) -> dict[str, object]:
    return event(
        EXECUTION,
        trial,
        reported_bar,
        signal_name=rpt.PROBE_EXIT,
        order_type="Market",
        order_state="Filled",
        execution_price=price,
    )


def limit_entry_events(reading: str = "rule") -> list[dict[str, object]]:
    """Build the two limit-entry trials, the gapped one filling at the price ``reading`` names."""
    return [
        *limit_sent(1, 0, LONG, 99.75),
        limit_fill(1, 0, LONG, 99.75, GAPPED_LIMIT_FILLS[reading]),
        probe_exit(1, 1, 99.5),
        *limit_sent(2, 2, SHORT, 100.0),
        limit_fill(2, 2, SHORT, 100.0, 100.0),
        probe_exit(2, 3, 100.0),
    ]


@pytest.mark.parametrize(
    ("reading", "key"), [("rule", "at_bar_extreme"), ("limit", "other"), ("open", "at_open")]
)
def test_a_limit_entry_a_bar_opens_past_is_read_at_the_price_it_filled_at(
    tmp_path: Path, reading: str, key: str
) -> None:
    run = read_run(write_run(tmp_path, limit_entry_events(reading), LIMIT_BARS))
    entries = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)
    assert entries["gapped"]["sent"] == 1
    assert entries["gapped"][key] == 1
    assert entries["resting"]["at_limit"] == 1  # the short is resting only if its side is read
    assert entries["marketable"]["sent"] == 0


@pytest.mark.parametrize(("reading", "follows"), [("rule", True), ("limit", False), ("open", False)])
def test_report_holds_limit_entries_to_the_rule(tmp_path: Path, reading: str, *, follows: bool) -> None:
    run = read_run(write_run(tmp_path, limit_entry_events(reading), LIMIT_BARS))
    assert rpt.report(run) is follows


def test_the_lag_is_measured_on_the_probes_exits_where_no_entry_is_a_market_order(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, limit_entry_events(), LIMIT_BARS))
    counts = rpt.measure_lag(run)
    assert counts["fills"] == 2
    assert rpt.lag_is_clean(counts)


@pytest.mark.parametrize(("low", "key"), [(99.75, "touched_unfilled"), (99.5, "through_unfilled")])
def test_a_resting_limit_entry_left_unfilled_is_told_by_how_far_its_bar_reached(
    tmp_path: Path, low: float, key: str
) -> None:
    bars = [*LIMIT_BARS, bar(5, 100.0, 100.0, low=low)]
    events = [*limit_entry_events(), *limit_sent(3, 4, LONG, 99.75)]
    run = read_run(write_run(tmp_path, events, bars))
    entries = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)
    assert entries["resting"][key] == 1
    assert rpt.report(run) is (key == "touched_unfilled")


def test_a_gapped_limit_entry_left_unfilled_fails_the_report(tmp_path: Path) -> None:
    events = [e for e in limit_entry_events() if not (e["trial"] == 1 and e["kind"] == EXECUTION)]
    run = read_run(write_run(tmp_path, events, LIMIT_BARS))
    assert rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["gapped"]["through_unfilled"] == 1
    assert rpt.report(run) is False


def test_a_rejected_limit_entry_a_bar_trades_through_is_not_read_as_left_unfilled(tmp_path: Path) -> None:
    bars = [*LIMIT_BARS, bar(5, 100.0, 100.0, low=99.5)]
    rejection = event(ORDER_UPDATE, 3, 4, signal_name=LONG, order_type="Limit", order_state=rpt.REJECTED)
    run = read_run(
        write_run(tmp_path, [*limit_entry_events(), *limit_sent(3, 4, LONG, 99.75), rejection], bars)
    )
    resting = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["resting"]
    assert resting["rejected"] == 1
    assert resting["through_unfilled"] == 0
    assert rpt.report(run) is True


def test_a_limit_entry_filled_on_a_touch_is_counted(tmp_path: Path) -> None:
    bars = [*LIMIT_BARS, bar(5, 100.0, 100.0, low=99.75)]
    events = [*limit_entry_events(), *limit_sent(3, 4, LONG, 99.75), limit_fill(3, 4, LONG, 99.75, 99.75)]
    run = read_run(write_run(tmp_path, events, bars))
    assert rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["resting"]["touched_filled"] == 1


def test_a_limit_entry_filled_off_the_bar_it_was_live_on_fails_the_report(tmp_path: Path) -> None:
    events = limit_entry_events()
    events[2]["bar"] = 1
    run = read_run(write_run(tmp_path, events, LIMIT_BARS))
    assert rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["checks"]["filled_off_the_live_bar"] == 1
    assert rpt.report(run) is False


# A buy limit a point over bar 0's close is marketable when sent. Bar 1 opens at 100 and never
# trades up to it, so the rule fills it at bar 1's high and the market would fill it at the open.
MARKETABLE_BARS = [bar(0, 100.0, 100.0), bar(1, 100.0, 100.25, high=100.5), bar(2, 100.25, 100.25)]


@pytest.mark.parametrize(("price", "key"), [(100.5, "at_bar_extreme"), (100.0, "at_open"), (101.0, "other")])
def test_a_marketable_limit_entry_is_read_at_the_price_it_filled_at(
    tmp_path: Path, price: float, key: str
) -> None:
    events = [*limit_sent(1, 0, LONG, 101.0), limit_fill(1, 0, LONG, 101.0, price), probe_exit(1, 1, 100.25)]
    run = read_run(write_run(tmp_path, events, MARKETABLE_BARS))
    marketable = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["marketable"]
    assert marketable["sent"] == marketable["acknowledged"] == marketable["filled"] == 1
    assert marketable[key] == 1


def test_a_marketable_limit_entry_ninjatrader_never_acknowledged_is_counted(tmp_path: Path) -> None:
    events = [event(SUBMIT, 1, 0, signal_name=LONG, order_type="Limit", limit_price=101.0)]
    run = read_run(write_run(tmp_path, events, MARKETABLE_BARS))
    marketable = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["marketable"]
    assert marketable["sent"] == 1
    assert marketable["acknowledged"] == 0
    assert marketable["filled"] == 0


def test_a_run_whose_every_entry_was_rejected_still_reports_what_was_sent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With nothing filled there is no lag to measure, and the rejections are the answer."""
    events = [
        *limit_sent(1, 0, LONG, 101.0),
        event(ORDER_UPDATE, 1, 0, signal_name=LONG, order_type="Limit", order_state=rpt.REJECTED),
    ]
    run = read_run(write_run(tmp_path, events, MARKETABLE_BARS))
    with caplog.at_level(logging.INFO):
        assert rpt.report(run) is False
    assert "'marketable': {'sent': 1, 'acknowledged': 1, 'rejected': 1}" in caplog.text


def test_a_rejected_marketable_limit_entry_is_counted(tmp_path: Path) -> None:
    events = [
        *limit_sent(1, 0, LONG, 101.0),
        event(ORDER_UPDATE, 1, 0, signal_name=LONG, order_type="Limit", order_state=rpt.REJECTED),
    ]
    run = read_run(write_run(tmp_path, events, MARKETABLE_BARS))
    assert rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["marketable"]["rejected"] == 1


def test_a_run_with_no_limit_entries_reports_none(tmp_path: Path) -> None:
    """The target scenarios send market entries, which must not be read as limit entries."""
    run = read_run(write_run(tmp_path, entry_bar_events(), ENTRY_BAR_BARS))
    entries = rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)
    assert all(entries[group]["sent"] == 0 for group in rpt.ENTRY_GROUPS)
    assert entries["checks"]["filled_off_the_live_bar"] == 0


# Scenario 5, a limit entry with its stop a tick beyond it. A buy limit a tick under bar 0's
# close, its stop a tick under that, meets bar 1 opening under both and never trading back to
# the stop, so the entry fills at bar 1's high, beyond its stop. A sell limit a tick over bar 1's
# close meets bar 2 opening short of its stop and trading up through both, which is the control.
# A buy limit a tick under bar 2's close meets bar 3 opening under its stop and trading back up
# to the limit, so the entry fills short of the stop.
STOP_BARS = [
    bar(0, 100.0, 100.0),
    bar(1, 99.0, 99.0, high=99.25, low=98.75),
    bar(2, 99.0, 99.5, high=99.75, low=98.75),
    bar(3, 98.75, 99.0, high=99.25, low=98.5),
    bar(4, 99.0, 99.0),
]

STOP_READINGS = {"rule": (99.0, 98.75), "stop": (99.5, 99.0), "entry": (99.25, 99.25)}
"""The two opened-past stops' fills under each reading: the open, the stop's price, the entry's fill."""


def stop_set(trial: int, at_bar: int, entry: str, price: float) -> dict[str, object]:
    return event(
        rpt.STOP_SET, trial, at_bar, from_entry_signal=entry, order_type="StopMarket", stop_price=price
    )


def stop_fill(trial: int, reported_bar: int, entry: str, stop: float, price: float) -> dict[str, object]:
    return event(
        EXECUTION,
        trial,
        reported_bar,
        signal_name=rpt.STOP_LOSS,
        from_entry_signal=entry,
        order_type="StopMarket",
        stop_price=stop,
        order_state="Filled",
        execution_price=price,
    )


def stopped_limit_trial(
    trial: int, sent_bar: int, entry: str, prices: tuple[float, float, float, float], lag: int
) -> list[dict[str, object]]:
    """Build one scenario-5 trial: the stop set, the limit sent, and both filling on the next bar.

    ``prices`` is the stop, the limit, the entry's fill and the stop's fill.
    """
    stop, limit, entry_price, stop_price = prices
    reported = sent_bar + 1 - lag

    return [
        stop_set(trial, sent_bar, entry, stop),
        *limit_sent(trial, sent_bar, entry, limit),
        limit_fill(trial, reported, entry, limit, entry_price),
        stop_fill(trial, reported, entry, stop, stop_price),
    ]


def stop_events(reading: str = "rule", *, lag: int = 1) -> list[dict[str, object]]:
    """Build the three scenario-5 trials, each opened-past stop filling at the price ``reading`` names."""
    beyond, gapped = STOP_READINGS[reading]

    return [
        *stopped_limit_trial(1, 0, LONG, (99.5, 99.75, 99.25, beyond), lag),
        *stopped_limit_trial(2, 1, SHORT, (99.5, 99.25, 99.25, 99.5), lag),
        *stopped_limit_trial(3, 2, LONG, (99.0, 99.25, 99.25, gapped), lag),
    ]


@pytest.mark.parametrize(
    ("reading", "key"), [("rule", "at_open"), ("stop", "against_path"), ("entry", "against_path")]
)
def test_a_stop_its_entry_bar_opened_past_is_read_at_the_price_it_filled_at(
    tmp_path: Path, reading: str, key: str
) -> None:
    run = read_run(write_run(tmp_path, stop_events(reading), STOP_BARS))
    stops = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)
    for group in ("beyond", "gapped"):  # each holds one long only if the entry's fill is read
        assert stops[group]["trials"]["entries"] == 1
        assert stops[group]["entry_bar"][key] == 1
        assert sum(stops[group]["entry_bar"].values()) == 1
    assert stops["control"]["entry_bar"] == {
        "at_open": 0,
        "at_stop": 1,
        "not_reached": 0,
        "against_path": 0,
    }


@pytest.mark.parametrize(("reading", "follows"), [("rule", True), ("stop", False), ("entry", False)])
def test_report_holds_stops_to_the_bars_path_on_the_entry_bar(
    tmp_path: Path, reading: str, *, follows: bool
) -> None:
    run = read_run(write_run(tmp_path, stop_events(reading), STOP_BARS))
    assert rpt.report(run) is follows


def test_a_control_stop_filled_where_its_bar_never_traded_breaks_the_rule(tmp_path: Path) -> None:
    """Bar 2 never trades up to 99.75, so the short's stop cannot have filled there."""
    events = stop_events()
    events[5]["stop_price"] = events[9]["stop_price"] = events[9]["execution_price"] = 99.75
    bars = [*STOP_BARS[:2], bar(2, 99.0, 99.5, high=99.5, low=98.75), *STOP_BARS[3:]]
    run = read_run(write_run(tmp_path, events, bars))
    control = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)["control"]
    assert control["entry_bar"]["against_path"] == 1
    assert rpt.report(run) is False


def test_a_stop_the_path_reaches_but_filling_a_bar_later_breaks_the_rule(tmp_path: Path) -> None:
    events = stop_events()
    events[9]["bar"] = 2  # the short's stop, reported a bar after its entry
    run = read_run(write_run(tmp_path, events, STOP_BARS))
    control = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)["control"]
    assert control["entry_bar"]["against_path"] == 1
    assert sum(control["on_a_later_bar"].values()) == 1
    assert rpt.report(run) is False


def test_a_stop_filled_before_its_entry_is_counted_and_fails_the_report(tmp_path: Path) -> None:
    events = stop_events()
    events[9]["bar"] = 0
    run = read_run(write_run(tmp_path, events, STOP_BARS))
    control = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)["control"]
    assert control["trials"]["filled_before_entry"] == 1
    assert rpt.report(run) is False


def test_a_rejected_stop_is_told_from_one_left_unfilled(tmp_path: Path) -> None:
    rejection = event(
        ORDER_UPDATE, 1, 0, signal_name=rpt.STOP_LOSS, from_entry_signal=LONG, order_state=rpt.REJECTED
    )
    events = [e for e in stop_events() if not (e["kind"] == EXECUTION and e["signal_name"] == rpt.STOP_LOSS)]
    run = read_run(write_run(tmp_path, [*events, rejection], STOP_BARS))
    stops = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)
    assert stops["beyond"]["trials"]["rejected"] == 1
    assert stops["beyond"]["trials"]["not_filled"] == 0
    assert stops["gapped"]["trials"]["not_filled"] == 1


def test_a_stop_naming_another_entry_is_caught_and_fails_the_report(tmp_path: Path) -> None:
    events = stop_events()
    events[4]["from_entry_signal"] = SHORT
    run = read_run(write_run(tmp_path, events, STOP_BARS))
    assert rpt.misattributed_stops(run, rpt.stop_trials(run)) == 1
    assert rpt.report(run) is False


def test_a_stop_in_a_trial_with_no_entry_is_caught(tmp_path: Path) -> None:
    events = [*stop_events(), stop_fill(4, 3, LONG, 98.5, 98.5)]
    run = read_run(write_run(tmp_path, events, STOP_BARS))
    assert rpt.misattributed_stops(run, rpt.stop_trials(run)) == 1


def test_a_run_that_set_no_stop_reports_without_reading_one(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, limit_entry_events(), LIMIT_BARS))
    assert not rpt.set_stops(run)
    assert rpt.report(run) is True


def test_a_run_written_before_the_stop_price_column_still_reports(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(), ENTRY_BAR_BARS, before_stops=True))
    assert "stop_price" not in run.events
    assert rpt.report(run) is True


# Scenario 6, a stop entry with its stop a tick beyond the close. A buy stop two ticks over bar
# 0's close, its stop one tick over, meets bar 1 opening at that close -- past the stop. The low
# is nearer the open, so the path runs down first, up through the entry, and back down to a
# close that only reaches the stop if it is at or under it.
def stop_entry_events(stop_fill_price: float, stop_reported_bar: int = 0) -> list[dict[str, object]]:
    """Build one scenario-6 long: a buy stop at 100.5 with its stop at 100.25, both filling as given."""
    return [
        stop_set(1, 0, LONG, 100.25),
        event(SUBMIT, 1, 0, signal_name=LONG, order_type="StopMarket", stop_price=100.5),
        event(
            EXECUTION,
            1,
            0,
            signal_name=LONG,
            order_type="StopMarket",
            order_state="Filled",
            execution_price=100.5,
        ),
        stop_fill(1, stop_reported_bar, LONG, 100.25, stop_fill_price),
    ]


@pytest.mark.parametrize(("price", "key"), [(100.25, "at_stop"), (100.0, "against_path")])
def test_a_stop_behind_a_stop_entry_fills_at_its_price_where_the_path_comes_back_to_it(
    tmp_path: Path, price: float, key: str
) -> None:
    bars = [bar(0, 100.0, 100.0), bar(1, 100.0, 100.0, high=100.75, low=99.75), bar(2, 100.0, 100.0)]
    run = read_run(write_run(tmp_path, stop_entry_events(price), bars))
    stops = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)
    assert stops["gapped"]["entry_bar"][key] == 1
    assert rpt.limit_entry_fills(rpt.limit_entries(run), run.bars)["resting"]["sent"] == 0
    assert rpt.report(run) is (key == "at_stop")


def test_a_stop_behind_a_stop_entry_the_path_never_comes_back_to_is_left_for_a_later_bar(
    tmp_path: Path,
) -> None:
    """The bar's low is before the entry on its path, so a stop the bar's range reaches is not reached."""
    bars = [bar(0, 100.0, 100.0), bar(1, 100.0, 100.5, high=100.75, low=99.75), bar(2, 100.0, 100.0)]
    run = read_run(write_run(tmp_path, stop_entry_events(100.0, stop_reported_bar=1), bars))
    stops = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)
    assert stops["gapped"]["entry_bar"]["not_reached"] == 1
    assert stops["gapped"]["on_a_later_bar"]["at_open"] == 1
    assert rpt.report(run) is True


FOUR_LEG_BARS = [bar(0, 100.0, 100.0), bar(1, 100.0, 100.5, high=100.75, low=99.75), bar(2, 100.0, 100.0)]
"""Bar 1 runs down first, up through the buy stop at 100.5, and closes short of its stop at 100.25."""


def four_leg_events(stop_fills: dict[int, tuple[int, float]]) -> list[dict[str, object]]:
    """Build one scenario-9 long of four legs on :data:`FOUR_LEG_BARS`, each stop as ``stop_fills`` says.

    ``stop_fills`` maps a leg to the bar its stop is reported on and the price it filled at.
    """
    names = [LONG, *(f"{LONG}{leg}" for leg in range(2, 5))]
    sent = [
        event(SUBMIT, 1, 0, signal_name=name, order_type="StopMarket", stop_price=100.5) for name in names
    ]
    filled = [
        event(
            EXECUTION,
            1,
            0,
            signal_name=name,
            order_type="StopMarket",
            order_state="Filled",
            execution_price=100.5,
        )
        for name in names
    ]
    stopped = [
        stop_fill(1, reported_bar, names[leg - 1], 100.25, price)
        for leg, (reported_bar, price) in stop_fills.items()
    ]

    return [stop_set(1, 0, LONG, 100.25), *sent, *filled, *stopped]


EARLIER_LEGS_ON_THE_ENTRY_BAR = dict.fromkeys((1, 2, 3), (0, 100.25))
"""Legs 1 to 3 stopped at their own price on the entry bar, as the stretch their entry filled in says."""


def test_each_leg_of_a_trial_is_read_on_its_own_stop(tmp_path: Path) -> None:
    run = read_run(
        write_run(tmp_path, four_leg_events({**EARLIER_LEGS_ON_THE_ENTRY_BAR, 4: (1, 100.0)}), FOUR_LEG_BARS)
    )
    frame = rpt.stop_trials(run)
    assert frame["leg"].tolist() == [1, 2, 3, 4]
    assert frame["last_leg"].tolist() == [False, False, False, True]
    assert frame["stop_fill"].tolist() == [100.25, 100.25, 100.25, 100.0]
    assert rpt.misattributed_stops(run, frame) == 0


@pytest.mark.parametrize(
    ("last_leg", "follows"),
    [((1, 100.0), True), ((0, 100.25), False)],
)
def test_the_last_leg_sees_only_the_path_after_its_entry_and_the_earlier_legs_the_whole_stretch(
    tmp_path: Path, last_leg: tuple[int, float], *, follows: bool
) -> None:
    """Every leg filled at 100.5 on the way up from the low; only the earlier legs see that low."""
    run = read_run(
        write_run(tmp_path, four_leg_events({**EARLIER_LEGS_ON_THE_ENTRY_BAR, 4: last_leg}), FOUR_LEG_BARS)
    )
    gapped = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)["gapped"]
    assert gapped["entry_bar_earlier_legs"] == {
        "at_open": 0,
        "at_stop": 3,
        "not_reached": 0,
        "against_path": 0,
    }
    assert gapped["entry_bar"]["not_reached" if follows else "against_path"] == 1
    assert rpt.report(run) is follows


def test_an_earlier_leg_left_for_a_later_bar_breaks_the_rule(tmp_path: Path) -> None:
    run = read_run(
        write_run(
            tmp_path,
            four_leg_events({1: (1, 100.0), 2: (0, 100.25), 3: (0, 100.25), 4: (1, 100.0)}),
            FOUR_LEG_BARS,
        )
    )
    gapped = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)["gapped"]
    assert gapped["entry_bar_earlier_legs"]["against_path"] == 1
    assert rpt.report(run) is False


def test_a_stop_naming_a_leg_its_trial_never_filled_is_caught(tmp_path: Path) -> None:
    events = [*four_leg_events(EARLIER_LEGS_ON_THE_ENTRY_BAR), stop_fill(1, 1, f"{LONG}5", 100.25, 100.0)]
    run = read_run(write_run(tmp_path, events, FOUR_LEG_BARS))
    assert rpt.misattributed_stops(run, rpt.stop_trials(run)) == 1


@pytest.mark.parametrize(
    ("side", "level", "stop", "ohlc", "last_leg", "expected"),
    [
        (1.0, 100.5, 100.25, (100.0, 100.75, 99.75, 100.5), True, None),
        (1.0, 100.5, 100.25, (100.0, 100.75, 99.75, 100.5), False, 100.25),
        (1.0, 100.5, 100.25, (100.0, 100.75, 99.0, 100.5), True, 100.25),
        (1.0, 100.5, 100.25, (100.0, 100.75, 99.0, 100.5), False, 100.0),
        (1.0, 100.5, 100.25, (100.75, 101.0, 100.0, 100.5), True, 100.25),
        (1.0, 100.5, 100.25, (100.75, 101.0, 100.0, 100.5), False, 100.25),
        (-1.0, 99.5, 99.75, (100.0, 100.25, 99.25, 99.5), True, None),
        (-1.0, 99.5, 99.75, (100.0, 100.25, 99.25, 99.5), False, 99.75),
    ],
)
def test_a_stop_on_its_entry_bar_sees_the_part_of_the_path_its_leg_does(
    side: float,
    level: float,
    stop: float,
    ohlc: tuple[float, float, float, float],
    *,
    last_leg: bool,
    expected: float | None,
) -> None:
    """An earlier leg fills at the open only where its entry's stretch starts there, past its stop."""
    trade = rpt.StoppedEntry("StopMarket", side, level, stop, last_leg, None)
    path = rpt.bar_path(*ohlc)
    point = rpt.entry_point(trade.entry_type, side, level, path)
    assert point is not None
    assert rpt.stop_on_entry_bar(trade, path, point) == expected


@pytest.mark.parametrize(
    ("price", "reported_bar", "key"), [(100.25, 0, "at_stop"), (100.0, 1, "against_path")]
)
def test_a_bar_whose_extremes_are_equally_near_its_open_is_walked_high_first(
    tmp_path: Path, price: float, reported_bar: int, key: str
) -> None:
    """Walked high first, the path comes back through the stop after the entry; low first, it would not."""
    bars = [bar(0, 100.0, 100.0), bar(1, 100.0, 100.5, high=100.75, low=99.25), bar(2, 100.0, 100.0)]
    run = read_run(write_run(tmp_path, stop_entry_events(price, stop_reported_bar=reported_bar), bars))
    stops = rpt.stops_after_entry(rpt.stop_trials(run), run.bars)
    assert stops["gapped"]["entry_bar"][key] == 1
    assert rpt.report(run) is (key == "at_stop")


@pytest.mark.parametrize(
    ("ohlc", "expected"),
    [
        ((100.0, 100.25, 99.0, 99.5), (100.0, 100.25, 99.0, 99.5)),
        ((100.0, 101.0, 99.75, 100.5), (100.0, 99.75, 101.0, 100.5)),
        ((100.0, 100.5, 99.5, 100.0), (100.0, 100.5, 99.5, 100.0)),
    ],
)
def test_a_bar_is_walked_to_the_extreme_nearer_its_open_first(
    ohlc: tuple[float, float, float, float], expected: tuple[float, float, float, float]
) -> None:
    assert rpt.bar_path(*ohlc) == expected


@pytest.mark.parametrize(
    ("entry_type", "side", "level", "expected"),
    [
        ("Market", 1.0, float("nan"), (100.0, 99.0, 101.0, 100.5)),
        ("StopMarket", 1.0, 100.5, (100.5, 101.0, 100.5)),
        ("StopMarket", 1.0, 99.75, (100.0, 99.0, 101.0, 100.5)),
        ("StopMarket", -1.0, 99.5, (99.5, 99.0, 101.0, 100.5)),
        ("Limit", 1.0, 99.5, (99.5, 99.0, 101.0, 100.5)),
        ("Limit", 1.0, 100.25, (100.0, 99.0, 101.0, 100.5)),
        ("Limit", -1.0, 100.75, (100.75, 101.0, 100.5)),
        ("StopMarket", 1.0, 101.25, None),
        ("Limit", 1.0, 99.0, None),
    ],
)
def test_an_entry_fills_where_the_path_first_trades_its_level(
    entry_type: str, side: float, level: float, expected: tuple[float, ...] | None
) -> None:
    """A limit has to trade through its level and a stop only reach it; either fills at an open past it."""
    assert rpt.path_after_entry(entry_type, side, level, (100.0, 99.0, 101.0, 100.5)) == expected


@pytest.mark.parametrize(
    ("side", "stop", "expected"),
    [
        (1.0, 100.75, 100.5),
        (1.0, 100.25, 100.25),
        (1.0, 99.75, None),
        (-1.0, 101.0, 101.0),
        (-1.0, 101.25, None),
    ],
)
def test_a_stop_fills_at_the_paths_first_price_past_it_or_at_its_own(
    side: float, stop: float, expected: float | None
) -> None:
    assert rpt.stop_on_path((100.5, 101.0, 100.0), side, stop) == expected


def test_the_lag_falls_back_to_the_entries_prices_where_nothing_filled_at_market(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, stop_events(), STOP_BARS))
    assert rpt.measure_lag(run)["fills"] == 0
    counts = rpt.measure_lag_on_entries(run)
    assert counts == {"fills": 3, "reported": 0, "reported_plus_one": 1, "both": 2, "neither": 0}
    assert rpt.lag_is_clean(counts)


def test_an_entry_reported_on_the_bar_it_filled_on_is_not_read_as_lagging(tmp_path: Path) -> None:
    """Bar 2 never trades at 99.25, so only bar 1 holds the fill, and it is the bar reported."""
    events = stopped_limit_trial(1, 0, LONG, (99.5, 99.75, 99.25, 99.0), lag=0)
    bars = [bar(0, 100.0, 100.0), bar(1, 99.0, 99.0, high=99.25, low=98.75), bar(2, 100.0, 100.0)]
    run = read_run(write_run(tmp_path, events, bars))
    counts = rpt.measure_lag_on_entries(run)
    assert counts["reported"] == 1
    assert not rpt.lag_is_clean(counts)
    assert rpt.report(run) is False


def test_an_entry_fill_no_bar_traded_at_fails_the_lag(tmp_path: Path) -> None:
    events = stop_events()
    events[3]["execution_price"] = 101.0
    counts = rpt.measure_lag_on_entries(read_run(write_run(tmp_path, events, STOP_BARS)))
    assert counts["neither"] == 1
    assert not rpt.lag_is_clean(counts)


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"at_open": 0, "at_stop": 0, "not_reached": 0, "against_path": 0}, "no instances in this run"),
        ({"at_open": 1, "at_stop": 2, "not_reached": 1, "against_path": 0}, "all 4 as the bar's path says"),
        ({"at_open": 0, "at_stop": 2, "not_reached": 0, "against_path": 1}, "1 of 3 break the rule"),
    ],
)
def test_the_path_verdict_passes_a_set_only_when_every_stop_did_what_its_path_says(
    counts: dict[str, int], expected: str
) -> None:
    assert rpt.path_verdict(counts) == expected


def test_a_trial_reaching_past_the_last_recorded_bar_is_left_out(tmp_path: Path) -> None:
    """The run's last bar takes fills the probe never records, so nothing there can be checked."""
    events = [*stop_events(), *stopped_limit_trial(4, 4, LONG, (98.5, 98.75, 98.0, 97.0), lag=1)]
    run = read_run(write_run(tmp_path, events, STOP_BARS))
    assert rpt.unrecorded_trials(run) == {4}
    assert rpt.report(run) is True


def test_an_entry_left_working_past_its_bar_is_counted_without_failing_the_report(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stuck = event(rpt.STUCK, 4, 5, signal_name=SHORT, order_type="StopMarket", order_state="Working")
    events = [*stop_events(), event(SUBMIT, 4, 3, signal_name=SHORT, order_type="StopMarket"), stuck]
    bars = [*STOP_BARS, bar(5, 99.0, 99.0)]
    run = read_run(write_run(tmp_path, events, bars))
    assert rpt.stuck_entries(run) == 1
    with caplog.at_level(logging.INFO):
        assert rpt.report(run) is True
    assert "entries left working past their bar: 1" in caplog.text


def test_every_trial_inside_the_recorded_bars_is_kept(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, stop_events(), STOP_BARS))
    assert rpt.unrecorded_trials(run) == set()


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"at_open": 0, "at_stop": 0, "at_stop_past_open": 0, "other": 0}, "no instances in this run"),
        (
            {"at_open": 2, "at_stop": 1, "at_stop_past_open": 0, "other": 0},
            "all 3 at the open where the bar opened past the stop, otherwise at the stop",
        ),
        ({"at_open": 1, "at_stop": 0, "at_stop_past_open": 2, "other": 0}, "2 of 3 break the rule"),
        ({"at_open": 1, "at_stop": 1, "at_stop_past_open": 0, "other": 1}, "1 of 3 break the rule"),
    ],
)
def test_the_stop_verdict_passes_a_set_only_when_every_fill_follows_the_rule(
    counts: dict[str, int], expected: str
) -> None:
    assert rpt.stop_verdict(counts) == expected


BAR_PRICES = np.arange(99.0, 101.75, 0.25)
"""The prices every bar shape below is built from."""


@pytest.mark.parametrize(("side", "level", "stop"), [(1.0, 100.5, 100.25), (-1.0, 99.5, 99.75)])
@pytest.mark.parametrize("last_leg", [True, False])
def test_the_tool_reads_a_stop_entrys_bar_as_the_simulation_resolves_it(
    side: float, level: float, stop: float, *, last_leg: bool
) -> None:
    """Two copies of one rule, kept apart so each checks the other, agree on every bar filling the entry.

    ``docs/nt8-fidelity.md``, "A stop on its entry bar is read along the bar's path".
    """
    fills = bracket.FillRules(
        fill_limit_on_touch=False, ambiguity_policy=bracket.AMBIGUITY_NEAREST_TO_OPEN, round_targets=True
    )
    compared = 0
    for open_, high, low, close in itertools.product(BAR_PRICES, repeat=4):
        reached = high if side > 0 else low
        if high < max(open_, close) or low > min(open_, close) or side * (reached - level) < 0:
            continue  # not a bar, or one that never reaches the trigger

        trade = rpt.StoppedEntry("StopMarket", side, level, stop, last_leg, None)
        path = rpt.bar_path(open_, high, low, close)
        point = rpt.entry_point(trade.entry_type, side, level, path)
        assert point is not None
        expected = rpt.stop_on_entry_bar(trade, path, point)

        bars = bracket.Bars(
            open_=np.array([open_]),
            high=np.array([high]),
            low=np.array([low]),
            close=np.array([close]),
            force_flat=np.zeros(1, dtype=np.bool_),
        )
        entry = open_ if side * (open_ - level) >= 0 else level
        opened = bracket.OpenTrade(
            trade_id=1,
            entry_bar=0,
            entry_price=entry,
            initial_stop=stop,
            risk=side * (level - stop),
            direction=side,
            stop_entry=True,
        )
        sim_path = bracket.bar_path(bars, 0)
        sim_point = bracket.stop_entry_point(sim_path, opened, 0.0)
        start = sim_point if last_leg else max(sim_point - 1, 0)
        reason, price, _ = bracket.leg_exit_on_stop_entry_bar(sim_path, start, stop, np.nan, side, fills)
        assert (price if reason == EXIT_STOP else None) == expected, (open_, high, low, close)
        compared += 1

    assert compared > 1000
