"""DeadCatBounce archetype: short an inverted hammer into an established downtrend.

Ported from ``ninjatrader-scripts/Strategies/DeadCatBounce.cs``, which is the source of truth.
The loop here is the stop-market **entry** half; every exit goes through
:mod:`nqbt.sim.bracket`.

Each rule it implements -- the one-bar order lifetime, the ``min(Low[0], Close[0] - 2 ticks)``
trigger, the fill and submittability tests, the ratchet -- and the evidence behind it:
``docs/nt8-fidelity.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt.sim import bracket
from nqbt.trades import EXIT_END_OF_DATA

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray


class DeadCatRules(NamedTuple):
    """The scalar rule set :func:`simulate_deadcat` reads, one field per NT8 property.

    Shared with PullBackAndGo, which sets the handful of fields the two strategies genuinely
    differ on -- ``ratchet_offset_ticks`` above all, which is separate from
    ``stop_offset_ticks`` for that reason. ``direction`` is ``+1.0`` long / ``-1.0`` short.
    """

    stop_offset_ticks: float
    entry_offset_ticks: float
    tp_multiplier: float
    max_risk_ticks: float
    bars_required: int
    min_reward_risk: float
    ratchet_lag: int
    ratchet_offset_ticks: float
    block_entry_at_session_close: bool
    direction: float


@njit(cache=True)
def simulate_deadcat(  # noqa: C901, PLR0912, PLR0915 - one branch per NT8 rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    leg_quantities: IntArray,
    target_r: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: DeadCatRules,
    out: FloatArray,
) -> int:
    """Run one bracket archetype over one dataset, writing one row per leg exit.

    Shared by DeadCatBounce and PullBackAndGo: both are a stop order in the trade direction, a
    ratcheting stop, and up to four R-multiple targets with the last leg a runner. ``signal``
    is the precomputed conjunction of every active entry filter, and ``bars.force_flat`` marks
    bars at or past the exit-on-session-close cutoff.

    Returns the number of rows written to ``out``; a negative return means ``out`` was too
    small.
    """
    n = bars.close.size
    n_legs = leg_quantities.size
    direction = rules.direction
    slippage = bracket.slippage_points(costs)
    stop_offset = rules.stop_offset_ticks * costs.tick_size
    entry_offset = rules.entry_offset_ticks * costs.tick_size
    ratchet_offset = rules.ratchet_offset_ticks * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1  # bar whose signal placed the order now resting
    pending_trigger = 0.0
    pending_stop = 0.0

    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, direction, False)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        leg_quantities,
    )

    for i in range(n):
        # ---- exits, using the stop and targets set at the close of bar i-1 ----------
        if in_position:
            excursion = bracket.extend_excursion(excursion, bars.high[i], bars.low[i])
            written, in_position = bracket.resolve_brackets(
                out,
                written,
                trade,
                stop,
                legs,
                excursion,
                bars,
                i,
                costs,
                fills,
            )
            if written < 0:
                return -1

        # ---- a resting entry order lives for exactly this one bar -------------------
        # pending_bar >= 0 matters at i == 0, where the -1 sentinel also equals i - 1;
        # a long would then fill against the zero-initialised trigger.
        elif pending_bar >= 0 and pending_bar == i - 1:
            filled = False
            fill = 0.0
            # A force-flat bar is tested for a fill like any other; the session-close handler
            # runs after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            if direction * bars.open_[i] >= direction * pending_trigger:
                fill = bars.open_[i] + direction * slippage  # gapped through the trigger
                filled = True
            else:
                _, touch = bracket.sided(bars.low[i], bars.high[i], direction)
                if direction * touch >= direction * pending_trigger:
                    fill = pending_trigger + direction * slippage
                    filled = True

            if filled:
                trade_id += 1
                risk = direction * (pending_trigger - pending_stop)
                trade = bracket.OpenTrade(
                    trade_id=trade_id,
                    entry_bar=i,
                    entry_price=fill,
                    initial_stop=pending_stop,
                    risk=risk,
                    direction=direction,
                    # Entered intrabar: the position did not exist at this bar's open.
                    filled_at_open=False,
                )
                stop = pending_stop
                excursion = bracket.Excursion(bars.high[i], bars.low[i])
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    if np.isnan(target_r[leg]):
                        legs.target[leg] = np.nan
                    else:
                        raw = pending_trigger + direction * risk * target_r[leg] * rules.tp_multiplier
                        legs.target[leg] = (
                            bracket.round_to_tick(raw, costs.tick_size) if fills.round_targets else raw
                        )

                # The entry bar can reach the stop as well, and resolves like any other.
                written, in_position = bracket.resolve_brackets(
                    out,
                    written,
                    trade,
                    stop,
                    legs,
                    excursion,
                    bars,
                    i,
                    costs,
                    fills,
                )
                if written < 0:
                    return -1

            pending_bar = -1  # filled or missed, and either way it does not rest a second bar

        # ---- close of bar i: ratchet, or look for a new signal ----------------------
        if in_position:
            ref = i - rules.ratchet_lag
            if ref >= 0:
                adverse_ref, _ = bracket.sided(bars.low[ref], bars.high[ref], direction)
                new_stop = adverse_ref - direction * ratchet_offset
                if direction * new_stop > direction * stop:
                    stop = new_stop
        elif (
            i >= rules.bars_required
            and signal[i]
            and not (rules.block_entry_at_session_close and bars.force_flat[i])
        ):
            trigger, candidate_stop, candidate_risk = bracket.entry_bracket(
                bars.high[i],
                bars.low[i],
                bars.close[i],
                entry_offset,
                stop_offset,
                direction,
            )
            # MaxRiskPerTrade is expressed in ticks, not dollars.
            too_risky = candidate_risk > rules.max_risk_ticks * costs.tick_size
            # A stop-market entry must sit strictly beyond the market it is submitted into,
            # which under Calculate.OnBarClose is the signal bar's close.
            submittable = direction * trigger > direction * bars.close[i]
            if (
                candidate_risk > 0.0
                and not too_risky
                and submittable
                and bracket.passes_reward_risk(target_r, rules.min_reward_risk)
            ):
                pending_bar = i
                pending_trigger = trigger
                pending_stop = candidate_stop

    # The series can stop mid-session, so anything still open is liquidated at the last bar
    # rather than dropped.
    if in_position:
        last = n - 1
        exit_fill = bars.close[last] - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = bracket.write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    bracket.LegExit(last, exit_fill, EXIT_END_OF_DATA, False),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1

    return written
