"""Place a campaign shortlist's configurations against a matched random entry.

    uv run tools/campaign_null.py --strategy ElasticBand --root MNQ
    uv run tools/campaign_null.py --strategy InsideBar --variant narrow --top 12
    uv run tools/campaign_null.py --strategy OpeningRange --root MNQ NQ \
        --stratum volume=THIN regime=DIRECTIONAL --draw levels --out or.parquet
    uv run tools/campaign_null.py --family-of or.parquet ibt.parquet

Exits 2 when no row could be placed against a null, so a gate that did not run is not read as
one that passed -- ``tools/README.md`` § "campaign_null.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, logsetup, randomentry, resample, results, splice, sweep
from nqbt.instruments import get_instrument
from tools.campaign_holdout import JOIN_KEYS
from tools.campaign_report import NET_TO_DRAWDOWN, narrowing, rank, ratio_to_drawdown, swept_axes
from tools.campaign_shortlist import rebuild, shortlist, source, verify
from tools.campaign_sweep import campaign_variant_names, db_path

if TYPE_CHECKING:
    from collections.abc import Collection

    from nqbt.arrays import FloatArray

logger = logging.getLogger(__name__)

NO_NULL_AVAILABLE = 2
"""Exit status for an archetype the matched null cannot be drawn for at all."""

STATISTICS = ("profit_factor", "expectancy", "win_rate", "mean_r", "net_pnl", "max_drawdown")
"""What the observation is placed against; ``profit_factor`` and ``expectancy`` are the verdict."""

RANKINGS = ("profit_factor", "expectancy_excess", NET_TO_DRAWDOWN)
"""The orders :func:`rankings` compares. Profit factor is here to be disagreed with rather than
to be believed -- ``docs/findings/m26-elastic-band.md`` § "The method that does answer the question"."""

CELL_KEYS = ["strategy", "root", "stratum"]
"""What one cell of a family run is. ``--resolution`` is fixed across a run rather than swept,
because bar size is the largest lever in the campaign and pooling two of them would be one
number over two populations -- ``docs/roadmap.md`` §M28.14."""

SAVED_CELL_KEYS = [*CELL_KEYS, "resolution"]
"""A cell of a family read from saved runs, which may each have fixed a different bar size."""

SIGNIFICANT = 0.05
"""The level :func:`family` counts configurations against. It is counted rather than concluded
from: a family of cells runs one test per configuration, so the count is read against how many
of them chance alone would put below it -- ``docs/roadmap.md`` § "Standing traps"."""

DRAWS_COLUMN = "profit_factor_draws"
"""Every null draw's profit factor, in seed order, which :func:`family_wise` reads."""

EXCESS_Z = "profit_factor_z"
FAMILY_P = "profit_factor_family_p"
"""The standardised excess and the family-wise p :func:`family_wise` adds to every measured row --
``docs/findings/m54-family-wise-null-preregistration.md``."""

TEST_KEYS = ["strategy", "sweep_id", "combo_id"]
"""What one test of a family is: its stored row, since a label names only what varies in one run."""

STORED_SQL = """
    SELECT c.sweep_id, c.combo_id, c.variant, c.stratum, c.resolution,
           c.trades, c.net_pnl, s.root, s.first_bar, s.last_bar
    FROM combos c JOIN sweeps s USING (sweep_id)
    WHERE c."window" = '{window}'
"""
"""What a re-run is checked against: one configuration's stored figures, and the bars its sweep ran on.

Not :func:`~tools.campaign_report.load`, which drops rows below
:data:`~tools.campaign_sweep.MIN_TRADES`.
"""


def stored_rows(
    name: str,
    root: str,
    window: str,
    *,
    variants: Collection[str] | None = None,
    resolutions: Collection[int] | None = None,
) -> pd.DataFrame:
    """Load every row one archetype stored for a root and window, with the bars its sweep ran on.

    Keyed by :data:`~tools.campaign_holdout.JOIN_KEYS`; a duplicate key is refused rather than
    picked between. ``variants`` and ``resolutions`` narrow what is read, where they are given.
    """
    frame: pd.DataFrame = results.query(
        STORED_SQL.format(window=window) + narrowing(variants=variants, resolutions=resolutions),
        db_path(name),
    )
    keyed: pd.DataFrame = frame[frame["root"] == root].set_index(JOIN_KEYS, drop=False)
    if keyed.index.has_duplicates:
        msg: str = (
            f"{name} on {root}: the {window} window stores more than one row under the same "
            f"{JOIN_KEYS}, so a re-run cannot be checked against any of them"
        )
        raise RuntimeError(msg)

    return keyed


def stored_for(stored: pd.DataFrame, row: pd.Series) -> pd.Series | None:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the stored row of one configuration in the window the null runs on, or ``None``.

    ``None`` where that window never swept it, which :func:`verify_bars` reports rather than
    taking for agreement.
    """
    key: tuple[object, ...] = tuple(row[column] for column in JOIN_KEYS)
    if key not in stored.index:
        return None

    return stored.loc[key]  # type: ignore[index]  # a row's join key


def _naive(when: pd.Timestamp) -> pd.Timestamp:
    """Strip one bar stamp of its zone, which is how :func:`nqbt.results.save_sweep` stores it."""
    if when.tz is None:
        return when

    return when.tz_localize(None)


def series_moved(reference: pd.Series, frame: pd.DataFrame) -> str:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Report which ends of the series a stored sweep ran on have moved, empty where neither has."""
    ends: list[str] = [
        f"{end} bar was {stored}, now {current}"
        for end, stored, current in (
            ("first", reference["first_bar"], _naive(frame.index[0])),
            ("last", reference["last_bar"], _naive(frame.index[-1])),
        )
        if pd.Timestamp(stored) != current
    ]

    return "; ".join(ends)


def verify_bars(  # type: ignore[explicit-any]  # duckdb's dtypes
    reference: pd.Series | None,
    frame: pd.DataFrame,
    label: str,
    window: str,
) -> None:
    """Refuse a re-run whose bars are not the ones the stored row was swept on."""
    if reference is None:
        logger.warning("  %-44s no stored %s row, so the re-run is unchecked", label, window)

        return

    moved: str = series_moved(reference, frame)
    if not moved:
        return

    msg: str = (
        f"{label} was swept on a different series: {moved}. Re-sweep the campaign before "
        f"reading a null off its stored rows"
    )
    raise RuntimeError(msg)


def verify_observation(  # type: ignore[explicit-any]  # duckdb's dtypes
    reference: pd.Series | None,
    measured: dict[str, object],
) -> None:
    """Refuse an observation that did not reproduce the row the sweep stored for these bars.

    ``tools/campaign_shortlist.py``'s ``verify`` is the predicate, so the two tools agree on
    what reproducing means.
    """
    if reference is None or measured["refused"] is not None:
        return

    verify(reference, measured)


def label_of(row: pd.Series, axes: list[str]) -> str:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Name one configuration by whatever actually varies across the shortlist."""
    if not axes:
        return f"sweep {int(row['sweep_id'])} combo {int(row['combo_id'])}"

    return " ".join(f"{axis}={row[axis]}" for axis in axes)


def measure_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    label: str,
    iterations: int,
    n_jobs: int,
    draw: str = randomentry.OVER_BARS,
) -> dict[str, object]:
    """Measure one configuration against its own matched null, or return a row saying it was refused.

    Every measured column is the test window's, including net-to-drawdown.
    """
    params: archetypes.Params = rebuild(row, archetype)
    identity: dict[str, object] = {
        "label": label,
        "sweep_id": int(row["sweep_id"]),
        "combo_id": int(row["combo_id"]),
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
    measured[DRAWS_COLUMN] = placed["profit_factor"].draws
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


def measure(
    rows: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    test_window: str,
    iterations: int,
    n_jobs: int,
    draw: str = randomentry.OVER_BARS,
) -> pd.DataFrame:
    """Measure every shortlisted configuration against its own null, one row each.

    Each configuration is checked against what the test window stored for it --
    :func:`verify_bars` and :func:`verify_observation`.
    """
    axes: list[str] = swept_axes(rows)
    tested: pd.DataFrame = source(splice.load_continuous(root), test_window)
    stored: pd.DataFrame = stored_rows(archetype.name, root, test_window)

    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[arg-type]  # a groupby key on an int column
        frame: pd.DataFrame = resample.resample(tested, bar_minutes)
        rebuilt = [(row, rebuild(row, archetype)) for _, row in block.iterrows()]
        for row, _ in rebuilt:
            verify_bars(stored_for(stored, row), frame, label_of(row, axes), test_window)

        spec: context.ContextSpec = context.ContextSpec()
        for _, params in rebuilt:
            spec = spec | sweep.Grid(base=params, archetype=archetype).required_context()
        data: context.Dataset = context.prepare(
            frame,
            spec,
            bar_minutes=bar_minutes,
            price_basis=context.PriceBasis.RAW,
        )

        for row, _ in rebuilt:
            result: dict[str, object] = measure_row(
                row,
                data,
                archetype,
                root,
                label_of(row, axes),
                iterations,
                n_jobs,
                draw,
            )
            verify_observation(stored_for(stored, row), result)
            measured.append({"strategy": archetype.name, "test_window": test_window, **result})

    return pd.DataFrame(measured)


def rankings(table: pd.DataFrame) -> list[str]:
    """Report which configuration each ranking picks, and whether they agree.

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


def family(table: pd.DataFrame, keys: list[str] = CELL_KEYS) -> pd.DataFrame:
    """Return one row per cell of a family run: what it beat, how often, and at what p.

    The row is a range rather than a mean -- ``docs/roadmap.md`` §M28.16.
    """
    rows: list[dict[str, object]] = []
    for values, block in table.groupby(keys, sort=False):
        cell: dict[str, object] = dict(zip(keys, values, strict=True))
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
                **({"family_p_low": measured[FAMILY_P].min()} if FAMILY_P in measured else {}),
                "net_to_drawdown_low": measured[NET_TO_DRAWDOWN].min(),
                "net_to_drawdown_high": measured[NET_TO_DRAWDOWN].max(),
            }
        )

    return pd.DataFrame(rows)


def family_wise(table: pd.DataFrame) -> pd.DataFrame:
    """Return ``table`` with every measured row's standardised excess and family-wise p added.

    The family is every measured row, whichever cell or run it came from. A refused row carries
    neither, and nor does a row whose null has no spread, which is named and left out --
    ``docs/findings/m54-family-wise-null-preregistration.md``.
    """
    widened: pd.DataFrame = table.assign(**{EXCESS_Z: np.nan, FAMILY_P: np.nan})
    measured: pd.DataFrame = table[table["refused"].isna()]
    if measured.empty:
        return widened

    refuse_a_mixed_family(measured)
    standardised: dict[object, tuple[float, FloatArray]] = {}
    for index, row in measured.iterrows():
        try:
            standardised[index] = randomentry.standardised_excess(
                float(row["profit_factor"]), np.asarray(row[DRAWS_COLUMN], dtype=float)
            )
        except randomentry.RandomEntryError as refused:
            logger.warning(
                "%s %s %s %s is left out of the family: %s", *row[CELL_KEYS], row["label"], refused
            )

    if not standardised:
        return widened

    rows: list[object] = list(standardised)
    observed_z: FloatArray = np.array([standardised[index][0] for index in rows])
    widened.loc[rows, EXCESS_Z] = observed_z
    widened.loc[rows, FAMILY_P] = randomentry.family_wise_p(
        observed_z, np.vstack([standardised[index][1] for index in rows])
    )

    return widened


def refuse_a_mixed_family(measured: pd.DataFrame) -> None:
    """Refuse a family that repeats a test, mixes test windows, or holds draws that do not line up."""
    duplicated: pd.DataFrame = measured[measured.duplicated(TEST_KEYS, keep=False)]
    if not duplicated.empty:
        msg: str = (
            f"{len(duplicated)} rows repeat a test, so the family would count them twice: "
            f"{duplicated[TEST_KEYS].to_dict('records')}"
        )
        raise RuntimeError(msg)

    for column, what in (("test_window", "tested on"), ("ranked_on", "ranked on")):
        windows: list[str] = sorted(measured[column].unique())
        if len(windows) > 1:
            msg = f"the rows were {what} {windows}, which are different questions and not one family"
            raise RuntimeError(msg)

    draw_counts: set[int] = {len(draws) for draws in measured[DRAWS_COLUMN]}
    if len(draw_counts) > 1:
        msg = f"the rows were drawn {sorted(draw_counts)} times, so their draws do not line up one to one"
        raise RuntimeError(msg)


def printable(table: pd.DataFrame) -> pd.DataFrame:
    """Return ``table`` without the columns no one reads off a screen: the refusal text and the draws."""
    return table.drop(columns=["refused", DRAWS_COLUMN], errors="ignore")


def family_headline(table: pd.DataFrame) -> str:
    """Name the family's best test, its family-wise p, and how many tests that p was taken over."""
    measured: pd.DataFrame = table[table[FAMILY_P].notna()]
    if measured.empty:
        return "nothing was measured, so there is no family-wise p"

    best = measured.sort_values([FAMILY_P, EXCESS_Z], ascending=[True, False], kind="stable").iloc[0]

    return (
        f"the best of {len(measured)} tests is {best['strategy']} {best['root']} {best['stratum']} "
        f"{best['label']}, at a one-sided family-wise p of {best[FAMILY_P]:.3f} "
        f"(its own two-sided p: {best['profit_factor_p']:.3f})"
    )


def read_family(paths: list[Path]) -> int:
    """Read saved tables as one family, report it, and return the process exit code."""
    table: pd.DataFrame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    if table["refused"].notna().all():
        logger.info("NO MATCHED NULL in any of %d tables", len(paths))

        return NO_NULL_AVAILABLE

    table = family_wise(table)
    show("every configuration against the best of every draw", printable(table.sort_values(FAMILY_P)))
    show("the family, one row per cell", family(table, SAVED_CELL_KEYS))
    logger.info("")
    logger.info("%s", family_headline(table))
    if table[FAMILY_P].isna().all():
        return NO_NULL_AVAILABLE

    return 0


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
    """Shortlist one root x stratum cell of a family run and place it against its own null."""
    rows: pd.DataFrame = shortlist(
        args.strategy,
        root,
        args.window,
        args.by,
        args.top,
        stratum,
        args.resolution,
        campaign_variant_names(args.strategy) if args.campaign_only else args.variant,
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

    measured: pd.DataFrame = measure(
        rows,
        archetype,
        root,
        args.test_window,
        args.iterations,
        args.n_jobs,
        args.draw,
    )

    return measured.assign(ranked_on="+".join(args.window))


def parse(argv: list[str]) -> argparse.Namespace:
    """Read the command line, refusing options that contradict each other before anything runs."""
    parser = argparse.ArgumentParser(description="Matched-null test of a campaign shortlist.")
    parser.add_argument("--strategy", help="the archetype to measure; required unless --family-of is given")
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
    parser.add_argument(
        "--campaign-only",
        action="store_true",
        help="rank only the archetype's own campaign variants, not later sets sharing a stratum name",
    )
    parser.add_argument("--top", type=int, default=1, help="how many configurations to place")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--n-jobs", type=int, default=8)
    parser.add_argument(
        "--draw",
        choices=list(randomentry.DRAWS),
        default=randomentry.OVER_BARS,
        help="what the null randomises; levels is for a trigger that is a level",
    )
    parser.add_argument("--out", type=Path, default=None, help="save the measured table, draws included")
    parser.add_argument(
        "--family-of",
        nargs="+",
        type=Path,
        default=None,
        help="read tables saved with --out as one family instead of measuring",
    )
    args = parser.parse_args(argv[1:])
    if args.family_of and (args.strategy or args.out):
        parser.error("--family-of reads saved tables; it takes no --strategy and writes no --out")

    if args.family_of:
        return args

    if args.strategy is None:
        parser.error("--strategy is required unless --family-of is given")

    if args.campaign_only and args.variant is not None:
        parser.error("--campaign-only and --variant each choose the variants; give one")

    for option, values in (("--root", args.root), ("--stratum", args.stratum or [])):
        if len(set(values)) < len(values):
            parser.error(f"{option} names a value twice, which would measure one cell twice")

    return args


def main(argv: list[str]) -> int:
    """Compare the shortlist against a matched random entry and return the process exit code."""
    logsetup.configure(__name__)
    args: argparse.Namespace = parse(argv)
    if args.family_of:
        return read_family(args.family_of)

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
    if args.out is not None:
        table.to_parquet(args.out, index=False)
        logger.info("saved the measured table to %s", args.out)

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

    table = family_wise(table)
    show("every configuration against its own null", printable(table))
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

    logger.info("")
    logger.info("%s", family_headline(table))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
