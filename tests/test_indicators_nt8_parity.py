"""NT8 parity for the M16 indicators: ATR, StdDev, Bollinger and Keltner.

The expected values below were read out of NinjaTrader 8 by
``ninjatrader-scripts/Strategies/NqbtIndicatorProbe.cs`` over MNQ 03-24, 1-minute, and are
the first 40 bars of that export. Bar 0 is included deliberately: every question M16 had
was about seeding, and the steady-state recursion was never in doubt.

Evidence, and what each rule turned out to be, is in ``docs/nt8-fidelity.md``.
"""

from __future__ import annotations

import numpy as np
import pytest

from nqbt import indicators

# open;high;low;close;ATR(14);SMA(20);StdDev(20);Bollinger(2,20).Upper;
# KeltnerChannel(1.5,20).Midline;KeltnerChannel(1.5,20).Upper
NT8_FIRST_40_BARS = """
16027.0;16027.0;16010.75;16015.25;16.25;16015.25;0.0;16015.25;16017.666666666666;16042.041666666666
16015.0;16020.75;16014.0;16017.75;11.5;16016.5;1.25;16019.0;16017.583333333332;16034.833333333332
16018.0;16023.25;16017.5;16021.75;9.583333333333332;16018.25;2.6770630673681683;16023.604126134736;16018.666666666666;16033.041666666666
16021.75;16022.25;16019.0;16021.75;8.0;16019.125;2.7698149757700423;16024.66462995154;16019.25;16031.25
16021.75;16024.75;16021.0;16022.0;7.15;16019.7;2.731300056749532;16025.1626001135;16019.916666666666;16030.641666666666
16022.0;16024.75;16021.5;16024.5;6.5;16020.5;3.0686587732536608;16026.637317546509;16020.527777777776;16030.277777777776
16024.75;16026.75;16022.75;16023.25;6.142857142857143;16020.892857142857;2.9995747997994373;16026.892006742455;16021.059523809525;16030.273809523807
16023.5;16023.5;16020.25;16021.25;5.78125;16020.9375;2.8083302423326213;16026.554160484666;16021.135416666666;16029.807291666666
16021.0;16026.0;16021.0;16024.75;5.694444444444445;16021.361111111111;2.9061981443667926;16027.173507399844;16021.444444444443;16029.986111111111
16024.75;16025.75;16023.25;16024.0;5.375;16021.625;2.8684708469845046;16027.361941693967;16021.733333333334;16029.795833333334
16024.0;16025.25;16023.0;16023.5;5.090909090909091;16021.795454545454;2.787590564811266;16027.370635675075;16021.931818181818;16029.568181818182
16023.75;16025.0;16023.25;16023.5;4.8125;16021.9375;2.710175655438837;16027.357851310877;16022.09722222222;16029.31597222222
16024.25;16025.0;16023.25;16024.75;4.576923076923077;16022.153846153846;2.7095601075324685;16027.572966368913;16022.26923076923;16029.134615384615
16024.25;16026.25;16024.0;16025.25;4.410714285714286;16022.375;2.7300412084801944;16027.83508241696;16022.476190476187;16029.09226190476
16025.5;16025.75;16024.25;16024.75;4.20280612244898;16022.533333333333;2.7031874189967326;16027.939708171329;16022.638888888889;16028.963888888888
16024.75;16025.75;16023.25;16023.75;4.081177113702624;16022.609375;2.633867092200174;16027.8771091844;16022.739583333332;16028.903645833332
16023.75;16028.5;16023.5;16028.0;4.1468073198667215;16022.926470588236;2.852713756854465;16028.631898101945;16022.970588235294;16029.213235294115
16028.0;16028.75;16026.75;16028.0;3.9934639398762415;16023.208333333334;3.006070247571292;16029.220473828476;16023.24074074074;16029.30324074074
16028.0;16030.0;16028.0;16028.25;3.851073658456511;16023.473684210529;3.135004760386406;16029.7436937313;16023.530701754386;16029.43201754386
16027.75;16031.75;16027.75;16031.75;3.861711254281045;16023.8875;3.5483050531204343;16030.98411010624;16023.875;16029.78125
16032.0;16034.0;16030.25;16031.75;3.853731878975256;16024.7125;3.3571518806869616;16031.426803761373;16024.591666666664;16029.560416666664
16031.25;16033.0;16030.0;16031.0;3.792751030477024;16025.375;3.2224796353119127;16031.819959270624;16025.283333333333;16029.970833333333
16031.25;16033.5;16030.5;16032.75;3.7361259568715215;16025.925;3.484878046646683;16032.894756093292;16025.854166666666;16030.335416666669
16033.0;16033.75;16032.0;16032.25;3.5942598170949847;16026.45;3.605204571172072;16033.660409142343;16026.4375;16030.80625
16032.25;16032.75;16031.25;16032.5;3.444669830159629;16026.975;3.682645109157275;16034.340290218315;16026.916666666668;16031.116666666669
16032.5;16032.75;16029.5;16030.5;3.430764842291084;16027.275;3.7130681383459687;16034.701136276692;16027.283333333336;16031.483333333335
16030.5;16031.5;16029.75;16030.5;3.310710210698864;16027.6375;3.655881391675612;16034.949262783352;16027.600000000002;16031.631250000002
16030.75;16030.75;16029.5;16030.5;3.1635166242203736;16028.1;3.3942966870914515;16034.888593374184;16028.029166666667;16031.910416666668
16030.75;16031.25;16030.0;16031.0;3.02683686534749;16028.4125;3.359013061897796;16035.130526123796;16028.370833333334;16031.970833333336
16030.75;16032.25;16030.75;16032.25;2.9177770892512407;16028.825;3.297821250462191;16035.420642500923;16028.741666666669;16032.266666666668
16032.25;16032.5;16031.25;16031.75;2.7986501543047235;16029.2375;3.1169646693538264;16035.471429338708;16029.1375;16032.5875
16031.75;16032.5;16030.25;16030.75;2.759460857568672;16029.6;2.8376927247325425;16035.275385449466;16029.5;16032.9875
16030.75;16031.75;16027.25;16027.5;2.8837850820280524;16029.7375;2.660445216500426;16035.058390433;16029.725;16033.41875
16027.75;16029.75;16026.75;16028.25;2.8920861475974773;16029.8875;2.4817773369099814;16034.85105467382;16029.879166666666;16033.629166666666
16028.25;16031.25;16028.25;16030.25;2.8997942799119434;16030.1625;2.1841402770884484;16034.530780554178;16030.129166666666;16033.991666666663
16030.75;16031.75;16030.5;16031.0;2.799808974203948;16030.525;1.6180621125284411;16033.761124225057;16030.470833333333;16034.23958333333
16031.75;16033.25;16031.25;16032.25;2.760536904617951;16030.7375;1.5501512023025366;16033.837802404603;16030.749999999996;16034.293749999995
16032.25;16033.0;16032.0;16032.25;2.6347842685738114;16030.95;1.4482748357960238;16033.846549671593;16030.979166666666;16034.447916666666
16032.25;16032.75;16031.75;16031.75;2.5180139636756818;16031.125;1.3169567191065925;16033.758913438212;16031.145833333332;16034.539583333331
16032.0;16032.25;16029.75;16031.5;2.5167272519845616;16031.1125;1.3121428085387656;16033.736785617077;16031.183333333332;16034.464583333332
"""

TOLERANCE = {"rtol": 1e-11, "atol": 1e-9}
"""Recursive float arithmetic will not reproduce NT8 bit for bit, and does not need to.

At index-future prices this is under 2e-7 of a point against a 0.25 tick, so it cannot move
a gate. Over the full 89,330-bar export every series here agrees at this tolerance on every
bar.
"""


@pytest.fixture(scope="module")
def pinned():
    rows = [
        [float(v) for v in line.split(";")]
        for line in NT8_FIRST_40_BARS.strip().splitlines()
    ]
    columns = np.array(rows, dtype=np.float64).T
    names = ("open", "high", "low", "close", "atr14", "sma20", "stddev20",
             "bb_upper", "kc_midline", "kc_upper")
    return dict(zip(names, columns))


def test_true_range_is_the_bare_range_on_the_first_bar(pinned) -> None:
    tr = indicators.nt8_true_range(pinned["high"], pinned["low"], pinned["close"])
    assert tr[0] == pinned["high"][0] - pinned["low"][0]


def test_true_range_reads_the_previous_close(pinned) -> None:
    h, l, c = pinned["high"], pinned["low"], pinned["close"]
    tr = indicators.nt8_true_range(h, l, c)
    expected = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    assert np.array_equal(tr[1:], expected)


def test_atr_matches_nt8(pinned) -> None:
    got = indicators.nt8_atr(pinned["high"], pinned["low"], pinned["close"], 14)
    assert np.allclose(got, pinned["atr14"], **TOLERANCE)


def test_atr_seeds_with_an_expanding_simple_average_not_wilder(pinned) -> None:
    """The whole of #20. Wilder from bar 0 is the textbook form and is not what NT8 does.

    At bar 1 with period 14 the two differ by more than 4 points on this data, so a seeding
    mistake is not a rounding difference -- it is a different indicator that converges
    slowly enough to look right much later.
    """
    h, l, c = pinned["high"], pinned["low"], pinned["close"]
    tr = indicators.nt8_true_range(h, l, c)
    got = indicators.nt8_atr(h, l, c, 14)

    assert got[1] == pytest.approx((tr[0] + tr[1]) / 2)
    wilder_from_bar_zero = (tr[0] * 13 + tr[1]) / 14
    assert abs(wilder_from_bar_zero - got[1]) > 4.0


def test_atr_switches_to_wilder_once_the_window_fills(pinned) -> None:
    h, l, c = pinned["high"], pinned["low"], pinned["close"]
    tr = indicators.nt8_true_range(h, l, c)
    got = indicators.nt8_atr(h, l, c, 14)
    assert got[14] == pytest.approx((got[13] * 13 + tr[14]) / 14)


def test_atr_emits_from_bar_zero(pinned) -> None:
    got = indicators.nt8_atr(pinned["high"], pinned["low"], pinned["close"], 14)
    assert np.isfinite(got).all()


def test_stddev_matches_nt8(pinned) -> None:
    got = indicators.nt8_stddev(pinned["close"], 20)
    assert np.allclose(got, pinned["stddev20"], **TOLERANCE)


def test_stddev_uses_the_population_divisor(pinned) -> None:
    """#21's first question. The sample divisor differs materially in the warm-up."""
    close = pinned["close"]
    got = indicators.nt8_stddev(close, 20)
    window = close[:2]
    assert got[1] == pytest.approx(window.std(ddof=0))
    assert got[1] != pytest.approx(window.std(ddof=1))


def test_stddev_uses_an_expanding_partial_window(pinned) -> None:
    got = indicators.nt8_stddev(pinned["close"], 20)
    assert got[0] == 0.0
    for i in (3, 7, 15):
        assert got[i] == pytest.approx(pinned["close"][: i + 1].std(ddof=0))


def test_bollinger_is_the_sma_plus_that_same_stddev(pinned) -> None:
    upper, middle, lower = indicators.nt8_bollinger(pinned["close"], 20, 2.0)
    assert np.allclose(upper, pinned["bb_upper"], **TOLERANCE)
    assert np.allclose(middle, pinned["sma20"], **TOLERANCE)
    assert np.allclose(middle - (upper - middle), lower)


def test_keltner_matches_nt8(pinned) -> None:
    upper, midline, _ = indicators.nt8_keltner(
        pinned["high"], pinned["low"], pinned["close"], 20, 1.5
    )
    assert np.allclose(midline, pinned["kc_midline"], **TOLERANCE)
    assert np.allclose(upper, pinned["kc_upper"], **TOLERANCE)


def test_keltner_centres_on_typical_price_not_close(pinned) -> None:
    """#22's first question, and the one most likely to be got wrong from memory."""
    _, midline, _ = indicators.nt8_keltner(
        pinned["high"], pinned["low"], pinned["close"], 20, 1.5
    )
    assert np.allclose(midline, pinned["kc_midline"], **TOLERANCE)
    assert not np.allclose(midline, indicators.nt8_sma(pinned["close"], 20), **TOLERANCE)
    typical = indicators.typical_price(pinned["high"], pinned["low"], pinned["close"])
    assert not np.allclose(midline, indicators.nt8_ema(typical, 20), **TOLERANCE)


def test_keltner_width_is_the_mean_range_not_atr(pinned) -> None:
    """The other half of #22, and the reason it was flagged as silently wrong.

    Both quantities average a per-bar measure of movement and are close enough that a wrong
    one looks plausible on a chart -- but they differ whenever a gap makes True Range exceed
    the bare high-low range.
    """
    upper, midline, _ = indicators.nt8_keltner(
        pinned["high"], pinned["low"], pinned["close"], 20, 1.5
    )
    half_width = (upper - midline) / 1.5
    mean_range = indicators.nt8_sma(pinned["high"] - pinned["low"], 20)
    atr = indicators.nt8_atr(pinned["high"], pinned["low"], pinned["close"], 20)
    assert np.allclose(half_width, mean_range, **TOLERANCE)
    assert not np.allclose(half_width, atr, **TOLERANCE)


def test_keltner_is_symmetric(pinned) -> None:
    upper, midline, lower = indicators.nt8_keltner(
        pinned["high"], pinned["low"], pinned["close"], 20, 1.5
    )
    assert np.allclose(upper - midline, midline - lower)
