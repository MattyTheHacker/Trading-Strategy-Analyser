"""Parse NT8 Historical Data exports into a Parquet bar cache.

Export format is semicolon-delimited, one minute bar per line, timestamps end-of-bar in
UTC::

    yyyyMMdd HHmmss;open;high;low;close;volume
    20231207 000100;16019.25;16019.25;16016.75;16017.25;19

Ingestion reads :mod:`nqbt.archive`, not the export folders themselves. Exports are moving
windows -- NinjaTrader drops each contract's tail once it expires -- and this module mirrors
its input exactly, so pointing it at a source folder would propagate that loss into the
cache. ``ingest_all`` refreshes the archive first so the step cannot be skipped.

Reading is **incremental** where it safely can be: the manifest records how far into the
file we parsed and a hash of exactly those bytes, so a genuine append reads only the tail
while anything else -- a bar revised, a bar withdrawn, a mid-formation bar completing --
falls back to a full reparse. Hashing only the head cannot see a rewritten tail, and reading
a rewrite as an append froze stale bars in the cache and dropped real ones at the seam.

The cache is deliberately lossless -- out-of-session prints are tagged, not dropped, so
the raw export can always be reconstructed from Parquet. Filtering happens downstream in
:mod:`nqbt.splice` when the continuous series is built.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from nqbt import archive, paths, sessions
from nqbt.instruments import ContractId

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

RAW_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
BAR_DTYPES = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
}

TIMESTAMP_FORMAT = "%Y%m%d %H%M%S"
HASH_CHUNK_BYTES = 1 << 20
"""Read size when hashing. Hashing is I/O bound and cheap next to parsing."""


@dataclass(slots=True)
class ContractManifest:
    """What we know about one raw file as of the last ingest."""

    contract: str
    source: str
    byte_offset: int
    source_size: int
    consumed_hash: str
    """SHA-256 of bytes ``[0, byte_offset)`` -- everything already parsed into the cache.

    Hashing the *whole* consumed range, rather than a fixed-size head, is what makes
    "appended to, or rewritten?" an exact question instead of a guess. Two producers write
    these files and they give different guarantees: the NinjaScript AddOn genuinely
    appends, while a manual Tools -> Historical Data export regenerates the file. NT8
    regenerations routinely differ in the tail -- a bar exported mid-formation returns
    with different values once complete, and bars occasionally vanish between exports.
    Both leave the head untouched, so a head-only check calls it an append and the stale
    or withdrawn bars then survive in the cache indefinitely.
    """
    last_timestamp: str
    rows: int

    @classmethod
    def from_dict(cls, d: dict) -> ContractManifest:
        return cls(**{k: d[k] for k in cls.__slots__})


@dataclass(slots=True)
class IngestResult:
    """Outcome of ingesting one contract."""

    contract: ContractId
    rows_added: int
    rows_total: int
    action: str
    """One of ``"created"``, ``"appended"``, ``"reparsed"``, ``"up-to-date"``."""
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"{self.contract.nt8_name:<12} {self.action:<11} "
            f"+{self.rows_added:>7,} rows  ({self.rows_total:,} total)"
        )


class IngestError(RuntimeError):
    """Raised when a raw export cannot be parsed into usable bars."""


# -- manifest -----------------------------------------------------------------


def load_manifest(path: Path = paths.MANIFEST_PATH) -> dict[str, ContractManifest]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, ContractManifest] = {}
    for key, value in raw.items():
        try:
            entries[key] = ContractManifest.from_dict(value)
        except KeyError:
            # Written by an older version carrying different integrity fields. Dropping
            # the entry costs one full reparse, which is the only safe reading of it.
            continue
    return entries


def save_manifest(manifest: dict[str, ContractManifest], path: Path = paths.MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: asdict(v) for k, v in sorted(manifest.items())}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _hash_range(source: Path, length: int) -> str:
    """SHA-256 of the first ``length`` bytes of ``source``.

    A file shorter than ``length`` hashes whatever it has, which simply produces a digest
    that will not match -- the same answer as an explicit error, without the branch.
    """
    digest = hashlib.sha256()
    remaining = length
    with source.open("rb") as fh:
        while remaining > 0:
            chunk = fh.read(min(HASH_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            digest.update(chunk)
    return digest.hexdigest()


# -- parsing ------------------------------------------------------------------


def _reject_tick_export(data: bytes, source_name: str) -> None:
    """Fail early and clearly if handed a tick export instead of minute bars.

    Both use the same ``.Last.txt`` suffix, and tick files run to several GB, so a
    mistaken path must not turn into a very slow parse that ends in a confusing error.
    """
    head = data[:512].split(b"\n", 1)[0]
    if not head:
        return
    fields = head.split(b";")
    stamp = fields[0].split()
    if len(fields) == 5 and len(stamp) == 3:
        msg = (
            f"{source_name} looks like a tick export "
            f"(timestamp;last;bid;ask;volume with sub-second stamps), not minute bars. "
            f"Bar ingestion reads {paths.MINUTE_DIR}; tick files live in {paths.TICK_DIR}."
        )
        raise IngestError(
            msg,
        )


def parse_export(data: bytes, *, source_name: str = "<bytes>") -> pd.DataFrame:
    """Parse raw export bytes into a validated bar frame indexed by UTC timestamp."""
    if not data.strip():
        return _empty_frame()

    _reject_tick_export(data, source_name)

    frame = pd.read_csv(
        io.BytesIO(data),
        sep=";",
        header=None,
        names=RAW_COLUMNS,
        dtype={c: BAR_DTYPES.get(c, "string") for c in RAW_COLUMNS},
        engine="c",
    )

    ts = pd.to_datetime(frame["timestamp"], format=TIMESTAMP_FORMAT, utc=True, errors="coerce")
    bad = ts.isna()
    if bad.all():
        msg = f"{source_name}: no parseable timestamps; expected '{TIMESTAMP_FORMAT}'"
        raise IngestError(msg)
    frame = frame.loc[~bad].copy()
    frame.index = pd.DatetimeIndex(ts.loc[~bad], name="ts_utc")
    frame = frame.drop(columns=["timestamp"])

    return _finalise(frame, source_name=source_name, dropped_timestamps=int(bad.sum()))


def _empty_frame() -> pd.DataFrame:
    frame = pd.DataFrame({c: pd.Series(dtype=t) for c, t in BAR_DTYPES.items()})
    frame.index = pd.DatetimeIndex([], tz="UTC", name="ts_utc")
    frame["trading_day"] = pd.Series(dtype="datetime64[s]")
    frame["in_session"] = pd.Series(dtype="bool")
    return frame


def _finalise(frame: pd.DataFrame, *, source_name: str, dropped_timestamps: int = 0) -> pd.DataFrame:
    """Sort, deduplicate, validate OHLC sanity and attach session classification."""
    frame = frame.sort_index(kind="stable")
    frame = frame[~frame.index.duplicated(keep="last")]

    highs, lows = frame["high"], frame["low"]
    body_max = frame[["open", "close"]].max(axis=1)
    body_min = frame[["open", "close"]].min(axis=1)
    invalid = (highs < lows) | (highs < body_max) | (lows > body_min)
    if invalid.any():
        msg = (
            f"{source_name}: {int(invalid.sum())} bars violate OHLC ordering, "
            f"first at {frame.index[invalid.argmax()]}"
        )
        raise IngestError(
            msg,
        )

    info = sessions.classify(frame.index)
    frame["trading_day"] = info.trading_day
    frame["in_session"] = info.in_session
    return frame


# -- ingestion ----------------------------------------------------------------


def discover_exports(data_dir: Path = paths.MINUTE_DIR, root: str | None = None) -> dict[ContractId, Path]:
    """Find raw exports, keyed by contract, optionally filtered to one root symbol."""
    found: dict[ContractId, Path] = {}
    for path in sorted(data_dir.glob("*.Last.txt")):
        name = path.name.removesuffix(".Last.txt")
        try:
            contract = ContractId.parse(name)
        except ValueError:
            continue
        if root is not None and contract.root != root.upper():
            continue
        found[contract] = path
    return found


def contract_cache_path(contract: ContractId, cache_dir: Path = paths.CACHE_DIR) -> Path:
    return cache_dir / "bars" / contract.root / f"{contract.cache_key}.parquet"


def load_contract(contract: ContractId, cache_dir: Path = paths.CACHE_DIR) -> pd.DataFrame:
    """Read one contract's cached bars."""
    path = contract_cache_path(contract, cache_dir)
    if not path.exists():
        msg = f"no cached bars for {contract.nt8_name}; run `nqbt ingest` first"
        raise FileNotFoundError(msg)
    return pd.read_parquet(path)


def ingest_contract(
    contract: ContractId,
    source: Path,
    *,
    cache_dir: Path = paths.CACHE_DIR,
    manifest: dict[str, ContractManifest] | None = None,
    force: bool = False,
) -> tuple[IngestResult, ContractManifest]:
    """Parse a single contract export into the cache, appending where possible."""
    manifest = manifest if manifest is not None else load_manifest(cache_dir / "manifest.json")
    key = contract.nt8_name
    entry = manifest.get(key)
    cache_path = contract_cache_path(contract, cache_dir)

    size = source.stat().st_size
    warnings: list[str] = []

    # A genuine append leaves every byte already parsed byte-for-byte intact. Anything
    # else -- a mid-formation bar completing, a bar revised, a bar withdrawn -- rewrites
    # part of that range, and nothing short of a full reparse can be trusted after it.
    appended_only = (
        entry is not None
        and cache_path.exists()
        and size >= entry.byte_offset
        and _hash_range(source, entry.byte_offset) == entry.consumed_hash
    )
    reuse = not force and appended_only

    if reuse and entry.source_size == size:
        return (
            IngestResult(contract, 0, entry.rows, "up-to-date"),
            entry,
        )

    if entry is not None and not reuse and not force and cache_path.exists():
        reason = "shrank" if size < entry.byte_offset else "was regenerated, not appended to"
        warnings.append(
            f"{source.name} {reason}; reparsing in full so revised or withdrawn bars "
            "are picked up rather than left stale",
        )

    if reuse:
        with source.open("rb") as fh:
            fh.seek(entry.byte_offset)
            tail = fh.read()
        consumed, tail = _trim_partial_line(tail)
        new_offset = entry.byte_offset + consumed
        added = parse_export(tail, source_name=source.name)
        existing = pd.read_parquet(cache_path)
        # Concatenate new last: _finalise sorts stably and keeps the last of any repeated
        # timestamp, so a bar present in both wins from the file. Filtering to strictly
        # newer timestamps instead would make a corrected bar unrepresentable.
        combined = pd.concat([existing, added]) if len(added) else existing
        combined = _finalise(combined, source_name=source.name)
        rows_added = len(combined) - len(existing)
        action = "appended" if rows_added else "up-to-date"
    else:
        data = source.read_bytes()
        consumed, data = _trim_partial_line(data)
        new_offset = consumed
        combined = parse_export(data, source_name=source.name)
        rows_added = len(combined)
        action = "reparsed" if cache_path.exists() else "created"

    if combined.empty:
        msg = f"{source.name}: produced no bars"
        raise IngestError(msg)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(cache_path, engine="pyarrow", compression="zstd", index=True)

    out_of_session = int((~combined["in_session"]).sum())
    if out_of_session:
        warnings.append(
            f"{out_of_session:,} bars fall outside session hours (stray prints); "
            "tagged in_session=False and excluded from the continuous series",
        )

    updated = ContractManifest(
        contract=key,
        source=str(source),
        byte_offset=new_offset,
        source_size=size,
        consumed_hash=_hash_range(source, new_offset),
        last_timestamp=combined.index[-1].isoformat(),
        rows=len(combined),
    )
    manifest[key] = updated

    return (
        IngestResult(contract, rows_added, len(combined), action, warnings),
        updated,
    )


def _trim_partial_line(data: bytes) -> tuple[int, bytes]:
    """Drop a trailing incomplete line, returning bytes safely consumed.

    An export being appended to while we read it can end mid-line. Parsing that would
    silently corrupt a bar, and recording its length as the offset would then skip the
    line's real content on the next run.
    """
    if not data:
        return 0, data
    cut = data.rfind(b"\n")
    if cut == -1:
        return 0, b""
    return cut + 1, data[: cut + 1]


def ingest_all(
    *,
    sources: Sequence[Path] = paths.SOURCE_DIRS,
    archive_dir: Path = paths.ARCHIVE_DIR,
    data_dir: Path | None = None,
    cache_dir: Path = paths.CACHE_DIR,
    root: str | None = None,
    force: bool = False,
) -> tuple[list[archive.MergeResult], list[IngestResult]]:
    """Refresh the archive from every source, then ingest it.

    The archive step is not optional by default, and that is deliberate. Exports are moving
    windows: run the AddOn after a contract expires and it returns only the truncated range
    the server still offers. Ingestion mirrors its input exactly -- correct for a snapshot,
    quietly destructive for a window -- so something has to accumulate, and doing it here
    means it cannot be skipped by forgetting a step.

    ``data_dir`` bypasses the archive and ingests one folder directly. For inspecting a
    single export in isolation; not the normal path.
    """
    manifest_path = cache_dir / "manifest.json"
    manifest = load_manifest(manifest_path)

    merges: list[archive.MergeResult] = []
    if data_dir is None:
        merges = archive.build_archive(sources, archive_dir, root=root)
        data_dir = archive_dir

    exports = discover_exports(data_dir, root=root)
    if not exports:
        target = f" for {root}" if root else ""
        msg = f"no NT8 exports{target} found in {data_dir}"
        raise IngestError(msg)

    results: list[IngestResult] = []
    for contract, source in sorted(exports.items()):
        result, _ = ingest_contract(contract, source, cache_dir=cache_dir, manifest=manifest, force=force)
        results.append(result)

    save_manifest(manifest, manifest_path)
    return merges, results
