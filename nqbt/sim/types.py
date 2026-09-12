"""Parameter sets for the simulated archetypes.

The trade-record layout these produce lives in :mod:`nqbt.trades`, which is shared with
the manual-trade importer and knows nothing about strategies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Protocol, override

from nqbt import (
    bands,
    compression,
    conditions,
    higher_timeframe,
    regime,
    sessionrange,
    timeofday,
    trades,
    trend,
    volume,
)


class ContextFilterParams(Protocol):
    """The six context filters and every field behind them, as one shape.

    Structural so that :func:`validate_context_filters` is one definition rather than a copy
    per parameter class. Narrower than :class:`nqbt.sim.filters.ContextFiltered`, which
    describes what the *signal* reads; this describes what has to be checked.
    """

    phase_filter: int
    regime_filter: int
    regime_lookback: int
    regime_consolidating_below: float
    regime_directional_above: float
    volume_filter: int
    volume_form: int
    volume_rolling_bars: int
    volume_baseline_sessions: int
    volume_thin_below: float
    volume_heavy_above: float
    compression_filter: int
    compression_form: int
    compression_period: int
    compression_baseline_bars: int
    compression_compressed_below: float
    compression_expanded_above: float
    trend_filter: int
    trend_fast_period: int
    trend_slow_period: int
    trend_slope_lookback: int
    trend_min_agreement: int
    higher_timeframe_filter: int
    higher_timeframe_minutes: int
    higher_timeframe_period: int


def validate_context_filters(params: ContextFilterParams) -> None:
    """Check every shared context-filter field, raising on the first that is out of range.

    The sub-fields are checked **whatever their filter admits**, so a nonsense window or
    resolution cannot ride along inertly until a sweep turns its filter on.
    """
    timeofday.validate_mask(params.phase_filter)
    regime.validate_mask(params.regime_filter)
    regime.validate_lookback(params.regime_lookback)
    regime.validate_thresholds(params.regime_consolidating_below, params.regime_directional_above)
    volume.validate_mask(params.volume_filter)
    volume.validate_form(params.volume_form)
    volume.validate_rolling_bars(params.volume_rolling_bars)
    volume.validate_baseline_sessions(params.volume_baseline_sessions)
    volume.validate_thresholds(params.volume_thin_below, params.volume_heavy_above)
    compression.validate_mask(params.compression_filter)
    compression.validate_form(params.compression_form)
    compression.validate_period(params.compression_period)
    compression.validate_baseline_bars(params.compression_baseline_bars)
    compression.validate_thresholds(
        params.compression_compressed_below,
        params.compression_expanded_above,
    )
    trend.validate_mask(params.trend_filter)
    trend.validate_periods(params.trend_fast_period, params.trend_slow_period)
    trend.validate_slope_lookback(params.trend_slope_lookback)
    trend.validate_min_agreement(params.trend_min_agreement)
    higher_timeframe.validate_mask(params.higher_timeframe_filter)
    higher_timeframe.validate_minutes(params.higher_timeframe_minutes)
    higher_timeframe.validate_period(params.higher_timeframe_period)


MIN_CONFLUENCE_FILTERS = 2
"""Fewest active context filters a confluence count can mean anything against."""

REQUIRE_ALL = 0
"""The confluence count meaning "every active context filter must pass", which is the AND
:func:`nqbt.sim.filters.apply_context_filters` has always applied.

Zero rather than the number of gates, because how many are active is a property of the
combination and a rule set has to be able to say "all of them" without knowing it.
"""


def active_context_filters(params: ContextFilterParams) -> int:
    """How many of the six context filters this combination actually restricts anything with.

    What a confluence count is measured against, and the reason it can be validated at
    construction: a rule set knows how many gates it switched on.
    """
    return sum(
        (
            params.phase_filter != timeofday.ALL_PHASES,
            params.regime_filter != regime.ALL_REGIMES,
            params.volume_filter != volume.ALL_STATES,
            params.compression_filter != compression.ALL_STATES,
            params.trend_filter != trend.ALL_TRENDS,
            params.higher_timeframe_filter != higher_timeframe.ALL_SIDES,
        ),
    )


def validate_confluence(params: ContextFilterParams, required: int) -> None:
    """Refuse a confluence count that is impossible, or that is the plain conjunction again.

    ``REQUIRE_ALL`` is the conjunction and always legal. Anything from the number of active
    gates upwards *is* that conjunction, or narrower than any bar can satisfy, and both are
    silent duplicates of a combination the sweep already runs -- the shape ``dead_axes``
    cannot see. ``docs/roadmap.md`` § "The build spec's three loose ends".
    """
    if required == REQUIRE_ALL:
        return

    active: int = active_context_filters(params)
    if active < MIN_CONFLUENCE_FILTERS:
        msg: str = (
            f"confluence_required is {required} but this combination switches {active} "
            f"context filters on; 'at least N of M' needs at least "
            f"{MIN_CONFLUENCE_FILTERS} of them, and {REQUIRE_ALL} is how a rule set asks "
            f"for every active filter"
        )
        raise ValueError(msg)

    if required < 1 or required >= active:
        msg = (
            f"confluence_required must be {REQUIRE_ALL} (every active filter) or between 1 "
            f"and {active - 1}; this combination switches {active} filters on, so {required} "
            f"is either unsatisfiable or the plain conjunction under another name"
        )
        raise ValueError(msg)


def validate_max_hold_bars(max_hold_bars: int) -> None:
    """Refuse a negative maximum hold time. ``0`` is how a rule set switches it off."""
    if max_hold_bars < 0:
        msg: str = f"max_hold_bars must be >= 0, got {max_hold_bars}"
        raise ValueError(msg)


@dataclass(slots=True)
class DeadCatParams:
    """Rule set for the DeadCatBounce archetype.

    Mirrors the NinjaScript's properties: booleans switch filters on and off, numbers set
    periods and sizes. Defaults are exactly the NT8 ``SetDefaults`` values so that an
    unmodified instance reproduces the live strategy.
    """

    ema_period: int = 11
    slow_sma_period: int = 155
    fast_sma_period: int = 80

    ema_kind: str = "ema"
    slow_sma_kind: str = "sma"
    fast_sma_kind: str = "sma"
    """Which average each gate is actually computed as -- one of
    :data:`nqbt.conditions.MA_KINDS`. Absent from the NinjaScript, which hardcodes an ``EMA``
    and two ``SMA``s; the gates keep their NinjaScript names so the C# and the Python can
    still be diffed by eye -- ``docs/roadmap.md`` § "Moving-average kind as a swept axis"."""

    order_quantity: int = 4

    use_ema: bool = True
    use_slow_sma: bool = False
    use_fast_sma: bool = True
    use_vwap: bool = False
    require_previous_green: bool = True
    require_new_high: bool = True

    phase_filter: int = timeofday.ALL_PHASES
    """Which session phases an entry may be taken in, as a :mod:`nqbt.timeofday` bitmask.

    Absent from the NinjaScript, and off by default. A bitmask integer rather than a tuple so
    that it is a legal sweep axis -- ``docs/roadmap.md`` §M10.4."""

    regime_filter: int = regime.ALL_REGIMES
    """Which market regimes an entry may be taken in, as a :mod:`nqbt.regime` bitmask.

    Absent from the NinjaScript, off by default, and a bitmask for the same reason
    :attr:`phase_filter` is -- ``docs/roadmap.md`` §M10.1."""

    regime_lookback: int = 20
    """Bars the efficiency ratio measures over."""

    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """Where the ratio is cut into the three regimes, both boundaries falling in the
    unclassifiable band. Conventional starting points rather than measured ones, and inert
    while :attr:`regime_filter` admits everything -- ``docs/roadmap.md`` §M10.1."""

    volume_filter: int = volume.ALL_STATES
    """Which volume states an entry may be taken in, as a :mod:`nqbt.volume` bitmask.

    Absent from the NinjaScript, off by default, and a bitmask for the same reason
    :attr:`phase_filter` is. The states are cut from **relative** volume, never an absolute
    count -- ``docs/roadmap.md`` §M10.2."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    """Which absolute quantity the ratio is taken of -- see :class:`nqbt.volume.VolumeForm`."""

    volume_rolling_bars: int = 30
    """Bars the :attr:`~nqbt.volume.VolumeForm.ROLLING` form sums over. Inert at every other
    form, which ``dead_axes`` cannot see -- ``docs/roadmap.md`` §M10.2."""

    volume_baseline_sessions: int = 20
    """Prior sessions the bar-of-session baseline is the median of."""

    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """Where relative volume is cut into the three states, both boundaries falling in the
    normal band. Conventional starting points rather than measured ones, and inert while
    :attr:`volume_filter` admits everything -- ``docs/roadmap.md`` §M10.2."""

    compression_filter: int = compression.ALL_STATES
    """Which compression states an entry may be taken in, as a :mod:`nqbt.compression` bitmask.

    Absent from the NinjaScript, off by default, and a bitmask for the same reason
    :attr:`phase_filter` is. The states are cut from a **trailing rank**, never a raw width --
    ``docs/roadmap.md`` §M19.1."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    """Which width measure the rank is taken of -- see :class:`nqbt.compression.CompressionForm`."""

    compression_period: int = 20
    """Bars the width measure spans. Both forms read it, so it is inert under neither."""

    compression_baseline_bars: int = 250
    """Bars the rank is taken against, all strictly before the bar being ranked."""

    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """Where the rank is cut into the three states, both boundaries falling in the normal band.
    Quarters of a trailing window rather than measured points, and inert while
    :attr:`compression_filter` admits everything -- ``docs/roadmap.md`` §M19.1."""

    trend_filter: int = trend.ALL_TRENDS
    """Which trends an entry may be taken in, as a :mod:`nqbt.trend` bitmask.

    Absent from the NinjaScript, off by default, and a bitmask for the same reason
    :attr:`phase_filter` is. Its averages are its own rather than the gates' above, so the
    label means the same thing across archetypes -- ``docs/roadmap.md`` §M10.3."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    """The pair the label reads. Both EMAs, and the fast one must be the shorter."""

    trend_slope_lookback: int = 5
    """Bars back the slow average's slope is measured over."""

    trend_min_agreement: int = 3
    """How many of the three components must agree before a bar is UP or DOWN rather than
    MIXED. ``3`` is unanimity, and inert while :attr:`trend_filter` admits everything --
    ``docs/roadmap.md`` §M10.3."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Which side of a coarse moving average an entry may be taken on, as a
    :mod:`nqbt.higher_timeframe` bitmask.

    Absent from the NinjaScript, off by default, and a bitmask for the same reason
    :attr:`phase_filter` is. The average is stamped from the last **completed** coarse bar --
    ``docs/roadmap.md`` § "Multi-timeframe moving averages"."""

    higher_timeframe_minutes: int = 60
    """Minutes one coarse bar spans, anchored to the session open."""

    higher_timeframe_period: int = 50
    """Bars of *that* resolution the average is taken over, never 1-minute bars. An EMA, and
    inert while :attr:`higher_timeframe_filter` admits every side."""

    tp_multiplier: float = 1.0
    """Scales every leg's target. ``TPMultiplier`` in the NinjaScript."""

    max_risk_ticks: int = 250
    """Reject the signal when ``stop - trigger`` exceeds this many **ticks**, not dollars."""

    bars_required_to_trade: int = 200
    stop_offset_ticks: int = 2
    """Ticks beyond the signal bar's high for the stop. Hardcoded as 2 in the NinjaScript."""

    entry_offset_ticks: int = 2
    """Ticks below the close used to cap the entry trigger at ``min(Low[0], Close[0] - 2t)``.

    See ``docs/nt8-fidelity.md``, "Trigger is capped below the close"."""

    ambiguity_policy: int = 1
    """How a bar holding both the stop and a target is resolved.

    ``1`` fills the level nearer the bar's open, reproducing NT8; ``0`` assumes a blanket
    worst case, which is *more* pessimistic than NT8 rather than equal to it. Evidence:
    ``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the open"."""

    fill_limit_on_touch: bool = False
    """Whether a profit target fills when price merely reaches it.

    ``IsFillLimitOnTouch = false`` in the NinjaScript, so a limit must be traded *through*."""

    block_entry_at_session_close: bool = True
    """Whether a signal on the session's final bar is skipped."""

    max_hold_bars: int = 0
    """Bars a position may be held before a market exit is submitted, off at ``0``.

    Absent from the NinjaScript, off by default, and on top of the session flatten every
    archetype already has. The count is bars *since* the entry bar and the order fills at the
    next bar's open, so a leg's ``bars_held`` reaches ``max_hold_bars + 1``. It is a bar count
    rather than a duration, so it means a different amount of time at every resolution --
    ``docs/nt8-fidelity.md``, "The maximum hold time, and why it is its own exit code"."""

    ratchet_lag: int = 0
    """Which bar's high the trailing stop references at each bar close.

    ``0`` is ``High[0]``, what the NinjaScript does; ``1`` is the bar before it. See
    ``docs/nt8-fidelity.md``, "Ratchet reads the just-closed bar"."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg profit targets in R. ``nan`` marks a runner with no target -- S4 in the
    NinjaScript, which exits only via the trailing stop or the session close."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on market and stop orders. Never applied to limit targets."""

    # Off by default: the spec asks for this, the NinjaScript does not implement it.
    min_reward_risk: float = 0.0
    """Pre-trade gate: skip the signal unless the furthest target clears this ratio."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            msg: str = (
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
            raise ValueError(
                msg,
            )

        for gate in ("ema", "slow_sma", "fast_sma"):
            if getattr(self, f"{gate}_period") < 1:
                msg = f"{gate}_period must be >= 1"
                raise ValueError(msg)

            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last: 10 splits 2/2/2/4, not 3/3/2/2."""
        n: int = len(self.target_r_multiples)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


@dataclass(slots=True)
class PullBackAndGoParams:
    """Rule set for the PullBackAndGo archetype -- DeadCatBounce's long-side mirror.

    Leaner than :class:`DeadCatParams` because ``PullBackAndGo.cs`` has fewer properties, and
    **these defaults are the reconciled configuration rather than the NinjaScript's**, which
    has none. Both points: ``docs/nt8-fidelity.md``, "Reconciliation result -- PullBackAndGo".
    """

    ema_period: int = 21
    slow_sma_period: int = 175
    fast_sma_period: int = 60

    ema_kind: str = "ema"
    slow_sma_kind: str = "sma"
    fast_sma_kind: str = "sma"
    """Which average each gate is actually computed as -- one of
    :data:`nqbt.conditions.MA_KINDS`. Absent from the NinjaScript, which hardcodes an ``EMA``
    and two ``SMA``s; the gates keep their NinjaScript names so the C# and the Python can
    still be diffed by eye -- ``docs/roadmap.md`` § "Moving-average kind as a swept axis"."""

    order_quantity: int = 4

    use_ema: bool = True
    use_slow_sma: bool = True
    use_fast_sma: bool = True
    use_vwap: bool = False
    """Off in the reconciled configuration, and deliberately so -- ``docs/nt8-fidelity.md``."""

    require_previous_red: bool = True
    require_new_low: bool = True

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The form the ratio is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The pair the label reads, its slope lookback and how many components must agree --
    see :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Which side of a coarse moving average an entry may be taken on --
    see :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged over it --
    see :attr:`DeadCatParams.higher_timeframe_period`."""

    bars_required_to_trade: int = 20
    stop_offset_ticks: int = 2
    """Ticks below the signal bar's low for the stop. ``TickSize * 2`` in the NinjaScript."""

    ratchet_lag: int = 1
    """``PullBackAndGo.cs`` ratchets to ``Low[1]``, unlike DeadCatBounce's lag-0 ``High[0]``.

    Evidence: ``docs/nt8-fidelity.md``, "Ratchet reads the just-closed bar"."""

    ratchet_offset_ticks: int = 2
    """Ticks beyond the ratchet's reference low, as ``Low[1] - (TickSize * 2)``.

    Separate from :attr:`stop_offset_ticks` -- ``docs/nt8-fidelity.md``."""

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- the same Tier-1 concept, same default."""

    fill_limit_on_touch: bool = False
    """``IsFillLimitOnTouch = false`` in the NinjaScript, same as DeadCatBounce."""

    block_entry_at_session_close: bool = True
    """``IsExitOnSessionCloseStrategy = true`` in the NinjaScript, same as DeadCatBounce."""

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    round_targets: bool = True
    """On, although ``PullBackAndGo.cs`` never calls ``RoundToTickSize``: NT8 snaps the targets
    anyway. See ``docs/nt8-fidelity.md``, "Targets snap to the tick grid"."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """L1/L2/L3 at 1R/1.5R/2R; L4 is the runner with no target, matching the NinjaScript."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on market and stop orders. Never applied to limit targets."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            msg: str = (
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
            raise ValueError(
                msg,
            )

        for gate in ("ema", "slow_sma", "fast_sma"):
            if getattr(self, f"{gate}_period") < 1:
                msg = f"{gate}_period must be >= 1"
                raise ValueError(msg)

            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- DeadCatBounce's split exactly."""
        n: int = len(self.target_r_multiples)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


STOP_MIN_TICKS = 1.0
"""Fewest ticks a protective stop may sit from the fill, below which the entry is skipped.

The stop-entry submittability rule applied to the protective stop, and reachable only for a
market-on-next-open entry -- ``docs/nt8-fidelity.md`` §M18.
"""


@dataclass(slots=True)
class EmaCrossoverParams:
    """Rule set for the EmaCrossover archetype -- the first original, with no NinjaScript.

    **A known-negative control, not an edge candidate**: if it reads meaningfully better than
    the random-entry arm, the first hypothesis is lookahead. Every rule it implements, and the
    NinjaScript each would be written as: ``docs/nt8-fidelity.md`` §M18. The result it produced:
    ``docs/roadmap.md`` §M18.
    """

    fast_period: int = 9
    slow_period: int = 21
    """The two periods that cross. Rejected only when the kinds match too, because
    ``ema(21)`` against ``sma(21)`` is a real cross."""

    fast_kind: str = "ema"
    slow_kind: str = "ema"
    """Which average each side is computed as -- one of :data:`nqbt.conditions.MA_KINDS`. The
    archetype's name records what it was built as, not what it is limited to."""

    cross_lookback: int = 1
    """``n`` in ``CrossAbove(fast, slow, n)`` -- a cross within the last ``n`` bars counts."""

    trade_long: bool = True
    trade_short: bool = True
    """Which sides to take. Switching one off is how the two halves get measured separately."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The form the ratio is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The pair the label reads, its slope lookback and how many components must agree --
    see :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Which side of a coarse moving average an entry may be taken on --
    see :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged over it --
    see :attr:`DeadCatParams.higher_timeframe_period`."""

    confluence_required: int = REQUIRE_ALL
    """How many of the active context filters an entry needs, rather than all of them.

    The only archetype that reads it, so the other six keep the plain conjunction. Legal
    values are :data:`REQUIRE_ALL` and ``1`` up to one below the number of filters this
    combination switches on -- :func:`validate_confluence`."""

    exit_on_opposite_cross: bool = True
    """Close the position at the next bar's open when the regime flips.

    The only producer of ``EXIT_SIGNAL``. Off leaves the stop, the targets and the session
    close."""

    order_quantity: int = 4

    use_atr_stop: bool = True
    """ATR-multiple stop when on, structural swing stop when off.

    ``dead_axes`` can guard the ATR fields against this but not :attr:`swing_lookback` --
    ``docs/roadmap.md`` §M17."""

    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    """Stop distance as a multiple of ATR at the signal bar -- the last *completed* bar."""

    min_bracket_dollars: float = 0.0
    """Floor on the ATR stop distance, in **dollars per contract**, off at ``0``.

    In **dollars** rather than points because NQ and MNQ share a tick size and differ 10x in
    tick value, so one point distance is two different amounts of money;
    :meth:`nqbt.instruments.Instrument.dollars_to_points` converts it per instrument. What it
    does to R: ``docs/roadmap.md`` § "ATR-multiple brackets and the dollar floor"."""

    swing_lookback: int = 3
    """Completed bars the swing stop takes its extreme from, the signal bar included."""

    stop_offset_ticks: int = 2
    """Ticks beyond the swing extreme, matching the two ported archetypes. Not applied to
    the ATR stop, whose multiple already sets the distance."""

    trail_ma_stop: bool = False
    """Trail the stop along a moving average, on top of whichever mode placed it.

    **Off by default and it must stay off in a sweep's base**: it is the only thing here that
    needs ``keep_values``, which is the 8-bytes-against-1 memory switch every parallel worker
    pays -- ``docs/roadmap.md`` § "The build spec's three loose ends"."""

    trail_ma_kind: str = "ema"
    trail_ma_period: int = 50
    """The average the stop follows -- a third grid, independent of the two that cross."""

    trail_offset_ticks: int = 2
    """Ticks beyond the average the trailing stop sits, so it is not exactly on the level it
    follows. Separate from :attr:`stop_offset_ticks` for the reason
    ``ratchet_offset_ticks`` is separate from it in the ported archetypes."""

    round_number_points: float = 0.0
    """Spacing of the round numbers a stop may never sit exactly on, in points; ``0`` is off.

    **Only meaningful on raw prices**, so a dataset must declare
    :attr:`nqbt.context.PriceBasis.RAW` before a combination setting this will run --
    ``docs/roadmap.md`` § "The build spec's three loose ends"."""

    round_number_offset_ticks: int = 2
    """Ticks further from the entry a stop landing on a round number is pushed."""

    tp_multiplier: float = 1.0
    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, ``nan`` marking a runner.

    **R is volatility-scaled here, not structure-scaled**, so these numbers are not comparable
    to DeadCatBounce's at the same values, and where :attr:`min_bracket_dollars` binds it is
    dollar-scaled instead -- ``docs/nt8-fidelity.md`` §M18."""

    bars_required_to_trade: int = 200

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- same concept, same default."""

    fill_limit_on_touch: bool = False
    block_entry_at_session_close: bool = True

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    round_targets: bool = True
    """Snap targets onto the tick grid, which NT8 does at submission whatever the script does."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and both market exits. Never applied to a limit target."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            msg: str = f"order_quantity {self.order_quantity} cannot fill {len(self.target_r_multiples)} legs"
            raise ValueError(msg)

        for name in ("fast_period", "slow_period", "atr_period", "swing_lookback", "trail_ma_period"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        for gate in ("fast", "slow", "trail_ma"):
            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        if self.cross_lookback < 1:
            msg = f"cross_lookback must be >= 1, got {self.cross_lookback}"
            raise ValueError(msg)

        if self.min_bracket_dollars < 0.0:
            msg = f"min_bracket_dollars must be >= 0, got {self.min_bracket_dollars}"
            raise ValueError(msg)

        if self.round_number_points < 0.0:
            msg = f"round_number_points must be >= 0, got {self.round_number_points}"
            raise ValueError(msg)

        # An offset of zero would leave the stop on the round number the rule exists to avoid.
        if self.round_number_points > 0.0 and self.round_number_offset_ticks < 1:
            msg = (
                f"round_number_offset_ticks must be >= 1 while round_number_points is "
                f"{self.round_number_points}, got {self.round_number_offset_ticks}"
            )
            raise ValueError(msg)

        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)
        validate_confluence(self, self.confluence_required)
        if (self.fast_kind, self.fast_period) == (self.slow_kind, self.slow_period):
            msg = (
                f"fast and slow are both {self.fast_kind}({self.fast_period}); identical "
                "averages never cross, so every combination along that axis trades nothing"
            )
            raise ValueError(msg)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- the ported archetypes' split."""
        n: int = len(self.target_r_multiples)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


@dataclass(slots=True)
class InsideBarParams:
    """Rule set for the InsideBar archetype -- an inside-bar breakout with an ATR bracket.

    Ported from ``ninjatrader-scripts/Strategies/InsideBar.cs``, whose ``SetDefaults``
    initialises every declared property, so these defaults are the NinjaScript's directly.
    Every rule and every open question: ``docs/nt8-fidelity.md`` §M22.

    **The default geometry is deliberately lopsided** -- a target 1x ATR(3) from the fill
    against a stop 10x ATR(3) beyond the signal bar, so R multiples cluster just above zero
    and are not comparable to another archetype's at the same value.
    """

    order_quantity: int = 4
    """One entry, one stop and one target: ``InsideBar.cs`` never scales out."""

    ema_period: int = 22
    fast_sma_period: int = 35
    slow_sma_period: int = 200
    """The three averages the breakout is gated on. All three must agree, and the comparison
    is **strict** on each -- ``docs/nt8-fidelity.md`` §M22."""

    ema_kind: str = "ema"
    slow_sma_kind: str = "sma"
    fast_sma_kind: str = "sma"
    """Which average each gate is actually computed as -- one of
    :data:`nqbt.conditions.MA_KINDS`. Absent from the NinjaScript, which hardcodes an ``EMA``
    and two ``SMA``s; the gates keep their NinjaScript names so the C# and the Python can
    still be diffed by eye -- ``docs/roadmap.md`` § "Moving-average kind as a swept axis"."""

    error_margin: float = 0.01
    """Fraction of the mother bar's range the close must clear its extreme by."""

    atr_length: int = 3
    atr_multiplier: float = 10.0
    """ATR period, and how many of them the stop sits beyond the signal bar's extreme."""

    tp_multiplier: float = 1.0
    """How many ATRs the target sits from the fill. ``TPMultiplier`` in the NinjaScript, whose
    default is the bare 1x the target was hardcoded at -- ``docs/nt8-fidelity.md`` §M22."""

    bars_required_to_trade: int = 5
    """``CurrentBars[0] <= BarsRequiredToTrade`` returns, so the first tradable bar is one
    later than the two ported archetypes' -- ``docs/nt8-fidelity.md`` §M22."""

    no_entry_minutes_before_close: int = 60
    """No entry within this many minutes of the session's scheduled close, off at ``0``.

    Distinct from :attr:`block_entry_at_session_close`, which guards only the force-flat bar.
    The NinjaScript's one hour, and the wall-clock trap it carries: ``docs/nt8-fidelity.md``
    §M22."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The form the ratio is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The pair the label reads, its slope lookback and how many components must agree --
    see :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Which side of a coarse moving average an entry may be taken on --
    see :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged over it --
    see :attr:`DeadCatParams.higher_timeframe_period`."""

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- the same concept, the same default."""

    fill_limit_on_touch: bool = True
    """``IsFillLimitOnTouch = true`` in the NinjaScript, unlike both ports: a target fills
    when price merely reaches it. ``docs/nt8-fidelity.md``, "Limit orders must trade
    *through*, not touch" -- and §M22 for what still has no evidence behind it."""

    block_entry_at_session_close: bool = True
    """``IsExitOnSessionCloseStrategy = true`` in the NinjaScript, same as both ports."""

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    round_targets: bool = True
    """On, although ``InsideBar.cs`` never calls ``RoundToTickSize``: NT8 snaps submitted
    prices anyway. **Here it covers the stop as well as the target**, which an ATR multiple
    puts off the grid where both ports' tick offsets cannot. See ``docs/nt8-fidelity.md``,
    "Targets snap to the tick grid"."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and both market exits. Never applied to a limit target."""

    def __post_init__(self) -> None:
        for name in ("order_quantity", "ema_period", "fast_sma_period", "slow_sma_period", "atr_length"):
            if getattr(self, name) < 1:
                msg: str = f"{name} must be >= 1"
                raise ValueError(msg)
        for gate in ("ema", "slow_sma", "fast_sma"):
            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        if not 0.0 <= self.error_margin <= 1.0:
            msg = f"error_margin must be in [0, 1], got {self.error_margin}; NT8 caps it with Range(0, 1)"
            raise ValueError(msg)

        if self.atr_multiplier <= 0.0:
            msg = f"atr_multiplier must be > 0, got {self.atr_multiplier}"
            raise ValueError(msg)

        if self.tp_multiplier <= 0.0:
            msg = f"tp_multiplier must be > 0, got {self.tp_multiplier}"
            raise ValueError(msg)

        if self.no_entry_minutes_before_close < 0:
            msg = f"no_entry_minutes_before_close must be >= 0, got {self.no_entry_minutes_before_close}"
            raise ValueError(msg)

        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """The whole position on one leg -- ``InsideBar.cs`` brackets it with one order pair."""
        return (self.order_quantity,)

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


MIN_SPLIT_QUANTITY = 2
"""Fewest contracts InsideBarTrailing can take, one per lot -- the NinjaScript's ``Range(2, ...)``."""

MAX_PARTIAL_SHARE = 0.9
"""Largest share the bracketed lot may take, so the trailing lot always gets something."""


@dataclass(slots=True)
class InsideBarTrailingParams(InsideBarParams):
    """Rule set for the InsideBarTrailing archetype -- InsideBar's entry, split-lot exits.

    Ported from ``ninjatrader-scripts/Strategies/InsideBarTrailing.cs``. It subclasses
    :class:`InsideBarParams` because the two NinjaScripts share one entry rule and differ only
    in its defaults, so the entry is one implementation with two sets of them.

    **The four redeclared defaults are not cosmetic.** ``error_margin`` is ten times
    ``InsideBar.cs``'s, which is a different strategy rather than a tweak, and the script drops
    the no-entry window entirely. ``docs/nt8-fidelity.md`` §M23.
    """

    order_quantity: int = 6
    """``Range(2, int.MaxValue)`` in the NinjaScript, because it is split across two entries."""

    slow_sma_period: int = 125
    error_margin: float = 0.1
    """``InsideBar.cs``'s 200 and 0.01. Ten times the breakout buffer is a different rule --
    ``docs/nt8-fidelity.md`` §M23."""

    no_entry_minutes_before_close: int = 0
    """Off: this NinjaScript has no session-end guard, where ``InsideBar.cs`` has an hour."""

    partial_take_profit_percentage: float = 0.6
    """Share of ``order_quantity`` the bracketed lot takes, rounded **up** -- 4 of 6."""

    trailing_stop_multiplier: float = 5.0
    """Multiples of the inside bar's range the trailing stop follows the high-water mark by."""

    position_update_loss_gate: float = 200.0
    """How far under water the open position must be before ``OnPositionUpdate`` acts at all.

    The NinjaScript's hardcoded ``-200``, which has no property behind it and sits **above**
    both exit branches -- so it gates the live trend violation, not just the dead max-loss
    check. **Account currency, so it means ten times the move on MNQ that it means on NQ**;
    it reaches ``instruments.py``'s point value in the loop. ``docs/nt8-fidelity.md`` §M23."""

    maximum_loss_per_trade: float = 0.0
    """Dead in the NinjaScript and refused at anything else here -- ``docs/nt8-fidelity.md``
    §M23. Enabling it needs a currency amount routed through :mod:`nqbt.instruments`."""

    @override
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.order_quantity < MIN_SPLIT_QUANTITY:
            msg: str = (
                f"order_quantity must be >= {MIN_SPLIT_QUANTITY} to split, got {self.order_quantity}; "
                f"NT8 caps it with Range({MIN_SPLIT_QUANTITY}, int.MaxValue)"
            )
            raise ValueError(msg)

        if not 0.0 <= self.partial_take_profit_percentage <= MAX_PARTIAL_SHARE:
            msg = (
                f"partial_take_profit_percentage must be in [0, {MAX_PARTIAL_SHARE}], got "
                f"{self.partial_take_profit_percentage}; NT8 caps it with Range(0, {MAX_PARTIAL_SHARE})"
            )
            raise ValueError(msg)

        if self.position_update_loss_gate < 0.0:
            msg = (
                f"position_update_loss_gate is a loss magnitude and must be >= 0, got "
                f"{self.position_update_loss_gate}"
            )
            raise ValueError(msg)

        if self.trailing_stop_multiplier < 1.0:
            msg = (
                f"trailing_stop_multiplier must be >= 1, got {self.trailing_stop_multiplier}; "
                f"NT8 caps it with Range(1, double.MaxValue)"
            )
            raise ValueError(msg)

        if min(self.leg_quantities) < 1:
            msg = (
                f"the split leaves a lot of zero contracts: {self.leg_quantities} from "
                f"order_quantity={self.order_quantity} at {self.partial_take_profit_percentage}"
            )
            raise ValueError(msg)

        if self.maximum_loss_per_trade != 0.0:
            msg = (
                "maximum_loss_per_trade is unreachable in the NinjaScript and unimplemented here; "
                "it must stay 0.0 -- see docs/nt8-fidelity.md, §M23"
            )
            raise ValueError(msg)

    @property
    @override
    def leg_quantities(self) -> tuple[int, ...]:
        """The two entry orders' sizes: the bracketed lot, then the trailing one.

        ``(int) Math.Ceiling(OrderQuantity * PartialTakeProfitPercentage)`` and the remainder.
        """
        first: int = math.ceil(self.order_quantity * self.partial_take_profit_percentage)

        return (first, self.order_quantity - first)


STOP_ATR = 0
STOP_EXCURSION = 1
STOP_CATASTROPHE = 2
STOP_SWING = 3
STOP_BAND = 4
STOP_MODES = {
    STOP_ATR: "atr",
    STOP_EXCURSION: "excursion",
    STOP_CATASTROPHE: "catastrophe",
    STOP_SWING: "swing",
    STOP_BAND: "band",
}
"""Where the elastic band's protective stop goes, one per exit scheme -- ``docs/roadmap.md``
§M26, "Three exit schemes". ``atr`` is a distance off the fill and the only floored one;
``excursion`` is the adverse extreme of the bars that were outside the band; ``catastrophe``
is :attr:`ElasticBandParams.catastrophe_stop_ticks` and is an account rule rather than a
strategy stop; ``swing`` is the adverse extreme of a fixed number of bars, which at
``swing_lookback = 1`` is the signal candle alone and is the tightest stop the archetype can
express; ``band`` is a level on the channel the entry was measured against, the only stop here
whose distance scales with the dispersion the entry threshold uses -- ``docs/roadmap.md``
§M26.8.
"""

BAND_BOLLINGER = 0
BAND_VWAP = 1
BAND_SOURCES = {BAND_BOLLINGER: "bollinger", BAND_VWAP: "vwap"}
"""Which channel the extension is measured against. ``bollinger`` is ``nt8_sma`` +- k *
``nt8_stddev`` over :attr:`ElasticBandParams.band_period`; ``vwap`` is the session VWAP and
its volume-weighted dispersion, whose window is the session so far rather than a period --
``docs/roadmap.md`` §M26.4.
"""

TARGET_STRETCH = 0
TARGET_R = 1
TARGET_MODES = {TARGET_STRETCH: "stretch", TARGET_R: "r"}
"""Which per-leg target tuple is read. ``stretch`` places every leg on a band level and is the
mean-reversion geometry; ``r`` uses the shared R ladder and is comparable with EmaCrossover.
"""

SHAPE_ANY = 0
SHAPE_REVERSAL = 1
SHAPE_RECLAIM = 2
SHAPE_REJECTION = 3
SHAPE_MODES = {
    SHAPE_ANY: "any",
    SHAPE_REVERSAL: "reversal",
    SHAPE_RECLAIM: "reclaim",
    SHAPE_REJECTION: "rejection",
}
"""What the signal bar's own candle has to look like before an extension is faded. ``any`` asks
nothing of it; ``reversal`` needs a body closing back towards the basis; ``reclaim`` needs the
bar to have taken out the previous bar's extreme and closed back past its close; ``rejection``
needs the close within :attr:`ElasticBandParams.rejection_close_fraction` of the bar's range of
the extreme it stretched to. Why there is no engulfing mode: ``docs/roadmap.md`` §M26.5.
"""

TRIGGER_EXTENDED = 0
TRIGGER_RECOVERY = 1
TRIGGER_MODES = {TRIGGER_EXTENDED: "extended", TRIGGER_RECOVERY: "recovery"}
"""Which bar of an extension schedules the entry. ``extended`` fades a bar that is still
outside the band, which is every rule above it; ``recovery`` waits for the run outside to end
and takes the bar that closes back inside, at a depth
:attr:`ElasticBandParams.recovery_fraction` names. A different trigger rather than a fifth
shape, because every :data:`SHAPE_MODES` value is read on a bar that is still beyond the
threshold -- ``docs/roadmap.md`` §M26.6.
"""


@dataclass(slots=True)
class ElasticBandParams:
    """Rule set for the ElasticBand archetype -- an original, with no NinjaScript.

    The first mean-reversion archetype: fade a close far enough outside a band and target the
    middle. :attr:`band_source` picks the channel -- Bollinger over :attr:`band_period`, or the
    session-anchored VWAP. Every rule it implements, and the NinjaScript each would be written
    as: ``docs/nt8-fidelity.md`` §M26. The design and the three exit schemes:
    ``docs/roadmap.md`` §M26.
    """

    band_source: int = BAND_BOLLINGER
    """One of :data:`BAND_SOURCES` -- which channel the extension is measured against."""

    band_period: int = 20
    """Period of both the basis and the standard deviation, which are one window.

    Read under :data:`BAND_BOLLINGER` alone; the VWAP band's window is the session."""

    vwap_min_session_bars: int = 30
    """Bars a session's VWAP band must have before it can signal, under :data:`BAND_VWAP`.

    The anchor resets at every session open, so the first bars of a session have a band built
    from too few observations to be one -- ``docs/roadmap.md`` §M26.4."""

    entry_std: float = 2.0
    """How far outside the basis a close must sit to signal, in standard deviations."""

    max_entry_std: float = 0.0
    """Ceiling on that extension, off at ``0``.

    Beyond some point the move is a trend breaking out rather than a band being stretched, so
    the entry region is bounded rather than one-sided -- ``docs/roadmap.md`` §M26."""

    min_bars_outside: int = 1
    """Consecutive bars that must have been outside before an entry.

    The signal bar is included under :data:`TRIGGER_EXTENDED` and is not under
    :data:`TRIGGER_RECOVERY`, where the run ends at the bar before it."""

    entry_trigger: int = TRIGGER_EXTENDED
    """One of :data:`TRIGGER_MODES` -- which bar of an extension schedules the entry."""

    recovery_fraction: float = 1.0
    """How far back inside the band the close must come, as a share of :attr:`entry_std`.

    ``1.0`` is the band edge itself and anything less is a depth. Read under
    :data:`TRIGGER_RECOVERY` alone -- ``docs/roadmap.md`` §M26.6."""

    band_lag: int = 0
    """Bars back the band is read from: ``0`` is the signal bar's own, ``1`` the previous one.

    At ``0`` the band contains the bar being tested, which damps the signal rather than
    looking ahead -- ``docs/roadmap.md`` §M26."""

    signal_shape: int = SHAPE_ANY
    """One of :data:`SHAPE_MODES` -- what the signal bar's own candle has to look like.

    A reaction at the level rather than a blind fade of it -- ``docs/roadmap.md`` §M26.5."""

    rejection_close_fraction: float = 0.5
    """Share of the signal bar's range its close must sit inside, measured from the extreme the
    move stretched to. Read under :data:`SHAPE_REJECTION` alone, where a zero-range bar never
    qualifies."""

    min_one_sided_bars: int = 0
    """Bars of the last :attr:`one_sided_lookback` that must have closed *with* the extension.

    Off at ``0``. How one-sided the move into the band was, which is the other half of the
    overextension gauge whose first half is how far beyond the band it went --
    ``docs/roadmap.md`` §M26.5."""

    one_sided_lookback: int = 10
    """Window :attr:`min_one_sided_bars` counts over, read while that is above ``0``."""

    trade_long: bool = True
    trade_short: bool = True
    """Which side to fade. Long fades a close below the lower band."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The relative-volume series and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The trend label's averages and its agreement threshold -- see
    :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Sides of a coarse average an entry may be taken on -- see
    :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged on it -- see
    :attr:`DeadCatParams.higher_timeframe_period`."""

    stop_mode: int = STOP_ATR
    """One of :data:`STOP_MODES`."""

    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    """Stop distance as a multiple of ATR at the signal bar, under :data:`STOP_ATR`."""

    min_bracket_dollars: float = 0.0
    """Floor on the ATR stop distance in **dollars per contract**, off at ``0``.

    Applies to :data:`STOP_ATR` alone, because only it is a distance rather than a level --
    see :attr:`EmaCrossoverParams.min_bracket_dollars`."""

    stop_offset_ticks: int = 2
    """Ticks beyond the extreme under :data:`STOP_EXCURSION` and :data:`STOP_SWING`, so the
    stop never sits exactly on the level it protects."""

    swing_lookback: int = 1
    """Completed bars :data:`STOP_SWING` takes its extreme from, the signal bar included.

    At ``1`` the stop is just beyond the signal candle itself: the cheapest possible attempt,
    which is the point of it -- a move that keeps going costs a few ticks and the next bar can
    try again."""

    catastrophe_stop_ticks: int = 400
    """Stop distance under :data:`STOP_CATASTROPHE`, in ticks from the fill.

    Deliberately wide: it is the account's loss limit rather than a strategy stop, and the
    scheme it belongs to exists to test whether a strategy stop helps at all."""

    band_stop_std: float = 1.0
    """How far past :attr:`entry_std` the band stop sits, in standard deviations.

    Read under :data:`STOP_BAND` alone, off the signal bar's basis and dispersion exactly as a
    stretch target is: at ``entry_std = 2.0`` a value of ``1.0`` stops at the 3-sigma band. Past
    the threshold rather than at an absolute level because :attr:`entry_std` is swept, and cells
    cut by a level one entry depth has already passed could not be read against each other --
    ``docs/roadmap.md`` §M26.8."""

    target_mode: int = TARGET_STRETCH
    """One of :data:`TARGET_MODES`."""

    target_stretch_levels: tuple[float, ...] = (0.0, float("nan"))
    """Per-leg exit levels in standard deviations from the basis, ``nan`` marking a runner.

    ``0.0`` is the midline and ``+k`` the far band, so ``(0.0, 2.0)`` is the rotation ladder.
    Read under :data:`TARGET_STRETCH`. Signed **towards the target**: a long's levels rise."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, read under :data:`TARGET_R` and capped at the basis -- a target
    beyond the mean is not a mean-reversion target."""

    tp_multiplier: float = 1.0
    """Scales every R target, as on the ported archetypes. Not applied to a stretch level,
    which is already a position rather than a distance."""

    exit_on_invalidation: bool = False
    """Leave at the next open when price closes further outside than the excursion extreme.

    The range broke and held, which is the mean-reversion definition of a failed trade."""

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    order_quantity: int = 4

    bars_required_to_trade: int = 200

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- same concept, same default."""

    fill_limit_on_touch: bool = False
    block_entry_at_session_close: bool = True
    round_targets: bool = True
    """Snap targets onto the tick grid, which NT8 does at submission whatever the script does."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and both market exits. Never applied to a limit target."""

    def __post_init__(self) -> None:
        self._validate_entry()
        self._validate_exit_scheme()
        validate_context_filters(self)

    def _validate_entry(self) -> None:
        """Check the band and the rule that decides which bars signal."""
        if self.band_source not in BAND_SOURCES:
            msg: str = f"unknown band_source {self.band_source}; use one of {sorted(BAND_SOURCES)}"
            raise ValueError(msg)

        bands.validate_period(self.band_period)
        if self.vwap_min_session_bars < 0:
            msg = f"vwap_min_session_bars must be >= 0, got {self.vwap_min_session_bars}"
            raise ValueError(msg)

        if self.entry_std <= 0.0:
            msg = f"entry_std must be > 0, got {self.entry_std}"
            raise ValueError(msg)

        if self.max_entry_std != 0.0 and self.max_entry_std <= self.entry_std:
            msg = (
                f"max_entry_std {self.max_entry_std} must exceed entry_std {self.entry_std} "
                "or be 0 to switch the ceiling off; otherwise no bar can pass both"
            )
            raise ValueError(msg)

        if self.min_bars_outside < 1:
            msg = f"min_bars_outside must be >= 1, got {self.min_bars_outside}"
            raise ValueError(msg)

        if self.entry_trigger not in TRIGGER_MODES:
            msg = f"unknown entry_trigger {self.entry_trigger}; use one of {sorted(TRIGGER_MODES)}"
            raise ValueError(msg)

        if not 0.0 < self.recovery_fraction <= 1.0:
            msg = (
                "recovery_fraction is a share of entry_std and must be in (0, 1], got "
                f"{self.recovery_fraction}; at 0 the close would have to sit exactly on the "
                "basis, which no bar passes"
            )
            raise ValueError(msg)

        if self.band_lag < 0:
            msg = f"band_lag must be >= 0, got {self.band_lag}"
            raise ValueError(msg)

        if not (self.trade_long or self.trade_short):
            msg = "trade_long and trade_short are both off, so nothing can ever be entered"
            raise ValueError(msg)

        self._validate_signal_bar()

    def _validate_signal_bar(self) -> None:
        """Check the two requirements the signal bar's own candle has to meet."""
        if self.signal_shape not in SHAPE_MODES:
            msg: str = f"unknown signal_shape {self.signal_shape}; use one of {sorted(SHAPE_MODES)}"
            raise ValueError(msg)

        if not 0.0 <= self.rejection_close_fraction <= 1.0:
            msg = (
                "rejection_close_fraction is a share of the bar's range and must be in [0, 1], "
                f"got {self.rejection_close_fraction}"
            )
            raise ValueError(msg)

        if self.one_sided_lookback < 1:
            msg = f"one_sided_lookback must be >= 1, got {self.one_sided_lookback}"
            raise ValueError(msg)

        if self.min_one_sided_bars < 0:
            msg = f"min_one_sided_bars must be >= 0, got {self.min_one_sided_bars}"
            raise ValueError(msg)

        if self.min_one_sided_bars > self.one_sided_lookback:
            msg = (
                f"min_one_sided_bars {self.min_one_sided_bars} exceeds one_sided_lookback "
                f"{self.one_sided_lookback}, so no bar can ever pass"
            )
            raise ValueError(msg)

    def _validate_exit_scheme(self) -> None:
        """Check the stop, the targets and the two signal exits against each other."""
        if self.stop_mode not in STOP_MODES:
            msg: str = f"unknown stop_mode {self.stop_mode}; use one of {sorted(STOP_MODES)}"
            raise ValueError(msg)

        if self.target_mode not in TARGET_MODES:
            msg = f"unknown target_mode {self.target_mode}; use one of {sorted(TARGET_MODES)}"
            raise ValueError(msg)

        if self.order_quantity < len(self.target_levels):
            msg = f"order_quantity {self.order_quantity} cannot fill {len(self.target_levels)} legs"
            raise ValueError(msg)

        for name in ("atr_period", "catastrophe_stop_ticks", "swing_lookback"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        if self.min_bracket_dollars < 0.0:
            msg = f"min_bracket_dollars must be >= 0, got {self.min_bracket_dollars}"
            raise ValueError(msg)

        if self.band_stop_std <= 0.0:
            msg = (
                "band_stop_std is how far past entry_std the stop sits and must be > 0, got "
                f"{self.band_stop_std}; at 0 it is the entry threshold itself, which the close "
                "that signalled has already passed"
            )
            raise ValueError(msg)

        validate_max_hold_bars(self.max_hold_bars)

    @property
    def target_levels(self) -> tuple[float, ...]:
        """The per-leg target tuple this combination reads, whichever mode selected it."""
        if self.target_mode == TARGET_STRETCH:
            return self.target_stretch_levels

        return self.target_r_multiples

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- the ported archetypes' split."""
        n: int = len(self.target_levels)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


ORB_ENTRY_BREAKOUT = 0
ORB_ENTRY_FADE = 1
ORB_ENTRY_RETEST = 2
ORB_ENTRY_REJECTION = 3
ORB_ENTRY_MODES = {
    ORB_ENTRY_BREAKOUT: "breakout",
    ORB_ENTRY_FADE: "fade",
    ORB_ENTRY_RETEST: "retest",
    ORB_ENTRY_REJECTION: "rejection",
}
"""Which event at the range the entry order waits for, and therefore which order type it is.

``breakout`` rests a stop beyond the extreme in the direction traded. ``fade`` waits for that
extreme to be broken *against* the direction traded and rests a stop back inside the range, so
a long fade buys the failed break of the low. ``retest`` waits for the break to happen in the
direction traded and then rests a **limit** at the level it broke. ``rejection`` rests a limit
just inside the extreme against the direction traded and waits for nothing, so a long buys the
approach to the low that turns before breaking it. All four read the same levels --
``docs/roadmap.md`` §M28.2 and §M28.6.
"""

ORB_OPPOSITE_EXTREME_ENTRIES = (ORB_ENTRY_FADE, ORB_ENTRY_REJECTION)
ORB_BREAK_ENTRIES = (ORB_ENTRY_FADE, ORB_ENTRY_RETEST)
ORB_LIMIT_ENTRIES = (ORB_ENTRY_RETEST, ORB_ENTRY_REJECTION)
"""The three properties an entry mode is made of, each read as a membership test.

Which extreme the order rests at, whether a break must already have happened, and whether the
order is a stop or a limit. The four modes are four combinations of those rather than four
mechanisms: ``rejection`` is the fade's level, the retest's order type and the breakout's lack
of an arming condition -- ``docs/roadmap.md`` §M28.6.
"""

ORB_STOP_OPPOSITE = 0
ORB_STOP_ATR = 1
ORB_STOP_FRACTION = 2
ORB_STOP_MODES = {
    ORB_STOP_OPPOSITE: "opposite",
    ORB_STOP_ATR: "atr",
    ORB_STOP_FRACTION: "fraction",
}
"""Where the opening range's protective stop goes. ``opposite`` is the range's other extreme,
which makes the stop distance the range width itself; ``atr`` is a multiple of ATR from the
trigger and is the only one floored, because only it is a distance rather than a level;
``fraction`` is :attr:`OpeningRangeParams.stop_range_fraction` of the range width back from the
extreme that was broken, which puts the midpoint stop the literature also uses at ``0.5`` and
reproduces ``opposite`` exactly at ``1.0`` -- ``docs/roadmap.md`` §M28.2.
"""

ORB_TARGET_R = 0
ORB_TARGET_WIDTH = 1
ORB_TARGET_MODES = {ORB_TARGET_R: "r", ORB_TARGET_WIDTH: "width"}
"""Which per-leg target tuple is read. ``r`` is the shared R ladder, comparable with every
other archetype; ``width`` places each leg a multiple of the **range width** past the trigger,
which is the unit the opening range states its own geometry in.
"""

ORB_SCALE_NONE = 0
ORB_SCALE_TARGET = 1
ORB_SCALE_STOP = 2
ORB_SCALE_BOTH = ORB_SCALE_TARGET | ORB_SCALE_STOP
ORB_SCALE_MODES = {
    ORB_SCALE_NONE: "none",
    ORB_SCALE_TARGET: "target",
    ORB_SCALE_STOP: "stop",
    ORB_SCALE_BOTH: "both",
}
"""Which halves of the bracket are denominated in the *trailing* follow-through rather than in
the session's own range width.

A bitmask so the two halves separate: the width a leg's target is a multiple of, the width the
fraction stop is a fraction of, either, or neither. At :data:`ORB_SCALE_NONE` the arithmetic is
byte-for-byte what §M28.1 swept. Above it the width both halves read becomes
``width * trailing follow-through``, which is how far price has lately gone past a range of
that size rather than how wide the range is -- ``docs/roadmap.md`` §M28.9.
"""


@dataclass(slots=True)
class OpeningRangeParams:
    """Rule set for the OpeningRange archetype -- an original, with no NinjaScript.

    The opening-range break, which the literature calls the ORB: measure the high and low of
    :attr:`window_minutes` from :attr:`anchor_minutes` past the session open, then rest a stop
    order at whichever extreme :attr:`direction` names. **One side per combination**, because
    NT8's managed approach refuses the opposite-direction submission and a two-sided range is
    not established as expressible -- ``docs/roadmap.md`` §M28.

    Every rule it implements and the NinjaScript each would be written as:
    ``docs/nt8-fidelity.md`` §M28. The design and what was deliberately left out:
    ``docs/roadmap.md`` §M28.1.
    """

    anchor_minutes: int = sessionrange.CASH_OPEN_MINUTES
    """Minutes past the session open at which the range starts -- the cash open by default.

    :data:`nqbt.sessionrange.ETH_OPEN_MINUTES` is the overnight range's anchor. **The bar size
    must divide it**, so this axis is constrained by the resolution rather than free --
    :func:`nqbt.sessionrange.validate_key`."""

    window_minutes: int = 30
    """How much of the session the range measures. 5, 15 and 30 are what every source means,
    and the bar size must divide this too."""

    direction: float = trades.LONG
    """Which break is taken: :data:`nqbt.trades.LONG` above the range, ``SHORT`` below it.

    A parameter rather than two archetypes, and one side per combination rather than both live
    at once -- ``docs/roadmap.md`` §M28, finding 1."""

    entry_mode: int = ORB_ENTRY_BREAKOUT
    """One of :data:`ORB_ENTRY_MODES` -- which event at the range the order waits for."""

    entry_offset_ticks: int = 1
    """Ticks past the level in the direction traded, read by every mode but
    :data:`ORB_ENTRY_RETEST`.

    Which side of the level that is follows from which extreme the mode rests at: outside the
    range for a breakout, and *inside* it for the two that rest at the opposite extreme. Not
    cosmetic under a stop entry: at ``0`` the trigger sits on the level, and a bar closing
    exactly there cannot submit at all, because NT8 declines a stop entry at or through the
    market -- ``docs/nt8-fidelity.md`` §M18. A limit at the level is legal, so
    :data:`ORB_ENTRY_REJECTION` may sit at ``0``."""

    break_confirm_ticks: int = 0
    """Ticks past the level price must trade before a fade or a retest arms, read under
    :data:`ORB_ENTRY_FADE` and :data:`ORB_ENTRY_RETEST` alone.

    At ``0`` any trade through the level counts as the break. The flag it sets lasts the rest
    of the session, so a fade re-arms after its own stop the way a breakout does.
    :data:`ORB_ENTRY_REJECTION` waits for no break and so reads nothing here."""

    retest_offset_ticks: int = 0
    """Ticks *inside* the broken level the limit sits at, read under
    :data:`ORB_ENTRY_RETEST` alone.

    At ``0`` the limit sits on the level itself. It is a limit rather than a stop, so it fills
    at its price or better and takes no slippage -- ``docs/nt8-fidelity.md`` §M28.2."""

    max_entries_per_session: int = 1
    """How many entries one session may fill, uncapped at ``0``.

    **The default is one-shot**, which is what essentially every published opening-range result
    measures; a level-based trigger re-arms every bar, so uncapped it re-enters after every
    stop -- ``docs/roadmap.md`` §M28, finding 4."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The relative-volume series and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The trend label's averages and its agreement threshold -- see
    :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Sides of a coarse average an entry may be taken on -- see
    :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged on it -- see
    :attr:`DeadCatParams.higher_timeframe_period`."""

    stop_mode: int = ORB_STOP_OPPOSITE
    """One of :data:`ORB_STOP_MODES`."""

    stop_offset_ticks: int = 2
    """Ticks beyond the stop's level under :data:`ORB_STOP_OPPOSITE` and
    :data:`ORB_STOP_FRACTION`, so the stop does not sit exactly on the level it protects."""

    stop_range_fraction: float = 0.5
    """How far back across the range the stop sits under :data:`ORB_STOP_FRACTION`, as a
    fraction of the range width from the extreme that was broken.

    ``0.5`` is the midpoint stop and ``1.0`` is :data:`ORB_STOP_OPPOSITE` exactly, offset
    included -- so the axis contains the mode that already works rather than running beside
    it. Values past ``1.0`` are legal and put the stop outside the range."""

    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    """Stop distance as a multiple of ATR at the signal bar, under :data:`ORB_STOP_ATR`."""

    min_bracket_dollars: float = 0.0
    """Floor on the ATR stop distance in **dollars per contract**, off at ``0``.

    Applies to :data:`ORB_STOP_ATR` alone, because only it is a distance rather than a level --
    see :attr:`EmaCrossoverParams.min_bracket_dollars`."""

    target_mode: int = ORB_TARGET_R
    """One of :data:`ORB_TARGET_MODES`."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, read under :data:`ORB_TARGET_R`. ``nan`` marks a runner, which
    here leaves at the session close."""

    target_width_multiples: tuple[float, ...] = (1.0, float("nan"))
    """Per-leg targets as multiples of the **range width** past the trigger, read under
    :data:`ORB_TARGET_WIDTH`. Not scaled by :attr:`tp_multiplier`, which would be the same
    axis twice."""

    tp_multiplier: float = 1.0
    """Scales every R target, as on the ported archetypes."""

    follow_through_scaling: int = ORB_SCALE_NONE
    """One of :data:`ORB_SCALE_MODES` -- which halves of the bracket the trailing follow-through
    scales. Off by default, which is the geometry every stored OpeningRange row was swept on."""

    follow_through_sessions: int = 60
    """How many prior sessions the trailing follow-through is the median of.

    Read under every :attr:`follow_through_scaling` but :data:`ORB_SCALE_NONE`, where it is
    inert -- so it is a **variant dimension** rather than an axis crossed with the mode."""

    order_quantity: int = 4

    bars_required_to_trade: int = 200

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- same concept, same default."""

    fill_limit_on_touch: bool = False
    block_entry_at_session_close: bool = True

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    round_targets: bool = True
    """Snap targets onto the tick grid, which NT8 does at submission whatever the script does."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the stop entry and both market exits. Never applied to a limit
    target."""

    def __post_init__(self) -> None:
        self._validate_entry()
        self._validate_exit_scheme()
        self._validate_follow_through()
        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)

    def _validate_entry(self) -> None:
        """Check the range and the rule that decides which bars may submit an order."""
        if self.direction not in (trades.LONG, trades.SHORT):
            msg: str = (
                f"direction must be {trades.LONG} (long) or {trades.SHORT} (short), got "
                f"{self.direction}; a range traded both ways at once is not expressible in NT8"
            )
            raise ValueError(msg)

        if self.entry_mode not in ORB_ENTRY_MODES:
            msg = f"unknown entry_mode {self.entry_mode}; use one of {sorted(ORB_ENTRY_MODES)}"
            raise ValueError(msg)

        # Resolution-independent only: whether the bar size can express this range is checked
        # where the bars are, in ``sessionrange.validate_key``.
        sessionrange.validate_key(self.anchor_minutes, self.window_minutes, bar_minutes=1)
        if self.entry_offset_ticks < 0:
            msg = f"entry_offset_ticks must be >= 0, got {self.entry_offset_ticks}"
            raise ValueError(msg)

        if self.break_confirm_ticks < 0:
            msg = f"break_confirm_ticks must be >= 0, got {self.break_confirm_ticks}"
            raise ValueError(msg)

        if self.retest_offset_ticks < 0:
            msg = f"retest_offset_ticks must be >= 0, got {self.retest_offset_ticks}"
            raise ValueError(msg)

        if self.max_entries_per_session < 0:
            msg = f"max_entries_per_session must be >= 0, got {self.max_entries_per_session}"
            raise ValueError(msg)

    def _validate_exit_scheme(self) -> None:
        """Check the stop and the targets against each other."""
        if self.stop_mode not in ORB_STOP_MODES:
            msg: str = f"unknown stop_mode {self.stop_mode}; use one of {sorted(ORB_STOP_MODES)}"
            raise ValueError(msg)

        if self.target_mode not in ORB_TARGET_MODES:
            msg = f"unknown target_mode {self.target_mode}; use one of {sorted(ORB_TARGET_MODES)}"
            raise ValueError(msg)

        if self.entry_mode in ORB_OPPOSITE_EXTREME_ENTRIES and self.stop_mode == ORB_STOP_OPPOSITE:
            msg = (
                "a fade and a rejection enter at the range extreme this stop mode names, so "
                "the stop would sit stop_offset_ticks from the entry and the mode would just "
                f"be the fraction stop at a fraction of zero. Use stop_mode {ORB_STOP_FRACTION} "
                f"(fraction), which measures from that same level, or {ORB_STOP_ATR} (atr)"
            )
            raise ValueError(msg)

        if self.order_quantity < len(self.target_levels):
            msg = f"order_quantity {self.order_quantity} cannot fill {len(self.target_levels)} legs"
            raise ValueError(msg)

        if self.atr_period < 1:
            msg = f"atr_period must be >= 1, got {self.atr_period}"
            raise ValueError(msg)

        if self.stop_offset_ticks < 0:
            msg = f"stop_offset_ticks must be >= 0, got {self.stop_offset_ticks}"
            raise ValueError(msg)

        if self.stop_range_fraction <= 0.0:
            msg = f"stop_range_fraction must be > 0, got {self.stop_range_fraction}"
            raise ValueError(msg)

        if self.min_bracket_dollars < 0.0:
            msg = f"min_bracket_dollars must be >= 0, got {self.min_bracket_dollars}"
            raise ValueError(msg)

    def _validate_follow_through(self) -> None:
        """Check the trailing scale against the two bracket halves it can be applied to.

        Each half is refused under a mode that states its geometry in some other unit, because
        there is then no width for the scale to multiply and the axis would be silently inert.
        """
        if self.follow_through_scaling not in ORB_SCALE_MODES:
            msg: str = (
                f"unknown follow_through_scaling {self.follow_through_scaling}; use one of "
                f"{sorted(ORB_SCALE_MODES)}"
            )
            raise ValueError(msg)

        sessionrange.validate_follow_through_sessions(self.follow_through_sessions)
        if self.follow_through_scaling & ORB_SCALE_TARGET and self.target_mode != ORB_TARGET_WIDTH:
            msg = (
                "follow-through can only scale a target that is a multiple of the range width; "
                f"target_mode {self.target_mode} states its targets in R. Use target_mode "
                f"{ORB_TARGET_WIDTH} (width) or drop {ORB_SCALE_TARGET} from "
                "follow_through_scaling"
            )
            raise ValueError(msg)

        if self.follow_through_scaling & ORB_SCALE_STOP and self.stop_mode != ORB_STOP_FRACTION:
            msg = (
                "follow-through can only scale a stop that is a fraction of the range width; "
                f"stop_mode {self.stop_mode} places a level or an ATR distance. Use stop_mode "
                f"{ORB_STOP_FRACTION} (fraction) or drop {ORB_SCALE_STOP} from "
                "follow_through_scaling"
            )
            raise ValueError(msg)

    @property
    def range_key(self) -> sessionrange.RangeKey:
        """Which of the dataset's session ranges this combination reads."""
        return (self.anchor_minutes, self.window_minutes)

    @property
    def scales_target(self) -> bool:
        """Whether a leg's target is a multiple of the trailing reach rather than of the range."""
        return bool(self.follow_through_scaling & ORB_SCALE_TARGET)

    @property
    def scales_stop(self) -> bool:
        """Whether the fraction stop is a fraction of the trailing reach rather than of the range."""
        return bool(self.follow_through_scaling & ORB_SCALE_STOP)

    @property
    def target_levels(self) -> tuple[float, ...]:
        """The per-leg target tuple this combination reads, whichever mode selected it."""
        if self.target_mode == ORB_TARGET_WIDTH:
            return self.target_width_multiples

        return self.target_r_multiples

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- the ported archetypes' split."""
        n: int = len(self.target_levels)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out


TOUCH_WICK = 0
TOUCH_CLOSE = 1
TOUCH_ANY = 2
TOUCH_MODES = {
    TOUCH_WICK: "wick",
    TOUCH_CLOSE: "close",
    TOUCH_ANY: "any",
}
"""How deep the pullback has to go before the bar that reaches the fast average signals.

:data:`TOUCH_WICK` asks the bar to close back beyond the average it touched, :data:`TOUCH_CLOSE`
asks it to close through it, and :data:`TOUCH_ANY` takes either -- ``docs/nt8-fidelity.md`` §M34.
"""


@dataclass(slots=True)
class EmaPullbackParams:
    """Rule set for the EmaPullback archetype -- an original, with no NinjaScript.

    The two averages EmaCrossover crosses, read for the trend they leave behind rather than for
    the cross: price runs away from the fast average, comes back to it, and the trade is taken
    with the **slow** average as the stop. R is therefore the distance between the two averages.

    Every rule it implements and the NinjaScript each would be written as:
    ``docs/nt8-fidelity.md`` §M34. The design and the alternatives rejected:
    ``docs/findings/m34-ema-pullback-spec.md``.
    """

    fast_period: int = 9
    slow_period: int = 21
    """The average price pulls back to, and the one the stop sits on."""

    fast_kind: str = "ema"
    slow_kind: str = "ema"
    """Which average each is computed as -- one of :data:`nqbt.conditions.MA_KINDS`. The
    archetype's name records what it was built as, not what it is limited to."""

    min_bars_extended: int = 3
    """Completed bars price must have spent entirely beyond the fast average before the touch.

    The run ends on the touch itself, so this is also how long ago the last touch was."""

    touch_mode: int = TOUCH_WICK
    """One of :data:`TOUCH_MODES` -- how deep the pullback has to go to signal."""

    require_slow_intact: bool = True
    """Refuse a signal bar that has already traded through the slow average.

    Off, the stop can be placed at a level the signal bar itself reached."""

    trade_long: bool = True
    trade_short: bool = True
    """Which sides to take. Switching one off is how the two halves get measured separately."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

    regime_filter: int = regime.ALL_REGIMES
    """Market regimes an entry may be taken in -- see :attr:`DeadCatParams.regime_filter`."""

    regime_lookback: int = 20
    regime_consolidating_below: float = 0.3
    regime_directional_above: float = 0.5
    """The efficiency-ratio lookback and its two cuts -- see
    :attr:`DeadCatParams.regime_directional_above`."""

    volume_filter: int = volume.ALL_STATES
    """Volume states an entry may be taken in -- see :attr:`DeadCatParams.volume_filter`."""

    volume_form: int = int(volume.VolumeForm.PER_BAR)
    volume_rolling_bars: int = 30
    volume_baseline_sessions: int = 20
    volume_thin_below: float = 0.7
    volume_heavy_above: float = 1.5
    """The form the ratio is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.volume_heavy_above`."""

    compression_filter: int = compression.ALL_STATES
    """Compression states an entry may be taken in -- see
    :attr:`DeadCatParams.compression_filter`."""

    compression_form: int = int(compression.CompressionForm.BANDWIDTH)
    compression_period: int = 20
    compression_baseline_bars: int = 250
    compression_compressed_below: float = 0.25
    compression_expanded_above: float = 0.75
    """The width measure the rank is taken of, its two windows and its two cuts -- see
    :attr:`DeadCatParams.compression_expanded_above`."""

    trend_filter: int = trend.ALL_TRENDS
    """Trends an entry may be taken in -- see :attr:`DeadCatParams.trend_filter`."""

    trend_fast_period: int = 20
    trend_slow_period: int = 50
    trend_slope_lookback: int = 5
    trend_min_agreement: int = 3
    """The pair the label reads, its slope lookback and how many components must agree --
    see :attr:`DeadCatParams.trend_min_agreement`."""

    higher_timeframe_filter: int = higher_timeframe.ALL_SIDES
    """Which side of a coarse moving average an entry may be taken on --
    see :attr:`DeadCatParams.higher_timeframe_filter`."""

    higher_timeframe_minutes: int = 60
    higher_timeframe_period: int = 50
    """The coarse resolution and the period averaged over it --
    see :attr:`DeadCatParams.higher_timeframe_period`."""

    exit_on_trend_flip: bool = False
    """Close the position at the next bar's open when the two averages cross back.

    The only producer of ``EXIT_SIGNAL`` here, and **off by default**: the strategy as specified
    is the stop and the targets, so the flip exit is an axis rather than part of it."""

    order_quantity: int = 4

    stop_offset_ticks: int = 2
    """Ticks beyond the slow average the stop sits, so it is not exactly on the level.

    ``0`` puts it on the average, which is what ElasticBand's band stop does --
    ``docs/nt8-fidelity.md`` §M34."""

    trail_ma_stop: bool = False
    """Trail the stop along a moving average once the slow one has placed it.

    **Off by default and it must stay off in a sweep's base**, for the reason
    :attr:`EmaCrossoverParams.trail_ma_stop` gives."""

    trail_ma_kind: str = "ema"
    trail_ma_period: int = 50
    """The average the stop follows -- a third grid, independent of the two that define the
    trend."""

    trail_offset_ticks: int = 2
    """Ticks beyond the average the trailing stop sits. Separate from
    :attr:`stop_offset_ticks` for the reason ``ratchet_offset_ticks`` is separate from it in
    the ported archetypes."""

    tp_multiplier: float = 1.0
    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, ``nan`` marking a runner.

    **R is the gap between the two averages**, so these numbers are comparable neither to
    DeadCatBounce's nor to EmaCrossover's at the same values -- ``docs/nt8-fidelity.md`` §M34."""

    bars_required_to_trade: int = 200

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- same concept, same default."""

    fill_limit_on_touch: bool = False
    block_entry_at_session_close: bool = True

    max_hold_bars: int = 0
    """See :attr:`DeadCatParams.max_hold_bars` -- same rule, same default."""

    round_targets: bool = True
    """Snap targets onto the tick grid, which NT8 does at submission whatever the script does."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and both market exits. Never applied to a limit target."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            msg: str = f"order_quantity {self.order_quantity} cannot fill {len(self.target_r_multiples)} legs"
            raise ValueError(msg)

        for name in ("fast_period", "slow_period", "trail_ma_period"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        for gate in ("fast", "slow", "trail_ma"):
            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        if self.min_bars_extended < 1:
            msg = f"min_bars_extended must be >= 1, got {self.min_bars_extended}"
            raise ValueError(msg)

        if self.touch_mode not in TOUCH_MODES:
            msg = f"touch_mode must be one of {sorted(TOUCH_MODES)}, got {self.touch_mode}"
            raise ValueError(msg)

        if self.stop_offset_ticks < 0:
            msg = f"stop_offset_ticks must be >= 0, got {self.stop_offset_ticks}"
            raise ValueError(msg)

        validate_max_hold_bars(self.max_hold_bars)
        validate_context_filters(self)
        if (self.fast_kind, self.fast_period) == (self.slow_kind, self.slow_period):
            msg = (
                f"fast and slow are both {self.fast_kind}({self.fast_period}); one average "
                "never separates from itself, so no bar is ever extended away from it"
            )
            raise ValueError(msg)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

    @property
    def compression_key(self) -> compression.CompressionKey:
        """Which of the dataset's compression series this combination reads."""
        return compression.key(
            self.compression_form,
            self.compression_period,
            self.compression_baseline_bars,
        )

    @property
    def trend_key(self) -> trend.TrendKey:
        """Which of the dataset's trend labels this combination reads."""
        return trend.key(self.trend_fast_period, self.trend_slow_period, self.trend_slope_lookback)

    @property
    def higher_timeframe_key(self) -> higher_timeframe.HigherTimeframeKey:
        """Which of the dataset's higher-timeframe averages this combination reads."""
        return higher_timeframe.key(self.higher_timeframe_minutes, self.higher_timeframe_period)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- the ported archetypes' split."""
        n: int = len(self.target_r_multiples)
        base: int = self.order_quantity // n
        remainder: int = self.order_quantity % n

        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict[str, object]:
        """Flat mapping of every parameter, keyed by field name."""
        out: dict[str, object] = {}
        for f in fields(self):
            value: object = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value

        return out
