"""Market context at the bars a trade was entered and left on.

One annotation row per trade, carrying every condition the :class:`~nqbt.context.Dataset` holds,
so a review can stratify realised P&L by them. Nothing here knows where the trades came from: a
sweep's log and an imported NT8 history annotate through the same call, which is what lets a
hypothesis raised on a few hundred real trades be tested against thousands of simulated ones.

Two traps this module exists to close, both of which produce plausible numbers rather than an
error -- ``docs/roadmap.md`` §M11.2:

**Back-adjustment.** A real fill at 18076.75 appears nowhere in a back-adjusted continuous
series, and the bar lookup still succeeds. Every fill price is therefore checked against the bar
it matched, and :func:`contract_bars` reads the per-contract cache rather than either continuous
series.

**Bar alignment.** Timestamps are end-of-bar, so a fill at 14:23:47 belongs to the bar stamped
14:24. A log that already carries bar indices keeps them; only one without them is resolved from
its timestamps, because a bar's own stamp is not a fill time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import ingest, notes, paths, regime, timeofday, trend, volume
from nqbt.instruments import ContractId

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from nqbt.context import Dataset

__all__ = [
    "NO_LABELS",
    "OUT_OF_SESSION_LABEL",
    "UNDEFINED_LABEL",
    "UNMATCHED",
    "Annotation",
    "AnnotationError",
    "LabelThresholds",
    "annotate_trades",
    "bars_for_fills",
    "contract_bars",
]

UNMATCHED = -1
"""Bar index for a fill no bar of the dataset covers. Negative rather than zero, so an unmatched
fill cannot be read as the first bar.
"""

UNDEFINED_LABEL = "undefined"
"""What a bar inside a warm-up, or with no baseline, is called. One name for all three label
kinds, each of which spells it :data:`nqbt.regime.UNDEFINED` in its own module.
"""

OUT_OF_SESSION_LABEL = "out_of_session"
"""What a bar in no session is called, a different statement from :data:`UNDEFINED_LABEL`."""

type Column = np.ndarray | pd.DatetimeIndex

_PHASE_NAMES = tuple(phase.name.lower() for phase in timeofday.SessionPhase)
_REGIME_NAMES = tuple(state.name.lower() for state in regime.Regime)
_VOLUME_NAMES = tuple(state.name.lower() for state in volume.VolumeState)
_TREND_NAMES = tuple(state.name.lower() for state in trend.Trend)
"""Label values are lowercase names rather than codes, as ``exit_reason`` already is."""

_SIDES = ("entry", "exit")


class AnnotationError(ValueError):
    """Raised when a trade log cannot be honestly joined to a dataset."""


def _check_pair(first: str, low: float | None, second: str, high: float | None) -> None:
    """Refuse half a pair of thresholds, which would label off one boundary."""
    if (low is None) != (high is None):
        given, absent = (first, second) if low is not None else (second, first)
        msg = f"{given} was given without {absent}; a label needs both cut points or neither"
        raise AnnotationError(msg)


@dataclass(frozen=True, slots=True)
class LabelThresholds:
    """The cut points a raw series needs before it is a label.

    Every field defaults to ``None``, which emits the raw series and no label: a threshold is a
    choice the review has to be able to state, so there is no default that could be right. Each
    pair is both or neither.
    """

    regime_consolidating_below: float | None = None
    regime_directional_above: float | None = None
    volume_thin_below: float | None = None
    volume_heavy_above: float | None = None
    trend_min_agreement: int | None = None

    def __post_init__(self) -> None:
        """Validate each pair through the module that owns it."""
        _check_pair(
            "regime_consolidating_below",
            self.regime_consolidating_below,
            "regime_directional_above",
            self.regime_directional_above,
        )
        if self.labels_regimes:
            regime.validate_thresholds(
                float(self.regime_consolidating_below),  # type: ignore[arg-type]  # the property checked
                float(self.regime_directional_above),  # type: ignore[arg-type]  # the property checked
            )
        _check_pair(
            "volume_thin_below",
            self.volume_thin_below,
            "volume_heavy_above",
            self.volume_heavy_above,
        )
        if self.labels_volume:
            volume.validate_thresholds(
                float(self.volume_thin_below),  # type: ignore[arg-type]  # the property checked
                float(self.volume_heavy_above),  # type: ignore[arg-type]  # the property checked
            )
        if self.trend_min_agreement is not None:
            trend.validate_min_agreement(self.trend_min_agreement)

    @property
    def labels_regimes(self) -> bool:
        """Whether a regime label can be cut from an efficiency ratio."""
        return self.regime_consolidating_below is not None and self.regime_directional_above is not None

    @property
    def labels_volume(self) -> bool:
        """Whether a volume-state label can be cut from a relative volume."""
        return self.volume_thin_below is not None and self.volume_heavy_above is not None

    @property
    def labels_trend(self) -> bool:
        """Whether a trend label can be cut from an agreement score."""
        return self.trend_min_agreement is not None


NO_LABELS = LabelThresholds()
"""Raw series only, which is what a caller that has not chosen its thresholds gets."""


@dataclass(frozen=True, slots=True)
class Annotation:
    """Every trade of a log, against the market context at its bars."""

    frame: pd.DataFrame
    """One row per trade, indexed by ``trade_id``. Conditions are null on an unmatched trade,
    and the dtypes do not depend on whether there is one."""

    conditions: tuple[str, ...]
    """The columns a review may stratify by, which is every column but the bookkeeping ones."""

    @property
    def trades(self) -> int:
        """Trades annotated, matched or not."""
        return len(self.frame)

    @property
    def matched(self) -> int:
        """Trades every bar of which was found in the dataset."""
        return int(self.frame["matched"].sum()) if self.trades else 0

    @property
    def unmatched(self) -> int:
        """Trades some bar of which the dataset does not hold, which carry no conditions."""
        return self.trades - self.matched

    @property
    def share(self) -> float:
        """Fraction of trades annotated. No trades is no coverage, not full coverage."""
        return self.matched / self.trades if self.trades else 0.0

    @property
    def reviewable(self) -> pd.DataFrame:
        """The matched subset: what a review may be computed over."""
        return self.frame[self.frame["matched"].astype(bool)]

    def __str__(self) -> str:
        """Render the matched share and how many conditions each row carries."""
        return (
            f"{self.matched}/{self.trades} trades annotated ({self.share:.1%}), "
            f"{len(self.conditions)} conditions"
        )


def bars_for_fills(
    index: pd.DatetimeIndex,
    times: pd.DatetimeIndex,
    *,
    bar_minutes: int | None = None,
) -> np.ndarray:
    """Index of the bar each fill happened in, :data:`UNMATCHED` where no bar covers it.

    Timestamps are end-of-bar and a fill matches the first bar stamped **strictly after** it, so
    the bar stamped ``s`` covers ``[s - bar_minutes, s)`` and a fill printed at a bar's own stamp
    belongs to the *next* bar -- ``docs/roadmap.md`` §M11.2. ``bar_minutes`` is inferred from the
    index when not given.
    """
    stamps = pd.DatetimeIndex(index)
    fills = pd.DatetimeIndex(times)
    if (stamps.tz is None) != (fills.tz is None):
        msg = (
            "cannot match fills to bars across a timezone-aware and a naive index; the bar "
            "cache is UTC and an imported log is converted to UTC on import"
        )
        raise AnnotationError(msg)

    size = timeofday.infer_bar_minutes(stamps) if bar_minutes is None else int(bar_minutes)
    if size < 1:
        msg = f"bar_minutes must be >= 1, got {size}"
        raise AnnotationError(msg)

    edges = _utc_naive(stamps)
    wanted = _utc_naive(fills)
    positions = np.searchsorted(edges, wanted, side="right")
    inside = positions < edges.size
    covered = np.zeros(wanted.size, dtype=np.bool_)
    covered[inside] = wanted[inside] >= edges[positions[inside]] - np.timedelta64(size, "m")
    return np.where(covered, positions, UNMATCHED).astype(np.int64)


def contract_bars(log: pd.DataFrame, *, cache_dir: Path = paths.CACHE_DIR) -> pd.DataFrame:
    """Read the per-contract bars a log must be annotated against.

    Neither continuous series is an option here: the back-adjusted one shifts every historical
    price by the cumulative roll offset, so the lookup succeeds and every comparison is wrong,
    and the raw one splices two contracts' prices into one series across a roll.
    """
    if "contract" not in log.columns:
        msg = (
            "this log does not name a contract, so the bars it happened on cannot be read for "
            "it; build the dataset yourself. Only an imported log carries the contract."
        )
        raise AnnotationError(msg)
    named = sorted(log["contract"].dropna().unique())
    if len(named) != 1:
        msg = f"expected one contract, got {named}; annotate one contract at a time"
        raise AnnotationError(msg)
    return ingest.load_contract(ContractId.parse(str(named[0])), cache_dir)


def annotate_trades(
    log: pd.DataFrame,
    data: Dataset,
    *,
    thresholds: LabelThresholds = NO_LABELS,
    at_exit: bool = False,
    price_tolerance: float = 0.0,
) -> Annotation:
    """Join every trade of ``log`` to the conditions ``data`` holds at its entry bar.

    ``at_exit`` adds the same conditions at the exit bar; it changes what is emitted, never
    which trades match. ``price_tolerance`` is in points and admits a fill outside the bar it
    matched -- zero for real fills, and the simulator's slippage for a slipped simulated log.
    """
    if len(data) == 0:
        msg = "cannot annotate against a dataset holding no bars"
        raise AnnotationError(msg)
    _check_one_contract(log)
    _check_columns(log)
    notes.check_excluded(log, what="a trade log being annotated")

    legs = {side: _resolve_bars(log, data, side) for side in _SIDES}
    for side, bars in legs.items():
        _check_prices(log, data, bars, side=side, tolerance=price_tolerance)

    trade_ids, per_trade, matched = _per_trade_bars(log, legs)

    columns: dict[str, Column] = {"matched": matched}
    conditions: list[str] = []
    for side in _SIDES:
        if side == "exit" and not at_exit:
            continue
        bars = per_trade[side]
        at = np.where(matched, bars, 0)
        columns.update(_bar_columns(data, bars, at, side))
        for name, values in _conditions_at(data, at, thresholds).items():
            column = f"{side}_{name}"
            columns[column] = values
            conditions.append(column)

    return Annotation(frame=_to_frame(columns, trade_ids, matched), conditions=tuple(conditions))


# -- resolving bars -----------------------------------------------------------


def _utc_naive(stamps: pd.DatetimeIndex) -> np.ndarray:
    """Timestamps as naive UTC ``datetime64``, the one form two indices compare in."""
    naive = stamps.tz_convert("UTC").tz_localize(None) if stamps.tz is not None else stamps
    return naive.to_numpy().astype("datetime64[ns]")


def _check_one_contract(log: pd.DataFrame) -> None:
    """Refuse a log spanning more than one contract, which one dataset cannot describe."""
    for name in ("contract", "instrument"):
        if name not in log.columns:
            continue
        found = sorted(log[name].dropna().unique())
        if len(found) > 1:
            msg = (
                f"this log spans {len(found)} values of {name} ({found}), and a dataset is one "
                f"series; annotate one at a time. NQ and MNQ trade at nearly the same price, so "
                f"nothing downstream would catch the mixture."
            )
            raise AnnotationError(msg)
        return


def _check_columns(log: pd.DataFrame) -> None:
    """Refuse a frame that is not a trade log before anything reads a column of it."""
    missing = [name for name in ("trade_id", "entry_price", "exit_price") if name not in log.columns]
    if missing:
        msg = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise AnnotationError(msg)


def _resolve_bars(log: pd.DataFrame, data: Dataset, side: str) -> np.ndarray:
    """Find the bar behind each leg's ``side`` fill: the log's own index, or one from its time.

    A log that carries bar indices keeps them. Resolving them from the timestamps instead would
    shift every simulated trade one bar forward, because a bar's own stamp is not a fill time.
    """
    bar_column, time_column = f"{side}_bar", f"{side}_time"
    known = (
        log[bar_column].notna().to_numpy(np.bool_)
        if bar_column in log.columns
        else np.zeros(len(log), dtype=np.bool_)
    )
    if len(log) and known.all():
        bars = log[bar_column].to_numpy(np.int64)
        _check_bar_range(bars, data, side)
        if time_column in log.columns:
            _check_bar_times(log[time_column], bars, data, side)
        return bars
    if known.any():
        msg = (
            f"{int(known.sum())} of {len(log)} rows carry a {bar_column} and the rest do not; a "
            f"log must carry one on every row or on none."
        )
        raise AnnotationError(msg)
    if time_column not in log.columns:
        msg = (
            f"this log carries neither {bar_column} nor {time_column}, so there is no way to say "
            f"which bar a leg {side}ed on."
        )
        raise AnnotationError(msg)
    return bars_for_fills(data.index, pd.DatetimeIndex(log[time_column]), bar_minutes=_bar_minutes(data))


def _bar_minutes(data: Dataset) -> int | None:
    """Read the dataset's own bar size where it has one, rather than inferring it again."""
    return None if data.time_of_day is None else data.time_of_day.bar_minutes


def _check_bar_range(bars: np.ndarray, data: Dataset, side: str) -> None:
    """Refuse a bar index the dataset does not hold, rather than wrapping on a negative one."""
    outside = (bars < 0) | (bars >= len(data))
    if outside.any():
        msg = (
            f"{int(outside.sum())} {side} bar index/indices fall outside the dataset's "
            f"0..{len(data) - 1}; this log was not produced over these bars."
        )
        raise AnnotationError(msg)


def _check_bar_times(times: pd.Series, bars: np.ndarray, data: Dataset, side: str) -> None:
    """Cross-check the log's own bar indices against its timestamps.

    The one test that catches a log being annotated against a different series of the same
    shape -- another contract, or the same bars at another resolution.
    """
    stamps = pd.DatetimeIndex(times)
    index = pd.DatetimeIndex(data.index)
    if (stamps.tz is None) != (index.tz is None):
        msg = (
            f"the log's {side}_time is {'naive' if stamps.tz is None else 'tz-aware'} and the "
            f"dataset's index is not; one of the two is not the series it is thought to be."
        )
        raise AnnotationError(msg)
    disagree = _utc_naive(index[bars]) != _utc_naive(stamps)
    if disagree.any():
        first = int(np.flatnonzero(disagree)[0])
        msg = (
            f"row {first}'s {side}_bar {int(bars[first])} is stamped {index[bars[first]]} and its "
            f"{side}_time is {stamps[first]}; this log was produced over different bars."
        )
        raise AnnotationError(msg)


def _check_prices(
    log: pd.DataFrame,
    data: Dataset,
    bars: np.ndarray,
    *,
    side: str,
    tolerance: float,
) -> None:
    """Refuse a fill outside the bar it matched, which is what a back-adjusted series produces."""
    matched = bars != UNMATCHED
    if not matched.any():
        return
    prices = log[f"{side}_price"].to_numpy(np.float64)
    at = bars[matched]
    outside = (prices[matched] > data.high[at] + tolerance) | (prices[matched] < data.low[at] - tolerance)
    if not outside.any():
        return

    row = int(np.flatnonzero(matched)[int(np.flatnonzero(outside)[0])])
    bar = int(bars[row])
    fill = float(prices[row])
    distance = max(fill - float(data.high[bar]), float(data.low[bar]) - fill)
    msg = (
        f"the {side} price {fill} on trade {log['trade_id'].to_numpy()[row]} is {distance:g} points "
        f"outside the bar stamped {data.index[bar]}, which ran {data.low[bar]}..{data.high[bar]}. "
        f"These are not the bars that trade happened on: back-adjustment shifts a continuous "
        f"series by hundreds of points and the lookup still succeeds, so annotate against the raw "
        f"or per-contract bars. A simulated log lands outside by its slippage, which is what "
        f"price_tolerance admits."
    )
    raise AnnotationError(msg)


def _per_trade_bars(
    log: pd.DataFrame,
    legs: dict[str, np.ndarray],
) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]:
    """Collapse leg bars into one entry and one exit bar per trade, and say which trades matched.

    A trade enters on its earliest leg and leaves on its latest. It matches only when every leg
    of it does, at both ends: half a trade annotated and half excluded would misstate the trade
    itself, which is the rule :mod:`nqbt.trade_import` already applies to coverage.
    """
    frame = pd.DataFrame(
        {
            "trade_id": log["trade_id"].to_numpy(np.int64),
            "entry": legs["entry"],
            "exit": legs["exit"],
            "ok": (legs["entry"] != UNMATCHED) & (legs["exit"] != UNMATCHED),
        },
    )
    aggregated = frame.groupby("trade_id", sort=True).agg(
        entry=("entry", "min"),
        exit=("exit", "max"),
        ok=("ok", "all"),
    )
    matched = aggregated["ok"].to_numpy(np.bool_)
    per_trade = {side: np.where(matched, aggregated[side].to_numpy(np.int64), UNMATCHED) for side in _SIDES}
    return aggregated.index.to_numpy(np.int64), per_trade, matched


# -- the conditions -----------------------------------------------------------


def _bar_columns(data: Dataset, bars: np.ndarray, at: np.ndarray, side: str) -> dict[str, Column]:
    """Which bar was matched and what it did: the bookkeeping half of a row."""
    return {
        f"{side}_bar": bars,
        f"{side}_bar_time": data.index[at],
        f"{side}_bar_open": data.open[at],
        f"{side}_bar_high": data.high[at],
        f"{side}_bar_low": data.low[at],
        f"{side}_bar_close": data.close[at],
    }


def _conditions_at(data: Dataset, at: np.ndarray, thresholds: LabelThresholds) -> dict[str, Column]:
    """Every condition the dataset holds, read at the given bars.

    Driven by what was built rather than by what the spec declared, so a dataset prepared with
    ``keep_ma_values=True`` carries its values here without anything having asked twice. Labels
    are cut from the gathered rows rather than from the whole series.
    """
    out: dict[str, Column] = {
        "hammer": data.geometry.hammer[at],
        "inverted_hammer": data.geometry.inverted_hammer[at],
        "made_new_high": data.geometry.made_new_high[at],
        "made_new_low": data.geometry.made_new_low[at],
        "previous_bar_green": data.geometry.previous_bar_green[at],
        "previous_bar_red": data.geometry.previous_bar_red[at],
    }
    if data.time_of_day is not None:
        out["phase"] = _named(data.phase_values()[at], _PHASE_NAMES, OUT_OF_SESSION_LABEL)
        out["bar_of_session"] = data.bar_of_session()[at]
    for kind, grid in sorted(data.mas.items()):
        for period in grid.periods.tolist():
            out[f"above_{kind}_{period}"] = data.ma_gate(kind, period, above=True)[at]
            if grid.values is not None:  # noqa: PD011 - a MovingAverageGrid attribute, not a Series
                out[f"{kind}_{period}"] = data.ma_values(kind, period)[at]
    for period in sorted(data.atrs):
        out[f"atr_{period}"] = data.atr_values(period)[at]
    if data.vwap is not None:
        out["vwap"] = data.vwap_values()[at]
        out["above_vwap"] = data.vwap_gate(above=True)[at]
    if data.regimes is not None:
        out.update(_regime_conditions(data.regimes, at, thresholds))
    if data.volumes is not None:
        out.update(_volume_conditions(data.volumes, at, thresholds))
    if data.trends is not None:
        out.update(_trend_conditions(data.trends, at, thresholds))
    return out


def _regime_conditions(
    grid: regime.EfficiencyRatioGrid,
    at: np.ndarray,
    thresholds: LabelThresholds,
) -> dict[str, Column]:
    """Gather the efficiency ratio at every lookback built, and its label where one is asked for."""
    out: dict[str, Column] = {}
    for lookback in grid.lookbacks.tolist():
        values = grid.values_for(lookback)[at]
        out[f"efficiency_ratio_{lookback}"] = values
        if thresholds.labels_regimes:
            labels = regime.label(
                values,
                float(thresholds.regime_consolidating_below),  # type: ignore[arg-type]  # the property checked
                float(thresholds.regime_directional_above),  # type: ignore[arg-type]  # the property checked
            )
            out[f"regime_{lookback}"] = _named(labels, _REGIME_NAMES, UNDEFINED_LABEL)
    return out


def _volume_conditions(
    grid: volume.VolumeGrid,
    at: np.ndarray,
    thresholds: LabelThresholds,
) -> dict[str, Column]:
    """Gather absolute and relative volume for every series built, and the state where asked."""
    out: dict[str, Column] = {}
    for key in grid.keys:
        suffix = _volume_suffix(key)
        relative = grid.relative_for(key)[at]
        out[f"volume_{suffix}"] = grid.absolute_for(key)[at]
        out[f"relative_volume_{suffix}"] = relative
        if thresholds.labels_volume:
            labels = volume.label(
                relative,
                float(thresholds.volume_thin_below),  # type: ignore[arg-type]  # the property checked
                float(thresholds.volume_heavy_above),  # type: ignore[arg-type]  # the property checked
            )
            out[f"volume_state_{suffix}"] = _named(labels, _VOLUME_NAMES, UNDEFINED_LABEL)
    return out


def _trend_conditions(
    grid: trend.TrendGrid,
    at: np.ndarray,
    thresholds: LabelThresholds,
) -> dict[str, Column]:
    """Gather the agreement score and its three votes for every label built, and the label."""
    out: dict[str, Column] = {}
    for key in grid.keys:
        suffix = _trend_suffix(key)
        agreement = grid.agreement_for(key)[at]
        out[f"trend_agreement_{suffix}"] = agreement
        votes = grid.votes_for(key)
        for component in trend.TrendComponent:
            out[f"trend_{suffix}_{component.name.lower()}"] = votes[int(component)][at]
        if thresholds.labels_trend:
            labels = trend.label(agreement, int(thresholds.trend_min_agreement))  # type: ignore[arg-type]  # checked
            out[f"trend_{suffix}"] = _named(labels, _TREND_NAMES, UNDEFINED_LABEL)
    return out


def _volume_suffix(key: volume.VolumeKey) -> str:
    """Name one relative-volume series, carrying the rolling window only where it has one."""
    form = volume.VolumeForm(key.form)
    window = f"_{key.rolling_bars}" if form is volume.VolumeForm.ROLLING else ""
    return f"{form.name.lower()}{window}_{key.baseline_sessions}"


def _trend_suffix(key: trend.TrendKey) -> str:
    """Name one trend label by the three numbers that determine it."""
    return f"{key.fast_period}_{key.slow_period}_{key.slope_lookback}"


def _named(codes: np.ndarray, names: Sequence[str], undefined: str) -> np.ndarray:
    """Turn label codes into their names, ``-1`` becoming ``undefined``."""
    lookup = np.array([undefined, *names], dtype=object)
    return lookup[np.asarray(codes, dtype=np.int64) + 1]


# -- the frame ----------------------------------------------------------------


def _to_frame(columns: dict[str, Column], trade_ids: np.ndarray, matched: np.ndarray) -> pd.DataFrame:
    """Assemble the annotation, nulling every condition of a trade that did not match.

    Every column is held as the nullable dtype :func:`pandas.array` infers for it, so a null
    cannot masquerade as ``False`` and the dtypes do not depend on whether anything is missing.
    """
    index = pd.Index(trade_ids, name="trade_id", dtype="int64")
    absent = pd.Series(~matched, index=index)
    frame = pd.DataFrame(index=index)
    for name, values in columns.items():
        column = pd.Series(pd.array(values), index=index)
        frame[name] = column if name == "matched" else column.mask(absent)
    return frame
