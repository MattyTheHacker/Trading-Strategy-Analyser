"""PullBackAndGo archetype: buy a hammer pulling back into an established uptrend.

Ported from ``ninjatrader-scripts/Strategies/PullBackAndGo.cs``, the exact mirror of
DeadCatBounce's entry mechanism. Reuses :func:`nqbt.sim.deadcat.simulate_deadcat` itself, not a
fork of it, with ``direction=LONG`` and the handful of parameters where the two strategies
genuinely differ -- see :class:`nqbt.sim.types.PullBackAndGoParams`.
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
    from nqbt.sim.types import PullBackAndGoParams
    from nqbt.trades import LegMatrix


def pullback_signal(data: Dataset, params: PullBackAndGoParams) -> BoolArray:
    """Conjunction of every active entry condition. The hammer is the only unconditional one."""
    signal: BoolArray = data.geometry.hammer.copy()
    if params.require_new_low:
        signal &= data.geometry.made_new_low
    if params.require_previous_red:
        signal &= data.geometry.previous_bar_red
    if params.use_ema:
        signal &= data.ma_gate(params.ema_kind, params.ema_period, above=True)
    if params.use_fast_sma:
        signal &= data.ma_gate(params.fast_sma_kind, params.fast_sma_period, above=True)
    if params.use_slow_sma:
        signal &= data.ma_gate(params.slow_sma_kind, params.slow_sma_period, above=True)
    if params.use_vwap:
        signal &= data.vwap_gate(above=True)
    return filters.apply_context_filters(signal, data, params)


def pullbackandgo_legs(
    data: Dataset,
    params: PullBackAndGoParams,
    instrument: Instrument = MNQ,
    signal: BoolArray | None = None,
) -> trades.LegMatrix:
    """Simulate one parameter combination and return its raw leg matrix.

    ``signal`` overrides the computed entry signal -- see :func:`nqbt.sim.runner.deadcat_legs`
    for why the random-entry control arm injects one here rather than calling
    ``simulate_deadcat`` itself.
    """
    signal = pullback_signal(data, params) if signal is None else signal
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
            round_targets=params.round_targets,
        ),
        deadcat.DeadCatRules(
            stop_offset_ticks=float(params.stop_offset_ticks),
            # No close-based trigger cap: the trigger is a bare High[0].
            entry_offset_ticks=0.0,
            tp_multiplier=1.0,  # PullBackAndGo.cs has no TPMultiplier property
            max_risk_ticks=float("inf"),  # no MaxRiskPerTrade property, so no cap
            bars_required=params.bars_required_to_trade,
            min_reward_risk=0.0,  # no property on PullBackAndGo.cs
            ratchet_lag=params.ratchet_lag,
            ratchet_offset_ticks=float(params.ratchet_offset_ticks),
            block_entry_at_session_close=params.block_entry_at_session_close,
            direction=trades.LONG,
        ),
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        msg: str = "trade buffer overflowed; allocate_output's signal-count bound was violated"
        raise RuntimeError(msg)

    return trades.validate_legs(trades.LegMatrix(out, count))


def run_pullbackandgo(
    data: Dataset,
    params: PullBackAndGoParams,
    instrument: Instrument = MNQ,
    with_times: bool = True,
    signal: BoolArray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    legs: LegMatrix = pullbackandgo_legs(data, params, instrument, signal=signal)
    return trades.validate(
        trades.trades_to_frame(
            legs.matrix,
            legs.count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        ),
    )
