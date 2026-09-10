"""Read the campaign databases and say which archetype is worth improving.

    ./.venv/Scripts/python.exe tools/campaign_report.py
    ./.venv/Scripts/python.exe tools/campaign_report.py --window selection holdout

Reports **distributions, not winners**. The best profit factor in a 300,000-row sweep is a
statement about the size of the sweep; the median and the profitable share are statements about
the strategy -- ``docs/roadmap.md`` § "Selecting on one contract is worse than not selecting".

**Every stored stratum is read, one dimension at a time.** §M27 swept twenty strata and reported
one pooled row per stratum, which is how session phase and relative volume went into the campaign
and no finding about either came out -- ``docs/roadmap.md`` §M27.7 and §M27.8. A cell is only
comparable within a resolution, so the dimension tables are cut by it rather than pooled over it,
and :data:`SHARES` travels with every table.

**Pooled over variants deliberately, which is why there is no ``--variant`` here.** The dilution
§M28.9 measured is a *selection* effect and this tool selects nothing; the mixture is the thing
the dimension tables exist to describe, and a variant is read on its own in the ``by variant``
table below -- ``docs/roadmap.md`` §M28.9.

**The one table that ranks carries what its exits were worth**, wherever
``tools/campaign_shortlist.py`` has stored the log. ``session_close_share`` says how often the
flatten took a leg and never what that leg returned, and on the survivor the two answers point
opposite ways -- ``docs/roadmap.md`` §M28.9, "The bracket is a net cost, which
``session_close_share`` cannot say". §M28.12 reads the column across the registry, where it
does not say the same thing twice.

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

from nqbt import logsetup, results, stats, trades

logger = logging.getLogger(__name__)

SUMMARY_SQL = """
    SELECT c.*, s.root AS root
    FROM combos c JOIN sweeps s USING (sweep_id)
    WHERE c.trades >= {min_trades} AND isfinite(c.profit_factor)
"""

STATISTICS = frozenset(stats.Summary.columns())
"""What a results row carries beside its parameters. Read from the class, never copied."""

NET_TO_DRAWDOWN = "net_to_drawdown"
"""Net P&L against the worst peak-to-trough that earned it -- Gate 4, and the ranking §M27.3
reads instead of profit factor."""

DERIVED = frozenset({NET_TO_DRAWDOWN})
"""Statistics :func:`load` computes from stored columns rather than reading.

Separate from :data:`STATISTICS` so that one stays exactly ``stats.Summary``'s fields, and
listed at all because :func:`parameter_columns` would otherwise call a derived statistic an
axis."""

UNFILTERED = "unfiltered"
"""The stratum every other one is read against, and the only name that names no dimension."""

SHARES = ("session_close_share", "ambiguous_share")
"""What every table carries beside its statistics, because a result is read wrong without them.

The final session phase holds the forced flat, so a stratification by the clock will always show
it as anomalous and ``session_close_share`` is what tells the two apart -- ``docs/roadmap.md``
§M10.4. ``ambiguous_share`` is the same obligation at a coarse resolution."""

EXIT_ORDER = tuple(trades.EXIT_REASONS.values())
"""Every exit reason a simulated leg can carry, in the simulator's own order rather than
alphabetically. Read out of :data:`nqbt.trades.EXIT_REASONS` so the two cannot drift apart."""

DECOMPOSITION = ("legs", "net", "bars_med")
"""What each exit reason contributes to a ranked row, beside :data:`SHARES`.

A share says how often a leg left by one route and never what that route was worth, and on the
opening range the two point opposite ways -- ``docs/roadmap.md`` §M28.9, "The bracket is a net
cost, which ``session_close_share`` cannot say"."""

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
"""Columns that say which run a row came from rather than which parameters it used.

The two cost fields are here because they vary with the root and nothing else, so reporting
them as axes would report the root twice under a name that hides it."""


def ratio_to_drawdown(net_pnl: float, max_drawdown: float) -> float:
    """One summary's net P&L over its own worst peak-to-trough, undefined at no drawdown.

    Undefined rather than infinite, because an unbounded statistic wins a ranking it was never
    measured on -- the defect ``docs/roadmap.md`` § "Reading the per-contract tally" records
    against profit factor. Rank with :func:`rank`, never with ``nlargest`` directly.
    """
    if max_drawdown <= 0.0:
        return float("nan")

    return net_pnl / max_drawdown


def net_to_drawdown(frame: pd.DataFrame) -> pd.Series:  # type: ignore[type-arg]  # duckdb's dtypes
    """:func:`ratio_to_drawdown` over a whole results frame.

    The same guard by a faster route -- ``load`` runs it over every stored row, so it is
    vectorised rather than applied. Pinned equal to the scalar, never re-derived.
    """
    drawdown: pd.Series = frame["max_drawdown"].where(frame["max_drawdown"] > 0.0)  # type: ignore[type-arg]  # duckdb's dtypes

    return frame["net_pnl"] / drawdown


def rank(frame: pd.DataFrame, top: int, by: str) -> pd.DataFrame:
    """The ``top`` highest rows on ``by``, after dropping the rows it is undefined on.

    **``DataFrame.nlargest`` pads its result with undefined rows rather than returning fewer**,
    so ranking a shortlist straight through it hands the null test and the per-contract step
    configurations whose ranking statistic was never measured. Measured, not assumed:
    ``tests/test_campaign_report.py`` pins it.
    """
    return frame[frame[by].notna()].nlargest(top, by)


def load(name: str, windows: list[str]) -> pd.DataFrame:
    """Every viable combination stored for one archetype, tagged with its root."""
    frame: pd.DataFrame = results.query(
        SUMMARY_SQL.format(min_trades=MIN_TRADES),
        db_path=db_path(name),
    )
    frame[NET_TO_DRAWDOWN] = net_to_drawdown(frame)

    return frame[frame["window"].isin(windows)]


def load_trades(sweep_id: int, combo_id: int, path: Path) -> pd.DataFrame:
    """The stored log of one combination, empty when no log has been stored for it.

    ``tools/campaign_shortlist.py`` writes them and only for the rows it was pointed at. Empty
    rather than raising, so a caller reading a whole shortlist can name the rows that have no
    log instead of stopping at the first one.
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


def parameter_columns(frame: pd.DataFrame) -> list[str]:
    """Columns holding a parameter rather than a tag or a statistic.

    Shared with ``tools/campaign_holdout.py`` because both held their own copy of the predicate
    and a derived statistic would have been a parameter to one of them.
    """
    return [
        column
        for column in frame.columns
        if column not in TAGS and column not in STATISTICS and column not in DERIVED
    ]


def swept_axes(frame: pd.DataFrame) -> list[str]:
    """Parameter columns that actually vary here, so a constant is never reported as an axis."""
    return [column for column in parameter_columns(frame) if frame[column].nunique(dropna=False) > 1]


def profile(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Combination count, profitable share and the profit-factor distribution, per group.

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
    """One stored log's leg count, net P&L and median bars held, per exit reason.

    ``stats.leg_summary`` supplies the first two, so this reads a summary over subsets and
    defines no statistic of its own -- ``docs/roadmap.md`` §M28.9, "The bracket is a net cost,
    which ``session_close_share`` cannot say". An exit reason the log never took is absent
    rather than zero.
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
    """The exit decomposition of every row of ``frame``, aligned to its index.

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
    """Which context dimension one stratum name cuts, ``unfiltered`` cutting none.

    Stratum names are ``<dimension>=<cell>``, and a cell may carry its own cut after an ``@`` --
    ``regime=DIRECTIONAL@n=20``, ``volume=HEAVY@per_bar_20 q=0.20/0.80``.
    """
    return stratum.split("=", 1)[0]


def dimensions(frame: pd.DataFrame) -> list[str]:
    """Every context dimension this frame holds strata for, unfiltered excluded."""
    found: set[str] = {dimension_of(str(name)) for name in frame["stratum"].unique()}

    return sorted(found - {UNFILTERED})


def in_dimension(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """The rows cut by one dimension, whatever cell of it each carries."""
    return frame[frame["stratum"].map(lambda name: dimension_of(str(name)) == dimension)]


def dimension_influence(frame: pd.DataFrame) -> pd.DataFrame:
    """How much of the profit-factor variance each dimension's cells explain, per resolution.

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
                    "resolution": int(resolution),  # type: ignore[call-overload]  # duckdb's dtypes
                    "cells": int(block["stratum"].nunique()),
                    "eta2": eta_squared(block, "stratum"),
                    "pf_median": block["profit_factor"].median(),
                },
            )
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("eta2", ascending=False).reset_index(drop=True)


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
