"""Guard tests: what a separation has to survive before anyone is allowed to believe it.

Four claims are pinned harder than the rest, because each would produce a confident number rather
than an error. **A separation is the review's quantity**, so it is asserted equal to
``review.rank_conditions`` on real logs rather than merely close to it. **A shuffle destroys only
the association**, so every stratum's size is asserted unchanged across the null. **The best of
many noise conditions is significant on its own and not against the family**, which is the whole
reason this module exists. **The holdout never re-chooses the split**, so a fixture whose effect
reverses in the recent trades is asserted to report the reversal rather than a second finding.

The fixtures come from ``tests/test_review.py``, so the guard is measured over exactly the trades
a review would rank.
"""

import numpy as np
import pandas as pd
import pytest
from test_review import SPEC, annotated, bars, bars_in, by_time_only, dataset, sim_log, two_phase_case

from nqbt import annotate, context, guard, review, stats, timeofday
from nqbt.guard import GuardError

ITERATIONS = 200
"""Enough shuffles for a p-value to be readable without making the suite slow."""

TRADES = 200
NOISE_CONDITIONS = 12
"""A few dozen conditions is the hazard; a dozen is enough to reproduce it."""


def labelled(
    count: int = TRADES,
    effect: float = 0.0,
    seed: int = 0,
    spread: float = 50.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw ``count`` trades alternating between two labels, ``effect`` landing only on ``a``."""
    rng = np.random.default_rng(seed)
    labels = np.where(np.arange(count) % 2 == 0, "a", "b")
    pnl = rng.normal(0.0, spread, count)
    pnl[labels == "a"] += effect

    return pnl, labels


def noise(
    count: int = TRADES,
    conditions: int = NOISE_CONDITIONS,
    seed: int = 7,
) -> dict[str, np.ndarray]:
    """Draw ``conditions`` labels that carry nothing, which is what a screen has to survive."""
    rng = np.random.default_rng(seed)

    return {f"noise_{i}": rng.integers(0, 3, count) for i in range(conditions)}


def per_trade_pnl(log: pd.DataFrame, annotation: annotate.Annotation) -> pd.DataFrame:
    """Collapse the reviewable trades to one row each, in the order a review groups them."""
    return stats.per_trade(log[log["trade_id"].isin(annotation.reviewable.index)])


def phase_case(winning: int = 60, losing: int = 60) -> tuple[pd.DataFrame, context.Dataset]:
    """Cash-open trades that win and midday trades that lose: a separation with a real cause."""
    data = dataset()
    entries = bars_in(data, timeofday.SessionPhase.CASH_OPEN, winning)
    entries += bars_in(data, timeofday.SessionPhase.MIDDAY, losing)

    return sim_log(entries, data, pnl=[100.0] * winning + [-100.0] * losing), data


# -- nothing here defines a statistic -----------------------------------------


def test_a_separation_is_exactly_the_quantity_rank_conditions_ranks_on() -> None:
    """The fast path is a route to the review's number, not a second opinion about it."""
    log, annotation, _ = two_phase_case()
    reviewed = review.review(log, annotation, min_trades=10)
    ordered = per_trade_pnl(log, annotation)
    pnl = ordered["net_pnl"].to_numpy(np.float64)

    assert not reviewed.ranking.empty
    for row in reviewed.ranking.itertuples(index=False):
        labels = annotation.reviewable.loc[ordered.index, row.condition]
        found = guard.separate(pnl, labels, statistic="expectancy", min_trades=10)
        assert (found.value == row.separation) or (pd.isna(found.value) and pd.isna(row.separation))
        assert (found.best == row.best) or (pd.isna(found.best) and pd.isna(row.best))
        assert (found.worst == row.worst) or (pd.isna(found.worst) and pd.isna(row.worst))
        assert found.strata == row.strata
        assert found.strata_ranked == row.strata_ranked
        assert found.trades_ranked == row.trades_ranked


def test_a_screen_carries_the_reviews_ranking_columns_unchanged() -> None:
    log, annotation, _ = two_phase_case()
    reviewed = review.review(log, annotation, min_trades=10).ranking
    screened = guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS).screen

    left = reviewed.set_index("condition").sort_index()
    right = screened.set_index("condition").sort_index()[left.columns]
    pd.testing.assert_frame_equal(left, right, check_dtype=False)


def test_a_separation_ignores_an_infinite_profit_factor_rather_than_being_topped_by_it() -> None:
    """A stratum with no losing trade would otherwise lead every ranking, forever."""
    labels = np.array(["flawless"] * 40 + ["good"] * 40 + ["bad"] * 40)
    pnl = np.concatenate([np.full(40, 10.0), np.tile([30.0, -10.0], 20), np.tile([10.0, -30.0], 20)])

    found = guard.separate(pnl, labels, statistic="profit_factor", min_trades=30)
    assert np.isinf(stats.trade_statistic(pnl[labels == "flawless"], "profit_factor"))
    assert found.strata == 3
    assert found.strata_ranked == 2, "the unbounded stratum is dropped, not ranked first"
    assert found.best == "good"


# -- the minimum stratum ------------------------------------------------------


def test_a_stratum_under_the_floor_is_counted_but_never_ranked() -> None:
    labels = np.array(["big"] * 60 + ["small"] * 5 + ["other"] * 60)
    pnl = np.concatenate([np.full(60, 10.0), np.full(5, 500.0), np.full(60, -10.0)])

    found = guard.separate(pnl, labels, statistic="expectancy", min_trades=30)
    assert found.strata == 3
    assert found.strata_ranked == 2
    assert found.trades_ranked == 120
    assert found.best == "big", "the five-trade stratum has the widest expectancy and is excluded"


def test_a_condition_with_one_surviving_stratum_separates_nothing_and_says_so() -> None:
    labels = np.array(["big"] * 60 + ["small"] * 5)
    pnl = np.arange(65, dtype=np.float64)

    found = guard.separate(pnl, labels, statistic="expectancy", min_trades=30)
    assert np.isnan(found.value)
    assert found.strata_ranked == 1
    assert pd.isna(found.best)


# -- the permutation test -----------------------------------------------------


def test_a_condition_that_carries_nothing_separates_no_better_than_its_own_shuffles() -> None:
    pnl, labels = labelled(effect=0.0)
    tested = guard.permutation_test(pnl, labels, iterations=ITERATIONS, min_trades=30)
    assert tested.p_value > 0.05, "labels drawn from nothing should not look like a finding"


def test_a_real_effect_separates_further_than_any_shuffle_of_the_same_trades() -> None:
    pnl, labels = labelled(effect=60.0)
    tested = guard.permutation_test(pnl, labels, iterations=ITERATIONS, min_trades=30)
    assert tested.observed > tested.null_p95
    assert tested.p_value == 0.0
    assert tested.draws_finite == ITERATIONS


def test_a_shuffle_moves_the_association_and_leaves_every_stratum_the_size_it_was() -> None:
    """The null has to be "these labels carry nothing", not "these strata are other strata"."""
    pnl, labels = labelled(effect=60.0)
    shuffled = np.random.default_rng(0).permutation(labels)
    sizes = pd.Series(labels).value_counts().sort_index()

    assert pd.Series(shuffled).value_counts().sort_index().equals(sizes)
    real = guard.separate(pnl, labels, min_trades=30)
    assert guard.separate(pnl, shuffled, min_trades=30).value < real.value


def test_the_same_seed_draws_the_same_null_twice() -> None:
    pnl, labels = labelled(effect=20.0)
    first = guard.permutation_test(pnl, labels, iterations=ITERATIONS, seed=3)
    second = guard.permutation_test(pnl, labels, iterations=ITERATIONS, seed=3)
    assert first == second


def test_permutation_test_reports_what_a_one_condition_screen_reports() -> None:
    """Both draw one null, so the single-hypothesis path cannot drift from the screened one."""
    pnl, labels = labelled(effect=20.0)
    alone = guard.permutation_test(pnl, labels, condition="side", iterations=ITERATIONS, seed=5)
    screened = guard.screen(pnl, {"side": labels}, iterations=ITERATIONS, seed=5)

    assert screened.loc[0, "p_value"] == alone.p_value
    assert screened.loc[0, "separation"] == alone.observed


# -- the family, which is what the guard is for -------------------------------


def test_the_best_of_many_noise_conditions_looks_real_alone_and_not_against_the_family() -> None:
    """The multiple-comparisons machine, reproduced and then caught."""
    pnl, _ = labelled(effect=0.0)
    screened = guard.screen(pnl, noise(), iterations=ITERATIONS, min_trades=30, seed=1)

    best = screened.iloc[0]
    assert best["p_value"] < 0.25, "some condition always splits the sample better than the rest"
    assert best[guard.FAMILY_COLUMN] > best["p_value"], "and the correction has to notice"
    assert (screened[guard.FAMILY_COLUMN] > 0.05).all(), "none of these carry anything"


def test_a_family_p_value_is_never_smaller_than_the_conditions_own() -> None:
    """It is a maximum over the same shuffles, so it can only ever be harder to pass."""
    pnl, labels = labelled(effect=40.0)
    screened = guard.screen(pnl, {**noise(), "side": labels}, iterations=ITERATIONS, min_trades=30)
    assert (screened[guard.FAMILY_COLUMN] >= screened["p_value"]).all()


def test_a_real_effect_survives_the_family_that_buries_the_noise() -> None:
    pnl, labels = labelled(effect=60.0)
    screened = guard.screen(
        pnl,
        {**noise(), "side": labels},
        iterations=ITERATIONS,
        min_trades=30,
        seed=1,
    ).set_index("condition")

    assert screened.loc["side", guard.FAMILY_COLUMN] == 0.0
    assert (screened.drop(index="side")[guard.FAMILY_COLUMN] > 0.05).all()


def test_a_screen_is_ordered_by_the_family_p_value_and_not_by_the_separation() -> None:
    pnl, labels = labelled(effect=60.0)
    screened = guard.screen(pnl, {**noise(), "side": labels}, iterations=ITERATIONS, min_trades=30)
    assert screened.loc[0, "condition"] == "side"
    assert screened[guard.FAMILY_COLUMN].is_monotonic_increasing


def test_a_trade_some_condition_leaves_null_is_dropped_from_all_of_them_and_counted() -> None:
    """A maximum over conditions measured on different trades would not compare like with like."""
    pnl, labels = labelled(effect=40.0)
    partial = pd.Series(labels, dtype="object")
    partial.iloc[:20] = None

    screened = guard.screen(pnl, {"side": labels, "partial": partial}, iterations=10, min_trades=30)
    assert screened.attrs["dropped"] == 20
    assert screened.attrs["trades"] == TRADES - 20
    assert set(screened["trades_ranked"]) == {TRADES - 20}


# -- the holdout --------------------------------------------------------------


def reversing(count: int = 400, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """Build a split that works over the first three quarters and inverts over the last one."""
    rng = np.random.default_rng(seed)
    labels = np.where(np.arange(count) % 2 == 0, "a", "b")
    pnl = rng.normal(0.0, 5.0, count)
    cut = count - count // 4
    pnl[:cut] += np.where(labels[:cut] == "a", 100.0, -100.0)
    pnl[cut:] += np.where(labels[cut:] == "a", -100.0, 100.0)

    return pnl, labels


def test_the_holdout_reads_the_split_the_earlier_trades_chose_rather_than_re_choosing_it() -> None:
    """Re-picking the best stratum on the recent trades would hold nothing out at all."""
    pnl, labels = reversing()
    held = guard.holdout_test(pnl, labels, min_trades=30)

    assert held.best == "a", "chosen on the earlier trades, where a wins"
    assert held.in_sample > 0
    assert held.out_of_sample < 0, "and the recent trades reverse it rather than confirming it"
    assert not held.direction_held
    assert held.reported, "both held-out strata clear the floor here"


def late(count: int = 400, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """Build a split worth two points early and two hundred over the most recent quarter."""
    rng = np.random.default_rng(seed)
    labels = np.where(np.arange(count) % 2 == 0, "a", "b")
    sign = np.where(labels == "a", 1.0, -1.0)
    effect = np.where(np.arange(count) < count - count // 4, 1.0, 100.0)

    return rng.normal(0.0, 5.0, count) + sign * effect, labels


def test_the_holdout_is_the_most_recent_trades_and_not_a_subset_chosen_some_other_way() -> None:
    """The split is worth a hundred times more in the last quarter, and only one end sees that."""
    pnl, labels = late()
    forwards = guard.holdout_test(pnl, labels, min_trades=30)
    backwards = guard.holdout_test(pnl[::-1], labels[::-1], min_trades=30)

    assert forwards.in_sample < 10.0 < forwards.out_of_sample
    assert backwards.out_of_sample < 10.0 < backwards.in_sample


def test_a_condition_the_earlier_trades_could_not_cut_has_no_split_to_hold_out() -> None:
    pnl = np.arange(100, dtype=np.float64)
    labels = np.array(["one"] * 100)
    held = guard.holdout_test(pnl, labels, min_trades=30)

    assert np.isnan(held.in_sample)
    assert np.isnan(held.out_of_sample)
    assert not held.reported
    assert held.held_out_trades == 0


def test_a_held_out_stratum_under_the_floor_is_reported_and_marked_rather_than_dropped() -> None:
    pnl, labels = reversing(count=160)
    held = guard.holdout_test(pnl, labels, min_trades=30)

    assert held.held_out_trades == 40, "a quarter of 160, split across the two chosen strata"
    assert not held.reported, "twenty trades a side is not a measurement"
    assert np.isfinite(held.out_of_sample), "but it is still reported"


def test_a_count_may_be_given_instead_of_a_share() -> None:
    pnl, labels = reversing()
    assert guard.holdout_test(pnl, labels, held_out=100, min_trades=30) == guard.holdout_test(
        pnl,
        labels,
        share=0.25,
        min_trades=30,
    )


@pytest.mark.parametrize(("share", "held_out"), [(0.0, None), (1.0, None), (0.25, 0), (0.25, 400)])
def test_a_holdout_that_would_leave_one_side_empty_is_refused(share: float, held_out: int) -> None:
    pnl, labels = reversing()
    with pytest.raises(GuardError, match=r"holdout share|leaves one side empty"):
        guard.holdout_test(pnl, labels, share=share, held_out=held_out)


# -- what a guard refuses -----------------------------------------------------


@pytest.mark.parametrize("statistic", ["net_pnl", "mean_r", "trades", "max_drawdown"])
def test_a_statistic_a_review_does_not_report_or_a_shuffle_cannot_move_is_refused(statistic: str) -> None:
    pnl, labels = labelled()
    with pytest.raises(GuardError, match="measures a separation in"):
        guard.separate(pnl, labels, statistic=statistic)


def test_a_label_per_anything_but_a_trade_is_refused() -> None:
    pnl, labels = labelled(count=100)
    with pytest.raises(GuardError, match="one label per trade"):
        guard.separate(pnl, labels[:50])


def test_a_null_needs_at_least_one_shuffle() -> None:
    pnl, labels = labelled()
    with pytest.raises(GuardError, match="at least one shuffle"):
        guard.screen(pnl, {"side": labels}, iterations=0)


def test_an_annotation_that_matched_nothing_cannot_be_guarded() -> None:
    log, _, _ = two_phase_case()
    elsewhere = context.prepare(bars(days=2, first_day="2025-06-02"), SPEC)
    unmatched = annotate.annotate_trades(by_time_only(log), elsewhere)

    assert unmatched.matched == 0
    with pytest.raises(GuardError, match="nothing to guard"):
        guard.guard(log, unmatched, iterations=10)


def test_a_log_without_entry_times_cannot_say_which_of_its_trades_are_recent() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(GuardError, match="no entry_time"):
        guard.guard(log.drop(columns=["entry_time", "exit_time"]), annotation, iterations=10)


def test_a_condition_this_annotation_does_not_hold_is_named_rather_than_skipped() -> None:
    log, annotation, _ = two_phase_case()
    with pytest.raises(GuardError, match="no condition"):
        guard.guard(log, annotation, conditions=["entry_moon_phase"], iterations=10)


# -- one review's conditions, guarded -----------------------------------------


def test_the_guard_runs_over_exactly_the_conditions_a_review_would_rank() -> None:
    log, annotation, _ = two_phase_case()
    guarded = guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS)
    assert guarded.conditions == review.stratifiable(annotation.reviewable, annotation.conditions)
    assert set(guarded.screen["condition"]) == set(guarded.conditions)


def test_the_holdout_frame_is_in_the_screens_order() -> None:
    log, annotation, _ = two_phase_case()
    guarded = guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS)
    assert guarded.holdout["condition"].tolist() == guarded.screen["condition"].tolist()


def test_a_real_time_of_day_effect_reaches_the_top_of_the_screen() -> None:
    log, data = phase_case()
    annotation = annotated(log, data)
    guarded = guard.guard(log, annotation, min_trades=30, iterations=ITERATIONS, seed=2)
    top = guarded.screen.iloc[0]

    assert top["condition"] == review.PHASE_COLUMN
    assert top["best"] == "cash_open"
    assert top[guard.FAMILY_COLUMN] == 0.0


# -- the report says what it is -----------------------------------------------


def test_the_report_states_that_a_guarded_separation_is_still_hypothesis_generating() -> None:
    log, annotation, _ = two_phase_case()
    rendered = str(guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS))
    assert "STILL HYPOTHESIS-GENERATING" in rendered
    assert guard.FAMILY_COLUMN in rendered


def test_the_report_states_the_holdout_it_applied_and_that_it_never_re_chose_the_split() -> None:
    log, annotation, _ = two_phase_case()
    guarded = guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS)
    rendered = str(guarded)
    assert f"the most recent {guarded.held_out} trades" in rendered
    assert "never re-chooses it" in rendered


def test_the_report_states_the_minimum_stratum_and_the_shuffles_behind_its_p_values() -> None:
    log, annotation, _ = two_phase_case()
    rendered = str(guard.guard(log, annotation, min_trades=10, iterations=ITERATIONS))
    assert "minimum 10 trades per stratum" in rendered
    assert f"{ITERATIONS} label shuffles" in rendered


# -- the edges ----------------------------------------------------------------


def test_a_condition_no_stratum_of_which_meets_the_floor_is_reported_without_a_p_value() -> None:
    """An excluded condition is a row saying so, never silence -- the review's rule too."""
    pnl, labels = labelled(count=40)
    screened = guard.screen(pnl, {"side": labels}, iterations=10, min_trades=100)
    row = screened.iloc[0]

    assert row["strata"] == 2
    assert row["strata_ranked"] == 0
    assert np.isnan(row["separation"])
    assert np.isnan(row["p_value"])
    assert np.isnan(row[guard.FAMILY_COLUMN])


def test_a_screen_of_no_conditions_is_an_empty_report_rather_than_an_error() -> None:
    pnl, _ = labelled()
    screened = guard.screen(pnl, {}, iterations=10)

    assert screened.empty
    assert list(screened.columns) == list(guard.SCREEN_COLUMNS)
    assert screened.attrs["trades"] == TRADES
    assert screened.attrs["dropped"] == 0


def test_a_guard_may_be_asked_for_named_conditions_rather_than_every_one() -> None:
    log, annotation, _ = two_phase_case()
    guarded = guard.guard(
        log,
        annotation,
        conditions=[review.PHASE_COLUMN],
        min_trades=10,
        iterations=ITERATIONS,
    )
    assert guarded.conditions == (review.PHASE_COLUMN,)
    assert guarded.screen["condition"].tolist() == [review.PHASE_COLUMN]


def test_every_result_flattens_to_a_row() -> None:
    pnl, labels = labelled(effect=40.0)
    tested = guard.permutation_test(pnl, labels, iterations=10)
    held = guard.holdout_test(pnl, labels, min_trades=30)

    assert tested.as_dict()["p_value"] == tested.p_value
    assert set(guard.HOLDOUT_COLUMNS) < set(held.as_dict()), "the report states the statistic once"


def test_strata_that_tie_exactly_name_one_stratum_at_both_ends_and_have_no_split_to_hold_out() -> None:
    """Zero is a separation the review reports; it is not a split anything can be read over."""
    labels = np.array(["a", "b"] * 100)
    pnl = np.tile([10.0, 10.0, -5.0, -5.0], 50)
    held = guard.holdout_test(pnl, labels, min_trades=30)

    assert guard.separate(pnl, labels, min_trades=30).value == 0.0
    assert held.best == held.worst
    assert held.in_sample == 0.0
    assert np.isnan(held.out_of_sample)
    assert held.held_out_trades == 0
    assert not held.reported
