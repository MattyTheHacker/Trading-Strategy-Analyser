"""Tests for the sweep harness, statistics and DuckDB results layer."""

import numpy as np
import pandas as pd
import pytest

from nqbt import results, sessions, stats, sweep, trades
from nqbt.instruments import NQ
from nqbt.sim import runner
from nqbt.sim.types import DeadCatParams


def trade_log(rows) -> pd.DataFrame:
    """Build a leg-level log. Each row is (trade_id, leg, net_pnl, bars, ambiguous)."""
    frame = pd.DataFrame(rows, columns=["trade_id", "leg", "net_pnl", "bars_held", "ambiguous_bar"])
    frame["commission"] = 0.5
    frame["mae_points"] = 1.0
    frame["mfe_points"] = 2.0
    frame["r_multiple"] = frame["net_pnl"] / 10.0
    base = pd.Timestamp("2024-01-02 10:00", tz="UTC")
    frame["entry_time"] = base + pd.to_timedelta(frame["trade_id"], unit="D")
    frame["exit_time"] = frame["entry_time"] + pd.Timedelta(minutes=5)
    return frame


# -- statistics ---------------------------------------------------------------


def test_summary_counts_trades_not_legs():
    # Two trades of four legs each. NT8 would call this eight trades; a person calls it two.
    log = trade_log([(1, l, 10.0, 3, False) for l in range(1, 5)]
                    + [(2, l, -5.0, 2, False) for l in range(1, 5)])
    s = stats.summarise(log)
    assert s.trades == 2
    assert s.legs == 8
    assert s.wins == 1 and s.losses == 1
    assert s.win_rate == pytest.approx(0.5)
    assert s.net_pnl == pytest.approx(40.0 - 20.0)


def test_profit_factor_and_expectancy():
    log = trade_log([(1, 1, 30.0, 1, False), (2, 1, -10.0, 1, False), (3, 1, -5.0, 1, False)])
    s = stats.summarise(log)
    assert s.gross_profit == pytest.approx(30.0)
    assert s.gross_loss == pytest.approx(-15.0)
    assert s.profit_factor == pytest.approx(2.0)
    assert s.expectancy == pytest.approx(15.0 / 3)


def test_profit_factor_with_no_losses_is_infinite_not_a_crash():
    log = trade_log([(1, 1, 5.0, 1, False), (2, 1, 7.0, 1, False)])
    assert stats.summarise(log).profit_factor == float("inf")


def test_max_drawdown_measures_peak_to_trough():
    # equity: 100, 60, 130 -> worst decline from the running peak is 40.
    log = trade_log([(1, 1, 100.0, 1, False), (2, 1, -40.0, 1, False), (3, 1, 70.0, 1, False)])
    assert stats.summarise(log).max_drawdown == pytest.approx(40.0)


def test_max_consecutive_losses():
    pnl = [5.0, -1.0, -1.0, -1.0, 5.0, -1.0]
    log = trade_log([(i + 1, 1, p, 1, False) for i, p in enumerate(pnl)])
    assert stats.summarise(log).max_consecutive_losses == 3


def test_scratches_are_neither_wins_nor_losses():
    log = trade_log([(1, 1, 0.0, 1, False), (2, 1, 5.0, 1, False)])
    s = stats.summarise(log)
    assert (s.wins, s.losses, s.scratches) == (1, 0, 1)
    assert s.win_rate == pytest.approx(0.5)


def test_ambiguous_share_reports_assumption_exposure():
    log = trade_log([(1, 1, 5.0, 1, True), (2, 1, 5.0, 1, False),
                     (3, 1, 5.0, 1, False), (4, 1, 5.0, 1, False)])
    assert stats.summarise(log).ambiguous_share == pytest.approx(0.25)


def test_leg_summary_matches_nt8s_way_of_counting():
    log = trade_log([(1, l, 10.0, 3, False) for l in range(1, 5)])
    assert stats.leg_summary(log)["legs"] == 4
    assert stats.summarise(log).trades == 1


# -- the empty log, which used to raise ---------------------------------------


def test_summarising_an_empty_log_returns_zeros_rather_than_raising():
    """The guard splatted 26 arguments into a 28-field dataclass and raised on every call."""
    s = stats.summarise(trade_log([]))
    assert s.trades == 0 and s.legs == 0
    assert s.net_pnl == 0.0 and s.profit_factor == 0.0


INTEGER_SUMMARY_FIELDS = {
    "trades", "legs", "wins", "losses", "scratches", "max_consecutive_losses",
}
"""Stated here independently of ``Summary``'s annotations, so this is a second opinion.

``max_consecutive_losses`` is the one that matters: it sits at field 17, so the splat this
replaced would have handed it a float even had someone fixed the argument count.
"""


def test_the_empty_summary_gives_each_field_its_declared_type():
    s = stats.Summary.empty()
    for name in stats.Summary.columns():
        value = getattr(s, name)
        if name in INTEGER_SUMMARY_FIELDS:
            assert isinstance(value, int) and not isinstance(value, bool), name
        else:
            assert isinstance(value, float), name


def test_a_barren_combination_summarises_exactly_like_an_empty_log():
    """One empty-log policy, not two.

    ``run_combination`` used to build its own all-int zero dict, which disagreed with
    ``summarise``'s empty case on the dtype of 22 of the 28 columns.
    """
    bars = synthetic_bars(n=800)
    # No bar can clear the warm-up, so the signal never fires and the log comes back empty.
    params = DeadCatParams(bars_required_to_trade=10_000)
    data = sweep.prepare_for(bars, sweep.Grid.of(params))
    row, log = sweep.run_combination(data, params, NQ)
    assert log.empty, "fixture produced trades; the test proves nothing"
    for name, value in stats.Summary.empty().as_dict().items():
        assert row[name] == value and type(row[name]) is type(value), name


# -- grid ---------------------------------------------------------------------


def test_grid_size_is_the_product_of_its_axes():
    g = sweep.Grid.of(ema_period=[9, 21], use_vwap=[True, False], fast_sma_period=[40, 60, 80])
    assert len(g) == 12
    assert len(list(g.combinations())) == 12


def test_grid_leaves_unswept_parameters_at_their_base_value():
    base = DeadCatParams(order_quantity=8, commission_per_contract=1.5)
    combos = list(sweep.Grid.of(base, ema_period=[9, 21]).combinations())
    assert {c.order_quantity for c in combos} == {8}
    assert {c.commission_per_contract for c in combos} == {1.5}
    assert sorted(c.ema_period for c in combos) == [9, 21]


def test_empty_grid_yields_the_base_alone():
    assert len(list(sweep.Grid.of().combinations())) == 1


def test_grid_rejects_unknown_parameters():
    with pytest.raises(sweep.SweepError, match="unknown sweep parameter"):
        sweep.Grid.of(emma_period=[9])


def test_grid_rejects_an_axis_whose_filter_is_switched_off():
    # The NinjaScript's current defaults leave the slow SMA off, so sweeping its period
    # would produce identical rows and multiply runtime for nothing.
    base = DeadCatParams(use_slow_sma=False)
    with pytest.raises(sweep.SweepError, match="cannot affect any result"):
        sweep.Grid.of(base, slow_sma_period=[120, 175])


def test_gated_axis_is_allowed_when_its_toggle_is_also_swept():
    base = DeadCatParams(use_slow_sma=False)
    g = sweep.Grid.of(base, slow_sma_period=[120, 175], use_slow_sma=[True, False])
    assert g.dead_axes() == {}
    assert len(g) == 4


def test_required_context_covers_every_combination():
    base = DeadCatParams(use_slow_sma=True)
    g = sweep.Grid.of(base, ema_period=[9, 21], fast_sma_period=[40, 60],
                      slow_sma_period=[150, 200])
    spec = g.required_context()
    assert spec.ema_periods == (9, 21)
    assert spec.sma_periods == (40, 60, 150, 200)


def test_required_context_includes_unswept_defaults():
    g = sweep.Grid.of(DeadCatParams(ema_period=11, fast_sma_period=80), use_vwap=[True, False])
    spec = g.required_context()
    assert 11 in spec.ema_periods and 80 in spec.sma_periods


# -- parallel execution -------------------------------------------------------


def test_chunk_bounds_cover_every_combination_exactly_once():
    # The property that matters: no combination run twice, none dropped, order preserved.
    for total in (1, 7, 100, 193):
        for workers in (1, 3, 8):
            bounds = sweep.chunk_bounds(total, workers)
            covered = [i for start, stop in bounds for i in range(start, stop)]
            assert covered == list(range(total)), f"{total} over {workers} workers"


def test_chunk_bounds_of_an_empty_grid_is_no_work():
    assert sweep.chunk_bounds(0, 4) == []


def test_chunk_bounds_respects_an_explicit_size():
    assert sweep.chunk_bounds(10, 4, chunk_size=3) == [(0, 3), (3, 6), (6, 9), (9, 10)]


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Random-walk minute bars with wicks wide enough to throw inverted hammers.

    Not a market model -- just a series the whole prepare/simulate path will actually
    trade on, so the parallel comparison has something to compare.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.5, n))
    frame = pd.DataFrame(
        {
            "open": open_, "high": high, "low": low, "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day
    return frame


@pytest.fixture(scope="module")
def prepared():
    bars = synthetic_bars()
    grid = sweep.Grid.of(
        DeadCatParams(bars_required_to_trade=200),
        ema_period=[9, 21], fast_sma_period=[40, 60],
    )
    return bars, grid, sweep.prepare_for(bars, grid)


def test_slim_drops_the_bar_columns_but_shares_the_arrays(prepared):
    _, _, data = prepared
    lean = data.slim()
    assert list(lean.bars.columns) == []
    assert lean.index.equals(data.index)
    # Shared, not copied -- copying is exactly the cost slim() exists to avoid.
    assert lean.close is data.close
    assert lean.mas["ema"].below is data.mas["ema"].below


def test_the_simulator_meets_the_trade_schema(prepared):
    """``run_deadcat`` is a producer, so its output is checked at the boundary."""
    _, grid, data = prepared
    params = next(grid.combinations())
    log = runner.run_deadcat(data, params, NQ)
    assert len(log), "fixture produced no trades; the test proves nothing"
    trades.validate(log)
    assert (log["source"] == "sim").all()
    assert (log["instrument"] == "NQ").all()
    # Short-only until M15 generalises the loop, but recorded rather than assumed.
    assert (log["direction"] == trades.SHORT).all()


def test_a_slim_dataset_simulates_identically(prepared):
    _, grid, data = prepared
    params = next(grid.combinations())
    pd.testing.assert_frame_equal(
        runner.run_deadcat(data, params), runner.run_deadcat(data.slim(), params)
    )


def test_parallel_sweep_matches_serial_exactly(prepared):
    bars, grid, data = prepared
    serial, _ = sweep.sweep(bars, grid, data=data, n_jobs=1)
    parallel, _ = sweep.sweep(bars, grid, data=data, n_jobs=2)
    assert serial["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    pd.testing.assert_frame_equal(serial, parallel)


def test_parallel_sweep_keys_trade_logs_by_combo_id(prepared):
    bars, grid, data = prepared
    frame, logs = sweep.sweep(bars, grid, data=data, n_jobs=2, keep_trades=True)
    assert sorted(logs) == list(range(len(grid)))
    assert list(frame["combo_id"]) == list(range(len(grid)))


# -- results store ------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return tmp_path / "sweeps.duckdb"


def fake_results(n=3) -> pd.DataFrame:
    return pd.DataFrame({
        "combo_id": range(n),
        "ema_period": [9, 21, 30][:n],
        "trades": [100, 200, 5][:n],
        "profit_factor": [1.2, 1.5, 9.9][:n],
        "net_pnl": [500.0, 900.0, 40.0][:n],
    })


def fake_bars() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=10, freq="min", tz="UTC")
    return pd.DataFrame({"close": np.arange(10.0)}, index=idx)


def test_save_and_reload_a_sweep(db):
    sid = results.save_sweep(fake_results(), root="MNQ", instrument="MNQ",
                             bars=fake_bars(), axes={"ema_period": [9, 21, 30]}, db_path=db)
    assert sid == 1
    listed = results.list_sweeps(db)
    assert len(listed) == 1
    assert listed.loc[0, "combos"] == 3
    assert results.query("SELECT COUNT(*) c FROM combos", db).loc[0, "c"] == 3


def test_sweep_ids_increment_and_rows_stay_tagged(db):
    for _ in range(3):
        results.save_sweep(fake_results(), root="MNQ", instrument="MNQ", bars=fake_bars(),
                           axes={}, db_path=db)
    assert list(results.list_sweeps(db)["sweep_id"]) == [3, 2, 1]
    counts = results.query("SELECT sweep_id, COUNT(*) n FROM combos GROUP BY 1 ORDER BY 1", db)
    assert list(counts["n"]) == [3, 3, 3]


def test_best_applies_a_trade_floor(db):
    results.save_sweep(fake_results(), root="MNQ", instrument="MNQ", bars=fake_bars(),
                       axes={}, db_path=db)
    # combo 2 has the best profit factor on five trades, which is noise, not an edge.
    top = results.best(by="profit_factor", top=5, min_trades=30, db_path=db)
    assert 5 not in list(top["trades"])
    assert top.iloc[0]["profit_factor"] == pytest.approx(1.5)


def test_rank_ignores_undersampled_combinations():
    ranked = sweep.rank(fake_results(), by="profit_factor", top=5, min_trades=30)
    assert list(ranked["trades"]) == [200, 100]


def test_a_later_sweep_with_extra_statistics_does_not_shift_columns(db):
    results.save_sweep(fake_results(), root="MNQ", instrument="MNQ", bars=fake_bars(),
                       axes={}, db_path=db)
    wider = fake_results()
    wider["brand_new_stat"] = [1.0, 2.0, 3.0]
    results.save_sweep(wider, root="MNQ", instrument="MNQ", bars=fake_bars(),
                       axes={}, db_path=db)
    rows = results.query("SELECT sweep_id, ema_period, profit_factor FROM combos ORDER BY sweep_id", db)
    assert len(rows) == 6
    assert rows["profit_factor"].notna().all()
