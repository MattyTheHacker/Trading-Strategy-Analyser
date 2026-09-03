"""Walk a campaign shortlist forward through several folds, rather than one hand-cut split.

    ./.venv/Scripts/python.exe tools/campaign_walkforward.py --strategy InsideBar

§M27's held-out gate is a single time cut at 60% of the bars, so it tests one regime transition
and cannot say whether a shortlist survives several. This is the multi-fold version:
:func:`nqbt.walkforward.walk_forward` re-selects on each training window and measures the winner
on the window that follows, which asks whether **picking** survives rather than whether one
choice did -- ``docs/roadmap.md`` §M27.6.

**The shortlist is the candidate pool, not the whole grid.** Putting 760,960 combinations through
several folds is unaffordable and the shortlist is what any claim rests on. The cost is that the
pool was itself chosen on stored rows, so a fold result is only clean to the extent the pool did
not see the folds: rank on ``--window selection``, or widen ``--top`` until the pool stops being
a selection, before reading one as a verdict.

**One walk-forward per resolution.** Two candidates at different bar sizes are different frames
and cannot be selected between, so a shortlist spanning resolutions runs as one independent
walk-forward each and never as one pool.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_shortlist import TOP, rebuild, shortlist
from tools.campaign_sweep import COMMISSION, SLIPPAGE_TICKS

from nqbt import archetypes, context, logsetup, resample, splice, sweep, walkforward
from nqbt.costs import TradingCosts
from nqbt.dispersion import MIN_TRADES
from nqbt.instruments import get_instrument

logger = logging.getLogger(__name__)

TRAIN_SHARE = 0.5
TEST_SHARE = 0.1
"""Fold geometry as shares of the resampled series rather than bar counts, because a bar count
means a different amount of time at each resolution. The pair gives five sliding folds."""

PASS_MARK = 1.0
"""Pooled out-of-sample profit factor a shortlist has to clear. The other half of §M27's Gate 2
-- beating the holdout median of not selecting at all -- is that gate's and is not re-derived
here; this one asks whether the selection makes money out of sample at all."""


def warmup_for(spec: context.ContextSpec, minutes: int) -> int:
    """The longest lookback the shortlist's own context declares, in bars of its resolution.

    Every fold is prepared independently, so without a prefix each one measures its own warm-up.
    **Relative volume is the gap**: its baseline is counted in sessions, not bars, so raise
    ``--warmup-bars`` by hand for a volume-stratified shortlist.
    """
    coarse: list[int] = [math.ceil(key.period * key.minutes / minutes) for key in spec.higher_timeframe_keys]
    trend: list[int] = [max(key) for key in spec.trend_keys]

    return max(
        [
            *(period for _, period in spec.ma_keys),
            *spec.atr_periods,
            *spec.band_periods,
            *spec.regime_lookbacks,
            *trend,
            *coarse,
        ],
        default=0,
    )


def candidate_grid(rows: pd.DataFrame, archetype: archetypes.Archetype) -> sweep.Grid:
    """The shortlisted rows as a grid whose combinations are exactly those configurations."""
    return sweep.Grid.of_combinations(
        [rebuild(row, archetype) for _, row in rows.iterrows()],
        archetype=archetype,
    )


def geometry(n_bars: int, train_share: float, test_share: float) -> tuple[int, int]:
    """Train and test window lengths, as bar counts taken from shares of the series."""
    train_bars: int = math.floor(n_bars * train_share)
    test_bars: int = math.floor(n_bars * test_share)
    if train_bars < 1 or test_bars < 1:
        msg: str = (
            f"{n_bars:,} bars at shares {train_share}/{test_share} gives a window of no bars; "
            f"raise the shares or use a finer resolution"
        )
        raise RuntimeError(msg)

    return train_bars, test_bars


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def run_resolution(
    name: str,
    rows: pd.DataFrame,
    root: str,
    minutes: int,
    bars: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Walk one resolution's shortlist forward and return its verdict row."""
    archetype: archetypes.Archetype = archetypes.get(name)
    grid: sweep.Grid = candidate_grid(rows, archetype)
    frame: pd.DataFrame = resample.resample(bars, minutes)
    train_bars, test_bars = geometry(len(frame), args.train_share, args.test_share)
    warmup: int = (
        args.warmup_bars if args.warmup_bars is not None else warmup_for(grid.required_context(), minutes)
    )

    logger.info("")
    logger.info(
        "%s on %s at %dm: %d candidates, %s bars, train %s / test %s, %s, warm-up %d",
        name,
        root,
        minutes,
        len(grid),
        f"{len(frame):,}",
        f"{train_bars:,}",
        f"{test_bars:,}",
        "anchored" if args.anchored else "sliding",
        warmup,
    )

    result: walkforward.WalkForwardResult = walkforward.walk_forward(
        frame,
        grid,
        TradingCosts(commission_per_contract=COMMISSION[root], slippage_ticks=SLIPPAGE_TICKS),
        train_bars=train_bars,
        test_bars=test_bars,
        instrument=get_instrument(root),
        select_by=args.by,
        anchored=args.anchored,
        warmup_bars=warmup,
        min_trades=args.min_trades,
        n_jobs=args.n_jobs,
    )
    show(
        f"{name} {root} {minutes}m -- each fold's choice and what it did next",
        result.table,
    )
    summary: walkforward.WalkForwardSummary = result.summary()

    return {
        "strategy": name,
        "root": root,
        "resolution": minutes,
        "candidates": len(grid),
        **summary.as_dict(),
        "passes": summary.test_pooled > PASS_MARK,
    }


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Multi-fold walk-forward over a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["selection"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="ranks the pool and selects each fold")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations the pool holds")
    parser.add_argument("--train-share", type=float, default=TRAIN_SHARE)
    parser.add_argument("--test-share", type=float, default=TEST_SHARE)
    parser.add_argument("--anchored", action="store_true", help="grow the training window from bar zero")
    parser.add_argument("--warmup-bars", type=int, default=None, help="default: the context's own longest")
    parser.add_argument("--min-trades", type=int, default=MIN_TRADES)
    parser.add_argument("--n-jobs", type=int, default=8)
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = shortlist(
        args.strategy,
        args.root,
        args.window,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
    )
    logger.info(
        "%s on %s: %d configurations ranked on %s by %s; stratum %s",
        args.strategy,
        args.root,
        len(rows),
        "+".join(args.window),
        args.by,
        args.stratum or "any",
    )

    bars: pd.DataFrame = splice.load_continuous(args.root)
    verdicts: list[dict[str, object]] = [
        run_resolution(args.strategy, block, args.root, int(minutes), bars, args)
        for minutes, block in rows.groupby("resolution", sort=True)
    ]
    logger.info("")
    logger.info("=" * 110)
    show("WALK-FORWARD VERDICT -- pooled out of sample, per resolution", pd.DataFrame(verdicts))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
