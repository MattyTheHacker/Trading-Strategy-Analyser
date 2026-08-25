"""Session-anchored bar aggregation: 1-minute bars into 2, 5, 15, 30 and so on.

Buckets are counted in minutes since the session open, never by wall clock, and timestamps are
end-of-bar throughout. Aggregation is exact rather than approximate, so the 1-minute archive is
sufficient and ``data/tick/`` must not be touched. Reasoning and the anchoring trap:
``docs/roadmap.md`` §M13.

Belongs to context, not simulation: it produces bars and knows nothing about trades.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import sessions
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH, SessionTemplate

if TYPE_CHECKING:
    from nqbt.arrays import IntArray

SECONDS_PER_DAY = 86_400

AGGREGATIONS: dict[str, str] = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "trading_day": "first",
}
"""How each known column collapses. Associative, which is what makes this exact."""

PASSTHROUGH = "last"
"""How an unrecognised column collapses: a bucket takes the label of the bar that closed it."""


class ResampleError(ValueError):
    """Raised when bars cannot be aggregated to the requested resolution."""


def minutes_since_open(
    index: pd.DatetimeIndex,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> IntArray:
    """How far each end-of-bar timestamp sits past its session's open, in minutes.

    Runs 1 to 1,380 over a full 18:00 -> 17:00 ET session. No DST bookkeeping is needed: US
    transitions fall at 02:00 ET on a Sunday, when the market is shut.
    """
    naive = sessions.to_eastern(pd.DatetimeIndex(index)).tz_localize(None)
    seconds = (naive.hour * 3600 + naive.minute * 60 + naive.second).to_numpy()
    open_s = template.open_seconds
    past_open = np.where(seconds > open_s, seconds - open_s, seconds + SECONDS_PER_DAY - open_s)
    return (past_open // 60).astype(np.int64)


def bucket_index(
    index: pd.DatetimeIndex,
    minutes: int,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> tuple[IntArray, IntArray]:
    """Per bar: which bucket it falls in, and how many minutes to its bucket's close.

    A bar stamped at minute ``m`` occupies index ``m - 1``, because the stamp is its close.
    """
    end_minute = minutes_since_open(index, template)
    occupies = end_minute - 1
    bucket = occupies // minutes
    to_bucket_close = (bucket + 1) * minutes - end_minute
    return bucket, to_bucket_close


def resample(
    bars: pd.DataFrame,
    minutes: int,
    *,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> pd.DataFrame:
    """Aggregate 1-minute ``bars`` to ``minutes``-minute bars, anchored to the session open.

    ``minutes=1`` returns the frame unchanged; ``minutes >= 2`` drops out-of-session bars.
    Both are load-bearing -- ``docs/roadmap.md`` §M13.
    """
    if minutes < 1:
        msg = f"minutes must be >= 1, got {minutes}"
        raise ResampleError(msg)
    if minutes == 1:
        return bars
    if bars.empty:
        return bars

    info = sessions.classify(pd.DatetimeIndex(bars.index), template)
    frame = bars[info.in_session]
    if frame.empty:
        return frame

    day = info.trading_day[info.in_session]
    stamps = pd.DatetimeIndex(frame.index)
    bucket, to_close = bucket_index(stamps, minutes, template)

    # Group id per (trading day, bucket). The day is what stops a bucket spanning the
    # maintenance break or the weekend.
    starts_group = np.empty(len(frame), dtype=bool)
    starts_group[0] = True
    starts_group[1:] = (day[1:] != day[:-1]) | (bucket[1:] != bucket[:-1])
    gid = np.cumsum(starts_group) - 1

    how = {c: AGGREGATIONS.get(c, PASSTHROUGH) for c in frame.columns}
    out = frame.groupby(gid, sort=False).agg(how)

    # Stamp each bucket at its close, capped at the session's observed last bar. Integer
    # nanoseconds throughout, because a tz-aware DatetimeIndex hands back object dtype;
    # ``dtype=`` is not optional, since pandas otherwise returns datetime64[us] and reading
    # that as nanoseconds puts every bar in 1970.
    ns = stamps.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")
    closes = ns + to_close * 60 * 1_000_000_000
    session_last = pd.Series(ns).groupby(day).transform("max").to_numpy()
    stamped = np.minimum(closes, session_last)

    first_of_group = np.flatnonzero(starts_group)
    out.index = pd.DatetimeIndex(
        stamped[first_of_group].astype("datetime64[ns]"),
        tz="UTC",
        name=bars.index.name,
    )
    return out[list(bars.columns)]
