"""ElasticBand simulation tests on hand-built bars.

The archetype has no NinjaScript, so like EmaCrossover there is no trade list to check against.
What these pin instead are the things it introduces -- three stop schemes, a target expressed
as a band level rather than as an R multiple, and two rule-driven exits -- plus the property
the whole thing is worthless without: that nothing it reads comes from a bar it could not have
seen.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, sweep
from nqbt.instruments import MNQ, NQ
from nqbt.sim import elasticband
from nqbt.sim.elasticband import (
    beyond_band,
    elasticband_signal,
    fade_direction,
    lagged,
    run_elasticband,
    run_extreme,
)
from nqbt.sim.types import (
    STOP_ATR,
    STOP_CATASTROPHE,
    STOP_EXCURSION,
    STOP_SWING,
    TARGET_R,
    TARGET_STRETCH,
    ElasticBandParams,
)
from nqbt.trades import LONG, N_COLUMNS, SHORT, trades_to_frame, validate

TICK = 0.25


def simulate(
    rows,
    signal_at=(),
   
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


# -- the three stop schemes -----------------------------------------------------


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


# -- the two rule-driven exits, both EXIT_SIGNAL --------------------------------


def test_the_time_stop_leaves_at_the_next_open_once_the_hold_is_reached() -> None:
    trades = run(FLAT, signal_at=[0], levels=(np.nan,), max_hold_bars=3)
    # Filled on bar 1; bar 4 is three bars later, so the order goes in at its close.
    assert trades["exit_bar"].iloc[0] == 5
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


# -- the archetype end to end ---------------------------------------------------


def test_a_full_run_produces_a_valid_trade_log_on_both_instruments() -> None:
    rng = np.random.default_rng(23)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 1200))
    params = ElasticBandParams(band_period=20, bars_required_to_trade=30, max_hold_bars=10)
    data = dataset(close, params)
    mnq = run_elasticband(data, params, MNQ)
    nq = run_elasticband(data, params, NQ)
    assert not mnq.empty
    assert mnq["exit_reason"].isin({"stop", "target", "signal", "session_close", "end_of_data"}).all()
    # Identical geometry, ten times the money -- instruments.py is the only difference.
    assert nq["entry_price"].tolist() == mnq["entry_price"].tolist()
    assert nq["gross_pnl"].to_numpy() == pytest.approx(10.0 * mnq["gross_pnl"].to_numpy())


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
