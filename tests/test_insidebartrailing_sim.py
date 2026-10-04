"""InsideBarTrailing simulation tests on hand-built bars.

The rules the trade list settled are pinned here; the measurements that settled them are in
``docs/nt8-fidelity.md``, "Reconciliation result -- InsideBarTrailing". Prices are kept small
and round so the arithmetic is checkable by eye.
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, sessions, sweep
from nqbt.archetypes import Tier2Status
from nqbt.instruments import MNQ, NQ
from nqbt.sim import bracket, filters, insidebartrailing
from nqbt.sim.insidebar import insidebar_direction, insidebar_patterns, insidebar_signal, insidebar_trends
from nqbt.sim.types import (
    EARLINESS_FIRST_BREAKOUT,
    EARLINESS_OFF,
    EARLINESS_SMA_EXTENSION,
    EARLINESS_TREND_AGE,
    InsideBarParams,
    InsideBarTrailingParams,
    sizing_labels,
)
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25
FAR_ATR = 40.0
"""An ATR large enough that the bracketed lot's stop and target never bind, so a test about
the trailing lot is about the trailing lot."""

FAR_TRAIL = 10.0
"""And a trail wide enough not to bind on :data:`QUIET` bars, for the mirror-image reason."""


def fixed_sizing(quantities, n):
    """Size every entry with one split, which is the NinjaScript as ported."""
    return bracket.Sizing(np.asarray([quantities], dtype=np.int64), np.zeros(n, dtype=np.int64))


def simulate(  # noqa: PLR0913 - one argument per simulated NT8 property
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
    sizing=None,
    atr_multiplier=1.0,
    tp_multiplier=1.0,
    trail_multiplier=FAR_TRAIL,
    loss_gate=0.0,
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    bars_required=-1,
    block_entry_at_close=True,
    max_hold_bars=0,
    fill_limit_on_touch=True,
    ambiguity_policy=0,
    round_targets=True,
    structure_bars: int = 0,
    structure_cushion_atr: float = 0.0,
    breakeven: bracket.Breakeven = bracket.BREAKEVEN_OFF,
):
    """Simulate hand-written OHLC rows.

    ``ema`` and ``fast_sma`` take a scalar or a per-bar sequence and default equal, which the
    trend-violation exit never fires on for either side. ``loss_gate`` defaults off, unlike the
    NinjaScript's $200; the gate has its own tests below.
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
        bracket.Bars(o, h, low, c, force_flat),
        signal,
        direction_at,
        series(atr),
        insidebartrailing.TrendAverages(series(ema), series(fast_sma)),
        sizing if sizing is not None else fixed_sizing(quantities, n),
        bracket.Costs(TICK, instrument.point_value, commission, slippage),
        bracket.FillRules(fill_limit_on_touch, ambiguity_policy, round_targets),
        insidebartrailing.InsideBarTrailingRules(
            atr_multiplier=atr_multiplier,
            tp_multiplier=tp_multiplier,
            trailing_stop_multiplier=trail_multiplier,
            position_update_loss_gate=loss_gate,
            bars_required=bars_required,
            block_entry_at_session_close=block_entry_at_close,
            max_hold_bars=max_hold_bars,
            breakeven=breakeven,
            structure_trail_bars=structure_bars,
            structure_trail_cushion_atr=structure_cushion_atr,
        ),
        out,
    )

    return count, out


def run(rows, signal_at=(), **kwargs):
    """Run :func:`simulate` with the count checked and the matrix turned into a trade log."""
    count, out = simulate(rows, signal_at, **kwargs)
    assert count >= 0, "trade buffer overflowed"

    return validate(trades_to_frame(out, count, instrument=kwargs.get("instrument", MNQ).symbol))


FLAT = (100.0, 100.5, 99.5, 100.0)
"""A one-point bar: the inside-bar range every trailing-stop test below is measured from."""

QUIET = [FLAT] * 8

# Bar 3 stops the runner out, leaving the bracketed lot for the trend violation to flatten.
PARTIAL = [
    FLAT,  # 0: inside bar, range 1.0
    FLAT,  # 1: signal
    FLAT,  # 2: fill at 100; trail starts at 96.0 and the entry bar advances it to 96.5
    (100.0, 100.5, 95.0, 95.5),  # 3: 95.0 <= 96.5, so the runner stops out at 96.5
    *QUIET,
]

STOPPED_ON_ENTRY = [FLAT, FLAT, (100.0, 100.5, 90.0, 95.0), *QUIET]
"""Both lots' stops sit inside the entry bar's own range, so both close where they opened."""

VIOLATED_AT_THE_CHANGE = [0.0] * 2 + [-1.0] * 10
"""An EMA below the fast SMA from bar 2 on, which is the bar :data:`PARTIAL`'s change reads."""


# -- the split, which is the structural change ---------------------------------


def test_one_entry_becomes_two_lots_with_their_own_exit_engines() -> None:
    """``EnterLong`` twice, ``entry1`` bracketed and ``entry2`` trailing.

    One position, two independent brackets, so a leg log carries two rows per trade rather than
    the one ``InsideBar.cs`` produces -- ``docs/nt8-fidelity.md`` §M23.
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
    # ranges below the fill, which is where it starts before it trails.
    assert trades["initial_stop"].iloc[0] == pytest.approx(99.5 - 8.0)
    assert trades["initial_stop"].iloc[1] == pytest.approx(100.0 - 2.0)
    assert trades["risk_points"].iloc[0] == pytest.approx(8.5)
    assert trades["risk_points"].iloc[1] == pytest.approx(2.0)


def test_the_tp_multiplier_scales_the_bracketed_lots_target_only() -> None:
    """The field is inherited from :class:`InsideBarParams`, and the runner has no target
    for it to reach -- ``docs/nt8-fidelity.md`` §M22."""
    trades = run(QUIET, signal_at=[1], tp_multiplier=2.5)
    assert trades["target_price"].iloc[0] == pytest.approx(100.0 + 2.5 * FAR_ATR)
    assert pd.isna(trades["target_price"].iloc[1])


def test_a_tp_multiplier_below_insidebars_nt8_floor_is_accepted() -> None:
    """InsideBarTrailing.cs has no TPMultiplier, so InsideBar.cs's Range(0.1, ...) does not bind it."""
    below_insidebars_floor = 0.05
    assert (
        InsideBarTrailingParams(tp_multiplier=below_insidebars_floor).tp_multiplier == below_insidebars_floor
    )
    with pytest.raises(ValueError, match=r"tp_multiplier must be >= 0\.1"):
        InsideBarParams(tp_multiplier=below_insidebars_floor)


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
# read with the signal bar current so `[1]` is the inside bar.


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


def test_the_trail_advances_on_the_entry_bar_and_can_be_hit_there() -> None:
    """The entry bar is the one bar the trail follows within -- ``docs/nt8-fidelity.md`` §M23."""
    trades = run(QUIET, signal_at=[1], trail_multiplier=1.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    # Entry at 100.0 and the entry bar's high 100.5, so the trail advances to 99.5 and the
    # bar's own low reaches it. Where it started, 99.0, is what the log keeps as initial_stop.
    assert runner["initial_stop"] == pytest.approx(99.0)
    assert runner["exit_bar"] == runner["entry_bar"] == 2
    assert runner["exit_price"] == pytest.approx(99.5)


def test_after_the_entry_bar_the_trail_cannot_be_hit_on_the_bar_that_advanced_it() -> None:
    """A resting trail advances at the bar close, not within the bar -- ``docs/nt8-fidelity.md`` §M23.

    Bar 3 makes a new high *and* trades below where that new high would put the stop, but not
    below the level standing when the bar opened.
    """
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; trail 98.5 after the entry bar's own advance
        (100.0, 103.0, 100.6, 102.0),  # 3: would-be stop 101.0, low 100.6 -- above 98.5
        (102.0, 102.5, 100.5, 101.0),  # 4: the advanced stop finally binds
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=2.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_bar"] == 4, "the stop set at bar 3's close is not live during bar 3"
    assert runner["exit_price"] == pytest.approx(101.0)


def test_the_trail_follows_the_high_water_mark_and_never_retreats() -> None:
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; trail 98.5
        (100.0, 103.0, 99.6, 102.0),  # 3: new high 103, so the stop trails to 101.0
        (102.0, 102.5, 102.1, 102.2),  # 4: a lower high must not pull the stop back down
        (102.0, 102.5, 100.5, 101.0),  # 5: 100.5 <= 101.0, so the runner stops out here
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], trail_multiplier=2.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 5
    assert runner["exit_price"] == pytest.approx(101.0)


def test_the_trail_mirrors_onto_a_shorts_low_water_mark() -> None:
    rows = [
        FLAT,  # 0: inside bar, range 1.0
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; the short's trail is 99.5 + 2.0 = 101.5
        (100.0, 100.4, 97.0, 98.0),  # 3: new low 97, so the stop trails down to 99.0
        (98.0, 99.5, 97.5, 98.5),  # 4: 99.5 >= 99.0, so the runner stops out here
        *QUIET,
    ]
    trades = run(rows, signal_at=[1], direction=SHORT, trail_multiplier=2.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(99.0)


def test_the_trailing_stop_lands_on_the_tick_grid() -> None:
    """A fractional multiplier puts the distance off the grid, as an ATR multiple does."""
    trades = run(QUIET, signal_at=[1], trail_multiplier=1.3)
    stop = trades["initial_stop"].iloc[1]
    assert stop == pytest.approx(98.75)
    assert stop / TICK == pytest.approx(round(stop / TICK))


def test_the_trail_stays_off_the_grid_when_rounding_is_switched_off() -> None:
    """The same switch that governs the target, reaching the trail at both ends of its life."""
    trades = run(QUIET, signal_at=[1], trail_multiplier=1.3, round_targets=False)
    assert trades["initial_stop"].iloc[1] == pytest.approx(98.7)


def test_an_inside_bar_with_no_range_leaves_the_runner_unprotected_and_is_refused() -> None:
    """The submittability rule applied to the trail: a zero-distance stop is not a stop.

    What NT8 does with ``SetTrailStop(..., 0, false)`` is unobserved, so the port refuses the
    entry rather than running an unprotected lot.
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


# -- the structure trail (#352) ------------------------------------------------

BROKEN_UPWARD = [
    FLAT,  # 0: inside bar, range 1.0
    FLAT,  # 1: signal
    FLAT,  # 2: fill at 100; the runner's stop starts at 90.0 and box {0, 1} is unbroken
    (100.0, 103.0, 99.6, 102.5),  # 3: closes above box {1, 2}'s 100.5, so the stop goes to 100.0
    (102.5, 104.0, 100.1, 103.5),  # 4: closes above box {2, 3}'s 103.0: (103.0 + 99.5) / 2 = 101.25
    (103.5, 103.6, 101.0, 101.5),  # 5: 101.0 <= 101.25, so the runner stops out here
    *QUIET,
]


def runner_leg(trades: pd.DataFrame) -> pd.Series:
    """Return the trailing lot's one leg."""
    return trades[trades["leg"] == 2].iloc[0]


def test_the_structure_trail_moves_the_runner_to_the_midpoint_of_each_box_its_close_broke() -> None:
    """Each close above the two bars before it moves the runner's stop to their midpoint."""
    runner = runner_leg(run(BROKEN_UPWARD, signal_at=[1], structure_bars=2))
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 5
    assert runner["exit_price"] == pytest.approx(101.25)


def test_a_structure_stop_cannot_be_hit_on_the_bar_whose_close_set_it() -> None:
    """Bar 3 trades under the 100.0 its own close sets, and the runner survives it."""
    rows = [*BROKEN_UPWARD[:4], (102.5, 102.6, 99.9, 100.2), *QUIET]
    runner = runner_leg(run(rows, signal_at=[1], structure_bars=2))
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(100.0)


def test_a_high_through_the_box_or_a_close_on_its_edge_moves_nothing() -> None:
    """Only a close strictly beyond the box is a break."""
    rows = [
        *BROKEN_UPWARD[:3],
        (100.0, 103.0, 99.6, 100.5),  # 3: the high breaks box {1, 2} and the close only reaches it
        (100.5, 100.6, 99.6, 100.0),  # 4: under the 100.0 a break would have set
        *QUIET,
    ]
    runner = runner_leg(run(rows, signal_at=[1], structure_bars=2))
    assert runner["exit_reason"] == "end_of_data"


def test_the_structure_stop_never_loosens() -> None:
    """A break whose midpoint sits behind the standing stop leaves it there."""
    rows = [
        *BROKEN_UPWARD[:3],
        (106.0, 110.0, 106.0, 109.0),  # 3: gaps up and closes above box {1, 2}: the stop goes to 100.0
        (109.0, 109.5, 107.0, 108.0),  # 4: inside box {2, 3}'s 110.0
        (108.0, 110.5, 101.0, 110.25),  # 5: above box {3, 4}: (110.0 + 106.0) / 2 = 108.0
        (110.25, 111.0, 108.5, 110.75),  # 6: above box {4, 5} too, but (110.5 + 101.0) / 2 is lower
        (110.75, 110.8, 107.0, 107.5),  # 7: 107.0 <= 108.0, and would clear 105.75
        *QUIET,
    ]
    runner = runner_leg(run(rows, signal_at=[1], structure_bars=2))
    assert runner["exit_bar"] == 7
    assert runner["exit_price"] == pytest.approx(108.0)


def test_the_cushion_is_in_atrs_read_on_the_signal_bar() -> None:
    """Half of the signal bar's 2.0 puts the stop at 99.0; the 8.0 on every other bar would put it at 96.0."""
    rows = [*BROKEN_UPWARD[:4], (102.5, 102.6, 98.9, 99.5), *QUIET]
    atr = [8.0] * len(rows)
    atr[1] = 2.0
    runner = runner_leg(
        run(
            rows,
            signal_at=[1],
            atr=atr,
            atr_multiplier=20.0,
            tp_multiplier=20.0,
            structure_bars=2,
            structure_cushion_atr=0.5,
        ),
    )
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(99.0)


def test_the_structure_trail_mirrors_onto_a_short() -> None:
    """A close below the box moves a short's stop down to its midpoint."""
    rows = [
        *BROKEN_UPWARD[:3],  # 2: fill at 100; the short runner's stop starts at 110.0
        (100.0, 100.4, 97.0, 97.5),  # 3: closes below box {1, 2}'s 99.5, so the stop goes to 100.0
        (97.5, 99.9, 96.0, 96.5),  # 4: closes below box {2, 3}'s 97.0: (100.5 + 97.0) / 2 = 98.75
        (96.5, 99.0, 96.4, 98.5),  # 5: 99.0 >= 98.75
        *QUIET,
    ]
    runner = runner_leg(run(rows, signal_at=[1], direction=SHORT, structure_bars=2))
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 5
    assert runner["exit_price"] == pytest.approx(98.75)


def test_the_structure_trail_starts_at_the_same_stop_and_does_not_follow_the_entry_bar() -> None:
    """The high-water trail stops this runner out on its entry bar -- see the §M23 test above."""
    high_water = runner_leg(run(QUIET, signal_at=[1], trail_multiplier=1.0))
    structure = runner_leg(run(QUIET, signal_at=[1], trail_multiplier=1.0, structure_bars=2))
    assert structure["initial_stop"] == high_water["initial_stop"] == pytest.approx(99.0)
    assert high_water["exit_bar"] == 2
    assert structure["exit_reason"] == "end_of_data"


@pytest.mark.parametrize(("round_targets", "level"), [(True, 100.25), (False, 100.125)])
def test_a_structure_stop_lands_on_the_tick_grid_only_where_targets_do(
    round_targets: bool, level: float
) -> None:
    """A midpoint between two ticks snaps to the grid under the switch that snaps the targets."""
    rows = [
        FLAT,  # 0: inside bar
        (100.0, 100.75, 99.5, 100.0),  # 1: signal
        FLAT,  # 2: fill at 100
        (100.0, 101.0, 100.0, 101.0),  # 3: above box {1, 2}'s 100.75: (100.75 + 99.5) / 2 = 100.125
        (101.0, 101.0, 100.0, 100.5),  # 4: reaches the level either way
        *QUIET,
    ]
    runner = runner_leg(run(rows, signal_at=[1], structure_bars=2, round_targets=round_targets))
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(level)


def test_a_half_tick_midpoint_rounds_up_on_a_short_as_every_snapped_level_does() -> None:
    """``round_to_tick`` rounds a half tick up whichever the side, so a short's stop lands half a tick looser."""
    rows = [
        FLAT,  # 0: inside bar
        (100.0, 100.5, 99.25, 100.0),  # 1: signal
        FLAT,  # 2: fill at 100
        (100.0, 100.0, 99.0, 99.0),  # 3: below box {1, 2}'s 99.25: (100.5 + 99.25) / 2 = 99.875
        (99.0, 100.0, 99.0, 99.5),  # 4: reaches 100.0
        *QUIET,
    ]
    runner = runner_leg(run(rows, signal_at=[1], direction=SHORT, structure_bars=2))
    assert runner["exit_bar"] == 4
    assert runner["exit_price"] == pytest.approx(100.0)


def test_a_box_reaching_before_the_first_bar_reads_the_bars_there_are() -> None:
    """NT8's ``MAX`` and ``MIN`` read what there is, and a box of no bars at all is no level."""
    arr = np.asarray([FLAT, (100.0, 102.0, 100.0, 101.5)], dtype=np.float64)
    bars = bracket.Bars(arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], np.zeros(2, dtype=np.bool_))
    costs = bracket.Costs(TICK, MNQ.point_value, 0.0, 0.0)
    fills = bracket.FillRules(fill_limit_on_touch=True, ambiguity_policy=0, round_targets=True)
    one_bar = insidebartrailing.structure_level(bars, 1, 1, 0.0, costs, fills, LONG)
    assert (
        insidebartrailing.structure_level(bars, 1, 5, 0.0, costs, fills, LONG)
        == one_bar
        == pytest.approx(100.0)
    )
    assert np.isnan(insidebartrailing.structure_level(bars, 0, 1, 0.0, costs, fills, LONG))
    assert np.isnan(insidebartrailing.structure_level(bars, 1, 0, 0.0, costs, fills, LONG))


@pytest.mark.parametrize(
    ("offset_ticks", "runner_exit", "bracketed_exit"),
    [
        # The runner's structure stop passes the breakeven's 100.0; the bracketed lot keeps 100.0.
        (0.0, (5, 101.25), (6, 100.0)),
        # The breakeven's 102.0 sits above the structure's 100.0 on both lots.
        (8.0, (4, 102.0), (4, 102.0)),
    ],
)
def test_the_breakeven_and_the_structure_stop_hold_whichever_is_nearer_the_market(
    offset_ticks: float,
    runner_exit: tuple[int, float],
    bracketed_exit: tuple[int, float],
) -> None:
    """Bar 3's close is 1R on a 2.5-point risk, which moves both lots to the entry plus the offset."""
    breakeven = bracket.Breakeven(
        1.0, bracket.BREAKEVEN_R, bracket.BREAKEVEN_ON_CLOSE, offset_ticks, bracket.NO_ATR
    )
    trades = run(
        BROKEN_UPWARD, signal_at=[1], atr=2.0, tp_multiplier=20.0, structure_bars=2, breakeven=breakeven
    )
    for leg, (exit_bar, exit_price) in ((2, runner_exit), (1, bracketed_exit)):
        exited = trades[trades["leg"] == leg].iloc[0]
        assert exited["exit_reason"] == "stop"
        assert (exited["exit_bar"], exited["exit_price"]) == (exit_bar, pytest.approx(exit_price))


def test_a_structure_stop_hit_can_trigger_the_trend_violation() -> None:
    """The bracketed lot leaves at the runner's fill, as it does behind the high-water trail (§M23)."""
    rows = [
        FLAT,  # 0: inside bar
        (100.0, 100.5, 97.5, 100.0),  # 1: signal
        FLAT,  # 2: fill at 100
        (100.0, 101.0, 99.8, 100.75),  # 3: above box {1, 2}'s 100.5: (100.5 + 97.5) / 2 = 99.0
        (100.75, 100.8, 99.2, 99.5),  # 4: under water at the close, and the EMA crosses under
        (99.5, 99.6, 98.5, 98.8),  # 5: 98.5 <= 99.0
        *QUIET,
    ]
    ema = [0.0] * 4 + [-1.0] * (len(rows) - 4)
    trades = run(rows, signal_at=[1], ema=ema, structure_bars=2)
    runner = runner_leg(trades)
    bracketed = trades[trades["leg"] == 1].iloc[0]
    assert (runner["exit_reason"], runner["exit_bar"], runner["exit_price"]) == (
        "stop",
        5,
        pytest.approx(99.0),
    )
    assert (bracketed["exit_reason"], bracketed["exit_bar"], bracketed["exit_price"]) == (
        "signal",
        5,
        pytest.approx(99.0),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"structure_trail_bars": -1}, "structure_trail_bars must be >= 0"),
        ({"structure_trail_bars": 2, "structure_trail_cushion_atr": -0.5}, "must be >= 0 and finite"),
        ({"structure_trail_bars": 2, "structure_trail_cushion_atr": float("nan")}, "must be >= 0 and finite"),
        ({"structure_trail_bars": 2, "structure_trail_cushion_atr": float("inf")}, "must be >= 0 and finite"),
        ({"structure_trail_cushion_atr": 0.5}, "structure_trail_bars is 0"),
    ],
)
def test_a_structure_trail_out_of_range_or_with_an_unread_cushion_is_refused(
    overrides: dict[str, float],
    message: str,
) -> None:
    """A negative box, a cushion that is negative or not finite, or a cushion with the trail off, raises."""
    with pytest.raises(ValueError, match=message):
        InsideBarTrailingParams(**overrides)


def test_the_structure_trail_is_off_by_default_and_a_row_using_it_leaves_the_port() -> None:
    """No NinjaScript has the structure trail, so a row using it is ``TIER1_ONLY``."""
    params = InsideBarTrailingParams()
    assert (params.structure_trail_bars, params.structure_trail_cushion_atr) == (0, 0.0)
    assert archetypes.INSIDEBARTRAILING.tier2_for(params) is Tier2Status.RECONCILED
    on = InsideBarTrailingParams(structure_trail_bars=3, structure_trail_cushion_atr=0.25)
    assert archetypes.INSIDEBARTRAILING.tier2_for(on) is Tier2Status.TIER1_ONLY


def test_the_cushion_is_dead_without_the_structure_trail() -> None:
    """Sweeping the cushion with the trail off is refused as an inert axis, and with it on is two cells."""
    archetype = archetypes.INSIDEBARTRAILING
    assert {"structure_trail_bars", "structure_trail_cushion_atr"} <= archetype.sweepable
    with pytest.raises(
        sweep.SweepError, match=r"structure_trail_cushion_atr \(inert while structure_trail_bars is 0\)"
    ):
        sweep.Grid.of(InsideBarTrailingParams(), archetype=archetype, structure_trail_cushion_atr=[0.0, 0.5])

    on = InsideBarTrailingParams(structure_trail_bars=2)
    assert len(sweep.Grid.of(on, archetype=archetype, structure_trail_cushion_atr=[0.0, 0.5])) == 2


# -- the trend-violation exit, the second EXIT_SIGNAL consumer ------------------

# `OnPositionUpdate` fires on position changes -- ``docs/nt8-fidelity.md`` §M23.


def test_one_lot_leaving_flattens_the_other_at_that_same_fill() -> None:
    """The remaining lot leaves at the price and bar the triggering exit filled at, not at the next open.

    ``docs/nt8-fidelity.md`` §M23.
    """
    trades = run(PARTIAL, signal_at=[1], ema=VIOLATED_AT_THE_CHANGE, trail_multiplier=4.0)
    runner = trades[trades["leg"] == 2].iloc[0]
    bracketed = trades[trades["leg"] == 1].iloc[0]
    assert runner["exit_reason"] == "stop"
    assert bracketed["exit_reason"] == "signal"
    assert bracketed["exit_bar"] == runner["exit_bar"] == 3
    assert bracketed["exit_price"] == pytest.approx(runner["exit_price"])


def test_nothing_leaving_means_no_position_change_to_check() -> None:
    """The trend violation is checked on a position change, never per bar.

    The averages cross against the position at bar 4 with nothing entering or leaving, and
    nothing happens.
    """
    trades = run(QUIET, signal_at=[1], ema=[0.0] * 4 + [-1.0] * 4)
    assert set(trades["exit_reason"]) == {"end_of_data"}


def test_the_entry_fill_alone_cannot_fire_it() -> None:
    """The entry is a position change, but nothing has left for the exit to fill alongside."""
    trades = run(QUIET, signal_at=[1], ema=[-1.0] * 8)
    assert set(trades["exit_reason"]) == {"end_of_data"}


def test_the_averages_touching_exactly_is_not_a_violation() -> None:
    """``ema[0] < smaFast[0]`` is strict on both sides, so equality holds the position."""
    trades = run(PARTIAL, signal_at=[1], ema=5.0, fast_sma=5.0, trail_multiplier=4.0)
    assert "signal" not in set(trades["exit_reason"])


def test_the_averages_are_read_at_the_bar_before_the_fill() -> None:
    """``OnPositionUpdate`` runs at strategy time ``i - 1``, the offset ``OnExecutionUpdate`` has.

    The violation is on bar 2 only, and it still fires for the change on bar 3; a version
    reading bar 3's averages instead would hold the position.
    """
    prior = [0.0, 0.0, -1.0] + [0.0] * 9
    at_fill = [0.0, 0.0, 0.0, -1.0] + [0.0] * 8
    assert "signal" in set(run(PARTIAL, signal_at=[1], ema=prior, trail_multiplier=4.0)["exit_reason"])
    assert "signal" not in set(run(PARTIAL, signal_at=[1], ema=at_fill, trail_multiplier=4.0)["exit_reason"])


def test_the_violation_mirrors_onto_a_short() -> None:
    """``ema[0] > smaFast[0]`` for a short -- the same comparison through the sign multiplier."""
    rows = [
        FLAT,  # 0: inside bar
        FLAT,  # 1: signal
        FLAT,  # 2: fill at 100; the short's trail is 99.5 + 4.0 = 103.5
        (100.0, 105.0, 99.5, 104.5),  # 3: 105.0 >= 103.5, so the runner stops out
        *QUIET,
    ]
    rising = [0.0] * 2 + [1.0] * 10
    falling = [0.0] * 2 + [-1.0] * 10
    kwargs = {"signal_at": [1], "direction": SHORT, "trail_multiplier": 4.0}
    assert "signal" in set(run(rows, ema=rising, **kwargs)["exit_reason"])
    assert "signal" not in set(run(rows, ema=falling, **kwargs)["exit_reason"])


# -- the loss gate above both branches -----------------------------------------


def test_the_gate_above_both_branches_holds_a_position_that_is_not_far_enough_down() -> None:
    """``if (GetUnrealizedProfitLoss(...) > -200) return;`` gates the trend check too.

    ``docs/nt8-fidelity.md`` §M23.
    """
    kwargs = {"signal_at": [1], "ema": VIOLATED_AT_THE_CHANGE, "trail_multiplier": 4.0}
    assert "signal" in set(run(PARTIAL, loss_gate=0.0, **kwargs)["exit_reason"])
    fenced = run(PARTIAL, loss_gate=200.0, **kwargs)["exit_reason"]
    assert "signal" not in set(fenced), "a few points down is not $200 down"


# Entry at 100.0, the runner stopped out on bar 4, and bar 3 closed five points against the
# position -- $40 on four MNQ contracts and $400 on four NQ ones.
GATE_SCALE = [
    FLAT,  # 0: inside bar
    FLAT,  # 1: signal
    FLAT,  # 2: fill at 100; trail 90.5 after the entry bar's advance
    (100.0, 100.5, 95.0, 95.0),  # 3: the close the gate is measured at
    (95.0, 95.5, 90.0, 91.0),  # 4: 90.0 <= 90.5, so the runner stops out and the gate is read
    *QUIET,
]


def test_the_gate_is_account_currency_so_it_binds_differently_on_the_two_roots() -> None:
    """The ``-200`` gate is currency, so it is reached by a tenth of the move on NQ that MNQ needs."""
    kwargs = {
        "signal_at": [1],
        "ema": [0.0] * 3 + [-1.0] * 10,
        "trail_multiplier": 10.0,
        "loss_gate": 200.0,
    }
    mnq = run(GATE_SCALE, instrument=MNQ, **kwargs)
    nq = run(GATE_SCALE, instrument=NQ, **kwargs)
    assert "signal" not in set(mnq["exit_reason"]), "$40 down does not clear a $200 gate"
    assert "signal" in set(nq["exit_reason"]), "$400 down does"


# -- the shared exits, which both lots reach independently ---------------------


def test_the_session_close_flattens_both_lots() -> None:
    trades = run(QUIET, signal_at=[1], force_flat_at=[4])
    assert list(trades["exit_reason"]) == ["session_close", "session_close"]
    assert list(trades["exit_bar"]) == [4, 4]


def test_a_position_open_at_the_last_bar_liquidates_every_lot_there() -> None:
    trades = run(QUIET, signal_at=[1])
    assert list(trades["exit_reason"]) == ["end_of_data", "end_of_data"]
    assert list(trades["exit_bar"]) == [len(QUIET) - 1] * 2


def test_the_entry_orders_fill_at_the_flatten_point_and_both_lots_are_flattened() -> None:
    """NT8 fills the resting orders and only then flattens -- ``docs/nt8-fidelity.md``,
    "A resting entry fills on the force-flat bar, and is flattened at its close"."""
    trades = run(QUIET, signal_at=[1], force_flat_at=[2])
    assert list(trades["entry_bar"]) == [2, 2]
    assert list(trades["exit_reason"]) == ["session_close", "session_close"]
    assert list(trades["exit_bar"]) == [2, 2]
    assert trades["exit_price"].unique() == pytest.approx([100.0])  # bar 2's close


def test_a_signal_on_a_force_flat_bar_is_blocked_when_asked() -> None:
    """``block_entry_at_session_close`` guards a *new* signal; the cancel above guards a
    resting order. Two rules, and the flag only ever meant the first."""
    assert run(QUIET, signal_at=[1], force_flat_at=[1]).empty
    assert not run(QUIET, signal_at=[1], force_flat_at=[1], block_entry_at_close=False).empty


def test_a_signal_while_already_in_a_position_does_not_pyramid() -> None:
    assert list(run(QUIET, signal_at=[1, 4])["entry_bar"].unique()) == [2]


@pytest.mark.parametrize(
    ("kwargs", "path"),
    [
        ({}, "the end of the data"),
        ({"force_flat_at": [4]}, "the session close, through the shared engine"),
        ({"rows": STOPPED_ON_ENTRY, "atr": 0.5, "trail_multiplier": 1.0}, "a stop on the entry bar"),
        (
            {"rows": PARTIAL, "ema": VIOLATED_AT_THE_CHANGE, "trail_multiplier": 4.0},
            "the trend-violation exit",
        ),
        ({"max_hold_bars": 2, "atr": FAR_ATR, "trail_multiplier": FAR_TRAIL}, "the hold limit"),
    ],
)
def test_the_buffer_overflowing_is_reported_rather_than_written_past(kwargs, path) -> None:
    """Two lots per trade, so a buffer sized for one leg overflows on whichever exit fires.

    Every path that writes a leg reports the overflow rather than silently dropping the second
    lot.
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
    """``MaximumLossPerTrade`` defaults to 0 and its own branch requires it > 0, so it is refused.

    ``docs/nt8-fidelity.md`` §M23.
    """
    assert InsideBarTrailingParams().maximum_loss_per_trade == 0.0
    with pytest.raises(ValueError, match="unreachable in the NinjaScript"):
        InsideBarTrailingParams(maximum_loss_per_trade=200.0)


def test_the_loss_gate_defaults_to_the_ninjascripts_hardcoded_amount() -> None:
    assert InsideBarTrailingParams().position_update_loss_gate == 200.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"order_quantity": 1}, "must be >= 2 to split"),
        ({"partial_take_profit_percentage": 0.95}, r"must be in \[0, 0.9\]"),
        ({"partial_take_profit_percentage": -0.1}, r"must be in \[0, 0.9\]"),
        ({"trailing_stop_multiplier": 0.5}, "must be >= 1"),
        ({"position_update_loss_gate": -1.0}, "loss magnitude"),
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
    """Build hand-written bars on a minute index, with the session closed by a copy of the last."""
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
    """Prepare the dataset the archetype's own ``ContextSpec`` asks for."""
    return context.prepare(bars, sweep.Grid.of(params).required_context())


def signalling(**overrides) -> InsideBarTrailingParams:
    """Build params with short periods, so three real averages sit under a rising close on hand-built bars."""
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
    """Given the same entry fields, InsideBar and InsideBarTrailing produce the same signal array."""
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
    """Everything monetary goes through ``instruments.py``: same geometry, ten times the P&L.

    The loss gate is off here, because it is the one rule that deliberately does *not* scale --
    that is pinned by the two-root gate test above.
    """
    params = signalling(atr_multiplier=2.0, position_update_loss_gate=0.0)
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


def test_the_structure_trail_reaches_the_loop_from_the_parameters() -> None:
    """Bar 4 closes above box {2, 3}: the high-water trail moves to 115.0 and the structure stop to 110.0."""
    bars = frame(
        [
            *BREAKOUT,
            (115.0, 116.0, 114.0, 115.0),  # 3: fill at 115; the inside bar's range is 10.0
            (115.0, 125.0, 115.0, 124.0),  # 4: closes above box {2, 3}'s 120.0
            (124.0, 124.5, 112.0, 113.0),  # 5: through 115.0 and not 110.0
            *[(113.0, 114.0, 112.0, 113.0)] * 2,
        ],
    )
    high_water = signalling(trailing_stop_multiplier=1.0, position_update_loss_gate=0.0)
    structure = dataclasses.replace(high_water, structure_trail_bars=2)
    data = prepared(bars, structure)

    trailed = runner_leg(insidebartrailing.run_insidebartrailing(data, high_water))
    structured = runner_leg(insidebartrailing.run_insidebartrailing(data, structure))
    assert structured["initial_stop"] == trailed["initial_stop"]
    assert (trailed["exit_bar"], trailed["exit_price"]) == (5, pytest.approx(115.0))
    assert structured["exit_bar"] > 5


# -- the registry --------------------------------------------------------------


def test_the_archetype_is_registered_and_carries_its_reconciliation() -> None:
    assert archetypes.get("InsideBarTrailing") is archetypes.INSIDEBARTRAILING
    assert archetypes.INSIDEBARTRAILING.tier2 is Tier2Status.RECONCILED
    assert archetypes.for_params(InsideBarTrailingParams()) is archetypes.INSIDEBARTRAILING
    assert archetypes.for_params(InsideBarParams()) is archetypes.INSIDEBAR


def test_the_split_lot_axes_are_sweepable_despite_being_inherited() -> None:
    """``sweepable`` includes every axis InsideBarTrailing inherits (#60)."""
    axes = archetypes.INSIDEBARTRAILING.sweepable
    assert {"trailing_stop_multiplier", "partial_take_profit_percentage"} <= axes
    assert {"error_margin", "atr_multiplier", "phase_filter"} <= axes


# -- the maximum hold time -----------------------------------------------------


def test_the_hold_limit_leaves_both_lots_at_the_next_bars_open() -> None:
    trades = run(QUIET, signal_at=[1], atr=FAR_ATR, trail_multiplier=FAR_TRAIL, max_hold_bars=2)
    # Filled at bar 2's open, so bar 4 is two bars later and the order goes in at its close.
    assert set(trades["leg"]) == {1, 2}
    assert set(trades["exit_bar"]) == {5}
    assert set(trades["exit_reason"]) == {"time_limit"}
    assert set(trades["exit_price"]) == {100.0}


def test_a_hold_limit_of_zero_leaves_both_lots_to_the_data() -> None:
    trades = run(QUIET, signal_at=[1], atr=FAR_ATR, trail_multiplier=FAR_TRAIL)
    assert set(trades["exit_reason"]) == {"end_of_data"}


def test_a_lot_that_already_left_is_not_flattened_twice_by_the_clock() -> None:
    trades = run(PARTIAL, signal_at=[1], atr=FAR_ATR, trail_multiplier=4.0, max_hold_bars=3)
    runner = trades[trades["leg"] == 2].iloc[0]
    bracketed = trades[trades["leg"] == 1].iloc[0]
    assert len(trades) == 2
    assert runner["exit_reason"] == "stop"
    assert runner["exit_bar"] == 3
    assert bracketed["exit_reason"] == "time_limit"
    assert bracketed["exit_bar"] == 6


# -- lot sizing per signal (§M45) ----------------------------------------------


def two_row_sizing(signal_row, n, *, rows=((4, 2), (1, 3))):
    """Build a two-split table with every bar on row 0 except the ones ``signal_row`` names."""
    row_at = np.zeros(n, dtype=np.int64)
    for bar, row in signal_row.items():
        row_at[bar] = row

    return bracket.Sizing(np.asarray(rows, dtype=np.int64), row_at)


def test_an_entry_takes_the_split_its_signal_bar_names() -> None:
    sizing = two_row_sizing({1: 1}, len(QUIET))
    trades = run(QUIET, signal_at=[1], sizing=sizing)
    assert list(trades["leg"]) == [1, 2]
    assert list(trades["quantity"]) == [1, 3]


def test_the_split_is_read_at_the_signal_bar_and_not_the_fill_bar() -> None:
    """The size is decided at the close that submits the order; the fill bar has not closed."""
    sizing = two_row_sizing({2: 1}, len(QUIET))
    trades = run(QUIET, signal_at=[1], sizing=sizing)
    assert list(trades["quantity"]) == [4, 2]


def test_each_trade_takes_its_own_split() -> None:
    rows = [*STOPPED_ON_ENTRY[:3], FLAT, FLAT, (100.0, 100.5, 90.0, 95.0), *QUIET]
    sizing = two_row_sizing({4: 1}, len(rows))
    trades = run(rows, signal_at=[1, 4], sizing=sizing, atr=0.5, trail_multiplier=1.0)
    by_trade = trades.sort_values(["trade_id", "leg"]).groupby("trade_id")["quantity"].apply(list).to_dict()
    assert by_trade == {1: [4, 2], 2: [1, 3]}


def test_the_loss_gate_reads_the_trades_own_size() -> None:
    """The ``-200`` is currency on the open position, so a larger split reaches it sooner.

    :data:`GATE_SCALE` is $40 down on the four-lot left open on MNQ; the same five points on a
    25-lot are $250.
    """
    kwargs = {
        "signal_at": [1],
        "ema": [0.0] * 3 + [-1.0] * 10,
        "trail_multiplier": 10.0,
        "loss_gate": 200.0,
    }
    small = run(GATE_SCALE, sizing=two_row_sizing({}, len(GATE_SCALE), rows=((4, 2), (25, 2))), **kwargs)
    large = run(GATE_SCALE, sizing=two_row_sizing({1: 1}, len(GATE_SCALE), rows=((4, 2), (25, 2))), **kwargs)
    assert "signal" not in set(small["exit_reason"])
    assert "signal" in set(large["exit_reason"])


def test_the_default_lot_table_is_the_one_fixed_split() -> None:
    params = InsideBarTrailingParams()
    assert params.lot_table == (params.leg_quantities,) == ((4, 2),)
    assert sizing_labels(params) == ()


def test_earliness_adds_an_early_tier_in_front_of_the_established_one() -> None:
    params = InsideBarTrailingParams(earliness_mode=EARLINESS_FIRST_BREAKOUT)
    # 6 contracts: a quarter rounds up to 2, and the established tier keeps 0.6 -> 4.
    assert params.lot_table == ((2, 4), (4, 2))


def test_confluence_adds_a_row_per_count_within_each_tier() -> None:
    params = InsideBarTrailingParams(
        order_quantity=4,
        partial_take_profit_percentage=0.5,
        earliness_mode=EARLINESS_TREND_AGE,
        quantity_per_confluence=2,
        size_on_vwap=True,
        size_on_trend=True,
    )
    assert sizing_labels(params) == ("size_on_trend", "size_on_vwap")
    early = ((1, 3), (2, 4), (2, 6))
    established = ((2, 2), (3, 3), (4, 4))
    assert params.lot_table == (*early, *established)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"earliness_mode": 9}, "earliness_mode must be one of"),
        (
            {"earliness_mode": EARLINESS_FIRST_BREAKOUT, "early_partial_percentage": 0.95},
            r"must be in \[0, 0.9\]",
        ),
        ({"early_max_extension_atr": -0.5}, "early_max_extension_atr must be >= 0"),
        ({"early_max_trend_bars": 0}, "early_max_trend_bars >= 1"),
        ({"quantity_per_confluence": -1}, "contract count"),
        ({"quantity_per_confluence": 1}, "fixed size under another name"),
        ({"size_on_regime": True}, "fixed size under another name"),
        (
            {"earliness_mode": EARLINESS_FIRST_BREAKOUT, "early_partial_percentage": 0.0},
            "lot of zero contracts",
        ),
        (
            {
                "order_quantity": 2,
                "partial_take_profit_percentage": 0.5,
                "earliness_mode": EARLINESS_TREND_AGE,
            },
            "which is earliness_mode off",
        ),
    ],
)
def test_a_sizing_rule_that_cannot_run_or_runs_as_fixed_size_is_refused(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        InsideBarTrailingParams(**overrides)


def test_tiers_that_differ_at_some_count_are_not_refused() -> None:
    """At 2 contracts a quarter and a half are both one lot, but a third label's step splits them."""
    params = InsideBarTrailingParams(
        order_quantity=2,
        partial_take_profit_percentage=0.5,
        earliness_mode=EARLINESS_TREND_AGE,
        quantity_per_confluence=2,
        size_on_regime=True,
    )
    assert params.lot_table == ((1, 1), (1, 3), (1, 1), (2, 2))


def walk_bars(n=4000, seed=3):
    """Build a trending random walk, so both sides' trends run long enough to hold several setups."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 1.5, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1.5, n))
    bars = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    bars["trading_day"] = sessions.classify(idx).trading_day

    return bars


def short_periods(**overrides) -> InsideBarTrailingParams:
    """Build params with periods short enough for trends to start and stop many times in :func:`walk_bars`."""
    defaults = {"ema_period": 5, "fast_sma_period": 8, "slow_sma_period": 13, "error_margin": 0.01}

    return InsideBarTrailingParams(**{**defaults, **overrides})


def first_of_run_by_brute_force(run_mask, event):
    """Walk back to each bar's run start and look for an earlier event: the definition, slowly."""
    out = []
    for i in range(len(run_mask)):
        start = i
        while run_mask[i] and start > 0 and run_mask[start - 1]:
            start -= 1
        out.append(not run_mask[i] or not event[start:i].any())

    return np.asarray(out)


def test_first_breakout_is_early_only_before_any_setup_in_the_same_trend_run() -> None:
    params = short_periods(earliness_mode=EARLINESS_FIRST_BREAKOUT)
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    up, down = insidebar_trends(data, params)
    long_pattern, short_pattern = insidebar_patterns(data, params)
    expected = np.where(
        direction_at == LONG,
        first_of_run_by_brute_force(up, long_pattern),
        first_of_run_by_brute_force(down, short_pattern),
    )
    early = insidebartrailing.early_entries(data, params, direction_at)
    assert np.array_equal(early, expected)
    patterns = long_pattern | short_pattern
    assert early[patterns].any(), "no setup was first in its run, so the test proves nothing"
    assert not early[patterns].all(), "no setup was a second one, so the test proves nothing"


def test_trend_age_is_early_up_to_the_cut_and_established_after() -> None:
    params = short_periods(earliness_mode=EARLINESS_TREND_AGE, early_max_trend_bars=4)
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    up, down = insidebar_trends(data, params)
    early = insidebartrailing.early_entries(data, params, direction_at)
    age = np.where(direction_at == LONG, conditions.consecutive_true(up), conditions.consecutive_true(down))
    assert np.array_equal(early, age <= 4)
    assert early[age == 4].all()
    assert not early[age == 5].any()
    assert early[age == 0].all(), "outside a trend on its side, no move has been established"


def test_sma_extension_is_early_within_the_cut_and_unmeasurable_is_established() -> None:
    params = short_periods(earliness_mode=EARLINESS_SMA_EXTENSION, early_max_extension_atr=1.5)
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    early = insidebartrailing.early_entries(data, params, direction_at)
    slow = data.ma_values(params.slow_sma_kind, params.slow_sma_period)
    extension = np.abs(data.close - slow) / data.atr_values(params.atr_length)
    measurable = np.isfinite(extension)
    assert np.array_equal(early[measurable], extension[measurable] <= 1.5)
    assert early.any()
    assert not early.all()


def test_an_unmeasurable_extension_reads_established() -> None:
    params = short_periods(earliness_mode=EARLINESS_SMA_EXTENSION)
    data = prepared(walk_bars(), params)
    data.atr_values(params.atr_length)[:] = 0.0
    early = insidebartrailing.early_entries(data, params, insidebar_direction(data, params))
    slow = data.ma_values(params.slow_sma_kind, params.slow_sma_period)
    assert not early[data.close != slow].any()


def test_every_bar_is_early_tier_while_earliness_is_off() -> None:
    params = short_periods()
    data = prepared(walk_bars(), params)
    tiers = insidebartrailing.earliness_tiers(data, params, insidebar_direction(data, params))
    assert not tiers.any()


def test_the_side_dependent_labels_flip_with_the_side_and_the_others_do_not() -> None:
    params = short_periods(quantity_per_confluence=1, size_on_vwap=True, size_on_regime=True)
    data = prepared(walk_bars(), params)
    n = len(data)
    long_side = np.ones(n, dtype=np.bool_)
    as_long = [label.favours for label in filters.label_sides(data, params, long_side)]
    as_short = [label.favours for label in filters.label_sides(data, params, ~long_side)]
    vwap_long, regime_long = as_long
    vwap_short, regime_short = as_short
    assert np.array_equal(vwap_long, data.vwap_gate(above=True))
    assert np.array_equal(vwap_short, data.vwap_gate(above=False))
    assert np.array_equal(regime_long, regime_short)
    assert vwap_long.any()
    assert vwap_short.any()


def test_every_label_kind_can_be_counted_and_the_count_is_their_sum() -> None:
    params = short_periods(
        quantity_per_confluence=1,
        size_on_trend=True,
        size_on_higher_timeframe=True,
        size_on_vwap=True,
        size_on_regime=True,
        size_on_volume=True,
    )
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    rows = [label.favours for label in filters.label_sides(data, params, direction_at == LONG)]
    counts = filters.confluence_counts(data, params, direction_at == LONG)
    assert len(rows) == 5
    assert np.array_equal(counts, np.sum(rows, axis=0))
    assert counts.max() <= 5


def test_no_labels_counts_nothing() -> None:
    params = short_periods()
    data = prepared(walk_bars(), params)
    assert not filters.confluence_counts(data, params, insidebar_direction(data, params) == LONG).any()


def test_every_row_a_bar_can_take_is_in_the_table() -> None:
    params = short_periods(
        earliness_mode=EARLINESS_FIRST_BREAKOUT,
        quantity_per_confluence=1,
        size_on_vwap=True,
        size_on_regime=True,
    )
    data = prepared(walk_bars(), params)
    sizing = insidebartrailing.lot_sizing(data, params, insidebar_direction(data, params))
    assert sizing.quantities.shape == (6, 2)
    assert sizing.row_at.min() >= 0
    assert sizing.row_at.max() < 6


def test_each_trade_is_sized_off_its_signal_bar_end_to_end() -> None:
    """Total size is ``order_quantity`` plus a step per favourable label, and the bracketed lot
    takes the share its tier names -- both read at the bar before the fill."""
    params = short_periods(
        earliness_mode=EARLINESS_TREND_AGE,
        early_max_trend_bars=3,
        early_partial_percentage=0.25,
        partial_take_profit_percentage=0.5,
        order_quantity=4,
        quantity_per_confluence=2,
        size_on_vwap=True,
        size_on_regime=True,
    )
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    counts = filters.confluence_counts(data, params, direction_at == LONG)
    early = insidebartrailing.early_entries(data, params, direction_at)
    log = insidebartrailing.run_insidebartrailing(data, params, MNQ)
    assert log["trade_id"].nunique() > 10

    by_trade = log.groupby("trade_id")
    signal_bar = by_trade["entry_bar"].first().to_numpy() - 1
    total = by_trade["quantity"].sum().to_numpy()
    bracketed = log[log["leg"] == 1].set_index("trade_id")["quantity"].sort_index().to_numpy()
    expected_total = 4 + 2 * counts[signal_bar]
    expected_share = np.where(early[signal_bar], 0.25, 0.5)
    assert np.array_equal(total, expected_total)
    assert np.array_equal(bracketed, np.ceil(expected_total * expected_share).astype(int))
    assert len(set(total)) > 1, "every trade took one size, so the count was never exercised"
    assert len(set(early[signal_bar])) == 2, "only one tier was reached"


def test_sizing_off_reproduces_the_fixed_split_bar_for_bar() -> None:
    """What the trade-log gate protects: the default path must not move a number."""
    params = short_periods()
    data = prepared(walk_bars(), params)
    direction_at = insidebar_direction(data, params)
    sized = insidebartrailing.lot_sizing(data, params, direction_at)
    assert sized.quantities.tolist() == [list(params.leg_quantities)]
    assert not sized.row_at.any()


# -- the registry and the sweep, for the sizing axes -----------------------------


def test_a_label_axis_is_live_when_sizing_reads_it_even_with_its_filter_off() -> None:
    sized = short_periods(quantity_per_confluence=1, size_on_regime=True)
    sweep.Grid.of(sized, regime_lookback=[10, 20])
    with pytest.raises(sweep.SweepError, match=r"regime_filter is 7 and size_on_regime is False"):
        sweep.Grid.of(short_periods(), regime_lookback=[10, 20])


def test_the_earliness_axes_are_dead_while_earliness_is_off() -> None:
    with pytest.raises(
        sweep.SweepError, match=r"early_partial_percentage \(inert while earliness_mode is 0\)"
    ):
        sweep.Grid.of(short_periods(), early_partial_percentage=[0.25, 0.3])

    sweep.Grid.of(short_periods(earliness_mode=EARLINESS_TREND_AGE), early_max_trend_bars=[5, 10])


def test_sizing_on_a_label_builds_its_series_and_nothing_else_does() -> None:
    bare = sweep.Grid.of(short_periods()).required_context()
    assert not bare.needs_vwap
    assert bare.regime_lookbacks == ()
    sized = sweep.Grid.of(
        short_periods(quantity_per_confluence=1, size_on_vwap=True, size_on_regime=True),
    ).required_context()
    assert sized.needs_vwap
    assert sized.regime_lookbacks == (short_periods().regime_lookback,)


def test_a_row_that_sizes_per_signal_is_tier1_only() -> None:
    """The reconciled NinjaScript sizes every entry the same; nothing has diffed the rest."""
    archetype = archetypes.INSIDEBARTRAILING
    assert archetype.tier2_for(InsideBarTrailingParams()) is Tier2Status.RECONCILED
    assert (
        archetype.tier2_for(InsideBarTrailingParams(earliness_mode=EARLINESS_TREND_AGE))
        is Tier2Status.TIER1_ONLY
    )
    sized = InsideBarTrailingParams(quantity_per_confluence=1, size_on_volume=True)
    assert archetype.tier2_for(sized) is Tier2Status.TIER1_ONLY
    assert archetypes.INSIDEBAR.tier2_for(InsideBarParams()) is Tier2Status.RECONCILED


def test_sweep_axes_stamps_the_status_row_by_row() -> None:
    grid = sweep.Grid.of(short_periods(), earliness_mode=[EARLINESS_OFF, EARLINESS_TREND_AGE])
    table, _ = sweep.sweep_axes(walk_bars(1500), grid)
    by_mode = dict(zip(table["earliness_mode"], table["tier2"], strict=True))
    assert by_mode == {EARLINESS_OFF: "reconciled", EARLINESS_TREND_AGE: "tier-1-only"}
