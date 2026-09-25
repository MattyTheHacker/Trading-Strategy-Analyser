"""Fit the cuts InsideBarTrailing's sizing arms run at, and read the confluence size against a null.

    ./.venv/Scripts/python.exe tools/campaign_sizing.py fit
    ./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies InsideBarTrailing \
        --variants ibt-sizing --split --strata ibt-sizing --resolutions 5 --n-jobs 12
    ./.venv/Scripts/python.exe tools/campaign_sizing.py null --root MNQ --resolution 5 \
        --stratum phase=MIDDAY

**Everything ``fit`` measures comes from the selection window**, so the held-out window reads
cuts it had no part in -- the rule ``tools/campaign_sweep.py``'s regime fit states. Each cut is
taken at the stored campaign's base configuration over its unfiltered signal, and written before
any sizing arm runs: the file is the pre-registration of every threshold the arms read --
``docs/findings/m45-ibt-sizing-preregistration.md``.

**The shuffled-size null is the control a confluence size needs**, and a matched random entry is
not it: the entries are the rule's own and only which size each signal took is permuted, so what
it measures is whether the count put the larger sizes on the better trades.
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
    SIZING_CUTS,
    SizingCut,
    insidebartrailing_variants,
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
from nqbt.sim import filters, insidebar, insidebartrailing
from nqbt.sim.types import EARLINESS_MODES, EARLINESS_OFF, SIZING_LABELS, InsideBarTrailingParams

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray
    from nqbt.instruments import Instrument

logger = logging.getLogger(__name__)

LABEL_QUANTILES = (0.20, 0.80)
"""Where the regime and volume labels are cut: directional and heavy are each the top fifth.

The campaign's own regime pair and one of its volume tails, so a sizing label and a stratum
mean the same thing -- ``docs/roadmap.md`` §M27.5 and §M27.8."""

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
"""The stored variant name of the confluence arm, which the null reads."""


def probe_params(base: InsideBarTrailingParams) -> InsideBarTrailingParams:
    """``base`` with every label switched on, so one prepared dataset holds all five."""
    return dataclasses.replace(base, quantity_per_confluence=1, **dict.fromkeys(SIZING_LABELS, True))


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


def fit_cut(
    frame: pd.DataFrame,
    root: str,
    minutes: int,
    base: InsideBarTrailingParams,
) -> tuple[SizingCut, dict[str, dict[str, float]]]:
    """One root and resolution's cut, with what it was read off.

    The report holds each label's favourable share at the fitted signals and, per earliness rule,
    the share of the base configuration's own trades that came out early under the fitted cut.
    """
    probe: InsideBarTrailingParams = probe_params(base)
    data: context.Dataset = context.prepare(
        frame,
        sweep.Grid.of(probe).required_context(),
        bar_minutes=minutes,
        price_basis=context.PriceBasis.RAW,
    )
    consolidating, directional = regime.thresholds_from_quantiles(
        data.regime_values(probe.regime_lookback),
        *LABEL_QUANTILES,
    )
    thin, heavy = volume.thresholds_from_quantiles(data.relative_volume(probe.volume_key), *LABEL_QUANTILES)
    labelled: InsideBarTrailingParams = dataclasses.replace(
        probe,
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
    )

    signal: BoolArray = insidebar.insidebar_signal(data, base)
    if not signal.any():
        msg: str = f"{root} {minutes}m: no signal in the selection window to fit a cut at"
        raise SystemExit(msg)

    direction_at: FloatArray = insidebar.insidebar_direction(data, base)
    extension: FloatArray = extension_at(data, base)[signal]
    rows: list[BoolArray] = filters.favourable_labels(data, labelled, direction_at == trades.LONG)
    shares: dict[str, float] = {
        label: float(row[signal].mean()) for label, row in zip(SIZING_LABELS, rows, strict=True)
    }
    cut: SizingCut = SizingCut(
        root=root,
        minutes=minutes,
        early_max_extension_atr=float(np.quantile(extension[np.isfinite(extension)], EARLY_QUANTILE)),
        early_max_trend_bars=int(np.quantile(age_at(data, base, direction_at)[signal], EARLY_QUANTILE)),
        regime_consolidating_below=consolidating,
        regime_directional_above=directional,
        volume_thin_below=thin,
        volume_heavy_above=heavy,
        labels=kept_labels(shares),
    )
    report: dict[str, dict[str, float]] = {
        "favourable_share": shares,
        "traded_early_share": traded_early_shares(data, cut, base, get_instrument(root)),
    }

    return cut, report


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


def fit(roots: list[str], resolutions: list[int], path: Path) -> list[dict[str, object]]:
    """Fit and write every root and resolution's cut, returning what was written."""
    written: list[dict[str, object]] = []
    for root in roots:
        (campaign,) = insidebartrailing_variants(root)
        if not isinstance(campaign.base, InsideBarTrailingParams):  # pragma: no cover - by construction
            msg: str = f"the stored InsideBarTrailing variant carries {type(campaign.base).__name__}"
            raise TypeError(msg)

        selection: pd.DataFrame = selection_window(splice.load_continuous(root))
        for minutes in resolutions:
            cut, report = fit_cut(resample.resample(selection, minutes), root, minutes, campaign.base)
            written.append({**dataclasses.asdict(cut), **report})
            logger.info(
                "  %-4s %2dm  trend age <= %d bars  extension <= %.3f ATR  labels %s",
                root,
                minutes,
                cut.early_max_trend_bars,
                cut.early_max_extension_atr,
                ", ".join(cut.labels) or "none",
            )
            for label, share in report["favourable_share"].items():
                logger.info("        %-26s favours %5.1f%% of signals", label, 100.0 * share)
            for rule, share in report["traded_early_share"].items():
                logger.info("        %-26s %5.1f%% of traded entries early", rule, 100.0 * share)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(written, indent=2), encoding="utf-8")
    logger.info("wrote %d cuts to %s", len(written), path)

    return written


def permuted_sizing(
    sizing: insidebartrailing.LotSizing,
    signal: BoolArray,
    rng: np.random.Generator,
) -> insidebartrailing.LotSizing:
    """``sizing`` with the rows its signal bars take shuffled among them, and every other bar kept."""
    rows: IntArray = sizing.row_at.copy()
    rows[signal] = rng.permutation(rows[signal])

    return insidebartrailing.LotSizing(sizing.quantities, rows)


def shuffled_null(
    data: context.Dataset,
    params: InsideBarTrailingParams,
    instrument: Instrument,
    *,
    by: str,
    draws: int,
    seed: int,
) -> dict[str, float]:
    """The configuration's own ``by`` against the same sizes shuffled across its signals.

    ``p`` is the share of shuffles at least as good, counting the observation itself, so it is
    never zero -- the convention ``nqbt/randomentry.py`` reports its matched null in.
    """
    direction_at: FloatArray = insidebar.insidebar_direction(data, params)
    signal: BoolArray = insidebar.insidebar_signal(data, params)
    sizing: insidebartrailing.LotSizing = insidebartrailing.lot_sizing(data, params, direction_at)

    def measured(lots: insidebartrailing.LotSizing) -> float:
        legs = insidebartrailing.insidebartrailing_legs(data, params, instrument, sizing=lots)

        return float(stats.summarise_legs(legs, data.day_codes).as_dict()[by])

    observed: float = measured(sizing)
    rng: np.random.Generator = np.random.default_rng(seed)
    null: FloatArray = np.array([measured(permuted_sizing(sizing, signal, rng)) for _ in range(draws)])
    at_least: int = int(np.sum(null >= observed))

    return {
        "observed": observed,
        "null_median": float(np.median(null)),
        "excess": observed - float(np.median(null)),
        "p": (1 + at_least) / (1 + draws),
    }


def null_for_shortlist(
    rows: pd.DataFrame,
    root: str,
    *,
    by: str,
    draws: int,
    seed: int,
) -> pd.DataFrame:
    """Every shortlisted confluence-sized configuration against its shuffled sizes, held out."""
    archetype: archetypes.Archetype = archetypes.INSIDEBARTRAILING
    stored: pd.DataFrame = stored_rows(archetype.name, root, HELD_OUT)
    candidates: tuple[pd.DataFrame, ...] = candidate_bars(stored, splice.load_continuous(root))
    measured: list[dict[str, object]] = []
    for minutes, block in rows.groupby("resolution", sort=False):
        frame, swept = bars_for(candidates, stored, block, int(minutes))
        for _, row in block.iterrows():
            params = rebuild(row, archetype)
            if not isinstance(params, InsideBarTrailingParams):  # pragma: no cover - by construction
                msg: str = f"rebuilt {type(params).__name__} for an InsideBarTrailing row"
                raise TypeError(msg)

            data: context.Dataset = context.prepare(
                frame,
                sweep.Grid.of(params).required_context(),
                bar_minutes=int(minutes),
                price_basis=context.PriceBasis.RAW,
            )
            sweep_id, combo_id = log_key(row)
            result: dict[str, float] = shuffled_null(
                data, params, get_instrument(root), by=by, draws=draws, seed=seed + combo_id
            )
            measured.append(
                {
                    "resolution": int(minutes),
                    "stratum": row.get("stratum"),
                    "sweep_id": sweep_id,
                    "combo_id": combo_id,
                    "order_quantity": params.order_quantity,
                    "labels": ",".join(params.sizing_labels),
                    "swept_bars": swept,
                    **result,
                },
            )

    return pd.DataFrame(measured)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(description="InsideBarTrailing's sizing cuts, and its confluence null.")
    commands = parser.add_subparsers(dest="command", required=True)
    fitting = commands.add_parser("fit", help="fit and write the cuts, on the selection window alone")
    fitting.add_argument("--roots", nargs="+", default=list(ROOTS))
    fitting.add_argument("--resolutions", nargs="+", type=int, default=list(RESOLUTIONS))
    nulling = commands.add_parser(
        "null", help="the confluence arm's held-out shortlist against shuffled sizes"
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
        fit(args.roots, args.resolutions, SIZING_CUTS)

        return 0

    rows: pd.DataFrame = held_out(
        archetypes.INSIDEBARTRAILING.name,
        args.root,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        CONFLUENCE_VARIANT,
    )
    if rows.empty:
        logger.warning("no stored %s rows; run the ibt-sizing variants first", CONFLUENCE_VARIANT)

        return 1

    table: pd.DataFrame = null_for_shortlist(rows, args.root, by=args.by, draws=args.draws, seed=args.seed)
    with pd.option_context("display.width", 240, "display.max_columns", 40):
        logger.info("%s", table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    logger.info("%d of %d at p <= 0.05", int((table["p"] <= 0.05).sum()), len(table))  # noqa: PLR2004 - the house significance level

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
