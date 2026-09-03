"""Wiring between a prepared :class:`~nqbt.context.Dataset` and the jitted simulation.

Everything strategy-specific about DeadCatBounce that is not inside the ``@njit`` loop: which
precomputed gates the signal ANDs together, and how a
:class:`~nqbt.sim.types.DeadCatParams` becomes the loop's scalar arguments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nqbt import trades
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import bracket, deadcat, filters

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.context import Dataset
    from nqbt.sim.types import DeadCatParams
    from nqbt.trades import LegMatrix


def deadcat_signal(data: Dataset, params: DeadCatParams) -> BoolArray:
    """Conjunction of every active entry filter.

    The inverted hammer is not optional -- ``DeadCatBounce.cs`` has no toggle for it.
    """
    signal: BoolArray = data.geometry.inverted_hammer.copy()
    if params.require_new_high:
        signal &= data.geometry.made_new_high

    if params.require_previous_green:
        signal &= data.geometry.previous_bar_green

    if params.use_ema:
        signal &= data.ma_gate(params.ema_kind, params.ema_period, above=False)

    if params.use_slow_sma:
        signal &= data.ma_gate(params.slow_sma_kind, params.slow_sma_period, above=False)

    if params.use_fast_sma:
        signal &= data.ma_gate(params.fast_sma_kind, params.fast_sma_period, above=False)

    if params.use_vwap:
        signal &= data.vwap_gate(above=False)

    return filters.apply_context_filters(signal, data, params)


def deadcat_legs(
    data: Dataset,
    params: DeadCatParams,
    instrument: Instrument = MNQ,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    The producer boundary for a caller that only wants statistics; :func:`run_deadcat` is the
    same simulation with the frame built on top.

    ``signal`` overrides the computed entry signal, which is what the random-entry control arm
    substitutes so that it runs **this** function rather than its own copy of the simulation.
    """
    signal = deadcat_signal(data, params) if signal is None else signal
    quantities: IntArray = np.asarray(params.leg_quantities, dtype=np.int64)
    targets: FloatArray = np.asarray(params.target_r_multiples, dtype=np.float64)
    out: FloatArray = bracket.allocate_output(int(signal.sum()), quantities.size)

    count: int = deadcat.simulate_deadcat(
        bracket.Bars(data.open, data.high, data.low, data.close, data.force_flat),
        signal,
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
            round_targets=True,  # DeadCatBounce.cs rounds every target with RoundToTickSize
        ),
        deadcat.DeadCatRules(
            stop_offset_ticks=float(params.stop_offset_ticks),
            entry_offset_ticks=float(params.entry_offset_ticks),
            tp_multiplier=params.tp_multiplier,
            max_risk_ticks=float(params.max_risk_ticks),
            bars_required=params.bars_required_to_trade,
            min_reward_risk=params.min_reward_risk,
            ratchet_lag=params.ratchet_lag,
            # The ratchet reapplies the same offset as the entry.
            ratchet_offset_ticks=float(params.stop_offset_ticks),
            block_entry_at_session_close=params.block_entry_at_session_close,
            direction=trades.SHORT,  # DeadCatBounce has no long variant; PullBackAndGo does.
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_deadcat(
    data: Dataset,
    params: DeadCatParams,
    instrument: Instrument = MNQ,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = deadcat_legs(data, params, instrument, signal=signal)

    return trades.validate(
        trades.trades_to_frame(
            matrix=legs.matrix,
            count=legs.count,
            instrument=instrument.symbol,
            index=data.index if with_times else None,
            source="sim",
        ),
    )
