"""The numpy summary path against the pandas one it replaces.

:func:`nqbt.stats.summarise` is the reference and :func:`nqbt.stats.summarise_legs` is the
fast path a sweep actually takes, so the only question that matters here is whether they
agree **exactly**. Not ``approx``: a sweep ranks combinations against each other, and two
producers agreeing to seven decimals still order a shortlist differently.

Where they can drift is the grouping, since everything after it is literally the same
arithmetic on the same arrays (``stats._summarise_arrays``). That is why the adversarial
summation test below is here at all.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, sessions, stats, sweep, trades
from nqbt.instruments import NQ
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams


def session_bars(days: int = 40, seed: int = 5) -> pd.DataFrame:
    """Minute bars on real CME sessions, so the daily grouping has days to group by."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-02 00:00", periods=days * 1440, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, len(index)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, len(index))),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 0.5, len(index))),
            "close": close,
            "volume": rng.integers(1, 500, len(index)).astype(float),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return session_bars()


CASES = [
    (archetypes.DEADCATBOUNCE, DeadCatParams(bars_required_to_trade=200)),
    (
        archetypes.DEADCATBOUNCE,
        DeadCatParams(bars_required_to_trade=200, commission_per_contract=1.24, slippage_ticks=1.0),
    ),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(bars_required_to_trade=200)),
]


def both_summaries(bars, archetype, params, instrument=NQ):
    """The same combination down both paths."""
    data = sweep.prepare_for(bars, sweep.Grid.of(params, archetype=archetype))
    legs = archetype.legs(data, params, instrument)
    frame = archetype.run(data, params, instrument)

    return stats.summarise(frame), stats.summarise_legs(legs, data.day_codes), legs


@pytest.mark.parametrize(("archetype", "params"), CASES, ids=lambda v: getattr(v, "name", ""))
def test_the_two_summary_paths_agree_exactly(bars, archetype, params) -> None:
    reference, fast, legs = both_summaries(bars, archetype, params)
    assert legs.count > 0, "fixture produced no trades; this would pass vacuously"
    assert dataclasses.asdict(fast) == dataclasses.asdict(reference)


def test_the_fixture_actually_exercises_multi_leg_trades(bars) -> None:
    """Otherwise every group is one row and the grouping is never tested."""
    reference, _, _ = both_summaries(bars, *CASES[0])
    assert reference.legs > reference.trades


def test_they_agree_on_a_combination_that_never_trades(bars) -> None:
    params = DeadCatParams(bars_required_to_trade=len(bars) + 1)
    reference, fast, legs = both_summaries(bars, archetypes.DEADCATBOUNCE, params)
    assert legs.count == 0
    assert dataclasses.asdict(fast) == dataclasses.asdict(stats.Summary.empty())
    assert dataclasses.asdict(fast) == dataclasses.asdict(reference)


def test_neither_path_will_compute_sharpe_without_times(bars) -> None:
    """``day_codes=None`` is the numpy spelling of a log with no ``exit_time`` column.

    Both used to annualise a **per-trade** ratio as though it were daily, and both now
    refuse. Agreeing about the refusal is the same invariant as agreeing about a number:
    two Sharpes with different denominators would sit in one results column (#81).
    """
    archetype, params = CASES[0]
    data = sweep.prepare_for(bars, sweep.Grid.of(params, archetype=archetype))
    undated = archetype.run(data, params, NQ, with_times=False)
    assert not undated.empty, "fixture produced no trades; this would pass vacuously"

    with pytest.raises(stats.MissingTimesError, match="exit_time"):
        stats.summarise(undated)
    with pytest.raises(stats.MissingTimesError, match="day codes"):
        stats.summarise_legs(archetype.legs(data, params, NQ), None)


# -- the grouping itself ------------------------------------------------------


def minute_index(bars: int) -> pd.DatetimeIndex:
    """An index long enough to carry the leg matrices below, all on one calendar day."""
    return pd.date_range("2024-01-02 00:00", periods=bars, freq="min", tz="UTC")


def leg_matrix(trade_ids, net_pnl, exit_bars=None) -> trades.LegMatrix:
    """A minimal but schema-valid leg matrix, for pinning the aggregation directly."""
    n = len(trade_ids)
    matrix = np.zeros((n, trades.N_COLUMNS))
    matrix[:, trades.C_TRADE_ID] = trade_ids
    matrix[:, trades.C_LEG] = 1
    matrix[:, trades.C_QUANTITY] = 1
    matrix[:, trades.C_DIRECTION] = trades.SHORT
    matrix[:, trades.C_EXIT_REASON] = trades.EXIT_TARGET
    matrix[:, trades.C_NET_PNL] = net_pnl
    matrix[:, trades.C_EXIT_BAR] = np.arange(n) if exit_bars is None else exit_bars

    return trades.validate_legs(trades.LegMatrix(matrix, n))


CANCELLING = [1e16, 1.0, 1.0, -1e16]
"""Four leg P&Ls whose total depends on how the summation is done.

Added left to right they come to 0.0, because the two ones fall off the end of a float64
beside 1e16. A Kahan-compensated sum, which is what pandas' ``groupby`` uses, returns 2.0.
"""


def test_a_running_sum_would_not_reproduce_pandas() -> None:
    """The premise of the next test: these two summations genuinely differ."""
    running = 0.0
    for value in CANCELLING:
        running += value
    assert running == 0.0
    assert pd.Series(CANCELLING).groupby([1, 1, 1, 1]).sum().iloc[0] == 2.0


def test_the_grouped_sum_is_compensated_like_pandas() -> None:
    """Guards the Kahan loop in ``_grouped_sum`` against being "simplified" away."""
    legs = leg_matrix([1, 1, 1, 1], CANCELLING)
    index = minute_index(legs.count)
    assert stats.summarise_legs(legs, context.day_codes(index)).net_pnl == 2.0

    frame = trades.trades_to_frame(matrix=legs.matrix, count=legs.count, index=index, instrument="NQ")
    assert stats.summarise(frame).net_pnl == 2.0


def test_legs_written_out_of_trade_order_are_refused() -> None:
    """``groupby`` sorts by key; a boundary scan only reproduces that on sorted keys.

    The simulation cannot emit them out of order -- a trade has to close before the next
    one opens -- so this guards a future producer rather than a live branch.
    """
    legs = leg_matrix([1, 2, 1], [1.0, 2.0, 3.0])
    with pytest.raises(stats.GroupingError, match="non-decreasing"):
        stats.summarise_legs(legs, context.day_codes(minute_index(legs.count)))


def test_trades_are_grouped_by_the_day_they_closed_on() -> None:
    """Sharpe's denominator is days, so which day a trade lands on has to be its exit's."""
    index = pd.date_range("2024-01-02 00:00", periods=3 * 1440, freq="min", tz="UTC")
    codes = context.day_codes(index)
    legs = leg_matrix([1, 2, 3], [10.0, -4.0, 7.0], exit_bars=[10, 20, 1500])

    fast = stats.summarise_legs(legs, codes)
    frame = trades.trades_to_frame(matrix=legs.matrix, count=legs.count, index=index, instrument="NQ")
    assert frame["exit_time"].dt.date.nunique() == 2, "fixture must straddle a day boundary"
    assert dataclasses.asdict(fast) == dataclasses.asdict(stats.summarise(frame))


# -- day codes ----------------------------------------------------------------


@pytest.mark.parametrize("tz", ["UTC", "Europe/London", "America/New_York"])
def test_day_codes_are_the_dates_pandas_would_group_by(tz) -> None:
    """In the index's own timezone, because ``DatetimeIndex.date`` is local.

    Reading them off UTC instead is invisible on a UTC index and an hour out for half the
    year on a London one, which is the shape of the bug ``tools/reconcile_nt8.py`` records.
    """
    index = pd.date_range("2024-06-01 21:00", periods=600, freq="min", tz="UTC").tz_convert(tz)
    codes = context.day_codes(index)
    dates = np.asarray(index.date)
    assert np.flatnonzero(np.diff(codes)).tolist() == np.flatnonzero(dates[1:] != dates[:-1]).tolist()
    assert len(set(codes)) == len(set(dates))


def test_a_frame_without_a_datetime_index_has_no_day_codes() -> None:
    frame = pd.DataFrame({"a": [1, 2]}, index=[0, 1])
    assert context.day_codes(frame.index) is None
