"""Band-grid tests: the three rows are exactly the pinned indicators, and the keys are strict."""

import numpy as np
import pytest

from nqbt import bands, indicators

CLOSE = np.array([100.0, 101.0, 99.0, 104.0, 98.0, 102.0, 103.0, 97.0], dtype=np.float64)


def test_the_grid_rows_are_the_pinned_indicators_and_nothing_else() -> None:
    grid = bands.band_grid(CLOSE, [4])
    assert grid.basis_for(4) == pytest.approx(indicators.nt8_sma(CLOSE, 4))
    assert grid.stddev_for(4) == pytest.approx(indicators.nt8_stddev(CLOSE, 4))
    assert grid.stretch_for(4) == pytest.approx(
        indicators.band_stretch(CLOSE, indicators.nt8_sma(CLOSE, 4), indicators.nt8_stddev(CLOSE, 4)),
    )


def test_a_price_is_recovered_from_a_stretch_level() -> None:
    # The whole reason stretch is the coordinate system: basis + level * stddev is a price,
    # so one grid serves every band multiple.
    grid = bands.band_grid(CLOSE, [4])
    basis, stddev, stretch = grid.basis_for(4), grid.stddev_for(4), grid.stretch_for(4)
    live = stddev > 0.0
    assert (basis + stretch * stddev)[live] == pytest.approx(CLOSE[live])


def test_periods_are_sorted_and_deduplicated() -> None:
    grid = bands.band_grid(CLOSE, [6, 4, 6, 4])
    assert grid.periods.tolist() == [4, 6]
    assert grid.basis.shape == (2, CLOSE.size)
    assert len(grid) == CLOSE.size


def test_a_period_the_grid_was_not_built_for_raises_and_says_what_it_holds() -> None:
    grid = bands.band_grid(CLOSE, [4])
    for read in (grid.basis_for, grid.stddev_for, grid.stretch_for):
        with pytest.raises(KeyError, match=r"not in this grid; built for \[4\]"):
            read(5)


def test_a_period_below_two_is_refused_because_its_band_has_no_width() -> None:
    with pytest.raises(bands.BandError, match="one-bar standard deviation is always zero"):
        bands.band_grid(CLOSE, [1])
    with pytest.raises(bands.BandError, match="one-bar standard deviation is always zero"):
        bands.validate_period(1)
    assert bands.validate_period(2) == 2


def test_no_periods_at_all_raises_rather_than_building_an_empty_grid() -> None:
    with pytest.raises(bands.BandError, match="no band periods supplied"):
        bands.band_grid(CLOSE, [])


def test_nbytes_counts_all_three_rows() -> None:
    grid = bands.band_grid(CLOSE, [4, 6])
    assert grid.nbytes == 3 * 2 * CLOSE.size * 8


def test_the_grid_reads_only_bars_up_to_and_including_each_one() -> None:
    rng = np.random.default_rng(3)
    close = 18000.0 + np.cumsum(rng.normal(0.0, 2.0, 400))
    full = bands.band_grid(close, [20])
    for cut in (60, 233, 399):
        prefix = bands.band_grid(close[:cut], [20])
        assert prefix.stretch_for(20) == pytest.approx(full.stretch_for(20)[:cut])
        assert prefix.basis_for(20) == pytest.approx(full.basis_for(20)[:cut])


# -- the VWAP band ----------------------------------------------------------------

HIGH = CLOSE + 1.0
LOW = CLOSE - 1.0
VOLUME = np.array([1.0, 2.0, 1.0, 3.0, 1.0, 1.0, 2.0, 1.0], dtype=np.float64)
DAYS = np.array(
    ["2024-03-07"] * 4 + ["2024-03-08"] * 4,
    dtype="datetime64[D]",
)


def test_the_vwap_bands_three_series_are_the_pinned_indicators_and_nothing_else() -> None:
    band = bands.vwap_band(HIGH, LOW, CLOSE, VOLUME, DAYS)
    typical = indicators.typical_price(HIGH, LOW, CLOSE)
    flags = indicators.new_session_flags(DAYS)
    basis = indicators.session_vwap(typical, VOLUME, flags)
    assert band.basis == pytest.approx(basis)
    assert band.stddev == pytest.approx(indicators.session_vwap_dispersion(typical, VOLUME, basis, flags))
    assert band.stretch == pytest.approx(indicators.band_stretch(CLOSE, basis, band.stddev))


def test_the_vwap_bands_basis_is_the_dataset_vwap_rather_than_a_second_estimate() -> None:
    # The band's midline has to be the number every other reader of the VWAP sees, or a
    # trade's target and its context row disagree about where the mean was.
    band = bands.vwap_band(HIGH, LOW, CLOSE, VOLUME, DAYS)
    typical = indicators.typical_price(HIGH, LOW, CLOSE)
    reported = indicators.session_vwap(typical, VOLUME, indicators.new_session_flags(DAYS))
    assert band.basis.tolist() == reported.tolist()


def test_a_price_is_recovered_from_a_vwap_stretch_level() -> None:
    band = bands.vwap_band(HIGH, LOW, CLOSE, VOLUME, DAYS)
    live = band.stddev > 0.0
    assert (band.basis + band.stretch * band.stddev)[live] == pytest.approx(CLOSE[live])


def test_the_vwap_band_reanchors_at_each_session_and_carries_its_own_clock() -> None:
    band = bands.vwap_band(HIGH, LOW, CLOSE, VOLUME, DAYS)
    assert band.bars_since_anchor.tolist() == [0, 1, 2, 3, 0, 1, 2, 3]
    # An anchor bar has one observation, so it has no width and can never be outside itself.
    assert band.stddev[0] == 0.0
    assert band.stddev[4] == 0.0
    assert band.stretch[0] == 0.0
    assert band.stretch[4] == 0.0


def test_the_vwap_band_has_no_period_axis_so_it_is_one_row_per_series() -> None:
    band = bands.vwap_band(HIGH, LOW, CLOSE, VOLUME, DAYS)
    assert len(band) == CLOSE.size
    assert band.nbytes == 3 * CLOSE.size * 8 + CLOSE.size * 8
