"""Costs must be chosen, and choosing them must not disturb anything else."""

from __future__ import annotations

import dataclasses

import pytest

from nqbt import costs
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

ALL_PARAMS = (DeadCatParams, EmaCrossoverParams, PullBackAndGoParams)


@pytest.mark.parametrize("params_cls", ALL_PARAMS)
def test_every_archetype_defaults_to_free_so_a_ranking_needs_an_explicit_choice(params_cls):
    params = params_cls()
    assert params.commission_per_contract == 0.0
    assert params.slippage_ticks == 0.0


@pytest.mark.parametrize("params_cls", ALL_PARAMS)
def test_apply_sets_both_costs_and_leaves_every_other_field_alone(params_cls):
    before = params_cls()
    after = costs.LIVE.apply(before)

    assert after.commission_per_contract == costs.LIVE.commission_per_contract
    assert after.slippage_ticks == costs.LIVE.slippage_ticks

    untouched = [f.name for f in dataclasses.fields(before) if f.name not in costs.COST_FIELDS]
    assert untouched, "expected the parameter class to have fields besides the two costs"
    for name in untouched:
        assert getattr(after, name) == getattr(before, name), name


def test_apply_does_not_mutate_the_params_it_was_given():
    before = DeadCatParams()
    costs.LIVE.apply(before)
    assert before.commission_per_contract == 0.0


def test_live_is_the_real_account_and_free_is_not():
    assert costs.LIVE.commission_per_contract == 1.50
    assert costs.LIVE.slippage_ticks == 1.0
    assert not costs.LIVE.is_free
    assert costs.FREE.is_free


def test_a_cost_that_is_only_half_zero_is_not_free():
    assert not costs.TradingCosts(commission_per_contract=0.0, slippage_ticks=1.0).is_free
    assert not costs.TradingCosts(commission_per_contract=1.5, slippage_ticks=0.0).is_free


@pytest.mark.parametrize(
    ("commission", "slippage"),
    [(-0.01, 0.0), (0.0, -1.0), (-1.0, -1.0)],
)
def test_negative_costs_raise(commission, slippage):
    with pytest.raises(costs.CostError, match="cannot be negative"):
        costs.TradingCosts(commission_per_contract=commission, slippage_ticks=slippage)


def test_params_without_cost_fields_raise_naming_what_is_missing():
    @dataclasses.dataclass(frozen=True, slots=True)
    class Costless:
        ema_period: int = 9

        def as_dict(self) -> dict:
            return dataclasses.asdict(self)

    with pytest.raises(costs.CostError, match="commission_per_contract"):
        costs.LIVE.apply(Costless())
