"""The price channel an elastic band is measured against, and where each bar sits in it.

``Bollinger(numStdDev, period)`` decomposed into the two series it is built from, because the
multiple is what a sweep varies and **neither series depends on it** -- one grid per period
serves every multiple, so the multiple costs no memory and no precompute. Reasoning:
``docs/roadmap.md`` §M26.

No NT8-parity question of its own: both halves are :func:`nqbt.indicators.nt8_sma` and
:func:`nqbt.indicators.nt8_stddev`, pinned against NinjaTrader in ``docs/nt8-fidelity.md``
§ "Indicators".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from nqbt import indicators

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from nqbt.arrays import FloatArray, IntArray

__all__: Sequence[str] = [
    "MIN_BAND_PERIOD",
    "BandError",
    "BandGrid",
    "band_grid",
    "validate_period",
]

MIN_BAND_PERIOD = 2
"""Shortest period a band accepts. At ``1`` the standard deviation of a one-bar window is
identically zero, so the band has no width and no bar is ever outside it.
"""


class BandError(ValueError):
    """Raised for a band period no grid can be built for."""


def validate_period(period: int) -> int:
    """Return ``period`` if a band can be built at it, else raise."""
    if period < MIN_BAND_PERIOD:
        msg: str = (
            f"band_period {period} is too short; needs >= {MIN_BAND_PERIOD}, because a "
            "one-bar standard deviation is always zero and nothing is ever outside the band"
        )
        raise BandError(msg)

    return int(period)


@dataclass(slots=True)
class BandGrid:
    """Basis, dispersion and extension at every period a sweep needs, each ``[n_periods, n_bars]``.

    ``periods`` is sorted and deduplicated, so :meth:`row` is the only supported way from a
    period back to its row.
    """

    periods: IntArray
    basis: FloatArray
    """The band's midline, ``nt8_sma`` of close."""
    stddev: FloatArray
    """Population standard deviation over the same window -- the band's half-width at ``k=1``."""
    stretch: FloatArray
    """Signed extension in standard deviations, and the entry rule's whole coordinate system.

    A price is recovered from a level with ``basis + level * stddev``, so ``0.0`` is the
    midline and ``±k`` are the two bands.
    """

    def __len__(self) -> int:
        """Count the bars, not the periods."""
        return int(self.basis.shape[1])

    def row(self, period: int) -> int:
        """The row holding ``period``, or an error naming what the grid was built for."""
        idx: int = int(np.searchsorted(self.periods, period))
        if idx >= self.periods.size or self.periods[idx] != period:
            msg: str = f"band period {period} is not in this grid; built for {self.periods.tolist()}"
            raise KeyError(msg)

        return idx

    def basis_for(self, period: int) -> FloatArray:
        """One period's midline."""
        return np.asarray(self.basis[self.row(period)])

    def stddev_for(self, period: int) -> FloatArray:
        """One period's standard deviation."""
        return np.asarray(self.stddev[self.row(period)])

    def stretch_for(self, period: int) -> FloatArray:
        """One period's signed extension in standard deviations."""
        return np.asarray(self.stretch[self.row(period)])

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed."""
        return self.basis.nbytes + self.stddev.nbytes + self.stretch.nbytes


def band_grid(close: FloatArray, periods: Iterable[int]) -> BandGrid:
    """Compute the basis, standard deviation and extension at every period, once."""
    unique: IntArray = np.unique(np.asarray(list(periods), dtype=np.int64))
    if unique.size == 0:
        msg: str = "no band periods supplied"
        raise BandError(msg)

    for period in unique:
        validate_period(int(period))

    close = np.ascontiguousarray(close, dtype=np.float64)
    basis: FloatArray = np.empty((unique.size, close.size), dtype=np.float64)
    stddev: FloatArray = np.empty((unique.size, close.size), dtype=np.float64)
    stretch: FloatArray = np.empty((unique.size, close.size), dtype=np.float64)

    for i, period in enumerate(unique):
        basis[i] = indicators.nt8_sma(close, int(period))
        stddev[i] = indicators.nt8_stddev(close, int(period))
        stretch[i] = indicators.band_stretch(close, basis[i], stddev[i])

    return BandGrid(periods=unique, basis=basis, stddev=stddev, stretch=stretch)
