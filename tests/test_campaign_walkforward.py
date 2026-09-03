"""Putting a campaign shortlist through several folds instead of one hand-cut split.

Three things can go wrong quietly here and each has its own section below. The fold geometry is
stated in shares because a bar count means a different amount of time at each resolution. The
warm-up has to cover the longest lookback the *shortlist's own* context declares, or every fold
measures its own cold start. And the candidate pool has to be the listed configurations rather
than a cross of their values -- twenty rows crossed would be thousands of combinations, and the
run would still look like it worked.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, higher_timeframe, sessions, trend, walkforward
from nqbt.conditions import ma_keys
from tools import campaign_walkforward
from tools.campaign_walkforward import candidate_grid, geometry, main, run_resolution, warmup_for

ROOT = "MNQ"
STRATEGY = "InsideBar"


# -- the fold geometry ---------------------------------------------------------------------


def test_the_shares_become_bar_counts_of_the_series_they_are_taken_from() -> None:
    """Stated as shares rather than bars because 20,000 bars is four months at 5 minutes and
    a year at 15, so one pair of counts cannot serve both resolutions."""
    assert geometry(1000, 0.5, 0.1) == (500, 100)
    assert geometry(113_814, 0.5, 0.1) == (56_907, 11_381)


def test_the_default_shares_leave_the_last_half_of_the_series_to_test_on() -> None:
    """Which is what makes five folds rather than a number that moves with the resolution."""
    train_bars, test_bars = geometry(1000, 0.5, 0.1)
    assert len(walkforward.splits(1000, train_bars=train_bars, test_bars=test_bars)) == 5


def test_a_share_that_rounds_down_to_no_bars_raises_rather_than_running_one() -> None:
    with pytest.raises(RuntimeError, match="window of no bars"):
        geometry(50, 0.5, 0.001)


# -- the warm-up ---------------------------------------------------------------------------


def test_the_warm_up_is_the_longest_lookback_the_context_declares() -> None:
    """Every fold is prepared independently, so a shorter prefix leaves the longest average
    reading its own warm-up for the first bars of every window."""
    spec = context.ContextSpec(ma_keys=ma_keys(ema=(11, 44), sma=(200,)), atr_periods=(14,))
    assert warmup_for(spec, 5) == 200


def test_a_coarse_average_is_counted_in_bars_of_the_series_it_is_stamped_onto() -> None:
    """A 20-period average of 60-minute bars is 240 ten-minute bars of history, not 20."""
    spec = context.ContextSpec(
        higher_timeframe_keys=(higher_timeframe.HigherTimeframeKey(minutes=60, period=20),),
    )
    assert warmup_for(spec, 10) == 120
    assert warmup_for(spec, 5) == 240


def test_a_trend_label_warms_over_its_longest_of_three_periods() -> None:
    spec = context.ContextSpec(
        trend_keys=(trend.TrendKey(fast_period=20, slow_period=50, slope_lookback=5),),
    )
    assert warmup_for(spec, 5) == 50


def test_a_context_declaring_no_lookback_at_all_needs_no_prefix() -> None:
    assert warmup_for(context.ContextSpec(), 5) == 0


# -- the candidate pool --------------------------------------------------------------------


def stored_rows(**columns: object) -> pd.DataFrame:
    """Two shortlisted InsideBar rows, as the campaign databases store them."""
    base = {
        "ema_period": [11, 44],
        "fast_sma_period": [20, 50],
        "slow_sma_period": [60, 60],
        "bars_required_to_trade": [60, 60],
        "atr_multiplier": [1.0, 2.0],
    }

    return pd.DataFrame({**base, **columns})


def test_the_pool_is_the_rows_themselves_and_never_a_cross_of_their_values() -> None:
    """The whole reason the grid takes combinations outright: crossing two rows of five
    parameters is not two candidates, and the fold would still report a clean number."""
    grid = candidate_grid(stored_rows(), archetypes.INSIDEBAR)
    assert len(grid) == 2
    assert [(c.ema_period, c.fast_sma_period) for c in grid.combinations()] == [(11, 20), (44, 50)]


def test_the_pool_carries_every_stored_parameter_rather_than_the_ranked_ones_alone() -> None:
    """``rebuild`` fills from defaults, so a column the sweep stored and the pool dropped would
    walk a configuration forward that the campaign never ranked."""
    grid = candidate_grid(stored_rows(), archetypes.INSIDEBAR)
    assert [c.atr_multiplier for c in grid.combinations()] == [1.0, 2.0]
    assert {c.slow_sma_period for c in grid.combinations()} == {60}


def test_the_pool_declares_the_context_of_every_member() -> None:
    spec = candidate_grid(stored_rows(), archetypes.INSIDEBAR).required_context()
    periods = {period for _, period in spec.ma_keys}
    assert {11, 44, 20, 50, 60} <= periods


# -- the run -------------------------------------------------------------------------------


def synthetic_bars(n: int = 40_000, seed: int = 7) -> pd.DataFrame:
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


def options(**overrides: object) -> argparse.Namespace:
    settings = {
        "by": "profit_factor",
        "train_share": 0.5,
        "test_share": 0.1,
        "anchored": False,
        "warmup_bars": None,
        "min_trades": 1,
        "n_jobs": 1,
    }

    return argparse.Namespace(**{**settings, **overrides})


@pytest.fixture(scope="module")
def verdict() -> dict[str, object]:
    """One real walk-forward over a two-row shortlist. Costed, because ``walk_forward``
    refuses a free one -- reaching a verdict at all is what says the tool passed costs in."""
    return run_resolution(STRATEGY, stored_rows(), ROOT, 5, synthetic_bars(), options())


def test_a_shortlist_walks_forward_and_reports_one_verdict_row(verdict) -> None:
    assert verdict["strategy"] == STRATEGY
    assert verdict["resolution"] == 5
    assert verdict["candidates"] == 2
    assert verdict["splits"] == 5
    assert verdict["statistic"] == "profit_factor"


def test_every_fold_chooses_from_the_pool_and_never_from_outside_it(verdict) -> None:
    """``combo_id`` is a position in the candidate list, so anything past its end would be a
    configuration nobody shortlisted, reported under a shortlisted row's name."""
    assert verdict["splits_selected"] == verdict["splits"], "no fold selected; the test proves nothing"
    assert 1 <= verdict["combos_distinct"] <= verdict["candidates"]


def test_the_verdict_is_the_pooled_out_of_sample_figure_and_not_a_median_of_medians(verdict) -> None:
    """``test_pooled`` is taken over every out-of-sample trade at once, which is why the
    windows have to tile the tested region -- ``docs/roadmap.md`` §M7b."""
    assert np.isfinite(verdict["test_pooled"])
    assert verdict["test_trades"] > 0
    assert verdict["passes"] == (verdict["test_pooled"] > 1.0)


# -- the run over a whole shortlist --------------------------------------------------------


def test_a_shortlist_spanning_resolutions_walks_each_one_forward_on_its_own(monkeypatch) -> None:
    """Two candidates at different bar sizes are different frames and cannot be selected
    between, so pooling them would rank a 5-minute profit factor against a 10-minute one."""
    rows = pd.concat([stored_rows(resolution=[5, 5]), stored_rows(resolution=[10, 10])])
    monkeypatch.setattr(campaign_walkforward, "shortlist", lambda *_: rows)
    monkeypatch.setattr(campaign_walkforward.splice, "load_continuous", lambda _: synthetic_bars())

    ran: list[int] = []
    walked = campaign_walkforward.run_resolution

    def spy(name, block, root, minutes, bars, args):
        ran.append(minutes)

        return walked(name, block, root, minutes, bars, args)

    monkeypatch.setattr(campaign_walkforward, "run_resolution", spy)
    argv = ["campaign_walkforward.py", "--strategy", STRATEGY, "--min-trades", "1", "--n-jobs", "1"]
    assert main(argv) == 0
    assert ran == [5, 10]
