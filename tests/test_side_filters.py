"""The filters relative to the trade's side: the trend, the higher-timeframe side and the VWAP side.

Each one keeps a signal only where its label points the way that bar would be entered, on every
archetype, and is off by default -- ``docs/nt8-fidelity.md``, "Filters relative to the trade's
side".
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pytest

from nqbt import archetypes, higher_timeframe, sweep, timeofday, trend
from nqbt.archetypes import Tier2Status
from nqbt.sim import filters
from nqbt.sim.types import (
    DeadCatParams,
    EmaCrossoverParams,
    PullBackAndGoParams,
    active_context_filters,
)
from tests.test_confluence_sizing import EVERY_CLASS, TRADING, bars, prepared

if TYPE_CHECKING:
    import pandas as pd

    from nqbt.archetypes import ArchetypeParams
    from nqbt.arrays import BoolArray
    from nqbt.context import Dataset

__all__ = ["bars"]

SIDE_FILTERS = ("with_trend", "with_higher_timeframe", "with_vwap")


def pointing_its_way(
    data: Dataset, params: ArchetypeParams, side_filter: str, long_side: BoolArray
) -> BoolArray:
    """Return where one label points each bar's own side, built from the label's gates directly."""
    if side_filter == "with_trend":
        up = data.trend_gate(
            params.trend_key, trend.trends_mask([trend.Trend.UP]), params.trend_min_agreement
        )
        down = data.trend_gate(
            params.trend_key, trend.trends_mask([trend.Trend.DOWN]), params.trend_min_agreement
        )
    elif side_filter == "with_higher_timeframe":
        key = params.higher_timeframe_key
        up = data.higher_timeframe_gate(key, higher_timeframe.sides_mask([higher_timeframe.Side.ABOVE]))
        down = data.higher_timeframe_gate(key, higher_timeframe.sides_mask([higher_timeframe.Side.BELOW]))
    else:
        up, down = data.vwap_gate(above=True), data.vwap_gate(above=False)

    return np.where(long_side, up, down)


@pytest.mark.parametrize("side_filter", SIDE_FILTERS)
@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_side_filter_keeps_exactly_the_signals_its_label_points_the_way_of(
    bars: pd.DataFrame, name: str, side_filter: str
) -> None:
    """Every archetype supplies the side it enters on, and the filter reads the label against it."""
    archetype = archetypes.get(name)
    filtered = dataclasses.replace(TRADING[name], **{side_filter: True})
    data = prepared(bars, filtered, archetype)
    unfiltered = archetype.signal(data, TRADING[name])
    expected = unfiltered & pointing_its_way(data, filtered, side_filter, archetype.long_side(data, filtered))

    assert np.array_equal(archetype.signal(data, filtered), expected)
    assert unfiltered.any()


@pytest.mark.parametrize("side_filter", SIDE_FILTERS)
def test_a_side_filter_narrows_a_two_sided_archetype_on_both_sides(
    bars: pd.DataFrame, side_filter: str
) -> None:
    """It is neither inert nor a long-only filter in disguise on an archetype that trades both ways."""
    archetype = archetypes.EMACROSSOVER
    filtered = dataclasses.replace(TRADING["EmaCrossover"], **{side_filter: True})
    data = prepared(bars, filtered, archetype)
    long_side = archetype.long_side(data, filtered)
    before = archetype.signal(data, TRADING["EmaCrossover"])
    after = archetype.signal(data, filtered)

    assert after.sum() < before.sum()
    assert (after & long_side).any()
    assert (after & ~long_side).any()


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_side_filter_off_is_the_signal_unchanged(bars: pd.DataFrame, name: str) -> None:
    archetype = archetypes.get(name)
    params = TRADING[name]
    data = prepared(bars, dataclasses.replace(params, with_trend=True), archetype)
    assert not any(getattr(params, side_filter) for side_filter in SIDE_FILTERS)
    assert filters.side_gates(data, params, None) == []


def test_the_side_is_not_computed_while_every_side_filter_is_off(bars: pd.DataFrame) -> None:
    """The archetype's side costs a recomputation, so a sweep with the filters off never pays it."""

    def never() -> BoolArray:
        msg = "computed the side with every side filter off"
        raise AssertionError(msg)

    params = TRADING["InsideBar"]
    data = prepared(bars, params, archetypes.INSIDEBAR)
    signal = np.ones(len(data), dtype=np.bool_)
    filters.apply_context_filters(signal, data, params, never)


def test_a_side_filter_given_no_side_is_refused_rather_than_read_against_one(bars: pd.DataFrame) -> None:
    params = dataclasses.replace(TRADING["InsideBar"], with_vwap=True)
    data = prepared(bars, params, archetypes.INSIDEBAR)
    with pytest.raises(ValueError, match="supplied no trade side"):
        filters.apply_context_filters(np.ones(len(data), dtype=np.bool_), data, params)


@pytest.mark.parametrize("cls", EVERY_CLASS)
@pytest.mark.parametrize(
    ("fields", "named"),
    [
        ({"with_trend": True, "trend_filter": trend.trends_mask([trend.Trend.UP])}, "trend_filter"),
        (
            {
                "with_higher_timeframe": True,
                "higher_timeframe_filter": higher_timeframe.sides_mask([higher_timeframe.Side.BELOW]),
            },
            "higher_timeframe_filter",
        ),
    ],
)
def test_a_side_filter_beside_the_absolute_filter_on_its_label_is_refused_on_every_class(
    cls: type[ArchetypeParams], fields: dict[str, object], named: str
) -> None:
    """With-trend and ``trend=UP`` together would quietly trade one side alone."""
    with pytest.raises(ValueError, match=rf"{named} is \d+ beside its side-relative filter"):
        cls(**fields)


@pytest.mark.parametrize("cls", EVERY_CLASS)
def test_the_vwap_side_filter_has_no_absolute_filter_to_clash_with(cls: type[ArchetypeParams]) -> None:
    params = cls(with_vwap=True, with_trend=True, with_higher_timeframe=True)  # type: ignore[call-arg]  # every params class takes its fields as keywords
    assert (params.with_trend, params.with_higher_timeframe, params.with_vwap) == (True, True, True)


@pytest.mark.parametrize("cls", [DeadCatParams, PullBackAndGoParams])
def test_a_one_sided_archetypes_own_vwap_condition_beside_the_vwap_filter_is_refused(
    cls: type[DeadCatParams | PullBackAndGoParams],
) -> None:
    """Both ask for the close on the archetype's one side of the VWAP, so together they are one gate twice."""
    assert cls(use_vwap=True).use_vwap
    assert cls(with_vwap=True).with_vwap
    with pytest.raises(ValueError, match="the same VWAP side"):
        cls(use_vwap=True, with_vwap=True)


def test_each_side_filter_counts_as_an_active_filter() -> None:
    plain = EmaCrossoverParams()
    assert active_context_filters(plain) == 0
    assert active_context_filters(dataclasses.replace(plain, with_trend=True, with_vwap=True)) == 2


def test_the_confluence_count_counts_side_filters_beside_the_phase(bars: pd.DataFrame) -> None:
    """The §M55 arms: at least two of the phase and the three side filters."""
    params = dataclasses.replace(
        TRADING["EmaCrossover"],
        phase_filter=timeofday.phases_mask([timeofday.SessionPhase.CASH_OPEN, timeofday.SessionPhase.MIDDAY]),
        with_trend=True,
        with_higher_timeframe=True,
        with_vwap=True,
        confluence_required=2,
    )
    archetype = archetypes.EMACROSSOVER
    data = prepared(bars, params, archetype)
    gates = filters.context_gates(data, params, lambda: archetype.long_side(data, params))
    raw = archetype.signal(data, TRADING["EmaCrossover"])
    counted = raw & (np.stack(gates).sum(axis=0) >= 2)

    assert len(gates) == 4
    assert np.array_equal(archetype.signal(data, params), counted)


@pytest.mark.parametrize("name", sorted(TRADING))
def test_every_series_a_side_filter_reads_is_built_into_the_dataset(name: str) -> None:
    archetype = archetypes.get(name)
    on = dataclasses.replace(TRADING[name], **dict.fromkeys(SIDE_FILTERS, True))
    spec = sweep.Grid.of(on, archetype=archetype).required_context()
    assert spec.trend_keys
    assert spec.higher_timeframe_keys
    assert spec.needs_vwap


@pytest.mark.parametrize("name", sorted(TRADING))
def test_a_labels_axes_are_live_under_its_side_filter_and_dead_otherwise(name: str) -> None:
    archetype = archetypes.get(name)
    sweep.Grid.of(
        dataclasses.replace(TRADING[name], with_trend=True), archetype=archetype, trend_slow_period=[50, 100]
    )
    sweep.Grid.of(
        dataclasses.replace(TRADING[name], with_higher_timeframe=True),
        archetype=archetype,
        higher_timeframe_period=[20, 50],
    )
    with pytest.raises(sweep.SweepError, match="trend_slow_period"):
        sweep.Grid.of(TRADING[name], archetype=archetype, trend_slow_period=[50, 100])


def test_a_side_filtered_row_leaves_the_reconciled_port() -> None:
    """No NinjaScript has the filter, so a combination using it is not the port any more."""
    assert archetypes.DEADCATBOUNCE.tier2 is Tier2Status.RECONCILED
    params = TRADING["DeadCatBounce"]
    assert (
        archetypes.DEADCATBOUNCE.tier2_for(dataclasses.replace(params, with_trend=True))
        is Tier2Status.TIER1_ONLY
    )
