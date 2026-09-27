r"""Fit the cuts a confluence size runs at, and read it against its own sizes shuffled.

    ./.venv/Scripts/python.exe tools/campaign_sizing.py fit --strategy ElasticBand \
        --resolutions 2 5 10 15
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies ElasticBand \
        --variants confluence-sizing --split --strata confluence-sizing --resolutions 2 5 10 15
    ./.venv/Scripts/python.exe tools/campaign_sizing.py null --strategy ElasticBand --root MNQ \
        --resolution 5 --variant "target=0.0s size=confluence"

InsideBarTrailing is the default strategy, and there the null reads §M45's confluence arm unless
``--variant`` names another -- ``docs/findings/m45-ibt-sizing-preregistration.md``.

**Everything ``fit`` measures comes from the selection window**, so the held-out window reads
cuts it had no part in -- the rule ``tools/campaign_sweep.py``'s regime fit states. Each cut is
taken at a stored variant's base configuration over its unfiltered signal, pooled over the sides
the variant sweeps, and written before any sizing arm runs: the file is the pre-registration of
every threshold the arms read. **A cut already in the file is kept**, so the arms stored against
it keep the cut they ran at -- ``docs/findings/m47-confluence-sizing-preregistration.md``.

**The shuffled-size null is the control a confluence size needs**, and a matched random entry is
not it: the entries are the rule's own and only which size each took is permuted, so what it
measures is whether the count put the larger sizes on the better trades. On InsideBarTrailing a
size moves the trades, so each shuffle is re-simulated across the signals. Everywhere else it
moves only the dollars -- ``docs/findings/m46-registry-size-ladder.md`` -- so each shuffle permutes
the sizes across the trades actually taken and recomputes their money exactly, and both halves of
that premise are checked on every configuration before a shuffle is drawn.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_holdout import held_out
from tools.campaign_null import stored_rows
from tools.campaign_report import log_key
from tools.campaign_shortlist import TOP, rebuild
from tools.campaign_sweep import (
    RESOLUTIONS,
    ROOTS,
    SELECTION_SHARE,
    SIZING_CONFLUENCE,
    SIZING_LABEL_QUANTILES,
    VARIANTS,
    SizingCut,
    Variant,
    sizing_cuts_path,
)
from tools.campaign_swept import HELD_OUT, bars_for, candidate_bars

from nqbt import (
    archetypes,
    conditions,
    context,
    logsetup,
    regime,
    resample,
    splice,
    stats,
    sweep,
    trades,
    volume,
)
from nqbt.instruments import get_instrument
from nqbt.sim import (
    bracket,
    crossover,
    elasticband,
    emapullback,
    filters,
    insidebar,
    insidebartrailing,
    openingrange,
    pullback,
    runner,
    squeeze,
)
from nqbt.sim.types import (
    EARLINESS_MODES,
    EARLINESS_OFF,
    SIZING_LABELS,
    InsideBarTrailingParams,
    sizing_labels,
)
from nqbt.trades import (
    C_COMMISSION,
    C_DIRECTION,
    C_ENTRY_PRICE,
    C_EXIT_PRICE,
    C_GROSS_PNL,
    C_LEG,
    C_NET_PNL,
    C_QUANTITY,
    C_TRADE_ID,
    N_COLUMNS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from nqbt.archetypes import Params
    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.instruments import Instrument

logger = logging.getLogger(__name__)

EARLY_QUANTILE = 0.5
"""Where the extension and trend-age cuts sit among the fitted signals: half early, half not."""

MIN_FAVOURABLE_SHARE = 0.10
MAX_FAVOURABLE_SHARE = 0.90
"""A label favouring fewer or more of the fitted signals than this is dropped from the count.

Near-constant at the signal, it adds the same contract to almost every trade and sorts nothing --
the entry already implies it, as ``above_ema_21`` did for EmaCrossover --
``docs/findings/confluence-count-per-trade.md``."""

DRAWS = 200
"""Shuffles per configuration: enough for a p-value of 0.005 to be reachable."""

CONFLUENCE_VARIANT = f"trailing {SIZING_CONFLUENCE}"
"""The stored variant name of §M45's confluence arm, which InsideBarTrailing's null reads."""

SIDES: dict[str, Callable[..., BoolArray]] = {
    archetypes.DEADCATBOUNCE.name: lambda data, _params: runner.deadcat_long_side(data),
    archetypes.PULLBACKANDGO.name: lambda data, _params: pullback.pullback_long_side(data),
    archetypes.EMACROSSOVER.name: crossover.crossover_long_side,
    archetypes.EMAPULLBACK.name: emapullback.emapullback_long_side,
    archetypes.INSIDEBAR.name: insidebar.insidebar_long_side,
    archetypes.INSIDEBARTRAILING.name: insidebar.insidebar_long_side,
    archetypes.ELASTICBAND.name: elasticband.elasticband_long_side,
    archetypes.OPENINGRANGE.name: openingrange.openingrange_long_side,
    archetypes.SQUEEZEBREAKOUT.name: squeeze.squeeze_long_side,
}
"""Which bars each archetype would enter long, which is what a sided label is read against."""

SIZED_COLUMNS = (C_QUANTITY, C_GROSS_PNL, C_COMMISSION, C_NET_PNL)
"""The four leg columns a size writes. Every other one is the trade itself."""


def probe_params(base: Params) -> Params:
    """``base`` with every label switched on, so one prepared dataset holds all five."""
    return dataclasses.replace(
        base,
        quantity_per_confluence=1,
        size_symmetric=False,
        **dict.fromkeys(SIZING_LABELS, True),
    )


def age_at(data: context.Dataset, params: InsideBarTrailingParams, direction_at: FloatArray) -> IntArray:
    """How many bars the trend on each bar's side has run, the bar included."""
    up, down = insidebar.insidebar_trends(data, params)
    long_side: BoolArray = direction_at == trades.LONG

    return np.where(long_side, conditions.consecutive_true(up), conditions.consecutive_true(down))


def extension_at(data: context.Dataset, params: InsideBarTrailingParams) -> FloatArray:
    """How far each close sits from the slow SMA, in ATRs."""
    slow: FloatArray = data.ma_values(params.slow_sma_kind, params.slow_sma_period)
    with np.errstate(divide="ignore", invalid="ignore"):
        extension: FloatArray = np.abs(data.close - slow) / data.atr_values(params.atr_length)

    return extension


def favourable_shares(data: context.Dataset, labelled: Params, campaign: Variant) -> dict[str, float]:
    """Each label's share of the unfiltered signals it favours, pooled over the sides swept.

    A variant sweeping ``direction`` trades both sides of the same signal and a sided label favours
    one of them, so a share read on one side alone would be the other side's complement.
    """
    archetype: archetypes.Archetype = campaign.archetype
    sides: list[object] = list(campaign.axes.get("direction", []))
    configurations: list[Params] = (
        [dataclasses.replace(labelled, direction=side) for side in sides] if sides else [labelled]
    )
    at_signals: list[list[BoolArray]] = []
    for params in configurations:
        signal: BoolArray = archetype.signal(data, params)
        rows: list[BoolArray] = filters.favourable_labels(data, params, SIDES[archetype.name](data, params))
        at_signals.append([row[signal] for row in rows])

    if not sum(int(rows[0].size) for rows in at_signals):
        msg: str = f"{archetype.name} {campaign.name}: no signal in the selection window to fit a cut at"
        raise SystemExit(msg)

    return {
        label: float(np.concatenate([rows[position] for rows in at_signals]).mean())
        for position, label in enumerate(SIZING_LABELS)
    }


def fit_cut(
    frame: pd.DataFrame,
    root: str,
    minutes: int,
    campaign: Variant,
    *,
    variant: str | None = None,
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """One root, resolution and variant's cut, with what it was read off.

    The report holds each label's favourable share at the fitted signals and, on
    InsideBarTrailing, per earliness rule the share of the base configuration's own trades that
    came out early under the fitted cut.
    """
    probe: Params = probe_params(campaign.base)
    data: context.Dataset = context.prepare(
        frame,
        sweep.Grid.of(probe, archetype=campaign.archetype).required_context(),
        bar_minutes=minutes,
        price_basis=context.PriceBasis.RAW,
    )
    consolidating, directional = regime.thresholds_from_quantiles(
        data.regime_values(probe.regime_lookback),
        *SIZING_LABEL_QUANTILES,
    )
    thin, heavy = volume.thresholds_from_quantiles(
        data.relative_volume(probe.volume_key), *SIZING_LABEL_QUANTILES
    )
    labelled: Params = dataclasses.replace(
        probe,
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
    )
    shares: dict[str, float] = favourable_shares(data, labelled, campaign)
    cut: SizingCut = SizingCut(
        root=root,
        minutes=minutes,
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
        labels=kept_labels(shares),
        variant=variant,
    )
    report: dict[str, dict[str, float]] = {"favourable_share": shares}
    if campaign.archetype.name != archetypes.INSIDEBARTRAILING.name:
        return cut, report

    return earliness_cut(data, cut, campaign.base, report, get_instrument(root))


def earliness_cut(
    data: context.Dataset,
    cut: SizingCut,
    base: Params,
    report: dict[str, dict[str, float]],
    instrument: Instrument,
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """InsideBarTrailing's cut with its earliness cuts fitted in, at the median of its signals."""
    if not isinstance(base, InsideBarTrailingParams):  # pragma: no cover - by construction
        msg: str = f"the stored InsideBarTrailing variant carries {type(base).__name__}"
        raise TypeError(msg)

    signal: BoolArray = insidebar.insidebar_signal(data, base)
    direction_at: FloatArray = insidebar.insidebar_direction(data, base)
    extension: FloatArray = extension_at(data, base)[signal]
    tiered: SizingCut = dataclasses.replace(
        cut,
        early_max_extension_atr=float(np.quantile(extension[np.isfinite(extension)], EARLY_QUANTILE)),
        early_max_trend_bars=int(np.quantile(age_at(data, base, direction_at)[signal], EARLY_QUANTILE)),
    )

    return tiered, {**report, "traded_early_share": traded_early_shares(data, tiered, base, instrument)}


def traded_early_shares(
    data: context.Dataset,
    cut: SizingCut,
    base: InsideBarTrailingParams,
    instrument: Instrument,
) -> dict[str, float]:
    """Per earliness rule, the share of the base configuration's trades whose signal bar was early.

    Counted over the trades taken rather than the signals, because a setup that arrives while a
    position is open is never traded: a rule near either end leaves its tier running as one of
    the fixed splits.
    """
    direction_at: FloatArray = insidebar.insidebar_direction(data, base)
    shares: dict[str, float] = {}
    for mode, name in EARLINESS_MODES.items():
        if mode == EARLINESS_OFF:
            continue

        tiered: InsideBarTrailingParams = dataclasses.replace(
            base,
            earliness_mode=mode,
            early_max_extension_atr=cut.early_max_extension_atr,
            early_max_trend_bars=cut.early_max_trend_bars,
        )
        log: pd.DataFrame = insidebartrailing.run_insidebartrailing(
            data, tiered, instrument, with_times=False
        )
        signal_bars: IntArray = log.groupby("trade_id")["entry_bar"].first().to_numpy() - 1
        early: BoolArray = insidebartrailing.early_entries(data, tiered, direction_at)
        shares[name] = float(early[signal_bars].mean()) if signal_bars.size else float("nan")

    return shares


def kept_labels(shares: dict[str, float]) -> tuple[str, ...]:
    """The labels whose favourable share at the fitted signals leaves them something to sort."""
    return tuple(
        label for label, share in shares.items() if MIN_FAVOURABLE_SHARE <= share <= MAX_FAVOURABLE_SHARE
    )


def selection_window(bars: pd.DataFrame) -> pd.DataFrame:
    """The bars the campaign's selection window holds, which is all a fit may read."""
    return bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]


def fit(name: str, roots: list[str], resolutions: list[int], path: Path) -> list[dict[str, object]]:
    """Fit every root, resolution and stored variant ``path`` does not hold yet, and write them all.

    A cut already there is kept rather than refitted, so the arms stored against it keep the cut
    they ran at; move the file aside to refit from scratch. The variant is recorded only where the
    archetype has more than one.
    """
    written: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    stored: set[tuple[str, int, object]] = {
        (str(cut["root"]), int(str(cut["minutes"])), cut.get("variant")) for cut in written
    }
    for root in roots:
        campaigns: list[Variant] = VARIANTS[name](root)
        selection: pd.DataFrame = selection_window(splice.load_continuous(root))
        for minutes in resolutions:
            frame: pd.DataFrame = resample.resample(selection, minutes)
            for campaign in campaigns:
                variant: str | None = campaign.name if len(campaigns) > 1 else None
                if not campaign.runs_at(minutes) or (root, minutes, variant) in stored:
                    continue

                cut, report = fit_cut(frame, root, minutes, campaign, variant=variant)
                written.append({**dataclasses.asdict(cut), **report})
                log_cut(cut, report)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(written, indent=2), encoding="utf-8")
    logger.info("wrote %d cuts to %s", len(written), path)

    return written


def log_cut(cut: SizingCut, report: dict[str, dict[str, float]]) -> None:
    """Report one fitted cut and what it was read off."""
    logger.info(
        "  %-4s %2dm %-40s labels %s",
        cut.root,
        cut.minutes,
        cut.variant or "",
        ", ".join(cut.labels) or "none",
    )
    for label, share in report["favourable_share"].items():
        logger.info("        %-26s favours %5.1f%% of signals", label, 100.0 * share)
    for rule, share in report.get("traded_early_share", {}).items():
        logger.info("        %-26s %5.1f%% of traded entries early", rule, 100.0 * share)


def placed(observed: dict[str, float], by: str, null: FloatArray) -> dict[str, float]:
    """The observation against its null, with the trade count and shares a reading needs beside it.

    ``p`` is the share of shuffles at least as good, counting the observation itself, so it is
    never zero -- the convention ``nqbt/randomentry.py`` reports its matched null in.
    """
    median: float = float(np.median(null))

    return {
        "observed": observed[by],
        "null_median": median,
        "excess": observed[by] - median,
        "p": (1 + int(np.sum(null >= observed[by]))) / (1 + null.size),
        "trades": observed["trades"],
        "session_close_share": observed["session_close_share"],
        "ambiguous_share": observed["ambiguous_share"],
    }


def permuted_sizing(sizing: bracket.Sizing, signal: BoolArray, rng: np.random.Generator) -> bracket.Sizing:
    """``sizing`` with the rows its signal bars take shuffled among them, and every other bar kept."""
    rows: IntArray = sizing.row_at.copy()
    rows[signal] = rng.permutation(rows[signal])

    return bracket.Sizing(sizing.quantities, rows)


def resimulated_null(
    data: context.Dataset,
    params: InsideBarTrailingParams,
    instrument: Instrument,
    *,
    by: str,
    draws: int,
    seed: int,
) -> dict[str, float]:
    """InsideBarTrailing's ``by`` against the same sizes shuffled across its signals, re-simulated.

    A size moves this archetype's trades through the ``-200`` gate, so each shuffle is run.
    """
    direction_at: FloatArray = insidebar.insidebar_direction(data, params)
    signal: BoolArray = insidebar.insidebar_signal(data, params)
    sizing: bracket.Sizing = insidebartrailing.lot_sizing(data, params, direction_at)

    def measured(lots: bracket.Sizing) -> dict[str, float]:
        legs = insidebartrailing.insidebartrailing_legs(data, params, instrument, sizing=lots)

        return stats.summarise_legs(legs, data.day_codes).as_dict()

    observed: dict[str, float] = measured(sizing)
    rng: np.random.Generator = np.random.default_rng(seed)
    null: FloatArray = np.array([measured(permuted_sizing(sizing, signal, rng))[by] for _ in range(draws)])

    return placed(observed, by, null)


def unsized(params: Params) -> Params:
    """``params`` at its fixed size, with the confluence size switched off."""
    return dataclasses.replace(
        params,
        quantity_per_confluence=0,
        size_symmetric=False,
        **dict.fromkeys(SIZING_LABELS, False),
    )


def same_trades(sized: trades.LegMatrix, fixed: trades.LegMatrix) -> bool:
    """Whether two runs took the same trades leg for leg, whatever size each took them at."""
    if sized.count != fixed.count:
        return False

    kept: list[int] = [column for column in range(N_COLUMNS) if column not in SIZED_COLUMNS]

    return bool(
        np.array_equal(sized.matrix[: sized.count, kept], fixed.matrix[: fixed.count, kept], equal_nan=True),
    )


def trade_rows(legs: trades.LegMatrix, table: IntArray) -> tuple[IntArray, IntArray, IntArray]:
    """Each leg's trade, each leg's place in its trade, and the table row each trade was sized at."""
    matrix: FloatArray = legs.matrix[: legs.count]
    _, trade_of_leg = np.unique(matrix[:, C_TRADE_ID], return_inverse=True)
    leg: IntArray = matrix[:, C_LEG].astype(np.int64) - 1
    taken: IntArray = np.zeros((int(trade_of_leg.max(initial=-1)) + 1, table.shape[1]), dtype=np.int64)
    taken[trade_of_leg, leg] = matrix[:, C_QUANTITY].astype(np.int64)
    matches: BoolArray = (taken[:, None, :] == table[None, :, :]).all(axis=2)
    if not matches.any(axis=1).all():
        msg: str = "a trade took a size its combination's table has no row for"
        raise RuntimeError(msg)

    return trade_of_leg, leg, matches.argmax(axis=1)


def resized(
    legs: trades.LegMatrix, quantities: IntArray, point_value: float, commission: float
) -> trades.LegMatrix:
    """``legs`` at other sizes, their money recomputed exactly as ``bracket.write_leg`` writes it."""
    matrix: FloatArray = legs.matrix[: legs.count].copy()
    per_unit: FloatArray = (matrix[:, C_EXIT_PRICE] - matrix[:, C_ENTRY_PRICE]) * matrix[:, C_DIRECTION]
    gross: FloatArray = per_unit * quantities * point_value
    fees: FloatArray = commission * quantities
    matrix[:, C_QUANTITY] = quantities
    matrix[:, C_GROSS_PNL] = gross
    matrix[:, C_COMMISSION] = fees
    matrix[:, C_NET_PNL] = gross - fees

    return trades.LegMatrix(matrix, legs.count)


def recomputed_null(
    data: context.Dataset,
    params: Params,
    instrument: Instrument,
    archetype: archetypes.Archetype,
    *,
    by: str,
    draws: int,
    seed: int,
) -> dict[str, float]:
    """The configuration's own ``by`` against its sizes shuffled across the trades it took.

    Exact rather than re-simulated, because outside InsideBarTrailing a size moves no trade. Both
    halves are checked on the configuration itself first: the fixed size takes the same trades,
    and recomputing the sizes it did take reproduces the simulation to the bit.
    """
    legs: trades.LegMatrix = archetype.legs(data, params, instrument)
    if not same_trades(legs, archetype.legs(data, unsized(params), instrument)):
        msg: str = (
            f"{archetype.name}: the size moved a trade, so it cannot be shuffled across the trades taken"
        )
        raise RuntimeError(msg)

    table: IntArray = np.asarray(params.size_table, dtype=np.int64)  # type: ignore[attr-defined]  # every params class carries one
    trade_of_leg, leg, rows = trade_rows(legs, table)

    def at(trade_row: IntArray) -> trades.LegMatrix:
        return resized(
            legs,
            table[trade_row[trade_of_leg], leg],
            instrument.point_value,
            params.commission_per_contract,  # type: ignore[attr-defined]  # every params class carries one
        )

    if not np.array_equal(at(rows).matrix, legs.matrix[: legs.count], equal_nan=True):
        msg = f"{archetype.name}: recomputing the sizes taken did not reproduce the simulation"
        raise RuntimeError(msg)

    rng: np.random.Generator = np.random.default_rng(seed)
    null: FloatArray = np.array(
        [stats.summarise_legs(at(rng.permutation(rows)), data.day_codes).as_dict()[by] for _ in range(draws)],
    )

    return placed(stats.summarise_legs(legs, data.day_codes).as_dict(), by, null)


def shuffled_null(
    data: context.Dataset,
    params: Params,
    instrument: Instrument,
    *,
    by: str,
    draws: int,
    seed: int,
    archetype: archetypes.Archetype = archetypes.INSIDEBARTRAILING,
) -> dict[str, float]:
    """The configuration's own ``by`` against its sizes shuffled, re-simulated where a size moves trades."""
    if archetype.name != archetypes.INSIDEBARTRAILING.name:
        return recomputed_null(data, params, instrument, archetype, by=by, draws=draws, seed=seed)

    if not isinstance(params, InsideBarTrailingParams):  # pragma: no cover - by construction
        msg: str = f"rebuilt {type(params).__name__} for an InsideBarTrailing row"
        raise TypeError(msg)

    return resimulated_null(data, params, instrument, by=by, draws=draws, seed=seed)


def null_for_shortlist(
    rows: pd.DataFrame,
    root: str,
    *,
    by: str,
    draws: int,
    seed: int,
    archetype: archetypes.Archetype = archetypes.INSIDEBARTRAILING,
) -> pd.DataFrame:
    """Every shortlisted sizing arm's configuration against its shuffled sizes, held out."""
    stored: pd.DataFrame = stored_rows(archetype.name, root, HELD_OUT)
    candidates: tuple[pd.DataFrame, ...] = candidate_bars(stored, splice.load_continuous(root))
    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        frame, swept = bars_for(candidates, stored, block, int(minutes))
        for _, row in block.iterrows():
            params: Params = rebuild(row, archetype)
            data: context.Dataset = context.prepare(
                frame,
                sweep.Grid.of(params, archetype=archetype).required_context(),
                bar_minutes=int(minutes),
                price_basis=context.PriceBasis.RAW,
            )
            sweep_id, combo_id = log_key(row)
            result: dict[str, float] = shuffled_null(
                data,
                params,
                get_instrument(root),
                by=by,
                draws=draws,
                seed=seed + combo_id,
                archetype=archetype,
            )
            measured.append(
                {
                    "resolution": int(minutes),
                    "stratum": row.get("stratum"),
                    "sweep_id": sweep_id,
                    "combo_id": combo_id,
                    "order_quantity": params.order_quantity,  # type: ignore[attr-defined]  # every params class carries one
                    "labels": ",".join(sizing_labels(params)),  # type: ignore[arg-type]  # every params class is ConfluenceSized
                    "swept_bars": swept,
                    **result,
                },
            )

    return pd.DataFrame(measured)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="The confluence size's cuts, and its shuffled-size null.")
    commands = parser.add_subparsers(dest="command", required=True)
    fitting = commands.add_parser("fit", help="fit and write the cuts, on the selection window alone")
    fitting.add_argument("--strategy", choices=sorted(VARIANTS), default=archetypes.INSIDEBARTRAILING.name)
    fitting.add_argument("--roots", nargs="+", default=list(ROOTS))
    fitting.add_argument("--resolutions", nargs="+", type=int, default=list(RESOLUTIONS))
    nulling = commands.add_parser("null", help="a sizing arm's held-out shortlist against shuffled sizes")
    nulling.add_argument("--strategy", choices=sorted(VARIANTS), default=archetypes.INSIDEBARTRAILING.name)
    nulling.add_argument(
        "--variant",
        default=None,
        help="the stored sizing arm to read; InsideBarTrailing's defaults to §M45's confluence arm",
    )
    nulling.add_argument("--root", default="MNQ")
    nulling.add_argument("--by", default="profit_factor", help="the statistic that ranks and is tested")
    nulling.add_argument("--stratum", default=None)
    nulling.add_argument("--resolution", type=int, default=None)
    nulling.add_argument("--top", type=int, default=TOP)
    nulling.add_argument("--draws", type=int, default=DRAWS)
    nulling.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv[1:])

    if args.command == "fit":
        fit(args.strategy, args.roots, args.resolutions, sizing_cuts_path(args.strategy))

        return 0

    archetype: archetypes.Archetype = archetypes.get(args.strategy)
    variant: str | None = args.variant
    if variant is None and archetype is archetypes.INSIDEBARTRAILING:
        variant = CONFLUENCE_VARIANT

    if variant is None:
        msg: str = (
            f"--variant names the {archetype.name} sizing arm to read, such as '<variant> size=confluence'"
        )
        raise SystemExit(msg)

    rows: pd.DataFrame = held_out(
        archetype.name,
        args.root,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        variant,
    )
    if rows.empty:
        logger.warning("no stored %s rows; run the sizing variants first", variant)

        return 1

    table: pd.DataFrame = null_for_shortlist(
        rows,
        args.root,
        by=args.by,
        draws=args.draws,
        seed=args.seed,
        archetype=archetype,
    )
    with pd.option_context("display.width", 240, "display.max_columns", 40):
        logger.info("%s", table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    logger.info("%d of %d at p <= 0.05", int((table["p"] <= 0.05).sum()), len(table))  # noqa: PLR2004 - the house significance level

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
