"""Condition tests, held to DeadCatBounce.cs semantics including its boundary cases."""

import numpy as np
import pandas as pd
import pytest

from nqbt import conditions


def bars(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float)


# -- inverted hammer ----------------------------------------------------------


@pytest.mark.parametrize(
    "row,expected,why",
    [
        ((10.0, 13.0, 10.0, 10.5), True, "upper 2.5 >= 2x body 0.5, no lower wick"),
        ((10.0, 11.0, 10.0, 10.5), False, "upper 0.5 < 2x body 0.5"),
        ((10.0, 13.0, 8.0, 10.5), False, "lower wick 2.0 exceeds body 0.5"),
        ((10.0, 13.0, 10.0, 10.0), False, "doji: body is zero so it cannot qualify"),
        ((10.5, 13.0, 10.0, 10.0), True, "red bar with a long upper wick still counts"),
        ((10.0, 12.0, 9.5, 10.5), True, "upper 1.5 >= 1.0, lower 0.5 <= body 0.5"),
    ],
)
def test_inverted_hammer(row, expected, why) -> None:
    assert conditions.inverted_hammer(bars([row]))[0] == expected, why


def test_inverted_hammer_boundary_is_inclusive_on_both_tests() -> None:
    # upper == 2x body and lower == body: DeadCatBounce.cs uses >= and <=, so this passes.
    frame = bars([(10.0, 11.0, 9.5, 10.5)])  # body 0.5, upper 0.5... not yet 2x
    assert not conditions.inverted_hammer(frame)[0]
    frame = bars([(10.0, 11.5, 9.5, 10.5)])  # body 0.5, upper 1.0 == 2x, lower 0.5 == body
    assert conditions.inverted_hammer(frame)[0]


# -- hammer (PullBackAndGo.cs's mirror) ----------------------------------------


@pytest.mark.parametrize(
    "row,expected,why",
    [
        ((10.5, 11.0, 8.0, 10.0), True, "lower 2.0 >= 2x body 0.5, no upper wick"),
        ((10.5, 11.0, 10.0, 10.0), False, "lower 0.5 < 2x body 0.5"),
        ((10.5, 13.0, 8.0, 10.0), False, "upper wick 2.5 exceeds body 0.5"),
        ((10.0, 13.0, 10.0, 10.0), False, "doji: body is zero so it cannot qualify"),
        ((10.0, 11.0, 8.0, 10.5), True, "green bar with a long lower wick still counts"),
    ],
)
def test_hammer(row, expected, why) -> None:
    assert conditions.hammer(bars([row]))[0] == expected, why


def test_hammer_is_inverted_hammers_wick_roles_swapped() -> None:
    # Same rows, opposite geometry: a bar that qualifies as one should not also qualify
    # as the other except in the degenerate doji case (neither qualifies).
    for row in [(10.0, 13.0, 10.0, 10.5), (10.5, 11.0, 8.0, 10.0), (10, 11, 9, 10)]:
        frame = bars([row])
        assert not (conditions.inverted_hammer(frame)[0] and conditions.hammer(frame)[0])


# -- new high/low, previous green/red ------------------------------------------


def test_made_new_high_requires_a_strictly_higher_high() -> None:
    frame = bars([(1, 10, 1, 5), (1, 11, 1, 5), (1, 11, 1, 5), (1, 10, 1, 5)])
    assert list(conditions.made_new_high(frame)) == [False, True, False, False]


def test_made_new_low_requires_a_strictly_lower_low() -> None:
    frame = bars([(1, 10, 5, 5), (1, 10, 4, 5), (1, 10, 4, 5), (1, 10, 5, 5)])
    assert list(conditions.made_new_low(frame)) == [False, True, False, False]


def test_previous_bar_green_treats_a_flat_close_as_green() -> None:
    # DeadCatBounce.cs rejects only on Close[1] < Open[1], so equality passes.
    flat = bars([(10, 11, 9, 10), (1, 2, 0, 1)])
    assert conditions.previous_bar_green(flat)[1]

    red = bars([(10, 11, 9, 9), (1, 2, 0, 1)])
    assert not conditions.previous_bar_green(red)[1]

    green = bars([(10, 11, 9, 11), (1, 2, 0, 1)])
    assert conditions.previous_bar_green(green)[1]


def test_previous_bar_red_rejects_a_flat_close() -> None:
    # PullBackAndGo.cs rejects on Close[1] >= Open[1], so a doji is not red. This is the
    # one boundary the two strategies do not mirror: previous_bar_green admits a doji and
    # this rejects one, making the pair exact complements rather than overlapping at
    # equality. The C# used to read Close[1] > Open[1]; the strictening cost 13.6% of
    # signals on MNQ 03-24, so the operator is worth reading rather than assuming.
    flat = bars([(10, 11, 9, 10), (1, 2, 0, 1)])
    assert not conditions.previous_bar_red(flat)[1]
    assert conditions.previous_bar_green(flat)[1]

    red = bars([(10, 11, 9, 9), (1, 2, 0, 1)])
    assert conditions.previous_bar_red(red)[1]

    green = bars([(10, 11, 9, 11), (1, 2, 0, 1)])
    assert not conditions.previous_bar_red(green)[1]


def test_first_bar_can_never_satisfy_a_lookback_condition() -> None:
    frame = bars([(1, 10, 1, 5)])
    assert not conditions.made_new_high(frame)[0]
    assert not conditions.made_new_low(frame)[0]
    assert not conditions.previous_bar_green(frame)[0]
    assert not conditions.previous_bar_red(frame)[0]


# -- trend gate ---------------------------------------------------------------


def test_below_series_passes_on_equality() -> None:
    # The C# rejects when Close > ma, so Close == ma must pass the filter.
    close = np.array([9.0, 10.0, 11.0])
    ma = np.array([10.0, 10.0, 10.0])
    assert list(conditions.below_series(close, ma)) == [True, True, False]


def test_above_series_passes_on_equality() -> None:
    # PullBackAndGo.cs rejects on Close < ma, so Close == ma passes here too -- the two
    # gates are not negations of one another, they overlap exactly at close == ma.
    close = np.array([9.0, 10.0, 11.0])
    ma = np.array([10.0, 10.0, 10.0])
    assert list(conditions.above_series(close, ma)) == [False, True, True]
    below = conditions.below_series(close, ma)
    above = conditions.above_series(close, ma)
    assert (below & above)[1], "close == ma must satisfy both gates independently"


# -- moving average grid ------------------------------------------------------


def test_grid_deduplicates_and_sorts_periods() -> None:
    close = np.arange(50, dtype=np.float64)
    grid = conditions.moving_average_grid(close, [21, 5, 21, 60], kind="ema")
    assert list(grid.periods) == [5, 21, 60]
    assert grid.below.shape == (3, 50)


def test_grid_drops_raw_values_unless_asked() -> None:
    close = np.arange(50, dtype=np.float64)
    lean = conditions.moving_average_grid(close, [21, 60])
    assert lean.values is None
    with pytest.raises(ValueError, match="keep_values=True"):
        lean.values_for(21)

    full = conditions.moving_average_grid(close, [21, 60], keep_values=True)
    assert full.values.shape == (2, 50)
    # Eight bytes per element versus one is the whole point -- compare like-shaped arrays
    # directly rather than the grid totals, which also carry the below+above bool pair
    # regardless of keep_values and would dilute the ratio.
    assert full.values.nbytes == full.below.nbytes * 8
    assert full.nbytes > lean.nbytes


def test_grid_row_lookup_is_by_period_not_position() -> None:
    close = np.arange(50, dtype=np.float64)
    grid = conditions.moving_average_grid(close, [60, 21, 5], keep_values=True)
    assert grid.row(5) == 0
    assert grid.row(60) == 2
    # Indexing the matrix with the period itself would silently return another series.
    assert grid.values_for(21) is not grid.values[21 % 3]


def test_grid_rejects_a_period_it_was_not_built_for() -> None:
    grid = conditions.moving_average_grid(np.arange(50, dtype=np.float64), [21])
    with pytest.raises(KeyError, match="not in this grid"):
        grid.row(22)


def test_grid_rows_match_the_standalone_indicator() -> None:
    from nqbt import indicators

    close = np.random.default_rng(2).normal(20000, 40, 500)
    grid = conditions.moving_average_grid(close, [21, 175], kind="sma", keep_values=True)
    assert grid.values_for(175) == pytest.approx(indicators.nt8_sma(close, 175))
    assert list(grid.below_for(21)) == list(conditions.below_series(close, indicators.nt8_sma(close, 21)))


def test_grid_carries_above_alongside_below() -> None:
    close = np.array([9.0, 10.0, 11.0, 12.0], dtype=np.float64)
    grid = conditions.moving_average_grid(close, [1], kind="sma")
    # SMA(1) == close, so below and above must both read the equality boundary as passing.
    assert list(grid.below_for(1)) == list(conditions.below_series(close, close))
    assert list(grid.above_for(1)) == list(conditions.above_series(close, close))
    assert all(grid.below_for(1)) and all(grid.above_for(1))


def test_grid_supports_both_kinds() -> None:
    close = np.arange(50, dtype=np.float64)
    ema = conditions.moving_average_grid(close, [10], kind="ema", keep_values=True)
    sma = conditions.moving_average_grid(close, [10], kind="sma", keep_values=True)
    assert ema.values_for(10)[-1] != pytest.approx(sma.values_for(10)[-1])


def test_grid_rejects_bad_input() -> None:
    close = np.arange(50, dtype=np.float64)
    with pytest.raises(ValueError, match="no periods"):
        conditions.moving_average_grid(close, [])
    with pytest.raises(ValueError, match=">= 1"):
        conditions.moving_average_grid(close, [0, 21])
    with pytest.raises(ValueError, match="unknown moving average"):
        conditions.moving_average_grid(close, [21], kind="wma")


# -- confluence ---------------------------------------------------------------


def test_count_true_backs_the_confluence_pattern() -> None:
    stack = np.array(
        [
            [True, True, False, False],
            [True, False, True, False],
            [True, True, True, False],
        ]
    )
    assert list(conditions.count_true(stack)) == [3, 2, 2, 0]
    # "at least 2 of 3" becomes a comparison rather than a hardcoded conjunction.
    assert list(conditions.count_true(stack) >= 2) == [True, True, True, False]


def test_bar_geometry_bundles_the_parameter_free_conditions() -> None:
    frame = bars([(10, 13, 10, 10.5), (10, 14, 10, 10.5)])
    geom = conditions.bar_geometry(frame)
    assert len(geom) == 2
    assert list(geom.inverted_hammer) == [True, True]
    assert list(geom.made_new_high) == [False, True]
    assert list(geom.previous_bar_green) == [False, True]


def test_bar_geometry_bundles_the_long_side_mirror_conditions() -> None:
    frame = bars([(10.5, 11, 8, 10), (10.5, 11, 7, 10)])
    geom = conditions.bar_geometry(frame)
    assert list(geom.hammer) == [True, True]
    assert list(geom.made_new_low) == [False, True]
    assert list(geom.previous_bar_red) == [False, True]
