"""Directional, consolidating, or unclassifiable: the market-regime label.

One scalar per bar -- Kaufman's efficiency ratio, ``|close[t] - close[t-n]| / sum|diff(close)|``
over the lookback -- cut by two thresholds into three labels. Bounded 0-1, no TA-Lib
dependency, and therefore **no NT8-parity question**: nothing here is a fill rule and nothing
here has a NinjaScript counterpart.

The band *between* the thresholds is the unclassifiable no-trade state, a real label rather
than a special case. Warm-up bars, which the lookback cannot reach back from, are
:data:`UNDEFINED` instead -- not measured is not the same as measured and inconclusive.

A regime set is carried as a bitmask integer so that it is a legal sweep axis, exactly as
:mod:`nqbt.timeofday` carries a phase set. Thresholds, equality boundaries and why the window
sum is recomputed rather than rolled: ``docs/roadmap.md`` §M10.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np
from numba import njit

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from nqbt.arrays import BoolArray, FloatArray, IntArray, LabelArray

__all__: Sequence[str] = [
    "ALL_REGIMES",
    "UNDEFINED",
    "EfficiencyRatioGrid",
    "Regime",
    "RegimeError",
    "describe_mask",
    "efficiency_ratio",
    "efficiency_ratio_grid",
    "gate",
    "label",
    "regimes_in",
    "regimes_mask",
    "validate_lookback",
    "validate_mask",
    "validate_thresholds",
]

UNDEFINED = -1
"""Label for a bar the lookback cannot reach back from. Negative, not a fourth regime --
``docs/roadmap.md`` §M10.1.
"""

MIN_LOOKBACK = 2
"""A one-bar lookback makes numerator and denominator the same quantity, so every bar would
read 1.0. Refused rather than labelled DIRECTIONAL everywhere.
"""


class RegimeError(ValueError):
    """Raised for an impossible regime mask, lookback or pair of thresholds."""


class Regime(IntEnum):
    """The three states of the efficiency ratio, ordered by it.

    The integer values ascend with the ratio, and are also the bit positions in a filter mask.
    """

    CONSOLIDATING = 0  # Below the lower threshold: the window's net move is small against its path length.
    UNCLASSIFIABLE = 1  # Between the thresholds, both boundaries included. The deliberate no-trade state.
    DIRECTIONAL = 2  # Above the upper threshold: the window went somewhere rather than wandering.

    @property
    def bit(self) -> int:
        """The bit this regime occupies in a filter mask."""
        return 1 << int(self)


ALL_REGIMES = (1 << len(Regime)) - 1
"""Every regime: the mask that filters nothing, and the default for every archetype."""


def regimes_mask(regimes: Iterable[Regime]) -> int:
    """Combine regimes into the bitmask an archetype's ``regime_filter`` takes."""
    mask: int = 0
    for regime in regimes:
        mask |= Regime(regime).bit

    return mask


def regimes_in(mask: int) -> tuple[Regime, ...]:
    """Unpack a mask into the regimes it admits, in ascending-ratio order."""
    validate_mask(mask)

    return tuple(r for r in Regime if mask & r.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no regime owns."""
    if mask < 0 or mask & ~ALL_REGIMES:
        msg: str = f"regime mask {mask} sets bits outside 0..{ALL_REGIMES}; use Regime.bit or regimes_mask()"
        raise RegimeError(msg)

    if mask == 0:
        msg = "regime mask 0 admits no regime, so every combination along it would trade nothing"
        raise RegimeError(msg)

    return mask


def describe_mask(mask: int) -> str:
    """Render a mask as a regime list, for a results table or an error message."""
    return "+".join(r.name for r in regimes_in(mask))


def validate_lookback(lookback: int) -> int:
    """Reject a lookback the ratio is degenerate at -- see :data:`MIN_LOOKBACK`."""
    if lookback < MIN_LOOKBACK:
        msg: str = f"regime lookback must be >= {MIN_LOOKBACK}, got {lookback}"
        raise RegimeError(msg)

    return lookback


def validate_thresholds(consolidating_below: float, directional_above: float) -> None:
    """Reject thresholds that would put a bar in two regimes at once, or fall outside 0-1.

    Equal thresholds are legal and collapse the unclassifiable band onto the boundary itself.
    """
    if not 0.0 <= consolidating_below <= 1.0:
        msg: str = f"consolidating_below must lie in 0..1, got {consolidating_below}"
        raise RegimeError(msg)

    if not 0.0 <= directional_above <= 1.0:
        msg = f"directional_above must lie in 0..1, got {directional_above}"
        raise RegimeError(msg)

    if consolidating_below > directional_above:
        msg = (
            f"consolidating_below {consolidating_below} exceeds directional_above "
            f"{directional_above}, which would put a bar in both regimes at once"
        )

        raise RegimeError(msg)


@njit(cache=True)
def _efficiency_ratio(close: FloatArray, lookback: int) -> FloatArray:
    """Net move over path length, ``nan`` until ``lookback`` bars of history exist.

    The window sum is recomputed rather than maintained incrementally, and a window that
    never moved scores 0.0 rather than dividing by zero -- ``docs/roadmap.md`` §M10.1.
    """
    n = close.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(lookback, n):
        path = 0.0
        for j in range(i - lookback + 1, i + 1):
            path += abs(close[j] - close[j - 1])
        if path == 0.0:
            out[i] = 0.0
        else:
            out[i] = abs(close[i] - close[i - lookback]) / path

    return out


@njit(cache=True)
def _regime_of(ratio: float, consolidating_below: float, directional_above: float) -> int:
    """Classify one ratio -- the only place this rule lives, shared by ``label`` and ``gate``."""
    if np.isnan(ratio):
        return UNDEFINED

    if ratio < consolidating_below:
        return Regime.CONSOLIDATING

    if ratio > directional_above:
        return Regime.DIRECTIONAL

    return Regime.UNCLASSIFIABLE


@njit(cache=True)
def _label(values: FloatArray, consolidating_below: float, directional_above: float) -> LabelArray:
    n = values.size
    out = np.empty(n, dtype=np.int8)
    for i in range(n):
        out[i] = _regime_of(values[i], consolidating_below, directional_above)

    return out


@njit(cache=True)
def _gate(values: FloatArray, consolidating_below: float, directional_above: float, mask: int) -> BoolArray:
    """One pass from ratio to boolean, so a sweep combination never builds a label array."""
    n = values.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        found = _regime_of(values[i], consolidating_below, directional_above)
        if found != UNDEFINED:
            out[i] = (mask & (1 << found)) != 0

    return out


def efficiency_ratio(close: FloatArray, lookback: int) -> FloatArray:
    """Kaufman's efficiency ratio over ``lookback`` bars, aligned to ``close``.

    ``nan`` for the first ``lookback`` bars, which have no window to measure.
    """
    validate_lookback(lookback)

    return _efficiency_ratio(np.ascontiguousarray(close, dtype=np.float64), int(lookback))


def label(values: FloatArray, consolidating_below: float, directional_above: float) -> LabelArray:
    """Cut efficiency ratios into ``int8`` :class:`Regime` values, :data:`UNDEFINED` for ``nan``.

    **Both boundaries fall in the band**: strictly below the lower threshold is consolidating,
    strictly above the upper is directional, and equality on either is unclassifiable.
    """
    validate_thresholds(consolidating_below, directional_above)

    return _label(np.ascontiguousarray(values, dtype=np.float64), float(consolidating_below), float(directional_above))


def gate(values: FloatArray, mask: int, consolidating_below: float, directional_above: float) -> BoolArray:
    """Test every bar's regime against ``mask``, one boolean per bar.

    An :data:`UNDEFINED` bar passes nothing, :data:`ALL_REGIMES` included, which is why an
    archetype's signal skips this call entirely at the default -- ``docs/roadmap.md`` §M10.1.
    """
    validate_mask(mask)
    validate_thresholds(consolidating_below, directional_above)

    return _gate(
        np.ascontiguousarray(values, dtype=np.float64),
        float(consolidating_below),
        float(directional_above),
        int(mask),
    )


@dataclass(frozen=True, slots=True)
class EfficiencyRatioGrid:
    """The ratio at every lookback a sweep needs, as ``[n_lookbacks, n_bars]``.

    Raw ratios rather than labels, because the two thresholds are swept as well and a grid
    over all three parameters would multiply out. ``lookbacks`` is sorted and deduplicated, so
    :meth:`row` is the only supported way from a lookback back to its row.
    """

    lookbacks: IntArray
    values: FloatArray
    """Efficiency ratios as ``[n_lookbacks, n_bars]`` float64, ``nan`` through each warm-up."""

    def __len__(self) -> int:
        """Count the bars, not the lookbacks."""
        return int(self.values.shape[1])

    def row(self, lookback: int) -> int:
        """Find the row holding ``lookback``, or say what the grid was built for."""
        idx: int = int(np.searchsorted(self.lookbacks, lookback))
        if idx >= self.lookbacks.size or self.lookbacks[idx] != lookback:
            msg: str = f"efficiency ratio over {lookback} bars is not in this grid; built for {self.lookbacks.tolist()}"
            raise KeyError(msg)

        return idx

    def values_for(self, lookback: int) -> FloatArray:
        """Read one lookback's efficiency ratios."""
        return np.asarray(self.values[self.row(lookback)])

    def labels_for(self, lookback: int, consolidating_below: float, directional_above: float) -> LabelArray:
        """Label every bar at one lookback, the stratification key -- see :func:`label`."""
        return label(self.values_for(lookback), consolidating_below, directional_above)

    def gate_for(self, lookback: int, mask: int, consolidating_below: float, directional_above: float) -> BoolArray:
        """Test every bar at one lookback against ``mask``, the entry filter -- see :func:`gate`."""
        return gate(self.values_for(lookback), mask, consolidating_below, directional_above)

    @property
    def nbytes(self) -> int:
        """Bytes the ratios occupy -- what a parallel worker is handed."""
        return self.values.nbytes


def efficiency_ratio_grid(close: FloatArray, lookbacks: Iterable[int]) -> EfficiencyRatioGrid:
    """Compute every distinct lookback a sweep needs, once.

    Eight bytes per element, so this is the one series a long lookback axis makes expensive
    for a parallel worker -- ``docs/roadmap.md`` §M10.1.
    """
    unique: IntArray = np.unique(np.asarray(list(lookbacks), dtype=np.int64))
    if unique.size == 0:
        msg: str = "no lookbacks supplied"
        raise RegimeError(msg)

    validate_lookback(int(unique[0]))

    close = np.ascontiguousarray(close, dtype=np.float64)
    values: FloatArray = np.empty((unique.size, close.size), dtype=np.float64)
    for i, lookback in enumerate(unique):
        values[i] = _efficiency_ratio(close, int(lookback))

    return EfficiencyRatioGrid(lookbacks=unique, values=values)
