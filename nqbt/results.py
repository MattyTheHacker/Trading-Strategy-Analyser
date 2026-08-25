"""Persist sweep results to DuckDB.

One database accumulates every sweep, so shortlisting is a SQL question rather than a directory
of files to glob. Each run gets a row in ``sweeps`` and its combinations land in ``combos``
tagged with that id.

**One ``sweeps`` row is one dataset** -- one strategy, one resolution, one contract -- because
``bars``/``first_bar``/``last_bar`` are properties of a dataset; ``batch_id`` says which rows
were one experiment. Schemas are created from whatever columns the summary frame carries, so a
new statistic needs no migration; the axis columns are the exception. Reasoning:
``docs/roadmap.md`` §M17.
"""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import duckdb

from nqbt import paths

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

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
    con = duckdb.connect(str(db_path))
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
    columns = {"sweeps": {**AXIS_COLUMNS, "batch_id": "BIGINT"}, "combos": AXIS_COLUMNS}
    for table, wanted in columns.items():
        if not _table_exists(con, table):
            continue
        for name, sql_type in wanted.items():
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {sql_type}")


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(
        con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table],
        ).fetchone()[0],
    )


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    got = con.execute("SELECT COALESCE(MAX(sweep_id), 0) + 1 FROM sweeps").fetchone()
    return int(got[0])


def next_batch_id(db_path: Path = paths.SWEEPS_DB) -> int:
    """Reserve the id tying one multi-axis run's ``sweeps`` rows together.

    Taken once by the caller and passed to every :func:`save_sweep` of the run. Nothing locks
    it -- ``docs/roadmap.md`` §M17.
    """
    con = connect(db_path)
    try:
        got = con.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM sweeps").fetchone()
        return int(got[0])
    finally:
        con.close()


def save_sweep(  # noqa: PLR0913 - each keyword is a column the stored row has to state
    results: pd.DataFrame,
    *,
    root: str,
    instrument: str,
    bars: pd.DataFrame,
    axes: dict,
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
    con = connect(db_path)
    try:
        sweep_id = _next_id(con)
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
        columns = ", ".join(row)
        placeholders = ", ".join("?" * len(row))
        con.execute(
            f"INSERT INTO sweeps ({columns}) VALUES ({placeholders})",  # noqa: S608 - keys of a dict built here
            list(row.values()),
        )

        tagged = _tag_axes(
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
    *,
    strategy: str | None,
    resolution: int | None,
    contract: str | None,
    tier2: str | None,
) -> pd.DataFrame:
    """Stamp the axis columns onto every combination row, with their types pinned.

    The dtypes are load-bearing, and a frame that already carries a column keeps its own values
    -- ``docs/roadmap.md`` §M17.
    """
    tagged = results.copy()
    supplied = {
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


def _append_or_create(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame) -> None:
    """Insert ``frame`` into ``table``, creating it from the frame's own columns if new.

    An existing table is written **by name, not by position**, and a column the frame carries
    but the table does not is dropped -- ``docs/roadmap.md`` §M17. :data:`AXIS_COLUMNS` are
    exempt from that and migrated up front by :func:`_migrate_axis_columns`.
    """
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchone()[0]
    if not exists:
        con.register("incoming", frame)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM incoming")  # noqa: S608 - a literal at both callers
        return

    stored = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    aligned = frame.copy()
    for name in stored:
        if name not in aligned.columns:
            aligned[name] = None
    con.register("incoming", aligned[stored])
    con.execute(f"INSERT INTO {table} SELECT * FROM incoming")  # noqa: S608 - a literal at both callers


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
) -> None:
    """Store one combination's trade log, for a shortlisted candidate worth inspecting.

    The frame carries its own ``source`` and ``instrument`` tags, so simulated and imported
    trades share this table.
    """
    con = connect(db_path)
    try:
        tagged = trades.copy()
        tagged.insert(0, "combo_id", combo_id)
        tagged.insert(0, "sweep_id", sweep_id)
        _append_or_create(con, "trades", tagged)
    finally:
        con.close()


def query(sql: str, db_path: Path = paths.SWEEPS_DB) -> pd.DataFrame:
    """Run SQL against the results database."""
    con = connect(db_path)
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
    where = f"WHERE trades >= {int(min_trades)}"
    if sweep_id is not None:
        where += f" AND sweep_id = {int(sweep_id)}"
    return query(
        f"SELECT * FROM combos {where} ORDER BY {by} DESC LIMIT {int(top)}",  # noqa: S608 - the ORDER BY; #61
        db_path,
    )
