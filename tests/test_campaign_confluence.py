"""EmaCrossover's confluence count from conditions it does not read, against a matched null.

``docs/findings/m59-confluence-not-read-preregistration.md``.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, conditions, context, randomentry, splice, stats, trades
from nqbt.instruments import MNQ
from nqbt.sim.types import EmaCrossoverParams
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_confluence
from tools.campaign_confluence import (
    BAND_PERIOD,
    CONDITIONS,
    KEYS,
    RANGE_KEY,
    SIDES,
    Favours,
    by_count,
    condition_shares,
    context_spec,
    costed,
    favouring,
    held,
    measure,
    null_by_count,
    placed,
)
from tools.campaign_sweep import COMMISSION, SLIPPAGE_TICKS

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.arrays import FloatArray

BARS = 20_000

PARAMS = costed("MNQ")


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(BARS, seed=5)


def prepared(bars: pd.DataFrame, params: EmaCrossoverParams = PARAMS) -> context.Dataset:
    return context.prepare(bars, context_spec(params), bar_minutes=1, price_basis=context.PriceBasis.RAW)


@pytest.fixture(scope="module")
def data(bars: pd.DataFrame) -> context.Dataset:
    return prepared(bars)


@pytest.fixture(scope="module")
def legs(data: context.Dataset) -> trades.LegMatrix:
    return archetypes.EMACROSSOVER.legs(data, PARAMS, MNQ)


def leg_rows(entry_bars: list[int], directions: list[float]) -> FloatArray:
    """Build leg rows carrying only an entry bar and a direction, which is all :func:`held` reads."""
    rows = np.zeros((len(entry_bars), trades.N_COLUMNS))
    rows[:, trades.C_ENTRY_BAR] = entry_bars
    rows[:, trades.C_DIRECTION] = directions

    return rows


# -- the parameters and the dataset -------------------------------------------------------------


def test_the_archetype_runs_at_its_defaults_with_the_roots_real_costs() -> None:
    for root in ("MNQ", "NQ"):
        params = costed(root)
        assert params.commission_per_contract == COMMISSION[root]
        assert params.slippage_ticks == SLIPPAGE_TICKS
        assert dataclasses.replace(params, commission_per_contract=0.0, slippage_ticks=0.0) == (
            EmaCrossoverParams(commission_per_contract=0.0, slippage_ticks=0.0)
        )


def test_the_spec_builds_what_the_archetype_reads_and_what_the_conditions_read() -> None:
    spec = context_spec(PARAMS)
    sweepable = archetypes.EMACROSSOVER.sweepable
    own = archetypes.EMACROSSOVER.context_for({name: [getattr(PARAMS, name)] for name in sweepable})

    assert set(own.ma_keys) <= set(spec.ma_keys)
    assert spec.needs_vwap
    assert BAND_PERIOD in spec.band_periods
    assert RANGE_KEY in spec.range_keys


# -- the five conditions ------------------------------------------------------------------------


def test_each_condition_is_its_own_definition_on_each_side(data: context.Dataset) -> None:
    favours = favouring(data)
    stretch = data.band_stretch(BAND_PERIOD)
    session = data.range_session_id()
    armed = data.range_armed(RANGE_KEY)
    no_bar_before = np.array([False])
    expected_long = [
        data.vwap_gate(above=True),
        data.close > data.open,
        np.concatenate([no_bar_before, data.high[1:] > data.high[:-1]]),
        stretch > 0.0,
        armed & (data.close > data.range_high(RANGE_KEY)[session]),
    ]
    expected_short = [
        data.vwap_gate(above=False),
        data.close < data.open,
        np.concatenate([no_bar_before, data.low[1:] < data.low[:-1]]),
        stretch < 0.0,
        armed & (data.close < data.range_low(RANGE_KEY)[session]),
    ]

    assert favours.long.shape == favours.short.shape == (len(CONDITIONS), len(data))
    for row, name in enumerate(CONDITIONS):
        assert np.array_equal(favours.long[row], expected_long[row]), name
        assert np.array_equal(favours.short[row], expected_short[row]), name
        assert favours.long[row].any(), name
        assert favours.short[row].any(), name


def test_the_midline_is_the_close_against_a_twenty_bar_average(data: context.Dataset) -> None:
    """Pinned against the close and the bars' own average, not the band's stretch."""
    favours = favouring(data)
    midline = CONDITIONS.index("midline")
    basis = data.band_basis(BAND_PERIOD)
    average = pd.Series(data.close).rolling(BAND_PERIOD).mean().to_numpy()

    assert BAND_PERIOD == 20
    assert np.allclose(basis[BAND_PERIOD - 1 :], average[BAND_PERIOD - 1 :])
    assert np.array_equal(favours.long[midline], data.close > basis)
    assert np.array_equal(favours.short[midline], data.close < basis)


def test_a_close_on_the_vwap_favours_both_sides_and_every_bar_favours_one(data: context.Dataset) -> None:
    """The side filters' rule: at or above for a long, at or below for a short."""
    favours = favouring(data)
    vwap = CONDITIONS.index("vwap")
    on_it = data.close == data.vwap_values()

    assert (favours.long[vwap] | favours.short[vwap]).all()
    assert np.array_equal(favours.long[vwap] & favours.short[vwap], on_it)


@pytest.mark.parametrize("name", ["body", "midline", "cash_range"])
def test_a_strict_condition_never_favours_both_sides_of_one_bar(data: context.Dataset, name: str) -> None:
    """A doji, a close on the midline and a bar inside the range each favour neither side."""
    favours = favouring(data)
    row = CONDITIONS.index(name)

    assert not (favours.long[row] & favours.short[row]).any()


def test_a_bar_before_its_cash_range_is_complete_favours_neither_side_on_it(data: context.Dataset) -> None:
    favours = favouring(data)
    unarmed = ~data.range_armed(RANGE_KEY)
    cash_range = CONDITIONS.index("cash_range")

    assert unarmed.any()
    assert not (favours.long[cash_range] | favours.short[cash_range])[unarmed].any()


def test_the_conditions_do_not_read_the_archetypes_averages(
    bars: pd.DataFrame, data: context.Dataset
) -> None:
    """The whole point of the set: other averages leave every condition where it was."""
    other = prepared(bars, dataclasses.replace(PARAMS, fast_period=5, slow_period=50))
    mine, theirs = favouring(data), favouring(other)

    assert np.array_equal(mine.long, theirs.long)
    assert np.array_equal(mine.short, theirs.short)


# -- reading them at the signal bar -------------------------------------------------------------


def test_a_leg_reads_its_own_sides_conditions_at_the_bar_before_its_fill() -> None:
    long_side = np.array([[True, False, False], [False, True, False]])
    short_side = np.array([[False, False, True], [True, True, False]])
    rows = leg_rows([1, 2, 3, 1], [trades.LONG, trades.LONG, trades.SHORT, trades.SHORT])

    got = held(rows, Favours(long_side, short_side))

    assert got.tolist() == [[True, False, True, False], [False, True, False, True]]


def test_a_leg_filled_on_the_first_bar_is_refused() -> None:
    favours = Favours(np.ones((1, 3), dtype=np.bool_), np.ones((1, 3), dtype=np.bool_))

    with pytest.raises(ValueError, match="no signal bar"):
        held(leg_rows([0], [trades.LONG]), favours)


def test_every_entry_fills_one_bar_after_its_signal(data: context.Dataset, legs: trades.LegMatrix) -> None:
    """What :func:`held` assumes of EmaCrossover: each fill's previous bar carries its signal."""
    signal = archetypes.EMACROSSOVER.signal(data, PARAMS)
    entry_bar = legs.matrix[: legs.count, trades.C_ENTRY_BAR].astype(np.int64)

    assert legs.count > 0
    assert signal[entry_bar - 1].all()


# -- the count table ----------------------------------------------------------------------------


def test_the_counts_partition_each_sides_trades(data: context.Dataset, legs: trades.LegMatrix) -> None:
    table = by_count(legs, favouring(data), data.day_codes)
    total = stats.summarise_legs(legs, data.day_codes).trades
    per_side = table.groupby("side")["trades"].sum()

    assert set(table["side"]) == set(SIDES)
    assert sorted(set(table["confluences"])) == list(range(len(CONDITIONS) + 1))
    assert per_side["both"] == total
    assert per_side["long"] + per_side["short"] == total
    both = table[table["side"] == "both"].set_index("confluences")["trades"]
    long_ = table[table["side"] == "long"].set_index("confluences")["trades"]
    short = table[table["side"] == "short"].set_index("confluences")["trades"]
    assert both.equals(long_ + short)


def test_a_rows_rates_are_the_summary_of_exactly_its_trades(
    data: context.Dataset, legs: trades.LegMatrix
) -> None:
    favours = favouring(data)
    rows = legs.matrix[: legs.count]
    counts = conditions.count_true(held(rows, favours))
    table = by_count(legs, favours, data.day_codes).set_index(KEYS)
    busiest = int(np.bincount(counts).argmax())
    kept = rows[(counts == busiest) & (rows[:, trades.C_DIRECTION] == trades.LONG)]
    expected = stats.summarise_legs(trades.LegMatrix(kept, len(kept)), data.day_codes)

    assert table.loc[("long", busiest), "trades"] == expected.trades
    assert table.loc[("long", busiest), "profit_factor"] == expected.profit_factor
    assert table.loc[("long", busiest), "win_rate"] == expected.win_rate


def test_a_count_no_trade_reached_has_no_rate() -> None:
    favours = Favours(
        np.zeros((len(CONDITIONS), 4), dtype=np.bool_), np.zeros((len(CONDITIONS), 4), dtype=np.bool_)
    )
    empty = trades.LegMatrix(np.zeros((0, trades.N_COLUMNS)), 0)

    table = by_count(empty, favours, np.zeros(4, dtype=np.int32))

    assert (table["trades"] == 0).all()
    assert table["profit_factor"].isna().all()
    assert table["win_rate"].isna().all()


def test_each_conditions_share_is_read_once_per_trade(data: context.Dataset, legs: trades.LegMatrix) -> None:
    favours = favouring(data)
    shares = condition_shares(legs, favours).set_index("side")
    rows = legs.matrix[: legs.count]
    first = rows[rows[:, trades.C_LEG] == 1]
    on_long = first[:, trades.C_DIRECTION] == trades.LONG

    assert shares.loc["both", "trades"] == len(first)
    assert shares.loc["long", "trades"] == int(on_long.sum())
    for row, name in enumerate(CONDITIONS):
        assert shares.loc["long", name] == pytest.approx(held(first, favours)[row, on_long].mean())
        assert shares[name].between(0.0, 1.0).all()


# -- the null -----------------------------------------------------------------------------------


def test_the_null_draws_what_randomentry_draws_at_the_same_seed(data: context.Dataset) -> None:
    """Each draw takes the trades `campaign_null.py`'s draw at that seed takes."""
    null = null_by_count(data, PARAMS, MNQ, favouring(data), iterations=3, seed=7)
    theirs = randomentry.null_summaries(data, PARAMS, archetypes.EMACROSSOVER, MNQ, iterations=3, seed=7)
    mine = null[null["side"] == "both"].groupby("draw")["trades"].sum()

    assert mine.tolist() == theirs["trades"].tolist()


def test_the_null_is_reproducible_from_its_seed(data: context.Dataset) -> None:
    favours = favouring(data)
    first = null_by_count(data, PARAMS, MNQ, favours, iterations=3, seed=7)
    again = null_by_count(data, PARAMS, MNQ, favours, iterations=3, seed=7)
    other = null_by_count(data, PARAMS, MNQ, favours, iterations=3, seed=8)

    pd.testing.assert_frame_equal(first, again)
    assert not first["trades"].equals(other["trades"])
    assert sorted(set(first["draw"])) == [0, 1, 2]


def test_a_null_needs_at_least_one_draw(data: context.Dataset) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        null_by_count(data, PARAMS, MNQ, favouring(data), iterations=0, seed=0)


def null_rows(profit_factors: list[float], trades_taken: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "side": "both",
            "confluences": 3,
            "trades": trades_taken,
            "profit_factor": profit_factors,
            "draw": range(len(profit_factors)),
        },
    )


def observed_row(profit_factor: float) -> pd.DataFrame:
    return pd.DataFrame(
        [{"side": "both", "confluences": 3, "trades": 40, "win_rate": 0.5, "profit_factor": profit_factor}]
    )


def test_the_excess_is_the_profit_factor_less_the_null_median() -> None:
    out = placed(observed_row(1.5), null_rows([0.8, 1.0, 1.2], [30, 31, 32])).iloc[0]

    assert out["null_profit_factor"] == pytest.approx(1.0)
    assert out["excess"] == pytest.approx(0.5)
    assert out["null_draws"] == 3
    assert out["null_trades"] == pytest.approx(31)
    assert out["null_p05"] == pytest.approx(0.8)
    assert out["null_p95"] == pytest.approx(1.2)


def test_a_draw_with_no_loser_places_a_row_and_one_with_no_trade_does_not() -> None:
    """Dropping the infinite draws would pull a sparse count's null down and its excess up."""
    out = placed(observed_row(1.5), null_rows([0.8, 1.0, np.inf, np.nan], [30, 32, 2, 0])).iloc[0]

    assert out["null_draws"] == 3
    assert out["null_profit_factor"] == pytest.approx(1.0)
    assert out["null_p95"] == np.inf
    assert out["null_trades"] == pytest.approx(16)


def test_a_row_with_too_few_draws_that_traded_there_has_no_null() -> None:
    out = placed(observed_row(1.5), null_rows([1.0, np.nan, np.nan], [30, 0, 0])).iloc[0]

    assert out["null_draws"] == 1
    assert np.isnan(out["null_profit_factor"])
    assert np.isnan(out["excess"])


# -- end to end ---------------------------------------------------------------------------------


def test_a_window_returns_every_side_and_count_against_its_null(bars: pd.DataFrame) -> None:
    counted, shares = measure(bars, "MNQ", 1, iterations=3, seed=0)

    assert len(counted) == len(SIDES) * (len(CONDITIONS) + 1)
    assert {"null_profit_factor", "null_p05", "null_p95", "null_trades", "excess"} <= set(counted.columns)
    assert (counted["null_draws"] <= 3).all()
    assert list(shares["side"]) == list(SIDES)


def test_main_writes_every_window_it_was_asked_for(
    bars: pd.DataFrame, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(splice, "load_continuous", lambda _root: bars)
    out = tmp_path / "counts.parquet"

    status = campaign_confluence.main(
        [
            "campaign_confluence.py",
            "--roots",
            "MNQ",
            "--resolution",
            "1",
            "--iterations",
            "2",
            "--out",
            str(out),
        ],
    )

    written = pd.read_parquet(out)
    shares = pd.read_parquet(tmp_path / "counts-shares.parquet")
    assert status == 0
    assert set(written["window"]) == set(shares["window"]) == {"full", "selection", "holdout"}
    assert set(written["root"]) == set(shares["root"]) == {"MNQ"}
    assert len(written) == 3 * len(SIDES) * (len(CONDITIONS) + 1)
    assert len(shares) == 3 * len(SIDES)
    assert set(CONDITIONS) <= set(shares.columns)


def test_main_refuses_a_bar_size_the_campaign_does_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(splice, "load_continuous", lambda _root: pytest.fail("loaded an archive"))

    with pytest.raises(SystemExit):
        campaign_confluence.main(["campaign_confluence.py", "--resolution", "7"])
