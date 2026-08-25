"""Per-contract sweeps, framed as dispersion rather than selection.

Reports how much a statistic varies across contracts and whether that variation exceeds what
relabelling the same trades produces. **Report the spread, not the winner**: a contract is
roughly a quarter of history, so a maximum over contracts x combinations is the
multiple-comparisons trap. Bars are raw rather than back-adjusted, which is what makes a
single-contract run directly reproducible in Strategy Analyzer.

Framing, the permutation test's limits and the first result: ``docs/roadmap.md`` §M14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import ingest, paths, sessions, splice, stats, sweep
from nqbt.instruments import MNQ, ContractId, Instrument

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.arrays import FloatArray, IntArray
    from nqbt.sessions import SessionInfo

MIN_CONTRACTS = 2
"""Fewest contracts a spread can be measured across."""

MIN_TRADES = 30
"""Below this a per-contract statistic is reported but excluded from dispersion.

Noise has the widest spread -- ``docs/roadmap.md`` §M14.
"""


class DispersionError(RuntimeError):
    """Raised when a per-contract sweep cannot be assembled."""


def front_month_windows(
    root: str,
    *,
    back_adjust: bool = True,
    cache_dir: Path = paths.CACHE_DIR,
) -> pd.DataFrame:
    """Each contract's front-month window, read off the continuous series' ``contract`` column.

    The windows are therefore the splicer's decisions rather than a second opinion about where
    the rolls are: non-overlapping, summing to the continuous series, and moving automatically
    when roll detection does.

    ``back_adjust`` selects which cached series to read the *labels* from; prices are never
    used here and the bars are reloaded raw.
    """
    series: pd.DataFrame = splice.load_continuous(root, back_adjust=back_adjust, cache_dir=cache_dir)
    grouped = series.groupby("contract", observed=True)
    windows: pd.DataFrame = pd.DataFrame(
        {
            "start": grouped.apply(lambda d: d.index.min()),
            "end": grouped.apply(lambda d: d.index.max()),
            "continuous_bars": grouped.size(),
        },
    )
    windows.index.name = "contract"
    return windows.sort_values("start")


def contract_frames(
    root: str,
    *,
    full_life: bool = False,
    back_adjust: bool = True,
    cache_dir: Path = paths.CACHE_DIR,
) -> dict[str, pd.DataFrame]:
    """Raw bars per contract, sliced to the front-month window by default.

    ``full_life=True`` returns each contract's entire cached history instead, in which case
    adjacent contracts overlap by months and anything aggregated across them double-counts
    calendar days.
    """
    windows: pd.DataFrame = front_month_windows(root, back_adjust=back_adjust, cache_dir=cache_dir)
    frames: dict[str, pd.DataFrame] = {}
    for name, window in windows.iterrows():
        bars: pd.DataFrame = ingest.load_contract(ContractId.parse(str(name)), cache_dir)
        if not full_life:
            bars = bars[(bars.index >= window.start) & (bars.index <= window.end)]
        if len(bars):
            frames[str(name)] = bars
    if not frames:
        msg: str = f"no cached per-contract bars for {root}"
        raise DispersionError(msg)
    return frames


def coverage(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Bars and sessions per contract, joined onto every performance figure.

    Not optional: the first contract of a root carries its whole pre-roll listing history and
    the newest is always partial, so a profit factor from 30 trades would otherwise sit
    unlabelled beside one from 400.
    """
    rows: list[dict[str, object]] = []
    for name, bars in frames.items():
        info: SessionInfo = sessions.classify(pd.DatetimeIndex(bars.index))
        rows.append(
            {
                "contract": name,
                "bars": len(bars),
                "in_session_bars": int(info.in_session.sum()),
                "sessions": int(pd.unique(info.trading_day[info.in_session]).size),
                "start": bars.index.min(),
                "end": bars.index.max(),
            },
        )
    return pd.DataFrame(rows).sort_values("start").reset_index(drop=True)


def sweep_contracts(
    root: str,
    grid: sweep.Grid,
    instrument: Instrument = MNQ,
    *,
    full_life: bool = False,
    back_adjust: bool = True,
    cache_dir: Path = paths.CACHE_DIR,
    keep_trades: bool = False,
    n_jobs: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[str | None, int], pd.DataFrame]]:
    """Run ``grid`` over every contract of ``root`` separately, via :func:`sweep.sweep_axes`.

    Returns ``(results, coverage_table, logs)``. ``results`` is one row per
    ``(contract, combo_id)`` with the contract's bar and session counts joined on, so no row
    can be read without its sample size. ``logs`` is empty unless ``keep_trades``, which
    :func:`spread_vs_resampling` needs.

    A table, not a ranking -- use :func:`dispersion`.
    """
    frames: dict[str, pd.DataFrame] = contract_frames(
        root, full_life=full_life, back_adjust=back_adjust, cache_dir=cache_dir
    )
    cover: pd.DataFrame = coverage(frames)

    # No empty-table guard: a sweep always returns one row per combination, and
    # ``contract_frames`` has already refused an empty set of contracts.
    results, axis_logs = sweep.sweep_axes(frames, grid, instrument, keep_trades=keep_trades, n_jobs=n_jobs)
    contract_column: pd.Series[str] = results.pop("contract")
    results.insert(0, "contract", contract_column)
    logs = {(point.contract, combo_id): log for (point, combo_id), log in axis_logs.items()}

    return results.merge(cover.drop(columns=["start", "end"]), on="contract"), cover, logs


def dispersion(
    results: pd.DataFrame,
    by: str = "profit_factor",
    *,
    min_trades: int = MIN_TRADES,
) -> pd.DataFrame:
    """How much ``by`` varies across contracts, per combination.

    **Rows come back in ``combo_id`` order, never sorted by performance** -- ``docs/roadmap.md``
    §M14. Read ``contracts_dropped`` beside the spread.
    """
    if by not in results.columns:
        msg: str = f"no column {by!r} in results; have {sorted(results.columns)}"
        raise DispersionError(msg)

    rows: list[dict[str, object]] = []
    for combo_id, group in results.groupby("combo_id", sort=True):
        viable: pd.DataFrame = group[group["trades"] >= min_trades]
        values: FloatArray = viable[by].to_numpy(dtype=float)
        finite: FloatArray = values[np.isfinite(values)]
        rows.append(
            {
                "combo_id": combo_id,
                "contracts": len(group),
                "contracts_used": len(finite),
                "contracts_dropped": len(group) - len(finite),
                "trades_total": int(group["trades"].sum()),
                f"{by}_median": np.median(finite) if finite.size else np.nan,
                f"{by}_min": finite.min() if finite.size else np.nan,
                f"{by}_max": finite.max() if finite.size else np.nan,
                f"{by}_iqr": (
                    float(np.subtract(*np.percentile(finite, [75, 25]))) if finite.size else np.nan
                ),
                f"{by}_range": float(finite.max() - finite.min()) if finite.size else np.nan,
            },
        )
    return pd.DataFrame(rows)


def _iqr(values: FloatArray) -> float:
    return float(np.subtract(*np.percentile(values, [75, 25])))


def _range(values: FloatArray) -> float:
    return float(values.max() - values.min())


SPREAD_MEASURES = {"iqr": _iqr, "range": _range}
"""Both are reported, because they answer different questions.

``iqr`` is robust and asks whether the bulk of contracts differ; ``range`` asks whether any one
contract is extreme, which is the data-integrity question the IQR is blind to by construction.
"""


def spread_vs_resampling(
    logs: dict[str, pd.DataFrame],
    by: str = "profit_factor",
    *,
    iterations: int = 1000,
    seed: int = 0,
    min_trades: int = MIN_TRADES,
) -> dict[str, object]:
    """Does the between-contract spread exceed what relabelling the same trades produces?

    A permutation test over whole trades, restricted to
    :data:`nqbt.stats.TRADE_PNL_STATISTICS`. Both measures in :data:`SPREAD_MEASURES` are
    reported.

    **Read a small ``p_value`` as "not obviously noise", never as evidence of a real
    per-contract effect** -- the test over-rejects by construction. That and the rest of its
    limits: ``docs/roadmap.md`` §M14.
    """
    if by not in stats.TRADE_PNL_STATISTICS:
        msg: str = (
            f"{by!r} is not permutable: shuffling trades between contracts destroys the "
            f"ordering it depends on. Choose from {list(stats.TRADE_PNL_STATISTICS)}."
        )
        raise DispersionError(
            msg,
        )

    grouped: dict[str, FloatArray] = {
        c: stats.per_trade(log)["net_pnl"].to_numpy(float) for c, log in logs.items()
    }
    usable: dict[str, FloatArray] = {c: pnl for c, pnl in grouped.items() if pnl.size >= min_trades}
    if len(usable) < MIN_CONTRACTS:
        msg = f"need at least {MIN_CONTRACTS} contracts with >= {min_trades} trades; got {len(usable)}"
        raise DispersionError(msg)

    observed_stats: dict[str, float] = {c: stats.trade_statistic(pnl, by) for c, pnl in usable.items()}
    observed_values: FloatArray = np.fromiter(observed_stats.values(), dtype=float, count=len(usable))
    if not np.isfinite(observed_values).all():
        msg = (
            f"{by} is not finite on every contract, so no spread can be measured. A "
            "contract with no losing trade reports an infinite profit factor."
        )
        raise DispersionError(
            msg,
        )

    pooled: FloatArray = np.concatenate(list(usable.values()))
    # Cut points, so every permutation reproduces the observed group sizes exactly.
    bounds: IntArray = np.cumsum([pnl.size for pnl in usable.values()])[:-1]

    rng: np.random.Generator = np.random.default_rng(seed)
    null: FloatArray = np.empty((iterations, len(SPREAD_MEASURES)), dtype=float)
    for i in range(iterations):
        shuffled: FloatArray = rng.permutation(pooled)
        values: FloatArray = np.fromiter(
            (stats.trade_statistic(part, by) for part in np.split(shuffled, bounds)),
            dtype=float,
            count=len(usable),
        )
        null[i] = [measure(values) for measure in SPREAD_MEASURES.values()]

    spread: dict[str, dict[str, float]] = {}
    for column, (name, measure) in enumerate(SPREAD_MEASURES.items()):
        observed: float = measure(observed_values)
        draws: FloatArray = null[:, column]
        spread[name] = {
            "observed": observed,
            "null_median": float(np.median(draws)),
            "null_p95": float(np.percentile(draws, 95)),
            "p_value": float((draws >= observed).mean()),
        }

    return {
        "statistic": by,
        "spread": spread,
        "iterations": iterations,
        "contracts": len(usable),
        "trades": int(pooled.size),
        "per_contract": observed_stats,
    }
