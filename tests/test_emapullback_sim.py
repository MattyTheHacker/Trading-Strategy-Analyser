"""EmaPullback simulation tests on hand-built bars.

The archetype has no NinjaScript, so there is no trade list to check against. What these pin
instead are the rules it introduces -- the extension that has to precede the touch, the three
touch modes and their shared boundary, and a stop placed on the slow average rather than at a
distance -- plus the property the whole thing is worthless without: that nothing it reads comes
from a bar it could not have seen.

The signal functions take the two averages as arguments, so the tests hand them flat synthetic
values and keep the arithmetic checkable by eye. The end-to-end tests use the real grids.
"""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, regime, sessions, sweep, trend
from nqbt.instruments import MNQ, NQ
from nqbt.sim import crossover, emapullback
from nqbt.sim.emapullback import (
    emapullback_signal,
    extension_run,
    pullback_averages,
    run_emapullback,
    side_signal,
    trailed_level,
)
from nqbt.sim.types import TOUCH_ANY, TOUCH_CLOSE, TOUCH_WICK, EmaPullbackParams
from nqbt.trades import LONG, SHORT

FAST = 100.0
SLOW = 95.0
"""Flat stand-ins for the two averages, so a bar's relation to each is readable in the row."""

UPTREND = [
    (102.0, 103.0, 101.0, 102.0),  # 0: entirely above the fast average
    (102.0, 103.0, 101.0, 102.0),  # 1
    (102.0, 103.0, 101.0, 102.0),  # 2
    (102.0, 103.0, 99.0, 102.0),  # 3: reaches the fast average, closes back above it
    (102.0, 103.0, 101.0, 102.0),  # 4: one bar of extension, not three
    (102.0, 103.0, 99.0, 102.0),  # 5: reaches it again
]

DEFAULTS = {"bars_required_to_trade": 0, "min_bars_extended": 3}


def params(**overrides) -> EmaPullbackParams:
    return EmaPullbackParams(**(DEFAULTS | overrides))


def frame(rows) -> pd.DataFrame:
    """A bar frame from hand-written OHLC rows."""
    arr = np.asarray(rows, dtype=np.float64)
    idx = pd.date_range("2024-01-02 00:00", periods=len(arr), freq="min", tz="UTC")
    out = pd.DataFrame(
        {
            "open": arr[:, 0],
            "high": arr[:, 1],
            "low": arr[:, 2],
            "close": arr[:, 3],
            "volume": np.full(len(arr), 100.0),
        },
        index=idx,
    )
    out["trading_day"] = sessions.classify(idx).trading_day

    return out


def dataset(rows, combination: EmaPullbackParams):
    return sweep.prepare_for(frame(rows), sweep.Grid.of(combination, archetype=archetypes.EMAPULLBACK))


def flat(value: float, n: int):
    return np.full(n, value, dtype=np.float64)


def signal_for(rows, combination: EmaPullbackParams, *, fast=FAST, slow=SLOW, direction=LONG):
    """One side's signal over ``rows``, with both averages held flat at stated values."""
    data = dataset(rows, combination)

    return side_signal(data, flat(fast, len(rows)), flat(slow, len(rows)), combination, direction)


def mirrored(rows, pivot: float = 200.0):
    """The same bars reflected about ``pivot`` -- an uptrend's rows become a downtrend's."""
    return [(pivot - o, pivot - low, pivot - high, pivot - c) for o, high, low, c in rows]


# -- the extension that has to precede the touch -------------------------------


def test_a_touch_signals_once_the_extension_behind_it_is_long_enough() -> None:
    signal = signal_for(UPTREND, params(min_bars_extended=3))
    assert list(np.flatnonzero(signal)) == [3]


def test_a_shorter_extension_than_the_rule_asks_for_signals_nothing() -> None:
    assert not signal_for(UPTREND, params(min_bars_extended=4)).any()


def test_the_touch_bar_ends_the_run_so_the_next_touch_counts_from_scratch() -> None:
    """Bar 5 has one bar of extension behind it, not four: bar 3 reached the average."""
    assert list(np.flatnonzero(signal_for(UPTREND, params(min_bars_extended=1)))) == [3, 5]
    assert list(np.flatnonzero(signal_for(UPTREND, params(min_bars_extended=2)))) == [3]


def test_the_run_a_bar_reads_is_the_one_the_bar_before_it_carried() -> None:
    lows = np.array([101.0, 101.0, 101.0, 99.0, 101.0], dtype=np.float64)
    run = extension_run(lows, flat(FAST, 5), flat(SLOW, 5), LONG)
    assert list(run) == [0, 1, 2, 3, 0]


def test_no_bar_is_extended_while_the_averages_are_the_wrong_way_round() -> None:
    """The trend gate is inside the run as well as beside it, so nothing arms at all."""
    assert not signal_for(UPTREND, params(min_bars_extended=1), fast=95.0, slow=100.0).any()


# -- how deep the pullback has to go -------------------------------------------


def test_a_bar_closing_through_the_fast_average_signals_under_the_deeper_modes_only() -> None:
    deep = [*UPTREND[:3], (102.0, 103.0, 99.0, 99.5)]
    assert not signal_for(deep, params(touch_mode=TOUCH_WICK)).any()
    assert signal_for(deep, params(touch_mode=TOUCH_CLOSE))[3]
    assert signal_for(deep, params(touch_mode=TOUCH_ANY))[3]


def test_a_bar_closing_back_beyond_the_fast_average_signals_under_the_shallow_modes_only() -> None:
    assert signal_for(UPTREND, params(touch_mode=TOUCH_WICK))[3]
    assert not signal_for(UPTREND, params(touch_mode=TOUCH_CLOSE)).any()
    assert signal_for(UPTREND, params(touch_mode=TOUCH_ANY))[3]


def test_a_close_exactly_on_the_fast_average_is_a_close_through_it() -> None:
    """The boundary both arms have to share: one sign multiplier, one rule."""
    touching = [*UPTREND[:3], (102.0, 103.0, 99.0, FAST)]
    assert not signal_for(touching, params(touch_mode=TOUCH_WICK)).any()
    assert signal_for(touching, params(touch_mode=TOUCH_CLOSE))[3]


def test_a_bar_that_never_reaches_the_fast_average_signals_under_no_mode() -> None:
    away = [*UPTREND[:3], (102.0, 103.0, 100.25, 102.0)]
    for mode in (TOUCH_WICK, TOUCH_CLOSE, TOUCH_ANY):
        assert not signal_for(away, params(touch_mode=mode)).any(), mode


# -- the reaction the pullback literature asks for -----------------------------


def test_the_turn_requirement_asks_the_signal_bars_own_body_to_have_turned() -> None:
    green = [*UPTREND[:3], (101.0, 103.0, 99.0, 102.0)]
    red = [*UPTREND[:3], (103.0, 103.5, 99.0, 102.0)]
    assert signal_for(green, params(require_turn=True))[3]
    assert not signal_for(red, params(require_turn=True)).any()
    assert signal_for(red, params(require_turn=False))[3]


def test_a_doji_signal_bar_passes_the_turn_requirement_on_neither_side() -> None:
    """The boundary one sign multiplier asks for -- not the ported archetypes' green/red pair."""
    doji = [*UPTREND[:3], (102.0, 103.0, 99.0, 102.0)]
    assert not signal_for(doji, params(require_turn=True)).any()
    assert not signal_for(
        mirrored(doji),
        params(require_turn=True),
        slow=200.0 - SLOW,
        direction=SHORT,
    ).any()


def test_the_turn_requirement_only_ever_narrows_the_signal() -> None:
    loose = EmaPullbackParams(bars_required_to_trade=50, touch_mode=TOUCH_ANY)
    strict = replace(loose, require_turn=True)
    data = walk_dataset(loose)
    wide = emapullback_signal(data, loose)
    narrow = emapullback_signal(data, strict)
    assert narrow.sum() < wide.sum()
    assert (narrow <= wide).all()


# -- the trend the stop is placed against --------------------------------------


def test_a_signal_bar_that_traded_through_the_slow_average_is_refused_while_asked_to_be() -> None:
    through = [*UPTREND[:3], (102.0, 103.0, 94.0, 102.0)]
    assert not signal_for(through, params(require_slow_intact=True)).any()
    assert signal_for(through, params(require_slow_intact=False))[3]


def test_a_bar_closing_beyond_the_slow_average_signals_however_the_requirement_is_set() -> None:
    """Not the same rule as the one above: the close is what the stop would be wrong about."""
    broken = [*UPTREND[:3], (102.0, 103.0, 94.0, 94.5)]
    assert not signal_for(broken, params(require_slow_intact=True)).any()
    assert not signal_for(broken, params(require_slow_intact=False)).any()


# -- the short side ------------------------------------------------------------


def test_the_short_side_is_the_long_side_reflected_about_a_price() -> None:
    """Reflection swaps every high with a low, so an equal answer is the mirror holding."""
    for mode in (TOUCH_WICK, TOUCH_CLOSE, TOUCH_ANY):
        combination = params(touch_mode=mode)
        long_side = signal_for(UPTREND, combination, direction=LONG)
        short_side = signal_for(
            mirrored(UPTREND),
            combination,
            fast=FAST,
            slow=200.0 - SLOW,
            direction=SHORT,
        )
        assert np.array_equal(long_side, short_side), mode


def test_switching_a_side_off_removes_exactly_that_side() -> None:
    both = EmaPullbackParams(bars_required_to_trade=50)
    data = walk_dataset(both)
    long_only = emapullback_signal(data, replace(both, trade_short=False))
    short_only = emapullback_signal(data, replace(both, trade_long=False))
    assert long_only.any()
    assert short_only.any()
    assert not (long_only & short_only).any()
    assert np.array_equal(emapullback_signal(data, both), long_only | short_only)


# -- the archetype end to end --------------------------------------------------


def walk_bars(n: int = 4000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    out = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    out["trading_day"] = sessions.classify(idx).trading_day

    return out


def walk_dataset(combination: EmaPullbackParams):
    grid = sweep.Grid.of(combination, archetype=archetypes.EMAPULLBACK)

    return sweep.prepare_for(walk_bars(), grid)


def test_the_archetype_trades_both_sides() -> None:
    combination = EmaPullbackParams(bars_required_to_trade=50)
    log = run_emapullback(walk_dataset(combination), combination, MNQ)
    assert set(log["direction"]) == {LONG, SHORT}


def test_every_stop_sits_on_the_slow_average_at_the_signal_bar_plus_the_offset() -> None:
    """The rule this archetype exists for, asserted on every trade rather than on one."""
    combination = EmaPullbackParams(bars_required_to_trade=50, stop_offset_ticks=2)
    data = walk_dataset(combination)
    log = run_emapullback(data, combination, MNQ)
    _, slow = pullback_averages(data, combination)
    first = log.groupby("trade_id").first()
    signal_bar = first["entry_bar"].to_numpy(dtype=np.int64) - 1
    direction = first["direction"].to_numpy(dtype=np.float64)
    expected = slow[signal_bar] - direction * 2 * MNQ.tick_size
    assert len(first)
    assert first["initial_stop"].to_numpy() == pytest.approx(expected)


def test_a_zero_offset_puts_the_stop_on_the_average_itself() -> None:
    combination = EmaPullbackParams(bars_required_to_trade=50, stop_offset_ticks=0)
    data = walk_dataset(combination)
    log = run_emapullback(data, combination, MNQ)
    _, slow = pullback_averages(data, combination)
    first = log.groupby("trade_id").first()
    signal_bar = first["entry_bar"].to_numpy(dtype=np.int64) - 1
    assert len(first)
    assert first["initial_stop"].to_numpy() == pytest.approx(slow[signal_bar])


def test_r_is_the_distance_from_the_fill_to_the_stop_on_the_slow_average() -> None:
    """R is structure-scaled here, so it varies trade by trade with the gap between averages."""
    combination = EmaPullbackParams(bars_required_to_trade=50)
    log = run_emapullback(walk_dataset(combination), combination, MNQ)
    first = log.groupby("trade_id").first()
    planned = first["direction"] * (first["entry_price"] - first["initial_stop"])
    assert first["risk_points"].to_numpy() == pytest.approx(planned.to_numpy())
    assert first["risk_points"].min() < first["risk_points"].max()


def test_nothing_the_signal_reads_comes_from_a_bar_it_could_not_have_seen() -> None:
    """Recompute over a prefix: every value must be what the full series already said.

    The test this archetype exists to make possible to fail. A pullback is easy to compute one
    bar early -- the extension run and the touch are one bar apart -- and the symptom is a
    profit factor above 1 rather than an exception.
    """
    combination = EmaPullbackParams(bars_required_to_trade=50, touch_mode=TOUCH_ANY)
    bars = walk_bars()
    grid = sweep.Grid.of(combination, archetype=archetypes.EMAPULLBACK)
    full = emapullback_signal(sweep.prepare_for(bars, grid), combination)
    for cut in (300, 700, 1000):
        prefix = emapullback_signal(sweep.prepare_for(bars.iloc[:cut], grid), combination)
        assert np.array_equal(prefix, full[:cut]), cut


def test_the_trend_flip_exit_is_off_by_default_and_produces_signal_exits_when_on() -> None:
    off = EmaPullbackParams(bars_required_to_trade=50)
    on = EmaPullbackParams(bars_required_to_trade=50, exit_on_trend_flip=True)
    data = walk_dataset(off)
    assert "signal" not in set(run_emapullback(data, off, MNQ)["exit_reason"])
    assert "signal" in set(run_emapullback(data, on, MNQ)["exit_reason"])


def test_the_nq_spec_scales_every_leg_by_ten() -> None:
    combination = EmaPullbackParams(bars_required_to_trade=50)
    data = walk_dataset(combination)
    mnq = run_emapullback(data, combination, MNQ)
    nq = run_emapullback(data, combination, NQ)
    assert len(mnq) == len(nq)
    assert list(nq["gross_pnl"]) == pytest.approx([v * 10 for v in mnq["gross_pnl"]])


def test_a_context_filter_narrows_the_signal_and_never_widens_it() -> None:
    unfiltered = EmaPullbackParams(bars_required_to_trade=50)
    filtered = EmaPullbackParams(
        bars_required_to_trade=50,
        regime_filter=regime.Regime.DIRECTIONAL.bit,
        trend_filter=trend.Trend.UP.bit,
    )
    wide = emapullback_signal(walk_dataset(unfiltered), unfiltered)
    narrow = emapullback_signal(walk_dataset(filtered), filtered)
    assert narrow.sum() < wide.sum()
    assert (narrow <= wide).all()


# -- the trail on the slow average ---------------------------------------------

# A long from bar 0's signal fills at bar 1's open of 100.0. The slow average is stated per bar,
# so the stop starts at 95.0 less two ticks and every trailed level is readable in the row.

TRAILED = [
    (100.0, 100.5, 99.5, 100.0),  # 0: signal
    (100.0, 100.5, 99.5, 100.0),  # 1: fill at 100.0, stop 94.5
    (100.0, 100.5, 99.5, 100.0),  # 2: the average has risen to 97.0 -> stop 96.5
    (100.0, 100.5, 96.8, 99.0),  # 3: short of 96.5
    (99.0, 99.5, 96.0, 97.0),  # 4: through 96.5, not through 94.5
    *[(97.0, 97.5, 96.9, 97.0)] * 3,
]

RISING = [95.0, 95.0, 97.0, 97.0, 97.0, 97.0, 97.0, 97.0]

type Row = tuple[float, float, float, float]


def trade_on_slow(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[Row],
    slow: list[float],
    *,
    direction: float = LONG,
    **overrides: object,
) -> pd.DataFrame:
    """One runner leg traded from a signal on bar 0, with the slow average stated per bar.

    The averages are substituted rather than computed, so the rule is read against levels the
    test chose; the fast one sits five points on the trend's side of the slow one.
    """
    slow_series = np.asarray(slow, dtype=np.float64)
    fast_series = slow_series + direction * 5.0
    monkeypatch.setattr(emapullback, "pullback_averages", lambda _data, _params: (fast_series, slow_series))
    combination = params(
        **{
            "trail_ma_stop": True,
            "trail_on_slow": True,
            "target_r_multiples": (float("nan"),),
            "order_quantity": 1,
            **overrides,
        },
    )
    signal = np.zeros(len(rows), dtype=np.bool_)
    signal[0] = True

    return run_emapullback(dataset(rows, combination), combination, MNQ, signal=signal)


def test_the_stop_follows_the_slow_average_and_exits_where_it_got_to(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bar 2's average sets a stop at 96.5 that bar 4 trades through; the fixed stop stays at 94.5."""
    trailed = trade_on_slow(monkeypatch, TRAILED, RISING)
    fixed = trade_on_slow(monkeypatch, TRAILED, RISING, trail_ma_stop=False)
    assert trailed["initial_stop"].tolist() == pytest.approx([94.5])
    assert trailed[["exit_reason", "exit_bar"]].to_numpy().tolist() == [["stop", 4]]
    assert trailed["exit_price"].tolist() == pytest.approx([96.5])
    assert "stop" not in set(fixed["exit_reason"])


def test_the_trail_on_the_short_side_is_the_long_side_reflected(monkeypatch: pytest.MonkeyPatch) -> None:
    """One sign multiplier, so the mirrored bars and average give the mirrored exit."""
    long_side = trade_on_slow(monkeypatch, TRAILED, RISING)
    short_side = trade_on_slow(
        monkeypatch,
        mirrored(TRAILED),
        [200.0 - level for level in RISING],
        direction=SHORT,
    )
    assert short_side[["exit_reason", "exit_bar"]].to_numpy().tolist() == [["stop", 4]]
    assert short_side["initial_stop"].tolist() == pytest.approx([200.0 - 94.5])
    assert short_side["exit_price"].tolist() == pytest.approx([200.0 - v for v in long_side["exit_price"]])


def test_an_average_that_retreats_leaves_the_stop_where_it_got_to(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ratchet: the average falling back does not take the stop back with it.

    Bar 3's average is below where the stop started, and bar 4 still exits at the level bar 2 set.
    """
    retreating = [95.0, 95.0, 97.0, 93.0, 93.0, 93.0, 93.0, 93.0]
    trades = trade_on_slow(monkeypatch, TRAILED, retreating)
    assert trades[["exit_reason", "exit_bar"]].to_numpy().tolist() == [["stop", 4]]
    assert trades["exit_price"].tolist() == pytest.approx([96.5])


def test_an_unmoved_average_leaves_the_stop_where_it_was_placed_whatever_the_trail_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trail reads the stop's own offset, so ``trail_offset_ticks`` cannot make it jump.

    Bar 2 trades to 94.8: through a trail at no offset on 95.0, short of the stop at 94.5.
    """
    rows = [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 94.8, 99.0),
        *[(99.0, 99.5, 98.5, 99.0)] * 3,
    ]
    flat_slow = [95.0] * len(rows)
    fixed = trade_on_slow(monkeypatch, rows, flat_slow, trail_ma_stop=False)
    assert "stop" not in set(fixed["exit_reason"])
    for offset in (0, 8):
        trailed = trade_on_slow(monkeypatch, rows, flat_slow, trail_offset_ticks=offset)
        pd.testing.assert_frame_equal(trailed, fixed)


def test_trailing_on_the_slow_average_is_the_third_grid_pointed_at_it() -> None:
    """One boolean for what took a pinned ``(kind, period, offset)`` triple, and nothing else."""
    tied = EmaPullbackParams(
        bars_required_to_trade=50,
        slow_kind="sma",
        slow_period=40,
        stop_offset_ticks=3,
        trail_ma_stop=True,
        trail_on_slow=True,
    )
    pinned = replace(tied, trail_on_slow=False, trail_ma_kind="sma", trail_ma_period=40, trail_offset_ticks=3)
    fixed = replace(tied, trail_ma_stop=False)
    data = sweep.prepare_for(
        walk_bars(),
        sweep.Grid.of_combinations([tied, pinned, fixed], archetype=archetypes.EMAPULLBACK),
    )
    trailed = run_emapullback(data, tied, MNQ)
    pd.testing.assert_frame_equal(trailed, run_emapullback(data, pinned, MNQ))
    assert not trailed.equals(run_emapullback(data, fixed, MNQ))


def test_the_slow_average_mode_does_nothing_while_the_trail_is_off() -> None:
    """It chooses which level the trail reads, so with nothing trailing there is nothing to choose."""
    fixed = EmaPullbackParams(bars_required_to_trade=50)
    data = walk_dataset(fixed)
    pd.testing.assert_frame_equal(
        run_emapullback(data, replace(fixed, trail_on_slow=True), MNQ),
        run_emapullback(data, fixed, MNQ),
    )


STOP_OFFSET = 3
TRAIL_OFFSET = 7


def test_the_trailed_level_is_the_series_and_offset_each_mode_names() -> None:
    """Off and on the third grid the trail keeps its own offset; on the slow average it takes the stop's."""
    combination = EmaPullbackParams(
        stop_offset_ticks=STOP_OFFSET,
        trail_offset_ticks=TRAIL_OFFSET,
        trail_ma_period=30,
    )
    data = walk_dataset(replace(combination, trail_ma_stop=True))
    _, slow = pullback_averages(data, combination)

    off_series, off_offset = trailed_level(data, slow, combination)
    grid_series, grid_offset = trailed_level(data, slow, replace(combination, trail_ma_stop=True))
    slow_series, slow_offset = trailed_level(
        data,
        slow,
        replace(combination, trail_ma_stop=True, trail_on_slow=True),
    )
    assert off_series is crossover.NO_TRAIL
    assert off_offset == TRAIL_OFFSET
    assert np.array_equal(grid_series, data.ma_values("ema", 30))
    assert grid_offset == TRAIL_OFFSET
    assert slow_series is slow
    assert slow_offset == STOP_OFFSET


# -- what the sweep has to build for it ----------------------------------------


def test_the_context_spec_asks_for_the_two_averages_their_values_and_no_atr() -> None:
    spec = archetypes.EMAPULLBACK.context_for(
        {"fast_kind": ["ema"], "fast_period": [9], "slow_kind": ["ema"], "slow_period": [21]},
    )
    assert spec.atr_periods == ()
    assert spec.needs_ma_values
    assert set(spec.ma_keys) == {conditions.ma_key("ema", 9), conditions.ma_key("ema", 21)}


def test_the_trail_grid_is_built_only_where_some_combination_trails_on_it() -> None:
    axes = {
        "fast_kind": ["ema"],
        "fast_period": [9],
        "slow_kind": ["ema"],
        "slow_period": [21],
        "trail_ma_kind": ["ema"],
        "trail_ma_period": [50],
    }
    off = archetypes.EMAPULLBACK.context_for({**axes, "trail_ma_stop": [False]})
    on = archetypes.EMAPULLBACK.context_for({**axes, "trail_ma_stop": [False, True]})
    assert conditions.ma_key("ema", 50) not in off.ma_keys
    assert conditions.ma_key("ema", 50) in on.ma_keys


def test_the_trail_axes_are_dead_while_the_trail_is_off() -> None:
    base = EmaPullbackParams(trail_ma_stop=False)
    with pytest.raises(sweep.SweepError, match="trail_ma_period"):
        sweep.Grid.of(base, trail_ma_period=[20, 50], archetype=archetypes.EMAPULLBACK)

    with pytest.raises(sweep.SweepError, match="trail_on_slow"):
        sweep.Grid.of(base, trail_on_slow=[False, True], archetype=archetypes.EMAPULLBACK)


@pytest.mark.parametrize("axis", ["trail_ma_kind", "trail_ma_period", "trail_offset_ticks"])
def test_the_third_grid_axes_are_dead_while_the_trail_is_on_the_slow_average(axis: str) -> None:
    """The mode leaves all three unread, and sweeping the mode itself brings them back."""
    values = {"trail_ma_kind": ["ema", "sma"], "trail_ma_period": [20, 50], "trail_offset_ticks": [2, 8]}
    on_slow = EmaPullbackParams(trail_ma_stop=True, trail_on_slow=True)
    with pytest.raises(sweep.SweepError, match=rf"{axis} \(inert while trail_on_slow is True\)"):
        sweep.Grid.of(on_slow, archetype=archetypes.EMAPULLBACK, **{axis: values[axis]})

    live = sweep.Grid.of(
        on_slow,
        archetype=archetypes.EMAPULLBACK,
        trail_on_slow=[False, True],
        **{axis: values[axis]},
    )
    assert live.dead_axes() == {}


def test_the_trail_grid_is_not_built_where_every_combination_trails_on_the_slow_average() -> None:
    """The slow average is already built, so a sweep trailing only on it pays for no third grid."""
    axes = {
        "fast_kind": ["ema"],
        "fast_period": [9],
        "slow_kind": ["ema"],
        "slow_period": [21],
        "trail_ma_kind": ["ema"],
        "trail_ma_period": [50],
        "trail_ma_stop": [True],
    }
    on_slow = archetypes.EMAPULLBACK.context_for({**axes, "trail_on_slow": [True]})
    mixed = archetypes.EMAPULLBACK.context_for({**axes, "trail_on_slow": [False, True]})
    assert set(on_slow.ma_keys) == {conditions.ma_key("ema", 9), conditions.ma_key("ema", 21)}
    assert conditions.ma_key("ema", 50) in mixed.ma_keys


# -- the parameter set ---------------------------------------------------------


def test_one_average_cannot_be_both() -> None:
    with pytest.raises(ValueError, match="never separates from itself"):
        EmaPullbackParams(fast_kind="ema", fast_period=21, slow_kind="ema", slow_period=21)


def test_an_extension_of_no_bars_is_refused() -> None:
    with pytest.raises(ValueError, match="min_bars_extended"):
        EmaPullbackParams(min_bars_extended=0)


def test_an_unknown_touch_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="touch_mode"):
        EmaPullbackParams(touch_mode=9)


def test_a_negative_stop_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="stop_offset_ticks"):
        EmaPullbackParams(stop_offset_ticks=-1)


def test_an_order_too_small_to_fill_its_legs_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot fill"):
        EmaPullbackParams(order_quantity=3)
