"""Compare an NT8 Strategy Analyzer Trades export against an nqbt run, leg for leg.

    ./.venv/Scripts/python.exe tools/reconcile_nt8.py <export.csv> <config> <contract> [from]

``config`` is a key of :data:`CONFIGS`, which is usually an archetype's name and is not always:
one archetype can have several reconciled configurations, at different parameters and different
bar sizes.

``from`` is an optional ISO date that trims the export. Needed whenever NT8 was asked for more
history than the contract itself has: it serves its *merged* series there, which a per-contract
archive cannot reproduce -- docs/nt8-fidelity.md, "Reconciliation result -- InsideBar".

Reasoning, results and the traps are in docs/nt8-fidelity.md; this is the mechanism.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
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

EXPECTED_ARGV = (4, 5)
FIRST_DISAGREEMENTS = 5
"""Disagreeing legs shown inline; the point is to characterise them, not to list them all."""

EXPORT_TZ = "Europe/London"
"""The export is stamped in NinjaTrader's display zone -- the machine's -- not UTC.

Explicit rather than inferred: a wrong zone shifts every trade by a whole hour and still
parses. See docs/nt8-fidelity.md, "Trade-list exports are in machine local time".
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
}


def parse_nt8(path: Path) -> pd.DataFrame:
    """One row per leg exit, matching nqbt's trade-log shape."""
    raw = pd.read_csv(path)
    raw.columns = [c.strip() for c in raw.columns]

    def money(column: pd.Series) -> pd.Series:
        """NT8 writes a loss as ``-$4.50`` or, in accounting format, as ``($4.50)``.

        Stripping the brackets without negating turns every loss into a gain, and the join
        still succeeds -- so it reads as a P&L disagreement rather than as a parse bug.
        """
        negative = column.str.strip().str.startswith("(")
        bare = column.str.replace(r"[$,()]", "", regex=True).astype(float)

        return bare.where(~negative, -bare.abs())

    def when(column: str) -> pd.Series:
        naive = pd.to_datetime(raw[column], format="%d/%m/%Y %I:%M:%S %p")

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


def run_nqbt(config_name: str, contract: str) -> pd.DataFrame:
    if config_name not in CONFIGS:
        msg = f"unknown config {config_name!r}; known: {sorted(CONFIGS)}"
        raise SystemExit(msg)

    config = CONFIGS[config_name]
    params = config.params
    archetype = archetypes.for_params(params)
    contract_id = ContractId.parse(contract)
    bars = resample.resample(ingest.load_contract(contract_id), config.resolution)
    data = context.prepare(
        bars,
        archetype.context_for({k: [v] for k, v in params.as_dict().items()}),
        bar_minutes=config.resolution,
        price_basis=context.PriceBasis.RAW,
    )
    log = archetype.run(data, params, contract_id.instrument)

    return log.sort_values(["entry_time", "leg"]).reset_index(drop=True)


def reconcile(nt8: pd.DataFrame, mine: pd.DataFrame) -> None:
    # Both ends are excluded: NT8 warms indicators from bars before the export starts, and
    # the export can stop before the backtest did. See docs/nt8-fidelity.md.
    cut = nt8["exit_reason"] == REVERSAL
    if cut.any():
        logger.info("  reversals         %s cut short by an NT8 reversal, held out", f"{int(cut.sum()):,}")
        nt8 = nt8[~cut]

    lo, hi = nt8["entry_time"].min(), nt8["entry_time"].max()
    inner = mine[(mine["entry_time"] > lo) & (mine["entry_time"] < hi)]
    nt8_inner = nt8[(nt8["entry_time"] > lo) & (nt8["entry_time"] < hi)]

    joined = nt8_inner.merge(
        inner,
        on=["entry_time", "leg"],
        how="outer",
        suffixes=("_nt8", "_nqbt"),
        indicator=True,
    )
    both = joined[joined["_merge"] == "both"]

    logger.info(
        "  window            %s -> %s (ends excluded)", f"{lo:%Y-%m-%d %H:%M}", f"{hi:%Y-%m-%d %H:%M}"
    )
    logger.info("  NT8 legs          %s", f"{len(nt8_inner):,}")
    logger.info("  nqbt legs         %s", f"{len(inner):,}")
    logger.info("  joined            %s", f"{len(both):,}")
    logger.info("  NT8 only          %s", f"{int((joined['_merge'] == 'left_only').sum()):,}")
    logger.info("  nqbt only         %s", f"{int((joined['_merge'] == 'right_only').sum()):,}")
    if not len(both):
        return

    checks = {
        "identical entry price": np.isclose(both["entry_price_nt8"], both["entry_price_nqbt"]),
        "identical exit price": np.isclose(both["exit_price_nt8"], both["exit_price_nqbt"]),
        "identical exit time": both["exit_time_nt8"] == both["exit_time_nqbt"],
        "identical exit reason": both["exit_reason_nt8"] == both["exit_reason_nqbt"],
        "identical P&L": np.isclose(both["net_pnl_nt8"], both["net_pnl_nqbt"], atol=1e-6),
    }
    every = np.ones(len(both), dtype=bool)
    for name, ok in checks.items():
        every &= np.asarray(ok)
        logger.info("  %-22s%s (%s)", name, f"{int(np.sum(ok)):,}", f"{np.mean(ok):.2%}")
    logger.info("  %-22s%s (%s)", "identical everywhere", f"{int(every.sum()):,}", f"{every.mean():.2%}")
    logger.info(
        "  net P&L           NT8 %s   nqbt %s",
        f"{both['net_pnl_nt8'].sum():,.2f}",
        f"{both['net_pnl_nqbt'].sum():,.2f}",
    )

    bad = both[~every]
    if len(bad):
        cols = [
            "entry_time",
            "leg",
            "exit_time_nt8",
            "exit_time_nqbt",
            "exit_price_nt8",
            "exit_price_nqbt",
            "exit_reason_nt8",
            "exit_reason_nqbt",
        ]
        logger.info("")
        logger.info("  first %d disagreeing legs:", min(FIRST_DISAGREEMENTS, len(bad)))
        logger.info("%s", bad[cols].head(FIRST_DISAGREEMENTS).to_string(index=False))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    if len(argv) not in EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    export, config_name, contract = argv[1], argv[2], argv[3]
    logger.info("== %s on %s ==", config_name, contract)
    nt8 = parse_nt8(Path(export))
    if len(argv) == EXPECTED_ARGV[1]:
        start = pd.Timestamp(argv[4], tz="UTC")
        logger.info("  trimmed to        %s onwards", f"{start:%Y-%m-%d}")
        nt8 = nt8[nt8["entry_time"] >= start]

    mine = run_nqbt(config_name, contract)
    reconcile(nt8, mine)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
