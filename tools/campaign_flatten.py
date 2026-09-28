"""Re-run a candidate at several ``ExitOnSessionCloseSeconds`` and say what the timing is worth.

    ./.venv/Scripts/python.exe tools/campaign_flatten.py --strategy InsideBarTrailing \
        --root MNQ NQ --stratum phase=MIDDAY --variant trailing --resolution 1 2 5 10 15

``tools/README.md`` § "campaign_flatten.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, logsetup, sessions, splice
from tools.campaign_holdout import held_out
from tools.campaign_montecarlo import labelled
from tools.campaign_null import stored_rows
from tools.campaign_paired import sign_test
from tools.campaign_report import NET_TO_DRAWDOWN, load, ratio_to_drawdown
from tools.campaign_shortlist import TOP, rerun_group
from tools.campaign_swept import (
    CELL_KEYS,
    HELD_OUT,
    SWEPT_BARS,
    bars_for,
    candidate_bars,
    reconciliation,
    stored_figures,
)

logger = logging.getLogger(__name__)

CUTOFFS = (30, 180, 300, 900)
"""The seconds before the session end to flatten at, the control first.

Why these four: ``tools/README.md`` § "campaign_flatten.py".
"""

CONTROL = sessions.EXIT_ON_CLOSE_SECONDS
"""The rung every other one is read against, which is also the simulation's one default."""

CUTOFF = "exit_on_close_seconds"
"""The column naming which rung a measured row belongs to."""

REPORTED = (
    "trades",
    "profit_factor",
    "net_pnl",
    "max_drawdown",
    "session_close_share",
    "avg_bars_held",
)
"""What each rung reports. The first three are the question; the last three say *how* a rung
changed the book rather than only by how much."""

PAIR_KEYS = ["root", "resolution", "variant", "stratum", "sweep_id", "combo_id"]
"""What identifies the same configuration in two rungs. Exact rather than derived: the arms are
the same stored rows re-run, so nothing about the parameters can differ between them."""

MOVED_ON = "net_pnl"
"""What says a rung actually fired. A cutoff that picks the same bars as the control reproduces
it exactly, so an unchanged net P&L is an arm that never bound rather than one that did
nothing."""


def measure_group(
    block: pd.DataFrame,
    frame: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    minutes: int,
    seconds: int,
) -> list[dict[str, object]]:
    """Re-run every row of one resampled frame at one cutoff."""
    measured: list[dict[str, object]] = []
    for row, summary, _ in rerun_group(
        block,
        frame,
        archetype,
        root,
        minutes,
        context.PriceBasis.RAW,
        seconds,
    ):
        figures: dict[str, object] = {field: summary[field] for field in REPORTED}
        figures[NET_TO_DRAWDOWN] = ratio_to_drawdown(
            float(summary["net_pnl"]),
            float(summary["max_drawdown"]),
        )
        measured.append({**labelled(row), **stored_figures(row), CUTOFF: seconds, **figures})

    return measured


def measure(
    rows: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    cutoffs: tuple[int, ...],
) -> pd.DataFrame:
    """Measure every shortlisted configuration at every cutoff, one row each.

    Every measured row carries what the sweep stored for it, which :func:`reconcile` reads back.
    """
    stored: pd.DataFrame = stored_rows(archetype.name, root, HELD_OUT)
    archive: pd.DataFrame = splice.load_continuous(root)
    candidates: tuple[pd.DataFrame, ...] = candidate_bars(stored, archive)

    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        frame: pd.DataFrame
        swept: bool
        frame, swept = bars_for(candidates, stored, block, int(minutes))
        for seconds in cutoffs:
            at_cutoff: list[dict[str, object]] = measure_group(
                block,
                frame,
                archetype,
                root,
                int(minutes),
                seconds,
            )
            report_group(root, int(minutes), seconds, at_cutoff)
            measured.extend({**result, SWEPT_BARS: swept} for result in at_cutoff)

    return pd.DataFrame(measured)


def report_group(root: str, minutes: int, seconds: int, measured: list[dict[str, object]]) -> None:
    """Log one line per (root, resolution, cutoff), so a run that binds nothing is visible while it runs."""
    frame: pd.DataFrame = pd.DataFrame(measured)
    logger.info(
        "  %-4s %2dm  flat %3ds  %2d configurations  median PF %.3f  close share %.3f",
        root,
        minutes,
        seconds,
        len(frame),
        frame["profit_factor"].median(),
        frame["session_close_share"].median(),
    )


def reconcile(table: pd.DataFrame) -> pd.DataFrame:
    """Measure, per root x resolution, how much of the control rung reproduced its stored row.

    Read it before the ladder: a cell reproducing nothing is a cell whose *levels* belong to
    this run, while the differences between its rungs still belong to the cutoff.
    """
    return reconciliation(table[table[CUTOFF] == CONTROL], CELL_KEYS)


def rung(table: pd.DataFrame, seconds: int, by: str) -> pd.DataFrame:
    """Compare one cutoff against the control, per root x resolution.

    **Never pooled across resolutions**, because the cutoff is a duration and a bar is not: the
    same 180 seconds is three whole bars at one resolution and none at another.
    """
    control: pd.DataFrame = table[table[CUTOFF] == CONTROL].set_index(PAIR_KEYS)
    treatment: pd.DataFrame = table[table[CUTOFF] == seconds].set_index(PAIR_KEYS)
    if control.empty or treatment.empty:
        return pd.DataFrame()

    joined: pd.DataFrame = control.join(treatment, how="inner", lsuffix="_control", rsuffix="")
    joined["delta"] = joined[by] - joined[f"{by}_control"]
    joined["moved"] = joined[MOVED_ON] != joined[f"{MOVED_ON}_control"]

    rows: list[dict[str, object]] = []
    for keys, group in joined.reset_index().groupby(CELL_KEYS, dropna=False, observed=True):
        improved: int = int((group["delta"] > 0.0).sum())
        rows.append(
            {
                CUTOFF: seconds,
                **dict(zip(CELL_KEYS, keys, strict=True)),
                "pairs": len(group),
                "moved": float(group["moved"].mean()),
                "control": group[f"{by}_control"].median(),
                "treatment": group[by].median(),
                "delta": group["delta"].median(),
                "improved": improved,
                "p": sign_test(improved, len(group)),
                "close_share": group["session_close_share"].median(),
                "close_share_delta": float(
                    (group["session_close_share"] - group["session_close_share_control"]).median(),
                ),
                "net_delta": float((group["net_pnl"] - group["net_pnl_control"]).median()),
            },
        )

    return pd.DataFrame(rows)


def ladder(table: pd.DataFrame, by: str) -> pd.DataFrame:
    """Stack every rung above the control."""
    stacked: list[pd.DataFrame] = [
        rung(table, int(seconds), by) for seconds in sorted(table[CUTOFF].unique()) if seconds != CONTROL
    ]
    live: list[pd.DataFrame] = [t for t in stacked if not t.empty]
    if not live:
        msg: str = f"nothing to pair against the {CONTROL}s control; --seconds gave only one rung"
        raise SystemExit(msg)

    return pd.concat(live, ignore_index=True)


COLUMNS = [
    CUTOFF,
    "root",
    "resolution",
    "pairs",
    "moved",
    "control",
    "treatment",
    "delta",
    "improved",
    "p",
    "close_share",
    "close_share_delta",
    "net_delta",
]
"""What is printed, in reading order: the rung, whether it fired, and what it was worth."""


def resolutions_for(
    name: str,
    root: str,
    stratum: str | None,
    variant: str | None,
) -> list[int]:
    """List every bar size the stored cell holds, which is what a shortlist has to be taken inside.

    A shortlist pooled across resolutions would rank bar size as well as parameters, and bar
    size is the largest lever in the campaign -- ``docs/roadmap.md`` §M28.14.
    """
    frame: pd.DataFrame = load(name, [HELD_OUT])
    frame = frame[frame["root"] == root]
    if stratum is not None:
        frame = frame[frame["stratum"] == stratum]

    if variant is not None:
        frame = frame[frame["variant"] == variant]

    return sorted(int(minutes) for minutes in frame["resolution"].unique())


def shortlisted(args: argparse.Namespace, name: str, root: str) -> pd.DataFrame:
    """Stack one held-out shortlist per bar size."""
    wanted: list[int] = args.resolution or resolutions_for(name, root, args.stratum, args.variant)
    if not wanted:
        msg: str = (
            f"{name} on {root}: no stored {HELD_OUT} rows for stratum {args.stratum}, variant {args.variant}"
        )
        raise SystemExit(msg)

    return pd.concat(
        [held_out(name, root, args.by, args.top, args.stratum, minutes, args.variant) for minutes in wanted],
        ignore_index=True,
    )


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading."""
    logger.info("")
    logger.info("--- %s ---", title)
    with pd.option_context("display.width", 240, "display.max_columns", 40):
        for line in frame.to_string(index=False, float_format=lambda v: f"{v:.3f}").splitlines():
            logger.info("%s", line)


def cell(args: argparse.Namespace, archetype: archetypes.Archetype, root: str) -> pd.DataFrame:
    """Measure one root's held-out shortlists at every cutoff."""
    rows: pd.DataFrame = shortlisted(args, archetype.name, root)
    logger.info("")
    logger.info(
        "%s on %s, stratum %s: %d configurations the selection window ranked highest on %s",
        archetype.name,
        root,
        args.stratum or "any",
        len(rows),
        args.by,
    )

    return measure(rows, archetype, root, tuple(args.seconds))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Re-run a candidate at several flatten cutoffs.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", nargs="+", default=["MNQ"])
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", nargs="+", type=int, default=None, help="which bar sizes")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to measure")
    parser.add_argument(
        "--seconds",
        nargs="+",
        type=int,
        default=list(CUTOFFS),
        help="the flatten cutoffs to run; the control rung has to be among them",
    )
    parser.add_argument("--out", default=None, help="write every measured row to this CSV")
    args = parser.parse_args(argv[1:])
    if CONTROL not in args.seconds:
        msg: str = f"--seconds has to include the control rung {CONTROL}, got {args.seconds}"
        raise SystemExit(msg)

    archetype: archetypes.Archetype = archetypes.get(args.strategy)
    table: pd.DataFrame = pd.concat(
        [cell(args, archetype, root) for root in args.root],
        ignore_index=True,
    )
    if args.out is not None:
        table.to_csv(args.out, index=False)

    show(f"the {CONTROL}s control against what the sweep stored for it", reconcile(table))
    show(f"each flatten cutoff against {CONTROL}s, on {args.by}", ladder(table, args.by)[COLUMNS])

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
