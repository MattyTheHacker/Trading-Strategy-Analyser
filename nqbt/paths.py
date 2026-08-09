"""Default filesystem locations.

Resolved relative to the repository root so that the CLI works from any working
directory. All three are gitignored -- raw exports and derived caches never enter version
control.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "Path",
    "REPO_ROOT",
    "DATA_DIR",
    "CACHE_DIR",
    "RESULTS_DIR",
    "BARS_DIR",
    "CONTINUOUS_DIR",
    "MANIFEST_PATH",
    "SWEEPS_DB",
]

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
"""Raw NT8 Historical Data exports, one file per contract."""

CACHE_DIR = REPO_ROOT / "cache"
"""Parsed bars in Parquet, plus the ingestion manifest."""

RESULTS_DIR = REPO_ROOT / "results"
"""DuckDB sweep results."""

BARS_DIR = CACHE_DIR / "bars"
CONTINUOUS_DIR = CACHE_DIR / "continuous"
MANIFEST_PATH = CACHE_DIR / "manifest.json"
SWEEPS_DB = RESULTS_DIR / "sweeps.duckdb"
