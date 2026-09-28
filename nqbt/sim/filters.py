"""The market-context filters every archetype's signal ends with.

Session phase, market regime, relative volume, compression, the compact trend label and the
side of a higher-timeframe average, ANDed onto every archetype's own conditions. A gate at its
everything value is skipped entirely -- ``nqbt/README.md`` § "sim/filters.py".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Protocol

import numpy as np

from nqbt import compression, conditions, higher_timeframe, regime, timeofday, trend, volume
from nqbt.sim import bracket
from nqbt.sim.types import REQUIRE_ALL, ConfluenceSized, SizingThesis, confluence_range

if TYPE_CHECKING:
    from collections.abc import Mapping

    from nqbt.arrays import BoolArray, IntArray
    from nqbt.context import Dataset

__all__ = [
    "ConfluenceFiltered",
    "ContextFiltered",
    "LabelSides",
    "LabelSized",
    "apply_confluence_filters",
    "apply_context_filters",
    "confluence_counts",
    "confluence_sizing",
    "context_gates",
    "favourable_labels",
    "label_sides",
]


class ContextFiltered(Protocol):
    """The parameters :func:`apply_context_filters` reads; declaring them gives an archetype all six."""

    phase_filter: int
    regime_filter: int
    regime_lookback: int
    regime_consolidating_below: float
    regime_directional_above: float
    volume_filter: int
    volume_thin_below: float
    volume_heavy_above: float
    compression_filter: int
    compression_compressed_below: float
    compression_expanded_above: float
    trend_filter: int
    trend_min_agreement: int
    higher_timeframe_filter: int

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which relative-volume series this combination reads."""
        ...

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which compression series this combination reads."""
        ...

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which trend label this combination reads."""
        ...

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which higher-timeframe average this combination reads."""
        ...


class ConfluenceFiltered(ContextFiltered, Protocol):
    """A :class:`ContextFiltered` that also says how many of its gates have to agree.

    Declaring the field is what opts an archetype into the confluence pattern.
    """

    confluence_required: int


class LabelSized(ContextFiltered, ConfluenceSized, Protocol):
    """A :class:`ContextFiltered` that also says which labels a confluence size counts, and how.

    Read for sizing, never for the signal, so a label counted here narrows no entry.
    """

    @property
    def sizing_thesis(self) -> SizingThesis:
        """Which regime and volume state favour this archetype's entry."""
        ...

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """The fixed split, which is every entry's while the confluence size is off."""
        ...

    @property
    def size_table(self) -> tuple[tuple[int, ...], ...]:
        """Every per-leg split a signal can take, one row per confluence count."""
        ...


def context_gates(data: Dataset, params: ContextFiltered) -> list[BoolArray]:
    """Return the masks the six filters contribute, skipping every gate at its everything value.

    One list rather than a conjunction, so a caller can AND them or count them. A gate at its
    everything value is absent from the list rather than present as an all-true row.
    """
    gates: list[BoolArray] = []
    if params.phase_filter != timeofday.ALL_PHASES:
        gates.append(data.phase_gate(params.phase_filter))

    if params.regime_filter != regime.ALL_REGIMES:
        gates.append(
            data.regime_gate(
                params.regime_lookback,
                params.regime_filter,
                params.regime_consolidating_below,
                params.regime_directional_above,
            ),
        )

    if params.volume_filter != volume.ALL_STATES:
        gates.append(
            data.volume_gate(
                params.volume_key,
                params.volume_filter,
                params.volume_thin_below,
                params.volume_heavy_above,
            ),
        )

    if params.compression_filter != compression.ALL_STATES:
        gates.append(
            data.compression_gate(
                params.compression_key,
                params.compression_filter,
                params.compression_compressed_below,
                params.compression_expanded_above,
            ),
        )

    if params.trend_filter != trend.ALL_TRENDS:
        gates.append(data.trend_gate(params.trend_key, params.trend_filter, params.trend_min_agreement))

    if params.higher_timeframe_filter != higher_timeframe.ALL_SIDES:
        gates.append(
            data.higher_timeframe_gate(params.higher_timeframe_key, params.higher_timeframe_filter),
        )

    return gates


def apply_context_filters(signal: BoolArray, data: Dataset, params: ContextFiltered) -> BoolArray:
    """Narrow an archetype's own signal to the market context its parameters admit."""
    for gate in context_gates(data, params):
        signal &= gate

    return signal


def apply_confluence_filters(signal: BoolArray, data: Dataset, params: ConfluenceFiltered) -> BoolArray:
    """Narrow a signal to bars where at least ``confluence_required`` of the gates agree.

    At :data:`REQUIRE_ALL` this is :func:`apply_context_filters` exactly. The count is over the
    *active* gates -- ``docs/roadmap.md`` § "The build spec's three loose ends".
    """
    if params.confluence_required == REQUIRE_ALL:
        return apply_context_filters(signal, data, params)

    gates: list[BoolArray] = context_gates(data, params)

    return signal & (conditions.count_true(np.stack(gates)) >= params.confluence_required)


class LabelSides(NamedTuple):
    """Where one sizing label favours each bar's side, and where it opposes it."""

    favours: BoolArray
    opposes: BoolArray


OPPOSITE_REGIME: Mapping[regime.Regime, regime.Regime] = {
    regime.Regime.DIRECTIONAL: regime.Regime.CONSOLIDATING,
    regime.Regime.CONSOLIDATING: regime.Regime.DIRECTIONAL,
}
OPPOSITE_VOLUME: Mapping[volume.VolumeState, volume.VolumeState] = {
    volume.VolumeState.HEAVY: volume.VolumeState.THIN,
    volume.VolumeState.THIN: volume.VolumeState.HEAVY,
}
"""The extreme that opposes a thesis's favoured one. The middle state is neutral."""


def _pointing(long_side: BoolArray, up: BoolArray, down: BoolArray) -> LabelSides:
    """Return a label that points one way: favouring the side it points to, opposing the other."""
    return LabelSides(np.where(long_side, up, down), np.where(long_side, down, up))


def _trend_sides(data: Dataset, params: LabelSized, long_side: BoolArray) -> LabelSides:
    def pointing(label: trend.Trend) -> BoolArray:
        return data.trend_gate(params.trend_key, trend.trends_mask([label]), params.trend_min_agreement)

    return _pointing(long_side, pointing(trend.Trend.UP), pointing(trend.Trend.DOWN))


def _higher_timeframe_sides(data: Dataset, params: LabelSized, long_side: BoolArray) -> LabelSides:
    def on(side: higher_timeframe.Side) -> BoolArray:
        return data.higher_timeframe_gate(params.higher_timeframe_key, higher_timeframe.sides_mask([side]))

    return _pointing(long_side, on(higher_timeframe.Side.ABOVE), on(higher_timeframe.Side.BELOW))


def _regime_sides(data: Dataset, params: LabelSized) -> LabelSides:
    def labelled(state: regime.Regime) -> BoolArray:
        return data.regime_gate(
            params.regime_lookback,
            regime.regimes_mask([state]),
            params.regime_consolidating_below,
            params.regime_directional_above,
        )

    favoured: regime.Regime = params.sizing_thesis.regime

    return LabelSides(labelled(favoured), labelled(OPPOSITE_REGIME[favoured]))


def _volume_sides(data: Dataset, params: LabelSized) -> LabelSides:
    def labelled(state: volume.VolumeState) -> BoolArray:
        return data.volume_gate(
            params.volume_key,
            volume.states_mask([state]),
            params.volume_thin_below,
            params.volume_heavy_above,
        )

    favoured: volume.VolumeState = params.sizing_thesis.volume

    return LabelSides(labelled(favoured), labelled(OPPOSITE_VOLUME[favoured]))


def label_sides(data: Dataset, params: LabelSized, long_side: BoolArray) -> list[LabelSides]:
    """One entry per ``size_on_*`` label switched on, in :data:`SIZING_LABELS` order.

    The trend, the higher-timeframe side and the VWAP side favour the trade on the side they
    point to and oppose the other; regime and volume favour both sides alike, in the state
    ``sizing_thesis`` names. A bar a label cannot classify passes no mask, so it neither favours
    nor opposes -- ``docs/nt8-fidelity.md`` §M47.
    """
    sides: list[LabelSides] = []
    if params.size_on_trend:
        sides.append(_trend_sides(data, params, long_side))

    if params.size_on_higher_timeframe:
        sides.append(_higher_timeframe_sides(data, params, long_side))

    if params.size_on_vwap:
        sides.append(_pointing(long_side, data.vwap_gate(above=True), data.vwap_gate(above=False)))

    if params.size_on_regime:
        sides.append(_regime_sides(data, params))

    if params.size_on_volume:
        sides.append(_volume_sides(data, params))

    return sides


def favourable_labels(data: Dataset, params: LabelSized, long_side: BoolArray) -> list[BoolArray]:
    """One row per ``size_on_*`` label switched on: whether it favours each bar's side."""
    return [label.favours for label in label_sides(data, params, long_side)]


def confluence_counts(data: Dataset, params: LabelSized, long_side: BoolArray) -> IntArray:
    """Each bar's count for its side: the labels favouring it, less the opposing ones if symmetric."""
    sides: list[LabelSides] = label_sides(data, params, long_side)
    if not sides:
        return np.zeros(len(data), dtype=np.int64)

    counts: IntArray = conditions.count_true(np.stack([label.favours for label in sides]))
    if params.size_symmetric:
        counts = counts - conditions.count_true(np.stack([label.opposes for label in sides]))

    return counts


def confluence_sizing(data: Dataset, params: LabelSized, long_side: BoolArray) -> bracket.Sizing:
    """Every per-leg split this combination can take, and the row each bar takes for its side.

    With the confluence size off it is the one fixed split on every bar, which is each
    NinjaScript as ported.
    """
    if params.quantity_per_confluence == 0:
        return bracket.fixed_sizing(params.leg_quantities, len(data))

    table: IntArray = np.asarray(params.size_table, dtype=np.int64)
    rows: IntArray = confluence_counts(data, params, long_side) - confluence_range(params).start

    return bracket.Sizing(table, rows)
