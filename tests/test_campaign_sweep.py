"""What the registry-wide campaign's plan claims, pinned.

The sweeps themselves are not exercised here -- they need ``cache/continuous`` and take about
an hour and a half. What is testable without data is the shape of the plan, which is where a
silent mistake would live: a stratum that filters two dimensions at once, a variant whose grid
cannot be built, a root whose commission is the other root's, or two archetypes pointed at one
database.
"""

from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, higher_timeframe, regime, sessionrange, timeofday, trades, trend, volume
from nqbt.sim.types import STOP_ATR, STOP_CATASTROPHE, STOP_SWING
from tools.campaign_sweep import (
    ALL_STRATA,
    COMMISSION,
    CONTEXT,
    CORE,
    ELASTIC_LADDERS,
    REGIME,
    REGIME_LOOKBACKS,
    REGIME_QUANTILES,
    RESOLUTIONS,
    SELECTION_SHARE,
    SLIPPAGE_TICKS,
    STRATUM_SETS,
    UNFILTERED,
    VARIANTS,
    Variant,
    calibrate,
    db_path,
    fit_regime,
    grids_for,
    orb_resolutions,
    planned_combinations,
    quantile_pair,
    strata,
    windows,
)

EVERY_STATE = {
    "regime": [f"regime={state.name}" for state in regime.Regime],
    "phase": [f"phase={phase.name}" for phase in timeofday.SessionPhase],
    "volume": [f"volume={state.name}" for state in volume.VolumeState],
    "trend": [f"trend={label.name}" for label in trend.Trend],
    "htf": [f"htf={side.name}" for side in higher_timeframe.Side],
}
"""Every stratum name each context dimension owes, so a dropped state fails rather than
quietly narrowing the campaign."""


def all_variants() -> list[Variant]:
    """Every variant of every archetype, on both roots."""
    return [variant for build in VARIANTS.values() for root in COMMISSION for variant in build(root)]


# -- the stratification --------------------------------------------------------------------


def test_every_state_of_every_dimension_gets_exactly_one_stratum() -> None:
    names = [name for name, _ in strata(ALL_STRATA)]
    assert names[0] == UNFILTERED
    assert names[1:] == [name for dimension in EVERY_STATE.values() for name in dimension]


def test_no_stratum_filters_two_dimensions_at_once() -> None:
    """One dimension at a time is the whole design; crossing them is 190 cells, not 20."""
    for _, extra in strata(ALL_STRATA):
        assert len(extra) <= 1


def test_each_filtered_stratum_admits_exactly_one_state() -> None:
    """A mask with two bits set would be a coarser stratum wearing a single state's name."""
    for name, extra in strata(ALL_STRATA):
        for values in extra.values():
            assert len(values) == 1, name
            assert int(values[0]).bit_count() == 1, name


def test_the_unfiltered_stratum_narrows_nothing() -> None:
    """It is the baseline every other row is read against, so it must sweep no filter."""
    assert dict(strata(ALL_STRATA))[UNFILTERED] == {}


def test_core_and_context_partition_the_whole_set() -> None:
    """The second pass appends the dimensions the first skipped; neither may repeat the other."""
    core = [name for name, _ in strata(CORE)]
    context = [name for name, _ in strata(CONTEXT)]
    assert set(core).isdisjoint(context)
    assert core + context == [name for name, _ in strata(ALL_STRATA)]


def test_every_dimension_is_selectable_on_its_own() -> None:
    """A held-out pass takes one dimension at a time, so each needs its own name -- a set that
    only reached a dimension through ``context`` could not be run without the other two."""
    for group, names in EVERY_STATE.items():
        assert [name for name, _ in strata(group)] == names, group
    assert [name for name, _ in strata(UNFILTERED)] == [UNFILTERED]


def test_every_named_set_is_built_from_the_shared_dimensions() -> None:
    """A set that named a dimension twice would double every combination inside it."""
    for which in STRATUM_SETS:
        names = [name for name, _ in strata(which)]
        assert len(names) == len(set(names)), which


# -- the variants --------------------------------------------------------------------------


def test_every_variant_carries_its_own_archetypes_parameter_class() -> None:
    for variant in all_variants():
        assert isinstance(variant.base, variant.archetype.params_cls)


def test_every_registered_archetype_is_swept() -> None:
    """A registry entry with no variant would be silently absent from the campaign."""
    assert set(VARIANTS) == set(archetypes.names())


def test_every_grid_in_the_campaign_can_be_built() -> None:
    """The real guard: ``Grid`` refuses dead axes and each parameter class refuses an
    impossible combination, so constructing every one of them is what catches a grid that
    would fail an hour into a run."""
    for variant in all_variants():
        for _, grid in grids_for(variant, ALL_STRATA):
            assert len(grid) == variant.sized()


def test_every_combination_of_every_grid_is_constructible() -> None:
    """``combinations()`` builds the parameter objects, so a validator that refuses a corner
    of the product -- identical crossover averages, both ElasticBand signal exits at once --
    fails here rather than mid-sweep."""
    for variant in all_variants():
        _, grid = grids_for(variant, UNFILTERED)[0]
        assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_every_base_carries_its_roots_real_costs() -> None:
    for name, build in VARIANTS.items():
        for root, commission in COMMISSION.items():
            for variant in build(root):
                assert variant.base.commission_per_contract == pytest.approx(commission), (name, root)
                assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS), (name, root)


def test_the_two_roots_are_not_costed_the_same() -> None:
    """One figure for both flatters NQ: the point value differs tenfold, the commission does not."""
    assert COMMISSION["NQ"] > COMMISSION["MNQ"]


def test_the_crossover_variants_sweep_disjoint_stop_axes() -> None:
    """``dead_axes`` cannot see that a swing stop ignores ``atr_stop_multiple``, so the two
    geometries are separate variants rather than one grid -- ``docs/roadmap.md`` §M27."""
    atr, swing = VARIANTS["EmaCrossover"]("MNQ")
    assert atr.base.use_atr_stop and not swing.base.use_atr_stop
    assert "atr_stop_multiple" in atr.axes and "atr_stop_multiple" not in swing.axes
    assert "swing_lookback" in swing.axes and "swing_lookback" not in atr.axes


def test_every_elastic_ladder_is_distinct_and_ends_in_a_runner() -> None:
    """A tuple is not a sweepable axis, so each ladder is its own variant; two that matched
    would run the same combinations twice under different names."""
    assert len(set(ELASTIC_LADDERS.values())) == len(ELASTIC_LADDERS)
    for name, levels in ELASTIC_LADDERS.items():
        assert math.isnan(levels[-1]), name


def test_the_elastic_variants_sweep_every_stop_mode_they_name() -> None:
    """The stop mode is the axis the exit scheme actually turns on."""
    for variant in VARIANTS["ElasticBand"]("MNQ"):
        assert variant.axes["stop_mode"] == [STOP_ATR, STOP_SWING, STOP_CATASTROPHE]


def test_every_resolution_divides_into_whole_bars_of_the_session() -> None:
    """A bar size that does not divide the session length would straddle the close."""
    for minutes in RESOLUTIONS:
        assert 1380 % minutes == 0


# -- windows and storage -------------------------------------------------------------------


def test_the_full_window_is_the_whole_series() -> None:
    bars = pd.DataFrame({"close": range(100)})
    assert [name for name, _ in windows(bars, split=False)] == ["full"]
    assert len(windows(bars, split=False)[0][1]) == len(bars)


def test_the_split_windows_cover_every_bar_exactly_once() -> None:
    """An overlap would leak the selection window into the test that is meant to be held out."""
    bars = pd.DataFrame({"close": range(1000)})
    (_, selection), (_, holdout) = windows(bars, split=True)
    assert len(selection) + len(holdout) == len(bars)
    assert selection.index.max() < holdout.index.min()
    assert len(selection) == math.floor(len(bars) * SELECTION_SHARE)


def test_each_archetype_gets_its_own_database(tmp_path, monkeypatch) -> None:
    """A convention since ``_append_or_create`` learned to widen, and still what the campaign
    ran on, so the report and holdout tools go on finding one file per archetype."""
    monkeypatch.setattr("tools.campaign_sweep.CAMPAIGN_DIR", tmp_path / "campaign")
    paths = {name: db_path(name) for name in VARIANTS}
    assert len(set(paths.values())) == len(VARIANTS)
    assert all(path.parent.exists() for path in paths.values())


def test_planned_combinations_multiplies_the_axes_out() -> None:
    args = argparse.Namespace(
        strategies=["InsideBar"],
        roots=["MNQ"],
        strata=UNFILTERED,
        resolutions=[5, 15],
        split=False,
        regime_quantiles=None,
        regime_lookbacks=list(REGIME_LOOKBACKS),
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    assert planned_combinations(args) == per_stratum * 2

    args.split = True
    assert planned_combinations(args) == per_stratum * 2 * 2


# -- the calibrated regime stratum ---------------------------------------------------------

FITTED = {5: (0.10, 0.70), 20: (0.05, 0.40)}
"""A calibration with two lookbacks, so a cell that ignored its own row would be visible."""


def calibration_bars(n: int = 4000, seed: int = 4) -> pd.DataFrame:
    """A one-minute frame whose held-out half is a straight line, which scores 1.0 everywhere.

    A fit that reached past the selection window would put the upper threshold at 1.0 and say so.
    """
    rng = np.random.default_rng(seed)
    close = 16000.0 + np.cumsum(rng.normal(0.0, 5.0, n))
    cut = math.floor(n * SELECTION_SHARE)
    close[cut:] = close[cut - 1] + np.arange(1, n - cut + 1, dtype=np.float64)

    return pd.DataFrame({"close": close})


def calibrated_args(**overrides: object) -> argparse.Namespace:
    """The arguments ``fit_regime`` reads, at one resolution so ``resample`` is a pass-through."""
    return argparse.Namespace(
        **{
            "resolutions": [1],
            "regime_quantiles": REGIME_QUANTILES,
            "regime_lookbacks": [20],
            **overrides,
        },
    )


def test_a_calibrated_regime_stratum_is_one_cell_per_lookback() -> None:
    """A cell rather than an axis: the thresholds move with the lookback, and a sweep crosses
    its axes, so pairing them any other way runs cells that are not comparable."""
    names = [name for name, _ in strata(REGIME, FITTED)]
    assert names == [f"regime={state.name}@n={n}" for state in regime.Regime for n in FITTED]


def test_a_calibrated_cell_carries_the_thresholds_fitted_at_its_own_lookback() -> None:
    for name, extra in strata(REGIME, FITTED):
        lookback = int(name.split("@n=")[1])
        consolidating, directional = FITTED[lookback]
        assert extra["regime_lookback"] == [lookback]
        assert extra["regime_consolidating_below"] == [consolidating]
        assert extra["regime_directional_above"] == [directional]


def test_a_calibration_changes_the_regime_dimension_and_no_other() -> None:
    """Every other stratum is one filter and stays one filter; only the cut is reparameterised."""
    others = [(name, extra) for name, extra in strata(ALL_STRATA) if not name.startswith("regime=")]
    calibrated = [
        (name, extra) for name, extra in strata(ALL_STRATA, FITTED) if not name.startswith("regime=")
    ]
    assert others == calibrated


def test_an_uncalibrated_run_keeps_the_stratum_names_the_stored_databases_carry() -> None:
    assert [name for name, _ in strata(ALL_STRATA, None)] == [name for name, _ in strata(ALL_STRATA)]


def test_every_calibrated_grid_in_the_campaign_can_be_built() -> None:
    """The fitted thresholds reach a real parameter class, which validates them on construction."""
    fitted = calibrate(calibration_bars(), [5, 20], REGIME_QUANTILES)
    for variant in all_variants():
        for _, grid in grids_for(variant, REGIME, fitted):
            assert len(grid) == variant.sized()


def test_the_fit_reads_the_selection_window_and_never_the_holdout() -> None:
    """Fitting on the whole series would leak the holdout into the definition of the stratum."""
    bars = calibration_bars()
    fitted = fit_regime(bars, calibrated_args())
    assert fitted[1][20][1] < 1.0
    assert calibrate(bars, [20], REGIME_QUANTILES)[20][1] == pytest.approx(1.0)


def test_no_fit_is_taken_when_the_thresholds_are_left_raw() -> None:
    assert fit_regime(calibration_bars(), calibrated_args(regime_quantiles=None)) == {}


def test_a_bare_quantile_flag_takes_the_pair_the_campaign_states() -> None:
    assert quantile_pair([]) == REGIME_QUANTILES
    assert quantile_pair([0.1, 0.9]) == (0.1, 0.9)
    assert quantile_pair(None) is None


def test_one_quantile_is_refused_rather_than_paired_with_a_default() -> None:
    with pytest.raises(SystemExit, match="consolidating and a directional"):
        quantile_pair([0.8])


def test_planned_combinations_counts_the_calibrated_cells() -> None:
    args = argparse.Namespace(
        strategies=["InsideBar"],
        roots=["MNQ"],
        strata=REGIME,
        resolutions=[5],
        split=False,
        regime_quantiles=REGIME_QUANTILES,
        regime_lookbacks=[5, 20],
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    assert planned_combinations(args) == per_stratum * len(regime.Regime) * 2


# -- the opening range, whose windows are not expressible at every resolution ---------------


def test_every_variant_but_the_opening_ranges_runs_at_every_resolution() -> None:
    """The exception is the point: a session-anchored range needs the bar size to divide both
    its 930-minute anchor and its window -- ``docs/roadmap.md`` §M28."""
    for variant in all_variants():
        expected = RESOLUTIONS if variant.archetype is not archetypes.OPENINGRANGE else variant.resolutions
        assert variant.resolutions == expected, variant.name
        assert all(variant.runs_at(minutes) for minutes in variant.resolutions)


def test_the_opening_ranges_windows_survive_exactly_the_resolutions_that_divide_them() -> None:
    assert orb_resolutions(5) == (1, 5)
    assert orb_resolutions(15) == (1, 5, 15)
    assert orb_resolutions(30) == RESOLUTIONS
    # 10-minute bars divide 930 but not a 5- or 15-minute window.
    assert 10 not in orb_resolutions(15)


def test_every_opening_range_variant_can_be_prepared_at_the_resolutions_it_claims() -> None:
    """The real guard: a claimed resolution whose range grid refuses to build would fail an
    hour into a run rather than here."""
    for variant in VARIANTS["OpeningRange"]("MNQ"):
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_planned_combinations_skips_a_resolution_a_variant_cannot_express() -> None:
    args = argparse.Namespace(
        strategies=["OpeningRange"],
        roots=["MNQ"],
        strata=UNFILTERED,
        resolutions=[10],
        split=False,
        regime_quantiles=None,
        regime_lookbacks=list(REGIME_LOOKBACKS),
    )
    variants = VARIANTS["OpeningRange"]("MNQ")
    only_thirty = sum(v.sized() for v in variants if v.runs_at(10))

    assert only_thirty < sum(v.sized() for v in variants), "premise gone; nothing is being skipped"
    assert planned_combinations(args) == only_thirty


def test_the_opening_range_sweeps_both_sides_as_separate_combinations() -> None:
    """A two-sided range is not expressible in NT8, so every combination is one-sided."""
    for variant in VARIANTS["OpeningRange"]("MNQ"):
        assert variant.axes["direction"] == [trades.LONG, trades.SHORT]
        for combination in grids_for(variant, UNFILTERED)[0][1].combinations():
            assert combination.direction in (trades.LONG, trades.SHORT)
