"""DeadCatBounce archetype: short an inverted hammer into an established downtrend.

Ported from ``ninjatrader-scripts/Strategies/DeadCatBounce.cs``, which is the source of truth.
The loop here is the stop-market **entry** half; every exit goes through
:mod:`nqbt.sim.bracket`.

Each rule it implements -- the one-bar order lifetime, the ``min(Low[0], Close[0] - 2 ticks)``
trigger, the fill and submittability tests, the ratchet -- and the evidence behind it:
``docs/nt8-fidelity.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray


@njit(cache=True)
def simulate_deadcat(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917 - one argument per NT8 property; #59
    open_: FloatArray,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    signal: BoolArray,
    force_flat: BoolArray,
    leg_quantities: IntArray,
    target_r: FloatArray,
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
    out: FloatArray,
) -> int:
    """Run one bracket archetype over one dataset, writing one row per leg exit.

    Shared by DeadCatBounce and PullBackAndGo: both are a stop order in the trade direction, a
    ratcheting stop, and up to four R-multiple targets with the last leg a runner. ``signal``
    is the precomputed conjunction of every active entry filter, ``force_flat`` marks bars at
    or past the exit-on-session-close cutoff, and ``direction`` is ``+1.0`` long / ``-1.0``
    short.

    ``ratchet_offset_ticks`` is separate from ``stop_offset_ticks`` because the two C#
    strategies genuinely differ there, and ``round_targets`` is a parameter for the same
    reason -- ``docs/nt8-fidelity.md``.

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
        # pending_bar >= 0 matters at i == 0, where the -1 sentinel also equals i - 1;
        # a long would then fill against the zero-initialised trigger.
        elif pending_bar >= 0 and pending_bar == i - 1:
            filled = False
            fill = 0.0
            # force_flat[i], not block_entry_at_session_close: that flag only stops a
            # *new* signal on a force-flat bar, never an order resting from the bar before.
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
                        raw = pending_trigger + direction * risk * target_r[leg] * tp_multiplier
                        leg_target[leg] = round_to_tick(raw, tick_size) if round_targets else raw

                # The entry bar can reach the stop as well, and resolves like any other.
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
            # A stop-market entry must sit strictly beyond the market it is submitted into,
            # which under Calculate.OnBarClose is the signal bar's close.
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

    # The series can stop mid-session, so anything still open is liquidated at the last bar
    # rather than dropped.
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
