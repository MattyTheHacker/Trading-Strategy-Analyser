"""Default filesystem locations.

Resolved relative to the repository root so that the CLI works from any working
directory. All three are gitignored -- raw exports and derived caches never enter version
control.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = [
    "ADDON_DIR",
    "ARCHIVE_DIR",
    "BARS_DIR",
    "CACHE_DIR",
    "CONTINUOUS_DIR",
    "DATA_DIR",
    "MANIFEST_PATH",
    "MINUTE_DIR",
    "REPO_ROOT",
    "RESULTS_DIR",
    "SOURCE_DIRS",
    "SWEEPS_DB",
    "TICK_DIR",
    "Path",
]

REPO_ROOT: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = REPO_ROOT / "data"  # Raw NT8 Historical Data exports.
MINUTE_DIR: Path = DATA_DIR / "minute"  # Manual Tools -> Historical Data exports, one file per contract.
ADDON_DIR: Path = DATA_DIR / "addon"  # Snapshots written by the NqbtHistoricalExporter AddOn via BarsRequest.
ARCHIVE_DIR: Path = DATA_DIR / "archive"  # The durable union of every source, and the only thing ingestion reads.
SOURCE_DIRS: tuple[Path, Path] = (MINUTE_DIR, ADDON_DIR)  # Folders merged into the archive, in precedence order.
TICK_DIR: Path = DATA_DIR / "tick"  # Tick exports: a different format, sharing the same ``.Last.txt`` naming.
CACHE_DIR: Path = REPO_ROOT / "cache"  # Parsed bars in Parquet, plus the ingestion manifest.
RESULTS_DIR: Path = REPO_ROOT / "results"  # DuckDB sweep results.
BARS_DIR: Path = CACHE_DIR / "bars"
CONTINUOUS_DIR: Path = CACHE_DIR / "continuous"
MANIFEST_PATH: Path = CACHE_DIR / "manifest.json"
SWEEPS_DB: Path = RESULTS_DIR / "sweeps.duckdb"
