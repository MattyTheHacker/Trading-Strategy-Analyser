"""Parse NT8 Historical Data exports into a Parquet bar cache.

Export format is semicolon-delimited, one minute bar per line, timestamps end-of-bar in
UTC::

    yyyyMMdd HHmmss;open;high;low;close;volume
    20231207 000100;16019.25;16019.25;16016.75;16017.25;19

A NinjaScript AddOn appends new bars to these files over time, so ingestion is
**incremental**: the manifest records how far into each raw file we have already parsed,
and a re-ingest reads only the tail. A full reparse happens automatically if the file
shrank or its head changed, which is what a regenerated export looks like.

The cache is deliberately lossless -- out-of-session prints are tagged, not dropped, so
the raw export can always be reconstructed from Parquet. Filtering happens downstream in
:mod:`nqbt.splice` when the continuous series is built.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from nqbt import paths, sessions
from nqbt.instruments import ContractId

RAW_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
BAR_DTYPES = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
}

TIMESTAMP_FORMAT = "%Y%m%d %H%M%S"
PREFIX_HASH_BYTES = 65_536
"""Bytes of the file head hashed to detect a regenerated (rather than appended) export."""


@dataclass(slots=True)
class ContractManifest:
    """What we know about one raw file as of the last ingest."""

    contract: str
    source: str
    byte_offset: int
    source_size: int
    prefix_hash: str
    prefix_len: int
    """Bytes covered by ``prefix_hash``. Stored so a later, longer file is re-hashed
    over the same range -- hashing "the whole file when it is small" would make every
    append look like a rewrite."""
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
    return {k: ContractManifest.from_dict(v) for k, v in raw.items()}


def save_manifest(
    manifest: dict[str, ContractManifest], path: Path = paths.MANIFEST_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: asdict(v) for k, v in sorted(manifest.items())}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _prefix_hash(source: Path, length: int) -> str:
    """Hash exactly ``length`` bytes from the head of ``source``."""
    with source.open("rb") as fh:
        return hashlib.sha256(fh.read(length)).hexdigest()


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
        raise IngestError(
            f"{source_name} looks like a tick export "
            f"(timestamp;last;bid;ask;volume with sub-second stamps), not minute bars. "
            f"Bar ingestion reads {paths.MINUTE_DIR}; tick files live in {paths.TICK_DIR}."
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

    ts = pd.to_datetime(
        frame["timestamp"], format=TIMESTAMP_FORMAT, utc=True, errors="coerce"
    )
    bad = ts.isna()
    if bad.all():
        raise IngestError(
            f"{source_name}: no parseable timestamps; expected '{TIMESTAMP_FORMAT}'"
        )
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


def _finalise(
    frame: pd.DataFrame, *, source_name: str, dropped_timestamps: int = 0
) -> pd.DataFrame:
    """Sort, deduplicate, validate OHLC sanity and attach session classification."""
    frame = frame.sort_index(kind="stable")
    frame = frame[~frame.index.duplicated(keep="last")]

    highs, lows = frame["high"], frame["low"]
    body_max = frame[["open", "close"]].max(axis=1)
    body_min = frame[["open", "close"]].min(axis=1)
    invalid = (highs < lows) | (highs < body_max) | (lows > body_min)
    if invalid.any():
        raise IngestError(
            f"{source_name}: {int(invalid.sum())} bars violate OHLC ordering, "
            f"first at {frame.index[invalid.argmax()]}"
        )

    info = sessions.classify(frame.index)
    frame["trading_day"] = info.trading_day
    frame["in_session"] = info.in_session
    return frame


# -- ingestion ----------------------------------------------------------------


def discover_exports(
    data_dir: Path = paths.MINUTE_DIR, root: str | None = None
) -> dict[ContractId, Path]:
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


def load_contract(
    contract: ContractId, cache_dir: Path = paths.CACHE_DIR
) -> pd.DataFrame:
    """Read one contract's cached bars."""
    path = contract_cache_path(contract, cache_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no cached bars for {contract.nt8_name}; run `nqbt ingest` first"
        )
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

    grew = entry is not None and entry.source_size <= size and size >= entry.prefix_len
    head_intact = grew and _prefix_hash(source, entry.prefix_len) == entry.prefix_hash
    reuse = (
        not force
        and entry is not None
        and cache_path.exists()
        and head_intact
        and entry.byte_offset <= size
    )

    if reuse and entry.source_size == size:
        return (
            IngestResult(contract, 0, entry.rows, "up-to-date"),
            entry,
        )

    if entry is not None and not reuse and not force and cache_path.exists():
        reason = "file shrank" if not grew else "head changed"
        warnings.append(f"{reason}; reparsing {source.name} in full")

    if reuse:
        with source.open("rb") as fh:
            fh.seek(entry.byte_offset)
            tail = fh.read()
        consumed, tail = _trim_partial_line(tail)
        new_offset = entry.byte_offset + consumed
        added = parse_export(tail, source_name=source.name)
        existing = pd.read_parquet(cache_path)
        added = added[added.index > existing.index[-1]] if len(existing) else added
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
        raise IngestError(f"{source.name}: produced no bars")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(cache_path, engine="pyarrow", compression="zstd", index=True)

    out_of_session = int((~combined["in_session"]).sum())
    if out_of_session:
        warnings.append(
            f"{out_of_session:,} bars fall outside session hours (stray prints); "
            "tagged in_session=False and excluded from the continuous series"
        )

    prefix_len = min(PREFIX_HASH_BYTES, size)
    updated = ContractManifest(
        contract=key,
        source=str(source),
        byte_offset=new_offset,
        source_size=size,
        prefix_hash=_prefix_hash(source, prefix_len),
        prefix_len=prefix_len,
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
    data_dir: Path = paths.MINUTE_DIR,
    cache_dir: Path = paths.CACHE_DIR,
    root: str | None = None,
    force: bool = False,
) -> list[IngestResult]:
    """Ingest every discovered export, updating the manifest once at the end."""
    manifest_path = cache_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    exports = discover_exports(data_dir, root=root)
    if not exports:
        target = f" for {root}" if root else ""
        raise IngestError(f"no NT8 exports{target} found in {data_dir}")

    results: list[IngestResult] = []
    for contract, source in sorted(exports.items()):
        result, _ = ingest_contract(
            contract, source, cache_dir=cache_dir, manifest=manifest, force=force
        )
        results.append(result)

    save_manifest(manifest, manifest_path)
    return results
