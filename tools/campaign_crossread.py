"""Read every stored stratum against the same combination run unfiltered.

    ./.venv/Scripts/python.exe tools/campaign_crossread.py
    ./.venv/Scripts/python.exe tools/campaign_crossread.py --dimension phase --min-score 8

A score is a consistency check and not a p-value -- ``tools/README.md`` § "campaign_crossread.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, logsetup, volume
from tools.campaign_report import UNFILTERED, dimension_of, load, parameter_columns
from tools.campaign_sweep import (
    STRATUM_GROUPS,
    VARIANTS,
    Calibration,
    Cuts,
    RegimeCut,
    VolumeCalibration,
    VolumeCut,
    strata,
)

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

SCALARS = (bool, int, float, str)
"""What a parameter default has to be to stand in for an absent one in a join key."""


def ran_at(strategy: str) -> dict[str, bool | int | float | str]:
    """Return every parameter's default for one archetype: what a row stored before it ran at."""
    params: archetypes.Params = archetypes.get(strategy).params_cls()

    return {
        field.name: value
        for field in fields(params)
        if isinstance(value := getattr(params, field.name), SCALARS)
    }


def probe_cuts() -> Cuts:
    """Return a calibration whose only job is to make the fitted stratum generators yield their axes.

    The values are never run; :func:`context_columns` reads the keys alone.
    """
    regime: Calibration = (RegimeCut(20, 0.35, 0.75, (0.20, 0.80)),)
    volumes: VolumeCalibration = tuple(
        VolumeCut(volume.key(form, 30, 20), 0.7, 1.5, (0.2, 0.8)) for form in volume.VolumeForm
    )

    return Cuts(regime=regime, volume=volumes)


def context_columns() -> frozenset[str]:
    """Return every parameter a stratum generator sets, read out of the generators themselves.

    Derived rather than listed so that a dimension added to ``STRATUM_GROUPS`` cannot leave a
    column behind here -- one left in the join key would pair a stratum only against itself.
    """
    found: set[str] = set()
    for group in STRATUM_GROUPS:
        for _, axes in strata(group, probe_cuts()):
            found.update(axes)

    return frozenset(found)


def pairing_columns(frame: pd.DataFrame) -> list[str]:
    """Return the columns that identify the same combination across two strata.

    Every parameter except the ones a stratum exists to move -- varying those is what a stratum
    *is*, so keeping them would make each stratum pair only with itself.
    """
    context: frozenset[str] = context_columns()

    return [column for column in parameter_columns(frame) if column not in context]


def is_recut(stratum: str) -> bool:
    """Return whether a stratum re-cuts a dimension another group already owns.

    ``volume=HEAVY@per_bar_20 q=0.20/0.80`` and ``regime=CONSOLIDATING@n=20`` are the shape --
    ``campaign_sweep.RECUTS``, and :func:`campaign_report.dimension_of` documents the ``@``.
    """
    return "@" in stratum


def common_variants(frame: pd.DataFrame) -> set[str]:
    """Return the variants every plain filtered stratum holds, empty where the frame holds none.

    Re-cuts are left out of the intersection, not out of the pairing.
    """
    filtered: pd.DataFrame = frame[frame["stratum"] != UNFILTERED]
    recut = filtered["stratum"].map(lambda name: is_recut(str(name))).astype(bool)
    plain: pd.DataFrame = filtered[~recut]
    per_stratum: pd.Series = plain.groupby("stratum")["variant"].agg(set)  # duckdb's dtypes
    if per_stratum.empty:
        return set()

    return set.intersection(*per_stratum.to_list())


def paired(frame: pd.DataFrame, variants: set[str] | None = None) -> pd.DataFrame:
    """Pair each filtered row with the unfiltered row of the same combination, in one window.

    ``variants`` states the set outright, for a campaign whose every filtered stratum is a
    re-cut.
    """
    shared: set[str] = variants if variants is not None else common_variants(frame)
    if not shared:
        return pd.DataFrame()

    block: pd.DataFrame = frame[frame["variant"].isin(shared)].copy()
    if block.empty:
        return pd.DataFrame()

    keys: list[str] = [*pairing_columns(block), *CELL_KEYS, "variant"]
    defaults: dict[str, bool | int | float | str] = ran_at(str(block["strategy"].iloc[0]))
    for column in keys:
        if column not in defaults:
            continue

        block[column] = block[column].fillna(defaults[column])

    for column in keys:
        if block[column].dtype.kind == "f":
            block[column] = block[column].fillna(MISSING)

    base: pd.DataFrame = block[block["stratum"] == UNFILTERED].drop_duplicates(subset=keys)
    arm: pd.DataFrame = block[block["stratum"] != UNFILTERED]
    if base.empty or arm.empty:
        return pd.DataFrame()

    carried: list[str] = ["profit_factor", "trades", "net_pnl"]

    return arm.merge(base[[*keys, *carried]], on=keys, suffixes=("", "_base"), how="inner")


def per_window(
    name: str,
    variants: set[str] | None = None,
    *,
    by_variant: bool = False,
) -> pd.DataFrame:
    """Return the paired difference per cell, one row per stratum, cell and window.

    ``by_variant`` keeps the variant in the key rather than pooling the arms of one set, which
    is what a campaign measuring the variant dimension itself needs -- ``docs/roadmap.md`` §M33.
    """
    keys: list[str] = ["stratum", *CELL_KEYS, *(["variant"] if by_variant else [])]
    blocks: list[pd.DataFrame] = []
    for window in WINDOWS:
        frame: pd.DataFrame = load(name, [window])
        if frame.empty:
            continue

        merged: pd.DataFrame = paired(frame, variants)
        if merged.empty:
            continue

        dropped: set[str] = set(frame["stratum"].unique()) - set(merged["stratum"].unique()) - {UNFILTERED}
        if dropped:
            missed: str = ", ".join(sorted({dimension_of(stratum) for stratum in dropped}))
            logger.info("%s %s: %d strata have no unfiltered twin (%s)", name, window, len(dropped), missed)

        merged = merged.assign(delta=merged["profit_factor"] - merged["profit_factor_base"])
        summary: pd.DataFrame = (
            merged.groupby(keys, dropna=False)
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


def agreement(cells: pd.DataFrame, *, by_variant: bool = False) -> pd.DataFrame:
    """Count the cells a filter won in both windows against the cells it lost in both.

    A cell that wins one window and loses the other counts for neither side. ``by_variant``
    scores each arm of a variant set separately.
    """
    if cells.empty:
        return pd.DataFrame()

    carried: list[str] = [*(["variant"] if by_variant else []), *GROUP_KEYS]
    wide: pd.DataFrame = cells.pivot_table(
        index=["strategy", "stratum", *CELL_KEYS, *(["variant"] if by_variant else [])],
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
        wide.groupby(carried, dropna=False)
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
    """Lay out one dimension's scores as cells down the rows and archetypes across the columns."""
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
        "--variant",
        nargs="+",
        default=None,
        help="score these variants separately instead of the arms every plain stratum shares",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=8,
        help="how many cells must agree before a stratum is named consistent",
    )
    args = parser.parse_args(argv[1:])

    wanted_variants: set[str] | None = set(args.variant) if args.variant else None
    by_variant: bool = wanted_variants is not None
    scores: list[pd.DataFrame] = []
    for name in args.strategies:
        cells: pd.DataFrame = per_window(name, wanted_variants, by_variant=by_variant)
        if cells.empty:
            logger.warning("no paired strata for %s; run --split first", name)
            continue

        scores.append(agreement(cells, by_variant=by_variant))

    if not scores:
        logger.warning("nothing to read")

        return 1

    scored: pd.DataFrame = pd.concat(scores, ignore_index=True)
    wanted: list[str] = args.dimension or sorted(scored["dimension"].unique())
    for dimension in wanted:
        show(f"{dimension}: cells won in both windows minus cells lost in both", matrix(scored, dimension))

    columns: list[str] = [
        *(["variant"] if by_variant else []),
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
