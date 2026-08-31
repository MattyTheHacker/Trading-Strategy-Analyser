"""InsideBarTrailing archetype: InsideBar's entry, split across two exit engines.

Ported from ``ninjatrader-scripts/Strategies/InsideBarTrailing.cs``. The entry is
:mod:`nqbt.sim.insidebar`'s -- the same functions, not a copy, with the NinjaScript's own
defaults on :class:`nqbt.sim.types.InsideBarTrailingParams`. What is new is the exit half:
the position is split into a bracketed lot and a trailing lot that resolve independently, the
trailing stop follows the high-water mark rather than a lagged bar's extreme, and a trend
violation flattens whatever is left.

Diffed leg-for-leg against an MNQ 03-24 Strategy Analyzer export, which **overturned three of
the four exit rules this port originally inferred** -- ``docs/nt8-fidelity.md``, "Reconciliation
result -- InsideBarTrailing". Read that before changing anything in the exit half: each of the
four was plausible in both directions, and the tests name the measurement that decided it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, insidebar
from nqbt.sim.types import STOP_MIN_TICKS
from nqbt.trades import C_EXIT_PRICE

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import InsideBarTrailingParams
    from nqbt.trades import LegMatrix

BRACKETED_LOT = 0
"""``entry1``: a fixed stop and a profit target."""

TRAILING_LOT = 1
"""``entry2``: a trailing stop and no target at all."""


class Lots(NamedTuple):
    """Each lot's own bracket state: parallel arrays, one entry per lot, mutated in place.

    ``mask`` is the scratch buffer :func:`resolve_lots` hides every other lot behind, and is
    overwritten on every call.
    """

    initial_stop: FloatArray
    stop: FloatArray
    risk: FloatArray
    mask: BoolArray


class TrendAverages(NamedTuple):
    """The two averages the trend-violation exit compares; the slow one gates the entry only."""

    ema: FloatArray
    fast_sma: FloatArray


class InsideBarTrailingRules(NamedTuple):
    """The scalar rule set the loop reads, one field per NT8 property.

    ``position_update_loss_gate`` is a **currency** amount on the whole open position, so it
    goes through ``instruments.py`` -- ``docs/nt8-fidelity.md`` §M23.
    """

    atr_multiplier: float
    tp_multiplier: float
    trailing_stop_multiplier: float
    position_update_loss_gate: float
    bars_required: int
    block_entry_at_session_close: bool


@njit(cache=True)
def resolve_lots(
    out: FloatArray,
    written: int,
    trade: bracket.OpenTrade,
    lots: Lots,
    legs: bracket.Legs,
    excursion: bracket.Excursion,
    bars: bracket.Bars,
    i: int,
    costs: bracket.Costs,
    fills: bracket.FillRules,
) -> tuple[int, float]:
    """Resolve one bar against each lot's own stop and target, closing whatever leaves.

    One call to :func:`nqbt.sim.bracket.resolve_brackets` per lot, with ``lots.mask`` hiding
    every other leg so the engine sees a single bracket and writes it under its own leg number.

    The split-lot model sits **beside** the shared engine rather than generalising it --
    ``docs/roadmap.md`` §M23. Returns the new write count and the price the last lot to leave
    filled at -- which is the price the trend-violation exit takes -- or ``-1`` and ``NaN`` if
    ``out`` overflowed.
    """
    n_lots = legs.is_open.size
    last_fill = np.nan
    for lot in range(n_lots):
        if not legs.is_open[lot]:
            continue
        for other in range(n_lots):
            lots.mask[other] = other == lot
        written, _ = bracket.resolve_brackets(
            out,
            written,
            lot_trade(trade, lots, lot),
            lots.stop[lot],
            bracket.Legs(lots.mask, legs.target, legs.quantity),
            excursion,
            bars,
            i,
            costs,
            fills,
        )
        if written < 0:
            return -1, np.nan
        if legs.is_open[lot] and not lots.mask[lot]:
            last_fill = out[written - 1, C_EXIT_PRICE]
        legs.is_open[lot] = lots.mask[lot]
    return written, last_fill


@njit(cache=True)
def flatten_lots(
    out: FloatArray,
    written: int,
    trade: bracket.OpenTrade,
    leg_exit: bracket.LegExit,
    lots: Lots,
    legs: bracket.Legs,
    excursion: bracket.Excursion,
    costs: bracket.Costs,
) -> int:
    """Close every still-open lot at one price for one reason, and mark them closed.

    Shared by the trend-violation exit and the end-of-data liquidation, which differ only in
    the price, the bar and the reason.
    """
    for lot in range(legs.is_open.size):
        if not legs.is_open[lot]:
            continue
        written = bracket.write_leg(
            out,
            written,
            lot_trade(trade, lots, lot),
            legs,
            lot,
            leg_exit,
            excursion,
            costs,
        )
        if written < 0:
            return -1
        legs.is_open[lot] = False
    return written


@njit(cache=True)
def lot_trade(trade: bracket.OpenTrade, lots: Lots, lot: int) -> bracket.OpenTrade:
    """``trade`` with this lot's own stop and risk in place of the shared ones."""
    return bracket.OpenTrade(
        trade_id=trade.trade_id,
        entry_bar=trade.entry_bar,
        entry_price=trade.entry_price,
        initial_stop=lots.initial_stop[lot],
        risk=lots.risk[lot],
        direction=trade.direction,
        filled_at_open=trade.filled_at_open,
    )


@njit(cache=True)
def trailed_stop(
    lots: Lots,
    excursion: bracket.Excursion,
    trail_distance: float,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    direction: float,
) -> float:
    """Where the trailing stop sits given the high-water mark so far, never retreating."""
    _, favourable = bracket.sided(excursion.run_low, excursion.run_high, direction)
    candidate = favourable - direction * trail_distance
    if fills.round_targets:
        candidate = bracket.round_to_tick(candidate, costs.tick_size)
    standing = float(lots.stop[TRAILING_LOT])
    if direction * candidate > direction * standing:
        return candidate
    return standing


@njit(cache=True)
def open_lots(legs: bracket.Legs) -> int:
    """How many lots are still live."""
    total = 0
    for lot in range(legs.is_open.size):
        if legs.is_open[lot]:
            total += 1
    return total


@njit(cache=True)
def simulate_insidebar_trailing(  # noqa: C901, PLR0912, PLR0915 - one branch per NT8 rule
    bars: bracket.Bars,
    signal: BoolArray,
    direction_at: FloatArray,
    atr: FloatArray,
    averages: TrendAverages,
    leg_quantities: IntArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: InsideBarTrailingRules,
    out: FloatArray,
) -> int:
    """Run the InsideBarTrailing archetype over one dataset, writing one row per leg exit.

    ``signal`` and ``direction_at`` are InsideBar's, unchanged.

    Both lots fill together at the next bar's open and are bracketed off the same fill: the
    bracketed lot takes an ATR stop beyond the inside bar and a target ``tp_multiplier`` ATRs
    from the fill, the trailing lot takes a stop ``trailing_stop_multiplier`` inside-bar ranges
    behind the high-water mark and no target. Returns the number of rows written, or ``-1`` if
    ``out`` overflowed.
    """
    n = bars.close.size
    n_lots = leg_quantities.size
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, True)
    trail_distance = 0.0
    trigger_fill = np.nan
    excursion = bracket.Excursion(0.0, 0.0)

    legs = bracket.Legs(
        np.zeros(n_lots, dtype=np.bool_),
        np.zeros(n_lots, dtype=np.float64),
        leg_quantities,
    )
    lots = Lots(
        np.zeros(n_lots, dtype=np.float64),
        np.zeros(n_lots, dtype=np.float64),
        np.zeros(n_lots, dtype=np.float64),
        np.zeros(n_lots, dtype=np.bool_),
    )

    for i in range(n):
        position_changed = False

        # ---- the live brackets, resolved against this bar -------------------------------
        if in_position:
            excursion = bracket.extend_excursion(excursion, bars.high[i], bars.low[i])
            before = open_lots(legs)
            written, trigger_fill = resolve_lots(
                out,
                written,
                trade,
                lots,
                legs,
                excursion,
                bars,
                i,
                costs,
                fills,
            )
            if written < 0:
                return -1
            after = open_lots(legs)
            in_position = after > 0
            position_changed = in_position and after != before

        # ---- both entry orders fill at this bar's open, unconditionally ------------------
        if not in_position and pending_bar >= 1 and pending_bar == i - 1:
            # A force-flat bar is filled like any other; the session-close handler runs
            # after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            d = pending_direction
            fill = bars.open_[i] + d * slippage
            # ``OnExecutionUpdate`` runs with the **signal** bar still current, so ATR[0]
            # is the signal bar's and [1] is the inside bar -- ``docs/nt8-fidelity.md``
            # §M22, established leg-for-leg against InsideBar's trade list.
            bar_atr = atr[pending_bar]
            inside_bar = pending_bar - 1
            adverse, _ = bracket.sided(bars.low[inside_bar], bars.high[inside_bar], d)
            # The NinjaScript floors nothing, so the port passes none -- ``docs/roadmap.md``
            # § "ATR-multiple brackets and the dollar floor".
            stop_distance = bracket.atr_bracket_distance(
                bar_atr,
                rules.atr_multiplier,
                bracket.NO_BRACKET_FLOOR,
            )
            fixed_stop = adverse - d * stop_distance
            # ``SetTrailStop`` takes a **tick count**, so the distance is computed as one
            # and converted back, exactly as the C# writes it.
            distance = (
                (bars.high[inside_bar] - bars.low[inside_bar])
                / costs.tick_size
                * rules.trailing_stop_multiplier
            )
            trail_distance = distance * costs.tick_size
            trail_stop = fill - d * trail_distance
            if fills.round_targets:
                # An ATR multiple lands off the grid, and an exchange takes a stop no more
                # than it takes a target there -- ``docs/nt8-fidelity.md``, "Targets snap to
                # the tick grid". Snapped before the risk, which every R multiple is
                # measured from.
                fixed_stop = bracket.round_to_tick(fixed_stop, costs.tick_size)
                trail_stop = bracket.round_to_tick(trail_stop, costs.tick_size)
            fixed_risk = d * (fill - fixed_stop)
            trail_risk = d * (fill - trail_stop)
            # A stop at or through the price it protects is not a stop order, and neither
            # lot may be left running without one -- ``docs/nt8-fidelity.md`` §M23.
            if fixed_risk >= min_risk and trail_risk >= min_risk:
                trade_id += 1
                trade = bracket.OpenTrade(
                    trade_id=trade_id,
                    entry_bar=i,
                    entry_price=fill,
                    # Per-lot; lot_trade substitutes each lot's own before a leg is written.
                    initial_stop=fixed_stop,
                    risk=fixed_risk,
                    direction=d,
                    filled_at_open=True,
                )
                excursion = bracket.Excursion(bars.high[i], bars.low[i])
                raw_target = fill + d * bar_atr * rules.tp_multiplier
                legs.is_open[BRACKETED_LOT] = True
                legs.is_open[TRAILING_LOT] = True
                lots.stop[BRACKETED_LOT] = fixed_stop
                lots.stop[TRAILING_LOT] = trail_stop
                lots.initial_stop[BRACKETED_LOT] = fixed_stop
                lots.initial_stop[TRAILING_LOT] = trail_stop
                lots.risk[BRACKETED_LOT] = fixed_risk
                lots.risk[TRAILING_LOT] = trail_risk
                legs.target[BRACKETED_LOT] = (
                    bracket.round_to_tick(raw_target, costs.tick_size) if fills.round_targets else raw_target
                )
                # The runner has no target: ``SetProfitTarget`` is never called for it.
                legs.target[TRAILING_LOT] = np.nan
                # `SetTrailStop` is submitted *during* this bar rather than resting from
                # its open, so on the entry bar alone it follows the bar's own extreme
                # before being tested. Measured -- ``docs/nt8-fidelity.md`` §M23.
                lots.stop[TRAILING_LOT] = trailed_stop(lots, excursion, trail_distance, costs, fills, d)
                position_changed = True
                written, trigger_fill = resolve_lots(
                    out,
                    written,
                    trade,
                    lots,
                    legs,
                    excursion,
                    bars,
                    i,
                    costs,
                    fills,
                )
                if written < 0:
                    return -1
                in_position = open_lots(legs) > 0
            pending_bar = -1

        # ---- close of bar i: trail the runner's stop ------------------------------------
        if in_position and legs.is_open[TRAILING_LOT]:
            # The high-water mark through this bar, so the new level is in force from the **next**
            # one and cannot be hit on the bar that set it. Measured, not assumed: advancing it
            # within the bar instead drops agreement from 98.42% to 94.04% --
            # ``docs/nt8-fidelity.md`` §M23.
            lots.stop[TRAILING_LOT] = trailed_stop(lots, excursion, trail_distance, costs, fills, d)

        # ---- the trend violation, on whichever bar the position just changed ------------
        if in_position and position_changed and i >= 1:
            # `OnPositionUpdate` runs at strategy time `i - 1` -- the one-bar offset
            # `OnExecutionUpdate` has -- and the market exit it submits fills at this bar's
            # open. Both settled against a trade list; ``docs/nt8-fidelity.md`` §M23.
            #
            # `if (GetUnrealizedProfitLoss(...) > -200) return;` sits **above** both branches in
            # `OnPositionUpdate`, so it gates the trend violation as well as the dead max-loss
            # one. A currency amount on the whole open position, hence `point_value`. The
            # max-loss branch beneath it stays unreachable: `MaximumLossPerTrade` defaults to 0
            # and its own condition requires it > 0.
            open_quantity = 0
            for lot in range(n_lots):
                if legs.is_open[lot]:
                    open_quantity += legs.quantity[lot]
            unrealised = (bars.close[i - 1] - trade.entry_price) * d * open_quantity * costs.point_value
            if (
                unrealised <= -rules.position_update_loss_gate
                and d * (averages.ema[i - 1] - averages.fast_sma[i - 1]) < 0.0
                and not np.isnan(trigger_fill)
            ):
                written = flatten_lots(
                    out,
                    written,
                    trade,
                    # The same fill, not a fresh market order: NT8 closed the remaining lot at
                    # the price and bar the triggering exit filled at, on every one of the 303
                    # in the export. It carries that fill's slippage and takes no second helping
                    # -- ``docs/nt8-fidelity.md`` §M23.
                    bracket.LegExit(i, trigger_fill, trades.EXIT_SIGNAL, False),
                    lots,
                    legs,
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1
                in_position = False

        if in_position or i <= rules.bars_required or not signal[i]:
            continue
        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue
        pending_bar = i
        pending_direction = direction_at[i]

    # Anything still open when the series runs out is liquidated at the last bar.
    if in_position:
        last = n - 1
        written = flatten_lots(
            out,
            written,
            trade,
            bracket.LegExit(last, bars.close[last] - d * slippage, trades.EXIT_END_OF_DATA, False),
            lots,
            legs,
            excursion,
            costs,
        )
        if written < 0:
            return -1

    return written


def insidebartrailing_legs(
    data: Dataset,
    params: InsideBarTrailingParams,
    instrument: Instrument = MNQ,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    The signal and direction series are :mod:`nqbt.sim.insidebar`'s, read with this
    archetype's defaults; ``signal`` overrides the first for the random-entry control arm.
    """
    direction_at: FloatArray = insidebar.insidebar_direction(data, params)
    signal = insidebar.insidebar_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = simulate_insidebar_trailing(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        direction_at,
        data.atr_values(params.atr_length),
        TrendAverages(
            ema=data.ma_values(params.ema_kind, params.ema_period),
            fast_sma=data.ma_values(params.fast_sma_kind, params.fast_sma_period),
        ),
        quantities,
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
        InsideBarTrailingRules(
            atr_multiplier=params.atr_multiplier,
            tp_multiplier=params.tp_multiplier,
            trailing_stop_multiplier=params.trailing_stop_multiplier,
            position_update_loss_gate=params.position_update_loss_gate,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_insidebartrailing(
    data: Dataset,
    params: InsideBarTrailingParams,
    instrument: Instrument = MNQ,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = insidebartrailing_legs(data, params, instrument, signal=signal)
    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
