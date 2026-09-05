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
    "RangeError",
    "RangeKey",
    "SessionRangeGrid",
    "anchor_for",
    "range_grid",
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


def _extremes(
    high: FloatArray,
    low: FloatArray,
    session_id: IndexArray,
    in_window: BoolArray,
    n_sessions: int,
    expected_bars: int,
) -> tuple[FloatArray, FloatArray]:
    """One high and one low per session, ``nan`` unless the window is entirely present.

    ``reduceat`` over the in-window bars rather than ``maximum.at`` over all of them: the bars
    of one session's window are contiguous, so the groups are slices.
    """
    session_high: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    session_low: FloatArray = np.full(n_sessions, np.nan, dtype=np.float64)
    inside: OffsetArray = np.flatnonzero(in_window)
    if inside.size == 0:
        return session_high, session_low

    of_session: IndexArray = session_id[inside]
    starts: OffsetArray = np.flatnonzero(
        np.concatenate(([True], of_session[1:] != of_session[:-1])),
    )
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
