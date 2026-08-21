"""The registry of strategy archetypes, and what a sweep needs to know about each.

An :class:`Archetype` is the bundle of facts that lets one sweep drive any strategy: the
parameter class, the legal axes, the series its signal reads, and how to run one combination.
Register a new archetype here rather than forking :mod:`nqbt.sweep`.

Holds no strategy logic -- signal and run functions stay in :mod:`nqbt.sim`. What each field is
for: ``docs/roadmap.md`` §M17.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from nqbt import regime, timeofday, trend, volume
from nqbt.context import ContextSpec
from nqbt.sim import crossover, pullback, runner
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import numpy as np
    import pandas as pd

    from nqbt.trades import LegMatrix


@runtime_checkable
class Params(Protocol):
    """One combination's parameters: what the sweep requires of any ``params_cls``.

    Structural rather than a union of the concrete classes, because the point of the registry
    is that :mod:`nqbt.sweep` does not name them.
    """

    __dataclass_fields__: ClassVar[dict[str, Any]]  # type: ignore[explicit-any]

    def as_dict(self) -> dict: ...


class ArchetypeError(KeyError):
    """Raised for an unknown or ambiguous archetype."""


class Tier2Status(StrEnum):
    """How much NinjaTrader evidence an archetype's results carry.

    Reaches the results table, deliberately -- ``docs/roadmap.md`` § "An original archetype has
    no C# to lose to".
    """

    RECONCILED = "reconciled"
    """Diffed leg-for-leg against a real NT8 Strategy Analyzer Trades export."""

    TIER1_ONLY = "tier-1-only"
    """Ported from C#, or original, but never checked against a trade list."""

    NOT_CHECKED = "not-checked"
    """No reconciliation attempted and none planned yet."""


def _needs_time_of_day(values: Mapping[str, Sequence]) -> bool:
    """Whether any combination actually restricts its entries to some session phases."""
    return any(int(v) != timeofday.ALL_PHASES for v in values.get("phase_filter", ()))


def _regime_lookbacks(values: Mapping[str, Sequence]) -> tuple[int, ...]:
    """The efficiency-ratio lookbacks to build: none unless some combination filters on them.

    The grid holds float64 rather than a boolean gate, so an unasked-for lookback is the most
    expensive thing this function can add -- ``docs/roadmap.md`` §M10.1.
    """
    if not any(int(v) != regime.ALL_REGIMES for v in values.get("regime_filter", ())):
        return ()
    return tuple(sorted({int(v) for v in values.get("regime_lookback", ())}))


def _volume_keys(values: Mapping[str, Sequence]) -> tuple[volume.VolumeKey, ...]:
    """List the relative-volume series to build: none unless some combination filters on them.

    Sixteen bytes per bar per series, plus the baseline pass -- ``docs/roadmap.md`` §M10.2.
    """
    if not any(int(v) != volume.ALL_STATES for v in values.get("volume_filter", ())):
        return ()
    return tuple(
        sorted(
            {
                volume.key(form, rolling, baseline)
                for form in values.get("volume_form", ())
                for rolling in values.get("volume_rolling_bars", ())
                for baseline in values.get("volume_baseline_sessions", ())
            },
        ),
    )


def _trend_keys(values: Mapping[str, Sequence]) -> tuple[trend.TrendKey, ...]:
    """List the trend labels to build: none unless some combination filters on them.

    Eleven bytes per bar per label, and the averages behind them never reach the dataset --
    ``docs/roadmap.md`` §M10.3.
    """
    if not any(int(v) != trend.ALL_TRENDS for v in values.get("trend_filter", ())):
        return ()
    return tuple(
        sorted(
            {
                trend.key(fast, slow, lookback)
                for fast in values.get("trend_fast_period", ())
                for slow in values.get("trend_slow_period", ())
                for lookback in values.get("trend_slope_lookback", ())
            },
        ),
    )


def moving_average_context(values: Mapping[str, Sequence]) -> ContextSpec:
    """The context spec shared by every archetype built on the MA grids plus VWAP.

    ``values`` maps each parameter name to every value the sweep will try for it, so a period
    that is only swept still gets its grid built. Which series are conditional and why:
    ``docs/roadmap.md`` §M17.
    """
    ema = {int(v) for v in values.get("ema_period", ())}
    sma = {int(v) for v in values.get("fast_sma_period", ())}
    sma |= {int(v) for v in values.get("slow_sma_period", ())}
    return ContextSpec(
        ema_periods=tuple(sorted(ema)),
        sma_periods=tuple(sorted(sma)),
        needs_vwap=any(values.get("use_vwap", ())),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        trend_keys=_trend_keys(values),
    )


def crossover_context(values: Mapping[str, Sequence]) -> ContextSpec:
    """What EmaCrossover reads: two EMA grids, their raw values, and an ATR.

    ``needs_ma_values`` costs 8x the memory of a boolean gate and the ATR is conditional --
    ``docs/roadmap.md`` §M17.
    """
    fast = {int(v) for v in values.get("fast_period", ())}
    slow = {int(v) for v in values.get("slow_period", ())}
    atr = {int(v) for v in values.get("atr_period", ())} if any(values.get("use_atr_stop", ())) else set()
    return ContextSpec(
        ema_periods=tuple(sorted(fast | slow)),
        atr_periods=tuple(sorted(atr)),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        trend_keys=_trend_keys(values),
        needs_ma_values=True,
    )


INERT_AT: Mapping[str, object] = {
    "regime_filter": regime.ALL_REGIMES,
    "volume_filter": volume.ALL_STATES,
    "trend_filter": trend.ALL_TRENDS,
}
"""What a toggle's off value is, where it is not simply ``False``.

A filter mask is off at the value that admits everything, so ``dead_axes`` has to compare
against that rather than test truthiness -- ``ALL_REGIMES`` is 7 and would read as on.
"""

REGIME_GATES: Mapping[str, str] = {
    "regime_lookback": "regime_filter",
    "regime_consolidating_below": "regime_filter",
    "regime_directional_above": "regime_filter",
}
"""Shared by every archetype: the three regime axes do nothing while the filter admits all
three regimes.
"""

VOLUME_GATES: Mapping[str, str] = {
    "volume_form": "volume_filter",
    "volume_rolling_bars": "volume_filter",
    "volume_baseline_sessions": "volume_filter",
    "volume_thin_below": "volume_filter",
    "volume_heavy_above": "volume_filter",
}
"""Shared by every archetype: the five volume axes do nothing while the filter admits all
three states. What this cannot catch: ``docs/roadmap.md`` §M10.2.
"""

TREND_GATES: Mapping[str, str] = {
    "trend_fast_period": "trend_filter",
    "trend_slow_period": "trend_filter",
    "trend_slope_lookback": "trend_filter",
    "trend_min_agreement": "trend_filter",
}
"""Shared by every archetype: the four trend axes do nothing while the filter admits all three
trends.
"""

# A period only matters when its filter is switched on.
MA_GATES: Mapping[str, str] = {
    "ema_period": "use_ema",
    "fast_sma_period": "use_fast_sma",
    "slow_sma_period": "use_slow_sma",
    **REGIME_GATES,
    **VOLUME_GATES,
    **TREND_GATES,
}

CROSSOVER_GATES: Mapping[str, str] = {
    "atr_period": "use_atr_stop",
    "atr_stop_multiple": "use_atr_stop",
    **REGIME_GATES,
    **VOLUME_GATES,
    **TREND_GATES,
}
"""EmaCrossover reads both averages always, so only its exclusive stop modes gate an axis.

Why ``swing_lookback`` cannot be guarded the same way: ``docs/roadmap.md`` §M17.
"""


@dataclass(frozen=True, slots=True)
class Archetype:
    """How to sweep one strategy. Frozen, so a lookup cannot mutate the registry."""

    name: str
    """The registry key, and the value written to the results table's ``strategy``."""

    params_cls: type
    """The dataclass a combination is an instance of. Replaces ``Grid.base``'s hardcoding."""

    run: Callable[..., pd.DataFrame]
    """Simulate one combination and return its leg-level trade log."""

    legs: Callable[..., LegMatrix]
    """The same simulation, stopping at the raw leg matrix. Required, not optional."""

    tier2: Tier2Status
    """See :class:`Tier2Status` -- this reaches the results table, deliberately."""

    signal: Callable[..., np.ndarray]
    """Compute this archetype's per-bar entry signal from a :class:`Dataset`."""

    gated_by: Mapping[str, str] = field(default_factory=lambda: MA_GATES)
    """Axis -> the toggle that has to be on for it to change anything. Feeds ``dead_axes``."""

    context_for: Callable[[Mapping[str, Sequence]], ContextSpec] = moving_average_context
    """Which precomputed series this archetype's signal reads."""

    not_sweepable: frozenset[str] = frozenset({"target_r_multiples"})
    """Fields that are not legal axes. Listed rather than inferred -- see #60."""

    @property
    def sweepable(self) -> frozenset[str]:
        """Every field of :attr:`params_cls` that may be given a list of values.

        Read from :func:`dataclasses.fields`, never ``__slots__``, which omits inherited
        fields -- see #60.
        """
        return frozenset(f.name for f in fields(self.params_cls)) - self.not_sweepable


DEADCATBOUNCE = Archetype(
    name="DeadCatBounce",
    params_cls=DeadCatParams,
    run=runner.run_deadcat,
    legs=runner.deadcat_legs,
    signal=runner.deadcat_signal,
    tier2=Tier2Status.RECONCILED,
)

PULLBACKANDGO = Archetype(
    name="PullBackAndGo",
    params_cls=PullBackAndGoParams,
    run=pullback.run_pullbackandgo,
    legs=pullback.pullbackandgo_legs,
    signal=pullback.pullback_signal,
    tier2=Tier2Status.RECONCILED,
)

EMACROSSOVER = Archetype(
    name="EmaCrossover",
    params_cls=EmaCrossoverParams,
    run=crossover.run_crossover,
    legs=crossover.crossover_legs,
    signal=crossover.crossover_signal,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=CROSSOVER_GATES,
    context_for=crossover_context,
)
"""The first original archetype: no NinjaScript, and TIER1_ONLY until there is one."""

_REGISTRY: dict[str, Archetype] = {a.name: a for a in (DEADCATBOUNCE, EMACROSSOVER, PULLBACKANDGO)}

DEFAULT = DEADCATBOUNCE
"""What a ``Grid`` assumes when nothing says otherwise. Changing it reinterprets every stored
result -- ``docs/roadmap.md`` §M17.
"""


def register(archetype: Archetype) -> Archetype:
    """Add an archetype, refusing to shadow one that already exists."""
    if archetype.name in _REGISTRY:
        msg = f"archetype {archetype.name!r} is already registered"
        raise ArchetypeError(msg)
    _REGISTRY[archetype.name] = archetype
    return archetype


def get(name: str) -> Archetype:
    if name not in _REGISTRY:
        msg = f"unknown archetype {name!r}; known: {sorted(_REGISTRY)}"
        raise ArchetypeError(msg)
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


def all_archetypes() -> list[Archetype]:
    return [_REGISTRY[n] for n in names()]


def for_params(params: Params) -> Archetype:
    """The archetype whose ``params_cls`` is exactly ``type(params)``.

    Ambiguity raises rather than picking one.
    """
    matches = [a for a in all_archetypes() if a.params_cls is type(params)]
    if not matches:
        msg = (
            f"no registered archetype takes {type(params).__name__}; "
            f"pass archetype= explicitly. Known: {names()}"
        )
        raise ArchetypeError(
            msg,
        )
    if len(matches) > 1:
        msg = f"{type(params).__name__} is shared by {[a.name for a in matches]}; pass archetype= explicitly"
        raise ArchetypeError(
            msg,
        )
    return matches[0]
