r"""Fit the cuts a confluence size runs at, and read it against its own sizes shuffled.

    uv run tools/campaign_sizing.py fit --strategy ElasticBand \
        --resolutions 2 5 10 15
    uv run tools/campaign_sweep.py --strategies ElasticBand \
        --variants confluence-sizing --split --strata confluence-sizing --resolutions 2 5 10 15
    uv run tools/campaign_sizing.py null --strategy ElasticBand --root MNQ \
        --resolution 5 --variant "target=0.0s size=confluence"

InsideBarTrailing is the default strategy, and there the null reads §M45's confluence arm unless
``--variant`` names another -- ``docs/findings/m45-ibt-sizing-preregistration.md``.

``fit`` reads the selection window alone -- ``tools/README.md`` § "campaign_sizing.py".
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

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
from nqbt.sim import bracket, filters, insidebar, insidebartrailing
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
    sizing_cuts,
    sizing_cuts_path,
)
from tools.campaign_swept import HELD_OUT, bars_for, candidate_bars

if TYPE_CHECKING:
    from nqbt.archetypes import ArchetypeParams
    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.instruments import Instrument

logger = logging.getLogger(__name__)

EARLY_QUANTILE = 0.5
"""Where the extension and trend-age cuts sit among the fitted signals: half early, half not."""

MIN_FAVOURABLE_SHARE = 0.10
MAX_FAVOURABLE_SHARE = 0.90
"""A label favouring fewer or more of the fitted signals than this is dropped from the count."""

MAX_STEP_SHARE = MAX_FAVOURABLE_SHARE
"""A label is dropped from the symmetric count where one step it moves that count by -- up, down or
none -- covers more of the fitted signals than this -- ``tools/README.md`` § "campaign_sizing.py"."""

DRAWS = 200
"""Shuffles per configuration: enough for a p-value of 0.005 to be reachable."""

CONFLUENCE_VARIANT = f"trailing {SIZING_CONFLUENCE}"
"""The stored variant name of §M45's confluence arm, which InsideBarTrailing's null reads."""

SIZED_COLUMNS = (C_QUANTITY, C_GROSS_PNL, C_COMMISSION, C_NET_PNL)
"""The four leg columns a size writes. Every other one is the trade itself."""


def probe_params(base: ArchetypeParams) -> ArchetypeParams:
    """Return ``base`` with every label switched on, so one prepared dataset holds all five."""
    return dataclasses.replace(
        base,
        quantity_per_confluence=1,
        size_symmetric=False,
        **dict.fromkeys(SIZING_LABELS, True),
    )


def age_at(data: context.Dataset, params: InsideBarTrailingParams, direction_at: FloatArray) -> IntArray:
    """Count how many bars the trend on each bar's side has run, the bar included."""
    up, down = insidebar.insidebar_trends(data, params)
    long_side: BoolArray = direction_at == trades.LONG

    return np.where(long_side, conditions.consecutive_true(up), conditions.consecutive_true(down))


def extension_at(data: context.Dataset, params: InsideBarTrailingParams) -> FloatArray:
    """Measure how far each close sits from the slow SMA, in ATRs."""
    slow: FloatArray = data.ma_values(params.slow_sma_kind, params.slow_sma_period)
    with np.errstate(divide="ignore", invalid="ignore"):
        extension: FloatArray = np.abs(data.close - slow) / data.atr_values(params.atr_length)

    return extension


def label_shares(
    data: context.Dataset, labelled: ArchetypeParams, campaign: Variant
) -> dict[str, dict[str, float]]:
    """Return, per label, the share of the unfiltered signals it favours, opposes alone, and leaves at none.

    Pooled over the sides the variant sweeps. A label that both favours and opposes, as the VWAP
    does at a tie, counts as none -- ``tools/README.md`` § "campaign_sizing.py".
    """
    archetype: archetypes.Archetype = campaign.archetype
    sides: list[object] = list(campaign.axes.get("direction", []))
    configurations: list[ArchetypeParams] = (
        [dataclasses.replace(labelled, direction=side) for side in sides] if sides else [labelled]
    )
    favours: list[list[BoolArray]] = [[] for _ in SIZING_LABELS]
    opposes: list[list[BoolArray]] = [[] for _ in SIZING_LABELS]
    for params in configurations:
        signal: BoolArray = archetype.signal(data, params)
        for position, label in enumerate(
            filters.label_sides(data, params, archetype.long_side(data, params))
        ):
            favours[position].append(label.favours[signal])
            opposes[position].append(label.opposes[signal])

    if not sum(int(rows.size) for rows in favours[0]):
        msg: str = f"{archetype.name} {campaign.name}: no signal in the selection window to fit a cut at"
        raise SystemExit(msg)

    pooled: dict[str, filters.LabelSides] = {
        label: filters.LabelSides(np.concatenate(up), np.concatenate(down))
        for label, up, down in zip(SIZING_LABELS, favours, opposes, strict=True)
    }

    return {
        "favourable_share": {label: float(at.favours.mean()) for label, at in pooled.items()},
        "opposing_share": {label: float((at.opposes & ~at.favours).mean()) for label, at in pooled.items()},
        "neutral_share": {label: float((at.favours == at.opposes).mean()) for label, at in pooled.items()},
    }


def probed(frame: pd.DataFrame, minutes: int, campaign: Variant) -> context.Dataset:
    """Prepare ``frame`` with everything :func:`probe_params` reads on ``campaign``'s base."""
    return context.prepare(
        frame,
        sweep.Grid.of(probe_params(campaign.base), archetype=campaign.archetype).required_context(),
        bar_minutes=minutes,
        price_basis=context.PriceBasis.RAW,
    )


def fit_cut(
    frame: pd.DataFrame,
    root: str,
    minutes: int,
    campaign: Variant,
    *,
    variant: str | None = None,
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """Fit one root, resolution and variant's cut, with what it was read off.

    The report holds each label's shares at the fitted signals, :func:`label_shares`, and, on
    InsideBarTrailing, per earliness rule the share of the base configuration's own trades that
    came out early under the fitted cut.
    """
    probe: ArchetypeParams = probe_params(campaign.base)
    data: context.Dataset = probed(frame, minutes, campaign)
    consolidating, directional = regime.thresholds_from_quantiles(
        data.regime_values(probe.regime_lookback),
        *SIZING_LABEL_QUANTILES,
    )
    thin, heavy = volume.thresholds_from_quantiles(
        data.relative_volume(probe.volume_key),
        *SIZING_LABEL_QUANTILES,
    )
    labelled: ArchetypeParams = dataclasses.replace(
        probe,
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
    )
    report: dict[str, dict[str, float]] = label_shares(data, labelled, campaign)
    cut: SizingCut = SizingCut(
        root=root,
        minutes=minutes,
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
        labels=kept_labels(report["favourable_share"]),
        symmetric_labels=symmetric_kept_labels(report),
        variant=variant,
    )
    if campaign.archetype.name != archetypes.INSIDEBARTRAILING.name:
        return cut, report

    return earliness_cut(data, cut, campaign.base, report, get_instrument(root))


def earliness_cut(
    data: context.Dataset,
    cut: SizingCut,
    base: ArchetypeParams,
    report: dict[str, dict[str, float]],
    instrument: Instrument,
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """Return InsideBarTrailing's cut with its earliness cuts fitted in, at the median of its signals."""
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
    """Return, per earliness rule, the share of the base configuration's trades whose signal bar was early.

    Counted over the trades taken rather than the signals.
    """
    direction_at: FloatArray = insidebar.insidebar_direction(data, base)
    shares: dict[str, float] = {}
    for mode, name in EARLINESS_MODES.items():
        if mode == EARLINESS_OFF:
            continue

        tiered: InsideBarTrailingParams = dataclasses.replace(
            base,
            earliness_mode=mode,
            early_max_extension_atr=cut.early_max_extension_atr,  # type: ignore[arg-type]  # set by earliness_cut
            early_max_trend_bars=cut.early_max_trend_bars,  # type: ignore[arg-type]  # set by earliness_cut
        )
        log: pd.DataFrame = insidebartrailing.run_insidebartrailing(
            data, tiered, instrument, with_times=False
        )
        signal_bars: IntArray = log.groupby("trade_id")["entry_bar"].first().to_numpy() - 1
        early: BoolArray = insidebartrailing.early_entries(data, tiered, direction_at)
        shares[name] = float(early[signal_bars].mean()) if signal_bars.size else float("nan")

    return shares


def kept_labels(shares: dict[str, float]) -> tuple[str, ...]:
    """Return the labels whose favourable share at the fitted signals leaves them something to sort."""
    return tuple(
        label for label, share in shares.items() if MIN_FAVOURABLE_SHARE <= share <= MAX_FAVOURABLE_SHARE
    )


def symmetric_kept_labels(report: dict[str, dict[str, float]]) -> tuple[str, ...]:
    """Return the labels the symmetric count keeps: those no one step covers almost every signal at."""
    opposing: dict[str, float] = report["opposing_share"]
    neutral: dict[str, float] = report["neutral_share"]

    return tuple(
        label
        for label in SIZING_LABELS
        if max(1.0 - opposing[label] - neutral[label], opposing[label], neutral[label]) <= MAX_STEP_SHARE
    )


def symmetric_fill(
    frame: pd.DataFrame,
    campaign: Variant,
    cut: SizingCut,
    stored: dict[str, object],
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """Return a cut stored before the fit read its symmetric labels, with them read at its thresholds.

    Nothing it already holds is refitted. Its favourable shares are read again first and have to
    come back exactly as stored, which is what shows the signals are the ones it was fitted at.
    """
    labelled: ArchetypeParams = dataclasses.replace(probe_params(campaign.base), **cut.thresholds())
    report: dict[str, dict[str, float]] = label_shares(
        probed(frame, cut.minutes, campaign), labelled, campaign
    )
    if report["favourable_share"] != stored.get("favourable_share"):
        msg: str = (
            f"{campaign.archetype.name} {campaign.name} {cut.root} {cut.minutes}m: the favourable "
            "shares read back differently from the stored cut's, so its signals have moved; "
            "move the file aside to refit"
        )
        raise SystemExit(msg)

    return dataclasses.replace(cut, symmetric_labels=symmetric_kept_labels(report)), report


def selection_window(bars: pd.DataFrame) -> pd.DataFrame:
    """Return the bars the campaign's selection window holds, which is all a fit may read."""
    return bars.iloc[: math.floor(len(bars) * SELECTION_SHARE)]


def fit(name: str, roots: list[str], resolutions: list[int], path: Path) -> list[dict[str, object]]:
    """Fit every root, resolution and stored variant ``path`` does not hold yet, and write them all.

    A cut already there is kept, and one stored without symmetric labels gains them,
    :func:`symmetric_fill`; move the file aside to refit from scratch. The variant is recorded only
    where the archetype has more than one.
    """
    written: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    stored: dict[tuple[str, int, str | None], tuple[SizingCut, dict[str, object]]] = {
        (cut.root, cut.minutes, cut.variant): (cut, row)
        for cut, row in zip(sizing_cuts(path) if written else [], written, strict=True)
    }
    for root in roots:
        campaigns: list[Variant] = VARIANTS[name](root)
        selection: pd.DataFrame = selection_window(splice.load_continuous(root))
        for minutes in resolutions:
            frame: pd.DataFrame = resample.resample(selection, minutes)
            for campaign in campaigns:
                variant: str | None = campaign.name if len(campaigns) > 1 else None
                if not campaign.runs_at(minutes):
                    continue

                if (root, minutes, variant) not in stored:
                    cut, report = fit_cut(frame, root, minutes, campaign, variant=variant)
                    written.append({**dataclasses.asdict(cut), **report})
                    stored[(root, minutes, variant)] = (cut, written[-1])
                    log_cut(cut, report)
                    continue

                kept, row = stored[(root, minutes, variant)]
                if kept.symmetric_labels is not None:
                    continue

                cut, report = symmetric_fill(frame, campaign, kept, row)
                row.update(
                    symmetric_labels=list(cut.symmetric_labels or ()),
                    opposing_share=report["opposing_share"],
                    neutral_share=report["neutral_share"],
                )
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
    logger.info("%52ssymmetric labels %s", "", ", ".join(cut.symmetric_labels or ()) or "none")
    for label, share in report["favourable_share"].items():
        logger.info(
            "        %-26s favours %5.1f%%, opposes %5.1f%% of signals",
            label,
            100.0 * share,
            100.0 * report["opposing_share"][label],
        )
    for rule, share in report.get("traded_early_share", {}).items():
        logger.info("        %-26s %5.1f%% of traded entries early", rule, 100.0 * share)


def placed(observed: dict[str, float], by: str, null: FloatArray) -> dict[str, float]:
    """Return the observation against its null, with the trade count and shares a reading needs.

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
    """Shuffle the rows ``sizing``'s signal bars take among them, keeping every other bar."""
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
    """Compare InsideBarTrailing's ``by`` against its sizes shuffled across its signals, each re-run."""
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


def unsized(params: ArchetypeParams) -> ArchetypeParams:
    """Return ``params`` at its fixed size, with the confluence size switched off."""
    return dataclasses.replace(
        params,
        quantity_per_confluence=0,
        size_symmetric=False,
        **dict.fromkeys(SIZING_LABELS, False),
    )


def same_trades(sized: trades.LegMatrix, fixed: trades.LegMatrix) -> bool:
    """Return whether two runs took the same trades leg for leg, whatever size each took them at."""
    if sized.count != fixed.count:
        return False

    kept: list[int] = [column for column in range(N_COLUMNS) if column not in SIZED_COLUMNS]

    return bool(
        np.array_equal(sized.matrix[: sized.count, kept], fixed.matrix[: fixed.count, kept], equal_nan=True),
    )


def trade_rows(legs: trades.LegMatrix, table: IntArray) -> tuple[IntArray, IntArray, IntArray]:
    """Return each leg's trade, each leg's place in its trade, and the table row each trade was sized at."""
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
    """Return ``legs`` at other sizes, their money recomputed exactly as ``bracket.write_leg`` writes it."""
    matrix: FloatArray = legs.matrix[: legs.count].copy()
    per_unit: FloatArray = (matrix[:, C_EXIT_PRICE] - matrix[:, C_ENTRY_PRICE]) * matrix[:, C_DIRECTION]
    gross: FloatArray = per_unit * quantities * point_value
    fees: FloatArray = quantities.astype(np.float64) * commission
    matrix[:, C_QUANTITY] = quantities
    matrix[:, C_GROSS_PNL] = gross
    matrix[:, C_COMMISSION] = fees
    matrix[:, C_NET_PNL] = gross - fees

    return trades.LegMatrix(matrix, legs.count)


def recomputed_null(
    data: context.Dataset,
    params: ArchetypeParams,
    instrument: Instrument,
    archetype: archetypes.Archetype,
    *,
    by: str,
    draws: int,
    seed: int,
) -> dict[str, float]:
    """Compare the configuration's own ``by`` against its sizes shuffled across the trades it took.

    Each shuffle's money is recomputed rather than re-simulated. Refuses a configuration whose fixed
    size takes other trades, or whose sizes, recomputed, do not reproduce the simulation to the bit
    -- ``tools/README.md`` § "campaign_sizing.py".
    """
    legs: trades.LegMatrix = archetype.legs(data, params, instrument)
    if not same_trades(legs, archetype.legs(data, unsized(params), instrument)):
        msg: str = (
            f"{archetype.name}: the size moved a trade, so it cannot be shuffled across the trades taken"
        )
        raise RuntimeError(msg)

    table: IntArray = np.asarray(params.size_table, dtype=np.int64)
    trade_of_leg, leg, rows = trade_rows(legs, table)

    def at(trade_row: IntArray) -> trades.LegMatrix:
        return resized(
            legs,
            table[trade_row[trade_of_leg], leg],
            instrument.point_value,
            params.commission_per_contract,
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
    params: ArchetypeParams,
    instrument: Instrument,
    *,
    by: str,
    draws: int,
    seed: int,
    archetype: archetypes.Archetype = archetypes.INSIDEBARTRAILING,
) -> dict[str, float]:
    """Compare the configuration's ``by`` with its sizes shuffled, re-simulated where a size moves trades."""
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
    """Test every shortlisted sizing arm's configuration against its shuffled sizes, held out."""
    stored: pd.DataFrame = stored_rows(archetype.name, root, HELD_OUT)
    candidates: tuple[pd.DataFrame, ...] = candidate_bars(stored, splice.load_continuous(root))
    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        bar_minutes: int = int(minutes)  # type: ignore[arg-type]  # a groupby key on an int column
        frame, swept = bars_for(candidates, stored, block, bar_minutes)
        for _, row in block.iterrows():
            params: ArchetypeParams = rebuild(row, archetype)
            data: context.Dataset = context.prepare(
                frame,
                sweep.Grid.of(params, archetype=archetype).required_context(),
                bar_minutes=bar_minutes,
                price_basis=context.PriceBasis.RAW,
            )
            result: dict[str, float] = shuffled_null(
                data,
                params,
                get_instrument(root),
                by=by,
                draws=draws,
                seed=seed + log_key(row)[1],
                archetype=archetype,
            )
            measured.append(
                null_row(log_key(row), row.get("stratum"), params, bar_minutes, result, swept=swept)
            )

    return pd.DataFrame(measured)


def null_row(
    key: tuple[int, int],
    stratum: object,
    params: ArchetypeParams,
    minutes: int,
    result: dict[str, float],
    *,
    swept: bool,
) -> dict[str, object]:
    """Return one configuration's null, tagged with its stored row's ids and the size it was read at."""
    sweep_id, combo_id = key

    return {
        "resolution": minutes,
        "stratum": stratum,
        "sweep_id": sweep_id,
        "combo_id": combo_id,
        "order_quantity": params.order_quantity,
        "labels": ",".join(sizing_labels(params)),
        "swept_bars": swept,
        **result,
    }


def main(argv: list[str]) -> int:
    """Run one subcommand and return the process exit code."""
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
