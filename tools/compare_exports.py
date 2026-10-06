"""Diff two folders of NT8 minute exports, contract by contract.

    uv run tools/compare_exports.py [baseline_dir] [candidate_dir]

Defaults to data/minute (baseline) against data/addon (candidate). Read-only.
``tools/README.md`` § "compare_exports.py".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from nqbt import ingest, logsetup, paths

logger = logging.getLogger(__name__)

VALUE_COLUMNS = ["open", "high", "low", "close", "volume"]

WHOLE_SESSION_BARS = 300
"""Bars in a day above which a difference is a whole session, not a few missing minutes."""

SOUND_AFTER_SHIFT = 0.95
"""Agreement once a timezone shift is undone, above which only the zone was wrong."""


def load(path: Path) -> pd.DataFrame:
    """Parse an export with the same code the pipeline uses, so differences are real."""
    return ingest.parse_export(path.read_bytes(), source_name=path.name)


def timezone_offset_hours(baseline: pd.DataFrame, candidate: pd.DataFrame) -> int:
    """Find the whole-hour shift that best aligns the two, or 0."""
    best_offset, best_overlap = 0, len(baseline.index.intersection(candidate.index))
    for hours in range(-12, 13):
        if hours == 0:
            continue

        shifted = candidate.index + pd.Timedelta(hours=hours)
        overlap = len(baseline.index.intersection(shifted))
        if overlap > best_overlap:
            best_offset, best_overlap = hours, overlap

    return best_offset


def identical_share(baseline: pd.DataFrame, candidate: pd.DataFrame) -> float:
    """Return the fraction of shared timestamps whose OHLCV agree exactly."""
    common = baseline.index.intersection(candidate.index)
    if not len(common):
        return 0.0

    left = baseline.loc[common, VALUE_COLUMNS]
    right = candidate.loc[common, VALUE_COLUMNS]

    return float((left == right).all(axis=1).mean())


class ContractDiff(NamedTuple):
    """How one contract's candidate export differs from its baseline."""

    row: dict[str, int | float | str]
    only_baseline: pd.DatetimeIndex
    only_candidate: pd.DatetimeIndex


def compare(name: str, baseline: pd.DataFrame, candidate: pd.DataFrame) -> ContractDiff:
    """Return the counts that differ between two exports of one contract, and the bars each lacks."""
    shift: int = timezone_offset_hours(baseline, candidate)
    # A wrong timezone and genuinely different data look alike until you undo the shift:
    # if the bars then agree, the exporter is fine apart from one constant, and the data is
    # worth keeping. If they still disagree, the difference is real.
    corrected: float = 0.0
    if shift:
        shifted: pd.DataFrame = candidate.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=shift)
        corrected = identical_share(baseline, shifted)

    only_baseline: pd.DatetimeIndex = pd.DatetimeIndex(baseline.index.difference(candidate.index))
    only_candidate: pd.DatetimeIndex = pd.DatetimeIndex(candidate.index.difference(baseline.index))
    common = baseline.index.intersection(candidate.index)

    differing: int = 0
    if len(common):
        left: pd.DataFrame = baseline.loc[common, VALUE_COLUMNS]
        right: pd.DataFrame = candidate.loc[common, VALUE_COLUMNS]
        differing = int((~((left == right) | (left.isna() & right.isna())).all(axis=1)).sum())

    row: dict[str, int | float | str] = {
        "contract": name,
        "baseline": len(baseline),
        "candidate": len(candidate),
        "delta": len(candidate) - len(baseline),
        "only_baseline": len(only_baseline),
        "only_candidate": len(only_candidate),
        "differing": differing,
        "shift_h": shift,
        "shifted_match": round(corrected, 4),
    }

    return ContractDiff(row, only_baseline, only_candidate)


def sessions_of(index: pd.DatetimeIndex) -> pd.Series[int]:
    """Count bars per trading day for a set of timestamps, for locating whole-session changes."""
    if not len(index):
        return pd.Series(dtype="int64")

    return pd.Series(1, index=index).groupby(index.tz_convert("UTC").date).size()


def report_shift(table: pd.DataFrame) -> bool:
    """Log the contracts that align better at a non-zero hour shift, and return whether there are any."""
    shifted: pd.DataFrame = table[table["shift_h"] != 0]
    if not len(shifted):
        return False

    agreement: float = float(shifted["shifted_match"].mean())
    verdict: str = (
        "Only the timezone is wrong -- the data itself is sound."
        if agreement > SOUND_AFTER_SHIFT
        else "The data differs beyond the shift; investigate before trusting it."
    )
    logger.info("")
    logger.info("*** %d contract(s) align better at a non-zero hour shift.", len(shifted))
    logger.info("*** The exporter's timezone conversion is wrong; do not ingest this folder.")
    logger.info("%s", shifted[["shift_h", "shifted_match"]].to_string())
    logger.info("")
    logger.info("*** Once the shift is undone the bars agree on %s of shared timestamps.", f"{agreement:.1%}")
    logger.info("*** %s", verdict)

    return True


def report_totals(table: pd.DataFrame) -> None:
    """Log the bar totals and how many contracts differ in each way."""
    logger.info("")
    logger.info(
        "totals: baseline %s  candidate %s  net %s",
        f"{table['baseline'].sum():,}",
        f"{table['candidate'].sum():,}",
        f"{table['delta'].sum():+,}",
    )
    logger.info(
        "contracts where the candidate has bars the baseline lacks: %d",
        int((table["only_candidate"] > 0).sum()),
    )
    logger.info(
        "contracts where the baseline has bars the candidate lacks: %d",
        int((table["only_baseline"] > 0).sum()),
    )
    logger.info(
        "contracts with differing values on shared timestamps: %d", int((table["differing"] > 0).sum())
    )


def report_details(details: list[ContractDiff]) -> None:
    """Log, per contract with missing bars, how many days they span and which are whole sessions."""
    for diff in details:
        logger.info("")
        logger.info("--- %s ---", diff.row["contract"])
        for label, idx in (
            ("only in baseline", diff.only_baseline),
            ("only in candidate", diff.only_candidate),
        ):
            counts: pd.Series[int] = sessions_of(idx)
            if not len(counts):
                continue

            whole: pd.Series[int] = counts[counts > WHOLE_SESSION_BARS]
            logger.info("  %s: %s bars across %d day(s)", label, f"{len(idx):,}", len(counts))
            if len(whole):
                logger.info(
                    "    substantial days: %s",
                    ", ".join(f"{d} ({n:,})" for d, n in whole.items()),
                )


def main(argv: list[str]) -> int:
    """Compare the two export folders and return the process exit code."""
    logsetup.configure(__name__)
    folders: list[str] = argv[1:]
    baseline_dir: Path = Path(folders[0]) if folders else paths.MINUTE_DIR
    candidate_dir: Path = Path(folders[1]) if len(folders) > 1 else paths.DATA_DIR / "addon"

    if not candidate_dir.exists():
        logger.info("candidate folder does not exist: %s", candidate_dir)
        logger.info("Run Tools -> 'Export historical bars (nqbt)' in NinjaTrader first.")
        return 1

    rows: list[dict[str, int | float | str]] = []
    details: list[ContractDiff] = []
    for candidate_path in sorted(candidate_dir.glob("*.Last.txt")):
        name: str = candidate_path.name.removesuffix(".Last.txt")
        baseline_path: Path = baseline_dir / candidate_path.name
        if not baseline_path.exists():
            logger.info("%s: only in candidate, no baseline to compare", name)
            continue

        diff: ContractDiff = compare(name, load(baseline_path), load(candidate_path))
        rows.append(diff.row)
        if len(diff.only_baseline) or len(diff.only_candidate):
            details.append(diff)

    if not rows:
        logger.info("nothing to compare")
        return 1

    table: pd.DataFrame = pd.DataFrame(rows).set_index("contract")
    logger.info("%s", table.to_string())
    if report_shift(table):
        return 2

    report_totals(table)
    report_details(details)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
