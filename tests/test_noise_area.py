"""The noise area: the band, the half-hour decisions, the trail and the cash-close exit.

The band is checked against a pandas reading of the same definition, and every exit against the
bar it was decided on -- ``docs/nt8-fidelity.md``, "The noise area".
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, noise, resample, sessions, sweep, timeofday, trades, volume
from nqbt.sim import elasticband
from nqbt.sim.types import (
    BAND_BOLLINGER,
    BAND_NOISE,
    BAND_VWAP,
    STOP_CATASTROPHE,
    TARGET_STRETCH,
    TRIGGER_RECOVERY,
    ElasticBandParams,
)
from tests.test_insidebartrailing_sim import walk_bars
from tools.campaign_shortlist import rebuild
from tools.campaign_sweep import (
    ELASTIC_NOISE,
    ELASTIC_NOISE_ARMS,
    ELASTIC_RUNNER,
    EVERY_DIMENSION,
    NOISE_RESOLUTIONS,
    RESOLUTIONS,
    STRATUM_SETS,
    decision_resolutions,
    grids_for,
    variants_for,
)
from tools.campaign_walkforward import warmup_for

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray

BARS = 40_000
"""About twenty sessions of minutes, so a fourteen-session width has room to be defined."""

LOOKBACK = 14

MOMENTUM = ElasticBandParams(
    band_source=BAND_NOISE,
    entry_std=1.0,
    invert_signal=True,
    stop_mode=STOP_CATASTROPHE,
    target_mode=TARGET_STRETCH,
    target_stretch_levels=(float("nan"),),
    bars_required_to_trade=30,
)
"""The noise area followed on every bar, leaving only by the account stop or the session close."""

RULE = dataclasses.replace(MOMENTUM, check_every_minutes=30, noise_trail_exit=True)
"""The paper's rule: decided on the half hour and trailed on the band or the VWAP."""

SIGNAL = trades.EXIT_REASONS[trades.EXIT_SIGNAL]
SESSION_CLOSE = trades.EXIT_REASONS[trades.EXIT_SESSION_CLOSE]


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(BARS, seed=11)


def prepared(bars: pd.DataFrame, params: ElasticBandParams) -> context.Dataset:
    return context.prepare(
        bars,
        sweep.Grid.of(params, archetype=archetypes.ELASTICBAND).required_context(),
        bar_minutes=1,
        price_basis=context.PriceBasis.RAW,
    )


def closes(data: context.Dataset) -> IntArray:
    """Return the minutes past the session open each bar closes at."""
    clock = data.time_of_day
    assert clock is not None

    return clock.close_minutes()


def mirrored(bars: pd.DataFrame) -> pd.DataFrame:
    """Turn the walk upside down, so every session gaps the other way."""
    flipped = bars.copy()
    level = 2 * float(bars["close"].iloc[0])
    flipped["open"] = level - bars["open"]
    flipped["close"] = level - bars["close"]
    flipped["high"] = level - bars["low"]
    flipped["low"] = level - bars["high"]

    return flipped


def expected_band(bars: pd.DataFrame) -> pd.DataFrame:
    """Read the band's definition with pandas, independently of :mod:`nqbt.noise`."""
    info = sessions.classify(pd.DatetimeIndex(bars.index))
    clock = timeofday.classify(pd.DatetimeIndex(bars.index), bar_minutes=1, info=info)
    frame = pd.DataFrame(
        {
            "session": volume.session_ids(info.trading_day, info.in_session),
            "bar": clock.bar_of_session.astype(np.int64),
            "open": bars["open"].to_numpy(),
            "high": bars["high"].to_numpy(),
            "low": bars["low"].to_numpy(),
            "close": bars["close"].to_numpy(),
            "volume": bars["volume"].to_numpy(),
        }
    )
    cash = (frame["session"] >= 0) & (frame["bar"] >= noise.CASH_OPEN_MINUTES)
    opens = frame[cash & (frame["bar"] == noise.CASH_OPEN_MINUTES)].groupby("session")["open"].first()
    closes_ = frame[cash & (frame["bar"] + 1 <= noise.CASH_CLOSE_MINUTES)].groupby("session")["close"].last()
    frame["opened"] = np.where(cash, frame["session"].map(opens), np.nan)
    anchored = cash & frame["opened"].notna()
    frame["previous"] = np.where(anchored, (frame["session"] - 1).map(closes_), np.nan)
    frame["upper"] = np.fmax(frame["opened"], frame["previous"])
    frame["lower"] = np.fmin(frame["opened"], frame["previous"])
    frame["move"] = (frame["close"] / frame["opened"] - 1.0).abs()
    moves = frame[anchored].pivot_table(index="session", columns="bar", values="move")
    widths = moves.rolling(LOOKBACK, min_periods=noise.MIN_LOOKBACK_SESSIONS).mean().shift(1)
    looked_up = widths.reset_index().melt(id_vars="session", var_name="bar", value_name="width")
    frame = (
        frame.reset_index()
        .merge(looked_up, on=["session", "bar"], how="left")
        .set_index("index")
        .sort_index()
    )
    frame.loc[~anchored, "width"] = np.nan
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    weighted = (typical * frame["volume"]).where(anchored, 0.0).groupby(frame["session"]).cumsum()
    traded = frame["volume"].where(anchored, 0.0).groupby(frame["session"]).cumsum()
    frame["vwap"] = np.where(anchored, weighted / traded, np.nan)

    return frame


# -- the band ----------------------------------------------------------------------------------


@pytest.mark.parametrize("falling", [False, True])
def test_the_band_matches_a_pandas_reading_of_its_definition(bars: pd.DataFrame, *, falling: bool) -> None:
    """The walk drifts, so one way it gaps up each session and the other way down: each anchor takes a gap."""
    walked = mirrored(bars) if falling else bars
    data = prepared(walked, MOMENTUM)
    band = data.noise_band(LOOKBACK)
    expected = expected_band(walked)
    gapped = np.isfinite(expected["previous"]) & (expected["previous"] != expected["opened"])
    side = "upper" if falling else "lower"
    assert (expected.loc[gapped, side] == expected.loc[gapped, "previous"]).all()

    np.testing.assert_allclose(band.upper_anchor, expected["upper"], rtol=0, atol=1e-9)
    np.testing.assert_allclose(band.lower_anchor, expected["lower"], rtol=0, atol=1e-9)
    np.testing.assert_allclose(band.width, expected["width"], rtol=1e-12, atol=0)
    np.testing.assert_allclose(data.noise_vwap(), expected["vwap"], rtol=1e-12, atol=0)
    assert np.isfinite(band.width).sum() > 1000, "nothing is checked if the band is never defined"


def test_a_session_does_not_read_its_own_move(bars: pd.DataFrame) -> None:
    """Strictly prior: moving one session's closes leaves that session's width where it was."""
    band = prepared(bars, MOMENTUM).noise_band(LOOKBACK)
    moved = bars.copy()
    in_session = sessions.classify(pd.DatetimeIndex(bars.index)).in_session
    day = moved.loc[in_session, "trading_day"].unique()[-6]
    inside = (moved["trading_day"] == day).to_numpy()
    moved.loc[inside, "close"] = moved.loc[inside, "close"] * 1.01
    after = prepared(moved, MOMENTUM).noise_band(LOOKBACK)

    np.testing.assert_array_equal(after.width[inside], band.width[inside])
    assert not np.array_equal(after.width[~inside], band.width[~inside], equal_nan=True)


def test_there_is_no_band_before_the_cash_open_or_without_enough_prior_sessions(bars: pd.DataFrame) -> None:
    band = prepared(bars, MOMENTUM).noise_band(LOOKBACK)
    clock = timeofday.classify(pd.DatetimeIndex(bars.index), bar_minutes=1)
    before_open = (clock.bar_of_session >= 0) & (clock.bar_of_session < noise.CASH_OPEN_MINUTES)
    assert np.isnan(band.width[before_open]).all()
    assert np.isnan(band.stretch[before_open]).all()

    first_sessions = bars["trading_day"].isin(bars["trading_day"].unique()[: noise.MIN_LOOKBACK_SESSIONS])
    assert np.isnan(band.width[first_sessions.to_numpy()]).all()


def test_a_series_joined_after_the_cash_open_has_no_anchor_that_session(bars: pd.DataFrame) -> None:
    """A held-out window starting at noon is not anchored on its first bar's open."""
    clock = timeofday.classify(pd.DatetimeIndex(bars.index), bar_minutes=1)
    noon = int(np.flatnonzero(clock.bar_of_session == noise.CASH_OPEN_MINUTES + 150)[3])
    joined = prepared(bars.iloc[noon:], MOMENTUM).noise_band(LOOKBACK)
    first_session = (bars["trading_day"].iloc[noon:] == bars["trading_day"].iloc[noon]).to_numpy()

    assert np.isnan(joined.upper_anchor[first_session]).all()
    assert np.isfinite(joined.upper_anchor[~first_session]).any()


def test_a_previous_close_on_another_contract_leaves_the_band_on_the_open(bars: pd.DataFrame) -> None:
    """A roll's previous close carries the calendar spread, so the session after it is not gap-adjusted."""
    traded = traded_bars(bars).copy()
    days = traded["trading_day"].unique()
    rolled_on = days[10]
    traded["contract"] = np.where(traded["trading_day"] >= rolled_on, "M", "H")
    rolled = prepared(traded, MOMENTUM).noise_band(LOOKBACK)
    unrolled = prepared(traded.drop(columns="contract"), MOMENTUM).noise_band(LOOKBACK)
    first = (traded["trading_day"] == rolled_on).to_numpy() & np.isfinite(rolled.upper_anchor)
    after = (traded["trading_day"] == days[11]).to_numpy() & np.isfinite(rolled.upper_anchor)

    assert first.any()
    np.testing.assert_array_equal(rolled.upper_anchor[first], rolled.lower_anchor[first])
    assert (unrolled.upper_anchor[first] != unrolled.lower_anchor[first]).all()
    np.testing.assert_array_equal(rolled.upper_anchor[after], unrolled.upper_anchor[after])


@pytest.mark.parametrize("bar_minutes", [4, 20, 31])
def test_a_bar_size_missing_a_cash_session_mark_is_refused(bars: pd.DataFrame, bar_minutes: int) -> None:
    """31 divides 09:30's 930 minutes and neither 15:30's nor 16:00's."""
    coarse = bars.iloc[bar_minutes - 1 :: bar_minutes]
    with pytest.raises(noise.NoiseError, match="no anchor"):
        context.prepare(coarse, context.ContextSpec(noise_lookbacks=(LOOKBACK,)), bar_minutes=bar_minutes)


@pytest.mark.parametrize(
    ("close", "expected"),
    [
        (103.0, (103.0 - 102.0) / (102.0 * 0.01)),
        (102.0, 0.0),
        (101.0, 0.0),
        (100.0, 0.0),
        (99.0, (99.0 - 100.0) / (100.0 * 0.01)),
    ],
)
def test_a_close_is_measured_past_the_nearer_anchor_and_reads_zero_between_them(
    close: float, expected: float
) -> None:
    stretch = noise.noise_stretch(np.array([close]), np.array([102.0]), np.array([100.0]), np.array([0.01]))
    assert stretch[0] == pytest.approx(expected)


@pytest.mark.parametrize("width", [np.nan, 0.0, -0.01])
def test_a_close_against_no_width_has_no_stretch(width: float) -> None:
    stretch = noise.noise_stretch(np.array([103.0]), np.array([102.0]), np.array([100.0]), np.array([width]))
    assert np.isnan(stretch[0])


def test_the_basis_is_the_anchor_a_close_is_measured_from(bars: pd.DataFrame) -> None:
    band = prepared(bars, MOMENTUM).noise_band(LOOKBACK)
    below = band.stretch < 0.0
    at_or_above = band.stretch >= 0.0

    np.testing.assert_array_equal(band.basis[below], band.lower_anchor[below])
    np.testing.assert_array_equal(band.basis[at_or_above], band.upper_anchor[at_or_above])
    np.testing.assert_allclose(band.stddev, band.basis * band.width)


def test_a_lookback_too_short_to_average_is_refused() -> None:
    with pytest.raises(noise.NoiseError, match="lookback"):
        noise.validate_lookback(noise.MIN_LOOKBACK_SESSIONS - 1)
    with pytest.raises(noise.NoiseError, match="lookback"):
        ElasticBandParams(band_source=BAND_NOISE, noise_lookback_sessions=noise.MIN_LOOKBACK_SESSIONS - 1)


def test_a_band_nobody_asked_for_names_the_spec_field_to_set(bars: pd.DataFrame) -> None:
    data = context.prepare(bars, context.ContextSpec(), bar_minutes=1)
    for read in (lambda: data.noise_band(LOOKBACK), data.noise_vwap):
        with pytest.raises(context.ContextError, match="noise_lookbacks"):
            read()


def test_a_lookback_the_grid_was_not_built_for_is_named() -> None:
    nothing: FloatArray = np.zeros(1)
    grid = noise.NoiseBandGrid({LOOKBACK: noise.NoiseBand(*(nothing,) * 7)}, nothing)
    with pytest.raises(KeyError, match=r"built for \[14\]"):
        grid.band(20)


def test_the_cash_session_is_the_phases_clock() -> None:
    starts = timeofday.phase_start_minutes()
    assert noise.CASH_OPEN_MINUTES == starts[timeofday.SessionPhase.CASH_OPEN] == 930
    assert noise.CASH_CLOSE_MINUTES == starts[timeofday.SessionPhase.CLOSE] == 1320
    assert noise.LAST_ENTRY_MINUTES == 1290


# -- what the registry builds ------------------------------------------------------------------


def test_a_noise_grid_builds_the_band_the_clock_and_no_period_grid() -> None:
    spec = sweep.Grid.of(RULE, archetype=archetypes.ELASTICBAND).required_context()
    assert spec.noise_lookbacks == (LOOKBACK,)
    assert spec.band_periods == ()
    assert not spec.needs_vwap_band
    assert spec.needs_time_of_day


def test_the_cash_close_asks_for_the_clock_on_any_source() -> None:
    closed = dataclasses.replace(MOMENTUM, band_source=BAND_VWAP, exit_at_cash_close=True)
    assert sweep.Grid.of(closed, archetype=archetypes.ELASTICBAND).required_context().needs_time_of_day


def test_a_bollinger_grid_still_builds_its_period_and_no_noise_band() -> None:
    spec = sweep.Grid.of(
        ElasticBandParams(band_source=BAND_BOLLINGER), archetype=archetypes.ELASTICBAND
    ).required_context()
    assert spec.band_periods == (20,)
    assert spec.noise_lookbacks == ()


def traded_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Keep the in-session bars alone, as every loaded series does."""
    return bars[sessions.classify(pd.DatetimeIndex(bars.index)).in_session]


def test_a_fold_behind_its_warm_up_reads_the_band_the_whole_series_does(bars: pd.DataFrame) -> None:
    """The walk-forward prefix is enough sessions of bars that a fold's band is the full run's."""
    traded = traded_bars(bars)
    spec = sweep.Grid.of(MOMENTUM, archetype=archetypes.ELASTICBAND).required_context()
    warm = warmup_for(spec, 1)
    start = warm + 700
    whole = prepared(traded, MOMENTUM).noise_band(LOOKBACK)
    fold = prepared(traded.iloc[start - warm :], MOMENTUM).noise_band(LOOKBACK)

    assert start < len(traded)
    assert np.isfinite(fold.width[warm:]).sum() > 100
    np.testing.assert_array_equal(fold.width[warm:], whole.width[start:])
    np.testing.assert_array_equal(fold.upper_anchor[warm:], whole.upper_anchor[start:])


@pytest.mark.parametrize("bar_minutes", [5, 15])
def test_a_coarser_bar_reads_the_band_the_minutes_read_at_its_close(
    bars: pd.DataFrame, bar_minutes: int
) -> None:
    """The anchors and the width are read on closes the bar sizes share, so they agree there."""
    traded = traded_bars(bars)
    fine = prepared(traded, MOMENTUM).noise_band(LOOKBACK)
    coarse_bars = resample.resample(traded, bar_minutes)
    coarse = context.prepare(
        coarse_bars,
        sweep.Grid.of(MOMENTUM, archetype=archetypes.ELASTICBAND).required_context(),
        bar_minutes=bar_minutes,
        price_basis=context.PriceBasis.RAW,
    ).noise_band(LOOKBACK)
    at = pd.DatetimeIndex(traded.index).get_indexer(pd.DatetimeIndex(coarse_bars.index))
    # A series' last coarse bar can be cut short, and is stamped off its own grid.
    shared = (at >= 0) & (pd.DatetimeIndex(coarse_bars.index).minute % bar_minutes == 0)

    assert np.isfinite(coarse.width[shared]).sum() > 50
    np.testing.assert_array_equal(coarse.upper_anchor[shared], fine.upper_anchor[at[shared]])
    np.testing.assert_array_equal(coarse.lower_anchor[shared], fine.lower_anchor[at[shared]])
    np.testing.assert_allclose(coarse.width[shared], fine.width[at[shared]], rtol=1e-12, atol=0)


# -- when an entry is decided ------------------------------------------------------------------


def test_the_noise_area_enters_only_on_closes_after_the_cash_open_and_by_1530(bars: pd.DataFrame) -> None:
    data = prepared(bars, MOMENTUM)
    signal = archetypes.ELASTICBAND.signal(data, MOMENTUM)
    decided = closes(data)[signal]

    assert signal.sum() > 50
    assert (decided > noise.CASH_OPEN_MINUTES).all()
    assert (decided <= noise.LAST_ENTRY_MINUTES).all()


def test_half_hour_decisions_are_the_every_bar_signals_on_the_half_hour(bars: pd.DataFrame) -> None:
    checked = dataclasses.replace(MOMENTUM, check_every_minutes=30)
    data = prepared(bars, checked)
    every = archetypes.ELASTICBAND.signal(data, MOMENTUM)
    halves = archetypes.ELASTICBAND.signal(data, checked)
    on_the_half_hour = closes(data) % 30 == 0

    assert np.array_equal(halves, every & on_the_half_hour)
    assert halves.any()
    assert halves.sum() < every.sum()


def test_a_bar_size_missing_some_decision_marks_is_refused(bars: pd.DataFrame) -> None:
    coarse = bars.iloc[19::20]
    data = context.prepare(coarse, context.ContextSpec(needs_time_of_day=True), bar_minutes=20)
    with pytest.raises(timeofday.TimeOfDayError, match="every 30-minute mark"):
        data.closes_every(30)


@pytest.mark.parametrize("minutes", [-1, 7, 45])
def test_a_cadence_off_the_hours_minutes_is_refused(minutes: int) -> None:
    with pytest.raises(ValueError, match="check_every_minutes"):
        dataclasses.replace(MOMENTUM, check_every_minutes=minutes)


def test_no_entry_is_decided_at_or_after_the_cash_close_while_that_exit_is_on(bars: pd.DataFrame) -> None:
    closed = dataclasses.replace(
        MOMENTUM, band_source=BAND_VWAP, vwap_min_session_bars=5, exit_at_cash_close=True
    )
    data = prepared(bars, closed)
    open_all_day = archetypes.ELASTICBAND.signal(data, dataclasses.replace(closed, exit_at_cash_close=False))
    signal = archetypes.ELASTICBAND.signal(data, closed)
    before_close = (closes(data) > 0) & (closes(data) < noise.CASH_CLOSE_MINUTES)

    assert (open_all_day & ~before_close).any()
    assert np.array_equal(signal, open_all_day & before_close)


def test_a_bar_between_the_anchors_takes_its_side_from_their_midpoint(bars: pd.DataFrame) -> None:
    """The random-entry arm draws bars inside the gap too, so they cannot all read as one side."""
    data = prepared(bars, RULE)
    band = data.noise_band(LOOKBACK)
    between: BoolArray = (
        np.isfinite(band.width) & (band.stretch == 0.0) & (band.upper_anchor > band.lower_anchor)
    )
    centre: FloatArray = 0.5 * (band.upper_anchor + band.lower_anchor)
    long_side = archetypes.ELASTICBAND.long_side(data, RULE)

    assert between.sum() > 100
    np.testing.assert_array_equal(long_side[between], (data.close >= centre)[between])
    assert long_side[between].any()
    assert not long_side[between].all()


# -- how a trade leaves ------------------------------------------------------------------------


def trail_level(data: context.Dataset, params: ElasticBandParams, bar: int, direction: float) -> float:
    """Return the trail's level the way the paper states it, independently of the loop."""
    band = data.noise_band(params.noise_lookback_sessions)
    vwap: FloatArray = data.noise_vwap()
    if direction > 0:
        return max(float(band.upper_anchor[bar] * (1 + params.entry_std * band.width[bar])), float(vwap[bar]))

    return min(float(band.lower_anchor[bar] * (1 - params.entry_std * band.width[bar])), float(vwap[bar]))


def test_every_trail_exit_follows_a_decided_close_back_past_the_band_or_the_vwap(bars: pd.DataFrame) -> None:
    data = prepared(bars, RULE)
    log = archetypes.ELASTICBAND.run(data, RULE)
    trailed = log[log["exit_reason"] == SIGNAL]
    positions = data.index.get_indexer(pd.DatetimeIndex(trailed["exit_time"])) - 1
    decided = data.closes_every(30)

    assert len(trailed) > 3, "nothing is checked if the trail never fires"
    for decision, direction in zip(positions, trailed["direction"], strict=True):
        assert decided[decision]
        assert (
            direction * (data.close[decision] - trail_level(data, RULE, int(decision), float(direction))) < 0
        )


def test_no_decided_close_that_holds_the_band_or_the_vwap_closes_a_trade(bars: pd.DataFrame) -> None:
    """The trail leaves at the first decided close past its level and at none before it."""
    data = prepared(bars, RULE)
    log = archetypes.ELASTICBAND.run(data, RULE)
    decided = np.flatnonzero(data.closes_every(30))
    entries = data.index.get_indexer(pd.DatetimeIndex(log["entry_time"]))
    exits = data.index.get_indexer(pd.DatetimeIndex(log["exit_time"]))

    held_checks = 0
    for entry, exit_bar, direction, reason in zip(
        entries, exits, log["direction"], log["exit_reason"], strict=True
    ):
        last_held = exit_bar - 2 if reason == SIGNAL else exit_bar - 1
        for bar in decided[(decided >= entry) & (decided <= last_held)]:
            assert direction * (data.close[bar] - trail_level(data, RULE, int(bar), float(direction))) >= 0
            held_checks += 1

    assert held_checks > 10, "nothing is checked if no trade held through a decided close"


def test_the_cash_close_exit_is_the_clocks_and_leaves_after_the_first_close_at_or_after_1600(
    bars: pd.DataFrame,
) -> None:
    closed = dataclasses.replace(MOMENTUM, exit_at_cash_close=True)
    data = prepared(bars, closed)
    log = archetypes.ELASTICBAND.run(data, closed)
    clocked = data.index.get_indexer(
        pd.DatetimeIndex(log.loc[log["exit_reason"] == SESSION_CLOSE, "exit_time"])
    )
    minutes = closes(data)
    at_the_cash_close = (minutes[clocked - 1] >= noise.CASH_CLOSE_MINUTES) & (
        minutes[clocked - 2] < noise.CASH_CLOSE_MINUTES
    )
    # A session whose bars stop before the cash close -- a half day, or a series cut off mid-session
    # -- has no close to leave after, so its own flatten closes it.
    flattened_early = minutes[clocked] < noise.CASH_CLOSE_MINUTES

    assert at_the_cash_close.sum() > 3
    assert (at_the_cash_close | flattened_early).all()
    assert not (log["exit_reason"] == SIGNAL).any()


def test_at_the_cash_close_the_clock_closes_a_trade_the_trail_would_also_close(bars: pd.DataFrame) -> None:
    """16:00 is a decided close too, and on that bar the exit is the clock's."""
    closed = dataclasses.replace(RULE, exit_at_cash_close=True)
    data = prepared(bars, closed)
    log = archetypes.ELASTICBAND.run(data, closed)
    decided_at = data.index.get_indexer(pd.DatetimeIndex(log["exit_time"])) - 1
    minutes = closes(data)
    at_the_cash_close = minutes[decided_at] == noise.CASH_CLOSE_MINUTES
    past_the_trail = np.array(
        [
            direction * (data.close[bar] - trail_level(data, closed, int(bar), float(direction))) < 0
            for bar, direction in zip(decided_at, log["direction"], strict=True)
        ]
    )

    assert (at_the_cash_close & past_the_trail).any(), (
        "nothing is checked if no trade was past the trail at 16:00"
    )
    assert (log.loc[at_the_cash_close, "exit_reason"] == SESSION_CLOSE).all()


def test_the_trail_level_takes_whichever_of_the_band_and_the_vwap_is_nearer() -> None:
    band = elasticband.BandSeries(
        basis=np.zeros(3),
        stddev=np.zeros(3),
        excursion_extreme=np.zeros(3),
        atr=np.zeros(0),
        upper_anchor=np.array([100.0, 100.0, np.nan]),
        lower_anchor=np.array([90.0, 90.0, np.nan]),
        width=np.array([0.01, 0.01, np.nan]),
        vwap=np.array([105.0, 95.0, 97.0]),
    )
    assert elasticband.noise_trail_level(band, 0, 1.0, 1.0) == pytest.approx(105.0)
    assert elasticband.noise_trail_level(band, 1, 1.0, 1.0) == pytest.approx(101.0)
    assert elasticband.noise_trail_level(band, 1, -1.0, 1.0) == pytest.approx(89.1)
    assert elasticband.noise_trail_level(band, 0, -1.0, 2.0) == pytest.approx(88.2)
    assert elasticband.noise_trail_level(band, 2, 1.0, 1.0) == pytest.approx(97.0)


# -- what is refused ---------------------------------------------------------------------------


def test_the_trail_off_the_noise_area_is_refused() -> None:
    with pytest.raises(ValueError, match="noise_trail_exit reads the noise area"):
        dataclasses.replace(RULE, band_source=BAND_VWAP)


def test_the_trail_on_a_fade_is_refused() -> None:
    with pytest.raises(ValueError, match="needs invert_signal"):
        dataclasses.replace(RULE, invert_signal=False)


def test_the_trail_on_a_recovery_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="recovery entry"):
        dataclasses.replace(RULE, entry_trigger=TRIGGER_RECOVERY)


def test_a_lagged_noise_area_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot move the noise area"):
        dataclasses.replace(MOMENTUM, band_lag=1)


# -- the campaign's arms -----------------------------------------------------------------------


def built_arms() -> dict[str, ElasticBandParams]:
    arms: dict[str, ElasticBandParams] = {}
    for variant in variants_for(ELASTIC_NOISE)["ElasticBand"]("MNQ"):
        assert isinstance(variant.base, ElasticBandParams)
        arms[variant.name] = variant.base

    return arms


def test_the_noise_set_is_four_arms_of_one_grid_in_every_dimension() -> None:
    built = variants_for(ELASTIC_NOISE)["ElasticBand"]("MNQ")
    assert [variant.name for variant in built] == list(ELASTIC_NOISE_ARMS)
    assert {len(grids_for(variant, "unfiltered")[0][1]) for variant in built} == {12}
    assert STRATUM_SETS[ELASTIC_NOISE] == EVERY_DIMENSION


def test_every_arm_builds_in_every_stratum() -> None:
    """A phase the noise area cannot reach trades nothing rather than being refused."""
    for variant in variants_for(ELASTIC_NOISE)["ElasticBand"]("MNQ"):
        for _, grid in grids_for(variant, ELASTIC_NOISE):
            assert len(grid) == 12


def test_a_bar_size_off_the_half_hour_is_skipped_and_every_campaign_one_kept() -> None:
    assert decision_resolutions((1, 2, 4, 5, 20, 30, 60)) == (1, 2, 5, 30)
    assert NOISE_RESOLUTIONS == RESOLUTIONS
    for variant in variants_for(ELASTIC_NOISE)["ElasticBand"]("MNQ"):
        assert variant.resolutions == NOISE_RESOLUTIONS


def test_the_rule_arm_is_the_papers_and_the_fade_targets_the_nearer_anchor() -> None:
    built = built_arms()
    rule = built[f"noise=rule {ELASTIC_RUNNER}"]
    fade = built["noise=fade target=0.0s"]
    assert (rule.band_source, rule.invert_signal, rule.check_every_minutes, rule.noise_trail_exit) == (
        BAND_NOISE,
        True,
        30,
        True,
    )
    assert np.isnan(rule.target_stretch_levels).all()
    assert not fade.invert_signal
    assert fade.target_stretch_levels[0] == 0.0


@pytest.mark.parametrize("name", list(ELASTIC_NOISE_ARMS))
def test_a_stored_row_of_every_arm_rebuilds_into_the_arm_it_ran(name: str) -> None:
    """A tuple is not a stored column, so the ladder has to come back from the variant's name."""
    base = built_arms()[name]
    stored = {key: value for key, value in dataclasses.asdict(base).items() if not isinstance(value, tuple)}
    rebuilt = rebuild(pd.Series({**stored, "variant": name}), archetypes.ELASTICBAND)

    assert isinstance(rebuilt, ElasticBandParams)
    np.testing.assert_array_equal(rebuilt.target_stretch_levels, base.target_stretch_levels)
    assert dataclasses.replace(rebuilt, target_stretch_levels=base.target_stretch_levels) == base
