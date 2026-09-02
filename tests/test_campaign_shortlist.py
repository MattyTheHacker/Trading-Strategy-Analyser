"""Getting a shortlisted configuration's trade log into the database it was ranked from.

The selection half is pure and needs no database. The storing half is a real round trip through
DuckDB, because what it has to prove is that a stored log belongs to the row it is filed under
-- a log attributed to the wrong configuration is worse than no log, and no summary statistic
would show it. ``store_logs`` reads ``cache/continuous``, so the loader is substituted; the
grouping is the part worth pinning and reading a file is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, resample, results, sessions, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.types import InsideBarParams
from tools import campaign_shortlist
from tools.campaign_shortlist import best_row, shortlist, source, store_group, store_logs, verify

ROOT = "MNQ"
STRATEGY = "InsideBar"


def stored_rows(**columns: object) -> pd.DataFrame:
    """A ranked frame with the tag columns a selection reads."""
    base = {
        "root": ROOT,
        "stratum": "unfiltered",
        "resolution": 5,
        "profit_factor": [0.8, 1.4, 1.1, 1.2],
        "trades": [100, 200, 300, 400],
    }

    return pd.DataFrame({**base, **columns})


# -- picking the rows ----------------------------------------------------------------------


def test_the_shortlist_takes_the_top_rows_by_the_named_statistic(monkeypatch) -> None:
    monkeypatch.setattr(campaign_shortlist, "load", lambda *_: stored_rows())
    ranked = shortlist(STRATEGY, ROOT, ["full"], "profit_factor", 2)
    assert list(ranked["profit_factor"]) == [1.4, 1.2]
    assert list(shortlist(STRATEGY, ROOT, ["full"], "trades", 2)["trades"]) == [400, 300]


def test_the_shortlist_is_restricted_to_one_root_stratum_and_resolution(monkeypatch) -> None:
    """The same five flags the other campaign tools select with, so two tools reading one
    shortlist read the same rows."""
    frame = stored_rows(
        root=[ROOT, ROOT, "NQ", "NQ"],
        stratum=["unfiltered", "phase=OPEN", "unfiltered", "unfiltered"],
        resolution=[5, 5, 5, 15],
    )
    monkeypatch.setattr(campaign_shortlist, "load", lambda *_: frame)
    picked = shortlist(STRATEGY, ROOT, ["full"], "profit_factor", 10, "unfiltered", 5)
    assert list(picked["trades"]) == [100]


def test_a_selection_matching_no_stored_row_raises_rather_than_ranking_nothing(monkeypatch) -> None:
    monkeypatch.setattr(campaign_shortlist, "load", lambda *_: stored_rows())
    with pytest.raises(RuntimeError, match="no stored rows"):
        shortlist(STRATEGY, "NQ", ["full"], "profit_factor", 10)


def test_the_best_row_is_the_first_row_of_the_shortlist(monkeypatch) -> None:
    """``campaign_null`` and ``campaign_contracts`` take the best of what this ranks, so the
    two must not be able to disagree about which row that is."""
    monkeypatch.setattr(campaign_shortlist, "load", lambda *_: stored_rows())
    best = best_row(STRATEGY, ROOT, ["full"], "profit_factor")
    assert best["profit_factor"] == pytest.approx(1.4)
    assert best["trades"] == shortlist(STRATEGY, ROOT, ["full"], "profit_factor", 5).iloc[0]["trades"]


# -- the bars a stored row was measured on -------------------------------------------------


def test_the_full_window_is_every_bar_and_the_split_windows_partition_them() -> None:
    """A row re-run over the wrong window reproduces nothing, so this is what ``verify``
    would otherwise have to catch."""
    bars = synthetic_bars(n=1000)
    assert source(bars, "full").equals(bars)
    selection, holdout = source(bars, "selection"), source(bars, "holdout")
    assert len(selection) + len(holdout) == len(bars)
    assert pd.concat([selection, holdout]).index.equals(bars.index)


# -- refusing a re-run that did not reproduce the row --------------------------------------


def summary_row(trades: int = 40, net_pnl: float = 1234.5) -> pd.Series:
    return pd.Series({"sweep_id": 1, "combo_id": 2, "trades": trades, "net_pnl": net_pnl})


def test_verify_accepts_a_rerun_that_reproduces_the_stored_summary() -> None:
    verify(summary_row(), {"trades": 40, "net_pnl": 1234.5})


def test_verify_refuses_a_rerun_with_a_different_trade_count() -> None:
    with pytest.raises(RuntimeError, match="41 trades, not the 40 stored"):
        verify(summary_row(), {"trades": 41, "net_pnl": 1234.5})


def test_verify_refuses_a_rerun_with_a_different_net_pnl() -> None:
    """Same trades, different money: a filter rebuilt wrong picks the same signals and
    brackets them differently."""
    with pytest.raises(RuntimeError, match="net 1300"):
        verify(summary_row(), {"trades": 40, "net_pnl": 1300.0})


def test_verify_reads_agreement_numerically_rather_than_textually() -> None:
    """A round trip through DuckDB and back is not required to be bit-identical, and a last-bit
    difference is not a different configuration."""
    verify(summary_row(), {"trades": 40, "net_pnl": np.nextafter(1234.5, 2000.0)})


# -- storing the logs ----------------------------------------------------------------------


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
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
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day

    return frame


def grid() -> sweep.Grid:
    """Two InsideBar combinations, both of which trade on the synthetic bars."""
    return sweep.Grid.of(
        InsideBarParams(slow_sma_period=50, bars_required_to_trade=60),
        atr_multiplier=[5.0, 10.0],
    )


def store_point(db, bars: pd.DataFrame, minutes: int, window: str) -> int:
    """Sweep one grid at one point and store it the way ``campaign_sweep.run_point`` does."""
    frame = resample.resample(bars, minutes)
    table, _ = sweep.sweep(frame, grid(), get_instrument(ROOT))
    table.insert(0, "variant", "bracket")
    table.insert(1, "stratum", "unfiltered")
    table.insert(2, "window", window)
    table["combo_id"] = range(len(table))

    return results.save_sweep(
        table,
        root=ROOT,
        instrument=ROOT,
        bars=frame,
        axes=grid().axis_values(),
        strategy=STRATEGY,
        resolution=minutes,
        db_path=db,
    )


def combos(db) -> pd.DataFrame:
    return results.query("SELECT * FROM combos ORDER BY sweep_id, combo_id", db)


def logs(db) -> pd.DataFrame:
    return results.query("SELECT * FROM trades", db)


def test_a_stored_log_is_filed_under_the_row_that_produced_it(tmp_path) -> None:
    """The whole point: the per-trade P&L a bootstrap reads has to belong to the summary the
    sweep ranked, and ``(sweep_id, combo_id)`` is what says so."""
    db = tmp_path / "InsideBar.duckdb"
    bars = synthetic_bars()
    store_point(db, bars, 5, "full")
    block = combos(db)
    assert block["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"

    frame = resample.resample(bars, 5)
    assert store_group(block, frame, archetypes.INSIDEBAR, ROOT, 5, db) == len(block)

    stored = logs(db)
    assert set(stored["source"]) == {"sim"}
    for _, row in block.iterrows():
        mine = stored[(stored["sweep_id"] == row["sweep_id"]) & (stored["combo_id"] == row["combo_id"])]
        assert len(mine) > 0
        assert mine["net_pnl"].sum() == pytest.approx(row["net_pnl"])


def test_storing_a_shortlist_twice_replaces_each_log_rather_than_doubling_it(tmp_path) -> None:
    """A doubled log halves nothing visibly -- it changes every statistic taken from it and
    still validates, so re-running has to be idempotent."""
    db = tmp_path / "InsideBar.duckdb"
    bars = synthetic_bars()
    store_point(db, bars, 5, "full")
    block, frame = combos(db), resample.resample(bars, 5)

    store_group(block, frame, archetypes.INSIDEBAR, ROOT, 5, db)
    once = len(logs(db))
    store_group(block, frame, archetypes.INSIDEBAR, ROOT, 5, db)
    assert len(logs(db)) == once


def test_a_row_the_rerun_does_not_reproduce_stores_no_log(tmp_path) -> None:
    """A drifted database is the case this exists for, and it must fail loudly rather than
    file a log against a configuration that did not produce it."""
    db = tmp_path / "InsideBar.duckdb"
    bars = synthetic_bars()
    store_point(db, bars, 5, "full")
    block = combos(db)
    block.loc[:, "trades"] = block["trades"] + 1

    with pytest.raises(RuntimeError, match="trades, not the"):
        store_group(block, resample.resample(bars, 5), archetypes.INSIDEBAR, ROOT, 5, db)
    assert not results.query(
        "SELECT COUNT(*) c FROM information_schema.tables WHERE table_name = 'trades'", db
    ).loc[0, "c"]


def test_every_shortlisted_row_is_stored_whatever_window_and_resolution_it_came_from(
    tmp_path,
    monkeypatch,
) -> None:
    """One shortlist spans several sweep points, and each row's own window and resolution say
    which bars reproduce it -- get either wrong and ``verify`` refuses the whole block."""
    db = tmp_path / "InsideBar.duckdb"
    bars = synthetic_bars()
    for window, minutes in (("selection", 5), ("holdout", 5), ("full", 10)):
        store_point(db, source(bars, window), minutes, window)

    monkeypatch.setattr(campaign_shortlist.splice, "load_continuous", lambda _: bars)
    monkeypatch.setattr(campaign_shortlist, "db_path", lambda _: db)

    block = combos(db)
    assert store_logs(STRATEGY, block, ROOT) == len(block)
    stored = logs(db)
    assert set(zip(stored["sweep_id"], stored["combo_id"], strict=True)) == set(
        zip(block["sweep_id"], block["combo_id"], strict=True),
    )
