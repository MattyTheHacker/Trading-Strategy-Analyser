"""Test whether a shortlist chosen on the selection window survives the held-out one.

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_holdout.py

A sweep table ranks configurations; it cannot say whether the ranking means anything. The
question this answers is the one that decides whether an archetype is worth more work: **does
picking the best 20 on the first 60% of the series beat not picking at all on the last 40%?**
On this project's own data that has come out *below* the median of every configuration --
``docs/roadmap.md`` § "Selecting on one contract is worse than not selecting".

**One row per root and stratum**, because a stratum is its own question and its own sample --
see :data:`GROUP_KEYS`. A stratum the split never ran simply has no row.

Reads what ``tools/campaign_sweep.py --split`` wrote, one database per archetype.
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

from tools.campaign_report import STATISTICS, TAGS, load
from tools.campaign_sweep import VARIANTS

from nqbt import logsetup

logger = logging.getLogger(__name__)

JOIN_KEYS = ["root", "resolution", "variant", "stratum", "combo_id"]
"""What identifies the same configuration in two windows.

``combo_id`` is the position in a deterministic product, and both windows run the same grids in
the same order, so equal ids are equal parameters. The paired columns are checked rather than
trusted -- see :func:`paired`."""

TOP = 20
"""How many the shortlist takes. The roadmap's own held-out test used twenty."""

GROUP_KEYS = ["root", "stratum"]
"""What a shortlist is chosen within. **A stratum is its own held-out test**, never pooled with
the others: pooling lets the selection window pick the stratum as well as the parameters, and
the twenty largest profit factors then come from whichever stratum has the fattest tail rather
than from the one being asked about -- ``docs/roadmap.md`` §M27.4."""


def paired(name: str) -> pd.DataFrame:
    """One row per configuration that cleared the trade floor in **both** windows."""
    selection: pd.DataFrame = load(name, ["selection"])
    holdout: pd.DataFrame = load(name, ["holdout"])
    if selection.empty or holdout.empty:
        return pd.DataFrame()

    parameters: list[str] = [column for column in selection.columns if column not in TAGS and column not in STATISTICS]
    merged: pd.DataFrame = selection.merge(
        holdout,
        on=JOIN_KEYS,
        suffixes=("_sel", "_hold"),
        validate="one_to_one",
    )
    mismatched: pd.DataFrame = merged[[f"{p}_sel" for p in parameters] + [f"{p}_hold" for p in parameters]]
    for parameter in parameters:
        if not mismatched[f"{parameter}_sel"].equals(mismatched[f"{parameter}_hold"]):
            msg: str = f"{name}: {parameter} differs between the windows at the same combo_id"
            raise RuntimeError(msg)
    return merged


def rank_correlation(block: pd.DataFrame) -> float:
    """Spearman between the two windows' profit factors, as Pearson on the ranks.

    Written out because ``Series.corr(method="spearman")`` needs scipy, which is not a
    dependency and must not become one for a report.
    """
    return float(
        block["profit_factor_sel"].rank().corr(block["profit_factor_hold"].rank()),
    )


def verdict(name: str, merged: pd.DataFrame) -> pd.DataFrame:
    """The held-out test, per root and stratum: the shortlist against not shortlisting at all."""
    rows: list[dict[str, object]] = []
    for (root, stratum), block in merged.groupby(GROUP_KEYS):
        top: pd.DataFrame = block.nlargest(TOP, "profit_factor_sel")
        shortlist_pf: float = float(top["profit_factor_hold"].mean())
        unselected_pf: float = float(block["profit_factor_hold"].median())
        rows.append(
            {
                "strategy": name,
                "root": root,
                "stratum": stratum,
                "paired": len(block),
                "sel_top20_pf": top["profit_factor_sel"].mean(),
                "hold_top20_pf": shortlist_pf,
                "hold_all_median_pf": unselected_pf,
                "top20_profitable": int((top["profit_factor_hold"] > 1.0).sum()),
                "hold_top20_net": top["net_pnl_hold"].mean(),
                "rank_corr": rank_correlation(block),
                "passes": shortlist_pf > 1.0 and shortlist_pf > unselected_pf,
            },
        )
    return pd.DataFrame(rows)


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")
        return
    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Held-out test of a --split campaign.")
    parser.add_argument("--strategies", nargs="+", default=list(VARIANTS))
    args = parser.parse_args(argv[1:])

    verdicts: list[pd.DataFrame] = []
    for name in args.strategies:
        merged: pd.DataFrame = paired(name)
        if merged.empty:
            logger.warning("no paired windows for %s; run --split first", name)
            continue
        block: pd.DataFrame = verdict(name, merged)
        verdicts.append(block)
        show(f"{name}: best 20 on the selection window, measured on the holdout", block)

        top: pd.DataFrame = merged.nlargest(TOP, "profit_factor_sel")
        show(
            f"{name}: the shortlist itself, top 5",
            top.head(5)[
                [
                    "root",
                    "stratum",
                    "resolution",
                    "variant",
                    "trades_sel",
                    "profit_factor_sel",
                    "trades_hold",
                    "profit_factor_hold",
                    "net_pnl_hold",
                ]
            ],
        )

    if verdicts:
        logger.info("")
        logger.info("=" * 110)
        show("HELD-OUT VERDICT -- every archetype", pd.concat(verdicts, ignore_index=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
