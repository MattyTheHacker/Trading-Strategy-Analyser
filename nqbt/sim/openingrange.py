"""OpeningRange archetype: rest a stop order at the opening range's extreme, one side at a time.

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
from nqbt.sim.types import ORB_STOP_ATR, ORB_TARGET_WIDTH, STOP_MIN_TICKS

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
    atr: FloatArray
    """Per bar, and empty outside :data:`ORB_STOP_ATR`, where the loop never indexes it."""


class OpeningRangeRules(NamedTuple):
    """The scalar rule set :func:`simulate_openingrange` reads, one field per parameter."""

    direction: float
    entry_offset: float
    stop_mode: int
    stop_offset: float
    atr_stop_multiple: float
    min_bracket_points: float
    target_mode: int
    tp_multiplier: float
    max_entries_per_session: int
    bars_required: int
    block_entry_at_session_close: bool


@njit(cache=True)
def range_bracket(
    range_high: float,
    range_low: float,
    atr: FloatArray,
    signal_bar: int,
    rules: OpeningRangeRules,
) -> tuple[float, float, float]:
    """One session range's order arithmetic: trigger, initial stop, planned risk.

    The trigger sits ``entry_offset`` beyond the extreme the trade breaks out of, and the stop
    either at the other extreme or an ATR multiple back from the trigger. **Everything is
    measured from the trigger rather than the fill**, because the whole bracket is known when
    the order is submitted -- which is what the reconciled DeadCatBounce port does and what a
    NinjaScript setting its stop and target at submission would do.
    """
    direction = rules.direction
    opposite, breakout = bracket.sided(range_low, range_high, direction)
    trigger = breakout + direction * rules.entry_offset

    if rules.stop_mode == ORB_STOP_ATR:
        distance = bracket.atr_bracket_distance(
            float(atr[signal_bar]),
            rules.atr_stop_multiple,
            rules.min_bracket_points,
        )
        stop = trigger - direction * distance
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

    in_position = False
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
        # ---- a new session re-arms the per-session entry cap -------------------------
        if i > 0 and ranges.session_id[i] != ranges.session_id[i - 1]:
            entries_this_session = 0

        # ---- exits, using the stop and targets set when the order was submitted ------
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

        # ---- the resting entry order, tested against this bar ------------------------
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

        # ---- close of bar i: resubmit the order, which is what makes it rest ---------
        if in_position or i < rules.bars_required or not signal[i]:
            continue

        # Not inherited from ``signal``, which the random-entry arm substitutes: a drawn bar
        # can land in a session whose range never completed, and that has no level to trade.
        if not ranges.armed[i]:
            continue

        if rules.max_entries_per_session > 0 and entries_this_session >= rules.max_entries_per_session:
            continue

        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue

        session = ranges.session_id[i]
        range_high = ranges.high[session]
        range_low = ranges.low[session]
        trigger, candidate_stop, candidate_risk = range_bracket(
            range_high,
            range_low,
            ranges.atr,
            i,
            rules,
        )
        # A stop-market entry must sit strictly beyond the market it is submitted into, which
        # under Calculate.OnBarClose is this bar's close -- ``docs/nt8-fidelity.md`` §M18.
        if candidate_risk < min_risk or direction * trigger <= direction * bars.close[i]:
            continue

        pending_bar = i
        pending_trigger = trigger
        pending_stop = candidate_stop
        pending_width = range_high - range_low

    # The series can stop mid-session, so anything still open is liquidated at the last bar.
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
                    bracket.LegExit(last, exit_fill, trades.EXIT_END_OF_DATA, False),
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
    out: FloatArray = bracket.allocate_output(entry_bound(data, params, signal), quantities.size)

    count: int = simulate_openingrange(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        RangeSeries(
            armed=data.range_armed(key),
            session_id=data.range_session_id(),
            high=data.range_high(key),
            low=data.range_low(key),
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
            entry_offset=params.entry_offset_ticks * instrument.tick_size,
            stop_mode=params.stop_mode,
            stop_offset=params.stop_offset_ticks * instrument.tick_size,
            atr_stop_multiple=params.atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(params.min_bracket_dollars),
            target_mode=params.target_mode,
            tp_multiplier=params.tp_multiplier,
            max_entries_per_session=params.max_entries_per_session,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
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
