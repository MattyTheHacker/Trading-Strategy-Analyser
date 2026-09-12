"""Command-line interface for the custom LibCST auto-formatter."""

from __future__ import annotations

import argparse
import enum
import sys
from pathlib import Path

import libcst as cst

from . import ACTIVE_RULES

EXIT_OK = 0
EXIT_WOULD_REFORMAT = 1
EXIT_ERROR = 2


class Outcome(enum.Enum):
    """What formatting one file came to."""

    UNCHANGED = enum.auto()
    CHANGED = enum.auto()
    FAILED = enum.auto()


def format_file(filepath: Path, check: bool = False) -> Outcome:
    """Applies rules to a file, reporting whether it changed or could not be parsed."""
    original_code = filepath.read_text(encoding="utf-8")

    try:
        tree = cst.parse_module(original_code)
    except cst.ParserSyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
        return Outcome.FAILED

    modified_tree = tree
    for rule in ACTIVE_RULES:
        modified_tree = modified_tree.visit(rule)

    new_code = modified_tree.code

    if original_code == new_code:
        return Outcome.UNCHANGED

    if check:
        print(f"Would reformat {filepath}")
    else:
        filepath.write_text(new_code, encoding="utf-8", newline="\n")
        print(f"Reformatted {filepath}")

    return Outcome.CHANGED


def python_files(directory: Path) -> list[Path]:
    """Every ``.py`` file under a directory, skipping the dot-directories beneath it."""
    return [
        path
        for path in sorted(directory.rglob("*.py"))
        if not any(part.startswith(".") for part in path.relative_to(directory).parts)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Custom LibCST auto-formatter")
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to format")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files are formatted without writing changes, exiting with status 1 if changes needed.",
    )
    args = parser.parse_args()

    files_to_format: list[Path] = []
    unusable = 0
    for path in args.paths:
        if path.is_file() and path.suffix == ".py":
            files_to_format.append(path)
        elif path.is_dir():
            files_to_format.extend(python_files(path))
        else:
            unusable += 1
            print(f"Skipping {path}, not a Python file or directory.", file=sys.stderr)

    outcomes = [format_file(file_path, check=args.check) for file_path in files_to_format]
    changed_files = outcomes.count(Outcome.CHANGED)
    failed_files = outcomes.count(Outcome.FAILED)

    print(f"\nDone. Found {changed_files} unformatted out of {len(files_to_format)} files.")

    # A file that could not be read or parsed is not a formatted file, and neither is a path
    # that is not there at all -- exit distinctly so neither passes as a clean run
    if failed_files or unusable:
        print(f"Failed on {failed_files + unusable} path(s).", file=sys.stderr)
        return EXIT_ERROR

    if args.check and changed_files > 0:
        return EXIT_WOULD_REFORMAT

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
