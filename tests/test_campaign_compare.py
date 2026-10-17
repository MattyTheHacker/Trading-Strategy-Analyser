"""Comparing two folders of campaign databases: what counts as reproduced, and what does not.

Every database here is built by :func:`nqbt.results.save_sweep`, so a row round-trips through
DuckDB as a campaign's does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from nqbt import results
from tools.campaign_compare import CHANGED, DIFFERENT, IDENTICAL, NEW_ONLY, OLD_ONLY, UNREADABLE, main
from tools.campaign_compare import compare_strategy as compare

if TYPE_CHECKING:
    from pathlib import Path

BARS = pd.DataFrame(
    {"close": [1.0, 2.0]},
    index=pd.date_range("2024-01-02 15:00", periods=2, freq="min", tz="UTC"),
)


def row(combo_id: int = 0, *, variant: str = "base", **fields: object) -> dict[str, object]:
    """Return one stored row as a campaign writes it, with ``fields`` overriding the defaults."""
    return {
        "variant": variant,
        "stratum": "unfiltered",
        "window": "selection",
        "combo_id": combo_id,
        "ema_period": 20 + combo_id,
        "trades": 40,
        "profit_factor": 1.2,
        "net_pnl": 500.0,
    } | fields


def store(
    folder: Path, rows: list[dict[str, object]], *, bars: pd.DataFrame = BARS, tier2: str = "tier-1-only"
) -> Path:
    """Store ``rows`` as one InsideBar sweep in ``folder`` and return the database."""
    folder.mkdir(exist_ok=True)
    db: Path = folder / "InsideBar.duckdb"
    results.save_sweep(
        pd.DataFrame(rows),
        root="MNQ",
        instrument="MNQ",
        bars=bars,
        axes={},
        strategy="InsideBar",
        resolution=5,
        tier2=tier2,
        db_path=db,
    )

    return db


def statuses(old: Path, new: Path) -> dict[str, str]:
    """Return each compared cell's status, keyed by its variant."""
    table: pd.DataFrame = compare("InsideBar", old / "InsideBar.duckdb", new / "InsideBar.duckdb")[0]

    return dict(zip(table["variant"], table["status"], strict=True))


def test_identical_folders_report_every_cell_identical(tmp_path: Path) -> None:
    """The same rows stored twice compare identical, and the tool exits 0."""
    rows = [row(0), row(1), row(0, variant="arm")]
    store(tmp_path / "old", rows)
    store(tmp_path / "new", rows)

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL, "arm": IDENTICAL}
    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == 0


def test_one_changed_statistic_marks_only_its_cell_and_counts_the_row_both_ways(tmp_path: Path) -> None:
    """A moved number is a changed cell, one unmatched row on each side, and a non-zero exit."""
    store(tmp_path / "old", [row(0), row(1), row(0, variant="arm")])
    store(tmp_path / "new", [row(0), row(1, net_pnl=499.0), row(0, variant="arm")])

    table: pd.DataFrame = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "new" / "InsideBar.duckdb"
    )[0]
    base = table.set_index("variant").loc["base"]

    assert dict(zip(table["variant"], table["status"], strict=True)) == {"base": CHANGED, "arm": IDENTICAL}
    assert (base["old_unmatched"], base["new_unmatched"]) == (1, 1)
    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == DIFFERENT


def test_row_order_combo_id_and_the_tier2_stamp_are_not_compared(tmp_path: Path) -> None:
    """The same measurements stored in another order, under other ids and another stamp, still match."""
    store(tmp_path / "old", [row(0), row(1)], tier2="reconciled")
    reordered = [row(1) | {"combo_id": 0}, row(0) | {"combo_id": 1}]
    store(tmp_path / "new", reordered, tier2="tier-1-only")

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL}


def test_a_column_only_the_new_rows_fill_is_not_a_change(tmp_path: Path) -> None:
    """A column a later campaign added reads null in the stored rows, so its new values are not compared."""
    store(tmp_path / "old", [row(0)])
    store(tmp_path / "old", [row(0, variant="arm", late_stop_minutes=5.0)])
    store(tmp_path / "new", [row(0, late_stop_minutes=0.0), row(0, variant="arm", late_stop_minutes=5.0)])

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL, "arm": IDENTICAL}


def test_a_column_the_stored_rows_fill_is_compared_where_they_fill_it(tmp_path: Path) -> None:
    """The same column is compared in the cell that filled it, so a change there is caught."""
    store(tmp_path / "old", [row(0), row(0, variant="arm", late_stop_minutes=5.0)])
    store(tmp_path / "new", [row(0, late_stop_minutes=0.0), row(0, variant="arm", late_stop_minutes=6.0)])

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL, "arm": CHANGED}


def test_a_column_only_a_later_sweep_into_the_cell_wrote_is_left_out(tmp_path: Path) -> None:
    """A cell a later sweep extended holds rows from two code versions; the older rows stay matched."""
    store(tmp_path / "old", [row(0)])
    store(tmp_path / "old", [row(1, late_stop_minutes=5.0)])
    store(tmp_path / "new", [row(0, late_stop_minutes=0.0), row(1, late_stop_minutes=5.0)])

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL}


def test_a_stored_column_the_new_database_lacks_is_named_and_left_out(tmp_path: Path) -> None:
    """A filled column NEW never wrote cannot be reproduced, so it is named rather than failing every row."""
    store(tmp_path / "old", [row(0, retired_axis=3)])
    store(tmp_path / "new", [row(0)])

    table, missing = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "new" / "InsideBar.duckdb"
    )

    assert table["status"].tolist() == [IDENTICAL]
    assert missing == ["retired_axis"]


def test_a_row_stored_twice_and_reproduced_once_counts_once(tmp_path: Path) -> None:
    """The comparison is over multisets, so a duplicate is a difference and not a match."""
    store(tmp_path / "old", [row(0), row(0)])
    store(tmp_path / "new", [row(0)])

    table: pd.DataFrame = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "new" / "InsideBar.duckdb"
    )[0]

    assert table["status"].tolist() == [CHANGED]
    assert (table["old_unmatched"].iloc[0], table["new_unmatched"].iloc[0]) == (1, 0)


def test_non_finite_and_signed_zero_statistics_match_themselves(tmp_path: Path) -> None:
    """NaN, infinity and nulls match their twins, and -0.0 matches 0.0, so only real differences count."""
    store(
        tmp_path / "old",
        [row(0, profit_factor=float("nan"), net_pnl=0.0), row(1, profit_factor=float("inf"), sharpe=None)],
    )
    store(
        tmp_path / "new",
        [row(0, profit_factor=float("nan"), net_pnl=-0.0), row(1, profit_factor=float("inf"), sharpe=None)],
    )

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": IDENTICAL}


def test_cells_on_one_side_only_are_named_and_only_a_missing_one_fails(tmp_path: Path) -> None:
    """A cell NEW lacks fails the comparison; one only NEW holds is listed and does not."""
    store(tmp_path / "old", [row(0), row(0, variant="dropped")])
    store(tmp_path / "new", [row(0), row(0, variant="added")])
    store(tmp_path / "new_superset", [row(0), row(0, variant="dropped"), row(0, variant="added")])

    assert statuses(tmp_path / "old", tmp_path / "new") == {
        "base": IDENTICAL,
        "dropped": OLD_ONLY,
        "added": NEW_ONLY,
    }
    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == DIFFERENT
    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new_superset")]) == 0


def test_an_archetype_stored_on_one_side_alone_lists_every_cell_on_that_side(tmp_path: Path) -> None:
    """A database missing from either folder makes each of its cells one-sided rather than raising."""
    store(tmp_path / "old", [row(0), row(0, variant="arm")])

    only_old, lacking = compare("InsideBar", tmp_path / "old" / "InsideBar.duckdb", None)
    only_new: pd.DataFrame = compare("InsideBar", None, tmp_path / "old" / "InsideBar.duckdb")[0]

    assert lacking == []
    assert set(only_old["status"]) == {OLD_ONLY}
    assert set(only_new["status"]) == {NEW_ONLY}
    assert len(only_old) == len(only_new) == 2
    assert only_old["same_bars"].isna().all()


def test_every_row_of_a_one_sided_cell_counts_as_unmatched(tmp_path: Path) -> None:
    """A cell missing from one side leaves all its rows unreproduced, not none of them."""
    store(tmp_path / "old", [row(0), row(1), row(0, variant="dropped"), row(1, variant="dropped")])
    store(tmp_path / "new", [row(0), row(1), row(0, variant="added")])

    table = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "new" / "InsideBar.duckdb"
    )[0]
    unmatched = {
        variant: (old, new)
        for variant, old, new in zip(
            table["variant"], table["old_unmatched"], table["new_unmatched"], strict=True
        )
    }

    assert unmatched == {"dropped": (2, 0), "added": (0, 1), "base": (0, 0)}


def test_rows_swept_on_other_bars_are_flagged(tmp_path: Path) -> None:
    """Each cell says whether both sides ran on the same bars, apart from whether the rows match."""
    store(tmp_path / "old", [row(0)])
    store(tmp_path / "new", [row(0)], bars=BARS.iloc[:1])
    store(tmp_path / "same", [row(0)])

    moved: pd.DataFrame = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "new" / "InsideBar.duckdb"
    )[0]
    held: pd.DataFrame = compare(
        "InsideBar", tmp_path / "old" / "InsideBar.duckdb", tmp_path / "same" / "InsideBar.duckdb"
    )[0]

    assert moved["same_bars"].tolist() == [False]
    assert held["same_bars"].tolist() == [True]


def test_out_writes_one_row_per_cell(tmp_path: Path) -> None:
    """``--out`` writes every cell, both sides' sizes and its status."""
    store(tmp_path / "old", [row(0), row(0, variant="arm")])
    store(tmp_path / "new", [row(0), row(0, variant="arm", trades=41)])
    out: Path = tmp_path / "cells.csv"

    main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new"), "--out", str(out)])
    written: pd.DataFrame = pd.read_csv(out)

    assert sorted(zip(written["variant"], written["status"], strict=True)) == [
        ("arm", CHANGED),
        ("base", IDENTICAL),
    ]
    assert {"strategy", "old_rows", "new_rows", "old_unmatched", "new_unmatched", "same_bars"} <= set(
        written.columns
    )


def test_strategies_narrows_the_comparison_and_an_unknown_one_is_refused(tmp_path: Path) -> None:
    """Only the named archetypes are compared, and one in neither folder is an error, not a clean pass."""
    store(tmp_path / "old", [row(0)])
    store(tmp_path / "new", [row(0, trades=41)])

    assert (
        main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new"), "--strategies", "InsideBar"])
        == DIFFERENT
    )
    assert (
        main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new"), "--strategies", "Nope"])
        == UNREADABLE
    )


def test_a_cell_with_a_null_key_is_still_compared(tmp_path: Path) -> None:
    """A cell whose stratum is null joins to its rows, so a change inside it is not read as identical."""
    store(tmp_path / "old", [row(0, stratum=None), row(0, variant="arm")])
    store(tmp_path / "new", [row(0, stratum=None, trades=41), row(0, variant="arm")])

    assert statuses(tmp_path / "old", tmp_path / "new") == {"base": CHANGED, "arm": IDENTICAL}


def test_a_folder_named_with_a_quote_opens(tmp_path: Path) -> None:
    """A path is quoted into the attach, so an apostrophe in it does not break the read."""
    store(tmp_path / "o'neil old", [row(0)])
    store(tmp_path / "o'neil new", [row(0)])

    assert main(["campaign_compare", str(tmp_path / "o'neil old"), str(tmp_path / "o'neil new")]) == 0


@pytest.mark.parametrize("contents", ["empty", "missing"])
@pytest.mark.parametrize("side", ["old", "new"])
def test_a_folder_with_no_databases_is_unreadable(tmp_path: Path, contents: str, side: str) -> None:
    """Either folder holding nothing is exit 2, so a mistyped path cannot pass or fail as a result."""
    store(tmp_path / ("new" if side == "old" else "old"), [row(0)])
    if contents == "empty":
        (tmp_path / side).mkdir()

    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == UNREADABLE


def test_an_old_folder_holding_no_rows_is_unreadable(tmp_path: Path) -> None:
    """A database with no stored rows leaves nothing to compare, which is not a clean pass."""
    (tmp_path / "old").mkdir()
    results.connect(tmp_path / "old" / "InsideBar.duckdb").close()
    store(tmp_path / "new", [row(0)])

    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == UNREADABLE


def test_a_database_duckdb_cannot_open_is_unreadable_not_different(tmp_path: Path) -> None:
    """A read error exits 2 rather than escaping as a traceback, whose exit 1 would read as changed rows."""
    store(tmp_path / "new", [row(0)])
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "InsideBar.duckdb").write_bytes(b"not a database")

    assert main(["campaign_compare", str(tmp_path / "old"), str(tmp_path / "new")]) == UNREADABLE
