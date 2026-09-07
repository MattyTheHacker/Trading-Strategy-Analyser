"""The second arm of a shortlist: what its profit factor becomes without the assumption.

Two halves, and they need different machinery. The reporting half is pure and reads a table.
The measuring half has to run the simulation twice on the same bars, because what it claims is
a relation between two runs -- that the first reproduces the stored figure and the second is
never the better of the two -- and no stub can establish either.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, disambiguate, resample, results, sessions, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.bracket import AMBIGUITY_NEAREST_TO_OPEN, AMBIGUITY_WORST_CASE
from nqbt.sim.types import InsideBarParams
from tools import campaign_ambiguity
from tools.campaign_ambiguity import (
    BREAKEVEN,
    RANKED_POLICY,
    SECOND_ARM,
    SPREAD,
    SURVIVES,
    WORST,
    measure,
    measure_row,
    survival,
)
from tools.campaign_report import SHARES

ROOT = "MNQ"
STRATEGY = "InsideBar"


def measured(**columns: object) -> pd.DataFrame:
    """A table shaped like :func:`~tools.campaign_ambiguity.measure`'s output."""
    base = {
        "label": ["a", "b", "c"],
        "stratum": "unfiltered",
        "resolution": 5,
        "trades": [100, 200, 300],
        "profit_factor": [1.2, 1.4, 2.8],
        WORST: [1.1, 0.9, 0.4],
        SPREAD: [0.1, 0.5, 2.4],
        SURVIVES: [True, False, False],
        "ambiguous_share": [0.01, 0.05, 0.35],
        "session_close_share": 0.1,
    }

    return pd.DataFrame({**base, **columns})


# -- which policy is which -------------------------------------------------------------------


def test_the_ranked_arm_is_nt8s_rule_and_the_second_arm_is_not() -> None:
    """The prime directive governs what the shortlist claims, so the arm the stored rows were
    ranked under has to be the one reproducing NT8 -- ``docs/roadmap.md`` §M28.3."""
    assert RANKED_POLICY == AMBIGUITY_NEAREST_TO_OPEN
    assert SECOND_ARM == AMBIGUITY_WORST_CASE
    assert RANKED_POLICY != SECOND_ARM


# -- reading the spread ----------------------------------------------------------------------


def test_the_survival_line_counts_the_rows_that_keep_an_edge_without_the_assumption() -> None:
    lines = survival(measured())
    assert any(f"1 of 3 keep a profit factor above {BREAKEVEN:.2f}" in line for line in lines)


def test_the_widest_spread_is_named_rather_than_only_counted() -> None:
    """The §M28.2 shape is a shortlist whose least attributable row is also its best one, and
    only naming the row makes that visible."""
    lines = survival(measured())
    assert any("widest spread" in line and "c" in line for line in lines)


def test_the_widest_spread_is_the_largest_rather_than_the_last() -> None:
    lines = survival(measured(label=["a", "b", "c"], **{SPREAD: [2.4, 0.5, 0.1]}))
    assert any("widest spread" in line and line.strip().endswith("a") for line in lines)


def test_the_statement_is_reported_beside_the_count() -> None:
    """It is stated as a sentence rather than as a threshold on a share, the way
    ``MIN_DRAW_FREEDOM`` and ``MIN_DONOR_SESSIONS`` are."""
    assert survival(measured())[0].strip() == campaign_ambiguity.STATEMENT


def test_an_empty_table_says_so_instead_of_raising() -> None:
    assert survival(pd.DataFrame()) == ["  (nothing was measured)"]


# -- the two runs ----------------------------------------------------------------------------


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


def grid() -> sweep.Grid:
    """Two InsideBar combinations, one of which resolves bars by assumption and one of which
    does not.

    A quarter-ATR stop against a quarter-ATR target puts both bracket levels inside one
    5-minute bar often enough to measure -- the geometry §M28.2 found on the retest, reached
    here through the bracket rather than through the entry. The pair is the point: the tool has
    to report a band on one configuration and none on its neighbour.
    """
    return sweep.Grid.of(
        InsideBarParams(slow_sma_period=50, bars_required_to_trade=60, tp_multiplier=0.25),
        atr_multiplier=[0.25, 0.5],
    )


def stored(db, bars: pd.DataFrame, minutes: int, window: str) -> int:
    """Sweep one grid at one point and store it the way ``campaign_sweep.run_point`` does."""
    frame = resample.resample(bars, minutes)
    table, _ = sweep.sweep(frame, grid(), get_instrument(ROOT))
    table.insert(0, "variant", "bracket")
    table.insert(1, "stratum", "unfiltered")
    table.insert(2, "window", window)
    table["combo_id"] = range(len(table))

    return results.save_sweep(
        table,
        root=ROOT,
        instrument=ROOT,
        bars=frame,
        axes=grid().axis_values(),
        strategy=STRATEGY,
        resolution=minutes,
        db_path=db,
    )


def combos(db) -> pd.DataFrame:
    return results.query("SELECT * FROM combos ORDER BY sweep_id, combo_id", db)


def spread_table(tmp_path, monkeypatch, bars: pd.DataFrame, points) -> pd.DataFrame:
    """Store every ``(window, resolution)`` point, then measure the whole thing."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    for window, minutes in points:
        stored(db, campaign_ambiguity.source(bars, window), minutes, window)

    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)
    block = combos(db)
    assert block["trades"].sum() > 0, "fixture produced no trades; the test proves nothing"

    return measure(block, archetypes.INSIDEBAR, ROOT)


def test_the_first_arm_reproduces_the_stored_profit_factor(tmp_path, monkeypatch) -> None:
    """The spread is only the width of a band if one end of it is the figure that was ranked."""
    bars = synthetic_bars()
    table = spread_table(tmp_path, monkeypatch, bars, [("full", 5)])
    block = combos(tmp_path / f"{STRATEGY}.duckdb")

    assert list(table["profit_factor"]) == pytest.approx(list(block["profit_factor"]))
    assert list(table["trades"]) == list(block["trades"])


def test_the_worst_case_is_never_the_better_of_the_two(tmp_path, monkeypatch) -> None:
    """Every ambiguous bar it resolves is one the ranked arm may have given to the target, so
    the second arm can only move gross profit down and gross loss up. A spread that came out
    negative would mean the two arms are not the same configuration."""
    table = spread_table(tmp_path, monkeypatch, synthetic_bars(), [("full", 5)])

    assert (table[WORST] <= table["profit_factor"] + 1e-12).all()
    assert (table[SPREAD] >= -1e-12).all()
    assert (table[SPREAD] > 0.0).any(), "no configuration resolved a bar by assumption"


def test_the_share_and_the_spread_are_not_the_same_measurement(tmp_path, monkeypatch) -> None:
    """The reason a ceiling on ``ambiguous_share`` is the wrong instrument: the share counts
    how often the assumption was invoked, the spread says how much the answer depends on it.
    The fixture holds one configuration with a band and one without."""
    table = spread_table(tmp_path, monkeypatch, synthetic_bars(), [("full", 5)])

    assert set(table[SPREAD] > 0.0) == {True, False}
    assert set(table["ambiguous_share"] > 0.0) == {True, False}


def test_a_row_whose_rerun_does_not_reproduce_it_is_refused(tmp_path, monkeypatch) -> None:
    """A spread filed against a summary it does not match would attribute a band to a
    configuration that did not produce it -- ``tools/campaign_shortlist.verify``."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)
    block = combos(db)
    block.loc[:, "trades"] = block["trades"] + 1

    with pytest.raises(RuntimeError, match="trades, not the"):
        measure(block, archetypes.INSIDEBAR, ROOT)


def test_every_shortlisted_row_is_measured_on_the_bars_its_own_window_names(
    tmp_path,
    monkeypatch,
) -> None:
    """One shortlist spans several sweep points, and a row measured on the wrong window would
    fail ``verify`` rather than report a spread -- so this passing is the grouping."""
    bars = synthetic_bars()
    points = [("selection", 5), ("holdout", 5), ("full", 10)]
    table = spread_table(tmp_path, monkeypatch, bars, points)

    assert len(table) == len(combos(tmp_path / f"{STRATEGY}.duckdb"))
    assert set(table["window"]) == {"selection", "holdout", "full"}
    assert set(table["resolution"]) == {5, 10}


def test_the_shares_travel_with_the_spread(tmp_path, monkeypatch) -> None:
    """The spread says how much the answer depends on the assumption and the share says how
    often it was invoked; §M28.2 needs both columns in one table to be read at all."""
    table = spread_table(tmp_path, monkeypatch, synthetic_bars(), [("full", 5)])

    assert set(SHARES) <= set(table.columns)


def test_the_second_arm_is_forced_rather_than_taken_from_the_stored_row(
    tmp_path,
    monkeypatch,
) -> None:
    """A row stored under the worst case would otherwise report a spread of zero between two
    arms neither of which is NT8's; forcing the policy makes it fail ``verify`` instead."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)

    seen: list[int] = []
    original = campaign_ambiguity.sweep.run_combination

    def record(data, params, *args, **kwargs):
        seen.append(params.ambiguity_policy)

        return original(data, params, *args, **kwargs)

    monkeypatch.setattr(campaign_ambiguity.sweep, "run_combination", record)
    measure(combos(db), archetypes.INSIDEBAR, ROOT)

    assert set(seen) == {RANKED_POLICY, SECOND_ARM}


def test_a_measured_row_carries_the_axes_that_vary_across_the_shortlist(
    tmp_path,
    monkeypatch,
) -> None:
    """The §M28.2 finding was that every one of the top twenty carried one parameter value, and
    a table naming only the sweep identifiers cannot show that."""
    table = spread_table(tmp_path, monkeypatch, synthetic_bars(), [("full", 5)])

    assert set(table["label"]) == {"atr_multiplier=0.25", "atr_multiplier=0.5"}


def test_one_row_is_measured_at_a_time_rather_than_pooled(tmp_path, monkeypatch) -> None:
    """A pooled spread would average an unattributable configuration into an attributable one,
    which is the reading §M28.2 says a shortlist cannot make."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)
    block = combos(db)

    table = measure(block, archetypes.INSIDEBAR, ROOT)
    assert len(table) == len(block)


def test_a_single_row_is_measured_without_a_varying_axis(tmp_path, monkeypatch) -> None:
    """``--top 1`` leaves nothing varying, and the label falls back to the stored identity."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)
    block = combos(db).head(1)

    table = measure(block, archetypes.INSIDEBAR, ROOT)
    assert len(table) == 1
    assert table["label"].iloc[0].startswith("sweep ")


def test_a_measured_row_reports_the_survival_of_its_own_second_arm(
    tmp_path,
    monkeypatch,
) -> None:
    """``survives`` is read off the worst case, never off the ranked figure."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)

    table = measure(combos(db), archetypes.INSIDEBAR, ROOT)
    assert list(table[SURVIVES]) == list(table[WORST] > BREAKEVEN)


def test_measure_row_needs_no_database_to_report_a_spread(tmp_path, monkeypatch) -> None:
    """The tool's unit is one row against one prepared dataset, and the table is a loop over
    it -- so a caller with a dataset in hand can ask for a single configuration's band."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    row = combos(db).iloc[0]

    frame = resample.resample(bars, 5)
    params = campaign_ambiguity.rebuild(row, archetypes.INSIDEBAR)
    spec = sweep.Grid(base=params, archetype=archetypes.INSIDEBAR).required_context()
    data = campaign_ambiguity.context.prepare(frame, spec, bar_minutes=5)

    result = measure_row(row, data, archetypes.INSIDEBAR, ROOT, "one")
    assert result["profit_factor"] == pytest.approx(float(row["profit_factor"]))
    assert result[SPREAD] == pytest.approx(result["profit_factor"] - result[WORST])


# -- the wiring ------------------------------------------------------------------------------


def main_over(monkeypatch: pytest.MonkeyPatch, table: pd.DataFrame) -> tuple[int, list[object]]:
    """Run ``main`` with the ranking and the measuring both stubbed, and return what it saw."""
    rows = pd.DataFrame({"window": ["full"], "resolution": [5]})
    seen: list[object] = []

    def remember(given: pd.DataFrame, *_args: object) -> pd.DataFrame:
        seen.append(given)

        return table

    monkeypatch.setattr(campaign_ambiguity, "shortlist", lambda *_args: rows)
    monkeypatch.setattr(campaign_ambiguity, "measure", remember)
    monkeypatch.setattr(campaign_ambiguity, "settle", lambda *_args: (pd.DataFrame(), pd.DataFrame()))
    status = campaign_ambiguity.main(["campaign_ambiguity.py", "--strategy", STRATEGY])

    return status, [rows, *seen]


def test_main_re_runs_exactly_the_rows_the_shortlist_ranked(monkeypatch) -> None:
    """The shortlist stays the selection; this tool only adds an arm to each row it picked."""
    status, (ranked, measured_over) = main_over(monkeypatch, measured())

    assert status == 0
    assert measured_over is ranked


def test_main_survives_a_shortlist_that_measured_nothing(monkeypatch) -> None:
    """An empty table is a run with nothing to say, not a crash in the reporting half."""
    status, _ = main_over(monkeypatch, pd.DataFrame())

    assert status == 0


def test_main_can_report_the_band_without_reading_any_minute_bars(monkeypatch) -> None:
    """``--no-settle`` is the cheap path, and it must not reach the third step at all."""
    rows = pd.DataFrame({"window": ["full"], "resolution": [5]})
    monkeypatch.setattr(campaign_ambiguity, "shortlist", lambda *_args: rows)
    monkeypatch.setattr(campaign_ambiguity, "measure", lambda *_args: measured())
    monkeypatch.setattr(
        campaign_ambiguity,
        "settle",
        lambda *_a: (_ for _ in ()).throw(AssertionError("settled under --no-settle")),
    )

    assert campaign_ambiguity.main(["campaign_ambiguity.py", "--strategy", STRATEGY, "--no-settle"]) == 0


# -- settling the band against the minute bars -----------------------------------------------


def settled_over(tmp_path, monkeypatch, bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Store the fixture's two configurations, then run the third step over them."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)

    return campaign_ambiguity.settle(combos(db), archetypes.INSIDEBAR, ROOT)


def test_only_the_rows_over_the_threshold_are_settled(tmp_path, monkeypatch) -> None:
    """The user-facing contract: an extra step on a finished result, run only where the
    assumption is common enough to have decided anything -- ``disambiguate.MIN_AMBIGUOUS_SHARE``."""
    bars = synthetic_bars()
    table = spread_table(tmp_path / "spread", monkeypatch, bars, [("full", 5)])
    over = table[table["ambiguous_share"] >= disambiguate.MIN_AMBIGUOUS_SHARE]
    assert len(over) == 1, "the fixture must straddle the threshold or this proves nothing"

    settled, _ = settled_over(tmp_path, monkeypatch, bars)
    assert len(settled) == 1
    assert settled["ambiguous_share"].iloc[0] >= disambiguate.MIN_AMBIGUOUS_SHARE


def test_a_shortlist_with_no_ambiguity_settles_nothing_rather_than_raising(tmp_path, monkeypatch) -> None:
    """Most shortlists are this case, and it must be a quiet skip rather than an error."""
    db = tmp_path / f"{STRATEGY}.duckdb"
    bars = synthetic_bars()
    stored(db, bars, 5, "full")
    monkeypatch.setattr(campaign_ambiguity.splice, "load_continuous", lambda _: bars)
    block = combos(db)
    block.loc[:, "ambiguous_share"] = 0.0

    settled, verdicts = campaign_ambiguity.settle(block, archetypes.INSIDEBAR, ROOT)
    assert settled.empty
    assert verdicts.empty


def test_a_settled_row_reports_the_resolved_result_beside_the_ranked_one(tmp_path, monkeypatch) -> None:
    """The point of the step: the profit factor with the assumption corrected where the minute
    bars can correct it, against the one that was ranked."""
    settled, _ = settled_over(tmp_path, monkeypatch, synthetic_bars())
    row = settled.iloc[0]

    assert row[campaign_ambiguity.MOVE] == pytest.approx(
        row[campaign_ambiguity.RESOLVED] - row["profit_factor"],
    )
    assert row["ambiguous_bars"] >= 1


def test_every_ambiguous_bar_of_a_settled_row_gets_a_verdict(tmp_path, monkeypatch) -> None:
    settled, verdicts = settled_over(tmp_path, monkeypatch, synthetic_bars())

    assert len(verdicts) == int(settled["ambiguous_bars"].sum())
    assert set(verdicts.columns) >= {"trade_id", "exit_bar", "assumed", "resolved", "agrees", "label"}


def test_the_printed_bars_are_the_ones_worth_looking_at() -> None:
    """A bar the assumption called right is evidence, not a finding; printing every one buries
    the handful that moved the result."""
    verdicts = pd.DataFrame(
        {
            "resolved": ["target_first", "stop_first", "still_ambiguous"],
            "agrees": pd.array([True, False, None], dtype="boolean"),
        },
    )
    shown = campaign_ambiguity.unsettled(verdicts)

    assert list(shown["resolved"]) == ["stop_first", "still_ambiguous"]
    assert campaign_ambiguity.unsettled(pd.DataFrame()).empty
