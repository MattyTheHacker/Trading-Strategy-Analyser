"""Tier 1 strategy research and backtesting tool for NQ/MNQ futures.

This package narrows a wide parameter search down to a shortlist of candidates fast.
It deliberately matches NinjaTrader 8's *default* backtest fidelity (bar-close OHLC
fills, no intrabar tick precision) so that results here can be attributed cleanly when
re-validated in NT8 Strategy Analyzer, which remains the ground truth.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = ()

__version__ = "0.1.0"
