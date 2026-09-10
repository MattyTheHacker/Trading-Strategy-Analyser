r"""Sweep every registered archetype across resolution, market regime and session phase.

One screen over the whole registry, so "which strategy is worth improving" is a query rather
than six incomparable runs:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --strata context --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --split --strata phase --n-jobs 8

Both roots, the spliced continuous series, resolutions 1/2/5/10/15, at the real commission for
the root and one tick of slippage. ``--split`` re-runs the same grids on a selection window and
a held-out window instead of the whole series, which is what makes a shortlist testable rather
than a ranking of noise -- ``docs/roadmap.md`` § "Held out, and then the test it fails".

**One database per archetype**, under ``results/campaign/``. A convention rather than a
constraint since ``_append_or_create`` learned to widen a table instead of dropping what it
does not recognise; the campaign's results are already there -- ``docs/roadmap.md`` §M27.

**Strata are one dimension at a time, never crossed.** ``--strata core`` is unfiltered, then
once per regime and once per session phase; ``--strata context`` adds the volume, trend and
higher-timeframe cuts and appends to the same databases. Each dimension is also nameable on its
own -- ``unfiltered``, ``regime``, ``phase``, ``volume``, ``trend``, ``htf`` -- which is how a
held-out pass adds one at a time.

``--strata volume-forms`` re-cuts the volume dimension rather than adding one: a cell per
(form, tail size, state), so that "an unusually busy bar" and "an unusually busy session so
far" are separable statements rather than one of three the campaign happened to ask.
``--volume-quantiles`` fits each form's thresholds to its own distribution on the selection
window, for the reason ``--regime-quantiles`` fits the regime's -- a raw pair is a different
share of bars under each form. Neither it nor ``directional`` is in ``--strata all``, which
would otherwise run their dimension twice:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --strata volume-forms --split \
        --volume-quantiles --n-jobs 8

``--regime-quantiles`` replaces the regime stratum's raw thresholds with a pair fitted to the
efficiency ratio's own distribution at each ``(resolution, lookback)``, and splits the stratum
into one cell per lookback -- ``regime=DIRECTIONAL@n=20``. The fit is taken on the selection
window at every window, so a held-out run reads a cut it did not see. Why a raw pair cannot be
swept against the lookback, and what the quantiles are chosen for: ``docs/roadmap.md`` §M27.5.

``--variants narrow`` sweeps the §M27.3 re-sweep instead of the campaign grid -- InsideBar's
entry held at what §M27 chose, its bracket pair crossed, and ``--strata narrow`` for the two
cells it is asked about:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants narrow --strata narrow \
        --split --regime-quantiles --n-jobs 8

``--resolutions`` is not needed there: each narrow variant declares the one bar size its entry
was chosen at, and a resolution no variant expresses is skipped.

Its rows land in ``results/campaign/InsideBar.duckdb`` beside the campaign's under the variant
name ``narrow``; every reading tool takes ``--variant`` to separate them. **Run it once per
database** -- a second pass appends a second copy of every row and
``tools/campaign_holdout.py`` pairs the windows one-to-one.

``--variants orb-fade`` re-runs §M28.2's parked fade over the bracket it was parked for, with
``--strata orb-fade`` for the two cells stated in advance -- ``docs/roadmap.md`` §M28.5:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-fade --strata orb-fade --split

``--variants orb-rejection`` runs the fourth entry over that same bracket, so the two reversion
entries differ by their entry rule and nothing else -- ``docs/roadmap.md`` §M28.7:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-rejection --split \
        --strata orb-rejection

``--variants orb-geometry`` crosses the range's anchor with its length on all four entries,
each held at the bracket its own campaign swept -- ``docs/roadmap.md`` §M28.8:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-geometry --split \
        --strata orb-geometry

``--variants orb-bracket`` carries the stop fraction past ``1.0`` -- the value it stopped on
and won at -- and crosses it with the width target ladder, which no ORB campaign has varied
-- ``docs/roadmap.md`` §M28.11:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-bracket --split \
        --strata orb-bracket

``--variants orb-followthrough`` denominates the bracket in the **trailing** follow-through
rather than in the session's own range width, against a control run on the same bars in the
same pass -- ``docs/roadmap.md`` §M28.10:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-followthrough --split \
        --strata orb-followthrough

``--variants elastic-shape`` asks what the signal bar itself has to look like, over the VWAP
source §M26.4 left standing, with the no-requirement control in the same pass --
``docs/roadmap.md`` §M26.5:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants elastic-shape --split \
        --strata elastic-shape

``--variants elastic-volume`` crosses the shape §M26.5 carried forward with the volume
states, each cell cut on its own distribution rather than on a raw pair --
``docs/roadmap.md`` §M26.9:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants elastic-volume --split \
        --strata elastic-volume --volume-quantiles

``--variants elastic-recovery`` waits for the run outside the band to end and takes the
bar that closes back inside, against the shapes read on a bar still outside --
``docs/roadmap.md`` §M26.6:

    ./.venv/Scripts/python.exe tools/campaign_sweep.py --variants elastic-recovery --split \
        --strata elastic-recovery
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, NamedTuple

import pandas as pd

from nqbt import (
    archetypes,
    compression,
    context,
    higher_timeframe,
    logsetup,
    paths,
    regime,
    resample,
    results,
    sessionrange,
    splice,
    sweep,
    timeofday,
    trades,
    trend,
    volume,
)
from nqbt.arrays import float_column
from nqbt.instruments import get_instrument
from nqbt.sim.types import (
    BAND_VWAP,
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_REJECTION,
    ORB_ENTRY_RETEST,
    ORB_SCALE_BOTH,
    ORB_SCALE_NONE,
    ORB_SCALE_STOP,
    ORB_SCALE_TARGET,
    ORB_STOP_ATR,
    ORB_STOP_FRACTION,
    ORB_STOP_OPPOSITE,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    REQUIRE_ALL,
    SHAPE_ANY,
    SHAPE_RECLAIM,
    SHAPE_REJECTION,
    SHAPE_REVERSAL,
    STOP_ATR,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_STRETCH,
    TRIGGER_EXTENDED,
    TRIGGER_RECOVERY,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from nqbt.archetypes import Archetype, AxisValue, Params

logger = logging.getLogger(__name__)

ROOTS = ("MNQ", "NQ")

COMMISSION: dict[str, float] = {"MNQ": 1.50, "NQ": 4.50}
"""Round-turn dollars per contract, per root. Never one figure for both -- the point value
differs tenfold and the commission does not, so MNQ's number applied to NQ flatters it."""

SLIPPAGE_TICKS = 1.0

RESOLUTIONS = (1, 2, 5, 10, 15)

SELECTION_SHARE = 0.6
"""Share of the series, by bar count, that ``--split`` selects on. The rest is held out."""

REGIME_LOOKBACKS = (5, 10, 20, 30, 50)
"""Horizons the regime label can describe, swept once ``--regime-quantiles`` makes the cells
comparable across them -- ``docs/roadmap.md`` §M27.5."""

REGIME_QUANTILES = (0.20, 0.80)
"""The cell size ``--regime-quantiles`` defaults to: a fifth of the measured bars in each of
CONSOLIDATING and DIRECTIONAL, stated ahead of the sweep rather than discovered in it."""

VOLUME_ROLLING_BARS = 30
VOLUME_BASELINE_SESSIONS = 20
"""The window and baseline §M27 ran at, held so that the form is what moves. Both are
``sim/types.py`` defaults, which is what makes the ``PER_BAR`` cells here the campaign's own."""

VOLUME_TAILS = ((0.10, 0.90), (0.20, 0.80), (0.33, 0.67))
"""Tail sizes ``--volume-quantiles`` fits, each stated as a share of the measured bars.

Three rather than one because the cut is what decides who is in ``HEAVY``, and a stratification
read off a single unexamined cut is the cut's result -- ``docs/roadmap.md`` §M27.8."""

COMPRESSION_PERIOD = 20
COMPRESSION_BASELINE_BARS = 250
"""The width window and the trailing window every compression cell runs at, held so that the
form is what moves. Both are ``sim/types.py`` defaults -- ``docs/roadmap.md`` §M19.1."""

MIN_TRADES = 30
"""The floor ``sweep.rank`` applies, repeated here for the per-sweep progress line."""

CAMPAIGN_DIR = paths.RESULTS_DIR / "campaign"

NAN = float("nan")


UNFILTERED = "unfiltered"
REGIME = "regime"
DIRECTIONAL = "directional"
CONSOLIDATING = "consolidating"
VOLUME_FORMS = "volume-forms"
COMPRESSION_FORMS = "compression-forms"
CORE = "core"
CONTEXT = "context"
NARROW = "narrow"
TREND_UP = "trend-up"
ORB = "orb"
ORB_FADE = "orb-fade"
ORB_REJECTION = "orb-rejection"
ORB_GEOMETRY = "orb-geometry"
ORB_FOLLOW_THROUGH = "orb-followthrough"
ORB_BRACKET = "orb-bracket"
ELASTIC_SHAPE = "elastic-shape"
ELASTIC_VOLUME = "elastic-volume"
ELASTIC_RECOVERY = "elastic-recovery"
SPEC = "spec"
ALL_STRATA = "all"

Calibration = dict[int, tuple[float, float]]
"""Regime lookback -> the threshold pair fitted at it, one entry per swept lookback."""


class VolumeCut(NamedTuple):
    """One relative-volume series, the tail size asked of it, and the pair that fitted to."""

    series: volume.VolumeKey
    thin_below: float
    heavy_above: float
    tails: tuple[float, float] | None = None
    """``None`` where the thresholds are the campaign's raw pair rather than a fit."""

    @property
    def name(self) -> str:
        """What a stratum cut this way is called, which is what separates it in the table."""
        stated: str = "raw" if self.tails is None else f"{self.tails[0]:.2f}/{self.tails[1]:.2f}"

        return f"{volume.describe_key(self.series)} q={stated}"


VolumeCalibration = tuple[VolumeCut, ...]
"""Every (series, tail size) a volume-form stratification runs, each carrying its own cut."""


@dataclass(frozen=True, slots=True)
class Cuts:
    """The fitted cut points one sweep point's strata are defined by, a field per dimension.

    One object rather than one argument each, because every reader of a stratum group needs the
    dimension it owns and none of them needs the others.
    """

    regime: Calibration | None = None
    volume: VolumeCalibration = ()


NO_CUTS = Cuts()
"""What an uncalibrated run passes: the stratum names the stored databases already carry."""


def _unfiltered() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """No context filter at all: the baseline every other stratum is read against."""
    yield UNFILTERED, {}


def _regime() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per efficiency-ratio regime."""
    for state in regime.Regime:
        yield f"regime={state.name}", {"regime_filter": [state.bit]}


def _directional() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The one regime cell a narrow re-sweep runs inside, without its four siblings.

    Its own group rather than ``--strata regime`` because four cells nobody is asking about are
    four more comparisons -- ``docs/roadmap.md`` §M27.3.
    """
    yield f"regime={regime.Regime.DIRECTIONAL.name}", {"regime_filter": [regime.Regime.DIRECTIONAL.bit]}


def _consolidating() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The regime cell a fade's own thesis names, without its four siblings.

    :func:`_directional` is the breakout's thesis, and running a fade inside it would be
    stating the wrong hypothesis in advance -- ``docs/roadmap.md`` §M28.5.
    """
    yield f"regime={regime.Regime.CONSOLIDATING.name}", {"regime_filter": [regime.Regime.CONSOLIDATING.bit]}


def _trend_up() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The one trend cell §M28.1's gate 3 passed in on both roots, without its siblings.

    Its own group so that the opening range's re-sweep can **name its strata before it runs**
    rather than pick them from the results afterwards, which is the caveat §M28.1 left for
    [#237] -- ``docs/roadmap.md`` §M28.2.
    """
    yield f"trend={trend.Trend.UP.name}", {"trend_filter": [trend.Trend.UP.bit]}


def _phase() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per session phase."""
    for phase in timeofday.SessionPhase:
        yield f"phase={phase.name}", {"phase_filter": [phase.bit]}


def _volume() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per relative-volume state, at the one form and the one cut §M27 ran."""
    for state in volume.VolumeState:
        yield f"volume={state.name}", {"volume_filter": [state.bit]}


def volume_series() -> tuple[volume.VolumeKey, ...]:
    """The three relative-volume series a form stratification reads.

    Built through :func:`nqbt.volume.key`, which drops the rolling window from every form but
    ``ROLLING`` -- the blind spot ``dead_axes`` cannot see, avoided rather than rediscovered.
    """
    return tuple(
        volume.key(form, VOLUME_ROLLING_BARS, VOLUME_BASELINE_SESSIONS) for form in volume.VolumeForm
    )


def raw_volume_cuts() -> VolumeCalibration:
    """The three forms at the campaign's own thresholds, which is what an unfitted run compares."""
    defaults: DeadCatParams = DeadCatParams()

    return tuple(
        VolumeCut(series, defaults.volume_thin_below, defaults.volume_heavy_above)
        for series in volume_series()
    )


def _volume_axes(cut: VolumeCut) -> dict[str, list[AxisValue]]:
    """The series and the cut one volume-form stratum reads.

    The rolling window is set only under the form that reads it, so the axis does not vary where
    it is inert and no combination is run twice -- ``.claude/rules/sweep-and-context.md``.
    """
    axes: dict[str, list[AxisValue]] = {
        "volume_form": [int(cut.series.form)],
        "volume_baseline_sessions": [cut.series.baseline_sessions],
        "volume_thin_below": [cut.thin_below],
        "volume_heavy_above": [cut.heavy_above],
    }
    if cut.series.form is volume.VolumeForm.ROLLING:
        axes["volume_rolling_bars"] = [cut.series.rolling_bars]

    return axes


def _volume_cells(cuts: VolumeCalibration) -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per (series, tail size, state): which of the three statements an edge belongs to."""
    for cut in cuts:
        for state in volume.VolumeState:
            yield f"volume={state.name}@{cut.name}", _volume_axes(cut) | {"volume_filter": [state.bit]}


def _volume_forms() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The form stratification at the raw thresholds, which is what an unfitted run gets."""
    yield from _volume_cells(raw_volume_cuts())


def _compression_axes(form: compression.CompressionForm) -> dict[str, list[AxisValue]]:
    """The series one compression stratum reads. Both forms read every axis, so none is dropped."""
    return {
        "compression_form": [int(form)],
        "compression_period": [COMPRESSION_PERIOD],
        "compression_baseline_bars": [COMPRESSION_BASELINE_BARS],
    }


def _compression() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per compression state, at the one form and the one cut a first pass runs."""
    for state in compression.Compression:
        yield f"compression={state.name}", {"compression_filter": [state.bit]}


def _compression_forms() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per (form, state): whether a narrow band and a short range say the same thing.

    The cut stays the campaign's raw pair rather than a fitted one, because a trailing rank
    already means the same share of bars in every cell -- ``docs/roadmap.md`` §M19.1.
    """
    for form in compression.CompressionForm:
        for state in compression.Compression:
            yield (
                f"compression={state.name}@{form.name.lower()}",
                _compression_axes(form) | {"compression_filter": [state.bit]},
            )


def _trend() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per compact trend label."""
    for label in trend.Trend:
        yield f"trend={label.name}", {"trend_filter": [label.bit]}


def _higher_timeframe() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Once per side of the 60-minute average."""
    for side in higher_timeframe.Side:
        yield f"htf={side.name}", {"higher_timeframe_filter": [side.bit]}


STRATUM_GROUPS = {
    UNFILTERED: _unfiltered,
    REGIME: _regime,
    DIRECTIONAL: _directional,
    CONSOLIDATING: _consolidating,
    "phase": _phase,
    "volume": _volume,
    VOLUME_FORMS: _volume_forms,
    "compression": _compression,
    COMPRESSION_FORMS: _compression_forms,
    "trend": _trend,
    TREND_UP: _trend_up,
    "htf": _higher_timeframe,
}
"""One generator per context dimension. **Never crossed** -- one dimension at a time is what
tells "no edge anywhere" from "edge in one stratum, drowned by the others"."""

REGIME_GROUPS = frozenset({REGIME, DIRECTIONAL, CONSOLIDATING})
"""Groups whose cells ``--regime-quantiles`` splits per lookback. Membership rather than one
name, so that a group yielding a single regime cell is calibrated like the full one."""

RECUTS = frozenset({DIRECTIONAL, CONSOLIDATING, TREND_UP, VOLUME_FORMS, COMPRESSION_FORMS})
"""Groups that re-cut a dimension another group already owns, so ``all`` leaves them out.

``directional`` and ``consolidating`` are each one regime cell without its four siblings, and
``trend-up`` one trend cell without its two; ``volume-forms`` is the volume
dimension under all three forms and a fitted cut; ``compression-forms`` is the compression
dimension under both of its forms. Any of them inside ``all`` would run its dimension twice
under two sets of names."""

ORB_REVERSION_STRATA = (UNFILTERED, CONSOLIDATING)
"""The two cells both reversion entries are asked about, stated before either run.

A range that holds is a range worth trading back from, so `regime=CONSOLIDATING` is the fade's
and the rejection's own thesis where `regime=DIRECTIONAL` is the breakout's -- one tuple
because it is one hypothesis, read twice."""

STRATUM_SETS: dict[str, tuple[str, ...]] = {
    **{group: (group,) for group in STRATUM_GROUPS},
    CORE: (UNFILTERED, "regime", "phase"),
    CONTEXT: ("volume", "compression", "trend", "htf"),
    NARROW: (UNFILTERED, DIRECTIONAL),
    ORB: (UNFILTERED, DIRECTIONAL, TREND_UP),
    ORB_FADE: ORB_REVERSION_STRATA,
    ORB_REJECTION: ORB_REVERSION_STRATA,
    ORB_GEOMETRY: (UNFILTERED,),
    ORB_FOLLOW_THROUGH: (UNFILTERED,),
    ORB_BRACKET: (UNFILTERED,),
    ELASTIC_SHAPE: (UNFILTERED,),
    ELASTIC_VOLUME: (UNFILTERED, VOLUME_FORMS),
    ELASTIC_RECOVERY: (UNFILTERED,),
    SPEC: (UNFILTERED,),
    ALL_STRATA: tuple(group for group in STRATUM_GROUPS if group not in RECUTS),
}
"""Named combinations of those groups, so a later pass can append the dimensions an earlier one
skipped rather than re-running it. Every dimension is also selectable on its own, which is what
lets a held-out pass take them one at a time -- ``docs/roadmap.md`` §M27.4."""


def _per_lookback(
    name: str,
    axes: dict[str, list[AxisValue]],
    calibration: Calibration,
) -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Split one regime cell into a cell per lookback, each carrying its own fitted thresholds.

    A cell rather than an axis because the thresholds move *with* the lookback, and a sweep
    crosses its axes -- pairing them any other way runs cells that are not comparable.
    """
    for lookback, (consolidating, directional) in calibration.items():
        yield (
            f"{name}@n={lookback}",
            axes
            | {
                "regime_lookback": [lookback],
                "regime_consolidating_below": [consolidating],
                "regime_directional_above": [directional],
            },
        )


def strata(
    which: str,
    cuts: Cuts = NO_CUTS,
) -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """The stratifications ``which`` names, unfiltered first wherever it is included."""
    for group in STRATUM_SETS[which]:
        if group == VOLUME_FORMS and cuts.volume:
            yield from _volume_cells(cuts.volume)
            continue

        for name, axes in STRATUM_GROUPS[group]():
            if group not in REGIME_GROUPS or cuts.regime is None:
                yield name, axes
                continue

            yield from _per_lookback(name, axes, cuts.regime)


def calibrate(
    frame: pd.DataFrame,
    lookbacks: Sequence[int],
    quantiles: tuple[float, float],
) -> Calibration:
    """Fit a threshold pair per lookback to ``frame``'s own efficiency ratios."""
    grid: regime.EfficiencyRatioGrid = regime.efficiency_ratio_grid(float_column(frame, "close"), lookbacks)

    return {lookback: grid.thresholds_for(lookback, *quantiles) for lookback in sorted(lookbacks)}


def calibrate_volume(
    frame: pd.DataFrame,
    minutes: int,
    tails: Sequence[tuple[float, float]],
) -> VolumeCalibration:
    """Fit a threshold pair per (series, tail size) to ``frame``'s own relative volumes.

    Each form is fitted against its own distribution, which is the whole point: the same raw
    pair sits at a different percentile under each of the three -- ``docs/roadmap.md`` §M27.8.
    """
    series: tuple[volume.VolumeKey, ...] = volume_series()
    spec = context.ContextSpec(volume_keys=series, needs_time_of_day=True)
    data: context.Dataset = context.prepare(frame, spec, bar_minutes=minutes)

    return tuple(
        VolumeCut(key, *volume.thresholds_from_quantiles(data.relative_volume(key), *pair), tails=pair)
        for key in series
        for pair in tails
    )


@dataclass(frozen=True, slots=True)
class Variant:
    """One base parameter set and the axes swept over it, under a name the results carry.

    A variant exists where an axis cannot express the difference: a target ladder is a tuple
    and tuples are not sweepable, and two stop modes read different axes.
    """

    name: str
    archetype: Archetype
    base: Params
    axes: dict[str, list[AxisValue]] = field(default_factory=dict)
    resolutions: tuple[int, ...] = RESOLUTIONS
    """Bar sizes this variant can be run at.

    Every variant but the opening range's is expressible at all of them. A session-anchored
    range is not: its anchor and its window must both be whole numbers of bars, so a 5-minute
    range does not exist on 10-minute bars -- ``docs/roadmap.md`` §M28.
    """

    def sized(self) -> int:
        """How many combinations this variant's own axes make."""
        total: int = 1
        for values in self.axes.values():
            total *= len(values)

        return total

    def runs_at(self, minutes: int) -> bool:
        """Whether this variant is expressible at one resolution."""
        return minutes in self.resolutions


def _costed(params: Params, root: str) -> Params:
    """The same rule set with this root's real costs on it."""
    return replace(params, commission_per_contract=COMMISSION[root], slippage_ticks=SLIPPAGE_TICKS)


def deadcat_variants(root: str) -> list[Variant]:
    """One variant: the entry gates, the moving-average kind, and how far the targets sit."""
    return [
        Variant(
            name="bracket",
            archetype=archetypes.DEADCATBOUNCE,
            base=_costed(DeadCatParams(), root),
            axes={
                "ema_kind": ["ema", "sma", "wma", "hma"],
                "ema_period": [9, 15, 21, 30],
                "fast_sma_period": [40, 60, 80],
                "use_vwap": [False, True],
                "tp_multiplier": [1.0, 1.5, 2.0],
            },
        ),
    ]


def pullback_variants(root: str) -> list[Variant]:
    """One variant: all three gates are on by default, so all three periods are live."""
    return [
        Variant(
            name="ratchet",
            archetype=archetypes.PULLBACKANDGO,
            base=_costed(PullBackAndGoParams(), root),
            axes={
                "ema_kind": ["ema", "sma", "wma", "hma"],
                "ema_period": [9, 15, 21, 30],
                "fast_sma_period": [40, 60, 80],
                "slow_sma_period": [125, 175],
                "use_vwap": [False, True],
            },
        ),
    ]


def crossover_variants(root: str) -> list[Variant]:
    """Two variants, one per stop geometry, because each reads an axis the other ignores.

    Sweeping ``atr_stop_multiple`` under the swing stop would run identical combinations and
    ``dead_axes`` cannot see it -- ``.claude/rules/sweep-and-context.md``.
    """
    shared: dict[str, list[AxisValue]] = {
        "fast_kind": ["ema", "sma", "wma", "hma"],
        "fast_period": [5, 9, 13, 20],
        "slow_period": [30, 50, 100, 200],
        "tp_multiplier": [1.0, 2.0],
        "exit_on_opposite_cross": [True, False],
    }

    return [
        Variant(
            name="stop=atr",
            archetype=archetypes.EMACROSSOVER,
            base=_costed(EmaCrossoverParams(use_atr_stop=True), root),
            axes={**shared, "atr_stop_multiple": [1.5, 3.0]},
        ),
        Variant(
            name="stop=swing",
            archetype=archetypes.EMACROSSOVER,
            base=_costed(EmaCrossoverParams(use_atr_stop=False), root),
            axes={**shared, "swing_lookback": [1, 3]},
        ),
    ]


def insidebar_variants(root: str) -> list[Variant]:
    """One variant: the three gates, the breakout margin and the lopsided ATR geometry."""
    return [
        Variant(
            name="bracket",
            archetype=archetypes.INSIDEBAR,
            base=_costed(InsideBarParams(), root),
            axes={
                "ema_kind": ["ema", "hma"],
                "ema_period": [11, 22, 44],
                "fast_sma_period": [20, 35, 50],
                "slow_sma_period": [100, 200],
                "error_margin": [0.01, 0.1],
                "atr_length": [3, 14],
                "atr_multiplier": [5.0, 10.0, 20.0],
            },
        ),
    ]


NARROW_ENTRY: dict[int, dict[str, AxisValue]] = {
    5: {"ema_kind": "hma", "ema_period": 22, "error_margin": 0.1, "atr_length": 14},
    10: {"ema_kind": "hma", "ema_period": 11, "error_margin": 0.1, "atr_length": 3},
}
"""InsideBar's entry, held per resolution at the modal value of §M27's own DIRECTIONAL top
twenty, so that the re-sweep varies the bracket and nothing else.

Where that twenty is tied -- ``fast_sma_period`` at both resolutions, ``slow_sma_period`` at ten
minutes -- the NinjaScript default stands rather than a coin flip, which is the campaign's own
finding that the moving-average axes barely matter. Chosen on profit factor because §M27 ranked
that way; **held**, never re-tuned -- ``docs/roadmap.md`` §M27.3."""

NARROW_TP = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
"""Target distances in ATRs from the fill. Opens at the ``1.0`` the campaign was stuck with and
runs well past it, because the lopsided bracket is what Gate 4 stops on."""

NARROW_ATR = [2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
"""Stop distances in ATRs beyond the signal bar. Covers §M27's 5/10/20 and extends below it,
since a tighter stop is the other half of the same asymmetry."""


def insidebar_narrow_variants(root: str) -> list[Variant]:
    """One variant per resolution: the campaign's entry, crossed over the bracket it never swept.

    Two variants rather than one because the entry §M27 chose differs between five and ten
    minutes, and a ``Variant`` carries one base -- ``docs/roadmap.md`` §M27.3.
    """
    return [
        Variant(
            name=NARROW,
            archetype=archetypes.INSIDEBAR,
            base=_costed(InsideBarParams(**entry), root),  # type: ignore[arg-type]  # keyed by field name
            axes={"tp_multiplier": [*NARROW_TP], "atr_multiplier": [*NARROW_ATR]},
            resolutions=(minutes,),
        )
        for minutes, entry in NARROW_ENTRY.items()
    ]


def insidebartrailing_variants(root: str) -> list[Variant]:
    """One variant: InsideBar's entry against the split-lot trailing exit's own axes."""
    return [
        Variant(
            name="trailing",
            archetype=archetypes.INSIDEBARTRAILING,
            base=_costed(InsideBarTrailingParams(), root),
            axes={
                "ema_period": [11, 22, 44],
                "fast_sma_period": [20, 35, 50],
                "error_margin": [0.05, 0.1],
                "atr_length": [3, 14],
                "partial_take_profit_percentage": [0.3, 0.5, 0.6, 0.8],
                "trailing_stop_multiplier": [2.0, 5.0, 10.0],
            },
        ),
    ]


ELASTIC_LADDERS: dict[str, tuple[float, ...]] = {
    "target=-0.5s": (-0.5, NAN),
    "target=0.0s": (0.0, NAN),
    "target=+1.0s": (1.0, NAN),
    "target=+2.0s": (2.0, NAN),
}
"""Where the scaled-out leg exits, in standard deviations from the basis, signed towards the
trade. A variant each because a tuple is not a sweepable axis -- ``docs/roadmap.md`` §M26."""


def elastic_ladder(variant: str) -> tuple[float, ...]:
    """The target ladder a stored ElasticBand variant name carries.

    The ladder is a tuple and tuples are not sweepable, so it is not a stored column and has to
    be read back off the variant name -- which carries other words in the §M26.5 set, hence the
    token rather than the whole name.
    """
    for token in variant.split():
        if token in ELASTIC_LADDERS:
            return ELASTIC_LADDERS[token]

    msg = f"no target ladder in the ElasticBand variant name {variant!r}; known: {sorted(ELASTIC_LADDERS)}"
    raise KeyError(msg)


def elasticband_variants(root: str) -> list[Variant]:
    """One variant per target ladder, each sweeping the entry, the stop mode and a time stop."""
    axes: dict[str, list[AxisValue]] = {
        "band_period": [10, 20, 50],
        "entry_std": [1.5, 2.0, 2.5, 3.0],
        "min_bars_outside": [1, 2],
        "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
        "max_hold_bars": [0, 30],
    }

    return [
        Variant(
            name=name,
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(target_mode=TARGET_STRETCH, target_stretch_levels=levels),
                root,
            ),
            axes=axes,
        )
        for name, levels in ELASTIC_LADDERS.items()
    ]


ELASTIC_SHAPE_TARGETS = ("target=0.0s", "target=+1.0s")
"""Two of :data:`ELASTIC_LADDERS`' four: the midline, and the one patience found.

Named out of that dict rather than restated, so :func:`elastic_ladder` resolves a variant from
either set and the two campaigns cannot drift apart on what a ladder name means."""

ELASTIC_SHAPES: dict[str, tuple[int, float]] = {
    "shape=any": (SHAPE_ANY, 0.5),
    "shape=reversal": (SHAPE_REVERSAL, 0.5),
    "shape=reclaim": (SHAPE_RECLAIM, 0.5),
    "shape=rejection@0.4": (SHAPE_REJECTION, 0.4),
    "shape=rejection@0.6": (SHAPE_REJECTION, 0.6),
}
"""What the signal bar itself has to look like, and the rejection depth where one is read.

A variant rather than an axis for the reason every mode in this file is one: the fraction is
inert under three of the four modes, so crossing them would run identical combinations that
`dead_axes` cannot see -- ``docs/roadmap.md`` §M26.5. ``shape=any`` is the control: the same
axes, over the entry §M26.4 left the archetype at, with no requirement on the bar at all.
"""


def elasticband_shape_variants(root: str) -> list[Variant]:
    """§M26.5's run: what the signal bar looks like, over the source §M26.4 left standing.

    The VWAP source alone, because §M26.4 is what established that the Bollinger one does not
    survive a holdout -- so the question here is the signal bar and not the channel.
    """
    axes: dict[str, list[AxisValue]] = {
        "entry_std": [2.0, 2.5, 3.0],
        "min_one_sided_bars": [0, 4, 6, 8],
        "min_bars_outside": [1, 2],
        "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
        "max_hold_bars": [0, 30],
    }

    return [
        Variant(
            name=f"{shape_name} {target_name}",
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(
                    band_source=BAND_VWAP,
                    signal_shape=shape,
                    rejection_close_fraction=fraction,
                    one_sided_lookback=10,
                    target_mode=TARGET_STRETCH,
                    target_stretch_levels=levels,
                ),
                root,
            ),
            axes=axes,
        )
        for shape_name, (shape, fraction) in ELASTIC_SHAPES.items()
        for target_name in ELASTIC_SHAPE_TARGETS
        for levels in [ELASTIC_LADDERS[target_name]]
    ]


ELASTIC_VOLUME_SHAPES: dict[str, int] = {
    "shape=any": SHAPE_ANY,
    "shape=reversal": SHAPE_REVERSAL,
}
"""The control and the one shape §M26.5 carried forward, which is the pair the volume question
is asked over. The other three shapes are not here: §M26.5 eliminated ``rejection`` on the
held-out gate and left ``reclaim`` behind ``reversal`` on the drawdown check."""

ELASTIC_VOLUME_TARGET = "target=0.0s"
"""The ladder §M26.5 read its drawdown and null tables on. Held rather than swept because the
target ladder's eta-squared on the held-out profit factor there was 0.0000."""


def elasticband_volume_variants(root: str) -> list[Variant]:
    """§M26.9's run: the shape crossed with the volume states, over a bracket held still.

    Three of §M26.5's five axes are held rather than swept, so that the cells this adds are the
    volume strata and not a wider grid: ``min_one_sided_bars`` because §M26.5 measured its low
    end as a dead value and its high end as a cost, ``min_bars_outside`` because the reversal
    shape makes it a duplicate on 82.7% of cells, and the target ladder above.
    """
    axes: dict[str, list[AxisValue]] = {
        "entry_std": [2.0, 2.5, 3.0],
        "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
        "max_hold_bars": [0, 30],
    }

    return [
        Variant(
            name=f"break-volume {shape_name} {ELASTIC_VOLUME_TARGET}",
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(
                    band_source=BAND_VWAP,
                    signal_shape=shape,
                    target_mode=TARGET_STRETCH,
                    target_stretch_levels=ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET],
                ),
                root,
            ),
            axes=axes,
        )
        for shape_name, shape in ELASTIC_VOLUME_SHAPES.items()
    ]


ELASTIC_RECOVERY_TARGET = "target=0.0s"
"""The ladder §M26.5 and §M26.9 both read their tables on, held here for the same reason: its
eta-squared on the held-out profit factor was 0.0000."""

ELASTIC_RECOVERY_ARMS: dict[str, tuple[int, int, float]] = {
    "entry=extended shape=any": (TRIGGER_EXTENDED, SHAPE_ANY, 1.0),
    "entry=extended shape=reversal": (TRIGGER_EXTENDED, SHAPE_REVERSAL, 1.0),
    "entry=recovery@1.0": (TRIGGER_RECOVERY, SHAPE_ANY, 1.0),
    "entry=recovery@0.9": (TRIGGER_RECOVERY, SHAPE_ANY, 0.9),
    "entry=recovery@0.75": (TRIGGER_RECOVERY, SHAPE_ANY, 0.75),
}
"""Which bar of an extension signals, and how far back inside the recovery bar has to close.

The trigger and its depth are one variant dimension for the reason every mode in this file is
one: the depth is inert under :data:`TRIGGER_EXTENDED`, so crossing them would run identical
combinations that ``dead_axes`` cannot see. Two controls rather than one, because §M26.5's
question was whether requiring a reaction beats requiring nothing and this one is whether
waiting for it beats reading it off a bar that is still outside -- ``docs/roadmap.md`` §M26.6.

**A fourth depth was measured and left out.** At 0.5 the gate leaves 140 signals in 1.66M MNQ
bars, which is the engulfing mode's failure and not a range worth sweeping -- §M26.6 has the
counts per resolution.
"""


def elasticband_recovery_variants(root: str) -> list[Variant]:
    """§M26.6's run: the recovery trigger against the shapes, over §M26.5's channel.

    §M26.5's grid minus ``min_one_sided_bars``, which it measured as a dead value at its low
    end and a cost at its high one. ``min_bars_outside`` stays, because the recovery trigger is
    the one entry here under which it is not a duplicate of the requirement beside it.
    """
    axes: dict[str, list[AxisValue]] = {
        "entry_std": [2.0, 2.5, 3.0],
        "min_bars_outside": [1, 2],
        "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
        "max_hold_bars": [0, 30],
    }

    return [
        Variant(
            name=f"{arm} {ELASTIC_RECOVERY_TARGET}",
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(
                    band_source=BAND_VWAP,
                    entry_trigger=trigger,
                    recovery_fraction=depth,
                    signal_shape=shape,
                    target_mode=TARGET_STRETCH,
                    target_stretch_levels=ELASTIC_LADDERS[ELASTIC_RECOVERY_TARGET],
                ),
                root,
            ),
            axes=axes,
        )
        for arm, (trigger, shape, depth) in ELASTIC_RECOVERY_ARMS.items()
    ]


ORB_WINDOWS = (5, 15, 30)
"""Opening-range windows, the three every source means -- ``docs/roadmap.md`` §M28."""


def orb_resolutions(anchor: int, window: int) -> tuple[int, ...]:
    """Which campaign resolutions can express a range of ``window`` minutes from ``anchor``.

    Both the anchor and the window have to be whole numbers of bars, which is why this is
    computed rather than written down: off the 930-minute cash anchor, 5-minute ranges survive
    at two resolutions of the five and 30-minute ranges at all of them.
    """
    return tuple(minutes for minutes in RESOLUTIONS if anchor % minutes == 0 and window % minutes == 0)


def openingrange_variants(root: str) -> list[Variant]:
    """One variant per (window, stop, target), because each triple reads axes the others do not.

    The window has to be a variant rather than an axis: it decides which resolutions the range
    exists at, and a sweep crosses its axes uniformly across every axis point.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "entry_offset_ticks": [1, 4],
        "max_entries_per_session": [1, 0],
    }
    stops: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
        "stop=opposite": (ORB_STOP_OPPOSITE, {"stop_offset_ticks": [1, 8]}),
        "stop=atr": (ORB_STOP_ATR, {"atr_stop_multiple": [1.0, 2.0]}),
    }
    targets: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
        "target=R": (ORB_TARGET_R, {"tp_multiplier": [1.0, 2.0]}),
        "target=width": (ORB_TARGET_WIDTH, {}),
    }

    return [
        Variant(
            name=f"window={window}m {stop_name} {target_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(window_minutes=window, stop_mode=stop_mode, target_mode=target_mode),
                root,
            ),
            axes={**shared, **stop_axes, **target_axes},
            resolutions=orb_resolutions(sessionrange.CASH_OPEN_MINUTES, window),
        )
        for window in ORB_WINDOWS
        for stop_name, (stop_mode, stop_axes) in stops.items()
        for target_name, (target_mode, target_axes) in targets.items()
    ]


LONDON_OPEN_MINUTES = sessionrange.anchor_for(timeofday.SessionPhase.LONDON)
"""Minutes from the 18:00 ET session open to the 03:00 ET European open -- §M28's third anchor."""

ORB_RANGES: dict[str, sessionrange.RangeKey] = {
    "cash=5m": (sessionrange.CASH_OPEN_MINUTES, 5),
    "cash=15m": (sessionrange.CASH_OPEN_MINUTES, 15),
    "cash=30m": (sessionrange.CASH_OPEN_MINUTES, 30),
    "overnight": (sessionrange.ETH_OPEN_MINUTES, sessionrange.CASH_OPEN_MINUTES),
    "london=60m": (LONDON_OPEN_MINUTES, 60),
}
"""The ranges the §M28.2 re-sweep trades: §M28's anchor axis, which §M28.1 never left.

``overnight`` is the session open through to the cash open, which is what "the overnight range"
and FX's "London breakout" both name; ``london=60m`` is the first hour of the European cash
session. Both were free once the range primitive was session-anchored -- ``docs/roadmap.md``
§M28.2.
"""

ORB_ENTRIES: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
    "entry=breakout": (ORB_ENTRY_BREAKOUT, {"entry_offset_ticks": [1, 4]}),
    "entry=fade": (ORB_ENTRY_FADE, {"entry_offset_ticks": [1, 4], "break_confirm_ticks": [0, 8]}),
    "entry=retest": (ORB_ENTRY_RETEST, {"retest_offset_ticks": [0, 4], "break_confirm_ticks": [0, 8]}),
}
"""The three entry mechanisms, each with the axes only it reads.

A variant dimension rather than an axis because of exactly that: ``entry_offset_ticks`` is
inert for a retest and ``retest_offset_ticks`` for the other two, and a grid crosses its axes
uniformly. ``docs/roadmap.md`` §M28.2.
"""

type OrbTarget = tuple[str, int, tuple[float, ...], dict[str, list[AxisValue]]]
"""One target scheme: its name, the mode, the per-leg ladder and the axes only it reads."""

ORB_TARGETS: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
    "target=R": (ORB_TARGET_R, {"tp_multiplier": [1.0, 2.0]}),
    "target=width": (ORB_TARGET_WIDTH, {}),
}
"""The two target schemes §M28.2 crossed every entry with, at the default width ladder.

``tp_multiplier`` scales an R target and is not read under :data:`ORB_TARGET_WIDTH`, so it is
swept where it lives rather than shared -- ``docs/roadmap.md`` §M28.2.
"""


def _orb_further_targets() -> list[OrbTarget]:
    """:data:`ORB_TARGETS` in the shape :func:`_orb_fade_targets` returns.

    The ladder is the parameter default rather than a copy of it, so a variant built here and
    one §M28.2 stored carry the same tuple.
    """
    default: tuple[float, ...] = OpeningRangeParams().target_width_multiples

    return [(name, mode, default, axes) for name, (mode, axes) in ORB_TARGETS.items()]


ORB_FRACTIONS = [0.25, 0.5, 0.75, 1.0]
"""How far back across the range the stop sits, in range widths.

**One axis where §M28.1 had two modes**: ``1.0`` reproduces the opposite-extreme stop exactly,
offset included, and ``0.5`` is the midpoint stop the literature also uses -- so the axis
contains the only stop that passed gate 1 rather than running beside it. The ATR stop is gone,
which is §M28.1's own deferral: 0 of 10 cells and half the runtime.
"""


def openingrange_further_variants(root: str) -> list[Variant]:
    """§M28.2's re-sweep: the anchor axis, the three entry mechanisms and one stop axis.

    One variant per (range, entry, target), because each triple reads axes the others do not
    and because the range decides which resolutions exist at all -- ``Variant.resolutions``.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "max_entries_per_session": [1, 0],
        "stop_range_fraction": [*ORB_FRACTIONS],
    }

    return [
        Variant(
            name=f"{range_name} {entry_name} {target_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=entry_mode,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=target_mode,
                ),
                root,
            ),
            axes={**shared, **entry_axes, **target_axes},
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in ORB_RANGES.items()
        for entry_name, (entry_mode, entry_axes) in ORB_ENTRIES.items()
        for target_name, (target_mode, target_axes) in ORB_TARGETS.items()
    ]


ORB_TIGHT_FRACTIONS = [0.02, 0.05, 0.10, 0.25]
"""How far outside the extreme a fade's stop sits, in range widths -- §M28.5's axis.

**A fade's stop runs outward where a breakout's runs inward**, because the extreme it enters at
is the one it has to stop behind, so §M28.2's ``[0.25, 0.5, 0.75, 1.0]`` placed it between a
quarter of the range width outside and a full width outside and never anywhere tight. This
extends the same axis downward and keeps ``0.25`` as its endpoint, so the new rows and the
parked ones share a cell exactly -- ``docs/roadmap.md`` §M28.5.
"""

ORB_FADE_LADDERS: dict[str, tuple[float, ...]] = {
    "target=width": (1.0, NAN),
    "target=width+mid": (0.5, 1.0, NAN),
}
"""Per-leg targets as multiples of the range width, past the trigger.

``target=width`` is §M28.2's ladder, kept so the two runs share it. ``target=width+mid`` adds
the **midpoint** — which is what a rejection trade is aiming at and the first target in the
band-reversion convention §M26 records — and which the swept space has never carried.
"""


def openingrange_fade_variants(root: str) -> list[Variant]:
    """§M28.5's re-run: the fade alone, with the bracket §M28.2 parked it for.

    The entry axes are held at exactly what §M28.2 swept, so the only thing that moved is the
    bracket — which is what § "Parked is not abandoned" asks a re-run to be able to say.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "max_entries_per_session": [1, 0],
        "entry_offset_ticks": [1, 4],
        "break_confirm_ticks": [0, 8],
        "stop_range_fraction": [*ORB_TIGHT_FRACTIONS],
        "stop_offset_ticks": [2, 8],
    }

    return [
        Variant(
            name=f"{range_name} entry=fade {target_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=ORB_ENTRY_FADE,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=target_mode,
                    target_width_multiples=ladder,
                ),
                root,
            ),
            axes={**shared, **target_axes},
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in ORB_RANGES.items()
        for target_name, target_mode, ladder, target_axes in _orb_fade_targets()
    ]


def _orb_fade_targets() -> list[OrbTarget]:
    """The three target schemes §M28.5 crosses: the R ladder and two width ladders.

    A ladder is a tuple, so it is a variant rather than an axis -- see :class:`Variant`. The
    width multiples ride along under :data:`ORB_TARGET_R` too, where nothing reads them.
    """
    default: tuple[float, ...] = ORB_FADE_LADDERS["target=width"]

    return [
        ("target=R", ORB_TARGET_R, default, {"tp_multiplier": [1.0, 2.0]}),
        *((name, ORB_TARGET_WIDTH, ladder, {}) for name, ladder in ORB_FADE_LADDERS.items()),
    ]


ORB_REJECTION_OFFSETS = [0, 1, 4, 8]
"""How far inside the extreme the rejection's limit rests, in ticks -- §M28.7's entry axis.

`0` is the one value that is not the setup: a limit resting on the extreme itself needs price
to trade **through** it under `IsFillLimitOnTouch = false`, which is the break the mode exists
to do without. From one tick in, the fill measures "came this close and turned" and nothing
has to break -- ``docs/roadmap.md`` §M28.7.
"""


def openingrange_rejection_variants(root: str) -> list[Variant]:
    """§M28.7's run: the rejection alone, over the bracket §M28.5 measured the fade on.

    The bracket axes are held at exactly what §M28.5 swept, so the entry is the only thing that
    moved -- which is the comparison § "Parked is not abandoned" asks a re-run to be able to
    make, read here between two entries rather than between two brackets.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "max_entries_per_session": [1, 0],
        "entry_offset_ticks": [*ORB_REJECTION_OFFSETS],
        "stop_range_fraction": [*ORB_TIGHT_FRACTIONS],
        "stop_offset_ticks": [2, 8],
    }

    return [
        Variant(
            name=f"{range_name} entry=rejection {target_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=ORB_ENTRY_REJECTION,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=target_mode,
                    target_width_multiples=ladder,
                ),
                root,
            ),
            axes={**shared, **target_axes},
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in ORB_RANGES.items()
        for target_name, target_mode, ladder, target_axes in _orb_fade_targets()
    ]


ORB_WIDE_BRACKET: dict[str, list[AxisValue]] = {"stop_range_fraction": [*ORB_FRACTIONS]}
"""The bracket §M28.2 swept the breakout and the retest on: the stop a fraction of the range
width back from the extreme that was broken, and the offset left at its default."""

ORB_TIGHT_BRACKET: dict[str, list[AxisValue]] = {
    "stop_range_fraction": [*ORB_TIGHT_FRACTIONS],
    "stop_offset_ticks": [2, 8],
}
"""The bracket §M28.5 and §M28.7 swept the fade and the rejection on: the stop just outside the
extreme entered at, with the absolute floor separated from the proportional part."""


ORB_REJECTION_ENTRY: dict[str, list[AxisValue]] = {"entry_offset_ticks": [*ORB_REJECTION_OFFSETS]}
"""The rejection's own entry axis, which is the whole of what it reads at the level."""


class OrbEntry(NamedTuple):
    """One entry mechanism at the axes and the bracket its own campaign swept it over."""

    mode: int
    axes: dict[str, list[AxisValue]]
    targets: list[OrbTarget]


ORB_GEOMETRY_ENTRIES: dict[str, OrbEntry] = {
    "entry=breakout": OrbEntry(
        ORB_ENTRY_BREAKOUT,
        ORB_ENTRIES["entry=breakout"][1] | ORB_WIDE_BRACKET,
        _orb_further_targets(),
    ),
    "entry=fade": OrbEntry(
        ORB_ENTRY_FADE,
        ORB_ENTRIES["entry=fade"][1] | ORB_TIGHT_BRACKET,
        _orb_fade_targets(),
    ),
    "entry=retest": OrbEntry(
        ORB_ENTRY_RETEST,
        ORB_ENTRIES["entry=retest"][1] | ORB_WIDE_BRACKET,
        _orb_further_targets(),
    ),
    "entry=rejection": OrbEntry(
        ORB_ENTRY_REJECTION,
        ORB_REJECTION_ENTRY | ORB_TIGHT_BRACKET,
        _orb_fade_targets(),
    ),
}
"""All four entries, each carrying what its own campaign gave it rather than one shared grid.

**That is what makes the range the only thing that moves.** §M28.2 measured the breakout and the
retest on a stop inside the range; §M28.5 and §M28.7 measured the fade and the rejection on one
just outside the extreme they enter at, which is the other side of the same formula. A single
bracket across all four would move two things at once on two of them -- ``docs/roadmap.md``
§M28.8.
"""

ORB_GEOMETRY_WINDOWS = (5, 15, 30, 45, 60, 90, 120, sessionrange.CASH_OPEN_MINUTES)
"""Range lengths in minutes: §M28's three, the hour most sources mean by "the ORB", and the
lengths that bracket it.

The last is the overnight span rather than a length anyone would name. It is in the axis
because it is the one window that reproduces §M28.2's ``overnight`` range, which anchors the
gradient to a stored measurement instead of running beside it -- ``docs/roadmap.md`` §M28.8.
"""


def orb_geometry_ranges() -> dict[str, sessionrange.RangeKey]:
    """Every (anchor, window) the session leaves room to trade, one entry per cell of the cross.

    The anchors are the session's own phase starts, and a range must complete before the phase
    the forced flat falls in -- so which cells exist is derived from the session template
    rather than chosen.
    """
    latest: int = sessionrange.anchor_for(timeofday.FORCED_EXIT_PHASE)
    anchors: dict[str, int] = {
        phase.name.lower().replace("_", "-"): sessionrange.anchor_for(phase)
        for phase in timeofday.SessionPhase
    }

    return {
        f"{name}+{window}m": (anchor, window)
        for name, anchor in anchors.items()
        for window in ORB_GEOMETRY_WINDOWS
        if anchor + window <= latest
    }


def openingrange_geometry_variants(root: str) -> list[Variant]:
    """§M28.8's run: the range's anchor crossed with its length, on all four entries.

    One variant per (range, entry, target), because the range decides which resolutions exist
    at all and each entry reads axes the others do not -- ``Variant.resolutions``.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "max_entries_per_session": [1, 0],
    }

    return [
        Variant(
            name=f"{range_name} {entry_name} {target_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=entry.mode,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=target_mode,
                    target_width_multiples=ladder,
                ),
                root,
            ),
            axes={**shared, **entry.axes, **target_axes},
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in orb_geometry_ranges().items()
        for entry_name, entry in ORB_GEOMETRY_ENTRIES.items()
        for target_name, target_mode, ladder, target_axes in entry.targets
    ]


ORB_FOLLOW_THROUGH_RANGES: dict[str, sessionrange.RangeKey] = {
    "cash-ft+15m": (sessionrange.CASH_OPEN_MINUTES, 15),
    "cash-ft+30m": (sessionrange.CASH_OPEN_MINUTES, 30),
}
"""The two ranges whose breakout separates from a permuted range, and no others.

§M28.8's gate 3 puts the excess at 15 and 30 minutes from the cash open and finds none at 45
or 60, so this run asks its question where there is an edge to lose rather than across a
plateau. The names carry ``cash-ft+`` where §M28.8 wrote ``cash-open+``, because the variant
name is the only thing separating two runs in one database.
"""

ORB_FOLLOW_THROUGH_LOOKBACKS = (20, 60, 250)
"""How many prior sessions the trailing median is taken over: a month, a quarter, a year.

Three rather than one because the lookback is what decides whether the scale tracks the regime
or averages over it, and a single unexamined window would be reporting its own choice.
"""

ORB_FOLLOW_THROUGH_MODES: dict[str, int] = {
    "scale=target": ORB_SCALE_TARGET,
    "scale=stop": ORB_SCALE_STOP,
    "scale=both": ORB_SCALE_BOTH,
}
"""Which halves of the bracket the trailing follow-through is applied to.

Separable on purpose: [#261] names both halves as denominated in the quantity that moved, and
one arm each is what says whether either is the one that matters.
"""


def openingrange_follow_through_variants(root: str) -> list[Variant]:
    """§M28.10's run: the bracket denominated in trailing reach, against an unscaled control.

    **A variant dimension rather than an axis**, for :data:`SPEC_TRAILS`' reason:
    ``follow_through_sessions`` is inert at :data:`ORB_SCALE_NONE`, so crossing the two as axes
    would run the control once per lookback and nothing would say so. The control is in the
    same pass on the same bars, which is what makes it a comparison rather than two runs.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "entry_offset_ticks": [1, 4],
        "max_entries_per_session": [1, 0],
        "stop_range_fraction": [*ORB_FRACTIONS],
    }
    scalings: list[tuple[str, int, int]] = [
        (f"{name}@{sessions}", mode, sessions)
        for name, mode in ORB_FOLLOW_THROUGH_MODES.items()
        for sessions in ORB_FOLLOW_THROUGH_LOOKBACKS
    ]

    return [
        Variant(
            name=f"{range_name} {scale_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=ORB_ENTRY_BREAKOUT,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=ORB_TARGET_WIDTH,
                    follow_through_scaling=mode,
                    follow_through_sessions=sessions,
                ),
                root,
            ),
            axes=dict(shared),
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in ORB_FOLLOW_THROUGH_RANGES.items()
        for scale_name, mode, sessions in [("scale=off", ORB_SCALE_NONE, 60), *scalings]
    ]


ORB_BRACKET_RANGES: dict[str, sessionrange.RangeKey] = {
    "cash-br+15m": (sessionrange.CASH_OPEN_MINUTES, 15),
    "cash-br+30m": (sessionrange.CASH_OPEN_MINUTES, 30),
}
"""The two ranges §M28.8's gate 3 separated from a permuted range, and no others.

Same cut as :data:`ORB_FOLLOW_THROUGH_RANGES` and for its reason: a bracket axis is worth
extending where there is an edge to lose rather than across the plateau above 30 minutes. The
names carry ``cash-br+`` because the variant name is the only thing separating two runs in one
database -- ``docs/roadmap.md`` §M28.11.
"""

ORB_LADDER_FRACTIONS = [*ORB_FRACTIONS, 1.5, 2.0, 3.0, 5.0]
"""§M28.2's stop axis carried past the boundary its best value sat on.

``1.0`` was the winner on both roots and both windows, so the axis was truncated rather than
swept -- [#262]. Built from :data:`ORB_FRACTIONS` rather than rewritten, so every stored cell
is re-run at exactly the fraction that produced it and the new rows extend the old ones instead
of running beside them. Past ``1.0`` the stop sits outside the range, which the params class
already allows -- ``docs/roadmap.md`` §M28.11.
"""

ORB_WIDTH_LADDERS: dict[str, tuple[float, ...]] = {
    "target=w0.5": (0.5, NAN),
    "target=w1.0": OpeningRangeParams().target_width_multiples,
    "target=w2.0": (2.0, NAN),
    "target=w3.0": (3.0, NAN),
    "target=w1.0+2.0": (1.0, 2.0, NAN),
    "target=runner": (NAN, NAN),
}
"""Per-leg targets as multiples of the range width past the trigger, one variant each.

``target=w1.0`` is the parameter default rather than a copy of it, for
:func:`_orb_further_targets`' reason: it is the ladder every ORB campaign to date ran under
:data:`ORB_TARGET_WIDTH` without varying it, so a cell here and a stored one carry the same
tuple. ``target=runner`` takes the target off entirely and leaves both legs to the forced flat,
and ``target=w1.0+2.0`` is the only cell that scales out at two distances -- ``docs/roadmap.md``
§M28.11.
"""


def openingrange_bracket_variants(root: str) -> list[Variant]:
    """§M28.11's run: the stop ladder past its boundary, crossed with the width ladder.

    One variant per (range, ladder), because a ladder is a tuple and tuples are not sweepable --
    see :class:`Variant`. The entry is the breakout alone, held at exactly the axes §M28.2 and
    §M28.10 swept it on, so the bracket is the only thing that moved.
    """
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "entry_offset_ticks": [1, 4],
        "max_entries_per_session": [1, 0],
        "stop_range_fraction": [*ORB_LADDER_FRACTIONS],
    }

    return [
        Variant(
            name=f"{range_name} {ladder_name}",
            archetype=archetypes.OPENINGRANGE,
            base=_costed(
                OpeningRangeParams(
                    anchor_minutes=anchor,
                    window_minutes=window,
                    entry_mode=ORB_ENTRY_BREAKOUT,
                    stop_mode=ORB_STOP_FRACTION,
                    target_mode=ORB_TARGET_WIDTH,
                    target_width_multiples=ladder,
                ),
                root,
            ),
            axes=dict(shared),
            resolutions=orb_resolutions(anchor, window),
        )
        for range_name, (anchor, window) in ORB_BRACKET_RANGES.items()
        for ladder_name, ladder in ORB_WIDTH_LADDERS.items()
    ]


SPEC_SHARED: dict[str, list[AxisValue]] = {
    "fast_period": [9, 20],
    "slow_period": [50, 200],
    "tp_multiplier": [1.0, 2.0],
    "exit_on_opposite_cross": [True, False],
}
"""What every spec variant holds in common: a coarse cut of the axes §M27 already measured.

Deliberately smaller than :func:`crossover_variants`' grid, and with the moving-average kind
dropped entirely. §M27's gate 1 puts every kind axis below 0.04 eta-squared, so crossing them
here would multiply the run without separating anything -- and the question this set exists to
ask is about the three new axes, which a large shared grid would bury.
"""

SPEC_STOPS: dict[str, tuple[bool, dict[str, list[AxisValue]]]] = {
    "stop=atr": (True, {"atr_stop_multiple": [1.5, 3.0]}),
    "stop=swing": (False, {"swing_lookback": [1, 3]}),
}
"""The two initial stops, carried through every spec variant.

A variant dimension for :func:`crossover_variants`' reason: ``atr_stop_multiple`` is inert
under the swing stop and ``swing_lookback`` under the ATR one, and a grid crosses its axes
uniformly.
"""

SPEC_TRAILS: dict[str, tuple[bool, dict[str, list[AxisValue]]]] = {
    "trail=off": (False, {}),
    "trail=on": (
        True,
        {
            "trail_ma_kind": ["ema", "sma"],
            "trail_ma_period": [20, 50, 100],
            "trail_offset_ticks": [2, 8],
        },
    ),
}
"""Whether the stop trails a moving average, and the three axes only the trailing half reads.

**A variant rather than an axis**: with the toggle off, its three axes are inert and every
combination along them is identical -- the silent duplicate ``dead_axes`` cannot see. The
``trail=off`` half is the control, run in the same pass on the same bars so the comparison is
inside one measurement rather than across two.
"""

SPEC_ROUNDS: dict[str, dict[str, list[AxisValue]]] = {
    "round=off": {},
    "round=on": {"round_number_points": [5.0, 25.0], "round_number_offset_ticks": [2, 8]},
}
"""The round-number spacings tried, against a control that avoids nothing.

5 and 25 points rather than a wider ladder: on NQ they are the two spacings a discretionary
trader would name, and the rule can only ever move a stop that lands exactly on one, so a
denser ladder buys resolution the rule does not have. **Every one of these cells needs raw
prices** -- see :func:`run_point`, which is where the campaign says so.
"""

SPEC_CONFLUENCE_FILTERS: dict[str, int] = {
    "regime_filter": regime.Regime.DIRECTIONAL.bit,
    "volume_filter": volume.VolumeState.HEAVY.bit,
    "compression_filter": compression.Compression.EXPANDED.bit,
}
"""The three filters a confluence count is measured over, all of them side-neutral.

Trend and higher-timeframe are left out on purpose: both name a *direction*, and EmaCrossover
takes each side on its own signal, so switching one on measures the long half rather than the
count. **Three is also the smallest number that makes the axis interesting** -- at two, the
only legal count is 1, which is the union.
"""


def spec_variants(root: str) -> list[Variant]:
    """The [#74] axes, each against a control run on the same bars in the same pass.

    Its own set rather than an edit to :data:`VARIANTS`, which is what §M27 measured --
    ``docs/roadmap.md`` § "The build spec's three loose ends, measured".
    """
    stopped: list[tuple[str, bool, dict[str, list[AxisValue]]]] = [
        (name, use_atr, axes) for name, (use_atr, axes) in SPEC_STOPS.items()
    ]

    return [
        *[
            Variant(
                name=f"{stop_name} {trail_name}",
                archetype=archetypes.EMACROSSOVER,
                base=_costed(
                    EmaCrossoverParams(use_atr_stop=use_atr, trail_ma_stop=trailing),
                    root,
                ),
                axes={**SPEC_SHARED, **stop_axes, **trail_axes},
            )
            for stop_name, use_atr, stop_axes in stopped
            for trail_name, (trailing, trail_axes) in SPEC_TRAILS.items()
        ],
        *[
            Variant(
                name=f"{stop_name} {round_name}",
                archetype=archetypes.EMACROSSOVER,
                base=_costed(EmaCrossoverParams(use_atr_stop=use_atr), root),
                axes={**SPEC_SHARED, **stop_axes, **round_axes},
            )
            for stop_name, use_atr, stop_axes in stopped
            for round_name, round_axes in SPEC_ROUNDS.items()
        ],
        *[
            Variant(
                name=f"{stop_name} confluence",
                archetype=archetypes.EMACROSSOVER,
                base=_costed(
                    EmaCrossoverParams(use_atr_stop=use_atr, **SPEC_CONFLUENCE_FILTERS),
                    root,
                ),
                axes={**SPEC_SHARED, **stop_axes, "confluence_required": [REQUIRE_ALL, 1, 2]},
            )
            for stop_name, use_atr, stop_axes in stopped
        ],
    ]


VARIANTS = {
    "DeadCatBounce": deadcat_variants,
    "PullBackAndGo": pullback_variants,
    "EmaCrossover": crossover_variants,
    "InsideBar": insidebar_variants,
    "InsideBarTrailing": insidebartrailing_variants,
    "ElasticBand": elasticband_variants,
    "OpeningRange": openingrange_variants,
}
"""Archetype name -> the variants swept for it, built per root so costs are the root's.

**This is what §M27 measured**, so a re-sweep that changes an axis belongs in its own entry of
:data:`VARIANT_SETS` rather than in here, where it would leave the stored rows and the code
that produced them disagreeing."""

NARROW_VARIANTS = {"InsideBar": insidebar_narrow_variants}
"""The §M27.3 re-sweep: one archetype, the bracket pair §M27 could not cross."""

ORB_VARIANTS = {"OpeningRange": openingrange_further_variants}
"""The §M28.2 re-sweep: §M28's deferred anchors, entries and stop levels, over §M28.1's
archetype. Its own set rather than an edit to :data:`VARIANTS`, which is what §M28.1 measured
and what the stored rows were produced by."""

ORB_FADE_VARIANTS = {"OpeningRange": openingrange_fade_variants}
"""The §M28.5 re-run: the fade alone, with a stop tighter than §M28.2's axis reached and a
target that stops at the middle of the range -- ``docs/roadmap.md`` §M28.5."""

ORB_BRACKET_VARIANTS = {"OpeningRange": openingrange_bracket_variants}
"""The §M28.11 run: the stop ladder carried past the value it stopped on, crossed with the
width ladder no ORB campaign has ever varied -- [#262]."""

ORB_FOLLOW_THROUGH_VARIANTS = {"OpeningRange": openingrange_follow_through_variants}
"""The §M28.10 run: the bracket denominated in trailing follow-through rather than in the
session's own range width, over the two ranges §M28.8's null separated -- [#261]."""

ORB_GEOMETRY_VARIANTS = {"OpeningRange": openingrange_geometry_variants}
"""The §M28.8 run: the anchor axis §M28.2 opened, crossed with the length axis nothing has swept.

Its own set rather than an edit to :data:`ORB_VARIANTS` for that dict's own reason, and the
range names carry a ``+`` where the stored ones carry a ``=`` so the two cannot collide in one
database -- ``docs/roadmap.md`` §M28.8."""

ORB_REJECTION_VARIANTS = {"OpeningRange": openingrange_rejection_variants}
"""The §M28.7 run: the rejection alone, over §M28.5's bracket, so that the two reversion
entries differ by their entry rule and nothing else -- ``docs/roadmap.md`` §M28.7."""

ELASTIC_SHAPE_VARIANTS = {"ElasticBand": elasticband_shape_variants}
"""The §M26.5 run: the two signal-bar requirements [#221] asked for, each against the
``shape=any`` control in the same pass. Its own set rather than an edit to :data:`VARIANTS`
for that dict's own reason -- ``docs/roadmap.md`` §M26.5."""

ELASTIC_VOLUME_VARIANTS = {"ElasticBand": elasticband_volume_variants}
"""The §M26.9 run: §M26.5's shape pair over a held bracket, so that the volume strata are
the only cells the pass adds. The names carry ``break-volume`` where the stored shape rows
carry none, so the two runs cannot collide in one database -- ``docs/roadmap.md`` §M26.9."""

ELASTIC_RECOVERY_VARIANTS = {"ElasticBand": elasticband_recovery_variants}
"""The §M26.6 run: the recovery trigger against the shapes it replaces, in one pass. The names
carry an ``entry=`` token where the stored shape rows carry none, so the two runs cannot collide
in one database -- ``docs/roadmap.md`` §M26.6."""

SPEC_VARIANTS = {"EmaCrossover": spec_variants}
"""The [#74] re-sweep: the moving-average trail, round-number avoidance and the confluence
count, each against a control in the same pass. One archetype, because that is where the three
axes exist -- ``docs/roadmap.md`` § "The build spec's three loose ends, measured"."""

CAMPAIGN = "campaign"

VARIANT_SETS = {
    CAMPAIGN,
    ELASTIC_RECOVERY,
    ELASTIC_SHAPE,
    ELASTIC_VOLUME,
    NARROW,
    ORB,
    ORB_BRACKET,
    ORB_FADE,
    ORB_FOLLOW_THROUGH,
    ORB_GEOMETRY,
    ORB_REJECTION,
    SPEC,
}
"""Which grid ``--variants`` selects. Rows carry the variant's own name, so a narrow re-sweep
lands in the same database as the campaign it follows and is still separable from it -- pass
``--variant narrow`` to the reading tools."""


def variants_for(which: str) -> dict[str, Callable[[str], list[Variant]]]:
    """The variant builders one ``--variants`` name selects."""
    sets: dict[str, dict[str, Callable[[str], list[Variant]]]] = {
        ELASTIC_RECOVERY: ELASTIC_RECOVERY_VARIANTS,
        ELASTIC_SHAPE: ELASTIC_SHAPE_VARIANTS,
        ELASTIC_VOLUME: ELASTIC_VOLUME_VARIANTS,
        NARROW: NARROW_VARIANTS,
        ORB: ORB_VARIANTS,
        ORB_BRACKET: ORB_BRACKET_VARIANTS,
        ORB_FADE: ORB_FADE_VARIANTS,
        ORB_FOLLOW_THROUGH: ORB_FOLLOW_THROUGH_VARIANTS,
        ORB_GEOMETRY: ORB_GEOMETRY_VARIANTS,
        ORB_REJECTION: ORB_REJECTION_VARIANTS,
        SPEC: SPEC_VARIANTS,
    }

    return sets.get(which, VARIANTS)


def grids_for(
    variant: Variant,
    which: str,
    cuts: Cuts = NO_CUTS,
) -> list[tuple[str, sweep.Grid]]:
    """One grid per stratum over ``variant``, named by the stratum."""
    return [
        (name, sweep.Grid(axes=variant.axes | extra, base=variant.base, archetype=variant.archetype))
        for name, extra in strata(which, cuts)
    ]


def windows(bars: pd.DataFrame, *, split: bool) -> list[tuple[str, pd.DataFrame]]:
    """The bar ranges to run: the whole series, or a selection window and a held-out one."""
    if not split:
        return [("full", bars)]

    cut: int = math.floor(len(bars) * SELECTION_SHARE)

    return [("selection", bars.iloc[:cut]), ("holdout", bars.iloc[cut:])]


def db_path(name: str) -> paths.Path:
    """Where one archetype's results live. Separate files, not separate tables -- see above."""
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

    return CAMPAIGN_DIR / f"{name}.duckdb"


def _merged_axes(grids: list[sweep.Grid]) -> dict[str, list[AxisValue]]:
    """Every value any grid tries for any axis, for the stored ``axes`` column."""
    merged: dict[str, list[AxisValue]] = {}
    for grid in grids:
        for axis, values in grid.axes.items():
            merged[axis] = sorted({*merged.get(axis, []), *values}, key=str)

    return merged


def run_point(
    frame: pd.DataFrame,
    variants: list[Variant],
    root: str,
    minutes: int,
    window: str,
    batch_id: int,
    which: str,
    cuts: Cuts,
    *,
    n_jobs: int,
) -> None:
    """Sweep every variant x stratum at one (root, archetype, resolution, window) point.

    The variants share one dataset built from the union of their specs, and their results are
    concatenated into a single ``sweeps`` row: a stratum is a parameter, not a dataset.
    """
    archetype: Archetype = variants[0].archetype
    named: list[tuple[str, str, sweep.Grid]] = [
        (variant.name, stratum, grid)
        for variant in variants
        for stratum, grid in grids_for(variant, which, cuts)
    ]

    spec: context.ContextSpec = context.ContextSpec()
    for _, _, grid in named:
        spec = spec | grid.required_context()
    started: float = time.perf_counter()
    # ``load_continuous`` is called without ``back_adjust``, so these are the prices that
    # traded and a rule reading an absolute level may run -- ``docs/roadmap.md`` § "The
    # build spec's three loose ends".
    data: context.Dataset = context.prepare(
        frame,
        spec,
        bar_minutes=minutes,
        price_basis=context.PriceBasis.RAW,
    )
    prepared: float = time.perf_counter() - started

    tables: list[pd.DataFrame] = []
    started = time.perf_counter()
    for variant_name, stratum, grid in named:
        table, _ = sweep.sweep(frame, grid, get_instrument(root), data=data, n_jobs=n_jobs)
        table.insert(0, "variant", variant_name)
        table.insert(1, "stratum", stratum)
        table.insert(2, "window", window)
        tables.append(table)
    elapsed: float = time.perf_counter() - started

    combined: pd.DataFrame = pd.concat(tables, ignore_index=True)
    combined["combo_id"] = range(len(combined))

    sweep_id: int = results.save_sweep(
        combined,
        root=root,
        instrument=root,
        bars=frame,
        axes=_merged_axes([grid for _, _, grid in named]),
        elapsed_s=elapsed,
        notes=(
            f"campaign; window={window}; strata={which}; variants={len(variants)}; "
            f"cells={len(named) // len(variants)}; "
            f"regime={'quantile-fitted' if cuts.regime else 'raw'}; "
            f"volume={'quantile-fitted' if cuts.volume else 'raw'}; "
            f"${COMMISSION[root]:.2f} RT + {SLIPPAGE_TICKS:g} tick"
        ),
        strategy=archetype.name,
        resolution=minutes,
        contract=None,
        tier2=str(archetype.tier2),
        batch_id=batch_id,
        db_path=db_path(archetype.name),
    )
    viable: pd.DataFrame = combined[combined["trades"] >= MIN_TRADES]
    logger.info(
        "  sweep %-4d %-4s %-9s %2dm  %6s combos  prep %5.1fs  sim %6.1fs  "
        "best PF %.3f  median PF %.3f  profitable %4.1f%%",
        sweep_id,
        root,
        window,
        minutes,
        f"{len(combined):,}",
        prepared,
        elapsed,
        viable["profit_factor"].max() if len(viable) else NAN,
        viable["profit_factor"].median() if len(viable) else NAN,
        100.0 * float((viable["profit_factor"] > 1.0).mean()) if len(viable) else NAN,
    )


def cell_shape(argv: argparse.Namespace) -> Cuts:
    """Cuts with the right cells and no thresholds in them, for counting cells only."""
    regime_cells: Calibration | None = (
        dict.fromkeys(argv.regime_lookbacks, (NAN, NAN)) if argv.regime_quantiles else None
    )
    volume_cells: VolumeCalibration = (
        tuple(
            VolumeCut(key, NAN, NAN, tails=pair) for key in volume_series() for pair in argv.volume_quantiles
        )
        if argv.volume_quantiles
        else ()
    )

    return Cuts(regime=regime_cells, volume=volume_cells)


def planned_combinations(argv: argparse.Namespace) -> int:
    """How many combinations the requested run will simulate, before it starts."""
    per_window: int = 0
    cells: int = len(list(strata(argv.strata, cell_shape(argv))))
    builders = variants_for(argv.variants)
    for name in argv.strategies:
        for root in argv.roots:
            for variant in builders[name](root):
                live: int = sum(1 for minutes in argv.resolutions if variant.runs_at(minutes))
                per_window += variant.sized() * cells * live

    return per_window * (2 if argv.split else 1)


def quantile_pair(given: list[float] | None) -> tuple[float, float] | None:
    """The pair to fit at: ``None`` for the raw thresholds, and bare for :data:`REGIME_QUANTILES`."""
    if given is None:
        return None

    if not given:
        return REGIME_QUANTILES

    if len(given) != len(REGIME_QUANTILES):
        msg: str = f"--regime-quantiles takes a consolidating and a directional quantile, got {len(given)}"
        raise SystemExit(msg)

    return given[0], given[1]


def tail_pairs(given: list[float] | None) -> tuple[tuple[float, float], ...]:
    """The tail sizes to fit: empty for the raw thresholds, and bare for :data:`VOLUME_TAILS`."""
    if given is None:
        return ()

    if not given:
        return VOLUME_TAILS

    if len(given) % 2:
        msg: str = f"--volume-quantiles takes a thin and a heavy quantile per cut, got {len(given)}"
        raise SystemExit(msg)

    return tuple((given[at], given[at + 1]) for at in range(0, len(given), 2))


def log_calibration(
    fitted: dict[int, Calibration],
    quantiles: tuple[float, float],
    selection_bars: int,
) -> None:
    """Report the cut every stratum below was defined by, beside the anchor it is read against."""
    logger.info("  regime thresholds fitted at q=%s on %s selection bars", quantiles, f"{selection_bars:,}")
    for minutes, calibration in fitted.items():
        for lookback, (consolidating, directional) in calibration.items():
            anchor: float = regime.random_walk_ratio(lookback)
            logger.info(
                "    %2dm n=%-3d consolidating %.4f (%.2fx)  directional %.4f (%.2fx)",
                minutes,
                lookback,
                consolidating,
                consolidating / anchor,
                directional,
                directional / anchor,
            )


def log_volume_calibration(fitted: dict[int, VolumeCalibration], selection_bars: int) -> None:
    """Report the cut each volume-form stratum below was defined by, and what share it admits."""
    logger.info("  volume thresholds fitted on %s selection bars", f"{selection_bars:,}")
    for minutes, calibration in fitted.items():
        for cut in calibration:
            logger.info(
                "    %2dm %-32s thin < %.4f  heavy > %.4f",
                minutes,
                cut.name,
                cut.thin_below,
                cut.heavy_above,
            )


def fit_volume(bars: pd.DataFrame, argv: argparse.Namespace) -> dict[int, VolumeCalibration]:
    """One calibration per resolution, fitted on the selection window whether or not it is split.

    The held-out window reads the selection window's cut, exactly as :func:`fit_regime`'s does.
    """
    if not argv.volume_quantiles:
        return {}

    selection: pd.DataFrame = bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]
    fitted: dict[int, VolumeCalibration] = {
        minutes: calibrate_volume(resample.resample(selection, minutes), minutes, argv.volume_quantiles)
        for minutes in argv.resolutions
    }
    log_volume_calibration(fitted, len(selection))

    return fitted


def fit_regime(bars: pd.DataFrame, argv: argparse.Namespace) -> dict[int, Calibration]:
    """One calibration per resolution, fitted on the selection window whether or not it is split.

    The held-out window reads the selection window's cut, so nothing about the holdout reaches
    the definition of the stratum -- ``docs/roadmap.md`` §M27.5.
    """
    if not argv.regime_quantiles:
        return {}

    selection: pd.DataFrame = bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]
    fitted: dict[int, Calibration] = {
        minutes: calibrate(
            resample.resample(selection, minutes), argv.regime_lookbacks, argv.regime_quantiles
        )
        for minutes in argv.resolutions
    }
    log_calibration(fitted, argv.regime_quantiles, len(selection))

    return fitted


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Sweep every archetype across resolution and context.")
    parser.add_argument("--n-jobs", type=int, default=8, help="joblib workers; 1 stays in-process")
    parser.add_argument("--split", action="store_true", help="selection and held-out windows")
    parser.add_argument("--roots", nargs="+", default=list(ROOTS))
    parser.add_argument("--strategies", nargs="+", default=None)
    parser.add_argument(
        "--variants",
        choices=sorted(VARIANT_SETS),
        default=CAMPAIGN,
        help="which grid to sweep; narrow is the §M27.3 re-sweep",
    )
    parser.add_argument("--resolutions", nargs="+", type=int, default=list(RESOLUTIONS))
    parser.add_argument("--strata", choices=sorted(STRATUM_SETS), default=None, help="stratifications")
    parser.add_argument(
        "--regime-quantiles",
        nargs="*",
        type=float,
        default=None,
        help="fit the regime thresholds on the selection window; bare takes the stated pair",
    )
    parser.add_argument("--regime-lookbacks", nargs="+", type=int, default=list(REGIME_LOOKBACKS))
    parser.add_argument(
        "--volume-quantiles",
        nargs="*",
        type=float,
        default=None,
        help="fit the volume-form thresholds on the selection window; bare takes the stated tails",
    )
    args = parser.parse_args(argv[1:])
    args.strategies = args.strategies or list(variants_for(args.variants))
    args.regime_quantiles = quantile_pair(args.regime_quantiles)
    args.volume_quantiles = tail_pairs(args.volume_quantiles)
    # A held-out test of a stratified shortlist is a smaller sample twice over, so --split
    # defaults to the unfiltered stratum alone unless one is named.
    args.strata = args.strata or (UNFILTERED if args.split else CORE)

    logger.info("planned combinations: %s", f"{planned_combinations(args):,}")
    started: float = time.perf_counter()
    for name in args.strategies:
        batch_id: int = results.next_batch_id(db_path(name))
        logger.info("")
        logger.info("=== %s (batch %d) ===", name, batch_id)
        for root in args.roots:
            variants: list[Variant] = variants_for(args.variants)[name](root)
            bars: pd.DataFrame = splice.load_continuous(root)
            fitted: dict[int, Calibration] = fit_regime(bars, args)
            volumes: dict[int, VolumeCalibration] = fit_volume(bars, args)
            for window, source in windows(bars, split=args.split):
                for minutes in args.resolutions:
                    # A variant the resolution cannot express is skipped rather than raising:
                    # the opening range is the only one this can drop -- see Variant.resolutions.
                    at_resolution: list[Variant] = [v for v in variants if v.runs_at(minutes)]
                    if not at_resolution:
                        continue

                    frame: pd.DataFrame = resample.resample(source, minutes)
                    run_point(
                        frame,
                        at_resolution,
                        root,
                        minutes,
                        window,
                        batch_id,
                        args.strata,
                        Cuts(regime=fitted.get(minutes), volume=volumes.get(minutes, ())),
                        n_jobs=args.n_jobs,
                    )
    logger.info("")
    logger.info("done in %.1f min", (time.perf_counter() - started) / 60.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
