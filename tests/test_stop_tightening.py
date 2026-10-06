"""The stop tightening with time: the rules, parameters, context they read, loops and registry.

What carries it is that **the stop only ever moves to a level one of the two rules named at an
earlier close, and never loosens after**: a trade no rule named a level for is left exactly as it
was, and every stop exit is at the tightest level named before it or better, unless the bar
gapped through it -- ``docs/nt8-fidelity.md``, "Tightening the stop with time".
"""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

from nqbt import archetypes, sweep
from nqbt.archetypes import Tier2Status
from nqbt.instruments import MNQ
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    LATE_STOP_ATR_PERIOD,
    DeadCatParams,
    EmaCrossoverParams,
    InsideBarParams,
    InsideBarTrailingParams,
    PullBackAndGoParams,
)
from nqbt.trades import (
    C_DIRECTION,
    C_ENTRY_BAR,
    C_ENTRY_PRICE,
    C_EXIT_BAR,
    C_EXIT_PRICE,
    C_EXIT_REASON,
    C_INITIAL_STOP,
    C_LEG,
    C_RISK_POINTS,
    C_TRADE_ID,
    EXIT_EARLY,
    EXIT_STOP,
    LONG,
    SHORT,
)
from tests.test_confluence_sizing import EVERY_CLASS, TRADING, prepared
from tests.test_early_exit import EVERY_LOOP
from tests.test_insidebartrailing_sim import walk_bars

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray
    from nqbt.context import ContextSpec, Dataset
    from tests.test_confluence_sizing import ArchetypeParams

TICK = 0.25
COSTS = bracket.Costs(tick_size=TICK, point_value=2.0, commission_per_contract=0.0, slippage_ticks=0.0)
SNAPPED = bracket.FillRules(fill_limit_on_touch=False, ambiguity_policy=1, round_targets=True)
UNSNAPPED = SNAPPED._replace(round_targets=False)

ARMS: dict[str, dict[str, object]] = {
    "to the entry at bar 1": {"age_stop_bars": 1},
    "half way along a line over 4 bars, while losing": {
        "age_stop_bars": 4,
        "age_stop_shape": bracket.AGE_STOP_LINE,
        "age_stop_fraction": 0.5,
        "age_stop_only_if_losing": True,
    },
    "half way at 2 minutes, while losing": {
        "age_stop_minutes": 2,
        "age_stop_fraction": 0.5,
        "age_stop_only_if_losing": True,
    },
    "to the entry late": {"late_stop_minutes_before_close": 600},
    "to the bar's extreme late": {
        "late_stop_minutes_before_close": 600,
        "late_stop_to": bracket.LATE_STOP_BAR_EXTREME,
    },
    "half an ATR of 10 late": {
        "late_stop_minutes_before_close": 600,
        "late_stop_to": bracket.LATE_STOP_ATR,
        "late_stop_atr": 0.5,
        "late_stop_atr_period": 10,
    },
}
"""One arm per shape, clock and late level, each moving a stop in every loop on :func:`walk_bars`.

The late window is wider than a campaign would run it so that it opens often on these bars."""


def open_trade(
    *, entry_bar: int = 2, entry_price: float = 100.0, risk: float = 10.0, direction: float = LONG
) -> bracket.OpenTrade:
    return bracket.OpenTrade(
        trade_id=1,
        entry_bar=entry_bar,
        entry_price=entry_price,
        initial_stop=entry_price - direction * risk,
        risk=risk,
        direction=direction,
        filled_at_open=True,
    )


def flat_bars(closes: list[float], *, spread: float = 1.0) -> bracket.Bars:
    """Return bars closing at ``closes``, each ``spread`` either side of its close."""
    close = np.asarray(closes, dtype=np.float64)

    return bracket.Bars(
        close.copy(), close + spread, close - spread, close, np.zeros(close.size, dtype=np.bool_)
    )


def rule(**fields: object) -> bracket.StopTightening:
    return bracket.STOP_TIGHTENING_OFF._replace(**fields)  # type: ignore[arg-type]  # each caller passes a field's own type


def level(
    bars: bracket.Bars,
    the_rule: bracket.StopTightening,
    trade: bracket.OpenTrade,
    i: int,
    *,
    initial_stop: float | None = None,
    fills: bracket.FillRules = SNAPPED,
) -> float:
    stop = trade.initial_stop if initial_stop is None else initial_stop

    return bracket.tightening_level(the_rule, trade, stop, bars, i, COSTS, fills)


def minute_clock(*minutes: float) -> FloatArray:
    return 1_700_000_000.0 + 60.0 * np.asarray(minutes, dtype=np.float64)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(20_000, seed=5)


# -- the age stop ------------------------------------------------------------------------------


def test_with_both_rules_off_no_level_is_returned() -> None:
    winning = flat_bars([100.0] * 3 + [150.0] * 10)
    assert all(math.isnan(level(winning, bracket.STOP_TIGHTENING_OFF, open_trade(), i)) for i in range(2, 13))


def test_the_step_moves_the_whole_fraction_at_its_age_and_not_before() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 10)
    half_at_three = rule(age_after=3.0, age_fraction=0.5)
    trade = open_trade(entry_bar=2, risk=10.0)
    assert all(math.isnan(level(winning, half_at_three, trade, i)) for i in range(2, 5))
    assert level(winning, half_at_three, trade, 5) == 95.0
    assert level(winning, half_at_three, trade, 9) == 95.0


def test_the_line_moves_a_little_at_every_close_until_its_age() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 10)
    line = rule(age_after=4.0, age_fraction=1.0, age_shape=bracket.AGE_STOP_LINE)
    trade = open_trade(entry_bar=2, risk=8.0)
    assert math.isnan(level(winning, line, trade, 2)), "age 0 names no level"
    assert [level(winning, line, trade, i) for i in range(3, 9)] == [
        94.0,
        96.0,
        98.0,
        100.0,
        100.0,
        100.0,
    ]


def test_the_line_does_not_snap_an_initial_stop_off_the_tick_grid_at_age_0() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 4)
    line = rule(age_after=4.0, age_shape=bracket.AGE_STOP_LINE)
    trade = open_trade(entry_bar=2, entry_price=100.0, risk=10.1)
    assert trade.initial_stop == pytest.approx(89.9)
    assert math.isnan(level(winning, line, trade, 2)), "89.9 would round to 90.0, nearer the market"
    assert level(winning, line, trade, 3) == 92.5


def test_the_fraction_is_of_the_distance_from_the_stop_it_is_given_so_each_lot_moves_from_its_own() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 10)
    half_at_one = rule(age_after=1.0, age_fraction=0.5)
    trade = open_trade(entry_bar=2, risk=10.0)
    assert level(winning, half_at_one, trade, 3) == 95.0
    assert level(winning, half_at_one, trade, 3, initial_stop=80.0) == 90.0


def test_the_minutes_clock_times_the_age_on_the_bars_own_timestamps() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 5)
    clock = minute_clock(0, 1, 2, 7, 12, 17, 22)
    trade = open_trade(entry_bar=2, risk=10.0)
    step = rule(age_after=10.0, clock=clock)
    assert [math.isnan(level(winning, step, trade, i)) for i in range(2, 7)] == [
        True,
        True,
        False,
        False,
        False,
    ]
    line = rule(age_after=10.0, age_shape=bracket.AGE_STOP_LINE, clock=clock)
    assert level(winning, line, trade, 3) == 95.0


def test_only_if_losing_leaves_a_winners_stop_alone() -> None:
    closes = flat_bars([100.0, 100.0, 100.0, 101.0, 99.0, 100.0])
    losing_only = rule(age_after=1.0, age_fraction=0.5, age_only_if_losing=True)
    trade = open_trade(entry_bar=2, risk=10.0)
    assert math.isnan(level(closes, losing_only, trade, 3)), "a winner"
    assert level(closes, losing_only, trade, 4) == 95.0, "a loser"
    assert math.isnan(level(closes, losing_only, trade, 5)), "exactly at the entry is not losing"


def test_a_level_at_or_through_the_close_is_not_a_stop_order() -> None:
    trade = open_trade(entry_bar=2, risk=10.0)
    to_the_entry = rule(age_after=1.0)
    assert math.isnan(level(flat_bars([100.0] * 4), to_the_entry, trade, 3)), "at the close"
    assert math.isnan(level(flat_bars([100.0, 100.0, 100.0, 98.0]), to_the_entry, trade, 3)), "through it"
    assert level(flat_bars([100.0, 100.0, 100.0, 100.25]), to_the_entry, trade, 3) == 100.0


def test_the_level_snaps_to_the_tick_only_where_targets_do() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 3)
    third = rule(age_after=1.0, age_fraction=1.0 / 3.0)
    trade = open_trade(entry_bar=2, risk=10.0)
    assert level(winning, third, trade, 3) == 93.25
    assert level(winning, third, trade, 3, fills=UNSNAPPED) == pytest.approx(90.0 + 10.0 / 3.0)


def test_the_short_side_is_the_long_side_through_the_sign() -> None:
    winning = flat_bars([100.0] * 2 + [95.0] * 6)
    short = open_trade(entry_bar=2, risk=10.0, direction=SHORT)
    assert level(winning, rule(age_after=2.0, age_fraction=0.5), short, 4) == 105.0
    line = rule(age_after=4.0, age_shape=bracket.AGE_STOP_LINE)
    assert level(winning, line, short, 3) == 107.5
    losing = flat_bars([100.0] * 2 + [102.0] * 6)
    assert level(losing, rule(age_after=1.0, age_fraction=0.5, age_only_if_losing=True), short, 3) == 105.0


# -- the late stop -----------------------------------------------------------------------------


def window(n: int, *open_from: int) -> BoolArray:
    late = np.zeros(n, dtype=np.bool_)
    late[list(open_from)] = True

    return late


def test_the_late_stop_moves_only_inside_its_window() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 4)
    late = rule(late_window=window(6, 4, 5))
    trade = open_trade(entry_bar=2)
    assert math.isnan(level(winning, late, trade, 3))
    assert [level(winning, late, trade, i) for i in (4, 5)] == [100.0, 100.0]


def test_the_late_stop_at_the_entry_cannot_move_a_losers_stop() -> None:
    losing = flat_bars([100.0] * 2 + [97.0] * 2)
    assert math.isnan(level(losing, rule(late_window=window(4, 3)), open_trade(entry_bar=2), 3))


def test_the_bar_extreme_is_the_just_closed_bars_adverse_side() -> None:
    bars = bracket.Bars(
        np.full(4, 100.0),
        np.asarray([100.0, 100.0, 104.0, 106.0]),
        np.asarray([100.0, 100.0, 96.0, 98.5]),
        np.asarray([100.0, 100.0, 101.0, 103.0]),
        np.zeros(4, dtype=np.bool_),
    )
    extreme = rule(late_window=window(4, 3), late_to=bracket.LATE_STOP_BAR_EXTREME)
    assert level(bars, extreme, open_trade(entry_bar=2), 3) == 98.5
    assert level(bars, extreme, open_trade(entry_bar=2, direction=SHORT), 3) == 106.0


def test_a_bar_closing_on_its_extreme_names_no_stop() -> None:
    bars = bracket.Bars(
        np.full(3, 100.0),
        np.full(3, 101.0),
        np.full(3, 99.0),
        np.asarray([100.0, 100.0, 99.0]),
        np.zeros(3, dtype=np.bool_),
    )
    extreme = rule(late_window=window(3, 2), late_to=bracket.LATE_STOP_BAR_EXTREME)
    assert math.isnan(level(bars, extreme, open_trade(entry_bar=1), 2))


def test_the_atr_level_is_measured_from_the_close_on_the_bars_own_atr() -> None:
    losing = flat_bars([100.0] * 2 + [97.0] * 2)
    atr = np.asarray([9.0, 9.0, 9.0, 4.0])
    in_atr = rule(
        late_window=window(4, 3), late_to=bracket.LATE_STOP_ATR, late_atr_multiple=0.5, late_atr=atr
    )
    assert level(losing, in_atr, open_trade(entry_bar=2), 3) == 95.0
    assert level(losing, in_atr, open_trade(entry_bar=2, direction=SHORT), 3) == 99.0
    warming = in_atr._replace(late_atr=np.full(4, np.nan))
    assert math.isnan(level(losing, warming, open_trade(entry_bar=2), 3))


def test_with_both_rules_on_the_level_nearer_the_market_is_the_one_returned() -> None:
    winning = flat_bars([100.0] * 2 + [105.0] * 4)
    trade = open_trade(entry_bar=2, risk=10.0)
    both = rule(age_after=1.0, age_fraction=0.5, late_window=window(6, 5))
    assert level(winning, both, trade, 4) == 95.0, "the late window is shut"
    assert level(winning, both, trade, 5) == 100.0, "the late stop is nearer"
    nearer_age = both._replace(
        age_fraction=1.0, late_to=bracket.LATE_STOP_ATR, late_atr_multiple=2.0, late_atr=np.full(6, 5.0)
    )
    assert level(winning, nearer_age, trade, 5) == 100.0
    no_age = both._replace(age_only_if_losing=True)
    assert level(winning, no_age, trade, 5) == 100.0, "the age stop is off, the late stop still moves"


# -- the parameters ----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_both_rules_are_off_by_default_on_every_class(cls: type[ArchetypeParams]) -> None:
    params = cls()
    assert (params.age_stop_bars, params.age_stop_minutes, params.late_stop_minutes_before_close) == (0, 0, 0)
    assert params.late_stop_atr_period == LATE_STOP_ATR_PERIOD


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"age_stop_bars": -1}, "age_stop_bars must be >= 0"),
        ({"age_stop_minutes": -1}, "age_stop_minutes must be >= 0"),
        ({"late_stop_minutes_before_close": -1}, "late_stop_minutes_before_close must be >= 0"),
        ({"age_stop_bars": 2, "age_stop_fraction": 0.0}, "age_stop_fraction must be above 0 and at most 1"),
        ({"age_stop_bars": 2, "age_stop_fraction": 1.5}, "age_stop_fraction must be above 0 and at most 1"),
        ({"age_stop_bars": 2, "age_stop_fraction": math.nan}, "age_stop_fraction must be above 0"),
        ({"age_stop_bars": 2, "age_stop_shape": 2}, "age_stop_shape must be one of"),
        ({"late_stop_minutes_before_close": 30, "late_stop_to": 3}, "late_stop_to must be one of"),
        (
            {
                "late_stop_minutes_before_close": 30,
                "late_stop_to": bracket.LATE_STOP_ATR,
                "late_stop_atr": 0.0,
            },
            "late_stop_atr must be > 0 and finite",
        ),
        (
            {
                "late_stop_minutes_before_close": 30,
                "late_stop_to": bracket.LATE_STOP_ATR,
                "late_stop_atr": math.inf,
            },
            "late_stop_atr must be > 0 and finite",
        ),
        (
            {
                "late_stop_minutes_before_close": 30,
                "late_stop_to": bracket.LATE_STOP_ATR,
                "late_stop_atr_period": 0,
            },
            "late_stop_atr_period must be >= 1",
        ),
        ({"age_stop_bars": 2, "age_stop_minutes": 10}, "the age stop is timed in one or the other"),
        (
            {"age_stop_fraction": 0.5},
            "age_stop_fraction set but age_stop_bars and age_stop_minutes are both 0",
        ),
        (
            {"age_stop_shape": bracket.AGE_STOP_LINE, "age_stop_only_if_losing": True},
            "age_stop_shape, age_stop_only_if_losing set but",
        ),
        ({"late_stop_to": bracket.LATE_STOP_ATR}, "late_stop_to set but late_stop_minutes_before_close is 0"),
        ({"late_stop_atr": 2.0}, "late_stop_atr set but the late stop is not at an ATR multiple"),
        (
            {"late_stop_minutes_before_close": 30, "late_stop_atr_period": 21},
            "late_stop_atr_period set but the late stop is not at an ATR multiple",
        ),
        ({"max_hold_bars": 3, "age_stop_bars": 3}, "can never move a stop under max_hold_bars of 3"),
        ({"max_hold_bars": 3, "age_stop_bars": 5}, "can never move a stop under max_hold_bars of 3"),
    ],
)
def test_a_tightening_out_of_range_unread_or_unreachable_is_refused(
    cls: type[ArchetypeParams], fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        cls(**fields)


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_every_arm_is_accepted_and_may_run_beside_a_breakeven_and_an_early_exit(
    cls: type[ArchetypeParams],
) -> None:
    for fields in ARMS.values():
        assert cls(**fields, breakeven_at=1.0, early_exit_bars=3).breakeven_at == 1.0  # type: ignore[call-arg]  # every params class takes its fields as keywords

    both = cls(age_stop_bars=2, late_stop_minutes_before_close=30)  # type: ignore[call-arg]  # every params class takes its fields as keywords
    assert both.age_stop_bars == 2


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_a_line_reaching_past_the_hold_cap_still_moves_before_it(cls: type[ArchetypeParams]) -> None:
    assert cls(max_hold_bars=3, age_stop_bars=5, age_stop_shape=bracket.AGE_STOP_LINE).age_stop_bars == 5  # type: ignore[call-arg]  # every params class takes its fields as keywords
    assert cls(max_hold_bars=4, age_stop_bars=3).age_stop_bars == 3  # type: ignore[call-arg]  # every params class takes its fields as keywords


# -- the context it reads ----------------------------------------------------------------------


def test_with_both_rules_off_it_carries_no_series(bars: pd.DataFrame) -> None:
    params = TRADING["DeadCatBounce"]
    built = filters.stop_tightening(prepared(bars, params, archetypes.DEADCATBOUNCE), params)
    off = bracket.STOP_TIGHTENING_OFF
    assert built.clock.size == built.late_window.size == built.late_atr.size == 0
    scalars = ("age_after", "age_fraction", "age_shape", "age_only_if_losing", "late_to", "late_atr_multiple")
    assert [getattr(built, name) for name in scalars] == [getattr(off, name) for name in scalars]


def test_the_age_reads_bars_or_the_bars_own_clock(bars: pd.DataFrame) -> None:
    in_bars = dataclasses.replace(TRADING["DeadCatBounce"], age_stop_bars=4)
    data = prepared(bars, in_bars, archetypes.DEADCATBOUNCE)
    built = filters.stop_tightening(data, in_bars)
    assert (built.age_after, built.clock.size) == (4.0, 0)
    in_minutes = dataclasses.replace(TRADING["DeadCatBounce"], age_stop_minutes=30)
    built = filters.stop_tightening(data, in_minutes)
    assert built.age_after == 30.0
    assert np.array_equal(built.clock, data.bar_seconds())


def test_the_late_window_is_the_no_entry_windows_and_the_atr_is_read_only_at_an_atr_multiple(
    bars: pd.DataFrame,
) -> None:
    late = dataclasses.replace(TRADING["DeadCatBounce"], late_stop_minutes_before_close=45)
    data = prepared(bars, late, archetypes.DEADCATBOUNCE)
    built = filters.stop_tightening(data, late)
    assert np.array_equal(built.late_window, ~data.session_end_gate(45))
    assert built.late_window.any()
    assert not built.late_window.all()
    assert built.late_atr.size == 0
    in_atr = dataclasses.replace(late, late_stop_to=bracket.LATE_STOP_ATR, late_stop_atr_period=21)
    data = prepared(bars, in_atr, archetypes.DEADCATBOUNCE)
    assert np.array_equal(filters.stop_tightening(data, in_atr).late_atr, data.atr_values(21), equal_nan=True)


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_series_a_rule_reads_is_built_into_the_dataset(name: str) -> None:
    archetype = archetypes.get(name)

    def spec(**fields: object) -> ContextSpec:
        return sweep.Grid.of(
            dataclasses.replace(TRADING[name], **fields), archetype=archetype
        ).required_context()

    assert not spec(age_stop_bars=3).needs_session_clock
    assert spec(late_stop_minutes_before_close=30).needs_session_clock
    assert (
        21
        not in spec(late_stop_minutes_before_close=30, late_stop_to=bracket.LATE_STOP_BAR_EXTREME).atr_periods
    )
    late_atr = spec(
        late_stop_minutes_before_close=30, late_stop_to=bracket.LATE_STOP_ATR, late_stop_atr_period=21
    )
    assert 21 in late_atr.atr_periods


# -- the loops ---------------------------------------------------------------------------------


def trade_of(rows: FloatArray) -> bracket.OpenTrade:
    """Return the position ``rows`` were legs of, carrying the bracketed lot's R as the loops do."""
    first = rows[0]

    return open_trade(
        entry_bar=int(first[C_ENTRY_BAR]),
        entry_price=float(first[C_ENTRY_PRICE]),
        risk=float(rows[rows[:, C_LEG] == 1][0, C_RISK_POINTS]),
        direction=float(first[C_DIRECTION]),
    )


def tightest_before(
    params: ArchetypeParams, data: Dataset, leg: FloatArray, trade: bracket.OpenTrade, until: int
) -> float:
    """Return the tightest level the rules named for ``leg`` at any close before bar ``until``, or ``nan``."""
    the_rule = filters.stop_tightening(data, params)
    bars = bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat)
    costs = COSTS._replace(tick_size=MNQ.tick_size)
    # DeadCatBounce has no field for it: its NinjaScript always rounds.
    fills = SNAPPED._replace(round_targets=getattr(params, "round_targets", True))
    tightest = math.nan
    for bar in range(trade.entry_bar, until):
        named = bracket.tightening_level(the_rule, trade, float(leg[C_INITIAL_STOP]), bars, bar, costs, fills)
        if math.isnan(tightest) or trade.direction * (named - tightest) > 0:
            tightest = named

    return tightest


def by_entry(matrix: FloatArray) -> dict[int, FloatArray]:
    return {int(bar): matrix[matrix[:, C_ENTRY_BAR] == bar] for bar in np.unique(matrix[:, C_ENTRY_BAR])}


@pytest.mark.parametrize("arm", sorted(ARMS))
@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_every_stop_exit_is_at_the_tightest_level_named_before_it_or_gapped_through_it(
    bars: pd.DataFrame, loop: str, arm: str
) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    params = dataclasses.replace(base, **ARMS[arm])
    data = prepared(bars, params, archetype)
    legs = archetype.legs(data, params, MNQ)
    at_the_level = 0
    for rows in by_entry(legs.matrix[: legs.count]).values():
        trade = trade_of(rows)
        for leg in rows[rows[:, C_EXIT_REASON] == EXIT_STOP]:
            exit_bar = int(leg[C_EXIT_BAR])
            tightest = tightest_before(params, data, leg, trade, exit_bar)
            if math.isnan(tightest):
                continue

            d, exit_price = leg[C_DIRECTION], leg[C_EXIT_PRICE]
            gapped = d * (data.open[exit_bar] - tightest) < 0 and np.isclose(exit_price, data.open[exit_bar])
            assert d * (exit_price - tightest) >= -1e-9 or gapped, (
                f"entry bar {int(leg[C_ENTRY_BAR])} left at {exit_price} behind its level {tightest}"
            )
            at_the_level += int(np.isclose(exit_price, tightest))

    assert at_the_level > 0, "no stop ever left at a named level, so the test proves nothing"


LEAVES_SOME_TRADES_ALONE = sorted(set(ARMS) - {"half way along a line over 4 bars, while losing"})
"""Every arm but the line, which moves every ElasticBand trade: a fade nearly always closes losing once."""


@pytest.mark.parametrize("arm", LEAVES_SOME_TRADES_ALONE)
@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_a_trade_no_rule_named_a_level_for_is_left_exactly_as_it_was(
    bars: pd.DataFrame, loop: str, arm: str
) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    params = dataclasses.replace(base, **ARMS[arm])
    data = prepared(bars, params, archetype)
    off = archetype.legs(data, base, MNQ)
    moved = archetype.legs(data, params, MNQ)
    on = by_entry(moved.matrix[: moved.count])
    untouched = 0
    for entry_bar, rows in by_entry(off.matrix[: off.count]).items():
        trade = trade_of(rows)
        last_exit = int(rows[:, C_EXIT_BAR].max())
        # A level at or behind the initial stop moves nothing.
        moves = [
            trade.direction * (tightest_before(params, data, leg, trade, last_exit) - leg[C_INITIAL_STOP]) > 0
            for leg in rows
        ]
        if entry_bar not in on or any(moves):
            continue

        untouched += 1
        # A trade's id counts the trades before it, which the rule may have changed.
        before, after = (np.delete(legs, C_TRADE_ID, axis=1) for legs in (rows, on[entry_bar]))
        assert np.array_equal(before, after, equal_nan=True), f"entry bar {entry_bar} moved"

    assert untouched > 0, "every trade had a level named, so the test proves nothing"


@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_a_rule_that_never_names_a_level_leaves_every_trade_as_it_was(bars: pd.DataFrame, loop: str) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    never = dataclasses.replace(base, age_stop_bars=10**6)
    data = prepared(bars, never, archetype)
    off = archetype.legs(data, base, MNQ)
    on = archetype.legs(data, never, MNQ)
    assert off.count > 10
    assert np.array_equal(off.matrix[: off.count], on.matrix[: on.count], equal_nan=True)


def stopped_at_entry(params: ArchetypeParams, data: Dataset) -> int:
    """Count the legs ``params`` stops out exactly at their entry price on DeadCatBounce."""
    legs = archetypes.DEADCATBOUNCE.legs(data, params, MNQ)
    # The rows past ``count`` are zero padding, which reads as a stop exit at a price of zero.
    matrix = legs.matrix[: legs.count]
    stopped = matrix[matrix[:, C_EXIT_REASON] == EXIT_STOP]

    return int(np.isclose(stopped[:, C_EXIT_PRICE], stopped[:, C_ENTRY_PRICE]).sum())


def test_the_tightening_and_an_early_exit_both_act_in_one_run(bars: pd.DataFrame) -> None:
    """The ratchet alone stops some legs out at their entry, so the tightening has to add to that count."""
    early_only = dataclasses.replace(TRADING["DeadCatBounce"], early_exit_bars=3)
    both = dataclasses.replace(early_only, **ARMS["to the entry at bar 1"])
    data = prepared(bars, both, archetypes.DEADCATBOUNCE)
    legs = archetypes.DEADCATBOUNCE.legs(data, both, MNQ)
    assert (legs.matrix[: legs.count, C_EXIT_REASON] == EXIT_EARLY).any()
    assert stopped_at_entry(both, data) > stopped_at_entry(early_only, data)


# -- the registry and the sweep ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_age_stops_settings_are_dead_without_it(name: str) -> None:
    archetype = archetypes.get(name)
    with pytest.raises(
        sweep.SweepError,
        match=r"age_stop_fraction \(inert while age_stop_bars is 0 and age_stop_minutes is 0\)",
    ):
        sweep.Grid.of(TRADING[name], archetype=archetype, age_stop_fraction=[0.5, 1.0])

    on = dataclasses.replace(TRADING[name], age_stop_minutes=30)
    assert (
        len(sweep.Grid.of(on, archetype=archetype, age_stop_fraction=[0.5, 1.0], age_stop_shape=[0, 1])) == 4
    )


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_late_stops_settings_are_dead_without_its_window_and_its_atr_without_an_atr_level(
    name: str,
) -> None:
    archetype = archetypes.get(name)
    with pytest.raises(
        sweep.SweepError, match=r"late_stop_to \(inert while late_stop_minutes_before_close is 0\)"
    ):
        sweep.Grid.of(TRADING[name], archetype=archetype, late_stop_to=[0, 1])

    late = dataclasses.replace(TRADING[name], late_stop_minutes_before_close=30)
    with pytest.raises(sweep.SweepError, match=r"late_stop_atr_period \(inert while late_stop_to is 0\)"):
        sweep.Grid.of(late, archetype=archetype, late_stop_atr_period=[14, 21])

    in_atr = dataclasses.replace(late, late_stop_to=bracket.LATE_STOP_ATR)
    assert len(sweep.Grid.of(in_atr, archetype=archetype, late_stop_atr_period=[14, 21])) == 2


@pytest.mark.parametrize(
    ("archetype", "params"),
    [
        (archetypes.DEADCATBOUNCE, DeadCatParams()),
        (archetypes.PULLBACKANDGO, PullBackAndGoParams()),
        (archetypes.INSIDEBAR, InsideBarParams()),
        (archetypes.INSIDEBARTRAILING, InsideBarTrailingParams()),
    ],
)
@pytest.mark.parametrize("arm", sorted(ARMS))
def test_a_tightening_row_leaves_every_reconciled_port(
    archetype: archetypes.Archetype, params: ArchetypeParams, arm: str
) -> None:
    assert archetype.tier2_for(params) is Tier2Status.RECONCILED
    assert archetype.tier2_for(dataclasses.replace(params, **ARMS[arm])) is Tier2Status.TIER1_ONLY


def test_an_original_archetype_stays_tier_1_only_with_a_tightening_or_not() -> None:
    assert archetypes.EMACROSSOVER.tier2_for(EmaCrossoverParams()) is Tier2Status.TIER1_ONLY
    assert archetypes.EMACROSSOVER.tier2_for(EmaCrossoverParams(age_stop_bars=2)) is Tier2Status.TIER1_ONLY
