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

    Absent from the NinjaScript, and off by default -- :data:`nqbt.timeofday.ALL_PHASES`
    admits every phase and the signal skips the conjunction entirely at that value, so an
    unfiltered run is the run that predates this field.

    A bitmask integer rather than a tuple of phases so it is a **legal sweep axis**: each
    value is one scalar and therefore one combination, which is how "does this rule only
    work at the cash open?" becomes a sweep rather than a set of hand-run backtests. A rule
    that works for one hour reads as unprofitable when averaged over 23."""

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
    :func:`nqbt.sim.bracket.targets_reached_first`."""

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

    Still leaner than :class:`DeadCatParams`, because ``PullBackAndGo.cs`` genuinely has
    fewer properties -- matching the C# text means not inventing configurability it does
    not have:

    - No ``TPMultiplier`` or ``MaxRiskPerTrade``. Neither property exists on the strategy,
      so there is no target scaling and no risk cap to reject a signal with.
    - No ``EntryOffsetTicks``. The trigger is simply ``High[0]`` -- ``entry_bracket`` reaches
      that exactly when ``entry_offset_ticks=0``, so ``run_pullbackandgo`` passes ``0``
      directly rather than exposing a field that would always be zero. This is also what
      exposes the archetype to NT8's stop-entry submittability rule, which DeadCatBounce's
      2-tick cap makes unreachable -- see ``docs/nt8-fidelity.md``.

    **These defaults are not the NinjaScript's, because it does not have any.**
    ``PullBackAndGo.cs`` sets only ``EmaPeriod``, ``SlowSMAPeriod`` and ``FastSMAPeriod`` in
    ``SetDefaults``; ``OrderQuantity`` and all six toggles are left uninitialised, so in
    Strategy Analyzer they present as ``0`` and ``false`` until set by hand -- and an
    ``OrderQuantity`` of 0 places four orders for nothing and trades nothing at all. What
    the values below reproduce is instead **the configuration the M15.5 reconciliation was
    run under**, which is the only combination with a trade list behind it. See
    ``docs/nt8-fidelity.md``.
    """

    ema_period: int = 21
    slow_sma_period: int = 175
    fast_sma_period: int = 60
    order_quantity: int = 4

    use_ema: bool = True
    use_slow_sma: bool = True
    use_fast_sma: bool = True
    use_vwap: bool = False
    """VWAP is off in the reconciled configuration, and deliberately so: nothing has ever
    checked nqbt's VWAP against NT8's ``OrderFlowVWAP``, so switching it on mixes an
    unvalidated indicator into an otherwise validated archetype."""

    require_previous_red: bool = True
    require_new_low: bool = True

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`.
    Absent from the NinjaScript and off by default."""

    bars_required_to_trade: int = 20
    stop_offset_ticks: int = 2
    """Ticks below the signal bar's low for the stop. Hardcoded as ``TickSize * 2`` in the
    NinjaScript, the same as DeadCatBounce's, just on the other side of price."""

    ratchet_lag: int = 1
    """Which bar the trailing stop references at each bar close.

    ``PullBackAndGo.cs`` ratchets to ``Low[1]`` -- the bar *before* the just-closed one,
    lag 1 -- unlike DeadCatBounce's default lag-0 ``High[0]``. Confirmed against the trade
    list: lag 1 leaves 120 disagreeing legs of 1,664 where lags 0, 2 and 3 leave ~1,100."""

    ratchet_offset_ticks: int = 2
    """Ticks beyond the ratchet's reference low, as ``Low[1] - (TickSize * 2)``.

    Was ``0`` when the C# ratcheted to a bare ``Low[1]``. Because ``ratchet_lag=1`` puts the
    first evaluation on the signal bar itself, the offset makes the entry-bar ratchet reduce
    to exactly the initial stop and therefore a no-op, where the bare form tightened by two
    ticks before any bar had closed with the position open."""

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- the same Tier-1 concept, same default."""

    fill_limit_on_touch: bool = False
    """``IsFillLimitOnTouch = false`` in the NinjaScript, same as DeadCatBounce."""

    block_entry_at_session_close: bool = True
    """``IsExitOnSessionCloseStrategy = true`` in the NinjaScript, same as DeadCatBounce."""

    round_targets: bool = True
    """``PullBackAndGo.cs`` never calls ``RoundToTickSize`` and **NT8 snaps the targets
    anyway.** Ported un-rounded on the reasoning that matching the C# text beats assuming
    symmetry with DeadCatBounce; the M15.5 trade list settled it the other way, taking the
    reconciliation from 176 disagreeing legs to 120. The discriminating case is a half-tick
    target nqbt placed at 16504.375 and NT8 filled at 16504.50. The snap is the platform's
    rather than the script's -- no NinjaScript can opt out of the exchange's tick grid."""

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
        """Contracts per leg, with the remainder on the last leg.

        ``baseQuantity = orderQuantity / 4`` with integer division, then
        ``baseQuantity + remainder`` on L4 -- identical to DeadCatBounce's split, so 10
        contracts go 2/2/2/4 rather than 3/3/2/2.
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


STOP_MIN_TICKS = 1.0
"""Fewest ticks a protective stop may sit from the fill, below which the entry is skipped.

A stop at or through the price it protects is not a stop order, which is the same rule NT8
applies to a stop-market *entry* -- see ``docs/nt8-fidelity.md``. It is reachable here and
not in the two ported archetypes, because a market-on-next-open entry has no trigger price
to anchor the stop to and the swing mode's reference can be gapped straight through.
"""


@dataclass(slots=True)
class EmaCrossoverParams:
    """Rule set for the EmaCrossover archetype -- the first original, with no NinjaScript.

    **A known-negative control, not an edge candidate.** MA crossover on 1-minute index
    futures is the most-tested idea in retail futures and is reliably unprofitable at
    realistic costs; if it reads meaningfully better than the random-entry arm the first
    hypothesis is lookahead. See ``docs/roadmap.md`` § M18.

    Three defaults that would otherwise be wrong are fixed explicitly, and each is a field
    here rather than a constant so the alternative stays reachable: the cross uses NT8's
    ``CrossAbove(a, b, n)`` semantics (:attr:`cross_lookback`), the entry is
    market-on-next-open rather than a resting stop, and the stop is an ATR multiple
    (:attr:`use_atr_stop`) because a crossover has no signal wick to anchor to.
    """

    fast_period: int = 9
    slow_period: int = 21
    """EMA periods, NT8-seeded via :func:`nqbt.indicators.nt8_ema`. Equal periods never
    cross and are rejected."""

    cross_lookback: int = 1
    """``n`` in ``CrossAbove(fast, slow, n)`` -- a cross within the last ``n`` bars counts.

    ``1`` is the bar of the cross itself, which is the naive form. Larger values let an
    entry missed at the session's flatten point be taken on a later bar."""

    trade_long: bool = True
    trade_short: bool = True
    """Which sides to take. Both on is the point of the archetype; switching one off is how
    the two halves get measured separately."""

    phase_filter: int = timeofday.ALL_PHASES
    """Session phases an entry may be taken in -- see :attr:`DeadCatParams.phase_filter`.

    The archetype most likely to want it: a crossover fires every ~22 bars, so restricting
    it to one phase still leaves thousands of trades to measure."""

    exit_on_opposite_cross: bool = True
    """Close the position when the regime flips, at the next bar's open.

    This is the ``EXIT_SIGNAL`` exit -- a rule-driven exit with no bracket level of its own,
    which nothing else in the project produces. Off leaves only the stop, the targets and
    the session close."""

    order_quantity: int = 4

    use_atr_stop: bool = True
    """ATR-multiple stop when on, structural swing stop when off.

    Sweeping this is what #37 means by keeping the swing mode as an alternative axis. Note
    ``dead_axes`` can only guard the ATR fields against it: it gates an axis on a toggle
    being *true* somewhere, so :attr:`swing_lookback` cannot be guarded the same way and a
    grid that never turns this off will sweep it for nothing."""

    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    """Stop distance as a multiple of ATR at the signal bar -- the last *completed* bar, so
    the stop cannot read the bar it is placed on."""

    swing_lookback: int = 3
    """Completed bars the swing stop takes its extreme from, the signal bar included."""

    stop_offset_ticks: int = 2
    """Ticks beyond the swing extreme, matching the two ported archetypes. Not applied to
    the ATR stop, whose multiple already sets the distance."""

    tp_multiplier: float = 1.0
    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg targets in R, ``nan`` marking a runner.

    **R means something different here.** It is ``stop - entry``, which with an ATR stop is
    volatility-scaled rather than structure-scaled, so these numbers are not comparable to
    DeadCatBounce's at the same values. Same trap as comparing profit factor across bar
    resolutions."""

    bars_required_to_trade: int = 200

    ambiguity_policy: int = 1
    """See :attr:`DeadCatParams.ambiguity_policy` -- same concept, same default."""

    fill_limit_on_touch: bool = False
    block_entry_at_session_close: bool = True
    round_targets: bool = True
    """Snap targets onto the tick grid. On because NT8 snaps them at submission whatever the
    script does -- the M15.5 trade list settled that for PullBackAndGo."""

    commission_per_contract: float = 0.0
    slippage_ticks: float = 0.0
    """Adverse slippage on the entry and on both market exits -- the stop and the signal
    exit. Never applied to a limit target."""

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
        """Contracts per leg, with the remainder on the last -- the same split as the two
        ported archetypes, so a scale-out is comparable across all three."""
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
