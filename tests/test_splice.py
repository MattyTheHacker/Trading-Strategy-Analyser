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


def test_volume_crossover_is_detected_when_the_export_covers_it():
    front = make_frame(DAYS, 100.0, {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100})
    back = make_frame(DAYS, 110.0, {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900})

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_VOLUME
    assert roll.roll_day == pd.Timestamp("2024-03-08")
    assert roll.crossover_observed


def test_confirmation_skips_a_one_day_blip_and_finds_the_real_roll():
    # Back leads on 03-05, falls behind again on 03-06, then leads for good from 03-07.
    week = ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 100, 900, 100, 100])))
    back = make_frame(week, 110.0, dict(zip(week, [100, 900, 100, 900, 900])))

    lenient = splice.detect_roll(FRONT, BACK, front, back, confirm_sessions=1)
    assert lenient.roll_day == pd.Timestamp("2024-03-05")

    strict = splice.detect_roll(FRONT, BACK, front, back, confirm_sessions=2)
    assert strict.method == splice.METHOD_VOLUME
    assert strict.roll_day == pd.Timestamp("2024-03-07")


def test_volume_is_compared_over_shared_bars_only():
    # The real failure mode: the front export stops mid-session on the last day, so its
    # daily total collapses. A calendar comparison would call that a crossover; a
    # bar-aligned one correctly does not.
    front = make_frame(
        DAYS, 100.0, {d: 900 for d in DAYS}, bars={"2024-03-08": 2}
    )
    back = make_frame(DAYS, 110.0, {d: 300 for d in DAYS})

    table = splice.overlap_volume(front, back)
    assert not table["back_wins"].any()
    assert table.loc[pd.Timestamp("2024-03-08"), "shared_bars"] == 2


def test_a_stub_session_cannot_decide_the_roll():
    # Both contracts are near-empty on 03-06 -- NT8's data has exactly this hole a few
    # days before most rolls. Restricting to shared bars does not help here, because both
    # sides are short; the ratio is an hour of overnight trade standing in for a session.
    # MNQ 03-23 -> 06-23 read 1.46 on such a stub and rolled a day early.
    week = ["2024-03-05", "2024-03-06", "2024-03-07"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300])), bars={"2024-03-06": 1})
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900])), bars={"2024-03-06": 1})

    table = splice.overlap_volume(front, back)
    assert table.loc[pd.Timestamp("2024-03-06"), "back_wins"]
    assert not table.loc[pd.Timestamp("2024-03-06"), "conclusive"]

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_VOLUME
    assert roll.roll_day == pd.Timestamp("2024-03-07")


def test_a_full_session_still_decides_the_roll_on_its_first_win():
    # The guard must not cost a legitimate same-day crossover: identical to the case
    # above except that the deciding session is a full one.
    week = ["2024-03-05", "2024-03-06", "2024-03-07"]
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300])))
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900])))

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.roll_day == pd.Timestamp("2024-03-06")


def test_rolls_at_the_coverage_boundary_when_the_crossover_is_missing():
    front = make_frame(DAYS, 100.0, {d: 900 for d in DAYS}, bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, {d: 300 for d in DAYS})

    roll = splice.detect_roll(FRONT, BACK, front, back)
    assert roll.method == splice.METHOD_COVERAGE
    assert roll.roll_day == pd.Timestamp("2024-03-08")
    assert not roll.crossover_observed
    assert any("no volume crossover" in n for n in roll.notes)


def test_strict_mode_refuses_to_guess():
    front = make_frame(DAYS, 100.0, {d: 900 for d in DAYS}, bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, {d: 300 for d in DAYS})

    with pytest.raises(splice.SpliceError, match="Supply history"):
        splice.detect_roll(FRONT, BACK, front, back, allow_coverage_boundary=False)


def test_non_overlapping_contracts_are_rejected():
    front = make_frame(["2024-03-06"], 100.0, 900)
    back = make_frame(["2024-06-06"], 110.0, 900)
    with pytest.raises(splice.SpliceError, match="share no in-session bars"):
        splice.detect_roll(FRONT, BACK, front, back)


# -- continuous series --------------------------------------------------------


def two_contract_frames():
    front = make_frame(DAYS, 100.0, {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100})
    back = make_frame(DAYS, 110.0, {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900})
    return {FRONT: front, BACK: back}


def test_segments_are_disjoint_and_the_index_stays_clean():
    frames = two_contract_frames()
    series, report = splice.build_continuous([FRONT, BACK], frames)

    assert series.index.is_monotonic_increasing
    assert series.index.is_unique
    assert list(report.segments["contract"]) == ["MNQ 03-24", "MNQ 06-24"]
    # The roll day belongs entirely to the back contract.
    roll_day_rows = series[series["trading_day"] == pd.Timestamp("2024-03-08")]
    assert set(roll_day_rows["contract"]) == {"MNQ 06-24"}


def test_raw_series_keeps_the_contract_gap():
    series, _ = splice.build_continuous([FRONT, BACK], two_contract_frames())
    assert series[series["contract"] == "MNQ 03-24"]["close"].iloc[0] == pytest.approx(100.0)
    assert series[series["contract"] == "MNQ 06-24"]["close"].iloc[0] == pytest.approx(110.0)


def test_back_adjustment_lifts_history_onto_the_current_contract():
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


def test_back_adjustment_preserves_real_price_movement_across_the_roll():
    # Both contracts are flat here, so a correct adjustment leaves no jump at all.
    frames = two_contract_frames()
    series, _ = splice.build_continuous([FRONT, BACK], frames, back_adjust=True)
    boundary = series.index[series["contract"] != series["contract"].shift()][1]
    i = series.index.get_loc(boundary)
    assert series["close"].iloc[i] - series["close"].iloc[i - 1] == pytest.approx(0.0)


def test_shifts_accumulate_across_multiple_rolls():
    days2 = ["2024-06-05", "2024-06-06", "2024-06-07"]
    frames = two_contract_frames()
    frames[BACK] = pd.concat(
        [
            frames[BACK],
            make_frame(days2, 110.0, {"2024-06-05": 900, "2024-06-06": 800, "2024-06-07": 100}),
        ]
    )
    frames[LATER] = make_frame(
        days2, 125.0, {"2024-06-05": 100, "2024-06-06": 200, "2024-06-07": 900}
    )

    _, report = splice.build_continuous([FRONT, BACK, LATER], frames, back_adjust=True)
    # Offsets: 100-110 = -10, then 110-125 = -15. Oldest segment carries both.
    assert list(report.segments["shift"]) == pytest.approx([25.0, 15.0, 0.0])


def test_report_stays_quiet_about_a_healthy_coverage_roll():
    # Front winds down to 100 while the back runs 300 across a full session; over the two
    # shared bars that is 60 vs 100, a ratio of 0.6 -- the back contract is clearly
    # taking over, so the roll needs no warning even though no crossover was observed.
    front = make_frame(
        DAYS, 100.0, {"2024-03-06": 900, "2024-03-07": 900, "2024-03-08": 100},
        bars={"2024-03-08": 2},
    )
    back = make_frame(DAYS, 110.0, {d: 300 for d in DAYS})
    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back})

    assert not report.all_crossovers_observed  # coverage boundary, as expected
    assert report.rolls[0].handover_ratio == pytest.approx(0.6)
    assert not report.rolls[0].looks_early
    assert report.early_rolls == []
    assert report.warnings == []


def test_report_flags_a_roll_that_fires_while_the_front_still_dominates():
    # Front is still doing 900 against the back's 60 over shared bars: ratio 0.067. The
    # data ran out long before the market rolled, and that is worth surfacing.
    front = make_frame(DAYS, 100.0, {d: 900 for d in DAYS}, bars={"2024-03-08": 2})
    back = make_frame(DAYS, 110.0, {d: 300 for d in DAYS})
    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back})

    assert report.rolls[0].looks_early
    assert len(report.early_rolls) == 1
    assert any("verify this handover" in w for w in report.warnings)
    assert "verify this handover" in report.summary()


def test_single_contract_needs_no_roll():
    frames = {FRONT: make_frame(DAYS, 100.0, 900)}
    series, report = splice.build_continuous([FRONT], frames)
    assert report.rolls == []
    assert len(series) == len(DAYS) * BARS_PER_DAY
    assert set(series["contract"]) == {"MNQ 03-24"}


def test_out_of_session_bars_never_reach_the_continuous_series():
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
