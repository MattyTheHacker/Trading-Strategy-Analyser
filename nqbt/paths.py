"""Default filesystem locations.

Resolved relative to the repository root so that the CLI works from any working
directory. All three are gitignored -- raw exports and derived caches never enter version
control.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
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

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
"""Raw NT8 Historical Data exports."""

MINUTE_DIR = DATA_DIR / "minute"
"""Manual Tools -> Historical Data exports, one file per contract."""

ADDON_DIR = DATA_DIR / "addon"
"""Snapshots written by the NqbtHistoricalExporter AddOn via BarsRequest."""

ARCHIVE_DIR = DATA_DIR / "archive"
"""The durable union of every source, and the only thing ingestion reads.

Exports are moving windows rather than snapshots -- ``docs/nt8-fidelity.md``, "Contract data"."""

SOURCE_DIRS = (MINUTE_DIR, ADDON_DIR)
"""Folders merged into the archive, in precedence order -- later wins a disagreement."""

TICK_DIR = DATA_DIR / "tick"
"""Tick exports: a different format, sharing the same ``.Last.txt`` naming, so bar ingestion
must never glob across both."""

CACHE_DIR = REPO_ROOT / "cache"
"""Parsed bars in Parquet, plus the ingestion manifest."""

RESULTS_DIR = REPO_ROOT / "results"
"""DuckDB sweep results."""

BARS_DIR = CACHE_DIR / "bars"
CONTINUOUS_DIR = CACHE_DIR / "continuous"
MANIFEST_PATH = CACHE_DIR / "manifest.json"
SWEEPS_DB = RESULTS_DIR / "sweeps.duckdb"
