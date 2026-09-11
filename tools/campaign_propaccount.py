"""Replay a campaign shortlist's stored trade logs through a prop firm's account rules.

    ./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --held-out
    ./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy OpeningRange

:mod:`nqbt.propaccount` answers the question no gate in §M27 or §M28 can be expressed in --
**not "is the edge real" but "would the account have survived it, and would it have made more
than it cost"** -- and §M28.13 read the whole registry through it from a script that was never
committed. This is that read as a tool, so a cell can be put through an account the way it is
put through a null -- ``docs/roadmap.md`` §M28.13.

**The shortlist is chosen on the selection window and replayed over the held-out one**, which
is :func:`~tools.campaign_holdout.held_out` and not :func:`~tools.campaign_shortlist.shortlist`:
a sequence of accounts read from the window that chose it is the trap §M28.12 records. There is
no ``--window`` here for that reason.

**The attempt cap must not bind, and by default it cannot.** §M28.13's population run capped
attempts at five, which bound on 98% of configurations and truncated their net figures badly
enough to be wrong in sign -- a blown account costs its fees and not its trading losses, so
stopping early hides the wins that come after. :func:`uncapped` is the default and
``capped`` says on every row whether the cap was reached.

**Nothing here is a ranking.** ``net`` rewards variance and can put a configuration that loses
money as a strategy above one that makes it, because each blown account caps the loss at the
fee -- ``docs/roadmap.md`` §M28.13, "The reset economics subsidise a losing strategy". Read it
beside the profit factor and the pass rate.

Reads the logs ``tools/campaign_shortlist.py --held-out`` stored, so run that first; a row with
no log, and one whose rule set refuses it, are each named and skipped rather than silently
dropped.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path

import pandas as pd

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.campaign_holdout import held_out
from tools.campaign_montecarlo import LABEL_COLUMNS
from tools.campaign_report import NET_TO_DRAWDOWN, load_trades
from tools.campaign_shortlist import TOP
from tools.campaign_sweep import db_path

from nqbt import logsetup, propaccount

logger = logging.getLogger(__name__)

REPORTED = (
    "account_name",
    "attempts",
    "passes",
    "breaches",
    "withdrawn",
    "payout",
    "fees_paid",
    "net",
    "trades_taken",
    "trades_total",
)
"""Which of :class:`~nqbt.propaccount.PropReplay`'s lifetime figures reach a row.

``pass_rate`` is left off because ``passes`` and ``attempts`` are both here and a ratio of two
printed columns is a third way to read the same pair."""

DEFAULT_PRESETS = ("Apex 50K", "Apex 150K", "TopStep 50K", "TopStep 150K")
"""Which rule sets a run reports unless ``--preset`` says otherwise.

The four §M28.13 read the registry through. TakeProfitTrader ships as six presets covering two
phases each, which is a table three times the size for a question about one cell."""

CONTRACTS = "contracts"
"""Position size the account actually faced, per trade.

Not a parameter of the replay and reported because it decides the answer: four contracts is a
different instrument-sized bet on each root, and the trailing threshold divided by the dollar
value of a point is the whole account's room to move -- ``docs/roadmap.md`` §M28.13, "The
binding constraint is position size, not the strategy"."""


def uncapped(log: pd.DataFrame) -> int:
    """An attempt cap that cannot bind on this log.

    Each attempt consumes at least one trading day and a day holds at least one trade, so the
    trade count bounds the attempts from above.
    """
    return max(1, int(log["trade_id"].nunique()))


def contracts_per_trade(log: pd.DataFrame) -> float:
    """Contracts one trade of this log put on, as the legs' quantities summed per trade."""
    return float(log.groupby("trade_id")["quantity"].sum().mean())


def rules_with(
    account: propaccount.PropAccount, order: propaccount.ExcursionOrder
) -> propaccount.PropAccount:
    """One preset with its excursion order replaced, the rest of the rule set untouched."""
    if order is account.rules.excursion_order:
        return account

    return dataclasses.replace(account, rules=dataclasses.replace(account.rules, excursion_order=order))


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The tag columns that say which stored configuration a result row belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def _where(row: pd.Series) -> tuple[int, int]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The ``(sweep_id, combo_id)`` a stored row is filed under."""
    return int(row["sweep_id"]), int(row["combo_id"])


def replay_row(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    log: pd.DataFrame,
    account: propaccount.PropAccount,
    max_accounts: int,
) -> dict[str, object] | None:
    """One configuration through one rule set, or ``None`` where the rules refuse the log."""
    try:
        result: propaccount.PropReplay = propaccount.replay(log, account, max_accounts=max_accounts)
    except propaccount.PropAccountError as refused:
        logger.warning("  %-14s sweep %-4d combo %-6d refused: %s", account.name, *_where(row), refused)

        return None

    lifetime: dict[str, str | float | int] = result.as_dict()

    return {
        **labelled(row),
        "held_pf": float(row["profit_factor"]),
        CONTRACTS: contracts_per_trade(log),
        **{field: lifetime[field] for field in REPORTED},
        "ever_passed": result.passes > 0,
        "profitable": result.net > 0.0,
        "capped": result.attempts >= max_accounts,
    }


def replay_shortlist(
    rows: pd.DataFrame,
    path: Path,
    accounts: list[propaccount.PropAccount],
    max_accounts: int | None,
) -> pd.DataFrame:
    """Every shortlisted configuration through every rule set, one row each."""
    replayed: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        log: pd.DataFrame = load_trades(*_where(row), path)
        if log.empty:
            logger.warning(
                "  sweep %-4d combo %-6d has no stored log; run tools/campaign_shortlist.py --held-out first",
                *_where(row),
            )
            continue

        attempts: int = max_accounts if max_accounts is not None else uncapped(log)
        for account in accounts:
            measured: dict[str, object] | None = replay_row(row, log, account, attempts)
            if measured is None:
                continue

            replayed.append(measured)

    return pd.DataFrame(replayed)


def verdict(table: pd.DataFrame) -> pd.DataFrame:
    """Each rule set's medians across the shortlist, and the two shares that are not medians.

    A median attempt count and a median net describe the sequence a configuration produced;
    ``ever_passed`` and ``profitable`` are shares because both questions are yes or no per
    configuration and a median of a boolean says nothing.
    """
    if table.empty:
        return pd.DataFrame()

    grouped = table.groupby("account_name", sort=False)

    return pd.DataFrame(
        {
            "configurations": grouped.size(),
            "attempts_med": grouped["attempts"].median(),
            "passes_med": grouped["passes"].median(),
            "withdrawn_med": grouped["withdrawn"].median(),
            "fees_med": grouped["fees_paid"].median(),
            "net_med": grouped["net"].median(),
            "ever_passed_%": 100.0 * grouped["ever_passed"].mean(),
            "profitable_%": 100.0 * grouped["profitable"].mean(),
            "capped": grouped["capped"].sum(),
        },
    ).reset_index()


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
    parser = argparse.ArgumentParser(description="Prop-account replay over a campaign shortlist.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", default="MNQ")
    parser.add_argument("--by", default="profit_factor", help="the selection-window statistic that ranks")
    parser.add_argument("--stratum", default=None, help="restrict the ranking to one stratum")
    parser.add_argument("--resolution", type=int, default=None, help="restrict it to one bar size")
    parser.add_argument("--variant", default=None, help="restrict it to one variant of the grid")
    parser.add_argument("--top", type=int, default=TOP, help="how many configurations to replay")
    parser.add_argument(
        "--preset",
        nargs="+",
        default=list(DEFAULT_PRESETS),
        help="which rule sets to replay; a name from nqbt.propaccount.PRESETS",
    )
    parser.add_argument(
        "--max-accounts",
        type=int,
        default=None,
        help="attempts per configuration; the default cannot bind, and a cap that does is wrong in sign",
    )
    parser.add_argument(
        "--excursion-order",
        choices=[str(order) for order in propaccount.ExcursionOrder],
        default=None,
        help="override which of a trade's excursions moves the floor first",
    )
    args = parser.parse_args(argv[1:])

    rows: pd.DataFrame = held_out(
        args.strategy,
        args.root,
        args.by,
        args.top,
        args.stratum,
        args.resolution,
        args.variant,
    )
    accounts: list[propaccount.PropAccount] = [propaccount.preset(name) for name in args.preset]
    if args.excursion_order is not None:
        order = propaccount.ExcursionOrder(args.excursion_order)
        accounts = [rules_with(account, order) for account in accounts]

    logger.info(
        "%s on %s: %d held-out configurations ranked on selection by %s, through %d rule sets",
        args.strategy,
        args.root,
        len(rows),
        args.by,
        len(accounts),
    )

    table: pd.DataFrame = replay_shortlist(rows, db_path(args.strategy), accounts, args.max_accounts)
    if table.empty:
        logger.warning("no stored trade logs for this shortlist; nothing to replay")

        return 1

    show(f"{args.strategy} {args.root} -- every configuration through every rule set", table)
    show("what each rule set was worth, across the shortlist", verdict(table))
    logger.info("")
    logger.info(
        "net is payout minus fees and is not a ranking; read it beside %s and the pass rate",
        NET_TO_DRAWDOWN,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
