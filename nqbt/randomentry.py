"""The random-entry control arm: a matched null for "is this entry rule better than chance?".

Holds the bars, costs, bracket geometry, direction, signal count and time-of-session
distribution fixed, and randomizes only which trading day each signal lands on. Methodology,
evidence and caveats: ``docs/roadmap.md`` §M7a.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from joblib import Parallel, delayed, effective_n_jobs

from nqbt import archetypes, resample, stats
from nqbt.instruments import MNQ, Instrument
from nqbt.sessions import CME_US_INDEX_FUTURES_ETH, SessionTemplate

if TYPE_CHECKING:
    from nqbt.archetypes import Archetype, Params
    from nqbt.arrays import BoolArray, FloatArray, IntArray, OffsetArray
    from nqbt.context import Dataset
    from nqbt.trades import LegMatrix

MIN_FINITE_DRAWS = 2
"""Fewest finite null draws that make a distribution to place an observation in."""

DEFAULT_ITERATIONS = 200
"""Null realisations drawn by default. Sized in ``docs/roadmap.md`` §M7a."""

DEFAULT_ALPHA = 0.05
"""Two-sided significance threshold behind :attr:`NullResult.verdict`."""

WORSE = "worse than random"
INDISTINGUISHABLE = "indistinguishable from random"
BETTER = "better than random"

RATE_STATISTICS = ("profit_factor", "expectancy", "win_rate")
"""Per-trade rates, so trade count divides out.

The default comparison, because the arms match on entry *signals* and diverge on fills.
"""

COUNT_SENSITIVE = frozenset(
    {
        "net_pnl",
        "gross_profit",
        "gross_loss",
        "commission_paid",
        "max_drawdown",
        "trades",
        "legs",
        "wins",
        "losses",
        "scratches",
        "max_consecutive_losses",
    },
)
"""Sums and path properties, which a difference in trade count moves.

Permitted, but never silently: :attr:`NullResult.count_sensitive` flags them and both trade
counts sit beside every comparison.
"""


class RandomEntryError(RuntimeError):
    """Raised when a null cannot be drawn or would not mean anything."""


@dataclass(frozen=True, slots=True)
class NullResult:
    """Where one observed statistic falls in the distribution of its null."""

    statistic: str
    observed: float
    null_median: float
    null_p05: float
    null_p95: float
    percentile: float
    """Share of null draws below the observed value, as a percentage."""
    p_value: float
    """Two-sided, so it answers "different from random" in either direction."""
    verdict: str
    iterations: int
    observed_trades: int
    null_median_trades: float
    """Reported on every row, not only the count-sensitive ones."""
    count_sensitive: bool
    """True when the statistic is a sum or a path property -- see :data:`COUNT_SENSITIVE`."""

    def as_dict(self) -> dict[str, object]:
        """Flat mapping, for a report row or a CSV."""
        return asdict(self)


def minute_of_session(
    index: pd.DatetimeIndex,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> IntArray:
    """How far each bar sits past its session open, in minutes."""
    return resample.minutes_since_open(index, template)


@dataclass(frozen=True, slots=True)
class SessionMinutePool:
    """Every bar grouped by its minute-of-session, built once and reused by every draw.

    Hoisting this out of the Monte Carlo loop is a measurement, not tidiness --
    ``docs/roadmap.md`` §M7a.
    """

    minutes: IntArray
    """Minute-of-session per bar, aligned to the index."""
    bars_by_minute: IntArray
    """Bar indices, sorted by minute-of-session, so one minute's pool is a contiguous slice."""
    starts: IntArray
    """Where each minute's slice begins in :attr:`bars_by_minute`; ``starts[m + 1]`` ends it."""

    @classmethod
    def build(
        cls,
        index: pd.DatetimeIndex,
        template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
    ) -> SessionMinutePool:
        """Group every bar of ``index`` by its minute-of-session, once."""
        minutes: IntArray = minute_of_session(index, template)
        order: OffsetArray = np.argsort(minutes, kind="stable")
        starts: OffsetArray = np.searchsorted(minutes[order], np.arange(minutes.max() + 2), side="left")
        return cls(minutes=minutes, bars_by_minute=order, starts=starts)

    def pool_for(self, minute: int) -> IntArray:
        """Every bar sharing one minute-of-session."""
        return self.bars_by_minute[self.starts[minute] : self.starts[minute + 1]]


def matched_random_signal(
    data: Dataset,
    signal: BoolArray,
    rng: np.random.Generator,
   
    pool: SessionMinutePool | None = None,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> BoolArray:
    """A random entry signal with ``signal``'s count and time-of-session distribution.

    For every minute-of-session at which the real rule fired, the same number of entries is
    drawn without replacement from all bars sharing that minute, across every trading day.
    The pool is deliberately not narrowed to in-session bars -- ``docs/roadmap.md`` §M7a.
    """
    if signal.shape != (len(data),):
        msg: str = f"signal has {signal.shape} entries for {len(data)} bars; it must be per-bar"
        raise RandomEntryError(msg)
    live: int = int(signal.sum())
    if not live:
        msg = (
            "the strategy produced no entry signals, so there is nothing to match a null "
            "against. Check the filters or the warm-up before reading this as a result."
        )
        raise RandomEntryError(
            msg,
        )

    grouped: SessionMinutePool = pool if pool is not None else SessionMinutePool.build(data.index, template)

    out: BoolArray = np.zeros(len(data), dtype=bool)
    wanted_minutes, wanted_counts = np.unique(grouped.minutes[signal], return_counts=True)
    for minute, count in zip(wanted_minutes, wanted_counts, strict=True):
        out[rng.choice(grouped.pool_for(minute), size=count, replace=False)] = True
    return out


def _null_summary(
    data: Dataset,
    params: Params,
    archetype: Archetype,
    instrument: Instrument,
    signal: BoolArray,
    seed: int,
    pool: SessionMinutePool,
) -> dict[str, float]:
    """One null realisation: draw a matched signal, simulate it, summarise it.

    Module level and seeded per draw so the parallel path returns the serial path's values in
    the serial path's order, whatever order the workers finish in.
    """
    rng: np.random.Generator = np.random.default_rng(seed)
    drawn: BoolArray = matched_random_signal(data, signal, rng, pool=pool)
    legs: LegMatrix = archetype.legs(data, params, instrument, signal=drawn)
    return stats.summarise_legs(legs, data.day_codes).as_dict()


def null_summaries(
    data: Dataset,
    params: Params,
    archetype: Archetype | None = None,
    instrument: Instrument = MNQ,
   
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
    n_jobs: int = 1,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> pd.DataFrame:
    """One row of :class:`nqbt.stats.Summary` per null realisation.

    Every draw is seeded deterministically from ``seed``, so ``n_jobs`` changes the wall clock
    and nothing else.
    """
    if iterations < 1:
        msg: str = "iterations must be at least 1"
        raise RandomEntryError(msg)
    archetype = archetype if archetype is not None else archetypes.for_params(params)
    signal: BoolArray = archetype.signal(data, params)
    pool: SessionMinutePool = SessionMinutePool.build(data.index, template)
    seeds = np.random.SeedSequence(seed).generate_state(iterations)

    rows: list[dict[str, float]]
    if effective_n_jobs(n_jobs) == 1:
        rows = [_null_summary(data, params, archetype, instrument, signal, int(s), pool) for s in seeds]
    else:
        lean: Dataset = data.slim()
        rows = Parallel(n_jobs=n_jobs)(
            delayed(_null_summary)(lean, params, archetype, instrument, signal, int(s), pool) for s in seeds
        )
    return pd.DataFrame(rows)


def compare(
    data: Dataset,
    params: Params,
    archetype: Archetype | None = None,
    instrument: Instrument = MNQ,
   
    statistics: tuple[str, ...] = RATE_STATISTICS,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
    n_jobs: int = 1,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> dict[str, NullResult]:
    """Run the strategy and its matched null, and say where the strategy landed.

    Any field of :class:`nqbt.stats.Summary` is permitted, including the time-dependent ones,
    because every draw is a genuine simulation rather than a relabelling. A
    :data:`COUNT_SENSITIVE` statistic comes back flagged; a non-finite observed statistic
    raises.
    """
    archetype = archetype if archetype is not None else archetypes.for_params(params)
    unknown: set[str] = set(statistics) - set(stats.Summary.columns())
    if unknown:
        msg: str = f"not statistics of a Summary: {sorted(unknown)}. Choose from {stats.Summary.columns()}"
        raise RandomEntryError(
            msg,
        )

    observed: dict[str, float] = stats.summarise_legs(
        archetype.legs(data, params, instrument), data.day_codes
    ).as_dict()
    null: pd.DataFrame = null_summaries(
        data,
        params,
        archetype,
        instrument,
        iterations=iterations,
        seed=seed,
        n_jobs=n_jobs,
        template=template,
    )

    results: dict[str, NullResult] = {}
    for name in statistics:
        value: float = float(observed[name])
        draws: FloatArray = null[name].to_numpy(dtype=float)
        draws = draws[np.isfinite(draws)]
        if not np.isfinite(value):
            msg = (
                f"observed {name} is {value}, which no null can be compared against -- a "
                "run with no losing trade reports an infinite profit factor"
            )
            raise RandomEntryError(
                msg,
            )
        if draws.size < MIN_FINITE_DRAWS:
            msg = (
                f"only {draws.size} of {iterations} null draws produced a finite {name}; "
                "there is no distribution to place the observation in"
            )
            raise RandomEntryError(
                msg,
            )
        results[name] = _place(
            name,
            value,
            draws,
            alpha,
            iterations,
            observed_trades=int(observed["trades"]),
            null_median_trades=float(null["trades"].median()),
        )
    return results


def _place(
    name: str,
    observed: float,
    draws: FloatArray,
    alpha: float,
    iterations: int,
   
    observed_trades: int,
    null_median_trades: float,
) -> NullResult:
    """Locate ``observed`` in the null draws and name the diagnosis.

    The p-value counts draws at least as extreme in either direction and carries the add-one
    correction, so its floor is 1/(n + 1) rather than zero.
    """
    below: float = float((draws < observed).mean())
    at_least_as_extreme: int = int(min((draws >= observed).sum(), (draws <= observed).sum()))
    p_value: float = min(1.0, 2.0 * (at_least_as_extreme + 1) / (draws.size + 1))

    verdict: str
    if p_value > alpha:
        verdict = INDISTINGUISHABLE
    else:
        verdict = BETTER if observed > float(np.median(draws)) else WORSE

    return NullResult(
        statistic=name,
        observed=observed,
        null_median=float(np.median(draws)),
        null_p05=float(np.percentile(draws, 5)),
        null_p95=float(np.percentile(draws, 95)),
        percentile=below * 100.0,
        p_value=p_value,
        verdict=verdict,
        iterations=iterations,
        observed_trades=observed_trades,
        null_median_trades=null_median_trades,
        count_sensitive=name in COUNT_SENSITIVE,
    )


def report(results: dict[str, NullResult]) -> pd.DataFrame:
    """One row per statistic, for reading a :func:`compare` at a glance."""
    return pd.DataFrame([r.as_dict() for r in results.values()])
