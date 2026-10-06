"""Re-stamping stored rows: which ``reconciled`` rows leave their port, and that nothing else moves.

Every database here is built by :func:`nqbt.results.save_sweep` from the row
:func:`nqbt.sweep.run_combination` would store, so a row round-trips through DuckDB as a
campaign's does.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import duckdb
import pandas as pd
import pytest

import tools.restamp_tier2 as module
from nqbt import archetypes, paths, regime, results
from nqbt.archetypes import Tier2Status
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, InsideBarParams
from tools.restamp_tier2 import UNREADABLE, default_databases, departures, main, restamp

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.archetypes import Params

BARS = pd.DataFrame(
    {"close": [1.0, 2.0]},
    index=pd.date_range("2024-01-02 15:00", periods=2, freq="min", tz="UTC"),
)


def store(db: Path, strategy: str, combos: list[Params], tier2: str = "reconciled", **drop: bool) -> None:
    """Store one sweep of ``combos`` as a campaign would, leaving out any column named in ``drop``."""
    unstored = archetypes.get(strategy).not_sweepable | {name for name, dropped in drop.items() if dropped}
    frame = pd.DataFrame(
        [params.as_dict() | {"combo_id": i, "trades": 40} for i, params in enumerate(combos)]
    )
    frame = frame.drop(columns=sorted(unstored & set(frame.columns)))
    frame["tier2"] = tier2
    results.save_sweep(
        frame,
        root="MNQ",
        instrument="MNQ",
        bars=BARS,
        axes={},
        strategy=strategy,
        resolution=5,
        tier2=tier2,
        db_path=db,
    )


def stamps(db: Path) -> list[tuple[str, int, str]]:
    """Return every stored row's strategy, ``combo_id`` and ``tier2``, in a fixed order."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(
            "SELECT strategy, combo_id, tier2 FROM combos ORDER BY sweep_id, combo_id"
        ).fetchall()
    finally:
        con.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "DeadCatBounce.duckdb"
    store(
        path,
        "DeadCatBounce",
        [
            DeadCatParams(),
            DeadCatParams(max_hold_bars=5),
            DeadCatParams(regime_filter=regime.Regime.DIRECTIONAL.bit),
            DeadCatParams(ema_period=30, commission_per_contract=1.5),
        ],
    )
    store(path, "InsideBar", [InsideBarParams(), InsideBarParams(fill_limit_on_touch=False)])

    return path


def test_a_report_names_the_leaving_rows_and_writes_nothing(db: Path) -> None:
    before = stamps(db)
    found = {one.strategy: one for one in restamp(db, apply=False)}
    assert found["DeadCatBounce"].checked == 4
    assert found["DeadCatBounce"].keys == [(1, 1), (1, 2)]
    assert dict(found["DeadCatBounce"].reasons) == {("max_hold_bars",): 1, ("regime_filter",): 1}
    assert found["InsideBar"].keys == [(2, 1)]
    assert stamps(db) == before


def test_writing_re_stamps_the_leaving_rows_and_only_them(db: Path) -> None:
    restamp(db, apply=True)
    assert stamps(db) == [
        ("DeadCatBounce", 0, "reconciled"),
        ("DeadCatBounce", 1, "tier-1-only"),
        ("DeadCatBounce", 2, "tier-1-only"),
        ("DeadCatBounce", 3, "reconciled"),
        ("InsideBar", 0, "reconciled"),
        ("InsideBar", 1, "tier-1-only"),
    ]
    again = restamp(db, apply=False)
    assert all(not one.keys for one in again), "a second run found rows the first left behind"


def test_a_field_no_sweep_stores_is_read_at_its_default(tmp_path: Path) -> None:
    """``target_r_multiples`` is not sweepable, so a sweep never writes it and the tool cannot see it."""
    path = tmp_path / "ladder.duckdb"
    store(path, "DeadCatBounce", [DeadCatParams(target_r_multiples=(1.0, 2.0, 3.0, float("nan")))])
    con = duckdb.connect(str(path), read_only=True)
    try:
        columns = {row[0] for row in con.execute("DESCRIBE combos").fetchall()}
        assert "target_r_multiples" not in columns
        assert departures(con, archetypes.DEADCATBOUNCE).keys == []
    finally:
        con.close()


def test_a_column_stored_before_its_field_existed_reads_as_the_default(tmp_path: Path) -> None:
    path = tmp_path / "older.duckdb"
    store(path, "DeadCatBounce", [DeadCatParams()], min_reward_risk=True, max_hold_bars=True)
    found = {one.strategy: one for one in restamp(path, apply=False)}
    assert found["DeadCatBounce"].checked == 1
    assert found["DeadCatBounce"].keys == []


def test_a_null_cell_reads_as_the_default(tmp_path: Path) -> None:
    """A later archetype's column is null on every earlier row, which ran without it."""
    path = tmp_path / "widened.duckdb"
    store(path, "DeadCatBounce", [DeadCatParams()], max_hold_bars=True)
    store(path, "DeadCatBounce", [DeadCatParams(max_hold_bars=5)])
    found = {one.strategy: one for one in restamp(path, apply=False)}
    assert found["DeadCatBounce"].keys == [(2, 0)]


def test_rows_already_tier_1_only_and_unreconciled_archetypes_are_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "mixed.duckdb"
    store(path, "DeadCatBounce", [DeadCatParams(max_hold_bars=5)], tier2="tier-1-only")
    store(path, "EmaCrossover", [EmaCrossoverParams(max_hold_bars=5)], tier2="tier-1-only")
    before = stamps(path)
    found = restamp(path, apply=True)
    assert sum(one.checked for one in found) == 0
    assert stamps(path) == before


def test_a_row_that_cannot_be_rebuilt_is_counted_and_left_as_it_is(tmp_path: Path) -> None:
    """Four legs cannot be filled by two contracts, so the row cannot be rebuilt today."""
    path = tmp_path / "unreadable.duckdb"
    store(path, "DeadCatBounce", [DeadCatParams(), DeadCatParams(max_hold_bars=5)])
    con = duckdb.connect(str(path))
    con.execute("UPDATE combos SET order_quantity = 2 WHERE combo_id = 1")
    con.close()
    found = {one.strategy: one for one in restamp(path, apply=True)}
    assert found["DeadCatBounce"].unreadable == 1
    assert "order_quantity 2 cannot fill" in found["DeadCatBounce"].first_error
    assert stamps(path) == [("DeadCatBounce", 0, "reconciled"), ("DeadCatBounce", 1, "reconciled")]
    assert main(["restamp_tier2.py", str(path)]) == UNREADABLE


def test_a_database_with_no_sweep_stored_has_nothing_to_check(tmp_path: Path) -> None:
    path = tmp_path / "empty.duckdb"
    results.connect(path).close()
    assert all(one.checked == 0 for one in restamp(path, apply=True))


def test_a_departure_only_the_rule_for_any_port_catches_is_still_named() -> None:
    """A rule ``departs_from_port`` catches without naming a field is reported under its own name."""
    flagged = dataclasses.replace(
        archetypes.EMACROSSOVER,
        tier2=Tier2Status.RECONCILED,
        departs_from_port=lambda _: True,
    )
    assert module._leaving(flagged, pd.Series(dtype=object)) == ("departs_from_port",)


def test_the_report_and_the_write_are_main_s_two_modes(db: Path) -> None:
    before = stamps(db)
    assert main(["restamp_tier2.py", str(db)]) == 0
    assert stamps(db) == before
    assert main(["restamp_tier2.py", str(db), "--write"]) == 0
    assert stamps(db) != before


def test_a_named_database_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    assert main(["restamp_tier2.py", str(tmp_path / "missing.duckdb")]) == UNREADABLE


def test_the_default_databases_are_the_ones_that_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaigns = tmp_path / "campaign"
    campaigns.mkdir()
    (campaigns / "InsideBar.duckdb").touch()
    (campaigns / "notes.txt").touch()
    monkeypatch.setattr(paths, "SWEEPS_DB", tmp_path / "sweeps.duckdb")
    monkeypatch.setattr(module, "CAMPAIGN_DIR", campaigns)
    assert default_databases() == [campaigns / "InsideBar.duckdb"]
    (tmp_path / "sweeps.duckdb").touch()
    assert default_databases() == [tmp_path / "sweeps.duckdb", campaigns / "InsideBar.duckdb"]


def test_no_stored_databases_is_nothing_to_do(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "SWEEPS_DB", tmp_path / "sweeps.duckdb")
    monkeypatch.setattr(module, "CAMPAIGN_DIR", tmp_path / "campaign")
    assert main(["restamp_tier2.py"]) == 0
