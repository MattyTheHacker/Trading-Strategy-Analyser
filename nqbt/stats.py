"""Summary statistics for a trade log.

Everything here is computed **per trade**, not per leg: a four-leg entry that scales out is one
decision and one risk event. NT8's own summary counts each named entry separately, so
:func:`leg_summary` reproduces that view when reconciling against Strategy Analyzer.

Two functions arrive at the same :class:`Summary`. :func:`summarise` reads a trade-log
DataFrame and is the reference; :func:`summarise_legs` reads the raw
:class:`~nqbt.trades.LegMatrix` and never builds one. They share every statistic through
:func:`_summarise_arrays` and differ only in how the per-trade vectors are obtained, so the one
thing that can drift is the grouping -- ``docs/roadmap.md`` §"The numpy-native summary path".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import get_type_hints

import numpy as np
import pandas as pd
from numba import njit

from nqbt.trades import (
    C_AMBIGUOUS,
    C_BARS_HELD,
    C_COMMISSION,
    C_EXIT_BAR,
    C_EXIT_REASON,
    C_MAE,
    C_MFE,
    C_NET_PNL,
    C_R_MULTIPLE,
    C_TRADE_ID,
    EXIT_REASONS,
    EXIT_SESSION_CLOSE,
    LegMatrix,
)

TRADING_DAYS_PER_YEAR = 252

SESSION_CLOSE = EXIT_REASONS[EXIT_SESSION_CLOSE]
"""The ``exit_reason`` string for a position closed by the clock.

Read out of :data:`nqbt.trades.EXIT_REASONS` so the label and its code cannot drift apart.
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

    How much of the result rests on an assumption the bar data cannot settle."""
    session_close_share: float
    """Fraction of leg exits taken by the clock rather than by the strategy's own rules.

    Over legs, matching :attr:`ambiguous_share`. Expect it to rise sharply with bar size, and
    read both before believing a coarse resolution -- ``docs/roadmap.md`` §M17."""
    commission_paid: float

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    @classmethod
    def empty(cls) -> Summary:
        """The zero summary, for a combination that produced no trades.

        Keyed by field name and typed from the annotations rather than splatted positionally.
        **Do not "simplify" it back to a splat** -- the version this replaces passed 26
        arguments into a 28-field dataclass and raised on every call.
        """
        hints = get_type_hints(cls)
        return cls(**{f.name: 0 if hints[f.name] is int else 0.0 for f in fields(cls)})


def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    return float((np.maximum.accumulate(equity) - equity).max())


def _max_consecutive(mask: np.ndarray) -> int:
    """Longest run of True values."""
    if mask.size == 0 or not mask.any():
        return 0
    edges = np.flatnonzero(np.diff(np.concatenate(([False], mask, [False]))))
    return int((edges[1::2] - edges[::2]).max())


def _ratio(numerator: float, denominator: float) -> float:
    """Guarded division that reports a run with no losses as infinite rather than crashing."""
    if denominator == 0:
        return float("inf") if numerator > 0 else 0.0
    return numerator / denominator


def _risk_adjusted(daily: np.ndarray) -> tuple[float, float]:
    """Annualised Sharpe and Sortino from daily P&L.

    Daily totals rather than per trade: a per-trade Sharpe rewards taking many tiny trades.
    """
    if daily.size < 2:  # noqa: PLR2004
        return 0.0, 0.0
    mean = daily.mean()
    sd = daily.std(ddof=1)
    downside = daily[daily < 0]
    dsd = downside.std(ddof=1) if downside.size > 1 else 0.0
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
    """Reduce a leg-level trade log to one row of performance statistics.

    The reference implementation. :func:`summarise_legs` is the fast path and must agree
    with this exactly; where they ever disagree, this one is right.
    """
    if trades.empty:
        return Summary.empty()

    t = per_trade(trades)
    pnl = t["net_pnl"].to_numpy(np.float64)

    if "exit_time" in t.columns:
        daily = _daily_totals(pnl, pd.DatetimeIndex(t["exit_time"]))
    else:  # pragma: no cover - only when times were not attached
        daily = pnl

    return _summarise_arrays(
        pnl=pnl,
        bars_held=t["bars_held"].to_numpy(np.float64),
        mae=t["mae_points"].to_numpy(np.float64),
        mfe=t["mfe_points"].to_numpy(np.float64),
        daily=daily,
        r=_finite(trades["r_multiple"].to_numpy(np.float64)),
        legs=len(trades),
        commission_paid=float(trades["commission"].sum()),
        ambiguous_share=float(trades["ambiguous_bar"].mean()),
        # Indexed, not ``.get``-ed: a log without ``exit_reason`` is a wiring bug, and
        # reporting 0.0 would read as "this strategy never runs into the close" (#81).
        session_close_share=float((trades["exit_reason"] == SESSION_CLOSE).mean()),
    )


def _daily_totals(pnl: np.ndarray, exit_times: pd.DatetimeIndex) -> np.ndarray:
    """Per-trade P&L totalled by the calendar day each trade closed on."""
    return pd.Series(pnl).groupby(exit_times.date).sum().to_numpy(np.float64)


def _finite(values: np.ndarray) -> np.ndarray:
    """Drop the infinities and nulls an ``r_multiple`` of zero planned risk leaves behind."""
    return values[np.isfinite(values)]


def _summarise_arrays(  # noqa: PLR0913 - one argument per input vector; a bag would hide a swap
    *,
    pnl: np.ndarray,
    bars_held: np.ndarray,
    mae: np.ndarray,
    mfe: np.ndarray,
    daily: np.ndarray,
    r: np.ndarray,
    legs: int,
    commission_paid: float,
    ambiguous_share: float,
    session_close_share: float,
) -> Summary:
    """Every statistic, from per-trade vectors and the leg-level quantities.

    The single definition both summary paths reach -- **do not re-inline it into either
    caller**. ``pnl``, ``bars_held``, ``mae`` and ``mfe`` are one element per **trade**;
    ``daily`` is one per calendar day; ``r`` is one per **leg**, non-finite values dropped.
    """
    wins, losses = pnl > 0, pnl < 0
    gross_profit = float(pnl[wins].sum())
    gross_loss = float(pnl[losses].sum())
    sharpe, sortino = _risk_adjusted(daily)

    return Summary(
        trades=pnl.size,
        legs=legs,
        wins=int(wins.sum()),
        losses=int(losses.sum()),
        scratches=int((pnl == 0).sum()),
        win_rate=float(wins.mean()),
        net_pnl=float(pnl.sum()),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=_ratio(gross_profit, -gross_loss),
        expectancy=float(pnl.mean()),
        avg_win=float(pnl[wins].mean()) if wins.any() else 0.0,
        avg_loss=float(pnl[losses].mean()) if losses.any() else 0.0,
        largest_win=float(pnl.max()),
        largest_loss=float(pnl.min()),
        max_drawdown=_max_drawdown(pnl.cumsum()),
        max_consecutive_losses=_max_consecutive(losses),
        avg_bars_held=float(bars_held.mean()),
        avg_mae_points=float(mae.mean()),
        avg_mfe_points=float(mfe.mean()),
        mean_r=float(r.mean()) if r.size else 0.0,
        r_p10=float(np.quantile(r, 0.10)) if r.size else 0.0,
        r_median=float(np.median(r)) if r.size else 0.0,
        r_p90=float(np.quantile(r, 0.90)) if r.size else 0.0,
        sharpe=sharpe,
        sortino=sortino,
        ambiguous_share=ambiguous_share,
        session_close_share=session_close_share,
        commission_paid=commission_paid,
    )


class GroupingError(ValueError):
    """Raised when a leg matrix is not ordered the way the numpy summary path requires."""


@njit(cache=True)
def _run_starts(keys: np.ndarray) -> np.ndarray:
    """Half-open boundaries of each run of equal ``keys``, plus a closing sentinel."""
    n = keys.size
    starts = np.empty(n + 1, np.int64)
    groups = 0
    for i in range(n):
        if i == 0 or keys[i] != keys[i - 1]:
            starts[groups] = i
            groups += 1
    starts[groups] = n
    return starts[: groups + 1]


@njit(cache=True)
def _grouped_sum(values: np.ndarray, starts: np.ndarray) -> np.ndarray:
    """Kahan-compensated sum per group -- which is what pandas' ``groupby`` does.

    The compensation is load-bearing, not decoration -- ``docs/roadmap.md`` §"The numpy-native
    summary path". Nulls are skipped for the same reason: ``groupby.sum`` defaults to
    ``skipna=True``.
    """
    out = np.empty(starts.size - 1, np.float64)
    for g in range(starts.size - 1):
        total = 0.0
        compensation = 0.0
        for i in range(starts[g], starts[g + 1]):
            value = values[i]
            if value == value:  # noqa: PLR0124 - NaN is the only value unequal to itself
                y = value - compensation
                t = total + y
                compensation = (t - total) - y
                total = t
        out[g] = total
    return out


@njit(cache=True)
def _grouped_max(values: np.ndarray, starts: np.ndarray) -> np.ndarray:
    """Largest value per group, skipping nulls as ``groupby.max`` does."""
    out = np.empty(starts.size - 1, np.float64)
    for g in range(starts.size - 1):
        best = np.nan
        for i in range(starts[g], starts[g + 1]):
            value = values[i]
            if value == value and (best != best or value > best):  # noqa: PLR0124
                best = value
        out[g] = best
    return out


def _ordered_starts(keys: np.ndarray, what: str) -> np.ndarray:
    """Group boundaries, refusing keys that are not already in ascending order.

    Holds by construction for the simulation's output; the check guards a future producer --
    ``docs/roadmap.md`` §"The numpy-native summary path".
    """
    if keys.size > 1 and not bool(np.all(keys[1:] >= keys[:-1])):
        msg = (
            f"{what} must be non-decreasing for the numpy summary path; summarise() the "
            "frame instead, or fix the producer to emit legs in trade order."
        )
        raise GroupingError(msg)
    return _run_starts(keys)


def summarise_legs(legs: LegMatrix, day_codes: np.ndarray | None = None) -> Summary:
    """Summarise the raw leg matrix, giving exactly what :func:`summarise` gives.

    Feed it :attr:`nqbt.context.Dataset.day_codes` so the Sharpe and Sortino denominators are
    days rather than trades. :func:`summarise` remains the reference, and
    ``tests/test_numpy_summary.py`` is what says the two agree.
    """
    matrix, count = legs
    if count == 0:
        return Summary.empty()

    rows = matrix[:count]
    starts = _ordered_starts(rows[:, C_TRADE_ID], "trade_id")
    pnl = _grouped_sum(rows[:, C_NET_PNL], starts)

    if day_codes is None:
        daily = pnl
    else:
        exit_bar = _grouped_max(rows[:, C_EXIT_BAR], starts).astype(np.int64)
        daily = _grouped_sum(pnl, _ordered_starts(day_codes[exit_bar], "exit day"))

    ambiguous = rows[:, C_AMBIGUOUS]
    return _summarise_arrays(
        pnl=pnl,
        bars_held=_grouped_max(rows[:, C_BARS_HELD], starts),
        mae=_grouped_max(rows[:, C_MAE], starts),
        mfe=_grouped_max(rows[:, C_MFE], starts),
        daily=daily,
        r=_finite(rows[:, C_R_MULTIPLE]),
        legs=count,
        commission_paid=float(rows[:, C_COMMISSION].sum()),
        # ``!= 0`` rather than a cast, matching ``trades_to_frame``'s ``astype(bool)``
        # -- which also sends a null to True.
        ambiguous_share=float((ambiguous != 0).mean()),
        session_close_share=float((rows[:, C_EXIT_REASON] == EXIT_SESSION_CLOSE).mean()),
    )


TRADE_PNL_STATISTICS = ("profit_factor", "net_pnl", "expectancy", "win_rate")
"""Statistics that depend on nothing but the per-trade P&L vector.

Which makes them the only ones a resampling test may permute -- ``docs/roadmap.md`` §M14.
"""


def trade_statistic(pnl: np.ndarray, name: str) -> float:
    """One :data:`TRADE_PNL_STATISTICS` value straight from a per-trade P&L vector.

    Roughly two orders of magnitude cheaper than :func:`summarise`, which is what lets a
    resampling test evaluate thousands of regroupings. **Not a second definition**: the
    division goes through the same ``_ratio``, and ``tests/test_dispersion.py`` asserts exact
    agreement on real logs. Feed it :func:`per_trade` output, never raw legs.
    """
    if name not in TRADE_PNL_STATISTICS:
        msg = (
            f"{name!r} cannot be computed from per-trade P&L alone; choose from {list(TRADE_PNL_STATISTICS)}"
        )
        raise ValueError(msg)
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


PATH_STATISTICS = ("max_drawdown", "max_consecutive_losses")
"""Statistics that depend on the order trades arrived in, not only on their values.

Which makes them the only ones a *sequence* permutation can move, and the exact complement of
:data:`TRADE_PNL_STATISTICS` -- ``docs/roadmap.md`` §M7b.
"""


def path_statistic(pnl: np.ndarray, name: str) -> float:
    """One :data:`PATH_STATISTICS` value from a per-trade P&L vector, in sequence order.

    **Not a second definition**: both branches call the same helpers :func:`summarise` does,
    and ``tests/test_montecarlo.py`` asserts exact agreement on real logs. Feed it
    :func:`per_trade` output, never raw legs.
    """
    if name not in PATH_STATISTICS:
        msg = f"{name!r} does not depend on trade order; choose from {list(PATH_STATISTICS)}"
        raise ValueError(msg)
    if pnl.size == 0:
        return 0.0
    if name == "max_drawdown":
        return _max_drawdown(pnl.cumsum())
    return float(_max_consecutive(pnl < 0))


def leg_summary(trades: pd.DataFrame) -> dict:
    """NT8's view: every named entry counted as its own trade.

    Only for reconciling against Strategy Analyzer, whose "Total # of trades" is the leg count.
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
