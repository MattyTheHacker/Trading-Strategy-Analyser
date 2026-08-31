"""Annotation tests: a trade log joined to the market context at its bars.

Two claims are pinned harder than the rest, because each produces plausible numbers rather than
an error. **A fill belongs to the bar stamped after it**, so every alignment test states which
bar it expects rather than that some bar was found, and the simulated case asserts that
resolving a bar index from its own timestamp would have moved it. **A back-adjusted series
annotates successfully and is wrong at every comparison**, so that test asserts the lookup
still succeeds and only the price check refuses it.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import annotate, conditions, context, ingest, regime, sessions, trade_import, trades, trend, volume
from nqbt.annotate import UNMATCHED, AnnotationError, LabelThresholds
from nqbt.context import ContextSpec
from nqbt.instruments import ContractId

BASE = 18000.0
START = "2024-01-02 15:00"

FULL_SPEC = ContextSpec(
    ma_keys=conditions.ma_keys(ema=(3,), sma=(5,)),
    atr_periods=(4,),
    needs_vwap=True,
    needs_time_of_day=True,
    regime_lookbacks=(2,),
    volume_keys=(volume.key(int(volume.VolumeForm.PER_BAR), volume.NO_ROLLING, 5),),
    trend_keys=(trend.key(2, 3, 1),),
)


def bars(n: int = 120, start: str = START) -> pd.DataFrame:
    """One-minute bars inside a session, priced so a bar's range is known from its index.

    Bar ``i`` opens at ``BASE + (i - 1) * 0.25``, closes a tick higher, and runs a point either
    side of that, so a fill inside a chosen bar can be written down rather than searched for.
    """
    index = pd.date_range(start, periods=n, freq="min", tz="UTC")
    close = BASE + np.arange(n) * 0.25
    open_ = close - 0.25
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": close + 1.0,
            "low": open_ - 1.0,
            "close": close,
            "volume": np.full(n, 100.0),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


def dataset(frame: pd.DataFrame | None = None, spec: ContextSpec = FULL_SPEC) -> context.Dataset:
    """Prepare a dataset over ``frame``, defaulting to the fixture bars and the full spec."""
    return context.prepare(bars() if frame is None else frame, spec)


def close_of(bar: int) -> float:
    """Return the close of bar ``bar`` of the fixture, which is a price inside it."""
    return BASE + bar * 0.25


def manual_log(legs: list[dict[str, object]], contract: str = "MNQ 09-26") -> pd.DataFrame:
    """Build a log the way an importer leaves one: fill times, and no bar index anywhere."""
    frame = pd.DataFrame(legs)
    frame["leg"] = frame.groupby("trade_id").cumcount() + 1
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True)
    frame["exit_time"] = pd.to_datetime(frame["exit_time"], utc=True)
    frame["contract"] = pd.Series(contract, index=frame.index, dtype="string")
    for name in ("entry_bar", "exit_bar"):
        frame[name] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    return frame


def leg(
    trade_id: int,
    entry_time: str,
    exit_time: str,
    entry_price: float,
    exit_price: float,
) -> dict[str, object]:
    """One leg of a manual log, priced explicitly. Legs are numbered in the order they arrive."""
    return {
        "trade_id": trade_id,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": entry_price,
        "exit_price": exit_price,
    }


def sim_log(
    pairs: list[tuple[int, int]],
    index: pd.DatetimeIndex,
    closes: np.ndarray | None = None,
) -> pd.DataFrame:
    """Build a log the way the simulator leaves one: bar indices, and the stamps of those bars."""
    prices = np.array([close_of(i) for i in range(len(index))]) if closes is None else closes
    return pd.DataFrame(
        {
            "trade_id": np.arange(1, len(pairs) + 1, dtype=np.int64),
            "leg": np.ones(len(pairs), dtype=np.int64),
            "entry_bar": np.array([entry for entry, _ in pairs], dtype=np.int64),
            "exit_bar": np.array([exit_ for _, exit_ in pairs], dtype=np.int64),
            "entry_time": index[[entry for entry, _ in pairs]],
            "exit_time": index[[exit_ for _, exit_ in pairs]],
            "entry_price": np.array([prices[entry] for entry, _ in pairs]),
            "exit_price": np.array([prices[exit_] for _, exit_ in pairs]),
        },
    )


# -- bar alignment ------------------------------------------------------------


def test_a_fill_inside_a_minute_belongs_to_the_bar_stamped_at_its_end() -> None:
    index = bars().index
    matched = annotate.bars_for_fills(index, pd.DatetimeIndex(["2024-01-02 15:23:47"], tz="UTC"))
    assert index[matched[0]] == pd.Timestamp("2024-01-02 15:24", tz="UTC")


def test_a_fill_on_a_whole_minute_belongs_to_the_next_bar_not_the_one_stamped_at_it() -> None:
    index = bars().index
    matched = annotate.bars_for_fills(index, pd.DatetimeIndex(["2024-01-02 15:24:00"], tz="UTC"))
    assert index[matched[0]] == pd.Timestamp("2024-01-02 15:25", tz="UTC"), (
        "a bar stamped 15:24 covers the minute ending at it, so a fill at 15:24:00 is in the next one"
    )


def test_a_fill_a_second_before_a_stamp_and_one_a_second_after_it_land_in_different_bars() -> None:
    index = bars().index
    times = pd.DatetimeIndex(["2024-01-02 15:23:59", "2024-01-02 15:24:01"], tz="UTC")
    before, after = annotate.bars_for_fills(index, times)
    assert after == before + 1


def test_a_fill_before_the_first_bar_matches_nothing() -> None:
    index = bars().index
    early = pd.DatetimeIndex(["2024-01-02 14:00:00"], tz="UTC")
    assert annotate.bars_for_fills(index, early)[0] == UNMATCHED


def test_a_fill_after_the_last_bar_matches_nothing() -> None:
    index = bars().index
    late = pd.DatetimeIndex([index[-1] + pd.Timedelta(minutes=5)])
    assert annotate.bars_for_fills(index, late)[0] == UNMATCHED


def test_a_fill_in_a_hole_in_the_bars_is_unmatched_rather_than_joined_to_the_next_one() -> None:
    frame = bars()
    without = frame.drop(index=[frame.index[40], frame.index[41]])
    inside_the_hole = pd.DatetimeIndex([frame.index[40] - pd.Timedelta(seconds=13)])
    assert annotate.bars_for_fills(without.index, inside_the_hole)[0] == UNMATCHED
    assert annotate.bars_for_fills(frame.index, inside_the_hole)[0] == 40


def test_the_bar_size_decides_how_far_back_a_bar_reaches() -> None:
    index = pd.date_range(START, periods=10, freq="5min", tz="UTC")
    fill = pd.DatetimeIndex(["2024-01-02 15:01:00"], tz="UTC")
    assert annotate.bars_for_fills(index, fill, bar_minutes=5)[0] == 1
    assert annotate.bars_for_fills(index, fill, bar_minutes=1)[0] == UNMATCHED


def test_a_naive_log_against_a_localised_index_is_refused_rather_than_compared() -> None:
    with pytest.raises(AnnotationError, match="timezone-aware and a naive"):
        annotate.bars_for_fills(bars().index, pd.DatetimeIndex(["2024-01-02 15:23:47"]))


def test_the_zone_a_fill_is_read_under_decides_which_bar_it_lands_in() -> None:
    index = bars().index
    utc = pd.DatetimeIndex(["2024-01-02 16:23:47"], tz="UTC")
    lisbon = pd.DatetimeIndex(["2024-01-02 16:23:47"], tz="Europe/Lisbon")
    berlin = pd.DatetimeIndex(["2024-01-02 16:23:47"], tz="Europe/Berlin")
    assert annotate.bars_for_fills(index, utc)[0] == annotate.bars_for_fills(index, lisbon)[0]
    assert annotate.bars_for_fills(index, berlin)[0] == annotate.bars_for_fills(index, utc)[0] - 60


def test_an_impossible_bar_size_is_refused() -> None:
    with pytest.raises(AnnotationError, match="bar_minutes"):
        annotate.bars_for_fills(bars().index, bars().index[:1], bar_minutes=0)


# -- which bar a log is annotated at ------------------------------------------


def test_a_simulated_log_is_annotated_at_its_own_bar_index_not_one_resolved_from_its_stamp() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    annotated = annotate.annotate_trades(log, data)

    assert annotated.frame["entry_bar"].tolist() == [30]
    resolved = annotate.bars_for_fills(data.index, pd.DatetimeIndex(log["entry_time"]))
    assert resolved[0] == 31, "a bar's own stamp is a fill time one bar later, which is the trap"


def test_a_manual_log_is_annotated_at_the_bar_its_fill_time_falls_in() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    annotated = annotate.annotate_trades(log, data, at_exit=True)
    assert annotated.frame["entry_bar"].tolist() == [30]
    assert annotated.frame["exit_bar"].tolist() == [34]


def test_a_bar_index_that_disagrees_with_its_own_timestamp_is_refused() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    log["entry_bar"] = np.array([31], dtype=np.int64)
    with pytest.raises(AnnotationError, match="produced over different bars"):
        annotate.annotate_trades(log, data)


def test_a_bar_index_outside_the_dataset_is_refused() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    log["exit_bar"] = np.array([len(data)], dtype=np.int64)
    with pytest.raises(AnnotationError, match="outside the dataset"):
        annotate.annotate_trades(log, data)


def test_a_log_carrying_a_bar_index_on_some_rows_only_is_refused() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                2,
                "2024-01-02 15:39:47",
                "2024-01-02 15:43:12",
                entry_price=close_of(40),
                exit_price=close_of(44),
            ),
        ],
    )
    log.loc[0, "entry_bar"] = 30
    with pytest.raises(AnnotationError, match="on every row or on none"):
        annotate.annotate_trades(log, data)


def test_a_log_carrying_bar_indices_and_no_times_at_all_is_annotated_at_them() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index).drop(columns=["entry_time", "exit_time"])
    assert annotate.annotate_trades(log, data, at_exit=True).frame["exit_bar"].tolist() == [34]


def test_a_naive_fill_time_beside_a_localised_index_is_refused_rather_than_cross_checked() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    log["entry_time"] = pd.DatetimeIndex(log["entry_time"]).tz_localize(None)
    with pytest.raises(AnnotationError, match="is not the series it is thought to be"):
        annotate.annotate_trades(log, data)


def test_a_log_with_neither_a_bar_index_nor_a_fill_time_is_refused() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    with pytest.raises(AnnotationError, match="neither entry_bar nor entry_time"):
        annotate.annotate_trades(log.drop(columns=["entry_bar", "entry_time"]), data)


# -- back-adjustment ----------------------------------------------------------


def test_every_fill_price_falls_inside_the_bar_it_was_matched_to() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    row = annotate.annotate_trades(log, data, at_exit=True).frame.iloc[0]
    assert row["entry_bar_low"] <= log["entry_price"].iloc[0] <= row["entry_bar_high"]
    assert row["exit_bar_low"] <= log["exit_price"].iloc[0] <= row["exit_bar_high"]


def test_a_fill_exactly_on_the_bars_high_is_inside_it() -> None:
    data = dataset()
    top = float(data.high[30])
    log = manual_log(
        [leg(1, "2024-01-02 15:29:47", "2024-01-02 15:33:12", entry_price=top, exit_price=close_of(34))],
    )
    assert annotate.annotate_trades(log, data).matched == 1


def test_annotating_against_a_back_adjusted_series_is_refused_rather_than_ranked() -> None:
    frame = bars()
    adjusted = frame.copy()
    adjusted[["open", "high", "low", "close"]] -= 250.0
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )

    found = annotate.bars_for_fills(adjusted.index, pd.DatetimeIndex(log["entry_time"]))
    assert found[0] == 30, "the lookup succeeds against a back-adjusted series; only the price catches it"
    with pytest.raises(AnnotationError, match="back-adjustment"):
        annotate.annotate_trades(log, dataset(adjusted))


def test_a_tick_of_tolerance_does_not_admit_a_back_adjusted_series() -> None:
    adjusted = bars()
    adjusted[["open", "high", "low", "close"]] -= 250.0
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    with pytest.raises(AnnotationError, match="points outside"):
        annotate.annotate_trades(log, dataset(adjusted), price_tolerance=0.25)


def test_a_slipped_simulated_fill_is_admitted_by_the_tolerance_it_slipped_by() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    log["entry_price"] = np.array([float(data.high[30]) + 0.25])

    with pytest.raises(AnnotationError, match="price_tolerance"):
        annotate.annotate_trades(log, data)
    assert annotate.annotate_trades(log, data, price_tolerance=0.25).matched == 1


def test_an_exit_price_outside_its_bar_is_caught_even_when_exits_are_not_annotated() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(90),
            ),
        ],
    )
    with pytest.raises(AnnotationError, match="the exit price"):
        annotate.annotate_trades(log, data, at_exit=False)


# -- one row per trade --------------------------------------------------------


def test_a_scale_out_is_one_annotation_row_spanning_its_first_entry_and_last_exit() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                1,
                "2024-01-02 15:31:47",
                "2024-01-02 15:37:12",
                entry_price=close_of(32),
                exit_price=close_of(38),
            ),
        ],
    )
    annotated = annotate.annotate_trades(log, data, at_exit=True)
    assert len(annotated.frame) == 1
    assert annotated.frame["entry_bar"].tolist() == [30]
    assert annotated.frame["exit_bar"].tolist() == [38]


def test_the_frame_is_indexed_by_trade_id_so_a_review_can_join_the_trade_log_to_it() -> None:
    data = dataset()
    annotated = annotate.annotate_trades(sim_log([(30, 34), (40, 44)], data.index), data)
    assert annotated.frame.index.name == "trade_id"
    assert annotated.frame.index.tolist() == [1, 2]


# -- what a row carries -------------------------------------------------------


def test_every_condition_the_dataset_holds_reaches_the_frame() -> None:
    data = dataset()
    annotated = annotate.annotate_trades(sim_log([(60, 64)], data.index), data)
    expected = {
        "entry_hammer",
        "entry_inverted_hammer",
        "entry_made_new_high",
        "entry_made_new_low",
        "entry_previous_bar_green",
        "entry_previous_bar_red",
        "entry_phase",
        "entry_bar_of_session",
        "entry_above_ema_3",
        "entry_above_sma_5",
        "entry_atr_4",
        "entry_vwap",
        "entry_above_vwap",
        "entry_efficiency_ratio_2",
        "entry_volume_per_bar_5",
        "entry_relative_volume_per_bar_5",
        "entry_trend_agreement_2_3_1",
        "entry_trend_2_3_1_price_vs_slow",
        "entry_trend_2_3_1_slow_slope",
        "entry_trend_2_3_1_stack",
    }
    assert expected <= set(annotated.conditions)
    assert expected <= set(annotated.frame.columns)


def test_each_condition_is_the_datasets_own_value_at_that_bar() -> None:
    data = dataset()
    row = annotate.annotate_trades(sim_log([(60, 64)], data.index), data).frame.iloc[0]
    assert row["entry_atr_4"] == pytest.approx(data.atr_values(4)[60])
    assert row["entry_vwap"] == pytest.approx(data.vwap_values()[60])
    assert bool(row["entry_above_ema_3"]) == bool(data.ma_gate("ema", 3, above=True)[60])
    assert row["entry_efficiency_ratio_2"] == pytest.approx(data.regime_values(2)[60])
    assert row["entry_bar_of_session"] == data.bar_of_session()[60]
    assert row["entry_trend_agreement_2_3_1"] == pytest.approx(data.trend_values(trend.key(2, 3, 1))[60])


def test_a_condition_the_dataset_was_not_asked_for_is_absent_rather_than_null() -> None:
    data = dataset(spec=ContextSpec(ma_keys=conditions.ma_keys(ema=(3,))))
    annotated = annotate.annotate_trades(sim_log([(60, 64)], data.index), data)
    assert "entry_above_ema_3" in annotated.conditions
    assert not [name for name in annotated.conditions if "efficiency_ratio" in name or "vwap" in name]


def test_raw_moving_average_values_travel_only_when_the_dataset_kept_them() -> None:
    spec = ContextSpec(ma_keys=conditions.ma_keys(ema=(3,)))
    without = annotate.annotate_trades(
        sim_log([(60, 64)], bars().index),
        context.prepare(bars(), spec),
    )
    with_values = annotate.annotate_trades(
        sim_log([(60, 64)], bars().index),
        context.prepare(bars(), spec, keep_ma_values=True),
    )
    assert "entry_ema_3" not in without.conditions
    assert "entry_ema_3" in with_values.conditions


def test_the_exit_side_is_absent_unless_it_is_asked_for() -> None:
    data = dataset()
    log = sim_log([(30, 34)], data.index)
    assert not [c for c in annotate.annotate_trades(log, data).frame.columns if c.startswith("exit_")]
    with_exit = annotate.annotate_trades(log, data, at_exit=True)
    assert "exit_phase" in with_exit.conditions
    assert with_exit.frame["exit_bar"].tolist() == [34]


def test_asking_for_the_exit_side_changes_what_is_emitted_and_not_which_trades_match() -> None:
    data = dataset()
    log = sim_log([(30, 34), (40, 44)], data.index)
    without = annotate.annotate_trades(log, data)
    with_exit = annotate.annotate_trades(log, data, at_exit=True)
    assert without.frame["matched"].tolist() == with_exit.frame["matched"].tolist()
    assert without.frame["entry_phase"].tolist() == with_exit.frame["entry_phase"].tolist()


# -- labels -------------------------------------------------------------------


def test_a_label_appears_only_when_its_thresholds_are_chosen() -> None:
    data = dataset()
    log = sim_log([(60, 64)], data.index)
    assert "entry_regime_2" not in annotate.annotate_trades(log, data).conditions

    labelled = annotate.annotate_trades(
        log,
        data,
        thresholds=LabelThresholds(regime_consolidating_below=0.3, regime_directional_above=0.5),
    )
    assert "entry_regime_2" in labelled.conditions


def test_a_label_is_the_name_the_module_that_defines_it_would_give_the_bar() -> None:
    data = dataset()
    thresholds = LabelThresholds(
        regime_consolidating_below=0.3,
        regime_directional_above=0.5,
        volume_thin_below=0.7,
        volume_heavy_above=1.5,
        trend_min_agreement=2,
    )
    row = annotate.annotate_trades(sim_log([(60, 64)], data.index), data, thresholds=thresholds).frame.iloc[0]
    expected = regime.Regime(data.regime_labels(2, 0.3, 0.5)[60])
    assert row["entry_regime_2"] == expected.name.lower()
    labelled = trend.Trend(data.trend_labels(trend.key(2, 3, 1), 2)[60])
    assert row["entry_trend_2_3_1"] == labelled.name.lower()


def test_a_bar_with_no_baseline_is_labelled_undefined_rather_than_normal() -> None:
    data = dataset()
    thresholds = LabelThresholds(volume_thin_below=0.7, volume_heavy_above=1.5)
    row = annotate.annotate_trades(sim_log([(60, 64)], data.index), data, thresholds=thresholds).frame.iloc[0]
    assert pd.isna(row["entry_relative_volume_per_bar_5"])
    assert row["entry_volume_state_per_bar_5"] == annotate.UNDEFINED_LABEL


def test_half_a_pair_of_thresholds_is_refused_rather_than_labelled_off_one_boundary() -> None:
    with pytest.raises(AnnotationError, match="both cut points or neither"):
        LabelThresholds(regime_consolidating_below=0.3)
    with pytest.raises(AnnotationError, match="both cut points or neither"):
        LabelThresholds(volume_heavy_above=1.5)


def test_an_impossible_threshold_is_refused_by_the_module_that_owns_it() -> None:
    with pytest.raises(ValueError, match="consolidating_below"):
        LabelThresholds(regime_consolidating_below=0.9, regime_directional_above=0.5)
    with pytest.raises(ValueError, match="trend_min_agreement"):
        LabelThresholds(trend_min_agreement=9)


# -- what did not match -------------------------------------------------------


def test_an_unmatched_trade_is_marked_rather_than_dropped() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                2,
                "2024-01-02 09:00:00",
                "2024-01-02 09:04:00",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    annotated = annotate.annotate_trades(log, data)
    assert annotated.trades == 2
    assert annotated.matched == 1
    assert annotated.unmatched == 1
    assert len(annotated.reviewable) == 1
    assert annotated.frame.loc[2, "entry_bar"] is pd.NA
    assert pd.isna(annotated.frame.loc[2, "entry_phase"])


def test_a_trade_is_annotated_whole_or_not_at_all() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                1,
                "2024-01-02 15:31:47",
                "2024-01-02 23:59:00",
                entry_price=close_of(32),
                exit_price=close_of(34),
            ),
        ],
    )
    annotated = annotate.annotate_trades(log, data)
    assert annotated.matched == 0, "half a trade annotated would misstate the trade itself"
    assert annotated.trades == 1


def test_the_dtypes_do_not_depend_on_whether_anything_was_unmatched() -> None:
    data = dataset()
    matched = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    mixed = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                2,
                "2024-01-02 09:00:00",
                "2024-01-02 09:04:00",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    one = annotate.annotate_trades(matched, data).frame.dtypes
    two = annotate.annotate_trades(mixed, data).frame.dtypes
    assert one.to_dict() == two.to_dict()
    assert str(one["entry_above_vwap"]) == "boolean", "a null must not be able to read as False"


def test_the_summary_states_the_matched_share() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    assert str(annotate.annotate_trades(log, data)).startswith("1/1 trades annotated (100.0%)")


# -- refusals and edges -------------------------------------------------------


def test_a_log_spanning_two_contracts_is_refused_rather_than_averaged() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                2,
                "2024-01-02 15:39:47",
                "2024-01-02 15:43:12",
                entry_price=close_of(40),
                exit_price=close_of(44),
            ),
        ],
    )
    log.loc[1, "contract"] = "MNQ 12-26"
    with pytest.raises(AnnotationError, match="annotate one at a time"):
        annotate.annotate_trades(log, data)


def test_a_log_spanning_two_roots_is_refused_when_it_names_no_contract() -> None:
    data = dataset()
    log = sim_log([(30, 34), (40, 44)], data.index)
    log["instrument"] = pd.Series(["MNQ", "NQ"], dtype="string")
    with pytest.raises(AnnotationError, match="values of instrument"):
        annotate.annotate_trades(log, data)


def test_a_frame_that_is_not_a_trade_log_is_refused_by_name() -> None:
    data = dataset()
    with pytest.raises(AnnotationError, match="missing required column"):
        annotate.annotate_trades(pd.DataFrame({"trade_id": [1]}), data)


def test_a_dataset_with_no_bars_is_refused() -> None:
    empty = bars(0)
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    with pytest.raises(AnnotationError, match="no bars"):
        annotate.annotate_trades(
            log, context.prepare(empty, ContextSpec(ma_keys=conditions.ma_keys(ema=(3,))))
        )


def test_an_empty_log_annotates_to_an_empty_frame_carrying_the_same_columns() -> None:
    data = dataset()
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    empty = annotate.annotate_trades(log.iloc[:0], data)
    assert empty.trades == 0
    assert empty.share == 0.0, "no trades is no coverage, not full coverage"
    assert empty.conditions == annotate.annotate_trades(log, data).conditions


# -- the bars a log must be annotated against ---------------------------------


def test_contract_bars_reads_the_per_contract_cache(tmp_path) -> None:
    frame = bars(10)
    path = ingest.contract_cache_path(ContractId.parse("MNQ 09-26"), tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # in_session is part of the cached schema, and load_contract filters on it.
    frame.assign(in_session=sessions.classify(frame.index).in_session).to_parquet(path)

    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
        ],
    )
    read = annotate.contract_bars(log, cache_dir=tmp_path)
    pd.testing.assert_index_equal(read.index, frame.index)


def test_contract_bars_refuses_a_log_that_names_no_contract() -> None:
    with pytest.raises(AnnotationError, match="does not name a contract"):
        annotate.contract_bars(sim_log([(30, 34)], bars().index))


def test_contract_bars_refuses_a_log_naming_more_than_one() -> None:
    log = manual_log(
        [
            leg(
                1,
                "2024-01-02 15:29:47",
                "2024-01-02 15:33:12",
                entry_price=close_of(30),
                exit_price=close_of(34),
            ),
            leg(
                2,
                "2024-01-02 15:39:47",
                "2024-01-02 15:43:12",
                entry_price=close_of(40),
                exit_price=close_of(44),
            ),
        ],
    )
    log.loc[1, "contract"] = "MNQ 12-26"
    with pytest.raises(AnnotationError, match="one contract at a time"):
        annotate.contract_bars(log)


# -- the same call on both kinds of log ---------------------------------------

TZ = "Europe/London"

SAMPLE = [
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,-,Stop4,",
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,1 S,Stop3,",
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,2 S,Stop2,",
    "MNQ 09-26,Buy,1,29761.75,10/08/2026 6:04:13 PM,3 S,Exit,",
    "MNQ 09-26,Sell,4,29767.00,10/08/2026 6:03:07 PM,4 S,Entry,",
    "MNQ 09-26,Buy,2,29782.75,10/08/2026 6:00:29 PM,-,Stop1,",
    "MNQ 09-26,Buy,1,29776.50,10/08/2026 6:00:21 PM,2 S,Exit,",
    "MNQ 09-26,Buy,1,29776.25,10/08/2026 6:00:17 PM,3 S,Exit,",
    "MNQ 09-26,Sell,2,29768.50,10/08/2026 5:58:52 PM,4 S,Entry,",
    "MNQ 09-26,Sell,2,29769.00,10/08/2026 5:58:49 PM,2 S,Entry,",
]
"""The 10 August 2026 session, as ``tests/test_trade_import.py`` carries it: two trades, seven
legs, and every fill between 16:58 and 17:08 UTC once the display zone is applied."""


def sample_bars() -> pd.DataFrame:
    """Minute bars over the sample's window, wide enough to hold every one of its fills."""
    index = pd.date_range("2026-08-10 16:50", periods=30, freq="min", tz="UTC")
    close = np.full(len(index), 29775.0)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 25.0,
            "low": close - 25.0,
            "close": close,
            "volume": np.full(len(index), 500.0),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


def test_an_imported_log_annotates_through_the_same_call_a_simulated_one_does(tmp_path) -> None:
    path = tmp_path / "grid.csv"
    header = "Instrument,Action,Quantity,Price,Time,Position,Name,"
    path.write_text("\r\n".join([header, *SAMPLE, ""]), encoding="utf-8")
    imported = trade_import.import_executions(path, timezone=TZ, cache_dir=tmp_path)

    data = context.prepare(sample_bars(), FULL_SPEC)
    annotated = annotate.annotate_trades(trades.validate(imported.frame), data, at_exit=True)

    assert annotated.trades == 2
    assert annotated.matched == 2
    assert annotated.frame["entry_bar_time"].tolist() == [
        pd.Timestamp("2026-08-10 16:59", tz="UTC"),
        pd.Timestamp("2026-08-10 17:04", tz="UTC"),
    ]
    simulated = annotate.annotate_trades(sim_log([(20, 24)], data.index, data.close), data, at_exit=True)
    assert simulated.conditions == annotated.conditions
