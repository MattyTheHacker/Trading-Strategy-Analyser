"""A moving average computed on coarser bars, read by a strategy running on fine ones.

"Only short below the hourly trend" is standard practice and was not expressible: every
average this project computes reads the 1-minute close. Here the average is computed on bars
:mod:`nqbt.resample` aggregates, then **stamped back onto the fine index from the most recently
*completed* coarse bar**, which is the whole of the difficulty -- ``docs/roadmap.md``
§ "Multi-timeframe moving averages".

Price against that average is a single ``int8`` per bar: :attr:`Side.BELOW`, :attr:`Side.AT` or
:attr:`Side.ABOVE`, :data:`UNDEFINED` before the first coarse bar has closed. A side set is
carried as a bitmask integer so that it is a legal sweep axis, exactly as :mod:`nqbt.regime`,
:mod:`nqbt.timeofday`, :mod:`nqbt.volume` and :mod:`nqbt.trend` carry theirs.

Distinct from :mod:`nqbt.trend`, which reads a coarse *condition* off 1-minute averages, and
from running the whole strategy on coarse bars. The three share the resampler and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from itertools import groupby
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd
from numba import njit

from nqbt import indicators, resample, timeofday
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BoolArray, FloatArray, IntArray, LabelArray, OffsetArray
    from nqbt.sessions import SessionTemplate

__all__ = [
    "ALL_SIDES",
    "KIND",
    "MIN_MINUTES",
    "UNDEFINED",
    "HigherTimeframeError",
    "HigherTimeframeGrid",
    "HigherTimeframeKey",
    "Side",
    "describe_mask",
    "gate",
    "higher_timeframe_grid",
    "key",
    "label",
    "project",
    "sides_in",
    "sides_mask",
    "validate_mask",
    "validate_minutes",
    "validate_period",
]

UNDEFINED = -1
"""Label for a bar no coarse bar has closed before. Negative, not a fourth side, so it cannot
be swept into a filter by accident -- ``docs/roadmap.md`` § "Multi-timeframe moving averages".
"""

KIND = "ema"
"""The moving average the side is measured against. Fixed rather than swept, for the reason
:data:`nqbt.trend.KIND` is.
"""

MIN_MINUTES = 2
"""Fewest minutes a higher timeframe may span. A one-minute one is the existing moving-average
gate under another name, and :func:`higher_timeframe_grid` refuses more than this: the coarse
period must also be a proper multiple of the bars it is aggregated from.
"""


class HigherTimeframeError(ValueError):
    """Raised for an impossible side mask, resolution or moving-average period."""


class Side(IntEnum):
    """Where the fine close sits against the higher-timeframe average, ordered by price.

    The integer values ascend with the close, and are also the bit positions in a filter mask.
    """

    BELOW = 0
    """Under the higher-timeframe average: the side a short-only archetype wants."""
    AT = 1
    """Exactly on it. Essentially never reached by two float64 values, and cheaper to give a
    state than to argue about which side it belongs on."""
    ABOVE = 2
    """Over it -- :attr:`BELOW` with the test mirrored."""

    @property
    def bit(self) -> int:
        """The bit this side occupies in a filter mask."""
        return 1 << int(self)


ALL_SIDES = (1 << len(Side)) - 1
"""Every side: the mask that filters nothing, and the default for every archetype."""


class HigherTimeframeKey(NamedTuple):
    """What one higher-timeframe average is determined by, and the grid's lookup key."""

    minutes: int
    """Minutes one coarse bar spans, anchored to the session open -- :mod:`nqbt.resample`."""
    period: int
    """Bars of *that* resolution the average is taken over, never bars of the fine series."""


def sides_mask(sides: Iterable[Side]) -> int:
    """Combine sides into the bitmask an archetype's ``higher_timeframe_filter`` takes."""
    mask: int = 0
    for side in sides:
        mask |= Side(side).bit
    return mask


def sides_in(mask: int) -> tuple[Side, ...]:
    """Unpack a mask into the sides it admits, in ascending-price order."""
    validate_mask(mask)
    return tuple(s for s in Side if mask & s.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no side owns."""
    if mask < 0 or mask & ~ALL_SIDES:
        msg: str = (
            f"higher-timeframe mask {mask} sets bits outside 0..{ALL_SIDES}; use Side.bit or sides_mask()"
        )
        raise HigherTimeframeError(msg)
    if mask == 0:
        msg = "higher-timeframe mask 0 admits no side, so every combination along it would trade nothing"
        raise HigherTimeframeError(msg)
    return mask


def validate_minutes(minutes: int) -> int:
    """Reject a resolution that is not coarser than the series it would be read on."""
    if minutes < MIN_MINUTES:
        msg: str = (
            f"higher_timeframe_minutes must be >= {MIN_MINUTES}, got {minutes}; "
            "a 1-minute higher timeframe is the existing moving-average gate"
        )
        raise HigherTimeframeError(msg)
    return minutes


def validate_period(period: int) -> int:
    """Reject a moving-average period no coarse bar could be averaged over."""
    if period < 1:
        msg: str = f"higher_timeframe_period must be >= 1, got {period}"
        raise HigherTimeframeError(msg)
    return period


def describe_mask(mask: int) -> str:
    """Render a mask as a side list, for a results table or an error message."""
    return "+".join(s.name for s in sides_in(mask))


def key(minutes: int, period: int) -> HigherTimeframeKey:
    """Build a grid key, validating the resolution and the period it will be averaged over."""
    return HigherTimeframeKey(validate_minutes(int(minutes)), validate_period(int(period)))


def _nanoseconds(index: pd.DatetimeIndex) -> IntArray:
    """UTC nanoseconds since the epoch, the one form two indices can be compared in."""
    naive: pd.DatetimeIndex = index.tz_convert("UTC").tz_localize(None) if index.tz is not None else index
    return naive.to_numpy(dtype="datetime64[ns]").astype("int64")


def project(coarse_stamps: pd.DatetimeIndex, values: FloatArray, stamps: pd.DatetimeIndex) -> FloatArray:
    """Stamp each fine bar with the most recently **completed** coarse bar's value.

    Both indices are end-of-bar, so a coarse bar is readable from the fine bar that closes
    alongside it and from every fine bar after, and from none before. ``nan`` until the first
    coarse bar has closed. **This is the whole lookahead question** -- ``docs/roadmap.md``
    § "Multi-timeframe moving averages".
    """
    coarse: FloatArray = np.ascontiguousarray(values, dtype=np.float64)
    if coarse.size != coarse_stamps.size:
        msg: str = f"{coarse.size} values against {coarse_stamps.size} coarse stamps"
        raise HigherTimeframeError(msg)

    # side="right" is what makes the bar closing alongside a coarse bar read it, and every
    # bar inside an unfinished one read the bar before.
    positions: OffsetArray = np.searchsorted(_nanoseconds(coarse_stamps), _nanoseconds(stamps), side="right")
    positions = positions - 1
    out: FloatArray = np.full(stamps.size, np.nan, dtype=np.float64)
    completed: BoolArray = positions >= 0
    out[completed] = coarse[positions[completed]]
    return out


@njit(cache=True)
def _label(close: FloatArray, series: FloatArray) -> LabelArray:
    n = close.size
    out = np.empty(n, dtype=np.int8)
    for i in range(n):
        if np.isnan(series[i]):
            out[i] = UNDEFINED
        elif close[i] < series[i]:
            out[i] = Side.BELOW
        elif close[i] > series[i]:
            out[i] = Side.ABOVE
        else:
            out[i] = Side.AT
    return out


@njit(cache=True)
def _gate(labels: LabelArray, mask: int) -> BoolArray:
    n = labels.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        if labels[i] != UNDEFINED:
            out[i] = (mask & (1 << labels[i])) != 0
    return out


def label(close: FloatArray, series: FloatArray) -> LabelArray:
    """Cut a close and a projected average into ``int8`` :class:`Side` values.

    :data:`UNDEFINED` wherever the average is ``nan``, which is every bar before the first
    coarse bar closed.
    """
    return _label(
        np.ascontiguousarray(close, dtype=np.float64),
        np.ascontiguousarray(series, dtype=np.float64),
    )


def gate(labels: LabelArray, mask: int) -> BoolArray:
    """Test every bar's side against ``mask``, one boolean per bar.

    An :data:`UNDEFINED` bar passes nothing, :data:`ALL_SIDES` included, which is why an
    archetype's signal skips this call entirely at the default.
    """
    validate_mask(mask)
    return _gate(np.ascontiguousarray(labels, dtype=np.int8), int(mask))


@dataclass(frozen=True, slots=True)
class HigherTimeframeGrid:
    """Every higher-timeframe average a sweep needs, projected onto the fine index.

    ``keys`` is sorted and deduplicated, so :meth:`row` is the only supported way from a key
    back to its row.
    """

    keys: tuple[HigherTimeframeKey, ...]
    values: FloatArray
    """The projected average, ``[n_keys, n_bars]`` float64, ``nan`` before the first close."""
    labels: LabelArray
    """Price against it, ``[n_keys, n_bars]`` int8 -- see :class:`Side` and :data:`UNDEFINED`."""

    def __len__(self) -> int:
        """Count the bars, not the keys."""
        return int(self.values.shape[1])

    def row(self, wanted: HigherTimeframeKey) -> int:
        """Find the row holding ``wanted``, or say what the grid was built for."""
        try:
            return self.keys.index(wanted)
        except ValueError:
            msg: str = f"higher-timeframe average {wanted} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg) from None

    def values_for(self, wanted: HigherTimeframeKey) -> FloatArray:
        """Read one average as the fine series sees it, the raw quantity behind the labels."""
        return np.asarray(self.values[self.row(wanted)])

    def labels_for(self, wanted: HigherTimeframeKey) -> LabelArray:
        """Read one average's per-bar :class:`Side`, the stratification key."""
        return np.asarray(self.labels[self.row(wanted)])

    def gate_for(self, wanted: HigherTimeframeKey, mask: int) -> BoolArray:
        """Test every bar of one average against ``mask``, the entry filter -- see :func:`gate`."""
        return gate(self.labels_for(wanted), mask)

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed."""
        return self.values.nbytes + self.labels.nbytes


def higher_timeframe_grid(
    bars: pd.DataFrame,
    keys: Iterable[HigherTimeframeKey],
    *,
    bar_minutes: int | None = None,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> HigherTimeframeGrid:
    """Compute every higher-timeframe average a sweep needs, once, and project each one back.

    One resample per distinct resolution, whatever periods share it. ``bar_minutes`` is the
    resolution ``bars`` already carries and is inferred from the index when not given; a
    coarse resolution that is not a proper multiple of it is refused rather than bucketed
    across bar boundaries.
    """
    ordered: tuple[HigherTimeframeKey, ...] = tuple(sorted({key(k.minutes, k.period) for k in keys}))
    if not ordered:
        msg: str = "no higher-timeframe averages supplied"
        raise HigherTimeframeError(msg)

    stamps: pd.DatetimeIndex = pd.DatetimeIndex(bars.index)
    fine: int = bar_minutes if bar_minutes is not None else timeofday.infer_bar_minutes(stamps)
    for wanted in ordered:
        if wanted.minutes <= fine or wanted.minutes % fine:
            msg = (
                f"higher_timeframe_minutes {wanted.minutes} is not a proper multiple of the "
                f"{fine}-minute bars it would be aggregated from"
            )
            raise HigherTimeframeError(msg)

    close: FloatArray = bars["close"].to_numpy(np.float64)
    values: FloatArray = np.empty((len(ordered), close.size), dtype=np.float64)
    labels: LabelArray = np.empty((len(ordered), close.size), dtype=np.int8)

    row = 0
    for minutes, group in groupby(ordered, key=lambda k: k.minutes):
        coarse: pd.DataFrame = resample.resample(bars[["close"]], minutes, template=template)
        coarse_close: FloatArray = coarse["close"].to_numpy(np.float64)
        coarse_stamps: pd.DatetimeIndex = pd.DatetimeIndex(coarse.index)
        for wanted in group:
            values[row] = project(coarse_stamps, indicators.nt8_ema(coarse_close, wanted.period), stamps)
            labels[row] = label(close, values[row])
            row += 1
    return HigherTimeframeGrid(keys=ordered, values=values, labels=labels)
