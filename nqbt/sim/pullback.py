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
        signal &= data.ma_gate("ema", params.ema_period, above=True)
    if params.use_fast_sma:
        signal &= data.ma_gate("sma", params.fast_sma_period, above=True)
    if params.use_slow_sma:
        signal &= data.ma_gate("sma", params.slow_sma_period, above=True)
    if params.use_vwap:
        signal &= data.vwap_gate(above=True)
    return filters.apply_context_filters(signal, data, params)


def pullbackandgo_legs(
    data: Dataset,
    params: PullBackAndGoParams,
    instrument: Instrument = MNQ,
    *,
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
        data.open,
        data.high,
        data.low,
        data.close,
        signal,
        data.force_flat,
        quantities,
        targets,
        instrument.tick_size,
        instrument.point_value,
        float(params.stop_offset_ticks),
        0.0,  # entry_offset_ticks: no close-based trigger cap; trigger is bare High[0]
        1.0,  # tp_multiplier: PullBackAndGo.cs has no TPMultiplier property
        float("inf"),  # max_risk_ticks: no MaxRiskPerTrade property, so no cap
        params.commission_per_contract,
        params.slippage_ticks,
        params.bars_required_to_trade,
        0.0,  # min_reward_risk: no property on PullBackAndGo.cs
        params.ratchet_lag,
        float(params.ratchet_offset_ticks),
        params.block_entry_at_session_close,
        params.fill_limit_on_touch,
        params.ambiguity_policy,
        trades.LONG,
        params.round_targets,
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
    *,
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
