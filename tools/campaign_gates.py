r"""Every per-cell read of a swept variant set, over every cell, from one load per archetype.

    uv run tools/campaign_gates.py --variants ibt-sizing --resolutions 5 \
        --out <dir> --n-jobs 6
    uv run tools/campaign_gates.py --variants ibt-sizing --resolutions 5 \
        --out <dir> --reads gate4 --cells <csv of strategy, root, resolution, variant and stratum>

The reads are the per-cell tools' own functions, and a run reads only what ``--out`` is missing.
Only this process opens a database, and only once the sweep has stopped writing it --
``tools/README.md`` § "campaign_gates.py".
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

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, logsetup, montecarlo, propaccount, splice, stats
from nqbt.dispersion import MIN_TRADES
from nqbt.instruments import get_instrument
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
from tools.campaign_shortlist import TOP, prepared, run_logged
from tools.campaign_sizing import DRAWS, null_row, shuffled_null
from tools.campaign_sweep import ROOTS, VARIANT_SETS, Variant, variants_for
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

RERUN = "rerun"
"""The table every re-run writes a row to, whichever read it was re-run for."""

TABLES: dict[str, str] = {
    RERUN: RERUN,
    "null": "null",
    "permutation": "gate4",
    "bootstrap": "gate4",
    "exclusion": "gate4",
    "walkforward": "gate4",
    "prop": "prop",
}
"""Every table a task writes, and the read whose strata it holds rows for."""

SETTINGS = ("variants", "draws", "iterations", "seed")
"""What every table under one ``--out`` is read at."""

CELL = ["root", "resolution", "variant", "stratum"]
"""What one cell is: every read ranks inside one."""

NAMED_CELL = ["strategy", *CELL]
"""What ``--cells`` names, since two archetypes can share an arm's name."""

STRATEGY = "strategy"
"""The column naming the archetype a re-run row belongs to."""

BY = "profit_factor"
"""The selection-window statistic every shortlist is ranked on, as the per-cell tools default."""

ARM_RULE = re.compile(r"^(?P<stem>.+) (?P<rule>[a-z_]+=\S+(?: symmetric| inverted)?)$")
"""An arm's name: the stored variant it re-emits, then the rule it runs, as the sizing arms are named."""

CONTROLS = ("size=fixed", "split=0.5", "structure=off")
"""The rules an arm is read against, first found first: a fixed size, InsideBarTrailing's half
split -- ``docs/findings/m45-ibt-sizing-preregistration.md`` -- or its runner trailing the
high-water mark rather than structure."""

SYMMETRIC = " symmetric"
INVERTED = " inverted"
"""What an arm's rule ends in when it has a twin to be read against: its add-only arm, or the rule
it inverts."""


@dataclasses.dataclass(frozen=True)
class Task:
    """One archetype, root, resolution and arm: the shortlists to re-run and what to read off them.

    ``held`` is the held-out shortlist of every stratum a read is run on, ranked on the selection
    window as :func:`campaign_holdout.held_out` ranks it; ``chosen`` is the selection-window
    shortlist :func:`campaign_walkforward.run_resolution` walks forward, for the strata gate 4 is
    read on; ``stored`` is the held-out rows those shortlists were swept as, which say what bars
    to run; ``strata`` is, per read and for :data:`RERUN`, the strata this task writes.
    """

    name: str
    root: str
    minutes: int
    arm: str
    held: pd.DataFrame
    chosen: pd.DataFrame
    stored: pd.DataFrame
    strata: dict[str, frozenset[str]]
    draws: int
    iterations: int
    seed: int

    @property
    def key(self) -> str:
        """What this task's files are called."""
        return task_key(self.root, self.minutes, self.arm)

    def reads(self, read: str, stratum: str) -> bool:
        """Return whether this task writes ``read`` for ``stratum``."""
        return stratum in self.strata.get(read, frozenset())


def slug(name: str) -> str:
    """Turn ``name`` into a file name, every character a path could misread replaced."""
    return re.sub(r"[^A-Za-z0-9=.+-]", "_", name)


def task_key(root: str, minutes: int, arm: str) -> str:
    """Return what one task's files are called: its root, resolution and arm."""
    return f"{root}-{minutes}m-{slug(arm)}"


def refuse_clashes(arms: list[str]) -> None:
    """Refuse two arms whose file names a case-blind file system would take for one."""
    seen: dict[str, str] = {}
    for arm in arms:
        other: str = seen.setdefault(slug(arm).casefold(), arm)
        if other != arm:
            msg: str = f"{other!r} and {arm!r} would be written to the same file"
            raise SystemExit(msg)


def sizes_on_count(arm: Variant) -> bool:
    """Return whether ``arm``'s base sizes on a confluence count, the thing gate 3's shuffled null tests."""
    return getattr(arm.base, "quantity_per_confluence", 0) > 0


def controls(arms: list[str]) -> list[tuple[str, str]]:
    """List every (control, treatment) pair the paired read sets against each other.

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
) -> dict[tuple[str, int], Variant]:
    """Return the arms the variant set builds for one archetype and root, by name and resolution."""
    return {
        (arm.name, minutes): arm
        for arm in builders[name](root)
        for minutes in resolutions
        if arm.runs_at(minutes)
    }


def gate_rows(name: str, selection: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """Read gate 1 and gate 2 per cell: the selection window's profitable share, then the held-out test."""
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
    """Read every pair :func:`controls` names, held out, one verdict row per stratum, root and resolution."""
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
    """Return one task's held-out shortlist per stratum, and its selection-window one where gate 4 is read.

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
    """Return what ``tools/campaign_walkforward.py``'s command line passes by default, on one core."""
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
    """Return the continuous series for ``root``, loaded on first use in this process."""
    if root not in ARCHIVES:
        ARCHIVES[root] = splice.load_continuous(root)

    return ARCHIVES[root]


def reruns(task: Task) -> Iterator[Rerun]:
    """Re-run every configuration ``task.held`` holds once, on one prepared dataset for the task.

    The archive is cut back at the newest bar those rows were swept on.
    """
    archetype: archetypes.Archetype = archetypes.get(task.name)
    frame, swept = bars_for(
        candidate_bars(task.stored, archive(task.root)), task.stored, task.held, task.minutes
    )
    rebuilt, data = prepared(task.held, frame, archetype, task.minutes, context.PriceBasis.RAW)
    for position, params in enumerate(rebuilt):
        summary, log = run_logged(data, params, task.root, archetype)
        yield Rerun(position, params, summary, log, data, swept)


def run_task(task: Task) -> dict[str, pd.DataFrame]:
    """Run every re-running read one task asks for, as tables keyed by name."""
    measured: dict[str, list[dict[str, object]]] = {table: [] for table in TABLES}
    spreads: list[pd.DataFrame] = []
    logs: dict[str, dict[tuple[int, int], pd.DataFrame]] = {}
    for run in reruns(task):
        row = task.held.iloc[run.position]
        stratum: str = str(row["stratum"])
        if task.reads(RERUN, stratum):
            measured[RERUN].append(
                {
                    STRATEGY: task.name,
                    **{column: row[column] for column in CELL},
                    **stored_figures(row),
                    **{field: run.summary[field] for field in RECONCILED},
                    SWEPT_BARS: run.swept,
                },
            )

        if task.reads("null", stratum):
            measured["null"].append(nulled(task, run))

        # ``campaign_exits.measure`` skips a configuration with no trades, so its table has no row for one.
        if task.reads("gate4", stratum) and not run.log.empty:
            resampled: tuple[dict[str, object], pd.DataFrame] | None = resample_row(
                row, run.log, task.iterations, task.seed
            )
            if resampled is not None:
                measured["permutation"].append(resampled[0])
                spreads.append(resampled[1])

            measured["exclusion"].append(measure_row(row, run.log, stats.SESSION_CLOSE, require_stored=False))

        if task.reads("prop", stratum):
            logs.setdefault(stratum, {})[log_key(row)] = run.log

    tables: dict[str, pd.DataFrame] = {name: pd.DataFrame(rows) for name, rows in measured.items() if rows}
    if spreads:
        tables["bootstrap"] = pd.concat(spreads, ignore_index=True)

    if logs:
        tables["prop"] = replayed(task, logs)

    if not task.chosen.empty:
        tables["walkforward"] = walked(task)

    return tables


def nulled(task: Task, run: Rerun) -> dict[str, object]:
    """Test one sizing configuration against its sizes shuffled, as ``campaign_sizing.py null`` reads it."""
    row = task.held.iloc[run.position]
    result: dict[str, float] = shuffled_null(
        run.data,
        run.params,
        get_instrument(task.root),
        by=BY,
        draws=task.draws,
        seed=task.seed + log_key(row)[1],
        archetype=archetypes.get(task.name),
    )

    return {
        "root": task.root,
        "variant": task.arm,
        **null_row(log_key(row), row["stratum"], run.params, task.minutes, result, swept=run.swept),
    }


def replayed(task: Task, logs: dict[str, dict[tuple[int, int], pd.DataFrame]]) -> pd.DataFrame:
    """Replay each prop stratum's held-out shortlist through ``campaign_propaccount.py``'s four presets."""
    accounts: list[propaccount.PropAccount] = [propaccount.preset(name) for name in DEFAULT_PRESETS]

    return pd.concat(
        [
            replay_shortlist(task.held[task.held["stratum"] == stratum], by_key, accounts, None)
            for stratum, by_key in sorted(logs.items())
        ],
        ignore_index=True,
    )


def walked(task: Task) -> pd.DataFrame:
    """Walk each gate-4 stratum's selection-window shortlist forward, one verdict row each."""
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
    """Return where one task's table is written."""
    return out / table / name / f"{key}.parquet"


def done_marker(out: Path, name: str, key: str) -> Path:
    """Return the file recording which strata each read has written for one task."""
    return out / "done" / name / f"{key}.json"


def write_whole(path: Path, write: Callable[[Path], object]) -> None:
    """Write ``path`` through ``write`` to a file beside it, renamed over it once whole.

    A run killed mid-write leaves the old file rather than half of a new one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path = path.with_name(path.name + ".tmp")
    write(temp)
    temp.replace(path)


def write_table(path: Path, frame: pd.DataFrame) -> None:
    """Write ``frame`` to ``path`` whole or not at all."""
    write_whole(path, lambda temp: frame.to_parquet(temp, index=False))


def write_json(path: Path, value: object) -> None:
    """Write ``value`` to ``path`` as JSON, whole or not at all."""
    write_whole(path, lambda temp: temp.write_text(json.dumps(value), encoding="utf-8"))


def recorded(out: Path, name: str, key: str) -> dict[str, frozenset[str]]:
    """Return the strata each read has written for one task, as earlier runs recorded them."""
    marker: Path = done_marker(out, name, key)
    if not marker.exists():
        return {}

    return {
        read: frozenset(strata) for read, strata in json.loads(marker.read_text(encoding="utf-8")).items()
    }


def replace_strata(path: Path, frame: pd.DataFrame | None, strata: frozenset[str]) -> None:
    """Write ``frame`` to ``path`` in place of the rows it holds for ``strata``, keeping the rest."""
    parts: list[pd.DataFrame] = [] if frame is None else [frame]
    if path.exists():
        existing: pd.DataFrame = pd.read_parquet(path)
        parts.insert(0, existing[~existing["stratum"].isin(strata)])

    kept: list[pd.DataFrame] = [part for part in parts if not part.empty]
    if not kept:
        path.unlink(missing_ok=True)

        return

    write_table(path, pd.concat(kept, ignore_index=True))


def save(
    out: Path,
    name: str,
    key: str,
    tables: dict[str, pd.DataFrame],
    strata: dict[str, frozenset[str]],
) -> None:
    """Write one task's tables over the strata it read, then add those strata to what it records.

    A task's rows for any other stratum are kept, so one read over several runs adds to its files,
    and one interrupted between the two is read again and replaces what it wrote.
    """
    for table, read in TABLES.items():
        covered: frozenset[str] = strata.get(read, frozenset())
        if not covered:
            continue

        replace_strata(written(out, table, name, key), tables.get(table), covered)

    done: dict[str, frozenset[str]] = recorded(out, name, key)
    merged: dict[str, list[str]] = {
        read: sorted(done.get(read, frozenset()) | strata.get(read, frozenset()))
        for read in sorted({*done, *strata})
    }
    write_json(done_marker(out, name, key), merged)


def remaining(asked: dict[str, frozenset[str]], done: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Return what is left of each read once earlier runs' strata are taken off, and nothing if none is.

    Every stratum left is re-run, and :data:`RERUN` names those whose re-run is not yet written.
    """
    left: dict[str, frozenset[str]] = {
        read: strata - done.get(read, frozenset()) for read, strata in asked.items()
    }
    rerun: frozenset[str] = frozenset[str]().union(*left.values())
    if not rerun:
        return {}

    return {**left, RERUN: rerun - done.get(RERUN, frozenset())}


def asked_of(
    reads: frozenset[str],
    present: frozenset[str],
    gate4: frozenset[str],
    prop: frozenset[str],
    *,
    counted: bool,
) -> dict[str, frozenset[str]]:
    """Return the strata each re-running read is asked for on one arm, of the strata it has rows in."""
    return {
        "null": present if "null" in reads and counted else frozenset(),
        "gate4": present & gate4 if "gate4" in reads else frozenset(),
        "prop": present & prop if "prop" in reads else frozenset(),
    }


def extra_cells(path: Path | None) -> pd.DataFrame:
    """Return the cells ``--cells`` names beyond the strata gate 4 is read on everywhere."""
    if path is None:
        return pd.DataFrame(columns=NAMED_CELL)

    cells: pd.DataFrame = pd.read_csv(path)
    missing: set[str] = set(NAMED_CELL) - set(cells.columns)
    if missing:
        msg: str = f"{path} names no {sorted(missing)}; a cell is {NAMED_CELL}"
        raise SystemExit(msg)

    return cells[NAMED_CELL].astype({"resolution": int})


def gate4_for(extra: pd.DataFrame, task: tuple[str, str, int, str], strata: frozenset[str]) -> frozenset[str]:
    """List the strata gate 4 is read on for one archetype, root, resolution and arm, ``--cells`` included."""
    name, root, minutes, arm = task
    named: pd.DataFrame = extra[
        (extra["strategy"] == name)
        & (extra["root"] == root)
        & (extra["resolution"] == minutes)
        & (extra["variant"] == arm)
    ]

    return strata | frozenset(str(stratum) for stratum in named["stratum"])


def save_by_cell(out: Path, table: str, name: str, frame: pd.DataFrame) -> None:
    """Write one stored-row read, a file per root and resolution, so a run over others keeps it."""
    if frame.empty:
        return

    for (root, minutes), block in frame.groupby(["root", "resolution"], sort=True):
        write_table(written(out, table, name, f"{root}-{int(str(minutes))}m"), block)


def settle(out: Path, args: argparse.Namespace) -> None:
    """Record the settings ``out``'s tables are read at, refusing a run that asks for others there."""
    asked: dict[str, object] = {setting: getattr(args, setting) for setting in SETTINGS}
    path: Path = out / "settings.json"
    if not path.exists():
        write_json(path, asked)

        return

    held = json.loads(path.read_text(encoding="utf-8"))
    if held != asked:
        msg: str = f"{out} holds tables read at {held}; write a run at {asked} to another --out"
        raise SystemExit(msg)


def tasks_for(
    name: str,
    args: argparse.Namespace,
    extra: pd.DataFrame,
    out: Path,
) -> Iterator[Task]:
    """Load one archetype's rows of the variant set once, write the stored-row reads, yield the re-runs."""
    builders: dict[str, Callable[[str], list[Variant]]] = variants_for(args.variants)
    arms: dict[str, dict[tuple[str, int], Variant]] = {
        root: arms_for(builders, name, root, args.resolutions) for root in args.roots
    }
    everything: list[str] = sorted({arm for built in arms.values() for arm, _ in built})
    refuse_clashes(everything)
    loaded: pd.DataFrame = load(
        name, ["selection", "holdout"], variants=everything, resolutions=args.resolutions
    )
    frame: pd.DataFrame = loaded[loaded["root"].isin(args.roots)]
    selection: pd.DataFrame = frame[frame["window"] == "selection"]
    holdout: pd.DataFrame = frame[frame["window"] == "holdout"]
    merged: pd.DataFrame = pair_windows(name, selection, holdout)
    logger.info("%s: %s paired rows over %d arms", name, f"{len(merged):,}", len(everything))
    if merged.empty:
        return

    if "gates" in args.reads:
        save_by_cell(out, "gates", name, gate_rows(name, selection, merged))

    if "paired" in args.reads:
        save_by_cell(out, "paired", name, paired_rows(name, holdout, everything))

    reads: frozenset[str] = frozenset(args.reads) & RERUN_READS
    if not reads:
        return

    for root in args.roots:
        stored: pd.DataFrame = stored_rows(
            name,
            root,
            "holdout",
            variants=sorted({arm for arm, _ in arms[root]}),
            resolutions=args.resolutions,
        )
        for (resolution, variant), block in merged[merged["root"] == root].groupby(
            ["resolution", "variant"], sort=True
        ):
            minutes, arm = int(resolution), str(variant)
            built: Variant | None = arms[root].get((arm, minutes))
            asked: dict[str, frozenset[str]] = asked_of(
                reads,
                frozenset(str(stratum) for stratum in block["stratum"]),
                gate4_for(extra, (name, root, minutes, arm), frozenset(args.gate4_strata)),
                frozenset(args.prop_strata),
                counted=built is not None and sizes_on_count(built),
            )
            left: dict[str, frozenset[str]] = remaining(
                asked, recorded(out, name, task_key(root, minutes, arm))
            )
            if not left:
                continue

            chosen_from: pd.DataFrame = selection[
                (selection["root"] == root)
                & (selection["resolution"] == minutes)
                & (selection["variant"] == arm)
            ]
            re_run: frozenset[str] = frozenset[str]().union(*left.values())
            held, chosen = shortlists(block[block["stratum"].isin(re_run)], chosen_from, left["gate4"], TOP)
            if held.empty:
                continue

            keys: pd.MultiIndex = pd.MultiIndex.from_frame(held[JOIN_KEYS])
            yield Task(
                name=name,
                root=root,
                minutes=minutes,
                arm=arm,
                held=held,
                chosen=chosen,
                stored=stored[stored.index.isin(keys)],
                strata=left,
                draws=args.draws,
                iterations=args.iterations,
                seed=args.seed,
            )


def saved(future: concurrent.futures.Future[dict[str, pd.DataFrame]], task: Task, out: Path) -> bool:
    """Save one finished task's tables, or log why it could not; whether it saved."""
    try:
        save(out, task.name, task.key, future.result(), task.strata)
    except Exception:
        logger.exception("  %s %s failed; the other tasks carry on", task.name, task.key)
        return False

    return True


def run_strategy(
    pool: concurrent.futures.Executor, name: str, args: argparse.Namespace, extra: pd.DataFrame
) -> list[str]:
    """Run one archetype's tasks on ``pool``, saving each as it finishes; what failed.

    If building or submitting a task fails, the tasks already submitted still run and are saved.
    """
    running: dict[concurrent.futures.Future[dict[str, pd.DataFrame]], Task] = {}
    failed: list[str] = []
    try:
        for task in tasks_for(name, args, extra, args.out):
            running[pool.submit(run_task, task)] = task
    except Exception:
        logger.exception("%s: its remaining tasks could not be started; the others carry on", name)
        failed.append(f"{name}'s remaining tasks")

    logger.info("%s: %d tasks to re-run", name, len(running))
    for finished, future in enumerate(concurrent.futures.as_completed(running), start=1):
        task = running[future]
        if not saved(future, task, args.out):
            failed.append(f"{name} {task.key}")

        if finished % max(1, math.ceil(len(running) / 20)) == 0 or finished == len(running):
            logger.info("  %s: %d of %d tasks done", name, finished, len(running))

    return failed


def report_reruns(out: Path) -> None:
    """Log how many arms reproduced every stored row they re-ran, and each one that did not."""
    paths: list[Path] = sorted((out / RERUN).glob("*/*.parquet"))
    if not paths:
        return

    table: pd.DataFrame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    arms: pd.DataFrame = reconciliation(table, [STRATEGY, *CELL_KEYS, "variant"])
    short: pd.DataFrame = arms[(arms["same_trades"] < arms["rows"]) | (arms["same_net"] < arms["rows"])]
    logger.info("%d of %d arms reproduced every stored row they re-ran", len(arms) - len(short), len(arms))
    if not short.empty:
        logger.warning("these did not, so their levels are this run's:\n%s", short.to_string(index=False))


def main(argv: list[str]) -> int:
    """Run every per-cell read over the variant set and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Every per-cell read of a variant set, in one pass.")
    parser.add_argument(
        "--variants", choices=sorted(VARIANT_SETS), required=True, help="the set the sweep ran"
    )
    parser.add_argument("--strategies", nargs="+", default=None, help="default: every one the set covers")
    parser.add_argument("--roots", nargs="+", default=list(ROOTS))
    parser.add_argument("--resolutions", nargs="+", type=int, required=True)
    parser.add_argument("--reads", nargs="+", choices=READS, default=list(READS))
    parser.add_argument("--gate4-strata", nargs="+", default=[UNFILTERED])
    parser.add_argument("--prop-strata", nargs="+", default=[UNFILTERED])
    parser.add_argument("--cells", type=Path, default=None, help="a csv of further cells gate 4 is read on")
    parser.add_argument("--draws", type=int, default=DRAWS)
    parser.add_argument("--iterations", type=int, default=montecarlo.DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, required=True, help="where the tables are written")
    args = parser.parse_args(argv[1:])
    covered: list[str] = list(variants_for(args.variants))
    unknown: list[str] = sorted(set(args.strategies or ()) - set(covered))
    if unknown:
        parser.error(f"--variants {args.variants} covers {sorted(covered)}, not {unknown}")

    extra: pd.DataFrame = extra_cells(args.cells)
    settle(args.out, args)
    failed: list[str] = []
    for name in args.strategies or covered:
        # A worker that dies breaks its pool for good, so each archetype gets a pool of its own.
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.n_jobs) as pool:
            failed.extend(run_strategy(pool, name, args, extra))

    report_reruns(args.out)
    if failed:
        logger.error(
            "%d failed, and a run over the same --out retries them: %s", len(failed), ", ".join(failed)
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
