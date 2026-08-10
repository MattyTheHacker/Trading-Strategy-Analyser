"""Command line entry points."""

from __future__ import annotations

import argparse
import sys

from nqbt import ingest, paths, splice


def _cmd_ingest(args: argparse.Namespace) -> int:
    merges, results = ingest.ingest_all(
        data_dir=args.data_dir, cache_dir=args.cache_dir, root=args.root, force=args.force
    )
    if merges:
        changed = [m for m in merges if m.added or m.revised]
        print(f"archive: {len(merges)} contracts, {sum(m.bars for m in merges):,} bars "
              f"({len(changed)} changed by this merge)")
        for merge in changed:
            print(f"  {merge}")
        print()

    total = 0
    for result in results:
        print(result)
        for warning in result.warnings:
            print(f"    [!] {warning}")
        total += result.rows_total
    print(f"\n{len(results)} contracts, {total:,} bars cached in {args.cache_dir}")
    return 0


def _cmd_contracts(args: argparse.Namespace) -> int:
    manifest = ingest.load_manifest(args.cache_dir / "manifest.json")
    if not manifest:
        print("nothing ingested yet; run `nqbt ingest`")
        return 1
    print(f"{'contract':<12} {'rows':>9}  last bar (UTC)")
    for key, entry in sorted(manifest.items()):
        print(f"{key:<12} {entry.rows:>9,}  {entry.last_timestamp}")
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
    print(report.summary())
    print(
        f"\n{len(series):,} bars  "
        f"{series.index[0]} -> {series.index[-1]}\n"
        f"written to {splice.continuous_path(args.root, args.back_adjust, args.cache_dir)}"
    )

    if args.diagnostics:
        for roll in report.rolls:
            print(f"\n--- {roll.front.nt8_name} -> {roll.back.nt8_name} ---")
            print(roll.diagnostics.to_string())
            for note in roll.notes:
                print(f"  note: {note}")

    # Rolling at the coverage boundary is normal for NT8 data, so only a handover that
    # looks premature is worth a non-zero exit.
    return 2 if report.early_rolls else 0


def _cmd_run(args: argparse.Namespace) -> int:
    import numpy as np

    from nqbt.instruments import get_instrument
    from nqbt.sim import explain as explain_mod
    from nqbt.sim import runner
    from nqbt.sim.types import DeadCatParams

    params = DeadCatParams(
        ema_period=args.ema,
        slow_sma_period=args.slow_sma,
        fast_sma_period=args.fast_sma,
        order_quantity=args.quantity,
        commission_per_contract=args.commission,
        slippage_ticks=args.slippage,
    )
    instrument = get_instrument(args.root)
    bars = splice.load_continuous(
        args.root, back_adjust=args.back_adjust, cache_dir=args.cache_dir
    )
    if args.start:
        bars = bars[bars.index >= args.start]
    if args.end:
        bars = bars[bars.index <= args.end]

    data = runner.prepare(
        bars,
        ema_periods=(params.ema_period,),
        sma_periods=(params.fast_sma_period, params.slow_sma_period),
        keep_ma_values=bool(args.explain),
    )
    trades = runner.run_deadcat(data, params, instrument)

    if trades.empty:
        print("no trades")
        return 0

    per_trade = trades.groupby("trade_id")["net_pnl"].sum()
    wins = per_trade > 0
    losses = -per_trade[~wins].sum()
    pf = per_trade[wins].sum() / losses if losses > 0 else float("inf")
    equity = per_trade.cumsum()
    max_dd = float((equity.cummax() - equity).max())

    print(f"{args.root} {bars.index[0].date()} -> {bars.index[-1].date()}  {len(bars):,} bars")
    print(f"  params        EMA {params.ema_period}, SMA {params.fast_sma_period}/"
          f"{params.slow_sma_period}, qty {params.order_quantity} "
          f"{params.leg_quantities}")
    print(f"  costs         ${params.commission_per_contract:.2f}/contract RT, "
          f"{params.slippage_ticks:g} ticks slippage")
    print(f"  trades        {len(per_trade):,}  ({len(trades):,} leg exits)")
    print(f"  win rate      {wins.mean():.2%}")
    print(f"  net P&L       ${per_trade.sum():,.2f}")
    print(f"  expectancy    ${per_trade.mean():.2f} / trade")
    print(f"  profit factor {pf:.3f}")
    print(f"  max drawdown  ${max_dd:,.2f}")
    print(f"  mean R        {trades['r_multiple'].mean():+.3f}")
    print(f"  ambiguous     {trades['ambiguous_bar'].mean():.2%} of leg exits "
          "(bar held both stop and target; stop assumed)")
    print("  exit reasons  " + ", ".join(
        f"{k} {v:,}" for k, v in trades["exit_reason"].value_counts().items()))

    if args.trades:
        trades.to_csv(args.trades, index=False)
        print(f"\ntrade log -> {args.trades}")

    if args.explain:
        detail = explain_mod.explain_trades(data, params, trades, instrument, args.explain)
        detail.to_csv(args.explain_out, index=False)
        print(f"hand-check detail for {len(detail)} trades -> {args.explain_out}")
        first = int(trades["trade_id"].iloc[0])
        hist = explain_mod.ratchet_history(data, params, trades, first, instrument)
        hist.to_csv(args.ratchet_out, index=False)
        print(f"ratchet history for trade {first} -> {args.ratchet_out}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nqbt", description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=lambda p: paths.Path(p),
        default=None,
        help="ingest one folder directly instead of refreshing and reading the archive; "
        "for inspecting a single export, not the normal path",
    )
    parser.add_argument("--cache-dir", type=lambda p: paths.Path(p), default=paths.CACHE_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="parse NT8 exports into the Parquet cache")
    p_ingest.add_argument("--root", help="limit to one instrument root, e.g. MNQ")
    p_ingest.add_argument(
        "--force", action="store_true", help="reparse in full, ignoring the manifest"
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    p_list = sub.add_parser("contracts", help="show what is currently cached")
    p_list.set_defaults(func=_cmd_contracts)

    p_splice = sub.add_parser("splice", help="build the continuous series for a root")
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
        "--diagnostics", action="store_true", help="print the per-roll volume tables"
    )
    p_splice.set_defaults(func=_cmd_splice)

    p_run = sub.add_parser(
        "run", help="simulate one DeadCatBounce parameter set over the continuous series"
    )
    p_run.add_argument("--root", default="MNQ")
    p_run.add_argument("--back-adjust", action="store_true")
    p_run.add_argument("--ema", type=int, default=21)
    p_run.add_argument("--slow-sma", type=int, default=175)
    p_run.add_argument("--fast-sma", type=int, default=60)
    p_run.add_argument("--quantity", type=int, default=4)
    p_run.add_argument(
        "--commission", type=float, default=0.0, help="round-turn dollars per contract"
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
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ingest.IngestError, splice.SpliceError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
