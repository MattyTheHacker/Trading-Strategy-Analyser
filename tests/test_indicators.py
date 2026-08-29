"""Indicator tests pinned against NT8's own recursions, not TA-Lib's."""

import numpy as np
import pytest
import talib

from nqbt import indicators

RAMP = np.arange(10, dtype=np.float64)


def test_nt8_ema_matches_the_hand_computed_recursion() -> None:
    # k = 2/(1+3) = 0.5, seeded with values[0] rather than a warm-up average.
    expected = [0.0, 0.5, 1.25, 2.125, 3.0625, 4.03125, 5.015625, 6.0078125, 7.00390625, 8.001953125]
    assert indicators.nt8_ema(RAMP, 3) == pytest.approx(expected)


def test_nt8_ema_differs_from_talib_which_is_why_it_exists() -> None:
    ours = indicators.nt8_ema(RAMP, 3)
    theirs = talib.EMA(RAMP, timeperiod=3)

    # TA-Lib seeds with SMA(first 3) and emits nothing before index 2.
    assert np.isnan(theirs[:2]).all()
    assert np.isfinite(ours).all()

    # They converge but never coincide: 8.001953125 vs exactly 8.0.
    assert theirs[-1] == pytest.approx(8.0, abs=1e-12)
    assert ours[-1] == pytest.approx(8.001953125, abs=1e-12)
    assert ours[-1] != theirs[-1]


def test_nt8_ema_seeding_difference_decays_with_distance() -> None:
    values = np.random.default_rng(0).normal(20000, 50, 5000)
    ours = indicators.nt8_ema(values, 21)
    theirs = talib.EMA(values, timeperiod=21)
    # Far from the seed the two agree to well inside a tick.
    assert abs(ours[-1] - theirs[-1]) < 1e-9


def test_nt8_sma_averages_a_partial_window_during_warm_up() -> None:
    out = indicators.nt8_sma(RAMP, 3)
    # NT8 shows a value from bar 0; TA-Lib shows nothing until index 2.
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(0.5)  # mean(0, 1)
    assert out[2] == pytest.approx(1.0)  # mean(0, 1, 2)
    assert np.isnan(talib.SMA(RAMP, timeperiod=3)[:2]).all()


def test_nt8_sma_is_a_true_rolling_mean_once_warmed_up() -> None:
    out = indicators.nt8_sma(RAMP, 3)
    assert out[3] == pytest.approx(2.0)  # mean(1, 2, 3)
    assert out[-1] == pytest.approx(8.0)  # mean(7, 8, 9)
    assert out[2:] == pytest.approx(talib.SMA(RAMP, timeperiod=3)[2:])


def test_nt8_sma_recursion_does_not_drift_meaningfully_over_a_long_series() -> None:
    values = np.random.default_rng(1).normal(20000, 100, 1_000_000)
    out = indicators.nt8_sma(values, 175)
    exact = values[-175:].mean()
    # Accumulated float error must stay far below a 0.25 tick.
    assert abs(out[-1] - exact) < 1e-6


@pytest.mark.parametrize("period", [2, 21, 175])
def test_moving_averages_handle_short_and_empty_inputs(period: int) -> None:
    empty = np.array([], dtype=np.float64)
    single = np.array([42.0])
    for kind in (indicators.nt8_ema, indicators.nt8_sma, indicators.nt8_wma, indicators.nt8_hma):
        assert kind(empty, period).size == 0
        assert kind(single, period)[0] == pytest.approx(42.0)
    # Period 1 is legal for every kind but the HMA, whose inner WMA(0) has nothing to average.
    assert indicators.nt8_ema(single, 1)[0] == pytest.approx(42.0)
    assert indicators.nt8_wma(single, 1)[0] == pytest.approx(42.0)


# -- WMA and HMA ---------------------------------------------------------------


def test_nt8_wma_weights_the_newest_bar_heaviest_by_hand() -> None:
    # @WMA.cs: weights 1..k with k on the current bar, over min(period, bars so far).
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    expected = [1.0, 5 / 3, 14 / 6, 20 / 6, 26 / 6]
    assert indicators.nt8_wma(values, 3) == pytest.approx(expected)


def test_nt8_wma_averages_an_expanding_window_during_warm_up() -> None:
    out = indicators.nt8_wma(RAMP, 4)
    # Bar 1 sees two bars, not four: (2*1 + 1*0) / 3.
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(2 / 3)
    assert out[2] == pytest.approx((3 * 2 + 2 * 1 + 1 * 0) / 6)


def test_nt8_wma_at_period_one_is_the_series_itself() -> None:
    assert indicators.nt8_wma(RAMP, 1) == pytest.approx(RAMP)


def test_nt8_wma_lags_a_ramp_less_than_the_sma_does() -> None:
    wma = indicators.nt8_wma(RAMP, 5)
    sma = indicators.nt8_sma(RAMP, 5)
    # On a rising line the weighted average sits nearer the newest bar throughout.
    assert (wma[1:] > sma[1:]).all()


def test_nt8_wma_matches_the_recursive_form_of_the_same_sum() -> None:
    """The two branches of ``@WMA.cs`` agree, so the exact one is safe to prefer.

    This one rebuilds the weighted sum every bar, which is what NT8 does for a bar type
    supporting ``RemoveLastBar``; the other carries it forward. Algebraically identical, and
    the accumulating form is the one that drifts -- ``docs/nt8-fidelity.md``.
    """
    values = np.random.default_rng(7).normal(18000, 40, 20_000)
    period = 60

    recursive = np.empty(values.size)
    weighted = running = 0.0
    for i, value in enumerate(values):
        span = min(i + 1, period)
        weighted += span * value - (running if i >= period else 0.0)
        running += value - (values[i - period] if i >= period else 0.0)
        recursive[i] = weighted / (0.5 * span * (span + 1))

    assert indicators.nt8_wma(values, period) == pytest.approx(recursive, rel=1e-9)


def test_nt8_hma_is_the_ninjascripts_composition_of_three_wmas() -> None:
    # @HMA.cs: WMA(2*WMA(p/2) - WMA(p), sqrt(p)), both inner lengths truncating.
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    expected = [1.0, 13 / 9, 23 / 9, 35 / 9, 5.0, 6.0]
    assert indicators.nt8_hma(values, 4) == pytest.approx(expected)


def test_nt8_hma_truncates_both_inner_lengths() -> None:
    values = np.random.default_rng(3).normal(18000, 40, 500)
    half = indicators.nt8_wma(values, 14 // 2)
    full = indicators.nt8_wma(values, 14)
    # sqrt(14) is 3.74, and NT8 casts it to int rather than rounding.
    expected = indicators.nt8_wma(2.0 * half - full, 3)
    assert indicators.nt8_hma(values, 14) == pytest.approx(expected)
    assert indicators.nt8_hma(values, 14) != pytest.approx(indicators.nt8_wma(2.0 * half - full, 4))


def test_nt8_hma_catches_up_with_a_ramp_where_the_wma_still_lags() -> None:
    hma = indicators.nt8_hma(RAMP, 4)
    wma = indicators.nt8_wma(RAMP, 4)
    # The Hull construction is built to remove the lag a plain WMA leaves on a straight line.
    assert hma[-1] == pytest.approx(RAMP[-1])
    assert wma[-1] < RAMP[-1]


def test_nt8_hma_refuses_a_period_below_two() -> None:
    with pytest.raises(ValueError, match="nt8_hma needs period >= 2"):
        indicators.nt8_hma(RAMP, 1)


# -- VWAP ---------------------------------------------------------------------


def test_session_vwap_accumulates_within_a_session() -> None:
    price = np.array([10.0, 20.0])
    volume = np.array([1.0, 1.0])
    out = indicators.session_vwap(price, volume, np.array([True, False]))
    assert out == pytest.approx([10.0, 15.0])


def test_session_vwap_reanchors_at_each_session_open() -> None:
    price = np.array([10.0, 20.0, 100.0, 200.0])
    volume = np.array([1.0, 1.0, 1.0, 1.0])
    out = indicators.session_vwap(price, volume, np.array([True, False, True, False]))
    # The second session starts clean rather than inheriting the first session's average.
    assert out == pytest.approx([10.0, 15.0, 100.0, 150.0])


def test_session_vwap_weights_by_volume() -> None:
    price = np.array([10.0, 20.0])
    volume = np.array([1.0, 3.0])
    out = indicators.session_vwap(price, volume, np.array([True, False]))
    assert out[1] == pytest.approx((10 * 1 + 20 * 3) / 4)


def test_session_vwap_survives_zero_volume_bars() -> None:
    price = np.array([10.0, 20.0, 30.0])
    volume = np.array([0.0, 0.0, 2.0])
    out = indicators.session_vwap(price, volume, np.array([True, False, False]))
    # No division by zero; the bar's own price stands in until volume arrives.
    assert out == pytest.approx([10.0, 20.0, 30.0])


def test_typical_price() -> None:
    high = np.array([12.0])
    low = np.array([9.0])
    close = np.array([11.0])
    assert indicators.typical_price(high, low, close) == pytest.approx([32.0 / 3.0])


def test_new_session_flags_marks_each_days_first_bar() -> None:
    days = np.array(
        ["2024-03-07", "2024-03-07", "2024-03-08", "2024-03-08", "2024-03-11"],
        dtype="datetime64[D]",
    )
    assert list(indicators.new_session_flags(days)) == [True, False, True, False, True]


def test_new_session_flags_on_empty_input() -> None:
    assert indicators.new_session_flags(np.array([], dtype="datetime64[D]")).size == 0


def test_band_stretch_is_the_band_multiple_a_value_sits_at() -> None:
    values = np.array([100.0, 104.0, 95.0])
    basis = np.array([100.0, 100.0, 100.0])
    stddev = np.array([2.0, 2.0, 2.0])
    assert indicators.band_stretch(values, basis, stddev) == pytest.approx([0.0, 2.0, -2.5])


def test_band_stretch_reads_zero_where_the_window_has_no_dispersion() -> None:
    # Not inf, not nan: a flat window has no extension to measure.
    out = indicators.band_stretch(
        np.array([100.0, 105.0]),
        np.array([100.0, 100.0]),
        np.zeros(2),
    )
    assert list(out) == [0.0, 0.0]
    assert np.isfinite(out).all()


def test_band_stretch_crosses_a_multiple_exactly_where_the_bollinger_band_does() -> None:
    rng = np.random.default_rng(11)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 3.0, 5_000))
    period = 20
    stddev = indicators.nt8_stddev(close, period)
    flat = stddev == 0.0
    # Only bar 0, where the bands collapse onto the close -- ``docs/roadmap.md`` §M26.
    assert list(np.flatnonzero(flat)) == [0]
    for num_std in (1.0, 2.0, 3.0):
        upper, middle, lower = indicators.nt8_bollinger(close, period, num_std)
        stretch = indicators.band_stretch(close, middle, stddev)
        assert np.array_equal((stretch >= num_std)[~flat], (close >= upper)[~flat])
        assert np.array_equal((stretch <= -num_std)[~flat], (close <= lower)[~flat])


def test_band_stretch_on_empty_input() -> None:
    empty = np.array([], dtype=np.float64)
    assert indicators.band_stretch(empty, empty, empty).size == 0
