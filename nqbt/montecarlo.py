"""Resampling a trade sequence, to ask whether its equity path was luckier than its trades.

Two tests over one per-trade P&L vector. :func:`permutation_test` reorders the trades, which
moves only :data:`nqbt.stats.PATH_STATISTICS` and answers "was this drawdown the ordering's
doing?". :func:`bootstrap` resamples with replacement, which moves the values too and answers
"how wide is the uncertainty around this figure?".

**Neither can say the entries are any good.** Both take the trades as given, so they cannot
distinguish "worse than random" from "no better than random" -- that is
:mod:`nqbt.randomentry`'s job, and a result quoted from here without it is half an argument.
Limits and framing: ``docs/roadmap.md`` §M7b.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import stats

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray

__all__ = [
    "MonteCarloError",
    "PermutationResult",
    "bootstrap",
    "permutation_test",
    "trade_pnl",
]

DEFAULT_ITERATIONS = 1000
MIN_RESAMPLE_TRADES = 2
"""Fewer than two trades has no ordering to permute and nothing to resample."""

MIN_TRADES = 30
"""Below this a resampling result is reported but should not be read as a measurement.

The same floor :mod:`nqbt.dispersion` applies, for the same reason.
"""


class MonteCarloError(ValueError):
    """Raised when a resampling test would be degenerate or uninterpretable."""


@dataclass(frozen=True, slots=True)
class PermutationResult:
    """One statistic's observed value against the distribution over reorderings."""

    statistic: str
    observed: float
    null_median: float
    null_p05: float
    null_p95: float
    p_value: float
    """Share of orderings at least as bad as the observed one."""

    iterations: int
    trades: int
    underpowered: bool
    """True below :data:`MIN_TRADES`, where the test is reported but not a measurement."""

    def as_dict(self) -> dict[str, str | float | int | bool]:
        """Flat mapping, for a report row or a CSV."""
        return dataclasses.asdict(self)


def trade_pnl(trades: pd.DataFrame) -> FloatArray:
    """Collapse legs into the per-trade P&L vector a resampling test operates on."""
    if trades.empty:
        return np.empty(0, dtype=float)
    per_trade: pd.DataFrame = stats.per_trade(trades)
    if "entry_time" in per_trade.columns:
        per_trade = per_trade.sort_values("entry_time", kind="stable")
    return per_trade["net_pnl"].to_numpy(dtype=float)


def _value(pnl: FloatArray, name: str) -> float:
    """Dispatch to whichever of the two ``stats`` entry points owns ``name``."""
    if name in stats.PATH_STATISTICS:
        return stats.path_statistic(pnl, name)
    return stats.trade_statistic(pnl, name)


def permutation_test(
    pnl: FloatArray,
    statistic: str = "max_drawdown",
    *,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
) -> PermutationResult:
    """Test whether ``statistic`` is extreme against the same trades in a different order.

    Only :data:`nqbt.stats.PATH_STATISTICS` may be permuted. Reordering leaves profit factor,
    net P&L, expectancy and win rate exactly where they were, so a permutation test on those
    is guaranteed to return ``p_value`` 1.0 and would read as a passed check.

    ``p_value`` is the share of orderings whose statistic was at least as *bad* as the
    observed one, so a small value means the real sequence was unluckier than most.
    """
    if statistic not in stats.PATH_STATISTICS:
        msg: str = (
            f"{statistic!r} does not depend on trade order, so permuting the sequence cannot "
            f"move it and the test would always pass; choose from {list(stats.PATH_STATISTICS)}"
        )
        raise MonteCarloError(msg)
    if pnl.size < MIN_RESAMPLE_TRADES:
        msg = f"need at least {MIN_RESAMPLE_TRADES} trades to permute an ordering; got {pnl.size}"
        raise MonteCarloError(msg)

    observed: float = _value(pnl, statistic)
    rng: np.random.Generator = np.random.default_rng(seed)
    draws: FloatArray = np.fromiter(
        (_value(rng.permutation(pnl), statistic) for _ in range(iterations)),
        dtype=float,
        count=iterations,
    )
    return PermutationResult(
        statistic=statistic,
        observed=observed,
        null_median=float(np.median(draws)),
        null_p05=float(np.percentile(draws, 5)),
        null_p95=float(np.percentile(draws, 95)),
        p_value=float((draws >= observed).mean()),
        iterations=iterations,
        trades=int(pnl.size),
        underpowered=bool(pnl.size < MIN_TRADES),
    )


def bootstrap(
    pnl: FloatArray,
    statistics: tuple[str, ...] = ("net_pnl", "profit_factor", "max_drawdown"),
    *,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
) -> pd.DataFrame:
    """Resample the trades with replacement and report the spread of each statistic.

    Answers how wide the uncertainty around a figure is, given this many trades of this
    dispersion. It **assumes the trades are exchangeable** -- independent and identically
    distributed -- which a strategy with serial correlation violates, so read a narrow
    interval as a lower bound on the true uncertainty rather than as the whole of it.
    """
    if pnl.size < MIN_RESAMPLE_TRADES:
        msg: str = f"need at least {MIN_RESAMPLE_TRADES} trades to resample; got {pnl.size}"
        raise MonteCarloError(msg)

    known: tuple[str, str, str, str, str, str] = (*stats.TRADE_PNL_STATISTICS, *stats.PATH_STATISTICS)
    unknown: list[str] = [s for s in statistics if s not in known]
    if unknown:
        msg = f"unknown statistic(s) {unknown}; choose from {list(known)}"
        raise MonteCarloError(msg)
    if not statistics:
        msg = "no statistics requested"
        raise MonteCarloError(msg)

    rng: np.random.Generator = np.random.default_rng(seed)
    draws: FloatArray = np.empty((iterations, len(statistics)), dtype=float)
    for i in range(iterations):
        sample: FloatArray = rng.choice(pnl, size=pnl.size, replace=True)
        for column, name in enumerate(statistics):
            draws[i, column] = _value(sample, name)

    rows: list[dict[str, object]] = []
    for column, name in enumerate(statistics):
        values: FloatArray = draws[:, column]
        finite: FloatArray = values[np.isfinite(values)]
        rows.append(
            {
                "statistic": name,
                "observed": _value(pnl, name),
                "median": float(np.median(finite)) if finite.size else np.nan,
                "p05": float(np.percentile(finite, 5)) if finite.size else np.nan,
                "p95": float(np.percentile(finite, 95)) if finite.size else np.nan,
                "share_below_zero": float((finite < 0).mean()) if finite.size else np.nan,
                "draws_finite": int(finite.size),
            },
        )
    frame: pd.DataFrame = pd.DataFrame(rows)
    frame.attrs["iterations"] = iterations
    frame.attrs["trades"] = int(pnl.size)
    frame.attrs["underpowered"] = bool(pnl.size < MIN_TRADES)
    return frame
