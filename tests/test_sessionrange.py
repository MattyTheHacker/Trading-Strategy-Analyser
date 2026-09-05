"""Tests for the session-anchored range primitive.

Three things it has to get right and nothing else can check: *which* bars the window covers,
that a session missing part of its window gets no range at all rather than a narrow one, and
that a range the bar size cannot express fails loudly instead of being measured over a
different span. The last is §M28's finding 2, and it is pinned here rather than written in a
comment because the alignment holding for the sizes anyone sweeps is exactly why it must be
tested.
"""

from math import gcd

import numpy as np
import pandas as pd
import pytest

from nqbt import sessionrange, sessions, timeofday
from nqbt.sessionrange import (
    CASH_OPEN_MINUTES,
    ETH_OPEN_MINUTES,
    RangeError,
    anchor_for,
    range_grid,
    validate_key,
)
from nqbt.timeofday import SessionPhase

CASH_WINDOW_30 = (CASH_OPEN_MINUTES, 30)


def minute_frame(days: int = 4, start: str = "2024-01-02 00:00") -> pd.DataFrame:
    """In-session 1-minute bars over ``days`` calendar days, every bar priced identically.

    Flat on purpose: a test states the geometry by writing highs and lows into the window it
    cares about, rather than reverse-engineering a series that produces them.
    """
    index = pd.date_range(start, periods=days * 1440, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )
    info = sessions.classify(index)
    frame["trading_day"] = info.trading_day

    return frame[info.in_session]


def eastern_minutes(frame: pd.DataFrame) -> pd.Index:
    """Wall-clock minutes past midnight Eastern, for placing a bar by the clock."""
    eastern = sessions.to_eastern(pd.DatetimeIndex(frame.index)).tz_localize(None)

    return eastern.hour * 60 + eastern.minute


def in_cash_window(frame: pd.DataFrame, minutes: int = 30) -> np.ndarray:
    """Mask of the bars covering the first ``minutes`` of cash trading, by the wall clock.

    Independent of :mod:`nqbt.sessionrange`'s own arithmetic, which is the point.
    """
    clock = eastern_minutes(frame)

    return np.asarray((clock > 9 * 60 + 30) & (clock <= 9 * 60 + 30 + minutes))


# -- the anchors ---------------------------------------------------------------


def test_the_cash_anchor_is_derived_from_the_phase_table_not_written_down() -> None:
    """930 is a consequence of the 18:00 open and the 09:30 phase start, not a constant."""
    assert CASH_OPEN_MINUTES == anchor_for(SessionPhase.CASH_OPEN)
    assert CASH_OPEN_MINUTES == int(timeofday.phase_start_minutes()[int(SessionPhase.CASH_OPEN)])
    assert CASH_OPEN_MINUTES == 930, "the ETH template moved; every window axis moves with it"


def test_the_overnight_anchor_is_the_session_open_itself() -> None:
    assert ETH_OPEN_MINUTES == anchor_for(SessionPhase.OVERNIGHT) == 0


# -- what the window covers ----------------------------------------------------


def test_the_range_is_the_windows_own_high_and_low_and_nothing_elses() -> None:
    """The extremes come from the window's bars; a spike outside it must not reach them."""
    frame = minute_frame()
    window = in_cash_window(frame)
    frame.loc[frame.index[window][3], "high"] = 110.0
    frame.loc[frame.index[window][7], "low"] = 90.0
    # A bigger spike one bar after the window closes, which must be invisible to the range.
    after = np.flatnonzero(window)[-1] + 1
    frame.iloc[after, frame.columns.get_loc("high")] = 999.0
    frame.iloc[after, frame.columns.get_loc("low")] = 1.0

    grid = range_grid(frame, [CASH_WINDOW_30], bar_minutes=1)
    highs = grid.high_for(CASH_WINDOW_30)
    lows = grid.low_for(CASH_WINDOW_30)

    assert highs[0] == 110.0
    assert lows[0] == 90.0
    assert (highs[1:] == 100.0).all(), "one session's spike leaked into another's range"
    assert (lows[1:] == 100.0).all()


def test_the_range_arms_on_the_bar_that_completes_the_window_and_stays_armed() -> None:
    """Not one bar earlier -- an order resting before the range is known is lookahead."""
    frame = minute_frame()
    grid = range_grid(frame, [CASH_WINDOW_30], bar_minutes=1)
    armed = grid.armed_for(CASH_WINDOW_30)
    clock = eastern_minutes(frame)
    session = np.asarray(grid.session_id == 1)

    first_armed = np.flatnonzero(armed & session)[0]
    assert clock[first_armed] == 10 * 60, "armed at the bar closing the 09:30-10:00 window"
    # Armed from there to the session's last bar, with no hole in between.
    tail = np.flatnonzero(session)
    tail = tail[tail >= first_armed]
    assert armed[tail].all()
    assert not armed[np.flatnonzero(session)[0] : first_armed].any()


def test_two_windows_in_one_grid_keep_their_own_levels() -> None:
    """The 5-minute range is inside the 30-minute one, so a shared row would still look sane."""
    frame = minute_frame()
    window = in_cash_window(frame)
    inside = np.flatnonzero(window)
    frame.iloc[inside[2], frame.columns.get_loc("high")] = 105.0
    frame.iloc[inside[20], frame.columns.get_loc("high")] = 120.0

    grid = range_grid(frame, [(CASH_OPEN_MINUTES, 5), CASH_WINDOW_30], bar_minutes=1)

    assert grid.high_for((CASH_OPEN_MINUTES, 5))[0] == 105.0
    assert grid.high_for(CASH_WINDOW_30)[0] == 120.0


def test_the_overnight_range_is_the_same_primitive_at_a_different_anchor() -> None:
    frame = minute_frame()
    key = (ETH_OPEN_MINUTES, 60)
    clock = eastern_minutes(frame)
    first_hour = np.asarray((clock > 18 * 60) & (clock <= 19 * 60))
    sessions_of = range_grid(frame, [key], bar_minutes=1).session_id
    frame.iloc[np.flatnonzero(first_hour & (sessions_of == 1))[4], frame.columns.get_loc("high")] = 130.0

    grid = range_grid(frame, [key], bar_minutes=1)
    highs = grid.high_for(key)

    assert highs[1] == 130.0
    # The fixture starts at 19:00 ET, inside session 0's window, so that session has no range
    # to report -- the same rule as a hole, reached from the front of the series.
    assert np.isnan(highs[0])


# -- a session whose window is not all there -----------------------------------


def test_a_session_short_of_window_bars_gets_no_range_and_never_arms() -> None:
    """A partial window measured as if it were whole is a silently narrow range."""
    frame = minute_frame()
    window = in_cash_window(frame)
    session_one = np.asarray(range_grid(frame, [CASH_WINDOW_30], bar_minutes=1).session_id == 1)
    holed = frame.drop(frame.index[np.flatnonzero(window & session_one)[5]])

    grid = range_grid(holed, [CASH_WINDOW_30], bar_minutes=1)

    assert np.isnan(grid.high_for(CASH_WINDOW_30)[1])
    assert np.isnan(grid.low_for(CASH_WINDOW_30)[1])
    assert not grid.armed_for(CASH_WINDOW_30)[grid.session_id == 1].any()
    # Every other session is untouched, so the hole is not a whole-series failure.
    assert np.isfinite(grid.high_for(CASH_WINDOW_30)[0])


def test_a_series_that_never_reaches_the_window_arms_nowhere() -> None:
    frame = minute_frame()
    overnight = np.asarray(eastern_minutes(frame) < 9 * 60)

    grid = range_grid(frame[overnight], [CASH_WINDOW_30], bar_minutes=1)

    assert not grid.armed_for(CASH_WINDOW_30).any()
    assert np.isnan(grid.high_for(CASH_WINDOW_30)).all()


# -- the divisibility rule, which is what decides a resolution axis -------------


def buildable_at(bar_minutes: int, anchor: int = CASH_OPEN_MINUTES, window: int = 30) -> bool:
    """Whether one range is expressible at one bar size."""
    try:
        validate_key(anchor, window, bar_minutes)
    except RangeError:
        return False

    return True


def test_a_cash_anchored_range_needs_a_bar_size_dividing_thirty() -> None:
    """§M28's finding 2, pinned: 60-minute bars cannot express a cash-anchored range at all.

    Two conditions, and the second is the one nobody expects: §M13 needs ``N | 60`` for the
    resample grid to line up with the session, and the 930-minute cash anchor needs ``N |
    930``. Their intersection is ``N | 30``.
    """
    session_aligned = [n for n in range(1, 61) if 60 % n == 0]
    assert buildable_at(60, window=60) is False, "the anchor is what fails, not the window"
    assert [n for n in session_aligned if buildable_at(n)] == [1, 2, 3, 5, 6, 10, 15, 30]
    assert gcd(60, CASH_OPEN_MINUTES) == 30, "the intersection above is this gcd"


def test_the_anchor_alone_admits_bar_sizes_the_session_grid_then_rejects() -> None:
    """31 divides 930 and not 60, so the two conditions are genuinely separate."""
    assert CASH_OPEN_MINUTES % 31 == 0
    assert buildable_at(31, window=31) is True
    assert 60 % 31 != 0, "a 31-minute resample would not align with the session at all"


def test_the_window_must_be_a_whole_number_of_bars() -> None:
    """Read against the overnight anchor, where the anchor condition cannot fire first."""
    assert buildable_at(2, window=30) is True
    with pytest.raises(RangeError, match="whole number of 4-minute bars"):
        validate_key(ETH_OPEN_MINUTES, 30, 4)


def test_an_overnight_anchor_is_expressible_at_every_bar_size() -> None:
    """Anchored at 0, only the window constrains it -- which is why it was deferred, not ruled out."""
    assert all(buildable_at(n, anchor=ETH_OPEN_MINUTES, window=60) for n in (1, 2, 5, 10, 15, 30, 60))


# -- the validator's own boundaries --------------------------------------------


def test_a_range_running_past_the_session_close_is_refused() -> None:
    length = timeofday.session_minutes()
    assert buildable_at(1, anchor=length - 30, window=30) is True
    with pytest.raises(RangeError, match="session close"):
        validate_key(length - 30, 31, 1)


@pytest.mark.parametrize(
    ("anchor", "window", "bar_minutes", "message"),
    [
        (CASH_OPEN_MINUTES, 30, 0, "bar_minutes must be >= 1"),
        (-1, 30, 1, "anchor_minutes must be >= 0"),
        (CASH_OPEN_MINUTES, 0, 1, "window_minutes must be >= 1"),
    ],
)
def test_an_impossible_range_is_refused_by_name(
    anchor: int,
    window: int,
    bar_minutes: int,
    message: str,
) -> None:
    with pytest.raises(RangeError, match=message):
        validate_key(anchor, window, bar_minutes)


def test_building_a_grid_validates_every_key_before_measuring_anything() -> None:
    """Otherwise a 5-minute window on 2-minute bars measures 6 minutes and says 5."""
    with pytest.raises(RangeError, match="whole number"):
        range_grid(minute_frame(), [CASH_WINDOW_30, (CASH_OPEN_MINUTES, 5)], bar_minutes=2)


def test_a_grid_with_no_keys_is_refused() -> None:
    with pytest.raises(RangeError, match="no ranges supplied"):
        range_grid(minute_frame(), [], bar_minutes=1)


# -- the shape, which is what keeps a sweep affordable -------------------------


def test_the_levels_are_stored_per_session_and_the_flag_per_bar() -> None:
    """A per-bar level would be ~16 bytes a bar per window; this is the reason it is not."""
    frame = minute_frame()
    keys = [(CASH_OPEN_MINUTES, 5), (CASH_OPEN_MINUTES, 15), CASH_WINDOW_30]

    grid = range_grid(frame, keys, bar_minutes=1)

    assert grid.high.shape == (3, grid.sessions)
    assert grid.armed.shape == (3, len(frame))
    assert len(grid) == len(frame)
    assert grid.sessions < len(frame) // 100, "the fixture should hold many bars per session"
    assert grid.nbytes / len(frame) < 10.0, "the grid must stay cheap enough to ship to a worker"


def test_the_session_index_maps_every_bar_onto_its_own_range() -> None:
    frame = minute_frame()
    grid = range_grid(frame, [CASH_WINDOW_30], bar_minutes=1)
    days = frame["trading_day"].to_numpy()

    assert grid.session_id[0] == 0
    assert grid.session_id[-1] == grid.sessions - 1
    # One id per trading day, changing exactly where the day does.
    assert (np.diff(grid.session_id) == (days[1:] != days[:-1]).astype(np.int32)).all()


def test_keys_are_sorted_and_deduplicated() -> None:
    grid = range_grid(
        minute_frame(),
        [CASH_WINDOW_30, (CASH_OPEN_MINUTES, 5), CASH_WINDOW_30],
        bar_minutes=1,
    )

    assert grid.keys == ((CASH_OPEN_MINUTES, 5), CASH_WINDOW_30)


def test_reading_a_range_the_grid_was_not_built_for_names_the_ones_it_was() -> None:
    grid = range_grid(minute_frame(), [CASH_WINDOW_30], bar_minutes=1)

    with pytest.raises(KeyError, match=str(CASH_OPEN_MINUTES)):
        grid.armed_for((CASH_OPEN_MINUTES, 15))


def test_a_range_grid_survives_being_built_at_a_coarser_resolution() -> None:
    """The whole point of the divisibility rule: at 5 minutes the window is six bars."""
    from nqbt import resample

    frame = resample.resample(minute_frame(), 5)
    grid = range_grid(frame, [CASH_WINDOW_30], bar_minutes=5)

    assert np.isfinite(grid.high_for(CASH_WINDOW_30)).all()
    assert grid.armed_for(CASH_WINDOW_30).any()


def test_the_module_reports_its_public_names() -> None:
    assert set(sessionrange.__all__) <= set(dir(sessionrange))
