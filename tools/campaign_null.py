"""Place a campaign shortlist's best configuration against a matched random entry.

    ./.venv/Scripts/python.exe tools/campaign_null.py --strategy ElasticBand --root MNQ

A sweep can say which configuration has the highest profit factor. It cannot say whether the
**entry** earned it, because a bracket that suits the bars flatters a random entry just as much.
The matched null holds the signal count and the time-of-session distribution fixed and
randomises the day -- ``docs/roadmap.md`` §M7a and § "The method that does answer the question".

Rebuilds the parameter set from a stored ``combos`` row, so what is tested is exactly what the
sweep ranked.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import fields, replace
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_report import load
from tools.campaign_sweep import ELASTIC_LADDERS, windows

from nqbt import archetypes, logsetup, randomentry, resample, splice, sweep
from nqbt.instruments import get_instrument

logger = logging.getLogger(__name__)

STATISTICS = ("profit_factor", "expectancy", "win_rate", "mean_r")
"""What the observation is placed against. ``profit_factor`` and ``expectancy`` are the
verdict; ``win_rate`` is reported because a mean-reversion entry can beat the null on payoff
while losing on frequency -- ``docs/roadmap.md`` §M26."""


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
        updates["target_stretch_levels"] = ELASTIC_LADDERS[str(row["variant"])]
    return replace(params, **updates)


def best_row(
    name: str,
    root: str,
    windows: list[str],
    by: str,
    stratum: str | None = None,
    resolution: int | None = None,
) -> pd.Series:  # type: ignore[type-arg]  # duckdb's dtypes
    """The highest-ranked stored combination for one archetype, root and stratum."""
    frame: pd.DataFrame = load(name, windows)
    frame = frame[frame["root"] == root]
    if stratum is not None:
        frame = frame[frame["stratum"] == stratum]
    if resolution is not None:
        frame = frame[frame["resolution"] == resolution]
    if frame.empty:
        msg: str = f"no stored rows for {name} on {root} in windows {windows}, stratum {stratum}"
        raise RuntimeError(msg)
    return frame.nlargest(1, by).iloc[0]


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Matched-null test of a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored rows rank")
    parser.add_argument(
        "--test-window",
        default="full",
        choices=["full", "selection", "holdout"],
        help="which bars the null runs on; holdout after ranking on selection is the honest pair",
    )
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the row")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--n-jobs", type=int, default=8)
    args = parser.parse_args(argv[1:])

    archetype: archetypes.Archetype = archetypes.get(args.strategy)
    row: pd.Series = best_row(args.strategy, args.root, args.window, args.by, args.stratum, args.resolution)  # type: ignore[type-arg]  # duckdb's dtypes
    params: archetypes.Params = rebuild(row, archetype)
    minutes: int = int(row["resolution"])

    logger.info(
        "%s on %s at %dm, ranked on %s by %s=%s, tested on %s; stratum %s, variant %s, %d trades",
        args.strategy,
        args.root,
        minutes,
        "+".join(args.window),
        args.by,
        f"{row[args.by]:.3f}",
        args.test_window,
        row["stratum"],
        row["variant"],
        int(row["trades"]),
    )

    bars: pd.DataFrame = splice.load_continuous(args.root)
    if args.test_window != "full":
        bars = dict(windows(bars, split=True))[args.test_window]
    frame: pd.DataFrame = resample.resample(bars, minutes)
    grid: sweep.Grid = sweep.Grid(base=params, archetype=archetype)
    data = sweep.prepare_for(frame, grid)
    placed: dict[str, randomentry.NullResult] = randomentry.compare(
        data,
        params,
        archetype,
        get_instrument(args.root),
        statistics=STATISTICS,
        iterations=args.iterations,
        n_jobs=args.n_jobs,
    )
    logger.info("")
    with pd.option_context("display.width", 220, "display.max_columns", 60):
        logger.info("%s", randomentry.report(placed).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
