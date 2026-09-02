"""Pinned numbers the whole numeric pipeline must keep reproducing.

One deterministic scenario -- bars, context, simulation, statistics -- compared against stored
values, so that a dependency bump moving a number fails CI instead of passing quietly. The
trade-log gate this stands in for needs `data/` and `verification/`, and neither is committed;
the argument is in ``docs/roadmap.md`` § "What CI can gate on a dependency bump".

Two things here are deliberate and read as mistakes otherwise:

- **It pins the transcript, not the property**, which ``CONTRIBUTING.md`` § "Tests" otherwise
  forbids. A stated property cannot see a one-ULP drift, and a one-ULP drift at a fill boundary
  is exactly what a numba or numpy bump moves.
- **The bars come from integer arithmetic, never from ``numpy.random``.** A change to the
  generator stream is ``tests/test_rng_stream_pins.py``'s finding, and must not be able to
  surface here as a simulation failure.
"""

import hashlib

import numpy as np
import pandas as pd
import pytest

from nqbt import conditions, context, sessions, stats
from nqbt.context import ContextSpec
from nqbt.instruments import MNQ
from nqbt.sim.runner import deadcat_legs, run_deadcat
from nqbt.sim.types import DeadCatParams

TICK = 0.25
BARS = 20_000

# The walk. Chosen so the scenario reaches every exit reason, both outcomes and a scratch --
# test_the_scenario_still_exercises_every_exit_reason is what holds that.
WALK_SEED = 23
STEP_TICKS = 6
WICK_TICKS = 3
DRIFT_TICKS = 3
FALL_FROM_MINUTE = 12 * 60
FALL_UNTIL_MINUTE = 22 * 60  # the force-flat, so a short can reach the close rather than a stop

NAN_SENTINEL = -8.5070591730234616e37
"""Stands in for ``nan`` when hashing, which has no single bit pattern to hash."""


def _lcg_states(count: int, seed: int) -> list[int]:
    """A linear congruential sequence in Python ints, so no library owns the stream."""
    state: int = seed
    states: list[int] = []
    for _ in range(count):
        state = (state * 1103515245 + 12345) % 2**31
        states.append(state)

    return states


def deterministic_bars(count: int = BARS) -> pd.DataFrame:
    """Bars on the tick grid, built from integer arithmetic alone.

    Every price is a whole number of ticks, so every value is exact in float64 and the frame is
    identical on any platform and any numpy.
    """
    states: list[int] = _lcg_states(count, WALK_SEED)
    index: pd.DatetimeIndex = pd.date_range("2024-01-02 00:00", periods=count, freq="min", tz="UTC")

    minute_of_day = index.hour * 60 + index.minute
    falling = (minute_of_day >= FALL_FROM_MINUTE) & (minute_of_day < FALL_UNTIL_MINUTE)
    steps = np.array([state % (2 * STEP_TICKS + 1) - STEP_TICKS for state in states], dtype=np.int64)
    walk = np.cumsum(steps + np.where(falling, -DRIFT_TICKS, DRIFT_TICKS))

    close = 16000.0 + TICK * walk
    open_ = np.concatenate([[16000.0], close[:-1]])
    upper_wick = np.array([(state >> 7) % (WICK_TICKS + 1) for state in states], dtype=np.int64)
    lower_wick = np.array([(state >> 13) % (WICK_TICKS + 1) for state in states], dtype=np.int64)
    volume = np.array([(state >> 3) % 500 + 1 for state in states], dtype=np.int64)

    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + TICK * upper_wick,
            "low": np.minimum(open_, close) - TICK * lower_wick,
            "close": close,
            "volume": volume.astype(np.float64),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


PARAMS = DeadCatParams(
    use_ema=True,
    use_slow_sma=True,
    use_fast_sma=True,
    use_vwap=True,
    commission_per_contract=0.75,
    slippage_ticks=1.0,
)
"""Every gate on and costs applied, so the pins cover the whole signal and the cost path."""

SPEC = ContextSpec(
    ma_keys=conditions.ma_keys(
        ema=(PARAMS.ema_period,), sma=tuple(sorted({PARAMS.slow_sma_period, PARAMS.fast_sma_period}))
    ),
    needs_vwap=True,
)


def _digest(values: np.ndarray) -> str:
    """Hash one float64 column, reading ``-0.0`` as ``0.0`` and ``nan`` as one fixed value.

    Both normalisations are what stops this being stricter than the trade-log gate --
    ``CONTRIBUTING.md`` § "The trade-log regression gate".
    """
    clean = np.where(np.isnan(values), NAN_SENTINEL, values) + 0.0

    return hashlib.sha256(np.ascontiguousarray(clean, dtype=np.float64).tobytes()).hexdigest()


BAR_DIGESTS = {
    "open": "44e601757efed0b0ba29c1e4dfc326ad95177f3433dbaf5f53265464babe804a",
    "high": "304a8914052a95134738c02ebd0bc054a8404751f8597878eead48c03e0bd592",
    "low": "fedd6f54302a933246e40ca6b39c026b058707bd5b1ed8c5f6e85de66c5eb373",
    "close": "fae1904ed2b1ad8b018b5ff89f389f07fc9cd4fa882cdc43c67a0b25ead70142",
    "volume": "c1600dc86f86aacd229c8d93db8be575a38e8a91313da940065d4cc8e76a7410",
}

LEG_DIGESTS = {
    "trade_id": "e3f4b3fb6df8f4db1330e5324f272b68abfa8b9d6de32a0350da6b78f12d2fe3",
    "leg": "82a55d1f32c4fcb208fb9d742c0044d48410cda6c306466c6f23bbfe598dd1e6",
    "entry_bar": "1ee1af8f01f52b05b948fe01625b75c7e8a7dc992819d0f07ee6b29704ba9340",
    "exit_bar": "60541545aa418af3063767e3479ef99ca17ed1b9d6dce5c5b3d0a528438a87f6",
    "entry_price": "3672296ae5e7e871440a6194e3639537fb5405a0b02a594eb6284cd96621aa88",
    "exit_price": "f5feaf348496ae1696f1e7b9350395aeff401ae108a1105c2d8e93e14acf11ee",
    "initial_stop": "da3b6b605b6a1dea57a9d4622c62dcfa2cbe3d94bea8ff63298583dbcead794a",
    "target_price": "c1b253135e7f4e03e3c1ef12b4973e862f0ffdb2be7fb2ecc613b0f8de744973",
    "quantity": "c08966543ff025ba74e2ce4905181ba53ce3d9dd1aa5508025efd7fcc60f8017",
    "direction": "3558cf855f59395baabd603d1aaf946cb0e93520bf5ea11a15bba6698e53d476",
    "gross_pnl": "d2d3c08c01491e42cd4225c0e579a71de9390c52da53af47e2dd79cf71d0c2c1",
    "commission": "e5f1d29cf913a5b7bd86841f045e17ce343fb81047cf090e2d123fd4fcb9f013",
    "net_pnl": "e0d6a72811a71abf1532a032f886233aa1e95df437ff9fa728574b0d42d6d580",
    "r_multiple": "bba4c58e3a5f6989b84ad04e21fa82c89083af87d049a5a49373597cfad1eb60",
    "risk_points": "08762497ba33bb0b44035d9784a882ae6342558be9192bf0dc7b9ff68a3fab66",
    "mae_points": "f0aafa90efe5f32044f6a04170deb107cdddd0f91ba85dfeeeac6c971d29ffd3",
    "mfe_points": "6f6a69ce627d8c6ffcdbcc38f736b1558ebb2116c5608b952fbbdb44ca0ecd0e",
    "bars_held": "9726c94fe1bed3b2afb0b0574c7e10db47c72659efd05fb9ea44f2ee73c85101",
}

SUMMARY = {
    "trades": 25,
    "legs": 100,
    "wins": 12,
    "losses": 11,
    "scratches": 2,
    "win_rate": 0.48,
    "net_pnl": 91.5,
    "gross_profit": 223.0,
    "gross_loss": -131.5,
    "profit_factor": 1.6958174904942966,
    "expectancy": 3.66,
    "avg_win": 18.583333333333332,
    "avg_loss": -11.954545454545455,
    "largest_win": 49.0,
    "largest_loss": -21.0,
    "max_drawdown": 36.0,
    "max_consecutive_losses": 3,
    "avg_bars_held": 4.48,
    "avg_mae_points": 1.31,
    "avg_mfe_points": 3.64,
    "mean_r": 0.43988095238095243,
    "r_p10": -1.3333333333333333,
    "r_median": 0.14285714285714285,
    "r_p90": 1.8571428571428572,
    "sharpe": 5.971901062695676,
    "sortino": 17.198349669136025,
    "ambiguous_share": 0.06,
    "session_close_share": 0.04,
    "commission_paid": 75.0,
}


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return deterministic_bars()


@pytest.fixture(scope="module")
def log(frame) -> pd.DataFrame:
    return run_deadcat(context.prepare(frame, SPEC), PARAMS, MNQ)


# -- the input, so a failure below can be attributed ---------------------------


def test_the_generated_bars_are_unchanged(frame) -> None:
    """Fails first when the *input* moved, which every other pin here would blame on the sim."""
    got = {name: _digest(frame[name].to_numpy(np.float64)) for name in BAR_DIGESTS}
    assert got == BAR_DIGESTS


def test_every_generated_price_lies_on_the_tick_grid(frame) -> None:
    """What makes the bars exact in float64, and so identical on any platform."""
    for name in ("open", "high", "low", "close"):
        prices = frame[name].to_numpy(np.float64)
        assert np.array_equal(prices, np.round(prices / TICK) * TICK)


# -- the pins ------------------------------------------------------------------


def test_every_trade_log_column_digests_to_its_pinned_value(log) -> None:
    """Column by column, so a failure names what moved rather than only that something did."""
    got = {name: _digest(log[name].to_numpy(np.float64)) for name in LEG_DIGESTS}
    assert got == LEG_DIGESTS


def test_the_pinned_summary_is_unchanged(log) -> None:
    assert stats.summarise(log).as_dict() == SUMMARY


def test_the_two_summary_paths_still_agree_on_this_scenario(frame) -> None:
    """``summarise_legs`` is the fast path; a bump must not move it away from the reference."""
    data = context.prepare(frame, SPEC)
    legs = deadcat_legs(data, PARAMS, MNQ)
    assert stats.summarise_legs(legs, data.day_codes).as_dict() == SUMMARY


# -- the scenario has to keep being worth pinning ------------------------------


def test_the_scenario_still_exercises_every_exit_reason(log) -> None:
    """Retuning the walk must not quietly drop the force-flat path out of the gate."""
    assert set(log["exit_reason"]) == {"stop", "target", "session_close"}
    assert log["ambiguous_bar"].sum() > 0, "no ambiguous bar, so the resolution rule is untested"


def test_the_scenario_produces_wins_losses_and_a_scratch() -> None:
    """A pin over one outcome would leave most of the statistics at a degenerate zero."""
    assert SUMMARY["wins"] > 0
    assert SUMMARY["losses"] > 0
    assert SUMMARY["scratches"] > 0


def test_a_moved_number_is_caught(log) -> None:
    """The gate must be able to fail: one value, one tick, one column."""
    tampered = log.copy()
    tampered.loc[tampered.index[0], "exit_price"] += TICK
    got = {name: _digest(tampered[name].to_numpy(np.float64)) for name in LEG_DIGESTS}
    assert got != LEG_DIGESTS
    assert [name for name in LEG_DIGESTS if got[name] != LEG_DIGESTS[name]] == ["exit_price"]
