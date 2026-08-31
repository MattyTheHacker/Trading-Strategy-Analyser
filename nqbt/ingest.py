"""Parse NT8 Historical Data exports into a Parquet bar cache.

Export format is semicolon-delimited, one minute bar per line, timestamps end-of-bar in
UTC::

    yyyyMMdd HHmmss;open;high;low;close;volume
    20231207 000100;16019.25;16019.25;16016.75;16017.25;19

**Ingestion reads :mod:`nqbt.archive`, never an export folder.** This module mirrors its
input exactly, which is correct for a snapshot and quietly destructive for a moving window --
``docs/nt8-fidelity.md``, "Contract data". ``ingest_all`` refreshes the archive first so the
step cannot be skipped.

Reading is **incremental** where it safely can be: the manifest records how far into the file
was parsed and a hash of exactly those bytes, so a genuine append reads only the tail while
anything else falls back to a full reparse. Hashing only the head cannot see a rewritten tail,
which froze stale bars in the cache and dropped real ones at the seam.

The cache is deliberately lossless -- out-of-session prints are tagged, not dropped, so the raw
export can always be reconstructed from Parquet. :func:`load_contract` drops them on the way
out, so a per-contract bar frame and a spliced one are the same bar set --
``docs/nt8-fidelity.md``, "Sessions".
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, override

import pandas as pd

from nqbt import archive, paths, sessions
from nqbt.instruments import ContractId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from nqbt.sessions import SessionInfo

RAW_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
BAR_DTYPES = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
}

TIMESTAMP_FORMAT = "%Y%m%d %H%M%S"

TICK_EXPORT_FIELDS = 5
"""Semicolon-separated fields in a tick export: timestamp;last;bid;ask;volume."""

TICK_STAMP_PARTS = 3
"""Whitespace-separated parts of a tick export's timestamp, the third sub-second."""
HASH_CHUNK_BYTES = 1 << 20
"""Read size when hashing. Hashing is I/O bound and cheap next to parsing."""

STRAY_SHARE_LIMIT = 0.01
"""Out-of-session share above which a cached contract is a broken export, not stray prints.

Comfortably above every rate measured here -- ``docs/nt8-fidelity.md``, "Sessions"."""


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
    def from_dict(cls, d: Mapping[str, str | int]) -> ContractManifest:
        """Rebuild an entry from the JSON the manifest file holds.

        Keyed off ``__slots__`` so an entry an older version wrote raises ``KeyError``
        rather than arriving half-filled.
        """
        return cls(**{k: d[k] for k in cls.__slots__})  # type: ignore[arg-type]  # JSON is untyped


@dataclass(slots=True)
class IngestResult:
    """Outcome of ingesting one contract."""

    contract: ContractId
    rows_added: int
    rows_total: int
    action: str
    """One of ``"created"``, ``"appended"``, ``"reparsed"``, ``"up-to-date"``."""
    warnings: list[str] = field(default_factory=list)

    @override
    def __str__(self) -> str:
        return (
            f"{self.contract.nt8_name:<12} {self.action:<11} "
            f"+{self.rows_added:>7,} rows  ({self.rows_total:,} total)"
        )


@dataclass(frozen=True, slots=True)
class SkippedExport:
    """An export-shaped file whose name is not a contract this project ingests."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.path.name}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ExportScan:
    """What one export folder holds, split into what ingests and what does not."""

    exports: dict[ContractId, Path]
    skipped: list[SkippedExport]


class IngestError(RuntimeError):
    """Raised when a raw export cannot be parsed into usable bars."""


# -- manifest -----------------------------------------------------------------


def load_manifest(path: Path = paths.MANIFEST_PATH) -> dict[str, ContractManifest]:
    """Every manifest entry on disk, dropping any an older version wrote differently."""
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
    """Write the manifest out sorted, creating its directory if it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, dict[str, object]] = {k: asdict(v) for k, v in sorted(manifest.items())}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _hash_range(source: Path, length: int) -> str:
    """SHA-256 of the first ``length`` bytes of ``source``.

    A file shorter than ``length`` hashes whatever it has, which simply produces a digest
    that will not match -- the same answer as an explicit error, without the branch.
    """
    digest = hashlib.sha256()
    remaining: int = length
    with source.open("rb") as fh:
        while remaining > 0:
            chunk: bytes = fh.read(min(HASH_CHUNK_BYTES, remaining))
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
    head: bytes = data[:512].split(b"\n", 1)[0]
    if not head:
        return
    fields: list[bytes] = head.split(b";")
    stamp: list[bytes] = fields[0].split()
    if len(fields) == TICK_EXPORT_FIELDS and len(stamp) == TICK_STAMP_PARTS:
        msg: str = (
            f"{source_name} looks like a tick export "
            f"(timestamp;last;bid;ask;volume with sub-second stamps), not minute bars. "
            f"Bar ingestion reads {paths.MINUTE_DIR}; tick files live in {paths.TICK_DIR}."
        )
        raise IngestError(
            msg,
        )


def parse_export(data: bytes, source_name: str = "<bytes>") -> pd.DataFrame:
    """Parse raw export bytes into a validated bar frame indexed by UTC timestamp."""
    if not data.strip():
        return _empty_frame()

    _reject_tick_export(data, source_name)

    frame: pd.DataFrame = pd.read_csv(
        io.BytesIO(data),
        sep=";",
        header=None,
        names=RAW_COLUMNS,
        dtype={c: BAR_DTYPES.get(c, "string") for c in RAW_COLUMNS},
        engine="c",
    )

    ts: pd.Series[pd.Timestamp] = pd.to_datetime(
        frame["timestamp"], format=TIMESTAMP_FORMAT, utc=True, errors="coerce"
    )
    bad: pd.Series[bool] = ts.isna()
    if bad.all():
        msg: str = f"{source_name}: no parseable timestamps; expected '{TIMESTAMP_FORMAT}'"
        raise IngestError(msg)
    frame = frame.loc[~bad].copy()
    frame.index = pd.DatetimeIndex(ts.loc[~bad], name="ts_utc")
    frame = frame.drop(columns=["timestamp"])

    return _finalise(frame, source_name=source_name)


def _empty_frame() -> pd.DataFrame:
    frame: pd.DataFrame = pd.DataFrame({c: pd.Series(dtype=t) for c, t in BAR_DTYPES.items()})
    frame.index = pd.DatetimeIndex([], tz="UTC", name="ts_utc")
    frame["trading_day"] = pd.Series(dtype="datetime64[s]")
    frame["in_session"] = pd.Series(dtype="bool")
    return frame


def _finalise(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Sort, deduplicate, validate OHLC sanity and attach session classification."""
    frame = frame.sort_index(kind="stable")
    frame = frame[~frame.index.duplicated(keep="last")]

    highs, lows = frame["high"], frame["low"]
    body_max: pd.Series[float] = frame[["open", "close"]].max(axis=1)
    body_min: pd.Series[float] = frame[["open", "close"]].min(axis=1)
    invalid: pd.Series[bool] = (highs < lows) | (highs < body_max) | (lows > body_min)
    if invalid.any():
        msg: str = (
            f"{source_name}: {int(invalid.sum())} bars violate OHLC ordering, "
            f"first at {frame.index[int(invalid.argmax())]}"
        )
        raise IngestError(
            msg,
        )

    info: SessionInfo = sessions.classify(pd.DatetimeIndex(frame.index))
    frame["trading_day"] = info.trading_day
    frame["in_session"] = info.in_session
    return frame


# -- ingestion ----------------------------------------------------------------


def discover_exports(data_dir: Path = paths.MINUTE_DIR, root: str | None = None) -> ExportScan:
    """Find raw exports, keyed by contract, optionally filtered to one root symbol.

    A file whose name is not a contract this project ingests is reported in
    :attr:`ExportScan.skipped`, never dropped silently.
    """
    found: dict[ContractId, Path] = {}
    skipped: list[SkippedExport] = []
    for path in sorted(data_dir.glob("*.Last.txt")):
        name: str = path.name.removesuffix(".Last.txt")
        try:
            contract: ContractId = ContractId.parse(name)
        except ValueError as exc:
            skipped.append(SkippedExport(path, str(exc)))
            continue
        if root is not None and contract.root != root.upper():
            continue
        found[contract] = path
    return ExportScan(found, skipped)


def contract_cache_path(contract: ContractId, cache_dir: Path = paths.CACHE_DIR) -> Path:
    """Where one contract's cached bars live."""
    return cache_dir / "bars" / contract.root / f"{contract.cache_key}.parquet"


def drop_out_of_session(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Drop the stray prints NT8 would never have formed into bars.

    Raises :class:`IngestError` above :data:`STRAY_SHARE_LIMIT`, where the export is telling us
    something other than "a handful of strays" and filtering it would hide that.
    """
    strays: int = int((~frame["in_session"]).sum())
    if strays > len(frame) * STRAY_SHARE_LIMIT:
        msg: str = (
            f"{source_name}: {strays:,} of {len(frame):,} bars fall outside session hours, "
            f"above the {STRAY_SHARE_LIMIT:.0%} that stray prints account for; the export or "
            f"the session template is wrong rather than the bars being strays"
        )
        raise IngestError(msg)
    return frame[frame["in_session"]]


def load_contract(contract: ContractId, cache_dir: Path = paths.CACHE_DIR) -> pd.DataFrame:
    """Read one contract's cached bars, less the prints NT8 would never have formed."""
    path: Path = contract_cache_path(contract, cache_dir)
    if not path.exists():
        msg: str = f"no cached bars for {contract.nt8_name}; run `nqbt ingest` first"
        raise FileNotFoundError(msg)
    return drop_out_of_session(pd.read_parquet(path), source_name=contract.nt8_name)


def ingest_contract(
    contract: ContractId,
    source: Path,
   
    cache_dir: Path = paths.CACHE_DIR,
    manifest: dict[str, ContractManifest] | None = None,
    force: bool = False,
) -> tuple[IngestResult, ContractManifest]:
    """Parse a single contract export into the cache, appending where possible."""
    manifest = manifest if manifest is not None else load_manifest(cache_dir / "manifest.json")
    key: str = contract.nt8_name
    entry: ContractManifest | None = manifest.get(key)
    cache_path: Path = contract_cache_path(contract, cache_dir)

    size: int = source.stat().st_size
    warnings: list[str] = []

    # A genuine append leaves every byte already parsed byte-for-byte intact. Anything
    # else -- a mid-formation bar completing, a bar revised, a bar withdrawn -- rewrites
    # part of that range, and nothing short of a full reparse can be trusted after it.
    appended_only: bool = (
        entry is not None
        and cache_path.exists()
        and size >= entry.byte_offset
        and _hash_range(source, entry.byte_offset) == entry.consumed_hash
    )
    reusable: ContractManifest | None = entry if appended_only and not force else None

    if reusable is not None and reusable.source_size == size:
        return (
            IngestResult(contract, 0, reusable.rows, "up-to-date"),
            reusable,
        )

    if entry is not None and reusable is None and not force and cache_path.exists():
        reason: str = "shrank" if size < entry.byte_offset else "was regenerated, not appended to"
        warnings.append(
            f"{source.name} {reason}; reparsing in full so revised or withdrawn bars "
            "are picked up rather than left stale",
        )

    new_offset: int
    combined: pd.DataFrame
    rows_added: int
    action: str
    if reusable is not None:
        with source.open("rb") as fh:
            fh.seek(reusable.byte_offset)
            tail: bytes = fh.read()
        consumed, tail = _trim_partial_line(tail)
        new_offset = reusable.byte_offset + consumed
        added: pd.DataFrame = parse_export(tail, source_name=source.name)
        existing: pd.DataFrame = pd.read_parquet(cache_path)
        # Concatenate new last: _finalise sorts stably and keeps the last of any repeated
        # timestamp, so a bar present in both wins from the file. Filtering to strictly
        # newer timestamps instead would make a corrected bar unrepresentable.
        combined = pd.concat([existing, added]) if len(added) else existing
        combined = _finalise(combined, source_name=source.name)
        rows_added = len(combined) - len(existing)
        action = "appended" if rows_added else "up-to-date"
    else:
        data: bytes = source.read_bytes()
        consumed, data = _trim_partial_line(data)
        new_offset = consumed
        combined = parse_export(data, source_name=source.name)
        rows_added = len(combined)
        action = "reparsed" if cache_path.exists() else "created"

    if combined.empty:
        msg: str = f"{source.name}: produced no bars"
        raise IngestError(msg)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(cache_path, engine="pyarrow", compression="zstd", index=True)

    out_of_session: int = int((~combined["in_session"]).sum())
    if out_of_session:
        warnings.append(
            f"{out_of_session:,} bars fall outside session hours (stray prints); "
            "tagged in_session=False in the cache and dropped from every bar frame "
            "`load_contract` hands out",
        )

    updated: ContractManifest = ContractManifest(
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
    cut: int = data.rfind(b"\n")
    if cut == -1:
        return 0, b""
    return cut + 1, data[: cut + 1]


def ingest_all(
   
    sources: Sequence[Path] = paths.SOURCE_DIRS,
    archive_dir: Path = paths.ARCHIVE_DIR,
    data_dir: Path | None = None,
    cache_dir: Path = paths.CACHE_DIR,
    root: str | None = None,
    force: bool = False,
) -> tuple[list[archive.MergeResult], list[IngestResult], list[SkippedExport]]:
    """Refresh the archive from every source, then ingest it.

    The archive step is not optional by default, so it cannot be skipped by forgetting it.
    ``data_dir`` bypasses it and ingests one folder directly, for inspecting a single export in
    isolation; **not the normal path**. The third return is every file the scan could not
    place, so a misnamed export is reported rather than lost.
    """
    manifest_path: Path = cache_dir / "manifest.json"
    manifest: dict[str, ContractManifest] = load_manifest(manifest_path)

    merges: list[archive.MergeResult] = []
    if data_dir is None:
        merges = archive.build_archive(sources, archive_dir, root=root)
        data_dir = archive_dir

    scan: ExportScan = discover_exports(data_dir, root=root)
    if not scan.exports:
        target: str = f" for {root}" if root else ""
        msg: str = f"no NT8 exports{target} found in {data_dir}"
        if scan.skipped:
            msg += "; skipped " + ", ".join(str(skip) for skip in scan.skipped)
        raise IngestError(msg)

    results: list[IngestResult] = []
    for contract, source in sorted(scan.exports.items()):
        result, _ = ingest_contract(contract, source, cache_dir=cache_dir, manifest=manifest, force=force)
        results.append(result)

    save_manifest(manifest, manifest_path)
    return merges, results, scan.skipped
