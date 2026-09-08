"""Storing a shortlist's per-trade context, so filtering trades is a query rather than a session.

Two claims are pinned harder than the rest. **The cut is stored with the rows it cut**, because
the same trades labelled at two threshold pairs are two populations and a query that mixed them
would report one. **A row that cannot honestly be joined to its bars is named and skipped**, not
absorbed -- a fill outside its bar is how a back-adjusted series announces itself, and admitting
it would annotate every trade against prices that never traded.
"""

from __future__ import annotations

import pandas as pd
import pytest
from test_campaign_review import COMBO_ID, HEAVY, THIN, bars, data, stored_row, trade_log  # noqa: F401 - fixtures

from nqbt import annotate, archetypes, context, notes, results
from tools import campaign_annotate
from tools.campaign_annotate import annotation_spec, main, store_row, thresholds_for

COMPRESSED = 0.25
EXPANDED = 0.75


def combo_frame() -> pd.DataFrame:
    """The summary row the view joins to, carrying one parameter to filter on."""
    return pd.DataFrame(
        {
            "combo_id": [COMBO_ID],
            "ema_period": [9],
            "trades": [100],
            "profit_factor": [1.2],
            "net_pnl": [500.0],
        },
    )


@pytest.fixture
def stocked(tmp_path, data):
    """A database holding one combination's summary row and its stored trade log."""
    db = tmp_path / "InsideBar.duckdb"
    sweep_id = results.save_sweep(
        combo_frame(),
        root="MNQ",
        instrument="MNQ",
        bars=bars(),
        axes={},
        db_path=db,
    )
    results.save_trades(trade_log(data), sweep_id, COMBO_ID, db)

    return db, sweep_id


# -- the cut a stored row was measured at --------------------------------------


def test_every_threshold_pair_the_row_carries_is_read_including_the_ones_a_clock_review_ignores() -> None:
    """``LabelThresholds`` and the params class use the same words, so a new pair flows through."""
    cut = thresholds_for(
        stored_row(
            regime_consolidating_below=0.3,
            regime_directional_above=0.5,
            compression_compressed_below=COMPRESSED,
            compression_expanded_above=EXPANDED,
            trend_min_agreement=3,
        ),
    )
    assert cut.labels_regimes
    assert cut.labels_volume
    assert cut.labels_compression
    assert cut.compression_expanded_above == EXPANDED
    assert cut.trend_min_agreement == 3


def test_a_threshold_the_row_does_not_carry_labels_nothing_rather_than_defaulting() -> None:
    """A cut nobody stored is not a cut this configuration ran at."""
    cut = thresholds_for(stored_row())
    assert cut.labels_volume, "the fixture row does carry the volume pair"
    assert not cut.labels_regimes
    assert not cut.labels_compression
    assert cut.trend_min_agreement is None


def test_the_agreement_score_is_read_as_a_whole_number() -> None:
    """DuckDB hands back a float; ``validate_min_agreement`` counts votes."""
    assert thresholds_for(stored_row(trend_min_agreement=2.0)).trend_min_agreement == 2


# -- what a dataset has to hold ------------------------------------------------


def test_the_spec_covers_the_configurations_own_series_as_well_as_the_reviews(data) -> None:
    """The union is what lets one prepared dataset serve a whole block of stored rows."""
    spec = annotation_spec(pd.DataFrame([stored_row()]), archetypes.get("InsideBar"))
    assert spec.needs_time_of_day, "the clock is the review's half"
    assert spec.volume_keys, "and so is every form of volume"
    assert spec.ma_keys or spec.atr_periods, "the configuration's own series come too"


# -- storing one row -----------------------------------------------------------


def test_a_stored_annotation_carries_the_context_at_each_trades_entry_bar(stocked, data) -> None:
    db, sweep_id = stocked
    assert store_row(stored_row(sweep_id=sweep_id), data, db, "MNQ", -1.0)

    stored = results.query("SELECT * FROM annotations", db)
    assert len(stored) == len(trade_log(data))
    assert "entry_phase" in stored.columns
    assert set(stored["sweep_id"]) == {sweep_id}


def test_the_cut_is_stored_with_the_rows_it_cut(stocked, data) -> None:
    db, sweep_id = stocked
    store_row(stored_row(sweep_id=sweep_id), data, db, "MNQ", -1.0)
    stored = results.query("SELECT * FROM annotations", db)
    assert stored["cut_volume_thin_below"].iloc[0] == THIN
    assert stored["cut_volume_heavy_above"].iloc[0] == HEAVY


def test_storing_a_row_twice_replaces_rather_than_doubles_it(stocked, data) -> None:
    """A doubled annotation still joins and every count taken through it moves."""
    db, sweep_id = stocked
    row = stored_row(sweep_id=sweep_id)
    store_row(row, data, db, "MNQ", -1.0)
    store_row(row, data, db, "MNQ", -1.0)
    assert results.query("SELECT COUNT(*) c FROM annotations", db).loc[0, "c"] == len(trade_log(data))


def test_a_row_with_no_stored_log_is_named_and_skipped(tmp_path, data) -> None:
    empty = tmp_path / "empty.duckdb"
    assert not store_row(stored_row(), data, empty, "MNQ", -1.0)


def test_a_log_whose_fill_lands_outside_its_bar_is_skipped_rather_than_annotated(tmp_path, data) -> None:
    """The price check is the only thing that catches a back-adjusted series."""
    db = tmp_path / "InsideBar.duckdb"
    moved = trade_log(data)
    moved.loc[0, "entry_price"] = float(moved.loc[0, "entry_price"]) + 500.0
    results.save_trades(moved, 1, COMBO_ID, db)

    assert not store_row(stored_row(sweep_id=1), data, db, "MNQ", -1.0)

    tables = results.query("SELECT table_name FROM information_schema.tables", db)
    assert "annotations" not in set(tables["table_name"]), "a refused row leaves nothing behind"


# -- end to end ----------------------------------------------------------------


def run_main(monkeypatch, rows: pd.DataFrame, db, frame: pd.DataFrame) -> int:
    monkeypatch.setattr(campaign_annotate, "shortlist", lambda *_: rows)
    monkeypatch.setattr(campaign_annotate, "db_path", lambda _: db)
    monkeypatch.setattr(campaign_annotate, "source", lambda bars, _window: bars)
    monkeypatch.setattr(campaign_annotate.splice, "load_continuous", lambda _root: frame)
    monkeypatch.setattr(campaign_annotate.resample, "resample", lambda bars, _minutes: bars)

    return main(["campaign_annotate.py", "--strategy", "InsideBar"])


def test_a_shortlist_with_a_stored_log_is_annotated_and_leaves_a_queryable_view(
    monkeypatch,
    stocked,
) -> None:
    db, sweep_id = stocked
    assert run_main(monkeypatch, pd.DataFrame([stored_row(sweep_id=sweep_id)]), db, bars()) == 0

    rows = results.query(f"SELECT * FROM {results.TRADE_VIEW}", db)
    assert not rows.empty
    assert "entry_phase" in rows.columns, "the context at the entry bar"
    assert "combo_ema_period" in rows.columns, "the configuration, as a filter"
    assert "net_pnl" in rows.columns, "and the leg's own P&L, not the combination's"


def test_the_view_answers_the_question_the_tool_exists_for(monkeypatch, stocked) -> None:
    """Profitable, and taken in a named phase -- one query over the three tables."""
    db, sweep_id = stocked
    run_main(monkeypatch, pd.DataFrame([stored_row(sweep_id=sweep_id)]), db, bars())
    rows = results.query(
        f"SELECT entry_phase, COUNT(*) n FROM {results.TRADE_VIEW} "
        f"WHERE net_pnl > 0 AND combo_ema_period = 9 GROUP BY 1 ORDER BY 1",
        db,
    )
    assert not rows.empty
    assert rows["n"].sum() > 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_leaving_an_empty_view(
    monkeypatch,
    tmp_path,
) -> None:
    db = tmp_path / "InsideBar.duckdb"
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), db, bars()) == 1


def test_an_annotation_carrying_a_note_never_reaches_a_column_a_query_can_group_by(stocked, data) -> None:
    """The exclusion rail is enforced at this door too -- ``docs/roadmap.md`` §M11.5."""
    db, _ = stocked
    ann = annotate.annotate_trades(trade_log(data), context.prepare(bars(), bar_minutes=1))
    with pytest.raises(notes.NotesError, match="free-text column"):
        results.save_annotation(ann.frame.assign(note="clean setup"), 1, 1, {}, db)
