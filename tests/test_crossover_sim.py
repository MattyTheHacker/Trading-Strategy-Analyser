"""EmaCrossover simulation tests on hand-built bars.

The archetype has no NinjaScript, so unlike the two ports there is no trade list to check
against. What these pin instead are the three mechanisms it introduces -- a
market-on-next-open entry, an ATR or swing stop with no trigger to anchor to, and the
``EXIT_SIGNAL`` exit -- plus the property the whole thing is worthless without: that nothing
it reads comes from a bar it could not have seen.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import conditions, sessions, sweep
from nqbt.instruments import MNQ, NQ
from nqbt.sim import crossover
from nqbt.sim.crossover import crossover_signal, regime_direction, run_crossover
from nqbt.sim.types import EmaCrossoverParams
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25


def simulate(
    rows,
    signal_at=(),
    max_rows=None,
    direction=LONG,
    flip_at=(),
    atr=4.0,
    force_flat_at=(),
    quantities=(1, 1, 1, 1),
    targets=(1.0, 1.5, 2.0, np.nan),
    use_atr_stop=True,
    atr_stop_multiple=1.0,
    min_bracket_dollars=0.0,
    swing_lookback=3,
    stop_offset_ticks=2.0,
    tp_multiplier=1.0,
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    bars_required=0,
    exit_on_opposite_cross=True,
    block_entry_at_close=True,
    fill_limit_on_touch=True,  # tests target exact prices; opt out explicitly
    ambiguity_policy=0,
    round_targets=True,
):
    """Simulate hand-written OHLC rows.

    ``signal_at`` lists the bars whose close schedules an entry; ``direction`` is the
    prevailing regime and ``flip_at`` the bars from which it is the other way, which is what
    the loop reads to close a position on a signal.
    """
    arr = np.asarray(rows, dtype=np.float64)
    o, h, low, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    signal = np.zeros(n, dtype=np.bool_)
    for i in signal_at:
        signal[i] = True
    direction_at = np.full(n, direction, dtype=np.float64)
    for i in flip_at:
        direction_at[i:] = -direction
    force_flat = np.zeros(n, dtype=np.bool_)
    for i in force_flat_at:
        force_flat[i] = True

    out = (
        crossover.bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
        if max_rows is None
        else np.zeros((max_rows, N_COLUMNS), dtype=np.float64)
    )
    count = crossover.simulate_crossover(
        crossover.bracket.Bars(o, h, low, c, force_flat),
        signal,
        direction_at,
        np.full(n, atr, dtype=np.float64) if np.isscalar(atr) else np.asarray(atr, dtype=np.float64),
        np.asarray(quantities, dtype=np.int64),
        np.asarray(targets, dtype=np.float64),
        crossover.bracket.Costs(TICK, instrument.point_value, commission, slippage),
        crossover.bracket.FillRules(fill_limit_on_touch, ambiguity_policy, round_targets),
        crossover.CrossoverRules(
            use_atr_stop=use_atr_stop,
            atr_stop_multiple=atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(min_bracket_dollars),
            swing_lookback=swing_lookback,
            stop_offset_ticks=stop_offset_ticks,
            tp_multiplier=tp_multiplier,
            bars_required=bars_required,
            exit_on_opposite_cross=exit_on_opposite_cross,
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


# -- the third entry mechanism -------------------------------------------------


def test_the_entry_fills_at_the_next_bars_open_without_touching_anything() -> None:
    # No trigger price and no "no touch, no fill": bar 1 opens at 102 and never trades back
    # to bar 0's range, and the entry fills at 102 regardless.
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal
            (102.0, 102.5, 101.5, 102.0),  # 1: gapped up; a stop-market entry would miss
            *FLAT,
        ],
        signal_at=[0],
    )
    assert trades["entry_bar"].iloc[0] == 1
    assert trades["entry_price"].iloc[0] == pytest.approx(102.0)


def test_slippage_on_the_entry_takes_the_direction_sign() -> None:
    long_side = run(FLAT, signal_at=[0], slippage=2.0, direction=LONG)
    short_side = run(FLAT, signal_at=[0], slippage=2.0, direction=SHORT)
    assert long_side["entry_price"].iloc[0] == pytest.approx(100.0 + 2 * TICK)
    assert short_side["entry_price"].iloc[0] == pytest.approx(100.0 - 2 * TICK)


def test_the_order_fills_at_the_flatten_point_and_is_flattened_there() -> None:
    """NT8 fills the resting order and only then flattens -- ``docs/nt8-fidelity.md``,
    "A resting entry fills on the force-flat bar, and is flattened at its close"."""
    trades = run(FLAT, signal_at=[0], force_flat_at=[1])
    assert list(trades["entry_bar"].unique()) == [1]
    assert set(trades["exit_reason"]) == {"session_close"}
    assert list(trades["exit_bar"].unique()) == [1]
    assert trades["exit_price"].unique() == pytest.approx([100.0])  # bar 1's close


def test_a_signal_on_a_force_flat_bar_is_blocked_when_asked() -> None:
    assert run(FLAT, signal_at=[0], force_flat_at=[0]).empty
    assert not run(FLAT, signal_at=[0], force_flat_at=[0], block_entry_at_close=False).empty


def test_a_signal_while_already_in_a_position_does_not_pyramid() -> None:
    """The loop is flat-to-flat: a second entry needs the first position to be gone."""
    trades = run(FLAT, signal_at=[0, 3], atr=40.0)
    assert list(trades["entry_bar"].unique()) == [1]


# -- the stop, which has no signal wick to anchor to ---------------------------


def test_the_atr_stop_is_a_multiple_of_atr_measured_from_the_fill() -> None:
    trades = run(FLAT, signal_at=[0], atr=4.0, atr_stop_multiple=1.5)
    assert trades["initial_stop"].iloc[0] == pytest.approx(100.0 - 6.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(6.0)


def test_the_atr_stop_reads_the_signal_bar_not_the_fill_bar() -> None:
    """The ATR the stop uses must come from a completed bar -- the whole lookahead worry.

    Bar 1's ATR is set ten times bar 0's, so a stop that read the fill bar lands nowhere
    near 96 and the test says which bar it read.
    """
    atr = np.zeros(len(FLAT), dtype=np.float64)
    atr[0] = 4.0
    atr[1] = 40.0
    trades = run(FLAT, signal_at=[0], atr=atr)
    assert trades["initial_stop"].iloc[0] == pytest.approx(96.0)


def test_the_swing_stop_takes_the_adverse_extreme_of_the_lookback() -> None:
    # Lows 99.5 / 97.0 / 98.0 over bars 0-2, so a long signalling at bar 2 stops at
    # 97.0 - 2 ticks. The offset is applied to the swing mode only.
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 97.0, 100.0),
            (100.0, 100.5, 98.0, 100.0),  # 2: signal
            *FLAT,
        ],
        signal_at=[2],
        use_atr_stop=False,
        swing_lookback=3,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(97.0 - 0.5)


def test_the_swing_stop_mirrors_for_a_short() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 103.0, 99.5, 100.0),
            (100.0, 102.0, 99.5, 100.0),  # 2: signal
            *FLAT,
        ],
        signal_at=[2],
        direction=SHORT,
        use_atr_stop=False,
        swing_lookback=3,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(103.0 + 0.5)


def test_an_entry_whose_stop_is_already_through_the_fill_is_skipped() -> None:
    """A stop at or through the price it protects is not a stop order.

    The same rule NT8 applies to a stop-market *entry*, and reachable here because the fill
    is wherever the next bar opens rather than at a trigger the stop was placed against.
    """
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal; swing low 99.5 -> stop 99.25
            (99.0, 99.5, 98.5, 99.0),  # 1: opens below its own stop
            *FLAT,
        ],
        signal_at=[0],
        use_atr_stop=False,
        swing_lookback=1,
    )
    assert trades.empty


def test_a_zero_atr_stop_is_skipped_rather_than_traded_at_no_risk() -> None:
    assert run(FLAT, signal_at=[0], atr=0.0).empty


# -- the hard dollar floor under the ATR bracket -------------------------------

# MNQ is $2 a point, so a $30 floor is 15 points; NQ is $20 a point and the same $30 is
# 1.5. Every case below picks its ATR against those two distances.


def test_the_dollar_floor_widens_a_bracket_the_atr_would_size_below_it() -> None:
    trades = run(FLAT, signal_at=[0], atr=4.0, atr_stop_multiple=1.0, min_bracket_dollars=30.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(100.0 - 15.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(15.0)


def test_the_dollar_floor_leaves_a_wider_atr_bracket_alone() -> None:
    trades = run(FLAT, signal_at=[0], atr=20.0, atr_stop_multiple=1.0, min_bracket_dollars=30.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(20.0)


def test_an_atr_bracket_exactly_on_the_floor_is_the_floor() -> None:
    """The boundary the two branches meet at, where neither may nudge the stop."""
    trades = run(FLAT, signal_at=[0], atr=15.0, atr_stop_multiple=1.0, min_bracket_dollars=30.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(15.0)


def test_the_same_dollar_floor_is_a_different_distance_on_each_instrument() -> None:
    """Why the floor is in dollars: NQ and MNQ share a tick size and differ 10x in value.

    A floor written in points would be $300 of risk on one and $30 on the other.
    """
    kwargs = {"atr": 0.5, "atr_stop_multiple": 1.0, "min_bracket_dollars": 30.0}
    micro = run(FLAT, signal_at=[0], instrument=MNQ, **kwargs)
    full = run(FLAT, signal_at=[0], instrument=NQ, **kwargs)
    assert micro["risk_points"].iloc[0] == pytest.approx(15.0)
    assert full["risk_points"].iloc[0] == pytest.approx(1.5)


def test_the_floor_does_not_reach_the_swing_stop() -> None:
    """A swing stop is a structural level rather than a distance, so it is left where it is."""
    rows = [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 97.0, 100.0),
        (100.0, 100.5, 98.0, 100.0),  # 2: signal
        *FLAT,
    ]
    trades = run(rows, signal_at=[2], use_atr_stop=False, swing_lookback=3, min_bracket_dollars=300.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(97.0 - 0.5)


def test_a_floored_bracket_scales_its_targets_off_the_floored_risk() -> None:
    """R follows the floor, which is the whole R-comparability consequence in one assertion."""
    trades = run(
        FLAT,
        signal_at=[0],
        atr=4.0,
        atr_stop_multiple=1.0,
        min_bracket_dollars=30.0,
        targets=(1.0, 2.0, np.nan, np.nan),
        quantities=(1, 1, 1, 1),
    )
    assert sorted(trades["target_price"].dropna().unique()) == [115.0, 130.0]


def test_the_floor_makes_a_zero_atr_bar_tradable_again() -> None:
    """Without it a quiet bar has no risk and is skipped -- the floor is what supplies one."""
    assert run(FLAT, signal_at=[0], atr=0.0).empty
    assert not run(FLAT, signal_at=[0], atr=0.0, min_bracket_dollars=30.0).empty


# -- the signal exit -----------------------------------------------------------


def test_the_regime_flip_exits_at_the_next_bars_open() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal
            (100.0, 100.5, 99.5, 100.0),  # 1: fill at 100
            (100.0, 100.5, 99.5, 100.0),  # 2: regime flips at this close
            (99.0, 99.5, 98.5, 99.0),  # 3: market exit at the open
            *FLAT,
        ],
        signal_at=[0],
        flip_at=[2],
    )
    leg = trades.iloc[0]
    assert leg["exit_reason"] == "signal"
    assert leg["exit_bar"] == 3
    assert leg["exit_price"] == pytest.approx(99.0)


def test_the_signal_exit_pays_slippage_on_the_correct_side() -> None:
    trades = run(
        [
            *[(100.0, 100.5, 99.5, 100.0)] * 3,
            (99.0, 99.5, 98.5, 99.0),
            *FLAT,
        ],
        signal_at=[0],
        flip_at=[2],
        slippage=2.0,
    )
    # Long exit: adverse slippage is a lower fill.
    assert trades["exit_price"].iloc[0] == pytest.approx(99.0 - 2 * TICK)


def test_the_signal_exit_does_not_extend_mae_or_mfe_past_the_open() -> None:
    """The position closed at the bar's first price, so the rest of its range never applied."""
    trades = run(
        [
            *[(100.0, 100.5, 99.5, 100.0)] * 3,
            (100.0, 120.0, 80.0, 100.0),  # 3: exit at the open, then a huge range
            *FLAT,
        ],
        signal_at=[0],
        flip_at=[2],
        atr=40.0,  # wide enough that the stop is not reached inside bar 3
    )
    leg = trades.iloc[0]
    assert leg["mfe_points"] < 20.0
    assert leg["mae_points"] < 20.0


def test_the_flip_closes_and_reopens_on_the_other_side_at_one_price() -> None:
    """Flat between trades, not stop-and-reverse: two trades, two fills, two lots of costs."""
    trades = run(
        [
            *[(100.0, 100.5, 99.5, 100.0)] * 3,
            (99.0, 99.5, 98.5, 99.0),  # 3: long exits and the short opens, both at 99
            *FLAT,
        ],
        signal_at=[0, 2],
        flip_at=[2],
        commission=1.0,
    )
    assert sorted(trades["trade_id"].unique()) == [1, 2]
    first, second = trades[trades["trade_id"] == 1], trades[trades["trade_id"] == 2]
    assert first["direction"].iloc[0] == LONG
    assert second["direction"].iloc[0] == SHORT
    assert first["exit_price"].iloc[0] == pytest.approx(second["entry_price"].iloc[0])
    assert first["exit_bar"].iloc[0] == second["entry_bar"].iloc[0] == 3
    # A reversing order would charge one commission per leg, not two.
    assert trades["commission"].sum() == pytest.approx(8.0)


def test_the_flip_can_be_switched_off() -> None:
    trades = run(
        [
            *[(100.0, 100.5, 99.5, 100.0)] * 3,
            (99.0, 99.5, 98.5, 99.0),
            *FLAT,
        ],
        signal_at=[0],
        flip_at=[2],
        exit_on_opposite_cross=False,
    )
    assert set(trades["exit_reason"]) == {"end_of_data"}


# -- the bracket half, which is the shared engine ------------------------------


def test_targets_are_measured_from_the_fill_and_land_on_the_tick_grid() -> None:
    trades = run(FLAT, signal_at=[0], atr=3.5, atr_stop_multiple=1.0)
    legs = trades.sort_values("leg")
    # risk 3.5: 1R at 103.5, 1.5R at 105.25, 2R at 107.
    assert list(legs["target_price"][:3]) == pytest.approx([103.5, 105.25, 107.0])
    assert np.isnan(legs["target_price"].iloc[3]), "the runner has no target"


def test_the_stop_and_the_session_close_still_exit() -> None:
    stopped = run(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 95.0, 96.0),  # 2: through the stop at 96
            *FLAT,
        ],
        signal_at=[0],
        atr=4.0,
    )
    assert set(stopped["exit_reason"]) == {"stop"}

    flattened = run(FLAT, signal_at=[0], force_flat_at=[3], atr=40.0)
    assert set(flattened["exit_reason"]) == {"session_close"}


def test_instrument_scaling_multiplies_gross_pnl_and_leaves_geometry_alone() -> None:
    mnq = run(FLAT, signal_at=[0], atr=4.0, instrument=MNQ)
    nq = run(FLAT, signal_at=[0], atr=4.0, instrument=NQ)
    assert list(mnq["entry_price"]) == pytest.approx(list(nq["entry_price"]))
    assert list(nq["gross_pnl"]) == pytest.approx([v * 10 for v in mnq["gross_pnl"]])


# -- the archetype end to end --------------------------------------------------


def bars(n: int = 1200, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.5, n))
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


def prepared(params: EmaCrossoverParams):
    return sweep.prepare_for(bars(), sweep.Grid.of(params))


def test_the_archetype_trades_both_sides_and_produces_signal_exits() -> None:
    params = EmaCrossoverParams(bars_required_to_trade=50)
    log = run_crossover(prepared(params), params, MNQ)
    assert set(log["direction"]) == {LONG, SHORT}
    assert "signal" in set(log["exit_reason"])


def test_nothing_the_signal_reads_comes_from_a_bar_it_could_not_have_seen() -> None:
    """Recompute over a prefix: every value must be what the full series already said.

    This is the test the archetype exists to make possible to fail. A crossover is unusually
    easy to compute one bar early, and the symptom is a profit factor above 1 rather than an
    exception.
    """
    params = EmaCrossoverParams(bars_required_to_trade=50, cross_lookback=3)
    frame = bars()
    grid = sweep.Grid.of(params)
    full = crossover_signal(sweep.prepare_for(frame, grid), params)
    for cut in (300, 700, 1000):
        prefix = crossover_signal(sweep.prepare_for(frame.iloc[:cut], grid), params)
        assert np.array_equal(prefix, full[:cut])


def test_trading_one_side_only_removes_the_other() -> None:
    long_only = EmaCrossoverParams(bars_required_to_trade=50, trade_short=False)
    log = run_crossover(prepared(long_only), long_only, MNQ)
    assert set(log["direction"]) == {LONG}


def test_the_regime_boundary_matches_the_cross_it_pairs_with() -> None:
    fast = np.array([1.0, 2.0, 2.0, 3.0])
    slow = np.array([2.0, 2.0, 2.0, 2.0])
    assert list(regime_direction(fast, slow)) == [SHORT, SHORT, SHORT, LONG]
    # Equality reads short, so the move to strictly above it is still a cross.
    assert list(conditions.cross_above(fast, slow)) == [False, False, False, True]


# -- the parameter set ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"order_quantity": 3}, "cannot fill"),
        ({"fast_period": 0}, "fast_period must be >= 1"),
        ({"atr_period": 0}, "atr_period must be >= 1"),
        ({"swing_lookback": 0}, "swing_lookback must be >= 1"),
        ({"cross_lookback": 0}, "cross_lookback must be >= 1"),
        ({"min_bracket_dollars": -1.0}, "min_bracket_dollars must be >= 0"),
        ({"fast_period": 21}, "identical\nx?averages never cross"),
        ({"fast_period": 21, "fast_kind": "sma", "slow_kind": "sma"}, "both sma\\(21\\)"),
    ],
)
def test_an_unusable_parameter_set_is_refused(kwargs, match) -> None:
    with pytest.raises(ValueError, match=match.replace("\nx?", " ")):
        EmaCrossoverParams(**kwargs)


def test_equal_periods_of_different_kinds_are_a_real_cross_and_are_allowed() -> None:
    """``ema(21)`` and ``sma(21)`` are two different series, so they do cross."""
    params = EmaCrossoverParams(fast_period=21, slow_period=21, fast_kind="ema", slow_kind="sma")
    assert (params.fast_kind, params.slow_kind) == ("ema", "sma")


def test_the_leg_split_matches_the_ported_archetypes() -> None:
    """10 contracts go 2/2/2/4, so a scale-out is comparable across all three archetypes."""
    assert EmaCrossoverParams(order_quantity=10).leg_quantities == (2, 2, 2, 4)


def test_as_dict_flattens_the_target_tuple_for_the_results_table() -> None:
    d = EmaCrossoverParams().as_dict()
    assert isinstance(d["target_r_multiples"], list)
    assert d["use_atr_stop"] is True


# -- the buffer-overflow guard -------------------------------------------------

# One scenario per place the loop can run out of room, because each has its own guard and
# a shared one would leave the others unexercised. `allocate_output`'s n_signals x n_legs
# bound makes all of them unreachable in normal use -- which is exactly why they are worth
# a test: numba does not bounds-check, so these returns are the only thing between a
# violated bound and a write past the end of the matrix. Verifying a guard can fire is part
# of relying on it.
OVERFLOW_CASES = {
    "stop while in a position": (
        [*[(100.0, 100.5, 99.5, 100.0)] * 2, (100.0, 100.5, 95.0, 96.0), *FLAT],
        {"signal_at": [0]},
    ),
    "two targets on one bar": (
        [*[(100.0, 100.5, 99.5, 100.0)] * 2, (100.0, 106.5, 99.5, 106.0), *FLAT],
        {"signal_at": [0]},
    ),
    "targets first, then the stop": (
        [*[(100.0, 100.5, 99.5, 100.0)] * 2, (103.0, 104.5, 95.0, 100.0), *FLAT],
        {"signal_at": [0], "ambiguity_policy": 1},
    ),
    "the session close": (
        FLAT,
        {"signal_at": [0], "force_flat_at": [3], "atr": 40.0},
    ),
    "the entry bar's own stop": (
        [(100.0, 100.5, 99.5, 100.0), (100.0, 100.5, 95.0, 96.0), *FLAT],
        {"signal_at": [0]},
    ),
    "the signal exit": (
        [*[(100.0, 100.5, 99.5, 100.0)] * 3, (99.0, 99.5, 98.5, 99.0), *FLAT],
        {"signal_at": [0], "flip_at": [2], "atr": 40.0},
    ),
    "the end of the series": (
        FLAT,
        {"signal_at": [0], "atr": 40.0},
    ),
}


@pytest.mark.parametrize(("rows", "kwargs"), OVERFLOW_CASES.values(), ids=list(OVERFLOW_CASES))
def test_a_full_buffer_is_reported_rather_than_written_past(rows, kwargs) -> None:
    # One row of room against a four-leg trade, so the second write has nowhere to go.
    assert simulate(rows, max_rows=1, **kwargs)[0] == -1
    # The same scenario with room is a normal trade, which is what says the buffer size is
    # the only thing under test here.
    assert not run(rows, **kwargs).empty


def test_trading_the_short_side_only_removes_the_long_one() -> None:
    short_only = EmaCrossoverParams(bars_required_to_trade=50, trade_long=False)
    log = run_crossover(prepared(short_only), short_only, MNQ)
    assert set(log["direction"]) == {SHORT}
