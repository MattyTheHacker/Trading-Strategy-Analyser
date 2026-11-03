"""FailedBreak simulation tests on hand-built bars.

The archetype has no NinjaScript and no trade list. These pin what it introduces: a sweep read as a
state over closes, levels fixed at the signal bar, a stop beyond the sweep's extreme, an exit on the
re-break, a random-entry arm that carries each signal's distances, and that nothing it reads comes
from a bar it could not have seen.

Bars are 30 minutes. The first two of a session close the first-hour range, which is 90 to 110
unless a test says otherwise.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, randomentry, sessionrange, sessions, sweep, timeofday
from nqbt.instruments import MNQ, NQ
from nqbt.sim.failedbreak import (
    NO_SIGNAL,
    failedbreak_legs,
    failedbreak_long_side,
    failedbreak_signal,
    first_per_session,
    geometry_of,
    level_series,
    run_failedbreak,
    scan_recoveries,
)
from nqbt.sim.types import (
    FB_LEVEL_FIRST_HOUR,
    FB_LEVEL_OVERNIGHT,
    FB_LEVEL_YESTERDAY,
    FB_RANGE_KEYS,
    FB_TARGET_MID_OPPOSITE,
    FB_TARGET_OPPOSITE_NEXT,
    FB_TARGET_R,
    FailedBreakParams,
)
from nqbt.trades import (
    C_ENTRY_BAR,
    C_ENTRY_PRICE,
    C_EXIT_BAR,
    C_EXIT_PRICE,
    C_EXIT_REASON,
    C_GROSS_PNL,
    C_INITIAL_STOP,
    C_LEG,
    C_QUANTITY,
    C_RISK_POINTS,
    C_TARGET_PRICE,
    EXIT_EARLY,
    EXIT_END_OF_DATA,
    EXIT_SESSION_CLOSE,
    EXIT_SIGNAL,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME_LIMIT,
    LONG,
    SHORT,
)
from tools import campaign_sweep

if TYPE_CHECKING:
    from collections.abc import Sequence

    from nqbt.arrays import BoolArray, FloatArray

type Row = tuple[float, float, float, float]
"""One bar as open, high, low, close."""

TICK = MNQ.tick_size
BAR_MINUTES = 30

HAND_BUILT = FailedBreakParams(bars_required_to_trade=0, stop_offset_ticks=4)
"""The first-hour level, a one-point cushion and no warm-up, so every price below reads by eye."""

FIRST_HOUR: list[Row] = [(100.0, 110.0, 95.0, 100.0), (100.0, 105.0, 90.0, 100.0)]
"""The two bars that close the 90 to 110 range."""

QUIET: Row = (100.0, 101.0, 99.0, 100.0)
"""A bar inside the range that reaches nothing."""

SWEEP: Row = (100.0, 101.0, 88.0, 95.0)
"""A bar that trades through the low of 90 and closes back inside: the signal, extreme 88."""


def frame_of(
    sessions_of_rows: Sequence[Sequence[Row]], contracts: Sequence[str] | None = None
) -> pd.DataFrame:
    """Build 30-minute bars from 10:00 ET on consecutive weekdays, one list of rows per session."""
    days = pd.bdate_range("2024-01-02", periods=len(sessions_of_rows))
    stamps: list[pd.Timestamp] = []
    rows: list[Row] = []
    labels: list[str] = []
    for position, (day, session_rows) in enumerate(zip(days, sessions_of_rows, strict=True)):
        first = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=15)
        stamps += [first + pd.Timedelta(minutes=BAR_MINUTES * k) for k in range(len(session_rows))]
        rows += list(session_rows)
        labels += [contracts[position] if contracts else ""] * len(session_rows)

    arr = np.asarray(rows, dtype=np.float64)
    index = pd.DatetimeIndex(stamps)
    frame = pd.DataFrame(
        {"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3], "volume": 100.0},
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    if contracts:
        frame["contract"] = labels

    return frame


def dataset_for(
    params: FailedBreakParams,
    frame: pd.DataFrame,
    price_basis: context.PriceBasis = context.PriceBasis.UNKNOWN,
) -> context.Dataset:
    """Build a dataset carrying exactly what one combination reads."""
    return context.prepare(
        frame,
        sweep.Grid.of(params).required_context(),
        bar_minutes=BAR_MINUTES,
        price_basis=price_basis,
    )


def legs_of(rows: Sequence[Row], params: FailedBreakParams = HAND_BUILT) -> FloatArray:
    """Simulate one session of hand-written rows after the first hour, with padding before the close."""
    frame = frame_of([[*FIRST_HOUR, *rows, QUIET, QUIET]])
    legs = failedbreak_legs(dataset_for(params, frame), params)

    return legs.matrix[: legs.count]


def scan(
    rows: Sequence[Row],
    level: float = 90.0,
    *,
    direction: float = LONG,
    max_minutes: float = 60.0,
    armed: Sequence[bool] | None = None,
    session_id: Sequence[int] | None = None,
) -> tuple[BoolArray, FloatArray]:
    """Scan hand-written rows, one bar a minute, against one level per session."""
    arr = np.asarray(rows, dtype=np.float64)
    n = len(arr)
    ids = np.zeros(n, dtype=np.int32) if session_id is None else np.asarray(session_id, dtype=np.int32)

    return scan_recoveries(
        arr[:, 2],
        arr[:, 1],
        arr[:, 3],
        np.arange(n, dtype=np.float64) * 60.0,
        np.ones(n, dtype=np.bool_) if armed is None else np.asarray(armed, dtype=np.bool_),
        ids,
        np.full(int(ids.max()) + 1, level, dtype=np.float64),
        direction,
        max_minutes * 60.0,
    )


# -- the sweep and the recovery ------------------------------------------------------


def test_a_bar_that_sweeps_and_recovers_by_itself_fires_with_its_own_low_as_the_extreme() -> None:
    fired, extremes = scan([QUIET, SWEEP])

    assert fired.tolist() == [False, True]
    assert extremes[1] == 88.0


def test_a_sweep_over_several_bars_fires_on_the_close_back_with_the_lowest_low() -> None:
    fired, extremes = scan(
        [QUIET, (95.0, 96.0, 87.0, 89.0), (89.0, 89.5, 85.0, 88.0), (88.0, 95.0, 87.0, 94.0)]
    )

    assert fired.tolist() == [False, False, False, True]
    assert extremes[3] == 85.0


def test_a_low_exactly_on_the_level_is_not_through_it() -> None:
    fired, _ = scan([QUIET, (100.0, 101.0, 90.0, 95.0)])

    assert not fired.any()


def test_a_close_exactly_on_the_level_is_not_back_inside() -> None:
    fired, _ = scan([QUIET, (100.0, 101.0, 88.0, 90.0), (90.0, 90.5, 89.0, 90.0), (90.0, 92.0, 89.5, 91.0)])

    assert fired.tolist() == [False, False, False, True]


def test_a_session_already_below_the_level_has_not_swept_it() -> None:
    """A gap through the level is not a sweep, so its first close back inside fires nothing."""
    gapped: Row = (85.0, 92.0, 84.0, 91.0)
    fired, _ = scan([gapped, QUIET, SWEEP])

    assert fired.tolist() == [False, False, True]


def test_a_bar_closed_outside_after_the_level_arms_is_not_inside_yet() -> None:
    below: Row = (85.0, 89.0, 84.0, 86.0)
    fired, _ = scan([below, below])

    assert not fired.any()


def test_the_age_cap_counts_from_the_bar_that_started_the_sweep_and_includes_its_limit() -> None:
    rows = [QUIET, (95.0, 96.0, 87.0, 89.0), (89.0, 89.5, 88.0, 89.0), (89.0, 95.0, 88.0, 94.0)]

    assert scan(rows, max_minutes=2.0)[0][3]
    assert not scan(rows, max_minutes=1.0)[0].any()


def test_at_an_age_cap_of_zero_only_the_same_bar_fires() -> None:
    late = [QUIET, (95.0, 96.0, 87.0, 89.0), (89.0, 95.0, 88.0, 94.0)]

    assert scan([QUIET, SWEEP], max_minutes=0.0)[0][1]
    assert not scan(late, max_minutes=0.0)[0].any()


def test_a_recovery_past_the_cap_still_ends_the_sweep_so_the_next_one_can_fire() -> None:
    rows = [
        QUIET,
        (95.0, 96.0, 87.0, 89.0),
        (89.0, 89.5, 88.0, 89.0),
        (89.0, 95.0, 88.0, 94.0),
        SWEEP,
    ]

    assert scan(rows, max_minutes=1.0)[0].tolist() == [False, False, False, False, True]


def test_the_short_side_is_the_mirror() -> None:
    fired, extremes = scan([QUIET, (100.0, 112.0, 99.0, 105.0)], level=110.0, direction=SHORT)

    assert fired.tolist() == [False, True]
    assert extremes[1] == 112.0


def test_a_sweep_does_not_carry_into_the_next_session() -> None:
    rows = [QUIET, (95.0, 96.0, 87.0, 89.0), (89.0, 95.0, 88.0, 94.0)]

    assert not scan(rows, session_id=[0, 0, 1])[0].any()


def test_an_unarmed_bar_is_not_read_at_all() -> None:
    assert not scan([QUIET, SWEEP], armed=[True, False])[0].any()


# -- the levels ----------------------------------------------------------------------


def test_yesterday_is_the_previous_session_s_cash_range_read_from_the_first_bar() -> None:
    cash = [(100.0, 120.0, 80.0, 100.0)] + [QUIET] * 12
    frame = frame_of([cash, [QUIET] * 13])
    params = replace(HAND_BUILT, level=FB_LEVEL_YESTERDAY)
    series = level_series(dataset_for(params, frame), FB_LEVEL_YESTERDAY)

    assert np.isnan(series.low[0])
    assert (series.low[1], series.high[1]) == (80.0, 120.0)
    assert series.armed.tolist() == [False] * 13 + [True] * 13


def test_yesterday_is_not_read_across_a_contract_roll() -> None:
    cash = [(100.0, 120.0, 80.0, 100.0)] + [QUIET] * 12
    frame = frame_of([cash, cash, cash], contracts=["A", "B", "B"])
    params = replace(HAND_BUILT, level=FB_LEVEL_YESTERDAY)
    series = level_series(dataset_for(params, frame), FB_LEVEL_YESTERDAY)

    assert np.isnan(series.low[:2]).all()
    assert series.low[2] == 80.0


def test_a_previous_session_short_of_its_cash_window_leaves_no_level() -> None:
    frame = frame_of([[QUIET] * 7, [QUIET] * 13])
    params = replace(HAND_BUILT, level=FB_LEVEL_YESTERDAY)
    series = level_series(dataset_for(params, frame), FB_LEVEL_YESTERDAY)

    assert not series.armed.any()


def test_a_single_contract_frame_has_no_rolls() -> None:
    frame = frame_of([[QUIET] * 13, [QUIET] * 13])
    params = replace(HAND_BUILT, level=FB_LEVEL_YESTERDAY)

    assert not dataset_for(params, frame).range_new_contract().any()


def test_previous_session_blanks_the_first_session_and_each_new_contract() -> None:
    levels = np.array([1.0, 2.0, 3.0, 4.0])
    new_contract = np.array([False, False, True, False])

    assert np.array_equal(
        sessionrange.previous_session(levels, new_contract),
        np.array([np.nan, 1.0, np.nan, 3.0]),
        equal_nan=True,
    )


def test_the_overnight_range_is_read_once_its_window_has_closed() -> None:
    bars_overnight = sessionrange.CASH_OPEN_MINUTES // BAR_MINUTES
    index = pd.date_range("2024-01-02 23:30", periods=bars_overnight + 2, freq="30min", tz="UTC")
    low = np.full(index.size, 99.0)
    low[3] = 80.0
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": low, "close": 100.0, "volume": 100.0},
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    params = replace(HAND_BUILT, level=FB_LEVEL_OVERNIGHT)
    series = level_series(dataset_for(params, frame), FB_LEVEL_OVERNIGHT)

    assert series.low[0] == 80.0
    assert series.armed.tolist() == [False] * (bars_overnight - 1) + [True] * 3


# -- the entry and the bracket -------------------------------------------------------


def test_the_entry_is_the_next_open_with_the_stop_a_cushion_beyond_the_extreme() -> None:
    rows = legs_of([SWEEP, (96.0, 97.0, 94.0, 96.0)])

    assert (rows[:, C_ENTRY_BAR] == 3).all()
    assert (rows[:, C_ENTRY_PRICE] == 96.0).all()
    assert (rows[:, C_INITIAL_STOP] == 88.0 - 4 * TICK).all()
    assert (rows[:, C_RISK_POINTS] == 96.0 - (88.0 - 4 * TICK)).all()


def test_the_first_target_is_the_opposite_edge_and_the_second_the_next_level_past_it() -> None:
    yesterday = [(100.0, 130.0, 70.0, 100.0)] + [QUIET] * 12
    today = [*FIRST_HOUR, SWEEP, (96.0, 111.0, 94.0, 96.0), QUIET, QUIET]
    legs = failedbreak_legs(dataset_for(HAND_BUILT, frame_of([yesterday, today])), HAND_BUILT)
    rows = legs.matrix[: legs.count]

    assert rows[rows[:, C_LEG] == 1][0, C_TARGET_PRICE] == 110.0
    assert rows[rows[:, C_LEG] == 1][0, C_EXIT_REASON] == EXIT_TARGET
    assert rows[rows[:, C_LEG] == 2][0, C_TARGET_PRICE] == 130.0


def test_with_no_next_level_the_second_leg_has_no_target() -> None:
    rows = legs_of([SWEEP, (96.0, 111.0, 94.0, 96.0)])
    second = rows[rows[:, C_LEG] == 2][0]

    assert np.isnan(second[C_TARGET_PRICE])
    assert second[C_EXIT_REASON] == EXIT_SESSION_CLOSE


def test_a_level_not_yet_readable_at_the_signal_bar_is_not_a_next_level() -> None:
    """Yesterday's high is past the first target, and a range closing later would be nearer."""
    params = replace(HAND_BUILT, level=FB_LEVEL_YESTERDAY)
    yesterday = [(100.0, 130.0, 70.0, 100.0)] + [QUIET] * 12
    today = [QUIET, (100.0, 101.0, 68.0, 95.0), QUIET, QUIET]
    legs = failedbreak_legs(dataset_for(params, frame_of([yesterday, today])), params)
    rows = legs.matrix[: legs.count]

    assert rows[0, C_TARGET_PRICE] == 130.0
    assert np.isnan(rows[rows[:, C_LEG] == 2][0, C_TARGET_PRICE])


def test_the_midpoint_scheme_targets_the_middle_then_the_opposite_edge() -> None:
    params = replace(HAND_BUILT, target_mode=FB_TARGET_MID_OPPOSITE)
    rows = legs_of([SWEEP, (96.0, 97.0, 94.0, 96.0)], params)

    assert rows[rows[:, C_LEG] == 1][0, C_TARGET_PRICE] == 100.0
    assert rows[rows[:, C_LEG] == 2][0, C_TARGET_PRICE] == 110.0


def test_the_r_scheme_measures_its_ladder_from_the_fill() -> None:
    params = replace(HAND_BUILT, target_mode=FB_TARGET_R, target_r_multiples=(1.0, float("nan")))
    rows = legs_of([SWEEP, (96.0, 97.0, 94.0, 96.0)], params)
    risk = 96.0 - (88.0 - 4 * TICK)

    assert rows[rows[:, C_LEG] == 1][0, C_TARGET_PRICE] == 96.0 + risk
    assert np.isnan(rows[rows[:, C_LEG] == 2][0, C_TARGET_PRICE])


def test_a_midpoint_on_a_half_tick_is_snapped_to_the_grid() -> None:
    wide: list[Row] = [(100.0, 110.25, 95.0, 100.0), (100.0, 105.0, 90.0, 100.0)]
    params = replace(HAND_BUILT, target_mode=FB_TARGET_MID_OPPOSITE)
    frame = frame_of([[*wide, SWEEP, (96.0, 97.0, 94.0, 96.0), QUIET, QUIET]])
    legs = failedbreak_legs(dataset_for(params, frame), params)
    target = legs.matrix[: legs.count][0, C_TARGET_PRICE]

    assert target % TICK == 0.0


def test_a_close_at_or_past_the_first_target_is_refused_under_a_level_scheme_and_not_under_r() -> None:
    through: Row = (100.0, 112.0, 88.0, 111.0)
    frame = frame_of([[*FIRST_HOUR, through, QUIET, QUIET]])
    under_r = replace(HAND_BUILT, target_mode=FB_TARGET_R)

    assert not failedbreak_signal(dataset_for(HAND_BUILT, frame), HAND_BUILT).any()
    assert failedbreak_signal(dataset_for(under_r, frame), under_r).sum() == 1


def test_a_stop_at_or_through_the_next_open_is_refused() -> None:
    gapped: Row = (87.0, 96.0, 86.0, 95.0)

    assert len(legs_of([SWEEP, gapped])) == 0


def test_the_stop_is_moved_off_a_round_number_on_raw_prices() -> None:
    params = replace(HAND_BUILT, round_number_points=50.0, round_number_offset_ticks=8, stop_offset_ticks=8)
    frame = frame_of([[*FIRST_HOUR, (100.0, 101.0, 52.0, 95.0), (96.0, 97.0, 94.0, 96.0), QUIET, QUIET]])
    legs = failedbreak_legs(dataset_for(params, frame, context.PriceBasis.RAW), params)

    assert legs.matrix[0, C_INITIAL_STOP] == 50.0 - 8 * TICK


def test_round_number_avoidance_is_refused_on_bars_not_declared_raw() -> None:
    params = replace(HAND_BUILT, round_number_points=50.0)
    frame = frame_of([[*FIRST_HOUR, SWEEP, QUIET, QUIET]])

    with pytest.raises(ValueError, match="round_number_points"):
        failedbreak_legs(dataset_for(params, frame), params)


def test_the_short_side_mirrors_the_long_side_price_for_price() -> None:
    def flipped(row: Row) -> Row:
        return (200.0 - row[0], 200.0 - row[2], 200.0 - row[1], 200.0 - row[3])

    rows = [SWEEP, (96.0, 97.0, 94.0, 96.0), (96.0, 111.0, 95.0, 96.0)]
    longs = legs_of(rows)
    frame = frame_of([[flipped(r) for r in [*FIRST_HOUR, *rows, QUIET, QUIET]]])
    params = replace(HAND_BUILT, direction=SHORT)
    legs = failedbreak_legs(dataset_for(params, frame), params)
    shorts = legs.matrix[: legs.count]

    assert np.array_equal(shorts[:, C_ENTRY_PRICE], 200.0 - longs[:, C_ENTRY_PRICE])
    assert np.array_equal(shorts[:, C_EXIT_PRICE], 200.0 - longs[:, C_EXIT_PRICE])
    assert np.array_equal(shorts[:, C_GROSS_PNL], longs[:, C_GROSS_PNL])


def test_gross_pnl_is_exactly_ten_times_on_nq_with_the_same_geometry() -> None:
    frame = frame_of([[*FIRST_HOUR, SWEEP, (96.0, 111.0, 94.0, 96.0), QUIET, QUIET]])
    data = dataset_for(HAND_BUILT, frame)
    micro = failedbreak_legs(data, HAND_BUILT, MNQ)
    full = failedbreak_legs(data, HAND_BUILT, NQ)

    assert np.array_equal(micro.matrix[:, C_ENTRY_PRICE], full.matrix[:, C_ENTRY_PRICE])
    assert np.allclose(full.matrix[:, C_GROSS_PNL], micro.matrix[:, C_GROSS_PNL] * 10.0)


# -- the exit on the re-break --------------------------------------------------------


def test_a_close_back_beyond_the_level_exits_at_the_next_open() -> None:
    rows = legs_of([SWEEP, (96.0, 97.0, 88.5, 89.0), (89.5, 92.0, 89.0, 90.0)])

    assert (rows[:, C_EXIT_REASON] == EXIT_SIGNAL).all()
    assert (rows[:, C_EXIT_BAR] == 4).all()
    assert (rows[:, C_EXIT_PRICE] == 89.5).all()


def test_a_close_exactly_on_the_level_does_not_exit() -> None:
    rows = legs_of([SWEEP, (96.0, 97.0, 88.5, 90.0), QUIET])

    assert (rows[:, C_EXIT_REASON] == EXIT_SESSION_CLOSE).all()


def test_a_wick_through_the_level_does_not_exit() -> None:
    rows = legs_of([SWEEP, (96.0, 97.0, 88.5, 96.0), QUIET])

    assert not (rows[:, C_EXIT_REASON] == EXIT_SIGNAL).any()


def test_with_the_exit_off_the_stop_takes_the_trade_instead() -> None:
    params = replace(HAND_BUILT, exit_on_rebreak=False)
    rows = legs_of([SWEEP, (96.0, 97.0, 88.5, 89.0), (89.0, 89.5, 80.0, 85.0)], params)

    assert (rows[:, C_EXIT_REASON] == EXIT_STOP).all()
    assert (rows[:, C_EXIT_PRICE] == 88.0 - 4 * TICK).all()


def test_the_re_break_takes_a_bar_the_hold_cap_also_wants() -> None:
    params = replace(HAND_BUILT, max_hold_bars=1)
    alone = legs_of([SWEEP, (96.0, 97.0, 95.0, 96.0), QUIET, QUIET], params)
    both = legs_of([SWEEP, (96.0, 97.0, 95.0, 96.0), (96.0, 97.0, 88.5, 89.0), QUIET], params)

    assert (alone[:, C_EXIT_REASON] == EXIT_TIME_LIMIT).all()
    assert (both[:, C_EXIT_REASON] == EXIT_SIGNAL).all()


def test_the_re_break_takes_a_bar_an_early_exit_also_wants() -> None:
    params = replace(HAND_BUILT, early_exit_bars=1, early_exit_below_r=0.5)
    alone = legs_of([SWEEP, (96.0, 97.0, 95.0, 96.0), QUIET, QUIET], params)
    both = legs_of([SWEEP, (96.0, 97.0, 95.0, 96.0), (96.0, 97.0, 88.5, 89.0), QUIET], params)

    assert (alone[:, C_EXIT_REASON] == EXIT_EARLY).all()
    assert (both[:, C_EXIT_REASON] == EXIT_SIGNAL).all()


def test_the_breakeven_stop_moves_the_stop_to_the_entry() -> None:
    params = replace(HAND_BUILT, breakeven_at=0.5)
    rows = legs_of([SWEEP, (96.0, 102.0, 95.0, 101.5), (101.0, 101.5, 94.0, 95.0)], params)

    assert (rows[:, C_EXIT_REASON] == EXIT_STOP).all()
    assert (rows[:, C_EXIT_PRICE] == 96.0).all()


def test_the_age_stop_moves_the_stop_to_the_entry() -> None:
    params = replace(HAND_BUILT, age_stop_bars=1)
    held: Row = (96.5, 97.0, 96.25, 96.5)
    rows = legs_of([SWEEP, (96.0, 97.0, 95.5, 96.5), held, (96.5, 97.0, 94.0, 95.0)], params)

    assert (rows[:, C_EXIT_REASON] == EXIT_STOP).all()
    assert (rows[:, C_EXIT_PRICE] == 96.0).all()


def test_slippage_moves_the_market_entry_and_the_market_exit_against_the_trade() -> None:
    params = replace(HAND_BUILT, slippage_ticks=2.0)
    rows = legs_of([SWEEP, (96.0, 97.0, 88.5, 89.0), (89.5, 92.0, 89.0, 90.0)], params)

    assert (rows[:, C_ENTRY_PRICE] == 96.0 + 2 * TICK).all()
    assert (rows[:, C_EXIT_PRICE] == 89.5 - 2 * TICK).all()


def test_a_signal_on_the_session_s_last_bar_is_blocked() -> None:
    frame = frame_of([[*FIRST_HOUR, QUIET, SWEEP]])
    legs = failedbreak_legs(dataset_for(HAND_BUILT, frame), HAND_BUILT)

    assert failedbreak_signal(dataset_for(HAND_BUILT, frame), HAND_BUILT).sum() == 1
    assert legs.count == 0


def test_a_position_still_open_when_the_series_runs_out_is_liquidated_at_the_last_close() -> None:
    frame = frame_of([[*FIRST_HOUR, SWEEP, (96.0, 97.0, 95.0, 96.5), (96.5, 97.0, 95.0, 96.5)]])
    data = dataset_for(HAND_BUILT, frame)
    never_flat = replace(data, force_flat=np.zeros(len(data), dtype=np.bool_))
    legs = failedbreak_legs(never_flat, HAND_BUILT)
    rows = legs.matrix[: legs.count]

    assert (rows[:, C_EXIT_REASON] == EXIT_END_OF_DATA).all()
    assert (rows[:, C_EXIT_PRICE] == 96.5).all()


def test_a_signal_on_the_bar_a_position_is_open_submits_nothing() -> None:
    """Still in the position at that close, so a second market entry would be ignored."""
    params = replace(HAND_BUILT, max_signals_per_session=0, exit_on_rebreak=False)
    rows = legs_of([SWEEP, QUIET, SWEEP, QUIET], params)

    assert set(rows[:, C_ENTRY_BAR]) == {3.0}


# -- the signal cap, which counts signals and not fills ------------------------------


def test_the_cap_keeps_each_session_s_first_signals() -> None:
    signal = np.array([True, True, False, True, True])
    session_id = np.array([0, 0, 0, 1, 1])

    assert first_per_session(signal, session_id, 1).tolist() == [True, False, False, True, False]
    assert first_per_session(signal, session_id, 2).tolist() == signal.tolist()
    assert first_per_session(signal, session_id, 0).tolist() == signal.tolist()


def test_the_cap_copes_with_no_signals_at_all() -> None:
    assert not first_per_session(np.zeros(3, dtype=np.bool_), np.zeros(3, dtype=np.int32), 1).any()


def test_a_session_takes_one_signal_by_default_and_every_one_uncapped() -> None:
    frame = frame_of([[*FIRST_HOUR, SWEEP, QUIET, SWEEP, QUIET, QUIET]])
    uncapped = replace(HAND_BUILT, max_signals_per_session=0)

    assert np.flatnonzero(failedbreak_signal(dataset_for(HAND_BUILT, frame), HAND_BUILT)).tolist() == [2]
    assert np.flatnonzero(failedbreak_signal(dataset_for(uncapped, frame), uncapped)).tolist() == [2, 4]


def test_the_cap_counts_what_the_filters_admit() -> None:
    """The first signal the filter admits is the session's first, whatever came before it."""
    rows: list[Row] = [*FIRST_HOUR, SWEEP, *[QUIET] * 6, SWEEP, QUIET, QUIET]
    frame = frame_of([rows])
    afternoon = replace(HAND_BUILT, phase_filter=timeofday.SessionPhase.AFTERNOON.bit)

    assert np.flatnonzero(failedbreak_signal(dataset_for(afternoon, frame), afternoon)).tolist() == [9]


# -- nothing from the future ---------------------------------------------------------


def test_nothing_after_a_bar_changes_whether_it_signals() -> None:
    rng = np.random.default_rng(3)
    frame = walk_frame(rng, sessions_count=12)
    data = dataset_for(HAND_BUILT, frame)
    whole = failedbreak_signal(data, HAND_BUILT)
    cut = len(frame) // 2
    early = failedbreak_signal(dataset_for(HAND_BUILT, frame.iloc[:cut]), HAND_BUILT)

    assert np.array_equal(whole[:cut], early)


def test_a_signal_s_prices_do_not_change_with_the_bars_after_it() -> None:
    params = replace(HAND_BUILT, max_signals_per_session=0)
    rng = np.random.default_rng(4)
    frame = walk_frame(rng, sessions_count=12)
    cut = len(frame) // 2
    whole = geometry_of(dataset_for(params, frame), params, None)
    early = geometry_of(dataset_for(params, frame.iloc[:cut]), params, None)
    rows = np.flatnonzero(early.row_of_bar != NO_SIGNAL).size

    assert rows > 0
    assert np.array_equal(whole.extreme[:rows], early.extreme, equal_nan=True)
    assert np.array_equal(whole.level[:rows], early.level, equal_nan=True)


# -- the random-entry arm ------------------------------------------------------------


def walk_frame(rng: np.random.Generator, sessions_count: int = 80) -> pd.DataFrame:
    """Build a random walk on the tick grid, thirteen bars a session."""
    rows: list[list[Row]] = []
    price = 1000.0
    for _ in range(sessions_count):
        session: list[Row] = []
        for _ in range(13):
            step = float(rng.integers(-40, 41)) * TICK
            close = price + step
            wick_up = float(rng.integers(0, 12)) * TICK
            wick_down = float(rng.integers(0, 12)) * TICK
            session.append((price, max(price, close) + wick_up, min(price, close) - wick_down, close))
            price = close

        rows.append(session)

    return frame_of(rows)


def whole_session_walk(rng: np.random.Generator, sessions_count: int = 30) -> pd.DataFrame:
    """Build a random walk from 18:30 to 17:00 ET, so every range closes on these 30-minute bars."""
    bars_per_session = 45
    closes = 1000.0 + np.cumsum(rng.integers(-40, 41, sessions_count * bars_per_session) * TICK)
    opens = np.concatenate(([1000.0], closes[:-1]))
    wicks = rng.integers(0, 12, (2, closes.size)) * TICK
    days = pd.bdate_range("2024-01-02", periods=sessions_count)
    stamps = [
        pd.Timestamp(day, tz="UTC") - pd.Timedelta(minutes=30) + pd.Timedelta(minutes=BAR_MINUTES * k)
        for day in days
        for k in range(bars_per_session)
    ]
    index = pd.DatetimeIndex(stamps)
    frame = pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + wicks[0],
            "low": np.minimum(opens, closes) - wicks[1],
            "close": closes,
            "volume": 100.0,
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


def test_a_signal_drawn_whole_reproduces_the_real_trades_exactly() -> None:
    params = replace(HAND_BUILT, max_signals_per_session=0)
    data = dataset_for(params, walk_frame(np.random.default_rng(1)))
    real = failedbreak_legs(data, params)
    drawn = failedbreak_legs(data, params, signal=failedbreak_signal(data, params))

    assert real.count > 0
    assert np.array_equal(real.matrix[: real.count], drawn.matrix[: drawn.count], equal_nan=True)


def test_a_drawn_bar_carries_its_signal_s_distances_from_its_own_close() -> None:
    day_one = [*FIRST_HOUR, SWEEP, QUIET, QUIET, QUIET]
    higher: Row = (200.0, 201.0, 199.0, 200.0)
    day_two = [(200.0, 210.0, 195.0, 200.0), (200.0, 205.0, 190.0, 200.0), higher, higher, higher, higher]
    data = dataset_for(HAND_BUILT, frame_of([day_one, day_two]))
    real = failedbreak_signal(data, HAND_BUILT)
    drawn = np.roll(real, 6)
    assert np.flatnonzero(real).tolist() == [2]
    assert np.flatnonzero(drawn).tolist() == [8]

    geometry = geometry_of(data, HAND_BUILT, drawn)
    shift = data.close[8] - data.close[2]

    assert geometry.row_of_bar[8] == 0
    assert geometry.extreme[0] == 88.0 + shift
    assert geometry.level[0] == 90.0 + shift
    assert geometry.targets[0, 0] == 110.0 + shift


def test_every_drawn_bar_trades_where_the_real_signal_would_have() -> None:
    """The point of carrying the geometry: left alone, a drawn bar has no sweep and is declined."""
    params = replace(HAND_BUILT, bars_required_to_trade=0)
    data = dataset_for(params, walk_frame(np.random.default_rng(2)))
    real = failedbreak_signal(data, params)
    drawn = randomentry.matched_random_signal(data, real, np.random.default_rng(9))
    legs = failedbreak_legs(data, params, signal=drawn)
    trades_taken = np.unique(legs.matrix[: legs.count, C_ENTRY_BAR]).size

    assert real.sum() > 10
    assert trades_taken >= real.sum() * 0.5


def test_a_mask_inside_the_real_signal_trades_those_bars_at_their_own_prices() -> None:
    params = replace(HAND_BUILT, max_signals_per_session=0)
    data = dataset_for(params, walk_frame(np.random.default_rng(1)))
    real = failedbreak_signal(data, params)
    kept = real.copy()
    kept[: np.flatnonzero(real)[real.sum() // 2]] = False

    whole = geometry_of(data, params, None)
    inside = geometry_of(data, params, kept)
    bars = np.flatnonzero(kept)

    assert bars.size > 0
    assert np.array_equal(inside.extreme, whole.extreme[whole.row_of_bar[bars]])
    assert np.array_equal(inside.level, whole.level[whole.row_of_bar[bars]])


def test_a_signal_not_matched_minute_by_minute_is_refused() -> None:
    data = dataset_for(HAND_BUILT, walk_frame(np.random.default_rng(2)))
    real = failedbreak_signal(data, HAND_BUILT)
    wrong = np.zeros_like(real)
    wrong[np.flatnonzero(real)[0] + 1] = True

    with pytest.raises(ValueError, match="minute of session"):
        failedbreak_legs(data, HAND_BUILT, signal=wrong)


@pytest.mark.parametrize("level", [FB_LEVEL_FIRST_HOUR, FB_LEVEL_YESTERDAY])
def test_the_bar_draw_has_room_on_a_real_shape_of_signal(level: int) -> None:
    params = replace(HAND_BUILT, level=level)
    data = dataset_for(params, walk_frame(np.random.default_rng(5)))
    signal = failedbreak_signal(data, params)
    pool = randomentry.SessionMinutePool.build(data.index)

    assert pool.draw_freedom(signal) >= randomentry.MIN_DRAW_FREEDOM


@pytest.mark.parametrize("draw", [randomentry.OVER_LEVELS, randomentry.OVER_KINDS])
@pytest.mark.parametrize("level", [FB_LEVEL_FIRST_HOUR, FB_LEVEL_YESTERDAY])
def test_a_level_draw_reruns_the_whole_rule_against_another_level(level: int, draw: str) -> None:
    params = replace(HAND_BUILT, level=level)
    data = dataset_for(params, walk_frame(np.random.default_rng(6)))
    summaries = randomentry.null_summaries(data, params, iterations=4, seed=1, draw=draw)
    observed = failedbreak_legs(data, params)

    assert len(summaries) == 4
    assert observed.count > 0
    assert np.unique(summaries["trades"].to_numpy()).size > 1


def test_a_level_draw_moves_its_own_range_and_leaves_the_others_alone() -> None:
    data = dataset_for(HAND_BUILT, walk_frame(np.random.default_rng(7)))
    key = FB_RANGE_KEYS[FB_LEVEL_FIRST_HOUR]
    other = FB_RANGE_KEYS[FB_LEVEL_YESTERDAY]
    drawn = randomentry.matched_random_placements(data, key, np.random.default_rng(1), TICK)

    assert not np.array_equal(drawn.low_for(key), data.range_low(key), equal_nan=True)
    assert np.array_equal(drawn.low_for(other), data.range_low(other), equal_nan=True)
    assert np.array_equal(drawn.new_contract, data.range_new_contract())


# -- the parameters and the registry -------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("level", 9, "unknown level"),
        ("direction", 0.0, "direction"),
        ("max_sweep_minutes", -1, "max_sweep_minutes"),
        ("max_signals_per_session", -1, "max_signals_per_session"),
        ("target_mode", 9, "unknown target_mode"),
        ("order_quantity", 1, "order_quantity"),
        ("stop_offset_ticks", 0, "stop_offset_ticks"),
        ("round_number_points", -1.0, "round_number_points"),
        ("round_number_offset_ticks", -1, "round_number_offset_ticks"),
        ("tp_multiplier", 2.0, "tp_multiplier"),
    ],
)
def test_a_parameter_nothing_can_read_is_refused(field: str, value: float, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(FailedBreakParams(), **{field: value})  # type: ignore[arg-type]  # one bad value per case


@pytest.mark.parametrize("ladder", [(), (-1.0,), (0.0,)])
def test_an_r_ladder_that_is_empty_or_not_above_zero_is_refused(ladder: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="target_r_multiples"):
        FailedBreakParams(target_mode=FB_TARGET_R, target_r_multiples=ladder)


def test_the_multiplier_is_read_under_the_r_scheme() -> None:
    assert FailedBreakParams(target_mode=FB_TARGET_R, tp_multiplier=2.0).tp_multiplier == 2.0


def test_the_legs_follow_the_target_scheme() -> None:
    assert FailedBreakParams().leg_quantities == (2, 2)
    assert FailedBreakParams(target_mode=FB_TARGET_MID_OPPOSITE).minimum_quantity == 2
    assert FailedBreakParams(target_mode=FB_TARGET_R).leg_quantities == (1, 1, 1, 1)


def test_the_context_builds_one_range_or_all_three_under_the_next_level_target() -> None:
    build = archetypes.failedbreak_context
    nearer = {"level": [FB_LEVEL_OVERNIGHT], "target_mode": [FB_TARGET_R]}
    further = {"level": [FB_LEVEL_OVERNIGHT], "target_mode": [FB_TARGET_OPPOSITE_NEXT]}

    assert build(nearer).range_keys == (FB_RANGE_KEYS[FB_LEVEL_OVERNIGHT],)
    assert set(build(further).range_keys) == set(FB_RANGE_KEYS.values())


def test_a_campaign_variant_runs_through_the_sweep_with_every_axis_live() -> None:
    bars = whole_session_walk(np.random.default_rng(8))
    for variant in campaign_sweep.VARIANTS["FailedBreak"]("MNQ"):
        grid = sweep.Grid(axes=variant.axes, base=variant.base, archetype=variant.archetype)
        spec = grid.required_context()
        data = context.prepare(bars, spec, bar_minutes=BAR_MINUTES, price_basis=context.PriceBasis.RAW)
        results, _ = sweep.sweep(bars, grid, MNQ, data=data)

        assert grid.dead_axes() == {}, variant.name
        assert len(results) == len(grid), variant.name
        assert results["trades"].sum() > 0, variant.name
        assert "target_r_multiples" not in results.columns, "a tuple is not a swept axis"


def test_the_side_is_the_parameter_s_on_every_bar() -> None:
    data = dataset_for(HAND_BUILT, frame_of([[*FIRST_HOUR, QUIET]]))

    assert failedbreak_long_side(data, HAND_BUILT).all()
    assert not failedbreak_long_side(data, replace(HAND_BUILT, direction=SHORT)).any()


def test_the_trade_log_runs_through_the_shared_validator() -> None:
    frame = frame_of([[*FIRST_HOUR, SWEEP, (96.0, 111.0, 94.0, 96.0), QUIET, QUIET]])
    log = run_failedbreak(dataset_for(HAND_BUILT, frame), HAND_BUILT)

    assert len(log) == 2
    assert log["quantity"].sum() == HAND_BUILT.order_quantity


def test_the_split_gives_each_leg_its_share_of_the_order() -> None:
    rows = legs_of([SWEEP, (96.0, 111.0, 94.0, 96.0)])

    assert rows[:, C_QUANTITY].tolist() == [2.0, 2.0]
