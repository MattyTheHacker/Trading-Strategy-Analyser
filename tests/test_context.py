"""Tests for the market context and what ``prepare`` is asked to build.

The rule M17.3 introduces is that a :class:`Dataset` holds what some archetype *declared*,
not everything anyone might want. So the tests that matter are the two failure modes that
creates: a series being missing when it should be there, and a series being silently
absent when something reads it.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import context, sessions, sweep
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


def test_vwap_is_absent_when_nothing_asked_for_it():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,), needs_vwap=False))
    assert data.vwap is None
    assert data.below_vwap is None
    assert data.above_vwap is None


def test_vwap_is_present_when_the_spec_asks():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,), needs_vwap=True))
    assert data.vwap_values().shape == (len(data),)
    assert data.vwap_gate(above=True).dtype == np.bool_


def test_only_the_declared_kinds_get_a_grid():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,)))
    assert set(data.mas) == {"ema"}, "an sma grid was built that nobody asked for"

    both = context.prepare(bars(), ContextSpec(ema_periods=(21,), sma_periods=(60,)))
    assert set(both.mas) == {"ema", "sma"}


def test_grids_are_addressed_by_kind_and_period_together():
    """What #72 needs: the kind stops being fixed by a field's name."""
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,), sma_periods=(21,)))
    ema21 = data.ma_gate("ema", 21, above=False)
    sma21 = data.ma_gate("sma", 21, above=False)
    assert ema21.shape == sma21.shape
    assert not np.array_equal(ema21, sma21), "same period, different kind, same answer"


# -- reading something that was not built says so ------------------------------


def test_reading_an_undeclared_kind_names_what_was_built():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,)))
    with pytest.raises(ContextError, match=r"no sma grid.*\['ema'\]"):
        data.ma_gate("sma", 21, above=False)


def test_reading_undeclared_vwap_points_at_the_spec():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,), needs_vwap=False))
    with pytest.raises(ContextError, match="needs_vwap"):
        data.vwap_gate(above=False)
    with pytest.raises(ContextError, match="needs_vwap"):
        data.vwap_values()


def test_a_period_outside_the_grid_still_raises_rather_than_returning_a_wrong_row():
    """Pre-existing guarantee, re-pinned through the new accessor."""
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,)))
    with pytest.raises(KeyError, match="ema\\(50\\)"):
        data.ma_gate("ema", 50, above=False)


# -- above is not the complement of below --------------------------------------


def test_the_two_gates_overlap_at_equality_rather_than_partitioning():
    """Each NinjaScript treats its own boundary as a pass; see docs/nt8-fidelity.md."""
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,)))
    below = data.ma_gate("ema", 21, above=False)
    above = data.ma_gate("ema", 21, above=True)
    assert not np.array_equal(above, ~below) or (below & above).any(), (
        "if these ever partition exactly, the equality boundary has been lost"
    )


# -- the spec comes from the grid, not from a guess ----------------------------


def test_a_deadcatbounce_sweep_gets_no_vwap_because_its_default_is_off():
    grid = sweep.Grid.of(DeadCatParams(), ema_period=[9, 21])
    assert grid.required_context().needs_vwap is False
    assert sweep.prepare_for(bars(), grid).vwap is None


def test_sweeping_the_vwap_toggle_makes_prepare_build_it():
    grid = sweep.Grid.of(DeadCatParams(), use_vwap=[True, False])
    data = sweep.prepare_for(bars(), grid)
    assert data.vwap is not None, "a combination switches VWAP on and would have crashed"
    # And the sweep runs, which is the real check that the spec covers the grid.
    results, _ = sweep.sweep(bars(), grid, data=data)
    assert len(results) == 2


def test_pullbackandgo_declares_vwap_off_but_reads_the_above_gates():
    grid = sweep.Grid.of(PullBackAndGoParams(bars_required_to_trade=20))
    data = sweep.prepare_for(bars(), grid)
    assert data.vwap is None
    assert set(data.mas) == {"ema", "sma"}
    results, _ = sweep.sweep(bars(), grid, data=data)
    assert len(results) == 1


def test_specs_union_so_several_archetypes_can_share_one_dataset():
    a = sweep.Grid.of(DeadCatParams()).required_context()
    b = sweep.Grid.of(PullBackAndGoParams()).required_context()
    both = a | b
    assert set(both.ema_periods) == set(a.ema_periods) | set(b.ema_periods)
    assert set(both.sma_periods) == set(a.sma_periods) | set(b.sma_periods)
    # One dataset now serves both, which is what M17.4 will lean on.
    data = context.prepare(bars(), both)
    for grid_spec in (a, b):
        for period in grid_spec.ema_periods:
            assert data.ma_gate("ema", period, above=True).shape == (len(data),)


def test_periods_by_kind_omits_a_kind_with_no_periods():
    assert ContextSpec(ema_periods=(21,)).periods_by_kind() == {"ema": (21,)}
    assert ContextSpec().periods_by_kind() == {}


# -- the size claim ------------------------------------------------------------


def test_dropping_an_undeclared_series_actually_shrinks_the_dataset():
    """The whole point: this is per-worker memory once joblib memmaps it."""
    frame = bars(4000)
    periods = {"ema_periods": (21,), "sma_periods": (60, 175)}
    with_vwap = context.prepare(frame, ContextSpec(**periods, needs_vwap=True))
    without = context.prepare(frame, ContextSpec(**periods, needs_vwap=False))
    assert without.nbytes < with_vwap.nbytes
    # VWAP is one float64 array plus two boolean ones, over every bar.
    assert with_vwap.nbytes - without.nbytes == 10 * len(frame)


def test_slim_keeps_the_declared_arrays_shared_rather_than_copied():
    data = context.prepare(bars(), ContextSpec(ema_periods=(21,), needs_vwap=True))
    lean = data.slim()
    assert list(lean.bars.columns) == []
    assert lean.close is data.close
    assert lean.mas["ema"].below is data.mas["ema"].below
    assert lean.vwap is data.vwap
