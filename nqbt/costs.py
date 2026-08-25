"""Trading costs as an explicit choice, never an inherited default.

Every archetype's parameter class defaults ``commission_per_contract`` and ``slippage_ticks``
to zero. That is correct for NT8 reconciliation and wrong for every ranking, so the presets
here exist to make a caller say which one it means.

Why the defaults stay zero and what an uncosted sweep does to a result:
``docs/roadmap.md`` §M7b.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from nqbt.archetypes import Params

ParamsT = TypeVar("ParamsT", bound="Params")

COST_FIELDS = ("commission_per_contract", "slippage_ticks")
"""The parameter-class fields costs are carried in, named once."""


class CostError(ValueError):
    """Raised for a negative cost, or for params that cannot carry one."""


@dataclass(frozen=True, slots=True)
class TradingCosts:
    """Commission and slippage, in the units the parameter classes take."""

    commission_per_contract: float
    """Round-turn dollars per contract, charged once per leg on exit."""

    slippage_ticks: float
    """Ticks of adverse fill, applied per stop or market fill and never to a limit."""

    def __post_init__(self) -> None:
        """Reject a negative cost, which would pay the account to trade."""
        if self.commission_per_contract < 0.0 or self.slippage_ticks < 0.0:
            msg: str = (
                f"costs cannot be negative; got commission_per_contract="
                f"{self.commission_per_contract}, slippage_ticks={self.slippage_ticks}"
            )
            raise CostError(msg)

    @property
    def is_free(self) -> bool:
        """True when both components are zero, which no ranking may be read from."""
        return self.commission_per_contract == 0.0 and self.slippage_ticks == 0.0

    def apply(self, params: ParamsT) -> ParamsT:
        """Return ``params`` with these costs substituted, leaving every other field alone."""
        missing: list[str] = [f for f in COST_FIELDS if f not in params.__dataclass_fields__]
        if missing:
            msg: str = f"{type(params).__name__} has no {', '.join(missing)}; it cannot carry costs"
            raise CostError(msg)
        return dataclasses.replace(
            params,
            commission_per_contract=self.commission_per_contract,
            slippage_ticks=self.slippage_ticks,
        )


LIVE = TradingCosts(commission_per_contract=1.50, slippage_ticks=1.0)
"""The account this project trades: $1.50 round turn per contract, one tick of slippage."""

FREE = TradingCosts(commission_per_contract=0.0, slippage_ticks=0.0)
"""What the parameter classes already default to, named so that choosing it is visible.

Correct for reconciling against a Strategy Analyzer run with commission and slippage set to
zero. Never correct for ranking two combinations against each other.
"""
