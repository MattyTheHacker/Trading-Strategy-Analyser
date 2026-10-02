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

from nqbt import (
    archetypes,
    compression,
    conditions,
    higher_timeframe,
    regime,
    sessions,
    sweep,
    timeofday,
    trend,
    volume,
)
from nqbt.archetypes import Archetype, ArchetypeError, ContextSpec, Tier2Status
from nqbt.instruments import NQ
from nqbt.sim import bracket
from nqbt.sim.types import (
    DeadCatParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
)

# -- the registry -------------------------------------------------------------


def test_every_archetype_is_registered() -> None:
    assert archetypes.names() == [
        "DeadCatBounce",
        "ElasticBand",
        "EmaCrossover",
        "EmaPullback",
        "InsideBar",
        "InsideBarTrailing",
        "OpeningRange",
        "PullBackAndGo",
        "SqueezeBreakout",
    ]
    assert archetypes.get("DeadCatBounce") is archetypes.DEADCATBOUNCE
    assert archetypes.get("ElasticBand") is archetypes.ELASTICBAND
    assert archetypes.get("EmaCrossover") is archetypes.EMACROSSOVER
    assert archetypes.get("EmaPullback") is archetypes.EMAPULLBACK
    assert archetypes.get("InsideBar") is archetypes.INSIDEBAR
    assert archetypes.get("InsideBarTrailing") is archetypes.INSIDEBARTRAILING
    assert archetypes.get("OpeningRange") is archetypes.OPENINGRANGE
    assert archetypes.get("PullBackAndGo") is archetypes.PULLBACKANDGO
    assert archetypes.get("SqueezeBreakout") is archetypes.SQUEEZEBREAKOUT


def test_an_unknown_name_lists_the_known_ones() -> None:
    with pytest.raises(ArchetypeError, match="DeadCatBounce"):
        archetypes.get("VolatilityCrush")


def test_registering_a_duplicate_name_is_refused() -> None:
    """``name`` is a results column, so two archetypes sharing one merge into a row group."""
    clash = Archetype(
        name="DeadCatBounce",
        params_cls=DeadCatParams,
        run=archetypes.DEADCATBOUNCE.run,
        legs=archetypes.DEADCATBOUNCE.legs,
        signal=archetypes.DEADCATBOUNCE.signal,
        long_side=archetypes.DEADCATBOUNCE.long_side,
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
    assert archetypes.for_params(EmaPullbackParams()) is archetypes.EMAPULLBACK
    assert archetypes.for_params(InsideBarParams()) is archetypes.INSIDEBAR
    assert archetypes.for_params(InsideBarTrailingParams()) is archetypes.INSIDEBARTRAILING
    assert archetypes.for_params(OpeningRangeParams()) is archetypes.OPENINGRANGE
    assert archetypes.for_params(SqueezeBreakoutParams()) is archetypes.SQUEEZEBREAKOUT


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
    assert archetypes.EMAPULLBACK.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.ELASTICBAND.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.OPENINGRANGE.tier2 is Tier2Status.TIER1_ONLY
    assert archetypes.SQUEEZEBREAKOUT.tier2 is Tier2Status.TIER1_ONLY


SCALES_ITS_TARGETS = [
    a for a in archetypes.all_archetypes() if "tp_multiplier" in {f.name for f in fields(a.params_cls)}
]


@pytest.mark.parametrize("archetype", SCALES_ITS_TARGETS, ids=lambda a: a.name)
@pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf])
def test_every_tp_multiplier_refuses_zero_below_or_not_finite(archetype: Archetype, value: float) -> None:
    """Every params class with a tp_multiplier refuses one at or below zero, nan or infinite."""
    with pytest.raises(ValueError, match="tp_multiplier must be"):
        archetype.params_cls(tp_multiplier=value)


def test_every_archetype_but_pullbackandgo_scales_its_targets() -> None:
    """The refusal test covers every archetype but PullBackAndGo, which has no tp_multiplier."""
    assert {a.name for a in SCALES_ITS_TARGETS} == set(archetypes.names()) - {"PullBackAndGo"}


# -- sweepable, and the __slots__ trap it exists to avoid ----------------------


def test_sweepable_is_every_field_except_the_declared_exclusions() -> None:
    a = archetypes.DEADCATBOUNCE
    assert a.sweepable == frozenset(f.name for f in fields(DeadCatParams)) - {"target_r_multiples"}
    assert "target_r_multiples" not in a.sweepable
    assert "ema_period" in a.sweepable


def test_sweepable_sees_inherited_fields_that_slots_would_hide() -> None:
    """``sweepable`` keeps an inherited field that ``__slots__`` would drop (#60)."""

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
        long_side=archetypes.DEADCATBOUNCE.long_side,
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
        for axis, gate in a.gated_by.items():
            assert axis in known, f"{a.name}: gated axis {axis!r} is not a field"
            for toggle in archetypes.gate_toggles(gate):
                assert toggle in known, f"{a.name}: gate {toggle!r} is not a field"


def test_a_gate_naming_one_toggle_and_one_naming_several_read_the_same_way() -> None:
    """Every reader of ``gated_by`` iterates the toggles, so a bare name must not iterate as letters."""
    assert archetypes.gate_toggles("use_ema") == ("use_ema",)
    assert archetypes.gate_toggles(("trail_ma_stop", "trail_on_slow")) == ("trail_ma_stop", "trail_on_slow")


def test_an_axis_naming_two_toggles_is_dead_while_either_leaves_it_unread() -> None:
    """Each toggle is checked on its own, so the axis is live only where both let it be read."""
    trail_off = EmaPullbackParams(trail_ma_stop=False, trail_on_slow=False)
    on_slow = EmaPullbackParams(trail_ma_stop=True, trail_on_slow=True)
    on_grid = EmaPullbackParams(trail_ma_stop=True, trail_on_slow=False)
    with pytest.raises(sweep.SweepError, match=r"trail_ma_period \(inert while trail_ma_stop is False\)"):
        sweep.Grid.of(trail_off, trail_ma_period=[20, 50])

    with pytest.raises(sweep.SweepError, match=r"trail_ma_period \(inert while trail_on_slow is True\)"):
        sweep.Grid.of(on_slow, trail_ma_period=[20, 50])

    assert sweep.Grid.of(on_grid, trail_ma_period=[20, 50]).dead_axes() == {}


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
    """Build random-walk minute bars with wicks wide enough to throw hammers both ways."""
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
    """A second archetype sweeps end to end without forking ``sweep.py`` -- ``docs/roadmap.md`` §M17."""
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


def test_every_archetype_can_be_swept_on_the_maximum_hold_time() -> None:
    """The exit every archetype owns, so a grid must be able to reach it on all of them.

    A missing field would not raise -- ``sweep_axes`` would reject the axis by name, and a
    campaign would quietly never test it.
    """
    for a in archetypes.all_archetypes():
        assert "max_hold_bars" in a.sweepable, a.name
        assert a.params_cls().max_hold_bars == 0, a.name


# -- leaving the reconciled port -----------------------------------------------

RECONCILED = (
    archetypes.DEADCATBOUNCE,
    archetypes.PULLBACKANDGO,
    archetypes.INSIDEBAR,
    archetypes.INSIDEBARTRAILING,
)

PROPERTY_VALUES: dict[str, object] = {
    "ema_period": 30,
    "slow_sma_period": 150,
    "fast_sma_period": 40,
    "order_quantity": 8,
    "tp_multiplier": 2.0,
    "max_risk_ticks": 100,
    "error_margin": 0.05,
    "atr_length": 5,
    "atr_multiplier": 5.0,
    "partial_take_profit_percentage": 0.5,
    "trailing_stop_multiplier": 3.0,
}
"""A legal value away from every default for each numeric NinjaScript property; a flag is flipped."""

UNMOVABLE_PROPERTIES = frozenset({"maximum_loss_per_trade"})
"""A property the parameter class refuses at anything but its default, so no row can move it."""

ONE_STATE_FILTERS: dict[str, int] = {
    "phase_filter": timeofday.SessionPhase.MIDDAY.bit,
    "regime_filter": regime.Regime.DIRECTIONAL.bit,
    "volume_filter": volume.VolumeState.HEAVY.bit,
    "compression_filter": compression.Compression.COMPRESSED.bit,
    "trend_filter": trend.Trend.UP.bit,
    "higher_timeframe_filter": higher_timeframe.Side.ABOVE.bit,
}
"""Each context filter narrowed to one state."""

NAN = float("nan")

LEAVING: list[tuple[Archetype, object, str]] = [
    (archetypes.DEADCATBOUNCE, DeadCatParams(max_hold_bars=5), "max_hold_bars"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(min_reward_risk=1.5), "min_reward_risk"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(ema_kind="sma"), "ema_kind"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(ambiguity_policy=0), "ambiguity_policy"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(ambiguity_policy=2), "ambiguity_policy"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(ratchet_lag=1), "ratchet_lag"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(fill_limit_on_touch=True), "fill_limit_on_touch"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(bars_required_to_trade=20), "bars_required_to_trade"),
    (
        archetypes.DEADCATBOUNCE,
        DeadCatParams(block_entry_at_session_close=False),
        "block_entry_at_session_close",
    ),
    (archetypes.DEADCATBOUNCE, DeadCatParams(stop_offset_ticks=3), "stop_offset_ticks"),
    (archetypes.DEADCATBOUNCE, DeadCatParams(entry_offset_ticks=3), "entry_offset_ticks"),
    (
        archetypes.DEADCATBOUNCE,
        DeadCatParams(target_r_multiples=(1.0, 2.0, 3.0, NAN)),
        "target_r_multiples",
    ),
    (
        archetypes.DEADCATBOUNCE,
        DeadCatParams(quantity_per_confluence=1, size_on_trend=True),
        "quantity_per_confluence",
    ),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(ratchet_lag=0), "ratchet_lag"),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(ratchet_offset_ticks=3), "ratchet_offset_ticks"),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(round_targets=False), "round_targets"),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(slow_sma_kind="ema"), "slow_sma_kind"),
    (archetypes.PULLBACKANDGO, PullBackAndGoParams(max_hold_bars=5), "max_hold_bars"),
    (archetypes.INSIDEBAR, InsideBarParams(max_hold_bars=5), "max_hold_bars"),
    (archetypes.INSIDEBAR, InsideBarParams(fast_sma_kind="ema"), "fast_sma_kind"),
    (
        archetypes.INSIDEBAR,
        InsideBarParams(no_entry_minutes_before_close=0),
        "no_entry_minutes_before_close",
    ),
    (
        archetypes.INSIDEBAR,
        InsideBarParams(no_entry_minutes_before_close=30),
        "no_entry_minutes_before_close",
    ),
    (archetypes.INSIDEBAR, InsideBarParams(fill_limit_on_touch=False), "fill_limit_on_touch"),
    (archetypes.INSIDEBAR, InsideBarParams(round_targets=False), "round_targets"),
    (archetypes.INSIDEBARTRAILING, InsideBarTrailingParams(tp_multiplier=2.0), "tp_multiplier"),
    (
        archetypes.INSIDEBARTRAILING,
        InsideBarTrailingParams(position_update_loss_gate=100.0),
        "position_update_loss_gate",
    ),
    (
        archetypes.INSIDEBARTRAILING,
        InsideBarTrailingParams(no_entry_minutes_before_close=60),
        "no_entry_minutes_before_close",
    ),
    (archetypes.DEADCATBOUNCE, DeadCatParams(early_exit_bars=3), "early_exit_bars"),
    (
        archetypes.PULLBACKANDGO,
        PullBackAndGoParams(early_exit_minutes_before_close=30),
        "early_exit_minutes_before_close",
    ),
    (archetypes.INSIDEBAR, InsideBarParams(early_exit_on_regime_change=True), "early_exit_on_regime_change"),
    (
        archetypes.INSIDEBARTRAILING,
        InsideBarTrailingParams(early_exit_on_trend=bracket.TREND_EXIT_OPPOSED),
        "early_exit_on_trend",
    ),
]
"""One setting each NinjaScript has no property for, and the field it is caught on."""


@pytest.mark.parametrize("archetype", RECONCILED, ids=lambda a: a.name)
def test_a_reconciled_archetype_at_its_defaults_stays_on_its_port(archetype: Archetype) -> None:
    params = archetype.params_cls()
    assert archetype.fields_off_port(params) == ()
    assert archetype.tier2_for(params) is Tier2Status.RECONCILED


@pytest.mark.parametrize(
    ("archetype", "params", "caught_on"),
    LEAVING,
    ids=lambda case: case.name if isinstance(case, Archetype) else None,
)
def test_a_setting_the_ninjascript_has_no_property_for_leaves_the_port(
    archetype: Archetype,
    params: archetypes.Params,
    caught_on: str,
) -> None:
    assert caught_on in archetype.fields_off_port(params)
    assert archetype.tier2_for(params) is Tier2Status.TIER1_ONLY


@pytest.mark.parametrize("archetype", RECONCILED, ids=lambda a: a.name)
@pytest.mark.parametrize("mask", sorted(ONE_STATE_FILTERS))
def test_every_context_filter_leaves_every_reconciled_port(archetype: Archetype, mask: str) -> None:
    """Including InsideBarTrailing's phase filter, although its NinjaScript has an entry window."""
    params = archetype.params_cls(**{mask: ONE_STATE_FILTERS[mask]})
    assert archetype.fields_off_port(params) == (mask,)
    assert archetype.tier2_for(params) is Tier2Status.TIER1_ONLY


@pytest.mark.parametrize("archetype", RECONCILED, ids=lambda a: a.name)
def test_every_ninjascript_property_and_cost_may_move_without_leaving_the_port(archetype: Archetype) -> None:
    assert archetype.port_properties is not None
    movable = archetype.port_properties - UNMOVABLE_PROPERTIES
    for name in sorted(movable):
        default = getattr(archetype.params_cls(), name)
        moved = not default if isinstance(default, bool) else PROPERTY_VALUES[name]
        params = archetype.params_cls(**{name: moved})
        assert getattr(params, name) != default, name
        assert archetype.tier2_for(params) is Tier2Status.RECONCILED, name

    costed = archetype.params_cls(commission_per_contract=1.5, slippage_ticks=1.0)
    assert archetype.tier2_for(costed) is Tier2Status.RECONCILED


@pytest.mark.parametrize("archetype", RECONCILED, ids=lambda a: a.name)
def test_every_ninjascript_property_names_a_field_of_its_parameter_class(archetype: Archetype) -> None:
    """A misspelt property would leave its field checked against its default, and silently so."""
    assert archetype.port_properties is not None
    assert archetype.port_properties <= {f.name for f in fields(archetype.params_cls)}
    assert not archetype.port_properties & archetypes.COST_FIELDS


def test_a_setting_its_toggle_leaves_unread_does_not_leave_the_port() -> None:
    """Each changes no trade, so it cannot take the row anywhere NT8 has not been."""
    assert archetypes.DEADCATBOUNCE.fields_off_port(DeadCatParams(regime_lookback=30)) == ()
    assert archetypes.DEADCATBOUNCE.fields_off_port(DeadCatParams(slow_sma_kind="ema")) == ()
    trailing = InsideBarTrailingParams(early_partial_percentage=0.5)
    assert archetypes.INSIDEBARTRAILING.fields_off_port(trailing) == ()


def test_the_same_setting_leaves_the_port_once_its_toggle_reads_it() -> None:
    read = DeadCatParams(slow_sma_kind="ema", use_slow_sma=True)
    assert archetypes.DEADCATBOUNCE.fields_off_port(read) == ("slow_sma_kind",)
    filtered = DeadCatParams(regime_lookback=30, regime_filter=regime.Regime.DIRECTIONAL.bit)
    assert archetypes.DEADCATBOUNCE.fields_off_port(filtered) == ("regime_filter", "regime_lookback")


def test_a_runner_written_with_a_fresh_nan_is_still_the_default_bracket() -> None:
    """NaN is unequal to itself, so a plain comparison would call every rebuilt bracket a departure."""
    params = DeadCatParams(target_r_multiples=(1.0, 1.5, 2.0, float("nan")))
    assert archetypes.DEADCATBOUNCE.fields_off_port(params) == ()


@pytest.mark.parametrize(
    "archetype",
    [a for a in archetypes.all_archetypes() if a.tier2 is not Tier2Status.RECONCILED],
    ids=lambda a: a.name,
)
def test_an_archetype_with_no_ninjascript_has_no_port_to_leave(archetype: Archetype) -> None:
    params = archetype.params_cls(max_hold_bars=5)
    assert archetype.port_properties is None
    assert archetype.fields_off_port(params) == ()
    assert archetype.tier2_for(params) is archetype.tier2


@pytest.mark.parametrize(
    ("gate", "use_ema", "use_vwap", "expected"),
    [
        ("use_ema", True, False, True),
        ("use_ema", False, True, False),
        (("use_ema", "use_vwap"), True, False, False),
        (("use_ema", "use_vwap"), True, True, True),
        (archetypes.AnyOf(("use_ema", "use_vwap")), False, True, True),
        (archetypes.AnyOf(("use_ema", "use_vwap")), False, False, False),
    ],
)
def test_a_gate_reads_its_axis_as_dead_axes_does(
    gate: archetypes.Gate,
    use_ema: bool,  # noqa: FBT001 - a parametrised case
    use_vwap: bool,  # noqa: FBT001 - a parametrised case
    expected: bool,  # noqa: FBT001 - a parametrised case
) -> None:
    """A tuple needs every toggle on and :class:`AnyOf` any one, and a mask is on away from everything."""
    params = DeadCatParams(use_ema=use_ema, use_vwap=use_vwap)
    assert archetypes.reads(params, gate) is expected
    assert archetypes.reads(DeadCatParams(regime_filter=regime.Regime.DIRECTIONAL.bit), "regime_filter")
    assert not archetypes.reads(DeadCatParams(), "regime_filter")


def test_a_sweep_stamps_each_row_by_whether_it_leaves_the_port() -> None:
    grid = sweep.Grid.of(DeadCatParams(), max_hold_bars=[0, 5], ema_period=[11, 30])
    stamped = sweep.row_tier2(pd.DataFrame({"combo_id": range(len(grid))}), grid)
    by_hold = {params.max_hold_bars: stamped[i] for i, params in enumerate(grid.combinations())}
    assert by_hold == {0: "reconciled", 5: "tier-1-only"}
    assert stamped.count("reconciled") == stamped.count("tier-1-only") == 2


def test_a_sweep_of_an_archetype_with_no_ninjascript_stamps_its_own_status_everywhere() -> None:
    grid = sweep.Grid.of(EmaCrossoverParams(), max_hold_bars=[0, 5])
    stamped = sweep.row_tier2(pd.DataFrame({"combo_id": [1, 0]}), grid)
    assert stamped == ["tier-1-only", "tier-1-only"]
