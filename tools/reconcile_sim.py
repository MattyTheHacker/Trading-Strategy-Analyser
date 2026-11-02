"""Compare an NT8 sim account's trade list against an nqbt run or a Strategy Analyzer export.

    uv run tools/reconcile_sim.py <trades.csv> <config> <contract> --from <time> --to <time>
        [--bars <minute export> | --analyzer <export>] [--month-first] [--analyzer-month-first]

``config`` is a key of ``reconcile_nt8.CONFIGS``; ``--from`` and ``--to`` are UK local times.
``tools/README.md`` § "reconcile_sim.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup
from nqbt.instruments import ContractId
from tools import reconcile_nt8

logger = logging.getLogger(__name__)


def refuse_mixed_export(path: Path, contract: str) -> None:
    """Stop unless the export holds one account's trades on this contract alone."""
    raw = reconcile_nt8.read_export(path)
    accounts = sorted(raw["Account"].unique())
    if len(accounts) > 1:
        msg = f"the export mixes accounts {accounts}; export one account at a time"
        raise SystemExit(msg)

    others = sorted(set(raw["Instrument"].unique()) - {ContractId.parse(contract).nt8_name})
    if others:
        msg = f"the export holds {others}, not {contract}"
        raise SystemExit(msg)


def signal_boundaries(fills: pd.Series[pd.Timestamp], resolution: int) -> pd.Series[pd.Timestamp]:
    """Return the bar boundary that triggered each market entry's fill."""
    return fills.dt.round(pd.Timedelta(minutes=resolution))


def refuse_trades_outside(sim: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, resolution: int) -> None:
    """Stop if an entry's signal falls outside the window, as it does under a wrong date order."""
    signals = signal_boundaries(sim["entry_time"], resolution)
    outside = sim[(signals < start) | (signals > end)]
    if not len(outside):
        return

    msg = (
        f"{len(outside)} entries fall outside the window, first at "
        f"{outside['entry_time'].iloc[0]:%Y-%m-%d %H:%M} UTC; trim the export, or pass "
        "--month-first if the machine writes dates that way"
    )
    raise SystemExit(msg)


def seconds_from_bar_boundary(sim: pd.DataFrame, resolution: int) -> pd.Series[float]:
    """Return how far each market entry's fill lies from the bar boundary that triggered it."""
    fills = sim["entry_time"]
    seconds: pd.Series[float] = (fills - signal_boundaries(fills, resolution)).dt.total_seconds()

    return seconds


def to_bar_stamps(sim: pd.DataFrame, resolution: int) -> pd.DataFrame:
    """Return a sim trade list with its fill times replaced by the stamps a backtest gives them."""
    bar = pd.Timedelta(minutes=resolution)
    stamped = sim.copy()
    stamped["entry_time"] = signal_boundaries(sim["entry_time"], resolution) + bar
    stamped["exit_time"] = sim["exit_time"].dt.ceil(bar)
    repeated = stamped[stamped.duplicated(["entry_time", "leg"], keep=False)]
    if len(repeated):
        msg = (
            f"{len(repeated)} rows share a bar and a leg, first at "
            f"{repeated['entry_time'].iloc[0]:%Y-%m-%d %H:%M} UTC; NT8 split a fill or paired an "
            "exit across legs, and joining them would double count"
        )
        raise SystemExit(msg)

    return stamped


def log_price_gaps(both: pd.DataFrame, other_name: str, tick_size: float) -> None:
    """Log the mean absolute price gap against the sim side, in ticks, per exit reason."""
    if not len(both):
        return

    entry_gap = (both["entry_price_sim"] - both[f"entry_price_{other_name}"]).abs() / tick_size
    exit_gap = (both["exit_price_sim"] - both[f"exit_price_{other_name}"]).abs() / tick_size
    logger.info("  %-30s%.2f ticks", "mean entry gap", entry_gap.mean())
    for reason, gaps in exit_gap.groupby(both[f"exit_reason_{other_name}"]):
        logger.info("  %-30s%.2f ticks over %d legs", f"mean exit gap, {reason}", gaps.mean(), len(gaps))


def compare_sim(
    sim: pd.DataFrame,
    other: pd.DataFrame,
    other_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    resolution: int,
    tick_size: float,
) -> pd.DataFrame:
    """Log how a sim trade list agrees with another over the window, and return the joined legs."""
    refuse_trades_outside(sim, start, end, resolution)
    sim = reconcile_nt8.hold_out_reversals(sim)
    # Unlike a backtest's export, both ends count: the window is when the strategy was enabled.
    # Each side is read at its signal, because a stamp is a bar later than the order went in.
    signals = other["entry_time"] - pd.Timedelta(minutes=resolution)
    inside = other[(signals >= start) & (signals <= end)]
    if len(other) and not len(inside):
        logger.warning(
            "none of %s's %d legs falls in the window; check its date order", other_name, len(other)
        )

    inside = reconcile_nt8.hold_out_reversals(inside)
    if len(sim):
        furthest = seconds_from_bar_boundary(sim, resolution).abs().max()
        logger.info("  %-18s%.0f s from its bar boundary", "furthest entry", furthest)

    both = reconcile_nt8.compare_legs(to_bar_stamps(sim, resolution), inside, "Sim", other_name)
    log_price_gaps(both, other_name.lower(), tick_size)

    return both


def main(argv: list[str]) -> int:
    """Reconcile the sim trade list and return the process exit code."""
    logsetup.configure(__name__, reconcile_nt8.__name__)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("trades", type=Path)
    parser.add_argument("config")
    parser.add_argument("contract")
    parser.add_argument("--from", dest="start", required=True, help="when the strategy went live, UK time")
    parser.add_argument("--to", dest="end", required=True, help="the last entry to compare, UK time")
    other_side = parser.add_mutually_exclusive_group()
    other_side.add_argument(
        "--bars", type=Path, help="a minute export to read instead of the cached contract"
    )
    other_side.add_argument(
        "--analyzer", type=Path, help="compare with this Strategy Analyzer export, not nqbt"
    )
    parser.add_argument("--month-first", action="store_true", help="the trade list's dates are mm/dd/yyyy")
    parser.add_argument(
        "--analyzer-month-first", action="store_true", help="the analyzer export's dates are mm/dd/yyyy"
    )
    args = parser.parse_args(argv[1:])

    if args.config not in reconcile_nt8.CONFIGS:
        msg = f"unknown config {args.config!r}; known: {sorted(reconcile_nt8.CONFIGS)}"
        raise SystemExit(msg)

    start = pd.Timestamp(args.start, tz=reconcile_nt8.EXPORT_TZ).tz_convert("UTC")
    end = pd.Timestamp(args.end, tz=reconcile_nt8.EXPORT_TZ).tz_convert("UTC")
    logger.info("== %s on %s, %s to %s ==", args.config, args.contract, args.start, args.end)
    refuse_mixed_export(args.trades, args.contract)
    sim = reconcile_nt8.parse_nt8(args.trades, day_first=not args.month_first)
    if args.analyzer is None:
        other, other_name = reconcile_nt8.run_nqbt(args.config, args.contract, args.bars), "nqbt"
    else:
        refuse_mixed_export(args.analyzer, args.contract)
        other = reconcile_nt8.parse_nt8(args.analyzer, day_first=not args.analyzer_month_first)
        other_name = "Analyzer"

    compare_sim(
        sim,
        other,
        other_name,
        start,
        end,
        reconcile_nt8.CONFIGS[args.config].resolution,
        ContractId.parse(args.contract).instrument.tick_size,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
