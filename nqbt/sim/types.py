"""Parameter sets for the simulated archetypes.

The trade-record layout these produce lives in :mod:`nqbt.trades`, which is shared with
the manual-trade importer and knows nothing about strategies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Protocol, override

from nqbt import bands, conditions, higher_timeframe, regime, timeofday, trend, volume


class ContextFilterParams(Protocol):
    """The five context filters and every field behind them, as one shape.

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
    trend.validate_mask(params.trend_filter)
    trend.validate_periods(params.trend_fast_period, params.trend_slow_period)
    trend.validate_slope_lookback(params.trend_slope_lookback)
    trend.validate_min_agreement(params.trend_min_agreement)
    higher_timeframe.validate_mask(params.higher_timeframe_filter)
    higher_timeframe.validate_minutes(params.higher_timeframe_minutes)
    higher_timeframe.validate_period(params.higher_timeframe_period)


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
        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

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
        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

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
    round_targets: bool = True
    """Snap targets onto the tick grid, which NT8 does at submission whatever the script does."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and both market exits. Never applied to a limit target."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            msg: str = f"order_quantity {self.order_quantity} cannot fill {len(self.target_r_multiples)} legs"
            raise ValueError(msg)

        for name in ("fast_period", "slow_period", "atr_period", "swing_lookback"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        for gate in ("fast", "slow"):
            conditions.ma_key(getattr(self, f"{gate}_kind"), getattr(self, f"{gate}_period"))
        if self.cross_lookback < 1:
            msg = f"cross_lookback must be >= 1, got {self.cross_lookback}"
            raise ValueError(msg)

        if self.min_bracket_dollars < 0.0:
            msg = f"min_bracket_dollars must be >= 0, got {self.min_bracket_dollars}"
            raise ValueError(msg)

        validate_context_filters(self)
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

        validate_context_filters(self)

    @property
    def volume_key(self) -> volume.VolumeKey:
        """Which of the dataset's volume series this combination reads."""
        return volume.key(self.volume_form, self.volume_rolling_bars, self.volume_baseline_sessions)

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
STOP_MODES = {
    STOP_ATR: "atr",
    STOP_EXCURSION: "excursion",
    STOP_CATASTROPHE: "catastrophe",
    STOP_SWING: "swing",
}
"""Where the elastic band's protective stop goes, one per exit scheme -- ``docs/roadmap.md``
§M26, "Three exit schemes". ``atr`` is a distance off the fill and the only floored one;
``excursion`` is the adverse extreme of the bars that were outside the band; ``catastrophe``
is :attr:`ElasticBandParams.catastrophe_stop_ticks` and is an account rule rather than a
strategy stop; ``swing`` is the adverse extreme of a fixed number of bars, which at
``swing_lookback = 1`` is the signal candle alone and is the tightest stop the archetype can
express.
"""

TARGET_STRETCH = 0
TARGET_R = 1
TARGET_MODES = {TARGET_STRETCH: "stretch", TARGET_R: "r"}
"""Which per-leg target tuple is read. ``stretch`` places every leg on a band level and is the
mean-reversion geometry; ``r`` uses the shared R ladder and is comparable with EmaCrossover.
"""


@dataclass(slots=True)
class ElasticBandParams:
    """Rule set for the ElasticBand archetype -- an original, with no NinjaScript.

    The first mean-reversion archetype: fade a close far enough outside a Bollinger band and
    target the middle. Every rule it implements, and the NinjaScript each would be written as:
    ``docs/nt8-fidelity.md`` §M26. The design and the three exit schemes: ``docs/roadmap.md``
    §M26.
    """

    band_period: int = 20
    """Period of both the basis and the standard deviation, which are one window."""

    entry_std: float = 2.0
    """How far outside the basis a close must sit to signal, in standard deviations."""

    max_entry_std: float = 0.0
    """Ceiling on that extension, off at ``0``.

    Beyond some point the move is a trend breaking out rather than a band being stretched, so
    the entry region is bounded rather than one-sided -- ``docs/roadmap.md`` §M26."""

    min_bars_outside: int = 1
    """Consecutive bars that must have been outside before an entry, the signal bar included."""

    band_lag: int = 0
    """Bars back the band is read from: ``0`` is the signal bar's own, ``1`` the previous one.

    At ``0`` the band contains the bar being tested, which damps the signal rather than
    looking ahead -- ``docs/roadmap.md`` §M26."""

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
    """Time stop in bars, off at ``0``, on top of the session flatten every archetype has."""

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
        bands.validate_period(self.band_period)
        if self.entry_std <= 0.0:
            msg: str = f"entry_std must be > 0, got {self.entry_std}"
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

        if self.band_lag < 0:
            msg = f"band_lag must be >= 0, got {self.band_lag}"
            raise ValueError(msg)

        if not (self.trade_long or self.trade_short):
            msg = "trade_long and trade_short are both off, so nothing can ever be entered"
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

        if self.max_hold_bars < 0:
            msg = f"max_hold_bars must be >= 0, got {self.max_hold_bars}"
            raise ValueError(msg)

        # Both write EXIT_SIGNAL, so a log carrying both cannot say which fired --
        # ``docs/nt8-fidelity.md`` §M26.
        if self.exit_on_invalidation and self.max_hold_bars > 0:
            msg = (
                "exit_on_invalidation and max_hold_bars both write EXIT_SIGNAL, so a trade "
                "log with both on cannot say which exit fired; enable one per grid"
            )
            raise ValueError(msg)

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
