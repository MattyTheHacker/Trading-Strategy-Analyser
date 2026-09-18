"""Ranking a campaign's configurations by what a prop account is scored on.

Three things carry this module. Each **objective has to be measured in trading days and fees the
account actually saw**, from the right phase of the right preset, because a TakeProfitTrader
Test account's life after its pass is not a funded life. Each **shortlist is chosen on the
selection window and read on the holdout**, beside the profit-factor shortlist it is measured
against. And the **pool is re-run on the archive as it stands**, so a stored row that no longer
reproduces is re-measured rather than refused -- ``docs/findings/m40-prop-objectives.md``.
"""

from __future__ import annotations

import argparse
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from nqbt import disambiguate, propaccount, resample, results, sessions, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.types import InsideBarParams
from tools import campaign_propobjectives
from tools.campaign_propobjectives import (
    CONTROL,
    OBJECTIVES,
    calendar,
    days_to_payout,
    funded_lives,
    main,
    measure,
    measure_window,
    pool,
    ranking,
    reads,
    run_cell,
    sessions_between,
    shortlists,
    verdict,
)
from tools.campaign_shortlist import source

ROOT = "MNQ"
START = dt.date(2024, 1, 2)


def days_from(start: dt.date, n: int) -> np.ndarray:
    """A calendar of ``n`` consecutive trading days, so a count of days is a count of dates."""
    return np.datetime64(start, "D") + np.arange(n).astype("timedelta64[D]")


def leg_log(daily: list[float]) -> pd.DataFrame:
    """One single-leg MNQ trade per trading day, from each day's net P&L."""
    n = len(daily)
    exits = pd.Timestamp("2024-01-02 15:00", tz="UTC") + pd.to_timedelta(np.arange(n), unit="D")

    return pd.DataFrame(
        {
            "source": "sim",
            "instrument": "MNQ",
            "trade_id": np.arange(1, n + 1),
            "leg": 1,
            "quantity": 1,
            "direction": 1.0,
            "gross_pnl": np.asarray(daily) + 1.5,
            "commission": 1.5,
            "net_pnl": daily,
            "bars_held": 5,
            "mae_points": 1.0,
            "mfe_points": 1.0,
            "r_multiple": 0.5,
            "ambiguous_bar": False,
            "exit_reason": "target",
            "entry_time": exits - pd.Timedelta(minutes=5),
            "exit_time": exits,
        },
    )


def evaluation(**overrides: object) -> propaccount.PropAccount:
    """A plain evaluation on closed balances, so each test moves only the field it names."""
    fields = {
        "starting_balance": 50_000.0,
        "profit_target": 3_000.0,
        "trailing_threshold": 2_000.0,
        "trail_basis": propaccount.TrailBasis.END_OF_DAY,
        "trail_breach": propaccount.EquityBasis.REALISED,
        "daily_loss_basis": propaccount.EquityBasis.REALISED,
        "withdrawal_threshold": 10_000.0,
    }

    return propaccount.PropAccount(name="Evaluation", rules=propaccount.AccountRules(**(fields | overrides)))


def funded(**overrides: object) -> propaccount.PropAccount:
    """A funded account from its first day, the shape of a TakeProfitTrader PRO preset."""
    return propaccount.PropAccount(name="Funded", rules=evaluation(profit_target=0.0, **overrides).rules)


def replayed(daily: list[float], account: propaccount.PropAccount) -> propaccount.PropReplay:
    return propaccount.replay(leg_log(daily), account, max_accounts=len(daily))


# -- counting trading days ---------------------------------------------------------------------


def test_the_days_between_two_dates_count_both_ends_and_only_trading_days() -> None:
    days = np.array(["2024-01-02", "2024-01-03", "2024-01-05"], dtype="datetime64[D]")
    assert sessions_between(days, dt.date(2024, 1, 2), dt.date(2024, 1, 5)) == 3
    assert sessions_between(days, dt.date(2024, 1, 3), dt.date(2024, 1, 3)) == 1
    assert sessions_between(days, dt.date(2024, 1, 4), dt.date(2024, 1, 4)) == 0, "not a trading day"
    assert sessions_between(days, dt.date(2024, 1, 5), dt.date(2024, 1, 2)) == 0, "never negative"


def test_the_calendar_holds_each_session_day_once_and_no_day_the_break_alone_touched() -> None:
    """A trading day is counted from the bars rather than from the log, so a day the strategy
    did not trade still counts toward how long an account lived."""
    in_session = pd.date_range("2024-01-02 15:00", periods=120, freq="min", tz="UTC")
    in_session = in_session.append(pd.date_range("2024-01-03 15:00", periods=120, freq="min", tz="UTC"))
    in_break = pd.date_range("2024-01-04 22:10", periods=30, freq="min", tz="UTC")
    bars = pd.DataFrame({"close": 1.0}, index=in_session.append(in_break))
    assert not sessions.classify(in_break).in_session.any(), "fixture: 17:10 to 17:40 ET is the break"

    assert list(calendar(bars)) == list(np.array(["2024-01-02", "2024-01-03"], dtype="datetime64[D]"))


# -- which preset answers which objective ------------------------------------------------------


def names(account: propaccount.PropAccount) -> set[str]:
    return {objective.name for objective in OBJECTIVES if reads(account, objective)}


def test_a_firm_with_one_rule_set_for_both_phases_answers_every_objective() -> None:
    assert names(propaccount.APEX_50K) == {"pass_rate", "fees_per_pass", "days_to_payout", "funded_days"}
    assert names(propaccount.TOPSTEP_150K) == names(propaccount.APEX_50K)


def test_a_split_firm_answers_the_evaluation_from_one_preset_and_the_funded_life_from_the_other() -> None:
    """What a Test preset does after it passes is a fiction, and a PRO preset has no evaluation
    -- ``docs/roadmap.md`` § "A firm that changes its rules at the pass ships as two presets"."""
    assert names(propaccount.TPT_50K_TEST) == {"pass_rate", "fees_per_pass", "days_to_payout"}
    assert names(propaccount.TPT_50K_PRO) == {"funded_days"}


# -- funded life -------------------------------------------------------------------------------


def test_an_evaluation_is_funded_from_the_day_after_its_pass_until_its_breach() -> None:
    """Passes on day 0, trades three more days and breaches on day 4: four funded days."""
    result = replayed([3_000.0, 100.0, 100.0, 100.0, -3_000.0], evaluation())
    assert result.runs[0].passed_on == START
    assert result.runs[0].outcome is not propaccount.Outcome.SURVIVED

    assert funded_lives(result, evaluation(), days_from(START, 30)) == [(4, False)]


def test_an_account_still_alive_at_the_end_of_the_window_lives_to_the_end_of_the_window() -> None:
    """Its last trade is not its last day; the window's is, and the life is marked as cut off."""
    result = replayed([3_000.0, 100.0], evaluation())
    assert funded_lives(result, evaluation(), days_from(START, 30)) == [(29, True)]


def test_a_funded_preset_is_funded_from_its_first_day() -> None:
    result = replayed([100.0, 100.0, 100.0, -3_000.0], funded())
    assert funded_lives(result, funded(), days_from(START, 30))[0] == (4, False)


def test_an_attempt_that_never_passed_has_no_funded_life_at_all() -> None:
    result = replayed([100.0, -2_500.0, 100.0], evaluation())
    assert result.passes == 0
    assert funded_lives(result, evaluation(), days_from(START, 30)) == []


# -- time to the first payout ------------------------------------------------------------------


def test_the_first_payout_is_counted_from_the_first_account_even_when_a_later_one_pays() -> None:
    """The first account breaches on day 0 and the second passes and withdraws on day 1: two
    trading days from opening the first account, not one from opening the second."""
    account = evaluation(withdrawal_threshold=1_000.0)
    result = replayed([-2_500.0, 3_000.0], account)
    assert result.attempts == 2
    assert result.runs[1].first_withdrawal_on == dt.date(2024, 1, 3)

    assert days_to_payout(result, days_from(START, 30)) == 2.0


def test_a_sequence_that_never_withdraws_takes_the_value_that_ranks_it_last() -> None:
    assert days_to_payout(replayed([100.0, 100.0], evaluation()), days_from(START, 30)) == float("inf")


# -- one replay's measures ---------------------------------------------------------------------


def test_an_objective_whose_event_never_happened_ranks_last_rather_than_vanishing() -> None:
    measured = measure(replayed([100.0, -2_500.0], evaluation()), evaluation(), days_from(START, 30))
    assert measured["passes"] == 0
    assert measured["fees_per_pass"] == float("inf")
    assert measured["days_to_payout"] == float("inf")
    assert measured["funded_days"] == 0.0
    assert not measured["ever_passed"]


def test_fees_per_pass_is_what_the_whole_sequence_cost_over_what_it_passed() -> None:
    paid = propaccount.PropAccount(
        name="Paid",
        rules=evaluation().rules,
        fees=propaccount.AccountFees(evaluation_fee=100.0, activation_fee=50.0),
    )
    result = replayed([-2_500.0, 3_000.0], paid)
    measured = measure(result, paid, days_from(START, 30))
    assert result.passes == 1
    assert measured["fees_per_pass"] == pytest.approx(250.0), "two entry fees and one activation"


def test_an_objective_the_preset_cannot_answer_is_blank_and_never_a_number() -> None:
    """A PRO preset's "pass" is its first profitable day, so a pass rate read off it would be
    a figure about nothing."""
    measured = measure(replayed([100.0, 100.0], funded()), funded(), days_from(START, 30))
    for name in ("pass_rate", "fees_per_pass", "days_to_payout"):
        assert np.isnan(measured[name])

    assert not np.isnan(measured["funded_days"])


def test_a_rule_set_that_refuses_the_log_costs_only_its_own_row() -> None:
    """Apex reads open equity, so a log with no excursions cannot answer it; the closed-book
    rule set still can, and dropping both would read as a preset nobody offered."""
    log = leg_log([100.0, 100.0]).assign(mae_points=np.nan, mfe_points=np.nan)
    row = pd.Series(
        {
            "root": ROOT,
            "resolution": 5,
            "variant": "bracket",
            "stratum": "unfiltered",
            "window": "selection",
            "sweep_id": 1,
            "combo_id": 7,
        }
    )
    measured = campaign_propobjectives.replay_configuration(
        row,
        {"trades": 2, CONTROL: 1.5, "ambiguous_share": 0.0, "session_close_share": 0.5},
        log,
        [propaccount.APEX_50K, evaluation()],
        days_from(START, 30),
    )
    assert [entry["account_name"] for entry in measured] == ["Evaluation"]
    assert measured[0]["combo_id"] == 7


# -- ranking and shortlists --------------------------------------------------------------------


def test_a_cost_ranks_lowest_first_and_selection_profit_factor_breaks_a_tie() -> None:
    measured = pd.DataFrame(
        {"fees_per_pass": [100.0, 100.0, 50.0, float("inf")], CONTROL: [1.0, 2.0, 0.5, 3.0]},
    )
    ranked = ranking(measured, "fees_per_pass", higher_is_better=False, top=3)
    assert list(ranked.index) == [2, 1, 0]


def selection_frame() -> pd.DataFrame:
    """Four configurations measured through two presets on the selection window."""
    return pd.DataFrame(
        [
            {
                "root": ROOT,
                "resolution": 5,
                "variant": "bracket",
                "stratum": "unfiltered",
                "combo_id": combo,
                "account_name": account,
                CONTROL: [1.1, 1.4, 1.2, 1.3][combo],
                "pass_rate": [0.9, 0.1, 0.5, 0.2][combo],
                "fees_per_pass": [400.0, 100.0, 300.0, 200.0][combo],
                "days_to_payout": [10.0, 40.0, 20.0, 30.0][combo],
                "funded_days": [5.0, 50.0, 25.0, 15.0][combo],
                "ambiguous_share": 0.002,
                "session_close_share": 0.3,
            }
            for account in ("Apex 50K", "TakeProfitTrader 50K PRO")
            for combo in range(4)
        ],
    )


def test_each_preset_is_shortlisted_by_the_control_and_by_every_objective_it_answers() -> None:
    accounts = [propaccount.APEX_50K, propaccount.TPT_50K_PRO, propaccount.TOPSTEP_50K]
    chosen = shortlists(selection_frame(), accounts, top=2)

    by_account = chosen.groupby("account_name")["ranked_by"].unique()
    assert set(by_account["Apex 50K"]) == {
        CONTROL,
        "pass_rate",
        "fees_per_pass",
        "days_to_payout",
        "funded_days",
    }
    assert set(by_account["TakeProfitTrader 50K PRO"]) == {CONTROL, "funded_days"}
    assert "TopStep 50K" not in by_account.index, "a preset with nothing measured has no shortlist"
    assert chosen.groupby(["account_name", "ranked_by"]).size().max() == 2


def test_each_objective_shortlists_the_configurations_it_ranks_best() -> None:
    chosen = shortlists(selection_frame(), [propaccount.APEX_50K], top=1)
    picked = dict(zip(chosen["ranked_by"], chosen["combo_id"], strict=True))
    assert picked == {CONTROL: 1, "pass_rate": 0, "fees_per_pass": 1, "days_to_payout": 0, "funded_days": 1}


def test_no_preset_with_a_measure_means_no_shortlist_rather_than_an_empty_row() -> None:
    assert shortlists(selection_frame(), [propaccount.TOPSTEP_50K], top=2).empty


# -- the verdict -------------------------------------------------------------------------------


def held_frame() -> pd.DataFrame:
    """The same four configurations through the same presets on the held-out window."""
    held = selection_frame()
    held["pass_rate"] = [0.3, 0.3, 0.1, 0.0] * 2
    held[CONTROL] = [1.0, 0.9, 1.1, 1.2] * 2
    held["funded_accounts"] = 2
    held["funded_censored"] = [1, 0, 0, 0] * 2
    held["ever_passed"] = [True, True, True, False] * 2
    held["paid_out"] = [True, False, True, False] * 2
    held["net"] = [100.0, -50.0, 20.0, -10.0] * 2

    return held


def test_the_verdict_puts_each_shortlist_s_selection_and_held_out_medians_side_by_side() -> None:
    chosen = shortlists(selection_frame(), [propaccount.APEX_50K], top=2)
    table = verdict(chosen, held_frame()).set_index("ranked_by")

    by_pass_rate = table.loc["pass_rate"]
    assert by_pass_rate["n"] == 2
    assert by_pass_rate["pass_rate_sel"] == pytest.approx(0.7), "combos 0 and 2 on selection"
    assert by_pass_rate["pass_rate_hold"] == pytest.approx(0.2), "the same two held out"
    assert by_pass_rate["ever_passed_%"] == pytest.approx(100.0)
    assert by_pass_rate["paid_out_%"] == pytest.approx(100.0)
    assert by_pass_rate["censored_share"] == pytest.approx(0.25)
    assert by_pass_rate["pf_hold"] == pytest.approx(1.05)
    assert table.loc[CONTROL, "pass_rate_sel"] == pytest.approx(0.15), "combos 1 and 3"


def test_nothing_chosen_or_nothing_held_has_no_verdict() -> None:
    chosen = shortlists(selection_frame(), [propaccount.APEX_50K], top=2)
    assert verdict(chosen, pd.DataFrame()).empty
    assert verdict(pd.DataFrame(), held_frame()).empty


# -- the pool ----------------------------------------------------------------------------------


def paired_rows() -> pd.DataFrame:
    """Four stored pairs, already in selection-window rank order."""
    return pd.DataFrame(
        {
            "root": ROOT,
            "resolution": 5,
            "variant": ["bracket", "bracket hold=10", "narrow", "bracket"],
            "stratum": "unfiltered",
            "combo_id": [0, 1, 0, 2],
            "ambiguous_share_sel": 0.001,
            "ambiguous_share_hold": 0.001,
            "atr_multiplier_sel": [5.0, 7.0, 5.0, 10.0],
            "atr_multiplier_hold": [5.0, 7.0, 5.0, 10.0],
            "profit_factor_sel": [3.0, 2.5, 2.0, 1.0],
            "profit_factor_hold": [1.0, 1.0, 1.0, 1.0],
        },
    )


def pool_args(size: int) -> argparse.Namespace:
    return argparse.Namespace(pool=size, stratum="unfiltered", resolution=None, variant=None)


def test_the_pool_leaves_out_the_hold_caps_and_takes_a_configuration_once(monkeypatch) -> None:
    """The ``narrow`` row is the ``bracket`` row's configuration under another name; re-run on
    one archive the two are the same trades, and two copies would fill two shortlist places."""
    monkeypatch.setattr(campaign_propobjectives, "ranked_pairs", lambda *_: paired_rows())
    kept = pool("InsideBar", ROOT, pool_args(10))
    assert list(zip(kept["variant"], kept["combo_id"], strict=True)) == [("bracket", 0), ("bracket", 2)]


def test_the_same_parameters_at_two_bar_sizes_are_two_configurations(monkeypatch) -> None:
    """Resolution is not a parameter, and it is the largest lever in the registry."""
    rows = pd.concat([paired_rows(), paired_rows().assign(resolution=15)], ignore_index=True)
    monkeypatch.setattr(campaign_propobjectives, "ranked_pairs", lambda *_: rows)
    kept = pool("InsideBar", ROOT, pool_args(10))
    assert list(zip(kept["resolution"], kept["combo_id"], strict=True)) == [(5, 0), (5, 2), (15, 0), (15, 2)]


def test_the_pool_stops_at_its_size_in_rank_order(monkeypatch) -> None:
    monkeypatch.setattr(campaign_propobjectives, "ranked_pairs", lambda *_: paired_rows())
    assert list(pool("InsideBar", ROOT, pool_args(1))["atr_multiplier_sel"]) == [5.0]


def test_the_pool_ranks_every_stored_pair_rather_than_a_shortlist_of_them(monkeypatch) -> None:
    """Hold arms and duplicates are removed after ranking, so a truncated ranking would leave a
    pool smaller than asked for."""
    asked: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        campaign_propobjectives, "ranked_pairs", lambda *args: asked.append(args) or paired_rows()
    )
    pool("InsideBar", ROOT, pool_args(2))
    assert asked == [("InsideBar", ROOT, CONTROL, None, "unfiltered", None, None)]


def test_a_row_the_fill_assumption_could_have_decided_never_enters_the_pool(monkeypatch) -> None:
    """Ranking a pool on profit factor selects for ``ambiguous_share``, and §M28.7's rejection is
    what that looks like -- profit factors past 200 that are the assumption and not the entry."""
    rows = paired_rows()
    rows.loc[0, "ambiguous_share_sel"] = disambiguate.MIN_AMBIGUOUS_SHARE + 0.001
    monkeypatch.setattr(campaign_propobjectives, "ranked_pairs", lambda *_: rows)

    kept = pool("InsideBar", ROOT, pool_args(10))
    assert list(zip(kept["variant"], kept["combo_id"], strict=True)) == [("narrow", 0), ("bracket", 2)]
    assert (kept["ambiguous_share_sel"] <= disambiguate.MIN_AMBIGUOUS_SHARE).all()
    # With the ``bracket`` row gone, the ``narrow`` row is no longer a duplicate of it.


# -- one cell, end to end ----------------------------------------------------------------------


def test_the_holdout_replays_only_the_shortlisted_configurations_through_their_own_presets(
    monkeypatch,
) -> None:
    """Replaying the whole pool held out would cost as much again and read nothing more."""
    pairs = paired_rows().drop(index=1).reset_index(drop=True)
    pairs["combo_id"] = [0, 1, 2]
    pairs["variant"] = "bracket"
    monkeypatch.setattr(campaign_propobjectives, "pool", lambda *_: pairs)

    calls: list[tuple[pd.DataFrame, dict]] = []

    def fake_measure(*arguments: object) -> pd.DataFrame:
        _, rows, _, _, wanted, _ = arguments
        calls.append((rows, wanted))
        frame = selection_frame()
        frame = frame[(frame["account_name"] == "Apex 50K") & frame["combo_id"].isin(rows["combo_id"])]

        return frame.assign(funded_accounts=1, funded_censored=0, ever_passed=True, paid_out=True, net=1.0)

    monkeypatch.setattr(campaign_propobjectives, "measure_window", fake_measure)
    bars = pd.DataFrame(
        {"close": np.arange(100.0)}, index=pd.date_range("2024-01-02", periods=100, freq="min")
    )
    args = argparse.Namespace(top=1, n_jobs=1)
    _, table = run_cell("InsideBar", ROOT, args, [propaccount.APEX_50K], bars)

    (selection_rows, everything), (held_rows, wanted) = calls
    assert len(selection_rows) == 3
    assert all(accounts == [propaccount.APEX_50K] for accounts in everything.values())
    assert set(held_rows["combo_id"]) == {0, 1}, "combo 2 leads no shortlist, so it is never held out"
    assert all(accounts == [propaccount.APEX_50K] for accounts in wanted.values())
    assert set(table["ranked_by"]) == {CONTROL, "pass_rate", "fees_per_pass", "days_to_payout", "funded_days"}


def test_a_pool_nothing_was_measured_on_is_never_read_held_out(monkeypatch) -> None:
    monkeypatch.setattr(campaign_propobjectives, "pool", lambda *_: paired_rows())
    held: list[object] = []

    def fake_measure(*arguments: object) -> pd.DataFrame:
        held.append(arguments[1])

        return pd.DataFrame()

    monkeypatch.setattr(campaign_propobjectives, "measure_window", fake_measure)
    bars = pd.DataFrame(
        {"close": np.arange(100.0)}, index=pd.date_range("2024-01-02", periods=100, freq="min")
    )
    _, table = run_cell("InsideBar", ROOT, argparse.Namespace(top=1, n_jobs=1), [propaccount.APEX_50K], bars)
    assert table.empty
    assert len(held) == 1, "the selection window only"


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day

    return frame


def stored_selection(db, bars: pd.DataFrame) -> pd.DataFrame:
    """Two InsideBar configurations swept on the selection window and read back as stored rows."""
    frame = resample.resample(source(bars, "selection"), 5)
    grid = sweep.Grid.of(
        InsideBarParams(slow_sma_period=50, bars_required_to_trade=60), atr_multiplier=[5.0, 10.0]
    )
    table, _ = sweep.sweep(frame, grid, get_instrument(ROOT))
    table.insert(0, "variant", "bracket")
    table.insert(1, "stratum", "unfiltered")
    table.insert(2, "window", "selection")
    table["combo_id"] = range(len(table))
    results.save_sweep(
        table,
        root=ROOT,
        instrument=ROOT,
        bars=frame,
        axes=grid.axis_values(),
        strategy="InsideBar",
        resolution=5,
        db_path=db,
    )

    return results.query("SELECT * FROM combos ORDER BY combo_id", db).assign(root=ROOT)


def test_a_window_is_re_run_and_replayed_through_every_preset_each_configuration_asks_for(tmp_path) -> None:
    bars = synthetic_bars()
    rows = stored_selection(tmp_path / "InsideBar.duckdb", bars)
    assert rows["trades"].min() > 0, "fixture produced no trades; the test proves nothing"

    closed = evaluation()
    wanted = {
        campaign_propobjectives.key_of(row): [propaccount.APEX_50K, closed]
        if row["combo_id"] == 0
        else [closed]
        for _, row in rows.iterrows()
    }
    measured = measure_window("InsideBar", rows, ROOT, source(bars, "selection"), wanted, n_jobs=1)

    assert sorted(zip(measured["combo_id"], measured["account_name"], strict=True)) == [
        (0, "Apex 50K"),
        (0, "Evaluation"),
        (1, "Evaluation"),
    ]
    assert set(measured["window"]) == {"selection"}
    assert list(measured.drop_duplicates("combo_id")["trades"]) == list(rows["trades"])


def test_a_stored_row_the_archive_no_longer_reproduces_is_re_measured_rather_than_refused(tmp_path) -> None:
    """The archive moved under every campaign stored before 2026-09-16, so the figures a
    shortlist is read by are the re-run's own and never the stored row's."""
    bars = synthetic_bars()
    rows = stored_selection(tmp_path / "InsideBar.duckdb", bars)
    stale = rows.assign(trades=rows["trades"] + 1, profit_factor=99.0)
    wanted = {campaign_propobjectives.key_of(row): [evaluation()] for _, row in stale.iterrows()}

    measured = measure_window("InsideBar", stale, ROOT, source(bars, "selection"), wanted, n_jobs=1)
    assert list(measured["trades"]) == list(rows["trades"])
    assert list(measured[CONTROL]) == pytest.approx(list(rows["profit_factor"]))


# -- the report --------------------------------------------------------------------------------


def run_main(monkeypatch, table: pd.DataFrame, *extra: str) -> int:
    monkeypatch.setattr(campaign_propobjectives.splice, "load_continuous", lambda _: pd.DataFrame())
    monkeypatch.setattr(campaign_propobjectives, "run_cell", lambda *_: (held_frame(), table))

    return main(["campaign_propobjectives.py", "--strategy", "InsideBar", "--preset", "Apex 50K", *extra])


def test_a_run_with_a_verdict_writes_every_replay_and_the_verdict(monkeypatch, tmp_path) -> None:
    table = verdict(shortlists(selection_frame(), [propaccount.APEX_50K], top=2), held_frame())
    assert run_main(monkeypatch, table, "--out", str(tmp_path / "out")) == 0
    written = pd.read_csv(tmp_path / "out" / "verdict.csv")
    assert set(written["strategy"]) == {"InsideBar"}
    assert set(written["stratum"]) == {"unfiltered"}
    assert len(pd.read_csv(tmp_path / "out" / "replays.csv")) == len(held_frame())


def test_a_run_with_nothing_replayed_held_out_fails_rather_than_writing_an_empty_table(
    monkeypatch, tmp_path
) -> None:
    """An empty report is indistinguishable from a cell with nothing to say."""
    assert run_main(monkeypatch, pd.DataFrame(), "--out", str(tmp_path / "out")) == 1
    assert not (tmp_path / "out").exists()


def test_an_unknown_preset_is_refused_by_name(monkeypatch) -> None:
    monkeypatch.setattr(campaign_propobjectives, "run_cell", lambda *_: (held_frame(), pd.DataFrame()))
    with pytest.raises(propaccount.PropAccountError, match="unknown preset"):
        main(["campaign_propobjectives.py", "--strategy", "InsideBar", "--preset", "Apex 40K"])


def test_a_rerun_of_an_unknown_archetype_fails_before_it_re_runs_anything() -> None:
    """A wrong name is a KeyError up front rather than a log rebuilt from another archetype's
    parameters."""
    with pytest.raises(KeyError):
        list(campaign_propobjectives.rerun_logs("NoSuchArchetype", pd.DataFrame(), ROOT, pd.DataFrame()))
