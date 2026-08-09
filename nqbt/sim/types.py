"""Parameter sets and the trade-record layout shared by every archetype.

Results come out of the jitted simulation as a plain ``float64`` matrix rather than a
record array, because that is what Numba handles without friction. :data:`COLUMNS` is the
only place the column order is defined -- read it through :func:`trades_to_frame` rather
than indexing by number.

One row per **leg exit**, not per trade. A four-leg entry that scales out at three targets
and trails the runner produces four rows sharing a ``trade_id``, which lets the stats layer
aggregate either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

import numpy as np
import pandas as pd

EXIT_STOP = 0.0
EXIT_TARGET = 1.0
EXIT_SESSION_CLOSE = 2.0
EXIT_END_OF_DATA = 3.0
"""Position still open when the series ran out.

The series does not necessarily end on a session close -- the front contract's export can
stop mid-session -- so without this a trade would simply vanish from the log and its P&L
would go unaccounted. Liquidated at the final bar's close and labelled distinctly so the
stats layer can exclude it rather than mistake it for a real exit.
"""

EXIT_REASONS = {
    EXIT_STOP: "stop",
    EXIT_TARGET: "target",
    EXIT_SESSION_CLOSE: "session_close",
    EXIT_END_OF_DATA: "end_of_data",
}

COLUMNS = [
    "trade_id",
    "leg",
    "entry_bar",
    "exit_bar",
    "entry_price",
    "exit_price",
    "initial_stop",
    "target_price",
    "quantity",
    "exit_reason",
    "gross_pnl",
    "commission",
    "net_pnl",
    "r_multiple",
    "risk_points",
    "mae_points",
    "mfe_points",
    "bars_held",
    "ambiguous_bar",
]

N_COLUMNS = len(COLUMNS)

# Column indices, used inside the jitted loop where names are not available.
(
    C_TRADE_ID,
    C_LEG,
    C_ENTRY_BAR,
    C_EXIT_BAR,
    C_ENTRY_PRICE,
    C_EXIT_PRICE,
    C_INITIAL_STOP,
    C_TARGET_PRICE,
    C_QUANTITY,
    C_EXIT_REASON,
    C_GROSS_PNL,
    C_COMMISSION,
    C_NET_PNL,
    C_R_MULTIPLE,
    C_RISK_POINTS,
    C_MAE,
    C_MFE,
    C_BARS_HELD,
    C_AMBIGUOUS,
) = range(N_COLUMNS)


@dataclass(slots=True)
class DeadCatParams:
    """Rule set for the DeadCatBounce archetype.

    Mirrors the NinjaScript's properties: booleans switch filters on and off, numbers set
    periods and sizes. Defaults are exactly the NT8 ``SetDefaults`` values so that an
    unmodified instance reproduces the live strategy.
    """

    ema_period: int = 11
    slow_sma_period: int = 155
    fast_sma_period: int = 80
    order_quantity: int = 4

    use_ema: bool = True
    use_slow_sma: bool = False
    use_fast_sma: bool = True
    use_vwap: bool = False
    require_previous_green: bool = True
    require_new_high: bool = True

    tp_multiplier: float = 1.0
    """Scales every leg's target. ``TPMultiplier`` in the NinjaScript."""

    max_risk_ticks: int = 250
    """Reject the signal when ``stop - trigger`` exceeds this many **ticks**.

    ``MaxRiskPerTrade`` is compared against ``risk > maxRiskPerTrade * TickSize``, so it is
    a tick count rather than a dollar amount -- 250 ticks is 62.5 MNQ points, not $250."""

    bars_required_to_trade: int = 200
    stop_offset_ticks: int = 2
    """Ticks beyond the signal bar's high for the stop. Hardcoded as 2 in the NinjaScript."""

    entry_offset_ticks: int = 2
    """Ticks below the close used to cap the entry trigger.

    The trigger is ``min(Low[0], Close[0] - 2 ticks)``. An inverted hammer closes near its
    low by construction, so the close-based term usually wins and drags the trigger below
    the bar's low, which makes the fill meaningfully harder to get."""

    ambiguity_policy: int = 1
    """How a bar holding both the stop and a target is resolved.

    ``1`` fills whichever level sits nearer the bar's open, which is what NT8 does and is
    therefore the default -- it is the only setting that keeps Tier 1 and Tier 2 aligned.
    ``0`` assumes the worst case, the stop taking the whole position, which is *more*
    pessimistic than NT8 rather than equal to it.

    Worth sweeping as an axis: the spread between the two is a direct measure of how much
    of a candidate's edge rests on an assumption the bar data cannot settle. See
    :func:`nqbt.sim.deadcat._targets_reached_first`."""

    fill_limit_on_touch: bool = False
    """Whether a profit target fills when price merely reaches it.

    ``IsFillLimitOnTouch = false`` in the NinjaScript, so the default is that a limit must
    be traded *through* to fill. Leaving this on inflates results: it hands you every
    target the market touched to the tick and then reversed away from."""

    block_entry_at_session_close: bool = True
    """Whether a signal on the session's final bar is skipped."""

    ratchet_lag: int = 0
    """Which bar's high the trailing stop references at each bar close.

    ``0`` reads the just-closed bar's high -- ``High[0]``, what the NinjaScript does.
    ``1`` reads the bar before it, which an earlier revision of the strategy used and which
    holds trades roughly a third longer. Left exposed because the two behave like genuinely
    different strategies and the comparison is worth sweeping."""

    target_r_multiples: tuple[float, ...] = (1.0, 1.5, 2.0, float("nan"))
    """Per-leg profit targets in R. ``nan`` marks a runner with no target -- S4 in the
    NinjaScript, which exits only via the trailing stop or the session close."""

    # -- costs, absent from the NinjaScript but required for an honest backtest --
    commission_per_contract: float = 0.0
    """Round-turn commission per contract, charged once per leg on exit."""
    slippage_ticks: float = 0.0
    """Adverse slippage on market and stop orders. Never applied to limit targets,
    matching NT8, where the ``Slippage`` property does not affect limit fills."""

    # -- options the spec asks for that the NinjaScript does not implement --
    # Kept off by default so the port stays faithful until validated against NT8.
    min_reward_risk: float = 0.0
    """Pre-trade gate: skip the signal unless the furthest target clears this ratio."""

    def __post_init__(self) -> None:
        if self.order_quantity < len(self.target_r_multiples):
            raise ValueError(
                f"order_quantity {self.order_quantity} cannot fill "
                f"{len(self.target_r_multiples)} legs; NT8 caps this with a Range(4, ...) "
                "attribute on OrderQuantity"
            )
        for name in ("ema_period", "slow_sma_period", "fast_sma_period"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    @property
    def leg_quantities(self) -> tuple[int, ...]:
        """Contracts per leg, with the remainder on the last leg.

        ``baseQuantity = orderQuantity / 4`` with integer division, then
        ``baseQuantity + remainder`` on S4 -- so 10 contracts split 2/2/2/4, not 3/3/2/2.
        """
        n = len(self.target_r_multiples)
        base = self.order_quantity // n
        remainder = self.order_quantity % n
        return tuple([base] * (n - 1) + [base + remainder])

    def as_dict(self) -> dict:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value
        return out


def trades_to_frame(
    matrix: np.ndarray, count: int, index: pd.DatetimeIndex | None = None
) -> pd.DataFrame:
    """Turn the raw simulation output into a labelled frame.

    ``count`` is the number of rows actually written; the matrix is preallocated to an
    upper bound and the tail is undefined.
    """
    frame = pd.DataFrame(matrix[:count], columns=COLUMNS)
    for name in ("trade_id", "leg", "entry_bar", "exit_bar", "quantity", "bars_held"):
        frame[name] = frame[name].astype("int64")
    frame["ambiguous_bar"] = frame["ambiguous_bar"].astype(bool)
    frame["exit_reason"] = frame["exit_reason"].map(EXIT_REASONS).astype("string")

    if index is not None:
        frame.insert(2, "entry_time", index[frame["entry_bar"].to_numpy()])
        frame.insert(3, "exit_time", index[frame["exit_bar"].to_numpy()])
    return frame
