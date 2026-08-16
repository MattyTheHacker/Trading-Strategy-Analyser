"""Persist sweep results to DuckDB.

One database accumulates every sweep, so shortlisting is a SQL question across all of them
rather than a directory of files to glob and concatenate. Each run gets a row in ``sweeps``
describing what was run, and its combinations land in ``combos`` tagged with that id, so a
result is never separated from the parameters and dataset that produced it.

Schemas are created from whatever columns the summary frame carries, so adding a statistic
in :mod:`nqbt.stats` does not need a migration here. The **axis** columns are the exception
and are migrated explicitly -- see :data:`AXIS_COLUMNS` for why identity is not a statistic.

## What a row is, once there are axes above the Dataset

Strategy, bar resolution and contract each select *which* :class:`~nqbt.context.Dataset`
gets built rather than varying a value inside one, so a run spanning several of them is
several datasets. Each gets its **own ``sweeps`` row**, because ``bars``, ``first_bar`` and
``last_bar`` are properties of a dataset: one row covering nineteen contracts could not
honestly fill them. :data:`batch_id` is what then says those rows were one experiment.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from nqbt import paths

AXIS_COLUMNS: dict[str, str] = {
    "strategy": "VARCHAR",
    "resolution": "BIGINT",
    "contract": "VARCHAR",
    "tier2": "VARCHAR",
}
"""The axes that sit *above* a :class:`~nqbt.context.Dataset`, and their storage types.

On **both** tables: on ``sweeps`` to describe the run, on ``combos`` so a query can filter
or group without a join -- which is the whole point once a comparison spans them.

**Migrated explicitly, unlike a new statistic.** :func:`_append_or_create` drops a column
the table does not have, and for a statistic that is the right trade: a gap in one column,
obvious on inspection. These four are *identity*, not measurement, so dropping one does not
leave a gap -- it silently relabels the row as some other run, and a 15-minute result then
sits in the same column as a 1-minute one with nothing to say so.

``tier2`` rides along because "validated against NT8" stops being a project-wide fact once
originals exist (see :class:`nqbt.archetypes.Tier2Status`); carrying it here is what stops
a ranking comparing a measurement against an assumption.
"""

NULL_MEANS: dict[str, str] = {
    "strategy": "unrecorded -- written before the axis columns existed",
    "resolution": "unrecorded -- written before the axis columns existed",
    "contract": "the spliced continuous series, which is not any one contract",
    "tier2": "unrecorded -- written before the axis columns existed",
    "batch_id": "a plain sweep() call rather than one point of a sweep_axes run",
}
"""What a null means per column, because it is **not** the same thing in each.

``contract`` is the odd one out and deliberately so: null is a real, expected value there,
naming the spliced series. Everywhere else null means the row predates the column. Stated
here rather than left to be inferred from a query returning empty.
"""


def connect(db_path: Path = paths.SWEEPS_DB) -> duckdb.DuckDBPyConnection:
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
        """
    )
    _migrate_axis_columns(con)
    return con


def _migrate_axis_columns(con: duckdb.DuckDBPyConnection) -> None:
    """Add the axis columns to whichever tables already exist, leaving old rows null.

    ``CREATE TABLE IF NOT EXISTS`` does nothing to a table that is already there, and
    ``results/sweeps.duckdb`` has years of rows in it, so the DDL above only covers a fresh
    database. ``ADD COLUMN IF NOT EXISTS`` is idempotent and backfills null, which is
    exactly the "existing rows keep working" requirement.

    ``combos`` gets the same treatment but only once it exists, because it is created
    lazily from a results frame rather than declared. Doing it here rather than inside
    :func:`_append_or_create` keeps one migration in one place.
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
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()[0]
    )


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    got = con.execute("SELECT COALESCE(MAX(sweep_id), 0) + 1 FROM sweeps").fetchone()
    return int(got[0])


def next_batch_id(db_path: Path = paths.SWEEPS_DB) -> int:
    """Reserve the id tying one multi-axis run's ``sweeps`` rows together.

    Taken once by the caller and passed to every :func:`save_sweep` of the run, because the
    rows are written one dataset at a time and only the caller knows where the run ends.

    Nothing locks it. That is fine for a single-user research tool and would not be for a
    shared one: two runs started in the same second would share a batch. Recorded rather
    than defended.
    """
    con = connect(db_path)
    try:
        got = con.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM sweeps").fetchone()
        return int(got[0])
    finally:
        con.close()


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
    strategy: str | None = None,
    resolution: int | None = None,
    contract: str | None = None,
    tier2: str | None = None,
    batch_id: int | None = None,
    db_path: Path = paths.SWEEPS_DB,
) -> int:
    """Write one sweep's results and return its ``sweep_id``.

    One call is **one dataset**: one strategy, one resolution, one contract. A run varying
    any of those calls this once per axis point under a shared ``batch_id`` from
    :func:`next_batch_id`, which is what keeps ``bars``/``first_bar``/``last_bar`` true of
    the rows they sit beside.

    The axis arguments default to ``None`` rather than being inferred from ``bars``.
    Resolution in particular is guessable from the index spacing and that guess would be
    right nearly always -- which is the problem: a tag that is usually right is worse than
    one that is absent, because nothing downstream can tell the two apart. See
    :data:`NULL_MEANS` for what a null means in each column.
    """
    con = connect(db_path)
    try:
        sweep_id = _next_id(con)
        # Named columns, not ``VALUES (?,?,...)``. A migrated database has the axis columns
        # appended at the end while a fresh one has them declared in the middle, so a
        # positional insert writes a different row into each -- and it does not fail
        # cleanly, it lands 'MNQ' in ``back_adjust``. This is the same by-name rule M9
        # applied to ``combos``, and the migration is what made ``sweeps`` need it too.
        row = {
            "sweep_id": sweep_id,
            "batch_id": batch_id,
            "created_utc": datetime.now(timezone.utc).replace(tzinfo=None),
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
            f"INSERT INTO sweeps ({columns}) VALUES ({placeholders})", list(row.values())
        )

        tagged = _tag_axes(
            results, strategy=strategy, resolution=resolution, contract=contract,
            tier2=tier2,
        )
        tagged.insert(0, "sweep_id", sweep_id)
        _append_or_create(con, "combos", tagged)
        return sweep_id
    finally:
        con.close()


def _tag_axes(
    results: pd.DataFrame, *, strategy: str | None, resolution: int | None,
    contract: str | None, tier2: str | None,
) -> pd.DataFrame:
    """Stamp the axis columns onto every combination row, with their types pinned.

    **The dtypes are the point, not decoration.** DuckDB infers a new table's column types
    from the frame it is created from, and an all-null ``object`` column infers as
    ``INTEGER`` -- so a first sweep over the spliced series, where ``contract`` is null by
    definition, would create ``combos.contract`` as an integer column that no contract name
    can ever afterwards be inserted into. Pinning ``string`` and ``Int64`` makes the null
    case declare the same type the populated case does.

    A caller may also supply these per row -- :func:`nqbt.sweep.sweep_axes` does, since its
    frame already spans axis points -- and then the frame's own values win. Overwriting them
    with a scalar ``None`` is how a multi-axis run would lose exactly the tags it exists to
    produce.
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

    :data:`AXIS_COLUMNS` are exempt from that trade and migrated up front by
    :func:`_migrate_axis_columns`, because dropping one does not leave a visible gap -- it
    relabels the row as a different run.
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


def _jsonable(value: Any) -> Any:  # type: ignore[explicit-any]
    """Unwrap a numpy scalar so an axis value survives ``json.dumps``.

    Genuinely ``Any``: an axis holds whatever its parameter field holds. The config sets
    ``disallow_any_explicit``, so this is waived here rather than widened silently.
    """
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
    """Every stored sweep, newest first.

    The axis columns sit next to ``root`` rather than at the end: a listing that shows two
    runs of the same grid without saying one was 15-minute bars on a single contract
    invites exactly the comparison that is meaningless.
    """
    return query(
        "SELECT sweep_id, batch_id, created_utc, root, strategy, resolution, contract, "
        "tier2, combos, bars, elapsed_s, axes, notes "
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
