"""Split each bracket geometry's result into what the geometry does and what the entry adds.

    ./.venv/Scripts/python.exe tools/geometry_contribution.py out.csv

Choose the entry settings before looking at any result -- ``tools/README.md`` § "geometry_contribution.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nqbt import archetypes, context, ingest, logsetup, randomentry, sweep
from nqbt.instruments import MNQ, ContractId
from nqbt.sim.types import (
    STOP_ATR,
    STOP_BAND,
    STOP_CATASTROPHE,
    TARGET_R,
    TARGET_STRETCH,
    ElasticBandParams,
)

logger = logging.getLogger(__name__)

CONTRACT = "MNQ 03-24"
COMMISSION = 0.75
"""Half of the $1.50 real round trip per contract -- ``CLAUDE.md``."""

SLIPPAGE = 1.0
ITERATIONS = 200
STATISTICS = ("profit_factor", "expectancy")

ENTRY = {"band_period": 20, "entry_std": 2.0, "min_bars_outside": 1, "band_lag": 0}
"""The middle of every entry axis, fixed so that only the geometry varies."""


BAND_STOP_DEPTHS = (0.5, 1.0, 1.5, 2.0)
"""How far past ``entry_std`` the band stop sits, in standard deviations."""


def geometries() -> list[tuple[str, str, ElasticBandParams]]:
    """Return ``(scheme, label, params)`` for every exit geometry to measure."""
    out: list[tuple[str, str, ElasticBandParams]] = []
    for hold in (5, 10, 20, 40):
        for level in (-0.5, 0.0, 0.5):
            out.append(
                (
                    "C-time-mean",
                    f"hold {hold}, target {level:+.1f}",
                    ElasticBandParams(
                        **ENTRY,
                        stop_mode=STOP_CATASTROPHE,
                        target_mode=TARGET_STRETCH,
                        target_stretch_levels=(level,),
                        max_hold_bars=hold,
                        commission_per_contract=COMMISSION,
                        slippage_ticks=SLIPPAGE,
                    ),
                ),
            )
    for stop in (1.0, 2.0, 3.0):
        for take_profit in (0.5, 1.0, 2.0):
            out.append(
                (
                    "B-atr",
                    f"stop {stop}xATR, tp {take_profit}R",
                    ElasticBandParams(
                        **ENTRY,
                        stop_mode=STOP_ATR,
                        target_mode=TARGET_R,
                        atr_stop_multiple=stop,
                        tp_multiplier=take_profit,
                        commission_per_contract=COMMISSION,
                        slippage_ticks=SLIPPAGE,
                    ),
                ),
            )
    for depth in BAND_STOP_DEPTHS:
        for level in (-0.5, 0.0, 0.5):
            out.append(
                (
                    "D-band",
                    f"stop {depth:+.1f}s, target {level:+.1f}",
                    ElasticBandParams(
                        **ENTRY,
                        stop_mode=STOP_BAND,
                        band_stop_std=depth,
                        target_mode=TARGET_STRETCH,
                        target_stretch_levels=(level,),
                        commission_per_contract=COMMISSION,
                        slippage_ticks=SLIPPAGE,
                    ),
                ),
            )

    return out


def measure(contract: str, iterations: int, n_jobs: int) -> pd.DataFrame:
    """Return one row per geometry: observed, null median and the excess between them."""
    bars = ingest.load_contract(ContractId.parse(contract))
    archetype = archetypes.ELASTICBAND
    rows: list[dict[str, object]] = []
    for scheme, label, params in geometries():
        grid = sweep.Grid.of(params, archetype=archetype)
        data = sweep.prepare_for(bars, grid, price_basis=context.PriceBasis.RAW)
        results = randomentry.compare(
            data,
            params,
            archetype,
            MNQ,
            statistics=STATISTICS,
            iterations=iterations,
            n_jobs=n_jobs,
        )
        row: dict[str, object] = {"scheme": scheme, "geometry": label}
        for statistic, result in results.items():
            row[f"{statistic}_observed"] = result.observed
            row[f"{statistic}_null"] = result.null_median
            row[f"{statistic}_excess"] = result.observed - result.null_median
            row[f"{statistic}_verdict"] = result.verdict
        row["trades"] = results[STATISTICS[0]].observed_trades
        row["null_trades"] = results[STATISTICS[0]].null_median_trades
        rows.append(row)
        logger.info("%s  %s", scheme, label)

    return pd.DataFrame(rows)


def report(table: pd.DataFrame, statistic: str = "profit_factor") -> str:
    """Render the two rankings side by side, which is the whole point of the exercise."""
    lines: list[str] = []
    for scheme, group in table.groupby("scheme"):
        by_observed = group.nlargest(1, f"{statistic}_observed").iloc[0]
        by_excess = group.nlargest(1, f"{statistic}_excess").iloc[0]
        lines.append(f"{scheme}:")
        lines.append(f"  best by {statistic}: {by_observed.geometry}")
        lines.append(f"  best by excess:      {by_excess.geometry}")
        agree = "agree" if by_observed.geometry == by_excess.geometry else "DISAGREE"
        lines.append(f"  the two rankings {agree}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, help="where to write the per-geometry CSV")
    parser.add_argument("--contract", default=CONTRACT)
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    parser.add_argument("--jobs", type=int, default=5)
    args = parser.parse_args(argv)

    logsetup.configure(__name__)
    table = measure(args.contract, args.iterations, args.jobs)
    table.to_csv(args.out, index=False)
    logger.info("wrote %d geometries to %s", len(table), args.out)
    logger.info("\n%s", report(table))

    return 0


if __name__ == "__main__":
    sys.exit(main())
