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
from tools.campaign_report import (
    NET_TO_DRAWDOWN,
    STATISTICS,
    TAGS,
    axis_influence,
    eta_squared,
    net_to_drawdown,
    parameter_columns,
    rank,
    ratio_to_drawdown,
    profile,
    swept_axes,
)
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
            "net_to_drawdown_sel": np.arange(size, dtype=float),
            "net_to_drawdown_hold": holdout,
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


# -- net-to-drawdown, the ranking Gate 4 is actually about ----------------------------------


def test_net_to_drawdown_divides_the_profit_by_the_worst_peak_to_trough() -> None:
    frame = combos(net_pnl=[100.0, -100.0, 50.0, 0.0], max_drawdown=[50.0, 25.0, 200.0, 10.0])
    assert list(net_to_drawdown(frame)) == pytest.approx([2.0, -4.0, 0.25, 0.0])


def test_a_row_with_no_drawdown_is_undefined_rather_than_infinite() -> None:
    """The defect §M27.5's tally records against profit factor, one statistic along: an
    unbounded value wins a ranking it was never measured on."""
    frame = combos(net_pnl=[100.0, 1.0, 1.0, 1.0], max_drawdown=[0.0, 10.0, 10.0, 10.0])
    assert np.isnan(net_to_drawdown(frame).iloc[0])
    assert not np.isinf(net_to_drawdown(frame)).any()


def test_nlargest_pads_with_undefined_rows_which_is_why_rank_exists() -> None:
    """The premise of :func:`rank`, pinned because it is the opposite of what it looks like:
    a shortlist drawn straight through ``nlargest`` carries rows it could not measure."""
    frame = combos(net_pnl=[100.0, 1.0, 1.0, 1.0], max_drawdown=[0.0, 10.0, 10.0, 10.0])
    frame["ntd"] = net_to_drawdown(frame)

    assert len(frame.nlargest(4, "ntd")) == 4, "premise gone; nlargest now drops them itself"
    assert frame.nlargest(4, "ntd")["ntd"].isna().any()
    assert len(rank(frame, 4, "ntd")) == 3
    assert not rank(frame, 4, "ntd")["ntd"].isna().any()


def test_rank_returns_the_largest_rows_in_order() -> None:
    frame = combos(net_pnl=[10.0, 40.0, 20.0, 30.0], max_drawdown=[10.0] * 4)
    frame["ntd"] = net_to_drawdown(frame)
    assert list(rank(frame, 2, "ntd")["net_pnl"]) == [40.0, 30.0]


def test_the_scalar_and_the_vectorised_guard_agree_exactly() -> None:
    """Two implementations of one rule, so the faster route is pinned to the slower one rather
    than re-derived -- the shape ``guard.separate`` and ``review.rank_conditions`` use."""
    frame = combos(net_pnl=[100.0, -50.0, 7.0, 0.0], max_drawdown=[50.0, 25.0, 0.0, 10.0])
    scalar = [ratio_to_drawdown(net, dd) for net, dd in zip(frame["net_pnl"], frame["max_drawdown"])]
    assert net_to_drawdown(frame).to_numpy() == pytest.approx(scalar, nan_ok=True)


def test_a_negative_drawdown_is_undefined_too() -> None:
    """``_max_drawdown`` cannot return one, so this pins the guard rather than the producer."""
    frame = combos(net_pnl=[10.0] * 4, max_drawdown=[-1.0, 1.0, 1.0, 1.0])
    assert np.isnan(net_to_drawdown(frame).iloc[0])


def test_a_derived_statistic_is_never_reported_as_a_swept_axis() -> None:
    """It varies on every row and is not a parameter, so the predicate has to know it by name."""
    frame = combos(ema_period=[11, 22, 33, 44], net_to_drawdown=[1.0, 2.0, 3.0, 4.0])
    assert swept_axes(frame) == ["ema_period"]
    assert NET_TO_DRAWDOWN not in parameter_columns(frame)


def test_the_two_predicates_agree_on_what_a_parameter_is() -> None:
    """``swept_axes`` is ``parameter_columns`` plus a variance filter and nothing else, which is
    what stops the holdout's parameter check and the report's axis table from drifting apart."""
    frame = combos(ema_period=[11, 22, 33, 44], atr_length=[3, 3, 3, 3])
    assert set(swept_axes(frame)) <= set(parameter_columns(frame))
    assert "atr_length" in parameter_columns(frame)


# -- the holdout ranks on whichever statistic it is given -----------------------------------


def test_the_holdout_can_shortlist_on_net_to_drawdown_instead_of_profit_factor() -> None:
    """§M27.3's instruction: the two disagree on this dataset, so the tool has to be able to
    take the other one."""
    size = 2 * TOP
    rows = paired_rows("unfiltered", np.linspace(0.9, 1.1, size), size)
    # The two rankings pick disjoint halves: profit factor ascends, net-to-drawdown descends.
    rows["profit_factor_sel"] = np.arange(size, dtype=float)
    rows["net_to_drawdown_sel"] = np.arange(size, dtype=float)[::-1]
    rows["net_to_drawdown_hold"] = np.r_[np.full(TOP, 5.0), np.full(TOP, 0.1)]

    by_drawdown = verdict("InsideBar", rows, NET_TO_DRAWDOWN).iloc[0]
    by_profit_factor = verdict("InsideBar", rows).iloc[0]

    assert by_drawdown["hold_top20_ntd"] == pytest.approx(5.0)
    assert by_drawdown["clears_drawdown"]
    assert by_profit_factor["hold_top20_ntd"] == pytest.approx(0.1)
    assert not by_profit_factor["clears_drawdown"]


def test_the_shortlisted_count_is_reported_because_an_undefined_ranking_drops_rows() -> None:
    """A cell whose rows mostly had no drawdown would otherwise report a twenty that was five."""
    size = TOP + 10
    measurable = 6
    rows = paired_rows("unfiltered", np.linspace(0.9, 1.1, size), size)
    rows["net_to_drawdown_sel"] = np.nan
    rows.loc[: measurable - 1, "net_to_drawdown_sel"] = 1.0

    row = verdict("InsideBar", rows, NET_TO_DRAWDOWN).iloc[0]
    assert row["paired"] == size
    assert row["shortlisted"] == measurable


def test_a_variant_can_be_held_out_on_its_own() -> None:
    """A narrow re-sweep lands in the same database as the campaign it follows, so a shortlist
    drawn without ``--variant`` would pool two grids inside one stratum -- §M27.3."""
    frame = combos(variant=["bracket", "bracket", "narrow", "narrow"], window="selection")
    assert list(frame[frame["variant"] == "narrow"]["combo_id"]) == [2, 3]
    assert "variant" not in parameter_columns(frame), "variant is a tag, not an axis"
