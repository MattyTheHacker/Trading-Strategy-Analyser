"""The durable union of every export source.

NinjaTrader's exports are **moving windows, not snapshots**. It serves each contract for a
limited period and drops the tail once the contract expires, so a folder of exports loses
history over time rather than accumulating it. Two sources make this concrete: the manual
Tools -> Historical Data export holds each contract's final weeks, which the AddOn cannot
reach, while the AddOn holds three to six months of earlier history the manual export never
had, plus sessions the manual export dropped outright.

Neither is a superset. So ingestion reads an archive that only ever grows, and each source
is merged into it. Without this, running the AddOn a few months from now would faithfully
overwrite every expired contract with the truncated window the server still offers --
:mod:`nqbt.ingest` mirrors its input exactly, which is correct for a snapshot and quietly
destructive for a window.

The merge is textual: lines are keyed by their timestamp field and otherwise passed
through byte for byte. Parsing prices into floats and formatting them back is a needless
opportunity to change a value, and ``yyyyMMdd HHmmss`` sorts chronologically as ASCII, so
nothing here needs to understand a date.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from nqbt import paths

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

    Malformed lines are dropped rather than raising: an export read while it is being
    written ends mid-line, and that half-line is not worth failing a merge over. Bar
    validation is :func:`nqbt.ingest.parse_export`'s job, downstream of here.
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
        # The newest bar in a file may have been caught mid-formation. One real example:
        # a manual export's last bar showed 294 contracts of an eventual 890, with a high
        # and close that had not happened yet. Such a bar may fill a gap, but it must
        # never overwrite something already recorded.
        newest = max(rows)
        for key, line in rows.items():
            if key not in merged:
                merged[key] = line
            elif key != newest:
                merged[key] = line

    # Counted against the archive as it was, not as each source touched it. Sources
    # routinely disagree -- a manual export and the AddOn hold different volumes for the
    # same bar -- so an earlier source overwrites and a later one overwrites back. Tallying
    # those intermediate writes reports churn on a merge that changed nothing.
    added = sum(1 for key in merged if key not in original)
    revised = sum(1 for key, line in merged.items() if key in original and original[key] != line)

    if len(merged) < len(original):
        raise RuntimeError(  # pragma: no cover - the merge cannot delete keys
            f"{archive_path.name}: archive shrank from {len(original):,} to {len(merged):,}"
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

    Sorting the keys is what makes an unchanged merge produce byte-identical output, so
    ingestion's content hash reports "up-to-date" instead of reparsing three million bars
    every run. Timestamps sort chronologically as ASCII, so no dates are parsed.
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

    A contract already in the archive but absent from every source is left alone -- that
    is the case this whole module exists for, since it is exactly what an expired contract
    looks like once the provider stops serving it.
    """
    results = []
    for name, source_paths in sorted(_contracts(source_dirs, root).items()):
        results.append(merge_contract(source_paths, archive_dir / f"{name}.Last.txt"))
    return results
