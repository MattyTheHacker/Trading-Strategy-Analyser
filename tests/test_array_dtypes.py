"""The dtypes the aliases in :mod:`nqbt.arrays` claim, asserted against real objects.

An annotation is not checked at runtime, so a wrong one reads as a guarantee and is worse
than none. These pin the three the whole scheme rests on -- the moving-average grid's gate
against its values, the session's dates against its flags, and the leg matrix everything is
written into as a float.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import context, regime, sessions, timeofday, trend, volume
from nqbt.context import ContextSpec
from nqbt.sim import runner
from nqbt.sim.types import DeadCatParams

SPEC = ContextSpec(
    ema_periods=(9,),
    sma_periods=(20,),
    atr_periods=(14,),
    needs_vwap=True,
    needs_time_of_day=True,
    regime_lookbacks=(20,),
    volume_keys=(volume.key(volume.VolumeForm.PER_BAR, volume.NO_ROLLING, 5),),
    trend_keys=(trend.key(9, 20, 5),),
    needs_ma_values=True,
)


def bars(n: int = 3000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
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


@pytest.fixture(scope="module")
def data() -> context.Dataset:
    return context.prepare(bars(), SPEC, keep_ma_values=True)


# -- the three the parent issue names -----------------------------------------


def test_the_ma_grid_gate_is_one_byte_and_its_values_are_eight(data: context.Dataset) -> None:
    """The 66 MB against 595 MB decision is this dtype difference and nothing else."""
    grid = data.grid("ema")
    assert grid.below.dtype == np.bool_
    assert grid.above.dtype == np.bool_
    assert grid.values is not None
    assert grid.values.dtype == np.float64
    assert grid.below.itemsize * 8 == grid.values.itemsize


def test_session_info_holds_dates_and_flags_as_different_things() -> None:
    info = sessions.classify(bars(200).index)
    assert info.trading_day.dtype == np.dtype("datetime64[D]")
    assert info.in_session.dtype == np.bool_
    assert info.is_session_open.dtype == np.bool_
    assert info.is_session_close.dtype == np.bool_


def test_the_leg_matrix_is_float64_so_codes_ride_in_it_as_floats(data: context.Dataset) -> None:
    """``exit_reason`` and ``direction`` are written as floats and mapped back later."""
    params = DeadCatParams(ema_period=9, use_slow_sma=False, use_fast_sma=False)
    legs = runner.deadcat_legs(data, params)
    assert legs.matrix.dtype == np.float64
    assert legs.matrix.ndim == 2


# -- the rest of the aliases --------------------------------------------------


def test_the_clock_keeps_its_three_widths(data: context.Dataset) -> None:
    assert data.phase_values().dtype == np.int8
    assert data.bar_of_session().dtype == np.int32
    tod = timeofday.classify(bars(200).index)
    assert tod.phase_bits.dtype == np.uint8


def test_every_label_kind_is_int8(data: context.Dataset) -> None:
    assert data.regime_labels(20, 0.3, 0.6).dtype == np.int8
    assert data.trend_labels(SPEC.trend_keys[0], 2).dtype == np.int8
    assert data.volume_labels(SPEC.volume_keys[0], 0.7, 1.3).dtype == np.int8
    assert data.trend_components(SPEC.trend_keys[0]).dtype == np.int8


def test_every_gate_is_bool(data: context.Dataset) -> None:
    assert data.ma_gate("ema", 9, above=True).dtype == np.bool_
    assert data.vwap_gate(above=False).dtype == np.bool_
    assert data.phase_gate(timeofday.ALL_PHASES).dtype == np.bool_
    assert data.regime_gate(20, regime.ALL_REGIMES, 0.3, 0.6).dtype == np.bool_
    assert data.trend_gate(SPEC.trend_keys[0], trend.ALL_TRENDS, 2).dtype == np.bool_
    assert data.volume_gate(SPEC.volume_keys[0], volume.ALL_STATES, 0.7, 1.3).dtype == np.bool_
    assert data.force_flat.dtype == np.bool_


def test_every_raw_series_is_float64(data: context.Dataset) -> None:
    for series in (data.open, data.high, data.low, data.close):
        assert series.dtype == np.float64
    assert data.ma_values("ema", 9).dtype == np.float64
    assert data.atr_values(14).dtype == np.float64
    assert data.vwap_values().dtype == np.float64
    assert data.regime_values(20).dtype == np.float64
    assert data.trend_values(SPEC.trend_keys[0]).dtype == np.float64
    assert data.volume_values(SPEC.volume_keys[0]).dtype == np.float64
    assert data.relative_volume(SPEC.volume_keys[0]).dtype == np.float64


def test_positions_into_an_array_are_intp_however_they_are_produced() -> None:
    """What ``OffsetArray`` claims: numpy picks this width, and it is not int64 everywhere."""
    values = np.array([3.0, 1.0, 2.0, 1.0])
    assert np.flatnonzero(values > 1.5).dtype == np.intp
    assert np.argsort(values, kind="stable").dtype == np.intp
    assert np.searchsorted(np.sort(values), values, side="left").dtype == np.intp


def test_day_codes_stay_narrow(data: context.Dataset) -> None:
    assert data.day_codes is not None
    assert data.day_codes.dtype == np.int32
