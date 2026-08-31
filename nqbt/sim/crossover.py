"""EmaCrossover archetype: the first original, and a deliberate known-negative control.

**There is no NinjaScript**, so this is ``Tier2Status.TIER1_ONLY`` and every rule below is
written down rather than reconciled -- ``docs/nt8-fidelity.md`` §M18 names the NinjaScript each
would become. **If it reads meaningfully better than the random-entry arm, the first
hypothesis is lookahead**: every series read here is stamped from completed bars.

It is the third entry mechanism (market-on-next-open, no trigger price), the only producer of
``EXIT_SIGNAL``, and the first archetype to take both sides within one run. It is **flat
between trades, not stop-and-reverse**, and its ``r_multiple`` is volatility-scaled rather than
structure-scaled. The result it produced: ``docs/roadmap.md`` §M18.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, filters
from nqbt.sim.types import STOP_MIN_TICKS

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import EmaCrossoverParams
    from nqbt.trades import LegMatrix

NO_ATR = np.zeros(0, dtype=np.float64)
"""Stand-in for the ATR array in swing-stop mode, where the loop never indexes it.

Numba needs an array of the right dtype whether or not the branch reading it runs.
"""


class CrossoverRules(NamedTuple):
    """The scalar rule set :func:`simulate_crossover` reads, one field per parameter."""

    use_atr_stop: bool
    atr_stop_multiple: float
    min_bracket_points: float
    swing_lookback: int
    stop_offset_ticks: float
    tp_multiplier: float
    bars_required: int
    exit_on_opposite_cross: bool
    block_entry_at_session_close: bool


@njit(cache=True)
def simulate_crossover(  # noqa: C901, PLR0912, PLR0915 - one branch per rule, in bar order
    bars: bracket.Bars,
    signal: BoolArray,
    direction_at: FloatArray,
    atr: FloatArray,
    leg_quantities: IntArray,
    target_r: FloatArray,
    costs: bracket.Costs,
    fills: bracket.FillRules,
    rules: CrossoverRules,
    out: FloatArray,
) -> int:
    """Run the crossover archetype over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close schedules an entry for the next bar's open, and
    ``direction_at`` gives the prevailing regime on every bar -- ``LONG`` where the fast
    average is above the slow one. The two are separate because an entry needs both *when*
    and *which way*, and the control arm substitutes only the first.

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = bars.close.size
    n_legs = leg_quantities.size
    slippage = bracket.slippage_points(costs)
    min_risk = STOP_MIN_TICKS * costs.tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit = False
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
    trade = bracket.OpenTrade(0, 0, 0.0, 0.0, 0.0, d, True)
    stop = 0.0
    excursion = bracket.Excursion(0.0, 0.0)
    legs = bracket.Legs(
        np.zeros(n_legs, dtype=np.bool_),
        np.zeros(n_legs, dtype=np.float64),
        leg_quantities,
    )

    for i in range(n):
        # ---- exits ------------------------------------------------------------------
        if in_position and pending_exit:
            # The exit was submitted at the close of bar i-1 and fills at this bar's first
            # price, so the excursion stays where it was.
            fill = bars.open_[i] - d * slippage
            for leg in range(n_legs):
                if legs.is_open[leg]:
                    written = bracket.write_leg(
                        out,
                        written,
                        trade,
                        legs,
                        leg,
                        bracket.LegExit(i, fill, trades.EXIT_SIGNAL, False),
                        excursion,
                        costs,
                    )
                    if written < 0:
                        return -1
                    legs.is_open[leg] = False
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
        pending_exit = False

        # ---- the entry order fills at this bar's open, unconditionally ---------------
        if not in_position and pending_bar >= 0 and pending_bar == i - 1:
            # A force-flat bar is filled like any other; the session-close handler runs
            # after -- ``docs/nt8-fidelity.md``, "A resting entry fills on the force-flat
            # bar, and is flattened at its close".
            d = pending_direction
            fill = bars.open_[i] + d * slippage
            candidate_stop = _protective_stop(bars, atr, pending_bar, fill, d, rules, costs)
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
                for leg in range(n_legs):
                    legs.is_open[leg] = True
                    if np.isnan(target_r[leg]):
                        legs.target[leg] = np.nan
                    else:
                        # Measured from the fill: there is no trigger price.
                        raw = fill + d * candidate_risk * target_r[leg] * rules.tp_multiplier
                        legs.target[leg] = (
                            bracket.round_to_tick(raw, costs.tick_size) if fills.round_targets else raw
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

        # ---- close of bar i: schedule the next bar's orders --------------------------
        if in_position and rules.exit_on_opposite_cross and direction_at[i] != d:
            pending_exit = True
        if (
            i >= rules.bars_required
            and signal[i]
            and not (rules.block_entry_at_session_close and bars.force_flat[i])
            and (not in_position or pending_exit)
        ):
            # `pending_exit` is what makes the archetype bidirectional: without it the flip
            # closing a long could never itself open a short, and crosses alternate.
            pending_bar = i
            pending_direction = direction_at[i]

    # Anything still open when the series runs out is liquidated at the last bar.
    if in_position:
        last = n - 1
        exit_fill = bars.close[last] - d * slippage
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


@njit(cache=True)
def _protective_stop(
    bars: bracket.Bars,
    atr: FloatArray,
    signal_bar: int,
    fill: float,
    direction: float,
    rules: CrossoverRules,
    costs: bracket.Costs,
) -> float:
    """Where the protective stop goes, in whichever of the two modes is selected.

    Both read the **signal** bar and the bars before it, never the bar the fill happens on. The
    ATR mode hangs the stop off the fill, so planned risk is the ATR multiple or the dollar
    floor, whichever is wider; the swing mode uses the adverse extreme of the last
    ``swing_lookback`` completed bars plus the usual offset and is **not** floored, because its
    stop is a structural level rather than a distance.
    """
    if rules.use_atr_stop:
        distance = bracket.atr_bracket_distance(
            float(atr[signal_bar]),
            rules.atr_stop_multiple,
            rules.min_bracket_points,
        )
        return fill - direction * distance

    return bracket.swing_stop(
        bars,
        signal_bar,
        rules.swing_lookback,
        rules.stop_offset_ticks * costs.tick_size,
        direction,
    )


def regime_direction(fast: FloatArray, slow: FloatArray) -> FloatArray:
    """Which side the prevailing regime is on: ``LONG`` where ``fast > slow``, else ``SHORT``.

    The boundary matches :func:`nqbt.conditions.cross_above`'s. Defined on **every** bar rather
    than only on cross bars, so the random-entry arm can drop a signal anywhere and still know
    which side it would have been taken on.
    """
    return np.where(fast > slow, trades.LONG, trades.SHORT).astype(np.float64)


def crossover_averages(data: Dataset, params: EmaCrossoverParams) -> tuple[FloatArray, FloatArray]:
    """The fast and slow EMA values this combination compares.

    Read out of the shared grid, which is built with ``needs_ma_values`` for this archetype.
    """
    return (
        data.ma_values(params.fast_kind, params.fast_period),
        data.ma_values(params.slow_kind, params.slow_period),
    )


def crossover_signal(data: Dataset, params: EmaCrossoverParams) -> BoolArray:
    """Bars whose close schedules an entry for the next bar's open.

    Each side's cross is ANDed with the prevailing regime, which matters once
    ``cross_lookback > 1``: the window stays true for ``n`` bars and the averages can cross
    back inside it.
    """
    fast, slow = crossover_averages(data, params)
    direction: FloatArray = regime_direction(fast, slow)
    signal: BoolArray = np.zeros(len(data), dtype=np.bool_)
    if params.trade_long:
        signal |= conditions.cross_above(fast, slow, params.cross_lookback) & (direction == trades.LONG)
    if params.trade_short:
        signal |= conditions.cross_below(fast, slow, params.cross_lookback) & (direction == trades.SHORT)
    return filters.apply_context_filters(signal, data, params)


def crossover_legs(
    data: Dataset,
    params: EmaCrossoverParams,
    instrument: Instrument = MNQ,
   
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the regime
    series is *not* overridden, so a drawn bar is taken on whichever side the averages were on.
    """
    fast, slow = crossover_averages(data, params)
    direction_at: FloatArray = regime_direction(fast, slow)
    signal = crossover_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    targets: FloatArray = np.asarray(params.target_r_multiples, dtype=np.float64)
    atr: FloatArray = data.atr_values(params.atr_period) if params.use_atr_stop else NO_ATR
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = simulate_crossover(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
        direction_at,
        atr,
        quantities,
        targets,
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
        CrossoverRules(
            use_atr_stop=params.use_atr_stop,
            atr_stop_multiple=params.atr_stop_multiple,
            min_bracket_points=instrument.dollars_to_points(params.min_bracket_dollars),
            swing_lookback=params.swing_lookback,
            stop_offset_ticks=float(params.stop_offset_ticks),
            tp_multiplier=params.tp_multiplier,
            bars_required=params.bars_required_to_trade,
            exit_on_opposite_cross=params.exit_on_opposite_cross,
            block_entry_at_session_close=params.block_entry_at_session_close,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_crossover(
    data: Dataset,
    params: EmaCrossoverParams,
    instrument: Instrument = MNQ,
   
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = crossover_legs(data, params, instrument, signal=signal)
    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
