"""Re-stamp stored ``reconciled`` rows that leave their NinjaScript as ``tier-1-only``.

    uv run tools/restamp_tier2.py                    # report, write nothing
    uv run tools/restamp_tier2.py --write
    uv run tools/restamp_tier2.py results/sweeps.duckdb --write

``tools/README.md`` § "restamp_tier2.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from array import array
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, logsetup, paths
from nqbt.archetypes import Archetype, Params, Tier2Status
from tools.campaign_shortlist import rebuild
from tools.campaign_sweep import CAMPAIGN_DIR

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

logger = logging.getLogger(__name__)

CHUNK_ROWS = 50_000
"""Rows fetched at a time, so a campaign database is never read into memory whole."""

UNREADABLE = 2
"""The exit status when a stored row could not be rebuilt, so it kept a status nothing checked."""


@dataclass(slots=True)
class Restamp:
    """What one archetype's ``reconciled`` rows in one database came to."""

    strategy: str
    checked: int = 0
    sweep_ids: array[int] = field(default_factory=lambda: array("q"))
    combo_ids: array[int] = field(default_factory=lambda: array("q"))
    """The key of every row leaving its NinjaScript, one array per column."""
    reasons: Counter[tuple[str, ...]] = field(default_factory=Counter)
    """How many leaving rows name each set of fields."""
    unreadable: int = 0
    first_error: str = ""

    @property
    def keys(self) -> list[tuple[int, int]]:
        """The ``(sweep_id, combo_id)`` of every leaving row."""
        return list(zip(self.sweep_ids, self.combo_ids, strict=True))


def default_databases() -> list[Path]:
    """Return every stored database that exists: the sweep database, then each campaign's."""
    found: list[Path] = [paths.SWEEPS_DB] if paths.SWEEPS_DB.exists() else []

    return found + sorted(CAMPAIGN_DIR.glob("*.duckdb"))


def reconciled_archetypes() -> list[Archetype]:
    """Return every registered archetype whose rows can be stamped ``reconciled``."""
    return [
        archetype for archetype in archetypes.all_archetypes() if archetype.tier2 is Tier2Status.RECONCILED
    ]


def _stored_columns(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Return the ``combos`` table's columns, empty when no sweep has been stored."""
    rows: list[tuple[str]] = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'combos'",
    ).fetchall()

    return {name for (name,) in rows}


def _rows(
    con: duckdb.DuckDBPyConnection,
    strategy: str,
    stored: Sequence[str],
) -> Iterator[tuple[tuple[int, int], tuple[object, ...]]]:
    """Yield the key and the stored fields of each of one archetype's ``reconciled`` rows."""
    selected: str = ", ".join(f'"{name}"' for name in ("sweep_id", "combo_id", *stored))
    cursor: duckdb.DuckDBPyConnection = con.execute(
        f"SELECT {selected} FROM combos WHERE strategy = ? AND tier2 = ?",  # noqa: S608 - field names of a dataclass
        [strategy, str(Tier2Status.RECONCILED)],
    )
    while chunk := cursor.fetchmany(CHUNK_ROWS):
        for row in chunk:
            yield (int(row[0]), int(row[1])), tuple(tuple(v) if isinstance(v, list) else v for v in row[2:])


def departures(con: duckdb.DuckDBPyConnection, archetype: Archetype) -> Restamp:
    """Find which of one archetype's ``reconciled`` rows leave its NinjaScript, rebuilding each once."""
    found: Restamp = Restamp(archetype.name)
    columns: set[str] = _stored_columns(con)
    if not {"strategy", "tier2"} <= columns:
        return found

    stored: list[str] = [f.name for f in fields(archetype.params_cls) if f.name in columns]
    seen: dict[tuple[object, ...], tuple[str, ...] | Exception] = {}
    for key, values in _rows(con, archetype.name, stored):
        found.checked += 1
        if values not in seen:
            seen[values] = _leaving(
                archetype, pd.Series(dict(zip(stored, values, strict=True)), dtype=object)
            )

        verdict: tuple[str, ...] | Exception = seen[values]
        if isinstance(verdict, Exception):
            found.unreadable += 1
            found.first_error = found.first_error or f"{type(verdict).__name__}: {verdict}"
            continue

        if not verdict:
            continue

        found.sweep_ids.append(key[0])
        found.combo_ids.append(key[1])
        found.reasons[verdict] += 1

    return found


def _leaving(archetype: Archetype, row: pd.Series) -> tuple[str, ...] | Exception:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the fields one stored row leaves its port on, empty if it stays, or why it cannot be rebuilt."""
    try:
        params: Params = rebuild(row, archetype)
    except (TypeError, ValueError) as error:
        return error

    if archetype.tier2_for(params) is not Tier2Status.TIER1_ONLY:
        return ()

    return archetype.fields_off_port(params) or ("departs_from_port",)


def write(con: duckdb.DuckDBPyConnection, found: Restamp) -> int:
    """Stamp every leaving row ``tier-1-only`` and return how many changed."""
    if not found.sweep_ids:
        return 0

    leaving: pd.DataFrame = pd.DataFrame({"sweep_id": found.sweep_ids, "combo_id": found.combo_ids})
    con.register("leaving", leaving)
    try:
        row = con.execute(
            "UPDATE combos SET tier2 = ? FROM leaving "
            "WHERE combos.sweep_id = leaving.sweep_id AND combos.combo_id = leaving.combo_id "
            "AND combos.strategy = ? AND combos.tier2 = ?",
            [str(Tier2Status.TIER1_ONLY), found.strategy, str(Tier2Status.RECONCILED)],
        ).fetchone()
    finally:
        con.unregister("leaving")

    return 0 if row is None else int(row[0])


def restamp(db_path: Path, *, apply: bool) -> list[Restamp]:
    """Check every reconciled archetype's rows in one database, and re-stamp the leaving ones if ``apply``."""
    con: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path), read_only=not apply)
    try:
        found: list[Restamp] = [departures(con, archetype) for archetype in reconciled_archetypes()]
        if not apply:
            return found

        con.execute("BEGIN TRANSACTION")
        changed: list[int] = [write(con, one) for one in found]
        con.execute("COMMIT")
        for one, count in zip(found, changed, strict=True):
            if count != len(one.sweep_ids):
                logger.warning("%s: %d rows re-stamped of %d found", one.strategy, count, len(one.sweep_ids))

        return found
    finally:
        con.close()


def report(db_path: Path, found: list[Restamp], *, applied: bool) -> None:
    """Log what one database's rows came to: how many leave, on which fields, and what could not be read."""
    logger.info("%s", db_path)
    for one in found:
        verb: str = "re-stamped" if applied else "would be re-stamped"
        logger.info(
            "  %-18s %9s reconciled rows checked, %9s %s tier-1-only",
            one.strategy,
            f"{one.checked:,}",
            f"{len(one.sweep_ids):,}",
            verb,
        )
        for reason, count in one.reasons.most_common():
            logger.info("      %9s  %s", f"{count:,}", ", ".join(reason))
        if one.unreadable:
            logger.warning(
                "      %9s  could not be rebuilt and were left as they are -- %s",
                f"{one.unreadable:,}",
                one.first_error,
            )


def main(argv: list[str]) -> int:
    """Re-stamp the stored rows and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(
        description="Re-stamp stored reconciled rows that leave their NinjaScript."
    )
    parser.add_argument("databases", nargs="*", type=Path, help="default: every database under results/")
    parser.add_argument(
        "--write", action="store_true", help="apply the change; without it nothing is written"
    )
    args = parser.parse_args(argv[1:])

    databases: list[Path] = args.databases or default_databases()
    missing: list[Path] = [path for path in databases if not path.exists()]
    if missing:
        logger.error("no such database: %s", ", ".join(map(str, missing)))
        return UNREADABLE

    if not databases:
        logger.info("no stored databases under %s", paths.RESULTS_DIR)
        return 0

    unreadable: int = 0
    for db_path in databases:
        found: list[Restamp] = restamp(db_path, apply=args.write)
        report(db_path, found, applied=args.write)
        unreadable += sum(one.unreadable for one in found)

    if not args.write:
        logger.info("nothing written; --write applies it")

    return UNREADABLE if unreadable else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
