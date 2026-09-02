"""Compare two captures from ``capture_trade_logs.py``.

    ./.venv/Scripts/python.exe tools/compare_trade_logs.py before after [--added col ...]

With no ``--added``, this demands **byte-for-byte identity** -- the gate for a refactor that
is meant to preserve behaviour exactly.

``--added`` names columns the change is *expected* to introduce. Every other column must
still match exactly, dtypes included, which is the gate for a schema addition. M9 used
``--added source instrument direction``.

Exits non-zero on any difference, so it can gate a script.

Reads with ``float_precision="round_trip"``, which is the other half of the ``%.17g`` that
``capture_trade_logs.py`` writes with: pandas' **default CSV parser is not correctly
rounded** and folds adjacent float64 values together, so a bare ``read_csv`` cannot see a
one-ULP difference no matter how many digits were written. Writing 17 digits and parsing
them approximately defeats the gate at exactly the precision it claims to guarantee.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nqbt import logsetup

logger = logging.getLogger(__name__)


def compare(before: Path, after: Path, added: set[str]) -> int:
    failures = 0
    names = sorted(p.name for p in before.iterdir() if p.is_file())
    if not names:
        logger.info("no files in %s", before)
        return 1

    missing = [n for n in names if not (after / n).exists()]
    for name in missing:
        logger.info("FAIL %s: absent from %s", name, after)
        failures += 1

    for name in (n for n in names if n not in missing):
        old = pd.read_csv(before / name, float_precision="round_trip")
        new = pd.read_csv(after / name, float_precision="round_trip")

        unexpected = [c for c in new.columns if c not in old.columns and c not in added]
        if unexpected:
            logger.info("FAIL %s: unexpected new column(s) %s", name, unexpected)
            failures += 1

        dropped = [c for c in old.columns if c not in new.columns]
        if dropped:
            logger.info("FAIL %s: column(s) disappeared %s", name, dropped)
            failures += 1
            continue

        try:
            pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)
        except AssertionError as exc:
            logger.info("FAIL %s: %s", name, str(exc).splitlines()[0])
            failures += 1
            continue

        gained = [c for c in new.columns if c not in old.columns]
        note = f"  (+{','.join(gained)})" if gained else ""
        logger.info("  ok  %s  %s rows x %d cols%s", name, f"{len(old):,}", len(old.columns), note)

    logger.info("")
    if failures:
        logger.info("%d FAILURE(S)", failures)
    elif added:
        logger.info("ALL PRE-EXISTING COLUMNS IDENTICAL")
    else:
        logger.info("BYTE-FOR-BYTE IDENTICAL")

    return failures


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument(
        "--added",
        nargs="*",
        default=[],
        help="columns the change is expected to add; all others must match exactly",
    )
    args = parser.parse_args(argv[1:])

    return 1 if compare(args.before, args.after, set(args.added)) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
