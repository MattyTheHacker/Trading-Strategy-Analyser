"""Tests for the random-entry control arm.

The tests that matter here are not "does it return a number" but **is the null a fair
control**: does it match what it claims to match, does it randomise what it claims to
randomise, and does it report "no signal" on data that provably has none. A null that is
subtly easier than the strategy makes every archetype look good, and nothing downstream
would say so.
"""

from __future__ import annotations

import collections

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, randomentry, sessions, stats, sweep
from nqbt.instruments import NQ
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams


def session_bars(days: int = 30, seed: int = 11) -> pd.DataFrame:
    """Minute bars laid out on real CME sessions rather than a bare date range.

    Session-shaped on purpose: the whole point of the null is the time-of-session marginal,
    and a fixture that ignores sessions would let a broken anchoring pass.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-02 00:00", periods=days * 1440, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, len(index)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, len(index)))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.5, len(index)))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(1, 500, len(index)).astype(float),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day
    return frame


@pytest.fixture(scope="module")
def prepared():
    bars = session_bars()
    params = DeadCatParams(bars_required_to_trade=200)
    data = sweep.prepare_for(bars, sweep.Grid.of(params))
    signal = archetypes.DEADCATBOUNCE.signal(data, params)
    assert signal.sum() > 50, "fixture produced too few signals; the tests prove little"
    return data, params, signal


# -- what the null matches, and what it does not ------------------------------


def test_the_null_draws_exactly_as_many_entries_as_the_strategy(prepared) -> None:
    data, _, signal = prepared
    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    assert int(drawn.sum()) == int(signal.sum())


def test_the_time_of_session_distribution_is_matched_exactly_not_approximately(prepared) -> None:
    """The substantive guarantee. Approximate matching would leave the confound in place.

    Intraday futures volatility is strongly seasonal, and a fixed-tick bracket has different
    hit probabilities in a volatile hour than a thin one -- so a null that drifted even
    slightly toward the quiet overnight session would lose for a reason unrelated to entry
    quality, and would flatter every strategy tested against it.
    """
    data, _, signal = prepared
    minutes = randomentry.minute_of_session(data.index)
    for seed in range(5):
        drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(seed))
        assert collections.Counter(minutes[drawn]) == collections.Counter(minutes[signal])


def test_the_null_actually_moves_the_entries_it_is_supposed_to_randomise(prepared) -> None:
    """Guards the guard: returning the strategy's own signal would pass every match test."""
    data, _, signal = prepared
    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    shared = int((signal & drawn).sum())
    assert shared < int(signal.sum()) * 0.5, "the draw barely moved; it is not a null"


def test_two_seeds_give_two_different_draws(prepared) -> None:
    data, _, signal = prepared
    a = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    b = randomentry.matched_random_signal(data, signal, np.random.default_rng(1))
    assert (a != b).any()


def test_one_seed_gives_the_same_draw_twice(prepared) -> None:
    data, _, signal = prepared
    a = randomentry.matched_random_signal(data, signal, np.random.default_rng(7))
    b = randomentry.matched_random_signal(data, signal, np.random.default_rng(7))
    assert np.array_equal(a, b)


def test_no_two_entries_land_on_the_same_bar(prepared) -> None:
    """Drawing without replacement is what makes the count exact rather than expected."""
    data, _, signal = prepared
    for seed in range(5):
        drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(seed))
        assert int(drawn.sum()) == int(signal.sum())


def test_the_pool_is_never_smaller_than_the_draw_it_must_serve(prepared) -> None:
    """The structural guarantee behind drawing without replacement.

    Every real signal at minute *m* is itself one of the bars at minute *m*, so the pool is a
    superset of what is being drawn from it. Asserted rather than trusted because it is what
    lets the implementation skip a resample-on-collision loop.
    """
    data, _, signal = prepared
    pool = randomentry.SessionMinutePool.build(data.index)
    minutes, counts = np.unique(pool.minutes[signal], return_counts=True)
    for minute, count in zip(minutes, counts):
        assert pool.pool_for(minute).size >= count, f"minute {minute}"


def test_the_hoisted_pool_gives_the_same_draw_as_building_it_inline(prepared) -> None:
    """The optimisation is a 12x speedup on the draw, so it must not change the draw."""
    data, _, signal = prepared
    pool = randomentry.SessionMinutePool.build(data.index)
    with_pool = randomentry.matched_random_signal(data, signal, np.random.default_rng(3), pool=pool)
    without = randomentry.matched_random_signal(data, signal, np.random.default_rng(3))
    assert np.array_equal(with_pool, without)


# -- the null is a control, which means it runs the strategy's own machinery ---


def test_the_null_runs_the_archetypes_own_simulation_not_a_copy(prepared) -> None:
    """Feeding the real signal back through the override must reproduce the real run.

    This is the property that makes the comparison meaningful: brackets, ratchet, costs,
    force-flat and direction are identical between arms because they are literally the same
    call, not because two implementations were reviewed and found to agree.
    """
    data, params, signal = prepared
    normal = archetypes.DEADCATBOUNCE.run(data, params, NQ)
    injected = archetypes.DEADCATBOUNCE.run(data, params, NQ, signal=signal)
    pd.testing.assert_frame_equal(normal, injected)


def test_every_archetype_exposes_the_signal_the_null_needs() -> None:
    """A new archetype that forgets this cannot be given a control arm at all."""
    for archetype in archetypes.all_archetypes():
        assert callable(archetype.signal), archetype.name


def test_the_null_keeps_the_direction_of_the_archetype_it_controls() -> None:
    """A long-only null against a bidirectional archetype measures market drift.

    Direction is matched here by construction rather than by a parameter, because the null
    calls the archetype's own run function and the direction constant lives inside it.
    """
    bars = session_bars()
    params = PullBackAndGoParams(bars_required_to_trade=200)
    data = sweep.prepare_for(bars, sweep.Grid.of(params))
    signal = archetypes.PULLBACKANDGO.signal(data, params)
    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    log = archetypes.PULLBACKANDGO.run(data, params, NQ, signal=drawn)
    assert len(log), "the null traded nothing; the test proves nothing"
    from nqbt import trades

    assert (log["direction"] == trades.LONG).all()


# -- calibration: does it say "nothing" when there is nothing? -----------------


def test_a_strategy_with_no_edge_reads_as_indistinguishable_from_random(prepared) -> None:
    """The calibration check, and the one that would catch a rigged null.

    These are random-walk bars, so no entry rule can have predictive power over them and the
    honest answer is "indistinguishable". A null that were systematically easier than the
    strategy would instead report "better than random" here, which is precisely the failure
    that would make every real result untrustworthy.
    """
    data, params, _ = prepared
    results = randomentry.compare(data, params, instrument=NQ, iterations=120, seed=5)
    assert results["profit_factor"].verdict == randomentry.INDISTINGUISHABLE
    assert results["win_rate"].verdict == randomentry.INDISTINGUISHABLE


def test_the_observed_value_sits_inside_the_null_range_on_random_bars(prepared) -> None:
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=120, seed=5)
    pf = got["profit_factor"]
    assert pf.null_p05 <= pf.observed <= pf.null_p95


# -- the arithmetic of placing an observation ---------------------------------


def test_an_observation_above_every_draw_is_better_than_random() -> None:
    draws = np.linspace(0.0, 1.0, 200)
    got = randomentry._place(
        "profit_factor",
        5.0,
        draws,
        0.05,
        200,
        observed_trades=100,
        null_median_trades=100.0,
    )
    assert got.verdict == randomentry.BETTER
    assert got.percentile == 100.0


def test_an_observation_below_every_draw_is_worse_than_random() -> None:
    """Both tails are reported, and this is why.

    An entry rule reading *worse* than random carries real information pointing the wrong
    way, which is a finding. A one-sided test would file it as an unremarkable failure.
    """
    draws = np.linspace(0.0, 1.0, 200)
    got = randomentry._place(
        "profit_factor",
        -3.0,
        draws,
        0.05,
        200,
        observed_trades=100,
        null_median_trades=100.0,
    )
    assert got.verdict == randomentry.WORSE
    assert got.percentile == 0.0


def test_an_observation_in_the_middle_is_indistinguishable() -> None:
    draws = np.linspace(0.0, 1.0, 200)
    got = randomentry._place(
        "profit_factor",
        0.5,
        draws,
        0.05,
        200,
        observed_trades=100,
        null_median_trades=100.0,
    )
    assert got.verdict == randomentry.INDISTINGUISHABLE


def test_the_p_value_never_claims_more_certainty_than_the_draws_support() -> None:
    """No draw beat the observation, but 50 draws cannot support p = 0.

    The add-one correction puts the floor at 1/(n+1). Without it a Monte Carlo test reports
    impossibility from a sample that merely never happened to exceed the observation.
    """
    draws = np.linspace(0.0, 1.0, 50)
    got = randomentry._place(
        "profit_factor",
        99.0,
        draws,
        0.05,
        50,
        observed_trades=10,
        null_median_trades=10.0,
    )
    assert got.p_value > 0.0
    assert got.p_value == pytest.approx(2.0 / 51.0)


def test_a_wider_null_makes_the_same_observation_less_significant() -> None:
    """Effect size is not significance: the spread of the null decides."""
    observed = 1.5
    tight = randomentry._place(
        "profit_factor",
        observed,
        np.linspace(0.9, 1.1, 200),
        0.05,
        200,
        observed_trades=10,
        null_median_trades=10.0,
    )
    wide = randomentry._place(
        "profit_factor",
        observed,
        np.linspace(-5.0, 8.0, 200),
        0.05,
        200,
        observed_trades=10,
        null_median_trades=10.0,
    )
    assert tight.verdict == randomentry.BETTER
    assert wide.verdict == randomentry.INDISTINGUISHABLE


# -- count sensitivity, which the fill-rate gap makes real ---------------------


def test_count_sensitive_statistics_are_flagged_and_rate_ones_are_not(prepared) -> None:
    data, params, _ = prepared
    got = randomentry.compare(
        data,
        params,
        instrument=NQ,
        iterations=30,
        statistics=("profit_factor", "net_pnl"),
    )
    assert got["profit_factor"].count_sensitive is False
    assert got["net_pnl"].count_sensitive is True


def test_every_comparison_reports_both_trade_counts(prepared) -> None:
    """The arms match on signals and diverge on fills, so the counts are never noise."""
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=30)
    for result in got.values():
        assert result.observed_trades > 0
        assert result.null_median_trades > 0


def test_the_default_statistics_are_the_ones_trade_count_divides_out_of() -> None:
    assert randomentry.RATE_STATISTICS == ("profit_factor", "expectancy", "win_rate")
    assert not set(randomentry.RATE_STATISTICS) & randomentry.COUNT_SENSITIVE


# -- reproducibility and parallelism ------------------------------------------


def test_the_null_distribution_is_reproducible_from_its_seed(prepared) -> None:
    data, params, _ = prepared
    a = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    b = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_a_different_seed_gives_a_different_null(prepared) -> None:
    data, params, _ = prepared
    a = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    b = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=4)
    assert not a["profit_factor"].equals(b["profit_factor"])


def test_parallel_draws_match_serial_exactly(prepared) -> None:
    """``n_jobs`` may change the wall clock and nothing else."""
    data, params, _ = prepared
    serial = randomentry.null_summaries(data, params, instrument=NQ, iterations=8, n_jobs=1)
    parallel = randomentry.null_summaries(data, params, instrument=NQ, iterations=8, n_jobs=2)
    pd.testing.assert_frame_equal(serial, parallel)


def test_one_row_per_iteration_carrying_the_whole_summary(prepared) -> None:
    data, params, _ = prepared
    null = randomentry.null_summaries(data, params, instrument=NQ, iterations=12)
    assert len(null) == 12
    assert set(stats.Summary.columns()) <= set(null.columns)


# -- refusals ------------------------------------------------------------------


def test_a_strategy_with_no_signals_refuses_rather_than_returning_a_null(prepared) -> None:
    """Zero signals is a wiring or warm-up bug, and a null against nothing means nothing."""
    data, _, _ = prepared
    empty = np.zeros(len(data), dtype=bool)
    with pytest.raises(randomentry.RandomEntryError, match="no entry signals"):
        randomentry.matched_random_signal(data, empty, np.random.default_rng(0))


def test_a_signal_of_the_wrong_length_is_refused(prepared) -> None:
    data, _, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="per-bar"):
        randomentry.matched_random_signal(data, np.zeros(7, dtype=bool), np.random.default_rng(0))


def test_an_unknown_statistic_names_what_is_available(prepared) -> None:
    data, params, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="not statistics of a Summary"):
        randomentry.compare(data, params, instrument=NQ, iterations=5, statistics=("alpha",))


def test_zero_iterations_is_refused(prepared) -> None:
    data, params, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="at least 1"):
        randomentry.null_summaries(data, params, instrument=NQ, iterations=0)


def stub_log(pnl_per_trade) -> pd.DataFrame:
    """A minimal leg-level log that :func:`nqbt.stats.summarise` will accept."""
    base = pd.Timestamp("2024-01-02 10:00", tz="UTC")
    return pd.DataFrame(
        {
            "trade_id": range(1, len(pnl_per_trade) + 1),
            "leg": 1,
            "net_pnl": list(pnl_per_trade),
            "commission": 0.5,
            "bars_held": 3,
            "mae_points": 1.0,
            "mfe_points": 2.0,
            "r_multiple": [p / 10.0 for p in pnl_per_trade],
            "ambiguous_bar": False,
            "exit_reason": "target",
            "entry_time": [base + pd.Timedelta(days=i) for i in range(len(pnl_per_trade))],
            "exit_time": [base + pd.Timedelta(days=i, minutes=5) for i in range(len(pnl_per_trade))],
        }
    )


def test_an_infinite_observed_statistic_is_refused_rather_than_compared(prepared) -> None:
    """A run with no losing trade reports an infinite profit factor.

    "Infinity beats the null" is an artefact of a run with nothing on the other side of the
    ratio, not a result, and returning it would put a meaningless row in the same table as
    real ones.

    Driven by a stub archetype rather than a lucky fixture: no random-walk seed produces an
    all-winning DeadCatBounce run, so a data-driven version of this test would skip forever
    and assert nothing.
    """
    data, params, signal = prepared

    def all_wins_when_real(data_, params_, instrument=NQ, *, signal=None, **kwargs):
        # Observed run: no losses at all, so profit factor is infinite. Null draws keep a
        # loser, so the null distribution itself stays finite and the refusal is about the
        # observation rather than about an empty comparison.
        return stub_log([5.0] * 8) if signal is None else stub_log([5.0] * 6 + [-4.0] * 2)

    probe = archetypes.Archetype(
        name="AllWinsProbe",
        params_cls=DeadCatParams,
        run=all_wins_when_real,
        signal=lambda d, p: signal,
        tier2=archetypes.Tier2Status.TIER1_ONLY,
    )
    assert np.isinf(stats.summarise(all_wins_when_real(data, params)).profit_factor)
    with pytest.raises(randomentry.RandomEntryError, match="no losing trade"):
        randomentry.compare(data, params, probe, NQ, iterations=5)


def test_a_null_that_is_mostly_infinite_is_refused_rather_than_averaged(prepared) -> None:
    """The mirror of the previous test: the *null* is what has nothing to divide by.

    Dropping the infinite draws and comparing against the two that survived would put a
    confident percentile on a distribution that does not exist.
    """
    data, params, signal = prepared

    def wins_only_in_the_null(data_, params_, instrument=NQ, *, signal=None, **kwargs):
        return stub_log([5.0, -4.0]) if signal is None else stub_log([5.0] * 4)

    probe = archetypes.Archetype(
        name="InfiniteNullProbe",
        params_cls=DeadCatParams,
        run=wins_only_in_the_null,
        signal=lambda d, p: signal,
        tier2=archetypes.Tier2Status.TIER1_ONLY,
    )
    with pytest.raises(randomentry.RandomEntryError, match="no distribution"):
        randomentry.compare(data, params, probe, NQ, iterations=5)


def test_report_gives_one_row_per_statistic(prepared) -> None:
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=20)
    frame = randomentry.report(got)
    assert list(frame["statistic"]) == list(randomentry.RATE_STATISTICS)
    assert {"verdict", "p_value", "percentile", "count_sensitive"} <= set(frame.columns)
