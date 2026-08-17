"""Diff two folders of NT8 minute exports, contract by contract.

Built to answer one question: does pulling bars through ``BarsRequest`` (the AddOn) return
anything the manual Tools -> Historical Data export does not? Manual exports have been
observed to gain and lose whole sessions between runs, so "different" is expected -- what
matters is *which* direction and *where*.

    ./.venv/Scripts/python.exe tools/compare_exports.py [baseline_dir] [candidate_dir]

Defaults to data/minute (baseline) against data/addon (candidate). Read-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from nqbt import ingest, paths

VALUE_COLUMNS = ["open", "high", "low", "close", "volume"]


def load(path: Path) -> pd.DataFrame:
    """Parse an export with the same code the pipeline uses, so differences are real."""
    return ingest.parse_export(path.read_bytes(), source_name=path.name)


def timezone_offset_hours(baseline: pd.DataFrame, candidate: pd.DataFrame) -> int:
    """Whole-hour shift that best aligns the two, or 0.

    A timezone mistake in the exporter shifts every bar by a whole number of hours and
    errors nowhere -- prices stay plausible, the file parses, and the damage only shows up
    as strategy results that quietly disagree. Worth testing for explicitly.
    """
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
    """Fraction of shared timestamps whose OHLCV agree exactly."""
    common = baseline.index.intersection(candidate.index)
    if not len(common):
        return 0.0
    left = baseline.loc[common, VALUE_COLUMNS]
    right = candidate.loc[common, VALUE_COLUMNS]
    return float((left == right).all(axis=1).mean())


def compare(name: str, baseline: pd.DataFrame, candidate: pd.DataFrame) -> dict:
    shift = timezone_offset_hours(baseline, candidate)
    # A wrong timezone and genuinely different data look alike until you undo the shift:
    # if the bars then agree, the exporter is fine apart from one constant, and the data is
    # worth keeping. If they still disagree, the difference is real.
    corrected = 0.0
    if shift:
        shifted = candidate.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=shift)
        corrected = identical_share(baseline, shifted)

    only_baseline = baseline.index.difference(candidate.index)
    only_candidate = candidate.index.difference(baseline.index)
    common = baseline.index.intersection(candidate.index)

    differing = 0
    if len(common):
        left = baseline.loc[common, VALUE_COLUMNS]
        right = candidate.loc[common, VALUE_COLUMNS]
        differing = int((~((left == right) | (left.isna() & right.isna())).all(axis=1)).sum())

    return {
        "contract": name,
        "baseline": len(baseline),
        "candidate": len(candidate),
        "delta": len(candidate) - len(baseline),
        "only_baseline": len(only_baseline),
        "only_candidate": len(only_candidate),
        "differing": differing,
        "shift_h": shift,
        "shifted_match": round(corrected, 4),
        "_only_baseline_idx": only_baseline,
        "_only_candidate_idx": only_candidate,
    }


def sessions_of(index: pd.DatetimeIndex) -> pd.Series:
    """Bars per trading day for a set of timestamps, for locating whole-session changes."""
    if not len(index):
        return pd.Series(dtype="int64")
    return pd.Series(1, index=index).groupby(index.tz_convert("UTC").date).size()


def main(argv: list[str]) -> int:
    baseline_dir = Path(argv[1]) if len(argv) > 1 else paths.MINUTE_DIR
    candidate_dir = Path(argv[2]) if len(argv) > 2 else paths.DATA_DIR / "addon"

    if not candidate_dir.exists():
        return 1

    rows, details = [], []
    for candidate_path in sorted(candidate_dir.glob("*.Last.txt")):
        name = candidate_path.name.removesuffix(".Last.txt")
        baseline_path = baseline_dir / candidate_path.name
        if not baseline_path.exists():
            continue

        result = compare(name, load(baseline_path), load(candidate_path))
        rows.append({k: v for k, v in result.items() if not k.startswith("_")})
        if result["only_baseline"] or result["only_candidate"]:
            details.append(result)

    if not rows:
        return 1

    table = pd.DataFrame(rows).set_index("contract")

    shifted = table[table["shift_h"] != 0]
    if len(shifted):
        shifted["shifted_match"].mean()
        return 2

    for result in details:
        for _label, idx in (
            ("only in baseline", result["_only_baseline_idx"]),
            ("only in candidate", result["_only_candidate_idx"]),
        ):
            counts = sessions_of(idx)
            if not len(counts):
                continue
            whole = counts[counts > 300]  # a few missing minutes is noise; a session is not
            if len(whole):
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
