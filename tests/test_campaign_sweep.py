"""What the registry-wide campaign's plan claims, pinned.

The sweeps themselves need ``cache/continuous`` and are not exercised here; the shape of the
plan is: a stratum that filters two dimensions at once, a variant whose grid cannot be built, a
root whose commission is the other root's, or two archetypes pointed at one database.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import logging
import math
from dataclasses import replace
from itertools import chain, product
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import (
    archetypes,
    compression,
    higher_timeframe,
    instruments,
    regime,
    results,
    sessionrange,
    sessions,
    sweep,
    timeofday,
    trades,
    trend,
    volume,
)
from nqbt.sim.bracket import BREAKEVEN_ON_CLOSE, BREAKEVEN_R, MEASURE_OPEN_PROFIT
from nqbt.sim.types import (
    BAND_BOLLINGER,
    BAND_VWAP,
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_REJECTION,
    ORB_ENTRY_RETEST,
    ORB_SCALE_NONE,
    ORB_STOP_ATR,
    ORB_STOP_FRACTION,
    ORB_STOP_OPPOSITE,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    SHAPE_ANY,
    SHAPE_REVERSAL,
    SIZING_LABELS,
    STOP_ATR,
    STOP_BAND,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_R,
    TARGET_STRETCH,
    TRIGGER_EXTENDED,
    TRIGGER_RECOVERY,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    SqueezeBreakoutParams,
    active_early_exits,
    sizing_labels,
)
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_sweep
from tools.campaign_sweep import (
    ADVERSE_ATRS,
    ADVERSE_CLOSES,
    ALL_STRATA,
    ATR_EXPANSIONS,
    CAMPAIGN,
    COMMISSION,
    CONFLUENCE_SIZING,
    CONFLUENCE_SIZING_VARIANTS,
    CONSOLIDATING,
    CONTEXT,
    CORE,
    COUNTER_TREND_BARS,
    DIRECTIONAL,
    EARLY_EXIT,
    EARLY_EXIT_2,
    EARLY_EXIT_2_VARIANTS,
    EARLY_EXIT_3,
    EARLY_EXIT_3_VARIANTS,
    EARLY_EXIT_BARS,
    EARLY_EXIT_BELOW_R,
    EARLY_EXIT_MINUTES,
    EARLY_EXIT_VARIANTS,
    ELASTIC_BAND_STOP,
    ELASTIC_BAND_STOP_ARMS,
    ELASTIC_BAND_STOP_SHAPES,
    ELASTIC_BAND_STOP_TARGET,
    ELASTIC_BAND_STOP_VARIANTS,
    ELASTIC_CHANNEL,
    ELASTIC_CHANNEL_PERIOD,
    ELASTIC_CHANNEL_SOURCES,
    ELASTIC_CHANNEL_VARIANTS,
    ELASTIC_INVERT,
    ELASTIC_INVERT_AXES,
    ELASTIC_INVERT_VARIANTS,
    ELASTIC_LADDERS,
    ELASTIC_RECOVERY,
    ELASTIC_RECOVERY_ARMS,
    ELASTIC_RECOVERY_TARGET,
    ELASTIC_RECOVERY_VARIANTS,
    ELASTIC_SHAPE_VARIANTS,
    ELASTIC_TARGET_R,
    ELASTIC_VOLUME,
    ELASTIC_VOLUME_BRACKET,
    ELASTIC_VOLUME_SHAPES,
    ELASTIC_VOLUME_TARGET,
    ELASTIC_VOLUME_VARIANTS,
    EMAPULLBACK_CONFIRM,
    EMAPULLBACK_CONFIRM_VARIANTS,
    EMAPULLBACK_HELD_KINDS,
    EMAPULLBACK_MA_TRAIL,
    EMAPULLBACK_MA_TRAIL_VARIANTS,
    EMAPULLBACK_TRAIL,
    EMAPULLBACK_TRAIL_VARIANTS,
    GIVE_BACK_FROM_R,
    GIVE_BACKS,
    IBT_SIZING,
    IBT_SIZING_HIGH,
    IBT_SIZING_HIGH_VARIANTS,
    IBT_SIZING_VARIANTS,
    IBT_STRUCTURE,
    IBT_STRUCTURE_ENDS,
    IBT_STRUCTURE_ENDS_VARIANTS,
    IBT_STRUCTURE_VARIANTS,
    LONDON_OPEN_MINUTES,
    MIDDAY,
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
    ORB_FOLLOW_THROUGH,
    ORB_FOLLOW_THROUGH_RANGES,
    ORB_FOLLOW_THROUGH_VARIANTS,
    ORB_FRACTIONS,
    ORB_GEOMETRY,
    ORB_GEOMETRY_ENTRIES,
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
    RECUTS,
    REGIME,
    REGIME_LOOKBACKS,
    REGIME_QUANTILES,
    RESOLUTIONS,
    ROOTS,
    SELECTION_SHARE,
    SERIAL_BELOW_COMBINATION_BARS,
    SIZE_FIXED,
    SIZING_CONFLUENCE,
    SIZING_HIGH_QUANTITIES,
    SIZING_QUANTITIES,
    SIZING_SYMMETRIC,
    SLIPPAGE_TICKS,
    SPEC_VARIANTS,
    STALL_BARS,
    STRATUM_SETS,
    STRUCTURE_TRAIL_BARS,
    STRUCTURE_TRAIL_CUSHIONS,
    STRUCTURE_TRAIL_WIDE_BARS,
    STRUCTURE_TRAIL_WIDE_CUSHIONS,
    UNFILTERED,
    VARIANT_SETS,
    VARIANTS,
    VOLUME_BASELINE_SESSIONS,
    VOLUME_FORMS,
    VOLUME_ROLLING_BARS,
    VOLUME_TAILS,
    Cuts,
    RegimeCut,
    SizingCut,
    Variant,
    VolumeCut,
    calibrate,
    calibrate_volume,
    check_confluence_request,
    check_volume_request,
    confluence_arms,
    confluence_cuts,
    db_path,
    early_exit_arms,
    elastic_ladder,
    fit_regime,
    fit_volume,
    grids_for,
    insidebartrailing_confluence_arms,
    insidebartrailing_sizing_high_variants,
    insidebartrailing_sizing_variants,
    insidebartrailing_structure_end_variants,
    insidebartrailing_structure_variants,
    insidebartrailing_variants,
    named_forms,
    orb_geometry_ranges,
    orb_resolutions,
    planned_combinations,
    quantile_pair,
    raw_volume_cuts,
    run_point,
    sizing_arms,
    sizing_cuts,
    sizing_cuts_path,
    sizing_high_arms,
    strata,
    structure_trail_arms,
    structure_trail_end_arms,
    swept_on,
    tail_pairs,
    tier2_arms,
    tier3_arms,
    unstored,
    variants_for,
    volume_series,
    windows,
    workers_for,
)

if TYPE_CHECKING:
    from nqbt import context
    from nqbt.instruments import Instrument

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


def base_as[P: archetypes.Params](variant: Variant, cls: type[P]) -> P:
    """Return ``variant``'s base parameters, checked to be a ``cls``."""
    base: archetypes.Params = variant.base
    assert isinstance(base, cls), f"{variant.name} is built on {type(base).__name__}, not {cls.__name__}"

    return base


def all_variants() -> list[Variant]:
    """Build every variant of every archetype, on both roots."""
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
    """A held-out pass takes one dimension at a time, so each needs its own name.

    A set that only reached a dimension through ``context`` could not be run without the other
    two.
    """
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
    """The real guard: ``Grid`` refuses dead axes and each parameter class refuses an impossible combination.

    Constructing every one of them is what catches a grid that would fail an hour into a run.
    """
    for variant in all_variants():
        for _, grid in grids_for(variant, ALL_STRATA):
            assert len(grid) == variant.sized()


def test_every_combination_of_every_grid_is_constructible() -> None:
    """``combinations()`` builds the parameter objects.

    A validator that refuses a corner of the product -- identical crossover averages, both
    ElasticBand signal exits at once -- fails here rather than mid-sweep.
    """
    for variant in all_variants():
        _, grid = grids_for(variant, UNFILTERED)[0]
        assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_every_base_carries_its_roots_real_costs() -> None:
    for name, build in VARIANTS.items():
        for root, commission in COMMISSION.items():
            for variant in build(root):
                assert variant.base.commission_per_contract == pytest.approx(commission), (name, root)
                assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS), (name, root)


def test_every_costed_root_is_a_registered_instrument() -> None:
    """A typo in the table reaches the sweep as a bare KeyError, one root into a long run."""
    for root in COMMISSION:
        assert instruments.get_instrument(root).symbol == root


@pytest.mark.parametrize(("micro", "full_size"), [("MNQ", "NQ"), ("MES", "ES"), ("MGC", "GC")])
def test_each_micro_is_costed_below_the_root_it_micros(micro: str, full_size: str) -> None:
    """One figure for both flatters the full-size root.

    The point value differs tenfold between a micro and its sibling, and the commission does
    not.
    """
    assert instruments.get_instrument(micro).point_value < instruments.get_instrument(full_size).point_value
    assert COMMISSION[micro] < COMMISSION[full_size]


def test_every_root_is_costed_at_the_index_figure_for_its_size() -> None:
    """A micro carries MNQ's figure and a full-size root NQ's.

    ``docs/roadmap.md`` § "Commission on the roots beyond NQ".
    """
    for root, commission in COMMISSION.items():
        index_root: str = "NQ" if instruments.get_instrument(root).mini_equivalent == 1.0 else "MNQ"
        assert commission == COMMISSION[index_root], root


def test_the_crossover_variants_sweep_disjoint_stop_axes() -> None:
    """``dead_axes`` cannot see that a swing stop ignores ``atr_stop_multiple``.

    The two geometries are separate variants rather than one grid -- ``docs/roadmap.md`` §M27.
    """
    atr, swing = VARIANTS["EmaCrossover"]("MNQ")
    assert base_as(atr, EmaCrossoverParams).use_atr_stop
    assert not base_as(swing, EmaCrossoverParams).use_atr_stop
    assert "atr_stop_multiple" in atr.axes
    assert "atr_stop_multiple" not in swing.axes
    assert "swing_lookback" in swing.axes
    assert "swing_lookback" not in atr.axes


def test_the_squeeze_variants_split_the_stop_axes_and_share_the_squeeze() -> None:
    """Each stop reads an axis the other ignores, and ``dead_axes`` cannot see either."""
    variants = VARIANTS["SqueezeBreakout"]("MNQ")
    by_stop = {base_as(v, SqueezeBreakoutParams).stop_mode: v for v in variants}
    assert set(by_stop) == {ORB_STOP_OPPOSITE, ORB_STOP_ATR}
    for variant in variants:
        reads_atr = base_as(variant, SqueezeBreakoutParams).stop_mode == ORB_STOP_ATR
        assert ("atr_stop_multiple" in variant.axes) is reads_atr, variant.name
        assert ("stop_offset_ticks" in variant.axes) is not reads_atr, variant.name
        assert {"squeeze_form", "squeeze_period", "squeeze_below", "direction"} <= set(variant.axes)


def test_every_elastic_ladder_is_distinct_and_ends_in_a_runner() -> None:
    """A tuple is not a sweepable axis, so each ladder is its own variant.

    Two that matched would run the same combinations twice under different names.
    """
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


def test_each_archetype_gets_its_own_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A convention since ``_append_or_create`` learned to widen, and still what the campaign ran on.

    The report and holdout tools go on finding one file per archetype.
    """
    monkeypatch.setattr("tools.campaign_sweep.CAMPAIGN_DIR", tmp_path / "campaign")
    paths = {name: db_path(name) for name in VARIANTS}
    assert len(set(paths.values())) == len(VARIANTS)
    assert all(path.parent.exists() for path in paths.values())


# -- the worker count ----------------------------------------------------------------------


def test_a_sweep_call_below_the_threshold_stays_in_process() -> None:
    assert workers_for(1, SERIAL_BELOW_COMBINATION_BARS - 1, 8) == 1
    assert workers_for(4, 1_000_000, 16) == 1


def test_a_sweep_call_at_the_threshold_gets_the_workers_it_asked_for() -> None:
    assert workers_for(1, SERIAL_BELOW_COMBINATION_BARS, 8) == 8
    assert workers_for(432, 1_000_000, 16) == 16


def test_the_same_combination_count_is_pooled_on_fine_bars_and_not_on_coarse_ones() -> None:
    """A combination costs roughly in proportion to the bars it runs over.

    A pool's overhead does not shrink with it, so a count alone cannot say which side of the
    threshold a call is.
    """
    assert workers_for(64, 1_000_000, 8) == 8
    assert workers_for(64, 70_000, 8) == 1


def test_a_call_over_no_bars_stays_in_process() -> None:
    assert workers_for(2304, 0, 8) == 1


def test_a_request_is_passed_through_in_joblibs_own_convention() -> None:
    """``-1`` is every core to joblib, so it has to reach joblib rather than be read as a count."""
    assert workers_for(1, SERIAL_BELOW_COMBINATION_BARS, -1) == -1
    assert workers_for(1, SERIAL_BELOW_COMBINATION_BARS, 1) == 1


def unswept(grids: list[sweep.Grid]) -> list[tuple[pd.DataFrame, dict[int, pd.DataFrame]]]:
    """Return what ``sweep.sweep_grids`` returns for ``grids``, without running anything."""
    return [
        (
            pd.DataFrame(
                {
                    "combo_id": range(len(grid)),
                    "trades": [0] * len(grid),
                    "profit_factor": [math.nan] * len(grid),
                },
            ),
            {},
        )
        for grid in grids
    ]


def test_a_points_cells_share_one_sweep_call_whose_total_size_picks_the_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One call per point rather than per (variant x stratum).

    Cells too small to pool on their own are pooled together once their combinations add up.
    """
    (wide,) = VARIANTS["InsideBar"]("MNQ")
    narrow = [replace(wide, name=f"narrow {n}", axes={"atr_multiplier": [5.0, 10.0]}) for n in range(60)]
    frame = pd.DataFrame(index=range(SERIAL_BELOW_COMBINATION_BARS // 100))
    called: list[tuple[list[int], int]] = []

    def record(
        _data: context.Dataset, grids: list[sweep.Grid], _instrument: Instrument, *, n_jobs: int
    ) -> list[tuple[pd.DataFrame, dict[int, pd.DataFrame]]]:
        called.append(([len(grid) for grid in grids], n_jobs))

        return unswept(grids)

    monkeypatch.setattr("tools.campaign_sweep.CAMPAIGN_DIR", tmp_path / "campaign")
    monkeypatch.setattr("nqbt.context.prepare", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("nqbt.results.save_sweep", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(sweep, "sweep_grids", record)
    run_point(frame, narrow[:1], "MNQ", 5, "selection", 1, UNFILTERED, NO_CUTS, n_jobs=8)
    run_point(frame, narrow, "MNQ", 5, "selection", 2, UNFILTERED, NO_CUTS, n_jobs=8)

    assert called == [([2], 1), ([2] * 60, 8)]
    assert 2 * len(frame) < SERIAL_BELOW_COMBINATION_BARS <= 2 * 60 * len(frame)


VOLUME_WINDOWS = {
    "volume_forms": tuple(volume.VolumeForm),
    "volume_rolling_bars": [VOLUME_ROLLING_BARS],
    "volume_baseline_sessions": [VOLUME_BASELINE_SESSIONS],
}
"""What the three form and window flags parse to when none of them is passed: the one series
per form, at the windows every stored row holds."""


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
        **VOLUME_WINDOWS,
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
    """Build a one-minute frame whose held-out half is a straight line, which scores 1.0 everywhere.

    A fit that reached past the selection window would put the upper threshold at 1.0 and say so.
    """
    rng = np.random.default_rng(seed)
    close = 16000.0 + np.cumsum(rng.normal(0.0, 5.0, n))
    cut = math.floor(n * SELECTION_SHARE)
    close[cut:] = close[cut - 1] + np.arange(1, n - cut + 1, dtype=np.float64)

    return pd.DataFrame({"close": close})


def calibrated_args(**overrides: object) -> argparse.Namespace:
    """Build the arguments ``fit_regime`` reads, at one resolution so ``resample`` is a pass-through."""
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
    """A cell rather than an axis.

    The thresholds move with the lookback, and a sweep crosses its axes, so pairing them any
    other way runs cells that are not comparable.
    """
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
    """Two cell sizes land in one database.

    A name that carried only the lookback would put two different cuts under one stratum --
    ``docs/roadmap.md`` §M31.
    """
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
        **VOLUME_WINDOWS,
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    assert planned_combinations(args) == per_stratum * len(regime.Regime) * 2


# -- the opening range, whose windows are not expressible at every resolution ---------------


def test_every_variant_but_the_opening_ranges_runs_at_every_resolution() -> None:
    """The exception is the point.

    A session-anchored range needs the bar size to divide both its 930-minute anchor and its
    window -- ``docs/roadmap.md`` §M28.
    """
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
    """The real guard: a claimed resolution whose range grid refuses to build fails here.

    Otherwise it would fail an hour into a run.
    """
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
        **VOLUME_WINDOWS,
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
            assert isinstance(combination, OpeningRangeParams)
            assert combination.direction in (trades.LONG, trades.SHORT)


# -- the volume form and the cut it is read at -----------------------------------------------


def volume_bars(sessions_wanted: int = 30, seed: int = 7) -> pd.DataFrame:
    """Build whole sessions carrying volume, so a bar-of-session baseline has sessions to be taken over."""
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
    """Build the arguments ``fit_volume`` reads, at one resolution so ``resample`` is a pass-through."""
    return argparse.Namespace(
        **{"resolutions": [1], "volume_quantiles": VOLUME_TAILS, **VOLUME_WINDOWS, **overrides}
    )


def test_the_volume_form_group_is_one_cell_per_form_tail_and_state() -> None:
    """§M27 swept three cells of one form; the axis itself is the form crossed with the cut."""
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS, volume_series()))
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
    """A cross of form x window would run duplicate combinations that ``dead_axes`` cannot see.

    It knows one inert value per toggle and this axis is inert at two forms -- ``docs/roadmap.md``
    §M10.2.
    """
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
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS, volume_series()))
    assert list(strata(CORE, cuts)) == list(strata(CORE))


def test_each_form_is_fitted_against_its_own_distribution() -> None:
    """The point of the fit: one raw pair sits at a different percentile under each form.

    HEAVY is a different population under each -- ``docs/roadmap.md`` §M27.8.
    """
    fitted = calibrate_volume(volume_bars(), 1, ((0.20, 0.80),), volume_series())
    heavy = {cut.series.form: cut.heavy_above for cut in fitted}
    assert len(set(heavy.values())) == len(volume.VolumeForm)


def test_every_volume_form_grid_in_the_campaign_can_be_built() -> None:
    """The fitted thresholds reach a real parameter class, which validates them on construction."""
    cuts = Cuts(volume=calibrate_volume(volume_bars(), 1, VOLUME_TAILS, volume_series()))
    for variant in all_variants():
        for _, grid in grids_for(variant, VOLUME_FORMS, cuts):
            assert len(grid) == variant.sized()


def test_the_volume_fit_reads_the_selection_window_and_never_the_holdout() -> None:
    """Fitting on the whole series would leak the holdout into the definition of the stratum."""
    bars = volume_bars()
    bars.iloc[math.floor(len(bars) * SELECTION_SHARE) :, list(bars.columns).index("volume")] *= 100.0
    selection_fit = fit_volume(bars, volume_args())[1]
    whole_fit = calibrate_volume(bars, 1, VOLUME_TAILS, volume_series())
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
        **VOLUME_WINDOWS,
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    cells = len(volume.VolumeForm) * len(VOLUME_TAILS) * len(volume.VolumeState)
    assert planned_combinations(args) == per_stratum * cells


# -- the two volume windows, one cell per rung -----------------------------------------------

ROLLING = volume.VolumeForm.ROLLING


def test_a_rolling_ladder_is_one_series_per_rung_and_no_duplicate_per_bar_one() -> None:
    """``volume.key`` drops the window from the two forms that do not read it.

    A ladder crossed with every form would otherwise build one identical per-bar series per
    rung.
    """
    series = volume_series(tuple(volume.VolumeForm), [10, 30, 90])
    rolling = [key for key in series if key.form is ROLLING]
    assert [key.rolling_bars for key in rolling] == [10, 30, 90]
    assert len(series) == len(rolling) + len(volume.VolumeForm) - 1
    assert len(set(series)) == len(series)


def test_a_baseline_ladder_is_one_series_per_rung_under_every_form() -> None:
    """Unlike the rolling window, every form divides by a bar-of-session baseline."""
    series = volume_series(tuple(volume.VolumeForm), [VOLUME_ROLLING_BARS], [10, 20, 40])
    assert len(series) == len(volume.VolumeForm) * 3
    assert {key.baseline_sessions for key in series} == {10, 20, 40}


def test_two_rungs_of_one_form_are_separable_in_the_results_table() -> None:
    """A rung is a cell, so the stratum name has to carry it -- ``docs/roadmap.md`` §M31."""
    names = {
        VolumeCut(key, 0.5, 2.0, tails=(0.20, 0.80)).name
        for key in volume_series((ROLLING,), [10, 90], [10, 40])
    }
    assert names == {
        "rolling_10_10 q=0.20/0.80",
        "rolling_10_40 q=0.20/0.80",
        "rolling_90_10 q=0.20/0.80",
        "rolling_90_40 q=0.20/0.80",
    }


def test_each_rung_is_fitted_against_its_own_distribution() -> None:
    """Why a rung is a cell and not an axis.

    The window moves the ratio's distribution, so the threshold pair moves with it and a crossed
    axis would read a cut fitted for another rung.
    """
    fitted = calibrate_volume(volume_bars(), 1, ((0.20, 0.80),), volume_series((ROLLING,), [5, 60]))
    heavy = {cut.series.rolling_bars: cut.heavy_above for cut in fitted}
    assert len(set(heavy.values())) == len(heavy)


def test_a_rolling_ladder_reaches_the_grid_at_the_rung_its_cell_names() -> None:
    cuts = Cuts(
        volume=calibrate_volume(volume_bars(), 1, ((0.20, 0.80),), volume_series((ROLLING,), [10, 90]))
    )
    for name, extra in strata(VOLUME_FORMS, cuts):
        rung = int(name.split("@rolling_")[1].split("_")[0])
        assert extra["volume_rolling_bars"] == [rung], name


def test_a_window_ladder_without_a_fitted_cut_is_refused() -> None:
    """A raw pair admits a different share of bars at each window.

    The rungs could not be read against each other -- ``.claude/rules/sweep-and-context.md``.
    """
    with pytest.raises(SystemExit, match="different share of bars"):
        check_volume_request(volume_args(volume_quantiles=(), volume_rolling_bars=[10, 30]))

    with pytest.raises(SystemExit, match="different share of bars"):
        check_volume_request(volume_args(volume_quantiles=(), volume_baseline_sessions=[10, 20]))


def test_a_rolling_ladder_without_the_rolling_form_is_refused_rather_than_run_flat() -> None:
    """The ``dead_axes`` blind spot, made loud.

    ``volume.key`` would collapse every rung onto one series, and the pass would look like a
    ladder while running one.
    """
    with pytest.raises(SystemExit, match="ROLLING in --volume-forms"):
        check_volume_request(
            volume_args(volume_forms=(volume.VolumeForm.PER_BAR,), volume_rolling_bars=[10, 90])
        )


def test_narrowing_the_forms_without_a_fitted_cut_is_refused() -> None:
    """An unfitted run's cells are the stored campaign's own, and the flag would be ignored."""
    with pytest.raises(SystemExit, match="leave every form in"):
        check_volume_request(volume_args(volume_quantiles=(), volume_forms=(ROLLING,)))


def test_a_window_the_form_is_degenerate_at_is_refused_by_name() -> None:
    with pytest.raises(SystemExit, match=r"a one-bar window is VolumeForm\.PER_BAR"):
        check_volume_request(volume_args(volume_rolling_bars=[1, 30]))

    with pytest.raises(SystemExit, match="baseline must span"):
        check_volume_request(volume_args(volume_baseline_sessions=[2, 20]))


def test_the_default_run_is_the_one_series_per_form_every_stored_row_holds() -> None:
    """So that a pass naming neither flag reproduces §M30 rather than appending beside it."""
    check_volume_request(volume_args())
    assert volume_series() == tuple(
        volume.key(form, VOLUME_ROLLING_BARS, VOLUME_BASELINE_SESSIONS) for form in volume.VolumeForm
    )


def test_the_named_forms_are_deduplicated_into_enum_order() -> None:
    assert named_forms(["SESSION_TO_DATE", "PER_BAR", "PER_BAR"]) == (
        volume.VolumeForm.PER_BAR,
        volume.VolumeForm.SESSION_TO_DATE,
    )


def test_planned_combinations_counts_a_window_ladders_cells() -> None:
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
        volume_forms=(ROLLING,),
        volume_rolling_bars=[10, 90],
        volume_baseline_sessions=[VOLUME_BASELINE_SESSIONS],
    )
    per_stratum = sum(variant.sized() for variant in VARIANTS["InsideBar"]("MNQ"))
    cells = 2 * len(VOLUME_TAILS) * len(volume.VolumeState)
    assert planned_combinations(args) == per_stratum * cells


# -- the §M27.3 narrow re-sweep --------------------------------------------------------------


def test_the_narrow_set_is_the_baseline_and_the_one_cell_it_asks_about() -> None:
    """Four regime cells nobody is asking about are four more comparisons -- §M27.3."""
    assert [name for name, _ in strata(NARROW)] == [UNFILTERED, "regime=DIRECTIONAL"]


def test_the_directional_group_is_calibrated_like_the_full_regime_one() -> None:
    """The prerequisite §M27.3 inherits from [#200].

    The raw 0.5 cut is not one filter, so a group yielding a single regime cell has to be split
    per lookback too.
    """
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
    """``directional`` is a subset of ``regime``.

    Including it in ``all`` would run one cell twice and report it as two.
    """
    assert DIRECTIONAL not in STRATUM_SETS[ALL_STRATA]
    assert len(list(strata(ALL_STRATA))) == 1 + sum(len(names) for names in EVERY_STATE.values())


def test_the_narrow_variants_cross_the_bracket_pair_and_nothing_else() -> None:
    """§M27 moved the stop across three values and could not move the target by a tick.

    The re-sweep varies exactly those two so the crossed pair is the only thing changing.
    """
    for variant in NARROW_VARIANTS["InsideBar"]("MNQ"):
        assert set(variant.axes) == {"tp_multiplier", "atr_multiplier"}
        assert variant.sized() == len(NARROW_TP) * len(NARROW_ATR)


def test_the_narrow_grid_contains_the_geometry_the_campaign_actually_ran() -> None:
    """Without §M27's own cell in the grid there is nothing to read the re-sweep against."""
    assert 1.0 in NARROW_TP, "the hardcoded 1x ATR target the campaign was stuck with"
    assert {5.0, 10.0, 20.0} <= set(NARROW_ATR), "§M27's three stop distances"


def test_each_narrow_variant_runs_at_exactly_one_resolution() -> None:
    """A ``Variant`` carries one base and the entry differs between bar sizes.

    The resolutions are what separates them.
    """
    variants = NARROW_VARIANTS["InsideBar"]("MNQ")
    assert all(len(variant.resolutions) == 1 for variant in variants)
    assert [minutes for variant in variants for minutes in variant.resolutions] == list(NARROW_ENTRY)


def test_the_narrow_set_runs_at_every_resolution_the_campaign_split() -> None:
    """One minute has no selection window to read an entry from -- §M44."""
    assert set(NARROW_ENTRY) == set(RESOLUTIONS) - {1}


def test_the_narrow_entry_is_held_at_a_value_and_never_swept() -> None:
    for variant in NARROW_VARIANTS["InsideBar"]("MNQ"):
        assert set(variant.axes).isdisjoint(NARROW_ENTRY[variant.resolutions[0]])


def test_each_narrow_variant_runs_its_own_resolutions_entry() -> None:
    for variant in NARROW_VARIANTS["InsideBar"]("MNQ"):
        for field, value in NARROW_ENTRY[variant.resolutions[0]].items():
            assert getattr(variant.base, field) == value


def test_the_narrow_variants_carry_the_roots_real_costs() -> None:
    for root, commission in COMMISSION.items():
        for variant in NARROW_VARIANTS["InsideBar"](root):
            assert variant.base.commission_per_contract == commission
            assert variant.base.slippage_ticks == SLIPPAGE_TICKS


def test_every_narrow_variant_is_named_for_the_reading_tools_to_filter_on() -> None:
    """The rows land in the campaign's own database, so the variant name is what separates them from §M27's.

    ``--variant narrow`` on every reading tool.
    """
    assert {variant.name for variant in NARROW_VARIANTS["InsideBar"]("MNQ")} == {NARROW}
    assert NARROW not in {variant.name for variant in all_variants()}


def test_the_campaign_grid_is_untouched_by_the_re_sweep() -> None:
    """§M27's stored rows and the code that produced them must not drift apart.

    A re-sweep is its own variant set rather than an axis added to the campaign's.
    """
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
    """§M28.1's deferral.

    Dropped for a fraction axis whose top value reproduces the opposite-extreme stop exactly.
    """
    variants = ORB_VARIANTS["OpeningRange"]("MNQ")

    assert {base_as(variant, OpeningRangeParams).stop_mode for variant in variants} == {ORB_STOP_FRACTION}
    assert all("atr_stop_multiple" not in variant.axes for variant in variants)
    assert all(1.0 in variant.axes["stop_range_fraction"] for variant in variants)


def test_the_re_sweep_carries_every_anchor_and_every_entry_mechanism() -> None:
    """§M28 deferred both and §M28.1 left both deferred; this is where they arrive."""
    variants = ORB_VARIANTS["OpeningRange"]("MNQ")
    keys = {
        (
            base_as(variant, OpeningRangeParams).anchor_minutes,
            base_as(variant, OpeningRangeParams).window_minutes,
        )
        for variant in variants
    }

    assert keys == set(ORB_RANGES.values())
    assert {base_as(variant, OpeningRangeParams).entry_mode for variant in variants} == {
        ORB_ENTRY_BREAKOUT,
        ORB_ENTRY_FADE,
        ORB_ENTRY_RETEST,
    }


def test_each_entry_mechanism_sweeps_only_the_offsets_it_reads() -> None:
    """The blind spot the entry mode is a variant dimension rather than an axis to avoid.

    ``retest_offset_ticks`` under a breakout would run identical combinations silently.
    """
    for variant in ORB_VARIANTS["OpeningRange"]("MNQ"):
        reads_a_limit = base_as(variant, OpeningRangeParams).entry_mode == ORB_ENTRY_RETEST
        assert ("retest_offset_ticks" in variant.axes) is reads_a_limit
        assert ("entry_offset_ticks" in variant.axes) is not reads_a_limit
        waits = base_as(variant, OpeningRangeParams).entry_mode != ORB_ENTRY_BREAKOUT
        assert ("break_confirm_ticks" in variant.axes) is waits


def test_the_campaign_grid_is_untouched_by_the_opening_ranges_re_sweep() -> None:
    """§M28.1's stored rows were produced by ``VARIANTS``, so the new axes go in their own set."""
    campaign = VARIANTS["OpeningRange"]("MNQ")

    assert all("stop_range_fraction" not in variant.axes for variant in campaign)
    assert {base_as(variant, OpeningRangeParams).entry_mode for variant in campaign} == {ORB_ENTRY_BREAKOUT}
    assert {base_as(variant, OpeningRangeParams).anchor_minutes for variant in campaign} == {
        sessionrange.CASH_OPEN_MINUTES
    }


# -- the §M28.5 fade re-run --------------------------------------------------------


def test_the_fades_re_run_states_the_fades_own_thesis_as_its_stratum() -> None:
    """``regime=DIRECTIONAL`` is the *breakout's* hypothesis.

    Running a fade inside it would be stating the wrong one in advance -- ``docs/roadmap.md``
    §M28.5.
    """
    assert [name for name, _ in strata(ORB_FADE)] == [UNFILTERED, "regime=CONSOLIDATING"]
    assert [name for name, _ in strata(CONSOLIDATING)] == ["regime=CONSOLIDATING"]


def test_the_fades_stop_axis_reaches_below_the_one_that_parked_it_and_keeps_its_endpoint() -> None:
    """A shared endpoint is what makes the two runs comparable rather than adjacent.

    §M28.2's tightest fade cell has to exist in this grid too, and everything else has to be
    tighter.
    """
    assert min(ORB_TIGHT_FRACTIONS) < min(ORB_FRACTIONS)
    assert max(ORB_TIGHT_FRACTIONS) == min(ORB_FRACTIONS)
    for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.axes["stop_range_fraction"] == ORB_TIGHT_FRACTIONS
        assert base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION


def test_the_fades_re_run_holds_its_entry_axes_at_exactly_what_parked_it() -> None:
    """The bracket is the only thing that moved.

    That is what § "Parked is not abandoned" asks a re-run to be able to say.
    """
    _, parked = ORB_ENTRIES["entry=fade"]

    for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ"):
        assert base_as(variant, OpeningRangeParams).entry_mode == ORB_ENTRY_FADE
        assert {key: variant.axes[key] for key in parked} == parked


def test_only_one_of_the_fades_target_ladders_reaches_the_middle_of_the_range() -> None:
    """§M28.2's ladder is kept so the two runs share it; the midpoint is the new half."""
    ladders = {
        base_as(variant, OpeningRangeParams).target_width_multiples
        for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ")
        if base_as(variant, OpeningRangeParams).target_mode == ORB_TARGET_WIDTH
    }

    assert ladders == set(ORB_FADE_LADDERS.values())
    assert [0.5 in ladder for ladder in sorted(ladders, key=len)] == [False, True]


def test_the_fades_re_run_is_one_variant_per_range_and_target_scheme() -> None:
    """The R ladder is not repeated once per width ladder, which would be the same grid twice."""
    variants = ORB_FADE_VARIANTS["OpeningRange"]("MNQ")

    assert len(variants) == len(ORB_RANGES) * (len(ORB_FADE_LADDERS) + 1)
    assert len({variant.name for variant in variants}) == len(variants)
    assert sum(
        base_as(variant, OpeningRangeParams).target_mode == ORB_TARGET_R for variant in variants
    ) == len(ORB_RANGES)


# -- the §M28.7 rejection run ------------------------------------------------------


def test_the_rejection_run_and_the_fades_share_one_stratum_tuple() -> None:
    """Both are reversion entries, so both are asked about the range that holds.

    One hypothesis stated once rather than two copies that could drift apart.
    """
    assert STRATUM_SETS[ORB_REJECTION] is STRATUM_SETS[ORB_FADE]
    assert [name for name, _ in strata(ORB_REJECTION)] == [UNFILTERED, "regime=CONSOLIDATING"]


def test_the_rejection_run_holds_the_fades_bracket_at_exactly_what_it_swept() -> None:
    """The entry is the only thing that moved between §M28.5 and this.

    That is what makes the two comparable as entries rather than as two unrelated grids.
    """
    bracket = {"stop_range_fraction", "stop_offset_ticks"}
    fade = {variant.name.split(" entry=")[0]: variant for variant in ORB_FADE_VARIANTS["OpeningRange"]("MNQ")}

    for variant in ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ"):
        against = fade[variant.name.split(" entry=")[0]]
        assert base_as(variant, OpeningRangeParams).entry_mode == ORB_ENTRY_REJECTION
        assert base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION
        assert {key: variant.axes[key] for key in bracket} == {key: against.axes[key] for key in bracket}


def test_the_rejection_sweeps_no_break_confirmation_and_a_zero_offset() -> None:
    """It waits for no break, so the fade's arming axis would be inert.

    And its limit may rest on the extreme itself, which a stop entry cannot --
    ``docs/roadmap.md`` §M28.7.
    """
    for variant in ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ"):
        assert "break_confirm_ticks" not in variant.axes
        assert variant.axes["entry_offset_ticks"] == ORB_REJECTION_OFFSETS

    assert min(ORB_REJECTION_OFFSETS) == 0
    assert 0 not in ORB_ENTRIES["entry=fade"][1]["entry_offset_ticks"], "a stop entry cannot"


def test_the_rejection_grid_is_the_same_size_as_the_fades() -> None:
    """One axis swapped for another of the same length.

    A difference in the results is not a difference in how many chances each entry was given.
    """
    rejection = ORB_REJECTION_VARIANTS["OpeningRange"]("MNQ")
    fade = ORB_FADE_VARIANTS["OpeningRange"]("MNQ")

    assert len(rejection) == len(fade) == len(ORB_RANGES) * (len(ORB_FADE_LADDERS) + 1)
    assert sum(v.sized() * len(v.resolutions) for v in rejection) == sum(
        v.sized() * len(v.resolutions) for v in fade
    )


def test_the_parked_orb_grid_is_untouched_by_the_fades_re_run() -> None:
    """§M28.2's stored rows were produced by ``ORB_VARIANTS``.

    The tighter axis goes in its own set for the reason that one did.
    """
    assert all(
        variant.axes["stop_range_fraction"] == ORB_FRACTIONS
        for variant in ORB_VARIANTS["OpeningRange"]("MNQ")
    )
    assert variants_for(ORB_FADE) is ORB_FADE_VARIANTS
    assert variants_for(ORB_REJECTION) is ORB_REJECTION_VARIANTS
    assert variants_for(ORB) is ORB_VARIANTS


# -- the §M28.8 geometry run -------------------------------------------------------


def stored_orb_variants() -> list[Variant]:
    """Return every OpeningRange variant the three stored runs were produced by."""
    return [
        variant
        for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS)
        for variant in build["OpeningRange"]("MNQ")
    ]


def test_the_one_hour_cash_range_is_in_the_swept_set_at_every_resolution() -> None:
    """[#258]'s gap: the only 60-minute window swept was anchored at the European open.

    "the first hour of the New York session" had never been run.
    """
    hour = (sessionrange.CASH_OPEN_MINUTES, 60)

    assert hour not in set(ORB_RANGES.values()), "premise gone; the gap has been filled elsewhere"
    assert hour in set(orb_geometry_ranges().values())
    assert orb_resolutions(*hour) == RESOLUTIONS


def test_the_geometry_cross_keeps_every_cell_the_session_leaves_room_to_trade() -> None:
    """The cut is the session's own.

    A range that is not complete before the phase the forced flat falls in has only that phase
    to trade in -- ``docs/roadmap.md`` §M28.8.
    """
    latest = sessionrange.anchor_for(timeofday.FORCED_EXIT_PHASE)
    anchors = {sessionrange.anchor_for(phase) for phase in timeofday.SessionPhase}
    ranges = orb_geometry_ranges()

    assert set(ranges.values()) == {
        (anchor, window) for anchor in anchors for window in ORB_GEOMETRY_WINDOWS if anchor + window <= latest
    }
    # The close phase is the one anchor no window fits after.
    assert not [name for name in ranges if name.startswith("close+")]


def test_the_geometry_cross_contains_every_range_the_stored_runs_measured() -> None:
    """A shared cell is what makes the length axis comparable to §M28.2 rather than adjacent to it.

    That is why the overnight span is a window here -- §M28.5's endpoint argument.
    """
    assert set(ORB_RANGES.values()) <= set(orb_geometry_ranges().values())


def test_no_geometry_variant_can_collide_with_a_stored_one_in_the_same_database() -> None:
    """Rows are separated by variant name alone, and ``campaign_holdout`` pairs the two windows one-to-one.

    So a duplicated name would pair a new row against a stored one.
    """
    geometry = ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ")
    names = {variant.name for variant in geometry}

    assert len(names) == len(geometry)
    assert not names & {variant.name for variant in stored_orb_variants()}


def test_the_geometry_run_states_its_stratum_before_it_runs() -> None:
    """One cell rather than the reversion pair.

    The question is geometric, and every entry has already been asked its own context question
    -- ``docs/roadmap.md`` §M28.8.
    """
    assert [name for name, _ in strata(ORB_GEOMETRY)] == [UNFILTERED]
    assert variants_for(ORB_GEOMETRY) is ORB_GEOMETRY_VARIANTS


def test_every_entry_keeps_the_bracket_its_own_campaign_swept() -> None:
    """A single bracket across all four would move two things at once on two of them.

    A fade's stop runs outward from the extreme it enters at where a breakout's runs inward.
    """
    wide = {ORB_ENTRY_BREAKOUT, ORB_ENTRY_RETEST}

    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        assert base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION
        if base_as(variant, OpeningRangeParams).entry_mode in wide:
            assert variant.axes["stop_range_fraction"] == ORB_FRACTIONS
            assert "stop_offset_ticks" not in variant.axes
            continue

        assert variant.axes["stop_range_fraction"] == ORB_TIGHT_FRACTIONS
        assert variant.axes["stop_offset_ticks"] == [2, 8]


def test_every_entry_sweeps_only_the_offsets_it_reads() -> None:
    """``ORB_ENTRIES``' own reason, carried to the fourth mode.

    ``dead_axes`` cannot see an axis that is inert under a mode, so an inert one runs identical
    combinations silently.
    """
    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        reads_a_limit = base_as(variant, OpeningRangeParams).entry_mode == ORB_ENTRY_RETEST
        assert ("retest_offset_ticks" in variant.axes) is reads_a_limit
        assert ("entry_offset_ticks" in variant.axes) is not reads_a_limit
        waits = base_as(variant, OpeningRangeParams).entry_mode in (ORB_ENTRY_FADE, ORB_ENTRY_RETEST)
        assert ("break_confirm_ticks" in variant.axes) is waits


def test_the_geometry_run_reproduces_a_stored_variant_wherever_the_two_share_a_cell() -> None:
    """The five stored ranges are re-run at exactly the parameters that produced their rows.

    The new table shares cells with the old one rather than running beside it.
    """
    stored = [
        variant
        for variant in stored_orb_variants()
        if base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION
    ]
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
    """The real guard: a claimed resolution whose range grid refuses to build fails here.

    Otherwise it would fail an hour into a run.
    """
    for variant in ORB_GEOMETRY_VARIANTS["OpeningRange"]("MNQ"):
        assert variant.resolutions, variant.name
        for minutes in variant.resolutions:
            for _, grid in grids_for(variant, UNFILTERED):
                for anchor, window in grid.required_context().range_keys:
                    sessionrange.validate_key(anchor, window, minutes)


def test_the_stored_orb_grids_are_untouched_by_the_geometry_run() -> None:
    """§M28.1's, §M28.2's and §M28.5's rows were each produced by their own set.

    A crossed anchor goes in a sixth rather than into any of them.
    """
    for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS):
        anchors = {
            base_as(variant, OpeningRangeParams).anchor_minutes for variant in build["OpeningRange"]("MNQ")
        }
        assert anchors <= {anchor for anchor, _ in ORB_RANGES.values()}


def test_the_hoisted_target_schemes_are_what_the_stored_re_sweep_swept() -> None:
    """``ORB_TARGETS`` is one dict where two builders held the same literal.

    The geometry run reads it so that a stored cell and a new one cannot drift apart.
    """
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
    """A treatment measured against a stored run is measured against a different pass.

    This one is on the same bars in the same sweep -- ``docs/roadmap.md`` M28.10.
    """
    controls = [
        v
        for v in follow_through_variants()
        if base_as(v, OpeningRangeParams).follow_through_scaling == ORB_SCALE_NONE
    ]

    assert len(controls) == len(ORB_FOLLOW_THROUGH_RANGES)
    assert all(name.endswith("scale=off") for name in (v.name for v in controls))


def test_the_control_and_every_treatment_differ_by_the_scaling_alone() -> None:
    """The property the comparison rests on: one field moves and the axes are identical."""
    by_range: dict[int, list[Variant]] = {}
    for variant in follow_through_variants():
        by_range.setdefault(base_as(variant, OpeningRangeParams).window_minutes, []).append(variant)

    for window, variants in by_range.items():
        control = next(
            v for v in variants if base_as(v, OpeningRangeParams).follow_through_scaling == ORB_SCALE_NONE
        )
        for treatment in variants:
            assert treatment.axes == control.axes, treatment.name
            assert treatment.resolutions == control.resolutions, treatment.name
            unscaled = replace(
                treatment.base,
                follow_through_scaling=ORB_SCALE_NONE,
                follow_through_sessions=base_as(control, OpeningRangeParams).follow_through_sessions,
            )
            assert unscaled == control.base, (window, treatment.name)


def test_the_lookback_is_a_variant_dimension_rather_than_an_axis() -> None:
    """``follow_through_sessions`` is inert at ORB_SCALE_NONE, and ``dead_axes`` knows one off value per axis.

    So crossing the two would run the control once per lookback in silence.
    """
    for variant in follow_through_variants():
        assert "follow_through_sessions" not in variant.axes
        assert "follow_through_scaling" not in variant.axes


def test_every_scaled_variant_states_its_geometry_in_a_width_the_scale_can_reach() -> None:
    """The params class refuses an R target or an opposite-extreme stop under a scaling mode.

    A variant set that built one would fail at construction rather than run.
    """
    for variant in follow_through_variants():
        assert base_as(variant, OpeningRangeParams).target_mode == ORB_TARGET_WIDTH
        assert base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION


def test_the_run_is_confined_to_the_ranges_the_null_separated() -> None:
    """M28.8's gate 3 puts the excess at 15 and 30 minutes from the cash open and nowhere else.

    This asks its question where there is an edge to lose.
    """
    windows = {base_as(variant, OpeningRangeParams).window_minutes for variant in follow_through_variants()}
    anchors = {base_as(variant, OpeningRangeParams).anchor_minutes for variant in follow_through_variants()}

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
    """The context is derived from the grid.

    A lookback nothing declared would raise in the loop rather than be built once.
    """
    for variant in follow_through_variants():
        for _, grid in grids_for(variant, UNFILTERED):
            declared = grid.required_context().follow_through_sessions
            if base_as(variant, OpeningRangeParams).follow_through_scaling == ORB_SCALE_NONE:
                assert declared == (), variant.name
                continue

            assert declared == (base_as(variant, OpeningRangeParams).follow_through_sessions,), variant.name


# -- the M28.11 bracket ladder run --------------------------------------------------


def bracket_variants() -> list[Variant]:
    return ORB_BRACKET_VARIANTS["OpeningRange"]("MNQ")


def test_the_bracket_run_states_its_stratum_before_it_runs() -> None:
    """One cell, as the geometry and follow-through runs have.

    The question is about the bracket's size rather than about the context it is traded in.
    """
    assert [name for name, _ in strata(ORB_BRACKET)] == [UNFILTERED]
    assert variants_for(ORB_BRACKET) is ORB_BRACKET_VARIANTS


def test_the_stop_ladder_extends_the_stored_axis_instead_of_replacing_it() -> None:
    """[#262]'s premise: 1.0 was the last value and the winning one, so the axis was truncated.

    Every stored fraction is re-run at exactly its own value, and the new ones sit past it.
    """
    assert ORB_LADDER_FRACTIONS[: len(ORB_FRACTIONS)] == ORB_FRACTIONS
    assert max(ORB_FRACTIONS) == 1.0
    assert [f for f in ORB_LADDER_FRACTIONS if f > 1.0]
    assert sorted(ORB_LADDER_FRACTIONS) == ORB_LADDER_FRACTIONS


def test_a_stop_past_the_range_width_is_legal_rather_than_refused() -> None:
    """The whole ladder rests on it.

    Past 1.0 the stop sits outside the range entirely, and a params class that refused it would
    fail the run rather than the axis.
    """
    for fraction in ORB_LADDER_FRACTIONS:
        params = OpeningRangeParams(stop_mode=ORB_STOP_FRACTION, stop_range_fraction=fraction)

        assert params.stop_range_fraction == fraction


def test_the_width_ladder_is_a_variant_dimension_rather_than_an_axis() -> None:
    """A ladder is a tuple and tuples are not sweepable, which is why no ORB campaign varied it.

    ``_orb_further_targets`` hands over the parameter default and no axis reaches it.
    """
    ladders = {base_as(variant, OpeningRangeParams).target_width_multiples for variant in bracket_variants()}

    assert ladders == set(ORB_WIDTH_LADDERS.values())
    for variant in bracket_variants():
        assert "target_width_multiples" not in variant.axes
        assert "target_mode" not in variant.axes


def test_the_ladder_every_stored_run_used_is_one_cell_of_the_swept_set() -> None:
    """What makes this an extension of the stored table rather than a run beside it.

    The parameter default is in the set, so the new rows share a target scheme with the old
    ones.
    """
    assert OpeningRangeParams().target_width_multiples in set(ORB_WIDTH_LADDERS.values())


def test_the_no_target_arm_leaves_every_leg_to_the_forced_flat() -> None:
    """The arm that reproduces M28.9's ``(nan, nan)`` measurement.

    M28.9 measured ``(nan, nan)`` against the default and reported it winning on the selection
    window and losing on the holdout.
    """
    runner = ORB_WIDTH_LADDERS["target=runner"]

    assert all(math.isnan(level) for level in runner)
    assert [name for name, ladder in ORB_WIDTH_LADDERS.items() if all(math.isnan(x) for x in ladder)] == [
        "target=runner",
    ]


def test_every_ladder_has_a_leg_for_each_target_the_order_can_fill() -> None:
    """A ladder longer than ``order_quantity`` raises at construction.

    A set built with one would fail the whole run rather than the cell.
    """
    for variant in bracket_variants():
        assert len(base_as(variant, OpeningRangeParams).target_levels) <= variant.base.order_quantity, (
            variant.name
        )


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
    """M28.8's gate 3 puts the excess at 15 and 30 minutes from the cash open and nowhere else.

    An axis is extended where there is an edge to lose -- ``ORB_FOLLOW_THROUGH_RANGES``.
    """
    assert {window for _, window in ORB_BRACKET_RANGES.values()} == {15, 30}
    assert {anchor for anchor, _ in ORB_BRACKET_RANGES.values()} == {sessionrange.CASH_OPEN_MINUTES}
    assert set(ORB_BRACKET_RANGES.values()) == set(ORB_FOLLOW_THROUGH_RANGES.values())


def test_the_bracket_run_sweeps_the_breakouts_own_offset_and_no_other() -> None:
    """One entry, held at exactly what M28.2 and M28.10 swept it on.

    The bracket is the only thing that moved -- and an offset the mode does not read runs
    identical combinations.
    """
    for variant in bracket_variants():
        assert base_as(variant, OpeningRangeParams).entry_mode == ORB_ENTRY_BREAKOUT
        assert base_as(variant, OpeningRangeParams).stop_mode == ORB_STOP_FRACTION
        assert base_as(variant, OpeningRangeParams).target_mode == ORB_TARGET_WIDTH
        assert variant.axes["entry_offset_ticks"] == [1, 4]
        assert "retest_offset_ticks" not in variant.axes
        assert "break_confirm_ticks" not in variant.axes


def test_the_bracket_run_reproduces_the_unscaled_control_at_the_cell_they_share() -> None:
    """M28.10's ``scale=off`` arm is this geometry at the stored fraction ladder.

    The two tables meet rather than run beside each other -- which is what makes the extension
    readable against the stored figure.
    """
    controls = {
        base_as(variant, OpeningRangeParams).window_minutes: variant
        for variant in ORB_FOLLOW_THROUGH_VARIANTS["OpeningRange"]("MNQ")
        if base_as(variant, OpeningRangeParams).follow_through_scaling == ORB_SCALE_NONE
    }
    matched = 0
    for variant in bracket_variants():
        if (
            base_as(variant, OpeningRangeParams).target_width_multiples
            != OpeningRangeParams().target_width_multiples
        ):
            continue

        control = controls[base_as(variant, OpeningRangeParams).window_minutes]

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
    """M28.1's through M28.10's rows were each produced by their own set.

    An extended axis goes in a seventh rather than into any of them.
    """
    for build in (VARIANTS, ORB_VARIANTS, ORB_FADE_VARIANTS, ORB_REJECTION_VARIANTS, ORB_GEOMETRY_VARIANTS):
        for variant in build["OpeningRange"]("MNQ"):
            fractions = variant.axes.get("stop_range_fraction", [])

            assert all(float(fraction) <= 1.0 for fraction in fractions), variant.name


def test_the_bracket_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in ORB_BRACKET_VARIANTS["OpeningRange"](root):
            assert variant.base.commission_per_contract == COMMISSION[root]
            assert variant.base.slippage_ticks == SLIPPAGE_TICKS


# -- the §M26.9 volume run -------------------------------------------------------------------


def volume_variants(root: str = "MNQ") -> list[Variant]:
    """Return the control and the treatment of the volume run, in that order."""
    return ELASTIC_VOLUME_VARIANTS["ElasticBand"](root)


def test_the_volume_run_states_its_strata_before_it_runs() -> None:
    """The volume dimension re-cut on its own distribution, read against the unfiltered baseline.

    The baseline is read in the same pass, rather than against a cell chosen once the table is
    in.
    """
    fitted = tuple(VolumeCut(key, 0.7, 1.5, tails=pair) for key in volume_series() for pair in VOLUME_TAILS)
    raw = [name for name, _ in strata(ELASTIC_VOLUME, Cuts(volume=raw_volume_cuts()))]
    cut = [name for name, _ in strata(ELASTIC_VOLUME, Cuts(volume=fitted))]

    assert raw[0] == UNFILTERED
    assert cut[0] == UNFILTERED
    assert len(raw) == 1 + len(volume_series()) * len(volume.VolumeState)
    assert len(cut) == 1 + len(volume_series()) * len(VOLUME_TAILS) * len(volume.VolumeState)


def test_the_volume_run_carries_its_own_control_shape_in_the_same_pass() -> None:
    """A stored ``shape=any`` row came out of a different grid.

    Pairing against it would compare two runs rather than two arms -- ``docs/roadmap.md``
    §M26.5.
    """
    assert set(ELASTIC_VOLUME_SHAPES.values()) == {SHAPE_ANY, SHAPE_REVERSAL}
    assert {base_as(variant, ElasticBandParams).signal_shape for variant in volume_variants()} == {
        SHAPE_ANY,
        SHAPE_REVERSAL,
    }


def test_the_control_and_the_treatment_differ_by_the_shape_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over this pair.

    Every other field of the base and every axis is shared, so a paired cell differs by the
    requirement only.
    """
    control, treatment = volume_variants()

    assert (
        replace(control.base, signal_shape=base_as(treatment, ElasticBandParams).signal_shape)
        == treatment.base
    )
    assert control.axes == treatment.axes


def test_the_volume_run_holds_the_three_axes_the_shape_campaign_spent() -> None:
    """The axes §M26.5 measured as dead or as duplicates are narrowed -- ``docs/roadmap.md`` §M26.5."""
    for variant in volume_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert "min_bars_outside" not in variant.axes
        assert base_as(variant, ElasticBandParams).min_one_sided_bars == 0
        assert (
            base_as(variant, ElasticBandParams).target_stretch_levels
            == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]
        )


def test_every_volume_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    """§M26.4 established that the Bollinger source does not survive a holdout.

    The question here is the volume and not the channel.
    """
    for variant in volume_variants():
        assert base_as(variant, ElasticBandParams).band_source == BAND_VWAP
        assert base_as(variant, ElasticBandParams).target_mode == TARGET_STRETCH
        assert variant.axes["stop_mode"] == [STOP_ATR, STOP_SWING, STOP_CATASTROPHE]


def test_the_ladder_is_readable_back_off_every_volume_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in volume_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]


def test_no_volume_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing separating them.

    ``campaign_holdout`` would pair two campaigns' windows together.
    """
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


# -- the §M33 channel run --------------------------------------------------------------------


def channel_variants(root: str = "MNQ") -> list[Variant]:
    """Return every arm of the channel run: both channels crossed with both shapes."""
    return ELASTIC_CHANNEL_VARIANTS["ElasticBand"](root)


def test_the_channel_run_asks_the_volume_question_over_the_same_cells() -> None:
    """The point of the run is that the cells are §M26.9's and the grid is not.

    A cell whose sign flips flipped because of the channel.
    """
    assert STRATUM_SETS[ELASTIC_CHANNEL] == STRATUM_SETS[ELASTIC_VOLUME]


def test_the_channel_run_crosses_both_channels_with_both_shapes() -> None:
    """Four arms rather than two, with §M26.9's pair among them as the control side."""
    variants = channel_variants()

    assert len(variants) == len(ELASTIC_CHANNEL_SOURCES) * len(ELASTIC_VOLUME_SHAPES)
    assert {base_as(variant, ElasticBandParams).band_source for variant in variants} == {
        BAND_VWAP,
        BAND_BOLLINGER,
    }
    assert {base_as(variant, ElasticBandParams).signal_shape for variant in variants} == {
        SHAPE_ANY,
        SHAPE_REVERSAL,
    }


def test_every_channel_arm_differs_from_another_by_one_field_alone() -> None:
    """The claim the campaign rests on.

    Two arms sharing a shape differ by the channel, and two sharing a channel differ by the
    shape -- so nothing else can explain a sign.
    """
    for variant in channel_variants():
        for other in channel_variants():
            if variant.name == other.name:
                continue

            differ = {
                field
                for field in ("band_source", "signal_shape")
                if getattr(variant.base, field) != getattr(other.base, field)
            }
            swapped = replace(
                variant.base,
                band_source=base_as(other, ElasticBandParams).band_source,
                signal_shape=base_as(other, ElasticBandParams).signal_shape,
            )

            assert differ
            assert swapped == other.base
            assert variant.axes == other.axes


def test_the_vwap_arm_reproduces_the_stored_volume_run_exactly() -> None:
    """§M26.9's two variants are this set's VWAP arms, parameter for parameter.

    The stored rows cross-check the new ones -- the shape ``ORB_LADDER_FRACTIONS`` has for
    §M28.11.
    """
    stored = {base_as(variant, ElasticBandParams).signal_shape: variant for variant in volume_variants()}

    matched = 0
    for variant in channel_variants():
        if base_as(variant, ElasticBandParams).band_source != BAND_VWAP:
            continue

        twin = stored[base_as(variant, ElasticBandParams).signal_shape]
        assert variant.base == twin.base
        assert variant.axes == twin.axes
        matched += 1

    assert matched == len(stored)


def test_the_channel_run_pins_the_bollinger_period_rather_than_sweeping_it() -> None:
    """``band_period`` is live under Bollinger and inert under VWAP.

    Sweeping it would make the Bollinger arm a best-of-three and break the one-thing-differs
    property.
    """
    for variant in channel_variants():
        assert "band_period" not in variant.axes
        assert base_as(variant, ElasticBandParams).band_period == ELASTIC_CHANNEL_PERIOD


def test_the_channel_run_holds_the_bracket_the_volume_run_held() -> None:
    """Holding the *same* bracket is what lets the two campaigns be read against each other."""
    for variant in channel_variants():
        assert variant.axes == ELASTIC_VOLUME_BRACKET
        assert (
            base_as(variant, ElasticBandParams).target_stretch_levels
            == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]
        )
        assert base_as(variant, ElasticBandParams).target_mode == TARGET_STRETCH


def test_the_stored_volume_grid_is_untouched_by_naming_the_bracket() -> None:
    """Naming the axes both sets share must not move §M26.9's own grid, whose rows are stored."""
    for variant in volume_variants():
        assert variant.axes == {
            "entry_std": [2.0, 2.5, 3.0],
            "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
            "max_hold_bars": [0, 30],
        }


def test_neither_set_hands_out_the_bracket_constant_itself() -> None:
    """Both builders copy it, so nothing downstream can mutate the axes of every set at once.

    Within one builder call the variants share one dict, as every set in this module does;
    ``grids_for`` copies before it adds a stratum, so nothing mutates it.
    """
    per_set = [
        [variant.axes for variant in build()]
        for build in (channel_variants, volume_variants, channel_variants)
    ]

    assert all(axes is not ELASTIC_VOLUME_BRACKET for axes in chain.from_iterable(per_set))
    assert all(axes == ELASTIC_VOLUME_BRACKET for axes in chain.from_iterable(per_set))
    assert len({id(axes[0]) for axes in per_set}) == len(per_set)


def test_no_channel_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing separating them.

    ``campaign_holdout`` would pair two campaigns' windows together.
    """
    stored: set[str] = set()
    for build in (
        VARIANTS,
        ELASTIC_SHAPE_VARIANTS,
        ELASTIC_VOLUME_VARIANTS,
        ELASTIC_RECOVERY_VARIANTS,
        ELASTIC_BAND_STOP_VARIANTS,
    ):
        stored |= {variant.name for variant in build["ElasticBand"]("MNQ")}

    assert not stored & {variant.name for variant in channel_variants()}


def test_the_ladder_is_readable_back_off_every_channel_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in channel_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET]


def test_every_channel_variant_grid_can_be_built_at_every_cell() -> None:
    """A cell that cannot be built fails here rather than a quarter of an hour into the run."""
    for variant in channel_variants():
        for _, grid in grids_for(variant, ELASTIC_CHANNEL, Cuts(volume=raw_volume_cuts())):
            assert len(grid) == variant.sized()
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_channel_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in channel_variants(root):
            assert variant.base.commission_per_contract == pytest.approx(COMMISSION[root])
            assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS)


def test_variants_for_selects_the_channel_grid() -> None:
    assert variants_for(ELASTIC_CHANNEL) is ELASTIC_CHANNEL_VARIANTS


# -- the §M26.6 recovery run -----------------------------------------------------------------


def recovery_variants(root: str = "MNQ") -> list[Variant]:
    """Return every arm of the recovery run, the two controls first."""
    return ELASTIC_RECOVERY_VARIANTS["ElasticBand"](root)


def test_the_recovery_run_states_its_stratum_before_it_runs() -> None:
    """The trigger is the thing being measured, so the pass adds no context cell to cross it with.

    ``docs/roadmap.md`` §M26.6.
    """
    assert [name for name, _ in strata(ELASTIC_RECOVERY, NO_CUTS)] == [UNFILTERED]


def test_the_recovery_run_carries_both_controls_in_the_same_pass() -> None:
    """A stored row came out of a different grid.

    Pairing against it would compare two runs rather than two arms. The question is whether
    waiting for the reaction beats reading it off a bar still outside, so requiring nothing is
    not the only control it needs.
    """
    triggers = {trigger for trigger, _, _ in ELASTIC_RECOVERY_ARMS.values()}
    shapes = {shape for trigger, shape, _ in ELASTIC_RECOVERY_ARMS.values() if trigger == TRIGGER_EXTENDED}

    assert triggers == {TRIGGER_EXTENDED, TRIGGER_RECOVERY}
    assert shapes == {SHAPE_ANY, SHAPE_REVERSAL}


def test_every_recovery_arm_differs_from_the_control_by_the_entry_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over these arms.

    Every other field of the base and every axis is shared, so a paired cell differs by the
    entry rule only.
    """
    control, *rest = recovery_variants()
    for arm in rest:
        rebased = replace(
            control.base,
            entry_trigger=base_as(arm, ElasticBandParams).entry_trigger,
            recovery_fraction=base_as(arm, ElasticBandParams).recovery_fraction,
            signal_shape=base_as(arm, ElasticBandParams).signal_shape,
        )

        assert rebased == arm.base
        assert control.axes == arm.axes


def test_the_recovery_run_keeps_the_run_length_the_shapes_made_a_duplicate() -> None:
    """The recovery trigger reads the run at the bar *before* the signal.

    It is the one entry under which ``min_bars_outside`` is live -- ``docs/roadmap.md`` §M26.6.
    """
    for variant in recovery_variants():
        assert variant.axes["min_bars_outside"] == [1, 2]


def test_the_recovery_run_drops_the_axis_the_shape_campaign_measured_as_dead() -> None:
    """§M26.5: ``min_one_sided_bars``'s low end is a dead value and its high end is a cost."""
    for variant in recovery_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert base_as(variant, ElasticBandParams).min_one_sided_bars == 0
        assert (
            base_as(variant, ElasticBandParams).target_stretch_levels
            == ELASTIC_LADDERS[ELASTIC_RECOVERY_TARGET]
        )


def test_every_recovery_depth_is_inside_the_band_and_the_loosest_is_its_edge() -> None:
    """A depth of 1.0 is the band edge itself; 0.5 is left out as near-empty -- ``docs/roadmap.md`` §M26.6."""
    depths = {depth for trigger, _, depth in ELASTIC_RECOVERY_ARMS.values() if trigger == TRIGGER_RECOVERY}

    assert depths == {1.0, 0.9, 0.75}
    assert all(0.0 < depth <= 1.0 for depth in depths)


def test_every_recovery_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    """§M26.4 established that the Bollinger source does not survive a holdout.

    The question here is the entry and not the channel.
    """
    for variant in recovery_variants():
        assert base_as(variant, ElasticBandParams).band_source == BAND_VWAP
        assert base_as(variant, ElasticBandParams).target_mode == TARGET_STRETCH
        assert variant.axes["stop_mode"] == [STOP_ATR, STOP_SWING, STOP_CATASTROPHE]


def test_the_ladder_is_readable_back_off_every_recovery_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in recovery_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_RECOVERY_TARGET]


def test_no_recovery_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing separating them.

    ``campaign_holdout`` would pair two campaigns' windows together.
    """
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
    """Return every arm of the band-stop run, the three existing stops first."""
    return ELASTIC_BAND_STOP_VARIANTS["ElasticBand"](root)


def test_the_band_stop_run_states_its_stratum_before_it_runs() -> None:
    """The stop is the thing being measured, so the pass adds no context cell to cross it with.

    ``docs/roadmap.md`` §M26.8.
    """
    assert [name for name, _ in strata(ELASTIC_BAND_STOP, NO_CUTS)] == [UNFILTERED]


def test_the_band_stop_run_carries_the_three_existing_stops_in_the_same_pass() -> None:
    """A stored row came out of a different grid.

    Pairing against it would compare two runs rather than two arms.
    """
    modes = {mode for mode, _ in ELASTIC_BAND_STOP_ARMS.values()}

    assert modes == {STOP_ATR, STOP_SWING, STOP_CATASTROPHE, STOP_BAND}


def test_every_band_stop_arm_differs_from_its_control_by_the_stop_alone() -> None:
    """Which is what makes ``campaign_paired`` readable over these arms.

    Every other field of the base and every axis is shared, so a paired cell differs by where
    the stop went.
    """
    control, *rest = band_stop_variants()
    for arm in rest:
        rebased = replace(
            control.base,
            stop_mode=base_as(arm, ElasticBandParams).stop_mode,
            band_stop_std=base_as(arm, ElasticBandParams).band_stop_std,
            signal_shape=base_as(arm, ElasticBandParams).signal_shape,
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
    """§M26.5 measured an excess for the reversal shape and none for the control.

    The pair bounds whether a stop scheme is being ranked or the bars under it are.
    """
    assert set(ELASTIC_BAND_STOP_SHAPES.values()) == {SHAPE_ANY, SHAPE_REVERSAL}
    shapes = {base_as(variant, ElasticBandParams).signal_shape for variant in band_stop_variants()}

    assert shapes == {SHAPE_ANY, SHAPE_REVERSAL}
    assert len(band_stop_variants()) == len(ELASTIC_BAND_STOP_ARMS) * len(ELASTIC_BAND_STOP_SHAPES)


def test_the_band_stop_run_drops_the_axis_the_shape_campaign_measured_as_dead() -> None:
    """§M26.5: ``min_one_sided_bars``'s low end is a dead value and its high end is a cost.

    ``min_bars_outside`` stays, because §M26.9 dropped it for the reversal shape alone and half
    these arms carry the control instead.
    """
    for variant in band_stop_variants():
        assert "min_one_sided_bars" not in variant.axes
        assert variant.axes["min_bars_outside"] == [1, 2]
        assert base_as(variant, ElasticBandParams).min_one_sided_bars == 0
        assert (
            base_as(variant, ElasticBandParams).target_stretch_levels
            == ELASTIC_LADDERS[ELASTIC_BAND_STOP_TARGET]
        )


def test_every_band_stop_variant_reads_the_source_the_shape_campaign_left_standing() -> None:
    for variant in band_stop_variants():
        assert base_as(variant, ElasticBandParams).band_source == BAND_VWAP
        assert base_as(variant, ElasticBandParams).target_mode == TARGET_STRETCH
        assert variant.axes["entry_std"] == [2.0, 2.5, 3.0]


def test_the_ladder_is_readable_back_off_every_band_stop_variant_name() -> None:
    """The ladder is a tuple and so not a stored column; the name is all a reading tool has."""
    for variant in band_stop_variants():
        assert elastic_ladder(variant.name) == ELASTIC_LADDERS[ELASTIC_BAND_STOP_TARGET]


def test_no_band_stop_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is the only thing separating them.

    ``campaign_holdout`` would pair two campaigns' windows together.
    """
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


# -- the [#279] inverted signal ------------------------------------------------------------


def invert_variants(root: str = "MNQ") -> list[Variant]:
    """Return every arm of the inverted-signal run, both sides on R first."""
    return ELASTIC_INVERT_VARIANTS["ElasticBand"](root)


def test_the_invert_run_states_its_strata_before_it_runs_and_they_are_every_dimension() -> None:
    assert variants_for(ELASTIC_INVERT) is ELASTIC_INVERT_VARIANTS
    assert [name for name, _ in strata(ELASTIC_INVERT)] == [name for name, _ in strata(ALL_STRATA)]


def test_the_invert_arms_are_both_sides_on_r_then_each_side_on_its_own_ladder() -> None:
    """``docs/findings/m26-7-inverted-signal-preregistration.md``."""
    sides = [
        (base_as(variant, ElasticBandParams).invert_signal, variant.name) for variant in invert_variants()
    ]
    assert sides == [
        (False, "invert=off target=R"),
        (True, "invert=on target=R"),
        (False, "invert=off target=0.0s"),
        (True, "invert=on target=+1.0s"),
        (True, "invert=on target=+2.0s"),
    ]


def test_every_invert_arm_is_the_fade_on_r_but_for_its_side_and_its_target() -> None:
    """Every axis is shared, so each pair holds the same combinations on the same bars."""
    for root in COMMISSION:
        fade_on_r, *others = invert_variants(root)
        control = base_as(fade_on_r, ElasticBandParams)
        assert (control.band_source, control.signal_shape) == (BAND_VWAP, SHAPE_ANY)
        for variant in others:
            base = base_as(variant, ElasticBandParams)
            assert variant.axes == fade_on_r.axes == ELASTIC_INVERT_AXES
            unsided = replace(
                base,
                invert_signal=False,
                target_mode=TARGET_R,
                target_stretch_levels=control.target_stretch_levels,
            )
            assert unsided == control, variant.name


def test_an_arm_on_r_runs_the_default_r_ladder_because_a_rebuild_restores_that_one() -> None:
    """The R ladder is not a stored column, so ``campaign_shortlist.rebuild`` returns the default."""
    default = ElasticBandParams().target_r_multiples
    on_r = [variant for variant in invert_variants() if ELASTIC_TARGET_R in variant.name.split()]
    assert len(on_r) == 2
    for variant in on_r:
        base = base_as(variant, ElasticBandParams)
        assert base.target_mode == TARGET_R
        np.testing.assert_array_equal(base.target_r_multiples, default)


def test_the_ladder_is_readable_back_off_every_invert_variant_on_stretch_targets() -> None:
    """An inverted level is past the close, so it sits above zero where the fade's is the midline."""
    for variant in invert_variants():
        base = base_as(variant, ElasticBandParams)
        if base.target_mode != TARGET_STRETCH:
            continue

        assert elastic_ladder(variant.name) == base.target_stretch_levels
        first = base.target_stretch_levels[0]
        assert first > 0.0 if base.invert_signal else first == 0.0


def test_no_invert_variant_can_collide_with_a_stored_elastic_one() -> None:
    """One database holds every ElasticBand run and the variant name is all that separates them."""
    stored = {
        variant.name
        for builders in (
            VARIANTS,
            ELASTIC_SHAPE_VARIANTS,
            ELASTIC_VOLUME_VARIANTS,
            ELASTIC_CHANNEL_VARIANTS,
            ELASTIC_RECOVERY_VARIANTS,
            ELASTIC_BAND_STOP_VARIANTS,
        )
        for variant in builders["ElasticBand"]("MNQ")
    }
    names = {variant.name for variant in invert_variants()}

    assert not stored & names
    assert len(names) == len(invert_variants())


def test_every_invert_variant_grid_can_be_built_at_every_cell() -> None:
    """A cell that cannot be built fails here rather than an hour into the run."""
    for variant in invert_variants():
        for _, grid in grids_for(variant, ELASTIC_INVERT, NO_CUTS):
            assert len(grid) == variant.sized()
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_invert_run_carries_the_roots_real_costs() -> None:
    for root in COMMISSION:
        for variant in invert_variants(root):
            assert variant.base.commission_per_contract == pytest.approx(COMMISSION[root])
            assert variant.base.slippage_ticks == pytest.approx(SLIPPAGE_TICKS)


# -- the [#313] trail on the slow average --------------------------------------------------


def trail_variants(root: str = "MNQ") -> list[Variant]:
    """Return both arms of the trail run, the fixed stop first."""
    return EMAPULLBACK_TRAIL_VARIANTS["EmaPullback"](root)


def test_the_trail_run_states_its_strata_before_it_runs_and_they_are_the_campaigns() -> None:
    """The control reproduces §M35's stored rows, so it runs every cell they were run in and no other."""
    assert variants_for(EMAPULLBACK_TRAIL) is EMAPULLBACK_TRAIL_VARIANTS
    assert [name for name, _ in strata(EMAPULLBACK_TRAIL)] == [name for name, _ in strata(ALL_STRATA)]


def test_the_trail_arms_differ_from_the_stored_campaign_by_the_trail_alone() -> None:
    """Every axis and every other field of the base is §M35's.

    Which is what makes the control a reproduction and ``campaign_paired`` readable over the two.
    """
    for root in COMMISSION:
        (campaign,) = VARIANTS["EmaPullback"](root)
        control, treatment = trail_variants(root)

        assert control.base == campaign.base
        assert treatment.base == replace(campaign.base, trail_ma_stop=True, trail_on_slow=True)
        assert control.axes == campaign.axes == treatment.axes


def test_no_trail_variant_can_collide_with_a_stored_emapullback_one() -> None:
    """One database holds every EmaPullback run and the variant name is all that separates them."""
    stored = {variant.name for variant in VARIANTS["EmaPullback"]("MNQ")}
    names = [variant.name for variant in trail_variants()]

    assert not stored & set(names)
    assert names == ["stop=slow trail=off", "stop=slow trail=slow"]


def test_every_trail_variant_grid_can_be_built_at_every_cell() -> None:
    """A grid that swept an axis the slow trail leaves unread is refused here, not an hour into the run."""
    for variant in trail_variants():
        for _, grid in grids_for(variant, EMAPULLBACK_TRAIL):
            assert len(grid) == variant.sized()
            assert conditions_free_of_the_third_grid(grid)


def conditions_free_of_the_third_grid(grid: sweep.Grid) -> bool:
    """Check neither arm builds the trail's own grid: one never trails and the other trails on ``slow``."""
    periods = {period for _, period in grid.required_context().ma_keys}

    return periods == set(grid.axes["fast_period"]) | set(grid.axes["slow_period"])


# -- §M53's trail on an average of its own ---------------------------------------------------

THIRD_GRID_AXES = ("trail_ma_kind", "trail_ma_period", "trail_offset_ticks")


def ma_trail_variants(root: str = "MNQ") -> list[Variant]:
    """Return all three arms of the third-average run: the fixed stop, the slow trail, the third average."""
    return EMAPULLBACK_MA_TRAIL_VARIANTS["EmaPullback"](root)


def pullback_combinations(variant: Variant) -> list[EmaPullbackParams]:
    """Return every combination of ``variant``'s unfiltered grid, checked to be EmaPullback's."""
    combinations: list[EmaPullbackParams] = []
    for combination in grids_for(variant, UNFILTERED)[0][1].combinations():
        assert isinstance(combination, EmaPullbackParams)
        combinations.append(combination)

    return combinations


def test_the_ma_trail_run_states_its_strata_before_it_runs_and_they_are_the_campaigns() -> None:
    assert variants_for(EMAPULLBACK_MA_TRAIL) is EMAPULLBACK_MA_TRAIL_VARIANTS
    assert [name for name, _ in strata(EMAPULLBACK_MA_TRAIL)] == [name for name, _ in strata(ALL_STRATA)]


def test_the_fixed_and_slow_arms_are_m37s_under_new_names() -> None:
    """Same base and axes as §M37's two arms, so each can be checked against §M37's rows on the same bars."""
    for root in COMMISSION:
        fixed, on_slow, _ = ma_trail_variants(root)
        m37_fixed, m37_slow = trail_variants(root)

        assert (fixed.base, fixed.axes) == (m37_fixed.base, m37_fixed.axes)
        assert (on_slow.base, on_slow.axes) == (m37_slow.base, m37_slow.axes)


def test_the_third_average_arm_adds_emacrossovers_trail_grid_and_nothing_else() -> None:
    """Every §M35 axis is shared, so ``campaign_paired`` keys on them and takes the median over the trail."""
    for root in COMMISSION:
        (campaign,) = VARIANTS["EmaPullback"](root)
        crossover_trail = next(
            variant for variant in SPEC_VARIANTS["EmaCrossover"](root) if variant.name == "stop=atr trail=on"
        )
        *_, on_third = ma_trail_variants(root)

        assert on_third.base == replace(campaign.base, trail_ma_stop=True, trail_on_slow=False)
        assert {axis: values for axis, values in on_third.axes.items() if axis not in THIRD_GRID_AXES} == (
            campaign.axes
        )
        assert {axis: on_third.axes[axis] for axis in THIRD_GRID_AXES} == {
            axis: crossover_trail.axes[axis] for axis in THIRD_GRID_AXES
        }


def test_no_ma_trail_variant_can_collide_with_any_other_sets_emapullback_one() -> None:
    """One database holds every EmaPullback run and the variant name is all that separates them.

    The sizing set is left out: it needs a fitted cuts file to build, and its names carry ``size=``.
    """
    stored = {
        variant.name
        for which in VARIANT_SETS - {EMAPULLBACK_MA_TRAIL, CONFLUENCE_SIZING}
        if "EmaPullback" in variants_for(which)
        for variant in variants_for(which)["EmaPullback"]("MNQ")
    }
    names = [variant.name for variant in ma_trail_variants()]

    assert not stored & set(names)
    assert names == ["stop=slow trail2=off", "stop=slow trail2=slow", "stop=slow trail2=ma"]


def test_every_ma_trail_variant_grid_can_be_built() -> None:
    """A grid sweeping an axis its arm leaves unread is refused here, not an hour into the run.

    Unfiltered only: a stratum adds a filter the trail never reads, and §M37's test builds the two
    repeated arms at every cell. The third average's 23 cells take most of a minute to build.
    """
    for variant in ma_trail_variants():
        assert len(grids_for(variant, UNFILTERED)[0][1]) == variant.sized()


def test_the_third_average_arm_holds_a_twin_of_every_slow_trail_it_can_reach() -> None:
    """Where the third average is the slow one at the stop's offset, the two arms trail the same stop.

    ``test_trailing_on_the_slow_average_is_the_third_grid_pointed_at_it`` pins that they trade
    identically, so those rows have to agree exactly -- the pre-registration's reproduction check.
    """
    _, on_slow, on_third = ma_trail_variants()
    default = EmaPullbackParams()
    reachable = set(product(on_third.axes["trail_ma_kind"], on_third.axes["trail_ma_period"]))
    twins = [
        replace(
            combination,
            trail_on_slow=True,
            trail_ma_kind=default.trail_ma_kind,
            trail_ma_period=default.trail_ma_period,
            trail_offset_ticks=default.trail_offset_ticks,
        )
        for combination in pullback_combinations(on_third)
        if (combination.trail_ma_kind, combination.trail_ma_period, combination.trail_offset_ticks)
        == (combination.slow_kind, combination.slow_period, combination.stop_offset_ticks)
    ]
    slow_trails = [
        combination
        for combination in pullback_combinations(on_slow)
        if (combination.slow_kind, combination.slow_period) in reachable
    ]

    assert slow_trails
    assert sorted(map(dataclasses.astuple, twins)) == sorted(map(dataclasses.astuple, slow_trails))


# -- the [#311] confirmation entry ---------------------------------------------------------


def confirm_variants(root: str = "MNQ") -> list[Variant]:
    """Return all three arms of the confirmation run, the market entry first."""
    return EMAPULLBACK_CONFIRM_VARIANTS["EmaPullback"](root)


def test_the_confirmation_run_states_its_strata_before_it_runs_and_they_are_the_campaigns() -> None:
    assert variants_for(EMAPULLBACK_CONFIRM) is EMAPULLBACK_CONFIRM_VARIANTS
    assert [name for name, _ in strata(EMAPULLBACK_CONFIRM)] == [name for name, _ in strata(ALL_STRATA)]


def test_the_confirmation_arms_differ_from_the_stored_campaign_by_the_entry_and_the_held_kinds() -> None:
    """Every other axis and field is §M35's, so the arms pair cell for cell under ``campaign_paired``."""
    for root in COMMISSION:
        (campaign,) = VARIANTS["EmaPullback"](root)
        market, one_bar, three_bars = confirm_variants(root)
        shared = {
            axis: values for axis, values in campaign.axes.items() if axis not in EMAPULLBACK_HELD_KINDS
        }

        assert market.base == campaign.base
        assert one_bar.base == replace(campaign.base, confirm_entry=True)
        assert three_bars.base == replace(campaign.base, confirm_entry=True, entry_order_lifetime_bars=3)
        assert market.axes == one_bar.axes == three_bars.axes == shared
        assert (
            base_as(campaign, EmaPullbackParams).fast_kind,
            base_as(campaign, EmaPullbackParams).slow_kind,
        ) == ("ema", "ema")


def test_no_confirmation_variant_can_collide_with_a_stored_emapullback_one() -> None:
    stored = {variant.name for variant in VARIANTS["EmaPullback"]("MNQ")} | {
        variant.name for variant in EMAPULLBACK_TRAIL_VARIANTS["EmaPullback"]("MNQ")
    }
    names = [variant.name for variant in confirm_variants()]

    assert not stored & set(names)
    assert names == [
        "stop=slow entry=market",
        "stop=slow entry=confirm life=1",
        "stop=slow entry=confirm life=3",
    ]


def test_every_confirmation_variant_grid_can_be_built_at_every_cell() -> None:
    """A grid sweeping an axis the entry leaves unread is refused here, not an hour into the run."""
    for variant in confirm_variants():
        for _, grid in grids_for(variant, EMAPULLBACK_CONFIRM):
            assert len(grid) == variant.sized()
            assert conditions_free_of_the_third_grid(grid)


SOURCE = Path(campaign_sweep.__file__)
FINDINGS = SOURCE.parent.parent / "docs" / "findings"


def prepared_price_bases() -> list[str]:
    """List every ``price_basis`` the campaign's own ``context.prepare`` calls state."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    return [
        ast.unparse(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("context.prepare")
        for keyword in node.keywords
        if keyword.arg == "price_basis"
    ]


def loaded_series() -> list[str]:
    """List every ``splice.load_continuous`` call the campaign makes, as written."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    return [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("splice.load_continuous")
    ]


def test_the_campaign_runs_on_the_prices_that_traded() -> None:
    """A rule reading an absolute level is refused on any other basis, so this is part of the plan."""
    assert prepared_price_bases() == ["context.PriceBasis.RAW"]
    assert loaded_series() == ["splice.load_continuous(root)"]


def test_the_findings_readme_names_the_basis_the_campaign_actually_ran_on() -> None:
    """It said back-adjusted, which reads as EmaCrossover's round-number arm never having run ([#334])."""
    rows = (FINDINGS / "README.md").read_text(encoding="utf-8").splitlines()
    (instruments,) = [row for row in rows if row.startswith("| **Instruments**")]

    assert "raw" in instruments
    assert "back-adjusted" not in instruments


def test_no_findings_file_calls_the_campaigns_series_back_adjusted() -> None:
    """Five carried it as a caveat, which is the README row's error one document further down ([#337])."""
    named = [
        path.name
        for path in sorted(FINDINGS.glob("*.md"))
        if "back-adjusted continuous series" in path.read_text(encoding="utf-8")
    ]

    assert named == []


# -- InsideBarTrailing's sizing arms, [#295] and [#353] ---------------------------------------


def a_cut(
    root: str = "MNQ",
    minutes: int = 5,
    labels: tuple[str, ...] = ("size_on_vwap", "size_on_regime"),
    symmetric_labels: tuple[str, ...] | None = None,
) -> SizingCut:
    """Build a cut of the shape ``tools/campaign_sizing.py fit`` writes, with plausible values in it.

    The symmetric arm counts ``labels`` unless told otherwise.
    """
    return SizingCut(
        root=root,
        minutes=minutes,
        early_max_extension_atr=1.2,
        early_max_trend_bars=14,
        regime_consolidating_below=0.1,
        regime_directional_above=0.4,
        volume_thin_below=0.6,
        volume_heavy_above=1.6,
        labels=labels,
        symmetric_labels=labels if symmetric_labels is None else symmetric_labels,
    )


def test_the_sizing_strata_are_named_before_the_run() -> None:
    assert [name for name, _ in strata(IBT_SIZING)] == [UNFILTERED, "phase=MIDDAY"]
    assert MIDDAY in RECUTS
    assert MIDDAY not in STRATUM_SETS[ALL_STRATA], "all would run the midday phase twice"


def test_every_sizing_arm_shares_one_grid_and_holds_the_split() -> None:
    """Paired, not a best-of-more: each arm differs from its control in its base alone."""
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = sizing_arms(campaign, a_cut())
    assert len(arms) == 9
    assert len({arm.name for arm in arms}) == 9
    assert all(arm.axes == arms[0].axes for arm in arms)
    assert "partial_take_profit_percentage" not in arms[0].axes
    assert arms[0].axes["order_quantity"] == SIZING_QUANTITIES
    assert {arm.resolutions for arm in arms} == {(5,)}
    assert all(arm.name.startswith(f"{campaign.name} ") for arm in arms)


def test_every_combination_of_every_sizing_arm_is_a_legal_rule_set() -> None:
    """The split rounds up, so a size where two tiers coincide would raise mid-sweep."""
    (campaign,) = insidebartrailing_variants("NQ")
    for arm in sizing_arms(campaign, a_cut("NQ")):
        for _, grid in grids_for(arm, IBT_SIZING):
            assert sum(1 for _ in grid.combinations()) == arm.sized()


def test_the_fitted_values_reach_every_arm_and_the_labels_only_the_confluence_one() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = {arm.name.removeprefix(f"{campaign.name} "): arm for arm in sizing_arms(campaign, a_cut())}
    assert all(base_as(arm, InsideBarTrailingParams).early_max_trend_bars == 14 for arm in arms.values())
    assert all(arm.base.regime_directional_above == 0.4 for arm in arms.values())
    confluence = base_as(arms[SIZING_CONFLUENCE], InsideBarTrailingParams)
    assert sizing_labels(confluence) == ("size_on_vwap", "size_on_regime")
    assert confluence.quantity_per_confluence == 1
    assert all(sizing_labels(arm.base) == () for name, arm in arms.items() if name != SIZING_CONFLUENCE)


def test_each_tier_runs_beside_its_inverse() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = {
        arm.name.removeprefix(f"{campaign.name} "): base_as(arm, InsideBarTrailingParams)
        for arm in sizing_arms(campaign, a_cut())
    }
    written, inverted = arms["tier=trend-age"], arms["tier=trend-age inverted"]
    assert (written.early_partial_percentage, written.partial_take_profit_percentage) == (0.25, 0.5)
    assert (inverted.early_partial_percentage, inverted.partial_take_profit_percentage) == (0.5, 0.25)
    assert arms["split=0.5"].earliness_mode == arms["split=0.25"].earliness_mode == 0


def test_a_cut_with_every_label_dropped_runs_no_confluence_arm() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = sizing_arms(campaign, a_cut(labels=()))
    assert len(arms) == 8
    assert not any(arm.name.endswith(SIZING_CONFLUENCE) for arm in arms)


def test_the_sizing_run_refuses_to_start_without_its_cuts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=r"campaign_sizing\.py fit"):
        sizing_cuts(tmp_path / "absent.json")


def test_the_refusal_names_the_strategy_whose_cuts_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``fit`` defaults to InsideBarTrailing, so a bare command would fill the wrong file."""
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    with pytest.raises(SystemExit, match=r"fit --strategy ElasticBand first"):
        sizing_cuts(sizing_cuts_path("ElasticBand"))


def test_insidebartrailings_arms_refuse_a_cut_without_its_earliness_cuts() -> None:
    """The tier arms would otherwise run at the parameter class's placeholders as if fitted."""
    (campaign,) = insidebartrailing_variants("MNQ")
    for missing in ("early_max_extension_atr", "early_max_trend_bars"):
        with pytest.raises(SystemExit, match="holds no earliness cuts"):
            sizing_arms(campaign, replace(a_cut(), **{missing: None}))  # type: ignore[arg-type]  # one optional field set to None
        with pytest.raises(SystemExit, match="holds no earliness cuts"):
            insidebartrailing_confluence_arms(campaign, replace(a_cut(), **{missing: None}))  # type: ignore[arg-type]  # one optional field set to None


def test_the_sizing_variants_read_their_own_roots_cuts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "cuts.json"
    rows = [
        dataclasses.asdict(a_cut("MNQ", 5)),
        dataclasses.asdict(a_cut("NQ", 5)),
        dataclasses.asdict(a_cut("MNQ", 10)),
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(campaign_sweep, "SIZING_CUTS", path)
    variants = insidebartrailing_sizing_variants("MNQ")
    assert {variant.resolutions for variant in variants} == {(5,), (10,)}
    assert variants_for(IBT_SIZING) is IBT_SIZING_VARIANTS


# -- the tiers above a half ----------------------------------------------------------------


def test_every_arm_above_a_half_shares_one_grid_at_its_own_ladder() -> None:
    """Paired, not a best-of-more: each arm differs from its control in its base alone."""
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = sizing_high_arms(campaign, a_cut())
    assert len(arms) == 8
    assert len({arm.name for arm in arms}) == 8
    assert all(arm.axes == arms[0].axes for arm in arms)
    assert "partial_take_profit_percentage" not in arms[0].axes
    assert arms[0].axes["order_quantity"] == SIZING_HIGH_QUANTITIES
    assert {arm.resolutions for arm in arms} == {(5,)}


def test_every_combination_of_every_arm_above_a_half_is_a_legal_rule_set() -> None:
    """The split rounds up, so a size leaving no runner would raise mid-sweep."""
    (campaign,) = insidebartrailing_variants("NQ")
    for arm in sizing_high_arms(campaign, a_cut("NQ")):
        for _, grid in grids_for(arm, IBT_SIZING_HIGH):
            assert sum(1 for _ in grid.combinations()) == arm.sized()


def test_an_eight_tenths_split_leaves_no_runner_below_the_ladders_floor() -> None:
    below: int = min(SIZING_HIGH_QUANTITIES) - 1
    with pytest.raises(ValueError, match="leaves a lot of zero contracts"):
        InsideBarTrailingParams(order_quantity=below, partial_take_profit_percentage=0.8)


def test_each_tier_above_a_half_runs_beside_its_inverse() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = {
        arm.name.removeprefix(f"{campaign.name} "): base_as(arm, InsideBarTrailingParams)
        for arm in sizing_high_arms(campaign, a_cut())
    }
    written, inverted = arms["tier=trend-age@0.6/0.8"], arms["tier=trend-age@0.6/0.8 inverted"]
    assert (written.early_partial_percentage, written.partial_take_profit_percentage) == (0.6, 0.8)
    assert (inverted.early_partial_percentage, inverted.partial_take_profit_percentage) == (0.8, 0.6)
    assert arms["split=0.8"].partial_take_profit_percentage == 0.8
    assert arms["split=0.6"].partial_take_profit_percentage == 0.6
    assert arms["split=0.8"].earliness_mode == arms["split=0.6"].earliness_mode == 0


def test_only_the_splits_above_a_half_keep_their_reconciliation() -> None:
    """No NinjaScript tiers its first partial, so every tier arm's rows are ``TIER1_ONLY``."""
    (campaign,) = insidebartrailing_variants("MNQ")
    for arm in sizing_high_arms(campaign, a_cut()):
        split: bool = " split=" in arm.name
        expected = archetypes.Tier2Status.RECONCILED if split else archetypes.Tier2Status.TIER1_ONLY
        assert arm.archetype.tier2_for(arm.base) is expected, arm.name


def test_no_arm_above_a_half_takes_a_name_already_in_the_database() -> None:
    """Rows are separated by variant name alone, so a shared name would be skipped as stored."""
    (campaign,) = insidebartrailing_variants("MNQ")
    taken = {variant.name for variant in VARIANTS["InsideBarTrailing"]("MNQ")}
    taken |= {arm.name for arm in insidebartrailing_confluence_arms(campaign, a_cut())}
    names = {arm.name for arm in sizing_high_arms(campaign, a_cut())}
    assert not taken & names


def test_the_tiers_above_a_half_refuse_a_cut_without_its_earliness_cuts() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    for missing in ("early_max_extension_atr", "early_max_trend_bars"):
        with pytest.raises(SystemExit, match="holds no earliness cuts"):
            sizing_high_arms(campaign, replace(a_cut(), **{missing: None}))  # type: ignore[arg-type]  # one optional field set to None


def test_the_tiers_above_a_half_read_their_own_roots_cuts_in_the_sizing_strata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "cuts.json"
    rows = [dataclasses.asdict(a_cut("MNQ", 5)), dataclasses.asdict(a_cut("NQ", 10))]
    path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(campaign_sweep, "SIZING_CUTS", path)
    assert {variant.resolutions for variant in insidebartrailing_sizing_high_variants("MNQ")} == {(5,)}
    assert [name for name, _ in strata(IBT_SIZING_HIGH)] == [name for name, _ in strata(IBT_SIZING)]
    assert variants_for(IBT_SIZING_HIGH) is IBT_SIZING_HIGH_VARIANTS


def test_a_sizing_arm_is_stored_tier1_only_and_its_control_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save_sweep`` stamps one status per sweep; the rows have to carry their own first."""
    (campaign,) = insidebartrailing_variants("MNQ")
    control, *_, confluence = sizing_arms(campaign, a_cut())
    control = replace(control, axes={"order_quantity": [3, 4]})
    confluence = replace(confluence, axes={"order_quantity": [3, 4]})
    stored: list[pd.DataFrame] = []

    def fake_sweep_grids(
        _data: context.Dataset,
        grids: list[sweep.Grid],
        _instrument: Instrument,
        *,
        n_jobs: int,  # noqa: ARG001 - the caller passes it by keyword
    ) -> list[tuple[pd.DataFrame, dict[int, pd.DataFrame]]]:
        return unswept(grids)

    def keep(frame: pd.DataFrame, **_: object) -> int:
        stored.append(frame)

        return 1

    monkeypatch.setattr("tools.campaign_sweep.CAMPAIGN_DIR", tmp_path / "campaign")
    monkeypatch.setattr("nqbt.context.prepare", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("nqbt.results.save_sweep", keep)
    monkeypatch.setattr(sweep, "sweep_grids", fake_sweep_grids)
    run_point(
        pd.DataFrame(index=range(10)),
        [control, confluence],
        "MNQ",
        5,
        "holdout",
        1,
        UNFILTERED,
        NO_CUTS,
        n_jobs=1,
    )

    (frame,) = stored
    by_variant = frame.groupby("variant")["tier2"].agg(set).to_dict()
    assert by_variant == {control.name: {"reconciled"}, confluence.name: {"tier-1-only"}}


# -- §M47: the confluence size on every archetype -------------------------------------------


def m47_cut(
    root: str = "MNQ",
    minutes: int = 5,
    labels: tuple[str, ...] = ("size_on_trend", "size_on_regime"),
    variant: str | None = None,
    symmetric_labels: tuple[str, ...] | None = None,
) -> SizingCut:
    """Build a cut of the shape the fit writes outside InsideBarTrailing: no earliness in it.

    The symmetric arm counts ``labels`` unless told otherwise.
    """
    return SizingCut(
        root=root,
        minutes=minutes,
        regime_consolidating_below=0.1,
        regime_directional_above=0.4,
        volume_thin_below=0.6,
        volume_heavy_above=1.6,
        labels=labels,
        symmetric_labels=labels if symmetric_labels is None else symmetric_labels,
        variant=variant,
    )


def arm_names(campaign: Variant, arms: list[Variant]) -> list[str]:
    return [arm.name.removeprefix(f"{campaign.name} ") for arm in arms]


def write_cuts(path: Path, cuts: list[SizingCut]) -> None:
    path.write_text(json.dumps([dataclasses.asdict(cut) for cut in cuts]), encoding="utf-8")


def test_a_cut_without_earliness_sets_the_label_thresholds_alone() -> None:
    thresholds = {
        "regime_consolidating_below": 0.1,
        "regime_directional_above": 0.4,
        "volume_thin_below": 0.6,
        "volume_heavy_above": 1.6,
    }
    assert m47_cut().fitted() == thresholds
    assert a_cut().fitted() == thresholds | {"early_max_extension_atr": 1.2, "early_max_trend_bars": 14}


def test_a_cut_naming_no_variant_fits_every_one_and_one_naming_a_variant_fits_that_one() -> None:
    assert m47_cut().fits("anything")
    assert m47_cut(variant="stop=atr").fits("stop=atr")
    assert not m47_cut(variant="stop=atr").fits("stop=swing")


def test_a_cut_file_reads_back_with_and_without_the_newer_fields(tmp_path: Path) -> None:
    """§M45's file carries no variant or symmetric labels, and only InsideBarTrailing's carry earliness."""
    newer = {"variant", "symmetric_labels"}
    legacy = {key: value for key, value in dataclasses.asdict(a_cut()).items() if key not in newer}
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps([legacy, dataclasses.asdict(m47_cut(variant="bracket"))]), encoding="utf-8")
    assert sizing_cuts(path) == [replace(a_cut(), symmetric_labels=None), m47_cut(variant="bracket")]


def test_a_four_target_bracket_at_its_floor_gets_every_arm_but_the_symmetric_one() -> None:
    (campaign,) = VARIANTS["DeadCatBounce"]("MNQ")
    arms = confluence_arms(campaign, m47_cut())
    assert arm_names(campaign, arms) == [SIZE_FIXED, SIZING_CONFLUENCE, "size=trend", "size=regime"]


def test_a_bracket_above_its_floor_also_gets_the_symmetric_arm() -> None:
    campaign = VARIANTS["ElasticBand"]("MNQ")[0]
    arms = confluence_arms(campaign, m47_cut())
    assert arm_names(campaign, arms)[-1] == SIZING_SYMMETRIC
    assert arms[-1].base.size_symmetric
    assert sizing_labels(arms[-1].base) == ("size_on_trend", "size_on_regime")


def test_the_arms_count_what_their_names_say() -> None:
    campaign = VARIANTS["ElasticBand"]("MNQ")[0]
    control, together, trend_alone, regime_alone, symmetric = confluence_arms(campaign, m47_cut())
    assert sizing_labels(control.base) == ()
    assert control.base.quantity_per_confluence == 0
    assert (
        sizing_labels(together.base) == sizing_labels(symmetric.base) == ("size_on_trend", "size_on_regime")
    )
    assert sizing_labels(trend_alone.base) == ("size_on_trend",)
    assert sizing_labels(regime_alone.base) == ("size_on_regime",)
    assert not together.base.size_symmetric


def test_the_symmetric_arm_counts_the_labels_fitted_for_it_rather_than_the_add_only_ones() -> None:
    """A label favouring few signals and opposing many sorts nothing added-only and plenty symmetric."""
    campaign = VARIANTS["ElasticBand"]("MNQ")[0]
    symmetric = ("size_on_trend", "size_on_higher_timeframe", "size_on_regime")
    cut = m47_cut(labels=("size_on_higher_timeframe",), symmetric_labels=symmetric)
    arms = confluence_arms(campaign, cut)
    assert arm_names(campaign, arms) == [SIZE_FIXED, SIZING_CONFLUENCE, SIZING_SYMMETRIC]
    assert sizing_labels(arms[1].base) == ("size_on_higher_timeframe",)
    assert sizing_labels(arms[2].base) == symmetric


def test_a_cut_keeping_labels_for_the_symmetric_arm_alone_runs_the_control_and_that_arm() -> None:
    campaign = VARIANTS["ElasticBand"]("MNQ")[0]
    arms = confluence_arms(campaign, m47_cut(labels=(), symmetric_labels=("size_on_trend",)))
    assert arm_names(campaign, arms) == [SIZE_FIXED, SIZING_SYMMETRIC]


def test_a_cut_stored_before_its_symmetric_labels_were_read_is_refused() -> None:
    """Counting the add-only labels in their place would run an arm the fit never chose."""
    campaign = VARIANTS["ElasticBand"]("MNQ")[0]
    with pytest.raises(SystemExit, match="no symmetric labels"):
        confluence_arms(campaign, replace(m47_cut(), symmetric_labels=None))


def test_one_kept_label_is_the_all_labels_arm_so_there_is_no_arm_for_it_alone() -> None:
    (campaign,) = VARIANTS["DeadCatBounce"]("MNQ")
    assert arm_names(campaign, confluence_arms(campaign, m47_cut(labels=("size_on_trend",)))) == [
        SIZE_FIXED,
        SIZING_CONFLUENCE,
    ]


def test_a_cut_that_kept_no_label_leaves_the_control_alone() -> None:
    (campaign,) = VARIANTS["DeadCatBounce"]("MNQ")
    assert arm_names(campaign, confluence_arms(campaign, m47_cut(labels=()))) == [SIZE_FIXED]


def test_every_arm_shares_the_stored_grid_and_the_fitted_thresholds() -> None:
    for campaign in VARIANTS["ElasticBand"]("NQ"):
        for arm in confluence_arms(campaign, m47_cut(root="NQ")):
            assert arm.axes == campaign.axes
            assert arm.resolutions == (5,)
            assert arm.base.regime_directional_above == 0.4
            assert arm.base.volume_thin_below == 0.6


def test_insidebartrailing_keeps_its_nine_arms_and_adds_the_new_ones_on_the_same_grid() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = insidebartrailing_confluence_arms(campaign, a_cut())
    names = arm_names(campaign, arms)
    assert names[:9] == arm_names(campaign, sizing_arms(campaign, a_cut()))
    assert names[9:] == ["size=vwap", "size=regime", SIZING_SYMMETRIC]
    assert all(arm.axes == arms[0].axes for arm in arms)
    assert all(
        base_as(arm, InsideBarTrailingParams).partial_take_profit_percentage == 0.5 for arm in arms[9:]
    )


def test_insidebartrailing_runs_its_symmetric_arm_on_its_own_labels() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    symmetric = ("size_on_trend", "size_on_vwap", "size_on_regime")
    arms = insidebartrailing_confluence_arms(campaign, a_cut(symmetric_labels=symmetric))
    assert arm_names(campaign, arms)[-1] == SIZING_SYMMETRIC
    assert sizing_labels(arms[-1].base) == symmetric
    bare = insidebartrailing_confluence_arms(campaign, a_cut(labels=(), symmetric_labels=symmetric))
    assert arm_names(campaign, bare) == [
        *arm_names(campaign, sizing_arms(campaign, a_cut(labels=()))),
        SIZING_SYMMETRIC,
    ]


def test_every_combination_of_every_confluence_arm_is_a_legal_rule_set() -> None:
    """A floor the symmetric arm cannot shed from, or a label on the wrong class, would raise mid-sweep."""
    for name, build in VARIANTS.items():
        ported = name == archetypes.INSIDEBARTRAILING.name
        arms_for = insidebartrailing_confluence_arms if ported else confluence_arms
        cut = a_cut(labels=SIZING_LABELS) if ported else m47_cut(labels=SIZING_LABELS)
        for campaign in build("MNQ"):
            for arm in arms_for(campaign, cut):
                grid = sweep.Grid(axes=arm.axes, base=arm.base, archetype=arm.archetype)
                assert sum(1 for _ in grid.combinations()) == arm.sized(), arm.name


def test_the_confluence_variants_run_only_where_a_cut_was_fitted_for_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    variant = "window=5m stop=opposite target=R"
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    write_cuts(
        sizing_cuts_path("OpeningRange"),
        [
            m47_cut("MNQ", 5, variant=variant),
            m47_cut("MNQ", 10, variant=variant),
            m47_cut("NQ", 5, variant=variant),
        ],
    )
    variants = CONFLUENCE_SIZING_VARIANTS["OpeningRange"]("MNQ")
    assert {arm.name.rsplit(" size=", 1)[0] for arm in variants} == {variant}
    assert {arm.resolutions for arm in variants} == {(5,)}, "a 5-minute range has no 10-minute bars"
    assert variants_for(CONFLUENCE_SIZING) is CONFLUENCE_SIZING_VARIANTS


def test_the_strata_cut_regime_and_volume_where_the_labels_are_cut(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    ladders = list(ELASTIC_LADDERS)
    write_cuts(sizing_cuts_path("ElasticBand"), [m47_cut(variant=ladder) for ladder in ladders])
    cuts = confluence_cuts("ElasticBand", "MNQ")
    assert set(cuts) == {5}
    cells = dict(strata(CONFLUENCE_SIZING, cuts[5]))
    regime_cell = cells["regime=DIRECTIONAL@n=20 q=0.20/0.80"]
    assert regime_cell["regime_directional_above"] == [0.4]
    assert regime_cell["regime_consolidating_below"] == [0.1]
    heavy = [name for name in cells if name.startswith("volume=HEAVY@")]
    assert len(heavy) == 1
    assert heavy[0].endswith("q=0.20/0.80")
    assert cells[heavy[0]]["volume_heavy_above"] == [1.6]
    assert len(cells) == 1 + 3 + len(timeofday.SessionPhase) + 3 + 3 + 3 + len(higher_timeframe.Side)


def test_variants_fitted_at_two_cuts_at_one_resolution_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    moved = dataclasses.replace(m47_cut(variant="target=+1.0s"), volume_heavy_above=2.0)
    write_cuts(sizing_cuts_path("ElasticBand"), [m47_cut(variant="target=0.0s"), moved])
    with pytest.raises(SystemExit, match="the strata need one"):
        confluence_cuts("ElasticBand", "MNQ")


def test_a_confluence_run_is_refused_under_another_cut_or_the_raw_volume_cells() -> None:
    args = argparse.Namespace(
        variants=CONFLUENCE_SIZING, regime_quantiles=(0.2, 0.8), volume_quantiles=(), strata=CONFLUENCE_SIZING
    )
    with pytest.raises(SystemExit, match="drop --regime-quantiles"):
        check_confluence_request(args)

    args.regime_quantiles = None
    args.strata = ALL_STRATA
    with pytest.raises(SystemExit, match="raw volume cells"):
        check_confluence_request(args)

    args.strata = CONFLUENCE_SIZING
    check_confluence_request(args)
    check_confluence_request(argparse.Namespace(variants=CAMPAIGN, strata=ALL_STRATA))


def test_the_planned_count_has_one_regime_and_one_volume_cut_per_dimension(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    write_cuts(sizing_cuts_path("DeadCatBounce"), [m47_cut()])
    args = argparse.Namespace(
        variants=CONFLUENCE_SIZING,
        strategies=["DeadCatBounce"],
        roots=["MNQ"],
        resolutions=[5],
        split=True,
        strata=CONFLUENCE_SIZING,
    )
    (campaign,) = VARIANTS["DeadCatBounce"]("MNQ")
    cells = 1 + 3 + len(timeofday.SessionPhase) + 3 + 3 + 3 + len(higher_timeframe.Side)
    assert planned_combinations(args) == campaign.sized() * cells * 4 * 2


# -- the stored-cell guard -------------------------------------------------------------------


def test_a_cell_stored_on_these_bars_is_skipped_and_one_on_other_bars_refused() -> None:
    frame = walk_bars(100)
    grid = sweep.Grid.of(DeadCatParams())
    named = [("a", UNFILTERED, grid), ("b", UNFILTERED, grid)]
    here = swept_on(frame)
    assert unstored(named, {}, frame) == named
    assert unstored(named, {("a", UNFILTERED): {here}}, frame) == named[1:]
    with pytest.raises(SystemExit, match="already stored"):
        unstored(named, {("a", UNFILTERED): {here._replace(bars=here.bars + 1)}}, frame)


def tiny_variant() -> Variant:
    """Return a two-combination DeadCatBounce variant that trades on :func:`walk_bars`."""
    return Variant(
        "tiny",
        archetypes.DEADCATBOUNCE,
        DeadCatParams(use_ema=False, use_fast_sma=False, require_new_high=False, bars_required_to_trade=20),
        axes={"tp_multiplier": [1.0, 2.0]},
    )


def test_a_point_run_twice_stores_each_cell_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    frame = walk_bars(3000, seed=5)
    tiny = tiny_variant()

    def stored() -> int:
        return int(results.query("SELECT count(*) AS n FROM combos", db_path("DeadCatBounce"))["n"].iloc[0])

    run_point(frame, [tiny], "MNQ", 1, "holdout", 1, UNFILTERED, NO_CUTS, n_jobs=1)
    assert stored() == 2
    run_point(frame, [tiny], "MNQ", 1, "holdout", 2, UNFILTERED, NO_CUTS, n_jobs=1)
    assert stored() == 2, "a cell already stored was swept again"
    run_point(
        frame, [tiny, replace(tiny, name="tiny again")], "MNQ", 1, "holdout", 3, UNFILTERED, NO_CUTS, n_jobs=1
    )
    assert stored() == 4, "the new cell at the same point was not swept"
    run_point(frame, [tiny], "MNQ", 1, "selection", 4, UNFILTERED, NO_CUTS, n_jobs=1)
    assert stored() == 6, "another window is another cell"
    with pytest.raises(SystemExit, match="already stored"):
        run_point(frame.iloc[:-10], [tiny], "MNQ", 1, "holdout", 5, UNFILTERED, NO_CUTS, n_jobs=1)


def test_a_skipped_cell_is_warned_of_and_the_notes_count_only_the_cells_swept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The skip compares the bars alone, so a cell whose grid has changed is skipped just the same."""
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    frame = walk_bars(3000, seed=5)
    tiny = tiny_variant()
    run_point(frame, [tiny], "MNQ", 1, "holdout", 1, UNFILTERED, NO_CUTS, n_jobs=1)
    with caplog.at_level(logging.WARNING, logger=campaign_sweep.__name__):
        run_point(
            frame,
            [tiny, replace(tiny, name="tiny again")],
            "MNQ",
            1,
            "holdout",
            2,
            UNFILTERED,
            NO_CUTS,
            n_jobs=1,
        )
    assert "1 of 2 cells already stored, skipped without checking" in caplog.text
    notes = results.query("SELECT notes FROM sweeps ORDER BY sweep_id", db_path("DeadCatBounce"))["notes"]
    assert "; variants=1; cells=1 of 1;" in notes.iloc[0]
    assert "; variants=1; cells=1 of 2;" in notes.iloc[1]


def test_insidebartrailing_with_no_kept_label_keeps_only_the_arms_that_need_none() -> None:
    (campaign,) = insidebartrailing_variants("MNQ")
    arms = insidebartrailing_confluence_arms(campaign, a_cut(labels=()))
    assert arm_names(campaign, arms) == arm_names(campaign, sizing_arms(campaign, a_cut(labels=())))
    assert SIZING_CONFLUENCE not in arm_names(campaign, arms)


def test_the_strata_read_each_roots_own_cut(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(campaign_sweep, "CAMPAIGN_DIR", tmp_path)
    nq = dataclasses.replace(m47_cut("NQ"), regime_directional_above=0.7)
    write_cuts(sizing_cuts_path("DeadCatBounce"), [m47_cut("MNQ"), nq])
    assert confluence_cuts("DeadCatBounce", "MNQ")[5].regime[0].directional_above == 0.4
    assert confluence_cuts("DeadCatBounce", "NQ")[5].regime[0].directional_above == 0.7


def early_exit_fields(params: archetypes.Params) -> dict[str, object]:
    """Return one parameter set's ``early_exit_*`` fields by name."""
    return {
        field.name: getattr(params, field.name)
        for field in dataclasses.fields(params)
        if field.name.startswith("early_exit_")
    }


def test_the_early_exit_arms_are_the_control_and_every_rule_at_every_rung() -> None:
    arms = early_exit_arms()
    not_working = len(EARLY_EXIT_BARS) * len(EARLY_EXIT_BELOW_R)
    assert len(arms) == 1 + not_working + len(EARLY_EXIT_MINUTES) + 2 + 4
    assert arms["off"] == {}
    assert len({tuple(sorted(fields.items())) for fields in arms.values()}) == len(arms)


def test_every_early_exit_arm_carries_its_stored_grid_unchanged() -> None:
    """The arm is a variant dimension and not an axis, so an arm and its control pair row for row.

    ``tools/README.md`` § "campaign_sweep.py".
    """
    arms = list(early_exit_arms())
    for name, build in VARIANTS.items():
        stored = build("MNQ")
        exited = EARLY_EXIT_VARIANTS[name]("MNQ")
        assert len(exited) == len(stored) * len(arms)
        for index, variant in enumerate(exited):
            source = stored[index // len(arms)]
            assert variant.name == f"{source.name} exit={arms[index % len(arms)]}"
            assert variant.axes == source.axes
            assert variant.archetype is source.archetype
            assert variant.sized() == source.sized()


def test_an_early_exit_arm_changes_nothing_but_the_early_exit_fields() -> None:
    per_variant = len(early_exit_arms())
    for name, build in VARIANTS.items():
        stored = build("NQ")
        for index, variant in enumerate(EARLY_EXIT_VARIANTS[name]("NQ")):
            source = stored[index // per_variant]
            assert replace(variant.base, **early_exit_fields(source.base)) == source.base


def test_each_early_exit_arm_switches_on_one_rule_and_the_control_none() -> None:
    """One exit code serves every rule, so an arm is one rule or the log cannot say which fired.

    ``docs/nt8-fidelity.md``, "The conditional early exit".
    """
    for name in VARIANTS:
        for variant in EARLY_EXIT_VARIANTS[name]("MNQ"):
            expected = 0 if variant.name.endswith(" exit=off") else 1
            assert len(active_early_exits(variant.base)) == expected


def test_no_stored_grid_or_stratum_sweeps_a_field_an_early_exit_arm_sets() -> None:
    """An axis over the same field would override the arm on every row, which is §M29's first-pass trap."""
    set_by_arms = {field for fields in early_exit_arms().values() for field in fields}
    stratum_axes = {axis for which in (EARLY_EXIT, MIDDAY) for _, extra in strata(which) for axis in extra}
    assert not set_by_arms & stratum_axes
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            assert not set_by_arms & set(variant.axes)


def test_every_not_working_bar_is_tested_before_any_stored_hold_cap() -> None:
    """A bar at or past ``max_hold_bars`` can never fire, so the ladder has to stop short of every cap."""
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            ladder: list[int] = [int(cap) for cap in variant.axes.get("max_hold_bars", [])]
            caps = [*ladder, variant.base.max_hold_bars]
            assert all(cap == 0 or cap > max(EARLY_EXIT_BARS) for cap in caps)


def test_an_early_exit_arm_at_a_hold_cap_is_refused_rather_than_run_inert() -> None:
    (campaign,) = VARIANTS["InsideBar"]("MNQ")
    with pytest.raises(ValueError, match="can never fire under max_hold_bars"):
        replace(campaign.base, max_hold_bars=max(EARLY_EXIT_BARS), early_exit_bars=max(EARLY_EXIT_BARS))


def test_no_early_exit_variant_can_collide_with_a_stored_one_in_the_same_database() -> None:
    """Rows are separated by variant name alone, and ``campaign_holdout`` pairs the two windows one-to-one."""
    for name, build in VARIANTS.items():
        exited = EARLY_EXIT_VARIANTS[name]("MNQ")
        names = {variant.name for variant in exited}
        assert len(names) == len(exited)
        assert not names & {variant.name for variant in build("MNQ")}


def test_the_early_exit_run_states_its_stratum_before_it_runs() -> None:
    assert [name for name, _ in strata(EARLY_EXIT)] == [UNFILTERED]
    assert variants_for(EARLY_EXIT) is EARLY_EXIT_VARIANTS


# -- the second early-exit run (#369's second tier) -----------------------------------------

TIER2_FAMILIES = ("early_exit_", "age_stop_", "late_stop_", "breakeven_")
"""The parameter families a tier-2 arm may set."""


def tier2_fields(params: archetypes.Params) -> dict[str, object]:
    """Return one parameter set's fields in the families a tier-2 arm sets, by name."""
    return {
        field.name: getattr(params, field.name)
        for field in dataclasses.fields(params)
        if field.name.startswith(TIER2_FAMILIES)
    }


def test_the_tier_2_arms_are_the_control_and_the_39_pre_registered_settings() -> None:
    arms = tier2_arms()
    assert len(arms) == 1 + 8 + 6 + 2 + 6 + 2 + 3 + 9 + 2
    assert arms["off"] == {}
    assert len({tuple(sorted(fields.items())) for fields in arms.values()}) == len(arms)
    assert all(field.startswith(TIER2_FAMILIES) for fields in arms.values() for field in fields)


def test_every_tier_2_arm_carries_its_stored_grid_unchanged_under_a_name_of_its_own() -> None:
    arms = list(tier2_arms())
    for name, build in VARIANTS.items():
        stored = build("MNQ")
        exited = EARLY_EXIT_2_VARIANTS[name]("MNQ")
        assert len(exited) == len(stored) * len(arms)
        tier1 = {variant.name for variant in EARLY_EXIT_VARIANTS[name]("MNQ")}
        assert not {variant.name for variant in exited} & (tier1 | {variant.name for variant in stored})
        for index, variant in enumerate(exited):
            source = stored[index // len(arms)]
            assert variant.name == f"{source.name} exit2={arms[index % len(arms)]}"
            assert variant.axes == source.axes
            assert variant.archetype is source.archetype
            assert variant.sized() == source.sized()
            assert replace(variant.base, **tier2_fields(source.base)) == source.base


def test_each_tier_2_arm_switches_on_at_most_one_rule() -> None:
    for name in VARIANTS:
        for variant in EARLY_EXIT_2_VARIANTS[name]("NQ"):
            base = variant.base
            stop_rules = [
                base.age_stop_bars > 0 or base.age_stop_minutes > 0,
                base.late_stop_minutes_before_close > 0,
                base.breakeven_at > 0,
            ]
            on = len(active_early_exits(base)) + sum(stop_rules)
            assert on == (0 if variant.name.endswith(" exit2=off") else 1), variant.name


def test_no_stored_grid_or_stratum_sweeps_a_field_a_tier_2_arm_sets() -> None:
    set_by_arms = {field for fields in tier2_arms().values() for field in fields}
    stratum_axes = {axis for which in (EARLY_EXIT_2, MIDDAY) for _, extra in strata(which) for axis in extra}
    assert not set_by_arms & stratum_axes
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            assert not set_by_arms & set(variant.axes)


def test_every_bar_timed_tier_2_arm_acts_before_any_stored_hold_cap() -> None:
    """A step or a not-working bar at or past ``max_hold_bars`` can never act."""
    bars: list[int] = [int(fields.get("early_exit_bars", 0)) for fields in tier2_arms().values()]
    steps: list[int] = [
        int(fields.get("age_stop_bars", 0))
        for fields in tier2_arms().values()
        if "age_stop_shape" not in fields
    ]
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            ladder: list[int] = [int(cap) for cap in variant.axes.get("max_hold_bars", [])]
            caps = [*ladder, variant.base.max_hold_bars]
            assert all(cap == 0 or cap > max(*bars, *steps) for cap in caps)


def test_each_tier_2_arm_runs_at_the_settings_the_pre_registration_names_where_it_leaves_a_default() -> None:
    """The late stop's ATR is 1 of 14, the breakeven stop is in R on the close, and a line reaches the entry.

    A losing exit is below 0 R of open profit -- ``docs/findings/m50-early-exit-tier-2-preregistration.md``.
    """
    (campaign,) = VARIANTS["InsideBar"]("MNQ")
    for arm, fields in tier2_arms().items():
        base = replace(campaign.base, **fields)
        if arm.startswith("late") and arm.endswith("-atr"):
            assert (base.late_stop_atr, base.late_stop_atr_period) == (1.0, 14), arm

        if arm.startswith("breakeven"):
            assert (base.breakeven_unit, base.breakeven_on, base.breakeven_offset_ticks) == (
                BREAKEVEN_R,
                BREAKEVEN_ON_CLOSE,
                0,
            ), arm

        if arm.startswith("losing"):
            assert (base.early_exit_below_r, base.early_exit_measure) == (0.0, MEASURE_OPEN_PROFIT), arm

        if arm.startswith("line"):
            assert base.age_stop_fraction == 1.0, arm


def test_the_tier_2_run_states_its_stratum_before_it_runs() -> None:
    assert [name for name, _ in strata(EARLY_EXIT_2)] == [UNFILTERED]
    assert variants_for(EARLY_EXIT_2) is EARLY_EXIT_2_VARIANTS


# -- the third early-exit run (#369's third tier) ------------------------------------------

LOSING_SUFFIX = "-losing"
COUNTER_TREND_INFIX = "-counter"


def test_the_tier_3_arms_are_the_control_and_the_37_pre_registered_settings() -> None:
    arms = tier3_arms()
    labels = 1 + 2 + 2 + 2 + len(ATR_EXPANSIONS)
    prices = 2 * len(STALL_BARS) + 2 * len(ADVERSE_CLOSES) + 2 * len(ADVERSE_ATRS)
    give_backs = len(GIVE_BACKS) * len(GIVE_BACK_FROM_R)
    assert len(arms) == 37 == 1 + labels + prices + give_backs + 2 * len(COUNTER_TREND_BARS)
    assert arms["off"] == {}
    assert len({tuple(sorted(fields.items())) for fields in arms.values()}) == len(arms)
    assert all(field.startswith("early_exit_") for fields in arms.values() for field in fields)


def test_every_tier_3_arm_carries_its_stored_grid_unchanged_under_a_name_of_its_own() -> None:
    arms = list(tier3_arms())
    for name, build in VARIANTS.items():
        stored = build("MNQ")
        exited = EARLY_EXIT_3_VARIANTS[name]("MNQ")
        assert len(exited) == len(stored) * len(arms)
        earlier = {
            variant.name
            for variants in (stored, EARLY_EXIT_VARIANTS[name]("MNQ"), EARLY_EXIT_2_VARIANTS[name]("MNQ"))
            for variant in variants
        }
        assert not {variant.name for variant in exited} & earlier
        for index, variant in enumerate(exited):
            source = stored[index // len(arms)]
            assert variant.name == f"{source.name} exit3={arms[index % len(arms)]}"
            assert variant.axes == source.axes
            assert variant.archetype is source.archetype
            assert variant.sized() == source.sized()
            assert replace(variant.base, **early_exit_fields(source.base)) == source.base


def test_each_tier_3_arm_switches_on_one_early_exit_and_moves_no_stop() -> None:
    for name in VARIANTS:
        for variant in EARLY_EXIT_3_VARIANTS[name]("NQ"):
            base = variant.base
            assert len(active_early_exits(base)) == (0 if variant.name.endswith(" exit3=off") else 1)
            assert (base.age_stop_bars, base.late_stop_minutes_before_close, base.breakeven_at) == (0, 0, 0.0)


def test_every_losing_tier_3_arm_is_its_twin_with_only_if_losing_added() -> None:
    """Each pair differs by the one condition, so the contrast the pre-registration reads is clean.

    ``docs/findings/m52-early-exit-tier-3-preregistration.md``.
    """
    arms = tier3_arms()
    losing = [arm for arm in arms if arm.endswith(LOSING_SUFFIX)]
    assert len(losing) == 3 + len(STALL_BARS) + len(ADVERSE_CLOSES) + len(ADVERSE_ATRS)
    for arm in losing:
        twin = arms[arm.removesuffix(LOSING_SUFFIX)]
        assert "early_exit_only_if_losing" not in twin
        assert arms[arm] == {**twin, "early_exit_only_if_losing": True}


def test_every_counter_trend_arm_is_its_twin_with_a_shorter_count_against_the_trend() -> None:
    arms = tier3_arms()
    counter = [arm for arm in arms if COUNTER_TREND_INFIX in arm]
    assert len(counter) == len(COUNTER_TREND_BARS)
    for arm in counter:
        twin = arms[arm.split(COUNTER_TREND_INFIX)[0]]
        shorter = arms[arm]["early_exit_counter_trend_bars"]
        assert arms[arm] == {**twin, "early_exit_counter_trend_bars": shorter}
        assert 0 < int(shorter) < int(twin["early_exit_bars"])


def test_no_stored_grid_or_stratum_sweeps_a_field_a_tier_3_arm_sets() -> None:
    set_by_arms = {field for fields in tier3_arms().values() for field in fields}
    stratum_axes = {axis for which in (EARLY_EXIT_3, MIDDAY) for _, extra in strata(which) for axis in extra}
    assert not set_by_arms & stratum_axes
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            assert not set_by_arms & set(variant.axes)


def test_every_bar_counted_tier_3_arm_can_fire_before_any_stored_hold_cap() -> None:
    """A count at or past ``max_hold_bars`` can never fire, and the parameter class refuses it."""
    counts: list[int] = [
        int(fields.get(name, 0))
        for fields in tier3_arms().values()
        for name in ("early_exit_bars", "early_exit_stall_bars", "early_exit_adverse_closes")
    ]
    for build in VARIANTS.values():
        for variant in build("MNQ"):
            ladder: list[int] = [int(cap) for cap in variant.axes.get("max_hold_bars", [])]
            caps = [*ladder, variant.base.max_hold_bars]
            assert all(cap == 0 or cap > max(counts) for cap in caps)


def test_every_stored_grid_reads_the_labels_at_the_settings_the_tier_3_pre_registration_names() -> None:
    """Every archetype reads the same labels, so one arm means one rule across the registry.

    ``docs/findings/m52-early-exit-tier-3-preregistration.md``.
    """
    per_bar_volume = volume.key(int(volume.VolumeForm.PER_BAR), VOLUME_ROLLING_BARS, VOLUME_BASELINE_SESSIONS)
    for build in VARIANTS.values():
        for variant in chain.from_iterable(build(root) for root in ROOTS):
            base = variant.base
            assert (base.early_exit_atr_period, base.early_exit_below_r, base.early_exit_measure) == (
                14,
                0.0,
                MEASURE_OPEN_PROFIT,
            ), variant.name
            assert base.higher_timeframe_key == higher_timeframe.key(60, 50), variant.name
            assert base.volume_key == per_bar_volume, variant.name
            assert (base.volume_thin_below, base.volume_heavy_above) == (0.7, 1.5), variant.name
            assert (base.trend_key, base.trend_min_agreement) == (trend.key(20, 50, 5), 3), variant.name


def test_each_tier_3_arm_that_reads_a_label_builds_it_on_every_archetype() -> None:
    """A rule reading a series its grid never built would read nothing rather than fail loudly."""
    for name in VARIANTS:
        for variant in EARLY_EXIT_3_VARIANTS[name]("MNQ"):
            arm = variant.name.split(" exit3=")[1]
            spec = sweep.Grid(
                axes=variant.axes, base=variant.base, archetype=variant.archetype
            ).required_context()
            if arm == "phase":
                assert spec.needs_time_of_day, variant.name

            if arm.startswith("htf"):
                assert spec.higher_timeframe_keys, variant.name

            if arm.startswith(("thin", "heavy-against")):
                assert spec.volume_keys, variant.name

            if arm.startswith(("atr", "adverse")):
                assert 14 in spec.atr_periods, variant.name

            if COUNTER_TREND_INFIX in arm:
                assert spec.trend_keys, variant.name


def test_the_tier_3_run_states_its_stratum_before_it_runs() -> None:
    assert [name for name, _ in strata(EARLY_EXIT_3)] == [UNFILTERED]
    assert variants_for(EARLY_EXIT_3) is EARLY_EXIT_3_VARIANTS


# -- the structure-trail run (#352) ----------------------------------------------------


def test_the_structure_trail_arms_are_the_control_and_every_box_at_every_cushion() -> None:
    arms = structure_trail_arms()
    assert len(arms) == 1 + len(STRUCTURE_TRAIL_BARS) * len(STRUCTURE_TRAIL_CUSHIONS)
    assert arms["off"] == {}
    assert len({tuple(sorted(fields.items())) for fields in arms.values()}) == len(arms)


def test_every_structure_trail_arm_is_the_stored_grid_with_only_the_trail_changed() -> None:
    """The arm is a variant dimension and not an axis, so an arm and its control pair row for row."""
    arms = structure_trail_arms()
    for root in COMMISSION:
        (campaign,) = insidebartrailing_variants(root)
        variants = insidebartrailing_structure_variants(root)
        assert [variant.name for variant in variants] == [f"trailing structure={arm}" for arm in arms]
        for variant, fields in zip(variants, arms.values(), strict=True):
            assert variant.axes == campaign.axes
            assert variant.archetype is campaign.archetype
            assert variant.base == replace(campaign.base, **fields)


def test_only_the_structure_trail_control_keeps_its_reconciliation() -> None:
    """No NinjaScript trails to structure, so every other arm's rows are ``TIER1_ONLY``."""
    for variant in insidebartrailing_structure_variants("MNQ"):
        control: bool = variant.name.endswith(" structure=off")
        expected = archetypes.Tier2Status.RECONCILED if control else archetypes.Tier2Status.TIER1_ONLY
        assert variant.archetype.tier2_for(variant.base) is expected


def test_no_structure_trail_variant_can_collide_with_a_stored_one_in_the_same_database() -> None:
    """Rows are separated by variant name alone, and ``campaign_holdout`` pairs the two windows one-to-one."""
    stored = {variant.name for variant in VARIANTS["InsideBarTrailing"]("MNQ")}
    names = [variant.name for variant in insidebartrailing_structure_variants("MNQ")]
    assert len(set(names)) == len(names)
    assert not stored & set(names)


def test_no_stored_grid_or_stratum_sweeps_a_field_a_structure_trail_arm_sets() -> None:
    """An axis over the same field would override the arm on every row, which is §M29's first-pass trap."""
    set_by_arms = {field for fields in structure_trail_arms().values() for field in fields}
    stratum_axes = {
        axis for which in (IBT_STRUCTURE, ALL_STRATA) for _, extra in strata(which) for axis in extra
    }
    (campaign,) = insidebartrailing_variants("MNQ")
    assert not set_by_arms & (stratum_axes | set(campaign.axes))


@pytest.mark.parametrize("which", [IBT_STRUCTURE, ALL_STRATA])
def test_every_structure_trail_grid_can_be_built_at_every_cell(which: str) -> None:
    """A grid that cannot be built is refused here, not an hour into the run."""
    for variant in insidebartrailing_structure_variants("NQ"):
        for _, grid in grids_for(variant, which):
            assert len(grid) == variant.sized()


def test_the_structure_trail_run_states_its_strata_before_it_runs() -> None:
    assert [name for name, _ in strata(IBT_STRUCTURE)] == [name for name, _ in strata(ALL_STRATA)]
    assert STRATUM_SETS[IBT_STRUCTURE] == STRATUM_SETS[ALL_STRATA]
    assert variants_for(IBT_STRUCTURE) is IBT_STRUCTURE_VARIANTS


# -- the structure-trail ladder's ends -------------------------------------------------------


def test_the_ladder_end_arms_are_every_rung_section_49_did_not_run() -> None:
    arms = structure_trail_end_arms()
    stored = structure_trail_arms()
    wide = len(STRUCTURE_TRAIL_WIDE_BARS) * len(STRUCTURE_TRAIL_WIDE_CUSHIONS)
    assert len(arms) == wide - (len(stored) - 1)
    assert not set(arms) & set(stored)
    for arm, fields in arms.items():
        past_an_end = fields["structure_trail_bars"] not in STRUCTURE_TRAIL_BARS
        past_an_end |= fields["structure_trail_cushion_atr"] not in STRUCTURE_TRAIL_CUSHIONS
        assert past_an_end, arm


def test_the_wide_ladders_widen_both_ends_of_the_box_and_the_top_of_the_cushion() -> None:
    assert min(STRUCTURE_TRAIL_WIDE_BARS) == 1 < min(STRUCTURE_TRAIL_BARS)
    assert max(STRUCTURE_TRAIL_WIDE_BARS) > max(STRUCTURE_TRAIL_BARS)
    assert min(STRUCTURE_TRAIL_WIDE_CUSHIONS) == min(STRUCTURE_TRAIL_CUSHIONS) == 0.0
    assert max(STRUCTURE_TRAIL_WIDE_CUSHIONS) > max(STRUCTURE_TRAIL_CUSHIONS)
    assert set(STRUCTURE_TRAIL_BARS) < set(STRUCTURE_TRAIL_WIDE_BARS)
    assert set(STRUCTURE_TRAIL_CUSHIONS) < set(STRUCTURE_TRAIL_WIDE_CUSHIONS)


def test_the_ladder_end_set_opens_with_section_49s_variants_unchanged() -> None:
    """Under their stored names, a sweep on §M49's bars skips them as stored and runs only the new arms."""
    for root in COMMISSION:
        stored = insidebartrailing_structure_variants(root)
        assert insidebartrailing_structure_end_variants(root)[: len(stored)] == stored


def test_every_new_ladder_end_arm_is_the_stored_grid_with_only_the_trail_changed() -> None:
    arms = structure_trail_end_arms()
    for root in COMMISSION:
        (campaign,) = insidebartrailing_variants(root)
        added = insidebartrailing_structure_end_variants(root)[len(structure_trail_arms()) :]
        assert [variant.name for variant in added] == [f"trailing structure_ends={arm}" for arm in arms]
        for variant, fields in zip(added, arms.values(), strict=True):
            assert variant.axes == campaign.axes
            assert variant.archetype is campaign.archetype
            assert variant.base == replace(campaign.base, **fields)


def test_no_new_ladder_end_arm_takes_a_name_already_in_the_database() -> None:
    taken = {variant.name for variant in VARIANTS["InsideBarTrailing"]("MNQ")}
    taken |= {variant.name for variant in insidebartrailing_structure_variants("MNQ")}
    names = [variant.name for variant in insidebartrailing_structure_end_variants("MNQ")]
    assert len(set(names)) == len(names)
    assert not taken & set(names[len(structure_trail_arms()) :])


def test_only_the_ladder_end_control_keeps_its_reconciliation() -> None:
    for variant in insidebartrailing_structure_end_variants("MNQ"):
        control: bool = variant.name.endswith(" structure=off")
        expected = archetypes.Tier2Status.RECONCILED if control else archetypes.Tier2Status.TIER1_ONLY
        assert variant.archetype.tier2_for(variant.base) is expected


def test_every_new_ladder_end_arm_is_a_legal_rule_set_at_every_cell() -> None:
    for variant in insidebartrailing_structure_end_variants("NQ")[len(structure_trail_arms()) :]:
        for _, grid in grids_for(variant, IBT_STRUCTURE_ENDS):
            assert sum(1 for _ in grid.combinations()) == variant.sized()


def test_the_ladder_end_run_states_the_same_strata_as_section_49() -> None:
    assert STRATUM_SETS[IBT_STRUCTURE_ENDS] == STRATUM_SETS[IBT_STRUCTURE]
    assert variants_for(IBT_STRUCTURE_ENDS) is IBT_STRUCTURE_ENDS_VARIANTS
