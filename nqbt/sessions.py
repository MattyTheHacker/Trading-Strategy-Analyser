"""CME session calendar and UTC -> US/Eastern conversion.

NT8's exported timestamps are **end-of-bar and in UTC**. Everything downstream reasons in
US/Eastern, because that is what the session template is defined in and what a trader
reads off a chart.

The CME US Index Futures ETH session runs 18:00 ET to 17:00 ET the following day, with a
17:00-18:00 maintenance break, Sunday evening through Friday afternoon. A session is
labelled by the date it *ends* on -- NT8's trading-day convention -- so the session opening
Sunday 18:00 is Monday's session.

One consequence worth stating because it makes the code simpler than it looks: **no session
ever spans a DST transition.** US transitions happen at 02:00 ET on a Sunday, and the market
is closed from Friday 17:00 to Sunday 18:00. So once timestamps are converted to Eastern,
naive wall-clock arithmetic within a session is exact and needs no offset bookkeeping.

Exported files also contain stray prints outside session hours -- isolated bars with volume
1 on a Saturday, for instance. NT8 building bars against an ETH template would never form
these at all, so :func:`classify` marks them out of session and the continuous-series
builder drops them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

EASTERN = "America/New_York"


@dataclass(frozen=True, slots=True)
class SessionTemplate:
    """A daily session definition, expressed in exchange local time."""

    name: str
    tz: str = EASTERN
    open_time: time = time(18, 0)
    close_time: time = time(17, 0)

    @property
    def open_seconds(self) -> int:
        return self.open_time.hour * 3600 + self.open_time.minute * 60 + self.open_time.second

    @property
    def close_seconds(self) -> int:
        return self.close_time.hour * 3600 + self.close_time.minute * 60 + self.close_time.second


CME_US_INDEX_FUTURES_ETH = SessionTemplate(name="CME US Index Futures ETH")

TEMPLATES: dict[str, SessionTemplate] = {
    CME_US_INDEX_FUTURES_ETH.name: CME_US_INDEX_FUTURES_ETH,
}


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Per-bar session classification, aligned to the input index."""

    eastern: pd.DatetimeIndex
    """Bar end timestamps converted to exchange local time (tz-aware)."""
    trading_day: np.ndarray
    """``datetime64[D]``: the date each bar's session ends on."""
    in_session: np.ndarray
    """Bool: bar falls inside a real session (not the break, not a weekend print)."""
    is_session_open: np.ndarray
    """Bool: first in-session bar of its trading day."""
    is_session_close: np.ndarray
    """Bool: last in-session bar of its trading day."""

    def __len__(self) -> int:
        return len(self.eastern)


def to_eastern(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert a UTC (or naive-assumed-UTC) index to US/Eastern."""
    if index.tz is None:
        index = index.tz_localize("UTC")
    return index.tz_convert(EASTERN)


def classify(
    index: pd.DatetimeIndex,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> SessionInfo:
    """Assign each bar to a trading day and flag whether it is inside a session.

    ``index`` holds **end-of-bar** timestamps. A bar stamped exactly at the close time
    (17:00:00) is the session's final bar, since it covers 16:59-17:00. A bar stamped in
    (17:00, 18:00] falls in the maintenance break and cannot be real.
    """
    eastern = to_eastern(pd.DatetimeIndex(index))
    naive = eastern.tz_localize(None)

    seconds = naive.hour * 3600 + naive.minute * 60 + naive.second
    after_close = seconds > template.close_seconds

    # Bars after the close belong to the session ending on the following calendar day.
    day = naive.normalize()
    trading_ts = day + pd.to_timedelta(after_close.astype("int8"), unit="D")

    in_break = after_close & (seconds <= template.open_seconds)
    is_weekday = trading_ts.dayofweek <= 4
    in_session = np.asarray(~in_break & is_weekday)

    trading_day = trading_ts.to_numpy().astype("datetime64[D]")

    is_open, is_close = _session_edges(trading_day, in_session)

    return SessionInfo(
        eastern=eastern,
        trading_day=trading_day,
        in_session=in_session,
        is_session_open=is_open,
        is_session_close=is_close,
    )


def _session_edges(trading_day: np.ndarray, in_session: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flag the first and last in-session bar of each trading day.

    Assumes the arrays are in ascending timestamp order, which ingestion guarantees.
    """
    n = trading_day.size
    is_open = np.zeros(n, dtype=bool)
    is_close = np.zeros(n, dtype=bool)
    if n == 0:
        return is_open, is_close

    idx = np.flatnonzero(in_session)
    if idx.size == 0:
        return is_open, is_close

    days = trading_day[idx]
    boundary = np.empty(idx.size, dtype=bool)
    boundary[0] = True
    boundary[1:] = days[1:] != days[:-1]

    is_open[idx[boundary]] = True
    # The bar before each new session's first bar is the previous session's last.
    last_positions = np.empty(idx.size, dtype=bool)
    last_positions[-1] = True
    last_positions[:-1] = boundary[1:]
    is_close[idx[last_positions]] = True

    return is_open, is_close


def force_flat_mask(
    info: SessionInfo,
    exit_on_close_seconds: int = 30,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> np.ndarray:
    """Bars at or past the exit-on-session-close cutoff.

    Mirrors NT8's ``IsExitOnSessionCloseStrategy`` with ``ExitOnSessionCloseSeconds``:
    a bar triggers the flatten when its end timestamp reaches ``session_end - seconds``.
    With 1-minute bars and the default 30s that is the bar stamped 17:00:00 -- the last
    bar of the session -- because the preceding bar ends at 16:59:00, still short of the
    16:59:30 cutoff.

    Returns a mask rather than a single index per session so the simulation can simply
    check "must I be flat on this bar?" without any grouping logic.
    """
    naive = info.eastern.tz_localize(None).to_numpy()
    session_end = info.trading_day.astype("datetime64[s]") + np.timedelta64(template.close_seconds, "s")
    cutoff = session_end - np.timedelta64(int(exit_on_close_seconds), "s")
    return info.in_session & (naive.astype("datetime64[s]") >= cutoff)
