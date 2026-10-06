"""Reading a campaign shortlist through a prop firm's account rules.

Three things carry it: the **attempt cap does not bind by default** -- ``docs/roadmap.md``
§M28.13 -- a row the rules **refuse** is named rather than dropped, and the **position size**
reaches the report.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, propaccount, results, splice, stats
from tests.rows import number
from tools import campaign_propaccount
from tools.campaign_propaccount import (
    ALL,
    CONTRACTS,
    DEFAULT_PRESETS,
    EVERY_PRESET,
    QUANTITY,
    REPORTED,
    Window,
    at_quantity,
    best_presets,
    cash_flows,
    chosen,
    contracts_per_trade,
    first_trading_day,
    held_out_days,
    in_order,
    labelled,
    last_whole_months,
    longest_run,
    main,
    monthly_net,
    out_of_pocket,
    replay_row,
    replay_rungs,
    replay_shortlist,
    rules_with,
    running_totals,
    spent_before_first_payout,
    uncapped,
    verdict,
    with_own_profit_factor,
)
from tools.campaign_report import stored_logs

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SWEEP_ID = 58
COMBO_ID = 1473
LEGS = 4
"""Legs per trade, which is the campaign's own four contracts one lot at a time."""


def stored_row(**columns: object) -> pd.Series:  # type: ignore[explicit-any]  # a row of mixed dtypes
    """Build one held-out row, carrying the tags a result is filed under."""
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
    """Build a leg-level log, one trade per trading day, from each day's total net P&L.

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
    """Build a log of ``n`` mildly profitable days, which one Apex 50K survives."""
    rng = np.random.default_rng(11)

    return leg_log(list(rng.normal(240.0, 900.0, n)), legs=legs, excursions=excursions)


CYCLE = [700.0] * 8 + [-6_000.0]
"""One account's life: eight days that fund it, then one that breaches the floor.

Eight at 700 clears Apex 50K's 3,000 target and its seven-day minimum, and the best day is
12.5% of the profit, so the 30% consistency rule is met too.
"""


def cycling_log(cycles: int = 4) -> pd.DataFrame:
    """Build a log that funds, withdraws from and then blows one account after another."""
    return leg_log(CYCLE * cycles)


@pytest.fixture
def stocked(tmp_path: Path) -> Path:
    """Provide a database holding one stored log, at the ids the held-out row names."""
    db = tmp_path / "OpeningRange.duckdb"
    results.save_trades(trade_log(), SWEEP_ID, COMBO_ID, db)

    return db


def apex() -> propaccount.PropAccount:
    return propaccount.preset("Apex 50K")


CALENDAR = np.arange("2024-08-01", "2026-01-01", dtype="datetime64[D]")
"""Every calendar day from August 2024 to the end of 2025, standing in for the session calendar."""


@pytest.fixture(autouse=True)
def calendar_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the held-out calendar, which needs the bar archive a test run does not have."""
    monkeypatch.setattr(campaign_propaccount, "held_out_days", lambda *_: CALENDAR)


# -- the cap that must not bind --------------------------------------------------------------


def test_the_default_cap_cannot_bind_on_any_log() -> None:
    """Each attempt consumes at least one trading day and a day holds at least one trade.

    The trade count bounds the attempts -- ``docs/roadmap.md`` §M28.13.
    """
    log = trade_log(n=30)
    assert uncapped(log) == 30
    result = propaccount.replay(log, apex(), max_accounts=uncapped(log))
    assert result.attempts < uncapped(log)


def test_a_log_with_one_trade_still_gets_an_attempt() -> None:
    """``replay`` refuses ``max_accounts`` below 1.

    A floor of one is the tool's and not a coincidence of the arithmetic.
    """
    assert uncapped(trade_log(n=1)) == 1


def test_a_cap_that_binds_is_reported_rather_than_left_to_be_noticed() -> None:
    """A row that hit the attempt cap says so, since a truncated net reads like a small one.

    ``docs/roadmap.md`` §M28.13.
    """
    log = cycling_log()
    capped = replay_row(stored_row(), log, apex(), 2)
    assert capped is not None
    assert capped["capped"]
    assert capped["attempts"] == 2

    loose = replay_row(stored_row(), log, apex(), uncapped(log))
    assert loose is not None
    assert not loose["capped"]
    assert number(loose, "attempts") > 2


def test_stopping_early_understates_what_the_sequence_was_worth() -> None:
    """Why the cap matters at all.

    A blown account costs its fees and not its trading losses, so the attempts after the cap are
    where the withdrawals are.
    """
    log = cycling_log()
    capped = replay_row(stored_row(), log, apex(), 1)
    loose = replay_row(stored_row(), log, apex(), uncapped(log))
    assert capped is not None
    assert loose is not None
    assert number(loose, "withdrawn") > number(capped, "withdrawn")
    assert number(loose, "passes") > number(capped, "passes")


# -- what a row says -------------------------------------------------------------------------


def test_a_replay_row_carries_the_tags_of_the_configuration_it_came_from() -> None:
    assert labelled(stored_row())["stratum"] == "phase=MIDDAY"
    assert labelled(stored_row())["combo_id"] == COMBO_ID
    assert "profit_factor" not in labelled(stored_row()), "a statistic is not a tag"


def test_the_position_size_the_account_faced_reaches_the_row() -> None:
    """The binding constraint §M28.13 measured is contracts, not the entry rule.

    The trailing threshold over the dollar value of a point is the whole account's room to move.
    """
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
    """``net`` rewards variance and can rank a losing configuration above a winning one.

    The row it must be read beside is on the same line -- ``docs/roadmap.md`` §M28.13.
    """
    row = replay_row(stored_row(), trade_log(), apex(), 5)
    assert row is not None
    assert row["held_pf"] == pytest.approx(1.236)


# -- refusals and absences -------------------------------------------------------------------


def test_a_rule_set_that_refuses_the_log_is_named_rather_than_reported() -> None:
    """Apex trails intraday, so it reads open equity.

    A log with no excursions cannot answer it and reading "unknown" as "none" would report a
    pass the account never had.
    """
    assert replay_row(stored_row(), trade_log(excursions=False), apex(), 5) is None


def closed_book() -> propaccount.PropAccount:
    """Build a rule set measured on closed balances alone, which no shipped preset is.

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


def test_a_refusal_costs_only_its_own_rule_set(tmp_path: Path) -> None:
    """A rule set reading closed balances can answer a log Apex cannot.

    A table that dropped both would read as a firm nobody offered.
    """
    db = tmp_path / "OpeningRange.duckdb"
    results.save_trades(trade_log(excursions=False), SWEEP_ID, COMBO_ID, db)
    rows = pd.DataFrame([stored_row()])
    table = replay_shortlist(rows, stored_logs(rows, db), [apex(), closed_book()], 5)
    assert list(table["account_name"]) == ["Closed-book"]


def test_a_row_with_no_stored_log_is_skipped_rather_than_replayed(stocked: Path) -> None:
    """Silently dropping it leaves a report that looks like the whole shortlist."""
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=999)])
    table = replay_shortlist(rows, stored_logs(rows, stocked), [apex()], 5)
    assert list(table["combo_id"]) == [COMBO_ID]


def test_every_configuration_meets_every_rule_set(stocked: Path) -> None:
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=COMBO_ID)])
    accounts = [apex(), propaccount.preset("TopStep 150K")]
    table = replay_shortlist(rows, stored_logs(rows, stocked), accounts, 5)
    assert len(table) == len(rows) * len(accounts)


def test_a_re_run_log_is_replayed_where_no_stored_one_exists() -> None:
    """``--rerun`` exists for a campaign the archive has moved under.

    Its rows can have no stored log at all -- ``tools/campaign_swept.py``.
    """
    rows = pd.DataFrame([stored_row()])
    logs = {(SWEEP_ID, COMBO_ID): trade_log()}
    table = replay_shortlist(rows, logs, [apex()], 5)
    assert list(table["combo_id"]) == [COMBO_ID]


# -- the excursion order, which is a parameter because it decides the answer ------------------


def test_the_excursion_order_replaces_that_field_and_nothing_else() -> None:
    swapped = rules_with(apex(), propaccount.ExcursionOrder.TROUGH_FIRST)
    assert swapped.rules.excursion_order is propaccount.ExcursionOrder.TROUGH_FIRST
    assert swapped.fees == apex().fees
    assert swapped.name == apex().name
    assert swapped.rules.trailing_threshold == apex().rules.trailing_threshold


def test_a_preset_already_in_that_order_is_handed_back_unchanged() -> None:
    """``PEAK_FIRST`` is every preset's default.

    The override is a no-op there and must not quietly become a different object a later
    identity check would miss.
    """
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


def run_main(monkeypatch: pytest.MonkeyPatch, rows: pd.DataFrame, db: Path, *extra: str) -> int:
    monkeypatch.setattr(campaign_propaccount, "held_out", lambda *_, **__: rows)
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: db)
    argv = ["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 50K"]

    return main([*argv, *extra])


def test_a_shortlist_with_stored_logs_reports_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, stocked: Path
) -> None:
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), stocked) == 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_printing_an_empty_table(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty report is indistinguishable from a cell with nothing to say."""
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), tmp_path / "OpeningRange.duckdb") == 1


def test_rerun_builds_the_logs_rather_than_reading_a_stored_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The flag a campaign the archive has moved under needs.

    No log can be stored for it at all, so the shortlist is re-run and the disagreement reported
    -- ``tools/campaign_swept.py``.
    """
    monkeypatch.setattr(
        campaign_propaccount,
        "logs_for",
        lambda _name, _rows, root: (
            {(SWEEP_ID, COMBO_ID): trade_log()},
            pd.DataFrame([{"root": root, "rows": 1}]),
        ),
    )
    monkeypatch.setattr(campaign_propaccount, "stored_logs", lambda *_: pytest.fail("read a stored log"))
    empty = tmp_path / "OpeningRange.duckdb"

    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), empty, "--rerun") == 0


def test_the_shortlist_is_the_held_out_pair_and_never_the_window_that_chose_it(
    monkeypatch: pytest.MonkeyPatch,
    stocked: Path,
) -> None:
    """There is no ``--window`` here on purpose.

    A sequence of accounts read from the window that picked the configurations is the trap
    §M28.12 records.
    """
    called: list[tuple[object, ...]] = []

    def fake_held_out(*args: object) -> pd.DataFrame:
        called.append(args)

        return pd.DataFrame([stored_row()])

    monkeypatch.setattr(campaign_propaccount, "held_out", fake_held_out)
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: stocked)
    argv = ["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 50K"]
    assert main([*argv, "--stratum", "phase=MIDDAY", "--resolution", "5"]) == 0
    assert called == [("OpeningRange", "MNQ", "profit_factor", 20, "phase=MIDDAY", 5, None)]


def test_the_excursion_order_flag_reaches_the_rules(monkeypatch: pytest.MonkeyPatch, stocked: Path) -> None:
    """A flag that parses without changing the rule set reads exactly like one that works.

    On NQ this one decides the answer -- ``docs/roadmap.md`` §M28.13.
    """
    orders: list[propaccount.ExcursionOrder] = []
    replay = campaign_propaccount.replay_row

    def spy(  # type: ignore[explicit-any]  # a row of mixed dtypes
        row: pd.Series,
        log: pd.DataFrame,
        account: propaccount.Account,
        max_accounts: int,
        window: Window | None = None,
    ) -> dict[str, object] | None:
        assert isinstance(account, propaccount.PropAccount)
        orders.append(account.rules.excursion_order)

        return replay(row, log, account, max_accounts, window)

    monkeypatch.setattr(campaign_propaccount, "replay_row", spy)
    rows = pd.DataFrame([stored_row()])
    assert run_main(monkeypatch, rows, stocked, "--excursion-order", "trough-first") == 0
    assert orders == [propaccount.ExcursionOrder.TROUGH_FIRST]

    orders.clear()
    assert run_main(monkeypatch, rows, stocked) == 0
    assert orders == [propaccount.ExcursionOrder.PEAK_FIRST], "the default every preset carries"


def test_an_unknown_preset_is_refused_by_name(monkeypatch: pytest.MonkeyPatch, stocked: Path) -> None:
    monkeypatch.setattr(campaign_propaccount, "held_out", lambda *_, **__: pd.DataFrame([stored_row()]))
    monkeypatch.setattr(campaign_propaccount, "db_path", lambda _: stocked)
    with pytest.raises(propaccount.PropAccountError, match="unknown preset"):
        main(["campaign_propaccount.py", "--strategy", "OpeningRange", "--preset", "Apex 40K"])


# -- the quantity rungs, because position size is what decides an account -------------------


def test_a_rung_restates_the_size_and_names_a_row_whose_rules_refuse_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """InsideBarTrailing's 0.6 split rounds to (2, 0) at two contracts, which has no runner."""
    rows = pd.DataFrame([stored_row(order_quantity=6, partial_take_profit_percentage=0.6)])
    at_three = at_quantity(rows, archetypes.INSIDEBARTRAILING, 3)
    assert list(at_three["order_quantity"]) == [3]
    assert at_quantity(rows, archetypes.INSIDEBARTRAILING, 2).empty
    assert "cannot take 2 contracts" in caplog.text


def test_a_rung_leaves_the_stored_rows_untouched() -> None:
    rows = pd.DataFrame([stored_row(order_quantity=4)])
    at_quantity(rows, archetypes.OPENINGRANGE, 2)
    assert list(rows["order_quantity"]) == [4]


def test_a_rung_reads_its_profit_factor_off_its_own_log() -> None:
    """The stored figure is the swept size's, which is not this rung's on InsideBarTrailing."""
    rows = pd.DataFrame([stored_row(profit_factor=9.9)])
    log = trade_log()
    measured = with_own_profit_factor(rows, {(SWEEP_ID, COMBO_ID): log})
    assert measured["profit_factor"].iloc[0] == pytest.approx(stats.summarise(log).profit_factor)
    assert np.isnan(with_own_profit_factor(rows, {})["profit_factor"].iloc[0])


def fake_rerun(
    calls: list[int],
) -> Callable[[str, pd.DataFrame, str], tuple[dict[tuple[int, int], pd.DataFrame], pd.DataFrame]]:
    """Build a ``logs_for`` that records the size it was asked for and scales one log by it."""

    def logs_for(
        _name: str, rows: pd.DataFrame, root: str
    ) -> tuple[dict[tuple[int, int], pd.DataFrame], pd.DataFrame]:
        quantity = int(rows["order_quantity"].iloc[0])
        calls.append(quantity)
        log = trade_log()
        log[["gross_pnl", "commission", "net_pnl"]] *= quantity / LEGS

        return {(SWEEP_ID, COMBO_ID): log}, pd.DataFrame([{"root": root, "resolution": 5, "rows": 1}])

    return logs_for


def test_every_rung_is_re_run_and_tagged_with_its_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(campaign_propaccount, "logs_for", fake_rerun(calls))
    rows = pd.DataFrame([stored_row(order_quantity=6)])
    table = replay_rungs("InsideBarTrailing", rows, "MNQ", [2, 3, 8], [apex()], 5)
    assert calls == [3, 8], "two contracts is refused before anything is re-run"
    assert list(table[QUANTITY]) == [3, 8]
    by_size = verdict(table).set_index(QUANTITY)
    assert list(by_size.index) == [3, 8]
    assert set(by_size["account_name"]) == {"Apex 50K"}


def test_no_rung_that_any_row_can_take_is_an_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_propaccount, "logs_for", lambda *_: pytest.fail("re-ran a refused size"))
    rows = pd.DataFrame([stored_row()])
    assert replay_rungs("InsideBarTrailing", rows, "MNQ", [1], [apex()], 5).empty


def test_quantities_re_run_rather_than_reading_the_stored_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(campaign_propaccount, "logs_for", fake_rerun(calls))
    monkeypatch.setattr(campaign_propaccount, "stored_logs", lambda *_: pytest.fail("read a stored log"))
    rows = pd.DataFrame([stored_row(order_quantity=4)])
    assert run_main(monkeypatch, rows, tmp_path / "OpeningRange.duckdb", "--quantities", "4", "8") == 0
    assert calls == [4, 8]


# -- every preset, and TakeProfitTrader's linked pairs ------------------------------------------


def test_all_means_apex_topstep_and_the_three_linked_pairs() -> None:
    assert [account.name for account in chosen([ALL])] == [
        *DEFAULT_PRESETS,
        "TakeProfitTrader 25K Test+PRO",
        "TakeProfitTrader 50K Test+PRO",
        "TakeProfitTrader 150K Test+PRO",
    ]


def test_the_default_is_still_the_four_presets_the_gates_read() -> None:
    """``campaign_gates.py``'s prop read imports it, so widening it would widen that read too."""
    assert DEFAULT_PRESETS == ("Apex 50K", "Apex 150K", "TopStep 50K", "TopStep 150K")


def test_a_separate_takeprofittrader_preset_can_still_be_named() -> None:
    picked = chosen(["TakeProfitTrader 50K PRO", "all"])

    assert picked[0] is propaccount.TPT_50K_PRO
    assert len(picked) == 1 + len(EVERY_PRESET)


def test_a_preset_named_beside_all_is_replayed_once() -> None:
    assert len(chosen(["all", "Apex 50K", "apex 50k"])) == len(EVERY_PRESET)


def test_the_excursion_order_reaches_both_accounts_of_a_linked_pair() -> None:
    swapped = in_order(propaccount.TPT_50K, propaccount.ExcursionOrder.TROUGH_FIRST)

    assert isinstance(swapped, propaccount.LinkedAccount)
    assert swapped.evaluation.rules.excursion_order is propaccount.ExcursionOrder.TROUGH_FIRST
    assert swapped.funded.rules.excursion_order is propaccount.ExcursionOrder.TROUGH_FIRST
    assert in_order(propaccount.TPT_50K, propaccount.ExcursionOrder.PEAK_FIRST) is propaccount.TPT_50K
    assert in_order(apex(), propaccount.ExcursionOrder.PEAK_FIRST) is propaccount.APEX_50K


# -- the months the monthly figures read ------------------------------------------------------

HOLDOUT = np.arange("2024-05-13", "2026-09-19", dtype="datetime64[D]")
"""The span of the holdout on the archive as it stands, 13 May 2024 to 18 September 2026."""


def test_the_whole_months_leave_out_the_two_the_window_cuts_into() -> None:
    months = last_whole_months(HOLDOUT, 27)

    assert (str(months[0]), str(months[-1])) == ("2024-06", "2026-08")
    assert [str(month) for month in last_whole_months(HOLDOUT, 2)] == ["2026-07", "2026-08"]


def test_an_end_month_counts_when_the_window_misses_none_of_its_weekdays() -> None:
    """June 2024 opened on a Saturday and August closed on one, so all three months are whole."""
    days = np.arange("2024-06-03", "2024-08-31", dtype="datetime64[D]")

    assert [str(month) for month in last_whole_months(days, 3)] == ["2024-06", "2024-07", "2024-08"]


@pytest.mark.parametrize("count", [0, 28])
def test_more_months_than_the_window_holds_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="27 whole months"):
        last_whole_months(HOLDOUT, count)


def test_a_month_starts_on_the_first_day_the_window_holds_in_it() -> None:
    """June 2024 opened on a Saturday, so its first trading day is the 3rd."""
    days = np.array(["2024-05-31", "2024-06-03", "2024-06-04"], dtype="datetime64[D]")

    assert first_trading_day(days, pd.Period("2024-06", freq="M")) == dt.date(2024, 6, 3)


def test_the_held_out_days_are_the_window_the_rows_were_swept_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The archive has grown since; the calendar must end where the stored rows' bars ended.

    One bar a day at 15:00 UTC, which is in session on a weekday and out of it at the weekend.
    """
    index = pd.date_range("2024-01-02 15:00", periods=100, freq="D", tz="UTC")
    archive = pd.DataFrame({"close": 1.0}, index=index)
    stored = pd.DataFrame({"last_bar": [index[49].tz_localize(None)]})
    monkeypatch.setattr(splice, "load_continuous", lambda _root: archive)
    monkeypatch.setattr(campaign_propaccount, "stored_rows", lambda *_: stored)

    # Swept on the first 50 bars, so the holdout is the last 40% of those: bars 30 to 49.
    expected = [stamp.date() for stamp in index[30:50] if stamp.weekday() < 5]
    days = held_out_days("OpeningRange", "MNQ")

    assert [pd.Timestamp(day).date() for day in days] == expected
    assert pd.Timestamp(days[-1]).date() < index[-1].date()


# -- when the money came back ----------------------------------------------------------------


def quick_payer() -> propaccount.PropAccount:
    """Build an account that never breaches, passes at 1,000 and withdraws all of it, for 300."""
    return propaccount.PropAccount(
        name="Quick",
        rules=propaccount.AccountRules(
            starting_balance=50_000.0,
            profit_target=1_000.0,
            trail_breach=propaccount.EquityBasis.REALISED,
            daily_loss_basis=propaccount.EquityBasis.REALISED,
        ),
        fees=propaccount.AccountFees(evaluation_fee=300.0),
    )


def autumn() -> Window:
    """Return September to November 2024, every calendar day a trading day."""
    months = tuple(pd.period_range("2024-09", "2024-11", freq="M"))

    return Window(CALENDAR, months)


EARNER = [600.0] * 60
"""Sixty days of 600 from 3 September, the last of them 1 November."""


def test_the_day_s_cash_nets_fees_against_payouts_and_adds_up_to_the_net() -> None:
    result = propaccount.replay(cycling_log(), apex(), max_accounts=10)
    cash = cash_flows(result)

    assert [day for day, _ in cash] == sorted({day for day, _ in cash})
    assert sum(moved for _, moved in cash) == pytest.approx(result.net)


def test_an_exact_tie_is_not_ahead() -> None:
    """Fees and payouts that cancel leave float dust, which must not read as breaking even."""
    running = running_totals(
        [(dt.date(2024, 1, 2), -130.0), (dt.date(2024, 1, 3), 100.1), (dt.date(2024, 1, 4), 29.9)]
    )

    assert running[-1][1] == 0.0
    assert out_of_pocket(running) == pytest.approx(130.0)


def test_out_of_pocket_stops_at_the_day_the_payouts_first_pass_the_fees() -> None:
    days = [dt.date(2024, 1, day) for day in (2, 3, 4, 5)]
    running = running_totals(list(zip(days, [-100.0, -50.0, 200.0, -500.0], strict=True)))

    assert out_of_pocket(running) == pytest.approx(150.0)


def test_each_month_is_its_own_net_and_a_quiet_month_is_zero() -> None:
    cash = [(dt.date(2024, 9, 3), -300.0), (dt.date(2024, 9, 30), 500.0), (dt.date(2024, 11, 1), -100.0)]

    assert monthly_net(cash, autumn().months) == [200.0, 0.0, -100.0]
    assert monthly_net([], autumn().months) == [0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    ("flags", "longest"),
    [([], 0), ([False, False], 0), ([True, True, False, True], 2), ([False, True, True, True], 3)],
)
def test_the_longest_run_is_the_longest_unbroken_one(flags: list[bool], longest: int) -> None:
    assert longest_run(flags) == longest


def test_a_row_given_a_window_says_when_the_money_came_back() -> None:
    """Passed on its second day, which paid 1,200 against the 300 it cost on its first."""
    row = replay_row(stored_row(), leg_log(EARNER), quick_payer(), 60, autumn())

    assert row is not None
    assert row["days_to_profit"] == 2.0
    assert row["broke_even"] is True
    assert row["out_of_pocket"] == pytest.approx(300.0)
    assert row["evaluations_before_payout"] == 1.0
    assert row["fees_before_payout"] == pytest.approx(300.0)
    assert row["payouts"] == 59
    assert row["payout_median"] == pytest.approx(600.0)
    assert (row["months"], row["profitable_months"], row["losing_streak"]) == (3, 3, 0)
    assert (row["best_month"], row["worst_month"]) == pytest.approx((18_600.0, 600.0))


def test_a_fresh_start_counts_only_if_it_ends_ahead() -> None:
    """November's start has one day of 600 left, short of the target, so it ends 300 down."""
    row = replay_row(stored_row(), leg_log(EARNER), quick_payer(), 60, autumn())

    assert row is not None
    assert row["fresh_ahead"] == 2


def test_a_row_that_never_breaks_even_says_never_and_spends_nothing_before_a_payout() -> None:
    row = replay_row(stored_row(), leg_log([-100.0] * 10), quick_payer(), 10, autumn())

    assert row is not None
    assert row["days_to_profit"] == math.inf
    assert row["broke_even"] is False
    assert math.isnan(number(row, "evaluations_before_payout"))
    assert math.isnan(number(row, "fees_before_payout"))
    assert math.isnan(number(row, "payout_median"))
    assert row["out_of_pocket"] == pytest.approx(300.0)
    assert (row["profitable_months"], row["losing_streak"], row["worst_month"]) == (0, 1, -300.0)


def test_a_linked_pair_counts_one_evaluation_and_one_hand_over_fee_before_its_first_payout() -> None:
    """The Test passes on its third day, and the PRO's first day pays 400 of 500 withdrawn.

    Before then: a month of the Test at 102 and the 130 that opened the PRO, once.
    """
    row = replay_row(stored_row(), leg_log([1_600.0] * 3 + [2_500.0]), propaccount.TPT_50K, 4, autumn())

    assert row is not None
    assert row["evaluations_before_payout"] == 1.0
    assert row["fees_before_payout"] == pytest.approx(232.0)
    assert row["days_to_profit"] == 4.0
    assert row["payout_median"] == pytest.approx(400.0)


def test_a_row_without_a_window_is_the_one_the_gates_read() -> None:
    """``campaign_gates.py`` passes none, so its prop read neither changes nor slows down."""
    row = replay_row(stored_row(), trade_log(), apex(), 5)

    assert row is not None
    assert "days_to_profit" not in row
    assert "fresh_ahead" not in row


def test_the_evaluations_before_a_payout_are_the_pair_s_evaluations_only() -> None:
    result = propaccount.replay(leg_log([1_600.0] * 3 + [2_500.0]), propaccount.TPT_50K)

    assert [run.account_name for run in result.runs] == [
        "TakeProfitTrader 50K Test",
        "TakeProfitTrader 50K PRO",
    ]
    assert spent_before_first_payout(result, propaccount.TPT_50K) == pytest.approx((1.0, 232.0))


# -- the summary across the shortlist and the best preset per configuration ------------------


def timed_table() -> pd.DataFrame:
    """Build replay rows for two configurations, one that breaks even somewhere and one that never does."""
    return pd.DataFrame(
        {
            "combo_id": [1, 1, 1, 2, 2],
            "account_name": ["A", "B", "C", "A", "B"],
            "held_pf": [1.2, 1.2, 1.2, 0.9, 0.9],
            "attempts": [1, 2, 3, 4, 5],
            "passes": [1, 1, 1, 0, 0],
            "withdrawn": [10.0, 20.0, 30.0, 0.0, 0.0],
            "fees_paid": [5.0] * 5,
            "net": [5.0, 15.0, 25.0, -5.0, -5.0],
            "ever_passed": [True, True, True, False, False],
            "profitable": [True, True, True, False, False],
            "capped": [False] * 5,
            "days_to_profit": [30.0, 12.0, 12.0, math.inf, math.inf],
            "broke_even": [True, True, True, False, False],
            "profitable_months": [5, 3, 7, 0, 1],
            "fresh_ahead": [1, 2, 3, 0, 0],
        },
    )


def test_the_best_preset_is_the_fastest_to_profit_with_more_good_months_breaking_ties() -> None:
    best = best_presets(timed_table()).set_index("combo_id")

    assert best.loc[1, "best_preset"] == "C"
    assert best.loc[1, "days_to_profit"] == 12.0


def test_a_configuration_no_preset_pays_back_has_no_best_preset_and_no_figures() -> None:
    """Figures beside ``none`` would belong to whichever preset happened to sort first."""
    row = best_presets(timed_table()).set_index("combo_id").loc[2]

    assert row["best_preset"] == "none"
    assert row[["profitable_months", "fresh_ahead"]].isna().all()


def test_there_is_no_best_preset_without_the_timing_figures() -> None:
    assert best_presets(timed_table().drop(columns=["days_to_profit"])).empty
    assert best_presets(pd.DataFrame()).empty


def test_the_verdict_adds_the_share_that_broke_even_and_the_timing_medians() -> None:
    row = verdict(timed_table()).set_index("account_name").loc["A"]

    assert row["broke_even_%"] == pytest.approx(50.0)
    assert row["days_to_profit_med"] == math.inf, "half never broke even, so the median is never"
    assert row["profitable_months_med"] == pytest.approx(2.5)
    assert row["fresh_ahead_med"] == pytest.approx(0.5)


def test_every_preset_runs_from_the_command_line_and_writes_three_tables(
    monkeypatch: pytest.MonkeyPatch,
    stocked: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "prop"
    rows = pd.DataFrame([stored_row()])
    assert run_main(monkeypatch, rows, stocked, "--preset", "all", "--out", str(out)) == 0

    replays = pd.read_csv(out / "replays.csv")
    assert list(replays["account_name"]) == list(EVERY_PRESET)
    assert set(replays.columns) >= {"days_to_profit", "profitable_months", "fresh_ahead", "held_pf"}
    assert list(pd.read_csv(out / "verdict.csv")["account_name"]) == list(EVERY_PRESET)
    assert len(pd.read_csv(out / "best.csv")) == 1


def test_more_months_than_the_holdout_holds_is_refused_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    stocked: Path,
) -> None:
    with pytest.raises(SystemExit):
        run_main(monkeypatch, pd.DataFrame([stored_row()]), stocked, "--last-months", "99")


def test_an_empty_shortlist_fails_without_reading_the_calendar(
    monkeypatch: pytest.MonkeyPatch,
    stocked: Path,
) -> None:
    monkeypatch.setattr(campaign_propaccount, "held_out_days", lambda *_: pytest.fail("read the calendar"))

    assert run_main(monkeypatch, pd.DataFrame(), stocked) == 1
