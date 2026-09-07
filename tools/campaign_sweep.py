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
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_RETEST,
    ORB_STOP_ATR,
    ORB_STOP_FRACTION,
    ORB_STOP_OPPOSITE,
    ORB_TARGET_R,
    ORB_TARGET_WIDTH,
    STOP_ATR,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_STRETCH,
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
VOLUME_FORMS = "volume-forms"
COMPRESSION_FORMS = "compression-forms"
CORE = "core"
CONTEXT = "context"
NARROW = "narrow"
TREND_UP = "trend-up"
ORB = "orb"
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

REGIME_GROUPS = frozenset({REGIME, DIRECTIONAL})
"""Groups whose cells ``--regime-quantiles`` splits per lookback. Membership rather than one
name, so that a group yielding a single regime cell is calibrated like the full one."""

RECUTS = frozenset({DIRECTIONAL, TREND_UP, VOLUME_FORMS, COMPRESSION_FORMS})
"""Groups that re-cut a dimension another group already owns, so ``all`` leaves them out.

``directional`` is one regime cell without its four siblings and ``trend-up`` one trend cell
without its two; ``volume-forms`` is the volume
dimension under all three forms and a fitted cut; ``compression-forms`` is the compression
dimension under both of its forms. Any of them inside ``all`` would run its dimension twice
under two sets of names."""

STRATUM_SETS: dict[str, tuple[str, ...]] = {
    **{group: (group,) for group in STRATUM_GROUPS},
    CORE: (UNFILTERED, "regime", "phase"),
    CONTEXT: ("volume", "compression", "trend", "htf"),
    NARROW: (UNFILTERED, DIRECTIONAL),
    ORB: (UNFILTERED, DIRECTIONAL, TREND_UP),
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
    targets: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
        "target=R": (ORB_TARGET_R, {"tp_multiplier": [1.0, 2.0]}),
        "target=width": (ORB_TARGET_WIDTH, {}),
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
        for target_name, (target_mode, target_axes) in targets.items()
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

CAMPAIGN = "campaign"

VARIANT_SETS = {CAMPAIGN, NARROW, ORB}
"""Which grid ``--variants`` selects. Rows carry the variant's own name, so a narrow re-sweep
lands in the same database as the campaign it follows and is still separable from it -- pass
``--variant narrow`` to the reading tools."""


def variants_for(which: str) -> dict[str, Callable[[str], list[Variant]]]:
    """The variant builders one ``--variants`` name selects."""
    return {NARROW: NARROW_VARIANTS, ORB: ORB_VARIANTS}.get(which, VARIANTS)


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
    data: context.Dataset = context.prepare(frame, spec, bar_minutes=minutes)
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
