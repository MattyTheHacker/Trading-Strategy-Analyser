"""Summary statistics for a trade log.

Everything here is computed **per trade**, not per leg. A four-leg entry that scales out
is one decision and one risk event; counting it as four trades would quadruple the sample
size and make a win rate meaningless. :func:`summarise` aggregates legs by ``trade_id``
first, so the numbers line up with how a person would count.

NT8's own summary counts each named entry separately, so its "total trades" is the leg
count. :func:`leg_summary` reproduces that view when reconciling against Strategy Analyzer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import get_type_hints

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass(slots=True)
class Summary:
    """Performance of one parameter combination."""

    trades: int
    legs: int
    wins: int
    losses: int
    scratches: int
    win_rate: float
    net_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    max_drawdown: float
    max_consecutive_losses: int
    avg_bars_held: float
    avg_mae_points: float
    avg_mfe_points: float
    mean_r: float
    r_p10: float
    r_median: float
    r_p90: float
    sharpe: float
    sortino: float
    ambiguous_share: float
    """Fraction of leg exits on a bar that held both the stop and a target.

    The one statistic that says how much of the result rests on an assumption the bar data
    cannot settle. A candidate with a high share deserves a second look before Tier 2."""
    commission_paid: float

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    @classmethod
    def empty(cls) -> Summary:
        """The zero summary, for a combination that produced no trades.

        Keyed by field name and typed from the annotations rather than splatted
        positionally: the version this replaces passed 26 arguments into a 28-field
        dataclass and raised on every call, which went unnoticed because the only caller
        had grown a second, divergent empty-log policy of its own. A constructor that
        cannot be miscounted is the point, so do not "simplify" it back to a splat.
        """
        hints = get_type_hints(cls)
        return cls(**{f.name: 0 if hints[f.name] is int else 0.0 for f in fields(cls)})


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float((equity.cummax() - equity).max())


def _max_consecutive(mask: pd.Series) -> int:
    """Longest run of True values."""
    if mask.empty or not mask.any():
        return 0
    groups = (~mask).cumsum()
    return int(mask.groupby(groups).cumsum().max())


def _ratio(numerator: float, denominator: float) -> float:
    """Guarded division that reports a run with no losses as infinite rather than crashing."""
    if denominator == 0:
        return float("inf") if numerator > 0 else 0.0
    return numerator / denominator


def _risk_adjusted(daily: pd.Series) -> tuple[float, float]:
    """Annualised Sharpe and Sortino from daily P&L.

    Computed on daily totals rather than per trade: a per-trade Sharpe rewards taking many
    tiny trades and is not comparable across combinations with different trade counts.
    """
    if len(daily) < 2:
        return 0.0, 0.0
    mean = daily.mean()
    sd = daily.std(ddof=1)
    downside = daily[daily < 0]
    dsd = downside.std(ddof=1) if len(downside) > 1 else 0.0
    scale = np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = float(mean / sd * scale) if sd > 0 else 0.0
    sortino = float(mean / dsd * scale) if dsd and dsd > 0 else 0.0
    return sharpe, sortino


def per_trade(trades: pd.DataFrame) -> pd.DataFrame:
    """Collapse leg exits into one row per trade."""
    if trades.empty:
        return pd.DataFrame(
            columns=["net_pnl", "commission", "bars_held", "mae_points", "mfe_points",
                     "r_multiple", "ambiguous_bar", "entry_time", "exit_time"]
        )
    agg = {
        "net_pnl": ("net_pnl", "sum"),
        "commission": ("commission", "sum"),
        "bars_held": ("bars_held", "max"),
        "mae_points": ("mae_points", "max"),
        "mfe_points": ("mfe_points", "max"),
        "r_multiple": ("r_multiple", "mean"),
        "ambiguous_bar": ("ambiguous_bar", "any"),
    }
    if "entry_time" in trades.columns:
        agg["entry_time"] = ("entry_time", "first")
        agg["exit_time"] = ("exit_time", "max")
    return trades.groupby("trade_id").agg(**agg)


def summarise(trades: pd.DataFrame) -> Summary:
    """Reduce a leg-level trade log to one row of performance statistics."""
    if trades.empty:
        return Summary.empty()

    t = per_trade(trades)
    pnl = t["net_pnl"]
    wins, losses = pnl > 0, pnl < 0
    equity = pnl.cumsum()

    if "entry_time" in t.columns:
        daily = pnl.groupby(pd.DatetimeIndex(t["exit_time"]).date).sum()
    else:  # pragma: no cover - only when times were not attached
        daily = pnl
    sharpe, sortino = _risk_adjusted(daily)

    r = trades["r_multiple"].replace([np.inf, -np.inf], np.nan).dropna()

    return Summary(
        trades=int(len(t)),
        legs=int(len(trades)),
        wins=int(wins.sum()),
        losses=int(losses.sum()),
        scratches=int((pnl == 0).sum()),
        win_rate=float(wins.mean()),
        net_pnl=float(pnl.sum()),
        gross_profit=float(pnl[wins].sum()),
        gross_loss=float(pnl[losses].sum()),
        profit_factor=_ratio(float(pnl[wins].sum()), float(-pnl[losses].sum())),
        expectancy=float(pnl.mean()),
        avg_win=float(pnl[wins].mean()) if wins.any() else 0.0,
        avg_loss=float(pnl[losses].mean()) if losses.any() else 0.0,
        largest_win=float(pnl.max()),
        largest_loss=float(pnl.min()),
        max_drawdown=_max_drawdown(equity),
        max_consecutive_losses=_max_consecutive(losses),
        avg_bars_held=float(t["bars_held"].mean()),
        avg_mae_points=float(t["mae_points"].mean()),
        avg_mfe_points=float(t["mfe_points"].mean()),
        mean_r=float(r.mean()) if len(r) else 0.0,
        r_p10=float(r.quantile(0.10)) if len(r) else 0.0,
        r_median=float(r.median()) if len(r) else 0.0,
        r_p90=float(r.quantile(0.90)) if len(r) else 0.0,
        sharpe=sharpe,
        sortino=sortino,
        ambiguous_share=float(trades["ambiguous_bar"].mean()),
        commission_paid=float(trades["commission"].sum()),
    )


def leg_summary(trades: pd.DataFrame) -> dict:
    """NT8's view: every named entry counted as its own trade.

    Only for reconciling against Strategy Analyzer, whose "Total # of trades" is the leg
    count rather than the number of decisions.
    """
    pnl = trades["net_pnl"]
    wins, losses = pnl > 0, pnl < 0
    equity = pnl.cumsum()
    return {
        "legs": int(len(trades)),
        "wins": int(wins.sum()),
        "losses": int(losses.sum()),
        "scratches": int((pnl == 0).sum()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": _ratio(float(pnl[wins].sum()), float(-pnl[losses].sum())),
        "max_drawdown": _max_drawdown(equity),
        "avg_trade": float(pnl.mean()),
    }
