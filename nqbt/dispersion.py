"""Per-contract sweeps, framed as dispersion rather than selection.

`sweep.sweep` already takes a bars frame, so running one contract has always been possible.
What was missing is the cross-contract table and -- the part that actually matters -- **the
framing that stops it being misread**.

## Why the maximum is the wrong output

Each contract is front-month for roughly three months, so *"which contract is this strategy
best on"* is very nearly *"which quarter of history was it best in"*. Taking the best of 19
contracts x N combinations is the multiple-comparisons trap: a good-looking maximum is the
*expected* output of noise, not evidence against it.

So :func:`dispersion` reports the spread and is deliberately **not** sorted by performance,
and :func:`spread_vs_resampling` exists to give that spread a scale. A spread with no null
to compare against is a number, not a finding.

## Three things this does that slicing the continuous series by date does not

1. **It is a data-integrity instrument.** An outlier contract is far more often a bad roll
   date, a hole or a bad splice than a market insight. Given how much of the archive work
   came from exactly such defects, this is a cheap standing check.
2. **It uses raw prices, never back-adjusted ones.** Back-adjustment shifts historical
   levels by hundreds of points, so any rule sensitive to the absolute level -- round-number
   stop avoidance -- can only be tested per contract.
3. **It is directly Tier-2 reproducible.** A single-contract run contains no roll, so
   Strategy Analyzer can reproduce it bar for bar. That makes it the cheapest route to the
   outstanding NQ reconciliation (#66).

## What this is not

A contract is a ~3-month bucket, so this surfaces **regime shifts, not events**. An election
or a CPI print is a day or an hour, and averaging it across a quarter dilutes it to nothing.
For events the tools are the regime and time-of-day labels (#40, #43) plus a date filter.

The per-contract loop here is intentionally thin -- it builds frames and calls
:func:`nqbt.sweep.sweep`. #28 folds contract into one `sweep_axes` mechanism alongside
strategy and resolution, and should absorb that loop while keeping the statistics below,
which are what this module is really for.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nqbt import ingest, paths, sessions, splice, sweep
from nqbt.instruments import MNQ, ContractId, Instrument

MIN_TRADES = 30
"""Below this a per-contract statistic is reported but excluded from dispersion.

A profit factor from a handful of trades is noise, and noise has the widest spread -- so
including small contracts does not merely add uncertainty, it dominates the very quantity
this module exists to measure.
"""


class DispersionError(RuntimeError):
    """Raised when a per-contract sweep cannot be assembled."""


def front_month_windows(
    root: str, *, back_adjust: bool = True, cache_dir: Path = paths.CACHE_DIR
) -> pd.DataFrame:
    """Each contract's front-month window, read off the continuous series.

    The continuous series already carries a ``contract`` column recording which contract
    supplied every bar, so the windows are whatever the splicer decided rather than a second
    opinion about where the rolls are. Two things follow: the windows are non-overlapping and
    sum to the continuous series, and a change to roll detection moves them automatically.

    ``back_adjust`` only selects which cached series to read the *labels* from -- prices here
    are never used, and the bars are reloaded raw. Its default matches the series most likely
    to be on disk.
    """
    series = splice.load_continuous(root, back_adjust=back_adjust, cache_dir=cache_dir)
    grouped = series.groupby("contract", observed=True)
    windows = pd.DataFrame(
        {
            "start": grouped.apply(lambda d: d.index.min()),
            "end": grouped.apply(lambda d: d.index.max()),
            "continuous_bars": grouped.size(),
        }
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

    **Raw, never back-adjusted** -- see the module docstring. The frames come from the
    per-contract cache, which is what NT8 exported, so a run over one of them is directly
    reproducible in Strategy Analyzer.

    ``full_life=True`` returns each contract's entire cached history instead. That is
    occasionally what you want, but adjacent contracts then overlap by months, so the same
    calendar days appear in two rows and anything aggregated across contracts double-counts
    them. The default is the non-overlapping window for that reason.
    """
    windows = front_month_windows(root, back_adjust=back_adjust, cache_dir=cache_dir)
    frames: dict[str, pd.DataFrame] = {}
    for name, window in windows.iterrows():
        bars = ingest.load_contract(ContractId.parse(name), cache_dir)
        if not full_life:
            bars = bars[(bars.index >= window.start) & (bars.index <= window.end)]
        if len(bars):
            frames[name] = bars
    if not frames:
        raise DispersionError(f"no cached per-contract bars for {root}")
    return frames


def coverage(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Bars and sessions per contract.

    Reported alongside every performance figure, and not optionally: the first contract of a
    root carries its whole pre-roll listing history and the newest is always partial, so a
    profit factor from 30 trades would otherwise sit unlabelled beside one from 400.
    """
    rows = []
    for name, bars in frames.items():
        info = sessions.classify(bars.index)
        rows.append(
            {
                "contract": name,
                "bars": len(bars),
                "in_session_bars": int(info.in_session.sum()),
                "sessions": int(pd.unique(info.trading_day[info.in_session]).size),
                "start": bars.index.min(),
                "end": bars.index.max(),
            }
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
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[str, int], pd.DataFrame]]:
    """Run ``grid`` over every contract of ``root`` separately.

    Returns ``(results, coverage_table, logs)``. ``results`` is one row per
    ``(contract, combo_id)`` with the contract's bar and session counts joined on, so no row
    can be read without its sample size. ``logs`` is empty unless ``keep_trades``, which
    :func:`spread_vs_resampling` needs.

    This deliberately returns a table rather than a ranking. Use :func:`dispersion`.
    """
    frames = contract_frames(
        root, full_life=full_life, back_adjust=back_adjust, cache_dir=cache_dir
    )
    cover = coverage(frames)

    per_contract: list[pd.DataFrame] = []
    logs: dict[tuple[str, int], pd.DataFrame] = {}
    for name, bars in frames.items():
        table, contract_logs = sweep.sweep(
            bars, grid, instrument, keep_trades=keep_trades, n_jobs=n_jobs
        )
        if table.empty:
            continue
        table.insert(0, "contract", name)
        per_contract.append(table)
        for combo_id, log in contract_logs.items():
            logs[(name, combo_id)] = log

    if not per_contract:
        raise DispersionError(f"no contract of {root} produced any result")

    results = pd.concat(per_contract, ignore_index=True)
    return results.merge(cover.drop(columns=["start", "end"]), on="contract"), cover, logs


def dispersion(
    results: pd.DataFrame, by: str = "profit_factor", *, min_trades: int = MIN_TRADES
) -> pd.DataFrame:
    """How much ``by`` varies across contracts, per combination.

    **Not sorted by performance, on purpose.** Rows come back in ``combo_id`` order, because
    sorting by the median would hand back the leaderboard this module exists to refuse. If
    you want the best row you have to reach for it deliberately, and then you own the
    multiple-comparisons problem that comes with it.

    ``contracts_dropped`` is as informative as the spread. A combination that clears
    ``min_trades`` on three of nineteen contracts has not been measured across contracts at
    all, whatever its median says.
    """
    if by not in results.columns:
        raise DispersionError(f"no column {by!r} in results; have {sorted(results.columns)}")

    rows = []
    for combo_id, group in results.groupby("combo_id", sort=True):
        viable = group[group["trades"] >= min_trades]
        values = viable[by].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
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
                    float(np.subtract(*np.percentile(finite, [75, 25])))
                    if finite.size
                    else np.nan
                ),
                f"{by}_range": float(finite.max() - finite.min()) if finite.size else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _iqr(values: np.ndarray) -> float:
    return float(np.subtract(*np.percentile(values, [75, 25])))


def _range(values: np.ndarray) -> float:
    return float(values.max() - values.min())


SPREAD_MEASURES = {"iqr": _iqr, "range": _range}
"""Both are reported, because this module has two jobs and they disagree.

``iqr`` answers *"how much does the bulk of contracts differ?"* and is robust -- on 19
contracts a max-minus-min is decided by the two smallest samples.

``range`` answers *"is any single contract extreme?"*, which is the **data-integrity**
question: an outlier contract is far more often a bad roll date or a hole than a market
insight. The IQR is blind to exactly that by construction, so reporting only the robust
measure would discard the signal this module is most useful for.
"""


def spread_vs_resampling(
    logs: dict[str, pd.DataFrame],
    by: str = "profit_factor",
    *,
    iterations: int = 1000,
    seed: int = 0,
    min_trades: int = MIN_TRADES,
) -> dict:
    """Does the between-contract spread exceed what relabelling the same trades produces?

    A permutation test, not a bootstrap: contract labels are shuffled over the **same** set
    of trades, keeping every group's trade count exactly as observed. That answers the only
    question the raw spread poses -- *"if which contract a trade happened in were arbitrary,
    would the contracts still look this different?"* -- and it is the difference between the
    spread being a number and being a finding.

    Trades are permuted **whole**: each contract's legs are collapsed by
    :func:`nqbt.stats.per_trade` first, so a trade's legs cannot be split across two groups
    and invent trades that never happened.

    Both spread measures in :data:`SPREAD_MEASURES` are reported, and they answer different
    questions -- read the one matching what you are asking. A rogue contract moves ``range``
    and leaves ``iqr`` almost untouched, which is the robustness working, not a bug.

    ``by`` is restricted to :data:`nqbt.stats.TRADE_PNL_STATISTICS`. Permuting destroys entry
    and exit times, so a time-dependent statistic -- Sharpe, max drawdown, consecutive losses
    -- would be computed over an ordering that never happened. Refusing is better than
    returning it.

    **Read a small ``p_value`` as "not obviously noise", never as evidence of a real
    per-contract effect.** Permutation destroys serial correlation and within-contract regime
    persistence, so the null it builds has *less* spread than reality and the test therefore
    **over-rejects**. It is a floor on scepticism, not a verdict. The stronger version --
    block resampling that keeps runs intact -- shares machinery with #50 and belongs there.
    """
    from nqbt import stats

    if by not in stats.TRADE_PNL_STATISTICS:
        raise DispersionError(
            f"{by!r} is not permutable: shuffling trades between contracts destroys the "
            f"ordering it depends on. Choose from {list(stats.TRADE_PNL_STATISTICS)}."
        )

    grouped = {c: stats.per_trade(log)["net_pnl"].to_numpy(float) for c, log in logs.items()}
    usable = {c: pnl for c, pnl in grouped.items() if pnl.size >= min_trades}
    if len(usable) < 2:
        raise DispersionError(
            f"need at least 2 contracts with >= {min_trades} trades; got {len(usable)}"
        )

    observed_stats = {c: stats.trade_statistic(pnl, by) for c, pnl in usable.items()}
    observed_values = np.fromiter(observed_stats.values(), dtype=float, count=len(usable))
    if not np.isfinite(observed_values).all():
        raise DispersionError(
            f"{by} is not finite on every contract, so no spread can be measured. A "
            "contract with no losing trade reports an infinite profit factor."
        )

    pooled = np.concatenate(list(usable.values()))
    # Cut points, so every permutation reproduces the observed group sizes exactly. Without
    # that the null would mix a spread effect with a sample-size effect.
    bounds = np.cumsum([pnl.size for pnl in usable.values()])[:-1]

    rng = np.random.default_rng(seed)
    null = np.empty((iterations, len(SPREAD_MEASURES)), dtype=float)
    for i in range(iterations):
        shuffled = rng.permutation(pooled)
        values = np.fromiter(
            (stats.trade_statistic(part, by) for part in np.split(shuffled, bounds)),
            dtype=float,
            count=len(usable),
        )
        null[i] = [measure(values) for measure in SPREAD_MEASURES.values()]

    spread = {}
    for column, (name, measure) in enumerate(SPREAD_MEASURES.items()):
        observed = measure(observed_values)
        draws = null[:, column]
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
