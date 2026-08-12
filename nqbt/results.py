"""Persist sweep results to DuckDB.

One database accumulates every sweep, so shortlisting is a SQL question across all of them
rather than a directory of files to glob and concatenate. Each run gets a row in ``sweeps``
describing what was run, and its combinations land in ``combos`` tagged with that id, so a
result is never separated from the parameters and dataset that produced it.

Schemas are created from whatever columns the summary frame carries, so adding a statistic
in :mod:`nqbt.stats` does not need a migration here.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from nqbt import paths


def connect(db_path: Path = paths.SWEEPS_DB) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sweeps (
            sweep_id     BIGINT PRIMARY KEY,
            created_utc  TIMESTAMP,
            root         VARCHAR,
            instrument   VARCHAR,
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
        """
    )
    return con


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    got = con.execute("SELECT COALESCE(MAX(sweep_id), 0) + 1 FROM sweeps").fetchone()
    return int(got[0])


def save_sweep(
    results: pd.DataFrame,
    *,
    root: str,
    instrument: str,
    bars: pd.DataFrame,
    axes: dict,
    back_adjust: bool = False,
    elapsed_s: float = 0.0,
    notes: str = "",
    db_path: Path = paths.SWEEPS_DB,
) -> int:
    """Write one sweep's results and return its ``sweep_id``."""
    con = connect(db_path)
    try:
        sweep_id = _next_id(con)
        con.execute(
            "INSERT INTO sweeps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                sweep_id,
                datetime.now(timezone.utc).replace(tzinfo=None),
                root,
                instrument,
                back_adjust,
                len(bars),
                bars.index[0].tz_localize(None) if len(bars) else None,
                bars.index[-1].tz_localize(None) if len(bars) else None,
                len(results),
                elapsed_s,
                json.dumps({k: list(map(_jsonable, v)) for k, v in axes.items()}),
                notes,
                platform.node(),
            ],
        )

        tagged = results.copy()
        tagged.insert(0, "sweep_id", sweep_id)
        _append_or_create(con, "combos", tagged)
        return sweep_id
    finally:
        con.close()


def _append_or_create(
    con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame
) -> None:
    """Insert ``frame`` into ``table``, creating it from the frame's own columns if new.

    An existing table is written **by name, not by position**. Without this, adding a
    statistic to :mod:`nqbt.stats` or a field to :mod:`nqbt.trades` would make
    ``INSERT ... SELECT *`` shift every column one place to the right and store a row of
    numbers under the wrong headings -- which reads as a result rather than as an error.

    A column the frame carries but the table does not is dropped. That is the accepted
    cost of not migrating on every schema change; the alternative is a failed insert on a
    database that has years of results in it. It is also why the stale-database re-run is
    scheduled after the axis columns land rather than before -- see ``docs/roadmap.md``.
    """
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()[0]
    if not exists:
        con.register("incoming", frame)
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM incoming")
        return

    stored = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    aligned = frame.copy()
    for name in stored:
        if name not in aligned.columns:
            aligned[name] = None
    con.register("incoming", aligned[stored])
    con.execute(f"INSERT INTO {table} SELECT * FROM incoming")


def _jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def save_trades(
    trades: pd.DataFrame, sweep_id: int, combo_id: int,
    db_path: Path = paths.SWEEPS_DB,
) -> None:
    """Store one combination's trade log, for a shortlisted candidate worth inspecting.

    The frame carries its own ``source`` and ``instrument`` tags from
    :func:`nqbt.trades.trades_to_frame`, so simulated and imported trades can share this
    table without a query having to know which it is reading.
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
    return query(
        "SELECT sweep_id, created_utc, root, combos, bars, elapsed_s, axes, notes "
        "FROM sweeps ORDER BY sweep_id DESC",
        db_path,
    )


def best(
    sweep_id: int | None = None, by: str = "profit_factor", top: int = 20,
    min_trades: int = 30, db_path: Path = paths.SWEEPS_DB,
) -> pd.DataFrame:
    """Top candidates, across every sweep unless one is named."""
    where = f"WHERE trades >= {int(min_trades)}"
    if sweep_id is not None:
        where += f" AND sweep_id = {int(sweep_id)}"
    return query(
        f"SELECT * FROM combos {where} ORDER BY {by} DESC LIMIT {int(top)}", db_path
    )
