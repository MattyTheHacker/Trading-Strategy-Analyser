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


def write(path, lines, *, trailing_newline=True):
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
    result, entry = ingest.ingest_contract(
        CONTRACT, export, cache_dir=cache, manifest=manifest, **kw
    )
    ingest.save_manifest(manifest, cache / "manifest.json")
    return result, entry


def test_parses_ohlcv_and_utc_timestamps(export, cache):
    result, _ = run(export, cache)
    assert result.action == "created"
    assert result.rows_added == 3

    frame = ingest.load_contract(CONTRACT, cache)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume", "trading_day", "in_session"]
    assert frame.index[0] == pd.Timestamp("2024-03-08 21:30:00", tz="UTC")
    assert frame["close"].iloc[-1] == pytest.approx(18001.75)
    assert frame["volume"].sum() == 361
    assert frame["volume"].dtype == np.int64


def test_attaches_session_classification(export, cache):
    run(export, cache)
    frame = ingest.load_contract(CONTRACT, cache)
    assert frame["in_session"].all()
    assert (frame["trading_day"] == pd.Timestamp("2024-03-08")).all()


def test_second_ingest_of_unchanged_file_is_a_no_op(export, cache):
    run(export, cache)
    result, _ = run(export, cache)
    assert result.action == "up-to-date"
    assert result.rows_added == 0


def test_appended_rows_are_parsed_without_rereading_the_head(export, cache):
    _, first = run(export, cache)
    extra = "20240308 213300;18001.75;18002.50;18000.00;18000.25;77"
    write(export, LINES + [extra])

    result, entry = run(export, cache)
    assert result.action == "appended"
    assert result.rows_added == 1
    # The offset advanced past the original content rather than restarting.
    assert entry.byte_offset > first.byte_offset

    frame = ingest.load_contract(CONTRACT, cache)
    assert len(frame) == 4
    assert frame.index.is_monotonic_increasing
    assert frame["close"].iloc[-1] == pytest.approx(18000.25)


def test_partial_trailing_line_is_deferred_until_complete(export, cache):
    run(export, cache)
    # Simulate reading mid-write: the final line has no newline terminator yet.
    partial = "20240308 213300;18001.75;18002.50"
    export.write_text("\n".join(LINES) + "\n" + partial, encoding="utf-8")

    result, _ = run(export, cache)
    assert result.rows_added == 0

    # Once the writer finishes the line, it is picked up intact.
    write(export, LINES + ["20240308 213300;18001.75;18002.50;18000.00;18000.25;77"])
    result, _ = run(export, cache)
    assert result.rows_added == 1
    assert len(ingest.load_contract(CONTRACT, cache)) == 4


def test_regenerated_export_triggers_a_full_reparse(export, cache):
    run(export, cache)
    # A re-export with a different head must not be treated as an append.
    rewritten = ["20240308 212900;17999.00;18000.50;17998.75;18000.25;55", *LINES]
    write(export, rewritten)

    result, _ = run(export, cache)
    assert result.action == "reparsed"
    assert result.rows_total == 4
    assert any("head changed" in w for w in result.warnings)

    frame = ingest.load_contract(CONTRACT, cache)
    assert frame.index[0] == pd.Timestamp("2024-03-08 21:29:00", tz="UTC")


def test_truncated_export_triggers_a_full_reparse(export, cache):
    run(export, cache)
    write(export, LINES[:1])
    result, _ = run(export, cache)
    assert result.action == "reparsed"
    assert result.rows_total == 1
    assert any("file shrank" in w for w in result.warnings)


def test_force_reparses_even_when_unchanged(export, cache):
    run(export, cache)
    result, _ = run(export, cache, force=True)
    assert result.action == "reparsed"
    assert result.rows_total == 3


def test_duplicate_timestamps_keep_the_latest_bar(cache, tmp_path):
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


def test_out_of_session_prints_are_kept_but_flagged(cache, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    src = write(
        data_dir / "MNQ 03-24.Last.txt",
        [
            *LINES,
            "20240309 154400;18001.00;18001.00;18001.00;18001.00;1",  # Saturday print
        ],
    )
    result, _ = run(src, cache)
    frame = ingest.load_contract(CONTRACT, cache)
    assert len(frame) == 4  # lossless: nothing dropped
    assert int((~frame["in_session"]).sum()) == 1
    assert any("outside session hours" in w for w in result.warnings)


def test_ohlc_violations_are_rejected_loudly(cache, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    src = write(
        data_dir / "MNQ 03-24.Last.txt",
        ["20240308 213000;18000.25;17999.00;18002.00;18001.00;120"],  # high < low
    )
    with pytest.raises(ingest.IngestError, match="OHLC ordering"):
        run(src, cache)


def test_discover_exports_finds_and_parses_contract_names(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ["MNQ 03-24.Last.txt", "NQ 12-25.Last.txt", "notes.txt", "junk.Last.txt"]:
        (data_dir / name).write_text("", encoding="utf-8")

    found = ingest.discover_exports(data_dir)
    assert {c.nt8_name for c in found} == {"MNQ 03-24", "NQ 12-25"}

    mnq_only = ingest.discover_exports(data_dir, root="mnq")
    assert {c.nt8_name for c in mnq_only} == {"MNQ 03-24"}


def test_ingest_all_reports_when_nothing_is_found(tmp_path):
    empty = tmp_path / "data"
    empty.mkdir()
    with pytest.raises(ingest.IngestError, match="no NT8 exports"):
        ingest.ingest_all(data_dir=empty, cache_dir=tmp_path / "cache")
