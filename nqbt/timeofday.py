"""Time of day as a first-class dimension: session phase and bar of session.

Two forms of the same clock, because they answer different questions. **Session phase** is
a coarse categorical label -- seven buckets, few enough to survive a minimum-stratum guard
on a few hundred real trades -- and is the form a review reports. **Bar of session** is an
integer index from the session open, the fine form for a sweep whose sample is thousands
of trades, and the axis #41 normalises relative volume against.

Both are derived from :func:`nqbt.resample.minutes_since_open`, so the session clock keeps
one definition here as it has everywhere else.

## Exchange local time, never UTC

The phases are named after events in **Eastern** time -- the London open at 03:00 ET, the
cash open at 09:30 ET -- and 09:30 ET is 13:30 or 14:30 UTC depending on the date. Bucketing
on UTC splits the single most distinctive hour of the day across two buckets for half the
year, and the damage reads as noise rather than as an error. Everything below goes through
:func:`nqbt.sessions.to_eastern` for that reason.

## The end-of-bar convention decides the boundaries

Timestamps are end-of-bar, so a bar stamped 09:30 covers 09:29-09:30 and belongs to the
*pre-open*; the first cash-open bar is the one stamped 09:31. Every label is therefore taken
from the minute a bar **occupies**, not the minute it is stamped at. Off by one there is
invisible in aggregate and wrong at exactly the boundaries the labels exist to isolate.

## The final phase is structurally anomalous

:attr:`SessionPhase.CLOSE` contains the forced flat (#16), so its exits are decided by the
clock rather than by the rules, and a time-of-day stratification will show it as different
whatever the market did. **That is an artefact, not a finding.** Read
``stats.Summary.session_close_share`` beside any result touching it, and separate "this hour
trades badly" from "this hour's trades were closed by the clock" before believing either.

## As an entry filter

A phase set is carried as a **bitmask integer** rather than a tuple, so it is a legal sweep
axis: one scalar per combination, ``phase_filter=[CASH_OPEN.bit, ALL_PHASES]`` being two
combinations rather than an axis the grid has to refuse. :data:`ALL_PHASES` is the no-op, and
each archetype's signal skips the conjunction entirely at that value -- so an unfiltered
sweep pays nothing for the filter existing.
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

SECONDS_PER_DAY = 86_400

OUT_OF_SESSION = -1
"""Label for a bar outside any session -- the maintenance break, a weekend stray print.

Negative rather than an eighth phase so it cannot be swept into a filter by accident, and so
a mean or a ``groupby`` over the labels reads as obviously wrong rather than quietly counting
the strays as an eighth hour of the day.
"""


class TimeOfDayError(ValueError):
    """Raised for an impossible phase mask, bar size or set of phase boundaries."""


class SessionPhase(IntEnum):
    """Coarse phases of the CME index-futures session, in Eastern time.

    Seven buckets, chosen for what happens in them rather than for equal length: the
    overnight hours are one bucket because little distinguishes 20:00 from 01:00, while the
    hour after the cash open gets one to itself because it is the most distinctive hour of
    the day. Fewer buckets is the point -- time of day multiplies every other stratification,
    and seven phases against five regimes is already 35 cells.

    The integer values are the session ordering, and are also the bit positions in a filter
    mask.
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
    """16:00-17:00 ET. **Structurally anomalous** -- see the module docstring."""

    @property
    def bit(self) -> int:
        """The bit this phase occupies in a filter mask."""
        return 1 << int(self)


FORCED_EXIT_PHASE = SessionPhase.CLOSE
"""The phase the session-close flatten falls in, named so a caller can exclude it.

Pointed at by name rather than left for a reader to work out, because every time-of-day
result that includes it is measuring the clock as well as the market.
"""

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

Written as ET times rather than as offsets from the session open because that is what they
mean: ``time(9, 30)`` is the cash open, where an offset of 930 minutes is a number nobody can
check. :func:`phase_start_minutes` converts them once.
"""

ALL_PHASES = (1 << len(SessionPhase)) - 1
"""Every phase: the mask that filters nothing, and the default for every archetype."""


def phases_mask(phases: Iterable[SessionPhase]) -> int:
    """Combine phases into the bitmask an archetype's ``phase_filter`` takes."""
    mask = 0
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
        msg = f"phase mask {mask} sets bits outside 0..{ALL_PHASES}; use SessionPhase.bit or phases_mask()"
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


def phase_start_minutes(template: SessionTemplate = CME_US_INDEX_FUTURES_ETH) -> np.ndarray:
    """:data:`PHASE_STARTS` as minutes past the session open, validated and ascending.

    Validated on every call rather than once at import: the boundaries are relative to the
    template's own open, so a template opening elsewhere reorders them, and a set that no
    longer ascends would mislabel whole phases through :func:`numpy.searchsorted` without
    raising.
    """
    starts = np.array(
        [
            ((t.hour * 3600 + t.minute * 60 + t.second - template.open_seconds) % SECONDS_PER_DAY) // 60
            for _, t in PHASE_STARTS
        ],
        dtype=np.int64,
    )
    length = session_minutes(template)
    if starts[0] != 0:
        msg = f"the first phase must begin at the session open; got {starts[0]} minutes past it"
        raise TimeOfDayError(msg)
    if np.any(np.diff(starts) <= 0):
        msg = f"phase starts must ascend within the session; got {starts.tolist()} minutes past the open"
        raise TimeOfDayError(msg)
    if starts[-1] >= length:
        msg = f"phase start {starts[-1]} falls at or past the {length}-minute close"
        raise TimeOfDayError(msg)
    return starts


def phase_from_minutes(
    minutes: np.ndarray,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> np.ndarray:
    """Label each bar from its minute-of-session, as ``int8`` :class:`SessionPhase` values.

    ``minutes`` is :func:`nqbt.resample.minutes_since_open` -- 1 for the bar stamped 18:01 --
    so the minute a bar *occupies* is one less, and that is what the boundaries are compared
    against. An out-of-session bar is not identifiable from its minute alone; :func:`classify`
    is what marks those.
    """
    occupied = np.asarray(minutes, dtype=np.int64) - 1
    starts = phase_start_minutes(template)
    return (np.searchsorted(starts, occupied, side="right") - 1).astype(np.int8)


def bits_from_phase(phase: np.ndarray) -> np.ndarray:
    """``1 << phase`` per bar, and ``0`` for :data:`OUT_OF_SESSION`.

    Precomputed so testing a filter is one ``&`` over the series rather than a comparison per
    phase, and so an out-of-session bar passes no mask at all.
    """
    phase = np.asarray(phase)
    bits = np.zeros(phase.size, dtype=np.uint8)
    inside = phase >= 0
    bits[inside] = (1 << phase[inside].astype(np.int64)).astype(np.uint8)
    return bits


def bar_index_from_minutes(minutes: np.ndarray, bar_minutes: int) -> np.ndarray:
    """Zero-based bar of session, from minute-of-session and the bar size.

    **Derived from the clock, not counted off the data.** An ordinal count of the bars
    actually present slides by one whenever a session is missing a bar, so index ``k`` would
    mean a different time of day in different sessions -- which is exactly the confound #41's
    relative volume exists to divide out. This is the same quantity
    :func:`nqbt.resample.bucket_index` groups by, so at 5 minutes a bar's index is the index
    of the 5-minute bucket it is.
    """
    if bar_minutes < 1:
        msg = f"bar_minutes must be >= 1, got {bar_minutes}"
        raise TimeOfDayError(msg)
    return ((np.asarray(minutes, dtype=np.int64) - 1) // bar_minutes).astype(np.int32)


def infer_bar_minutes(index: pd.DatetimeIndex) -> int:
    """The bar size in minutes, as the most common gap between consecutive stamps.

    The mode rather than the minimum or the mean: every session has a one-hour break and the
    archive has holes, so both of those measure the gaps rather than the bars. Falls back to
    1 for an index too short to have a gap.
    """
    stamps = pd.DatetimeIndex(index)
    if stamps.size < 2:
        return 1
    naive = stamps.tz_convert("UTC").tz_localize(None) if stamps.tz is not None else stamps
    deltas = np.diff(naive.to_numpy().astype("datetime64[m]").astype(np.int64))
    positive = deltas[deltas > 0]
    if positive.size == 0:
        return 1
    values, counts = np.unique(positive, return_counts=True)
    return int(values[counts.argmax()])


@dataclass(frozen=True, slots=True)
class TimeOfDay:
    """Both forms of the clock for one series, aligned to its index.

    One object rather than three loose arrays because they come out of a single pass over the
    index -- the tz conversion is the expensive part -- and because a caller holding the phase
    almost always needs to know the bar size it was labelled at.
    """

    phase: np.ndarray
    """``int8`` :class:`SessionPhase` per bar, :data:`OUT_OF_SESSION` outside a session."""
    phase_bits: np.ndarray
    """``uint8`` ``1 << phase``, ``0`` out of session -- see :func:`bits_from_phase`."""
    bar_of_session: np.ndarray
    """``int32`` zero-based bar index from the session open, :data:`OUT_OF_SESSION` outside."""
    bar_minutes: int
    """The bar size :attr:`bar_of_session` was computed at."""

    def __len__(self) -> int:
        return self.phase.size

    @property
    def nbytes(self) -> int:
        return self.phase.nbytes + self.phase_bits.nbytes + self.bar_of_session.nbytes

    def gate(self, mask: int) -> np.ndarray:
        """Per-bar boolean: does this bar's phase pass ``mask``?

        An out-of-session bar passes nothing, :data:`ALL_PHASES` included. That asymmetry is
        why an archetype's signal skips this call at the default rather than ANDing an
        all-true array: the no-op has to be *no filter*, or switching the filter on to "every
        phase" would quietly drop the stray prints and move a result.
        """
        return (self.phase_bits & np.uint8(validate_mask(mask))) != 0


def classify(
    index: pd.DatetimeIndex,
    *,
    bar_minutes: int | None = None,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
    info: sessions.SessionInfo | None = None,
) -> TimeOfDay:
    """Label every bar with its session phase and its bar of session.

    ``bar_minutes`` is inferred from the index when not given; pass it wherever it is known,
    which a resolution sweep always is. ``info`` lets a caller that has already run
    :func:`nqbt.sessions.classify` skip a second tz conversion over millions of rows.
    """
    stamps = pd.DatetimeIndex(index)
    if info is None:
        info = sessions.classify(stamps, template)
    size = bar_minutes if bar_minutes is not None else infer_bar_minutes(stamps)

    minutes = resample.minutes_since_open(stamps, template)
    phase = phase_from_minutes(minutes, template)
    bar = bar_index_from_minutes(minutes, size)

    outside = ~info.in_session
    phase[outside] = OUT_OF_SESSION
    bar[outside] = OUT_OF_SESSION

    return TimeOfDay(phase=phase, phase_bits=bits_from_phase(phase), bar_of_session=bar, bar_minutes=size)
