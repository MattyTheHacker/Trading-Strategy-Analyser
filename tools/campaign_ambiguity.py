"""Re-run a campaign shortlist under both ambiguity policies, and report the spread.

    ./.venv/Scripts/python.exe tools/campaign_ambiguity.py --strategy OpeningRange --root MNQ
    ./.venv/Scripts/python.exe tools/campaign_ambiguity.py --strategy OpeningRange --window holdout

A shortlist ranks on profit factor, and nothing in that ranking stops it picking a configuration
whose profit factor is an artefact of ``ambiguity_policy`` rather than of the strategy: where an
archetype has configurations that resolve many bars by assumption, that is where the largest
profit factors are -- ``docs/roadmap.md`` §M28.2.

``ambiguous_share`` counts how often the assumption was invoked, which is not how much the
answer depends on it, and the two come apart in both directions. This re-runs each shortlisted
row under :data:`SECOND_ARM` as well and reports the **spread** between the two profit factors,
which is the width of the band the bar data cannot narrow -- ``docs/roadmap.md`` §M28.3.

**The ranking statistic stays :data:`RANKED_POLICY`, and nothing here re-orders a shortlist or
drops a row.** The second arm is deliberately more pessimistic than NT8, so selecting on it
would select against a fill rule the prime directive rejects -- ``docs/roadmap.md``
§ "Eleven strata per root, one dimension at a time". It is attribution, not selection.

Each row is re-run on the bars its own ``window`` names, so the first arm reproduces the stored
figure exactly; ``tools/campaign_shortlist.verify`` refuses it otherwise.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_montecarlo import labelled
from tools.campaign_null import label_of
from tools.campaign_report import SHARES, swept_axes
from tools.campaign_shortlist import TOP, rebuild, shortlist, source, verify

from nqbt import archetypes, context, logsetup, resample, splice, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE

logger = logging.getLogger(__name__)

RANKED_POLICY = AMBIGUITY_NEAREST_TO_OPEN
"""What every stored row was measured under, and what a shortlist keeps ranking on.

Forced rather than taken from the row, so a stored configuration carrying anything else fails
``verify`` instead of quietly reporting a spread between two arms neither of which is NT8's."""

SECOND_ARM = AMBIGUITY_WORST_CASE
"""What the same configuration scores when every ambiguous bar is resolved against it."""

WORST = "profit_factor_worst"
SPREAD = "profit_factor_spread"
SURVIVES = "survives"

BREAKEVEN = 1.0
"""The profit factor :data:`SURVIVES` reads the second arm against."""

STATEMENT = "the claimed edge must survive the assumption"
"""What :data:`SURVIVES` means, said as a sentence rather than as a threshold on a share --
``docs/roadmap.md`` §M28.3. Reported here; it gates no selection."""


def measure_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    label: str,
) -> dict[str, object]:
    """One configuration's two profit factors, their spread, and the shares beside them.

    The first arm is checked against the summary the sweep stored, so a spread is never
    reported for a row the re-run did not reproduce.
    """
    params: archetypes.Params = rebuild(row, archetype)
    instrument = get_instrument(root)
    ranked, _ = sweep.run_combination(
        data,
        replace(params, ambiguity_policy=RANKED_POLICY),
        instrument,
        archetype,
        keep_trades=False,
    )
    verify(row, ranked)
    worst, _ = sweep.run_combination(
        data,
        replace(params, ambiguity_policy=SECOND_ARM),
        instrument,
        archetype,
        keep_trades=False,
    )

    observed: float = float(ranked["profit_factor"])  # type: ignore[arg-type]  # a statistic by construction
    pessimistic: float = float(worst["profit_factor"])  # type: ignore[arg-type]  # a statistic by construction
    measured: dict[str, object] = {
        **labelled(row),
        "label": label,
        "trades": int(ranked["trades"]),  # type: ignore[call-overload]  # a statistic by construction
        "profit_factor": observed,
        WORST: pessimistic,
        SPREAD: observed - pessimistic,
        SURVIVES: pessimistic > BREAKEVEN,
        **{share: float(ranked[share]) for share in SHARES},  # type: ignore[arg-type]  # statistics by construction
    }
    logger.info(
        "  %-44s PF %6.3f  worst %6.3f  spread %6.3f  ambiguous %5.3f  %5d trades",
        label,
        observed,
        pessimistic,
        measured[SPREAD],
        measured["ambiguous_share"],
        measured["trades"],
    )

    return measured


def measure(rows: pd.DataFrame, archetype: archetypes.Archetype, root: str) -> pd.DataFrame:
    """Every shortlisted configuration under both policies, one row each.

    Grouped by window and resolution, because the resample and the prepared dataset are the
    expensive parts and every row sharing those two shares both -- exactly as
    ``tools/campaign_shortlist.store_logs`` groups them.
    """
    axes: list[str] = swept_axes(rows)
    bars: pd.DataFrame = splice.load_continuous(root)

    measured: list[dict[str, object]] = []
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), int(minutes))
        rebuilt: list[tuple[pd.Series, archetypes.Params]] = [  # type: ignore[type-arg]  # duckdb's dtypes
            (row, rebuild(row, archetype)) for _, row in block.iterrows()
        ]
        spec: context.ContextSpec = context.ContextSpec()
        for _, params in rebuilt:
            spec = spec | sweep.Grid(base=params, archetype=archetype).required_context()
        data: context.Dataset = context.prepare(frame, spec, bar_minutes=int(minutes))

        measured.extend(measure_row(row, data, archetype, root, label_of(row, axes)) for row, _ in rebuilt)

    return pd.DataFrame(measured)


def survival(table: pd.DataFrame) -> list[str]:
    """How much of the shortlist is left once the assumption is taken away.

    Read rather than applied: the widest spread is the row whose result is least attributable,
    and a shortlist where that row is also the highest-ranked one is the §M28.2 shape.
    """
    if table.empty:
        return ["  (nothing was measured)"]

    kept: int = int(table[SURVIVES].sum())
    # Bare: ``.loc`` on one label is a Series here and a DataFrame to mypy, so no honest annotation.
    widest = table.loc[table[SPREAD].idxmax()]
    band: str = f"{widest['profit_factor']:.3f} -> {widest[WORST]:.3f}"

    return [
        f"  {STATEMENT}",
        f"  {kept} of {len(table)} keep a profit factor above {BREAKEVEN:.2f} under the worst case",
        f"  widest spread    {widest['label']}",
        f"    {band}  on ambiguous_share {widest['ambiguous_share']:.3f}",
        f"  median spread    {table[SPREAD].median():.3f}",
    ]


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="Ambiguity spread over a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--window", nargs="+", default=["holdout"], help="which stored rows rank")
    parser.add_argument("--by", default="profit_factor", help="which statistic picks the rows")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to re-run")
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = shortlist(
        args.strategy,
        args.root,
        args.window,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        args.variant,
    )
    logger.info(
        "%s on %s: %d configurations ranked on %s by %s, re-run under both policies",
        args.strategy,
        args.root,
        len(rows),
        "+".join(args.window),
        args.by,
    )

    table: pd.DataFrame = measure(rows, archetypes.get(args.strategy), args.root)
    show("both policies side by side, and the band between them", table)
    logger.info("")
    logger.info("--- what the spread leaves ---")
    for line in survival(table):
        logger.info("%s", line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
