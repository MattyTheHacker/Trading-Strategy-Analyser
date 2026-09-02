"""Clear the sweep database and re-run the grids that still matter, stratified.

Every row stored before this was computed against a continuous series with different roll
dates, at a commission that is not the real one, and before the market-context labels
existed. Those rows are answers to a different question, so they are dropped rather than
added to -- ``docs/roadmap.md`` § "Stored sweeps -- dropped and re-run, stratified".

    ./.venv/Scripts/python.exe tools/rerun_sweeps.py            # drop, then re-run
    ./.venv/Scripts/python.exe tools/rerun_sweeps.py --n-jobs 8

**This deletes ``sweeps``, ``combos`` and ``trades``.** The drop is not optional and not
skippable, and the reason is the one above rather than a schema one: the stored rows answer a
different question, so they go rather than being appended to.

**One dimension at a time, never crossed.** Eleven strata per root -- unfiltered, then once
per regime, then once per session phase -- rather than the 32 cells the product would give.
The point is to tell "no edge anywhere" from "edge in one stratum, drowned by the others",
and each label answers that on its own; crossing them is what #48's guard exists to refuse.
Every stratum runs the same grid, so the stratum is the only thing that varies between two
comparable rows.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import TYPE_CHECKING

import duckdb

from nqbt import archetypes, context, logsetup, paths, regime, results, splice, sweep, timeofday
from nqbt.instruments import get_instrument
from nqbt.sim.types import DeadCatParams

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pandas as pd

    from nqbt.archetypes import AxisValue

logger = logging.getLogger(__name__)

ROOTS = ("MNQ", "NQ")
"""Both roots, because NQ failing on its own years is corroboration rather than a second
data point -- ``README.md`` § "Current finding"."""

COMMISSION = 1.50
"""Round-turn dollars per contract. The real figure, not the $0.74 the dropped rows carry."""

SLIPPAGE_TICKS = 1.0

GRID_AXES: dict[str, list[AxisValue]] = {
    "ema_period": [9, 15, 21, 30],
    "fast_sma_period": [40, 60, 80],
    "use_slow_sma": [True, False],
    "slow_sma_period": [120, 175],
    "use_vwap": [True, False],
}
"""96 combinations: the dropped grid minus ``ambiguity_policy``.

That axis is not swept. ``0`` is a blanket worst case, deliberately *more* pessimistic than
NT8 rather than equal to it, so half the stored rows would rank a combination against a fill
rule the prime directive rejects -- and the two policies were measured 0.009 profit factor
apart. Fixed at ``1``, which is what NT8 does.
"""

TABLES = ("trades", "combos", "sweeps")
"""Dropped in this order so a later foreign key would not have to reorder it."""


def strata() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The eleven stratifications, each an extra axis over :data:`GRID_AXES`.

    The unfiltered run comes first so every stratum has its own baseline to be read against,
    and the two labels never appear in the same grid.
    """
    yield "unfiltered", {}
    for state in regime.Regime:
        yield f"regime={state.name}", {"regime_filter": [state.bit]}
    for phase in timeofday.SessionPhase:
        yield f"phase={phase.name}", {"phase_filter": [phase.bit]}


def drop_tables(db_path: paths.Path) -> None:
    """Remove every results table, leaving the database file itself in place."""
    if not db_path.exists():
        logger.info("no database at %s; nothing to drop", db_path)

        return

    con: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        for table in TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
    finally:
        con.close()
    logger.info("dropped %s from %s", ", ".join(TABLES), db_path)


def grids() -> list[tuple[str, sweep.Grid]]:
    """One named grid per stratum, all over the same base parameters."""
    base = DeadCatParams(commission_per_contract=COMMISSION, slippage_ticks=SLIPPAGE_TICKS)

    return [
        (name, sweep.Grid(axes=GRID_AXES | extra, base=base, archetype=archetypes.DEADCATBOUNCE))
        for name, extra in strata()
    ]


def run_root(root: str, batch_id: int, *, n_jobs: int, db_path: paths.Path) -> None:
    """Sweep every stratum of one root, storing each as its own ``sweeps`` row.

    The eleven grids share one dataset built from the union of their specs, so the
    efficiency-ratio grid and the session clock are each built once rather than eleven times.
    """
    bars: pd.DataFrame = splice.load_continuous(root)
    named: list[tuple[str, sweep.Grid]] = grids()

    spec: context.ContextSpec = context.ContextSpec()
    for _, grid in named:
        spec = spec | grid.required_context()
    started: float = time.perf_counter()
    data: context.Dataset = context.prepare(bars, spec, bar_minutes=1)
    logger.info(
        "%s: %s bars  %s -> %s  prepared in %.1fs",
        root,
        f"{len(bars):,}",
        bars.index[0],
        bars.index[-1],
        time.perf_counter() - started,
    )

    for name, grid in named:
        started = time.perf_counter()
        table, _ = sweep.sweep(bars, grid, get_instrument(root), data=data, n_jobs=n_jobs)
        elapsed: float = time.perf_counter() - started
        sweep_id: int = results.save_sweep(
            table,
            root=root,
            instrument=root,
            bars=bars,
            axes=grid.axes,
            elapsed_s=elapsed,
            notes=f"{name}; ${COMMISSION:.2f} RT + {SLIPPAGE_TICKS:g} tick",
            strategy=archetypes.DEADCATBOUNCE.name,
            resolution=1,
            contract=None,
            tier2=str(archetypes.DEADCATBOUNCE.tier2),
            batch_id=batch_id,
            db_path=db_path,
        )
        logger.info(
            "  sweep %-3d %-22s %3d combos  %5.1fs  best PF %.3f  trades %s",
            sweep_id,
            name,
            len(table),
            elapsed,
            table["profit_factor"].max(),
            f"{int(table['trades'].max()):,}",
        )


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Drop the sweep tables and re-run them stratified.")
    parser.add_argument("--n-jobs", type=int, default=1, help="joblib workers; 1 stays in-process")
    parser.add_argument("--db", type=paths.Path, default=paths.SWEEPS_DB, help="results database")
    args = parser.parse_args(argv[1:])

    drop_tables(args.db)
    batch_id: int = results.next_batch_id(args.db)
    for root in ROOTS:
        run_root(root, batch_id, n_jobs=args.n_jobs, db_path=args.db)
    logger.info("")
    logger.info("batch %d: %d roots x %d strata", batch_id, len(ROOTS), len(list(strata())))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
