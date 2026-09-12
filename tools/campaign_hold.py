"""Read the maximum-hold-time ladder: what each cap is worth against the uncapped arm.

    ./.venv/Scripts/python.exe tools/campaign_hold.py --strategy InsideBar --window holdout

``tools/campaign_sweep.py --variants hold`` runs every archetype's stored campaign grid once
per rung of :data:`~tools.campaign_sweep.HOLD_BARS`, the uncapped ``hold=0`` arm included, so
two rows differ by the cap and nothing else. This pairs each capped arm against that control
cell by cell, which is the instrument an A/B rule needs -- ``tools/campaign_paired.py`` has why
a shortlist is not.

**Never pooled across resolutions.** The cap is a bar count, so twenty bars is twenty minutes
at one resolution and five hours at another; every reported row is one root x resolution, and
the minutes each rung means are printed beside it.

**A rung that cannot bind must read as its control**, which is what ``bound`` measures: the
share of paired cells whose average hold actually moved. A rung with a low ``bound`` share and
a p-value near 1 is an arm that never fired, not a cap that did nothing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_paired import CELL_KEYS, cells, paired, shared_columns, verdict
from tools.campaign_report import load
from tools.campaign_sweep import HOLD_BARS

from nqbt import logsetup

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
    """Every viable ``--variants hold`` row for one archetype, keyed by its base variant.

    ``stratum`` is what keeps :data:`~tools.campaign_paired.REPORT_KEYS` honest once the ladder
    has been run inside one: a pair only ever forms within a stratum, but the report pools over
    it -- ``docs/roadmap.md`` §M31.1.
    """
    frame: pd.DataFrame = load(name, windows)
    rows: pd.DataFrame = frame[frame["variant"].str.contains("hold=", na=False)].copy()
    if stratum is not None:
        rows = rows[rows["stratum"] == stratum]

    rows[BASE_VARIANT] = rows["variant"].str.replace(HOLD_SUFFIX, "", regex=True)

    return rows


def bound_share(control: pd.DataFrame, treatment: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per cell, whether the cap moved the average hold at all."""
    joined: pd.DataFrame = cells(control, keys, BOUND).join(
        cells(treatment, keys, BOUND),
        how="inner",
        lsuffix="_control",
        rsuffix="_treatment",
    )
    joined["bound"] = joined["median_treatment"] != joined["median_control"]

    return joined.reset_index()


def rung(rows: pd.DataFrame, bars: int, by: str) -> pd.DataFrame:
    """One rung of the ladder against the uncapped arm, per root x resolution."""
    keys: list[str] = [*CELL_KEYS, BASE_VARIANT]
    control: pd.DataFrame = rows[rows["max_hold_bars"] == CONTROL_BARS]
    treatment: pd.DataFrame = rows[rows["max_hold_bars"] == bars]
    if control.empty or treatment.empty:
        return pd.DataFrame()

    table: pd.DataFrame = verdict(paired(control, treatment, by, cell_keys=keys))
    # The same de-duplication ``paired`` does, and for the same reason.
    cell: list[str] = list(dict.fromkeys(keys + shared_columns(control, treatment)))
    fired: pd.DataFrame = bound_share(control, treatment, cell)
    share: pd.Series[float] = fired.groupby(["root", "resolution"], observed=True)["bound"].mean()
    table["bound"] = table.set_index(["root", "resolution"]).index.map(share)
    table.insert(0, "hold_bars", bars)
    table.insert(1, "hold_minutes", bars * table["resolution"])

    return table


def ladder(name: str, windows: list[str], by: str, stratum: str | None = None) -> pd.DataFrame:
    """Every rung above the control, stacked."""
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
