"""Tests for the ``nqbt run --explain`` audit trail.

The audit trail is the instrument a human uses to tick a trade off against a chart before
trusting anything downstream, so the property that matters is not that it produces
plausible numbers -- it is that it produces *the simulation's* numbers. It did not: it
recomputed the entry arithmetic independently and dropped the ``Close[0] - 2 ticks``
trigger cap, which binds on roughly half of all signals. It agreed on the stop, which is
what made it survive inspection.

These tests compare every trade rather than a sample, because the defect was a
disagreement on half the rows and any single row had even odds of looking fine.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import context, sessions
from nqbt.instruments import MNQ
from nqbt.sim import deadcat, explain
from nqbt.sim.runner import run_deadcat
from nqbt.sim.types import DeadCatParams
from nqbt.trades import SHORT


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Random-walk minute bars with wicks wide enough to throw inverted hammers."""
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
def audited():
    """A trade log and the audit trail over the whole of it, not a prefix."""
    params = DeadCatParams(bars_required_to_trade=200)
    data = context.prepare(
        synthetic_bars(),
        ema_periods=(params.ema_period,),
        sma_periods=(params.fast_sma_period, params.slow_sma_period),
        keep_ma_values=True,
    )
    log = run_deadcat(data, params, MNQ)
    assert len(log), "fixture produced no trades; the tests below would prove nothing"
    detail = explain.explain_trades(data, params, log, MNQ, limit=len(log))
    return log, detail


def test_the_audit_trail_reports_the_simulations_own_order_arithmetic(audited):
    """The regression test for the defect: it disagreed on 50% of trades.

    ``trigger`` is not a column of the trade log, but the log pins it exactly --
    ``risk_points`` is ``initial_stop - trigger`` by construction, so agreeing on both
    named columns is agreeing on the trigger too.
    """
    log, detail = audited
    first_leg = log.groupby("trade_id").first()
    joined = detail.set_index("trade_id").join(first_leg, rsuffix="_log")

    assert len(joined) == log["trade_id"].nunique()
    pd.testing.assert_series_equal(
        joined["initial_stop"], joined["initial_stop_log"], check_names=False
    )
    pd.testing.assert_series_equal(
        joined["risk_points"], joined["risk_points_log"], check_names=False
    )
    implied_trigger = joined["initial_stop"] - joined["risk_points"]
    assert np.allclose(joined["trigger"], implied_trigger, rtol=0, atol=0)


def test_the_capped_trigger_actually_binds_in_this_fixture(audited):
    """Guards the test above from passing vacuously.

    If the close-based cap never bound, the old ``trigger = Low[0]`` would agree with the
    simulation everywhere and the comparison would prove nothing. It has to bind on a
    substantial share of trades for that test to have teeth.
    """
    _, detail = audited
    capped = detail["trigger"] < detail["sig_low"]
    assert capped.mean() > 0.2, f"cap bound on only {capped.mean():.1%} of trades"


def test_fill_type_agrees_with_the_price_the_entry_actually_filled_at(audited):
    """``fill_type`` reads the trigger too, so it was wrong on the same rows."""
    log, detail = audited
    gapped = detail["fill_type"] == "gap_at_open"
    assert (detail.loc[gapped, "entry_price"] == detail.loc[gapped, "entry_open"]).all()
    touched = ~gapped
    assert (detail.loc[touched, "entry_price"] == detail.loc[touched, "trigger"]).all()


def test_entry_bracket_caps_the_trigger_at_two_ticks_below_the_close():
    """The helper's own rule, stated independently of the loop that calls it."""
    tick = 0.25
    # An inverted hammer: closes near its low, so the cap binds.
    trigger, stop, risk = entry = deadcat.entry_bracket(
        100.0, 99.0, 99.25, 2 * tick, 2 * tick, SHORT
    )
    assert trigger == pytest.approx(98.75)  # min(99.0, 99.25 - 0.5)
    assert stop == pytest.approx(100.5)
    assert risk == pytest.approx(stop - trigger)
    assert len(entry) == 3


def test_entry_bracket_leaves_the_low_alone_when_the_close_is_high():
    tick = 0.25
    trigger, stop, risk = deadcat.entry_bracket(100.0, 99.0, 99.9, 2 * tick, 2 * tick, SHORT)
    assert trigger == pytest.approx(99.0)  # min(99.0, 99.4) -- the low wins
    assert risk == pytest.approx(1.5)
