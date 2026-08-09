"""Wiring between cached bars, precomputed conditions and the jitted simulation.

:class:`Dataset` is built once per bar series and reused by every parameter combination in
a sweep. Everything expensive -- candlestick geometry, session VWAP, the moving-average
grids -- lives here, so a combination costs only a boolean AND plus one pass of the
simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from nqbt import conditions, indicators, sessions
from nqbt.conditions import MovingAverageGrid
from nqbt.instruments import MNQ, Instrument
from nqbt.sim import deadcat
from nqbt.sim.types import DeadCatParams, trades_to_frame


@dataclass(slots=True)
class Dataset:
    """Bars plus every condition a sweep might read, computed once."""

    bars: pd.DataFrame
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    force_flat: np.ndarray
    geometry: conditions.BarGeometry
    below_vwap: np.ndarray
    vwap: np.ndarray
    ema: MovingAverageGrid
    sma: MovingAverageGrid

    def __len__(self) -> int:
        return self.close.size

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.bars.index

    def slim(self) -> Dataset:
        """A copy carrying only what the simulation reads, for crossing a process boundary.

        ``bars`` is the expensive part -- seven columns over 1.65M rows -- and everything
        the sweep needs from it was already lifted into the plain arrays beside it. The
        one remaining use is the index, to stamp trade times, so an index-only frame is
        enough. Dropping the columns is what makes a parallel worker cheap to start.

        The arrays are shared, not copied: this is a view for shipping, not a deep copy.
        """
        return replace(self, bars=self.bars.iloc[:, :0])


def prepare(
    bars: pd.DataFrame,
    *,
    ema_periods=(21,),
    sma_periods=(60, 175),
    exit_on_close_seconds: int = 30,
    keep_ma_values: bool = False,
) -> Dataset:
    """Precompute everything the DeadCatBounce archetype reads.

    ``ema_periods`` and ``sma_periods`` must cover every value the sweep will ask for --
    the grids refuse a period they were not built for rather than returning a wrong row.
    """
    close = bars["close"].to_numpy(np.float64)
    info = sessions.classify(bars.index)
    force_flat = sessions.force_flat_mask(info, exit_on_close_seconds)

    typical = indicators.typical_price(
        bars["high"].to_numpy(np.float64), bars["low"].to_numpy(np.float64), close
    )
    vwap = indicators.session_vwap(
        typical,
        bars["volume"].to_numpy(np.float64),
        indicators.new_session_flags(bars["trading_day"].to_numpy()),
    )

    return Dataset(
        bars=bars,
        open=bars["open"].to_numpy(np.float64),
        high=bars["high"].to_numpy(np.float64),
        low=bars["low"].to_numpy(np.float64),
        close=close,
        force_flat=force_flat,
        geometry=conditions.bar_geometry(bars),
        below_vwap=conditions.below_series(close, vwap),
        vwap=vwap,
        ema=conditions.moving_average_grid(
            close, ema_periods, "ema", keep_values=keep_ma_values
        ),
        sma=conditions.moving_average_grid(
            close, sma_periods, "sma", keep_values=keep_ma_values
        ),
    )


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
