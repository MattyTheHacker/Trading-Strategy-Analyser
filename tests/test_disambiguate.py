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
    FILL_BAR_SCORED,
    HELD,
    MIN_AMBIGUOUS_SHARE,
    MISALIGNED,
    STILL_AMBIGUOUS,
    STOP_FIRST,
    STOP_MOVED,
    TARGET_FIRST,
    DisambiguationError,
    accuracy,
    aligned,
    check_fill_bars,
    enters_on_stop,
    entry_minute,
    fill_bar_accuracy,
    fill_minute,
    first_level_reached,
    first_target,
    guessed,
    owning_bar,
    rebuilds,
    resolve,
    resolved_log,
    simulated_outcome,
    stop_is_the_one_it_opened_with,
    sub_bars,
    worth_resolving,
)
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import AMBIGUITY_BEST_CASE, AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE
from nqbt.sim.types import (
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_REJECTION,
    ORB_ENTRY_RETEST,
    ORB_STOP_FRACTION,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
)
from tests.rows import number

LONG = 1.0
SHORT = -1.0


def minutes(*ranges: tuple[float, float]) -> pd.DataFrame:
    """Build minute bars given only their low and high, which is all the walk reads."""
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
    """End-of-bar stamps, so a minute bar belongs to the first coarse bar stamped at or after it.

    Get this off by one and every verdict is read from a neighbouring bar.
    """
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
    """Run ``first_level_reached`` with a long stop at 90 and target at 110."""
    stop, target = (90.0, 110.0) if direction > 0 else (110.0, 90.0)

    return first_level_reached(window, stop, target, direction, fill_limit_on_touch=False, **kwargs)  # type: ignore[arg-type]  # kwargs are the caller's


def test_the_stop_alone_in_an_earlier_minute_settles_it() -> None:
    assert walk(minutes((99.0, 101.0), (85.0, 101.0), (99.0, 115.0))) == STOP_FIRST


def test_the_target_alone_in_an_earlier_minute_settles_it() -> None:
    assert walk(minutes((99.0, 101.0), (99.0, 115.0), (85.0, 101.0))) == TARGET_FIRST


def test_one_minute_holding_both_levels_is_the_residue_rather_than_a_verdict() -> None:
    """A minute is not fine enough here, and only ``data/tick/`` goes further.

    So it is reported as unsettled instead of assumed a second time.
    """
    assert walk(minutes((99.0, 101.0), (85.0, 115.0))) == STILL_AMBIGUOUS


def test_minute_bars_reaching_neither_level_are_refused() -> None:
    """The coarse bar held both levels, so its minutes must too.

    That they do not means the window is not the bar's.
    """
    assert walk(minutes((99.0, 101.0), (98.0, 102.0))) == MISALIGNED


def test_the_walk_is_sided_so_a_short_reads_its_own_adverse_extreme() -> None:
    """A short's stop is above and its target below.

    Reading them the long way round would settle every short backwards.
    """
    assert walk(minutes((99.0, 101.0), (99.0, 115.0), (85.0, 101.0)), SHORT) == STOP_FIRST
    assert walk(minutes((99.0, 101.0), (85.0, 101.0), (99.0, 115.0)), SHORT) == TARGET_FIRST


# -- the position did not exist for the whole bar --------------------------------------------


def test_minutes_before_the_fill_are_not_the_trades() -> None:
    """The dominant case rather than an edge one.

    Every ambiguous bar in §M28.2's retest shortlist exits on its own entry bar, so a walk from
    the bar's first minute reads levels reached before the position existed.
    """
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
    """A resting order filling at the open is open for every minute of it.

    There is no unknown ordering to protect against.
    """
    window = minutes((99.0, 101.0), (95.0, 105.0))
    coarse = pd.Series({"open": 99.0, "high": 105.0, "low": 95.0, "close": 105.0})
    assert entry_minute(window, coarse, 99.0) == -1


def test_a_fill_price_no_minute_bar_holds_runs_off_the_end() -> None:
    window = minutes((99.0, 101.0), (99.0, 101.0))
    coarse = pd.Series({"open": 99.0, "high": 101.0, "low": 99.0, "close": 101.0})
    assert entry_minute(window, coarse, 500.0) == len(window)


# -- which target the walk asks about --------------------------------------------------------


def ladder(direction: float, *targets: float) -> pd.DataFrame:
    """Build one trade's legs, each carrying its own rung of the target ladder."""
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
    """Not the one nearest the bar's open, which is what the *policy* compares.

    Price reaches the closest rung first, and asking about a further one biases every verdict to
    the stop.
    """
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
    """A trailing archetype reaches this on every leg, which is the point.

    The log's ``initial_stop`` is not what was live, and answering against it would be answering
    a different question confidently.
    """
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
    assert np.isnan(number(scored, "assumption_accuracy"))


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
    """The output is the assumption corrected where the data can correct it.

    It is not a different assumption applied everywhere.
    """
    ranked, worst, best = arm([1.0, 2.0, 3.0, 4.0]), arm([9.0] * 4), arm([5.0] * 4)
    out = resolved_log(ranked, worst, best, verdicts())

    assert out["exit_price"].iloc[2] == 3.0, "still ambiguous, so NT8's guess stands"
    assert out["exit_price"].iloc[3] == 4.0, "refused, so NT8's guess stands"


def test_nothing_settled_leaves_the_log_alone() -> None:
    ranked = arm([1.0, 2.0, 3.0, 4.0])
    out = resolved_log(ranked, arm([9.0] * 4), arm([5.0] * 4), pd.DataFrame())
    pd.testing.assert_frame_equal(out, ranked.reset_index(drop=True))


def test_arms_that_are_not_the_same_trades_are_refused() -> None:
    """A resolved log built on a false alignment would file one configuration's legs under another's.

    Every statistic taken from it would look reasonable.
    """
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
    """Run one ambiguity-producing configuration under all three policies."""
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
        assert log is not None
        logs[policy] = log

    return logs, fine, coarse


def test_the_three_arms_are_the_same_trades_leg_for_leg() -> None:
    """What the whole splice rests on.

    It is a property of ``resolve_brackets`` rather than of this module: the whole position
    closes on an ambiguous bar under either policy, so the next bar starts flat in every arm and
    nothing downstream can diverge. A stop entry's own bar is the one exception, tested below.
    """
    logs, _, _ = three_arms()
    assert aligned(
        logs[AMBIGUITY_NEAREST_TO_OPEN],
        logs[AMBIGUITY_WORST_CASE],
        logs[AMBIGUITY_BEST_CASE],
    )


def test_a_stop_entrys_three_arms_are_the_same_trades_even_where_its_legs_part() -> None:
    """A stop entry's own bar can stop the earlier legs and close the last one at its target.

    Which legs leave does not depend on the policy, and each leg is written in leg order, so
    the arms still line up -- ``docs/nt8-fidelity.md``, "A stop on its entry bar is read along
    the bar's path". The last leg is given a target of its own so that the case occurs.
    """
    base = DeadCatParams(
        use_ema=False,
        use_fast_sma=False,
        require_previous_green=False,
        require_new_high=False,
        bars_required_to_trade=0,
        target_r_multiples=(0.5, 1.0, 1.5, 2.0),
    )
    spec = sweep.Grid(base=base, archetype=archetypes.DEADCATBOUNCE).required_context()
    data = context.prepare(synthetic_bars(), spec)
    logs: dict[int, pd.DataFrame] = {}
    for policy in (AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE, AMBIGUITY_BEST_CASE):
        _, log = sweep.run_combination(
            data,
            replace(base, ambiguity_policy=policy),
            get_instrument("MNQ"),
            archetypes.DEADCATBOUNCE,
            keep_trades=True,
        )
        assert log is not None
        logs[policy] = log

    ranked = logs[AMBIGUITY_NEAREST_TO_OPEN]
    on_entry_bar = ranked[ranked["exit_bar"] == ranked["entry_bar"]]
    last_at_target = on_entry_bar[(on_entry_bar["leg"] == 4) & (on_entry_bar["exit_reason"] == "target")]
    earlier_stopped = on_entry_bar[(on_entry_bar["leg"] < 4) & (on_entry_bar["exit_reason"] == "stop")]
    assert last_at_target["trade_id"].isin(earlier_stopped["trade_id"]).any()
    assert aligned(ranked, logs[AMBIGUITY_WORST_CASE], logs[AMBIGUITY_BEST_CASE])


def test_the_arms_bracket_the_ranked_result_rather_than_straddling_it() -> None:
    """The two ends of the band are ends: NT8's guess cannot be outside them."""
    logs, _, _ = three_arms()
    ranked = stats.summarise(logs[AMBIGUITY_NEAREST_TO_OPEN]).profit_factor
    worst = stats.summarise(logs[AMBIGUITY_WORST_CASE]).profit_factor
    best = stats.summarise(logs[AMBIGUITY_BEST_CASE]).profit_factor

    assert worst <= ranked <= best


def test_a_real_ambiguous_bar_is_settled_against_its_own_minute_bars() -> None:
    """The end-to-end claim: the fixture's ambiguous bar gets a verdict.

    The resolved log is one of the two arms on that trade rather than a third thing.
    """
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


def test_a_moved_stop_is_refused_through_the_whole_pass() -> None:
    """The trailing-archetype guard, reached the way a real run reaches it.

    The log's ``initial_stop`` no longer agrees with the arm that always takes the stop.
    """
    logs, fine, coarse = three_arms()
    ranked = logs[AMBIGUITY_NEAREST_TO_OPEN].copy()
    ranked.loc[ranked["ambiguous_bar"], "initial_stop"] += 7.0
    table = resolve(ranked, logs[AMBIGUITY_WORST_CASE], fine, coarse, slippage=0.0, fill_limit_on_touch=False)

    assert set(table["resolved"]) == {STOP_MOVED}
    assert accuracy(table)["refused"] == len(table)


def test_a_window_that_cannot_be_lined_up_is_refused_through_the_whole_pass() -> None:
    """A coarse frame whose bars are not the ones the minutes built.

    Every verdict must become a refusal rather than a reading off the wrong bars.
    """
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


# -- a stop entry's own bar --------------------------------------------------------------------


def a_bar(*ranges: tuple[float, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build minute bars and the one coarse bar they aggregate into, stamped at its last minute."""
    fine = minutes(*ranges)
    coarse = pd.DataFrame(
        {
            "open": [fine["open"].iloc[0]],
            "high": [fine["high"].max()],
            "low": [fine["low"].min()],
            "close": [fine["close"].iloc[-1]],
        },
        index=fine.index[-1:],
    )

    return fine, coarse


def a_leg(
    exit_bar: int = 1, exit_reason: str = "target", net: float = 50.0, leg: int = 1
) -> dict[str, object]:
    """Return one leg of a long stop entry triggered at 100 and filled a quarter-point worse.

    Its stop is at 99.5 and its target at 110.
    """
    return {
        "trade_id": 1,
        "leg": leg,
        "entry_bar": 0,
        "exit_bar": exit_bar,
        "entry_price": 100.25,
        "initial_stop": 99.5,
        "target_price": 110.0,
        "direction": LONG,
        "exit_reason": exit_reason,
        "net_pnl": net,
    }


def read(fine: pd.DataFrame, coarse: pd.DataFrame, *legs: dict[str, object]) -> pd.DataFrame:
    """Read hand-built legs' fill bar at a quarter-point of slippage."""
    return check_fill_bars(pd.DataFrame(list(legs)), fine, coarse, slippage=0.25, fill_limit_on_touch=False)


SPARED = ((99.6, 100.2), (99.0, 99.8), (99.6, 101.0))
"""A bar whose low is nearer its open than its high, so the path reaches the low before the high
the entry fills on, while its minutes reach the low after the fill."""


def test_a_stop_entry_fills_in_the_first_minute_that_trades_through_its_trigger() -> None:
    fine, coarse = a_bar((99.0, 99.5), (99.2, 100.1), (100.0, 100.5))
    assert fill_minute(fine, coarse.iloc[0], 100.25, 0.25, LONG) == 1


def test_a_stop_entry_whose_bar_opened_past_its_trigger_held_the_whole_bar() -> None:
    """A gap fills at the open, so the whole bar was the trade's -- :func:`entry_minute`'s ``-1``."""
    fine, coarse = a_bar((101.0, 101.5), (100.5, 102.0))
    assert fill_minute(fine, coarse.iloc[0], 101.25, 0.25, LONG) == -1


def test_a_short_stop_entry_fills_where_a_low_trades_through_its_trigger() -> None:
    fine, coarse = a_bar((100.5, 101.0), (99.5, 100.5))
    assert fill_minute(fine, coarse.iloc[0], 99.75, 0.25, SHORT) == 1


def test_a_trigger_no_minute_traded_through_runs_off_the_end() -> None:
    fine, coarse = a_bar((99.0, 99.5), (99.2, 99.6))
    assert fill_minute(fine, coarse.iloc[0], 100.25, 0.25, LONG) == len(fine)


def test_a_walk_reaching_neither_level_returns_what_its_caller_names() -> None:
    """On an ambiguous bar that means a window off its bar; on a fill bar it is a leg held through."""
    window = minutes((99.0, 101.0), (98.0, 102.0))
    assert walk(window) == MISALIGNED
    assert walk(window, if_neither=HELD) == HELD


def test_the_paths_reading_comes_from_where_and_why_each_leg_left() -> None:
    assert simulated_outcome(3, 3, "stop") == STOP_FIRST
    assert simulated_outcome(3, 3, "target") == TARGET_FIRST
    assert simulated_outcome(3, 3, "session_close") == HELD
    assert simulated_outcome(4, 3, "stop") == HELD


def test_a_leg_the_path_held_that_the_minutes_stop_after_the_fill_is_spared() -> None:
    """The case the check exists for.

    The path puts the stop's extreme before the fill, while the minute bars put it after.
    """
    fine, coarse = a_bar(*SPARED)
    table = read(fine, coarse, a_leg())
    assert table[["simulated", "minute"]].iloc[0].tolist() == [HELD, STOP_FIRST]
    assert not bool(table["agrees"].iloc[0])
    assert fill_bar_accuracy(table)["path_spared"] == 1


def test_a_leg_both_readings_stop_on_its_fill_bar_agrees() -> None:
    fine, coarse = a_bar(*SPARED)
    table = read(fine, coarse, a_leg(exit_bar=0, exit_reason="stop", net=-20.0))
    assert table[["simulated", "minute"]].iloc[0].tolist() == [STOP_FIRST, STOP_FIRST]
    assert bool(table["agrees"].iloc[0])


def test_a_leg_the_minutes_take_to_its_target_after_the_fill_reads_target_first() -> None:
    fine, coarse = a_bar((99.6, 100.2), (100.0, 111.0), (99.0, 100.0))
    table = read(fine, coarse, a_leg(exit_bar=0, exit_reason="target"))
    assert table[["simulated", "minute"]].iloc[0].tolist() == [TARGET_FIRST, TARGET_FIRST]


def test_a_leg_reaching_neither_level_on_its_fill_bar_is_held_by_both_readings() -> None:
    fine, coarse = a_bar((99.6, 100.2), (99.8, 101.0))
    table = read(fine, coarse, a_leg())
    assert table[["simulated", "minute"]].iloc[0].tolist() == [HELD, HELD]
    assert bool(table["agrees"].iloc[0])


def test_a_stop_inside_the_fill_minute_cannot_be_ordered_against_the_fill() -> None:
    """A minute is the finest the data goes, so this is counted rather than scored."""
    fine, coarse = a_bar((99.4, 100.2), (99.8, 101.0))
    table = read(fine, coarse, a_leg())
    assert table["minute"].iloc[0] == STILL_AMBIGUOUS
    assert pd.isna(table["agrees"].iloc[0])


def test_a_fill_bar_whose_minutes_do_not_rebuild_it_is_refused_for_every_leg() -> None:
    fine, coarse = a_bar(*SPARED)
    shifted = coarse.assign(high=coarse["high"] + 5.0)
    table = read(fine, shifted, a_leg(), a_leg(leg=2))
    assert set(table["minute"]) == {MISALIGNED}
    assert fill_bar_accuracy(table)["refused"] == len(table)


def test_a_fill_no_minute_traded_through_is_refused_rather_than_walked() -> None:
    fine, coarse = a_bar((99.6, 99.9), (99.7, 99.95))
    assert read(fine, coarse, a_leg())["minute"].iloc[0] == ENTRY_UNLOCATED


def test_fill_bar_accuracy_scores_only_the_legs_both_readings_decided() -> None:
    """A leg a minute could not settle is not one the path got wrong."""
    spared_fine, spared_coarse = a_bar(*SPARED)
    open_fine, open_coarse = a_bar((99.4, 100.2), (99.8, 101.0))
    table = pd.concat(
        [
            read(spared_fine, spared_coarse, a_leg(net=50.0)),
            read(spared_fine, spared_coarse, a_leg(exit_bar=0, exit_reason="stop", net=-20.0)),
            read(open_fine, open_coarse, a_leg(net=30.0)),
        ],
        ignore_index=True,
    )
    counts = fill_bar_accuracy(table)
    assert counts["fill_bar_legs"] == 3
    assert counts["scored"] == 2
    assert counts["path_correct"] == 1
    assert counts["path_accuracy"] == pytest.approx(0.5)
    assert counts["path_spared"] == 1
    assert counts["spared_net"] == pytest.approx(50.0)
    assert counts["spared_share"] == pytest.approx(50.0 / 60.0)
    assert counts["path_stopped"] == 0
    assert counts["still_ambiguous"] == 1
    assert counts["refused"] == 0


def test_the_path_stopping_a_leg_the_minutes_hold_is_counted_the_other_way() -> None:
    fine, coarse = a_bar((99.6, 100.2), (99.8, 101.0))
    counts = fill_bar_accuracy(read(fine, coarse, a_leg(exit_bar=0, exit_reason="stop", net=-20.0)))
    assert counts["path_stopped"] == 1
    assert counts["path_spared"] == 0


def test_the_spared_share_is_undefined_where_the_legs_made_nothing() -> None:
    """A share of a loss reads as the opposite claim, so it is left undefined."""
    fine, coarse = a_bar(*SPARED)
    counts = fill_bar_accuracy(read(fine, coarse, a_leg(net=-50.0)))
    assert counts["path_spared"] == 1
    assert np.isnan(number(counts, "spared_share"))


def test_a_run_with_no_trade_reads_no_fill_bar_rather_than_raising() -> None:
    fine, coarse = a_bar(*SPARED)
    table = check_fill_bars(
        pd.DataFrame(columns=list(a_leg())), fine, coarse, slippage=0.25, fill_limit_on_touch=False
    )
    assert table.empty
    assert "agrees" in table.columns
    counts = fill_bar_accuracy(table)
    assert counts["fill_bar_legs"] == 0
    assert np.isnan(number(counts, "path_accuracy"))


def test_the_stop_entries_are_the_ones_the_simulation_walks_a_path_for() -> None:
    """Each archetype's ``OpenTrade.stop_entry``, case by case."""
    assert enters_on_stop(OpeningRangeParams(entry_mode=ORB_ENTRY_BREAKOUT))
    assert enters_on_stop(OpeningRangeParams(entry_mode=ORB_ENTRY_FADE, stop_mode=ORB_STOP_FRACTION))
    assert not enters_on_stop(OpeningRangeParams(entry_mode=ORB_ENTRY_RETEST))
    assert not enters_on_stop(OpeningRangeParams(entry_mode=ORB_ENTRY_REJECTION, stop_mode=ORB_STOP_FRACTION))
    assert enters_on_stop(EmaPullbackParams(confirm_entry=True))
    assert not enters_on_stop(EmaPullbackParams())
    for always in (DeadCatParams(), PullBackAndGoParams(), SqueezeBreakoutParams()):
        assert enters_on_stop(always), type(always).__name__
    for never in (InsideBarParams(), InsideBarTrailingParams(), ElasticBandParams(), EmaCrossoverParams()):
        assert not enters_on_stop(never), type(never).__name__


def test_every_registered_archetype_has_its_entries_classified() -> None:
    """A new archetype has to be placed on one side, or its fill bars are silently never read."""
    classified = {
        DeadCatParams,
        PullBackAndGoParams,
        SqueezeBreakoutParams,
        OpeningRangeParams,
        EmaPullbackParams,
        InsideBarParams,
        InsideBarTrailingParams,
        ElasticBandParams,
        EmaCrossoverParams,
    }
    assert {archetypes.get(name).params_cls for name in archetypes.names()} == classified


def stop_entry_run() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, float]:
    """Run DeadCatBounce's stop entries on 5-minute bars built from the synthetic minutes."""
    fine = synthetic_bars()
    coarse = resample.resample(fine, 5)
    base = DeadCatParams(
        use_ema=False,
        use_fast_sma=False,
        require_previous_green=False,
        require_new_high=False,
        bars_required_to_trade=0,
    )
    spec = sweep.Grid(base=base, archetype=archetypes.DEADCATBOUNCE).required_context()
    data = context.prepare(coarse, spec, bar_minutes=5)
    instrument = get_instrument("MNQ")
    _, log = sweep.run_combination(data, base, instrument, archetypes.DEADCATBOUNCE, keep_trades=True)
    assert log is not None

    return log, fine, coarse, base.slippage_ticks * instrument.tick_size


def test_every_leg_of_a_real_stop_entry_run_is_read_on_its_own_fill_bar() -> None:
    """The end-to-end claim: real fills line up with their minutes and get a reading."""
    log, fine, coarse, slippage = stop_entry_run()
    assert not log.empty, "fixture produced no trades; the test proves nothing"

    table = check_fill_bars(log, fine, coarse, slippage=slippage, fill_limit_on_touch=False)
    assert len(table) == len(log)
    assert table["minute"].isin(FILL_BAR_SCORED).any(), "nothing was scored; the test proves nothing"
    assert not (table["minute"] == ENTRY_UNLOCATED).any(), "every real fill traded through its trigger"
    assert not (table["minute"] == MISALIGNED).any(), "every real fill bar is rebuilt by its own minutes"
