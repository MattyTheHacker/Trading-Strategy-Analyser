"""Read the maximum-hold-time ladder: what each cap is worth against the uncapped arm.

    uv run tools/campaign_hold.py --strategy InsideBar --window holdout

``tools/README.md`` § "campaign_hold.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup
from tools.campaign_paired import CELL_KEYS, REPORT_KEYS, cells, paired, shared_columns, verdict
from tools.campaign_report import load
from tools.campaign_sweep import HOLD_BARS

logger = logging.getLogger(__name__)

CONTROL_BARS = 0
"""The uncapped rung, which every other one is read against."""

BASE_VARIANT = "base_variant"
"""The arm's name with its ``hold=`` token removed, so the ladder pairs within each one."""

HOLD_SUFFIX = r" hold=\d+$"
"""The rung's own token, which every ``--variants hold`` name ends with."""

BOUND = "avg_bars_held"
"""What says whether a rung actually fired: a cap that never binds leaves the hold alone."""


def held(name: str, windows: list[str], stratum: str | None = None) -> pd.DataFrame:
    """Return every viable ``--variants hold`` row for one archetype, keyed by its base variant.

    ``stratum`` keeps each pair within one stratum once the ladder has been run inside one --
    ``docs/roadmap.md`` §M31.1.
    """
    frame: pd.DataFrame = load(name, windows)
    rows: pd.DataFrame = frame[frame["variant"].str.contains("hold=", na=False)].copy()
    if stratum is not None:
        rows = rows[rows["stratum"] == stratum]

    rows[BASE_VARIANT] = rows["variant"].str.replace(HOLD_SUFFIX, "", regex=True)

    return rows


def bound_share(control: pd.DataFrame, treatment: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Measure, per cell, whether the cap moved the average hold at all."""
    joined: pd.DataFrame = cells(control, keys, BOUND).join(
        cells(treatment, keys, BOUND),
        how="inner",
        lsuffix="_control",
        rsuffix="_treatment",
    )
    joined["bound"] = joined["median_treatment"] != joined["median_control"]

    return joined.reset_index()


def bound_by_row(control: pd.DataFrame, treatment: pd.DataFrame, keys: list[str]) -> dict[object, float]:
    """Return the share of paired cells whose average hold moved, per root x resolution."""
    # The same de-duplication ``paired`` does, and for the same reason.
    cell: list[str] = list(dict.fromkeys(keys + shared_columns(control, treatment)))
    fired: pd.DataFrame = bound_share(control, treatment, cell)

    return fired.groupby(REPORT_KEYS, observed=True)["bound"].mean().to_dict()


def rung(rows: pd.DataFrame, bars: int, by: str) -> pd.DataFrame:
    """Compare one rung of the ladder against the uncapped arm, per root x resolution."""
    keys: list[str] = [*CELL_KEYS, BASE_VARIANT]
    control: pd.DataFrame = rows[rows["max_hold_bars"] == CONTROL_BARS]
    treatment: pd.DataFrame = rows[rows["max_hold_bars"] == bars]
    if control.empty or treatment.empty:
        return pd.DataFrame()

    table: pd.DataFrame = verdict(paired(control, treatment, by, cell_keys=keys))
    table["bound"] = pd.MultiIndex.from_frame(table[REPORT_KEYS]).map(bound_by_row(control, treatment, keys))
    table.insert(0, "hold_bars", bars)
    table.insert(1, "hold_minutes", bars * table["resolution"])

    return table


def ladder(name: str, windows: list[str], by: str, stratum: str | None = None) -> pd.DataFrame:
    """Stack every rung above the control."""
    rows: pd.DataFrame = held(name, windows, stratum)
    if rows.empty:
        msg: str = (
            f"{name}: no --variants hold rows in windows {windows}, stratum {stratum}; "
            "run campaign_sweep first"
        )
        raise SystemExit(msg)

    stacked: list[pd.DataFrame] = [rung(rows, bars, by) for bars in HOLD_BARS if bars != CONTROL_BARS]

    return pd.concat([t for t in stacked if not t.empty], ignore_index=True)


COLUMNS = [
    "hold_bars",
    "hold_minutes",
    "root",
    "resolution",
    "pairs",
    "bound",
    "control",
    "treatment",
    "delta",
    "improved",
    "share",
    "p",
]
"""What is printed, in reading order: the rung, what it binds on, and what it was worth."""


def main(argv: list[str]) -> int:
    """Read each hold-time cap against the uncapped arm and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Read the maximum-hold-time ladder against its control.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--window", nargs="+", default=["holdout"], help="which stored windows to read")
    parser.add_argument("--by", default="profit_factor", help="the statistic to compare on")
    parser.add_argument("--stratum", default=None, help="restrict the ladder to one stratum")
    args = parser.parse_args(argv[1:])

    table: pd.DataFrame = ladder(args.strategy, args.window, args.by, args.stratum)
    logger.info("")
    logger.info(
        "%s: each hold cap against the uncapped arm, on %s, stratum %s",
        args.strategy,
        args.by,
        args.stratum or "any",
    )
    logger.info("windows: %s;  %d tests in this family", ", ".join(args.window), len(table))
    logger.info("")
    shown: pd.DataFrame = table[COLUMNS]
    for line in shown.to_string(index=False, float_format=lambda v: f"{v:.3f}").splitlines():
        logger.info("%s", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
