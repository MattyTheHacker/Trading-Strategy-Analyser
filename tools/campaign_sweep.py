"""Sweep every registered archetype across resolution, market regime and session phase.

One screen over the whole registry, so "which strategy is worth improving" is a query rather
than six incomparable runs:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --strata context --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --strata phase --n-jobs 8

Both roots, the spliced continuous series, resolutions 1/2/5/10/15, at the real commission for
the root and one tick of slippage. ``--split`` re-runs the same grids on a selection window and
a held-out window instead of the whole series, which is what makes a shortlist testable rather
than a ranking of noise -- ``docs/roadmap.md`` § "Held out, and then the test it fails".

**One database per archetype**, under ``results/campaign/``. A convention rather than a
constraint since ``_append_or_create`` learned to widen a table instead of dropping what it
does not recognise; the campaign's results are already there -- ``docs/roadmap.md`` §M27.

**Strata are one dimension at a time, never crossed.** ``--strata core`` is unfiltered, then
once per regime and once per session phase; ``--strata context`` adds the volume, trend and
higher-timeframe cuts and appends to the same databases. Each dimension is also nameable on its
own -- ``unfiltered``, ``regime``, ``phase``, ``volume``, ``trend``, ``htf`` -- which is how a
held-out pass adds one at a time.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import pandas as pd

from nqbt import (
    archetypes,
    context,
    higher_timeframe,
    logsetup,
    paths,
    regime,
    resample,
    results,
    splice,
    sweep,
    timeofday,
    trend,
    volume,
)
from nqbt.instruments import get_instrument
from nqbt.sim.types import (
    STOP_ATR,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_STRETCH,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    InsideBarParams,
    InsideBarTrailingParams,
    PullBackAndGoParams,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from nqbt.archetypes import Archetype, AxisValue, Params

logger = logging.getLogger(__name__)

ROOTS = ("MNQ", "NQ")

COMMISSION: dict[str, float] = {"MNQ": 1.50, "NQ": 4.50}
"""Round-turn dollars per contract, per root. Never one figure for both -- the point value
differs tenfold and the commission does not, so MNQ's number applied to NQ flatters it."""

SLIPPAGE_TICKS = 1.0

RESOLUTIONS = (1, 2, 5, 10, 15)

SELECTION_SHARE = 0.6
"""Share of the series, by bar count, that ``--split`` selects on. The rest is held out."""

MIN_TRADES = 30
"""The floor ``sweep.rank`` applies, repeated here for the per-sweep progress line."""

CAMPAIGN_DIR = paths.RESULTS_DIR / "campaign"

NAN = float("nan")


UNFILTERED = "unfiltered"
CORE = "core"
CONTEXT = "context"
ALL_STRATA = "all"


def _unfiltered() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """No context filter at all: the baseline every other stratum is read against."""
    yield UNFILTERED, {}


def _regime() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per efficiency-ratio regime."""
    for state in regime.Regime:
        yield f"regime={state.name}", {"regime_filter": [state.bit]}


def _phase() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per session phase."""
    for phase in timeofday.SessionPhase:
        yield f"phase={phase.name}", {"phase_filter": [phase.bit]}


def _volume() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per relative-volume state."""
    for state in volume.VolumeState:
        yield f"volume={state.name}", {"volume_filter": [state.bit]}


def _trend() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per compact trend label."""
    for label in trend.Trend:
        yield f"trend={label.name}", {"trend_filter": [label.bit]}


def _higher_timeframe() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per side of the 60-minute average."""
    for side in higher_timeframe.Side:
        yield f"htf={side.name}", {"higher_timeframe_filter": [side.bit]}


STRATUM_GROUPS = {
    UNFILTERED: _unfiltered,
    "regime": _regime,
    "phase": _phase,
    "volume": _volume,
    "trend": _trend,
    "htf": _higher_timeframe,
}
"""One generator per context dimension. **Never crossed** -- one dimension at a time is what
tells "no edge anywhere" from "edge in one stratum, drowned by the others"."""

STRATUM_SETS: dict[str, tuple[str, ...]] = {
    **{group: (group,) for group in STRATUM_GROUPS},
    CORE: (UNFILTERED, "regime", "phase"),
    CONTEXT: ("volume", "trend", "htf"),
    ALL_STRATA: tuple(STRATUM_GROUPS),
}
"""Named combinations of those groups, so a later pass can append the dimensions an earlier one
skipped rather than re-running it. Every dimension is also selectable on its own, which is what
lets a held-out pass take them one at a time -- ``docs/roadmap.md`` §M27.4."""


def strata(which: str) -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The stratifications ``which`` names, unfiltered first wherever it is included."""
    for group in STRATUM_SETS[which]:
        yield from STRATUM_GROUPS[group]()


@dataclass(frozen=True, slots=True)
class Variant:
    """One base parameter set and the axes swept over it, under a name the results carry.

    A variant exists where an axis cannot express the difference: a target ladder is a tuple
    and tuples are not sweepable, and two stop modes read different axes.
    """

    name: str
    archetype: Archetype
    base: Params
    axes: dict[str, list[AxisValue]] = field(default_factory=dict)

    def sized(self) -> int:
        """How many combinations this variant's own axes make."""
        total: int = 1
        for values in self.axes.values():
            total *= len(values)
        return total


def _costed(params: Params, root: str) -> Params:
    """The same rule set with this root's real costs on it."""
    return replace(params, commission_per_contract=COMMISSION[root], slippage_ticks=SLIPPAGE_TICKS)


def deadcat_variants(root: str) -> list[Variant]:
    """One variant: the entry gates, the moving-average kind, and how far the targets sit."""
    return [
        Variant(
            name="bracket",
            archetype=archetypes.DEADCATBOUNCE,
            base=_costed(DeadCatParams(), root),
            axes={
                "ema_kind": ["ema", "sma", "wma", "hma"],
                "ema_period": [9, 15, 21, 30],
                "fast_sma_period": [40, 60, 80],
                "use_vwap": [False, True],
                "tp_multiplier": [1.0, 1.5, 2.0],
            },
        ),
    ]


def pullback_variants(root: str) -> list[Variant]:
    """One variant: all three gates are on by default, so all three periods are live."""
    return [
        Variant(
            name="ratchet",
            archetype=archetypes.PULLBACKANDGO,
            base=_costed(PullBackAndGoParams(), root),
            axes={
                "ema_kind": ["ema", "sma", "wma", "hma"],
                "ema_period": [9, 15, 21, 30],
                "fast_sma_period": [40, 60, 80],
                "slow_sma_period": [125, 175],
                "use_vwap": [False, True],
            },
        ),
    ]


def crossover_variants(root: str) -> list[Variant]:
    """Two variants, one per stop geometry, because each reads an axis the other ignores.

    Sweeping ``atr_stop_multiple`` under the swing stop would run identical combinations and
    ``dead_axes`` cannot see it -- ``.claude/rules/sweep-and-context.md``.
    """
    shared: dict[str, list[AxisValue]] = {
        "fast_kind": ["ema", "sma", "wma", "hma"],
        "fast_period": [5, 9, 13, 20],
        "slow_period": [30, 50, 100, 200],
        "tp_multiplier": [1.0, 2.0],
        "exit_on_opposite_cross": [True, False],
    }
    return [
        Variant(
            name="stop=atr",
            archetype=archetypes.EMACROSSOVER,
            base=_costed(EmaCrossoverParams(use_atr_stop=True), root),
            axes={**shared, "atr_stop_multiple": [1.5, 3.0]},
        ),
        Variant(
            name="stop=swing",
            archetype=archetypes.EMACROSSOVER,
            base=_costed(EmaCrossoverParams(use_atr_stop=False), root),
            axes={**shared, "swing_lookback": [1, 3]},
        ),
    ]


def insidebar_variants(root: str) -> list[Variant]:
    """One variant: the three gates, the breakout margin and the lopsided ATR geometry."""
    return [
        Variant(
            name="bracket",
            archetype=archetypes.INSIDEBAR,
            base=_costed(InsideBarParams(), root),
            axes={
                "ema_kind": ["ema", "hma"],
                "ema_period": [11, 22, 44],
                "fast_sma_period": [20, 35, 50],
                "slow_sma_period": [100, 200],
                "error_margin": [0.01, 0.1],
                "atr_length": [3, 14],
                "atr_multiplier": [5.0, 10.0, 20.0],
            },
        ),
    ]


def insidebartrailing_variants(root: str) -> list[Variant]:
    """One variant: InsideBar's entry against the split-lot trailing exit's own axes."""
    return [
        Variant(
            name="trailing",
            archetype=archetypes.INSIDEBARTRAILING,
            base=_costed(InsideBarTrailingParams(), root),
            axes={
                "ema_period": [11, 22, 44],
                "fast_sma_period": [20, 35, 50],
                "error_margin": [0.05, 0.1],
                "atr_length": [3, 14],
                "partial_take_profit_percentage": [0.3, 0.5, 0.6, 0.8],
                "trailing_stop_multiplier": [2.0, 5.0, 10.0],
            },
        ),
    ]


ELASTIC_LADDERS: dict[str, tuple[float, ...]] = {
    "target=-0.5s": (-0.5, NAN),
    "target=0.0s": (0.0, NAN),
    "target=+1.0s": (1.0, NAN),
    "target=+2.0s": (2.0, NAN),
}
"""Where the scaled-out leg exits, in standard deviations from the basis, signed towards the
trade. A variant each because a tuple is not a sweepable axis -- ``docs/roadmap.md`` §M26."""


def elasticband_variants(root: str) -> list[Variant]:
    """One variant per target ladder, each sweeping the entry, the stop mode and a time stop."""
    axes: dict[str, list[AxisValue]] = {
        "band_period": [10, 20, 50],
        "entry_std": [1.5, 2.0, 2.5, 3.0],
        "min_bars_outside": [1, 2],
        "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
        "max_hold_bars": [0, 30],
    }
    return [
        Variant(
            name=name,
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(target_mode=TARGET_STRETCH, target_stretch_levels=levels),
                root,
            ),
            axes=axes,
        )
        for name, levels in ELASTIC_LADDERS.items()
    ]


VARIANTS = {
    "DeadCatBounce": deadcat_variants,
    "PullBackAndGo": pullback_variants,
    "EmaCrossover": crossover_variants,
    "InsideBar": insidebar_variants,
    "InsideBarTrailing": insidebartrailing_variants,
    "ElasticBand": elasticband_variants,
}
"""Archetype name -> the variants swept for it, built per root so costs are the root's."""


def grids_for(variant: Variant, which: str) -> list[tuple[str, sweep.Grid]]:
    """One grid per stratum over ``variant``, named by the stratum."""
    return [
        (name, sweep.Grid(axes=variant.axes | extra, base=variant.base, archetype=variant.archetype))
        for name, extra in strata(which)
    ]


def windows(bars: pd.DataFrame, *, split: bool) -> list[tuple[str, pd.DataFrame]]:
    """The bar ranges to run: the whole series, or a selection window and a held-out one."""
    if not split:
        return [("full", bars)]
    cut: int = math.floor(len(bars) * SELECTION_SHARE)
    return [("selection", bars.iloc[:cut]), ("holdout", bars.iloc[cut:])]


def db_path(name: str) -> paths.Path:
    """Where one archetype's results live. Separate files, not separate tables -- see above."""
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    return CAMPAIGN_DIR / f"{name}.duckdb"


def _merged_axes(grids: list[sweep.Grid]) -> dict[str, list[AxisValue]]:
    """Every value any grid tries for any axis, for the stored ``axes`` column."""
    merged: dict[str, list[AxisValue]] = {}
    for grid in grids:
        for axis, values in grid.axes.items():
            merged[axis] = sorted({*merged.get(axis, []), *values}, key=str)
    return merged


def run_point(
    frame: pd.DataFrame,
    variants: list[Variant],
    root: str,
    minutes: int,
    window: str,
    batch_id: int,
    which: str,
    *,
    n_jobs: int,
) -> None:
    """Sweep every variant x stratum at one (root, archetype, resolution, window) point.

    The variants share one dataset built from the union of their specs, and their results are
    concatenated into a single ``sweeps`` row: a stratum is a parameter, not a dataset.
    """
    archetype: Archetype = variants[0].archetype
    named: list[tuple[str, str, sweep.Grid]] = [
        (variant.name, stratum, grid) for variant in variants for stratum, grid in grids_for(variant, which)
    ]

    spec: context.ContextSpec = context.ContextSpec()
    for _, _, grid in named:
        spec = spec | grid.required_context()
    started: float = time.perf_counter()
    data: context.Dataset = context.prepare(frame, spec, bar_minutes=minutes)
    prepared: float = time.perf_counter() - started

    tables: list[pd.DataFrame] = []
    started = time.perf_counter()
    for variant_name, stratum, grid in named:
        table, _ = sweep.sweep(frame, grid, get_instrument(root), data=data, n_jobs=n_jobs)
        table.insert(0, "variant", variant_name)
        table.insert(1, "stratum", stratum)
        table.insert(2, "window", window)
        tables.append(table)
    elapsed: float = time.perf_counter() - started

    combined: pd.DataFrame = pd.concat(tables, ignore_index=True)
    combined["combo_id"] = range(len(combined))

    sweep_id: int = results.save_sweep(
        combined,
        root=root,
        instrument=root,
        bars=frame,
        axes=_merged_axes([grid for _, _, grid in named]),
        elapsed_s=elapsed,
        notes=(
            f"campaign; window={window}; strata={which}; variants={len(variants)}; "
            f"cells={len(named) // len(variants)}; "
            f"${COMMISSION[root]:.2f} RT + {SLIPPAGE_TICKS:g} tick"
        ),
        strategy=archetype.name,
        resolution=minutes,
        contract=None,
        tier2=str(archetype.tier2),
        batch_id=batch_id,
        db_path=db_path(archetype.name),
    )
    viable: pd.DataFrame = combined[combined["trades"] >= MIN_TRADES]
    logger.info(
        "  sweep %-4d %-4s %-9s %2dm  %6s combos  prep %5.1fs  sim %6.1fs  "
        "best PF %.3f  median PF %.3f  profitable %4.1f%%",
        sweep_id,
        root,
        window,
        minutes,
        f"{len(combined):,}",
        prepared,
        elapsed,
        viable["profit_factor"].max() if len(viable) else NAN,
        viable["profit_factor"].median() if len(viable) else NAN,
        100.0 * float((viable["profit_factor"] > 1.0).mean()) if len(viable) else NAN,
    )


def planned_combinations(argv: argparse.Namespace) -> int:
    """How many combinations the requested run will simulate, before it starts."""
    per_window: int = 0
    for name in argv.strategies:
        for root in argv.roots:
            per_stratum: int = sum(variant.sized() for variant in VARIANTS[name](root))
            cells: int = len(list(strata(argv.strata)))
            per_window += per_stratum * cells * len(argv.resolutions)
    return per_window * (2 if argv.split else 1)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Sweep every archetype across resolution and context.")
    parser.add_argument("--n-jobs", type=int, default=8, help="joblib workers; 1 stays in-process")
    parser.add_argument("--split", action="store_true", help="selection and held-out windows")
    parser.add_argument("--roots", nargs="+", default=list(ROOTS))
    parser.add_argument("--strategies", nargs="+", default=list(VARIANTS))
    parser.add_argument("--resolutions", nargs="+", type=int, default=list(RESOLUTIONS))
    parser.add_argument("--strata", choices=sorted(STRATUM_SETS), default=None, help="stratifications")
    args = parser.parse_args(argv[1:])
    # A held-out test of a stratified shortlist is a smaller sample twice over, so --split
    # defaults to the unfiltered stratum alone unless one is named.
    args.strata = args.strata or (UNFILTERED if args.split else CORE)

    logger.info("planned combinations: %s", f"{planned_combinations(args):,}")
    started: float = time.perf_counter()
    for name in args.strategies:
        batch_id: int = results.next_batch_id(db_path(name))
        logger.info("")
        logger.info("=== %s (batch %d) ===", name, batch_id)
        for root in args.roots:
            variants: list[Variant] = VARIANTS[name](root)
            bars: pd.DataFrame = splice.load_continuous(root)
            for window, source in windows(bars, split=args.split):
                for minutes in args.resolutions:
                    frame: pd.DataFrame = resample.resample(source, minutes)
                    run_point(
                        frame,
                        variants,
                        root,
                        minutes,
                        window,
                        batch_id,
                        args.strata,
                        n_jobs=args.n_jobs,
                    )
    logger.info("")
    logger.info("done in %.1f min", (time.perf_counter() - started) / 60.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
