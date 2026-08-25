"""Trade-import tests: the NT8 executions grid in, the canonical schema out.

Three claims are pinned harder than the rest, because each fails silently rather than loudly.
**Row timestamps are ``DD/MM``**, so every date test uses a day past the twelfth in one half and
a day under it in the other -- under ``MM/DD`` the second half parses to a real but wrong date.
**Ties are ordered by the position chain, never by file order**, and the fixture for that is two
real exports of one history that disagree about the order of two fills sharing a second.
**Costs come from the project, never from the file**, whose ``Commission`` column reads ``$0.00``
on an account that is charged.
"""

import pandas as pd
import pytest

from nqbt import costs, ingest, instruments, stats, trade_import, trades
from nqbt.instruments import ContractId
from nqbt.trade_import import TradeImportError

TZ = "Europe/London"

FULL_HEADER = "Instrument,Action,Quantity,Price,Time,E/X,Position,Name,Commission,Account display name,"
HEADER = "Instrument,Action,Quantity,Price,Time,Position,Name,"

# The 10 August 2026 session, verbatim from a Control Center -> Executions export: newest first,
# a trailing comma on every row, and three fills sharing 6:07:25. Two trades, -$173.50 gross.
SAMPLE = [
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,Exit,-,Stop4,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,Exit,1 S,Stop3,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,1,29783.25,10/08/2026 6:07:25 PM,Exit,2 S,Stop2,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,1,29761.75,10/08/2026 6:04:13 PM,Exit,3 S,Exit,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Sell,4,29767.00,10/08/2026 6:03:07 PM,Entry,4 S,Entry,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,2,29782.75,10/08/2026 6:00:29 PM,Exit,-,Stop1,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,1,29776.50,10/08/2026 6:00:21 PM,Exit,2 S,Exit,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Buy,1,29776.25,10/08/2026 6:00:17 PM,Exit,3 S,Exit,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Sell,2,29768.50,10/08/2026 5:58:52 PM,Entry,4 S,Entry,$0.00,TAKEPROFIT385029293,",
    "MNQ 09-26,Sell,2,29769.00,10/08/2026 5:58:49 PM,Entry,2 S,Entry,$0.00,TAKEPROFIT385029293,",
]

SAMPLE_GROSS = -173.50
SAMPLE_TRADE_GROSS = {1: -86.50, 2: -87.00}


def grid(tmp_path, rows, *, header=HEADER, name="grid.csv"):
    """Write ``rows`` as an executions grid: newest first, CRLF, trailing comma intact."""
    path = tmp_path / name
    path.write_text("\r\n".join([header, *rows, ""]), encoding="utf-8")
    return path


def fill(time, order, price, position, name="Entry"):
    """One row of the minimal column set. ``order`` reads as it does on the grid: ``"Sell 4"``."""
    action, quantity = order.split()
    return f"MNQ 09-26,{action},{quantity},{price},{time},{position},{name},"


def chronological(tmp_path, rows, **kwargs: str):
    """Write rows given oldest-first, reversing them the way the grid itself does."""
    return grid(tmp_path, list(reversed(rows)), **kwargs)


def short_scale_out(tmp_path):
    """Four short at 100, out one at 99, then three at 105. One trade, four legs."""
    return chronological(
        tmp_path,
        [
            fill("06/08/2026 1:00:00 PM", "Sell 4", "100.00", "4 S"),
            fill("06/08/2026 1:01:00 PM", "Buy 1", "99.00", "3 S", "Exit"),
            fill("06/08/2026 1:02:00 PM", "Buy 3", "105.00", "-", "Stop1"),
        ],
    )


def cache_bars(cache_dir, contract, first, last):
    """Write a minimal cached-bar file so coverage has a real range to read."""
    path = ingest.contract_cache_path(ContractId.parse(contract), cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = pd.DatetimeIndex([first, last], tz="UTC", name="ts_utc")
    pd.DataFrame({"close": [1.0, 2.0]}, index=index).to_parquet(path)
    return path


# -- the worked example -------------------------------------------------------


def test_the_sample_export_reproduces_its_two_trades_and_gross_pnl(tmp_path):
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        commission_per_contract=0.0,
    )
    per_trade = imported.frame.groupby("trade_id")["gross_pnl"].sum()
    assert per_trade.to_dict() == SAMPLE_TRADE_GROSS
    assert imported.frame["gross_pnl"].sum() == pytest.approx(SAMPLE_GROSS)


def test_the_sample_exit_reasons_survive_as_the_grid_wrote_them(tmp_path):
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
    )
    assert imported.frame["exit_reason"].tolist() == [
        "Exit",
        "Exit",
        "Stop1",
        "Exit",
        "Stop2",
        "Stop3",
        "Stop4",
    ]


def test_the_sample_is_seven_legs_across_two_trades_not_seven_trades(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert len(imported.frame) == 7
    assert imported.frame["trade_id"].nunique() == 2


def test_an_imported_log_passes_the_shared_schema_validation(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert trades.validate(imported.frame) is imported.frame
    assert set(imported.frame["source"]) == {"manual"}
    assert set(imported.frame["instrument"]) == {"MNQ"}


# -- ordering -----------------------------------------------------------------


def test_tied_fills_are_ordered_by_the_position_chain_not_by_file_order(tmp_path):
    """Two real exports put these two fills in opposite order; both must import identically."""
    first = [
        fill("13/08/2026 2:30:42 PM", "Buy 1", "29912.75", "4 L"),
        fill("13/08/2026 2:30:42 PM", "Buy 1", "29911.25", "3 L"),
        fill("13/08/2026 2:30:17 PM", "Buy 1", "29896.50", "2 L"),
        fill("13/08/2026 2:29:56 PM", "Buy 1", "29911.75", "1 L"),
    ]
    swapped = [first[1], first[0], *first[2:]]
    closes = [
        fill("13/08/2026 2:34:33 PM", "Sell 4", "29938.00", "-", "Exit"),
    ]

    a = trade_import.import_executions(grid(tmp_path, closes + first, name="a.csv"), timezone=TZ)
    b = trade_import.import_executions(grid(tmp_path, closes + swapped, name="b.csv"), timezone=TZ)
    pd.testing.assert_frame_equal(a.frame, b.frame, check_exact=True)

    # And the chain, not the file, decided which entry price is which leg.
    assert a.frame["entry_price"].tolist() == [29911.75, 29896.50, 29911.25, 29912.75]


def test_sorting_the_tied_fills_on_price_would_have_scrambled_them(tmp_path):
    """The null: a stable sort on anything but the chain reverses two of these four legs."""
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    tied = imported.frame[imported.frame["exit_time"] == imported.frame["exit_time"].max()]
    assert tied["exit_reason"].tolist() == ["Stop2", "Stop3", "Stop4"]


def test_an_export_that_is_not_newest_first_is_refused(tmp_path):
    rows = [
        fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "1 S"),
        fill("06/08/2026 1:01:00 PM", "Buy 1", "99.00", "-", "Exit"),
    ]
    with pytest.raises(TradeImportError, match="newest first"):
        trade_import.read_executions(grid(tmp_path, rows), timezone=TZ)


def test_a_position_walk_that_cannot_be_chained_is_refused(tmp_path):
    """A missing fill leaves a gap the running position cannot bridge."""
    rows = [
        fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "1 S"),
        fill("06/08/2026 1:01:00 PM", "Sell 1", "100.00", "4 S"),
        fill("06/08/2026 1:02:00 PM", "Buy 4", "99.00", "-", "Exit"),
    ]
    with pytest.raises(TradeImportError, match="position walk breaks"):
        trade_import.read_executions(chronological(tmp_path, rows), timezone=TZ)


# -- dates and times ----------------------------------------------------------


def test_row_timestamps_are_read_as_day_first(tmp_path):
    """``10/08`` is 10 August. Under ``MM/DD`` it would be 8 October and never error."""
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert imported.frame["entry_time"].min().month == 8
    assert imported.frame["entry_time"].min().day == 10


def test_a_day_past_the_twelfth_parses_rather_than_being_rejected(tmp_path):
    fills = trade_import.read_executions(short_scale_out(tmp_path), timezone=TZ)
    assert fills["time"].iloc[0].day == 6

    rows = [
        fill("31/12/2026 1:00:00 PM", "Sell 1", "100.00", "1 S"),
        fill("31/12/2026 1:01:00 PM", "Buy 1", "99.00", "-", "Exit"),
    ]
    late = trade_import.read_executions(chronological(tmp_path, rows, name="late.csv"), timezone=TZ)
    assert late["time"].iloc[0].month == 12


def test_a_twenty_four_hour_clock_is_accepted_and_still_day_first(tmp_path):
    rows = [
        fill("13/08/2026 14:29:56", "Sell 1", "100.00", "1 S"),
        fill("13/08/2026 14:34:33", "Buy 1", "99.00", "-", "Exit"),
    ]
    fills = trade_import.read_executions(chronological(tmp_path, rows), timezone=TZ)
    assert fills["time"].iloc[0].day == 13
    assert fills["time"].iloc[0].month == 8


def test_a_time_matching_no_accepted_format_is_refused_rather_than_guessed(tmp_path):
    rows = [
        fill("2026-08-06T13:00:00", "Sell 1", "100.00", "1 S"),
        fill("2026-08-06T13:01:00", "Buy 1", "99.00", "-", "Exit"),
    ]
    with pytest.raises(TradeImportError, match="not inferred from the values"):
        trade_import.read_executions(chronological(tmp_path, rows), timezone=TZ)


def test_the_timezone_is_applied_and_a_different_one_moves_every_trade(tmp_path):
    """Both halves: the wall-clock reading is unchanged, and the UTC instant is not."""
    path = grid(tmp_path, SAMPLE, header=FULL_HEADER)
    london = trade_import.read_executions(path, timezone=TZ)["time"]
    eastern = trade_import.read_executions(path, timezone="America/New_York")["time"]

    assert london.dt.tz_convert(TZ).dt.strftime("%H:%M:%S").tolist() == [
        "17:58:49",
        "17:58:52",
        "18:00:17",
        "18:00:21",
        "18:00:29",
        "18:03:07",
        "18:04:13",
        "18:07:25",
        "18:07:25",
        "18:07:25",
    ]
    assert (eastern - london).unique().tolist() == [pd.Timedelta(hours=5)]


def test_the_timezone_has_no_default(tmp_path):
    with pytest.raises(TypeError):
        trade_import.read_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER))  # type: ignore[call-arg]  # the omission is the point


# -- FIFO matching ------------------------------------------------------------


def test_partial_exits_are_matched_fifo_against_the_oldest_lot(tmp_path):
    """The sample's first trade has two entry lots; the first exit must take the older one."""
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    first = imported.frame[imported.frame["trade_id"] == 1]
    assert first["entry_price"].tolist() == [29769.00, 29769.00, 29768.50]
    assert first["quantity"].tolist() == [1, 1, 2]


def test_fifo_and_average_entry_agree_per_trade_and_differ_per_leg(tmp_path):
    """Why the matching rule matters: it is invisible in the total and decides every leg."""
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        commission_per_contract=0.0,
    )
    first = imported.frame[imported.frame["trade_id"] == 1]
    average = first["entry_price"].mul(first["quantity"]).sum() / first["quantity"].sum()
    point_value = instruments.get_instrument("MNQ").point_value
    as_average = (average - first["exit_price"]) * point_value * first["quantity"]

    assert as_average.sum() == pytest.approx(first["gross_pnl"].sum())
    assert as_average.tolist() != first["gross_pnl"].tolist()


def test_a_scale_out_is_one_trade_with_several_legs(tmp_path):
    imported = trade_import.import_executions(short_scale_out(tmp_path), timezone=TZ)
    assert set(imported.frame["trade_id"]) == {1}
    assert imported.frame["leg"].tolist() == [1, 2]
    assert imported.frame["quantity"].tolist() == [1, 3]


def test_a_flip_becomes_two_trades_each_paying_its_own_costs(tmp_path):
    rows = [
        fill("06/08/2026 1:00:00 PM", "Buy 2", "100.00", "2 L"),
        fill("06/08/2026 1:01:00 PM", "Sell 5", "105.00", "3 S", "Exit"),
        fill("06/08/2026 1:02:00 PM", "Buy 3", "101.00", "-", "Exit"),
    ]
    imported = trade_import.import_executions(chronological(tmp_path, rows), timezone=TZ)
    assert imported.frame["trade_id"].tolist() == [1, 2]
    assert imported.frame["direction"].tolist() == [trades.LONG, trades.SHORT]
    assert imported.frame["commission"].sum() == pytest.approx(5 * costs.LIVE.commission_per_contract)


def test_direction_is_the_side_the_leg_was_entered_on(tmp_path):
    imported = trade_import.import_executions(short_scale_out(tmp_path), timezone=TZ)
    assert set(imported.frame["direction"]) == {trades.SHORT}
    assert imported.frame["gross_pnl"].tolist() == [2.0, -30.0]


# -- costs --------------------------------------------------------------------


def test_commission_comes_from_the_project_not_from_the_files_zero(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    expected = costs.LIVE.commission_per_contract * imported.frame["quantity"]
    assert imported.frame["commission"].tolist() == expected.tolist()
    assert imported.frame["commission"].sum() > 0.0


def test_net_pnl_is_gross_less_commission_on_every_leg(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert (
        imported.frame["net_pnl"].tolist()
        == (imported.frame["gross_pnl"] - imported.frame["commission"]).tolist()
    )


def test_dollars_come_from_the_instrument_so_nq_is_ten_times_mnq(tmp_path):
    rows = [
        fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "1 S").replace("MNQ", "NQ"),
        fill("06/08/2026 1:01:00 PM", "Buy 1", "99.00", "-", "Exit").replace("MNQ", "NQ"),
    ]
    big = trade_import.import_executions(chronological(tmp_path, rows, name="nq.csv"), timezone=TZ)
    small = trade_import.import_executions(short_scale_out(tmp_path), timezone=TZ)

    assert big.frame["instrument"].tolist() == ["NQ"]
    assert big.frame["gross_pnl"].iloc[0] == pytest.approx(10 * small.frame["gross_pnl"].iloc[0])


# -- what the source cannot supply --------------------------------------------


def test_every_nullable_schema_column_has_a_stated_reason():
    assert set(trade_import.UNPOPULATED) == set(trades.NULLABLE)
    assert set(trade_import.POPULATED) == set(trades.REQUIRED)


def test_the_unavailable_columns_are_null_rather_than_zero(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    for name in trades.NULLABLE:
        assert imported.frame[name].isna().all(), name
    assert imported.populated == trade_import.POPULATED


def test_absent_integer_columns_keep_a_nullable_dtype(tmp_path):
    """Absent, not zero and not NaN-in-a-float-column, so M11.2 can fill them without a cast."""
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert imported.frame["bars_held"].dtype == "Int64"
    assert imported.frame["ambiguous_bar"].dtype == "boolean"
    assert imported.frame["mae_points"].dtype == "float64"


def test_an_imported_log_cannot_be_summarised_into_a_bar_count_by_accident(tmp_path):
    """The failure this guards: an absent column reaching ``summarise`` and reading as measured.

    Refusing is the correct half of that. Omitting the statistic with its reason is the review's
    job, off :attr:`ImportedTrades.populated` -- [#48], and [#81] for the same hazard on times.
    """
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    with pytest.raises(TypeError):
        stats.summarise(imported.frame)

    per_trade = stats.per_trade(imported.frame)
    assert per_trade["bars_held"].isna().all()
    assert per_trade["net_pnl"].tolist() == [-92.5, -93.0]


def test_the_frame_carries_the_contract_not_only_the_root(tmp_path):
    """M11.2 annotates against the per-contract series; the root alone cannot address one."""
    imported = trade_import.import_executions(grid(tmp_path, SAMPLE, header=FULL_HEADER), timezone=TZ)
    assert set(imported.frame["contract"]) == {"MNQ 09-26"}


# -- coverage -----------------------------------------------------------------


def test_coverage_is_measured_against_the_cached_bars(tmp_path):
    cache = tmp_path / "cache"
    cache_bars(cache, "MNQ 09-26", "2026-08-01 00:00", "2026-08-31 00:00")
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=cache,
    )
    assert imported.coverage.covered == 2
    assert imported.coverage.uncovered == 0
    assert imported.coverage.share == 1.0
    assert len(imported.reviewable) == len(imported.frame)


def test_trades_past_the_end_of_the_cache_are_excluded_loudly_not_dropped(tmp_path):
    """The export lags live by about two hours, so the newest session is routinely uncovered."""
    cache = tmp_path / "cache"
    cache_bars(cache, "MNQ 09-26", "2026-08-01 00:00", "2026-08-10 17:01")
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=cache,
    )
    assert imported.coverage.covered == 1
    assert imported.coverage.uncovered == 1
    assert len(imported.frame) == 7
    assert imported.reviewable["trade_id"].unique().tolist() == [1]


def test_an_uncached_contract_is_reported_rather_than_assumed_covered(tmp_path):
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=tmp_path / "empty",
    )
    assert imported.coverage.share == 0.0
    assert imported.reviewable.empty
    assert [c.cached for c in imported.coverage.contracts] == [False]
    assert "not cached" in str(imported.coverage)


def test_a_trade_straddling_the_end_of_the_cache_is_excluded_whole(tmp_path):
    """Half a trade reviewed and half excluded would misstate the trade's own P&L."""
    cache = tmp_path / "cache"
    cache_bars(cache, "MNQ 09-26", "2026-08-10 16:00", "2026-08-10 17:00:25")
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=cache,
    )
    assert imported.coverage.covered == 0
    assert imported.reviewable.empty


# -- incomplete trades --------------------------------------------------------


def test_an_export_beginning_mid_trade_drops_that_trade_and_counts_it(tmp_path):
    rows = [
        fill("06/08/2026 1:00:00 PM", "Buy 1", "99.00", "1 S", "Exit"),
        fill("06/08/2026 1:01:00 PM", "Buy 1", "98.00", "-", "Exit"),
        fill("06/08/2026 1:02:00 PM", "Sell 1", "100.00", "1 S"),
        fill("06/08/2026 1:03:00 PM", "Buy 1", "97.00", "-", "Exit"),
    ]
    imported = trade_import.import_executions(chronological(tmp_path, rows), timezone=TZ)
    assert imported.incomplete.leading_fills == 2
    assert imported.incomplete.trailing_fills == 0
    assert imported.frame["trade_id"].tolist() == [1]


def test_a_position_still_open_at_the_end_is_dropped_and_counted(tmp_path):
    rows = [
        fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "1 S"),
        fill("06/08/2026 1:01:00 PM", "Buy 1", "99.00", "-", "Exit"),
        fill("06/08/2026 1:02:00 PM", "Sell 2", "101.00", "2 S"),
    ]
    imported = trade_import.import_executions(chronological(tmp_path, rows), timezone=TZ)
    assert imported.incomplete.trailing_fills == 1
    assert imported.incomplete.total == 1
    assert "1 trailing" in str(imported.incomplete)
    assert len(imported.frame) == 1


def test_an_export_holding_no_complete_trade_imports_nothing(tmp_path):
    rows = [fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "1 S")]
    imported = trade_import.import_executions(chronological(tmp_path, rows), timezone=TZ)
    assert imported.frame.empty
    assert imported.incomplete.trailing_fills == 1
    assert imported.coverage.share == 0.0
    assert imported.reviewable.empty


def test_an_export_with_no_rows_at_all_is_an_empty_log(tmp_path):
    imported = trade_import.import_executions(grid(tmp_path, []), timezone=TZ)
    assert imported.frame.empty
    assert list(imported.frame.columns)[:2] == ["source", "instrument"]
    assert imported.incomplete.total == 0


# -- the column set -----------------------------------------------------------


def test_columns_beyond_the_required_set_are_ignored(tmp_path):
    """The grid's columns are configurable; a second export off one machine had six more."""
    header = (
        "Instrument,Action,Quantity,Price,Time,ID,E/X,Position,Order ID,"
        "Name,Commission,Rate,Account,Connection,"
    )
    rows = [
        "MNQ 09-26,Buy,1,99.00,06/08/2026 1:01:00 PM,NT-1,Exit,-,NT-2,Stop loss,$0.00,1,Sim101,,",
        "MNQ 09-26,Sell,1,100.00,06/08/2026 1:00:00 PM,NT-3,Entry,1 S,NT-4,Entry,$0.00,1,Sim101,,",
    ]
    imported = trade_import.import_executions(grid(tmp_path, rows, header=header), timezone=TZ)
    assert imported.frame["exit_reason"].tolist() == ["Stop loss"]


def test_a_grid_that_is_not_the_executions_grid_is_refused_by_name(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("Time,Category,Message,\r\n10/08/2026 6:00:31 PM,Default,Cancel all,\r\n")
    with pytest.raises(TradeImportError, match="not an NT8 executions grid"):
        trade_import.read_executions(path, timezone=TZ)


def test_the_direction_column_is_cross_checked_against_the_position_walk(tmp_path):
    rows = [row.replace(",Entry,4 S,Entry,", ",Exit,4 S,Entry,") for row in SAMPLE]
    with pytest.raises(TradeImportError, match="disagrees with the position walk"):
        trade_import.read_executions(grid(tmp_path, rows, header=FULL_HEADER), timezone=TZ)


# -- refusals -----------------------------------------------------------------


def test_an_unparseable_position_names_the_offending_value(tmp_path):
    rows = [fill("06/08/2026 1:00:00 PM", "Sell 1", "100.00", "4 X")]
    with pytest.raises(TradeImportError, match="cannot parse Position '4 X'"):
        trade_import.read_executions(grid(tmp_path, rows), timezone=TZ)


def test_a_missing_position_is_refused_rather_than_walked_around(tmp_path):
    rows = ["MNQ 09-26,Sell,1,100.00,06/08/2026 1:00:00 PM,,Entry,"]
    with pytest.raises(TradeImportError, match="only trade boundary"):
        trade_import.read_executions(grid(tmp_path, rows), timezone=TZ)


def test_an_unknown_action_is_refused(tmp_path):
    rows = [fill("06/08/2026 1:00:00 PM", "SellShort 1", "100.00", "1 S")]
    with pytest.raises(TradeImportError, match="unknown Action"):
        trade_import.read_executions(grid(tmp_path, rows), timezone=TZ)


def test_a_non_positive_quantity_is_refused(tmp_path):
    rows = [fill("06/08/2026 1:00:00 PM", "Sell 0", "100.00", "-")]
    with pytest.raises(TradeImportError, match="positive Quantity"):
        trade_import.read_executions(grid(tmp_path, rows), timezone=TZ)


def test_an_empty_cache_file_is_no_coverage_rather_than_a_crash(tmp_path):
    cache = tmp_path / "cache"
    path = ingest.contract_cache_path(ContractId.parse("MNQ 09-26"), cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = pd.DatetimeIndex([], tz="UTC", name="ts_utc")
    pd.DataFrame({"close": pd.Series(dtype="float64")}, index=index).to_parquet(path)

    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=cache,
    )
    assert imported.coverage.share == 0.0
    assert [c.cached for c in imported.coverage.contracts] == [False]


def test_the_summary_states_the_legs_the_coverage_and_what_was_dropped(tmp_path):
    cache = tmp_path / "cache"
    cache_bars(cache, "MNQ 09-26", "2026-08-01 00:00", "2026-08-31 00:00")
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
        cache_dir=cache,
    )
    summary = str(imported)
    assert "7 legs" in summary
    assert "2/2 trades reviewable (100.0%)" in summary
    assert "MNQ 09-26" in summary
    assert "2026-08-01 00:00:00+00:00 .. 2026-08-31 00:00:00+00:00" in summary
    assert "0 leading and 0 trailing fills dropped" in summary


def test_the_timezone_the_fills_were_read_under_is_recorded_on_every_row(tmp_path):
    """No timestamp can be re-derived without it, and one table can hold two machines' rows."""
    imported = trade_import.import_executions(
        grid(tmp_path, SAMPLE, header=FULL_HEADER),
        timezone=TZ,
    )
    assert set(imported.frame["timezone"]) == {TZ}
    assert imported.frame["timezone"].dtype == "string"
