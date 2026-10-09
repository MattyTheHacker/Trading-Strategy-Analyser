"""Tests for the passed-target probe reader.

Each price check runs against both readings, at the target and at the open, and each trial set
holds a long and a short.
"""

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from tools import reconcile_passed_target as rpt
from tools.reconcile_order_lifetime import EXECUTION, ORDER_UPDATE, read_run

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
        EXECUTION, trial, reported_bar, signal_name=entry, order_state="Filled", execution_price=price
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
ENTRY_BAR_BARS = [bar(0, 100.0, 100.0), bar(1, 100.25, 100.5), bar(2, 100.5, 100.75), bar(3, 100.75, 100.75)]
LONG_TARGET = 99.0
SHORT_TARGET = 101.5


def entry_bar_events(*, at_open: bool, lag: int = 1, target_lag: int = 0) -> list[dict[str, object]]:
    """Build the two scenario-1 trials, each target filling at the open or at its own price.

    ``lag`` is how far the entry callbacks report behind their fill bar, and ``target_lag`` how
    many bars after its entry the target filled.
    """
    long_fill = 100.25 if at_open else LONG_TARGET
    short_fill = 100.5 if at_open else SHORT_TARGET
    if target_lag:
        long_fill = 100.5 if at_open else LONG_TARGET
        short_fill = 100.75 if at_open else SHORT_TARGET

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


@pytest.mark.parametrize(("at_open", "key"), [(True, "at_open"), (False, "at_target")])
def test_a_target_passed_at_the_entry_is_read_at_the_price_it_filled_at(
    tmp_path: Path, *, at_open: bool, key: str
) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=at_open), ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert counts["trials"]["entries"] == 2
    assert counts["trials"]["passed"] == 2  # the short is passed only if its side is read
    assert counts["on_entry_bar"][key] == 2
    assert sum(counts["on_entry_bar"].values()) == 2
    assert sum(counts["on_a_later_bar"].values()) == 0


def test_a_passed_target_filling_a_bar_later_is_told_from_one_filling_on_the_entry_bar(
    tmp_path: Path,
) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=True, target_lag=1), ENTRY_BAR_BARS))
    counts = rpt.passed_at_entry(rpt.trials(run), run.bars)
    assert sum(counts["on_entry_bar"].values()) == 0
    assert counts["on_a_later_bar"] == {"at_target": 0, "at_open": 2, "other": 0}


def test_a_passed_target_filling_later_is_not_read_as_a_resting_one(tmp_path: Path) -> None:
    """It sat behind the previous close, so the bar it filled on did not gap through it."""
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=False, target_lag=1), ENTRY_BAR_BARS))
    resting = rpt.gapped_while_resting(rpt.trials(run), run.bars)
    assert resting == {
        "gapped": {"at_target": 0, "at_open": 0, "other": 0},
        "control": {"at_target": 0, "at_open": 0, "other": 0},
        "control_bar": {"inside": 0, "outside": 0},
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


def test_every_target_tied_to_its_trials_entry_is_attributed(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=True), ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 0


def test_a_target_naming_another_entry_is_caught_and_fails_the_report(tmp_path: Path) -> None:
    events = entry_bar_events(at_open=True)
    events[3]["from_entry_signal"] = SHORT
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 1
    assert rpt.report(run) is False


def test_a_target_in_a_trial_with_no_entry_is_caught(tmp_path: Path) -> None:
    events = [*entry_bar_events(at_open=True), target_fill(3, 2, LONG, LONG_TARGET, 100.75)]
    run = read_run(write_run(tmp_path, events, ENTRY_BAR_BARS))
    assert rpt.misattributed_targets(run, rpt.trials(run)) == 1


def test_the_lag_is_a_clean_plus_one_when_every_entry_is_the_next_bars_open(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=True), ENTRY_BAR_BARS))
    counts = rpt.measure_entry_lag(run)
    assert counts == {"fills": 2, "reported": 0, "reported_plus_one": 2, "both": 0, "neither": 0}
    assert rpt.lag_is_clean(counts)


def test_a_callback_naming_the_bar_it_filled_on_is_not_read_as_lagging(tmp_path: Path) -> None:
    """The other candidate reading, which must not pass as a clean +1."""
    run = read_run(write_run(tmp_path, entry_bar_events(at_open=True, lag=0), ENTRY_BAR_BARS))
    counts = rpt.measure_entry_lag(run)
    assert counts["reported"] == 2
    assert not rpt.lag_is_clean(counts)
    assert rpt.report(run) is False


def test_an_entry_two_equal_opens_explain_decides_nothing(tmp_path: Path) -> None:
    bars = [bar(0, 100.25, 100.0), bar(1, 100.25, 100.5)]
    run = read_run(write_run(tmp_path, [entry_fill(1, 0, LONG, 100.25)], bars))
    counts = rpt.measure_entry_lag(run)
    assert counts["both"] == 1
    assert not rpt.lag_is_clean(counts)


def test_an_entry_no_open_explains_fails_the_lag_check(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, [entry_fill(1, 0, LONG, 100.125)], ENTRY_BAR_BARS))
    counts = rpt.measure_entry_lag(run)
    assert counts["neither"] == 1
    assert not rpt.lag_is_clean(counts)


def test_a_run_with_no_entry_fills_does_not_pass_the_lag_check(tmp_path: Path) -> None:
    """A probe that traded nothing has measured nothing, and must not read as clean."""
    run = read_run(write_run(tmp_path, [target_set(1, 0, LONG, LONG_TARGET)], ENTRY_BAR_BARS))
    assert not rpt.lag_is_clean(rpt.measure_entry_lag(run))


# Scenario 2. A long entered at bar 1's open has its target moved to a tick over bar 1's close;
# bar 2 opens three ticks over that, so the target is gapped through. A short entered at bar 3's
# open has its target moved to a tick under bar 3's close; bar 4 opens short of it and trades
# through, which is the control.
RESTING_BARS = [
    bar(0, 100.0, 100.0),
    bar(1, 100.25, 100.0),
    bar(2, 101.0, 101.0),
    bar(3, 100.75, 100.5),
    bar(4, 100.5, 100.25, low=100.0),
]
GAPPED_TARGET = 100.25
CONTROL_TARGET = 100.25


def resting_events(*, at_open: bool) -> list[dict[str, object]]:
    """Build the two scenario-2 trials, the gapped target filling at the open or at its own price."""
    return [
        target_set(1, 0, LONG, 2100.0),
        entry_fill(1, 0, LONG, 100.25),
        target_set(1, 1, LONG, GAPPED_TARGET),
        target_fill(1, 1, LONG, GAPPED_TARGET, 101.0 if at_open else GAPPED_TARGET),
        target_set(2, 2, SHORT, 51.0),
        entry_fill(2, 2, SHORT, 100.75),
        target_set(2, 3, SHORT, CONTROL_TARGET),
        target_fill(2, 3, SHORT, CONTROL_TARGET, CONTROL_TARGET),
    ]


@pytest.mark.parametrize(("at_open", "key"), [(True, "at_open"), (False, "at_target")])
def test_a_gapped_through_target_is_read_at_the_price_it_filled_at(
    tmp_path: Path, *, at_open: bool, key: str
) -> None:
    run = read_run(write_run(tmp_path, resting_events(at_open=at_open), RESTING_BARS))
    resting = rpt.gapped_while_resting(rpt.trials(run), run.bars)
    assert resting["gapped"][key] == 1
    assert sum(resting["gapped"].values()) == 1
    assert resting["control"] == {"at_target": 1, "at_open": 0, "other": 0}
    assert resting["control_bar"] == {"inside": 1, "outside": 0}


def test_a_control_fill_outside_its_bar_fails_the_report(tmp_path: Path) -> None:
    """Bar 4 never trades down to the short's target, so a fill there names the wrong bar."""
    bars = [*RESTING_BARS[:4], bar(4, 100.5, 100.75, low=100.5)]
    run = read_run(write_run(tmp_path, resting_events(at_open=True), bars))
    assert rpt.gapped_while_resting(rpt.trials(run), run.bars)["control_bar"] == {"inside": 0, "outside": 1}
    assert rpt.report(run) is False


def test_an_out_of_reach_target_at_the_entry_is_not_read_as_passed(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, resting_events(at_open=True), RESTING_BARS))
    assert rpt.passed_at_entry(rpt.trials(run), run.bars)["trials"]["passed"] == 0


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"at_target": 0, "at_open": 0, "other": 0}, "no instances in this run"),
        ({"at_target": 3, "at_open": 0, "other": 0}, "all 3 at the target's own price"),
        ({"at_target": 0, "at_open": 3, "other": 0}, "all 3 at the fill bar's open"),
        ({"at_target": 2, "at_open": 1, "other": 0}, "mixed over 3 -- read the counts"),
        ({"at_target": 0, "at_open": 2, "other": 1}, "mixed over 3 -- read the counts"),
    ],
)
def test_the_verdict_names_a_price_only_when_every_fill_agrees(counts: dict[str, int], expected: str) -> None:
    assert rpt.verdict(counts) == expected


def test_report_reads_a_run_with_its_config(tmp_path: Path) -> None:
    run = read_run(write_run(tmp_path, resting_events(at_open=True), RESTING_BARS, config=True))
    assert run.config is not None
    assert rpt.report(run) is True


def test_main_reports_usage_when_given_no_export() -> None:
    assert rpt.main(["reconcile_passed_target.py"]) == 2


def test_main_returns_zero_on_a_run_whose_lag_is_clean(tmp_path: Path) -> None:
    path = write_run(tmp_path, entry_bar_events(at_open=True), ENTRY_BAR_BARS)
    assert rpt.main(["reconcile_passed_target.py", str(path)]) == 0


def test_main_returns_one_on_a_run_whose_lag_is_not(tmp_path: Path) -> None:
    path = write_run(tmp_path, entry_bar_events(at_open=True, lag=0), ENTRY_BAR_BARS)
    assert rpt.main(["reconcile_passed_target.py", str(path)]) == 1
