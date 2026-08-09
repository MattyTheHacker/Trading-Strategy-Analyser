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

TA-Lib is still the right tool for MACD, RSI, Bollinger Bands and ATR, which no archetype
uses yet. Those carry their own NT8 discrepancies (NT8's RSI smooths differently) and will
need the same treatment when an archetype first depends on one.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "nt8_ema",
    "nt8_sma",
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
