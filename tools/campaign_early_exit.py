"""Read the conditional early exit: each arm against the control with every rule off.

    ./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBar --window holdout
    ./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBarTrailing \
        --stratum phase=MIDDAY --picks
    ./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBar --reproduce

``tools/README.md`` § "campaign_early_exit.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup, results
from tools.campaign_hold import BASE_VARIANT, bound_share
from tools.campaign_paired import CELL_KEYS, paired, shared_columns, verdict
from tools.campaign_report import STATISTICS, UNFILTERED, load, narrowing, parameter_columns
from tools.campaign_sweep import EARLY_EXIT_VARIANTS, ROOTS, db_path, early_exit_arms

logger = logging.getLogger(__name__)

ARM = "arm"
"""The early-exit arm a row belongs to, read off its variant name."""

ARM_MARKER = " exit="
"""What every ``--variants early-exit`` name carries between its base variant and its arm."""

CONTROL_ARM = "off"
"""The arm with every rule off, which every other one is read against."""

BOUND_FLOOR = 0.5
"""The bound share below which an arm is untested in a cell rather than measured there."""

SIGNIFICANCE = 0.05
"""The held-out sign test's p a selection-window pick has to reach to pay."""

PICK_KEYS = ["root", "resolution"]
"""What one pick is made within."""

REPRODUCED_KEYS = ["root", "resolution", "window", "stratum", BASE_VARIANT]
"""What joins a control row to its stored twin, beside the parameters both carry."""


def exit_variants(name: str) -> list[str]:
    """Return every variant name the early-exit set builds for one archetype, on every root."""
    return sorted({variant.name for root in ROOTS for variant in EARLY_EXIT_VARIANTS[name](root)})


def tagged(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the rows with their base variant and arm read off the variant name."""
    split = frame["variant"].str.split(ARM_MARKER, n=1, regex=False)

    return frame.assign(**{BASE_VARIANT: split.str[0], ARM: split.str[1]})


def exited(name: str, windows: list[str], stratum: str = UNFILTERED) -> pd.DataFrame:
    """Return every viable early-exit row for one archetype in one stratum, tagged by base variant and arm.

    One stratum at a time, because a pair only forms within one -- ``docs/roadmap.md`` §M31.1.
    """
    frame: pd.DataFrame = load(name, windows, variants=exit_variants(name))
    rows: pd.DataFrame = frame[frame["stratum"] == stratum]

    return tagged(rows)


def arm_table(rows: pd.DataFrame, arm: str, by: str) -> pd.DataFrame:
    """Compare one arm against the control, per root x resolution, within each base variant."""
    keys: list[str] = [*CELL_KEYS, BASE_VARIANT]
    control: pd.DataFrame = rows[rows[ARM] == CONTROL_ARM]
    treatment: pd.DataFrame = rows[rows[ARM] == arm]
    if control.empty or treatment.empty:
        return pd.DataFrame()

    table: pd.DataFrame = verdict(paired(control, treatment, by, cell_keys=keys))
    index: pd.MultiIndex = pd.MultiIndex.from_frame(table[PICK_KEYS])
    # The same de-duplication ``paired`` does, and for the same reason.
    cell: list[str] = list(dict.fromkeys(keys + shared_columns(control, treatment)))
    fired: pd.DataFrame = bound_share(control, treatment, cell)
    table["bound"] = index.map(fired.groupby(PICK_KEYS, observed=True)["bound"].mean().to_dict())
    trades: pd.DataFrame = verdict(paired(control, treatment, "trades", cell_keys=keys)).set_index(PICK_KEYS)
    table["trade_ratio"] = index.map((trades["treatment"] / trades["control"]).to_dict())
    table.insert(0, ARM, arm)

    return table


def ladder(name: str, windows: list[str], by: str, stratum: str = UNFILTERED) -> pd.DataFrame:
    """Stack every arm's table against the control."""
    rows: pd.DataFrame = exited(name, windows, stratum)
    if rows.empty:
        msg: str = (
            f"{name}: no --variants early-exit rows in windows {windows}, stratum {stratum}; "
            "run campaign_sweep first"
        )
        raise SystemExit(msg)

    stacked: list[pd.DataFrame] = [
        arm_table(rows, arm, by) for arm in early_exit_arms() if arm != CONTROL_ARM
    ]
    tables: list[pd.DataFrame] = [table for table in stacked if not table.empty]
    if not tables:
        msg = f"{name}: no arm pairs with the control in windows {windows}, stratum {stratum}"
        raise SystemExit(msg)

    return pd.concat(tables, ignore_index=True)


def picks(selection: pd.DataFrame, holdout: pd.DataFrame) -> pd.DataFrame:
    """Return the arm the selection window picks per root x resolution, read held out.

    Only an arm bound on the selection window can be picked; a pick pays where its held-out
    delta is positive and its sign test reaches :data:`SIGNIFICANCE`.
    """
    eligible: pd.DataFrame = selection[selection["bound"] >= BOUND_FLOOR]
    if eligible.empty:
        return pd.DataFrame(columns=[*PICK_KEYS, ARM, "sel_delta", "hold_delta", "hold_p", "pays"])

    chosen: pd.DataFrame = eligible.loc[
        eligible.groupby(PICK_KEYS)["delta"].idxmax(), [*PICK_KEYS, ARM, "delta"]
    ]
    held: pd.DataFrame = holdout[[*PICK_KEYS, ARM, "delta", "p", "pairs"]].rename(
        columns={"delta": "hold_delta", "p": "hold_p", "pairs": "hold_pairs"},
    )
    read: pd.DataFrame = chosen.rename(columns={"delta": "sel_delta"}).merge(
        held, on=[*PICK_KEYS, ARM], how="left"
    )
    read["pays"] = (read["hold_delta"] > 0.0) & (read["hold_p"] < SIGNIFICANCE)

    return read.reset_index(drop=True)


def clearing(read: pd.DataFrame) -> pd.DataFrame:
    """Return per resolution whether the pick pays on every root, the bar §M48 pre-registered."""
    grouped = read.groupby("resolution")["pays"]

    return pd.DataFrame(
        {"roots": grouped.size(), "paying": grouped.sum(), "clears": grouped.sum() == len(ROOTS)},
    ).reset_index()


def stored_twins(name: str, stratum: str) -> pd.DataFrame:
    """Return every control row and every stored row of its base variant in one stratum, viable or not."""
    controls: list[str] = [
        variant for variant in exit_variants(name) if variant.endswith(f"{ARM_MARKER}{CONTROL_ARM}")
    ]
    bases: list[str] = [variant.removesuffix(f"{ARM_MARKER}{CONTROL_ARM}") for variant in controls]
    if "'" in stratum:
        msg: str = f"a stratum name holding a quote cannot be read: {stratum!r}"
        raise ValueError(msg)

    return results.query(
        "SELECT c.*, s.root AS root FROM combos c JOIN sweeps s USING (sweep_id) "  # noqa: S608 - every name is the campaign's own, quotes refused
        f"WHERE c.stratum = '{stratum}'" + narrowing(["selection", "holdout"], controls + bases),
        db_path(name),
    )


def reproduction(rows: pd.DataFrame) -> dict[str, object]:
    """Join every control row to its stored twin on every parameter both carry, and count what differs.

    A parameter the stored rows hold only as null was added after they were swept, so it is
    left out of the join rather than allowed to unmatch every row.
    """
    named: pd.DataFrame = tagged(rows)
    control: pd.DataFrame = named[named[ARM] == CONTROL_ARM]
    stored: pd.DataFrame = rows[~rows["variant"].str.contains(ARM_MARKER, regex=False)].assign(
        **{BASE_VARIANT: lambda frame: frame["variant"]},
    )
    shared: list[str] = [
        column
        for column in parameter_columns(rows)
        if not column.startswith("early_exit_")
        and column not in REPRODUCED_KEYS
        and stored[column].notna().any()
    ]
    joined: pd.DataFrame = control.merge(
        stored, on=[*REPRODUCED_KEYS, *shared], how="outer", suffixes=("_control", "_stored"), indicator=True
    )
    both: pd.DataFrame = joined[joined["_merge"] == "both"]
    differing: dict[str, int] = {}
    for statistic in sorted(STATISTICS & set(rows.columns)):
        left: pd.Series[float] = both[f"{statistic}_control"]
        right: pd.Series[float] = both[f"{statistic}_stored"]
        unequal: int = int((~((left == right) | (left.isna() & right.isna()))).sum())
        if unequal:
            differing[statistic] = unequal

    return {
        "control_rows": len(control),
        "stored_rows": len(stored),
        "joined": len(both),
        "control_unmatched": int((joined["_merge"] == "left_only").sum()),
        "stored_unmatched": int((joined["_merge"] == "right_only").sum()),
        "rows_differing": max(differing.values(), default=0),
        "statistics_differing": differing,
    }


COLUMNS = [
    ARM,
    "root",
    "resolution",
    "pairs",
    "bound",
    "trade_ratio",
    "control",
    "treatment",
    "delta",
    "improved",
    "share",
    "p",
]
"""What is printed, in reading order: the arm, whether it fired, and what it was worth."""


def show(title: str, frame: pd.DataFrame) -> None:
    """Log one table under its title."""
    logger.info("")
    logger.info("%s", title)
    for line in frame.to_string(index=False, float_format=lambda v: f"{v:.4f}").splitlines():
        logger.info("%s", line)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Read the conditional early exit against its control.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--window", default="holdout", help="which stored window to read")
    parser.add_argument("--by", default="profit_factor", help="the statistic to compare on")
    parser.add_argument(
        "--stratum", default=UNFILTERED, help="the stratum to read; a pair only forms within one"
    )
    parser.add_argument("--picks", action="store_true", help="the selection window's pick, read held out")
    parser.add_argument("--reproduce", action="store_true", help="join the control to its stored twin")
    args = parser.parse_args(argv[1:])

    if args.reproduce:
        found: dict[str, object] = reproduction(stored_twins(args.strategy, args.stratum))
        show(
            f"{args.strategy}: the control against its stored twin, stratum {args.stratum}",
            pd.DataFrame([found]),
        )
        return 0

    if args.picks:
        selection: pd.DataFrame = ladder(args.strategy, ["selection"], args.by, args.stratum)
        holdout: pd.DataFrame = ladder(args.strategy, ["holdout"], args.by, args.stratum)
        read: pd.DataFrame = picks(selection, holdout)
        show(f"{args.strategy}: the selection window's pick, read held out, stratum {args.stratum}", read)
        show("per resolution: the pick pays on every root", clearing(read))
        return 0

    table: pd.DataFrame = ladder(args.strategy, [args.window], args.by, args.stratum)
    show(
        f"{args.strategy}: each arm against {CONTROL_ARM}, on {args.by}, {args.window}, "
        f"stratum {args.stratum}",
        table[COLUMNS],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
