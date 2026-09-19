"""Re-run a candidate at several ``ExitOnSessionCloseSeconds`` and say what the timing is worth.

    ./.venv/Scripts/python.exe tools/campaign_flatten.py --strategy InsideBarTrailing \
        --root MNQ NQ --stratum phase=MIDDAY --variant trailing --resolution 1 2 5 10 15

In a backtest the property is inert: NinjaTrader flattens on the session's last bar whatever the
script sets, which is why :data:`~nqbt.sessions.EXIT_ON_CLOSE_SECONDS` is one default rather
than a per-archetype field -- ``docs/nt8-fidelity.md`` §M22. **Live it is not inert**, so for a
strategy whose P&L is carried by session-close legs the value the C# ships decides trades the
Strategy Analyzer can never show moving. This is the instrument that can: the simulator takes
the cutoff, so the same configurations run at the backtested value and at the live one over the
same bars.

**The pairing is exact.** Each rung re-runs the *same* stored configurations on the *same* bars,
so a pair is one configuration and the only thing differing between its two rows is the cutoff.
``moved`` is what says a rung fired at all -- a cutoff shorter than the last bar selects the
same bars as the control and reproduces it exactly, which above 2-minute bars is most of the
ladder.

**Every row is the held-out pair** ``tools/campaign_holdout.py``'s ``held_out`` builds, so
nothing is read from the window that chose it -- ``docs/roadmap.md`` §M28.13.

**The control rung is reconciled against the stored row and the agreement is reported rather
than required.** The ladder is a within-run comparison -- same configurations, same bars, same
code, one cutoff apart -- so it does not rest on reproducing a figure measured months ago. What
it does rest on is being told when that figure has moved, because the levels are then this run's
rather than the registry's. ``reconcile`` is that number and it is part of the reading.

What it returned, and what it settles about the per-archetype value:
``docs/findings/m41-flatten-timing.md``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_holdout import held_out
from tools.campaign_montecarlo import labelled
from tools.campaign_null import series_moved, stored_for, stored_rows
from tools.campaign_paired import sign_test
from tools.campaign_report import NET_TO_DRAWDOWN, load, ratio_to_drawdown
from tools.campaign_shortlist import NET_PNL_TOLERANCE, TOP, rerun_group, source, swept_series

from nqbt import archetypes, context, logsetup, resample, sessions, splice

logger = logging.getLogger(__name__)

CUTOFFS = (30, 180, 300, 900)
"""The seconds before the session end to flatten at, the control first.

``30`` is what every stored row was swept at and what both stop-market ports set. ``180`` is
what ``InsideBar.cs`` and ``InsideBarTrailing.cs`` set, so it is what a live account does.
``300`` is a whole 5-minute bar, and it is here because 180 cannot be expressed on a 5-minute
series at all: the live flatten falls *inside* the last bar, so the truth sits between those
two rungs rather than on either. ``900`` binds at every resolution the campaign runs, which is
what separates "the live cutoff is too small to see" from "this book does not care when it is
flattened" -- ``docs/findings/m41-flatten-timing.md``.
"""

CONTROL = sessions.EXIT_ON_CLOSE_SECONDS
"""The rung every other one is read against, which is also the simulation's one default."""

HELD_OUT = "holdout"
"""The window ``held_out`` returns rows from, and so the bars every rung has to run on."""

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

CELL_KEYS = ["root", "resolution"]
"""What one reported row pools over.

**Never pooled across resolutions**, because the cutoff is a duration and a bar is not: the
same 180 seconds is three whole bars at one resolution and none at another."""

PAIR_KEYS = ["root", "resolution", "variant", "stratum", "sweep_id", "combo_id"]
"""What identifies the same configuration in two rungs. Exact rather than derived: the arms are
the same stored rows re-run, so nothing about the parameters can differ between them."""

MOVED_ON = "net_pnl"
"""What says a rung actually fired. A cutoff that picks the same bars as the control reproduces
it exactly, so an unchanged net P&L is an arm that never bound rather than one that did
nothing."""

SWEPT_BARS = "swept_bars"
"""Whether a cell ran on the bars its stored rows were swept on, which an archive that gained
history earlier than its tail makes unrecoverable."""

RECONCILED = ("trades", "net_pnl")
"""What the control rung is read back against in the row the sweep stored for it.

**Reported and not required**, which is a deliberate weakening of the guard
``tools/campaign_shortlist.py``'s ``verify`` puts on a stored log. Nothing is filed here
against a stored summary: the ladder pairs two rungs of one run, so a control that no longer
reproduces makes this campaign's levels its own rather than making its differences wrong.
``docs/findings/m41-flatten-timing.md`` § "The stored rows no longer reproduce".
"""


def last_swept(stored: pd.DataFrame, bars: pd.DataFrame) -> pd.Timestamp:
    """The newest bar any of these stored rows was swept on, in the archive's own zone.

    ``save_sweep`` stores the stamp naive, and the spliced series is tz-aware.
    """
    return pd.Timestamp(stored["last_bar"].max()).tz_localize(bars.index.tz)


def on_swept_bars(stored: pd.DataFrame, block: pd.DataFrame, frame: pd.DataFrame) -> bool:
    """Whether every row in ``block`` was swept on exactly the bars ``frame`` holds."""
    references = [stored_for(stored, row) for _, row in block.iterrows()]

    return all(ref is not None and not series_moved(ref, frame) for ref in references)


def bars_for(
    candidates: tuple[pd.DataFrame, ...],
    stored: pd.DataFrame,
    block: pd.DataFrame,
    minutes: int,
) -> tuple[pd.DataFrame, bool]:
    """The held-out frame to run, preferring the one these rows were swept on.

    An archive that only grew at the end is recovered by cutting it back; one that gained
    history earlier moves the 60/40 split and cannot be. Neither is refused -- the ladder pairs
    two rungs of one run -- but which bars a cell ran on is reported beside it.
    """
    frames: list[pd.DataFrame] = [resample.resample(source(bars, HELD_OUT), minutes) for bars in candidates]
    for frame in frames:
        if on_swept_bars(stored, block, frame):
            return frame, True

    return frames[-1], False


def measure_group(
    block: pd.DataFrame,
    frame: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    minutes: int,
    seconds: int,
) -> list[dict[str, object]]:
    """Every row of one resampled frame re-run at one cutoff.

    The bars are :data:`~nqbt.context.PriceBasis.RAW`, which is what ``load_continuous`` returns
    and what the sweep measured them as, so a rule reading an absolute level runs rather than
    being refused -- ``docs/roadmap.md`` § "The build spec's three loose ends".
    """
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
        stored: dict[str, object] = {f"stored_{field}": row[field] for field in RECONCILED}
        measured.append({**labelled(row), **stored, CUTOFF: seconds, **figures})

    return measured


def measure(
    rows: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    cutoffs: tuple[int, ...],
) -> pd.DataFrame:
    """Every shortlisted configuration at every cutoff, one row each.

    Grouped by resolution because the resample is the expensive part every rung shares, and the
    bars each cell runs on are the ones its rows were swept on wherever that survives. Every
    measured row carries what the sweep stored for it, which :func:`reconcile` reads back.
    """
    stored: pd.DataFrame = stored_rows(archetype.name, root, HELD_OUT)
    archive: pd.DataFrame = splice.load_continuous(root)
    candidates: tuple[pd.DataFrame, ...] = (
        swept_series(archive, last_swept(stored, archive)),
        archive,
    )

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
    """One line per (root, resolution, cutoff), so a run that binds nothing is visible while it runs."""
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
    """Per root x resolution, how much of the control rung reproduced its stored row.

    Read it before the ladder: a cell reproducing nothing is a cell whose *levels* belong to
    this run, while the differences between its rungs still belong to the cutoff.
    """
    control: pd.DataFrame = table[table[CUTOFF] == CONTROL]
    rows: list[dict[str, object]] = []
    for keys, group in control.groupby(CELL_KEYS, dropna=False, observed=True):
        same_net: pd.Series[bool] = (group["net_pnl"] - group["stored_net_pnl"]).abs() <= (
            group["stored_net_pnl"].abs() * NET_PNL_TOLERANCE
        )
        rows.append(
            {
                **dict(zip(CELL_KEYS, keys, strict=True)),
                "rows": len(group),
                SWEPT_BARS: bool(group[SWEPT_BARS].all()),
                "same_trades": int((group["trades"] == group["stored_trades"]).sum()),
                "same_net": int(same_net.sum()),
                "net_gap": float((group["net_pnl"] - group["stored_net_pnl"]).abs().max()),
            },
        )

    return pd.DataFrame(rows)


def rung(table: pd.DataFrame, seconds: int, by: str) -> pd.DataFrame:
    """One cutoff against the control, per root x resolution."""
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
    """Every rung above the control, stacked."""
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
    """Every bar size the stored cell holds, which is what a shortlist has to be taken inside.

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
    """One held-out shortlist per bar size, stacked."""
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
    """One root's held-out shortlists, measured at every cutoff."""
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
