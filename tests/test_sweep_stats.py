"""Tests for the sweep harness, statistics and DuckDB results layer."""

import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from nqbt import conditions, context, resample, results, sessions, stats, sweep, trades
from nqbt.instruments import NQ
from nqbt.sim import runner
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams


def trade_log(rows, exit_reasons=None) -> pd.DataFrame:
    """Build a leg-level log. Each row is (trade_id, leg, net_pnl, bars, ambiguous).

    ``exit_reasons`` defaults to every leg exiting at its target, which is a real reason
    rather than a placeholder -- ``session_close_share`` reads this column, so a log full of
    ``""`` would make that statistic vacuously 0 in every test that does not set it.
    """
    frame = pd.DataFrame(rows, columns=["trade_id", "leg", "net_pnl", "bars_held", "ambiguous_bar"])
    frame["commission"] = 0.5
    frame["mae_points"] = 1.0
    frame["mfe_points"] = 2.0
    frame["r_multiple"] = frame["net_pnl"] / 10.0
    frame["exit_reason"] = exit_reasons if exit_reasons is not None else "target"
    base = pd.Timestamp("2024-01-02 10:00", tz="UTC")
    frame["entry_time"] = base + pd.to_timedelta(frame["trade_id"], unit="D")
    frame["exit_time"] = frame["entry_time"] + pd.Timedelta(minutes=5)
    return frame


# -- statistics ---------------------------------------------------------------


def test_summary_counts_trades_not_legs() -> None:
    # Two trades of four legs each. NT8 would call this eight trades; a person calls it two.
    log = trade_log(
        [(1, l, 10.0, 3, False) for l in range(1, 5)] + [(2, l, -5.0, 2, False) for l in range(1, 5)],
    )
    s = stats.summarise(log)
    assert s.trades == 2
    assert s.legs == 8
    assert s.wins == 1
    assert s.losses == 1
    assert s.win_rate == pytest.approx(0.5)
    assert s.net_pnl == pytest.approx(40.0 - 20.0)


def test_profit_factor_and_expectancy() -> None:
    log = trade_log([(1, 1, 30.0, 1, False), (2, 1, -10.0, 1, False), (3, 1, -5.0, 1, False)])
    s = stats.summarise(log)
    assert s.gross_profit == pytest.approx(30.0)
    assert s.gross_loss == pytest.approx(-15.0)
    assert s.profit_factor == pytest.approx(2.0)
    assert s.expectancy == pytest.approx(15.0 / 3)


def test_profit_factor_with_no_losses_is_infinite_not_a_crash() -> None:
    log = trade_log([(1, 1, 5.0, 1, False), (2, 1, 7.0, 1, False)])
    assert stats.summarise(log).profit_factor == float("inf")


def test_max_drawdown_measures_peak_to_trough() -> None:
    # equity: 100, 60, 130 -> worst decline from the running peak is 40.
    log = trade_log([(1, 1, 100.0, 1, False), (2, 1, -40.0, 1, False), (3, 1, 70.0, 1, False)])
    assert stats.summarise(log).max_drawdown == pytest.approx(40.0)


def test_max_consecutive_losses() -> None:
    pnl = [5.0, -1.0, -1.0, -1.0, 5.0, -1.0]
    log = trade_log([(i + 1, 1, p, 1, False) for i, p in enumerate(pnl)])
    assert stats.summarise(log).max_consecutive_losses == 3


def test_scratches_are_neither_wins_nor_losses() -> None:
    log = trade_log([(1, 1, 0.0, 1, False), (2, 1, 5.0, 1, False)])
    s = stats.summarise(log)
    assert (s.wins, s.losses, s.scratches) == (1, 0, 1)
    assert s.win_rate == pytest.approx(0.5)


def test_ambiguous_share_reports_assumption_exposure() -> None:
    log = trade_log(
        [(1, 1, 5.0, 1, True), (2, 1, 5.0, 1, False), (3, 1, 5.0, 1, False), (4, 1, 5.0, 1, False)],
    )
    assert stats.summarise(log).ambiguous_share == pytest.approx(0.25)


def test_session_close_share_counts_exits_taken_by_the_clock() -> None:
    log = trade_log(
        [(1, 1, 5.0, 1, False), (2, 1, 5.0, 1, False), (3, 1, -5.0, 1, False), (4, 1, 5.0, 1, False)],
        exit_reasons=["target", "session_close", "stop", "session_close"],
    )
    assert stats.summarise(log).session_close_share == pytest.approx(0.5)


def test_session_close_share_is_zero_when_nothing_runs_into_the_close() -> None:
    log = trade_log([(1, 1, 5.0, 1, False), (2, 1, -5.0, 1, False)], exit_reasons=["target", "stop"])
    assert stats.summarise(log).session_close_share == 0.0


def test_session_close_share_is_measured_over_legs_like_ambiguous_share() -> None:
    """Denominator pinned, because the two defensible choices differ by 4x here.

    One trade of four legs, one of which the clock closed. Over legs that is 0.25; over
    trades it would be 1.0, since the trade did end at the close. Legs is chosen to match
    ``ambiguous_share``, so the two diagnostics in adjacent columns are comparable.
    """
    log = trade_log(
        [(1, leg, 5.0, 1, False) for leg in range(1, 5)],
        exit_reasons=["target", "target", "target", "session_close"],
    )
    s = stats.summarise(log)
    assert s.trades == 1
    assert s.legs == 4
    assert s.session_close_share == pytest.approx(0.25)


def test_session_close_share_reads_the_label_the_simulator_actually_writes() -> None:
    """Guards the guard: the tests above would pass on a typo shared with the source.

    ``stats.SESSION_CLOSE`` is derived from ``trades.EXIT_REASONS`` rather than spelled
    twice, and this asserts the derivation lands on the string the mapping produces.
    """
    # Left-to-right follows the docstring's derivation; SIM300 misfires here because
    # neither side is a literal.
    assert stats.SESSION_CLOSE == trades.EXIT_REASONS[trades.EXIT_SESSION_CLOSE]  # noqa: SIM300
    assert stats.SESSION_CLOSE == "session_close"


def test_a_log_without_an_exit_reason_raises_rather_than_reporting_zero() -> None:
    """A missing column is a wiring bug, and 0.0 would read as a finding about the market.

    The same shape as #81's Sharpe branch below, which is why this is indexed rather than
    defaulted -- ``trades.validate`` requires the column of every producer.
    """
    log = trade_log([(1, 1, 5.0, 1, False)]).drop(columns=["exit_reason"])
    with pytest.raises(KeyError, match="exit_reason"):
        stats.summarise(log)


# -- Sharpe and Sortino are refused rather than approximated (#81) -------------


def test_a_log_without_exit_times_is_refused_rather_than_summarised_per_trade() -> None:
    """A per-trade ratio annualised as though it were daily is a plausible wrong number.

    Refusing is the loud half of the choice #11 made for the empty log: the branch this
    replaces returned one, and two Sharpes with different denominators would have sat in
    the same results column with nothing distinguishing them.
    """
    log = trade_log([(1, 1, 5.0, 1, False), (2, 1, -5.0, 1, False)]).drop(columns=["exit_time"])
    with pytest.raises(stats.MissingTimesError, match="exit_time"):
        stats.summarise(log)


def test_a_log_whose_exit_times_are_null_is_refused_too() -> None:
    """The same defect by another route: those trades would leave the daily totals silently.

    Every other statistic still counts them, so the Sharpe denominator alone would shrink.
    """
    log = trade_log([(1, 1, 5.0, 1, False), (2, 1, -5.0, 1, False)])
    log.loc[0, "exit_time"] = pd.NaT
    with pytest.raises(stats.MissingTimesError, match="null on 1 of 2 legs"):
        stats.summarise(log)


def test_the_times_are_checked_before_the_log_is_found_to_be_empty() -> None:
    """Schema first, then emptiness -- the order ``trades.validate`` already uses.

    A producer that attaches no times is a wiring bug whether or not it happened to trade,
    and an empty frame is the case where the mistake is cheapest to make.
    """
    with pytest.raises(stats.MissingTimesError, match="exit_time"):
        stats.summarise(pd.DataFrame())


def test_sharpe_is_denominated_in_days_not_trades() -> None:
    """The property the refusal exists to protect: same trades, different closing days.

    Six identical P&Ls, once two to a day and once one to a day. Every other statistic is
    the same across the pair, and a per-trade denominator could not tell them apart either.
    """
    pnl = [10.0, -5.0, 25.0, 10.0, -5.0, 25.0]
    log = trade_log([(i + 1, 1, p, 1, False) for i, p in enumerate(pnl)])
    day = pd.Timestamp("2024-01-02 20:00", tz="UTC")

    paired = log.assign(exit_time=[day + pd.Timedelta(days=i // 2) for i in range(len(pnl))])
    spread = log.assign(exit_time=[day + pd.Timedelta(days=i) for i in range(len(pnl))])

    assert stats.summarise(paired).net_pnl == stats.summarise(spread).net_pnl
    assert stats.summarise(paired).sharpe != stats.summarise(spread).sharpe


def test_leg_summary_matches_nt8s_way_of_counting() -> None:
    log = trade_log([(1, l, 10.0, 3, False) for l in range(1, 5)])
    assert stats.leg_summary(log)["legs"] == 4
    assert stats.summarise(log).trades == 1


# -- the empty log, which used to raise ---------------------------------------


def test_summarising_an_empty_log_returns_zeros_rather_than_raising() -> None:
    """The guard splatted 26 arguments into a 28-field dataclass and raised on every call."""
    s = stats.summarise(trade_log([]))
    assert s.trades == 0
    assert s.legs == 0
    assert s.net_pnl == 0.0
    assert s.profit_factor == 0.0


INTEGER_SUMMARY_FIELDS = {
    "trades",
    "legs",
    "wins",
    "losses",
    "scratches",
    "max_consecutive_losses",
}
"""Stated here independently of ``Summary``'s annotations, so this is a second opinion.

``max_consecutive_losses`` is the one that matters: it sits at field 17, so the splat this
replaced would have handed it a float even had someone fixed the argument count.
"""


def test_the_empty_summary_gives_each_field_its_declared_type() -> None:
    s = stats.Summary.empty()
    for name in stats.Summary.columns():
        value = getattr(s, name)
        if name in INTEGER_SUMMARY_FIELDS:
            assert isinstance(value, int) and not isinstance(value, bool), name
        else:
            assert isinstance(value, float), name


def test_a_barren_combination_summarises_exactly_like_an_empty_log() -> None:
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


def test_grid_size_is_the_product_of_its_axes() -> None:
    g = sweep.Grid.of(ema_period=[9, 21], use_vwap=[True, False], fast_sma_period=[40, 60, 80])
    assert len(g) == 12
    assert len(list(g.combinations())) == 12


def test_grid_leaves_unswept_parameters_at_their_base_value() -> None:
    base = DeadCatParams(order_quantity=8, commission_per_contract=1.5)
    combos = list(sweep.Grid.of(base, ema_period=[9, 21]).combinations())
    assert {c.order_quantity for c in combos} == {8}
    assert {c.commission_per_contract for c in combos} == {1.5}
    assert sorted(c.ema_period for c in combos) == [9, 21]


def test_empty_grid_yields_the_base_alone() -> None:
    assert len(list(sweep.Grid.of().combinations())) == 1


def test_grid_rejects_unknown_parameters() -> None:
    with pytest.raises(sweep.SweepError, match="unknown sweep parameter"):
        sweep.Grid.of(emma_period=[9])


def test_grid_rejects_an_axis_with_no_values() -> None:
    # An empty axis multiplies the grid by zero, so the sweep would silently run nothing.
    with pytest.raises(sweep.SweepError, match="has no values"):
        sweep.Grid.of(ema_period=[])


def test_grid_rejects_an_axis_whose_filter_is_switched_off() -> None:
    # The NinjaScript's current defaults leave the slow SMA off, so sweeping its period
    # would produce identical rows and multiply runtime for nothing.
    base = DeadCatParams(use_slow_sma=False)
    with pytest.raises(sweep.SweepError, match="cannot affect any result"):
        sweep.Grid.of(base, slow_sma_period=[120, 175])


def test_gated_axis_is_allowed_when_its_toggle_is_also_swept() -> None:
    base = DeadCatParams(use_slow_sma=False)
    g = sweep.Grid.of(base, slow_sma_period=[120, 175], use_slow_sma=[True, False])
    assert g.dead_axes() == {}
    assert len(g) == 4


def test_required_context_covers_every_combination() -> None:
    base = DeadCatParams(use_slow_sma=True)
    g = sweep.Grid.of(base, ema_period=[9, 21], fast_sma_period=[40, 60], slow_sma_period=[150, 200])
    spec = g.required_context()
    assert spec.ma_keys == conditions.ma_keys(ema=(9, 21), sma=(40, 60, 150, 200))


def test_required_context_includes_unswept_defaults() -> None:
    g = sweep.Grid.of(DeadCatParams(ema_period=11, fast_sma_period=80), use_vwap=[True, False])
    spec = g.required_context()
    assert conditions.ma_key("ema", 11) in spec.ma_keys
    assert conditions.ma_key("sma", 80) in spec.ma_keys


def test_sweeping_a_kind_builds_every_pair_it_crosses_with_its_period() -> None:
    base = DeadCatParams(use_slow_sma=True)
    g = sweep.Grid.of(base, ema_kind=["ema", "wma"], ema_period=[9, 21])
    spec = g.required_context()
    assert spec.ma_keys == conditions.ma_keys(
        ema=(9, 21),
        wma=(9, 21),
        sma=(base.fast_sma_period, base.slow_sma_period),
    )
    assert len(g) == 4


def test_a_kind_axis_is_dead_while_the_filter_reading_it_is_off() -> None:
    base = DeadCatParams(use_slow_sma=False)
    with pytest.raises(sweep.SweepError, match="slow_sma_kind"):
        sweep.Grid.of(base, slow_sma_kind=["sma", "wma"])


# -- parallel execution -------------------------------------------------------


def test_chunk_bounds_cover_every_combination_exactly_once() -> None:
    # The property that matters: no combination run twice, none dropped, order preserved.
    for total in (1, 7, 100, 193):
        for workers in (1, 3, 8):
            bounds = sweep.chunk_bounds(total, workers)
            covered = [i for start, stop in bounds for i in range(start, stop)]
            assert covered == list(range(total)), f"{total} over {workers} workers"


def test_chunk_bounds_of_an_empty_grid_is_no_work() -> None:
    assert sweep.chunk_bounds(0, 4) == []


def test_chunk_bounds_respects_an_explicit_size() -> None:
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
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
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
        ema_period=[9, 21],
        fast_sma_period=[40, 60],
    )
    return bars, grid, sweep.prepare_for(bars, grid)


def test_slim_drops_the_bar_columns_but_shares_the_arrays(prepared) -> None:
    _, _, data = prepared
    lean = data.slim()
    assert list(lean.bars.columns) == []
    assert lean.index.equals(data.index)
    # Shared, not copied -- copying is exactly the cost slim() exists to avoid.
    assert lean.close is data.close
    assert lean.mas["ema"].below is data.mas["ema"].below


def test_the_simulator_meets_the_trade_schema(prepared) -> None:
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


def test_a_slim_dataset_simulates_identically(prepared) -> None:
    _, grid, data = prepared
    params = next(grid.combinations())
    pd.testing.assert_frame_equal(runner.run_deadcat(data, params), runner.run_deadcat(data.slim(), params))


def test_parallel_sweep_matches_serial_exactly(prepared) -> None:
    bars, grid, data = prepared
    serial, _ = sweep.sweep(bars, grid, data=data, n_jobs=1)
    parallel, _ = sweep.sweep(bars, grid, data=data, n_jobs=2)
    assert serial["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    pd.testing.assert_frame_equal(serial, parallel)


def test_parallel_sweep_keys_trade_logs_by_combo_id(prepared) -> None:
    bars, grid, data = prepared
    frame, logs = sweep.sweep(bars, grid, data=data, n_jobs=2, keep_trades=True)
    assert sorted(logs) == list(range(len(grid)))
    assert list(frame["combo_id"]) == list(range(len(grid)))


# -- sweep_axes: strategy, resolution and contract (M17.4) --------------------


@pytest.fixture(scope="module")
def axis_bars():
    """Enough bars that a 15-minute resample still has a workable series."""
    return synthetic_bars(n=12_000)


@pytest.fixture(scope="module")
def axis_grid():
    return sweep.Grid.of(DeadCatParams(bars_required_to_trade=200), ema_period=[9, 21])


def test_the_default_call_is_one_axis_point_tagged_with_what_it_ran(axis_bars, axis_grid) -> None:
    frame, logs = sweep.sweep_axes(axis_bars, axis_grid, NQ)
    assert len(frame) == len(axis_grid)
    assert set(frame["strategy"]) == {"DeadCatBounce"}
    assert set(frame["resolution"]) == {1}
    assert frame["contract"].isna().all(), "a single frame is the spliced series"
    assert set(frame["tier2"]) == {"reconciled"}
    assert logs == {}


def test_the_axis_columns_lead_so_no_row_is_anonymous(axis_bars, axis_grid) -> None:
    frame, _ = sweep.sweep_axes(axis_bars, axis_grid, NQ)
    assert list(frame.columns[:4]) == list(sweep.AxisPoint._fields)


def test_the_axis_point_names_the_same_columns_the_results_store_declares() -> None:
    """Pins the two together without coupling ``sweep`` to ``results``.

    ``sweep_axes`` produces the tags and ``save_sweep`` stores them; if the names drift the
    columns silently arrive null rather than failing.
    """
    assert sweep.AxisPoint._fields == tuple(results.AXIS_COLUMNS)


def test_one_axis_point_reproduces_a_plain_sweep_exactly(axis_bars, axis_grid) -> None:
    """The mechanism must not perturb the path every stored result was produced on."""
    plain, _ = sweep.sweep(axis_bars, axis_grid, NQ)
    axed, _ = sweep.sweep_axes(axis_bars, axis_grid, NQ)
    assert plain["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    pd.testing.assert_frame_equal(axed.drop(columns=list(sweep.AxisPoint._fields)), plain)


# -- the resolution axis -------------------------------------------------------


def test_the_resolution_axis_runs_each_bar_size_and_tags_it(axis_bars, axis_grid) -> None:
    frame, _ = sweep.sweep_axes(axis_bars, axis_grid, NQ, resolutions=[1, 5, 15])
    assert len(frame) == 3 * len(axis_grid)
    assert sorted(frame["resolution"].unique()) == [1, 5, 15]
    for minutes in (1, 5, 15):
        block = frame[frame["resolution"] == minutes]
        assert sorted(block["combo_id"]) == list(range(len(axis_grid)))


def test_a_coarser_resolution_really_is_run_on_coarser_bars(axis_bars, axis_grid) -> None:
    """Guards the guard: tagging a row '5' while running 1-minute bars would look fine.

    Fewer bars means fewer signals, so the leg counts must actually move -- and the 5-minute
    run must match what resampling by hand and sweeping directly produces.
    """
    frame, _ = sweep.sweep_axes(axis_bars, axis_grid, NQ, resolutions=[1, 5])
    one = frame[frame["resolution"] == 1].reset_index(drop=True)
    five = frame[frame["resolution"] == 5].reset_index(drop=True)
    assert five["legs"].sum() < one["legs"].sum(), "coarser bars produced no fewer legs"

    direct, _ = sweep.sweep(resample.resample(axis_bars, 5), axis_grid, NQ)
    pd.testing.assert_frame_equal(five.drop(columns=list(sweep.AxisPoint._fields)), direct)


def test_the_one_minute_path_is_the_untouched_frame(axis_bars) -> None:
    """``resample(bars, 1)`` returns the same object, so resolution 1 cannot drift."""
    assert resample.resample(axis_bars, 1) is axis_bars


# -- the contract axis ---------------------------------------------------------


def contract_frames(bars) -> dict:
    """Two disjoint halves standing in for two front-month windows."""
    midpoint = len(bars) // 2
    return {"MNQ 03-24": bars.iloc[:midpoint], "MNQ 06-24": bars.iloc[midpoint:]}


def test_the_contract_axis_runs_each_frame_and_names_it(axis_bars, axis_grid) -> None:
    frames = contract_frames(axis_bars)
    frame, _ = sweep.sweep_axes(frames, axis_grid, NQ)
    assert len(frame) == 2 * len(axis_grid)
    assert set(frame["contract"]) == {"MNQ 03-24", "MNQ 06-24"}
    assert frame["contract"].notna().all(), "a named contract must never tag as spliced"


def test_a_per_contract_row_matches_sweeping_that_contract_directly(axis_bars, axis_grid) -> None:
    frames = contract_frames(axis_bars)
    frame, _ = sweep.sweep_axes(frames, axis_grid, NQ)
    direct, _ = sweep.sweep(frames["MNQ 06-24"], axis_grid, NQ)
    mine = frame[frame["contract"] == "MNQ 06-24"].reset_index(drop=True)
    pd.testing.assert_frame_equal(mine.drop(columns=list(sweep.AxisPoint._fields)), direct)


# -- the strategy axis ---------------------------------------------------------


def test_the_strategy_axis_takes_a_grid_each_rather_than_a_name_each(axis_bars) -> None:
    """Two archetypes, each swept over its *own* parameters.

    This is why the axis is grids and not names: ``require_previous_red`` is a field of
    PullBackAndGo alone, so no single grid could express both sides of this call.
    """
    deadcat = sweep.Grid.of(DeadCatParams(bars_required_to_trade=200), ema_period=[9, 21])
    pullback = sweep.Grid.of(
        PullBackAndGoParams(bars_required_to_trade=200),
        require_previous_red=[True, False],
    )
    frame, _ = sweep.sweep_axes(axis_bars, [deadcat, pullback], NQ)
    assert set(frame["strategy"]) == {"DeadCatBounce", "PullBackAndGo"}
    assert len(frame) == len(deadcat) + len(pullback)
    # combo_id restarts per grid, which is exactly why strategy is part of the key.
    for name in ("DeadCatBounce", "PullBackAndGo"):
        block = frame[frame["strategy"] == name]
        assert sorted(block["combo_id"]) == [0, 1]


def test_the_original_archetype_sweeps_beside_a_ported_one(axis_bars) -> None:
    """The protocol test M18 exists to be. EmaCrossover shares no parameter with
    DeadCatBounce, reads a different set of series, enters by a different mechanism and
    exits on a rule -- and ``sweep_axes`` needs no knowledge of any of that.
    """
    from nqbt.sim.types import EmaCrossoverParams

    deadcat = sweep.Grid.of(DeadCatParams(bars_required_to_trade=200), ema_period=[9, 21])
    cross = sweep.Grid.of(
        EmaCrossoverParams(bars_required_to_trade=200),
        atr_stop_multiple=[1.5, 2.5],
    )
    frame, _ = sweep.sweep_axes(axis_bars, [deadcat, cross], NQ)
    assert set(frame["strategy"]) == {"DeadCatBounce", "EmaCrossover"}
    tiers = dict(zip(frame["strategy"], frame["tier2"], strict=True))
    assert tiers == {"DeadCatBounce": "reconciled", "EmaCrossover": "tier-1-only"}


def test_each_strategys_rows_carry_its_own_tier2_status(axis_bars) -> None:
    """A per-archetype property, so it cannot be a column written once for the run."""
    from nqbt import archetypes as registry

    tier1 = registry.Archetype(
        name="UnreconciledProbe",
        params_cls=DeadCatParams,
        run=registry.DEADCATBOUNCE.run,
        legs=registry.DEADCATBOUNCE.legs,
        signal=registry.DEADCATBOUNCE.signal,
        tier2=registry.Tier2Status.TIER1_ONLY,
    )
    grids = [
        sweep.Grid.of(DeadCatParams(bars_required_to_trade=200)),
        sweep.Grid(axes={}, base=DeadCatParams(bars_required_to_trade=200), archetype=tier1),
    ]
    frame, _ = sweep.sweep_axes(axis_bars, grids, NQ)
    by_strategy = dict(zip(frame["strategy"], frame["tier2"], strict=True))
    assert by_strategy == {"DeadCatBounce": "reconciled", "UnreconciledProbe": "tier-1-only"}


def test_every_grid_at_one_axis_point_shares_a_single_dataset(axis_bars, monkeypatch) -> None:
    """The memory argument, pinned.

    ``prepare`` is the expensive part and the parallel path memmaps its arrays to every
    worker, so a dataset per grid would multiply that by the number of strategies. The union
    of the grids' ``ContextSpec``s is what makes one dataset serve them all.
    """
    calls = []
    real = context.prepare

    def counting(bars, spec=context.DEFAULT_SPEC, **kwargs):
        calls.append(spec)
        return real(bars, spec, **kwargs)

    monkeypatch.setattr(context, "prepare", counting)
    grids = [
        sweep.Grid.of(DeadCatParams(bars_required_to_trade=200, use_vwap=True)),
        sweep.Grid.of(PullBackAndGoParams(bars_required_to_trade=200), ema_period=[9, 21]),
    ]
    sweep.sweep_axes(axis_bars, grids, NQ, resolutions=[1, 5])
    assert len(calls) == 2, "one prepare per axis point, not one per grid"
    # And the union really is a union: VWAP comes from the first grid, period 9 the second.
    for spec in calls:
        assert spec.needs_vwap
        assert conditions.ma_key("ema", 9) in spec.ma_keys
        assert conditions.ma_key("ema", 21) in spec.ma_keys


# -- the axes compose ----------------------------------------------------------


def test_the_axes_multiply_and_every_block_is_distinguishable(axis_bars) -> None:
    grids = [
        sweep.Grid.of(DeadCatParams(bars_required_to_trade=200)),
        sweep.Grid.of(PullBackAndGoParams(bars_required_to_trade=200)),
    ]
    frames = contract_frames(axis_bars)
    frame, _ = sweep.sweep_axes(frames, grids, NQ, resolutions=[1, 5])
    assert len(frame) == 2 * 2 * 2  # contracts x resolutions x strategies, one combo each
    keys = set(zip(frame["strategy"], frame["resolution"], frame["contract"], strict=True))
    assert len(keys) == 8, "two blocks share an axis point and would aggregate as one"


def test_combo_id_means_the_same_parameters_at_every_axis_point(axis_bars, axis_grid) -> None:
    """What makes a cross-resolution comparison a comparison rather than a coincidence."""
    frame, _ = sweep.sweep_axes(axis_bars, axis_grid, NQ, resolutions=[1, 5, 15])
    for combo_id, params in enumerate(axis_grid.combinations()):
        block = frame[frame["combo_id"] == combo_id]
        assert len(block) == 3
        assert set(block["ema_period"]) == {params.ema_period}


# -- logs and parallelism ------------------------------------------------------


def test_logs_come_back_keyed_by_axis_point_and_combination(axis_bars, axis_grid) -> None:
    frames = contract_frames(axis_bars)
    _, logs = sweep.sweep_axes(frames, axis_grid, NQ, resolutions=[1, 5], keep_trades=True)
    assert len(logs) == 2 * 2 * len(axis_grid)
    for (point, combo_id), log in logs.items():
        assert isinstance(point, sweep.AxisPoint)
        assert point.contract in {"MNQ 03-24", "MNQ 06-24"}
        assert point.resolution in {1, 5}
        assert combo_id in range(len(axis_grid))
        assert {"trade_id", "net_pnl"} <= set(log.columns)


def test_no_logs_are_kept_unless_asked_for(axis_bars, axis_grid) -> None:
    _, logs = sweep.sweep_axes(axis_bars, axis_grid, NQ, resolutions=[1, 5])
    assert logs == {}


def test_a_parallel_multi_axis_sweep_matches_serial_exactly(axis_bars, axis_grid) -> None:
    """The guarantee ``sweep`` already gives, which must survive the axes above it."""
    frames = contract_frames(axis_bars)
    serial, _ = sweep.sweep_axes(frames, axis_grid, NQ, resolutions=[1, 5], n_jobs=1)
    parallel, _ = sweep.sweep_axes(frames, axis_grid, NQ, resolutions=[1, 5], n_jobs=2)
    assert serial["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    pd.testing.assert_frame_equal(serial, parallel)


# -- refusals ------------------------------------------------------------------


def test_sweep_axes_refuses_an_empty_axis(axis_bars, axis_grid) -> None:
    with pytest.raises(sweep.SweepError, match="at least one grid"):
        sweep.sweep_axes(axis_bars, [], NQ)
    with pytest.raises(sweep.SweepError, match="resolutions is empty"):
        sweep.sweep_axes(axis_bars, axis_grid, NQ, resolutions=[])
    with pytest.raises(sweep.SweepError, match="contract mapping is empty"):
        sweep.sweep_axes({}, axis_grid, NQ)


# -- results store ------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return tmp_path / "sweeps.duckdb"


def fake_results(n=3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "combo_id": range(n),
            "ema_period": [9, 21, 30][:n],
            "trades": [100, 200, 5][:n],
            "profit_factor": [1.2, 1.5, 9.9][:n],
            "net_pnl": [500.0, 900.0, 40.0][:n],
        },
    )


def fake_bars() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=10, freq="min", tz="UTC")
    return pd.DataFrame({"close": np.arange(10.0)}, index=idx)


def test_save_and_reload_a_sweep(db) -> None:
    sid = results.save_sweep(
        fake_results(),
        root="MNQ",
        instrument="MNQ",
        bars=fake_bars(),
        axes={"ema_period": [9, 21, 30]},
        db_path=db,
    )
    assert sid == 1
    listed = results.list_sweeps(db)
    assert len(listed) == 1
    assert listed.loc[0, "combos"] == 3
    assert results.query("SELECT COUNT(*) c FROM combos", db).loc[0, "c"] == 3


def test_sweep_ids_increment_and_rows_stay_tagged(db) -> None:
    for _ in range(3):
        results.save_sweep(
            fake_results(),
            root="MNQ",
            instrument="MNQ",
            bars=fake_bars(),
            axes={},
            db_path=db,
        )
    assert list(results.list_sweeps(db)["sweep_id"]) == [3, 2, 1]
    counts = results.query("SELECT sweep_id, COUNT(*) n FROM combos GROUP BY 1 ORDER BY 1", db)
    assert list(counts["n"]) == [3, 3, 3]


def test_best_applies_a_trade_floor(db) -> None:
    results.save_sweep(fake_results(), root="MNQ", instrument="MNQ", bars=fake_bars(), axes={}, db_path=db)
    # combo 2 has the best profit factor on five trades, which is noise, not an edge.
    top = results.best(by="profit_factor", top=5, min_trades=30, db_path=db)
    assert 5 not in list(top["trades"])
    assert top.iloc[0]["profit_factor"] == pytest.approx(1.5)


def test_rank_ignores_undersampled_combinations() -> None:
    ranked = sweep.rank(fake_results(), by="profit_factor", top=5, min_trades=30)
    assert list(ranked["trades"]) == [200, 100]


def test_a_later_sweep_with_extra_statistics_does_not_shift_columns(db) -> None:
    results.save_sweep(fake_results(), root="MNQ", instrument="MNQ", bars=fake_bars(), axes={}, db_path=db)
    wider = fake_results()
    wider["brand_new_stat"] = [1.0, 2.0, 3.0]
    results.save_sweep(wider, root="MNQ", instrument="MNQ", bars=fake_bars(), axes={}, db_path=db)
    rows = results.query("SELECT sweep_id, ema_period, profit_factor FROM combos ORDER BY sweep_id", db)
    assert len(rows) == 6
    assert rows["profit_factor"].notna().all()


def fake_log(n=2) -> pd.DataFrame:
    """The columns ``save_trades`` needs to see; the schema itself is pinned elsewhere."""
    return pd.DataFrame(
        {
            "source": ["sim"] * n,
            "instrument": ["MNQ"] * n,
            "trade_id": range(n),
            "net_pnl": [10.0, -4.0][:n],
        },
    )


def test_a_trade_log_stored_twice_doubles_and_replacing_it_does_not(db) -> None:
    """Nothing about a doubled log looks wrong -- it still validates, and every statistic
    taken from it moves -- so the tool that re-runs a shortlist stores with ``replace``."""
    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db)
    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db)
    assert results.query("SELECT COUNT(*) c FROM trades", db).loc[0, "c"] == 4

    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db, replace=True)
    assert results.query("SELECT COUNT(*) c FROM trades", db).loc[0, "c"] == 2


def test_replacing_a_trade_log_leaves_every_other_combination_alone(db) -> None:
    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db)
    results.save_trades(fake_log(), sweep_id=1, combo_id=1, db_path=db)
    results.save_trades(fake_log(), sweep_id=2, combo_id=0, db_path=db)
    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db, replace=True)
    counts = results.query("SELECT sweep_id, combo_id, COUNT(*) n FROM trades GROUP BY 1, 2", db)
    assert list(counts["n"]) == [2, 2, 2]


def test_replacing_into_a_database_with_no_trades_table_yet_just_stores(db) -> None:
    """The first shortlist stored into a fresh campaign database takes this path."""
    results.save_trades(fake_log(), sweep_id=1, combo_id=0, db_path=db, replace=True)
    assert results.query("SELECT COUNT(*) c FROM trades", db).loc[0, "c"] == 2


# -- the axis columns (M17.5) --------------------------------------------------


def save(db, results_frame=None, **kwargs) -> int:
    """``save_sweep`` with the arguments that are noise for these tests filled in."""
    defaults = {"root": "MNQ", "instrument": "MNQ", "bars": fake_bars(), "axes": {}}
    return results.save_sweep(
        fake_results() if results_frame is None else results_frame,
        db_path=db,
        **{**defaults, **kwargs},
    )


def test_axis_tags_land_on_both_tables(db) -> None:
    save(db, strategy="PullBackAndGo", resolution=5, contract="MNQ 03-24", tier2="reconciled")
    swept = results.query("SELECT * FROM sweeps", db).iloc[0]
    assert (swept["strategy"], swept["resolution"]) == ("PullBackAndGo", 5)
    assert (swept["contract"], swept["tier2"]) == ("MNQ 03-24", "reconciled")
    combos = results.query("SELECT * FROM combos", db)
    assert set(combos["strategy"]) == {"PullBackAndGo"}
    assert set(combos["resolution"]) == {5}
    assert set(combos["contract"]) == {"MNQ 03-24"}
    assert set(combos["tier2"]) == {"reconciled"}


def test_a_null_contract_means_the_spliced_series_not_a_missing_value(db) -> None:
    save(db, strategy="DeadCatBounce", resolution=1)
    row = results.query("SELECT contract FROM sweeps", db).iloc[0]
    assert row["contract"] is None
    assert "spliced" in results.NULL_MEANS["contract"]


def test_an_untagged_save_still_works_and_leaves_the_axes_null(db) -> None:
    """Every existing caller passes none of these, and must keep working unchanged."""
    save(db)
    row = results.query("SELECT * FROM sweeps", db).iloc[0]
    for name in results.AXIS_COLUMNS:
        assert pd.isna(row[name]), name
    assert pd.isna(row["batch_id"])


def test_a_spliced_first_sweep_does_not_type_the_contract_column_as_a_number(db) -> None:
    """The trap that makes this worth pinning rather than trusting.

    DuckDB types a new table from the frame that creates it, and an all-null *object*
    column infers as INTEGER -- so a first sweep over the continuous series, where
    ``contract`` is null by definition, would create ``combos.contract`` as an integer and
    every later per-contract sweep would fail to insert into it.
    """
    save(db)  # contract is null throughout: the case that sets the column's type
    described = {name: sql_type for name, sql_type, *_ in results.query("DESCRIBE combos", db).itertuples(index=False)}
    assert described["contract"] == "VARCHAR"
    assert described["resolution"] == "BIGINT"
    # And the type holds: a real contract name inserts into the column the null one made.
    save(db, contract="MNQ 06-24", resolution=15)
    assert set(results.query("SELECT contract FROM combos", db)["contract"].dropna()) == {"MNQ 06-24"}


def test_per_row_axis_values_survive_rather_than_being_overwritten(db) -> None:
    """What ``sweep_axes`` needs: a frame already spanning axis points keeps its own tags."""
    frame = fake_results()
    frame["contract"] = ["MNQ 03-24", "MNQ 06-24", "MNQ 09-24"]
    frame["resolution"] = [1, 5, 15]
    save(db, results_frame=frame, strategy="DeadCatBounce")
    stored = results.query("SELECT contract, resolution FROM combos ORDER BY resolution", db)
    assert list(stored["contract"]) == ["MNQ 03-24", "MNQ 06-24", "MNQ 09-24"]
    assert list(stored["resolution"]) == [1, 5, 15]


def test_batch_id_ties_one_multi_axis_run_together(db) -> None:
    batch = results.next_batch_id(db)
    for minutes in (1, 5, 15):
        save(db, resolution=minutes, batch_id=batch)
    save(db, resolution=1)  # a separate, later single sweep
    grouped = results.query("SELECT batch_id, COUNT(*) n FROM sweeps GROUP BY 1 ORDER BY n DESC", db)
    assert list(grouped["n"]) == [3, 1]
    assert grouped.iloc[0]["batch_id"] == batch


def test_next_batch_id_advances_past_the_batches_already_stored(db) -> None:
    first = results.next_batch_id(db)
    save(db, batch_id=first)
    assert results.next_batch_id(db) == first + 1


def test_list_sweeps_shows_what_a_row_was_run_on(db) -> None:
    save(db, strategy="DeadCatBounce", resolution=15, contract="MNQ 03-24", tier2="reconciled")
    listed = results.list_sweeps(db)
    for name in (*results.AXIS_COLUMNS, "batch_id"):
        assert name in listed.columns, name
    assert listed.loc[0, "resolution"] == 15


# -- migrating a database written before the axis columns existed --------------


def legacy_database(db) -> None:
    """A ``sweeps``/``combos`` pair in the pre-M17.5 shape, with a row in each.

    Written with raw SQL rather than by an older ``save_sweep``, so the test does not
    depend on code that no longer exists.
    """
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE sweeps (sweep_id BIGINT PRIMARY KEY, created_utc TIMESTAMP, "
        "root VARCHAR, instrument VARCHAR, back_adjust BOOLEAN, bars BIGINT, "
        "first_bar TIMESTAMP, last_bar TIMESTAMP, combos BIGINT, elapsed_s DOUBLE, "
        "axes VARCHAR, notes VARCHAR, host VARCHAR)",
    )
    con.execute(
        "INSERT INTO sweeps VALUES (1, NOW(), 'MNQ', 'MNQ', true, 10, NOW(), NOW(), 1, 0.5, '{}', 'old', 'box')",
    )
    con.execute("CREATE TABLE combos (sweep_id BIGINT, combo_id BIGINT, profit_factor DOUBLE)")
    con.execute("INSERT INTO combos VALUES (1, 0, 1.23)")
    con.close()


def test_an_existing_database_gains_the_columns_and_keeps_its_rows(db) -> None:
    legacy_database(db)
    results.connect(db).close()
    swept = results.query("SELECT * FROM sweeps", db)
    assert len(swept) == 1
    assert swept.loc[0, "notes"] == "old"
    combos = results.query("SELECT * FROM combos", db)
    assert len(combos) == 1
    assert combos.loc[0, "profit_factor"] == pytest.approx(1.23)
    for name in results.AXIS_COLUMNS:
        assert pd.isna(swept.loc[0, name]) and pd.isna(combos.loc[0, name]), name
    assert pd.isna(swept.loc[0, "batch_id"])


def test_a_migrated_database_puts_every_value_in_the_column_it_names(db) -> None:
    """Why ``save_sweep`` inserts by name, and not merely because a positional one raised.

    ALTER appends the axis columns at the end, while a fresh database declares them in the
    middle, so one positional insert statement cannot serve both. The clash that surfaced
    this was ``'MNQ'`` into a BOOLEAN, which raises -- but ``root``/``instrument``/
    ``strategy``/``contract`` are four adjacent VARCHARs, and transposing those stores a
    plausible row that reads as a result rather than an error.
    """
    legacy_database(db)
    results.save_sweep(
        fake_results(),
        root="NQ",
        instrument="MNQ",
        bars=fake_bars(),
        axes={"ema_period": [9]},
        back_adjust=True,
        notes="tagged",
        elapsed_s=2.5,
        strategy="PullBackAndGo",
        resolution=5,
        contract="MNQ 06-24",
        tier2="reconciled",
        batch_id=7,
        db_path=db,
    )
    row = results.query("SELECT * FROM sweeps WHERE sweep_id = 2", db).iloc[0]
    assert row["root"] == "NQ"
    assert row["instrument"] == "MNQ"
    assert row["strategy"] == "PullBackAndGo"
    assert row["contract"] == "MNQ 06-24"
    assert row["tier2"] == "reconciled"
    assert row["batch_id"] == 7
    assert bool(row["back_adjust"]) is True
    assert row["bars"] == len(fake_bars())
    assert row["combos"] == 3
    assert row["notes"] == "tagged"
    assert row["elapsed_s"] == pytest.approx(2.5)
    assert json.loads(row["axes"]) == {"ema_period": [9]}


def test_migrating_twice_is_a_no_op(db) -> None:
    legacy_database(db)
    for _ in range(3):
        results.connect(db).close()
    assert len(results.query("SELECT * FROM sweeps", db)) == 1


def test_a_migrated_database_stores_tags_on_new_rows_beside_untagged_old_ones(db) -> None:
    """The requirement in one assertion: old rows null, new rows tagged, same table."""
    legacy_database(db)
    save(db, strategy="PullBackAndGo", resolution=5, contract="MNQ 06-24")
    rows = results.query("SELECT sweep_id, strategy, resolution FROM sweeps ORDER BY sweep_id", db)
    assert pd.isna(rows.loc[0, "strategy"])
    assert rows.loc[1, "strategy"] == "PullBackAndGo"
    assert rows.loc[1, "resolution"] == 5
    combos = results.query("SELECT contract FROM combos ORDER BY sweep_id", db)
    assert pd.isna(combos.loc[0, "contract"])
    assert combos.loc[1, "contract"] == "MNQ 06-24"


def test_a_later_sweep_missing_a_stored_statistic_gets_null_not_a_shifted_row(db) -> None:
    """The other half of writing by name, and the one that would read as a result.

    A frame *narrower* than the table has to be widened with nulls in the right places. By
    position it would instead slide every value left, so ``net_pnl`` would be stored under
    ``brand_new_stat`` and the row would look entirely plausible.
    """
    wider = fake_results()
    wider["brand_new_stat"] = [1.0, 2.0, 3.0]
    save(db, results_frame=wider)
    save(db, results_frame=fake_results())  # narrower: no brand_new_stat this time
    rows = results.query(
        "SELECT sweep_id, brand_new_stat, net_pnl FROM combos ORDER BY sweep_id, combo_id",
        db,
    )
    assert list(rows[rows["sweep_id"] == 1]["brand_new_stat"]) == [1.0, 2.0, 3.0]
    assert rows[rows["sweep_id"] == 2]["brand_new_stat"].isna().all()
    assert list(rows[rows["sweep_id"] == 2]["net_pnl"]) == [500.0, 900.0, 40.0]


def test_axis_values_from_numpy_survive_the_json_round_trip(db) -> None:
    """A grid built from ``np.arange`` holds numpy scalars, which ``json.dumps`` refuses."""
    save(db, axes={"ema_period": list(np.arange(9, 12, dtype=np.int64))})
    stored = results.query("SELECT axes FROM sweeps", db).loc[0, "axes"]
    assert json.loads(stored) == {"ema_period": [9, 10, 11]}


def test_saving_a_shortlisted_combinations_trade_log(db) -> None:
    sid = save(db, strategy="DeadCatBounce", resolution=1)
    log = trade_log([(1, 1, 5.0, 2, False), (2, 1, -3.0, 4, True)])
    log["source"] = "sim"
    log["instrument"] = "MNQ"
    results.save_trades(log, sweep_id=sid, combo_id=2, db_path=db)
    stored = results.query("SELECT * FROM trades ORDER BY trade_id", db)
    assert list(stored["sweep_id"]) == [sid, sid]
    assert list(stored["combo_id"]) == [2, 2]
    assert list(stored["net_pnl"]) == [5.0, -3.0]
    assert set(stored["source"]) == {"sim"}


def test_best_can_be_narrowed_to_one_sweep(db) -> None:
    save(db)
    save(db, results_frame=fake_results().assign(profit_factor=[3.0, 3.1, 3.2]))
    everywhere = results.best(by="profit_factor", top=5, min_trades=30, db_path=db)
    assert set(everywhere["sweep_id"]) == {1, 2}
    just_one = results.best(sweep_id=1, by="profit_factor", top=5, min_trades=30, db_path=db)
    assert set(just_one["sweep_id"]) == {1}


def test_the_axis_columns_arrive_at_connect_and_every_other_column_at_its_first_insert(db) -> None:
    """The distinction ``AXIS_COLUMNS`` still makes now that nothing is dropped.

    Both kinds of column reach a legacy table, but only these four are there before a frame
    carrying them is written -- so a query against an untouched old database can group by
    ``contract`` and read nulls, rather than failing on a column that does not exist yet.
    """
    legacy_database(db)
    results.connect(db).close()
    migrated = results.query("DESCRIBE combos", db)
    assert set(results.AXIS_COLUMNS) <= set(migrated["column_name"])
    assert "brand_new_stat" not in set(migrated["column_name"])

    frame = fake_results()
    frame["brand_new_stat"] = [1.0, 2.0, 3.0]
    save(db, results_frame=frame, contract="MNQ 03-24")
    stored = results.query("SELECT * FROM combos WHERE sweep_id = 2", db)
    assert set(stored["contract"]) == {"MNQ 03-24"}
    assert list(stored["brand_new_stat"]) == [1.0, 2.0, 3.0]


# -- widening rather than dropping (#201) --------------------------------------


def insidebar_shaped() -> pd.DataFrame:
    """A frame from a different parameter class: three columns the first sweep never had."""
    frame = fake_results()
    frame["error_margin"] = [0.01, 0.05, 0.1]
    frame["atr_length"] = [3, 14, 14]
    frame["atr_multiplier"] = [5.0, 10.0, 20.0]
    return frame


def test_a_second_parameter_class_widens_the_table_rather_than_losing_its_columns(db) -> None:
    """The trap this exists to close: one ``combos`` table holding two parameter classes.

    Appending an InsideBar-shaped frame to a table created from a DeadCat-shaped one used to
    store it with ``error_margin``, ``atr_length`` and ``atr_multiplier`` thrown away.
    """
    save(db, strategy="DeadCatBounce")
    save(db, results_frame=insidebar_shaped(), strategy="InsideBar")
    stored = results.query("SELECT * FROM combos WHERE strategy = 'InsideBar' ORDER BY combo_id", db)
    assert list(stored["error_margin"]) == [0.01, 0.05, 0.1]
    assert list(stored["atr_length"]) == [3, 14, 14]
    assert list(stored["atr_multiplier"]) == [5.0, 10.0, 20.0]


def test_the_rows_written_before_a_column_existed_read_null_rather_than_moving(db) -> None:
    """Widening is what the old rows see, and it must not disturb what they already hold."""
    save(db, strategy="DeadCatBounce")
    save(db, results_frame=insidebar_shaped(), strategy="InsideBar")
    earlier = results.query("SELECT * FROM combos WHERE strategy = 'DeadCatBounce' ORDER BY combo_id", db)
    assert earlier["atr_multiplier"].isna().all()
    assert list(earlier["ema_period"]) == [9, 21, 30]
    assert list(earlier["net_pnl"]) == [500.0, 900.0, 40.0]


def test_a_column_the_stored_type_cannot_give_back_is_refused(db) -> None:
    """The loud path: a value silently rounded into the stored type reads as a result."""
    integral = fake_results()
    integral["atr_multiplier"] = [5, 10, 20]  # BIGINT, because this grid swept whole numbers
    save(db, results_frame=integral)
    fractional = fake_results()
    fractional["atr_multiplier"] = [2.5, 3.5, 20.0]
    with pytest.raises(results.ResultsError, match="atr_multiplier"):
        save(db, results_frame=fractional)
    assert len(results.query("SELECT * FROM combos", db)) == 3


def test_a_type_that_does_give_the_value_back_still_inserts(db) -> None:
    """Measured loss, not a rule about casts: 5.0 into a BIGINT column loses nothing."""
    integral = fake_results()
    integral["atr_multiplier"] = [5, 10, 20]
    save(db, results_frame=integral)
    whole = fake_results()
    whole["atr_multiplier"] = [5.0, 10.0, 20.0]
    save(db, results_frame=whole)
    stored = results.query("SELECT atr_multiplier FROM combos ORDER BY sweep_id, combo_id", db)
    assert list(stored["atr_multiplier"]) == [5, 10, 20, 5, 10, 20]


def test_a_column_named_like_a_sql_keyword_survives_the_widening(db) -> None:
    """``window`` is one of the campaign's own columns, and it is a reserved word."""
    save(db)
    windowed = fake_results()
    windowed["window"] = ["selection", "holdout", "holdout"]
    save(db, results_frame=windowed)
    stored = results.query('SELECT "window" FROM combos WHERE sweep_id = 2 ORDER BY combo_id', db)
    assert list(stored["window"]) == ["selection", "holdout", "holdout"]
