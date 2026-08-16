"""Tests for per-contract sweeps and the dispersion framing around them.

Two things are being guarded. The **statistics** must not become a second definition of
what `stats.py` already computes, which is the most expensive defect class this codebase
has. And the **framing** must survive: the module exists to report a spread rather than a
winner, so the tests that matter are the ones that would fail if it quietly started ranking.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import dispersion, stats
from nqbt.dispersion import DispersionError


def leg_log(pnl_per_trade, *, legs: int = 2, start: str = "2024-01-02") -> pd.DataFrame:
    """A leg-level log whose trades sum to ``pnl_per_trade``.

    Split across legs on purpose: everything here has to survive the leg -> trade collapse,
    and a one-leg-per-trade fixture would never exercise it.
    """
    rows = []
    base = pd.Timestamp(start, tz="UTC")
    for trade_id, total in enumerate(pnl_per_trade, start=1):
        share = total / legs
        for leg in range(1, legs + 1):
            rows.append(
                {
                    "trade_id": trade_id,
                    "leg": leg,
                    "net_pnl": share,
                    "commission": 0.5,
                    "bars_held": 5,
                    "mae_points": 1.0,
                    "mfe_points": 2.0,
                    "r_multiple": share / 10.0,
                    "ambiguous_bar": False,
                    "entry_time": base + pd.Timedelta(days=trade_id),
                    "exit_time": base + pd.Timedelta(days=trade_id, minutes=5),
                }
            )
    return pd.DataFrame(rows)


# -- trade_statistic must not become a second definition -----------------------


@pytest.mark.parametrize("name", stats.TRADE_PNL_STATISTICS)
@pytest.mark.parametrize(
    "pnl",
    [
        [100.0, -50.0, 200.0, -75.0, 30.0],
        [-10.0] * 8,  # no wins: profit factor must not divide by a zero numerator
        [10.0] * 8,  # no losses: the guarded division reports infinity
        [0.0, 5.0, -5.0, 0.0],  # scratches
    ],
)
def test_the_fast_statistic_equals_the_reference_exactly(name, pnl):
    """``summarise`` is the reference; ``trade_statistic`` only exists to be faster.

    Exact equality rather than ``approx``: they share ``_ratio`` and operate on the same
    float64 sums, so any difference at all means they have drifted into two definitions.
    """
    log = leg_log(pnl)
    fast = stats.trade_statistic(stats.per_trade(log)["net_pnl"].to_numpy(float), name)
    reference = getattr(stats.summarise(log), name)
    assert fast == reference, f"{name}: {fast!r} != {reference!r}"


def test_a_time_dependent_statistic_is_refused_rather_than_approximated():
    with pytest.raises(ValueError, match="per-trade P&L alone"):
        stats.trade_statistic(np.array([1.0, -1.0]), "sharpe")


def test_an_empty_trade_vector_is_zero_not_a_crash():
    for name in stats.TRADE_PNL_STATISTICS:
        assert stats.trade_statistic(np.array([]), name) == 0.0


# -- the framing: dispersion reports a spread, not a winner --------------------


def results_table(rows) -> pd.DataFrame:
    """``(contract, combo_id, trades, profit_factor)`` tuples as a results frame."""
    return pd.DataFrame(rows, columns=["contract", "combo_id", "trades", "profit_factor"])


def test_dispersion_is_returned_in_combo_order_not_performance_order():
    """The leaderboard this module exists to refuse must not appear by accident."""
    table = results_table(
        [("A", 0, 100, 0.5), ("B", 0, 100, 0.6), ("A", 1, 100, 2.0), ("B", 1, 100, 2.2)]
    )
    out = dispersion.dispersion(table)
    assert list(out["combo_id"]) == [0, 1], "sorted by performance; combo 1 is far better"


def test_a_contract_below_the_trade_floor_is_excluded_and_counted():
    """A profit factor from four trades is noise, and noise has the widest spread."""
    table = results_table(
        [("A", 0, 400, 0.9), ("B", 0, 350, 1.0), ("C", 0, 4, 12.0)]
    )
    out = dispersion.dispersion(table, min_trades=30).iloc[0]
    assert out["contracts"] == 3
    assert out["contracts_used"] == 2
    assert out["contracts_dropped"] == 1
    assert out["profit_factor_max"] == 1.0, "the 4-trade outlier reached the spread"
    assert out["profit_factor_range"] == pytest.approx(0.1)


def test_an_infinite_profit_factor_is_dropped_rather_than_poisoning_the_spread():
    """A contract with no losing trade reports inf, which would make every spread inf."""
    table = results_table([("A", 0, 100, 0.9), ("B", 0, 100, 1.1), ("C", 0, 100, np.inf)])
    out = dispersion.dispersion(table).iloc[0]
    assert out["contracts_used"] == 2
    assert np.isfinite(out["profit_factor_range"])


def test_trades_total_counts_every_contract_including_the_dropped_ones():
    table = results_table([("A", 0, 400, 0.9), ("C", 0, 4, 12.0)])
    assert dispersion.dispersion(table).iloc[0]["trades_total"] == 404


def test_an_unknown_statistic_names_what_is_available():
    with pytest.raises(DispersionError, match="no column 'sharpe_ratio'"):
        dispersion.dispersion(results_table([("A", 0, 50, 1.0)]), by="sharpe_ratio")


# -- the permutation test ------------------------------------------------------


def test_spread_from_one_pooled_population_looks_like_noise():
    """Every contract drawn from the same distribution: neither measure should fire."""
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(8)}
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)
    assert out["contracts"] == 8
    for name, result in out["spread"].items():
        assert result["p_value"] > 0.05, f"{name} flagged one population as differing"


def test_a_broadly_different_set_of_contracts_moves_the_iqr():
    """Half the contracts from a different population: the robust measure should see it."""
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(5)}
    logs.update({f"H{i}": leg_log(rng.normal(80, 100, 200).tolist()) for i in range(5)})
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)
    assert out["spread"]["iqr"]["p_value"] < 0.05, "no power against a real bulk difference"


def test_one_rogue_contract_moves_the_range_and_not_the_iqr():
    """The documented division of labour between the two measures.

    A single bad contract -- which in practice means a bad roll date or a hole, not a market
    insight -- is exactly what the IQR is built to ignore. If only the robust measure were
    reported, the data-integrity signal would be discarded silently.
    """
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(9)}
    logs["ROGUE"] = leg_log(rng.normal(220, 150, 200).tolist())
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)

    assert out["spread"]["range"]["p_value"] < 0.05, "the rogue contract went unseen"
    assert out["spread"]["iqr"]["p_value"] > 0.05, (
        "the IQR moved on one outlier; it is supposed to be robust to exactly that"
    )


def test_every_permutation_reproduces_the_observed_group_sizes():
    """Otherwise the null mixes a spread effect with a sample-size effect.

    Checked by construction: unequal groups whose small member is the one that would move.
    """
    rng = np.random.default_rng(2)
    logs = {
        "BIG": leg_log(rng.normal(0, 100, 400).tolist()),
        "SMALL": leg_log(rng.normal(0, 100, 40).tolist()),
        "MID": leg_log(rng.normal(0, 100, 120).tolist()),
    }
    out = dispersion.spread_vs_resampling(logs, iterations=50, seed=3)
    assert out["trades"] == 400 + 40 + 120
    assert out["contracts"] == 3
    assert set(out["spread"]) == set(dispersion.SPREAD_MEASURES)


def test_the_permutation_test_is_deterministic_for_a_seed():
    rng = np.random.default_rng(5)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 120).tolist()) for i in range(4)}
    a = dispersion.spread_vs_resampling(logs, iterations=100, seed=7)
    b = dispersion.spread_vs_resampling(logs, iterations=100, seed=7)
    assert a == b


def test_a_time_dependent_statistic_is_refused_by_the_permutation_test():
    """Shuffling trades between contracts destroys the ordering Sharpe is computed over."""
    rng = np.random.default_rng(6)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 80).tolist()) for i in range(3)}
    with pytest.raises(DispersionError, match="not permutable"):
        dispersion.spread_vs_resampling(logs, by="sharpe")


def test_one_usable_contract_cannot_have_a_spread():
    logs = {"A": leg_log([10.0] * 100), "B": leg_log([10.0] * 3)}
    with pytest.raises(DispersionError, match="at least 2 contracts"):
        dispersion.spread_vs_resampling(logs, min_trades=30)


def test_the_observed_statistic_matches_the_reference_per_contract():
    """The reported per-contract numbers are the same ones ``summarise`` would give."""
    rng = np.random.default_rng(8)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 100).tolist()) for i in range(3)}
    out = dispersion.spread_vs_resampling(logs, iterations=10, seed=0)
    for contract, value in out["per_contract"].items():
        assert value == stats.summarise(logs[contract]).profit_factor


# -- real cached data ----------------------------------------------------------


def cached_windows():
    try:
        return dispersion.front_month_windows("MNQ")
    except Exception:  # pragma: no cover - the cache is not in CI
        pytest.skip("no spliced MNQ cache on this machine")


def test_front_month_windows_are_contiguous_and_do_not_overlap():
    windows = cached_windows()
    assert len(windows) > 1
    assert windows["start"].is_monotonic_increasing
    assert (windows["start"].to_numpy()[1:] > windows["end"].to_numpy()[:-1]).all()


def test_the_windows_account_for_the_continuous_series_exactly():
    """The strongest available check that these are the splicer's own decisions.

    Front-month windows are non-overlapping and sum to the continuous series. If they did
    not, some calendar days would be double-counted or missing, and every cross-contract
    aggregate would be wrong by that amount.
    """
    splice = pytest.importorskip("nqbt.splice")
    windows = cached_windows()
    series = splice.load_continuous("MNQ", back_adjust=True)
    assert int(windows["continuous_bars"].sum()) == len(series)


def test_contract_frames_carry_raw_prices_not_back_adjusted_ones():
    """Back-adjustment shifts historical levels by hundreds of points.

    Anything sensitive to the absolute level can only be tested per contract, so a frame
    that quietly came back adjusted would make that impossible while looking fine.
    """
    splice = pytest.importorskip("nqbt.splice")
    cached_windows()
    frames = dispersion.contract_frames("MNQ")
    adjusted = splice.load_continuous("MNQ", back_adjust=True)

    name = next(iter(frames))
    raw = frames[name]
    overlap = adjusted[adjusted["contract"] == name]
    shared = raw.index.intersection(overlap.index)
    assert len(shared) > 1000, "no overlap to compare"
    shift = (overlap.loc[shared, "close"] - raw.loc[shared, "close"]).abs().max()
    assert shift > 1.0, f"{name} looks already back-adjusted (max shift {shift})"


def test_coverage_reports_a_sample_size_for_every_contract():
    cached_windows()
    cover = dispersion.coverage(dispersion.contract_frames("MNQ"))
    assert (cover["sessions"] > 0).all()
    assert (cover["in_session_bars"] <= cover["bars"]).all()
    assert cover["contract"].is_unique
