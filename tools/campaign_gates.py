r"""Every per-cell read of a swept variant set, over every cell, from one load per archetype.

    ./.venv/Scripts/python.exe tools/campaign_gates.py --variants ibt-sizing --resolutions 5 \
        --out <dir> --n-jobs 6
    ./.venv/Scripts/python.exe tools/campaign_gates.py --variants ibt-sizing --resolutions 5 \
        --out <dir> --reads gate4 --cells <csv of variant, root, resolution and stratum>

**The per-cell tools pay for their inputs on every call.** ``tools/campaign_holdout.py``,
``tools/campaign_sizing.py null``, ``tools/campaign_montecarlo.py``, ``tools/campaign_exits.py``,
``tools/campaign_walkforward.py`` and ``tools/campaign_propaccount.py`` each load an archetype's
results database whole and prepare their bars again, the null once per configuration, so over a
campaign of thousands of cells the loading costs more than the reads. This loads the rows of the
variant set ``--variants`` names once per archetype, re-runs each shortlisted configuration once
on the bars it was swept on, and hands that one log to every read.

**The reads are those tools' own functions**, given what their command lines give them for one
arm, root, resolution and stratum -- ``--variant``, ``--root``, ``--resolution`` and ``--stratum``
-- so a cell read here and the same cell read there agree:

- ``gates``: gate 1, :func:`campaign_report.profile` on the selection window, and gate 2,
  :func:`campaign_holdout.verdict`;
- ``paired``: :func:`campaign_paired.paired` held out, stratum by stratum, over the pairs
  :func:`controls` reads off the arms' names;
- ``null``: :func:`campaign_sizing.shuffled_null` on the held-out shortlist of every arm whose
  base sizes on a confluence count;
- ``gate4``: :func:`campaign_montecarlo.resample_row`, :func:`campaign_exits.measure_row` and
  :func:`campaign_walkforward.run_resolution`, on the cells ``--gate4-strata`` and ``--cells`` name;
- ``prop``: :func:`campaign_propaccount.replay_shortlist` over the four presets, on the cells
  ``--prop-strata`` names.

Every re-run also writes what it reproduced of its stored row, which is read before anything the
logs were re-run for -- :func:`campaign_swept.reconciliation`.

The tables land under ``--out``, one file per archetype, root, resolution and arm, so an
interrupted run resumes where it stopped. **Only this process opens a database**, and only once
the sweep has stopped writing it: ``nqbt.results.connect`` opens a file read-write.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, logsetup, montecarlo, propaccount, splice, stats, sweep
from nqbt.dispersion import MIN_TRADES
from nqbt.instruments import get_instrument
from nqbt.sim.types import InsideBarTrailingParams
from tools import campaign_paired
from tools.campaign_exits import measure_row
from tools.campaign_holdout import (
    HELD_OUT_SUFFIX,
    JOIN_KEYS,
    SELECTION_SUFFIX,
    half,
    pair_windows,
    verdict,
)
from tools.campaign_montecarlo import resample_row
from tools.campaign_null import stored_rows
from tools.campaign_propaccount import DEFAULT_PRESETS, replay_shortlist
from tools.campaign_report import UNFILTERED, load, log_key, profile, rank
from tools.campaign_shortlist import TOP, rebuild
from tools.campaign_sizing import DRAWS, null_row, shuffled_null
from tools.campaign_sweep import ROOTS, Variant, variants_for
from tools.campaign_swept import (
    CELL_KEYS,
    RECONCILED,
    SWEPT_BARS,
    bars_for,
    candidate_bars,
    reconciliation,
    stored_figures,
)
from tools.campaign_walkforward import TEST_SHARE, TRAIN_SHARE, run_resolution

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)

READS = ("gates", "paired", "null", "gate4", "prop")
"""What a run can be asked for. ``gates`` and ``paired`` read stored rows; the rest re-run."""

RERUN_READS = frozenset({"null", "gate4", "prop"})
"""The reads that need a shortlist's logs, and so a re-run."""

CELL = ["root", "resolution", "variant", "stratum"]
"""What one cell is: every read ranks inside one."""

BY = "profit_factor"
"""The selection-window statistic every shortlist is ranked on, as the per-cell tools default."""

TABLES = (
    "gates",
    "paired",
    "rerun",
    "null",
    "permutation",
    "bootstrap",
    "exclusion",
    "walkforward",
    "prop",
)
"""Every table a run can write, each under its own directory of ``--out``."""

ARM_RULE = re.compile(r"^(?P<stem>.+) (?P<rule>[a-z_]+=\S+(?: symmetric| inverted)?)$")
"""An arm's name: the stored variant it re-emits, then the rule it runs, as the sizing arms are named."""

CONTROLS = ("size=fixed", "split=0.5")
"""The rules an arm is read against, first found first: a fixed size, or InsideBarTrailing's half
split -- ``docs/findings/m45-ibt-sizing-preregistration.md``."""

SYMMETRIC = " symmetric"
INVERTED = " inverted"
"""What an arm's rule ends in when it has a twin to be read against: its add-only arm, or the rule
it inverts."""


@dataclasses.dataclass(frozen=True)
class Task:
    """One archetype, root, resolution and arm: the shortlists to re-run and what to read off them.

    ``held`` is every stratum's held-out shortlist, ranked on the selection window as
    :func:`campaign_holdout.held_out` ranks it; ``chosen`` is the selection-window shortlist
    :func:`campaign_walkforward.run_resolution` walks forward, for the strata gate 4 is read on;
    ``stored`` is the held-out rows those shortlists were swept as, which say what bars to run.
    """

    name: str
    root: str
    minutes: int
    arm: str
    held: pd.DataFrame
    chosen: pd.DataFrame
    stored: pd.DataFrame
    reads: frozenset[str]
    gate4_strata: frozenset[str]
    prop_strata: frozenset[str]
    draws: int
    iterations: int
    seed: int

    @property
    def key(self) -> str:
        """What this task's files are called: its root, resolution and arm."""
        return f"{self.root}-{self.minutes}m-{slug(self.arm)}"


def slug(name: str) -> str:
    """``name`` as a file name, every character a path could misread replaced."""
    return re.sub(r"[^A-Za-z0-9=.+-]", "_", name)


def sizes_on_count(arm: Variant) -> bool:
    """Whether ``arm``'s base sizes on a confluence count, which is what gate 3's shuffled null tests."""
    return getattr(arm.base, "quantity_per_confluence", 0) > 0


def controls(arms: list[str]) -> list[tuple[str, str]]:
    """Every (control, treatment) pair the paired read sets against each other.

    An arm named ``<stem> <rule>`` is read against its stem's control, the first of
    :data:`CONTROLS` present, unless it is one or it inverts another rule. One ending in
    :data:`SYMMETRIC` is also read against its add-only twin, and one with an :data:`INVERTED`
    twin against that. An arm with no control beside it is paired with nothing.
    """
    present: set[str] = set(arms)
    pairs: list[tuple[str, str]] = []
    for arm in arms:
        match: re.Match[str] | None = ARM_RULE.match(arm)
        if match is None:
            continue

        stem, rule = match["stem"], match["rule"]
        control: str | None = next(
            (f"{stem} {name}" for name in CONTROLS if f"{stem} {name}" in present), None
        )
        if control is None:
            continue

        if rule not in CONTROLS and not rule.endswith(INVERTED):
            pairs.append((control, arm))

        if rule.endswith(SYMMETRIC) and arm.removesuffix(SYMMETRIC) in present:
            pairs.append((arm.removesuffix(SYMMETRIC), arm))

        if f"{arm}{INVERTED}" in present:
            pairs.append((f"{arm}{INVERTED}", arm))

    return pairs


def arms_for(
    builders: dict[str, Callable[[str], list[Variant]]], name: str, root: str, resolutions: list[int]
) -> dict[str, Variant]:
    """The arms the variant set builds for one archetype and root at any of these resolutions."""
    return {
        arm.name: arm for arm in builders[name](root) if any(arm.runs_at(minutes) for minutes in resolutions)
    }


def gate_rows(name: str, selection: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Gate 1 and gate 2 per cell: the selection window's profitable share, then the held-out test."""
    first: pd.DataFrame = profile(selection, CELL).rename(
        columns=lambda column: column if column in CELL else f"gate1_{column}",
    )
    second: list[pd.DataFrame] = [
        verdict(name, block).assign(variant=str(variant), resolution=int(str(minutes)))
        for (variant, minutes), block in merged.groupby(["variant", "resolution"], sort=True)
    ]
    held: pd.DataFrame = pd.concat(second, ignore_index=True) if second else pd.DataFrame(columns=CELL)

    return first.merge(held.drop(columns="strategy", errors="ignore"), on=CELL, how="outer").assign(
        strategy=name,
    )


def paired_rows(name: str, holdout: pd.DataFrame, arms: list[str]) -> pd.DataFrame:
    """Every pair :func:`controls` names, held out, one verdict row per stratum, root and resolution."""
    rows: list[pd.DataFrame] = []
    for control, treatment in controls(arms):
        left: pd.DataFrame = holdout[holdout["variant"] == control]
        right: pd.DataFrame = holdout[holdout["variant"] == treatment]
        for stratum in sorted(set(left["stratum"]) & set(right["stratum"])):
            table: pd.DataFrame = campaign_paired.verdict(
                campaign_paired.paired(
                    left[left["stratum"] == stratum],
                    right[right["stratum"] == stratum],
                    BY,
                ),
            )
            rows.append(
                table.assign(strategy=name, stratum=stratum, control_arm=control, treatment_arm=treatment)
            )

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def shortlists(
    merged: pd.DataFrame,
    selection: pd.DataFrame,
    gate4_strata: frozenset[str],
    top: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One task's held-out shortlist per stratum, and its selection-window one where gate 4 is read.

    Ranked as :func:`campaign_holdout.held_out` and :func:`campaign_shortlist.shortlist` rank them
    once narrowed to one cell: a row undefined on ``BY`` is dropped rather than ranked.
    """
    held: list[pd.DataFrame] = [
        half(rank(block, top, f"{BY}{SELECTION_SUFFIX}"), HELD_OUT_SUFFIX)
        for _, block in merged.groupby("stratum", sort=True)
    ]
    chosen: list[pd.DataFrame] = [
        rank(block, top, BY)
        for stratum, block in selection.groupby("stratum", sort=True)
        if stratum in gate4_strata
    ]

    return (
        pd.concat(held, ignore_index=True) if held else pd.DataFrame(columns=JOIN_KEYS),
        pd.concat(chosen, ignore_index=True) if chosen else pd.DataFrame(columns=JOIN_KEYS),
    )


def walk_arguments() -> argparse.Namespace:
    """What ``tools/campaign_walkforward.py``'s command line passes by default, on one core."""
    return argparse.Namespace(
        by=BY,
        train_share=TRAIN_SHARE,
        test_share=TEST_SHARE,
        anchored=False,
        warmup_bars=None,
        min_trades=MIN_TRADES,
        n_jobs=1,
    )


@dataclasses.dataclass(frozen=True)
class Rerun:
    """One shortlisted configuration re-run: where it sits in the shortlist, and what the run gave."""

    position: int
    params: archetypes.Params
    summary: dict[str, object]
    log: pd.DataFrame
    data: context.Dataset
    swept: bool


ARCHIVES: dict[str, pd.DataFrame] = {}
"""Each root's archive, loaded once per worker process."""


def archive(root: str) -> pd.DataFrame:
    """The continuous series for ``root``, loaded on first use in this process."""
    if root not in ARCHIVES:
        ARCHIVES[root] = splice.load_continuous(root)

    return ARCHIVES[root]


def reruns(task: Task) -> Iterator[Rerun]:
    """Every shortlisted configuration re-run once, on one prepared dataset for the whole task.

    One dataset serves every stratum, built from the task's shortlists as a combination grid so
    that it holds the union of what they read, as :func:`campaign_shortlist.rerun_group` builds one.
    """
    archetype: archetypes.Archetype = archetypes.get(task.name)
    frame, swept = bars_for(
        candidate_bars(task.stored, archive(task.root)), task.stored, task.held, task.minutes
    )
    rebuilt = [rebuild(row, archetype) for _, row in task.held.iterrows()]
    grid: sweep.Grid = sweep.Grid.of_combinations(rebuilt, archetype=archetype)
    data: context.Dataset = context.prepare(
        frame,
        grid.required_context(),
        bar_minutes=task.minutes,
        price_basis=context.PriceBasis.RAW,
    )
    for position, params in enumerate(rebuilt):
        summary, log = sweep.run_combination(
            data, params, get_instrument(task.root), archetype, keep_trades=True
        )
        if log is None:  # pragma: no cover - keep_trades always returns a log
            msg: str = "run_combination kept no log with keep_trades set"
            raise RuntimeError(msg)

        yield Rerun(position, params, summary, log, data, swept)


def run_task(task: Task) -> dict[str, pd.DataFrame]:
    """Every re-running read one task asks for, as tables keyed by name."""
    measured: dict[str, list[dict[str, object]]] = {name: [] for name in TABLES}
    spreads: list[pd.DataFrame] = []
    logs: dict[str, dict[tuple[int, int], pd.DataFrame]] = {}
    for run in reruns(task):
        row = task.held.iloc[run.position]
        stratum: str = str(row["stratum"])
        measured["rerun"].append(
            {
                **{column: row[column] for column in CELL},
                **stored_figures(row),
                **{field: run.summary[field] for field in RECONCILED},
                SWEPT_BARS: run.swept,
            },
        )
        if "null" in task.reads:
            measured["null"].append(nulled(task, run))

        if "gate4" in task.reads and stratum in task.gate4_strata:
            resampled: tuple[dict[str, object], pd.DataFrame] | None = resample_row(
                row, run.log, task.iterations, task.seed
            )
            if resampled is not None:
                measured["permutation"].append(resampled[0])
                spreads.append(resampled[1])

            measured["exclusion"].append(measure_row(row, run.log, stats.SESSION_CLOSE, require_stored=False))

        if "prop" in task.reads and stratum in task.prop_strata:
            logs.setdefault(stratum, {})[log_key(row)] = run.log

    tables: dict[str, pd.DataFrame] = {name: pd.DataFrame(rows) for name, rows in measured.items() if rows}
    if spreads:
        tables["bootstrap"] = pd.concat(spreads, ignore_index=True)

    if logs:
        tables["prop"] = replayed(task, logs)

    if "gate4" in task.reads and not task.chosen.empty:
        tables["walkforward"] = walked(task)

    return tables


def nulled(task: Task, run: Rerun) -> dict[str, object]:
    """One sizing configuration against its own sizes shuffled, as ``campaign_sizing.py null`` reads it."""
    row = task.held.iloc[run.position]
    if not isinstance(run.params, InsideBarTrailingParams):
        msg: str = f"{task.name}: the shuffled-size null reads InsideBarTrailing's sizes alone"
        raise TypeError(msg)

    result: dict[str, float] = shuffled_null(
        run.data,
        run.params,
        get_instrument(task.root),
        by=BY,
        draws=task.draws,
        seed=task.seed + log_key(row)[1],
    )

    return {
        "root": task.root,
        "variant": task.arm,
        **null_row(log_key(row), row["stratum"], run.params, task.minutes, result, swept=run.swept),
    }


def replayed(task: Task, logs: dict[str, dict[tuple[int, int], pd.DataFrame]]) -> pd.DataFrame:
    """Each prop stratum's held-out shortlist through the four presets ``campaign_propaccount.py`` reads."""
    accounts: list[propaccount.PropAccount] = [propaccount.preset(name) for name in DEFAULT_PRESETS]

    return pd.concat(
        [
            replay_shortlist(task.held[task.held["stratum"] == stratum], by_key, accounts, None)
            for stratum, by_key in sorted(logs.items())
        ],
        ignore_index=True,
    )


def walked(task: Task) -> pd.DataFrame:
    """Each gate-4 stratum's selection-window shortlist walked forward, one verdict row each."""
    return pd.DataFrame(
        [
            {
                "variant": task.arm,
                "stratum": stratum,
                **run_resolution(
                    task.name, block, task.root, task.minutes, archive(task.root), walk_arguments()
                ),
            }
            for stratum, block in task.chosen.groupby("stratum", sort=True)
        ],
    )


def written(out: Path, table: str, name: str, key: str) -> Path:
    """Where one task's table is written."""
    return out / table / name / f"{key}.parquet"


def done_marker(out: Path, name: str, key: str) -> Path:
    """The file that says a task finished, so a resumed run skips it."""
    return out / "done" / name / f"{key}.json"


def save(out: Path, name: str, key: str, tables: dict[str, pd.DataFrame], reads: frozenset[str]) -> None:
    """Write one task's tables, then mark it done: a task interrupted between the two re-runs."""
    for table, frame in tables.items():
        path: Path = written(out, table, name, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)

    marker: Path = done_marker(out, name, key)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(sorted(reads)), encoding="utf-8")


def is_done(out: Path, name: str, key: str, reads: frozenset[str]) -> bool:
    """Whether a task already ran every read asked of it now."""
    marker: Path = done_marker(out, name, key)

    return marker.exists() and reads <= set(json.loads(marker.read_text(encoding="utf-8")))


def extra_cells(path: Path | None) -> pd.DataFrame:
    """The cells ``--cells`` names beyond the strata gate 4 is read on everywhere."""
    if path is None:
        return pd.DataFrame(columns=CELL)

    cells: pd.DataFrame = pd.read_csv(path)
    missing: set[str] = set(CELL) - set(cells.columns)
    if missing:
        msg: str = f"{path} names no {sorted(missing)}; a cell is {CELL}"
        raise SystemExit(msg)

    return cells[CELL].astype({"resolution": int})


def gate4_for(
    extra: pd.DataFrame, root: str, minutes: int, arm: str, strata: frozenset[str]
) -> frozenset[str]:
    """The strata gate 4 is read on for one task: everywhere's, and any cell ``--cells`` adds."""
    named: pd.DataFrame = extra[
        (extra["root"] == root) & (extra["resolution"] == minutes) & (extra["variant"] == arm)
    ]

    return strata | frozenset(str(stratum) for stratum in named["stratum"])


def tasks_for(
    name: str,
    args: argparse.Namespace,
    extra: pd.DataFrame,
    out: Path,
) -> Iterator[Task]:
    """Load one archetype's rows of the variant set once, write the stored-row reads, yield the re-runs."""
    builders: dict[str, Callable[[str], list[Variant]]] = variants_for(args.variants)
    arms: dict[str, dict[str, Variant]] = {
        root: arms_for(builders, name, root, args.resolutions) for root in args.roots
    }
    everything: list[str] = sorted({arm for built in arms.values() for arm in built})
    frame: pd.DataFrame = load(
        name, ["selection", "holdout"], variants=everything, resolutions=args.resolutions
    )
    selection: pd.DataFrame = frame[frame["window"] == "selection"]
    holdout: pd.DataFrame = frame[frame["window"] == "holdout"]
    merged: pd.DataFrame = pair_windows(name, selection, holdout)
    logger.info("%s: %s paired rows over %d arms", name, f"{len(merged):,}", len(everything))
    if merged.empty:
        return

    if "gates" in args.reads:
        save(out, name, "all", {"gates": gate_rows(name, selection, merged)}, frozenset({"gates"}))

    if "paired" in args.reads:
        save(out, name, "paired", {"paired": paired_rows(name, holdout, everything)}, frozenset({"paired"}))

    reads: frozenset[str] = frozenset(args.reads) & RERUN_READS
    if not reads:
        return

    for root in args.roots:
        stored: pd.DataFrame = stored_rows(
            name, root, "holdout", variants=list(arms[root]), resolutions=args.resolutions
        )
        for (minutes, arm), block in merged[merged["root"] == root].groupby(
            ["resolution", "variant"], sort=True
        ):
            gate4_strata: frozenset[str] = gate4_for(
                extra, root, int(minutes), str(arm), frozenset(args.gate4_strata)
            )
            counted: bool = str(arm) in arms[root] and sizes_on_count(arms[root][str(arm)])
            task_reads: frozenset[str] = reads if counted else reads - {"null"}
            key: str = f"{root}-{int(minutes)}m-{slug(str(arm))}"
            if not task_reads or is_done(out, name, key, task_reads):
                continue

            chosen_from: pd.DataFrame = selection[
                (selection["root"] == root)
                & (selection["resolution"] == minutes)
                & (selection["variant"] == arm)
            ]
            held, chosen = shortlists(block, chosen_from, gate4_strata, args.top)
            keys: pd.MultiIndex = pd.MultiIndex.from_frame(held[JOIN_KEYS])
            yield Task(
                name=name,
                root=root,
                minutes=int(minutes),
                arm=str(arm),
                held=held,
                chosen=chosen,
                stored=stored[stored.index.isin(keys)],
                reads=task_reads,
                gate4_strata=gate4_strata,
                prop_strata=frozenset(args.prop_strata),
                draws=args.draws,
                iterations=args.iterations,
                seed=args.seed,
            )


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Every per-cell read of a variant set, in one pass.")
    parser.add_argument("--variants", required=True, help="the variant set the sweep ran, as it names it")
    parser.add_argument("--strategies", nargs="+", default=None, help="default: every one the set covers")
    parser.add_argument("--roots", nargs="+", default=list(ROOTS))
    parser.add_argument("--resolutions", nargs="+", type=int, required=True)
    parser.add_argument("--reads", nargs="+", choices=READS, default=list(READS))
    parser.add_argument("--gate4-strata", nargs="+", default=[UNFILTERED])
    parser.add_argument("--prop-strata", nargs="+", default=[UNFILTERED])
    parser.add_argument("--cells", type=Path, default=None, help="a csv of further cells gate 4 is read on")
    parser.add_argument("--top", type=int, default=TOP)
    parser.add_argument("--draws", type=int, default=DRAWS)
    parser.add_argument("--iterations", type=int, default=montecarlo.DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, required=True, help="where the tables are written")
    args = parser.parse_args(argv[1:])

    extra: pd.DataFrame = extra_cells(args.cells)
    strategies: list[str] = args.strategies or list(variants_for(args.variants))
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.n_jobs) as pool:
        for name in strategies:
            running: dict[concurrent.futures.Future[dict[str, pd.DataFrame]], Task] = {
                pool.submit(run_task, task): task for task in tasks_for(name, args, extra, args.out)
            }
            logger.info("%s: %d tasks to re-run", name, len(running))
            for finished, future in enumerate(concurrent.futures.as_completed(running), start=1):
                task: Task = running[future]
                save(args.out, name, task.key, future.result(), task.reads)
                if finished % max(1, math.ceil(len(running) / 20)) == 0 or finished == len(running):
                    logger.info("  %s: %d of %d tasks done", name, finished, len(running))

    rerun: list[Path] = sorted((args.out / "rerun").glob("*/*.parquet"))
    if rerun:
        table: pd.DataFrame = pd.concat([pd.read_parquet(path) for path in rerun], ignore_index=True)
        logger.info("what the re-runs reproduced of their stored rows:\n%s", reconciliation(table, CELL_KEYS))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
