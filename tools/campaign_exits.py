"""Re-summarise a campaign shortlist with one exit reason's legs removed, and say what survives.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --held-out
    ./.venv/Scripts/python.exe tools/campaign_exits.py --strategy OpeningRange

``tools/campaign_report.py``'s ranked table says what each exit reason was worth. It cannot say
what is left without one, because net P&L is additive and profit factor and drawdown are not --
so "the flatten earned +57,256 against a bracket of −32,458" leaves the question of whether the
rest of the book stands up unasked. This asks it: drop one reason's legs and run
:func:`nqbt.stats.summarise` over what remains -- ``docs/roadmap.md`` §M28.12 and §M28.15.

**It is a decomposition and not a counterfactual.** A leg the clock closed is a leg the stop did
not take, so nothing here supports "remove this half and keep the other" -- the position would
have gone on to some other exit, and these bars do not say which. What it supports is the weaker
and sufficient statement about whether a configuration's result rests on one exit reason.

**Every figure is ``summarise``'s, over subsets**, which is the same discipline a review keeps:
a second definition of a profit factor here would drift from the sweep's silently. The whole-log
column therefore reproduces the stored row exactly, and :func:`verify` refuses a run where it
does not.

**The shortlist is chosen on the selection window and read on the held-out one**, the pair
``tools/campaign_holdout.py``'s :func:`~tools.campaign_holdout.held_out` builds, so nothing is
read from the window that chose it -- ``docs/roadmap.md`` §M28.13.

Reads the logs ``tools/campaign_shortlist.py --held-out`` stored, so run that first; a row with
no log is named and skipped rather than silently dropped.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_holdout import held_out
from tools.campaign_montecarlo import LABEL_COLUMNS
from tools.campaign_report import NET_TO_DRAWDOWN, load_trades, ratio_to_drawdown
from tools.campaign_shortlist import NET_PNL_TOLERANCE, TOP
from tools.campaign_sweep import db_path

from nqbt import logsetup, stats, trades

logger = logging.getLogger(__name__)

REPORTED = ("trades", "profit_factor", "net_pnl", "max_drawdown")
"""Which of :class:`~nqbt.stats.Summary`'s fields each half of the split reports.

Profit factor and net-to-drawdown are §M27's Gate 4 read together, and ``trades`` is here
because a residual book below the trade floor is not a result at all."""

PASS_MARK = 1.0
"""What both the residual profit factor and its net-to-drawdown have to clear.

The same two thresholds ``tools/campaign_holdout.py``'s ``passes`` and ``clears_drawdown`` use,
so a residual read can be compared with the gate the whole book went through."""


def summary_of(log: pd.DataFrame) -> dict[str, float]:
    """:data:`REPORTED` plus net-to-drawdown for one set of legs, zeroed where there are none."""
    summary: stats.Summary = stats.summarise(log)
    figures: dict[str, float] = {field: float(getattr(summary, field)) for field in REPORTED}
    figures[NET_TO_DRAWDOWN] = ratio_to_drawdown(summary.net_pnl, summary.max_drawdown)

    return figures


def split_on(log: pd.DataFrame, reason: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One log's legs that left by ``reason``, and the ones that did not."""
    taken = log["exit_reason"] == reason

    return log[taken], log[~taken]


def verify(row: pd.Series, whole: dict[str, float]) -> None:  # type: ignore[type-arg]  # duckdb's dtypes
    """Refuse a log whose own summary does not reproduce the net P&L its stored row carries.

    A residual read of a log filed against the wrong summary would attribute every figure below
    to a configuration that did not produce it -- the same guard
    ``tools/campaign_shortlist.verify`` puts on the re-run that wrote it.
    """
    stored: float = float(row["net_pnl"])
    if not math.isclose(whole["net_pnl"], stored, rel_tol=NET_PNL_TOLERANCE):
        msg: str = (
            f"sweep {int(row['sweep_id'])} combo {int(row['combo_id'])}: the stored log sums to "
            f"{whole['net_pnl']:.4f}, not the {stored:.4f} its row carries"
        )
        raise RuntimeError(msg)


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The tag columns that say which stored configuration a result row belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def measure_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    log: pd.DataFrame,
    reason: str,
) -> dict[str, object]:
    """One configuration's whole book, the legs one reason took, and what is left without them."""
    whole: dict[str, float] = summary_of(log)
    verify(row, whole)
    removed, residual = split_on(log, reason)
    figures: dict[str, float] = summary_of(residual)
    measured: dict[str, object] = {
        **labelled(row),
        "legs": len(log),
        f"{reason}_legs": len(removed),
        f"{reason}_net": summary_of(removed)["net_pnl"],
        **{f"{field}_whole": whole[field] for field in (*REPORTED, NET_TO_DRAWDOWN)},
        **{f"{field}_rest": figures[field] for field in (*REPORTED, NET_TO_DRAWDOWN)},
        "survives": figures["profit_factor"] > PASS_MARK and figures[NET_TO_DRAWDOWN] > PASS_MARK,
    }
    logger.info(
        "  sweep %-4d combo %-6d  PF %6.3f -> %6.3f   net %12.2f -> %12.2f   n/dd %6.3f -> %6.3f",
        int(row["sweep_id"]),
        int(row["combo_id"]),
        whole["profit_factor"],
        figures["profit_factor"],
        whole["net_pnl"],
        figures["net_pnl"],
        whole[NET_TO_DRAWDOWN],
        figures[NET_TO_DRAWDOWN],
    )

    return measured


def measure(rows: pd.DataFrame, path: Path, reason: str) -> pd.DataFrame:
    """Every shortlisted configuration split on ``reason``, one row each."""
    measured: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        log: pd.DataFrame = load_trades(int(row["sweep_id"]), int(row["combo_id"]), path)
        if log.empty:
            logger.warning(
                "  sweep %-4d combo %-6d has no stored log; run tools/campaign_shortlist.py --held-out first",
                int(row["sweep_id"]),
                int(row["combo_id"]),
            )
            continue

        measured.append(measure_row(row, log, reason))

    return pd.DataFrame(measured)


def survival(table: pd.DataFrame, reason: str) -> list[str]:
    """What the exclusion leaves, as lines rather than a one-row table."""
    if table.empty:
        return ["  (nothing was measured)"]

    profitable_whole: int = int((table["profit_factor_whole"] > PASS_MARK).sum())
    profitable_rest: int = int((table["profit_factor_rest"] > PASS_MARK).sum())
    survives: int = int(table["survives"].sum())

    return [
        f"  profit factor above {PASS_MARK}       {profitable_whole:3d} of {len(table)} whole, "
        f"{profitable_rest:3d} of {len(table)} without {reason}",
        f"  and net-to-drawdown above {PASS_MARK}  {survives:3d} of {len(table)} without {reason}",
        f"  median profit factor          {table['profit_factor_whole'].median():.3f} whole, "
        f"{table['profit_factor_rest'].median():.3f} without {reason}",
        f"  median net P&L                {table['net_pnl_whole'].median():,.2f} whole, "
        f"{table['net_pnl_rest'].median():,.2f} without {reason}",
    ]


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 260, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Re-summarise a shortlist without one exit reason.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--by", default="profit_factor", help="the selection-window statistic that ranks")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to re-summarise")
    parser.add_argument(
        "--reason",
        choices=sorted(trades.EXIT_REASONS.values()),
        default=stats.SESSION_CLOSE,
        help="which exit reason's legs come out",
    )
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = held_out(
        args.strategy,
        args.root,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        args.variant,
    )
    logger.info(
        "%s on %s: %d held-out configurations ranked on selection by %s, without %s",
        args.strategy,
        args.root,
        len(rows),
        args.by,
        args.reason,
    )

    table: pd.DataFrame = measure(rows, db_path(args.strategy), args.reason)
    if table.empty:
        logger.warning("no stored trade logs for this shortlist; nothing to re-summarise")

        return 1

    show(f"{args.strategy} {args.root} -- the whole book and what is left without {args.reason}", table)
    logger.info("")
    logger.info("--- what the exclusion leaves ---")
    for line in survival(table, args.reason):
        logger.info("%s", line)

    logger.info("")
    logger.info("a decomposition, not a counterfactual: those positions would have left some other way")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
