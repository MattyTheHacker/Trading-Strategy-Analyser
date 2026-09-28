"""Test whether a shortlist chosen on the selection window survives the held-out one.

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_holdout.py

One row per root and stratum -- ``tools/README.md`` § "campaign_holdout.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup
from tools.campaign_report import NET_TO_DRAWDOWN, load, parameter_columns, rank
from tools.campaign_sweep import VARIANTS

logger = logging.getLogger(__name__)

JOIN_KEYS = ["root", "resolution", "variant", "stratum", "combo_id"]
"""What identifies the same configuration in two windows; the paired columns are checked, not trusted."""

TOP = 20
"""How many the shortlist takes. The roadmap's own held-out test used twenty."""

GROUP_KEYS = ["root", "stratum"]
"""What a shortlist is chosen within: a stratum is its own held-out test -- ``docs/roadmap.md`` §M27.4."""

DEFAULT_BY = "profit_factor"
"""What the shortlist is chosen on unless ``--by`` says otherwise. §M27.4's table was measured
on this one; :data:`~tools.campaign_report.NET_TO_DRAWDOWN` is what §M27.3 ranks on instead."""


def paired(name: str, variant: str | None = None) -> pd.DataFrame:
    """Return one row per configuration that cleared the trade floor in **both** windows."""
    selection: pd.DataFrame = load(name, ["selection"])
    holdout: pd.DataFrame = load(name, ["holdout"])
    if variant is not None:
        selection = selection[selection["variant"] == variant]
        holdout = holdout[holdout["variant"] == variant]

    return pair_windows(name, selection, holdout)


def pair_windows(name: str, selection: pd.DataFrame, holdout: pd.DataFrame) -> pd.DataFrame:
    """Run :func:`paired` over rows already loaded, each window's under its own name."""
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


SELECTION_SUFFIX = "_sel"
"""Which half of a :func:`paired` row the selection window measured."""

HELD_OUT_SUFFIX = "_hold"
"""Which half of a :func:`paired` row :func:`held_out` keeps."""


def held_out(
    name: str,
    root: str,
    by: str = DEFAULT_BY,
    top: int = TOP,
    stratum: str | None = None,
    resolution: int | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """Return the held-out rows of the configurations the selection window ranks highest.

    Shaped like :func:`campaign_report.load`'s rows, so it can stand in for
    :func:`campaign_shortlist.shortlist`.
    """
    return half(ranked_pairs(name, root, by, top, stratum, resolution, variant), HELD_OUT_SUFFIX)


def ranked_pairs(
    name: str,
    root: str,
    by: str = DEFAULT_BY,
    top: int | None = TOP,
    stratum: str | None = None,
    resolution: int | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """Return the :func:`paired` rows the selection window ranks highest on ``by``, both halves kept.

    ``top`` of ``None`` ranks every row.
    """
    merged: pd.DataFrame = paired(name, variant)
    if not merged.empty:
        merged = merged[merged["root"] == root]

    if stratum is not None:
        merged = merged[merged["stratum"] == stratum]

    if resolution is not None:
        merged = merged[merged["resolution"] == resolution]

    if merged.empty:
        msg: str = f"no paired windows for {name} on {root}, stratum {stratum}, variant {variant}"
        raise RuntimeError(msg)

    ranked: pd.DataFrame = rank(merged, len(merged) if top is None else top, f"{by}{SELECTION_SUFFIX}")
    if ranked.empty:
        msg = f"{name} on {root}: every one of {len(merged)} paired rows has no {by}_sel to rank on"
        raise RuntimeError(msg)

    return ranked


def half(merged: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """Return one half of a paired frame, under the unsuffixed names the stored rows carry."""
    renamed: dict[str, str] = {
        column: column.removesuffix(suffix) for column in merged.columns if column.endswith(suffix)
    }

    return merged[[*JOIN_KEYS, *renamed]].rename(columns=renamed).reset_index(drop=True)


def rank_correlation(block: pd.DataFrame) -> float:
    """Compute Spearman between the two windows' profit factors, as Pearson on the ranks.

    Written out because ``Series.corr(method="spearman")`` needs scipy, which is not a
    dependency and must not become one for a report.
    """
    return float(
        block["profit_factor_sel"].rank().corr(block["profit_factor_hold"].rank()),
    )


def verdict(name: str, merged: pd.DataFrame, by: str = DEFAULT_BY) -> pd.DataFrame:
    """Run the held-out test, per root and stratum: the shortlist against not shortlisting at all.

    ``by`` names the selection-window statistic ranked on. A row it is undefined on is dropped,
    so ``shortlisted`` can come back below :data:`TOP`.
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
