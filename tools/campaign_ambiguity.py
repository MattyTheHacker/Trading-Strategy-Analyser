"""Re-run a campaign shortlist under both ambiguity policies, and report the spread.

    uv run tools/campaign_ambiguity.py --strategy OpeningRange --root MNQ
    uv run tools/campaign_ambiguity.py --strategy OpeningRange --window holdout
    uv run tools/campaign_ambiguity.py --strategy EmaPullback --window holdout --fill-bars

``tools/README.md`` § "campaign_ambiguity.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, disambiguate, logsetup, resample, splice, stats, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import AMBIGUITY_BEST_CASE, AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE
from tools.campaign_montecarlo import labelled
from tools.campaign_null import label_of
from tools.campaign_report import SHARES, swept_axes
from tools.campaign_shortlist import TOP, prepared, rebuild, run_logged, shortlist, source, verify

logger = logging.getLogger(__name__)

RANKED_POLICY = AMBIGUITY_NEAREST_TO_OPEN
"""What every stored row was measured under, and what a shortlist keeps ranking on.

Forced rather than read from the row, so ``verify`` fails a configuration carrying anything
else.
"""

SECOND_ARM = AMBIGUITY_WORST_CASE
"""What the same configuration scores when every ambiguous bar is resolved against it."""

THIRD_ARM = AMBIGUITY_BEST_CASE
"""The other end of the band, never reported on its own -- :data:`nqbt.disambiguate.ARM_FOR`."""

RESOLVED = "profit_factor_resolved"
MOVE = "resolved_move"

WORST = "profit_factor_worst"
SPREAD = "profit_factor_spread"
SURVIVES = "survives"

BREAKEVEN = 1.0
"""The profit factor :data:`SURVIVES` reads the second arm against."""

type RowReader = Callable[  # type: ignore[explicit-any]  # duckdb's dtypes
    [pd.Series, context.Dataset, archetypes.Archetype, str, pd.DataFrame, pd.DataFrame, str],
    tuple[dict[str, object], pd.DataFrame],
]
"""What :func:`over_minute_bars` runs on each row, beside its dataset and its minute and coarse bars."""

STATEMENT = "the claimed edge must survive the assumption"
"""What :data:`SURVIVES` means, said as a sentence rather than as a threshold on a share --
``docs/roadmap.md`` §M28.3. Reported here; it gates no selection."""


def measure_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    label: str,
) -> dict[str, object]:
    """Measure one configuration's two profit factors, their spread, and the shares beside them.

    The first arm is checked against the summary the sweep stored, so a spread is never
    reported for a row the re-run did not reproduce.
    """
    params: archetypes.ArchetypeParams = rebuild(row, archetype)
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
    """Measure every shortlisted configuration under both policies, one row each."""
    axes: list[str] = swept_axes(rows)
    bars: pd.DataFrame = splice.load_continuous(root)

    measured: list[dict[str, object]] = []
    for (window, minutes), block in rows.groupby(["window", "resolution"], sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[call-overload]  # a groupby key on an int column
        frame: pd.DataFrame = resample.resample(source(bars, str(window)), bar_minutes)
        rebuilt = [(row, rebuild(row, archetype)) for _, row in block.iterrows()]
        spec: context.ContextSpec = context.ContextSpec()
        for _, params in rebuilt:
            spec = spec | sweep.Grid(base=params, archetype=archetype).required_context()
        data: context.Dataset = context.prepare(
            frame,
            spec,
            bar_minutes=bar_minutes,
            price_basis=context.PriceBasis.RAW,
        )

        measured.extend(measure_row(row, data, archetype, root, label_of(row, axes)) for row, _ in rebuilt)

    return pd.DataFrame(measured)


def over_minute_bars(
    selected: pd.DataFrame,
    axes: list[str],
    archetype: archetypes.Archetype,
    root: str,
    read_row: RowReader,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run ``read_row`` on each selected row against its own window's minute bars, and stack the results.

    Returns the headline rows and the per-row tables, one of each per row.
    """
    bars: pd.DataFrame = splice.load_continuous(root)
    measured: list[dict[str, object]] = []
    tables: list[pd.DataFrame] = []
    for (window, minutes), block in selected.groupby(["window", "resolution"], sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[call-overload]  # a groupby key on an int column
        fine: pd.DataFrame = source(bars, str(window))
        coarse: pd.DataFrame = resample.resample(fine, bar_minutes)
        _, data = prepared(block, coarse, archetype, bar_minutes, context.PriceBasis.RAW)
        for _, row in block.iterrows():
            headline, table = read_row(row, data, archetype, root, fine, coarse, label_of(row, axes))
            measured.append(headline)
            tables.append(table)

    return pd.DataFrame(measured), pd.concat(tables, ignore_index=True)


def settle_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    fine: pd.DataFrame,
    coarse: pd.DataFrame,
    label: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Settle one configuration's ambiguous bars against the minute bars inside them.

    Runs all three arms so that a settled bar's outcome is taken from the arm that resolved it
    that way, rather than recomputed. Returns the headline row and the per-bar verdicts.
    """
    params: archetypes.ArchetypeParams = rebuild(row, archetype)
    instrument = get_instrument(root)
    arms: dict[int, pd.DataFrame] = {}
    ranked: dict[str, object] = {}
    for policy in (RANKED_POLICY, SECOND_ARM, THIRD_ARM):
        summary, log = sweep.run_combination(
            data,
            replace(params, ambiguity_policy=policy),
            instrument,
            archetype,
            keep_trades=True,
        )
        if log is None:  # pragma: no cover - keep_trades always returns a log
            msg: str = "run_combination kept no log with keep_trades set"
            raise RuntimeError(msg)

        arms[policy] = log
        if policy == RANKED_POLICY:
            ranked = summary
    verify(row, ranked)

    slippage: float = float(row["slippage_ticks"]) * instrument.tick_size
    verdicts: pd.DataFrame = disambiguate.resolve(
        arms[RANKED_POLICY],
        arms[SECOND_ARM],
        fine,
        coarse,
        slippage=slippage,
        fill_limit_on_touch=bool(params.fill_limit_on_touch),
    )
    resolved: pd.DataFrame = disambiguate.resolved_log(
        arms[RANKED_POLICY],
        arms[SECOND_ARM],
        arms[THIRD_ARM],
        verdicts,
    )
    observed: float = float(ranked["profit_factor"])  # type: ignore[arg-type]  # a statistic by construction
    settled: float = stats.summarise(resolved).profit_factor
    measured: dict[str, object] = {
        **labelled(row),
        "label": label,
        "ambiguous_share": float(row["ambiguous_share"]),
        **disambiguate.accuracy(verdicts),
        "profit_factor": observed,
        RESOLVED: settled,
        MOVE: settled - observed,
    }
    logger.info(
        "  %-44s PF %6.3f  resolved %6.3f  move %+6.3f  assumption right %s of %s",
        label,
        observed,
        settled,
        measured[MOVE],
        measured["assumption_correct"],
        measured["decided"],
    )

    return measured, verdicts.assign(label=label)


def settle(
    rows: pd.DataFrame, archetype: archetypes.Archetype, root: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Settle every shortlisted row whose ambiguity clears the threshold, and only those."""
    qualifying: pd.DataFrame = rows[rows["ambiguous_share"].map(disambiguate.worth_resolving)]
    if qualifying.empty:
        return pd.DataFrame(), pd.DataFrame()

    return over_minute_bars(qualifying, swept_axes(rows), archetype, root, settle_row)


def fill_bar_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    data: context.Dataset,
    archetype: archetypes.Archetype,
    root: str,
    fine: pd.DataFrame,
    coarse: pd.DataFrame,
    label: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Read one stop-entry configuration's fill bars against the minute bars inside them.

    Returns the headline row and every leg's two readings.
    """
    params: archetypes.ArchetypeParams = rebuild(row, archetype)
    summary, log = run_logged(data, replace(params, ambiguity_policy=RANKED_POLICY), root, archetype)
    verify(row, summary)

    slippage: float = float(row["slippage_ticks"]) * get_instrument(root).tick_size
    legs: pd.DataFrame = disambiguate.check_fill_bars(
        log,
        fine,
        coarse,
        slippage=slippage,
        fill_limit_on_touch=bool(params.fill_limit_on_touch),
    )
    counts: dict[str, object] = disambiguate.fill_bar_accuracy(legs)
    measured: dict[str, object] = {
        **labelled(row),
        "label": label,
        "profit_factor": float(summary["profit_factor"]),  # type: ignore[arg-type]  # a statistic by construction
        "net_pnl": float(summary["net_pnl"]),  # type: ignore[arg-type]  # a statistic by construction
        **counts,
    }
    logger.info(
        "  %-44s PF %6.3f  path right %s of %s  spared %s legs making %s of the net",
        label,
        measured["profit_factor"],
        counts["path_correct"],
        counts["scored"],
        counts["path_spared"],
        counts["spared_share"],
    )

    return measured, legs.assign(label=label)


def check_fill_bars(
    rows: pd.DataFrame, archetype: archetypes.Archetype, root: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the fill bars of every shortlisted row that enters on a stop order, and skip the rest."""
    enters_on_stop = pd.Series(
        [disambiguate.enters_on_stop(rebuild(row, archetype)) for _, row in rows.iterrows()],
        index=rows.index,
        dtype=bool,
    )
    stop_entries: pd.DataFrame = rows[enters_on_stop]
    if stop_entries.empty:
        return pd.DataFrame(), pd.DataFrame()

    return over_minute_bars(stop_entries, swept_axes(rows), archetype, root, fill_bar_row)


def survival(table: pd.DataFrame) -> list[str]:
    """Report how much of the shortlist is left once the assumption is taken away.

    Read rather than applied: the widest spread is the row whose result is least attributable,
    and a shortlist where that row is also the highest-ranked one is the §M28.2 shape. A row with
    no losing trade under either policy has no spread, and is counted on its own line.
    """
    if table.empty:
        return ["  (nothing was measured)"]

    kept: int = int(table[SURVIVES].sum())
    no_losing_trade = table[["profit_factor", WORST]].eq(float("inf")).all(axis="columns")
    lines: list[str] = [
        f"  {STATEMENT}",
        f"  {kept} of {len(table)} keep a profit factor above {BREAKEVEN:.2f} under the worst case",
        *spread_lines(table[~no_losing_trade]),
    ]
    if no_losing_trade.any():
        lines.append(f"  no losing trade  {int(no_losing_trade.sum())} under either policy, spread undefined")

    return lines


def spread_lines(defined: pd.DataFrame) -> list[str]:
    """Return the widest and median spread over rows whose spread is defined."""
    if defined.empty:
        return ["  widest spread    none defined"]

    widest = defined.iloc[defined[SPREAD].argmax()]
    band: str = f"{widest['profit_factor']:.3f} -> {widest[WORST]:.3f}"

    return [
        f"  widest spread    {widest['label']}",
        f"    {band}  on ambiguous_share {widest['ambiguous_share']:.3f}",
        f"  median spread    {defined[SPREAD].median():.3f}",
    ]


def unsettled(verdicts: pd.DataFrame) -> pd.DataFrame:
    """Return the bars worth looking at: the ones the assumption got wrong, and the ones still open.

    A bar the assumption called correctly is evidence and not a finding, and printing every one
    of them buries the handful that moved the result.
    """
    if verdicts.empty:
        return verdicts

    # A nullable boolean: NA is "not settled", so it has to survive the filter rather than be
    # compared away -- ``!= True`` on NA is NA, which drops exactly the rows this exists to show.
    return verdicts[~verdicts["agrees"].fillna(value=False).astype(bool)]


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def report_settled(rows: pd.DataFrame, archetype: archetypes.Archetype, root: str) -> None:
    """Settle the band against the minute bars, and print what that corrected."""
    logger.info("")
    logger.info(
        "--- settling the band against the minute bars, above %.0f%% ambiguous ---",
        100.0 * disambiguate.MIN_AMBIGUOUS_SHARE,
    )
    settled, verdicts = settle(rows, archetype, root)
    if settled.empty:
        logger.info("no shortlisted row resolves enough bars by assumption to be worth settling")

        return

    show("the assumption scored, and the result with it corrected", settled)
    show(
        "the bars the assumption got wrong, and the ones a minute bar cannot settle",
        unsettled(verdicts),
    )


def report_fill_bars(rows: pd.DataFrame, archetype: archetypes.Archetype, root: str) -> None:
    """Read each stop entry's own bar against the minute bars, and print where the two part."""
    logger.info("")
    logger.info("--- reading each stop entry's own bar against the minute bars inside it ---")
    checked, legs = check_fill_bars(rows, archetype, root)
    if checked.empty:
        logger.info("no shortlisted row enters on a stop order")

        return

    show("the path scored on each fill bar, and what the legs it spared made", checked)
    show(
        "every fill-bar leg, by how the path and the minute bars each read it",
        legs.groupby(["simulated", "minute"]).size().reset_index(name="legs"),
    )


def main(argv: list[str]) -> int:
    """Measure the ambiguity spread and return the process exit code."""
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
    parser.add_argument(
        "--no-settle",
        action="store_true",
        help="skip settling the band against the minute bars inside each ambiguous bar",
    )
    parser.add_argument(
        "--fill-bars",
        action="store_true",
        help="also read each stop entry's own bar against the minute bars inside it",
    )
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

    archetype: archetypes.Archetype = archetypes.get(args.strategy)
    table: pd.DataFrame = measure(rows, archetype, args.root)
    show("both policies side by side, and the band between them", table)
    logger.info("")
    logger.info("--- what the spread leaves ---")
    for line in survival(table):
        logger.info("%s", line)

    if not args.no_settle:
        report_settled(rows, archetype, args.root)

    if args.fill_bars:
        report_fill_bars(rows, archetype, args.root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
