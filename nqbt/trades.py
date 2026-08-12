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
