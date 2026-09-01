"""Free-text context on a trade: stored, shown, and never an input to a statistic.

Why a trade was taken, what was going on at the time, a screenshot to look at later. All of it
is worth keeping and none of it may reach a ``groupby``. A note is written after the fact,
knowing the outcome, so a loser attracts "I was impatient" and a winner attracts "clean setup";
stratifying by one would rediscover the outcome and present it as a finding --
``docs/roadmap.md`` §M11.5.

**The exclusion is structural rather than intended.** Notes live here, in a sidecar keyed by
``trade_id``, and never as columns on a trade log or on an annotation. :func:`alongside` is the
one join that attaches them, for a viewer or a per-trade export, and :func:`check_excluded` is
what :mod:`nqbt.annotate`, :mod:`nqbt.review` and :mod:`nqbt.guard` call to refuse a frame that
carries one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Sequence


__all__: Sequence[str] = [
    "COLUMNS",
    "KEY",
    "TEXT_COLUMNS",
    "Notes",
    "NotesError",
    "alongside",
    "check_excluded",
    "empty",
    "read",
    "record",
    "write",
]

KEY: str = "trade_id"  # What a sidecar is keyed by: the same trade id every producer writes.
TEXT_COLUMNS: tuple[str, ...] = ("note", "screenshot")
COLUMNS: tuple[str, ...] = (KEY, *TEXT_COLUMNS)  # A sidecar's columns as they are stored, in file order.


class NotesError(ValueError):
    """Raised for a sidecar that is not keyed by a unique trade, or free text where none may go."""


@dataclass(frozen=True, slots=True)
class Notes:
    """Discretionary context on trades, keyed by ``trade_id`` and holding nothing else."""

    frame: pd.DataFrame
    """One row per noted trade, indexed by ``trade_id``, carrying :data:`TEXT_COLUMNS`."""

    def __post_init__(self) -> None:
        """Refuse anything that is not a sidecar keyed by a unique trade."""
        missing: list[str] = [name for name in TEXT_COLUMNS if name not in self.frame.columns]
        if missing:
            msg: str = f"a sidecar is missing column(s) {missing}; the shape is nqbt.notes.COLUMNS"
            raise NotesError(msg)

        if self.frame.index.name != KEY:
            msg = f"a sidecar is keyed by {KEY}; this frame's index is named {self.frame.index.name!r}"
            raise NotesError(msg)

        if not self.frame.index.is_unique:
            repeated: list[int] = sorted(self.frame.index[self.frame.index.duplicated()].unique().tolist())
            msg = (
                f"trade(s) {repeated} carry more than one note; a duplicate key fans a join out "
                f"into extra rows, which would move every number computed over the result"
            )
            raise NotesError(msg)

    @property
    def trades(self) -> int:
        """Trades a note was written on."""
        return len(self.frame)

    @override
    def __str__(self) -> str:
        """Say how many trades carry a note, and how many of those name a screenshot."""
        shots: int = int(self.frame["screenshot"].notna().sum()) if self.trades else 0
        return f"{self.trades} trade(s) noted, {shots} naming a screenshot"


def empty() -> Notes:
    """Build an empty sidecar, in the dtypes a populated one carries."""
    index: pd.MultiIndex = pd.Index([], name=KEY, dtype="int64")
    columns = {name: pd.array([], dtype="string") for name in TEXT_COLUMNS}
    return Notes(frame=pd.DataFrame(columns, index=index))


def record(notes: Notes, trade_id: int, note: str, screenshot: str | None = None) -> Notes:
    """Return ``notes`` with one trade's context written, replacing anything already on it."""
    text: str = note.strip()
    if not text:
        msg: str = f"trade {trade_id}'s note is empty; a trade with nothing to say carries no row"
        raise NotesError(msg)
    written: pd.DataFrame = pd.DataFrame(
        {
            "note": pd.array([text], dtype="string"),
            "screenshot": pd.array([screenshot], dtype="string"),
        },
        index=pd.Index([int(trade_id)], name=KEY, dtype="int64"),
    )
    kept: pd.DataFrame = notes.frame.drop(index=int(trade_id), errors="ignore")
    return Notes(frame=pd.concat([kept, written]).sort_index())


def read(path: Path | str) -> Notes:
    """Read a sidecar CSV, as :func:`write` leaves one or as it is kept by hand."""
    raw: pd.DataFrame = pd.read_csv(path, dtype="string")
    missing: list[str] = [name for name in COLUMNS if name not in raw.columns]
    if missing:
        msg: str = f"{path}: not a notes sidecar -- missing column(s) {missing}. The shape is nqbt.notes.COLUMNS."
        raise NotesError(msg)

    unknown: list[str] = [name for name in raw.columns if name not in COLUMNS]
    if unknown:
        msg = (
            f"{path}: unknown column(s) {unknown}. A sidecar holds exactly {list(COLUMNS)}, so a "
            f"mistyped header is refused rather than read as a note nobody wrote."
        )
        raise NotesError(msg)

    return Notes(frame=_keyed(raw, source=str(path)))


def write(notes: Notes, path: Path | str) -> None:
    """Write a sidecar to CSV, creating the directory if it is not already there."""
    destination: Path = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    notes.frame.to_csv(destination, index=True)


def alongside(frame: pd.DataFrame, notes: Notes) -> pd.DataFrame:
    """Attach each trade's context to ``frame``, for a viewer or a per-trade export.

    **The one join that puts free text beside a number**, and nothing computing a statistic may
    call it. ``frame`` is keyed by ``trade_id`` as a column or as its index; a leg-level log
    carries the trade's note on every leg of it.
    """
    check_excluded(frame, what="the frame notes are being attached to")
    if KEY not in frame.columns and frame.index.name != KEY:
        msg: str = (
            f"this frame is keyed by neither a {KEY} column nor a {KEY} index, so there is no "
            f"saying which note belongs to which row"
        )
        raise NotesError(msg)

    ids: pd.Series[int] = frame[KEY] if KEY in frame.columns else frame.index.to_series()
    attached: pd.DataFrame = frame.copy()

    for name in TEXT_COLUMNS:
        attached[name] = ids.map(notes.frame[name]).astype("string")

    return attached


def check_excluded(frame: pd.DataFrame, what: str) -> None:
    """Refuse a frame carrying free text into anything that evaluates a trade.

    Called at each door into the evaluation path rather than left to a convention, because a
    note merged onto a trade log or an annotation is one ``groupby`` away from a finding that
    restates the outcome it was written after -- ``docs/roadmap.md`` §M11.5.
    """
    found: list[str] = [name for name in TEXT_COLUMNS if name in frame.columns]
    if not found:
        return

    msg: str = (
        f"{what} carries the free-text column(s) {found}, which nothing evaluating a trade may "
        f"see: a note is written knowing the outcome, so a stratification by one would "
        f"rediscover that outcome. Notes live in an nqbt.notes sidecar and attach only at "
        f"nqbt.notes.alongside."
    )
    raise NotesError(msg)


def _keyed(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    """Key the parsed rows by ``trade_id``, refusing one that is not a whole number."""
    ids: pd.Series[float] = pd.to_numeric(raw[KEY], errors="coerce")
    unreadable: pd.Series[bool] = ids.isna() | (ids % 1 != 0)
    if unreadable.any():
        row: int = int(unreadable.to_numpy().argmax())
        msg: str = f"{source}: {KEY} must be a whole number on every row; row {row} carries {raw[KEY].iloc[row]!r}"
        raise NotesError(msg)
    frame: pd.DataFrame = raw[list(TEXT_COLUMNS)].copy()
    frame.index = pd.Index(ids.astype("int64"), name=KEY)
    return frame
