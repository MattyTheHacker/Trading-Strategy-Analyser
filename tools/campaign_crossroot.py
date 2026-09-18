"""Run one root's shortlist on another root, to see whether a configuration travels.

    ./.venv/Scripts/python.exe tools/campaign_crossroot.py --top 200 --min-trades 500

Every other campaign tool asks whether a configuration survives a different *window* of the
same instrument. This asks whether it survives a different *instrument*, which is a stronger
test of the same kind: nothing in the target root was seen when the configuration was chosen.

**Roots are paired by size class**, NQ to ES and GC, MNQ to MES and MGC, so that the round-turn
commission is the same on both sides and the only thing changing is the market. The target
root's commission is set explicitly rather than inherited from the stored row.

**The ranking floor is the point of the tool, not a detail.** Ranked on profit factor at the
campaign's own ``MIN_TRADES`` of 30, the top of every archetype is small-sample noise -- the
median top-200 row holds 43 trades and two thirds hold under 50, and the median profit factor
falls from 3.77 to 1.44 as the floor rises to 500. ``--min-trades`` defaults high for that
reason, and a row whose profit factor is infinite is dropped rather than ranked first.

**A shortlist also has to be readable, and profit factor does not say whether it is.** A row
whose fill assumption decided most of its legs is an artifact of ``ambiguity_policy`` rather
than a strategy, and it outranks everything real: OpeningRange's ``entry=rejection`` rows reach
a stored profit factor of 3,955 on 613 trades with one loser, an ``ambiguous_share`` of 0.89
and trades held under one bar. §M28.7 measured that family and found 0 of 20 keep a profit
factor above 1.00 under the other policy. Rows above :data:`~nqbt.disambiguate.MIN_AMBIGUOUS_SHARE`
are therefore dropped before ranking -- ``docs/findings/m28-7-rejection-swept.md``.

Nothing here is a gate. It reports the distribution of a pre-chosen set on unseen instruments;
picking the best performer *on the target* would re-introduce the selection bias one level up,
which is why no ranking of the output is printed -- ``docs/findings/README.md``.
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
from tools.campaign_report import rank
from tools.campaign_shortlist import db_path, load, rerun_group

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

PAIRS: dict[str, tuple[str, ...]] = {"NQ": ("ES", "GC"), "MNQ": ("MES", "MGC")}
"""Which target roots each source root's shortlist is run on, paired by size class."""

COMMISSION: dict[str, float] = {
    "NQ": 4.50,
    "MNQ": 1.50,
    "ES": 4.50,
    "MES": 1.50,
    "GC": 4.50,
    "MGC": 1.50,
}
"""Round-turn dollars per contract, matching ``tools/campaign_sweep.py``."""

TOP = 200
MIN_TRADES = 500
WINDOW = "selection"
BY = "profit_factor"

OUT_DIR = paths.RESULTS_DIR / "crossroot"


def selected(name: str, root: str, top: int, min_trades: int) -> pd.DataFrame:
    """The configurations a source root nominates, on a sample large enough to mean something."""
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
        frame: pd.DataFrame = resample.resample(bars, int(minutes))
        priced = block.assign(commission_per_contract=COMMISSION[target])
        for row, summary, _ in rerun_group(
            priced, frame, archetype, target, int(minutes), context.PriceBasis.RAW
        ):
            out.append(
                {
                    "strategy": name,
                    "source_root": str(row["root"]),
                    "target_root": target,
                    "resolution": int(minutes),
                    "stratum": str(row["stratum"]),
                    "variant": str(row["variant"]),
                    "source_pf": float(row[BY]),
                    "source_trades": int(row["trades"]),
                    "target_pf": float(summary["profit_factor"]),
                    "target_trades": int(summary["trades"]),
                    "target_net_pnl": float(summary["net_pnl"]),
                    "target_session_close_share": float(summary["session_close_share"]),
                    "source_ambiguous_share": float(row["ambiguous_share"]),
                    "target_ambiguous_share": float(summary["ambiguous_share"]),
                },
            )
        logger.info("  %-18s %-4s %2dm  %4d configurations", name, target, int(minutes), len(block))

    return pd.DataFrame(out)


def crossroot(names: Sequence[str], top: int, min_trades: int) -> pd.DataFrame:
    """Every archetype's shortlist, run on every target root its source root pairs with."""
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
    """Per archetype and target root: the distribution, never a ranking of it."""
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
