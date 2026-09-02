"""Build the `POST /git/trees` body that moves submodule pointers to new commits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# A submodule is a tree entry of mode 160000 holding a commit id rather than a blob, which is
# why the blob-only endpoints cannot move one. `.github/workflows/bump-submodules.yaml` has the
# rest of the reasoning.
SUBMODULE_MODE = "160000"


def parse_moved(text: str) -> list[tuple[str, str]]:
    """The `<path> <sha>` lines of a moved-submodule list, blank lines dropped."""
    moved: list[tuple[str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            path, sha = line.split()
        except ValueError:
            msg: str = f"line {number} is not '<path> <sha>': {line!r}"
            raise ValueError(msg) from None
        moved.append((path, sha))

    return moved


def tree_payload(base_tree: str, moved: list[tuple[str, str]]) -> dict[str, object]:
    """The request body laying `moved` over `base_tree`."""
    if not moved:
        msg: str = "no submodule moved, so there is no tree to write"
        raise ValueError(msg)

    return {
        "base_tree": base_tree,
        "tree": [{"path": path, "mode": SUBMODULE_MODE, "type": "commit", "sha": sha} for path, sha in moved],
    }


def build_parser() -> argparse.ArgumentParser:
    """The command line: the tree to build on, and the list of pointers that moved."""
    parser = argparse.ArgumentParser(description="Build a git tree payload moving submodules.")
    parser.add_argument("base_tree", help="sha of the tree the new one is layered onto")
    parser.add_argument("moved_file", help="a file of '<path> <sha>' lines, one per submodule")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the payload to stdout and return the process exit code."""
    args = build_parser().parse_args(argv)
    moved = parse_moved(Path(args.moved_file).read_text(encoding="utf-8"))
    sys.stdout.write(json.dumps(tree_payload(args.base_tree, moved)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
