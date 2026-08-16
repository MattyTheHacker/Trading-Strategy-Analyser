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


@pytest.mark.parametrize("period", [1, 2, 21, 175])
def test_moving_averages_handle_short_and_empty_inputs(period: int) -> None:
    assert indicators.nt8_ema(np.array([], dtype=np.float64), period).size == 0
    assert indicators.nt8_sma(np.array([], dtype=np.float64), period).size == 0
    single = np.array([42.0])
    assert indicators.nt8_ema(single, period)[0] == pytest.approx(42.0)
    assert indicators.nt8_sma(single, period)[0] == pytest.approx(42.0)


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
        ["2024-03-07", "2024-03-07", "2024-03-08", "2024-03-08", "2024-03-11"], dtype="datetime64[D]"
    )
    assert list(indicators.new_session_flags(days)) == [True, False, True, False, True]


def test_new_session_flags_on_empty_input() -> None:
    assert indicators.new_session_flags(np.array([], dtype="datetime64[D]")).size == 0
