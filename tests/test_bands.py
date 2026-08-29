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
