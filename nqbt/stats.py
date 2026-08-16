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

from nqbt.trades import EXIT_REASONS, EXIT_SESSION_CLOSE

TRADING_DAYS_PER_YEAR = 252

SESSION_CLOSE = EXIT_REASONS[EXIT_SESSION_CLOSE]
"""The ``exit_reason`` string for a position closed by the clock.

Read out of :data:`nqbt.trades.EXIT_REASONS` rather than spelled again here, so the label
and the code it maps from cannot drift apart. Importing :mod:`nqbt.trades` is within the
layering rule -- ``stats.py`` may not reach into :mod:`nqbt.sim`, but the trade schema is
what it is defined over.
"""


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
    session_close_share: float
    """Fraction of leg exits taken by the clock rather than by the strategy's own rules.

    Reported rather than buried in the trade log because a strategy taking 40% of its exits
    at the session close **is not the strategy its rules describe**, and no aggregate here
    says so -- the profit factor of such a run is largely a measurement of the flatten time.

    Flat-before-the-close is a prop-account rule, so this is never a bug to be fixed; it is
    a property of the archetype at that bar size. Expect it to rise sharply with resolution
    (#30): a position opened near the close has fewer and fewer bars in which to reach a
    target, so more of its outcomes are decided by the clock. Read it beside
    :attr:`ambiguous_share` whenever a coarse resolution looks profitable.

    Over **legs**, matching :attr:`ambiguous_share`'s denominator -- a leg exit is an exit.
    An imported real-fill log has an ``exit_reason`` NT8 wrote (``Stop1..4``, ``Exit``),
    none of which is this label, so it reports 0.0 rather than a wrong number."""
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
            columns=[
                "net_pnl",
                "commission",
                "bars_held",
                "mae_points",
                "mfe_points",
                "r_multiple",
                "ambiguous_bar",
                "entry_time",
                "exit_time",
            ],
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
        trades=len(t),
        legs=len(trades),
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
        # Indexed, not ``.get``-ed. ``validate`` requires ``exit_reason`` of every producer,
        # so a log without it is a wiring bug and should say so here rather than quietly
        # report 0.0 -- which would read as "this strategy never runs into the close".
        # That silent-branch shape is what #81 records against the Sharpe path above.
        session_close_share=float((trades["exit_reason"] == SESSION_CLOSE).mean()),
        commission_paid=float(trades["commission"].sum()),
    )


TRADE_PNL_STATISTICS = ("profit_factor", "net_pnl", "expectancy", "win_rate")
"""Statistics that depend on nothing but the per-trade P&L vector.

Which makes them the only ones a resampling test may permute: shuffling trades between
groups destroys entry and exit times, so anything time-dependent -- Sharpe, Sortino, max
drawdown, consecutive losses -- would be computed over an ordering that never happened.
"""


def trade_statistic(pnl: np.ndarray, name: str) -> float:
    """One :data:`TRADE_PNL_STATISTICS` value straight from a per-trade P&L vector.

    Exists so a resampling test can evaluate thousands of regroupings without paying for
    :func:`summarise` each time -- it is roughly two orders of magnitude cheaper.

    **It is not a second definition.** The division goes through the same ``_ratio``, and
    ``tests/test_dispersion.py`` asserts this returns exactly what :func:`summarise` does on
    real logs, for every name. :func:`summarise` remains the reference; if the two ever
    disagree, this one is wrong. Feed it :func:`per_trade` output, never raw legs.
    """
    if name not in TRADE_PNL_STATISTICS:
        msg = f"{name!r} cannot be computed from per-trade P&L alone; choose from {list(TRADE_PNL_STATISTICS)}"
        raise ValueError(
            msg,
        )
    if pnl.size == 0:
        return 0.0
    wins = pnl > 0
    if name == "profit_factor":
        return _ratio(float(pnl[wins].sum()), float(-pnl[pnl < 0].sum()))
    if name == "net_pnl":
        return float(pnl.sum())
    if name == "expectancy":
        return float(pnl.mean())
    return float(wins.mean())


def leg_summary(trades: pd.DataFrame) -> dict:
    """NT8's view: every named entry counted as its own trade.

    Only for reconciling against Strategy Analyzer, whose "Total # of trades" is the leg
    count rather than the number of decisions.
    """
    pnl = trades["net_pnl"]
    wins, losses = pnl > 0, pnl < 0
    equity = pnl.cumsum()
    return {
        "legs": len(trades),
        "wins": int(wins.sum()),
        "losses": int(losses.sum()),
        "scratches": int((pnl == 0).sum()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": _ratio(float(pnl[wins].sum()), float(-pnl[losses].sum())),
        "max_drawdown": _max_drawdown(equity),
        "avg_trade": float(pnl.mean()),
    }
