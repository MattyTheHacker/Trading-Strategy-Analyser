"""Session classification tests.

Timestamps below are drawn from the real MNQ 03-24 export, which straddles the
2024-03-10 DST transition and so exercises both offsets.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import sessions


def idx(*stamps: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(stamps), utc=True))


def test_friday_close_bar_is_the_last_bar_of_fridays_session() -> None:
    # 22:00 UTC in winter is 17:00 EST -- the bar covering 16:59-17:00, so still in.
    info = sessions.classify(idx("2024-03-08 22:00:00"))
    assert info.eastern[0].strftime("%H:%M") == "17:00"
    assert info.in_session[0]
    assert info.trading_day[0] == np.datetime64("2024-03-08")
    assert info.is_session_close[0]


def test_sunday_reopen_belongs_to_mondays_trading_day() -> None:
    # 22:01 UTC on 2024-03-10 is 18:01 EDT: DST has begun, so the offset is -4.
    info = sessions.classify(idx("2024-03-10 22:01:00"))
    assert info.eastern[0].strftime("%H:%M") == "18:01"
    assert info.in_session[0]
    assert info.trading_day[0] == np.datetime64("2024-03-11")
    assert info.is_session_open[0]


def test_dst_shifts_the_utc_offset_within_one_contract() -> None:
    winter, summer = sessions.classify(idx("2024-01-15 22:00:00", "2024-07-15 21:00:00")).eastern
    assert winter.utcoffset().total_seconds() == -5 * 3600
    assert summer.utcoffset().total_seconds() == -4 * 3600
    assert winter.strftime("%H:%M") == summer.strftime("%H:%M") == "17:00"


@pytest.mark.parametrize(
    ("stamp", "why"),
    [
        ("2024-03-09 15:44:00", "Saturday morning print"),
        ("2024-03-09 21:14:00", "Saturday afternoon print"),
        ("2024-03-10 00:43:00", "Saturday evening print"),
        ("2024-03-10 20:34:00", "Sunday before the 18:00 reopen"),
    ],
)
def test_stray_weekend_prints_are_out_of_session(stamp, why) -> None:
    # These exist in the real exports with volume 1. NT8 building bars against an ETH
    # template would never form them, so neither do we.
    info = sessions.classify(idx(stamp))
    assert not info.in_session[0], why


def test_maintenance_break_is_out_of_session() -> None:
    # 17:00-18:00 ET daily. 22:30 UTC in winter is 17:30 EST.
    info = sessions.classify(idx("2024-01-16 22:30:00"))
    assert info.eastern[0].strftime("%H:%M") == "17:30"
    assert not info.in_session[0]


def test_session_edges_mark_first_and_last_in_session_bars_only() -> None:
    # Monday session: two bars, then the break, then Tuesday's session opens.
    info = sessions.classify(
        idx(
            "2024-01-15 23:01:00",  # Mon 18:01 ET -> Tuesday's session opens
            "2024-01-16 23:00:00",  # 18:00 ET Tue -> break, excluded
            "2024-01-16 22:00:00",  # Tue 17:00 ET -> Tuesday's session closes
            "2024-01-16 23:01:00",  # Tue 18:01 ET -> Wednesday's session opens
        ),
    )
    # classify sorts nothing; the caller supplies ascending order, so re-sort here.
    order = np.argsort(info.eastern.values)
    in_session = info.in_session[order]
    is_open = info.is_session_open[order]
    is_close = info.is_session_close[order]

    assert list(in_session) == [True, True, False, True]
    assert list(is_open) == [True, False, False, True]
    assert list(is_close) == [False, True, False, True]


def test_force_flat_triggers_on_the_final_bar_not_the_one_before() -> None:
    # ExitOnSessionCloseSeconds=30 puts the cutoff at 16:59:30 ET. The bar stamped
    # 16:59:00 ends before it; the bar stamped 17:00:00 reaches it.
    info = sessions.classify(idx("2024-01-16 21:59:00", "2024-01-16 22:00:00"))
    assert [t.strftime("%H:%M") for t in info.eastern] == ["16:59", "17:00"]
    mask = sessions.force_flat_mask(info, exit_on_close_seconds=30)
    assert list(mask) == [False, True]


def test_force_flat_cutoff_is_configurable() -> None:
    info = sessions.classify(idx("2024-01-16 21:59:00", "2024-01-16 22:00:00"))
    mask = sessions.force_flat_mask(info, exit_on_close_seconds=90)
    assert list(mask) == [True, True]


def test_seconds_to_session_end_counts_down_to_the_sessions_last_bar() -> None:
    info = sessions.classify(idx("2024-01-16 20:00:00", "2024-01-16 21:59:00", "2024-01-16 22:00:00"))
    assert [t.strftime("%H:%M") for t in info.eastern] == ["15:00", "16:59", "17:00"]
    assert list(sessions.seconds_to_session_end(info)) == [7200.0, 60.0, 0.0]


def test_a_holiday_early_close_flattens_on_its_own_last_bar() -> None:
    """MLK 2024: CME stops at 13:00 ET, four hours before the template says it should."""
    info = sessions.classify(
        idx(
            "2024-01-15 17:59:00",  # Mon 12:59 ET, the holiday
            "2024-01-15 18:00:00",  # Mon 13:00 ET, the exchange's early close
            "2024-01-15 23:01:00",  # Mon 18:01 ET -> Tuesday's session opens
            "2024-01-16 22:00:00",  # Tue 17:00 ET, a full-length close
        ),
    )
    assert [t.strftime("%m-%d %H:%M") for t in info.eastern] == [
        "01-15 12:59",
        "01-15 13:00",
        "01-15 18:01",
        "01-16 17:00",
    ]
    assert list(info.is_session_close) == [False, True, False, True]

    # Both halves: the holiday's last bar is four hours from the template's fixed close, and
    # the countdown reaches zero on it anyway. Measured against the template it never would.
    eastern = info.eastern.tz_localize(None)
    seconds_past_midnight = eastern[1].hour * 3600 + eastern[1].minute * 60
    assert 17 * 3600 - seconds_past_midnight == 4 * 3600
    assert list(sessions.seconds_to_session_end(info)) == [60.0, 0.0, 82740.0, 0.0]
    assert list(sessions.force_flat_mask(info)) == [False, True, False, True]


def test_a_session_truncated_by_a_data_hole_still_flattens() -> None:
    """A missing tail is indistinguishable from an early close, and both have to flatten.

    There are no later bars in that session to close the position in.
    """
    info = sessions.classify(idx("2024-01-16 21:41:00", "2024-01-16 21:42:00"))
    assert [t.strftime("%H:%M") for t in info.eastern] == ["16:41", "16:42"]
    assert list(sessions.force_flat_mask(info)) == [False, True]


def test_a_day_with_no_in_session_bar_falls_back_to_the_template_close() -> None:
    """A weekend stray has no observed session end, so there is nothing to derive one from."""
    info = sessions.classify(idx("2024-03-09 15:44:00"))
    assert not info.in_session[0]
    assert not info.is_session_close[0]
    assert list(sessions.seconds_to_session_end(info)) == [(17 - 10) * 3600 - 44 * 60]
    assert list(sessions.force_flat_mask(info)) == [False]


def test_the_force_flat_mask_is_that_countdown_cut_at_the_exit_seconds() -> None:
    """One definition of the session end, so a no-entry window cannot drift from the flatten."""
    info = sessions.classify(idx("2024-01-16 21:58:00", "2024-01-16 21:59:00", "2024-01-16 22:00:00"))
    remaining = sessions.seconds_to_session_end(info)
    for seconds in (30, 90, 120):
        expected = info.in_session & (remaining <= seconds)
        assert list(sessions.force_flat_mask(info, exit_on_close_seconds=seconds)) == list(expected)


def test_classify_handles_an_empty_index() -> None:
    info = sessions.classify(pd.DatetimeIndex([], tz="UTC"))
    assert len(info) == 0
    assert info.in_session.size == 0


def test_naive_index_is_treated_as_utc() -> None:
    naive = pd.DatetimeIndex(["2024-03-08 22:00:00"])
    aware = idx("2024-03-08 22:00:00")
    assert sessions.classify(naive).eastern[0] == sessions.classify(aware).eastern[0]
