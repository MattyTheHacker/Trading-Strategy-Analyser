"""Re-run a campaign shortlist with its trade logs kept, and store them beside the summary.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar --root MNQ

The campaign sweep stores summary rows and nothing per trade, and turning ``keep_trades`` on
there is not the fix: every combination's log is not a thing to store, and ``keep_trades``
changes what ``sweep.run_combination`` returns and never what it measures. A bootstrap, a
permutation test and a time-of-day review each need a per-trade vector, so the logs are made
here instead -- rebuild a stored ``combos`` row, run that one configuration again with its log
kept, and save it under the ``(sweep_id, combo_id)`` the summary row already carries.

**``--held-out`` logs the pair a gate should read**: the held-out rows of the configurations
the *selection* window ranked highest, so nothing whose log is stored here was ranked on the
window it is then read from -- ``docs/roadmap.md`` §M28.13.

Also the home of :func:`rebuild`, :func:`shortlist` and :func:`best_row`, which every campaign
tool that starts from a stored row needs. What :func:`store_logs` wrote is read back by
``tools/campaign_report.py``'s ``load_trades``, beside the loader that reads the summary rows.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import fields, replace
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, logsetup, resample, results, splice, sweep
from nqbt.instruments import get_instrument
from tools.campaign_holdout import held_out
from tools.campaign_report import load, rank
from tools.campaign_sweep import db_path, elastic_ladder, windows

logger = logging.getLogger(__name__)

TOP = 20
"""How many configurations a shortlist takes by default -- the same twenty
``tools/campaign_holdout.py`` ranks, so the two tools shortlist the same rows."""

NET_PNL_TOLERANCE = 1e-9
"""Relative agreement required of a re-run's net P&L. Numerical rather than textual --
``CONTRIBUTING.md`` § "The trade-log regression gate"."""


def _absent(value: object) -> bool:
    """Whether a stored cell holds nothing.

    A sequence cell never does, and ``pd.isna`` returns an array rather than a bool for one.
    """
    if isinstance(value, (list, tuple)):
        return False

    return bool(pd.isna(value))


def _coerced(value: object, default: object) -> object:
    """One DuckDB cell as the field's own type. A stored list becomes a tuple again."""
    if isinstance(default, tuple):
        return tuple(value)  # type: ignore[call-overload]  # a list by construction

    if isinstance(default, (bool, int, float, str)):
        return type(default)(value)

    return value


def rebuild(row: pd.Series, archetype: archetypes.Archetype) -> archetypes.Params:  # type: ignore[type-arg]  # duckdb's dtypes
    """The parameter set a stored row came from, defaults filling anything not stored."""
    params: archetypes.Params = archetype.params_cls()
    updates: dict[str, object] = {}
    for field in fields(params):  # type: ignore[arg-type]  # a dataclass by construction
        if field.name not in row.index or _absent(row[field.name]):
            continue

        updates[field.name] = _coerced(row[field.name], getattr(params, field.name))
    if archetype is archetypes.ELASTICBAND:
        updates["target_stretch_levels"] = elastic_ladder(str(row["variant"]))

    return replace(params, **updates)


def shortlist(
    name: str,
    root: str,
    window: list[str],
    by: str,
    top: int = 1,
    stratum: str | None = None,
    resolution: int | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """The highest-ranked stored combinations for one archetype, root and stratum.

    A row whose ``by`` is undefined is dropped rather than ranked -- :func:`campaign_report.rank`.
    """
    frame: pd.DataFrame = load(name, window)
    frame = frame[frame["root"] == root]
    if stratum is not None:
        frame = frame[frame["stratum"] == stratum]

    if resolution is not None:
        frame = frame[frame["resolution"] == resolution]

    if variant is not None:
        frame = frame[frame["variant"] == variant]

    if frame.empty:
        msg: str = f"no stored rows for {name} on {root} in windows {window}, stratum {stratum}"
        raise RuntimeError(msg)

    ranked: pd.DataFrame = rank(frame, top, by)
    if ranked.empty:
        msg = f"{name} on {root}: every one of {len(frame)} stored rows has no {by} to rank on"
        raise RuntimeError(msg)

    return ranked


def best_row(
    name: str,
    root: str,
    window: list[str],
    by: str,
    stratum: str | None = None,
    resolution: int | None = None,
    variant: str | None = None,
) -> pd.Series:  # type: ignore[type-arg]  # duckdb's dtypes
    """The highest-ranked stored combination for one archetype, root and stratum."""
    return shortlist(name, root, window, by, 1, stratum, resolution, variant).iloc[0]


def source(bars: pd.DataFrame, window: str) -> pd.DataFrame:
    """The bar range a stored row's ``window`` names."""
    if window == "full":
        return bars

    return dict(windows(bars, split=True))[window]


def verify(row: pd.Series, summary: dict[str, object]) -> None:  # type: ignore[type-arg]  # duckdb's dtypes
    """Refuse a re-run that did not reproduce the trade count and net P&L the sweep stored.

    A log filed against a summary it does not match is worse than no log, because every
    statistic taken from it would be attributed to a configuration that did not produce it.
    """
    where: str = f"sweep {int(row['sweep_id'])} combo {int(row['combo_id'])}"
    trades: int = int(row["trades"])
    if int(summary["trades"]) != trades:
        msg: str = f"{where} re-ran to {int(summary['trades'])} trades, not the {trades} stored"
        raise RuntimeError(msg)

    net_pnl: float = float(row["net_pnl"])
    rerun_pnl: float = float(summary["net_pnl"])
    if not math.isclose(rerun_pnl, net_pnl, rel_tol=NET_PNL_TOLERANCE):
        msg = f"{where} re-ran to net {rerun_pnl:.4f}, not the {net_pnl:.4f} stored"
        raise RuntimeError(msg)


def store_group(
    block: pd.DataFrame,
    frame: pd.DataFrame,
    archetype: archetypes.Archetype,
    root: str,
    minutes: int,
    path: Path,
) -> int:
    """Store the log of every row measured on one resampled frame, and return how many.

    One prepared dataset serves the whole block, built from the shortlist as a combination grid
    so that the union over its members is :meth:`~nqbt.sweep.Grid.required_context`'s rather
    than a second copy of it.
    """
    rebuilt: list[tuple[pd.Series, archetypes.Params]] = [  # type: ignore[type-arg]  # duckdb's dtypes
        (row, rebuild(row, archetype)) for _, row in block.iterrows()
    ]
    grid: sweep.Grid = sweep.Grid.of_combinations([params for _, params in rebuilt], archetype=archetype)
    data: context.Dataset = context.prepare(frame, grid.required_context(), bar_minutes=minutes)

    for row, params in rebuilt:
        summary, log = sweep.run_combination(
            data,
            params,
            get_instrument(root),
            archetype,
            keep_trades=True,
        )
        verify(row, summary)
        if log is None:  # pragma: no cover - keep_trades always returns a log
            msg: str = "run_combination kept no log with keep_trades set"
            raise RuntimeError(msg)

        results.save_trades(log, int(row["sweep_id"]), int(row["combo_id"]), path, replace=True)
        logger.info(
            "  sweep %-4d combo %-6d %2dm %-9s %-24s %5d legs  PF %.3f",
            int(row["sweep_id"]),
            int(row["combo_id"]),
            minutes,
            str(row["window"]),
            str(row["stratum"]),
            len(log),
            float(row["profit_factor"]),
        )

    return len(rebuilt)


def store_logs(name: str, rows: pd.DataFrame, root: str) -> int:
    """Re-run every shortlisted row with its log kept, and return how many were stored.

    Grouped by window and resolution, because the resample and the prepared dataset are the
    expensive parts and every row sharing those two shares both. A stored log replaces whatever
    sits under the same ``(sweep_id, combo_id)``, so a second run refreshes rather than doubles.
    """
    archetype: archetypes.Archetype = archetypes.get(name)
    path: Path = db_path(name)
    bars: pd.DataFrame = splice.load_continuous(root)
    stored: int = 0
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), int(minutes))
        stored += store_group(block, frame, archetype, root, int(minutes), path)

    return stored


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Store a campaign shortlist's trade logs.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to log")
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="log the held-out rows of the configurations the selection window ranks highest",
    )
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = (
        held_out(args.strategy, args.root, args.by, args.top, args.stratum, args.resolution, args.variant)
        if args.held_out
        else shortlist(
            args.strategy,
            args.root,
            args.window,
            args.by,
            args.top,
            args.stratum,
            args.resolution,
            args.variant,
        )
    )
    logger.info(
        "%s on %s: %d configurations ranked on %s by %s",
        args.strategy,
        args.root,
        len(rows),
        "selection" if args.held_out else "+".join(args.window),
        args.by,
    )
    stored: int = store_logs(args.strategy, rows, args.root)
    logger.info("")
    logger.info("stored %d trade logs in %s", stored, db_path(args.strategy))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
