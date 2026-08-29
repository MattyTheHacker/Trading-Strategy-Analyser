"""Run one campaign configuration per contract, each against its own matched null.

    ./.venv/Scripts/python.exe tools/campaign_contracts.py --strategy InsideBar

**Read the consistency across contracts, not the individual p-values** -- with nineteen
contracts and two roots, one cell clearing 0.05 is the expected output of that many comparisons,
while every contract agreeing on the sign is not -- ``docs/roadmap.md`` §M26.

Per contract rather than spliced because ATR and the moving averages both step at a roll seam,
and because a spliced series hides whether an edge is two good quarters wide.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_null import rebuild
from tools.campaign_report import load

from nqbt import archetypes, dispersion, logsetup, randomentry, resample, stats, sweep
from nqbt.instruments import get_instrument

logger = logging.getLogger(__name__)

MIN_TRADES = 30
"""Contracts producing fewer trades than this are reported but not counted in the tally."""


def chosen(
    name: str,
    root: str,
    window: list[str],
    by: str,
    stratum: str | None = None,
    resolution: int | None = None,
) -> tuple[archetypes.Params, int]:
    """The configuration a window's ranking picked, and the resolution it was ranked at."""
    frame: pd.DataFrame = load(name, window)
    frame = frame[frame["root"] == root]
    if stratum is not None:
        frame = frame[frame["stratum"] == stratum]
    if resolution is not None:
        frame = frame[frame["resolution"] == resolution]
    if frame.empty:
        msg: str = f"no stored rows for {name} on {root} in {window}, stratum {stratum}"
        raise RuntimeError(msg)
    row: pd.Series = frame.nlargest(1, by).iloc[0]  # type: ignore[type-arg]  # duckdb's dtypes
    return rebuild(row, archetypes.get(name)), int(row["resolution"])


def one_contract(
    bars: pd.DataFrame,
    params: archetypes.Params,
    archetype: archetypes.Archetype,
    root: str,
    minutes: int,
    iterations: int,
    n_jobs: int,
) -> dict[str, object]:
    """Observed statistics and the matched null's median, for one contract."""
    frame: pd.DataFrame = resample.resample(bars, minutes)
    data = sweep.prepare_for(frame, sweep.Grid(base=params, archetype=archetype))
    observed: stats.Summary = stats.summarise_legs(
        archetype.legs(data, params, get_instrument(root)),
        data.day_codes,
    )
    if observed.trades == 0:
        return {"trades": 0, "profit_factor": float("nan"), "null_pf": float("nan")}
    null: pd.DataFrame = randomentry.null_summaries(
        data,
        params,
        archetype,
        get_instrument(root),
        iterations=iterations,
        n_jobs=n_jobs,
    )
    finite: pd.Series = null["profit_factor"][np.isfinite(null["profit_factor"])]  # type: ignore[type-arg]  # a float column
    return {
        "trades": observed.trades,
        "profit_factor": observed.profit_factor,
        "net_pnl": observed.net_pnl,
        "null_pf": float(finite.median()) if len(finite) else float("nan"),
        "null_trades": float(null["trades"].median()),
        "excess": observed.profit_factor - (float(finite.median()) if len(finite) else float("nan")),
    }


def run_root(
    name: str,
    root: str,
    window: list[str],
    by: str,
    iterations: int,
    n_jobs: int,
    stratum: str | None = None,
    resolution: int | None = None,
) -> pd.DataFrame:
    """Every front-month contract of one root, under the configuration the window chose."""
    archetype: archetypes.Archetype = archetypes.get(name)
    params, minutes = chosen(name, root, window, by, stratum, resolution)
    logger.info("")
    logger.info("%s on %s at %dm, configuration ranked on %s by %s", name, root, minutes, window, by)

    rows: list[dict[str, object]] = []
    for contract, bars in dispersion.contract_frames(root).items():
        result: dict[str, object] = one_contract(
            bars,
            params,
            archetype,
            root,
            minutes,
            iterations,
            n_jobs,
        )
        rows.append({"root": root, "contract": contract, **result})
        logger.info(
            "  %-10s trades %6s  PF %6s  null %6s  excess %+7s",
            contract,
            f"{int(result['trades']):,}",
            f"{result['profit_factor']:.3f}",
            f"{result['null_pf']:.3f}",
            f"{result.get('excess', float('nan')):.3f}",
        )
    return pd.DataFrame(rows)


def tally(frame: pd.DataFrame) -> pd.DataFrame:
    """How many contracts beat their own null, and how many simply made money."""
    rows: list[dict[str, object]] = []
    for root, block in frame.groupby("root"):
        viable: pd.DataFrame = block[block["trades"] >= MIN_TRADES]
        rows.append(
            {
                "root": root,
                "contracts": len(viable),
                "beats_null": int((viable["excess"] > 0).sum()),
                "profitable": int((viable["profit_factor"] > 1.0).sum()),
                "mean_pf": viable["profit_factor"].mean(),
                "mean_null_pf": viable["null_pf"].mean(),
                "mean_excess": viable["excess"].mean(),
                "total_net": viable["net_pnl"].sum(),
            },
        )
    return pd.DataFrame(rows)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Per-contract null test of a campaign configuration.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--roots", nargs="+", default=["MNQ", "NQ"])
    parser.add_argument("--window", nargs="+", default=["selection"])
    parser.add_argument("--by", default="profit_factor")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--n-jobs", type=int, default=8)
    args = parser.parse_args(argv[1:])

    frames: list[pd.DataFrame] = [
        run_root(
            args.strategy,
            root,
            args.window,
            args.by,
            args.iterations,
            args.n_jobs,
            args.stratum,
            args.resolution,
        )
        for root in args.roots
    ]
    combined: pd.DataFrame = pd.concat(frames, ignore_index=True)
    logger.info("")
    logger.info("--- per-contract tally ---")
    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", tally(combined).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
