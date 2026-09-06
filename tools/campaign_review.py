"""Read a campaign shortlist's realised trades by the clock, and guard what that turns up.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar --window holdout
    ./.venv/Scripts/python.exe tools/campaign_review.py --strategy InsideBar --window holdout

Filtering entries to a phase and re-running the grid answers *does this strategy work if it only
trades then*, which ``tools/campaign_sweep.py`` swept and ``tools/campaign_report.py`` reads. The
other question -- *when did these trades actually happen, and what was true when they did* -- is
:mod:`nqbt.review`'s, and no campaign tool asked it: the sweep discards its logs, so until
``tools/campaign_shortlist.py`` there was no per-trade vector to ask it of --
``docs/roadmap.md`` §M27.7.

Two things come out of one annotation, because they are two halves of one question:

- :func:`nqbt.review.time_of_day` in session order, with **both forms of volume beside it**.
  Relative volume says whether an hour was unusually busy and absolute volume says whether there
  was anything there to trade at all, which is the half a profit factor cannot see --
  ``docs/roadmap.md`` §M27.8. ``session_close_share`` is in the same table, because the forced
  flat makes a poor result late in the session the clock until that column says otherwise.
- :func:`nqbt.guard.guard` over the clock and the three volume labels together. A stratum picked
  by reading a table is the multiple-comparisons machine one level up, and
  :data:`nqbt.guard.FAMILY_COLUMN` is the number that answers it.

Reads the logs ``tools/campaign_shortlist.py`` stored, so run that first; a row with no log, or
one that cannot honestly be joined to its bars, is named and skipped rather than silently
dropped -- and the second of those is not hypothetical here, see :data:`SLIPPAGE_TOLERANCE`.
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

from tools.campaign_shortlist import load_trades, shortlist, source
from tools.campaign_sweep import VOLUME_BASELINE_SESSIONS, VOLUME_ROLLING_BARS, db_path

from nqbt import annotate, context, guard, logsetup, resample, review, splice, timeofday, volume
from nqbt.instruments import get_instrument

logger = logging.getLogger(__name__)

VOLUME_STATE_PREFIX = "entry_volume_state_"
"""What :func:`nqbt.annotate.annotate_trades` calls a volume label at the entry bar."""

LABEL_COLUMNS = ["root", "resolution", "variant", "stratum", "window", "sweep_id", "combo_id"]
"""What names a configuration in the output, matching ``tools/campaign_montecarlo.py``'s so that
two reports of one shortlist can be read side by side."""

BY = "expectancy"
"""What a separation is measured in. Bounded by the largest win and defined where gross loss is
zero, which profit factor is not -- ``docs/roadmap.md`` § "Reading the per-contract tally"."""

SLIPPAGE_TOLERANCE = -1.0
"""``--price-tolerance`` unset: take the run's own slippage, which is the documented default.

A simulated log is expected to land outside its bar by at most that, and on this project's own
shortlists it does not -- a profit target that a bar gapped through fills at the target price
and lands further out. Widen it deliberately and the widening is printed; do not raise it past
the point where a back-adjusted series would still be caught -- ``docs/roadmap.md`` §M27.7."""


def volume_keys() -> tuple[volume.VolumeKey, ...]:
    """All three relative-volume series, so the clock is read against every form at once.

    The campaign swept one of them; which of the three a result belongs to is exactly what
    reading them side by side settles -- ``docs/roadmap.md`` §M27.8.
    """
    return tuple(
        volume.key(form, VOLUME_ROLLING_BARS, VOLUME_BASELINE_SESSIONS) for form in volume.VolumeForm
    )


def review_spec() -> context.ContextSpec:
    """What a review needs of a dataset: the clock, and every form of volume beside it."""
    return context.ContextSpec(needs_time_of_day=True, volume_keys=volume_keys())


def thresholds_for(row: pd.Series) -> annotate.LabelThresholds:  # type: ignore[type-arg]  # duckdb's dtypes
    """The cut this configuration ran at, so the review states the configuration's own cut.

    A review has to be able to say where it cut a raw series, and the honest answer here is
    already stored: it is what the sweep measured this row with.
    """
    return annotate.LabelThresholds(
        volume_thin_below=float(row["volume_thin_below"]),
        volume_heavy_above=float(row["volume_heavy_above"]),
    )


def conditions_of(annotation: annotate.Annotation) -> tuple[str, ...]:
    """The clock and the three volume labels: the family this tool screens.

    Named rather than taken from :func:`nqbt.review.stratifiable`, which would put every
    moving-average gate in the same family and dilute the family-wise null with conditions
    nobody asked about.
    """
    volumes: tuple[str, ...] = tuple(
        name for name in annotation.conditions if name.startswith(VOLUME_STATE_PREFIX)
    )

    return (review.PHASE_COLUMN, *volumes)


def tolerance_for(row: pd.Series, root: str, given: float) -> float:  # type: ignore[type-arg]  # duckdb's dtypes
    """How far a fill of this run may land outside its bar: the run's slippage, or the override."""
    if given >= 0.0:
        return given

    return float(row["slippage_ticks"]) * get_instrument(root).tick_size


def annotate_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    log: pd.DataFrame,
    data: context.Dataset,
    root: str,
    tolerance: float,
) -> annotate.Annotation:
    """Join one stored log to the bars it was simulated over -- ``docs/roadmap.md`` §M11.2."""
    return annotate.annotate_trades(
        log,
        data,
        thresholds=thresholds_for(row),
        price_tolerance=tolerance_for(row, root, tolerance),
    )


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The tag columns that say which stored configuration a result belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def review_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    data: context.Dataset,
    path: Path,
    root: str,
    iterations: int,
    tolerance: float = SLIPPAGE_TOLERANCE,
) -> pd.DataFrame:
    """One configuration's clock table, printed with its guard beneath it.

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
        annotation: annotate.Annotation = annotate_row(row, log, data, root, tolerance)
    except annotate.AnnotationError as refused:
        logger.warning(
            "  sweep %-4d combo %-6d cannot be annotated at this tolerance: %s",
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

    return clock.reset_index().assign(**labelled(row))


def review_shortlist(
    name: str,
    rows: pd.DataFrame,
    root: str,
    iterations: int,
    tolerance: float = SLIPPAGE_TOLERANCE,
) -> pd.DataFrame:
    """Review every shortlisted configuration, one clock table each.

    Grouped by window and resolution because the resample and the prepared dataset are the
    expensive parts, exactly as ``tools/campaign_shortlist.store_group`` groups them.
    """
    path: Path = db_path(name)
    bars: pd.DataFrame = splice.load_continuous(root)
    tables: list[pd.DataFrame] = []
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), int(minutes))
        data: context.Dataset = context.prepare(frame, review_spec(), bar_minutes=int(minutes))
        tables.extend(review_row(row, data, path, root, iterations, tolerance) for _, row in block.iterrows())

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
    parser.add_argument(
        "--price-tolerance",
        type=float,
        default=SLIPPAGE_TOLERANCE,
        help="points a fill may land outside its bar; unset takes the run's own slippage",
    )
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

    if args.price_tolerance >= 0.0:
        logger.info("fills may land %.2f points outside their bar by request", args.price_tolerance)

    reviewed: pd.DataFrame = review_shortlist(
        args.strategy,
        rows,
        args.root,
        args.iterations,
        args.price_tolerance,
    )
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
