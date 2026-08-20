"""Resampling tests, and the two ways they can silently become meaningless.

The failure this file exists to prevent is a permutation test on a statistic reordering
cannot move: it returns ``p_value`` 1.0 for every input and reads exactly like a passed
check. The second is ``path_statistic`` drifting into a second definition of the drawdown
``stats.summarise`` already computes.
"""

import numpy as np
import pandas as pd
import pytest
from test_dispersion import leg_log

from nqbt import montecarlo, stats
from nqbt.montecarlo import MonteCarloError

# -- path_statistic must not become a second definition ------------------------


@pytest.mark.parametrize(
    "pnl",
    [
        [100.0, -50.0, 200.0, -75.0, 30.0],
        [-10.0] * 8,
        [10.0] * 8,
        [0.0, 5.0, -5.0, 0.0],
        [-5.0, -5.0, -5.0, 10.0, -5.0, -5.0],
    ],
)
def test_path_statistic_equals_the_reference_summary_exactly(pnl) -> None:
    log = leg_log(pnl)
    reference = stats.summarise(log)
    vector = montecarlo.trade_pnl(log)

    assert stats.path_statistic(vector, "max_drawdown") == reference.max_drawdown
    assert stats.path_statistic(vector, "max_consecutive_losses") == reference.max_consecutive_losses


def test_path_statistic_rejects_an_order_invariant_name() -> None:
    with pytest.raises(ValueError, match="does not depend on trade order"):
        stats.path_statistic(np.array([1.0, -1.0]), "profit_factor")


def test_path_statistic_of_no_trades_is_zero() -> None:
    assert stats.path_statistic(np.empty(0), "max_drawdown") == 0.0


# -- the degenerate-permutation guard ------------------------------------------


@pytest.mark.parametrize("name", stats.TRADE_PNL_STATISTICS)
def test_permuting_a_value_statistic_is_refused_rather_than_silently_passing(name) -> None:
    pnl = np.array([100.0, -50.0, 200.0, -75.0, 30.0])
    with pytest.raises(MonteCarloError, match="does not depend on trade order"):
        montecarlo.permutation_test(pnl, name)


@pytest.mark.parametrize("name", stats.TRADE_PNL_STATISTICS)
def test_and_the_reason_it_is_refused_holds__reordering_cannot_move_those(name) -> None:
    """The guard above is only correct because this is true. Pin it, do not assume it."""
    pnl = np.array([100.0, -50.0, 200.0, -75.0, 30.0, -20.0, 45.0])
    rng = np.random.default_rng(7)
    before = stats.trade_statistic(pnl, name)
    for _ in range(20):
        assert stats.trade_statistic(rng.permutation(pnl), name) == pytest.approx(before)


@pytest.mark.parametrize("name", stats.PATH_STATISTICS)
def test_reordering_does_move_a_path_statistic(name) -> None:
    """The complement of the test above: if this failed, the whole module is pointless."""
    pnl = np.array([-5.0, -5.0, -5.0, -5.0, 40.0, -2.0, 3.0])
    rng = np.random.default_rng(3)
    observed = stats.path_statistic(pnl, name)
    assert any(stats.path_statistic(rng.permutation(pnl), name) != observed for _ in range(50))


# -- permutation_test ----------------------------------------------------------


def test_the_worst_possible_ordering_is_flagged_as_extreme() -> None:
    """All losses first, then all wins, is the maximum drawdown any ordering can produce.

    90 rather than 100 because ``stats._max_drawdown`` measures from the running peak of the
    equity curve, which starts at the *first* trade's P&L rather than at zero. That is the
    definition ``summarise`` already reports and this must not fork it.
    """
    pnl = np.array([-10.0] * 10 + [10.0] * 10)
    result = montecarlo.permutation_test(pnl, "max_drawdown", iterations=200, seed=0)

    assert result.observed == pytest.approx(90.0)
    assert result.observed == stats.summarise(leg_log(list(pnl), legs=1)).max_drawdown
    assert result.observed >= result.null_p95
    assert result.p_value <= 0.05


def test_a_typical_ordering_is_not_flagged() -> None:
    rng = np.random.default_rng(11)
    pnl = rng.normal(5.0, 50.0, size=200)
    result = montecarlo.permutation_test(pnl, "max_drawdown", iterations=200, seed=1)
    assert 0.05 < result.p_value < 0.95


def test_permutation_is_reproducible_from_its_seed() -> None:
    pnl = np.array([-10.0, 5.0, -3.0, 12.0, -8.0, 4.0, -1.0, 9.0])
    first = montecarlo.permutation_test(pnl, iterations=50, seed=4)
    second = montecarlo.permutation_test(pnl, iterations=50, seed=4)
    third = montecarlo.permutation_test(pnl, iterations=50, seed=5)

    assert first == second
    assert first.p_value != third.p_value or first.null_median != third.null_median


def test_permutation_reports_when_there_are_too_few_trades_to_believe_it() -> None:
    pnl = np.array([-10.0, 5.0, -3.0, 12.0])
    assert montecarlo.permutation_test(pnl, iterations=20).underpowered is True

    rng = np.random.default_rng(2)
    many = rng.normal(1.0, 10.0, size=montecarlo.MIN_TRADES)
    assert montecarlo.permutation_test(many, iterations=20).underpowered is False


@pytest.mark.parametrize("size", [0, 1])
def test_permuting_fewer_than_two_trades_raises(size) -> None:
    with pytest.raises(MonteCarloError, match="at least 2 trades"):
        montecarlo.permutation_test(np.ones(size))


# -- bootstrap -----------------------------------------------------------------


def test_bootstrap_brackets_the_observed_value() -> None:
    rng = np.random.default_rng(5)
    pnl = rng.normal(2.0, 40.0, size=300)
    frame = montecarlo.bootstrap(pnl, ("net_pnl", "expectancy"), iterations=300, seed=0)

    for row in frame.itertuples():
        assert row.p05 <= row.observed <= row.p95, row.statistic


def test_bootstrap_of_an_all_losing_record_never_resamples_a_profit() -> None:
    pnl = np.full(60, -25.0)
    frame = montecarlo.bootstrap(pnl, ("net_pnl",), iterations=100, seed=0)
    assert frame.loc[0, "share_below_zero"] == 1.0
    assert frame.loc[0, "p95"] < 0


def test_bootstrap_carries_its_provenance_on_the_frame() -> None:
    pnl = np.array([-10.0, 5.0, -3.0, 12.0, -8.0, 4.0])
    frame = montecarlo.bootstrap(pnl, ("net_pnl",), iterations=25, seed=0)

    assert frame.attrs["iterations"] == 25
    assert frame.attrs["trades"] == 6
    assert frame.attrs["underpowered"] is True


def test_bootstrap_counts_the_infinite_draws_it_dropped() -> None:
    """A resample with no losing trade reports an infinite profit factor by design."""
    pnl = np.array([10.0, 20.0, 30.0, -1.0])
    frame = montecarlo.bootstrap(pnl, ("profit_factor",), iterations=200, seed=0)
    assert 0 < frame.loc[0, "draws_finite"] < 200


def test_bootstrap_rejects_an_unknown_statistic() -> None:
    with pytest.raises(MonteCarloError, match="unknown statistic"):
        montecarlo.bootstrap(np.ones(10), ("sharpe",))


def test_bootstrap_rejects_an_empty_statistic_list() -> None:
    with pytest.raises(MonteCarloError, match="no statistics requested"):
        montecarlo.bootstrap(np.ones(10), ())


@pytest.mark.parametrize("size", [0, 1])
def test_bootstrapping_fewer_than_two_trades_raises(size) -> None:
    with pytest.raises(MonteCarloError, match="at least 2 trades"):
        montecarlo.bootstrap(np.ones(size))


# -- trade_pnl -----------------------------------------------------------------


def test_trade_pnl_collapses_legs_to_one_value_per_trade() -> None:
    log = leg_log([100.0, -50.0, 25.0], legs=3)
    vector = montecarlo.trade_pnl(log)

    assert vector.size == 3
    assert vector == pytest.approx([100.0, -50.0, 25.0])


def test_trade_pnl_is_in_entry_order_not_groupby_order() -> None:
    log = leg_log([10.0, 20.0, 30.0], legs=1)
    shuffled = log.iloc[::-1].reset_index(drop=True)
    assert montecarlo.trade_pnl(shuffled) == pytest.approx([10.0, 20.0, 30.0])


def test_trade_pnl_of_an_empty_log_is_empty_rather_than_raising() -> None:
    assert montecarlo.trade_pnl(pd.DataFrame()).size == 0
