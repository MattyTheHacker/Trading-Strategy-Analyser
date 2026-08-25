"""Command line entry points."""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from nqbt import ingest, logsetup, paths, splice

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

    from nqbt.archive import MergeResult
    from nqbt.context import Dataset
    from nqbt.ingest import ContractManifest
    from nqbt.instruments import Instrument

logger = logging.getLogger(__name__)


def _cmd_ingest(args: argparse.Namespace) -> int:
    merges, results = ingest.ingest_all(
        data_dir=args.data_dir,
        cache_dir=args.cache_dir,
        root=args.root,
        force=args.force,
    )
    if merges:
        changed: list[MergeResult] = [m for m in merges if m.added or m.revised]
        logger.info(
            "archive: %d contracts, %s bars (%d changed by this merge)",
            len(merges),
            f"{sum(m.bars for m in merges):,}",
            len(changed),
        )
        for merge in changed:
            logger.info("  %s", merge)
        logger.info("")

    total: int = 0
    for result in results:
        logger.info("%s", result)
        for warning in result.warnings:
            logger.info("    [!] %s", warning)
        total += result.rows_total
    logger.info("")
    logger.info("%d contracts, %s bars cached in %s", len(results), f"{total:,}", args.cache_dir)
    return 0


def _cmd_contracts(args: argparse.Namespace) -> int:
    manifest: dict[str, ContractManifest] = ingest.load_manifest(args.cache_dir / "manifest.json")
    if not manifest:
        logger.info("nothing ingested yet; run `nqbt ingest`")
        return 1
    logger.info("%-12s %9s  last bar (UTC)", "contract", "rows")
    for key, entry in sorted(manifest.items()):
        logger.info("%-12s %9s  %s", key, f"{entry.rows:,}", entry.last_timestamp)
    return 0


def _cmd_splice(args: argparse.Namespace) -> int:
    series, report = splice.splice_root(
        args.root,
        data_dir=args.data_dir or paths.ARCHIVE_DIR,
        cache_dir=args.cache_dir,
        back_adjust=args.back_adjust,
        confirm_sessions=args.confirm_sessions,
        allow_coverage_boundary=not args.strict,
    )
    logger.info("%s", report.summary())
    logger.info("")
    logger.info("%s bars  %s -> %s", f"{len(series):,}", series.index[0], series.index[-1])
    path: Path = splice.continuous_path(args.root, back_adjust=args.back_adjust, cache_dir=args.cache_dir)
    logger.info("written to %s", path)

    if args.diagnostics:
        for roll in report.rolls:
            logger.info("")
            logger.info("--- %s -> %s ---", roll.front.nt8_name, roll.back.nt8_name)
            logger.info("%s", roll.diagnostics.to_string())
            for note in roll.notes:
                logger.info("  note: %s", note)

    # Rolling at the coverage boundary is normal for NT8 data, so only a handover that
    # looks premature is worth a non-zero exit.
    return 2 if report.early_rolls else 0


def _cmd_run(args: argparse.Namespace) -> int:
    from nqbt import context
    from nqbt.instruments import get_instrument
    from nqbt.sim import explain as explain_mod
    from nqbt.sim import runner
    from nqbt.sim.types import DeadCatParams

    params: DeadCatParams = DeadCatParams(
        ema_period=args.ema,
        slow_sma_period=args.slow_sma,
        fast_sma_period=args.fast_sma,
        order_quantity=args.quantity,
        commission_per_contract=args.commission,
        slippage_ticks=args.slippage,
    )
    instrument: Instrument = get_instrument(args.root)
    bars: pd.DataFrame = splice.load_continuous(
        args.root,
        back_adjust=args.back_adjust,
        cache_dir=args.cache_dir,
    )
    if args.start:
        bars = bars[bars.index >= args.start]
    if args.end:
        bars = bars[bars.index <= args.end]

    # VWAP unconditionally: --explain reports every gate whether or not this
    # combination reads it, and the audit trail is the point of the command.
    data: Dataset = context.prepare(
        bars,
        context.ContextSpec(
            ema_periods=(params.ema_period,),
            sma_periods=(params.fast_sma_period, params.slow_sma_period),
            needs_vwap=True,
        ),
        keep_ma_values=bool(args.explain),
    )
    trades: pd.DataFrame = runner.run_deadcat(data, params, instrument)

    if trades.empty:
        logger.info("no trades")
        return 0

    per_trade: pd.Series[float] = trades.groupby("trade_id")["net_pnl"].sum()
    wins: pd.Series[bool] = per_trade > 0
    losses: float = -per_trade[~wins].sum()
    pf: float = per_trade[wins].sum() / losses if losses > 0 else float("inf")
    equity: pd.Series[float] = per_trade.cumsum()
    max_dd: float = float((equity.cummax() - equity).max())

    logger.info(
        "%s %s -> %s  %s bars",
        args.root,
        bars.index[0].date(),
        bars.index[-1].date(),
        f"{len(bars):,}",
    )
    logger.info(
        "  params        EMA %d, SMA %d/%d, qty %d %s",
        params.ema_period,
        params.fast_sma_period,
        params.slow_sma_period,
        params.order_quantity,
        params.leg_quantities,
    )
    logger.info(
        "  costs         $%.2f/contract RT, %g ticks slippage",
        params.commission_per_contract,
        params.slippage_ticks,
    )
    logger.info("  trades        %s  (%s leg exits)", f"{len(per_trade):,}", f"{len(trades):,}")
    logger.info("  win rate      %s", f"{wins.mean():.2%}")
    logger.info("  net P&L       %s", f"${per_trade.sum():,.2f}")
    logger.info("  expectancy    %s / trade", f"${per_trade.mean():.2f}")
    logger.info("  profit factor %.3f", pf)
    logger.info("  max drawdown  %s", f"${max_dd:,.2f}")
    logger.info("  mean R        %s", f"{trades['r_multiple'].mean():+.3f}")
    logger.info(
        "  ambiguous     %s of leg exits (bar held both stop and target; stop assumed)",
        f"{trades['ambiguous_bar'].mean():.2%}",
    )
    logger.info(
        "  exit reasons  %s",
        ", ".join(f"{k} {v:,}" for k, v in trades["exit_reason"].value_counts().items()),
    )

    if args.trades:
        trades.to_csv(args.trades, index=False)
        logger.info("")
        logger.info("trade log -> %s", args.trades)

    if args.explain:
        detail: pd.DataFrame = explain_mod.explain_trades(data, params, trades, instrument, args.explain)
        detail.to_csv(args.explain_out, index=False)
        logger.info("hand-check detail for %d trades -> %s", len(detail), args.explain_out)
        first: int = int(trades["trade_id"].iloc[0])
        hist: pd.DataFrame = explain_mod.ratchet_history(data, params, trades, first, instrument)
        hist.to_csv(args.ratchet_out, index=False)
        logger.info("ratchet history for trade %d -> %s", first, args.ratchet_out)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """The parser for every ``nqbt`` subcommand."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="nqbt", description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=paths.Path,
        default=None,
        help="ingest one folder directly instead of refreshing and reading the archive; "
        "for inspecting a single export, not the normal path",
    )
    parser.add_argument("--cache-dir", type=paths.Path, default=paths.CACHE_DIR)
    sub: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command", required=True
    )

    p_ingest: argparse.ArgumentParser = sub.add_parser(
        "ingest", help="parse NT8 exports into the Parquet cache"
    )
    p_ingest.add_argument("--root", help="limit to one instrument root, e.g. MNQ")
    p_ingest.add_argument(
        "--force",
        action="store_true",
        help="reparse in full, ignoring the manifest",
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    p_list: argparse.ArgumentParser = sub.add_parser("contracts", help="show what is currently cached")
    p_list.set_defaults(func=_cmd_contracts)

    p_splice: argparse.ArgumentParser = sub.add_parser(
        "splice", help="build the continuous series for a root"
    )
    p_splice.add_argument("--root", default="MNQ")
    p_splice.add_argument(
        "--back-adjust",
        action="store_true",
        help="shift history to line up with the current contract (NT8 MergeBackAdjusted)",
    )
    p_splice.add_argument(
        "--confirm-sessions",
        type=int,
        default=1,
        help="sessions the back contract must lead before the roll is accepted",
    )
    p_splice.add_argument(
        "--strict",
        action="store_true",
        help="require an observed volume crossover; fail rather than roll at the "
        "coverage boundary (NT8 data will not satisfy this)",
    )
    p_splice.add_argument(
        "--diagnostics",
        action="store_true",
        help="print the per-roll volume tables",
    )
    p_splice.set_defaults(func=_cmd_splice)

    p_run: argparse.ArgumentParser = sub.add_parser(
        "run",
        help="simulate one DeadCatBounce parameter set over the continuous series",
    )
    p_run.add_argument("--root", default="MNQ")
    p_run.add_argument("--back-adjust", action="store_true")
    p_run.add_argument("--ema", type=int, default=21)
    p_run.add_argument("--slow-sma", type=int, default=175)
    p_run.add_argument("--fast-sma", type=int, default=60)
    p_run.add_argument("--quantity", type=int, default=4)
    p_run.add_argument(
        "--commission",
        type=float,
        default=0.0,
        help="round-turn dollars per contract",
    )
    p_run.add_argument("--slippage", type=float, default=0.0, help="ticks, adverse")
    p_run.add_argument("--start", help="ISO date; restrict the window, e.g. 2024-01-01")
    p_run.add_argument("--end", help="ISO date")
    p_run.add_argument("--trades", help="write the full leg-level trade log to this CSV")
    p_run.add_argument(
        "--explain",
        type=int,
        metavar="N",
        help="write a hand-checkable audit trail for the first N trades",
    )
    p_run.add_argument("--explain-out", default="explain.csv")
    p_run.add_argument("--ratchet-out", default="ratchet.csv")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one ``nqbt`` command line and return its process exit code."""
    logsetup.configure(__name__)
    args: argparse.Namespace = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ingest.IngestError, splice.SpliceError, FileNotFoundError) as exc:
        logger.error("%s", exc)  # noqa: TRY400 - an expected failure, not an unhandled one
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
