"""The breakeven stop: the rule, the parameters, the context it reads, the loops and the registry.

What carries it is that **the stop moves to the entry only after a close where the trigger held,
and never loosens after**: a trade whose trigger never held is left exactly as it was, and every
stop exit after the trigger is at the level or better unless the bar gapped through it --
``docs/nt8-fidelity.md``, "The breakeven stop".
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
    BREAKEVEN_ATR_PERIOD,
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

    from nqbt.arrays import FloatArray
    from nqbt.context import ContextSpec, Dataset
    from tests.test_confluence_sizing import ArchetypeParams

TICK = 0.25
COSTS = bracket.Costs(tick_size=TICK, point_value=2.0, commission_per_contract=0.0, slippage_ticks=0.0)
SNAPPED = bracket.FillRules(fill_limit_on_touch=False, ambiguity_policy=1, round_targets=True)
UNSNAPPED = SNAPPED._replace(round_targets=False)

ARMS: dict[str, dict[str, object]] = {
    "0.05R on the close": {"breakeven_at": 0.05},
    "0.05R on the extreme, 2 ticks past": {
        "breakeven_at": 0.05,
        "breakeven_on": bracket.BREAKEVEN_ON_EXTREME,
        "breakeven_offset_ticks": 2,
    },
    "0.25 ATRs of 21 on the close": {
        "breakeven_at": 0.25,
        "breakeven_unit": bracket.BREAKEVEN_ATR,
        "breakeven_atr_period": 21,
    },
}
"""One arm per unit and per trigger price, each firing in every loop on :func:`walk_bars`.

The thresholds are small because InsideBar's default target sits about a tenth of its R from the
entry, so a trigger any further out would never be reached before it."""


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


def one_bar(*, high: float, low: float, close: float, bars_before: int = 3) -> bracket.Bars:
    """Return ``bars_before`` flat bars at 100 and then one bar with the given range and close."""
    flat = [100.0] * bars_before

    return bracket.Bars(
        open_=np.asarray([*flat, 100.0]),
        high=np.asarray([*flat, high]),
        low=np.asarray([*flat, low]),
        close=np.asarray([*flat, close]),
        force_flat=np.zeros(bars_before + 1, dtype=np.bool_),
    )


def rule(**fields: object) -> bracket.Breakeven:
    return bracket.BREAKEVEN_OFF._replace(**fields)  # type: ignore[arg-type]  # each caller passes a field's own type


def level(
    bars: bracket.Bars,
    the_rule: bracket.Breakeven,
    trade: bracket.OpenTrade,
    fills: bracket.FillRules = SNAPPED,
) -> float:
    return bracket.breakeven_level(the_rule, trade, bars, bars.close.size - 1, COSTS, fills)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(20_000, seed=5)


# -- the rule ----------------------------------------------------------------------------------


def test_with_the_rule_off_no_level_is_returned() -> None:
    assert math.isnan(level(one_bar(high=200.0, low=100.0, close=190.0), bracket.BREAKEVEN_OFF, open_trade()))


def test_a_close_exactly_on_the_trigger_moves_the_stop_and_one_tick_short_does_not() -> None:
    trade = open_trade(risk=10.0)
    assert level(one_bar(high=111.0, low=100.0, close=110.0), rule(at=1.0), trade) == 100.0
    assert math.isnan(level(one_bar(high=111.0, low=100.0, close=110.0 - TICK), rule(at=1.0), trade))


def test_a_gain_exactly_on_a_distance_that_floating_point_rounds_up_still_triggers() -> None:
    assert 1.1 * 12.5 > 13.75, "the case this pins: the product rounds above the exact distance"
    bar = one_bar(high=114.0, low=100.0, close=113.75)
    assert level(bar, rule(at=1.1), open_trade(risk=12.5)) == 100.0


def test_the_threshold_in_r_moves_with_the_planned_risk() -> None:
    bar = one_bar(high=106.0, low=100.0, close=105.0)
    assert level(bar, rule(at=1.0), open_trade(risk=5.0)) == 100.0
    assert math.isnan(level(bar, rule(at=1.0), open_trade(risk=10.0)))


def test_the_extreme_trigger_fires_on_a_bar_whose_close_fell_back() -> None:
    bar = one_bar(high=110.0, low=100.0, close=103.0)
    assert math.isnan(level(bar, rule(at=1.0), open_trade()))
    assert level(bar, rule(at=1.0, on=bracket.BREAKEVEN_ON_EXTREME), open_trade()) == 100.0


def test_the_atr_unit_reads_the_bar_before_the_entry_bar() -> None:
    atr = np.asarray([1.0, 4.0, 99.0, 99.0])
    bar = one_bar(high=104.0, low=100.0, close=104.0)
    assert level(bar, rule(at=1.0, unit=bracket.BREAKEVEN_ATR, atr=atr), open_trade(entry_bar=2)) == 100.0
    assert math.isnan(
        level(bar, rule(at=1.0, unit=bracket.BREAKEVEN_ATR, atr=atr * 2), open_trade(entry_bar=2))
    )


def test_an_atr_warming_up_or_missing_or_a_position_entered_on_the_first_bar_never_moves() -> None:
    bar = one_bar(high=200.0, low=100.0, close=200.0)
    warming = rule(at=1.0, unit=bracket.BREAKEVEN_ATR, atr=np.full(4, np.nan))
    assert math.isnan(level(bar, warming, open_trade(entry_bar=2)))
    first = rule(at=1.0, unit=bracket.BREAKEVEN_ATR, atr=np.ones(4))
    assert math.isnan(level(bar, first, open_trade(entry_bar=0)))
    no_atr = rule(at=1.0, unit=bracket.BREAKEVEN_ATR)
    assert math.isnan(level(bar, no_atr, open_trade(entry_bar=2)))


def test_the_offset_puts_the_stop_that_many_ticks_past_the_entry() -> None:
    bar = one_bar(high=111.0, low=100.0, close=110.0)
    assert level(bar, rule(at=1.0, offset_ticks=3.0), open_trade()) == 100.0 + 3 * TICK


def test_the_level_snaps_to_the_tick_only_where_targets_do() -> None:
    bar = one_bar(high=111.0, low=100.0, close=110.0)
    off_grid = open_trade(entry_price=100.1)
    assert level(bar, rule(at=0.5), off_grid) == 100.0
    assert level(bar, rule(at=0.5), off_grid, fills=UNSNAPPED) == 100.1


def test_a_level_at_or_through_the_close_is_not_a_stop_order() -> None:
    reached_and_fell_back = one_bar(high=111.0, low=100.0, close=101.0)
    extreme = rule(at=1.0, on=bracket.BREAKEVEN_ON_EXTREME)
    assert level(reached_and_fell_back, extreme, open_trade()) == 100.0
    assert math.isnan(level(reached_and_fell_back, extreme._replace(offset_ticks=4.0), open_trade()))
    assert math.isnan(level(reached_and_fell_back, extreme._replace(offset_ticks=5.0), open_trade()))


def test_the_short_side_is_the_long_side_through_the_sign() -> None:
    short = open_trade(direction=SHORT)
    assert level(one_bar(high=100.0, low=89.0, close=90.0), rule(at=1.0, offset_ticks=2.0), short) == 99.5
    assert math.isnan(level(one_bar(high=100.0, low=89.0, close=90.0 + TICK), rule(at=1.0), short))
    extreme = rule(at=1.0, on=bracket.BREAKEVEN_ON_EXTREME)
    assert level(one_bar(high=100.0, low=90.0, close=97.0), extreme, short) == 100.0


def test_a_stop_already_past_the_level_is_left_where_it_is() -> None:
    assert bracket.tightened_stop(104.0, 100.0, LONG) == 104.0
    assert bracket.tightened_stop(96.0, 100.0, SHORT) == 96.0
    assert bracket.tightened_stop(90.0, math.nan, LONG) == 90.0


# -- the parameters ----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_the_rule_is_off_by_default_on_every_class(cls: type[ArchetypeParams]) -> None:
    params = cls()
    assert params.breakeven_at == 0.0
    assert params.breakeven_atr_period == BREAKEVEN_ATR_PERIOD


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"breakeven_at": -0.5}, "breakeven_at must be >= 0 and finite"),
        ({"breakeven_at": math.nan}, "breakeven_at must be >= 0 and finite"),
        ({"breakeven_at": math.inf}, "breakeven_at must be >= 0 and finite"),
        ({"breakeven_at": 1.0, "breakeven_unit": 2}, "breakeven_unit must be one of"),
        ({"breakeven_at": 1.0, "breakeven_on": 2}, "breakeven_on must be one of"),
        ({"breakeven_at": 1.0, "breakeven_offset_ticks": -1}, "breakeven_offset_ticks must be >= 0"),
        (
            {"breakeven_at": 1.0, "breakeven_unit": bracket.BREAKEVEN_ATR, "breakeven_atr_period": 0},
            "breakeven_atr_period must be >= 1",
        ),
        ({"breakeven_unit": bracket.BREAKEVEN_ATR}, "breakeven_unit set but breakeven_at is 0"),
        ({"breakeven_on": bracket.BREAKEVEN_ON_EXTREME}, "breakeven_on set but breakeven_at is 0"),
        (
            {"breakeven_offset_ticks": 2, "breakeven_atr_period": 21},
            "breakeven_offset_ticks, breakeven_atr_period set but breakeven_at is 0",
        ),
        ({"breakeven_at": 1.0, "breakeven_atr_period": 21}, "breakeven_unit is 'r', so nothing reads it"),
    ],
)
def test_a_breakeven_out_of_range_or_carrying_an_unread_setting_is_refused(
    cls: type[ArchetypeParams], fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        cls(**fields)


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_every_arm_is_accepted_and_may_run_beside_an_early_exit(cls: type[ArchetypeParams]) -> None:
    for fields in ARMS.values():
        assert cls(**fields).breakeven_at > 0.0
        assert cls(**fields, early_exit_bars=3).early_exit_bars == 3  # type: ignore[call-arg]  # every params class takes its fields as keywords


# -- the context it reads ----------------------------------------------------------------------


def test_with_the_rule_off_it_carries_no_atr(bars: pd.DataFrame) -> None:
    params = TRADING["DeadCatBounce"]
    built = filters.breakeven(prepared(bars, params, archetypes.DEADCATBOUNCE), params)
    off = bracket.BREAKEVEN_OFF
    assert built.atr.size == 0
    assert (built.at, built.unit, built.on, built.offset_ticks) == (
        off.at,
        off.unit,
        off.on,
        off.offset_ticks,
    )


def test_a_trigger_in_r_carries_no_atr_and_one_in_atrs_carries_its_own_period(bars: pd.DataFrame) -> None:
    in_r = dataclasses.replace(TRADING["DeadCatBounce"], breakeven_at=1.0)
    assert filters.breakeven(prepared(bars, in_r, archetypes.DEADCATBOUNCE), in_r).atr.size == 0
    in_atr = dataclasses.replace(in_r, breakeven_unit=bracket.BREAKEVEN_ATR, breakeven_atr_period=21)
    data = prepared(bars, in_atr, archetypes.DEADCATBOUNCE)
    assert np.array_equal(filters.breakeven(data, in_atr).atr, data.atr_values(21), equal_nan=True)


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_atr_a_trigger_reads_is_built_into_the_dataset_only_in_atrs(name: str) -> None:
    archetype = archetypes.get(name)

    def spec(**fields: object) -> ContextSpec:
        return sweep.Grid.of(
            dataclasses.replace(TRADING[name], **fields), archetype=archetype
        ).required_context()

    assert 21 not in spec().atr_periods
    assert 21 not in spec(breakeven_at=1.0).atr_periods
    assert (
        21
        in spec(breakeven_at=1.0, breakeven_unit=bracket.BREAKEVEN_ATR, breakeven_atr_period=21).atr_periods
    )


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


def first_move(params: ArchetypeParams, data: Dataset, rows: FloatArray) -> tuple[int, float]:
    """Return the first close at which the trigger held for the position ``rows`` were legs of, and its level.

    ``(-1, nan)`` where it never held before the last leg left.
    """
    trade = trade_of(rows)
    the_rule = filters.breakeven(data, params)
    bars = bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat)
    costs = COSTS._replace(tick_size=MNQ.tick_size)
    # DeadCatBounce has no field for it: its NinjaScript always rounds.
    fills = SNAPPED._replace(round_targets=getattr(params, "round_targets", True))
    for bar in range(trade.entry_bar, int(rows[:, C_EXIT_BAR].max())):
        moved_to = bracket.breakeven_level(the_rule, trade, bars, bar, costs, fills)
        if not math.isnan(moved_to):
            return bar, moved_to

    return -1, math.nan


def by_entry(matrix: FloatArray) -> dict[int, FloatArray]:
    return {int(bar): matrix[matrix[:, C_ENTRY_BAR] == bar] for bar in np.unique(matrix[:, C_ENTRY_BAR])}


@pytest.mark.parametrize("arm", sorted(ARMS))
@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_every_stop_exit_after_the_trigger_is_at_the_level_or_gapped_through_it(
    bars: pd.DataFrame, loop: str, arm: str
) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    params = dataclasses.replace(base, **ARMS[arm])
    data = prepared(bars, params, archetype)
    legs = archetype.legs(data, params, MNQ)
    at_the_level = 0
    for rows in by_entry(legs.matrix[: legs.count]).values():
        moved_at, moved_to = first_move(params, data, rows)
        if moved_at < 0:
            continue

        stopped = rows[(rows[:, C_EXIT_REASON] == EXIT_STOP) & (rows[:, C_EXIT_BAR] > moved_at)]
        for leg in stopped:
            d, exit_price, exit_bar = leg[C_DIRECTION], leg[C_EXIT_PRICE], int(leg[C_EXIT_BAR])
            gapped = d * (data.open[exit_bar] - moved_to) < 0 and np.isclose(exit_price, data.open[exit_bar])
            assert d * (exit_price - moved_to) >= -1e-9 or gapped, (
                f"entry bar {int(leg[C_ENTRY_BAR])} left at {exit_price} below its level {moved_to}"
            )
            at_the_level += int(np.isclose(exit_price, moved_to))

    assert at_the_level > 0, "no stop ever left at the level, so the test proves nothing"


@pytest.mark.parametrize("arm", sorted(ARMS))
@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_a_trade_whose_trigger_never_held_is_left_exactly_as_it_was(
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
        if entry_bar not in on or first_move(params, data, rows)[0] >= 0:
            continue

        untouched += 1
        # A trade's id counts the trades before it, which the rule may have changed.
        before, after = (np.delete(legs, C_TRADE_ID, axis=1) for legs in (rows, on[entry_bar]))
        assert np.array_equal(before, after, equal_nan=True), f"entry bar {entry_bar} moved"

    assert untouched > 0, "every trade's trigger held, so the test proves nothing"


@pytest.mark.parametrize("loop", sorted(EVERY_LOOP))
def test_a_rule_that_never_fires_leaves_every_trade_as_it_was(bars: pd.DataFrame, loop: str) -> None:
    name, base = EVERY_LOOP[loop]
    archetype = archetypes.get(name)
    never = dataclasses.replace(base, breakeven_at=1e9)
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


def test_the_breakeven_and_an_early_exit_both_act_in_one_run(bars: pd.DataFrame) -> None:
    """The ratchet alone stops some legs out at their entry, so the breakeven has to add to that count."""
    early_only = dataclasses.replace(TRADING["DeadCatBounce"], early_exit_bars=3)
    both = dataclasses.replace(early_only, **ARMS["0.05R on the close"])
    data = prepared(bars, both, archetypes.DEADCATBOUNCE)
    legs = archetypes.DEADCATBOUNCE.legs(data, both, MNQ)
    assert (legs.matrix[: legs.count, C_EXIT_REASON] == EXIT_EARLY).any()
    assert stopped_at_entry(both, data) > stopped_at_entry(early_only, data)


# -- the registry and the sweep ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_breakeven_setting_is_dead_without_the_trigger(name: str) -> None:
    archetype = archetypes.get(name)
    with pytest.raises(sweep.SweepError, match=r"breakeven_on \(inert while breakeven_at is 0.0\)"):
        sweep.Grid.of(TRADING[name], archetype=archetype, breakeven_on=[0, 1])

    on = dataclasses.replace(TRADING[name], breakeven_at=1.0)
    assert (
        len(sweep.Grid.of(on, archetype=archetype, breakeven_on=[0, 1], breakeven_offset_ticks=[0, 2])) == 4
    )


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_atr_period_is_dead_unless_the_trigger_is_in_atrs(name: str) -> None:
    archetype = archetypes.get(name)
    in_r = dataclasses.replace(TRADING[name], breakeven_at=1.0)
    with pytest.raises(sweep.SweepError, match=r"breakeven_atr_period \(inert while breakeven_unit is 0\)"):
        sweep.Grid.of(in_r, archetype=archetype, breakeven_atr_period=[14, 21])

    in_atr = dataclasses.replace(in_r, breakeven_unit=bracket.BREAKEVEN_ATR)
    assert len(sweep.Grid.of(in_atr, archetype=archetype, breakeven_atr_period=[14, 21])) == 2


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
def test_a_breakeven_row_leaves_every_reconciled_port(
    archetype: archetypes.Archetype, params: ArchetypeParams, arm: str
) -> None:
    assert archetype.tier2_for(params) is Tier2Status.RECONCILED
    assert archetype.tier2_for(dataclasses.replace(params, **ARMS[arm])) is Tier2Status.TIER1_ONLY


def test_an_original_archetype_stays_tier_1_only_with_a_breakeven_or_not() -> None:
    assert archetypes.EMACROSSOVER.tier2_for(EmaCrossoverParams()) is Tier2Status.TIER1_ONLY
    assert archetypes.EMACROSSOVER.tier2_for(EmaCrossoverParams(breakeven_at=1.0)) is Tier2Status.TIER1_ONLY
