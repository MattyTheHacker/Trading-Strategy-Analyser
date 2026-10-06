"""The confluence size on every archetype: the parameters, the labels, the loops and the registry.

What carries it is that **a size is read at the signal bar and moves nothing but the size**:
outside InsideBarTrailing the trades a sized run takes are the fixed-size run's, leg for leg,
and each one carries the row of the size table its signal bar named -- ``docs/nt8-fidelity.md``
§M47. With the size off, the table is the one fixed split, which is each NinjaScript as ported.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Protocol

import numpy as np
import pytest

from nqbt import archetypes, context, regime, sweep, trend, volume
from nqbt.archetypes import Tier2Status
from nqbt.instruments import MNQ
from nqbt.sim import bracket, filters
from nqbt.sim.types import (
    EXPANSION,
    ORB_ENTRY_BREAKOUT,
    ORB_ENTRY_FADE,
    ORB_ENTRY_REJECTION,
    ORB_ENTRY_RETEST,
    ORB_TARGET_WIDTH,
    PULLBACK,
    ROTATION,
    SIZING_LABELS,
    BreakevenParams,
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
    StopTighteningParams,
    confluence_range,
    leg_size_table,
    sizing_labels,
    split_evenly,
    validate_sizing,
)
from nqbt.trades import (
    C_COMMISSION,
    C_DIRECTION,
    C_ENTRY_BAR,
    C_GROSS_PNL,
    C_LEG,
    C_NET_PNL,
    C_QUANTITY,
    C_TRADE_ID,
    LONG,
    N_COLUMNS,
    SHORT,
)
from tests.test_insidebartrailing_sim import walk_bars

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.arrays import BoolArray, FloatArray
    from nqbt.sim.types import SizingThesis
    from nqbt.trades import LegMatrix

BARS = 20_000
"""Enough synthetic minutes that every archetype below trades, and at several sizes."""


class ArchetypeParams(
    archetypes.Params,
    filters.LabelSized,
    filters.EarlyExiting,
    StopTighteningParams,
    BreakevenParams,
    Protocol,
):
    """A parameter class as the registry, the confluence size and every exit rule read it."""


TRADING: dict[str, ArchetypeParams] = {
    "DeadCatBounce": DeadCatParams(
        use_ema=False, use_fast_sma=False, require_new_high=False, bars_required_to_trade=20
    ),
    "PullBackAndGo": PullBackAndGoParams(
        use_ema=False, use_fast_sma=False, use_slow_sma=False, require_new_low=False
    ),
    "EmaCrossover": EmaCrossoverParams(fast_period=5, slow_period=20, bars_required_to_trade=30),
    "EmaPullback": EmaPullbackParams(fast_period=5, slow_period=20, bars_required_to_trade=30),
    "InsideBar": InsideBarParams(
        ema_period=5, fast_sma_period=8, slow_sma_period=13, no_entry_minutes_before_close=0
    ),
    "ElasticBand": ElasticBandParams(band_period=20, entry_std=1.5, bars_required_to_trade=30),
    "OpeningRange": OpeningRangeParams(window_minutes=30, max_entries_per_session=0),
    "SqueezeBreakout": SqueezeBreakoutParams(squeeze_period=10, squeeze_below=0.5),
}
"""A combination per archetype but InsideBarTrailing that trades on :func:`walk_bars`."""

LOOPS: dict[str, tuple[str, ArchetypeParams]] = {
    **{name: (name, params) for name, params in TRADING.items()},
    "EmaPullback confirmation": (
        "EmaPullback",
        dataclasses.replace(TRADING["EmaPullback"], confirm_entry=True),
    ),
}
"""Every entry loop a size reaches: EmaPullback's confirmation entry is a loop of its own."""

EVERY_CLASS: tuple[type[ArchetypeParams], ...] = (
    DeadCatParams,
    PullBackAndGoParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    InsideBarTrailingParams,
    ElasticBandParams,
    OpeningRangeParams,
    SqueezeBreakoutParams,
)

SIZE_COLUMNS = (C_QUANTITY, C_GROSS_PNL, C_COMMISSION, C_NET_PNL)
"""The columns a size writes. Everything else is the trade."""


def every_label[P: archetypes.Params](params: P, **fields: object) -> P:
    """Return ``params`` sizing on all five labels at one contract per leg per label."""
    return dataclasses.replace(
        params, quantity_per_confluence=1, **dict.fromkeys(SIZING_LABELS, True), **fields
    )


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(BARS, seed=5)


def prepared(bars: pd.DataFrame, params: ArchetypeParams, archetype: archetypes.Archetype) -> context.Dataset:
    return context.prepare(
        bars,
        sweep.Grid.of(params, archetype=archetype).required_context(),
        bar_minutes=1,
        price_basis=context.PriceBasis.RAW,
    )


# -- the parameters ----------------------------------------------------------------------------


def test_an_even_split_puts_the_remainder_on_the_last_leg() -> None:
    assert split_evenly(4, 4) == (1, 1, 1, 1)
    assert split_evenly(10, 4) == (2, 2, 2, 4)
    assert split_evenly(5, 2) == (2, 3)
    assert split_evenly(3, 1) == (3,)


def test_every_count_moves_every_leg_by_one_step_so_the_position_keeps_its_shape() -> None:
    params = DeadCatParams(order_quantity=6, quantity_per_confluence=2, size_on_trend=True, size_on_vwap=True)
    table = leg_size_table(params, 4)
    assert table == ((1, 1, 1, 3), (3, 3, 3, 5), (5, 5, 5, 7))
    steps = np.diff(np.asarray(table), axis=0)
    assert (steps == 2).all(), "a label moves every leg, not the last one"


def test_a_symmetric_count_removes_a_step_per_opposing_label_and_stops_at_one_per_leg() -> None:
    params = ElasticBandParams(
        order_quantity=6,
        quantity_per_confluence=1,
        size_on_trend=True,
        size_on_vwap=True,
        size_on_regime=True,
        size_symmetric=True,
    )
    assert list(confluence_range(params)) == [-3, -2, -1, 0, 1, 2, 3]
    assert params.size_table == ((1, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6))
    assert min(min(row) for row in params.size_table) == 1


def test_the_default_table_is_the_one_fixed_split_on_every_class() -> None:
    for cls in EVERY_CLASS:
        params = cls()
        assert params.size_table == (params.leg_quantities,), cls.__name__
        assert sizing_labels(params) == ()
        assert list(confluence_range(params)) == [0]


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_the_smallest_position_is_one_contract_per_leg(cls: type[ArchetypeParams]) -> None:
    params = cls()
    if cls is InsideBarTrailingParams:
        # 0.6 of 2 rounds up to both contracts, so the stored split needs three.
        assert params.minimum_quantity == 3

        return

    assert params.minimum_quantity == len(params.leg_quantities)


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"quantity_per_confluence": -1}, "contract count"),
        ({"quantity_per_confluence": 1}, "fixed size under another name"),
        ({"size_on_volume": True}, "fixed size under another name"),
        ({"size_symmetric": True}, "no confluence size"),
    ],
)
def test_a_size_that_cannot_run_or_runs_as_fixed_size_is_refused_on_every_class(
    cls: type[ArchetypeParams], fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        cls(**fields)


@pytest.mark.parametrize("cls", [c for c in EVERY_CLASS if c is not InsideBarTrailingParams])
def test_a_symmetric_size_at_the_smallest_position_is_refused_rather_than_run_as_add_only(
    cls: type[ArchetypeParams],
) -> None:
    smallest = cls().minimum_quantity
    with pytest.raises(ValueError, match="can remove nothing"):
        cls(order_quantity=smallest, quantity_per_confluence=1, size_on_trend=True, size_symmetric=True)  # type: ignore[call-arg]  # every params class takes its fields as keywords

    above = cls(  # type: ignore[call-arg]  # every params class takes its fields as keywords
        order_quantity=smallest + 1, quantity_per_confluence=1, size_on_trend=True, size_symmetric=True
    )
    shed, base, _ = above.size_table
    assert shed == tuple([1] * len(above.leg_quantities))
    assert base == above.leg_quantities
    assert sum(shed) < sum(base)


def test_validate_sizing_passes_a_legal_symmetric_size() -> None:
    validate_sizing(InsideBarParams(quantity_per_confluence=1, size_on_regime=True, size_symmetric=True))


def test_insidebartrailings_floor_is_its_splits_so_symmetric_stops_where_the_split_would_empty() -> None:
    params = InsideBarTrailingParams(
        order_quantity=4,
        partial_take_profit_percentage=0.6,
        quantity_per_confluence=1,
        size_on_trend=True,
        size_on_vwap=True,
        size_symmetric=True,
    )
    # 0.6 of 2 rounds to both contracts, so a two-contract split is empty and 3 is the floor.
    assert params.minimum_quantity == 3
    assert params.lot_table == ((2, 1), (2, 1), (3, 1), (3, 2), (4, 2))
    with pytest.raises(ValueError, match="can remove nothing"):
        dataclasses.replace(params, order_quantity=3)


def test_insidebartrailing_adds_to_the_whole_position_before_the_split() -> None:
    params = InsideBarTrailingParams(
        order_quantity=4, partial_take_profit_percentage=0.5, quantity_per_confluence=1, size_on_trend=True
    )
    assert params.size_table == params.lot_table == ((2, 2), (3, 2))


@pytest.mark.parametrize(
    ("params", "thesis"),
    [
        (DeadCatParams(), PULLBACK),
        (PullBackAndGoParams(), PULLBACK),
        (EmaPullbackParams(), PULLBACK),
        (EmaCrossoverParams(), EXPANSION),
        (InsideBarParams(), EXPANSION),
        (InsideBarTrailingParams(), EXPANSION),
        (SqueezeBreakoutParams(), EXPANSION),
        (ElasticBandParams(), ROTATION),
        (OpeningRangeParams(entry_mode=ORB_ENTRY_BREAKOUT), EXPANSION),
        (OpeningRangeParams(entry_mode=ORB_ENTRY_RETEST, target_mode=ORB_TARGET_WIDTH), EXPANSION),
        (OpeningRangeParams(entry_mode=ORB_ENTRY_FADE, stop_mode=2), ROTATION),
        (OpeningRangeParams(entry_mode=ORB_ENTRY_REJECTION, stop_mode=2), ROTATION),
    ],
)
def test_each_archetype_names_the_regime_and_volume_its_entry_wants(
    params: ArchetypeParams, thesis: SizingThesis
) -> None:
    assert params.sizing_thesis == thesis


# -- the labels --------------------------------------------------------------------------------


def labelled_insidebar(**fields: object) -> ArchetypeParams:
    return dataclasses.replace(every_label(TRADING["InsideBar"]), **fields)


def test_a_sided_label_favours_one_side_and_opposes_the_other(bars: pd.DataFrame) -> None:
    params = labelled_insidebar()
    data = prepared(bars, params, archetypes.INSIDEBAR)
    long_side = np.ones(len(data), dtype=np.bool_)
    as_long = filters.label_sides(data, params, long_side)
    as_short = filters.label_sides(data, params, ~long_side)
    for position in range(3):  # trend, higher timeframe, vwap
        assert np.array_equal(as_long[position].favours, as_short[position].opposes)
        assert np.array_equal(as_long[position].opposes, as_short[position].favours)
        assert as_long[position].favours.any()
        assert as_long[position].opposes.any()


def test_the_trend_label_leaves_a_mixed_bar_neither_favouring_nor_opposing(bars: pd.DataFrame) -> None:
    params = labelled_insidebar()
    data = prepared(bars, params, archetypes.INSIDEBAR)
    trend_label = filters.label_sides(data, params, np.ones(len(data), dtype=np.bool_))[0]
    mixed = data.trend_gate(
        params.trend_key, trend.trends_mask([trend.Trend.MIXED]), params.trend_min_agreement
    )
    assert mixed.any()
    assert not (trend_label.favours | trend_label.opposes)[mixed].any()


@pytest.mark.parametrize(
    ("params", "favoured", "opposed"),
    [
        (every_label(InsideBarParams()), regime.Regime.DIRECTIONAL, regime.Regime.CONSOLIDATING),
        (every_label(ElasticBandParams()), regime.Regime.CONSOLIDATING, regime.Regime.DIRECTIONAL),
    ],
)
def test_the_regime_label_follows_the_archetypes_thesis(
    bars: pd.DataFrame,
    params: ArchetypeParams,
    favoured: regime.Regime,
    opposed: regime.Regime,
) -> None:
    archetype = archetypes.for_params(params)
    data = prepared(bars, params, archetype)
    regime_label = filters.label_sides(data, params, np.ones(len(data), dtype=np.bool_))[3]

    def labelled(state: regime.Regime) -> BoolArray:
        return data.regime_gate(
            params.regime_lookback,
            regime.regimes_mask([state]),
            params.regime_consolidating_below,
            params.regime_directional_above,
        )

    assert np.array_equal(regime_label.favours, labelled(favoured))
    assert np.array_equal(regime_label.opposes, labelled(opposed))


@pytest.mark.parametrize(
    ("params", "favoured"),
    [
        (every_label(InsideBarParams()), volume.VolumeState.HEAVY),
        (every_label(DeadCatParams()), volume.VolumeState.THIN),
    ],
)
def test_the_volume_label_follows_the_archetypes_thesis(
    bars: pd.DataFrame, params: ArchetypeParams, favoured: volume.VolumeState
) -> None:
    archetype = archetypes.for_params(params)
    data = prepared(bars, params, archetype)
    volume_label = filters.label_sides(data, params, np.zeros(len(data), dtype=np.bool_))[4]
    favours = data.volume_gate(
        params.volume_key, volume.states_mask([favoured]), params.volume_thin_below, params.volume_heavy_above
    )
    assert np.array_equal(volume_label.favours, favours)
    assert not (volume_label.favours & volume_label.opposes).any()


def test_an_add_only_count_is_the_favourable_labels_and_a_symmetric_one_nets_the_opposing(
    bars: pd.DataFrame,
) -> None:
    add_only = labelled_insidebar()
    symmetric = labelled_insidebar(size_symmetric=True, order_quantity=6)
    data = prepared(bars, add_only, archetypes.INSIDEBAR)
    long_side = data.close > data.open
    sides = filters.label_sides(data, add_only, long_side)
    favours = np.sum([label.favours for label in sides], axis=0)
    opposes = np.sum([label.opposes for label in sides], axis=0)
    assert np.array_equal(filters.confluence_counts(data, add_only, long_side), favours)
    assert np.array_equal(filters.confluence_counts(data, symmetric, long_side), favours - opposes)
    assert (favours - opposes < 0).any(), (
        "no bar was net unfavourable, so the symmetric count was not exercised"
    )


def test_every_row_a_bar_can_take_is_in_its_table(bars: pd.DataFrame) -> None:
    params = labelled_insidebar(size_symmetric=True, order_quantity=6)
    data = prepared(bars, params, archetypes.INSIDEBAR)
    sizing = filters.confluence_sizing(data, params, data.close > data.open)
    assert sizing.quantities.shape == (11, 1)
    assert sizing.row_at.min() >= 0
    assert sizing.row_at.max() < 11


def test_no_labels_counts_nothing_and_sizing_off_is_the_fixed_split_on_every_bar(bars: pd.DataFrame) -> None:
    params = TRADING["InsideBar"]
    data = prepared(bars, params, archetypes.INSIDEBAR)
    assert not filters.confluence_counts(data, params, np.ones(len(data), dtype=np.bool_)).any()
    sizing = filters.confluence_sizing(data, params, np.ones(len(data), dtype=np.bool_))
    assert sizing.quantities.tolist() == [list(params.leg_quantities)]
    assert not sizing.row_at.any()


# -- the loops ---------------------------------------------------------------------------------


def trades_of(legs: LegMatrix) -> FloatArray:
    """Return every column of every leg but the four a size writes."""
    kept = [column for column in range(N_COLUMNS) if column not in SIZE_COLUMNS]

    return legs.matrix[: legs.count, kept]


@pytest.mark.parametrize("loop", sorted(LOOPS))
def test_sizing_moves_the_quantities_and_never_a_trade(bars: pd.DataFrame, loop: str) -> None:
    name, params = LOOPS[loop]
    archetype = archetypes.get(name)
    sized = every_label(params)
    data = prepared(bars, sized, archetype)
    fixed = archetype.legs(data, params, MNQ)
    on = archetype.legs(data, sized, MNQ)
    assert fixed.count > 10, "too few legs for the comparison to mean anything"
    assert np.array_equal(trades_of(fixed), trades_of(on), equal_nan=True)
    assert (on.matrix[: on.count, C_QUANTITY] != fixed.matrix[: fixed.count, C_QUANTITY]).any()
    assert len(set(on.matrix[: on.count, C_QUANTITY])) > 1, "every trade took one size"


@pytest.mark.parametrize("loop", sorted(LOOPS))
def test_sizing_off_takes_the_fixed_split_on_every_trade(bars: pd.DataFrame, loop: str) -> None:
    name, params = LOOPS[loop]
    archetype = archetypes.get(name)
    data = prepared(bars, params, archetype)
    legs = archetype.legs(data, params, MNQ)
    quantities = legs.matrix[: legs.count, C_QUANTITY]
    leg = legs.matrix[: legs.count, C_LEG].astype(int) - 1
    assert np.array_equal(quantities, np.asarray(params.leg_quantities)[leg])


@pytest.mark.parametrize("loop", sorted(LOOPS))
def test_each_trade_takes_the_row_its_signal_bar_names_and_not_its_fill_bars(
    monkeypatch: pytest.MonkeyPatch, bars: pd.DataFrame, loop: str
) -> None:
    """Alternating rows, so reading the fill bar instead would give every trade the other one."""
    name, params = LOOPS[loop]
    archetype = archetypes.get(name)
    data = prepared(bars, params, archetype)
    legs_per_trade = len(params.leg_quantities)
    table = np.asarray([[1] * legs_per_trade, [3] * legs_per_trade], dtype=np.int64)
    alternating = bracket.Sizing(table, np.arange(len(data), dtype=np.int64) % 2)
    monkeypatch.setattr(filters, "confluence_sizing", lambda *_: alternating)
    legs = archetype.legs(data, params, MNQ)
    matrix = legs.matrix[: legs.count]
    signal_bar = matrix[:, C_ENTRY_BAR].astype(int) - 1
    assert legs.count > 10
    assert np.array_equal(matrix[:, C_QUANTITY], table[signal_bar % 2, 0])


def test_every_leg_of_a_trade_scales_together(bars: pd.DataFrame) -> None:
    params = every_label(TRADING["DeadCatBounce"])
    data = prepared(bars, params, archetypes.DEADCATBOUNCE)
    legs = archetypes.DEADCATBOUNCE.legs(data, params, MNQ)
    matrix = legs.matrix[: legs.count]
    for trade_id in np.unique(matrix[:, C_TRADE_ID]):
        sizes = matrix[matrix[:, C_TRADE_ID] == trade_id, C_QUANTITY]
        assert len(set(sizes)) == 1, "a four-target bracket at four contracts gains one per leg"


def test_size_legs_copies_the_signal_bars_row_into_the_legs() -> None:
    legs = bracket.Legs(np.zeros(2, dtype=np.bool_), np.zeros(2), np.zeros(2, dtype=np.int64))
    sizing = bracket.Sizing(
        np.asarray([[1, 1], [2, 3]], dtype=np.int64), np.asarray([0, 1, 0], dtype=np.int64)
    )
    bracket.size_legs(legs, sizing, 1)
    assert legs.quantity.tolist() == [2, 3]
    bracket.size_legs(legs, sizing, 2)
    assert legs.quantity.tolist() == [1, 1]


# -- the registry and the sweep ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_labels_axes_are_live_when_sizing_reads_them_and_dead_otherwise(name: str) -> None:
    archetype = archetypes.get(name)
    sized = dataclasses.replace(TRADING[name], quantity_per_confluence=1, size_on_regime=True)
    sweep.Grid.of(sized, archetype=archetype, regime_lookback=[10, 20])
    with pytest.raises(sweep.SweepError, match=r"regime_filter is 7 and size_on_regime is False"):
        sweep.Grid.of(TRADING[name], archetype=archetype, regime_lookback=[10, 20])


@pytest.mark.parametrize("name", sorted(TRADING))
def test_the_symmetric_axis_is_dead_without_a_confluence_size(name: str) -> None:
    with pytest.raises(
        sweep.SweepError, match=r"size_symmetric \(inert while quantity_per_confluence is 0\)"
    ):
        sweep.Grid.of(TRADING[name], archetype=archetypes.get(name), size_symmetric=[False, True])


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_label_a_size_counts_is_built_into_the_dataset(name: str) -> None:
    archetype = archetypes.get(name)
    spec = sweep.Grid.of(every_label(TRADING[name]), archetype=archetype).required_context()
    assert spec.needs_vwap
    assert spec.regime_lookbacks
    assert spec.volume_keys
    assert spec.trend_keys
    assert spec.higher_timeframe_keys
    assert not sweep.Grid.of(TRADING[name], archetype=archetype).required_context().needs_vwap or name in {
        "DeadCatBounce",
        "PullBackAndGo",
    }


@pytest.mark.parametrize(
    ("archetype", "params"),
    [
        (archetypes.DEADCATBOUNCE, DeadCatParams()),
        (archetypes.PULLBACKANDGO, PullBackAndGoParams()),
        (archetypes.INSIDEBAR, InsideBarParams()),
        (archetypes.INSIDEBARTRAILING, InsideBarTrailingParams()),
    ],
)
def test_a_sized_row_leaves_every_reconciled_port(
    archetype: archetypes.Archetype, params: archetypes.Params
) -> None:
    assert archetype.tier2_for(params) is Tier2Status.RECONCILED
    assert archetype.tier2_for(every_label(params)) is Tier2Status.TIER1_ONLY


def test_an_original_archetype_stays_tier_1_only_sized_or_not() -> None:
    params = EmaCrossoverParams()
    assert archetypes.EMACROSSOVER.tier2_for(params) is Tier2Status.TIER1_ONLY
    assert archetypes.EMACROSSOVER.tier2_for(every_label(params)) is Tier2Status.TIER1_ONLY


def test_a_grid_refuses_a_symmetric_size_where_some_base_cannot_shed_a_step_before_anything_runs() -> None:
    sized = InsideBarParams(quantity_per_confluence=1, size_on_trend=True, size_symmetric=True)
    assert len(sweep.Grid.of(sized, order_quantity=[2, 3])) == 2
    with pytest.raises(sweep.SweepError, match=r"cannot be built, so none runs: .*size_symmetric"):
        sweep.Grid.of(sized, order_quantity=[1, 3])


def test_long_and_short_sides_are_read_per_archetype(bars: pd.DataFrame) -> None:
    """The side a sided label is read against: fixed for the one-sided archetypes, per bar otherwise."""
    data = prepared(bars, TRADING["OpeningRange"], archetypes.OPENINGRANGE)
    assert not archetypes.DEADCATBOUNCE.long_side(data, DeadCatParams()).any()
    assert archetypes.PULLBACKANDGO.long_side(data, PullBackAndGoParams()).all()
    assert archetypes.OPENINGRANGE.long_side(data, OpeningRangeParams(direction=LONG)).all()
    assert not archetypes.OPENINGRANGE.long_side(data, OpeningRangeParams(direction=SHORT)).any()


@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_sized_row_would_leave_any_archetype_once_it_is_reconciled(name: str) -> None:
    """Reconciling an original later needs no change to the rule, whatever its parameter class."""
    reconciled = dataclasses.replace(
        archetypes.get(name),
        tier2=Tier2Status.RECONCILED,
        departs_from_port=archetypes._sizes_per_signal,
        port_properties=None,
    )
    assert reconciled.tier2_for(TRADING[name]) is Tier2Status.RECONCILED
    assert reconciled.tier2_for(every_label(TRADING[name])) is Tier2Status.TIER1_ONLY


@pytest.mark.parametrize("name", sorted(TRADING))
def test_each_trade_is_entered_on_the_side_its_labels_were_read_against(
    bars: pd.DataFrame, name: str
) -> None:
    """The long-side series a sized label reads has to be the side the loop actually enters on."""
    archetype = archetypes.get(name)
    params = TRADING[name]
    data = prepared(bars, params, archetype)
    legs = archetype.legs(data, params, MNQ)
    matrix = legs.matrix[: legs.count]
    signal_bar = matrix[:, C_ENTRY_BAR].astype(int) - 1
    long_side = archetype.long_side(data, params)
    assert legs.count > 10
    assert np.array_equal(matrix[:, C_DIRECTION] == LONG, long_side[signal_bar])
