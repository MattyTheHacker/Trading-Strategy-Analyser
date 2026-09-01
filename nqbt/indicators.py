"""Indicators, computed to match NinjaTrader 8 rather than the textbook.

Where NT8's implementation differs from the standard one, NT8 wins -- ``Close[0] > ema[0]`` is
a hard entry gate, so a value differing in the fourth decimal flips which bars produce a
signal. In every case so far the difference has been **seeding, not formula**, except Keltner,
which matches neither half of the usual definition.

Each function's rule and the evidence it was pinned against: ``docs/nt8-fidelity.md``,
"Indicators". TA-Lib remains in use for MACD and RSI, which no archetype reads yet and which
carry the same unpinned discrepancy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numba import njit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from nqbt.arrays import BoolArray, DateArray, FloatArray

__all__: Sequence[str] = [
    "MIN_HMA_PERIOD",
    "band_stretch",
    "new_session_flags",
    "nt8_atr",
    "nt8_bollinger",
    "nt8_ema",
    "nt8_hma",
    "nt8_keltner",
    "nt8_sma",
    "nt8_stddev",
    "nt8_true_range",
    "nt8_wma",
    "session_vwap",
    "typical_price",
]

MIN_HMA_PERIOD: int = 2
"""Shortest period an HMA takes -- NT8's ``Range(2, int.MaxValue)``. At ``1`` its inner
``WMA(period // 2)`` would have no bars to average.
"""


@njit(cache=True)
def nt8_ema(values: FloatArray, period: int) -> FloatArray:
    """Exponential moving average using NT8's recursion and seeding.

    Emits a value from index 0, seeded with ``values[0]`` rather than a warm-up average.
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out

    k = 2.0 / (1.0 + period)
    inv = 1.0 - k
    out[0] = values[0]
    for i in range(1, n):
        out[i] = values[i] * k + inv * out[i - 1]
    return out


@njit(cache=True)
def nt8_sma(values: FloatArray, period: int) -> FloatArray:
    """Simple moving average using NT8's expanding warm-up and recursive update.

    Before ``period`` bars exist the result is the average of everything so far; from then on
    it is a rolling mean maintained by add/subtract rather than re-summing the window.
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out

    out[0] = values[0]
    for i in range(1, n):
        if i >= period:
            total = out[i - 1] * period
            out[i] = (total + values[i] - values[i - period]) / period
        else:
            total = out[i - 1] * i
            out[i] = (total + values[i]) / (i + 1)
    return out


@njit(cache=True)
def nt8_wma(values: FloatArray, period: int) -> FloatArray:
    """Weighted moving average, weights ``1..k`` with the heaviest on the newest bar.

    Emits from index 0 over an expanding window, exactly as :func:`nt8_sma` does. **The
    weighted sum is rebuilt every bar rather than updated**, which is what NT8's own
    minute-bar branch does -- ``docs/nt8-fidelity.md`` § "WMA and HMA, ported from the
    NinjaScript rather than reconciled".
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        span = min(period, i + 1)
        total = 0.0
        weight = 0
        for j in range(span):
            total += (span - j) * values[i - j]
            weight += span - j
        out[i] = total / weight
    return out


def nt8_hma(values: FloatArray, period: int) -> FloatArray:
    """Hull moving average: ``WMA(2*WMA(p/2) - WMA(p), sqrt(p))``, all three NT8's WMA.

    Both inner lengths **truncate**: ``period // 2`` and ``int(sqrt(period))``. NT8 caps the
    period with ``Range(2, ...)`` and this follows -- see :data:`MIN_HMA_PERIOD`.
    """
    if period < MIN_HMA_PERIOD:
        msg: str = f"nt8_hma needs period >= {MIN_HMA_PERIOD}, got {period}; NT8 caps it with Range(2, ...)"
        raise ValueError(msg)
    half: FloatArray = nt8_wma(values, period // 2)
    full: FloatArray = nt8_wma(values, period)
    return nt8_wma(2.0 * half - full, int(np.sqrt(period)))


@njit(cache=True)
def nt8_true_range(high: FloatArray, low: FloatArray, close: FloatArray) -> FloatArray:
    """True Range: ``max(H-L, |H-prevC|, |L-prevC|)``, and the bare range at bar 0.

    The previous close is read across session and roll boundaries alike, because NT8 does not
    reset it -- ``docs/nt8-fidelity.md``.
    """
    n = high.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out

    out[0] = high[0] - low[0]
    for i in range(1, n):
        prev = close[i - 1]
        span = high[i] - low[i]
        up = abs(high[i] - prev)
        down = abs(low[i] - prev)
        out[i] = max(span, up, down)
    return out


@njit(cache=True)
def nt8_atr(high: FloatArray, low: FloatArray, close: FloatArray, period: int) -> FloatArray:
    """Average True Range, seeded NT8's way rather than Wilder's.

    Emits from bar 0: an expanding simple average of True Range until ``period`` bars exist,
    then the Wilder recursion. The seed difference persists -- the recursion never forgets it.
    """
    tr = nt8_true_range(high, low, close)
    n = tr.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out

    out[0] = tr[0]
    running = tr[0]
    for i in range(1, n):
        if i < period:
            running += tr[i]
            out[i] = running / (i + 1)
        else:
            out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


@njit(cache=True)
def nt8_stddev(values: FloatArray, period: int) -> FloatArray:
    """Population standard deviation over an expanding window capped at ``period``.

    Divisor is the sample count, not ``n-1``. **Two passes, subtracting the window mean
    explicitly**: the algebraically identical incremental update drifts -- ``docs/nt8-fidelity.md``
    §M16.
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        start = i - period + 1
        start = max(start, 0)
        count = i - start + 1

        total = 0.0
        for j in range(start, i + 1):
            total += values[j]
        mean = total / count

        acc = 0.0
        for j in range(start, i + 1):
            diff = values[j] - mean
            acc += diff * diff
        out[i] = np.sqrt(acc / count)
    return out


def nt8_bollinger(values: FloatArray, period: int, num_std: float) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Bollinger Bands as ``(upper, middle, lower)``: ``SMA +/- k * StdDev``."""
    middle: FloatArray = nt8_sma(values, period)
    spread: FloatArray = num_std * nt8_stddev(values, period)
    return middle + spread, middle, middle - spread


@njit(cache=True)
def band_stretch(values: FloatArray, basis: FloatArray, stddev: FloatArray) -> FloatArray:
    """How far each value sits from ``basis``, signed, in units of ``stddev``.

    ``2.0`` is the upper band of a two-sigma channel and ``-2.0`` the lower, so the number is
    read against a band multiple directly. **Zero wherever ``stddev`` is zero** -- a window
    with no dispersion has no extension to measure -- ``docs/roadmap.md`` §M26.
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if stddev[i] > 0.0:
            out[i] = (values[i] - basis[i]) / stddev[i]
        else:
            out[i] = 0.0
    return out


def nt8_keltner(
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    period: int,
    offset: float,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Keltner Channels as ``(upper, midline, lower)``.

    **Neither half matches the common definition**: an SMA of *typical* price, widened by the
    mean **high-low range** rather than by ATR -- ``docs/nt8-fidelity.md`` §M16.
    """
    midline: FloatArray = nt8_sma(typical_price(high, low, close), period)
    width: FloatArray = offset * nt8_sma(high - low, period)
    return midline + width, midline, midline - width


@njit(cache=True)
def typical_price(high: FloatArray, low: FloatArray, close: FloatArray) -> FloatArray:
    """``(H + L + C) / 3`` -- the price VWAP weights by volume."""
    return (high + low + close) / 3.0


@njit(cache=True)
def session_vwap(price: FloatArray, volume: FloatArray, new_session: BoolArray) -> FloatArray:
    """Volume weighted average price, re-anchored at each session open.

    Mirrors ``OrderFlowVWAP(VWAPResolution.Standard, Bars.TradingHours, ...)``, whose Standard
    resolution works from bar data rather than ticks -- ``docs/nt8-fidelity.md``. A zero-volume
    bar inherits the running value rather than dividing by zero.
    """
    n = price.size
    out = np.empty(n, dtype=np.float64)
    cum_pv = 0.0
    cum_v = 0.0

    for i in range(n):
        if new_session[i]:
            cum_pv = 0.0
            cum_v = 0.0
        v = volume[i]
        cum_pv += price[i] * v
        cum_v += v
        if cum_v > 0.0:
            out[i] = cum_pv / cum_v
        else:
            out[i] = price[i]
    return out


def new_session_flags(trading_day: DateArray) -> BoolArray:
    """Mark the first bar of each trading day in an ascending, in-session series."""
    days: DateArray = np.asarray(trading_day)
    flags: BoolArray = np.zeros(days.size, dtype=np.bool_)
    if days.size == 0:
        return flags
    flags[0] = True
    flags[1:] = days[1:] != days[:-1]
    return flags
