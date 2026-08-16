"""Precomputed entry conditions, built once per dataset and reused across a sweep.

The simulation must never recompute an indicator. Everything a strategy tests is reduced
here to boolean arrays it can index into.

Conditions split into two shapes:

**Parameter-free (1D).** Candlestick geometry, "made a new high", "previous bar was
green". These depend only on the bars, so one array each covers the whole sweep.

**Parameter-dependent (2D).** ``Close > EMA(p)`` depends on the swept period ``p``, so it
cannot collapse to a single array. Instead the union of periods in the grid is computed
once into a ``[n_periods, n_bars]`` matrix and the simulation takes a row index. For
~1.65M bars and 30 periods that is ~50 MB per gate as bools -- cheap next to recomputing
an EMA for every combination.

The confluence-count pattern is supported directly: rather than requiring all N filters,
:func:`count_true` sums how many passed so the required minimum can itself be swept.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numba import njit

from nqbt import indicators

__all__ = [
    "MovingAverageGrid",
    "BarGeometry",
    "bar_geometry",
    "inverted_hammer",
    "hammer",
    "made_new_high",
    "made_new_low",
    "previous_bar_green",
    "previous_bar_red",
    "below_series",
    "above_series",
    "count_true",
]


@njit(cache=True)
def _inverted_hammer(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Upper wick at least twice the body, lower wick no larger than the body.

    Ported from ``DeadCatBounce.cs``. The ``body > 0`` requirement means a doji never
    qualifies, however long its upper wick -- with a zero body the 2x test would be
    trivially satisfied.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        body = abs(close[i] - open_[i])
        top = close[i] if close[i] > open_[i] else open_[i]
        bottom = close[i] if close[i] < open_[i] else open_[i]
        upper = high[i] - top
        lower = bottom - low[i]
        out[i] = (upper >= body * 2.0) and (lower <= body) and (body > 0.0)
    return out


@njit(cache=True)
def _hammer(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Lower wick at least twice the body, upper wick no larger than the body.

    Ported from ``PullBackAndGo.cs`` -- the mirror of :func:`_inverted_hammer` with the
    wick roles swapped, as a bullish pullback-into-an-uptrend hammer rather than a bearish
    inverted one. ``body > 0`` rules out a doji the same way.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        body = abs(close[i] - open_[i])
        top = close[i] if close[i] > open_[i] else open_[i]
        bottom = close[i] if close[i] < open_[i] else open_[i]
        upper = high[i] - top
        lower = bottom - low[i]
        out[i] = (lower >= body * 2.0) and (upper <= body) and (body > 0.0)
    return out


@njit(cache=True)
def _made_new_high(high: np.ndarray) -> np.ndarray:
    """``High[0] > High[1]``. The first bar has no predecessor and cannot qualify."""
    n = high.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = high[i] > high[i - 1]
    return out


@njit(cache=True)
def _made_new_low(low: np.ndarray) -> np.ndarray:
    """``Low[0] < Low[1]``, ``PullBackAndGo.cs``'s mirror of :func:`_made_new_high`."""
    n = low.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = low[i] < low[i - 1]
    return out


@njit(cache=True)
def _previous_bar_green(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
    """``Close[1] >= Open[1]``.

    Note the boundary: ``DeadCatBounce.cs`` rejects on ``Close[1] < Open[1]``, so a
    doji-closed previous bar (``Close[1] == Open[1]``) counts as green and passes.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = close[i - 1] >= open_[i - 1]
    return out


@njit(cache=True)
def _previous_bar_red(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
    """``Close[1] < Open[1]``.

    ``PullBackAndGo.cs`` rejects on ``Close[1] >= Open[1]``, so a doji-closed previous bar
    is **not** red and does not pass. This is the one boundary where the two strategies do
    not mirror each other: :func:`_previous_bar_green` admits a doji and this rejects one,
    which makes the pair exact complements rather than a pair that overlaps at equality.

    The C# used to read ``Close[1] > Open[1]`` here, which did make them symmetric, and the
    port followed it. The strictening cost 103 of 760 signals on MNQ 03-24 -- 13.6% -- so it
    is worth checking the operator rather than assuming the mirror holds.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = close[i - 1] < open_[i - 1]
    return out


def inverted_hammer(bars: pd.DataFrame) -> np.ndarray:
    return _inverted_hammer(
        bars["open"].to_numpy(np.float64),
        bars["high"].to_numpy(np.float64),
        bars["low"].to_numpy(np.float64),
        bars["close"].to_numpy(np.float64),
    )


def hammer(bars: pd.DataFrame) -> np.ndarray:
    return _hammer(
        bars["open"].to_numpy(np.float64),
        bars["high"].to_numpy(np.float64),
        bars["low"].to_numpy(np.float64),
        bars["close"].to_numpy(np.float64),
    )


def made_new_high(bars: pd.DataFrame) -> np.ndarray:
    return _made_new_high(bars["high"].to_numpy(np.float64))


def made_new_low(bars: pd.DataFrame) -> np.ndarray:
    return _made_new_low(bars["low"].to_numpy(np.float64))


def previous_bar_green(bars: pd.DataFrame) -> np.ndarray:
    return _previous_bar_green(bars["open"].to_numpy(np.float64), bars["close"].to_numpy(np.float64))


def previous_bar_red(bars: pd.DataFrame) -> np.ndarray:
    return _previous_bar_red(bars["open"].to_numpy(np.float64), bars["close"].to_numpy(np.float64))


def below_series(close: np.ndarray, series: np.ndarray) -> np.ndarray:
    """``Close < series`` -- the downtrend gate, expressed as NT8 evaluates it.

    ``DeadCatBounce.cs`` rejects when ``Close[0] > ma[0]``, so equality *passes*. Writing
    the positive form as ``close < series`` would silently drop those bars; the negation
    of the rejection is what belongs here.
    """
    return ~(close > series)


def above_series(close: np.ndarray, series: np.ndarray) -> np.ndarray:
    """``Close > series`` -- the uptrend gate, as ``PullBackAndGo.cs`` evaluates it.

    It rejects when ``Close[0] < ma[0]``, so equality *passes* here too -- not the negation
    of :func:`below_series`, which also passes on equality. The two overlap exactly at
    ``close == series``, independently, because each strategy's own C# chose to treat its
    own boundary that way.
    """
    return ~(close < series)


@dataclass(slots=True)
class BarGeometry:
    """Parameter-free conditions, computed once for the whole dataset."""

    inverted_hammer: np.ndarray
    hammer: np.ndarray
    made_new_high: np.ndarray
    made_new_low: np.ndarray
    previous_bar_green: np.ndarray
    previous_bar_red: np.ndarray

    def __len__(self) -> int:
        return self.inverted_hammer.size


def bar_geometry(bars: pd.DataFrame) -> BarGeometry:
    return BarGeometry(
        inverted_hammer=inverted_hammer(bars),
        hammer=hammer(bars),
        made_new_high=made_new_high(bars),
        made_new_low=made_new_low(bars),
        previous_bar_green=previous_bar_green(bars),
        previous_bar_red=previous_bar_red(bars),
    )


@dataclass(slots=True)
class MovingAverageGrid:
    """``Close < MA(p)`` for every period in a sweep, as ``[n_periods, n_bars]``.

    ``periods`` is sorted and deduplicated, so :meth:`row` is the only supported way to
    get from a period back to its row -- indexing the matrix directly with a period would
    silently return the wrong series.
    """

    kind: str
    periods: np.ndarray
    below: np.ndarray
    """``Close < MA``, ``[n_periods, n_bars]`` bool. Read as NT8's downtrend gate does --
    see :func:`below_series`."""
    above: np.ndarray
    """``Close > MA``, ``[n_periods, n_bars]`` bool, for a long-capable archetype's uptrend
    gate -- see :func:`above_series`. Computed alongside :attr:`below` from the same MA
    pass rather than lazily, since ``prepare`` already builds this grid for every archetype
    unconditionally (M17 is what makes that conditional)."""
    values: np.ndarray | None = None
    """The raw MA values, ``[n_periods, n_bars]`` float64 -- only when explicitly kept.

    Eight bytes per element against one makes this the difference between 580 MB and
    64 MB for 39 periods over 1.65M bars, which matters once a parallel sweep starts
    handing the grid to every worker. Entry gates only ever need :attr:`below` or
    :attr:`above`; the values are needed solely by the moving-average trailing stop.
    """

    def row(self, period: int) -> int:
        idx = int(np.searchsorted(self.periods, period))
        if idx >= self.periods.size or self.periods[idx] != period:
            raise KeyError(f"{self.kind}({period}) is not in this grid; built for {self.periods.tolist()}")
        return idx

    def below_for(self, period: int) -> np.ndarray:
        return self.below[self.row(period)]

    def above_for(self, period: int) -> np.ndarray:
        return self.above[self.row(period)]

    def values_for(self, period: int) -> np.ndarray:
        if self.values is None:
            raise ValueError(
                "this grid kept only the boolean gate; rebuild it with keep_values=True "
                "to read raw moving-average values (needed for the MA trailing stop)"
            )
        return self.values[self.row(period)]

    @property
    def nbytes(self) -> int:
        return self.below.nbytes + self.above.nbytes + (0 if self.values is None else self.values.nbytes)


def moving_average_grid(
    close: np.ndarray, periods: Iterable[int], kind: str = "ema", *, keep_values: bool = False
) -> MovingAverageGrid:
    """Compute every distinct MA period a sweep needs, once.

    ``kind`` selects the NT8-compatible EMA or SMA from :mod:`nqbt.indicators`. Raw
    values are discarded unless ``keep_values`` is set -- see :attr:`MovingAverageGrid.values`.
    """
    unique = np.unique(np.asarray(list(periods), dtype=np.int64))
    if unique.size == 0:
        raise ValueError("no periods supplied")
    if unique[0] < 1:
        raise ValueError(f"periods must be >= 1, got {unique[0]}")

    try:
        fn = {"ema": indicators.nt8_ema, "sma": indicators.nt8_sma}[kind]
    except KeyError:
        raise ValueError(f"unknown moving average kind {kind!r}; use 'ema' or 'sma'") from None

    close = np.ascontiguousarray(close, dtype=np.float64)
    below = np.empty((unique.size, close.size), dtype=np.bool_)
    above = np.empty((unique.size, close.size), dtype=np.bool_)
    values = np.empty((unique.size, close.size), dtype=np.float64) if keep_values else None

    for i, period in enumerate(unique):
        ma = fn(close, int(period))
        below[i] = below_series(close, ma)
        above[i] = above_series(close, ma)
        if values is not None:
            values[i] = ma

    return MovingAverageGrid(kind=kind, periods=unique, below=below, above=above, values=values)


@njit(cache=True)
def count_true(stack: np.ndarray) -> np.ndarray:
    """Per-bar count of satisfied conditions, given a ``[n_conditions, n_bars]`` stack.

    Backs the confluence pattern: instead of hardcoding that all N filters must hold, the
    strategy compares this count against a swept minimum ("at least 3 of 5").
    """
    n_cond, n_bars = stack.shape
    out = np.zeros(n_bars, dtype=np.int64)
    for c in range(n_cond):
        for i in range(n_bars):
            if stack[c, i]:
                out[i] += 1
    return out
