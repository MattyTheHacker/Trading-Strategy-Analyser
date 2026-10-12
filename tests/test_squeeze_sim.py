"""SqueezeBreakout simulation tests on hand-built bars.

The archetype has no NinjaScript and runs OpeningRange's loop, whose fill rules
``tests/test_openingrange_sim.py`` already pins. What these pin instead is what the squeeze adds:
a level that moves with a rolling window rather than resting for a session, a signal that is the
compression filter's own rule cut at one threshold, and the property the archetype is worthless
without -- that nothing it reads comes from a bar it could not have seen.

Prices are kept small and round so the arithmetic is checkable by eye.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, compression, context, randomentry, sessions, sweep, timeofday
from nqbt.compression import Compression, CompressionForm
from nqbt.instruments import MNQ, NQ
from nqbt.sim import openingrange
from nqbt.sim.squeeze import (
    NO_UPPER_CUT,
    entry_bound,
    latch_of,
    run_squeeze,
    scan_latches,
    squeeze_levels,
    squeeze_signal,
    squeezed_bars,
)
from nqbt.sim.types import (
    ORB_STOP_ATR,
    ORB_STOP_FRACTION,
    ORB_STOP_OPPOSITE,
    ORB_TARGET_WIDTH,
    SqueezeBreakoutParams,
)
from nqbt.trades import LONG, SHORT

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

type Row = tuple[float, float, float, float]
"""One bar as open, high, low, close."""

TICK = MNQ.tick_size
WINDOW = 3

HAND_BUILT = SqueezeBreakoutParams(
    squeeze_period=WINDOW,
    bars_required_to_trade=0,
    entry_offset_ticks=1,
    stop_offset_ticks=2,
    target_r_multiples=(1.0,),
    order_quantity=1,
)
"""A three-bar window, one leg at 1R, and no warm-up, so every level below is readable by eye."""

QUIET = [
    (100.0, 105.0, 98.0, 101.0),
    (101.0, 103.0, 99.0, 102.0),
    (102.0, 104.0, 100.0, 103.0),
]
"""Three bars whose window is 98 to 105 at bar 2."""

PAD = (104.0, 104.5, 103.5, 104.0)
"""A bar that reaches nothing, so the one after a test's last bar is not also the session's last."""


def frame_of(rows: Sequence[Row]) -> pd.DataFrame:
    """Build consecutive minute bars from hand-written OHLC rows, in the middle of one session."""
    arr = np.asarray(rows, dtype=np.float64)
    index = pd.date_range("2024-01-02 15:00", periods=len(arr), freq="min", tz="UTC")
    frame = pd.DataFrame(
        {"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3], "volume": 100.0},
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


def dataset_for(params: SqueezeBreakoutParams, frame: pd.DataFrame) -> context.Dataset:
    """Build a dataset carrying exactly what one combination reads."""
    return context.prepare(frame, sweep.Grid.of(params).required_context(), bar_minutes=1)


def run(
    rows: Sequence[Row], signal_at: Iterable[int], params: SqueezeBreakoutParams = HAND_BUILT
) -> pd.DataFrame:
    """Simulate hand-written rows with the squeeze injected on ``signal_at``."""
    frame = frame_of([*rows, PAD])
    data = dataset_for(params, frame)
    signal = np.zeros(len(data), dtype=np.bool_)
    signal[list(signal_at)] = True

    return run_squeeze(data, params, MNQ, signal=signal)


# -- the level, which moves with the window ----------------------------------------


def test_the_order_rests_a_tick_beyond_the_window_high_at_the_signal_bar() -> None:
    trades = run([*QUIET, (103.0, 108.0, 102.0, 107.0)], signal_at=(2,))

    assert len(trades) == 1
    assert trades["entry_bar"].iloc[0] == 3
    assert trades["entry_price"].iloc[0] == 105.0 + TICK
    assert trades["initial_stop"].iloc[0] == 98.0 - 2 * TICK, "the window's other extreme, offset"


def test_the_level_moves_with_the_window_and_the_resubmitted_order_follows_it() -> None:
    """The one thing the squeeze does that OpeningRange's resting level never does.

    Bar 0's high of 105 leaves the window at bar 3, so the order bar 3 resubmits rests below the
    one bar 2 placed -- and bar 4 reaches the new level without reaching the old one.
    """
    rows = [*QUIET, (103.0, 104.5, 102.0, 104.0), (104.0, 105.0, 103.5, 104.5)]

    trades = run(rows, signal_at=(2, 3))
    assert len(trades) == 1
    assert trades["entry_bar"].iloc[0] == 4
    assert trades["entry_price"].iloc[0] == 104.5 + TICK
    assert trades["initial_stop"].iloc[0] == 99.0 - 2 * TICK

    assert len(run(rows, signal_at=(2,))) == 0, "one submission lives one bar, at bar 2's level"


def test_a_bar_that_is_not_squeezed_submits_nothing() -> None:
    assert len(run([*QUIET, (103.0, 108.0, 102.0, 107.0)], signal_at=())) == 0


def test_the_short_side_rests_a_tick_below_the_window_low() -> None:
    params = replace(HAND_BUILT, direction=SHORT)
    trades = run([*QUIET, (101.0, 102.0, 95.0, 96.0)], signal_at=(2,), params=params)

    assert len(trades) == 1
    assert trades["direction"].iloc[0] == SHORT
    assert trades["entry_price"].iloc[0] == 98.0 - TICK
    assert trades["initial_stop"].iloc[0] == 105.0 + 2 * TICK


def test_a_window_still_filling_has_no_level_to_rest_at() -> None:
    """Bar 1's window is two bars of three, so a signal there is refused rather than traded short."""
    trades = run([QUIET[0], QUIET[1], (102.0, 110.0, 101.0, 109.0)], signal_at=(1,))

    assert len(trades) == 0


def test_a_close_on_the_window_high_cannot_submit_without_an_offset() -> None:
    """NT8 declines a stop entry at the market -- ``docs/nt8-fidelity.md`` §M18."""
    closed_on_high = [QUIET[0], QUIET[1], (102.0, 106.0, 100.0, 106.0), (106.0, 110.0, 105.0, 109.0)]

    assert len(run(closed_on_high, signal_at=(2,), params=replace(HAND_BUILT, entry_offset_ticks=0))) == 0
    assert len(run(closed_on_high, signal_at=(2,))) == 1


# -- the bracket, measured against the window rather than a session's range --------


def test_the_fraction_stop_is_a_share_of_the_window_back_from_its_high() -> None:
    params = replace(HAND_BUILT, stop_mode=ORB_STOP_FRACTION, stop_range_fraction=0.5)
    trades = run([*QUIET, (103.0, 108.0, 102.0, 107.0)], signal_at=(2,), params=params)

    assert trades["initial_stop"].iloc[0] == 105.0 - 0.5 * 7.0 - 2 * TICK


def test_the_atr_stop_reads_the_signal_bar_s_atr() -> None:
    params = replace(HAND_BUILT, stop_mode=ORB_STOP_ATR, atr_period=2, atr_stop_multiple=1.5)
    rows = [*QUIET, (103.0, 108.0, 102.0, 107.0)]
    frame = frame_of([*rows, PAD])
    data = dataset_for(params, frame)
    signal = np.zeros(len(data), dtype=np.bool_)
    signal[2] = True

    trades = run_squeeze(data, params, MNQ, signal=signal)
    trigger = 105.0 + TICK
    assert trades["initial_stop"].iloc[0] == pytest.approx(trigger - 1.5 * data.atr_values(2)[2])


def test_a_width_target_is_a_multiple_of_the_window() -> None:
    params = replace(HAND_BUILT, target_mode=ORB_TARGET_WIDTH, target_width_multiples=(0.5,))
    trades = run([*QUIET, (103.0, 110.0, 102.0, 109.0)], signal_at=(2,), params=params)

    assert trades["target_price"].iloc[0] == 105.0 + TICK + 0.5 * 7.0
    assert trades["exit_reason"].iloc[0] == "target"


# -- the loop it borrows, and what it hands it ---------------------------------------


def test_the_levels_hand_the_shared_loop_one_row_per_bar() -> None:
    frame = frame_of([*QUIET, PAD])
    data = dataset_for(HAND_BUILT, frame)
    levels = squeeze_levels(data, HAND_BUILT)

    np.testing.assert_array_equal(levels.session_id, np.arange(len(data)))
    np.testing.assert_array_equal(levels.high, data.window_high(WINDOW))
    np.testing.assert_array_equal(levels.low, data.window_low(WINDOW))
    assert levels.armed.tolist() == [False, False, True, True]
    assert levels.atr is openingrange.NO_ATR, "no ATR unless the ATR stop reads it"


def test_the_output_bound_counts_the_bars_that_could_fill() -> None:
    """A squeeze holds for many bars and breaks on few, so the signal count is the wrong bound."""
    rows = [*QUIET, (103.0, 104.5, 102.0, 104.0), (104.0, 105.0, 103.5, 104.5), (104.0, 104.5, 99.5, 100.0)]
    data = dataset_for(HAND_BUILT, frame_of(rows))
    levels = squeeze_levels(data, HAND_BUILT)
    signal = np.ones(len(data), dtype=np.bool_)

    # Bar 4 reaches bar 3's window high of 104.5, and no other bar reaches the high before it.
    assert entry_bound(data, levels, signal, LONG) == 1
    # Bar 5 falls to bar 4's window low of 100.0, and no other bar reaches the low before it.
    assert entry_bound(data, levels, signal, SHORT) == 1
    assert entry_bound(data, levels, np.zeros(len(data), dtype=np.bool_), LONG) == 0


# -- the squeeze itself, on ranks stated rather than reverse-engineered ---------------


def with_ranks(params: SqueezeBreakoutParams, ranks: Sequence[float]) -> context.Dataset:
    """Build a dataset whose squeeze series is exactly ``ranks``, one per bar."""
    stated = np.asarray(ranks, dtype=np.float64)
    data = dataset_for(params, frame_of([QUIET[0]] * stated.size))
    data.compressions = compression.CompressionGrid(
        keys=(params.squeeze_key,),
        width=np.zeros((1, stated.size)),
        rank=stated[np.newaxis, :],
    )

    return data


def test_the_squeeze_is_a_rank_strictly_below_its_threshold() -> None:
    params = replace(HAND_BUILT, squeeze_below=0.1)
    data = with_ranks(params, [np.nan, 0.05, 0.1, 0.0999, 0.5])

    assert squeeze_signal(data, params).tolist() == [False, True, False, True, False]


def test_a_threshold_of_one_admits_all_but_the_widest_bar_of_its_baseline() -> None:
    params = replace(HAND_BUILT, squeeze_below=1.0)
    data = with_ranks(params, [0.0, 0.5, 0.999, 1.0])

    assert squeeze_signal(data, params).tolist() == [True, True, True, False]


def test_min_squeeze_bars_asks_for_an_unbroken_run_ending_at_the_signal_bar() -> None:
    params = replace(HAND_BUILT, squeeze_below=0.1, min_squeeze_bars=3)
    data = with_ranks(params, [0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0])

    assert squeeze_signal(data, params).tolist() == [False, False, False, False, False, True, True]


def test_the_shared_compression_filter_narrows_the_squeeze_rather_than_replacing_it() -> None:
    """The filter is a second condition; reading the same series it can only take bars away."""
    params = replace(
        HAND_BUILT,
        squeeze_below=0.5,
        compression_filter=Compression.COMPRESSED.bit,
        compression_period=WINDOW,
        compression_compressed_below=0.1,
    )
    data = with_ranks(params, [0.05, 0.3, 0.6])

    assert params.compression_key == params.squeeze_key, "the test needs both to read one row"
    assert squeeze_signal(data, params).tolist() == [True, False, False]


def test_the_filter_narrows_a_copy_of_the_squeeze_and_leaves_the_dataset_s_gate_as_it_was() -> None:
    """The dataset hands every reader one shared gate, so narrowing it in place would leak into the next."""
    params = replace(
        HAND_BUILT,
        squeeze_below=0.5,
        compression_filter=Compression.COMPRESSED.bit,
        compression_period=WINDOW,
        compression_compressed_below=0.1,
    )
    data = with_ranks(params, [0.05, 0.3, 0.6])
    squeezed = data.compression_gate(params.squeeze_key, Compression.COMPRESSED.bit, 0.5, NO_UPPER_CUT)

    assert squeeze_signal(data, params).tolist() == [True, False, False]
    assert squeezed.tolist() == [True, True, False]


# -- the latched squeeze: when a latch opens and what ends it -------------------------


def latches(
    squeezed: Sequence[bool],
    close: Sequence[float],
    *,
    latch_bars: int = 3,
    direction: float = LONG,
    force_flat: Sequence[bool] | None = None,
    window_low: Sequence[float] | None = None,
) -> tuple[list[bool], list[int]]:
    """Scan stated bars for latches over a window of 98 to 105 unless told otherwise."""
    n = len(squeezed)
    submits, rows = scan_latches(
        np.asarray(squeezed, dtype=np.bool_),
        np.full(n, 105.0),
        np.full(n, 98.0) if window_low is None else np.asarray(window_low, dtype=np.float64),
        np.asarray(close, dtype=np.float64),
        np.zeros(n, dtype=np.bool_) if force_flat is None else np.asarray(force_flat, dtype=np.bool_),
        latch_bars,
        direction,
    )

    return submits.tolist(), rows.tolist()


def test_a_latch_opens_on_the_first_bar_the_squeeze_no_longer_holds_and_lasts_its_count() -> None:
    submits, rows = latches([False, True, True, False, False, False, False], [100.0] * 7)

    assert submits == [False, False, False, True, True, True, False], "never while squeezed"
    assert rows == [0, 1, 2, 3, 3, 3, 6], "a latched bar reads its release's row"


def test_the_squeeze_holding_again_ends_the_latch_and_its_next_release_opens_another() -> None:
    submits, rows = latches([True, False, False, True, False, False, False], [100.0] * 7, latch_bars=5)

    assert submits == [False, True, True, False, True, True, True]
    assert rows == [0, 1, 1, 3, 4, 4, 4]


def test_a_close_beyond_the_frozen_window_s_other_side_ends_the_latch() -> None:
    """The window low falls to 90 after the release; the latch still reads the frozen 98."""
    falling = [98.0, 98.0, 90.0, 90.0, 90.0]

    submits, _ = latches(
        [True, False, False, False, False], [100.0, 100.0, 95.0, 100.0, 100.0], window_low=falling
    )
    assert submits == [False, True, False, False, False]

    submits, _ = latches(
        [True, False, False, False, False], [100.0, 100.0, 98.0, 100.0, 100.0], window_low=falling
    )
    assert submits == [False, True, True, True, False], "a close on the low is not beyond it"


def test_the_short_side_s_other_side_is_the_frozen_high() -> None:
    squeezed = [True, False, False, False]

    assert latches(squeezed, [100.0, 100.0, 105.5, 100.0], direction=SHORT)[0] == [False, True, False, False]
    assert latches(squeezed, [100.0, 100.0, 105.0, 100.0], direction=SHORT)[0] == [False, True, True, True]
    assert latches(squeezed, [100.0, 100.0, 97.5, 100.0], direction=SHORT)[0] == [False, True, True, True]


def test_a_release_closing_beyond_the_other_side_opens_nothing() -> None:
    assert latches([True, False, False, False], [100.0, 97.0, 100.0, 100.0])[0] == [False] * 4


def test_the_force_flat_bar_ends_the_latch_and_the_next_session_opens_none() -> None:
    submits, _ = latches(
        [True, False, False, False, False],
        [100.0] * 5,
        latch_bars=4,
        force_flat=[False, False, True, False, False],
    )

    assert submits == [False, True, False, False, False]


def test_a_squeeze_held_through_the_session_close_releases_on_the_next_session_s_first_bar() -> None:
    """The window reads back across the boundary, so the latch is frozen at the last session's close."""
    submits, rows = latches(
        [False, True, True, False, False],
        [100.0] * 5,
        force_flat=[False, False, True, False, False],
    )

    assert submits == [False, False, False, True, True]
    assert rows == [0, 1, 2, 3, 3]


# -- the latched squeeze, through the shared loop -------------------------------------

LATCHED = replace(HAND_BUILT, latch_bars=3)
"""The hand-built rule set with a three-close latch."""

RELEASE = (103.0, 104.0, 102.0, 103.5)
"""A bar ending the squeeze inside the window: its own window is 99 to 104, the frozen one 98 to 105."""


def squeezed_on(
    params: SqueezeBreakoutParams, rows: Sequence[Row], squeezed_at: Iterable[int]
) -> context.Dataset:
    """Build a dataset over hand-written rows whose squeeze holds on ``squeezed_at`` alone."""
    frame = frame_of([*rows, PAD])
    ranks = np.full(len(frame), 0.5)
    ranks[list(squeezed_at)] = 0.0
    data = dataset_for(params, frame)
    data.compressions = compression.CompressionGrid(
        keys=(params.squeeze_key,),
        width=np.zeros((1, len(frame))),
        rank=ranks[np.newaxis, :],
    )

    return data


def test_the_latched_order_rests_beyond_the_window_frozen_at_the_last_squeezed_bar() -> None:
    data = squeezed_on(LATCHED, [*QUIET, RELEASE, (104.0, 106.0, 103.5, 105.8)], squeezed_at=(2,))
    trades = run_squeeze(data, LATCHED, MNQ)

    assert data.window_high(WINDOW)[3] == 104.0, "the release bar's own window would rest lower"
    assert len(trades) == 1
    assert trades["entry_bar"].iloc[0] == 4
    assert trades["entry_price"].iloc[0] == 105.0 + TICK
    assert trades["initial_stop"].iloc[0] == 98.0 - 2 * TICK


def test_the_latch_trades_a_re_break_and_never_the_bar_that_released_it() -> None:
    """The unlatched rule trades the breaking bar; the latch can only rest once price is back inside."""
    rows = [*QUIET, (103.0, 108.0, 102.0, 107.0), PAD, (104.0, 106.0, 104.0, 105.5)]

    unlatched = run_squeeze(squeezed_on(HAND_BUILT, rows, squeezed_at=(2,)), HAND_BUILT, MNQ)
    latched = run_squeeze(squeezed_on(LATCHED, rows, squeezed_at=(2,)), LATCHED, MNQ)

    assert unlatched["entry_bar"].tolist() == [3]
    assert latched["entry_bar"].tolist() == [5]
    assert latched["entry_price"].iloc[0] == 105.0 + TICK


def test_the_latch_rests_for_its_count_of_closes_and_no_longer() -> None:
    rows = [*QUIET, RELEASE, (103.5, 104.5, 103.0, 104.0), PAD, (104.0, 106.0, 104.0, 105.5)]

    three = run_squeeze(squeezed_on(LATCHED, rows, squeezed_at=(2,)), LATCHED, MNQ)
    two_params = replace(LATCHED, latch_bars=2)
    two = run_squeeze(squeezed_on(two_params, rows, squeezed_at=(2,)), two_params, MNQ)

    assert three["entry_bar"].tolist() == [6], "submitted at the release and the two closes after"
    assert len(two) == 0


def test_a_fill_ends_the_latch_so_a_stopped_trade_is_not_taken_again() -> None:
    """Bar 5 stops the trade out and closes under the trigger; bar 6 would refill an order never sent."""
    params = replace(LATCHED, latch_bars=12, stop_mode=ORB_STOP_FRACTION, stop_range_fraction=0.1)
    rows = [
        *QUIET,
        RELEASE,
        (104.5, 106.0, 104.5, 105.8),
        (105.5, 105.6, 103.5, 104.0),
        (104.0, 106.0, 104.0, 105.5),
    ]
    data = squeezed_on(params, rows, squeezed_at=(2,))
    trades = run_squeeze(data, params, MNQ)

    assert squeeze_levels(data, params).session_id[3:7].tolist() == [3, 3, 3, 3]
    assert trades["exit_reason"].tolist() == ["stop"]
    assert trades["exit_bar"].iloc[0] == 5


def test_the_short_side_latch_rests_a_tick_below_the_frozen_low() -> None:
    params = replace(LATCHED, direction=SHORT)
    rows = [*QUIET, (101.0, 102.0, 99.5, 100.0), (100.0, 100.5, 97.0, 97.5)]
    trades = run_squeeze(squeezed_on(params, rows, squeezed_at=(2,)), params, MNQ)

    assert len(trades) == 1
    assert trades["entry_price"].iloc[0] == 98.0 - TICK, "the release bar's own window low is 99"
    assert trades["initial_stop"].iloc[0] == 105.0 + 2 * TICK


def test_the_latched_levels_freeze_only_each_release_s_own_row() -> None:
    data = squeezed_on(LATCHED, [*QUIET, RELEASE, RELEASE, RELEASE], squeezed_at=(2,))
    levels = squeeze_levels(data, LATCHED)
    high = data.window_high(WINDOW)

    assert levels.session_id.tolist() == [0, 1, 2, 3, 3, 3, 6]
    assert levels.high[3] == high[2]
    assert levels.low[3] == data.window_low(WINDOW)[2]
    np.testing.assert_array_equal(np.delete(levels.high, 3), np.delete(high, 3))
    assert levels.armed.tolist() == [False, False, True, True, True, True, True]


# -- end to end over random-walk sessions ---------------------------------------------


def session_bars(days: int = 6, seed: int = 11) -> pd.DataFrame:
    """Build random-walk minute bars over whole sessions, long enough for a 250-bar baseline."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    index = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0.0, 0.3, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0.0, 0.3, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=index,
    )
    info = sessions.classify(index)
    frame["trading_day"] = info.trading_day

    return frame[info.in_session]


WALKED = SqueezeBreakoutParams(bars_required_to_trade=0, squeeze_below=0.25)


def test_every_entry_follows_a_squeezed_bar_and_fills_beyond_that_bar_s_window() -> None:
    data = dataset_for(WALKED, session_bars())
    trades = run_squeeze(data, WALKED, NQ)
    assert len(trades), "the fixture produced no trades; the test proves nothing"

    signal = squeeze_signal(data, WALKED)
    signal_bars = trades["entry_bar"].to_numpy().astype(int) - 1
    assert signal[signal_bars].all()
    trigger = data.window_high(WALKED.squeeze_period)[signal_bars] + WALKED.entry_offset_ticks * NQ.tick_size
    assert (trades["entry_price"].to_numpy() >= trigger).all()


def test_the_output_bound_covers_every_fill_and_sits_far_below_the_signal() -> None:
    data = dataset_for(WALKED, session_bars())
    signal = squeeze_signal(data, WALKED)
    bound = entry_bound(data, squeeze_levels(data, WALKED), signal, WALKED.direction)
    entries = run_squeeze(data, WALKED, NQ)["trade_id"].nunique()

    assert entries <= bound
    assert bound < int(signal.sum()) / 2


def test_the_squeeze_on_a_prefix_is_the_prefix_of_the_squeeze() -> None:
    """No bar's squeeze reads a later bar: truncating the series leaves every earlier answer alone."""
    bars = session_bars()
    whole = squeeze_signal(dataset_for(WALKED, bars), WALKED)
    cut = len(bars) * 2 // 3
    prefix = squeeze_signal(dataset_for(WALKED, bars.iloc[:cut]), WALKED)

    assert whole[:cut].sum() > 0, "the prefix holds no squeeze; the test proves nothing"
    np.testing.assert_array_equal(prefix, whole[:cut])


def test_nothing_the_entry_reads_comes_from_a_bar_after_the_signal() -> None:
    """Rewriting every bar after the first entry must not move that entry's own bracket."""
    bars = session_bars()
    first = run_squeeze(dataset_for(WALKED, bars), WALKED, NQ).iloc[0]

    tampered = bars.copy()
    after = int(first["entry_bar"]) + 1
    for column in ("open", "high", "close"):
        tampered.iloc[after:, list(tampered.columns).index(column)] += 50.0
    tampered.iloc[after:, list(tampered.columns).index("low")] -= 50.0
    again = run_squeeze(dataset_for(WALKED, tampered), WALKED, NQ).iloc[0]

    for column in ("entry_bar", "entry_price", "initial_stop", "target_price", "risk_points"):
        assert again[column] == pytest.approx(first[column]), column


WALKED_LATCHED = replace(WALKED, latch_bars=6)


def test_every_latched_entry_follows_a_release_and_fills_beyond_its_frozen_window() -> None:
    data = dataset_for(WALKED_LATCHED, session_bars())
    trades = run_squeeze(data, WALKED_LATCHED, NQ)
    assert len(trades), "the fixture produced no latched trades; the test proves nothing"

    latch = latch_of(data, WALKED_LATCHED)
    squeezed = squeezed_bars(data, WALKED_LATCHED)
    signal_bars = trades.drop_duplicates("trade_id")["entry_bar"].to_numpy().astype(int) - 1
    releases = latch.row_of_bar[signal_bars]
    assert latch.submits[signal_bars].all()
    assert squeezed[releases - 1].all()
    assert not squeezed[signal_bars].any(), "a latched order is never submitted while squeezed"
    assert len(set(releases)) == len(releases), "one trade per release"

    frozen_high = data.window_high(WALKED_LATCHED.squeeze_period)[releases - 1]
    entries = trades.drop_duplicates("trade_id")["entry_price"].to_numpy()
    assert (entries >= frozen_high + WALKED_LATCHED.entry_offset_ticks * NQ.tick_size).all()


def test_the_filters_narrow_a_copy_of_the_latch_and_leave_the_levels_every_release() -> None:
    """The filters narrow the signal in place, and the levels find each release in the latch's own bars."""
    overnight = timeofday.phases_mask([timeofday.SessionPhase.OVERNIGHT])
    params = replace(WALKED_LATCHED, phase_filter=overnight)
    data = dataset_for(params, session_bars())
    latch = latch_of(data, params)
    submits = latch.submits.copy()

    signal = squeeze_signal(data, params, latch)
    assert 0 < signal.sum() < submits.sum(), "the filter removed no latched bar; the test proves nothing"
    np.testing.assert_array_equal(latch.submits, submits)
    np.testing.assert_array_equal(squeeze_levels(data, params, latch).high, squeeze_levels(data, params).high)


def test_the_output_bound_covers_every_latched_fill() -> None:
    data = dataset_for(WALKED_LATCHED, session_bars())
    signal = squeeze_signal(data, WALKED_LATCHED)
    bound = entry_bound(data, squeeze_levels(data, WALKED_LATCHED), signal, WALKED_LATCHED.direction)

    assert 0 < run_squeeze(data, WALKED_LATCHED, NQ)["trade_id"].nunique() <= bound


def test_the_latch_on_a_prefix_is_the_prefix_of_the_latch() -> None:
    bars = session_bars()
    whole = squeeze_signal(dataset_for(WALKED_LATCHED, bars), WALKED_LATCHED)
    cut = len(bars) * 2 // 3
    prefix = squeeze_signal(dataset_for(WALKED_LATCHED, bars.iloc[:cut]), WALKED_LATCHED)

    assert whole[:cut].sum() > 0, "the prefix holds no latch; the test proves nothing"
    np.testing.assert_array_equal(prefix, whole[:cut])


def test_nothing_the_latched_entry_reads_comes_from_a_bar_after_the_signal() -> None:
    bars = session_bars()
    first = run_squeeze(dataset_for(WALKED_LATCHED, bars), WALKED_LATCHED, NQ).iloc[0]

    tampered = bars.copy()
    after = int(first["entry_bar"]) + 1
    for column in ("open", "high", "close"):
        tampered.iloc[after:, list(tampered.columns).index(column)] += 50.0
    tampered.iloc[after:, list(tampered.columns).index("low")] -= 50.0
    again = run_squeeze(dataset_for(WALKED_LATCHED, tampered), WALKED_LATCHED, NQ).iloc[0]

    for column in ("entry_bar", "entry_price", "initial_stop", "target_price", "risk_points"):
        assert again[column] == pytest.approx(first[column]), column


def test_the_injected_latch_reproduces_the_latched_run_and_the_null_draws_over_it() -> None:
    data = dataset_for(WALKED_LATCHED, session_bars())

    pd.testing.assert_frame_equal(
        run_squeeze(data, WALKED_LATCHED, NQ),
        run_squeeze(data, WALKED_LATCHED, NQ, signal=squeeze_signal(data, WALKED_LATCHED)),
    )
    null = randomentry.null_summaries(data, WALKED_LATCHED, instrument=NQ, iterations=6)
    assert null["profit_factor"].nunique() > 1, "every draw agreed, so nothing was randomised"  # noqa: PD101 - a NaN draw is ignored, which an equality check would not do


def test_a_grid_sweeps_end_to_end_through_the_registry() -> None:
    bars = session_bars()
    grid = sweep.Grid.of(
        WALKED,
        squeeze_form=[int(CompressionForm.BANDWIDTH), int(CompressionForm.RANGE_TO_ATR)],
        direction=[LONG, SHORT],
    )
    spec = grid.required_context()
    assert {k.form for k in spec.compression_keys} == set(CompressionForm)
    assert spec.window_range_periods == (WALKED.squeeze_period,)
    assert spec.atr_periods == (), "no ATR unless a combination selects the ATR stop"

    results, _ = sweep.sweep(bars, grid, NQ, data=context.prepare(bars, spec, bar_minutes=1))

    assert len(results) == 4
    assert results["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    assert "target_width_multiples" not in results.columns, "a tuple is not a swept axis"


def test_the_atr_stop_asks_for_the_atr_and_the_opposite_stop_does_not() -> None:
    atr_grid = sweep.Grid.of(replace(WALKED, stop_mode=ORB_STOP_ATR, atr_period=7))
    opposite = sweep.Grid.of(replace(WALKED, stop_mode=ORB_STOP_OPPOSITE, atr_period=7))

    assert atr_grid.required_context().atr_periods == (7,)
    assert opposite.required_context().atr_periods == ()


def test_a_compression_filter_builds_its_own_series_beside_the_squeeze() -> None:
    filtered = replace(
        WALKED,
        compression_filter=Compression.EXPANDED.bit,
        compression_form=int(CompressionForm.RANGE_TO_ATR),
    )

    assert sweep.Grid.of(WALKED).required_context().compression_keys == (WALKED.squeeze_key,)
    assert sweep.Grid.of(filtered).required_context().compression_keys == tuple(
        sorted({filtered.squeeze_key, filtered.compression_key}),
    )


def test_the_archetype_is_registered_as_tier_1_only() -> None:
    """There is no NinjaScript, so it must not claim a reconciliation it does not have."""
    assert archetypes.SQUEEZEBREAKOUT.tier2 is archetypes.Tier2Status.TIER1_ONLY
    assert archetypes.for_params(SqueezeBreakoutParams()) is archetypes.SQUEEZEBREAKOUT


# -- the null, which a squeeze leaves room to draw ------------------------------------


def test_the_injected_signal_reproduces_the_archetype_s_own_run() -> None:
    """The null calls this run with a drawn signal, so feeding the real one back must change nothing."""
    data = dataset_for(WALKED, session_bars())

    pd.testing.assert_frame_equal(
        run_squeeze(data, WALKED, NQ),
        run_squeeze(data, WALKED, NQ, signal=squeeze_signal(data, WALKED)),
    )


def test_the_matched_random_null_draws_over_bars() -> None:
    """Unlike OpeningRange's level, a squeeze is a state most bars are not in, so the draw has room."""
    data = dataset_for(WALKED, session_bars())
    null = randomentry.null_summaries(data, WALKED, instrument=NQ, iterations=6)

    assert len(null) == 6
    assert null["profit_factor"].nunique() > 1, "every draw agreed, so nothing was randomised"  # noqa: PD101 - a NaN draw is ignored, which an equality check would not do


def test_a_level_draw_is_refused_because_there_is_no_session_range() -> None:
    with pytest.raises(randomentry.RandomEntryError, match="no session range"):
        randomentry._range_key_for(
            WALKED,
            archetypes.SQUEEZEBREAKOUT,
            randomentry.OVER_LEVELS,
        )


# -- the parameter class's own guards -----------------------------------------------


def test_a_window_traded_both_ways_cannot_be_asked_for() -> None:
    with pytest.raises(ValueError, match="not expressible in NT8's managed approach"):
        SqueezeBreakoutParams(direction=0.0)


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"squeeze_form": 9}, compression.CompressionError, "unknown compression form"),
        ({"squeeze_period": 1}, compression.CompressionError, "must span >= 2 bars"),
        ({"squeeze_baseline_bars": 5}, compression.CompressionError, "must span >= 20 bars"),
        ({"squeeze_below": 0.0}, ValueError, r"squeeze_below must lie in \(0, 1\]"),
        ({"squeeze_below": 1.5}, ValueError, r"squeeze_below must lie in \(0, 1\]"),
        ({"min_squeeze_bars": 0}, ValueError, "min_squeeze_bars must be >= 1"),
        ({"entry_offset_ticks": -1}, ValueError, "entry_offset_ticks must be >= 0"),
        ({"latch_bars": -1}, ValueError, "latch_bars must be >= 0"),
        ({"stop_mode": 9}, ValueError, "unknown stop_mode"),
        ({"target_mode": 9}, ValueError, "unknown target_mode"),
        ({"order_quantity": 1}, ValueError, "cannot fill 4 legs"),
        ({"atr_period": 0}, ValueError, "atr_period must be >= 1"),
        ({"stop_offset_ticks": -1}, ValueError, "stop_offset_ticks must be >= 0"),
        ({"stop_range_fraction": 0.0}, ValueError, "stop_range_fraction must be > 0"),
        ({"min_bracket_dollars": -1.0}, ValueError, "min_bracket_dollars must be >= 0"),
        ({"max_hold_bars": -1}, ValueError, "max_hold_bars must be >= 0"),
        ({"compression_filter": 0}, compression.CompressionError, "admits no state"),
    ],
)
def test_an_impossible_rule_set_is_refused_by_name(
    kwargs: dict[str, object], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        SqueezeBreakoutParams(**kwargs)  # type: ignore[arg-type]  # each caller passes a field's own type


def test_the_leg_split_follows_the_selected_target_ladder() -> None:
    assert SqueezeBreakoutParams(order_quantity=4).leg_quantities == (1, 1, 1, 1)
    assert SqueezeBreakoutParams(order_quantity=5, target_mode=ORB_TARGET_WIDTH).leg_quantities == (2, 3)


def test_the_squeeze_key_is_the_form_and_both_windows() -> None:
    params = SqueezeBreakoutParams(
        squeeze_form=int(CompressionForm.RANGE_TO_ATR),
        squeeze_period=40,
        squeeze_baseline_bars=500,
    )

    assert params.squeeze_key == compression.key(CompressionForm.RANGE_TO_ATR, 40, 500)
    assert params.as_dict()["target_r_multiples"] == list(params.target_r_multiples)
