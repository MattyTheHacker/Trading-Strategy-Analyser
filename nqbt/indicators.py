"""Indicators, computed to match NinjaTrader 8 rather than the textbook.

NT8 is the ground truth this tool is measured against, so where NT8's implementation
differs from the standard one, NT8 wins. That matters most for the moving averages,
because ``Close[0] > ema[0]`` is a hard entry gate -- a value that differs in the fourth
decimal still flips which bars produce a signal.

**EMA.** TA-Lib seeds its EMA with a simple average of the first ``period`` values and
emits nothing before index ``period-1``. NT8 seeds from the raw price at bar 0 and emits a
value from bar 0 onward::

    Value[0] = CurrentBar == 0 ? Input[0]
             : Input[0] * (2/(1+Period)) + (1 - 2/(1+Period)) * Value[1]

The two converge but are not equal: for ``EMA(3)`` over ``0..9`` TA-Lib returns exactly
8.0 while NT8 returns 8.001953125.

**SMA.** NT8 averages a *partial* window before ``period`` bars have accumulated, where
TA-Lib returns NaN, and it maintains the average by recursive add/subtract rather than
re-summing the window. Both behaviours are reproduced here.

**ATR, StdDev, Bollinger and Keltner** were pinned against an NT8 export of 89,330 bars
(M16). Every rule and its evidence is in ``docs/nt8-fidelity.md``; two are worth knowing
before reading the code, because both differ from the textbook:

- ATR seeds with an expanding *simple* average of True Range, then switches to Wilder.
- Keltner is built on the **mean high-low range**, not on ATR, around an SMA of typical
  price.

TA-Lib remains in use for MACD and RSI, which no archetype reads yet and which carry the
same unpinned discrepancy.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "nt8_atr",
    "nt8_bollinger",
    "nt8_ema",
    "nt8_keltner",
    "nt8_sma",
    "nt8_stddev",
    "nt8_true_range",
    "session_vwap",
    "typical_price",
    "new_session_flags",
]


@njit(cache=True)
def nt8_ema(values: np.ndarray, period: int) -> np.ndarray:
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
def nt8_sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average using NT8's expanding warm-up and recursive update.

    Before ``period`` bars exist the result is the average of everything so far, which is
    why NT8 charts show an SMA immediately instead of a gap. From ``period`` bars on it is
    a true rolling mean, maintained the way NT8 maintains it: add the new value, subtract
    the one leaving the window.
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
def nt8_true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range: ``max(H-L, |H-prevC|, |L-prevC|)``, and the bare range at bar 0.

    The previous close is used across session and roll boundaries alike -- NT8 does not
    reset it, and on 27 of 65 session opens in the pinning window the overnight gap makes
    the difference. See ``docs/nt8-fidelity.md``.
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
        out[i] = max(span, max(up, down))
    return out


@njit(cache=True)
def nt8_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Average True Range, seeded NT8's way rather than Wilder's.

    Emits from bar 0. Until ``period`` bars exist the value is the expanding simple average
    of True Range; from then on it is the Wilder recursion
    ``(prior * (period - 1) + TR) / period``. Seeding with a plain simple average is the
    same class of difference the EMA has, and it persists: the recursion never forgets its
    seed.
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
def nt8_stddev(values: np.ndarray, period: int) -> np.ndarray:
    """Population standard deviation over an expanding window capped at ``period``.

    Divisor is the sample count, not ``n-1``, and a partial window is used before ``period``
    bars exist -- the same warm-up :func:`nt8_sma` has.

    Computed in two passes, subtracting the window mean explicitly. An incremental
    sum-of-squares update is algebraically identical and drifts: pandas' rolling standard
    deviation differs from this by up to 4.2e-07 over the pinning window, which is far
    below a tick but is not the exact agreement a pin is for.
    """
    n = values.size
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        start = i - period + 1
        if start < 0:
            start = 0
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


def nt8_bollinger(
    values: np.ndarray, period: int, num_std: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands as ``(upper, middle, lower)``.

    The midline is :func:`nt8_sma` and the bands are that midline plus and minus
    ``num_std`` times :func:`nt8_stddev` -- both exact on all 89,330 pinned bars.
    """
    middle = nt8_sma(values, period)
    spread = num_std * nt8_stddev(values, period)
    return middle + spread, middle, middle - spread


def nt8_keltner(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int, offset: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keltner Channels as ``(upper, midline, lower)``.

    **Neither half matches the common definition**, and this is the one M16 expected to be
    silently wrong. The midline is an SMA of *typical* price, not an EMA of close; the width
    is ``offset`` times the mean **high-low range**, not times ATR. Using ATR here agreed
    with NT8 on 20 of 89,330 bars.
    """
    midline = nt8_sma(typical_price(high, low, close), period)
    width = offset * nt8_sma(high - low, period)
    return midline + width, midline, midline - width


@njit(cache=True)
def typical_price(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """``(H + L + C) / 3`` -- the price VWAP weights by volume."""
    return (high + low + close) / 3.0


@njit(cache=True)
def session_vwap(
    price: np.ndarray, volume: np.ndarray, new_session: np.ndarray
) -> np.ndarray:
    """Volume weighted average price, re-anchored at each session open.

    Mirrors ``OrderFlowVWAP(VWAPResolution.Standard, Bars.TradingHours, ...)``: the
    accumulation resets at the 18:00 ET open and runs to the 17:00 ET close, and the
    Standard resolution works from bar data rather than ticks -- which is why minute bars
    are the right input here and tick data would actually *reduce* agreement with NT8.

    Bars carrying zero volume inherit the running value rather than producing a division
    by zero, which is what NT8 shows at an illiquid open.
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


def new_session_flags(trading_day: np.ndarray) -> np.ndarray:
    """Mark the first bar of each trading day in an ascending, in-session series."""
    days = np.asarray(trading_day)
    flags = np.zeros(days.size, dtype=np.bool_)
    if days.size == 0:
        return flags
    flags[0] = True
    flags[1:] = days[1:] != days[:-1]
    return flags
