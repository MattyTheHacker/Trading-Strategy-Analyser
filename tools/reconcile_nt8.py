"""Compare an NT8 Strategy Analyzer Trades export against an nqbt run, leg for leg.

    uv run tools/reconcile_nt8.py <export.csv> <config> <contract> [from] [--bars <minute export>]

``config`` is a key of :data:`CONFIGS`; ``from`` is an optional ISO date trimming the export.
``tools/README.md`` § "reconcile_nt8.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import archetypes, context, ingest, logsetup, resample, timeofday
from nqbt.instruments import ContractId
from nqbt.sim.types import (
    DeadCatParams,
    InsideBarParams,
    InsideBarTrailingParams,
    PullBackAndGoParams,
)

logger = logging.getLogger(__name__)

EXIT_NAMES = {
    "Profit target": "target",
    "Stop loss": "stop",
    # SetTrailStop's own exit, which only InsideBarTrailing places. A trail is still a stop.
    "Trail stop": "stop",
    "Exit on session close": "session_close",
    # InsideBarTrailing's trend violation, named by the C# rather than by NT8 -- the two-string
    # ExitLong overload is (signalName, fromEntrySignal), so the signal name is what is exported.
    "Exit Long Trend Violation": "signal",
    "Exit Short Trend Violation": "signal",
    # "Exit Long Max Loss" and "Exit Short Max Loss" are deliberately absent. That branch is
    # unreachable at MaximumLossPerTrade = 0, so an export carrying one falsifies the reading in
    # docs/nt8-fidelity.md §M23 and must stop the run rather than be quietly counted.
    # Not an exit rule: NT8 reversing, which no archetype reproduces. Reported apart from the
    # comparison rather than counted as a disagreement -- docs/nt8-fidelity.md, "The position
    # guard does not hold in Strategy Analyzer".
    "Close position": "reversal",
}

REVERSAL = "reversal"

FIRST_DISAGREEMENTS = 5
"""Disagreeing legs shown inline; the point is to characterise them, not to list them all."""

DAY_FIRST_TIME = "%d/%m/%Y %I:%M:%S %p"
MONTH_FIRST_TIME = "%m/%d/%Y %I:%M:%S %p"

LEG_KEY = ["entry_time", "leg"]

EXPORT_TZ = "Europe/London"
"""The export is stamped in NinjaTrader's display zone -- the machine's -- not UTC.

See ``docs/nt8-fidelity.md`` § "Sessions".
"""

if TYPE_CHECKING:
    from nqbt.archetypes import Params

MIDDAY = timeofday.SessionPhase.MIDDAY.bit
"""10:30-14:00 ET, the stratum ``InsideBarTrailing.cs``'s trading window was added for."""


@dataclass(frozen=True, slots=True)
class Config:
    """One reconciled configuration: a parameter set and the bar size it was run at."""

    params: Params
    resolution: int = 1


INSIDEBAR_SIM = InsideBarParams(
    ema_period=44,
    fast_sma_period=50,
    error_margin=0.10,
    atr_length=14,
    atr_multiplier=20.0,
)

# The reconciled configurations, not the NinjaScripts' SetDefaults. See docs/nt8-fidelity.md.
CONFIGS: dict[str, Config] = {
    "DeadCatBounce": Config(
        DeadCatParams(
            ema_period=21,
            slow_sma_period=175,
            fast_sma_period=60,
            use_ema=True,
            use_slow_sma=True,
            use_fast_sma=True,
            use_vwap=True,
            require_previous_green=True,
            require_new_high=True,
        ),
    ),
    "PullBackAndGo": Config(PullBackAndGoParams()),
    # The no-entry window is off because the C# measures it against the wall clock, so the
    # two sides can only be made to test the same rule by both having it off. See
    # docs/nt8-fidelity.md, "A no-entry window before the session close".
    "InsideBar": Config(InsideBarParams(no_entry_minutes_before_close=0)),
    # SetDefaults unchanged: this NinjaScript has no wall-clock window to switch off.
    "InsideBarTrailing": Config(InsideBarTrailingParams()),
    # The trading window on, everything else SetDefaults, so the gate is the only thing that
    # moved against the row above -- docs/nt8-fidelity.md, "The entry trading window".
    "InsideBarTrailing-midday": Config(InsideBarTrailingParams(phase_filter=MIDDAY)),
    # Combo 2035, the cell Phase 0 named -- docs/findings/m43-midday-candidates-ranked.md
    # § "The cell to port". Its commission and slippage are deliberately not carried: that
    # file costs the campaign at 1.5 and 1 tick, and NT8 ran with no fee template, so a
    # reconciliation needs both sides at zero or every leg disagrees on price and P&L.
    "InsideBarTrailing-midday-2035": Config(
        InsideBarTrailingParams(
            phase_filter=MIDDAY,
            ema_period=44,
            fast_sma_period=20,
            error_margin=0.05,
            atr_length=14,
        ),
        resolution=5,
    ),
    # The same settings over the whole session: the November 2026 sim's second account.
    "InsideBarTrailing-2035": Config(
        InsideBarTrailingParams(
            ema_period=44,
            fast_sma_period=20,
            error_margin=0.05,
            atr_length=14,
        ),
        resolution=5,
    ),
    # The sim's third account. Its one-hour no-entry window reads the wall clock, so it fires on
    # a sim account and not in a Strategy Analyzer run started outside that hour, and each needs
    # its own row -- docs/nt8-fidelity.md, "A no-entry window before the session close".
    "InsideBar-sim": Config(INSIDEBAR_SIM, resolution=5),
    "InsideBar-sim-analyzer": Config(replace(INSIDEBAR_SIM, no_entry_minutes_before_close=0), resolution=5),
}


def read_export(path: Path) -> pd.DataFrame:
    """Read a trade-list export as written, with its column names stripped."""
    raw = pd.read_csv(path)
    raw.columns = [c.strip() for c in raw.columns]

    return raw


def parse_nt8(path: Path, *, day_first: bool = True) -> pd.DataFrame:
    """Parse the export into one row per leg exit, matching nqbt's trade-log shape.

    ``day_first`` is the exporting machine's date order: the laptop's is, an en-US machine's is not.
    """
    raw = read_export(path)

    def money(column: pd.Series[str]) -> pd.Series[float]:
        """Parse NT8's money, which writes a loss as ``-$4.50`` or, in accounting format, as ``($4.50)``.

        Stripping the brackets without negating turns every loss into a gain, and the join
        still succeeds -- so it reads as a P&L disagreement rather than as a parse bug.
        """
        negative = column.str.strip().str.startswith("(")
        bare = column.str.replace(r"[$,()]", "", regex=True).astype(float)

        return bare.where(~negative, -bare.abs())

    def when(column: str) -> pd.Series[pd.Timestamp]:
        naive = pd.to_datetime(raw[column], format=DAY_FIRST_TIME if day_first else MONTH_FIRST_TIME)

        return naive.dt.tz_localize(EXPORT_TZ, ambiguous="infer", nonexistent="shift_forward").dt.tz_convert(
            "UTC",
        )

    out = pd.DataFrame(
        {
            "entry_time": when("Entry time"),
            "exit_time": when("Exit time"),
            # S1..S4 and L1..L4 carry their leg in the name, and so do InsideBarTrailing's
            # "entry1"/"entry2" -- which land on legs 1 and 2, the order the port writes its
            # bracketed and trailing lots in. InsideBar brackets one order called "entry" and
            # has no scale-out, so it is leg 1.
            "leg": raw["Entry name"].str.extract(r"(\d+)")[0].fillna("1").astype(int),
            "side": raw["Market pos."],
            "quantity": raw["Qty"].astype(int),
            "entry_price": raw["Entry price"].astype(float),
            "exit_price": raw["Exit price"].astype(float),
            "net_pnl": money(raw["Profit"]),
            "exit_reason": raw["Exit name"].map(EXIT_NAMES),
            "bars": raw["Bars"].astype(int),
        },
    )
    if out["exit_reason"].isna().any():
        unknown = sorted(raw.loc[out["exit_reason"].isna(), "Exit name"].unique())
        msg = f"unmapped NT8 exit name(s): {unknown}"
        raise SystemExit(msg)

    return out.sort_values(["entry_time", "leg"]).reset_index(drop=True)


def load_bars(contract_id: ContractId, bars_export: Path | None) -> pd.DataFrame:
    """Return one contract's bars from a minute export if given, else from the cache."""
    if bars_export is None:
        return ingest.load_contract(contract_id)

    try:
        named = ContractId.parse(bars_export.name.removesuffix(".Last.txt"))
    except ValueError:
        named = contract_id
    if named != contract_id:
        msg = f"{bars_export.name} holds {named.nt8_name}'s bars, not {contract_id.nt8_name}'s"
        raise SystemExit(msg)

    parsed = ingest.parse_export(bars_export.read_bytes(), source_name=bars_export.name)

    return ingest.drop_out_of_session(parsed, source_name=bars_export.name)


def run_nqbt(config_name: str, contract: str, bars_export: Path | None = None) -> pd.DataFrame:
    """Return nqbt's trade log for one named configuration on one contract."""
    if config_name not in CONFIGS:
        msg = f"unknown config {config_name!r}; known: {sorted(CONFIGS)}"
        raise SystemExit(msg)

    config = CONFIGS[config_name]
    params = config.params
    archetype = archetypes.for_params(params)
    contract_id = ContractId.parse(contract)
    bars = resample.resample(load_bars(contract_id, bars_export), config.resolution)
    data = context.prepare(
        bars,
        archetype.context_for({k: [v] for k, v in params.as_dict().items()}),  # type: ignore[list-item]  # a params field holds an axis value
        bar_minutes=config.resolution,
        price_basis=context.PriceBasis.RAW,
    )
    log = archetype.run(data, params, contract_id.instrument)

    return log.sort_values(["entry_time", "leg"]).reset_index(drop=True)


def hold_out_reversals(nt8: pd.DataFrame) -> pd.DataFrame:
    """Return the legs an NT8 reversal did not cut short, logging how many it did."""
    cut = nt8["exit_reason"] == REVERSAL
    if cut.any():
        logger.info("  reversals         %s cut short by an NT8 reversal, held out", f"{int(cut.sum()):,}")

    return nt8[~cut]


def compare_legs(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_name: str = "NT8",
    right_name: str = "nqbt",
) -> pd.DataFrame:
    """Log how two trade lists agree, leg for leg, and return the legs both hold.

    Each side's columns come back suffixed with its name in lower case.
    """
    left_suffix, right_suffix = f"_{left_name.lower()}", f"_{right_name.lower()}"
    joined = left.merge(
        right,
        on=LEG_KEY,
        how="outer",
        suffixes=(left_suffix, right_suffix),
        indicator=True,
    )
    both = joined[joined["_merge"] == "both"]

    logger.info("  %-18s%s", f"{left_name} legs", f"{len(left):,}")
    logger.info("  %-18s%s", f"{right_name} legs", f"{len(right):,}")
    logger.info("  %-18s%s", "joined", f"{len(both):,}")
    logger.info("  %-18s%s", f"{left_name} only", f"{int((joined['_merge'] == 'left_only').sum()):,}")
    logger.info("  %-18s%s", f"{right_name} only", f"{int((joined['_merge'] == 'right_only').sum()):,}")
    if not len(both):
        return both

    checks = {
        "identical entry price": np.isclose(
            both[f"entry_price{left_suffix}"], both[f"entry_price{right_suffix}"]
        ),
        "identical exit price": np.isclose(
            both[f"exit_price{left_suffix}"], both[f"exit_price{right_suffix}"]
        ),
        "identical exit time": both[f"exit_time{left_suffix}"] == both[f"exit_time{right_suffix}"],
        "identical exit reason": both[f"exit_reason{left_suffix}"] == both[f"exit_reason{right_suffix}"],
        "identical P&L": np.isclose(both[f"net_pnl{left_suffix}"], both[f"net_pnl{right_suffix}"], atol=1e-6),
    }
    every = np.ones(len(both), dtype=bool)
    for name, ok in checks.items():
        every &= np.asarray(ok)
        logger.info("  %-22s%s (%s)", name, f"{int(np.sum(ok)):,}", f"{np.mean(ok):.2%}")
    logger.info("  %-22s%s (%s)", "identical everywhere", f"{int(every.sum()):,}", f"{every.mean():.2%}")
    logger.info(
        "  net P&L           %s %s   %s %s",
        left_name,
        f"{both[f'net_pnl{left_suffix}'].sum():,.2f}",
        right_name,
        f"{both[f'net_pnl{right_suffix}'].sum():,.2f}",
    )

    bad = both[~every]
    if len(bad):
        cols = list(LEG_KEY)
        for column in ("exit_time", "exit_price", "exit_reason"):
            cols += [f"{column}{left_suffix}", f"{column}{right_suffix}"]
        logger.info("")
        logger.info("  first %d disagreeing legs:", min(FIRST_DISAGREEMENTS, len(bad)))
        logger.info("%s", bad[cols].head(FIRST_DISAGREEMENTS).to_string(index=False))

    return both


def reconcile(nt8: pd.DataFrame, mine: pd.DataFrame) -> None:
    """Log how NT8's legs and nqbt's agree, leg for leg, over the window both cover."""
    nt8 = hold_out_reversals(nt8)
    # Both ends are excluded: NT8 warms indicators from bars before the export starts, and
    # the export can stop before the backtest did. See docs/nt8-fidelity.md.
    lo, hi = nt8["entry_time"].min(), nt8["entry_time"].max()
    inner = mine[(mine["entry_time"] > lo) & (mine["entry_time"] < hi)]
    nt8_inner = nt8[(nt8["entry_time"] > lo) & (nt8["entry_time"] < hi)]

    logger.info(
        "  window            %s -> %s (ends excluded)", f"{lo:%Y-%m-%d %H:%M}", f"{hi:%Y-%m-%d %H:%M}"
    )
    compare_legs(nt8_inner, inner)


def main(argv: list[str]) -> int:
    """Reconcile the NT8 export against an nqbt run and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("export", type=Path)
    parser.add_argument("config")
    parser.add_argument("contract")
    parser.add_argument("start", metavar="from", nargs="?")
    parser.add_argument("--bars", type=Path, help="a minute export to read instead of the cached contract")
    args = parser.parse_args(argv[1:])

    logger.info("== %s on %s ==", args.config, args.contract)
    nt8 = parse_nt8(args.export)
    if args.start is not None:
        start = pd.Timestamp(args.start, tz="UTC")
        logger.info("  trimmed to        %s onwards", f"{start:%Y-%m-%d}")
        nt8 = nt8[nt8["entry_time"] >= start]

    mine = run_nqbt(args.config, args.contract, args.bars)
    reconcile(nt8, mine)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
