"""The paired A/B read: what a cell is, and what the comparison inside one is allowed to be.

Every function under test is pure, so none of this needs a database. What is worth pinning is
the arithmetic the conclusion rests on -- which columns key a cell, that the treatment is
collapsed to its median rather than its best, and that the sign test is exact.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tools.campaign_paired import CELL_KEYS, cells, paired, shared_columns, sign_test, under_test, verdict


def arm(variant: str, **columns: object) -> pd.DataFrame:
    """A results frame with the tag columns every stored row carries."""
    base = {
        "sweep_id": 1,
        "combo_id": range(4),
        "variant": variant,
        "stratum": "unfiltered",
        "window": "full",
        "strategy": "EmaCrossover",
        "resolution": 5,
        "contract": None,
        "tier2": "tier-1-only",
        "root": "MNQ",
        "profit_factor": [0.8, 0.9, 1.1, 1.2],
        "trades": [100, 200, 300, 400],
        "net_pnl": [-10.0, -5.0, 5.0, 10.0],
    }

    return pd.DataFrame({**base, **columns})


# -- what a cell is keyed on ---------------------------------------------------------------


def test_the_axis_under_test_is_not_part_of_the_cell_key() -> None:
    """Otherwise every cell would hold one row of each arm and nothing would pair."""
    control = arm("trail=off", fast_period=[9, 9, 20, 20], trail_ma_period=[50, 50, 50, 50])
    treatment = arm("trail=on", fast_period=[9, 9, 20, 20], trail_ma_period=[20, 50, 20, 50])
    assert "fast_period" in shared_columns(control, treatment)
    assert "trail_ma_period" not in shared_columns(control, treatment)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ({False}, {True}, True),
        ({50}, {20, 50, 100}, True),
        ({9, 20}, {9, 20}, False),
        ({9, 13, 20, 30}, {9, 13, 99}, False),
        ({0.0}, {5.0, 25.0}, True),
        ({2}, {2}, False),
    ],
    ids=["toggle", "held against swept", "identical", "one value lost", "disjoint", "both held"],
)
def test_which_value_sets_mean_the_column_is_the_rule_under_test(left, right, expected) -> None:
    """Set equality is not the test: ``MIN_TRADES`` can drop a value from one arm alone."""
    assert under_test(left, right) is expected


def test_a_column_only_one_arm_carries_is_not_shared() -> None:
    control = arm("round=off", fast_period=[9, 9, 20, 20])
    treatment = arm("round=on", fast_period=[9, 9, 20, 20]).drop(columns=["fast_period"])
    assert shared_columns(control, treatment) == []


def test_the_cell_key_carries_the_root_the_resolution_and_the_stratum() -> None:
    """A pair is only a pair within one of each -- pooling them compares different questions."""
    assert CELL_KEYS == ["root", "resolution", "stratum"]


# -- what the comparison inside a cell is --------------------------------------------------


def test_the_treatment_is_collapsed_to_its_median_not_its_best() -> None:
    """Taking the best in each cell is selection, and it is what this instrument exists to avoid."""
    frame = arm("trail=on", fast_period=[9, 9, 9, 9], profit_factor=[0.5, 0.9, 1.1, 9.0])
    one = cells(frame, ["root", "fast_period"], "profit_factor")
    assert one["median"].to_numpy() == pytest.approx([1.0])
    assert one["best"].to_numpy() == pytest.approx([9.0])
    assert one["rows"].to_numpy() == pytest.approx([4])


def test_a_cell_only_one_arm_reaches_is_dropped_rather_than_scored() -> None:
    """A rule that thins the sample loses cells; the pair count is what says so."""
    control = arm("trail=off", fast_period=[9, 13, 20, 30])
    treatment = arm("trail=on", fast_period=[9, 13, 99, 99])
    pairs = paired(control, treatment, "profit_factor")
    assert sorted(pairs["fast_period"]) == [9, 13]


def test_the_delta_is_the_treatment_minus_the_control() -> None:
    control = arm("trail=off", fast_period=[9, 13, 20, 30], profit_factor=[1.0, 1.0, 1.0, 1.0])
    treatment = arm("trail=on", fast_period=[9, 13, 20, 30], profit_factor=[1.5, 0.5, 1.0, 2.0])
    pairs = paired(control, treatment, "profit_factor").sort_values("fast_period")
    assert pairs["delta"].to_numpy() == pytest.approx([0.5, -0.5, 0.0, 1.0])


# -- the sign test -------------------------------------------------------------------------


@pytest.mark.parametrize("total", [1, 2, 5, 10, 21])
def test_the_sign_test_is_the_exact_two_sided_binomial(total) -> None:
    """Written out rather than imported, so it is pinned against the definition."""
    for improved in range(total + 1):
        tail = min(improved, total - improved)
        expected = min(1.0, 2.0 * sum(math.comb(total, k) for k in range(tail + 1)) / 2.0**total)
        assert sign_test(improved, total) == pytest.approx(expected)


def test_an_even_split_is_a_p_of_one_and_a_clean_sweep_is_the_smallest_reachable() -> None:
    assert sign_test(5, 10) == pytest.approx(1.0)
    assert sign_test(10, 10) == pytest.approx(2.0 / 2.0**10)
    assert sign_test(0, 10) == pytest.approx(2.0 / 2.0**10)


def test_no_pairs_is_undefined_rather_than_significant() -> None:
    assert math.isnan(sign_test(0, 0))


# -- the reported row ----------------------------------------------------------------------


def test_a_tie_counts_as_not_improved() -> None:
    """The conservative direction: a rule that changed nothing did not help."""
    control = arm("off", fast_period=[9, 13, 20, 30], profit_factor=[1.0, 1.0, 1.0, 1.0])
    treatment = arm("on", fast_period=[9, 13, 20, 30], profit_factor=[1.0, 1.0, 1.0, 2.0])
    row = verdict(paired(control, treatment, "profit_factor")).iloc[0]
    assert row["pairs"] == 4
    assert row["improved"] == 1
    assert row["share"] == pytest.approx(0.25)


def test_one_row_per_root_and_resolution() -> None:
    control = pd.concat(
        [
            arm("off", fast_period=[9, 13, 20, 30]),
            arm("off", fast_period=[9, 13, 20, 30], resolution=15),
        ],
    )
    treatment = pd.concat(
        [
            arm("on", fast_period=[9, 13, 20, 30], profit_factor=[1.0, 1.0, 1.0, 2.0]),
            arm("on", fast_period=[9, 13, 20, 30], resolution=15),
        ],
    )
    table = verdict(paired(control, treatment, "profit_factor"))
    assert sorted(table["resolution"]) == [5, 15]
    assert set(table["root"]) == {"MNQ"}
