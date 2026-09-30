"""InsideBar archetype: break an inside bar out of its mother bar, both sides.

Ported from ``ninjatrader-scripts/Strategies/InsideBar.cs``: a market entry at the next open,
``IsFillLimitOnTouch = true``, a bracket computed at the fill, and a no-entry window before the
session close. Each rule: ``docs/nt8-fidelity.md`` §M22 and "Reconciliation result --
InsideBar".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import STOP_MIN_TICKS

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray
    from nqbt.context import Dataset
    from nqbt.sim.types import InsideBarParams
    from nqbt.trades import LegMatrix

MOTHER_BAR_LAG = 2
"""Bars back to the mother bar: the inside bar is ``[1]`` and its own predecessor is ``[2]``."""


class InsideBarRules(NamedTuple):
    """The rule set :func:`simulate_insidebar` reads, one field per NT8 property."""

    atr_multiplier: float
    tp_multiplier: float
    bars_required: int
    block_entry_at_session_close: bool
    max_hold_bars: int
    early_exit: bracket.EarlyExit = bracket.EARLY_EXIT_OFF


@njit(cache=True)
def simulate_insidebar(  # noqa: C901, PLR0912, PLR0915 - one branch per NT8 rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    direction_at: FloatArray,
    atr: FloatArray,
    sizing: bracket.Sizing,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: InsideBarRules,
    out: FloatArray,
) -> int:
    """Run the InsideBar archetype over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close schedules a market entry for the next bar's open and
    ``direction_at`` says which side each bar is on, as in
    :func:`nqbt.sim.crossover.simulate_crossover`. ``sizing`` names the size each signal bar's
    entry takes.

    The bracket is built at the **fill**: the target is ``tp_multiplier`` ATRs from the fill
    price and the stop ``atr_multiplier`` ATRs beyond the inside bar's adverse extreme, both
    reading the signal bar's ATR. Returns the number of rows written, or ``-1`` if ``out``
    overflowed.
    """
    n = bars.close.size
    n_legs = sizing.quantities.shape[1]
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit_reason = bracket.NO_MARKET_EXIT
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, True)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        np.zeros(n_legs, dtype=np.int64),
    )

    for i in range(n):
        # ---- the live bracket, resolved against this bar --------------------------------
        if in_position and pending_exit_reason != bracket.NO_MARKET_EXIT:
            # Submitted at the close of bar i-1 and filled at this bar's first price, so the
            # excursion stays where it was.
            written = bracket.flatten_position(
                out,
                written,
                trade,
                legs,
                bracket.LegExit(i, bars.open_[i] - d * slippage, pending_exit_reason, False),
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

        # ---- the entry order fills at this bar's open, unconditionally -------------------
        if not in_position and pending_bar >= 1 and pending_bar == i - 1:
            # A force-flat bar is filled like any other; the session-close handler runs
            # after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            d = pending_direction
            fill = bars.open_[i] + d * slippage
            # ``OnExecutionUpdate`` runs with the **signal** bar still current, so its
            # ATR[0] is the signal bar's and its Low[1] is the inside bar's --
            # ``docs/nt8-fidelity.md`` §M22.
            bar_atr = atr[pending_bar]
            adverse, _ = bracket.sided(bars.low[pending_bar - 1], bars.high[pending_bar - 1], d)
            # The NinjaScript floors nothing.
            stop_distance = bracket.atr_bracket_distance(
                bar_atr,
                rules.atr_multiplier,
                bracket.NO_BRACKET_FLOOR,
            )
            candidate_stop = adverse - d * stop_distance
            if fills.round_targets:
                # Snapped before the risk is measured -- ``docs/nt8-fidelity.md``, "Targets snap
                # to the tick grid".
                candidate_stop = bracket.round_to_tick(candidate_stop, costs.tick_size)

            candidate_risk = d * (fill - candidate_stop)
            # A stop at or through the price it protects is not a stop order --
            # ``docs/nt8-fidelity.md`` §M18.
            if candidate_risk >= min_risk:
                trade_id += 1
                trade = bracket.OpenTrade(
                    trade_id=trade_id,
                    entry_bar=i,
                    entry_price=fill,
                    initial_stop=candidate_stop,
                    risk=candidate_risk,
                    direction=d,
                    filled_at_open=True,
                )
                stop = candidate_stop
                excursion = bracket.Excursion(bars.high[i], bars.low[i])
                raw_target = fill + d * bar_atr * rules.tp_multiplier
                bracket.size_legs(legs, sizing, pending_bar)
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    legs.target[leg] = (
                        bracket.round_to_tick(raw_target, costs.tick_size)
                        if fills.round_targets
                        else raw_target
                    )
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

        pending_exit_reason = (
            bracket.market_exit_reason(trade, i, bars.close[i], rules.max_hold_bars, rules.early_exit)
            if in_position
            else bracket.NO_MARKET_EXIT
        )

        # ---- close of bar i: schedule the next bar's entry -------------------------------
        if in_position or i <= rules.bars_required or not signal[i]:
            continue

        if rules.block_entry_at_session_close and bars.force_flat[i]:
            continue

        pending_bar = i
        pending_direction = direction_at[i]

    # Anything still open when the series runs out is liquidated at the last bar.
    if in_position:
        last = n - 1
        written = bracket.flatten_position(
            out,
            written,
            trade,
            legs,
            bracket.LegExit(last, bars.close[last] - d * slippage, trades.EXIT_END_OF_DATA, False),
            excursion,
            costs,
        )
        if written < 0:
            return -1

    return written


def insidebar_trends(data: Dataset, params: InsideBarParams) -> tuple[BoolArray, BoolArray]:
    """Return the two three-average gates: close **strictly** above all three, or below all three.

    Strict on each comparison, so equality fails both -- ``docs/nt8-fidelity.md`` §M22.
    """
    ema: FloatArray = data.ma_values(params.ema_kind, params.ema_period)
    fast: FloatArray = data.ma_values(params.fast_sma_kind, params.fast_sma_period)
    slow: FloatArray = data.ma_values(params.slow_sma_kind, params.slow_sma_period)
    up: BoolArray = (data.close > ema) & (data.close > fast) & (data.close > slow)
    down: BoolArray = (data.close < ema) & (data.close < fast) & (data.close < slow)

    return up, down


def insidebar_breakouts(data: Dataset, params: InsideBarParams) -> tuple[BoolArray, BoolArray]:
    """Return whether this bar's close clears the mother bar by ``error_margin`` of its range.

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
    """Return which side each bar would be entered on: ``LONG`` where the averages say uptrend.

    Defined on every bar, so the random-entry arm can drop a signal anywhere. A bar agreeing
    with neither gate reads ``SHORT``, which :func:`insidebar_signal` never reaches.
    """
    up, _ = insidebar_trends(data, params)

    return np.where(up, trades.LONG, trades.SHORT).astype(np.float64)


def insidebar_long_side(data: Dataset, params: InsideBarParams) -> BoolArray:
    """Return the bars one combination would enter long: those strictly above all three averages."""
    long_side: BoolArray = insidebar_direction(data, params) == trades.LONG

    return long_side


def insidebar_patterns(data: Dataset, params: InsideBarParams) -> tuple[BoolArray, BoolArray]:
    """Return the long and short setups on their own, before any clock or context filter narrows them.

    An inside bar behind this one, a close clearing the mother bar's extreme by the error
    margin, and all three averages agreeing with the direction of the break.
    """
    up_trend, down_trend = insidebar_trends(data, params)
    up_break, down_break = insidebar_breakouts(data, params)
    inside: BoolArray = data.geometry.prior_bar_inside

    return inside & up_break & up_trend, inside & down_break & down_trend


def insidebar_signal(data: Dataset, params: InsideBarParams) -> BoolArray:
    """Flag bars whose close schedules an entry for the next bar's open: a pattern the filters admit."""
    long_pattern, short_pattern = insidebar_patterns(data, params)
    signal: BoolArray = long_pattern | short_pattern
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
    sizing: bracket.Sizing = filters.confluence_sizing(data, params, direction_at == trades.LONG)
    out: FloatArray = bracket.allocate_output(int(signal.sum()), sizing.quantities.shape[1])

    count: int = simulate_insidebar(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        direction_at,
        data.atr_values(params.atr_length),
        sizing,
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
        InsideBarRules(
            atr_multiplier=params.atr_multiplier,
            tp_multiplier=params.tp_multiplier,
            bars_required=params.bars_required_to_trade,
            block_entry_at_session_close=params.block_entry_at_session_close,
            max_hold_bars=params.max_hold_bars,
            early_exit=filters.early_exit(data, params),
        ),
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
