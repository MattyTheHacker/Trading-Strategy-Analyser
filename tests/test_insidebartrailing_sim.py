"""InsideBarTrailing simulation tests on hand-built bars.

`InsideBarTrailing.cs` exists, but no Strategy Analyzer trade list has been diffed against this
port, so these pin it against the **C#** rather than against NT8. Two of the rules they pin are
assumptions the C# cannot settle -- when a trailing stop advances, and how often
``OnPositionUpdate`` fires -- and those tests exist to make the assumption visible and to fail
loudly when a trade list overturns it. ``docs/nt8-fidelity.md`` §M23.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, sessions, sweep
from nqbt.archetypes import Tier2Status
from nqbt.instruments import MNQ, NQ
from nqbt.sim import bracket, insidebartrailing
from nqbt.sim.insidebar import insidebar_signal
from nqbt.sim.types import InsideBarParams, InsideBarTrailingParams
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25
FAR_ATR = 40.0
"""An ATR large enough that the bracketed lot's stop and target never bind, so a test about
the trailing lot is about the trailing lot."""

FAR_TRAIL = 4.0
"""And a trail wide enough not to bind on :data:`QUIET` bars, for the mirror-image reason."""


def simulate(  # noqa: PLR0913, PLR0917 - one argument per simulated NT8 property
    rows,
    signal_at=(),
    *,
    max_rows=None,
    direction=LONG,
    atr=FAR_ATR,
    ema=0.0,
    fast_sma=0.0,
    force_flat_at=(),
    quantities=(4, 2),
    atr_multiplier=1.0,
    trail_multiplier=FAR_TRAIL,
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

    ``ema`` and ``fast_sma`` take a scalar or a per-bar sequence and default equal, which is the
    one relationship the trend-violation exit never fires on for either side.
    """
    arr = np.asarray(rows, dtype=np.float64)
    o, h, low, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    def series(value):
        return np.full(n, value, dtype=np.float64) if np.isscalar(value) else np.asarray(value, np.float64)

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
    count = insidebartrailing.simulate_insidebar_trailing(
        o,
        h,
        low,
        c,
        signal,
        direction_at,
        force_flat,
        series(atr),
        series(ema),
        series(fast_sma),
        np.asarray(quantities, dtype=np.int64),
        TICK,
        instrument.point_value,
        atr_multiplier,
        trail_multiplier,
        commission,
        slippage,
        bars_required,
        block_entry_at_close,
        fill_limit_on_touch,
        ambiguity_policy,
        round_targets,
        out,
    )
    return count, out


def run(rows, signal_at=(), **kwargs):
    """:func:`simulate` with the count checked and the matrix turned into a trade log."""
    count, out = simulate(rows, signal_at, **kwargs)
    assert count >= 0, "trade buffer overflowed"
    return validate(trades_to_frame(out, count, instrument=kwargs.get("instrument", MNQ).symbol))


FLAT = (100.0, 100.5, 99.5, 100.0)
"""A one-point bar: the inside-bar range every trailing-stop test below is measured from."""

QUIET = [FLAT] * 8

STOPPED_ON_ENTRY = [FLAT, FLAT, (100.0, 100.5, 90.0, 95.0), *QUIET]
"""Both lots' stops sit inside the entry bar's own range, so both close where they opened."""


# -- the split, which is the structural change ---------------------------------


def test_one_entry_becomes_two_lots_with_their_own_exit_engines() -> None:
    """``EnterLong`` twice, ``entry1`` bracketed and ``entry2`` trailing.

    The whole point of the archetype: one position, two independent brackets, so a leg log
    carries two rows per trade rather than the one ``InsideBar.cs`` produces.
    """
    trades = run(QUIET, signal_at=[1])
    assert list(trades["leg"]) == [1, 2]
    assert list(trades["quantity"]) == [4, 2]
    assert trades["trade_id"].nunique() == 1
    assert list(trades["entry_bar"].unique()) == [2]
    assert trades["entry_price"].nunique() == 1


def test_the_trailing_lot_has_no_profit_target_at_all() -> None:
    """``SetProfitTarget`` is called for ``entry1`` only, so the runner runs."""
    trades = run(QUIET, signal_at=[1])
    assert trades["target_price"].iloc[0] == pytest.approx(100.0 + FAR_ATR)
    assert pd.isna(trades["target_price"].iloc[1])


def test_the_two_lots_carry_their_own_stops_and_their_own_planned_risk() -> None:
    trades = run(QUIET, signal_at=[1], atr=8.0, trail_multiplier=2.0)
    # The bracketed lot: one ATR beyond the inside bar's low. The trailing lot: two inside-bar
    # ranges below the fill.
    assert trades["initial_stop"].iloc[0] == pytest.approx(99.5 - 8.0)
    assert trades["initial_stop"].iloc[1] == pytest.approx(100.0 - 2.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(8.5)
    assert trades["risk_points"].iloc[1] == pytest.approx(2.0)


def test_the_split_rounds_the_bracketed_lot_up() -> None:
    """``(int) Math.Ceiling(OrderQuantity * PartialTakeProfitPercentage)`` -- 4 of 6."""
    assert InsideBarTrailingParams().leg_quantities == (4, 2)
    assert InsideBarTrailingParams(order_quantity=5).leg_quantities == (3, 2)
    assert InsideBarTrailingParams(order_quantity=7, partial_take_profit_percentage=0.5).leg_quantities == (
        4,
        3,
    )


# -- the trailing stop ---------------------------------------------------------

# `SetTrailStop("entry2", CalculationMode.Ticks, (High[1] - Low[1]) / TickSize * mult, false)`,
# read with the signal bar current so `[1]` is the inside bar. When it advances within a bar is
# an assumption -- see the two tests that say so.


def test_the_trail_distance_is_the_inside_bars_range_times_the_multiplier() -> None:
    rows = [
        (100.0, 104.0, 100.0, 100.0),  # 0: the inside bar, a four-point range
        (100.0, 100.5, 99.5, 100.0),  # 1: signal
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=3.0)
    assert trades["initial_stop"].iloc[1] == pytest.approx(100.0 - 12.0)


def test_the_trail_is_anchored_to_the_inside_bar_not_the_signal_bar() -> None:
    """The same indexing ``OnExecutionUpdate`` gives the fixed stop -- ``[1]`` is two back."""
    rows = [
        (100.0, 102.0, 100.0, 100.0),  # 0: the inside bar, a two-point range
        (100.0, 110.0, 90.0, 100.0),  # 1: signal, a twenty-point range that must not be read
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=1.0)
    assert trades["initial_stop"].iloc[1] == pytest.approx(98.0)


def test_the_trail_follows_the_high_water_mark_and_never_retreats() -> None:
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; the stop starts at 99.0 and trails to 99.5
        (100.0, 103.0, 99.6, 102.0),  # 3: new high 103, so the stop trails to 102.0
        (102.0, 102.5, 102.1, 102.2),  # 4: a lower high must not pull the stop back down
        (102.0, 102.5, 101.0, 101.5),  # 5: 101.0 <= 102.0, so the runner stops out here
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=1.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 5
    assert runner["exit_price"] == pytest.approx(102.0)


def test_the_trail_cannot_be_hit_on_the_bar_that_advanced_it() -> None:
    """**An assumption, not evidence.** The trail is bar-close cadence, like the ratchet.

    Bar 3 makes a new high *and* trades below where that new high would put the stop, but not
    below the level standing when the bar opened. A trail that advanced intrabar would exit
    here; this port exits a bar later. Only a trade list settles it -- ``docs/nt8-fidelity.md``
    §M23.
    """
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; the stop ends this bar at 99.5
        (100.0, 103.0, 99.6, 102.0),  # 3: would-be stop 102.0, low 99.6 -- above 99.5
        (102.0, 102.5, 101.0, 101.5),  # 4: the advanced stop finally binds
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=1.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_bar"] == 4, "the stop set at bar 3's close is not live during bar 3"
    assert runner["exit_price"] == pytest.approx(102.0)


def test_the_trail_mirrors_onto_a_shorts_low_water_mark() -> None:
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; the short's stop starts at 101.0 and trails to 100.5
        (100.0, 100.4, 97.0, 98.0),  # 3: new low 97, so the stop trails down to 98.0
        (98.0, 99.0, 97.5, 98.5),  # 4: 99.0 >= 98.0, so the runner stops out here
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], direction=SHORT, trail_multiplier=1.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(98.0)


def test_the_trailing_stop_lands_on_the_tick_grid() -> None:
    """A fractional multiplier puts the distance off the grid, as an ATR multiple does."""
    trades = run(QUIET, signal_at=[1], trail_multiplier=1.3)
    stop = trades["initial_stop"].iloc[1]
    assert stop == pytest.approx(98.75)
    assert stop / TICK == pytest.approx(round(stop / TICK))


def test_an_inside_bar_with_no_range_leaves_the_runner_unprotected_and_is_refused() -> None:
    """The submittability rule applied to the trail: a zero-distance stop is not a stop.

    What NT8 does with ``SetTrailStop(..., 0, false)`` has never been observed, so the port
    refuses the trade rather than running an unprotected lot -- ``docs/nt8-fidelity.md`` §M23.
    """
    rows = [
        (100.0, 100.0, 100.0, 100.0),  # 0: the inside bar, no range at all
        FLAT,  # 1: signal
        *QUIET,
    ]
    assert run(rows, signal_at=[1]).empty
    assert not run([FLAT, FLAT, *QUIET], signal_at=[1]).empty, "the range is the only difference"


def test_an_entry_whose_fixed_stop_is_already_through_the_fill_is_still_skipped() -> None:
    """InsideBar's rule, inherited: neither lot may start life without a live stop."""
    rows = [
        (100.0, 100.5, 99.5, 100.0),  # 0: the inside bar
        (100.0, 100.5, 99.5, 100.0),  # 1: signal
        (90.0, 90.5, 89.5, 90.0),  # 2: gapped below the stop the inside bar implies
        *QUIET,
    ]
    assert run(rows, signal_at=[1], atr=1.0, atr_multiplier=1.0).empty


# -- the trend-violation exit, the second EXIT_SIGNAL consumer ------------------

# `OnPositionUpdate` fires on **position changes**, not on every bar. Which changes NT8 counts,
# and therefore how often this can fire, is a trade-list question -- #67.


def test_a_trend_violation_at_the_entry_flattens_both_lots_at_the_next_open() -> None:
    """``ExitLong("Exit Long Trend Violation", ...)`` for both entries, as a market order."""
    trades = run(QUIET, signal_at=[1], ema=[0.0] * 2 + [-1.0] * 6, fast_sma=0.0)
    assert list(trades["exit_reason"]) == ["signal", "signal"]
    assert list(trades["exit_bar"]) == [3, 3]
    assert list(trades["quantity"]) == [4, 2]
    assert trades["exit_price"].iloc[0] == pytest.approx(100.0)


def test_the_violation_is_not_checked_on_a_bar_where_the_position_did_not_change() -> None:
    """The cadence trap. A per-bar check is a **different strategy** -- ``#67``.

    The averages cross against the position at bar 4, with nothing entering or leaving, and
    nothing happens. This test is the one that fails first if the port is ever "fixed" into a
    per-bar check without a trade list to justify it.
    """
    ema = [0.0] * 4 + [-1.0] * 4
    trades = run(QUIET, signal_at=[1], ema=ema, fast_sma=0.0)
    assert set(trades["exit_reason"]) == {"end_of_data"}


def test_one_lot_leaving_is_a_position_change_that_can_flatten_the_other() -> None:
    """The reachable case: ``entry1`` takes its target, and the runner is checked at that fill."""
    rows = [
        FLAT,  # 0: inside bar
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100, target at 104
        (100.0, 105.0, 99.6, 104.5),  # 3: the bracketed lot takes its target
        *[(104.0, 104.5, 103.5, 104.0)] * 8,
    ]
    ema = [0.0] * 3 + [-1.0] * 9
    trades = run(rows, signal_at=[1], atr=4.0, ema=ema, fast_sma=0.0)
    bracketed = trades[trades["leg"] == 1].iloc[0]
    runner = trades[trades["leg"] == 2].iloc[0]
    assert bracketed["exit_reason"] == "target"
    assert bracketed["exit_bar"] == 3
    assert runner["exit_reason"] == "signal"
    assert runner["exit_bar"] == 4


def test_the_averages_touching_exactly_is_not_a_violation() -> None:
    """``ema[0] < smaFast[0]`` is strict on both sides, so equality holds the position."""
    trades = run(QUIET, signal_at=[1], ema=5.0, fast_sma=5.0)
    assert set(trades["exit_reason"]) == {"end_of_data"}


def test_the_violation_mirrors_onto_a_short() -> None:
    """``ema[0] > smaFast[0]`` for a short -- the same comparison through the sign multiplier."""
    rising = run(QUIET, signal_at=[1], direction=SHORT, ema=[0.0] * 2 + [1.0] * 6, fast_sma=0.0)
    falling = run(QUIET, signal_at=[1], direction=SHORT, ema=[0.0] * 2 + [-1.0] * 6, fast_sma=0.0)
    assert set(rising["exit_reason"]) == {"signal"}
    assert set(falling["exit_reason"]) == {"end_of_data"}


def test_the_signal_exit_pays_slippage_in_the_adverse_direction() -> None:
    trades = run(QUIET, signal_at=[1], ema=[0.0] * 2 + [-1.0] * 6, slippage=2.0)
    assert trades["exit_price"].iloc[0] == pytest.approx(100.0 - 2 * TICK)


# -- the shared exits, which both lots reach independently ---------------------


def test_the_session_close_flattens_both_lots() -> None:
    trades = run(QUIET, signal_at=[1], force_flat_at=[4])
    assert list(trades["exit_reason"]) == ["session_close", "session_close"]
    assert list(trades["exit_bar"]) == [4, 4]


def test_a_position_open_at_the_last_bar_liquidates_every_lot_there() -> None:
    trades = run(QUIET, signal_at=[1])
    assert list(trades["exit_reason"]) == ["end_of_data", "end_of_data"]
    assert list(trades["exit_bar"]) == [len(QUIET) - 1] * 2


def test_the_entry_orders_are_cancelled_at_the_flatten_point() -> None:
    assert run(QUIET, signal_at=[1], force_flat_at=[2]).empty


def test_a_signal_on_a_force_flat_bar_is_blocked_when_asked() -> None:
    """``block_entry_at_session_close`` guards a *new* signal; the cancel above guards a resting
    order. Two rules, and the flag only ever meant the first."""
    assert run(QUIET, signal_at=[1], force_flat_at=[1]).empty
    assert not run(QUIET, signal_at=[1], force_flat_at=[1], block_entry_at_close=False).empty


def test_a_signal_while_already_in_a_position_does_not_pyramid() -> None:
    assert list(run(QUIET, signal_at=[1, 4])["entry_bar"].unique()) == [2]


def test_the_trail_stays_off_the_grid_when_rounding_is_switched_off() -> None:
    """The same switch that governs the target, reaching the trail at both ends of its life."""
    trades = run(QUIET, signal_at=[1], trail_multiplier=1.3, round_targets=False)
    assert trades["initial_stop"].iloc[1] == pytest.approx(98.7)


@pytest.mark.parametrize(
    ("kwargs", "path"),
    [
        ({}, "the end of the data"),
        ({"force_flat_at": [4]}, "the session close, through the shared engine"),
        ({"atr": 0.5, "trail_multiplier": 1.0, "rows": STOPPED_ON_ENTRY}, "a stop on the entry bar"),
        ({"ema": [0.0] * 2 + [-1.0] * 6}, "the trend-violation exit"),
    ],
)
def test_the_buffer_overflowing_is_reported_rather_than_written_past(kwargs, path) -> None:
    """Two lots per trade, so a buffer sized for one leg overflows on whichever exit fires.

    Every path that writes a leg has to report the overflow rather than silently drop the
    second lot, which is why this is parametrised over all four rather than over the easiest.
    """
    rows = kwargs.pop("rows", QUIET)
    count, _ = simulate(rows, signal_at=[1], max_rows=1, **kwargs)
    assert count == -1, path


# -- the parameters, and the dead branch ---------------------------------------


def test_the_defaults_are_not_insidebars_and_the_difference_is_not_cosmetic() -> None:
    """Ten times the breakout buffer is a different strategy, not a tweak."""
    trailing, plain = InsideBarTrailingParams(), InsideBarParams()
    assert trailing.error_margin == pytest.approx(plain.error_margin * 10)
    assert trailing.slow_sma_period == 125
    assert trailing.order_quantity == 6
    assert trailing.no_entry_minutes_before_close == 0, "this NinjaScript has no session guard"
    assert plain.no_entry_minutes_before_close == 60


def test_the_max_loss_branch_is_dead_and_may_not_be_switched_on() -> None:
    """``MaximumLossPerTrade`` defaults to 0 and its own branch requires it > 0.

    Enabling it means a currency amount, which has to go through ``instruments.py`` before it
    can mean the same thing on NQ and MNQ -- ``docs/nt8-fidelity.md`` §M23.
    """
    assert InsideBarTrailingParams().maximum_loss_per_trade == 0.0
    with pytest.raises(ValueError, match="unreachable in the NinjaScript"):
        InsideBarTrailingParams(maximum_loss_per_trade=200.0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"order_quantity": 1}, "must be >= 2 to split"),
        ({"partial_take_profit_percentage": 0.95}, r"must be in \[0, 0.9\]"),
        ({"partial_take_profit_percentage": -0.1}, r"must be in \[0, 0.9\]"),
        ({"trailing_stop_multiplier": 0.5}, "must be >= 1"),
        ({"partial_take_profit_percentage": 0.0}, "lot of zero contracts"),
    ],
)
def test_a_configuration_that_cannot_produce_two_lots_is_refused(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        InsideBarTrailingParams(**overrides)


def test_the_inherited_validation_still_applies() -> None:
    with pytest.raises(ValueError, match="error_margin"):
        InsideBarTrailingParams(error_margin=1.5)


# -- the shared entry, over a real prepared dataset ----------------------------


SESSION_CLOSE = "2024-01-16 22:00"
"""17:00 ET, and the last bar of every frame below -- see ``tests/test_insidebar_sim.py``."""


def frame(rows, start="2024-01-16 15:00") -> pd.DataFrame:
    """Hand-written bars on a minute index, with the session closed by a copy of the last."""
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


def prepared(bars: pd.DataFrame, params):
    """The dataset the archetype's own ``ContextSpec`` asks for."""
    return context.prepare(bars, sweep.Grid.of(params).required_context())


def signalling(**overrides) -> InsideBarTrailingParams:
    """Short periods, so three real averages sit under a rising close on hand-built bars."""
    defaults = {
        "ema_period": 2,
        "fast_sma_period": 2,
        "slow_sma_period": 2,
        "atr_length": 2,
        "bars_required_to_trade": 0,
    }
    return InsideBarTrailingParams(**{**defaults, **overrides})


BREAKOUT = [
    (100.0, 110.0, 90.0, 100.0),  # 0: the mother bar
    (100.0, 105.0, 95.0, 101.0),  # 1: inside it
    (101.0, 120.0, 100.0, 115.0),  # 2: the close breaks out above
]


def test_the_entry_is_insidebars_and_not_a_second_copy_of_it() -> None:
    """One entry rule, two sets of defaults -- the reason the params class subclasses.

    Given the same values for every field the entry reads, the two archetypes must produce the
    same signal array bar for bar; a forked entry would drift silently.
    """
    trailing = signalling(error_margin=0.01, no_entry_minutes_before_close=60)
    plain = InsideBarParams(
        ema_period=2,
        fast_sma_period=2,
        slow_sma_period=2,
        atr_length=2,
        bars_required_to_trade=0,
    )
    data = prepared(frame(BREAKOUT), trailing)
    assert np.array_equal(insidebar_signal(data, trailing), insidebar_signal(data, plain))
    assert insidebar_signal(data, trailing)[2]


def test_the_larger_error_margin_refuses_a_break_the_smaller_one_takes() -> None:
    """The mother bar's range is 20, so 0.01 asks for 0.2 of clearance and 0.1 asks for 2."""
    rows = [*BREAKOUT[:2], (101.0, 111.0, 100.0, 111.0)]  # a close 1.0 above the mother's high
    data = prepared(frame(rows), signalling())
    assert not insidebar_signal(data, signalling())[2]
    assert insidebar_signal(data, signalling(error_margin=0.01))[2]


def test_a_run_produces_a_valid_leg_log_on_both_instruments() -> None:
    """Everything monetary goes through ``instruments.py``: same geometry, ten times the P&L."""
    params = signalling(atr_multiplier=2.0)
    bars = frame([*BREAKOUT, (115.0, 116.0, 114.0, 115.0), *[(116.0, 117.0, 115.0, 116.0)] * 3])
    data = prepared(bars, params)

    mnq = insidebartrailing.run_insidebartrailing(data, params, MNQ)
    nq = insidebartrailing.run_insidebartrailing(data, params, NQ)
    assert list(mnq["leg"]) == [1, 2]
    assert list(mnq["quantity"]) == [4, 2]
    assert mnq["entry_bar"].iloc[0] == 3
    assert nq["entry_price"].iloc[0] == pytest.approx(mnq["entry_price"].iloc[0])
    assert mnq["gross_pnl"].abs().sum() > 0, "a ten-times assertion on zero proves nothing"
    assert list(nq["gross_pnl"]) == pytest.approx(list(mnq["gross_pnl"] * 10.0))


# -- the registry --------------------------------------------------------------


def test_the_archetype_is_registered_and_claims_no_ninjatrader_evidence() -> None:
    """``TIER1_ONLY`` until a trade list settles the trail and the exit cadence -- ``#67``."""
    assert archetypes.get("InsideBarTrailing") is archetypes.INSIDEBARTRAILING
    assert archetypes.INSIDEBARTRAILING.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.for_params(InsideBarTrailingParams()) is archetypes.INSIDEBARTRAILING
    assert archetypes.for_params(InsideBarParams()) is archetypes.INSIDEBAR


def test_the_split_lot_axes_are_sweepable_despite_being_inherited() -> None:
    """``sweepable`` reads ``dataclasses.fields()``, which is what makes a subclass safe.

    ``__slots__`` holds only the fields declared on the class itself, so reading it would drop
    every axis InsideBarTrailing inherits -- see #60.
    """
    axes = archetypes.INSIDEBARTRAILING.sweepable
    assert {"trailing_stop_multiplier", "partial_take_profit_percentage"} <= axes
    assert {"error_margin", "atr_multiplier", "phase_filter"} <= axes
