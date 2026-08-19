"""The trade-log schema, shared by every producer.

Two things will write trade logs: the jitted simulation, and an importer for real NT8
executions. This module is the contract between them, so that a statistic computed over
one means the same thing computed over the other. It deliberately knows nothing about
strategies, bars or indicators -- :mod:`nqbt.stats` and the review layer depend on this
and on nothing else.

Results come out of the jitted simulation as a plain ``float64`` matrix rather than a
record array, because that is what Numba handles without friction. :data:`COLUMNS` is the
only place the column order is defined -- read it through :func:`trades_to_frame` rather
than indexing by number.

One row per **leg exit**, not per trade. A four-leg entry that scales out at three targets
and trails the runner produces four rows sharing a ``trade_id``, which lets the stats layer
aggregate either way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import numpy as np

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
EXIT_SIGNAL = 4.0
"""A rule-driven exit -- "close when the MAs cross back" -- with no bracket level of its
own. DeadCatBounce has no such exit and never produces this; it exists for EMA crossover
(M18) and ``InsideBarTrailing.cs``, both of which do."""

EXIT_REASONS = {
    EXIT_STOP: "stop",
    EXIT_TARGET: "target",
    EXIT_SESSION_CLOSE: "session_close",
    EXIT_END_OF_DATA: "end_of_data",
    EXIT_SIGNAL: "signal",
}
"""Reasons the *simulator* can give. An imported trade is not restricted to these.

NT8's executions grid names its exits ``Stop1..4`` and ``Exit``, which do not map onto
this enum without inventing information. :func:`validate` therefore requires
``exit_reason`` to be a string, not a member of this set.
"""

LONG = 1.0
SHORT = -1.0
"""Sign of the position, carried per row rather than per run.

Per row because a bidirectional archetype takes both sides within one run, and because a
real trading history certainly does. Every P&L and MAE/MFE sign convention downstream
reads this rather than assuming the short side the first archetype happened to have.
"""

SOURCES = ("sim", "manual")
"""Where a row came from. Real and simulated trades share one DuckDB table, so without a
tag one careless ``GROUP BY`` averages a backtest into a trading record."""

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
    "direction",
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
    C_DIRECTION,
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


TAGS = ["source", "instrument"]
"""Per-row strings that cannot live in a ``float64`` matrix, prepended by
:func:`trades_to_frame`. Constant for one simulated run; genuinely varying for an imported
history that spans both roots."""

SCHEMA = TAGS + COLUMNS

NULLABLE = frozenset(
    {
        "entry_bar",
        "exit_bar",
        "bars_held",
        "initial_stop",
        "target_price",
        "risk_points",
        "r_multiple",
        "mae_points",
        "mfe_points",
        "ambiguous_bar",
    },
)
"""Columns a producer may legitimately leave empty, and why each one.

Stated here so the nullability is a documented property rather than something discovered
by a ``NaN`` reaching a chart:

- ``entry_bar`` / ``exit_bar`` / ``bars_held`` -- positional indices into a specific bar
  series. A real fill has a timestamp but no bar number until one is matched to it.
- ``initial_stop`` / ``target_price`` / ``risk_points`` / ``r_multiple`` -- need the
  *planned* levels. Deliberately absent on imported trades: the only stop levels the
  Control Center log records are ATM-template defaults dragged to intent seconds later,
  so a risk computed from them is wrong by an order of magnitude.
- ``mae_points`` / ``mfe_points`` -- need the bars the trade was open across.
- ``ambiguous_bar`` -- a simulator-only concept. A real fill is not ambiguous; it happened.

Everything else is required on every row from every producer.
"""

REQUIRED = [c for c in SCHEMA if c not in NULLABLE]


class TradeSchemaError(ValueError):
    """Raised when a trade log does not meet the schema in this module."""


def trades_to_frame(
    matrix: np.ndarray,
    count: int,
    index: pd.DatetimeIndex | None = None,
    *,
    instrument: str,
    source: str = "sim",
) -> pd.DataFrame:
    """Turn the raw simulation output into a labelled frame.

    ``count`` is the number of rows actually written; the matrix is preallocated to an
    upper bound and the tail is undefined.

    ``instrument`` is required rather than defaulted because a trade log without it cannot
    be summed in dollars -- NQ and MNQ differ 10x in tick value -- and a default would make
    the wrong answer the easy one.
    """
    frame = pd.DataFrame(matrix[:count], columns=COLUMNS)
    for name in ("trade_id", "leg", "entry_bar", "exit_bar", "quantity", "bars_held"):
        frame[name] = frame[name].astype("int64")
    frame["ambiguous_bar"] = frame["ambiguous_bar"].astype(bool)
    frame["exit_reason"] = frame["exit_reason"].map(EXIT_REASONS).astype("string")

    if index is not None:
        frame.insert(2, "entry_time", index[frame["entry_bar"].to_numpy()])
        frame.insert(3, "exit_time", index[frame["exit_bar"].to_numpy()])

    frame.insert(0, "instrument", pd.array([instrument] * count, dtype="string"))
    frame.insert(0, "source", pd.array([source] * count, dtype="string"))
    return frame


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    """Check a trade log against the schema, returning it unchanged.

    Called at every producer's boundary. A schema that is only a convention drifts the
    first time someone adds a column, and the drift shows up as a statistic quietly
    computed over the wrong population rather than as an error.

    Returns the frame so it can wrap a producer's return expression.

    This runs once per parameter combination inside a sweep, so it is written to
    short-circuit: every check is a whole-column test that stops at the first failure,
    and the per-row accounting that makes a good error message is only paid for once
    there is an error to describe. Measured end to end on a 12-combination sweep it costs
    **1.3%**; the obvious form -- ``frame[REQUIRED].isna().sum()`` plus ``isin`` -- costs
    9.4%, which is the wrong direction in a sweep whose bottleneck is already pandas.

    Beware of microbenchmarking this by validating one frame repeatedly:
    ``Series.hasnans`` is a cached property, so the second call onwards is free and the
    result is meaningless. Every combination validates a frame it has just built.
    """
    missing = [c for c in SCHEMA if c not in frame.columns]
    if missing:
        msg = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise TradeSchemaError(
            msg,
        )
    if frame.empty:
        return frame

    for name in REQUIRED:
        column = frame[name]
        # An integer column cannot hold a null, so scanning one tests numpy rather than
        # the producer. Skipping the three of them is a third of this loop's cost.
        if column.dtype.kind not in "iu" and column.hasnans:
            _raise_nulls(frame)

    direction = frame["direction"].to_numpy()
    if not ((direction == LONG) | (direction == SHORT)).all():
        msg = (
            f"direction must be {LONG} (long) or {SHORT} (short); found "
            f"{sorted(set(direction) - {LONG, SHORT})}"
        )
        raise TradeSchemaError(
            msg,
        )
    unknown = set(frame["source"].unique()) - set(SOURCES)
    if unknown:
        msg = f"unknown source(s) {sorted(unknown)}; expected one of {SOURCES}"
        raise TradeSchemaError(msg)
    if (frame["quantity"].to_numpy() <= 0).any():
        msg = (
            "quantity must be positive on every row; a short position is expressed by "
            "direction, not by a negative size"
        )
        raise TradeSchemaError(
            msg,
        )
    if (frame["leg"].to_numpy() < 1).any():
        msg = "leg numbering starts at 1"
        raise TradeSchemaError(msg)
    return frame


def _raise_nulls(frame: pd.DataFrame) -> None:
    """Count the nulls properly now that we know there is at least one."""
    counts = frame[REQUIRED].isna().sum()
    offenders = counts[counts > 0]
    raise TradeSchemaError(
        "null values in non-nullable column(s): "
        + ", ".join(f"{c} ({n})" for c, n in offenders.items())
        + ". Columns that may be null are listed in nqbt.trades.NULLABLE.",
    )
