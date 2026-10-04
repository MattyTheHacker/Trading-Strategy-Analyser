"""One stored shortlist's held-out logs, re-run on the bars it was swept on.

    uv run tools/campaign_exits.py --strategy InsideBarTrailing --rerun
    uv run tools/campaign_montecarlo.py --strategy InsideBarTrailing --rerun

The agreement with the stored row is reported rather than required --
``tools/README.md`` § "campaign_swept.py".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, resample, splice
from tools.campaign_null import series_moved, stored_for, stored_rows
from tools.campaign_report import log_key
from tools.campaign_shortlist import NET_PNL_TOLERANCE, rerun_group, source, swept_series

logger = logging.getLogger(__name__)

HELD_OUT = "holdout"
"""The window a gate-4 read measures, and so the bars every log built here has to run on."""

SWEPT_BARS = "swept_bars"
"""Whether a cell ran on the bars its stored rows were swept on, which an archive that gained
history earlier than its tail makes unrecoverable."""

RECONCILED = ("trades", "net_pnl")
"""What a re-run is read back against in the row the sweep stored for it; reported, not required."""

CELL_KEYS = ["root", "resolution"]
"""What one reconciliation row pools over, never across resolutions."""


def last_swept(stored: pd.DataFrame, bars: pd.DataFrame) -> pd.Timestamp:
    """Return the newest bar any of these stored rows was swept on, in the archive's own zone.

    ``save_sweep`` stores the stamp naive, and the spliced series is tz-aware.
    """
    return pd.Timestamp(stored["last_bar"].max()).tz_localize(bars.index.tz)


def on_swept_bars(stored: pd.DataFrame, block: pd.DataFrame, frame: pd.DataFrame) -> bool:
    """Return whether every row in ``block`` was swept on exactly the bars ``frame`` holds."""
    references = [stored_for(stored, row) for _, row in block.iterrows()]

    return all(ref is not None and not series_moved(ref, frame) for ref in references)


def bars_for(
    candidates: tuple[pd.DataFrame, ...],
    stored: pd.DataFrame,
    block: pd.DataFrame,
    minutes: int,
) -> tuple[pd.DataFrame, bool]:
    """Return the held-out frame to run, preferring the one these rows were swept on.

    Neither kind of frame is refused; which bars a cell ran on is reported beside its result
    instead.
    """
    frames: list[pd.DataFrame] = [resample.resample(source(bars, HELD_OUT), minutes) for bars in candidates]
    for frame in frames:
        if on_swept_bars(stored, block, frame):
            return frame, True

    return frames[-1], False


def candidate_bars(stored: pd.DataFrame, archive: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Return the archive cut back to where these rows were swept, then the archive as it stands.

    In that order, so :func:`bars_for` prefers the window a stored row was measured on and falls
    back to today's only where no truncation recovers it.
    """
    return swept_series(archive, last_swept(stored, archive)), archive


def stored_figures(row: pd.Series) -> dict[str, object]:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return what the sweep stored for one configuration, tagged so a re-run reads back against it."""
    return {f"stored_{field}": row[field] for field in RECONCILED}


def reconciliation(table: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Measure, per cell, how far a re-run reproduced the rows it was read back against.

    Read it before whatever the logs were re-run for: a cell reproducing nothing is a cell whose
    *levels* belong to this run rather than to the campaign that stored them.
    """
    if table.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for values, group in table.groupby(keys, dropna=False, observed=True):
        gap: pd.Series[float] = (group["net_pnl"] - group["stored_net_pnl"]).abs()
        same_net: pd.Series[bool] = gap <= group["stored_net_pnl"].abs() * NET_PNL_TOLERANCE
        rows.append(
            {
                **dict(zip(keys, values, strict=True)),
                "rows": len(group),
                SWEPT_BARS: bool(group[SWEPT_BARS].all()),
                "same_trades": int((group["trades"] == group["stored_trades"]).sum()),
                "same_net": int(same_net.sum()),
                "net_gap": float(gap.max()),
            },
        )

    return pd.DataFrame(rows)


def logs_for(
    name: str,
    rows: pd.DataFrame,
    root: str,
) -> tuple[dict[tuple[int, int], pd.DataFrame], pd.DataFrame]:
    """Return each shortlisted configuration's held-out log, keyed by its stored ids, and what it reproduced.

    Each block runs on the bars its rows were swept on, wherever those survive.
    """
    archetype: archetypes.Archetype = archetypes.get(name)
    stored: pd.DataFrame = stored_rows(name, root, HELD_OUT)
    archive: pd.DataFrame = splice.load_continuous(root)
    candidates: tuple[pd.DataFrame, ...] = candidate_bars(stored, archive)

    logs: dict[tuple[int, int], pd.DataFrame] = {}
    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        frame: pd.DataFrame
        swept: bool
        frame, swept = bars_for(candidates, stored, block, int(minutes))
        logger.info(
            "  %-4s %2dm  %2d configurations on %s bars, %s to %s",
            root,
            int(minutes),
            len(block),
            "their own swept" if swept else "today's",
            frame.index[0],
            frame.index[-1],
        )
        for row, summary, log in rerun_group(
            block,
            frame,
            archetype,
            root,
            int(minutes),
            context.PriceBasis.RAW,
        ):
            logs[log_key(row)] = log
            measured.append(
                {
                    **{column: row[column] for column in CELL_KEYS},
                    **stored_figures(row),
                    **{field: summary[field] for field in RECONCILED},
                    SWEPT_BARS: swept,
                },
            )

    return logs, reconciliation(pd.DataFrame(measured), CELL_KEYS)
