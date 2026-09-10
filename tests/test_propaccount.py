"""Replaying a prop account's rules over a trade log.

Three claims carry this module and each has a test named after it. The **statistics** must stay
`stats.summarise`'s, because a second definition of a win rate here would drift from the sweep's
silently. **Unrealised P&L must decide outcomes a realised replay gets wrong**, which is the
whole reason the module reads `mae_points` at all. And a **blown account must still be able to
be profitable**, because the money already withdrawn is kept.
"""

import dataclasses
import datetime as dt

import pandas as pd
import pytest

from nqbt import instruments, propaccount, stats
from nqbt.propaccount import (
    AccountFees,
    AccountRules,
    DailyBreach,
    EquityBasis,
    Outcome,
    PropAccount,
    PropAccountError,
    TrailBasis,
    TrailLock,
)

# MNQ is $2 a point, so one 4-lot moves $8 for every point of excursion. Every dollar figure
# below is derived from that rather than written out, so a tick-value change cannot pass here.
LOTS = 4
MNQ_PER_POINT = instruments.MNQ.point_value * LOTS
COMMISSION = 6.0


def leg_log(rows, *, instrument: str = "MNQ", start: str = "2024-01-02 15:00") -> pd.DataFrame:
    """A one-leg-per-trade log from ``(day_offset, net_pnl, mae_points)`` triples.

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


def account(**overrides) -> PropAccount:
    """A deliberately plain rule set, so each test switches on exactly the field it names."""
    fields = {
        "starting_balance": 50_000.0,
        "profit_target": 3_000.0,
        "trailing_threshold": 2_000.0,
        "trail_basis": TrailBasis.END_OF_DAY,
        "trail_breach": EquityBasis.REALISED,
        "daily_loss_basis": EquityBasis.REALISED,
    }

    return PropAccount(name="Test", rules=AccountRules(**(fields | overrides)))


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


def _dips_but_wins(mae_points: float):
    """One profitable trade that first goes ``mae_points`` against, then a quiet second day."""
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


def _spikes_then_dips():
    """One trade that runs $3,000 in favour and $1,000 against, under Apex's geometry.

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


def _intraday(**overrides) -> PropAccount:
    """Apex's trailing geometry: an intraday mark and a floor that locks just above the start."""
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
    """The measured lever, pinned: §M28.13 is the difference between one trade and twelve."""
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
    assert run.trailing_floor > propaccount.APEX_50K.rules.starting_balance


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


def paying(**overrides) -> PropAccount:
    """A rule set that passes and then withdraws without walking onto its own floor."""
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
    assert log["exit_time"].dt.date.nunique() == 1


def test_two_trades_inside_one_session_are_one_trading_day() -> None:
    log = leg_log([(0, -900.0, 1.0), (0, -900.0, 1.0)])
    log.loc[0, "exit_time"] = pd.Timestamp("2024-01-02 15:00", tz="UTC")
    log.loc[1, "exit_time"] = pd.Timestamp("2024-01-02 20:00", tz="UTC")

    run = propaccount.replay(log, account(daily_loss_limit=1_000.0, trailing_threshold=0.0)).runs[0]

    assert run.outcome is Outcome.BREACHED_DAILY_LOSS
    assert run.days_traded == 1


# -- the presets ---------------------------------------------------------------


@pytest.mark.parametrize("preset", propaccount.PRESETS.values(), ids=lambda a: a.name)
def test_a_preset_withdrawal_cannot_breach_its_own_floor(preset) -> None:
    """The one way `withdrawal_threshold` and `trail_lock` can be set to kill the account."""
    rules = preset.rules
    if rules.trail_lock is TrailLock.NEVER:
        pytest.skip("an unlocked floor has no fixed level a withdrawal could land on")

    locked = rules.starting_balance + rules.trail_lock_buffer

    assert rules.starting_balance + rules.withdrawal_threshold > locked


@pytest.mark.parametrize("preset", propaccount.PRESETS.values(), ids=lambda a: a.name)
def test_every_preset_replays(preset) -> None:
    log = leg_log([(day, 400.0, 1.0) for day in range(10)])
    result = propaccount.replay(log, preset, max_accounts=2)

    assert result.attempts >= 1
    assert result.summary == stats.summarise(log[log["trade_id"].isin(range(1, 11))])


def test_the_two_firms_disagree_about_what_raises_the_floor() -> None:
    """The reason both are shipped: they are not the same rule with different numbers."""
    assert propaccount.APEX_50K.rules.trail_basis is TrailBasis.INTRADAY
    assert propaccount.TOPSTEP_50K.rules.trail_basis is TrailBasis.END_OF_DAY


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
    preset,
    balance,
    target,
    drawdown,
) -> None:
    """The three figures the firm publishes per account size, checked against the table."""
    assert preset.rules.starting_balance == balance
    assert preset.rules.profit_target == target
    assert preset.rules.trailing_threshold == drawdown


@pytest.mark.parametrize("preset", [row[0] for row in TPT_TABLE], ids=lambda a: a.name)
def test_the_takeprofittrader_buffer_zone_is_its_own_drawdown(preset) -> None:
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
    test_account,
    pro_account,
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
    test_account,
    pro_account,
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


def test_a_preset_is_found_by_name_case_insensitively() -> None:
    assert propaccount.preset("apex 50k") is propaccount.APEX_50K
    assert propaccount.preset("  TopStep 150K ") is propaccount.TOPSTEP_150K


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
def test_fewer_than_one_account_is_refused(count) -> None:
    with pytest.raises(PropAccountError, match="max_accounts"):
        propaccount.replay(leg_log([(0, 100.0, 1.0)]), account(), max_accounts=count)


def test_a_consistency_ratio_above_one_is_refused() -> None:
    with pytest.raises(PropAccountError, match="cannot exceed 1.0"):
        account(consistency_ratio=1.5)


@pytest.mark.parametrize("share", [0.0, -0.5, 1.5])
def test_a_profit_split_outside_its_range_is_refused(share) -> None:
    """0.0 is refused rather than read as "off", which is the convention every other field uses."""
    with pytest.raises(PropAccountError, match="profit_split"):
        account(profit_split=share)


@pytest.mark.parametrize(
    "field",
    ["trailing_threshold", "daily_loss_limit", "profit_target", "withdrawal_threshold"],
)
def test_a_negative_limit_is_refused_by_name(field) -> None:
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
    tighter = dataclasses.replace(propaccount.APEX_50K.rules, trailing_threshold=1_000.0)

    assert tighter.trailing_threshold == 1_000.0
    assert propaccount.APEX_50K.rules.trailing_threshold == 2_500.0
