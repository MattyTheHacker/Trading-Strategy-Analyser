"""Read the campaign databases and say which archetype is worth improving.

    ./.venv/Scripts/python.exe tools/campaign_report.py
    ./.venv/Scripts/python.exe tools/campaign_report.py --window selection holdout

Reports **distributions, not winners**. The best profit factor in a 300,000-row sweep is a
statement about the size of the sweep; the median and the profitable share are statements about
the strategy -- ``docs/roadmap.md`` § "Selecting on one contract is worse than not selecting".

Reads what ``tools/campaign_sweep.py`` wrote, one database per archetype.
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

from tools.campaign_sweep import MIN_TRADES, VARIANTS, db_path

from nqbt import logsetup, results, stats

logger = logging.getLogger(__name__)

SUMMARY_SQL = """
    SELECT c.*, s.root AS root
    FROM combos c JOIN sweeps s USING (sweep_id)
    WHERE c.trades >= {min_trades} AND isfinite(c.profit_factor)
"""

STATISTICS = frozenset(stats.Summary.columns())
"""What a results row carries beside its parameters. Read from the class, never copied."""

TAGS = frozenset(
    {
        "sweep_id",
        "combo_id",
        "variant",
        "stratum",
        "window",
        "strategy",
        "resolution",
        "contract",
        "tier2",
        "root",
        "commission_per_contract",
        "slippage_ticks",
    },
)
"""Columns that say which run a row came from rather than which parameters it used.

The two cost fields are here because they vary with the root and nothing else, so reporting
them as axes would report the root twice under a name that hides it."""


def load(name: str, windows: list[str]) -> pd.DataFrame:
    """Every viable combination stored for one archetype, tagged with its root."""
    frame: pd.DataFrame = results.query(
        SUMMARY_SQL.format(min_trades=MIN_TRADES),
        db_path=db_path(name),
    )

    return frame[frame["window"].isin(windows)]


def swept_axes(frame: pd.DataFrame) -> list[str]:
    """Parameter columns that actually vary here, so a constant is never reported as an axis."""
    return [
        column
        for column in frame.columns
        if column not in TAGS and column not in STATISTICS and frame[column].nunique(dropna=False) > 1
    ]


def profile(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Combination count, profitable share and the profit-factor distribution, per group."""
    grouped = frame.groupby(by, dropna=False)

    return pd.DataFrame(
        {
            "combos": grouped.size(),
            "profitable_%": 100.0 * grouped["profit_factor"].apply(lambda s: float((s > 1.0).mean())),
            "pf_median": grouped["profit_factor"].median(),
            "pf_p90": grouped["profit_factor"].quantile(0.90),
            "pf_best": grouped["profit_factor"].max(),
            "trades_med": grouped["trades"].median(),
            "net_median": grouped["net_pnl"].median(),
        },
    ).reset_index()


def eta_squared(frame: pd.DataFrame, axis: str, statistic: str = "profit_factor") -> float:
    """Share of ``statistic``'s variance the grouping by ``axis`` explains."""
    values = frame[statistic]
    grand: float = float(values.mean())
    total: float = float(((values - grand) ** 2).sum())
    if total <= 0.0:
        return 0.0

    groups = frame.groupby(axis, dropna=False)[statistic].agg(["count", "mean"])
    between: float = float((groups["count"] * (groups["mean"] - grand) ** 2).sum())

    return between / total


def axis_influence(frame: pd.DataFrame, axes: list[str]) -> pd.DataFrame:
    """How much of the profit-factor variance each axis explains, largest first.

    A property of the ranges swept rather than of the strategy -- ``docs/roadmap.md`` §M26.
    """
    rows: list[dict[str, object]] = [{"axis": axis, "eta2": eta_squared(frame, axis)} for axis in axes]

    return pd.DataFrame(rows).sort_values("eta2", ascending=False).reset_index(drop=True)


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def report_strategy(name: str, windows: list[str]) -> pd.DataFrame:
    """Print every table for one archetype and return its headline row."""
    frame: pd.DataFrame = load(name, windows)
    logger.info("")
    logger.info("=" * 110)
    logger.info("%s  --  %s combinations with >= %d trades", name, f"{len(frame):,}", MIN_TRADES)
    logger.info("=" * 110)
    if frame.empty:
        return pd.DataFrame()

    show("by root and resolution", profile(frame, ["root", "resolution"]))
    show("by context stratum, pooled over resolution", profile(frame, ["stratum"]))

    unfiltered: pd.DataFrame = frame[frame["stratum"] == "unfiltered"]
    if frame["variant"].nunique() > 1:
        show("by variant, unfiltered only", profile(unfiltered, ["variant"]))

    show(
        "axis influence on profit factor, unfiltered, eta^2",
        axis_influence(unfiltered, [*swept_axes(unfiltered), "resolution", "root"]),
    )
    show(
        "top 5 by profit factor -- a statement about the sweep's size, not the strategy",
        frame.nlargest(5, "profit_factor")[
            ["root", "resolution", "variant", "stratum", "trades", "profit_factor", "net_pnl", "sharpe"]
        ],
    )

    by_resolution: pd.DataFrame = profile(frame, ["resolution"])

    return pd.DataFrame(
        [
            {
                "strategy": name,
                "combos": len(frame),
                "profitable_%": 100.0 * float((frame["profit_factor"] > 1.0).mean()),
                "pf_median": frame["profit_factor"].median(),
                "pf_p90": frame["profit_factor"].quantile(0.90),
                "pf_best": frame["profit_factor"].max(),
                "best_res": int(by_resolution.nlargest(1, "pf_median")["resolution"].iloc[0]),
                "net_median": frame["net_pnl"].median(),
            },
        ],
    )


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Summarise the campaign sweep databases.")
    parser.add_argument("--strategies", nargs="+", default=list(VARIANTS))
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored windows to read")
    args = parser.parse_args(argv[1:])

    headlines: list[pd.DataFrame] = []
    for name in args.strategies:
        if not db_path(name).exists():
            logger.warning("no database for %s; skipping", name)
            continue

        headline: pd.DataFrame = report_strategy(name, args.window)
        if not headline.empty:
            headlines.append(headline)

    if headlines:
        logger.info("")
        logger.info("=" * 110)
        show("HEADLINE -- every archetype side by side", pd.concat(headlines, ignore_index=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
