"""Compare one variant against its control cell by cell, rather than distribution to distribution.

    ./.venv/Scripts/python.exe tools/campaign_paired.py --strategy EmaCrossover \
        --control "stop=atr trail=off" --treatment "stop=atr trail=on"

``tools/campaign_report.py`` compares distributions and ``tools/campaign_holdout.py`` compares
shortlists. Neither answers the question an A/B variant is built to ask -- **does switching this
one rule on help, holding everything else at the same value?** -- and the two it does answer are
both biased when the arms are different sizes: the treatment's extra axes make its shortlist a
best-of-more, which is the multiple-comparisons trap inside the design rather than in the data.

So this pairs instead. Every parameter the two arms agree about becomes part of the key, the
treatment's own axes are collapsed to their **median** within each cell, and what is reported is
the distribution of within-cell differences. The median is deliberate: taking the treatment's
best in each cell is selection, and it is reported beside the median only so the gap between
them can be seen.

**A cell needs both arms viable.** ``load`` drops rows under ``MIN_TRADES``, so a rule that
thins the sample loses cells rather than scoring badly in them -- the pair count is reported for
that reason and is part of the reading.

Reads what ``tools/campaign_sweep.py`` wrote, one database per archetype.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_report import load, parameter_columns

from nqbt import logsetup

logger = logging.getLogger(__name__)

CELL_KEYS = ["root", "resolution", "stratum"]
"""What a cell is identified by before the shared parameters are added.

``window`` is not here: a paired comparison is within one window, and the caller says which.
"""

REPORT_KEYS = ["root", "resolution"]
"""What one reported row pools over.

The stratum stays inside :data:`CELL_KEYS` rather than becoming a row of its own: a pair is
only a pair within one stratum, but a variant set run unfiltered has just the one, so splitting
the report by it would print a column with a single value in every row."""


def under_test(left: set[object], right: set[object]) -> bool:
    """Whether one column's two value sets say it is the rule being tested rather than a key.

    Two shapes mean "under test", and only these two: **one arm holds it constant while the
    other varies it** -- the trail's period against a control that never trails -- or **the two
    sets are disjoint**, which is what a toggle looks like. Anything else is a shared axis.

    Set equality is *not* the test, and that is the point: ``load`` drops a row under
    ``MIN_TRADES``, so a genuinely shared axis can lose one of its values in one arm alone.
    Read as equality that would silently stop keying on it and collapse cells that are not the
    same cell.
    """
    if not left.isdisjoint(right):
        return (len(left) == 1) != (len(right) == 1)

    return True


def shared_columns(control: pd.DataFrame, treatment: pd.DataFrame) -> list[str]:
    """The parameter columns the two arms agree about, which are what a cell is keyed on.

    Derived rather than declared, by :func:`under_test`: nothing has to name the axis the
    variant pair exists to compare.
    """
    return [
        column
        for column in parameter_columns(control)
        if column in treatment.columns
        and not under_test(set(control[column].dropna()), set(treatment[column].dropna()))
    ]


def cells(frame: pd.DataFrame, keys: list[str], by: str) -> pd.DataFrame:
    """One row per cell: the median of ``by`` over whatever the arm varies inside it, and the best.

    The median is what the comparison uses. ``best`` rides along so a reader can see how much of
    the arm's headline number is selection -- ``docs/roadmap.md`` § "The build spec's three loose
    ends, measured".
    """
    grouped = frame.groupby(keys, dropna=False, observed=True)[by]

    return pd.DataFrame({"median": grouped.median(), "best": grouped.max(), "rows": grouped.size()})


def paired(control: pd.DataFrame, treatment: pd.DataFrame, by: str) -> pd.DataFrame:
    """Every cell both arms are viable in, with the control and treatment values side by side."""
    keys: list[str] = CELL_KEYS + shared_columns(control, treatment)
    joined: pd.DataFrame = cells(control, keys, by).join(
        cells(treatment, keys, by),
        how="inner",
        lsuffix="_control",
        rsuffix="_treatment",
    )
    joined["delta"] = joined["median_treatment"] - joined["median_control"]

    return joined.reset_index()


def sign_test(improved: int, total: int) -> float:
    """Two-sided exact binomial p for ``improved`` of ``total`` cells, against a fair coin.

    Exact rather than normal-approximated, and written out rather than imported: the campaign
    runs on nine pinned dependencies and this is four lines. A cell whose difference is exactly
    zero is counted as not improved, which is the conservative direction.
    """
    if total <= 0:
        return float("nan")

    tail: float = sum(math.comb(total, k) for k in range(min(improved, total - improved) + 1))

    return min(1.0, 2.0 * tail / 2.0**total)


def verdict(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per root x resolution: how many cells the treatment improved, and by how much."""
    rows: list[dict[str, object]] = []
    for keys, group in frame.groupby(REPORT_KEYS, dropna=False, observed=True):
        improved: int = int((group["delta"] > 0.0).sum())
        total: int = len(group)
        rows.append(
            {
                **dict(zip(REPORT_KEYS, keys if isinstance(keys, tuple) else (keys,), strict=True)),
                "pairs": total,
                "control": group["median_control"].median(),
                "treatment": group["median_treatment"].median(),
                "delta": group["delta"].median(),
                "improved": improved,
                "share": improved / total if total else float("nan"),
                "p": sign_test(improved, total),
                "treatment_best": group["best_treatment"].max(),
                "control_best": group["best_control"].max(),
            },
        )

    return pd.DataFrame(rows)


def report(name: str, control: str, treatment: str, windows: list[str], by: str) -> pd.DataFrame:
    """The paired verdict for one control/treatment pair of variants."""
    stored: pd.DataFrame = load(name, windows)
    left: pd.DataFrame = stored[stored["variant"] == control]
    right: pd.DataFrame = stored[stored["variant"] == treatment]
    if left.empty or right.empty:
        msg: str = (
            f"{name}: no viable rows for control={control!r} ({len(left)}) or "
            f"treatment={treatment!r} ({len(right)}) in windows {windows}. "
            f"Stored variants: {sorted(stored['variant'].unique())}"
        )
        raise SystemExit(msg)

    return verdict(paired(left, right, by))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Pair one variant against its control, cell by cell.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--control", required=True, help="the variant the rule is switched off in")
    parser.add_argument("--treatment", required=True, help="the variant it is switched on in")
    parser.add_argument("--window", nargs="+", default=["full"], help="which stored windows to read")
    parser.add_argument("--by", default="profit_factor", help="the statistic to compare on")
    args = parser.parse_args(argv[1:])

    table: pd.DataFrame = report(args.strategy, args.control, args.treatment, args.window, args.by)
    logger.info("")
    logger.info("%s: %r against %r on %s", args.strategy, args.treatment, args.control, args.by)
    logger.info("windows: %s", ", ".join(args.window))
    logger.info("")
    for line in table.to_string(index=False, float_format=lambda v: f"{v:.3f}").splitlines():
        logger.info("%s", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
