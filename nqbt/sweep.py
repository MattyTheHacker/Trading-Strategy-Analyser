"""Parameter sweep over a strategy archetype.

Combo-major: build the dataset once, then loop combinations and run the full jitted
simulation over the whole series for each. Deliberately the straightforward shape --
correctness first. A bar-major restructuring would reuse cache better across combinations,
but it is a real complexity cost and should be justified by profiling a real sweep size
rather than assumed.

The expensive work is hoisted out of the loop entirely: candlestick geometry, session
VWAP, and the moving-average grids for every period in the grid are computed once in
:func:`nqbt.sim.runner.prepare`. What remains per combination is a boolean AND over the
precomputed gates plus one pass of the simulation -- about 26 ms over 1.65M bars.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field, replace

import pandas as pd

from nqbt import stats
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import runner
from nqbt.sim.runner import Dataset
from nqbt.sim.types import DeadCatParams

SWEEPABLE = {f for f in DeadCatParams.__slots__} - {"target_r_multiples"}


class SweepError(RuntimeError):
    """Raised when a grid cannot be turned into a runnable set of combinations."""


@dataclass(slots=True)
class Grid:
    """Values to try for each parameter. Anything omitted keeps its default.

    ``Grid(ema_period=[9, 21], use_vwap=[True, False])`` is 4 combinations; every other
    field of :class:`DeadCatParams` stays at its default for all of them.
    """

    axes: dict[str, list] = field(default_factory=dict)
    base: DeadCatParams = field(default_factory=DeadCatParams)

    def __post_init__(self) -> None:
        unknown = set(self.axes) - SWEEPABLE
        if unknown:
            raise SweepError(
                f"unknown sweep parameter(s): {sorted(unknown)}. "
                f"Sweepable: {sorted(SWEEPABLE)}"
            )
        for name, values in self.axes.items():
            if not values:
                raise SweepError(f"axis {name!r} has no values")
        dead = self.dead_axes()
        if dead:
            detail = "; ".join(f"{a} (needs {t}=True)" for a, t in dead.items())
            raise SweepError(
                f"these axes cannot affect any result: {detail}. Every combination would "
                "be identical along them, multiplying runtime for nothing. Either enable "
                "the toggle or drop the axis."
            )

    # A period only matters when its filter is switched on.
    _GATED_BY = {
        "ema_period": "use_ema",
        "fast_sma_period": "use_fast_sma",
        "slow_sma_period": "use_slow_sma",
    }

    def dead_axes(self) -> dict[str, str]:
        """Swept periods whose filter is off for every combination.

        Easy to do by accident: the NinjaScript's current defaults leave the slow SMA and
        VWAP filters disabled, so sweeping ``slow_sma_period`` across four values yields
        four identical rows and a 4x runtime bill.
        """
        dead = {}
        for axis, toggle in self._GATED_BY.items():
            if axis not in self.axes:
                continue
            values = self.axes.get(toggle, [getattr(self.base, toggle)])
            if not any(values):
                dead[axis] = toggle
        return dead

    @classmethod
    def of(cls, base: DeadCatParams | None = None, **axes) -> Grid:
        return cls(axes={k: list(v) for k, v in axes.items()}, base=base or DeadCatParams())

    def __len__(self) -> int:
        n = 1
        for values in self.axes.values():
            n *= len(values)
        return n

    def combinations(self):
        """Yield one :class:`DeadCatParams` per point in the grid."""
        if not self.axes:
            yield self.base
            return
        names = list(self.axes)
        for values in itertools.product(*(self.axes[n] for n in names)):
            yield replace(self.base, **dict(zip(names, values)))

    def required_periods(self) -> tuple[list[int], list[int]]:
        """Every EMA and SMA period any combination will ask for.

        The moving-average grids refuse a period they were not built for, so this has to
        cover the whole sweep up front rather than being discovered mid-loop.
        """
        ema = set(self.axes.get("ema_period", [self.base.ema_period]))
        sma = set(self.axes.get("fast_sma_period", [self.base.fast_sma_period]))
        sma |= set(self.axes.get("slow_sma_period", [self.base.slow_sma_period]))
        return sorted(ema), sorted(sma)


def prepare_for(bars: pd.DataFrame, grid: Grid, **kwargs) -> Dataset:
    """Build the shared dataset covering every period the grid needs."""
    ema, sma = grid.required_periods()
    return runner.prepare(bars, ema_periods=ema, sma_periods=sma, **kwargs)


def run_combination(
    data: Dataset, params: DeadCatParams, instrument: Instrument = MNQ
) -> tuple[dict, pd.DataFrame]:
    """Simulate one combination, returning its summary row and its trade log."""
    trades = runner.run_deadcat(data, params, instrument)
    row = params.as_dict()
    row.pop("target_r_multiples", None)
    if trades.empty:
        summary = {c: 0 for c in stats.Summary.columns()}
    else:
        summary = stats.summarise(trades).as_dict()
    return {**row, **summary}, trades


def sweep(
    bars: pd.DataFrame,
    grid: Grid,
    instrument: Instrument = MNQ,
    *,
    data: Dataset | None = None,
    keep_trades: bool = False,
    progress_every: int = 0,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """Run every combination in ``grid`` and return a summary table.

    Trade logs are discarded unless ``keep_trades`` is set -- a wide sweep produces far
    more trade rows than fit comfortably in memory, and the summary is what ranks
    candidates. Re-run a shortlisted combination on its own to get its trades.
    """
    data = data if data is not None else prepare_for(bars, grid)
    rows: list[dict] = []
    logs: dict[int, pd.DataFrame] = {}

    started = time.perf_counter()
    for i, params in enumerate(grid.combinations()):
        row, trades = run_combination(data, params, instrument)
        row["combo_id"] = i
        rows.append(row)
        if keep_trades:
            logs[i] = trades
        if progress_every and (i + 1) % progress_every == 0:
            rate = (i + 1) / (time.perf_counter() - started)
            print(f"  {i + 1:,}/{len(grid):,} combos  {rate:,.0f}/s")

    frame = pd.DataFrame(rows)
    if not frame.empty:
        cols = ["combo_id"] + [c for c in frame.columns if c != "combo_id"]
        frame = frame[cols]
    return frame, logs


def rank(results: pd.DataFrame, by: str = "profit_factor", top: int = 20,
         min_trades: int = 30) -> pd.DataFrame:
    """Shortlist candidates, ignoring combinations with too few trades to mean anything.

    A profit factor computed from four trades is noise, and without a floor it will
    dominate any ranking -- the smallest samples produce the most extreme statistics.
    """
    if results.empty:
        return results
    viable = results[results["trades"] >= min_trades]
    if viable.empty:
        return viable
    return viable.sort_values(by, ascending=False).head(top)
