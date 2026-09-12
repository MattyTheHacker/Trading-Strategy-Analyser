"""Compare the raw context labels against the fitted ones over the same bars.

    ./.venv/Scripts/python.exe tools/campaign_labels.py --dimension regime
    ./.venv/Scripts/python.exe tools/campaign_labels.py --dimension volume --resolutions 5
    ./.venv/Scripts/python.exe tools/campaign_labels.py --dimension windows --volume-rolling-bars 10 90

A stratum is named for a state and cut by a threshold pair, so a result quoted under a label is
a result about a cut. This measures how much of that label survives being re-cut: the share of
bars each raw state keeps, and where the rest of them go.

**No sweep and no database.** The bars are the spliced continuous series and both cuts are
computed here, so this says what the two stratifications label differently and nothing about
what either one earns -- ``docs/findings/m30-volume-regime-recut.md`` reads it against the
paired scores.

The fit is taken on the selection window alone, exactly as ``tools/campaign_sweep.py`` takes
it, so the cut compared against is the cut the sweep ran.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_sweep import (
    REGIME_QUANTILES,
    SELECTION_SHARE,
    VOLUME_BASELINE_SESSIONS,
    VOLUME_ROLLING_BARS,
    VOLUME_TAILS,
    named_forms,
    volume_series,
)

from nqbt import context, logsetup, regime, resample, splice, volume

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray

logger = logging.getLogger(__name__)

REGIME = "regime"
VOLUME = "volume"
FORMS = "forms"
WINDOWS = "windows"

REGIME_ORDER = ("CONSOLIDATING", "UNCLASSIFIABLE", "DIRECTIONAL")
VOLUME_ORDER = ("THIN", "NORMAL", "HEAVY")

RAW_REGIME = (0.3, 0.5)
"""``DeadCatParams``' own defaults, which is the pair every stored regime stratum was cut by."""

RAW_VOLUME = (0.7, 1.5)
"""``DeadCatParams``' own defaults, which is the pair every stored volume stratum was cut by."""


def selection_bars(root: str) -> pd.DataFrame:
    """The window a cut is fitted on, taken exactly as ``campaign_sweep.fit_regime`` takes it."""
    bars: pd.DataFrame = splice.load_continuous(root)

    return bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]


def confusion(raw: pd.Series, fitted: pd.Series, order: tuple[str, ...]) -> pd.DataFrame:
    """Row-normalised percentages: where each raw state's bars land under the fitted cut."""
    table: pd.DataFrame = pd.crosstab(raw, fitted, normalize="index") * 100.0

    return table.reindex(index=list(order), columns=list(order))


def named(labels: np.ndarray, states: dict[int, str], keep: BoolArray, name: str) -> pd.Series:
    """One label array as state names, warm-up bars dropped."""
    return pd.Series([states[int(value)] for value in labels[keep]], name=name)


def regime_rows(root: str, minutes: int, lookbacks: list[int]) -> list[pd.DataFrame]:
    """One confusion table per lookback, raw pair against the fitted quantiles."""
    close: FloatArray = resample.resample(selection_bars(root), minutes)["close"].to_numpy(dtype=float)
    states: dict[int, str] = {int(state): state.name for state in regime.Regime}
    tables: list[pd.DataFrame] = []
    for lookback in lookbacks:
        ratio: FloatArray = regime.efficiency_ratio(close, lookback)
        measured: BoolArray = np.isfinite(ratio)
        cut: tuple[float, float] = regime.thresholds_from_quantiles(ratio, *REGIME_QUANTILES)
        raw: pd.Series = named(regime.label(ratio, *RAW_REGIME), states, measured, "raw")
        fitted: pd.Series = named(regime.label(ratio, *cut), states, measured, "fitted")
        logger.info(
            "  %s %2dm n=%-3d raw %.2f/%.2f  fitted %.4f/%.4f  agree %.1f%%  bars %s",
            root,
            minutes,
            lookback,
            *RAW_REGIME,
            *cut,
            float((raw.to_numpy() == fitted.to_numpy()).mean() * 100.0),
            f"{int(measured.sum()):,}",
        )
        table: pd.DataFrame = confusion(raw, fitted, REGIME_ORDER)
        tables.append(table.assign(root=root, resolution=minutes, cut=lookback))

    return tables


def labelled(
    root: str,
    minutes: int,
    tails: tuple[float, float],
    series: tuple[volume.VolumeKey, ...],
) -> dict[str, pd.Series]:
    """Each series' states over the same bars, every one fitted to its own distribution.

    Keyed by ``volume.describe_key``, so two series differing only in a window are separable.
    """
    frame: pd.DataFrame = resample.resample(selection_bars(root), minutes)
    spec = context.ContextSpec(volume_keys=series, needs_time_of_day=True)
    data: context.Dataset = context.prepare(frame, spec, bar_minutes=minutes)
    states: dict[int, str] = {int(state): state.name for state in volume.VolumeState}
    measured: BoolArray = np.all([np.isfinite(data.relative_volume(key)) for key in series], axis=0)
    cut: dict[str, pd.Series] = {}
    for key in series:
        relative: FloatArray = data.relative_volume(key)
        pair: tuple[float, float] = volume.thresholds_from_quantiles(relative, *tails)
        cut[volume.describe_key(key)] = named(volume.label(relative, *pair), states, measured, "fitted")

    return cut


def pair_rows(
    root: str,
    minutes: int,
    series: tuple[volume.VolumeKey, ...],
) -> list[pd.DataFrame]:
    """One confusion table per (tail size, ordered pair of series): who agrees with whom.

    The cut is held at one tail size across both, so every series labels the same share of bars
    and any disagreement is about *which* bars -- ``docs/roadmap.md`` §M10.2.
    """
    tables: list[pd.DataFrame] = []
    for tails in VOLUME_TAILS:
        cut: dict[str, pd.Series] = labelled(root, minutes, tails, series)
        for reference, other in itertools.permutations(cut, 2):
            left: pd.Series = cut[reference].rename("raw")
            right: pd.Series = cut[other].rename("fitted")
            logger.info(
                "  %s %2dm q=%.2f/%.2f  %-20s vs %-20s  agree %.1f%%",
                root,
                minutes,
                *tails,
                reference,
                other,
                float((left.to_numpy() == right.to_numpy()).mean() * 100.0),
            )
            table: pd.DataFrame = confusion(left, right, VOLUME_ORDER)
            tables.append(
                table.assign(
                    root=root,
                    resolution=minutes,
                    cut=f"q={tails[0]:.2f}/{tails[1]:.2f} {reference} -> {other}",
                )
            )

    return tables


def volume_rows(root: str, minutes: int) -> list[pd.DataFrame]:
    """One confusion table per (form, tail size), raw pair against the fitted tails."""
    series: tuple[volume.VolumeKey, ...] = volume_series()
    frame: pd.DataFrame = resample.resample(selection_bars(root), minutes)
    spec = context.ContextSpec(volume_keys=series, needs_time_of_day=True)
    data: context.Dataset = context.prepare(frame, spec, bar_minutes=minutes)
    states: dict[int, str] = {int(state): state.name for state in volume.VolumeState}
    tables: list[pd.DataFrame] = []
    for key in series:
        relative: FloatArray = data.relative_volume(key)
        measured: BoolArray = np.isfinite(relative)
        raw: pd.Series = named(volume.label(relative, *RAW_VOLUME), states, measured, "raw")
        for tails in VOLUME_TAILS:
            cut: tuple[float, float] = volume.thresholds_from_quantiles(relative, *tails)
            fitted: pd.Series = named(volume.label(relative, *cut), states, measured, "fitted")
            logger.info(
                "  %s %2dm %-16s q=%.2f/%.2f  raw %.2f/%.2f  fitted %.3f/%.3f  agree %.1f%%",
                root,
                minutes,
                key.form.name.lower(),
                *tails,
                *RAW_VOLUME,
                *cut,
                float((raw.to_numpy() == fitted.to_numpy()).mean() * 100.0),
            )
            tables.append(
                confusion(raw, fitted, VOLUME_ORDER).assign(
                    root=root,
                    resolution=minutes,
                    cut=f"{key.form.name.lower()} q={tails[0]:.2f}/{tails[1]:.2f}",
                )
            )

    return tables


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.max_rows", 200):
        logger.info("%s", frame.to_string(float_format=lambda value: f"{value:.1f}", na_rep="--"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Raw context labels against the fitted ones.")
    parser.add_argument("--dimension", choices=[REGIME, VOLUME, FORMS, WINDOWS], default=REGIME)
    parser.add_argument("--roots", nargs="+", default=["MNQ", "NQ"])
    parser.add_argument("--resolutions", nargs="+", type=int, default=[5, 15])
    parser.add_argument("--regime-lookbacks", nargs="+", type=int, default=[5, 10, 20, 30, 50])
    parser.add_argument(
        "--volume-forms",
        nargs="+",
        choices=[form.name for form in volume.VolumeForm],
        default=[form.name for form in volume.VolumeForm],
    )
    parser.add_argument("--volume-rolling-bars", nargs="+", type=int, default=[VOLUME_ROLLING_BARS])
    parser.add_argument("--volume-baseline-sessions", nargs="+", type=int, default=[VOLUME_BASELINE_SESSIONS])
    args = parser.parse_args(argv[1:])
    ladder: tuple[volume.VolumeKey, ...] = volume_series(
        named_forms(args.volume_forms), args.volume_rolling_bars, args.volume_baseline_sessions
    )

    tables: list[pd.DataFrame] = []
    for root in args.roots:
        for minutes in args.resolutions:
            if args.dimension == REGIME:
                tables.extend(regime_rows(root, minutes, args.regime_lookbacks))
                continue

            if args.dimension == FORMS:
                tables.extend(pair_rows(root, minutes, volume_series()))
                continue

            if args.dimension == WINDOWS:
                tables.extend(pair_rows(root, minutes, ladder))
                continue

            tables.extend(volume_rows(root, minutes))

    stacked: pd.DataFrame = pd.concat(tables)
    stacked.index.name = "raw"
    heading: str = (
        "where each series' state lands under another series"
        if args.dimension in {FORMS, WINDOWS}
        else "where each raw state's bars land under the fitted cut"
    )
    show(
        f"{args.dimension}: {heading}, % of the row state",
        stacked.reset_index().set_index(["root", "resolution", "cut", "raw"]),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
