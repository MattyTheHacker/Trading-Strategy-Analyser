"""Market context: bars plus every derived condition, computed once and shared.

The half of a backtest that has nothing to do with a strategy. One :class:`Dataset` serves
every parameter combination of a sweep and every archetype, so everything expensive lives here
and a combination costs only a boolean AND plus one pass of the simulation.

**What gets computed is declared, not assumed**: a :class:`ContextSpec` says which series an
archetype's signal will read and :func:`prepare` builds exactly that -- ``docs/roadmap.md``
§M17.

Nothing here knows what a trade is; :mod:`nqbt.trades` owns that, and the two never import
each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, TypedDict

import numpy as np
import pandas as pd

from nqbt import conditions, indicators, regime, sessions, timeofday, trend, volume

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IndexArray, LabelArray
    from nqbt.conditions import MovingAverageGrid


class ContextError(KeyError):
    """Raised when a strategy reads a series :func:`prepare` was not asked to build."""


@dataclass(frozen=True, slots=True)
class ContextSpec:
    """Everything a strategy's signal will read out of a :class:`Dataset`.

    Declared up front rather than discovered mid-loop, because the grids refuse a period they
    were not built for rather than returning a wrong row. ``__or__`` is what lets several
    archetypes at one axis point share a single dataset.

    Lives here rather than beside the archetype registry because it describes a
    :class:`Dataset`, and ``context.py`` must not import from :mod:`nqbt.sim`.
    """

    ema_periods: tuple[int, ...] = ()
    sma_periods: tuple[int, ...] = ()
    atr_periods: tuple[int, ...] = ()
    needs_vwap: bool = False
    needs_time_of_day: bool = False
    """Build the session-phase and bar-of-session labels (:mod:`nqbt.timeofday`)."""

    regime_lookbacks: tuple[int, ...] = ()
    """Efficiency-ratio lookbacks to build (:mod:`nqbt.regime`). Empty builds nothing."""

    volume_keys: tuple[volume.VolumeKey, ...] = ()
    """Relative-volume series to build (:mod:`nqbt.volume`). Empty builds nothing, and any
    entry implies the time-of-day labels the baseline is taken over."""

    trend_keys: tuple[trend.TrendKey, ...] = ()
    """Compact trend labels to build (:mod:`nqbt.trend`). Empty builds nothing, and an entry
    does **not** imply :attr:`needs_ma_values` -- the averages behind a label are built and
    dropped inside :func:`nqbt.trend.trend_grid`."""

    needs_ma_values: bool = False
    """Keep the raw moving-average values, not just the boolean gates -- eight bytes per
    element against one, so off unless something reads the numbers themselves."""

    def __or__(self, other: ContextSpec) -> ContextSpec:
        return ContextSpec(
            ema_periods=tuple(sorted({*self.ema_periods, *other.ema_periods})),
            sma_periods=tuple(sorted({*self.sma_periods, *other.sma_periods})),
            atr_periods=tuple(sorted({*self.atr_periods, *other.atr_periods})),
            needs_vwap=self.needs_vwap or other.needs_vwap,
            needs_time_of_day=self.needs_time_of_day or other.needs_time_of_day,
            regime_lookbacks=tuple(sorted({*self.regime_lookbacks, *other.regime_lookbacks})),
            volume_keys=tuple(sorted({*self.volume_keys, *other.volume_keys})),
            trend_keys=tuple(sorted({*self.trend_keys, *other.trend_keys})),
            needs_ma_values=self.needs_ma_values or other.needs_ma_values,
        )

    def periods_by_kind(self) -> dict[str, tuple[int, ...]]:
        """The grids to build, keyed by kind. Keying by ``(kind, period)`` is what #72 needs."""
        return {
            kind: periods
            for kind, periods in (("ema", self.ema_periods), ("sma", self.sma_periods))
            if periods
        }


@dataclass(slots=True)
class Dataset:
    """Bars plus every condition a sweep might read, computed once.

    Conditional series are reached through :meth:`ma_gate` and :meth:`vwap_gate` rather than as
    bare attributes, so reading one nobody declared raises :class:`ContextError` naming the
    spec field to set rather than returning ``None`` into a boolean AND.
    """

    bars: pd.DataFrame
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    force_flat: BoolArray
    geometry: conditions.BarGeometry
    spec: ContextSpec
    mas: dict[str, MovingAverageGrid] = field(default_factory=dict)
    atrs: dict[int, FloatArray] = field(default_factory=dict)
    vwap: FloatArray | None = None
    below_vwap: BoolArray | None = None
    above_vwap: BoolArray | None = None
    time_of_day: timeofday.TimeOfDay | None = None
    """Session phase and bar of session, or ``None`` when nothing asked for them."""

    regimes: regime.EfficiencyRatioGrid | None = None
    """Efficiency ratios per declared lookback, or ``None`` when nothing asked for them."""

    volumes: volume.VolumeGrid | None = None
    """Absolute and relative volume per declared series, or ``None`` when nothing asked."""

    trends: trend.TrendGrid | None = None
    """Compact trend labels per declared key, or ``None`` when nothing asked for them."""

    day_codes: IndexArray | None = None
    """Calendar day of each bar as an integer, or ``None`` for a non-datetime index.

    In the index's own timezone, not UTC -- ``docs/roadmap.md`` §"The numpy-native summary
    path".
    """

    def __len__(self) -> int:
        return self.close.size

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.bars.index

    def grid(self, kind: str) -> MovingAverageGrid:
        """The grid for one moving-average kind, or a pointed error."""
        if kind not in self.mas:
            msg = (
                f"no {kind} grid in this dataset; prepare() was asked for "
                f"{sorted(self.mas)}. Add it to the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.mas[kind]

    def ma_gate(self, kind: str, period: int, *, above: bool) -> BoolArray:
        """Per-bar boolean: is the close above (or below) ``kind(period)``?

        Not ``~below`` -- the two overlap at ``close == ma``, see ``docs/nt8-fidelity.md``.
        """
        g = self.grid(kind)
        return g.above_for(period) if above else g.below_for(period)

    def ma_values(self, kind: str, period: int) -> FloatArray:
        """Raw moving-average values, for the audit trail and the MA trailing stop."""
        return self.grid(kind).values_for(period)

    def atr_values(self, period: int) -> FloatArray:
        """NT8-seeded ATR for one period, or a pointed error."""
        if period not in self.atrs:
            msg = (
                f"no ATR({period}) in this dataset; prepare() was asked for "
                f"{sorted(self.atrs)}. Add it to the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.atrs[period]

    def vwap_gate(self, *, above: bool) -> BoolArray:
        if self.below_vwap is None or self.above_vwap is None:
            msg = (
                "no session VWAP in this dataset; prepare() was not asked for it. "
                "Set needs_vwap on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.above_vwap if above else self.below_vwap

    def vwap_values(self) -> FloatArray:
        if self.vwap is None:
            msg = (
                "no session VWAP in this dataset; prepare() was not asked for it. "
                "Set needs_vwap on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.vwap

    def _time_of_day(self) -> timeofday.TimeOfDay:
        if self.time_of_day is None:
            msg = (
                "no time-of-day labels in this dataset; prepare() was not asked for them. "
                "Set needs_time_of_day on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.time_of_day

    def phase_gate(self, mask: int) -> BoolArray:
        """Per-bar boolean: does this bar's session phase pass ``mask``?

        Callers skip this entirely at :data:`nqbt.timeofday.ALL_PHASES` -- see
        :meth:`nqbt.timeofday.TimeOfDay.gate`.
        """
        return self._time_of_day().gate(mask)

    def phase_values(self) -> LabelArray:
        """Per-bar :class:`nqbt.timeofday.SessionPhase`, for stratifying results."""
        return self._time_of_day().phase

    def bar_of_session(self) -> IndexArray:
        """Per-bar index from the session open, the fine form of the same clock."""
        return self._time_of_day().bar_of_session

    def _regimes(self) -> regime.EfficiencyRatioGrid:
        if self.regimes is None:
            msg = (
                "no efficiency ratios in this dataset; prepare() was not asked for them. "
                "Add the lookback to regime_lookbacks on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.regimes

    def regime_gate(
        self,
        lookback: int,
        mask: int,
        consolidating_below: float,
        directional_above: float,
    ) -> BoolArray:
        """Per-bar boolean: does this bar's regime pass ``mask``?

        Callers skip this entirely at :data:`nqbt.regime.ALL_REGIMES` -- see
        :func:`nqbt.regime.gate`.
        """
        return self._regimes().gate_for(lookback, mask, consolidating_below, directional_above)

    def regime_values(self, lookback: int) -> FloatArray:
        """Per-bar efficiency ratio, the raw quantity behind the labels."""
        return self._regimes().values_for(lookback)

    def regime_labels(
        self,
        lookback: int,
        consolidating_below: float,
        directional_above: float,
    ) -> LabelArray:
        """Per-bar :class:`nqbt.regime.Regime`, for stratifying results."""
        return self._regimes().labels_for(lookback, consolidating_below, directional_above)

    def _volumes(self) -> volume.VolumeGrid:
        if self.volumes is None:
            msg = (
                "no volume series in this dataset; prepare() was not asked for them. "
                "Add the series to volume_keys on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.volumes

    def volume_gate(
        self,
        key: volume.VolumeKey,
        mask: int,
        thin_below: float,
        heavy_above: float,
    ) -> BoolArray:
        """Per-bar boolean: whether this bar's volume state passes ``mask``.

        Callers skip this entirely at :data:`nqbt.volume.ALL_STATES` -- see
        :func:`nqbt.volume.gate`.
        """
        return self._volumes().gate_for(key, mask, thin_below, heavy_above)

    def volume_values(self, key: volume.VolumeKey) -> FloatArray:
        """Per-bar **absolute** volume, the form that answers execution feasibility."""
        return self._volumes().absolute_for(key)

    def relative_volume(self, key: volume.VolumeKey) -> FloatArray:
        """Per-bar volume over its bar-of-session baseline -- the quantity behind the labels."""
        return self._volumes().relative_for(key)

    def volume_labels(
        self,
        key: volume.VolumeKey,
        thin_below: float,
        heavy_above: float,
    ) -> LabelArray:
        """Per-bar :class:`nqbt.volume.VolumeState`, for stratifying results."""
        return self._volumes().labels_for(key, thin_below, heavy_above)

    def _trends(self) -> trend.TrendGrid:
        if self.trends is None:
            msg = (
                "no trend labels in this dataset; prepare() was not asked for them. "
                "Add the label to trend_keys on the archetype's ContextSpec."
            )
            raise ContextError(
                msg,
            )
        return self.trends

    def trend_gate(self, key: trend.TrendKey, mask: int, min_agreement: int) -> BoolArray:
        """Per-bar boolean: whether this bar's trend passes ``mask``.

        Callers skip this entirely at :data:`nqbt.trend.ALL_TRENDS` -- see
        :func:`nqbt.trend.gate`.
        """
        return self._trends().gate_for(key, mask, min_agreement)

    def trend_values(self, key: trend.TrendKey) -> FloatArray:
        """Per-bar agreement score, the raw quantity behind the labels."""
        return self._trends().agreement_for(key)

    def trend_labels(self, key: trend.TrendKey, min_agreement: int) -> LabelArray:
        """Per-bar :class:`nqbt.trend.Trend`, for stratifying results."""
        return self._trends().labels_for(key, min_agreement)

    def trend_components(self, key: trend.TrendKey) -> LabelArray:
        """Per-bar ``[3, n_bars]`` votes, so a review can say which component dissented."""
        return self._trends().votes_for(key)

    @property
    def nbytes(self) -> int:
        """Bytes held by the derived arrays -- what a parallel worker is handed.

        Excludes ``bars``, which :meth:`slim` drops before the dataset crosses a process
        boundary.
        """
        total = sum(a.nbytes for a in (self.open, self.high, self.low, self.close))
        total += self.force_flat.nbytes
        total += sum(g.nbytes for g in self.mas.values())
        total += sum(a.nbytes for a in self.atrs.values())
        for a in (self.vwap, self.below_vwap, self.above_vwap, self.day_codes):
            if a is not None:
                total += a.nbytes
        if self.time_of_day is not None:
            total += self.time_of_day.nbytes
        if self.regimes is not None:
            total += self.regimes.nbytes
        if self.volumes is not None:
            total += self.volumes.nbytes
        if self.trends is not None:
            total += self.trends.nbytes
        return total

    def slim(self) -> Dataset:
        """A copy carrying only what the simulation reads, for crossing a process boundary.

        Everything the sweep needs from ``bars`` was already lifted into the arrays beside it
        except the index, so an index-only frame is enough. The arrays are shared, not copied.
        """
        return replace(self, bars=self.bars.iloc[:, :0])


def day_codes(index: pd.Index) -> IndexArray | None:
    """Each bar's calendar day as an ``int32``, in the index's own timezone.

    ``None`` when the index is not datetime-like. Local rather than UTC because that is what
    ``DatetimeIndex.date`` gives, which the pandas summary path groups by.
    """
    if not isinstance(index, pd.DatetimeIndex):
        return None
    local = index.tz_localize(None) if index.tz is not None else index
    return local.to_numpy().astype("datetime64[D]").astype(np.int32)


DEFAULT_SPEC = ContextSpec(ema_periods=(21,), sma_periods=(60, 175), needs_vwap=True)
"""What :func:`prepare` builds when nothing says otherwise: the pre-#27 unconditional set."""


class PrepareOptions(TypedDict, total=False):
    """Everything :func:`prepare` takes beyond the bars and the spec.

    Named once so a wrapper can forward them without restating a default.
    """

    exit_on_close_seconds: int
    keep_ma_values: bool
    bar_minutes: int | None


def prepare(
    bars: pd.DataFrame,
    spec: ContextSpec = DEFAULT_SPEC,
    *,
    exit_on_close_seconds: int = 30,
    keep_ma_values: bool = False,
    bar_minutes: int | None = None,
) -> Dataset:
    """Precompute exactly the conditions ``spec`` declares.

    ``spec`` must cover every value the sweep will ask for;
    :meth:`nqbt.sweep.Grid.required_context` derives it from the grid, which is the only way to
    be sure it does. ``bar_minutes`` sizes the bar-of-session index and is inferred from the
    index when not given -- pass it wherever the resolution is already known.
    """
    close = bars["close"].to_numpy(np.float64)
    high = bars["high"].to_numpy(np.float64)
    low = bars["low"].to_numpy(np.float64)
    info = sessions.classify(bars.index)

    # Relative volume is defined per bar of session, so asking for it builds the clock too.
    tod = (
        timeofday.classify(bars.index, bar_minutes=bar_minutes, info=info)
        if spec.needs_time_of_day or spec.volume_keys
        else None
    )
    regimes = regime.efficiency_ratio_grid(close, spec.regime_lookbacks) if spec.regime_lookbacks else None
    trends = trend.trend_grid(close, spec.trend_keys) if spec.trend_keys else None
    volumes = (
        volume.volume_grid(
            bars["volume"].to_numpy(np.float64),
            info.trading_day,
            info.in_session,
            tod.bar_of_session,  # type: ignore[union-attr]  # built above whenever keys exist
            spec.volume_keys,
        )
        if spec.volume_keys
        else None
    )

    vwap = below_vwap = above_vwap = None
    if spec.needs_vwap:
        typical = indicators.typical_price(high, low, close)
        vwap = indicators.session_vwap(
            typical,
            bars["volume"].to_numpy(np.float64),
            indicators.new_session_flags(bars["trading_day"].to_numpy()),
        )
        below_vwap = conditions.below_series(close, vwap)
        above_vwap = conditions.above_series(close, vwap)

    return Dataset(
        bars=bars,
        open=bars["open"].to_numpy(np.float64),
        high=high,
        low=low,
        close=close,
        force_flat=sessions.force_flat_mask(info, exit_on_close_seconds),
        geometry=conditions.bar_geometry(bars),
        spec=spec,
        mas={
            kind: conditions.moving_average_grid(
                close,
                periods,
                kind,
                keep_values=keep_ma_values or spec.needs_ma_values,
            )
            for kind, periods in spec.periods_by_kind().items()
        },
        atrs={p: indicators.nt8_atr(high, low, close, p) for p in spec.atr_periods},
        vwap=vwap,
        below_vwap=below_vwap,
        above_vwap=above_vwap,
        time_of_day=tod,
        regimes=regimes,
        volumes=volumes,
        trends=trends,
        day_codes=day_codes(bars.index),
    )
