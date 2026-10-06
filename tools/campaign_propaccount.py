"""Replay a campaign shortlist's stored trade logs through a prop firm's account rules.

    uv run tools/campaign_shortlist.py --strategy OpeningRange --held-out
    uv run tools/campaign_propaccount.py --strategy OpeningRange
    uv run tools/campaign_propaccount.py --strategy OpeningRange --preset all --last-months 12
    uv run tools/campaign_propaccount.py --strategy InsideBarTrailing \
        --stratum phase=MIDDAY --resolution 5 --quantities 3 4 6 8

Nothing here is a ranking -- ``tools/README.md`` § "campaign_propaccount.py".
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, logsetup, propaccount, sessions, splice, stats
from tools.campaign_holdout import held_out
from tools.campaign_montecarlo import LABEL_COLUMNS
from tools.campaign_null import stored_rows
from tools.campaign_report import NET_TO_DRAWDOWN, log_key, stored_logs
from tools.campaign_shortlist import TOP, rebuild, source
from tools.campaign_sweep import db_path
from tools.campaign_swept import CELL_KEYS, HELD_OUT, SWEPT_BARS, candidate_bars, logs_for

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Iterable, Mapping, Sequence

    from nqbt.arrays import DateArray

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
    "trades_rejected",
    "trades_total",
)
"""Which of :class:`~nqbt.propaccount.PropReplay`'s lifetime figures reach a row."""

DEFAULT_PRESETS = (
    "Apex 50K Intraday Evaluation+PA",
    "Apex 150K Intraday Evaluation+PA",
    "TopStep 50K Combine+XFA",
    "TopStep 150K Combine+XFA",
)
"""Which rule sets a run reports unless ``--preset`` says otherwise: the firms and sizes §M28.13 read."""

ALL = "all"
"""The ``--preset`` value standing for :data:`EVERY_PRESET`."""

EVERY_PRESET = tuple(propaccount.LINKED_PRESETS)
"""What ``--preset all`` replays: every firm's evaluation linked to its funded account."""

LAST_MONTHS = 12
"""How many of the holdout's last whole months the monthly figures read by default."""

CONTRACTS = "contracts"
"""Position size the account actually faced, per trade -- ``docs/roadmap.md`` §M28.13."""


QUANTITY = "quantity"
"""The contract count a rung re-ran the shortlist at, which the verdict groups by beside the rule set."""

RUNG_CHECK = [*CELL_KEYS, "rows", SWEPT_BARS, "same_trades"]
"""What a rung reports of its re-run: the bars it ran on and how many rows kept their stored
trade count. Net is left out, because a row stored at one size is not reproduced at another."""

BEST_COLUMNS = ["held_pf", "best_preset", "days_to_profit", "profitable_months", "fresh_ahead"]
"""What :func:`best_presets` reports beside each configuration's tags."""


class Window(NamedTuple):
    """The held-out trading days, and the whole months at their end the monthly figures read."""

    days: DateArray
    months: tuple[pd.Period, ...]


def uncapped(log: pd.DataFrame) -> int:
    """Return an attempt cap that cannot bind on this log.

    Each attempt consumes at least one trading day and a day holds at least one trade, so the
    trade count bounds the attempts from above.
    """
    return max(1, int(log["trade_id"].nunique()))


def contracts_per_trade(log: pd.DataFrame) -> float:
    """Count the contracts one trade of this log put on, as the legs' quantities summed per trade."""
    return float(log.groupby("trade_id")["quantity"].sum().mean())


def rules_with(
    account: propaccount.PropAccount, order: propaccount.ExcursionOrder
) -> propaccount.PropAccount:
    """Return one preset with its excursion order replaced, the rest of the rule set untouched."""
    if order is account.rules.excursion_order:
        return account

    return dataclasses.replace(account, rules=dataclasses.replace(account.rules, excursion_order=order))


def in_order(account: propaccount.Account, order: propaccount.ExcursionOrder) -> propaccount.Account:
    """Return a preset or a linked pair with every rule set's excursion order replaced."""
    if not isinstance(account, propaccount.LinkedAccount):
        return rules_with(account, order)

    evaluation: propaccount.PropAccount = rules_with(account.evaluation, order)
    funded: propaccount.PropAccount = rules_with(account.funded, order)
    if evaluation is account.evaluation and funded is account.funded:
        return account

    return dataclasses.replace(account, evaluation=evaluation, funded=funded)


def chosen(names: Iterable[str]) -> list[propaccount.Account]:
    """Look up ``--preset``'s names once each, with ``all`` standing for :data:`EVERY_PRESET`."""
    expanded: list[str] = [
        name for given in names for name in (EVERY_PRESET if given.strip().casefold() == ALL else (given,))
    ]

    found: list[propaccount.Account] = [propaccount.account_named(name) for name in expanded]

    return list({account.name: account for account in found}.values())


def labelled(row: pd.Series) -> dict[str, object]:  # type: ignore[explicit-any]  # duckdb's dtypes
    """Return the tag columns that say which stored configuration a result row belongs to."""
    return {column: row[column] for column in LABEL_COLUMNS if column in row.index}


def calendar(bars: pd.DataFrame) -> DateArray:
    """List every trading day a window's bars hold a session bar on, in order."""
    info: sessions.SessionInfo = sessions.classify(pd.DatetimeIndex(bars.index))

    return np.unique(info.trading_day[info.in_session])


def sessions_between(days: DateArray, first: dt.date, last: dt.date) -> int:
    """Count trading days from ``first`` to ``last``, both included."""
    start: int = int(np.searchsorted(days, np.datetime64(first, "D"), side="left"))
    end: int = int(np.searchsorted(days, np.datetime64(last, "D"), side="right"))

    return max(0, end - start)


def held_out_days(strategy: str, root: str) -> DateArray:
    """Return every trading day of the held-out window this campaign's stored rows were swept on."""
    archive: pd.DataFrame = splice.load_continuous(root)
    swept: pd.DataFrame = candidate_bars(stored_rows(strategy, root, HELD_OUT), archive)[0]

    return calendar(source(swept, HELD_OUT))


def last_whole_months(days: DateArray, count: int) -> tuple[pd.Period, ...]:
    """Return the last ``count`` calendar months the window covers end to end, oldest first.

    An end month counts as covered when none of its weekdays falls outside the window.
    """
    first: pd.Period = pd.Period(pd.Timestamp(days[0]), freq="M")
    last: pd.Period = pd.Period(pd.Timestamp(days[-1]), freq="M")
    missed_before: int = int(np.busday_count(np.datetime64(first.start_time.date(), "D"), days[0]))
    one_day = np.timedelta64(1, "D")
    missed_after: int = int(
        np.busday_count(days[-1] + one_day, np.datetime64(last.end_time.date(), "D") + one_day)
    )
    whole: list[pd.Period] = list(
        pd.period_range(
            first if missed_before == 0 else first + 1, last if missed_after == 0 else last - 1, freq="M"
        )
    )
    if not 1 <= count <= len(whole):
        msg: str = (
            f"the holdout holds {len(whole)} whole months, so --last-months must be 1 to {len(whole)}; "
            f"got {count}"
        )
        raise ValueError(msg)

    return tuple(whole[-count:])


def first_trading_day(days: DateArray, month: pd.Period) -> dt.date:
    """Return the first trading day in ``month`` that the window holds."""
    index: int = int(np.searchsorted(days, np.datetime64(month.start_time.date(), "D"), side="left"))

    return pd.Timestamp(days[index]).date()


def cash_flows(result: propaccount.PropReplay) -> list[tuple[dt.date, float]]:
    """Return what each day's fees and payouts came to, payouts positive, oldest day first."""
    by_day: defaultdict[dt.date, float] = defaultdict(float)
    for run in result.runs:
        for charge in run.charges:
            by_day[charge.day] -= charge.amount

        for taken in run.withdrawals:
            by_day[taken.day] += taken.payout

    return sorted(by_day.items())


def running_totals(cash: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    """Return the payouts less the fees at the end of each day, to the cent."""
    totals: list[tuple[dt.date, float]] = []
    total: float = 0.0
    for day, moved in cash:
        total += moved
        totals.append((day, round(total, 2)))

    return totals


def days_to_profit(
    result: propaccount.PropReplay,
    running: list[tuple[dt.date, float]],
    days: DateArray,
) -> float:
    """Count trading days from the first account's opening to the first day payouts exceed fees.

    ``inf`` where they never do.
    """
    broke_even: dt.date | None = next((day for day, total in running if total > 0.0), None)
    if broke_even is None:
        return float("inf")

    return float(sessions_between(days, result.runs[0].first_day, broke_even))


def out_of_pocket(running: list[tuple[dt.date, float]]) -> float:
    """Return the most the fees ever stood above the payouts before the payouts first passed them."""
    deepest: float = 0.0
    for _, total in running:
        if total > 0.0:
            break

        deepest = max(deepest, -total)

    return deepest


def spent_before_first_payout(
    result: propaccount.PropReplay,
    account: propaccount.Account,
) -> tuple[float, float]:
    """Return the evaluations bought and the fees charged up to the first payout's day.

    Both ``nan`` where nothing was ever paid out.
    """
    paid: list[dt.date] = [taken.day for run in result.runs for taken in run.withdrawals]
    if not paid:
        return float("nan"), float("nan")

    first: dt.date = min(paid)
    bought: str = propaccount.evaluation_of(account).name
    evaluations: int = sum(run.account_name == bought and run.first_day <= first for run in result.runs)
    fees: float = sum(charge.amount for run in result.runs for charge in run.charges if charge.day <= first)

    return float(evaluations), fees


def monthly_net(cash: list[tuple[dt.date, float]], months: tuple[pd.Period, ...]) -> list[float]:
    """Return payouts less fees in each of ``months``, to the cent, zero in a month nothing moved."""
    by_month: defaultdict[tuple[int, int], float] = defaultdict(float)
    for day, moved in cash:
        by_month[day.year, day.month] += moved

    return [round(by_month[month.year, month.month], 2) for month in months]


def longest_run(flags: Iterable[bool]) -> int:
    """Return the length of the longest unbroken run of ``True``."""
    longest: int = 0
    current: int = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)

    return longest


def fresh_starts_ahead(
    log: pd.DataFrame,
    account: propaccount.Account,
    window: Window,
    max_accounts: int,
) -> int:
    """Count the months whose fresh run, opened on the month's first trading day, ends ahead."""
    ahead: int = 0
    for month in window.months:
        start: dt.date = first_trading_day(window.days, month)
        result: propaccount.PropReplay = propaccount.replay(
            log, account, max_accounts=max_accounts, start=start
        )
        ahead += round(result.net, 2) > 0.0

    return ahead


def timing(
    result: propaccount.PropReplay,
    account: propaccount.Account,
    log: pd.DataFrame,
    window: Window,
    max_accounts: int,
) -> dict[str, float | int | bool]:
    """Measure when one replay's money came back and how steady its months were."""
    cash: list[tuple[dt.date, float]] = cash_flows(result)
    running: list[tuple[dt.date, float]] = running_totals(cash)
    months: list[float] = monthly_net(cash, window.months)
    evaluations, fees = spent_before_first_payout(result, account)
    payouts: list[float] = [taken.payout for run in result.runs for taken in run.withdrawals]
    days: float = days_to_profit(result, running, window.days)

    return {
        "days_to_profit": days,
        "broke_even": bool(np.isfinite(days)),
        "months": len(window.months),
        "profitable_months": sum(net > 0.0 for net in months),
        "fresh_ahead": fresh_starts_ahead(log, account, window, max_accounts),
        "out_of_pocket": out_of_pocket(running),
        "evaluations_before_payout": evaluations,
        "fees_before_payout": fees,
        "payouts": len(payouts),
        "payout_median": statistics.median(payouts) if payouts else float("nan"),
        "best_month": max(months),
        "worst_month": min(months),
        "losing_streak": longest_run(net < 0.0 for net in months),
    }


def replay_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    log: pd.DataFrame,
    account: propaccount.Account,
    max_accounts: int,
    window: Window | None = None,
) -> dict[str, object] | None:
    """Replay one configuration through one rule set, or return ``None`` where the rules refuse the log.

    A ``window`` adds :func:`timing`'s figures.
    """
    try:
        result: propaccount.PropReplay = propaccount.replay(log, account, max_accounts=max_accounts)
    except propaccount.PropAccountError as refused:
        logger.warning("  %-14s sweep %-4d combo %-6d refused: %s", account.name, *log_key(row), refused)

        return None

    lifetime: dict[str, str | float | int] = result.as_dict()
    measured: dict[str, object] = {
        **labelled(row),
        "held_pf": float(row["profit_factor"]),
        CONTRACTS: contracts_per_trade(log),
        **{field: lifetime[field] for field in REPORTED},
        "ever_passed": result.passes > 0,
        "profitable": result.net > 0.0,
        "capped": result.attempts >= max_accounts,
    }
    if window is None:
        return measured

    return {**measured, **timing(result, account, log, window, max_accounts)}


def replay_shortlist(
    rows: pd.DataFrame,
    logs: Mapping[tuple[int, int], pd.DataFrame],
    accounts: Sequence[propaccount.Account],
    max_accounts: int | None,
    window: Window | None = None,
) -> pd.DataFrame:
    """Replay every shortlisted configuration through every rule set, one row each."""
    replayed: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        log: pd.DataFrame = logs.get(log_key(row), pd.DataFrame())
        if log.empty:
            logger.warning(
                "  sweep %-4d combo %-6d has no log; run tools/campaign_shortlist.py --held-out or --rerun",
                *log_key(row),
            )
            continue

        attempts: int = max_accounts if max_accounts is not None else uncapped(log)
        for account in accounts:
            measured: dict[str, object] | None = replay_row(row, log, account, attempts, window)
            if measured is None:
                continue

            replayed.append(measured)

    return pd.DataFrame(replayed)


def takes_quantity(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    archetype: archetypes.Archetype,
    quantity: int,
) -> bool:
    """Return whether a stored configuration's rules accept ``quantity`` contracts, naming it where not."""
    resized = row.copy()
    resized["order_quantity"] = quantity
    try:
        rebuild(resized, archetype)
    except ValueError as refused:
        logger.warning(
            "  sweep %-4d combo %-6d cannot take %d contracts: %s", *log_key(row), quantity, refused
        )

        return False

    return True


def at_quantity(rows: pd.DataFrame, archetype: archetypes.Archetype, quantity: int) -> pd.DataFrame:
    """Restate the shortlist at ``quantity`` contracts, less any row whose rules refuse that size.

    A refusal is named rather than dropped: InsideBarTrailing's 0.6 split leaves no second lot
    below three contracts, and a bracket with several targets needs a contract for each.
    """
    takes: list[bool] = [takes_quantity(row, archetype, quantity) for _, row in rows.iterrows()]

    return rows.loc[takes].assign(order_quantity=quantity)


def with_own_profit_factor(rows: pd.DataFrame, logs: Mapping[tuple[int, int], pd.DataFrame]) -> pd.DataFrame:
    """Return the rows with ``profit_factor`` read off their re-run logs rather than the stored size's."""
    measured: list[float] = [
        stats.summarise(logs[log_key(row)]).profit_factor if log_key(row) in logs else float("nan")
        for _, row in rows.iterrows()
    ]

    return rows.assign(profit_factor=measured)


def replay_rungs(
    strategy: str,
    rows: pd.DataFrame,
    root: str,
    quantities: list[int],
    accounts: Sequence[propaccount.Account],
    max_accounts: int | None,
    window: Window | None = None,
) -> pd.DataFrame:
    """Re-run and replay the shortlist once per contract count, each row tagged with its rung."""
    archetype: archetypes.Archetype = archetypes.get(strategy)
    tables: list[pd.DataFrame] = []
    for quantity in quantities:
        resized: pd.DataFrame = at_quantity(rows, archetype, quantity)
        if resized.empty:
            logger.warning("  no configuration here can take %d contracts", quantity)
            continue

        logs: dict[tuple[int, int], pd.DataFrame]
        rerun: pd.DataFrame
        logs, rerun = logs_for(strategy, resized, root)
        show(
            f"{strategy} {root} at {quantity} contracts -- what the re-run ran on",
            rerun.reindex(columns=RUNG_CHECK),
        )
        table: pd.DataFrame = replay_shortlist(
            with_own_profit_factor(resized, logs), logs, accounts, max_accounts, window
        )
        tables.append(table.assign(**{QUANTITY: quantity}))

    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


def configuration_keys(table: pd.DataFrame) -> list[str]:
    """List the columns that name one configuration at one size in a table of replay rows."""
    return [column for column in [*LABEL_COLUMNS, QUANTITY] if column in table.columns]


def verdict(table: pd.DataFrame) -> pd.DataFrame:
    """Return each rule set's medians across the shortlist, and the shares that are not medians.

    A table of rungs gets one row per rule set and contract count.
    """
    if table.empty:
        return pd.DataFrame()

    keys: list[str] = ["account_name", *([QUANTITY] if QUANTITY in table.columns else [])]
    grouped = table.groupby(keys, sort=False)
    columns = {
        "configurations": grouped.size(),
        "attempts_med": grouped["attempts"].median(),
        "passes_med": grouped["passes"].median(),
        "withdrawn_med": grouped["withdrawn"].median(),
        "fees_med": grouped["fees_paid"].median(),
        "net_med": grouped["net"].median(),
        "ever_passed_%": 100.0 * grouped["ever_passed"].mean(),
        "profitable_%": 100.0 * grouped["profitable"].mean(),
        "capped": grouped["capped"].sum(),
    }
    if "days_to_profit" in table.columns:
        columns |= {
            "broke_even_%": 100.0 * grouped["broke_even"].mean(),
            "days_to_profit_med": grouped["days_to_profit"].median(),
            "profitable_months_med": grouped["profitable_months"].median(),
            "fresh_ahead_med": grouped["fresh_ahead"].median(),
        }

    return pd.DataFrame(columns).reset_index()


def best_presets(table: pd.DataFrame) -> pd.DataFrame:
    """Return each configuration's fastest rule set to profit, more profitable months breaking ties.

    ``none`` where no rule set ever broke even, with no figures beside it.
    """
    if table.empty or "days_to_profit" not in table.columns:
        return pd.DataFrame()

    keys: list[str] = configuration_keys(table)
    ranked: pd.DataFrame = table.sort_values(
        ["days_to_profit", "profitable_months"],
        ascending=[True, False],
        kind="stable",
    )
    best: pd.DataFrame = ranked.groupby(keys, sort=False, dropna=False).head(1)
    named = best["account_name"].where(best["broke_even"], "none")
    picked: pd.DataFrame = best.assign(best_preset=named)[[*keys, *BEST_COLUMNS]].reset_index(drop=True)
    picked.loc[picked["best_preset"] == "none", ["profitable_months", "fresh_ahead"]] = float("nan")

    return picked


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 240, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def shortlist_logs(
    strategy: str,
    rows: pd.DataFrame,
    root: str,
    *,
    rerun: bool,
) -> Mapping[tuple[int, int], pd.DataFrame]:
    """Return the shortlist's held-out logs at the size they were swept at: stored, or re-run."""
    if not rerun:
        return stored_logs(rows, db_path(strategy))

    logs: dict[tuple[int, int], pd.DataFrame]
    reconciled: pd.DataFrame
    logs, reconciled = logs_for(strategy, rows, root)
    show(f"{strategy} {root} -- what the re-run reproduced of its stored rows", reconciled)

    return logs


def write(out: Path, table: pd.DataFrame) -> None:
    """Write every replay row, the verdict and each configuration's best rule set under ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "replays.csv", index=False)
    verdict(table).to_csv(out / "verdict.csv", index=False)
    best_presets(table).to_csv(out / "best.csv", index=False)
    logger.info("wrote %s", out)


def main(argv: list[str]) -> int:
    """Replay the shortlist through the prop account rules and return the process exit code."""
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
        help=f"which rule sets to replay: a name from nqbt.propaccount.PRESETS or LINKED_PRESETS, or {ALL!r}",
    )
    parser.add_argument(
        "--last-months",
        type=int,
        default=LAST_MONTHS,
        help="how many of the holdout's last whole months the monthly figures read",
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
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="re-run the shortlist on the bars it was swept on rather than reading a stored log",
    )
    parser.add_argument(
        "--quantities",
        nargs="+",
        type=int,
        default=None,
        help="re-run and replay the shortlist once per contract count; implies --rerun",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write every replay row, the verdict and each configuration's best rule set here",
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
    accounts: list[propaccount.Account] = chosen(args.preset)
    if args.excursion_order is not None:
        order = propaccount.ExcursionOrder(args.excursion_order)
        accounts = [in_order(account, order) for account in accounts]

    if rows.empty:
        logger.warning("no held-out configurations for this shortlist; nothing to replay")

        return 1

    days: DateArray = held_out_days(args.strategy, args.root)
    try:
        window = Window(days, last_whole_months(days, args.last_months))
    except ValueError as refused:
        parser.error(str(refused))

    logger.info(
        "%s on %s: %d held-out configurations ranked on selection by %s, through %d rule sets, "
        "the monthly figures over %s to %s",
        args.strategy,
        args.root,
        len(rows),
        args.by,
        len(accounts),
        window.months[0],
        window.months[-1],
    )

    table: pd.DataFrame
    if args.quantities:
        table = replay_rungs(
            args.strategy, rows, args.root, args.quantities, accounts, args.max_accounts, window
        )
    else:
        table = replay_shortlist(
            rows,
            shortlist_logs(args.strategy, rows, args.root, rerun=args.rerun),
            accounts,
            args.max_accounts,
            window,
        )

    if table.empty:
        logger.warning("no trade logs for this shortlist; nothing to replay")

        return 1

    show(f"{args.strategy} {args.root} -- every configuration through every rule set", table)
    show("what each rule set was worth, across the shortlist", verdict(table))
    show("each configuration's fastest rule set to profit", best_presets(table))
    logger.info("")
    logger.info(
        "net is payout minus fees and is not a ranking; read it beside %s and the pass rate",
        NET_TO_DRAWDOWN,
    )
    logger.info("days to profit is a best case: every payout is taken in full on the first day it is allowed")
    if args.out is not None:
        write(args.out, table)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
