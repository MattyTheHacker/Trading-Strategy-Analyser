"""Parameter sets for the simulated archetypes.

The trade-record layout these produce lives in :mod:`nqbt.trades`, which is shared with
the manual-trade importer and knows nothing about strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from nqbt import timeofday


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
            msg = (
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
            raise ValueError(
                msg,
            )
        for name in ("ema_period", "slow_sma_period", "fast_sma_period"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        timeofday.validate_mask(self.phase_filter)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last: 10 splits 2/2/2/4, not 3/3/2/2."""
        n = len(self.target_r_multiples)
        base = self.order_quantity // n
        remainder = self.order_quantity % n
        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
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
            msg = (
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
            raise ValueError(
                msg,
            )
        for name in ("ema_period", "slow_sma_period", "fast_sma_period"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        timeofday.validate_mask(self.phase_filter)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- DeadCatBounce's split exactly."""
        n = len(self.target_r_multiples)
        base = self.order_quantity // n
        remainder = self.order_quantity % n
        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
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
    """EMA periods, NT8-seeded via :func:`nqbt.indicators.nt8_ema`. Equal periods never
    cross and are rejected."""

    cross_lookback: int = 1
    """``n`` in ``CrossAbove(fast, slow, n)`` -- a cross within the last ``n`` bars counts."""

    trade_long: bool = True
    trade_short: bool = True
    """Which sides to take. Switching one off is how the two halves get measured separately."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`."""

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

    swing_lookback: int = 3
    """Completed bars the swing stop takes its extreme from, the signal bar included."""

    stop_offset_ticks: int = 2
    """Ticks beyond the swing extreme, matching the two ported archetypes. Not applied to
    the ATR stop, whose multiple already sets the distance."""

    tp_multiplier: float = 1.0
    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, ``nan`` marking a runner.

    **R is volatility-scaled here, not structure-scaled**, so these numbers are not comparable
    to DeadCatBounce's at the same values -- ``docs/nt8-fidelity.md`` §M18."""

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
            msg = f"order_quantity {self.order_quantity} cannot fill {len(self.target_r_multiples)} legs"
            raise ValueError(msg)
        for name in ("fast_period", "slow_period", "atr_period", "swing_lookback"):
            if getattr(self, name) < 1:
                msg = f"{name} must be >= 1"
                raise ValueError(msg)
        if self.cross_lookback < 1:
            msg = f"cross_lookback must be >= 1, got {self.cross_lookback}"
            raise ValueError(msg)
        timeofday.validate_mask(self.phase_filter)
        if self.fast_period == self.slow_period:
            msg = (
                f"fast_period and slow_period are both {self.fast_period}; identical "
                "averages never cross, so every combination along that axis trades nothing"
            )
            raise ValueError(msg)

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last -- the ported archetypes' split."""
        n = len(self.target_r_multiples)
        base = self.order_quantity // n
        remainder = self.order_quantity % n
        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value
        return out
