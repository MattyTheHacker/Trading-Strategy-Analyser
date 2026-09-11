"""Place a campaign shortlist's configurations against a matched random entry.

    ./.venv/Scripts/python.exe tools/campaign_null.py --strategy ElasticBand --root MNQ
    ./.venv/Scripts/python.exe tools/campaign_null.py --strategy InsideBar --variant narrow --top 12
    ./.venv/Scripts/python.exe tools/campaign_null.py --strategy OpeningRange --root MNQ NQ         --stratum volume=THIN regime=DIRECTIONAL --draw levels

A sweep can say which configuration has the highest profit factor. It cannot say whether the
**entry** earned it, because a bracket that suits the bars flatters a random entry just as much.
The matched null holds the signal count and the time-of-session distribution fixed and
randomises the day -- ``docs/roadmap.md`` §M7a and § "The method that does answer the question".

Rebuilds the parameter set from a stored ``combos`` row, so what is tested is exactly what the
sweep ranked. ``--top`` measures that many of them and reports **three rankings side by side**:
the observed statistic, the excess over each configuration's own null, and net-to-drawdown. They
can order a grid differently, and where they part the excess is the one to believe --
``docs/roadmap.md`` §M27.3.

**Not every archetype has a matched null, and one that does not exits 2 rather than 0.** An
entry whose trigger is a *level* fires on every bar the level exists, which leaves the matched
draw nothing to randomise -- ``docs/roadmap.md`` §M28.1. That is a gate that could not be run,
not a gate that passed, so it is reported as its own status the way ``formatting.cli``'s is.
Over a shortlist the status is reached only when **every** row was refused; a row refused
alongside rows that ran is reported as a refusal and carries no verdict.

**``--draw levels`` is the second arm, and it is the one such an entry can use.** It permutes
which session's range is traded instead of which day each signal lands on, so the signal itself
is held fixed -- ``docs/roadmap.md`` §M28.2. The two arms ask different questions and are not
interchangeable, which is why every measured row carries the ``draw`` it was produced under: a
table mixing them silently would be two nulls wearing one set of names.

**Several roots and several strata run as one stated family**, printed before the first cell
rather than counted afterwards. A p-value is only readable against how many tests it was one
of, and a cell chosen after a consistency score has already been looked at is the multiple-
comparisons load § "Standing traps" names -- ``docs/roadmap.md`` §M28.16.
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

from tools.campaign_report import NET_TO_DRAWDOWN, rank, ratio_to_drawdown, swept_axes
from tools.campaign_shortlist import rebuild, shortlist, source

from nqbt import archetypes, context, logsetup, randomentry, resample, splice, sweep
from nqbt.instruments import get_instrument

logger = logging.getLogger(__name__)

NO_NULL_AVAILABLE = 2
"""Exit status for an archetype the matched null cannot be drawn for at all.

Distinct from 0 so that "the gate did not run" cannot be read as "the gate passed" -- the same
reason ``formatting.cli`` separates its statuses.
"""

STATISTICS = ("profit_factor", "expectancy", "win_rate", "mean_r", "net_pnl", "max_drawdown")
"""What the observation is placed against. ``profit_factor`` and ``expectancy`` are the
verdict; ``win_rate`` is reported because a mean-reversion entry can beat the null on payoff
while losing on frequency -- ``docs/roadmap.md`` §M26.

The last two are here for :data:`~tools.campaign_report.NET_TO_DRAWDOWN` and cost almost
nothing: ``compare`` summarises the observation once and draws the null once, then reads a
column per statistic."""

RANKINGS = ("profit_factor", "expectancy_excess", NET_TO_DRAWDOWN)
"""The orders :func:`rankings` compares. Profit factor is here to be disagreed with rather than
to be believed -- ``docs/roadmap.md`` § "The method that does answer the question"."""

CELL_KEYS = ["root", "stratum"]
"""What one cell of a family run is. ``--resolution`` is fixed across a run rather than swept,
because bar size is the largest lever in the campaign and pooling two of them would be one
number over two populations -- ``docs/roadmap.md`` §M28.14."""

SIGNIFICANT = 0.05
"""The level :func:`family` counts configurations against. It is counted rather than concluded
from: a family of cells runs one test per configuration, so the count is read against how many
of them chance alone would put below it -- ``docs/roadmap.md`` § "Standing traps"."""


def label_of(row: pd.Series, axes: list[str]) -> str:  # type: ignore[type-arg]  # duckdb's dtypes
    """One configuration named by whatever actually varies across the shortlist."""
    if not axes:
        return f"sweep {int(row['sweep_id'])} combo {int(row['combo_id'])}"

    return " ".join(f"{axis}={row[axis]}" for axis in axes)


def measure_row(  # noqa: PLR0913 - each argument is a distinct axis of one measurement
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    label: str,
    iterations: int,
    n_jobs: int,
    draw: str = randomentry.OVER_BARS,
) -> dict[str, object]:
    """One configuration against its own matched null, or a row saying it was refused.

    Every measured column is the **test window's**, including net-to-drawdown; the stored row
    supplies the parameters and its own ranking-window figures stay out, so that one row is not
    two windows wearing one set of names.
    """
    params: archetypes.Params = rebuild(row, archetype)
    identity: dict[str, object] = {
        "label": label,
        # Carried so a stored table cannot mix the two arms silently: they ask different
        # questions -- ``docs/roadmap.md`` §M28.2.
        "draw": draw,
        "root": root,
        "stratum": row["stratum"],
        "resolution": int(row["resolution"]),
        "ranked_by": float(row[NET_TO_DRAWDOWN]),
        "stored_trades": int(row["trades"]),
    }
    try:
        placed: dict[str, randomentry.NullResult] = randomentry.compare(
            data,
            params,
            archetype,
            get_instrument(root),
            statistics=STATISTICS,
            iterations=iterations,
            n_jobs=n_jobs,
            draw=draw,
        )
    except randomentry.RandomEntryError as refused:
        logger.info("  %-44s REFUSED: %s", label, refused)

        return {**identity, "refused": str(refused)}

    measured: dict[str, object] = {**identity, "refused": None}
    for statistic, result in placed.items():
        measured[statistic] = result.observed
        measured[f"{statistic}_null"] = result.null_median
        measured[f"{statistic}_excess"] = result.observed - result.null_median
        measured[f"{statistic}_p"] = result.p_value
    measured["trades"] = placed[STATISTICS[0]].observed_trades
    measured["null_trades"] = placed[STATISTICS[0]].null_median_trades
    measured[NET_TO_DRAWDOWN] = ratio_to_drawdown(
        placed["net_pnl"].observed,
        placed["max_drawdown"].observed,
    )
    logger.info(
        "  %-44s PF %6.3f  null %6.3f  excess %+6.3f  n/dd %6.3f  %5d trades",
        label,
        measured["profit_factor"],
        measured["profit_factor_null"],
        measured["profit_factor_excess"],
        measured[NET_TO_DRAWDOWN],
        measured["trades"],
    )

    return measured


def measure(  # noqa: PLR0913 - each argument is a distinct axis of one measurement
    rows: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    test_window: str,
    iterations: int,
    n_jobs: int,
    draw: str = randomentry.OVER_BARS,
) -> pd.DataFrame:
    """Every shortlisted configuration against its own null, one row each.

    Grouped by resolution because the resample and the prepared dataset are the expensive parts,
    exactly as ``tools/campaign_shortlist.store_group`` groups them.
    """
    axes: list[str] = swept_axes(rows)
    tested: pd.DataFrame = source(splice.load_continuous(root), test_window)

    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        frame: pd.DataFrame = resample.resample(tested, int(minutes))
        rebuilt: list[tuple[pd.Series, archetypes.Params]] = [  # type: ignore[type-arg]  # duckdb's dtypes
            (row, rebuild(row, archetype)) for _, row in block.iterrows()
        ]
        spec: context.ContextSpec = context.ContextSpec()
        for _, params in rebuilt:
            spec = spec | sweep.Grid(base=params, archetype=archetype).required_context()
        data: context.Dataset = context.prepare(frame, spec, bar_minutes=int(minutes))

        measured.extend(
            measure_row(row, data, archetype, root, label_of(row, axes), iterations, n_jobs, draw)
            for row, _ in rebuilt
        )

    return pd.DataFrame(measured)


def rankings(table: pd.DataFrame) -> list[str]:
    """Which configuration each ranking picks, and whether they agree.

    The disagreement is the finding: a bracket that suits the bars raises the observed statistic
    and its null together, so the two orders part exactly where profit factor misleads.
    """
    ranked: pd.DataFrame = table[table["refused"].isna()]
    if ranked.empty:
        return ["  (nothing was measured)"]

    lines: list[str] = []
    picked: list[str] = []
    for statistic in RANKINGS:
        best: pd.DataFrame = rank(ranked, 1, statistic)
        if best.empty:
            lines.append(f"  best by {statistic:<18} (undefined on every row)")
            continue

        picked.append(str(best.iloc[0]["label"]))
        lines.append(f"  best by {statistic:<18} {best.iloc[0]['label']}")
    agree: str = "agree" if len(set(picked)) == 1 else "DISAGREE"
    lines.append(f"  the rankings {agree}")

    return lines


def family(table: pd.DataFrame) -> pd.DataFrame:
    """One row per cell of a family run: what it beat, how often, and at what p.

    The row is a range rather than a mean because ten configurations of one cell are ten
    overlapping runs over the same bars, so their spread is the honest summary and their
    average is not -- ``docs/roadmap.md`` §M28.16.
    """
    rows: list[dict[str, object]] = []
    for keys, block in table.groupby(CELL_KEYS, sort=False):
        cell: dict[str, object] = dict(zip(CELL_KEYS, keys, strict=True))
        measured: pd.DataFrame = block[block["refused"].isna()]
        if measured.empty:
            rows.append({**cell, "measured": 0, "refused": len(block)})
            continue

        rows.append(
            {
                **cell,
                "measured": len(measured),
                "refused": len(block) - len(measured),
                "trades_low": int(measured["trades"].min()),
                "trades_high": int(measured["trades"].max()),
                "profit_factor_low": measured["profit_factor"].min(),
                "profit_factor_high": measured["profit_factor"].max(),
                "null_low": measured["profit_factor_null"].min(),
                "null_high": measured["profit_factor_null"].max(),
                "excess_low": measured["profit_factor_excess"].min(),
                "excess_high": measured["profit_factor_excess"].max(),
                "beat_null": int((measured["profit_factor_excess"] > 0).sum()),
                "p_under_05": int((measured["profit_factor_p"] < SIGNIFICANT).sum()),
                "net_to_drawdown_low": measured[NET_TO_DRAWDOWN].min(),
                "net_to_drawdown_high": measured[NET_TO_DRAWDOWN].max(),
            }
        )

    return pd.DataFrame(rows)


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def cell(
    args: argparse.Namespace,
    archetype: archetypes.Archetype,
    root: str,
    stratum: str | None,
) -> pd.DataFrame:
    """One root x stratum cell of a family run, shortlisted and placed against its own null."""
    rows: pd.DataFrame = shortlist(
        args.strategy,
        root,
        args.window,
        args.by,
        args.top,
        stratum,
        args.resolution,
        args.variant,
    )
    logger.info("")
    logger.info(
        "%s on %s, stratum %s: %d of the top configurations ranked on %s by %s, tested on %s",
        args.strategy,
        root,
        stratum or "any",
        len(rows),
        "+".join(args.window),
        args.by,
        args.test_window,
    )

    return measure(
        rows,
        archetype,
        root,
        args.test_window,
        args.iterations,
        args.n_jobs,
        args.draw,
    )


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Matched-null test of a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", nargs="+", default=["MNQ"])
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored rows rank")
    parser.add_argument(
        "--test-window",
        default="full",
        choices=["full", "selection", "holdout"],
        help="which bars the null runs on; holdout after ranking on selection is the honest pair",
    )
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument(
        "--stratum",
        nargs="+",
        default=None,
        help="restrict the ranking to one stratum; several run as one stated family",
    )
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=1, help="how many configurations to place")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--n-jobs", type=int, default=8)
    parser.add_argument(
        "--draw",
        choices=list(randomentry.DRAWS),
        default=randomentry.OVER_BARS,
        help="what the null randomises; levels is for a trigger that is a level",
    )
    args = parser.parse_args(argv[1:])

    archetype: archetypes.Archetype = archetypes.get(args.strategy)
    strata: list[str | None] = args.stratum or [None]
    logger.info(
        "%s: %d root x stratum cells of at most %d configurations each -- the family every "
        "p-value below is one of",
        args.strategy,
        len(args.root) * len(strata),
        args.top,
    )

    table: pd.DataFrame = pd.concat(
        [cell(args, archetype, root, stratum) for root in args.root for stratum in strata],
        ignore_index=True,
    )
    refused: pd.DataFrame = table[table["refused"].notna()]
    if len(refused) == len(table):
        logger.info("")
        logger.info(
            "NO MATCHED NULL for %s over %s: %s",
            args.strategy,
            args.draw,
            table.iloc[0]["refused"],
        )

        return NO_NULL_AVAILABLE

    show("every configuration against its own null", table.drop(columns=["refused"]))
    if not refused.empty:
        logger.info("")
        logger.info(
            "%d of %d configurations were refused a null and carry no verdict", len(refused), len(table)
        )

    if len(args.root) * len(strata) > 1:
        show("the family, one row per cell", family(table))

    for keys, block in table.groupby(CELL_KEYS, sort=False):
        logger.info("")
        logger.info("--- the rankings for %s, side by side ---", ", ".join(str(key) for key in keys))
        for line in rankings(block):
            logger.info("%s", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
