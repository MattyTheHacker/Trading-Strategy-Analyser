"""Compare an NT8 Strategy Analyzer Trades export against an nqbt run, leg for leg.

    ./.venv/Scripts/python.exe tools/reconcile_nt8.py <export.csv> <archetype> <contract>

Reasoning, results and the traps are in docs/nt8-fidelity.md; this is the mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nqbt import archetypes, context, ingest
from nqbt.instruments import MNQ, NQ, ContractId
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams

EXIT_NAMES = {
    "Profit target": "target",
    "Stop loss": "stop",
    "Exit on session close": "session_close",
}

EXPORT_TZ = "Europe/London"
"""The export is stamped in NinjaTrader's display zone -- the machine's -- not UTC.

Explicit rather than inferred: a wrong zone shifts every trade by a whole hour and still
parses. See docs/nt8-fidelity.md, "Trade-list exports are in machine local time".
"""

# The reconciled configuration, not the NinjaScript's SetDefaults. See docs/nt8-fidelity.md.
CONFIGS = {
    "DeadCatBounce": DeadCatParams(
        ema_period=21, slow_sma_period=175, fast_sma_period=60,
        use_ema=True, use_slow_sma=True, use_fast_sma=True, use_vwap=True,
        require_previous_green=True, require_new_high=True,
    ),
    "PullBackAndGo": PullBackAndGoParams(),
}


def parse_nt8(path: Path) -> pd.DataFrame:
    """One row per leg exit, matching nqbt's trade-log shape."""
    raw = pd.read_csv(path)
    raw.columns = [c.strip() for c in raw.columns]

    money = lambda s: s.str.replace(r"[$,()]", "", regex=True).astype(float)  # noqa: E731

    def when(column: str) -> pd.Series:
        naive = pd.to_datetime(raw[column], format="%d/%m/%Y %I:%M:%S %p")
        return (
            naive.dt.tz_localize(EXPORT_TZ, ambiguous="infer", nonexistent="shift_forward")
            .dt.tz_convert("UTC")
        )

    out = pd.DataFrame({
        "entry_time": when("Entry time"),
        "exit_time": when("Exit time"),
        "leg": raw["Entry name"].str.extract(r"(\d+)")[0].astype(int),
        "entry_price": raw["Entry price"].astype(float),
        "exit_price": raw["Exit price"].astype(float),
        "net_pnl": money(raw["Profit"]),
        "exit_reason": raw["Exit name"].map(EXIT_NAMES),
        "bars": raw["Bars"].astype(int),
    })
    if out["exit_reason"].isna().any():
        unknown = sorted(raw.loc[out["exit_reason"].isna(), "Exit name"].unique())
        raise SystemExit(f"unmapped NT8 exit name(s): {unknown}")
    return out.sort_values(["entry_time", "leg"]).reset_index(drop=True)


def run_nqbt(archetype_name: str, contract: str) -> pd.DataFrame:
    archetype = archetypes.get(archetype_name)
    params = CONFIGS[archetype_name]
    bars = ingest.load_contract(ContractId.parse(contract))
    instrument = NQ if contract.startswith("NQ") else MNQ
    data = context.prepare(bars, archetype.context_for({
        k: [v] for k, v in params.as_dict().items()
    }))
    log = archetype.run(data, params, instrument)
    return log.sort_values(["entry_time", "leg"]).reset_index(drop=True)


def reconcile(nt8: pd.DataFrame, mine: pd.DataFrame) -> None:
    # Both ends are excluded: NT8 warms indicators from bars before the export starts, and
    # the export can stop before the backtest did. See docs/nt8-fidelity.md.
    lo, hi = nt8["entry_time"].min(), nt8["entry_time"].max()
    inner = mine[(mine["entry_time"] > lo) & (mine["entry_time"] < hi)]
    nt8_inner = nt8[(nt8["entry_time"] > lo) & (nt8["entry_time"] < hi)]

    joined = nt8_inner.merge(
        inner, on=["entry_time", "leg"], how="outer", suffixes=("_nt8", "_nqbt"),
        indicator=True,
    )
    both = joined[joined["_merge"] == "both"]

    print(f"  window            {lo:%Y-%m-%d %H:%M} -> {hi:%Y-%m-%d %H:%M} (ends excluded)")
    print(f"  NT8 legs          {len(nt8_inner):,}")
    print(f"  nqbt legs         {len(inner):,}")
    print(f"  joined            {len(both):,}")
    print(f"  NT8 only          {int((joined['_merge'] == 'left_only').sum()):,}")
    print(f"  nqbt only         {int((joined['_merge'] == 'right_only').sum()):,}")
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
        print(f"  {name:<22}{int(np.sum(ok)):,} ({np.mean(ok):.2%})")
    print(f"  {'identical everywhere':<22}{int(every.sum()):,} ({every.mean():.2%})")
    print(f"  net P&L           NT8 {both['net_pnl_nt8'].sum():,.2f}   "
          f"nqbt {both['net_pnl_nqbt'].sum():,.2f}")

    bad = both[~every]
    if len(bad):
        print(f"\n  first {min(5, len(bad))} disagreeing legs:")
        cols = ["entry_time", "leg", "exit_time_nt8", "exit_time_nqbt",
                "exit_price_nt8", "exit_price_nqbt", "exit_reason_nt8", "exit_reason_nqbt"]
        print(bad[cols].head(5).to_string(index=False))


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    export, archetype_name, contract = argv[1], argv[2], argv[3]
    print(f"== {archetype_name} on {contract} ==")
    nt8 = parse_nt8(Path(export))
    mine = run_nqbt(archetype_name, contract)
    reconcile(nt8, mine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
