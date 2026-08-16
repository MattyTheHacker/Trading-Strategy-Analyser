"""Compare two captures from ``capture_trade_logs.py``.

    ./.venv/Scripts/python.exe tools/compare_trade_logs.py before after [--added col ...]

With no ``--added``, this demands **byte-for-byte identity** -- the gate for a refactor that
is meant to preserve behaviour exactly.

``--added`` names columns the change is *expected* to introduce. Every other column must
still match exactly, dtypes included, which is the gate for a schema addition. M9 used
``--added source instrument direction``.

Exits non-zero on any difference, so it can gate a script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def compare(before: Path, after: Path, added: set[str]) -> int:
    failures = 0
    names = sorted(p.name for p in before.iterdir() if p.is_file())
    if not names:
        return 1

    missing = [n for n in names if not (after / n).exists()]
    for name in missing:
        failures += 1

    for name in (n for n in names if n not in missing):
        old = pd.read_csv(before / name)
        new = pd.read_csv(after / name)

        unexpected = [c for c in new.columns if c not in old.columns and c not in added]
        if unexpected:
            failures += 1
        dropped = [c for c in old.columns if c not in new.columns]
        if dropped:
            failures += 1
            continue

        try:
            pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)
        except AssertionError:
            failures += 1
            continue

        gained = [c for c in new.columns if c not in old.columns]
        f"  (+{','.join(gained)})" if gained else ""

    if failures or added:
        pass
    else:
        pass
    return failures


def main(argv: list[str]) -> int:
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
