"""ElasticBand simulation tests on hand-built bars.

The archetype has no NinjaScript, so like EmaCrossover there is no trade list to check against.
What these pin instead are the things it introduces -- five stop schemes, a target expressed
as a band level rather than as an R multiple, and two rule-driven exits -- plus the property
the whole thing is worthless without: that nothing it reads comes from a bar it could not have
seen.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, sweep
from nqbt.instruments import MNQ, NQ
from nqbt.sim import elasticband
from nqbt.sim.elasticband import (
    beyond_band,
    closed_off_extreme,
    elasticband_signal,
    swept_and_reclaimed,
    fade_direction,
    lagged,
    one_sided_bars,
    outside_run_length,
    returned_inside,
    run_elasticband,
    run_extreme,
)
from nqbt.sim.types import (
    BAND_VWAP,
    SHAPE_ANY,
    SHAPE_RECLAIM,
    SHAPE_REJECTION,
    SHAPE_REVERSAL,
    STOP_ATR,
    STOP_BAND,
    STOP_CATASTROPHE,
    STOP_EXCURSION,
    STOP_SWING,
    TARGET_R,
    TARGET_STRETCH,
    TRIGGER_EXTENDED,
    TRIGGER_RECOVERY,
    ElasticBandParams,
)
from nqbt.trades import EXIT_REASONS, LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25


def simulate(
    rows,
    signal_at=(),
    *,
    max_rows=None,
    direction=LONG,
    basis=100.0,
    stddev=2.0,
    atr=4.0,
    extremes=None,
    force_flat_at=(),
    quantities=(1,),
    levels=(0.0,),
    stop_mode=STOP_CATASTROPHE,
    swing_lookback=1,
    atr_stop_multiple=1.0,
    min_bracket_dollars=0.0,
    stop_offset_ticks=2.0,
    catastrophe_stop_ticks=40.0,
    entry_std=2.0,
    band_stop_std=1.0,
    target_mode=TARGET_STRETCH,
    tp_multiplier=1.0,
    bars_required=0,
    exit_on_invalidation=False,
    max_hold_bars=0,
    block_entry_at_close=True,
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    fill_limit_on_touch=True,  # tests target exact prices; opt out explicitly
    ambiguity_policy=0,
    round_targets=True,
):
    """Simulate hand-written OHLC rows against a band supplied directly.

    ``signal_at`` lists the bars whose close schedules an entry; ``basis``, ``stddev`` and
    ``extremes`` stand in for the band grid so a test can state the geometry rather than
    reverse-engineer a price series that produces it.
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

    def series(value):
        return np.full(n, value, dtype=np.float64) if np.isscalar(value) else np.asarray(value, np.float64)

    out = (
        elasticband.bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
        if max_rows is None
        else np.zeros((max_rows, N_COLUMNS), dtype=np.float64)
    )
    count = elasticband.simulate_elasticband(
        elasticband.bracket.Bars(o, h, low, c, force_flat),
        signal,
        direction_at,
        elasticband.BandSeries(
            basis=series(basis),
            stddev=series(stddev),
            excursion_extreme=series(low.min() if extremes is None else extremes),
            atr=series(atr),
        ),
        np.asarray(quantities, dtype=np.int64),
        np.asarray(levels, dtype=np.float64),
        elasticband.bracket.Costs(TICK, instrument.point_value, commission, slippage),
        elasticband.bracket.FillRules(fill_limit_on_touch, ambiguity_policy, round_targets),
        elasticband.ElasticBandRules(
            stop_mode=stop_mode,
            atr_stop_multiple=atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(min_bracket_dollars),
            stop_offset=stop_offset_ticks * TICK,
            catastrophe_distance=catastrophe_stop_ticks * TICK,
            swing_lookback=swing_lookback,
            entry_std=entry_std,
            band_stop_std=band_stop_std,
            target_mode=target_mode,
            tp_multiplier=tp_multiplier,
            bars_required=bars_required,
            exit_on_invalidation=exit_on_invalidation,
            max_hold_bars=max_hold_bars,
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


FLAT = [(100.0, 100.5, 99.5, 100.0)] * 8


# -- the entry, which is EmaCrossover's mechanism -------------------------------


def test_the_entry_fills_at_the_next_bars_open_without_touching_anything() -> None:
    trades = run(
        [
            (90.0, 90.5, 89.5, 90.0),  # 0: signal, far below the basis
            (92.0, 92.5, 91.5, 92.0),  # 1: gapped up; a stop-market entry would miss
            *FLAT,
        ],
        signal_at=[0],
    )
    assert trades["entry_bar"].iloc[0] == 1
    assert trades["entry_price"].iloc[0] == pytest.approx(92.0)


def test_the_resting_order_fills_at_the_flatten_point_and_is_flattened_there() -> None:
    """NT8 fills the resting order and only then flattens -- ``docs/nt8-fidelity.md``,
    "A resting entry fills on the force-flat bar, and is flattened at its close"."""
    # The basis target sits out of reach so the flatten is what the exit reports.
    trades = run(FLAT, signal_at=[0], force_flat_at=[1], levels=(1.0,))
    assert list(trades["entry_bar"].unique()) == [1]
    assert set(trades["exit_reason"]) == {"session_close"}
    assert list(trades["exit_bar"].unique()) == [1]
    assert trades["exit_price"].unique() == pytest.approx([100.0])  # bar 1's close


def test_a_signal_below_bars_required_is_ignored() -> None:
    assert run(FLAT, signal_at=[0], bars_required=4).empty


# -- the stop schemes -----------------------------------------------------------


def test_the_catastrophe_stop_is_a_fixed_tick_distance_from_the_fill() -> None:
    trades = run(FLAT, signal_at=[0], stop_mode=STOP_CATASTROPHE, catastrophe_stop_ticks=40.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(100.0 - 40 * TICK)


def test_the_atr_stop_hangs_off_the_fill_and_takes_the_dollar_floor() -> None:
    unfloored = run(FLAT, signal_at=[0], stop_mode=STOP_ATR, atr=4.0, atr_stop_multiple=1.5)
    assert unfloored["initial_stop"].iloc[0] == pytest.approx(100.0 - 6.0)
    # $100 per contract is 50 MNQ points, which is wider than 6 and therefore binds.
    floored = run(
        FLAT,
        signal_at=[0],
        stop_mode=STOP_ATR,
        atr=4.0,
        atr_stop_multiple=1.5,
        min_bracket_dollars=100.0,
    )
    assert floored["initial_stop"].iloc[0] == pytest.approx(100.0 - 50.0)


def test_the_excursion_stop_sits_beyond_the_run_extreme_by_the_offset() -> None:
    trades = run(
        FLAT,
        signal_at=[0],
        stop_mode=STOP_EXCURSION,
        extremes=94.0,
        stop_offset_ticks=2.0,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(94.0 - 2 * TICK)


def test_only_the_atr_stop_is_floored_because_only_it_is_a_distance() -> None:
    # A structural level pushed away from its structure stops being the rule it is --
    # docs/nt8-fidelity.md §M26.
    trades = run(
        FLAT,
        signal_at=[0],
        stop_mode=STOP_EXCURSION,
        extremes=99.0,
        min_bracket_dollars=100.0,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(99.0 - 2 * TICK)


def test_an_entry_whose_stop_would_sit_at_its_own_fill_is_skipped() -> None:
    assert run(FLAT, signal_at=[0], stop_mode=STOP_EXCURSION, extremes=100.0, stop_offset_ticks=0.0).empty


def test_the_swing_stop_sits_just_beyond_the_signal_candle_at_lookback_one() -> None:
    # The tightest stop the archetype can express: a move that keeps going costs a few ticks.
    trades = run(
        [
            (100.0, 100.5, 97.0, 100.0),  # 0: signal, low 97
            (100.0, 100.5, 99.5, 100.0),  # 1: fill at 100
            *FLAT,
        ],
        signal_at=[0],
        stop_mode=STOP_SWING,
        swing_lookback=1,
        stop_offset_ticks=2.0,
        levels=(np.nan,),
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(97.0 - 2 * TICK)
    assert trades["risk_points"].iloc[0] == pytest.approx(3.5)


def test_a_longer_swing_lookback_reaches_further_back_for_its_extreme() -> None:
    rows = [
        (100.0, 100.5, 95.0, 100.0),  # 0: the deeper low
        (100.0, 100.5, 97.0, 100.0),  # 1: signal
        (100.0, 100.5, 99.5, 100.0),  # 2: fill
        *FLAT,
    ]
    one = run(
        rows, signal_at=[1], stop_mode=STOP_SWING, swing_lookback=1, stop_offset_ticks=0.0, levels=(np.nan,)
    )
    two = run(
        rows, signal_at=[1], stop_mode=STOP_SWING, swing_lookback=2, stop_offset_ticks=0.0, levels=(np.nan,)
    )
    assert one["initial_stop"].iloc[0] == pytest.approx(97.0)
    assert two["initial_stop"].iloc[0] == pytest.approx(95.0)


def test_the_swing_stop_mirrors_on_the_short_side() -> None:
    trades = run(
        [
            (100.0, 103.0, 99.5, 100.0),  # 0: signal, high 103
            (100.0, 100.5, 99.5, 100.0),  # 1: fill at 100
            *FLAT,
        ],
        signal_at=[0],
        direction=SHORT,
        stop_mode=STOP_SWING,
        swing_lookback=1,
        stop_offset_ticks=2.0,
        levels=(np.nan,),
        basis=96.0,
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(103.0 + 2 * TICK)


def test_the_swing_stop_is_not_floored_because_it_is_a_level() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.0, 100.0),
            (100.0, 100.5, 99.5, 100.0),
            *FLAT,
        ],
        signal_at=[0],
        stop_mode=STOP_SWING,
        swing_lookback=1,
        stop_offset_ticks=0.0,
        min_bracket_dollars=100.0,
        levels=(np.nan,),
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(99.0)


def test_the_band_stop_is_a_level_on_the_channel_the_entry_was_measured_against() -> None:
    # Enter at 2 sigma, stop at 3: basis 100, sigma 2, so the stop is 100 - 3 * 2.
    trades = run(FLAT, signal_at=[0], stop_mode=STOP_BAND, entry_std=2.0, band_stop_std=1.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(94.0)


def test_the_band_stop_mirrors_on_the_short_side() -> None:
    trades = run(
        FLAT,
        signal_at=[0],
        direction=SHORT,
        stop_mode=STOP_BAND,
        entry_std=2.0,
        band_stop_std=1.0,
        levels=(0.0,),
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(106.0)


def test_the_band_stop_is_measured_past_the_entry_threshold_rather_than_from_the_basis() -> None:
    """Which is what makes cells comparable across a swept ``entry_std``: the same multiple is
    the same distance beyond wherever the entry was taken."""
    for entry_std in (1.5, 2.0, 3.0):
        trades = run(FLAT, signal_at=[0], stop_mode=STOP_BAND, entry_std=entry_std, band_stop_std=0.5)
        assert trades["initial_stop"].iloc[0] == pytest.approx(100.0 - (entry_std + 0.5) * 2.0)


def test_the_band_stops_distance_scales_with_the_dispersion_the_threshold_uses() -> None:
    """The property it exists for -- no other stop here is denominated in the same units as
    the entry rule."""
    for stddev in (1.0, 2.0, 5.0):
        trades = run(
            FLAT,
            signal_at=[0],
            stop_mode=STOP_BAND,
            stddev=stddev,
            entry_std=2.0,
            band_stop_std=1.0,
        )
        assert trades["initial_stop"].iloc[0] == pytest.approx(100.0 - 3.0 * stddev)


def test_the_band_stop_reads_the_signal_bars_band_and_not_the_fill_bars() -> None:
    trades = run(
        FLAT,
        signal_at=[0],
        stop_mode=STOP_BAND,
        basis=[100.0, *[90.0] * 7],
        stddev=[2.0, *[8.0] * 7],
        entry_std=2.0,
        band_stop_std=1.0,
        levels=(np.nan,),
    )
    assert trades["initial_stop"].iloc[0] == pytest.approx(94.0)


def test_the_band_stop_takes_no_offset_because_nothing_rests_at_a_computed_level() -> None:
    """Unlike the excursion and swing stops, whose level is a price the market traded at."""
    for offset in (0.0, 2.0, 20.0):
        trades = run(FLAT, signal_at=[0], stop_mode=STOP_BAND, stop_offset_ticks=offset)
        assert trades["initial_stop"].iloc[0] == pytest.approx(94.0)


def test_the_band_stop_is_not_floored_because_it_is_a_level() -> None:
    # $100 per contract is 50 MNQ points and would bind on a 6-point stop if it applied.
    trades = run(FLAT, signal_at=[0], stop_mode=STOP_BAND, min_bracket_dollars=100.0)
    assert trades["initial_stop"].iloc[0] == pytest.approx(94.0)


def test_a_band_narrow_enough_to_put_its_stop_at_the_fill_skips_the_entry() -> None:
    """The refusal path every stop here shares: a stop at or through the price it protects is
    not a stop order -- ``docs/nt8-fidelity.md`` §M18."""
    assert run(FLAT, signal_at=[0], stop_mode=STOP_BAND, basis=100.0, stddev=0.0).empty
    # A band exactly STOP_MIN_TICKS wide at the stop is the boundary, and it passes: 2 sigma
    # of 0.125 is one tick.
    assert not run(
        FLAT,
        signal_at=[0],
        stop_mode=STOP_BAND,
        basis=100.0,
        stddev=0.125,
        entry_std=1.0,
        band_stop_std=1.0,
        levels=(np.nan,),
    ).empty


def test_a_band_stop_at_or_inside_the_entry_threshold_is_refused() -> None:
    for value in (0.0, -1.0):
        with pytest.raises(ValueError, match="band_stop_std is how far past entry_std"):
            ElasticBandParams(band_stop_std=value)


def test_a_swing_stop_the_fill_has_already_passed_skips_the_entry() -> None:
    # The candle's low is 99 but the next bar opens at 98.5, so the stop is already behind
    # the fill and there is no stop order to place.
    assert run(
        [
            (100.0, 100.5, 99.0, 100.0),
            (98.5, 99.0, 98.0, 98.5),
            *FLAT,
        ],
        signal_at=[0],
        stop_mode=STOP_SWING,
        swing_lookback=1,
        stop_offset_ticks=0.0,
        levels=(np.nan,),
    ).empty


# -- the target, which is a level rather than an R multiple ---------------------


def test_a_stretch_level_of_zero_is_the_basis_on_both_sides() -> None:
    long_side = run(FLAT, signal_at=[0], levels=(0.0,), basis=104.0, direction=LONG)
    short_side = run(FLAT, signal_at=[0], levels=(0.0,), basis=96.0, direction=SHORT)
    assert long_side["target_price"].iloc[0] == pytest.approx(104.0)
    assert short_side["target_price"].iloc[0] == pytest.approx(96.0)


def test_a_positive_stretch_level_is_the_far_band_whichever_side_is_faded() -> None:
    # Levels are signed *towards* the target, so +2 is the upper band on a long and the
    # lower band on a short.
    long_side = run(FLAT, signal_at=[0], levels=(2.0,), basis=100.0, stddev=3.0, direction=LONG)
    short_side = run(FLAT, signal_at=[0], levels=(2.0,), basis=100.0, stddev=3.0, direction=SHORT)
    assert long_side["target_price"].iloc[0] == pytest.approx(106.0)
    assert short_side["target_price"].iloc[0] == pytest.approx(94.0)


def test_an_r_multiple_target_is_capped_at_the_basis() -> None:
    # 3R off a 10-point stop is 30 points away, but the mean is 4 above the fill and a target
    # past the mean is not a mean-reversion target.
    trades = run(
        FLAT,
        signal_at=[0],
        target_mode=TARGET_R,
        levels=(3.0,),
        basis=104.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=40.0,
    )
    assert trades["target_price"].iloc[0] == pytest.approx(104.0)


def test_an_r_multiple_target_short_of_the_basis_is_left_alone() -> None:
    trades = run(
        FLAT,
        signal_at=[0],
        target_mode=TARGET_R,
        levels=(0.3,),
        basis=104.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=40.0,
    )
    # 0.3R off a 10-point stop is 3 points, which stops short of the 4-point basis.
    assert trades["target_price"].iloc[0] == pytest.approx(103.0)


def test_a_nan_level_is_a_runner_with_no_target() -> None:
    trades = run(FLAT, signal_at=[0], levels=(0.0, np.nan), quantities=(1, 1))
    assert np.isnan(trades["target_price"].iloc[-1])


def test_the_band_is_read_from_the_signal_bar_not_the_fill_bar() -> None:
    # The basis moves at bar 1, and the target must still be bar 0's.
    trades = run(FLAT, signal_at=[0], levels=(0.0,), basis=[104.0] + [120.0] * 7)
    assert trades["target_price"].iloc[0] == pytest.approx(104.0)


# -- the two rule-driven exits ---------------------------------------------------


def test_the_time_stop_leaves_at_the_next_open_once_the_hold_is_reached() -> None:
    trades = run(FLAT, signal_at=[0], levels=(np.nan,), max_hold_bars=3)
    # Filled on bar 1; bar 4 is three bars later, so the order goes in at its close.
    assert trades["exit_bar"].iloc[0] == 5
    assert trades["exit_reason"].iloc[0] == "time_limit"


def test_both_rule_driven_exits_may_be_enabled_at_once_and_stay_distinguishable() -> None:
    """The reason each has its own exit code: they were mutually exclusive without it."""
    trades = run(
        FLAT,
        signal_at=[0],
        levels=(np.nan,),
        extremes=94.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=80.0,
        exit_on_invalidation=True,
        max_hold_bars=3,
    )
    # The close never leaves the excursion, so only the hold limit can have fired.
    assert trades["exit_bar"].iloc[0] == 5
    assert trades["exit_reason"].iloc[0] == "time_limit"


def test_the_invalidation_takes_a_bar_that_is_also_the_hold_limit() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal
            (100.0, 100.5, 99.5, 100.0),  # 1: fill
            (100.0, 100.5, 93.0, 93.5),  # 2: closes below the 94 extreme, and hold bar 1
            *FLAT,
        ],
        signal_at=[0],
        levels=(np.nan,),
        extremes=94.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=80.0,
        exit_on_invalidation=True,
        max_hold_bars=1,
    )
    assert trades["exit_bar"].iloc[0] == 3
    assert trades["exit_reason"].iloc[0] == "signal"


def test_the_invalidation_exit_fires_when_the_close_passes_the_faded_extreme() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal
            (100.0, 100.5, 99.5, 100.0),  # 1: fill
            (100.0, 100.5, 93.0, 93.5),  # 2: closes below the 94 extreme it faded
            *FLAT,
        ],
        signal_at=[0],
        levels=(np.nan,),
        extremes=94.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=80.0,
        exit_on_invalidation=True,
    )
    assert trades["exit_bar"].iloc[0] == 3
    assert trades["exit_reason"].iloc[0] == "signal"


def test_the_invalidation_exit_holds_while_the_close_stays_inside_the_excursion() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),  # 0: signal
            (100.0, 100.5, 99.5, 100.0),  # 1: fill
            (100.0, 100.5, 94.5, 94.5),  # 2: dips but closes above 94
            *FLAT,
        ],
        signal_at=[0],
        levels=(np.nan,),
        extremes=94.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=80.0,
        exit_on_invalidation=True,
    )
    assert trades["exit_reason"].iloc[0] != "signal"


def test_the_short_side_mirrors_the_invalidation_test_exactly() -> None:
    trades = run(
        [
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 100.5, 99.5, 100.0),
            (100.0, 107.0, 99.5, 106.5),  # closes above the 106 extreme it faded
            *FLAT,
        ],
        signal_at=[0],
        direction=SHORT,
        levels=(np.nan,),
        basis=100.0,
        extremes=106.0,
        stop_mode=STOP_CATASTROPHE,
        catastrophe_stop_ticks=80.0,
        exit_on_invalidation=True,
    )
    assert trades["exit_bar"].iloc[0] == 3
    assert trades["exit_reason"].iloc[0] == "signal"


# -- run_extreme ----------------------------------------------------------------


def test_run_extreme_tracks_the_adverse_extreme_of_an_unbroken_run() -> None:
    low = np.array([99.0, 97.0, 98.0, 96.0, 99.0])
    high = np.array([101.0, 103.0, 102.0, 104.0, 101.0])
    beyond = np.array([True, True, True, True, False])
    out = run_extreme(low, high, beyond, np.full(5, LONG))
    assert out[:4].tolist() == [99.0, 97.0, 97.0, 96.0]
    assert np.isnan(out[4])


def test_run_extreme_restarts_when_the_run_breaks_or_changes_side() -> None:
    low = np.array([99.0, 97.0, 100.0, 98.0])
    high = np.array([101.0, 103.0, 100.0, 105.0])
    beyond = np.array([True, True, False, True])
    out = run_extreme(low, high, beyond, np.array([LONG, LONG, LONG, SHORT]))
    assert out[1] == 97.0
    assert np.isnan(out[2])
    assert out[3] == 105.0  # a short run reads the high, and starts fresh

    same_run_flip = run_extreme(
        low,
        high,
        np.array([True, True, True, True]),
        np.array([LONG, LONG, SHORT, SHORT]),
    )
    assert same_run_flip[2] == 100.0


# -- the signal -----------------------------------------------------------------


def frame(close):
    """A one-column bar frame at a fixed geometry, enough for the signal path."""
    close = np.asarray(close, dtype=np.float64)
    index = pd.date_range("2024-01-02 19:00", periods=close.size, freq="1min", tz="UTC")

    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.ones(close.size),
            "trading_day": index.tz_convert("America/New_York").normalize().tz_localize(None),
        },
        index=index,
    )


def dataset(close, params):
    grid = sweep.Grid.of(params, archetype=archetypes.ELASTICBAND)

    return sweep.prepare_for(frame(close), grid)


def test_the_signal_fires_only_beyond_the_entry_threshold() -> None:
    rng = np.random.default_rng(7)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    params = ElasticBandParams(band_period=20, entry_std=2.0, bars_required_to_trade=30)
    data = dataset(close, params)
    signal = elasticband_signal(data, params)
    stretch = data.band_stretch(20)
    assert signal.any()
    assert (np.abs(stretch[signal]) >= 2.0).all()


def test_the_ceiling_removes_the_most_extended_bars_and_nothing_else() -> None:
    rng = np.random.default_rng(7)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    base = ElasticBandParams(band_period=20, entry_std=2.0, bars_required_to_trade=30)
    capped = ElasticBandParams(
        band_period=20,
        entry_std=2.0,
        max_entry_std=2.5,
        bars_required_to_trade=30,
    )
    data = dataset(close, base)
    uncapped_signal = elasticband_signal(data, base)
    capped_signal = elasticband_signal(data, capped)
    stretch = data.band_stretch(20)
    dropped = uncapped_signal & ~capped_signal
    assert dropped.any()
    assert (np.abs(stretch[dropped]) > 2.5).all()
    assert (capped_signal <= uncapped_signal).all()


def test_a_longer_run_requirement_is_a_subset_of_a_shorter_one() -> None:
    rng = np.random.default_rng(11)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    one = ElasticBandParams(band_period=20, min_bars_outside=1, bars_required_to_trade=30)
    three = ElasticBandParams(band_period=20, min_bars_outside=3, bars_required_to_trade=30)
    data = dataset(close, one)
    first, third = elasticband_signal(data, one), elasticband_signal(data, three)
    assert third.any()
    assert (third <= first).all()


def test_each_side_can_be_switched_off_independently() -> None:
    rng = np.random.default_rng(13)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    both = ElasticBandParams(band_period=20, bars_required_to_trade=30)
    data = dataset(close, both)
    stretch = data.band_stretch(20)
    long_only = elasticband_signal(
        data,
        ElasticBandParams(band_period=20, trade_short=False, bars_required_to_trade=30),
    )
    short_only = elasticband_signal(
        data,
        ElasticBandParams(band_period=20, trade_long=False, bars_required_to_trade=30),
    )
    assert long_only.any()
    assert short_only.any()
    assert (stretch[long_only] < 0).all()
    assert (stretch[short_only] > 0).all()
    assert not (long_only & short_only).any()


def test_the_signal_reads_only_bars_up_to_and_including_its_own() -> None:
    """The property the archetype is worthless without: no bar sees the future."""
    rng = np.random.default_rng(17)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 800))
    params = ElasticBandParams(band_period=20, min_bars_outside=2, bars_required_to_trade=30)
    full = elasticband_signal(dataset(close, params), params)
    for cut in (120, 455, 799):
        assert np.array_equal(elasticband_signal(dataset(close[:cut], params), params), full[:cut])


def test_fade_direction_is_defined_on_every_bar_so_the_null_arm_can_use_it() -> None:
    stretch = np.array([-3.0, -0.1, 0.0, 0.1, 3.0])
    assert fade_direction(stretch).tolist() == [LONG, LONG, SHORT, SHORT, SHORT]


def test_beyond_band_is_symmetric_about_the_basis() -> None:
    stretch = np.array([-2.5, -2.0, -1.9, 1.9, 2.0, 2.5])
    params = ElasticBandParams(entry_std=2.0)
    assert beyond_band(stretch, params).tolist() == [True, True, False, False, True, True]


def test_lagging_the_band_shifts_it_and_leaves_no_readable_head() -> None:
    series = np.array([1.0, 2.0, 3.0, 4.0])
    assert lagged(series, 0) is series
    out = lagged(series, 2)
    assert np.isnan(out[:2]).all()
    assert out[2:].tolist() == [1.0, 2.0]
    # A lag past the series leaves nothing readable rather than raising.
    assert np.isnan(lagged(series, 9)).all()


def test_the_band_lag_makes_the_signal_read_the_previous_bars_band() -> None:
    rng = np.random.default_rng(19)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    live = ElasticBandParams(band_period=20, bars_required_to_trade=30)
    lag = ElasticBandParams(band_period=20, band_lag=1, bars_required_to_trade=30)
    data = dataset(close, live)
    assert np.array_equal(
        elasticband_signal(data, lag)[1:],
        elasticband_signal(data, live)[:-1],
    )


# -- what the signal bar itself looks like ----------------------------------------


def candle_frame(close, seed):
    """A bar frame with real bodies and wicks, which :func:`frame` deliberately has neither of.

    Every random value is drawn per bar out of one array, so a prefix of a series is built
    from the same numbers as the series -- which is what the no-lookahead tests compare.
    """
    close = np.asarray(close, dtype=np.float64)
    jitter = np.random.default_rng(seed).uniform(0.25, 2.0, (close.size, 3))
    open_ = np.concatenate(([close[0] - 1.0], close[:-1] + jitter[1:, 0] - 1.125))
    index = pd.date_range("2024-01-02 19:00", periods=close.size, freq="1min", tz="UTC")

    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + jitter[:, 1],
            "low": np.minimum(open_, close) - jitter[:, 2],
            "close": close,
            "volume": np.ones(close.size),
            "trading_day": index.tz_convert("America/New_York").normalize().tz_localize(None),
        },
        index=index,
    )


def candle_dataset(close, params, seed=101):
    grid = sweep.Grid.of(params, archetype=archetypes.ELASTICBAND)

    return sweep.prepare_for(candle_frame(close, seed), grid)


def shape_params(**kwargs):
    """A parameter set on the Bollinger source, warmed up enough for the signal path."""
    defaults = {"band_period": 20, "entry_std": 2.0, "bars_required_to_trade": 30}

    return ElasticBandParams(**(defaults | kwargs))


def walk(seed, periods=800, step=2.0):
    rng = np.random.default_rng(seed)

    return 18000.0 + np.cumsum(rng.normal(0.0, step, periods))


def test_the_defaults_ask_nothing_at_all_of_the_signal_bar() -> None:
    """The off value has to leave the signal exactly as it was, or every stored row moves."""
    close = walk(31)
    params = shape_params()
    data = candle_dataset(close, params)
    assert params.signal_shape == SHAPE_ANY
    assert params.min_one_sided_bars == 0
    assert np.array_equal(
        elasticband_signal(data, params),
        beyond_band(data.band_stretch(20), params),
    )


def test_a_reversal_requirement_keeps_only_bars_that_closed_back_towards_the_basis() -> None:
    close = walk(37)
    plain, turned = shape_params(), shape_params(signal_shape=SHAPE_REVERSAL)
    data = candle_dataset(close, plain)
    loose, tight = elasticband_signal(data, plain), elasticband_signal(data, turned)
    stretch = data.band_stretch(20)
    body = data.close - data.open
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()
    # A long below the basis wants a green bar; a short at or above it wants a red one.
    assert (body[tight & (stretch < 0.0)] > 0.0).all()
    assert (body[tight & (stretch >= 0.0)] < 0.0).all()


def test_a_doji_closes_neither_way_and_passes_the_reversal_requirement_on_neither_side() -> None:
    open_ = np.array([10.0, 10.0, 10.0, 10.0])
    close = np.array([10.0, 10.0, 11.0, 9.0])
    direction = np.array([LONG, SHORT, LONG, SHORT], dtype=np.float64)
    assert conditions.closed_towards(open_, close, direction).tolist() == [False, False, True, True]


def test_reclaiming_needs_both_a_new_extreme_against_the_fade_and_a_close_back_past_it() -> None:
    """Bar 1 is the long reclaim, bar 2 the short one, and bar 3 sweeps a low but keeps falling."""
    params = shape_params()
    data = candle_dataset(np.array([11.0, 11.5, 11.0, 10.0]), params)
    data.close = np.array([11.0, 11.5, 11.0, 10.0])
    data.geometry.made_new_low = np.array([False, True, False, True])
    data.geometry.made_new_high = np.array([False, False, True, False])
    long_side = np.full(4, LONG, dtype=np.float64)
    short_side = np.full(4, SHORT, dtype=np.float64)
    assert swept_and_reclaimed(data, long_side).tolist() == [False, True, False, False]
    # The short side reads the other extreme and the other sign of the close.
    assert swept_and_reclaimed(data, short_side).tolist() == [False, False, True, False]


def test_reclaiming_is_a_subset_of_the_bars_that_took_out_the_previous_extreme() -> None:
    close = walk(41, periods=2000)
    plain = shape_params()
    reclaiming = shape_params(signal_shape=SHAPE_RECLAIM)
    data = candle_dataset(close, plain)
    loose, tight = elasticband_signal(data, plain), elasticband_signal(data, reclaiming)
    direction = fade_direction(data.band_stretch(20))
    swept = np.where(direction > 0.0, data.geometry.made_new_low, data.geometry.made_new_high)
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()
    assert swept[tight].all()


def test_the_rejection_requirement_measures_the_close_from_the_stretched_extreme() -> None:
    """A long fades a low, so its close is measured up from the low; a short mirrors it."""
    params = shape_params()
    data = candle_dataset(np.array([12.0, 12.0, 18.0, 18.0]), params)
    data.high = np.full(4, 20.0)
    data.low = np.full(4, 10.0)
    data.close = np.array([12.0, 12.0, 18.0, 18.0])
    direction = np.array([LONG, SHORT, LONG, SHORT], dtype=np.float64)
    # 12 is 20% up from the low and 80% down from the high; 18 is the mirror of it.
    assert closed_off_extreme(data, direction, 0.5).tolist() == [False, True, True, False]


def test_a_zero_range_bar_never_passes_the_rejection_requirement() -> None:
    params = shape_params()
    data = candle_dataset(np.full(4, 15.0), params)
    data.high = np.full(4, 15.0)
    data.low = np.full(4, 15.0)
    data.close = np.full(4, 15.0)
    direction = np.array([LONG, SHORT, LONG, SHORT], dtype=np.float64)
    assert not closed_off_extreme(data, direction, 0.0).any()


def test_a_deeper_rejection_fraction_keeps_a_subset_of_a_shallower_one() -> None:
    close = walk(43)
    shallow = shape_params(signal_shape=SHAPE_REJECTION, rejection_close_fraction=0.3)
    deep = shape_params(signal_shape=SHAPE_REJECTION, rejection_close_fraction=0.7)
    data = candle_dataset(close, shallow)
    loose, tight = elasticband_signal(data, shallow), elasticband_signal(data, deep)
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()


def test_the_one_sided_count_counts_bodies_running_with_the_extension() -> None:
    params = shape_params()
    data = candle_dataset(np.array([10.0, 9.0, 8.0, 9.5, 9.0]), params)
    data.open = np.array([10.0, 10.0, 9.0, 8.0, 9.5])
    data.close = np.array([10.0, 9.0, 8.0, 9.5, 9.0])
    # Bodies, in order: flat, down, down, up, down.
    down_side = np.full(5, LONG, dtype=np.float64)
    up_side = np.full(5, SHORT, dtype=np.float64)
    assert one_sided_bars(data, down_side, 3).tolist() == [0, 1, 2, 2, 2]
    assert one_sided_bars(data, up_side, 3).tolist() == [0, 0, 0, 1, 1]


def test_a_larger_one_sided_requirement_keeps_a_subset_of_a_smaller_one() -> None:
    close = walk(47)
    light = shape_params(min_one_sided_bars=4, one_sided_lookback=10)
    heavy = shape_params(min_one_sided_bars=7, one_sided_lookback=10)
    data = candle_dataset(close, light)
    loose, tight = elasticband_signal(data, light), elasticband_signal(data, heavy)
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()


def test_the_count_is_over_a_window_rather_than_over_an_unbroken_run() -> None:
    """What separates it from ``min_bars_outside``: the bars need not be consecutive."""
    close = walk(53)
    windowed = shape_params(min_one_sided_bars=3, one_sided_lookback=6)
    unbroken = shape_params(min_one_sided_bars=3, one_sided_lookback=3)
    data = candle_dataset(close, windowed)
    loose, tight = elasticband_signal(data, windowed), elasticband_signal(data, unbroken)
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()


@pytest.mark.parametrize(
    "params",
    [
        shape_params(signal_shape=SHAPE_REVERSAL),
        shape_params(signal_shape=SHAPE_RECLAIM),
        shape_params(signal_shape=SHAPE_REJECTION, rejection_close_fraction=0.6),
        shape_params(min_one_sided_bars=5, one_sided_lookback=8),
    ],
)
def test_every_signal_bar_gate_reads_only_bars_up_to_and_including_its_own(params) -> None:
    """The property the archetype is worthless without, run once per gate that was added."""
    close = walk(59)
    full = elasticband_signal(candle_dataset(close, params), params)
    for cut in (120, 455, 799):
        prefix = elasticband_signal(candle_dataset(close[:cut], params), params)
        assert np.array_equal(prefix, full[:cut])


def test_an_unknown_signal_shape_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown signal_shape 9"):
        ElasticBandParams(signal_shape=9)


@pytest.mark.parametrize("fraction", [-0.1, 1.1])
def test_a_rejection_fraction_outside_the_bar_is_refused(fraction) -> None:
    with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
        ElasticBandParams(rejection_close_fraction=fraction)


def test_a_one_sided_window_of_no_bars_is_refused() -> None:
    with pytest.raises(ValueError, match="one_sided_lookback must be >= 1"):
        ElasticBandParams(one_sided_lookback=0)


def test_a_negative_one_sided_requirement_is_refused() -> None:
    with pytest.raises(ValueError, match="min_one_sided_bars must be >= 0"):
        ElasticBandParams(min_one_sided_bars=-1)


def test_a_one_sided_requirement_no_window_could_meet_is_refused() -> None:
    with pytest.raises(ValueError, match="no bar can ever pass"):
        ElasticBandParams(min_one_sided_bars=11, one_sided_lookback=10)


def test_a_shaped_run_produces_a_valid_trade_log() -> None:
    close = walk(61, periods=1200)
    params = shape_params(
        signal_shape=SHAPE_REJECTION,
        rejection_close_fraction=0.4,
        min_one_sided_bars=5,
        one_sided_lookback=10,
        commission_per_contract=1.5,
        slippage_ticks=1.0,
    )
    log = run_elasticband(candle_dataset(close, params), params)
    assert not log.empty
    validate(log)


# -- the VWAP band as the second source -------------------------------------------


def vwap_params(**kwargs):
    """A VWAP-source parameter set with the warm-up gate off unless a test sets it."""
    defaults = {
        "band_source": BAND_VWAP,
        "entry_std": 2.0,
        "vwap_min_session_bars": 0,
        "bars_required_to_trade": 0,
    }

    return ElasticBandParams(**(defaults | kwargs))


def test_the_vwap_source_reads_the_session_band_and_never_the_period_grid() -> None:
    rng = np.random.default_rng(29)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    params = vwap_params()
    data = dataset(close, params)
    basis, stddev, stretch = elasticband.band_series(data, params)
    assert basis.tolist() == data.vwap_band_basis().tolist()
    assert stddev.tolist() == data.vwap_band_stddev().tolist()
    assert stretch.tolist() == data.vwap_band_stretch().tolist()
    # Nothing keyed by a period was built, so a period read would have raised.
    assert data.band is None


def test_the_two_sources_are_different_bands_rather_than_the_same_one_renamed() -> None:
    rng = np.random.default_rng(31)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    bollinger = ElasticBandParams(band_period=20, entry_std=2.0, bars_required_to_trade=30)
    vwap = vwap_params(bars_required_to_trade=30)
    from_bollinger = elasticband_signal(dataset(close, bollinger), bollinger)
    from_vwap = elasticband_signal(dataset(close, vwap), vwap)
    assert from_bollinger.any()
    assert from_vwap.any()
    assert not np.array_equal(from_bollinger, from_vwap)


def test_the_vwap_signal_fires_only_beyond_the_entry_threshold() -> None:
    rng = np.random.default_rng(37)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    params = vwap_params(entry_std=2.0)
    data = dataset(close, params)
    signal = elasticband_signal(data, params)
    assert signal.any()
    assert (np.abs(data.vwap_band_stretch()[signal]) >= 2.0).all()


def test_the_warm_up_gate_drops_the_bars_whose_session_is_too_young() -> None:
    rng = np.random.default_rng(41)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 900))
    ungated = vwap_params()
    gated = vwap_params(vwap_min_session_bars=60)
    data = dataset(close, ungated)
    loose, tight = elasticband_signal(data, ungated), elasticband_signal(data, gated)
    age = data.vwap_band_age()
    assert tight.any()
    assert (tight <= loose).all()
    assert (age[tight] >= 60).all()
    dropped = loose & ~tight
    assert dropped.any()
    assert (age[dropped] < 60).all()


def test_a_lagged_vwap_band_is_never_read_across_its_own_anchor() -> None:
    # The lag is added to the requirement rather than applied to the counter, so the band a
    # bar reads always belongs to the session that bar is in.
    rng = np.random.default_rng(43)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 900))
    params = vwap_params(band_lag=3, vwap_min_session_bars=1)
    data = dataset(close, params)
    signal = elasticband_signal(data, params)
    assert signal.any()
    assert (data.vwap_band_age()[signal] >= 4).all()


def test_the_vwap_signal_reads_only_bars_up_to_and_including_its_own() -> None:
    """The same no-lookahead property as the Bollinger source, over the anchored window."""
    rng = np.random.default_rng(47)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 800))
    params = vwap_params(min_bars_outside=2, vwap_min_session_bars=10)
    full = elasticband_signal(dataset(close, params), params)
    for cut in (120, 455, 799):
        assert np.array_equal(elasticband_signal(dataset(close[:cut], params), params), full[:cut])


def test_a_vwap_run_produces_a_valid_trade_log() -> None:
    rng = np.random.default_rng(53)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1200))
    params = vwap_params(vwap_min_session_bars=20, max_hold_bars=10)
    log = run_elasticband(dataset(close, params), params, MNQ)
    assert not log.empty
    assert log["exit_reason"].isin(set(EXIT_REASONS.values())).all()


def test_an_unknown_band_source_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match=r"unknown band_source 7; use one of \[0, 1\]"):
        ElasticBandParams(band_source=7)


def test_a_negative_warm_up_is_refused() -> None:
    with pytest.raises(ValueError, match="vwap_min_session_bars must be >= 0"):
        ElasticBandParams(vwap_min_session_bars=-1)


# -- which bar of an extension signals ---------------------------------------------


def recovery_params(**kwargs):
    """A VWAP-source recovery set, on the channel §M26.6's campaign runs."""
    defaults = {
        "band_source": BAND_VWAP,
        "entry_std": 2.0,
        "entry_trigger": TRIGGER_RECOVERY,
        "vwap_min_session_bars": 10,
        "bars_required_to_trade": 0,
    }

    return ElasticBandParams(**(defaults | kwargs))


def test_the_default_trigger_is_the_bar_that_is_still_outside() -> None:
    """The off value has to leave the signal exactly as it was, or every stored row moves."""
    assert ElasticBandParams().entry_trigger == TRIGGER_EXTENDED
    rng = np.random.default_rng(67)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 600))
    params = vwap_params()
    data = dataset(close, params)
    assert np.array_equal(
        elasticband_signal(data, params),
        beyond_band(data.vwap_band_stretch(), params),
    )


def test_the_recovery_trigger_fires_inside_the_band_after_a_run_outside_it() -> None:
    rng = np.random.default_rng(71)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 900))
    params = recovery_params()
    data = dataset(close, params)
    signal = elasticband_signal(data, params)
    stretch = data.vwap_band_stretch()
    assert signal.any()
    assert not signal[0]
    # Back inside the band, and the bar before it was beyond it on the same side.
    assert (np.abs(stretch[signal]) < 2.0).all()
    previous = lagged(stretch, 1)[signal]
    assert (np.abs(previous) >= 2.0).all()
    assert (np.sign(previous) == np.sign(stretch[signal])).all()


def test_the_two_triggers_can_never_fire_on_the_same_bar() -> None:
    """One reads a bar beyond the threshold and the other a bar back inside it."""
    rng = np.random.default_rng(73)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 900))
    extended, recovery = vwap_params(), recovery_params(vwap_min_session_bars=0)
    data = dataset(close, extended)
    outside = elasticband_signal(data, extended)
    inside = elasticband_signal(data, recovery)
    assert outside.any()
    assert inside.any()
    assert not (outside & inside).any()


def test_a_deeper_recovery_is_a_subset_of_a_shallower_one() -> None:
    rng = np.random.default_rng(79)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 1200))
    edge, deep = recovery_params(), recovery_params(recovery_fraction=0.5)
    data = dataset(close, edge)
    loose, tight = elasticband_signal(data, edge), elasticband_signal(data, deep)
    stretch = data.vwap_band_stretch()
    assert tight.any()
    assert (tight <= loose).all()
    assert (tight < loose).any()
    assert (np.abs(stretch[tight]) <= 1.0).all()
    dropped = loose & ~tight
    assert (np.abs(stretch[dropped]) > 1.0).all()


def test_the_band_edge_is_the_loosest_depth_and_the_edge_itself_still_fails() -> None:
    stretch = np.array([-2.5, -2.0, -1.99, -1.0, 0.0, 1.0, 1.99, 2.0, 2.5])
    params = ElasticBandParams(entry_std=2.0, entry_trigger=TRIGGER_RECOVERY)
    passed = returned_inside(stretch, params).tolist()
    assert passed == [False, False, True, True, False, True, True, False, False]


def test_a_close_exactly_on_the_basis_recovers_on_neither_side() -> None:
    """One sign multiplier means the long and short arms have to be the same rule."""
    stretch = np.array([-0.5, 0.0, 0.5])
    half = ElasticBandParams(entry_std=2.0, entry_trigger=TRIGGER_RECOVERY, recovery_fraction=0.5)
    assert returned_inside(stretch, half).tolist() == [True, False, True]


def test_the_run_a_recovery_entry_reads_is_the_one_that_ended_at_the_bar_before() -> None:
    outside = np.array([False, True, True, True, False, False, True, False])
    assert outside_run_length(outside, ends_before=False).tolist() == [0, 1, 2, 3, 0, 0, 1, 0]
    assert outside_run_length(outside, ends_before=True).tolist() == [0, 0, 1, 2, 3, 0, 0, 1]


def test_a_longer_run_requirement_still_narrows_the_recovery_trigger() -> None:
    """The one entry here under which the run length is not a duplicate of the gate beside it."""
    rng = np.random.default_rng(83)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 1200))
    one, three = recovery_params(), recovery_params(min_bars_outside=3)
    data = dataset(close, one)
    first, third = elasticband_signal(data, one), elasticband_signal(data, three)
    assert third.any()
    assert (third <= first).all()
    assert (third < first).any()


def test_the_ceiling_gates_the_bar_the_extension_was_measured_on() -> None:
    """Under the recovery trigger the signal bar is inside the band, so the ceiling reads i-1."""
    rng = np.random.default_rng(89)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 1200))
    base, capped = recovery_params(), recovery_params(max_entry_std=2.5)
    data = dataset(close, base)
    loose, tight = elasticband_signal(data, base), elasticband_signal(data, capped)
    stretch = data.vwap_band_stretch()
    dropped = loose & ~tight
    assert tight.any()
    assert dropped.any()
    assert (tight <= loose).all()
    # It is the bar the run ended on that was too far out, never the signal bar itself.
    assert (np.abs(lagged(stretch, 1)[dropped]) > 2.5).all()
    assert (np.abs(stretch[dropped]) < 2.0).all()


def test_the_recovery_signal_reads_only_bars_up_to_and_including_its_own() -> None:
    """The property the archetype is worthless without, over the trigger that looks back."""
    rng = np.random.default_rng(97)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 800))
    params = recovery_params(min_bars_outside=2, recovery_fraction=0.75)
    full = elasticband_signal(dataset(close, params), params)
    for cut in (120, 455, 799):
        assert np.array_equal(elasticband_signal(dataset(close[:cut], params), params), full[:cut])


def test_the_excursion_stop_hangs_off_the_run_that_ended_rather_than_off_nothing() -> None:
    """``run_extreme`` reads ``nan`` inside the band, which would refuse every trade silently."""
    rng = np.random.default_rng(101)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1500))
    params = recovery_params(stop_mode=STOP_EXCURSION, max_hold_bars=10)
    log = run_elasticband(dataset(close, params), params)
    assert not log.empty
    assert np.isfinite(log["initial_stop"]).all()
    longs = log[log["direction"] == LONG]
    assert not longs.empty
    assert (longs["initial_stop"] < longs["entry_price"]).all()


def test_the_band_stop_reads_the_same_band_under_both_triggers() -> None:
    """The three reads that had to move a bar back for the recovery trigger are the run's;
    the band stop is a level on the channel itself, so it is defined on a signal bar inside
    the band as much as on one outside it -- ``docs/nt8-fidelity.md`` §M26.8."""
    rng = np.random.default_rng(107)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1500))
    params = recovery_params(stop_mode=STOP_BAND, band_stop_std=1.0, max_hold_bars=10)
    data = dataset(close, params)
    log = run_elasticband(data, params)
    assert not log.empty
    assert np.isfinite(log["initial_stop"]).all()
    basis, stddev, _ = elasticband.band_series(data, params)
    signal_bars = log["entry_bar"].to_numpy(dtype=int) - 1
    expected = basis[signal_bars] - log["direction"].to_numpy() * 3.0 * stddev[signal_bars]
    assert log["initial_stop"].to_numpy() == pytest.approx(expected)


def test_a_recovery_run_produces_a_valid_trade_log() -> None:
    rng = np.random.default_rng(103)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1500))
    params = recovery_params(
        recovery_fraction=0.75,
        max_hold_bars=10,
        commission_per_contract=1.5,
        slippage_ticks=1.0,
    )
    log = run_elasticband(dataset(close, params), params)
    assert not log.empty
    validate(log)


def test_an_unknown_entry_trigger_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown entry_trigger 5"):
        ElasticBandParams(entry_trigger=5)


@pytest.mark.parametrize("fraction", [-0.1, 0.0, 1.1])
def test_a_recovery_depth_outside_the_band_is_refused(fraction) -> None:
    with pytest.raises(ValueError, match=r"must be in \(0, 1\]"):
        ElasticBandParams(recovery_fraction=fraction)


# -- the archetype end to end ---------------------------------------------------


def test_a_full_run_produces_a_valid_trade_log_on_both_instruments() -> None:
    rng = np.random.default_rng(23)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1200))
    params = ElasticBandParams(band_period=20, bars_required_to_trade=30, max_hold_bars=10)
    data = dataset(close, params)
    mnq = run_elasticband(data, params, MNQ)
    nq = run_elasticband(data, params, NQ)
    assert not mnq.empty
    assert mnq["exit_reason"].isin(set(EXIT_REASONS.values())).all()
    # Identical geometry, ten times the money -- instruments.py is the only difference.
    assert nq["entry_price"].tolist() == mnq["entry_price"].tolist()
    assert nq["gross_pnl"].to_numpy() == pytest.approx(10.0 * mnq["gross_pnl"].to_numpy())


def test_a_band_stop_run_produces_a_valid_trade_log_with_every_stop_beyond_its_fill() -> None:
    rng = np.random.default_rng(109)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1500))
    params = vwap_params(
        stop_mode=STOP_BAND,
        band_stop_std=0.5,
        max_hold_bars=10,
        commission_per_contract=1.5,
        slippage_ticks=1.0,
    )
    log = run_elasticband(dataset(close, params), params)
    assert not log.empty
    validate(log)
    adverse = log["direction"].to_numpy() * (log["entry_price"] - log["initial_stop"]).to_numpy()
    assert (adverse >= MNQ.tick_size).all()


def test_the_registry_carries_it_as_tier_one_only_with_both_tuples_off_the_axes() -> None:
    band = archetypes.get("ElasticBand")
    assert band.tier2 is archetypes.Tier2Status.TIER1_ONLY
    assert "target_r_multiples" not in band.sweepable
    assert "target_stretch_levels" not in band.sweepable
    assert "entry_std" in band.sweepable


def test_the_context_it_asks_for_holds_a_band_and_no_moving_average_at_all() -> None:
    grid = sweep.Grid.of(
        ElasticBandParams(band_period=20),
        archetype=archetypes.ELASTICBAND,
        entry_std=[2.0, 2.5, 3.0],
    )
    spec = grid.required_context()
    assert spec.band_periods == (20,)
    assert spec.ma_keys == ()
    # The multiple is free: three values of entry_std, still one band grid.
    assert len(spec.band_periods) == 1


def test_the_atr_is_built_only_for_the_stop_mode_that_reads_one() -> None:
    atr_stop = sweep.Grid.of(ElasticBandParams(stop_mode=STOP_ATR), archetype=archetypes.ELASTICBAND)
    no_atr = sweep.Grid.of(
        ElasticBandParams(stop_mode=STOP_EXCURSION),
        archetype=archetypes.ELASTICBAND,
    )
    assert atr_stop.required_context().atr_periods == (14,)
    assert no_atr.required_context().atr_periods == ()


# -- the buffer guard, one case per write site ----------------------------------

WIDE_STOP = {"stop_mode": STOP_CATASTROPHE, "catastrophe_stop_ticks": 400.0}
NEAR_STOP = {"stop_mode": STOP_CATASTROPHE, "catastrophe_stop_ticks": 40.0}
RUNNERS = {"quantities": (1, 1), "levels": (np.nan, np.nan)}

OVERFLOW_CASES = {
    "the signal exit": (FLAT, {"signal_at": [0], **RUNNERS, **WIDE_STOP, "max_hold_bars": 2}),
    "a stop while in a position": (
        [*[(100.0, 100.5, 99.5, 100.0)] * 2, (100.0, 100.5, 85.0, 86.0), *FLAT],
        {"signal_at": [0], **RUNNERS, **NEAR_STOP},
    ),
    "the entry bar's own stop": (
        [(100.0, 100.5, 99.5, 100.0), (100.0, 100.5, 85.0, 86.0), *FLAT],
        {"signal_at": [0], **RUNNERS, **NEAR_STOP},
    ),
    "the end of the series": (FLAT, {"signal_at": [0], **RUNNERS, **WIDE_STOP}),
}


@pytest.mark.parametrize(("rows", "kwargs"), OVERFLOW_CASES.values(), ids=list(OVERFLOW_CASES))
def test_a_full_buffer_is_reported_rather_than_written_past(rows, kwargs) -> None:
    # One row of room against a two-leg trade, so the second write has nowhere to go.
    assert simulate(rows, max_rows=1, **kwargs)[0] == -1
    # The same scenario with room is a normal trade, which is what says the buffer size is
    # the only thing under test here.
    assert not run(rows, **kwargs).empty
