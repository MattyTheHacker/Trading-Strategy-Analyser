"""Sweep every registered archetype across resolution, market regime and session phase.

    uv run tools/campaign_sweep.py --n-jobs 8
    uv run tools/campaign_sweep.py --split --strata context --n-jobs 8
    uv run tools/campaign_sweep.py --variants orb-fade --strata orb-fade --split

``--variants`` picks the grid and ``--strata`` the cells, and a cell already stored is skipped.
Every option and variant set, and why each grid looks the way it does:
``tools/README.md`` § "campaign_sweep.py".
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, NamedTuple, Protocol, TypedDict

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
from nqbt.costs import ParamsT, TradingCosts
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import (
    AGE_STOP_LINE,
    LATE_STOP_LEVELS,
    MEASURE_EXCURSION,
    TREND_EXIT_FORMS,
    TREND_EXIT_OFF,
)
from nqbt.sim.types import (
    BAND_BOLLINGER,
    BAND_VWAP,
    EARLINESS_FIRST_BREAKOUT,
    EARLINESS_SMA_EXTENSION,
    EARLINESS_TREND_AGE,
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
    STOP_BAND,
    STOP_CATASTROPHE,
    STOP_SWING,
    TARGET_STRETCH,
    TOUCH_ANY,
    TOUCH_CLOSE,
    TOUCH_WICK,
    TRIGGER_EXTENDED,
    TRIGGER_RECOVERY,
    ConfluenceSized,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from nqbt.archetypes import Archetype, ArchetypeParams, AxisValue, Params

logger = logging.getLogger(__name__)

ROOTS = ("MNQ", "NQ")

COMMISSION: dict[str, float] = {
    "MNQ": 1.50,
    "NQ": 4.50,
    "MES": 1.50,
    "ES": 4.50,
    "MGC": 1.50,
    "GC": 4.50,
    "SI": 4.50,
}
"""Round-turn dollars per contract, per root; never one figure for both sizes.

``docs/roadmap.md`` § "Commission on the roots beyond NQ".
"""

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
"""The window and baseline §M27 ran at, and the rung each ladder defaults to. Both are
``sim/types.py`` defaults, which is what makes the ``PER_BAR`` cells here the campaign's own."""

VOLUME_TAILS = ((0.10, 0.90), (0.20, 0.80), (0.33, 0.67))
"""Tail sizes ``--volume-quantiles`` fits, each stated as a share of the measured bars."""

COMPRESSION_PERIOD = 20
COMPRESSION_BASELINE_BARS = 250
"""The width window and the trailing window every compression cell runs at, held so that the
form is what moves. Both are ``sim/types.py`` defaults -- ``docs/roadmap.md`` §M19.1."""

MIN_TRADES = 30
"""The floor ``sweep.rank`` applies, repeated here for the per-sweep progress line."""

SERIAL_BELOW_COMBINATION_BARS = 8_000_000
"""Combinations x bars below which a sweep call stays in-process whatever ``--n-jobs`` asks for."""

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
ELASTIC_CHANNEL = "elastic-channel"
ELASTIC_RECOVERY = "elastic-recovery"
ELASTIC_BAND_STOP = "elastic-band-stop"
EMAPULLBACK_TRAIL = "emapullback-trail"
EMAPULLBACK_CONFIRM = "emapullback-confirm"
IBT_SIZING = "ibt-sizing"
IBT_STRUCTURE = "ibt-structure"
IBT_STRUCTURE_ENDS = "ibt-structure-ends"
IBT_SIZING_HIGH = "ibt-sizing-high"
CONFLUENCE_SIZING = "confluence-sizing"
MIDDAY = "midday"
HOLD = "hold"
EARLY_EXIT = "early-exit"
EARLY_EXIT_2 = "early-exit-2"
SPEC = "spec"
ALL_STRATA = "all"


class RegimeCut(NamedTuple):
    """One lookback, the threshold pair fitted at it, and the cell size that pair came from."""

    lookback: int
    consolidating_below: float
    directional_above: float
    quantiles: tuple[float, float]

    @property
    def name(self) -> str:
        """What a stratum cut this way is called, which is what separates it in the table."""
        return f"n={self.lookback} q={self.quantiles[0]:.2f}/{self.quantiles[1]:.2f}"


Calibration = tuple[RegimeCut, ...]
"""Every lookback a regime stratification runs, each carrying its own fitted cut."""


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

    regime: Calibration = ()
    volume: VolumeCalibration = ()


NO_CUTS = Cuts()
"""What an uncalibrated run passes: the stratum names the stored databases already carry."""


def _unfiltered() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the stratum with no context filter at all: the baseline every other stratum is read against."""
    yield UNFILTERED, {}


def _regime() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per efficiency-ratio regime."""
    for state in regime.Regime:
        yield f"regime={state.name}", {"regime_filter": [state.bit]}


def _directional() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the one regime cell a narrow re-sweep runs inside, without its four siblings.

    Its own group rather than ``--strata regime`` because four cells nobody is asking about are
    four more comparisons -- ``docs/roadmap.md`` §M27.3.
    """
    yield f"regime={regime.Regime.DIRECTIONAL.name}", {"regime_filter": [regime.Regime.DIRECTIONAL.bit]}


def _consolidating() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the regime cell a fade's own thesis names, without its four siblings.

    :func:`_directional` is the breakout's thesis, and running a fade inside it would be
    stating the wrong hypothesis in advance -- ``docs/roadmap.md`` §M28.5.
    """
    yield f"regime={regime.Regime.CONSOLIDATING.name}", {"regime_filter": [regime.Regime.CONSOLIDATING.bit]}


def _trend_up() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the one trend cell §M28.1's gate 3 passed in on both roots, without its siblings.

    Its own group so the re-sweep names its strata before it runs -- ``docs/roadmap.md`` §M28.2.
    """
    yield f"trend={trend.Trend.UP.name}", {"trend_filter": [trend.Trend.UP.bit]}


def _phase() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per session phase."""
    for phase in timeofday.SessionPhase:
        yield f"phase={phase.name}", {"phase_filter": [phase.bit]}


def _midday() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the one phase InsideBarTrailing's live candidate trades in, without its six siblings.

    Named before the sizing run, as :func:`_trend_up` was for the opening range --
    ``docs/findings/m43-midday-candidates-ranked.md``.
    """
    phase: timeofday.SessionPhase = timeofday.SessionPhase.MIDDAY
    yield f"phase={phase.name}", {"phase_filter": [phase.bit]}


def _volume() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per relative-volume state, at the one form and the one cut §M27 ran."""
    for state in volume.VolumeState:
        yield f"volume={state.name}", {"volume_filter": [state.bit]}


def volume_series(
    forms: Sequence[volume.VolumeForm] = tuple(volume.VolumeForm),
    rolling_bars: Sequence[int] = (VOLUME_ROLLING_BARS,),
    baseline_sessions: Sequence[int] = (VOLUME_BASELINE_SESSIONS,),
) -> tuple[volume.VolumeKey, ...]:
    """Return one relative-volume series per (form, rolling window, baseline), deduplicated.

    Built through :func:`nqbt.volume.key`, and deduplicated after its drop of the rolling window
    -- ``docs/findings/m32-volume-windows.md``.
    """
    return tuple(
        dict.fromkeys(
            volume.key(form, rolling, baseline)
            for form in forms
            for rolling in rolling_bars
            for baseline in baseline_sessions
        )
    )


def raw_volume_cuts() -> VolumeCalibration:
    """Return the three forms at the campaign's own thresholds, which is what an unfitted run compares."""
    defaults: DeadCatParams = DeadCatParams()

    return tuple(
        VolumeCut(series, defaults.volume_thin_below, defaults.volume_heavy_above)
        for series in volume_series()
    )


def _volume_axes(cut: VolumeCut) -> dict[str, list[AxisValue]]:
    """Return the series and the cut one volume-form stratum reads.

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
    """Yield once per (series, tail size, state): which of the three statements an edge belongs to."""
    for cut in cuts:
        for state in volume.VolumeState:
            yield f"volume={state.name}@{cut.name}", _volume_axes(cut) | {"volume_filter": [state.bit]}


def _volume_forms() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the form stratification at the raw thresholds, which is what an unfitted run gets."""
    yield from _volume_cells(raw_volume_cuts())


def _compression_axes(form: compression.CompressionForm) -> dict[str, list[AxisValue]]:
    """Return the series one compression stratum reads. Both forms read every axis, so none is dropped."""
    return {
        "compression_form": [int(form)],
        "compression_period": [COMPRESSION_PERIOD],
        "compression_baseline_bars": [COMPRESSION_BASELINE_BARS],
    }


def _compression() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per compression state, at the one form and the one cut a first pass runs."""
    for state in compression.Compression:
        yield f"compression={state.name}", {"compression_filter": [state.bit]}


def _compression_forms() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per (form, state): whether a narrow band and a short range say the same thing.

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
    """Yield once per compact trend label."""
    for label in trend.Trend:
        yield f"trend={label.name}", {"trend_filter": [label.bit]}


def _higher_timeframe() -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield once per side of the 60-minute average."""
    for side in higher_timeframe.Side:
        yield f"htf={side.name}", {"higher_timeframe_filter": [side.bit]}


STRATUM_GROUPS = {
    UNFILTERED: _unfiltered,
    REGIME: _regime,
    DIRECTIONAL: _directional,
    CONSOLIDATING: _consolidating,
    "phase": _phase,
    MIDDAY: _midday,
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

RECUTS = frozenset({DIRECTIONAL, CONSOLIDATING, TREND_UP, MIDDAY, VOLUME_FORMS, COMPRESSION_FORMS})
"""Groups that re-cut a dimension another group already owns, so ``all`` leaves them out."""

EVERY_DIMENSION = tuple(group for group in STRATUM_GROUPS if group not in RECUTS)
"""Each context dimension once, at the cut the campaign ran -- what ``all`` names."""

ORB_REVERSION_STRATA = (UNFILTERED, CONSOLIDATING)
"""The two cells both reversion entries are asked about, stated before either run."""

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
    ELASTIC_CHANNEL: (UNFILTERED, VOLUME_FORMS),
    ELASTIC_RECOVERY: (UNFILTERED,),
    ELASTIC_BAND_STOP: (UNFILTERED,),
    EMAPULLBACK_TRAIL: EVERY_DIMENSION,
    EMAPULLBACK_CONFIRM: EVERY_DIMENSION,
    IBT_SIZING: (UNFILTERED, MIDDAY),
    IBT_SIZING_HIGH: (UNFILTERED, MIDDAY),
    IBT_STRUCTURE: EVERY_DIMENSION,
    IBT_STRUCTURE_ENDS: EVERY_DIMENSION,
    CONFLUENCE_SIZING: (UNFILTERED, REGIME, "phase", VOLUME_FORMS, "compression", "trend", "htf"),
    HOLD: (UNFILTERED,),
    EARLY_EXIT: (UNFILTERED,),
    EARLY_EXIT_2: (UNFILTERED,),
    SPEC: (UNFILTERED,),
    ALL_STRATA: EVERY_DIMENSION,
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

    A cell rather than an axis, because the thresholds move with the lookback --
    ``docs/roadmap.md`` §M31.
    """
    for cut in calibration:
        yield (
            f"{name}@{cut.name}",
            axes
            | {
                "regime_lookback": [cut.lookback],
                "regime_consolidating_below": [cut.consolidating_below],
                "regime_directional_above": [cut.directional_above],
            },
        )


def strata(
    which: str,
    cuts: Cuts = NO_CUTS,
) -> Iterator[tuple[str, dict[str, list[AxisValue]]]]:
    """Yield the stratifications ``which`` names, unfiltered first wherever it is included."""
    for group in STRATUM_SETS[which]:
        if group == VOLUME_FORMS and cuts.volume:
            yield from _volume_cells(cuts.volume)
            continue

        for name, axes in STRATUM_GROUPS[group]():
            if group not in REGIME_GROUPS or not cuts.regime:
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

    return tuple(
        RegimeCut(lookback, *grid.thresholds_for(lookback, *quantiles), quantiles=quantiles)
        for lookback in sorted(lookbacks)
    )


def calibrate_volume(
    frame: pd.DataFrame,
    minutes: int,
    tails: Sequence[tuple[float, float]],
    series: Sequence[volume.VolumeKey],
) -> VolumeCalibration:
    """Fit a threshold pair per (series, tail size) to ``frame``'s own relative volumes.

    Each series is fitted against its own distribution -- ``docs/roadmap.md`` §M27.8.
    """
    spec = context.ContextSpec(volume_keys=tuple(series), needs_time_of_day=True)
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
    base: ArchetypeParams
    axes: dict[str, list[AxisValue]] = field(default_factory=dict)
    resolutions: tuple[int, ...] = RESOLUTIONS
    """Bar sizes this variant can be run at; a session-anchored range cannot run at all of them."""

    def sized(self) -> int:
        """Count how many combinations this variant's own axes make."""
        total: int = 1
        for values in self.axes.values():
            total *= len(values)

        return total

    def runs_at(self, minutes: int) -> bool:
        """Return whether this variant is expressible at one resolution."""
        return minutes in self.resolutions


def _costed(params: ParamsT, root: str) -> ParamsT:
    """Return the same rule set with this root's real costs on it."""
    return TradingCosts(commission_per_contract=COMMISSION[root], slippage_ticks=SLIPPAGE_TICKS).apply(params)


def deadcat_variants(root: str) -> list[Variant]:
    """Build one variant: the entry gates, the moving-average kind, and how far the targets sit."""
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
    """Build one variant: all three gates are on by default, so all three periods are live."""
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
    """Build two variants, one per stop geometry, because each reads an axis the other ignores.

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


def emapullback_variants(root: str) -> list[Variant]:
    """Build one variant: both averages crossed over kind and period, and the entry's own three axes."""
    return [
        Variant(
            name="stop=slow",
            archetype=archetypes.EMAPULLBACK,
            base=_costed(EmaPullbackParams(), root),
            axes={
                "fast_kind": ["ema", "sma", "wma", "hma"],
                "fast_period": [5, 9, 13, 20],
                "slow_kind": ["ema", "sma"],
                "slow_period": [30, 50, 100, 200],
                "min_bars_extended": [1, 3, 5],
                "touch_mode": [TOUCH_WICK, TOUCH_CLOSE, TOUCH_ANY],
                "require_turn": [False, True],
            },
        ),
    ]


def insidebar_variants(root: str) -> list[Variant]:
    """Build one variant: the three gates, the breakout margin and the lopsided ATR geometry."""
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
"""InsideBar's entry, held per resolution at the modal value of §M27's own DIRECTIONAL top twenty."""

NARROW_TP = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
"""Target distances in ATRs from the fill. Opens at the ``1.0`` the campaign was stuck with and
runs well past it, because the lopsided bracket is what Gate 4 stops on."""

NARROW_ATR = [2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
"""Stop distances in ATRs beyond the signal bar. Covers §M27's 5/10/20 and extends below it,
since a tighter stop is the other half of the same asymmetry."""


def insidebar_narrow_variants(root: str) -> list[Variant]:
    """Build one variant per resolution: the campaign's entry, crossed over the bracket it never swept.

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
    """Build one variant: InsideBar's entry against the split-lot trailing exit's own axes."""
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
    """Return the target ladder a stored ElasticBand variant name carries.

    Read off the name's ``target=`` token, because a tuple is not sweepable and so is not a
    stored column.
    """
    for token in variant.split():
        if token in ELASTIC_LADDERS:
            return ELASTIC_LADDERS[token]

    msg = f"no target ladder in the ElasticBand variant name {variant!r}; known: {sorted(ELASTIC_LADDERS)}"
    raise KeyError(msg)


def elasticband_variants(root: str) -> list[Variant]:
    """Build one variant per target ladder, each sweeping the entry, the stop mode and a time stop."""
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
"""Two of :data:`ELASTIC_LADDERS`' four: the midline, and the one patience found."""

ELASTIC_SHAPES: dict[str, tuple[int, float]] = {
    "shape=any": (SHAPE_ANY, 0.5),
    "shape=reversal": (SHAPE_REVERSAL, 0.5),
    "shape=reclaim": (SHAPE_RECLAIM, 0.5),
    "shape=rejection@0.4": (SHAPE_REJECTION, 0.4),
    "shape=rejection@0.6": (SHAPE_REJECTION, 0.6),
}
"""What the signal bar itself has to look like, and the rejection depth where one is read."""


def elasticband_shape_variants(root: str) -> list[Variant]:
    """Build §M26.5's run: what the signal bar looks like, over the source §M26.4 left standing.

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


ELASTIC_VOLUME_BRACKET: dict[str, list[AxisValue]] = {
    "entry_std": [2.0, 2.5, 3.0],
    "stop_mode": [STOP_ATR, STOP_SWING, STOP_CATASTROPHE],
    "max_hold_bars": [0, 30],
}
"""The bracket the volume question is asked over, held by §M26.9 and by §M33.

Copy it into a variant rather than sharing the dict, so nothing downstream can mutate both sets
at once.
"""


def elasticband_volume_variants(root: str) -> list[Variant]:
    """Build §M26.9's run: the shape crossed with the volume states, over a bracket held still."""
    axes: dict[str, list[AxisValue]] = dict(ELASTIC_VOLUME_BRACKET)

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


ELASTIC_CHANNEL_SOURCES: dict[str, int] = {
    "channel=vwap": BAND_VWAP,
    "channel=bollinger": BAND_BOLLINGER,
}
"""The two channels the volume question has been asked over."""

ELASTIC_CHANNEL_PERIOD = 20
"""The Bollinger period this set pins, where §M30 swept three."""


def elasticband_channel_variants(root: str) -> list[Variant]:
    """Build §M33's run: the channel crossed with the shape, over §M26.9's bracket."""
    axes: dict[str, list[AxisValue]] = dict(ELASTIC_VOLUME_BRACKET)

    return [
        Variant(
            name=f"channel-volume {channel_name} {shape_name} {ELASTIC_VOLUME_TARGET}",
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(
                    band_source=source,
                    band_period=ELASTIC_CHANNEL_PERIOD,
                    signal_shape=shape,
                    target_mode=TARGET_STRETCH,
                    target_stretch_levels=ELASTIC_LADDERS[ELASTIC_VOLUME_TARGET],
                ),
                root,
            ),
            axes=axes,
        )
        for channel_name, source in ELASTIC_CHANNEL_SOURCES.items()
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
"""Which bar of an extension signals, and how far back inside the recovery bar has to close."""


def elasticband_recovery_variants(root: str) -> list[Variant]:
    """Build §M26.6's run: the recovery trigger against the shapes, over §M26.5's channel."""
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


ELASTIC_BAND_STOP_TARGET = "target=0.0s"
"""The ladder every campaign since §M26.5 has read its tables on, held for the same reason: its
eta-squared on the held-out profit factor there was 0.0000."""

ELASTIC_BAND_STOP_SHAPES: dict[str, int] = {
    "shape=any": SHAPE_ANY,
    "shape=reversal": SHAPE_REVERSAL,
}
"""The entry the stop is measured over, held at two values rather than swept."""

ELASTIC_BAND_STOP_ARMS: dict[str, tuple[int, float]] = {
    "stop=atr": (STOP_ATR, 1.0),
    "stop=swing": (STOP_SWING, 1.0),
    "stop=catastrophe": (STOP_CATASTROPHE, 1.0),
    "stop=band@0.5": (STOP_BAND, 0.5),
    "stop=band@1.0": (STOP_BAND, 1.0),
    "stop=band@1.5": (STOP_BAND, 1.5),
    "stop=band@2.0": (STOP_BAND, 2.0),
}
"""Where the protective stop goes, and how far past ``entry_std`` the band arm puts it."""


def elasticband_band_stop_variants(root: str) -> list[Variant]:
    """Build §M26.8's run: a stop on the channel itself, against the three that are not."""
    axes: dict[str, list[AxisValue]] = {
        "entry_std": [2.0, 2.5, 3.0],
        "min_bars_outside": [1, 2],
        "max_hold_bars": [0, 30],
    }

    return [
        Variant(
            name=f"{arm} {shape_name} {ELASTIC_BAND_STOP_TARGET}",
            archetype=archetypes.ELASTICBAND,
            base=_costed(
                ElasticBandParams(
                    band_source=BAND_VWAP,
                    signal_shape=shape,
                    stop_mode=stop_mode,
                    band_stop_std=depth,
                    target_mode=TARGET_STRETCH,
                    target_stretch_levels=ELASTIC_LADDERS[ELASTIC_BAND_STOP_TARGET],
                ),
                root,
            ),
            axes=axes,
        )
        for arm, (stop_mode, depth) in ELASTIC_BAND_STOP_ARMS.items()
        for shape_name, shape in ELASTIC_BAND_STOP_SHAPES.items()
    ]


ORB_WINDOWS = (5, 15, 30)
"""Opening-range windows, the three every source means -- ``docs/roadmap.md`` §M28."""


def orb_resolutions(anchor: int, window: int) -> tuple[int, ...]:
    """Return which campaign resolutions can express a range of ``window`` minutes from ``anchor``.

    Both the anchor and the window have to be whole numbers of bars.
    """
    return tuple(minutes for minutes in RESOLUTIONS if anchor % minutes == 0 and window % minutes == 0)


def openingrange_variants(root: str) -> list[Variant]:
    """Build one variant per (window, stop, target), because each triple reads axes the others do not.

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


def squeeze_variants(root: str) -> list[Variant]:
    """Build one variant per (stop, target), for OpeningRange's reason: each pair reads axes others do not."""
    shared: dict[str, list[AxisValue]] = {
        "direction": [trades.LONG, trades.SHORT],
        "squeeze_form": [
            int(compression.CompressionForm.BANDWIDTH),
            int(compression.CompressionForm.RANGE_TO_ATR),
        ],
        "squeeze_period": [10, 20, 40],
        "squeeze_below": [0.05, 0.1, 0.25],
        "min_squeeze_bars": [1, 5],
        "entry_offset_ticks": [1, 4],
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
            name=f"{stop_name} {target_name}",
            archetype=archetypes.SQUEEZEBREAKOUT,
            base=_costed(SqueezeBreakoutParams(stop_mode=stop_mode, target_mode=target_mode), root),
            axes={**shared, **stop_axes, **target_axes},
        )
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
"""The ranges the §M28.2 re-sweep trades: §M28's anchor axis, which §M28.1 never left."""

ORB_ENTRIES: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
    "entry=breakout": (ORB_ENTRY_BREAKOUT, {"entry_offset_ticks": [1, 4]}),
    "entry=fade": (ORB_ENTRY_FADE, {"entry_offset_ticks": [1, 4], "break_confirm_ticks": [0, 8]}),
    "entry=retest": (ORB_ENTRY_RETEST, {"retest_offset_ticks": [0, 4], "break_confirm_ticks": [0, 8]}),
}
"""The three entry mechanisms, each with the axes only it reads."""

type OrbTarget = tuple[str, int, tuple[float, ...], dict[str, list[AxisValue]]]
"""One target scheme: its name, the mode, the per-leg ladder and the axes only it reads."""

ORB_TARGETS: dict[str, tuple[int, dict[str, list[AxisValue]]]] = {
    "target=R": (ORB_TARGET_R, {"tp_multiplier": [1.0, 2.0]}),
    "target=width": (ORB_TARGET_WIDTH, {}),
}
"""The two target schemes §M28.2 crossed every entry with, at the default width ladder."""


def _orb_further_targets() -> list[OrbTarget]:
    """Return :data:`ORB_TARGETS` in the shape :func:`_orb_fade_targets` returns.

    The ladder is the parameter default rather than a copy of it, so a variant built here and
    one §M28.2 stored carry the same tuple.
    """
    default: tuple[float, ...] = OpeningRangeParams().target_width_multiples

    return [(name, mode, default, axes) for name, (mode, axes) in ORB_TARGETS.items()]


ORB_FRACTIONS = [0.25, 0.5, 0.75, 1.0]
"""How far back across the range the stop sits, in range widths."""


def openingrange_further_variants(root: str) -> list[Variant]:
    """Build §M28.2's re-sweep: the anchor axis, the three entry mechanisms and one stop axis.

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
"""How far outside the extreme a fade's stop sits, in range widths -- §M28.5's axis."""

ORB_FADE_LADDERS: dict[str, tuple[float, ...]] = {
    "target=width": (1.0, NAN),
    "target=width+mid": (0.5, 1.0, NAN),
}
"""Per-leg targets as multiples of the range width, past the trigger."""


def openingrange_fade_variants(root: str) -> list[Variant]:
    """Build §M28.5's re-run: the fade alone, with the bracket §M28.2 parked it for.

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
    """Return the three target schemes §M28.5 crosses: the R ladder and two width ladders.

    A ladder is a tuple, so it is a variant rather than an axis -- see :class:`Variant`. The
    width multiples ride along under :data:`ORB_TARGET_R` too, where nothing reads them.
    """
    default: tuple[float, ...] = ORB_FADE_LADDERS["target=width"]

    return [
        ("target=R", ORB_TARGET_R, default, {"tp_multiplier": [1.0, 2.0]}),
        *((name, ORB_TARGET_WIDTH, ladder, {}) for name, ladder in ORB_FADE_LADDERS.items()),
    ]


ORB_REJECTION_OFFSETS = [0, 1, 4, 8]
"""How far inside the extreme the rejection's limit rests, in ticks -- §M28.7's entry axis."""


def openingrange_rejection_variants(root: str) -> list[Variant]:
    """Build §M28.7's run: the rejection alone, over the bracket §M28.5 measured the fade on."""
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
"""All four entries, each carrying what its own campaign gave it rather than one shared grid."""

ORB_GEOMETRY_WINDOWS = (5, 15, 30, 45, 60, 90, 120, sessionrange.CASH_OPEN_MINUTES)
"""Range lengths in minutes: §M28's three, the hour most sources call "the ORB", and those either side."""


def orb_geometry_ranges() -> dict[str, sessionrange.RangeKey]:
    """Return every (anchor, window) the session leaves room to trade, one entry per cell of the cross.

    Derived from the session template: a range must complete before the phase the forced flat
    falls in.
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
    """Build §M28.8's run: the range's anchor crossed with its length, on all four entries.

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
"""The two ranges whose breakout separates from a permuted range, and no others."""

ORB_FOLLOW_THROUGH_LOOKBACKS = (20, 60, 250)
"""How many prior sessions the trailing median is taken over: a month, a quarter, a year."""

ORB_FOLLOW_THROUGH_MODES: dict[str, int] = {
    "scale=target": ORB_SCALE_TARGET,
    "scale=stop": ORB_SCALE_STOP,
    "scale=both": ORB_SCALE_BOTH,
}
"""Which halves of the bracket the trailing follow-through is applied to."""


def openingrange_follow_through_variants(root: str) -> list[Variant]:
    """Build §M28.10's run: the bracket denominated in trailing reach, against an unscaled control."""
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
"""The two ranges §M28.8's gate 3 separated from a permuted range, and no others."""

ORB_LADDER_FRACTIONS = [*ORB_FRACTIONS, 1.5, 2.0, 3.0, 5.0]
"""§M28.2's stop axis carried past the boundary its best value sat on."""

ORB_WIDTH_LADDERS: dict[str, tuple[float, ...]] = {
    "target=w0.5": (0.5, NAN),
    "target=w1.0": OpeningRangeParams().target_width_multiples,
    "target=w2.0": (2.0, NAN),
    "target=w3.0": (3.0, NAN),
    "target=w1.0+2.0": (1.0, 2.0, NAN),
    "target=runner": (NAN, NAN),
}
"""Per-leg targets as multiples of the range width past the trigger, one variant each."""


def openingrange_bracket_variants(root: str) -> list[Variant]:
    """Build §M28.11's run: the stop ladder past its boundary, crossed with the width ladder."""
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
"""What every spec variant holds in common: a coarse cut of the axes §M27 already measured."""

SPEC_STOPS: dict[str, tuple[bool, dict[str, list[AxisValue]]]] = {
    "stop=atr": (True, {"atr_stop_multiple": [1.5, 3.0]}),
    "stop=swing": (False, {"swing_lookback": [1, 3]}),
}
"""The two initial stops, carried through every spec variant."""

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
"""Whether the stop trails a moving average, and the three axes only the trailing half reads."""

SPEC_ROUNDS: dict[str, dict[str, list[AxisValue]]] = {
    "round=off": {},
    "round=on": {"round_number_points": [5.0, 25.0], "round_number_offset_ticks": [2, 8]},
}
"""The round-number spacings tried, against a control that avoids nothing; every cell needs raw prices."""


class ConfluenceFilters(TypedDict):
    """The three filter masks a confluence count is measured over."""

    regime_filter: int
    volume_filter: int
    compression_filter: int


SPEC_CONFLUENCE_FILTERS: ConfluenceFilters = {
    "regime_filter": regime.Regime.DIRECTIONAL.bit,
    "volume_filter": volume.VolumeState.HEAVY.bit,
    "compression_filter": compression.Compression.EXPANDED.bit,
}
"""The three filters a confluence count is measured over, all of them side-neutral."""


def spec_variants(root: str) -> list[Variant]:
    """Build the [#74] axes, each against a control run on the same bars in the same pass.

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


type VariantBuilders = dict[str, Callable[[str], list[Variant]]]
"""Each archetype's variant builder, keyed by its name."""

VARIANTS: VariantBuilders = {
    "DeadCatBounce": deadcat_variants,
    "PullBackAndGo": pullback_variants,
    "EmaCrossover": crossover_variants,
    "EmaPullback": emapullback_variants,
    "InsideBar": insidebar_variants,
    "InsideBarTrailing": insidebartrailing_variants,
    "ElasticBand": elasticband_variants,
    "OpeningRange": openingrange_variants,
    "SqueezeBreakout": squeeze_variants,
}
"""Archetype name -> the variants swept for it, built per root so costs are the root's.

This is what §M27 measured, so a re-sweep that changes an axis belongs in its own entry of
:data:`VARIANT_SETS`.
"""

NARROW_VARIANTS: VariantBuilders = {"InsideBar": insidebar_narrow_variants}
"""The §M27.3 re-sweep: one archetype, the bracket pair §M27 could not cross."""

ORB_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_further_variants}
"""The §M28.2 re-sweep: §M28's deferred anchors, entries and stop levels, over §M28.1's
archetype. Its own set rather than an edit to :data:`VARIANTS`, which is what §M28.1 measured
and what the stored rows were produced by."""

ORB_FADE_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_fade_variants}
"""The §M28.5 re-run: the fade alone, with a stop tighter than §M28.2's axis reached and a
target that stops at the middle of the range -- ``docs/roadmap.md`` §M28.5."""

ORB_BRACKET_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_bracket_variants}
"""The §M28.11 run: the stop ladder carried past the value it stopped on, crossed with the
width ladder no ORB campaign has ever varied -- [#262]."""

ORB_FOLLOW_THROUGH_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_follow_through_variants}
"""The §M28.10 run: the bracket denominated in trailing follow-through rather than in the
session's own range width, over the two ranges §M28.8's null separated -- [#261]."""

ORB_GEOMETRY_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_geometry_variants}
"""The §M28.8 run: the anchor axis §M28.2 opened, crossed with the length axis nothing had swept."""

ORB_REJECTION_VARIANTS: VariantBuilders = {"OpeningRange": openingrange_rejection_variants}
"""The §M28.7 run: the rejection alone, over §M28.5's bracket, so that the two reversion
entries differ by their entry rule and nothing else -- ``docs/roadmap.md`` §M28.7."""

ELASTIC_SHAPE_VARIANTS: VariantBuilders = {"ElasticBand": elasticband_shape_variants}
"""The §M26.5 run: the two signal-bar requirements [#221] asked for, each against the
``shape=any`` control in the same pass. Its own set rather than an edit to :data:`VARIANTS`
for that dict's own reason -- ``docs/roadmap.md`` §M26.5."""

ELASTIC_VOLUME_VARIANTS: VariantBuilders = {"ElasticBand": elasticband_volume_variants}
"""The §M26.9 run: §M26.5's shape pair over a held bracket, so that the volume strata are
the only cells the pass adds. The names carry ``break-volume`` where the stored shape rows
carry none, so the two runs cannot collide in one database -- ``docs/roadmap.md`` §M26.9."""

ELASTIC_CHANNEL_VARIANTS: VariantBuilders = {"ElasticBand": elasticband_channel_variants}
"""The §M33 run: §M26.9's bracket and shape pair, crossed with the channel §M30 read its
opposite answer on. The names carry ``channel-volume`` where §M26.9's carry ``break-volume``,
so the two runs cannot collide in one database -- ``docs/roadmap.md`` §M33."""

ELASTIC_RECOVERY_VARIANTS: VariantBuilders = {"ElasticBand": elasticband_recovery_variants}
"""The §M26.6 run: the recovery trigger against the shapes it replaces, in one pass. The names
carry an ``entry=`` token where the stored shape rows carry none, so the two runs cannot collide
in one database -- ``docs/roadmap.md`` §M26.6."""

ELASTIC_BAND_STOP_VARIANTS: VariantBuilders = {"ElasticBand": elasticband_band_stop_variants}
"""The §M26.8 run: the stop on the band itself against the three stops that are not, over one
entry pair. The names carry a ``stop=`` token where every stored ElasticBand row carries none,
so the two runs cannot collide in one database -- ``docs/roadmap.md`` §M26.8."""

HOLD_BARS = (0, 5, 10, 20, 40, 80)
"""Maximum hold times in bars, ``0`` being the uncapped arm every stored campaign ran."""


def _held(build: Callable[[str], list[Variant]]) -> Callable[[str], list[Variant]]:
    """Re-emit one archetype's stored campaign variants once per rung of the hold ladder.

    ``max_hold_bars`` is dropped from the axes, or an archetype that sweeps it would beat the
    ladder -- ``tools/README.md`` § "campaign_sweep.py".
    """

    def variants(root: str) -> list[Variant]:
        return [
            replace(
                variant,
                name=f"{variant.name} hold={bars}",
                base=replace(variant.base, max_hold_bars=bars),
                axes={k: v for k, v in variant.axes.items() if k != "max_hold_bars"},
            )
            for variant in build(root)
            for bars in HOLD_BARS
        ]

    return variants


HOLD_VARIANTS: VariantBuilders = {name: _held(build) for name, build in VARIANTS.items()}
"""The [#292] run: every archetype's stored campaign grid, once per maximum hold time."""

EARLY_EXIT_BARS = (3, 5, 10, 20)
"""The bar at which the not-working exit is tested, every one below ElasticBand's hold cap of 30."""

EARLY_EXIT_BELOW_R = (-0.5, 0.0, 0.25, 0.5)
"""The open profit, in R, the not-working exit requires at that bar; ``0`` is "losing at bar N"."""

EARLY_EXIT_MINUTES = (15, 30, 60, 120)
"""The window before the session close in which a losing position is closed."""

EARLY_EXIT_MARKER = " exit="
"""What every ``--variants early-exit`` name carries between its base variant and its arm."""


def early_exit_arms() -> dict[str, dict[str, AxisValue | bool]]:
    """Return every early-exit arm by name, each the fields it sets and ``off`` setting none."""
    arms: dict[str, dict[str, AxisValue | bool]] = {"off": {}}
    for bars in EARLY_EXIT_BARS:
        for below_r in EARLY_EXIT_BELOW_R:
            arms[f"bars{bars}@{below_r:g}R"] = {"early_exit_bars": bars, "early_exit_below_r": below_r}

    for minutes in EARLY_EXIT_MINUTES:
        arms[f"close{minutes}m"] = {"early_exit_minutes_before_close": minutes}

    for only_if_losing in (False, True):
        suffix: str = "-losing" if only_if_losing else ""
        arms[f"regime{suffix}"] = {
            "early_exit_on_regime_change": True,
            "early_exit_only_if_losing": only_if_losing,
        }
        for form, form_name in TREND_EXIT_FORMS.items():
            if form == TREND_EXIT_OFF:
                continue

            arms[f"trend-{form_name.replace('_', '-')}{suffix}"] = {
                "early_exit_on_trend": form,
                "early_exit_only_if_losing": only_if_losing,
            }

    return arms


def _exited(
    build: Callable[[str], list[Variant]],
    arms: Callable[[], dict[str, dict[str, AxisValue | bool]]],
    marker: str,
) -> Callable[[str], list[Variant]]:
    """Re-emit one archetype's stored campaign variants once per arm of a set, axes unchanged."""

    def variants(root: str) -> list[Variant]:
        every: dict[str, dict[str, AxisValue | bool]] = arms()

        return [
            replace(variant, name=f"{variant.name}{marker}{arm}", base=replace(variant.base, **fields))
            for variant in build(root)
            for arm, fields in every.items()
        ]

    return variants


EARLY_EXIT_VARIANTS: VariantBuilders = {
    name: _exited(build, early_exit_arms, EARLY_EXIT_MARKER) for name, build in VARIANTS.items()
}
"""The [#369] run: every archetype's stored campaign grid, once per early-exit arm."""

EXCURSION_BARS = EARLY_EXIT_BARS
"""The bar at which the excursion exit is tested, which is the not-working exit's ladder."""

EXCURSION_REACHED_R = (0.5, 1.0)
"""The favourable excursion, in R, a position has to have reached by that bar to stay."""

NOT_WORKING_MINUTES = (15, 30, 60)
"""The age in minutes at which the not-working exit is tested; 30 is ``Trading-Docs`` §7.2's."""

AGE_STOP_BARS = (3, 5, 10)
"""The age in bars at which the stepped age stop moves."""

AGE_STOP_FRACTIONS = (0.5, 1.0)
"""How far of the way to the entry the stepped age stop moves: half way, or to the entry."""

AGE_LINE_BARS = (10, 20)
"""The age in bars by which the age stop's line reaches the entry."""

LATE_STOP_MINUTES = (15, 30, 60)
"""The window before the session close in which the late stop moves."""

BREAKEVEN_AT_R = (0.5, 1.0)
"""The open profit, in R and on the close, at which the breakeven stop moves."""

EARLY_EXIT_2_MARKER = " exit2="
"""What every ``--variants early-exit-2`` name carries between its base variant and its arm."""


def tier2_arms() -> dict[str, dict[str, AxisValue | bool]]:
    """Return every arm of #369's second tier, and two breakeven arms, by name, ``off`` setting none."""
    return {"off": {}, **_tier2_market_exits(), **_tier2_stop_moves()}


def _tier2_market_exits() -> dict[str, dict[str, AxisValue | bool]]:
    """Return the second tier's market-exit arms: the excursion, the minutes form and the invalidation."""
    arms: dict[str, dict[str, AxisValue | bool]] = {}
    excursion: dict[str, AxisValue] = {"early_exit_measure": MEASURE_EXCURSION}
    for bars in EXCURSION_BARS:
        for reached in EXCURSION_REACHED_R:
            arms[f"excursion{bars}@{reached:g}R"] = {
                "early_exit_bars": bars,
                **excursion,
                "early_exit_below_r": reached,
            }

    for minutes in NOT_WORKING_MINUTES:
        arms[f"losing{minutes}m"] = {"early_exit_minutes": minutes}
        arms[f"excursion{minutes}m@0.5R"] = {
            "early_exit_minutes": minutes,
            **excursion,
            "early_exit_below_r": 0.5,
        }

    for only_if_losing in (False, True):
        suffix: str = "-losing" if only_if_losing else ""
        arms[f"invalidated{suffix}"] = {
            "early_exit_on_invalidation": True,
            "early_exit_only_if_losing": only_if_losing,
        }

    return arms


def _tier2_stop_moves() -> dict[str, dict[str, AxisValue | bool]]:
    """Return the second tier's stop-moving arms, the age stop and the late stop, then the breakeven's."""
    arms: dict[str, dict[str, AxisValue | bool]] = {}
    for bars in AGE_STOP_BARS:
        for fraction in AGE_STOP_FRACTIONS:
            arms[f"step{bars}@{fraction:g}"] = {"age_stop_bars": bars, "age_stop_fraction": fraction}

    for bars in AGE_LINE_BARS:
        arms[f"line{bars}"] = {"age_stop_bars": bars, "age_stop_shape": AGE_STOP_LINE}

    for bars in AGE_STOP_BARS:
        arms[f"step{bars}@0.5-losing"] = {
            "age_stop_bars": bars,
            "age_stop_fraction": 0.5,
            "age_stop_only_if_losing": True,
        }

    for minutes in LATE_STOP_MINUTES:
        for level, level_name in LATE_STOP_LEVELS.items():
            arms[f"late{minutes}m-{level_name.replace('_', '-')}"] = {
                "late_stop_minutes_before_close": minutes,
                "late_stop_to": level,
            }

    for at in BREAKEVEN_AT_R:
        arms[f"breakeven@{at:g}R"] = {"breakeven_at": at}

    return arms


EARLY_EXIT_2_VARIANTS: VariantBuilders = {
    name: _exited(build, tier2_arms, EARLY_EXIT_2_MARKER) for name, build in VARIANTS.items()
}
"""The second [#369] run: every archetype's stored campaign grid, once per tier-2 arm."""

EMAPULLBACK_TRAILS: dict[str, dict[str, bool]] = {
    "trail=off": {"trail_ma_stop": False},
    "trail=slow": {"trail_ma_stop": True, "trail_on_slow": True},
}
"""The fixed stop, and the stop trailed on the slow average at the offset that placed it."""


def emapullback_trail_variants(root: str) -> list[Variant]:
    """Build §M35's variant once per stop, so the two arms share every axis and differ by the trail."""
    (campaign,) = emapullback_variants(root)

    return [
        replace(campaign, name=f"{campaign.name} {trail_name}", base=replace(campaign.base, **trail))
        for trail_name, trail in EMAPULLBACK_TRAILS.items()
    ]


EMAPULLBACK_TRAIL_VARIANTS: VariantBuilders = {"EmaPullback": emapullback_trail_variants}
"""The [#313] run: EmaPullback's stored grid with the stop fixed and trailed on the slow average.
Every name carries a ``trail=`` token no stored row has, so the two runs cannot collide in one
database -- ``docs/findings/m37-ema-pullback-trail-on-slow.md``."""

EMAPULLBACK_ENTRIES: dict[str, dict[str, bool | int]] = {
    "entry=market": {"confirm_entry": False},
    "entry=confirm life=1": {"confirm_entry": True, "entry_order_lifetime_bars": 1},
    "entry=confirm life=3": {"confirm_entry": True, "entry_order_lifetime_bars": 3},
}
"""The market entry, and the stop order beyond the signal bar resting for one bar and for three.

The ``entry=market`` arm is the control, run on the same bars in the same pass."""

EMAPULLBACK_HELD_KINDS = ("fast_kind", "slow_kind")
"""The two axes the confirmation run holds at the archetype's own ``ema``."""


def emapullback_confirm_variants(root: str) -> list[Variant]:
    """Build §M35's variant once per entry, so the three arms share every axis and differ by the order."""
    (campaign,) = emapullback_variants(root)
    axes: dict[str, list[AxisValue]] = {
        axis: values for axis, values in campaign.axes.items() if axis not in EMAPULLBACK_HELD_KINDS
    }

    return [
        replace(
            campaign, name=f"{campaign.name} {entry_name}", base=replace(campaign.base, **entry), axes=axes
        )
        for entry_name, entry in EMAPULLBACK_ENTRIES.items()
    ]


EMAPULLBACK_CONFIRM_VARIANTS: VariantBuilders = {"EmaPullback": emapullback_confirm_variants}
"""The [#311] run: EmaPullback's market entry against its confirmation entry. Every name carries an
``entry=`` token no stored row has, so the runs cannot collide in one database --
``docs/findings/m39-ema-pullback-confirmation-entry.md``."""


SIZING_CUTS_SUFFIX = "-sizing-cuts.json"


def sizing_cuts_path(name: str) -> paths.Path:
    """Return where ``tools/campaign_sizing.py fit`` writes one archetype's selection-window cuts."""
    return CAMPAIGN_DIR / f"{name}{SIZING_CUTS_SUFFIX}"


SIZING_CUTS = sizing_cuts_path("InsideBarTrailing")
"""§M45's cuts, which the ``ibt-sizing`` arms read."""

SIZING_LABEL_QUANTILES = (0.20, 0.80)
"""Where the regime and volume labels a size counts are cut: each extreme a fifth of its own series.

The campaign's regime pair and one of its volume tails, so a sizing label and a stratum mean the
same thing -- ``docs/roadmap.md`` §M27.5 and §M27.8."""


@dataclass(frozen=True, slots=True)
class SizingCut:
    """The thresholds a sizing arm runs at on one root, resolution and variant, fitted before any runs."""

    root: str
    minutes: int
    regime_consolidating_below: float
    regime_directional_above: float
    volume_thin_below: float
    volume_heavy_above: float
    labels: tuple[str, ...]
    """The ``size_on_*`` labels the add-only arms count: the ones the fit did not drop."""

    symmetric_labels: tuple[str, ...] | None = None
    """The labels the symmetric arm counts, or ``None`` on a cut stored before the fit read them.

    Every label :attr:`labels` keeps and any it drops that still sorts once a step comes off
    where the label opposes -- ``docs/findings/m47-confluence-sizing-preregistration.md``."""

    variant: str | None = None
    """The stored variant the labels were fitted at, or ``None`` on an archetype with only one."""

    early_max_extension_atr: float | None = None
    early_max_trend_bars: int | None = None
    """InsideBarTrailing's earliness cuts, and ``None`` on every other archetype."""

    def thresholds(self) -> dict[str, AxisValue]:
        """Return the regime and volume thresholds the labels are read at."""
        return {
            "regime_consolidating_below": self.regime_consolidating_below,
            "regime_directional_above": self.regime_directional_above,
            "volume_thin_below": self.volume_thin_below,
            "volume_heavy_above": self.volume_heavy_above,
        }

    def fitted(self) -> dict[str, AxisValue]:
        """Return the parameter values every arm on this cell takes, whichever of them it reads."""
        earliness: dict[str, float | None] = {
            "early_max_extension_atr": self.early_max_extension_atr,
            "early_max_trend_bars": self.early_max_trend_bars,
        }

        return self.thresholds() | {name: value for name, value in earliness.items() if value is not None}

    def fits(self, variant: str) -> bool:
        """Return whether this cut was fitted for ``variant``: every variant, where it names none."""
        return self.variant is None or self.variant == variant


def sizing_cuts(path: paths.Path | None = None) -> list[SizingCut]:
    """Load the fitted cuts, or refuse by name where nothing has been fitted yet.

    §M45's file carries no variant and no symmetric labels, and only InsideBarTrailing's carry
    earliness cuts.
    """
    source: paths.Path = SIZING_CUTS if path is None else path
    if not source.exists():
        strategy: str = source.name.removesuffix(SIZING_CUTS_SUFFIX)
        msg: str = f"no sizing cuts at {source}; run tools/campaign_sizing.py fit --strategy {strategy} first"
        raise SystemExit(msg)

    cuts: list[SizingCut] = []
    for cut in json.loads(source.read_text(encoding="utf-8")):
        variant, symmetric, extension, trend_bars = (
            cut.get(name)
            for name in ("variant", "symmetric_labels", "early_max_extension_atr", "early_max_trend_bars")
        )
        cuts.append(
            SizingCut(
                root=str(cut["root"]),
                minutes=int(cut["minutes"]),
                regime_consolidating_below=float(cut["regime_consolidating_below"]),
                regime_directional_above=float(cut["regime_directional_above"]),
                volume_thin_below=float(cut["volume_thin_below"]),
                volume_heavy_above=float(cut["volume_heavy_above"]),
                labels=tuple(str(label) for label in cut["labels"]),
                symmetric_labels=None if symmetric is None else tuple(str(label) for label in symmetric),
                variant=None if variant is None else str(variant),
                early_max_extension_atr=None if extension is None else float(extension),
                early_max_trend_bars=None if trend_bars is None else int(trend_bars),
            ),
        )

    return cuts


SIZING_QUANTITIES = [3, 4, 6, 8]
"""Contract counts every sizing arm but the tiers above a half crosses: the plain axis [#295] asks for,
floored at three."""

SIZING_EARLY_SHARE = 0.25
SIZING_ESTABLISHED_SHARE = 0.5
"""``Trading-Docs`` §11's quarter and half, held rather than swept."""

SIZING_SPLITS: dict[str, float] = {
    "split=0.5": SIZING_ESTABLISHED_SHARE,
    "split=0.25": SIZING_EARLY_SHARE,
}
"""The two fixed splits §M45's tiers are read against: each tier's share on every entry."""

SIZING_TIERS: dict[str, int] = {
    "tier=first-breakout": EARLINESS_FIRST_BREAKOUT,
    "tier=sma-extension": EARLINESS_SMA_EXTENSION,
    "tier=trend-age": EARLINESS_TREND_AGE,
}
"""The three earliness rules, each run as written and inverted -- the inverse is the placebo."""

SIZING_HIGH_QUANTITIES = [5, 6, 8, 10]
"""Contract counts the tiers above a half cross."""

SIZING_HIGH_EARLY_SHARE = 0.6
SIZING_HIGH_ESTABLISHED_SHARE = 0.8
"""The shares the tiers above a half run at: an early entry's, then an established one's."""

SIZING_HIGH_SPLITS: dict[str, float] = {
    "split=0.8": SIZING_HIGH_ESTABLISHED_SHARE,
    "split=0.6": SIZING_HIGH_EARLY_SHARE,
}
"""The two fixed splits the tiers above a half are read against, the established share first."""

SIZING_CONFLUENCE = "size=confluence"
SIZING_STEP = 1
"""Contracts a confluence arm adds per favourable label: to each leg, or on InsideBarTrailing to the
whole position before its split."""


class Arm(Protocol):
    """Build one sizing arm from its name and the fields it holds over the fitted base."""

    def __call__(self, name: str, **fields: AxisValue | bool) -> Variant:
        """Return the arm called ``name``, with ``fields`` replaced on the fitted base."""
        ...


def arm_factory(
    campaign: Variant,
    cut: SizingCut,
    axes: dict[str, list[AxisValue]],
) -> Arm:
    """Return what builds one sizing arm over ``campaign`` at ``cut``, every arm on the same axes.

    Each arm is the fitted values on the base with its own fields over them. The arms share
    every axis, so :func:`tools.campaign_paired` reads each against its control cell by cell
    rather than as two shortlists of different sizes.
    """
    base: ArchetypeParams = replace(campaign.base, **cut.fitted())

    def arm(name: str, **fields: AxisValue | bool) -> Variant:
        return Variant(
            name=f"{campaign.name} {name}",
            archetype=campaign.archetype,
            base=replace(base, **fields),
            axes=axes,
            resolutions=(cut.minutes,),
        )

    return arm


def counted(labels: tuple[str, ...], **held: AxisValue | bool) -> dict[str, AxisValue | bool]:
    """Return the fields that size on ``labels`` at one step per label, beside whatever an arm holds."""
    return {**held, "quantity_per_confluence": SIZING_STEP, **dict.fromkeys(labels, True)}


def sizing_axes(campaign: Variant, quantities: list[int] | None = None) -> dict[str, list[AxisValue]]:
    """Return InsideBarTrailing's stored grid with the split held and a quantity ladder crossed in.

    The ladder is :data:`SIZING_QUANTITIES` unless ``quantities`` names another.
    """
    held: dict[str, list[AxisValue]] = {
        axis: values for axis, values in campaign.axes.items() if axis != "partial_take_profit_percentage"
    }

    return held | {"order_quantity": [*(SIZING_QUANTITIES if quantities is None else quantities)]}


def require_earliness_cuts(cut: SizingCut) -> None:
    """Refuse a cut without the earliness cuts a tier arm runs at."""
    if cut.early_max_extension_atr is not None and cut.early_max_trend_bars is not None:
        return

    msg: str = (
        f"the {cut.root} {cut.minutes}m InsideBarTrailing sizing cut holds no earliness cuts; move "
        "its file aside and run tools/campaign_sizing.py fit --strategy InsideBarTrailing"
    )
    raise SystemExit(msg)


def split_and_tier_arms(
    arm: Arm, splits: dict[str, float], early: float, established: float, suffix: str = ""
) -> list[Variant]:
    """Build each fixed split, then each earliness rule at ``early`` and ``established`` beside its inverse.

    ``suffix`` follows each tier's name, before ``inverted``.
    """
    arms: list[Variant] = [arm(name, partial_take_profit_percentage=share) for name, share in splits.items()]
    for name, mode in SIZING_TIERS.items():
        arms.append(
            arm(
                f"{name}{suffix}",
                earliness_mode=mode,
                early_partial_percentage=early,
                partial_take_profit_percentage=established,
            ),
        )
        arms.append(
            arm(
                f"{name}{suffix} inverted",
                earliness_mode=mode,
                early_partial_percentage=established,
                partial_take_profit_percentage=early,
            ),
        )

    return arms


def sizing_arms(campaign: Variant, cut: SizingCut) -> list[Variant]:
    """Build §M45's arms on one root and resolution: the stored grid with the split held.

    Refuses a cut without the earliness cuts its tier arms run at.
    """
    require_earliness_cuts(cut)
    arm: Arm = arm_factory(campaign, cut, sizing_axes(campaign))
    arms: list[Variant] = split_and_tier_arms(
        arm, SIZING_SPLITS, SIZING_EARLY_SHARE, SIZING_ESTABLISHED_SHARE
    )

    if not cut.labels:
        logger.warning(
            "  %s %dm: every label was dropped by the fit, so no confluence arm", cut.root, cut.minutes
        )

        return arms

    arms.append(
        arm(SIZING_CONFLUENCE, **counted(cut.labels, partial_take_profit_percentage=SIZING_ESTABLISHED_SHARE))
    )

    return arms


def insidebartrailing_sizing_variants(root: str) -> list[Variant]:
    """Build [#295] and [#353] over InsideBarTrailing's stored grid, one set of arms per fitted resolution."""
    (campaign,) = insidebartrailing_variants(root)

    return [arm for cut in sizing_cuts() if cut.root == root for arm in sizing_arms(campaign, cut)]


IBT_SIZING_VARIANTS: VariantBuilders = {"InsideBarTrailing": insidebartrailing_sizing_variants}
"""The [#295] and [#353] run. Every name carries a ``split=``, ``tier=`` or ``size=`` token no
stored row has, so the run cannot collide with the campaign in one database --
``docs/findings/m45-ibt-sizing-preregistration.md``."""


def sizing_high_arms(campaign: Variant, cut: SizingCut) -> list[Variant]:
    """Build §M45's splits and tiers again at the two shares above a half, on one root and resolution.

    Refuses a cut without the earliness cuts its tier arms run at.
    """
    require_earliness_cuts(cut)
    arm: Arm = arm_factory(campaign, cut, sizing_axes(campaign, SIZING_HIGH_QUANTITIES))
    shares: str = f"@{SIZING_HIGH_EARLY_SHARE:g}/{SIZING_HIGH_ESTABLISHED_SHARE:g}"

    return split_and_tier_arms(
        arm, SIZING_HIGH_SPLITS, SIZING_HIGH_EARLY_SHARE, SIZING_HIGH_ESTABLISHED_SHARE, shares
    )


def insidebartrailing_sizing_high_variants(root: str) -> list[Variant]:
    """Build the tiers above a half on InsideBarTrailing's stored grid, per fitted resolution."""
    (campaign,) = insidebartrailing_variants(root)

    return [arm for cut in sizing_cuts() if cut.root == root for arm in sizing_high_arms(campaign, cut)]


IBT_SIZING_HIGH_VARIANTS: VariantBuilders = {"InsideBarTrailing": insidebartrailing_sizing_high_variants}
"""§M45's splits and tiers at 0.6 and 0.8 rather than a quarter and a half. The tier names carry
the two shares, so no name collides with §M45's in one database --
``docs/findings/m45-ibt-sizing-result.md`` § "What this settles, and what it does not"."""

STRUCTURE_TRAIL_BARS = (2, 3, 5, 10, 20, 40)
"""How many completed bars make the box the runner's stop trails to."""

STRUCTURE_TRAIL_CUSHIONS = (0.0, 0.25, 0.5, 1.0)
"""How far behind the box's midpoint the runner's stop sits, in ATRs."""

STRUCTURE_TRAIL_WIDE_BARS = (1, *STRUCTURE_TRAIL_BARS, 80)
STRUCTURE_TRAIL_WIDE_CUSHIONS = (*STRUCTURE_TRAIL_CUSHIONS, 1.5, 2.0)
"""§M49's ladders widened: the boxes one rung past each end, the cushions two rungs past the top."""


def structure_trail_arms(
    boxes: tuple[int, ...] = STRUCTURE_TRAIL_BARS,
    cushions: tuple[float, ...] = STRUCTURE_TRAIL_CUSHIONS,
) -> dict[str, dict[str, int | float]]:
    """Return every structure-trail arm by name, each the fields it sets and ``off`` setting none."""
    arms: dict[str, dict[str, int | float]] = {"off": {}}
    for bars in boxes:
        for cushion in cushions:
            arms[f"box{bars}@{cushion:g}atr"] = {
                "structure_trail_bars": bars,
                "structure_trail_cushion_atr": cushion,
            }

    return arms


def structure_variants(root: str, token: str, arms: dict[str, dict[str, int | float]]) -> list[Variant]:
    """Build InsideBarTrailing's stored grid once per arm, named ``<token>=<arm>``, axes unchanged."""
    (campaign,) = insidebartrailing_variants(root)

    return [
        replace(campaign, name=f"{campaign.name} {token}={arm}", base=replace(campaign.base, **fields))
        for arm, fields in arms.items()
    ]


def insidebartrailing_structure_variants(root: str) -> list[Variant]:
    """Build InsideBarTrailing's stored grid once per structure-trail arm, axes unchanged."""
    return structure_variants(root, "structure", structure_trail_arms())


IBT_STRUCTURE_VARIANTS: VariantBuilders = {"InsideBarTrailing": insidebartrailing_structure_variants}
"""The [#352] run: InsideBarTrailing's stored grid with the runner trailing the high-water mark and
trailing to structure. Every name carries a ``structure=`` token no stored row has, so the run
cannot collide with the campaign in one database."""


def structure_trail_end_arms() -> dict[str, dict[str, int | float]]:
    """Return every structure-trail arm the wider ladders add to §M49's, by name."""
    stored: dict[str, dict[str, int | float]] = structure_trail_arms()
    wide: dict[str, dict[str, int | float]] = structure_trail_arms(
        STRUCTURE_TRAIL_WIDE_BARS, STRUCTURE_TRAIL_WIDE_CUSHIONS
    )

    return {arm: fields for arm, fields in wide.items() if arm not in stored}


def insidebartrailing_structure_end_variants(root: str) -> list[Variant]:
    """Build §M49's variants under their stored names, then every arm past its ladders' ends."""
    return [
        *insidebartrailing_structure_variants(root),
        *structure_variants(root, "structure_ends", structure_trail_end_arms()),
    ]


IBT_STRUCTURE_ENDS_VARIANTS: VariantBuilders = {"InsideBarTrailing": insidebartrailing_structure_end_variants}
"""§M49's variants, and the arms its ladders left out. Each new arm's name carries a
``structure_ends=`` token that neither the stored rows nor §M49's carry --
``docs/findings/m49-structure-trail-result.md`` § "What this does not settle"."""

SIZE_FIXED = "size=fixed"
"""The control on every archetype but InsideBarTrailing, whose control is §M45's ``split=0.5``, or
``split=0.8`` for the tiers above a half."""

SIZING_SYMMETRIC = f"{SIZING_CONFLUENCE} symmetric"

LABEL_TOKENS: dict[str, str] = {
    "size_on_trend": "trend",
    "size_on_higher_timeframe": "htf",
    "size_on_vwap": "vwap",
    "size_on_regime": "regime",
    "size_on_volume": "volume",
}
"""What a label-alone arm is called: ``size=<token>``."""


def sheds_a_step(together: Variant) -> bool:
    """Return whether every base size ``together`` runs at is above its bracket's smallest position.

    Where one is not, the symmetric size is refused rather than run as add-only --
    ``docs/nt8-fidelity.md`` §M47.
    """
    quantities: list[AxisValue] = together.axes.get("order_quantity", [])
    bases: list[Params] = [replace(together.base, order_quantity=int(q)) for q in quantities] or [
        together.base
    ]

    return all(
        isinstance(base, ConfluenceSized) and base.order_quantity > base.minimum_quantity for base in bases
    )


def label_arms(arm: Arm, labels: tuple[str, ...], **held: AxisValue | bool) -> list[Variant]:
    """Return an add-only arm per kept label alone, or none where one is kept: that is the all-labels arm."""
    if len(labels) < 2:  # noqa: PLR2004 - one label alone is the all-labels arm
        return []

    return [arm(f"size={LABEL_TOKENS[label]}", **counted((label,), **held)) for label in labels]


def symmetric_arms(arm: Arm, cut: SizingCut, **held: AxisValue | bool) -> list[Variant]:
    """Return the arm counting every symmetric label, a step off per opposing one, where each base can shed.

    Refused on a cut stored before the fit read its symmetric labels, rather than counting the
    add-only ones in their place.
    """
    labels: tuple[str, ...] | None = cut.symmetric_labels
    if labels is None:
        msg: str = (
            f"the {cut.root} {cut.minutes}m sizing cut holds no symmetric labels; "
            "run tools/campaign_sizing.py fit to read them"
        )
        raise SystemExit(msg)

    if not labels:
        return []

    together: Variant = arm(SIZING_CONFLUENCE, **counted(labels, **held))
    if not sheds_a_step(together):
        logger.info("  %s: its base is already one contract per leg, so no symmetric arm", together.name)

        return []

    return [arm(SIZING_SYMMETRIC, **counted(labels, **held), size_symmetric=True)]


def confluence_arms(campaign: Variant, cut: SizingCut) -> list[Variant]:
    """Build §M47's arms over one stored variant at one root and resolution, all on its own axes.

    The control, every kept label together, each alone, and every symmetric label counted
    symmetrically where the base can shed a step --
    ``docs/findings/m47-confluence-sizing-preregistration.md``.
    """
    arm: Arm = arm_factory(campaign, cut, campaign.axes)
    control: Variant = arm(SIZE_FIXED)
    added: list[Variant] = (
        [arm(SIZING_CONFLUENCE, **counted(cut.labels)), *label_arms(arm, cut.labels)] if cut.labels else []
    )
    arms: list[Variant] = [control, *added, *symmetric_arms(arm, cut)]
    if len(arms) == 1:
        logger.warning(
            "  %s %dm: every label was dropped by the fit, so only the control", control.name, cut.minutes
        )

    return arms


def insidebartrailing_confluence_arms(campaign: Variant, cut: SizingCut) -> list[Variant]:
    """Build §M45's nine arms, then §M47's label-alone and symmetric ones, all on §M45's grid."""
    arms: list[Variant] = sizing_arms(campaign, cut)
    arm: Arm = arm_factory(campaign, cut, sizing_axes(campaign))
    held: dict[str, AxisValue | bool] = {"partial_take_profit_percentage": SIZING_ESTABLISHED_SHARE}

    return [*arms, *label_arms(arm, cut.labels, **held), *symmetric_arms(arm, cut, **held)]


def confluence_variants(
    name: str,
    arms_for: Callable[[Variant, SizingCut], list[Variant]],
) -> Callable[[str], list[Variant]]:
    """Return what re-emits one archetype's stored variants as sizing arms, at every resolution fitted."""

    def variants(root: str) -> list[Variant]:
        cuts: list[SizingCut] = [cut for cut in sizing_cuts(sizing_cuts_path(name)) if cut.root == root]

        return [
            arm
            for campaign in VARIANTS[name](root)
            for cut in cuts
            if cut.fits(campaign.name) and campaign.runs_at(cut.minutes)
            for arm in arms_for(campaign, cut)
        ]

    return variants


CONFLUENCE_SIZING_VARIANTS: VariantBuilders = {
    name: confluence_variants(
        name,
        insidebartrailing_confluence_arms if name == archetypes.INSIDEBARTRAILING.name else confluence_arms,
    )
    for name in VARIANTS
}
"""The [#295] run: every archetype's stored grid once per sizing arm. Every name carries a
``size=`` token no campaign row has, and InsideBarTrailing's reuse §M45's names, so the stored-cell
guard skips the cells §M45 already holds -- ``docs/findings/m47-confluence-sizing-preregistration.md``."""


def sizing_strata_cuts(
    consolidating_below: float,
    directional_above: float,
    thin_below: float,
    heavy_above: float,
) -> Cuts:
    """Return the regime and volume cells a sizing run's strata are cut at: one lookback, one series."""
    defaults: DeadCatParams = DeadCatParams()

    return Cuts(
        regime=(
            RegimeCut(
                defaults.regime_lookback, consolidating_below, directional_above, SIZING_LABEL_QUANTILES
            ),
        ),
        volume=(VolumeCut(defaults.volume_key, thin_below, heavy_above, tails=SIZING_LABEL_QUANTILES),),
    )


def confluence_cuts(name: str, root: str) -> dict[int, Cuts]:
    """Return, per resolution, the cut its labels read, which a sizing run's regime and volume strata take.

    Refuses a resolution whose variants carry more than one.
    """
    fitted: dict[int, set[tuple[float, float, float, float]]] = {}
    for cut in sizing_cuts(sizing_cuts_path(name)):
        if cut.root != root:
            continue

        thresholds: tuple[float, float, float, float] = (
            cut.regime_consolidating_below,
            cut.regime_directional_above,
            cut.volume_thin_below,
            cut.volume_heavy_above,
        )
        fitted.setdefault(cut.minutes, set()).add(thresholds)

    for minutes, found in fitted.items():
        if len(found) != 1:
            msg: str = f"{name} {root} {minutes}m: its variants carry {len(found)} cuts; the strata need one"
            raise SystemExit(msg)

    return {minutes: sizing_strata_cuts(*next(iter(found))) for minutes, found in fitted.items()}


SPEC_VARIANTS: VariantBuilders = {"EmaCrossover": spec_variants}
"""The [#74] re-sweep: the moving-average trail, round-number avoidance and the confluence
count, each against a control in the same pass. One archetype, because that is where the three
axes exist -- ``docs/roadmap.md`` § "The build spec's three loose ends, measured"."""

CAMPAIGN = "campaign"

VARIANT_SETS = {
    CAMPAIGN,
    CONFLUENCE_SIZING,
    EARLY_EXIT,
    EARLY_EXIT_2,
    ELASTIC_BAND_STOP,
    EMAPULLBACK_CONFIRM,
    EMAPULLBACK_TRAIL,
    ELASTIC_CHANNEL,
    ELASTIC_RECOVERY,
    ELASTIC_SHAPE,
    ELASTIC_VOLUME,
    HOLD,
    IBT_SIZING,
    IBT_SIZING_HIGH,
    IBT_STRUCTURE,
    IBT_STRUCTURE_ENDS,
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


def variants_for(which: str) -> VariantBuilders:
    """Return the variant builders one ``--variants`` name selects."""
    sets: dict[str, VariantBuilders] = {
        CONFLUENCE_SIZING: CONFLUENCE_SIZING_VARIANTS,
        EARLY_EXIT: EARLY_EXIT_VARIANTS,
        EARLY_EXIT_2: EARLY_EXIT_2_VARIANTS,
        ELASTIC_BAND_STOP: ELASTIC_BAND_STOP_VARIANTS,
        EMAPULLBACK_CONFIRM: EMAPULLBACK_CONFIRM_VARIANTS,
        EMAPULLBACK_TRAIL: EMAPULLBACK_TRAIL_VARIANTS,
        ELASTIC_CHANNEL: ELASTIC_CHANNEL_VARIANTS,
        ELASTIC_RECOVERY: ELASTIC_RECOVERY_VARIANTS,
        ELASTIC_SHAPE: ELASTIC_SHAPE_VARIANTS,
        ELASTIC_VOLUME: ELASTIC_VOLUME_VARIANTS,
        HOLD: HOLD_VARIANTS,
        IBT_SIZING: IBT_SIZING_VARIANTS,
        IBT_SIZING_HIGH: IBT_SIZING_HIGH_VARIANTS,
        IBT_STRUCTURE: IBT_STRUCTURE_VARIANTS,
        IBT_STRUCTURE_ENDS: IBT_STRUCTURE_ENDS_VARIANTS,
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
    """Build one grid per stratum over ``variant``, named by the stratum."""
    return [
        (name, sweep.Grid(axes=variant.axes | extra, base=variant.base, archetype=variant.archetype))
        for name, extra in strata(which, cuts)
    ]


def windows(bars: pd.DataFrame, *, split: bool) -> list[tuple[str, pd.DataFrame]]:
    """Return the bar ranges to run: the whole series, or a selection window and a held-out one."""
    if not split:
        return [("full", bars)]

    cut: int = math.floor(len(bars) * SELECTION_SHARE)

    return [("selection", bars.iloc[:cut]), ("holdout", bars.iloc[cut:])]


def db_path(name: str) -> paths.Path:
    """Return where one archetype's results live. Separate files, not separate tables -- see above."""
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

    return CAMPAIGN_DIR / f"{name}.duckdb"


def _merged_axes(grids: list[sweep.Grid]) -> dict[str, list[AxisValue]]:
    """Merge every value any grid tries for any axis, for the stored ``axes`` column."""
    merged: dict[str, list[AxisValue]] = {}
    for grid in grids:
        for axis, values in grid.axes.items():
            merged[axis] = sorted({*merged.get(axis, []), *values}, key=str)

    return merged


class SweptBars(NamedTuple):
    """The bars one stored sweep ran on, as its ``sweeps`` row records them."""

    bars: int
    first_bar: pd.Timestamp
    last_bar: pd.Timestamp


def swept_on(frame: pd.DataFrame) -> SweptBars:
    """Return what ``results.save_sweep`` records of the bars ``frame`` holds."""
    return SweptBars(len(frame), frame.index[0].tz_localize(None), frame.index[-1].tz_localize(None))


def stored_cells(name: str, root: str, minutes: int, window: str) -> dict[tuple[str, str], set[SweptBars]]:
    """Return every (variant, stratum) cell one archetype's database holds at one point, and its bars."""
    path: paths.Path = db_path(name)
    if results.query("SELECT 1 FROM information_schema.tables WHERE table_name = 'combos'", path).empty:
        return {}

    rows: pd.DataFrame = results.query(
        "SELECT DISTINCT c.variant, c.stratum, s.bars, s.first_bar, s.last_bar "  # noqa: S608 - every value is the campaign's own
        "FROM combos c JOIN sweeps s USING (sweep_id) "
        f"WHERE s.strategy = '{name}' AND s.root = '{root}' AND s.resolution = {int(minutes)} "
        f"AND c.\"window\" = '{window}'",
        path,
    )
    stored: dict[tuple[str, str], set[SweptBars]] = {}
    for variant, stratum, bars, first_bar, last_bar in rows.itertuples(index=False):
        swept: SweptBars = SweptBars(int(bars), pd.Timestamp(first_bar), pd.Timestamp(last_bar))
        stored.setdefault((str(variant), str(stratum)), set()).add(swept)

    return stored


def unstored(
    named: list[tuple[str, str, sweep.Grid]],
    stored: dict[tuple[str, str], set[SweptBars]],
    frame: pd.DataFrame,
) -> list[tuple[str, str, sweep.Grid]]:
    """Return the cells a run still has to sweep, refusing one already stored on other bars.

    ``tools/README.md`` § "campaign_sweep.py".
    """
    fresh: list[tuple[str, str, sweep.Grid]] = []
    for variant, stratum, grid in named:
        found: set[SweptBars] | None = stored.get((variant, stratum))
        if found is None:
            fresh.append((variant, stratum, grid))
            continue

        here: SweptBars = swept_on(frame)
        if found != {here}:
            msg: str = (
                f"{variant!r} in {stratum!r} is already stored, swept on {sorted(found)}, and this run's "
                f"bars are {here}; move the stored rows aside or run it under another name"
            )
            raise SystemExit(msg)

    return fresh


def workers_for(combinations: int, bars: int, n_jobs: int) -> int:
    """Return the joblib worker count for one sweep call of ``combinations`` over ``bars``."""
    if combinations * bars < SERIAL_BELOW_COMBINATION_BARS:
        return 1

    return n_jobs


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
    concatenated into a single ``sweeps`` row: a stratum is a parameter, not a dataset. Every
    cell runs in one sweep call, so ``n_jobs`` is chosen for the point as a whole. A cell already
    stored at the point is skipped.
    """
    archetype: Archetype = variants[0].archetype
    requested: list[tuple[str, str, sweep.Grid]] = [
        (variant.name, stratum, grid)
        for variant in variants
        for stratum, grid in grids_for(variant, which, cuts)
    ]
    named: list[tuple[str, str, sweep.Grid]] = unstored(
        requested,
        stored_cells(archetype.name, root, minutes, window),
        frame,
    )
    if len(named) < len(requested):
        logger.warning(
            "  %-4s %-9s %2dm  %d of %d cells already stored, skipped without checking their grid or code",
            root,
            window,
            minutes,
            len(requested) - len(named),
            len(requested),
        )

    if not named:
        return

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

    grids: list[sweep.Grid] = [grid for _, _, grid in named]
    started = time.perf_counter()
    swept: list[tuple[pd.DataFrame, dict[int, pd.DataFrame]]] = sweep.sweep_grids(
        data,
        grids,
        get_instrument(root),
        n_jobs=workers_for(sum(len(grid) for grid in grids), len(frame), n_jobs),
    )
    tables: list[pd.DataFrame] = []
    for (variant_name, stratum, grid), (table, _) in zip(named, swept, strict=True):
        table.insert(0, "variant", variant_name)
        table.insert(1, "stratum", stratum)
        table.insert(2, "window", window)
        # Before combo_id is renumbered below: a sizing arm is TIER1_ONLY on a reconciled archetype.
        table["tier2"] = sweep.row_tier2(table, grid)
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
            f"campaign; window={window}; strata={which}; "
            f"variants={len({variant for variant, _, _ in named})}; "
            f"cells={len(named)} of {len(requested)}; "
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
    """Return cuts with the right cells and no thresholds in them, for counting cells only."""
    if argv.variants == CONFLUENCE_SIZING:
        return sizing_strata_cuts(NAN, NAN, NAN, NAN)

    regime_cells: Calibration = (
        tuple(RegimeCut(lookback, NAN, NAN, argv.regime_quantiles) for lookback in argv.regime_lookbacks)
        if argv.regime_quantiles
        else ()
    )
    volume_cells: VolumeCalibration = (
        tuple(
            VolumeCut(key, NAN, NAN, tails=pair)
            for key in requested_volume_series(argv)
            for pair in argv.volume_quantiles
        )
        if argv.volume_quantiles
        else ()
    )

    return Cuts(regime=regime_cells, volume=volume_cells)


def planned_combinations(argv: argparse.Namespace) -> int:
    """Count how many combinations the requested run will simulate, before it starts."""
    per_window: int = 0
    cells: int = len(list(strata(argv.strata, cell_shape(argv))))
    builders = variants_for(argv.variants)
    for name in argv.strategies:
        for root in argv.roots:
            for variant in builders[name](root):
                live: int = sum(1 for minutes in argv.resolutions if variant.runs_at(minutes))
                per_window += variant.sized() * cells * live

    return per_window * (2 if argv.split else 1)


def check_confluence_request(argv: argparse.Namespace) -> None:
    """Refuse a sizing run cut anywhere but at its own fit, or under a stratum named for another cut.

    ``tools/README.md`` § "Why the grids look the way they do".
    """
    if argv.variants != CONFLUENCE_SIZING:
        return

    if argv.regime_quantiles or argv.volume_quantiles:
        msg: str = (
            f"--variants {CONFLUENCE_SIZING} cuts its regime and volume strata at the sizing fit's own "
            "thresholds; drop --regime-quantiles and --volume-quantiles"
        )
        raise SystemExit(msg)

    if "volume" in STRATUM_SETS[argv.strata]:
        msg = (
            f"--strata {argv.strata} holds the raw volume cells, which a sizing run would cut at its fit "
            f"under the raw names; use --strata {CONFLUENCE_SIZING}"
        )
        raise SystemExit(msg)


def quantile_pair(given: list[float] | None) -> tuple[float, float] | None:
    """Return the pair to fit at: ``None`` for the raw thresholds, and bare for :data:`REGIME_QUANTILES`."""
    if given is None:
        return None

    if not given:
        return REGIME_QUANTILES

    if len(given) != len(REGIME_QUANTILES):
        msg: str = f"--regime-quantiles takes a consolidating and a directional quantile, got {len(given)}"
        raise SystemExit(msg)

    return given[0], given[1]


def tail_pairs(given: list[float] | None) -> tuple[tuple[float, float], ...]:
    """Return the tail sizes to fit: empty for the raw thresholds, and bare for :data:`VOLUME_TAILS`."""
    if given is None:
        return ()

    if not given:
        return VOLUME_TAILS

    if len(given) % 2:
        msg: str = f"--volume-quantiles takes a thin and a heavy quantile per cut, got {len(given)}"
        raise SystemExit(msg)

    return tuple((given[at], given[at + 1]) for at in range(0, len(given), 2))


def named_forms(given: list[str]) -> tuple[volume.VolumeForm, ...]:
    """Return the forms a volume-form stratification runs, deduplicated into enum order."""
    wanted: set[volume.VolumeForm] = {volume.VolumeForm[name] for name in given}

    return tuple(form for form in volume.VolumeForm if form in wanted)


def check_volume_request(argv: argparse.Namespace) -> None:
    """Refuse a form or window selection that an unfitted run would silently ignore.

    Three ways a rung says nothing, all of them quiet without this --
    ``docs/findings/m32-volume-windows.md``.
    """
    ladders: dict[str, list[int]] = {
        "--volume-rolling-bars": argv.volume_rolling_bars,
        "--volume-baseline-sessions": argv.volume_baseline_sessions,
    }
    for flag, rungs in ladders.items():
        if len(rungs) > 1 and not argv.volume_quantiles:
            msg: str = (
                f"{flag} takes several windows, and a raw pair admits a different share of bars "
                "at each of them; pass --volume-quantiles so every rung is cut on its own "
                "distribution"
            )
            raise SystemExit(msg)

    if len(argv.volume_forms) < len(volume.VolumeForm) and not argv.volume_quantiles:
        msg = (
            "--volume-forms narrows a stratification whose unfitted cells are the stored "
            "campaign's own; pass --volume-quantiles, or leave every form in"
        )
        raise SystemExit(msg)

    if len(argv.volume_rolling_bars) > 1 and volume.VolumeForm.ROLLING not in argv.volume_forms:
        msg = (
            "--volume-rolling-bars is read under VolumeForm.ROLLING alone, so a ladder without "
            "ROLLING in --volume-forms collapses to one series and every rung runs identically"
        )
        raise SystemExit(msg)

    try:
        requested_volume_series(argv)
    except volume.VolumeError as refused:
        raise SystemExit(str(refused)) from None


def requested_volume_series(argv: argparse.Namespace) -> tuple[volume.VolumeKey, ...]:
    """Return every series the requested forms and window ladders name, the inert rungs dropped."""
    return volume_series(argv.volume_forms, argv.volume_rolling_bars, argv.volume_baseline_sessions)


def log_calibration(
    fitted: dict[int, Calibration],
    quantiles: tuple[float, float],
    selection_bars: int,
) -> None:
    """Report the cut every stratum below was defined by, beside the anchor it is read against."""
    logger.info("  regime thresholds fitted at q=%s on %s selection bars", quantiles, f"{selection_bars:,}")
    for minutes, calibration in fitted.items():
        for cut in calibration:
            anchor: float = regime.random_walk_ratio(cut.lookback)
            logger.info(
                "    %2dm n=%-3d consolidating %.4f (%.2fx)  directional %.4f (%.2fx)",
                minutes,
                cut.lookback,
                cut.consolidating_below,
                cut.consolidating_below / anchor,
                cut.directional_above,
                cut.directional_above / anchor,
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
    """Fit one calibration per resolution on the selection window, whether or not it is split.

    The held-out window reads the selection window's cut, exactly as :func:`fit_regime`'s does.
    """
    if not argv.volume_quantiles:
        return {}

    series: tuple[volume.VolumeKey, ...] = requested_volume_series(argv)
    selection: pd.DataFrame = bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]
    fitted: dict[int, VolumeCalibration] = {
        minutes: calibrate_volume(
            resample.resample(selection, minutes), minutes, argv.volume_quantiles, series
        )
        for minutes in argv.resolutions
    }
    log_volume_calibration(fitted, len(selection))

    return fitted


def fit_regime(bars: pd.DataFrame, argv: argparse.Namespace) -> dict[int, Calibration]:
    """Fit one calibration per resolution on the selection window, whether or not it is split.

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
    """Run the campaign sweep and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Sweep every archetype across resolution and context.")
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=8,
        help=(
            f"joblib workers for a sweep call of at least {SERIAL_BELOW_COMBINATION_BARS:,} "
            "combinations x bars; smaller ones stay in-process"
        ),
    )
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
    parser.add_argument(
        "--volume-forms",
        nargs="+",
        choices=[form.name for form in volume.VolumeForm],
        default=[form.name for form in volume.VolumeForm],
        help="which relative-volume forms the volume-form strata run",
    )
    parser.add_argument(
        "--volume-rolling-bars",
        nargs="+",
        type=int,
        default=[VOLUME_ROLLING_BARS],
        help="the ROLLING form's window, one cell per rung; a ladder needs --volume-quantiles",
    )
    parser.add_argument(
        "--volume-baseline-sessions",
        nargs="+",
        type=int,
        default=[VOLUME_BASELINE_SESSIONS],
        help="prior sessions the baseline spans, one cell per rung; a ladder needs --volume-quantiles",
    )
    args = parser.parse_args(argv[1:])
    args.strategies = args.strategies or list(variants_for(args.variants))
    args.regime_quantiles = quantile_pair(args.regime_quantiles)
    args.volume_quantiles = tail_pairs(args.volume_quantiles)
    args.volume_forms = named_forms(args.volume_forms)
    check_volume_request(args)
    # A held-out test of a stratified shortlist is a smaller sample twice over, so --split
    # defaults to the unfiltered stratum alone unless one is named.
    args.strata = args.strata or (UNFILTERED if args.split else CORE)
    check_confluence_request(args)

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
            sized: dict[int, Cuts] = confluence_cuts(name, root) if args.variants == CONFLUENCE_SIZING else {}
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
                        sized.get(
                            minutes, Cuts(regime=fitted.get(minutes, ()), volume=volumes.get(minutes, ()))
                        ),
                        n_jobs=args.n_jobs,
                    )
    logger.info("")
    logger.info("done in %.1f min", (time.perf_counter() - started) / 60.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
