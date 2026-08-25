"""The trade-log schema, shared by every producer.

The contract between the jitted simulation and the importer for real NT8 executions, so a
statistic computed over one means the same thing computed over the other. Knows nothing about
strategies, bars or indicators.

**One row per leg exit, not per trade.** Results arrive as a plain ``float64``
:class:`LegMatrix` rather than a record array, because that is what Numba handles without
friction; :data:`COLUMNS` is the only place the column order is defined. Schema reasoning:
``docs/roadmap.md`` §M9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray

EXIT_STOP = 0.0
EXIT_TARGET = 1.0
EXIT_SESSION_CLOSE = 2.0
EXIT_END_OF_DATA = 3.0
"""Position still open when the series ran out.

Liquidated at the final bar's close and labelled distinctly, so the stats layer can exclude it
rather than mistake it for a real exit.
"""
EXIT_SIGNAL = 4.0
"""A rule-driven exit with no bracket level of its own. Produced only by EmaCrossover."""

EXIT_REASONS = {
    EXIT_STOP: "stop",
    EXIT_TARGET: "target",
    EXIT_SESSION_CLOSE: "session_close",
    EXIT_END_OF_DATA: "end_of_data",
    EXIT_SIGNAL: "signal",
}
"""Reasons the *simulator* can give. An imported trade is not restricted to these --
``docs/roadmap.md`` §M9.
"""

EXIT_CODES = np.array(sorted(EXIT_REASONS), dtype=np.float64)
"""The same codes as an array, so :func:`validate_legs` can test a column against them."""

LONG = 1.0
SHORT = -1.0
"""Sign of the position, carried per row rather than per run."""

SOURCES = ("sim", "manual")
"""Where a row came from. Real and simulated trades share one DuckDB table."""

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
"""Columns a producer may legitimately leave empty. Which, and why each: ``docs/roadmap.md``
§M9. Everything else is required on every row from every producer.
"""

REQUIRED = [c for c in SCHEMA if c not in NULLABLE]

REQUIRED_INDICES = tuple(COLUMNS.index(c) for c in COLUMNS if c not in NULLABLE)
""":data:`REQUIRED` minus the two :data:`TAGS`, which cannot be in a ``float64`` matrix."""


class TradeSchemaError(ValueError):
    """Raised when a trade log does not meet the schema in this module."""


class LegMatrix(NamedTuple):
    """The jitted simulation's raw output: a preallocated matrix and how much of it is real.

    ``matrix`` is ``(rows, N_COLUMNS)`` ``float64`` in :data:`COLUMNS` order and sized to an
    upper bound, so only the first ``count`` rows mean anything.
    """

    matrix: FloatArray
    count: int


def validate_legs(legs: LegMatrix) -> LegMatrix:
    """Check a raw leg matrix against the schema, returning it unchanged.

    The producer boundary for a caller that never builds the frame: the same invariants
    :func:`validate` asserts, plus ``exit_reason`` against :data:`EXIT_REASONS`, which only a
    matrix can be held to.
    """
    matrix, count = legs
    if matrix.ndim != 2 or matrix.shape[1] != N_COLUMNS:  # noqa: PLR2004
        msg = f"a leg matrix is (rows, {N_COLUMNS}); got {matrix.shape}. The order is nqbt.trades.COLUMNS."
        raise TradeSchemaError(msg)
    if count > matrix.shape[0]:
        msg = f"count {count} exceeds the {matrix.shape[0]} rows allocated"
        raise TradeSchemaError(msg)
    if count == 0:
        return legs

    rows = matrix[:count]
    # Column by column, stopping at the first failure: ``rows[:, REQUIRED_INDICES]`` would
    # copy ten columns on every combination of a sweep.
    for index in REQUIRED_INDICES:
        if np.isnan(rows[:, index]).any():
            _raise_matrix_nulls(rows)

    direction = rows[:, C_DIRECTION]
    if not ((direction == LONG) | (direction == SHORT)).all():
        msg = (
            f"direction must be {LONG} (long) or {SHORT} (short); found "
            f"{sorted(set(direction) - {LONG, SHORT})}"
        )
        raise TradeSchemaError(msg)
    if (rows[:, C_QUANTITY] <= 0).any():
        msg = (
            "quantity must be positive on every row; a short position is expressed by "
            "direction, not by a negative size"
        )
        raise TradeSchemaError(msg)
    if (rows[:, C_LEG] < 1).any():
        msg = "leg numbering starts at 1"
        raise TradeSchemaError(msg)
    reasons = rows[:, C_EXIT_REASON]
    if not np.isin(reasons, EXIT_CODES).all():
        unknown = sorted(set(np.unique(reasons)) - set(EXIT_REASONS))
        msg = f"unknown exit_reason code(s) {unknown}; expected one of {sorted(EXIT_REASONS)}"
        raise TradeSchemaError(msg)
    return legs


def _raise_matrix_nulls(rows: FloatArray) -> None:
    """Name the offending columns now that we know there is at least one."""
    names = [c for c in COLUMNS if c not in NULLABLE]
    counts = np.isnan(rows[:, REQUIRED_INDICES]).sum(axis=0)
    offenders = [(n, int(k)) for n, k in zip(names, counts, strict=True) if k]
    raise TradeSchemaError(
        "null values in non-nullable column(s): "
        + ", ".join(f"{c} ({n})" for c, n in offenders)
        + ". Columns that may be null are listed in nqbt.trades.NULLABLE.",
    )


def trades_to_frame(
    matrix: FloatArray,
    count: int,
    index: pd.DatetimeIndex | None = None,
    *,
    instrument: str,
    source: str = "sim",
) -> pd.DataFrame:
    """Turn the raw simulation output into a labelled frame.

    ``count`` is the number of rows actually written; the matrix is preallocated to an upper
    bound and the tail is undefined. ``instrument`` is required rather than defaulted, since
    NQ and MNQ differ 10x in tick value.
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

    Called at every producer's boundary, and returning the frame so it can wrap a producer's
    return expression. Written to short-circuit because it runs once per combination inside a
    sweep -- ``docs/roadmap.md`` §M9 has the measurement and the microbenchmarking trap.
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
        # An integer column cannot hold a null, so scanning one tests numpy, not the producer.
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
