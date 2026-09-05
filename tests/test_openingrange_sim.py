"""OpeningRange simulation tests on hand-built bars.

The archetype has no NinjaScript, so there is no trade list to check against. What these pin
instead are the three things it introduces -- a trigger that is a *level* and so rests for the
whole session, a per-session entry cap, and a target expressed in range widths -- plus the two
NT8 rules its entry mechanism inherits and the property the whole thing is worthless without:
that nothing it reads comes from a bar it could not have seen.

Prices are kept small and round so the arithmetic is checkable by eye: the range is 90 to 110
unless a test says otherwise.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import (
    archetypes,
    context,
    higher_timeframe,
    randomentry,
    regime,
    sessionrange,
    sessions,
    sweep,
    timeofday,
    trend,
    volume,
)
from nqbt.instruments import MNQ, NQ
from nqbt.sim import openingrange
from nqbt.sim.openingrange import entry_bound, openingrange_signal, run_openingrange
from nqbt.sim.types import (
    ORB_STOP_ATR,
    ORB_STOP_OPPOSITE,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    OpeningRangeParams,
)
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25
RANGE_HIGH = 110.0
RANGE_LOW = 90.0


def simulate(
    rows,
    signal_at=(),
    *,
    max_rows=None,
    direction=LONG,
    range_high=RANGE_HIGH,
    range_low=RANGE_LOW,
    session_id=None,
    armed=None,
    atr=4.0,
    force_flat_at=(),
    quantities=(1,),
    levels=(1.0,),
    entry_offset_ticks=0.0,
    stop_mode=ORB_STOP_OPPOSITE,
    stop_offset_ticks=0.0,
    atr_stop_multiple=1.0,
    min_bracket_dollars=0.0,
    target_mode=ORB_TARGET_R,
    tp_multiplier=1.0,
    max_entries_per_session=0,
    bars_required=0,
    block_entry_at_close=True,
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    fill_limit_on_touch=True,  # tests target exact prices; opt out explicitly
    ambiguity_policy=0,
    round_targets=False,
):
    """Simulate hand-written OHLC rows against a range supplied directly.

    ``signal_at`` lists the bars that may submit an order, and ``range_high``/``range_low``
    stand in for the range grid so a test can state the geometry rather than reverse-engineer
    a price series that produces it.
    """
    arr = np.asarray(rows, dtype=np.float64)
    o, h, low, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    signal = np.zeros(n, dtype=np.bool_)
    for i in signal_at:
        signal[i] = True
    ids = np.zeros(n, dtype=np.int32) if session_id is None else np.asarray(session_id, dtype=np.int32)
    live = np.ones(n, dtype=np.bool_) if armed is None else np.asarray(armed, dtype=np.bool_)
    force_flat = np.zeros(n, dtype=np.bool_)
    for i in force_flat_at:
        force_flat[i] = True

    def per_session(value):
        return np.full(int(ids.max()) + 1, value, dtype=np.float64)

    out = (
        openingrange.bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
        if max_rows is None
        else np.zeros((max_rows, N_COLUMNS), dtype=np.float64)
    )
    count = openingrange.simulate_openingrange(
        openingrange.bracket.Bars(o, h, low, c, force_flat),
        signal,
        openingrange.RangeSeries(
            armed=live,
            session_id=ids,
            high=per_session(range_high),
            low=per_session(range_low),
            atr=np.full(n, atr, dtype=np.float64),
        ),
        np.asarray(quantities, dtype=np.int64),
        np.asarray(levels, dtype=np.float64),
        openingrange.bracket.Costs(TICK, instrument.point_value, commission, slippage),
        openingrange.bracket.FillRules(fill_limit_on_touch, ambiguity_policy, round_targets),
        openingrange.OpeningRangeRules(
            direction=direction,
            entry_offset=entry_offset_ticks * TICK,
            stop_mode=stop_mode,
            stop_offset=stop_offset_ticks * TICK,
            atr_stop_multiple=atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(min_bracket_dollars),
            target_mode=target_mode,
            tp_multiplier=tp_multiplier,
            max_entries_per_session=max_entries_per_session,
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


BELOW = (100.0, 105.0, 95.0, 100.0)
"""A bar that stays inside the range on both sides."""

BREAKS = (100.0, 115.0, 95.0, 112.0)
"""A bar that trades through the range high."""


# -- the entry, which is DeadCatBounce's mechanism at a persistent level --------


def test_the_resting_order_fills_at_the_trigger_when_price_trades_through_it() -> None:
    trades = run([BELOW, BREAKS], signal_at=(0,))

    assert len(trades) == 1
    assert trades["entry_price"].iloc[0] == RANGE_HIGH
    assert trades["entry_bar"].iloc[0] == 1


def test_an_open_beyond_the_trigger_fills_at_the_open_not_the_trigger() -> None:
    """A stop order is a market order once triggered, so a gap fills where the market is."""
    trades = run([BELOW, (114.0, 116.0, 113.0, 115.0)], signal_at=(0,))

    assert trades["entry_price"].iloc[0] == 114.0


def test_the_trigger_sits_the_entry_offset_beyond_the_range_extreme() -> None:
    trades = run([BELOW, BREAKS], signal_at=(0,), entry_offset_ticks=4.0)

    assert trades["entry_price"].iloc[0] == RANGE_HIGH + 1.0


def test_a_bar_closing_at_or_beyond_the_trigger_submits_nothing() -> None:
    """NT8 declines a stop entry at or through the market -- ``docs/nt8-fidelity.md`` §M18.

    This is not a corner case here: it is every bar after the break, which is exactly why the
    entry offset defaults to a tick rather than zero.
    """
    closed_at_trigger = (100.0, RANGE_HIGH, 95.0, RANGE_HIGH)

    assert len(run([closed_at_trigger, BREAKS], signal_at=(0,))) == 0
    assert len(run([BREAKS, BREAKS], signal_at=(0,))) == 0, "closed above the trigger"
    # One tick of offset puts the trigger back above that close and the order is live again.
    assert len(run([closed_at_trigger, BREAKS], signal_at=(0,), entry_offset_ticks=1.0)) == 1


def test_the_order_rests_for_the_whole_session_rather_than_one_bar() -> None:
    """The route-3 property, and what separates this from every other archetype here.

    DeadCatBounce's trigger is computed from its signal bar, so its order is gone after one
    bar. This trigger is a level, so resubmitting it every bar is a resting order -- a break
    five bars later still fills, at the same price.
    """
    rows = [BELOW, BELOW, BELOW, BELOW, BELOW, BREAKS]
    trades = run(rows, signal_at=(0, 1, 2, 3, 4))

    assert len(trades) == 1
    assert trades["entry_bar"].iloc[0] == 5
    assert trades["entry_price"].iloc[0] == RANGE_HIGH
    # Submitted on bar 0 alone, the order would have expired long before the break.
    assert len(run(rows, signal_at=(0,))) == 0


def test_a_bar_whose_range_never_completed_cannot_submit_an_order() -> None:
    """``armed`` is checked in the loop, not inherited from the signal, because the
    random-entry arm substitutes the signal and can drop one anywhere."""
    assert len(run([BELOW, BREAKS], signal_at=(0,), armed=[False, False])) == 0


def test_a_range_too_tight_to_hold_a_stop_is_not_traded() -> None:
    """The submittability floor every archetype shares: risk below one tick is not an order."""
    assert len(run([BELOW, BREAKS], signal_at=(0,), range_low=RANGE_HIGH)) == 0


# -- the per-session entry cap -------------------------------------------------


STOPS_OUT = (100.0, 115.0, 85.0, 95.0)
"""Trades through the trigger and then through the opposite extreme on the same bar."""


def test_one_entry_a_session_is_the_default_and_a_stop_out_ends_the_session() -> None:
    """Essentially every published opening-range result is one-shot -- §M28, finding 4."""
    rows = [BELOW, STOPS_OUT, BELOW, BREAKS]
    trades = run(rows, signal_at=(0, 1, 2), max_entries_per_session=1)

    assert trades["trade_id"].nunique() == 1
    assert trades["exit_reason"].iloc[0] == "stop"


def test_uncapped_the_same_session_re_enters_at_the_same_level_after_every_stop() -> None:
    """The divergence from the published results, made measurable rather than left as a caveat."""
    rows = [BELOW, STOPS_OUT, BELOW, BREAKS]
    trades = run(rows, signal_at=(0, 1, 2), max_entries_per_session=0)

    assert trades["trade_id"].nunique() == 2
    assert (trades["entry_price"] == RANGE_HIGH).all(), "the second entry is the same level"


def test_the_cap_re_arms_at_the_session_boundary() -> None:
    """Otherwise one trade would use up the whole series rather than one day of it."""
    # Bar 2 stops the first trade out, so the cap rather than the open position is what
    # would refuse the second one.
    rows = [BELOW, BREAKS, (100.0, 105.0, 85.0, 95.0), BELOW, BREAKS]
    same_session = run(rows, signal_at=(0, 3), max_entries_per_session=1)
    assert same_session["trade_id"].nunique() == 1, "premise gone; the cap is not binding"

    trades = run(rows, signal_at=(0, 3), session_id=[0, 0, 0, 1, 1], max_entries_per_session=1)

    assert trades["trade_id"].nunique() == 2
    assert list(trades["entry_bar"]) == [1, 4]


# -- the stop -------------------------------------------------------------------


def test_the_opposite_extreme_stop_sits_the_offset_beyond_the_far_side() -> None:
    trades = run([BELOW, BREAKS], signal_at=(0,), stop_offset_ticks=4.0)

    assert trades["initial_stop"].iloc[0] == RANGE_LOW - 1.0
    assert trades["risk_points"].iloc[0] == pytest.approx(RANGE_HIGH - RANGE_LOW + 1.0)


def test_the_atr_stop_is_a_multiple_back_from_the_trigger_and_is_floored() -> None:
    """The floor is a per-contract dollar amount, so it converts through the instrument."""
    trades = run([BELOW, BREAKS], signal_at=(0,), stop_mode=ORB_STOP_ATR, atr=4.0)
    assert trades["initial_stop"].iloc[0] == RANGE_HIGH - 4.0

    floored = run(
        [BELOW, BREAKS],
        signal_at=(0,),
        stop_mode=ORB_STOP_ATR,
        atr=1.0,
        min_bracket_dollars=MNQ.point_value * 6.0,
    )
    assert floored["initial_stop"].iloc[0] == RANGE_HIGH - 6.0


def test_the_stop_offset_does_nothing_under_the_atr_stop() -> None:
    """The blind spot ``dead_axes`` cannot see, asserted so it is at least written down."""
    kwargs = {"signal_at": (0,), "stop_mode": ORB_STOP_ATR}
    wide = run([BELOW, BREAKS], stop_offset_ticks=40.0, **kwargs)
    none = run([BELOW, BREAKS], stop_offset_ticks=0.0, **kwargs)

    assert wide["initial_stop"].iloc[0] == none["initial_stop"].iloc[0]


# -- the targets ----------------------------------------------------------------


def test_r_targets_are_measured_from_the_trigger_not_the_fill() -> None:
    """A gapped fill is worse than planned; the bracket was set when the order was submitted."""
    gapped = run([BELOW, (114.0, 132.0, 113.0, 130.0)], signal_at=(0,), levels=(1.0,))

    assert gapped["entry_price"].iloc[0] == 114.0
    assert gapped["target_price"].iloc[0] == RANGE_HIGH + (RANGE_HIGH - RANGE_LOW)
    assert gapped["risk_points"].iloc[0] == pytest.approx(RANGE_HIGH - RANGE_LOW)


def test_a_width_target_is_a_multiple_of_the_range_and_ignores_the_r_ladder() -> None:
    trades = run(
        [BELOW, BREAKS],
        signal_at=(0,),
        target_mode=ORB_TARGET_WIDTH,
        levels=(0.5,),
        stop_offset_ticks=4.0,
    )

    assert trades["target_price"].iloc[0] == RANGE_HIGH + 0.5 * (RANGE_HIGH - RANGE_LOW)


def test_tp_multiplier_scales_an_r_target_and_not_a_width_target() -> None:
    """A width multiple is already a distance, so scaling it too would be one axis twice."""
    kwargs = {"signal_at": (0,), "levels": (1.0,)}
    r_one = run([BELOW, BREAKS], tp_multiplier=1.0, **kwargs)["target_price"].iloc[0]
    r_two = run([BELOW, BREAKS], tp_multiplier=2.0, **kwargs)["target_price"].iloc[0]
    assert r_two - RANGE_HIGH == pytest.approx(2.0 * (r_one - RANGE_HIGH))

    width = {"target_mode": ORB_TARGET_WIDTH, **kwargs}
    assert (
        run([BELOW, BREAKS], tp_multiplier=1.0, **width)["target_price"].iloc[0]
        == run([BELOW, BREAKS], tp_multiplier=2.0, **width)["target_price"].iloc[0]
    )


def test_a_runner_leg_carries_no_target_and_leaves_at_the_session_close() -> None:
    trades = run(
        [BELOW, BREAKS, (112.0, 113.0, 111.0, 112.0)],
        signal_at=(0,),
        quantities=(1, 1),
        levels=(1.0, float("nan")),
        force_flat_at=(2,),
    )

    runner = trades[trades["leg"] == 2].iloc[0]
    assert np.isnan(runner["target_price"])
    assert runner["exit_reason"] == "session_close"


# -- the short side mirrors the long ---------------------------------------------


def test_the_short_side_is_the_long_side_reflected_through_the_range() -> None:
    """One sign multiplier, not two code paths -- the same property the bracket engine has."""
    breaks_down = (100.0, 105.0, 85.0, 88.0)
    trades = run([BELOW, breaks_down], signal_at=(0,), direction=SHORT, stop_offset_ticks=4.0)

    assert trades["direction"].iloc[0] == SHORT
    assert trades["entry_price"].iloc[0] == RANGE_LOW
    assert trades["initial_stop"].iloc[0] == RANGE_HIGH + 1.0
    assert trades["target_price"].iloc[0] == RANGE_LOW - (RANGE_HIGH - RANGE_LOW + 1.0)


def test_a_short_is_not_submitted_when_the_close_is_already_below_the_trigger() -> None:
    assert len(run([(100.0, 105.0, 85.0, 88.0), BELOW], signal_at=(0,), direction=SHORT)) == 0


# -- costs and the session close -------------------------------------------------


def test_slippage_worsens_the_stop_entry_and_never_the_limit_target() -> None:
    trades = run([BELOW, BREAKS], signal_at=(0,), slippage=2.0, levels=(0.1,))

    assert trades["entry_price"].iloc[0] == RANGE_HIGH + 2 * TICK
    assert trades["exit_reason"].iloc[0] == "target"
    assert trades["exit_price"].iloc[0] == trades["target_price"].iloc[0]


def test_a_resting_order_still_fills_on_the_force_flat_bar_and_is_flattened_at_its_close() -> None:
    """NT8 fills the resting order and refuses only a *new* signal there --
    ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat bar"."""
    trades = run([BELOW, BREAKS], signal_at=(0,), force_flat_at=(1,), levels=(float("nan"),))

    assert len(trades) == 1
    assert trades["exit_reason"].iloc[0] == "session_close"
    assert trades["exit_price"].iloc[0] == BREAKS[3]


def test_a_signal_on_the_force_flat_bar_submits_nothing() -> None:
    assert len(run([BELOW, BELOW, BREAKS], signal_at=(1,), force_flat_at=(1,))) == 0
    assert (
        len(run([BELOW, BELOW, BREAKS], signal_at=(1,), force_flat_at=(1,), block_entry_at_close=False)) == 1
    )


def test_a_position_open_when_the_series_ends_is_liquidated_at_the_last_bar() -> None:
    trades = run([BELOW, BREAKS], signal_at=(0,), levels=(float("nan"),))

    assert trades["exit_reason"].iloc[0] == "end_of_data"
    assert trades["exit_price"].iloc[0] == BREAKS[3]


def test_bars_required_holds_the_order_back() -> None:
    assert len(run([BELOW, BREAKS], signal_at=(0,), bars_required=1)) == 0


LEGGED = {"quantities": (1, 1), "levels": (1.0, float("nan"))}
"""Two legs against a one-row buffer, which is what makes an overflow reachable."""


def test_an_overflow_at_the_end_of_the_data_is_reported_rather_than_written_past() -> None:
    count, _ = simulate([BELOW, BREAKS], signal_at=(0,), max_rows=1, **LEGGED)

    assert count == -1


def test_an_overflow_on_the_entry_bar_is_reported_rather_than_written_past() -> None:
    """The entry bar resolves its own bracket, so it has an overflow path of its own."""
    count, _ = simulate([BELOW, STOPS_OUT], signal_at=(0,), max_rows=1, **LEGGED)

    assert count == -1


def test_an_overflow_on_a_later_exit_is_reported_rather_than_written_past() -> None:
    stops_next_bar = (100.0, 105.0, 85.0, 95.0)
    count, _ = simulate([BELOW, BREAKS, stops_next_bar], signal_at=(0,), max_rows=1, **LEGGED)

    assert count == -1


def test_only_the_legs_still_open_are_liquidated_at_the_end_of_the_data() -> None:
    """A leg that already took its target must not be written a second time."""
    trades = run([BELOW, BREAKS], signal_at=(0,), quantities=(1, 1), levels=(0.1, float("nan")))

    assert list(trades["exit_reason"]) == ["target", "end_of_data"]


# -- the output bound, which the dense signal makes load-bearing -----------------


def cash_bars(days: int = 5) -> pd.DataFrame:
    """Random-walk minute bars over whole sessions, wide enough to break a 30-minute range."""
    rng = np.random.default_rng(11)
    n = days * 1440
    index = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0.0, 0.3, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0.0, 0.3, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=index,
    )
    info = sessions.classify(index)
    frame["trading_day"] = info.trading_day

    return frame[info.in_session]


def dataset_for(params: OpeningRangeParams, bars: pd.DataFrame | None = None) -> context.Dataset:
    """A dataset carrying exactly what one combination reads."""
    frame = cash_bars() if bars is None else bars
    grid = sweep.Grid.of(params)

    return context.prepare(frame, grid.required_context(), bar_minutes=1)


def test_the_output_is_sized_from_the_session_cap_not_the_dense_signal() -> None:
    """The signal is true on most bars of the day, so the usual bound would allocate a
    thousandfold more rows than the run can possibly write."""
    params = OpeningRangeParams(bars_required_to_trade=0, max_entries_per_session=1)
    data = dataset_for(params)
    signal = openingrange_signal(data, params)

    bound = entry_bound(data, params, signal)
    assert bound <= int(data.range_session_id().max()) + 1
    assert bound < int(signal.sum()) / 50, "the dense signal is what makes this bound matter"


def test_an_uncapped_combination_falls_back_to_the_signal_count() -> None:
    params = OpeningRangeParams(bars_required_to_trade=0, max_entries_per_session=0)
    data = dataset_for(params)
    signal = openingrange_signal(data, params)

    assert entry_bound(data, params, signal) == int(signal.sum())


# -- end to end through a real dataset -------------------------------------------


def test_no_entry_precedes_its_sessions_range_completing() -> None:
    """The property the archetype is worthless without: the level cannot be known early."""
    params = OpeningRangeParams(bars_required_to_trade=0, window_minutes=30)
    data = dataset_for(params)
    trades = run_openingrange(data, params, NQ)
    assert len(trades), "the fixture produced no trades; the test proves nothing"

    armed = data.range_armed(params.range_key)
    entries = trades["entry_bar"].to_numpy().astype(int)
    # The order is submitted at the close of an armed bar and fills on the next one.
    assert armed[entries - 1].all()


def test_nothing_the_entry_reads_comes_from_a_bar_after_the_signal() -> None:
    """Rewriting every bar after the first entry must not move that entry's own bracket."""
    params = OpeningRangeParams(bars_required_to_trade=0)
    bars = cash_bars()
    first = run_openingrange(dataset_for(params, bars), params, NQ).iloc[0]

    tampered = bars.copy()
    after = int(first["entry_bar"]) + 1
    for column in ("open", "high", "close"):
        tampered.iloc[after:, tampered.columns.get_loc(column)] += 50.0
    tampered.iloc[after:, tampered.columns.get_loc("low")] -= 50.0
    again = run_openingrange(dataset_for(params, tampered), params, NQ).iloc[0]

    for column in ("entry_bar", "entry_price", "initial_stop", "target_price", "risk_points"):
        assert again[column] == pytest.approx(first[column]), column


def test_the_one_shot_default_takes_at_most_one_trade_a_session() -> None:
    params = OpeningRangeParams(bars_required_to_trade=0)
    data = dataset_for(params)
    trades = run_openingrange(data, params, NQ)

    per_session = trades.groupby(data.range_session_id()[trades["entry_bar"].to_numpy().astype(int)])
    assert per_session["trade_id"].nunique().max() == 1


def test_a_grid_sweeps_end_to_end_through_the_registry() -> None:
    """Its ``ContextSpec`` is the only one asking for a session range, so a sweep proves it arrives."""
    bars = cash_bars()
    grid = sweep.Grid.of(
        OpeningRangeParams(bars_required_to_trade=0),
        window_minutes=[15, 30],
        direction=[LONG, SHORT],
    )
    spec = grid.required_context()
    assert spec.range_keys == ((sessionrange.CASH_OPEN_MINUTES, 15), (sessionrange.CASH_OPEN_MINUTES, 30))
    assert spec.atr_periods == (), "no ATR unless a combination selects the ATR stop"

    results, _ = sweep.sweep(bars, grid, NQ, data=context.prepare(bars, spec, bar_minutes=1))

    assert len(results) == 4
    assert results["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    assert "window_minutes" in results.columns
    assert "target_width_multiples" not in results.columns, "a tuple is not a swept axis"


def test_the_atr_stop_asks_for_the_atr_and_the_opposite_stop_does_not() -> None:
    atr_grid = sweep.Grid.of(OpeningRangeParams(stop_mode=ORB_STOP_ATR, atr_period=7))
    opposite = sweep.Grid.of(OpeningRangeParams(stop_mode=ORB_STOP_OPPOSITE, atr_period=7))

    assert atr_grid.required_context().atr_periods == (7,)
    assert opposite.required_context().atr_periods == ()


def test_the_archetype_is_registered_as_tier_1_only() -> None:
    """There is no NinjaScript, so it must not claim a reconciliation it does not have."""
    assert archetypes.OPENINGRANGE.tier2 is archetypes.Tier2Status.TIER1_ONLY
    assert archetypes.for_params(OpeningRangeParams()) is archetypes.OPENINGRANGE


# -- the null this archetype cannot have -----------------------------------------


def test_the_matched_random_null_refuses_a_signal_this_dense() -> None:
    """A level-based trigger fires on every armed bar, so the matched draw is the identity.

    Left unguarded this reports a p-value of 1 and reads as "indistinguishable from random" --
    ``docs/roadmap.md`` §M28.1.
    """
    params = OpeningRangeParams(bars_required_to_trade=0)
    data = dataset_for(params)
    signal = openingrange_signal(data, params)

    with pytest.raises(randomentry.RandomEntryError, match="same signal"):
        randomentry.matched_random_signal(data, signal, np.random.default_rng(0))


# -- the parameter class's own guards ---------------------------------------------


def test_a_two_sided_range_cannot_be_asked_for() -> None:
    with pytest.raises(ValueError, match="not expressible in NT8"):
        OpeningRangeParams(direction=0.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"window_minutes": 0}, "window_minutes must be >= 1"),
        ({"anchor_minutes": -5}, "anchor_minutes must be >= 0"),
        ({"entry_offset_ticks": -1}, "entry_offset_ticks must be >= 0"),
        ({"max_entries_per_session": -1}, "max_entries_per_session must be >= 0"),
        ({"stop_mode": 9}, "unknown stop_mode"),
        ({"target_mode": 9}, "unknown target_mode"),
        ({"atr_period": 0}, "atr_period must be >= 1"),
        ({"stop_offset_ticks": -1}, "stop_offset_ticks must be >= 0"),
        ({"min_bracket_dollars": -1.0}, "min_bracket_dollars must be >= 0"),
        ({"order_quantity": 1}, "cannot fill 4 legs"),
    ],
)
def test_an_impossible_rule_set_is_refused_by_name(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OpeningRangeParams(**kwargs)


def test_the_leg_split_follows_the_selected_target_ladder() -> None:
    """The width ladder has two legs and the R ladder four, so the split has to follow it."""
    assert OpeningRangeParams(order_quantity=4).leg_quantities == (1, 1, 1, 1)
    assert OpeningRangeParams(order_quantity=5, target_mode=ORB_TARGET_WIDTH).leg_quantities == (2, 3)


def test_the_range_key_is_the_anchor_and_the_window() -> None:
    params = OpeningRangeParams(anchor_minutes=0, window_minutes=60)

    assert params.range_key == (0, 60)
    assert params.target_levels == params.target_r_multiples


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase_filter", timeofday.SessionPhase.CASH_OPEN.bit),
        ("regime_filter", regime.Regime.DIRECTIONAL.bit),
        ("volume_filter", volume.VolumeState.HEAVY.bit),
        ("trend_filter", trend.Trend.UP.bit),
        ("higher_timeframe_filter", higher_timeframe.Side.ABOVE.bit),
    ],
)
def test_each_context_filter_narrows_the_signal(field: str, value: int) -> None:
    """§M28's "the five context filters come free by declaring the fields", checked.

    The archetype implements none of them: the shared conjunction in ``sim/filters.py`` reads
    the fields, and the three keyed ones reach their series through this class's own key
    properties. A filter that narrowed nothing would mean one of those was never wired.
    """
    base = OpeningRangeParams(bars_required_to_trade=0)
    filtered = replace(base, **{field: value})

    wide = openingrange_signal(dataset_for(base), base)
    narrow = openingrange_signal(dataset_for(filtered), filtered)

    assert narrow.sum() < wide.sum(), field
    assert not (narrow & ~wide).any(), "a filter added signals rather than removing them"
