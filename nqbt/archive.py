"""The durable union of every export source, and the only thing ingestion reads.

Exports are **moving windows, not snapshots**, and neither source is a superset of the other,
so the archive only ever grows and each source is merged into it -- ``docs/nt8-fidelity.md``,
"Contract data".

The merge is **textual**: lines are keyed by their timestamp field and otherwise passed through
byte for byte. Parsing prices into floats and formatting them back is a needless opportunity to
change a value, and ``yyyyMMdd HHmmss`` sorts chronologically as ASCII, so nothing here needs
to understand a date.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nqbt import paths

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

__all__ = ["MergeResult", "build_archive", "merge_contract"]

FIELDS = 6
"""``timestamp;open;high;low;close;volume``."""


@dataclass(slots=True)
class MergeResult:
    """What one contract's merge changed."""

    contract: str
    bars: int
    added: int
    revised: int
    sources: int
    skipped_lines: int = 0

    def __str__(self) -> str:
        detail = f"+{self.added:,} new" if self.added else "no new bars"
        if self.revised:
            detail += f", {self.revised:,} revised"
        return f"{self.contract:<12} {self.bars:>9,} bars  ({detail}, {self.sources} source(s))"


def _read(path: Path) -> dict[bytes, bytes]:
    """Map each bar's timestamp field to its whole line.

    Malformed lines are dropped rather than raising: an export read while it is being written
    ends mid-line. Bar validation is :func:`nqbt.ingest.parse_export`'s job, downstream.
    """
    rows: dict[bytes, bytes] = {}
    for raw in path.read_bytes().split(b"\n"):
        line = raw.rstrip(b"\r")
        if not line:
            continue
        key, separator, rest = line.partition(b";")
        if not separator or rest.count(b";") != FIELDS - 2:
            continue
        rows[key] = line
    return rows


def merge_contract(source_paths: Sequence[Path], archive_path: Path) -> MergeResult:
    """Fold every source into ``archive_path``, which may not exist yet."""
    original: dict[bytes, bytes] = _read(archive_path) if archive_path.exists() else {}
    merged = dict(original)

    for path in source_paths:
        rows = _read(path)
        if not rows:
            continue
        # The newest bar in a file may have been caught mid-formation, so it may fill a
        # gap but must never overwrite something already recorded.
        newest = max(rows)
        for key, line in rows.items():
            if key == newest and key in merged:
                continue
            merged[key] = line

    # Counted against the archive as it was, not as each source touched it: sources
    # routinely disagree, so tallying intermediate writes reports churn on a no-op merge.
    added = sum(1 for key in merged if key not in original)
    revised = sum(1 for key, line in merged.items() if key in original and original[key] != line)

    if len(merged) < len(original):
        msg = f"{archive_path.name}: archive shrank from {len(original):,} to {len(merged):,}"
        raise RuntimeError(  # pragma: no cover - the merge cannot delete keys
            msg,
        )
    archive = merged

    _write(archive_path, archive)
    return MergeResult(
        contract=archive_path.name.removesuffix(".Last.txt"),
        bars=len(archive),
        added=added,
        revised=revised,
        sources=len(source_paths),
    )


def _write(path: Path, rows: dict[bytes, bytes]) -> None:
    """Write sorted, atomically.

    Sorting is what makes an unchanged merge produce byte-identical output, so ingestion's
    content hash reports "up-to-date" instead of reparsing millions of bars every run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = b"\n".join(rows[key] for key in sorted(rows))
    if body:
        body += b"\n"
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(body)
    temp.replace(path)


def _contracts(source_dirs: Iterable[Path], root: str | None) -> dict[str, list[Path]]:
    """Source files per contract, in the precedence order the folders were given."""
    found: dict[str, list[Path]] = {}
    for directory in source_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.Last.txt")):
            name = path.name.removesuffix(".Last.txt")
            if root is not None and not name.upper().startswith(root.upper() + " "):
                continue
            found.setdefault(name, []).append(path)
    return found


def build_archive(
    source_dirs: Sequence[Path] = paths.SOURCE_DIRS,
    archive_dir: Path = paths.ARCHIVE_DIR,
    *,
    root: str | None = None,
) -> list[MergeResult]:
    """Merge every source folder into the archive and report what changed.

    A contract in the archive but absent from every source is left alone -- which is what an
    expired contract looks like once the provider stops serving it.
    """
    results = []
    for name, source_paths in sorted(_contracts(source_dirs, root).items()):
        results.append(merge_contract(source_paths, archive_dir / f"{name}.Last.txt"))
    return results
