import numpy as np
import pandas as pd
import pytest

from nqbt import ingest
from nqbt.instruments import ContractId

CONTRACT = ContractId.parse("MNQ 03-24")

# Winter bars: 22:00 UTC is 17:00 EST, so these all sit inside Friday 2024-03-08.
LINES = [
    "20240308 213000;18000.25;18002.00;17999.50;18001.00;120",
    "20240308 213100;18001.00;18003.25;18000.75;18002.50;98",
    "20240308 213200;18002.50;18004.00;18001.25;18001.75;143",
]


def session_lines(count, start="2024-03-08 18:00"):
    """``count`` consecutive in-session minute bars, so a fixture can carry a stray legally."""
    stamps = pd.date_range(start, periods=count, freq="min")

    return [f"{ts:%Y%m%d %H%M%S};18000.25;18002.00;17999.50;18001.00;120" for ts in stamps]


def write(path, lines, trailing_newline=True):
    text = "\n".join(lines) + ("\n" if trailing_newline else "")
    path.write_text(text, encoding="utf-8")

    return path


@pytest.fixture
def export(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    return write(data_dir / "MNQ 03-24.Last.txt", LINES)


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache"


def run(export, cache, **kw):
    manifest = ingest.load_manifest(cache / "manifest.json")
    result, entry = ingest.ingest_contract(CONTRACT, export, cache_dir=cache, manifest=manifest, **kw)
    ingest.save_manifest(manifest, cache / "manifest.json")

    return result, entry


def test_parses_ohlcv_and_utc_timestamps(export, cache) -> None:
    result, _ = run(export, cache)
    assert result.action == "created"
    assert result.rows_added == 3

    frame = ingest.load_contract(CONTRACT, cache)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume", "trading_day", "in_session"]
    assert frame.index[0] == pd.Timestamp("2024-03-08 21:30:00", tz="UTC")
    assert frame["close"].iloc[-1] == pytest.approx(18001.75)
    assert frame["volume"].sum() == 361
    assert frame["volume"].dtype == np.int64


def test_attaches_session_classification(export, cache) -> None:
    run(export, cache)
    frame = ingest.load_contract(CONTRACT, cache)
    assert frame["in_session"].all()
    assert (frame["trading_day"] == pd.Timestamp("2024-03-08")).all()


def test_second_ingest_of_unchanged_file_is_a_no_op(export, cache) -> None:
    run(export, cache)
    result, _ = run(export, cache)
    assert result.action == "up-to-date"
    assert result.rows_added == 0


def test_appended_rows_are_parsed_without_rereading_the_head(export, cache) -> None:
    _, first = run(export, cache)
    extra = "20240308 213300;18001.75;18002.50;18000.00;18000.25;77"
    write(export, [*LINES, extra])

    result, entry = run(export, cache)
    assert result.action == "appended"
    assert result.rows_added == 1
    # The offset advanced past the original content rather than restarting.
    assert entry.byte_offset > first.byte_offset

    frame = ingest.load_contract(CONTRACT, cache)
    assert len(frame) == 4
    assert frame.index.is_monotonic_increasing
    assert frame["close"].iloc[-1] == pytest.approx(18000.25)


def test_partial_trailing_line_is_deferred_until_complete(export, cache) -> None:
    run(export, cache)
    # Simulate reading mid-write: the final line has no newline terminator yet.
    partial = "20240308 213300;18001.75;18002.50"
    export.write_text("\n".join(LINES) + "\n" + partial, encoding="utf-8")

    result, _ = run(export, cache)
    assert result.rows_added == 0

    # Once the writer finishes the line, it is picked up intact.
    write(export, [*LINES, "20240308 213300;18001.75;18002.50;18000.00;18000.25;77"])
    result, _ = run(export, cache)
    assert result.rows_added == 1
    assert len(ingest.load_contract(CONTRACT, cache)) == 4


def test_a_bar_exported_mid_formation_is_corrected_by_a_later_export(export, cache) -> None:
    """The failure that silently corrupted the real cache.

    Exporting during a session captures the newest bar part-formed. When it completes,
    NT8 rewrites that line with the true high/low/close/volume. Detecting an append from
    the file head alone cannot see that, so the partial bar used to be frozen forever.
    """
    partial = "20240308 213300;18001.75;18002.00;18001.50;18001.80;12"
    write(export, [*LINES, partial])
    run(export, cache)
    assert ingest.load_contract(CONTRACT, cache)["volume"].iloc[-1] == 12

    complete = "20240308 213300;18001.75;18010.00;17995.00;18008.25;884"
    write(export, [*LINES, complete, "20240308 213400;18008.25;18009.00;18007.00;18008.00;61"])
    result, _ = run(export, cache)

    frame = ingest.load_contract(CONTRACT, cache)
    bar = frame.loc[pd.Timestamp("2024-03-08 21:33:00", tz="UTC")]
    assert bar["volume"] == 884, "partial bar left stale"
    assert bar["high"] == pytest.approx(18010.00)
    # The bar after the rewritten one must survive too: the old byte offset landed
    # mid-line when the line changed length, which silently dropped it.
    assert len(frame) == 5
    assert result.action == "reparsed"


def test_a_bar_withdrawn_between_exports_is_dropped_from_the_cache(export, cache) -> None:
    """NT8 re-exports do not always contain every bar a previous export did.

    An append-only cache keeps the withdrawn bar forever as a phantom, because appending
    can add rows but never remove them.
    """
    run(export, cache)
    assert len(ingest.load_contract(CONTRACT, cache)) == 3

    write(export, [LINES[0], LINES[2]])  # the middle bar is no longer served
    result, _ = run(export, cache)

    frame = ingest.load_contract(CONTRACT, cache)
    assert len(frame) == 2, "withdrawn bar survived as a phantom"
    assert pd.Timestamp("2024-03-08 21:31:00", tz="UTC") not in frame.index
    assert result.action == "reparsed"


def test_a_rewrite_that_keeps_the_file_length_is_still_detected(export, cache) -> None:
    # Same byte count, different content: size alone cannot distinguish this.
    run(export, cache)
    swapped = [*LINES[:2], "20240308 213200;18002.50;18004.00;18001.25;18003.75;143"]
    write(export, swapped)
    assert export.stat().st_size  # unchanged length, by construction of the literal

    run(export, cache)
    frame = ingest.load_contract(CONTRACT, cache)
    assert frame["close"].iloc[-1] == pytest.approx(18003.75)


def test_a_legacy_manifest_entry_forces_a_reparse_rather_than_a_bad_append(export, cache, tmp_path) -> None:
    import json

    run(export, cache)
    path = cache / "manifest.json"
    stored = json.loads(path.read_text())
    for entry in stored.values():  # emulate a manifest from before the integrity change
        entry.pop("consumed_hash")
        entry["prefix_hash"], entry["prefix_len"] = "deadbeef", 64
    path.write_text(json.dumps(stored))

    assert ingest.load_manifest(path) == {}
    write(export, [*LINES, "20240308 213300;18001.75;18002.50;18000.00;18000.25;77"])
    result, _ = run(export, cache)
    assert result.action == "reparsed"
    assert len(ingest.load_contract(CONTRACT, cache)) == 4


def test_regenerated_export_triggers_a_full_reparse(export, cache) -> None:
    run(export, cache)
    # A re-export with a different head must not be treated as an append.
    rewritten = ["20240308 212900;17999.00;18000.50;17998.75;18000.25;55", *LINES]
    write(export, rewritten)

    result, _ = run(export, cache)
    assert result.action == "reparsed"
    assert result.rows_total == 4
    assert any("regenerated" in w for w in result.warnings)

    frame = ingest.load_contract(CONTRACT, cache)
    assert frame.index[0] == pd.Timestamp("2024-03-08 21:29:00", tz="UTC")


def test_truncated_export_triggers_a_full_reparse(export, cache) -> None:
    run(export, cache)
    write(export, LINES[:1])
    result, _ = run(export, cache)
    assert result.action == "reparsed"
    assert result.rows_total == 1
    assert any("shrank" in w for w in result.warnings)


def test_force_reparses_even_when_unchanged(export, cache) -> None:
    run(export, cache)
    result, _ = run(export, cache, force=True)
    assert result.action == "reparsed"
    assert result.rows_total == 3


def test_duplicate_timestamps_keep_the_latest_bar(cache, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    src = write(
        data_dir / "MNQ 03-24.Last.txt",
        [
            "20240308 213000;18000.25;18002.00;17999.50;18001.00;120",
            "20240308 213000;18000.25;18005.00;17999.50;18004.00;999",
        ],
    )
    run(src, cache)
    frame = ingest.load_contract(CONTRACT, cache)
    assert len(frame) == 1
    assert frame["close"].iloc[0] == pytest.approx(18004.00)


def test_out_of_session_prints_are_cached_but_not_handed_out(cache, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    src = write(
        data_dir / "MNQ 03-24.Last.txt",
        [
            *session_lines(200),
            "20240309 154400;18001.00;18001.00;18001.00;18001.00;1",  # Saturday print
        ],
    )
    result, _ = run(src, cache)
    cached = pd.read_parquet(ingest.contract_cache_path(CONTRACT, cache))
    assert len(cached) == 201  # lossless: the export can still be reconstructed
    assert int((~cached["in_session"]).sum()) == 1
    assert any("outside session hours" in w for w in result.warnings)

    assert len(ingest.load_contract(CONTRACT, cache)) == 200


def cached_frame(flags: list[bool]) -> pd.DataFrame:
    """A frame shaped like the parquet cache, flagged as ``flags`` says rather than by clock."""
    prices = np.arange(len(flags), dtype=np.float64)

    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices,
            "volume": np.ones(len(flags), dtype=np.int64),
            "trading_day": pd.Timestamp("2024-03-08"),
            "in_session": flags,
        },
        index=pd.date_range("2024-03-08 00:01", periods=len(flags), freq="min", tz="UTC", name="ts_utc"),
    )


def test_dropping_strays_renumbers_positions_and_moves_no_bar() -> None:
    """The whole point: a stray shifts every ``[n]`` behind it, and dropping it must not."""
    frame = cached_frame([False, *[True] * 200, False])
    kept = ingest.drop_out_of_session(frame, source_name=CONTRACT.nt8_name)

    assert len(kept) == 200
    assert kept.index[0] == frame.index[1]
    pd.testing.assert_frame_equal(kept, frame[frame["in_session"]])


def test_a_frame_that_is_mostly_strays_is_rejected_rather_than_filtered() -> None:
    frame = cached_frame([False] * 3 + [True] * 200)
    with pytest.raises(ingest.IngestError, match="outside session hours"):
        ingest.drop_out_of_session(frame, source_name=CONTRACT.nt8_name)


def test_a_stray_share_exactly_at_the_limit_is_still_filtered() -> None:
    at_limit = int(200 * ingest.STRAY_SHARE_LIMIT)
    frame = cached_frame([False] * at_limit + [True] * (200 - at_limit))
    assert len(ingest.drop_out_of_session(frame, source_name=CONTRACT.nt8_name)) == 200 - at_limit


def test_an_empty_frame_has_no_stray_share_to_divide_by() -> None:
    empty = cached_frame([])
    assert ingest.drop_out_of_session(empty, source_name=CONTRACT.nt8_name).empty


def test_ohlc_violations_are_rejected_loudly(cache, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    src = write(
        data_dir / "MNQ 03-24.Last.txt",
        ["20240308 213000;18000.25;17999.00;18002.00;18001.00;120"],  # high < low
    )
    with pytest.raises(ingest.IngestError, match="OHLC ordering"):
        run(src, cache)


def test_discover_exports_finds_and_parses_contract_names(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ["MNQ 03-24.Last.txt", "NQ 12-25.Last.txt", "notes.txt", "junk.Last.txt"]:
        (data_dir / name).write_text("", encoding="utf-8")

    found = ingest.discover_exports(data_dir).exports
    assert {c.nt8_name for c in found} == {"MNQ 03-24", "NQ 12-25"}

    mnq_only = ingest.discover_exports(data_dir, root="mnq").exports
    assert {c.nt8_name for c in mnq_only} == {"MNQ 03-24"}


def test_discover_exports_reports_names_it_cannot_place(tmp_path) -> None:
    """An export whose name will not parse must be reported, not silently dropped."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ["MNQ 03-24.Last.txt", "NG 02-26.Last.txt", "junk.Last.txt", "notes.txt"]:
        (data_dir / name).write_text("", encoding="utf-8")

    scan = ingest.discover_exports(data_dir)
    assert {c.nt8_name for c in scan.exports} == {"MNQ 03-24"}
    assert {skip.path.name for skip in scan.skipped} == {"NG 02-26.Last.txt", "junk.Last.txt"}

    reasons = {skip.path.name: skip.reason for skip in scan.skipped}
    assert "unknown root 'NG'" in reasons["NG 02-26.Last.txt"]
    assert "cannot parse contract name" in reasons["junk.Last.txt"]


def test_a_skipped_export_is_still_reported_when_filtered_to_one_root(tmp_path) -> None:
    """The root filter narrows what ingests; it must not narrow what is reported."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ["MNQ 03-24.Last.txt", "NQ 12-25.Last.txt", "NG 02-26.Last.txt"]:
        (data_dir / name).write_text("", encoding="utf-8")

    scan = ingest.discover_exports(data_dir, root="MNQ")
    assert {c.nt8_name for c in scan.exports} == {"MNQ 03-24"}
    assert [skip.path.name for skip in scan.skipped] == ["NG 02-26.Last.txt"]


def test_ingest_all_returns_the_files_it_skipped(export, cache) -> None:
    (export.parent / "NG 02-26.Last.txt").write_text("", encoding="utf-8")

    _, results, skipped = ingest.ingest_all(data_dir=export.parent, cache_dir=cache)

    assert [r.contract.nt8_name for r in results] == ["MNQ 03-24"]
    assert [skip.path.name for skip in skipped] == ["NG 02-26.Last.txt"]
    assert "unknown root 'NG'" in skipped[0].reason


def test_ingest_all_names_the_skipped_files_when_none_are_ingestable(tmp_path) -> None:
    """A folder of misnamed exports must not report only that it found nothing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "NG 02-26.Last.txt").write_text("", encoding="utf-8")

    with pytest.raises(ingest.IngestError, match="skipped NG 02-26.Last.txt"):
        ingest.ingest_all(data_dir=data_dir, cache_dir=tmp_path / "cache")


def test_ingest_all_reports_when_nothing_is_found(tmp_path) -> None:
    empty = tmp_path / "data"
    empty.mkdir()
    with pytest.raises(ingest.IngestError, match="no NT8 exports"):
        ingest.ingest_all(data_dir=empty, cache_dir=tmp_path / "cache")


def test_empty_export_raises_ingest_error(cache, tmp_path) -> None:
    """Ensure that an empty or whitespace-only file is rejected cleanly."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Write a file with no bar data, only an empty string.
    src = write(data_dir / "MNQ 03-24.Last.txt", [])

    with pytest.raises(ingest.IngestError, match="produced no bars"):
        run(src, cache)


def test_tick_export_is_rejected_early(cache, tmp_path) -> None:
    """Verify tick-level exports are rejected rather than parsed incorrectly.

    NinjaTrader tick files have 5 fields instead of 6, and a 3-part timestamp
    separated by spaces (Date Time Subsecond).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Tick format: yyyyMMdd HHmmss fff;last;bid;ask;volume
    tick_line = "20240308 213000 123;18000.25;18000.00;18000.50;1"
    src = write(data_dir / "MNQ 03-24.Last.txt", [tick_line])

    with pytest.raises(ingest.IngestError, match="looks like a tick export"):
        run(src, cache)


def test_unparseable_timestamps_raise_error(cache, tmp_path) -> None:
    """Ensures export files with malformed timestamps trigger a failure."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    bad_line = "Not a timestamp;18000.25;18002.00;17999.50;18001.00;120"
    src = write(data_dir / "MNQ 03-24.Last.txt", [bad_line])

    with pytest.raises(ingest.IngestError, match="no parseable timestamps"):
        run(src, cache)


def test_load_contract_raises_file_not_found_when_missing(tmp_path) -> None:
    """Loading a contract that has not been cached should abort safely."""
    with pytest.raises(FileNotFoundError, match="no cached bars for MNQ 03-24"):
        ingest.load_contract(CONTRACT, tmp_path)


def test_ingest_all_builds_archive_when_data_dir_is_none(monkeypatch, export, cache) -> None:
    """Verifies that ingest_all defaults to refreshing the archive if no data_dir is provided."""
    from unittest.mock import MagicMock

    mock_build = MagicMock(return_value=[])
    monkeypatch.setattr(ingest.archive, "build_archive", mock_build)

    # Point the archive_dir to the tmp_path containing our export fixture so it succeeds
    ingest.ingest_all(archive_dir=export.parent, cache_dir=cache, root="MNQ")

    mock_build.assert_called_once()
