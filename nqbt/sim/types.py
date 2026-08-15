"""Parameter sets for the simulated archetypes.

The trade-record layout these produce lives in :mod:`nqbt.trades`, which is shared with
the manual-trade importer and knows nothing about strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


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

    tp_multiplier: float = 1.0
    """Scales every leg's target. ``TPMultiplier`` in the NinjaScript."""

    max_risk_ticks: int = 250
    """Reject the signal when ``stop - trigger`` exceeds this many **ticks**.

    ``MaxRiskPerTrade`` is compared against ``risk > maxRiskPerTrade * TickSize``, so it is
    a tick count rather than a dollar amount -- 250 ticks is 62.5 MNQ points, not $250."""

    bars_required_to_trade: int = 200
    stop_offset_ticks: int = 2
    """Ticks beyond the signal bar's high for the stop. Hardcoded as 2 in the NinjaScript."""

    entry_offset_ticks: int = 2
    """Ticks below the close used to cap the entry trigger.

    The trigger is ``min(Low[0], Close[0] - 2 ticks)``. An inverted hammer closes near its
    low by construction, so the close-based term usually wins and drags the trigger below
    the bar's low, which makes the fill meaningfully harder to get."""

    ambiguity_policy: int = 1
    """How a bar holding both the stop and a target is resolved.

    ``1`` fills whichever level sits nearer the bar's open, which is what NT8 does and is
    therefore the default -- it is the only setting that keeps Tier 1 and Tier 2 aligned.
    ``0`` assumes the worst case, the stop taking the whole position, which is *more*
    pessimistic than NT8 rather than equal to it.

    Worth sweeping as an axis: the spread between the two is a direct measure of how much
    of a candidate's edge rests on an assumption the bar data cannot settle. See
    :func:`nqbt.sim.deadcat._targets_reached_first`."""

    fill_limit_on_touch: bool = False
    """Whether a profit target fills when price merely reaches it.

    ``IsFillLimitOnTouch = false`` in the NinjaScript, so the default is that a limit must
    be traded *through* to fill. Leaving this on inflates results: it hands you every
    target the market touched to the tick and then reversed away from."""

    block_entry_at_session_close: bool = True
    """Whether a signal on the session's final bar is skipped."""

    ratchet_lag: int = 0
    """Which bar's high the trailing stop references at each bar close.

    ``0`` reads the just-closed bar's high -- ``High[0]``, what the NinjaScript does.
    ``1`` reads the bar before it, which an earlier revision of the strategy used and which
    holds trades roughly a third longer. Left exposed because the two behave like genuinely
    different strategies and the comparison is worth sweeping."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg profit targets in R. ``nan`` marks a runner with no target -- S4 in the
    NinjaScript, which exits only via the trailing stop or the session close."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on market and stop orders. Never applied to limit targets,
    matching NT8, where the ``Slippage`` property does not affect limit fills."""

    # -- options the spec asks for that the NinjaScript does not implement --
    # Kept off by default so the port stays faithful until validated against NT8.
    min_reward_risk: float = 0.0
    """Pre-trade gate: skip the signal unless the furthest target clears this ratio."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            raise ValueError(
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
        for name in ("ema_period", "slow_sma_period", "fast_sma_period"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last leg.

        ``baseQuantity = orderQuantity / 4`` with integer division, then
        ``baseQuantity + remainder`` on S4 -- so 10 contracts split 2/2/2/4, not 3/3/2/2.
        """
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

    Ported for M15.4 as the validation case for a bidirectional simulator: the same stop
    order, ratcheting stop and R-multiple bracket as DeadCatBounce, reflected to the long
    side, with C# to check the Python against once M15.5 reconciles it.

    Deliberately **leaner than** :class:`DeadCatParams`, not just its mirror, because
    ``PullBackAndGo.cs`` genuinely has fewer properties -- matching the C# text means not
    inventing configurability it does not have:

    - No ``Use*`` toggles. All four trend filters (EMA, slow SMA, fast SMA, VWAP) are
      unconditional in the C#'s single combined ``if``, unlike DeadCatBounce's four
      independent, individually-switchable ``if`` statements.
    - No ``OrderQuantity``. Every ``EnterLongStopMarket`` call omits the quantity argument,
      so each of the four legs trades NT8's default of one contract -- fixed, not swept.
    - No ``TPMultiplier`` or ``MaxRiskPerTrade``. Neither property exists on the strategy,
      so there is no target scaling and no risk cap to reject a signal with.
    - No ``EntryOffsetTicks``. The trigger is simply ``High[0]`` -- ``entry_bracket`` reaches
      that exactly when ``entry_offset_ticks=0``, so ``run_pullbackandgo`` passes ``0``
      directly rather than exposing a field that would always be zero.
    """

    ema_period: int = 21
    slow_sma_period: int = 175
    fast_sma_period: int = 60

    bars_required_to_trade: int = 20
    stop_offset_ticks: int = 2
    """Ticks below the signal bar's low for the stop. Hardcoded as ``TickSize * 2`` in the
    NinjaScript, the same as DeadCatBounce's, just on the other side of price."""

    ratchet_lag: int = 1
    """Which bar the trailing stop references at each bar close.

    ``PullBackAndGo.cs`` ratchets to a bare ``Low[1]`` -- the bar *before* the just-closed
    one, lag 1 -- unlike DeadCatBounce's default lag-0 ``High[0]``. Also unlike
    DeadCatBounce, the ratchet reapplies no offset at all; ``run_pullbackandgo`` passes
    ``ratchet_offset_ticks=0`` to :func:`nqbt.sim.deadcat.simulate_deadcat` for exactly
    this reason, not as a sweepable field, since the C# has no property for it either."""

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- the same Tier-1 concept, same default."""

    fill_limit_on_touch: bool = False
    """``IsFillLimitOnTouch = false`` in the NinjaScript, same as DeadCatBounce."""

    block_entry_at_session_close: bool = True
    """``IsExitOnSessionCloseStrategy = true`` in the NinjaScript, same as DeadCatBounce."""

    round_targets: bool = False
    """``PullBackAndGo.cs`` never calls ``RoundToTickSize`` on its profit targets, unlike
    DeadCatBounce.cs. Ported as written rather than assumed symmetric -- see
    :func:`nqbt.sim.deadcat.simulate_deadcat`'s ``round_targets`` docstring for why this is
    a live question for M15.5's NT8 reconciliation, not a settled one."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """L1/L2/L3 at 1R/1.5R/2R; L4 is the runner with no target, matching the NinjaScript."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on market and stop orders. Never applied to limit targets."""

    def __post_init__(self) -> None:
        for name in ("ema_period", "slow_sma_period", "fast_sma_period"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """One contract per leg -- ``EnterLongStopMarket`` never specifies a quantity."""
        return (1,) * len(self.target_r_multiples)

    def as_dict(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value
        return out
