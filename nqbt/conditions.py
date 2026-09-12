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
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import indicators
from nqbt.arrays import float_column, ohlc

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray

__all__: Sequence[str] = [
    "MA_KINDS",
    "BarGeometry",
    "MovingAverageError",
    "MovingAverageGrid",
    "MovingAverageKey",
    "MovingAverageKind",
    "above_series",
    "bar_geometry",
    "below_series",
    "consecutive_true",
    "count_true",
    "cross_above",
    "cross_below",
    "hammer",
    "inverted_hammer",
    "ma_key",
    "ma_keys",
    "ma_keys_from_pairs",
    "made_new_high",
    "made_new_low",
    "moving_average_grid",
    "previous_bar_green",
    "previous_bar_red",
    "prior_bar_inside",
]


@njit(cache=True)
def _inverted_hammer(open_: FloatArray, high: FloatArray, low: FloatArray, close: FloatArray) -> BoolArray:
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
def _hammer(open_: FloatArray, high: FloatArray, low: FloatArray, close: FloatArray) -> BoolArray:
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
def _made_new_high(high: FloatArray) -> BoolArray:
    """``High[0] > High[1]``. The first bar has no predecessor and cannot qualify."""
    n = high.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = high[i] > high[i - 1]

    return out


@njit(cache=True)
def _made_new_low(low: FloatArray) -> BoolArray:
    """``Low[0] < Low[1]``, ``PullBackAndGo.cs``'s mirror of :func:`_made_new_high`."""
    n = low.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = low[i] < low[i - 1]

    return out


@njit(cache=True)
def _previous_bar_green(open_: FloatArray, close: FloatArray) -> BoolArray:
    """``Close[1] >= Open[1]``, so a doji-closed previous bar counts as green and passes."""
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = close[i - 1] >= open_[i - 1]

    return out


@njit(cache=True)
def _previous_bar_red(open_: FloatArray, close: FloatArray) -> BoolArray:
    """``Close[1] < Open[1]``, so a doji-closed previous bar is **not** red and does not pass.

    The one boundary where the two archetypes do not mirror each other --
    ``docs/nt8-fidelity.md``, "The entry filters' equality boundaries".
    """
    n = open_.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(1, n):
        out[i] = close[i - 1] < open_[i - 1]

    return out


@njit(cache=True)
def _prior_bar_inside(high: FloatArray, low: FloatArray) -> BoolArray:
    """``High[1] < High[2] and Low[1] > Low[2]``, stamped on the bar whose close judges it.

    ``InsideBar.cs``. Both bounds are strict, so a bar equalling either extreme of its
    predecessor is not inside it. The first two bars have no pair behind them.
    """
    n = high.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(2, n):
        out[i] = high[i - 1] < high[i - 2] and low[i - 1] > low[i - 2]

    return out


def inverted_hammer(bars: pd.DataFrame) -> BoolArray:
    """:func:`_inverted_hammer` over a bar frame's OHLC columns."""
    return _inverted_hammer(*ohlc(bars))


def hammer(bars: pd.DataFrame) -> BoolArray:
    """:func:`_hammer` over a bar frame's OHLC columns."""
    return _hammer(*ohlc(bars))


def made_new_high(bars: pd.DataFrame) -> BoolArray:
    """:func:`_made_new_high` over a bar frame's highs."""
    return _made_new_high(float_column(bars, "high"))


def made_new_low(bars: pd.DataFrame) -> BoolArray:
    """:func:`_made_new_low` over a bar frame's lows."""
    return _made_new_low(float_column(bars, "low"))


def previous_bar_green(bars: pd.DataFrame) -> BoolArray:
    """:func:`_previous_bar_green` over a bar frame's opens and closes."""
    return _previous_bar_green(float_column(bars, "open"), float_column(bars, "close"))


def previous_bar_red(bars: pd.DataFrame) -> BoolArray:
    """:func:`_previous_bar_red` over a bar frame's opens and closes."""
    return _previous_bar_red(float_column(bars, "open"), float_column(bars, "close"))


def prior_bar_inside(bars: pd.DataFrame) -> BoolArray:
    """:func:`_prior_bar_inside` over a bar frame's highs and lows."""
    return _prior_bar_inside(float_column(bars, "high"), float_column(bars, "low"))


def below_series(close: FloatArray, series: FloatArray) -> BoolArray:
    """The downtrend gate: the negation of ``DeadCatBounce.cs``'s rejection, so equality passes.

    Writing the positive ``close < series`` would silently drop those bars.
    """
    return ~(close > series)


def above_series(close: FloatArray, series: FloatArray) -> BoolArray:
    """The uptrend gate: the negation of ``PullBackAndGo.cs``'s rejection, so equality passes.

    **Not** ``~below_series`` -- the two overlap at ``close == series`` rather than
    partitioning it. See ``docs/nt8-fidelity.md``.
    """
    return ~(close < series)


@njit(cache=True)
def _crossed(fast: FloatArray, slow: FloatArray, lookback: int, above: bool) -> BoolArray:
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


def cross_above(fast: FloatArray, slow: FloatArray, lookback: int = 1) -> BoolArray:
    """``CrossAbove(fast, slow, lookback)`` as NinjaScript evaluates it.

    True on every bar within ``lookback`` bars *of* a cross, not only on the bar the cross
    happened; ``lookback=1`` is the bar itself. Equality is resolved on the *prior* bar. Reads
    only bars ``<= i``. See ``docs/nt8-fidelity.md`` §M18.
    """
    if lookback < 1:
        msg: str = f"lookback must be >= 1, got {lookback}"
        raise ValueError(msg)

    return _crossed(
        np.ascontiguousarray(fast, dtype=np.float64),
        np.ascontiguousarray(slow, dtype=np.float64),
        int(lookback),
        True,
    )


def cross_below(fast: FloatArray, slow: FloatArray, lookback: int = 1) -> BoolArray:
    """``CrossBelow(fast, slow, lookback)`` -- :func:`cross_above` with both tests mirrored.

    Not its complement: where neither series moved past the other, both are false.
    """
    if lookback < 1:
        msg: str = f"lookback must be >= 1, got {lookback}"
        raise ValueError(msg)

    return _crossed(
        np.ascontiguousarray(fast, dtype=np.float64),
        np.ascontiguousarray(slow, dtype=np.float64),
        int(lookback),
        False,
    )


@dataclass(slots=True)
class BarGeometry:
    """Parameter-free conditions, computed once for the whole dataset."""

    inverted_hammer: BoolArray
    hammer: BoolArray
    made_new_high: BoolArray
    made_new_low: BoolArray
    previous_bar_green: BoolArray
    previous_bar_red: BoolArray
    prior_bar_inside: BoolArray

    def __len__(self) -> int:
        return self.inverted_hammer.size


def bar_geometry(bars: pd.DataFrame) -> BarGeometry:
    """Every parameter-free condition, computed once over the whole frame."""
    return BarGeometry(
        inverted_hammer=inverted_hammer(bars),
        hammer=hammer(bars),
        made_new_high=made_new_high(bars),
        made_new_low=made_new_low(bars),
        previous_bar_green=previous_bar_green(bars),
        previous_bar_red=previous_bar_red(bars),
        prior_bar_inside=prior_bar_inside(bars),
    )


class MovingAverageError(ValueError):
    """Raised for a moving-average kind no grid can be built for, or a period one refuses."""


class MovingAverageKind(NamedTuple):
    """How one kind of average is computed, and the shortest period it accepts."""

    compute: Callable[[FloatArray, int], FloatArray]
    min_period: int


class MovingAverageKey(NamedTuple):
    """One moving-average grid a sweep needs, and the pair every gate is looked up by."""

    kind: str
    period: int


MA_KINDS: Mapping[str, MovingAverageKind] = {
    "ema": MovingAverageKind(indicators.nt8_ema, 1),
    "hma": MovingAverageKind(indicators.nt8_hma, indicators.MIN_HMA_PERIOD),
    "sma": MovingAverageKind(indicators.nt8_sma, 1),
    "wma": MovingAverageKind(indicators.nt8_wma, 1),
}
"""Every kind a grid can be built for, all four matching NT8's recursion rather than the
textbook one. They do not carry the same weight of evidence: ``ema`` and ``sma`` were read out
of NinjaTrader by ``NqbtIndicatorProbe.cs`` -- ``docs/nt8-fidelity.md`` § "Indicators" --
while ``wma`` and ``hma`` were transcribed from the NinjaScript and never probed --
``docs/nt8-fidelity.md`` § "WMA and HMA, ported from the NinjaScript rather than reconciled".
"""


def ma_key(kind: str, period: int) -> MovingAverageKey:
    """Build a grid key, rejecting an unknown kind and a period that kind refuses."""
    if kind not in MA_KINDS:
        msg: str = f"unknown moving average kind {kind!r}; use one of {sorted(MA_KINDS)}"
        raise MovingAverageError(msg)

    minimum: int = MA_KINDS[kind].min_period
    if period < minimum:
        msg = f"{kind}({period}) is too short; {kind} needs period >= {minimum}"
        raise MovingAverageError(msg)

    return MovingAverageKey(kind, int(period))


def ma_keys_from_pairs(pairs: Iterable[tuple[str, int]]) -> tuple[MovingAverageKey, ...]:
    """Build the key set from explicit ``(kind, period)`` pairs, one per gate.

    The form to use when the kinds come from separate gates rather than from a literal:
    two gates sharing a kind are two pairs here, where as keyword arguments to
    :func:`ma_keys` they would be one key overwriting the other.
    """
    return tuple(sorted({ma_key(kind, int(period)) for kind, period in pairs}))


def ma_keys(**periods_by_kind: Iterable[int]) -> tuple[MovingAverageKey, ...]:
    """Build the sorted, deduplicated key set a :class:`~nqbt.context.ContextSpec` carries.

    ``ma_keys(ema=(21,), sma=(60, 175))`` is the three grids that pair of gates needs. A kind
    can only appear once, so a caller holding one pair per gate wants
    :func:`ma_keys_from_pairs` instead.
    """
    return ma_keys_from_pairs((kind, int(p)) for kind, periods in periods_by_kind.items() for p in periods)


@dataclass(slots=True)
class MovingAverageGrid:
    """``Close < MA(p)`` for every period in a sweep, as ``[n_periods, n_bars]``.

    ``periods`` is sorted and deduplicated, so :meth:`row` is the only supported way from a
    period back to its row.
    """

    kind: str
    periods: IntArray
    below: BoolArray  # ``Close < MA``, ``[n_periods, n_bars]`` bool -- see :func:`below_series`.
    above: BoolArray  # ``Close > MA``, ``[n_periods, n_bars]`` bool -- see :func:`above_series`.
    values: FloatArray | None = None
    """The raw MA values, ``[n_periods, n_bars]`` float64 -- only when explicitly kept.

    Eight bytes per element against one: 580 MB rather than 64 MB for 39 periods over 1.65M
    bars, which a parallel sweep hands to every worker.
    """

    def row(self, period: int) -> int:
        """The row holding ``period``, or an error naming what the grid was built for."""
        idx: int = int(np.searchsorted(self.periods, period))
        if idx >= self.periods.size or self.periods[idx] != period:
            msg: str = f"{self.kind}({period}) is not in this grid; built for {self.periods.tolist()}"
            raise KeyError(msg)

        return idx

    def below_for(self, period: int) -> BoolArray:
        """One period's ``Close < MA`` gate."""
        return np.asarray(self.below[self.row(period)])

    def above_for(self, period: int) -> BoolArray:
        """One period's ``Close > MA`` gate."""
        return np.asarray(self.above[self.row(period)])

    def values_for(self, period: int) -> FloatArray:
        """One period's raw moving-average values, when the grid kept them."""
        if self.values is None:
            msg: str = (
                "this grid kept only the boolean gate; rebuild it with keep_values=True "
                "to read raw moving-average values (needed for the MA trailing stop)"
            )
            raise ValueError(
                msg,
            )

        return np.asarray(self.values[self.row(period)])

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed."""
        return self.below.nbytes + self.above.nbytes + (0 if self.values is None else self.values.nbytes)


def moving_average_grid(
    close: FloatArray,
    periods: Iterable[int],
    kind: str = "ema",
    keep_values: bool = False,
) -> MovingAverageGrid:
    """Compute every distinct period one kind of average is needed at, once.

    ``kind`` selects one of :data:`MA_KINDS`. Raw values are discarded unless ``keep_values``
    is set -- see :attr:`MovingAverageGrid.values`.
    """
    unique: IntArray = np.unique(np.asarray(list(periods), dtype=np.int64))
    if unique.size == 0:
        msg: str = "no periods supplied"
        raise MovingAverageError(msg)

    for period in unique:
        ma_key(kind, int(period))
    fn: Callable[[FloatArray, int], FloatArray] = MA_KINDS[kind].compute

    close = np.ascontiguousarray(close, dtype=np.float64)
    below: BoolArray = np.empty((unique.size, close.size), dtype=np.bool_)
    above: BoolArray = np.empty((unique.size, close.size), dtype=np.bool_)
    values: FloatArray | None = np.empty((unique.size, close.size), dtype=np.float64) if keep_values else None

    for i, period in enumerate(unique):
        ma: FloatArray = fn(close, int(period))
        below[i] = below_series(close, ma)
        above[i] = above_series(close, ma)
        if values is not None:
            values[i] = ma

    return MovingAverageGrid(kind=kind, periods=unique, below=below, above=above, values=values)


@njit(cache=True)
def consecutive_true(mask: BoolArray) -> IntArray:
    """How many bars up to and including this one are ``True`` unbroken; ``0`` where it is not.

    The other axis from :func:`count_true`, which counts conditions on one bar where this
    counts bars for one condition -- ``docs/roadmap.md`` §M26.
    """
    n = mask.size
    out = np.zeros(n, dtype=np.int64)
    run = 0
    for i in range(n):
        run = run + 1 if mask[i] else 0
        out[i] = run

    return out


@njit(cache=True)
def count_true(stack: BoolArray) -> IntArray:
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
