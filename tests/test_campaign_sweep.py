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
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import (
    archetypes,
    compression,
    higher_timeframe,
    regime,
    sessionrange,
    sessions,
    timeofday,
    trades,
    trend,
    volume,
)
from nqbt.sim.types import (
    BAND_VWAP,
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_REJECTION,
    ORB_ENTRY_RETEST,
    ORB_SCALE_NONE,
    ORB_STOP_FRACTION,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    SHAPE_ANY,
    SHAPE_REVERSAL,
    STOP_ATR,
    STOP_BAND,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_STRETCH,
    TRIGGER_EXTENDED,
    TRIGGER_RECOVERY,
    DeadCatParams,
    OpeningRangeParams,
)
from tools.campaign_sweep import (
    ALL_STRATA,
    CAMPAIGN,
    COMMISSION,
    CONTEXT,
    CORE,
    CONSOLIDATING,
    DIRECTIONAL,
    ELASTIC_BAND_STOP,
    ELASTIC_BAND_STOP_ARMS,
    ELASTIC_BAND_STOP_SHAPES,
    ELASTIC_BAND_STOP_TARGET,
    ELASTIC_BAND_STOP_VARIANTS,
    ELASTIC_LADDERS,
    ELASTIC_RECOVERY,
    ELASTIC_RECOVERY_ARMS,
    ELASTIC_RECOVERY_TARGET,
    ELASTIC_RECOVERY_VARIANTS,
    ELASTIC_SHAPE_VARIANTS,
    ELASTIC_VOLUME,
    ELASTIC_VOLUME_SHAPES,
    ELASTIC_VOLUME_TARGET,
    ELASTIC_VOLUME_VARIANTS,
    NARROW,
    NARROW_ATR,
    NARROW_ENTRY,
    NARROW_TP,
    NARROW_VARIANTS,
    NO_CUTS,
    ORB,
    ORB_BRACKET,
    ORB_BRACKET_RANGES,
    ORB_BRACKET_VARIANTS,
    ORB_ENTRIES,
    ORB_FADE,
    ORB_FADE_LADDERS,
    ORB_FADE_VARIANTS,
    ORB_FRACTIONS,
    ORB_GEOMETRY,
    ORB_GEOMETRY_ENTRIES,
    ORB_FOLLOW_THROUGH,
    ORB_FOLLOW_THROUGH_RANGES,
    ORB_FOLLOW_THROUGH_VARIANTS,
    ORB_GEOMETRY_VARIANTS,
    ORB_GEOMETRY_WINDOWS,
    ORB_LADDER_FRACTIONS,
    ORB_RANGES,
    ORB_REJECTION,
    ORB_REJECTION_OFFSETS,
    ORB_REJECTION_VARIANTS,
    ORB_TARGETS,
    ORB_TIGHT_FRACTIONS,
    ORB_VARIANTS,
    ORB_WIDTH_LADDERS,
    LONDON_OPEN_MINUTES,
    RECUTS,
    REGIME,
    REGIME_LOOKBACKS,
    REGIME_QUANTILES,
    RESOLUTIONS,
    SELECTION_SHARE,
    SLIPPAGE_TICKS,
    STRATUM_SETS,
    UNFILTERED,
    VARIANTS,
    VOLUME_BASELINE_SESSIONS,
    VOLUME_FORMS,
    VOLUME_ROLLING_BARS,
    VOLUME_TAILS,
    Cuts,
    RegimeCut,
    Variant,
    VolumeCut,
    calibrate,
    calibrate_volume,
    db_path,
    elastic_ladder,
    fit_regime,
    fit_volume,
    grids_for,
    orb_geometry_ranges,
    orb_resolutions,
    planned_combinations,
    quantile_pair,
    raw_volume_cuts,
    strata,
    tail_pairs,
    variants_for,
    volume_series,
    windows,
)

EVERY_STATE = {
    "regime": [f"regime={state.name}" for state in regime.Regime],
    "phase": [f"phase={phase.name}" for phase in timeofday.SessionPhase],
    "volume": [f"volume={state.name}" for state in volume.VolumeState],
    "compression": [f"compression={state.name}" for state in compression.Compression],
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
        variants=CAMPAIGN,
        resolutions=[5, 15],
        split=False,
        regime_quantiles=None,
        regime_lookbacks=list(REGIME_LOOKBACKS),
        volume_quantiles=(),
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    assert planned_combinations(args) == per_stratum * 2

    args.split = True
    assert planned_combinations(args) == per_stratum * 2 * 2


# -- the calibrated regime stratum ---------------------------------------------------------

FITTED = (
    RegimeCut(5, 0.10, 0.70, REGIME_QUANTILES),
    RegimeCut(20, 0.05, 0.40, REGIME_QUANTILES),
)
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
            "volume_quantiles": (),
            **overrides,
        },
    )


def test_a_calibrated_regime_stratum_is_one_cell_per_lookback() -> None:
    """A cell rather than an axis: the thresholds move with the lookback, and a sweep crosses
    its axes, so pairing them any other way runs cells that are not comparable."""
    names = [name for name, _ in strata(REGIME, Cuts(regime=FITTED))]
    assert names == [f"regime={state.name}@{cut.name}" for state in regime.Regime for cut in FITTED]


def test_a_calibrated_cell_carries_the_thresholds_fitted_at_its_own_lookback() -> None:
    at_lookback = {cut.lookback: cut for cut in FITTED}
    for name, extra in strata(REGIME, Cuts(regime=FITTED)):
        lookback = int(name.split("@n=")[1].split(" ")[0])
        cut = at_lookback[lookback]
        assert extra["regime_lookback"] == [lookback]
        assert extra["regime_consolidating_below"] == [cut.consolidating_below]
        assert extra["regime_directional_above"] == [cut.directional_above]


def test_a_calibrated_cell_is_named_by_the_cell_size_it_was_fitted_at() -> None:
    """Two cell sizes land in one database, so a name that carried only the lookback would put
    two different cuts under one stratum -- ``docs/roadmap.md`` §M31."""
    tenths = [
        name for name, _ in strata(REGIME, Cuts(regime=calibrate(calibration_bars(), [20], (0.1, 0.9))))
    ]
    fifths = [
        name for name, _ in strata(REGIME, Cuts(regime=calibrate(calibration_bars(), [20], (0.2, 0.8))))
    ]
    assert set(tenths).isdisjoint(fifths)
    assert tenths[0].endswith("@n=20 q=0.10/0.90")
    assert fifths[0].endswith("@n=20 q=0.20/0.80")


def test_a_calibration_changes_the_regime_dimension_and_no_other() -> None:
    """Every other stratum is one filter and stays one filter; only the cut is reparameterised."""
    others = [(name, extra) for name, extra in strata(ALL_STRATA) if not name.startswith("regime=")]
    calibrated = [
        (name, extra)
        for name, extra in strata(ALL_STRATA, Cuts(regime=FITTED))
        if not name.startswith("regime=")
    ]
    assert others == calibrated


def test_an_uncalibrated_run_keeps_the_stratum_names_the_stored_databases_carry() -> None:
    assert [name for name, _ in strata(ALL_STRATA, NO_CUTS)] == [name for name, _ in strata(ALL_STRATA)]


def test_every_calibrated_grid_in_the_campaign_can_be_built() -> None:
    """The fitted thresholds reach a real parameter class, which validates them on construction."""
    fitted = calibrate(calibration_bars(), [5, 20], REGIME_QUANTILES)
    for variant in all_variants():
        for _, grid in grids_for(variant, REGIME, Cuts(regime=fitted)):
            assert len(grid) == variant.sized()


def test_the_fit_reads_the_selection_window_and_never_the_holdout() -> None:
    """Fitting on the whole series would leak the holdout into the definition of the stratum."""
    bars = calibration_bars()
    fitted = fit_regime(bars, calibrated_args())
    assert fitted[1][0].directional_above < 1.0
    assert calibrate(bars, [20], REGIME_QUANTILES)[0].directional_above == pytest.approx(1.0)


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
        variants=CAMPAIGN,
        resolutions=[5],
        split=False,
        regime_quantiles=REGIME_QUANTILES,
        regime_lookbacks=[5, 20],
        volume_quantiles=(),
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
    cash = sessionrange.CASH_OPEN_MINUTES
    assert orb_resolutions(cash, 5) == (1, 5)
    assert orb_resolutions(cash, 15) == (1, 5, 15)
    assert orb_resolutions(cash, 30) == RESOLUTIONS
    # 10-minute bars divide 930 but not a 5- or 15-minute window.
    assert 10 not in orb_resolutions(cash, 15)


def test_the_anchor_constrains_the_resolutions_as_much_as_the_window_does() -> None:
    """§M28.2's own anchors: both are whole numbers of bars at every campaign resolution.

    The overnight range spans the anchor to the cash open, so its window carries the 930 the
    cash anchor carries -- which is why it survives where a 5-minute cash range does not.
    """
    assert orb_resolutions(sessionrange.ETH_OPEN_MINUTES, sessionrange.CASH_OPEN_MINUTES) == RESOLUTIONS
    assert orb_resolutions(LONDON_OPEN_MINUTES, 60) == RESOLUTIONS
    # An anchor no bar boundary lands on rules out every resolution but the minute.
    assert orb_resolutions(7, 60) == (1,)


def test_every_opening_range_variant_can_be_prepared_at_the_resolutions_it_claims() -> None:
    """The real guard: a claimed resolution whose range grid refuses to build would fail an
    hour into a run rather than here."""
    for variant in VARIANTS["OpeningRange"]("MNQ") + ORB_VARIANTS["OpeningRange"]("MNQ"):
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_planned_combinations_skips_a_resolution_a_variant_cannot_express() -> None:
    args = argparse.Namespace(
        strategies=["OpeningRange"],
        roots=["MNQ"],
        strata=UNFILTERED,
        variants=CAMPAIGN,
        resolutions=[10],
        split=False,
        regime_quantiles=None,
        regime_lookbacks=list(REGIME_LOOKBACKS),
        volume_quantiles=(),
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


# -- the volume form and the cut it is read at -----------------------------------------------


def volume_bars(sessions_wanted: int = 30, seed: int = 7) -> pd.DataFrame:
    """Whole sessions carrying volume, so a bar-of-session baseline has sessions to be taken over."""
    n = sessions_wanted * 1440
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    opened = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": opened,
            "high": np.maximum(opened, close) + 1.0,
            "low": np.minimum(opened, close) - 1.0,
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day

    return frame


def volume_args(**overrides: object) -> argparse.Namespace:
    """The arguments ``fit_volume`` reads, at one resolution so ``resample`` is a pass-through."""
    return argparse.Namespace(**{"resolutions": [1], "volume_quantiles": VOLUME_TAILS, **overrides})


def test_the_volume_form_group_is_one_cell_per_form_tail_and_state() -> None:
    """§M27 swept three cells of one form; the axis itself is the form crossed with the cut."""
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS))
    names = [name for name, _ in strata(VOLUME_FORMS, cuts)]
    assert len(names) == len(volume.VolumeForm) * len(VOLUME_TAILS) * len(volume.VolumeState)
    assert len(set(names)) == len(names)


def test_each_volume_form_cell_admits_exactly_one_state() -> None:
    for name, extra in strata(VOLUME_FORMS):
        state = name.removeprefix("volume=").split("@")[0]
        assert extra["volume_filter"] == [volume.VolumeState[state].bit]


def test_a_volume_form_cell_names_the_series_and_the_cut_it_reads() -> None:
    """Two cells that differ only in the tail size have to be separable in the results table."""
    cut = VolumeCut(volume.key(volume.VolumeForm.PER_BAR, 30, 20), 0.5, 2.0, tails=(0.10, 0.90))
    assert cut.name == "per_bar_20 q=0.10/0.90"
    assert VolumeCut(cut.series, 0.7, 1.5).name == "per_bar_20 q=raw"


def test_the_rolling_window_is_set_only_under_the_form_that_reads_it() -> None:
    """``dead_axes`` knows one toggle per axis and this one has two, so a cross of form x window
    would run duplicate combinations silently -- ``.claude/rules/sweep-and-context.md``."""
    for name, extra in strata(VOLUME_FORMS):
        rolling = "@rolling_" in name
        assert ("volume_rolling_bars" in extra) is rolling, name
        if rolling:
            assert extra["volume_rolling_bars"] == [VOLUME_ROLLING_BARS]


def test_every_volume_series_is_a_distinct_form_at_the_campaigns_own_window() -> None:
    series = volume_series()
    assert len(series) == len(volume.VolumeForm)
    assert {key.form for key in series} == set(volume.VolumeForm)
    assert {key.baseline_sessions for key in series} == {VOLUME_BASELINE_SESSIONS}


def test_an_unfitted_volume_form_run_cuts_at_the_thresholds_the_campaign_ran() -> None:
    """So that the PER_BAR cells of an unfitted run are §M27's own, and comparable to them."""
    defaults = DeadCatParams()
    for cut in raw_volume_cuts():
        assert (cut.thin_below, cut.heavy_above) == (defaults.volume_thin_below, defaults.volume_heavy_above)
        assert cut.tails is None


def test_the_volume_form_group_is_left_out_of_all_because_it_recuts_one_dimension() -> None:
    """``all`` is one pass per dimension; including a re-cut would run volume twice."""
    assert VOLUME_FORMS in RECUTS
    assert VOLUME_FORMS not in STRATUM_SETS[ALL_STRATA]
    assert STRATUM_SETS[VOLUME_FORMS] == (VOLUME_FORMS,)


def test_a_volume_calibration_changes_the_volume_forms_and_no_other_dimension() -> None:
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS))
    assert list(strata(CORE, cuts)) == list(strata(CORE))


def test_each_form_is_fitted_against_its_own_distribution() -> None:
    """The point of the fit: one raw pair sits at a different percentile under each form, so
    HEAVY is a different population under each -- ``docs/roadmap.md`` §M27.8."""
    fitted = calibrate_volume(volume_bars(), 1, ((0.20, 0.80),))
    heavy = {cut.series.form: cut.heavy_above for cut in fitted}
    assert len(set(heavy.values())) == len(volume.VolumeForm)


def test_every_volume_form_grid_in_the_campaign_can_be_built() -> None:
    """The fitted thresholds reach a real parameter class, which validates them on construction."""
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS))
    for variant in all_variants():
        for _, grid in grids_for(variant, VOLUME_FORMS, cuts):
            assert len(grid) == variant.sized()


def test_the_volume_fit_reads_the_selection_window_and_never_the_holdout() -> None:
    """Fitting on the whole series would leak the holdout into the definition of the stratum."""
    bars = volume_bars()
    bars.iloc[math.floor(len(bars) * SELECTION_SHARE) :, bars.columns.get_loc("volume")] *= 100.0
    selection_fit = fit_volume(bars, volume_args())[1]
    whole_fit = calibrate_volume(bars, 1, VOLUME_TAILS)
    for fitted, leaked in zip(selection_fit, whole_fit, strict=True):
        assert fitted.series == leaked.series
        assert fitted.heavy_above != leaked.heavy_above


def test_no_volume_fit_is_taken_when_the_thresholds_are_left_raw() -> None:
    assert fit_volume(volume_bars(), volume_args(volume_quantiles=())) == {}


def test_a_bare_volume_quantile_flag_takes_the_tails_the_campaign_states() -> None:
    assert tail_pairs([]) == VOLUME_TAILS
    assert tail_pairs([0.1, 0.9, 0.2, 0.8]) == ((0.1, 0.9), (0.2, 0.8))
    assert tail_pairs(None) == ()


def test_an_odd_number_of_volume_quantiles_is_refused_rather_than_half_paired() -> None:
    with pytest.raises(SystemExit, match="thin and a heavy quantile per cut"):
        tail_pairs([0.2, 0.8, 0.3])


def test_planned_combinations_counts_the_volume_form_cells() -> None:
    args = argparse.Namespace(
        strategies=["InsideBar"],
        roots=["MNQ"],
        strata=VOLUME_FORMS,
        variants=CAMPAIGN,
        resolutions=[5],
        split=False,
        regime_quantiles=None,
        regime_lookbacks=list(REGIME_LOOKBACKS),
        volume_quantiles=VOLUME_TAILS,
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    cells = len(volume.VolumeForm) * len(VOLUME_TAILS) * len(volume.VolumeState)
    assert planned_combinations(args) == per_stratum * cells


# -- the §M27.3 narrow re-sweep --------------------------------------------------------------


def test_the_narrow_set_is_the_baseline_and_the_one_cell_it_asks_about() -> None:
    """Four regime cells nobody is asking about are four more comparisons -- §M27.3."""
    assert [name for name, _ in strata(NARROW)] == [UNFILTERED, "regime=DIRECTIONAL"]


def test_the_directional_group_is_calibrated_like_the_full_regime_one() -> None:
    """The prerequisite §M27.3 inherits from [#200]: the raw 0.5 cut is not one filter, so a
    group yielding a single regime cell has to be split per lookback too."""
    fitted = {name for name, _ in strata(NARROW, Cuts(regime=FITTED))}
    assert fitted == {UNFILTERED, *(f"regime=DIRECTIONAL@{cut.name}" for cut in FITTED)}


def test_a_calibrated_directional_cell_carries_its_own_lookbacks_thresholds() -> None:
    cells = dict(strata(DIRECTIONAL, Cuts(regime=FITTED)))
    for cut in FITTED:
        axes = cells[f"regime=DIRECTIONAL@{cut.name}"]
        assert axes["regime_lookback"] == [cut.lookback]
        assert axes["regime_consolidating_below"] == [cut.consolidating_below]
        assert axes["regime_directional_above"] == [cut.directional_above]


def test_the_directional_cell_is_not_swept_twice_by_the_full_set() -> None:
    """``directional`` is a subset of ``regime``, so including it in ``all`` would run one cell
    twice and report it as two."""
    assert DIRECTIONAL not in STRATUM_SETS[ALL_STRATA]
    assert len(list(strata(ALL_STRATA))) == 1 + sum(len(names) for names in EVERY_STATE.values())


def test_the_narrow_variants_cross_the_bracket_pair_and_nothing_else() -> None:
    """§M27 moved the stop across three values and could not move the target by a tick; the
    re-sweep varies exactly those two so the crossed pair is the only thing changing."""
    for variant in NARROW_VARIANTS["InsideBar"]("MNQ"):
        assert set(variant.axes) == {"tp_multiplier", "atr_multiplier"}
        assert variant.sized() == len(NARROW_TP) * len(NARROW_ATR)


def test_the_narrow_grid_contains_the_geometry_the_campaign_actually_ran() -> None:
    """Without §M27's own cell in the grid there is nothing to read the re-sweep against."""
    assert 1.0 in NARROW_TP, "the hardcoded 1x ATR target the campaign was stuck with"
    assert {5.0, 10.0, 20.0} <= set(NARROW_ATR), "§M27's three stop distances"


def test_each_narrow_variant_runs_at_exactly_one_resolution() -> None:
    """A ``Variant`` carries one base and the entry §M27 chose differs between the two bar
    sizes, so the resolutions are what separates them."""
    variants = NARROW_VARIANTS["InsideBar"]("MNQ")
    assert [variant.resolutions for variant in variants] == [(5,), (10,)]
    assert {minutes for variant in variants for minutes in variant.resolutions} == set(NARROW_ENTRY)


def test_the_narrow_entry_is_held_at_a_value_and_never_swept() -> None:
    for variant in NARROW_VARIANTS["InsideBar"]("MNQ"):
        assert set(variant.axes).isdisjoint(NARROW_ENTRY[variant.resolutions[0]])


def test_the_narrow_variants_carry_the_roots_real_costs() -> None:
    for root, commission in COMMISSION.items():
        for variant in NARROW_VARIANTS["InsideBar"](root):
            assert variant.base.commission_per_contract == commission
            assert variant.base.slippage_ticks == SLIPPAGE_TICKS


def test_every_narrow_variant_is_named_for_the_reading_tools_to_filter_on() -> None:
    """The rows land in the campaign's own database, so the variant name is what separates
    them from §M27's -- ``--variant narrow`` on every reading tool."""
    assert {variant.name for variant in NARROW_VARIANTS["InsideBar"]("MNQ")} == {NARROW}
    assert NARROW not in {variant.name for variant in all_variants()}


def test_the_campaign_grid_is_untouched_by_the_re_sweep() -> None:
    """§M27's stored rows and the code that produced them must not drift apart, so a re-sweep
    is its own variant set rather than an axis added to the campaign's."""
    assert "tp_multiplier" not in VARIANTS["InsideBar"]("MNQ")[0].axes
    assert set(NARROW_VARIANTS) < set(VARIANTS)


def test_variants_for_selects_the_grid_the_flag_names() -> None:
    assert variants_for(NARROW) is NARROW_VARIANTS
    assert variants_for(ORB) is ORB_VARIANTS
    assert variants_for(CAMPAIGN) is VARIANTS


# -- the §M28.2 re-sweep -----------------------------------------------------------


def test_the_opening_ranges_re_sweep_states_its_strata_before_it_runs() -> None:
    """§M28.1's own caveat for [#237]: choosing the stratum afterwards is a comparison too.

    The two beyond ``unfiltered`` are exactly the two that passed gate 3 on **both** roots, and
    naming them here is what makes the re-sweep a test of them rather than another search.
    """
    assert [name for name, _ in strata(ORB)] == [
        UNFILTERED,
        "regime=DIRECTIONAL",
        "trend=UP",
    ]


def test_the_re_sweep_drops_the_atr_stop_and_keeps_the_one_that_worked() -> None:
    """§M28.1's deferral: 0 of 10 cells and half the runtime, against a fraction axis whose
    top value reproduces the opposite-extreme stop exactly."""
    variants = ORB_VARIANTS["OpeningRange"]("MNQ")

    assert {variant.base.stop_mode for variant in variants} == {ORB_STOP_FRACTION}
    assert all("atr_stop_multiple" not in variant.axes for variant in variants)
    assert all(1.0 in variant.axes["stop_range_fraction"] for variant in variants)


def test_the_re_sweep_carries_every_anchor_and_every_entry_mechanism() -> None:
    """§M28 deferred both and §M28.1 left both deferred; this is where they arrive."""
    variants = ORB_VARIANTS["OpeningRange"]("MNQ")
    keys = {(variant.base.anchor_minutes, variant.base.window_minutes) for variant in variants}

    assert keys == set(ORB_RANGES.values())
    assert {variant.base.entry_mode for variant in variants} == {
        ORB_ENTRY_BREAKOUT,
        ORB_ENTRY_FADE,
        ORB_ENTRY_RETEST,
    }


def test_each_entry_mechanism_sweeps_only_the_offsets_it_reads() -> None:
    """The blind spot the entry mode is a variant dimension rather than an axis to avoid:
    ``retest_offset_ticks`` under a breakout would run identical combinations silently."""
    for variant in ORB_VARIANTS["OpeningRange"]("MNQ"):
        reads_a_limit = variant.base.entry_mode == ORB_ENTRY_RETEST
        assert ("retest_offset_ticks" in variant.axes) is reads_a_limit
        assert ("entry_offset_ticks" in variant.axes) is not reads_a_limit
        waits = variant.base.entry_mode != ORB_ENTRY_BREAKOUT
        assert ("break_confirm_ticks" in variant.axes) is waits


def test_the_campaign_grid_is_untouched_by_the_opening_ranges_re_sweep() -> None:
    """§M28.1's stored rows were produced by ``VARIANTS``, so the new axes go in their own set."""
    campaign = VARIANTS["OpeningRange"]("MNQ")

    assert all("stop_range_fraction" not in variant.axes for variant in campaign)
    assert {variant.base.entry_mode for variant in campaign} == {ORB_ENTRY_BREAKOUT}
    assert {variant.base.anchor_minutes for variant in campaign} == {sessionrange.CASH_OPEN_MINUTES}


# -- the §M28.5 fade re-run --------------------------------------------------------


def test_the_fades_re_run_states_the_fades_own_thesis_as_its_stratum() -> None:
    """``regime=DIRECTIONAL`` is the *breakout's* hypothesis, and running a fade inside it
    would be stating the wrong one in advance -- ``docs/roadmap.md`` §M28.5."""
    assert [name for name, _ in strata(ORB_FADE)] == [UNFILTERED, "regime=CONSOLIDATING"]
    assert [name for name, _ in strata(CONSOLIDATING)] == ["regime=CONSOLIDATING"]


def test_the_fades_stop_axis_reaches_below_the_one_that_parked_it_and_keeps_its_endpoint() -> None:
    """A shared endpoint is what makes the two runs comparable rather than adjacent: §M28.2's
    tightest fade cell has to exist in this grid too, and everything else has to be tighter."""
    assert min(ORB_TIGHT_FRACTIONS) < min(ORB_FRACTIONS)
    assert max(ORB_TIGHT_FRACTIONS) == min(ORB_FRACTIONS)
    for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.axes["stop_range_fraction"] == ORB_TIGHT_FRACTIONS
        assert variant.base.stop_mode == ORB_STOP_FRACTION


def test_the_fades_re_run_holds_its_entry_axes_at_exactly_what_parked_it() -> None:
    """The bracket is the only thing that moved, which is what § "Parked is not abandoned"
    asks a re-run to be able to say."""
    _, parked = ORB_ENTRIES["entry=fade"]

    for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.base.entry_mode == ORB_ENTRY_FADE
        assert {key: variant.axes[key] for key in parked} == parked


def test_only_one_of_the_fades_target_ladders_reaches_the_middle_of_the_range() -> None:
    """§M28.2's ladder is kept so the two runs share it; the midpoint is the new half."""
    ladders = {
        variant.base.target_width_multiples
        for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ")
        if variant.base.target_mode == ORB_TARGET_WIDTH
    }

    assert ladders == set(ORB_FADE_LADDERS.values())
    assert [0.5 in ladder for ladder in sorted(ladders, key=len)] == [False, True]


def test_the_fades_re_run_is_one_variant_per_range_and_target_scheme() -> None:
    """The R ladder is not repeated once per width ladder, which would be the same grid twice."""
    variants = ORB_FADE_VARIANTS["OpeningRange"]("MNQ")

    assert len(variants) == len(ORB_RANGES) * (len(ORB_FADE_LADDERS) + 1)
    assert len({variant.name for variant in variants}) == len(variants)
    assert sum(variant.base.target_mode == ORB_TARGET_R for variant in variants) == len(ORB_RANGES)


# -- the §M28.7 rejection run ------------------------------------------------------


def test_the_rejection_run_and_the_fades_share_one_stratum_tuple() -> None:
    """Both are reversion entries, so both are asked about the range that holds -- one
    hypothesis stated once rather than two copies that could drift apart."""
    assert STRATUM_SETS[ORB_REJECTION] is STRATUM_SETS[ORB_FADE]
    assert [name for name, _ in strata(ORB_REJECTION)] == [UNFILTERED, "regime=CONSOLIDATING"]


def test_the_rejection_run_holds_the_fades_bracket_at_exactly_what_it_swept() -> None:
    """The entry is the only thing that moved between §M28.5 and this, which is what makes the
    two comparable as entries rather than as two unrelated grids."""
    bracket = {"stop_range_fraction", "stop_offset_ticks"}
    fade = {variant.name.split(" entry=")[0]: variant for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ")}

    for variant in ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ"):
        against = fade[variant.name.split(" entry=")[0]]
        assert variant.base.entry_mode == ORB_ENTRY_REJECTION
        assert variant.base.stop_mode == ORB_STOP_FRACTION
        assert {key: variant.axes[key] for key in bracket} == {key: against.axes[key] for key in bracket}


def test_the_rejection_sweeps_no_break_confirmation_and_a_zero_offset() -> None:
    """It waits for no break, so the fade's arming axis would be inert; and its limit may rest
    on the extreme itself, which a stop entry cannot -- ``docs/roadmap.md`` §M28.7."""
    for variant in ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ"):
        assert "break_confirm_ticks" not in variant.axes
        assert variant.axes["entry_offset_ticks"] == ORB_REJECTION_OFFSETS

    assert min(ORB_REJECTION_OFFSETS) == 0
    assert 0 not in ORB_ENTRIES["entry=fade"][1]["entry_offset_ticks"], "a stop entry cannot"


def test_the_rejection_grid_is_the_same_size_as_the_fades() -> None:
    """One axis swapped for another of the same length, so a difference in the results is not a
    difference in how many chances each entry was given."""
    rejection = ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ")
    fade = ORB_FADE_VARIANTS["OpeningRange"]("MNQ")

    assert len(rejection) == len(fade) == len(ORB_RANGES) * (len(ORB_FADE_LADDERS) + 1)
    assert sum(v.sized() * len(v.resolutions) for v in rejection) == sum(
        v.sized() * len(v.resolutions) for v in fade
    )


def test_the_parked_orb_grid_is_untouched_by_the_fades_re_run() -> None:
    """§M28.2's stored rows were produced by ``ORB_VARIANTS``, so the tighter axis goes in its
    own set for the reason that one did."""
    assert all(
        variant.axes["stop_range_fraction"] == ORB_FRACTIONS
        for variant in ORB_VARIANTS["OpeningRange"]("MNQ")
    )
    assert variants_for(ORB_FADE) is ORB_FADE_VARIANTS
    assert variants_for(ORB_REJECTION) is ORB_REJECTION_VARIANTS
    assert variants_for(ORB) is ORB_VARIANTS


# -- the §M28.8 geometry run -------------------------------------------------------


def stored_orb_variants() -> list[Variant]:
    """Every OpeningRange variant the three stored runs were produced by."""
    return [
        variant
        for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS)
        for variant in build["OpeningRange"]("MNQ")
    ]


def test_the_one_hour_cash_range_is_in_the_swept_set_at_every_resolution() -> None:
    """[#258]'s gap: the only 60-minute window swept was anchored at the European open, so
    "the first hour of the New York session" had never been run."""
    hour = (sessionrange.CASH_OPEN_MINUTES, 60)

    assert hour not in set(ORB_RANGES.values()), "premise gone; the gap has been filled elsewhere"
    assert hour in set(orb_geometry_ranges().values())
    assert orb_resolutions(*hour) == RESOLUTIONS


def test_the_geometry_cross_keeps_every_cell_the_session_leaves_room_to_trade() -> None:
    """The cut is the session's own: a range that is not complete before the phase the forced
    flat falls in has only that phase to trade in -- ``docs/roadmap.md`` §M28.8."""
    latest = sessionrange.anchor_for(timeofday.FORCED_EXIT_PHASE)
    anchors = {sessionrange.anchor_for(phase) for phase in timeofday.SessionPhase}
    ranges = orb_geometry_ranges()

    assert set(ranges.values()) == {
        (anchor, window) for anchor in anchors for window in ORB_GEOMETRY_WINDOWS if anchor + window <= latest
    }
    # The close phase is the one anchor no window fits after.
    assert not [name for name in ranges if name.startswith("close+")]


def test_the_geometry_cross_contains_every_range_the_stored_runs_measured() -> None:
    """A shared cell is what makes the length axis comparable to §M28.2 rather than adjacent to
    it, which is why the overnight span is a window here -- §M28.5's endpoint argument."""
    assert set(ORB_RANGES.values()) <= set(orb_geometry_ranges().values())


def test_no_geometry_variant_can_collide_with_a_stored_one_in_the_same_database() -> None:
    """Rows are separated by variant name alone, and ``campaign_holdout`` pairs the two windows
    one-to-one -- so a duplicated name would pair a new row against a stored one."""
    geometry = ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ")
    names = {variant.name for variant in geometry}

    assert len(names) == len(geometry)
    assert not names & {variant.name for variant in stored_orb_variants()}


def test_the_geometry_run_states_its_stratum_before_it_runs() -> None:
    """One cell rather than the reversion pair: the question is geometric, and every entry has
    already been asked its own context question -- ``docs/roadmap.md`` §M28.8."""
    assert [name for name, _ in strata(ORB_GEOMETRY)] == [UNFILTERED]
    assert variants_for(ORB_GEOMETRY) is ORB_GEOMETRY_VARIANTS


def test_every_entry_keeps_the_bracket_its_own_campaign_swept() -> None:
    """A single bracket across all four would move two things at once on two of them: a fade's
    stop runs outward from the extreme it enters at where a breakout's runs inward."""
    wide = {ORB_ENTRY_BREAKOUT, ORB_ENTRY_RETEST}

    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.base.stop_mode == ORB_STOP_FRACTION
        if variant.base.entry_mode in wide:
            assert variant.axes["stop_range_fraction"] == ORB_FRACTIONS
            assert "stop_offset_ticks" not in variant.axes
            continue

        assert variant.axes["stop_range_fraction"] == ORB_TIGHT_FRACTIONS
        assert variant.axes["stop_offset_ticks"] == [2, 8]


def test_every_entry_sweeps_only_the_offsets_it_reads() -> None:
    """``ORB_ENTRIES``' own reason, carried to the fourth mode: ``dead_axes`` cannot see an
    axis that is inert under a mode, so an inert one runs identical combinations silently."""
    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        reads_a_limit = variant.base.entry_mode == ORB_ENTRY_RETEST
        assert ("retest_offset_ticks" in variant.axes) is reads_a_limit
        assert ("entry_offset_ticks" in variant.axes) is not reads_a_limit
        waits = variant.base.entry_mode in (ORB_ENTRY_FADE, ORB_ENTRY_RETEST)
        assert ("break_confirm_ticks" in variant.axes) is waits


def test_the_geometry_run_reproduces_a_stored_variant_wherever_the_two_share_a_cell() -> None:
    """The five stored ranges are re-run at exactly the parameters that produced their rows, so
    the new table shares cells with the old one rather than running beside it."""
    stored = [variant for variant in stored_orb_variants() if variant.base.stop_mode == ORB_STOP_FRACTION]
    matched = 0
    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        against = [other for other in stored if other.base == variant.base]
        if not against:
            continue

        assert len(against) == 1, variant.name
        assert variant.axes == against[0].axes, variant.name
        assert variant.resolutions == against[0].resolutions, variant.name
        matched += 1

    schemes = sum(len(entry.targets) for entry in ORB_GEOMETRY_ENTRIES.values())
    assert matched == len(ORB_RANGES) * schemes


def test_every_geometry_variant_can_be_prepared_at_the_resolutions_it_claims() -> None:
    """The real guard: a claimed resolution whose range grid refuses to build would fail an
    hour into a run rather than here."""
    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.resolutions, variant.name
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_the_stored_orb_grids_are_untouched_by_the_geometry_run() -> None:
    """§M28.1's, §M28.2's and §M28.5's rows were each produced by their own set, so a crossed
    anchor goes in a sixth rather than into any of them."""
    for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS):
        anchors = {variant.base.anchor_minutes for variant in build["OpeningRange"]("MNQ")}
        assert anchors <= {anchor for anchor, _ in ORB_RANGES.values()}


def test_the_hoisted_target_schemes_are_what_the_stored_re_sweep_swept() -> None:
    """``ORB_TARGETS`` is one dict where two builders held the same literal; the geometry run
    reads it so that a stored cell and a new one cannot drift apart."""
    assert list(ORB_TARGETS) == ["target=R", "target=width"]
    assert ORB_TARGETS["target=R"] == (ORB_TARGET_R, {"tp_multiplier": [1.0, 2.0]})
    assert ORB_TARGETS["target=width"] == (ORB_TARGET_WIDTH, {})
    for name in ("entry=breakout", "entry=retest"):
        assert [target[0] for target in ORB_GEOMETRY_ENTRIES[name].targets] == list(ORB_TARGETS)


# -- the M28.10 follow-through run --------------------------------------------------


def follow_through_variants() -> list[Variant]:
    return ORB_FOLLOW_THROUGH_VARIANTS["OpeningRange"]("MNQ")


def test_the_follow_through_run_states_its_stratum_before_it_runs() -> None:
    """One cell, as the geometry run has: the question is about the bracket's unit."""
    assert [name for name, _ in strata(ORB_FOLLOW_THROUGH)] == [UNFILTERED]
    assert variants_for(ORB_FOLLOW_THROUGH) is ORB_FOLLOW_THROUGH_VARIANTS


def test_no_follow_through_variant_can_collide_with_a_stored_one() -> None:
    """Rows are separated by variant name alone, and the ranges here are ones already swept."""
    variants = follow_through_variants()
    names = {variant.name for variant in variants}

    assert len(names) == len(variants)
    assert not names & {other.name for other in stored_orb_variants()}
    assert not names & {other.name for other in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ")}


def test_the_run_carries_an_unscaled_control_in_the_same_pass() -> None:
    """A treatment measured against a stored run is measured against a different pass; this
    one is on the same bars in the same sweep -- ``docs/roadmap.md`` M28.10."""
    controls = [v for v in follow_through_variants() if v.base.follow_through_scaling == ORB_SCALE_NONE]

    assert len(controls) == len(ORB_FOLLOW_THROUGH_RANGES)
    assert all(name.endswith("scale=off") for name in (v.name for v in controls))


def test_the_control_and_every_treatment_differ_by_the_scaling_alone() -> None:
    """The property the comparison rests on: one field moves and the axes are identical."""
    by_range: dict[int, list[Variant]] = {}
    for variant in follow_through_variants():
        by_range.setdefault(variant.base.window_minutes, []).append(variant)

    for window, variants in by_range.items():
        control = next(v for v in variants if v.base.follow_through_scaling == ORB_SCALE_NONE)
        for treatment in variants:
            assert treatment.axes == control.axes, treatment.name
            assert treatment.resolutions == control.resolutions, treatment.name
            unscaled = replace(
                treatment.base,
                follow_through_scaling=ORB_SCALE_NONE,
                follow_through_sessions=control.base.follow_through_sessions,
            )
            assert unscaled == control.base, (window, treatment.name)


def test_the_lookback_is_a_variant_dimension_rather_than_an_axis() -> None:
    """``follow_through_sessions`` is inert at ORB_SCALE_NONE, and ``dead_axes`` knows one off
    value per axis -- so crossing the two would run the control once per lookback in silence."""
    for variant in follow_through_variants():
        assert "follow_through_sessions" not in variant.axes
        assert "follow_through_scaling" not in variant.axes


def test_every_scaled_variant_states_its_geometry_in_a_width_the_scale_can_reach() -> None:
    """The params class refuses an R target or an opposite-extreme stop under a scaling mode,
    so a variant set that built one would fail at construction rather than run."""
    for variant in follow_through_variants():
        assert variant.base.target_mode == ORB_TARGET_WIDTH
        assert variant.base.stop_mode == ORB_STOP_FRACTION


def test_the_run_is_confined_to_the_ranges_the_null_separated() -> None:
    """M28.8's gate 3 puts the excess at 15 and 30 minutes from the cash open and nowhere
    else, so this asks its question where there is an edge to lose."""
    windows = {variant.base.window_minutes for variant in follow_through_variants()}
    anchors = {variant.base.anchor_minutes for variant in follow_through_variants()}

    assert windows == {15, 30}
    assert anchors == {sessionrange.CASH_OPEN_MINUTES}


def test_every_follow_through_variant_can_be_prepared_at_the_resolutions_it_claims() -> None:
    for variant in follow_through_variants():
        assert variant.resolutions, variant.name
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_a_scaled_grid_declares_the_lookback_its_combinations_read() -> None:
    """The context is derived from the grid, so a lookback nothing declared would raise in the
    loop rather than be built once."""
    for variant in follow_through_variants():
        for _, grid in grids_for(variant, UNFILTERED):
            declared = grid.required_context().follow_through_sessions
            if variant.base.follow_through_scaling == ORB_SCALE_NONE:
                assert declared == (), variant.name
                continue

            assert declared == (variant.base.follow_through_sessions,), variant.name


# -- the M28.11 bracket ladder run --------------------------------------------------


def bracket_variants() -> list[Variant]:
    return ORB_BRACKET_VARIANTS["OpeningRange"]("MNQ")


def test_the_bracket_run_states_its_stratum_before_it_runs() -> None:
    """One cell, as the geometry and follow-through runs have: the question is about the
    bracket's size rather than about the context it is traded in."""
    assert [name for name, _ in strata(ORB_BRACKET)] == [UNFILTERED]
    assert variants_for(ORB_BRACKET) is ORB_BRACKET_VARIANTS


def test_the_stop_ladder_extends_the_stored_axis_instead_of_replacing_it() -> None:
    """[#262]'s premise: 1.0 was the last value and the winning one, so the axis was truncated.
    Every stored fraction is re-run at exactly its own value, and the new ones sit past it."""
    assert ORB_LADDER_FRACTIONS[: len(ORB_FRACTIONS)] == ORB_FRACTIONS
    assert max(ORB_FRACTIONS) == 1.0
    assert [f for f in ORB_LADDER_FRACTIONS if f > 1.0]
    assert ORB_LADDER_FRACTIONS == sorted(ORB_LADDER_FRACTIONS)


def test_a_stop_past_the_range_width_is_legal_rather_than_refused() -> None:
    """The whole ladder rests on it: past 1.0 the stop sits outside the range entirely, and a
    params class that refused it would fail the run rather than the axis."""
    for fraction in ORB_LADDER_FRACTIONS:
        params = OpeningRangeParams(stop_mode=ORB_STOP_FRACTION, stop_range_fraction=fraction)

        assert params.stop_range_fraction == fraction


def test_the_width_ladder_is_a_variant_dimension_rather_than_an_axis() -> None:
    """A ladder is a tuple and tuples are not sweepable, which is why no ORB campaign varied
    it: ``_orb_further_targets`` hands over the parameter default and no axis reaches it."""
    ladders = {variant.base.target_width_multiples for variant in bracket_variants()}

    assert ladders == set(ORB_WIDTH_LADDERS.values())
    for variant in bracket_variants():
        assert "target_width_multiples" not in variant.axes
        assert "target_mode" not in variant.axes


def test_the_ladder_every_stored_run_used_is_one_cell_of_the_swept_set() -> None:
    """What makes this an extension of the stored table rather than a run beside it: the
    parameter default is in the set, so the new rows share a target scheme with the old ones."""
    assert OpeningRangeParams().target_width_multiples in set(ORB_WIDTH_LADDERS.values())


def test_the_no_target_arm_leaves_every_leg_to_the_forced_flat() -> None:
    """M28.9 measured ``(nan, nan)`` against the default and reported it winning on the
    selection window and losing on the holdout; this is the arm that reproduces it."""
    runner = ORB_WIDTH_LADDERS["target=runner"]

    assert all(math.isnan(level) for level in runner)
    assert [name for name, ladder in ORB_WIDTH_LADDERS.items() if all(math.isnan(x) for x in ladder)] == [
        "target=runner",
    ]


def test_every_ladder_has_a_leg_for_each_target_the_order_can_fill() -> None:
    """A ladder longer than ``order_quantity`` raises at construction, so a set built with one
    would fail the whole run rather than the cell."""
    for variant in bracket_variants():
        assert len(variant.base.target_levels) <= variant.base.order_quantity, variant.name


def test_no_bracket_variant_can_collide_with_a_stored_one() -> None:
    """Rows are separated by variant name alone, and these are ranges already swept twice."""
    variants = bracket_variants()
    names = {variant.name for variant in variants}
    elsewhere = {
        other.name
        for build in (ORB_GEOMETRY_VARIANTS, ORB_FOLLOW_THROUGH_VARIANTS)
        for other in build["OpeningRange"]("MNQ")
    }

    assert len(names) == len(variants)
    assert not names & {other.name for other in stored_orb_variants()}
    assert not names & elsewhere


def test_the_bracket_run_is_confined_to_the_ranges_the_null_separated() -> None:
    """M28.8's gate 3 puts the excess at 15 and 30 minutes from the cash open and nowhere else,
    so an axis is extended where there is an edge to lose -- ``ORB_FOLLOW_THROUGH_RANGES``."""
    assert {window for _, window in ORB_BRACKET_RANGES.values()} == {15, 30}
    assert {anchor for anchor, _ in ORB_BRACKET_RANGES.values()} == {sessionrange.CASH_OPEN_MINUTES}
    assert set(ORB_BRACKET_RANGES.values()) == set(ORB_FOLLOW_THROUGH_RANGES.values())


def test_the_bracket_run_sweeps_the_breakouts_own_offset_and_no_other() -> None:
    """One entry, held at exactly what M28.2 and M28.10 swept it on, so the bracket is the only
    thing that moved -- and an offset the mode does not read runs identical combinations."""
    for variant in bracket_variants():
        assert variant.base.entry_mode == ORB_ENTRY_BREAKOUT
        assert variant.base.stop_mode == ORB_STOP_FRACTION
        assert variant.base.target_mode == ORB_TARGET_WIDTH
        assert variant.axes["entry_offset_ticks"] == [1, 4]
        assert "retest_offset_ticks" not in variant.axes
        assert "break_confirm_ticks" not in variant.axes


def test_the_bracket_run_reproduces_the_unscaled_control_at_the_cell_they_share() -> None:
    """M28.10's ``scale=off`` arm is this geometry at the stored fraction ladder, so the two
    tables meet rather than run beside each other -- which is what makes the extension readable
    against the stored figure."""
    controls = {
        variant.base.window_minutes: variant
        for variant in ORB_FOLLOW_THROUGH_VARIANTS["OpeningRange"]("MNQ")
        if variant.base.follow_through_scaling == ORB_SCALE_NONE
    }
    matched = 0
    for variant in bracket_variants():
        if variant.base.target_width_multiples != OpeningRangeParams().target_width_multiples:
            continue

        control = controls[variant.base.window_minutes]

        assert variant.base == control.base, variant.name
        assert variant.resolutions == control.resolutions, variant.name
        assert set(control.axes["stop_range_fraction"]) <= set(variant.axes["stop_range_fraction"])
        assert {k: v for k, v in variant.axes.items() if k != "stop_range_fraction"} == {
            k: v for k, v in control.axes.items() if k != "stop_range_fraction"
        }
        matched += 1

    assert matched == len(ORB_BRACKET_RANGES)


def test_every_bracket_variant_can_be_prepared_at_the_resolutions_it_claims() -> None:
    for variant in bracket_variants():
        assert variant.resolutions, variant.name
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_the_stored_orb_grids_are_untouched_by_the_bracket_run() -> None:
    """M28.1's through M28.10's rows were each produced by their own set, so an extended axis
    goes in a seventh rather than into any of them."""
    for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS, ORB_GEOMETRY_VARIANTS):
        for variant in build["OpeningRange"]("MNQ"):
            fractions = variant.axes.get("stop_range_fraction", [])

            assert all(fraction <= 1.0 for fraction in fractions), variant.name


def test_the_bracket_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in ORB_BRACKET_VARIANTS["OpeningRange"](root):
            assert variant.base.commission_per_contract == COMMISSION[root]
            assert variant.base.slippage_ticks == SLIPPAGE_TICKS


# -- the §M26.9 volume run -------------------------------------------------------------------


def volume_variants(root: str = "MNQ") -> list[Variant]:
    """The control and the treatment of the volume run, in that order."""
    return ELASTIC_VOLUME_VARIANTS["ElasticBand"](root)


def test_the_volume_run_states_its_strata_before_it_runs() -> None:
    """The volume dimension re-cut on its own distribution, read against the unfiltered
    baseline in the same pass rather than against a cell chosen once the table is in."""
    fitted = tuple(VolumeCut(key, 0.7, 1.5, tails=pair) for key in volume_series() for pair in VOLUME_TAILS)
    raw = [name for name, _ in strata(ELASTIC_VOLUME, Cuts(volume=raw_volume_cuts()))]
    cut = [name for name, _ in strata(ELASTIC_VOLUME, Cuts(volume=fitted))]

    assert raw[0] == UNFILTERED and cut[0] == UNFILTERED
    assert len(raw) == 1 + len(volume_series()) * len(volume.VolumeState)
    assert len(cut) == 1 + len(volume_series()) * len(VOLUME_TAILS) * len(volume.VolumeState)


def test_the_volume_run_carries_its_own_control_shape_in_the_same_pass() -> None:
    """A stored ``shape=any`` row came out of a different grid, so pairing against it would
    compare two runs rather than two arms -- ``docs/roadmap.md`` §M26.5."""
    assert set(ELASTIC_VOLUME_SHAPES.values()) == {SHAPE_ANY, SHAPE_REVERSAL}
    assert {variant.base.signal_shape for variant in volume_variants()} == {SHAPE_ANY, SHAPE_REVERSAL}


def test_the_control_and_the_treatment_differ_by_the_shape_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over this pair: every other field of
    the base and every axis is shared, so a paired cell differs by the requirement only."""
    control, treatment = volume_variants()

    assert replace(control.base, signal_shape=treatment.base.signal_shape) == treatment.base
    assert control.axes == treatment.axes


def test_the_volume_run_holds_the_three_axes_the_shape_campaign_spent() -> None:
    """§M26.5 measured ``min_one_sided_bars``'s low end as a dead value and its high end as a
    cost, the reversal shape as making ``min_bars_outside`` a duplicate on 82.7% of cells, and
    the target ladder's η² on the held-out profit factor as 0.0000."""
    for variant in volume_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert "min_bars_outside" not in variant.axes
        assert variant.base.min_one_sided_bars == 0
        assert variant.base.target_stretch_levels == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]


def test_every_volume_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    """§M26.4 established that the Bollinger source does not survive a holdout, so the question
    here is the volume and not the channel."""
    for variant in volume_variants():
        assert variant.base.band_source == BAND_VWAP
        assert variant.base.target_mode == TARGET_STRETCH
        assert variant.axes["stop_mode"] == [STOP_ATR, STOP_SWING, STOP_CATASTROPHE]


def test_the_ladder_is_readable_back_off_every_volume_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in volume_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]


def test_no_volume_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing
    separating them, so ``campaign_holdout`` would pair two campaigns' windows together."""
    stored = {variant.name for variant in VARIANTS["ElasticBand"]("MNQ")} | {
        variant.name for variant in ELASTIC_SHAPE_VARIANTS["ElasticBand"]("MNQ")
    }

    assert not stored & {variant.name for variant in volume_variants()}


def test_the_stored_shape_grid_is_untouched_by_the_volume_run() -> None:
    """§M26.5's rows were produced by its own set, so holding an axis goes in a new one."""
    for variant in ELASTIC_SHAPE_VARIANTS["ElasticBand"]("MNQ"):
        assert "min_one_sided_bars" in variant.axes
        assert "min_bars_outside" in variant.axes


def test_every_volume_variant_grid_can_be_built_at_every_cell() -> None:
    """A cell that cannot be built fails here rather than an hour into the run."""
    for variant in volume_variants():
        for _, grid in grids_for(variant, ELASTIC_VOLUME, Cuts(volume=raw_volume_cuts())):
            assert len(grid) == variant.sized()
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_volume_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in volume_variants(root):
            assert variant.base.commission_per_contract == pytest.approx(COMMISSION[root])
            assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS)


def test_variants_for_selects_the_volume_grid() -> None:
    assert variants_for(ELASTIC_VOLUME) is ELASTIC_VOLUME_VARIANTS


# -- the §M26.6 recovery run -----------------------------------------------------------------


def recovery_variants(root: str = "MNQ") -> list[Variant]:
    """Every arm of the recovery run, the two controls first."""
    return ELASTIC_RECOVERY_VARIANTS["ElasticBand"](root)


def test_the_recovery_run_states_its_stratum_before_it_runs() -> None:
    """The trigger is the thing being measured, so the pass adds no context cell to cross it
    with -- ``docs/roadmap.md`` §M26.6."""
    assert [name for name, _ in strata(ELASTIC_RECOVERY, NO_CUTS)] == [UNFILTERED]


def test_the_recovery_run_carries_both_controls_in_the_same_pass() -> None:
    """A stored row came out of a different grid, so pairing against it would compare two runs
    rather than two arms. The question is whether waiting for the reaction beats reading it off
    a bar still outside, so requiring nothing is not the only control it needs."""
    triggers = {trigger for trigger, _, _ in ELASTIC_RECOVERY_ARMS.values()}
    shapes = {shape for trigger, shape, _ in ELASTIC_RECOVERY_ARMS.values() if trigger == TRIGGER_EXTENDED}

    assert triggers == {TRIGGER_EXTENDED, TRIGGER_RECOVERY}
    assert shapes == {SHAPE_ANY, SHAPE_REVERSAL}


def test_every_recovery_arm_differs_from_the_control_by_the_entry_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over these arms: every other field of
    the base and every axis is shared, so a paired cell differs by the entry rule only."""
    control, *rest = recovery_variants()
    for arm in rest:
        rebased = replace(
            control.base,
            entry_trigger=arm.base.entry_trigger,
            recovery_fraction=arm.base.recovery_fraction,
            signal_shape=arm.base.signal_shape,
        )

        assert rebased == arm.base
        assert control.axes == arm.axes


def test_the_recovery_run_keeps_the_run_length_the_shapes_made_a_duplicate() -> None:
    """§M26.5 measured ``min_bars_outside`` as inert under ``reclaim`` on 100% of cells and
    under ``reversal`` on 82.7%. The recovery trigger reads the run at the bar *before* the
    signal, so it is the one entry here under which the axis is live."""
    for variant in recovery_variants():
        assert variant.axes["min_bars_outside"] == [1, 2]


def test_the_recovery_run_drops_the_axis_the_shape_campaign_measured_as_dead() -> None:
    """§M26.5: ``min_one_sided_bars``'s low end is a dead value and its high end is a cost."""
    for variant in recovery_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert variant.base.min_one_sided_bars == 0
        assert variant.base.target_stretch_levels == ELASTIC_LADDERS[ELASTIC_RECOVERY_TARGET]


def test_every_recovery_depth_is_inside_the_band_and_the_loosest_is_its_edge() -> None:
    """A depth of 1.0 is the band edge itself; 0.5 was measured at 140 signals in 1.66M MNQ
    bars and left out, which is the engulfing mode's failure -- ``docs/roadmap.md`` §M26.6."""
    depths = {depth for trigger, _, depth in ELASTIC_RECOVERY_ARMS.values() if trigger == TRIGGER_RECOVERY}

    assert depths == {1.0, 0.9, 0.75}
    assert all(0.0 < depth <= 1.0 for depth in depths)


def test_every_recovery_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    """§M26.4 established that the Bollinger source does not survive a holdout, so the question
    here is the entry and not the channel."""
    for variant in recovery_variants():
        assert variant.base.band_source == BAND_VWAP
        assert variant.base.target_mode == TARGET_STRETCH
        assert variant.axes["stop_mode"] == [STOP_ATR, STOP_SWING, STOP_CATASTROPHE]


def test_the_ladder_is_readable_back_off_every_recovery_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in recovery_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_RECOVERY_TARGET]


def test_no_recovery_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing
    separating them, so ``campaign_holdout`` would pair two campaigns' windows together."""
    stored = (
        {variant.name for variant in VARIANTS["ElasticBand"]("MNQ")}
        | {variant.name for variant in ELASTIC_SHAPE_VARIANTS["ElasticBand"]("MNQ")}
        | {variant.name for variant in ELASTIC_VOLUME_VARIANTS["ElasticBand"]("MNQ")}
    )

    assert not stored & {variant.name for variant in recovery_variants()}


def test_every_recovery_variant_grid_can_be_built_at_every_cell() -> None:
    """A cell that cannot be built fails here rather than an hour into the run."""
    for variant in recovery_variants():
        for _, grid in grids_for(variant, ELASTIC_RECOVERY, NO_CUTS):
            assert len(grid) == variant.sized()
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_recovery_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in recovery_variants(root):
            assert variant.base.commission_per_contract == pytest.approx(COMMISSION[root])
            assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS)


def test_variants_for_selects_the_recovery_grid() -> None:
    assert variants_for(ELASTIC_RECOVERY) is ELASTIC_RECOVERY_VARIANTS


# -- the §M26.8 band-stop run ------------------------------------------------------------------


def band_stop_variants(root: str = "MNQ") -> list[Variant]:
    """Every arm of the band-stop run, the three existing stops first."""
    return ELASTIC_BAND_STOP_VARIANTS["ElasticBand"](root)


def test_the_band_stop_run_states_its_stratum_before_it_runs() -> None:
    """The stop is the thing being measured, so the pass adds no context cell to cross it
    with -- ``docs/roadmap.md`` §M26.8."""
    assert [name for name, _ in strata(ELASTIC_BAND_STOP, NO_CUTS)] == [UNFILTERED]


def test_the_band_stop_run_carries_the_three_existing_stops_in_the_same_pass() -> None:
    """A stored row came out of a different grid, so pairing against it would compare two runs
    rather than two arms."""
    modes = {mode for mode, _ in ELASTIC_BAND_STOP_ARMS.values()}

    assert modes == {STOP_ATR, STOP_SWING, STOP_CATASTROPHE, STOP_BAND}


def test_every_band_stop_arm_differs_from_its_control_by_the_stop_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over these arms: every other field of
    the base and every axis is shared, so a paired cell differs by where the stop went."""
    control, *rest = band_stop_variants()
    for arm in rest:
        rebased = replace(
            control.base,
            stop_mode=arm.base.stop_mode,
            band_stop_std=arm.base.band_stop_std,
            signal_shape=arm.base.signal_shape,
        )

        assert rebased == arm.base
        assert control.axes == arm.axes


def test_the_depth_is_carried_by_the_arm_because_it_is_inert_under_every_other_stop() -> None:
    """Crossing it with the scheme would run identical combinations ``dead_axes`` cannot see."""
    for variant in band_stop_variants():
        assert "band_stop_std" not in variant.axes
        assert "stop_mode" not in variant.axes

    depths = {depth for mode, depth in ELASTIC_BAND_STOP_ARMS.values() if mode == STOP_BAND}
    others = {depth for mode, depth in ELASTIC_BAND_STOP_ARMS.values() if mode != STOP_BAND}

    assert depths == {0.5, 1.0, 1.5, 2.0}
    assert all(depth > 0.0 for depth in depths)
    # The three schemes that never read it carry one value between them, so nothing about
    # them varies with an axis they are blind to.
    assert len(others) == 1


def test_the_band_stop_run_asks_its_question_over_an_entry_with_an_edge_and_one_without() -> None:
    """§M26.5 measured an excess for the reversal shape and none for the control, so the pair
    bounds whether a stop scheme is being ranked or the bars under it are."""
    assert set(ELASTIC_BAND_STOP_SHAPES.values()) == {SHAPE_ANY, SHAPE_REVERSAL}
    shapes = {variant.base.signal_shape for variant in band_stop_variants()}

    assert shapes == {SHAPE_ANY, SHAPE_REVERSAL}
    assert len(band_stop_variants()) == len(ELASTIC_BAND_STOP_ARMS) * len(ELASTIC_BAND_STOP_SHAPES)


def test_the_band_stop_run_drops_the_axis_the_shape_campaign_measured_as_dead() -> None:
    """§M26.5: ``min_one_sided_bars``'s low end is a dead value and its high end is a cost.
    ``min_bars_outside`` stays, because §M26.9 dropped it for the reversal shape alone and half
    these arms carry the control instead."""
    for variant in band_stop_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert variant.axes["min_bars_outside"] == [1, 2]
        assert variant.base.min_one_sided_bars == 0
        assert variant.base.target_stretch_levels == ELASTIC_LADDERS[ELASTIC_BAND_STOP_TARGET]


def test_every_band_stop_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    for variant in band_stop_variants():
        assert variant.base.band_source == BAND_VWAP
        assert variant.base.target_mode == TARGET_STRETCH
        assert variant.axes["entry_std"] == [2.0, 2.5, 3.0]


def test_the_ladder_is_readable_back_off_every_band_stop_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in band_stop_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_BAND_STOP_TARGET]


def test_no_band_stop_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing
    separating them, so ``campaign_holdout`` would pair two campaigns' windows together."""
    stored = (
        {variant.name for variant in VARIANTS["ElasticBand"]("MNQ")}
        | {variant.name for variant in ELASTIC_SHAPE_VARIANTS["ElasticBand"]("MNQ")}
        | {variant.name for variant in ELASTIC_VOLUME_VARIANTS["ElasticBand"]("MNQ")}
        | {variant.name for variant in ELASTIC_RECOVERY_VARIANTS["ElasticBand"]("MNQ")}
    )
    names = {variant.name for variant in band_stop_variants()}

    assert not stored & names
    assert len(names) == len(band_stop_variants())


def test_every_band_stop_variant_grid_can_be_built_at_every_cell() -> None:
    """A cell that cannot be built fails here rather than an hour into the run."""
    for variant in band_stop_variants():
        for _, grid in grids_for(variant, ELASTIC_BAND_STOP, NO_CUTS):
            assert len(grid) == variant.sized()
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_band_stop_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in band_stop_variants(root):
            assert variant.base.commission_per_contract == pytest.approx(COMMISSION[root])
            assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS)


def test_variants_for_selects_the_band_stop_grid() -> None:
    assert variants_for(ELASTIC_BAND_STOP) is ELASTIC_BAND_STOP_VARIANTS
