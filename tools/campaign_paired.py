"""Compare one variant against its control cell by cell, rather than distribution to distribution.

    uv run tools/campaign_paired.py --strategy EmaCrossover \
        --control "stop=atr trail=off" --treatment "stop=atr trail=on"

``tools/README.md`` § "campaign_paired.py".
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup
from tools.campaign_report import load, parameter_columns

logger = logging.getLogger(__name__)

CELL_KEYS = ["root", "resolution", "stratum"]
"""What a cell is identified by before the shared parameters are added; the window is the caller's."""

REPORT_KEYS = ["root", "resolution"]
"""What one reported row pools over."""


def under_test(left: set[object], right: set[object]) -> bool:
    """Return whether one column's two value sets say it is the rule being tested rather than a key.

    Under test means one arm holds it constant while the other varies it, or the two sets are
    disjoint. Set equality is not the test -- ``tools/README.md`` § "campaign_paired.py".
    """
    if not left.isdisjoint(right):
        return (len(left) == 1) != (len(right) == 1)

    return True


def shared_columns(control: pd.DataFrame, treatment: pd.DataFrame) -> list[str]:
    """Return the parameter columns the two arms agree about, which are what a cell is keyed on.

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
    """Return one row per cell: the median of ``by`` over whatever the arm varies inside it, and the best.

    The comparison uses the median; ``best`` shows how much of the arm's headline number is
    selection.
    """
    grouped = frame.groupby(keys, dropna=False, observed=True)[by]

    return pd.DataFrame({"median": grouped.median(), "best": grouped.max(), "rows": grouped.size()})


def paired(
    control: pd.DataFrame,
    treatment: pd.DataFrame,
    by: str,
    cell_keys: list[str] | None = None,
) -> pd.DataFrame:
    """Return every cell both arms are viable in, with the control and treatment values side by side.

    ``cell_keys`` widens :data:`CELL_KEYS` for arms spanning several base variants.
    """
    # De-duplicated, order kept: a caller naming a column ``shared_columns`` also derives must
    # not key on it twice, which ``reset_index`` refuses rather than ignores.
    keys: list[str] = list(
        dict.fromkeys((cell_keys or CELL_KEYS) + shared_columns(control, treatment)),
    )
    joined: pd.DataFrame = cells(control, keys, by).join(
        cells(treatment, keys, by),
        how="inner",
        lsuffix="_control",
        rsuffix="_treatment",
    )
    joined["delta"] = joined["median_treatment"] - joined["median_control"]

    return joined.reset_index()


def sign_test(improved: int, total: int) -> float:
    """Compute a two-sided exact binomial p for ``improved`` of ``total`` cells, against a fair coin.

    A zero difference counts as not improved. The division stays in integers until the last
    step, because ``2.0 ** total`` overflows above 1,023 pairs ([#292]).
    """
    if total <= 0:
        return float("nan")

    tail: int = sum(math.comb(total, k) for k in range(min(improved, total - improved) + 1))

    return min(1.0, 2.0 * (tail / 2**total))


def verdict(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one row per root x resolution: how many cells the treatment improved, and by how much."""
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


def report(
    name: str,
    control: str,
    treatment: str,
    windows: list[str],
    by: str,
    stratum: str | None = None,
) -> pd.DataFrame:
    """Return the paired verdict for one control/treatment pair of variants, in one stratum if named.

    A report row pools every stratum of a root and resolution, so a verdict pre-registered on one
    cell has to name it -- ``docs/findings/m45-ibt-sizing-preregistration.md``.
    """
    stored: pd.DataFrame = load(name, windows)
    if stratum is not None:
        stored = stored[stored["stratum"] == stratum]

    left: pd.DataFrame = stored[stored["variant"] == control]
    right: pd.DataFrame = stored[stored["variant"] == treatment]
    if left.empty or right.empty:
        msg: str = (
            f"{name}: no viable rows for control={control!r} ({len(left)}) or "
            f"treatment={treatment!r} ({len(right)}) in windows {windows}"
            f"{'' if stratum is None else f' and stratum {stratum!r}'}. "
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
    parser.add_argument("--stratum", default=None, help="read one stratum alone rather than pooling them")
    args = parser.parse_args(argv[1:])

    table: pd.DataFrame = report(
        args.strategy, args.control, args.treatment, args.window, args.by, args.stratum
    )
    logger.info("")
    logger.info("%s: %r against %r on %s", args.strategy, args.treatment, args.control, args.by)
    logger.info("windows: %s; stratum: %s", ", ".join(args.window), args.stratum or "all, pooled")
    logger.info("")
    for line in table.to_string(index=False, float_format=lambda v: f"{v:.3f}").splitlines():
        logger.info("%s", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
