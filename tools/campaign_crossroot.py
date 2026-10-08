"""Run one root's shortlist on another root, to see whether a configuration travels.

    uv run tools/campaign_crossroot.py --top 200 --min-trades 500

``tools/README.md`` § "campaign_crossroot.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, disambiguate, logsetup, paths, resample, splice
from tools.campaign_report import load, rank
from tools.campaign_shortlist import rerun_group
from tools.campaign_sweep import COMMISSION, db_path

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

PAIRS: dict[str, tuple[str, ...]] = {"NQ": ("ES", "GC"), "MNQ": ("MES", "MGC")}
"""Which target roots each source root's shortlist is run on, paired by size class."""

TOP = 200
MIN_TRADES = 500
WINDOW = "selection"
BY = "profit_factor"

OUT_DIR = paths.RESULTS_DIR / "crossroot"


def selected(name: str, root: str, top: int, min_trades: int) -> pd.DataFrame:
    """Return the configurations a source root nominates, on a sample large enough to mean something."""
    frame: pd.DataFrame = load(name, [WINDOW])
    frame = frame[(frame["root"] == root) & (frame["trades"] >= min_trades)]
    # A variant swept into a stratum contaminates a later top-N -- docs/roadmap.md, "Standing traps".
    frame = frame[~frame["variant"].str.contains("hold=", na=False)]
    frame = frame[np.isfinite(frame[BY])]
    # A row the fill assumption decided is not a measurement of the strategy -- §M28.7.
    frame = frame[frame["ambiguous_share"] <= disambiguate.MIN_AMBIGUOUS_SHARE]
    if frame.empty:
        msg: str = (
            f"{name} on {root}: no stored row clears {min_trades} trades and "
            f"an ambiguous share of {disambiguate.MIN_AMBIGUOUS_SHARE} in the {WINDOW} window"
        )
        raise RuntimeError(msg)

    return rank(frame, top, BY)


def run_on(name: str, rows: pd.DataFrame, target: str) -> pd.DataFrame:
    """Re-run every selected configuration on one target root, one group per resolution."""
    archetype: archetypes.Archetype = archetypes.get(name)
    bars: pd.DataFrame = splice.load_continuous(target)
    out: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=True):
        bar_minutes: int = int(minutes)  # type: ignore[arg-type]  # a groupby key on an int column
        frame: pd.DataFrame = resample.resample(bars, bar_minutes)
        priced = block.assign(commission_per_contract=COMMISSION[target])
        for row, summary, _ in rerun_group(
            priced, frame, archetype, target, bar_minutes, context.PriceBasis.RAW
        ):
            out.append(
                {
                    "strategy": name,
                    "source_root": str(row["root"]),
                    "target_root": target,
                    "resolution": bar_minutes,
                    "stratum": str(row["stratum"]),
                    "variant": str(row["variant"]),
                    "source_pf": float(row[BY]),
                    "source_trades": int(row["trades"]),
                    "target_pf": float(summary["profit_factor"]),  # type: ignore[arg-type]  # a statistic
                    "target_trades": int(summary["trades"]),  # type: ignore[call-overload]  # a statistic
                    "target_net_pnl": float(summary["net_pnl"]),  # type: ignore[arg-type]  # a statistic
                    "target_session_close_share": float(summary["session_close_share"]),  # type: ignore[arg-type]  # a statistic
                    "source_ambiguous_share": float(row["ambiguous_share"]),
                    "target_ambiguous_share": float(summary["ambiguous_share"]),  # type: ignore[arg-type]  # a statistic
                },
            )
        logger.info("  %-18s %-4s %2dm  %4d configurations", name, target, bar_minutes, len(block))

    return pd.DataFrame(out)


def crossroot(names: Sequence[str], top: int, min_trades: int) -> pd.DataFrame:
    """Run every archetype's shortlist on every target root its source root pairs with."""
    frames: list[pd.DataFrame] = []
    for name in names:
        if not db_path(name).exists():
            logger.warning("%s has no stored campaign; skipped", name)
            continue

        for source_root, targets in PAIRS.items():
            rows: pd.DataFrame = selected(name, source_root, top, min_trades)
            logger.info("%s from %s: %d configurations", name, source_root, len(rows))
            frames.extend(run_on(name, rows, target) for target in targets)

    return pd.concat(frames, ignore_index=True)


def summarise(rows: pd.DataFrame) -> pd.DataFrame:
    """Summarise per archetype and target root: the distribution, never a ranking of it."""
    grouped = rows.groupby(["strategy", "target_root"])

    return pd.DataFrame(
        {
            "n": grouped.size(),
            "source_pf_median": grouped["source_pf"].median(),
            "target_pf_median": grouped["target_pf"].median(),
            "target_pf_p90": grouped["target_pf"].quantile(0.90),
            "share_above_1": grouped["target_pf"].apply(lambda s: float((s > 1.0).mean())),
            "target_trades_median": grouped["target_trades"].median(),
            "close_share_median": grouped["target_session_close_share"].median(),
            "ambiguous_share_median": grouped["target_ambiguous_share"].median(),
        },
    ).reset_index()


def main(argv: list[str]) -> int:
    """Run each shortlist on its paired roots and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Run one root's shortlist on another root.")
    parser.add_argument("--strategies", nargs="+", default=sorted(archetypes.names()))
    parser.add_argument("--top", type=int, default=TOP, help="configurations per archetype per source root")
    parser.add_argument(
        "--min-trades",
        type=int,
        default=MIN_TRADES,
        help="ranking floor; the campaign's own 30 ranks small-sample noise",
    )
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = crossroot(args.strategies, args.top, args.min_trades)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(OUT_DIR / "rows.parquet", index=False)

    table: pd.DataFrame = summarise(rows)
    table.to_csv(OUT_DIR / "summary.csv", index=False)
    logger.info("")
    logger.info("%s", table.to_string(index=False))
    logger.info("")
    logger.info("%d configuration runs -> %s", len(rows), OUT_DIR)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
