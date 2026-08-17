"""Splicing tests against synthetic contracts with known roll behaviour."""

import pandas as pd
import pytest

from nqbt import sessions, splice
from nqbt.instruments import ContractId

FRONT = ContractId.parse("MNQ 03-24")
BACK = ContractId.parse("MNQ 06-24")
LATER = ContractId.parse("MNQ 09-24")

BARS_PER_DAY = 10


def make_frame(
    days: list[str],
    price: float,
    volume: int | dict[str, int],
    bars: int | dict[str, int] = BARS_PER_DAY,
) -> pd.DataFrame:
    """Build a contract frame whose sessions open at 18:01 ET the previous evening."""
    stamps, rows = [], []
    for day in days:
        n = bars.get(day, BARS_PER_DAY) if isinstance(bars, dict) else bars
        vol = volume.get(day, 0) if isinstance(volume, dict) else volume
        start = pd.Timestamp(day, tz=sessions.EASTERN) - pd.Timedelta(hours=6)  # 18:00 prev day
        for i in range(n):
            stamps.append((start + pd.Timedelta(minutes=i + 1)).tz_convert("UTC"))
            rows.append((price, price + 1.0, price - 1.0, price, vol // max(n, 1)))

    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    frame.index = pd.DatetimeIndex(stamps, name="ts_utc")
    frame = frame.sort_index()
    info = sessions.classify(frame.index)
    frame["trading_day"] = info.trading_day
    frame["in_session"] = info.in_session
    return frame


DAYS = ["2024-03-06", "2024-03-07", "2024-03-08"]


def test_volume_crossover_is_detected_when_the_export_covers_it() -> None:
    front = make_frame(DAYS, 100.0, {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100})
    back = make_frame(DAYS, 110.0, {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900})

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_VOLUME
    assert roll.roll_day == pd.Timestamp("2024-03-08")
    assert roll.crossover_observed


def test_confirmation_skips_a_one_day_blip_and_finds_the_real_roll() -> None:
    # Back leads on 03-05, falls behind again on 03-06, then leads for good from 03-07.
    week = ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 100, 900, 100, 100], strict=False)))
    back = make_frame(week, 110.0, dict(zip(week, [100, 900, 100, 900, 900], strict=False)))

    lenient = splice.detect_roll(FRONT, BACK, front, back, confirm_sessions=1)
    assert lenient.roll_day == pd.Timestamp("2024-03-05")

    strict = splice.detect_roll(FRONT, BACK, front, back, confirm_sessions=2)
    assert strict.method == splice.METHOD_VOLUME
    assert strict.roll_day == pd.Timestamp("2024-03-07")


def test_volume_is_compared_over_shared_bars_only() -> None:
    # The real failure mode: the front export stops mid-session on the last day, so its
    # daily total collapses. A calendar comparison would call that a crossover; a
    # bar-aligned one correctly does not.
    front = make_frame(DAYS, 100.0, dict.fromkeys(DAYS, 900), bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, dict.fromkeys(DAYS, 300))

    table = splice.overlap_volume(front, back)
    assert not table["back_wins"].any()
    assert table.loc[pd.Timestamp("2024-03-08"), "shared_bars"] == 2


def test_a_stub_session_cannot_decide_the_roll() -> None:
    # Both contracts are near-empty on 03-06 -- NT8's data has exactly this hole a few
    # days before most rolls. Restricting to shared bars does not help here, because both
    # sides are short; the ratio is an hour of overnight trade standing in for a session.
    # MNQ 03-23 -> 06-23 read 1.46 on such a stub and rolled a day early.
    week = ["2024-03-05", "2024-03-06", "2024-03-07"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300], strict=False)), bars={"2024-03-06": 1})
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900], strict=False)), bars={"2024-03-06": 1})

    table = splice.overlap_volume(front, back)
    assert table.loc[pd.Timestamp("2024-03-06"), "back_wins"]
    assert not table.loc[pd.Timestamp("2024-03-06"), "conclusive"]

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_VOLUME
    assert roll.roll_day == pd.Timestamp("2024-03-07")


def test_a_full_session_still_decides_the_roll_on_its_first_win() -> None:
    # The guard must not cost a legitimate same-day crossover: identical to the case
    # above except that the deciding session is a full one.
    week = ["2024-03-05", "2024-03-06", "2024-03-07"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300], strict=False)))
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900], strict=False)))

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.roll_day == pd.Timestamp("2024-03-06")


def test_rolls_at_the_coverage_boundary_when_the_crossover_is_missing() -> None:
    front = make_frame(DAYS, 100.0, dict.fromkeys(DAYS, 900), bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, dict.fromkeys(DAYS, 300))

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_COVERAGE
    assert roll.roll_day == pd.Timestamp("2024-03-08")
    assert not roll.crossover_observed
    assert any("no volume crossover" in n for n in roll.notes)


def test_strict_mode_refuses_to_guess() -> None:
    front = make_frame(DAYS, 100.0, dict.fromkeys(DAYS, 900), bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, dict.fromkeys(DAYS, 300))

    with pytest.raises(splice.SpliceError, match="Supply history"):
        splice.detect_roll(FRONT, BACK, front, back, allow_coverage_boundary=False)


def test_non_overlapping_contracts_are_rejected() -> None:
    front = make_frame(["2024-03-06"], 100.0, 900)
    back = make_frame(["2024-06-06"], 110.0, 900)
    with pytest.raises(splice.SpliceError, match="share no in-session bars"):
        splice.detect_roll(FRONT, BACK, front, back)


# -- continuous series --------------------------------------------------------


def two_contract_frames():
    front = make_frame(DAYS, 100.0, {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100})
    back = make_frame(DAYS, 110.0, {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900})
    return {FRONT: front, BACK: back}


def test_segments_are_disjoint_and_the_index_stays_clean() -> None:
    frames = two_contract_frames()
    series, report = splice.build_continuous([FRONT, BACK], frames)

    assert series.index.is_monotonic_increasing
    assert series.index.is_unique
    assert list(report.segments["contract"]) == ["MNQ 03-24", "MNQ 06-24"]
    # The roll day belongs entirely to the back contract.
    roll_day_rows = series[series["trading_day"] == pd.Timestamp("2024-03-08")]
    assert set(roll_day_rows["contract"]) == {"MNQ 06-24"}


def test_raw_series_keeps_the_contract_gap() -> None:
    series, _ = splice.build_continuous([FRONT, BACK], two_contract_frames())
    assert series[series["contract"] == "MNQ 03-24"]["close"].iloc[0] == pytest.approx(100.0)
    assert series[series["contract"] == "MNQ 06-24"]["close"].iloc[0] == pytest.approx(110.0)


def test_back_adjustment_lifts_history_onto_the_current_contract() -> None:
    frames = two_contract_frames()
    series, report = splice.build_continuous([FRONT, BACK], frames, back_adjust=True)

    # Offset = front_close - back_close = 100 - 110 = -10, so history shifts up by 10.
    assert report.rolls[0].offset == pytest.approx(-10.0)
    assert list(report.segments["shift"]) == pytest.approx([10.0, 0.0])

    front_rows = series[series["contract"] == "MNQ 03-24"]
    assert front_rows["close"].iloc[0] == pytest.approx(110.0)
    # The newest contract is never shifted -- its prices stay real.
    back_rows = series[series["contract"] == "MNQ 06-24"]
    assert back_rows["close"].iloc[0] == pytest.approx(110.0)


def test_back_adjustment_preserves_real_price_movement_across_the_roll() -> None:
    # Both contracts are flat here, so a correct adjustment leaves no jump at all.
    frames = two_contract_frames()
    series, _ = splice.build_continuous([FRONT, BACK], frames, back_adjust=True)
    boundary = series.index[series["contract"] != series["contract"].shift()][1]
    i = series.index.get_loc(boundary)
    assert series["close"].iloc[i] - series["close"].iloc[i - 1] == pytest.approx(0.0)


def test_shifts_accumulate_across_multiple_rolls() -> None:
    days2 = ["2024-06-05", "2024-06-06", "2024-06-07"]
    frames = two_contract_frames()
    frames[BACK] = pd.concat(
        [
            frames[BACK],
            make_frame(days2, 110.0, {"2024-06-05": 900, "2024-06-06": 800, "2024-06-07": 100}),
        ],
    )
    frames[LATER] = make_frame(days2, 125.0, {"2024-06-05": 100, "2024-06-06": 200, "2024-06-07": 900})

    _, report = splice.build_continuous([FRONT, BACK, LATER], frames, back_adjust=True)
    # Offsets: 100-110 = -10, then 110-125 = -15. Oldest segment carries both.
    assert list(report.segments["shift"]) == pytest.approx([25.0, 15.0, 0.0])


def test_report_stays_quiet_about_a_healthy_coverage_roll() -> None:
    # Front winds down to 100 while the back runs 300 across a full session; over the two
    # shared bars that is 60 vs 100, a ratio of 0.6 -- the back contract is clearly
    # taking over, so the roll needs no warning even though no crossover was observed.
    front = make_frame(
        DAYS,
        100.0,
        {"2024-03-06": 900, "2024-03-07": 900, "2024-03-08": 100},
        bars={"2024-03-08": 2},
    )
    back = make_frame(DAYS, 110.0, dict.fromkeys(DAYS, 300))
    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back})

    assert not report.all_crossovers_observed  # coverage boundary, as expected
    assert report.rolls[0].handover_ratio == pytest.approx(0.6)
    assert not report.rolls[0].looks_early
    assert report.early_rolls == []
    assert report.warnings == []


def test_report_flags_a_roll_that_fires_while_the_front_still_dominates() -> None:
    # Front is still doing 900 against the back's 60 over shared bars: ratio 0.067. The
    # data ran out long before the market rolled, and that is worth surfacing.
    front = make_frame(DAYS, 100.0, dict.fromkeys(DAYS, 900), bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, dict.fromkeys(DAYS, 300))
    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back})

    assert report.rolls[0].looks_early
    assert len(report.early_rolls) == 1
    assert any("verify this handover" in w for w in report.warnings)
    assert "verify this handover" in report.summary()


def test_single_contract_needs_no_roll() -> None:
    frames = {FRONT: make_frame(DAYS, 100.0, 900)}
    series, report = splice.build_continuous([FRONT], frames)
    assert report.rolls == []
    assert len(series) == len(DAYS) * BARS_PER_DAY
    assert set(series["contract"]) == {"MNQ 03-24"}


def test_out_of_session_bars_never_reach_the_continuous_series() -> None:
    frames = two_contract_frames()
    stray = frames[FRONT].iloc[[0]].copy()
    stray.index = pd.DatetimeIndex([pd.Timestamp("2024-03-09 15:44:00", tz="UTC")], name="ts_utc")
    info = sessions.classify(stray.index)
    stray["trading_day"] = info.trading_day
    stray["in_session"] = info.in_session
    assert not stray["in_session"].iloc[0]

    frames[FRONT] = pd.concat([frames[FRONT], stray]).sort_index()
    series, _ = splice.build_continuous([FRONT, BACK], frames)
    assert pd.Timestamp("2024-03-09 15:44:00", tz="UTC") not in series.index
    assert "in_session" not in series.columns


def test_load_continuous_raises_file_not_found_when_missing(tmp_path) -> None:
    """Ensures load_continuous aborts clearly if the parquet file does not exist."""
    with pytest.raises(FileNotFoundError, match="no continuous series for MNQ"):
        # tmp_path is an empty temporary directory provided by pytest,
        # guaranteeing the file will not be present.
        splice.load_continuous("MNQ", cache_dir=tmp_path)


def test_boundary_offset_raises_if_no_prior_shared_bars() -> None:
    """Verifies failure when a roll is found but there is no previous bar to measure the price offset."""
    day1, day2 = ["2024-03-06"], ["2024-03-07"]

    # Front has a full session on Day 1, and a tiny stub on Day 2.
    front = pd.concat([make_frame(day1, 100.0, 900), make_frame(day2, 100.0, 10, bars=1)])
    # Back has NO data on Day 1, and a full session on Day 2.
    back = make_frame(day2, 110.0, 900)

    # The coverage fallback will pick Day 2 for the roll, but `_boundary_offset`
    # won't find any shared bars on Day 1 to calculate the gap.
    with pytest.raises(splice.SpliceError, match="no shared bar before"):
        splice.detect_roll(FRONT, BACK, front, back)


def test_build_continuous_requires_at_least_one_contract() -> None:
    """Ensure the continuous builder rejects an empty contract list."""
    with pytest.raises(splice.SpliceError, match="need at least one contract"):
        splice.build_continuous([], {})


def test_check_roll_monotonicity_raises_on_out_of_order_rolls() -> None:
    """Verifies the splicer aborts if roll dates regress chronologically."""
    roll1 = splice.RollDecision(
        FRONT, BACK, pd.Timestamp("2024-03-08"), splice.METHOD_VOLUME, 0.0, 1.0, pd.DataFrame()
    )
    # Roll 2 happens a day BEFORE Roll 1, which should trigger the monotonicity guard.
    roll2 = splice.RollDecision(
        BACK, LATER, pd.Timestamp("2024-03-07"), splice.METHOD_VOLUME, 0.0, 1.0, pd.DataFrame()
    )

    with pytest.raises(splice.SpliceError, match="roll dates are out of order"):
        splice._check_roll_monotonicity([roll1, roll2])


def test_back_adjustment_warns_if_prices_drop_below_zero() -> None:
    """Ensure a warning is surfaced if large roll gaps push historical prices negative."""
    days = ["2024-03-06", "2024-03-07", "2024-03-08"]

    # We must create a valid volume crossover so detect_roll succeeds naturally.
    front_vols = {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100}
    back_vols = {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900}

    # Front trades around 100. Back trades around -5.
    # Offset = 100 - (-5) = 105. Back-adjusting will shift the Front prices by -105.
    front = make_frame(days, 100.0, front_vols)
    back = make_frame(days, -5.0, back_vols)

    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back}, back_adjust=True)

    assert any("drove prices to or below zero" in w for w in report.warnings)


def test_segment_fully_consumed_by_surrounding_rolls_emits_warning(monkeypatch) -> None:
    """Tests the edge case where a contract's valid window is squeezed to 0 bars."""
    days = ["2024-03-06", "2024-03-07", "2024-03-08"]
    front = make_frame(days, 100.0, 900)

    # The BACK contract only has data on 03-08.
    back = make_frame(["2024-03-08"], 110.0, 900)
    later = make_frame(days, 120.0, 900)

    # The defensive warning in build_continuous is mathematically unreachable
    # with real data because detect_roll requires shared in-session bars to pick a roll.
    # We use monkeypatch to safely simulate the edge case and bypass the monotonicity guard.
    roll1 = splice.RollDecision(
        FRONT, BACK, pd.Timestamp("2024-03-07"), splice.METHOD_VOLUME, 0.0, 1.0, pd.DataFrame()
    )
    roll2 = splice.RollDecision(
        BACK, LATER, pd.Timestamp("2024-03-08"), splice.METHOD_VOLUME, 0.0, 1.0, pd.DataFrame()
    )

    def mock_detect_roll(f_id, b_id, *args, **kwargs):
        if f_id == FRONT and b_id == BACK:
            return roll1
        return roll2

    monkeypatch.setattr(splice, "detect_roll", mock_detect_roll)

    frames = {FRONT: front, BACK: back, LATER: later}
    series, report = splice.build_continuous([FRONT, BACK, LATER], frames)

    assert any("contributes no bars" in w for w in report.warnings)
    assert "MNQ 06-24" not in series["contract"].values
