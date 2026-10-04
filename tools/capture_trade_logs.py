"""Capture every trade-log producer path to CSV, for comparison across a refactor.

    uv run tools/capture_trade_logs.py before
    ...make the change...
    uv run tools/capture_trade_logs.py after
    uv run tools/compare_trade_logs.py before after

``tools/README.md`` § "capture_trade_logs.py".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from nqbt import archetypes, conditions, context, costs, ingest, logsetup, paths, splice, stats, sweep
from nqbt.instruments import MNQ, NQ, ContractId
from nqbt.sim.runner import run_deadcat
from nqbt.sim.types import DeadCatParams

if TYPE_CHECKING:
    from nqbt.instruments import Instrument

logger = logging.getLogger(__name__)


class EmptyCaptureError(RuntimeError):
    """Raised when an archetype trades nothing at its defaults, so its log could gate nothing."""


CONTRACT = "MNQ 03-24"
SWEEP_FROM = "2024-01-01"
EXPECTED_ARGV = 2

JIT_CACHE_SUFFIXES = (".nbi", ".nbc")
"""What ``@njit(cache=True)`` writes beside each module, and what a capture deletes first.

Do not remove that purge: numba's cache does not track cross-module dependencies --
``.claude/rules/regression-gate.md``.
"""


def purge_jit_cache(package: Path = paths.REPO_ROOT / "nqbt") -> int:
    """Delete every compiled-function cache under ``package`` and return how many files went.

    Cheap insurance rather than an optimisation to skip: the recompile costs a minute and a
    stale cache costs the gate.
    """
    stale: list[Path] = [path for path in package.rglob("*") if path.suffix in JIT_CACHE_SUFFIXES]
    for path in stale:
        path.unlink()

    return len(stale)


CAPTURE_GLOBS = ("recon.csv", "live_*.csv", "sweep_*.csv", "defaults_*.csv")
"""Every file a capture writes, which the next capture into the same directory deletes first."""


def clear_previous_capture(outdir: Path) -> int:
    """Delete every file an earlier capture wrote into ``outdir`` and return how many went."""
    stale: list[Path] = [path for pattern in CAPTURE_GLOBS for path in outdir.glob(pattern)]
    for path in stale:
        path.unlink()

    return len(stale)


EXACT = "%.17g"
"""Round-trips float64 without loss. See the module docstring -- the default does not."""


def write(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, float_format=EXACT)


def gated_archetypes() -> list[archetypes.Archetype]:
    """Return every registered archetype but DeadCatBounce, whose loop the four fixed paths run."""
    return [
        archetype
        for archetype in archetypes.all_archetypes()
        if archetype.name != archetypes.DEADCATBOUNCE.name
    ]


def capture_archetypes(
    bars: pd.DataFrame,
    instrument: Instrument,
    *,
    price_basis: context.PriceBasis,
) -> dict[str, pd.DataFrame]:
    """Return a trade log per gated archetype, at its defaults and live costs, keyed by file name."""
    defaults: list[tuple[archetypes.Archetype, archetypes.Params]] = [
        (archetype, costs.LIVE.apply(archetype.params_cls())) for archetype in gated_archetypes()
    ]
    spec: context.ContextSpec = context.ContextSpec()
    for archetype, params in defaults:
        spec = spec | sweep.Grid.of(params, archetype=archetype).required_context()
    data: context.Dataset = context.prepare(bars, spec, price_basis=price_basis)

    logs: dict[str, pd.DataFrame] = {}
    for archetype, params in defaults:
        log: pd.DataFrame = archetype.run(data, params, instrument)
        if log.empty:
            msg: str = f"{archetype.name} traded nothing at its defaults, so its log would gate nothing"
            raise EmptyCaptureError(msg)

        logs[f"defaults_{archetype.name}.csv"] = log
        logger.info("  %s at its defaults: %s legs", archetype.name, f"{len(log):,}")

    return logs


def capture(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    logger.info("cleared %d files an earlier capture left in %s", clear_previous_capture(outdir), outdir)

    contract: ContractId = ContractId.parse(CONTRACT)
    bars = ingest.load_contract(contract)
    logger.info("%s: %s bars  %s -> %s", CONTRACT, f"{len(bars):,}", bars.index[0], bars.index[-1])

    # 5 runs first, and is written last, because it is the path that refuses: a refusal leaves
    # nothing behind to compare.
    per_archetype: dict[str, pd.DataFrame] = capture_archetypes(
        bars,
        contract.instrument,
        price_basis=context.PriceBasis.RAW,
    )

    # 1. The pinned reconciliation window. These two settings are what reproduce the
    #    stored pre-fix run; do not "modernise" them.
    recon = DeadCatParams(
        ema_period=21,
        slow_sma_period=175,
        fast_sma_period=60,
        use_ema=True,
        use_slow_sma=True,
        use_fast_sma=True,
        use_vwap=True,
        require_previous_green=True,
        require_new_high=True,
        fill_limit_on_touch=True,
        ambiguity_policy=0,
    )
    recon_spec = context.ContextSpec(
        ma_keys=conditions.ma_keys(ema=(21,), sma=(60, 175)),
        needs_vwap=True,
    )
    data = context.prepare(bars, recon_spec)
    write(run_deadcat(data, recon, MNQ), outdir / "recon.csv")

    # 2 and 3. Current settings with costs, through both instrument specs.
    live = DeadCatParams(commission_per_contract=1.24, slippage_ticks=1.0)
    data = context.prepare(
        bars,
        context.ContextSpec(
            ma_keys=conditions.ma_keys(
                ema=(live.ema_period,),
                sma=(live.fast_sma_period, live.slow_sma_period),
            ),
            needs_vwap=True,
        ),
    )
    live_trades = run_deadcat(data, live, MNQ)
    write(live_trades, outdir / "live_mnq.csv")
    write(run_deadcat(data, live, NQ), outdir / "live_nq.csv")
    pd.Series(stats.summarise(live_trades).as_dict()).to_csv(outdir / "live_summary.csv", float_format=EXACT)
    logger.info("  single-contract legs: recon and live captured (%s live)", f"{len(live_trades):,}")

    # 4. A real sweep, both execution paths.
    continuous = splice.load_continuous("MNQ", back_adjust=True)
    continuous = continuous[continuous.index >= SWEEP_FROM]
    grid = sweep.Grid.of(
        DeadCatParams(commission_per_contract=1.24, slippage_ticks=1.0),
        ema_period=[11, 21],
        fast_sma_period=[60, 80],
        use_vwap=[True, False],
    )
    prepared = sweep.prepare_for(continuous, grid)
    serial, logs = sweep.sweep(continuous, grid, MNQ, data=prepared, keep_trades=True)
    write(serial, outdir / "sweep_serial.csv")
    parallel, _ = sweep.sweep(continuous, grid, MNQ, data=prepared, n_jobs=4)
    write(parallel, outdir / "sweep_parallel.csv")
    for combo_id, log in sorted(logs.items()):
        write(log, outdir / f"sweep_trades_{combo_id}.csv")
    legs = sum(len(v) for v in logs.values())
    logger.info(
        "  %s continuous bars, %d combos, %s legs",
        f"{len(continuous):,}",
        len(serial),
        f"{legs:,}",
    )

    # 5. Every other registered archetype's loop, which the four paths above do not run.
    for name, log in per_archetype.items():
        write(log, outdir / name)
    logger.info("")
    logger.info("wrote %d files to %s", len(list(outdir.iterdir())), outdir)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    if len(argv) != EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    logger.info("purged %d stale JIT cache files", purge_jit_cache())
    capture(Path(argv[1]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
