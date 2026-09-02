"""Command-line interface for the custom LibCST auto-formatter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst

from . import ACTIVE_RULES


def format_file(filepath: Path, check: bool = False) -> bool:  # noqa: FBT002, FBT001
    """Applies rules to a file. Returns True if changes would be/were made."""
    original_code = filepath.read_text(encoding="utf-8")

    try:
        tree = cst.parse_module(original_code)
    except cst.ParserSyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
        return False

    modified_tree = tree
    for rule in ACTIVE_RULES:
        modified_tree = modified_tree.visit(rule)

    new_code = modified_tree.code

    if original_code != new_code:
        if check:
            print(f"Would reformat {filepath}")
        else:
            filepath.write_text(new_code, encoding="utf-8")
            print(f"Reformatted {filepath}")
        return True

    return False


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
    for path in args.paths:
        if path.is_file() and path.suffix == ".py":
            files_to_format.append(path)
        elif path.is_dir():
            files_to_format.extend(path.rglob("*.py"))
        else:
            print(f"Skipping {path}, not a Python file or directory.")

    changed_files = 0
    for file_path in files_to_format:
        if format_file(file_path, check=args.check):
            changed_files += 1

    print(f"\nDone. Found {changed_files} unformatted out of {len(files_to_format)} files.")

    if args.check and changed_files > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
