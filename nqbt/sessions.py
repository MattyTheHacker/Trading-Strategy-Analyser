"""CME session calendar and UTC -> US/Eastern conversion.

NT8's exported timestamps are **end-of-bar and in UTC**; everything downstream reasons in
US/Eastern, which is what the session template is defined in. The CME US Index Futures ETH
session runs 18:00 ET to 17:00 ET the following day with a 17:00-18:00 maintenance break, and
is labelled by the date it *ends* on -- NT8's trading-day convention.

**No session ever spans a DST transition**, because US transitions fall at 02:00 ET on a
Sunday and the market is shut from Friday 17:00 to Sunday 18:00. So once converted to Eastern,
naive wall-clock arithmetic within a session is exact.

Exported files contain stray prints outside session hours, which NT8 building bars against an
ETH template would never form; :func:`classify` marks them out of session.

**The template's 17:00 close is the scheduled one.** The session end everything downstream
counts down to is the trading day's last in-session bar, which is where a CME half-day actually
stops -- ``docs/nt8-fidelity.md``, "The session end is the observed last bar, not the
template's".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, DateArray, FloatArray, IntArray, OffsetArray

EASTERN: str = "America/New_York"
FRIDAY: int = 4  # ``DatetimeIndex.dayofweek`` for the last weekday a session may end on.


@dataclass(frozen=True, slots=True)
class SessionTemplate:
    """A daily session definition, expressed in exchange local time."""

    name: str
    tz: str = EASTERN
    open_time: time = time(18, 0)
    close_time: time = time(17, 0)

    @property
    def open_seconds(self) -> int:
        """The session open as seconds past midnight, exchange local."""
        return self.open_time.hour * 3600 + self.open_time.minute * 60 + self.open_time.second

    @property
    def close_seconds(self) -> int:
        """The session close as seconds past midnight, exchange local."""
        return self.close_time.hour * 3600 + self.close_time.minute * 60 + self.close_time.second


CME_US_INDEX_FUTURES_ETH = SessionTemplate(name="CME US Index Futures ETH")

TEMPLATES: dict[str, SessionTemplate] = {
    CME_US_INDEX_FUTURES_ETH.name: CME_US_INDEX_FUTURES_ETH,
}


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Per-bar session classification, aligned to the input index."""

    eastern: pd.DatetimeIndex  # Bar end timestamps converted to exchange local time (tz-aware).
    trading_day: DateArray  # ``datetime64[D]``: the date each bar's session ends on.
    in_session: BoolArray  # Bool: bar falls inside a real session (not the break, not a weekend print).
    is_session_open: BoolArray  # Bool: first in-session bar of its trading day.
    is_session_close: BoolArray  # Bool: last in-session bar of its trading day.

    def __len__(self) -> int:
        return len(self.eastern)


def to_eastern(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert a UTC (or naive-assumed-UTC) index to US/Eastern."""
    if index.tz is None:
        index = index.tz_localize("UTC")

    return index.tz_convert(EASTERN)


def classify(index: pd.DatetimeIndex, template: SessionTemplate = CME_US_INDEX_FUTURES_ETH) -> SessionInfo:
    """Assign each bar to a trading day and flag whether it is inside a session.

    ``index`` holds **end-of-bar** timestamps. A bar stamped exactly at the close time
    (17:00:00) is the session's final bar, since it covers 16:59-17:00. A bar stamped in
    (17:00, 18:00] falls in the maintenance break and cannot be real.
    """
    eastern: pd.DatetimeIndex = to_eastern(pd.DatetimeIndex(index))
    naive: pd.DatetimeIndex = eastern.tz_localize(None)

    seconds: pd.Index[int] = naive.hour * 3600 + naive.minute * 60 + naive.second
    after_close: BoolArray = seconds > template.close_seconds

    # Bars after the close belong to the session ending on the following calendar day.
    day: pd.DatetimeIndex = naive.normalize()
    trading_ts: pd.DatetimeIndex = day + pd.to_timedelta(after_close.astype("int8"), unit="D")

    in_break: BoolArray = after_close & (seconds <= template.open_seconds)
    is_weekday: BoolArray = trading_ts.dayofweek <= FRIDAY
    in_session: BoolArray = np.asarray(~in_break & is_weekday)

    trading_day: DateArray = trading_ts.to_numpy().astype("datetime64[D]")

    is_open, is_close = _session_edges(trading_day, in_session)

    return SessionInfo(
        eastern=eastern,
        trading_day=trading_day,
        in_session=in_session,
        is_session_open=is_open,
        is_session_close=is_close,
    )


def _session_edges(trading_day: DateArray, in_session: BoolArray) -> tuple[BoolArray, BoolArray]:
    """Flag the first and last in-session bar of each trading day.

    Assumes the arrays are in ascending timestamp order, which ingestion guarantees.
    """
    n: int = trading_day.size
    is_open: BoolArray = np.zeros(n, dtype=bool)
    is_close: BoolArray = np.zeros(n, dtype=bool)
    if n == 0:
        return is_open, is_close

    idx: OffsetArray = np.flatnonzero(in_session)
    if idx.size == 0:
        return is_open, is_close

    days: DateArray = trading_day[idx]
    boundary: BoolArray = np.empty(idx.size, dtype=bool)
    boundary[0] = True
    boundary[1:] = days[1:] != days[:-1]

    is_open[idx[boundary]] = True
    # The bar before each new session's first bar is the previous session's last.
    last_positions: BoolArray = np.empty(idx.size, dtype=bool)
    last_positions[-1] = True
    last_positions[:-1] = boundary[1:]
    is_close[idx[last_positions]] = True

    return is_open, is_close


def force_flat_mask(
    info: SessionInfo,
    exit_on_close_seconds: int = 30,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> BoolArray:
    """Bars at or past the exit-on-session-close cutoff.

    Mirrors NT8's ``IsExitOnSessionCloseStrategy`` with ``ExitOnSessionCloseSeconds``: a bar
    triggers the flatten when its end timestamp reaches ``session_end - seconds``. A mask
    rather than one index per session, so the simulation asks only "must I be flat here?".

    Every session's last bar is in the mask, holiday early closes included --
    ``docs/nt8-fidelity.md``, "The session end is the observed last bar, not the template's".
    """
    return info.in_session & (seconds_to_session_end(info, template) <= float(exit_on_close_seconds))


def seconds_to_session_end(info: SessionInfo, template: SessionTemplate = CME_US_INDEX_FUTURES_ETH) -> FloatArray:
    """Seconds from each bar's end timestamp to its session's end, which is its last bar.

    Reaches exactly zero on that bar. The quantity both :func:`force_flat_mask` and a no-entry
    window before the close are cut from, so the two cannot drift apart --
    ``docs/nt8-fidelity.md``, "A no-entry window before the session close".
    """
    return (_session_end_seconds(info, template) - _epoch_seconds(info.eastern)).astype(np.float64)


def _epoch_seconds(eastern: pd.DatetimeIndex) -> IntArray:
    """Eastern wall-clock timestamps as whole seconds since the epoch, offset discarded."""
    return eastern.tz_localize(None).to_numpy().astype("datetime64[s]").astype(np.int64)


def _session_end_seconds(info: SessionInfo, template: SessionTemplate) -> IntArray:
    """Each bar's session end as epoch seconds: the last in-session bar of its trading day.

    Observed rather than scheduled, because NT8's trading-hours template carries the holiday
    calendar and the data is the only place that calendar can be read from here. Falls back to
    the template's fixed close for a trading day holding no in-session bar at all.

    Assumes ascending timestamp order, as :func:`_session_edges` does.
    """
    # Epoch seconds on both sides: numpy types ``datetime64 + timedelta64`` as ``timedelta64``,
    # which then refuses the subtraction.
    end: IntArray = info.trading_day.astype("datetime64[s]").astype(np.int64) + template.close_seconds

    closes: OffsetArray = np.flatnonzero(info.is_session_close)
    if closes.size == 0:
        return end

    closing_day: DateArray = info.trading_day[closes]
    slot: OffsetArray = np.searchsorted(closing_day, info.trading_day).clip(max=closes.size - 1)
    has_close: BoolArray = closing_day[slot] == info.trading_day

    end[has_close] = _epoch_seconds(info.eastern)[closes][slot[has_close]]
    return end
