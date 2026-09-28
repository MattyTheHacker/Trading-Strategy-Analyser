"""Path-dependent trade simulation -- ``nqbt/README.md`` § "Simulation".

One jitted function per strategy *archetype* -- per distinct entry/exit shape, not per
parameter combination. The market context these read is built by :mod:`nqbt.context`, and the
trade log they write is defined by :mod:`nqbt.trades`.
"""

from nqbt.sim.types import (
    DeadCatParams,
    ElasticBandParams,
    EmaCrossoverParams,
    EmaPullbackParams,
    InsideBarParams,
    OpeningRangeParams,
    PullBackAndGoParams,
    SqueezeBreakoutParams,
)

__all__ = [
    "DeadCatParams",
    "ElasticBandParams",
    "EmaCrossoverParams",
    "EmaPullbackParams",
    "InsideBarParams",
    "OpeningRangeParams",
    "PullBackAndGoParams",
    "SqueezeBreakoutParams",
]
