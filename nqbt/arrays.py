"""Dtype-parameterised aliases for the arrays this package passes between its modules.

A bare ``np.ndarray`` says only "some array". Here the element type is load-bearing --
``MovingAverageGrid.below`` is bool where ``.values`` is float64, and that one distinction is
the difference between a 66 MB grid and a 595 MB one. Spelled once here rather than at every
signature, and **not** used inside ``@njit`` bodies as a promise: numba infers from the call and
ignores the annotation entirely -- ``docs/roadmap.md`` §M20b.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "AnyArray",
    "BitsArray",
    "BoolArray",
    "DateArray",
    "FloatArray",
    "IndexArray",
    "IntArray",
    "LabelArray",
    "TextArray",
]

type FloatArray = NDArray[np.float64]
"""Prices, indicator values, ratios and P&L: the one float width the simulation uses."""

type BoolArray = NDArray[np.bool_]
"""A gate or a mask, one per bar or one per leg."""

type IntArray = NDArray[np.int64]
"""Bar indices, session ids, counts and group boundaries."""

type LabelArray = NDArray[np.int8]
"""A compact state per bar -- :class:`~nqbt.regime.Regime` and its siblings -- or a trend vote."""

type IndexArray = NDArray[np.int32]
"""Bar of session and calendar day code: one small integer per bar, kept narrow for size."""

type BitsArray = NDArray[np.uint8]
"""``1 << label`` per bar, so testing a filter is one ``&`` over the series."""

type DateArray = NDArray[np.datetime64]
"""Whole dates, as ``datetime64[D]``: the trading day each bar belongs to."""

type TextArray = NDArray[np.object_]
"""Label names, which numpy holds as objects rather than as a fixed-width string dtype."""

type AnyArray = np.ndarray[tuple[int, ...], np.dtype[np.generic[object]]]
"""Any of the above, where a column's dtype is the caller's business rather than this one's."""
