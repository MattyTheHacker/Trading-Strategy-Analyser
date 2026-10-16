"""Tests for the order-lifetime probe reader, which is code and can therefore be wrong.

The tool exists to say which bar an order really filled or cancelled on. A reader that reports
the same answer whatever it is handed would settle nothing, so each check below runs twice:
once against a synthetic run where NinjaTrader behaves as the reconciliation found it to, and
once against the same run perturbed in the one way that check exists to catch.

The perturbation for the lag check is **the other candidate reading** -- a callback whose
reported bar already explains the fill. That is what a run would look like if Strategy Analyzer
processed fills after advancing the bar rather than before, and it is the reading that would
shift every lifetime in this file by one bar.
"""

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from tools import reconcile_order_lifetime as rol

if TYPE_CHECKING:
    from pathlib import Path

EVENT_COLUMNS = [
    "kind",
    "trial",
    "bar",
    "bar_utc",
    "bar_local",
    "is_first_bar_of_session",
    "signal_name",
    "submitted_luc",
    "order_luc",
    "order_id",
    "order_action",
    "order_type",
    "stop_price",
    "limit_price",
    "quantity",
    "filled",
    "average_fill_price",
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
    "primary_state",
    "secondary_state",
    "is_last_bar_of_session",
]

TRIGGER = 100.0


def event(kind: str, trial: int, bar: int, signal: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(EVENT_COLUMNS, "")
    row.update(
        kind=kind,
        trial=trial,
        bar=bar,
        signal_name=signal,
        is_first_bar_of_session=0,
        order_action="Buy",
        order_type="StopMarket",
        stop_price=TRIGGER,
        quantity=1,
        filled=0,
        average_fill_price=0.0,
        is_last_bar_of_session=0,
    )
    row.update(overrides)

    return row


def bar(
    index: int, high: float, *, low: float = 90.0, close: float = 95.0, **overrides: object
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(BAR_COLUMNS, "")
    row.update(
        bar=index,
        open=92.0,
        high=high,
        low=low,
        close=close,
        volume=10,
        market_position="Flat",
        position_quantity=0,
        primary_state="Working",
        secondary_state="none",
        is_first_bar_of_session=0,
        is_last_bar_of_session=0,
    )
    row.update(overrides)

    return row


def write_run(
    tmp_path: Path,
    events: list[dict[str, object]],
    bars: list[dict[str, object]],
    config: list[dict[str, object]] | None = None,
    stem: str = "SYN_s2",
) -> Path:
    """Write a synthetic probe run and return the path to its events file."""
    events_path = tmp_path / f"{stem}_events.csv"
    pd.DataFrame(events, columns=EVENT_COLUMNS).to_csv(events_path, sep=";", index=False)
    pd.DataFrame(bars, columns=BAR_COLUMNS).to_csv(tmp_path / f"{stem}_bars.csv", sep=";", index=False)
    if config is not None:
        pd.DataFrame(config).to_csv(tmp_path / f"{stem}_config.csv", sep=";", index=False)

    return events_path


def one_fill(reported_bar: int) -> list[dict[str, object]]:
    """Build a trial submitted at bar 0 whose fill callback reports ``reported_bar``."""
    return [
        event("SUBMIT", 1, 0, "probe1"),
        event("ORDER_UPDATE", 1, 0, "probe1", order_state="Working"),
        event(
            "ORDER_UPDATE",
            1,
            reported_bar,
            "probe1",
            order_state="Filled",
            filled=1,
            average_fill_price=TRIGGER,
        ),
        event(
            "EXECUTION", 1, reported_bar, "probe1", order_state="Filled", filled=1, average_fill_price=TRIGGER
        ),
    ]


# Bar 1 is the only bar that reaches the trigger, so a fill is explained by bar 1 and by
# nothing else. Which bar the callback *names* is then the whole question.
REACHING_BARS = [bar(0, high=95.0), bar(1, high=105.0), bar(2, high=95.0)]


def test_the_lag_is_measured_as_plus_one_when_only_the_next_bar_reaches_the_trigger(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS))
    assert rol.measure_entry_lag(run) == {
        "fills": 1,
        "reported": 0,
        "reported_plus_one": 1,
        "unresolved": 0,
    }


def test_a_callback_naming_the_bar_that_reaches_the_trigger_is_not_read_as_lagging(tmp_path: Path) -> None:
    """The other candidate reading, which must not be reported as a clean +1."""
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=1), REACHING_BARS))
    counts = rol.measure_entry_lag(run)
    assert counts["reported"] == 1
    assert counts["reported_plus_one"] == 0
    assert rol.report(run) is False


def test_report_accepts_a_run_whose_lag_is_a_clean_plus_one(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS))
    assert rol.report(run) is True


def test_a_short_entry_is_measured_against_the_low(tmp_path: Path) -> None:
    """The sign multiplier's counterpart here: a sell stop fills on a low, not a high."""
    events = [
        event("SUBMIT", 1, 0, "probe2", order_action="SellShort"),
        event(
            "EXECUTION",
            1,
            0,
            "probe2",
            order_action="SellShort",
            order_state="Filled",
            filled=1,
            average_fill_price=TRIGGER,
        ),
    ]
    bars = [bar(0, high=95.0, low=99.0), bar(1, high=99.0, low=85.0)]
    run = rol.read_run(write_run(tmp_path, events, bars))
    assert rol.measure_entry_lag(run)["reported_plus_one"] == 1


def test_a_fill_with_no_bar_row_either_side_is_counted_unresolved(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=40), REACHING_BARS))
    assert rol.measure_entry_lag(run)["unresolved"] == 1


def test_the_session_close_exit_is_measured_at_the_reported_bars_close(tmp_path: Path) -> None:
    events = [
        event(
            "EXECUTION", 1, 1, rol.SESSION_CLOSE_EXIT, order_state="Filled", filled=1, average_fill_price=95.0
        )
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    counts = rol.measure_session_close_exit_lag(run)
    assert counts == {"exits": 1, "at_reported_close": 1, "inside_reported": 1, "unresolved": 0}


def test_a_session_close_exit_away_from_the_reported_close_is_not_counted(tmp_path: Path) -> None:
    events = [
        event(
            "EXECUTION",
            1,
            1,
            rol.SESSION_CLOSE_EXIT,
            order_state="Filled",
            filled=1,
            average_fill_price=104.0,
        )
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    counts = rol.measure_session_close_exit_lag(run)
    assert counts["at_reported_close"] == 0
    assert counts["inside_reported"] == 1


def test_a_three_argument_entry_lives_exactly_one_bar(tmp_path: Path) -> None:
    """The reconciled control: submitted at i, cancelled during the pass for i+2."""
    events = [
        event("SUBMIT", 1, 0, "probe2"),
        event("ORDER_UPDATE", 1, 0, "probe2", order_state="Working"),
        event("ORDER_UPDATE", 1, 1, "probe2", order_state="Cancelled"),
    ]
    frame = rol.lifetimes(rol.read_run(write_run(tmp_path, events, REACHING_BARS)), "probe2")
    assert rol.offsets_from_submit(frame, "cancelled") == {2: 1}
    assert bool(frame["acknowledged"].iloc[0]) is True


def test_an_unacknowledged_submission_is_reported_as_refused(tmp_path: Path) -> None:
    """A SUBMIT with no order update behind it -- how a refusal differs from a cancel."""
    events = [
        event("SUBMIT", 1, 0, "probe1"),
        event("ORDER_UPDATE", 1, 0, "probe1", order_state="Working"),
        event("SUBMIT", 1, 0, "probe2", order_action="SellShort"),
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    assert rol.refused_submissions(run) == {"probe1": 0, "probe2": 1}


def test_a_cancelled_order_that_never_filled_afterwards_reports_zero(tmp_path: Path) -> None:
    events = [
        event("SUBMIT", 1, 0, "probe1"),
        event("CANCEL_REQUEST", 1, 2, "probe1"),
        event("ORDER_UPDATE", 1, 2, "probe1", order_state="Cancelled"),
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    assert rol.fills_after_cancel(run) == {
        "cancel_requested": 1,
        "filled_on_the_request_bar": 0,
        "filled_after_the_request_bar": 0,
    }


def test_a_fill_after_the_cancel_request_is_caught(tmp_path: Path) -> None:
    """The finding this check exists to falsify: nothing filled after its cancel was issued."""
    events = [
        event("SUBMIT", 1, 0, "probe1"),
        event("CANCEL_REQUEST", 1, 2, "probe1"),
        event("ORDER_UPDATE", 1, 4, "probe1", order_state="Filled", filled=1),
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    assert rol.fills_after_cancel(run)["filled_after_the_request_bar"] == 1


def test_session_edge_counts_come_from_ninjatraders_own_last_bar_flag(tmp_path: Path) -> None:
    events = [
        event("SUBMIT", 1, 0, "probe1", is_last_bar_of_session=1),
        event(
            "EXECUTION",
            1,
            0,
            "probe1",
            order_state="Filled",
            filled=1,
            average_fill_price=TRIGGER,
            is_last_bar_of_session=1,
        ),
    ]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    edge = rol.last_bar_fills(run)
    assert edge["submits_on_a_last_bar"] == 1
    assert edge["fills_on_a_last_bar"] == 0  # corrected to bar 1, which is not flagged


def test_an_export_without_the_last_bar_column_reports_no_session_edge(tmp_path: Path) -> None:
    """Runs made before the column was added must degrade, not raise."""
    events_path = write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS)
    frame = pd.read_csv(events_path, sep=";").drop(columns=["is_last_bar_of_session"])
    frame.to_csv(events_path, sep=";", index=False)
    assert rol.last_bar_fills(rol.read_run(events_path)) == {}


def test_the_effective_settings_are_read_when_a_config_file_is_present(tmp_path: Path) -> None:
    config = [
        {
            "stage": "Terminated",
            "is_exit_on_session_close_strategy": True,
            "exit_on_session_close_seconds": 300,
            "entries_per_direction": 2,
            "entry_handling": "AllEntries",
            "calculate": "OnBarClose",
            "order_fill_resolution": "Standard",
            "slippage": 0,
            "time_in_force": "Gtc",
            "bars_required_to_trade": 0,
        }
    ]
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS, config))
    assert run.config is not None
    assert int(run.config.iloc[-1]["exit_on_session_close_seconds"]) == 300


def test_a_run_without_a_config_file_still_loads(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS))
    assert run.config is None


def test_a_path_that_is_not_an_events_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"expected a probe _events\.csv"):
        rol.read_run(tmp_path / "SYN_s2_bars.csv")


def test_a_missing_bar_export_is_refused_by_name(tmp_path: Path) -> None:
    events_path = write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS)
    (tmp_path / "SYN_s2_bars.csv").unlink()
    with pytest.raises(FileNotFoundError, match=r"SYN_s2_bars\.csv"):
        rol.read_run(events_path)


def test_a_long_offset_distribution_is_summarised_rather_than_dumped(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    for trial in range(rol.MAX_DISTINCT_OFFSETS + 2):
        events.append(event("SUBMIT", trial, 0, "probe1"))
        events.append(event("ORDER_UPDATE", trial, trial, "probe1", order_state="Filled", filled=1))
    frame = rol.lifetimes(rol.read_run(write_run(tmp_path, events, REACHING_BARS)), "probe1")
    described = rol.describe_offsets(frame, "filled")
    assert "distinct offsets" in described
    assert "median" in described


def test_a_short_offset_distribution_is_shown_exactly(tmp_path: Path) -> None:
    events = [
        event("SUBMIT", 1, 0, "probe1"),
        event("ORDER_UPDATE", 1, 0, "probe1", order_state="Filled", filled=1),
    ]
    frame = rol.lifetimes(rol.read_run(write_run(tmp_path, events, REACHING_BARS)), "probe1")
    assert rol.describe_offsets(frame, "filled") == "{1: 1}"


def test_an_absent_state_describes_as_none(tmp_path: Path) -> None:
    events = [event("SUBMIT", 1, 0, "probe1")]
    frame = rol.lifetimes(rol.read_run(write_run(tmp_path, events, REACHING_BARS)), "probe1")
    assert rol.describe_offsets(frame, "filled") == "none"


MARKET_FILL = {"order_type": "Market", "stop_price": 0.0, "order_state": "Filled", "filled": 1}

# Every bar opens at a different price, so a market fill's price names the one bar it filled on.
OPENING_BARS = [bar(index, high=110.0, open=100.0 + index) for index in range(4)]


def market_entry(reported_bar: int, price: float) -> list[dict[str, object]]:
    """Build a market entry submitted at bar 0 whose fill callback reports ``reported_bar``."""
    return [
        event("SUBMIT", 1, 0, "probe1", order_type="Market", stop_price=""),
        event("EXECUTION", 1, reported_bar, "probe1", **MARKET_FILL, average_fill_price=price),
    ]


def test_a_market_entry_is_measured_against_the_next_bars_open(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, market_entry(reported_bar=0, price=101.0), OPENING_BARS))
    counts = rol.measure_market_entry_lag(run)
    assert counts == {"fills": 1, "reported": 0, "reported_plus_one": 1, "both": 0, "neither": 0}
    assert rol.measure_entry_lag(run)["fills"] == 0
    assert rol.report(run) is True


def test_a_market_fill_at_the_reported_bars_own_open_is_not_read_as_lagging(tmp_path: Path) -> None:
    """The other candidate reading, which must fail the run."""
    run = rol.read_run(write_run(tmp_path, market_entry(reported_bar=0, price=100.0), OPENING_BARS))
    assert rol.measure_market_entry_lag(run)["reported"] == 1
    assert rol.report(run) is False


def test_a_market_fill_both_opens_explain_decides_nothing(tmp_path: Path) -> None:
    bars = [bar(0, high=110.0, open=100.0), bar(1, high=110.0, open=100.0)]
    run = rol.read_run(write_run(tmp_path, market_entry(reported_bar=0, price=100.0), bars))
    counts = rol.measure_market_entry_lag(run)
    assert counts["both"] == 1
    assert rol.lag_is_clean(counts) is False


def test_a_market_fill_neither_open_explains_fails_the_run(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, market_entry(reported_bar=0, price=105.5), OPENING_BARS))
    assert rol.measure_market_entry_lag(run)["neither"] == 1
    assert rol.report(run) is False


def test_a_good_stop_fill_does_not_cover_for_a_bad_market_fill(tmp_path: Path) -> None:
    events = [*one_fill(reported_bar=0), *market_entry(reported_bar=0, price=100.0)]
    bars = [bar(0, high=95.0, open=100.0), bar(1, high=105.0, open=101.0), bar(2, high=95.0, open=102.0)]
    run = rol.read_run(write_run(tmp_path, events, bars))
    assert rol.stop_lag_is_clean(rol.measure_entry_lag(run)) is True
    assert rol.report(run) is False


def test_a_run_whose_stop_and_market_fills_both_lag_one_bar_passes(tmp_path: Path) -> None:
    events = [*one_fill(reported_bar=0), *market_entry(reported_bar=0, price=101.0)]
    bars = [bar(0, high=95.0, open=100.0), bar(1, high=105.0, open=101.0), bar(2, high=95.0, open=102.0)]
    assert rol.report(rol.read_run(write_run(tmp_path, events, bars))) is True


def test_an_entry_fill_of_another_order_type_is_still_measured_as_a_stop(tmp_path: Path) -> None:
    """Only a market fill leaves the trigger check; nothing drops out of both."""
    events = [{**row, "order_type": "StopLimit"} for row in one_fill(reported_bar=1)]
    run = rol.read_run(write_run(tmp_path, events, REACHING_BARS))
    assert rol.measure_entry_lag(run)["fills"] == 1
    assert rol.report(run) is False


def exit_and_entry(
    action: str, *, acknowledged: bool, fills: tuple[str, ...], trial: int = 1, pair_bar: int = 1
) -> list[dict[str, object]]:
    """Build one scenario 7 trial: its long, the pair sent at ``pair_bar``, and the flatten after a reversal.

    Every fill reports the bar before the one it fills on, at that bar's open from ``pair_bars``.
    """
    market = {"order_type": "Market", "stop_price": ""}
    rows = [
        event("SUBMIT", trial, pair_bar - 1, "probe1", **market),
        event("EXECUTION", trial, pair_bar - 1, "probe1", **MARKET_FILL, average_fill_price=100.0 + pair_bar),
        event("SUBMIT", trial, pair_bar, rol.EXIT_LONG, order_action="Sell", **market),
        event("SUBMIT", trial, pair_bar, rol.SECOND_ENTRY, order_action=action, **market),
    ]
    if acknowledged:
        working = {"order_state": "Working", "order_type": "Market"}
        rows.append(event("ORDER_UPDATE", trial, pair_bar, rol.SECOND_ENTRY, order_action=action, **working))
        rows.append(
            event("ORDER_UPDATE", trial, pair_bar, rol.CLOSE_POSITION, order_action="Sell", **working)
        )
        flatten_price = 102.0 + pair_bar
        rows.append(
            event(
                "EXECUTION",
                trial,
                pair_bar + 1,
                "Buy to cover",
                **MARKET_FILL,
                average_fill_price=flatten_price,
            )
        )

    pair_price = 101.0 + pair_bar
    rows.extend(
        event("EXECUTION", trial, pair_bar, name, **MARKET_FILL, average_fill_price=pair_price)
        for name in fills
    )

    return rows


def pair_bars(position: str, quantity: int, count: int = 4) -> list[dict[str, object]]:
    """Build bars opening a point apart, bar 2 holding the position the pair at bar 1 left."""
    bars = [bar(index, high=110.0, open=100.0 + index) for index in range(count)]
    if count > 2:
        bars[2].update(market_position=position, position_quantity=quantity)

    return bars


def test_a_same_side_entry_beside_an_exit_reads_as_ignored(tmp_path: Path) -> None:
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0)))
    assert rol.pair_outcomes(rol.exit_and_entry_pairs(run)) == {
        "same side": {
            "pairs": 1,
            "entry_acknowledged": 0,
            "position_after": {"Flat 0": 1},
            "filled": {"Sell": 1},
            "all_fills_at_the_open": 1,
            "close_position_sent": 0,
            "close_position_filled": 0,
        }
    }


def test_an_other_side_entry_beside_an_exit_reads_as_one_clean_reversal(tmp_path: Path) -> None:
    events = exit_and_entry("SellShort", acknowledged=True, fills=(rol.EXIT_LONG, rol.SECOND_ENTRY))
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Short", 1)))
    outcome = rol.pair_outcomes(rol.exit_and_entry_pairs(run))["other side"]
    assert outcome["position_after"] == {"Short 1": 1}
    assert outcome["filled"] == {"Sell+probe2": 1}
    assert outcome["close_position_sent"] == 1
    assert outcome["close_position_filled"] == 0


def test_a_reversal_that_closes_twice_is_told_from_a_clean_one(tmp_path: Path) -> None:
    """The reading question 2 exists to rule out: NinjaTrader's own close fills beside the exit."""
    fills = (rol.CLOSE_POSITION, rol.EXIT_LONG, rol.SECOND_ENTRY)
    events = exit_and_entry("SellShort", acknowledged=True, fills=fills)
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Short", 2)))
    outcome = rol.pair_outcomes(rol.exit_and_entry_pairs(run))["other side"]
    assert outcome["position_after"] == {"Short 2": 1}
    assert outcome["filled"] == {"Close position+Sell+probe2": 1}
    assert outcome["close_position_filled"] == 1


def test_a_pair_fill_away_from_the_open_is_not_counted_at_it(tmp_path: Path) -> None:
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    events[-1]["average_fill_price"] = 101.0
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0)))
    assert rol.pair_outcomes(rol.exit_and_entry_pairs(run))["same side"]["all_fills_at_the_open"] == 0


def test_a_pair_with_nothing_filled_is_not_counted_at_the_open(tmp_path: Path) -> None:
    events = exit_and_entry("Buy", acknowledged=False, fills=())
    outcome = rol.pair_outcomes(
        rol.exit_and_entry_pairs(rol.read_run(write_run(tmp_path, events, pair_bars("Long", 1))))
    )
    assert outcome["same side"]["filled"] == {"none": 1}
    assert outcome["same side"]["all_fills_at_the_open"] == 0


def test_a_session_close_exit_on_the_pair_bar_is_not_read_as_a_pair_fill(tmp_path: Path) -> None:
    """That exit does not lag, so shifting it a bar would land it on the pair's fill bar."""
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    events.append(event("EXECUTION", 1, 1, rol.SESSION_CLOSE_EXIT, **MARKET_FILL, average_fill_price=95.0))
    outcome = rol.pair_outcomes(
        rol.exit_and_entry_pairs(rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0))))
    )
    assert outcome["same side"]["filled"] == {"Sell": 1}
    assert outcome["same side"]["all_fills_at_the_open"] == 1


@pytest.mark.parametrize("entry_action", ["Sell short", None])
def test_a_pair_whose_entry_is_unrecognised_or_missing_is_still_counted(
    tmp_path: Path, entry_action: str | None
) -> None:
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    entry = next(row for row in events if row["kind"] == "SUBMIT" and row["signal_name"] == rol.SECOND_ENTRY)
    if entry_action is None:
        events.remove(entry)
    else:
        entry["order_action"] = entry_action

    outcome = rol.pair_outcomes(
        rol.exit_and_entry_pairs(rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0))))
    )
    assert outcome[rol.UNKNOWN_SIDE]["pairs"] == 1


def test_a_close_position_row_on_a_later_bar_is_not_read_as_the_pairs(tmp_path: Path) -> None:
    """A callback carries whichever trial the probe is on, not the order's own."""
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    events.append(
        event("ORDER_UPDATE", 1, 3, rol.CLOSE_POSITION, order_action="Sell", order_state="Cancelled")
    )
    outcome = rol.pair_outcomes(
        rol.exit_and_entry_pairs(rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0))))
    )
    assert outcome["same side"]["close_position_sent"] == 0


def test_a_recorded_pairs_position_stays_whole_beside_an_unrecorded_one(tmp_path: Path) -> None:
    events = [
        *exit_and_entry("SellShort", acknowledged=True, fills=(rol.EXIT_LONG, rol.SECOND_ENTRY)),
        *exit_and_entry(
            "SellShort", acknowledged=True, fills=(rol.EXIT_LONG, rol.SECOND_ENTRY), trial=2, pair_bar=3
        ),
    ]
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Short", 1)))
    outcomes = rol.pair_outcomes(rol.exit_and_entry_pairs(run))
    assert outcomes["other side"]["position_after"] == {"Short 1": 1}
    assert outcomes["unrecorded"] == {"pairs": 1}


def test_a_pair_whose_fill_bar_was_never_recorded_is_counted_apart(tmp_path: Path) -> None:
    events = exit_and_entry("Buy", acknowledged=False, fills=(rol.EXIT_LONG,))
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Flat", 0, count=2)))
    assert rol.pair_outcomes(rol.exit_and_entry_pairs(run)) == {"unrecorded": {"pairs": 1}}


def test_a_run_without_a_pair_reports_no_pair_outcomes(tmp_path: Path) -> None:
    run = rol.read_run(write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS))
    assert rol.pair_outcomes(rol.exit_and_entry_pairs(run)) == {}
    assert rol.close_position_states(run) == {}


def test_every_close_position_row_is_counted_by_kind_and_state(tmp_path: Path) -> None:
    events = exit_and_entry("SellShort", acknowledged=True, fills=(rol.EXIT_LONG, rol.SECOND_ENTRY))
    events.append(
        event("ORDER_UPDATE", 1, 1, rol.CLOSE_POSITION, order_action="Sell", order_state="Accepted")
    )
    run = rol.read_run(write_run(tmp_path, events, pair_bars("Short", 1)))
    assert rol.close_position_states(run) == {"ORDER_UPDATE Accepted": 1, "ORDER_UPDATE Working": 1}


def test_main_reports_usage_when_given_no_export() -> None:
    assert rol.main(["reconcile_order_lifetime.py"]) == 2


def test_main_returns_zero_on_a_run_whose_lag_is_clean(tmp_path: Path) -> None:
    path = write_run(tmp_path, one_fill(reported_bar=0), REACHING_BARS)
    assert rol.main(["reconcile_order_lifetime.py", str(path)]) == 0


def test_main_returns_one_on_a_run_whose_lag_is_not(tmp_path: Path) -> None:
    path = write_run(tmp_path, one_fill(reported_bar=1), REACHING_BARS)
    assert rol.main(["reconcile_order_lifetime.py", str(path)]) == 1
