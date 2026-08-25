"""Parameter sweep over a strategy archetype.

Which archetype is a property of the :class:`Grid`, resolved through :mod:`nqbt.archetypes`;
nothing here names a parameter class or a run function.

Combo-major: build the dataset once in :func:`nqbt.context.prepare`, then loop combinations.
What remains per combination is a boolean AND over the precomputed gates, one pass of the
jitted simulation, and a summary taken straight off the raw leg matrix. ``n_jobs`` spreads
those over processes; the dataset is shared rather than copied -- see :func:`_sweep_parallel`.

:func:`sweep` varies parameters *inside* one :class:`~nqbt.context.Dataset`. Strategy, bar
resolution and contract each select **which dataset gets built**, and :func:`sweep_axes` is the
one mechanism for all three. Why one rather than three wrappers, and why bar-major is not
scheduled: ``docs/roadmap.md`` §M17 and §M8.
"""

from __future__ import annotations

import itertools
import logging
import math
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, NamedTuple, Unpack, cast

import pandas as pd
from joblib import Parallel, delayed, effective_n_jobs

from nqbt import archetypes, context, resample, stats, trades
from nqbt.context import ContextSpec, Dataset, PrepareOptions
from nqbt.instruments import MNQ, Instrument

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from nqbt.archetypes import Archetype, AxisValue, Params

logger = logging.getLogger(__name__)


class SweepError(RuntimeError):
    """Raised when a grid cannot be turned into a runnable set of combinations."""


@dataclass(slots=True)
class Grid:
    """Values to try for each parameter. Anything omitted keeps its default.

    ``Grid.of(ema_period=[9, 21], use_vwap=[True, False])`` is 4 combinations; every other
    field of the archetype's parameter class stays at its default for all of them.

    The archetype belongs to the grid rather than to :func:`sweep`, because it decides what
    ``base`` and ``axes`` mean.
    """

    axes: dict[str, list[AxisValue]] = field(default_factory=dict)
    base: Params = None  # type: ignore[assignment]  # __post_init__ fills it
    archetype: Archetype = archetypes.DEFAULT

    def __post_init__(self) -> None:
        if self.base is None:  # type: ignore[comparison-overlap]  # the None default above
            self.base = self.archetype.params_cls()  # type: ignore[unreachable]  # __post_init__ fills it
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
            detail = "; ".join(
                f"{axis} (inert while {toggle} is {archetypes.INERT_AT.get(toggle, False)})"
                for axis, toggle in dead.items()
            )
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

        Easy to do by accident: sweeping ``slow_sma_period`` while ``use_slow_sma`` is false
        everywhere yields identical rows and a proportional runtime bill. A toggle that is a
        mask rather than a boolean is off at its everything value -- :data:`nqbt.archetypes.INERT_AT`.
        """
        dead = {}
        for axis, toggle in self.archetype.gated_by.items():
            if axis not in self.axes:
                continue
            inert = archetypes.INERT_AT.get(toggle, False)
            values = self.axes.get(toggle, [getattr(self.base, toggle)])
            if all(value == inert for value in values):
                dead[axis] = toggle
        return dead

    @classmethod
    def of(
        cls,
        base: Params | None = None,
        *,
        archetype: Archetype | None = None,
        **axes: Iterable[AxisValue],
    ) -> Grid:
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
            yield replace(self.base, **dict(zip(names, values, strict=True)))

    def axis_values(self) -> dict[str, list[AxisValue]]:
        """Every value each parameter will take across the sweep, swept or not.

        The whole parameter set rather than just ``axes``, because a period that is never
        swept still has to have its grid built.
        """
        return {
            name: list(self.axes.get(name, [getattr(self.base, name)])) for name in self.archetype.sweepable
        }

    def required_context(self) -> ContextSpec:
        """Every precomputed series any combination in this grid will read."""
        return self.archetype.context_for(self.axis_values())


def prepare_for(bars: pd.DataFrame, grid: Grid, **kwargs: Unpack[PrepareOptions]) -> Dataset:
    """Build the shared dataset covering every series the grid needs."""
    return context.prepare(bars, grid.required_context(), **kwargs)


def run_combination(
    data: Dataset,
    params: Params,
    instrument: Instrument = MNQ,
    archetype: Archetype = archetypes.DEFAULT,
    *,
    keep_trades: bool = True,
) -> tuple[dict[str, object], pd.DataFrame | None]:
    """Simulate one combination, returning its summary row and its trade log.

    The summary always comes off the raw leg matrix, so ``keep_trades`` changes what is
    returned and never what is measured.
    """
    legs = archetype.legs(data, params, instrument)
    row = params.as_dict()
    for name in archetype.not_sweepable:
        row.pop(name, None)
    # No empty-log branch here: one policy for an empty summary, and it lives in ``stats``.
    summary = stats.summarise_legs(legs, data.day_codes).as_dict()
    log = None
    if keep_trades:
        log = trades.validate(
            trades.trades_to_frame(
                legs.matrix,
                legs.count,
                data.index,
                instrument=instrument.symbol,
                source="sim",
            ),
        )
    return {**row, **summary}, log


CHUNKS_PER_WORKER = 4
"""Chunks handed to each worker rather than one big slice, since combinations differ in cost."""


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
    *,
    keep_trades: bool,
) -> tuple[list[dict[str, object]], dict[int, pd.DataFrame]]:
    """Run combinations ``[start, stop)``. Module level so loky can pickle it.

    The worker regenerates its combinations from the grid rather than being handed a list;
    ``combinations()`` is deterministic, so ``start + offset`` is the serial path's ``combo_id``.
    """
    rows: list[dict[str, object]] = []
    logs: dict[int, pd.DataFrame] = {}
    for offset, params in enumerate(itertools.islice(grid.combinations(), start, stop)):
        combo_id = start + offset
        row, log = run_combination(data, params, instrument, grid.archetype, keep_trades=keep_trades)
        row["combo_id"] = combo_id
        rows.append(row)
        if log is not None:
            logs[combo_id] = log
    return rows, logs


def _sweep_serial(
    data: Dataset,
    grid: Grid,
    instrument: Instrument,
    *,
    keep_trades: bool,
    progress_every: int,
) -> tuple[list[dict[str, object]], dict[int, pd.DataFrame]]:
    rows: list[dict[str, object]] = []
    logs: dict[int, pd.DataFrame] = {}
    started = time.perf_counter()
    for i, params in enumerate(grid.combinations()):
        row, log = run_combination(data, params, instrument, grid.archetype, keep_trades=keep_trades)
        row["combo_id"] = i
        rows.append(row)
        if log is not None:
            logs[i] = log
        if progress_every and (i + 1) % progress_every == 0:
            rate = (i + 1) / (time.perf_counter() - started)
            logger.info("  %s/%s combos  %s/s", f"{i + 1:,}", f"{len(grid):,}", f"{rate:,.0f}")
    return rows, logs


def _sweep_parallel(
    data: Dataset,
    grid: Grid,
    instrument: Instrument,
    *,
    keep_trades: bool,
    n_jobs: int,
    chunk_size: int | None,
    progress_every: int,
) -> tuple[list[dict[str, object]], dict[int, pd.DataFrame]]:
    """Spread chunks over processes, sharing one copy of the dataset.

    The payload is :meth:`Dataset.slim`, hoisted out of the generator below so every task
    references the *same* array objects -- joblib keys its memmap cache on array identity, so
    one dump on disk is shared by every worker instead of one copy per task.
    """
    bounds = chunk_bounds(len(grid), effective_n_jobs(n_jobs), chunk_size)
    payload = data.slim()
    batches = Parallel(n_jobs=n_jobs, verbose=10 if progress_every else 0)(
        delayed(_run_chunk)(payload, grid, instrument, start, stop, keep_trades=keep_trades)
        for start, stop in bounds
    )

    rows: list[dict[str, object]] = []
    logs: dict[int, pd.DataFrame] = {}
    for chunk_rows, chunk_logs in batches:
        rows.extend(chunk_rows)
        logs.update(chunk_logs)
    # Chunks come back in submission order; sorting states the guarantee rather than
    # relying on it.
    rows.sort(key=lambda r: cast("int", r["combo_id"]))
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

    Trade logs are discarded unless ``keep_trades`` is set; re-run a shortlisted combination on
    its own to get its trades.

    ``n_jobs`` follows the joblib convention and defaults to serial, because process startup
    costs a few seconds per worker. Results are identical either way. ``progress_every`` logs a
    running rate when serial and switches joblib's own reporting on when parallel; the serial
    rate goes through ``logging``, so a caller with no handler sees nothing.
    """
    data = data if data is not None else prepare_for(bars, grid)

    if effective_n_jobs(n_jobs) == 1:
        rows, logs = _sweep_serial(
            data,
            grid,
            instrument,
            keep_trades=keep_trades,
            progress_every=progress_every,
        )
    else:
        rows, logs = _sweep_parallel(
            data,
            grid,
            instrument,
            keep_trades=keep_trades,
            n_jobs=n_jobs,
            chunk_size=chunk_size,
            progress_every=progress_every,
        )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        cols = ["combo_id"] + [c for c in frame.columns if c != "combo_id"]
        frame = frame[cols]
    return frame, logs


class AxisPoint(NamedTuple):
    """Which dataset, and which strategy on it, one block of results came from.

    A :class:`NamedTuple` so it can key the returned trade logs and expand straight into the
    results row's tag columns; :attr:`_fields` is the same four names
    :data:`nqbt.results.AXIS_COLUMNS` declares, and a test pins that.
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

    ``bars`` carries the contract axis: one frame for the spliced continuous series, or a
    ``{contract: frame}`` mapping to run each contract separately. A single frame tags every
    row with ``contract=None``, which is what that null means. The strategy axis is a **list of
    grids**, not a list of archetype names.

    Returns ``(results, logs)``. Every results row leads with the four columns of
    :class:`AxisPoint`, and ``logs`` is keyed by ``(AxisPoint, combo_id)``. **``combo_id`` is
    the grid's own index, so it means the same thing at every axis point** -- but not across
    grids, which is why ``strategy`` is part of the key.

    Comparing a profit factor across resolutions at the same period number is meaningless
    unless the periods are scaled with the bar size. Reasoning: ``docs/roadmap.md`` §M17.
    """
    grid_list = [grids] if isinstance(grids, Grid) else list(grids)
    if not grid_list:
        msg = "sweep_axes needs at least one grid"
        raise SweepError(msg)
    if not resolutions:
        msg = "resolutions is empty; pass (1,) for plain 1-minute bars"
        raise SweepError(msg)

    sources: dict[str | None, pd.DataFrame] = {}
    if isinstance(bars, pd.DataFrame):
        sources[None] = bars
    else:
        sources.update(bars)
    if not sources:
        msg = "no bars to sweep: the contract mapping is empty"
        raise SweepError(msg)

    # One spec covering every grid, so the axis point builds *one* dataset all of them read.
    spec = ContextSpec()
    for grid in grid_list:
        spec = spec | grid.required_context()

    tables: list[pd.DataFrame] = []
    logs: dict[tuple[AxisPoint, int], pd.DataFrame] = {}
    for contract, source in sources.items():
        for minutes in resolutions:
            frame = resample.resample(source, minutes)
            # ``bar_minutes`` is stated rather than inferred: this loop already knows it.
            data = context.prepare(frame, spec, bar_minutes=minutes)
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
    """Put the axis point's four columns in front of one sweep's results."""
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
    """Shortlist candidates, ignoring combinations with fewer than ``min_trades`` trades.

    The floor is not optional: the smallest samples produce the most extreme statistics, so
    without it they dominate the ranking.
    """
    if results.empty:
        return results
    viable = results[results["trades"] >= min_trades]
    if viable.empty:
        return viable
    return viable.sort_values(by, ascending=False).head(top)
