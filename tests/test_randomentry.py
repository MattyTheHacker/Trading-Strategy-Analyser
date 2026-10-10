"""Tests for the random-entry control arm.

Whether the null is a fair control: it matches what it claims to match, randomises what it
claims to randomise, and reports "no signal" on data that provably has none --
``docs/roadmap.md`` §M7a.
"""

from __future__ import annotations

import collections
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, randomentry, sessions, stats, sweep, trades
from nqbt.instruments import NQ
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams

if TYPE_CHECKING:
    from nqbt import context
    from nqbt.arrays import BoolArray
    from nqbt.instruments import Instrument


def session_bars(days: int = 30, seed: int = 11) -> pd.DataFrame:
    """Build minute bars laid out on real CME sessions rather than a bare date range.

    Session-shaped, so a broken time-of-session anchoring cannot pass.
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


type Prepared = tuple[context.Dataset, DeadCatParams, BoolArray]
"""The dataset, the configuration run on it and that configuration's signal."""


@pytest.fixture(scope="module")
def prepared() -> Prepared:
    bars = session_bars()
    params = DeadCatParams(bars_required_to_trade=200)
    data = sweep.prepare_for(bars, sweep.Grid.of(params))
    signal = archetypes.DEADCATBOUNCE.signal(data, params)
    assert signal.sum() > 50, "fixture produced too few signals; the tests prove little"

    return data, params, signal


# -- what the null matches, and what it does not ------------------------------


def test_the_null_draws_exactly_as_many_entries_as_the_strategy(
    prepared: Prepared,
) -> None:
    data, _, signal = prepared
    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    assert int(drawn.sum()) == int(signal.sum())


def test_the_time_of_session_distribution_is_matched_exactly_not_approximately(
    prepared: Prepared,
) -> None:
    """The drawn signal matches the real one's minute-of-session counts exactly, not approximately."""
    data, _, signal = prepared
    minutes = randomentry.minute_of_session(data.index)
    for seed in range(5):
        drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(seed))
        assert collections.Counter(minutes[drawn]) == collections.Counter(minutes[signal])


def test_the_null_actually_moves_the_entries_it_is_supposed_to_randomise(
    prepared: Prepared,
) -> None:
    """Guards the guard: returning the strategy's own signal would pass every match test."""
    data, _, signal = prepared
    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    shared = int((signal & drawn).sum())
    assert shared < int(signal.sum()) * 0.5, "the draw barely moved; it is not a null"


def test_two_seeds_give_two_different_draws(
    prepared: Prepared,
) -> None:
    data, _, signal = prepared
    a = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))
    b = randomentry.matched_random_signal(data, signal, np.random.default_rng(1))
    assert (a != b).any()


def test_one_seed_gives_the_same_draw_twice(
    prepared: Prepared,
) -> None:
    data, _, signal = prepared
    a = randomentry.matched_random_signal(data, signal, np.random.default_rng(7))
    b = randomentry.matched_random_signal(data, signal, np.random.default_rng(7))
    assert np.array_equal(a, b)


def test_no_two_entries_land_on_the_same_bar(
    prepared: Prepared,
) -> None:
    """Drawing without replacement is what makes the count exact rather than expected."""
    data, _, signal = prepared
    for seed in range(5):
        drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(seed))
        assert int(drawn.sum()) == int(signal.sum())


def test_the_pool_is_never_smaller_than_the_draw_it_must_serve(
    prepared: Prepared,
) -> None:
    """The structural guarantee behind drawing without replacement.

    Every real signal at minute *m* is itself one of the bars at minute *m*, so the pool is a
    superset of what is being drawn from it.
    """
    data, _, signal = prepared
    pool = randomentry.SessionMinutePool.build(data.index)
    minutes, counts = np.unique(pool.minutes[signal], return_counts=True)
    for minute, count in zip(minutes, counts, strict=True):
        assert pool.pool_for(minute).size >= count, f"minute {minute}"


def test_the_hoisted_pool_gives_the_same_draw_as_building_it_inline(
    prepared: Prepared,
) -> None:
    """The optimisation is a 12x speedup on the draw, so it must not change the draw."""
    data, _, signal = prepared
    pool = randomentry.SessionMinutePool.build(data.index)
    with_pool = randomentry.matched_random_signal(data, signal, np.random.default_rng(3), pool=pool)
    without = randomentry.matched_random_signal(data, signal, np.random.default_rng(3))
    assert np.array_equal(with_pool, without)


# -- the null is a control, which means it runs the strategy's own machinery ---


def test_the_null_runs_the_archetypes_own_simulation_not_a_copy(
    prepared: Prepared,
) -> None:
    """Feeding the real signal back through the override must reproduce the real run.

    Brackets, ratchet, costs, force-flat and direction are identical between the arms because
    they are the same call.
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

    assert (log["direction"] == trades.LONG).all()


# -- calibration: does it say "nothing" when there is nothing? -----------------


def test_a_strategy_with_no_edge_reads_as_indistinguishable_from_random(
    prepared: Prepared,
) -> None:
    """On random-walk bars the verdict is "indistinguishable", which a rigged null would not give."""
    data, params, _ = prepared
    results = randomentry.compare(data, params, instrument=NQ, iterations=120, seed=5)
    assert results["profit_factor"].verdict == randomentry.INDISTINGUISHABLE
    assert results["win_rate"].verdict == randomentry.INDISTINGUISHABLE


def test_the_observed_value_sits_inside_the_null_range_on_random_bars(
    prepared: Prepared,
) -> None:
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


def test_count_sensitive_statistics_are_flagged_and_rate_ones_are_not(
    prepared: Prepared,
) -> None:
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


def test_every_comparison_reports_both_trade_counts(
    prepared: Prepared,
) -> None:
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


def test_the_null_distribution_is_reproducible_from_its_seed(
    prepared: Prepared,
) -> None:
    data, params, _ = prepared
    a = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    b = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_a_different_seed_gives_a_different_null(
    prepared: Prepared,
) -> None:
    data, params, _ = prepared
    a = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    b = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=4)
    assert not a["profit_factor"].equals(b["profit_factor"])


def test_parallel_draws_match_serial_exactly(
    prepared: Prepared,
) -> None:
    """``n_jobs`` may change the wall clock and nothing else."""
    data, params, _ = prepared
    serial = randomentry.null_summaries(data, params, instrument=NQ, iterations=8, n_jobs=1)
    parallel = randomentry.null_summaries(data, params, instrument=NQ, iterations=8, n_jobs=2)
    pd.testing.assert_frame_equal(serial, parallel)


def test_one_row_per_iteration_carrying_the_whole_summary(
    prepared: Prepared,
) -> None:
    data, params, _ = prepared
    null = randomentry.null_summaries(data, params, instrument=NQ, iterations=12)
    assert len(null) == 12
    assert set(stats.Summary.columns()) <= set(null.columns)


# -- refusals ------------------------------------------------------------------


def test_a_strategy_with_no_signals_refuses_rather_than_returning_a_null(
    prepared: Prepared,
) -> None:
    """Zero signals is a wiring or warm-up bug, and a null against nothing means nothing."""
    data, _, _ = prepared
    empty = np.zeros(len(data), dtype=bool)
    with pytest.raises(randomentry.RandomEntryError, match="no entry signals"):
        randomentry.matched_random_signal(data, empty, np.random.default_rng(0))


def test_a_signal_of_the_wrong_length_is_refused(
    prepared: Prepared,
) -> None:
    data, _, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="per-bar"):
        randomentry.matched_random_signal(data, np.zeros(7, dtype=bool), np.random.default_rng(0))


def test_an_unknown_statistic_names_what_is_available(
    prepared: Prepared,
) -> None:
    data, params, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="not statistics of a Summary"):
        randomentry.compare(data, params, instrument=NQ, iterations=5, statistics=("alpha",))


def test_zero_iterations_is_refused(prepared: Prepared) -> None:
    data, params, _ = prepared
    with pytest.raises(randomentry.RandomEntryError, match="at least 1"):
        randomentry.null_summaries(data, params, instrument=NQ, iterations=0)


def stub_log(pnl_per_trade: list[float]) -> pd.DataFrame:
    """Build a minimal leg-level log that :func:`nqbt.stats.summarise` will accept."""
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
        },
    )


def stub_legs(pnl_per_trade: list[float]) -> trades.LegMatrix:
    """Build the same stub as a raw leg matrix, which is what ``compare`` actually reads."""
    matrix = np.zeros((len(pnl_per_trade), trades.N_COLUMNS))
    matrix[:, trades.C_TRADE_ID] = np.arange(1, len(pnl_per_trade) + 1)
    matrix[:, trades.C_LEG] = 1
    matrix[:, trades.C_EXIT_BAR] = np.arange(len(pnl_per_trade))
    matrix[:, trades.C_NET_PNL] = pnl_per_trade
    matrix[:, trades.C_R_MULTIPLE] = np.asarray(pnl_per_trade) / 10.0
    matrix[:, trades.C_COMMISSION] = 0.5
    matrix[:, trades.C_BARS_HELD] = 3
    matrix[:, trades.C_MAE] = 1.0
    matrix[:, trades.C_MFE] = 2.0
    matrix[:, trades.C_QUANTITY] = 1
    matrix[:, trades.C_DIRECTION] = trades.SHORT
    matrix[:, trades.C_EXIT_REASON] = trades.EXIT_TARGET

    return trades.LegMatrix(matrix, len(pnl_per_trade))


def test_an_infinite_observed_statistic_is_refused_rather_than_compared(
    prepared: Prepared,
) -> None:
    """An infinite observed profit factor is refused rather than compared with the null.

    Driven by a stub archetype, because no random-walk seed produces an all-winning
    DeadCatBounce run.
    """
    data, params, signal = prepared

    def all_wins_when_real(
        _data: context.Dataset,
        _params: DeadCatParams,
        _instrument: Instrument = NQ,
        *,
        signal: BoolArray | None = None,
        **_kwargs: object,
    ) -> pd.DataFrame:
        # Observed run: no losses at all, so profit factor is infinite. Null draws keep a
        # loser, so the null distribution itself stays finite and the refusal is about the
        # observation rather than about an empty comparison.
        return stub_log([5.0] * 8) if signal is None else stub_log([5.0] * 6 + [-4.0] * 2)

    def all_wins_legs(
        _data: context.Dataset,
        _params: DeadCatParams,
        _instrument: Instrument = NQ,
        *,
        signal: BoolArray | None = None,
        **_kwargs: object,
    ) -> trades.LegMatrix:
        return stub_legs([5.0] * 8) if signal is None else stub_legs([5.0] * 6 + [-4.0] * 2)

    probe = archetypes.Archetype(
        name="AllWinsProbe",
        params_cls=DeadCatParams,
        run=all_wins_when_real,
        legs=all_wins_legs,
        signal=lambda _d, _p: signal,
        long_side=archetypes.DEADCATBOUNCE.long_side,
        tier2=archetypes.Tier2Status.TIER1_ONLY,
    )
    assert np.isinf(stats.summarise(all_wins_when_real(data, params)).profit_factor)
    with pytest.raises(randomentry.RandomEntryError, match="no losing trade"):
        randomentry.compare(data, params, probe, NQ, iterations=5)


def test_a_null_that_is_mostly_infinite_is_refused_rather_than_averaged(
    prepared: Prepared,
) -> None:
    """The mirror of the previous test: the *null* is what has nothing to divide by.

    Dropping the infinite draws and comparing against the two that survived would put a
    confident percentile on a distribution that does not exist.
    """
    data, params, signal = prepared

    def wins_only_in_the_null(
        _data: context.Dataset,
        _params: DeadCatParams,
        _instrument: Instrument = NQ,
        *,
        signal: BoolArray | None = None,
        **_kwargs: object,
    ) -> pd.DataFrame:
        return stub_log([5.0, -4.0]) if signal is None else stub_log([5.0] * 4)

    def wins_only_in_the_null_legs(
        _data: context.Dataset,
        _params: DeadCatParams,
        _instrument: Instrument = NQ,
        *,
        signal: BoolArray | None = None,
        **_kwargs: object,
    ) -> trades.LegMatrix:
        return stub_legs([5.0, -4.0]) if signal is None else stub_legs([5.0] * 4)

    probe = archetypes.Archetype(
        name="InfiniteNullProbe",
        params_cls=DeadCatParams,
        run=wins_only_in_the_null,
        legs=wins_only_in_the_null_legs,
        signal=lambda _d, _p: signal,
        long_side=archetypes.DEADCATBOUNCE.long_side,
        tier2=archetypes.Tier2Status.TIER1_ONLY,
    )
    with pytest.raises(randomentry.RandomEntryError, match="no distribution"):
        randomentry.compare(data, params, probe, NQ, iterations=5)


def test_report_gives_one_row_per_statistic(
    prepared: Prepared,
) -> None:
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=20)
    frame = randomentry.report(got)
    assert list(frame["statistic"]) == list(randomentry.RATE_STATISTICS)
    assert {"verdict", "p_value", "percentile", "count_sensitive"} <= set(frame.columns)


# -- the draw that cannot randomise anything -----------------------------------


def test_a_signal_filling_every_pool_it_touches_is_refused_rather_than_drawn(
    prepared: Prepared,
) -> None:
    """Drawing without replacement from a pool the signal already fills returns that signal.

    Left unguarded the null is the observation, reported as a p-value of 1 and read as
    "indistinguishable from random". OpeningRange's trigger is a level rather than an event,
    so it fires on every armed bar and reaches this -- ``docs/roadmap.md`` §M28.1.
    """
    data, _, _ = prepared
    every_bar = np.ones(len(data), dtype=bool)

    with pytest.raises(randomentry.RandomEntryError, match="spare bars"):
        randomentry.matched_random_signal(data, every_bar, np.random.default_rng(0))


def test_a_nearly_saturated_signal_is_refused_too(
    prepared: Prepared,
) -> None:
    """A signal leaving a sliver of spare bars is refused too, not only a saturating one.

    ``docs/roadmap.md`` §M28.1.
    """
    data, _, _ = prepared
    nearly_every_bar = np.ones(len(data), dtype=bool)
    nearly_every_bar[:: len(data) // 3] = False

    pool = randomentry.SessionMinutePool.build(data.index)
    freedom = pool.draw_freedom(nearly_every_bar)
    assert 0.0 < freedom < randomentry.MIN_DRAW_FREEDOM, "premise gone; rewrite this test"

    with pytest.raises(randomentry.RandomEntryError, match="spare bars"):
        randomentry.matched_random_signal(data, nearly_every_bar, np.random.default_rng(0))


def test_draw_freedom_separates_the_registry_from_the_degenerate_case(
    prepared: Prepared,
) -> None:
    """The cut is meaningful because nothing real sits near it -- ``docs/roadmap.md`` §M28.1."""
    data, _, signal = prepared
    pool = randomentry.SessionMinutePool.build(data.index)

    assert pool.draw_freedom(signal) > randomentry.MIN_DRAW_FREEDOM
    assert pool.draw_freedom(np.ones(len(data), dtype=bool)) == 0.0
    assert pool.draw_freedom(np.zeros(len(data), dtype=bool)) == 0.0


def test_a_null_whose_draws_all_agree_is_refused_from_the_result_side(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second guard: the same failure seen from the result, whatever caused the point mass.

    The draw-freedom check catches the dense-signal cause before the simulations run; this one
    holds for any cause.
    """
    data, params, _ = prepared
    monkeypatch.setattr(
        randomentry,
        "null_summaries",
        lambda *_args, **_kwargs: pd.DataFrame({"profit_factor": [1.5] * 4, "trades": [10] * 4}),
    )

    with pytest.raises(randomentry.RandomEntryError, match="randomised nothing"):
        randomentry.compare(data, params, statistics=("profit_factor",), iterations=4)


def test_a_sparse_signal_still_draws_and_still_moves(
    prepared: Prepared,
) -> None:
    """The guard must not fire for the archetypes it was not written for."""
    data, _, signal = prepared

    drawn = randomentry.matched_random_signal(data, signal, np.random.default_rng(0))

    assert drawn.sum() == signal.sum()
    assert not np.array_equal(drawn, signal), "the draw randomised nothing"


def test_spare_bars_counts_the_room_the_draw_has(
    prepared: Prepared,
) -> None:
    """One bar short of saturation is still a legal draw, which is where the boundary is."""
    data, _, _ = prepared
    pool = randomentry.SessionMinutePool.build(data.index)
    minutes, counts = np.unique(pool.minutes, return_counts=True)

    assert pool.spare_bars(minutes, counts) == 0, "every bar of every minute is every bar"
    assert pool.spare_bars(minutes, counts - 1) == len(minutes)


def test_the_refusal_survives_the_parallel_path_as_the_same_exception(
    prepared: Prepared,
) -> None:
    """``tools/campaign_null.py`` catches ``RandomEntryError`` to report gate 3 as not run.

    joblib reconstructs a worker's exception rather than re-raising it, so the type surviving
    the round trip is what that catch depends on.
    """
    data, params, _ = prepared
    every_bar = np.ones(len(data), dtype=bool)

    def dense(*_args: object, **_kwargs: object) -> BoolArray:
        return every_bar

    for jobs in (1, 2):
        with pytest.raises(randomentry.RandomEntryError, match="spare bars"):
            randomentry.null_summaries(
                data,
                params,
                replace(archetypes.DEADCATBOUNCE, signal=dense),
                iterations=2,
                n_jobs=jobs,
            )


# -- the draws kept, and the family-wise null over them --------------------------


def test_every_draw_is_kept_in_seed_order_beside_the_summary(prepared: Prepared) -> None:
    """The draws are the null's own rows, non-finite ones included, so two results can line up."""
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=20, seed=3)
    null = randomentry.null_summaries(data, params, instrument=NQ, iterations=20, seed=3)
    for name, result in got.items():
        assert np.array_equal(result.draws, null[name].to_numpy(dtype=float), equal_nan=True)


def test_the_report_leaves_the_draws_out(prepared: Prepared) -> None:
    data, params, _ = prepared
    got = randomentry.compare(data, params, instrument=NQ, iterations=20)
    assert "draws" not in randomentry.report(got).columns
    assert "draws" not in next(iter(got.values())).as_dict()


SPREAD_DRAWS = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
"""Median 3 and a median absolute deviation of 1, so the robust spread is the scale alone."""


def test_the_excess_is_measured_from_the_null_median_in_robust_spreads() -> None:
    observed, draws = randomentry.standardised_excess(6.0, SPREAD_DRAWS)
    assert observed == pytest.approx(3.0 / randomentry.ROBUST_SPREAD_SCALE)
    assert draws == pytest.approx((SPREAD_DRAWS - 3.0) / randomentry.ROBUST_SPREAD_SCALE)


def test_the_excess_is_the_same_whatever_scale_and_level_the_statistic_has() -> None:
    """What makes two cells' tests comparable: a null twice as wide halves the same excess."""
    observed, draws = randomentry.standardised_excess(6.0, SPREAD_DRAWS)
    moved, moved_draws = randomentry.standardised_excess(6.0 * 4.0 + 7.0, SPREAD_DRAWS * 4.0 + 7.0)
    assert moved == pytest.approx(observed)
    assert moved_draws == pytest.approx(draws)


def test_a_non_finite_draw_keeps_its_place_without_moving_the_centre_or_the_spread() -> None:
    with_gaps = np.array([*SPREAD_DRAWS, np.inf, np.nan])
    observed, draws = randomentry.standardised_excess(6.0, with_gaps)
    assert observed == pytest.approx(randomentry.standardised_excess(6.0, SPREAD_DRAWS)[0])
    assert draws[-2] == np.inf
    assert np.isnan(draws[-1])


def test_a_null_with_too_few_finite_draws_is_refused() -> None:
    with pytest.raises(randomentry.RandomEntryError, match="only 1 of 3 null draws are finite"):
        randomentry.standardised_excess(1.0, np.array([1.0, np.nan, np.inf]))


def test_a_null_with_no_spread_is_refused_rather_than_divided_by() -> None:
    with pytest.raises(randomentry.RandomEntryError, match="no spread to standardise by"):
        randomentry.standardised_excess(1.0, np.array([2.0, 2.0, 2.0, 5.0]))


def test_a_family_of_one_is_the_one_sided_p_with_the_add_one_correction() -> None:
    draws = np.arange(10.0)
    family_p = randomentry.family_wise_p(np.array([7.5]), draws[np.newaxis, :])
    assert family_p == pytest.approx([(2 + 1) / (10 + 1)])


def test_adding_a_test_never_lowers_any_other_tests_family_wise_p() -> None:
    rng = np.random.default_rng(5)
    draws = rng.normal(size=(3, 50))
    observed = np.array([1.5, 0.5, 2.5])
    alone = randomentry.family_wise_p(observed, draws)
    added = rng.normal(1.0, size=50)
    widened = randomentry.family_wise_p(np.append(observed, 0.0), np.vstack([draws, added]))
    assert np.all(widened[:3] >= alone)
    assert np.any(widened[:3] > alone)


def test_an_observation_above_every_draw_of_every_test_reaches_the_floor() -> None:
    draws = np.arange(20.0).reshape(2, 10)
    assert randomentry.family_wise_p(np.array([100.0, 0.0]), draws)[0] == pytest.approx(1 / 11)


def test_an_infinite_draw_counts_against_every_observation() -> None:
    """A draw with no losing trade beats anything, which keeps the family-wise p conservative."""
    draws = np.array([[0.0, 0.0, np.inf], [0.0, 0.0, 0.0]])
    assert randomentry.family_wise_p(np.array([50.0, 50.0]), draws) == pytest.approx([2 / 4, 2 / 4])


def test_a_draw_undefined_for_one_test_is_not_its_best_and_one_undefined_for_all_is_dropped() -> None:
    draws = np.array([[np.nan, 1.0, 1.0, np.nan], [5.0, 0.0, 0.0, np.nan]])
    family_p = randomentry.family_wise_p(np.array([2.0, 2.0]), draws)
    assert family_p == pytest.approx([(1 + 1) / (3 + 1), (1 + 1) / (3 + 1)])


def test_draws_that_do_not_match_the_observations_are_refused() -> None:
    with pytest.raises(randomentry.RandomEntryError, match="2 observations need one row of draws each"):
        randomentry.family_wise_p(np.array([1.0, 2.0]), np.zeros((3, 10)))


def test_a_family_with_fewer_than_two_defined_draws_is_refused() -> None:
    with pytest.raises(randomentry.RandomEntryError, match="only 1 draws are defined"):
        randomentry.family_wise_p(np.array([1.0]), np.array([[1.0, np.nan]]))


def test_on_noise_the_family_wise_p_clears_about_as_often_as_its_level_and_the_raw_p_does_not() -> None:
    """The multiple-comparisons machine it exists to stop, measured on families with no signal.

    Twenty tests per family, each observation drawn from its own null: the best raw p clears
    0.05 in most families, the family-wise p in about one in twenty.
    """
    rng = np.random.default_rng(11)
    families, tests, iterations = 400, 20, 199
    cleared_raw = cleared_family = 0
    for _ in range(families):
        draws = rng.normal(size=(tests, iterations))
        observed = rng.normal(size=tests)
        raw_p = ((draws >= observed[:, np.newaxis]).sum(axis=1) + 1) / (iterations + 1)
        cleared_raw += int(raw_p.min() < randomentry.DEFAULT_ALPHA)
        cleared_family += int(randomentry.family_wise_p(observed, draws).min() < randomentry.DEFAULT_ALPHA)
    assert cleared_raw / families > 0.5
    assert 0.01 < cleared_family / families < 0.1
