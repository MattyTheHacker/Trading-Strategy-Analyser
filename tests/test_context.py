"""Tests for the market context and what ``prepare`` is asked to build.

The rule M17.3 introduces is that a :class:`Dataset` holds what some archetype *declared*,
not everything anyone might want. So the tests that matter are the two failure modes that
creates: a series being missing when it should be there, and a series being silently
absent when something reads it.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import conditions, context, sessions, sweep
from nqbt.context import ContextError, ContextSpec
from nqbt.sim.types import DeadCatParams, PullBackAndGoParams


def bars(n: int = 800, seed: int = 3) -> pd.DataFrame:
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


# -- the spec decides what exists ---------------------------------------------


def test_vwap_is_absent_when_nothing_asked_for_it() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_vwap=False))
    assert data.vwap is None
    assert data.below_vwap is None
    assert data.above_vwap is None


def test_vwap_is_present_when_the_spec_asks() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_vwap=True))
    assert data.vwap_values().shape == (len(data),)
    assert data.vwap_gate(above=True).dtype == np.bool_


def test_only_the_declared_kinds_get_a_grid() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    assert set(data.mas) == {"ema"}, "an sma grid was built that nobody asked for"

    both = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,), sma=(60,))))
    assert set(both.mas) == {"ema", "sma"}


def test_grids_are_addressed_by_kind_and_period_together() -> None:
    """The period alone is not the key: two kinds share it and answer differently."""
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,), sma=(21,))))
    ema21 = data.ma_gate("ema", 21, above=False)
    sma21 = data.ma_gate("sma", 21, above=False)
    assert ema21.shape == sma21.shape
    assert not np.array_equal(ema21, sma21), "same period, different kind, same answer"


def test_a_declared_kind_reaches_the_dataset_whichever_kind_it_is() -> None:
    keys = conditions.ma_keys(hma=(20,), wma=(20,))
    data = context.prepare(bars(), ContextSpec(ma_keys=keys, needs_ma_values=True))
    assert set(data.mas) == {"hma", "wma"}
    assert not np.array_equal(data.ma_values("hma", 20), data.ma_values("wma", 20))


# -- reading something that was not built says so ------------------------------


def test_reading_an_undeclared_kind_names_what_was_built() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    with pytest.raises(ContextError, match=r"no sma grid.*\['ema'\]"):
        data.ma_gate("sma", 21, above=False)


def test_reading_undeclared_vwap_points_at_the_spec() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_vwap=False))
    with pytest.raises(ContextError, match="needs_vwap"):
        data.vwap_gate(above=False)
    with pytest.raises(ContextError, match="needs_vwap"):
        data.vwap_values()


def test_a_period_outside_the_grid_still_raises_rather_than_returning_a_wrong_row() -> None:
    """Pre-existing guarantee, re-pinned through the new accessor."""
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    with pytest.raises(KeyError, match="ema\\(50\\)"):
        data.ma_gate("ema", 50, above=False)


# -- above is not the complement of below --------------------------------------


def test_the_two_gates_overlap_at_equality_rather_than_partitioning() -> None:
    """Each NinjaScript treats its own boundary as a pass; see docs/nt8-fidelity.md."""
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    below = data.ma_gate("ema", 21, above=False)
    above = data.ma_gate("ema", 21, above=True)
    assert not np.array_equal(above, ~below) or (below & above).any(), (
        "if these ever partition exactly, the equality boundary has been lost"
    )


# -- the spec comes from the grid, not from a guess ----------------------------


def test_a_deadcatbounce_sweep_gets_no_vwap_because_its_default_is_off() -> None:
    grid = sweep.Grid.of(DeadCatParams(), ema_period=[9, 21])
    assert grid.required_context().needs_vwap is False
    assert sweep.prepare_for(bars(), grid).vwap is None


def test_sweeping_the_vwap_toggle_makes_prepare_build_it() -> None:
    grid = sweep.Grid.of(DeadCatParams(), use_vwap=[True, False])
    data = sweep.prepare_for(bars(), grid)
    assert data.vwap is not None, "a combination switches VWAP on and would have crashed"
    # And the sweep runs, which is the real check that the spec covers the grid.
    results, _ = sweep.sweep(bars(), grid, data=data)
    assert len(results) == 2


def test_pullbackandgo_declares_vwap_off_but_reads_the_above_gates() -> None:
    grid = sweep.Grid.of(PullBackAndGoParams(bars_required_to_trade=20))
    data = sweep.prepare_for(bars(), grid)
    assert data.vwap is None
    assert set(data.mas) == {"ema", "sma"}
    results, _ = sweep.sweep(bars(), grid, data=data)
    assert len(results) == 1


def test_specs_union_so_several_archetypes_can_share_one_dataset() -> None:
    a = sweep.Grid.of(DeadCatParams()).required_context()
    b = sweep.Grid.of(PullBackAndGoParams()).required_context()
    both = a | b
    assert set(both.ma_keys) == set(a.ma_keys) | set(b.ma_keys)
    # One dataset now serves both, which is what M17.4 will lean on.
    data = context.prepare(bars(), both)
    for grid_spec in (a, b):
        for kind, period in grid_spec.ma_keys:
            assert data.ma_gate(kind, period, above=True).shape == (len(data),)


def test_periods_by_kind_groups_the_keys_into_one_grid_call_each() -> None:
    spec = ContextSpec(ma_keys=conditions.ma_keys(sma=(175, 60), ema=(21,)))
    assert spec.periods_by_kind() == {"ema": (21,), "sma": (60, 175)}
    assert ContextSpec().periods_by_kind() == {}, "a kind with no periods is not a grid"


def test_periods_by_kind_sorts_and_deduplicates_whatever_order_the_keys_arrived_in() -> None:
    """The keys every builder produces are sorted; a spec constructed by hand need not be."""
    unsorted = (
        conditions.ma_key("sma", 175),
        conditions.ma_key("ema", 21),
        conditions.ma_key("sma", 60),
        conditions.ma_key("sma", 175),
    )
    assert ContextSpec(ma_keys=unsorted).periods_by_kind() == {"ema": (21,), "sma": (60, 175)}


# -- the size claim ------------------------------------------------------------


def test_dropping_an_undeclared_series_actually_shrinks_the_dataset() -> None:
    """The whole point: this is per-worker memory once joblib memmaps it."""
    frame = bars(4000)
    keys = conditions.ma_keys(ema=(21,), sma=(60, 175))
    with_vwap = context.prepare(frame, ContextSpec(ma_keys=keys, needs_vwap=True))
    without = context.prepare(frame, ContextSpec(ma_keys=keys, needs_vwap=False))
    assert without.nbytes < with_vwap.nbytes
    # VWAP is one float64 array plus two boolean ones, over every bar.
    assert with_vwap.nbytes - without.nbytes == 10 * len(frame)


def test_slim_keeps_the_declared_arrays_shared_rather_than_copied() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_vwap=True))
    lean = data.slim()
    assert list(lean.bars.columns) == []
    assert lean.close is data.close
    assert lean.mas["ema"].below is data.mas["ema"].below
    assert lean.vwap is data.vwap


# -- ATR and raw moving-average values (M18) ----------------------------------


def test_atr_is_absent_unless_the_spec_asks_for_it() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    assert data.atrs == {}
    with pytest.raises(ContextError, match="Add it to the archetype's ContextSpec"):
        data.atr_values(14)


def test_atr_is_built_for_exactly_the_declared_periods() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), atr_periods=(14, 20)))
    assert sorted(data.atrs) == [14, 20]
    assert data.atr_values(14).shape == (len(data),)
    with pytest.raises(ContextError, match=r"no ATR\(9\)"):
        data.atr_values(9)


def test_needs_ma_values_keeps_the_raw_averages() -> None:
    """A rule comparing two averages to each other cannot be answered by a boolean gate."""
    gates_only = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(9, 21))))
    with pytest.raises(ValueError, match="keep_values=True"):
        gates_only.ma_values("ema", 9)

    with_values = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(9, 21)), needs_ma_values=True))
    assert with_values.ma_values("ema", 9).shape == (len(with_values),)


def test_the_union_of_two_specs_carries_the_new_fields() -> None:
    merged = ContextSpec(
        ma_keys=conditions.ma_keys(ema=(9,)),
        atr_periods=(14,),
        needs_ma_values=True,
    ) | ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), atr_periods=(20,), needs_vwap=True)
    assert merged.ma_keys == conditions.ma_keys(ema=(9, 21))
    assert merged.atr_periods == (14, 20)
    assert merged.needs_vwap
    assert merged.needs_ma_values


def test_the_session_clock_is_absent_unless_the_spec_asks_for_it() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    assert data.seconds_to_session_end is None
    with pytest.raises(ContextError, match="needs_session_clock"):
        data.session_end_gate(60)


def test_the_session_clock_gate_admits_a_bar_strictly_outside_the_window() -> None:
    """``(ActualSessionEnd - Now).TotalHours <= 1`` returns, so an hour exactly is blocked."""
    idx = pd.DatetimeIndex(
        # 15:59, 16:00 and 17:00 ET. The last one is the session end the other two count to.
        pd.to_datetime(["2024-01-16 20:59:00", "2024-01-16 21:00:00", "2024-01-16 22:00:00"], utc=True),
    )
    frame = bars(len(idx)).set_index(idx)
    data = context.prepare(frame, ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_session_clock=True))

    assert list(data.seconds_to_session_end) == [3660.0, 3600.0, 0.0]
    assert list(data.session_end_gate(60)) == [True, False, False]
    assert list(data.session_end_gate(61)) == [False, False, False]


def test_the_no_entry_window_follows_a_holiday_early_close_too() -> None:
    """One session end feeds the window and the flatten, so neither can miss a half-day."""
    idx = pd.DatetimeIndex(
        # MLK 2024: 11:59, 12:00 and 13:00 ET, and the exchange stops at the last of them.
        pd.to_datetime(["2024-01-15 16:59:00", "2024-01-15 17:00:00", "2024-01-15 18:00:00"], utc=True),
    )
    frame = bars(len(idx)).set_index(idx)
    data = context.prepare(frame, ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), needs_session_clock=True))

    assert list(data.seconds_to_session_end) == [3660.0, 3600.0, 0.0]
    assert list(data.session_end_gate(60)) == [True, False, False]
    assert list(data.force_flat) == [False, False, True]


def test_the_union_of_two_specs_carries_the_session_clock() -> None:
    assert (ContextSpec() | ContextSpec(needs_session_clock=True)).needs_session_clock
    assert (ContextSpec(needs_session_clock=True) | ContextSpec()).needs_session_clock
    assert not (ContextSpec() | ContextSpec()).needs_session_clock


def test_the_band_grid_is_absent_unless_the_spec_asks_for_it() -> None:
    data = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    assert data.band is None
    for read in (data.band_basis, data.band_stddev, data.band_stretch):
        with pytest.raises(ContextError, match="band_periods"):
            read(20)


def test_the_band_grid_is_built_for_exactly_the_declared_periods() -> None:
    data = context.prepare(bars(), ContextSpec(band_periods=(20, 50)))
    assert data.band is not None
    assert data.band.periods.tolist() == [20, 50]
    assert data.band_stretch(20).shape == (len(data),)
    # No moving-average grid was asked for, so none exists -- the band carries its own basis.
    assert data.mas == {}
    with pytest.raises(KeyError, match="band period 30 is not in this grid"):
        data.band_basis(30)


def test_the_union_of_two_specs_carries_the_band_periods() -> None:
    merged = ContextSpec(band_periods=(20,)) | ContextSpec(band_periods=(50,), atr_periods=(14,))
    assert merged.band_periods == (20, 50)
    assert merged.atr_periods == (14,)


def test_the_band_grid_counts_towards_what_a_worker_is_handed() -> None:
    without = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,))))
    with_band = context.prepare(bars(), ContextSpec(ma_keys=conditions.ma_keys(ema=(21,)), band_periods=(20,)))
    assert with_band.nbytes == without.nbytes + with_band.band.nbytes
