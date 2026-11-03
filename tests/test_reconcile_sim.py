"""The sim trade-list comparison, over the rows a real Trade Performance export holds."""

from pathlib import Path

import pandas as pd
import pytest

from nqbt import paths
from nqbt.instruments import ContractId
from tools import reconcile_nt8, reconcile_sim

HEADER = (
    "Trade number,Instrument,Account,Strategy,Market pos.,Qty,Entry price,Exit price,"
    "Entry time,Exit time,Entry name,Exit name,Profit,Cum. net profit,Commission,"
    "Clearing Fee,Exchange Fee,IP Fee,NFA Fee,MAE,MFE,ETD,Bars,\n"
)
ROW = (
    "1,{instrument},{account},X,Long,4,25000.00,25010.00,{entry},{exit},entry1,Profit target,"
    "$80.00,$80.00,$0.00,$0.00,$0.00,$0.00,$0.00,$0.00,$80.00,$0.00,5,\n"
)
FILL = (
    "1,MNQ 12-26,SimAccount1,X,{side},{quantity},{entry_price},{exit_price},"
    "03/11/2026 3:35:00 PM,{exit_time},"
    "{entry_name},{exit_name},{profit},$80.00,$0.00,$0.00,$0.00,$0.00,$0.00,$0.00,$80.00,$0.00,2,\n"
)
START = pd.Timestamp("2026-11-03 14:00", tz="UTC")
END = pd.Timestamp("2026-11-03 21:00", tz="UTC")
MNQ_TICK = 0.25


def export(
    tmp_path: Path,
    entry: str = "03/11/2026 3:35:02 PM",
    exit_time: str = "03/11/2026 3:42:17 PM",
    account: str = "SimAccount1",
    instrument: str = "MNQ 12-26",
    extra_row: str = "",
) -> Path:
    path = tmp_path / "trades.csv"
    row = ROW.format(instrument=instrument, account=account, entry=entry, exit=exit_time)
    path.write_text(HEADER + row + extra_row, encoding="utf-8")

    return path


def fill_row(
    quantity: int,
    entry_price: float = 25000.0,
    exit_price: float = 25010.0,
    exit_name: str = "Profit target",
    exit_time: str = "03/11/2026 3:42:17 PM",
    entry_name: str = "entry1",
    side: str = "Long",
) -> str:
    return FILL.format(
        side=side,
        quantity=quantity,
        entry_price=f"{entry_price:.2f}",
        exit_price=f"{exit_price:.2f}",
        exit_time=exit_time,
        entry_name=entry_name,
        exit_name=exit_name,
        profit=f"${(exit_price - entry_price) * quantity * 2:.2f}",
    )


def fills(tmp_path: Path, *rows: str) -> pd.DataFrame:
    path = tmp_path / "trades.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")

    return reconcile_nt8.parse_nt8(path)


def nqbt_leg(entry: str = "2026-11-03 15:40", exit_time: str = "2026-11-03 15:45") -> dict[str, object]:
    return {
        "entry_time": pd.Timestamp(entry, tz="UTC"),
        "exit_time": pd.Timestamp(exit_time, tz="UTC"),
        "leg": 1,
        "quantity": 4,
        "entry_price": 25000.0,
        "exit_price": 25010.0,
        "net_pnl": 80.0,
        "exit_reason": "target",
    }


def compare(sim: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    return reconcile_sim.compare_sim(sim, other, "nqbt", START, END, 5, MNQ_TICK)


def test_a_live_fill_joins_the_backtest_leg_on_the_bar_it_filled_in(tmp_path: Path) -> None:
    """The fill comes just after the signal bar closes, and a backtest stamps the bar after it."""
    both = compare(reconcile_nt8.parse_nt8(export(tmp_path)), pd.DataFrame([nqbt_leg()]))

    assert len(both) == 1
    assert both["exit_time_sim"].iloc[0] == pd.Timestamp("2026-11-03 15:45", tz="UTC")
    assert both["exit_time_sim"].iloc[0] == both["exit_time_nqbt"].iloc[0]


@pytest.mark.parametrize(
    "fill",
    ["03/11/2026 3:34:59 PM", "03/11/2026 3:35:00 PM", "03/11/2026 3:35:01 PM", "03/11/2026 3:36:20 PM"],
)
def test_a_market_entry_stays_on_its_bar_either_side_of_the_boundary(tmp_path: Path, fill: str) -> None:
    """A clock a second behind the bars must not move the entry a whole bar earlier."""
    both = compare(reconcile_nt8.parse_nt8(export(tmp_path, entry=fill)), pd.DataFrame([nqbt_leg()]))

    assert len(both) == 1


def test_an_exit_on_a_bar_boundary_belongs_to_the_bar_ending_there(tmp_path: Path) -> None:
    sim = reconcile_nt8.parse_nt8(export(tmp_path, exit_time="03/11/2026 3:45:00 PM"))

    stamped = reconcile_sim.to_bar_stamps(sim, 5)

    assert stamped["exit_time"].iloc[0] == pd.Timestamp("2026-11-03 15:45", tz="UTC")


def test_a_trade_only_nqbt_took_is_not_joined_or_dropped_at_the_windows_edge(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The pass bar is no trade missing, so a missed first trade has to count against it."""
    before_the_first_sim_trade = nqbt_leg("2026-11-03 14:10", "2026-11-03 14:15")
    other = pd.DataFrame([before_the_first_sim_trade, nqbt_leg()])

    with caplog.at_level("INFO"):
        both = compare(reconcile_nt8.parse_nt8(export(tmp_path)), other)

    assert len(both) == 1
    assert any("nqbt only" in message and message.endswith("1") for message in caplog.messages)


def test_nqbts_trades_outside_the_window_are_not_reported_as_missed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    other = pd.DataFrame([nqbt_leg("2026-11-02 15:40", "2026-11-02 15:45"), nqbt_leg()])

    with caplog.at_level("INFO"):
        compare(reconcile_nt8.parse_nt8(export(tmp_path)), other)

    assert any("nqbt only" in message and message.endswith("0") for message in caplog.messages)


def test_a_wrong_date_order_is_refused_rather_than_read_as_march(tmp_path: Path) -> None:
    """An en-US machine's 11/03 parses cleanly as 11 March under the day-first format."""
    sim = reconcile_nt8.parse_nt8(
        export(tmp_path, entry="11/03/2026 3:35:02 PM", exit_time="11/03/2026 3:42:17 PM")
    )

    with pytest.raises(SystemExit, match="--month-first"):
        compare(sim, pd.DataFrame([nqbt_leg()]))


def test_month_first_reads_an_en_us_export_without_leading_zeros(tmp_path: Path) -> None:
    path = export(tmp_path, entry="11/3/2026 3:35:02 PM", exit_time="11/3/2026 3:42:17 PM")

    sim = reconcile_nt8.parse_nt8(path, day_first=False)

    assert sim["entry_time"].iloc[0] == pd.Timestamp("2026-11-03 15:35:02", tz="UTC")
    assert len(compare(sim, pd.DataFrame([nqbt_leg()]))) == 1


def test_a_split_fill_merges_into_one_leg_at_its_weighted_prices(tmp_path: Path) -> None:
    """Three lots at one price and one at another average by lots, not by rows."""
    sim = fills(tmp_path, fill_row(3, 25000.0, 25010.0), fill_row(1, 25004.0, 25014.0))

    both = compare(sim, pd.DataFrame([nqbt_leg()]))

    assert len(both) == 1
    assert both["entry_price_sim"].iloc[0] == pytest.approx(25001.0)
    assert both["exit_price_sim"].iloc[0] == pytest.approx(25011.0)
    assert both["quantity_sim"].iloc[0] == 4
    assert both["net_pnl_sim"].iloc[0] == pytest.approx(80.0)


def test_each_of_a_trades_legs_keeps_its_own_row(tmp_path: Path) -> None:
    """Rows sharing a bar merge only within a leg: the runner is not the bracketed lot."""
    sim = fills(
        tmp_path,
        fill_row(2),
        fill_row(2),
        fill_row(2, exit_price=25030.0, entry_name="entry2", exit_name="Trail stop"),
    )

    merged = reconcile_sim.merge_split_fills(reconcile_sim.to_bar_stamps(sim, 5))

    assert list(merged["leg"]) == [1, 2]
    assert list(merged["quantity"]) == [4, 2]
    assert list(merged["exit_reason"]) == ["target", "stop"]


def test_a_split_exit_over_two_bars_closes_the_leg_on_the_later_one(tmp_path: Path) -> None:
    """A backtest leg closes on one bar, so the disagreement has to show rather than average away."""
    sim = fills(
        tmp_path,
        fill_row(2, exit_time="03/11/2026 3:44:59 PM"),
        fill_row(2, exit_time="03/11/2026 3:45:01 PM"),
    )

    merged = reconcile_sim.merge_split_fills(reconcile_sim.to_bar_stamps(sim, 5))

    assert merged["exit_time"].iloc[0] == pd.Timestamp("2026-11-03 15:50", tz="UTC")


def test_a_leg_closed_for_two_reasons_reads_as_a_disagreement(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A target part filled before the stop took the rest is real, and must not pass as one exit."""
    sim = fills(tmp_path, fill_row(2), fill_row(2, exit_price=24990.0, exit_name="Stop loss"))

    with caplog.at_level("INFO"):
        both = compare(sim, pd.DataFrame([nqbt_leg()]))

    assert both["exit_reason_sim"].iloc[0] == "stop+target"
    assert any("identical exit reason" in message and "0 (0.00%)" in message for message in caplog.messages)


def test_both_sides_on_one_bar_and_leg_are_refused(tmp_path: Path) -> None:
    """A restart can leave two real trades there, and merging them would net one against the other."""
    sim = fills(tmp_path, fill_row(4), fill_row(4, side="Short"))

    with pytest.raises(SystemExit, match="both sides"):
        compare(sim, pd.DataFrame([nqbt_leg()]))


def test_a_leg_part_open_at_the_export_is_refused(tmp_path: Path) -> None:
    sim = fills(tmp_path, fill_row(3))

    with pytest.raises(SystemExit, match="different quantity from nqbt"):
        compare(sim, pd.DataFrame([nqbt_leg()]))


def test_a_leg_only_the_sim_holds_counts_as_missing_whatever_its_quantity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    other = pd.DataFrame([nqbt_leg("2026-11-03 16:40", "2026-11-03 16:45")])

    with caplog.at_level("INFO"):
        both = compare(fills(tmp_path, fill_row(3)), other)

    assert both.empty
    assert any("Sim only" in message and message.endswith("1") for message in caplog.messages)


def test_an_export_mixing_accounts_is_refused(tmp_path: Path) -> None:
    second_row = ROW.format(
        instrument="MNQ 12-26",
        account="Sim101",
        entry="03/11/2026 4:35:02 PM",
        exit="03/11/2026 4:42:17 PM",
    )

    with pytest.raises(SystemExit, match="Sim101"):
        reconcile_sim.refuse_mixed_export(export(tmp_path, extra_row=second_row), "MNQ 12-26")


def test_an_export_of_another_contract_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="MNQ 03-27"):
        reconcile_sim.refuse_mixed_export(export(tmp_path, instrument="MNQ 03-27"), "MNQ 12-26")


def test_an_account_with_no_trades_reports_every_nqbt_leg_as_missed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "trades.csv"
    path.write_text(HEADER, encoding="utf-8")

    with caplog.at_level("INFO"):
        both = compare(reconcile_nt8.parse_nt8(path), pd.DataFrame([nqbt_leg()]))

    assert both.empty
    assert any("nqbt only" in message and message.endswith("1") for message in caplog.messages)


def test_the_price_gap_is_measured_in_ticks_per_exit_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    leg = nqbt_leg() | {"entry_price": 25000.5, "exit_price": 25009.0}

    with caplog.at_level("INFO"):
        compare(reconcile_nt8.parse_nt8(export(tmp_path)), pd.DataFrame([leg]))

    assert any("mean entry gap" in message and "2.00 ticks" in message for message in caplog.messages)
    assert any("mean exit gap, target" in message and "4.00 ticks" in message for message in caplog.messages)


def test_a_reversal_is_held_out_of_the_comparison(tmp_path: Path) -> None:
    path = export(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Profit target", "Close position"), encoding="utf-8"
    )

    both = compare(reconcile_nt8.parse_nt8(path), pd.DataFrame([nqbt_leg()]))

    assert both.empty


def test_the_outer_edges_of_the_window_count(tmp_path: Path) -> None:
    """A leg signalled exactly at ``--to`` is still inside, on both sides."""
    sim = reconcile_nt8.parse_nt8(export(tmp_path))
    edge = pd.Timestamp("2026-11-03 15:35", tz="UTC")

    both = reconcile_sim.compare_sim(sim, pd.DataFrame([nqbt_leg()]), "nqbt", START, edge, 5, MNQ_TICK)

    assert len(both) == 1


def test_a_signal_before_the_strategy_went_live_is_not_reported_as_missed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A backtest stamps its entry a bar after the signal, so the stamp can pass ``--from``."""
    sim = reconcile_nt8.parse_nt8(export(tmp_path))
    signalled_at_14_00 = nqbt_leg("2026-11-03 14:05", "2026-11-03 14:10")
    went_live = pd.Timestamp("2026-11-03 14:03", tz="UTC")

    with caplog.at_level("INFO"):
        reconcile_sim.compare_sim(
            sim, pd.DataFrame([signalled_at_14_00, nqbt_leg()]), "nqbt", went_live, END, 5, MNQ_TICK
        )

    assert any("nqbt only" in message and message.endswith("0") for message in caplog.messages)


def test_a_window_ending_inside_the_bar_keeps_the_trade_on_both_sides(tmp_path: Path) -> None:
    """The sim's fill at 15:35:02 and nqbt's stamp of 15:40 are the same trade, either side of 15:37."""
    sim = reconcile_nt8.parse_nt8(export(tmp_path))
    end = pd.Timestamp("2026-11-03 15:37", tz="UTC")

    both = reconcile_sim.compare_sim(sim, pd.DataFrame([nqbt_leg()]), "nqbt", START, end, 5, MNQ_TICK)

    assert len(both) == 1


def test_a_clock_a_second_behind_at_the_window_start_is_not_refused(tmp_path: Path) -> None:
    sim = reconcile_nt8.parse_nt8(export(tmp_path, entry="03/11/2026 3:34:59 PM"))
    start = pd.Timestamp("2026-11-03 15:35", tz="UTC")

    both = reconcile_sim.compare_sim(sim, pd.DataFrame([nqbt_leg()]), "nqbt", start, END, 5, MNQ_TICK)

    assert len(both) == 1


def test_a_reversal_on_the_other_side_is_held_out_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    other = pd.DataFrame([nqbt_leg() | {"exit_reason": reconcile_nt8.REVERSAL}])

    with caplog.at_level("INFO"):
        both = compare(reconcile_nt8.parse_nt8(export(tmp_path)), other)

    assert both.empty
    assert any("nqbt legs" in message and message.endswith("0") for message in caplog.messages)


def analyzer_run(tmp_path: Path, entry: str, exit_time: str) -> list[str]:
    sim_dir = tmp_path / "sim"
    sim_dir.mkdir()
    analyzer_dir = tmp_path / "analyzer"
    analyzer_dir.mkdir()

    return [
        "reconcile_sim.py",
        str(export(sim_dir)),
        "InsideBar-sim",
        "MNQ 12-26",
        "--from",
        "2026-11-03 14:00",
        "--to",
        "2026-11-03 21:00",
        "--analyzer",
        str(export(analyzer_dir, entry=entry, exit_time=exit_time)),
    ]


def test_an_analyzer_export_entirely_outside_the_window_is_warned_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A misread analyzer date order drops every leg, and that must not read as trades missing."""
    assert reconcile_sim.main(analyzer_run(tmp_path, "11/03/2026 3:40:00 PM", "11/03/2026 3:45:00 PM")) == 0

    captured = capsys.readouterr()
    assert "check its date order" in captured.out + captured.err


def test_an_analyzer_export_inside_the_window_draws_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert reconcile_sim.main(analyzer_run(tmp_path, "03/11/2026 3:40:00 PM", "03/11/2026 3:45:00 PM")) == 0

    captured = capsys.readouterr()
    assert "check its date order" not in captured.out + captured.err


def test_no_nqbt_trade_in_the_window_is_not_blamed_on_the_date_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The dates of nqbt's legs come from the bars, so a window it did not trade in is only that."""
    earlier = nqbt_leg("2026-10-27 15:40", "2026-10-27 15:45")

    with caplog.at_level("WARNING"):
        compare(reconcile_nt8.parse_nt8(export(tmp_path)), pd.DataFrame([earlier]))

    assert not caplog.messages


def test_an_analyzer_export_of_another_contract_is_refused(tmp_path: Path) -> None:
    sim_dir = tmp_path / "sim"
    sim_dir.mkdir()
    analyzer_dir = tmp_path / "analyzer"
    analyzer_dir.mkdir()

    with pytest.raises(SystemExit, match="MNQ 03-27"):
        reconcile_sim.main(
            [
                "reconcile_sim.py",
                str(export(sim_dir)),
                "InsideBar-sim",
                "MNQ 12-26",
                "--from",
                "2026-11-03 14:00",
                "--to",
                "2026-11-03 21:00",
                "--analyzer",
                str(export(analyzer_dir, instrument="MNQ 03-27")),
            ]
        )


def test_bars_and_an_analyzer_export_cannot_both_be_given(tmp_path: Path) -> None:
    """The bars feed the nqbt run an analyzer comparison never makes."""
    with pytest.raises(SystemExit):
        reconcile_sim.main(
            [
                "reconcile_sim.py",
                str(tmp_path / "absent.csv"),
                "InsideBar-sim",
                "MNQ 12-26",
                "--from",
                "2026-11-03",
                "--to",
                "2026-11-04",
                "--bars",
                "bars.txt",
                "--analyzer",
                "analyzer.csv",
            ]
        )


def test_a_bars_export_named_for_another_contract_is_refused(tmp_path: Path) -> None:
    bars = tmp_path / "MNQ 03-27.Last.txt"
    bars.write_text("20261103 150100;25000;25001;24999;25000.5;10\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="MNQ 03-27"):
        reconcile_nt8.load_bars(ContractId.parse("MNQ 12-26"), bars)


def test_an_analyzer_export_holding_split_rows_is_merged_before_it_joins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two rows on that side would join one sim leg twice and read as a perfect match."""
    argv = analyzer_run(tmp_path, "03/11/2026 3:40:00 PM", "03/11/2026 3:45:00 PM")
    analyzer = Path(argv[-1])
    half = (
        analyzer.read_text(encoding="utf-8")
        .splitlines(keepends=True)[1]
        .replace(",Long,4,", ",Long,2,")
        .replace("$80.00,$80.00", "$40.00,$40.00")
    )
    analyzer.write_text(HEADER + half + half, encoding="utf-8")

    assert reconcile_sim.main(argv) == 0

    captured = capsys.readouterr().out
    assert "joined            1" in captured
    assert "identical P&L         1 (100.00%)" in captured


def test_a_strategy_analyzer_export_can_be_the_other_side(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = reconcile_sim.main(analyzer_run(tmp_path, "03/11/2026 3:40:00 PM", "03/11/2026 3:45:00 PM"))

    assert code == 0
    # The agreement lines log from reconcile_nt8, whose logger the entry point has to switch on.
    assert "joined            1" in capsys.readouterr().out


def test_an_unknown_config_is_refused_before_anything_is_read(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="InsideBar-sim"):
        reconcile_sim.main(
            [
                "reconcile_sim.py",
                str(tmp_path / "absent.csv"),
                "Nope",
                "MNQ 12-26",
                "--from",
                "2026-11-03",
                "--to",
                "2026-11-04",
            ]
        )


def test_the_bars_export_is_read_instead_of_the_cache_and_leaves_the_cache_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive stays frozen, so the sim period's bars must not need ingesting."""

    def fail_if_called(_contract: object) -> None:
        pytest.fail("the cached contract was read")

    monkeypatch.setattr("tools.reconcile_nt8.ingest.load_contract", fail_if_called)
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    bars = tmp_path / "MNQ 12-26.Last.txt"
    bars.write_text("20261103 150100;25000;25001;24999;25000.5;10\n", encoding="utf-8")

    loaded = reconcile_nt8.load_bars(ContractId.parse("MNQ 12-26"), bars)

    assert list(loaded["close"]) == [25000.5]
    assert not (tmp_path / "cache").exists()


def test_without_a_bars_export_the_cache_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = pd.DataFrame({"close": [1.0]})
    monkeypatch.setattr("tools.reconcile_nt8.ingest.load_contract", lambda _contract: sentinel)

    assert reconcile_nt8.load_bars(ContractId.parse("MNQ 12-26"), None) is sentinel


def test_the_sim_configs_hold_the_settings_the_accounts_were_given() -> None:
    """The November 2026 sim's three accounts, and the one rule that splits InsideBar's in two."""
    midday = reconcile_nt8.CONFIGS["InsideBarTrailing-midday-2035"].params.as_dict()
    whole = reconcile_nt8.CONFIGS["InsideBarTrailing-2035"].params.as_dict()
    assert {k for k in whole if whole[k] != midday[k]} == {"phase_filter"}

    live = reconcile_nt8.CONFIGS["InsideBar-sim"].params.as_dict()
    analyzer = reconcile_nt8.CONFIGS["InsideBar-sim-analyzer"].params.as_dict()
    assert {k for k in live if live[k] != analyzer[k]} == {"no_entry_minutes_before_close"}
    assert live["no_entry_minutes_before_close"] == 60
    assert analyzer["no_entry_minutes_before_close"] == 0
    assert (live["ema_period"], live["fast_sma_period"], live["slow_sma_period"]) == (44, 50, 200)
    assert (live["error_margin"], live["atr_length"], live["atr_multiplier"]) == (0.10, 14, 20.0)
    assert (live["tp_multiplier"], live["order_quantity"]) == (1.0, 4)
