"""Can a NamedTuple carry the loop's scalar parameters without cost or losing cache=True?

simulate_deadcat takes 23 positional parameters and _write takes 18. Grouping them is the
obvious fix, but only if Numba unboxes the tuple rather than boxing it per call, and only
if @njit(cache=True) still works -- the disk cache is what makes parallel workers cheap.
"""

import time
from typing import NamedTuple

import numpy as np
from numba import njit


class Costs(NamedTuple):
    tick_size: float
    point_value: float
    commission: float
    slippage: float


@njit(cache=True)
def with_tuple(x, c):
    total = 0.0
    for i in range(x.size):
        total += x[i] * c.tick_size * c.point_value - c.commission - c.slippage
    return total


@njit(cache=True)
def with_scalars(x, tick_size, point_value, commission, slippage):
    total = 0.0
    for i in range(x.size):
        total += x[i] * tick_size * point_value - commission - slippage
    return total


def bench(fn, *args, n=7):
    fn(*args)
    start = time.perf_counter()
    for _ in range(n):
        fn(*args)
    return (time.perf_counter() - start) / n * 1000


if __name__ == "__main__":
    x = np.random.default_rng(0).random(5_000_000)
    c = Costs(0.25, 2.0, 1.24, 0.5)

    a, b = with_tuple(x, c), with_scalars(x, *c)

    tt, ts = bench(with_tuple, x, c), bench(with_scalars, x, *c)
