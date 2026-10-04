"""Read the campaign databases and say which archetype is worth improving.

    uv run tools/campaign_report.py
    uv run tools/campaign_report.py --window selection holdout

Reports distributions, not winners -- ``tools/README.md`` § "campaign_report.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup, results, stats, trades
from tools.campaign_sweep import MIN_TRADES, VARIANTS, db_path

if TYPE_CHECKING:
    from collections.abc import Collection

logger = logging.getLogger(__name__)

ROWS_SQL = """
    SELECT c.*, s.root AS root
    FROM combos c JOIN sweeps s USING (sweep_id)
    WHERE TRUE
"""
"""Every stored row, tagged with its root, before any narrowing."""

SUMMARY_SQL = ROWS_SQL + " AND c.trades >= {min_trades} AND isfinite(c.profit_factor)"

STATISTICS = frozenset(stats.Summary.columns())
"""What a results row carries beside its parameters. Read from the class, never copied."""

NET_TO_DRAWDOWN = "net_to_drawdown"
"""Net P&L against the worst peak-to-trough that earned it -- Gate 4, and the ranking §M27.3
reads instead of profit factor."""

DERIVED = frozenset({NET_TO_DRAWDOWN})
"""Statistics :func:`load` computes from stored columns rather than reading, apart from :data:`STATISTICS`."""

UNFILTERED = "unfiltered"
"""The stratum every other one is read against, and the only name that names no dimension."""

SHARES = ("session_close_share", "ambiguous_share")
"""What every table carries beside its statistics, because a result is read wrong without them."""

EXIT_ORDER = tuple(trades.EXIT_REASONS.values())
"""Every exit reason a simulated leg can carry, in the simulator's own order rather than
alphabetically. Read out of :data:`nqbt.trades.EXIT_REASONS` so the two cannot drift apart."""

DECOMPOSITION = ("legs", "net", "bars_med")
"""What each exit reason contributes to a ranked row, beside :data:`SHARES`."""

RANKED_COLUMNS = [
    "root",
    "resolution",
    "variant",
    "stratum",
    "trades",
    "profit_factor",
    "net_pnl",
    "sharpe",
    *SHARES,
]
"""What the one ranking table names a configuration by. The shares are on it because it is the
only table here that picks rows rather than describing a distribution."""

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
"""Columns that say which run a row came from rather than which parameters it used, costs included."""


def ratio_to_drawdown(net_pnl: float, max_drawdown: float) -> float:
    """Return one summary's net P&L over its own worst peak-to-trough, undefined at no drawdown.

    Rank with :func:`rank`, never with ``nlargest`` directly.
    """
    if max_drawdown <= 0.0:
        return float("nan")

    return net_pnl / max_drawdown


def net_to_drawdown(frame: pd.DataFrame) -> pd.Series:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Apply :func:`ratio_to_drawdown` over a whole results frame.

    The same guard by a faster route -- ``load`` runs it over every stored row, so it is
    vectorised rather than applied. Pinned equal to the scalar, never re-derived.
    """
    drawdown = frame["max_drawdown"].where(frame["max_drawdown"] > 0.0)

    return frame["net_pnl"] / drawdown


def rank(frame: pd.DataFrame, top: int, by: str) -> pd.DataFrame:
    """Return the ``top`` highest rows on ``by``, after dropping the rows it is undefined on.

    ``DataFrame.nlargest`` pads its result with undefined rows rather than returning fewer;
    ``tests/test_campaign_report.py`` pins it.
    """
    return frame[frame[by].notna()].nlargest(top, by)


def narrowing(
    windows: Collection[str] | None = None,
    variants: Collection[str] | None = None,
    resolutions: Collection[int] | None = None,
    strata: Collection[str] | None = None,
) -> str:
    """Return the clauses that narrow a stored-row query to these windows, variants, resolutions and strata.

    Appended to a query that already has its ``WHERE``. A name holding a quote is refused rather
    than escaped.
    """
    clauses: list[str] = []
    for column, names in (('c."window"', windows), ("c.variant", variants), ("c.stratum", strata)):
        if names is None:
            continue

        if any("'" in name for name in names):
            msg: str = f"a {column} name holding a quote cannot be read: {sorted(names)}"
            raise ValueError(msg)

        quoted: list[str] = [f"'{name}'" for name in names]
        clauses.append(f"{column} IN ({', '.join(quoted) or 'NULL'})")

    if resolutions is not None:
        listed: list[str] = [str(int(minutes)) for minutes in resolutions]
        clauses.append(f"c.resolution IN ({', '.join(listed) or 'NULL'})")

    return "".join(f" AND {clause}" for clause in clauses)


def load(
    name: str,
    windows: list[str],
    *,
    variants: Collection[str] | None = None,
    resolutions: Collection[int] | None = None,
) -> pd.DataFrame:
    """Load every viable combination stored for one archetype, tagged with its root.

    Read for ``windows`` alone, and for ``variants`` and ``resolutions`` where they are given.
    """
    frame: pd.DataFrame = results.query(
        SUMMARY_SQL.format(min_trades=MIN_TRADES) + narrowing(windows, variants, resolutions),
        db_path=db_path(name),
    )
    frame[NET_TO_DRAWDOWN] = net_to_drawdown(frame)

    return frame[frame["window"].isin(windows)]


def load_trades(sweep_id: int, combo_id: int, path: Path) -> pd.DataFrame:
    """Load the stored log of one combination, empty when no log has been stored for it.

    Empty rather than raising, so a caller reading a whole shortlist can name every row that has
    no log.
    """
    if not path.exists():
        return pd.DataFrame()

    present: pd.DataFrame = results.query(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'trades'",
        path,
    )
    if present.empty:
        return pd.DataFrame()

    return results.query(
        f"SELECT * FROM trades WHERE sweep_id = {int(sweep_id)} AND combo_id = {int(combo_id)}",  # noqa: S608 - both are ints
        path,
    )


def log_key(row: pd.Series) -> tuple[int, int]:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the ``(sweep_id, combo_id)`` a configuration's log is filed under."""
    return int(row["sweep_id"]), int(row["combo_id"])


def stored_logs(rows: pd.DataFrame, path: Path) -> dict[tuple[int, int], pd.DataFrame]:
    """Load every shortlisted row's stored log, keyed by :func:`log_key`, absent where none was stored.

    Serves a stored log and one re-run by ``tools/campaign_swept.py`` through the same mapping.
    """
    return {log_key(row): load_trades(*log_key(row), path) for _, row in rows.iterrows()}


def parameter_columns(frame: pd.DataFrame) -> list[str]:
    """List the columns holding a parameter rather than a tag or a statistic.

    Shared with ``tools/campaign_holdout.py`` because both held their own copy of the predicate
    and a derived statistic would have been a parameter to one of them.
    """
    return [
        column
        for column in frame.columns
        if column not in TAGS and column not in STATISTICS and column not in DERIVED
    ]


def swept_axes(frame: pd.DataFrame) -> list[str]:
    """List the parameter columns that actually vary here, so a constant is never reported as an axis."""
    return [column for column in parameter_columns(frame) if frame[column].nunique(dropna=False) > 1]


def profile(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Return the combination count, profitable share and the profit-factor distribution, per group.

    The two share columns are here rather than optional because a coarse resolution and the
    final session phase are both read wrong without them -- :data:`SHARES`.
    """
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
            **{f"{share}_med": grouped[share].median() for share in SHARES if share in frame.columns},
        },
    ).reset_index()


def exit_decomposition(log: pd.DataFrame) -> dict[str, float]:
    """Return one stored log's leg count, net P&L and median bars held, per exit reason.

    Built on ``stats.leg_summary`` and defining no statistic of its own. A reason the log never
    took is absent rather than zero.
    """
    if log.empty:
        return {}

    decomposed: dict[str, float] = {}
    for reason in EXIT_ORDER:
        legs: pd.DataFrame = log[log["exit_reason"] == reason]
        if legs.empty:
            continue

        summary: dict[str, float] = stats.leg_summary(legs)
        decomposed[f"{reason}_legs"] = summary["legs"]
        decomposed[f"{reason}_net"] = summary["net_pnl"]
        decomposed[f"{reason}_bars_med"] = float(legs["bars_held"].median())

    return decomposed


def decompose_exits(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Return the exit decomposition of every row of ``frame``, aligned to its index.

    Blank for a row ``tools/campaign_shortlist.py`` has stored no log for, since a shortlist
    ranked here is not necessarily one whose logs were kept.
    """
    rows: list[dict[str, float]] = [
        exit_decomposition(load_trades(int(row["sweep_id"]), int(row["combo_id"]), path))
        for _, row in frame.iterrows()
    ]
    decomposed: pd.DataFrame = pd.DataFrame(rows, index=frame.index)
    order: list[str] = [f"{reason}_{field}" for reason in EXIT_ORDER for field in DECOMPOSITION]

    return decomposed[[column for column in order if column in decomposed.columns]]


def dimension_of(stratum: str) -> str:
    """Return which context dimension one stratum name cuts, ``unfiltered`` cutting none.

    Stratum names are ``<dimension>=<cell>``, and a cell may carry its own cut after an ``@`` --
    ``regime=DIRECTIONAL@n=20``, ``volume=HEAVY@per_bar_20 q=0.20/0.80``.
    """
    return stratum.split("=", 1)[0]


def dimensions(frame: pd.DataFrame) -> list[str]:
    """List every context dimension this frame holds strata for, unfiltered excluded."""
    found: set[str] = {dimension_of(str(name)) for name in frame["stratum"].unique()}

    return sorted(found - {UNFILTERED})


def in_dimension(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Return the rows cut by one dimension, whatever cell of it each carries."""
    return frame[frame["stratum"].map(lambda name: dimension_of(str(name)) == dimension)]


def dimension_influence(frame: pd.DataFrame) -> pd.DataFrame:
    """Measure how much of the profit-factor variance each dimension's cells explain, per resolution.

    Measured **within** a resolution, never pooled over them: bar size is the largest lever in
    the campaign (§M27), so a figure taken across resolutions reports that instead.
    """
    rows: list[dict[str, object]] = []
    for dimension in dimensions(frame):
        cut: pd.DataFrame = in_dimension(frame, dimension)
        for resolution, block in cut.groupby("resolution"):
            rows.append(
                {
                    "dimension": dimension,
                    "resolution": int(resolution),
                    "cells": int(block["stratum"].nunique()),
                    "eta2": eta_squared(block, "stratum"),
                    "pf_median": block["profit_factor"].median(),
                },
            )
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("eta2", ascending=False).reset_index(drop=True)


def eta_squared(frame: pd.DataFrame, axis: str, statistic: str = "profit_factor") -> float:
    """Return the share of ``statistic``'s variance the grouping by ``axis`` explains."""
    values = frame[statistic]
    grand: float = float(values.mean())
    total: float = float(((values - grand) ** 2).sum())
    if total <= 0.0:
        return 0.0

    groups = frame.groupby(axis, dropna=False)[statistic].agg(["count", "mean"])
    between: float = float((groups["count"] * (groups["mean"] - grand) ** 2).sum())

    return between / total


def axis_influence(frame: pd.DataFrame, axes: list[str]) -> pd.DataFrame:
    """Measure how much of the profit-factor variance each axis explains, largest first.

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
    show(
        "how much each context dimension's cells explain, within a resolution, eta^2",
        dimension_influence(frame),
    )
    for dimension in dimensions(frame):
        show(
            f"by {dimension} and resolution -- read {SHARES[0]} before the clock",
            profile(in_dimension(frame, dimension), ["stratum", "resolution"]),
        )

    unfiltered: pd.DataFrame = frame[frame["stratum"] == UNFILTERED]
    if frame["variant"].nunique() > 1:
        show("by variant, unfiltered only", profile(unfiltered, ["variant"]))

    show(
        "axis influence on profit factor, unfiltered, eta^2",
        axis_influence(unfiltered, [*swept_axes(unfiltered), "resolution", "root"]),
    )
    ranked: pd.DataFrame = frame.nlargest(5, "profit_factor")
    named: list[str] = [column for column in RANKED_COLUMNS if column in ranked.columns]
    decomposed: pd.DataFrame = decompose_exits(ranked, db_path(name))
    show(
        "top 5 by profit factor -- a statement about the sweep's size, not the strategy",
        pd.concat([ranked[named], decomposed], axis=1),
    )
    if decomposed.columns.empty:
        logger.info("  none of these has a stored log; tools/campaign_shortlist.py writes them")

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
