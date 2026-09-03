"""Walk-forward splits, and the three ways one stops meaning anything.

The split geometry can leak, so the tests assert the *property* -- no test bar is ever a
train bar, and the out-of-sample windows tile the region exactly. Selection can happen on
data the measurement also sees. And an uncosted run selects for trade frequency, which is
the one thing costs punish, so it must be refused rather than defaulted.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import costs, stats, sweep, walkforward
from nqbt.sim.types import DeadCatParams
from nqbt.walkforward import Split, WalkForwardError

BAR = pd.Timedelta(minutes=1)


def bars(n: int, *, seed: int = 0) -> pd.DataFrame:
    """Build a synthetic minute series with enough movement to produce trades."""
    rng = np.random.default_rng(seed)
    close = 18000 + np.cumsum(rng.normal(0.0, 2.0, size=n))
    high = close + rng.uniform(0.25, 4.0, size=n)
    low = close - rng.uniform(0.25, 4.0, size=n)
    open_ = np.concatenate(([close[0]], close[:-1]))
    index = pd.date_range("2024-01-02 00:00", periods=n, freq=BAR, tz="UTC")

    return pd.DataFrame(
        {
            "open": np.round(open_ * 4) / 4,
            "high": np.round(np.maximum(high, np.maximum(open_, close)) * 4) / 4,
            "low": np.round(np.minimum(low, np.minimum(open_, close)) * 4) / 4,
            "close": np.round(close * 4) / 4,
            "volume": rng.integers(50, 500, size=n),
        },
        index=index,
    )


# -- split geometry ------------------------------------------------------------


def test_no_test_bar_is_ever_a_train_bar() -> None:
    """The leakage property, asserted directly rather than inferred from the arithmetic."""
    for split in walkforward.splits(1000, train_bars=200, test_bars=50):
        train = set(range(split.train_start, split.train_end))
        test = set(range(split.test_start, split.test_end))
        assert not (train & test)
        assert max(train) < min(test)


def test_the_out_of_sample_windows_tile_the_tested_region_exactly() -> None:
    """What makes concatenating their trade logs legitimate rather than double-counting."""
    windows = walkforward.splits(1000, train_bars=200, test_bars=50)
    covered = [pos for s in windows for pos in range(s.test_start, s.test_end)]

    assert len(covered) == len(set(covered))
    assert covered == list(range(windows[0].test_start, windows[-1].test_end))


def test_a_rolling_window_slides_and_an_anchored_one_grows() -> None:
    rolling = walkforward.splits(1000, train_bars=200, test_bars=50)
    anchored = walkforward.splits(1000, train_bars=200, test_bars=50, anchored=True)

    assert {s.train_bars for s in rolling} == {200}
    assert all(s.train_start == 0 for s in anchored)
    assert [s.train_bars for s in anchored] == sorted({s.train_bars for s in anchored})
    assert [s.test_start for s in rolling] == [s.test_start for s in anchored]


def test_an_overlapping_step_still_never_leaks() -> None:
    windows = walkforward.splits(1000, train_bars=200, test_bars=100, step=50)
    assert len(windows) > len(walkforward.splits(1000, train_bars=200, test_bars=100))
    for split in windows:
        assert split.train_end == split.test_start


def test_splits_stop_before_running_off_the_end() -> None:
    windows = walkforward.splits(305, train_bars=200, test_bars=50)
    assert windows[-1].test_end <= 305
    assert len(windows) == 2


def test_exactly_enough_bars_yields_exactly_one_split() -> None:
    windows = walkforward.splits(250, train_bars=200, test_bars=50)
    assert len(windows) == 1
    assert windows[0] == Split(index=0, train_start=0, train_end=200, test_start=200, test_end=250)


def test_one_bar_too_few_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(WalkForwardError, match="at least train_bars \\+ test_bars"):
        walkforward.splits(249, train_bars=200, test_bars=50)


@pytest.mark.parametrize(("train", "test"), [(0, 50), (200, 0), (-1, 50)])
def test_a_window_of_no_bars_raises(train, test) -> None:
    with pytest.raises(WalkForwardError, match="must both be >= 1"):
        walkforward.splits(1000, train_bars=train, test_bars=test)


def test_a_step_of_zero_raises_rather_than_looping_forever() -> None:
    with pytest.raises(WalkForwardError, match="step must be >= 1"):
        walkforward.splits(1000, train_bars=200, test_bars=50, step=0)


def test_split_reports_its_own_lengths() -> None:
    split = Split(index=0, train_start=10, train_end=110, test_start=110, test_end=135)
    assert split.train_bars == 100
    assert split.test_bars == 25


# -- the cost gate -------------------------------------------------------------


def test_an_uncosted_walk_forward_is_refused() -> None:
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.0])
    with pytest.raises(WalkForwardError, match="costs are zero"):
        walkforward.walk_forward(
            bars(600),
            grid,
            costs.FREE,
            train_bars=400,
            test_bars=100,
        )


def test_costs_reach_every_combination_rather_than_only_the_base() -> None:
    """The grid is rebuilt on costed params; a combination must not carry the old zero."""
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.0, 2.5])
    costed = sweep.Grid(
        axes=dict(grid.axes),
        base=costs.LIVE.apply(grid.base),
        archetype=grid.archetype,
    )
    for params in costed.combinations():
        assert params.commission_per_contract == costs.LIVE.commission_per_contract
        assert params.slippage_ticks == costs.LIVE.slippage_ticks
    assert {p.tp_multiplier for p in costed.combinations()} == {1.5, 2.0, 2.5}


def test_a_shortlist_grid_walks_forward_exactly_as_the_axis_that_would_produce_it() -> None:
    """Where a list and a product happen to coincide, the two have to be the same run.

    That is what says the list survives the costed rebuild: drop it there and the grid falls
    back to its base alone, so every fold would "select" the one combination left to it.
    """
    base = DeadCatParams()
    multiples = [1.5, 2.0, 2.5]
    swept = walkforward.walk_forward(
        bars(3000),
        sweep.Grid.of(base, tp_multiplier=multiples),
        costs.LIVE,
        train_bars=2000,
        test_bars=500,
        min_trades=1,
    )
    listed = walkforward.walk_forward(
        bars(3000),
        sweep.Grid.of_combinations([replace(base, tp_multiplier=m) for m in multiples]),
        costs.LIVE,
        train_bars=2000,
        test_bars=500,
        min_trades=1,
    )
    assert swept.table["combos_viable"].max() > 1, "fixture selected from one; the test proves nothing"
    pd.testing.assert_frame_equal(swept.table, listed.table)
    pd.testing.assert_frame_equal(swept.trades, listed.trades)


# -- selection -----------------------------------------------------------------


def test_selection_is_refused_on_a_statistic_with_the_opposite_sense() -> None:
    grid = sweep.Grid.of(DeadCatParams())
    with pytest.raises(WalkForwardError, match="cannot be selected on"):
        walkforward.walk_forward(
            bars(600),
            grid,
            costs.LIVE,
            train_bars=400,
            test_bars=100,
            select_by="max_drawdown",
        )


def test_a_negative_warmup_raises() -> None:
    grid = sweep.Grid.of(DeadCatParams())
    with pytest.raises(WalkForwardError, match="warmup_bars must be >= 0"):
        walkforward.walk_forward(
            bars(600),
            grid,
            costs.LIVE,
            train_bars=400,
            test_bars=100,
            warmup_bars=-1,
        )


def test_a_split_that_selects_nothing_reports_nan_rather_than_picking_noise() -> None:
    """With a high floor no combination is viable, and inventing a winner is the bug."""
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.0])
    result = walkforward.walk_forward(
        bars(3000),
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=500,
        min_trades=10_000_000,
    )

    assert len(result.table) >= 1
    assert result.table["combo_id"].isna().all()
    assert (result.table["combos_viable"] == 0).all()
    assert result.trades.empty
    assert result.summary().splits_selected == 0


def test_a_real_walk_forward_selects_and_measures_on_disjoint_windows() -> None:
    frame = bars(6000, seed=3)
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.5], max_risk_ticks=[40, 80])
    result = walkforward.walk_forward(
        frame,
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=1000,
        min_trades=1,
    )

    assert len(result.table) == 4
    assert result.statistic == "profit_factor"
    assert result.costs is costs.LIVE

    chosen = result.table[result.table["combo_id"].notna()]
    assert len(chosen) > 0
    for row in chosen.itertuples():
        assert row.train_end < row.test_start
        assert row.train_trades >= 1


def test_every_out_of_sample_trade_entered_inside_its_own_test_window() -> None:
    """The measurement half of the leakage property, on real simulated trades."""
    frame = bars(6000, seed=3)
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.5])
    result = walkforward.walk_forward(
        frame,
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=1000,
        min_trades=1,
    )
    if result.trades.empty:
        pytest.skip("no out-of-sample trades on this fixture")

    windows = {s.index: s for s in walkforward.splits(len(frame), train_bars=2000, test_bars=1000)}
    for row in result.trades.itertuples():
        split = windows[row.split]
        assert frame.index[split.test_start] <= row.entry_time <= frame.index[split.test_end - 1]


def test_the_warmup_prefix_does_not_leak_its_trades_into_the_result() -> None:
    frame = bars(6000, seed=3)
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5])
    result = walkforward.walk_forward(
        frame,
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=1000,
        warmup_bars=300,
        min_trades=1,
    )
    if result.trades.empty:
        pytest.skip("no out-of-sample trades on this fixture")

    windows = {s.index: s for s in walkforward.splits(len(frame), train_bars=2000, test_bars=1000)}
    for row in result.trades.itertuples():
        assert row.entry_time >= frame.index[windows[row.split].test_start]


def test_summary_pools_the_out_of_sample_trades_it_reports_the_count_of() -> None:
    frame = bars(6000, seed=3)
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.5])
    result = walkforward.walk_forward(
        frame,
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=1000,
        min_trades=1,
    )
    summary = result.summary()

    assert summary.statistic == "profit_factor"
    assert summary.splits == len(result.table)
    assert summary.splits_selected <= summary.splits
    assert summary.combos_distinct <= 2
    assert summary.test_trades == int(result.table["test_trades"].sum())


def test_pooling_does_not_merge_trades_that_only_share_a_trade_id() -> None:
    """``trade_id`` restarts at 1 in every window, so a naive collapse undercounts."""
    frame = bars(6000, seed=3)
    grid = sweep.Grid.of(DeadCatParams(), tp_multiplier=[1.5, 2.5])
    result = walkforward.walk_forward(
        frame,
        grid,
        costs.LIVE,
        train_bars=2000,
        test_bars=1000,
        min_trades=1,
    )
    if result.trades.empty:
        pytest.skip("no out-of-sample trades on this fixture")

    first_ids = result.trades.groupby("split")["trade_id"].min()
    repeated = bool((first_ids == first_ids.iloc[0]).all())
    assert repeated, "fixture no longer exercises the collision this test exists for"
    assert result.pooled_pnl().size == int(result.table["test_trades"].sum())
    assert result.pooled_pnl().size > stats.per_trade(result.trades).shape[0]
