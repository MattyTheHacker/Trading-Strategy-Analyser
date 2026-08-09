"""Command line entry points."""

from __future__ import annotations

import argparse
import sys

from nqbt import ingest, paths, splice


def _cmd_ingest(args: argparse.Namespace) -> int:
    results = ingest.ingest_all(
        data_dir=args.data_dir, cache_dir=args.cache_dir, root=args.root, force=args.force
    )
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
        data_dir=args.data_dir,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nqbt", description=__doc__)
    parser.add_argument("--data-dir", type=lambda p: paths.Path(p), default=paths.DATA_DIR)
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
