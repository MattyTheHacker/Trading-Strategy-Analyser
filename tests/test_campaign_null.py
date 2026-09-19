"""The matched null over a shortlist rather than one row.

The null draws themselves are pinned in ``tests/test_randomentry.py``; what is testable without
data is the part §M27.3 added -- that three rankings are reported side by side, that they are
allowed to disagree, and that a configuration the draw refused carries no verdict instead of a
missing one -- and the part [#320] added, that a stored row is refused unless the re-run is on
the bars it was swept on.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nqbt import randomentry, results
from tools import campaign_null, campaign_report
from tools.campaign_holdout import JOIN_KEYS
from tools.campaign_null import (
    RANKINGS,
    STATISTICS,
    family,
    label_of,
    measure_row,
    rankings,
    series_moved,
    stored_for,
    stored_rows,
    verify_bars,
    verify_observation,
)
from tools.campaign_report import NET_TO_DRAWDOWN


def measured(**columns: object) -> pd.DataFrame:
    """A table shaped like :func:`~tools.campaign_null.measure`'s output."""
    base = {
        "label": ["a", "b", "c"],
        "stratum": "unfiltered",
        "resolution": 10,
        NET_TO_DRAWDOWN: [1.0, 2.0, 3.0],
        "ranked_by": [3.0, 2.0, 1.0],
        "refused": None,
        "profit_factor": [1.0, 2.0, 3.0],
        "expectancy_excess": [1.0, 2.0, 3.0],
    }

    return pd.DataFrame({**base, **columns})


# -- which null a row was produced under -----------------------------------------------------


def refused_row(monkeypatch: pytest.MonkeyPatch, draw: str) -> dict[str, object]:
    """One ``measure_row`` result, with the simulation and the null both stubbed out.

    The identity half is what is under test, so neither a dataset nor a draw is needed --
    stubbing ``compare`` to refuse reaches it by the shortest path.
    """

    def refuse(*_args: object, **_kwargs: object) -> dict[str, object]:
        msg = "stubbed"
        raise randomentry.RandomEntryError(msg)

    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(campaign_null.randomentry, "compare", refuse)
    row = pd.Series({"stratum": "unfiltered", "resolution": 10, NET_TO_DRAWDOWN: 1.0, "trades": 5})

    return measure_row(row, object(), object(), "MNQ", "a", 2, 1, draw)


def test_a_measured_row_says_which_null_produced_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two arms ask different questions, so a table mixing them would be two nulls wearing
    one set of names -- ``docs/roadmap.md`` §M28.2."""
    over_bars = refused_row(monkeypatch, randomentry.OVER_BARS)
    over_levels = refused_row(monkeypatch, randomentry.OVER_LEVELS)

    assert over_bars["draw"] == randomentry.OVER_BARS
    assert over_levels["draw"] == randomentry.OVER_LEVELS


def test_the_draw_defaults_to_the_one_every_archetype_has(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding the second arm must not change what an unflagged run measures."""
    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(
        campaign_null.randomentry,
        "compare",
        lambda *_a, **kwargs: (_ for _ in ()).throw(AssertionError(kwargs["draw"])),
    )
    row = pd.Series({"stratum": "unfiltered", "resolution": 10, NET_TO_DRAWDOWN: 1.0, "trades": 5})

    with pytest.raises(AssertionError, match=randomentry.OVER_BARS):
        measure_row(row, object(), object(), "MNQ", "a", 2, 1)


# -- naming a configuration ------------------------------------------------------------------


def test_a_configuration_is_named_by_whatever_varies_across_the_shortlist() -> None:
    row = pd.Series({"tp_multiplier": 2.0, "atr_multiplier": 5.0, "sweep_id": 1, "combo_id": 7})
    assert label_of(row, ["tp_multiplier", "atr_multiplier"]) == "tp_multiplier=2.0 atr_multiplier=5.0"


def test_a_shortlist_with_no_varying_axis_falls_back_to_the_stored_identity() -> None:
    """``--top 1`` has nothing to vary, and an empty label would name every row the same."""
    row = pd.Series({"sweep_id": 3, "combo_id": 11})
    assert label_of(row, []) == "sweep 3 combo 11"


# -- the three rankings ----------------------------------------------------------------------


def test_the_three_rankings_are_the_ones_m27_3_asked_for() -> None:
    """Profit factor is reported to be disagreed with, not to be believed."""
    assert RANKINGS == ("profit_factor", "expectancy_excess", NET_TO_DRAWDOWN)


def test_agreement_is_reported_when_every_ranking_picks_the_same_row() -> None:
    lines = rankings(measured())
    assert lines[-1].endswith("agree")
    assert all("c" in line for line in lines[:-1])


def test_a_disagreement_is_reported_rather_than_a_winner() -> None:
    """The case the exercise exists for: a bracket that suits the bars raises the observed
    statistic and its own null together -- ``docs/findings/m26-elastic-band.md`` § "The method that does answer
    the question"."""
    table = measured(profit_factor=[3.0, 2.0, 1.0])
    lines = rankings(table)
    assert lines[-1].endswith("DISAGREE")
    assert "best by profit_factor" in lines[0] and lines[0].endswith("a")


def test_a_refused_configuration_is_not_ranked() -> None:
    """A gate that could not run is not a gate that passed, so the row carries no verdict and
    must not win an ordering -- ``docs/roadmap.md`` §M28.1."""
    table = measured(refused=[None, None, "no draw freedom"], profit_factor=[1.0, 2.0, np.nan])
    lines = rankings(table)
    assert all(line.endswith("b") for line in lines[: len(RANKINGS)]), "the refused row was ranked"
    assert lines[-1].endswith("agree")


def test_a_table_with_nothing_measured_says_so_instead_of_raising() -> None:
    table = measured(refused="no draw freedom")
    assert rankings(table) == ["  (nothing was measured)"]


def test_a_ranking_undefined_on_every_row_is_named_rather_than_skipped() -> None:
    """The whole point of leaving net-to-drawdown undefined is that it can be, so a run where
    no configuration had a drawdown must say the ranking is missing."""
    table = measured(**{NET_TO_DRAWDOWN: np.nan})
    lines = rankings(table)
    assert any("undefined on every row" in line for line in lines)
    assert lines[-1].endswith("agree"), "the two rankings that did run both picked c"


def test_an_undefined_ranking_does_not_count_as_a_disagreement() -> None:
    """It is a measurement that is missing, not an order that differs."""
    agreeing = rankings(measured(**{NET_TO_DRAWDOWN: np.nan}))
    disagreeing = rankings(measured(profit_factor=[3.0, 2.0, 1.0], **{NET_TO_DRAWDOWN: np.nan}))
    assert agreeing[-1].endswith("agree")
    assert disagreeing[-1].endswith("DISAGREE")


def test_every_ranking_is_reported_even_when_they_agree() -> None:
    """The two orders side by side are the output; printing only the winner hides the finding."""
    lines = rankings(measured())
    assert len(lines) == len(RANKINGS) + 1
    for statistic in RANKINGS:
        assert any(statistic in line for line in lines), statistic


def test_the_best_row_is_the_largest_rather_than_the_first() -> None:
    table = measured(profit_factor=[2.0, 3.0, 1.0])
    assert rankings(table)[0].endswith("b")


def test_a_refusal_column_of_all_nulls_ranks_every_row() -> None:
    """``measure`` writes ``None`` rather than omitting the column, so the filter has to treat
    a fully-unrefused table as fully rankable."""
    table = measured()
    assert table["refused"].isna().all()
    assert rankings(table)[-1].endswith("agree")


def test_the_ranking_window_and_the_test_window_are_separate_columns() -> None:
    """One row must not be two windows wearing one set of names: everything measured is the
    test window's, and the stored row's own figure is reported under its own name."""
    table = measured(**{NET_TO_DRAWDOWN: [9.0, 1.0, 1.0]}, ranked_by=[0.1, 0.2, 0.3])
    assert rankings(table)[2].endswith("a"), "the ranking read the test window's column"
    assert table["ranked_by"].iloc[0] == pytest.approx(0.1)


def test_net_to_drawdown_needs_the_two_statistics_it_is_built_from() -> None:
    """``measure_row`` derives it from the observation rather than the stored row, so both have
    to be asked of ``compare`` -- and they are nearly free, since it summarises once."""
    assert {"net_pnl", "max_drawdown"} <= set(STATISTICS)


# -- the family summary ----------------------------------------------------------------------


def family_rows(**columns: object) -> pd.DataFrame:
    """A table shaped like :func:`~tools.campaign_null.measure`'s output over two cells."""
    base = {
        "root": ["MNQ", "MNQ", "NQ", "NQ"],
        "stratum": "phase=MIDDAY",
        "refused": None,
        "trades": [100, 200, 300, 400],
        "profit_factor": [1.0, 1.2, 0.9, 1.1],
        "profit_factor_null": [0.9, 0.9, 1.0, 1.0],
        "profit_factor_excess": [0.1, 0.3, -0.1, 0.1],
        "profit_factor_p": [0.01, 0.20, 0.90, 0.04],
        NET_TO_DRAWDOWN: [0.5, 1.5, -0.5, 0.25],
    }

    return pd.DataFrame({**base, **columns})


def test_a_family_reports_one_row_per_root_and_stratum() -> None:
    """The cell is what a score was consistent across, so it is what a null has to be read
    per -- ``docs/roadmap.md`` §M28.16."""
    summary = family(family_rows())
    assert list(summary["root"]) == ["MNQ", "NQ"]
    assert campaign_null.CELL_KEYS == ["root", "stratum"]


def test_a_cell_is_summarised_as_a_range_rather_than_a_mean() -> None:
    """Ten configurations of one cell are overlapping runs over the same bars, so their spread
    is the honest summary."""
    summary = family(family_rows()).set_index("root")
    assert summary.loc["MNQ", "profit_factor_low"] == pytest.approx(1.0)
    assert summary.loc["MNQ", "profit_factor_high"] == pytest.approx(1.2)
    assert summary.loc["NQ", "excess_low"] == pytest.approx(-0.1)
    assert summary.loc["NQ", "net_to_drawdown_high"] == pytest.approx(0.25)


def test_beating_the_null_and_clearing_the_level_are_counted_separately() -> None:
    """A cell can beat its own null on every configuration and clear p on almost none, which is
    §M28.14's ElasticBand result and the reason both columns are reported."""
    summary = family(family_rows()).set_index("root")
    assert summary.loc["MNQ", "beat_null"] == 2
    assert summary.loc["MNQ", "p_under_05"] == 1
    assert summary.loc["NQ", "beat_null"] == 1
    assert summary.loc["NQ", "p_under_05"] == 1


def test_the_level_the_count_is_taken_against_is_named_rather_than_inlined() -> None:
    """It is counted rather than concluded from, so the number a reader corrects for is
    visible."""
    assert campaign_null.SIGNIFICANT == pytest.approx(0.05)


def test_a_wholly_refused_cell_carries_a_count_rather_than_a_verdict() -> None:
    """A gate that could not run is not one that passed -- the same reason
    :data:`~tools.campaign_null.NO_NULL_AVAILABLE` exists."""
    rows = family_rows(refused=[None, None, "dense", "dense"])
    summary = family(rows).set_index("root")
    assert summary.loc["NQ", "measured"] == 0
    assert summary.loc["NQ", "refused"] == 2
    assert pd.isna(summary.loc["NQ", "profit_factor_low"])


def test_a_partly_refused_cell_summarises_only_what_ran() -> None:
    """A row refused alongside rows that ran carries no verdict, so it must not reach the
    range either."""
    rows = family_rows(refused=[None, "dense", None, None])
    summary = family(rows).set_index("root")
    assert summary.loc["MNQ", "measured"] == 1
    assert summary.loc["MNQ", "refused"] == 1
    assert summary.loc["MNQ", "profit_factor_high"] == pytest.approx(1.0)


# -- the bars a stored row was swept on ------------------------------------------------------


FIRST_BAR = pd.Timestamp("2021-09-19 22:05:00")
LAST_BAR = pd.Timestamp("2024-09-17 14:56:00")
"""The ends of one stored sweep, naive as ``results.save_sweep`` writes them."""


def stored_frame(**columns: object) -> pd.DataFrame:
    """A frame shaped like :func:`~tools.campaign_null.stored_rows`' output, unindexed."""
    base = {
        "sweep_id": 1,
        "combo_id": [10, 11],
        "root": "MNQ",
        "resolution": 5,
        "variant": "bracket",
        "stratum": "unfiltered",
        "trades": [40, 50],
        "net_pnl": [1234.5, 900.0],
        "first_bar": FIRST_BAR,
        "last_bar": LAST_BAR,
    }

    return pd.DataFrame({**base, **columns})


def stubbed(monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """:func:`~tools.campaign_null.stored_rows` over a stubbed query."""
    stored = stored_frame() if frame is None else frame
    monkeypatch.setattr(campaign_null, "db_path", Path)
    monkeypatch.setattr(campaign_null.results, "query", lambda *_a, **_k: stored)

    return stored_rows("InsideBar", "MNQ", "holdout")


def assembled() -> pd.DataFrame:
    """The same frame without monkeypatching, for the tests that only read one row from it."""
    return stored_frame().set_index(JOIN_KEYS, drop=False)


def shortlisted(**columns: object) -> pd.Series:
    """One shortlist row, carrying the keys that identify it in another window."""
    base = {
        "sweep_id": 7,
        "combo_id": 10,
        "root": "MNQ",
        "resolution": 5,
        "variant": "bracket",
        "stratum": "unfiltered",
    }

    return pd.Series({**base, **columns})


def bars(first: object, last: object) -> pd.DataFrame:
    """A bar frame with only its two ends, stamped the way the archive is."""
    index = pd.DatetimeIndex([pd.Timestamp(first, tz="UTC"), pd.Timestamp(last, tz="UTC")])

    return pd.DataFrame({"close": [1.0, 2.0]}, index=index)


def test_a_stored_row_is_found_by_the_keys_that_pair_two_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ranking window and the test window are different sweeps, so the stored counterpart
    has to be found by configuration rather than by ``sweep_id``."""
    found = stored_for(stubbed(monkeypatch), shortlisted())
    assert found is not None
    assert int(found["trades"]) == 40
    assert found["first_bar"] == FIRST_BAR


def test_a_configuration_the_test_window_never_swept_has_no_counterpart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shortlist spanning two variant sets can reach it, and a check that could not run is
    not one that failed."""
    assert stored_for(stubbed(monkeypatch), shortlisted(combo_id=99)) is None


def test_another_roots_rows_are_not_a_counterpart(monkeypatch: pytest.MonkeyPatch) -> None:
    """NQ and MNQ hold the same ``combo_id`` at the same bar size, and their trade counts are
    equal while their money is ten times apart -- ``CLAUDE.md``, the tick-value rule."""
    stored = stubbed(monkeypatch, stored_frame(root=["NQ", "NQ"]))
    assert stored.empty
    assert stored_for(stored, shortlisted()) is None


def test_two_stored_rows_under_one_key_are_refused_rather_than_chosen_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tools/campaign_holdout.py`` pairs the windows one-to-one on the same keys, so an
    ambiguous database is a failure there too."""
    with pytest.raises(RuntimeError, match="more than one row under the same"):
        stubbed(monkeypatch, stored_frame(combo_id=[10, 10]))


def test_a_stored_row_carries_the_bar_range_of_its_own_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sweeps of one window can hold different ranges, so the range travels with the row
    rather than being read once for the whole run."""
    stored = stubbed(
        monkeypatch,
        stored_frame(sweep_id=[1, 2], first_bar=[FIRST_BAR, LAST_BAR]),
    )
    assert stored_for(stored, shortlisted())["first_bar"] == FIRST_BAR
    assert stored_for(stored, shortlisted(combo_id=11))["first_bar"] == LAST_BAR


def swept(db: Path, window: str, trades: list[int], bars_frame: pd.DataFrame) -> None:
    """One ``sweeps`` row and its combinations, stored the way ``campaign_sweep.run_point`` does."""
    table = pd.DataFrame(
        {
            "variant": "bracket",
            "stratum": "unfiltered",
            "window": window,
            "combo_id": range(len(trades)),
            "trades": trades,
            "net_pnl": [100.0 * n for n in trades],
            "profit_factor": 1.2,
            "max_drawdown": 50.0,
        },
    )
    results.save_sweep(
        table,
        root="MNQ",
        instrument="MNQ",
        bars=bars_frame,
        axes={},
        strategy="InsideBar",
        resolution=5,
        db_path=db,
    )


def test_a_stored_row_below_the_trade_floor_is_still_what_a_rerun_is_checked_against(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real round trip, because the claim is about the SQL. ``campaign_report.load`` drops
    every row under ``MIN_TRADES``, and a shortlist ranked on the selection window routinely
    lands under it in the holdout, so reading through that loader would be the check that never
    runs -- ``docs/findings/m36-ema-pullback-volume-recut.md`` § "Gate 3 -- 1 of 120, and it is
    in the wrong direction"."""
    db = tmp_path / "InsideBar.duckdb"
    index = pd.date_range("2024-01-02 00:00", periods=400, freq="5min", tz="UTC")
    frame = pd.DataFrame({"close": 1.0}, index=index)
    swept(db, "holdout", [4, 40], frame)
    swept(db, "selection", [900], frame)
    monkeypatch.setattr(campaign_null, "db_path", lambda _: db)
    monkeypatch.setattr(campaign_report, "db_path", lambda _: db)

    stored = stored_rows("InsideBar", "MNQ", "holdout")
    assert list(stored["trades"]) == [4, 40], "the other window's rows reached the check"
    assert set(campaign_report.load("InsideBar", ["holdout"])["combo_id"]) == {1}

    thin = stored_for(stored, shortlisted(combo_id=0))
    assert thin is not None
    assert int(thin["trades"]) == 4
    verify_bars(thin, frame, "a", "holdout")
    with pytest.raises(RuntimeError, match="swept on a different series"):
        verify_bars(thin, frame.iloc[:-1], "a", "holdout")


def test_bars_matching_the_stored_sweep_report_no_movement() -> None:
    """The stored stamps are naive UTC and a bar index is zoned, which is the comparison that
    would otherwise report every run as moved."""
    assert series_moved(stored_for(assembled(), shortlisted()), bars(FIRST_BAR, LAST_BAR)) == ""


def test_each_end_of_the_series_is_named_on_its_own() -> None:
    """Which end moved is the diagnosis: a later export extends the last bar, more history
    moves the first, and a re-split moves both."""
    reference = stored_for(assembled(), shortlisted())
    later = series_moved(reference, bars(FIRST_BAR, "2026-09-16 12:07"))
    earlier = series_moved(reference, bars("2019-01-02 00:00", LAST_BAR))
    both = series_moved(reference, bars("2019-01-02 00:00", "2026-09-16 12:07"))
    assert later.startswith("last bar was")
    assert "first bar" not in later
    assert earlier.startswith("first bar was")
    assert "last bar" not in earlier
    assert both.count("bar was") == 2


def test_a_rerun_on_a_series_that_has_moved_is_refused() -> None:
    """The archive was extended under every campaign stored before 2026-09-16, which moved the
    split -- ``docs/roadmap.md`` § "Standing traps"."""
    reference = stored_for(assembled(), shortlisted())
    with pytest.raises(RuntimeError, match="swept on a different series"):
        verify_bars(reference, bars(FIRST_BAR, "2026-09-16 12:07"), "a", "holdout")


def test_a_rerun_on_the_stored_series_is_not_refused() -> None:
    verify_bars(stored_for(assembled(), shortlisted()), bars(FIRST_BAR, LAST_BAR), "a", "holdout")


def test_an_unstored_configuration_is_warned_about_rather_than_refused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A check that could not run must not read as one that passed, so it is said out loud --
    the same distinction :data:`~tools.campaign_null.NO_NULL_AVAILABLE` draws."""
    with caplog.at_level("WARNING"):
        verify_bars(None, bars(FIRST_BAR, LAST_BAR), "a", "holdout")

    assert "unchecked" in caplog.text
    assert "holdout" in caplog.text


# -- the observation against the row the sweep stored ----------------------------------------


def null_result(statistic: str, observed: float, trades: int) -> randomentry.NullResult:
    """One :class:`~nqbt.randomentry.NullResult` with everything but the observation stubbed."""
    return randomentry.NullResult(
        statistic=statistic,
        observed=observed,
        null_median=0.0,
        null_p05=0.0,
        null_p95=0.0,
        percentile=50.0,
        p_value=0.5,
        verdict=randomentry.INDISTINGUISHABLE,
        iterations=2,
        observed_trades=trades,
        null_median_trades=float(trades),
        count_sensitive=False,
    )


def measured_row(monkeypatch: pytest.MonkeyPatch, trades: int, net_pnl: float) -> dict[str, object]:
    """One real :func:`~tools.campaign_null.measure_row` result, with only ``compare`` stubbed.

    Going through the producer rather than writing the dict out is the point: what ``verify``
    reads has to be what the table actually carries.
    """
    placed = {statistic: null_result(statistic, 1.0, trades) for statistic in STATISTICS}
    placed["net_pnl"] = null_result("net_pnl", net_pnl, trades)
    placed["max_drawdown"] = null_result("max_drawdown", 100.0, trades)
    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(campaign_null.randomentry, "compare", lambda *_a, **_k: placed)
    row = pd.Series({"stratum": "unfiltered", "resolution": 5, NET_TO_DRAWDOWN: 1.0, "trades": 5})

    return measure_row(row, object(), object(), "MNQ", "a", 2, 1)


def test_an_observation_reproducing_the_stored_row_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The columns ``verify`` reads are the ones ``measure_row`` writes, which is the wiring a
    hand-written dict would not pin."""
    verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 40, 1234.5))


def test_an_observation_with_a_different_trade_count_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§M37 and §M38 each caught the moved split only because their plan carried a control that
    failed to reproduce; this is that control, run on every row."""
    with pytest.raises(RuntimeError, match="41 trades, not the 40 stored"):
        verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 41, 1234.5))


def test_an_observation_with_a_different_net_pnl_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same trades, different money: the bars under them were revised rather than replaced."""
    with pytest.raises(RuntimeError, match="net 1300"):
        verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 40, 1300.0))


def test_a_configuration_the_draw_refused_is_not_checked_against_a_stored_row() -> None:
    """A refused row carries no observation at all, so reading one off it would raise a
    ``KeyError`` in place of the verdict it already has."""
    verify_observation(stored_for(assembled(), shortlisted()), {"refused": "no draw freedom"})


def test_an_unstored_configuration_leaves_the_observation_unchecked() -> None:
    verify_observation(None, {"refused": None, "trades": 1, "net_pnl": 0.0})
