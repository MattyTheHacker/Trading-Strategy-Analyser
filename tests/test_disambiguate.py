"""Reading the minute bars inside an ambiguous bar, and refusing to when they cannot be read.

Two halves. The walk itself is pure and is tested against hand-built minute bars, because every
verdict it can return has to be reachable and a fixture large enough to produce them all by
accident would prove nothing about which produced what. The splice is tested against the real
simulation, because what it rests on -- that the three ambiguity arms are the same trades leg
for leg -- is a property of ``resolve_brackets`` rather than of this module.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, disambiguate, resample, sessions, stats, sweep
from nqbt.disambiguate import (
    ENTRY_UNLOCATED,
    MIN_AMBIGUOUS_SHARE,
    MISALIGNED,
    STILL_AMBIGUOUS,
    STOP_FIRST,
    STOP_MOVED,
    TARGET_FIRST,
    DisambiguationError,
    accuracy,
    aligned,
    entry_minute,
    first_level_reached,
    first_target,
    guessed,
    owning_bar,
    rebuilds,
    resolve,
    resolved_log,
    stop_is_the_one_it_opened_with,
    sub_bars,
    worth_resolving,
)
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import AMBIGUITY_BEST_CASE, AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE
from nqbt.sim.types import InsideBarParams

LONG = 1.0
SHORT = -1.0


def minutes(*ranges: tuple[float, float]) -> pd.DataFrame:
    """Minute bars given only their low and high, which is all the walk reads."""
    lows = [low for low, _ in ranges]
    highs = [high for _, high in ranges]

    return pd.DataFrame(
        {"open": lows, "high": highs, "low": lows, "close": highs},
        index=pd.date_range("2024-01-02 14:31", periods=len(ranges), freq="min", tz="UTC"),
    )


# -- the threshold that keeps this an extra step ---------------------------------------------


def test_the_pass_runs_only_above_the_share_it_names() -> None:
    """It is an extra step on a finished result, not part of producing one."""
    assert worth_resolving(MIN_AMBIGUOUS_SHARE)
    assert worth_resolving(MIN_AMBIGUOUS_SHARE + 0.01)
    assert not worth_resolving(MIN_AMBIGUOUS_SHARE - 0.01)
    assert not worth_resolving(0.0)


# -- lining the minute bars up against the bar they built ------------------------------------


def test_each_minute_bar_maps_to_the_coarse_bar_it_was_aggregated_into() -> None:
    """End-of-bar stamps, so a minute bar belongs to the first coarse bar stamped at or after
    it -- get this off by one and every verdict is read from a neighbouring bar."""
    index = pd.date_range("2024-01-02 14:31", periods=10, freq="min", tz="UTC")
    coarse = pd.DatetimeIndex([index[4], index[9]])
    assert list(owning_bar(index, coarse)) == [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]


def test_the_window_of_a_coarse_bar_is_exactly_its_own_minutes() -> None:
    fine = minutes(*[(1.0, 2.0)] * 10)
    owner = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    assert len(sub_bars(fine, owner, 0)) == 5
    assert sub_bars(fine, owner, 1).index[0] == fine.index[5]


def test_a_window_that_rebuilds_its_coarse_bar_is_accepted() -> None:
    """§M13's associativity used as a guard on the alignment rather than an argument for it."""
    fine = minutes((10.0, 12.0), (9.0, 11.0), (11.0, 15.0))
    coarse = pd.Series({"open": 10.0, "high": 15.0, "low": 9.0, "close": 15.0})
    assert rebuilds(fine, coarse)


def test_a_window_that_does_not_rebuild_its_coarse_bar_is_refused() -> None:
    """The failure this exists for: a window off by a bar still looks like bars."""
    fine = minutes((10.0, 12.0), (9.0, 11.0))
    coarse = pd.Series({"open": 10.0, "high": 15.0, "low": 9.0, "close": 15.0})
    assert not rebuilds(fine, coarse)
    assert not rebuilds(fine.iloc[:0], coarse)


# -- which level came first ------------------------------------------------------------------


def walk(window: pd.DataFrame, direction: float = LONG, **kwargs: object) -> str:
    """``first_level_reached`` with a long stop at 90 and target at 110."""
    stop, target = (90.0, 110.0) if direction > 0 else (110.0, 90.0)

    return first_level_reached(window, stop, target, direction, fill_limit_on_touch=False, **kwargs)  # type: ignore[arg-type]  # kwargs are the caller's


def test_the_stop_alone_in_an_earlier_minute_settles_it() -> None:
    assert walk(minutes((99.0, 101.0), (85.0, 101.0), (99.0, 115.0))) == STOP_FIRST


def test_the_target_alone_in_an_earlier_minute_settles_it() -> None:
    assert walk(minutes((99.0, 101.0), (99.0, 115.0), (85.0, 101.0))) == TARGET_FIRST


def test_one_minute_holding_both_levels_is_the_residue_rather_than_a_verdict() -> None:
    """A minute is not fine enough here, and only ``data/tick/`` goes further -- so it is
    reported as unsettled instead of assumed a second time."""
    assert walk(minutes((99.0, 101.0), (85.0, 115.0))) == STILL_AMBIGUOUS


def test_minute_bars_reaching_neither_level_are_refused() -> None:
    """The coarse bar held both levels, so its minutes must too; that they do not means the
    window is not the bar's."""
    assert walk(minutes((99.0, 101.0), (98.0, 102.0))) == MISALIGNED


def test_the_walk_is_sided_so_a_short_reads_its_own_adverse_extreme() -> None:
    """A short's stop is above and its target below, and reading them the long way round would
    settle every short backwards."""
    assert walk(minutes((99.0, 101.0), (99.0, 115.0), (85.0, 101.0)), SHORT) == STOP_FIRST
    assert walk(minutes((99.0, 101.0), (85.0, 101.0), (99.0, 115.0)), SHORT) == TARGET_FIRST


# -- the position did not exist for the whole bar --------------------------------------------


def test_minutes_before_the_fill_are_not_the_trades() -> None:
    """The dominant case rather than an edge one: every ambiguous bar in §M28.2's retest
    shortlist exits on its own entry bar, so a walk from the bar's first minute reads levels
    reached before the position existed."""
    window = minutes((85.0, 101.0), (99.0, 101.0), (99.0, 115.0))
    assert walk(window) == STOP_FIRST, "the whole window reaches the stop first"
    assert walk(window, opened_in=1) == TARGET_FIRST, "held only from minute 1, the target is first"


def test_a_level_inside_the_fill_minute_cannot_be_ordered_against_the_fill() -> None:
    assert walk(minutes((85.0, 101.0), (99.0, 115.0)), opened_in=0) == STILL_AMBIGUOUS


def test_a_fill_minute_holding_neither_level_starts_a_clean_walk() -> None:
    assert walk(minutes((99.0, 101.0), (85.0, 101.0)), opened_in=0) == STOP_FIRST


def test_an_entry_that_cannot_be_located_is_refused_rather_than_walked() -> None:
    assert walk(minutes((99.0, 101.0), (85.0, 101.0)), opened_in=2) == ENTRY_UNLOCATED


def test_the_fill_minute_is_the_first_one_holding_the_fill_price() -> None:
    window = minutes((99.0, 101.0), (95.0, 105.0), (95.0, 105.0))
    coarse = pd.Series({"open": 99.0, "high": 105.0, "low": 95.0, "close": 105.0})
    assert entry_minute(window, coarse, 104.0) == 1


def test_a_fill_at_the_bars_open_means_the_whole_bar_was_held() -> None:
    """A resting order filling at the open is open for every minute of it, so there is no
    unknown ordering to protect against."""
    window = minutes((99.0, 101.0), (95.0, 105.0))
    coarse = pd.Series({"open": 99.0, "high": 105.0, "low": 95.0, "close": 105.0})
    assert entry_minute(window, coarse, 99.0) == -1


def test_a_fill_price_no_minute_bar_holds_runs_off_the_end() -> None:
    window = minutes((99.0, 101.0), (99.0, 101.0))
    coarse = pd.Series({"open": 99.0, "high": 101.0, "low": 99.0, "close": 101.0})
    assert entry_minute(window, coarse, 500.0) == len(window)


# -- which target the walk asks about --------------------------------------------------------


def ladder(direction: float, *targets: float) -> pd.DataFrame:
    """One trade's legs, each carrying its own rung of the target ladder."""
    return pd.DataFrame(
        {
            "target_price": list(targets),
            "direction": direction,
            "entry_price": 100.0,
            "initial_stop": 90.0 if direction > 0 else 110.0,
            "exit_reason": "target",
        },
    )


def test_the_target_asked_about_is_the_one_nearest_the_fill() -> None:
    """Not the one nearest the bar's open, which is what the *policy* compares. Price reaches
    the closest rung first, and asking about a further one biases every verdict to the stop."""
    coarse = pd.Series({"open": 100.0, "high": 130.0, "low": 99.0, "close": 130.0})
    assert first_target(ladder(LONG, 110.0, 120.0), coarse, LONG, fill_limit_on_touch=False) == 110.0


def test_an_unreachable_target_is_not_offered_to_the_walk() -> None:
    coarse = pd.Series({"open": 100.0, "high": 115.0, "low": 99.0, "close": 115.0})
    assert first_target(ladder(LONG, 110.0, 120.0), coarse, LONG, fill_limit_on_touch=False) == 110.0


def test_a_bar_reaching_no_target_at_all_has_no_level_to_walk_against() -> None:
    coarse = pd.Series({"open": 100.0, "high": 105.0, "low": 99.0, "close": 105.0})
    assert np.isnan(first_target(ladder(LONG, 110.0), coarse, LONG, fill_limit_on_touch=False))


# -- the stop has to be the one the log carries ----------------------------------------------


def stop_legs(initial_stop: float, direction: float = LONG) -> pd.DataFrame:
    return pd.DataFrame({"initial_stop": [initial_stop], "direction": [direction]})


def test_the_stop_is_verified_against_the_arm_that_always_takes_it() -> None:
    """The worst-case arm exits every open leg at the stop, so its fill is the live stop's."""
    worst = pd.DataFrame({"exit_price": [89.75]})
    assert stop_is_the_one_it_opened_with(stop_legs(90.0), worst, 0.25)


def test_a_stop_that_moved_is_refused_rather_than_read_at_the_wrong_level() -> None:
    """A trailing archetype reaches this on every leg, which is the point: the log's
    ``initial_stop`` is not what was live, and answering against it would be answering a
    different question confidently."""
    worst = pd.DataFrame({"exit_price": [95.0]})
    assert not stop_is_the_one_it_opened_with(stop_legs(90.0), worst, 0.0)
    assert not stop_is_the_one_it_opened_with(stop_legs(90.0), pd.DataFrame({"exit_price": []}), 0.0)


# -- reading the assumption back --------------------------------------------------------------


def test_the_assumption_is_read_back_from_how_the_legs_left() -> None:
    assert guessed(pd.DataFrame({"exit_reason": ["stop", "target"]})) == TARGET_FIRST
    assert guessed(pd.DataFrame({"exit_reason": ["stop", "stop"]})) == STOP_FIRST


def verdicts(**columns: object) -> pd.DataFrame:
    base = {
        "assumed": [TARGET_FIRST, TARGET_FIRST, TARGET_FIRST, TARGET_FIRST],
        "resolved": [TARGET_FIRST, STOP_FIRST, STILL_AMBIGUOUS, STOP_MOVED],
        "opened_here": True,
        "trade_id": [1, 2, 3, 4],
    }
    frame = pd.DataFrame({**base, **columns})
    settled = frame["resolved"].isin(disambiguate.DECIDED)
    frame["agrees"] = (frame["assumed"] == frame["resolved"]).astype("boolean").where(settled)

    return frame


def test_accuracy_is_measured_over_the_bars_that_were_settled() -> None:
    """A bar a minute could not settle is not a bar the assumption got wrong."""
    scored = accuracy(verdicts())
    assert scored["ambiguous_bars"] == 4
    assert scored["decided"] == 2
    assert scored["assumption_correct"] == 1
    assert scored["assumption_accuracy"] == pytest.approx(0.5)
    assert scored["still_ambiguous"] == 1
    assert scored["refused"] == 1


def test_accuracy_of_a_run_that_settled_nothing_is_undefined_rather_than_zero() -> None:
    """Zero would read as "the assumption was always wrong", which is the opposite claim."""
    scored = accuracy(verdicts(resolved=[STILL_AMBIGUOUS] * 4))
    assert scored["decided"] == 0
    assert np.isnan(scored["assumption_accuracy"])


# -- rebuilding the log from the arms ----------------------------------------------------------


def arm(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4],
            "leg": 0,
            "entry_bar": [10, 20, 30, 40],
            "exit_bar": [11, 21, 31, 41],
            "exit_price": prices,
        },
    )


def test_a_settled_bar_takes_its_rows_from_the_arm_that_resolved_it_that_way() -> None:
    """A resolved log is a row selection, never arithmetic on a price."""
    ranked, worst, best = arm([1.0, 2.0, 3.0, 4.0]), arm([9.0] * 4), arm([5.0] * 4)
    out = resolved_log(ranked, worst, best, verdicts())

    assert out["exit_price"].iloc[0] == 5.0, "trade 1 settled target-first, so it is the best arm"
    assert out["exit_price"].iloc[1] == 9.0, "trade 2 settled stop-first, so it is the worst arm"


def test_a_bar_the_minute_bars_could_not_settle_keeps_the_assumption() -> None:
    """The output is the assumption corrected where the data can correct it, not a different
    assumption applied everywhere."""
    ranked, worst, best = arm([1.0, 2.0, 3.0, 4.0]), arm([9.0] * 4), arm([5.0] * 4)
    out = resolved_log(ranked, worst, best, verdicts())

    assert out["exit_price"].iloc[2] == 3.0, "still ambiguous, so NT8's guess stands"
    assert out["exit_price"].iloc[3] == 4.0, "refused, so NT8's guess stands"


def test_nothing_settled_leaves_the_log_alone() -> None:
    ranked = arm([1.0, 2.0, 3.0, 4.0])
    out = resolved_log(ranked, arm([9.0] * 4), arm([5.0] * 4), pd.DataFrame())
    pd.testing.assert_frame_equal(out, ranked.reset_index(drop=True))


def test_arms_that_are_not_the_same_trades_are_refused() -> None:
    """A resolved log built on a false alignment would file one configuration's legs under
    another's, and every statistic taken from it would look reasonable."""
    ranked = arm([1.0, 2.0, 3.0, 4.0])
    shifted = ranked.assign(exit_bar=ranked["exit_bar"] + 1)
    assert not aligned(ranked, shifted, ranked)

    with pytest.raises(DisambiguationError, match="not the same trades"):
        resolved_log(ranked, shifted, ranked, verdicts())


def test_arms_of_different_lengths_are_refused() -> None:
    ranked = arm([1.0, 2.0, 3.0, 4.0])
    assert not aligned(ranked, ranked.iloc[:2], ranked)


# -- against the simulation itself -------------------------------------------------------------


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
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
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day

    return frame


def three_arms() -> tuple[dict[int, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """One ambiguity-producing configuration run under all three policies."""
    fine = synthetic_bars()
    coarse = resample.resample(fine, 5)
    base = InsideBarParams(
        slow_sma_period=50,
        bars_required_to_trade=60,
        tp_multiplier=0.25,
        atr_multiplier=0.25,
    )
    spec = sweep.Grid(base=base, archetype=archetypes.INSIDEBAR).required_context()
    data = context.prepare(coarse, spec, bar_minutes=5)

    logs: dict[int, pd.DataFrame] = {}
    for policy in (AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE, AMBIGUITY_BEST_CASE):
        _, log = sweep.run_combination(
            data,
            replace(base, ambiguity_policy=policy),
            get_instrument("MNQ"),
            archetypes.INSIDEBAR,
            keep_trades=True,
        )
        logs[policy] = log

    return logs, fine, coarse


def test_the_three_arms_are_the_same_trades_leg_for_leg() -> None:
    """What the whole splice rests on, and it is a property of ``resolve_brackets`` rather than
    of this module: the whole position closes on an ambiguous bar under either policy, so the
    next bar starts flat in every arm and nothing downstream can diverge."""
    logs, _, _ = three_arms()
    assert aligned(
        logs[AMBIGUITY_NEAREST_TO_OPEN],
        logs[AMBIGUITY_WORST_CASE],
        logs[AMBIGUITY_BEST_CASE],
    )


def test_the_arms_bracket_the_ranked_result_rather_than_straddling_it() -> None:
    """The two ends of the band are ends: NT8's guess cannot be outside them."""
    logs, _, _ = three_arms()
    ranked = stats.summarise(logs[AMBIGUITY_NEAREST_TO_OPEN]).profit_factor
    worst = stats.summarise(logs[AMBIGUITY_WORST_CASE]).profit_factor
    best = stats.summarise(logs[AMBIGUITY_BEST_CASE]).profit_factor

    assert worst <= ranked <= best


def test_a_real_ambiguous_bar_is_settled_against_its_own_minute_bars() -> None:
    """The end-to-end claim: the fixture's ambiguous bar gets a verdict, and the resolved log
    is one of the two arms on that trade rather than a third thing."""
    logs, fine, coarse = three_arms()
    ranked, worst, best = (
        logs[AMBIGUITY_NEAREST_TO_OPEN],
        logs[AMBIGUITY_WORST_CASE],
        logs[AMBIGUITY_BEST_CASE],
    )
    table = resolve(ranked, worst, fine, coarse, slippage=0.0, fill_limit_on_touch=False)

    assert not table.empty, "fixture produced no ambiguous bar; the test proves nothing"
    assert set(table["resolved"]) <= {TARGET_FIRST, STOP_FIRST, STILL_AMBIGUOUS, MISALIGNED, STOP_MOVED}

    out = resolved_log(ranked, worst, best, table)
    assert len(out) == len(ranked)
    for _, row in table[table["resolved"].isin(disambiguate.DECIDED)].iterrows():
        taken = out[out["trade_id"] == row["trade_id"]]["exit_price"].to_numpy()
        source = worst if row["resolved"] == STOP_FIRST else best
        expected = source[source["trade_id"] == row["trade_id"]]["exit_price"].to_numpy()
        assert np.array_equal(taken, expected)


def test_a_configuration_with_no_ambiguous_bar_produces_no_table() -> None:
    logs, fine, coarse = three_arms()
    clean = logs[AMBIGUITY_NEAREST_TO_OPEN].assign(ambiguous_bar=False)
    assert resolve(
        clean, logs[AMBIGUITY_WORST_CASE], fine, coarse, slippage=0.0, fill_limit_on_touch=False
    ).empty


def test_a_moved_stop_is_refused_through_the_whole_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """The trailing-archetype guard, reached the way a real run reaches it: the log's
    ``initial_stop`` no longer agrees with the arm that always takes the stop."""
    logs, fine, coarse = three_arms()
    ranked = logs[AMBIGUITY_NEAREST_TO_OPEN].copy()
    ranked.loc[ranked["ambiguous_bar"], "initial_stop"] += 7.0
    table = resolve(ranked, logs[AMBIGUITY_WORST_CASE], fine, coarse, slippage=0.0, fill_limit_on_touch=False)

    assert set(table["resolved"]) == {STOP_MOVED}
    assert accuracy(table)["refused"] == len(table)


def test_a_window_that_cannot_be_lined_up_is_refused_through_the_whole_pass() -> None:
    """A coarse frame whose bars are not the ones the minutes built: every verdict must become
    a refusal rather than a reading off the wrong bars."""
    logs, fine, coarse = three_arms()
    shifted = coarse.assign(high=coarse["high"] + 50.0)
    table = resolve(
        logs[AMBIGUITY_NEAREST_TO_OPEN],
        logs[AMBIGUITY_WORST_CASE],
        fine,
        shifted,
        slippage=0.0,
        fill_limit_on_touch=False,
    )

    assert set(table["resolved"]) == {MISALIGNED}
