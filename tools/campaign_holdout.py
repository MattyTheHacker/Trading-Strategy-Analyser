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

from tools.campaign_report import NET_TO_DRAWDOWN, load, parameter_columns, rank
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
than from the one being asked about -- ``docs/roadmap.md`` §M27.4.

**Variant is not here and a database holding more than one needs ``--variant``**, because the
same argument applies to it and this does not yet make it -- ``docs/roadmap.md`` §M27.3."""

DEFAULT_BY = "profit_factor"
"""What the shortlist is chosen on unless ``--by`` says otherwise. §M27.4's table was measured
on this one; :data:`~tools.campaign_report.NET_TO_DRAWDOWN` is what §M27.3 ranks on instead."""


def paired(name: str, variant: str | None = None) -> pd.DataFrame:
    """One row per configuration that cleared the trade floor in **both** windows."""
    selection: pd.DataFrame = load(name, ["selection"])
    holdout: pd.DataFrame = load(name, ["holdout"])
    if variant is not None:
        selection = selection[selection["variant"] == variant]
        holdout = holdout[holdout["variant"] == variant]

    if selection.empty or holdout.empty:
        return pd.DataFrame()

    parameters: list[str] = parameter_columns(selection)
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


def verdict(name: str, merged: pd.DataFrame, by: str = DEFAULT_BY) -> pd.DataFrame:
    """The held-out test, per root and stratum: the shortlist against not shortlisting at all.

    ``by`` names the selection-window statistic the shortlist is drawn on. A row it is undefined
    on is not shortlistable and is dropped, so ``shortlisted`` can come back below :data:`TOP`
    and is reported rather than assumed -- :func:`campaign_report.rank`.
    """
    rows: list[dict[str, object]] = []
    for (root, stratum), block in merged.groupby(GROUP_KEYS):
        top: pd.DataFrame = rank(block, TOP, f"{by}_sel")
        shortlist_pf: float = float(top["profit_factor_hold"].mean())
        unselected_pf: float = float(block["profit_factor_hold"].median())
        shortlist_ntd: float = float(top[f"{NET_TO_DRAWDOWN}_hold"].median())
        rows.append(
            {
                "strategy": name,
                "root": root,
                "stratum": stratum,
                "paired": len(block),
                "shortlisted": len(top),
                "sel_top20_pf": top["profit_factor_sel"].mean(),
                "hold_top20_pf": shortlist_pf,
                "hold_all_median_pf": unselected_pf,
                "top20_profitable": int((top["profit_factor_hold"] > 1.0).sum()),
                "hold_top20_net": top["net_pnl_hold"].mean(),
                "hold_top20_ntd": shortlist_ntd,
                "hold_all_median_ntd": block[f"{NET_TO_DRAWDOWN}_hold"].median(),
                "rank_corr": rank_correlation(block),
                "passes": shortlist_pf > 1.0 and shortlist_pf > unselected_pf,
                "clears_drawdown": shortlist_ntd > 1.0,
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
    parser.add_argument("--variant", default=None, help="restrict to one variant of each grid")
    parser.add_argument("--by", default=DEFAULT_BY, help="selection statistic the shortlist ranks on")
    args = parser.parse_args(argv[1:])

    verdicts: list[pd.DataFrame] = []
    for name in args.strategies:
        merged: pd.DataFrame = paired(name, args.variant)
        if merged.empty:
            logger.warning("no paired windows for %s; run --split first", name)
            continue

        block: pd.DataFrame = verdict(name, merged, args.by)
        verdicts.append(block)
        show(f"{name}: best 20 on the selection window by {args.by}, measured on the holdout", block)

        top: pd.DataFrame = rank(merged, TOP, f"{args.by}_sel")
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
                    f"{NET_TO_DRAWDOWN}_hold",
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
