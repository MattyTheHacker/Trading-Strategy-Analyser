"""Resampling a shortlisted configuration's own trade log, and refusing to invent one.

The tests that matter here are about attribution and about absence. A bootstrap row carries the
tags of the configuration it came from, because a percentile filed under the wrong row is worse
than no percentile and no statistic would show it. And a row whose log was never stored has to
be named and skipped -- a shortlist quietly resampling four of its twenty configurations reads
exactly like one resampling all twenty.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import montecarlo, results, stats, trades
from tools import campaign_montecarlo
from tools.campaign_montecarlo import PERMUTED, STATISTICS, labelled, main, resample_row

SWEEP_ID = 30
COMBO_ID = 417


def stored_row(**columns: object) -> pd.Series:
    """One ranked row, carrying the tags the report labels a result with."""
    base = {
        "sweep_id": SWEEP_ID,
        "combo_id": COMBO_ID,
        "root": "MNQ",
        "resolution": 15,
        "variant": "bracket",
        "stratum": "unfiltered",
        "window": "holdout",
        "profit_factor": 1.153,
    }

    return pd.Series({**base, **columns})


def trade_log(n: int = 120, seed: int = 3) -> pd.DataFrame:
    """A leg-level log with wins and losses, in the shape ``save_trades`` stores."""
    rng = np.random.default_rng(seed)
    pnl = rng.normal(5.0, 60.0, n)
    entry = pd.Timestamp("2025-01-02 14:30", tz="UTC") + pd.to_timedelta(np.arange(n), unit="h")

    return pd.DataFrame(
        {
            "trade_id": np.arange(1, n + 1),
            "leg": 1,
            "direction": trades.LONG,
            "net_pnl": pnl,
            "commission": 1.5,
            "bars_held": 4,
            "ambiguous_bar": False,
            "mae_points": 1.0,
            "mfe_points": 2.0,
            "r_multiple": pnl / 50.0,
            "exit_reason": "target",
            "entry_time": entry,
            "exit_time": entry + pd.Timedelta(minutes=20),
            "instrument": "MNQ",
            "source": "sim",
        },
    )


@pytest.fixture
def stocked(tmp_path):
    """A database holding one stored log, at the ids the ranked row names."""
    db = tmp_path / "InsideBar.duckdb"
    results.save_trades(trade_log(), SWEEP_ID, COMBO_ID, db)

    return db


# -- attribution ---------------------------------------------------------------------------


def test_a_result_carries_the_tags_of_the_row_it_came_from() -> None:
    assert labelled(stored_row())["stratum"] == "unfiltered"
    assert labelled(stored_row())["combo_id"] == COMBO_ID
    assert "profit_factor" not in labelled(stored_row()), "a statistic is not a tag"


def test_a_row_missing_a_tag_column_is_labelled_with_what_it_has() -> None:
    """The campaign databases widened over time, so an older row can be short a column."""
    assert "variant" not in labelled(stored_row().drop("variant"))


def test_every_bootstrap_row_names_the_configuration_it_was_drawn_from(stocked) -> None:
    """One report holds several configurations' percentiles, so a row that does not say which
    is a number attributed by position in a table."""
    permutation, spread = resample_row(stored_row(), stocked, 50, 0)
    assert set(spread["statistic"]) == set(STATISTICS)
    assert set(spread["combo_id"]) == {COMBO_ID}
    assert set(spread["stratum"]) == {"unfiltered"}
    assert permutation["combo_id"] == COMBO_ID


# -- what each test actually asks ----------------------------------------------------------


def test_the_permutation_test_asks_about_the_path_and_not_about_the_value(stocked) -> None:
    """Reordering cannot move a profit factor, so permuting one returns 1.0 for every input
    and reads like a passed check -- ``docs/roadmap.md`` §M7b."""
    permutation, _ = resample_row(stored_row(), stocked, 50, 0)
    assert permutation["statistic"] == PERMUTED
    assert PERMUTED in stats.PATH_STATISTICS
    assert PERMUTED not in stats.TRADE_PNL_STATISTICS
    assert 0.0 <= permutation["p_value"] <= 1.0


def test_the_bootstrap_reports_the_observed_figure_beside_its_percentiles(stocked) -> None:
    """The point of the table: a drawdown with no spread beside it is the reading §M27's Gate 4
    could not check."""
    _, spread = resample_row(stored_row(), stocked, 200, 0)
    for _, row in spread.iterrows():
        assert row["p05"] <= row["median"] <= row["p95"]
        assert np.isfinite(row["observed"])


def test_the_observed_figure_is_the_log_s_own_and_not_a_resample_of_it(stocked) -> None:
    """A bootstrap median is close to the observation and is not it; quoting the median as the
    result would report a figure the strategy never produced."""
    _, spread = resample_row(stored_row(), stocked, 200, 0)
    pnl = montecarlo.trade_pnl(trade_log())
    observed = spread.set_index("statistic")["observed"]
    assert observed["net_pnl"] == pytest.approx(float(pnl.sum()))
    assert observed["max_drawdown"] == pytest.approx(stats.path_statistic(pnl, "max_drawdown"))


def test_the_same_seed_reproduces_the_same_percentiles(stocked) -> None:
    once, _ = resample_row(stored_row(), stocked, 100, 7)
    twice, _ = resample_row(stored_row(), stocked, 100, 7)
    assert once == twice


# -- absence -------------------------------------------------------------------------------


def test_a_row_with_no_stored_log_is_skipped_rather_than_resampled(stocked) -> None:
    """Silently dropping it would leave a report that looks like the whole shortlist."""
    assert resample_row(stored_row(combo_id=999), stocked, 50, 0) is None


def test_a_database_that_was_never_given_a_shortlist_yields_nothing(tmp_path) -> None:
    """``trades`` is created lazily, so before ``campaign_shortlist.py`` runs there is no table
    to read at all -- which must not be an exception halfway through a report."""
    empty = tmp_path / "InsideBar.duckdb"
    results.query("SELECT 1", empty)
    assert resample_row(stored_row(), empty, 50, 0) is None


def test_a_log_too_short_to_resample_is_skipped_rather_than_reported(tmp_path) -> None:
    """One trade has no ordering to permute, and :mod:`nqbt.montecarlo` raises on it."""
    db = tmp_path / "InsideBar.duckdb"
    results.save_trades(trade_log(n=1), SWEEP_ID, COMBO_ID, db)
    assert resample_row(stored_row(), db, 50, 0) is None


# -- the report over a whole shortlist ------------------------------------------------------


def run_main(monkeypatch, rows: pd.DataFrame, db) -> int:
    monkeypatch.setattr(campaign_montecarlo, "shortlist", lambda *_: rows)
    monkeypatch.setattr(campaign_montecarlo, "db_path", lambda _: db)

    return main(["campaign_montecarlo.py", "--strategy", "InsideBar", "--iterations", "50"])


def test_a_shortlist_with_stored_logs_reports_and_succeeds(monkeypatch, stocked) -> None:
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), stocked) == 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_printing_an_empty_table(
    monkeypatch,
    tmp_path,
) -> None:
    """An empty report is indistinguishable from a strategy with nothing to say, so the
    missing prerequisite has to be an exit status rather than a blank table."""
    db = tmp_path / "InsideBar.duckdb"
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), db) == 1


def test_the_rows_that_do_have_logs_are_still_reported(monkeypatch, stocked) -> None:
    """One missing log must not cost the other nineteen their percentiles."""
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=999)])
    assert run_main(monkeypatch, rows, stocked) == 0
