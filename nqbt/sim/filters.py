"""The market-context filters every archetype's signal ends with.

Session phase, market regime, relative volume, the compact trend label and the side of a
higher-timeframe average are properties of the bars rather than of a strategy, so all three
archetypes AND exactly the same five gates on after their own conditions. One conjunction here
rather than one per signal function.

**Each gate is skipped entirely at its everything value, and that is not an optimisation.** An
out-of-session stray, an efficiency-ratio warm-up bar, a session with no volume baseline yet, a
bar whose slope cannot be measured and a bar no coarse bar has closed before each pass *no*
mask, so ANDing at the default would quietly drop them -- ``docs/roadmap.md`` §M10.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from nqbt import higher_timeframe, regime, timeofday, trend, volume

if TYPE_CHECKING:
    from collections.abc import Sequence

    from nqbt.arrays import BoolArray
    from nqbt.context import Dataset


__all__: Sequence[str] = ["ContextFiltered", "apply_context_filters"]


class ContextFiltered(Protocol):
    """The parameters :func:`apply_context_filters` reads, shared by every archetype.

    Structural rather than a union of the concrete classes, so a new archetype gets the five
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
    trend_filter: int
    trend_min_agreement: int
    higher_timeframe_filter: int

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which relative-volume series this combination reads."""
        ...

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which trend label this combination reads."""
        ...

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which higher-timeframe average this combination reads."""
        ...


def apply_context_filters(signal: BoolArray, data: Dataset, params: ContextFiltered) -> BoolArray:
    """Narrow an archetype's own signal to the market context its parameters admit."""
    if params.phase_filter != timeofday.ALL_PHASES:
        signal &= data.phase_gate(params.phase_filter)

    if params.regime_filter != regime.ALL_REGIMES:
        signal &= data.regime_gate(
            params.regime_lookback,
            params.regime_filter,
            params.regime_consolidating_below,
            params.regime_directional_above,
        )

    if params.volume_filter != volume.ALL_STATES:
        signal &= data.volume_gate(
            params.volume_key,
            params.volume_filter,
            params.volume_thin_below,
            params.volume_heavy_above,
        )

    if params.trend_filter != trend.ALL_TRENDS:
        signal &= data.trend_gate(params.trend_key, params.trend_filter, params.trend_min_agreement)

    if params.higher_timeframe_filter != higher_timeframe.ALL_SIDES:
        signal &= data.higher_timeframe_gate(params.higher_timeframe_key, params.higher_timeframe_filter)

    return signal
