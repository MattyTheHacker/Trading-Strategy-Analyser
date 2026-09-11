"""Reading a campaign shortlist through a prop firm's account rules.

Three things carry this module. The **attempt cap must not bind by default**, because §M28.13's
capped population run was truncated badly enough to be wrong in sign and a truncated net looks
exactly like a small one. A row the rules **refuse** has to be named rather than dropped, since
a table of three presets where four were asked for reads as a firm that was never offered. And
the **position size** has to reach the report, because four contracts is a different bet on each
root and it is what decides whether an account has room to move at all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import propaccount, results
from tools import campaign_propaccount
from tools.campaign_propaccount import (
    CONTRACTS,
    REPORTED,
    contracts_per_trade,
    labelled,
    main,
    replay_row,
    replay_shortlist,
    rules_with,
    uncapped,
    verdict,
)

SWEEP_ID = 58
COMBO_ID = 1473
LEGS = 4
"""Legs per trade, which is the campaign's own four contracts one lot at a time."""


def stored_row(**columns: object) -> pd.Series:
    """One held-out row, carrying the tags a result is filed under."""
    base = {
        "sweep_id": SWEEP_ID,
        "combo_id": COMBO_ID,
        "root": "MNQ",
        "resolution": 5,
        "variant": "window=30m stop=opposite target=R",
        "stratum": "phase=MIDDAY",
        "window": "holdout",
        "profit_factor": 1.236,
    }

    return pd.Series({**base, **columns})


def leg_log(daily: list[float], *, legs: int = LEGS, excursions: bool = True) -> pd.DataFrame:
    """A leg-level log, one trade per trading day, from each day's total net P&L.

    Each trade is ``legs`` lots wide and closes mid-afternoon, so a day's P&L is what the
    account sees and no trade straddles a session boundary.
    """
    n = len(daily)
    pnl = np.repeat(np.asarray(daily, dtype=float) / legs, legs)
    exits = pd.Timestamp("2024-09-03 18:00", tz="UTC") + pd.to_timedelta(
        np.repeat(np.arange(n), legs),
        unit="D",
    )
    excursion = 4.0 if excursions else np.nan

    return pd.DataFrame(
        {
            "source": "sim",
            "instrument": "MNQ",
            "trade_id": np.repeat(np.arange(1, n + 1), legs),
            "leg": np.tile(np.arange(1, legs + 1), n),
            "quantity": 1,
            "direction": 1.0,
            "gross_pnl": pnl + 1.5,
            "commission": 1.5,
            "net_pnl": pnl,
            "bars_held": 60,
            "mae_points": excursion,
            "mfe_points": excursion,
            "r_multiple": pnl / 200.0,
            "ambiguous_bar": False,
            "exit_reason": "session_close",
            "entry_time": exits - pd.Timedelta(hours=5),
            "exit_time": exits,
        },
    )


def trade_log(n: int = 40, *, legs: int = LEGS, excursions: bool = True) -> pd.DataFrame:
    """A log of ``n`` mildly profitable days, which one Apex 50K survives."""
    rng = np.random.default_rng(11)

    return leg_log(list(rng.normal(240.0, 900.0, n)), legs=legs, excursions=excursions)


CYCLE = [700.0] * 8 + [-6_000.0]
"""One account's life: eight days that fund it, then one that breaches the floor.

Eight at 700 clears Apex 50K's 3,000 target and its seven-day minimum, and the best day is
12.5% of the profit, so the 30% consistency rule is met too.
"""


def cycling_log(cycles: int = 4) -> pd.DataFrame:
    """A log that funds, withdraws from and then blows one account after another."""
    return leg_log(CYCLE * cycles)


@pytest.fixture
def stocked(tmp_path):
    """A database holding one stored log, at the ids the held-out row names."""
    db = tmp_path / "OpeningRange.duckdb"
    results.save_trades(trade_log(), SWEEP_ID, COMBO_ID, db)

    return db


def apex() -> propaccount.PropAccount:
    return propaccount.preset("Apex 50K")


# -- the cap that must not bind --------------------------------------------------------------


def test_the_default_cap_cannot_bind_on_any_log() -> None:
    """Each attempt consumes at least one trading day and a day holds at least one trade, so
    the trade count bounds the attempts -- ``docs/roadmap.md`` §M28.13."""
    log = trade_log(n=30)
    assert uncapped(log) == 30
    result = propaccount.replay(log, apex(), max_accounts=uncapped(log))
    assert result.attempts < uncapped(log)


def test_a_log_with_one_trade_still_gets_an_attempt() -> None:
    """``replay`` refuses ``max_accounts`` below 1, so a floor of one is the tool's and not
    a coincidence of the arithmetic."""
    assert uncapped(trade_log(n=1)) == 1


def test_a_cap_that_binds_is_reported_rather_than_left_to_be_noticed() -> None:
    """§M28.13's five-attempt cap bound on 98% of its population and truncated their net
    figures; a truncated net reads exactly like a small one unless the row says so."""
    log = cycling_log()
    capped = replay_row(stored_row(), log, apex(), 2)
    assert capped is not None
    assert capped["capped"]
    assert capped["attempts"] == 2

    loose = replay_row(stored_row(), log, apex(), uncapped(log))
    assert loose is not None
    assert not loose["capped"]
    assert loose["attempts"] > 2


def test_stopping_early_understates_what_the_sequence_was_worth() -> None:
    """Why the cap matters at all: a blown account costs its fees and not its trading losses,
    so the attempts after the cap are where the withdrawals are."""
    log = cycling_log()
    capped = replay_row(stored_row(), log, apex(), 1)
    loose = replay_row(stored_row(), log, apex(), uncapped(log))
    assert capped is not None
    assert loose is not None
    assert loose["withdrawn"] > capped["withdrawn"]
    assert loose["passes"] > capped["passes"]


# -- what a row says -------------------------------------------------------------------------


def test_a_replay_row_carries_the_tags_of_the_configuration_it_came_from() -> None:
    assert labelled(stored_row())["stratum"] == "phase=MIDDAY"
    assert labelled(stored_row())["combo_id"] == COMBO_ID
    assert "profit_factor" not in labelled(stored_row()), "a statistic is not a tag"


def test_the_position_size_the_account_faced_reaches_the_row() -> None:
    """The binding constraint §M28.13 measured is contracts, not the entry rule: the trailing
    threshold over the dollar value of a point is the whole account's room to move."""
    assert contracts_per_trade(trade_log(legs=4)) == pytest.approx(4.0)
    assert contracts_per_trade(trade_log(legs=1)) == pytest.approx(1.0)

    row = replay_row(stored_row(), trade_log(), apex(), 5)
    assert row is not None
    assert row[CONTRACTS] == pytest.approx(float(LEGS))


def test_the_lifetime_figures_are_the_replay_s_own_and_not_re_derived() -> None:
    """``propaccount`` defines the account's figures; a second arithmetic here would drift."""
    log = trade_log()
    row = replay_row(stored_row(), log, apex(), 5)
    result = propaccount.replay(log, apex(), max_accounts=5)
    assert row is not None
    for field in REPORTED:
        assert row[field] == result.as_dict()[field]

    assert row["net"] == pytest.approx(result.payout - result.fees_paid)


def test_the_held_out_profit_factor_travels_beside_the_account_verdict() -> None:
    """``net`` rewards variance and can rank a losing configuration above a winning one, so
    the row it must be read beside is on the same line -- ``docs/roadmap.md`` §M28.13."""
    row = replay_row(stored_row(), trade_log(), apex(), 5)
    assert row is not None
    assert row["held_pf"] == pytest.approx(1.236)


# -- refusals and absences -------------------------------------------------------------------


def test_a_rule_set_that_refuses_the_log_is_named_rather_than_reported() -> None:
    """Apex trails intraday, so it reads open equity; a log with no excursions cannot answer
    it and reading "unknown" as "none" would report a pass the account never had."""
    assert replay_row(stored_row(), trade_log(excursions=False), apex(), 5) is None


def closed_book() -> propaccount.PropAccount:
    """A rule set measured on closed balances alone, which no shipped preset is.

    All four presets §M28.13 read the registry through breach on open equity, so this is what
    a refusal is compared against rather than a second preset.
    """
    return propaccount.PropAccount(
        name="Closed-book",
        rules=propaccount.AccountRules(
            starting_balance=50_000.0,
            profit_target=3_000.0,
            trailing_threshold=2_500.0,
            trail_basis=propaccount.TrailBasis.END_OF_DAY,
            trail_breach=propaccount.EquityBasis.REALISED,
            daily_loss_basis=propaccount.EquityBasis.REALISED,
        ),
    )


def test_a_refusal_costs_only_its_own_rule_set(tmp_path) -> None:
    """A rule set reading closed balances can answer a log Apex cannot, and a table that
    dropped both would read as a firm nobody offered."""
    db = tmp_path / "OpeningRange.duckdb"
    results.save_trades(trade_log(excursions=False), SWEEP_ID, COMBO_ID, db)
    table = replay_shortlist(pd.DataFrame([stored_row()]), db, [apex(), closed_book()], 5)
    assert list(table["account_name"]) == ["Closed-book"]


def test_a_row_with_no_stored_log_is_skipped_rather_than_replayed(stocked) -> None:
    """Silently dropping it leaves a report that looks like the whole shortlist."""
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=999)])
    table = replay_shortlist(rows, stocked, [apex()], 5)
    assert list(table["combo_id"]) == [COMBO_ID]


def test_every_configuration_meets_every_rule_set(stocked) -> None:
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=COMBO_ID)])
    accounts = [apex(), propaccount.preset("TopStep 150K")]
    table = replay_shortlist(rows, stocked, accounts, 5)
    assert len(table) == len(rows) * len(accounts)


# -- the excursion order, which is a parameter because it decides the answer ------------------


def test_the_excursion_order_replaces_that_field_and_nothing_else() -> None:
    swapped = rules_with(apex(), propaccount.ExcursionOrder.TROUGH_FIRST)
    assert swapped.rules.excursion_order is propaccount.ExcursionOrder.TROUGH_FIRST
    assert swapped.fees == apex().fees
    assert swapped.name == apex().name
    assert swapped.rules.trailing_threshold == apex().rules.trailing_threshold


def test_a_preset_already_in_that_order_is_handed_back_unchanged() -> None:
    """``PEAK_FIRST`` is every preset's default, so the override is a no-op there and must
    not quietly become a different object a later identity check would miss."""
    assert rules_with(apex(), propaccount.ExcursionOrder.PEAK_FIRST) is propaccount.APEX_50K


# -- the verdict across a shortlist ----------------------------------------------------------


def test_the_verdict_reports_a_share_for_a_question_that_is_yes_or_no() -> None:
    """A median of a boolean says nothing; "did it ever pass" is a share of configurations."""
    table = pd.DataFrame(
        {
            "account_name": ["Apex 50K"] * 4,
            "attempts": [10, 20, 30, 40],
            "passes": [0, 1, 2, 3],
            "withdrawn": [0.0, 100.0, 200.0, 300.0],
            "fees_paid": [50.0] * 4,
            "net": [-50.0, 50.0, 150.0, 250.0],
            "ever_passed": [False, True, True, True],
            "profitable": [False, True, True, True],
            "capped": [False, False, False, True],
        },
    )
    row = verdict(table).iloc[0]
    assert row["configurations"] == 4
    assert row["attempts_med"] == pytest.approx(25.0)
    assert row["ever_passed_%"] == pytest.approx(75.0)
    assert row["profitable_%"] == pytest.approx(75.0)
    assert row["capped"] == 1


def test_an_empty_table_has_no_verdict_rather_than_a_row_of_nothing() -> None:
    assert verdict(pd.DataFrame()).empty


# -- the report ------------------------------------------------------------------------------


def run_main(monkeypatch, rows: pd.DataFrame, db, *extra: str) -> int:
    monkeypatch.setattr(campaign_propaccount, "held_out", lambda *_, **__: rows)
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: db)
    argv = ["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 50K"]

    return main([*argv, *extra])


def test_a_shortlist_with_stored_logs_reports_and_succeeds(monkeypatch, stocked) -> None:
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), stocked) == 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_printing_an_empty_table(
    monkeypatch,
    tmp_path,
) -> None:
    """An empty report is indistinguishable from a cell with nothing to say."""
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), tmp_path / "OpeningRange.duckdb") == 1


def test_the_shortlist_is_the_held_out_pair_and_never_the_window_that_chose_it(
    monkeypatch,
    stocked,
) -> None:
    """There is no ``--window`` here on purpose: a sequence of accounts read from the window
    that picked the configurations is the trap §M28.12 records."""
    called: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        campaign_propaccount,
        "held_out",
        lambda *args: called.append(args) or pd.DataFrame([stored_row()]),
    )
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: stocked)
    argv = ["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 50K"]
    assert main([*argv, "--stratum", "phase=MIDDAY", "--resolution", "5"]) == 0
    assert called == [("OpeningRange", "MNQ", "profit_factor", 20, "phase=MIDDAY", 5, None)]


def test_the_excursion_order_flag_reaches_the_rules(monkeypatch, stocked) -> None:
    """A flag that parses without changing the rule set reads exactly like one that works,
    and on NQ this one decides the answer -- ``docs/roadmap.md`` §M28.13."""
    orders: list[propaccount.ExcursionOrder] = []
    replay = campaign_propaccount.replay_row

    def spy(row, log, account, max_accounts):
        orders.append(account.rules.excursion_order)

        return replay(row, log, account, max_accounts)

    monkeypatch.setattr(campaign_propaccount, "replay_row", spy)
    rows = pd.DataFrame([stored_row()])
    assert run_main(monkeypatch, rows, stocked, "--excursion-order", "trough-first") == 0
    assert orders == [propaccount.ExcursionOrder.TROUGH_FIRST]

    orders.clear()
    assert run_main(monkeypatch, rows, stocked) == 0
    assert orders == [propaccount.ExcursionOrder.PEAK_FIRST], "the default every preset carries"


def test_an_unknown_preset_is_refused_by_name(monkeypatch, stocked) -> None:
    monkeypatch.setattr(campaign_propaccount, "held_out", lambda *_, **__: pd.DataFrame([stored_row()]))
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: stocked)
    with pytest.raises(propaccount.PropAccountError, match="unknown preset"):
        main(["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 40K"])
