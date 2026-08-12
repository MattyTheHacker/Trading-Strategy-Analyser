"""Wiring between a prepared :class:`~nqbt.context.Dataset` and the jitted simulation.

Everything strategy-specific about DeadCatBounce that is not inside the ``@njit`` loop
lives here: which precomputed gates the signal ANDs together, and how a
:class:`~nqbt.sim.types.DeadCatParams` becomes the loop's scalar arguments. The market
context itself is built once by :func:`nqbt.context.prepare` and reused by every
combination in a sweep.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nqbt.context import Dataset
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import deadcat
from nqbt.sim.types import DeadCatParams
from nqbt.trades import trades_to_frame


def deadcat_signal(data: Dataset, params: DeadCatParams) -> np.ndarray:
    """Conjunction of every active entry filter.

    The inverted hammer is not optional -- ``DeadCatBounce.cs`` has no toggle for it, so
    it anchors the signal and the switchable filters narrow it from there.
    """
    signal = data.geometry.inverted_hammer.copy()
    if params.require_new_high:
        signal &= data.geometry.made_new_high
    if params.require_previous_green:
        signal &= data.geometry.previous_bar_green
    if params.use_ema:
        signal &= data.ema.below_for(params.ema_period)
    if params.use_slow_sma:
        signal &= data.sma.below_for(params.slow_sma_period)
    if params.use_fast_sma:
        signal &= data.sma.below_for(params.fast_sma_period)
    if params.use_vwap:
        signal &= data.below_vwap
    return signal


def run_deadcat(
    data: Dataset,
    params: DeadCatParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log."""
    signal = deadcat_signal(data, params)
    quantities = np.asarray(params.leg_quantities, dtype=np.int64)
    targets = np.asarray(params.target_r_multiples, dtype=np.float64)
    out = deadcat.allocate_output(int(signal.sum()), quantities.size)

    count = deadcat.simulate_deadcat(
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
        float(params.entry_offset_ticks),
        params.tp_multiplier,
        float(params.max_risk_ticks),
        params.commission_per_contract,
        params.slippage_ticks,
        params.bars_required_to_trade,
        params.min_reward_risk,
        params.ratchet_lag,
        params.block_entry_at_session_close,
        params.fill_limit_on_touch,
        params.ambiguity_policy,
        out,
    )
    if count < 0:  # pragma: no cover - allocation is a proven upper bound
        raise RuntimeError(
            "trade buffer overflowed; allocate_output's signal-count bound was violated"
        )

    return trades_to_frame(out, count, data.index if with_times else None)
