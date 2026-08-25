"""What a separation has to survive before it is even a candidate.

A few hundred trades against a few dozen conditions is a multiple-comparisons machine: some
condition *will* split that sample impressively, and most of the time it will be noise. Three
mitigations, none of them expensive -- ``docs/roadmap.md`` §M11.4.

**A minimum sample per stratum** is :mod:`nqbt.review`'s floor, imported rather than restated.
**A permutation test** shuffles the P&L against the labels, which holds every stratum's size
fixed and destroys only the association, and reports where the real separation fell in that
distribution. Every condition is shuffled by the *same* permutation, so the maximum across them
is a family-wise null and :data:`FAMILY_COLUMN` is the number to read when the condition was
picked by looking. **A holdout** re-reads the split the earlier trades chose over the most recent
ones, without re-choosing it.

**Nothing here defines a statistic, and nothing here is review-specific.** A stratum's value comes
from :func:`nqbt.stats.trade_statistic` and a separation is :func:`nqbt.review.rank_conditions`'
quantity reached by a faster route, both pinned in ``tests/test_guard.py``. The array-level
functions take a per-trade P&L vector and one label per trade, which is the shape the best of
nineteen contracts (#31) and a ranking over archetypes x combinations (#24) both reduce to.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, override

import numpy as np
import pandas as pd

from nqbt import notes, review, stats
from nqbt.arrays import AnyArray

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from nqbt.annotate import Annotation

__all__ = [
    "DEFAULT_HOLDOUT_SHARE",
    "DEFAULT_ITERATIONS",
    "FAMILY_COLUMN",
    "HOLDOUT_COLUMNS",
    "SCREEN_COLUMNS",
    "STATISTICS",
    "STATUS",
    "Guard",
    "GuardError",
    "Holdout",
    "Labels",
    "Separation",
    "SeparationTest",
    "guard",
    "holdout_test",
    "permutation_test",
    "screen",
    "separate",
]

type Floats = np.ndarray[tuple[int], np.dtype[np.float64]]
"""A per-trade P&L vector, or one statistic per stratum."""

type Counts = np.ndarray[tuple[int], np.dtype[np.int64]]
"""Positions into a P&L vector, or the size of each stratum."""

type Flags = np.ndarray[tuple[int], np.dtype[np.bool_]]
"""One mask per trade, or one per stratum."""

type Draws = np.ndarray[tuple[int, int], np.dtype[np.float64]]
"""A row per shuffle, a column per condition."""

type Column = pd.Series
"""One condition's labels as pandas holds them; a condition's dtype is its own."""

type Labels = Sequence[object] | Column | AnyArray
"""One label per trade, however the caller holds them."""

DEFAULT_ITERATIONS = 2000
"""Label shuffles drawn by default.

A p-value cannot resolve below ``1 / iterations``, and a family-wise one has to separate the best
of a few dozen conditions from the rest -- so it needs to resolve well under one over that count,
which the 1000 used elsewhere in the project does not do comfortably.
"""

DEFAULT_HOLDOUT_SHARE = 0.25
"""Share of the trades held back, most recent first.

A share rather than a count because both halves have to clear :data:`nqbt.review.MIN_TRADES` per
stratum, and the sample size is not known when the default is written.
"""

STATISTICS = tuple(name for name in review.REPORTED if name in stats.TRADE_PNL_STATISTICS)
"""The statistics a separation may be measured in: the reported ones a shuffle can move.

Both halves of that intersection matter. A statistic outside :data:`nqbt.review.REPORTED` is not
one the review printed, so testing it would answer a question nobody asked; one outside
:data:`nqbt.stats.TRADE_PNL_STATISTICS` cannot be had from a P&L vector alone, and thousands of
:func:`nqbt.stats.summarise` calls is not a test anyone runs. It excludes ``net_pnl`` for a third
reason that would apply on its own: a sum separates strata by how many trades they hold.
"""

FAMILY_COLUMN = "family_p_value"
"""The p-value of the best of several conditions, against the maximum over the same shuffles.

``p_value`` answers "would *this* condition have split the trades this well by chance?", which is
the right question only for a condition chosen for a reason. Taking the widest separation on
offer and reading its ``p_value`` is the multiple-comparisons machine again, one level up.
"""

SCREEN_COLUMNS = (*review.RANKING_COLUMNS, "p_value", FAMILY_COLUMN)
"""A screen is :func:`nqbt.review.rank_conditions`' columns with the two nulls beside them."""

HOLDOUT_COLUMNS = (
    "condition",
    "best",
    "worst",
    "in_sample",
    "out_of_sample",
    "in_sample_trades",
    "held_out_trades",
    "direction_held",
    "reported",
)
"""A holdout row: the split the earlier trades chose, and what the recent ones did with it.

A subset of :class:`Holdout`'s fields -- the statistic is stated once on the report rather than
repeated down a column.
"""

STATUS = (
    "STILL HYPOTHESIS-GENERATING -- a separation that survives a shuffled-label null and a "
    "holdout is worth testing over a sweep's thousands of trades, not worth trading. The null "
    "says the split is unlikely if the labels carried nothing; it cannot say the cause is this "
    "condition rather than something that travels with it."
)
"""What a guarded separation is still not, said in the report rather than left to be recalled."""

HOLDOUT_NOTE = (
    "The holdout re-reads the split the earlier trades chose and never re-chooses it, because "
    "picking the best stratum on the recent trades too would hold nothing out. Its strata are "
    "small by construction, so read `reported` before `direction_held`."
)
"""What has to travel with a holdout row, for the same reason as :data:`nqbt.review.STATUS`."""


class GuardError(ValueError):
    """Raised when a guard would be degenerate, or would not be testing what it claims to."""


@dataclass(frozen=True, slots=True)
class Separation:
    """The gap one condition opened in one statistic, and the two strata that opened it."""

    value: float
    """Best stratum minus worst, over the strata that met the floor. NaN below two of them."""

    best: object
    worst: object
    strata: int
    """Distinct values the condition took, before the floor."""

    strata_ranked: int
    """Strata that met the floor and reported a finite statistic."""

    trades_ranked: int
    """Trades those strata held."""


@dataclass(frozen=True, slots=True)
class SeparationTest:
    """Where one condition's separation fell in the distribution over shuffled labels."""

    condition: str
    statistic: str
    observed: float
    null_median: float
    null_p95: float
    p_value: float
    """Share of shuffles that separated the trades at least as far as the real labels did."""

    iterations: int
    draws_finite: int
    """Shuffles that produced a measurable separation. The rest cannot vote."""

    strata_ranked: int
    trades_ranked: int

    def as_dict(self) -> dict[str, object]:
        """Flat mapping, for a report row or a CSV."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Holdout:
    """One condition's in-sample split, re-read over the trades held back from choosing it."""

    condition: str
    statistic: str
    best: object
    worst: object
    in_sample: float
    out_of_sample: float
    """The same two strata's gap over the held-out trades. NaN where either is absent."""

    in_sample_trades: int
    held_out_trades: int
    """Held-out trades falling in those two strata, not held-out trades in total."""

    direction_held: bool
    """Whether the gap kept its sign. Read :attr:`reported` first."""

    reported: bool
    """Whether both held-out strata met the floor. Rarely, on a few hundred trades."""

    def as_dict(self) -> dict[str, object]:
        """Flat mapping, for a report row or a CSV."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Guard:
    """Every condition of one review, against a shuffled-label null and against a holdout."""

    screen: pd.DataFrame
    """A row per condition, most significant family-wise first -- :data:`SCREEN_COLUMNS`."""

    holdout: pd.DataFrame
    """A row per condition, in the screen's order -- :data:`HOLDOUT_COLUMNS`."""

    statistic: str
    conditions: tuple[str, ...]
    iterations: int
    min_trades: int
    trades: int
    """Trades the screen ran over."""

    dropped: int
    """Trades set aside because some screened condition left them null."""

    held_out: int

    @override
    def __str__(self) -> str:
        """Render what was guarded, then the null, then the holdout."""
        return "\n".join(
            [
                (
                    f"{self.trades} trades screened ({self.dropped} set aside for a null label), "
                    f"{len(self.conditions)} conditions, {self.iterations} label shuffles, "
                    f"minimum {self.min_trades} trades per stratum, separation in {self.statistic}"
                ),
                STATUS,
                "",
                "Separation against shuffled labels",
                self.screen.to_string() if not self.screen.empty else "  nothing to screen",
                f"  {FAMILY_COLUMN} is the one to read when the condition was picked by looking.",
                "",
                f"Holdout: the most recent {self.held_out} trades",
                self.holdout.to_string() if not self.holdout.empty else "  nothing to hold out",
                f"  {HOLDOUT_NOTE}",
            ],
        )


# -- the separation, reached the fast way -------------------------------------


@dataclass(frozen=True, slots=True)
class _Grouping:
    """One condition's trades sorted into contiguous strata, so a shuffle is a split.

    Which strata meet the floor depends on their sizes alone, and a permutation moves P&L rather
    than labels, so this is built once and every draw reuses it.
    """

    order: Counts
    """Positions into the P&L vector, grouped by label, excluding the strata below the floor."""

    bounds: Counts
    """Where each stratum ends inside :attr:`order`, for :func:`numpy.split`."""

    values: tuple[object, ...]
    """The label each stratum carries, in :attr:`order`'s order, which is sorted by value."""

    sizes: Counts
    strata: int
    """Distinct values before the floor, which is what a report calls the condition's strata."""


def _positional(labels: Labels) -> Column:
    """One label per trade, indexed by position, whatever the caller held them in."""
    return pd.Series(labels).reset_index(drop=True)


def _group(labels: Column, *, min_trades: int) -> _Grouping:
    """Sort the trades into the strata a separation is measured across, floor applied.

    Null labels are dropped, which is what :func:`nqbt.review.stratify` does with them.
    """
    present = labels.dropna()
    grouped = present.groupby(present, sort=True, observed=True).groups
    kept = [(value, at) for value, at in grouped.items() if len(at) >= min_trades]
    if not kept:
        return _Grouping(
            order=np.empty(0, dtype=np.int64),
            bounds=np.empty(0, dtype=np.int64),
            values=(),
            sizes=np.empty(0, dtype=np.int64),
            strata=len(grouped),
        )

    sizes = np.array([len(at) for _, at in kept], dtype=np.int64)
    return _Grouping(
        order=np.concatenate([np.asarray(at, dtype=np.int64) for _, at in kept]),
        bounds=np.cumsum(sizes)[:-1],
        values=tuple(value for value, _ in kept),
        sizes=sizes,
        strata=len(grouped),
    )


def _stratum_values(pnl: Floats, grouping: _Grouping, statistic: str) -> Floats:
    """Read the statistic of every stratum that met the floor, in :attr:`_Grouping.values`' order."""
    if grouping.order.size == 0:
        return np.empty(0, dtype=np.float64)
    parts = np.split(pnl[grouping.order], grouping.bounds)
    return np.fromiter(
        (stats.trade_statistic(part, statistic) for part in parts),
        dtype=np.float64,
        count=len(parts),
    )


def _spread(values: Floats) -> float:
    """Measure the gap between the best and worst finite stratum, NaN where there is no comparison."""
    finite = values[np.isfinite(values)]
    if finite.size < review.MIN_STRATA:
        return np.nan
    return float(finite.max() - finite.min())


def separate(
    pnl: Floats,
    labels: Labels,
    *,
    statistic: str = "expectancy",
    min_trades: int = review.MIN_TRADES,
) -> Separation:
    """How far ``statistic`` separates the strata one condition cuts ``pnl`` into.

    The quantity :func:`nqbt.review.rank_conditions` ranks on, computed from a per-trade P&L
    vector rather than from a :func:`nqbt.stats.summarise` per stratum, because a null needs
    thousands of them. **Not a second definition**: ``tests/test_guard.py`` asserts the two agree
    on real logs, as ``tests/test_dispersion.py`` does for the statistic underneath.
    """
    _check_statistic(statistic)
    values = _positional(labels)
    _check_length(pnl, len(values), "labels")
    grouping = _group(values, min_trades=min_trades)
    stratum = _stratum_values(pnl, grouping, statistic)
    finite = np.isfinite(stratum)
    usable = stratum[finite]
    ranked = [value for value, keep in zip(grouping.values, finite, strict=True) if keep]
    if usable.size < review.MIN_STRATA:
        return Separation(
            value=np.nan,
            best=pd.NA,
            worst=pd.NA,
            strata=grouping.strata,
            strata_ranked=int(usable.size),
            trades_ranked=int(grouping.sizes[finite].sum()),
        )
    return Separation(
        value=float(usable.max() - usable.min()),
        best=ranked[int(np.argmax(usable))],
        worst=ranked[int(np.argmin(usable))],
        strata=grouping.strata,
        strata_ranked=int(usable.size),
        trades_ranked=int(grouping.sizes[finite].sum()),
    )


# -- the null -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Null:
    """One set of shuffles, and what every condition separated under each of them."""

    observed: dict[str, Separation]
    draws: Draws
    """A row per shuffle, a column per condition, in :attr:`observed`'s order."""

    trades: int
    dropped: int


def _null(  # noqa: PLR0913 - each keyword is a separate choice the result has to state
    pnl: Floats,
    labels: Mapping[str, Labels],
    *,
    statistic: str,
    min_trades: int,
    iterations: int,
    seed: int,
) -> _Null:
    """Shuffle the P&L ``iterations`` times and re-separate every condition under each shuffle.

    One permutation per iteration, read by all of them: the conditions are measured over the same
    trades and move together, so a family-wise maximum has to be taken over a shared shuffle.
    """
    _check_statistic(statistic)
    if iterations < 1:
        msg = f"a null needs at least one shuffle; got {iterations}"
        raise GuardError(msg)

    at, complete, dropped = _complete(pnl, labels)
    kept = np.asarray(pnl, dtype=np.float64)[at]
    groupings = {name: _group(complete[name], min_trades=min_trades) for name in complete.columns}
    observed = {
        name: separate(kept, complete[name], statistic=statistic, min_trades=min_trades)
        for name in complete.columns
    }

    rng = np.random.default_rng(seed)
    draws = np.full((iterations, len(groupings)), np.nan, dtype=np.float64)
    for draw in range(iterations):
        shuffled = rng.permutation(kept)
        for column, grouping in enumerate(groupings.values()):
            draws[draw, column] = _spread(_stratum_values(shuffled, grouping, statistic))
    return _Null(observed=observed, draws=draws, trades=int(kept.size), dropped=dropped)


def _family_null(draws: Draws) -> Floats:
    """Take the widest separation any condition reached per shuffle, NaN where none of them could."""
    widest = np.where(np.isfinite(draws), draws, -np.inf).max(axis=1)
    return np.where(np.isneginf(widest), np.nan, widest)


def _p_value(null: Floats, observed: float) -> tuple[float, int]:
    """Share of a null's measurable draws that reached ``observed``, and how many voted."""
    finite = null[np.isfinite(null)]
    if not np.isfinite(observed) or finite.size == 0:
        return np.nan, int(finite.size)
    return float((finite >= observed).mean()), int(finite.size)


def screen(  # noqa: PLR0913 - each keyword is a separate choice the report has to state
    pnl: Floats,
    labels: Mapping[str, Labels],
    *,
    statistic: str = "expectancy",
    min_trades: int = review.MIN_TRADES,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
) -> pd.DataFrame:
    """Test every condition against shuffled labels, and the best of them against all of them.

    A trade any condition leaves null is dropped from all of them, so the family-wise maximum
    compares conditions measured over one set of trades rather than over each one's own.
    ``frame.attrs`` carries how many that was.
    """
    drawn = _null(
        pnl,
        labels,
        statistic=statistic,
        min_trades=min_trades,
        iterations=iterations,
        seed=seed,
    )
    frame = _screen_frame(drawn)
    frame.attrs = {
        "statistic": statistic,
        "min_trades": min_trades,
        "iterations": iterations,
        "trades": drawn.trades,
        "dropped": drawn.dropped,
    }
    return frame


def _screen_frame(drawn: _Null) -> pd.DataFrame:
    """Assemble the screen, most significant family-wise first and widest first within a tie."""
    if not drawn.observed:
        return pd.DataFrame(columns=list(SCREEN_COLUMNS))

    family = _family_null(drawn.draws)
    rows = []
    for column, (condition, separation) in enumerate(drawn.observed.items()):
        alone, _ = _p_value(drawn.draws[:, column], separation.value)
        together, _ = _p_value(family, separation.value)
        rows.append(
            {
                "condition": condition,
                "strata": separation.strata,
                "strata_ranked": separation.strata_ranked,
                "trades_ranked": separation.trades_ranked,
                "separation": separation.value,
                "best": separation.best,
                "worst": separation.worst,
                "p_value": alone,
                FAMILY_COLUMN: together,
            },
        )
    frame = pd.DataFrame(rows, columns=list(SCREEN_COLUMNS))
    ordered = frame.sort_values(
        [FAMILY_COLUMN, "separation"],
        ascending=[True, False],
        na_position="last",
        kind="stable",
    )
    return ordered.reset_index(drop=True)


def permutation_test(  # noqa: PLR0913 - each keyword is a separate choice the result has to state
    pnl: Floats,
    labels: Labels,
    *,
    condition: str = "condition",
    statistic: str = "expectancy",
    min_trades: int = review.MIN_TRADES,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = 0,
) -> SeparationTest:
    """One condition's separation against shuffled labels.

    **For a condition chosen for a reason.** Running it over several and reading the smallest
    ``p_value`` is what :func:`screen` exists to stop; both draw one :class:`_Null`, so the two
    cannot drift apart.
    """
    drawn = _null(
        pnl,
        {condition: labels},
        statistic=statistic,
        min_trades=min_trades,
        iterations=iterations,
        seed=seed,
    )
    separation = drawn.observed[condition]
    column = drawn.draws[:, 0]
    p_value, finite = _p_value(column, separation.value)
    measurable = column[np.isfinite(column)]
    return SeparationTest(
        condition=condition,
        statistic=statistic,
        observed=separation.value,
        null_median=float(np.median(measurable)) if measurable.size else np.nan,
        null_p95=float(np.percentile(measurable, 95)) if measurable.size else np.nan,
        p_value=p_value,
        iterations=iterations,
        draws_finite=finite,
        strata_ranked=separation.strata_ranked,
        trades_ranked=separation.trades_ranked,
    )


# -- the holdout --------------------------------------------------------------


def holdout_test(  # noqa: PLR0913 - each keyword is a separate choice the result has to state
    pnl: Floats,
    labels: Labels,
    *,
    condition: str = "condition",
    statistic: str = "expectancy",
    min_trades: int = review.MIN_TRADES,
    share: float = DEFAULT_HOLDOUT_SHARE,
    held_out: int | None = None,
) -> Holdout:
    """Choose the split on the earlier trades, then read it over the most recent ones.

    ``pnl`` and ``labels`` must be in chronological order, which is what makes the held-out
    trades the recent ones. The held-out strata are **not** re-ranked: re-choosing the best one
    there would hold nothing out, and the answer would be the in-sample answer again.

    A condition the earlier trades could not cut, and one whose strata tied exactly, both name
    one stratum at each end and so have no split to read.
    """
    _check_statistic(statistic)
    values = _positional(labels)
    _check_length(pnl, len(values), "labels")
    cut = _cut(int(pnl.size), share=share, held_out=held_out)

    chosen = separate(pnl[:cut], values.iloc[:cut], statistic=statistic, min_trades=min_trades)
    if not np.isfinite(chosen.value) or chosen.best == chosen.worst:
        return _nothing_to_hold_out(condition, statistic, chosen, in_sample_trades=cut)

    recent, recent_labels = pnl[cut:], values.iloc[cut:].reset_index(drop=True)
    best = recent[_is(recent_labels, chosen.best)]
    worst = recent[_is(recent_labels, chosen.worst)]
    gap = _gap(best, worst, statistic)
    return Holdout(
        condition=condition,
        statistic=statistic,
        best=chosen.best,
        worst=chosen.worst,
        in_sample=chosen.value,
        out_of_sample=gap,
        in_sample_trades=chosen.trades_ranked,
        held_out_trades=int(best.size + worst.size),
        direction_held=bool(gap > 0),
        reported=bool(min(best.size, worst.size) >= min_trades),
    )


def _is(labels: Column, value: object) -> Flags:
    """Mask of the trades carrying one label, with a null reading as "not this one"."""
    return np.asarray((labels == value).fillna(value=False), dtype=np.bool_)


def _gap(best: Floats, worst: Floats, statistic: str) -> float:
    """Measure the two chosen strata's gap out of sample, NaN where either is empty or unbounded."""
    if not best.size or not worst.size:
        return np.nan
    gap = stats.trade_statistic(best, statistic) - stats.trade_statistic(worst, statistic)
    return float(gap) if np.isfinite(gap) else np.nan


def _cut(trades: int, *, share: float, held_out: int | None) -> int:
    """Where the recent trades begin, refusing a split that would leave one side empty."""
    if held_out is None:
        if not 0.0 < share < 1.0:
            msg = f"a holdout share must sit strictly between 0 and 1; got {share}"
            raise GuardError(msg)
        held_out = round(trades * share)
    if held_out < 1 or held_out >= trades:
        msg = (
            f"holding out {held_out} of {trades} trades leaves one side empty, so there is "
            f"either nothing to choose a split on or nothing to read it over"
        )
        raise GuardError(msg)
    return trades - held_out


def _nothing_to_hold_out(
    condition: str,
    statistic: str,
    chosen: Separation,
    *,
    in_sample_trades: int,
) -> Holdout:
    """Report a condition with no split to hold out: uncuttable in sample, or every stratum tied."""
    return Holdout(
        condition=condition,
        statistic=statistic,
        best=chosen.best,
        worst=chosen.worst,
        in_sample=chosen.value,
        out_of_sample=np.nan,
        in_sample_trades=in_sample_trades,
        held_out_trades=0,
        direction_held=False,
        reported=False,
    )


# -- one review's conditions, guarded -----------------------------------------


def guard(  # noqa: PLR0913 - each keyword is a separate choice the report has to state
    log: pd.DataFrame,
    annotation: Annotation,
    *,
    by: str = "expectancy",
    min_trades: int = review.MIN_TRADES,
    conditions: Sequence[str] | None = None,
    iterations: int = DEFAULT_ITERATIONS,
    share: float = DEFAULT_HOLDOUT_SHARE,
    held_out: int | None = None,
    seed: int = 0,
) -> Guard:
    """Run all three mitigations over the conditions :func:`nqbt.review.review` would rank.

    ``by`` is the statistic a separation is measured in and must be one :data:`STATISTICS` holds.
    The trades are the annotation's matched subset in the order they were entered, because "the
    most recent" is not a question a log without times can answer.
    """
    _check_statistic(by, argument="by")
    pnl, labels = _trades(log, annotation, conditions)
    screened = screen(pnl, labels, statistic=by, min_trades=min_trades, iterations=iterations, seed=seed)
    held = [
        holdout_test(
            pnl,
            labels[name],
            condition=name,
            statistic=by,
            min_trades=min_trades,
            share=share,
            held_out=held_out,
        )
        for name in screened["condition"]
    ]
    return Guard(
        screen=screened,
        holdout=pd.DataFrame([one.as_dict() for one in held], columns=list(HOLDOUT_COLUMNS)),
        statistic=by,
        conditions=tuple(labels),
        iterations=iterations,
        min_trades=min_trades,
        trades=int(screened.attrs["trades"]),
        dropped=int(screened.attrs["dropped"]),
        held_out=int(pnl.size) - _cut(int(pnl.size), share=share, held_out=held_out),
    )


def _trades(
    log: pd.DataFrame,
    annotation: Annotation,
    conditions: Sequence[str] | None,
) -> tuple[Floats, dict[str, Column]]:
    """Gather the per-trade P&L in entry order, and one label per trade for every chosen condition."""
    notes.check_excluded(annotation.frame, what="an annotation being guarded")
    reviewable = annotation.reviewable
    if reviewable.empty:
        msg = (
            f"no trade of this annotation matched the dataset ({annotation}), so there is "
            f"nothing to guard. Annotate against the bars these trades happened on."
        )
        raise GuardError(msg)

    per_trade = stats.per_trade(log[log["trade_id"].isin(reviewable.index)])
    if "entry_time" not in per_trade.columns:
        msg = (
            "this log carries no entry_time, so its trades cannot be put in the order they "
            "happened and 'the most recent N' has no meaning over them"
        )
        raise GuardError(msg)

    ordered = per_trade.sort_values("entry_time", kind="stable")
    aligned = reviewable.loc[ordered.index]
    chosen = _chosen(reviewable, annotation, conditions)
    return ordered["net_pnl"].to_numpy(np.float64), {
        name: aligned[name].reset_index(drop=True) for name in chosen
    }


def _chosen(
    reviewable: pd.DataFrame,
    annotation: Annotation,
    conditions: Sequence[str] | None,
) -> tuple[str, ...]:
    """Pick the conditions to guard: the caller's, checked, or every one a review could cut by."""
    if conditions is None:
        return review.stratifiable(reviewable, annotation.conditions)
    unknown = [name for name in conditions if name not in reviewable.columns]
    if unknown:
        msg = f"no condition(s) {unknown} in this annotation; it holds {sorted(reviewable.columns)}"
        raise GuardError(msg)
    return tuple(conditions)


# -- shared checks ------------------------------------------------------------


def _check_statistic(statistic: str, *, argument: str = "statistic") -> None:
    """Refuse a statistic a separation cannot honestly be measured in."""
    if statistic in STATISTICS:
        return
    msg = (
        f"cannot separate strata by {argument}={statistic!r}; a guard measures a separation in "
        f"{list(STATISTICS)}, which is what a review reports and a shuffle can move"
    )
    raise GuardError(msg)


def _check_length(pnl: Floats, given: int, what: str) -> None:
    """Refuse a label per anything but a trade, which would silently mis-stratify every one."""
    if given == pnl.size:
        return
    msg = f"{given} {what} for {pnl.size} trades; a guard takes one label per trade"
    raise GuardError(msg)


def _complete(pnl: Floats, labels: Mapping[str, Labels]) -> tuple[Counts, pd.DataFrame, int]:
    """Find the trades every condition labels: where they are, what they carry, how many are not.

    A maximum over conditions measured on different trades would not be comparing like with
    like, so the screen narrows to the trades all of them cover rather than to each one's own.
    The labels come back re-indexed from zero, because a stratum is positions into the P&L the
    caller keeps rather than into the P&L it started with.
    """
    if not labels:
        return np.arange(pnl.size, dtype=np.int64), pd.DataFrame(index=pd.RangeIndex(pnl.size)), 0
    columns = {}
    for name, values in labels.items():
        column = _positional(values)
        _check_length(pnl, len(column), f"{name} labels")
        columns[name] = column
    frame = pd.DataFrame(columns)
    complete = frame.dropna()
    at = complete.index.to_numpy(np.int64)
    return at, complete.reset_index(drop=True), int(len(frame) - len(complete))
