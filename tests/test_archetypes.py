"""Tests for the archetype protocol and registry, and for the sweep reaching through it.

The point of M17 is that ``sweep.py`` stops naming ``DeadCatParams``. The test that
actually proves it is :func:`test_a_pullbackandgo_grid_sweeps_end_to_end` -- everything
else guards a way the indirection could be wrong while still passing.
"""

from dataclasses import dataclass, fields
from pickle import dumps, loads

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, sessions, sweep
from nqbt.archetypes import Archetype, ArchetypeError, ContextSpec, Tier2Status
from nqbt.instruments import NQ
from nqbt.sim.types import (
    DeadCatParams,
    EmaCrossoverParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
)

# -- the registry -------------------------------------------------------------


def test_every_archetype_is_registered() -> None:
    assert archetypes.names() == [
        "DeadCatBounce",
        "ElasticBand",
        "EmaCrossover",
        "InsideBar",
        "InsideBarTrailing",
        "OpeningRange",
        "PullBackAndGo",
    ]
    assert archetypes.get("DeadCatBounce") is archetypes.DEADCATBOUNCE
    assert archetypes.get("ElasticBand") is archetypes.ELASTICBAND
    assert archetypes.get("EmaCrossover") is archetypes.EMACROSSOVER
    assert archetypes.get("InsideBar") is archetypes.INSIDEBAR
    assert archetypes.get("InsideBarTrailing") is archetypes.INSIDEBARTRAILING
    assert archetypes.get("OpeningRange") is archetypes.OPENINGRANGE
    assert archetypes.get("PullBackAndGo") is archetypes.PULLBACKANDGO


def test_an_unknown_name_lists_the_known_ones() -> None:
    with pytest.raises(ArchetypeError, match="DeadCatBounce"):
        archetypes.get("SqueezeBreakout")


def test_registering_a_duplicate_name_is_refused() -> None:
    """``name`` is a results column, so two archetypes sharing one merge into a row group."""
    clash = Archetype(
        name="DeadCatBounce",
        params_cls=DeadCatParams,
        run=archetypes.DEADCATBOUNCE.run,
        legs=archetypes.DEADCATBOUNCE.legs,
        signal=archetypes.DEADCATBOUNCE.signal,
        tier2=Tier2Status.TIER1_ONLY,
    )
    with pytest.raises(ArchetypeError, match="already registered"):
        archetypes.register(clash)


def test_the_default_is_deadcatbounce() -> None:
    """Every stored result and captured trade log was produced with it."""
    assert archetypes.DEFAULT is archetypes.DEADCATBOUNCE


def test_for_params_infers_the_archetype_from_its_parameter_class() -> None:
    assert archetypes.for_params(DeadCatParams()) is archetypes.DEADCATBOUNCE
    assert archetypes.for_params(PullBackAndGoParams()) is archetypes.PULLBACKANDGO
    assert archetypes.for_params(EmaCrossoverParams()) is archetypes.EMACROSSOVER
    assert archetypes.for_params(InsideBarParams()) is archetypes.INSIDEBAR
    assert archetypes.for_params(InsideBarTrailingParams()) is archetypes.INSIDEBARTRAILING
    assert archetypes.for_params(OpeningRangeParams()) is archetypes.OPENINGRANGE


def test_for_params_refuses_to_guess_for_an_unregistered_class() -> None:
    @dataclass(slots=True)
    class Unknown:
        pass

    with pytest.raises(ArchetypeError, match="pass archetype="):
        archetypes.for_params(Unknown())  # type: ignore[arg-type]  # not a Params; the test's point


def test_tier2_separates_the_ported_archetypes_from_the_original() -> None:
    """``tier2`` is the column that stops a ranking mixing a measurement with an assumption.

    All four ports have a real NT8 trade list behind them. EmaCrossover has no NinjaScript at
    all, so it must not claim one -- this is the assertion that would fail if someone
    registered an original with the reconciled ports' status copied across.
    """
    assert archetypes.DEADCATBOUNCE.tier2 is Tier2Status.RECONCILED
    assert archetypes.PULLBACKANDGO.tier2 is Tier2Status.RECONCILED
    assert archetypes.INSIDEBAR.tier2 is Tier2Status.RECONCILED
    assert archetypes.INSIDEBARTRAILING.tier2 is Tier2Status.RECONCILED
    assert archetypes.EMACROSSOVER.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.ELASTICBAND.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.OPENINGRANGE.tier2 is Tier2Status.TIER1_ONLY


# -- sweepable, and the __slots__ trap it exists to avoid ----------------------


def test_sweepable_is_every_field_except_the_declared_exclusions() -> None:
    a = archetypes.DEADCATBOUNCE
    assert a.sweepable == frozenset(f.name for f in fields(DeadCatParams)) - {"target_r_multiples"}
    assert "target_r_multiples" not in a.sweepable
    assert "ema_period" in a.sweepable


def test_sweepable_sees_inherited_fields_that_slots_would_hide() -> None:
    """The #60 failure, made to actually fail rather than asserted about.

    ``__slots__`` holds only the fields declared on the class itself. A params class that
    inherits one would silently lose that axis -- and a dropped axis does not raise, it
    makes every combination along it identical. This pins the difference between the two
    readings on a class where they genuinely disagree.
    """

    @dataclass(slots=True)
    class Base:
        inherited_period: int = 5

    @dataclass(slots=True)
    class Derived(Base):
        own_period: int = 7

    assert "inherited_period" not in Derived.__slots__, "premise gone; rewrite this test"

    probe = Archetype(
        name="_slots_probe",
        params_cls=Derived,
        run=archetypes.DEADCATBOUNCE.run,
        legs=archetypes.DEADCATBOUNCE.legs,
        signal=archetypes.DEADCATBOUNCE.signal,
        tier2=Tier2Status.NOT_CHECKED,
        not_sweepable=frozenset(),
    )
    assert probe.sweepable == {"inherited_period", "own_period"}


def test_an_axis_the_archetype_does_not_have_is_rejected_by_name() -> None:
    """DeadCatBounce has no ``require_previous_red``; PullBackAndGo has no ``tp_multiplier``."""
    with pytest.raises(sweep.SweepError, match="require_previous_red"):
        sweep.Grid.of(DeadCatParams(), require_previous_red=[True, False])
    with pytest.raises(sweep.SweepError, match="tp_multiplier"):
        sweep.Grid.of(PullBackAndGoParams(), tp_multiplier=[1.0, 1.5])


# -- ContextSpec ---------------------------------------------------------------


def test_specs_union_so_several_archetypes_can_share_one_dataset() -> None:
    a = ContextSpec(ma_keys=conditions.ma_keys(ema=(9, 21), sma=(60,)), needs_vwap=False)
    b = ContextSpec(ma_keys=conditions.ma_keys(ema=(21, 50), sma=(175,)), needs_vwap=True)
    both = a | b
    assert both.ma_keys == conditions.ma_keys(ema=(9, 21, 50), sma=(60, 175))
    assert both.needs_vwap is True


def test_vwap_is_requested_only_when_some_combination_switches_it_on() -> None:
    off = sweep.Grid.of(DeadCatParams(use_vwap=False))
    assert off.required_context().needs_vwap is False

    swept = sweep.Grid.of(DeadCatParams(), use_vwap=[True, False])
    assert swept.required_context().needs_vwap is True, "one True in the axis is enough"

    always = sweep.Grid.of(DeadCatParams(use_vwap=True))
    assert always.required_context().needs_vwap is True


def test_axis_values_reports_defaults_for_parameters_that_are_not_swept() -> None:
    """Reading only ``axes`` is how an unswept period gets left out of the grid."""
    grid = sweep.Grid.of(DeadCatParams(ema_period=11), fast_sma_period=[40, 60])
    values = grid.axis_values()
    assert values["ema_period"] == [11]
    assert values["fast_sma_period"] == [40, 60]
    assert set(values) == archetypes.DEADCATBOUNCE.sweepable


# -- the gate map is per archetype, and has to name real fields ----------------


def test_every_gate_names_a_real_field_on_its_own_params_class() -> None:
    """A typo'd gate does not raise -- it just never fires, so ``dead_axes`` stops guarding.

    Structural rather than a spot check, so a newly registered archetype cannot bring a
    silently inert gate map with it.
    """
    for a in archetypes.all_archetypes():
        known = {f.name for f in fields(a.params_cls)}
        for axis, toggle in a.gated_by.items():
            assert axis in known, f"{a.name}: gated axis {axis!r} is not a field"
            assert toggle in known, f"{a.name}: gate {toggle!r} is not a field"


def test_the_bracket_floor_is_dead_while_the_swing_stop_is_selected() -> None:
    """The floor sizes the ATR stop only, so sweeping it in swing mode buys nothing."""
    base = EmaCrossoverParams(use_atr_stop=False)
    with pytest.raises(sweep.SweepError, match="min_bracket_dollars"):
        sweep.Grid.of(base, min_bracket_dollars=[0.0, 30.0])
    grid = sweep.Grid.of(base, min_bracket_dollars=[0.0, 30.0], use_atr_stop=[True, False])
    assert len(grid) == 4


def test_dead_axes_guards_pullbackandgo_too() -> None:
    """The guard came with the archetype rather than being reimplemented per strategy."""
    base = PullBackAndGoParams(use_slow_sma=False)
    with pytest.raises(sweep.SweepError, match="slow_sma_period"):
        sweep.Grid.of(base, slow_sma_period=[120, 175])
    # Sweeping the toggle alongside it makes the period live again.
    grid = sweep.Grid.of(base, slow_sma_period=[120, 175], use_slow_sma=[True, False])
    assert len(grid) == 4


# -- Grid wiring ---------------------------------------------------------------


def test_a_grid_infers_its_archetype_from_base() -> None:
    assert sweep.Grid.of(PullBackAndGoParams()).archetype is archetypes.PULLBACKANDGO
    assert sweep.Grid.of(DeadCatParams()).archetype is archetypes.DEADCATBOUNCE
    assert sweep.Grid.of().archetype is archetypes.DEFAULT


def test_a_base_of_the_wrong_class_is_refused_rather_than_run() -> None:
    """Otherwise the archetype's ``run`` gets parameters it will read the wrong fields off."""
    with pytest.raises(sweep.SweepError, match="takes DeadCatParams"):
        sweep.Grid(base=PullBackAndGoParams(), archetype=archetypes.DEADCATBOUNCE)


def test_a_grid_survives_pickling() -> None:
    """The parallel path ships the grid to every worker, archetype included."""
    grid = sweep.Grid.of(PullBackAndGoParams(), ema_period=[9, 21])
    back = loads(dumps(grid))
    assert back.archetype.name == "PullBackAndGo"
    assert [p.ema_period for p in back.combinations()] == [9, 21]


def test_combinations_yield_the_archetypes_own_parameter_class() -> None:
    combos = list(sweep.Grid.of(PullBackAndGoParams(), ema_period=[9, 21]).combinations())
    assert [type(c) for c in combos] == [PullBackAndGoParams, PullBackAndGoParams]


# -- the acceptance criterion --------------------------------------------------


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Random-walk minute bars with wicks wide enough to throw hammers both ways."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n))
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


def test_a_pullbackandgo_grid_sweeps_end_to_end() -> None:
    """What M17 is for: a second archetype swept without forking ``sweep.py``.

    Before the registry this was impossible -- ``run_combination`` named ``run_deadcat``
    and ``SWEEPABLE`` was scraped off ``DeadCatParams``.
    """
    bars = synthetic_bars()
    grid = sweep.Grid.of(
        PullBackAndGoParams(bars_required_to_trade=20, use_slow_sma=False),
        ema_period=[9, 21],
    )
    data = sweep.prepare_for(bars, grid)
    results, _ = sweep.sweep(bars, grid, NQ, data=data)

    assert len(results) == 2
    assert results["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    # PullBackAndGo's own fields reach the results table, not DeadCatBounce's.
    assert "require_previous_red" in results.columns
    assert "require_previous_green" not in results.columns


def test_the_two_archetypes_disagree_on_direction_over_the_same_bars() -> None:
    """Guards against the registry dispatching both names to the same ``run``.

    A lookup that silently returned DeadCatBounce for everything would pass every test
    above -- the params class is checked, the columns come from the params, and both
    produce trades. The direction column is what separates them.
    """
    bars = synthetic_bars()
    long_grid = sweep.Grid.of(PullBackAndGoParams(bars_required_to_trade=20, use_slow_sma=False))
    short_grid = sweep.Grid.of(DeadCatParams(bars_required_to_trade=20))

    _, long_logs = sweep.sweep(bars, long_grid, NQ, keep_trades=True)
    _, short_logs = sweep.sweep(bars, short_grid, NQ, keep_trades=True)

    assert len(long_logs[0]) and len(short_logs[0]), "one side produced nothing"
    assert (long_logs[0]["direction"] == 1).all()
    assert (short_logs[0]["direction"] == -1).all()


def test_an_insidebar_grid_sweeps_end_to_end() -> None:
    """The third port reaching the results table through the registry, not a fork of it.

    Its ``ContextSpec`` is the one that asks for raw moving-average values, an ATR and the
    session clock together, so a sweep is what proves the three arrive.
    """
    bars = synthetic_bars()
    grid = sweep.Grid.of(
        InsideBarParams(slow_sma_period=50, bars_required_to_trade=60),
        atr_multiplier=[5.0, 10.0],
    )
    spec = grid.required_context()
    assert spec.needs_ma_values and spec.atr_periods == (3,) and spec.needs_session_clock

    results, _ = sweep.sweep(bars, grid, NQ)
    assert len(results) == 2
    assert results["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"
    assert "error_margin" in results.columns
    assert "require_previous_green" not in results.columns
