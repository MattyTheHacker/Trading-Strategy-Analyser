"""Precomputed entry conditions, built once per dataset and reused across a sweep.

The simulation must never recompute an indicator, so everything a strategy tests is reduced
here to boolean arrays it can index into. Parameter-free conditions are one array each;
parameter-dependent ones become a ``[n_periods, n_bars]`` matrix the simulation takes a row of.

**Every filter is the negation of its C#'s rejection, not the positive form**, and the
equality boundaries do not mirror between archetypes -- ``docs/nt8-fidelity.md``, "The entry
filters' equality boundaries".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numba import njit

from nqbt import indicators

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pandas as pd

__all__ = [
    "BarGeometry",
    "MovingAverageGrid",
    "above_series",
    "bar_geometry",
    "below_series",
    "count_true",
    "cross_above",
    "cross_below",
    "hammer",
    "inverted_hammer",
    "made_new_high",
    "made_new_low",
    "previous_bar_green",
    "previous_bar_red",
]


@njit(cache=True)
def _inverted_hammer(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Upper wick at least twice the body, lower wick no larger than the body.

    ``DeadCatBounce.cs``. ``body > 0`` means a doji never qualifies.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        body = abs(close[i] - open_[i])
        top = max(open_[i], close[i])
        bottom = min(open_[i], close[i])
        upper = high[i] - top
        lower = bottom - low[i]
        out[i] = (upper >= body * 2.0) and (lower <= body) and (body > 0.0)
    return out


@njit(cache=True)
def _hammer(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Lower wick at least twice the body, upper wick no larger than the body.

    ``PullBackAndGo.cs`` -- :func:`_inverted_hammer` with the wick roles swapped.
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        body = abs(close[i] - open_[i])
        top = max(open_[i], close[i])
        bottom = min(open_[i], close[i])
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
    """``Close[1] >= Open[1]``, so a doji-closed previous bar counts as green and passes."""
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = close[i - 1] >= open_[i - 1]
    return out


@njit(cache=True)
def _previous_bar_red(open_: np.ndarray, close: np.ndarray) -> np.ndarray:
    """``Close[1] < Open[1]``, so a doji-closed previous bar is **not** red and does not pass.

    The one boundary where the two archetypes do not mirror each other --
    ``docs/nt8-fidelity.md``, "The entry filters' equality boundaries".
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
    """The downtrend gate: the negation of ``DeadCatBounce.cs``'s rejection, so equality passes.

    Writing the positive ``close < series`` would silently drop those bars.
    """
    return ~(close > series)


def above_series(close: np.ndarray, series: np.ndarray) -> np.ndarray:
    """The uptrend gate: the negation of ``PullBackAndGo.cs``'s rejection, so equality passes.

    **Not** ``~below_series`` -- the two overlap at ``close == series`` rather than
    partitioning it. See ``docs/nt8-fidelity.md``.
    """
    return ~(close < series)


@njit(cache=True)
def _crossed(fast: np.ndarray, slow: np.ndarray, lookback: int, above: bool) -> np.ndarray:
    """NT8's ``CrossAbove``/``CrossBelow``: did the cross happen within ``lookback`` bars?"""
    n = fast.size
    out = np.zeros(n, dtype=np.bool_)
    last = -1
    for i in range(1, n):
        if above:
            crossed = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
        else:
            crossed = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
        if crossed:
            last = i
        if last >= 0 and i - last < lookback:
            out[i] = True
    return out


def cross_above(fast: np.ndarray, slow: np.ndarray, lookback: int = 1) -> np.ndarray:
    """``CrossAbove(fast, slow, lookback)`` as NinjaScript evaluates it.

    True on every bar within ``lookback`` bars *of* a cross, not only on the bar the cross
    happened; ``lookback=1`` is the bar itself. Equality is resolved on the *prior* bar. Reads
    only bars ``<= i``. See ``docs/nt8-fidelity.md`` §M18.
    """
    if lookback < 1:
        msg = f"lookback must be >= 1, got {lookback}"
        raise ValueError(msg)
    return _crossed(
        np.ascontiguousarray(fast, dtype=np.float64),
        np.ascontiguousarray(slow, dtype=np.float64),
        int(lookback),
        True,  # noqa: FBT003
    )


def cross_below(fast: np.ndarray, slow: np.ndarray, lookback: int = 1) -> np.ndarray:
    """``CrossBelow(fast, slow, lookback)`` -- :func:`cross_above` with both tests mirrored.

    Not its complement: where neither series moved past the other, both are false.
    """
    if lookback < 1:
        msg = f"lookback must be >= 1, got {lookback}"
        raise ValueError(msg)
    return _crossed(
        np.ascontiguousarray(fast, dtype=np.float64),
        np.ascontiguousarray(slow, dtype=np.float64),
        int(lookback),
        False,  # noqa: FBT003
    )


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

    ``periods`` is sorted and deduplicated, so :meth:`row` is the only supported way from a
    period back to its row.
    """

    kind: str
    periods: np.ndarray
    below: np.ndarray
    """``Close < MA``, ``[n_periods, n_bars]`` bool -- see :func:`below_series`."""
    above: np.ndarray
    """``Close > MA``, ``[n_periods, n_bars]`` bool -- see :func:`above_series`."""
    values: np.ndarray | None = None
    """The raw MA values, ``[n_periods, n_bars]`` float64 -- only when explicitly kept.

    Eight bytes per element against one: 580 MB rather than 64 MB for 39 periods over 1.65M
    bars, which a parallel sweep hands to every worker.
    """

    def row(self, period: int) -> int:
        idx = int(np.searchsorted(self.periods, period))
        if idx >= self.periods.size or self.periods[idx] != period:
            msg = f"{self.kind}({period}) is not in this grid; built for {self.periods.tolist()}"
            raise KeyError(msg)
        return idx

    def below_for(self, period: int) -> np.ndarray:
        return self.below[self.row(period)]

    def above_for(self, period: int) -> np.ndarray:
        return self.above[self.row(period)]

    def values_for(self, period: int) -> np.ndarray:
        if self.values is None:
            msg = (
                "this grid kept only the boolean gate; rebuild it with keep_values=True "
                "to read raw moving-average values (needed for the MA trailing stop)"
            )
            raise ValueError(
                msg,
            )
        return self.values[self.row(period)]

    @property
    def nbytes(self) -> int:
        return self.below.nbytes + self.above.nbytes + (0 if self.values is None else self.values.nbytes)


def moving_average_grid(
    close: np.ndarray,
    periods: Iterable[int],
    kind: str = "ema",
    *,
    keep_values: bool = False,
) -> MovingAverageGrid:
    """Compute every distinct MA period a sweep needs, once.

    ``kind`` selects the NT8-compatible EMA or SMA from :mod:`nqbt.indicators`. Raw
    values are discarded unless ``keep_values`` is set -- see :attr:`MovingAverageGrid.values`.
    """
    unique = np.unique(np.asarray(list(periods), dtype=np.int64))
    if unique.size == 0:
        msg = "no periods supplied"
        raise ValueError(msg)
    if unique[0] < 1:
        msg = f"periods must be >= 1, got {unique[0]}"
        raise ValueError(msg)

    try:
        fn = {"ema": indicators.nt8_ema, "sma": indicators.nt8_sma}[kind]
    except KeyError:
        msg = f"unknown moving average kind {kind!r}; use 'ema' or 'sma'"
        raise ValueError(msg) from None

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

    Backs the confluence pattern: "at least 3 of 5", with the minimum itself sweepable.
    """
    n_cond, n_bars = stack.shape
    out = np.zeros(n_bars, dtype=np.int64)
    for c in range(n_cond):
        for i in range(n_bars):
            if stack[c, i]:
                out[i] += 1
    return out
