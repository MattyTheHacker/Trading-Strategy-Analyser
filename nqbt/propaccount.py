"""Replaying a prop-firm account's rules over a trade log.

Every figure describing *the trades* comes from :func:`nqbt.stats.summarise`; this module owns
the figures describing *the account*. Open equity is priced from each leg's ``mae_points`` and
``mfe_points`` through :mod:`nqbt.instruments`. The presets' sources, the assumptions bar data
cannot decide, and what is not modelled: ``docs/roadmap.md`` § "Replaying a prop account over
the trade log".
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

from nqbt import instruments, sessions, stats

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from nqbt.arrays import DateArray, FloatArray, IntArray

__all__ = [
    "APEX_50K_EOD",
    "APEX_50K_INTRADAY",
    "APEX_150K_EOD",
    "APEX_150K_INTRADAY",
    "APEX_LOCK_BUFFER",
    "EXCURSION_COLUMNS",
    "LINKED_PRESETS",
    "LUCIDDAILY_50K",
    "LUCIDDAILY_150K",
    "LUCIDFLEX_50K",
    "LUCIDFLEX_150K",
    "LUCIDPRO_50K",
    "LUCIDPRO_150K",
    "LUCID_LOCK_BUFFER",
    "PRESETS",
    "REQUIRED_COLUMNS",
    "SIZE_TOLERANCE",
    "TOPSTEP_50K",
    "TOPSTEP_150K",
    "TPT_25K",
    "TPT_25K_PRO",
    "TPT_25K_TEST",
    "TPT_50K",
    "TPT_50K_PRO",
    "TPT_50K_TEST",
    "TPT_150K",
    "TPT_150K_PRO",
    "TPT_150K_TEST",
    "Account",
    "AccountFees",
    "AccountRules",
    "AccountRun",
    "Charge",
    "DailyBreach",
    "EquityBasis",
    "ExcursionOrder",
    "FeeKind",
    "LinkedAccount",
    "Outcome",
    "PropAccount",
    "PropAccountError",
    "PropReplay",
    "ScalingTier",
    "TrailBasis",
    "TrailLock",
    "Withdrawal",
    "account_named",
    "evaluation_of",
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
"""Columns that must also be **non-null** when a rule measures open equity; an imported log may
leave them empty -- :data:`nqbt.trades.NULLABLE`.
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


class ExcursionOrder(StrEnum):
    """Which of one trade's two excursions is applied first, where bar data cannot say.

    Read only under :attr:`TrailBasis.INTRADAY`, the only basis a trade's own peak can move the
    floor under -- ``docs/roadmap.md`` §M28.13.
    """

    PEAK_FIRST = "peak-first"
    """The favourable excursion raises the floor before the adverse one is tested against it.

    The harsher reading, and the default.
    """

    TROUGH_FIRST = "trough-first"
    """The adverse excursion is tested against the floor the trade opened with.

    The peak is still recorded afterwards, so it moves the floor for every later trade.
    """


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

    PROMOTED = "promoted"
    """The evaluation passed and closed, for the funded account a :class:`LinkedAccount` opens."""

    EXPIRED = "expired"
    """The evaluation did not pass within the calendar days its firm allows."""

    MOVED_LIVE = "moved-live"
    """The account reached its firm's limit on payouts or on one day's profit, and the firm closed
    it or moved it to a live account the replay does not follow."""


_BREACHES = frozenset({Outcome.BREACHED_TRAILING, Outcome.BREACHED_DAILY_LOSS})
"""The outcomes that end an attempt by breaking a rule."""

SIZE_TOLERANCE = 1e-9
"""How far over a size limit a trade may sit and still be taken, for a micro's float share."""


class ScalingTier(NamedTuple):
    """One rung of a scaling plan: the size limit from a level of profit upward."""

    from_profit: float
    """Profit above the starting balance, at the session's open, the rung starts at."""

    contracts: float
    """Largest position, in full-size contracts."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountRules:
    """One firm's risk rules and targets, in dollars.

    A limit of ``0.0`` is off: that is how the trailing threshold, the daily loss limit and the
    consistency ratio are each toggled. :attr:`profit_split` is the exception -- a firm that
    paid nothing would be ``0.0``, so its "no rule" value is ``1.0``.
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

    excursion_order: ExcursionOrder = ExcursionOrder.PEAK_FIRST
    """Which of a trade's excursions moves the floor first, under an intraday basis --
    ``docs/roadmap.md`` §M28.13.
    """

    daily_loss_limit: float = 0.0
    """Loss from the day's opening balance that ends the day. ``0.0`` disables it."""

    daily_loss_basis: EquityBasis = EquityBasis.UNREALISED
    on_daily_breach: DailyBreach = DailyBreach.FAIL

    consistency_ratio: float = 0.0
    """Largest share of total profit one day may contribute and still pass. ``0.0`` disables it."""

    minimum_trading_days: int = 0
    withdrawal_threshold: float = 0.0
    """Profit left in the account after a withdrawal -- the safety net a firm requires.

    Set it at or above the locked floor: nothing stops a withdrawal from breaching the account.
    """

    profit_split: float = 1.0
    """The trader's share of each withdrawal. ``1.0`` is no split at all.

    The account still gives up the whole withdrawal: :attr:`AccountRun.withdrawn` is what left
    it and :attr:`AccountRun.payout` what reached the trader.
    """

    evaluation_days: int = 0
    """Calendar days an account has to pass, counted from the day it opens. ``0`` disables it."""

    max_contracts: float = 0.0
    """Largest position a trade may put on, in full-size contracts. ``0.0`` disables it.

    A micro counts as its instrument's ``mini_equivalent``, and a trade over the limit is
    rejected rather than taken.
    """

    scaling_plan: tuple[ScalingTier, ...] = ()
    """A size limit that rises with the profit each session opens on.

    The first rung starts at zero and also covers a loss; the lower of this and
    :attr:`max_contracts` binds.
    """

    payout_days: int = 0
    """Trading days a payout needs since the last one. ``0`` disables it."""

    payout_day_profit: float = 0.0
    """What a day must make to count toward :attr:`payout_days`. ``0.0`` counts every day traded."""

    payout_consistency: float = 0.0
    """Largest share of the profit since the last payout one day may contribute. ``0.0`` disables it."""

    payout_profit_goal: float = 0.0
    """Profit a payout needs since the last one. ``0.0`` disables it."""

    payout_share: float = 1.0
    """Largest share of the profit above the starting balance one payout may take."""

    payout_cap: float = 0.0
    """Largest single payout. ``0.0`` disables it."""

    payout_minimum: float = 0.0
    """Smallest payout the firm pays; anything less waits. ``0.0`` disables it."""

    floor_locks_at_payout: bool = False
    """Whether the first payout moves the floor straight to where :attr:`trail_lock` locks it."""

    max_payouts: int = 0
    """Payouts after which the account moves to a live one. ``0`` disables it."""

    daily_profit_cap: float = 0.0
    """One day's profit that moves the account to a live one. ``0.0`` disables it."""

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

        for name in ("consistency_ratio", "payout_consistency"):
            if getattr(self, name) > 1.0:
                msg = (
                    f"{name} is a share of profit and cannot exceed 1.0; got {getattr(self, name)}. "
                    f"Use 0.0 to disable the rule."
                )
                raise PropAccountError(msg)

        for name, no_rule in (("profit_split", "no split"), ("payout_share", "no limit")):
            if not 0.0 < getattr(self, name) <= 1.0:
                msg = (
                    f"{name} is a share and must be above 0.0 and at most 1.0; got "
                    f"{getattr(self, name)}. Use 1.0 for {no_rule}."
                )
                raise PropAccountError(msg)

        self._check_lock()
        self._check_scaling_plan()

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

        locks: bool = self.trailing_threshold > 0.0 and self.trail_lock is not TrailLock.NEVER
        if self.floor_locks_at_payout and not locks:
            msg = (
                f"floor_locks_at_payout moves the floor to where trail_lock locks it, so it needs "
                f"a trailing threshold and a lock; got {self.trailing_threshold} under {self.trail_lock}"
            )
            raise PropAccountError(msg)

    def _check_scaling_plan(self) -> None:
        """Hold a scaling plan to rungs that start at zero, rise in profit and allow a position."""
        if not self.scaling_plan:
            return

        starts: list[float] = [tier.from_profit for tier in self.scaling_plan]
        if starts[0] != 0.0 or any(later <= earlier for earlier, later in itertools.pairwise(starts)):
            msg: str = f"scaling_plan's rungs must start at 0.0 and rise in profit; got {starts}"
            raise PropAccountError(msg)

        if any(tier.contracts <= 0.0 for tier in self.scaling_plan):
            msg = f"every scaling_plan rung must allow a position; got {self.scaling_plan}"
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

    @property
    def limits_size(self) -> bool:
        """Whether a size limit or a scaling plan can reject a trade."""
        return self.max_contracts > 0.0 or bool(self.scaling_plan)


def _is_negative(value: object) -> bool:
    """Return whether a field holds a negative number, with bool excluded as it is not a quantity."""
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

    monthly_fee_ends_at_pass: bool = False
    """Whether the monthly fee stops on the day the account passes.

    True for a firm charging for the evaluation and nothing afterwards, false for one whose
    funded account carries the same subscription.
    """

    def __post_init__(self) -> None:
        """Reject a negative fee, which would pay the trader to fail."""
        if min(self.evaluation_fee, self.monthly_fee, self.activation_fee) < 0.0:
            msg: str = f"fees cannot be negative; got {self}"
            raise PropAccountError(msg)


class FeeKind(StrEnum):
    """Which of :class:`AccountFees`' fees a charge was."""

    EVALUATION = "evaluation"
    MONTHLY = "monthly"
    ACTIVATION = "activation"


class Charge(NamedTuple):
    """One fee, on the day it was charged."""

    day: dt.date
    amount: float
    kind: FeeKind


class Withdrawal(NamedTuple):
    """One withdrawal, on the trading day it was taken."""

    day: dt.date
    withdrawn: float
    """Taken out of the account, before the firm's split."""

    payout: float
    """What reached the trader."""


@dataclass(frozen=True, slots=True)
class PropAccount:
    """A named rule set and what it costs."""

    name: str
    rules: AccountRules
    fees: AccountFees = AccountFees()


@dataclass(frozen=True, slots=True)
class LinkedAccount:
    """An evaluation and the funded account its pass opens, replayed as one sequence.

    Each keeps its own rule set -- ``docs/roadmap.md`` § "A firm that changes its rules at the
    pass ships as two presets".
    """

    name: str
    evaluation: PropAccount
    funded: PropAccount

    def __post_init__(self) -> None:
        """Refuse a pair the replay could not tell apart or would charge wrongly at the hand-over."""
        if self.evaluation.name == self.funded.name:
            msg: str = (
                f"the two accounts of {self.name!r} need different names; both are {self.funded.name!r}"
            )
            raise PropAccountError(msg)

        if self.evaluation.fees.activation_fee != self.funded.fees.evaluation_fee:
            msg = (
                f"{self.name!r} charges the evaluation's activation fee as the funded account's "
                f"opening fee, once; got {self.evaluation.fees.activation_fee} and "
                f"{self.funded.fees.evaluation_fee}"
            )
            raise PropAccountError(msg)

    @property
    def opened_by_pass(self) -> PropAccount:
        """The funded account as a pass opens it, its opening fee already charged as the activation."""
        fees: AccountFees = dataclasses.replace(self.funded.fees, evaluation_fee=0.0)

        return dataclasses.replace(self.funded, fees=fees)


type Account = PropAccount | LinkedAccount
"""Anything :func:`replay` replays."""


APEX_LOCK_BUFFER = 100.0
"""Dollars above the starting balance an Apex floor locks at, and that its safety net adds."""


class _ApexSize(NamedTuple):
    """The figures one Apex account size sets, whichever trail it is bought with."""

    balance: float
    target: float
    drawdown: float
    evaluation_contracts: float
    evaluation_daily_loss: float
    """The end-of-day evaluation's daily loss limit; the intraday one has none."""

    scaling_plan: tuple[ScalingTier, ...]
    funded_daily_loss: float
    payout_cap: float


def _apex(
    size: _ApexSize, basis: TrailBasis, *, fee: float, activation: float, day_profit: float
) -> LinkedAccount:
    """Build Apex's evaluation and the Performance Account its pass opens, at one size and trail."""
    end_of_day: bool = basis is TrailBasis.END_OF_DAY
    name: str = f"Apex {size.balance / 1_000:.0f}K {'EOD' if end_of_day else 'Intraday'}"
    trail: AccountRules = AccountRules(
        starting_balance=size.balance,
        profit_target=0.0,
        trailing_threshold=size.drawdown,
        trail_basis=basis,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
        trail_lock_buffer=APEX_LOCK_BUFFER,
        daily_loss_basis=EquityBasis.UNREALISED,
        on_daily_breach=DailyBreach.LOCKOUT,
        withdrawal_threshold=size.drawdown + APEX_LOCK_BUFFER,
    )
    evaluation: PropAccount = PropAccount(
        name=f"{name} Evaluation",
        rules=dataclasses.replace(
            trail,
            profit_target=size.target,
            daily_loss_limit=size.evaluation_daily_loss if end_of_day else 0.0,
            max_contracts=size.evaluation_contracts,
            evaluation_days=30,
        ),
        fees=AccountFees(evaluation_fee=fee, activation_fee=activation),
    )
    performance: PropAccount = PropAccount(
        name=f"{name} PA",
        rules=dataclasses.replace(
            trail,
            daily_loss_limit=size.funded_daily_loss,
            max_contracts=size.scaling_plan[-1].contracts,
            scaling_plan=size.scaling_plan,
            payout_days=5,
            payout_day_profit=day_profit,
            payout_consistency=0.50,
            payout_cap=size.payout_cap,
            payout_minimum=500.0,
            max_payouts=6,
        ),
        fees=AccountFees(evaluation_fee=activation),
    )

    return LinkedAccount(name=f"{name} Evaluation+PA", evaluation=evaluation, funded=performance)


_APEX_50K_SIZE = _ApexSize(
    balance=50_000.0,
    target=3_000.0,
    drawdown=2_000.0,
    evaluation_contracts=6.0,
    evaluation_daily_loss=1_000.0,
    scaling_plan=(ScalingTier(0.0, 2.0), ScalingTier(1_500.0, 3.0), ScalingTier(3_000.0, 4.0)),
    funded_daily_loss=1_000.0,
    payout_cap=1_500.0,
)

_APEX_150K_SIZE = _ApexSize(
    balance=150_000.0,
    target=9_000.0,
    drawdown=4_000.0,
    evaluation_contracts=12.0,
    evaluation_daily_loss=2_000.0,
    scaling_plan=(
        ScalingTier(0.0, 4.0),
        ScalingTier(2_000.0, 5.0),
        ScalingTier(3_000.0, 7.0),
        ScalingTier(5_000.0, 10.0),
    ),
    funded_daily_loss=2_500.0,
    payout_cap=2_500.0,
)

APEX_50K_EOD = _apex(_APEX_50K_SIZE, TrailBasis.END_OF_DAY, fee=47.20, activation=129.0, day_profit=250.0)
APEX_50K_INTRADAY = _apex(_APEX_50K_SIZE, TrailBasis.INTRADAY, fee=19.92, activation=99.0, day_profit=200.0)
APEX_150K_EOD = _apex(_APEX_150K_SIZE, TrailBasis.END_OF_DAY, fee=175.20, activation=159.0, day_profit=350.0)
APEX_150K_INTRADAY = _apex(
    _APEX_150K_SIZE, TrailBasis.INTRADAY, fee=95.20, activation=149.0, day_profit=300.0
)


def _topstep(
    balance: float,
    *,
    target: float,
    drawdown: float,
    monthly_fee: float,
    contracts: float,
    scaling_plan: tuple[ScalingTier, ...],
    payout_cap: float,
) -> LinkedAccount:
    """Build TopStep's Trading Combine and the Express Funded Account its pass opens, at one size."""
    size: str = f"TopStep {balance / 1_000:.0f}K"
    combine: PropAccount = PropAccount(
        name=f"{size} Combine",
        rules=AccountRules(
            starting_balance=balance,
            profit_target=target,
            trailing_threshold=drawdown,
            trail_basis=TrailBasis.END_OF_DAY,
            trail_breach=EquityBasis.UNREALISED,
            trail_lock=TrailLock.AT_STARTING_BALANCE,
            consistency_ratio=0.55,
            minimum_trading_days=2,
            withdrawal_threshold=drawdown,
            profit_split=0.90,
            max_contracts=contracts,
        ),
        fees=AccountFees(monthly_fee=monthly_fee, activation_fee=149.0, monthly_fee_ends_at_pass=True),
    )
    express: PropAccount = PropAccount(
        name=f"{size} XFA",
        rules=AccountRules(
            starting_balance=balance,
            profit_target=0.0,
            trailing_threshold=drawdown,
            trail_basis=TrailBasis.END_OF_DAY,
            trail_breach=EquityBasis.UNREALISED,
            trail_lock=TrailLock.AT_STARTING_BALANCE,
            profit_split=0.90,
            max_contracts=contracts,
            scaling_plan=scaling_plan,
            payout_days=5,
            payout_day_profit=150.0,
            payout_profit_goal=0.01,
            payout_share=0.50,
            payout_cap=payout_cap,
            payout_minimum=125.0,
            floor_locks_at_payout=True,
        ),
        fees=AccountFees(evaluation_fee=149.0),
    )

    return LinkedAccount(name=f"{size} Combine+XFA", evaluation=combine, funded=express)


TOPSTEP_50K = _topstep(
    50_000.0,
    target=3_000.0,
    drawdown=2_000.0,
    monthly_fee=49.0,
    contracts=5.0,
    scaling_plan=(ScalingTier(0.0, 2.0), ScalingTier(1_500.0, 3.0), ScalingTier(2_000.0, 5.0)),
    payout_cap=2_000.0,
)

TOPSTEP_150K = _topstep(
    150_000.0,
    target=9_000.0,
    drawdown=4_500.0,
    monthly_fee=199.0,
    contracts=15.0,
    scaling_plan=(
        ScalingTier(0.0, 3.0),
        ScalingTier(1_500.0, 4.0),
        ScalingTier(2_000.0, 5.0),
        ScalingTier(3_000.0, 10.0),
        ScalingTier(4_500.0, 15.0),
    ),
    payout_cap=5_000.0,
)


LUCID_LOCK_BUFFER = 100.0
"""Dollars above the starting balance every Lucid floor locks at, and that its buffer adds."""


def _lucid_rules(
    balance: float,
    drawdown: float,
    contracts: float,
    *,
    basis: TrailBasis = TrailBasis.END_OF_DAY,
) -> AccountRules:
    """Return the drawdown, split and size every Lucid account shares, before its own rules."""
    return AccountRules(
        starting_balance=balance,
        profit_target=0.0,
        trailing_threshold=drawdown,
        trail_basis=basis,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
        trail_lock_buffer=LUCID_LOCK_BUFFER,
        profit_split=0.90,
        max_contracts=contracts,
    )


def _lucid_evaluation(
    plan: str,
    balance: float,
    *,
    target: float,
    drawdown: float,
    contracts: float,
    consistency: float,
    fee: float,
) -> PropAccount:
    """Build one Lucid evaluation, which charges once and nothing to activate."""
    rules: AccountRules = dataclasses.replace(
        _lucid_rules(balance, drawdown, contracts),
        profit_target=target,
        consistency_ratio=consistency,
        withdrawal_threshold=drawdown + LUCID_LOCK_BUFFER,
    )

    return PropAccount(
        name=f"{plan} {balance / 1_000:.0f}K Evaluation", rules=rules, fees=AccountFees(evaluation_fee=fee)
    )


def _lucid_pair(evaluation: PropAccount, funded: AccountRules) -> LinkedAccount:
    """Link a Lucid evaluation to the funded account its pass opens."""
    size: str = evaluation.name.removesuffix(" Evaluation")
    held: PropAccount = PropAccount(name=f"{size} Funded", rules=funded)

    return LinkedAccount(name=f"{size} Evaluation+Funded", evaluation=evaluation, funded=held)


def _lucidpro(
    balance: float,
    *,
    target: float,
    drawdown: float,
    contracts: float,
    fee: float,
    profit_goal: float,
    payout_cap: float,
) -> LinkedAccount:
    """Build LucidPro: a buffer, a per-cycle profit goal and 40% consistency at each payout."""
    evaluation: PropAccount = _lucid_evaluation(
        "LucidPro", balance, target=target, drawdown=drawdown, contracts=contracts, consistency=0.0, fee=fee
    )
    funded: AccountRules = dataclasses.replace(
        _lucid_rules(balance, drawdown, contracts),
        withdrawal_threshold=drawdown + LUCID_LOCK_BUFFER,
        payout_consistency=0.40,
        payout_profit_goal=profit_goal,
        payout_cap=payout_cap,
        payout_minimum=500.0,
    )

    return _lucid_pair(evaluation, funded)


def _lucidflex(
    balance: float,
    *,
    target: float,
    drawdown: float,
    contracts: float,
    fee: float,
    scaling_plan: tuple[ScalingTier, ...],
    day_profit: float,
    payout_cap: float,
) -> LinkedAccount:
    """Build LucidFlex: no buffer, half the profit per payout, and five payouts before live."""
    evaluation: PropAccount = _lucid_evaluation(
        "LucidFlex", balance, target=target, drawdown=drawdown, contracts=contracts, consistency=0.50, fee=fee
    )
    funded: AccountRules = dataclasses.replace(
        _lucid_rules(balance, drawdown, contracts),
        scaling_plan=scaling_plan,
        payout_days=5,
        payout_day_profit=day_profit,
        payout_profit_goal=0.01,
        payout_share=0.50,
        payout_cap=payout_cap,
        payout_minimum=500.0,
        floor_locks_at_payout=True,
        max_payouts=5,
    )

    return _lucid_pair(evaluation, funded)


def _luciddaily(
    balance: float,
    *,
    target: float,
    drawdown: float,
    contracts: float,
    fee: float,
    daily_profit_cap: float,
) -> LinkedAccount:
    """Build LucidDaily: an intraday floor once funded, a payout any day, and a daily profit cap."""
    evaluation: PropAccount = _lucid_evaluation(
        "LucidDaily",
        balance,
        target=target,
        drawdown=drawdown,
        contracts=contracts,
        consistency=0.50,
        fee=fee,
    )
    funded: AccountRules = dataclasses.replace(
        _lucid_rules(balance, drawdown, contracts, basis=TrailBasis.INTRADAY),
        withdrawal_threshold=drawdown + LUCID_LOCK_BUFFER,
        payout_profit_goal=0.01,
        payout_minimum=500.0,
        daily_profit_cap=daily_profit_cap,
    )

    return _lucid_pair(evaluation, funded)


LUCIDPRO_50K = _lucidpro(
    50_000.0,
    target=3_000.0,
    drawdown=2_000.0,
    contracts=4.0,
    fee=140.40,
    profit_goal=500.0,
    payout_cap=2_000.0,
)
LUCIDPRO_150K = _lucidpro(
    150_000.0,
    target=9_000.0,
    drawdown=4_500.0,
    contracts=10.0,
    fee=300.50,
    profit_goal=1_000.0,
    payout_cap=3_000.0,
)
LUCIDFLEX_50K = _lucidflex(
    50_000.0,
    target=3_000.0,
    drawdown=2_000.0,
    contracts=4.0,
    fee=105.20,
    scaling_plan=(ScalingTier(0.0, 2.0), ScalingTier(1_000.0, 3.0), ScalingTier(2_000.0, 4.0)),
    day_profit=150.0,
    payout_cap=2_000.0,
)
LUCIDFLEX_150K = _lucidflex(
    150_000.0,
    target=9_000.0,
    drawdown=4_500.0,
    contracts=10.0,
    fee=295.40,
    scaling_plan=(
        ScalingTier(0.0, 4.0),
        ScalingTier(1_000.0, 5.0),
        ScalingTier(2_000.0, 6.0),
        ScalingTier(3_000.0, 8.0),
        ScalingTier(4_500.0, 10.0),
    ),
    day_profit=250.0,
    payout_cap=3_000.0,
)
LUCIDDAILY_50K = _luciddaily(
    50_000.0, target=3_000.0, drawdown=2_000.0, contracts=4.0, fee=125.20, daily_profit_cap=8_000.0
)
LUCIDDAILY_150K = _luciddaily(
    150_000.0, target=9_000.0, drawdown=4_500.0, contracts=10.0, fee=280.50, daily_profit_cap=12_000.0
)

TPT_25K_TEST = PropAccount(
    name="TakeProfitTrader 25K Test",
    rules=AccountRules(
        starting_balance=25_000.0,
        profit_target=1_500.0,
        trailing_threshold=1_500.0,
        trail_basis=TrailBasis.END_OF_DAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        consistency_ratio=0.50,
        minimum_trading_days=3,
        withdrawal_threshold=1_500.0,
        profit_split=0.80,
    ),
    fees=AccountFees(monthly_fee=90.0, activation_fee=130.0, monthly_fee_ends_at_pass=True),
)

TPT_25K_PRO = PropAccount(
    name="TakeProfitTrader 25K PRO",
    rules=AccountRules(
        starting_balance=25_000.0,
        profit_target=0.0,
        trailing_threshold=1_500.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        withdrawal_threshold=1_500.0,
        profit_split=0.80,
    ),
    fees=AccountFees(evaluation_fee=130.0),
)

TPT_50K_TEST = PropAccount(
    name="TakeProfitTrader 50K Test",
    rules=AccountRules(
        starting_balance=50_000.0,
        profit_target=3_000.0,
        trailing_threshold=2_000.0,
        trail_basis=TrailBasis.END_OF_DAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        consistency_ratio=0.50,
        minimum_trading_days=3,
        withdrawal_threshold=2_000.0,
        profit_split=0.80,
    ),
    fees=AccountFees(monthly_fee=102.0, activation_fee=130.0, monthly_fee_ends_at_pass=True),
)

TPT_50K_PRO = PropAccount(
    name="TakeProfitTrader 50K PRO",
    rules=AccountRules(
        starting_balance=50_000.0,
        profit_target=0.0,
        trailing_threshold=2_000.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        withdrawal_threshold=2_000.0,
        profit_split=0.80,
    ),
    fees=AccountFees(evaluation_fee=130.0),
)

TPT_150K_TEST = PropAccount(
    name="TakeProfitTrader 150K Test",
    rules=AccountRules(
        starting_balance=150_000.0,
        profit_target=9_000.0,
        trailing_threshold=4_500.0,
        trail_basis=TrailBasis.END_OF_DAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        consistency_ratio=0.50,
        minimum_trading_days=3,
        withdrawal_threshold=4_500.0,
        profit_split=0.80,
    ),
    fees=AccountFees(monthly_fee=216.0, activation_fee=130.0, monthly_fee_ends_at_pass=True),
)

TPT_150K_PRO = PropAccount(
    name="TakeProfitTrader 150K PRO",
    rules=AccountRules(
        starting_balance=150_000.0,
        profit_target=0.0,
        trailing_threshold=4_500.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        withdrawal_threshold=4_500.0,
        profit_split=0.80,
    ),
    fees=AccountFees(evaluation_fee=130.0),
)

TPT_25K = LinkedAccount(name="TakeProfitTrader 25K Test+PRO", evaluation=TPT_25K_TEST, funded=TPT_25K_PRO)
TPT_50K = LinkedAccount(name="TakeProfitTrader 50K Test+PRO", evaluation=TPT_50K_TEST, funded=TPT_50K_PRO)
TPT_150K = LinkedAccount(name="TakeProfitTrader 150K Test+PRO", evaluation=TPT_150K_TEST, funded=TPT_150K_PRO)

LINKED_PRESETS: dict[str, LinkedAccount] = {
    linked.name: linked
    for linked in (
        APEX_50K_EOD,
        APEX_50K_INTRADAY,
        APEX_150K_EOD,
        APEX_150K_INTRADAY,
        TOPSTEP_50K,
        TOPSTEP_150K,
        LUCIDPRO_50K,
        LUCIDPRO_150K,
        LUCIDFLEX_50K,
        LUCIDFLEX_150K,
        LUCIDDAILY_50K,
        LUCIDDAILY_150K,
        TPT_25K,
        TPT_50K,
        TPT_150K,
    )
}
"""Each firm's evaluation chained to the funded account its pass opens, at each size it ships."""

PRESETS: dict[str, PropAccount] = {
    account.name: account
    for linked in LINKED_PRESETS.values()
    for account in (linked.evaluation, linked.funded)
}
"""Every evaluation and funded account on its own, for replaying one phase alone.

Dated, and not quotable terms. Where each number came from: ``docs/roadmap.md`` § "Where the
preset numbers came from".
"""


def preset(name: str) -> PropAccount:
    """Look up a preset by name, case-insensitively."""
    return _named(name, PRESETS)


def account_named(name: str) -> Account:
    """Look up a preset or a linked pair by name, case-insensitively."""
    known: dict[str, Account] = {**PRESETS, **LINKED_PRESETS}

    return _named(name, known)


def _named[A: PropAccount | LinkedAccount](name: str, known: Mapping[str, A]) -> A:
    """Return the account in ``known`` called ``name``, ignoring case, or refuse naming every one."""
    wanted: str = name.strip().casefold()
    for account in known.values():
        if account.name.casefold() == wanted:
            return account

    msg: str = f"unknown preset {name!r}; known presets: {', '.join(sorted(known))}"
    raise PropAccountError(msg)


def evaluation_of(account: Account) -> PropAccount:
    """Return the account an attempt is bought as: a linked pair's evaluation, or the preset itself."""
    if isinstance(account, LinkedAccount):
        return account.evaluation

    return account


_NOT_FLAT = frozenset({"summary", "charges", "withdrawals"})
"""The :class:`AccountRun` fields a report row leaves out."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountRun:
    """What one attempt at an account did.

    :attr:`summary` is the strategy's performance over the trades this account actually took;
    every other field describes the account. The two part company at a breach, where the
    account is liquidated at the floor and the trade log is not.
    """

    account_name: str
    """The preset this account ran under, which tells a linked pair's two accounts apart."""

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

    trades_rejected: int
    """Trades over the account's size limit, which the firm would have refused."""

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
    """Taken out of the account, before the firm's split."""

    first_withdrawal_on: dt.date | None
    """The trading day of the first withdrawal. ``None`` when nothing was withdrawn."""

    payout: float
    """What reached the trader: :attr:`withdrawn` times ``rules.profit_split``."""

    fees_paid: float
    net: float
    """:attr:`payout` minus :attr:`fees_paid`: what this attempt was worth."""

    charges: tuple[Charge, ...]
    """Every fee, dated, adding up to :attr:`fees_paid`."""

    withdrawals: tuple[Withdrawal, ...]
    """Every withdrawal, dated, adding up to :attr:`withdrawn` and :attr:`payout`."""

    summary: stats.Summary

    def as_dict(self) -> dict[str, str | float | int | bool | None]:
        """Return a flat mapping of the account's own figures, for a report row.

        The performance half is :attr:`summary`, which carries its own ``as_dict``, and the dated
        money is :attr:`charges` and :attr:`withdrawals`.
        """
        row: dict[str, str | float | int | bool | None] = {
            f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.name not in _NOT_FLAT
        }
        row["outcome"] = str(self.outcome)
        row["first_day"] = self.first_day.isoformat()
        row["last_day"] = self.last_day.isoformat()
        row["passed_on"] = self.passed_on.isoformat() if self.passed_on else None
        first_withdrawal: dt.date | None = self.first_withdrawal_on
        row["first_withdrawal_on"] = first_withdrawal.isoformat() if first_withdrawal else None

        return row


@dataclass(frozen=True, slots=True, kw_only=True)
class PropReplay:
    """Every attempt at one rule set over one trade log, and what the sequence was worth."""

    account_name: str
    attempts: int
    """Evaluations bought. A linked pair's funded account belongs to the attempt that passed."""

    passes: int
    """Evaluations passed."""

    pass_rate: float
    breaches: int
    """Attempts a breach ended, of either account of a linked pair."""

    withdrawn: float
    """Taken out of the accounts, before the firm's split."""

    payout: float
    """What reached the trader: :attr:`withdrawn` times ``rules.profit_split``."""

    fees_paid: float
    net: float
    """:attr:`payout` minus :attr:`fees_paid`: what the whole sequence of attempts was worth."""

    trades_taken: int
    trades_rejected: int
    """Trades over a size limit, which the firm would have refused."""

    trades_total: int
    """Trades in the log from the first account's opening day on.

    Above :attr:`trades_taken` by whatever lockouts, rejections and breaches skipped.
    """

    runs: tuple[AccountRun, ...]
    summary: stats.Summary
    """:func:`nqbt.stats.summarise` over every trade any attempt took."""

    def as_dict(self) -> dict[str, str | float | int]:
        """Return a flat mapping of the lifetime figures, for a ranking row."""
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

    contracts: FloatArray
    """Full-size contracts each trade put on, a micro counting as its share of one."""

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
    payout: float = 0.0
    lowest_equity: float = float("inf")
    floor_headroom: float = float("inf")
    days_traded: int = 0
    locked_out_days: int = 0
    skipped: int = 0
    rejected: int = 0
    size_limit: float = float("inf")
    floor_locked: bool = False
    cycle_start: float = 0.0
    """The balance the current payout cycle opened on."""

    passed_on: dt.date | None = None
    first_withdrawal_on: dt.date | None = None
    taken: list[int] = field(default_factory=list)
    daily: list[float] = field(default_factory=list)
    cycle_daily: list[float] = field(default_factory=list)
    """Each day's realised P&L since the last payout."""

    withdrawals: list[Withdrawal] = field(default_factory=list)


class _Attempt(NamedTuple):
    """One account's replay, before it is read off into an :class:`AccountRun`."""

    state: _AccountState
    outcome: Outcome
    first_day: int
    last_day: int
    resume: int
    """Day index the next attempt may open on."""


def replay(
    log: pd.DataFrame,
    account: Account,
    *,
    max_accounts: int = 1,
    start: dt.date | None = None,
) -> PropReplay:
    """Replay ``account``'s rules over a trade log, one attempt after another.

    ``max_accounts`` of 1 gives a single verdict; higher opens a fresh account on the day after
    each breach, up to that many attempts, and nets the withdrawals against the fees. The first
    account opens on the log's first trading day, or its first on or after ``start``.

    A :class:`LinkedAccount` closes its evaluation at the pass and opens the funded account on
    the next trading day; an attempt ends when either breaches.
    """
    if max_accounts < 1:
        msg: str = f"max_accounts must be at least 1; got {max_accounts}"
        raise PropAccountError(msg)

    rule_sets: tuple[AccountRules, ...] = _rule_sets(account)
    table: _TradeTable = _trade_table(
        log,
        needs_excursions=any(rules.needs_excursions for rules in rule_sets),
        needs_contracts=any(rules.limits_size for rules in rule_sets),
    )
    first_day: int = _first_day(table, start)
    funded: PropAccount | None = account.opened_by_pass if isinstance(account, LinkedAccount) else None
    runs: list[AccountRun] = []
    taken: list[int] = []
    for opened, attempt in _attempts(table, evaluation_of(account), funded, first_day, max_accounts):
        runs.append(_finish(log, table, opened, attempt))
        taken.extend(attempt.state.taken)

    return _lifetime(log, table, account, tuple(runs), taken, first_day)


def _rule_sets(account: Account) -> tuple[AccountRules, ...]:
    """Return every rule set the account trades under."""
    if isinstance(account, LinkedAccount):
        return (account.evaluation.rules, account.funded.rules)

    return (account.rules,)


def _first_day(table: _TradeTable, start: dt.date | None) -> int:
    """Return the index of the first trading day on or after ``start``, or of the log's first."""
    if start is None:
        return 0

    return int(np.searchsorted(table.days, np.datetime64(start, "D"), side="left"))


def _attempts(
    table: _TradeTable,
    bought: PropAccount,
    funded: PropAccount | None,
    day: int,
    max_accounts: int,
) -> Iterator[tuple[PropAccount, _Attempt]]:
    """Yield one account after another, each opening on the trading day after the last one closed.

    With a ``funded`` account, each evaluation closes at its pass and the funded account follows.
    """
    opened: int = 0
    while day < table.n_days and opened < max_accounts:
        evaluation: _Attempt = _run_account(table, bought, day, until_pass=funded is not None)
        yield bought, evaluation
        opened += 1
        day = evaluation.resume
        if funded is None or evaluation.outcome is not Outcome.PROMOTED or day >= table.n_days:
            continue

        held: _Attempt = _run_account(table, funded, day)
        yield funded, held
        day = held.resume


def _lifetime(
    log: pd.DataFrame,
    table: _TradeTable,
    account: Account,
    runs: tuple[AccountRun, ...],
    taken: list[int],
    first_day: int,
) -> PropReplay:
    """Total the attempts, and summarise every trade any of them took."""
    bought: str = evaluation_of(account).name
    evaluations: list[AccountRun] = [run for run in runs if run.account_name == bought]
    passes: int = sum(run.passed for run in evaluations)
    withdrawn: float = sum(run.withdrawn for run in runs)
    payout: float = sum(run.payout for run in runs)
    fees_paid: float = sum(run.fees_paid for run in runs)

    return PropReplay(
        account_name=account.name,
        attempts=len(evaluations),
        passes=passes,
        pass_rate=passes / len(evaluations) if evaluations else 0.0,
        breaches=sum(run.outcome in _BREACHES for run in runs),
        withdrawn=withdrawn,
        payout=payout,
        fees_paid=fees_paid,
        net=payout - fees_paid,
        trades_taken=len(taken),
        trades_rejected=sum(run.trades_rejected for run in runs),
        trades_total=table.trade_id.size - int(table.day_starts[first_day]),
        runs=runs,
        summary=stats.summarise(_legs_taken(log, table, taken)),
    )


def _legs_taken(log: pd.DataFrame, table: _TradeTable, positions: list[int]) -> pd.DataFrame:
    """Return the legs of the trades at ``positions``, so every performance figure is ``summarise``'s."""
    if not positions:
        return log.iloc[:0]

    wanted: IntArray = table.trade_id[np.asarray(positions, dtype=np.int64)]

    return log[log["trade_id"].isin(wanted)]


def _trade_table(log: pd.DataFrame, *, needs_excursions: bool, needs_contracts: bool) -> _TradeTable:
    """Collapse a leg-level log into the per-trade, per-day quantities the replay walks.

    Contracts are zero on every trade when no size limit reads them.
    """
    _require_columns(log, needs_excursions=needs_excursions)
    if log.empty:
        empty_days: DateArray = np.empty(0, dtype="datetime64[D]")

        return _TradeTable(
            trade_id=np.empty(0, dtype=np.int64),
            net_pnl=np.empty(0, dtype=np.float64),
            commission=np.empty(0, dtype=np.float64),
            adverse=np.empty(0, dtype=np.float64),
            favourable=np.empty(0, dtype=np.float64),
            contracts=np.empty(0, dtype=np.float64),
            days=empty_days,
            day_starts=np.zeros(1, dtype=np.int64),
        )

    per_trade: pd.DataFrame = stats.per_trade(log).sort_values("exit_time", kind="stable")
    excursions: pd.DataFrame = _excursion_dollars(log, needs_excursions=needs_excursions).reindex(
        per_trade.index
    )
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
        contracts=_contracts(log, per_trade.index) if needs_contracts else np.zeros(len(per_trade)),
        days=trading_day[starts[:-1]],
        day_starts=starts,
    )


def _require_columns(log: pd.DataFrame, *, needs_excursions: bool) -> None:
    """Refuse a log that cannot answer the rules, naming the rule that needed the column."""
    missing: list[str] = [c for c in REQUIRED_COLUMNS if c not in log.columns]
    if missing:
        msg: str = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise PropAccountError(msg)

    if not needs_excursions:
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


def _excursion_dollars(log: pd.DataFrame, *, needs_excursions: bool) -> pd.DataFrame:
    """Return each trade's worst and best open equity in dollars, summed over its legs.

    Zero on both when no enabled limit reads them, so a log with no excursions still replays.
    """
    index: pd.Index[int] = pd.Index(sorted(set(log["trade_id"])), name="trade_id")
    if not needs_excursions:
        return pd.DataFrame({"adverse": 0.0, "favourable": 0.0}, index=index)

    point_value: FloatArray = _per_leg(log, "point_value")
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


def _contracts(log: pd.DataFrame, trades: pd.Index[int]) -> FloatArray:
    """Return the full-size contracts each of ``trades`` put on, summed over its legs."""
    minis: FloatArray = log["quantity"].to_numpy(np.float64) * _per_leg(log, "mini_equivalent")
    per_trade = pd.Series(minis, index=log.index).groupby(log["trade_id"].to_numpy(np.int64)).sum()

    return np.asarray(per_trade.reindex(trades), dtype=np.float64)


def _per_leg(log: pd.DataFrame, figure: str) -> FloatArray:
    """Return one instrument figure for each leg's own instrument, since a log may span both roots."""
    per_symbol: dict[str, float] = {
        str(symbol): float(getattr(instruments.get_instrument(str(symbol)), figure))
        for symbol in log["instrument"].unique()
    }

    return np.asarray(log["instrument"].map(per_symbol), dtype=np.float64)


def _day_starts(trading_day: DateArray) -> IntArray:
    """Return half-open bounds of each run of equal trading days, plus a closing sentinel."""
    changed: IntArray = np.flatnonzero(trading_day[1:] != trading_day[:-1]) + 1

    return np.concatenate(([0], changed, [trading_day.size])).astype(np.int64)


def _trailing_floor(high_water: float, rules: AccountRules, *, locked: bool = False) -> float:
    """Return where the account dies, given the highest equity it has reached.

    ``locked`` is a floor a payout has already moved to its lock.
    """
    if rules.trailing_threshold <= 0.0:
        return float("-inf")

    lock: float = rules.starting_balance + rules.trail_lock_buffer
    if locked:
        return lock

    floor: float = high_water - rules.trailing_threshold
    if rules.trail_lock is TrailLock.NEVER:
        return floor

    return min(floor, lock)


def _probe_low(balance: float, table: _TradeTable, pos: int, basis: EquityBasis) -> float:
    """Return the lowest equity one trade reaches, on the basis a rule measures itself against."""
    if basis is EquityBasis.UNREALISED:
        return balance - float(table.adverse[pos]) - float(table.commission[pos])

    return balance + float(table.net_pnl[pos])


def _probe_high(balance: float, table: _TradeTable, pos: int) -> float:
    """Return the highest equity one trade reaches, which only an intraday high-water mark reads."""
    return balance + float(table.favourable[pos]) - float(table.commission[pos])


def _take_trade(table: _TradeTable, pos: int, rules: AccountRules, state: _AccountState) -> Outcome:
    """Apply one trade to the account and report how it left it.

    Which excursion moves the floor first is ``rules.excursion_order`` -- ``docs/roadmap.md``
    §M28.13.
    """
    tracks_peak: bool = rules.trail_basis is TrailBasis.INTRADAY
    peak: float = _probe_high(state.balance, table, pos)
    if tracks_peak and rules.excursion_order is ExcursionOrder.PEAK_FIRST:
        state.high_water = max(state.high_water, peak)

    floor: float = _trailing_floor(state.high_water, rules, locked=state.floor_locked)
    trail_low: float = _probe_low(state.balance, table, pos, rules.trail_breach)
    state.lowest_equity = min(state.lowest_equity, trail_low)
    state.floor_headroom = min(state.floor_headroom, trail_low - floor)
    state.taken.append(pos)
    if trail_low <= floor:
        state.balance = trail_low

        return Outcome.BREACHED_TRAILING

    # Under either order the peak still happened, so it moves the floor for every later trade.
    # Re-applying it is a no-op when it was already taken above.
    if tracks_peak:
        state.high_water = max(state.high_water, peak)

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
    *,
    until_pass: bool,
) -> Outcome:
    """Walk one trading day's trades, record the day, then close it if the account survived.

    The day is recorded either way, so an account that died on its only day does not report
    having traded on none; a day whose every trade was rejected is not a day traded at all.
    """
    state.day_open_balance = state.balance
    state.day_realised = 0.0
    state.size_limit = _size_limit(rules, state.balance - rules.starting_balance)
    taken_before: int = len(state.taken)

    outcome: Outcome = _walk_day(table, day, rules, state)
    if len(state.taken) == taken_before:
        return Outcome.SURVIVED

    state.days_traded += 1
    state.daily.append(state.day_realised)
    state.cycle_daily.append(state.day_realised)
    if outcome is not Outcome.SURVIVED:
        return outcome

    return _close_day(table, day, rules, state, until_pass=until_pass)


def _size_limit(rules: AccountRules, opening_profit: float) -> float:
    """Return the largest position a session opening on ``opening_profit`` may put on."""
    limits: list[float] = [rules.max_contracts] if rules.max_contracts > 0.0 else []
    if rules.scaling_plan:
        reached: list[ScalingTier] = [
            tier for tier in rules.scaling_plan if opening_profit >= tier.from_profit
        ]
        limits.append((reached or [rules.scaling_plan[0]])[-1].contracts)

    return min(limits, default=float("inf"))


def _walk_day(table: _TradeTable, day: int, rules: AccountRules, state: _AccountState) -> Outcome:
    """Take one day's trades in order, stopping at whatever ends the day or the account."""
    end: int = int(table.day_starts[day + 1])
    for pos in range(int(table.day_starts[day]), end):
        if table.contracts[pos] > state.size_limit + SIZE_TOLERANCE:
            state.rejected += 1
            continue

        outcome: Outcome = _take_trade(table, pos, rules, state)
        if outcome is Outcome.SURVIVED:
            continue

        if outcome is Outcome.BREACHED_TRAILING or rules.on_daily_breach is DailyBreach.FAIL:
            return outcome

        state.locked_out_days += 1
        state.skipped += end - pos - 1
        break

    return Outcome.SURVIVED


def _close_day(
    table: _TradeTable,
    day: int,
    rules: AccountRules,
    state: _AccountState,
    *,
    until_pass: bool,
) -> Outcome:
    """Advance the high-water mark, test the pass, take any payout due, and test for a move live.

    The floor needs no second test here: a trade's own probe is never above the balance it
    leaves behind, so the closing balance cannot breach a floor the day's trades did not. An
    account replayed ``until_pass`` closes at its pass, before it could withdraw anything.
    """
    if rules.trail_basis is TrailBasis.END_OF_DAY:
        state.high_water = max(state.high_water, state.balance)

    _check_pass(table, day, rules, state)
    if until_pass and state.passed_on is not None:
        return Outcome.PROMOTED

    _withdraw(table, day, rules, state)
    paid_out: bool = 0 < rules.max_payouts <= len(state.withdrawals)
    capped_day: bool = 0.0 < rules.daily_profit_cap <= state.day_realised
    if paid_out or capped_day:
        return Outcome.MOVED_LIVE

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
    """Return one trading day as the calendar date a report prints."""
    return pd.Timestamp(day).date()


def _consistent(daily: list[float], profit: float, ratio: float) -> bool:
    """Return whether no single day contributed more than ``ratio`` of the account's total profit."""
    if ratio <= 0.0:
        return True

    if profit <= 0.0:
        return False

    return max(daily) <= ratio * profit


def _withdraw(table: _TradeTable, day: int, rules: AccountRules, state: _AccountState) -> None:
    """Take the largest payout the rules allow above the safety net, once the account has passed."""
    if state.passed_on is None or not _payout_due(rules, state):
        return

    excess: float = _payout_size(rules, state.balance - rules.starting_balance)
    if excess <= 0.0 or excess < rules.payout_minimum:
        return

    taken_on: dt.date = _as_date(table.days[day])
    if state.first_withdrawal_on is None:
        state.first_withdrawal_on = taken_on

    payout: float = excess * rules.profit_split
    state.balance -= excess
    state.withdrawn += excess
    state.payout += payout
    state.withdrawals.append(Withdrawal(taken_on, excess, payout))
    state.cycle_start = state.balance
    state.cycle_daily = []
    state.floor_locked = state.floor_locked or rules.floor_locks_at_payout


def _payout_due(rules: AccountRules, state: _AccountState) -> bool:
    """Return whether the days since the last payout meet every condition a payout needs."""
    profit: float = state.balance - state.cycle_start
    if rules.payout_profit_goal > 0.0 and profit < rules.payout_profit_goal:
        return False

    if _qualifying_days(rules, state.cycle_daily) < rules.payout_days:
        return False

    return _consistent(state.cycle_daily, profit, rules.payout_consistency)


def _qualifying_days(rules: AccountRules, daily: list[float]) -> int:
    """Count the days that make at least ``payout_day_profit``, or every day where it is off."""
    if rules.payout_day_profit <= 0.0:
        return len(daily)

    return sum(made >= rules.payout_day_profit for made in daily)


def _payout_size(rules: AccountRules, profit: float) -> float:
    """Return the largest payout ``profit`` above the starting balance allows."""
    size: float = min(profit - rules.withdrawal_threshold, profit * rules.payout_share)
    if rules.floor_locks_at_payout:
        size = min(size, profit - rules.trail_lock_buffer)

    if rules.payout_cap <= 0.0:
        return size

    return min(size, rules.payout_cap)


def _run_account(
    table: _TradeTable,
    account: PropAccount,
    first_day: int,
    *,
    until_pass: bool = False,
) -> _Attempt:
    """Replay one account from ``first_day``, and report the day the next one may open on."""
    rules: AccountRules = account.rules
    state = _AccountState(
        balance=rules.starting_balance,
        high_water=rules.starting_balance,
        day_open_balance=rules.starting_balance,
        cycle_start=rules.starting_balance,
    )

    outcome: Outcome = Outcome.SURVIVED
    last_day: int = first_day
    for day in range(first_day, table.n_days):
        if _expired(table, first_day, day, rules, state):
            outcome = Outcome.EXPIRED
            break

        last_day = day
        outcome = _trade_one_day(table, day, rules, state, until_pass=until_pass)
        if outcome is not Outcome.SURVIVED:
            break

    resume: int = table.n_days if outcome is Outcome.SURVIVED else last_day + 1

    return _Attempt(state, outcome, first_day, last_day, resume)


def _expired(table: _TradeTable, first_day: int, day: int, rules: AccountRules, state: _AccountState) -> bool:
    """Return whether an account that has not passed is past the calendar days it had to pass in."""
    if rules.evaluation_days <= 0 or state.passed_on is not None:
        return False

    return bool(table.days[day] - table.days[first_day] >= np.timedelta64(rules.evaluation_days, "D"))


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
    fees: float = _fees_paid(account.fees, opened, closed, passed_on=state.passed_on)
    profit: float = state.balance + state.withdrawn - rules.starting_balance

    return AccountRun(
        account_name=account.name,
        outcome=attempt.outcome,
        passed=state.passed_on is not None,
        first_day=opened,
        last_day=closed,
        days_traded=state.days_traded,
        passed_on=state.passed_on,
        trades_taken=len(state.taken),
        trades_skipped=state.skipped,
        trades_rejected=state.rejected,
        locked_out_days=state.locked_out_days,
        final_balance=state.balance,
        peak_balance=state.high_water,
        lowest_equity=state.lowest_equity if state.taken else rules.starting_balance,
        trailing_floor=_trailing_floor(state.high_water, rules, locked=state.floor_locked),
        floor_headroom=state.floor_headroom if state.taken else float("inf"),
        best_day=max(state.daily) if state.daily else 0.0,
        worst_day=min(state.daily) if state.daily else 0.0,
        consistency=(max(state.daily) / profit) if state.daily and profit > 0.0 else 0.0,
        withdrawn=state.withdrawn,
        first_withdrawal_on=state.first_withdrawal_on,
        payout=state.payout,
        fees_paid=fees,
        net=state.payout - fees,
        charges=_charges(account.fees, opened, closed, passed_on=state.passed_on),
        withdrawals=tuple(state.withdrawals),
        summary=stats.summarise(_legs_taken(log, table, state.taken)),
    )


def _fees_paid(
    fees: AccountFees,
    opened: dt.date,
    closed: dt.date,
    *,
    passed_on: dt.date | None,
) -> float:
    """Return one attempt's cost: the entry fee, a month for every month it was billed, and activation."""
    billed_to: dt.date = _billed_to(fees, closed, passed_on=passed_on)
    months: int = (billed_to.year - opened.year) * 12 + billed_to.month - opened.month + 1
    total: float = fees.evaluation_fee + fees.monthly_fee * months
    if passed_on is None:
        return total

    return total + fees.activation_fee


def _charges(
    fees: AccountFees,
    opened: dt.date,
    closed: dt.date,
    *,
    passed_on: dt.date | None,
) -> tuple[Charge, ...]:
    """Return one attempt's fees, each on the day it was charged, leaving out any that cost nothing.

    The entry fee and the first month fall on the opening day, each later month on its first
    calendar day, and the activation fee on the day of the pass.
    """
    billed: list[dt.date] = [opened, *_month_starts(opened, _billed_to(fees, closed, passed_on=passed_on))]
    charges: list[Charge] = [
        Charge(opened, fees.evaluation_fee, FeeKind.EVALUATION),
        *(Charge(day, fees.monthly_fee, FeeKind.MONTHLY) for day in billed),
    ]
    if passed_on is not None:
        charges.append(Charge(passed_on, fees.activation_fee, FeeKind.ACTIVATION))

    return tuple(charge for charge in charges if charge.amount > 0.0)


def _billed_to(fees: AccountFees, closed: dt.date, *, passed_on: dt.date | None) -> dt.date:
    """Return the last day the monthly fee covers: the close, or the pass where billing stops there."""
    if fees.monthly_fee_ends_at_pass and passed_on is not None:
        return passed_on

    return closed


def _month_starts(opened: dt.date, billed_to: dt.date) -> list[dt.date]:
    """List the first day of every month after the opening one, up to the one ``billed_to`` is in."""
    first: int = opened.year * 12 + opened.month - 1
    last: int = billed_to.year * 12 + billed_to.month - 1

    return [dt.date(month // 12, month % 12 + 1, 1) for month in range(first + 1, last + 1)]
