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
    "MINUTE_DIR",
    "TICK_DIR",
    "CACHE_DIR",
    "RESULTS_DIR",
    "BARS_DIR",
    "CONTINUOUS_DIR",
    "MANIFEST_PATH",
    "SWEEPS_DB",
]

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
"""Raw NT8 Historical Data exports."""

MINUTE_DIR = DATA_DIR / "minute"
"""Minute bar exports, one file per contract -- the input to the bar cache."""

TICK_DIR = DATA_DIR / "tick"
"""Tick exports. A different format (``timestamp;last;bid;ask;volume``) and orders of
magnitude larger, but sharing the same ``.Last.txt`` naming, so bar ingestion must never
glob across both."""

CACHE_DIR = REPO_ROOT / "cache"
"""Parsed bars in Parquet, plus the ingestion manifest."""

RESULTS_DIR = REPO_ROOT / "results"
"""DuckDB sweep results."""

BARS_DIR = CACHE_DIR / "bars"
CONTINUOUS_DIR = CACHE_DIR / "continuous"
MANIFEST_PATH = CACHE_DIR / "manifest.json"
SWEEPS_DB = RESULTS_DIR / "sweeps.duckdb"
