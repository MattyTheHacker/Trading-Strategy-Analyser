"""DeadCatBounce simulation tests on hand-built bars.

Every expectation here is computed by hand from DeadCatBounce.cs semantics. Prices are
kept small and round so the arithmetic is checkable by eye.
"""

import numpy as np
import pytest

from nqbt.instruments import MNQ, NQ
from nqbt.sim import bracket, deadcat
from nqbt.sim.types import DeadCatParams
from nqbt.trades import LONG, SHORT

TICK = 0.25
OFFSET = 2 * TICK  # stop sits 2 ticks beyond the reference high


def run(
    rows,
    signal_at=(),
    *,
    force_flat_at=(),
    quantities=(1, 1, 1, 1),
    targets=(1.0, 1.5, 2.0, np.nan),
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    bars_required=0,
    min_reward_risk=0.0,
    ratchet_lag=1,
    entry_offset=0.0,  # 0 => trigger is just Low[0]; tests opt in explicitly
    tp_multiplier=1.0,
    max_risk_ticks=1e9,
    block_entry_at_close=True,
    fill_limit_on_touch=True,  # tests target exact prices; opt out explicitly
    ambiguity_policy=0,
    direction=SHORT,
    ratchet_offset_ticks=2.0,  # DeadCatBounce.cs reapplies the entry's stop offset
    round_targets=True,  # DeadCatBounce.cs calls RoundToTickSize; PBG does not
):
    """Simulate hand-written OHLC rows. ``signal_at`` lists signal bar indices."""
    arr = np.asarray(rows, dtype=np.float64)
    o, h, l, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    signal = np.zeros(n, dtype=np.bool_)
    for i in signal_at:
        signal[i] = True
    force_flat = np.zeros(n, dtype=np.bool_)
    for i in force_flat_at:
        force_flat[i] = True

    out = bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
    count = deadcat.simulate_deadcat(
        o,
        h,
        l,
        c,
        signal,
        force_flat,
        np.asarray(quantities, dtype=np.int64),
        np.asarray(targets, dtype=np.float64),
        TICK,
        instrument.point_value,
        2.0,
        entry_offset,
        tp_multiplier,
        max_risk_ticks,
        commission,
        slippage,
        bars_required,
        min_reward_risk,
        ratchet_lag,
        ratchet_offset_ticks,
        block_entry_at_close,
        fill_limit_on_touch,
        ambiguity_policy,
        direction,
        round_targets,
        out,
    )
    assert count >= 0, "trade buffer overflowed"

    from nqbt import trades as trades_mod

    return trades_mod.validate(trades_mod.trades_to_frame(out, count, instrument=instrument.symbol))


# -- entry mechanics ----------------------------------------------------------


def test_signal_places_an_order_that_fills_on_the_next_bar() -> None:
    # Signal bar: low 100, high 104 -> trigger 100, stop 104.5, risk 4.5.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal
            (101, 102, 99, 100),  # 1: trades down through 100 -> fill at 100
            (100, 101, 99, 100),
        ],
        signal_at=[0],
    )
    assert trades["entry_bar"].nunique() == 1
    assert trades["entry_bar"].iloc[0] == 1
    assert trades["entry_price"].iloc[0] == pytest.approx(100.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(104.5)
    assert trades["risk_points"].iloc[0] == pytest.approx(4.5)


def test_unfilled_order_is_cancelled_after_one_bar() -> None:
    # NT8's managed approach cancels an unfilled entry at the next bar's close; it does
    # not rest as GTC. Bar 1 never reaches 100, and bar 2 dipping to 99 must not fill it.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100
            (102, 103, 101, 102),  # 1: never touches 100 -> order cancelled
            (101, 102, 99, 100),  # 2: would have filled a resting order
        ],
        signal_at=[0],
    )
    assert trades.empty


def test_gap_through_the_trigger_fills_at_the_open() -> None:
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100
            (98, 99, 97, 98),  # 1: opens below the trigger
        ],
        signal_at=[0],
    )
    assert trades["entry_price"].iloc[0] == pytest.approx(98.0)


def test_touching_the_trigger_exactly_fills() -> None:
    trades = run(
        [(102, 104, 100, 101), (101, 102, 100, 101)],
        signal_at=[0],
    )
    assert len(trades) > 0
    assert trades["entry_price"].iloc[0] == pytest.approx(100.0)


def test_a_buy_stop_at_the_market_is_never_submitted() -> None:
    # PullBackAndGo triggers on a bare High[0]. When the signal bar closes on its high the
    # trigger equals the market it would be submitted into, which is not a stop order at
    # all -- NT8 declines it. This was 86 of the 502 PullBackAndGo trades on MNQ 03-24,
    # and the signal bar closed on its high in 86 of 86 of them against 2 of 416 taken.
    rows = [
        (101, 104, 100, 104),  # 0: signal, closes ON its high -> trigger 104 == market
        (104, 106, 103, 105),  # 1: would have filled easily
    ]
    assert len(run(rows, signal_at=[0], direction=LONG)) == 0

    # One tick of daylight between the close and the high and it is a real stop order.
    rows[0] = (101, 104, 100, 103.75)
    assert len(run(rows, signal_at=[0], direction=LONG)) == 4


def test_a_sell_stop_at_the_market_is_never_submitted_either() -> None:
    rows = [
        (104, 105, 100, 100),  # 0: signal, closes ON its low -> trigger 100 == market
        (100, 101, 98, 99),  # 1: would have filled easily
    ]
    assert len(run(rows, signal_at=[0])) == 0

    # DeadCatBounce is immune by construction: its trigger is min(Low[0], Close[0] - 2
    # ticks), so the cap puts it 2 ticks under the close on exactly the bars that would
    # otherwise be unsubmittable. No DeadCatBounce signal in MNQ 03-24's 132,454 bars
    # has a trigger at or above its close, which is why this rule never showed up there.
    assert len(run(rows, signal_at=[0], entry_offset=2.0)) == 4


def test_no_new_signal_is_taken_while_in_a_position() -> None:
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal
            (101, 102, 99, 100),  # 1: fill at 100
            (100, 101, 99, 100),  # 2: signal ignored, already short
            (100, 101, 99, 100),
        ],
        signal_at=[0, 2],
    )
    assert trades["trade_id"].nunique() == 1


def test_bars_required_to_trade_suppresses_early_signals() -> None:
    rows = [(102, 104, 100, 101), (101, 102, 99, 100)] * 3
    assert run(rows, signal_at=[0], bars_required=0).empty is False
    assert run(rows, signal_at=[0], bars_required=4).empty


# -- exits --------------------------------------------------------------------


def test_targets_fill_at_their_price_and_scale_out_independently() -> None:
    # Entry 100, stop 104.5, risk 4.5. Targets: 95.5 (1R), 93.25 (1.5R), 91 (2R).
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill at 100
            (100, 101, 95.5, 96),  # 2: reaches the 1R target only
            (96, 97, 91, 92),  # 3: reaches 1.5R and 2R
        ],
        signal_at=[0],
    )
    by_leg = trades.set_index("leg")
    assert by_leg.loc[1, "exit_price"] == pytest.approx(95.5)
    assert by_leg.loc[1, "exit_bar"] == 2
    assert by_leg.loc[2, "exit_price"] == pytest.approx(93.25)
    assert by_leg.loc[3, "exit_price"] == pytest.approx(91.0)
    assert by_leg.loc[1, "r_multiple"] == pytest.approx(1.0)
    assert by_leg.loc[3, "r_multiple"] == pytest.approx(2.0)
    assert list(by_leg.loc[[1, 2, 3], "exit_reason"]) == ["target"] * 3
    # Leg 4 is the runner: no target of its own, so it survives to the end of the data.
    assert np.isnan(by_leg.loc[4, "target_price"])
    assert by_leg.loc[4, "exit_reason"] == "end_of_data"
    assert by_leg.loc[4, "exit_price"] == pytest.approx(92.0)


def test_stop_exits_every_remaining_leg_at_once() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill at 100, stop 104.5
            (101, 104.5, 100, 104),  # 2: touches the stop
        ],
        signal_at=[0],
    )
    assert len(trades) == 4
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([104.5])
    assert trades["r_multiple"].unique() == pytest.approx([-1.0])


def test_stop_wins_when_a_bar_contains_both_stop_and_target() -> None:
    # The worst-case assumption, and the bar is flagged so its cost stays measurable.
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill at 100, stop 104.5, 1R target 95.5
            (101, 104.5, 91, 100),  # 2: spans stop and every target
        ],
        signal_at=[0],
    )
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["ambiguous_bar"].all()


def test_unambiguous_exits_are_not_flagged() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),
            (100, 101, 95.5, 96),  # target only, stop nowhere near
        ],
        signal_at=[0],
    )
    assert not trades["ambiguous_bar"].any()


def test_stop_can_fire_on_the_entry_bar() -> None:
    # Entry at the signal bar's low, stop above its high: one wide bar reaches both.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100, stop 104.5
            (101, 105, 99, 104),  # 1: fills at 100 then runs to 105
        ],
        signal_at=[0],
    )
    assert len(trades) == 4
    assert set(trades["exit_reason"]) == {"stop"}
    assert (trades["entry_bar"] == trades["exit_bar"]).all()
    assert (trades["bars_held"] == 0).all()


def test_a_bar_that_gaps_through_the_stop_fills_at_its_open() -> None:
    # A stop is a market order once triggered, so a bar that opens beyond it offers no
    # trade at the stop level. Filling at the stop anyway was worth $222.50 of a $292.50
    # result over the 1,664-leg PullBackAndGo reconciliation; NT8 fills at the open.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100, stop 104.5
            (101, 102, 100, 101),  # 1: fills at 100, stop stays 104.5
            (106, 107, 105, 106),  # 2: opens 1.5 above the stop -- gapped through
        ],
        signal_at=[0],
    )
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([106.0])  # not 104.5


def test_a_long_gapping_through_its_stop_fills_at_the_open_too() -> None:
    trades = run(
        [
            (101, 104, 100, 103),  # 0: signal, trigger 104, stop 99.5
            (103, 105, 102, 104),  # 1: fills at 104, stop stays 99.5
            (98, 99, 97, 98),  # 2: opens 1.5 below the stop -- gapped through
        ],
        signal_at=[0],
        direction=LONG,
    )
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([98.0])  # not 99.5


def test_the_entry_bar_never_uses_the_gap_rule() -> None:
    # The position did not exist at this bar's open, so an open beyond the initial stop
    # says nothing: price still had to travel down to the trigger to open the short at
    # all, and only then back up to the stop -- which it reaches at the stop's own price.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100, stop 104.5
            (105, 106, 99, 100),  # 1: opens above the stop, dips to fill, then runs
        ],
        signal_at=[0],
    )
    assert trades["entry_price"].unique() == pytest.approx([100.0])
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([104.5])  # not the 105 open


def test_session_close_flattens_whatever_is_left() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill at 100
            (100, 101, 99, 99.5),  # 2: force flat here
        ],
        signal_at=[0],
        force_flat_at=[2],
    )
    assert len(trades) == 4
    assert set(trades["exit_reason"]) == {"session_close"}
    assert trades["exit_price"].unique() == pytest.approx([99.5])


def test_position_open_when_the_data_ends_is_liquidated_not_dropped() -> None:
    # The series can stop mid-session, so an open position must still be accounted for.
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 99, 100),  # 1: fill at 100
            (100, 101, 99, 99.5),  # 2: data ends with the position still open
        ],
        signal_at=[0],
    )
    assert len(trades) == 4
    assert set(trades["exit_reason"]) == {"end_of_data"}
    assert trades["exit_bar"].unique() == [2]
    assert trades["exit_price"].unique() == pytest.approx([99.5])


def test_partially_scaled_out_trade_liquidates_only_what_remains() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill at 100
            (100, 101, 95.5, 96),  # 2: 1R target fills; data ends
        ],
        signal_at=[0],
    )
    by_reason = trades.groupby("exit_reason").size()
    assert by_reason["target"] == 1
    assert by_reason["end_of_data"] == 3


def test_no_entry_is_taken_on_a_force_flat_bar() -> None:
    trades = run(
        [(102, 104, 100, 101), (101, 102, 99, 100)],
        signal_at=[0],
        force_flat_at=[0],
    )
    assert trades.empty


def test_a_resting_order_is_cancelled_rather_than_filled_at_the_flatten_point() -> None:
    # block_entry_at_session_close only stops a *new* signal being accepted on a
    # force-flat bar (see test_no_entry_is_taken_on_a_force_flat_bar); it does not reach
    # an order that rested from the bar before. Bar 1 here is the same gap-through-trigger
    # shape as test_gap_through_the_trigger_fills_at_the_open, so without cancellation this
    # would fill -- the account rules forbid a new position once flat is required.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, trigger 100
            (98, 99, 97, 98),  # 1: force-flat; would gap through the trigger
        ],
        signal_at=[0],
        force_flat_at=[1],
    )
    assert trades.empty


# -- ratcheting stop ----------------------------------------------------------


def test_stop_ratchets_down_but_never_loosens() -> None:
    # Fill on bar 1. At the close of bar 2 the stop becomes High[1] + 2 ticks = 102.5.
    # At the close of bar 3 it would be High[2] + 2 ticks = 101.5, tighter, so it moves.
    # Bar 4 then reaches 101.5 and stops out, even though the original 104.5 is untouched.
    trades = run(
        [
            (102, 104, 100, 101),  # 0: signal, stop 104.5
            (101, 102, 100, 101),  # 1: fill at 100
            (100, 101, 99, 100),  # 2: close -> stop 102.5
            (100, 100.5, 99, 100),  # 3: close -> stop 101.5 (High[2]=101 + 0.5)
            (100, 101.5, 99, 100),  # 4: touches 101.5
        ],
        signal_at=[0],
    )
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([101.5])
    assert trades["exit_bar"].unique() == [4]


def test_a_rising_high_does_not_loosen_the_stop() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),  # 1: fill, stop 104.5
            (100, 100.5, 99, 100),  # 2: close -> stop 101 (High[1]=102... wait, 102.5)
            (100, 103, 99, 100),  # 3: high rises; stop must not widen back out
            (100, 102.6, 99, 100),  # 4: above the loosened level, below the kept one
        ],
        signal_at=[0],
    )
    # Stop after bar 2 is High[1] + 0.5 = 102.5; bar 3's high of 103 exceeds it, so the
    # stop fires there rather than the stop drifting up to follow price.
    assert trades["exit_bar"].unique() == [3]
    assert trades["exit_price"].unique() == pytest.approx([102.5])


# -- costs --------------------------------------------------------------------


def test_slippage_is_adverse_on_stops_and_absent_on_limits() -> None:
    # Bar 1's high matches bar 0's so the ratchet leaves the stop at 104.5 and this test
    # measures slippage alone.
    slipped = run(
        [
            (102, 104, 100, 101),
            (101, 104, 100, 101),
            (100, 101, 95.5, 96),  # 1R target hit
            (96, 104.5, 95, 104),  # stop hit for the rest
        ],
        signal_at=[0],
        slippage=1.0,  # one tick
    )
    by_leg = slipped.set_index("leg")
    # Short entry via sell-stop: adverse means selling lower.
    assert by_leg["entry_price"].unique() == pytest.approx([99.75])
    # Limit target fills exactly at its price.
    assert by_leg.loc[1, "exit_price"] == pytest.approx(95.5)
    # Buy-stop to cover: adverse means buying higher.
    assert by_leg.loc[2, "exit_price"] == pytest.approx(104.75)


def test_commission_is_charged_per_contract_per_leg() -> None:
    trades = run(
        [(102, 104, 100, 101), (101, 102, 100, 101), (101, 104.5, 100, 104)],
        signal_at=[0],
        quantities=(1, 1, 1, 2),
        commission=1.5,
    )
    by_leg = trades.set_index("leg")
    assert by_leg.loc[1, "commission"] == pytest.approx(1.5)
    assert by_leg.loc[4, "commission"] == pytest.approx(3.0)
    assert trades["commission"].sum() == pytest.approx(7.5)


def test_pnl_is_instrument_aware() -> None:
    rows = [(102, 104, 100, 101), (101, 102, 100, 101), (100, 101, 95.5, 96)]
    mnq = run(rows, signal_at=[0], instrument=MNQ)
    nq = run(rows, signal_at=[0], instrument=NQ)
    # 4.5 points on leg 1, one contract: $9 on MNQ, $90 on NQ.
    assert mnq.set_index("leg").loc[1, "gross_pnl"] == pytest.approx(9.0)
    assert nq.set_index("leg").loc[1, "gross_pnl"] == pytest.approx(90.0)


# -- excursions and bookkeeping ----------------------------------------------


def test_mae_and_mfe_track_the_short_position_correctly() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 103, 100, 101),  # 1: fill at 100, high 103
            (100, 102, 94, 95),  # 2: low 94
            (95, 104.5, 94, 104),  # 3: stop out, high 104.5
        ],
        signal_at=[0],
    )
    row = trades.set_index("leg").loc[4]
    assert row["mae_points"] == pytest.approx(4.5)  # 104.5 - 100
    assert row["mfe_points"] == pytest.approx(6.0)  # 100 - 94


def test_legs_share_a_trade_id_and_carry_their_own_quantity() -> None:
    trades = run(
        [(102, 104, 100, 101), (101, 102, 100, 101), (101, 104.5, 100, 104)],
        signal_at=[0],
        quantities=(2, 2, 2, 4),
    )
    assert trades["trade_id"].nunique() == 1
    assert list(trades.sort_values("leg")["quantity"]) == [2, 2, 2, 4]


def test_consecutive_signals_produce_separate_trades() -> None:
    trades = run(
        [
            (102, 104, 100, 101),
            (102, 103, 101, 102),  # 1: no fill, order cancelled
            (102, 104, 100, 101),  # 2: new signal
            (101, 102, 100, 101),  # 3: fills
            (101, 104.5, 100, 104),
        ],
        signal_at=[0, 2],
    )
    assert trades["trade_id"].nunique() == 1
    assert trades["entry_bar"].unique() == [3]


# -- optional gates -----------------------------------------------------------


def test_reward_risk_gate_can_block_every_signal() -> None:
    rows = [(102, 104, 100, 101), (101, 102, 100, 101), (100, 101, 95.5, 96)]
    assert not run(rows, signal_at=[0], min_reward_risk=2.0).empty
    assert run(rows, signal_at=[0], min_reward_risk=2.5).empty


def test_leg_quantities_put_the_remainder_on_the_runner() -> None:
    assert DeadCatParams(order_quantity=4).leg_quantities == (1, 1, 1, 1)
    assert DeadCatParams(order_quantity=10).leg_quantities == (2, 2, 2, 4)
    assert DeadCatParams(order_quantity=7).leg_quantities == (1, 1, 1, 4)


def test_params_reject_a_quantity_that_cannot_fill_every_leg() -> None:
    with pytest.raises(ValueError, match="cannot fill"):
        DeadCatParams(order_quantity=3)


# -- behaviours added by the current NinjaScript revision ---------------------


def test_trigger_is_capped_two_ticks_below_the_close() -> None:
    # Signal bar closes at 101 with a low of 100. Close - 2 ticks = 100.5, which is above
    # the low, so the low still wins and the trigger is unchanged.
    unchanged = run([(102, 104, 100, 101), (101, 102, 99, 100)], signal_at=[0], entry_offset=2.0)
    assert unchanged["entry_price"].iloc[0] == pytest.approx(100.0)

    # An inverted hammer closes near its low: close 100.25, low 100. Now
    # close - 2 ticks = 99.75 sits *below* the low and becomes the trigger.
    capped = run([(102, 104, 100, 100.25), (101, 102, 99, 100)], signal_at=[0], entry_offset=2.0)
    assert capped["entry_price"].iloc[0] == pytest.approx(99.75)


def test_capped_trigger_makes_a_marginal_fill_miss() -> None:
    # Bar 1 bottoms at exactly 100. With the trigger at the low it fills; with the
    # close-based cap pushing the trigger to 99.75 it does not.
    rows = [(102, 104, 100, 100.25), (101, 102, 100, 101)]
    assert not run(rows, signal_at=[0], entry_offset=0.0).empty
    assert run(rows, signal_at=[0], entry_offset=2.0).empty


def test_capped_trigger_widens_the_risk_it_measures() -> None:
    capped = run([(102, 104, 100, 100.25), (101, 102, 99, 100)], signal_at=[0], entry_offset=2.0)
    # stop 104.5 against a 99.75 trigger rather than 100.
    assert capped["risk_points"].iloc[0] == pytest.approx(4.75)


def test_max_risk_is_measured_in_ticks_not_dollars() -> None:
    # Signal bar spans 100-104, so risk is 4.5 points = 18 ticks.
    rows = [(102, 104, 100, 101), (101, 102, 99, 100), (100, 101, 95, 96)]
    assert not run(rows, signal_at=[0], max_risk_ticks=18).empty
    assert run(rows, signal_at=[0], max_risk_ticks=17).empty


def test_tp_multiplier_scales_every_target() -> None:
    # Entry 100, risk 4.5. At 2x the targets become 2R, 3R and 4R of the base multiples.
    trades = run(
        [
            (102, 104, 100, 101),
            (101, 102, 100, 101),
            (100, 101, 82, 83),  # deep enough to fill all three
        ],
        signal_at=[0],
        tp_multiplier=2.0,
    )
    by_leg = trades.set_index("leg")
    assert by_leg.loc[1, "target_price"] == pytest.approx(91.0)  # 100 - 4.5*1*2
    assert by_leg.loc[2, "target_price"] == pytest.approx(86.5)  # 100 - 4.5*1.5*2
    assert by_leg.loc[3, "target_price"] == pytest.approx(82.0)  # 100 - 4.5*2*2


def test_targets_are_rounded_onto_the_tick_grid() -> None:
    # Risk of 4.25 points is 17 ticks; 1.5x is 25.5 ticks, a half tick that no exchange
    # accepts. RoundToTickSize in the NinjaScript snaps it, so we must too.
    trades = run(
        [
            (102, 103.75, 100, 101),  # stop 104.25, trigger 100 -> risk 4.25
            (101, 102, 100, 101),
            (100, 101, 85, 86),
        ],
        signal_at=[0],
    )
    targets = trades.set_index("leg")["target_price"].dropna()
    for t in targets:
        assert abs(t / 0.25 - round(t / 0.25)) < 1e-9, f"{t} is off the tick grid"
    # 100 - 4.25*1.5 = 93.625 -> rounds to 93.75, not left as a half tick.
    assert targets.loc[2] == pytest.approx(93.75)


def test_ratchet_lag_zero_uses_the_just_closed_bars_high() -> None:
    rows = [
        (102, 104, 100, 101),  # 0: signal, stop 104.5
        (101, 102, 100, 101),  # 1: fill at 100
        (100, 101, 99, 100),  # 2: close -> lag0 stop 101.5, lag1 stop 102.5
        (100, 102, 99, 100),  # 3: high 102 takes out 101.5 but not 102.5
    ]
    lag0 = run(rows, signal_at=[0], ratchet_lag=0)
    lag1 = run(rows, signal_at=[0], ratchet_lag=1)
    assert lag0["exit_price"].unique() == pytest.approx([101.5])
    assert lag0["exit_bar"].unique() == [3]
    # The looser lag=1 stop survives bar 3 and the position is still open at the end.
    assert set(lag1["exit_reason"]) == {"end_of_data"}


# -- direction (M15.1) ---------------------------------------------------------


def test_long_side_is_the_mirror_image_of_the_short_side() -> None:
    # Exactly test_stop_exits_every_remaining_leg_at_once's bars, reflected around 100:
    # new_open = 200-open, new_close = 200-close, new_high = 200-low, new_low = 200-high.
    # A long-capable archetype run with direction=LONG over the reflected bars must
    # reproduce every price and ratio from the short original, since the reflection and
    # the direction flip cancel exactly.
    trades = run(
        [
            (98, 100, 96, 99),
            (99, 100, 98, 99),  # 1: fill at 100, stop 95.5
            (99, 100, 95.5, 96),  # 2: touches the stop
        ],
        signal_at=[0],
        direction=LONG,
    )
    assert trades["entry_price"].iloc[0] == pytest.approx(100.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(95.5)
    assert trades["risk_points"].iloc[0] == pytest.approx(4.5)
    assert len(trades) == 4
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([95.5])
    # Same magnitude loss as the short original: R is dimensionless, so a mirrored losing
    # trade reads as the same -1.0R on either side.
    assert trades["r_multiple"].unique() == pytest.approx([-1.0])
    assert (trades["direction"] == LONG).all()


def test_targets_reached_first_is_direction_free() -> None:
    # _targets_reached_first takes no direction argument -- it works from the bar's open
    # alone, via abs() distance, which is already mirror-invariant. This pins that down so
    # a future "fix" that adds a sign to it cannot silently break just the long side.
    short_case = bracket.targets_reached_first(100.0, 104.0, 95.0, 1)
    long_case = bracket.targets_reached_first(100.0, 96.0, 105.0, 1)  # mirrored around 100
    assert short_case == long_case
