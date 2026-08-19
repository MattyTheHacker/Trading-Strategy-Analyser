"""EmaCrossover archetype: the first original, and a deliberate known-negative control.

**There is no NinjaScript.** MA crossover on 1-minute index futures is the most-tested idea
in retail futures and is reliably unprofitable at realistic costs, so writing the C# before
a candidate looks worth trading would spend the scarce resource on a result already known.
That makes this ``Tier2Status.TIER1_ONLY``, and it is what the results column is for: a
ranking that puts this beside DeadCatBounce is comparing an assumption against a
measurement unless the column says so.

**If it reads meaningfully better than the random-entry arm, the first hypothesis is a bug**
-- specifically lookahead, since a crossover is unusually easy to compute one bar early.
Every series this reads is stamped from completed bars: the cross from bars ``<= i``, the
ATR from the signal bar, the fill from the *next* bar's open.

What it exercises that nothing else does:

**The third entry mechanism.** DeadCatBounce rests a stop-market order for one bar and
PullBackAndGo mirrors it; this enters market-on-next-open. There is no trigger price and no
"no touch, no fill" -- the fill is ``open[i+1] + d * slippage`` and it is unconditional. The
only thing that stops it is the flatten point, which cancels the order exactly as it cancels
a resting one.

**A signal exit.** ``EXIT_SIGNAL`` -- a rule-driven exit with no bracket level of its own.
The regime flip is detected at the close of bar ``i`` and the market exit fills at the open
of bar ``i+1``, which is the same next-open convention the entry uses. It takes precedence
over the stop and the targets on that bar, because it is filled at the bar's first price and
NT8's managed approach cancels the brackets when a position is flattened.

**Both sides.** ``direction`` is per bar rather than per run, which is what M15 generalised
the bracket engine for.

**Flat between trades, not stop-and-reverse.** The classic form reverses in one order. Here
the flip closes the position and opens the new one as two separate fills at the same open
price, each paying its own slippage and commission and each appearing as its own trade. The
economics are a reversal; the accounting is two trades, and any comparison against published
crossover results has to say so.

**R means something different here.** ``r_multiple`` is measured against ``stop - entry``,
which with an ATR stop is volatility-scaled rather than structure-scaled, so a 2R target is
not DeadCatBounce's 2R. Same trap as comparing profit factor across bar resolutions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numba import njit

from nqbt import conditions, trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket
from nqbt.sim.types import STOP_MIN_TICKS

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.context import Dataset
    from nqbt.sim.types import EmaCrossoverParams

NO_ATR = np.zeros(0, dtype=np.float64)
"""Stand-in for the ATR array in swing-stop mode, where the loop never indexes it.

Numba needs an array of the right dtype whether or not the branch that reads it runs, and an
empty one costs nothing -- the alternative is building an ATR the combination will not use.
"""


@njit(cache=True)
def simulate_crossover(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signal: np.ndarray,
    direction_at: np.ndarray,
    force_flat: np.ndarray,
    atr: np.ndarray,
    leg_quantities: np.ndarray,
    target_r: np.ndarray,
    tick_size: float,
    point_value: float,
    use_atr_stop: bool,
    atr_stop_multiple: float,
    swing_lookback: int,
    stop_offset_ticks: float,
    tp_multiplier: float,
    commission_per_contract: float,
    slippage_ticks: float,
    bars_required: int,
    exit_on_opposite_cross: bool,
    block_entry_at_session_close: bool,
    fill_limit_on_touch: bool,
    ambiguity_policy: int,
    round_targets: bool,
    out: np.ndarray,
) -> int:
    """Run the crossover archetype over one dataset, writing one row per leg exit.

    ``signal`` marks bars whose close schedules an entry for the next bar's open, and
    ``direction_at`` gives the prevailing regime on every bar -- ``LONG`` where the fast
    average is above the slow one. The two are separate because an entry needs both *when*
    and *which way*, and the control arm substitutes only the first.

    Returns the number of rows written, or ``-1`` if ``out`` overflowed.
    """
    n = close.size
    n_legs = leg_quantities.size
    slippage = slippage_ticks * tick_size
    stop_offset = stop_offset_ticks * tick_size
    min_risk = STOP_MIN_TICKS * tick_size

    written = 0
    trade_id = 0

    in_position = False
    pending_exit = False
    pending_bar = -1
    pending_direction = 0.0

    d = 0.0
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
        # ---- exits ------------------------------------------------------------------
        if in_position and pending_exit:
            # The regime flipped at the close of bar i-1, so a market exit was submitted
            # then and fills here at the bar's first price. run_high/run_low are left where
            # they were: the position closed at the open, so the rest of this bar's range
            # never applied to it.
            fill = open_[i] - d * slippage
            for leg in range(n_legs):
                if leg_open[leg]:
                    written = bracket.write_leg(
                        out,
                        written,
                        trade_id,
                        leg,
                        entry_bar,
                        i,
                        entry_price,
                        fill,
                        initial_stop,
                        leg_target[leg],
                        leg_quantities[leg],
                        trades.EXIT_SIGNAL,
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
                    leg_open[leg] = False
            in_position = False
        elif in_position:
            run_high = max(run_high, high[i])
            run_low = min(run_low, low[i])
            written, in_position = bracket.resolve_brackets(
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
                d,
                True,  # held since this bar's open, so a gap through the stop fills at it
            )
            if written < 0:
                return -1
        pending_exit = False

        # ---- the entry order fills at this bar's open, unconditionally ---------------
        if not in_position and pending_bar >= 0 and pending_bar == i - 1:
            # A bar at or past the flatten cutoff cancels the order rather than filling it,
            # exactly as it cancels a resting stop-market entry.
            if not force_flat[i]:
                d = pending_direction
                fill = open_[i] + d * slippage
                candidate_stop = _protective_stop(
                    high,
                    low,
                    atr,
                    pending_bar,
                    fill,
                    d,
                    use_atr_stop,
                    atr_stop_multiple,
                    swing_lookback,
                    stop_offset,
                )
                candidate_risk = d * (fill - candidate_stop)
                # A stop at or through the price it protects is not a stop order. Reachable
                # here and not in the ported archetypes: this entry has no trigger to anchor
                # the stop to, and the swing reference can be gapped straight through.
                if candidate_risk >= min_risk:
                    trade_id += 1
                    entry_price = fill
                    entry_bar = i
                    initial_stop = candidate_stop
                    stop = candidate_stop
                    risk = candidate_risk
                    run_high = high[i]
                    run_low = low[i]
                    for leg in range(n_legs):
                        leg_open[leg] = True
                        if np.isnan(target_r[leg]):
                            leg_target[leg] = np.nan
                        else:
                            # Measured from the fill, not from a trigger: there is no
                            # trigger price, so the fill is the only reference there is.
                            raw = fill + d * risk * target_r[leg] * tp_multiplier
                            leg_target[leg] = bracket.round_to_tick(raw, tick_size) if round_targets else raw
                    written, in_position = bracket.resolve_brackets(
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
                        d,
                        True,  # filled at this bar's open, so it is held from the open
                    )
                    if written < 0:
                        return -1
            pending_bar = -1

        # ---- close of bar i: schedule the next bar's orders --------------------------
        if in_position and exit_on_opposite_cross and direction_at[i] != d:
            pending_exit = True
        if (
            i >= bars_required
            and signal[i]
            and not (block_entry_at_session_close and force_flat[i])
            and (not in_position or pending_exit)
        ):
            # `pending_exit` is what makes the archetype bidirectional. Without it the flip
            # that closes a long would have to be followed by a second cross the same way
            # before anything went short, and with the default one-bar lookback there never
            # is one -- crosses alternate, so the strategy would only ever go long.
            pending_bar = i
            pending_direction = direction_at[i]

    # Anything still open when the series runs out is liquidated at the last bar rather
    # than dropped, exactly as the stop-market loop does.
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
                    initial_stop,
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


@njit(cache=True)
def _protective_stop(
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    signal_bar: int,
    fill: float,
    direction: float,
    use_atr_stop: bool,
    atr_stop_multiple: float,
    swing_lookback: int,
    stop_offset: float,
) -> float:
    """Where the protective stop goes, in whichever of the two modes is selected.

    Both read the **signal** bar and the bars before it, never the bar the fill happens on.

    The ATR mode hangs the stop off the fill, so planned risk is exactly ``atr * multiple``.
    The swing mode anchors it to the adverse extreme of the last ``swing_lookback``
    completed bars plus the usual two-tick offset, which is the closest thing a crossover
    has to DeadCatBounce's structural stop -- a crossover has no signal wick, which is the
    whole reason #37 exists.
    """
    if use_atr_stop:
        return fill - direction * atr[signal_bar] * atr_stop_multiple

    start = signal_bar - swing_lookback + 1
    start = max(start, 0)
    extreme = 0.0
    for j in range(start, signal_bar + 1):
        adverse, _ = bracket.sided(low[j], high[j], direction)
        if j == start or direction * adverse < direction * extreme:
            extreme = adverse
    return extreme - direction * stop_offset


def regime_direction(fast: np.ndarray, slow: np.ndarray) -> np.ndarray:
    """Which side the prevailing regime is on: ``LONG`` where ``fast > slow``, else ``SHORT``.

    The boundary matches :func:`nqbt.conditions.cross_above`'s -- strictly greater is long,
    so a bar where the two are equal reads short and a cross above it still counts.

    Defined on **every** bar rather than only on cross bars, which is what lets the
    random-entry control arm drop a signal on an arbitrary bar and still know which side it
    would have been taken on. It lives here rather than in :mod:`nqbt.conditions` because
    ``LONG``/``SHORT`` are trade concepts and the market-context layer does not import them.
    """
    return np.where(fast > slow, trades.LONG, trades.SHORT).astype(np.float64)


def crossover_averages(data: Dataset, params: EmaCrossoverParams) -> tuple[np.ndarray, np.ndarray]:
    """The fast and slow EMA values this combination compares.

    Read out of the shared grid rather than recomputed. The grid is built with
    ``needs_ma_values`` because this archetype compares two averages to each other rather
    than the close to one of them, which no boolean gate can answer.
    """
    return (
        data.ma_values("ema", params.fast_period),
        data.ma_values("ema", params.slow_period),
    )


def crossover_signal(data: Dataset, params: EmaCrossoverParams) -> np.ndarray:
    """Bars whose close schedules an entry for the next bar's open.

    Each side's cross is ANDed with the prevailing regime, which matters only when
    ``cross_lookback > 1``: the window stays true for ``n`` bars after the cross, and the
    averages can cross back inside it. Without the AND a stale cross-above would enter long
    on a bar the fast average had already fallen back below the slow one.
    """
    fast, slow = crossover_averages(data, params)
    direction = regime_direction(fast, slow)
    signal = np.zeros(len(data), dtype=np.bool_)
    if params.trade_long:
        signal |= conditions.cross_above(fast, slow, params.cross_lookback) & (direction == trades.LONG)
    if params.trade_short:
        signal |= conditions.cross_below(fast, slow, params.cross_lookback) & (direction == trades.SHORT)
    return signal


def crossover_legs(
    data: Dataset,
    params: EmaCrossoverParams,
    instrument: Instrument = MNQ,
    *,
    signal: np.ndarray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal for the random-entry control arm; the
    regime series is *not* overridden, so a drawn bar is taken on whichever side the
    averages were on at that bar. That is what lets the null match this archetype on entry
    count and time of session without inventing a direction rule of its own.
    """
    fast, slow = crossover_averages(data, params)
    direction_at = regime_direction(fast, slow)
    signal = crossover_signal(data, params) if signal is None else signal
    quantities = np.asarray(params.leg_quantities, dtype=np.int64)
    targets = np.asarray(params.target_r_multiples, dtype=np.float64)
    atr = data.atr_values(params.atr_period) if params.use_atr_stop else NO_ATR
    out = bracket.allocate_output(int(signal.sum()), quantities.size)

    count = simulate_crossover(
        data.open,
        data.high,
        data.low,
        data.close,
        signal,
        direction_at,
        data.force_flat,
        atr,
        quantities,
        targets,
        instrument.tick_size,
        instrument.point_value,
        params.use_atr_stop,
        params.atr_stop_multiple,
        params.swing_lookback,
        float(params.stop_offset_ticks),
        params.tp_multiplier,
        params.commission_per_contract,
        params.slippage_ticks,
        params.bars_required_to_trade,
        params.exit_on_opposite_cross,
        params.block_entry_at_session_close,
        params.fill_limit_on_touch,
        params.ambiguity_policy,
        params.round_targets,
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_crossover(
    data: Dataset,
    params: EmaCrossoverParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: np.ndarray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs = crossover_legs(data, params, instrument, signal=signal)
    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
