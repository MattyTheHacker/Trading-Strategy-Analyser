"""Replay a campaign shortlist's stored trade logs through a prop firm's account rules.

    uv run tools/campaign_shortlist.py --strategy OpeningRange --held-out
    uv run tools/campaign_propaccount.py --strategy OpeningRange
    uv run tools/campaign_propaccount.py --strategy OpeningRange --preset all --last-months 12
    uv run tools/campaign_propaccount.py --strategy InsideBarTrailing \
        --stratum phase=MIDDAY --resolution 5 --quantities 3 4 6 8
    uv run tools/campaign_propaccount.py --strategy OpeningRange --book-sizes 5 10 15 20 --stagger 5

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

FUNDED = "funded"
"""The ``--stagger`` value that opens each next account once the book's payouts less fees cover it."""

BOOK_REPORTED = (
    "attempts",
    "breaches",
    "payout",
    "fees_paid",
    "net",
    "most_breached_in_a_day",
    "days_most_breached",
    "open_at_end",
)
"""Which of :class:`~nqbt.propaccount.BookReplay`'s figures reach a book's row."""


class Window(NamedTuple):
    """The held-out trading days, and the whole months at their end the monthly figures read."""

    days: DateArray
    months: tuple[pd.Period, ...]


class Book(NamedTuple):
    """How a book is built: what its slots take in turn, and when each opens."""

    accounts: tuple[propaccount.Account, ...]
    sizes: tuple[int, ...] | None
    """The contract counts slots take in turn; ``None`` trades the log at the size it was stored at."""

    stagger: int | None
    """Trading days between openings; ``None`` opens each once the book's payouts can pay for it."""

    max_accounts: int | None
    """Attempts per slot: 1 lets the book shrink, and ``None`` cannot bind."""

    @property
    def name(self) -> str:
        """The presets the book's slots take in turn."""
        return " + ".join(account.name for account in self.accounts)


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


def cash_flows(result: propaccount.PropReplay | propaccount.BookReplay) -> list[tuple[dt.date, float]]:
    """Return what each day's fees and payouts came to, payouts positive, oldest day first."""
    return propaccount.daily_cash(result.runs)


def running_totals(cash: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    """Return the payouts less the fees at the end of each day, to the cent."""
    totals: list[tuple[dt.date, float]] = []
    total: float = 0.0
    for day, moved in cash:
        total += moved
        totals.append((day, round(total, 2)))

    return totals


def days_to_profit(opened: dt.date, running: list[tuple[dt.date, float]], days: DateArray) -> float:
    """Count trading days from the first account's opening to the first day payouts exceed fees.

    ``inf`` where they never do.
    """
    broke_even: dt.date | None = next((day for day, total in running if total > 0.0), None)
    if broke_even is None:
        return float("inf")

    return float(sessions_between(days, opened, broke_even))


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


def paid_back(
    result: propaccount.PropReplay | propaccount.BookReplay,
    window: Window,
) -> dict[str, float | int | bool]:
    """Measure when a replay's fees were paid back and how steady its months were."""
    cash: list[tuple[dt.date, float]] = cash_flows(result)
    running: list[tuple[dt.date, float]] = running_totals(cash)
    months: list[float] = monthly_net(cash, window.months)
    days: float = float("inf")
    if result.runs:
        days = days_to_profit(min(run.first_day for run in result.runs), running, window.days)

    return {
        "days_to_profit": days,
        "broke_even": bool(np.isfinite(days)),
        "months": len(window.months),
        "profitable_months": sum(net > 0.0 for net in months),
        "out_of_pocket": out_of_pocket(running),
        "best_month": max(months),
        "worst_month": min(months),
        "losing_streak": longest_run(net < 0.0 for net in months),
    }


def timing(
    result: propaccount.PropReplay,
    account: propaccount.Account,
    log: pd.DataFrame,
    window: Window,
    max_accounts: int,
) -> dict[str, float | int | bool]:
    """Measure when one replay's money came back, how steady its months were and how fresh starts fared."""
    evaluations, fees = spent_before_first_payout(result, account)
    payouts: list[float] = [taken.payout for run in result.runs for taken in run.withdrawals]

    return {
        **paid_back(result, window),
        "fresh_ahead": fresh_starts_ahead(log, account, window, max_accounts),
        "evaluations_before_payout": evaluations,
        "fees_before_payout": fees,
        "payouts": len(payouts),
        "payout_median": statistics.median(payouts) if payouts else float("nan"),
    }


def lifetime_figures(result: propaccount.PropReplay, log: pd.DataFrame) -> dict[str, object]:
    """Return the contracts ``log`` put on per trade, and :data:`REPORTED`'s figures of its replay."""
    lifetime: dict[str, str | float | int] = result.as_dict()

    return {CONTRACTS: contracts_per_trade(log), **{field: lifetime[field] for field in REPORTED}}


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

    measured: dict[str, object] = {
        **labelled(row),
        "held_pf": float(row["profit_factor"]),
        **lifetime_figures(result, log),
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


def stagger(text: str) -> int | None:
    """Parse ``--stagger``: trading days between openings, or :data:`FUNDED` for ``None``."""
    if text.strip().casefold() == FUNDED:
        return None

    days: int = int(text)
    if days < 0:
        msg: str = f"a stagger is trading days and cannot be negative; got {days}"
        raise argparse.ArgumentTypeError(msg)

    return days


def logs_as_stored(
    rows: pd.DataFrame,
    logs: Mapping[tuple[int, int], pd.DataFrame],
) -> dict[tuple[int, int], dict[int, pd.DataFrame]]:
    """Key each configuration's one log by the contract count it was stored at."""
    return {
        log_key(row): {int(row["order_quantity"]): logs[log_key(row)]}
        for _, row in rows.iterrows()
        if log_key(row) in logs
    }


def logs_at_sizes(
    strategy: str,
    rows: pd.DataFrame,
    root: str,
    quantities: Sequence[int],
) -> dict[tuple[int, int], dict[int, pd.DataFrame]]:
    """Re-run the shortlist at each contract count, leaving out a configuration that refuses any of them."""
    archetype: archetypes.Archetype = archetypes.get(strategy)
    distinct: list[int] = list(dict.fromkeys(quantities))
    eligible: pd.DataFrame = rows
    for quantity in distinct:
        eligible = at_quantity(eligible, archetype, quantity)

    if eligible.empty:
        logger.warning("  no configuration here can take every one of %s contracts", distinct)

        return {}

    sized: dict[tuple[int, int], dict[int, pd.DataFrame]] = {}
    for quantity in distinct:
        logs: dict[tuple[int, int], pd.DataFrame]
        rerun: pd.DataFrame
        logs, rerun = logs_for(strategy, eligible.assign(order_quantity=quantity), root)
        show(
            f"{strategy} {root} at {quantity} contracts -- what the book's re-run ran on",
            rerun.reindex(columns=RUNG_CHECK),
        )
        for key, log in logs.items():
            sized.setdefault(key, {})[quantity] = log

    return {key: by_size for key, by_size in sized.items() if len(by_size) == len(distinct)}


def replay_one_book(
    book: Book,
    logs: Mapping[int, pd.DataFrame],
    count: int,
    days: DateArray,
) -> propaccount.BookReplay:
    """Replay a book of ``count`` slots over one configuration's logs, opening from the window's first day."""
    sizes: tuple[int, ...] = book.sizes if book.sizes is not None else tuple(logs)
    plan: list[tuple[propaccount.Account, int]] = [
        (book.accounts[slot % len(book.accounts)], sizes[slot % len(sizes)]) for slot in range(count)
    ]
    if book.stagger is None:
        start: dt.date = pd.Timestamp(days[0]).date()

        return propaccount.replay_funded_book(logs, plan, start, max_accounts=book.max_accounts)

    slots: list[propaccount.BookSlot] = [
        propaccount.BookSlot(account, pd.Timestamp(days[slot * book.stagger]).date(), contracts)
        for slot, (account, contracts) in enumerate(plan)
        if slot * book.stagger < days.size
    ]

    return propaccount.replay_book(logs, slots, max_accounts=book.max_accounts)


def book_row(  # type: ignore[explicit-any]  # duckdb's dtypes
    row: pd.Series,
    book: Book,
    result: propaccount.BookReplay,
    size: int,
    window: Window,
) -> dict[str, object]:
    """Return one book's figures at one size, beside the configuration it replayed."""
    lifetime: dict[str, object] = {name: getattr(result, name) for name in BOOK_REPORTED}

    return {
        **labelled(row),
        "held_pf": float(row["profit_factor"]),
        "book": book.name,
        "book_size": size,
        "accounts": len(result.slots),
        "sizes": "/".join(str(contracts) for contracts in sorted({slot.contracts for slot in result.slots})),
        **lifetime,
        "profitable": result.net > 0.0,
        **paid_back(result, window),
    }


def replay_books(
    rows: pd.DataFrame,
    logs: Mapping[tuple[int, int], Mapping[int, pd.DataFrame]],
    books: Sequence[Book],
    sizes: Sequence[int],
    window: Window,
) -> pd.DataFrame:
    """Replay every configuration through every book at every size, a book of one beside them.

    Each book is replayed once at its largest size; a smaller one is its first slots.
    """
    counts: list[int] = sorted({1, *sizes})
    replayed: list[dict[str, object]] = []
    for _, row in rows.iterrows():
        sized: Mapping[int, pd.DataFrame] = logs.get(log_key(row), {})
        if not sized or any(log.empty for log in sized.values()):
            logger.warning("  sweep %-4d combo %-6d has no log at every size the book trades", *log_key(row))
            continue

        for book in books:
            try:
                whole: propaccount.BookReplay = replay_one_book(book, sized, counts[-1], window.days)
            except propaccount.PropAccountError as refused:
                logger.warning("  %-14s sweep %-4d combo %-6d refused: %s", book.name, *log_key(row), refused)
                continue

            replayed.extend(book_row(row, book, whole.first(count), count, window) for count in counts)

    return pd.DataFrame(replayed)


def book_verdict(table: pd.DataFrame) -> pd.DataFrame:
    """Return each book's medians across the shortlist at each size, and the shares that are not medians."""
    if table.empty:
        return pd.DataFrame()

    grouped = table.groupby(["book", "book_size"], sort=False)
    columns = {
        "configurations": grouped.size(),
        "accounts_med": grouped["accounts"].median(),
        "fees_med": grouped["fees_paid"].median(),
        "net_med": grouped["net"].median(),
        "profitable_%": 100.0 * grouped["profitable"].mean(),
        "broke_even_%": 100.0 * grouped["broke_even"].mean(),
        "days_to_profit_med": grouped["days_to_profit"].median(),
        "out_of_pocket_med": grouped["out_of_pocket"].median(),
        "profitable_months_med": grouped["profitable_months"].median(),
        "most_breached_med": grouped["most_breached_in_a_day"].median(),
        "days_most_breached_med": grouped["days_most_breached"].median(),
        "open_at_end_med": grouped["open_at_end"].median(),
    }

    return pd.DataFrame(columns).reset_index()


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


def write(out: Path, table: pd.DataFrame, books: pd.DataFrame | None = None) -> None:
    """Write every replay row, the verdict and each configuration's best rule set under ``out``.

    ``books`` adds every book row and the books' verdict.
    """
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "replays.csv", index=False)
    verdict(table).to_csv(out / "verdict.csv", index=False)
    best_presets(table).to_csv(out / "best.csv", index=False)
    if books is not None:
        books.to_csv(out / "books.csv", index=False)
        book_verdict(books).to_csv(out / "book_verdict.csv", index=False)

    logger.info("wrote %s", out)


def books_from(
    args: argparse.Namespace,
    accounts: Sequence[propaccount.Account],
    order: propaccount.ExcursionOrder | None,
) -> list[Book]:
    """Return one book per rule set, or the one ``--book-mix`` names, under the command line's settings."""
    max_accounts: int | None = 1 if args.no_replace else args.max_accounts
    sizes: tuple[int, ...] | None = tuple(args.book_quantities) if args.book_quantities else None
    if not args.book_mix:
        return [Book((account,), sizes, args.stagger, max_accounts) for account in accounts]

    mix: list[propaccount.Account] = [account for name in args.book_mix for account in chosen([name])]
    if order is not None:
        mix = [in_order(account, order) for account in mix]

    return [Book(tuple(mix), sizes, args.stagger, max_accounts)]


def check_book_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Refuse a book option given without ``--book-sizes``, sizes no book could take and an unknown mix."""
    shapes_a_book: bool = (
        args.stagger != 0 or args.no_replace or bool(args.book_mix) or bool(args.book_quantities)
    )
    if not args.book_sizes:
        if shapes_a_book:
            parser.error("--stagger, --no-replace, --book-mix and --book-quantities need --book-sizes")

        return

    if args.quantities:
        parser.error("--book-sizes takes its contract counts from --book-quantities, not --quantities")

    if min(args.book_sizes) < 1 or min(args.book_quantities or [1]) < 1:
        parser.error("--book-sizes and --book-quantities must be at least 1")

    try:
        chosen(args.book_mix or [])
    except propaccount.PropAccountError as refused:
        parser.error(str(refused))


def report_books(
    args: argparse.Namespace,
    rows: pd.DataFrame,
    logs: Mapping[tuple[int, int], pd.DataFrame],
    accounts: Sequence[propaccount.Account],
    order: propaccount.ExcursionOrder | None,
    window: Window,
) -> pd.DataFrame:
    """Replay and print every book ``args`` asks for, over ``logs`` or ``--book-quantities``' re-runs.

    Under ``--book-quantities`` the profit factor is read off the first size's log.
    """
    sized: dict[tuple[int, int], dict[int, pd.DataFrame]]
    if args.book_quantities:
        sized = logs_at_sizes(args.strategy, rows, args.root, args.book_quantities)
        first: int = args.book_quantities[0]
        rows = with_own_profit_factor(rows, {key: by_size[first] for key, by_size in sized.items()})
    else:
        sized = logs_as_stored(rows, logs)

    books: pd.DataFrame = replay_books(
        rows, sized, books_from(args, accounts, order), args.book_sizes, window
    )
    show(f"{args.strategy} {args.root} -- every configuration through every book", books)
    show("what each book was worth, across the shortlist", book_verdict(books))

    return books


def build_parser() -> argparse.ArgumentParser:
    """Return the command line's parser."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Prop-account replay over a campaign shortlist."
    )
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
        "--book-sizes",
        nargs="+",
        type=int,
        default=None,
        help="also replay a book of this many accounts on each configuration, beside a book of one",
    )
    parser.add_argument(
        "--stagger",
        type=stagger,
        default=0,
        help=f"trading days between a book's openings, or {FUNDED!r} to open each once its payouts cover it",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="give each of a book's accounts one attempt, so it shrinks; overrides --max-accounts for books",
    )
    parser.add_argument(
        "--book-mix",
        nargs="+",
        default=None,
        help="replay one book whose accounts take these rule sets in turn, rather than a book per --preset",
    )
    parser.add_argument(
        "--book-quantities",
        nargs="+",
        type=int,
        default=None,
        help="re-run the shortlist at these contract counts, which a book's accounts take in turn",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write every replay row, the verdict and each configuration's best rule set here",
    )

    return parser


def main(argv: list[str]) -> int:
    """Replay the shortlist through the prop account rules and return the process exit code."""
    logsetup.configure(__name__)
    parser: argparse.ArgumentParser = build_parser()
    args = parser.parse_args(argv[1:])
    check_book_options(parser, args)

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
    order: propaccount.ExcursionOrder | None = None
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
    logs: Mapping[tuple[int, int], pd.DataFrame] = {}
    if args.quantities:
        table = replay_rungs(
            args.strategy, rows, args.root, args.quantities, accounts, args.max_accounts, window
        )
    else:
        logs = shortlist_logs(args.strategy, rows, args.root, rerun=args.rerun)
        table = replay_shortlist(rows, logs, accounts, args.max_accounts, window)

    if table.empty:
        logger.warning("no trade logs for this shortlist; nothing to replay")

        return 1

    show(f"{args.strategy} {args.root} -- every configuration through every rule set", table)
    show("what each rule set was worth, across the shortlist", verdict(table))
    show("each configuration's fastest rule set to profit", best_presets(table))
    books: pd.DataFrame | None = None
    if args.book_sizes:
        books = report_books(args, rows, logs, accounts, order, window)

    logger.info("")
    logger.info(
        "net is payout minus fees and is not a ranking; read it beside %s and the pass rate",
        NET_TO_DRAWDOWN,
    )
    logger.info(
        "days to profit is a best case: every payout is taken at the close of the first day the "
        "firm's payout rules allow it, at the largest size they allow"
    )
    if books is not None:
        logger.info(
            "a book's net grows with its size and the strategy's edge does not: read it beside held_pf "
            "and the book of one. Its accounts share almost every trade, so they are not independent "
            "samples, and no firm's limit on accounts per trader is checked"
        )

    if args.out is not None:
        write(args.out, table, books)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
