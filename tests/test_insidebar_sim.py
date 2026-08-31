"""InsideBar simulation tests on hand-built bars.

`InsideBar.cs` exists, but no Strategy Analyzer trade list has been diffed against this port
yet, so these pin the port against the **C#** rather than against NT8. Three of them cover
what nothing else in the project reaches: ``IsFillLimitOnTouch = true``, a bracket whose stop
and target are anchored to two different bars, and a no-entry window before the session close.
Each rule and the evidence behind it: ``docs/nt8-fidelity.md`` §M22.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import context, sessions, sweep
from nqbt.context import ContextError
from nqbt.instruments import MNQ, NQ
from nqbt.sim import bracket, insidebar
from nqbt.sim.insidebar import insidebar_direction, insidebar_signal, run_insidebar
from nqbt.sim.types import InsideBarParams
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25


def simulate(
    rows,
    signal_at=(),
    max_rows=None,
    direction=LONG,
    atr=4.0,
    force_flat_at=(),
    quantities=(4,),
    atr_multiplier=1.0,
    tp_multiplier=1.0,
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    bars_required=-1,
    block_entry_at_close=True,
    fill_limit_on_touch=True,
    ambiguity_policy=0,
    round_targets=True,
):
    """Simulate hand-written OHLC rows.

    ``signal_at`` lists the bars whose close schedules an entry and ``direction`` is the side
    every bar is on. ``bars_required`` defaults below zero so that bar 0 can signal: the C#
    returns on ``CurrentBars[0] <= BarsRequiredToTrade``, not on ``<``.
    """
    arr = np.asarray(rows, dtype=np.float64)
    o, h, low, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    signal = np.zeros(n, dtype=np.bool_)
    for i in signal_at:
        signal[i] = True
    direction_at = np.full(n, direction, dtype=np.float64)
    force_flat = np.zeros(n, dtype=np.bool_)
    for i in force_flat_at:
        force_flat[i] = True

    out = (
        bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
        if max_rows is None
        else np.zeros((max_rows, N_COLUMNS), dtype=np.float64)
    )
    count = insidebar.simulate_insidebar(
        bracket.Bars(o, h, low, c, force_flat),
        signal,
        direction_at,
        np.full(n, atr, dtype=np.float64) if np.isscalar(atr) else np.asarray(atr, dtype=np.float64),
        np.asarray(quantities, dtype=np.int64),
        bracket.Costs(TICK, instrument.point_value, commission, slippage),
        bracket.FillRules(fill_limit_on_touch, ambiguity_policy, round_targets),
        insidebar.InsideBarRules(
            atr_multiplier=atr_multiplier,
            tp_multiplier=tp_multiplier,
            bars_required=bars_required,
            block_entry_at_session_close=block_entry_at_close,
        ),
        out,
    )
    return count, out


def run(rows, signal_at=(), **kwargs):
    """:func:`simulate` with the count checked and the matrix turned into a trade log."""
    count, out = simulate(rows, signal_at, **kwargs)
    assert count >= 0, "trade buffer overflowed"
    return validate(trades_to_frame(out, count, instrument=kwargs.get("instrument", MNQ).symbol))


FLAT = [(100.0, 100.5, 99.5, 100.0)] * 6


# -- the entry, which is M18's market-on-next-open -----------------------------

# Every signal below sits at bar 1 or later: the stop anchors to the bar *before* the signal
# bar, so bar 0 can never carry one. The loop refuses it rather than wrapping the index.


def test_the_entry_fills_at_the_next_bars_open_without_touching_anything() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: the stop's anchor
            (100.0, 100.5, 99.5, 100.0),  # 1: signal
            (102.0, 102.5, 101.5, 102.0),  # 2: gapped up; a stop-market entry would miss
            *FLAT,
        ],
        signal_at=[1],
        atr=40.0,
    )
    assert trades["entry_bar"].iloc[0] == 2
    assert trades["entry_price"].iloc[0] == pytest.approx(102.0)


def test_a_signal_on_the_first_bar_is_refused_rather_than_wrapping_the_anchor() -> None:
    """Bar 0 has no bar behind it, and numba would index the *last* bar instead.

    Unreachable through :func:`insidebar_signal`, which needs an inside bar and a mother bar
    behind the signal -- but the random-entry arm injects a signal wherever it likes.
    """
    assert run(FLAT, signal_at=[0], atr=40.0).empty


def test_slippage_on_the_entry_takes_the_direction_sign() -> None:
    long_side = run(FLAT, signal_at=[1], slippage=2.0, direction=LONG, atr=40.0)
    short_side = run(FLAT, signal_at=[1], slippage=2.0, direction=SHORT, atr=40.0)
    assert long_side["entry_price"].iloc[0] == pytest.approx(100.0 + 2 * TICK)
    assert short_side["entry_price"].iloc[0] == pytest.approx(100.0 - 2 * TICK)


def test_the_order_fills_at_the_flatten_point_and_is_flattened_there() -> None:
    """NT8 fills the resting order and only then flattens -- ``docs/nt8-fidelity.md``,
    "A resting entry fills on the force-flat bar, and is flattened at its close"."""
    trades = run(FLAT, signal_at=[1], force_flat_at=[2], atr=40.0)
    assert list(trades["entry_bar"].unique()) == [2]
    assert set(trades["exit_reason"]) == {"session_close"}
    assert list(trades["exit_bar"].unique()) == [2]
    assert trades["exit_price"].unique() == pytest.approx([100.0])  # bar 2's close


def test_a_signal_on_a_force_flat_bar_is_blocked_when_asked() -> None:
    assert run(FLAT, signal_at=[1], force_flat_at=[1], atr=40.0).empty
    assert not run(FLAT, signal_at=[1], force_flat_at=[1], block_entry_at_close=False, atr=40.0).empty


def test_a_signal_while_already_in_a_position_does_not_pyramid() -> None:
    """Flat-to-flat, which is what ``Position.MarketPosition != Flat`` asks for.

    The C# read ``PositionAccount`` until the reconciliation caught it -- that property never
    leaves Flat in Strategy Analyzer, so NT8 reversed instead. ``docs/nt8-fidelity.md`` §M22,
    "The position guard has to read ``Position``".
    """
    trades = run(FLAT, signal_at=[1, 4], atr=40.0)
    assert list(trades["entry_bar"].unique()) == [2]


def test_bars_required_to_trade_costs_one_more_bar_than_the_other_ports() -> None:
    """``CurrentBars[0] <= BarsRequiredToTrade`` returns, where both ports use ``<``.

    An off-by-one here is invisible in aggregate and shifts every result by one bar of
    warm-up, so the boundary is pinned rather than assumed to mirror the other two.
    """
    assert run(FLAT, signal_at=[2], bars_required=2, atr=40.0).empty
    assert not run(FLAT, signal_at=[2], bars_required=1, atr=40.0).empty


# -- the bracket, and the two bars OnExecutionUpdate reads it from -------------

# Established leg-for-leg against an MNQ 03-24 trade list, against an inference that had both
# terms one bar later: ``OnExecutionUpdate`` runs with the **signal** bar still current, so
# ATR[0] is the signal bar's and Low[1] is the bar before it -- the inside bar.


def test_the_stop_sits_an_atr_multiple_beyond_the_inside_bars_low() -> None:
    trades = run(FLAT, signal_at=[1], atr=4.0, atr_multiplier=2.5)
    leg = trades.iloc[0]
    assert leg["initial_stop"] == pytest.approx(99.5 - 2.5 * 4.0)
    assert leg["risk_points"] == pytest.approx(100.0 - (99.5 - 10.0))


def test_the_stop_is_anchored_to_the_inside_bar_not_the_signal_bar_or_the_fill_bar() -> None:
    """``Low[1]`` in ``OnExecutionUpdate``, where ``[0]`` is the signal bar.

    Three distinct lows, so the assertion says which of the three bars was read. The trade
    list put this at 100% of stop exits; the other two candidates matched none of them.
    """
    trades = run(
        [
            (100.0, 100.5, 95.0, 100.0),  # 0: the inside bar -- Low[1] at execution
            (100.0, 100.5, 93.0, 100.0),  # 1: signal
            (100.0, 100.5, 90.0, 100.0),  # 2: the fill bar
            *FLAT,
        ],
        signal_at=[1],
        atr=1.0,
        atr_multiplier=1.0,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(94.0), "read 93 or 90, not 95"


def test_the_stop_mirrors_onto_the_inside_bars_high_for_a_short() -> None:
    trades = run(
        [
            (100.0, 105.0, 99.5, 100.0),  # 0: the inside bar
            (100.0, 107.0, 99.5, 100.0),  # 1: signal
            (100.0, 110.0, 99.5, 100.0),  # 2: the fill bar
            *FLAT,
        ],
        signal_at=[1],
        direction=SHORT,
        atr=1.0,
        atr_multiplier=1.0,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(106.0)


def test_the_target_is_one_atr_from_the_fill_price_not_from_the_signal_close() -> None:
    """``target = price + atr``, where ``price`` is the execution's own fill."""
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: anchor
            (100.0, 100.5, 99.5, 100.0),  # 1: signal, closing at 100
            (108.0, 108.5, 107.5, 108.0),  # 2: fills at 108, so the target is 112
            *[(108.0, 108.5, 107.5, 108.0)] * 5,
        ],
        signal_at=[1],
        atr=4.0,
        atr_multiplier=10.0,
    )
    assert trades["target_price"].iloc[0] == pytest.approx(112.0)


def test_the_tp_multiplier_scales_the_target_and_leaves_the_stop_alone() -> None:
    """``target = price + TPMultiplier * atr``, the property ``InsideBar.cs`` did not have.

    Its default is the bare 1x the C# hardcoded, so a stored result reproduces unchanged --
    ``docs/nt8-fidelity.md`` §M22.
    """
    rows = [*FLAT, *FLAT]
    at_one = run(rows, signal_at=[1], atr=4.0, atr_multiplier=10.0)
    at_three = run(rows, signal_at=[1], atr=4.0, atr_multiplier=10.0, tp_multiplier=3.0)
    at_a_quarter = run(rows, signal_at=[1], atr=4.0, atr_multiplier=10.0, tp_multiplier=0.25)
    # Entry is bar 2's open at 100, so the target sits tp_multiplier * 4 points above it.
    assert at_one["target_price"].iloc[0] == pytest.approx(104.0)
    assert at_three["target_price"].iloc[0] == pytest.approx(112.0)
    assert at_a_quarter["target_price"].iloc[0] == pytest.approx(101.0)
    assert at_three["initial_stop"].iloc[0] == pytest.approx(at_one["initial_stop"].iloc[0])
    assert at_a_quarter["initial_stop"].iloc[0] == pytest.approx(at_one["initial_stop"].iloc[0])


def test_the_scaled_target_mirrors_below_the_fill_for_a_short() -> None:
    trades = run(
        [*FLAT, *FLAT], signal_at=[1], atr=4.0, atr_multiplier=10.0, tp_multiplier=2.0, direction=SHORT
    )
    assert trades["target_price"].iloc[0] == pytest.approx(92.0)


def test_a_target_the_multiplier_pulls_inside_the_bar_is_taken_there() -> None:
    """Scaling the target moves which bar it fills on, not only where it is written."""
    rows = [
        (100.0, 100.5, 99.5, 100.0),  # 0: anchor
        (100.0, 100.5, 99.5, 100.0),  # 1: signal
        (100.0, 101.0, 99.5, 100.0),  # 2: fills at 100 and reaches 101
        *FLAT,
    ]
    assert run(rows, signal_at=[1], atr=4.0, atr_multiplier=10.0)["exit_reason"].iloc[0] == "end_of_data"
    reachable = run(rows, signal_at=[1], atr=4.0, atr_multiplier=10.0, tp_multiplier=0.25)
    assert reachable["exit_reason"].iloc[0] == "target"
    assert reachable["exit_bar"].iloc[0] == 2


def test_a_tp_multiplier_at_or_below_zero_is_refused() -> None:
    """A target at or behind the fill is not a profit target, the way a zero stop is not one."""
    for value in (0.0, -1.0):
        with pytest.raises(ValueError, match="tp_multiplier must be > 0"):
            InsideBarParams(tp_multiplier=value)


def test_the_target_multiplier_is_a_sweepable_axis() -> None:
    """What #197 was for: the campaign could move the stop across the grid and not the target."""
    combinations = sweep.Grid.of(InsideBarParams(), tp_multiplier=[1.0, 2.0, 4.0]).combinations()
    assert {p.tp_multiplier for p in combinations} == {1.0, 2.0, 4.0}


def test_the_bracket_reads_the_signal_bars_atr_not_the_fill_bars() -> None:
    """``ATR(ATRLength)[0]`` in ``OnExecutionUpdate``, where ``[0]`` is the signal bar.

    The port originally read the fill bar's, on the reasoning that the fill lands on the next
    bar's open so the series must have advanced by then. The trade list says otherwise: the
    signal bar's ATR reproduces NT8's target on 99.75% of target exits and the fill bar's on
    19%. The correct reading is also the one that reads no bar the fill could not have seen.
    """
    atr = np.full(len(FLAT), 1.0)
    atr[1] = 5.0  # the signal bar
    atr[2] = 10.0  # the fill bar
    trades = run(FLAT, signal_at=[1], atr=atr, atr_multiplier=1.0)
    leg = trades.iloc[0]
    assert leg["target_price"] == pytest.approx(105.0), "target read the fill bar's ATR"
    assert leg["initial_stop"] == pytest.approx(99.5 - 5.0), "stop read the fill bar's ATR"


def test_the_stop_lands_on_the_tick_grid_too() -> None:
    """An ATR multiple puts the stop off the grid, where both ports' tick offsets cannot.

    NT8 snaps a submitted price whatever the script asks for, and an exchange takes a stop no
    more than it takes a target at a half tick -- ``docs/nt8-fidelity.md``, "Targets snap to
    the tick grid". Snapped before the risk, so ``r_multiple`` measures the real stop.
    """
    trades = run(FLAT, signal_at=[1], atr=1.1, atr_multiplier=1.0)
    leg = trades.iloc[0]
    assert leg["initial_stop"] == pytest.approx(98.5), "99.5 - 1.1 = 98.4, which is off the grid"
    assert leg["risk_points"] == pytest.approx(1.5)

    raw = run(FLAT, signal_at=[1], atr=1.1, atr_multiplier=1.0, round_targets=False)
    assert raw["initial_stop"].iloc[0] == pytest.approx(98.4)


def test_targets_land_on_the_tick_grid_unless_that_is_switched_off() -> None:
    rounded = run(FLAT, signal_at=[1], atr=3.6, atr_multiplier=10.0)
    raw = run(FLAT, signal_at=[1], atr=3.6, atr_multiplier=10.0, round_targets=False)
    assert rounded["target_price"].iloc[0] == pytest.approx(103.5)
    assert raw["target_price"].iloc[0] == pytest.approx(103.6)


def test_an_entry_whose_stop_is_already_through_the_fill_is_skipped() -> None:
    """A stop at or through the price it protects is not a stop order.

    Reachable here for M18's reason: the fill is wherever the next bar opens, so a gap can put
    the inside bar's low on the wrong side of it.
    """
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: the anchor; stop at 99.5 - 0.1, snapped to 99.5
            (100.0, 100.5, 99.5, 100.0),  # 1: signal
            (99.0, 99.5, 98.5, 99.0),  # 2: opens below its own stop
            *FLAT,
        ],
        signal_at=[1],
        atr=0.1,
        atr_multiplier=1.0,
    )
    assert trades.empty


def test_the_whole_position_rides_on_one_leg() -> None:
    """``InsideBar.cs`` brackets the entry with one stop and one target; it never scales out."""
    trades = run(FLAT, signal_at=[1], atr=40.0, quantities=(4,))
    assert len(trades) == 1
    assert trades["leg"].iloc[0] == 1
    assert trades["quantity"].iloc[0] == 4


# -- IsFillLimitOnTouch, which this is the first archetype to set --------------


def test_a_target_touched_to_the_tick_fills_when_fill_limit_on_touch_is_set() -> None:
    """``IsFillLimitOnTouch = true``: ``high >= target``, where both ports need ``high >``.

    The `true` branch has existed as a sweep axis all along and no archetype's defaults reached
    it. ``docs/nt8-fidelity.md``, "Limit orders must trade *through*, not touch".
    """
    rows = [
        (100.0, 100.5, 99.5, 100.0),  # 0: anchor
        (100.0, 100.5, 99.5, 100.0),  # 1: signal
        (100.0, 100.5, 99.5, 100.0),  # 2: fill at 100, target at 101
        (100.0, 101.0, 99.5, 100.0),  # 3: high touches the target exactly
        *FLAT,
    ]
    touched = run(rows, signal_at=[1], atr=1.0, atr_multiplier=10.0, fill_limit_on_touch=True)
    through = run(rows, signal_at=[1], atr=1.0, atr_multiplier=10.0, fill_limit_on_touch=False)
    assert touched["exit_reason"].iloc[0] == "target"
    assert touched["exit_bar"].iloc[0] == 3
    assert through["exit_reason"].iloc[0] == "end_of_data"


def test_the_touch_rule_mirrors_onto_a_shorts_low() -> None:
    rows = [
        (100.0, 100.5, 99.5, 100.0),  # 0: anchor
        (100.0, 100.5, 99.5, 100.0),  # 1: signal
        (100.0, 100.5, 99.5, 100.0),  # 2: fill at 100, target at 99
        (100.0, 100.5, 99.0, 100.0),  # 3: low touches the target exactly
        *FLAT,
    ]
    touched = run(rows, signal_at=[1], direction=SHORT, atr=1.0, atr_multiplier=10.0)
    through = run(
        rows,
        signal_at=[1],
        direction=SHORT,
        atr=1.0,
        atr_multiplier=10.0,
        fill_limit_on_touch=False,
    )
    assert touched["exit_reason"].iloc[0] == "target"
    assert through["exit_reason"].iloc[0] == "end_of_data"


# -- the shared bracket engine is reached, not reimplemented -------------------


def test_the_stop_closes_the_position_and_pays_slippage() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: anchor; stop at 98.5
            (100.0, 100.5, 99.5, 100.0),  # 1: signal
            (100.0, 100.5, 99.5, 100.0),  # 2: fill at 100
            (100.0, 100.5, 98.0, 99.0),  # 3: trades through the stop
            *FLAT,
        ],
        signal_at=[1],
        atr=1.0,
        atr_multiplier=1.0,
        slippage=2.0,
    )
    leg = trades.iloc[0]
    assert leg["exit_reason"] == "stop"
    assert leg["exit_price"] == pytest.approx(98.5 - 2 * TICK)


def test_the_session_close_flattens_whatever_is_left() -> None:
    trades = run(FLAT, signal_at=[1], atr=40.0, force_flat_at=[4])
    leg = trades.iloc[0]
    assert leg["exit_reason"] == "session_close"
    assert leg["exit_bar"] == 4


def test_a_position_open_at_the_last_bar_is_liquidated_there() -> None:
    trades = run(FLAT, signal_at=[1], atr=40.0)
    leg = trades.iloc[0]
    assert leg["exit_reason"] == "end_of_data"
    assert leg["exit_bar"] == len(FLAT) - 1


def test_the_buffer_overflowing_is_reported_rather_than_written_past() -> None:
    count, _ = simulate(FLAT, signal_at=[1], atr=40.0, max_rows=0)
    assert count == -1


# -- the signal, over a real prepared dataset ----------------------------------


SESSION_CLOSE = "2024-01-16 22:00"
"""17:00 ET, and the last bar of every frame below. The session end is the observed last bar,
so without it a handful of hand-written rows would be a session ending wherever they stop."""


def frame(rows, start="2024-01-16 15:00") -> pd.DataFrame:
    """Hand-written bars on a minute index, stamped mid-session unless told otherwise.

    A copy of the final row is appended at :data:`SESSION_CLOSE` to close the session, so the
    rows a test wrote about are never the ones the flatten and the no-entry window act on.
    """
    arr = np.asarray(rows, dtype=np.float64)
    idx = pd.date_range(start, periods=len(arr), freq="min", tz="UTC")
    idx = idx.append(pd.DatetimeIndex([pd.Timestamp(SESSION_CLOSE, tz="UTC")]))
    arr = np.vstack([arr, arr[-1]])
    out = pd.DataFrame(
        {
            "open": arr[:, 0],
            "high": arr[:, 1],
            "low": arr[:, 2],
            "close": arr[:, 3],
            "volume": np.full(len(arr), 100.0),
        },
        index=idx,
    )
    out["trading_day"] = sessions.classify(idx).trading_day
    return out


def prepared(bars: pd.DataFrame, params: InsideBarParams):
    """The dataset the archetype's own ``ContextSpec`` asks for."""
    return context.prepare(bars, sweep.Grid.of(params).required_context())


def signalling(**overrides) -> InsideBarParams:
    """Short periods, so three real averages sit under a rising close on hand-built bars."""
    defaults = {
        "ema_period": 2,
        "fast_sma_period": 2,
        "slow_sma_period": 2,
        "atr_length": 2,
        "bars_required_to_trade": 0,
    }
    return InsideBarParams(**{**defaults, **overrides})


# Bar 0 is the mother bar, bar 1 is inside it, and bar 2's close breaks out above.
BREAKOUT = [
    (100.0, 110.0, 90.0, 100.0),
    (100.0, 105.0, 95.0, 101.0),
    (101.0, 120.0, 100.0, 115.0),
]


def test_the_breakout_signal_needs_an_inside_bar_a_break_and_the_averages() -> None:
    params = signalling()
    data = prepared(frame(BREAKOUT), params)
    assert list(insidebar_signal(data, params))[: len(BREAKOUT)] == [False, False, True]
    assert insidebar_direction(data, params)[2] == LONG


def test_the_breakout_is_measured_against_the_mother_bar_two_back() -> None:
    """The inside bar's own extremes are never the threshold -- ``High[2]``, not ``High[1]``."""
    params = signalling()
    # Closing above the inside bar's high but below the mother bar's is not a break.
    rows = [*BREAKOUT[:2], (101.0, 120.0, 100.0, 108.0)]
    assert not insidebar_signal(prepared(frame(rows), params), params)[2]


def test_the_error_margin_scales_with_the_mother_bars_range() -> None:
    params = signalling(error_margin=0.5)  # 110 + 20 * 0.5 = 120, which the close misses
    assert not insidebar_signal(prepared(frame(BREAKOUT), params), params)[2]

    at_zero = signalling(error_margin=0.0)
    rows = [*BREAKOUT[:2], (101.0, 120.0, 100.0, 110.1)]
    assert insidebar_signal(prepared(frame(rows), at_zero), at_zero)[2]


def test_a_bar_that_is_not_inside_its_predecessor_produces_no_signal() -> None:
    params = signalling()
    rows = [(100.0, 110.0, 90.0, 100.0), (100.0, 110.0, 95.0, 101.0), *BREAKOUT[2:]]
    assert not insidebar_signal(prepared(frame(rows), params), params)[2]


def test_the_short_side_mirrors_the_long_one() -> None:
    params = signalling()
    rows = [
        (100.0, 110.0, 90.0, 100.0),
        (100.0, 105.0, 95.0, 99.0),
        (99.0, 100.0, 80.0, 85.0),  # closes below 90 - 20 * 0.01
    ]
    data = prepared(frame(rows), params)
    assert list(insidebar_signal(data, params))[: len(rows)] == [False, False, True]
    assert insidebar_direction(data, params)[2] == SHORT


def test_a_close_equal_to_an_average_fails_both_trend_gates() -> None:
    """``InsideBar.cs`` writes ``Close[0] > ema[0]`` positively, so equality is a rejection.

    The two ports port their gates as the negation of the C#'s rejection, which makes
    equality *pass*; this one does not mirror them, which is why it reads the raw averages
    rather than the shared boolean grid.
    """
    params = signalling(ema_period=1, fast_sma_period=1, slow_sma_period=1)
    data = prepared(frame(BREAKOUT), params)
    assert data.ma_values("ema", 1)[2] == pytest.approx(data.close[2]), "premise gone; rewrite"
    assert data.ma_gate("ema", 1, above=True)[2], "the boolean grid would have admitted it"
    assert not insidebar_signal(data, params)[2]


# -- the no-entry window before the close --------------------------------------

# The same three bars, stamped so the breakout closes exactly one hour before 17:00 ET.
LAST_HOUR = "2024-01-16 20:58"


def test_no_entry_inside_the_window_before_the_session_close() -> None:
    params = signalling()
    data = prepared(frame(BREAKOUT, start=LAST_HOUR), params)
    assert not insidebar_signal(data, params)[2], "an hour exactly is inside the window"
    assert not data.force_flat[2], "this is not the force-flat rule wearing another name"


def test_the_window_is_a_parameter_rather_than_the_ninjascripts_hour() -> None:
    inside = signalling(no_entry_minutes_before_close=61)
    outside = signalling(no_entry_minutes_before_close=59)
    assert not insidebar_signal(prepared(frame(BREAKOUT, start=LAST_HOUR), inside), inside)[2]
    assert insidebar_signal(prepared(frame(BREAKOUT, start=LAST_HOUR), outside), outside)[2]


def test_a_window_of_zero_switches_the_rule_off_and_builds_no_clock() -> None:
    """Skipped entirely at its off value, like every other gate that can pass no mask."""
    params = signalling(no_entry_minutes_before_close=0)
    data = prepared(frame(BREAKOUT, start=LAST_HOUR), params)
    assert data.seconds_to_session_end is None
    assert insidebar_signal(data, params)[2]


def test_reading_the_window_without_declaring_the_clock_raises() -> None:
    params = signalling()
    bars = frame(BREAKOUT, start=LAST_HOUR)
    spec = sweep.Grid.of(params).required_context()
    without = context.prepare(bars, replace(spec, needs_session_clock=False))
    with pytest.raises(ContextError, match="needs_session_clock"):
        insidebar_signal(without, params)


# -- end to end ----------------------------------------------------------------


def test_a_run_produces_a_valid_leg_log_on_both_instruments() -> None:
    """Everything monetary goes through ``instruments.py``: same geometry, ten times the P&L."""
    params = signalling(atr_multiplier=2.0)
    bars = frame([*BREAKOUT, *[(115.0, 116.0, 114.0, 115.0)] * 4])
    data = prepared(bars, params)

    mnq = run_insidebar(data, params, MNQ)
    nq = run_insidebar(data, params, NQ)
    assert len(mnq) == 1
    assert mnq["entry_bar"].iloc[0] == 3
    assert nq["entry_price"].iloc[0] == pytest.approx(mnq["entry_price"].iloc[0])
    assert nq["gross_pnl"].iloc[0] == pytest.approx(mnq["gross_pnl"].iloc[0] * 10.0)
