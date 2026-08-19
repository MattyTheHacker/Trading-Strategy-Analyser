"""Market context: bars plus every derived condition, computed once and shared.

This is the half of a backtest that has nothing to do with a strategy. The same
:class:`Dataset` serves every parameter combination of a sweep, every archetype, and --
once the review layer exists -- the annotation of real trades against the market they
happened in. Nothing here knows what a trade is; :mod:`nqbt.trades` owns that, and the
two never import each other.

Everything expensive lives here -- candlestick geometry, session VWAP, the moving-average
grids -- so a combination costs only a boolean AND plus one pass of the simulation.

**What gets computed is declared, not assumed.** A :class:`ContextSpec` says which moving
averages and which series an archetype's signal will read, and :func:`prepare` builds
exactly that. Computing everything unconditionally was fine for one archetype and stops
being fine at four: with M16's Bollinger and Keltner grids and M10's regime, volume and
time-of-day labels, every sweep would pay for every archetype's needs, and the parallel
path memmaps the result to each worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import conditions, indicators, sessions

if TYPE_CHECKING:
    from nqbt.conditions import MovingAverageGrid


class ContextError(KeyError):
    """Raised when a strategy reads a series :func:`prepare` was not asked to build."""


@dataclass(frozen=True, slots=True)
class ContextSpec:
    """Everything a strategy's signal will read out of a :class:`Dataset`.

    Declared up front rather than discovered mid-loop, because the moving-average grids
    refuse a period they were not built for rather than returning a wrong row -- so the
    whole sweep's needs have to be known before the first combination runs.

    Lives here rather than beside the archetype registry because it describes a
    :class:`Dataset`, and ``context.py`` must not import from :mod:`nqbt.sim`.

    The union operator is what lets several archetypes share **one** dataset: build the
    union of their specs, prepare once, and each finds what it asked for. Without it every
    archetype needs its own ``Dataset`` and the parallel path's memmap sharing stops
    paying for itself.
    """

    ema_periods: tuple[int, ...] = ()
    sma_periods: tuple[int, ...] = ()
    atr_periods: tuple[int, ...] = ()
    needs_vwap: bool = False
    needs_ma_values: bool = False
    """Keep the raw moving-average values, not just the boolean gates.

    Eight bytes per element against one, so this is off unless something reads the numbers
    themselves: the MA trailing stop, the audit trail, and any archetype whose rule compares
    two averages to each other rather than the close to one of them."""

    def __or__(self, other: ContextSpec) -> ContextSpec:
        return ContextSpec(
            ema_periods=tuple(sorted({*self.ema_periods, *other.ema_periods})),
            sma_periods=tuple(sorted({*self.sma_periods, *other.sma_periods})),
            atr_periods=tuple(sorted({*self.atr_periods, *other.atr_periods})),
            needs_vwap=self.needs_vwap or other.needs_vwap,
            needs_ma_values=self.needs_ma_values or other.needs_ma_values,
        )

    def periods_by_kind(self) -> dict[str, tuple[int, ...]]:
        """The grids to build, keyed by kind.

        Keying by ``(kind, period)`` rather than period alone is what makes "what if the
        fast filter were an EMA rather than an SMA?" expressible at all -- today the kind
        is fixed by the field's *name*, which is the whole of #72.
        """
        return {
            kind: periods
            for kind, periods in (("ema", self.ema_periods), ("sma", self.sma_periods))
            if periods
        }


@dataclass(slots=True)
class Dataset:
    """Bars plus every condition a sweep might read, computed once.

    The moving-average grids and VWAP are present only if some archetype asked for them,
    so they are reached through :meth:`ma_gate` and :meth:`vwap_gate` rather than as bare
    attributes. Both raise :class:`ContextError` naming what was asked for and what was
    built -- a strategy reading a series nobody requested is a wiring bug, and it should
    say so rather than fail somewhere downstream on a ``None``.
    """

    bars: pd.DataFrame
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    force_flat: np.ndarray
    geometry: conditions.BarGeometry
    spec: ContextSpec
    mas: dict[str, MovingAverageGrid] = field(default_factory=dict)
    atrs: dict[int, np.ndarray] = field(default_factory=dict)
    vwap: np.ndarray | None = None
    below_vwap: np.ndarray | None = None
    above_vwap: np.ndarray | None = None
    day_codes: np.ndarray | None = None
    """Calendar day of each bar as an integer, or ``None`` for a non-datetime index.

    Days since the epoch in the index's own timezone, which is what makes daily P&L
    groupable without touching pandas. Precomputed like everything else here because the
    conversion costs about as much as a whole combination of the simulation, and the numpy
    summary path would otherwise pay it once per combination.
    """

    def __len__(self) -> int:
        return self.close.size

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.bars.index

    def grid(self, kind: str) -> MovingAverageGrid:
        """The grid for one moving-average kind, or a pointed error."""
        if kind not in self.mas:
            msg = (
                f"no {kind} grid in this dataset; prepare() was asked for "
                f"{sorted(self.mas)}. Add it to the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.mas[kind]

    def ma_gate(self, kind: str, period: int, *, above: bool) -> np.ndarray:
        """Per-bar boolean: is the close above (or below) ``kind(period)``?

        Not ``~below``: each NinjaScript treats its own equality boundary as a pass
        independently, so the two overlap exactly at ``close == ma`` rather than
        partitioning it. See ``docs/nt8-fidelity.md``.
        """
        g = self.grid(kind)
        return g.above_for(period) if above else g.below_for(period)

    def ma_values(self, kind: str, period: int) -> np.ndarray:
        """Raw moving-average values, for the audit trail and the MA trailing stop."""
        return self.grid(kind).values_for(period)

    def atr_values(self, period: int) -> np.ndarray:
        """NT8-seeded ATR for one period, or a pointed error.

        Keyed by period alone rather than by ``(kind, period)`` as the moving averages are:
        there is one ATR, and its NT8 seeding is the whole of M16's finding for it.
        """
        if period not in self.atrs:
            msg = (
                f"no ATR({period}) in this dataset; prepare() was asked for "
                f"{sorted(self.atrs)}. Add it to the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.atrs[period]

    def vwap_gate(self, *, above: bool) -> np.ndarray:
        if self.below_vwap is None or self.above_vwap is None:
            msg = (
                "no session VWAP in this dataset; prepare() was not asked for it. "
                "Set needs_vwap on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.above_vwap if above else self.below_vwap

    def vwap_values(self) -> np.ndarray:
        if self.vwap is None:
            msg = (
                "no session VWAP in this dataset; prepare() was not asked for it. "
                "Set needs_vwap on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.vwap

    @property
    def nbytes(self) -> int:
        """Bytes held by the derived arrays -- what a parallel worker is handed.

        Excludes ``bars``, which :meth:`slim` drops before the dataset crosses a process
        boundary. This is the number ``ContextSpec`` exists to keep down.
        """
        total = sum(a.nbytes for a in (self.open, self.high, self.low, self.close))
        total += self.force_flat.nbytes
        total += sum(g.nbytes for g in self.mas.values())
        total += sum(a.nbytes for a in self.atrs.values())
        for a in (self.vwap, self.below_vwap, self.above_vwap, self.day_codes):
            if a is not None:
                total += a.nbytes
        return total

    def slim(self) -> Dataset:
        """A copy carrying only what the simulation reads, for crossing a process boundary.

        ``bars`` is the expensive part -- seven columns over 1.65M rows -- and everything
        the sweep needs from it was already lifted into the plain arrays beside it. The
        one remaining use is the index, to stamp trade times, so an index-only frame is
        enough. Dropping the columns is what makes a parallel worker cheap to start.

        The arrays are shared, not copied: this is a view for shipping, not a deep copy.
        """
        return replace(self, bars=self.bars.iloc[:, :0])


def day_codes(index: pd.Index) -> np.ndarray | None:
    """Each bar's calendar day as an ``int32``, in the index's own timezone.

    ``None`` when the index is not datetime-like, which only a synthetic frame is.

    In the index's timezone rather than UTC because that is what ``DatetimeIndex.date``
    gives, and the pandas summary path groups daily P&L by exactly that. On a
    ``Europe/London`` index the two differ for half the year.
    """
    if not isinstance(index, pd.DatetimeIndex):
        return None
    local = index.tz_localize(None) if index.tz is not None else index
    return local.to_numpy().astype("datetime64[D]").astype(np.int32)


DEFAULT_SPEC = ContextSpec(ema_periods=(21,), sma_periods=(60, 175), needs_vwap=True)
"""What :func:`prepare` builds when nothing says otherwise.

Reproduces the pre-#27 behaviour, when every series was computed unconditionally, so a
caller that has not been taught to declare its needs gets what it always got rather than a
dataset with holes in it.
"""


def prepare(
    bars: pd.DataFrame,
    spec: ContextSpec = DEFAULT_SPEC,
    *,
    exit_on_close_seconds: int = 30,
    keep_ma_values: bool = False,
) -> Dataset:
    """Precompute exactly the conditions ``spec`` declares.

    The moving-average grids refuse a period they were not built for rather than returning
    a wrong row, so ``spec`` must cover every value the sweep will ask for.
    :meth:`nqbt.sweep.Grid.required_context` derives it from the grid, which is the only
    way to be sure it does.
    """
    close = bars["close"].to_numpy(np.float64)
    high = bars["high"].to_numpy(np.float64)
    low = bars["low"].to_numpy(np.float64)
    info = sessions.classify(bars.index)

    vwap = below_vwap = above_vwap = None
    if spec.needs_vwap:
        typical = indicators.typical_price(high, low, close)
        vwap = indicators.session_vwap(
            typical,
            bars["volume"].to_numpy(np.float64),
            indicators.new_session_flags(bars["trading_day"].to_numpy()),
        )
        below_vwap = conditions.below_series(close, vwap)
        above_vwap = conditions.above_series(close, vwap)

    return Dataset(
        bars=bars,
        open=bars["open"].to_numpy(np.float64),
        high=high,
        low=low,
        close=close,
        force_flat=sessions.force_flat_mask(info, exit_on_close_seconds),
        geometry=conditions.bar_geometry(bars),
        spec=spec,
        mas={
            kind: conditions.moving_average_grid(
                close,
                periods,
                kind,
                keep_values=keep_ma_values or spec.needs_ma_values,
            )
            for kind, periods in spec.periods_by_kind().items()
        },
        atrs={p: indicators.nt8_atr(high, low, close, p) for p in spec.atr_periods},
        vwap=vwap,
        below_vwap=below_vwap,
        above_vwap=above_vwap,
        day_codes=day_codes(bars.index),
    )
