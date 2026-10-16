"""Compare two folders of campaign databases cell by cell, row for row.

    uv run tools/campaign_compare.py OLD NEW
    uv run tools/campaign_compare.py OLD NEW --strategies InsideBar --out cells.csv

``tools/README.md`` § "campaign_compare.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup

logger = logging.getLogger(__name__)

CELL = ["root", "resolution", "window", "variant", "stratum"]
"""One compared cell inside an archetype's database: the unit the sweep stores and skips."""

SWEEP_KEYS = frozenset({"root", "resolution"})
"""The cell keys read from a row's sweep rather than from the row itself."""

KEY_SQL = {key: f'{"s" if key in SWEEP_KEYS else "c"}."{key}"' for key in CELL}
"""Each cell key as a query reads it, from the row or from its sweep."""

CELL_SQL = ", ".join(f'{column} AS "{key}"' for key, column in KEY_SQL.items())
"""The cell's keys as every query here selects them."""

NOT_COMPARED = frozenset({"sweep_id", "combo_id", "tier2", "strategy", "resolution", "contract", *CELL})
"""Columns naming where a row was stored rather than what it measured, and the cell's own keys."""

CELL_TYPES = {"root": "str", "resolution": "int64", "window": "str", "variant": "str", "stratum": "str"}
"""One dtype per cell key on both sides, so an archetype stored on one side alone still merges."""

FILLED = "filled:"
"""Prefix of the per-cell flag saying every sweep that stored rows in the cell filled one column."""

IDENTICAL = "identical"
CHANGED = "changed"
OLD_ONLY = "old only"
NEW_ONLY = "new only"

DIFFERENT = 1
"""The exit status when a stored cell was changed or is missing from NEW."""

UNREADABLE = 2
"""The exit status when nothing could be compared, so a mistyped path or a locked file cannot pass."""


def databases(folder: Path) -> dict[str, Path]:
    """Return each archetype's campaign database in ``folder``, keyed by its name."""
    return {path.stem: path for path in sorted(folder.glob("*.duckdb"))}


def stored_columns(con: duckdb.DuckDBPyConnection, catalog: str, table: str) -> list[str]:
    """Return the columns of one table in an attached database, in stored order; none if it is absent."""
    rows: list[tuple[str]] = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_name = ? ORDER BY ordinal_position",
        [catalog, table],
    ).fetchall()

    return [name for (name,) in rows]


def rows_sql(catalog: str) -> str:
    """Return the FROM clause joining one attached database's rows to their sweeps."""
    return f"FROM {catalog}.combos c JOIN {catalog}.sweeps s USING (sweep_id)"


def holds_rows(con: duckdb.DuckDBPyConnection, catalog: str) -> bool:
    """Say whether an attached database has a ``combos`` table to compare."""
    return "combos" in {name for (name,) in con.execute(f"SHOW TABLES FROM {catalog}").fetchall()}


def profile(con: duckdb.DuckDBPyConnection, catalog: str) -> pd.DataFrame:
    """Return one row per stored cell: its size, its bars, its trades and its median profit factor."""
    if not holds_rows(con, catalog):
        return pd.DataFrame(columns=[*CELL, "rows", "bars", "trades", "median_pf"]).astype(CELL_TYPES)

    bars: str = "concat_ws('/', s.bars, s.first_bar, s.last_bar)"
    cells: pd.DataFrame = con.execute(
        f"SELECT {CELL_SQL}, count(*) AS rows, "
        f"string_agg(DISTINCT {bars}, ';' ORDER BY {bars}) AS bars, sum(c.trades) AS trades, "
        "median(c.profit_factor) FILTER (WHERE isfinite(c.profit_factor)) AS median_pf "
        f"{rows_sql(catalog)} GROUP BY ALL",
    ).df()

    return cells.astype(CELL_TYPES)


def filled(con: duckdb.DuckDBPyConnection, catalog: str, columns: list[str]) -> pd.DataFrame:
    """Return, per stored cell, whether every sweep that stored rows in it filled each of ``columns``.

    A cell extended by a later sweep holds rows from two versions of the code, and a column only the
    later one wrote is left out rather than read as changed in the earlier rows.
    """
    if not holds_rows(con, catalog):
        return pd.DataFrame(columns=CELL).astype(CELL_TYPES)

    per_sweep: str = "".join(f', count(c."{column}") > 0 AS "{column}"' for column in columns)
    every: str = "".join(f', bool_and("{column}") AS "{FILLED}{column}"' for column in columns)
    cells: pd.DataFrame = con.execute(
        f"SELECT {', '.join(f'"{key}"' for key in CELL)}{every} FROM ("  # noqa: S608 - names read from the database
        f"SELECT {CELL_SQL}, s.sweep_id{per_sweep} {rows_sql(catalog)} GROUP BY ALL"
        f") GROUP BY {', '.join(f'"{key}"' for key in CELL)}",
    ).df()

    return cells.astype(CELL_TYPES)


def unmatched(con: duckdb.DuckDBPyConnection, columns: list[str], first: str, second: str) -> pd.DataFrame:
    """Count, per cell in the registered ``cells`` view, the rows of ``first`` that ``second`` does not hold.

    A multiset difference over ``columns``, so a row stored twice and reproduced once counts once.
    """
    compared: str = "".join(f', c."{column}"' for column in columns)
    keyed: str = "JOIN cells k ON " + " AND ".join(
        f'{column} IS NOT DISTINCT FROM k."{key}"' for key, column in KEY_SQL.items()
    )

    return con.execute(
        f"SELECT {', '.join(f'"{key}"' for key in CELL)}, count(*) AS unmatched FROM ("  # noqa: S608 - names read from the database
        f"SELECT {CELL_SQL}{compared} {rows_sql(first)} {keyed} "
        f"EXCEPT ALL SELECT {CELL_SQL}{compared} {rows_sql(second)} {keyed}"
        ") GROUP BY ALL",
    ).df()


def differences(con: duckdb.DuckDBPyConnection, shared: pd.DataFrame, compared: list[str]) -> pd.DataFrame:
    """Return each shared cell's unmatched rows in both directions, over the columns its stored rows fill.

    Cells are grouped by which columns they fill, so one pair of queries serves every cell in a group.
    """
    flags = shared[[f"{FILLED}{column}" for column in compared]].to_numpy(dtype=bool)
    signature: pd.Series[str] = pd.Series(
        ["|".join(column for column, on in zip(compared, row, strict=True) if on) for row in flags],
        index=shared.index,
        dtype="str",
    )
    found: list[pd.DataFrame] = []
    for columns, group in shared.groupby(signature, sort=False):
        names: list[str] = [name for name in str(columns).split("|") if name]
        con.register("cells", group[CELL])
        try:
            old_side: pd.DataFrame = unmatched(con, names, "old", "new").rename(
                columns={"unmatched": "old_unmatched"}
            )
            new_side: pd.DataFrame = unmatched(con, names, "new", "old").rename(
                columns={"unmatched": "new_unmatched"}
            )
        finally:
            con.unregister("cells")
        found.append(
            group[CELL]
            .merge(old_side.astype(CELL_TYPES), on=CELL, how="left")
            .merge(new_side.astype(CELL_TYPES), on=CELL, how="left")
        )

    if not found:
        return pd.DataFrame(columns=[*CELL, "old_unmatched", "new_unmatched"]).astype(CELL_TYPES)

    return pd.concat(found, ignore_index=True).fillna({"old_unmatched": 0, "new_unmatched": 0})


def status(row: pd.Series) -> str:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return what one compared cell came to."""
    if pd.isna(row["new_rows"]):
        return OLD_ONLY

    if pd.isna(row["old_rows"]):
        return NEW_ONLY

    if row["old_unmatched"] == 0 and row["new_unmatched"] == 0:
        return IDENTICAL

    return CHANGED


def compare_strategy(
    name: str, old_path: Path | None, new_path: Path | None
) -> tuple[pd.DataFrame, list[str]]:
    """Compare one archetype's databases and return every cell's result, and the stored columns NEW lacks."""
    con: duckdb.DuckDBPyConnection = duckdb.connect()
    try:
        for catalog, path in (("old", old_path), ("new", new_path)):
            if path is None:
                con.execute(f"ATTACH ':memory:' AS {catalog}")
                continue

            quoted: str = path.as_posix().replace("'", "''")
            con.execute(f"ATTACH '{quoted}' AS {catalog} (READ_ONLY)")

        old_columns: list[str] = [c for c in stored_columns(con, "old", "combos") if c not in NOT_COMPARED]
        new_columns: set[str] = set(stored_columns(con, "new", "combos"))
        compared: list[str] = [column for column in old_columns if column in new_columns]
        missing: list[str] = [
            column
            for column in old_columns
            if new_columns
            and column not in new_columns
            and con.execute(f'SELECT count("{column}") FROM old.combos').fetchone() != (0,)  # noqa: S608 - a stored column's name
        ]
        old_cells: pd.DataFrame = profile(con, "old").merge(filled(con, "old", compared), on=CELL)
        new_cells: pd.DataFrame = profile(con, "new")

        merged: pd.DataFrame = old_cells.merge(new_cells, on=CELL, how="outer", suffixes=("_old", "_new"))
        shared: pd.DataFrame = merged[merged["rows_old"].notna() & merged["rows_new"].notna()]
        found: pd.DataFrame = differences(con, shared, compared)
    finally:
        con.close()

    table: pd.DataFrame = merged[CELL].merge(found, on=CELL, how="left")
    table.insert(0, "strategy", name)
    for side in ("old", "new"):
        table[f"{side}_rows"] = merged[f"rows_{side}"].to_numpy()
        table[f"{side}_trades"] = merged[f"trades_{side}"].to_numpy()
        table[f"{side}_median_pf"] = merged[f"median_pf_{side}"].to_numpy()
    on_both: pd.Series[bool] = merged["bars_old"].notna() & merged["bars_new"].notna()
    table["same_bars"] = (
        (merged["bars_old"] == merged["bars_new"]).astype("boolean").where(on_both).to_numpy()
    )
    table["status"] = table.apply(status, axis=1)
    for side in ("old", "new"):
        # Only a one-sided cell is unset here, and every row it holds is one the other side lacks.
        table[f"{side}_unmatched"] = table[f"{side}_unmatched"].fillna(table[f"{side}_rows"]).fillna(0)

    return table, missing


def report(table: pd.DataFrame, missing: dict[str, list[str]]) -> None:
    """Log one line per archetype, the columns left out, and the verdict."""
    for name, cells in table.groupby("strategy", sort=True):
        counts: pd.Series[int] = cells["status"].value_counts()
        logger.info(
            "%-18s cells %6s: identical %6s  changed %5s  old only %5s  new only %5s  "
            "rows not reproduced %s of %s",
            name,
            f"{len(cells):,}",
            f"{counts.get(IDENTICAL, 0):,}",
            f"{counts.get(CHANGED, 0):,}",
            f"{counts.get(OLD_ONLY, 0):,}",
            f"{counts.get(NEW_ONLY, 0):,}",
            f"{int(cells['old_unmatched'].sum()):,}",
            f"{int(cells['old_rows'].sum()):,}",
        )
        if missing.get(str(name)):
            logger.info("%-18s stored columns NEW lacks, not compared: %s", "", ", ".join(missing[str(name)]))

    changed: int = int(table["status"].isin([CHANGED, OLD_ONLY]).sum())
    logger.info("IDENTICAL" if not changed else f"DIFFERENT: {changed:,} cells changed or missing from NEW")


def main(argv: list[str]) -> int:
    """Compare the two folders and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Compare two folders of campaign databases row for row.")
    parser.add_argument("old", type=Path, help="the folder compared against, such as the set moved aside")
    parser.add_argument("new", type=Path, help="the folder holding the re-run")
    parser.add_argument(
        "--strategies", nargs="+", default=None, help="default: every database in either folder"
    )
    parser.add_argument("--out", type=Path, default=None, help="write every cell's comparison to this CSV")
    args = parser.parse_args(argv[1:])

    old: dict[str, Path] = databases(args.old)
    new: dict[str, Path] = databases(args.new)
    empty: list[Path] = [folder for folder, found in ((args.old, old), (args.new, new)) if not found]
    if empty:
        logger.error("no campaign databases in %s", ", ".join(map(str, empty)))
        return UNREADABLE

    names: list[str] = args.strategies or sorted(old.keys() | new.keys())
    absent: list[str] = [name for name in names if name not in old and name not in new]
    if absent:
        logger.error("no database for %s in either folder", ", ".join(absent))
        return UNREADABLE

    tables: list[pd.DataFrame] = []
    missing: dict[str, list[str]] = {}
    for name in names:
        table: pd.DataFrame
        try:
            table, missing[name] = compare_strategy(name, old.get(name), new.get(name))
        except duckdb.Error:
            logger.exception("could not compare %s", name)
            return UNREADABLE
        tables.append(table)
    combined: pd.DataFrame = pd.concat(tables, ignore_index=True)
    if combined["old_rows"].isna().all():
        logger.error("no stored rows to compare against in %s", args.old)
        return UNREADABLE

    report(combined, missing)
    if args.out is not None:
        combined.to_csv(args.out, index=False)

    return DIFFERENT if combined["status"].isin([CHANGED, OLD_ONLY]).any() else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
