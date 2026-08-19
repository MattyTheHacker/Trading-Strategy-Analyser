"""PullBackAndGo simulation tests on hand-built bars.

The shared bracket engine (entry_bracket, _resolve_brackets, _limit_filled, _write) is
already exercised thoroughly by test_deadcat_sim.py and pinned bidirectional by M15.1's
mirrored long-side test. What is specific to this archetype and needs its own coverage is
the handful of places PullBackAndGo.cs genuinely differs from DeadCatBounce.cs rather than
merely mirroring it -- see nqbt.sim.types.PullBackAndGoParams for the full list -- plus
the entry-condition wiring (nqbt.sim.pullback.pullback_signal), which is new code.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import context, sessions
from nqbt.instruments import MNQ
from nqbt.sim import bracket, deadcat
from nqbt.sim.pullback import pullback_signal, run_pullbackandgo
from nqbt.sim.types import PullBackAndGoParams
from nqbt.trades import LONG

TICK = 0.25


def run(
    rows,
    signal_at=(),
    *,
    force_flat_at=(),
    quantities=(1, 1, 1, 1),
    targets=(1.0, 1.5, 2.0, np.nan),
    slippage=0.0,
    commission=0.0,
    instrument=MNQ,
    bars_required=0,
    ratchet_lag=1,  # PullBackAndGo.cs ratchets off Low[1]
    fill_limit_on_touch=True,
    ambiguity_policy=0,
    round_targets=False,  # engine default here; PullBackAndGoParams ships True (M15.5)
):
    """Simulate hand-written OHLC rows with PullBackAndGo's defaults."""
    arr = np.asarray(rows, dtype=np.float64)
    o, h, l, c = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    n = len(arr)

    signal = np.zeros(n, dtype=np.bool_)
    for i in signal_at:
        signal[i] = True
    force_flat = np.zeros(n, dtype=np.bool_)
    for i in force_flat_at:
        force_flat[i] = True

    out = bracket.allocate_output(max(int(signal.sum()), 1), len(quantities))
    count = deadcat.simulate_deadcat(
        o,
        h,
        l,
        c,
        signal,
        force_flat,
        np.asarray(quantities, dtype=np.int64),
        np.asarray(targets, dtype=np.float64),
        TICK,
        instrument.point_value,
        2.0,  # stop_offset_ticks: Low[0] - 2 ticks
        0.0,  # entry_offset_ticks: no close-based cap, trigger is bare High[0]
        1.0,  # tp_multiplier: no property on PullBackAndGo.cs
        1e9,  # max_risk_ticks: no cap on PullBackAndGo.cs
        commission,
        slippage,
        bars_required,
        0.0,  # min_reward_risk: no property on PullBackAndGo.cs
        ratchet_lag,
        0.0,  # ratchet_offset_ticks: bare Low[1], no offset reapplied
        True,
        fill_limit_on_touch,
        ambiguity_policy,
        LONG,
        round_targets,
        out,
    )
    assert count >= 0, "trade buffer overflowed"

    from nqbt import trades as trades_mod

    return trades_mod.validate(trades_mod.trades_to_frame(out, count, instrument=instrument.symbol))


# -- entry mechanics: bare High[0], no close-based cap -------------------------


def test_signal_places_a_buy_stop_at_the_bare_high() -> None:
    # Signal bar: high 101.5, low 97 -> trigger 101.5 (no close-based cap), stop 96.5.
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal
            (101, 101.5, 100, 101),  # 1: touches 101.5 -> fill at trigger
        ],
        signal_at=[0],
    )
    assert trades["entry_bar"].nunique() == 1
    assert trades["entry_price"].iloc[0] == pytest.approx(101.5)
    assert trades["initial_stop"].iloc[0] == pytest.approx(96.5)
    assert trades["risk_points"].iloc[0] == pytest.approx(5.0)


def test_gap_up_through_the_trigger_fills_at_the_open() -> None:
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal, trigger 101.5
            (103, 104, 102, 103),  # 1: opens above the trigger
        ],
        signal_at=[0],
    )
    assert trades["entry_price"].iloc[0] == pytest.approx(103.0)


def test_unfilled_order_is_cancelled_after_one_bar() -> None:
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal, trigger 101.5
            (100, 101, 99, 100),  # 1: never reaches 101.5 -> cancelled
            (101, 102, 100, 101.5),  # 2: would have filled a resting order
        ],
        signal_at=[0],
    )
    assert trades.empty


def test_a_resting_order_is_cancelled_rather_than_filled_at_the_flatten_point() -> None:
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal, trigger 101.5
            (103, 104, 102, 103),  # 1: force-flat; would gap through the trigger
        ],
        signal_at=[0],
        force_flat_at=[1],
    )
    assert trades.empty


# -- the ratchet: bare Low[1], not High[0] + offset -----------------------------


def test_ratchet_tightens_immediately_on_the_entry_bar_because_the_offsets_differ() -> None:
    # Entry stop is Low[0] - 2 ticks = 96.5 (entry_bracket uses stop_offset_ticks). But
    # ratchet_lag=1 means the ratchet evaluates at ref = entry_bar - 1 = the signal bar
    # itself on the very bar the fill happens, reading Low[0] with *no* offset -- 97, not
    # 96.5. Since 97 is tighter it applies immediately, before any bar has even closed
    # with the position open. DeadCatBounce never shows this because its ratchet and entry
    # share one offset, so the two formulas coincide exactly on the signal bar.
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal, trigger 101.5, entry-stop 96.5
            (101, 101.5, 100, 101),  # 1: fill at 101.5; ratchet(ref=0) -> Low[0] = 97
            (98, 99, 97, 98),  # 2: low touches 97, not 96.5
        ],
        signal_at=[0],
    )
    assert set(trades["exit_reason"]) == {"stop"}
    assert trades["exit_price"].unique() == pytest.approx([97.0])
    assert trades["initial_stop"].unique() == pytest.approx([96.5])  # the plan, unchanged


def test_ratchet_keeps_tracking_the_bare_low_one_bar_back_and_never_loosens() -> None:
    trades = run(
        [
            (100, 101.5, 97, 101),  # 0: signal, trigger 101.5, entry-stop 96.5
            (101, 101.5, 100, 101),  # 1: fill; ratchet(ref=0) -> Low[0] = 97
            (100, 101, 98.5, 100),  # 2: no touch; ratchet(ref=1) -> Low[1] = 100
            (100.5, 101, 100.2, 100.8),  # 3: no touch; ratchet(ref=2) candidate Low[2] =
            #    98.5 is looser than 100, so it is ignored
            (100, 100.5, 99, 99.5),  # 4: low 99 trades through the still-100 stop
        ],
        signal_at=[0],
    )
    assert set(trades["exit_reason"]) == {"stop"}
    # 100.0 exactly -- not 98.5 (which a naive "always take the latest" ratchet would
    # loosen to) and not 100 + 2 ticks (which DeadCatBounce's own offset would give).
    assert trades["exit_price"].unique() == pytest.approx([100.0])
    assert trades["exit_bar"].unique() == [4]


# -- targets are not rounded to the tick grid -----------------------------------


def test_targets_are_left_unrounded() -> None:
    # An engine test for the round_targets flag, not a claim about the archetype: the
    # M15.5 reconciliation showed NT8 snaps PullBackAndGo's targets even though the C#
    # never calls RoundToTickSize, so PullBackAndGoParams now defaults it to True. What
    # this pins is that the flag is what does the rounding and nothing else does.
    #
    # Trigger 104.25 (bare High[0]), stop 99.5 (Low[0] - 2 ticks), risk 4.75. Leg 2's
    # target is 104.25 + 4.75*1.5 = 111.375 -- a genuine half tick on the 0.25 grid.
    trades = run(
        [
            (100, 104.25, 100, 101),  # 0: signal, trigger 104.25, stop 99.5, risk 4.75
            (101, 104.25, 100, 101),  # 1: fill at 104.25; ratchet(ref=0) -> stop = Low[0] = 100
            (101, 118, 100.5, 117),  # 2: low 100.5 clears the 100 stop; high reaches every
            #    target cleanly, not as an ambiguous stop-touch bar
        ],
        signal_at=[0],
    )
    assert list(trades.sort_values("leg")["exit_reason"])[:3] == ["target"] * 3
    targets = trades.set_index("leg")["target_price"].dropna()
    assert targets.loc[1] == pytest.approx(104.25 + 4.75 * 1.0)
    assert targets.loc[2] == pytest.approx(104.25 + 4.75 * 1.5)
    assert targets.loc[3] == pytest.approx(104.25 + 4.75 * 2.0)
    # Confirm leg 2 is genuinely off the tick grid, so the test has teeth.
    off_grid = targets.loc[2] / TICK - round(targets.loc[2] / TICK)
    assert abs(off_grid) > 1e-9


def test_round_targets_true_would_have_snapped_the_same_bars() -> None:
    # Same bars as above with round_targets=True (DeadCatBounce's setting) confirm the
    # flag is what makes the difference, not something else about this scenario.
    trades = run(
        [
            (100, 104.25, 100, 101),
            (101, 104.25, 100, 101),
            (101, 118, 100.5, 117),
        ],
        signal_at=[0],
        round_targets=True,
    )
    leg2 = trades.set_index("leg").loc[2, "target_price"]
    on_grid = leg2 / TICK - round(leg2 / TICK)
    assert abs(on_grid) < 1e-9


# -- entry conditions: hammer, new low, previous red, above every MA -----------


def synthetic_bars(n: int = 4000, seed: int = 11) -> pd.DataFrame:
    """Random-walk minute bars, matching test_explain.py's pattern for a live sweep."""
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


def test_pullback_signal_and_run_wire_together_end_to_end() -> None:
    params = PullBackAndGoParams(bars_required_to_trade=200)
    bars = synthetic_bars()
    data = context.prepare(
        bars,
        context.ContextSpec(
            ema_periods=(params.ema_period,),
            sma_periods=(params.fast_sma_period, params.slow_sma_period),
            needs_vwap=True,
        ),
    )
    signal = pullback_signal(data, params)
    assert signal.dtype == np.bool_
    assert signal.size == len(bars)

    log = run_pullbackandgo(data, params, MNQ)
    assert not log.empty, "fixture produced no trades; the test below would prove nothing"
    assert (log["direction"] == LONG).all()
    assert (log["quantity"] == 1).all()
    # A long's stop sits below its entry, the opposite of DeadCatBounce.
    assert (log["initial_stop"] < log["entry_price"]).all()


def test_every_entry_condition_actually_binds() -> None:
    # Guards the test above from passing vacuously if one condition never mattered.
    params = PullBackAndGoParams(bars_required_to_trade=200)
    data = context.prepare(
        synthetic_bars(),
        context.ContextSpec(
            ema_periods=(params.ema_period,),
            sma_periods=(params.fast_sma_period, params.slow_sma_period),
            needs_vwap=True,
        ),
    )
    anchor = data.geometry.hammer
    full = pullback_signal(data, params)
    assert full.sum() < anchor.sum(), "no filter narrowed the raw hammer count"
    assert full.sum() > 0


# -- params -----------------------------------------------------------------


def test_leg_quantities_split_the_order_with_the_remainder_last() -> None:
    # OrderQuantity now exists on the C#, split baseQuantity = qty / 4 with the remainder
    # added to L4 -- identical to DeadCatBounce, so 10 goes 2/2/2/4 and not 3/3/2/2.
    assert PullBackAndGoParams().leg_quantities == (1, 1, 1, 1)
    assert PullBackAndGoParams(order_quantity=10).leg_quantities == (2, 2, 2, 4)
    three_legs = PullBackAndGoParams(order_quantity=3, target_r_multiples=(1.0, 2.0, float("nan")))
    assert three_legs.leg_quantities == (1, 1, 1)


def test_params_reject_an_order_quantity_that_cannot_fill_every_leg() -> None:
    with pytest.raises(ValueError, match="cannot fill"):
        PullBackAndGoParams(order_quantity=3)


def test_default_filters_are_the_reconciled_configuration() -> None:
    # The C# leaves all six uninitialised in SetDefaults, so there is no NinjaScript
    # default to mirror. These reproduce the M15.5 reconciliation, the only combination
    # with a trade list behind it; VWAP is off because nqbt's has never been checked
    # against OrderFlowVWAP. See docs/nt8-fidelity.md.
    p = PullBackAndGoParams()
    assert (p.use_ema, p.use_slow_sma, p.use_fast_sma, p.use_vwap) == (
        True,
        True,
        True,
        False,
    )
    assert (p.require_previous_red, p.require_new_low) == (True, True)


def test_every_filter_can_be_switched_off_independently() -> None:
    # Each filter is its own early-return `if` in the C#, so switching one off must relax
    # that condition and leave every other one exactly as it was. Asserting the defaults
    # is not enough: it never runs the branches.
    data = context.prepare(
        synthetic_bars(),
        context.ContextSpec(
            ema_periods=(21,),
            sma_periods=(60, 175),
            needs_vwap=True,
        ),
    )
    # With every optional filter off the signal is the bare hammer and nothing else.
    all_off = PullBackAndGoParams(
        bars_required_to_trade=200,
        use_ema=False,
        use_slow_sma=False,
        use_fast_sma=False,
        use_vwap=False,
        require_previous_red=False,
        require_new_low=False,
    )
    bare = pullback_signal(data, all_off)
    assert (bare == data.geometry.hammer).all()
    assert bare.sum() > 0

    # Each filter is then measured against that anchor rather than against the full
    # conjunction, which on this many bars leaves too few signals to tell anything apart.
    for field in (
        "require_new_low",
        "require_previous_red",
        "use_ema",
        "use_fast_sma",
        "use_slow_sma",
        "use_vwap",
    ):
        only = pullback_signal(data, replace(all_off, **{field: True}))
        assert only.sum() < bare.sum(), f"{field} never bound, so its branch is untested"
        assert not (only & ~bare).any(), f"{field} admitted a signal that is not a hammer"

    # And the reconciled default set is a subset of the anchor, narrower than any of them.
    full = pullback_signal(data, PullBackAndGoParams(bars_required_to_trade=200))
    assert 0 < full.sum() < bare.sum()
    assert not (full & ~bare).any()


def test_params_reject_a_non_positive_period() -> None:
    with pytest.raises(ValueError, match="must be >= 1"):
        PullBackAndGoParams(ema_period=0)
