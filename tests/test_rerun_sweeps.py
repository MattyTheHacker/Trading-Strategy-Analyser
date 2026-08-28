"""What the re-run's stratification claims, pinned.

The sweeps themselves are not exercised here -- they need ``cache/continuous`` and take
minutes. What is testable without data is the shape of the plan, which is where a silent
mistake would live: a stratum that filters two labels at once, a label whose states are not
all covered, or a grid that is not the same 96 combinations as its neighbours.
"""

from __future__ import annotations

import duckdb
import pytest

from nqbt import archetypes, regime, timeofday
from tools.rerun_sweeps import TABLES, drop_tables, grids, strata


def test_every_regime_and_phase_gets_exactly_one_stratum() -> None:
    names = [name for name, _ in strata()]
    assert names[0] == "unfiltered"
    assert names[1:] == [f"regime={r.name}" for r in regime.Regime] + [
        f"phase={p.name}" for p in timeofday.SessionPhase
    ]


def test_no_stratum_filters_both_labels_at_once() -> None:
    """One dimension at a time is the whole design; crossing them is 21 cells, not 10."""
    for _, extra in strata():
        assert len(extra) <= 1


def test_each_filtered_stratum_admits_exactly_one_state() -> None:
    """A mask with two bits set would be a coarser stratum wearing a single label's name."""
    for name, extra in strata():
        for values in extra.values():
            assert len(values) == 1, name
            assert int(values[0]).bit_count() == 1, name


def test_the_unfiltered_stratum_narrows_nothing() -> None:
    """It is the baseline every other row is read against, so it must sweep no filter."""
    baseline = dict(strata())["unfiltered"]
    assert baseline == {}


def test_ambiguity_policy_is_not_swept_and_stays_at_nt8s_rule() -> None:
    """Policy 0 is more pessimistic than NT8, so ranking against it violates fidelity."""
    for _, grid in grids():
        assert "ambiguity_policy" not in grid.axes
        assert grid.base.ambiguity_policy == 1


def test_every_stratum_runs_the_same_number_of_combinations() -> None:
    """The stratum has to be the only difference between two rows that get compared."""
    sizes = {len(grid) for _, grid in grids()}
    assert sizes == {96}


def test_every_grid_carries_the_real_commission_and_slippage() -> None:
    for _, grid in grids():
        assert grid.base.commission_per_contract == pytest.approx(1.50)
        assert grid.base.slippage_ticks == pytest.approx(1.0)


def test_every_grid_is_deadcatbounce() -> None:
    """Named rather than left to ``Grid``'s default, which reinterprets stored results."""
    assert all(grid.archetype is archetypes.DEADCATBOUNCE for _, grid in grids())


def test_the_regime_strata_ask_for_the_efficiency_ratio_and_the_phase_strata_do_not() -> None:
    """A filtered stratum has to actually build its label, and pay for no other."""
    specs = {name: grid.required_context() for name, grid in grids()}
    assert specs["unfiltered"].regime_lookbacks == ()
    assert not specs["unfiltered"].needs_time_of_day
    assert specs["regime=DIRECTIONAL"].regime_lookbacks == (20,)
    assert not specs["regime=DIRECTIONAL"].needs_time_of_day
    assert specs["phase=MIDDAY"].needs_time_of_day
    assert specs["phase=MIDDAY"].regime_lookbacks == ()


def test_drop_tables_removes_the_stale_schema(tmp_path) -> None:
    """The drop is what stops ``_append_or_create`` silently discarding the new columns."""
    db = tmp_path / "sweeps.duckdb"
    con = duckdb.connect(str(db))
    for table in TABLES:
        con.execute(f"CREATE TABLE {table} (x INTEGER)")
    con.close()

    drop_tables(db)

    con = duckdb.connect(str(db))
    remaining = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    con.close()
    assert remaining.isdisjoint(TABLES)


def test_drop_tables_is_quiet_when_there_is_no_database(tmp_path) -> None:
    drop_tables(tmp_path / "absent.duckdb")
    assert not (tmp_path / "absent.duckdb").exists()
