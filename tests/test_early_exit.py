"""The conditional early exit: the rule, the parameters, the context it reads, the loops and the registry.

What carries it is that **an early exit fires where its condition held at a bar close, and
nowhere else**, and leaves at the next bar's open. Each loop is checked against the condition
recomputed straight from the bars -- ``docs/nt8-fidelity.md``, "The conditional early exit".
"""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, regime, sweep, trend
from nqbt.archetypes import Tier2Status
from nqbt.instruments import MNQ
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    DeadCatParams,
    EmaCrossoverParams,
    InsideBarParams,
    InsideBarTrailingParams,
    PullBackAndGoParams,
    active_early_exits,
)
from nqbt.trades import (
    C_BARS_HELD,
    C_DIRECTION,
    C_ENTRY_BAR,
    C_ENTRY_PRICE,
    C_EXIT_BAR,
    C_EXIT_PRICE,
    C_EXIT_REASON,
    C_LEG,
    C_RISK_POINTS,
    C_TRADE_ID,
    EXIT_EARLY,
    EXIT_REASONS,
    EXIT_SIGNAL,
    EXIT_TIME_LIMIT,
    LONG,
    SHORT,
)
from tests.test_confluence_sizing import EVERY_CLASS, LOOPS, TRADING, prepared
from tests.test_insidebartrailing_sim import short_periods, walk_bars

if TYPE_CHECKING:
    from nqbt.arrays import LabelArray
    from nqbt.context import ContextSpec, Dataset

UP = int(trend.Trend.UP)
MIXED = int(trend.Trend.MIXED)
DOWN = int(trend.Trend.DOWN)
DIRECTIONAL = int(regime.Regime.DIRECTIONAL)
CONSOLIDATING = int(regime.Regime.CONSOLIDATING)

EVERY_LOOP: dict[str, tuple[str, archetypes.Params]] = {
    **LOOPS,
    "InsideBarTrailing": ("InsideBarTrailing", short_periods()),
}
"""Every loop the exit reaches, InsideBarTrailing's included."""

RULES: dict[str, dict[str, object]] = {
    "losing at bar 3": {"early_exit_bars": 3},
    "below 0.25R at bar 5": {"early_exit_bars": 5, "early_exit_below_r": 0.25},
    "below -0.1R at bar 2": {"early_exit_bars": 2, "early_exit_below_r": -0.1},
    "losing in the last 600 minutes": {"early_exit_minutes_before_close": 600},
    "regime change": {"early_exit_on_regime_change": True},
    "regime change while losing": {"early_exit_on_regime_change": True, "early_exit_only_if_losing": True},
    "trend opposed": {"early_exit_on_trend": bracket.TREND_EXIT_OPPOSED},
    "trend not with, while losing": {
        "early_exit_on_trend": bracket.TREND_EXIT_NOT_WITH,
        "early_exit_only_if_losing": True,
    },
    "losing 3 minutes in": {"early_exit_minutes": 3},
    "no 0.5R excursion by bar 3": {
        "early_exit_bars": 3,
        "early_exit_measure": bracket.MEASURE_EXCURSION,
        "early_exit_below_r": 0.5,
    },
    "no 1R excursion 2 minutes in": {
        "early_exit_minutes": 2,
        "early_exit_measure": bracket.MEASURE_EXCURSION,
        "early_exit_below_r": 1.0,
    },
    "invalidated": {"early_exit_on_invalidation": True},
    "invalidated while losing": {"early_exit_on_invalidation": True, "early_exit_only_if_losing": True},
}
"""One arm per rule, and the "only if losing" cross on each label rule and the invalidation.

Each setting is one that fires in every loop on :func:`walk_bars`, which is why the window before
the close is wider than a campaign would run it."""


def open_trade(*, entry_bar=5, entry_price=100.0, risk=10.0, direction=LONG) -> bracket.OpenTrade:
    return bracket.OpenTrade(
        trade_id=1,
        entry_bar=entry_bar,
        entry_price=entry_price,
        initial_stop=entry_price - direction * risk,
        risk=risk,
        direction=direction,
        filled_at_open=True,
    )


def rule(**fields: object) -> bracket.EarlyExit:
    return bracket.EARLY_EXIT_OFF._replace(**fields)


def bars_at(close: float, n: int = 64, *, low: float = 0.0, high: float = 1e9) -> bracket.Bars:
    """Build ``n`` bars that all close at ``close``, wide enough that no extreme binds unless set."""
    return bracket.Bars(
        np.full(n, close),
        np.full(n, high),
        np.full(n, low),
        np.full(n, close),
        np.zeros(n, dtype=np.bool_),
    )


def due(
    exit_rule: bracket.EarlyExit,
    trade: bracket.OpenTrade,
    i: int,
    close: float,
    excursion: bracket.Excursion | None = None,
) -> bool:
    """Return :func:`~nqbt.sim.bracket.early_exit_due` on bars closing at ``close``, the excursion the entry's."""
    if excursion is None:
        excursion = bracket.Excursion(trade.entry_price, trade.entry_price)

    return bracket.early_exit_due(exit_rule, trade, bars_at(close), excursion, i)


def reason(
    trade: bracket.OpenTrade, i: int, close: float, max_hold_bars: int, exit_rule: bracket.EarlyExit
) -> float:
    """Return :func:`~nqbt.sim.bracket.market_exit_reason` on bars closing at ``close``."""
    excursion = bracket.Excursion(trade.entry_price, trade.entry_price)

    return bracket.market_exit_reason(trade, bars_at(close), excursion, i, max_hold_bars, exit_rule)


def labels(*values: int) -> np.ndarray:
    return np.asarray(values, dtype=np.int8)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(20_000, seed=5)


# -- the rule ----------------------------------------------------------------------------------


def test_with_every_rule_off_nothing_exits() -> None:
    losing = open_trade()
    assert not any(due(bracket.EARLY_EXIT_OFF, losing, i, 50.0) for i in range(5, 50))


def test_the_not_working_exit_is_tested_at_one_bar_close_only() -> None:
    losing = open_trade(entry_bar=5)
    three_bars = rule(at_bar=3)
    assert [i for i in range(5, 20) if due(three_bars, losing, i, 99.0)] == [8]


def test_a_close_exactly_on_the_threshold_holds_the_position() -> None:
    trade = open_trade(entry_bar=5, entry_price=100.0, risk=10.0)
    assert not due(rule(at_bar=3), trade, 8, 100.0)
    assert due(rule(at_bar=3), trade, 8, 99.75)
    assert not due(rule(at_bar=3, below_r=0.25), trade, 8, 102.5)
    assert due(rule(at_bar=3, below_r=0.25), trade, 8, 102.25)


def test_the_threshold_is_in_r_so_it_moves_with_the_planned_risk() -> None:
    half_r_down = rule(at_bar=2, below_r=-0.5)
    assert not due(half_r_down, open_trade(risk=10.0), 7, 95.0)
    assert due(half_r_down, open_trade(risk=10.0), 7, 94.75)
    assert due(half_r_down, open_trade(risk=4.0), 7, 97.75)


def test_the_short_side_is_the_long_side_through_the_sign() -> None:
    short = open_trade(direction=SHORT)
    assert due(rule(at_bar=3), short, 8, 100.25)
    assert not due(rule(at_bar=3), short, 8, 99.75)
    window = rule(near_close=np.ones(10, dtype=np.bool_))
    assert due(window, short, 6, 100.25)
    assert not due(window, short, 6, 99.75)


def test_only_a_losing_position_leaves_inside_the_window_before_the_close() -> None:
    near = np.zeros(10, dtype=np.bool_)
    near[7:] = True
    window = rule(near_close=near)
    trade = open_trade(entry_bar=2)
    assert not due(window, trade, 6, 90.0), "outside the window"
    assert due(window, trade, 7, 99.75)
    assert not due(window, trade, 7, 100.0), "exactly at the entry is not losing"
    assert not due(window, trade, 7, 100.25)


def test_a_winner_that_turns_into_a_loser_inside_the_window_still_leaves() -> None:
    near = np.zeros(10, dtype=np.bool_)
    near[7:] = True
    window = rule(near_close=near)
    trade = open_trade(entry_bar=2)
    closes = {7: 101.0, 8: 100.5, 9: 99.5}
    assert [i for i, close in closes.items() if due(window, trade, i, close)] == [9]


def test_the_regime_exit_compares_against_the_bar_before_the_entry_bar() -> None:
    #                 0             1             2 = entry-1     3 = entry     4
    series = labels(CONSOLIDATING, CONSOLIDATING, DIRECTIONAL, CONSOLIDATING, DIRECTIONAL)
    change = rule(regime_labels=series)
    trade = open_trade(entry_bar=3)
    assert due(change, trade, 3, 101.0), "the entry bar's own close already differs"
    assert not due(change, trade, 4, 101.0)


def test_an_undefined_regime_label_on_either_side_never_counts_as_a_change() -> None:
    change = rule(regime_labels=labels(regime.UNDEFINED, DIRECTIONAL, regime.UNDEFINED))
    assert not due(change, open_trade(entry_bar=1), 1, 99.0)
    assert not due(change, open_trade(entry_bar=2), 2, 99.0)


def test_only_if_losing_holds_a_winner_through_a_regime_change() -> None:
    series = labels(DIRECTIONAL, CONSOLIDATING)
    trade = open_trade(entry_bar=1)
    assert due(rule(regime_labels=series), trade, 1, 101.0)
    losing_only = rule(only_if_losing=True, regime_labels=series)
    assert not due(losing_only, trade, 1, 101.0)
    assert due(losing_only, trade, 1, 99.0)


@pytest.mark.parametrize(
    ("label", "direction", "form", "against"),
    [
        (DOWN, LONG, bracket.TREND_EXIT_OPPOSED, True),
        (MIXED, LONG, bracket.TREND_EXIT_OPPOSED, False),
        (UP, LONG, bracket.TREND_EXIT_OPPOSED, False),
        (DOWN, LONG, bracket.TREND_EXIT_NOT_WITH, True),
        (MIXED, LONG, bracket.TREND_EXIT_NOT_WITH, True),
        (UP, LONG, bracket.TREND_EXIT_NOT_WITH, False),
        (UP, SHORT, bracket.TREND_EXIT_OPPOSED, True),
        (MIXED, SHORT, bracket.TREND_EXIT_NOT_WITH, True),
        (DOWN, SHORT, bracket.TREND_EXIT_NOT_WITH, False),
        (trend.UNDEFINED, LONG, bracket.TREND_EXIT_NOT_WITH, False),
        (trend.UNDEFINED, SHORT, bracket.TREND_EXIT_NOT_WITH, False),
    ],
)
def test_a_trend_label_is_against_a_position_in_each_form(label, direction, form, against) -> None:
    assert bracket.trend_against(label, direction, form) is against


@pytest.mark.parametrize(
    ("at_entry", "now", "form", "fires"),
    [
        (UP, DOWN, bracket.TREND_EXIT_OPPOSED, True),
        (UP, MIXED, bracket.TREND_EXIT_OPPOSED, False),
        (UP, MIXED, bracket.TREND_EXIT_NOT_WITH, True),
        (MIXED, DOWN, bracket.TREND_EXIT_OPPOSED, True),
        (MIXED, DOWN, bracket.TREND_EXIT_NOT_WITH, False),
        (DOWN, DOWN, bracket.TREND_EXIT_OPPOSED, False),
        (DOWN, MIXED, bracket.TREND_EXIT_NOT_WITH, False),
        (trend.UNDEFINED, DOWN, bracket.TREND_EXIT_OPPOSED, False),
        (UP, trend.UNDEFINED, bracket.TREND_EXIT_NOT_WITH, False),
    ],
)
def test_the_trend_exit_fires_on_a_turn_against_and_leaves_a_trade_entered_against_alone(
    at_entry, now, form, fires
) -> None:
    turn = rule(trend_form=form, trend_labels=labels(at_entry, now))
    assert due(turn, open_trade(entry_bar=1), 1, 99.0) is fires


def test_a_label_exit_on_a_position_entered_on_the_first_bar_has_nothing_to_compare_with() -> None:
    series = labels(DIRECTIONAL, CONSOLIDATING)
    first_bar = open_trade(entry_bar=0)
    assert not due(rule(regime_labels=series), first_bar, 1, 99.0)
    turn = rule(trend_form=bracket.TREND_EXIT_OPPOSED, trend_labels=labels(UP, DOWN))
    assert not due(turn, first_bar, 1, 99.0)


def minute_clock(*minutes: float) -> np.ndarray:
    """Return a clock in epoch seconds whose bars stand at these minutes."""
    return 1_700_000_000.0 + 60.0 * np.asarray(minutes, dtype=np.float64)


def test_the_minutes_form_is_tested_at_the_first_close_that_old_and_no_other() -> None:
    losing = open_trade(entry_bar=1)
    #                           0  1 = entry  2  3  4   5   6
    in_minutes = rule(at_minutes=10.0, clock=minute_clock(0, 5, 10, 15, 20, 25, 30))
    assert [i for i in range(1, 7) if due(in_minutes, losing, i, 99.0)] == [3]


def test_a_gap_in_the_bars_moves_the_minutes_form_to_the_first_close_past_it() -> None:
    losing = open_trade(entry_bar=0)
    gapped = rule(at_minutes=6.0, clock=minute_clock(0, 2, 4, 9, 11))
    assert [i for i in range(5) if due(gapped, losing, i, 99.0)] == [3]


def test_the_minutes_form_means_the_same_time_at_every_bar_size() -> None:
    losing = open_trade(entry_bar=0)
    for bar_minutes, expected_bar in ((1, 30), (2, 15), (5, 6), (10, 3), (15, 2)):
        clock = minute_clock(*range(0, 40 * bar_minutes, bar_minutes))
        thirty = rule(at_minutes=30.0, clock=clock)
        assert [i for i in range(40) if due(thirty, losing, i, 99.0)] == [expected_bar], bar_minutes


def test_the_minutes_form_holds_a_position_above_its_threshold() -> None:
    trade = open_trade(entry_bar=0, entry_price=100.0, risk=10.0)
    in_minutes = rule(at_minutes=10.0, below_r=0.25, clock=minute_clock(0, 5, 10))
    assert not due(in_minutes, trade, 2, 102.5)
    assert due(in_minutes, trade, 2, 102.25)


def test_the_excursion_measure_reads_the_best_price_reached_not_the_close() -> None:
    trade = open_trade(entry_bar=5, entry_price=100.0, risk=10.0)
    half_r = rule(at_bar=3, below_r=0.5, measure=bracket.MEASURE_EXCURSION)
    went_far = bracket.Excursion(run_high=105.0, run_low=90.0)
    stayed_close = bracket.Excursion(run_high=104.75, run_low=99.0)
    assert not due(half_r, trade, 8, 91.0, went_far), "a close far below holds a trade that got 0.5R"
    assert due(half_r, trade, 8, 104.0, stayed_close), "a close in profit still exits one that never got 0.5R"


def test_the_excursion_measure_reads_the_low_on_a_short() -> None:
    short = open_trade(entry_bar=5, entry_price=100.0, risk=10.0, direction=SHORT)
    half_r = rule(at_bar=3, below_r=0.5, measure=bracket.MEASURE_EXCURSION)
    assert not due(half_r, short, 8, 101.0, bracket.Excursion(run_high=110.0, run_low=95.0))
    assert due(half_r, short, 8, 99.0, bracket.Excursion(run_high=101.0, run_low=95.25))


def invalidation_bars(*, signal_low: float, signal_high: float, closes: list[float]) -> bracket.Bars:
    """Build bars whose bar 0 is the signal bar and whose later closes are ``closes``."""
    close = np.asarray([100.0, *closes])
    low = np.full(close.size, 0.0)
    high = np.full(close.size, 1e9)
    low[0], high[0] = signal_low, signal_high

    return bracket.Bars(close.copy(), high, low, close, np.zeros(close.size, dtype=np.bool_))


def test_the_invalidation_exit_fires_on_a_close_strictly_beyond_the_signal_bars_adverse_extreme() -> None:
    long_trade = open_trade(entry_bar=1, entry_price=101.0, risk=4.0)
    bars = invalidation_bars(signal_low=97.0, signal_high=101.0, closes=[98.0, 97.0, 96.75])
    start = bracket.Excursion(101.0, 101.0)
    fired = [
        i
        for i in range(1, 4)
        if bracket.early_exit_due(rule(on_invalidation=True), long_trade, bars, start, i)
    ]
    assert fired == [3], "a close exactly on the extreme is not beyond it"


def test_the_invalidation_exit_reads_the_high_on_a_short() -> None:
    short = open_trade(entry_bar=1, entry_price=97.0, risk=4.0, direction=SHORT)
    bars = invalidation_bars(signal_low=97.0, signal_high=101.0, closes=[101.0, 101.25])
    start = bracket.Excursion(97.0, 97.0)
    fired = [
        i for i in range(1, 3) if bracket.early_exit_due(rule(on_invalidation=True), short, bars, start, i)
    ]
    assert fired == [2]


def test_the_invalidation_exit_has_no_signal_bar_on_the_first_bar() -> None:
    first_bar = open_trade(entry_bar=0)
    assert not due(rule(on_invalidation=True), first_bar, 0, 1.0)


def test_only_if_losing_holds_an_invalidated_winner() -> None:
    # A gapped market entry can fill below the signal bar's low, so the close can be beyond it and up.
    trade = open_trade(entry_bar=1, entry_price=95.0, risk=4.0)
    bars = invalidation_bars(signal_low=97.0, signal_high=101.0, closes=[96.0])
    start = bracket.Excursion(95.0, 95.0)
    assert bracket.early_exit_due(rule(on_invalidation=True), trade, bars, start, 1)
    assert not bracket.early_exit_due(rule(on_invalidation=True, only_if_losing=True), trade, bars, start, 1)


def test_the_hold_cap_takes_a_bar_it_and_the_early_exit_would_both_leave_on() -> None:
    losing = open_trade(entry_bar=5)
    three_bars = rule(at_bar=3)
    assert reason(losing, 8, 99.0, 3, three_bars) == EXIT_TIME_LIMIT
    assert reason(losing, 8, 99.0, 0, three_bars) == EXIT_EARLY
    assert reason(losing, 7, 99.0, 0, three_bars) == bracket.NO_MARKET_EXIT
    assert reason(losing, 7, 99.0, 0, bracket.EARLY_EXIT_OFF) == bracket.NO_MARKET_EXIT


def test_no_exit_code_is_the_no_exit_sentinel() -> None:
    assert bracket.NO_MARKET_EXIT not in EXIT_REASONS


# -- the parameters ----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_every_rule_is_off_by_default_on_every_class(cls) -> None:
    assert active_early_exits(cls()) == []


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"early_exit_bars": -1}, "early_exit_bars must be >= 0"),
        ({"early_exit_below_r": math.nan}, "early_exit_below_r must be finite"),
        ({"early_exit_below_r": math.inf}, "early_exit_below_r must be finite"),
        ({"early_exit_minutes_before_close": -5}, "early_exit_minutes_before_close must be >= 0"),
        ({"early_exit_on_trend": 3}, "early_exit_on_trend must be one of"),
        (
            {"early_exit_bars": 3, "early_exit_minutes_before_close": 30},
            "at most one early exit may be on",
        ),
        (
            {"early_exit_on_regime_change": True, "early_exit_on_trend": bracket.TREND_EXIT_OPPOSED},
            "early_exit_on_regime_change, early_exit_on_trend",
        ),
        ({"early_exit_minutes": -1}, "early_exit_minutes must be >= 0"),
        ({"early_exit_measure": 2}, "early_exit_measure must be one of"),
        (
            {"early_exit_bars": 3, "early_exit_minutes": 30},
            "early_exit_bars, early_exit_minutes",
        ),
        (
            {"early_exit_on_invalidation": True, "early_exit_minutes_before_close": 30},
            "early_exit_minutes_before_close, early_exit_on_invalidation",
        ),
        ({"early_exit_below_r": 0.5}, "both 0, so the not-working exit that reads it is off"),
        (
            {"early_exit_measure": bracket.MEASURE_EXCURSION},
            "early_exit_measure set but early_exit_bars and early_exit_minutes are both 0",
        ),
        (
            {"early_exit_on_invalidation": True, "early_exit_measure": bracket.MEASURE_EXCURSION},
            "early_exit_measure set but",
        ),
        ({"early_exit_only_if_losing": True}, "none of the regime, trend or invalidation exits is on"),
        (
            {"early_exit_minutes_before_close": 30, "early_exit_only_if_losing": True},
            "none of the regime, trend or invalidation exits is on",
        ),
        (
            {"early_exit_minutes": 30, "early_exit_only_if_losing": True},
            "none of the regime, trend or invalidation exits is on",
        ),
        ({"max_hold_bars": 3, "early_exit_bars": 3}, "can never fire under max_hold_bars of 3"),
        ({"max_hold_bars": 3, "early_exit_bars": 5}, "can never fire under max_hold_bars of 3"),
    ],
)
def test_an_exit_that_is_out_of_range_unread_unreachable_or_a_second_rule_is_refused(
    cls, fields, message
) -> None:
    with pytest.raises(ValueError, match=message):
        cls(**fields)


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_one_rule_with_its_own_settings_is_accepted_on_every_class(cls) -> None:
    for fields in RULES.values():
        assert len(active_early_exits(cls(**fields))) == 1


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_a_not_working_bar_before_the_hold_cap_is_accepted(cls) -> None:
    assert cls(max_hold_bars=4, early_exit_bars=3).early_exit_bars == 3
    assert cls(max_hold_bars=0, early_exit_bars=30).early_exit_bars == 30


# -- the context it reads ----------------------------------------------------------------------


def test_with_every_rule_off_the_exit_carries_no_series(bars) -> None:
    params = TRADING["DeadCatBounce"]
    built = filters.early_exit(prepared(bars, params, archetypes.DEADCATBOUNCE), params)
    off = bracket.EARLY_EXIT_OFF
    series = (built.near_close, built.regime_labels, built.trend_labels, built.clock)
    assert all(s.size == 0 for s in series)
    scalars = (
        "at_bar",
        "at_minutes",
        "below_r",
        "measure",
        "trend_form",
        "only_if_losing",
        "on_invalidation",
    )
    assert [getattr(built, name) for name in scalars] == [getattr(off, name) for name in scalars]


def test_the_minutes_form_reads_the_bars_own_timestamps(bars) -> None:
    params = dataclasses.replace(TRADING["DeadCatBounce"], early_exit_minutes=30)
    data = prepared(bars, params, archetypes.DEADCATBOUNCE)
    built = filters.early_exit(data, params)
    assert built.at_minutes == 30.0
    assert built.at_bar == 0
    assert np.array_equal(np.diff(built.clock), np.full(len(data) - 1, 60.0))
    assert built.clock[0] == data.index[0].timestamp()


def test_the_dataset_clock_is_utc_seconds_whatever_unit_the_index_is_stored_in() -> None:
    for unit in ("s", "us", "ns"):
        index = pd.DatetimeIndex(["2024-03-10 06:55", "2024-03-10 07:00"], tz="UTC").as_unit(unit)
        frame = pd.DataFrame({"close": [1.0, 2.0]}, index=index.tz_convert("America/New_York"))
        data = context.Dataset(
            bars=frame,
            open=frame["close"].to_numpy(),
            high=frame["close"].to_numpy(),
            low=frame["close"].to_numpy(),
            close=frame["close"].to_numpy(),
            force_flat=np.zeros(2, dtype=np.bool_),
            geometry=None,
            spec=context.ContextSpec(),
        )
        assert data.bar_seconds().tolist() == [1710053700.0, 1710054000.0], unit
        assert data.bar_seconds() is data.bar_seconds()
        assert not data.bar_seconds().flags.writeable


def test_the_window_before_the_close_is_the_no_entry_windows_at_the_same_minutes(bars) -> None:
    params = dataclasses.replace(TRADING["DeadCatBounce"], early_exit_minutes_before_close=45)
    data = prepared(bars, params, archetypes.DEADCATBOUNCE)
    built = filters.early_exit(data, params)
    assert np.array_equal(built.near_close, ~data.session_end_gate(45))
    assert built.near_close.any()
    assert not built.near_close.all()


def test_the_label_exits_read_the_labels_at_the_combinations_own_settings(bars) -> None:
    base = TRADING["DeadCatBounce"]
    on_regime = dataclasses.replace(base, early_exit_on_regime_change=True, regime_lookback=12)
    data = prepared(bars, on_regime, archetypes.DEADCATBOUNCE)
    expected = data.regime_labels(
        12, on_regime.regime_consolidating_below, on_regime.regime_directional_above
    )
    assert np.array_equal(filters.early_exit(data, on_regime).regime_labels, expected)

    on_trend = dataclasses.replace(
        base, early_exit_on_trend=bracket.TREND_EXIT_OPPOSED, trend_min_agreement=2
    )
    data = prepared(bars, on_trend, archetypes.DEADCATBOUNCE)
    expected = data.trend_labels(on_trend.trend_key, 2)
    assert np.array_equal(filters.early_exit(data, on_trend).trend_labels, expected)


# -- the loops ---------------------------------------------------------------------------------


def losing_by(close: float, trade: np.ndarray) -> float:
    """Return the open profit per contract at ``close``, which is negative while the position loses."""
    return trade[C_DIRECTION] * (close - trade[C_ENTRY_PRICE])


def rule_labels(params: filters.EarlyExiting, data: Dataset) -> LabelArray | None:
    """Return the label series ``params``' exit reads, or ``None`` for a rule that reads none."""
    if params.early_exit_on_regime_change:
        return data.regime_labels(
            params.regime_lookback, params.regime_consolidating_below, params.regime_directional_above
        )

    if params.early_exit_on_trend != bracket.TREND_EXIT_OFF:
        return data.trend_labels(params.trend_key, params.trend_min_agreement)

    return None


def reached(params, data: Dataset, entry_bar: int, bar: int) -> bool:
    """Recompute whether ``bar`` is the one close the not-working exit tests, from the bar count or the index."""
    if params.early_exit_bars > 0:
        return bar - entry_bar == params.early_exit_bars

    elapsed = (data.index - data.index[entry_bar]).total_seconds()
    horizon = params.early_exit_minutes * 60

    return elapsed[bar] >= horizon > elapsed[bar - 1]


def measured(params, data: Dataset, trade: np.ndarray, bar: int) -> float:
    """Recompute what the not-working exit compares with its threshold: open profit, or the best excursion."""
    if params.early_exit_measure == bracket.MEASURE_OPEN_PROFIT:
        return losing_by(data.close[bar], trade)

    entry_bar = int(trade[C_ENTRY_BAR])
    if trade[C_DIRECTION] == LONG:
        return float(data.high[entry_bar : bar + 1].max() - trade[C_ENTRY_PRICE])

    return float(trade[C_ENTRY_PRICE] - data.low[entry_bar : bar + 1].min())


def condition_held(params, data, series: LabelArray | None, trade: np.ndarray, risk: float, bar: int) -> bool:
    """Recompute from the bars whether ``params``' rule held at ``bar``'s close for ``trade``.

    ``series`` is :func:`rule_labels` for the same ``params``.
    """
    profit = losing_by(data.close[bar], trade)
    entry_bar = int(trade[C_ENTRY_BAR])
    if params.early_exit_bars > 0 or params.early_exit_minutes > 0:
        return reached(params, data, entry_bar, bar) and measured(params, data, trade, bar) < (
            params.early_exit_below_r * risk
        )

    if params.early_exit_minutes_before_close > 0:
        return profit < 0 and data.seconds_to_session_end[bar] <= params.early_exit_minutes_before_close * 60

    before = entry_bar - 1
    if before < 0 or (params.early_exit_only_if_losing and profit >= 0):
        return False

    if params.early_exit_on_invalidation:
        adverse = data.low[before] if trade[C_DIRECTION] == LONG else data.high[before]
        return trade[C_DIRECTION] * (data.close[bar] - adverse) < 0

    assert series is not None, "a label rule reads rule_labels' series"
    if params.early_exit_on_regime_change:
        return regime.UNDEFINED not in (series[before], series[bar]) and series[bar] != series[before]

    if trend.UNDEFINED in (series[before], series[bar]):
        return False

    def against(label) -> bool:
        lean = trade[C_DIRECTION] * (int(label) - MIXED)

        return lean < 0 if params.early_exit_on_trend == bracket.TREND_EXIT_OPPOSED else lean <= 0

    return against(series[bar]) and not against(series[before])


@pytest.mark.parametrize("rule_name", sorted(RULES))
@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_every_loop_exits_where_the_rule_held_and_nowhere_else(bars, loop, rule_name) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    params = dataclasses.replace(base, **RULES[rule_name])
    data = prepared(bars, params, archetype)
    series: LabelArray | None = rule_labels(params, data)
    legs = archetype.legs(data, params, MNQ)
    matrix = legs.matrix[: legs.count]
    fired = 0
    for trade_id in np.unique(matrix[:, C_TRADE_ID]):
        rows = matrix[matrix[:, C_TRADE_ID] == trade_id]
        first = rows[0]
        # InsideBarTrailing's two lots carry their own risks; R is the bracketed lot's.
        risk = rows[rows[:, C_LEG] == 1][0, C_RISK_POINTS]
        last_exit = int(rows[:, C_EXIT_BAR].max())
        reasons = set(rows[:, C_EXIT_REASON])
        # A market exit decided at the close before fills at this open; InsideBarTrailing's
        # trend violation instead leaves at a stop fill, on the bar it was decided.
        at_open = bool(reasons & {EXIT_EARLY, EXIT_TIME_LIMIT}) or (
            EXIT_SIGNAL in reasons and name != "InsideBarTrailing"
        )
        for bar in range(int(first[C_ENTRY_BAR]), last_exit - 1 if at_open else last_exit):
            assert not condition_held(params, data, series, first, risk, bar), (
                f"trade {trade_id:.0f} missed bar {bar}"
            )

        early = rows[rows[:, C_EXIT_REASON] == EXIT_EARLY]
        if not len(early):
            continue

        fired += 1
        exit_bar = int(early[0, C_EXIT_BAR])
        assert condition_held(params, data, series, first, risk, exit_bar - 1)
        assert (early[:, C_EXIT_BAR] == last_exit).all(), "every leg left together"
        assert np.allclose(early[:, C_EXIT_PRICE], data.open[exit_bar])

    assert fired > 0, "the rule never fired, so the test proves nothing"


@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_a_rule_that_never_fires_leaves_every_trade_as_it_was(bars, loop) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    never = dataclasses.replace(base, early_exit_bars=2, early_exit_below_r=-1e9)
    data = prepared(bars, never, archetype)
    off = archetype.legs(data, base, MNQ)
    on = archetype.legs(data, never, MNQ)
    assert off.count > 10
    assert np.array_equal(off.matrix[: off.count], on.matrix[: on.count], equal_nan=True)


@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_the_hold_cap_takes_a_bar_both_would_exit_on(bars, loop) -> None:
    """Every close is inside the window, so a trade first losing at the hold limit is a tie."""
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    both = dataclasses.replace(base, max_hold_bars=3, early_exit_minutes_before_close=10**6)
    data = prepared(bars, both, archetype)
    legs = archetype.legs(data, both, MNQ)
    matrix = legs.matrix[: legs.count]
    at_the_limit = matrix[matrix[:, C_BARS_HELD] == 4, C_EXIT_REASON]
    assert (at_the_limit == EXIT_TIME_LIMIT).any(), "the hold cap never fired, so nothing was tied"
    assert (at_the_limit != EXIT_EARLY).all()
    assert (matrix[:, C_EXIT_REASON] == EXIT_EARLY).any()


def test_the_archetypes_own_signal_exit_takes_a_bar_both_would_exit_on(bars) -> None:
    base = TRADING["EmaCrossover"]
    always = dataclasses.replace(base, early_exit_bars=2, early_exit_below_r=1e9)
    data = prepared(bars, always, archetypes.EMACROSSOVER)
    legs = archetypes.EMACROSSOVER.legs(data, always, MNQ)
    matrix = legs.matrix[: legs.count]
    at_the_limit = matrix[matrix[:, C_BARS_HELD] == 3]
    assert (at_the_limit[:, C_EXIT_REASON] == EXIT_EARLY).any()
    assert (at_the_limit[:, C_EXIT_REASON] == EXIT_SIGNAL).any(), (
        "an opposite cross at the limit keeps its reason"
    )


@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_slippage_worsens_the_early_exits_fill_on_either_side(bars, loop) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    slipped = dataclasses.replace(base, early_exit_bars=2, early_exit_below_r=1e9, slippage_ticks=2.0)
    data = prepared(bars, slipped, archetype)
    legs = archetype.legs(data, slipped, MNQ)
    early = legs.matrix[: legs.count][legs.matrix[: legs.count, C_EXIT_REASON] == EXIT_EARLY]
    exit_bar = early[:, C_EXIT_BAR].astype(int)
    assert len(early) > 0
    assert np.allclose(
        early[:, C_EXIT_PRICE], data.open[exit_bar] - early[:, C_DIRECTION] * 2 * MNQ.tick_size
    )


# -- the registry and the sweep ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_threshold_axis_is_dead_without_the_not_working_exit(name) -> None:
    archetype = archetypes.get(name)
    with pytest.raises(
        sweep.SweepError,
        match=r"early_exit_below_r \(inert while early_exit_bars is 0 and early_exit_minutes is 0\)",
    ):
        sweep.Grid.of(TRADING[name], archetype=archetype, early_exit_below_r=[0.0, 0.25])

    at_three = dataclasses.replace(TRADING[name], early_exit_bars=3)
    assert len(sweep.Grid.of(at_three, archetype=archetype, early_exit_below_r=[0.0, 0.25])) == 2
    in_minutes = dataclasses.replace(TRADING[name], early_exit_minutes=30)
    assert len(sweep.Grid.of(in_minutes, archetype=archetype, early_exit_below_r=[0.0, 0.25])) == 2


@pytest.mark.parametrize("name", sorted(TRADING))
def test_only_if_losing_is_dead_without_a_label_exit(name) -> None:
    archetype = archetypes.get(name)
    with pytest.raises(sweep.SweepError, match=r"early_exit_only_if_losing"):
        sweep.Grid.of(TRADING[name], archetype=archetype, early_exit_only_if_losing=[False, True])

    on_trend = dataclasses.replace(TRADING[name], early_exit_on_trend=bracket.TREND_EXIT_OPPOSED)
    assert len(sweep.Grid.of(on_trend, archetype=archetype, early_exit_only_if_losing=[False, True])) == 2


@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_labels_axes_are_live_when_an_exit_reads_them(name) -> None:
    archetype = archetypes.get(name)
    on_regime = dataclasses.replace(TRADING[name], early_exit_on_regime_change=True)
    sweep.Grid.of(on_regime, archetype=archetype, regime_lookback=[10, 20])
    on_trend = dataclasses.replace(TRADING[name], early_exit_on_trend=bracket.TREND_EXIT_NOT_WITH)
    sweep.Grid.of(on_trend, archetype=archetype, trend_min_agreement=[2, 3])


def test_a_window_shorter_than_a_minute_still_builds_the_clock_it_reads(bars) -> None:
    params = dataclasses.replace(TRADING["DeadCatBounce"], early_exit_minutes_before_close=0.5)
    spec = sweep.Grid.of(params, archetype=archetypes.DEADCATBOUNCE).required_context()
    assert spec.needs_session_clock
    data = prepared(bars, params, archetypes.DEADCATBOUNCE)
    assert archetypes.DEADCATBOUNCE.legs(data, params, MNQ).count > 0


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_series_an_exit_reads_is_built_into_the_dataset(name) -> None:
    archetype = archetypes.get(name)
    off = sweep.Grid.of(TRADING[name], archetype=archetype).required_context()
    assert not off.regime_lookbacks
    assert not off.trend_keys
    assert not off.needs_session_clock

    def spec(**fields: object) -> ContextSpec:
        return sweep.Grid.of(
            dataclasses.replace(TRADING[name], **fields), archetype=archetype
        ).required_context()

    assert spec(early_exit_on_regime_change=True).regime_lookbacks
    assert spec(early_exit_on_trend=bracket.TREND_EXIT_OPPOSED).trend_keys
    assert spec(early_exit_minutes_before_close=30).needs_session_clock


def test_a_grid_refuses_two_rules_at_once_before_anything_runs() -> None:
    on_bars = DeadCatParams(early_exit_bars=3)
    with pytest.raises(sweep.SweepError, match=r"cannot be built, so none runs: .*at most one early exit"):
        sweep.Grid.of(on_bars, early_exit_minutes_before_close=[0, 30])


@pytest.mark.parametrize(
    ("archetype", "params"),
    [
        (archetypes.DEADCATBOUNCE, DeadCatParams()),
        (archetypes.PULLBACKANDGO, PullBackAndGoParams()),
        (archetypes.INSIDEBAR, InsideBarParams()),
        (archetypes.INSIDEBARTRAILING, InsideBarTrailingParams()),
    ],
)
@pytest.mark.parametrize("rule_name", sorted(RULES))
def test_an_early_exit_row_leaves_every_reconciled_port(archetype, params, rule_name) -> None:
    assert archetype.tier2_for(params) is Tier2Status.RECONCILED
    assert archetype.tier2_for(dataclasses.replace(params, **RULES[rule_name])) is Tier2Status.TIER1_ONLY


def test_an_original_archetype_stays_tier_1_only_with_an_early_exit_or_not() -> None:
    params = EmaCrossoverParams()
    assert archetypes.EMACROSSOVER.tier2_for(params) is Tier2Status.TIER1_ONLY
    assert archetypes.EMACROSSOVER.tier2_for(EmaCrossoverParams(early_exit_bars=3)) is Tier2Status.TIER1_ONLY
