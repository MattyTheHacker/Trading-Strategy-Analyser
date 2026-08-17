"""Path-dependent trade simulation.

One jitted function per strategy *archetype* -- per distinct entry/exit shape, not per
parameter combination. Different parameter values reuse the same compiled function.

The market context these read is built by :mod:`nqbt.context`, and the trade log they
write is defined by :mod:`nqbt.trades`. Neither belongs here: the review layer needs both
and has no strategy at all.
"""


from typing import TYPE_CHECKING

from nqbt.sim.types import DeadCatParams, PullBackAndGoParams

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = ("DeadCatParams", "PullBackAndGoParams")
