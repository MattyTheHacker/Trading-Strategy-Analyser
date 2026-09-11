"""Re-summarising a shortlist with one exit reason's legs removed.

Two claims carry this module. **Net P&L is additive across the split and profit factor is not**,
which is the whole reason a tool exists rather than a subtraction on the decomposition
``tools/campaign_report.py`` already prints. And **every figure stays ``stats.summarise``'s over
a subset**, because a second definition of a profit factor here would drift from the sweep's
silently and both numbers would look reasonable.

The third thing tested is arithmetic rather than a claim: the two halves must partition the log,
since a leg counted in both or in neither moves a total nothing else would check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import results, stats, trades
from tools import campaign_exits
from tools.campaign_exits import (
    PASS_MARK,
    REPORTED,
    labelled,
    main,
    measure,
    measure_row,
    split_on,
    summary_of,
    survival,
    verify,
)
from tools.campaign_report import NET_TO_DRAWDOWN

SWEEP_ID = 58
COMBO_ID = 1473
FLATTEN = stats.SESSION_CLOSE


def leg_log(legs: list[tuple[float, str]]) -> pd.DataFrame:
    """A one-leg-per-trade log from ``(net_pnl, exit_reason)`` pairs, one trade an hour."""
    pnl = np.array([net for net, _ in legs], dtype=float)
    exits = pd.Timestamp("2024-09-03 18:00", tz="UTC") + pd.to_timedelta(np.arange(len(legs)), unit="h")

    return pd.DataFrame(
        {
            "source": "sim",
            "instrument": "MNQ",
            "trade_id": np.arange(1, len(legs) + 1),
            "leg": 1,
            "quantity": 4,
            "direction": 1.0,
            "gross_pnl": pnl + 6.0,
            "commission": 6.0,
            "net_pnl": pnl,
            "bars_held": 60,
            "mae_points": 4.0,
            "mfe_points": 4.0,
            "r_multiple": pnl / 200.0,
            "ambiguous_bar": False,
            "exit_reason": [reason for _, reason in legs],
            "entry_time": exits - pd.Timedelta(hours=5),
            "exit_time": exits,
        },
    )


CARRIED = [(900.0, FLATTEN), (800.0, FLATTEN), (-300.0, "stop"), (-400.0, "stop"), (200.0, "target")]
"""A book the flatten pays for: +1,700 from the clock against -500 from the bracket."""


def stored_row(log: pd.DataFrame, **columns: object) -> pd.Series:
    """The held-out row a log is filed against, carrying the net P&L it must reproduce."""
    base = {
        "sweep_id": SWEEP_ID,
        "combo_id": COMBO_ID,
        "root": "MNQ",
        "resolution": 5,
        "variant": "window=30m stop=opposite target=R",
        "stratum": "phase=MIDDAY",
        "window": "holdout",
        "net_pnl": float(log["net_pnl"].sum()),
    }

    return pd.Series({**base, **columns})


@pytest.fixture
def stocked(tmp_path):
    """A database holding one stored log, at the ids the held-out row names."""
    db = tmp_path / "OpeningRange.duckdb"
    results.save_trades(leg_log(CARRIED), SWEEP_ID, COMBO_ID, db)

    return db


# -- the split is a partition ----------------------------------------------------------------


def test_the_two_halves_hold_every_leg_once() -> None:
    """A leg in both or in neither moves a total that nothing else here would check."""
    log = leg_log(CARRIED)
    removed, residual = split_on(log, FLATTEN)
    assert len(removed) + len(residual) == len(log)
    assert set(removed["trade_id"]).isdisjoint(residual["trade_id"])
    assert removed["net_pnl"].sum() + residual["net_pnl"].sum() == pytest.approx(log["net_pnl"].sum())


def test_an_exit_reason_the_log_never_took_leaves_the_book_whole() -> None:
    removed, residual = split_on(leg_log(CARRIED), "signal")
    assert removed.empty
    assert len(residual) == len(CARRIED)


def test_removing_every_leg_leaves_the_zero_summary_rather_than_raising() -> None:
    """A configuration whose every leg was the clock's is exactly the case being looked for,
    so it must produce a row rather than an exception."""
    row = measure_row(stored_row(leg_log([(5.0, FLATTEN)])), leg_log([(5.0, FLATTEN)]), FLATTEN)
    assert row["trades_rest"] == 0
    assert row["net_pnl_rest"] == 0.0
    assert not row["survives"]


# -- what the tool exists for ----------------------------------------------------------------


def test_net_is_additive_across_the_split_and_profit_factor_is_not() -> None:
    """The reason this is a re-summarise rather than a subtraction on the decomposition
    ``tools/campaign_report.py`` already prints."""
    log = leg_log(CARRIED)
    row = measure_row(stored_row(log), log, FLATTEN)
    assert row[f"{FLATTEN}_net"] + row["net_pnl_rest"] == pytest.approx(row["net_pnl_whole"])
    assert row["profit_factor_rest"] != pytest.approx(row["profit_factor_whole"])


def test_a_book_the_flatten_carries_does_not_survive_without_it() -> None:
    """§M28.12's finding in one row: the bracket is a net cost and the clock is the result."""
    log = leg_log(CARRIED)
    row = measure_row(stored_row(log), log, FLATTEN)
    assert row["profit_factor_whole"] > PASS_MARK
    assert row["profit_factor_rest"] < PASS_MARK
    assert row["net_pnl_rest"] < 0.0
    assert not row["survives"]


def test_a_book_that_stands_up_without_the_flatten_is_reported_as_surviving() -> None:
    """The test that can pass, without which "nothing survives" is a claim about the tool."""
    log = leg_log([(900.0, "target"), (800.0, "target"), (-200.0, "stop"), (50.0, FLATTEN)])
    row = measure_row(stored_row(log), log, FLATTEN)
    assert row["profit_factor_rest"] > PASS_MARK
    assert row[NET_TO_DRAWDOWN + "_rest"] > PASS_MARK
    assert row["survives"]


def test_surviving_needs_the_drawdown_as_well_as_the_profit_factor() -> None:
    """Gate 4 is both, and a profitable book that gave back more than it made is the case a
    profit factor alone passes."""
    log = leg_log([(1_000.0, "target"), (-900.0, "stop"), (100.0, "target"), (10.0, FLATTEN)])
    row = measure_row(stored_row(log), log, FLATTEN)
    assert row["profit_factor_rest"] > PASS_MARK
    assert 0.0 < row[NET_TO_DRAWDOWN + "_rest"] < PASS_MARK
    assert not row["survives"]


# -- every figure is summarise's -------------------------------------------------------------


def test_the_whole_book_column_is_summarise_over_the_whole_log() -> None:
    log = leg_log(CARRIED)
    row = measure_row(stored_row(log), log, FLATTEN)
    summary = stats.summarise(log)
    for field in REPORTED:
        assert row[f"{field}_whole"] == pytest.approx(float(getattr(summary, field)))


def test_the_residual_column_is_summarise_over_the_legs_that_are_left() -> None:
    """A subset of a log is what a review summarises too; nothing here defines a statistic."""
    log = leg_log(CARRIED)
    row = measure_row(stored_row(log), log, FLATTEN)
    summary = stats.summarise(split_on(log, FLATTEN)[1])
    for field in REPORTED:
        assert row[f"{field}_rest"] == pytest.approx(float(getattr(summary, field)))


def test_summary_of_reports_net_to_drawdown_beside_the_summary_fields() -> None:
    figures = summary_of(leg_log(CARRIED))
    assert set(figures) == {*REPORTED, NET_TO_DRAWDOWN}
    assert figures[NET_TO_DRAWDOWN] == pytest.approx(figures["net_pnl"] / figures["max_drawdown"])


# -- the log has to be the one the row names --------------------------------------------------


def test_a_log_that_does_not_reproduce_its_stored_row_is_refused() -> None:
    """Every figure below it would otherwise be attributed to a configuration that did not
    produce it -- the guard ``tools/campaign_shortlist.verify`` puts on the run that wrote it."""
    log = leg_log(CARRIED)
    with pytest.raises(RuntimeError, match="not the"):
        measure_row(stored_row(log, net_pnl=99.0), log, FLATTEN)


def test_a_log_that_does_reproduce_its_stored_row_passes_the_guard() -> None:
    log = leg_log(CARRIED)
    verify(stored_row(log), summary_of(log))


# -- attribution and absence -----------------------------------------------------------------


def test_a_measured_row_carries_the_tags_of_the_configuration_it_came_from() -> None:
    assert labelled(stored_row(leg_log(CARRIED)))["stratum"] == "phase=MIDDAY"
    assert "net_pnl" not in labelled(stored_row(leg_log(CARRIED))), "a statistic is not a tag"


def test_a_row_with_no_stored_log_is_skipped_rather_than_re_summarised(stocked) -> None:
    log = leg_log(CARRIED)
    rows = pd.DataFrame([stored_row(log), stored_row(log, combo_id=999)])
    assert list(measure(rows, stocked, FLATTEN)["combo_id"]) == [COMBO_ID]


def test_survival_counts_both_windows_of_the_comparison() -> None:
    table = pd.DataFrame(
        {
            "profit_factor_whole": [1.2, 1.3, 0.9],
            "profit_factor_rest": [0.4, 1.4, 0.8],
            "net_pnl_whole": [10.0, 20.0, -5.0],
            "net_pnl_rest": [-5.0, 8.0, -9.0],
            "survives": [False, True, False],
        },
    )
    lines = survival(table, FLATTEN)
    assert "2 of 3 whole" in lines[0]
    assert "1 of 3 without" in lines[0]
    assert "1 of 3 without" in lines[1]


def test_an_empty_table_says_so_rather_than_dividing_by_nothing() -> None:
    assert survival(pd.DataFrame(), FLATTEN) == ["  (nothing was measured)"]


# -- the report ------------------------------------------------------------------------------


def run_main(monkeypatch, rows: pd.DataFrame, db, *extra: str) -> int:
    monkeypatch.setattr(campaign_exits, "held_out", lambda *_, **__: rows)
    monkeypatch.setattr(campaign_exits, "db_path", lambda _: db)

    return main(["campaign_exits.py", "--strategy", "OpeningRange", *extra])


def test_a_shortlist_with_stored_logs_reports_and_succeeds(monkeypatch, stocked) -> None:
    assert run_main(monkeypatch, pd.DataFrame([stored_row(leg_log(CARRIED))]), stocked) == 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_printing_an_empty_table(
    monkeypatch,
    tmp_path,
) -> None:
    """An empty report is indistinguishable from a cell that survives the exclusion."""
    rows = pd.DataFrame([stored_row(leg_log(CARRIED))])
    assert run_main(monkeypatch, rows, tmp_path / "OpeningRange.duckdb") == 1


def test_the_reason_offered_is_the_simulator_s_own_vocabulary(monkeypatch, stocked, capsys) -> None:
    """An imported log's reasons are its source's, so a free-text reason would silently
    remove nothing and report the whole book twice -- ``docs/roadmap.md`` §M9."""
    rows = pd.DataFrame([stored_row(leg_log(CARRIED))])
    assert run_main(monkeypatch, rows, stocked, "--reason", "stop") == 0
    with pytest.raises(SystemExit):
        run_main(monkeypatch, rows, stocked, "--reason", "flattened")

    assert "flattened" in capsys.readouterr().err


def test_the_default_reason_is_the_one_no_strategy_chose(monkeypatch, stocked) -> None:
    """The flatten is an account rule rather than a rule of any archetype, which is what
    makes it the exclusion worth defaulting to -- ``docs/roadmap.md`` §M28.15."""
    assert campaign_exits.main.__module__
    assert FLATTEN in trades.EXIT_REASONS.values()

    measured: list[str] = []
    monkeypatch.setattr(
        campaign_exits, "measure", lambda rows, path, reason: measured.append(reason) or pd.DataFrame()
    )
    monkeypatch.setattr(
        campaign_exits, "held_out", lambda *_, **__: pd.DataFrame([stored_row(leg_log(CARRIED))])
    )
    monkeypatch.setattr(campaign_exits, "db_path", lambda _: stocked)
    assert main(["campaign_exits.py", "--strategy", "OpeningRange"]) == 1
    assert measured == [FLATTEN]


def test_the_shortlist_is_the_held_out_pair_and_never_the_window_that_chose_it(
    monkeypatch,
    stocked,
) -> None:
    """There is no ``--window`` here on purpose -- ``docs/roadmap.md`` §M28.13."""
    called: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        campaign_exits,
        "held_out",
        lambda *args: called.append(args) or pd.DataFrame([stored_row(leg_log(CARRIED))]),
    )
    monkeypatch.setattr(campaign_exits, "db_path", lambda _: stocked)
    argv = ["campaign_exits.py", "--strategy", "OpeningRange", "--root", "NQ", "--top", "5"]
    assert main([*argv, "--stratum", "phase=MIDDAY", "--resolution", "5"]) == 0
    assert called == [("OpeningRange", "NQ", "profit_factor", 5, "phase=MIDDAY", 5, None)]
