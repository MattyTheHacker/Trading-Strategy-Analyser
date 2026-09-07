"""The market-context filters every archetype's signal ends with.

Session phase, market regime, relative volume, how compressed the range is, the compact trend
label and the side of a higher-timeframe average are properties of the bars rather than of a
strategy, so every archetype ANDs exactly the same six gates on after its own conditions. One
conjunction here rather than one per signal function.

**Each gate is skipped entirely at its everything value, and that is not an optimisation.** An
out-of-session stray, an efficiency-ratio warm-up bar, a session with no volume baseline yet, a
bar with no trailing window to rank against, a bar whose slope cannot be measured and a bar no
coarse bar has closed before each pass *no* mask, so ANDing at the default would quietly drop
them -- ``docs/roadmap.md`` §M10.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np

from nqbt import compression, conditions, higher_timeframe, regime, timeofday, trend, volume
from nqbt.sim.types import REQUIRE_ALL

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray
    from nqbt.context import Dataset

__all__ = [
    "ConfluenceFiltered",
    "ContextFiltered",
    "apply_confluence_filters",
    "apply_context_filters",
    "context_gates",
]


class ContextFiltered(Protocol):
    """The parameters :func:`apply_context_filters` reads, shared by every archetype.

    Structural rather than a union of the concrete classes, so a new archetype gets the six
    filters by declaring the fields.
    """

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

    Separate from :class:`ContextFiltered` because declaring the field is what opts an
    archetype into the confluence pattern; the six ported ones keep the plain conjunction.
    """

    confluence_required: int


def context_gates(data: Dataset, params: ContextFiltered) -> list[BoolArray]:
    """The masks the six filters contribute, skipping every gate at its everything value.

    One list rather than a conjunction, so a caller can AND them or count them. **A gate at
    its everything value contributes nothing at all** -- it is absent from this list rather
    than present as an all-true row, because a warm-up bar passes *no* mask and counting one
    would make the two readings disagree on exactly the bars the skip exists for.
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

    At :data:`REQUIRE_ALL` this is :func:`apply_context_filters` exactly, which is what keeps
    the pattern off every archetype that has not asked for it. The count is over the *active*
    gates -- ``docs/roadmap.md`` § "The build spec's three loose ends".
    """
    if params.confluence_required == REQUIRE_ALL:
        return apply_context_filters(signal, data, params)

    gates: list[BoolArray] = context_gates(data, params)

    return signal & (conditions.count_true(np.stack(gates)) >= params.confluence_required)
