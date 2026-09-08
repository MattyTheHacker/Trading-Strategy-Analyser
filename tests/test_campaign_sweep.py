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
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_RETEST,
    ORB_STOP_FRACTION,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    STOP_ATR,
    STOP_CATASTROPHE,
    STOP_SWING,
    DeadCatParams,
)
from tools.campaign_sweep import (
    ALL_STRATA,
    CAMPAIGN,
    COMMISSION,
    CONTEXT,
    CORE,
    CONSOLIDATING,
    DIRECTIONAL,
    ELASTIC_LADDERS,
    NARROW,
    NARROW_ATR,
    NARROW_ENTRY,
    NARROW_TP,
    NARROW_VARIANTS,
    NO_CUTS,
    ORB,
    ORB_ENTRIES,
    ORB_FADE,
    ORB_FADE_LADDERS,
    ORB_FADE_VARIANTS,
    ORB_FRACTIONS,
    ORB_RANGES,
    ORB_TIGHT_FRACTIONS,
    ORB_VARIANTS,
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
    Variant,
    VolumeCut,
    calibrate,
    calibrate_volume,
    db_path,
    fit_regime,
    fit_volume,
    grids_for,
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
            "volume_quantiles": (),
            **overrides,
        },
    )


def test_a_calibrated_regime_stratum_is_one_cell_per_lookback() -> None:
    """A cell rather than an axis: the thresholds move with the lookback, and a sweep crosses
    its axes, so pairing them any other way runs cells that are not comparable."""
    names = [name for name, _ in strata(REGIME, Cuts(regime=FITTED))]
    assert names == [f"regime={state.name}@n={n}" for state in regime.Regime for n in FITTED]


def test_a_calibrated_cell_carries_the_thresholds_fitted_at_its_own_lookback() -> None:
    for name, extra in strata(REGIME, Cuts(regime=FITTED)):
        lookback = int(name.split("@n=")[1])
        consolidating, directional = FITTED[lookback]
        assert extra["regime_lookback"] == [lookback]
        assert extra["regime_consolidating_below"] == [consolidating]
        assert extra["regime_directional_above"] == [directional]


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
    assert fitted == {UNFILTERED, *(f"regime=DIRECTIONAL@n={n}" for n in FITTED)}


def test_a_calibrated_directional_cell_carries_its_own_lookbacks_thresholds() -> None:
    cells = dict(strata(DIRECTIONAL, Cuts(regime=FITTED)))
    for lookback, (consolidating, directional) in FITTED.items():
        axes = cells[f"regime=DIRECTIONAL@n={lookback}"]
        assert axes["regime_lookback"] == [lookback]
        assert axes["regime_consolidating_below"] == [consolidating]
        assert axes["regime_directional_above"] == [directional]


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


def test_the_parked_orb_grid_is_untouched_by_the_fades_re_run() -> None:
    """§M28.2's stored rows were produced by ``ORB_VARIANTS``, so the tighter axis goes in its
    own set for the reason that one did."""
    assert all(
        variant.axes["stop_range_fraction"] == ORB_FRACTIONS
        for variant in ORB_VARIANTS["OpeningRange"]("MNQ")
    )
    assert variants_for(ORB_FADE) is ORB_FADE_VARIANTS
    assert variants_for(ORB) is ORB_VARIANTS
