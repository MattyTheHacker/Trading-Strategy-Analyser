"""Replaying a prop-firm account's rules over a trade log.

The question a ranking by profit factor cannot answer: **would this account have survived, and
would it have made more than it cost?** A strategy that breaches the trailing threshold on the
way to a good profit factor does not get funded, and a strategy that blows three accounts while
withdrawing more than the four of them cost is still a business.

Nothing here defines a performance statistic. Every figure describing *the trades* comes from
:func:`nqbt.stats.summarise`; the figures this module owns describe *the account* -- where the
floor sat, which day it was breached on, what was withdrawn and what the attempts cost.

**Unrealised P&L is modelled, and it is why this needs more than ``net_pnl``.** Most firms
measure both the trailing threshold and the daily loss limit against open equity, so a trade
that dips far enough before turning around can end an account it finished profitably. Each
trade's worst and best open equity come from its legs' ``mae_points`` and ``mfe_points``, priced
through :mod:`nqbt.instruments` -- bar-resolution excursions, in keeping with the prime
directive, and never tick data.

The rule set is entirely parameterised because firms genuinely disagree on every axis. What
each preset number rests on, the three assumptions the replay makes where bar data cannot
decide, and what is deliberately not modelled: ``docs/roadmap.md`` § "Replaying a prop account
over the trade log".
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

from nqbt import instruments, sessions, stats

if TYPE_CHECKING:
    import datetime as dt

    from nqbt.arrays import DateArray, FloatArray, IntArray

__all__ = [
    "APEX_50K",
    "APEX_150K",
    "EXCURSION_COLUMNS",
    "PRESETS",
    "REQUIRED_COLUMNS",
    "TOPSTEP_50K",
    "TOPSTEP_150K",
    "AccountFees",
    "AccountRules",
    "AccountRun",
    "DailyBreach",
    "EquityBasis",
    "Outcome",
    "PropAccount",
    "PropAccountError",
    "PropReplay",
    "TrailBasis",
    "TrailLock",
    "preset",
    "replay",
]

REQUIRED_COLUMNS = (
    "trade_id",
    "instrument",
    "quantity",
    "net_pnl",
    "commission",
    "bars_held",
    "mae_points",
    "mfe_points",
    "r_multiple",
    "ambiguous_bar",
    "exit_reason",
    "exit_time",
)
"""Columns every replay needs: what :func:`nqbt.stats.per_trade` collapses and
:func:`nqbt.stats.summarise` reads, plus the two that price an excursion in dollars."""

EXCURSION_COLUMNS = ("mae_points", "mfe_points")
"""Columns that must additionally be **non-null** when a rule measures open equity.

An imported log may legitimately leave them empty -- :data:`nqbt.trades.NULLABLE` -- which is
why their presence is required and their contents only conditionally.
"""


class PropAccountError(ValueError):
    """Raised for a rule set that cannot be replayed, or a log that cannot answer it."""


class TrailBasis(StrEnum):
    """What advances the high-water mark the trailing threshold hangs from."""

    INTRADAY = "intraday"
    """Open equity counts, so a trade's best excursion raises the floor even if it gave it back."""

    END_OF_DAY = "end-of-day"
    """Only the day's closing balance counts, so an intraday spike never raises the floor."""


class EquityBasis(StrEnum):
    """What a limit is measured against."""

    REALISED = "realised"
    """Closed P&L only: the balance after each trade."""

    UNREALISED = "unrealised"
    """Open P&L too: the worst equity reached while each trade was live."""


class TrailLock(StrEnum):
    """Whether the trailing floor stops following the high-water mark, and where."""

    NEVER = "never"
    """The floor follows for the life of the account."""

    AT_STARTING_BALANCE = "at-starting-balance"
    """The floor freezes once it reaches the balance the account opened at."""

    ABOVE_STARTING_BALANCE = "above-starting-balance"
    """The floor freezes a fixed buffer above the opening balance."""


class DailyBreach(StrEnum):
    """What breaching the daily loss limit costs."""

    FAIL = "fail"
    """The account is over, the same as a trailing breach."""

    LOCKOUT = "lockout"
    """The rest of that day's trades are skipped and the account trades on tomorrow."""


class Outcome(StrEnum):
    """How one account's replay ended. Whether it ever *passed* is a separate field."""

    SURVIVED = "survived"
    """The trade log ran out with the account still alive."""

    BREACHED_TRAILING = "breached-trailing"
    """Open equity or a closed balance reached the trailing floor."""

    BREACHED_DAILY_LOSS = "breached-daily-loss"
    """The daily loss limit was reached, under a rule set where that ends the account."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountRules:
    """One firm's risk rules and targets, in dollars.

    A limit of ``0.0`` is off: that is how the trailing threshold, the daily loss limit and the
    consistency ratio are each toggled.
    """

    starting_balance: float
    profit_target: float
    """Profit above the starting balance that passes the evaluation."""

    trailing_threshold: float = 0.0
    """Dollars below the high-water mark the account dies at. ``0.0`` disables trailing."""

    trail_basis: TrailBasis = TrailBasis.END_OF_DAY
    trail_breach: EquityBasis = EquityBasis.UNREALISED
    """Whether the floor is tested against open equity or only against closed balances."""

    trail_lock: TrailLock = TrailLock.NEVER
    trail_lock_buffer: float = 0.0
    """Dollars above the starting balance the floor freezes at, under that lock only."""

    daily_loss_limit: float = 0.0
    """Loss from the day's opening balance that ends the day. ``0.0`` disables it."""

    daily_loss_basis: EquityBasis = EquityBasis.UNREALISED
    on_daily_breach: DailyBreach = DailyBreach.FAIL

    consistency_ratio: float = 0.0
    """Largest share of total profit one day may contribute and still pass. ``0.0`` disables it."""

    minimum_trading_days: int = 0
    withdrawal_threshold: float = 0.0
    """Profit left in the account after a withdrawal -- the safety net a firm requires.

    Set it at or above the locked floor: a withdrawal is not stopped from breaching the account,
    because a rule set that permits one is a rule set under which it would happen.
    """

    def __post_init__(self) -> None:
        """Reject a rule set the replay could not mean anything under."""
        negative: list[str] = [
            f.name for f in dataclasses.fields(self) if _is_negative(getattr(self, f.name))
        ]
        if negative:
            msg: str = f"these must not be negative: {', '.join(negative)}"
            raise PropAccountError(msg)

        if self.starting_balance <= 0.0:
            msg = f"starting_balance must be positive; got {self.starting_balance}"
            raise PropAccountError(msg)

        if self.consistency_ratio > 1.0:
            msg = (
                f"consistency_ratio is a share of total profit and cannot exceed 1.0; got "
                f"{self.consistency_ratio}. Use 0.0 to disable the rule."
            )
            raise PropAccountError(msg)

        self._check_lock()

    def _check_lock(self) -> None:
        """Hold the buffer and the lock it belongs to together, so neither can be set alone."""
        wants_buffer: bool = self.trail_lock is TrailLock.ABOVE_STARTING_BALANCE
        if wants_buffer and self.trail_lock_buffer <= 0.0:
            msg: str = (
                f"{TrailLock.ABOVE_STARTING_BALANCE} needs a positive trail_lock_buffer; got "
                f"{self.trail_lock_buffer}. Use {TrailLock.AT_STARTING_BALANCE} for no buffer."
            )
            raise PropAccountError(msg)

        if not wants_buffer and self.trail_lock_buffer:
            msg = (
                f"trail_lock_buffer is only read under {TrailLock.ABOVE_STARTING_BALANCE}; got "
                f"{self.trail_lock_buffer} under {self.trail_lock}"
            )
            raise PropAccountError(msg)

    @property
    def needs_excursions(self) -> bool:
        """Whether any enabled limit is measured against open equity."""
        trails: bool = self.trailing_threshold > 0.0
        limits_the_day: bool = self.daily_loss_limit > 0.0

        return (
            (trails and self.trail_basis is TrailBasis.INTRADAY)
            or (trails and self.trail_breach is EquityBasis.UNREALISED)
            or (limits_the_day and self.daily_loss_basis is EquityBasis.UNREALISED)
        )


def _is_negative(value: object) -> bool:
    """Whether a field holds a negative number, with bool excluded as it is not a quantity."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountFees:
    """What one attempt costs, in dollars."""

    evaluation_fee: float = 0.0
    """Charged once when the account is opened."""

    monthly_fee: float = 0.0
    """Charged for every calendar month the account is live, the first one included."""

    activation_fee: float = 0.0
    """Charged once, when the account passes."""

    def __post_init__(self) -> None:
        """Reject a negative fee, which would pay the trader to fail."""
        if min(self.evaluation_fee, self.monthly_fee, self.activation_fee) < 0.0:
            msg: str = f"fees cannot be negative; got {self}"
            raise PropAccountError(msg)


@dataclass(frozen=True, slots=True)
class PropAccount:
    """A named rule set and what it costs."""

    name: str
    rules: AccountRules
    fees: AccountFees = AccountFees()


APEX_50K = PropAccount(
    name="Apex 50K",
    rules=AccountRules(
        starting_balance=50_000.0,
        profit_target=3_000.0,
        trailing_threshold=2_500.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
        trail_lock_buffer=100.0,
        consistency_ratio=0.30,
        minimum_trading_days=7,
        withdrawal_threshold=2_600.0,
    ),
    fees=AccountFees(monthly_fee=167.0, activation_fee=130.0),
)

APEX_150K = PropAccount(
    name="Apex 150K",
    rules=AccountRules(
        starting_balance=150_000.0,
        profit_target=9_000.0,
        trailing_threshold=5_000.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
        trail_lock_buffer=100.0,
        consistency_ratio=0.30,
        minimum_trading_days=7,
        withdrawal_threshold=5_100.0,
    ),
    fees=AccountFees(monthly_fee=297.0, activation_fee=130.0),
)

TOPSTEP_50K = PropAccount(
    name="TopStep 50K",
    rules=AccountRules(
        starting_balance=50_000.0,
        profit_target=3_000.0,
        trailing_threshold=2_000.0,
        trail_basis=TrailBasis.END_OF_DAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        daily_loss_limit=1_000.0,
        daily_loss_basis=EquityBasis.UNREALISED,
        on_daily_breach=DailyBreach.FAIL,
        consistency_ratio=0.50,
        minimum_trading_days=2,
        withdrawal_threshold=2_000.0,
    ),
    fees=AccountFees(monthly_fee=49.0, activation_fee=149.0),
)

TOPSTEP_150K = PropAccount(
    name="TopStep 150K",
    rules=AccountRules(
        starting_balance=150_000.0,
        profit_target=9_000.0,
        trailing_threshold=4_500.0,
        trail_basis=TrailBasis.END_OF_DAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        daily_loss_limit=3_300.0,
        daily_loss_basis=EquityBasis.UNREALISED,
        on_daily_breach=DailyBreach.FAIL,
        consistency_ratio=0.50,
        minimum_trading_days=2,
        withdrawal_threshold=4_500.0,
    ),
    fees=AccountFees(monthly_fee=149.0, activation_fee=149.0),
)

PRESETS: dict[str, PropAccount] = {
    account.name: account for account in (APEX_50K, APEX_150K, TOPSTEP_50K, TOPSTEP_150K)
}
"""The two firms at the two commonest sizes.

**Dated, and not quotable terms** -- published rules and prices move, which is why every field
is overridable. Where each number came from, and which are conservative stand-ins rather than
published figures: ``docs/roadmap.md`` § "Replaying a prop account over the trade log".
"""


def preset(name: str) -> PropAccount:
    """Look up a preset by name, case-insensitively."""
    wanted: str = name.strip().casefold()
    for account in PRESETS.values():
        if account.name.casefold() == wanted:
            return account

    msg: str = f"unknown preset {name!r}; known presets: {', '.join(sorted(PRESETS))}"
    raise PropAccountError(msg)


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountRun:
    """What one attempt at an account did.

    :attr:`summary` is the strategy's performance over the trades this account actually took;
    every other field describes the account. The two part company at a breach, where the
    account is liquidated at the floor and the trade log is not.
    """

    outcome: Outcome
    passed: bool
    """Whether the profit target, the minimum days and the consistency rule were all met."""

    first_day: dt.date
    last_day: dt.date
    days_traded: int
    passed_on: dt.date | None
    trades_taken: int
    trades_skipped: int
    """Trades the log held on a locked-out day, which this account never took."""

    locked_out_days: int
    final_balance: float
    peak_balance: float
    """The high-water mark the trailing floor hung from, on this rule set's own basis."""

    lowest_equity: float
    trailing_floor: float
    """Where the floor stood when the account ended. ``-inf`` when trailing is disabled."""

    floor_headroom: float
    """Closest the account came to the floor, in dollars. Negative once it was breached."""

    best_day: float
    worst_day: float
    consistency: float
    """Best day as a share of total profit. ``0.0`` when the account never made any."""

    withdrawn: float
    fees_paid: float
    net: float
    """:attr:`withdrawn` minus :attr:`fees_paid`: what this attempt was worth."""

    summary: stats.Summary

    def as_dict(self) -> dict[str, str | float | int | bool | None]:
        """Flat mapping of the account's own figures, for a report row.

        The performance half is :attr:`summary`, which carries its own ``as_dict``.
        """
        row: dict[str, str | float | int | bool | None] = {
            f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.name != "summary"
        }
        row["outcome"] = str(self.outcome)
        row["first_day"] = self.first_day.isoformat()
        row["last_day"] = self.last_day.isoformat()
        row["passed_on"] = self.passed_on.isoformat() if self.passed_on else None

        return row


@dataclass(frozen=True, slots=True, kw_only=True)
class PropReplay:
    """Every attempt at one rule set over one trade log, and what the sequence was worth."""

    account_name: str
    attempts: int
    passes: int
    pass_rate: float
    breaches: int
    withdrawn: float
    fees_paid: float
    net: float
    """:attr:`withdrawn` minus :attr:`fees_paid`. **The figure the issue exists for**: an
    account may be blown and the sequence still profitable."""

    trades_taken: int
    trades_total: int
    """Trades in the log. Below :attr:`trades_taken` by whatever lockouts and breaches skipped."""

    runs: tuple[AccountRun, ...]
    summary: stats.Summary
    """:func:`nqbt.stats.summarise` over every trade any attempt took."""

    def as_dict(self) -> dict[str, str | float | int]:
        """Flat mapping of the lifetime figures, for a ranking row."""
        return {
            f.name: getattr(self, f.name)
            for f in dataclasses.fields(self)
            if f.name not in ("runs", "summary")
        }


class _TradeTable(NamedTuple):
    """One row per trade, in exit order, with the dollars each rule needs."""

    trade_id: IntArray
    net_pnl: FloatArray
    commission: FloatArray
    adverse: FloatArray
    """Worst open loss while the trade was live, in dollars, before commission."""

    favourable: FloatArray
    """Best open profit while the trade was live, in dollars, before commission."""

    days: DateArray
    """The exchange trading day each trade closed on, one per day rather than per trade."""

    day_starts: IntArray
    """Half-open bounds of each day's trades, plus a closing sentinel."""

    @property
    def n_days(self) -> int:
        """Trading days the log spans."""
        return self.days.size


@dataclass(slots=True)
class _AccountState:
    """The mutable half of one account's replay."""

    balance: float
    high_water: float
    day_open_balance: float
    day_realised: float = 0.0
    withdrawn: float = 0.0
    lowest_equity: float = float("inf")
    floor_headroom: float = float("inf")
    days_traded: int = 0
    locked_out_days: int = 0
    skipped: int = 0
    passed_on: dt.date | None = None
    taken: list[int] = field(default_factory=list)
    daily: list[float] = field(default_factory=list)


class _Attempt(NamedTuple):
    """One account's replay, before it is read off into an :class:`AccountRun`."""

    state: _AccountState
    outcome: Outcome
    first_day: int
    last_day: int
    resume: int
    """Day index the next attempt may open on."""


def replay(log: pd.DataFrame, account: PropAccount, *, max_accounts: int = 1) -> PropReplay:
    """Replay ``account``'s rules over a trade log, one attempt after another.

    ``max_accounts`` of 1 gives a single verdict; higher opens a fresh account on the day after
    each breach, up to that many attempts, and nets the withdrawals against the fees.
    """
    if max_accounts < 1:
        msg: str = f"max_accounts must be at least 1; got {max_accounts}"
        raise PropAccountError(msg)

    table: _TradeTable = _trade_table(log, account.rules)
    runs: list[AccountRun] = []
    taken: list[int] = []
    day: int = 0
    while day < table.n_days and len(runs) < max_accounts:
        attempt: _Attempt = _run_account(table, account, day)
        runs.append(_finish(log, table, account, attempt))
        taken.extend(attempt.state.taken)
        day = attempt.resume

    return _lifetime(log, table, account, tuple(runs), taken)


def _lifetime(
    log: pd.DataFrame,
    table: _TradeTable,
    account: PropAccount,
    runs: tuple[AccountRun, ...],
    taken: list[int],
) -> PropReplay:
    """Total the attempts, and summarise every trade any of them took."""
    passes: int = sum(run.passed for run in runs)
    withdrawn: float = sum(run.withdrawn for run in runs)
    fees_paid: float = sum(run.fees_paid for run in runs)

    return PropReplay(
        account_name=account.name,
        attempts=len(runs),
        passes=passes,
        pass_rate=passes / len(runs) if runs else 0.0,
        breaches=sum(run.outcome is not Outcome.SURVIVED for run in runs),
        withdrawn=withdrawn,
        fees_paid=fees_paid,
        net=withdrawn - fees_paid,
        trades_taken=len(taken),
        trades_total=table.trade_id.size,
        runs=runs,
        summary=stats.summarise(_legs_taken(log, table, taken)),
    )


def _legs_taken(log: pd.DataFrame, table: _TradeTable, positions: list[int]) -> pd.DataFrame:
    """The legs of the trades at ``positions``, so every performance figure is ``summarise``'s."""
    if not positions:
        return log.iloc[:0]

    wanted: IntArray = table.trade_id[np.asarray(positions, dtype=np.int64)]

    return log[log["trade_id"].isin(wanted)]


def _trade_table(log: pd.DataFrame, rules: AccountRules) -> _TradeTable:
    """Collapse a leg-level log into the per-trade, per-day quantities the replay walks."""
    _require_columns(log, rules)
    if log.empty:
        empty_days: DateArray = np.empty(0, dtype="datetime64[D]")

        return _TradeTable(
            trade_id=np.empty(0, dtype=np.int64),
            net_pnl=np.empty(0, dtype=np.float64),
            commission=np.empty(0, dtype=np.float64),
            adverse=np.empty(0, dtype=np.float64),
            favourable=np.empty(0, dtype=np.float64),
            days=empty_days,
            day_starts=np.zeros(1, dtype=np.int64),
        )

    per_trade: pd.DataFrame = stats.per_trade(log).sort_values("exit_time", kind="stable")
    excursions: pd.DataFrame = _excursion_dollars(log, rules).reindex(per_trade.index)
    # The exchange trading day, not the calendar date ``stats.summarise`` groups Sharpe by: a
    # daily loss limit resets at the session open, and the two disagree every evening.
    trading_day: DateArray = sessions.classify(pd.DatetimeIndex(per_trade["exit_time"])).trading_day
    starts: IntArray = _day_starts(trading_day)

    return _TradeTable(
        trade_id=per_trade.index.to_numpy(np.int64),
        net_pnl=per_trade["net_pnl"].to_numpy(np.float64),
        commission=per_trade["commission"].to_numpy(np.float64),
        adverse=excursions["adverse"].to_numpy(np.float64),
        favourable=excursions["favourable"].to_numpy(np.float64),
        days=trading_day[starts[:-1]],
        day_starts=starts,
    )


def _require_columns(log: pd.DataFrame, rules: AccountRules) -> None:
    """Refuse a log that cannot answer this rule set, naming the rule that needed the column."""
    missing: list[str] = [c for c in REQUIRED_COLUMNS if c not in log.columns]
    if missing:
        msg: str = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise PropAccountError(msg)

    if not rules.needs_excursions:
        return

    null: list[str] = [c for c in EXCURSION_COLUMNS if log[c].isna().any()]
    if null:
        msg = (
            f"{null} is null on some legs, and this rule set measures open equity against it. "
            f"Treating a null excursion as zero would report a pass the account never had. Set "
            f"trail_breach and daily_loss_basis to {EquityBasis.REALISED} to replay it on "
            f"closed P&L alone."
        )
        raise PropAccountError(msg)


def _excursion_dollars(log: pd.DataFrame, rules: AccountRules) -> pd.DataFrame:
    """Each trade's worst and best open equity in dollars, summed over its legs.

    Zero on both when no enabled limit reads them, so a log with no excursions still replays.
    """
    index: pd.Index[int] = pd.Index(sorted(set(log["trade_id"])), name="trade_id")
    if not rules.needs_excursions:
        return pd.DataFrame({"adverse": 0.0, "favourable": 0.0}, index=index)

    point_value: FloatArray = _point_values(log)
    quantity: FloatArray = log["quantity"].to_numpy(np.float64)
    # A negative excursion means the trade never went that way at all, which is zero dollars.
    priced: pd.DataFrame = pd.DataFrame(
        {
            "adverse": np.maximum(log["mae_points"].to_numpy(np.float64), 0.0),
            "favourable": np.maximum(log["mfe_points"].to_numpy(np.float64), 0.0),
        },
        index=log.index,
    ).mul(quantity * point_value, axis=0)
    priced["trade_id"] = log["trade_id"].to_numpy(np.int64)

    return priced.groupby("trade_id").sum()


def _point_values(log: pd.DataFrame) -> FloatArray:
    """Dollars per point for each leg's own instrument, since a log may span both roots."""
    per_symbol: dict[str, float] = {
        str(symbol): instruments.get_instrument(str(symbol)).point_value
        for symbol in log["instrument"].unique()
    }

    return np.asarray(log["instrument"].map(per_symbol), dtype=np.float64)


def _day_starts(trading_day: DateArray) -> IntArray:
    """Half-open bounds of each run of equal trading days, plus a closing sentinel."""
    changed: IntArray = np.flatnonzero(trading_day[1:] != trading_day[:-1]) + 1

    return np.concatenate(([0], changed, [trading_day.size])).astype(np.int64)


def _trailing_floor(high_water: float, rules: AccountRules) -> float:
    """Where the account dies, given the highest equity it has reached."""
    if rules.trailing_threshold <= 0.0:
        return float("-inf")

    floor: float = high_water - rules.trailing_threshold
    if rules.trail_lock is TrailLock.NEVER:
        return floor

    return min(floor, rules.starting_balance + rules.trail_lock_buffer)


def _probe_low(balance: float, table: _TradeTable, pos: int, basis: EquityBasis) -> float:
    """Lowest equity one trade reaches, on the basis a rule measures itself against."""
    if basis is EquityBasis.UNREALISED:
        return balance - float(table.adverse[pos]) - float(table.commission[pos])

    return balance + float(table.net_pnl[pos])


def _probe_high(balance: float, table: _TradeTable, pos: int) -> float:
    """Highest equity one trade reaches, which only an intraday high-water mark reads."""
    return balance + float(table.favourable[pos]) - float(table.commission[pos])


def _take_trade(table: _TradeTable, pos: int, rules: AccountRules, state: _AccountState) -> Outcome:
    """Apply one trade to the account and report how it left it.

    The peak is applied before the trough, which is the harsher reading of a bar the data cannot
    order -- ``docs/roadmap.md`` § "Replaying a prop account over the trade log".
    """
    if rules.trail_basis is TrailBasis.INTRADAY:
        state.high_water = max(state.high_water, _probe_high(state.balance, table, pos))

    floor: float = _trailing_floor(state.high_water, rules)
    trail_low: float = _probe_low(state.balance, table, pos, rules.trail_breach)
    state.lowest_equity = min(state.lowest_equity, trail_low)
    state.floor_headroom = min(state.floor_headroom, trail_low - floor)
    state.taken.append(pos)
    if trail_low <= floor:
        state.balance = trail_low

        return Outcome.BREACHED_TRAILING

    daily_low: float = _probe_low(state.balance, table, pos, rules.daily_loss_basis)
    realised: float = float(table.net_pnl[pos])
    state.balance += realised
    state.day_realised += realised

    limit: float = rules.daily_loss_limit
    if limit <= 0.0 or daily_low > state.day_open_balance - limit:
        return Outcome.SURVIVED

    if rules.on_daily_breach is DailyBreach.FAIL:
        state.balance = daily_low

    return Outcome.BREACHED_DAILY_LOSS


def _trade_one_day(
    table: _TradeTable,
    day: int,
    rules: AccountRules,
    state: _AccountState,
) -> Outcome:
    """Walk one trading day's trades, record the day, then close it if the account survived.

    The day is recorded either way, so an account that died on its only day does not report
    having traded on none.
    """
    state.day_open_balance = state.balance
    state.day_realised = 0.0

    outcome: Outcome = _walk_day(table, day, rules, state)
    state.days_traded += 1
    state.daily.append(state.day_realised)
    if outcome is not Outcome.SURVIVED:
        return outcome

    return _close_day(table, day, rules, state)


def _walk_day(table: _TradeTable, day: int, rules: AccountRules, state: _AccountState) -> Outcome:
    """Take one day's trades in order, stopping at whatever ends the day or the account."""
    end: int = int(table.day_starts[day + 1])
    for pos in range(int(table.day_starts[day]), end):
        outcome: Outcome = _take_trade(table, pos, rules, state)
        if outcome is Outcome.SURVIVED:
            continue

        if outcome is Outcome.BREACHED_TRAILING or rules.on_daily_breach is DailyBreach.FAIL:
            return outcome

        state.locked_out_days += 1
        state.skipped += end - pos - 1
        break

    return Outcome.SURVIVED


def _close_day(table: _TradeTable, day: int, rules: AccountRules, state: _AccountState) -> Outcome:
    """Advance the high-water mark, then test the pass and take any withdrawal due.

    The floor needs no second test here: a trade's own probe is never above the balance it
    leaves behind, so the closing balance cannot breach a floor the day's trades did not.
    """
    if rules.trail_basis is TrailBasis.END_OF_DAY:
        state.high_water = max(state.high_water, state.balance)

    _check_pass(table, day, rules, state)
    _withdraw(rules, state)

    return Outcome.SURVIVED


def _check_pass(table: _TradeTable, day: int, rules: AccountRules, state: _AccountState) -> None:
    """Record the day the account met every condition for a pass, once."""
    if state.passed_on is not None:
        return

    profit: float = state.balance - rules.starting_balance
    if profit < rules.profit_target:
        return

    if state.days_traded < rules.minimum_trading_days:
        return

    if not _consistent(state.daily, profit, rules.consistency_ratio):
        return

    state.passed_on = _as_date(table.days[day])


def _as_date(day: np.datetime64[dt.date | int | None]) -> dt.date:
    """One trading day as the calendar date a report prints."""
    return pd.Timestamp(day).date()


def _consistent(daily: list[float], profit: float, ratio: float) -> bool:
    """Whether no single day contributed more than ``ratio`` of the account's total profit."""
    if ratio <= 0.0:
        return True

    if profit <= 0.0:
        return False

    return max(daily) <= ratio * profit


def _withdraw(rules: AccountRules, state: _AccountState) -> None:
    """Take everything above the safety net, once the account has passed."""
    if state.passed_on is None:
        return

    excess: float = state.balance - rules.starting_balance - rules.withdrawal_threshold
    if excess <= 0.0:
        return

    state.balance -= excess
    state.withdrawn += excess


def _run_account(table: _TradeTable, account: PropAccount, first_day: int) -> _Attempt:
    """Replay one attempt from ``first_day``, and report the day the next one may open on."""
    rules: AccountRules = account.rules
    state = _AccountState(
        balance=rules.starting_balance,
        high_water=rules.starting_balance,
        day_open_balance=rules.starting_balance,
    )

    outcome: Outcome = Outcome.SURVIVED
    last_day: int = first_day
    for day in range(first_day, table.n_days):
        last_day = day
        outcome = _trade_one_day(table, day, rules, state)
        if outcome is not Outcome.SURVIVED:
            break

    resume: int = table.n_days if outcome is Outcome.SURVIVED else last_day + 1

    return _Attempt(state, outcome, first_day, last_day, resume)


def _finish(
    log: pd.DataFrame,
    table: _TradeTable,
    account: PropAccount,
    attempt: _Attempt,
) -> AccountRun:
    """Read the account's figures off the state it ended in."""
    rules: AccountRules = account.rules
    state: _AccountState = attempt.state
    opened: dt.date = _as_date(table.days[attempt.first_day])
    closed: dt.date = _as_date(table.days[attempt.last_day])
    fees: float = _fees_paid(account.fees, opened, closed, passed=state.passed_on is not None)
    profit: float = state.balance + state.withdrawn - rules.starting_balance

    return AccountRun(
        outcome=attempt.outcome,
        passed=state.passed_on is not None,
        first_day=opened,
        last_day=closed,
        days_traded=state.days_traded,
        passed_on=state.passed_on,
        trades_taken=len(state.taken),
        trades_skipped=state.skipped,
        locked_out_days=state.locked_out_days,
        final_balance=state.balance,
        peak_balance=state.high_water,
        lowest_equity=state.lowest_equity if state.taken else rules.starting_balance,
        trailing_floor=_trailing_floor(state.high_water, rules),
        floor_headroom=state.floor_headroom if state.taken else float("inf"),
        best_day=max(state.daily) if state.daily else 0.0,
        worst_day=min(state.daily) if state.daily else 0.0,
        consistency=(max(state.daily) / profit) if state.daily and profit > 0.0 else 0.0,
        withdrawn=state.withdrawn,
        fees_paid=fees,
        net=state.withdrawn - fees,
        summary=stats.summarise(_legs_taken(log, table, state.taken)),
    )


def _fees_paid(fees: AccountFees, opened: dt.date, closed: dt.date, *, passed: bool) -> float:
    """One attempt's cost: the entry fee, a month for every month it was live, and activation."""
    months: int = (closed.year - opened.year) * 12 + closed.month - opened.month + 1
    total: float = fees.evaluation_fee + fees.monthly_fee * months
    if not passed:
        return total

    return total + fees.activation_fee
