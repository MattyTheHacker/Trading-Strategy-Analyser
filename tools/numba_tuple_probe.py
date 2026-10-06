"""Check whether a NamedTuple can carry a jitted loop's parameters at no cost to speed or the cache.

Run it twice: only the second run can report a cache hit -- ``tools/README.md`` § "numba_tuple_probe.py".
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import logsetup
from nqbt.sim.bracket import Bars, Costs

if TYPE_CHECKING:
    from collections.abc import Callable

    from nqbt.arrays import FloatArray

logger = logging.getLogger(__name__)

BENCH_RUNS = 7
"""Timed calls per benchmark, after one untimed call that compiles."""


class LocalCosts(NamedTuple):
    """The same four fields, but declared here in ``__main__`` -- see claim 3."""

    tick_size: float
    point_value: float
    commission_per_contract: float
    slippage_ticks: float


@njit(cache=True)
def with_tuple(x: FloatArray, c: Costs) -> float:
    """Sum a toy P&L over ``x``, reading the costs from an importable NamedTuple."""
    total = 0.0
    for i in range(x.size):
        total += x[i] * c.tick_size * c.point_value - c.commission_per_contract - c.slippage_ticks

    return total


@njit(cache=True)
def with_scalars(
    x: FloatArray, tick_size: float, point_value: float, commission: float, slippage: float
) -> float:
    """Sum the same toy P&L, with the costs passed as four scalars."""
    total = 0.0
    for i in range(x.size):
        total += x[i] * tick_size * point_value - commission - slippage

    return total


@njit(cache=True)
def with_local_tuple(x: FloatArray, c: LocalCosts) -> float:
    """Sum the same toy P&L, reading the costs from a NamedTuple declared in ``__main__``."""
    total = 0.0
    for i in range(x.size):
        total += x[i] * c.tick_size * c.point_value - c.commission_per_contract - c.slippage_ticks

    return total


@njit(cache=True)
def with_arrays(bars: Bars, c: Costs) -> float:
    """Sum a toy figure over a ``Bars`` blob of arrays, skipping the forced-flat bars."""
    total = 0.0
    for i in range(bars.close.size):
        if bars.force_flat[i]:
            continue

        total += (bars.high[i] - bars.low[i] + bars.close[i] - bars.open_[i]) * c.tick_size

    return total


def bench[**P](fn: Callable[P, float], *args: P.args, **kwargs: P.kwargs) -> float:
    """Return the mean milliseconds per call of ``fn``, after one untimed call."""
    fn(*args, **kwargs)
    start: float = time.perf_counter()
    for _ in range(BENCH_RUNS):
        fn(*args, **kwargs)

    return (time.perf_counter() - start) / BENCH_RUNS * 1000


def cache_line(name: str, hits: int, misses: int) -> str:
    """Return one function's disk-cache line: reused when every lookup hit, recompiled otherwise."""
    verdict: str = "REUSED" if hits and not misses else "recompiled"

    return f"{name:16s} hits={hits} misses={misses}  {verdict}"


if __name__ == "__main__":
    logsetup.configure(__name__)
    x = np.random.default_rng(0).random(5_000_000)
    c = Costs(0.25, 2.0, 1.24, 0.5)
    bars = Bars(x, x + 1.0, x - 1.0, x, np.zeros(x.size, dtype=np.bool_))

    a, b = with_tuple(x, c), with_scalars(x, *c)
    logger.info("bit-identical result: %s   (%r)", a == b, a)

    tt, ts = bench(with_tuple, x, c), bench(with_scalars, x, *c)
    logger.info("namedtuple %6.1f ms   scalars %6.1f ms   ratio %.3f", tt, ts, tt / ts)

    with_arrays(bars, c)
    with_local_tuple(x, LocalCosts(*c))
    logger.info("")
    logger.info("disk cache, second run onwards -- an importable blob is what makes it reusable:")
    for fn in (with_scalars, with_tuple, with_arrays, with_local_tuple):
        hits: int = sum(fn.stats.cache_hits.values())
        misses: int = sum(fn.stats.cache_misses.values())
        logger.info("  %s", cache_line(fn.py_func.__name__, hits, misses))
