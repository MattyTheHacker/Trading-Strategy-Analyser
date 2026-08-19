"""DeadCatBounce archetype: short an inverted hammer into an established downtrend.

Ported from ``ninjatrader-scripts/Strategies/DeadCatBounce.cs``, which is the source of
truth. Where the C# is ambiguous the resolution is recorded below rather than guessed at
silently, because these choices move trade counts far more than any parameter does.

**Order lifetime.** ``EnterShortStopMarket`` under NT8's managed approach is *not* GTC
despite ``TimeInForce.Gtc`` on the strategy: an unfilled entry is cancelled at the close of
the following bar. A signal at the close of bar ``t`` therefore places an order live for
bar ``t+1`` only.

**Trigger.** ``min(Low[0], Close[0] - 2 ticks)``, not simply the bar's low. An inverted
hammer closes near its low by construction, so the close-based term binds on about a third
of signals and drags the trigger 1-2 ticks under the low, which is enough to turn a
marginal fill into no fill at all.

**Fill.** On bar ``t+1``, a gap through the trigger fills at the open; otherwise a trade
down to the trigger fills at the trigger. No touch, no fill, order gone.

**Exit precedence.** Bar-close OHLC cannot say whether a bar hit the stop or a target
first, so ``ambiguity_policy`` decides. NT8 fills whichever level sits nearer the bar's
open, verified against a real trade list where that rule called all seven ambiguous bars
correctly. The alternative is a blanket worst case, which is more pessimistic than NT8 and
therefore breaks Tier 1 / Tier 2 parity in the safe direction. Either way the bar is
flagged ``ambiguous_bar`` so the cost of the assumption stays measurable.

**Limit fills.** ``IsFillLimitOnTouch = false`` in the NinjaScript, so a profit target
needs price to trade *through* it, not merely reach it. Every disagreement with NT8 about
a target fill came from a bar whose low equalled the target to the tick.

**Ratchet.** At the close of each bar in a position the stop becomes
``High[0] + 2 ticks`` -- the just-closed bar's high -- if that is tighter, never looser,
shared across all four legs. The stop set at the close of bar ``i`` is live during bar
``i+1``. ``ratchet_lag`` exposes the older ``High[1]`` variant, which holds trades about a
third longer.

**Targets.** Each leg's target is rounded onto the tick grid, as ``RoundToTickSize`` does
in the NinjaScript: a 1.5x multiple of an odd tick count otherwise lands on a half tick.

**Same-bar stop-out.** A stop can fire on the bar the entry filled: the entry is at the
bar's low and the stop above it, so a wide enough bar reaches both.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from nqbt.sim.bracket import (
    entry_bracket,
    passes_reward_risk,
    resolve_brackets,
    round_to_tick,
    sided,
    write_leg,
)
from nqbt.trades import EXIT_END_OF_DATA


@njit(cache=True)
def simulate_deadcat(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signal: np.ndarray,
    force_flat: np.ndarray,
    leg_quantities: np.ndarray,
    target_r: np.ndarray,
    tick_size: float,
    point_value: float,
    stop_offset_ticks: float,
    entry_offset_ticks: float,
    tp_multiplier: float,
    max_risk_ticks: float,
    commission_per_contract: float,
    slippage_ticks: float,
    bars_required: int,
    min_reward_risk: float,
    ratchet_lag: int,
    ratchet_offset_ticks: float,
    block_entry_at_session_close: bool,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    direction: float,
    round_targets: bool,
    out: np.ndarray,
) -> int:
    """Run one bracket archetype over one dataset, writing one row per leg exit.

    Shared by DeadCatBounce and PullBackAndGo.cs -- both are a stop order in the trade
    direction, a ratcheting stop, and up to four R-multiple targets with the last leg a
    runner. ``signal`` is the precomputed conjunction of every active entry filter, and
    ``force_flat`` marks bars at or past the exit-on-session-close cutoff. ``direction`` is
    ``+1.0`` long / ``-1.0`` short (see ``nqbt.trades.LONG``/``SHORT``); DeadCatBounce
    always calls this with ``SHORT``, since the NinjaScript has no long variant.

    ``ratchet_offset_ticks`` is separate from ``stop_offset_ticks`` because the two C#
    strategies genuinely differ here, not just in direction: ``DeadCatBounce.cs`` ratchets
    to ``High[0] + 2 ticks`` every bar, reapplying the same offset used for the initial
    stop, while ``PullBackAndGo.cs`` ratchets to a bare ``Low[1]`` with no offset at all.
    ``run_deadcat`` passes ``stop_offset_ticks`` here to reproduce its behaviour exactly;
    ``run_pullbackandgo`` passes ``0``.

    ``round_targets`` exists for the same reason: ``DeadCatBounce.cs`` rounds every target
    onto the tick grid via ``RoundToTickSize``, but ``PullBackAndGo.cs`` does not call it at
    all, so its targets are ported un-rounded even though that can land on a half tick --
    matching the C# text rather than assuming symmetry. Whether NT8 silently snaps such a
    price at submission is a live-platform question M15.5's reconciliation has to settle,
    not something to guess at here.

    Returns the number of rows written to ``out``; a negative return means ``out`` was too
    small.
    """
    n = close.size
    n_legs = leg_quantities.size
    slippage = slippage_ticks * tick_size
    stop_offset = stop_offset_ticks * tick_size
    entry_offset = entry_offset_ticks * tick_size
    ratchet_offset = ratchet_offset_ticks * tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1  # bar whose signal placed the order now resting
    pending_trigger = 0.0
    pending_stop = 0.0

    entry_price = 0.0
    entry_bar = 0
    stop = 0.0
    risk = 0.0
    initial_stop = 0.0
    run_high = 0.0
    run_low = 0.0

    leg_open = np.zeros(n_legs, dtype=np.bool_)
    leg_target = np.zeros(n_legs, dtype=np.float64)

    for i in range(n):
        # ---- exits, using the stop and targets set at the close of bar i-1 ----------
        if in_position:
            run_high = max(run_high, high[i])
            run_low = min(run_low, low[i])

            written, in_position = resolve_brackets(
                out,
                written,
                trade_id,
                entry_bar,
                i,
                entry_price,
                initial_stop,
                stop,
                risk,
                leg_open,
                leg_target,
                leg_quantities,
                run_high,
                run_low,
                open_[i],
                high[i],
                low[i],
                close[i],
                force_flat[i],
                slippage,
                point_value,
                commission_per_contract,
                fill_limit_on_touch,
                ambiguity_policy,
                direction,
                True,  # held since this bar's open, so a gap through the stop fills at it
            )
            if written < 0:
                return -1

        # ---- a resting entry order lives for exactly this one bar -------------------
        # pending_bar >= 0 matters at i == 0: the sentinel -1 would otherwise equal
        # i - 1 there too. The short-only loop never noticed, because a zero-initialised
        # pending_trigger makes `open_[i] <= pending_trigger` false for any real price and
        # the touch test below is never reached; direction generalises the comparison to
        # `direction * open_[i] >= direction * pending_trigger`, which a long's positive
        # price satisfies against that same zero trigger immediately.
        elif pending_bar >= 0 and pending_bar == i - 1:
            filled = False
            fill = 0.0
            # A bar at or past the flatten cutoff cancels a resting order rather than
            # letting it fill: no new position may open once the account rules require
            # being flat. force_flat[i] here, not block_entry_at_session_close -- that
            # flag only stops a *new* signal being accepted on a force-flat bar, and does
            # not reach an order that rested from the bar before.
            if not force_flat[i]:
                if direction * open_[i] >= direction * pending_trigger:
                    fill = open_[i] + direction * slippage  # gapped through the trigger
                    filled = True
                else:
                    _, touch = sided(low[i], high[i], direction)
                    if direction * touch >= direction * pending_trigger:
                        fill = pending_trigger + direction * slippage
                        filled = True

            if filled:
                trade_id += 1
                entry_price = fill
                entry_bar = i
                initial_stop = pending_stop
                stop = pending_stop
                risk = direction * (pending_trigger - pending_stop)
                run_high = high[i]
                run_low = low[i]
                for leg in range(n_legs):
                    leg_open[leg] = True
                    if np.isnan(target_r[leg]):
                        leg_target[leg] = np.nan
                    else:
                        # RoundToTickSize in DeadCatBounce.cs: a 1.5x multiple of an odd
                        # tick count lands on a half tick, which no exchange accepts.
                        # PullBackAndGo.cs never calls it -- see round_targets in the
                        # docstring -- so this must stay conditional, not assumed.
                        raw = pending_trigger + direction * risk * target_r[leg] * tp_multiplier
                        leg_target[leg] = round_to_tick(raw, tick_size) if round_targets else raw

                # The entry bar can reach the stop as well: entry sits at the signal
                # bar's low, the stop above the signal bar's high. Same resolution as any
                # other bar -- the `leg_open` guards inside are simply no-ops here, since
                # every leg was opened a few lines above.
                written, in_position = resolve_brackets(
                    out,
                    written,
                    trade_id,
                    entry_bar,
                    i,
                    entry_price,
                    initial_stop,
                    stop,
                    risk,
                    leg_open,
                    leg_target,
                    leg_quantities,
                    run_high,
                    run_low,
                    open_[i],
                    high[i],
                    low[i],
                    close[i],
                    force_flat[i],
                    slippage,
                    point_value,
                    commission_per_contract,
                    fill_limit_on_touch,
                    ambiguity_policy,
                    direction,
                    False,  # entered intrabar: the position did not exist at the open
                )
                if written < 0:
                    return -1

            pending_bar = -1  # filled, cancelled at the flatten point, or just missed -- gone

        # ---- close of bar i: ratchet, or look for a new signal ----------------------
        if in_position:
            ref = i - ratchet_lag
            if ref >= 0:
                adverse_ref, _ = sided(low[ref], high[ref], direction)
                new_stop = adverse_ref - direction * ratchet_offset
                if direction * new_stop > direction * stop:
                    stop = new_stop
        elif i >= bars_required and signal[i] and not (block_entry_at_session_close and force_flat[i]):
            trigger, candidate_stop, candidate_risk = entry_bracket(
                high[i],
                low[i],
                close[i],
                entry_offset,
                stop_offset,
                direction,
            )
            # MaxRiskPerTrade is expressed in ticks, not dollars.
            too_risky = candidate_risk > max_risk_ticks * tick_size
            # A stop-market entry must sit strictly beyond the market it is submitted
            # into -- a buy stop above it, a sell stop below it -- or it is not a stop
            # order at all and the platform will not accept it. The market at submission
            # is the signal bar's close, this being Calculate.OnBarClose.
            submittable = direction * trigger > direction * close[i]
            if (
                candidate_risk > 0.0
                and not too_risky
                and submittable
                and passes_reward_risk(target_r, min_reward_risk)
            ):
                pending_bar = i
                pending_trigger = trigger
                pending_stop = candidate_stop

    # The series can stop mid-session, so anything still open is liquidated at the last
    # bar rather than dropped -- an untracked open position would silently lose its P&L.
    if in_position:
        last = n - 1
        exit_fill = close[last] - direction * slippage
        for leg in range(n_legs):
            if leg_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    last,
                    entry_price,
                    exit_fill,
                    initial_stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    EXIT_END_OF_DATA,
                    risk,
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    False,
                    direction,
                )
                if written < 0:
                    return -1

    return written
