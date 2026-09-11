"""Read every stored stratum against the same combination run unfiltered.

    ./.venv/Scripts/python.exe tools/campaign_crossread.py
    ./.venv/Scripts/python.exe tools/campaign_crossread.py --dimension phase --min-score 8

``tools/campaign_holdout.py`` asks whether a *shortlist* survives the held-out window, which
makes it a measurement of selection as much as of the strategy. This asks the other question:
**does pinning one context filter on beat leaving it off, for the same parameters?** Every
filtered row has an unfiltered twin at identical parameters, root, resolution and variant, so
the comparison is paired and carries none of the shortlist-size bias § "The build spec's three
loose ends, measured" records.

Each pair is scored in **both** windows independently and the cells are counted, never pooled
into one number -- ``docs/roadmap.md`` §M28.14. A cell is one ``root x resolution``; the score
is how many of them the filter won in both windows minus how many it lost in both.

**A score is a consistency check and not a p-value.** The cells are two roots tracking one index
at five overlapping bar sizes, so they are nowhere near independent, and this tool ranks nothing
and tests nothing. ``tools/campaign_null.py`` is what carries evidence.

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

from tools.campaign_report import UNFILTERED, dimension_of, load, parameter_columns
from tools.campaign_sweep import (
    STRATUM_GROUPS,
    VARIANTS,
    Calibration,
    Cuts,
    VolumeCalibration,
    VolumeCut,
    strata,
)

from nqbt import logsetup, volume

logger = logging.getLogger(__name__)

WINDOWS = ("selection", "holdout")
"""The two disjoint spans a stratum has to win in to be counted. Both, never either."""

CELL_KEYS = ["root", "resolution"]
"""What one cell of the agreement count is. **Bar size is the largest lever in the campaign**, so
a pair is formed inside one resolution and the difference is only then counted across them --
``docs/roadmap.md`` §M28.14. Nothing here compares a cell against a cell of another size."""

GROUP_KEYS = ["strategy", "stratum"]
"""What a score is reported for: one archetype's one context cell."""

MISSING = -9.99e12
"""Stand-in for a NaN in a join key, because a NaN never equals itself and pandas would drop the
pair silently. Outside every parameter's range, so it can only match another absence."""


def probe_cuts() -> Cuts:
    """A calibration whose only job is to make the fitted stratum generators yield their axes.

    The values are never run; :func:`context_columns` reads the keys alone.
    """
    regime: Calibration = {20: (0.35, 0.75)}
    volumes: VolumeCalibration = tuple(
        VolumeCut(volume.key(form, 30, 20), 0.7, 1.5, (0.2, 0.8)) for form in volume.VolumeForm
    )

    return Cuts(regime=regime, volume=volumes)


def context_columns() -> frozenset[str]:
    """Every parameter a stratum generator sets, read out of the generators themselves.

    Derived rather than listed so that a dimension added to ``STRATUM_GROUPS`` cannot leave a
    column behind here -- one left in the join key would pair a stratum only against itself.
    """
    found: set[str] = set()
    for group in STRATUM_GROUPS:
        for _, axes in strata(group, probe_cuts()):
            found.update(axes)

    return frozenset(found)


def pairing_columns(frame: pd.DataFrame) -> list[str]:
    """The columns that identify the same combination across two strata.

    Every parameter except the ones a stratum exists to move -- varying those is what a stratum
    *is*, so keeping them would make each stratum pair only with itself.
    """
    context: frozenset[str] = context_columns()

    return [column for column in parameter_columns(frame) if column not in context]


def is_recut(stratum: str) -> bool:
    """Whether a stratum re-cuts a dimension another group already owns.

    ``volume=HEAVY@per_bar_20 q=0.20/0.80`` and ``regime=CONSOLIDATING@n=20`` are the shape --
    ``campaign_sweep.RECUTS``, and :func:`campaign_report.dimension_of` documents the ``@``.
    """
    return "@" in stratum


def common_variants(frame: pd.DataFrame) -> set[str]:
    """The variants every plain filtered stratum holds, empty where the frame holds none.

    A stratum run by a later campaign carries that campaign's variants and no earlier stratum's:
    OpeningRange's ``regime=CONSOLIDATING`` holds the fade and rejection arms that only the
    reversion campaigns ran. Read against a stratum built from the breakout arms alone, the
    difference reported would be the entry mechanism wearing the regime's name.

    **Re-cuts are left out of the intersection and not out of the pairing.** Each was run by its
    own campaign over its own variants, so including them empties the set and every archetype
    with one reports nothing -- which is what ElasticBand and OpeningRange did.
    """
    filtered: pd.DataFrame = frame[frame["stratum"] != UNFILTERED]
    recut = filtered["stratum"].map(lambda name: is_recut(str(name))).astype(bool)
    plain: pd.DataFrame = filtered[~recut]
    per_stratum: pd.Series = plain.groupby("stratum")["variant"].agg(set)  # duckdb's dtypes
    if per_stratum.empty:
        return set()

    return set.intersection(*per_stratum.to_list())


def paired(frame: pd.DataFrame) -> pd.DataFrame:
    """Each filtered row beside the unfiltered row of the same combination, in one window."""
    shared: set[str] = common_variants(frame)
    if not shared:
        return pd.DataFrame()

    block: pd.DataFrame = frame[frame["variant"].isin(shared)].copy()
    keys: list[str] = [*pairing_columns(block), *CELL_KEYS, "variant"]
    for column in keys:
        if block[column].dtype.kind == "f":
            block[column] = block[column].fillna(MISSING)

    base: pd.DataFrame = block[block["stratum"] == UNFILTERED].drop_duplicates(subset=keys)
    arm: pd.DataFrame = block[block["stratum"] != UNFILTERED]
    if base.empty or arm.empty:
        return pd.DataFrame()

    carried: list[str] = ["profit_factor", "trades", "net_pnl"]

    return arm.merge(base[[*keys, *carried]], on=keys, suffixes=("", "_base"), how="inner")


def per_window(name: str) -> pd.DataFrame:
    """The paired difference per cell, one row per stratum, cell and window."""
    blocks: list[pd.DataFrame] = []
    for window in WINDOWS:
        frame: pd.DataFrame = load(name, [window])
        if frame.empty:
            continue

        merged: pd.DataFrame = paired(frame)
        if merged.empty:
            continue

        dropped: set[str] = set(frame["stratum"].unique()) - set(merged["stratum"].unique()) - {UNFILTERED}
        if dropped:
            missed: str = ", ".join(sorted({dimension_of(stratum) for stratum in dropped}))
            logger.info("%s %s: %d strata have no unfiltered twin (%s)", name, window, len(dropped), missed)

        merged = merged.assign(delta=merged["profit_factor"] - merged["profit_factor_base"])
        summary: pd.DataFrame = (
            merged.groupby(["stratum", *CELL_KEYS], dropna=False)
            .agg(
                pairs=("delta", "size"),
                delta=("delta", "median"),
                profit_factor=("profit_factor", "median"),
                trades=("trades", "median"),
                session_close_share=("session_close_share", "median"),
            )
            .reset_index()
        )
        blocks.append(summary.assign(window=window, strategy=name))

    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


def agreement(cells: pd.DataFrame) -> pd.DataFrame:
    """Count the cells a filter won in both windows against the cells it lost in both.

    A cell that wins one window and loses the other counts for neither side, which is the whole
    point: the two windows are disjoint spans and agreeing across them is the claim being made.
    """
    if cells.empty:
        return pd.DataFrame()

    wide: pd.DataFrame = cells.pivot_table(
        index=["strategy", "stratum", *CELL_KEYS],
        columns="window",
        values=["delta", "profit_factor", "trades", "session_close_share"],
    ).reset_index()
    wide.columns = ["_".join(str(part) for part in name).rstrip("_") for name in wide.columns]
    deltas: list[str] = [f"delta_{window}" for window in WINDOWS]
    if not set(deltas) <= set(wide.columns):
        return pd.DataFrame()

    wide = wide.dropna(subset=deltas)
    if wide.empty:
        return pd.DataFrame()

    wide["helped"] = (wide["delta_holdout"] > 0.0) & (wide["delta_selection"] > 0.0)
    wide["hurt"] = (wide["delta_holdout"] < 0.0) & (wide["delta_selection"] < 0.0)

    scored: pd.DataFrame = (
        wide.groupby(GROUP_KEYS, dropna=False)
        .agg(
            cells=("helped", "size"),
            helped=("helped", "sum"),
            hurt=("hurt", "sum"),
            delta_hold=("delta_holdout", "median"),
            pf_hold=("profit_factor_holdout", "median"),
            trades_hold=("trades_holdout", "median"),
            close_share=("session_close_share_holdout", "median"),
        )
        .reset_index()
    )
    scored["score"] = scored["helped"] - scored["hurt"]
    scored["dimension"] = scored["stratum"].map(lambda name: dimension_of(str(name)))
    scored["cell"] = scored["stratum"].map(lambda name: str(name).split("=", 1)[-1])

    return scored


def matrix(scored: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """One dimension's scores as cells down the rows and archetypes across the columns."""
    block: pd.DataFrame = scored[scored["dimension"] == dimension]

    return block.pivot_table(index="cell", columns="strategy", values="score", aggfunc="first")


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", frame.to_string(float_format=lambda v: f"{v:.3f}", na_rep="--"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Read every stratum against its unfiltered twin.")
    parser.add_argument("--strategies", nargs="+", default=list(VARIANTS))
    parser.add_argument("--dimension", nargs="+", default=None, help="which context dimensions to print")
    parser.add_argument(
        "--min-score",
        type=int,
        default=8,
        help="how many cells must agree before a stratum is named consistent",
    )
    args = parser.parse_args(argv[1:])

    scores: list[pd.DataFrame] = []
    for name in args.strategies:
        cells: pd.DataFrame = per_window(name)
        if cells.empty:
            logger.warning("no paired strata for %s; run --split first", name)
            continue

        scores.append(agreement(cells))

    if not scores:
        logger.warning("nothing to read")

        return 1

    scored: pd.DataFrame = pd.concat(scores, ignore_index=True)
    wanted: list[str] = args.dimension or sorted(scored["dimension"].unique())
    for dimension in wanted:
        show(f"{dimension}: cells won in both windows minus cells lost in both", matrix(scored, dimension))

    columns: list[str] = [
        *GROUP_KEYS,
        "cells",
        "helped",
        "hurt",
        "score",
        "delta_hold",
        "pf_hold",
        "trades_hold",
        "close_share",
    ]
    consistent: pd.DataFrame = scored[scored["score"] >= args.min_score]
    show(
        f"consistent helpers -- score at or above {args.min_score}",
        consistent.sort_values("score", ascending=False)[columns].reset_index(drop=True),
    )
    costly: pd.DataFrame = scored[scored["score"] <= -args.min_score]
    show(
        f"consistent costs -- score at or below {-args.min_score}",
        costly.sort_values("score")[columns].reset_index(drop=True),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
