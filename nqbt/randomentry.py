"""The random-entry control arm: the scale a profit factor is otherwise missing.

A backtest reports numbers, not evidence. "Profit factor 0.746" is only interpretable
against what the *same bracket, the same costs and the same exits* would have produced with
entries chosen at random -- and until that arm exists, three very different diagnoses look
identical:

- **worse than random** -- the entry rule carries real information and is pointing the wrong
  way; investigate the inverse
- **indistinguishable from random** -- the entry rule contributes nothing, and further
  parameter tuning is a search over noise
- **better than random but still unprofitable** -- there is signal; the loss is coming from
  costs, hold time or bracket geometry rather than from entry selection

Permuting an existing trade sequence cannot separate any of these, because it takes the
entries as given. This module is the only thing here that varies them.

## The methodology, and why it is this one

The design principle is the standard one for a randomization test: **hold every nuisance
variable fixed and randomize only the quantity under test.** The quantity under test is
*when the strategy chooses to enter*.

Held fixed, and all of it by construction rather than by review, because the null calls the
archetype's own ``run`` with a substituted signal rather than its own copy of the
simulation:

| held fixed | how |
|---|---|
| bars, instrument, costs, slippage | same ``Dataset`` and same params object |
| bracket geometry, targets, ratchet, stop rules | same ``simulate_deadcat`` call |
| force-flat and session handling | same, and it is a hard account rule either way |
| direction | the archetype's own constant, so it cannot drift |
| number of entry signals | matched exactly -- see :func:`matched_random_signal` |
| distribution over time of session | matched exactly, which is the substantive one |

Randomized: **which trading day each signal falls on**.

### Why time of session is held fixed, and not merely mentioned

This is the part that decides whether the answer means anything. Intraday index futures have
a pronounced and well-known seasonality -- volume and realised volatility are high around the
cash open and the close, and thin overnight. A bracket built from *fixed tick offsets* has
materially different hit probabilities in a volatile hour than in a quiet one: the same stop
is far more likely to be reached at 14:30 UTC than at 03:00.

So a null that scatters entries uniformly across 23 hours would trade mostly in thin bars and
would lose for a reason that has nothing to do with entry quality. **It would flatter every
strategy tested against it.** Matching the time-of-session distribution removes that
confound, and it is the difference between a control arm and a strawman.

Matching is **exact, not coarsened**. Minute-of-session is discrete and low cardinality
(at most 1,380 values) against millions of bars, so there is no need to bucket it into
session phases -- and bucketing would leave real confounding inside each bucket, since the
cash open and a mid-morning lull would share one. That also keeps this module independent of
M10.4's time-of-day labels (#43), which exist to *stratify results* rather than to condition
a null.

### Why the trading day is randomized rather than matched

Choosing which days to be active on is part of what an entry rule does, so it is under test.
Matching on day as well would hold the strategy's regime selection fixed and reduce the
question to intraday timing alone -- a narrower claim than the one anyone wants to make.

### Why many draws, not one

A single random-entry backtest is the folk version of this idea and is not evidence: one
draw of a random variable says nothing about where the observed value sits in its
distribution. The accepted form is a Monte Carlo randomization test -- draw many null
realisations, build the distribution of the statistic, and report where the strategy falls
in it. That is what :func:`compare` returns, in the same shape
:func:`nqbt.dispersion.spread_vs_resampling` already uses.

**Unlike that test, this one may report time-dependent statistics.** Permuting trade labels
destroys the ordering Sharpe and max drawdown depend on, which is why the dispersion test
refuses them; here every null realisation is a *real simulation over real bars*, so its
equity curve is genuine and every statistic in :class:`nqbt.stats.Summary` is fair game.

## What this still does not do

- **It does not correct for multiple comparisons.** Running it across a whole sweep and
  keeping the combinations that beat the null is the same trap #48 exists to guard, with an
  extra step. Test a combination chosen for a reason, not the best of two hundred.
- **A small p-value is not a tradeable edge.** It says the entry timing is unlikely to be
  noise; profitability after costs is a separate question this module reports but does not
  answer.
- **It assumes the signal count is worth matching.** A rule that fires four times is not
  rescued by a null that also fires four times; the trade floor still applies.
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
    from nqbt.context import Dataset

DEFAULT_ITERATIONS = 200
"""Null realisations drawn by default.

Each one is a **full simulation over every bar**, not a cheap regrouping of an existing
trade list, so this is two orders of magnitude more expensive per iteration than
:func:`nqbt.dispersion.spread_vs_resampling` and cannot default to its 1,000. 200 gives a
p-value resolution of 0.005, which is finer than the decision being made with it. Raise it
when a result lands near the threshold -- and note the numpy-native summary path (#33) is
what makes a larger default affordable.
"""

DEFAULT_ALPHA = 0.05
"""Two-sided significance threshold behind :attr:`NullResult.verdict`.

A reporting convention, not a law of nature. It is exposed as an argument precisely so that
nobody has to remember which value produced a stored verdict.
"""

WORSE = "worse than random"
INDISTINGUISHABLE = "indistinguishable from random"
BETTER = "better than random"
"""The three diagnoses this module exists to separate. See the module docstring."""

RATE_STATISTICS = ("profit_factor", "expectancy", "win_rate")
"""The default comparison: statistics that are per-trade rates, so trade count divides out.

**Matching is on entry *signals*, not on filled trades**, and the two are not the same
number. A stop entry only fills if the next bar trades through its trigger, and how often
that happens depends on the bar the signal fired on. Measured on costed MNQ from 2024:
DeadCatBounce's own signals fill 74.4% of the time and its matched null's fill 47.7%, which
is a structural consequence of the trigger being ``min(Low[0], Close[0] - 2 ticks)`` --
on an inverted hammer the close sits near the low, so the trigger sits just under the bar and
is easily reached, while on an average bar it sits well below.

Matching filled trades instead would mean redrawing until the counts agreed, which selects
among null draws on an outcome and is a worse cure than the disease.
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
"""Statistics that are sums or path properties, so a difference in trade count moves them.

Permitted, but never silently: :attr:`NullResult.count_sensitive` flags them and both trade
counts are reported beside every comparison. They are excluded from the default statistics
because a net-P&L comparison between arms with a 36% difference in trade count reads as a
result and is mostly an accounting of how many trades each arm took.
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
    """Share of null draws below the observed value, as a percentage.

    The most directly readable number here: 50 means the strategy landed exactly where a
    coin would, 99 means only 1% of random arms did better.
    """
    p_value: float
    """Two-sided, so it answers "different from random" in either direction.

    Both tails matter and this is the whole reason: an entry rule that reads *worse* than
    random is a finding -- real information pointing the wrong way -- and a one-sided test
    would report it as an unremarkable failure to beat the null.
    """
    verdict: str
    iterations: int
    observed_trades: int
    null_median_trades: float
    """Reported on every row, not only the count-sensitive ones.

    The two arms match on entry *signals* and diverge on fills -- see
    :data:`RATE_STATISTICS`. Even for a rate statistic the counts say how much sample each
    side of the comparison rests on, which is the first thing to check when a p-value is
    surprising.
    """
    count_sensitive: bool
    """True when the statistic is a sum or a path property -- see :data:`COUNT_SENSITIVE`.

    Read such a row against the two trade counts or not at all.
    """

    def as_dict(self) -> dict:
        return asdict(self)


def minute_of_session(
    index: pd.DatetimeIndex,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> np.ndarray:
    """How far each bar sits past its session open, in minutes.

    Delegates to :func:`nqbt.resample.minutes_since_open` rather than recomputing it. That
    function already carries the end-of-bar convention and the reasoning about why no DST
    transition can fall inside a session, and a second implementation of the session clock
    is exactly the duplication this codebase keeps paying for.
    """
    return resample.minutes_since_open(index, template)


@dataclass(frozen=True, slots=True)
class SessionMinutePool:
    """Every bar grouped by its minute-of-session, built once and reused by every draw.

    **This exists because of a measurement, not a preference.** Grouping means an argsort
    over the whole series, and rebuilding it per draw made the draw **89% of an iteration**
    on 914,700 bars -- 106 ms against the 13 ms simulation it exists to feed. It depends only
    on the index, so it is hoisted out of the Monte Carlo loop exactly like
    :func:`nqbt.context.prepare` is hoisted out of a sweep.
    """

    minutes: np.ndarray
    """Minute-of-session per bar, aligned to the index."""
    bars_by_minute: np.ndarray
    """Bar indices, sorted by minute-of-session, so one minute's pool is a contiguous slice."""
    starts: np.ndarray
    """Where each minute's slice begins in :attr:`bars_by_minute`; ``starts[m + 1]`` ends it."""

    @classmethod
    def build(
        cls,
        index: pd.DatetimeIndex,
        template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
    ) -> SessionMinutePool:
        minutes = minute_of_session(index, template)
        order = np.argsort(minutes, kind="stable")
        starts = np.searchsorted(minutes[order], np.arange(minutes.max() + 2), side="left")
        return cls(minutes=minutes, bars_by_minute=order, starts=starts)

    def pool_for(self, minute: int) -> np.ndarray:
        """Every bar sharing one minute-of-session."""
        return self.bars_by_minute[self.starts[minute] : self.starts[minute + 1]]


def matched_random_signal(
    data: Dataset,
    signal: np.ndarray,
    rng: np.random.Generator,
    *,
    pool: SessionMinutePool | None = None,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> np.ndarray:
    """A random entry signal with ``signal``'s count and time-of-session distribution.

    For every minute-of-session at which the real rule fired, the same number of entries is
    drawn -- from the pool of *all* bars sharing that minute, across every trading day. The
    time-of-session marginal is therefore reproduced **exactly**, not approximately, while
    which day each entry lands on is uniformly random.

    Draws within a minute are **without replacement**, so no two null entries collide on one
    bar and the signal count is exact rather than merely expected. That is always possible
    rather than merely usually: the pool is **every bar sharing that minute**, and the real
    signals at that minute are themselves a subset of it, so the pool can never be smaller
    than the number of draws. The guarantee is structural, which is why there is no
    resample-on-collision loop here to get subtly wrong.

    The pool is deliberately *not* narrowed to in-session bars, and that is the symmetric
    choice rather than a lax one: the null must face the same bar universe the strategy
    faced. A per-contract frame keeps a handful of out-of-session stray prints -- an isolated
    Saturday bar with volume 1 -- and the strategy's own signal is computed over them too
    (see ``CLAUDE.md``, "out-of-session stray prints"). Narrowing the pool while leaving the
    strategy's own entries unnarrowed would compare two different bar universes, and it would
    also break the subset guarantee above. On the spliced continuous series the question does
    not arise at all, because ``build_continuous`` has already filtered them out.
    """
    if signal.shape != (len(data),):
        msg = f"signal has {signal.shape} entries for {len(data)} bars; it must be per-bar"
        raise RandomEntryError(msg)
    live = int(signal.sum())
    if not live:
        msg = (
            "the strategy produced no entry signals, so there is nothing to match a null "
            "against. Check the filters or the warm-up before reading this as a result."
        )
        raise RandomEntryError(
            msg,
        )

    grouped = pool if pool is not None else SessionMinutePool.build(data.index, template)

    out = np.zeros(len(data), dtype=bool)
    wanted_minutes, wanted_counts = np.unique(grouped.minutes[signal], return_counts=True)
    for minute, count in zip(wanted_minutes, wanted_counts, strict=True):
        out[rng.choice(grouped.pool_for(minute), size=count, replace=False)] = True
    return out


def _null_summary(
    data: Dataset,
    params: Params,
    archetype: Archetype,
    instrument: Instrument,
    signal: np.ndarray,
    seed: int,
    pool: SessionMinutePool,
) -> dict:
    """One null realisation: draw a matched signal, simulate it, summarise it.

    Module level and seeded per draw so the parallel path is reproducible and returns the
    same values in the same order as the serial one, whatever order the workers finish in.
    """
    rng = np.random.default_rng(seed)
    drawn = matched_random_signal(data, signal, rng, pool=pool)
    log = archetype.run(data, params, instrument, signal=drawn)
    return stats.summarise(log).as_dict()


def null_summaries(
    data: Dataset,
    params: Params,
    archetype: Archetype | None = None,
    instrument: Instrument = MNQ,
    *,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
    n_jobs: int = 1,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> pd.DataFrame:
    """One row of :class:`nqbt.stats.Summary` per null realisation.

    Returned rather than reduced straight to a p-value, because the distribution is the
    interesting object: it says how wide the null is, which decides whether a difference in
    profit factor is worth anything at all.

    Every draw is seeded from ``seed`` deterministically, so ``n_jobs`` changes the wall
    clock and nothing else.

    The minute-of-session grouping and the strategy's own signal are both computed **once**
    and shared by every iteration -- see :class:`SessionMinutePool` for the measurement that
    made that mandatory rather than tidy.
    """
    if iterations < 1:
        msg = "iterations must be at least 1"
        raise RandomEntryError(msg)
    archetype = archetype if archetype is not None else archetypes.for_params(params)
    signal = archetype.signal(data, params)
    pool = SessionMinutePool.build(data.index, template)
    seeds = np.random.SeedSequence(seed).generate_state(iterations)

    if effective_n_jobs(n_jobs) == 1:
        rows = [_null_summary(data, params, archetype, instrument, signal, int(s), pool) for s in seeds]
    else:
        # ``slim()`` for the same reason the sweep does it: the bar frame is the expensive
        # part of the payload and only its index is read downstream.
        lean = data.slim()
        rows = Parallel(n_jobs=n_jobs)(
            delayed(_null_summary)(lean, params, archetype, instrument, signal, int(s), pool) for s in seeds
        )
    return pd.DataFrame(rows)


def compare(
    data: Dataset,
    params: Params,
    archetype: Archetype | None = None,
    instrument: Instrument = MNQ,
    *,
    statistics: tuple[str, ...] = RATE_STATISTICS,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
    n_jobs: int = 1,
    template: SessionTemplate = CME_US_INDEX_FUTURES_ETH,
) -> dict[str, NullResult]:
    """Run the strategy and its matched null, and say where the strategy landed.

    Several statistics by default because one simulation produces all of them, so the extra
    ones are free -- and because profit factor alone hides the case where a rule wins more
    often but loses more per loss.

    Any field of :class:`nqbt.stats.Summary` is permitted, **including the time-dependent
    ones**. Every null realisation here is a genuine simulation over real bars rather than a
    relabelling of an existing trade list, so Sharpe and max drawdown are computed over an
    ordering that actually happened -- which is not true of
    :func:`nqbt.dispersion.spread_vs_resampling` and is the substantive difference between
    the two tests.

    The default is :data:`RATE_STATISTICS` rather than everything, because the arms match on
    signals and diverge on fills. Ask for a :data:`COUNT_SENSITIVE` statistic and it is
    returned with ``count_sensitive=True`` and both trade counts beside it.

    A non-finite observed statistic raises rather than returning a comparison, because
    "infinite profit factor beats the null" is an artefact of a run with no losing trade
    rather than a result.
    """
    archetype = archetype if archetype is not None else archetypes.for_params(params)
    unknown = set(statistics) - set(stats.Summary.columns())
    if unknown:
        msg = f"not statistics of a Summary: {sorted(unknown)}. Choose from {stats.Summary.columns()}"
        raise RandomEntryError(
            msg,
        )

    observed = stats.summarise(archetype.run(data, params, instrument)).as_dict()
    null = null_summaries(
        data,
        params,
        archetype,
        instrument,
        iterations=iterations,
        seed=seed,
        n_jobs=n_jobs,
        template=template,
    )

    results = {}
    for name in statistics:
        value = float(observed[name])
        draws = null[name].to_numpy(dtype=float)
        draws = draws[np.isfinite(draws)]
        if not np.isfinite(value):
            msg = (
                f"observed {name} is {value}, which no null can be compared against -- a "
                "run with no losing trade reports an infinite profit factor"
            )
            raise RandomEntryError(
                msg,
            )
        if draws.size < 2:
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
    draws: np.ndarray,
    alpha: float,
    iterations: int,
    *,
    observed_trades: int,
    null_median_trades: float,
) -> NullResult:
    """Locate ``observed`` in the null draws and name the diagnosis.

    The p-value counts draws **at least as extreme in either direction**, and adds one to
    both numerator and denominator. That correction is not decoration: without it a
    statistic no draw happened to beat reports p = 0, which claims more certainty than
    ``iterations`` draws can support. With it the floor is 1/(n+1), which is the honest
    resolution of a Monte Carlo test.
    """
    below = float((draws < observed).mean())
    at_least_as_extreme = int(min((draws >= observed).sum(), (draws <= observed).sum()))
    p_value = min(1.0, 2.0 * (at_least_as_extreme + 1) / (draws.size + 1))

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
