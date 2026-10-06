"""Annotate a campaign shortlist's stored trade logs and persist them, so filtering is a query.

    uv run tools/campaign_shortlist.py --strategy OpeningRange --root MNQ
    uv run tools/campaign_annotate.py  --strategy OpeningRange --root MNQ

``tools/README.md`` § "campaign_annotate.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import annotate, archetypes, context, logsetup, resample, results, splice, sweep
from tools.campaign_report import load_trades
from tools.campaign_review import SLIPPAGE_TOLERANCE, review_spec, tolerance_for
from tools.campaign_shortlist import rebuild, shortlist, source
from tools.campaign_sweep import db_path

logger = logging.getLogger(__name__)


def thresholds_for(row: pd.Series) -> annotate.LabelThresholds:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return every cut this configuration ran at, read off its stored row by name."""
    given: dict[str, float | int] = {}
    for field in fields(annotate.LabelThresholds):
        if field.name not in row.index or pd.isna(row[field.name]):
            continue

        given[field.name] = int(row[field.name]) if "agreement" in field.name else float(row[field.name])

    return annotate.LabelThresholds(**given)  # type: ignore[arg-type]  # each key is a field of it


def annotation_spec(block: pd.DataFrame, archetype: archetypes.Archetype) -> context.ContextSpec:
    """Return every series these configurations read, plus the clock and volume a review wants beside it.

    The union is what lets one prepared dataset serve a whole block, exactly as
    ``tools/campaign_shortlist.store_group`` builds one for the re-run.
    """
    spec: context.ContextSpec = review_spec()
    for _, row in block.iterrows():
        spec = spec | sweep.Grid(base=rebuild(row, archetype), archetype=archetype).required_context()

    return spec


def store_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    path: Path,
    root: str,
    tolerance: float,
) -> bool:
    """Annotate one stored log and persist it, reporting whether it went."""
    sweep_id, combo_id = int(row["sweep_id"]), int(row["combo_id"])
    log: pd.DataFrame = load_trades(sweep_id, combo_id, path)
    if log.empty:
        logger.warning(
            "  sweep %-4d combo %-6d has no stored log; run tools/campaign_shortlist.py first",
            sweep_id,
            combo_id,
        )

        return False

    thresholds: annotate.LabelThresholds = thresholds_for(row)
    try:
        annotation: annotate.Annotation = annotate.annotate_trades(
            log,
            data,
            thresholds=thresholds,
            price_tolerance=tolerance_for(row, root, tolerance),
        )
    except annotate.AnnotationError as refused:
        logger.warning(
            "  sweep %-4d combo %-6d cannot be annotated at this tolerance: %s",
            sweep_id,
            combo_id,
            refused,
        )

        return False

    results.save_annotation(
        annotation.frame,
        sweep_id,
        combo_id,
        {field.name: getattr(thresholds, field.name) for field in fields(thresholds)},
        path,
        replace=True,
    )
    logger.info(
        "  sweep %-4d combo %-6d %-9s %-24s %s",
        sweep_id,
        combo_id,
        str(row["window"]),
        str(row["stratum"]),
        annotation,
    )

    return True


def store_annotations(
    name: str,
    rows: pd.DataFrame,
    root: str,
    tolerance: float = SLIPPAGE_TOLERANCE,
) -> int:
    """Annotate and store every shortlisted configuration's log, returning how many went.

    Grouped by window and resolution because the resample and the prepared dataset are the
    expensive parts, and every row sharing those two shares both.
    """
    archetype: archetypes.Archetype = archetypes.get(name)
    path: Path = db_path(name)
    bars: pd.DataFrame = splice.load_continuous(root)
    stored: int = 0
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[call-overload]  # a groupby key on an int column
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), bar_minutes)
        data: context.Dataset = context.prepare(
            frame,
            annotation_spec(block, archetype),
            bar_minutes=bar_minutes,
        )
        stored += sum(store_row(row, data, path, root, tolerance) for _, row in block.iterrows())

    return stored


def main(argv: list[str]) -> int:
    """Annotate and store the shortlist's trade logs and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Store a campaign shortlist's per-trade context.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=20, help="how many configurations to annotate")
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
    logger.info("%s on %s: annotating %d stored configurations", args.strategy, args.root, len(rows))
    if args.price_tolerance >= 0.0:
        logger.info("fills may land %.2f points outside their bar by request", args.price_tolerance)

    stored: int = store_annotations(args.strategy, rows, args.root, args.price_tolerance)
    if not stored:
        logger.warning("nothing annotated; run tools/campaign_shortlist.py for these rows first")

        return 1

    path: Path = db_path(args.strategy)
    results.create_trade_view(path)
    logger.info("")
    logger.info("%d annotation(s) stored; %s is ready in %s", stored, results.TRADE_VIEW, path)
    logger.info(
        "  example: SELECT * FROM %s WHERE entry_trend_20_50_1 = 'up' AND net_pnl > 0",
        results.TRADE_VIEW,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
