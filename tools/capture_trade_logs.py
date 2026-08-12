"""Capture every trade-log producer path to CSV, for byte-comparison across a refactor.

The regression gate for anything that touches the simulation. Run it before the change and
after, then diff the two directories: a refactor that is meant to preserve behaviour must
reproduce every file byte-for-byte, and one that adds a column must leave every other
column identical.

    ./.venv/Scripts/python.exe tools/capture_trade_logs.py before
    ...make the change...
    ./.venv/Scripts/python.exe tools/capture_trade_logs.py after
    ./.venv/Scripts/python.exe tools/compare_trade_logs.py before after

Written for M9, which moved validated code and needed to prove it had not moved a number.
M15 needs exactly the same gate and a stronger one -- every short-only trade log
byte-identical after the loop is generalised -- so this is deliberately a tool rather than
a throwaway. See ``docs/roadmap.md`` under M9 and M15.

**Every frame is written with ``float_format="%.17g"``, and that is not cosmetic.** Pandas'
default CSV writer is *not* round-trip exact for float64: round-tripping a real trade log
through ``to_csv``/``read_csv`` moves 4 of 1,664 ``r_multiple`` values by one ULP. A gate
written in the default format therefore compares text-rounded numbers and can miss a
sub-ULP change -- which is exactly the class of difference a sign or associativity error in
the simulation produces. 17 significant digits round-trips float64 exactly, so byte-identity
of these files is byte-identity of the floats.

The four paths are chosen to cover what a single run does not:

1. the pinned MNQ 03-24 reconciliation window, under the two settings that reproduce
   ``verification/nt8_reconciliation_MNQ_03-24.csv`` (see ``verification/README.md``);
2. the same contract at current fidelity settings, with costs applied;
3. the same bars through the NQ spec, which proves instrument scaling is untouched;
4. a real sweep over spliced continuous bars, serial *and* parallel, since the parallel
   path memmaps the dataset and could diverge on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from nqbt import context, ingest, splice, stats, sweep
from nqbt.instruments import MNQ, NQ, ContractId
from nqbt.sim.runner import run_deadcat
from nqbt.sim.types import DeadCatParams

CONTRACT = "MNQ 03-24"
SWEEP_FROM = "2024-01-01"

EXACT = "%.17g"
"""Round-trips float64 without loss. See the module docstring -- the default does not."""


def write(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, float_format=EXACT)


def capture(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    bars = ingest.load_contract(ContractId.parse(CONTRACT))
    print(f"{CONTRACT}: {len(bars):,} bars  {bars.index[0]} -> {bars.index[-1]}")

    # 1. The pinned reconciliation window. These two settings are what reproduce the
    #    stored pre-fix run; do not "modernise" them.
    recon = DeadCatParams(
        ema_period=21, slow_sma_period=175, fast_sma_period=60,
        use_ema=True, use_slow_sma=True, use_fast_sma=True, use_vwap=True,
        require_previous_green=True, require_new_high=True,
        fill_limit_on_touch=True, ambiguity_policy=0,
    )
    data = context.prepare(bars, ema_periods=(21,), sma_periods=(60, 175))
    write(run_deadcat(data, recon, MNQ), outdir / "recon.csv")

    # 2 and 3. Current settings with costs, through both instrument specs.
    live = DeadCatParams(commission_per_contract=1.24, slippage_ticks=1.0)
    data = context.prepare(
        bars,
        ema_periods=(live.ema_period,),
        sma_periods=(live.fast_sma_period, live.slow_sma_period),
    )
    live_trades = run_deadcat(data, live, MNQ)
    write(live_trades, outdir / "live_mnq.csv")
    write(run_deadcat(data, live, NQ), outdir / "live_nq.csv")
    pd.Series(stats.summarise(live_trades).as_dict()).to_csv(
        outdir / "live_summary.csv", float_format=EXACT
    )
    print(f"  single-contract legs: recon and live captured ({len(live_trades):,} live)")

    # 4. A real sweep, both execution paths.
    continuous = splice.load_continuous("MNQ", back_adjust=True)
    continuous = continuous[continuous.index >= SWEEP_FROM]
    grid = sweep.Grid.of(
        DeadCatParams(commission_per_contract=1.24, slippage_ticks=1.0),
        ema_period=[11, 21], fast_sma_period=[60, 80], use_vwap=[True, False],
    )
    prepared = sweep.prepare_for(continuous, grid)
    serial, logs = sweep.sweep(continuous, grid, MNQ, data=prepared, keep_trades=True)
    write(serial, outdir / "sweep_serial.csv")
    parallel, _ = sweep.sweep(continuous, grid, MNQ, data=prepared, n_jobs=4)
    write(parallel, outdir / "sweep_parallel.csv")
    for combo_id, log in sorted(logs.items()):
        write(log, outdir / f"sweep_trades_{combo_id}.csv")
    legs = sum(len(v) for v in logs.values())
    print(f"  {len(continuous):,} continuous bars, {len(serial)} combos, {legs:,} legs")

    print(f"\nwrote {len(list(outdir.iterdir()))} files to {outdir}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    capture(Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
