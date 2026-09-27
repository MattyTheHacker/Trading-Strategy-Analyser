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

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, propaccount, stats
from nqbt.sim.types import InsideBarParams, InsideBarTrailingParams
from tests.test_campaign_sizing import sized
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_gates, campaign_holdout, campaign_paired, campaign_sizing, campaign_swept
from tools.campaign_sweep import Variant
from tools.campaign_exits import measure
from tools.campaign_gates import (
    CELL,
    Task,
    controls,
    extra_cells,
    gate4_for,
    gate_rows,
    is_done,
    paired_rows,
    replayed,
    run_task,
    save,
    shortlists,
    sizes_on_count,
    slug,
    tasks_for,
    walk_arguments,
    walked,
)
from tools.campaign_holdout import JOIN_KEYS, held_out, pair_windows, verdict
from tools.campaign_montecarlo import resample_row
from tools.campaign_propaccount import DEFAULT_PRESETS, replay_shortlist
from tools.campaign_report import log_key
from tools.campaign_shortlist import rerun_group
from tools.campaign_walkforward import run_resolution

NAME = "InsideBarTrailing"
FIXED, TOGETHER, SYMMETRIC = (
    f"trailing {rule}" for rule in ("split=0.5", "size=confluence", "size=confluence symmetric")
)
ARMS = [FIXED, TOGETHER, SYMMETRIC]
STRATA = ["phase=MIDDAY", "unfiltered"]


def stored_frame(combos: int = 30, seed: int = 0) -> pd.DataFrame:
    """Both windows of a small sizing campaign, shaped as ``campaign_report.load`` returns them."""
    rng: np.random.Generator = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for window, sweep_id in (("selection", 1), ("holdout", 2)):
        for arm in ARMS:
            for stratum in STRATA:
                for combo in range(combos):
                    pf: float = float(rng.uniform(0.6, 1.6))
                    rows.append(
                        {
                            "sweep_id": sweep_id,
                            "combo_id": combo,
                            "root": "MNQ",
                            "resolution": 10,
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
    """A stand-in for ``campaign_report.load`` over ``frame``, narrowed as the real one narrows."""

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
            "gate4_strata": ["unfiltered"],
            "prop_strata": ["unfiltered"],
            "top": 5,
            "draws": 3,
            "iterations": 50,
            "seed": 0,
            **fields,
        },
    )


@pytest.fixture
def campaign(monkeypatch):
    """The synthetic campaign behind every loader ``tasks_for`` reads through."""
    frame = stored_frame()
    monkeypatch.setattr(campaign_gates, "load", by_window(frame))
    monkeypatch.setattr(campaign_holdout, "load", by_window(frame))
    monkeypatch.setattr(campaign_paired, "load", by_window(frame))
    monkeypatch.setattr(campaign_gates, "variants_for", lambda which: {NAME: lambda root: []})
    monkeypatch.setattr(campaign_gates, "arms_for", lambda builders, name, root, resolutions: built())
    holdout = frame[frame["window"] == "holdout"].assign(first_bar=pd.Timestamp(0), last_bar=pd.Timestamp(1))
    monkeypatch.setattr(
        campaign_gates,
        "stored_rows",
        lambda name, root, window, **_: holdout.set_index(JOIN_KEYS, drop=False),
    )

    return frame


def built() -> dict[str, Variant]:
    """The three arms, each over the base its rule runs: the control's sizes on no count."""
    fixed: InsideBarTrailingParams = InsideBarTrailingParams()

    return {
        FIXED: Variant(FIXED, archetypes.INSIDEBARTRAILING, fixed),
        TOGETHER: Variant(TOGETHER, archetypes.INSIDEBARTRAILING, sized()),
        SYMMETRIC: Variant(SYMMETRIC, archetypes.INSIDEBARTRAILING, sized()),
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


def test_a_file_name_keeps_what_a_path_reads_plainly() -> None:
    assert slug("window=5m stop=atr target=+1.0s size=confluence symmetric") == (
        "window=5m_stop=atr_target=+1.0s_size=confluence_symmetric"
    )
    assert slug("a/b:c") == "a_b_c"


# -- the stored-row reads ------------------------------------------------------------------------


def test_each_held_out_shortlist_is_the_one_held_out_returns_for_its_cell(campaign) -> None:
    selection = campaign[campaign["window"] == "selection"]
    merged = pair_windows(NAME, selection, campaign[campaign["window"] == "holdout"])
    cell = merged[merged["variant"] == TOGETHER]
    held, chosen = shortlists(cell, selection[selection["variant"] == TOGETHER], frozenset({"unfiltered"}), 5)
    for stratum in STRATA:
        expected = held_out(NAME, "MNQ", "profit_factor", 5, stratum, 10, TOGETHER)
        pd.testing.assert_frame_equal(held[held["stratum"] == stratum].reset_index(drop=True), expected)

    assert set(chosen["stratum"]) == {"unfiltered"}
    assert (
        list(chosen["profit_factor"])
        == sorted(
            selection[(selection["variant"] == TOGETHER) & (selection["stratum"] == "unfiltered")][
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
    row = table[(table["variant"] == SYMMETRIC) & (table["stratum"] == "unfiltered")].iloc[0]
    cell = selection[(selection["variant"] == SYMMETRIC) & (selection["stratum"] == "unfiltered")]
    assert row["gate1_profitable_%"] == pytest.approx(100.0 * (cell["profit_factor"] > 1.0).mean())
    expected = verdict(
        NAME, merged[(merged["variant"] == SYMMETRIC) & (merged["stratum"] == "unfiltered")]
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


def test_a_task_per_arm_and_the_stored_row_reads_written_once(campaign, tmp_path) -> None:
    tasks = list(tasks_for(NAME, arguments(), pd.DataFrame(columns=CELL), tmp_path))
    assert [task.arm for task in tasks] == sorted(ARMS)
    assert all(len(task.held) == 5 * len(STRATA) for task in tasks)
    assert all(set(task.chosen["stratum"]) == {"unfiltered"} for task in tasks)
    assert {task.arm: "null" in task.reads for task in tasks} == {
        FIXED: False,
        TOGETHER: True,
        SYMMETRIC: True,
    }
    assert all(len(task.stored) == len(task.held) for task in tasks)
    assert (tmp_path / "gates" / NAME / "all.parquet").exists()
    assert (tmp_path / "paired" / NAME / "paired.parquet").exists()


def test_a_task_that_already_ran_every_read_asked_of_it_is_skipped(campaign, tmp_path) -> None:
    key = f"MNQ-10m-{slug(TOGETHER)}"
    save(tmp_path, NAME, key, {}, frozenset({"null", "gate4", "prop"}))
    arms = [task.arm for task in tasks_for(NAME, arguments(), pd.DataFrame(columns=CELL), tmp_path)]
    assert TOGETHER not in arms
    assert is_done(tmp_path, NAME, key, frozenset({"null"}))
    assert not is_done(tmp_path, NAME, key, frozenset({"null", "a read it never ran"}))
    assert not is_done(tmp_path, NAME, "never-ran", frozenset({"null"}))


def test_the_stored_row_reads_alone_re_run_nothing(campaign, tmp_path) -> None:
    assert (
        list(tasks_for(NAME, arguments(reads=["gates", "paired"]), pd.DataFrame(columns=CELL), tmp_path))
        == []
    )


def test_a_named_cell_adds_gate_4_where_it_would_not_otherwise_be_read(tmp_path) -> None:
    path = tmp_path / "cells.csv"
    pd.DataFrame([{"root": "MNQ", "resolution": 10, "variant": TOGETHER, "stratum": "phase=MIDDAY"}]).to_csv(
        path, index=False
    )
    extra = extra_cells(path)
    assert gate4_for(extra, "MNQ", 10, TOGETHER, frozenset({"unfiltered"})) == {"unfiltered", "phase=MIDDAY"}
    assert gate4_for(extra, "NQ", 10, TOGETHER, frozenset({"unfiltered"})) == {"unfiltered"}
    assert extra_cells(None).empty
    pd.DataFrame([{"root": "MNQ"}]).to_csv(path, index=False)
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
                "stratum": "unfiltered",
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
            "reads": frozenset({"null", "gate4", "prop"}),
            "gate4_strata": frozenset({"unfiltered"}),
            "prop_strata": frozenset({"unfiltered"}),
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
    table = run_task(a_task(rows, reads=frozenset({"null"})))["null"]
    theirs = campaign_sizing.null_for_shortlist(rows, "MNQ", by="profit_factor", draws=3, seed=0)
    pd.testing.assert_frame_equal(table.drop(columns=["root", "variant"]), theirs)


def test_the_bootstrap_exclusion_and_prop_replay_read_the_same_logs_their_tools_would(on_the_walk) -> None:
    rows = shortlisted_rows()
    tables = run_task(a_task(rows, reads=frozenset({"gate4", "prop"})))
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


def test_every_re_run_says_what_it_reproduced_of_its_stored_row(on_the_walk) -> None:
    rows = shortlisted_rows()
    rerun = run_task(a_task(rows, reads=frozenset({"gate4"})))["rerun"]
    assert list(rerun["stored_trades"]) == [0, 0]
    assert (rerun["trades"] > 0).all()
    assert rerun[campaign_swept.SWEPT_BARS].all()
    assert set(CELL) <= set(rerun.columns)


def test_a_null_asked_of_an_archetype_it_cannot_read_is_refused(on_the_walk) -> None:
    rows = shortlisted_rows()
    unsized = Task(**{**a_task(rows).__dict__, "name": "InsideBar"})
    run = campaign_gates.Rerun(0, InsideBarParams(), {}, pd.DataFrame(), None, True)
    with pytest.raises(TypeError, match="InsideBarTrailing's sizes alone"):
        campaign_gates.nulled(unsized, run)


def test_a_stratum_gate_4_and_prop_do_not_read_is_re_run_for_the_null_alone(on_the_walk) -> None:
    rows = shortlisted_rows().assign(stratum="phase=MIDDAY")
    tables = run_task(a_task(rows))
    assert set(tables) == {"rerun", "null"}


def test_prop_replays_each_stratum_it_is_asked_for_through_its_own_logs(on_the_walk) -> None:
    rows = pd.concat(
        [shortlisted_rows(), shortlisted_rows().assign(stratum="phase=MIDDAY")], ignore_index=True
    )
    logs = own_logs(rows.iloc[:2], on_the_walk)
    table = replayed(a_task(rows), {"unfiltered": logs, "phase=MIDDAY": logs})
    assert set(table["stratum"]) == {"unfiltered", "phase=MIDDAY"}
    assert len(table) == 2 * 2 * len(DEFAULT_PRESETS)


def test_the_walk_forward_is_the_tools_own_on_the_selection_shortlist(on_the_walk) -> None:
    chosen = shortlisted_rows().assign(window="selection")
    task = a_task(shortlisted_rows(), chosen=chosen)
    (row,) = walked(task).to_dict("records")
    theirs = run_resolution(NAME, chosen, "MNQ", 1, on_the_walk, walk_arguments())
    expected = {"variant": TOGETHER, "stratum": "unfiltered", **theirs}
    pd.testing.assert_series_equal(pd.Series(row, dtype=object), pd.Series(expected, dtype=object))


# -- the run -------------------------------------------------------------------------------------


def test_a_run_writes_every_task_and_a_second_run_re_runs_none(campaign, monkeypatch, tmp_path) -> None:
    ran = []

    def stub(task):
        ran.append(task.arm)

        return {
            "rerun": pd.DataFrame(
                [
                    {
                        "root": "MNQ",
                        "resolution": 10,
                        "trades": 1,
                        "net_pnl": 1.0,
                        "stored_trades": 1,
                        "stored_net_pnl": 1.0,
                        "swept_bars": True,
                    }
                ]
            )
        }

    monkeypatch.setattr(campaign_gates, "run_task", stub)
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor)
    argv = [
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
    assert campaign_gates.main(argv) == 0
    assert sorted(ran) == sorted(ARMS)
    assert len(list((tmp_path / "rerun" / NAME).glob("*.parquet"))) == len(ARMS)
    assert campaign_gates.main(argv) == 0
    assert len(ran) == len(ARMS), "a finished task ran again"
