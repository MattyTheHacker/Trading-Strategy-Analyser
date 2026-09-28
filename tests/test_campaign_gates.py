"""The batch read of a variant set: one load, one re-run per configuration, every read.

What carries it is that **a cell read here and the same cell read by its own tool agree**, so
each read is pinned against that tool's function on the same rows: the shortlist against
``held_out``, the gates against ``profile`` and ``verdict``, the paired read against
``campaign_paired.report``, and the re-running reads against the null, the bootstrap, the
exclusion and the prop replay each given its own re-run.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import logging
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, propaccount, stats
from nqbt.sim.types import InsideBarParams, InsideBarTrailingParams
from tests.test_campaign_sizing import sized
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_gates, campaign_holdout, campaign_paired, campaign_sizing, campaign_swept
from tools.campaign_exits import measure
from tools.campaign_gates import (
    CELL,
    RERUN,
    Rerun,
    Task,
    arms_for,
    asked_of,
    controls,
    extra_cells,
    gate4_for,
    gate_rows,
    paired_rows,
    recorded,
    refuse_clashes,
    remaining,
    replace_strata,
    replayed,
    report_reruns,
    run_task,
    save,
    settle,
    shortlists,
    sizes_on_count,
    slug,
    task_key,
    tasks_for,
    walk_arguments,
    walked,
    written,
)
from tools.campaign_holdout import JOIN_KEYS, held_out, pair_windows, verdict
from tools.campaign_montecarlo import resample_row
from tools.campaign_propaccount import DEFAULT_PRESETS, replay_shortlist
from tools.campaign_report import log_key
from tools.campaign_shortlist import TOP, rerun_group
from tools.campaign_sweep import Variant
from tools.campaign_walkforward import run_resolution

NAME = "InsideBarTrailing"
FIXED, TOGETHER, SYMMETRIC = (
    f"trailing {rule}" for rule in ("split=0.5", "size=confluence", "size=confluence symmetric")
)
ARMS = [FIXED, TOGETHER, SYMMETRIC]
STRATA = ["phase=MIDDAY", "unfiltered"]
MIDDAY, UNFILTERED = STRATA
USAGE_ERROR = "2"
"""The status argparse exits with on an argument it refuses, as ``SystemExit`` reads it."""


def stored_frame(cells: tuple[tuple[str, int], ...] = (("MNQ", 10),), combos: int = 30) -> pd.DataFrame:
    """Both windows of a small sizing campaign, shaped as ``campaign_report.load`` returns them."""
    rng: np.random.Generator = np.random.default_rng(0)
    rows: list[dict[str, object]] = []
    for window, sweep_id in (("selection", 1), ("holdout", 2)):
        for root, minutes in cells:
            for arm in ARMS:
                for stratum in STRATA:
                    for combo in range(combos):
                        pf: float = float(rng.uniform(0.6, 1.6))
                        rows.append(
                            {
                                "sweep_id": sweep_id,
                                "combo_id": combo,
                                "root": root,
                                "resolution": minutes,
                                "variant": arm,
                                "stratum": stratum,
                                "window": window,
                                "stop_ticks": combo % 5,
                                "target_ticks": combo // 5,
                                "profit_factor": pf,
                                "net_pnl": (pf - 1.0) * 1000.0,
                                "trades": 50,
                                "max_drawdown": 500.0,
                                "net_to_drawdown": (pf - 1.0) * 2.0,
                                "session_close_share": 0.1,
                                "ambiguous_share": 0.0,
                            },
                        )

    return pd.DataFrame(rows)


def by_window(frame: pd.DataFrame):
    """Build a stand-in for ``campaign_report.load`` over ``frame``, narrowed as the real one narrows."""

    def load(name, windows, *, variants=None, resolutions=None):
        narrowed = frame[frame["window"].isin(windows)]
        if variants is not None:
            narrowed = narrowed[narrowed["variant"].isin(variants)]

        if resolutions is not None:
            narrowed = narrowed[narrowed["resolution"].isin(resolutions)]

        return narrowed

    return load


def arguments(**fields) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "variants": "ibt-sizing",
            "roots": ["MNQ"],
            "resolutions": [10],
            "reads": list(campaign_gates.READS),
            "gate4_strata": [UNFILTERED],
            "prop_strata": [UNFILTERED],
            "draws": 3,
            "iterations": 50,
            "seed": 0,
            **fields,
        },
    )


def built() -> dict[str, Variant]:
    """Build the three arms, each over the base its rule runs: the control's sizes on no count."""
    fixed: InsideBarTrailingParams = InsideBarTrailingParams()

    return {
        FIXED: Variant(FIXED, archetypes.INSIDEBARTRAILING, fixed),
        TOGETHER: Variant(TOGETHER, archetypes.INSIDEBARTRAILING, sized()),
        SYMMETRIC: Variant(SYMMETRIC, archetypes.INSIDEBARTRAILING, sized()),
    }


def point_at(monkeypatch, frame: pd.DataFrame) -> pd.DataFrame:
    """Every loader ``tasks_for`` reads through, pointed at ``frame``."""
    monkeypatch.setattr(campaign_gates, "load", by_window(frame))
    monkeypatch.setattr(campaign_holdout, "load", by_window(frame))
    monkeypatch.setattr(campaign_paired, "load", by_window(frame))
    monkeypatch.setattr(campaign_gates, "variants_for", lambda which: {NAME: lambda root: []})
    monkeypatch.setattr(
        campaign_gates,
        "arms_for",
        lambda builders, name, root, resolutions: {
            (arm, minutes): variant for arm, variant in built().items() for minutes in resolutions
        },
    )
    holdout = frame[frame["window"] == "holdout"].assign(first_bar=pd.Timestamp(0), last_bar=pd.Timestamp(1))
    monkeypatch.setattr(
        campaign_gates,
        "stored_rows",
        lambda name, root, window, **_: holdout.set_index(JOIN_KEYS, drop=False),
    )

    return frame


@pytest.fixture
def campaign(monkeypatch):
    """Provide the synthetic campaign behind every loader ``tasks_for`` reads through."""
    return point_at(monkeypatch, stored_frame())


def every_read_recorded() -> dict[str, frozenset[str]]:
    """Return what a sizing arm's default run records: each stratum re-run and nulled, the rest unfiltered."""
    return {
        RERUN: frozenset(STRATA),
        "null": frozenset(STRATA),
        "gate4": frozenset({UNFILTERED}),
        "prop": frozenset({UNFILTERED}),
    }


# -- naming the arms -----------------------------------------------------------------------------


def test_every_arm_is_read_against_its_fixed_size_and_symmetric_against_add_only() -> None:
    fixed, together, symmetric = (
        f"bracket {rule}" for rule in ("size=fixed", "size=confluence", "size=confluence symmetric")
    )
    arms = [fixed, together, symmetric, "bracket size=trend"]
    assert sorted(controls(arms)) == sorted(
        [(fixed, together), (fixed, symmetric), (fixed, "bracket size=trend"), (together, symmetric)],
    )


def test_insidebartrailing_reads_against_its_half_split_and_each_tier_against_its_inverse() -> None:
    arms = [
        "trailing split=0.5",
        "trailing split=0.25",
        "trailing tier=trend-age",
        "trailing tier=trend-age inverted",
        "trailing size=confluence",
        "trailing size=confluence symmetric",
    ]
    assert sorted(controls(arms)) == sorted(
        [
            ("trailing split=0.5", "trailing split=0.25"),
            ("trailing split=0.5", "trailing tier=trend-age"),
            ("trailing tier=trend-age inverted", "trailing tier=trend-age"),
            ("trailing split=0.5", "trailing size=confluence"),
            ("trailing split=0.5", "trailing size=confluence symmetric"),
            ("trailing size=confluence", "trailing size=confluence symmetric"),
        ],
    )


def test_a_variant_name_holding_spaces_and_signs_splits_at_its_rule() -> None:
    assert controls(["target=+1.0s size=fixed", "target=+1.0s size=confluence symmetric"]) == [
        ("target=+1.0s size=fixed", "target=+1.0s size=confluence symmetric"),
    ]
    assert controls(["an arm with no rule", "size=fixed"]) == []


def test_only_an_arm_whose_base_sizes_on_a_count_is_nulled() -> None:
    arms = built()
    assert sizes_on_count(arms[TOGETHER])
    assert not sizes_on_count(arms[FIXED])
    assert not sizes_on_count(Variant("bracket", archetypes.INSIDEBAR, InsideBarParams())), (
        "no count to size on"
    )


def test_an_arm_is_looked_up_at_each_resolution_it_is_built_for() -> None:
    builders = {
        NAME: lambda root: [
            Variant(TOGETHER, archetypes.INSIDEBARTRAILING, sized(), resolutions=(5,)),
            Variant(TOGETHER, archetypes.INSIDEBARTRAILING, InsideBarTrailingParams(), resolutions=(10,)),
        ],
    }
    arms = arms_for(builders, NAME, "MNQ", [5, 10])
    assert sizes_on_count(arms[TOGETHER, 5])
    assert not sizes_on_count(arms[TOGETHER, 10]), "the later resolution's arm did not replace the earlier's"
    assert list(arms_for(builders, NAME, "MNQ", [5])) == [(TOGETHER, 5)]


def test_a_file_name_keeps_what_a_path_reads_plainly() -> None:
    assert slug("window=5m stop=atr target=+1.0s size=confluence symmetric") == (
        "window=5m_stop=atr_target=+1.0s_size=confluence_symmetric"
    )
    assert slug("a/b:c") == "a_b_c"
    assert task_key("MNQ", 10, TOGETHER) == f"MNQ-10m-{slug(TOGETHER)}"


def test_two_arms_one_file_system_would_take_for_one_file_are_refused() -> None:
    refuse_clashes(ARMS)
    with pytest.raises(SystemExit, match="same file"):
        refuse_clashes(["size=a/b", "size=a_b"])

    with pytest.raises(SystemExit, match="same file"):
        refuse_clashes(["size=Fixed", "size=fixed"])


# -- the stored-row reads ------------------------------------------------------------------------


def test_each_held_out_shortlist_is_the_one_held_out_returns_for_its_cell(campaign) -> None:
    selection = campaign[campaign["window"] == "selection"]
    merged = pair_windows(NAME, selection, campaign[campaign["window"] == "holdout"])
    cell = merged[merged["variant"] == TOGETHER]
    held, chosen = shortlists(cell, selection[selection["variant"] == TOGETHER], frozenset({UNFILTERED}), 5)
    for stratum in STRATA:
        expected = held_out(NAME, "MNQ", "profit_factor", 5, stratum, 10, TOGETHER)
        pd.testing.assert_frame_equal(held[held["stratum"] == stratum].reset_index(drop=True), expected)

    assert set(chosen["stratum"]) == {UNFILTERED}
    assert (
        list(chosen["profit_factor"])
        == sorted(
            selection[(selection["variant"] == TOGETHER) & (selection["stratum"] == UNFILTERED)][
                "profit_factor"
            ],
            reverse=True,
        )[:5]
    )


def test_the_gates_are_profile_and_verdict_cell_by_cell(campaign) -> None:
    selection = campaign[campaign["window"] == "selection"]
    merged = pair_windows(NAME, selection, campaign[campaign["window"] == "holdout"])
    table = gate_rows(NAME, selection, merged)
    assert len(table) == len(ARMS) * len(STRATA)
    row = table[(table["variant"] == SYMMETRIC) & (table["stratum"] == UNFILTERED)].iloc[0]
    cell = selection[(selection["variant"] == SYMMETRIC) & (selection["stratum"] == UNFILTERED)]
    assert row["gate1_profitable_%"] == pytest.approx(100.0 * (cell["profit_factor"] > 1.0).mean())
    expected = verdict(
        NAME, merged[(merged["variant"] == SYMMETRIC) & (merged["stratum"] == UNFILTERED)]
    ).iloc[0]
    for column in ("hold_top20_pf", "hold_all_median_pf", "passes", "rank_corr"):
        assert row[column] == expected[column]


def test_the_paired_read_is_campaign_paireds_report_stratum_by_stratum(campaign) -> None:
    holdout = campaign[campaign["window"] == "holdout"]
    table = paired_rows(NAME, holdout, ARMS)
    assert set(zip(table["control_arm"], table["treatment_arm"], strict=True)) == set(controls(ARMS))
    for stratum in STRATA:
        mine = table[(table["control_arm"] == TOGETHER) & (table["stratum"] == stratum)]
        theirs = campaign_paired.report(NAME, TOGETHER, SYMMETRIC, ["holdout"], "profit_factor", stratum)
        pd.testing.assert_frame_equal(
            mine[theirs.columns].reset_index(drop=True),
            theirs.reset_index(drop=True),
        )


def test_a_task_per_arm_re_runs_only_the_strata_some_read_is_asked_for(campaign, tmp_path) -> None:
    tasks = list(tasks_for(NAME, arguments(), extra_cells(None), tmp_path))
    assert [task.arm for task in tasks] == sorted(ARMS)
    assert {task.arm: set(task.held["stratum"]) for task in tasks} == {
        FIXED: {UNFILTERED},
        TOGETHER: set(STRATA),
        SYMMETRIC: set(STRATA),
    }
    assert {task.arm: task.strata["null"] for task in tasks} == {
        FIXED: frozenset(),
        TOGETHER: frozenset(STRATA),
        SYMMETRIC: frozenset(STRATA),
    }
    assert all(len(task.held) == TOP * len(set(task.held["stratum"])) for task in tasks)
    assert all(set(task.chosen["stratum"]) == {UNFILTERED} for task in tasks)
    assert all(len(task.stored) == len(task.held) for task in tasks)


def test_the_stored_row_reads_keep_a_file_per_root_and_resolution(monkeypatch, tmp_path) -> None:
    point_at(monkeypatch, stored_frame((("MNQ", 10), ("NQ", 10), ("MNQ", 15))))
    only = arguments(reads=["gates", "paired"])
    list(tasks_for(NAME, only, extra_cells(None), tmp_path))
    list(tasks_for(NAME, arguments(reads=["gates", "paired"], resolutions=[15]), extra_cells(None), tmp_path))
    for table in ("gates", "paired"):
        files = sorted(path.name for path in (tmp_path / table / NAME).glob("*.parquet"))
        assert files == ["MNQ-10m.parquet", "MNQ-15m.parquet"], "a root not asked for was written"
        first = pd.read_parquet(tmp_path / table / NAME / "MNQ-10m.parquet")
        assert set(first["root"]) == {"MNQ"}
        assert set(first["resolution"]) == {10}, "the second run replaced the first's cells"


def test_the_stored_row_reads_alone_re_run_nothing(campaign, tmp_path) -> None:
    assert list(tasks_for(NAME, arguments(reads=["gates", "paired"]), extra_cells(None), tmp_path)) == []


def test_a_task_whose_every_read_is_recorded_is_skipped(campaign, tmp_path) -> None:
    save(tmp_path, NAME, task_key("MNQ", 10, TOGETHER), {}, every_read_recorded())
    arms = [task.arm for task in tasks_for(NAME, arguments(), extra_cells(None), tmp_path)]
    assert arms == sorted([FIXED, SYMMETRIC])


def test_a_later_run_reads_only_the_cells_it_adds(campaign, tmp_path) -> None:
    save(tmp_path, NAME, task_key("MNQ", 10, TOGETHER), {}, every_read_recorded())
    extra = pd.DataFrame(
        [{"strategy": NAME, "root": "MNQ", "resolution": 10, "variant": TOGETHER, "stratum": MIDDAY}],
    )
    (task,) = (
        task for task in tasks_for(NAME, arguments(reads=["gate4"]), extra, tmp_path) if task.arm == TOGETHER
    )
    assert task.strata == {
        "null": frozenset(),
        "gate4": frozenset({MIDDAY}),
        "prop": frozenset(),
        RERUN: frozenset(),
    }, "gate 4 read again unfiltered, or a re-run written twice"
    assert set(task.held["stratum"]) == {MIDDAY}
    assert set(task.chosen["stratum"]) == {MIDDAY}


def test_what_a_task_records_is_added_to_rather_than_replaced(tmp_path) -> None:
    save(tmp_path, NAME, "key", {}, {"null": frozenset({MIDDAY}), RERUN: frozenset({MIDDAY})})
    save(tmp_path, NAME, "key", {}, {"gate4": frozenset({UNFILTERED}), RERUN: frozenset({UNFILTERED})})
    assert recorded(tmp_path, NAME, "key") == {
        "null": frozenset({MIDDAY}),
        "gate4": frozenset({UNFILTERED}),
        RERUN: frozenset(STRATA),
    }
    assert remaining({"null": frozenset({MIDDAY})}, recorded(tmp_path, NAME, "key")) == {}
    assert recorded(tmp_path, NAME, "never-ran") == {}


def test_what_is_left_of_a_read_is_what_no_earlier_run_recorded() -> None:
    asked = {"null": frozenset(STRATA), "gate4": frozenset({UNFILTERED}), "prop": frozenset()}
    done = {"null": frozenset({MIDDAY}), RERUN: frozenset({MIDDAY})}
    assert remaining(asked, done) == {
        "null": frozenset({UNFILTERED}),
        "gate4": frozenset({UNFILTERED}),
        "prop": frozenset(),
        RERUN: frozenset({UNFILTERED}),
    }


def test_each_read_is_asked_of_the_strata_an_arm_has_rows_in() -> None:
    present = frozenset({UNFILTERED})
    asked = asked_of(
        frozenset({"null", "gate4"}), present, frozenset(STRATA), frozenset(STRATA), counted=False
    )
    assert asked == {"null": frozenset(), "gate4": present, "prop": frozenset()}
    assert asked_of(frozenset({"null"}), present, frozenset(), frozenset(), counted=True)["null"] == present


def test_a_table_replaces_the_strata_it_read_and_keeps_the_rest(tmp_path) -> None:
    path = tmp_path / "table.parquet"
    first = pd.DataFrame({"stratum": [MIDDAY, UNFILTERED], "value": [1, 2]})
    replace_strata(path, first, frozenset(STRATA))
    replace_strata(path, pd.DataFrame({"stratum": [UNFILTERED], "value": [3]}), frozenset({UNFILTERED}))
    table = pd.read_parquet(path).sort_values("stratum").reset_index(drop=True)
    pd.testing.assert_frame_equal(table, pd.DataFrame({"stratum": [MIDDAY, UNFILTERED], "value": [1, 3]}))
    replace_strata(path, None, frozenset(STRATA))
    assert not path.exists(), "a read that now returns nothing left its old rows behind"


def half_written(path) -> None:
    """Write what a run killed partway through writing ``path`` leaves there."""
    Path(path).write_bytes(b"PAR1{")
    msg = "killed mid-write"
    raise OSError(msg)


@pytest.mark.parametrize(
    ("owner", "method", "dies"),
    [
        (pd.DataFrame, "to_parquet", lambda frame, path, **_: half_written(path)),
        (Path, "write_text", lambda path, *_, **__: half_written(path)),
    ],
    ids=["table", "marker"],
)
def test_a_save_killed_mid_write_leaves_every_file_readable_for_the_next(
    monkeypatch, tmp_path, owner, method, dies
) -> None:
    key = task_key("MNQ", 10, TOGETHER)
    table = written(tmp_path, RERUN, NAME, key)
    save(tmp_path, NAME, key, {RERUN: pd.DataFrame({"stratum": [MIDDAY]})}, {RERUN: frozenset({MIDDAY})})
    later = ({RERUN: pd.DataFrame({"stratum": [UNFILTERED]})}, {RERUN: frozenset({UNFILTERED})})
    with monkeypatch.context() as killed:
        killed.setattr(owner, method, dies)
        with pytest.raises(OSError, match="mid-write"):
            save(tmp_path, NAME, key, *later)

    assert recorded(tmp_path, NAME, key) == {RERUN: frozenset({MIDDAY})}
    assert MIDDAY in set(pd.read_parquet(table)["stratum"])
    save(tmp_path, NAME, key, *later)
    assert set(pd.read_parquet(table)["stratum"]) == set(STRATA)
    assert recorded(tmp_path, NAME, key) == {RERUN: frozenset(STRATA)}
    assert list(tmp_path.rglob("*.tmp")) == [], "a whole write left its temporary file behind"


def test_an_out_directory_refuses_a_run_at_other_settings(tmp_path) -> None:
    settle(tmp_path, arguments())
    settle(tmp_path, arguments(roots=["NQ"], resolutions=[5]))
    with pytest.raises(SystemExit, match="another --out"):
        settle(tmp_path, arguments(seed=1))


def test_a_named_cell_adds_gate_4_where_it_would_not_otherwise_be_read(tmp_path) -> None:
    path = tmp_path / "cells.csv"
    cell = {"strategy": NAME, "root": "MNQ", "resolution": 10, "variant": TOGETHER, "stratum": MIDDAY}
    pd.DataFrame([cell]).to_csv(path, index=False)
    extra = extra_cells(path)
    everywhere = frozenset({UNFILTERED})
    assert gate4_for(extra, (NAME, "MNQ", 10, TOGETHER), everywhere) == {UNFILTERED, MIDDAY}
    assert gate4_for(extra, (NAME, "NQ", 10, TOGETHER), everywhere) == everywhere
    assert gate4_for(extra, ("InsideBar", "MNQ", 10, TOGETHER), everywhere) == everywhere, (
        "a cell was read on another archetype's arm of the same name"
    )
    assert extra_cells(None).empty
    pd.DataFrame([{key: value for key, value in cell.items() if key != "strategy"}]).to_csv(path, index=False)
    with pytest.raises(SystemExit, match="a cell is"):
        extra_cells(path)


# -- the re-running reads ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def walk():
    return walk_bars(6000, seed=9)


def shortlisted_rows() -> pd.DataFrame:
    """Two configurations whose contexts differ, so the task's one dataset is a union."""
    rows = []
    for combo_id, fields in ((3, {}), (4, {"slow_sma_period": 21, "order_quantity": 6})):
        params = dataclasses.replace(sized(), **fields)
        rows.append(
            {
                "sweep_id": 9,
                "combo_id": combo_id,
                "root": "MNQ",
                "resolution": 1,
                "stratum": UNFILTERED,
                "variant": TOGETHER,
                "window": "holdout",
                "profit_factor": 1.1,
                "trades": 0,
                "net_pnl": 0.0,
                **dataclasses.asdict(params),
            },
        )

    return pd.DataFrame(rows)


@pytest.fixture
def on_the_walk(monkeypatch, walk):
    """Every loader a re-run reads through, pointed at the synthetic walk."""
    monkeypatch.setattr(campaign_gates, "archive", lambda root: walk)
    monkeypatch.setattr(campaign_gates, "candidate_bars", lambda stored, bars: (bars,))
    monkeypatch.setattr(
        campaign_gates, "bars_for", lambda candidates, stored, block, minutes: (candidates[0], True)
    )
    monkeypatch.setattr(campaign_sizing, "stored_rows", lambda *_: pd.DataFrame())
    monkeypatch.setattr(campaign_sizing.splice, "load_continuous", lambda _root: walk)
    monkeypatch.setattr(campaign_sizing, "candidate_bars", lambda stored, archive: (archive,))
    monkeypatch.setattr(
        campaign_sizing, "bars_for", lambda candidates, stored, block, minutes: (candidates[0], True)
    )

    return walk


def reading(*reads: str, stratum: str = UNFILTERED) -> dict[str, frozenset[str]]:
    """Return a task's strata that re-runs ``stratum`` and writes each of ``reads`` for it."""
    return {read: frozenset({stratum}) for read in (RERUN, *reads)}


def a_task(rows: pd.DataFrame, **fields) -> Task:
    return Task(
        **{
            "name": NAME,
            "root": "MNQ",
            "minutes": 1,
            "arm": TOGETHER,
            "held": rows,
            "chosen": pd.DataFrame(columns=JOIN_KEYS),
            "stored": pd.DataFrame(),
            "strata": reading("null", "gate4", "prop"),
            "draws": 3,
            "iterations": 40,
            "seed": 0,
            **fields,
        },
    )


def own_logs(rows: pd.DataFrame, walk: pd.DataFrame) -> dict[tuple[int, int], pd.DataFrame]:
    """Each row's log as ``campaign_shortlist``'s re-run builds it, for the reads to be set against."""
    return {
        log_key(row): log
        for row, _, log in rerun_group(
            rows, walk, archetypes.INSIDEBARTRAILING, "MNQ", 1, campaign_gates.context.PriceBasis.RAW
        )
    }


def test_the_null_is_campaign_sizings_on_the_same_rows(on_the_walk) -> None:
    rows = shortlisted_rows()
    table = run_task(a_task(rows, strata=reading("null")))["null"]
    theirs = campaign_sizing.null_for_shortlist(rows, "MNQ", by="profit_factor", draws=3, seed=0)
    pd.testing.assert_frame_equal(table.drop(columns=["root", "variant"]), theirs)


def test_the_bootstrap_exclusion_and_prop_replay_read_the_same_logs_their_tools_would(on_the_walk) -> None:
    rows = shortlisted_rows()
    tables = run_task(a_task(rows, strata=reading("gate4", "prop")))
    logs = own_logs(rows, on_the_walk)
    pd.testing.assert_frame_equal(
        tables["exclusion"], measure(rows, logs, stats.SESSION_CLOSE, require_stored=False)
    )
    resampled = [resample_row(row, logs[log_key(row)], 40, 0) for _, row in rows.iterrows()]
    assert tables["permutation"].to_dict("records") == [permutation for permutation, _ in resampled]
    pd.testing.assert_frame_equal(
        tables["bootstrap"], pd.concat([spread for _, spread in resampled], ignore_index=True)
    )
    accounts = [propaccount.preset(name) for name in DEFAULT_PRESETS]
    pd.testing.assert_frame_equal(tables["prop"], replay_shortlist(rows, logs, accounts, None))
    assert "null" not in tables


def test_a_configuration_with_no_trades_has_no_exclusion_row_as_its_tool_gives_none(monkeypatch) -> None:
    rows = shortlisted_rows().iloc[:1]
    empty = Rerun(0, sized(), {"trades": 0, "net_pnl": 0.0}, pd.DataFrame(), None, True)
    monkeypatch.setattr(campaign_gates, "reruns", lambda task: iter([empty]))
    tables = run_task(a_task(rows, strata=reading("gate4")))
    assert "exclusion" not in tables
    assert "permutation" not in tables
    assert measure(rows, {log_key(rows.iloc[0]): pd.DataFrame()}, stats.SESSION_CLOSE).empty
    assert list(tables[RERUN]["trades"]) == [0]


def test_every_re_run_says_what_it_reproduced_of_its_stored_row(on_the_walk) -> None:
    rows = shortlisted_rows()
    rerun = run_task(a_task(rows, strata=reading("gate4")))[RERUN]
    assert list(rerun["stored_trades"]) == [0, 0]
    assert (rerun["trades"] > 0).all()
    assert rerun[campaign_swept.SWEPT_BARS].all()
    assert set(CELL) <= set(rerun.columns)
    assert set(rerun["strategy"]) == {NAME}


def test_a_re_run_an_earlier_run_wrote_is_not_written_again(on_the_walk) -> None:
    tables = run_task(a_task(shortlisted_rows(), strata={"gate4": frozenset({UNFILTERED})}))
    assert RERUN not in tables
    assert "exclusion" in tables


def test_a_null_asked_of_an_archetype_it_cannot_read_is_refused(on_the_walk) -> None:
    rows = shortlisted_rows()
    unsized = Task(**{**a_task(rows).__dict__, "name": "InsideBar"})
    run = Rerun(0, InsideBarParams(), {}, pd.DataFrame(), None, True)
    with pytest.raises(TypeError, match="InsideBarTrailing's sizes alone"):
        campaign_gates.nulled(unsized, run)


def test_a_stratum_gate_4_and_prop_do_not_read_is_re_run_for_the_null_alone(on_the_walk) -> None:
    rows = shortlisted_rows().assign(stratum=MIDDAY)
    strata = {
        **reading("null", stratum=MIDDAY),
        "gate4": frozenset({UNFILTERED}),
        "prop": frozenset({UNFILTERED}),
    }
    tables = run_task(a_task(rows, strata=strata))
    assert set(tables) == {RERUN, "null"}


def test_prop_replays_each_stratum_it_is_asked_for_through_its_own_logs(on_the_walk) -> None:
    rows = pd.concat([shortlisted_rows(), shortlisted_rows().assign(stratum=MIDDAY)], ignore_index=True)
    logs = own_logs(rows.iloc[:2], on_the_walk)
    table = replayed(a_task(rows), {UNFILTERED: logs, MIDDAY: logs})
    assert set(table["stratum"]) == set(STRATA)
    assert len(table) == 2 * 2 * len(DEFAULT_PRESETS)


def test_the_walk_forward_is_the_tools_own_on_the_selection_shortlist(on_the_walk) -> None:
    chosen = shortlisted_rows().assign(window="selection")
    task = a_task(shortlisted_rows(), chosen=chosen)
    (row,) = walked(task).to_dict("records")
    theirs = run_resolution(NAME, chosen, "MNQ", 1, on_the_walk, walk_arguments())
    expected = {"variant": TOGETHER, "stratum": UNFILTERED, **theirs}
    pd.testing.assert_series_equal(pd.Series(row, dtype=object), pd.Series(expected, dtype=object))


# -- the run -------------------------------------------------------------------------------------


def argv_for(tmp_path) -> list[str]:
    return [
        "campaign_gates.py",
        "--variants",
        "ibt-sizing",
        "--strategies",
        NAME,
        "--roots",
        "MNQ",
        "--resolutions",
        "10",
        "--out",
        str(tmp_path),
    ]


def reproduced(task: Task) -> dict[str, pd.DataFrame]:
    """Return what a task that reproduced its one stored row would write."""
    return {
        RERUN: pd.DataFrame(
            [
                {
                    "strategy": task.name,
                    "root": task.root,
                    "resolution": task.minutes,
                    "variant": task.arm,
                    "stratum": UNFILTERED,
                    "trades": 1,
                    "net_pnl": 1.0,
                    "stored_trades": 1,
                    "stored_net_pnl": 1.0,
                    "swept_bars": True,
                },
            ],
        ),
    }


@pytest.fixture
def in_threads(monkeypatch):
    """Run the pool in threads, so a stubbed ``run_task`` reaches it."""
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor)


def test_a_run_writes_every_task_and_a_second_run_re_runs_none(
    campaign, in_threads, monkeypatch, tmp_path
) -> None:
    ran = []

    def stub(task):
        ran.append(task.arm)

        return reproduced(task)

    monkeypatch.setattr(campaign_gates, "run_task", stub)
    assert campaign_gates.main(argv_for(tmp_path)) == 0
    assert sorted(ran) == sorted(ARMS)
    assert len(list((tmp_path / RERUN / NAME).glob("*.parquet"))) == len(ARMS)
    assert campaign_gates.main(argv_for(tmp_path)) == 0
    assert len(ran) == len(ARMS), "a finished task ran again"


def test_a_failed_task_leaves_the_others_saved_and_the_run_failing(
    campaign, in_threads, monkeypatch, tmp_path
) -> None:
    def failing(task):
        if task.arm == TOGETHER:
            msg = "a task that fails"
            raise RuntimeError(msg)

        return reproduced(task)

    monkeypatch.setattr(campaign_gates, "run_task", failing)
    assert campaign_gates.main(argv_for(tmp_path)) == 1
    written = sorted(path.stem for path in (tmp_path / RERUN / NAME).glob("*.parquet"))
    assert written == sorted(task_key("MNQ", 10, arm) for arm in (FIXED, SYMMETRIC))
    assert recorded(tmp_path, NAME, task_key("MNQ", 10, TOGETHER)) == {}
    ran = []
    monkeypatch.setattr(campaign_gates, "run_task", lambda task: ran.append(task.arm) or reproduced(task))
    assert campaign_gates.main(argv_for(tmp_path)) == 0
    assert ran == [TOGETHER], "the resumed run did more than the task that failed"


def test_a_task_that_fails_to_save_leaves_the_others_saved_and_the_run_failing(
    campaign, in_threads, monkeypatch, tmp_path
) -> None:
    real_save = campaign_gates.save

    def failing(out, name, key, tables, strata):
        if key == task_key("MNQ", 10, TOGETHER):
            msg = "the disk filled"
            raise OSError(msg)

        real_save(out, name, key, tables, strata)

    monkeypatch.setattr(campaign_gates, "run_task", reproduced)
    monkeypatch.setattr(campaign_gates, "save", failing)
    assert campaign_gates.main(argv_for(tmp_path)) == 1
    written = sorted(path.stem for path in (tmp_path / RERUN / NAME).glob("*.parquet"))
    assert written == sorted(task_key("MNQ", 10, arm) for arm in (FIXED, SYMMETRIC))
    assert recorded(tmp_path, NAME, task_key("MNQ", 10, TOGETHER)) == {}


def test_a_root_whose_tasks_cannot_be_built_still_saves_the_tasks_already_started(
    in_threads, monkeypatch, tmp_path
) -> None:
    point_at(monkeypatch, stored_frame((("MNQ", 10), ("NQ", 10))))
    real_rows = campaign_gates.stored_rows

    def duplicated_on_nq(name, root, window, **narrowing):
        if root == "NQ":
            msg = "NQ stores more than one row under the same keys"
            raise RuntimeError(msg)

        return real_rows(name, root, window, **narrowing)

    monkeypatch.setattr(campaign_gates, "stored_rows", duplicated_on_nq)
    monkeypatch.setattr(campaign_gates, "run_task", reproduced)
    argv = [*argv_for(tmp_path), "--roots", "MNQ", "NQ"]
    assert campaign_gates.main(argv) == 1
    written = sorted(path.stem for path in (tmp_path / RERUN / NAME).glob("*.parquet"))
    assert written == sorted(task_key("MNQ", 10, arm) for arm in ARMS)
    ran = []
    monkeypatch.setattr(campaign_gates, "stored_rows", real_rows)
    monkeypatch.setattr(campaign_gates, "run_task", lambda task: ran.append(task.root) or reproduced(task))
    assert campaign_gates.main(argv) == 0
    assert ran == ["NQ"] * len(ARMS), "the resumed run did more than the root that failed"


class DeadPool(concurrent.futures.Executor):
    """A process pool whose worker died on its first task: that task fails, and it takes no more."""

    given: int = 0

    def submit(self, _fn: object, /, *_: object, **__: object) -> concurrent.futures.Future[object]:
        """Return a future failed as a dead worker fails it, or refuse once one has been handed out."""
        msg = "a child process terminated abruptly"
        if self.given:
            raise BrokenProcessPool(msg)

        self.given += 1
        future: concurrent.futures.Future[object] = concurrent.futures.Future()
        future.set_exception(BrokenProcessPool(msg))

        return future


def test_a_worker_that_dies_fails_its_own_archetype_and_the_run_still_reports(
    campaign, capsys, monkeypatch, tmp_path
) -> None:
    other = "InsideBar"
    pools = iter([DeadPool(), concurrent.futures.ThreadPoolExecutor()])
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", lambda **_: next(pools))
    monkeypatch.setattr(
        campaign_gates, "variants_for", lambda which: {NAME: lambda root: [], other: lambda root: []}
    )
    monkeypatch.setattr(campaign_gates, "run_task", reproduced)
    assert campaign_gates.main([*argv_for(tmp_path), "--strategies", NAME, other]) == 1
    assert not (tmp_path / RERUN / NAME).exists()
    assert len(list((tmp_path / RERUN / other).glob("*.parquet"))) == len(ARMS), (
        "the next archetype ran on the dead pool"
    )
    logged = capsys.readouterr()
    assert f"{len(ARMS)} of {len(ARMS)} arms reproduced" in logged.out
    assert "a run over the same --out retries them" in logged.err


def test_a_variant_set_that_does_not_exist_is_refused(tmp_path) -> None:
    argv = argv_for(tmp_path)
    argv[argv.index("ibt-sizing")] = "ibt-sizng"
    with pytest.raises(SystemExit, match=USAGE_ERROR):
        campaign_gates.main(argv)

    assert not (tmp_path / "settings.json").exists()


def test_an_archetype_the_variant_set_does_not_cover_is_refused(capsys, tmp_path) -> None:
    argv = argv_for(tmp_path)
    argv[argv.index(NAME)] = "InsideBarTrailng"
    with pytest.raises(SystemExit, match=USAGE_ERROR):
        campaign_gates.main(argv)

    assert "not ['InsideBarTrailng']" in capsys.readouterr().err
    assert not (tmp_path / "settings.json").exists()


def test_the_re_run_report_names_each_arm_that_fell_short(caplog, tmp_path) -> None:
    for name, trades in ((NAME, 1), ("InsideBar", 2)):
        task = a_task(pd.DataFrame(), name=name)
        table = reproduced(task)[RERUN].assign(trades=trades)
        path = tmp_path / RERUN / name / f"{task.key}.parquet"
        path.parent.mkdir(parents=True)
        table.to_parquet(path, index=False)

    with caplog.at_level(logging.INFO, logger=campaign_gates.__name__):
        report_reruns(tmp_path)

    assert "1 of 2 arms reproduced" in caplog.text
    assert "InsideBar " in caplog.text.split("these did not")[1], "the arm that fell short went unnamed"
