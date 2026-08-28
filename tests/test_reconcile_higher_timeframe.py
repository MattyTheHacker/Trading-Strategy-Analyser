"""Tests for the probe comparison tool, which is code and can therefore be wrong.

The tool exists to decide whether NinjaTrader agrees with `nqbt.higher_timeframe`. A tool that
reports agreement whatever it is given would settle nothing, so every check below is exercised
twice: once against a synthetic export that agrees exactly, and once against the same export
perturbed in the one way that check exists to catch.

The perturbation for the projection check is **the other candidate rule** -- each fine bar
reading the coarse bar before the one it closes alongside. That is the reading a real NT8
export would show if nqbt has the boundary backwards, so it is what the tool must catch.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nqbt import higher_timeframe, indicators, resample, sessions
from tools import reconcile_higher_timeframe as rht

COARSE_MINUTES = 60
SHORT, LONG = 3, 50
FIRST_OPEN = "2024-01-07 23:01"


def minute_bars(days: int = 4, seed: int = 7) -> pd.DataFrame:
    """1-minute bars from the first bar of an ETH session, long enough for an hourly EMA(50)."""
    rng = np.random.default_rng(seed)
    index = pd.date_range(FIRST_OPEN, periods=days * 24 * 60, freq="min", tz="UTC")
    n = index.size
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


def agreeing_export(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A probe export in which NinjaTrader agrees with nqbt on all four questions."""
    coarse = resample.resample(bars, COARSE_MINUTES)
    stamps = pd.DatetimeIndex(bars.index)
    reads = rht.nqbt_reads(pd.DatetimeIndex(coarse.index), stamps)

    closes = coarse["close"].to_numpy(np.float64)
    at_coarse = {
        f"coarse_{kind}_{label}": pd.Series(fn(closes, period), index=coarse.index)
        for kind, fn in (("ema", indicators.nt8_ema), ("sma", indicators.nt8_sma))
        for label, period in (("short", SHORT), ("long", LONG))
    }

    primary = pd.DataFrame(index=stamps)
    primary["bar"] = np.arange(len(bars))
    primary["coarse_utc"] = reads
    # -1 exactly where no coarse bar has closed yet, which is what the probe writes.
    ordinal = pd.Series(np.arange(len(coarse)), index=coarse.index).reindex(stamps).ffill()
    primary["coarse_bar"] = ordinal.fillna(rht.NO_COARSE_BAR).astype(int)
    for column, values in at_coarse.items():
        primary[column] = values.reindex(stamps).ffill()
    primary.loc[reads.isna(), list(at_coarse)] = np.nan
    return primary, coarse


@pytest.fixture
def export():
    bars = minute_bars()
    primary, coarse = agreeing_export(bars)
    return bars, primary, coarse


# -- the checks pass on an export that agrees ---------------------------------


def test_every_check_agrees_on_an_export_that_matches(export) -> None:
    bars, primary, coarse = export

    assert rht.check_anchoring(coarse, bars, COARSE_MINUTES)
    assert rht.check_seeding(coarse, primary, {"short": SHORT, "long": LONG})
    assert rht.check_projection(primary, coarse)
    assert rht.check_warmup(primary, bars, higher_timeframe.key(COARSE_MINUTES, LONG))


def test_the_resolution_and_periods_are_recovered_from_the_export(export) -> None:
    _, primary, coarse = export

    assert rht.infer_coarse_minutes(pd.DatetimeIndex(coarse.index)) == COARSE_MINUTES
    assert rht.infer_periods(primary, coarse) == {"short": SHORT, "long": LONG}


# -- and fail on the one difference each exists to catch ----------------------


def test_the_projection_check_catches_the_other_candidate_rule(export) -> None:
    _, primary, coarse = export

    # Rule B: read the coarse bar strictly before this one, not the one closing alongside it.
    lagged = primary.copy()
    lagged["coarse_utc"] = rht.nqbt_reads(
        pd.DatetimeIndex(coarse.index),
        pd.DatetimeIndex(primary.index) - pd.Timedelta(minutes=1),
    ).to_numpy()

    assert not rht.check_projection(lagged, coarse)


def test_the_projection_check_refuses_a_run_that_cannot_discriminate(export) -> None:
    _, primary, coarse = export

    # No primary bar closes alongside a coarse one, so neither rule could be distinguished.
    shifted = coarse.copy()
    shifted.index = coarse.index + pd.Timedelta(seconds=30)

    assert not rht.check_projection(primary, shifted)


def test_the_anchoring_check_catches_a_moved_bucket(export) -> None:
    bars, _, coarse = export

    moved = coarse.copy()
    moved.iloc[5, moved.columns.get_loc("high")] += 0.25

    assert not rht.check_anchoring(moved, bars, COARSE_MINUTES)


def test_the_anchoring_check_catches_a_bucket_that_only_one_side_has(export) -> None:
    bars, _, coarse = export

    assert not rht.check_anchoring(coarse.iloc[:-3], bars, COARSE_MINUTES)


def test_the_seeding_check_catches_a_differently_seeded_average(export) -> None:
    _, primary, coarse = export

    reseeded = primary.copy()
    reseeded["coarse_ema_long"] = reseeded["coarse_ema_long"] + 0.5

    assert not rht.check_seeding(coarse, reseeded, {"short": SHORT, "long": LONG})


def test_the_warmup_check_catches_a_different_number_of_unreadable_bars(export) -> None:
    bars, primary, _ = export

    late = primary.copy()
    late.iloc[:120, late.columns.get_loc("coarse_bar")] = rht.NO_COARSE_BAR

    assert not rht.check_warmup(late, bars, higher_timeframe.key(COARSE_MINUTES, LONG))


# -- the export parses, warm-up rows included ---------------------------------


def test_a_written_export_round_trips_including_its_empty_warm_up_rows(tmp_path, export) -> None:
    _, primary, coarse = export
    stem = tmp_path / "MNQ-03-24_60min_20240107_20240111"
    write_probe_csv(primary, stem.with_name(stem.name + "_primary.csv"), coarse_columns=True)
    write_probe_csv(coarse, stem.with_name(stem.name + "_coarse.csv"), coarse_columns=False)

    read_primary, read_coarse = rht.read_probe(stem.with_name(stem.name + "_primary.csv"))

    assert len(read_primary) == len(primary)
    assert len(read_coarse) == len(coarse)
    # The leading rows carry no coarse bar, and must come back as NaT rather than as a date.
    assert read_primary["coarse_utc"].isna().sum() == primary["coarse_utc"].isna().sum()
    assert read_primary["coarse_utc"].notna().any()


def test_a_missing_coarse_half_is_refused_rather_than_half_checked(tmp_path, export) -> None:
    _, primary, _ = export
    path = tmp_path / "MNQ-03-24_60min_20240107_20240111_primary.csv"
    write_probe_csv(primary, path, coarse_columns=True)

    with pytest.raises(FileNotFoundError, match="no coarse export beside"):
        rht.read_probe(path)


def write_probe_csv(frame: pd.DataFrame, path: Path, *, coarse_columns: bool) -> None:
    """Write a frame in the probe's own format: semicolons, and NT8's compact timestamps."""
    out = frame.copy()
    out.insert(0, "utc", pd.DatetimeIndex(out.index).strftime("%Y%m%d %H%M%S"))
    if coarse_columns:
        stamps = pd.DatetimeIndex(out["coarse_utc"])
        out["coarse_utc"] = np.where(stamps.isna(), "", stamps.strftime("%Y%m%d %H%M%S"))
    out.to_csv(path, sep=";", index=False)
