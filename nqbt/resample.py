"""Session-anchored bar aggregation: 1-minute bars into 2, 5, 15, 30 and so on.

Belongs to **context, not simulation** -- it produces bars, and knows nothing about trades
or strategies. :func:`nqbt.context.prepare` runs on whatever this returns.

## Resampling is exact, not approximate

OHLC aggregation is associative -- ``open=first, high=max, low=min, close=last,
volume=sum`` -- so a 5-minute bar assembled from five 1-minute bars is **bit-identical** to
one NinjaTrader assembles from ticks. A minute with no trades contributes nothing either
way. The existing 1-minute archive is therefore sufficient: **do not reach for
``data/tick/``**, which would be the more-precise-than-NT8 error the prime directive
forbids.

## The trap: anchoring

Buckets are counted in **minutes since the session open**, never by wall clock, and never
with a bare ``DataFrame.resample()``. NT8 restarts bar building at each session start, so
under the CME ETH template a 5-minute bar runs 18:00-18:05 ET.

For the periods anyone actually sweeps this happens to be harmless, and **that coincidence
is exactly why it must be tested rather than assumed** -- it holds for every period likely
to be tried first, then silently fails.

The usual statement of the coincidence is incomplete, so the exact rule is worth having.
Agreement needs a boundary at the session **open** *and* at the session **close**: 18:00 ET
is 1,080 minutes past midnight and 17:00 ET is 1,020, so the condition is
``N | gcd(1080, 1020)``, which is ``N | 60``. Dividing 1,080 alone is not enough -- **45
divides 1,080 and still diverges**, because a midnight-anchored grid then runs a bucket
from 16:45 to 17:30, straight through the maintenance break. ``tests/test_resample.py``
pins both halves, with 8 and 45 as the counter-examples.

Because the grouping key includes the trading day, no bar can span the 17:00-18:00
maintenance break or the Friday-to-Sunday weekend. That falls out of the anchoring rather
than needing its own rule.

## Timestamps are end-of-bar

Every timestamp in this project is the moment a bar **closed**. So a bar stamped 18:01
covers 18:00-18:01 and is the session's *first* minute, and a 5-minute bucket covering
18:00-18:05 is stamped **18:05**.

The final bucket of a session is stamped at the session's **observed** last bar rather than
at its theoretical end. Two cases need it: a period that does not divide the session (7
would put the last bucket's end at 17:06, past the close), and a holiday early close, where
the session simply stops. Deriving it from the data rather than from the template is the
same choice ``is_session_close`` makes, and avoids the trap #68 records against
``force_flat_mask``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nqbt import sessions
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH, SessionTemplate

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
"""How an unrecognised column collapses.

``contract`` is the one that exists today, and ``last`` agrees with ``close`` -- a bucket is
labelled with the contract whose price closed it. Any future label column gets the same
treatment, which is a guess, so it is stated here rather than buried in a ``dict.get``.
"""


class ResampleError(ValueError):
    """Raised when bars cannot be aggregated to the requested resolution."""


def minutes_since_open(
    index: pd.DatetimeIndex, template: SessionTemplate = CME_US_INDEX_FUTURES_ETH
) -> np.ndarray:
    """How far each **end-of-bar** timestamp sits past its session's open, in minutes.

    The session runs 18:00 -> 17:00 ET, so a bar's seconds-of-day is either already past
    the open (the evening portion) or belongs to the next calendar day and needs a day
    added. Runs 1 to 1,380 over a full session: the bar stamped 18:01 is minute 1, and the
    bar stamped 17:00 is minute 1,380.

    No DST bookkeeping is needed. US transitions happen at 02:00 ET on a Sunday and the
    market is shut from Friday 17:00 to Sunday 18:00, so no session ever spans one.
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
) -> tuple[np.ndarray, np.ndarray]:
    """Per bar: which bucket it falls in, and how many minutes to its bucket's close.

    A bar stamped at minute ``m`` of the session *occupies* index ``m - 1``, because the
    stamp is its close. Getting that off by one puts every boundary one minute out, which
    is invisible at 1 minute and wrong everywhere else.
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

    ``minutes=1`` returns the frame unchanged. That is not just an optimisation: the
    1-minute path is the one every reconciliation and every captured trade log was produced
    against, so resampling must not be able to perturb it even by dropping a row.

    For ``minutes >= 2``, **out-of-session bars are dropped**. Exported files contain stray
    prints outside session hours -- an isolated Saturday bar with volume 1 -- and such a bar
    has no session to be anchored to, so there is no bucket it could honestly join. This
    matches what ``splice.build_continuous`` already does to the continuous series; it
    differs from a per-contract 1-minute frame, which keeps them. See the "out-of-session
    stray prints" note in ``CLAUDE.md``.
    """
    if minutes < 1:
        raise ResampleError(f"minutes must be >= 1, got {minutes}")
    if minutes == 1:
        return bars
    if bars.empty:
        return bars

    info = sessions.classify(bars.index, template)
    frame = bars[info.in_session]
    if frame.empty:
        return frame

    day = info.trading_day[info.in_session]
    bucket, to_close = bucket_index(frame.index, minutes, template)

    # One integer group id per (trading day, bucket). Including the day is what stops a
    # bucket spanning the maintenance break or the weekend -- those are different sessions,
    # so they cannot share a group however close their bucket numbers land.
    starts_group = np.empty(len(frame), dtype=bool)
    starts_group[0] = True
    starts_group[1:] = (day[1:] != day[:-1]) | (bucket[1:] != bucket[:-1])
    gid = np.cumsum(starts_group) - 1

    how = {c: AGGREGATIONS.get(c, PASSTHROUGH) for c in frame.columns}
    out = frame.groupby(gid, sort=False).agg(how)

    # Stamp each bucket at its close: this bar's own close plus the minutes still to run.
    # Then cap at the session's observed last bar, for a period that does not divide the
    # session and for a holiday early close. Integer nanoseconds throughout -- a tz-aware
    # DatetimeIndex hands back object dtype, which will not take a timedelta.
    # ``dtype=`` is not optional: pandas hands back datetime64[us] here, and reading that
    # as nanoseconds puts every bar in 1970.
    ns = frame.index.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]").astype("int64")
    closes = ns + to_close * 60 * 1_000_000_000
    session_last = pd.Series(ns).groupby(day).transform("max").to_numpy()
    stamped = np.minimum(closes, session_last)

    first_of_group = np.flatnonzero(starts_group)
    out.index = pd.DatetimeIndex(
        stamped[first_of_group].astype("datetime64[ns]"), tz="UTC", name=bars.index.name
    )
    return out[list(bars.columns)]
