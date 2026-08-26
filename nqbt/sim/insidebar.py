"""InsideBar archetype: break an inside bar out of its mother bar, both sides.

Ported from ``ninjatrader-scripts/Strategies/InsideBar.cs``. The entry mechanism is
M18's market-on-next-open, but three things here reach parts of the fill model no other
archetype does -- ``IsFillLimitOnTouch = true``, a bracket computed in ``OnExecutionUpdate``
from the **fill** price with the stop anchored to the **signal bar**, and a no-entry window
before the session close. Each rule, and which of them still has no evidence:
``docs/nt8-fidelity.md`` §M22.

``Tier2Status.TIER1_ONLY`` until a real Strategy Analyzer trade list has been diffed
against it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numba import njit

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import STOP_MIN_TICKS

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import InsideBarParams
    from nqbt.trades import LegMatrix

MOTHER_BAR_LAG = 2
"""Bars back to the mother bar: the inside bar is ``[1]`` and its own predecessor is ``[2]``."""


@njit(cache=True)
def simulate_insidebar(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917 - one argument per NT8 property; #59
    open_: FloatArray,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    signal: BoolArray,
    direction_at: FloatArray,
    force_flat: BoolArray,
    atr: FloatArray,
    leg_quantities: IntArray,
    tick_size: float,
    point_value: float,
    atr_multiplier: float,
    commission_per_contract: float,
    slippage_ticks: float,
    bars_required: int,
    block_entry_at_session_close: bool,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    round_targets: bool,
    out: FloatArray,
) -> int:
    """Run the InsideBar archetype over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close schedules a market entry for the next bar's open and
    ``direction_at`` says which side each bar is on, separated for the reason
    :func:`nqbt.sim.crossover.simulate_crossover` separates them.

    The bracket is built at the **fill**, not at the signal: the target is one ATR from the
    fill price and the stop ``atr_multiplier`` ATRs beyond the signal bar's adverse extreme,
    both reading the ATR of the bar the fill lands on. Returns the number of rows written, or
    ``-1`` if ``out`` overflowed.
    """
    n = close.size
    n_legs = leg_quantities.size
    slippage = slippage_ticks * tick_size
    min_risk = STOP_MIN_TICKS * tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
    entry_price = 0.0
    entry_bar = 0
    stop = 0.0
    risk = 0.0
    run_high = 0.0
    run_low = 0.0

    leg_open = np.zeros(n_legs, dtype=np.bool_)
    leg_target = np.zeros(n_legs, dtype=np.float64)

    for i in range(n):
        # ---- the live bracket, resolved against this bar --------------------------------
        if in_position:
            run_high = max(run_high, high[i])
            run_low = min(run_low, low[i])
            written, in_position = bracket.resolve_brackets(
                out,
                written,
                trade_id,
                entry_bar,
                i,
                entry_price,
                stop,
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
                d,
                True,  # held since this bar's open, so a gap through the stop fills at it
            )
            if written < 0:
                return -1

        # ---- the entry order fills at this bar's open, unconditionally -------------------
        if not in_position and pending_bar >= 1 and pending_bar == i - 1:
            # A bar at or past the flatten cutoff cancels the order rather than filling it.
            if not force_flat[i]:
                d = pending_direction
                fill = open_[i] + d * slippage
                # ``OnExecutionUpdate`` runs with the **signal** bar still current, so its
                # ATR[0] is the signal bar's and its Low[1] is the inside bar's -- the bar
                # before it. Both established leg-for-leg against a trade list, against an
                # inference that had them one bar later -- ``docs/nt8-fidelity.md`` §M22.
                bar_atr = atr[pending_bar]
                adverse, _ = bracket.sided(low[pending_bar - 1], high[pending_bar - 1], d)
                candidate_stop = adverse - d * atr_multiplier * bar_atr
                if round_targets:
                    # An ATR multiple lands off the grid, and an exchange takes a stop no more
                    # than it takes a target there -- ``docs/nt8-fidelity.md``, "Targets snap to
                    # the tick grid". Snapped before the risk, which the submittability test
                    # and every R multiple are measured from.
                    candidate_stop = bracket.round_to_tick(candidate_stop, tick_size)
                candidate_risk = d * (fill - candidate_stop)
                # A stop at or through the price it protects is not a stop order --
                # ``docs/nt8-fidelity.md`` §M18.
                if candidate_risk >= min_risk:
                    trade_id += 1
                    entry_price = fill
                    entry_bar = i
                    stop = candidate_stop
                    risk = candidate_risk
                    run_high = high[i]
                    run_low = low[i]
                    raw_target = fill + d * bar_atr
                    for leg in range(n_legs):
                        leg_open[leg] = True
                        leg_target[leg] = (
                            bracket.round_to_tick(raw_target, tick_size) if round_targets else raw_target
                        )
                    written, in_position = bracket.resolve_brackets(
                        out,
                        written,
                        trade_id,
                        entry_bar,
                        i,
                        entry_price,
                        stop,
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
                        d,
                        True,  # filled at this bar's open, so it is held from the open
                    )
                    if written < 0:
                        return -1
            pending_bar = -1

        # ---- close of bar i: schedule the next bar's entry -------------------------------
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
        for leg in range(n_legs):
            if leg_open[leg]:
                written = bracket.write_leg(
                    out,
                    written,
                    trade_id,
                    leg,
                    entry_bar,
                    last,
                    entry_price,
                    exit_fill,
                    stop,
                    leg_target[leg],
                    leg_quantities[leg],
                    trades.EXIT_END_OF_DATA,
                    risk,
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


def insidebar_trends(data: Dataset, params: InsideBarParams) -> tuple[BoolArray, BoolArray]:
    """The two three-average gates: close **strictly** above all three, or below all three.

    Strict on each comparison, so equality fails both -- ``InsideBar.cs`` writes the positive
    form rather than a rejection, unlike the two ports, and the raw values are read for that
    reason. ``docs/nt8-fidelity.md`` §M22.
    """
    ema: FloatArray = data.ma_values("ema", params.ema_period)
    fast: FloatArray = data.ma_values("sma", params.fast_sma_period)
    slow: FloatArray = data.ma_values("sma", params.slow_sma_period)
    up: BoolArray = (data.close > ema) & (data.close > fast) & (data.close > slow)
    down: BoolArray = (data.close < ema) & (data.close < fast) & (data.close < slow)
    return up, down


def insidebar_breakouts(data: Dataset, params: InsideBarParams) -> tuple[BoolArray, BoolArray]:
    """Whether this bar's close clears the mother bar by ``error_margin`` of its range.

    Stamped on the bar whose close judges it, so the mother bar is two back.
    """
    n: int = len(data)
    up: BoolArray = np.zeros(n, dtype=np.bool_)
    down: BoolArray = np.zeros(n, dtype=np.bool_)
    mother_high: FloatArray = data.high[:-MOTHER_BAR_LAG]
    mother_low: FloatArray = data.low[:-MOTHER_BAR_LAG]
    margin: FloatArray = (mother_high - mother_low) * params.error_margin
    up[MOTHER_BAR_LAG:] = data.close[MOTHER_BAR_LAG:] > mother_high + margin
    down[MOTHER_BAR_LAG:] = data.close[MOTHER_BAR_LAG:] < mother_low - margin
    return up, down


def insidebar_direction(data: Dataset, params: InsideBarParams) -> FloatArray:
    """Which side each bar would be entered on: ``LONG`` where the averages say uptrend.

    Defined on **every** bar rather than only on signal bars, so the random-entry arm can drop
    a signal anywhere. The two gates are not complements, so a bar agreeing with neither reads
    ``SHORT`` -- unreachable through :func:`insidebar_signal`, which requires one of them.
    """
    up, _ = insidebar_trends(data, params)
    return np.where(up, trades.LONG, trades.SHORT).astype(np.float64)


def insidebar_signal(data: Dataset, params: InsideBarParams) -> BoolArray:
    """Bars whose close schedules an entry for the next bar's open.

    An inside bar behind this one, a close clearing the mother bar's extreme by the error
    margin, and all three averages agreeing with the direction of the break.
    """
    up_trend, down_trend = insidebar_trends(data, params)
    up_break, down_break = insidebar_breakouts(data, params)
    signal: BoolArray = data.geometry.prior_bar_inside & ((up_break & up_trend) | (down_break & down_trend))
    if params.no_entry_minutes_before_close > 0:
        signal &= data.session_end_gate(params.no_entry_minutes_before_close)
    return filters.apply_context_filters(signal, data, params)


def insidebar_legs(
    data: Dataset,
    params: InsideBarParams,
    instrument: Instrument = MNQ,
    *,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the
    direction series is *not* overridden, so a drawn bar is taken on whichever side the
    averages were on.
    """
    direction_at: FloatArray = insidebar_direction(data, params)
    signal = insidebar_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = simulate_insidebar(
        data.open,
        data.high,
        data.low,
        data.close,
        signal,
        direction_at,
        data.force_flat,
        data.atr_values(params.atr_length),
        quantities,
        instrument.tick_size,
        instrument.point_value,
        params.atr_multiplier,
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


def run_insidebar(
    data: Dataset,
    params: InsideBarParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = insidebar_legs(data, params, instrument, signal=signal)
    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
