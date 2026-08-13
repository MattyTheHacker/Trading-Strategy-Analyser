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
    "made_new_high",
    "previous_bar_green",
    "below_series",
    "count_true",
]


@njit(cache=True)
def _inverted_hammer(
    open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> np.ndarray:
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
def _made_new_high(high: np.ndarray) -> np.ndarray:
    """``High[0] > High[1]``. The first bar has no predecessor and cannot qualify."""
    n = high.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = high[i] > high[i - 1]
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


def inverted_hammer(bars: pd.DataFrame) -> np.ndarray:
    return _inverted_hammer(
        bars["open"].to_numpy(np.float64),
        bars["high"].to_numpy(np.float64),
        bars["low"].to_numpy(np.float64),
        bars["close"].to_numpy(np.float64),
    )


def made_new_high(bars: pd.DataFrame) -> np.ndarray:
    return _made_new_high(bars["high"].to_numpy(np.float64))


def previous_bar_green(bars: pd.DataFrame) -> np.ndarray:
    return _previous_bar_green(
        bars["open"].to_numpy(np.float64), bars["close"].to_numpy(np.float64)
    )


def below_series(close: np.ndarray, series: np.ndarray) -> np.ndarray:
    """``Close < series`` -- the downtrend gate, expressed as NT8 evaluates it.

    ``DeadCatBounce.cs`` rejects when ``Close[0] > ma[0]``, so equality *passes*. Writing
    the positive form as ``close < series`` would silently drop those bars; the negation
    of the rejection is what belongs here.
    """
    return ~(close > series)


@dataclass(slots=True)
class BarGeometry:
    """Parameter-free conditions, computed once for the whole dataset."""

    inverted_hammer: np.ndarray
    made_new_high: np.ndarray
    previous_bar_green: np.ndarray

    def __len__(self) -> int:
        return self.inverted_hammer.size


def bar_geometry(bars: pd.DataFrame) -> BarGeometry:
    return BarGeometry(
        inverted_hammer=inverted_hammer(bars),
        made_new_high=made_new_high(bars),
        previous_bar_green=previous_bar_green(bars),
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
    """``Close < MA``, ``[n_periods, n_bars]`` bool."""
    values: np.ndarray | None = None
    """The raw MA values, ``[n_periods, n_bars]`` float64 -- only when explicitly kept.

    Eight bytes per element against one makes this the difference between 580 MB and
    64 MB for 39 periods over 1.65M bars, which matters once a parallel sweep starts
    handing the grid to every worker. Entry gates only ever need :attr:`below`; the
    values are needed solely by the moving-average trailing stop.
    """

    def row(self, period: int) -> int:
        idx = int(np.searchsorted(self.periods, period))
        if idx >= self.periods.size or self.periods[idx] != period:
            raise KeyError(
                f"{self.kind}({period}) is not in this grid; built for "
                f"{self.periods.tolist()}"
            )
        return idx

    def below_for(self, period: int) -> np.ndarray:
        return self.below[self.row(period)]

    def values_for(self, period: int) -> np.ndarray:
        if self.values is None:
            raise ValueError(
                "this grid kept only the boolean gate; rebuild it with keep_values=True "
                "to read raw moving-average values (needed for the MA trailing stop)"
            )
        return self.values[self.row(period)]

    @property
    def nbytes(self) -> int:
        return self.below.nbytes + (0 if self.values is None else self.values.nbytes)


def moving_average_grid(
    close: np.ndarray, periods, kind: str = "ema", *, keep_values: bool = False
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
    values = np.empty((unique.size, close.size), dtype=np.float64) if keep_values else None

    for i, period in enumerate(unique):
        ma = fn(close, int(period))
        below[i] = below_series(close, ma)
        if values is not None:
            values[i] = ma

    return MovingAverageGrid(kind=kind, periods=unique, below=below, values=values)


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
