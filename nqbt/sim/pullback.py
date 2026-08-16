"""PullBackAndGo archetype: buy a hammer pulling back into an established uptrend.

Ported from ``ninjatrader-scripts/Strategies/PullBackAndGo.cs`` as the long-side proof for
M15's direction generalisation -- the exact mirror of DeadCatBounce's entry mechanism
(``EnterLongStopMarket`` where DeadCatBounce uses ``EnterShortStopMarket``), chosen
specifically because it has C# to reconcile against (M15.5) rather than being an original
archetype nothing can be checked against.

Reuses :func:`nqbt.sim.deadcat.simulate_deadcat` -- the shared bracket engine, not a fork of
it -- with ``direction=LONG`` and the handful of parameters where the two strategies
genuinely differ rather than merely mirror. See :class:`nqbt.sim.types.PullBackAndGoParams`
for what those are and why each one is not swept as a DeadCatBounce-shaped field.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nqbt import trades
from nqbt.context import Dataset
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import deadcat
from nqbt.sim.types import PullBackAndGoParams


def pullback_signal(data: Dataset, params: PullBackAndGoParams) -> np.ndarray:
    """Conjunction of every active entry condition.

    The hammer is the only unconditional one; every other filter has a ``Use*`` or
    ``Require*`` property behind it, each its own early-return ``if`` in the C# rather than
    one combined condition, so switching one off leaves the rest exactly as they were.
    """
    signal = data.geometry.hammer.copy()
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
    return signal


def run_pullbackandgo(
    data: Dataset,
    params: PullBackAndGoParams,
    instrument: Instrument = MNQ,
    *,
    with_times: bool = True,
    signal: np.ndarray | None = None,
) -> pd.DataFrame:
    """Simulate one parameter combination and return its leg-level trade log.

    ``signal`` overrides the computed entry signal -- see :func:`nqbt.sim.runner.run_deadcat`
    for why the random-entry control arm injects one here rather than calling
    ``simulate_deadcat`` itself.
    """
    signal = pullback_signal(data, params) if signal is None else signal
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
        raise RuntimeError(
            "trade buffer overflowed; allocate_output's signal-count bound was violated"
        )

    return trades.validate(
        trades.trades_to_frame(
            out,
            count,
            data.index if with_times else None,
            instrument=instrument.symbol,
            source="sim",
        )
    )
