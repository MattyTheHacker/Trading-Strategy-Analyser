"""Read a campaign shortlist's realised trades by the clock, and guard what that turns up.

    uv run tools/campaign_shortlist.py --strategy InsideBar --window holdout
    uv run tools/campaign_review.py --strategy InsideBar --window holdout

``tools/README.md`` § "campaign_review.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import annotate, context, guard, logsetup, resample, review, splice, timeofday, volume
from nqbt.instruments import get_instrument
from tools.campaign_report import load_trades
from tools.campaign_shortlist import shortlist, source
from tools.campaign_sweep import VOLUME_BASELINE_SESSIONS, VOLUME_ROLLING_BARS, db_path

logger = logging.getLogger(__name__)

VOLUME_STATE_PREFIX = "entry_volume_state_"
"""What :func:`nqbt.annotate.annotate_trades` calls a volume label at the entry bar."""

LABEL_COLUMNS = ["root", "resolution", "variant", "stratum", "window", "sweep_id", "combo_id"]
"""What names a configuration in the output, matching ``tools/campaign_montecarlo.py``'s so that
two reports of one shortlist can be read side by side."""

BY = "expectancy"
"""What a separation is measured in. Bounded by the largest win and defined where gross loss is
zero, which profit factor is not -- ``docs/findings/m27-registry-campaign.md``
§ "Reading the per-contract tally"."""


def volume_keys() -> tuple[volume.VolumeKey, ...]:
    """Return all three relative-volume series, so the clock is read against every form at once.

    The campaign swept one of them; which of the three a result belongs to is exactly what
    reading them side by side settles -- ``docs/roadmap.md`` §M27.8.
    """
    return tuple(
        volume.key(form, VOLUME_ROLLING_BARS, VOLUME_BASELINE_SESSIONS) for form in volume.VolumeForm
    )


def review_spec() -> context.ContextSpec:
    """Return what a review needs of a dataset: the clock, and every form of volume beside it."""
    return context.ContextSpec(needs_time_of_day=True, volume_keys=volume_keys())


def thresholds_for(row: pd.Series) -> annotate.LabelThresholds:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the cut this configuration ran at, so the review states the configuration's own cut.

    A review has to be able to say where it cut a raw series, and the honest answer here is
    already stored: it is what the sweep measured this row with.
    """
    return annotate.LabelThresholds(
        volume_thin_below=float(row["volume_thin_below"]),
        volume_heavy_above=float(row["volume_heavy_above"]),
    )


def conditions_of(annotation: annotate.Annotation) -> tuple[str, ...]:
    """Return the clock and the three volume labels: the family this tool screens.

    Named rather than taken from :func:`nqbt.review.stratifiable`, which would add every
    moving-average gate to the family.
    """
    volumes: tuple[str, ...] = tuple(
        name for name in annotation.conditions if name.startswith(VOLUME_STATE_PREFIX)
    )

    return (review.PHASE_COLUMN, *volumes)


def tolerance_for(row: pd.Series, root: str) -> float:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return how far a fill of this run may land outside its bar, which is the run's own slippage."""
    return float(row["slippage_ticks"]) * get_instrument(root).tick_size


def annotate_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    log: pd.DataFrame,
    data: context.Dataset,
    root: str,
) -> annotate.Annotation:
    """Join one stored log to the bars it was simulated over -- ``docs/roadmap.md`` §M11.2."""
    return annotate.annotate_trades(
        log,
        data,
        thresholds=thresholds_for(row),
        price_tolerance=tolerance_for(row, root),
    )


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the tag columns that say which stored configuration a result belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def review_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    path: Path,
    root: str,
    iterations: int,
) -> pd.DataFrame:
    """Print one configuration's clock table, with its guard beneath it.

    Returns the clock table alone: the guard is a report about a family rather than a row per
    stratum, so concatenating the two would produce a frame with two meanings.
    """
    log: pd.DataFrame = load_trades(int(row["sweep_id"]), int(row["combo_id"]), path)
    if log.empty:
        logger.warning(
            "  sweep %-4d combo %-6d has no stored log; run tools/campaign_shortlist.py first",
            int(row["sweep_id"]),
            int(row["combo_id"]),
        )

        return pd.DataFrame()

    try:
        annotation: annotate.Annotation = annotate_row(row, log, data, root)
    except annotate.AnnotationError as refused:
        logger.warning(
            "  sweep %-4d combo %-6d cannot be annotated: %s",
            int(row["sweep_id"]),
            int(row["combo_id"]),
            refused,
        )

        return pd.DataFrame()

    clock: pd.DataFrame = review.time_of_day(log, annotation)
    logger.info("")
    logger.info("=== %s ===", " ".join(f"{name}={value}" for name, value in labelled(row).items()))
    logger.info("%s", annotation)
    show(f"realised P&L by {review.PHASE_COLUMN}, in session order", clock.reset_index())
    # The note belongs to the final phase, and an archetype with a session-end guard of its own
    # never enters in it -- printing it regardless would attach a caveat to a row that is absent.
    if timeofday.FORCED_EXIT_PHASE.name.lower() in clock.index:
        logger.info("  %s", review.FORCED_EXIT_NOTE)

    guarded: guard.Guard = guard.guard(
        log,
        annotation,
        by=BY,
        conditions=conditions_of(annotation),
        iterations=iterations,
    )
    logger.info("")
    logger.info("%s", guarded)

    return clock.reset_index().assign(**labelled(row))  # type: ignore[arg-type]  # a stored row's tag values


def review_shortlist(
    name: str,
    rows: pd.DataFrame,
    root: str,
    iterations: int,
) -> pd.DataFrame:
    """Review every shortlisted configuration, one clock table each.

    Grouped by window and resolution because the resample and the prepared dataset are the
    expensive parts, exactly as ``tools/campaign_shortlist.store_group`` groups them.
    """
    path: Path = db_path(name)
    bars: pd.DataFrame = splice.load_continuous(root)
    tables: list[pd.DataFrame] = []
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[call-overload]  # a groupby key on an int column
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), bar_minutes)
        data: context.Dataset = context.prepare(frame, review_spec(), bar_minutes=bar_minutes)
        tables.extend(review_row(row, data, path, root, iterations) for _, row in block.iterrows())

    present: list[pd.DataFrame] = [table for table in tables if not table.empty]
    if not present:
        return pd.DataFrame()

    return pd.concat(present, ignore_index=True)


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str]) -> int:
    """Review the shortlist's trades by the clock and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Time-of-day review of a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["holdout"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=1, help="how many configurations to review")
    parser.add_argument("--iterations", type=int, default=guard.DEFAULT_ITERATIONS)
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = shortlist(
        args.strategy,
        args.root,
        args.window,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        args.variant,
    )
    logger.info(
        "%s on %s: %d configurations ranked on %s by %s",
        args.strategy,
        args.root,
        len(rows),
        "+".join(args.window),
        args.by,
    )

    reviewed: pd.DataFrame = review_shortlist(args.strategy, rows, args.root, args.iterations)
    if reviewed.empty:
        logger.warning("no stored trade logs for this shortlist; nothing to review")

        return 1

    if len(rows) > 1:
        logger.info("")
        logger.info("=" * 110)
        show(f"{args.strategy} {args.root} -- every reviewed configuration's clock", reviewed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
