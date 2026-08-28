"""Can a NamedTuple carry the loop's parameters without cost or losing the disk cache?

The question #59 turned on. The answer is a property of the installed Numba rather than a
language guarantee, so re-run this before relying on it -- and **run it twice**: only the
second run can report a cache *hit*, and the disk cache is what makes parallel workers cheap.

Three claims, one per section of the output:

1. a NamedTuple argument gives a bit-identical result at the same speed as loose scalars;
2. a blob carrying **arrays** compiles and caches too, which is what ``bracket.Bars`` is;
3. ``cache=True`` only *reuses* its cache when the blob type is importable. A NamedTuple
   defined in ``__main__`` writes a cache and then misses it on every run, silently -- which
   is why the blobs live in ``nqbt.sim.bracket`` and not beside the loop that reads them.
"""

import logging
import time
from typing import NamedTuple

import numpy as np
from numba import njit

from nqbt import logsetup
from nqbt.sim.bracket import Bars, Costs

logger = logging.getLogger(__name__)


class LocalCosts(NamedTuple):
    """The same four fields, but declared here in ``__main__`` -- see claim 3."""

    tick_size: float
    point_value: float
    commission_per_contract: float
    slippage_ticks: float


@njit(cache=True)
def with_tuple(x, c):
    total = 0.0
    for i in range(x.size):
        total += x[i] * c.tick_size * c.point_value - c.commission_per_contract - c.slippage_ticks
    return total


@njit(cache=True)
def with_scalars(x, tick_size, point_value, commission, slippage):
    total = 0.0
    for i in range(x.size):
        total += x[i] * tick_size * point_value - commission - slippage
    return total


@njit(cache=True)
def with_local_tuple(x, c):
    total = 0.0
    for i in range(x.size):
        total += x[i] * c.tick_size * c.point_value - c.commission_per_contract - c.slippage_ticks
    return total


@njit(cache=True)
def with_arrays(bars, c):
    total = 0.0
    for i in range(bars.close.size):
        if bars.force_flat[i]:
            continue
        total += (bars.high[i] - bars.low[i] + bars.close[i] - bars.open_[i]) * c.tick_size
    return total


def bench(fn, *args, n=7):
    fn(*args)
    start = time.perf_counter()
    for _ in range(n):
        fn(*args)
    return (time.perf_counter() - start) / n * 1000


def cache_line(fn):
    hits = sum(fn.stats.cache_hits.values())
    misses = sum(fn.stats.cache_misses.values())
    verdict = "REUSED" if hits and not misses else "recompiled"
    return f"{fn.py_func.__name__:16s} hits={hits} misses={misses}  {verdict}"


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
        logger.info("  %s", cache_line(fn))
