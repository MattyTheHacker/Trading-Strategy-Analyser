"""Tests for session-anchored bar aggregation.

The aggregation itself is arithmetic and hard to get wrong. **The anchoring is the part
that fails silently**, and it fails in a way that looks fine for every period anyone tries
first, so most of what follows is about boundaries rather than about OHLC.

Groups are reconstructed here from the *output* timestamps alone -- ``searchsorted`` over
the returned index -- rather than by recomputing the module's own bucket ids. A test that
regroups with the implementation's own key cannot catch the implementation mis-grouping.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import resample, sessions
from nqbt.resample import ResampleError

AGREES_WITH_WALL_CLOCK = (2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
"""Periods for which session-anchored and midnight-anchored bucketing coincide.

These are the divisors of 60, and the reason is **two** constraints rather than the one
usually quoted. Dividing the 1,080 minutes from midnight to the 18:00 open puts a
boundary at the session open; dividing the 1,020 minutes to the 17:00 close puts one at
the session close. Agreement needs both, so the condition is
``N | gcd(1080, 1020) == N | 60``.

45 is the counter-example that matters: it divides 1,080, so the open lines up, but it
does not divide 1,020, so a midnight-anchored grid runs a bucket straight through the
16:45-17:30 maintenance break.
"""


def minute_bars(sessions_wanted: int = 3, seed: int = 11) -> pd.DataFrame:
    """Full ETH sessions of 1-minute bars, 18:00 -> 17:00 ET, weekdays only.

    Built session by session from the open rather than by slicing a date range, so the
    first bucket of every session is complete and boundary assertions mean something.
    """
    rng = np.random.default_rng(seed)
    stamps: list[pd.Timestamp] = []
    # 2024-01-02 is a Tuesday; its session opens Monday 2024-01-01 at 18:00 ET.
    open_et = pd.Timestamp("2024-01-01 18:00", tz=sessions.EASTERN)
    for _ in range(sessions_wanted):
        # 1,380 bars: the first is stamped 18:01 and the last 17:00 the next day.
        stamps.extend(open_et + pd.Timedelta(minutes=m) for m in range(1, 1381))
        open_et = open_et + pd.Timedelta(days=1)
        while open_et.dayofweek in (4, 5):  # Friday 18:00 and Saturday 18:00 do not open
            open_et = open_et + pd.Timedelta(days=1)

    idx = pd.DatetimeIndex(stamps).tz_convert("UTC")
    idx.name = "ts_utc"
    n = len(idx)
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day
    return frame


def groups_from_output(source: pd.DataFrame, out: pd.DataFrame) -> list[pd.DataFrame]:
    """Split the 1-minute bars by which output bar's window they land in.

    Uses only the returned timestamps, so it is independent of how the module grouped.
    """
    edges = out.index.to_numpy(dtype="datetime64[ns]")
    pos = np.searchsorted(edges, source.index.to_numpy(dtype="datetime64[ns]"), side="left")
    return [source[pos == i] for i in range(len(out))]


# -- the aggregation is exact --------------------------------------------------


@pytest.mark.parametrize("minutes", [2, 3, 5, 7, 15, 30])
def test_every_bar_matches_the_minutes_it_was_built_from(minutes):
    src = minute_bars()
    out = resample.resample(src, minutes)
    assert len(out) < len(src)

    for row, members in zip(out.itertuples(), groups_from_output(src, out)):
        assert len(members), f"output bar {row.Index} has no source bars"
        assert row.open == members["open"].iloc[0]
        assert row.high == members["high"].max()
        assert row.low == members["low"].min()
        assert row.close == members["close"].iloc[-1]
        assert row.volume == members["volume"].sum()


def test_no_bar_is_lost_or_double_counted():
    src = minute_bars()
    out = resample.resample(src, 5)
    assert sum(len(g) for g in groups_from_output(src, out)) == len(src)
    assert out["volume"].sum() == src["volume"].sum()


def test_one_minute_is_the_identity_and_returns_the_frame_untouched():
    """The 1-minute path carries every reconciliation; resampling must not perturb it."""
    src = minute_bars()
    assert resample.resample(src, 1) is src


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_a_period_below_one_minute_is_refused(bad):
    with pytest.raises(ResampleError, match="must be >= 1"):
        resample.resample(minute_bars(1), bad)


# -- anchoring -----------------------------------------------------------------


@pytest.mark.parametrize("minutes", [2, 3, 5, 7, 15, 30, 60])
def test_every_bucket_closes_a_whole_number_of_periods_after_the_session_open(minutes):
    src = minute_bars()
    out = resample.resample(src, minutes)
    end_minute = resample.minutes_since_open(out.index)
    session_last = 1380  # a full ETH session, 18:00 -> 17:00

    for m in end_minute:
        assert m % minutes == 0 or m == session_last, (
            f"bucket closes {m} minutes into the session, which is neither a multiple "
            f"of {minutes} nor the session close"
        )


def test_the_first_bar_of_a_session_covers_the_first_period_from_the_open():
    src = minute_bars()
    out = resample.resample(src, 5)
    first_per_day = out.groupby(out["trading_day"]).head(1)
    assert (resample.minutes_since_open(first_per_day.index) == 5).all()


def test_the_last_bar_of_a_session_is_stamped_at_the_close_not_past_it():
    """With 7, the final bucket would otherwise run to 17:06 -- an hour into the break."""
    src = minute_bars()
    out = resample.resample(src, 7)
    last_per_day = out.groupby(out["trading_day"]).tail(1)
    assert (resample.minutes_since_open(last_per_day.index) == 1380).all()

    et = sessions.to_eastern(last_per_day.index)
    assert set(et.strftime("%H:%M")) == {"17:00"}


# -- boundaries no bar may cross -----------------------------------------------


@pytest.mark.parametrize("minutes", [2, 5, 7, 15, 30])
def test_no_bar_spans_the_maintenance_break_or_the_weekend(minutes):
    """Both fall out of including the trading day in the grouping key.

    The break and the weekend are the same defect wearing different clothes: a bucket that
    joined 16:59 to 18:01 would carry an hour of nothing, and one that joined Friday to
    Sunday would carry two days of it.
    """
    src = minute_bars(sessions_wanted=5)  # spans a Friday -> Monday handover
    out = resample.resample(src, minutes)

    for row, members in zip(out.itertuples(), groups_from_output(src, out)):
        assert members["trading_day"].nunique() == 1, (
            f"bar {row.Index} mixes trading days {sorted(set(members['trading_day']))}"
        )
        assert len(members) <= minutes, f"bar {row.Index} holds {len(members)} minutes"


def test_a_bars_own_close_stamp_classifies_to_the_session_it_aggregated():
    """Catches a bucket stamped past the close, which would re-date it to the next day."""
    src = minute_bars(sessions_wanted=5)
    out = resample.resample(src, 7)
    assert (sessions.classify(out.index).trading_day == out["trading_day"].to_numpy()).all()


def test_out_of_session_prints_are_dropped_rather_than_given_a_bucket():
    """A Saturday print has no session to be anchored to. See CLAUDE.md on stray prints."""
    src = minute_bars(1)
    stray = src.iloc[[0]].copy()
    stray.index = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-06 15:00", tz=sessions.EASTERN).tz_convert("UTC")],
        name=src.index.name,
    )
    stray["volume"] = 1.0
    polluted = pd.concat([src, stray]).sort_index()

    assert len(polluted) == len(src) + 1
    out = resample.resample(polluted, 5)
    assert out["volume"].sum() == src["volume"].sum(), "the stray reached a bucket"


# -- the coincidence, made into a documented property --------------------------


def midnight_anchored(src: pd.DataFrame, minutes: int) -> pd.DatetimeIndex:
    """What a bare ``resample()`` would produce: buckets counted from midnight."""
    grouped = src.resample(f"{minutes}min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return grouped.dropna(subset=["open"]).index


@pytest.mark.parametrize("minutes", AGREES_WITH_WALL_CLOCK)
def test_session_and_midnight_anchoring_agree_for_divisors_of_sixty(minutes):
    """The coincidence that makes the bug invisible, pinned as a property.

    Every period anyone reaches for first is in this list, which is exactly why nobody
    should "simplify" this module into a bare ``resample()`` on the strength of it.
    """
    assert 1080 % minutes == 0 and 1020 % minutes == 0, "this test's premise"
    src = minute_bars()
    assert resample.resample(src, minutes).index.equals(midnight_anchored(src, minutes))


@pytest.mark.parametrize("minutes", [7, 11, 16, 25, 8, 45])
def test_the_two_anchorings_diverge_for_a_period_that_does_not_divide_sixty(minutes):
    """The other half, and the reason the agreement above is not a licence.

    8 and 45 are the interesting entries: both divide 1,080, so the *open* lines up and
    the usual one-line justification says they should agree. They do not, because
    neither divides 1,020 and so the session *close* does not land on a boundary.
    """
    assert 60 % minutes != 0, "this test's premise"
    src = minute_bars()
    ours = resample.resample(src, minutes).index
    theirs = midnight_anchored(src, minutes)
    assert not ours.equals(theirs), (
        f"{minutes} does not divide 1,080, so a midnight-anchored bucket cannot line up "
        "with the session open -- if these now agree, the anchoring has been lost"
    )


# -- real bars -----------------------------------------------------------------


def test_a_real_contract_resamples_with_every_bar_inside_one_session():
    """Synthetic sessions are tidy; real ones have gaps, thin nights and early closes."""
    pytest.importorskip("pyarrow")
    splice = pytest.importorskip("nqbt.splice")
    try:
        bars = splice.load_continuous("MNQ", back_adjust=True)
    except Exception:  # pragma: no cover - the cache is not in CI
        pytest.skip("no spliced MNQ cache on this machine")

    bars = bars[(bars.index >= "2024-01-01") & (bars.index < "2024-02-01")]
    out = resample.resample(bars, 15)
    assert len(out)
    assert out.index.is_monotonic_increasing
    assert not out.index.has_duplicates
    assert (sessions.classify(out.index).trading_day == out["trading_day"].to_numpy()).all()
    assert out["volume"].sum() == bars[sessions.classify(bars.index).in_session]["volume"].sum()
