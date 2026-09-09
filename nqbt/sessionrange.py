"""The session-anchored price range an opening-range break is measured against.

One window per session -- the highest high and the lowest low of the bars covering
``[anchor_minutes, anchor_minutes + window_minutes)`` past the session open -- plus the flag
saying which bars may read it. The cash open is :data:`CASH_OPEN_MINUTES` past the ETH open,
and the ETH open itself is ``0``, so the overnight range is the same primitive at a different
anchor.

**A range exists only where its whole window does.** A session whose window is short of bars
gets no range at all rather than one measured over what happened to be there, which is why
:attr:`SessionRangeGrid.armed` carries that verdict rather than the caller re-deriving it.

**The anchor and the window must both be whole numbers of bars**, so the bar grid decides which
ranges exist at all -- a cash-anchored range is not expressible on 60-minute bars.
:func:`validate_key` is where that is enforced and ``docs/roadmap.md`` §M28 is the reasoning.

Belongs to context, not simulation: it describes the bars and knows nothing about trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import indicators, resample, timeofday
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH, SessionTemplate
from nqbt.timeofday import SessionPhase

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BoolArray, DateArray, FloatArray, IndexArray, IntArray, OffsetArray

__all__ = [
    "CASH_OPEN_MINUTES",
    "ETH_OPEN_MINUTES",
    "MIN_FOLLOW_THROUGH_SESSIONS",
    "FollowThroughGrid",
    "RangeError",
    "RangeKey",
    "SessionRangeGrid",
    "anchor_for",
    "follow_through",
    "follow_through_grid",
    "range_grid",
    "trailing_median",
    "validate_follow_through_sessions",
    "validate_key",
]

type RangeKey = tuple[int, int]
"""One range to build: ``(anchor_minutes, window_minutes)`` past the session open."""

ETH_OPEN_MINUTES = 0
"""The session's own open, which is where an overnight range is anchored."""


def anchor_for(
    phase: SessionPhase,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> int:
    """Minutes from the session open to the start of ``phase`` -- one anchor per clock.

    Derived from :func:`nqbt.timeofday.phase_start_minutes` rather than written down, so the
    two clocks cannot drift apart if the template's open ever moves.
    """
    return int(timeofday.phase_start_minutes(template)[int(phase)])


CASH_OPEN_MINUTES = anchor_for(SessionPhase.CASH_OPEN)
"""Minutes from the 18:00 ET session open to the 09:30 ET cash open -- 930 on the ETH template.

The number every published opening range is anchored on, and the one whose divisors decide
which bar sizes can express it: ``docs/roadmap.md`` §M28.
"""


class RangeError(ValueError):
    """Raised for a range no grid can be built for at the resolution it was asked for."""


def validate_key(
    anchor_minutes: int,
    window_minutes: int,
    bar_minutes: int,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> RangeKey:
    """Return the key if a range can be built for it at ``bar_minutes``, else raise.

    Three conditions, and the last two are the ones that surprise: the window must fit inside
    the session, the anchor must land on a bucket boundary, and the window must be a whole
    number of bars. A cash-anchored range therefore needs ``bar_minutes`` to divide 930, which
    with §M13's own ``N | 60`` leaves ``N`` dividing 30 and rules 60-minute bars out entirely.
    """
    if bar_minutes < 1:
        msg: str = f"bar_minutes must be >= 1, got {bar_minutes}"
        raise RangeError(msg)

    if anchor_minutes < 0:
        msg = f"anchor_minutes must be >= 0, got {anchor_minutes}"
        raise RangeError(msg)

    if window_minutes < 1:
        msg = f"window_minutes must be >= 1, got {window_minutes}"
        raise RangeError(msg)

    length: int = timeofday.session_minutes(template)
    if anchor_minutes + window_minutes > length:
        msg = (
            f"a {window_minutes}-minute range anchored {anchor_minutes} minutes past the open "
            f"ends past the {length}-minute session close"
        )
        raise RangeError(msg)

    if anchor_minutes % bar_minutes:
        msg = (
            f"a range anchored {anchor_minutes} minutes past the session open needs a bar size "
            f"dividing {anchor_minutes}; {bar_minutes}-minute bars straddle the anchor"
        )
        raise RangeError(msg)

    if window_minutes % bar_minutes:
        msg = (
            f"a {window_minutes}-minute window is not a whole number of {bar_minutes}-minute "
            "bars, so the range would be measured over a different span than it names"
        )
        raise RangeError(msg)

    return int(anchor_minutes), int(window_minutes)


@dataclass(slots=True)
class SessionRangeGrid:
    """Every range a sweep needs, one row per key, plus the session index they are read through.

    **The levels are per session and the flag is per bar**, because a range is one fact about a
    session rather than a series: :attr:`high` and :attr:`low` are ``[n_keys, n_sessions]`` and
    :attr:`armed` is ``[n_keys, n_bars]``. That is what keeps the grid at a few bytes per bar
    however many windows are swept -- ``docs/roadmap.md`` §M28.1.
    """

    keys: tuple[RangeKey, ...]
    """The ranges built, sorted and deduplicated, so :meth:`row` is the way back to one."""

    session_id: IndexArray
    """Which session each bar belongs to, dense from ``0`` -- the index into :attr:`high`."""

    armed: BoolArray
    """``[n_keys, n_bars]``: may this bar read this range?

    True from the bar that completes the window to the end of its session, and false for the
    whole of a session whose window was short of bars -- so one flag answers both "not yet"
    and "not at all".
    """

    high: FloatArray
    """``[n_keys, n_sessions]``: the window's highest high, ``nan`` where there is no range."""

    low: FloatArray
    """``[n_keys, n_sessions]``: the window's lowest low, ``nan`` where there is no range."""

    def __len__(self) -> int:
        """Count the bars, not the keys or the sessions."""
        return int(self.armed.shape[1])

    @property
    def sessions(self) -> int:
        """How many sessions the bars span."""
        return int(self.high.shape[1])

    def row(self, key: RangeKey) -> int:
        """The row holding ``key``, or an error naming what the grid was built for."""
        if key not in self.keys:
            msg: str = f"range {key} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg)

        return self.keys.index(key)

    def armed_for(self, key: RangeKey) -> BoolArray:
        """Per bar: whether one range is complete and readable."""
        return np.asarray(self.armed[self.row(key)])

    def high_for(self, key: RangeKey) -> FloatArray:
        """Per session: one range's high, ``nan`` where the session has no range."""
        return np.asarray(self.high[self.row(key)])

    def low_for(self, key: RangeKey) -> FloatArray:
        """Per session: one range's low, ``nan`` where the session has no range."""
        return np.asarray(self.low[self.row(key)])

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed."""
        return self.session_id.nbytes + self.armed.nbytes + self.high.nbytes + self.low.nbytes


def _session_ids(trading_day: DateArray) -> IndexArray:
    """Each bar's session as a dense index from zero, in bar order."""
    return (np.cumsum(indicators.new_session_flags(trading_day)) - 1).astype(np.int32)


def _session_runs(
    session_id: IndexArray,
    mask: BoolArray,
) -> tuple[OffsetArray, OffsetArray, IndexArray]:
    """The masked bars, where each session's run of them starts, and whose session each run is.

    Every mask this module reduces over is contiguous within a session -- a window is a span of
    minutes and an armed flag a suffix of one -- so a group is a slice and ``reduceat`` is the
    reduction rather than ``maximum.at`` over every bar.
    """
    inside: OffsetArray = np.flatnonzero(mask)
    of_session: IndexArray = session_id[inside]
    if inside.size == 0:
        return inside, np.zeros(0, dtype=np.intp), of_session

    starts: OffsetArray = np.flatnonzero(
        np.concatenate(([True], of_session[1:] != of_session[:-1])),
    )

    return inside, starts, of_session


def _extremes(
    high: FloatArray,
    low: FloatArray,
    session_id: IndexArray,
    in_window: BoolArray,
    n_sessions: int,
    expected_bars: int,
) -> tuple[FloatArray, FloatArray]:
    """One high and one low per session, ``nan`` unless the window is entirely present."""
    session_high: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    session_low: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    inside: OffsetArray
    starts: OffsetArray
    of_session: IndexArray
    inside, starts, of_session = _session_runs(session_id, in_window)
    if inside.size == 0:
        return session_high, session_low

    counts: IntArray = np.diff(np.concatenate((starts, [inside.size])))
    whole: BoolArray = counts == expected_bars

    windows: IndexArray = of_session[starts][whole]
    session_high[windows] = np.maximum.reduceat(high[inside], starts)[whole]
    session_low[windows] = np.minimum.reduceat(low[inside], starts)[whole]

    return session_high, session_low


def range_grid(
    bars: pd.DataFrame,
    keys: Iterable[RangeKey],
    bar_minutes: int,
    *,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> SessionRangeGrid:
    """Compute every requested range once, over the whole series.

    ``bars`` must carry a ``trading_day`` column and be in session order, which is what
    :func:`nqbt.ingest.load_contract` guarantees. Every key is validated against
    ``bar_minutes`` first, so an unexpressible range fails loudly rather than being measured
    over a span it does not name.
    """
    ordered: tuple[RangeKey, ...] = tuple(
        sorted({validate_key(anchor, window, bar_minutes, template) for anchor, window in keys}),
    )
    if not ordered:
        msg: str = "no ranges supplied"
        raise RangeError(msg)

    index: pd.DatetimeIndex = pd.DatetimeIndex(bars.index)
    end_minute: IntArray = resample.minutes_since_open(index, template)
    session_id: IndexArray = _session_ids(bars["trading_day"].to_numpy())
    n_sessions: int = int(session_id[-1]) + 1 if session_id.size else 0

    high: FloatArray = bars["high"].to_numpy(np.float64)
    low: FloatArray = bars["low"].to_numpy(np.float64)

    armed: BoolArray = np.zeros((len(ordered), end_minute.size), dtype=np.bool_)
    session_high: FloatArray = np.full((len(ordered), n_sessions), np.nan, dtype=np.float64)
    session_low: FloatArray = np.full((len(ordered), n_sessions), np.nan, dtype=np.float64)

    for i, (anchor, window) in enumerate(ordered):
        # A bar stamped at minute m covers (m - bar_minutes, m], so it is inside the window
        # when its stamp clears the anchor and does not run past the window's end.
        in_window: BoolArray = (end_minute > anchor) & (end_minute <= anchor + window)
        session_high[i], session_low[i] = _extremes(
            high,
            low,
            session_id,
            in_window,
            n_sessions,
            window // bar_minutes,
        )
        complete: BoolArray = end_minute >= anchor + window
        armed[i] = complete & np.isfinite(session_high[i][session_id])

    return SessionRangeGrid(
        keys=ordered,
        session_id=session_id,
        armed=armed,
        high=session_high,
        low=session_low,
    )


MIN_FOLLOW_THROUGH_SESSIONS = 5
"""Fewest prior sessions a trailing follow-through may be taken over.

A median of fewer than a handful is the sessions themselves rather than the regime they sit in.
"""


def validate_follow_through_sessions(sessions: int) -> int:
    """Return the lookback if a trailing follow-through can be taken over it, else raise."""
    if sessions < MIN_FOLLOW_THROUGH_SESSIONS:
        msg: str = f"follow_through_sessions must be >= {MIN_FOLLOW_THROUGH_SESSIONS}, got {sessions}"
        raise RangeError(msg)

    return int(sessions)


def _reach(
    high: FloatArray,
    low: FloatArray,
    session_id: IndexArray,
    armed: BoolArray,
    n_sessions: int,
) -> tuple[FloatArray, FloatArray]:
    """Per session: the extreme prices of the bars that may trade the range, ``nan`` where none.

    The armed bars are the whole of the session past the window, so this is how far price
    actually went while an order could have been resting -- and therefore what a bracket
    denominated in the range could ever have reached.
    """
    reach_high: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    reach_low: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    inside: OffsetArray
    starts: OffsetArray
    of_session: IndexArray
    inside, starts, of_session = _session_runs(session_id, armed)
    if inside.size == 0:
        return reach_high, reach_low

    sessions: IndexArray = of_session[starts]
    reach_high[sessions] = np.maximum.reduceat(high[inside], starts)
    reach_low[sessions] = np.minimum.reduceat(low[inside], starts)

    return reach_high, reach_low


def follow_through(
    range_high: FloatArray,
    range_low: FloatArray,
    reach_high: FloatArray,
    reach_low: FloatArray,
) -> FloatArray:
    """How far past the range price travelled, in range widths -- the further of the two sides.

    One number per session: ``0`` where the range held all day, ``1`` where price extended a
    whole further range width beyond it. A session with no range, no bars past its window or a
    range of zero width has none -- ``docs/roadmap.md`` §M28.9.
    """
    width: FloatArray = range_high - range_low
    beyond: FloatArray = np.maximum(reach_high - range_high, range_low - reach_low)
    out: FloatArray = np.full(width.shape, np.nan, dtype=np.float64)

    return np.divide(np.maximum(beyond, 0.0), width, out=out, where=width > 0.0)


def trailing_median(values: FloatArray, sessions: int) -> FloatArray:
    """Per session: the median of the ``sessions`` most recent **earlier** sessions with a value.

    Strictly earlier, so no session contributes to its own statistic, and ``nan`` until that
    many have accumulated -- a scale with no history behind it is refused rather than
    approximated from what happens to be there, which is :func:`range_grid`'s rule for a short
    window read at one level up.
    """
    validate_follow_through_sessions(sessions)
    out: FloatArray = np.full(values.shape, np.nan, dtype=np.float64)
    measured: OffsetArray = np.flatnonzero(np.isfinite(values))
    if measured.size < sessions:
        return out

    windows: FloatArray = np.lib.stride_tricks.sliding_window_view(values[measured], sessions)
    medians: FloatArray = np.median(windows, axis=1)

    # How many earlier sessions carry a value; the window ending there is the one to read.
    seen: OffsetArray = np.searchsorted(measured, np.arange(values.size))
    enough: BoolArray = seen >= sessions
    out[enough] = medians[seen[enough] - sessions]

    return out


@dataclass(slots=True)
class FollowThroughGrid:
    """One session's follow-through per range, plus the trailing median at each declared lookback.

    Per session rather than per bar, exactly as :class:`SessionRangeGrid` holds its levels --
    follow-through is one fact about a session, and :attr:`SessionRangeGrid.session_id` is the
    index into both.
    """

    keys: tuple[RangeKey, ...]
    """The ranges measured, in :attr:`SessionRangeGrid.keys` order."""

    lookbacks: tuple[int, ...]
    """The trailing windows built, sorted and deduplicated."""

    raw: FloatArray
    """``[n_keys, n_sessions]``: each session's own follow-through, ``nan`` where it has none."""

    trailing: FloatArray
    """``[n_keys, n_lookbacks, n_sessions]``: :func:`trailing_median` of :attr:`raw`."""

    def row(self, key: RangeKey) -> int:
        """The row holding ``key``, or an error naming what the grid was built for."""
        if key not in self.keys:
            msg: str = f"range {key} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg)

        return self.keys.index(key)

    def lookback_row(self, sessions: int) -> int:
        """The row holding one trailing window, or an error naming the ones built."""
        if sessions not in self.lookbacks:
            msg: str = (
                f"follow-through over {sessions} sessions is not in this grid; built for "
                f"{list(self.lookbacks)}"
            )
            raise KeyError(msg)

        return self.lookbacks.index(sessions)

    def raw_for(self, key: RangeKey) -> FloatArray:
        """Per session: one range's own follow-through."""
        return np.asarray(self.raw[self.row(key)])

    def scale_for(self, key: RangeKey, sessions: int) -> FloatArray:
        """Per session: the trailing follow-through a bracket is denominated against."""
        return np.asarray(self.trailing[self.row(key), self.lookback_row(sessions)])

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed."""
        return self.raw.nbytes + self.trailing.nbytes


def follow_through_grid(
    high: FloatArray,
    low: FloatArray,
    ranges: SessionRangeGrid,
    lookbacks: Iterable[int],
) -> FollowThroughGrid:
    """Measure every range's follow-through once, and take each declared trailing median of it.

    Reads :class:`SessionRangeGrid` rather than re-deriving the windows, so the sessions a
    range exists for are the grid's decision and not a second opinion about it.
    """
    windows: tuple[int, ...] = tuple(
        sorted({validate_follow_through_sessions(n) for n in lookbacks}),
    )
    if not windows:
        msg: str = "no follow-through lookbacks supplied"
        raise RangeError(msg)

    n_sessions: int = ranges.sessions
    raw: FloatArray = np.full((len(ranges.keys), n_sessions), np.nan, dtype=np.float64)
    trailing: FloatArray = np.full(
        (len(ranges.keys), len(windows), n_sessions),
        np.nan,
        dtype=np.float64,
    )

    for i in range(len(ranges.keys)):
        reach_high: FloatArray
        reach_low: FloatArray
        reach_high, reach_low = _reach(high, low, ranges.session_id, ranges.armed[i], n_sessions)
        raw[i] = follow_through(ranges.high[i], ranges.low[i], reach_high, reach_low)
        for j, sessions in enumerate(windows):
            trailing[i, j] = trailing_median(raw[i], sessions)

    return FollowThroughGrid(keys=ranges.keys, lookbacks=windows, raw=raw, trailing=trailing)
