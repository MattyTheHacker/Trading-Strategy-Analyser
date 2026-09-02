"""The committed cache fixture, and what must keep being true of reading it.

Everything under `data/` and `cache/` is derived and uncommitted, so on a pyarrow or pandas
bump the *only* artefact that survives the upgrade is a parquet written by the previous
version. Nothing else in the suite reads one: every other test writes and reads inside the
same process, under the same version, which cannot catch a reader that has changed.

``tests/fixtures/cached_bars.parquet`` is therefore a real cache file, produced through
:func:`nqbt.ingest.ingest_contract` and kept. Regenerate it only when the cached schema itself
changes, never to make this file pass -- ``docs/roadmap.md`` § "What CI can gate on a dependency
bump".

The bars sit either side of the 2024-03-10 US DST transition and across the 17:00 ET break, so
the stored session labels are worth re-deriving: that comparison is what a tzdata bump moves.
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyarrow.parquet import ParquetFile

from nqbt import sessions

FIXTURE = Path(__file__).parent / "fixtures" / "cached_bars.parquet"

WRITTEN_BY = "parquet-cpp-arrow version 25.0.0"
"""Which pyarrow wrote the fixture. Pinned so that regenerating it cannot pass unnoticed."""

COLUMNS = ["open", "high", "low", "close", "volume", "trading_day", "in_session"]

DTYPES = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
    "trading_day": "datetime64[ms]",
    "in_session": "bool",
}
"""Resolution included deliberately: ``ms`` here and ``us`` on the index are exactly what a
pandas or pyarrow bump changes without anything else noticing."""

INDEX_NAME = "ts_utc"
INDEX_DTYPE = "datetime64[us, UTC]"
FIRST_BAR = pd.Timestamp("2024-03-08 14:00:00", tz="UTC")
LAST_BAR = pd.Timestamp("2024-03-11 22:11:00", tz="UTC")
ROWS = 48

VALUE_DIGESTS = {
    "open": "2ee3ee302e9f3f1e0880e5eeeb942945c030b1711c5e0c235f43046ac7b1dc1f",
    "high": "c61efb3723c1a7b4d2c48d62885caad7839a9558d76315d98e61abfcc5dc8a59",
    "low": "37e46e727d255eccf58ef981222690698e2fd862130bd45a69f27d3c3fd4508d",
    "close": "5734ac4ec5c939fd6304acbaa5f09738668cf01d5f579667ec500f8e90fd48ce",
    "volume": "dfdd55c424ce54a03d9881749a8049293255198ba56a246aea08ab2e9eaa1c30",
}


def _digest(values) -> str:
    """Hash one column as float64, reading ``-0.0`` as ``0.0``."""
    clean = np.ascontiguousarray(np.asarray(values, dtype=np.float64) + 0.0)

    return hashlib.sha256(clean.tobytes()).hexdigest()


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return pd.read_parquet(FIXTURE)


# -- provenance ----------------------------------------------------------------


def test_the_fixture_was_written_by_the_pinned_pyarrow() -> None:
    """A fixture silently rewritten by the current version would be testing nothing."""
    assert ParquetFile(FIXTURE).metadata.created_by == WRITTEN_BY


# -- what reading it must give -------------------------------------------------


def test_the_cached_schema_reads_back_unchanged(frame) -> None:
    assert list(frame.columns) == COLUMNS
    assert {name: str(dtype) for name, dtype in frame.dtypes.items()} == DTYPES


def test_the_index_reads_back_as_a_named_utc_timestamp(frame) -> None:
    assert frame.index.name == INDEX_NAME
    assert str(frame.index.dtype) == INDEX_DTYPE
    assert frame.index[0] == FIRST_BAR
    assert frame.index[-1] == LAST_BAR
    assert len(frame) == ROWS
    assert frame.index.is_monotonic_increasing


def test_the_stored_values_read_back_unchanged(frame) -> None:
    got = {name: _digest(frame[name].to_numpy()) for name in VALUE_DIGESTS}
    assert got == VALUE_DIGESTS


def test_ohlc_ordering_survives_the_round_trip(frame) -> None:
    """Cheap, and it fails loudly if a column ever came back permuted rather than mistyped."""
    assert (frame["high"] >= frame[["open", "close"]].max(axis=1)).all()
    assert (frame["low"] <= frame[["open", "close"]].min(axis=1)).all()


# -- the timezone half ---------------------------------------------------------


def test_the_stored_session_labels_still_match_a_fresh_classification(frame) -> None:
    """The tzdata canary: stored at ingest, re-derived now, and they have to agree."""
    fresh = sessions.classify(pd.DatetimeIndex(frame.index))
    assert np.array_equal(fresh.in_session, frame["in_session"].to_numpy())
    assert np.array_equal(
        fresh.trading_day.astype("datetime64[ms]"),
        frame["trading_day"].to_numpy().astype("datetime64[ms]"),
    )


def test_the_fixture_spans_both_dst_offsets_and_the_session_break(frame) -> None:
    """What makes the check above bite. Trimming the fixture must fail here, not silently."""
    in_session = frame["in_session"]
    assert in_session.any(), "no in-session bar"
    assert not in_session.all(), "no out-of-session bar to disagree over"

    # 22:00 UTC is 17:00 EST before the transition and 18:00 EDT after it, and the 17:00-18:00
    # ET break makes those opposite answers.
    assert bool(in_session.loc[pd.Timestamp("2024-03-08 22:00", tz="UTC")])
    assert not bool(in_session.loc[pd.Timestamp("2024-03-11 22:00", tz="UTC")])


# -- the writer, not only the reader -------------------------------------------


def test_todays_writer_round_trips_the_fixture_exactly(frame, tmp_path) -> None:
    """The same call ``ingest`` and ``splice`` make, so a writer change fails here too."""
    out = tmp_path / "round_trip.parquet"
    frame.to_parquet(out, engine="pyarrow", compression="zstd", index=True)
    pd.testing.assert_frame_equal(pd.read_parquet(out), frame, check_exact=True)


def test_a_changed_value_is_caught(frame) -> None:
    """The gate must be able to fail."""
    tampered = frame.copy()
    tampered.loc[tampered.index[0], "close"] += 0.25
    got = {name: _digest(tampered[name].to_numpy()) for name in VALUE_DIGESTS}
    assert [name for name in VALUE_DIGESTS if got[name] != VALUE_DIGESTS[name]] == ["close"]
