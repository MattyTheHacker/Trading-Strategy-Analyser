"""Rolling in-sample / out-of-sample evaluation of a parameter choice.

Answers whether a combination survives being *chosen* on data it did not see. Distinct from
:mod:`nqbt.dispersion`, which asks whether a result holds across contracts: the two are a
finer and a coarser cut of the same question and must be read together rather than as two
independent verdicts.

The split geometry, the boundary approximation and why selection is capped to
:data:`nqbt.stats.TRADE_PNL_STATISTICS`: ``docs/roadmap.md`` §M7b.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import stats, sweep
from nqbt.dispersion import MIN_TRADES
from nqbt.instruments import MNQ

if TYPE_CHECKING:
    from nqbt.archetypes import Params
    from nqbt.arrays import AnyArray, BoolArray, FloatArray
    from nqbt.context import Dataset
    from nqbt.costs import TradingCosts
    from nqbt.instruments import Instrument
    from nqbt.sweep import Grid

__all__ = [
    "Split",
    "WalkForwardError",
    "WalkForwardResult",
    "WalkForwardSummary",
    "splits",
    "walk_forward",
]


class WalkForwardError(RuntimeError):
    """Raised when a walk-forward cannot be assembled or would be uninterpretable."""


@dataclass(frozen=True, slots=True)
class Split:
    """One in-sample / out-of-sample pair, as half-open positions into the bar frame."""

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def train_bars(self) -> int:
        """How many bars the selection sees."""
        return self.train_end - self.train_start

    @property
    def test_bars(self) -> int:
        """How many bars the measurement runs over."""
        return self.test_end - self.test_start


def splits(
    n_bars: int,
    train_bars: int,
    test_bars: int,
    step: int | None = None,
    anchored: bool = False,
) -> list[Split]:
    """Build rolling train/test pairs covering ``n_bars``.

    ``step`` defaults to ``test_bars``, which makes the out-of-sample windows a partition of
    the tested region -- the property that lets their trade logs be concatenated into one
    out-of-sample record. ``anchored`` grows the training window from bar zero instead of
    sliding it.
    """
    if train_bars < 1 or test_bars < 1:
        msg: str = f"train_bars and test_bars must both be >= 1; got {train_bars} and {test_bars}"
        raise WalkForwardError(msg)
    step = test_bars if step is None else step
    if step < 1:
        msg = f"step must be >= 1; got {step}"
        raise WalkForwardError(msg)
    if n_bars < train_bars + test_bars:
        msg = (
            f"need at least train_bars + test_bars = {train_bars + test_bars} bars for one "
            f"split; got {n_bars}"
        )
        raise WalkForwardError(msg)

    out: list[Split] = []
    train_end: int = train_bars
    while train_end + test_bars <= n_bars:
        out.append(
            Split(
                index=len(out),
                train_start=0 if anchored else train_end - train_bars,
                train_end=train_end,
                test_start=train_end,
                test_end=train_end + test_bars,
            ),
        )
        train_end += step
    return out


@dataclass(frozen=True, slots=True)
class WalkForwardSummary:
    """In-sample against out-of-sample, aggregated over the splits that selected."""

    statistic: str
    splits: int
    splits_selected: int
    combos_distinct: int
    """How many different combinations won a training window; 1 means a stable choice."""

    train_median: float
    test_median: float
    test_pooled: float
    """The statistic over every out-of-sample trade at once, not a median of medians."""

    test_trades: int
    splits_test_better: int

    def as_dict(self) -> dict[str, str | float | int]:
        """Flat mapping, for a report row or a CSV."""
        return dataclasses.asdict(self)


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """Per-split selections and their out-of-sample outcome."""

    table: pd.DataFrame
    """One row per split: what was chosen in sample and what it did out of sample."""

    trades: pd.DataFrame
    """Every out-of-sample trade, concatenated in time order, tagged with ``split``."""

    statistic: str
    costs: TradingCosts

    def pooled_pnl(self) -> FloatArray:
        """Per-trade P&L across every out-of-sample window, in split order.

        Grouped per split before the leg collapse, because ``trade_id`` restarts at 1 in each
        window -- collapsing the concatenated log would merge trades that only share a number.
        """
        if self.trades.empty:
            return np.empty(0, dtype=float)
        parts: list[AnyArray] = [
            stats.per_trade(window)["net_pnl"].to_numpy(dtype=float)
            for _, window in self.trades.groupby("split", sort=True)
        ]
        return np.concatenate(parts)

    def summary(self) -> WalkForwardSummary:
        """Aggregate in-sample against out-of-sample, over splits that selected anything."""
        chosen: pd.DataFrame = self.table[self.table["combo_id"].notna()]
        pooled: FloatArray = self.pooled_pnl()
        return WalkForwardSummary(
            statistic=self.statistic,
            splits=len(self.table),
            splits_selected=len(chosen),
            combos_distinct=int(chosen["combo_id"].nunique()),
            train_median=float(chosen["train_statistic"].median()) if len(chosen) else np.nan,
            test_median=float(chosen["test_statistic"].median()) if len(chosen) else np.nan,
            test_pooled=stats.trade_statistic(pooled, self.statistic),
            test_trades=int(pooled.size),
            splits_test_better=int(
                (chosen["test_statistic"] >= chosen["train_statistic"]).sum(),
            ),
        )


def _window_log(
    bars: pd.DataFrame,
    window: tuple[int, int],
    combination: sweep.Grid,
    instrument: Instrument,
    warmup: int,
) -> pd.DataFrame:
    """Run a one-combination grid over ``window``, dropping trades entered in the warm-up."""
    start, end = window
    lead: int = max(0, start - warmup)
    slice_: pd.DataFrame = bars.iloc[lead:end]
    data: Dataset = sweep.prepare_for(slice_, combination)
    _, log = sweep.run_combination(
        data,
        combination.base,
        instrument,
        combination.archetype,
        keep_trades=True,
    )
    if log is None or log.empty:
        return pd.DataFrame() if log is None else log
    # ``entry_bar`` is a position into ``slice_``, which is what the prefix is measured in.
    keep: BoolArray = log["entry_bar"].to_numpy() >= (start - lead)
    return log[keep].reset_index(drop=True)


def _statistic(log: pd.DataFrame, name: str) -> tuple[float, int]:
    """``name`` and the trade count behind it, from a leg-level log."""
    if log.empty:
        return np.nan, 0
    pnl: FloatArray = stats.per_trade(log)["net_pnl"].to_numpy(float)
    return stats.trade_statistic(pnl, name), int(pnl.size)


def walk_forward(  # noqa: PLR0913, PLR0917 - each argument is a distinct axis; a config bag would hide a swap
    bars: pd.DataFrame,
    grid: sweep.Grid,
    costs: TradingCosts,
    train_bars: int,
    test_bars: int,
    instrument: Instrument = MNQ,
    select_by: str = "profit_factor",
    step: int | None = None,
    anchored: bool = False,
    warmup_bars: int = 0,
    min_trades: int = MIN_TRADES,
    n_jobs: int = 1,
) -> WalkForwardResult:
    """Select on each training window, measure on the window that follows, and report both.

    ``costs`` has no default: an uncosted walk-forward selects for trade frequency, which is
    the one thing costs punish, so it would report a clean result that inverts the moment
    costs are applied.

    ``warmup_bars`` prefixes every window so indicators are warm at its first tradeable bar;
    trades entered in the prefix are discarded. A grid reading an SMA(200) needs at least 200.
    """
    if select_by not in stats.TRADE_PNL_STATISTICS:
        msg: str = (
            f"{select_by!r} cannot be selected on: walk-forward compares in-sample against "
            f"out-of-sample using one definition, and lower-is-better statistics would need "
            f"the opposite comparison. Choose from {list(stats.TRADE_PNL_STATISTICS)}."
        )
        raise WalkForwardError(msg)
    if costs.is_free:
        msg = (
            "costs are zero, so this would rank gross results. Pass nqbt.costs.LIVE, or "
            "nqbt.costs.FREE explicitly if an uncosted walk-forward is genuinely wanted."
        )
        raise WalkForwardError(msg)
    if warmup_bars < 0:
        msg = f"warmup_bars must be >= 0; got {warmup_bars}"
        raise WalkForwardError(msg)

    costed: Grid = sweep.Grid(
        axes=dict(grid.axes),
        base=costs.apply(grid.base),
        archetype=grid.archetype,
    )
    combos: list[Params] = list(costed.combinations())
    windows: list[Split] = splits(
        len(bars),
        train_bars=train_bars,
        test_bars=test_bars,
        step=step,
        anchored=anchored,
    )

    rows, logs = [], []
    for split in windows:
        train: pd.DataFrame = bars.iloc[max(0, split.train_start - warmup_bars) : split.train_end]
        table, _ = sweep.sweep(train, costed, instrument, n_jobs=n_jobs)
        viable: pd.DataFrame = table[table["trades"] >= min_trades]
        finite: pd.DataFrame = viable[np.isfinite(viable[select_by].to_numpy(dtype=float))]

        row = {
            "split": split.index,
            "train_start": bars.index[split.train_start],
            "train_end": bars.index[split.train_end - 1],
            "test_start": bars.index[split.test_start],
            "test_end": bars.index[split.test_end - 1],
            "combos_viable": len(finite),
        }
        if finite.empty:
            rows.append(
                {
                    **row,
                    "combo_id": np.nan,
                    "train_statistic": np.nan,
                    "train_trades": 0,
                    "test_statistic": np.nan,
                    "test_trades": 0,
                },
            )
            continue

        best = finite.loc[finite[select_by].idxmax()].to_dict()
        combo_id: int = int(best["combo_id"])
        test_log: pd.DataFrame = _window_log(
            bars,
            (split.test_start, split.test_end),
            sweep.Grid(base=combos[combo_id], archetype=costed.archetype),
            instrument,
            warmup_bars,
        )
        test_stat, test_trades = _statistic(test_log, select_by)
        if not test_log.empty:
            logs.append(test_log.assign(split=split.index))
        rows.append(
            {
                **row,
                "combo_id": combo_id,
                "train_statistic": float(best[select_by]),
                "train_trades": int(best["trades"]),
                "test_statistic": test_stat,
                "test_trades": test_trades,
            },
        )

    return WalkForwardResult(
        table=pd.DataFrame(rows),
        trades=(
            pd.concat(logs, ignore_index=True)
            if logs
            else pd.DataFrame(columns=["trade_id", "net_pnl", "split"])
        ),
        statistic=select_by,
        costs=costs,
    )
