"""One stored shortlist's held-out logs, re-run on the bars it was swept on.

    ./.venv/Scripts/python.exe tools/campaign_exits.py --strategy InsideBarTrailing --rerun
    ./.venv/Scripts/python.exe tools/campaign_montecarlo.py --strategy InsideBarTrailing --rerun

A stored row belongs to the archive it was swept on, and extending the archive moves the 60/40
split under every campaign stored before it -- ``docs/roadmap.md`` § "Standing traps". That
leaves a gate-4 read with no log at all: ``tools/campaign_shortlist.py``'s ``verify`` refuses to
file one whose trade count or net P&L disagrees with the row it is filed against, so nothing can
be stored for a campaign swept before the extension.

The way round it that does not weaken that guard is to re-run the shortlist here and hand each
log to the caller instead of storing it, over the archive cut back to where it stood when the row
was swept. **The agreement is then reported rather than required** -- the weakening
``tools/campaign_flatten.py`` already makes, for the reason
``docs/findings/m41-flatten-timing.md`` § "The stored rows no longer reproduce" gives: a
decomposition or a bootstrap of one book does not rest on reproducing a figure measured months
ago, while which bars it ran on is part of the reading either way.

**Cutting back recovers one root and not the other**, so it is attempted rather than assumed and
:data:`SWEPT_BARS` says per cell which window was actually run.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_null import series_moved, stored_for, stored_rows
from tools.campaign_report import log_key
from tools.campaign_shortlist import NET_PNL_TOLERANCE, rerun_group, source, swept_series

from nqbt import archetypes, context, resample, splice

logger = logging.getLogger(__name__)

HELD_OUT = "holdout"
"""The window a gate-4 read measures, and so the bars every log built here has to run on."""

SWEPT_BARS = "swept_bars"
"""Whether a cell ran on the bars its stored rows were swept on, which an archive that gained
history earlier than its tail makes unrecoverable."""

RECONCILED = ("trades", "net_pnl")
"""What a re-run is read back against in the row the sweep stored for it.

**Reported and not required**, a deliberate weakening of the guard
``tools/campaign_shortlist.py``'s ``verify`` puts on a stored log, because nothing here is filed
against a stored summary -- ``docs/findings/m41-flatten-timing.md`` § "The stored rows no longer
reproduce"."""

CELL_KEYS = ["root", "resolution"]
"""What one reconciliation row pools over.

**Never across resolutions**, because a cell is recovered or not by its own bars: one figure
spanning two bar sizes would hide a root that reproduced at one of them and not the other."""


def last_swept(stored: pd.DataFrame, bars: pd.DataFrame) -> pd.Timestamp:
    """The newest bar any of these stored rows was swept on, in the archive's own zone.

    ``save_sweep`` stores the stamp naive, and the spliced series is tz-aware.
    """
    return pd.Timestamp(stored["last_bar"].max()).tz_localize(bars.index.tz)


def on_swept_bars(stored: pd.DataFrame, block: pd.DataFrame, frame: pd.DataFrame) -> bool:
    """Whether every row in ``block`` was swept on exactly the bars ``frame`` holds."""
    references = [stored_for(stored, row) for _, row in block.iterrows()]

    return all(ref is not None and not series_moved(ref, frame) for ref in references)


def bars_for(
    candidates: tuple[pd.DataFrame, ...],
    stored: pd.DataFrame,
    block: pd.DataFrame,
    minutes: int,
) -> tuple[pd.DataFrame, bool]:
    """The held-out frame to run, preferring the one these rows were swept on.

    An archive that only grew at the end is recovered by cutting it back; one that gained history
    earlier moves the 60/40 split and cannot be. Neither is refused -- which bars a cell ran on
    is reported beside its result instead.
    """
    frames: list[pd.DataFrame] = [resample.resample(source(bars, HELD_OUT), minutes) for bars in candidates]
    for frame in frames:
        if on_swept_bars(stored, block, frame):
            return frame, True

    return frames[-1], False


def candidate_bars(stored: pd.DataFrame, archive: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """The archive cut back to where these rows were swept, then the archive as it stands.

    In that order, so :func:`bars_for` prefers the window a stored row was measured on and falls
    back to today's only where no truncation recovers it.
    """
    return swept_series(archive, last_swept(stored, archive)), archive


def stored_figures(row: pd.Series) -> dict[str, object]:  # type: ignore[type-arg]  # duckdb's dtypes
    """What the sweep stored for one configuration, tagged so a re-run reads back against it."""
    return {f"stored_{field}": row[field] for field in RECONCILED}


def reconciliation(table: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per cell, how far a re-run reproduced the rows it was read back against.

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
    """Each shortlisted configuration's held-out log, keyed by its stored ids, and what it reproduced.

    Grouped by resolution because the resample and the prepared dataset are what a block shares,
    and the bars a cell runs on are the ones its rows were swept on wherever that survives. The
    bars are :data:`~nqbt.context.PriceBasis.RAW`, which is what ``load_continuous`` returns and
    what the sweep measured them as -- ``docs/roadmap.md`` § "The build spec's three loose ends".
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
