"""Resample a campaign shortlist's trade sequences, to size the luck in their equity paths.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar
    ./.venv/Scripts/python.exe tools/campaign_montecarlo.py --strategy InsideBar

:func:`nqbt.montecarlo.permutation_test` reorders the same trades, which moves only the path
statistics and answers *was this drawdown the ordering's doing*.
:func:`nqbt.montecarlo.bootstrap` resamples them with replacement, which moves the values too
and answers *how wide is the uncertainty around this figure*. §M27 asked neither, and an 87% win
rate against a 5:1 loss size is exactly the shape a bootstrap exists to size --
``docs/roadmap.md`` §M27.6.

**This is not the matched null and does not replace it.** Both tests take the entries as given,
so neither can tell "worse than random" from "no better than random"; that is
``tools/campaign_null.py``'s question, and a figure quoted from here without it is half an
argument. `nqbt/randomentry.py` drawing 200 samples per comparison makes it look like the same
machinery and it is not -- it replaces the entry and holds the ordering.

Reads the logs ``tools/campaign_shortlist.py`` stored, so run that first; a row with no log is
named and skipped rather than silently dropped.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_shortlist import TOP, load_trades, shortlist
from tools.campaign_sweep import db_path

from nqbt import logsetup, montecarlo

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray

logger = logging.getLogger(__name__)

STATISTICS = ("net_pnl", "profit_factor", "max_drawdown")
"""What the bootstrap reports percentiles for. Profit factor and drawdown are §M27's Gate 4 read
together; net P&L is there because ``share_below_zero`` on it is the blunt question."""

PERMUTED = "max_drawdown"
"""What the permutation test asks about. Reordering cannot move a value statistic, and
:func:`nqbt.montecarlo.permutation_test` refuses one rather than returning a vacuous pass."""

LABEL_COLUMNS = ["root", "resolution", "variant", "stratum", "window", "sweep_id", "combo_id"]
"""What names a configuration in the output. The same tags the other campaign tools print, so
two reports of one shortlist can be read side by side."""


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The tag columns that say which stored configuration a result row belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def resample_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    path: Path,
    iterations: int,
    seed: int,
) -> tuple[dict[str, object], pd.DataFrame] | None:
    """One configuration's permutation row and bootstrap table, or ``None`` with no log."""
    log: pd.DataFrame = load_trades(int(row["sweep_id"]), int(row["combo_id"]), path)
    if log.empty:
        logger.warning(
            "  sweep %-4d combo %-6d has no stored log; run tools/campaign_shortlist.py first",
            int(row["sweep_id"]),
            int(row["combo_id"]),
        )

        return None

    pnl: FloatArray = montecarlo.trade_pnl(log)
    if pnl.size < montecarlo.MIN_RESAMPLE_TRADES:
        logger.warning(
            "  sweep %-4d combo %-6d has %d trades; nothing to resample",
            int(row["sweep_id"]),
            int(row["combo_id"]),
            pnl.size,
        )

        return None

    permutation: montecarlo.PermutationResult = montecarlo.permutation_test(
        pnl,
        PERMUTED,
        iterations=iterations,
        seed=seed,
    )
    spread: pd.DataFrame = montecarlo.bootstrap(pnl, STATISTICS, iterations=iterations, seed=seed)

    return {**labelled(row), **permutation.as_dict()}, spread.assign(**labelled(row))


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Permutation and bootstrap over a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["holdout"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to resample")
    parser.add_argument("--iterations", type=int, default=montecarlo.DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = shortlist(
        args.strategy,
        args.root,
        args.window,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
    )
    logger.info(
        "%s on %s: %d configurations ranked on %s by %s, %s resamples each",
        args.strategy,
        args.root,
        len(rows),
        "+".join(args.window),
        args.by,
        f"{args.iterations:,}",
    )

    path: Path = db_path(args.strategy)
    resampled: list[tuple[dict[str, object], pd.DataFrame]] = [
        result
        for result in (resample_row(row, path, args.iterations, args.seed) for _, row in rows.iterrows())
        if result is not None
    ]
    if not resampled:
        logger.warning("no stored trade logs for this shortlist; nothing to resample")

        return 1

    show(
        f"{args.strategy} {args.root} -- {PERMUTED} against the same trades reordered",
        pd.DataFrame([permutation for permutation, _ in resampled]),
    )
    show(
        f"{args.strategy} {args.root} -- bootstrap percentiles beside the observed figure",
        pd.concat([spread for _, spread in resampled], ignore_index=True),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
