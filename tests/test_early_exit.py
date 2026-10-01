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
import pytest

from nqbt import archetypes, regime, sweep, trend
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
    import pandas as pd

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
}
"""One arm per tier-1 rule, and the "only if losing" cross on each label rule.

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


def labels(*values: int) -> np.ndarray:
    return np.asarray(values, dtype=np.int8)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(20_000, seed=5)


# -- the rule ----------------------------------------------------------------------------------


def test_with_every_rule_off_nothing_exits() -> None:
    losing = open_trade()
    assert not any(bracket.early_exit_due(bracket.EARLY_EXIT_OFF, losing, i, 50.0) for i in range(5, 50))


def test_the_not_working_exit_is_tested_at_one_bar_close_only() -> None:
    losing = open_trade(entry_bar=5)
    three_bars = rule(at_bar=3)
    assert [i for i in range(5, 20) if bracket.early_exit_due(three_bars, losing, i, 99.0)] == [8]


def test_a_close_exactly_on_the_threshold_holds_the_position() -> None:
    trade = open_trade(entry_bar=5, entry_price=100.0, risk=10.0)
    assert not bracket.early_exit_due(rule(at_bar=3), trade, 8, 100.0)
    assert bracket.early_exit_due(rule(at_bar=3), trade, 8, 99.75)
    assert not bracket.early_exit_due(rule(at_bar=3, below_r=0.25), trade, 8, 102.5)
    assert bracket.early_exit_due(rule(at_bar=3, below_r=0.25), trade, 8, 102.25)


def test_the_threshold_is_in_r_so_it_moves_with_the_planned_risk() -> None:
    half_r_down = rule(at_bar=2, below_r=-0.5)
    assert not bracket.early_exit_due(half_r_down, open_trade(risk=10.0), 7, 95.0)
    assert bracket.early_exit_due(half_r_down, open_trade(risk=10.0), 7, 94.75)
    assert bracket.early_exit_due(half_r_down, open_trade(risk=4.0), 7, 97.75)


def test_the_short_side_is_the_long_side_through_the_sign() -> None:
    short = open_trade(direction=SHORT)
    assert bracket.early_exit_due(rule(at_bar=3), short, 8, 100.25)
    assert not bracket.early_exit_due(rule(at_bar=3), short, 8, 99.75)
    window = rule(near_close=np.ones(10, dtype=np.bool_))
    assert bracket.early_exit_due(window, short, 6, 100.25)
    assert not bracket.early_exit_due(window, short, 6, 99.75)


def test_only_a_losing_position_leaves_inside_the_window_before_the_close() -> None:
    near = np.zeros(10, dtype=np.bool_)
    near[7:] = True
    window = rule(near_close=near)
    trade = open_trade(entry_bar=2)
    assert not bracket.early_exit_due(window, trade, 6, 90.0), "outside the window"
    assert bracket.early_exit_due(window, trade, 7, 99.75)
    assert not bracket.early_exit_due(window, trade, 7, 100.0), "exactly at the entry is not losing"
    assert not bracket.early_exit_due(window, trade, 7, 100.25)


def test_a_winner_that_turns_into_a_loser_inside_the_window_still_leaves() -> None:
    near = np.zeros(10, dtype=np.bool_)
    near[7:] = True
    window = rule(near_close=near)
    trade = open_trade(entry_bar=2)
    closes = {7: 101.0, 8: 100.5, 9: 99.5}
    assert [i for i, close in closes.items() if bracket.early_exit_due(window, trade, i, close)] == [9]


def test_the_regime_exit_compares_against_the_bar_before_the_entry_bar() -> None:
    #                 0             1             2 = entry-1     3 = entry     4
    series = labels(CONSOLIDATING, CONSOLIDATING, DIRECTIONAL, CONSOLIDATING, DIRECTIONAL)
    change = rule(regime_labels=series)
    trade = open_trade(entry_bar=3)
    assert bracket.early_exit_due(change, trade, 3, 101.0), "the entry bar's own close already differs"
    assert not bracket.early_exit_due(change, trade, 4, 101.0)


def test_an_undefined_regime_label_on_either_side_never_counts_as_a_change() -> None:
    change = rule(regime_labels=labels(regime.UNDEFINED, DIRECTIONAL, regime.UNDEFINED))
    assert not bracket.early_exit_due(change, open_trade(entry_bar=1), 1, 99.0)
    assert not bracket.early_exit_due(change, open_trade(entry_bar=2), 2, 99.0)


def test_only_if_losing_holds_a_winner_through_a_regime_change() -> None:
    series = labels(DIRECTIONAL, CONSOLIDATING)
    trade = open_trade(entry_bar=1)
    assert bracket.early_exit_due(rule(regime_labels=series), trade, 1, 101.0)
    losing_only = rule(only_if_losing=True, regime_labels=series)
    assert not bracket.early_exit_due(losing_only, trade, 1, 101.0)
    assert bracket.early_exit_due(losing_only, trade, 1, 99.0)


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
    assert bracket.early_exit_due(turn, open_trade(entry_bar=1), 1, 99.0) is fires


def test_a_label_exit_on_a_position_entered_on_the_first_bar_has_nothing_to_compare_with() -> None:
    series = labels(DIRECTIONAL, CONSOLIDATING)
    first_bar = open_trade(entry_bar=0)
    assert not bracket.early_exit_due(rule(regime_labels=series), first_bar, 1, 99.0)
    turn = rule(trend_form=bracket.TREND_EXIT_OPPOSED, trend_labels=labels(UP, DOWN))
    assert not bracket.early_exit_due(turn, first_bar, 1, 99.0)


def test_the_hold_cap_takes_a_bar_it_and_the_early_exit_would_both_leave_on() -> None:
    losing = open_trade(entry_bar=5)
    three_bars = rule(at_bar=3)
    assert bracket.market_exit_reason(losing, 8, 99.0, 3, three_bars) == EXIT_TIME_LIMIT
    assert bracket.market_exit_reason(losing, 8, 99.0, 0, three_bars) == EXIT_EARLY
    assert bracket.market_exit_reason(losing, 7, 99.0, 0, three_bars) == bracket.NO_MARKET_EXIT
    assert bracket.market_exit_reason(losing, 7, 99.0, 0, bracket.EARLY_EXIT_OFF) == bracket.NO_MARKET_EXIT


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
        ({"early_exit_below_r": 0.5}, "early_exit_bars is 0, so the not-working exit that reads it is off"),
        ({"early_exit_only_if_losing": True}, "neither the regime exit nor the trend exit is on"),
        (
            {"early_exit_minutes_before_close": 30, "early_exit_only_if_losing": True},
            "neither the regime exit nor the trend exit is on",
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
    assert built.near_close.size == built.regime_labels.size == built.trend_labels.size == 0
    assert (built.at_bar, built.below_r, built.trend_form, built.only_if_losing) == (
        off.at_bar,
        off.below_r,
        off.trend_form,
        off.only_if_losing,
    )


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


def condition_held(params, data, series: LabelArray | None, trade: np.ndarray, risk: float, bar: int) -> bool:
    """Recompute from the bars whether ``params``' rule held at ``bar``'s close for ``trade``.

    ``series`` is :func:`rule_labels` for the same ``params``.
    """
    profit = losing_by(data.close[bar], trade)
    entry_bar = int(trade[C_ENTRY_BAR])
    if params.early_exit_bars > 0:
        return bar - entry_bar == params.early_exit_bars and profit < params.early_exit_below_r * risk

    if params.early_exit_minutes_before_close > 0:
        return profit < 0 and data.seconds_to_session_end[bar] <= params.early_exit_minutes_before_close * 60

    if params.early_exit_only_if_losing and profit >= 0:
        return False

    assert series is not None, "a label rule reads rule_labels' series"
    before = entry_bar - 1
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
    with pytest.raises(sweep.SweepError, match=r"early_exit_below_r \(inert while early_exit_bars is 0\)"):
        sweep.Grid.of(TRADING[name], archetype=archetype, early_exit_below_r=[0.0, 0.25])

    at_three = dataclasses.replace(TRADING[name], early_exit_bars=3)
    assert len(sweep.Grid.of(at_three, archetype=archetype, early_exit_below_r=[0.0, 0.25])) == 2


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
