"""Realised P&L, stratified by what was true when each trade was taken.

The review's question is **which trades worked, and what was true when they did**. Every number
here is a :class:`nqbt.stats.Summary` field computed over a subset of one trade log, so nothing
in this module defines a statistic: it reads an :class:`nqbt.annotate.Annotation`, groups the
trades by one condition at a time, and ranks the conditions by how far apart their strata sit.

**Time of day is the headline**, reported before anything else and paired with both forms of
volume so that "this hour is always busy" and "this hour was unusually busy" are separable. The
final phase holds the forced flat, which makes a poor result there an artefact rather than a
finding until the two are told apart -- ``docs/roadmap.md`` §M11.3.

**Every output is hypothesis-generating, not confirmatory.** A few hundred trades against a few
dozen conditions is a multiple-comparisons machine; the minimum stratum here is one third of the
guard, and :mod:`nqbt.guard` is the shuffled-label null and the holdout that finish it.
:data:`STATUS` says so in the report itself, because a separation read without that sentence is
the failure mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

import numpy as np
import pandas as pd

from nqbt import annotate, notes, stats, timeofday, trades

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from nqbt.annotate import Annotation
    from nqbt.stats import Summary

__all__ = [
    "FORCED_EXIT_NOTE",
    "MAX_STRATA",
    "MIN_STRATA",
    "MIN_TRADES",
    "PHASE_COLUMN",
    "RANKING_COLUMNS",
    "REPORTED",
    "STATISTICS_FROM",
    "STATUS",
    "Review",
    "ReviewError",
    "rank_conditions",
    "review",
    "stratifiable",
    "stratify",
    "time_of_day",
]

MIN_TRADES = 30
"""Fewest trades a stratum needs before it is ranked, the floor ``sweep.rank`` already enforces.

The smallest samples produce the most extreme statistics, so without a floor they lead every
ranking. A stratum under it is still reported, and marked.
"""

MIN_STRATA = 2
"""Fewest values a condition must take to be a comparison. One value separates nothing."""

MAX_STRATA = 12
"""Most distinct values a condition may take and still be a stratification.

Above it the split is a list of trades rather than a comparison, and no stratum would survive
:data:`MIN_TRADES` anyway.
"""

REPORTED = ("trades", "win_rate", "expectancy", "profit_factor", "mean_r")
"""The :class:`nqbt.stats.Summary` fields a stratum is reported by, in column order."""

STATISTICS_FROM = {
    "bars_held": ("avg_bars_held",),
    "mae_points": ("avg_mae_points",),
    "mfe_points": ("avg_mfe_points",),
    "r_multiple": ("mean_r", "r_p10", "r_median", "r_p90"),
    "ambiguous_bar": ("ambiguous_share",),
}
"""Which summary fields each nullable column feeds, so a log leaving one empty omits exactly
those and no more. A :data:`nqbt.trades.NULLABLE` column absent from here feeds none of them.
The wording of each omission comes from the producer -- :data:`nqbt.trade_import.UNPOPULATED`.
"""

PHASE_COLUMN = "entry_phase"
""":mod:`nqbt.timeofday`'s coarse label at the entry bar: the headline stratification."""

STATUS = (
    "HYPOTHESIS-GENERATING, NOT CONFIRMATORY -- a few hundred trades against a few dozen "
    "conditions is a multiple-comparisons machine, and the minimum stratum below is one third of "
    "the guard. Run nqbt.guard over these trades for the other two, and take a separation from "
    "here to a sweep, never to a decision (#48)."
)
"""The status every report states about itself, rather than leaving it to be remembered."""

_FORCED_EXIT_VALUE = timeofday.FORCED_EXIT_PHASE.name.lower()

FORCED_EXIT_NOTE = (
    f"{_FORCED_EXIT_VALUE} contains the session-close flatten, so a poor result there may be "
    "the clock rather than the hour; read session_close_share beside it."
)
"""What has to travel with any time-of-day result touching the final phase."""

_PLACEHOLDERS = {"bars_held": 0, "ambiguous_bar": False}
"""What an absent column holds while :func:`nqbt.stats.summarise` runs over it.

``summarise`` refuses a nullable column rather than reporting a figure nobody measured, which is
correct and would otherwise also cost the statistics that column does *not* feed. Every field an
absent column does feed is dropped by name before a row is built, so **no placeholder ever
reaches a reported number** -- ``docs/roadmap.md`` §M11.3.
"""

_NEEDED = (
    "trade_id",
    "net_pnl",
    "commission",
    "exit_reason",
    "exit_time",
    "bars_held",
    "mae_points",
    "mfe_points",
    "r_multiple",
    "ambiguous_bar",
)
"""Columns ``summarise`` reads, which a log must carry even where it leaves them null.

``exit_time`` is the exception it may not leave null: ``summarise`` refuses a log that cannot
say which day each trade closed on, so a review refuses it here rather than at the first
stratum -- ``docs/roadmap.md`` § "Sharpe and Sortino are refused rather than approximated".
"""

_ABSOLUTE_VOLUME = "entry_volume_"
_RELATIVE_VOLUME = "entry_relative_volume_"
_VOLUME_STATE = "entry_volume_state_"

_PHASE_ORDER = (
    *(phase.name.lower() for phase in timeofday.SessionPhase),
    annotate.OUT_OF_SESSION_LABEL,
    annotate.UNDEFINED_LABEL,
)
"""Session order, which is the order phases are reported in -- never alphabetical."""

RANKING_COLUMNS = ("condition", "strata", "strata_ranked", "trades_ranked", "separation", "best", "worst")
"""One ranked condition's columns. :mod:`nqbt.guard` builds on them, so they are not private."""


class ReviewError(ValueError):
    """Raised when a trade log and an annotation cannot honestly be reviewed together."""


@dataclass(frozen=True, slots=True)
class Review:
    """One trade log's realised P&L, cut by every condition its annotation can be cut by."""

    strata: pd.DataFrame
    """A row per ``(condition, value)``: the stratum's sample and its :data:`REPORTED` statistics."""
    ranking: pd.DataFrame
    """One row per condition, widest separation first. **Candidates, not findings.**"""
    time_of_day: pd.DataFrame
    """The headline, in session order. Empty if the dataset carried no clock."""
    omitted: Mapping[str, str]
    """Statistic -> why this log cannot support it, in the producer's own words."""
    conditions: tuple[str, ...]
    """The conditions stratified."""
    skipped: tuple[str, ...]
    """The conditions that are raw series or take too many values -- :func:`stratifiable`."""
    trades: int
    """Trades the annotation covered, matched or not."""
    reviewed: int
    """Trades actually stratified: the matched subset."""
    min_trades: int
    by: str

    @override
    def __str__(self) -> str:
        """Render the report: what it is worth, then time of day, then the ranking."""
        parts: list[str] = [
            (
                f"{self.reviewed}/{self.trades} trades reviewed, {len(self.conditions)} of "
                f"{len(self.conditions) + len(self.skipped)} conditions stratified, "
                f"minimum {self.min_trades} trades per stratum"
            ),
            STATUS,
            "",
            *self._time_of_day_lines(),
            "",
            f"Conditions, by how far {self.by} separates their strata",
            self.ranking.to_string() if not self.ranking.empty else "  nothing to rank",
        ]
        if self.omitted:
            parts += ["", "Omitted:", *(f"  {name} -- {why}" for name, why in sorted(self.omitted.items()))]
        return "\n".join(parts)

    def _time_of_day_lines(self) -> list[str]:
        """Render the headline section, or say why there is none."""
        if self.time_of_day.empty:
            return [f"No {PHASE_COLUMN}: this annotation was built over a dataset with no clock."]
        lines: list[str] = [f"Time of day ({PHASE_COLUMN})", self.time_of_day.to_string()]
        if _FORCED_EXIT_VALUE in self.time_of_day.index:
            lines.append(f"  {FORCED_EXIT_NOTE}")
        return lines


def review(
    log: pd.DataFrame,
    annotation: Annotation,
    by: str = "expectancy",
    min_trades: int = MIN_TRADES,
    conditions: Sequence[str] | None = None,
    unpopulated: Mapping[str, str] | None = None,
) -> Review:
    """Stratify ``log``'s realised P&L by every condition ``annotation`` can be cut by.

    ``by`` names the statistic conditions are ranked on. ``unpopulated`` is the producer's reason
    per absent column -- :attr:`nqbt.trade_import.ImportedTrades.unpopulated` -- and decides the
    wording of an omission, never which statistics are omitted.
    """
    if by not in REPORTED:
        msg: str = f"cannot rank by {by!r}; a review reports {list(REPORTED)}"
        raise ReviewError(msg)

    legs, reviewable, omitted = _prepare(log, annotation, unpopulated)
    if by in omitted:
        msg = f"cannot rank by {by!r}: {omitted[by]}"
        raise ReviewError(msg)

    available: tuple[str, ...] = stratifiable(reviewable, annotation.conditions)
    chosen: tuple[str, ...] = available if conditions is None else _requested(reviewable, conditions)
    frames: list[pd.DataFrame] = [
        _strata(legs, reviewable[name], name, min_trades=min_trades, omitted=omitted) for name in chosen
    ]
    strata: pd.DataFrame = pd.concat(frames, ignore_index=True) if frames else _empty_strata(omitted)

    headline: pd.DataFrame = pd.DataFrame()
    if PHASE_COLUMN in reviewable.columns:
        headline = _time_of_day(legs, reviewable, min_trades=min_trades, omitted=omitted)

    return Review(
        strata=strata,
        ranking=rank_conditions(strata, by=by),
        time_of_day=headline,
        omitted=omitted,
        conditions=tuple(chosen),
        skipped=tuple(name for name in annotation.conditions if name not in set(chosen)),
        trades=annotation.trades,
        reviewed=len(reviewable),
        min_trades=min_trades,
        by=by,
    )


def stratify(
    log: pd.DataFrame,
    annotation: Annotation,
    condition: str,
    min_trades: int = MIN_TRADES,
    unpopulated: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """One condition's strata: a row per value it took, summarising the trades that carried it."""
    legs, reviewable, omitted = _prepare(log, annotation, unpopulated)
    _check_stratifiable(reviewable, condition)
    return _strata(legs, reviewable[condition], condition, min_trades=min_trades, omitted=omitted)


def time_of_day(
    log: pd.DataFrame,
    annotation: Annotation,
    min_trades: int = MIN_TRADES,
    unpopulated: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Realised P&L by session phase, in session order, with both forms of volume beside it.

    Relative volume answers *was this unusual for the time of day* and absolute volume answers
    *was there anything here to trade at all*; the pair is what separates an hour that is always
    busy from one that was unusually busy. Reported first because it is the stratification most
    likely to show real structure in a discretionary record -- ``docs/roadmap.md`` §M11.3.
    """
    legs, reviewable, omitted = _prepare(log, annotation, unpopulated)
    if PHASE_COLUMN not in reviewable.columns:
        msg: str = (
            f"this annotation carries no {PHASE_COLUMN}, so there is no clock to stratify by; "
            f"prepare() the dataset with needs_time_of_day=True."
        )
        raise ReviewError(msg)
    return _time_of_day(legs, reviewable, min_trades=min_trades, omitted=omitted)


def stratifiable(frame: pd.DataFrame, conditions: Sequence[str]) -> tuple[str, ...]:
    """Pick the conditions of ``frame`` that are a stratification rather than a list of trades.

    A raw series is excluded rather than bucketed here: where to cut it is the review's most
    consequential choice, and :class:`nqbt.annotate.LabelThresholds` is where a review states the
    cut it tested -- ``docs/roadmap.md`` §M11.3.
    """
    return tuple(name for name in conditions if _is_stratifiable(frame[name]))


def rank_conditions(strata: pd.DataFrame, by: str = "expectancy") -> pd.DataFrame:
    """Order the conditions by how far ``by`` separates the strata that met the minimum.

    The separation is the range across ranked strata: the widest gap the condition produced, and
    therefore the quantity a hypothesis would be drawn from and the one :func:`nqbt.guard.screen`
    shuffles the labels against. **A wide separation is a candidate, not a finding** --
    :data:`STATUS`.
    """
    if strata.empty:
        return pd.DataFrame(columns=list(RANKING_COLUMNS))
    if by not in strata.columns:
        msg: str = f"no {by!r} column in these strata; it was omitted when they were built"
        raise ReviewError(msg)

    rows: list[dict[str, object]] = []
    for condition, group in strata.groupby("condition", sort=False):
        ranked: pd.DataFrame = group[group["reported"].astype(bool)]
        usable: pd.DataFrame = ranked[np.isfinite(ranked[by].to_numpy(np.float64))]
        separation, best, worst = _separation(usable, by)
        rows.append(
            {
                "condition": condition,
                "strata": len(group),
                "strata_ranked": len(usable),
                "trades_ranked": int(usable["trades"].sum()),
                "separation": separation,
                "best": best,
                "worst": worst,
            },
        )
    ordered: pd.DataFrame = pd.DataFrame(rows).sort_values("separation", ascending=False, na_position="last")
    return ordered.reset_index(drop=True)


# -- the trades a review runs over --------------------------------------------


def _prepare(
    log: pd.DataFrame,
    annotation: Annotation,
    unpopulated: Mapping[str, str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Gather the legs to summarise, the rows to group them by, and what this log cannot report."""
    _check_columns(log)
    _check_same_log(log, annotation)
    notes.check_excluded(annotation.frame, what="an annotation being reviewed")
    reviewable: pd.DataFrame = annotation.reviewable
    if reviewable.empty:
        msg: str = (
            f"no trade of this annotation matched the dataset ({annotation}), so there is "
            f"nothing to stratify. Annotate against the bars these trades happened on."
        )
        raise ReviewError(msg)

    legs: pd.DataFrame = log[log["trade_id"].isin(reviewable.index)]
    absent: tuple[str, ...] = _absent_columns(legs)
    return _summarisable(legs, absent), reviewable, _reasons(absent, legs, unpopulated or {})


def _check_columns(log: pd.DataFrame) -> None:
    """Refuse a frame that is not a trade log before anything reads a column of it."""
    missing: list[str] = [name for name in _NEEDED if name not in log.columns]
    if missing:
        msg: str = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise ReviewError(msg)


def _check_same_log(log: pd.DataFrame, annotation: Annotation) -> None:
    """Refuse an annotation built over other trades, which would carry another log's context."""
    known: set[int] = set(log["trade_id"].dropna().tolist())
    unknown: list[int] = [trade for trade in annotation.frame.index.tolist() if trade not in known]
    if unknown:
        msg: str = (
            f"{len(unknown)} annotated trade(s) are not in this log, the first being "
            f"{unknown[0]}; the annotation was built over different trades."
        )
        raise ReviewError(msg)


def _absent_columns(legs: pd.DataFrame) -> tuple[str, ...]:
    """Find the columns this log leaves null on every row, which cannot be summarised through."""
    return tuple(name for name in STATISTICS_FROM if name in legs.columns and legs[name].isna().all())


def _reasons(absent: Sequence[str], legs: pd.DataFrame, unpopulated: Mapping[str, str]) -> dict[str, str]:
    """Every statistic this log cannot support, and the reason for each in the producer's words."""
    reasons: dict[str, str] = {}
    for column in absent:
        why: str = unpopulated.get(column, f"this log leaves {column} null on every row")
        for name in STATISTICS_FROM[column]:
            reasons[name] = why
    if not _simulator_exit_reasons(legs):
        reasons["session_close_share"] = (
            "this log's exit reasons are its source's own rather than the simulator's, so a "
            "position closed by the clock cannot be told from one closed by a rule"
        )
    return reasons


def _simulator_exit_reasons(legs: pd.DataFrame) -> bool:
    """Whether the exit reasons are the vocabulary that names the session-close flatten."""
    return set(legs["exit_reason"].dropna().unique()) <= set(trades.EXIT_REASONS.values())


def _summarisable(legs: pd.DataFrame, absent: Sequence[str]) -> pd.DataFrame:
    """``legs`` with each absent column filled, so ``summarise`` runs over the columns that are not.

    Every statistic a filled column feeds is already omitted by name, so no value substituted
    here can reach a reported number -- :data:`_PLACEHOLDERS`.
    """
    fills: list[str] = [name for name in absent if name in _PLACEHOLDERS]
    if not fills:
        return legs
    filled: pd.DataFrame = legs.copy()
    for name in fills:
        filled[name] = _PLACEHOLDERS[name]
    return filled


# -- the strata ---------------------------------------------------------------


def _is_stratifiable(column: pd.Series) -> bool:  # type: ignore[explicit-any]  # a condition's dtype is its own
    """Whether one condition takes few enough values, and is not a raw series."""
    if pd.api.types.is_float_dtype(column.dtype):
        return False
    return MIN_STRATA <= column.dropna().nunique() <= MAX_STRATA


def _requested(reviewable: pd.DataFrame, conditions: Sequence[str]) -> tuple[str, ...]:
    """Check every condition the caller named, rather than silently dropping one."""
    for name in conditions:
        _check_stratifiable(reviewable, name)
    return tuple(conditions)


def _check_stratifiable(reviewable: pd.DataFrame, condition: str) -> None:
    """Refuse a condition that is absent, constant, or a raw series needing a cut."""
    if condition not in reviewable.columns:
        msg: str = f"no condition {condition!r} in this annotation; it holds {sorted(reviewable.columns)}"
        raise ReviewError(msg)
    if _is_stratifiable(reviewable[condition]):
        return
    values: int = reviewable[condition].dropna().nunique()
    msg = (
        f"{condition!r} takes {values} distinct value(s) over these trades, which is not a "
        f"stratification. A raw series has to be cut before it is a condition, and where to cut "
        f"it is a choice a review states: annotate with LabelThresholds."
    )
    raise ReviewError(msg)


def _strata(  # type: ignore[explicit-any]  # a condition's dtype is its own
    legs: pd.DataFrame,
    values: pd.Series,
    condition: str,
    min_trades: int,
    omitted: Mapping[str, str],
) -> pd.DataFrame:
    """Summarise the legs of the trades carrying each value ``condition`` took, a row per value."""
    rows: list[dict[str, object]] = []
    for value, ids in _groups(values):
        summary: Summary = stats.summarise(legs[legs["trade_id"].isin(ids)])
        rows.append(
            {
                "condition": condition,
                "value": value,
                **_reported(summary, omitted),
                "reported": summary.trades >= min_trades,
            },
        )
    return pd.DataFrame(rows, columns=["condition", "value", *_columns(omitted), "reported"])


def _groups(values: pd.Series) -> list[tuple[object, pd.Index]]:  # type: ignore[explicit-any]  # a condition's dtype is its own
    """Each distinct value of one condition and the trade ids carrying it, nulls excluded."""
    present = values.dropna()
    return list(present.groupby(present, sort=True, observed=True).groups.items())


def _columns(omitted: Mapping[str, str]) -> list[str]:
    """List the statistics this log can support, in :data:`REPORTED` order."""
    return [name for name in REPORTED if name not in omitted]


def _reported(summary: stats.Summary, omitted: Mapping[str, str]) -> dict[str, float]:
    """Read the reportable statistics off one summary. Nothing is computed here."""
    return {name: getattr(summary, name) for name in _columns(omitted)}


def _empty_strata(omitted: Mapping[str, str]) -> pd.DataFrame:
    """Build the strata frame's columns for a review that found nothing to cut by."""
    return pd.DataFrame(columns=["condition", "value", *_columns(omitted), "reported"])


def _separation(usable: pd.DataFrame, by: str) -> tuple[float, object, object]:
    """Measure the widest gap in ``by`` across a condition's strata, and name both its ends."""
    if len(usable) < MIN_STRATA:
        return np.nan, pd.NA, pd.NA
    best = usable.loc[usable[by].idxmax()]
    worst = usable.loc[usable[by].idxmin()]
    # A row of a numeric column; pandas types every cell as the frame's widest possible value.
    return float(best[by] - worst[by]), best["value"], worst["value"]  # type: ignore[arg-type]


# -- the headline -------------------------------------------------------------


def _time_of_day(
    legs: pd.DataFrame,
    reviewable: pd.DataFrame,
    min_trades: int,
    omitted: Mapping[str, str],
) -> pd.DataFrame:
    """Assemble the phase strata in session order, with the volume medians and the clock's share."""
    frame: pd.DataFrame = _strata(
        legs, reviewable[PHASE_COLUMN], PHASE_COLUMN, min_trades=min_trades, omitted=omitted
    )
    ordered: pd.DataFrame = frame.drop(columns="condition").set_index("value")
    ordered = ordered.reindex([value for value in _PHASE_ORDER if value in ordered.index])
    ordered.index.name = PHASE_COLUMN
    beside: pd.DataFrame = _volume_medians(reviewable, ordered.index)
    if "session_close_share" not in omitted:
        beside["session_close_share"] = _forced_exit_share(legs, reviewable, ordered.index)
    return ordered.join(beside)


def _volume_medians(reviewable: pd.DataFrame, phases: pd.Index[int]) -> pd.DataFrame:
    """Median absolute and relative volume per phase: what is normal here, and what was not.

    The absolute figure alone cannot say whether a busy hour was unusually busy, and the relative
    figure alone cannot say whether there was anything there to trade.
    """
    columns: list[str] = _volume_columns(reviewable)
    if not columns:
        return pd.DataFrame(index=phases)
    grouped: pd.DataFrame = reviewable.groupby(reviewable[PHASE_COLUMN], observed=True)[columns].median()
    named: pd.DataFrame = grouped.rename(columns={name: f"median_{name}" for name in columns})
    return named.reindex(phases)


def _volume_columns(reviewable: pd.DataFrame) -> list[str]:
    """Both forms of volume at the entry bar, and never the state label cut from one of them."""
    return [
        name
        for name in reviewable.columns
        if name.startswith((_ABSOLUTE_VOLUME, _RELATIVE_VOLUME)) and not name.startswith(_VOLUME_STATE)
    ]


def _forced_exit_share(
    legs: pd.DataFrame,
    reviewable: pd.DataFrame,
    phases: pd.Index[int],
) -> pd.Series[float]:
    """Share of each phase's leg exits taken by the clock rather than by the strategy's own rules.

    What separates "this hour trades badly" from "this hour's trades were closed by the clock",
    which the final phase demands by construction -- :data:`FORCED_EXIT_NOTE`.
    """
    per_leg: pd.Series[float] = legs["trade_id"].map(reviewable[PHASE_COLUMN])
    closed: pd.Series[bool] = legs["exit_reason"] == stats.SESSION_CLOSE
    return closed.groupby(per_leg, observed=True).mean().reindex(phases)  # type: ignore[return-value]  # a mean of booleans is a float
