"""Parameter sweep over a strategy archetype.

Which archetype is a property of the :class:`Grid`, resolved through
:mod:`nqbt.archetypes`. Nothing here names a parameter class or a run function: the
registry supplies the legal axes, the toggle map ``dead_axes`` guards with, the series
``prepare`` has to build, and the simulation to call. That indirection is the whole of
M17 -- before it, adding a second archetype meant forking this module.

Combo-major: build the dataset once, then loop combinations and run the full jitted
simulation over the whole series for each. Deliberately the straightforward shape --
correctness first. A bar-major restructuring would reuse cache better across combinations,
but it is a real complexity cost and should be justified by profiling a real sweep size
rather than assumed.

The expensive work is hoisted out of the loop entirely: candlestick geometry, session
VWAP, and the moving-average grids for every period in the grid are computed once in
:func:`nqbt.context.prepare`. What remains per combination is a boolean AND over the
precomputed gates plus one pass of the simulation -- about 30 ms over 1.65M bars, of which
roughly 70% is pandas building and aggregating the trade log rather than the jitted loop.

``n_jobs`` spreads combinations over processes. The combinations are independent, so this
is embarrassingly parallel; the only thing that needs care is that the dataset must be
*shared* rather than copied into every worker. See :func:`_sweep_parallel`.

## Axes above the Dataset

:func:`sweep` varies parameters *inside* one :class:`~nqbt.context.Dataset`. Strategy, bar
resolution and contract are different in kind: each selects **which dataset gets built**, so
each needs its own. :func:`sweep_axes` is the one mechanism for all three -- deliberately
one rather than three wrappers, because they differ only in what varies and would otherwise
grow three incompatible ways of tagging the same results table.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, NamedTuple

import pandas as pd
from joblib import Parallel, delayed, effective_n_jobs

from nqbt import archetypes, context, resample, stats
from nqbt.context import ContextSpec, Dataset
from nqbt.instruments import MNQ, Instrument

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from nqbt.archetypes import Archetype, Params


class SweepError(RuntimeError):
    """Raised when a grid cannot be turned into a runnable set of combinations."""


@dataclass(slots=True)
class Grid:
    """Values to try for each parameter. Anything omitted keeps its default.

    ``Grid.of(ema_period=[9, 21], use_vwap=[True, False])`` is 4 combinations; every other
    field of the archetype's parameter class stays at its default for all of them.

    The archetype is a property of the grid rather than an argument to :func:`sweep`,
    because it decides what ``base`` and ``axes`` even mean -- which fields are legal, and
    which toggle gates which period. Passing them separately would let the two disagree.
    """

    axes: dict[str, list] = field(default_factory=dict)
    base: Params = None  # type: ignore[assignment]  # __post_init__ fills it
    archetype: Archetype = archetypes.DEFAULT

    def __post_init__(self) -> None:
        if self.base is None:  # type: ignore[comparison-overlap]
            self.base = self.archetype.params_cls()
        if not isinstance(self.base, self.archetype.params_cls):
            msg = (
                f"archetype {self.archetype.name!r} takes "
                f"{self.archetype.params_cls.__name__}, but base is a "
                f"{type(self.base).__name__}"
            )
            raise SweepError(
                msg,
            )
        sweepable = self.archetype.sweepable
        unknown = set(self.axes) - sweepable
        if unknown:
            msg = (
                f"unknown sweep parameter(s) for {self.archetype.name}: {sorted(unknown)}. "
                f"Sweepable: {sorted(sweepable)}"
            )
            raise SweepError(
                msg,
            )
        for name, values in self.axes.items():
            if not values:
                msg = f"axis {name!r} has no values"
                raise SweepError(msg)
        dead = self.dead_axes()
        if dead:
            detail = "; ".join(f"{a} (needs {t}=True)" for a, t in dead.items())
            msg = (
                f"these axes cannot affect any result: {detail}. Every combination would "
                "be identical along them, multiplying runtime for nothing. Either enable "
                "the toggle or drop the axis."
            )
            raise SweepError(
                msg,
            )

    def dead_axes(self) -> dict[str, str]:
        """Swept periods whose filter is off for every combination.

        Easy to do by accident: the NinjaScript's current defaults leave the slow SMA and
        VWAP filters disabled, so sweeping ``slow_sma_period`` across four values yields
        four identical rows and a 4x runtime bill.

        The gate map comes from the archetype, so every new one gets this guard rather
        than getting its own version of the same mistake.
        """
        dead = {}
        for axis, toggle in self.archetype.gated_by.items():
            if axis not in self.axes:
                continue
            values = self.axes.get(toggle, [getattr(self.base, toggle)])
            if not any(values):
                dead[axis] = toggle
        return dead

    @classmethod
    def of(cls, base: Params | None = None, *, archetype: Archetype | None = None, **axes) -> Grid:
        """Build a grid, inferring the archetype from ``base`` when it is unambiguous."""
        if archetype is None:
            archetype = archetypes.for_params(base) if base is not None else archetypes.DEFAULT
        return cls(
            axes={k: list(v) for k, v in axes.items()},
            base=base if base is not None else archetype.params_cls(),
            archetype=archetype,
        )

    def __len__(self) -> int:
        n = 1
        for values in self.axes.values():
            n *= len(values)
        return n

    def combinations(self) -> Iterator[Params]:
        """Yield one parameter instance per point in the grid."""
        if not self.axes:
            yield self.base
            return
        names = list(self.axes)
        for values in itertools.product(*(self.axes[n] for n in names)):
            yield replace(self.base, **dict(zip(names, values, strict=False)))

    def axis_values(self) -> dict[str, list]:
        """Every value each parameter will take across the sweep, swept or not.

        The archetype reads this to declare its context needs. It is deliberately the
        whole parameter set rather than just ``axes``: a period that is *never* swept
        still has to have its grid built, and reading only the axes is how a default
        period gets silently left out.
        """
        return {
            name: list(self.axes.get(name, [getattr(self.base, name)])) for name in self.archetype.sweepable
        }

    def required_context(self) -> ContextSpec:
        """Every precomputed series any combination in this grid will read."""
        return self.archetype.context_for(self.axis_values())


def prepare_for(bars: pd.DataFrame, grid: Grid, **kwargs) -> Dataset:
    """Build the shared dataset covering every series the grid needs."""
    return context.prepare(bars, grid.required_context(), **kwargs)


def run_combination(
    data: Dataset,
    params: Params,
    instrument: Instrument = MNQ,
    archetype: Archetype = archetypes.DEFAULT,
) -> tuple[dict, pd.DataFrame]:
    """Simulate one combination, returning its summary row and its trade log."""
    trades = archetype.run(data, params, instrument)
    row = params.as_dict()
    for name in archetype.not_sweepable:
        row.pop(name, None)
    # No empty-log branch here on purpose. There used to be one, building an all-int zero
    # dict, and it disagreed with ``summarise``'s own empty case on the dtype of 22 of the
    # 28 columns -- which reaches DuckDB, where a barren combination could then define a
    # column's type for the whole table. One policy, and it lives in ``stats``.
    summary = stats.summarise(trades).as_dict()
    return {**row, **summary}, trades


CHUNKS_PER_WORKER = 4
"""Chunks handed to each worker rather than one big slice.

Combinations are not equal in cost -- a permissive filter set produces several times the
trades of a strict one -- so a single slice per worker leaves cores idle at the end.
Four is enough to even that out while staying far above the per-task overhead, which is
tens of microseconds against a combination's tens of milliseconds.
"""


def chunk_bounds(total: int, n_workers: int, chunk_size: int | None = None) -> list[tuple[int, int]]:
    """Half-open ``[start, stop)`` ranges covering ``total`` combinations exactly once."""
    if total <= 0:
        return []
    if chunk_size is None:
        chunk_size = max(1, math.ceil(total / max(1, n_workers * CHUNKS_PER_WORKER)))
    return [(s, min(s + chunk_size, total)) for s in range(0, total, chunk_size)]


def _run_chunk(
    data: Dataset,
    grid: Grid,
    instrument: Instrument,
    start: int,
    stop: int,
    keep_trades: bool,
) -> tuple[list[dict], dict[int, pd.DataFrame]]:
    """Run combinations ``[start, stop)``. Module level so loky can pickle it.

    The worker regenerates its own combinations from the grid rather than being handed a
    materialised list: a grid is a handful of small lists whatever its size, and
    ``combinations()`` is deterministic, so ``start + offset`` is the same ``combo_id``
    the serial path would assign.
    """
    rows: list[dict] = []
    logs: dict[int, pd.DataFrame] = {}
    for offset, params in enumerate(itertools.islice(grid.combinations(), start, stop)):
        combo_id = start + offset
        row, trades = run_combination(data, params, instrument, grid.archetype)
        row["combo_id"] = combo_id
        rows.append(row)
        if keep_trades:
            logs[combo_id] = trades
    return rows, logs


def _sweep_serial(
    data: Dataset,
    grid: Grid,
    instrument: Instrument,
    keep_trades: bool,
    progress_every: int,
) -> tuple[list[dict], dict[int, pd.DataFrame]]:
    rows: list[dict] = []
    logs: dict[int, pd.DataFrame] = {}
    started = time.perf_counter()
    for i, params in enumerate(grid.combinations()):
        row, trades = run_combination(data, params, instrument, grid.archetype)
        row["combo_id"] = i
        rows.append(row)
        if keep_trades:
            logs[i] = trades
        if progress_every and (i + 1) % progress_every == 0:
            (i + 1) / (time.perf_counter() - started)
    return rows, logs


def _sweep_parallel(
    data: Dataset,
    grid: Grid,
    instrument: Instrument,
    keep_trades: bool,
    n_jobs: int,
    chunk_size: int | None,
    progress_every: int,
) -> tuple[list[dict], dict[int, pd.DataFrame]]:
    """Spread chunks over processes, sharing one copy of the dataset.

    Two things make this cheap rather than ruinous. The payload is
    :meth:`Dataset.slim`, which drops the bar DataFrame and keeps the arrays. And it is
    hoisted out of the generator below so that every task references the *same* array
    objects -- joblib keys its memmap cache on array identity, so one dump on disk is
    then shared by every worker instead of one copy per task.

    Workers reuse the on-disk Numba cache rather than re-JITing, which is what
    ``@njit(cache=True)`` throughout ``nqbt.sim`` is for.
    """
    bounds = chunk_bounds(len(grid), effective_n_jobs(n_jobs), chunk_size)
    payload = data.slim()
    batches = Parallel(n_jobs=n_jobs, verbose=10 if progress_every else 0)(
        delayed(_run_chunk)(payload, grid, instrument, start, stop, keep_trades) for start, stop in bounds
    )

    rows: list[dict] = []
    logs: dict[int, pd.DataFrame] = {}
    for chunk_rows, chunk_logs in batches:
        rows.extend(chunk_rows)
        logs.update(chunk_logs)
    # Chunks come back in submission order, but sorting states the guarantee rather than
    # relying on it: combo_id must mean the same thing however the sweep was run.
    rows.sort(key=lambda r: r["combo_id"])
    return rows, logs


def sweep(
    bars: pd.DataFrame,
    grid: Grid,
    instrument: Instrument = MNQ,
    *,
    data: Dataset | None = None,
    keep_trades: bool = False,
    progress_every: int = 0,
    n_jobs: int = 1,
    chunk_size: int | None = None,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """Run every combination in ``grid`` and return a summary table.

    Trade logs are discarded unless ``keep_trades`` is set -- a wide sweep produces far
    more trade rows than fit comfortably in memory, and the summary is what ranks
    candidates. Re-run a shortlisted combination on its own to get its trades.

    ``n_jobs`` follows the joblib convention: ``1`` runs in this process, ``-1`` uses
    every core. It defaults to serial because process startup costs a few seconds --
    each worker imports Numba -- which is not worth paying for a few hundred
    combinations. The results are identical either way; only the wall clock changes.
    ``progress_every`` prints a running rate when serial, and switches joblib's own
    per-task reporting on when parallel.
    """
    data = data if data is not None else prepare_for(bars, grid)

    if effective_n_jobs(n_jobs) == 1:
        rows, logs = _sweep_serial(data, grid, instrument, keep_trades, progress_every)
    else:
        rows, logs = _sweep_parallel(data, grid, instrument, keep_trades, n_jobs, chunk_size, progress_every)

    frame = pd.DataFrame(rows)
    if not frame.empty:
        cols = ["combo_id"] + [c for c in frame.columns if c != "combo_id"]
        frame = frame[cols]
    return frame, logs


class AxisPoint(NamedTuple):
    """Which dataset, and which strategy on it, one block of results came from.

    A :class:`NamedTuple` so it can key the returned trade logs and expand straight into the
    results row's tag columns -- :attr:`_fields` is deliberately the same four names
    :data:`nqbt.results.AXIS_COLUMNS` declares, and a test pins that rather than letting the
    two drift.

    ``tier2`` is **carried, not swept**: it is a property of the strategy rather than an axis
    of its own. It rides here because it has to reach the results row, where its whole job is
    to stop a ranking comparing a reconciled archetype against an unreconciled one.
    """

    strategy: str
    resolution: int
    contract: str | None
    """``None`` means the spliced continuous series, which is not any one contract."""
    tier2: str


def sweep_axes(
    bars: pd.DataFrame | Mapping[str, pd.DataFrame],
    grids: Grid | Sequence[Grid],
    instrument: Instrument = MNQ,
    *,
    resolutions: Sequence[int] = (1,),
    keep_trades: bool = False,
    n_jobs: int = 1,
    chunk_size: int | None = None,
    progress_every: int = 0,
) -> tuple[pd.DataFrame, dict[tuple[AxisPoint, int], pd.DataFrame]]:
    """Run one or more grids across strategy, resolution and contract.

    ``bars`` carries the contract axis, because a contract axis *is* which bars: pass one
    frame for the spliced continuous series, or a ``{contract: frame}`` mapping -- exactly
    what :func:`nqbt.dispersion.contract_frames` returns -- to run each contract separately.
    A single frame tags every row with ``contract=None``, which is what that null means.

    The strategy axis is a **list of grids**, not a list of archetype names. Each archetype
    has its own parameter class, so ``ema_period=[9, 21]`` is not even a legal axis of the
    next one; a single grid re-based onto another archetype would raise or, worse, silently
    sweep a different field. One grid per strategy is the only shape that can express two
    archetypes being swept over their own parameters.

    Returns ``(results, logs)``. Every results row carries the four columns of
    :class:`AxisPoint` as its leading columns, and ``logs`` is keyed by
    ``(AxisPoint, combo_id)``.

    **``combo_id`` is the grid's own index, so it means the same thing at every axis point** --
    that is what makes "combination 7 at 1 minute against combination 7 at 15 minutes" a
    comparison rather than a coincidence. It does *not* carry across grids: combination 7 of
    two different archetypes is two unrelated parameter sets, which is why ``strategy`` is
    part of the key and not a column you may drop.

    Every axis defaults to a single value, so the cost is opt-in one axis at a time. They do
    compose, and the product is a product: three grids over four resolutions over nineteen
    contracts is 228 datasets, each paying the full :func:`nqbt.context.prepare` cost.

    Comparing a profit factor across resolutions **at the same period number is meaningless**
    unless the periods are scaled with the bar size. Order lifetime, the ratchet and
    ``bars_required_to_trade`` are all counted in bars, so a resolution sweep is a family of
    related strategies rather than one strategy sampled differently.
    """
    grid_list = [grids] if isinstance(grids, Grid) else list(grids)
    if not grid_list:
        msg = "sweep_axes needs at least one grid"
        raise SweepError(msg)
    if not resolutions:
        msg = "resolutions is empty; pass (1,) for plain 1-minute bars"
        raise SweepError(msg)

    sources: Mapping[str | None, pd.DataFrame] = (
        {None: bars} if isinstance(bars, pd.DataFrame) else dict(bars)
    )
    if not sources:
        msg = "no bars to sweep: the contract mapping is empty"
        raise SweepError(msg)

    # One spec covering every grid, so the axis point builds *one* dataset that all of them
    # read. This is what ``ContextSpec.__or__`` exists for -- a dataset each would multiply
    # the memory the parallel path memmaps to every worker by the number of strategies.
    spec = ContextSpec()
    for grid in grid_list:
        spec = spec | grid.required_context()

    tables: list[pd.DataFrame] = []
    logs: dict[tuple[AxisPoint, int], pd.DataFrame] = {}
    for contract, source in sources.items():
        for minutes in resolutions:
            frame = resample.resample(source, minutes)
            data = context.prepare(frame, spec)
            for grid in grid_list:
                point = AxisPoint(
                    strategy=grid.archetype.name,
                    resolution=minutes,
                    contract=contract,
                    tier2=str(grid.archetype.tier2),
                )
                table, point_logs = sweep(
                    frame,
                    grid,
                    instrument,
                    data=data,
                    keep_trades=keep_trades,
                    n_jobs=n_jobs,
                    chunk_size=chunk_size,
                    progress_every=progress_every,
                )
                tables.append(_tag(table, point))
                for combo_id, log in point_logs.items():
                    logs[(point, combo_id)] = log

    return pd.concat(tables, ignore_index=True), logs


def _tag(table: pd.DataFrame, point: AxisPoint) -> pd.DataFrame:
    """Put the axis point's four columns in front of one sweep's results.

    In front rather than appended: these are what the row *is*, and a table whose leading
    column is ``combo_id`` invites reading two resolutions as one population.
    """
    tagged = table.copy()
    for position, name in enumerate(AxisPoint._fields):
        tagged.insert(position, name, getattr(point, name))
    return tagged


def rank(
    results: pd.DataFrame,
    by: str = "profit_factor",
    top: int = 20,
    min_trades: int = 30,
) -> pd.DataFrame:
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
