"""Annotate a campaign shortlist's stored trade logs and persist them, so filtering is a query.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --root MNQ
    ./.venv/Scripts/python.exe tools/campaign_annotate.py  --strategy OpeningRange --root MNQ

``tools/campaign_review.py`` annotates the same logs and throws the annotation away, because it
asks one question of it and prints the answer. This stores it instead, keyed by the
``(sweep_id, combo_id, trade_id)`` the trade log already carries, and builds
:data:`nqbt.results.TRADE_VIEW` over the three tables -- after which "which trades were
profitable, taken in an uptrend, by a configuration on a 20-period EMA" is one ``SELECT``
rather than a Python session.

**The parameters come along as a filter and never as a ranking.** Two combinations differing in
one axis share most of their entries, so grouping the view's rows by a parameter counts the same
trade many times and would make :mod:`nqbt.guard`'s null far too tight;
``tools/campaign_report.py``'s ``axis_influence`` is where that comparison belongs.

Reads what ``tools/campaign_shortlist.py`` stored, so run that first. A row with no log, or one
that cannot honestly be joined to its bars, is named and skipped rather than silently dropped --
and the second is not hypothetical, see :data:`nqbt.annotate.annotate_trades`' price check.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_review import SLIPPAGE_TOLERANCE, review_spec, tolerance_for
from tools.campaign_shortlist import load_trades, rebuild, shortlist, source
from tools.campaign_sweep import db_path

from nqbt import annotate, archetypes, context, logsetup, resample, results, splice, sweep

logger = logging.getLogger(__name__)


def thresholds_for(row: pd.Series) -> annotate.LabelThresholds:  # type: ignore[type-arg]  # duckdb's dtypes
    """Every cut this configuration ran at, read off its stored row by name.

    :class:`nqbt.annotate.LabelThresholds`' fields and ``ContextFilterParams``' threshold
    parameters are the same words, so a pair added to one flows through here without a change.

    **A stored threshold is the configuration's cut, not a chosen one.** Where its filter was
    inert the pair is the params-class default that nobody picked, and a raw pair is a different
    share of bars at every form and resolution -- ``docs/roadmap.md`` §M27.8. That is why
    :func:`nqbt.results.save_annotation` stamps the pair onto every row it writes rather than
    leaving it to be remembered.
    """
    given: dict[str, float | int] = {}
    for field in fields(annotate.LabelThresholds):
        if field.name not in row.index or pd.isna(row[field.name]):
            continue

        given[field.name] = int(row[field.name]) if "agreement" in field.name else float(row[field.name])

    return annotate.LabelThresholds(**given)  # type: ignore[arg-type]  # each key is a field of it


def annotation_spec(block: pd.DataFrame, archetype: archetypes.Archetype) -> context.ContextSpec:
    """Every series these configurations read, plus the clock and volume a review wants beside it.

    The union is what lets one prepared dataset serve a whole block, exactly as
    ``tools/campaign_shortlist.store_group`` builds one for the re-run.
    """
    spec: context.ContextSpec = review_spec()
    for _, row in block.iterrows():
        spec = spec | sweep.Grid(base=rebuild(row, archetype), archetype=archetype).required_context()

    return spec


def store_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
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
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), int(minutes))
        data: context.Dataset = context.prepare(
            frame,
            annotation_spec(block, archetype),
            bar_minutes=int(minutes),
        )
        stored += sum(store_row(row, data, path, root, tolerance) for _, row in block.iterrows())

    return stored


def main(argv: list[str]) -> int:
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
