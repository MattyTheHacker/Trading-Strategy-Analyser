"""Tests for the passed-target probe reader.

Each price check runs against three readings -- the measured rule, the target's own price and the
open -- and each trial set holds a long and a short.
"""

import logging
from typing import TYPE_CHECKING

import pandas as pd
import pytest

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
) -> Path:
    """Write a synthetic probe run and return the path to its events file."""
    events_path = tmp_path / "SYN_s1_events.csv"
    pd.DataFrame(events, columns=EVENT_COLUMNS).to_csv(events_path, sep=";", index=False)
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
