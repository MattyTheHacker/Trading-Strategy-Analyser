"""Review tests: realised P&L cut by the conditions that were true at each entry.

Three claims are pinned harder than the rest, because each would produce a confident number
rather than an error. **Nothing here defines a statistic**, so a stratum's row is asserted equal
to ``stats.summarise`` over exactly that stratum's legs. **A placeholder never reaches a reported
number**, so the statistics an absent column feeds are asserted absent by name and the rest are
asserted identical to the populated log's. **Time of day is reported first and in session
order**, which alphabetical ordering would silently pass every other assertion.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import (
    annotate,
    conditions,
    context,
    review,
    sessions,
    stats,
    timeofday,
    trade_import,
    trades,
    volume,
)
from nqbt.annotate import LabelThresholds
from nqbt.context import ContextSpec
from nqbt.review import ReviewError

BASE = 18000.0
FIRST_DAY = "2024-01-02"
DAYS = 6
MINUTES = 480
TZ = "Europe/London"

SPEC = ContextSpec(
    ma_keys=conditions.ma_keys(ema=(3,)),
    needs_time_of_day=True,
    regime_lookbacks=(2,),
    volume_keys=(volume.key(int(volume.VolumeForm.PER_BAR), volume.NO_ROLLING, 5),),
)
"""Enough conditions to stratify by: a moving-average gate, a clock, a raw ratio and volume."""


def bars(days: int = DAYS, minutes: int = MINUTES, first_day: str = FIRST_DAY) -> pd.DataFrame:
    """``minutes`` one-minute bars from 09:00 ET on each of ``days`` weekdays.

    Six sessions because relative volume is undefined until five sit behind it, and a triangular
    price because a straight line has an efficiency ratio of 1.0 on every bar and would leave the
    regime label with nothing to stratify.
    """
    days_index = pd.bdate_range(first_day, periods=days)
    stamps = [
        pd.date_range(f"{day:%Y-%m-%d} 14:00", periods=minutes, freq="min", tz="UTC") for day in days_index
    ]
    index = stamps[0].append(stamps[1:])

    count = len(index)
    close = BASE + 0.25 * np.cumsum(np.where((np.arange(count) // 20) % 2 == 0, 1.0, -1.0))
    open_ = np.concatenate(([close[0]], close[:-1]))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 1.0,
            "low": np.minimum(open_, close) - 1.0,
            "close": close,
            "volume": np.random.default_rng(0).integers(50, 500, count).astype(np.float64),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


def dataset(spec: ContextSpec = SPEC, **kwargs: int | str) -> context.Dataset:
    """Prepare the fixture bars with every condition the review reads."""
    return context.prepare(bars(**kwargs), spec)


def bars_in(
    data: context.Dataset,
    phase: timeofday.SessionPhase,
    count: int,
    session: int = -1,
) -> list[int]:
    """``count`` bar indices in ``phase`` of one session -- the last, which alone has baselines.

    Relative volume is null until five sessions sit behind the bar, so a trade placed in the
    first session would be paired with a volume nobody could measure.
    """
    day = np.unique(data.bars["trading_day"].to_numpy())[session]
    in_session = data.bars["trading_day"].to_numpy() == day
    found = np.flatnonzero((data.phase_values() == int(phase)) & in_session)
    return found[:count].tolist()


def sim_log(
    entries: list[int],
    data: context.Dataset,
    pnl: list[float],
    hold: int = 2,
    exit_reasons: list[str] | None = None,
) -> pd.DataFrame:
    """Build a simulated log: one leg per trade, entering on the named bars, held ``hold`` bars.

    Every column ``summarise`` reads carries a value, so a review of it omits nothing.
    """
    at = np.asarray(entries, dtype=np.int64)
    out = at + hold
    count = len(at)
    net = np.asarray(pnl, dtype=np.float64)
    return pd.DataFrame(
        {
            "source": pd.array(["sim"] * count, dtype="string"),
            "instrument": pd.array(["MNQ"] * count, dtype="string"),
            "trade_id": np.arange(1, count + 1, dtype=np.int64),
            "leg": np.ones(count, dtype=np.int64),
            "entry_bar": at,
            "exit_bar": out,
            "entry_time": data.index[at],
            "exit_time": data.index[out],
            "entry_price": data.close[at],
            "exit_price": data.close[out],
            "quantity": np.ones(count, dtype=np.int64),
            "direction": np.ones(count),
            "net_pnl": net,
            "gross_pnl": net + 1.5,
            "commission": np.full(count, 1.5),
            "exit_reason": pd.array(exit_reasons or ["target"] * count, dtype="string"),
            "bars_held": np.full(count, hold, dtype=np.int64),
            "mae_points": np.full(count, 1.0),
            "mfe_points": np.full(count, 2.0),
            "r_multiple": net / 10.0,
            "ambiguous_bar": np.zeros(count, dtype=bool),
        },
    )


def blanked(log: pd.DataFrame) -> pd.DataFrame:
    """Null every column an importer cannot supply, in the dtypes the importer leaves them."""
    frame = log.copy()
    for name in ("bars_held", "entry_bar", "exit_bar"):
        frame[name] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    frame["ambiguous_bar"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    for name in ("mae_points", "mfe_points", "r_multiple"):
        frame[name] = pd.Series(np.nan, index=frame.index, dtype="float64")
    return frame


def by_time_only(log: pd.DataFrame) -> pd.DataFrame:
    """Strip the bar indices, leaving the log as an importer does: fill times and nothing else.

    Resolving a bar from its own stamp moves every trade one bar on, which is why a log carrying
    indices keeps them; here it decides only which trades a dataset holds bars for at all.
    """
    frame = log.copy()
    for name in ("entry_bar", "exit_bar"):
        frame[name] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    return frame


def alternating(count: int, win: float = 100.0, loss: float = -50.0) -> list[float]:
    """P&L that gives a stratum both winners and losers, so a win rate is not 0 or 1."""
    return [win if i % 2 else loss for i in range(count)]


def annotated(log: pd.DataFrame, data: context.Dataset, **kwargs: object) -> annotate.Annotation:
    """Annotate a log against the dataset it was built over."""
    return annotate.annotate_trades(log, data, **kwargs)


def two_phase_case(
    per_phase: int = 40,
    data: context.Dataset | None = None,
) -> tuple[pd.DataFrame, annotate.Annotation, context.Dataset]:
    """``per_phase`` trades in the cash open and as many at midday, each phase both winning and losing."""
    data = dataset() if data is None else data
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, per_phase)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, per_phase)
    log = sim_log(entries, data, pnl=alternating(len(entries)))
    return log, annotated(log, data), data


# -- nothing here defines a statistic -----------------------------------------


def test_a_stratum_reports_exactly_what_summarise_reports_over_its_own_legs() -> None:
    """The point of M9: a review is ``summarise`` over subsets, not a second set of formulae."""
    log, annotation, _ = two_phase_case()
    strata = review.stratify(log, annotation, review.PHASE_COLUMN, min_trades=1)

    phases = annotation.reviewable[review.PHASE_COLUMN]
    for row in strata.itertuples(index=False):
        ids = phases[phases == row.value].index
        expected = stats.summarise(log[log["trade_id"].isin(ids)])
        for name in review.REPORTED:
            assert getattr(row, name) == getattr(expected, name), name


def test_the_strata_of_one_condition_partition_the_reviewed_trades() -> None:
    log, annotation, _ = two_phase_case()
    strata = review.stratify(log, annotation, review.PHASE_COLUMN, min_trades=1)
    assert strata["trades"].sum() == annotation.matched


def test_stratify_and_review_produce_the_same_rows_for_one_condition() -> None:
    log, annotation, _ = two_phase_case()
    alone = review.stratify(log, annotation, review.PHASE_COLUMN, min_trades=10)
    reviewed = review.review(log, annotation, min_trades=10).strata
    together = reviewed[reviewed["condition"] == review.PHASE_COLUMN].reset_index(drop=True)
    # Not the dtype of ``value``: one condition's labels are strings and every condition's
    # together are objects, which is a property of the concatenation rather than of a stratum.
    pd.testing.assert_frame_equal(alone, together, check_dtype=False)


# -- time of day, the headline ------------------------------------------------


def test_time_of_day_is_reported_in_session_order_and_not_alphabetically() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.AFTERNOON, 5)
    entries += bars_in(data, timeofday.SessionPhase.CASH_OPEN, 5)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 5)
    log = sim_log(entries, data, pnl=alternating(len(entries)))

    phases = review.time_of_day(log, annotated(log, data), min_trades=1)
    assert phases.index.tolist() == ["cash_open", "midday", "afternoon"], (
        "session order; alphabetically this would be afternoon, cash_open, midday"
    )


def test_a_phase_carries_both_forms_of_volume_so_busy_and_unusually_busy_are_separable() -> None:
    log, annotation, _ = two_phase_case()
    phases = review.time_of_day(log, annotation, min_trades=1)
    assert [name for name in phases.columns if name.startswith("median_entry_volume_")]
    assert [name for name in phases.columns if name.startswith("median_entry_relative_volume_")]


def test_the_volume_state_label_is_not_read_as_a_volume_to_take_a_median_of() -> None:
    data = dataset()
    log, _, _ = two_phase_case(data=data)
    thresholds = LabelThresholds(volume_thin_below=0.5, volume_heavy_above=1.5)
    labelled = annotated(log, data, thresholds=thresholds)
    phases = review.time_of_day(log, labelled, min_trades=1)
    assert not [name for name in phases.columns if "volume_state" in name]


def test_a_dataset_with_a_clock_but_no_volume_still_reports_time_of_day() -> None:
    data = dataset(ContextSpec(needs_time_of_day=True))
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, 5)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 5)
    log = sim_log(entries, data, pnl=alternating(10))

    phases = review.time_of_day(log, annotated(log, data), min_trades=1)
    assert phases.index.tolist() == ["cash_open", "midday"]
    assert not [name for name in phases.columns if name.startswith("median_")]


def test_the_final_phase_reports_the_share_its_trades_were_closed_by_the_clock() -> None:
    """#43's artefact: a poor result in the close is the clock until the two are told apart."""
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CLOSE, 4)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 4)
    reasons = ["session_close"] * 4 + ["target"] * 4
    log = sim_log(entries, data, pnl=alternating(8), exit_reasons=reasons)

    phases = review.time_of_day(log, annotated(log, data), min_trades=1)
    assert phases.loc["close", "session_close_share"] == 1.0
    assert phases.loc["midday", "session_close_share"] == 0.0


def test_a_report_touching_the_final_phase_carries_the_forced_exit_note() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CLOSE, 4) + bars_in(data, timeofday.SessionPhase.MIDDAY, 4)
    log = sim_log(entries, data, pnl=alternating(8))
    rendered = str(review.review(log, annotated(log, data), min_trades=1))
    assert review.FORCED_EXIT_NOTE in rendered


def test_time_of_day_is_rendered_before_the_ranking() -> None:
    log, annotation, _ = two_phase_case()
    rendered = str(review.review(log, annotation, min_trades=1))
    assert rendered.index(review.PHASE_COLUMN) < rendered.index("separates their strata")


def test_a_dataset_with_no_clock_reports_no_time_of_day_rather_than_raising() -> None:
    data = dataset(ContextSpec(ma_keys=conditions.ma_keys(ema=(3,))))
    entries = list(range(0, 80, 2))
    log = sim_log(entries, data, pnl=alternating(len(entries)))
    annotation = annotated(log, data)

    reviewed = review.review(log, annotation, min_trades=1)
    assert reviewed.time_of_day.empty
    assert review.PHASE_COLUMN in str(reviewed)
    with pytest.raises(ReviewError, match="no clock to stratify by"):
        review.time_of_day(log, annotation)


# -- what a log cannot support ------------------------------------------------


def test_an_imported_log_omits_average_r_in_the_importers_own_words() -> None:
    log, annotation, _ = two_phase_case()
    reviewed = review.review(blanked(log), annotation, unpopulated=trade_import.UNPOPULATED, min_trades=1)

    assert reviewed.omitted["mean_r"] == trade_import.UNPOPULATED["r_multiple"]
    assert "mean_r" not in reviewed.strata.columns
    assert "mean_r" in str(reviewed)


def test_an_absent_column_omits_the_statistics_it_feeds_and_no_others() -> None:
    log, annotation, _ = two_phase_case()
    reviewed = review.review(blanked(log), annotation, min_trades=1)
    assert set(reviewed.strata.columns) == {
        "condition",
        "value",
        "trades",
        "win_rate",
        "expectancy",
        "profit_factor",
        "reported",
    }
    assert set(reviewed.omitted) >= {"mean_r", "avg_bars_held", "avg_mae_points", "ambiguous_share"}


def test_a_placeholder_never_reaches_a_reported_number() -> None:
    """``summarise`` needs the absent columns filled to run; the fill may not move a statistic."""
    log, annotation, _ = two_phase_case()
    populated = review.review(log, annotation, min_trades=1).strata
    absent = review.review(blanked(log), annotation, min_trades=1).strata

    shared = [name for name in populated.columns if name in absent.columns]
    pd.testing.assert_frame_equal(populated[shared], absent[shared])
    assert "avg_bars_held" not in absent.columns


def test_a_review_refuses_to_rank_by_a_statistic_this_log_cannot_support() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="cannot rank by 'mean_r'"):
        review.review(blanked(log), annotation, by="mean_r", min_trades=1)


def test_a_review_refuses_to_rank_by_a_statistic_no_review_reports() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="cannot rank by 'sharpe'"):
        review.review(log, annotation, by="sharpe")


def test_an_imported_logs_exit_reasons_cannot_identify_the_clock() -> None:
    """NT8's ``Name`` field is the source's vocabulary, so a zero share would be an invention."""
    log, annotation, _ = two_phase_case()
    log["exit_reason"] = pd.array(["Stop1"] * len(log), dtype="string")
    reviewed = review.review(log, annotation, min_trades=1)

    assert "session_close_share" in reviewed.omitted
    assert "session_close_share" not in reviewed.time_of_day.columns


# -- which conditions are a stratification ------------------------------------


def test_a_raw_series_is_refused_with_the_thresholds_that_would_cut_it() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="LabelThresholds"):
        review.stratify(log, annotation, "entry_efficiency_ratio_2")


def test_a_label_cut_from_that_series_is_stratifiable() -> None:
    data = dataset()
    log, _, _ = two_phase_case(data=data)
    thresholds = LabelThresholds(regime_consolidating_below=0.3, regime_directional_above=0.7)
    labelled = annotated(log, data, thresholds=thresholds)

    assert "entry_regime_2" in review.stratifiable(labelled.reviewable, labelled.conditions)
    assert "entry_efficiency_ratio_2" not in review.stratifiable(labelled.reviewable, labelled.conditions)


def test_a_condition_that_took_one_value_separates_nothing_and_is_not_stratified() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.MIDDAY, 20)
    log = sim_log(entries, data, pnl=alternating(20))
    annotation = annotated(log, data)

    reviewed = review.review(log, annotation, min_trades=1)
    assert review.PHASE_COLUMN not in reviewed.conditions
    assert review.PHASE_COLUMN in reviewed.skipped


def test_a_condition_with_a_value_per_trade_is_not_a_stratification() -> None:
    _, annotation, _ = two_phase_case()
    assert "entry_bar_of_session" not in review.stratifiable(annotation.reviewable, annotation.conditions)


def test_a_condition_the_caller_named_is_checked_rather_than_dropped() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="LabelThresholds"):
        review.review(log, annotation, conditions=["entry_efficiency_ratio_2"], min_trades=1)


def test_a_condition_no_annotation_holds_names_what_it_does_hold() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="no condition 'entry_moon_phase'"):
        review.stratify(log, annotation, "entry_moon_phase")


# -- the minimum stratum and the ranking --------------------------------------


def test_a_stratum_below_the_minimum_is_reported_but_not_ranked() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, 40)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 5)
    log = sim_log(entries, data, pnl=alternating(45))

    reviewed = review.review(log, annotated(log, data), min_trades=30)
    phases = reviewed.strata[reviewed.strata["condition"] == review.PHASE_COLUMN]
    assert phases["value"].tolist() == ["cash_open", "midday"]
    assert phases["reported"].tolist() == [True, False]
    ranked = reviewed.ranking.set_index("condition").loc[review.PHASE_COLUMN]
    assert ranked["strata"] == 2
    assert ranked["strata_ranked"] == 1
    assert pd.isna(ranked["separation"]), "one stratum separates nothing"


def test_the_ranking_names_the_widest_gap_and_both_ends_of_it() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, 10)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 10)
    pnl = [100.0] * 10 + [-100.0] * 10
    log = sim_log(entries, data, pnl=pnl)

    reviewed = review.review(log, annotated(log, data), min_trades=10)
    ranked = reviewed.ranking.set_index("condition").loc[review.PHASE_COLUMN]
    assert ranked["best"] == "cash_open"
    assert ranked["worst"] == "midday"
    assert ranked["separation"] == pytest.approx(200.0)


def test_conditions_come_back_widest_separation_first() -> None:
    log, annotation, _ = two_phase_case()
    ranking = review.review(log, annotation, min_trades=1).ranking
    separations = ranking["separation"].dropna().to_numpy(np.float64)
    assert (np.diff(separations) <= 0).all()


def test_an_infinite_profit_factor_is_dropped_from_the_separation_rather_than_leading_it() -> None:
    """A stratum with no losing trade reports an infinite profit factor, which no range survives."""
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, 10)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 10)
    log = sim_log(entries, data, pnl=[100.0] * 10 + alternating(10))

    ranking = review.review(log, annotated(log, data), by="profit_factor", min_trades=10).ranking
    ranked = ranking.set_index("condition").loc[review.PHASE_COLUMN]
    assert ranked["strata_ranked"] == 1
    assert pd.isna(ranked["separation"])


def test_rank_conditions_refuses_a_statistic_the_strata_were_built_without() -> None:
    log, annotation, _ = two_phase_case()
    strata = review.review(blanked(log), annotation, min_trades=1).strata
    with pytest.raises(ReviewError, match="mean_r"):
        review.rank_conditions(strata, by="mean_r")


def test_ranking_nothing_returns_the_ranking_columns_rather_than_an_empty_frame() -> None:
    empty = review.rank_conditions(pd.DataFrame())
    assert empty.empty
    assert "separation" in empty.columns


# -- the log and the annotation have to be the same trades --------------------


def test_a_review_refuses_an_annotation_built_over_other_trades() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="not in this log"):
        review.review(log[log["trade_id"] > 10], annotation, min_trades=1)


def test_a_review_refuses_a_frame_that_is_not_a_trade_log() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(ReviewError, match="missing required column"):
        review.review(log.drop(columns="net_pnl"), annotation, min_trades=1)


def test_a_review_refuses_an_annotation_nothing_matched() -> None:
    log, _, _ = two_phase_case()
    elsewhere = context.prepare(bars(days=2, first_day="2025-06-02"), SPEC)
    unmatched = annotate.annotate_trades(by_time_only(log), elsewhere)

    assert unmatched.matched == 0
    with pytest.raises(ReviewError, match="nothing to stratify"):
        review.review(log, unmatched, min_trades=1)


def test_only_the_matched_trades_are_reviewed() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.MIDDAY, 10, session=0)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, 10, session=-1)
    log = sim_log(entries, data, pnl=alternating(20))

    prefix = context.prepare(bars(days=3), SPEC)
    partial = annotate.annotate_trades(by_time_only(log), prefix)
    reviewed = review.review(log, partial, min_trades=1)

    assert partial.unmatched == 10, "the last session's trades are past the end of these bars"
    assert reviewed.reviewed == partial.matched
    assert reviewed.trades == partial.trades
    for _, group in reviewed.strata.groupby("condition"):
        assert group["trades"].sum() == partial.matched


# -- the report says what it is -----------------------------------------------


def test_the_report_states_that_it_is_hypothesis_generating_not_confirmatory() -> None:
    log, annotation, _ = two_phase_case()
    rendered = str(review.review(log, annotation, min_trades=1))
    assert "HYPOTHESIS-GENERATING, NOT CONFIRMATORY" in rendered
    assert "#48" in rendered


def test_the_report_states_the_minimum_stratum_it_applied() -> None:
    log, annotation, _ = two_phase_case()
    assert "minimum 30 trades per stratum" in str(review.review(log, annotation, min_trades=30))


def test_the_report_says_how_many_conditions_it_could_not_cut_by() -> None:
    log, annotation, _ = two_phase_case()
    reviewed = review.review(log, annotation, min_trades=1)
    assert reviewed.skipped, "the raw series are not stratifiable"
    total = len(reviewed.conditions) + len(reviewed.skipped)
    assert f"{len(reviewed.conditions)} of {total} conditions stratified" in str(reviewed)


def test_a_review_that_can_cut_by_nothing_still_renders() -> None:
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.MIDDAY, 6)
    log = sim_log(entries, data, pnl=alternating(6))
    reviewed = review.review(log, annotated(log, data), conditions=[], min_trades=1)

    assert reviewed.strata.empty
    assert "nothing to rank" in str(reviewed)


# -- an imported history, end to end ------------------------------------------

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
"""The 10 August 2026 session, as ``tests/test_trade_import.py`` carries it: two trades, seven legs."""


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


def test_a_real_imported_history_reviews_through_the_same_call_a_simulated_one_does(tmp_path) -> None:
    path = tmp_path / "grid.csv"
    header = "Instrument,Action,Quantity,Price,Time,Position,Name,"
    path.write_text("\r\n".join([header, *SAMPLE, ""]), encoding="utf-8")
    imported = trade_import.import_executions(path, timezone=TZ, cache_dir=tmp_path)

    data = context.prepare(sample_bars(), SPEC)
    annotation = annotate.annotate_trades(trades.validate(imported.frame), data)
    reviewed = review.review(
        imported.frame,
        annotation,
        min_trades=1,
        unpopulated=imported.unpopulated,
    )

    assert reviewed.reviewed == 2
    assert reviewed.omitted["mean_r"] == imported.unpopulated["r_multiple"]
    assert "HYPOTHESIS-GENERATING" in str(reviewed)
