"""Compare ``NqbtHigherTimeframeProbe``'s export against nqbt's higher-timeframe projection.

    uv run tools/reconcile_higher_timeframe.py <..._primary.csv> <contract> [from]

The companion ``_coarse.csv`` is found beside it; ``from`` is an optional ISO date trimming the export.
``tools/README.md`` § "reconcile_higher_timeframe.py".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import higher_timeframe, indicators, ingest, logsetup, resample, sessions
from nqbt.instruments import ContractId

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray, IntArray

logger = logging.getLogger(__name__)

EXPECTED_ARGV = (3, 4)
FIRST_DISAGREEMENTS = 5
"""Disagreeing rows shown inline; the point is to characterise them, not to list them all."""

OHLCV = ("open", "high", "low", "close", "volume")
NO_COARSE_BAR = -1
"""What the probe writes for a primary bar the secondary series has not reached yet."""

PRICE_TOLERANCE = 0.0
"""Bars are exact: aggregation is associative, so a coarse bar is bit-identical either way."""

MA_TOLERANCE = 1e-6
"""Averages are not. The probe writes NinjaTrader's own round-trip through text."""

MIN_COARSE_BARS = 2
"""Fewer coarse bars than this leave no gap to infer a resolution from."""


def read_probe(primary_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load both halves of one probe run, indexed by UTC bar stamp."""
    coarse_path: Path = primary_path.with_name(primary_path.name.replace("_primary.csv", "_coarse.csv"))
    if not coarse_path.exists():
        msg: str = f"no coarse export beside {primary_path.name}; expected {coarse_path.name}"
        raise FileNotFoundError(msg)

    primary: pd.DataFrame = pd.read_csv(primary_path, sep=";", float_precision="round_trip")
    coarse: pd.DataFrame = pd.read_csv(coarse_path, sep=";", float_precision="round_trip")
    for frame in (primary, coarse):
        frame["utc"] = pd.to_datetime(frame["utc"], format="%Y%m%d %H%M%S", utc=True)
    primary["coarse_utc"] = pd.to_datetime(
        primary["coarse_utc"],
        format="%Y%m%d %H%M%S",
        utc=True,
        errors="coerce",
    )

    return primary.set_index("utc"), coarse.set_index("utc")


def report(name: str, *, agreed: bool, detail: str) -> bool:
    """Log one question's verdict, in the form the other reconciliation tools print."""
    logger.info("  %-12s %-9s %s", name, "AGREES" if agreed else "DIFFERS", detail)

    return agreed


def check_anchoring(nt8_coarse: pd.DataFrame, bars: pd.DataFrame, minutes: int) -> bool:
    """Check that NinjaTrader buckets the coarse series where :mod:`nqbt.resample` buckets it."""
    ours: pd.DataFrame = resample.resample(bars, minutes)
    shared: pd.DatetimeIndex = pd.DatetimeIndex(nt8_coarse.index.intersection(ours.index))
    only_nt8: int = len(nt8_coarse.index.difference(ours.index))
    only_ours: int = len(ours.index.difference(nt8_coarse.index))

    if not len(shared):
        return report("anchoring", agreed=False, detail="no coarse stamp is common to both")

    mismatched: dict[str, int] = {}
    for column in OHLCV:
        if column not in nt8_coarse.columns:
            continue

        differs = ~np.isclose(
            nt8_coarse.loc[shared, column].to_numpy(np.float64),
            ours.loc[shared, column].to_numpy(np.float64),
            rtol=0.0,
            atol=PRICE_TOLERANCE,
        )
        if differs.any():
            mismatched[column] = int(differs.sum())

    agreed: bool = not mismatched and not only_nt8 and not only_ours
    detail: str = f"{len(shared):,} shared {minutes}-minute bars"
    if only_nt8 or only_ours:
        detail += f"; {only_nt8:,} only in NT8, {only_ours:,} only in nqbt"

    if mismatched:
        detail += "; " + ", ".join(f"{c} on {n:,}" for c, n in mismatched.items())

    if not agreed:
        detail += settled_from(nt8_coarse, ours, shared)

    return report("anchoring", agreed=agreed, detail=detail)


def settled_from(nt8_coarse: pd.DataFrame, ours: pd.DataFrame, shared: pd.DatetimeIndex) -> str:
    """Find where the two series stop disagreeing, which is usually NT8's merge boundary."""
    differs = nt8_coarse.loc[shared, "close"].to_numpy() != ours.loc[shared, "close"].to_numpy()
    if not differs.any():
        return ""

    last_bad = shared[differs].max()
    after = shared[shared > last_bad]

    return f"; agrees on all {len(after):,} bars after {last_bad}"


def check_seeding(nt8_coarse: pd.DataFrame, primary: pd.DataFrame, periods: dict[str, int]) -> bool:
    """Check that NT8's average over a secondary series matches :func:`nqbt.indicators.nt8_ema`.

    Taken over NT8's *own* coarse closes and read at the bars that close alongside one, so
    an anchoring difference cannot be mistaken for a seeding one.
    """
    closes: FloatArray = nt8_coarse["close"].to_numpy(np.float64)
    functions = {"ema": indicators.nt8_ema, "sma": indicators.nt8_sma}
    agreed: bool = True
    for kind, function in functions.items():
        for label, period in periods.items():
            column: str = f"coarse_{kind}_{label}"
            if column not in primary.columns:
                continue

            ours: pd.Series[float] = pd.Series(function(closes, period), index=nt8_coarse.index)
            theirs: pd.Series[float] = primary[column].reindex(ours.index)
            usable = theirs.notna()
            differs = ~np.isclose(
                ours[usable].to_numpy(np.float64),
                theirs[usable].to_numpy(np.float64),
                rtol=0.0,
                atol=MA_TOLERANCE,
            )
            agreed &= not differs.any()
            report(
                f"{kind}({period})",
                agreed=not differs.any(),
                detail=f"{int(usable.sum()):,} coarse closes compared, {int(differs.sum()):,} differ",
            )

    return agreed


def nqbt_reads(coarse_stamps: pd.DatetimeIndex, stamps: pd.DatetimeIndex) -> pd.Series[pd.Timestamp]:
    """Return which coarse stamp nqbt's projection reads at each fine bar.

    Runs the coarse stamps through :func:`nqbt.higher_timeframe.project` itself. ``dtype=`` is
    not optional on either conversion: ``read_csv`` hands back microsecond stamps, and reading
    those as nanoseconds puts every bar in 1970.
    """
    seconds: IntArray = epoch_seconds(coarse_stamps)
    read: FloatArray = higher_timeframe.project(coarse_stamps, seconds.astype(np.float64), stamps)

    return pd.Series(pd.to_datetime(read, unit="s", utc=True), index=stamps)


def epoch_seconds(stamps: pd.DatetimeIndex) -> IntArray:
    """Convert to UTC seconds since the epoch, whatever resolution the index happens to carry."""
    naive: pd.DatetimeIndex = stamps.tz_convert("UTC").tz_localize(None) if stamps.tz else stamps

    return naive.to_numpy(dtype="datetime64[s]").astype("int64")


def check_projection(primary: pd.DataFrame, nt8_coarse: pd.DataFrame) -> bool:
    """Check which coarse bar each 1-minute bar reads -- the question trades cannot answer."""
    stamps = pd.DatetimeIndex(primary.index)
    ours: pd.Series[pd.Timestamp] = nqbt_reads(pd.DatetimeIndex(nt8_coarse.index), stamps)
    theirs: pd.Series[pd.Timestamp] = primary["coarse_utc"]

    comparable = ours.notna() & theirs.notna()
    differs = comparable & (ours != theirs)
    closing = comparable & stamps.isin(nt8_coarse.index)

    detail: str = (
        f"{int(comparable.sum()):,} bars compared, {int(closing.sum()):,} of them on a coarse "
        f"close; {int(differs.sum()):,} differ"
    )
    agreed: bool = not differs.any()
    if not agreed:
        for stamp in stamps[differs][:FIRST_DISAGREEMENTS]:
            logger.info("      %s: nqbt reads %s, NT8 reads %s", stamp, ours[stamp], theirs[stamp])

    if not closing.any():
        logger.warning(
            "      no bar closes alongside a coarse bar, so this run cannot discriminate "
            "the two candidate rules -- check the coarse resolution divides the primary one",
        )
        agreed = False

    return report("projection", agreed=agreed, detail=detail)


def check_warmup(primary: pd.DataFrame, key: higher_timeframe.HigherTimeframeKey) -> bool:
    """Check how many leading bars NT8 leaves unreadable, against nqbt's UNDEFINED count.

    Measured over the probe's own bars, never the archive's.
    """
    theirs: int = int((primary["coarse_bar"] == NO_COARSE_BAR).sum())
    bars: pd.DataFrame = primary[list(OHLCV)].copy()
    bars["trading_day"] = sessions.classify(pd.DatetimeIndex(bars.index)).trading_day
    grid = higher_timeframe.higher_timeframe_grid(bars, [key], bar_minutes=1)
    ours: int = int((grid.labels_for(key) == higher_timeframe.UNDEFINED).sum())

    return report(
        "warm-up",
        agreed=theirs == ours,
        detail=f"NT8 leaves {theirs:,} leading bars unreadable, nqbt {ours:,}",
    )


def reconcile(primary_path: Path, contract: str, start: str | None) -> bool:
    """Run all four checks over one probe export, and report each separately."""
    primary, nt8_coarse = read_probe(primary_path)
    bars: pd.DataFrame = ingest.load_contract(ContractId.parse(contract))
    if start is not None:
        bars = bars[bars.index >= start]
        primary = primary[primary.index >= start]
        nt8_coarse = nt8_coarse[nt8_coarse.index >= start]

    # Clip to the probe's own span: an archive that runs past where the export stopped is not
    # a disagreement, and its trailing coarse bar would be reported as one.
    bars = bars[(bars.index >= primary.index[0]) & (bars.index <= primary.index[-1])]
    nt8_coarse = nt8_coarse[nt8_coarse.index <= primary.index[-1]]
    bars = bars[bars.index.isin(primary.index)]
    minutes: int = infer_coarse_minutes(pd.DatetimeIndex(nt8_coarse.index))
    periods: dict[str, int] = infer_periods(primary, nt8_coarse)

    logger.info(
        "%s: %s probe bars, %s NT8 coarse bars at %d minutes",
        contract,
        f"{len(primary):,}",
        f"{len(nt8_coarse):,}",
        minutes,
    )
    logger.info("  periods read from the export: %s", periods or "none recovered")
    if not periods:
        logger.warning(
            "      no period reproduces the export's averages, so seeding is NOT checked. "
            "Expected on a trimmed window: NT8's average carries history from before the "
            "trim and ours cannot. Re-run seeding untrimmed -- it needs no archive.",
        )

    results: list[bool] = [
        check_anchoring(nt8_coarse, bars, minutes),
        check_seeding(nt8_coarse, primary, periods),
        check_projection(primary, nt8_coarse),
    ]
    if periods:
        results.append(check_warmup(primary, higher_timeframe.key(minutes, max(periods.values()))))

    agreed: bool = all(results)
    logger.info("")
    logger.info("%s", "RECONCILED" if agreed else "DIFFERENCES FOUND -- see above")

    return agreed


def infer_coarse_minutes(coarse_stamps: pd.DatetimeIndex) -> int:
    """Infer the coarse resolution, as the most common gap between consecutive coarse stamps."""
    if coarse_stamps.size < MIN_COARSE_BARS:
        msg: str = "the coarse export holds fewer than two bars; nothing to infer a resolution from"
        raise ValueError(msg)

    gaps = np.diff(epoch_seconds(coarse_stamps)) // 60
    values, counts = np.unique(gaps[gaps > 0], return_counts=True)

    return int(values[counts.argmax()])


def infer_periods(primary: pd.DataFrame, nt8_coarse: pd.DataFrame) -> dict[str, int]:
    """Recover the periods the probe was run with, by matching its EMA column to a search.

    The probe writes ``short``/``long`` rather than the numbers, so they are read back off the
    data. An EMA is determined by its period, so the match is unambiguous.
    """
    closes: FloatArray = nt8_coarse["close"].to_numpy(np.float64)
    found: dict[str, int] = {}
    for label in ("short", "long"):
        column: str = f"coarse_ema_{label}"
        if column not in primary.columns:
            continue

        theirs: pd.Series[float] = primary[column].reindex(nt8_coarse.index)
        usable = theirs.notna()
        if not usable.any():
            continue

        for period in range(1, 401):
            ours = indicators.nt8_ema(closes, period)
            if np.allclose(
                ours[usable.to_numpy()], theirs[usable].to_numpy(np.float64), rtol=0, atol=MA_TOLERANCE
            ):
                found[label] = period
                break

    return found


def main(argv: list[str]) -> int:
    """Reconcile the probe's export against nqbt and return the process exit code."""
    logsetup.configure(__name__)
    if len(argv) not in EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    start: str | None = argv[3] if len(argv) == max(EXPECTED_ARGV) else None

    return 0 if reconcile(Path(argv[1]), argv[2], start) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
