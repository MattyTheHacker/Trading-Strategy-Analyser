"""The registry of strategy archetypes, and what a sweep needs to know about each.

An :class:`Archetype` is the bundle of facts that lets one sweep drive any strategy: the
parameter class, the legal axes, the series its signal reads, and how to run one combination.
Register a new archetype here rather than forking :mod:`nqbt.sweep`.

Holds no strategy logic -- signal and run functions stay in :mod:`nqbt.sim`. What each field is
for: ``docs/roadmap.md`` §M17; the gate maps' blind spots: ``nqbt/README.md`` § "archetypes.py".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from enum import StrEnum
from functools import cache
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from nqbt import compression, conditions, higher_timeframe, regime, timeofday, trend, volume
from nqbt.context import ContextSpec
from nqbt.sim import (
    bracket,
    crossover,
    elasticband,
    emapullback,
    insidebar,
    insidebartrailing,
    openingrange,
    pullback,
    runner,
    squeeze,
)
from nqbt.sim.filters import EarlyExiting, LabelSized
from nqbt.sim.types import (
    BAND_VWAP,
    EARLINESS_OFF,
    LOSING_OPTIONAL_EXITS,
    ORB_SCALE_NONE,
    ORB_STOP_ATR,
    STOP_ATR,
    BreakevenParams,
    ConfluenceSized,
    DeadCatParams,
    EarlyExitParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
    StopTighteningParams,
    active_early_exits,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import pandas as pd

    from nqbt.arrays import BoolArray
    from nqbt.trades import LegMatrix


type AxisValue = float | str
"""One value a swept parameter may take: any number, or a name."""


@dataclass(frozen=True, slots=True)
class AnyOf:
    """Toggles an axis is read under **any one** of, so only all of them together leave it unread."""

    toggles: tuple[str, ...]


type Gate = str | tuple[str, ...] | AnyOf
"""The toggle, or toggles, an axis is read under. With a tuple, any one of them can leave it
unread; with :class:`AnyOf`, any one of them can read it."""


@runtime_checkable
class Params(Protocol):
    """One combination's parameters: what the sweep requires of any ``params_cls``."""

    __dataclass_fields__: ClassVar[dict[str, Any]]  # type: ignore[explicit-any]  # dataclasses' own type

    def as_dict(self) -> dict[str, object]:
        """Return a flat mapping of every parameter, keyed by field name."""
        ...


class ArchetypeParams(Params, LabelSized, EarlyExiting, StopTighteningParams, BreakevenParams, Protocol):
    """A registered archetype's parameters: what the registry, the sizing and every exit rule read."""

    commission_per_contract: float
    slippage_ticks: float
    fill_limit_on_touch: bool


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


MA_GATE_PREFIXES = ("ema", "fast_sma", "slow_sma")
"""The three moving-average gates the ported archetypes share, as the prefix each pair of
``<gate>_period`` and ``<gate>_kind`` fields is named after.
"""


def _needs_time_of_day(values: Mapping[str, Sequence[AxisValue]]) -> bool:
    """Return whether any combination restricts its entries to some phases, or exits on leaving one."""
    filters: bool = any(int(v) != timeofday.ALL_PHASES for v in values.get("phase_filter", ()))

    return filters or any(values.get("early_exit_on_phase_change", ()))


def _reads_vwap(values: Mapping[str, Sequence[AxisValue]]) -> bool:
    """Return whether some combination sizes or filters on the close's side of the session VWAP."""
    return any(values.get("size_on_vwap", ())) or any(values.get("with_vwap", ()))


def _needs_session_clock(values: Mapping[str, Sequence[AxisValue]]) -> bool:
    """Return whether some combination sets a window before the close: no entry, early exit or late stop."""
    windows: tuple[str, ...] = (
        "no_entry_minutes_before_close",
        "early_exit_minutes_before_close",
        "late_stop_minutes_before_close",
    )

    return any(float(v) > 0 for window in windows for v in values.get(window, ()))


def _reads_label(
    values: Mapping[str, Sequence[AxisValue]],
    filter_name: str,
    everything: int,
    *readers: str,
) -> bool:
    """Return whether some combination filters on a label, or switches on anything else reading it."""
    filters: bool = any(int(v) != everything for v in values.get(filter_name, ()))

    return filters or any(any(values.get(reader, ())) for reader in readers)


def _exit_atr_periods(values: Mapping[str, Sequence[AxisValue]]) -> set[int]:
    """Return the ATR periods an exit reads: a breakeven trigger, a late stop or an early exit in ATRs."""
    periods: set[int] = set()
    if any(
        float(v) > 0
        for name in ("early_exit_atr_expansion", "early_exit_adverse_atr")
        for v in values.get(name, ())
    ):
        periods |= {int(v) for v in values.get("early_exit_atr_period", ())}

    if any(float(v) > 0 for v in values.get("breakeven_at", ())) and any(
        int(v) == bracket.BREAKEVEN_ATR for v in values.get("breakeven_unit", ())
    ):
        periods |= {int(v) for v in values.get("breakeven_atr_period", ())}

    if any(float(v) > 0 for v in values.get("late_stop_minutes_before_close", ())) and any(
        int(v) == bracket.LATE_STOP_ATR for v in values.get("late_stop_to", ())
    ):
        periods |= {int(v) for v in values.get("late_stop_atr_period", ())}

    return periods


def _regime_lookbacks(values: Mapping[str, Sequence[AxisValue]]) -> tuple[int, ...]:
    """Return the efficiency-ratio lookbacks to build: none unless some combination reads the label."""
    if not _reads_label(
        values,
        "regime_filter",
        regime.ALL_REGIMES,
        "size_on_regime",
        "early_exit_on_regime_change",
    ):
        return ()

    return tuple(sorted({int(v) for v in values.get("regime_lookback", ())}))


VOLUME_EXITS = ("early_exit_on_thin_volume", "early_exit_on_heavy_against")
"""The two volume exits: each reads the volume series, and one threshold of the two."""


def _volume_keys(values: Mapping[str, Sequence[AxisValue]]) -> tuple[volume.VolumeKey, ...]:
    """List the relative-volume series to build: none unless a combination filters, sizes or exits on them."""
    if not _reads_label(values, "volume_filter", volume.ALL_STATES, "size_on_volume", *VOLUME_EXITS):
        return ()

    return tuple(
        sorted(
            {
                volume.key(int(form), int(rolling), int(baseline))
                for form in values.get("volume_form", ())
                for rolling in values.get("volume_rolling_bars", ())
                for baseline in values.get("volume_baseline_sessions", ())
            },
        ),
    )


def _compression_keys(
    values: Mapping[str, Sequence[AxisValue]],
) -> tuple[compression.CompressionKey, ...]:
    """List the compression series to build: none unless some combination filters on them."""
    if not any(int(v) != compression.ALL_STATES for v in values.get("compression_filter", ())):
        return ()

    return tuple(
        sorted(
            {
                compression.key(int(form), int(period), int(baseline))
                for form in values.get("compression_form", ())
                for period in values.get("compression_period", ())
                for baseline in values.get("compression_baseline_bars", ())
            },
        ),
    )


def _trend_keys(values: Mapping[str, Sequence[AxisValue]]) -> tuple[trend.TrendKey, ...]:
    """List the trend labels to build: none unless some combination filters, sizes or exits on them."""
    if not _reads_label(
        values,
        "trend_filter",
        trend.ALL_TRENDS,
        "with_trend",
        "size_on_trend",
        "early_exit_on_trend",
        "early_exit_counter_trend_bars",
    ):
        return ()

    return tuple(
        sorted(
            {
                trend.key(int(fast), int(slow), int(lookback))
                for fast in values.get("trend_fast_period", ())
                for slow in values.get("trend_slow_period", ())
                for lookback in values.get("trend_slope_lookback", ())
            },
        ),
    )


def _higher_timeframe_keys(
    values: Mapping[str, Sequence[AxisValue]],
) -> tuple[higher_timeframe.HigherTimeframeKey, ...]:
    """List the coarse averages to build: none unless some combination filters, sizes or exits on a side."""
    if not _reads_label(
        values,
        "higher_timeframe_filter",
        higher_timeframe.ALL_SIDES,
        "with_higher_timeframe",
        "size_on_higher_timeframe",
        "early_exit_on_higher_timeframe",
    ):
        return ()

    return tuple(
        sorted(
            {
                higher_timeframe.key(int(minutes), int(period))
                for minutes in values.get("higher_timeframe_minutes", ())
                for period in values.get("higher_timeframe_period", ())
            },
        ),
    )


def _ma_keys(
    values: Mapping[str, Sequence[AxisValue]],
    gates: Sequence[str],
) -> tuple[conditions.MovingAverageKey, ...]:
    """Cross each gate's kind axis with its period axis: every grid some combination may read.

    A gate contributes nothing unless both of its axes are present -- ``docs/roadmap.md``
    § "Moving-average kind as a swept axis".
    """
    periods_by_kind: dict[str, set[int]] = {}
    for gate in gates:
        for kind in values.get(f"{gate}_kind", ()):
            for period in values.get(f"{gate}_period", ()):
                periods_by_kind.setdefault(str(kind), set()).add(int(period))

    return conditions.ma_keys(**periods_by_kind)


def moving_average_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return the context spec shared by every archetype built on the MA grids plus VWAP.

    ``values`` maps each parameter name to every value the sweep will try for it, so a period
    that is only swept still gets its grid built. Which series are conditional and why:
    ``docs/roadmap.md`` §M17.
    """
    return ContextSpec(
        ma_keys=_ma_keys(values, MA_GATE_PREFIXES),
        atr_periods=tuple(sorted(_exit_atr_periods(values))),
        needs_vwap=any(values.get("use_vwap", ())) or _reads_vwap(values),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
    )


def crossover_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what EmaCrossover reads: the two grids its sides name, their raw values, and an ATR.

    The ATR is built only where some combination uses the ATR stop or a breakeven trigger in
    ATRs, and the trailing average, a third grid, only where some combination trails on it --
    ``docs/roadmap.md`` §M17.
    """
    atr: set[int] = (
        {int(v) for v in values.get("atr_period", ())} if any(values.get("use_atr_stop", ())) else set()
    )
    gates: tuple[str, ...] = (
        ("fast", "slow", "trail_ma") if any(values.get("trail_ma_stop", ())) else ("fast", "slow")
    )

    return ContextSpec(
        ma_keys=_ma_keys(values, gates),
        atr_periods=tuple(sorted(atr | _exit_atr_periods(values))),
        needs_vwap=_reads_vwap(values),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
        needs_ma_values=True,
    )


def emapullback_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what EmaPullback reads: the two grids its trend names, their raw values, and no stop ATR.

    :func:`crossover_context` without the stop's ATR, so an ATR is built only for a breakeven
    trigger in ATRs. The trailing average, a third grid, is built only where some combination
    trails on it rather than on the slow average.
    """
    trails_on_third_grid: bool = any(values.get("trail_ma_stop", ())) and not all(
        values.get("trail_on_slow", (False,)),
    )
    gates: tuple[str, ...] = ("fast", "slow", "trail_ma") if trails_on_third_grid else ("fast", "slow")

    return ContextSpec(
        ma_keys=_ma_keys(values, gates),
        atr_periods=tuple(sorted(_exit_atr_periods(values))),
        needs_time_of_day=_needs_time_of_day(values),
        needs_vwap=_reads_vwap(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
        needs_ma_values=True,
    )


def elasticband_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what ElasticBand reads: whichever bands its sources name, and an ATR where a stop needs one.

    No moving-average grid, and the band multiple is not part of the key -- ``docs/roadmap.md``
    §M26. A grid that never selects a Bollinger source builds no period grid, and one that never
    selects the VWAP source builds no VWAP band. A breakeven trigger in ATRs adds its own period.
    """
    sources: set[int] = {int(v) for v in values.get("band_source", ())}
    periods: set[int] = {int(v) for v in values.get("band_period", ())} if sources != {BAND_VWAP} else set()
    atr: set[int] = (
        {int(v) for v in values.get("atr_period", ())}
        if any(int(v) == STOP_ATR for v in values.get("stop_mode", ()))
        else set()
    )

    return ContextSpec(
        band_periods=tuple(sorted(periods)),
        needs_vwap_band=BAND_VWAP in sources,
        needs_vwap=_reads_vwap(values),
        atr_periods=tuple(sorted(atr | _exit_atr_periods(values))),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
    )


def openingrange_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what OpeningRange reads: the ranges its anchors and windows name, and an ATR under one stop.

    No moving-average grid and no band. A range key is the anchor crossed with the window, and
    the resolution decides which are buildable -- :func:`nqbt.sessionrange.validate_key`. The
    trailing follow-through, like the ATR, is built only where some combination reads it. A
    breakeven trigger in ATRs adds its own period.
    """
    atr: set[int] = (
        {int(v) for v in values.get("atr_period", ())}
        if any(int(v) == ORB_STOP_ATR for v in values.get("stop_mode", ()))
        else set()
    )
    scaled: set[int] = (
        {int(v) for v in values.get("follow_through_sessions", ())}
        if any(int(v) != ORB_SCALE_NONE for v in values.get("follow_through_scaling", ()))
        else set()
    )

    return ContextSpec(
        range_keys=tuple(
            sorted(
                {
                    (int(anchor), int(window))
                    for anchor in values.get("anchor_minutes", ())
                    for window in values.get("window_minutes", ())
                },
            ),
        ),
        follow_through_sessions=tuple(sorted(scaled)),
        needs_vwap=_reads_vwap(values),
        atr_periods=tuple(sorted(atr | _exit_atr_periods(values))),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
    )


def squeeze_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what SqueezeBreakout reads: its squeeze series, that window's levels, and an ATR under one stop.

    The squeeze's own compression series and window levels are built for every combination,
    unlike the compression *filter's*, which :func:`_compression_keys` builds only where some
    combination filters on them. A bandwidth squeeze implies its band period, as the filter's does.
    A breakeven trigger in ATRs adds its own period.
    """
    squeezes: set[compression.CompressionKey] = {
        compression.key(int(form), int(period), int(baseline))
        for form in values.get("squeeze_form", ())
        for period in values.get("squeeze_period", ())
        for baseline in values.get("squeeze_baseline_bars", ())
    }
    atr: set[int] = (
        {int(v) for v in values.get("atr_period", ())}
        if any(int(v) == ORB_STOP_ATR for v in values.get("stop_mode", ()))
        else set()
    )

    return ContextSpec(
        atr_periods=tuple(sorted(atr | _exit_atr_periods(values))),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=tuple(sorted({*squeezes, *_compression_keys(values)})),
        window_range_periods=tuple(sorted({int(v) for v in values.get("squeeze_period", ())})),
        needs_vwap=_reads_vwap(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_session_clock=_needs_session_clock(values),
    )


def insidebar_context(values: Mapping[str, Sequence[AxisValue]]) -> ContextSpec:
    """Return what InsideBar reads: three moving-average grids, their raw values, an ATR and a clock.

    ``needs_ma_values`` because its three gates are strict -- ``docs/nt8-fidelity.md`` §M22. The
    session clock is built only where some combination sets a no-entry window or an early exit
    before the close, and the VWAP only where some combination sizes on it. A breakeven trigger in
    ATRs adds its own period.
    """
    return ContextSpec(
        ma_keys=_ma_keys(values, MA_GATE_PREFIXES),
        atr_periods=tuple(sorted({int(v) for v in values.get("atr_length", ())} | _exit_atr_periods(values))),
        needs_vwap=_reads_vwap(values),
        needs_time_of_day=_needs_time_of_day(values),
        regime_lookbacks=_regime_lookbacks(values),
        volume_keys=_volume_keys(values),
        compression_keys=_compression_keys(values),
        trend_keys=_trend_keys(values),
        higher_timeframe_keys=_higher_timeframe_keys(values),
        needs_ma_values=True,
        needs_session_clock=_needs_session_clock(values),
    )


INERT_AT: Mapping[str, object] = {
    "round_number_points": 0.0,
    "trail_on_slow": True,
    "regime_filter": regime.ALL_REGIMES,
    "volume_filter": volume.ALL_STATES,
    "compression_filter": compression.ALL_STATES,
    "trend_filter": trend.ALL_TRENDS,
    "higher_timeframe_filter": higher_timeframe.ALL_SIDES,
    "earliness_mode": EARLINESS_OFF,
    "quantity_per_confluence": 0,
    "early_exit_bars": 0,
    "early_exit_minutes": 0,
    "early_exit_on_trend": bracket.TREND_EXIT_OFF,
    "early_exit_counter_trend_bars": 0,
    "early_exit_stall_bars": 0,
    "early_exit_atr_expansion": 0.0,
    "early_exit_adverse_closes": 0,
    "early_exit_adverse_atr": 0.0,
    "early_exit_give_back": 0.0,
    "breakeven_at": 0.0,
    "breakeven_unit": bracket.BREAKEVEN_R,
    "age_stop_bars": 0,
    "age_stop_minutes": 0,
    "late_stop_minutes_before_close": 0,
    "late_stop_to": bracket.LATE_STOP_ENTRY,
    "structure_trail_bars": 0,
}
"""The value at which a toggle leaves its axes unread, where that is not simply ``False``.

A filter mask is off at the value that admits everything, and ``trail_on_slow`` leaves axes
unread by being on.
"""


def gate_toggles(gate: Gate) -> tuple[str, ...]:
    """Return every toggle one :data:`Gate` names, as a tuple whether it names one or several."""
    if isinstance(gate, AnyOf):
        return gate.toggles

    return (gate,) if isinstance(gate, str) else gate


def reads(params: Params, gate: Gate) -> bool:
    """Return whether one combination reads an axis gated by ``gate``, so its value can change a trade."""
    switched_on: list[bool] = [
        getattr(params, toggle) != INERT_AT.get(toggle, False) for toggle in gate_toggles(gate)
    ]

    return any(switched_on) if isinstance(gate, AnyOf) else all(switched_on)


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

COMPRESSION_GATES: Mapping[str, str] = {
    "compression_form": "compression_filter",
    "compression_period": "compression_filter",
    "compression_baseline_bars": "compression_filter",
    "compression_compressed_below": "compression_filter",
    "compression_expanded_above": "compression_filter",
}
"""Shared by every archetype: the five compression axes do nothing while the filter admits all
three states.
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

HIGHER_TIMEFRAME_GATES: Mapping[str, str] = {
    "higher_timeframe_minutes": "higher_timeframe_filter",
    "higher_timeframe_period": "higher_timeframe_filter",
}
"""Shared by every archetype: both coarse-average axes do nothing while the filter admits every
side.
"""


def _read_by_filter_or(gates: Mapping[str, str], *readers: str) -> dict[str, Gate]:
    """Return one filter's axes, re-gated so that each other reader of the same label also reads them."""
    return {axis: AnyOf((toggle, *readers)) for axis, toggle in gates.items()}


EARLY_EXIT_GATES: Mapping[str, Gate] = {
    "early_exit_below_r": AnyOf(("early_exit_bars", "early_exit_minutes")),
    "early_exit_measure": AnyOf(("early_exit_bars", "early_exit_minutes")),
    "early_exit_counter_trend_bars": "early_exit_bars",
    "early_exit_only_if_losing": AnyOf(LOSING_OPTIONAL_EXITS),
    "early_exit_atr_period": AnyOf(("early_exit_atr_expansion", "early_exit_adverse_atr")),
    "early_exit_give_back_from_r": "early_exit_give_back",
}
"""The threshold and the measure are read only by the not-working exit, in bars or in minutes, its
counter-trend age only in bars, the losing condition only by the exits it applies to, the ATR
period only by the two exits in ATRs and the arming distance only by the give-back exit --
``docs/nt8-fidelity.md``, "The conditional early exit"."""

STOP_TIGHTENING_GATES: Mapping[str, Gate] = {
    "age_stop_fraction": AnyOf(("age_stop_bars", "age_stop_minutes")),
    "age_stop_shape": AnyOf(("age_stop_bars", "age_stop_minutes")),
    "age_stop_only_if_losing": AnyOf(("age_stop_bars", "age_stop_minutes")),
    "late_stop_to": "late_stop_minutes_before_close",
    "late_stop_atr": ("late_stop_minutes_before_close", "late_stop_to"),
    "late_stop_atr_period": ("late_stop_minutes_before_close", "late_stop_to"),
}
"""The age stop's settings are read only with it on, in bars or in minutes, and the late stop's
only with its window open. What this cannot catch: the two ATR settings are read at one level
alone, and the bar extreme counts as reading them -- ``docs/nt8-fidelity.md``, "Tightening the
stop with time"."""

BREAKEVEN_GATES: Mapping[str, Gate] = {
    "breakeven_unit": "breakeven_at",
    "breakeven_on": "breakeven_at",
    "breakeven_offset_ticks": "breakeven_at",
    "breakeven_atr_period": ("breakeven_at", "breakeven_unit"),
}
"""Every breakeven setting is read only with the trigger on, and its ATR period only in ATRs --
``docs/nt8-fidelity.md``, "The breakeven stop"."""

CONTEXT_GATES: Mapping[str, Gate] = {
    **_read_by_filter_or(REGIME_GATES, "size_on_regime", "early_exit_on_regime_change"),
    **_read_by_filter_or(VOLUME_GATES, "size_on_volume", *VOLUME_EXITS),
    "volume_thin_below": AnyOf(("volume_filter", "size_on_volume", "early_exit_on_thin_volume")),
    "volume_heavy_above": AnyOf(("volume_filter", "size_on_volume", "early_exit_on_heavy_against")),
    **COMPRESSION_GATES,
    **_read_by_filter_or(
        TREND_GATES,
        "with_trend",
        "size_on_trend",
        "early_exit_on_trend",
        "early_exit_counter_trend_bars",
    ),
    **_read_by_filter_or(
        HIGHER_TIMEFRAME_GATES,
        "with_higher_timeframe",
        "size_on_higher_timeframe",
        "early_exit_on_higher_timeframe",
    ),
    "size_symmetric": "quantity_per_confluence",
    **EARLY_EXIT_GATES,
    **BREAKEVEN_GATES,
    **STOP_TIGHTENING_GATES,
}
"""Every archetype's context axes. A label's axes are read under its filter, its side-relative
filter, its ``size_on_*`` label *or* an early exit on it, and ``size_symmetric`` only beside a
confluence size -- ``docs/nt8-fidelity.md`` §M47.
"""

# A period and its kind only matter when the filter reading them is switched on.
MA_GATES: Mapping[str, Gate] = {
    "ema_period": "use_ema",
    "ema_kind": "use_ema",
    "fast_sma_period": "use_fast_sma",
    "fast_sma_kind": "use_fast_sma",
    "slow_sma_period": "use_slow_sma",
    "slow_sma_kind": "use_slow_sma",
    **CONTEXT_GATES,
}

CROSSOVER_GATES: Mapping[str, Gate] = {
    "atr_period": "use_atr_stop",
    "atr_stop_multiple": "use_atr_stop",
    "min_bracket_dollars": "use_atr_stop",
    "trail_ma_kind": "trail_ma_stop",
    "trail_ma_period": "trail_ma_stop",
    "trail_offset_ticks": "trail_ma_stop",
    "round_number_offset_ticks": "round_number_points",
    **CONTEXT_GATES,
}
"""EmaCrossover reads both averages always, so only its exclusive stop modes gate an axis.

``swing_lookback`` cannot be guarded -- ``docs/roadmap.md`` §M17 -- and ``confluence_required``
is checked at construction by :func:`nqbt.sim.types.validate_confluence` instead.
"""


EMAPULLBACK_GATES: Mapping[str, Gate] = {
    "entry_offset_ticks": "confirm_entry",
    "entry_order_lifetime_bars": "confirm_entry",
    "trail_ma_kind": ("trail_ma_stop", "trail_on_slow"),
    "trail_ma_period": ("trail_ma_stop", "trail_on_slow"),
    "trail_offset_ticks": ("trail_ma_stop", "trail_on_slow"),
    "trail_on_slow": "trail_ma_stop",
    **CONTEXT_GATES,
}
"""EmaPullback's gates: the confirmation entry, the trail and the shared context filters.

The third grid's three axes are unread with the trail off *and* with it on the slow average, so
they name both toggles. Every entry axis is read on every combination --
``docs/findings/m34-ema-pullback-spec.md``.
"""


INSIDEBAR_GATES: Mapping[str, Gate] = {
    **CONTEXT_GATES,
}
"""InsideBar reads all three averages and the ATR on every combination, so only the shared
context filters gate an axis.
"""


INSIDEBARTRAILING_GATES: Mapping[str, Gate] = {
    **INSIDEBAR_GATES,
    "early_partial_percentage": "earliness_mode",
    "early_max_extension_atr": "earliness_mode",
    "early_max_trend_bars": "earliness_mode",
    "structure_trail_cushion_atr": "structure_trail_bars",
}
"""InsideBar's map, with the earliness axes read only with a rule on and the cushion only with the
structure trail on. What this cannot catch: the extension and the trend-age cut are each read
under one mode alone -- ``docs/nt8-fidelity.md`` §M45.
"""


def _sizes_per_signal(params: Params) -> bool:
    """Return whether a combination sizes its entries per signal, which no reconciled NinjaScript does."""
    if isinstance(params, InsideBarTrailingParams) and params.earliness_mode != EARLINESS_OFF:
        return True

    return isinstance(params, ConfluenceSized) and params.quantity_per_confluence > 0


def _exits_early(params: Params) -> bool:
    """Return whether a combination switches on a conditional early exit, which no NinjaScript has."""
    return isinstance(params, EarlyExitParams) and bool(active_early_exits(params))


def _moves_to_breakeven(params: Params) -> bool:
    """Return whether a combination switches on the breakeven stop, which no NinjaScript has."""
    return isinstance(params, BreakevenParams) and params.breakeven_at > 0.0


def _tightens_with_time(params: Params) -> bool:
    """Return whether a combination switches on the age stop or the late stop, which no NinjaScript has."""
    return isinstance(params, StopTighteningParams) and (
        params.age_stop_bars > 0 or params.age_stop_minutes > 0 or params.late_stop_minutes_before_close > 0
    )


def _leaves_the_port(params: Params) -> bool:
    """Return whether a combination sizes per signal, exits early or moves its stop: all off the port."""
    return (
        _sizes_per_signal(params)
        or _exits_early(params)
        or _moves_to_breakeven(params)
        or _tightens_with_time(params)
    )


COST_FIELDS: frozenset[str] = frozenset({"commission_per_contract", "slippage_ticks"})
"""The costs, which a reconciled row may vary -- ``docs/roadmap.md`` § "Decisions taken"."""

DEADCATBOUNCE_PROPERTIES: frozenset[str] = frozenset(
    {
        "ema_period",
        "slow_sma_period",
        "fast_sma_period",
        "order_quantity",
        "use_ema",
        "use_slow_sma",
        "use_fast_sma",
        "use_vwap",
        "require_previous_green",
        "require_new_high",
        "tp_multiplier",
        "max_risk_ticks",
    },
)
"""Every ``[NinjaScriptProperty]`` in ``DeadCatBounce.cs``, by the field that mirrors it."""

PULLBACKANDGO_PROPERTIES: frozenset[str] = frozenset(
    {
        "ema_period",
        "slow_sma_period",
        "fast_sma_period",
        "order_quantity",
        "use_ema",
        "use_slow_sma",
        "use_fast_sma",
        "use_vwap",
        "require_previous_red",
        "require_new_low",
    },
)
"""Every ``[NinjaScriptProperty]`` in ``PullBackAndGo.cs``, by the field that mirrors it."""

INSIDEBAR_PROPERTIES: frozenset[str] = frozenset(
    {
        "order_quantity",
        "ema_period",
        "fast_sma_period",
        "slow_sma_period",
        "error_margin",
        "atr_length",
        "atr_multiplier",
        "tp_multiplier",
    },
)
"""Every ``[NinjaScriptProperty]`` in ``InsideBar.cs``, by the field that mirrors it."""

INSIDEBARTRAILING_PROPERTIES: frozenset[str] = (INSIDEBAR_PROPERTIES - {"tp_multiplier"}) | {
    "partial_take_profit_percentage",
    "trailing_stop_multiplier",
    "maximum_loss_per_trade",
}
"""Every ``[NinjaScriptProperty]`` in ``InsideBarTrailing.cs`` that a field mirrors."""


@cache
def _defaults(params_cls: type[Params]) -> dict[str, object]:
    """Return every field's default for one parameter class, keyed by name."""
    return {f.name: f.default for f in fields(params_cls)}


def _same(value: object, default: object) -> bool:
    """Return whether a field holds its default, counting a NaN target slot equal to the default's NaN."""
    if isinstance(value, tuple) and isinstance(default, tuple):
        return len(value) == len(default) and all(_same(v, d) for v, d in zip(value, default, strict=True))

    if isinstance(value, float) and isinstance(default, float) and math.isnan(default):
        return math.isnan(value)

    return value == default


ELASTICBAND_GATES: Mapping[str, Gate] = {
    **CONTEXT_GATES,
}
"""Only the shared context filters gate an axis here; the stop and target axes cannot be gated
-- ``nqbt/README.md`` § "archetypes.py".
"""


OPENINGRANGE_GATES: Mapping[str, Gate] = {
    **CONTEXT_GATES,
}
"""Only the shared context filters gate an axis here; the stop axes and
``follow_through_sessions`` cannot be gated -- ``nqbt/README.md`` § "archetypes.py".
"""


SQUEEZE_GATES: Mapping[str, Gate] = {
    **CONTEXT_GATES,
}
"""Only the shared context filters gate an axis here. The squeeze's own axes are read on every
combination, and the stop axes cannot be gated -- see :data:`OPENINGRANGE_GATES`.
"""


@dataclass(frozen=True, slots=True)
class Archetype:  # type: ignore[explicit-any]  # its __init__ takes the Callables below
    """How to sweep one strategy. Frozen, so a lookup cannot mutate the registry."""

    name: str
    """The registry key, and the value written to the results table's ``strategy``."""

    params_cls: type[ArchetypeParams]
    """The dataclass a combination is an instance of. Replaces ``Grid.base``'s hardcoding."""

    run: Callable[..., pd.DataFrame]  # type: ignore[explicit-any]  # the signature differs per archetype
    """Simulate one combination and return its leg-level trade log."""

    legs: Callable[..., LegMatrix]  # type: ignore[explicit-any]  # the signature differs per archetype
    """The same simulation, stopping at the raw leg matrix. Required, not optional."""

    tier2: Tier2Status
    """See :class:`Tier2Status` -- this reaches the results table, deliberately."""

    signal: Callable[..., BoolArray]  # type: ignore[explicit-any]  # the signature differs per archetype
    """Compute this archetype's per-bar entry signal from a :class:`Dataset`."""

    long_side: Callable[..., BoolArray]  # type: ignore[explicit-any]  # the signature differs per archetype
    """Return the bars one combination would enter long, which a sided sizing label is read against."""

    gated_by: Mapping[str, Gate] = field(default_factory=lambda: MA_GATES)
    """Axis -> the toggle, or toggles, that have to be on for it to change anything. Feeds
    ``dead_axes``."""

    context_for: Callable[[Mapping[str, Sequence[AxisValue]]], ContextSpec] = moving_average_context
    """Which precomputed series this archetype's signal reads."""

    not_sweepable: frozenset[str] = frozenset({"target_r_multiples"})
    """Fields that are not legal axes. Listed rather than inferred -- see #60."""

    departs_from_port: Callable[[Params], bool] | None = None
    """Whether a combination uses a rule no reconciled NinjaScript has, whatever its parameter
    class. Such a row is ``TIER1_ONLY`` whatever :attr:`tier2` says -- :meth:`tier2_for`."""

    port_properties: frozenset[str] | None = None
    """The fields mirroring a ``[NinjaScriptProperty]`` of the reconciled NinjaScript, ``None``
    without one. Any other field read away from its default leaves the port --
    :meth:`fields_off_port`."""

    def fields_off_port(self, params: Params) -> tuple[str, ...]:
        """Return the fields one combination reads away from their defaults that its NinjaScript lacks.

        Empty without :attr:`port_properties`. The costs are never in it, and a field its
        :attr:`gated_by` toggle leaves unread changes nothing.
        """
        if self.port_properties is None:
            return ()

        free: frozenset[str] = self.port_properties | COST_FIELDS

        return tuple(
            name
            for name, default in _defaults(type(params)).items()
            if name not in free
            and not _same(getattr(params, name), default)
            and (name not in self.gated_by or reads(params, self.gated_by[name]))
        )

    def tier2_for(self, params: Params) -> Tier2Status:
        """Return the status one combination's results carry: :attr:`tier2`, unless it leaves the port."""
        departs: bool = bool(self.fields_off_port(params)) or (
            self.departs_from_port is not None and self.departs_from_port(params)
        )
        if departs and self.tier2 is Tier2Status.RECONCILED:
            return Tier2Status.TIER1_ONLY

        return self.tier2

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
    long_side=runner.deadcat_long_side,
    tier2=Tier2Status.RECONCILED,
    departs_from_port=_leaves_the_port,
    port_properties=DEADCATBOUNCE_PROPERTIES,
)
"""The first C#-backed port. A row sizing per signal, or setting anything else its NinjaScript has
no property for, is ``TIER1_ONLY`` -- ``docs/roadmap.md`` § "Decisions taken"."""

PULLBACKANDGO = Archetype(
    name="PullBackAndGo",
    params_cls=PullBackAndGoParams,
    run=pullback.run_pullbackandgo,
    legs=pullback.pullbackandgo_legs,
    signal=pullback.pullback_signal,
    long_side=pullback.pullback_long_side,
    tier2=Tier2Status.RECONCILED,
    departs_from_port=_leaves_the_port,
    port_properties=PULLBACKANDGO_PROPERTIES,
)
"""DeadCatBounce's long-side mirror, and the second C#-backed port. A row leaving its NinjaScript
is ``TIER1_ONLY`` -- ``docs/roadmap.md`` § "Decisions taken"."""

EMACROSSOVER = Archetype(
    name="EmaCrossover",
    params_cls=EmaCrossoverParams,
    run=crossover.run_crossover,
    legs=crossover.crossover_legs,
    signal=crossover.crossover_signal,
    long_side=crossover.crossover_long_side,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=CROSSOVER_GATES,
    context_for=crossover_context,
)
"""The first original archetype: no NinjaScript, and TIER1_ONLY until there is one."""

EMAPULLBACK = Archetype(
    name="EmaPullback",
    params_cls=EmaPullbackParams,
    run=emapullback.run_emapullback,
    legs=emapullback.emapullback_legs,
    signal=emapullback.emapullback_signal,
    long_side=emapullback.emapullback_long_side,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=EMAPULLBACK_GATES,
    context_for=emapullback_context,
)
"""The fourth original: EmaCrossover's two averages read for the trend rather than the cross,
and the first stop placed on a level the shared loop is handed -- ``docs/nt8-fidelity.md``
§M34."""

INSIDEBAR = Archetype(
    name="InsideBar",
    params_cls=InsideBarParams,
    run=insidebar.run_insidebar,
    legs=insidebar.insidebar_legs,
    signal=insidebar.insidebar_signal,
    long_side=insidebar.insidebar_long_side,
    tier2=Tier2Status.RECONCILED,
    gated_by=INSIDEBAR_GATES,
    context_for=insidebar_context,
    departs_from_port=_leaves_the_port,
    port_properties=INSIDEBAR_PROPERTIES,
)
"""The third C#-backed port, diffed leg-for-leg against an MNQ 03-24 trade list. A row leaving
its NinjaScript is ``TIER1_ONLY`` -- ``docs/roadmap.md`` § "Decisions taken"."""

INSIDEBARTRAILING = Archetype(
    name="InsideBarTrailing",
    params_cls=InsideBarTrailingParams,
    run=insidebartrailing.run_insidebartrailing,
    legs=insidebartrailing.insidebartrailing_legs,
    signal=insidebar.insidebar_signal,
    long_side=insidebar.insidebar_long_side,
    tier2=Tier2Status.RECONCILED,
    gated_by=INSIDEBARTRAILING_GATES,
    context_for=insidebar_context,
    departs_from_port=_leaves_the_port,
    port_properties=INSIDEBARTRAILING_PROPERTIES,
)
"""The fourth C#-backed port: InsideBar's entry with split-lot exits, diffed leg-for-leg against
an MNQ 03-24 trade list -- ``docs/nt8-fidelity.md`` §M23. A row leaving its NinjaScript is
``TIER1_ONLY`` -- ``docs/roadmap.md`` § "Decisions taken"."""

ELASTICBAND = Archetype(
    name="ElasticBand",
    params_cls=ElasticBandParams,
    run=elasticband.run_elasticband,
    legs=elasticband.elasticband_legs,
    signal=elasticband.elasticband_signal,
    long_side=elasticband.elasticband_long_side,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=ELASTICBAND_GATES,
    context_for=elasticband_context,
    not_sweepable=frozenset({"target_r_multiples", "target_stretch_levels"}),
)
"""The second original and the first mean-reversion archetype: no NinjaScript, and TIER1_ONLY
until there is one -- ``docs/roadmap.md`` §M26."""

OPENINGRANGE = Archetype(
    name="OpeningRange",
    params_cls=OpeningRangeParams,
    run=openingrange.run_openingrange,
    legs=openingrange.openingrange_legs,
    signal=openingrange.openingrange_signal,
    long_side=openingrange.openingrange_long_side,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=OPENINGRANGE_GATES,
    context_for=openingrange_context,
    not_sweepable=frozenset({"target_r_multiples", "target_width_multiples"}),
)
"""The third original, whose trigger is a level rather than an event: no NinjaScript, and
TIER1_ONLY until there is one -- ``docs/roadmap.md`` §M28."""

SQUEEZEBREAKOUT = Archetype(
    name="SqueezeBreakout",
    params_cls=SqueezeBreakoutParams,
    run=squeeze.run_squeeze,
    legs=squeeze.squeeze_legs,
    signal=squeeze.squeeze_signal,
    long_side=squeeze.squeeze_long_side,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=SQUEEZE_GATES,
    context_for=squeeze_context,
    not_sweepable=frozenset({"target_r_multiples", "target_width_multiples"}),
)
"""The fifth original: OpeningRange's resting breakout with the level taken from a compressed
rolling window -- ``docs/findings/m19-2-squeeze-breakout-spec.md``."""

_REGISTRY: dict[str, Archetype] = {
    a.name: a
    for a in (
        DEADCATBOUNCE,
        ELASTICBAND,
        EMACROSSOVER,
        EMAPULLBACK,
        INSIDEBAR,
        INSIDEBARTRAILING,
        OPENINGRANGE,
        PULLBACKANDGO,
        SQUEEZEBREAKOUT,
    )
}

DEFAULT = DEADCATBOUNCE
"""What a ``Grid`` assumes when nothing says otherwise. Changing it reinterprets every stored
result -- ``docs/roadmap.md`` §M17.
"""


def register(archetype: Archetype) -> Archetype:
    """Add an archetype, refusing to shadow one that already exists."""
    if archetype.name in _REGISTRY:
        msg: str = f"archetype {archetype.name!r} is already registered"
        raise ArchetypeError(msg)

    _REGISTRY[archetype.name] = archetype

    return archetype


def get(name: str) -> Archetype:
    """Return the archetype registered under ``name``, or raise an error naming the ones that are."""
    if name not in _REGISTRY:
        msg: str = f"unknown archetype {name!r}; known: {sorted(_REGISTRY)}"
        raise ArchetypeError(msg)

    return _REGISTRY[name]


def names() -> list[str]:
    """Return every registered archetype name, sorted."""
    return sorted(_REGISTRY)


def all_archetypes() -> list[Archetype]:
    """Return every registered archetype, in name order."""
    return [_REGISTRY[n] for n in names()]


def for_params(params: Params) -> Archetype:
    """Return the archetype whose ``params_cls`` is exactly ``type(params)``.

    Ambiguity raises rather than picking one.
    """
    matches: list[Archetype] = [a for a in all_archetypes() if a.params_cls is type(params)]
    if not matches:
        msg: str = (
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
