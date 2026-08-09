"""Path-dependent trade simulation.

One jitted function per strategy *archetype* -- per distinct entry/exit shape, not per
parameter combination. Different parameter values reuse the same compiled function.
"""

from nqbt.sim.types import (
    COLUMNS,
    EXIT_END_OF_DATA,
    EXIT_SESSION_CLOSE,
    EXIT_STOP,
    EXIT_TARGET,
    DeadCatParams,
    trades_to_frame,
)

__all__ = [
    "COLUMNS",
    "DeadCatParams",
    "EXIT_STOP",
    "EXIT_TARGET",
    "EXIT_SESSION_CLOSE",
    "EXIT_END_OF_DATA",
    "trades_to_frame",
]
