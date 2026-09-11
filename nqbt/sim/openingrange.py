"""OpeningRange archetype: rest an order at the opening range's extreme, one side at a time.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule below is
written down rather than reconciled -- ``docs/nt8-fidelity.md`` §M28 names the NinjaScript each
would become, and ``docs/roadmap.md`` §M28.1 carries the design.

The entry is DeadCatBounce's mechanism -- a stop-market order tested against the next bar's
OHLC -- with the trigger taken from a **level that persists** rather than from the signal bar,
which is what makes the order rest for the whole session instead of one bar
(``docs/roadmap.md`` § "Route 3"). Two things here reach no other archetype: the trigger is a
session-scoped level rather than a per-bar computation, and a per-session entry cap makes the
one-shot form every published result measures expressible at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    ORB_BREAK_ENTRIES,
    ORB_ENTRY_FADE,
    ORB_ENTRY_RETEST,
    ORB_LIMIT_ENTRIES,
    ORB_OPPOSITE_EXTREME_ENTRIES,
    ORB_SCALE_NONE,
    ORB_STOP_ATR,
    ORB_STOP_FRACTION,
    ORB_TARGET_WIDTH,
    STOP_MIN_TICKS,
)

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IndexArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import OpeningRangeParams
    from nqbt.trades import LegMatrix

NO_ATR = np.zeros(0, dtype=np.float64)
"""Stand-in for the ATR array outside :data:`ORB_STOP_ATR`, where the loop never indexes it.

Numba needs an array of the right dtype whether or not the branch reading it runs.
"""


class RangeSeries(NamedTuple):
    """The range this combination trades, in the two shapes it is stored in.

    :attr:`armed` is per bar and :attr:`high`, :attr:`low` are per **session**, read through
    :attr:`session_id` -- one range is a fact about a session rather than a series, and
    holding it that way is what keeps the dataset small however many windows a sweep tries.
    """

    armed: BoolArray
    session_id: IndexArray
    high: FloatArray
    low: FloatArray
    scale: FloatArray
    """Per **session**: what the range width is multiplied by before the bracket reads it.

    All ones where nothing is scaled, so the loop multiplies rather than branches; ``nan`` on a
    session whose trailing follow-through has no history behind it, which is a session the
    geometry cannot be stated for and so is not traded.
    """

    atr: FloatArray
    """Per bar, and empty outside :data:`ORB_STOP_ATR`, where the loop never indexes it."""


class OpeningRangeRules(NamedTuple):
    """The scalar rule set :func:`simulate_openingrange` reads, one field per parameter."""

    direction: float
    entry_mode: int
    entry_offset: float
    break_confirm: float
    retest_offset: float
    stop_mode: int
    stop_offset: float
    stop_range_fraction: float
    atr_stop_multiple: float
    min_bracket_points: float
    target_mode: int
    tp_multiplier: float
    scale_target: bool
    scale_stop: bool
    max_entries_per_session: int
    bars_required: int
    block_entry_at_session_close: bool
    max_hold_bars: int


@njit(cache=True)
def entry_level(range_high: float, range_low: float, rules: OpeningRangeRules) -> float:
    """The range extreme this combination's order rests at.

    A breakout and a retest both work off the extreme in the direction traded -- one waiting
    to go through it, the other to come back to it -- and a fade and a rejection work off the
    extreme against it, one waiting for it to break and the other for it to hold.
    """
    opposite, breakout = bracket.sided(range_low, range_high, rules.direction)
    if rules.entry_mode in ORB_OPPOSITE_EXTREME_ENTRIES:
        return opposite

    return breakout


@njit(cache=True)
def break_confirmed(
    bars: bracket.Bars, i: int, range_high: float, range_low: float, rules: OpeningRangeRules
) -> bool:
    """Whether bar ``i`` breaks the level a fade or a retest is waiting on.

    A fade needs its level broken *against* the direction traded and a retest needs it broken
    *with* it, so one comparison serves both once :func:`bracket.sided` has picked the extreme
    each reads. ``break_confirm`` is a price, and at zero any trade through the level counts.
    """
    direction = rules.direction
    adverse, favourable = bracket.sided(bars.low[i], bars.high[i], direction)
    level = entry_level(range_high, range_low, rules)
    if rules.entry_mode == ORB_ENTRY_FADE:
        return direction * adverse < direction * level - rules.break_confirm

    return direction * favourable > direction * level + rules.break_confirm


@njit(cache=True)
def submittable(trigger: float, close: float, rules: OpeningRangeRules) -> bool:
    """Whether NT8 would accept this order at this bar's close.

    A stop entry has to sit strictly beyond the market it is submitted into --
    ``docs/nt8-fidelity.md`` §M18 -- and a limit entry strictly inside it, which is the same
    refusal read from the other side: a limit at or through the market is marketable, and what
    NT8 does with one is written down rather than reconciled -- ``docs/nt8-fidelity.md`` §M28.2.
    """
    if rules.entry_mode in ORB_LIMIT_ENTRIES:
        return rules.direction * trigger < rules.direction * close

    return rules.direction * trigger > rules.direction * close


@njit(cache=True)
def _stop_entry_fill(
    bars: bracket.Bars, i: int, trigger: float, slippage: float, direction: float
) -> tuple[bool, float]:
    """DeadCatBounce's stop-entry test: a market order once triggered, so a gap fills at the open."""
    if direction * bars.open_[i] >= direction * trigger:
        return True, bars.open_[i] + direction * slippage

    _, touch = bracket.sided(bars.low[i], bars.high[i], direction)
    if direction * touch >= direction * trigger:
        return True, trigger + direction * slippage

    return False, 0.0


@njit(cache=True)
def _limit_entry_fill(
    bars: bracket.Bars, i: int, trigger: float, fills: bracket.FillRules, direction: float
) -> tuple[bool, float]:
    """The limit test the retest and the rejection share, which is the stop's mirror in both halves.

    A limit fills at its price or better, so a bar opening past it fills at the open and the
    trade is *better* than planned rather than worse; and it takes no slippage, which is the
    rule the bracket's targets already follow. The limit rests against the direction traded, so
    :func:`bracket.limit_filled` reads it at ``-direction`` -- price has to trade **through**
    it under ``IsFillLimitOnTouch = false``.
    """
    if direction * bars.open_[i] <= direction * trigger:
        return True, bars.open_[i]

    adverse, _ = bracket.sided(bars.low[i], bars.high[i], direction)
    if bracket.limit_filled(adverse, trigger, fills.fill_limit_on_touch, -direction):
        return True, trigger

    return False, 0.0


@njit(cache=True)
def entry_fill(
    bars: bracket.Bars,
    i: int,
    trigger: float,
    slippage: float,
    fills: bracket.FillRules,
    rules: OpeningRangeRules,
) -> tuple[bool, float]:
    """Whether the resting order fills on bar ``i``, and at what price."""
    if rules.entry_mode in ORB_LIMIT_ENTRIES:
        return _limit_entry_fill(bars, i, trigger, fills, rules.direction)

    return _stop_entry_fill(bars, i, trigger, slippage, rules.direction)


@njit(cache=True)
def range_bracket(
    range_high: float,
    range_low: float,
    stop_scale: float,
    atr: FloatArray,
    signal_bar: int,
    rules: OpeningRangeRules,
) -> tuple[float, float, float]:
    """One session range's order arithmetic: trigger, initial stop, planned risk.

    The trigger sits ``entry_offset`` past the level in the direction traded -- outside the
    range for a breakout, inside it for a fade or a rejection, whose level is the opposite
    extreme -- or ``retest_offset`` back inside the level a retest waits at; the stop goes at
    the range's other extreme, a fraction of the range width back from the level, or an ATR
    multiple back from the trigger. **Everything is measured from the trigger rather than the
    fill**, because the whole bracket is known when the order is submitted -- which is what the
    reconciled DeadCatBounce port does and what a NinjaScript setting its stop and target at
    submission would do.

    ``stop_scale`` is what the fraction stop's range width is multiplied by -- one under every
    mode but the one that denominates it in trailing follow-through.
    """
    direction = rules.direction
    opposite, _ = bracket.sided(range_low, range_high, direction)
    level = entry_level(range_high, range_low, rules)
    if rules.entry_mode == ORB_ENTRY_RETEST:
        trigger = level - direction * rules.retest_offset
    else:
        trigger = level + direction * rules.entry_offset

    if rules.stop_mode == ORB_STOP_ATR:
        distance = bracket.atr_bracket_distance(
            float(atr[signal_bar]),
            rules.atr_stop_multiple,
            rules.min_bracket_points,
        )
        stop = trigger - direction * distance
    elif rules.stop_mode == ORB_STOP_FRACTION:
        width = (range_high - range_low) * stop_scale
        stop = level - direction * (rules.stop_range_fraction * width + rules.stop_offset)
    else:
        stop = opposite - direction * rules.stop_offset

    return trigger, stop, direction * (trigger - stop)


@njit(cache=True)
def _leg_target(level: float, trigger: float, risk: float, width: float, rules: OpeningRangeRules) -> float:
    """One leg's target price, in whichever unit its mode expresses it.

    A width multiple is already a distance, so :attr:`OpeningRangeRules.tp_multiplier` is not
    applied to it -- scaling it as well would be the same axis twice.
    """
    if rules.target_mode == ORB_TARGET_WIDTH:
        return trigger + rules.direction * width * level

    return trigger + rules.direction * risk * level * rules.tp_multiplier


@njit(cache=True)
def simulate_openingrange(  # noqa: C901, PLR0912, PLR0915 - one branch per rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    ranges: RangeSeries,
    leg_quantities: IntArray,
    target_levels: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: OpeningRangeRules,
    out: FloatArray,
) -> int:
    """Run the opening range over one dataset, writing one row per leg exit.

    ``signal`` marks bars that may submit an order -- every bar whose session range is
    complete, narrowed by the context filters. The same trigger is resubmitted on each of
    them, which is a resting order and not an approximation of one: the fill test is the same
    per-bar OHLC comparison either way (``docs/roadmap.md`` § "Route 3").

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = bars.close.size
    n_legs = leg_quantities.size
    direction = rules.direction
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0
    entries_this_session = 0
    broken_this_session = False
    waits_for_a_break = rules.entry_mode in ORB_BREAK_ENTRIES

    in_position = False
    pending_time_exit = False
    pending_bar = -1
    pending_trigger = 0.0
    pending_stop = 0.0
    pending_width = 0.0

    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, direction, False)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        leg_quantities,
    )

    for i in range(n):
        # ---- a new session re-arms the per-session entry cap and forgets the break ---
        if i > 0 and ranges.session_id[i] != ranges.session_id[i - 1]:
            entries_this_session = 0
            broken_this_session = False

        # ---- exits, using the stop and targets set when the order was submitted ------
        if in_position and pending_time_exit:
            # Submitted at the close of bar i-1 and filled at this bar's first price, so the
            # excursion stays where it was.
            written = bracket.flatten_position(
                out,
                written,
                trade,
                legs,
                bracket.LegExit(i, bars.open_[i] - direction * slippage, trades.EXIT_TIME_LIMIT, False),
                excursion,
                costs,
            )
            if written < 0:
                return -1

            in_position = False
        elif in_position:
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

        # ---- the resting entry order, tested against this bar ------------------------
        elif pending_bar >= 0 and pending_bar == i - 1:
            # A force-flat bar is tested for a fill like any other; the session-close handler
            # runs after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            filled, fill = entry_fill(bars, i, pending_trigger, slippage, fills, rules)

            if filled:
                trade_id += 1
                entries_this_session += 1
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
                    if np.isnan(target_levels[leg]):
                        legs.target[leg] = np.nan
                    else:
                        raw = _leg_target(
                            target_levels[leg],
                            pending_trigger,
                            risk,
                            pending_width,
                            rules,
                        )
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

            pending_bar = -1

        pending_time_exit = in_position and bracket.hold_expired(trade.entry_bar, i, rules.max_hold_bars)

        # ---- the break a fade or a retest waits for, remembered for the session ------
        # Updated whatever the submission guards below do, because a break that happens while
        # a position is open still happened.
        session = ranges.session_id[i]
        if waits_for_a_break and not broken_this_session and ranges.armed[i]:
            broken_this_session = break_confirmed(bars, i, ranges.high[session], ranges.low[session], rules)

        # ---- close of bar i: resubmit the order, which is what makes it rest ---------
        if in_position or i < rules.bars_required or not signal[i]:
            continue

        # Not inherited from ``signal``, which the random-entry arm substitutes: a drawn bar
        # can land in a session whose range never completed, and that has no level to trade.
        if not ranges.armed[i]:
            continue

        if waits_for_a_break and not broken_this_session:
            continue

        if rules.max_entries_per_session > 0 and entries_this_session >= rules.max_entries_per_session:
            continue

        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue

        # A session with too little history behind it to state the trailing scale has no
        # geometry rather than an unscaled one; at ORB_SCALE_NONE the scale is one everywhere.
        scale = ranges.scale[session]
        if not np.isfinite(scale):
            continue

        stop_scale = scale if rules.scale_stop else 1.0
        target_scale = scale if rules.scale_target else 1.0
        range_high = ranges.high[session]
        range_low = ranges.low[session]
        trigger, candidate_stop, candidate_risk = range_bracket(
            range_high,
            range_low,
            stop_scale,
            ranges.atr,
            i,
            rules,
        )
        if candidate_risk < min_risk or not submittable(trigger, bars.close[i], rules):
            continue

        pending_bar = i
        pending_trigger = trigger
        pending_stop = candidate_stop
        pending_width = (range_high - range_low) * target_scale

    # The series can stop mid-session, so anything still open is liquidated at the last bar.
    if in_position:
        last = n - 1
        written = bracket.flatten_position(
            out,
            written,
            trade,
            legs,
            bracket.LegExit(last, bars.close[last] - direction * slippage, trades.EXIT_END_OF_DATA, False),
            excursion,
            costs,
        )
        if written < 0:
            return -1

    return written


def openingrange_signal(data: Dataset, params: OpeningRangeParams) -> BoolArray:
    """Bars that may submit an entry order: those whose session range is complete.

    Dense by construction rather than by oversight -- the trigger is a level that persists, so
    a bar not resubmitting the order would be a bar the order was *not* resting on. What that
    costs the matched random-entry null: ``docs/roadmap.md`` §M28.1.
    """
    signal: BoolArray = data.range_armed(params.range_key).copy()

    return filters.apply_context_filters(signal, data, params)


def entry_bound(data: Dataset, params: OpeningRangeParams, signal: BoolArray) -> int:
    """How many entries this combination can possibly fill -- what the output is sized from.

    ``allocate_output``'s usual "one row per leg per signal" bound is far too loose here,
    because the signal is dense: capped, the real bound is one entry per session per allowed
    entry, which is three orders of magnitude smaller.
    """
    live: int = int(signal.sum())
    if params.max_entries_per_session <= 0:
        return live

    sessions: int = int(data.range_session_id().max()) + 1 if len(data) else 0

    return min(live, sessions * params.max_entries_per_session)


def follow_through_scale(data: Dataset, params: OpeningRangeParams) -> FloatArray:
    """Per session: what this combination multiplies the range width by, before the bracket.

    Ones at :data:`ORB_SCALE_NONE`, so the loop is one multiplication rather than a branch and
    the unscaled arithmetic is bit-for-bit what it was -- ``docs/roadmap.md`` §M28.9.
    """
    sessions: int = int(data.range_session_id().max()) + 1 if len(data) else 0
    if params.follow_through_scaling == ORB_SCALE_NONE:
        return np.ones(sessions, dtype=np.float64)

    return data.range_follow_through_scale(params.range_key, params.follow_through_sessions)


def openingrange_legs(
    data: Dataset,
    params: OpeningRangeParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the
    direction is a parameter rather than a series, so a drawn bar is taken on the same side.
    """
    key = params.range_key
    signal = openingrange_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    levels: FloatArray = np.asarray(params.target_levels, dtype=np.float64)
    atr: FloatArray = data.atr_values(params.atr_period) if params.stop_mode == ORB_STOP_ATR else NO_ATR
    scale: FloatArray = follow_through_scale(data, params)
    out: FloatArray = bracket.allocate_output(entry_bound(data, params, signal), quantities.size)

    count: int = simulate_openingrange(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        RangeSeries(
            armed=data.range_armed(key),
            session_id=data.range_session_id(),
            high=data.range_high(key),
            low=data.range_low(key),
            scale=scale,
            atr=atr,
        ),
        quantities,
        levels,
        bracket.Costs(
            tick_size=instrument.tick_size,
            point_value=instrument.point_value,
            commission_per_contract=params.commission_per_contract,
            slippage_ticks=params.slippage_ticks,
        ),
        bracket.FillRules(
            fill_limit_on_touch=params.fill_limit_on_touch,
            ambiguity_policy=params.ambiguity_policy,
            round_targets=params.round_targets,
        ),
        OpeningRangeRules(
            direction=params.direction,
            entry_mode=params.entry_mode,
            entry_offset=params.entry_offset_ticks * instrument.tick_size,
            break_confirm=params.break_confirm_ticks * instrument.tick_size,
            retest_offset=params.retest_offset_ticks * instrument.tick_size,
            stop_mode=params.stop_mode,
            stop_offset=params.stop_offset_ticks * instrument.tick_size,
            stop_range_fraction=params.stop_range_fraction,
            atr_stop_multiple=params.atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(params.min_bracket_dollars),
            target_mode=params.target_mode,
            tp_multiplier=params.tp_multiplier,
            scale_target=params.scales_target,
            scale_stop=params.scales_stop,
            max_entries_per_session=params.max_entries_per_session,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
            max_hold_bars=params.max_hold_bars,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; entry_bound's per-session cap was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_openingrange(
    data: Dataset,
    params: OpeningRangeParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = openingrange_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
