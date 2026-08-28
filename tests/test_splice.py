"""Splicing tests against synthetic contracts with known roll behaviour."""

import pandas as pd
import pytest

from nqbt import ingest, sessions, splice
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
    front = make_frame(week, 100.0, dict(zip(week, [900, 100, 900, 100, 100], strict=True)))
    back = make_frame(week, 110.0, dict(zip(week, [100, 900, 100, 900, 900], strict=True)))

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
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300], strict=True)), bars={"2024-03-06": 1})
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900], strict=True)), bars={"2024-03-06": 1})

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
    front = make_frame(week, 100.0, dict(zip(week, [900, 10, 300], strict=True)))
    back = make_frame(week, 110.0, dict(zip(week, [100, 90, 900], strict=True)))

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


# -- roll seams ---------------------------------------------------------------


def moving_frame(prices: dict[str, float], volumes: dict[str, int]) -> pd.DataFrame:
    """A contract whose price changes day to day, so a seam carries a real move."""
    return pd.concat([make_frame([day], price, {day: volumes[day]}) for day, price in prices.items()])


def drifting_basis_frames() -> dict[ContractId, pd.DataFrame]:
    """Two contracts whose basis widens 8 -> 10 -> 22 over the three days.

    An offset measured on any bar but the last one the front contract contributes would
    therefore leave a residual at the seam.
    """
    front = moving_frame(
        {"2024-03-06": 100.0, "2024-03-07": 102.0, "2024-03-08": 104.0},
        {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100},
    )
    back = moving_frame(
        {"2024-03-06": 108.0, "2024-03-07": 112.0, "2024-03-08": 126.0},
        {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900},
    )
    return {FRONT: front, BACK: back}


def test_back_adjustment_leaves_no_contract_basis_at_the_seam() -> None:
    frames = drifting_basis_frames()
    series, _ = splice.build_continuous([FRONT, BACK], frames, back_adjust=True)
    seam = splice.roll_seams(series).iloc[0]

    # The same interval measured entirely inside the back contract, which holds no basis
    # at all. The two agree because the offset is read at exactly the bar the seam follows.
    back = frames[BACK]
    within_one_contract = back.loc[seam.name, "open"] - back.loc[seam["previous_bar"], "close"]
    assert seam["carry_over"] == pytest.approx(within_one_contract)


def test_true_range_at_a_seam_reads_across_the_roll_rather_than_resetting() -> None:
    series, _ = splice.build_continuous([FRONT, BACK], drifting_basis_frames(), back_adjust=True)
    seam = splice.roll_seams(series).iloc[0]

    # A True Range that reset at the roll would be the seam bar's own high-low range.
    bar = series.loc[seam.name]
    assert bar["high"] - bar["low"] == pytest.approx(2.0)
    assert seam["true_range"] == pytest.approx(abs(seam["carry_over"]) + 1.0)


def test_roll_seams_finds_one_bar_per_contract_handover() -> None:
    series, _ = splice.build_continuous([FRONT, BACK], two_contract_frames(), back_adjust=True)
    seams = splice.roll_seams(series)

    assert list(seams["previous_contract"]) == ["MNQ 03-24"]
    assert list(seams["contract"]) == ["MNQ 06-24"]
    assert seams.index[0] == series.index[series["contract"] == "MNQ 06-24"][0]
    # Every seam sits across a break, so the bar it reads back to is a real earlier bar.
    assert (seams["gap_minutes"] > 0).all()
    assert list(seams["previous_bar"]) == [series.index[series["contract"] == "MNQ 03-24"][-1]]


def test_a_single_contract_series_has_no_seams() -> None:
    series, _ = splice.build_continuous([FRONT], {FRONT: two_contract_frames()[FRONT]})
    seams = splice.roll_seams(series)

    assert seams.empty
    assert list(seams.columns) == splice.SEAM_COLUMNS


def test_roll_seams_rejects_a_series_that_was_never_spliced() -> None:
    with pytest.raises(splice.SpliceError, match="no contract column"):
        splice.roll_seams(make_frame(DAYS, 100.0, 900))


# -- reporting ----------------------------------------------------------------


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
        FRONT,
        BACK,
        pd.Timestamp("2024-03-08"),
        splice.METHOD_VOLUME,
        0.0,
        1.0,
        pd.DataFrame(),
    )
    # Roll 2 happens a day BEFORE Roll 1, which should trigger the monotonicity guard.
    roll2 = splice.RollDecision(
        BACK,
        LATER,
        pd.Timestamp("2024-03-07"),
        splice.METHOD_VOLUME,
        0.0,
        1.0,
        pd.DataFrame(),
    )

    with pytest.raises(splice.SpliceError, match="roll dates are out of order"):
        splice._check_roll_monotonicity([roll1, roll2])


def test_back_adjustment_warns_if_prices_drop_below_zero() -> None:
    """A back-adjusted series can go non-positive, and then only the raw one is usable.

    Real data reaches this by accumulating roll gaps over many years -- back-adjustment
    subtracts a cumulative offset, so a long enough history of downward rolls eventually
    crosses zero. The fixture manufactures the offset in one roll instead: a back contract
    priced below the front's gap makes the shift larger than the price it is applied to,
    which is the same arithmetic without simulating a decade of contracts.
    """
    days = ["2024-03-06", "2024-03-07", "2024-03-08"]

    # A genuine volume crossover, so detect_roll picks the roll rather than falling back.
    front_vols = {"2024-03-06": 900, "2024-03-07": 800, "2024-03-08": 100}
    back_vols = {"2024-03-06": 100, "2024-03-07": 200, "2024-03-08": 900}

    # Offset = 100 - (-5) = 105, so the front's 100 shifts to -5.
    front = make_frame(days, 100.0, front_vols)
    back = make_frame(days, -5.0, back_vols)

    _, report = splice.build_continuous([FRONT, BACK], {FRONT: front, BACK: back}, back_adjust=True)

    assert any("drove prices to or below zero" in w for w in report.warnings)


def test_a_contract_squeezed_to_no_bars_is_reported_not_silently_dropped(monkeypatch) -> None:
    """A contract consumed by its neighbouring rolls must warn, not vanish.

    ``detect_roll`` cannot currently produce this state -- it needs shared in-session bars
    to pick a roll at all -- so the rolls are supplied directly. That is the point rather
    than a limitation: the warning guards against a future roll rule that *can* produce it,
    and a contract disappearing from a spliced series without a word is the failure it
    exists to prevent. Delete the guard and this test is what notices.
    """
    days = ["2024-03-06", "2024-03-07", "2024-03-08"]
    front = make_frame(days, 100.0, 900)

    # The BACK contract only has data on 03-08, which both rolls then claim.
    back = make_frame(["2024-03-08"], 110.0, 900)
    later = make_frame(days, 120.0, 900)

    roll1 = splice.RollDecision(
        FRONT,
        BACK,
        pd.Timestamp("2024-03-07"),
        splice.METHOD_VOLUME,
        0.0,
        1.0,
        pd.DataFrame(),
    )
    roll2 = splice.RollDecision(
        BACK,
        LATER,
        pd.Timestamp("2024-03-08"),
        splice.METHOD_VOLUME,
        0.0,
        1.0,
        pd.DataFrame(),
    )

    def mock_detect_roll(f_id, b_id, *args, **kwargs):
        if f_id == FRONT and b_id == BACK:
            return roll1
        return roll2

    monkeypatch.setattr(splice, "detect_roll", mock_detect_roll)

    frames = {FRONT: front, BACK: back, LATER: later}
    series, report = splice.build_continuous([FRONT, BACK, LATER], frames)

    assert any("contributes no bars" in w for w in report.warnings)
    assert "MNQ 06-24" not in series["contract"].to_numpy()


def test_splice_root_reports_an_export_it_could_not_place(tmp_path) -> None:
    """A misnamed file in the archive must reach the report, not vanish from the splice."""
    data_dir, cache_dir = tmp_path / "archive", tmp_path / "cache"
    data_dir.mkdir()
    for contract, frame in two_contract_frames().items():
        (data_dir / f"{contract.nt8_name}.Last.txt").write_text("", encoding="utf-8")
        path = ingest.contract_cache_path(contract, cache_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, engine="pyarrow", index=True)
    (data_dir / "NG 02-26.Last.txt").write_text("", encoding="utf-8")

    _, report = splice.splice_root("MNQ", data_dir=data_dir, cache_dir=cache_dir, write=False)

    assert list(report.segments["contract"]) == ["MNQ 03-24", "MNQ 06-24"]
    assert any("skipped NG 02-26.Last.txt" in w for w in report.warnings)
