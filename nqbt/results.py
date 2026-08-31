"""Persist sweep results to DuckDB.

One database accumulates every sweep, so shortlisting is a SQL question rather than a directory
of files to glob. Each run gets a row in ``sweeps`` and its combinations land in ``combos``
tagged with that id.

**One ``sweeps`` row is one dataset** -- one strategy, one resolution, one contract -- because
``bars``/``first_bar``/``last_bar`` are properties of a dataset; ``batch_id`` says which rows
were one experiment. A table grows to fit whatever columns the frame carries, so a new
statistic, a new parameter and a second parameter class all need no migration; the axis columns
are the exception, migrated up front so they exist before an insert. Reasoning:
``docs/roadmap.md`` §M17.
"""

from __future__ import annotations

import json
import logging
import platform
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import duckdb

from nqbt import paths

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import pandas as pd

logger = logging.getLogger(__name__)


class ResultsError(ValueError):
    """Raised when a frame cannot be stored without losing something it carries."""


AXIS_COLUMNS: dict[str, str] = {
    "strategy": "VARCHAR",
    "resolution": "BIGINT",
    "contract": "VARCHAR",
    "tier2": "VARCHAR",
}
"""The axes that sit *above* a :class:`~nqbt.context.Dataset`, and their storage types.

On **both** tables: on ``sweeps`` to describe the run, on ``combos`` so a query can filter or
group without a join. Migrated explicitly, unlike a new statistic -- ``docs/roadmap.md`` §M17.
"""

NULL_MEANS: dict[str, str] = {
    "strategy": "unrecorded -- written before the axis columns existed",
    "resolution": "unrecorded -- written before the axis columns existed",
    "contract": "the spliced continuous series, which is not any one contract",
    "tier2": "unrecorded -- written before the axis columns existed",
    "batch_id": "a plain sweep() call rather than one point of a sweep_axes run",
}
"""What a null means per column, because it is **not** the same thing in each."""


def connect(db_path: Path = paths.SWEEPS_DB) -> duckdb.DuckDBPyConnection:
    """Open the sweep database, creating its directory and tables if they are missing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sweeps (
            sweep_id     BIGINT PRIMARY KEY,
            batch_id     BIGINT,
            created_utc  TIMESTAMP,
            root         VARCHAR,
            instrument   VARCHAR,
            strategy     VARCHAR,
            resolution   BIGINT,
            contract     VARCHAR,
            tier2        VARCHAR,
            back_adjust  BOOLEAN,
            bars         BIGINT,
            first_bar    TIMESTAMP,
            last_bar     TIMESTAMP,
            combos       BIGINT,
            elapsed_s    DOUBLE,
            axes         VARCHAR,
            notes        VARCHAR,
            host         VARCHAR
        )
        """,
    )
    _migrate_axis_columns(con)
    return con


def _migrate_axis_columns(con: duckdb.DuckDBPyConnection) -> None:
    """Add the axis columns to whichever tables already exist, leaving old rows null.

    ``combos`` is covered only once it exists, because it is created lazily from a results
    frame rather than declared. Here rather than in :func:`_append_or_create` so there is one
    migration in one place.
    """
    columns: dict[str, dict[str, str]] = {
        "sweeps": {**AXIS_COLUMNS, "batch_id": "BIGINT"},
        "combos": AXIS_COLUMNS,
    }
    for table, wanted in columns.items():
        if not _table_exists(con, table):
            continue
        for name, sql_type in wanted.items():
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {sql_type}")


def _count(con: duckdb.DuckDBPyConnection, sql: str, parameters: Sequence[object] = ()) -> int:
    """The single number an aggregate query returns."""
    row = con.execute(sql, list(parameters)).fetchone()
    if row is None:  # pragma: no cover - an aggregate always returns exactly one row
        msg: str = f"no row from {sql!r}"
        raise RuntimeError(msg)
    return int(row[0])


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(_count(con, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]))


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    return _count(con, "SELECT COALESCE(MAX(sweep_id), 0) + 1 FROM sweeps")


def next_batch_id(db_path: Path = paths.SWEEPS_DB) -> int:
    """Reserve the id tying one multi-axis run's ``sweeps`` rows together.

    Taken once by the caller and passed to every :func:`save_sweep` of the run. Nothing locks
    it -- ``docs/roadmap.md`` §M17.
    """
    con: duckdb.DuckDBPyConnection = connect(db_path)
    try:
        return _count(con, "SELECT COALESCE(MAX(batch_id), 0) + 1 FROM sweeps")
    finally:
        con.close()


def save_sweep(  # noqa: PLR0913 - each keyword is a column the stored row has to state
    results: pd.DataFrame,
    root: str,
    instrument: str,
    bars: pd.DataFrame,
    axes: Mapping[str, Sequence[object]],
    back_adjust: bool = False,
    elapsed_s: float = 0.0,
    notes: str = "",
    strategy: str | None = None,
    resolution: int | None = None,
    contract: str | None = None,
    tier2: str | None = None,
    batch_id: int | None = None,
    db_path: Path = paths.SWEEPS_DB,
) -> int:
    """Write one sweep's results and return its ``sweep_id``.

    One call is **one dataset**: one strategy, one resolution, one contract. A run varying any
    of those calls this once per axis point under a shared ``batch_id`` from
    :func:`next_batch_id`. The axis arguments default to ``None`` rather than being inferred
    from ``bars``; see :data:`NULL_MEANS` for what each null means.
    """
    con: duckdb.DuckDBPyConnection = connect(db_path)
    try:
        sweep_id: int = _next_id(con)
        # Named columns, not ``VALUES (?,?,...)``: a migrated database has the axis columns
        # at the end and a fresh one has them in the middle, so a positional insert lands
        # 'MNQ' in ``back_adjust`` rather than failing.
        row = {
            "sweep_id": sweep_id,
            "batch_id": batch_id,
            "created_utc": datetime.now(UTC).replace(tzinfo=None),
            "root": root,
            "instrument": instrument,
            "strategy": strategy,
            "resolution": resolution,
            "contract": contract,
            "tier2": tier2,
            "back_adjust": back_adjust,
            "bars": len(bars),
            "first_bar": bars.index[0].tz_localize(None) if len(bars) else None,
            "last_bar": bars.index[-1].tz_localize(None) if len(bars) else None,
            "combos": len(results),
            "elapsed_s": elapsed_s,
            "axes": json.dumps({k: list(map(_jsonable, v)) for k, v in axes.items()}),
            "notes": notes,
            "host": platform.node(),
        }
        columns: str = ", ".join(row)
        placeholders: str = ", ".join("?" * len(row))
        con.execute(
            f"INSERT INTO sweeps ({columns}) VALUES ({placeholders})",  # noqa: S608 - keys of a dict built here
            list(row.values()),
        )

        tagged: pd.DataFrame = _tag_axes(
            results,
            strategy=strategy,
            resolution=resolution,
            contract=contract,
            tier2=tier2,
        )
        tagged.insert(0, "sweep_id", sweep_id)
        _append_or_create(con, "combos", tagged)
        return sweep_id
    finally:
        con.close()


def _tag_axes(
    results: pd.DataFrame,
    strategy: str | None,
    resolution: int | None,
    contract: str | None,
    tier2: str | None,
) -> pd.DataFrame:
    """Stamp the axis columns onto every combination row, with their types pinned.

    The dtypes are load-bearing, and a frame that already carries a column keeps its own values
    -- ``docs/roadmap.md`` §M17.
    """
    tagged: pd.DataFrame = results.copy()
    supplied: dict[str, tuple[str | int | None, Literal["string", "Int64"]]] = {
        "strategy": (strategy, "string"),
        "resolution": (resolution, "Int64"),
        "contract": (contract, "string"),
        "tier2": (tier2, "string"),
    }
    for name, (value, dtype) in supplied.items():
        if name not in tagged.columns:
            tagged[name] = value
        tagged[name] = tagged[name].astype(dtype)
    return tagged


def _quoted(name: str) -> str:
    """A column name as a SQL identifier, so a statistic named like a keyword still inserts."""
    escaped: str = name.replace('"', '""')
    return f'"{escaped}"'


def _describe(con: duckdb.DuckDBPyConnection, relation: str) -> dict[str, str]:
    """Column name to DuckDB type, for a stored table or for the registered frame."""
    return {str(row[0]): str(row[1]) for row in con.execute(f"DESCRIBE {relation}").fetchall()}


def _lossy_columns(
    con: duckdb.DuckDBPyConnection,
    stored: Mapping[str, str],
    incoming: Mapping[str, str],
) -> list[str]:
    """Which shared columns hold a value the stored column's type would not give back.

    A round trip through both types, so this reports *measured* loss rather than a rule about
    which casts are safe: ``5.0`` into a BIGINT column is fine and ``2.5`` is not.
    """
    lossy: list[str] = []
    for name, incoming_type in incoming.items():
        stored_type: str | None = stored.get(name)
        if stored_type is None or stored_type == incoming_type:
            continue
        column: str = _quoted(name)
        changed: int = _count(
            con,
            f"SELECT COUNT(*) FROM incoming WHERE {column} IS NOT NULL AND "  # noqa: S608 - identifiers, quoted
            f"TRY_CAST(TRY_CAST({column} AS {stored_type}) AS {incoming_type}) IS DISTINCT FROM {column}",
        )
        if changed:
            lossy.append(f"{name} ({incoming_type} into {stored_type}, {changed} rows)")
    return lossy


def _widen(
    con: duckdb.DuckDBPyConnection,
    table: str,
    stored: Mapping[str, str],
    incoming: Mapping[str, str],
) -> None:
    """Add the columns the frame carries and the table does not, leaving stored rows null."""
    for name, sql_type in incoming.items():
        if name in stored:
            continue
        con.execute(f"ALTER TABLE {table} ADD COLUMN {_quoted(name)} {sql_type}")
        logger.info("%s: added column %s %s", table, name, sql_type)


def _append_or_create(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame) -> None:
    """Insert ``frame`` into ``table``, creating or widening it to fit the frame's columns.

    An existing table is written **by name, not by position**; a column the frame carries and
    the table does not is *added*, and a column the table carries and the frame does not is
    null on these rows -- ``docs/roadmap.md`` §M17. A shared column keeps the stored type, and
    a value that type would not give back raises :class:`ResultsError` rather than rounding in.
    """
    con.register("incoming", frame)
    if not _table_exists(con, table):
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM incoming")  # noqa: S608 - a literal at both callers
        return

    stored: dict[str, str] = _describe(con, table)
    incoming: dict[str, str] = _describe(con, "SELECT * FROM incoming")
    lossy: list[str] = _lossy_columns(con, stored, incoming)
    if lossy:
        msg: str = f"{table} cannot store these columns without losing values: {'; '.join(lossy)}"
        raise ResultsError(msg)

    _widen(con, table, stored, incoming)
    columns: str = ", ".join(_quoted(name) for name in incoming)
    con.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM incoming")  # noqa: S608 - as above


def _jsonable(value: Any) -> Any:  # type: ignore[explicit-any]  # noqa: ANN401 - see the docstring
    """Unwrap a numpy scalar so an axis value survives ``json.dumps``.

    Genuinely ``Any``: an axis holds whatever its parameter field holds.
    """
    if hasattr(value, "item"):
        return value.item()
    return value


def save_trades(
    trades: pd.DataFrame,
    sweep_id: int,
    combo_id: int,
    db_path: Path = paths.SWEEPS_DB,
    replace: bool = False,
) -> None:
    """Store one combination's trade log, for a shortlisted candidate worth inspecting.

    The frame carries its own ``source`` and ``instrument`` tags, so simulated and imported
    trades share this table. ``replace`` drops whatever is stored under the same
    ``(sweep_id, combo_id)`` first, so storing a log twice replaces it rather than doubling it.
    """
    con: duckdb.DuckDBPyConnection = connect(db_path)
    try:
        if replace and _table_exists(con, "trades"):
            con.execute(
                "DELETE FROM trades WHERE sweep_id = ? AND combo_id = ?",
                [sweep_id, combo_id],
            )
        tagged: pd.DataFrame = trades.copy()
        tagged.insert(0, "combo_id", combo_id)
        tagged.insert(0, "sweep_id", sweep_id)
        _append_or_create(con, "trades", tagged)
    finally:
        con.close()


def query(sql: str, db_path: Path = paths.SWEEPS_DB) -> pd.DataFrame:
    """Run SQL against the results database."""
    con: duckdb.DuckDBPyConnection = connect(db_path)
    try:
        return con.execute(sql).fetch_df()
    finally:
        con.close()


def list_sweeps(db_path: Path = paths.SWEEPS_DB) -> pd.DataFrame:
    """Every stored sweep, newest first, with the axis columns next to ``root``."""
    return query(
        "SELECT sweep_id, batch_id, created_utc, root, strategy, resolution, contract, "
        "tier2, combos, bars, elapsed_s, axes, notes "
        "FROM sweeps ORDER BY sweep_id DESC",
        db_path,
    )


def best(
    sweep_id: int | None = None,
    by: str = "profit_factor",
    top: int = 20,
    min_trades: int = 30,
    db_path: Path = paths.SWEEPS_DB,
) -> pd.DataFrame:
    """Top candidates, across every sweep unless one is named."""
    where: str = f"WHERE trades >= {int(min_trades)}"
    if sweep_id is not None:
        where += f" AND sweep_id = {int(sweep_id)}"
    return query(
        f"SELECT * FROM combos {where} ORDER BY {by} DESC LIMIT {int(top)}",  # noqa: S608 - the ORDER BY; #61
        db_path,
    )
