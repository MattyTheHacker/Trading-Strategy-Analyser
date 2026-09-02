"""The campaign's read side: what a stored row means once it comes back out.

Every function here is pure, so none of it needs a database. What is worth pinning is the
arithmetic a conclusion rests on -- which columns count as swept axes, what share of variance
an axis explains, and whether a stored row rebuilds into the parameters it came from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, stats
from tools.campaign_holdout import GROUP_KEYS, JOIN_KEYS, TOP, rank_correlation, verdict
from tools.campaign_report import STATISTICS, TAGS, axis_influence, eta_squared, profile, swept_axes
from tools.campaign_shortlist import rebuild


def combos(**columns: object) -> pd.DataFrame:
    """A results frame with the tag columns every stored row carries."""
    base = {
        "sweep_id": 1,
        "combo_id": range(4),
        "variant": "bracket",
        "stratum": "unfiltered",
        "window": "full",
        "strategy": "InsideBar",
        "resolution": 5,
        "contract": None,
        "tier2": "reconciled",
        "root": "MNQ",
        "profit_factor": [0.8, 0.9, 1.1, 1.2],
        "trades": [100, 200, 300, 400],
        "net_pnl": [-10.0, -5.0, 5.0, 10.0],
    }

    return pd.DataFrame({**base, **columns})


# -- what counts as an axis ----------------------------------------------------------------


def test_the_summary_columns_are_read_from_the_class_not_copied() -> None:
    """A statistic added to ``Summary`` would otherwise be reported as a swept parameter."""
    assert STATISTICS == frozenset(stats.Summary.columns())


def test_a_constant_parameter_is_not_reported_as_an_axis() -> None:
    frame = combos(ema_period=[22, 22, 22, 22], atr_length=[3, 3, 14, 14])
    assert swept_axes(frame) == ["atr_length"]


def test_tags_and_statistics_are_never_axes() -> None:
    """``combo_id`` varies on every row and ``profit_factor`` is the thing being explained."""
    frame = combos(ema_period=[11, 22, 33, 44])
    assert set(swept_axes(frame)).isdisjoint(TAGS | STATISTICS)


def test_the_cost_fields_are_tags_rather_than_axes() -> None:
    """They vary with the root and nothing else, so reporting them would report the root
    twice under a name that hides it."""
    assert {"commission_per_contract", "slippage_ticks"} <= TAGS


# -- how much an axis explains -------------------------------------------------------------


def test_an_axis_that_separates_the_groups_completely_explains_everything() -> None:
    frame = combos(gate=["a", "a", "b", "b"], profit_factor=[1.0, 1.0, 2.0, 2.0])
    assert eta_squared(frame, "gate") == pytest.approx(1.0)


def test_an_axis_whose_groups_share_a_mean_explains_nothing() -> None:
    """Variance the axis does not move belongs to the residual, however wide it is."""
    frame = combos(gate=["a", "b", "a", "b"], profit_factor=[1.0, 2.0, 2.0, 1.0])
    assert eta_squared(frame, "gate") == pytest.approx(0.0)


def test_a_statistic_with_no_variance_explains_nothing_rather_than_dividing_by_zero() -> None:
    frame = combos(gate=["a", "a", "b", "b"], profit_factor=[1.0, 1.0, 1.0, 1.0])
    assert eta_squared(frame, "gate") == 0.0


def test_axis_influence_is_sorted_largest_first() -> None:
    frame = combos(
        strong=["a", "a", "b", "b"],
        weak=["x", "y", "x", "y"],
        profit_factor=[1.0, 1.1, 2.0, 2.1],
    )
    ranked = axis_influence(frame, ["weak", "strong"])
    assert list(ranked["axis"]) == ["strong", "weak"]
    assert ranked["eta2"].is_monotonic_decreasing


# -- the distribution tables ---------------------------------------------------------------


def test_profile_reports_the_profitable_share_not_the_best_row() -> None:
    """The headline claim of the whole report: distributions, not winners."""
    row = profile(combos(), ["root"]).iloc[0]
    assert row["combos"] == 4
    assert row["profitable_%"] == pytest.approx(50.0)
    assert row["pf_median"] == pytest.approx(1.0)
    assert row["pf_best"] == pytest.approx(1.2)


def test_profile_groups_by_every_column_it_is_given() -> None:
    frame = combos(resolution=[5, 5, 15, 15])
    assert len(profile(frame, ["root", "resolution"])) == 2


# -- the held-out test ---------------------------------------------------------------------


def test_rank_correlation_is_one_for_an_order_that_survives_and_minus_one_for_a_reversal() -> None:
    """Spearman without scipy, which is not a dependency and must not become one."""
    order = pd.DataFrame({"profit_factor_sel": [1.0, 2.0, 3.0], "profit_factor_hold": [4.0, 5.0, 9.0]})
    reversed_order = pd.DataFrame(
        {"profit_factor_sel": [1.0, 2.0, 3.0], "profit_factor_hold": [9.0, 5.0, 4.0]},
    )
    assert rank_correlation(order) == pytest.approx(1.0)
    assert rank_correlation(reversed_order) == pytest.approx(-1.0)


def paired_rows(stratum: str, holdout: np.ndarray, size: int = TOP + 10) -> pd.DataFrame:
    """One stratum's paired window, ranked so the shortlist is the last ``TOP`` rows."""
    return pd.DataFrame(
        {
            "root": "MNQ",
            "stratum": stratum,
            "profit_factor_sel": np.arange(size, dtype=float),
            "profit_factor_hold": holdout,
            "net_pnl_hold": np.zeros(size),
        },
    )


def test_the_verdict_compares_the_shortlist_against_not_shortlisting() -> None:
    """The benchmark is the holdout median of every configuration, not zero."""
    size = TOP + 10
    row = verdict("InsideBar", paired_rows("unfiltered", np.linspace(0.4, 0.6, size))).iloc[0]
    assert row["paired"] == size
    assert row["hold_all_median_pf"] == pytest.approx(0.5)
    assert row["hold_top20_pf"] < 1.0
    assert row["top20_profitable"] == 0
    assert not row["passes"]


def test_a_shortlist_that_beats_1_but_not_the_unselected_median_does_not_pass() -> None:
    """Gate 2 is two conditions and the second is the one a profit factor alone hides:
    selecting can be profitable and still be worse than not selecting at all."""
    size = 5 * TOP
    holdout = np.full(size, 3.0)
    holdout[-TOP:] = 1.5
    row = verdict("InsideBar", paired_rows("unfiltered", holdout, size)).iloc[0]
    assert row["hold_top20_pf"] == pytest.approx(1.5)
    assert row["hold_all_median_pf"] == pytest.approx(3.0)
    assert row["top20_profitable"] == TOP
    assert not row["passes"]


def test_a_stratum_is_shortlisted_within_itself_and_never_pooled() -> None:
    """The hazard §M27.4 exists to avoid: pooling lets the twenty largest selection-window
    profit factors come from the fattest-tailed stratum, so a weak stratum inherits a
    shortlist it never produced and reads as having been tested."""
    size = TOP + 10
    unselected = np.full(size - TOP, 1.0)
    fat = paired_rows("regime=DIRECTIONAL", np.r_[unselected, np.full(TOP, 2.0)])
    fat["profit_factor_sel"] += 1000.0
    thin = paired_rows("regime=CONSOLIDATING", np.r_[unselected, np.full(TOP, 0.5)])

    rows = verdict("InsideBar", pd.concat([fat, thin], ignore_index=True)).set_index("stratum")
    assert len(rows) == 2
    assert rows.loc["regime=DIRECTIONAL", "hold_top20_pf"] == pytest.approx(2.0)
    assert rows.loc["regime=CONSOLIDATING", "hold_top20_pf"] == pytest.approx(0.5)
    assert rows.loc["regime=CONSOLIDATING", "paired"] == size


def test_a_shortlist_is_chosen_within_one_root_and_one_stratum() -> None:
    """Both are choices the selection window would otherwise get to make for free."""
    assert GROUP_KEYS == ["root", "stratum"]


def test_the_windows_are_paired_on_a_key_that_identifies_one_configuration() -> None:
    """``combo_id`` is a position in a deterministic product, so it only means the same
    parameters within the same grid, root and resolution."""
    assert JOIN_KEYS == ["root", "resolution", "variant", "stratum", "combo_id"]


# -- rebuilding a stored row ---------------------------------------------------------------


def test_a_stored_row_rebuilds_into_the_parameters_it_came_from() -> None:
    """What the null test is actually run on, so a coerced type here is a different strategy."""
    params = archetypes.INSIDEBAR.params_cls(ema_period=33, atr_length=7, atr_multiplier=12.5)
    row = pd.Series({**params.as_dict(), "variant": "bracket"})
    assert rebuild(row, archetypes.INSIDEBAR) == params


def test_rebuilding_restores_the_elastic_ladder_the_variant_names() -> None:
    """``target_stretch_levels`` is not sweepable, so it is popped from every stored row and
    only the variant name says which ladder ran."""
    row = pd.Series({**archetypes.ELASTICBAND.params_cls().as_dict(), "variant": "target=+2.0s"})
    del row["target_stretch_levels"]
    rebuilt = rebuild(row, archetypes.ELASTICBAND)
    assert rebuilt.target_stretch_levels[0] == pytest.approx(2.0)


def test_rebuilding_keeps_the_default_for_a_column_the_row_does_not_carry() -> None:
    row = pd.Series({"ema_period": 44, "variant": "bracket"})
    rebuilt = rebuild(row, archetypes.INSIDEBAR)
    assert rebuilt.ema_period == 44
    assert rebuilt.atr_length == archetypes.INSIDEBAR.params_cls().atr_length
