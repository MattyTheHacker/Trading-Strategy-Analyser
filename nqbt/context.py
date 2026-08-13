"""Market context: bars plus every derived condition, computed once and shared.

This is the half of a backtest that has nothing to do with a strategy. The same
:class:`Dataset` serves every parameter combination of a sweep, every archetype, and --
once the review layer exists -- the annotation of real trades against the market they
happened in. Nothing here knows what a trade is; :mod:`nqbt.trades` owns that, and the
two never import each other.

Everything expensive lives here -- candlestick geometry, session VWAP, the moving-average
grids -- so a combination costs only a boolean AND plus one pass of the simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from nqbt import conditions, indicators, sessions
from nqbt.conditions import MovingAverageGrid


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
    """Precompute every condition an archetype might read.

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
