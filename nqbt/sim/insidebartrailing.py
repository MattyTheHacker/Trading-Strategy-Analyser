"""InsideBarTrailing archetype: InsideBar's entry, split across two exit engines.

Ported from ``ninjatrader-scripts/Strategies/InsideBarTrailing.cs``. The entry is
:mod:`nqbt.sim.insidebar`'s -- the same functions, not a copy, with the NinjaScript's own
defaults on :class:`nqbt.sim.types.InsideBarTrailingParams`. What is new is the exit half:
the position is split into a bracketed lot and a trailing lot that resolve independently, the
trailing stop follows the high-water mark rather than a lagged bar's extreme, and a trend
violation flattens whatever is left.

**No trade list has been diffed against any of it**, so the archetype is
``Tier2Status.TIER1_ONLY`` and the two rules a trade list has to settle -- the trailing stop's
cadence and ``OnPositionUpdate``'s -- are recorded as assumptions in ``docs/nt8-fidelity.md``
§M23 rather than as evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numba import njit

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, insidebar
from nqbt.sim.types import STOP_MIN_TICKS

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


@njit(cache=True)
def resolve_lots(  # noqa: PLR0913, PLR0917 - one argument per bracket property; #59
    out: FloatArray,
    written: int,
    trade_id: int,
    entry_bar: int,
    i: int,
    entry_price: float,
    lot_initial_stop: FloatArray,
    lot_stop: FloatArray,
    lot_risk: FloatArray,
    leg_open: BoolArray,
    lot_mask: BoolArray,
    leg_target: FloatArray,
    leg_quantities: IntArray,
    run_high: float,
    run_low: float,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    must_flatten: bool,
    slippage: float,
    point_value: float,
    commission_per_contract: float,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    direction: float,
    held_from_bar_open: bool,
) -> int:
    """Resolve one bar against each lot's own stop and target, closing whatever leaves.

    One call to :func:`nqbt.sim.bracket.resolve_brackets` per lot, with ``lot_mask`` hiding
    every other leg so the engine sees a single bracket and writes it under its own leg number.
    ``lot_mask`` is the caller's scratch buffer, overwritten on every call.

    The split-lot model sits **beside** the shared engine rather than generalising it --
    ``docs/roadmap.md`` §M23. Returns the new write count, or ``-1`` if ``out`` overflowed.
    """
    n_lots = leg_open.size
    for lot in range(n_lots):
        if not leg_open[lot]:
            continue
        for other in range(n_lots):
            lot_mask[other] = other == lot
        written, _ = bracket.resolve_brackets(
            out,
            written,
            trade_id,
            entry_bar,
            i,
            entry_price,
            lot_initial_stop[lot],
            lot_stop[lot],
            lot_risk[lot],
            lot_mask,
            leg_target,
            leg_quantities,
            run_high,
            run_low,
            open_px,
            high_px,
            low_px,
            close_px,
            must_flatten,
            slippage,
            point_value,
            commission_per_contract,
            fill_limit_on_touch,
            ambiguity_policy,
            direction,
            held_from_bar_open,
        )
        if written < 0:
            return -1
        leg_open[lot] = lot_mask[lot]
    return written


@njit(cache=True)
def open_lots(leg_open: BoolArray) -> int:
    """How many lots are still live."""
    total = 0
    for lot in range(leg_open.size):
        if leg_open[lot]:
            total += 1
    return total


@njit(cache=True)
def simulate_insidebar_trailing(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917 - one argument per NT8 property; #59
    open_: FloatArray,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    signal: BoolArray,
    direction_at: FloatArray,
    force_flat: BoolArray,
    atr: FloatArray,
    ema: FloatArray,
    fast_sma: FloatArray,
    leg_quantities: IntArray,
    tick_size: float,
    point_value: float,
    atr_multiplier: float,
    trailing_stop_multiplier: float,
    commission_per_contract: float,
    slippage_ticks: float,
    bars_required: int,
    block_entry_at_session_close: bool,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    round_targets: bool,
    out: FloatArray,
) -> int:
    """Run the InsideBarTrailing archetype over one dataset, writing one row per leg exit.

    ``signal`` and ``direction_at`` are InsideBar's, unchanged. ``ema`` and ``fast_sma`` are the
    two averages the trend-violation exit compares; the slow one gates the entry only.

    Both lots fill together at the next bar's open and are bracketed off the same fill: the
    bracketed lot takes an ATR stop beyond the inside bar and a target one ATR from the fill,
    the trailing lot takes a stop ``trailing_stop_multiplier`` inside-bar ranges behind the
    high-water mark and no target. Returns the number of rows written, or ``-1`` if ``out``
    overflowed.
    """
    n = close.size
    n_lots = leg_quantities.size
    slippage = slippage_ticks * tick_size
    min_risk = STOP_MIN_TICKS * tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1
    pending_direction = 0.0
    pending_signal_exit = False

    d = 0.0
    entry_price = 0.0
    entry_bar = 0
    trail_distance = 0.0
    run_high = 0.0
    run_low = 0.0

    leg_open = np.zeros(n_lots, dtype=np.bool_)
    lot_mask = np.zeros(n_lots, dtype=np.bool_)
    leg_target = np.zeros(n_lots, dtype=np.float64)
    lot_stop = np.zeros(n_lots, dtype=np.float64)
    lot_initial_stop = np.zeros(n_lots, dtype=np.float64)
    lot_risk = np.zeros(n_lots, dtype=np.float64)

    for i in range(n):
        position_changed = False

        # ---- the trend-violation exit submitted at the last position change ------------
        if in_position and pending_signal_exit:
            # A market order, so it fills at this bar's first price and takes precedence over
            # the brackets -- ``docs/nt8-fidelity.md`` §M18, "The signal exit fills at the next
            # bar's open too".
            fill = open_[i] - d * slippage
            for lot in range(n_lots):
                if leg_open[lot]:
                    written = bracket.write_leg(
                        out,
                        written,
                        trade_id,
                        lot,
                        entry_bar,
                        i,
                        entry_price,
                        fill,
                        lot_initial_stop[lot],
                        leg_target[lot],
                        leg_quantities[lot],
                        trades.EXIT_SIGNAL,
                        lot_risk[lot],
                        run_high,
                        run_low,
                        point_value,
                        commission_per_contract,
                        False,
                        d,
                    )
                    if written < 0:
                        return -1
                    leg_open[lot] = False
            in_position = False

        # ---- the live brackets, resolved against this bar -------------------------------
        elif in_position:
            run_high = max(run_high, high[i])
            run_low = min(run_low, low[i])
            before = open_lots(leg_open)
            written = resolve_lots(
                out,
                written,
                trade_id,
                entry_bar,
                i,
                entry_price,
                lot_initial_stop,
                lot_stop,
                lot_risk,
                leg_open,
                lot_mask,
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
                d,
                True,  # held since this bar's open, so a gap through a stop fills at it
            )
            if written < 0:
                return -1
            after = open_lots(leg_open)
            in_position = after > 0
            position_changed = in_position and after != before
        pending_signal_exit = False

        # ---- both entry orders fill at this bar's open, unconditionally ------------------
        if not in_position and pending_bar >= 1 and pending_bar == i - 1:
            # A bar at or past the flatten cutoff cancels the orders rather than filling them.
            if not force_flat[i]:
                d = pending_direction
                fill = open_[i] + d * slippage
                # ``OnExecutionUpdate`` runs with the **signal** bar still current, so ATR[0]
                # is the signal bar's and [1] is the inside bar -- ``docs/nt8-fidelity.md``
                # §M22, established leg-for-leg against InsideBar's trade list.
                bar_atr = atr[pending_bar]
                inside_bar = pending_bar - 1
                adverse, _ = bracket.sided(low[inside_bar], high[inside_bar], d)
                fixed_stop = adverse - d * atr_multiplier * bar_atr
                # ``SetTrailStop`` takes a **tick count**, so the distance is computed as one
                # and converted back, exactly as the C# writes it.
                distance = (high[inside_bar] - low[inside_bar]) / tick_size * trailing_stop_multiplier
                trail_distance = distance * tick_size
                trail_stop = fill - d * trail_distance
                if round_targets:
                    # An ATR multiple lands off the grid, and an exchange takes a stop no more
                    # than it takes a target there -- ``docs/nt8-fidelity.md``, "Targets snap to
                    # the tick grid". Snapped before the risk, which every R multiple is
                    # measured from.
                    fixed_stop = bracket.round_to_tick(fixed_stop, tick_size)
                    trail_stop = bracket.round_to_tick(trail_stop, tick_size)
                fixed_risk = d * (fill - fixed_stop)
                trail_risk = d * (fill - trail_stop)
                # A stop at or through the price it protects is not a stop order, and neither
                # lot may be left running without one -- ``docs/nt8-fidelity.md`` §M23.
                if fixed_risk >= min_risk and trail_risk >= min_risk:
                    trade_id += 1
                    entry_price = fill
                    entry_bar = i
                    run_high = high[i]
                    run_low = low[i]
                    raw_target = fill + d * bar_atr
                    leg_open[BRACKETED_LOT] = True
                    leg_open[TRAILING_LOT] = True
                    lot_stop[BRACKETED_LOT] = fixed_stop
                    lot_stop[TRAILING_LOT] = trail_stop
                    lot_initial_stop[BRACKETED_LOT] = fixed_stop
                    lot_initial_stop[TRAILING_LOT] = trail_stop
                    lot_risk[BRACKETED_LOT] = fixed_risk
                    lot_risk[TRAILING_LOT] = trail_risk
                    leg_target[BRACKETED_LOT] = (
                        bracket.round_to_tick(raw_target, tick_size) if round_targets else raw_target
                    )
                    # The runner has no target: ``SetProfitTarget`` is never called for it.
                    leg_target[TRAILING_LOT] = np.nan
                    position_changed = True
                    written = resolve_lots(
                        out,
                        written,
                        trade_id,
                        entry_bar,
                        i,
                        entry_price,
                        lot_initial_stop,
                        lot_stop,
                        lot_risk,
                        leg_open,
                        lot_mask,
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
                        d,
                        True,  # filled at this bar's open, so it is held from the open
                    )
                    if written < 0:
                        return -1
                    in_position = open_lots(leg_open) > 0
            pending_bar = -1

        # ---- close of bar i: trail the runner's stop ------------------------------------
        if in_position and leg_open[TRAILING_LOT]:
            # The high-water mark through this bar, so the new level is in force from the next
            # one and cannot be hit on the bar that set it. Bar-close cadence, matching the
            # ratchet; **an assumption, not evidence** -- ``docs/nt8-fidelity.md`` §M23.
            _, favourable = bracket.sided(run_low, run_high, d)
            trailed = favourable - d * trail_distance
            if round_targets:
                trailed = bracket.round_to_tick(trailed, tick_size)
            if d * trailed > d * lot_stop[TRAILING_LOT]:
                lot_stop[TRAILING_LOT] = trailed

        # ---- close of bar i: the trend violation, then a new signal ---------------------
        if in_position and position_changed and d * (ema[i] - fast_sma[i]) < 0.0:
            # The C#'s max-loss branch above this one is unreachable: MaximumLossPerTrade
            # defaults to 0 and the branch requires it > 0 -- ``docs/nt8-fidelity.md`` §M23.
            pending_signal_exit = True

        if in_position or i <= bars_required or not signal[i]:
            continue
        if block_entry_at_session_close and force_flat[i]:
            continue
        pending_bar = i
        pending_direction = direction_at[i]

    # Anything still open when the series runs out is liquidated at the last bar.
    if in_position:
        last = n - 1
        exit_fill = close[last] - d * slippage
        for lot in range(n_lots):
            if leg_open[lot]:
                written = bracket.write_leg(
                    out,
                    written,
                    trade_id,
                    lot,
                    entry_bar,
                    last,
                    entry_price,
                    exit_fill,
                    lot_initial_stop[lot],
                    leg_target[lot],
                    leg_quantities[lot],
                    trades.EXIT_END_OF_DATA,
                    lot_risk[lot],
                    run_high,
                    run_low,
                    point_value,
                    commission_per_contract,
                    False,
                    d,
                )
                if written < 0:
                    return -1

    return written


def insidebartrailing_legs(
    data: Dataset,
    params: InsideBarTrailingParams,
    instrument: Instrument = MNQ,
    *,
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
        data.open,
        data.high,
        data.low,
        data.close,
        signal,
        direction_at,
        data.force_flat,
        data.atr_values(params.atr_length),
        data.ma_values("ema", params.ema_period),
        data.ma_values("sma", params.fast_sma_period),
        quantities,
        instrument.tick_size,
        instrument.point_value,
        params.atr_multiplier,
        params.trailing_stop_multiplier,
        params.commission_per_contract,
        params.slippage_ticks,
        params.bars_required_to_trade,
        params.block_entry_at_session_close,
        params.fill_limit_on_touch,
        params.ambiguity_policy,
        params.round_targets,
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
    *,
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
