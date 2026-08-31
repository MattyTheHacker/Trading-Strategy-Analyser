"""Time of day as a first-class dimension: session phase and bar of session.

Two forms of one clock. **Session phase** is a coarse categorical label, seven Eastern-time
buckets, and is the form a review reports; **bar of session** is the integer index from the
session open, the fine form for a sweep. Both come out of one :func:`classify` pass over
:func:`nqbt.resample.minutes_since_open`, so the session clock keeps one definition.

Everything here is **Eastern time, never UTC**, and every label is taken from the minute a bar
*occupies* rather than the minute it is stamped at. A phase set is carried as a bitmask integer
so that it is a legal sweep axis. Reasoning, the DST pin and the first stratification:
``docs/roadmap.md`` §M10.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import resample, sessions
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH, SessionTemplate

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BitsArray, BoolArray, IndexArray, IntArray, LabelArray

SECONDS_PER_DAY = 86_400

MIN_STAMPS_FOR_A_GAP = 2
"""Stamps needed before :func:`infer_bar_minutes` has a gap to measure."""

OUT_OF_SESSION = -1
"""Label for a bar outside any session. Negative, not an eighth phase -- ``docs/roadmap.md``
§M10.4.
"""


class TimeOfDayError(ValueError):
    """Raised for an impossible phase mask, bar size or set of phase boundaries."""


class SessionPhase(IntEnum):
    """Coarse phases of the CME index-futures session, in Eastern time.

    The integer values are the session ordering, and also the bit positions in a filter mask.
    Why seven and why these: ``docs/roadmap.md`` §M10.4.
    """

    OVERNIGHT = 0
    """18:00-03:00 ET. The session open through the Asian hours."""
    LONDON = 1
    """03:00-07:00 ET, the European cash session."""
    PRE_OPEN = 2
    """07:00-09:30 ET. US pre-market, and where the day's economic releases land."""
    CASH_OPEN = 3
    """09:30-10:30 ET, the first hour of US cash trading."""
    MIDDAY = 4
    """10:30-14:00 ET, the midday lull."""
    AFTERNOON = 5
    """14:00-16:00 ET, through the cash close."""
    CLOSE = 6
    """16:00-17:00 ET. **Structurally anomalous**: it contains the forced flat."""

    @property
    def bit(self) -> int:
        """The bit this phase occupies in a filter mask."""
        return 1 << int(self)


FORCED_EXIT_PHASE = SessionPhase.CLOSE
"""The phase the session-close flatten falls in, named so a caller can exclude it."""

PHASE_STARTS: tuple[tuple[SessionPhase, time], ...] = (
    (SessionPhase.OVERNIGHT, time(18, 0)),
    (SessionPhase.LONDON, time(3, 0)),
    (SessionPhase.PRE_OPEN, time(7, 0)),
    (SessionPhase.CASH_OPEN, time(9, 30)),
    (SessionPhase.MIDDAY, time(10, 30)),
    (SessionPhase.AFTERNOON, time(14, 0)),
    (SessionPhase.CLOSE, time(16, 0)),
)
"""Where each phase begins, as an exchange-local wall clock time.

:func:`phase_start_minutes` converts them to offsets from the session open.
"""

ALL_PHASES = (1 << len(SessionPhase)) - 1
"""Every phase: the mask that filters nothing, and the default for every archetype."""


def phases_mask(phases: Iterable[SessionPhase]) -> int:
    """Combine phases into the bitmask an archetype's ``phase_filter`` takes."""
    mask: int = 0
    for phase in phases:
        mask |= SessionPhase(phase).bit
    return mask


def phases_in(mask: int) -> tuple[SessionPhase, ...]:
    """The phases a mask admits, in session order."""
    validate_mask(mask)
    return tuple(p for p in SessionPhase if mask & p.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no phase owns."""
    if mask < 0 or mask & ~ALL_PHASES:
        msg: str = (
            f"phase mask {mask} sets bits outside 0..{ALL_PHASES}; use SessionPhase.bit or phases_mask()"
        )
        raise TimeOfDayError(msg)
    if mask == 0:
        msg = "phase mask 0 admits no phase, so every combination along it would trade nothing"
        raise TimeOfDayError(msg)
    return mask


def describe_mask(mask: int) -> str:
    """A readable phase list, for a results table or an error message."""
    return "+".join(p.name for p in phases_in(mask))


def session_minutes(template: SessionTemplate = CME_US_INDEX_FUTURES_ETH) -> int:
    """How many minutes a full session runs -- 1,380 for the 18:00-17:00 ET template."""
    return ((template.close_seconds - template.open_seconds) % SECONDS_PER_DAY) // 60


def phase_start_minutes(template: SessionTemplate = CME_US_INDEX_FUTURES_ETH) -> IntArray:
    """:data:`PHASE_STARTS` as minutes past the session open, validated and ascending.

    Validated on every call, not once at import, because the boundaries are relative to the
    template's open -- ``docs/roadmap.md`` §M10.4.
    """
    starts: IntArray = np.array(
        [
            ((t.hour * 3600 + t.minute * 60 + t.second - template.open_seconds) % SECONDS_PER_DAY) // 60
            for _, t in PHASE_STARTS
        ],
        dtype=np.int64,
    )
    length: int = session_minutes(template)
    if starts[0] != 0:
        msg: str = f"the first phase must begin at the session open; got {starts[0]} minutes past it"
        raise TimeOfDayError(msg)
    if np.any(np.diff(starts) <= 0):
        msg = f"phase starts must ascend within the session; got {starts.tolist()} minutes past the open"
        raise TimeOfDayError(msg)
    if starts[-1] >= length:
        msg = f"phase start {starts[-1]} falls at or past the {length}-minute close"
        raise TimeOfDayError(msg)
    return starts


def phase_from_minutes(
    minutes: IntArray,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> LabelArray:
    """Label each bar from its minute-of-session, as ``int8`` :class:`SessionPhase` values.

    ``minutes`` is :func:`nqbt.resample.minutes_since_open`, so the minute a bar *occupies* is
    one less. Out-of-session bars are not identifiable here; :func:`classify` marks those.
    """
    occupied: IntArray = np.asarray(minutes, dtype=np.int64) - 1
    starts: IntArray = phase_start_minutes(template)
    return (np.searchsorted(starts, occupied, side="right") - 1).astype(np.int8)


def bits_from_phase(phase: LabelArray) -> BitsArray:
    """``1 << phase`` per bar, and ``0`` for :data:`OUT_OF_SESSION`.

    Precomputed so testing a filter is one ``&`` over the series.
    """
    phase = np.asarray(phase)
    bits: BitsArray = np.zeros(phase.size, dtype=np.uint8)
    inside: BoolArray = phase >= 0
    bits[inside] = (1 << phase[inside].astype(np.int64)).astype(np.uint8)
    return bits


def bar_index_from_minutes(minutes: IntArray, bar_minutes: int) -> IndexArray:
    """Zero-based bar of session, from minute-of-session and the bar size.

    **Derived from the clock, never counted off the data** -- ``docs/roadmap.md`` §M10.4. Same
    quantity :func:`nqbt.resample.bucket_index` groups by.
    """
    if bar_minutes < 1:
        msg: str = f"bar_minutes must be >= 1, got {bar_minutes}"
        raise TimeOfDayError(msg)
    return ((np.asarray(minutes, dtype=np.int64) - 1) // bar_minutes).astype(np.int32)


def infer_bar_minutes(index: pd.DatetimeIndex) -> int:
    """The bar size in minutes, as the most common gap between consecutive stamps.

    The mode, not the minimum or the mean -- ``docs/roadmap.md`` §M10.4. Falls back to 1 for an
    index too short to have a gap.
    """
    stamps: pd.DatetimeIndex = pd.DatetimeIndex(index)
    if stamps.size < MIN_STAMPS_FOR_A_GAP:
        return 1
    naive: pd.DatetimeIndex = stamps.tz_convert("UTC").tz_localize(None) if stamps.tz is not None else stamps
    deltas = np.diff(naive.to_numpy().astype("datetime64[m]").astype(np.int64))
    positive = deltas[deltas > 0]
    if positive.size == 0:
        return 1
    values, counts = np.unique(positive, return_counts=True)
    return int(values[counts.argmax()])


@dataclass(frozen=True, slots=True)
class TimeOfDay:
    """Both forms of the clock for one series, aligned to its index."""

    phase: LabelArray
    """``int8`` :class:`SessionPhase` per bar, :data:`OUT_OF_SESSION` outside a session."""
    phase_bits: BitsArray
    """``uint8`` ``1 << phase``, ``0`` out of session -- see :func:`bits_from_phase`."""
    bar_of_session: IndexArray
    """``int32`` zero-based bar index from the session open, :data:`OUT_OF_SESSION` outside."""
    bar_minutes: int
    """The bar size :attr:`bar_of_session` was computed at."""

    def __len__(self) -> int:
        return self.phase.size

    @property
    def nbytes(self) -> int:
        """Bytes the labels occupy -- what a parallel worker is handed."""
        return self.phase.nbytes + self.phase_bits.nbytes + self.bar_of_session.nbytes

    def gate(self, mask: int) -> BoolArray:
        """Per-bar boolean: does this bar's phase pass ``mask``?

        An out-of-session bar passes nothing, :data:`ALL_PHASES` included, which is why an
        archetype's signal skips this call entirely at the default -- ``docs/roadmap.md`` §M10.4.
        """
        return np.asarray((self.phase_bits & np.uint8(validate_mask(mask))) != 0)


def classify(
    index: pd.DatetimeIndex,
    bar_minutes: int | None = None,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
    info: sessions.SessionInfo | None = None,
) -> TimeOfDay:
    """Label every bar with its session phase and its bar of session.

    ``bar_minutes`` is inferred from the index when not given; pass it wherever it is known.
    ``info`` lets a caller that has already run :func:`nqbt.sessions.classify` skip a second tz
    conversion over millions of rows.
    """
    stamps: pd.DatetimeIndex = pd.DatetimeIndex(index)
    if info is None:
        info = sessions.classify(stamps, template)
    size: int = bar_minutes if bar_minutes is not None else infer_bar_minutes(stamps)

    minutes: IntArray = resample.minutes_since_open(stamps, template)
    phase: LabelArray = phase_from_minutes(minutes, template)
    bar: IndexArray = bar_index_from_minutes(minutes, size)

    outside: BoolArray = ~info.in_session
    phase[outside] = OUT_OF_SESSION
    bar[outside] = OUT_OF_SESSION

    return TimeOfDay(phase=phase, phase_bits=bits_from_phase(phase), bar_of_session=bar, bar_minutes=size)
