"""Replaying a prop account's rules over a trade log.

Three claims carry this module and each has a test named after it. The **statistics** must stay
`stats.summarise`'s, because a second definition of a win rate here would drift from the sweep's
silently. **Unrealised P&L must decide outcomes a realised replay gets wrong**, which is the
whole reason the module reads `mae_points` at all. And a **blown account must still be able to
be profitable**, because the money already withdrawn is kept.
"""

import dataclasses
import datetime as dt
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from nqbt import instruments, propaccount, stats
from nqbt.propaccount import (
    AccountFees,
    AccountRules,
    Charge,
    DailyBreach,
    EquityBasis,
    FeeKind,
    LinkedAccount,
    Outcome,
    PropAccount,
    PropAccountError,
    TrailBasis,
    TrailLock,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# MNQ is $2 a point, so one 4-lot moves $8 for every point of excursion. Every dollar figure
# below is derived from that rather than written out, so a tick-value change cannot pass here.
LOTS = 4
MNQ_PER_POINT = instruments.MNQ.point_value * LOTS
COMMISSION = 6.0


def leg_log(
    rows: Sequence[tuple[int, float, float]], *, instrument: str = "MNQ", start: str = "2024-01-02 15:00"
) -> pd.DataFrame:
    """Build a one-leg-per-trade log from ``(day_offset, net_pnl, mae_points)`` triples.

    Times are UTC and mid-afternoon, so every trade lands on the trading day its offset names
    unless a test deliberately moves one across the session boundary.
    """
    base = pd.Timestamp(start, tz="UTC")
    built = []
    for trade_id, (day, net, mae) in enumerate(rows, start=1):
        built.append(
            {
                "source": "sim",
                "instrument": instrument,
                "trade_id": trade_id,
                "leg": 1,
                "quantity": LOTS,
                "direction": 1.0,
                "gross_pnl": net + COMMISSION,
                "commission": COMMISSION,
                "net_pnl": net,
                "bars_held": 5,
                "mae_points": mae,
                "mfe_points": 1.0,
                "r_multiple": 0.5,
                "ambiguous_bar": False,
                "exit_reason": "target",
                "entry_time": base + pd.Timedelta(days=day),
                "exit_time": base + pd.Timedelta(days=day, minutes=trade_id),
            },
        )

    return pd.DataFrame(built)


def account(**overrides: object) -> PropAccount:
    """Build a deliberately plain rule set, so each test switches on exactly the field it names."""
    fields = {
        "starting_balance": 50_000.0,
        "profit_target": 3_000.0,
        "trailing_threshold": 2_000.0,
        "trail_basis": TrailBasis.END_OF_DAY,
        "trail_breach": EquityBasis.REALISED,
        "daily_loss_basis": EquityBasis.REALISED,
    }

    return PropAccount(name="Test", rules=AccountRules(**(fields | overrides)))  # type: ignore[arg-type]  # AccountRules' own fields


# -- the summary must stay stats.summarise's -----------------------------------


def test_the_replay_summary_is_summarise_over_the_trades_it_took() -> None:
    """The reuse the issue asks for, pinned rather than assumed."""
    log = leg_log([(0, 400.0, 1.0), (1, -200.0, 2.0), (2, 900.0, 1.0)])
    result = propaccount.replay(log, account())

    assert result.trades_taken == len(log)
    assert result.summary == stats.summarise(log)


def test_a_breached_account_summarises_only_the_trades_it_took() -> None:
    log = leg_log([(0, -2_500.0, 1.0), (1, 5_000.0, 1.0)])
    result = propaccount.replay(log, account())

    assert result.runs[0].outcome is Outcome.BREACHED_TRAILING
    assert result.trades_taken == 1
    assert result.summary == stats.summarise(log[log["trade_id"] == 1])
    # The trade it never took is the one that would have made the log look profitable.
    assert stats.summarise(log).net_pnl > 0
    assert result.summary.net_pnl < 0


def test_the_module_defines_no_statistic_summarise_already_owns() -> None:
    """Every performance name belongs to ``Summary``; the run's own fields are about the account."""
    log = leg_log([(0, 400.0, 1.0), (1, 100.0, 1.0)])
    run = propaccount.replay(log, account()).runs[0]

    assert not set(run.as_dict()) & set(stats.Summary.columns())


# -- unrealised P&L must decide what realised P&L gets wrong -------------------


def _dips_but_wins(mae_points: float) -> pd.DataFrame:
    """Build one profitable trade that first goes ``mae_points`` against, then a quiet second day."""
    return leg_log([(0, 100.0, mae_points), (1, 100.0, 1.0)])


def test_open_equity_breaches_an_account_the_closed_pnl_says_is_fine() -> None:
    """The headline case: a profitable trade that dipped too far kills the account anyway."""
    dip = 2_100.0 / MNQ_PER_POINT  # $100 past a $2,000 floor
    log = _dips_but_wins(dip)
    unrealised = account(trail_breach=EquityBasis.UNREALISED)

    breached = propaccount.replay(log, unrealised).runs[0]
    survived = propaccount.replay(log, account()).runs[0]

    assert breached.outcome is Outcome.BREACHED_TRAILING
    assert survived.outcome is Outcome.SURVIVED
    # And the half that makes it a finding rather than a tautology: the log is profitable.
    assert stats.summarise(log).net_pnl > 0


def test_the_excursion_is_priced_through_the_instrument_not_a_constant() -> None:
    """The same points on NQ are ten times the dollars, and that decides the outcome."""
    dip = 250.0  # $2,000 on MNQ at four lots, $20,000 on NQ
    unrealised = account(trail_breach=EquityBasis.UNREALISED)

    micro = propaccount.replay(_dips_but_wins(dip - 1.0), unrealised).runs[0]
    full = propaccount.replay(
        leg_log([(0, 100.0, dip - 1.0), (1, 100.0, 1.0)], instrument="NQ"),
        unrealised,
    ).runs[0]

    assert micro.outcome is Outcome.SURVIVED
    assert full.outcome is Outcome.BREACHED_TRAILING


def test_a_daily_loss_limit_reads_open_equity_when_told_to() -> None:
    dip = 1_200.0 / MNQ_PER_POINT
    log = leg_log([(0, 100.0, dip), (1, 100.0, 1.0)])
    rules = {"daily_loss_limit": 1_000.0, "trailing_threshold": 0.0}

    on_open = propaccount.replay(log, account(daily_loss_basis=EquityBasis.UNREALISED, **rules))
    on_closed = propaccount.replay(log, account(**rules))

    assert on_open.runs[0].outcome is Outcome.BREACHED_DAILY_LOSS
    assert on_closed.runs[0].outcome is Outcome.SURVIVED


def test_an_intraday_high_water_mark_raises_the_floor_a_daily_one_does_not() -> None:
    """A trade that gave its profit back still moves the floor under an intraday basis."""
    log = leg_log([(0, 0.0, 1.0)])
    log.loc[0, "mfe_points"] = 3_000.0 / MNQ_PER_POINT

    intraday = propaccount.replay(log, account(trail_basis=TrailBasis.INTRADAY)).runs[0]
    end_of_day = propaccount.replay(log, account()).runs[0]

    assert intraday.peak_balance == pytest.approx(53_000.0 - COMMISSION)
    assert end_of_day.peak_balance == pytest.approx(50_000.0)
    assert intraday.trailing_floor > end_of_day.trailing_floor


# -- which excursion moves the floor first -------------------------------------


def _spikes_then_dips() -> pd.DataFrame:
    """Build one trade that runs $3,000 in favour and $1,000 against, under Apex's geometry.

    The peak takes the high-water mark to $52,994, which under a $2,500 threshold locks the
    floor at its $50,100 ceiling; the trough at $48,994 is then below it. Applied the other way
    round the floor is still $47,500 and the same trough clears it. Sized so the two disagree,
    which is the whole point of the parameter.

    It closes at +$500 rather than +$100 so the second day clears the $50,100 the peak locked
    the floor at; at +$100 the balance lands exactly on that floor and any dip kills it, which
    is realistic and not what this fixture is for.
    """
    log = leg_log([(0, 500.0, 1_000.0 / MNQ_PER_POINT), (1, 100.0, 1.0)])
    log.loc[0, "mfe_points"] = 3_000.0 / MNQ_PER_POINT

    return log


def _intraday(**overrides: object) -> PropAccount:
    """Build Apex's trailing geometry: an intraday mark and a floor that locks just above the start."""
    return account(
        trailing_threshold=2_500.0,
        trail_basis=TrailBasis.INTRADAY,
        trail_breach=EquityBasis.UNREALISED,
        trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
        trail_lock_buffer=100.0,
        profit_target=1e6,
        **overrides,
    )


def test_the_excursion_order_decides_whether_the_account_survives_its_first_trade() -> None:
    """Which excursion moves the floor first decides the outcome -- ``docs/roadmap.md`` §M28.13."""
    log = _spikes_then_dips()

    peak_first = propaccount.replay(log, _intraday()).runs[0]
    trough_first = propaccount.replay(
        log,
        _intraday(excursion_order=propaccount.ExcursionOrder.TROUGH_FIRST),
    ).runs[0]

    assert peak_first.outcome is Outcome.BREACHED_TRAILING
    assert peak_first.trades_taken == 1
    assert trough_first.outcome is Outcome.SURVIVED
    assert trough_first.trades_taken == 2


def test_the_peak_still_moves_the_floor_under_the_kinder_order() -> None:
    """Deferring the peak is not discarding it: later trades face the floor it raised."""
    log = _spikes_then_dips()
    run = propaccount.replay(
        log,
        _intraday(excursion_order=propaccount.ExcursionOrder.TROUGH_FIRST),
    ).runs[0]

    assert run.peak_balance == pytest.approx(53_000.0 - COMMISSION)
    assert run.trailing_floor == pytest.approx(50_100.0)


def test_the_harsher_order_is_the_default_so_a_preset_is_unchanged() -> None:
    assert (
        propaccount.AccountRules(
            starting_balance=1.0,
            profit_target=1.0,
        ).excursion_order
        is propaccount.ExcursionOrder.PEAK_FIRST
    )
    assert all(
        a.rules.excursion_order is propaccount.ExcursionOrder.PEAK_FIRST for a in propaccount.PRESETS.values()
    )


def test_an_end_of_day_mark_is_untouched_by_the_order() -> None:
    """No intraday high-water mark means no peak to order against the trough.

    Asserted as agreement between the two rather than against a figure, so the claim cannot be
    broken by re-sizing the fixture.
    """
    log = _spikes_then_dips()
    runs = [
        propaccount.replay(log, account(excursion_order=order)).runs[0]
        for order in propaccount.ExcursionOrder
    ]

    assert runs[0].outcome is Outcome.SURVIVED
    assert runs[0].as_dict() == runs[1].as_dict()
    # And the peak that would have moved an intraday mark is genuinely in the fixture.
    assert log["mfe_points"].max() * MNQ_PER_POINT > 2_500.0


# -- a blown account can still have been profitable ----------------------------


def test_money_withdrawn_before_a_breach_is_kept() -> None:
    """The framing that makes this worth building: the account died and the sequence paid."""
    earn = [(day, 1_000.0, 1.0) for day in range(4)]
    blow = [(4, -3_000.0, 1.0)]
    run = propaccount.replay(
        leg_log(earn + blow),
        account(withdrawal_threshold=2_500.0, trail_lock=TrailLock.AT_STARTING_BALANCE),
    ).runs[0]

    assert run.outcome is Outcome.BREACHED_TRAILING
    assert run.withdrawn == pytest.approx(1_500.0)
    assert run.net > 0.0


def test_a_withdrawal_into_the_floor_breaches_the_account_it_funded() -> None:
    """The documented footgun: no safety net under a floor that never locks is a dead account."""
    log = leg_log([(day, 1_000.0, 1.0) for day in range(5)])
    run = propaccount.replay(
        log,
        account(withdrawal_threshold=0.0, trail_lock=TrailLock.NEVER),
    ).runs[0]

    assert run.passed
    assert run.outcome is Outcome.BREACHED_TRAILING
    # The floor is above the balance the withdrawal left behind, and nothing else moved it.
    assert run.trailing_floor > 50_000.0


def test_a_withdrawal_does_not_lower_the_high_water_mark() -> None:
    """Taking profit out shrinks the buffer; it does not buy back any trailing room."""
    log = leg_log([(day, 1_500.0, 1.0) for day in range(3)])
    run = propaccount.replay(log, account(withdrawal_threshold=1_000.0)).runs[0]

    assert run.withdrawn == pytest.approx(3_500.0)
    assert run.peak_balance == pytest.approx(53_000.0)
    assert run.final_balance == pytest.approx(51_000.0)
    # Two withdrawals later the balance is back at the safety net and the floor has not followed
    # it down -- it is sitting exactly on it.
    assert run.trailing_floor == pytest.approx(51_000.0)


def test_the_fees_are_netted_against_the_withdrawals() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    fees = AccountFees(evaluation_fee=100.0, monthly_fee=50.0, activation_fee=25.0)
    paid = PropAccount(name="Test", rules=account(withdrawal_threshold=0.0).rules, fees=fees)
    result = propaccount.replay(log, paid)

    # One calendar month, and the activation fee only because it passed.
    assert result.fees_paid == pytest.approx(175.0)
    assert result.net == pytest.approx(result.withdrawn - 175.0)
    assert result.runs[0].passed


def test_an_attempt_that_never_passes_pays_no_activation_fee() -> None:
    log = leg_log([(0, -100.0, 1.0)])
    fees = AccountFees(evaluation_fee=100.0, activation_fee=25.0)
    result = propaccount.replay(log, PropAccount(name="Test", rules=account().rules, fees=fees))

    assert not result.runs[0].passed
    assert result.fees_paid == pytest.approx(100.0)


def test_a_monthly_fee_is_charged_for_every_month_the_account_is_live() -> None:
    log = leg_log([(0, 10.0, 1.0), (40, 10.0, 1.0)])
    fees = AccountFees(monthly_fee=50.0)
    result = propaccount.replay(log, PropAccount(name="Test", rules=account().rules, fees=fees))

    # 2 January to 11 February inclusive is two calendar months, not one and a third.
    assert result.fees_paid == pytest.approx(100.0)


def test_a_monthly_fee_that_ends_at_the_pass_stops_billing_there() -> None:
    """A firm charging for the evaluation and nothing afterwards."""
    log = leg_log([(0, 3_000.0, 1.0), (40, 10.0, 1.0)])
    fees = AccountFees(monthly_fee=50.0, monthly_fee_ends_at_pass=True)
    result = propaccount.replay(log, PropAccount(name="Test", rules=account().rules, fees=fees))

    # It passed on 2 January and traded on into February, which it is no longer billed for.
    assert result.runs[0].passed_on == dt.date(2024, 1, 2)
    assert result.runs[0].last_day == dt.date(2024, 2, 11)
    assert result.fees_paid == pytest.approx(50.0)


def test_a_monthly_fee_that_ends_at_the_pass_bills_an_attempt_that_never_passed() -> None:
    """The half that would make the flag a discount rather than a rule."""
    log = leg_log([(0, -100.0, 1.0), (40, -100.0, 1.0)])
    fees = AccountFees(monthly_fee=50.0, monthly_fee_ends_at_pass=True)
    result = propaccount.replay(log, PropAccount(name="Test", rules=account().rules, fees=fees))

    assert not result.runs[0].passed
    assert result.fees_paid == pytest.approx(100.0)


# -- the firm's split of what is withdrawn -------------------------------------


def paying(**overrides: object) -> PropAccount:
    """Build a rule set that passes and then withdraws without walking onto its own floor."""
    return account(
        withdrawal_threshold=1_000.0,
        trail_lock=TrailLock.AT_STARTING_BALANCE,
        **overrides,
    )


def test_the_profit_split_takes_its_share_of_the_payout_and_not_of_the_balance() -> None:
    """The account gives up the whole withdrawal; the trader receives a share of it."""
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    run = propaccount.replay(log, paying(profit_split=0.80)).runs[0]

    assert run.withdrawn == pytest.approx(3_000.0)
    assert run.payout == pytest.approx(2_400.0)
    # The balance is back at the safety net, not 600 above it.
    assert run.final_balance == pytest.approx(51_000.0)


def test_the_net_of_an_attempt_is_the_payout_and_never_the_gross() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    fees = AccountFees(evaluation_fee=100.0)
    split = PropAccount(name="Test", rules=paying(profit_split=0.50).rules, fees=fees)
    result = propaccount.replay(log, split)

    assert result.withdrawn == pytest.approx(3_000.0)
    assert result.payout == pytest.approx(1_500.0)
    assert result.net == pytest.approx(1_400.0)


def test_the_default_split_leaves_the_payout_equal_to_the_withdrawal() -> None:
    """What makes the field additive: every preset written before it is unchanged."""
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    result = propaccount.replay(log, paying())

    assert account().rules.profit_split == 1.0
    assert result.payout == pytest.approx(result.withdrawn)


def test_a_split_does_not_change_what_the_account_itself_made() -> None:
    """The consistency figure is the account's profit, so the firm's share must not shrink it."""
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    halved = propaccount.replay(log, paying(profit_split=0.50)).runs[0]
    whole = propaccount.replay(log, paying()).runs[0]

    assert halved.payout == pytest.approx(1_500.0)
    assert halved.consistency == pytest.approx(whole.consistency)
    assert halved.consistency == pytest.approx(0.25)


# -- resets --------------------------------------------------------------------


def test_a_breach_opens_the_next_account_on_the_following_day() -> None:
    log = leg_log([(0, -2_500.0, 1.0), (1, 500.0, 1.0), (2, 500.0, 1.0)])
    result = propaccount.replay(log, account(), max_accounts=3)

    assert result.attempts == 2
    assert result.runs[0].outcome is Outcome.BREACHED_TRAILING
    assert result.runs[1].first_day == dt.date(2024, 1, 3)
    assert result.trades_taken == len(log)


def test_max_accounts_of_one_stops_at_the_first_breach() -> None:
    log = leg_log([(0, -2_500.0, 1.0), (1, 500.0, 1.0)])
    result = propaccount.replay(log, account())

    assert result.attempts == 1
    assert result.trades_taken == 1
    assert result.trades_total == 2


def test_the_pass_rate_is_over_the_attempts_that_were_made() -> None:
    log = leg_log([(0, -2_500.0, 1.0), *[(day, 1_500.0, 1.0) for day in range(1, 4)]])
    result = propaccount.replay(log, account(), max_accounts=2)

    assert result.attempts == 2
    assert result.passes == 1
    assert result.pass_rate == pytest.approx(0.5)


# -- the pass gates ------------------------------------------------------------


def test_the_profit_target_is_what_passes_an_account() -> None:
    just_under = leg_log([(0, 1_500.0, 1.0), (1, 1_499.0, 1.0)])
    just_over = leg_log([(0, 1_500.0, 1.0), (1, 1_500.0, 1.0)])

    assert not propaccount.replay(just_under, account()).runs[0].passed
    assert propaccount.replay(just_over, account()).runs[0].passed


def test_the_consistency_ratio_blocks_a_pass_the_profit_target_would_allow() -> None:
    """One day carrying most of the profit fails the rule even at the target."""
    lumpy = leg_log([(0, 2_800.0, 1.0), (1, 200.0, 1.0)])

    assert propaccount.replay(lumpy, account()).runs[0].passed
    assert not propaccount.replay(lumpy, account(consistency_ratio=0.5)).runs[0].passed


def test_an_even_account_passes_the_same_consistency_ratio() -> None:
    even = leg_log([(day, 1_000.0, 1.0) for day in range(3)])
    run = propaccount.replay(even, account(consistency_ratio=0.5)).runs[0]

    assert run.passed
    assert run.consistency == pytest.approx(1 / 3)


def test_minimum_trading_days_blocks_a_pass_made_in_too_few() -> None:
    quick = leg_log([(0, 3_000.0, 1.0)])

    assert propaccount.replay(quick, account()).runs[0].passed
    assert not propaccount.replay(quick, account(minimum_trading_days=5)).runs[0].passed


def test_a_withdrawal_leaves_the_safety_net_behind() -> None:
    log = leg_log([(day, 1_500.0, 1.0) for day in range(3)])
    run = propaccount.replay(log, account(withdrawal_threshold=1_000.0)).runs[0]

    assert run.passed
    assert run.final_balance == pytest.approx(51_000.0)
    assert run.withdrawn == pytest.approx(3_500.0)


def test_a_losing_day_after_the_pass_withdraws_nothing_rather_than_a_negative() -> None:
    """Below the safety net there is nothing to take out, and taking it out backwards is worse."""
    log = leg_log([(0, 3_000.0, 1.0), (1, -800.0, 1.0)])
    run = propaccount.replay(log, account(withdrawal_threshold=1_000.0)).runs[0]

    assert run.passed
    assert run.withdrawn == pytest.approx(2_000.0)
    assert run.final_balance == pytest.approx(50_200.0)


def test_a_flat_account_fails_a_consistency_rule_even_at_a_zero_target() -> None:
    """No profit is not evenly distributed profit, and dividing by it would say otherwise."""
    flat = leg_log([(0, 0.0, 1.0)])

    assert propaccount.replay(flat, account(profit_target=0.0)).runs[0].passed
    assert not propaccount.replay(flat, account(profit_target=0.0, consistency_ratio=0.5)).runs[0].passed


def test_nothing_is_withdrawn_before_the_account_passes() -> None:
    log = leg_log([(0, 1_000.0, 1.0)])
    run = propaccount.replay(log, account(withdrawal_threshold=0.0)).runs[0]

    assert not run.passed
    assert run.withdrawn == 0.0
    assert run.final_balance == pytest.approx(51_000.0)
    assert run.first_withdrawal_on is None
    assert run.as_dict()["first_withdrawal_on"] is None


def test_the_first_withdrawal_is_dated_by_the_day_it_was_taken_and_not_by_the_pass() -> None:
    """The pass on day 0 leaves nothing above the safety net, so the first money out is day 2's."""
    log = leg_log([(0, 3_000.0, 1.0), (1, -500.0, 1.0), (2, 2_000.0, 1.0), (3, 1_000.0, 1.0)])
    run = propaccount.replay(log, account(withdrawal_threshold=3_000.0)).runs[0]

    assert run.passed_on == dt.date(2024, 1, 2)
    assert run.first_withdrawal_on == dt.date(2024, 1, 4)
    assert run.as_dict()["first_withdrawal_on"] == "2024-01-04"


# -- the daily loss limit ------------------------------------------------------


def test_a_lockout_skips_the_rest_of_the_day_and_trades_on_tomorrow() -> None:
    log = leg_log([(0, -600.0, 1.0), (0, -600.0, 1.0), (0, -600.0, 1.0), (1, 200.0, 1.0)])
    run = propaccount.replay(
        log,
        account(
            daily_loss_limit=1_000.0,
            on_daily_breach=DailyBreach.LOCKOUT,
            trailing_threshold=0.0,
        ),
    ).runs[0]

    assert run.outcome is Outcome.SURVIVED
    assert run.trades_taken == 3
    assert run.trades_skipped == 1
    assert run.locked_out_days == 1
    assert run.final_balance == pytest.approx(49_000.0)


def test_the_same_breach_ends_the_account_under_the_other_setting() -> None:
    log = leg_log([(0, -600.0, 1.0), (0, -600.0, 1.0), (0, -600.0, 1.0), (1, 200.0, 1.0)])
    run = propaccount.replay(
        log,
        account(daily_loss_limit=1_000.0, on_daily_breach=DailyBreach.FAIL, trailing_threshold=0.0),
    ).runs[0]

    assert run.outcome is Outcome.BREACHED_DAILY_LOSS
    assert run.trades_taken == 2


def test_the_daily_loss_limit_measures_from_the_day_it_is_in() -> None:
    """Yesterday's loss does not count against today's limit."""
    log = leg_log([(0, -900.0, 1.0), (1, -900.0, 1.0)])
    run = propaccount.replay(
        log,
        account(daily_loss_limit=1_000.0, trailing_threshold=0.0),
    ).runs[0]

    assert run.outcome is Outcome.SURVIVED
    assert run.days_traded == 2


# -- the trailing floor and its lock -------------------------------------------


def test_the_floor_follows_the_high_water_mark_when_it_never_locks() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(5)])
    # Out of reach of the profit target, so no withdrawal moves the balance under the floor.
    run = propaccount.replay(log, account(trail_lock=TrailLock.NEVER, profit_target=1e6)).runs[0]

    assert run.peak_balance == pytest.approx(55_000.0)
    assert run.trailing_floor == pytest.approx(53_000.0)


def test_the_floor_freezes_at_the_starting_balance_under_that_lock() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(5)])
    run = propaccount.replay(
        log,
        account(trail_lock=TrailLock.AT_STARTING_BALANCE, profit_target=1e6),
    ).runs[0]

    assert run.peak_balance == pytest.approx(55_000.0)
    assert run.trailing_floor == pytest.approx(50_000.0)


def test_the_floor_freezes_above_the_starting_balance_under_the_buffered_lock() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(5)])
    run = propaccount.replay(
        log,
        account(
            trail_lock=TrailLock.ABOVE_STARTING_BALANCE,
            trail_lock_buffer=100.0,
            profit_target=1e6,
        ),
    ).runs[0]

    assert run.trailing_floor == pytest.approx(50_100.0)


def test_a_zero_threshold_disables_trailing_entirely() -> None:
    log = leg_log([(0, -40_000.0, 1.0), (1, 100.0, 1.0)])
    run = propaccount.replay(log, account(trailing_threshold=0.0)).runs[0]

    assert run.outcome is Outcome.SURVIVED
    assert run.trailing_floor == float("-inf")


def test_the_headroom_reports_how_close_the_account_came() -> None:
    log = leg_log([(0, -1_500.0, 1.0)])
    run = propaccount.replay(log, account()).runs[0]

    assert run.outcome is Outcome.SURVIVED
    assert run.floor_headroom == pytest.approx(500.0)


# -- the trading day is the exchange's, not the calendar's ---------------------


def test_two_trades_either_side_of_the_session_close_are_two_trading_days() -> None:
    """21:00 UTC is 16:00 in New York and 23:00 UTC is 18:00, so the session has turned over."""
    log = leg_log([(0, -900.0, 1.0), (0, -900.0, 1.0)])
    log.loc[0, "exit_time"] = pd.Timestamp("2024-01-02 21:00", tz="UTC")
    log.loc[1, "exit_time"] = pd.Timestamp("2024-01-02 23:00", tz="UTC")

    run = propaccount.replay(log, account(daily_loss_limit=1_000.0, trailing_threshold=0.0)).runs[0]

    assert run.outcome is Outcome.SURVIVED
    assert run.days_traded == 2
    # And the half that stops this being a tautology: they share a calendar date.
    assert log["exit_time"].dt.date.nunique() == 1  # noqa: PD101 - a count of one also fails an empty frame


def test_two_trades_inside_one_session_are_one_trading_day() -> None:
    log = leg_log([(0, -900.0, 1.0), (0, -900.0, 1.0)])
    log.loc[0, "exit_time"] = pd.Timestamp("2024-01-02 15:00", tz="UTC")
    log.loc[1, "exit_time"] = pd.Timestamp("2024-01-02 20:00", tz="UTC")

    run = propaccount.replay(log, account(daily_loss_limit=1_000.0, trailing_threshold=0.0)).runs[0]

    assert run.outcome is Outcome.BREACHED_DAILY_LOSS
    assert run.days_traded == 1


# -- the size limit --------------------------------------------------------------


def resized(log: pd.DataFrame, quantities: Sequence[int], *, instrument: str = "MNQ") -> pd.DataFrame:
    """Return ``log`` with each trade's quantity replaced, in trade order."""
    changed = log.copy()
    changed["quantity"] = list(quantities)
    changed["instrument"] = instrument

    return changed


def test_a_trade_over_the_size_limit_is_rejected_and_never_taken() -> None:
    log = leg_log([(0, 500.0, 1.0), (0, 700.0, 1.0)])
    result = propaccount.replay(resized(log, [3, 5]), account(max_contracts=0.4))

    assert result.runs[0].trades_rejected == result.trades_rejected == 1
    assert result.trades_taken == 1
    assert result.runs[0].final_balance == pytest.approx(50_500.0)


def test_a_micro_counts_as_its_share_of_a_mini_against_the_limit() -> None:
    """Four micros sit exactly on a 0.4 limit; four minis are ten times over it."""
    log = leg_log([(0, 500.0, 1.0)])

    assert propaccount.replay(log, account(max_contracts=0.4)).trades_taken == 1
    assert (
        propaccount.replay(resized(log, [4], instrument="NQ"), account(max_contracts=0.4)).trades_taken == 0
    )


def test_a_day_whose_every_trade_is_rejected_is_not_a_day_traded() -> None:
    log = resized(leg_log([(0, 500.0, 1.0), (1, 500.0, 1.0)]), [5, 3])
    run = propaccount.replay(log, account(max_contracts=0.4)).runs[0]

    assert run.days_traded == 1
    assert run.first_day == dt.date(2024, 1, 2)


SCALING = (propaccount.ScalingTier(0.0, 0.3), propaccount.ScalingTier(500.0, 0.5))
"""A 3-lot limit until the account opens a session 500 up, then a 5-lot one."""


def test_the_scaling_plan_reads_the_profit_the_session_opened_on() -> None:
    """The second trade comes after the account is 600 up, and is still refused that day."""
    log = resized(leg_log([(0, 600.0, 1.0), (0, 100.0, 1.0), (1, 100.0, 1.0)]), [3, 5, 5])
    result = propaccount.replay(log, account(scaling_plan=SCALING))

    assert result.trades_rejected == 1
    assert result.runs[0].final_balance == pytest.approx(50_700.0)


def test_the_first_rung_of_a_scaling_plan_also_covers_a_loss() -> None:
    log = resized(leg_log([(0, -300.0, 1.0), (1, 100.0, 1.0)]), [3, 3])

    assert propaccount.replay(log, account(scaling_plan=SCALING)).trades_rejected == 0


def test_the_lower_of_the_two_limits_binds() -> None:
    log = resized(leg_log([(0, 600.0, 1.0), (1, 100.0, 1.0)]), [3, 5])
    result = propaccount.replay(log, account(scaling_plan=SCALING, max_contracts=0.4))

    assert result.trades_rejected == 1


def test_a_rule_set_with_no_size_limit_never_looks_the_contract_up() -> None:
    """A closed-P&L replay reads no instrument figure, so an unregistered root still replays."""
    log = leg_log([(0, 500.0, 1.0)], instrument="ZZZ")

    assert propaccount.replay(log, account()).trades_taken == 1
    with pytest.raises(KeyError, match="ZZZ"):
        propaccount.replay(log, account(max_contracts=1.0))


@pytest.mark.parametrize(
    "plan",
    [
        (propaccount.ScalingTier(100.0, 1.0),),
        (propaccount.ScalingTier(0.0, 1.0), propaccount.ScalingTier(0.0, 2.0)),
        (propaccount.ScalingTier(0.0, 1.0), propaccount.ScalingTier(500.0, 0.0)),
    ],
    ids=["not from zero", "not rising", "no position"],
)
def test_a_scaling_plan_that_cannot_be_read_is_refused(plan: tuple[propaccount.ScalingTier, ...]) -> None:
    with pytest.raises(PropAccountError, match="scaling_plan"):
        account(scaling_plan=plan)


# -- the days an evaluation has to pass in ---------------------------------------


def test_an_evaluation_that_has_not_passed_in_its_days_expires() -> None:
    """Opened on 2 January with seven days, it cannot trade on the 9th; the next one opens there."""
    log = leg_log([(day, 100.0, 1.0) for day in range(10)])
    result = propaccount.replay(log, account(evaluation_days=7), max_accounts=5)

    assert result.runs[0].outcome is Outcome.EXPIRED
    assert result.runs[0].last_day == dt.date(2024, 1, 8)
    assert result.runs[1].first_day == dt.date(2024, 1, 9)


def test_an_expiry_ends_the_attempt_without_counting_as_a_breach() -> None:
    log = leg_log([(day, 100.0, 1.0) for day in range(10)])
    result = propaccount.replay(log, account(evaluation_days=7), max_accounts=5)

    assert (result.attempts, result.passes, result.breaches) == (2, 0, 0)


def test_an_account_that_passed_in_time_never_expires() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(12)])
    run = propaccount.replay(log, paying(evaluation_days=7)).runs[0]

    assert run.passed_on == dt.date(2024, 1, 4)
    assert run.outcome is Outcome.SURVIVED
    assert run.last_day == dt.date(2024, 1, 13)


# -- the payout rules ------------------------------------------------------------


def funded_account(**overrides: object) -> PropAccount:
    """Build a funded account: no target, so it may pay out from its first profitable day."""
    fields = {
        "profit_target": 0.0,
        "withdrawal_threshold": 1_000.0,
        "trail_lock": TrailLock.AT_STARTING_BALANCE,
    }

    return account(**(fields | overrides))


def test_a_payout_waits_for_its_qualifying_days() -> None:
    """Only the days making 150 count, so the payout waits for the third of them."""
    log = leg_log([(0, 1_500.0, 1.0), (1, 100.0, 1.0), (2, 200.0, 1.0), (3, 300.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_days=3, payout_day_profit=150.0)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 5)]


def test_a_qualifying_day_with_no_profit_floor_is_any_day_traded() -> None:
    log = leg_log([(0, 1_500.0, 1.0), (1, -100.0, 1.0), (2, 100.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_days=3)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 4)]


def test_the_qualifying_days_start_again_after_each_payout() -> None:
    log = leg_log([(day, 1_200.0, 1.0) for day in range(4)])
    run = propaccount.replay(log, funded_account(payout_days=2)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 3), dt.date(2024, 1, 5)]


def test_a_payout_takes_no_more_than_its_share_of_the_profit() -> None:
    log = leg_log([(0, 3_000.0, 1.0)])
    run = propaccount.replay(log, funded_account(withdrawal_threshold=0.0, payout_share=0.5)).runs[0]

    assert run.withdrawn == pytest.approx(1_500.0)


def test_a_payout_takes_no_more_than_its_cap() -> None:
    log = leg_log([(0, 5_000.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_cap=1_500.0)).runs[0]

    assert run.withdrawn == pytest.approx(1_500.0)


def test_a_payout_below_the_minimum_waits_for_more() -> None:
    log = leg_log([(0, 1_300.0, 1.0), (1, 300.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_minimum=500.0)).runs[0]

    assert [(taken.day, taken.withdrawn) for taken in run.withdrawals] == [(dt.date(2024, 1, 3), 600.0)]


def test_the_payout_consistency_reads_only_the_days_since_the_last_payout() -> None:
    """Day 0's 3,000 is most of what the account holds after its first payout, and is not read."""
    log = leg_log([(0, 3_000.0, 1.0), (1, 2_500.0, 1.0), (2, 600.0, 1.0), (3, 600.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_consistency=0.6)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 3), dt.date(2024, 1, 5)]


def test_the_profit_goal_counts_from_the_last_payout() -> None:
    log = leg_log([(0, 1_600.0, 1.0), (1, 400.0, 1.0), (2, 200.0, 1.0)])
    run = propaccount.replay(log, funded_account(payout_profit_goal=500.0)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 2), dt.date(2024, 1, 4)]


def test_a_losing_cycle_pays_nothing_under_a_positive_goal() -> None:
    """Half the balance is still above the floor after the loss, which a share alone would pay."""
    log = leg_log([(0, 2_000.0, 1.0), (1, -200.0, 1.0)])
    rules = {"withdrawal_threshold": 0.0, "payout_share": 0.5}

    assert len(propaccount.replay(log, funded_account(**rules)).runs[0].withdrawals) == 2
    assert (
        len(propaccount.replay(log, funded_account(**rules, payout_profit_goal=0.01)).runs[0].withdrawals)
        == 1
    )


def test_the_first_payout_moves_the_floor_straight_to_its_lock() -> None:
    """Before the payout the floor sits 2,000 under a 51,000 mark; after it, at the start."""
    log = leg_log([(0, 1_000.0, 1.0), (1, -600.0, 1.0)])
    rules = {"withdrawal_threshold": 0.0, "payout_share": 0.5}
    kept = propaccount.replay(log, funded_account(**rules)).runs[0]
    locked = propaccount.replay(log, funded_account(**rules, floor_locks_at_payout=True)).runs[0]

    assert kept.trailing_floor == pytest.approx(49_000.0)
    assert locked.trailing_floor == pytest.approx(50_000.0)
    assert locked.outcome is Outcome.BREACHED_TRAILING
    assert kept.outcome is Outcome.SURVIVED


def test_a_payout_that_locks_the_floor_never_leaves_the_balance_below_it() -> None:
    """Without the lock's own buffer kept back, the payout would end 100 under its new floor."""
    log = leg_log([(0, 1_000.0, 1.0), (1, 500.0, 1.0)])
    rules = {
        "withdrawal_threshold": 0.0,
        "trail_lock": TrailLock.ABOVE_STARTING_BALANCE,
        "trail_lock_buffer": 100.0,
        "floor_locks_at_payout": True,
    }
    run = propaccount.replay(log, funded_account(**rules)).runs[0]

    assert run.withdrawals[0].withdrawn == pytest.approx(900.0)
    assert run.outcome is Outcome.SURVIVED
    assert run.final_balance >= run.trailing_floor == pytest.approx(50_100.0)


def test_the_last_payout_moves_the_account_live() -> None:
    log = leg_log([(day, 1_200.0, 1.0) for day in range(5)])
    run = propaccount.replay(log, funded_account(max_payouts=2)).runs[0]

    assert run.outcome is Outcome.MOVED_LIVE
    assert len(run.withdrawals) == 2
    assert run.last_day == dt.date(2024, 1, 3)


def test_a_day_at_the_profit_cap_moves_the_account_live_after_its_payout() -> None:
    log = leg_log([(0, 500.0, 1.0), (1, 2_000.0, 1.0), (2, 100.0, 1.0)])
    run = propaccount.replay(log, funded_account(daily_profit_cap=2_000.0)).runs[0]

    assert run.outcome is Outcome.MOVED_LIVE
    assert run.last_day == dt.date(2024, 1, 3)
    assert run.withdrawn == pytest.approx(1_500.0)


def test_a_funded_account_that_moves_live_buys_a_new_evaluation_without_a_breach() -> None:
    log = leg_log([*PASS_THEN_TRADE[:3], (3, 1_200.0, 1.0), (4, 100.0, 1.0)])
    result = propaccount.replay(log, linked(max_payouts=1), max_accounts=5)

    assert [run.account_name for run in result.runs] == ["Eval", "Funded", "Eval"]
    assert result.runs[1].outcome is Outcome.MOVED_LIVE
    assert (result.attempts, result.passes, result.breaches) == (2, 1, 0)


@pytest.mark.parametrize("share", [0.0, -0.5, 1.5])
def test_a_payout_share_outside_its_range_is_refused(share: float) -> None:
    with pytest.raises(PropAccountError, match="payout_share"):
        account(payout_share=share)


def test_a_payout_consistency_above_one_is_refused() -> None:
    with pytest.raises(PropAccountError, match="payout_consistency"):
        account(payout_consistency=1.5)


@pytest.mark.parametrize(
    "rules",
    [
        {"trail_lock": TrailLock.NEVER},
        {"trail_lock": TrailLock.AT_STARTING_BALANCE, "trailing_threshold": 0.0},
    ],
    ids=["never locks", "no floor"],
)
def test_a_floor_that_locks_at_payout_needs_a_lock_to_move_to(rules: dict[str, object]) -> None:
    with pytest.raises(PropAccountError, match="floor_locks_at_payout"):
        account(floor_locks_at_payout=True, **rules)


# -- the presets ---------------------------------------------------------------


@pytest.mark.parametrize("preset", propaccount.PRESETS.values(), ids=lambda a: a.name)
def test_a_preset_withdrawal_cannot_breach_its_own_floor(preset: PropAccount) -> None:
    """The one way the payout rules and `trail_lock` can be set to kill the account.

    A payout that leaves the balance on the locked floor lets the next trade's adverse excursion
    end the account it funded, so a steadily winning path must pay out and never breach.
    """
    if preset.rules.trail_lock is TrailLock.NEVER:
        pytest.skip("an unlocked floor has no fixed level a withdrawal could land on")

    log = leg_log([(day, 400.0, 1.0) for day in range(80)])
    result = propaccount.replay(log, preset, max_accounts=10)

    assert any(run.withdrawals for run in result.runs), "a path that never pays out tests nothing"
    assert result.breaches == 0


@pytest.mark.parametrize("preset", propaccount.PRESETS.values(), ids=lambda a: a.name)
def test_every_preset_replays(preset: PropAccount) -> None:
    log = leg_log([(day, 400.0, 1.0) for day in range(10)])
    result = propaccount.replay(log, preset, max_accounts=2)

    assert result.attempts >= 1
    assert result.summary == stats.summarise(log[log["trade_id"].isin(range(1, 11))])


def test_the_two_apex_trails_disagree_about_what_raises_the_floor() -> None:
    """The reason both are shipped: they are not the same rule with different numbers."""
    for pair in (propaccount.APEX_50K_INTRADAY, propaccount.APEX_150K_INTRADAY):
        assert {pair.evaluation.rules.trail_basis, pair.funded.rules.trail_basis} == {TrailBasis.INTRADAY}

    for pair in (propaccount.APEX_50K_EOD, propaccount.APEX_150K_EOD):
        assert {pair.evaluation.rules.trail_basis, pair.funded.rules.trail_basis} == {TrailBasis.END_OF_DAY}


# TakeProfitTrader's published table, which is what these presets have to reproduce:
# account size, profit target, maximum trailing drawdown.
TPT_TABLE = [
    (propaccount.TPT_25K_TEST, 25_000.0, 1_500.0, 1_500.0),
    (propaccount.TPT_25K_PRO, 25_000.0, 0.0, 1_500.0),
    (propaccount.TPT_50K_TEST, 50_000.0, 3_000.0, 2_000.0),
    (propaccount.TPT_50K_PRO, 50_000.0, 0.0, 2_000.0),
    (propaccount.TPT_150K_TEST, 150_000.0, 9_000.0, 4_500.0),
    (propaccount.TPT_150K_PRO, 150_000.0, 0.0, 4_500.0),
]


@pytest.mark.parametrize(
    ("preset", "balance", "target", "drawdown"),
    TPT_TABLE,
    ids=lambda value: getattr(value, "name", value),
)
def test_a_takeprofittrader_preset_carries_its_published_row(
    preset: PropAccount,
    balance: float,
    target: float,
    drawdown: float,
) -> None:
    """The three figures the firm publishes per account size, checked against the table."""
    assert preset.rules.starting_balance == balance
    assert preset.rules.profit_target == target
    assert preset.rules.trailing_threshold == drawdown


@pytest.mark.parametrize("preset", [row[0] for row in TPT_TABLE], ids=lambda a: a.name)
def test_the_takeprofittrader_buffer_zone_is_its_own_drawdown(preset: PropAccount) -> None:
    """The firm defines the withdrawal floor as the drawdown, rather than as a separate number."""
    assert preset.rules.withdrawal_threshold == preset.rules.trailing_threshold
    assert preset.rules.profit_split == 0.80
    assert preset.rules.trail_lock is TrailLock.AT_STARTING_BALANCE
    assert preset.rules.trail_breach is EquityBasis.UNREALISED


@pytest.mark.parametrize(
    ("test_account", "pro_account"),
    [
        (propaccount.TPT_25K_TEST, propaccount.TPT_25K_PRO),
        (propaccount.TPT_50K_TEST, propaccount.TPT_50K_PRO),
        (propaccount.TPT_150K_TEST, propaccount.TPT_150K_PRO),
    ],
    ids=["25K", "50K", "150K"],
)
def test_takeprofittrader_changes_its_rules_when_the_account_passes(
    test_account: PropAccount,
    pro_account: PropAccount,
) -> None:
    """The reason it ships as two presets: one `AccountRules` cannot hold both phases."""
    assert test_account.rules.trail_basis is TrailBasis.END_OF_DAY
    assert pro_account.rules.trail_basis is TrailBasis.INTRADAY

    # The evaluation's two gates are the funded account's neither.
    assert test_account.rules.consistency_ratio == 0.50
    assert test_account.rules.minimum_trading_days == 3
    assert pro_account.rules.consistency_ratio == 0.0
    assert pro_account.rules.minimum_trading_days == 0


@pytest.mark.parametrize(
    ("test_account", "pro_account"),
    [
        (propaccount.TPT_25K_TEST, propaccount.TPT_25K_PRO),
        (propaccount.TPT_50K_TEST, propaccount.TPT_50K_PRO),
        (propaccount.TPT_150K_TEST, propaccount.TPT_150K_PRO),
    ],
    ids=["25K", "50K", "150K"],
)
def test_a_takeprofittrader_pro_account_carries_no_monthly_fee(
    test_account: PropAccount,
    pro_account: PropAccount,
) -> None:
    """The subscription is the evaluation's; the funded account pays $130 once and nothing more."""
    assert test_account.fees.monthly_fee > 0.0
    assert test_account.fees.monthly_fee_ends_at_pass
    assert pro_account.fees.monthly_fee == 0.0
    assert pro_account.fees.evaluation_fee == 130.0
    assert pro_account.fees.activation_fee == 0.0


def test_a_takeprofittrader_pro_account_may_withdraw_before_it_has_a_target_to_hit() -> None:
    """A funded account withdraws above the buffer from day one, which a zero target expresses."""
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    run = propaccount.replay(log, propaccount.TPT_50K_PRO).runs[0]

    assert run.passed_on == dt.date(2024, 1, 2)
    assert run.withdrawn == pytest.approx(2_000.0)
    assert run.payout == pytest.approx(1_600.0)


# Apex's product cards: size, profit target, drawdown, the evaluation's fee with the coupon
# applied, the activation fee, and the largest position in the evaluation and the PA.
APEX_TABLE = [
    (propaccount.APEX_50K_EOD, 50_000.0, 3_000.0, 2_000.0, 47.20, 129.0, 6.0, 4.0),
    (propaccount.APEX_50K_INTRADAY, 50_000.0, 3_000.0, 2_000.0, 19.92, 99.0, 6.0, 4.0),
    (propaccount.APEX_150K_EOD, 150_000.0, 9_000.0, 4_000.0, 175.20, 159.0, 12.0, 10.0),
    (propaccount.APEX_150K_INTRADAY, 150_000.0, 9_000.0, 4_000.0, 95.20, 149.0, 12.0, 10.0),
]


@pytest.mark.parametrize(
    ("pair", "balance", "target", "drawdown", "fee", "activation", "evaluation_size", "funded_size"),
    APEX_TABLE,
    ids=lambda value: getattr(value, "name", value),
)
def test_an_apex_pair_carries_its_product_card(  # one argument per column of the table
    pair: LinkedAccount,
    balance: float,
    target: float,
    drawdown: float,
    fee: float,
    activation: float,
    evaluation_size: float,
    funded_size: float,
) -> None:
    evaluation, performance = pair.evaluation.rules, pair.funded.rules

    assert evaluation.starting_balance == performance.starting_balance == balance
    assert evaluation.profit_target == target
    assert evaluation.trailing_threshold == performance.trailing_threshold == drawdown
    assert pair.evaluation.fees == AccountFees(evaluation_fee=fee, activation_fee=activation)
    assert evaluation.max_contracts == evaluation_size
    assert performance.max_contracts == performance.scaling_plan[-1].contracts == funded_size


@pytest.mark.parametrize("pair", [row[0] for row in APEX_TABLE], ids=lambda a: a.name)
def test_apex_gives_its_evaluation_thirty_days_and_its_pa_six_payouts(pair: LinkedAccount) -> None:
    evaluation, performance = pair.evaluation.rules, pair.funded.rules

    assert evaluation.evaluation_days == 30
    assert (evaluation.consistency_ratio, evaluation.minimum_trading_days) == (0.0, 0)
    assert (performance.payout_consistency, performance.max_payouts) == (0.50, 6)
    assert performance.withdrawal_threshold == performance.trailing_threshold + propaccount.APEX_LOCK_BUFFER
    assert performance.profit_split == 1.0
    assert performance.on_daily_breach is DailyBreach.LOCKOUT


@pytest.mark.parametrize(
    ("pair", "day_profit", "first_cap"),
    [(propaccount.APEX_50K_EOD, 250.0, 1_500.0), (propaccount.APEX_150K_EOD, 350.0, 2_500.0)],
    ids=lambda value: getattr(value, "name", value),
)
def test_apex_s_end_of_day_pa_carries_its_payout_table(
    pair: LinkedAccount, day_profit: float, first_cap: float
) -> None:
    """Apex's own payout page: five days at the minimum, the drawdown plus 100 kept, 500 at least."""
    rules = pair.funded.rules

    assert (rules.payout_days, rules.payout_day_profit) == (5, day_profit)
    assert rules.payout_cap == first_cap
    assert rules.payout_minimum == 500.0
    assert rules.withdrawal_threshold == rules.trailing_threshold + 100.0


def test_only_apex_s_end_of_day_evaluation_has_a_daily_loss_limit() -> None:
    assert propaccount.APEX_50K_EOD.evaluation.rules.daily_loss_limit == 1_000.0
    assert propaccount.APEX_50K_INTRADAY.evaluation.rules.daily_loss_limit == 0.0
    assert propaccount.APEX_50K_INTRADAY.funded.rules.daily_loss_limit == 1_000.0


def test_an_apex_evaluation_that_has_not_passed_in_thirty_days_buys_another() -> None:
    log = leg_log([(day, 50.0, 1.0) for day in range(40)])
    result = propaccount.replay(log, propaccount.APEX_50K_EOD, max_accounts=5)

    assert result.runs[0].outcome is Outcome.EXPIRED
    assert result.runs[1].first_day == dt.date(2024, 2, 1)
    assert result.fees_paid == pytest.approx(2 * 47.20)


# TopStep's published rows: size, profit target, maximum loss limit, monthly fee, the largest
# position, and the Standard path's largest payout.
TOPSTEP_TABLE = [
    (propaccount.TOPSTEP_50K, 50_000.0, 3_000.0, 2_000.0, 49.0, 5.0, 2_000.0),
    (propaccount.TOPSTEP_150K, 150_000.0, 9_000.0, 4_500.0, 199.0, 15.0, 5_000.0),
]


@pytest.mark.parametrize(
    ("pair", "balance", "target", "drawdown", "monthly", "contracts", "cap"),
    TOPSTEP_TABLE,
    ids=lambda value: getattr(value, "name", value),
)
def test_a_topstep_pair_carries_its_published_row(  # one argument per column of the table
    pair: LinkedAccount,
    balance: float,
    target: float,
    drawdown: float,
    monthly: float,
    contracts: float,
    cap: float,
) -> None:
    combine, express = pair.evaluation.rules, pair.funded.rules

    assert combine.starting_balance == express.starting_balance == balance
    assert combine.profit_target == target
    assert combine.trailing_threshold == express.trailing_threshold == drawdown
    assert pair.evaluation.fees.monthly_fee == monthly
    assert combine.max_contracts == express.max_contracts == express.scaling_plan[-1].contracts == contracts
    assert express.payout_cap == cap


@pytest.mark.parametrize("pair", [row[0] for row in TOPSTEP_TABLE], ids=lambda a: a.name)
def test_topstep_s_express_account_pays_half_its_balance_and_locks_its_floor_there(
    pair: LinkedAccount,
) -> None:
    combine, express = pair.evaluation, pair.funded

    assert combine.rules.consistency_ratio == 0.55
    assert combine.fees.monthly_fee_ends_at_pass
    assert combine.fees.activation_fee == 149.0
    assert (express.rules.payout_days, express.rules.payout_day_profit) == (5, 150.0)
    assert express.rules.payout_share == 0.50
    assert express.rules.floor_locks_at_payout
    assert combine.rules.profit_split == express.rules.profit_split == 0.90
    assert combine.rules.daily_loss_limit == express.rules.daily_loss_limit == 0.0, "optional, and off"


# Lucid's published rows: size, profit target, maximum loss limit, the largest position, and the
# one-time evaluation fee with the coupon applied.
LUCID_TABLE = [
    (propaccount.LUCIDPRO_50K, 50_000.0, 3_000.0, 2_000.0, 4.0, 140.40),
    (propaccount.LUCIDPRO_150K, 150_000.0, 9_000.0, 4_500.0, 10.0, 300.50),
    (propaccount.LUCIDFLEX_50K, 50_000.0, 3_000.0, 2_000.0, 4.0, 105.20),
    (propaccount.LUCIDFLEX_150K, 150_000.0, 9_000.0, 4_500.0, 10.0, 295.40),
    (propaccount.LUCIDDAILY_50K, 50_000.0, 3_000.0, 2_000.0, 4.0, 125.20),
    (propaccount.LUCIDDAILY_150K, 150_000.0, 9_000.0, 4_500.0, 10.0, 280.50),
]


@pytest.mark.parametrize(
    ("pair", "balance", "target", "drawdown", "contracts", "fee"),
    LUCID_TABLE,
    ids=lambda value: getattr(value, "name", value),
)
def test_a_lucid_pair_carries_its_published_row(  # one argument per column of the table
    pair: LinkedAccount,
    balance: float,
    target: float,
    drawdown: float,
    contracts: float,
    fee: float,
) -> None:
    evaluation, held = pair.evaluation.rules, pair.funded.rules

    assert evaluation.starting_balance == held.starting_balance == balance
    assert evaluation.profit_target == target
    assert evaluation.trailing_threshold == held.trailing_threshold == drawdown
    assert evaluation.max_contracts == held.max_contracts == contracts
    assert pair.evaluation.fees == AccountFees(evaluation_fee=fee)
    assert pair.funded.fees == AccountFees(), "Lucid charges nothing to activate"
    assert evaluation.trail_lock_buffer == held.trail_lock_buffer == propaccount.LUCID_LOCK_BUFFER
    assert held.profit_split == 0.90


def test_lucid_s_three_funded_accounts_pay_out_by_three_different_rules() -> None:
    pro = propaccount.LUCIDPRO_50K.funded.rules
    flex = propaccount.LUCIDFLEX_50K.funded.rules
    daily = propaccount.LUCIDDAILY_50K.funded.rules

    assert (pro.withdrawal_threshold, pro.payout_consistency, pro.payout_profit_goal) == (
        2_100.0,
        0.40,
        500.0,
    )
    assert (flex.withdrawal_threshold, flex.payout_share, flex.max_payouts) == (0.0, 0.50, 5)
    assert flex.floor_locks_at_payout
    assert flex.scaling_plan[-1].contracts == flex.max_contracts
    assert daily.trail_basis is TrailBasis.INTRADAY
    assert (daily.daily_profit_cap, daily.payout_cap) == (8_000.0, 0.0)
    assert {pro.trail_basis, flex.trail_basis} == {TrailBasis.END_OF_DAY}


def test_a_preset_is_found_by_name_case_insensitively() -> None:
    assert propaccount.preset("apex 50k eod pa") is propaccount.APEX_50K_EOD.funded
    assert propaccount.preset("  TopStep 150K Combine ") is propaccount.TOPSTEP_150K.evaluation


def test_an_unknown_preset_names_the_ones_that_exist() -> None:
    with pytest.raises(PropAccountError, match="known presets"):
        propaccount.preset("Made Up 25K")


# -- refusals ------------------------------------------------------------------


def test_a_log_missing_a_column_is_refused_by_name() -> None:
    log = leg_log([(0, 100.0, 1.0)]).drop(columns=["quantity"])
    with pytest.raises(PropAccountError, match="quantity"):
        propaccount.replay(log, account())


def test_a_null_excursion_is_refused_rather_than_read_as_zero() -> None:
    """Treating an unknown excursion as no excursion would report a pass the account never had."""
    log = leg_log([(0, 100.0, 1.0)])
    log.loc[0, "mae_points"] = None
    with pytest.raises(PropAccountError, match="mae_points"):
        propaccount.replay(log, account(trail_breach=EquityBasis.UNREALISED))


def test_and_the_same_log_replays_on_closed_pnl_alone() -> None:
    """The refusal above must be about the rule set, not about the log being unusable."""
    log = leg_log([(0, 100.0, 1.0)])
    log.loc[0, "mae_points"] = None

    assert propaccount.replay(log, account()).runs[0].outcome is Outcome.SURVIVED


@pytest.mark.parametrize("count", [0, -1])
def test_fewer_than_one_account_is_refused(count: int) -> None:
    with pytest.raises(PropAccountError, match="max_accounts"):
        propaccount.replay(leg_log([(0, 100.0, 1.0)]), account(), max_accounts=count)


def test_a_consistency_ratio_above_one_is_refused() -> None:
    with pytest.raises(PropAccountError, match=r"cannot exceed 1\.0"):
        account(consistency_ratio=1.5)


@pytest.mark.parametrize("share", [0.0, -0.5, 1.5])
def test_a_profit_split_outside_its_range_is_refused(share: float) -> None:
    """0.0 is refused rather than read as "off", which is the convention every other field uses."""
    with pytest.raises(PropAccountError, match="profit_split"):
        account(profit_split=share)


@pytest.mark.parametrize(
    "field",
    [
        "trailing_threshold",
        "daily_loss_limit",
        "profit_target",
        "withdrawal_threshold",
        "max_contracts",
        "payout_days",
        "payout_cap",
        "payout_minimum",
        "daily_profit_cap",
    ],
)
def test_a_negative_limit_is_refused_by_name(field: str) -> None:
    with pytest.raises(PropAccountError, match=field):
        account(**{field: -1.0})


def test_a_starting_balance_of_zero_is_refused() -> None:
    with pytest.raises(PropAccountError, match="starting_balance"):
        account(starting_balance=0.0)


def test_a_buffer_without_the_lock_that_reads_it_is_refused() -> None:
    with pytest.raises(PropAccountError, match="only read under"):
        account(trail_lock=TrailLock.AT_STARTING_BALANCE, trail_lock_buffer=100.0)


def test_the_buffered_lock_without_a_buffer_is_refused() -> None:
    with pytest.raises(PropAccountError, match="needs a positive trail_lock_buffer"):
        account(trail_lock=TrailLock.ABOVE_STARTING_BALANCE)


def test_a_negative_fee_is_refused() -> None:
    with pytest.raises(PropAccountError, match="cannot be negative"):
        AccountFees(monthly_fee=-1.0)


# -- the edges -----------------------------------------------------------------


def test_an_empty_log_makes_no_attempt_at_all() -> None:
    result = propaccount.replay(leg_log([(0, 100.0, 1.0)]).iloc[:0], account())

    assert result.attempts == 0
    assert result.pass_rate == 0.0
    assert result.summary == stats.Summary.empty()


def test_a_single_trade_replays() -> None:
    run = propaccount.replay(leg_log([(0, 100.0, 1.0)]), account()).runs[0]

    assert run.trades_taken == 1
    assert run.first_day == run.last_day == dt.date(2024, 1, 2)


def test_the_rows_a_report_prints_are_plain_python_values() -> None:
    """A results row goes to DuckDB and a CSV, so a numpy scalar or an enum would leak."""
    log = leg_log([(0, 400.0, 1.0), (1, 100.0, 1.0)])
    result = propaccount.replay(log, account())

    for value in (*result.as_dict().values(), *result.runs[0].as_dict().values()):
        assert value is None or isinstance(value, (str, int, float))


def test_a_frozen_rule_set_can_be_varied_without_touching_the_preset() -> None:
    """`dataclasses.replace` is how a caller overrides a dated preset number."""
    preset = propaccount.APEX_50K_EOD.evaluation
    tighter = dataclasses.replace(preset.rules, trailing_threshold=1_000.0)

    assert tighter.trailing_threshold == 1_000.0
    assert preset.rules.trailing_threshold == 2_000.0


# -- every fee and withdrawal carries its day ----------------------------------


def priced(fees: AccountFees, **overrides: object) -> PropAccount:
    """Build the plain rule set with ``fees`` attached."""
    return PropAccount(name="Test", rules=account(**overrides).rules, fees=fees)


FEE_SCENARIOS = {
    "never passes": [(0, -100.0, 1.0), (40, -100.0, 1.0)],
    "passes and withdraws": [(day, 1_000.0, 1.0) for day in (0, 1, 2, 3, 35, 70)],
    "breaches and reopens": [(0, -2_500.0, 1.0), (1, 1_500.0, 1.0), (2, 1_500.0, 1.0), (33, 500.0, 1.0)],
}


@pytest.mark.parametrize(
    "preset",
    [*propaccount.PRESETS.values(), *propaccount.LINKED_PRESETS.values()],
    ids=lambda a: a.name,
)
@pytest.mark.parametrize("rows", FEE_SCENARIOS.values(), ids=list(FEE_SCENARIOS))
def test_every_preset_s_dated_fees_add_up_to_what_it_paid(
    preset: propaccount.Account,
    rows: list[tuple[int, float, float]],
) -> None:
    """The dated charges are a second derivation of ``fees_paid``, so the two must agree everywhere."""
    result = propaccount.replay(leg_log(rows), preset, max_accounts=10)

    assert result.runs
    for run in result.runs:
        assert sum(charge.amount for charge in run.charges) == pytest.approx(run.fees_paid)


def test_the_entry_fee_and_the_first_month_fall_on_the_opening_day() -> None:
    fees = AccountFees(evaluation_fee=100.0, monthly_fee=50.0)
    run = propaccount.replay(leg_log([(0, -100.0, 1.0)]), priced(fees)).runs[0]

    assert run.charges == (
        Charge(dt.date(2024, 1, 2), 100.0, FeeKind.EVALUATION),
        Charge(dt.date(2024, 1, 2), 50.0, FeeKind.MONTHLY),
    )


def test_each_later_month_is_charged_on_its_first_calendar_day() -> None:
    """2 January to 11 March is three months: the opening day, then 1 February and 1 March."""
    log = leg_log([(0, 10.0, 1.0), (69, 10.0, 1.0)])
    run = propaccount.replay(log, priced(AccountFees(monthly_fee=50.0))).runs[0]

    assert [charge.day for charge in run.charges] == [
        dt.date(2024, 1, 2),
        dt.date(2024, 2, 1),
        dt.date(2024, 3, 1),
    ]


def test_a_monthly_charge_crosses_the_year_end() -> None:
    log = leg_log([(0, 10.0, 1.0), (64, 10.0, 1.0)], start="2024-12-02 15:00")
    run = propaccount.replay(log, priced(AccountFees(monthly_fee=50.0))).runs[0]

    assert [charge.day for charge in run.charges] == [
        dt.date(2024, 12, 2),
        dt.date(2025, 1, 1),
        dt.date(2025, 2, 1),
    ]


def test_the_activation_fee_falls_on_the_day_of_the_pass() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    run = propaccount.replay(log, priced(AccountFees(activation_fee=25.0))).runs[0]

    assert run.passed_on == dt.date(2024, 1, 4)
    assert run.charges == (Charge(dt.date(2024, 1, 4), 25.0, FeeKind.ACTIVATION),)


def test_a_fee_that_costs_nothing_is_not_charged() -> None:
    """TopStep charges no entry fee, so its only charge on the opening day is the month."""
    run = propaccount.replay(leg_log([(0, -100.0, 1.0)]), propaccount.TOPSTEP_50K).runs[0]

    assert [charge.kind for charge in run.charges] == [FeeKind.MONTHLY]


def test_a_monthly_fee_that_ends_at_the_pass_stops_its_dated_charges_there() -> None:
    log = leg_log([(0, 3_000.0, 1.0), (40, 10.0, 1.0)])
    fees = AccountFees(monthly_fee=50.0, monthly_fee_ends_at_pass=True)
    run = propaccount.replay(log, priced(fees)).runs[0]

    assert [charge.day for charge in run.charges] == [dt.date(2024, 1, 2)]


def test_each_withdrawal_carries_its_day_and_adds_up_to_the_totals() -> None:
    log = leg_log([(day, 1_000.0, 1.0) for day in range(4)])
    run = propaccount.replay(log, paying(profit_split=0.80)).runs[0]

    assert [taken.day for taken in run.withdrawals] == [dt.date(2024, 1, 4), dt.date(2024, 1, 5)]
    assert [taken.withdrawn for taken in run.withdrawals] == pytest.approx([2_000.0, 1_000.0])
    assert sum(taken.withdrawn for taken in run.withdrawals) == pytest.approx(run.withdrawn)
    assert sum(taken.payout for taken in run.withdrawals) == pytest.approx(run.payout)
    assert run.first_withdrawal_on == run.withdrawals[0].day


def test_the_dated_money_stays_out_of_a_report_row() -> None:
    """Neither is one value, so a row carries the totals and the tuples stay on the run."""
    run = propaccount.replay(leg_log([(day, 1_000.0, 1.0) for day in range(4)]), paying()).runs[0]
    row = run.as_dict()

    assert run.charges == ()
    assert run.withdrawals
    assert "charges" not in row
    assert "withdrawals" not in row
    assert row["account_name"] == "Test"


# -- an evaluation linked to the funded account its pass opens -----------------


def linked(**funded: object) -> LinkedAccount:
    """Build an evaluation that passes at 3,000, linked to a funded account with no target."""
    evaluation = PropAccount(
        name="Eval",
        rules=account().rules,
        fees=AccountFees(monthly_fee=50.0, activation_fee=130.0, monthly_fee_ends_at_pass=True),
    )
    held = PropAccount(
        name="Funded",
        rules=paying(profit_target=0.0, **funded).rules,
        fees=AccountFees(evaluation_fee=130.0),
    )

    return LinkedAccount(name="Eval+Funded", evaluation=evaluation, funded=held)


PASS_THEN_TRADE = [(0, 1_000.0, 1.0), (1, 1_000.0, 1.0), (2, 1_000.0, 1.0), (3, 500.0, 1.0)]
"""Passes the evaluation on 4 January, then gives the funded account one day of 500."""


def test_a_linked_evaluation_closes_at_its_pass_and_pays_nothing() -> None:
    """Alone, the same evaluation keeps trading and withdraws from its pass day on."""
    log = leg_log(PASS_THEN_TRADE)
    evaluation = propaccount.replay(log, linked()).runs[0]

    assert evaluation.account_name == "Eval"
    assert evaluation.outcome is Outcome.PROMOTED
    assert evaluation.passed_on == evaluation.last_day == dt.date(2024, 1, 4)
    assert evaluation.withdrawals == ()
    assert evaluation.payout == 0.0
    assert propaccount.replay(log, linked().evaluation).runs[0].withdrawn > 0.0


def test_the_funded_account_opens_the_next_trading_day_without_the_evaluation_s_profit() -> None:
    funded = propaccount.replay(leg_log(PASS_THEN_TRADE), linked()).runs[1]

    assert funded.account_name == "Funded"
    assert funded.first_day == dt.date(2024, 1, 5)
    # The evaluation made 3,000; the funded account opens at 50,000 and made 500 of its own.
    assert funded.final_balance + funded.withdrawn == pytest.approx(50_500.0)


def test_the_hand_over_charges_the_shared_fee_once() -> None:
    """The evaluation's activation fee is what opening the funded account costs, not a second fee."""
    result = propaccount.replay(leg_log(PASS_THEN_TRADE), linked())
    charged = [(charge.kind, charge.amount) for run in result.runs for charge in run.charges]

    assert charged == [(FeeKind.MONTHLY, 50.0), (FeeKind.ACTIVATION, 130.0)]
    assert result.fees_paid == pytest.approx(180.0)


def test_a_funded_breach_buys_a_new_evaluation_on_the_next_trading_day() -> None:
    log = leg_log([*PASS_THEN_TRADE[:3], (3, -2_500.0, 1.0), (6, -100.0, 1.0)])
    result = propaccount.replay(log, linked(), max_accounts=5)

    assert [run.account_name for run in result.runs] == ["Eval", "Funded", "Eval"]
    assert result.runs[1].outcome is Outcome.BREACHED_TRAILING
    assert result.runs[2].first_day == dt.date(2024, 1, 8)
    assert (result.attempts, result.passes, result.breaches) == (2, 1, 1)


def test_an_evaluation_breach_buys_another_evaluation() -> None:
    log = leg_log([(0, -2_500.0, 1.0), (1, 100.0, 1.0)])
    result = propaccount.replay(log, linked(), max_accounts=5)

    assert [run.account_name for run in result.runs] == ["Eval", "Eval"]
    assert (result.attempts, result.passes, result.breaches) == (2, 0, 1)


def test_a_funded_account_s_first_profitable_day_is_not_counted_as_a_pass() -> None:
    """A funded account reads "eligible to withdraw" as a pass; the attempt passed once, not twice."""
    result = propaccount.replay(leg_log(PASS_THEN_TRADE), linked())

    assert result.runs[1].passed
    assert (result.attempts, result.passes, result.breaches) == (1, 1, 0)
    assert result.pass_rate == 1.0


def test_a_pass_on_the_log_s_last_day_opens_no_funded_account() -> None:
    result = propaccount.replay(leg_log(PASS_THEN_TRADE[:3]), linked())

    assert [run.account_name for run in result.runs] == ["Eval"]
    assert result.fees_paid == pytest.approx(180.0)


def test_the_attempt_cap_counts_evaluations_bought() -> None:
    log = leg_log([*PASS_THEN_TRADE[:3], (3, -2_500.0, 1.0), (6, -100.0, 1.0)])
    result = propaccount.replay(log, linked(), max_accounts=1)

    assert [run.account_name for run in result.runs] == ["Eval", "Funded"]
    assert result.attempts == 1


def test_a_pair_whose_hand_over_fees_differ_is_refused() -> None:
    pair = linked()
    dearer = dataclasses.replace(pair.funded, fees=AccountFees(evaluation_fee=99.0))
    with pytest.raises(PropAccountError, match="activation fee"):
        LinkedAccount(name="Mismatched", evaluation=pair.evaluation, funded=dearer)


def test_a_pair_whose_accounts_share_a_name_is_refused() -> None:
    pair = linked()
    renamed = dataclasses.replace(pair.funded, name="Eval")
    with pytest.raises(PropAccountError, match="different names"):
        LinkedAccount(name="Shared", evaluation=pair.evaluation, funded=renamed)


def test_a_pair_refuses_a_log_its_funded_account_could_not_read() -> None:
    """The evaluation here reads closed balances; its funded account reads open equity."""
    log = leg_log([(0, 100.0, 1.0)])
    log.loc[0, "mae_points"] = None
    with pytest.raises(PropAccountError, match="mae_points"):
        propaccount.replay(log, linked(trail_breach=EquityBasis.UNREALISED))


@pytest.mark.parametrize("pair", propaccount.LINKED_PRESETS.values(), ids=lambda a: a.name)
def test_a_linked_preset_chains_the_evaluation_and_funded_account_of_one_size(pair: LinkedAccount) -> None:
    size, evaluation = pair.evaluation.name.rsplit(" ", 1)
    funded_size, held = pair.funded.name.rsplit(" ", 1)

    assert size == funded_size
    assert pair.name == f"{size} {evaluation}+{held}"
    assert pair.evaluation.rules.starting_balance == pair.funded.rules.starting_balance
    assert pair.funded.rules.profit_target == 0.0
    assert pair.opened_by_pass.fees.evaluation_fee == 0.0
    assert pair.funded.fees.evaluation_fee == pair.evaluation.fees.activation_fee, (
        "the preset itself is untouched"
    )


@pytest.mark.parametrize("pair", propaccount.LINKED_PRESETS.values(), ids=lambda a: a.name)
def test_every_linked_preset_replays(pair: LinkedAccount) -> None:
    result = propaccount.replay(leg_log([(day, 400.0, 1.0) for day in range(10)]), pair, max_accounts=2)

    assert result.attempts >= 1
    assert result.account_name == pair.name


def test_a_linked_pair_is_found_by_name_beside_the_single_presets() -> None:
    assert propaccount.account_named("takeprofittrader 50k test+pro") is propaccount.TPT_50K
    assert propaccount.account_named("TakeProfitTrader 50K Test") is propaccount.TPT_50K_TEST


def test_an_unknown_name_lists_the_linked_pairs_too() -> None:
    with pytest.raises(PropAccountError, match=r"TakeProfitTrader 50K Test\+PRO"):
        propaccount.account_named("Made Up 25K")


def test_an_attempt_is_bought_as_the_pair_s_evaluation() -> None:
    assert propaccount.evaluation_of(propaccount.TPT_25K) is propaccount.TPT_25K_TEST
    assert propaccount.evaluation_of(propaccount.TPT_25K_TEST) is propaccount.TPT_25K_TEST


# -- opening the first account later than the log's first day ------------------


def test_the_first_account_opens_on_the_first_trading_day_on_or_after_the_start() -> None:
    log = leg_log([(0, 100.0, 1.0), (1, 100.0, 1.0), (6, 100.0, 1.0)])
    result = propaccount.replay(log, account(), start=dt.date(2024, 1, 4))

    assert result.runs[0].first_day == dt.date(2024, 1, 8)
    assert result.trades_taken == result.trades_total == 1


def test_a_start_after_the_log_ends_opens_no_account() -> None:
    result = propaccount.replay(leg_log([(0, 100.0, 1.0)]), linked(), start=dt.date(2024, 2, 1))

    assert result.runs == ()
    assert (result.attempts, result.trades_total, result.net) == (0, 0, 0.0)
