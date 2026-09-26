"""Decide whether a pull request runs the trade-log gate, and whether its result passes.

The caller is ``.github/workflows/trade-log-gate.yaml``; the procedure it automates is
``CONTRIBUTING.md`` § "The trade-log regression gate".

    git diff --name-only --no-renames BASE HEAD | python tools/trade_log_gate_ci.py applies
    python tools/trade_log_gate_ci.py verdict --status N --output compare.txt --labels '[...]'
"""

from __future__ import annotations

import argparse
import enum
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

DOCUMENTATION_DIRECTORIES = ("docs/",)
DOCUMENTATION_SUFFIXES = (".md",)
DOCUMENTATION_FILES = frozenset({"Trading-Docs"})
"""The documentation submodule, whose pointer is the only path a bump of it changes."""

ACCEPT_LABEL = "expected-trade-log-change"
"""The label that says a pull request means to move a number."""

COMPARED = re.compile(r"^\d+ FAILURE\(S\)$", re.MULTILINE)
"""The last line ``compare_trade_logs.py`` writes when it ran to the end and found a difference."""


class Verdict(enum.Enum):
    """What one run of the gate came to."""

    IDENTICAL = enum.auto()
    ACCEPTED = enum.auto()
    MOVED = enum.auto()
    BROKEN = enum.auto()


MESSAGES = {
    Verdict.IDENTICAL: "The trade logs are identical.",
    Verdict.ACCEPTED: (
        f"::warning::Numbers moved, and the pull request carries the {ACCEPT_LABEL} label. "
        "Say in the pull request why they moved."
    ),
    Verdict.MOVED: (
        f"::error::Numbers moved. If that is intended, add the {ACCEPT_LABEL} label "
        "and say in the pull request why."
    ),
    Verdict.BROKEN: (
        "::error::The comparison did not finish, so nothing was measured, and no label passes that."
    ),
}

PASSING = frozenset({Verdict.IDENTICAL, Verdict.ACCEPTED})


def is_documentation(path: str) -> bool:
    """Whether a changed path is documentation, which is all the gate lets a pull request skip it for."""
    return (
        path in DOCUMENTATION_FILES
        or path.startswith(DOCUMENTATION_DIRECTORIES)
        or path.endswith(DOCUMENTATION_SUFFIXES)
    )


def applies(changed_paths: Iterable[str]) -> bool:
    """Whether the gate runs: on every pull request that changes anything but documentation."""
    return not all(is_documentation(path) for path in changed_paths)


def verdict(status: int, output: str, labels: Iterable[str]) -> Verdict:
    """Classify a comparison by its exit status, its output and the pull request's labels."""
    if status == 0:
        return Verdict.IDENTICAL

    if not COMPARED.search(output):
        return Verdict.BROKEN

    if ACCEPT_LABEL in labels:
        return Verdict.ACCEPTED

    return Verdict.MOVED


def build_parser() -> argparse.ArgumentParser:
    """The command line: one subcommand per question the workflow asks."""
    parser = argparse.ArgumentParser(description="Drive the trade-log gate from CI.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("applies", help="read changed paths on stdin; print applies=true|false")

    judge = commands.add_parser("verdict", help="exit 0 if the comparison passes, 1 if not")
    judge.add_argument("--status", type=int, required=True, help="compare_trade_logs.py's exit status")
    judge.add_argument("--output", type=Path, required=True, help="a file holding what it printed")
    judge.add_argument("--labels", default="[]", help="the pull request's label names, as a JSON list")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Answer one subcommand on stdout and return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "applies":
        changed: list[str] = [line.strip() for line in sys.stdin if line.strip()]
        sys.stdout.write(f"applies={str(applies(changed)).lower()}\n")

        return 0

    outcome: Verdict = verdict(
        args.status,
        args.output.read_text(encoding="utf-8"),
        json.loads(args.labels),
    )
    sys.stdout.write(MESSAGES[outcome] + "\n")

    return 0 if outcome in PASSING else 1


if __name__ == "__main__":
    raise SystemExit(main())
