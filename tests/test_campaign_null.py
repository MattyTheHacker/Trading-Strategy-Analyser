"""The matched null over a shortlist rather than one row.

The null draws themselves are pinned in ``tests/test_randomentry.py``; what is testable without
data is the part §M27.3 added -- that three rankings are reported side by side, that they are
allowed to disagree, and that a configuration the draw refused carries no verdict instead of a
missing one -- and the part [#320] added, that a stored row is refused unless the re-run is on
the bars it was swept on.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, randomentry, resample, results, sessions, splice, sweep
from nqbt.instruments import get_instrument
from nqbt.sim.types import EmaCrossoverParams
from tools import campaign_null, campaign_report
from tools.campaign_holdout import JOIN_KEYS
from tools.campaign_null import (
    RANKINGS,
    STATISTICS,
    family,
    family_headline,
    family_wise,
    label_of,
    measure_row,
    rankings,
    read_family,
    series_moved,
    stored_for,
    stored_rows,
    verify_bars,
    verify_observation,
)
from tools.campaign_report import NET_TO_DRAWDOWN
from tools.campaign_sweep import campaign_variant_names

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray


def measured(**columns: object) -> pd.DataFrame:
    """Build a table shaped like :func:`~tools.campaign_null.measure`'s output."""
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
    """Return one ``measure_row`` result, with the simulation and the null both stubbed out.

    The identity half is what is under test, so neither a dataset nor a draw is needed --
    stubbing ``compare`` to refuse reaches it by the shortest path.
    """

    def refuse(*_args: object, **_kwargs: object) -> dict[str, object]:
        msg = "stubbed"
        raise randomentry.RandomEntryError(msg)

    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(randomentry, "compare", refuse)
    row = pd.Series(
        {
            "stratum": "unfiltered",
            "resolution": 10,
            NET_TO_DRAWDOWN: 1.0,
            "trades": 5,
            "sweep_id": 1,
            "combo_id": 0,
        }
    )

    return measure_row(row, object(), object(), "MNQ", "a", 2, 1, draw)  # type: ignore[arg-type]  # rebuild and compare are stubbed


def test_a_measured_row_says_which_null_produced_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two arms ask different questions.

    A table mixing them would be two nulls wearing one set of names -- ``docs/roadmap.md``
    §M28.2.
    """
    over_bars = refused_row(monkeypatch, randomentry.OVER_BARS)
    over_levels = refused_row(monkeypatch, randomentry.OVER_LEVELS)

    assert over_bars["draw"] == randomentry.OVER_BARS
    assert over_levels["draw"] == randomentry.OVER_LEVELS


def test_the_draw_defaults_to_the_one_every_archetype_has(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding the second arm must not change what an unflagged run measures."""
    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(
        randomentry,
        "compare",
        lambda *_a, **kwargs: (_ for _ in ()).throw(AssertionError(kwargs["draw"])),
    )
    row = pd.Series(
        {
            "stratum": "unfiltered",
            "resolution": 10,
            NET_TO_DRAWDOWN: 1.0,
            "trades": 5,
            "sweep_id": 1,
            "combo_id": 0,
        }
    )

    with pytest.raises(AssertionError, match=randomentry.OVER_BARS):
        measure_row(row, object(), object(), "MNQ", "a", 2, 1)  # type: ignore[arg-type]  # rebuild and compare are stubbed


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
    """The case the exercise exists for.

    A bracket that suits the bars raises the observed statistic and its own null together --
    ``docs/findings/m26-elastic-band.md`` § "The method that does answer the question".
    """
    table = measured(profit_factor=[3.0, 2.0, 1.0])
    lines = rankings(table)
    assert lines[-1].endswith("DISAGREE")
    assert "best by profit_factor" in lines[0]
    assert lines[0].endswith("a")


def test_a_refused_configuration_is_not_ranked() -> None:
    """A gate that could not run is not a gate that passed.

    The row carries no verdict and must not win an ordering -- ``docs/roadmap.md`` §M28.1.
    """
    table = measured(refused=[None, None, "no draw freedom"], profit_factor=[1.0, 2.0, np.nan])
    lines = rankings(table)
    assert all(line.endswith("b") for line in lines[: len(RANKINGS)]), "the refused row was ranked"
    assert lines[-1].endswith("agree")


def test_a_table_with_nothing_measured_says_so_instead_of_raising() -> None:
    table = measured(refused="no draw freedom")
    assert rankings(table) == ["  (nothing was measured)"]


def test_a_ranking_undefined_on_every_row_is_named_rather_than_skipped() -> None:
    """The whole point of leaving net-to-drawdown undefined is that it can be.

    A run where no configuration had a drawdown must say the ranking is missing.
    """
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
    """``measure`` writes ``None`` rather than omitting the column.

    The filter has to treat a fully-unrefused table as fully rankable.
    """
    table = measured()
    assert table["refused"].isna().all()
    assert rankings(table)[-1].endswith("agree")


def test_the_ranking_window_and_the_test_window_are_separate_columns() -> None:
    """One row must not be two windows wearing one set of names.

    Everything measured is the test window's, and the stored row's own figure is reported under
    its own name.
    """
    table = measured(**{NET_TO_DRAWDOWN: [9.0, 1.0, 1.0]}, ranked_by=[0.1, 0.2, 0.3])
    assert rankings(table)[2].endswith("a"), "the ranking read the test window's column"
    assert table["ranked_by"].iloc[0] == pytest.approx(0.1)


def test_net_to_drawdown_needs_the_two_statistics_it_is_built_from() -> None:
    """``measure_row`` derives it from the observation rather than the stored row.

    Both have to be asked of ``compare`` -- and they are nearly free, since it summarises once.
    """
    assert {"net_pnl", "max_drawdown"} <= set(STATISTICS)


# -- the family summary ----------------------------------------------------------------------


def family_rows(**columns: object) -> pd.DataFrame:
    """Build a table shaped like :func:`~tools.campaign_null.measure`'s output over two cells."""
    base = {
        "strategy": "OpeningRange",
        "test_window": "holdout",
        "ranked_on": "selection",
        "root": ["MNQ", "MNQ", "NQ", "NQ"],
        "stratum": "phase=MIDDAY",
        "resolution": 5,
        "label": ["a", "b", "a", "b"],
        "sweep_id": [1, 1, 2, 2],
        "combo_id": [0, 1, 0, 1],
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
    """The cell is what a score was consistent across, so it is what a null has to be read per.

    ``docs/roadmap.md`` §M28.16.
    """
    summary = family(family_rows())
    assert list(summary["root"]) == ["MNQ", "NQ"]
    assert campaign_null.CELL_KEYS == ["strategy", "root", "stratum"]


def test_a_family_from_saved_runs_keeps_two_bar_sizes_of_one_stratum_apart() -> None:
    """Each saved run may have fixed a different bar size, and two bar sizes are not one population."""
    rows = family_rows(resolution=[5, 10, 5, 10])
    assert len(family(rows)) == 2
    assert len(family(rows, campaign_null.SAVED_CELL_KEYS)) == 4


def test_two_archetypes_sharing_a_stratum_are_two_cells() -> None:
    """A family read from several runs crosses archetypes, and their midday cells are not one cell."""
    rows = pd.concat([family_rows(), family_rows(strategy="InsideBarTrailing")], ignore_index=True)
    assert len(family(rows)) == 4


def test_a_cell_is_summarised_as_a_range_rather_than_a_mean() -> None:
    """Ten configurations of one cell are overlapping runs over the same bars.

    Their spread is the honest summary.
    """
    summary = family(family_rows()).set_index("root")
    assert summary.loc["MNQ", "profit_factor_low"] == pytest.approx(1.0)
    assert summary.loc["MNQ", "profit_factor_high"] == pytest.approx(1.2)
    assert summary.loc["NQ", "excess_low"] == pytest.approx(-0.1)
    assert summary.loc["NQ", "net_to_drawdown_high"] == pytest.approx(0.25)


def test_beating_the_null_and_clearing_the_level_are_counted_separately() -> None:
    """A cell can beat its own null on every configuration and clear p on almost none.

    That is §M28.14's ElasticBand result and the reason both columns are reported.
    """
    summary = family(family_rows()).set_index("root")
    assert summary.loc["MNQ", "beat_null"] == 2
    assert summary.loc["MNQ", "p_under_05"] == 1
    assert summary.loc["NQ", "beat_null"] == 1
    assert summary.loc["NQ", "p_under_05"] == 1


def test_the_level_the_count_is_taken_against_is_named_rather_than_inlined() -> None:
    """It is counted rather than concluded from, so the number a reader corrects for is visible."""
    assert pytest.approx(0.05) == campaign_null.SIGNIFICANT


def test_a_wholly_refused_cell_carries_a_count_rather_than_a_verdict() -> None:
    """A gate that could not run is not one that passed.

    The same reason :data:`~tools.campaign_null.NO_NULL_AVAILABLE` exists.
    """
    rows = family_rows(refused=[None, None, "dense", "dense"])
    summary = family(rows).set_index("root")
    assert summary.loc["NQ", "measured"] == 0
    assert summary.loc["NQ", "refused"] == 2
    assert pd.isna(summary.loc["NQ", "profit_factor_low"])


def test_a_partly_refused_cell_summarises_only_what_ran() -> None:
    """A row refused alongside rows that ran carries no verdict, so it must not reach the range either."""
    rows = family_rows(refused=[None, "dense", None, None])
    summary = family(rows).set_index("root")
    assert summary.loc["MNQ", "measured"] == 1
    assert summary.loc["MNQ", "refused"] == 1
    assert summary.loc["MNQ", "profit_factor_high"] == pytest.approx(1.0)


# -- the family-wise null, over one run or several saved ones --------------------------------

NOISE_DRAWS = 199
"""Draws per test in the family-wise fixtures, so a p resolves in steps of 1/200."""


def drawn_rows(seed: int = 3, **columns: object) -> pd.DataFrame:
    """Build :func:`family_rows` with every row carrying its own profit-factor draws, as ``measure`` does."""
    rng = np.random.default_rng(seed)
    draws = [1.0 + rng.normal(0.0, 0.1, NOISE_DRAWS) for _ in range(4)]

    return family_rows(**{campaign_null.DRAWS_COLUMN: draws, **columns})


def with_draws(rows: pd.DataFrame, row: int, draws: FloatArray) -> pd.DataFrame:
    """Return ``rows`` with one row's draws replaced, which no cell setter takes as a single value."""
    column = pd.Series(
        [draws if index == row else kept for index, kept in enumerate(rows[campaign_null.DRAWS_COLUMN])],
        index=rows.index,
        dtype=object,
    )

    return rows.assign(**{campaign_null.DRAWS_COLUMN: column})


def test_a_measured_row_carries_its_profit_factor_draws(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the family-wise null reads has to be what ``measure_row`` writes, not a hand-built column."""
    draws = np.array([0.9, 1.1, np.inf, np.nan])
    placed = {statistic: null_result(statistic, 1.0, 40) for statistic in STATISTICS}
    placed["profit_factor"] = replace(placed["profit_factor"], draws=draws)
    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(randomentry, "compare", lambda *_a, **_k: placed)
    row = pd.Series(
        {
            "stratum": "unfiltered",
            "resolution": 5,
            NET_TO_DRAWDOWN: 1.0,
            "trades": 5,
            "sweep_id": 1,
            "combo_id": 0,
        }
    )
    measured_row_ = measure_row(row, object(), object(), "MNQ", "a", 2, 1)  # type: ignore[arg-type]  # rebuild and compare are stubbed
    assert measured_row_[campaign_null.DRAWS_COLUMN] is draws


def test_every_measured_row_gets_a_standardised_excess_and_a_family_wise_p() -> None:
    widened = family_wise(drawn_rows())
    assert widened[campaign_null.EXCESS_Z].notna().all()
    assert widened[campaign_null.FAMILY_P].between(0.0, 1.0).all()


def test_a_family_of_one_reads_its_own_one_sided_p() -> None:
    """The family-wise p of a lone test is that test's own p, one-sided, on its standardised draws."""
    one = drawn_rows().iloc[[0]]
    observed, draws = randomentry.standardised_excess(1.0, one.iloc[0][campaign_null.DRAWS_COLUMN])
    expected = ((draws >= observed).sum() + 1) / (NOISE_DRAWS + 1)
    assert family_wise(one)[campaign_null.FAMILY_P].iloc[0] == pytest.approx(expected)


def test_a_wider_family_never_lowers_a_tests_family_wise_p() -> None:
    narrow = family_wise(drawn_rows().iloc[:2])
    wide = family_wise(drawn_rows())
    assert np.all(
        wide[campaign_null.FAMILY_P].iloc[:2].to_numpy() >= narrow[campaign_null.FAMILY_P].to_numpy()
    )


def test_a_refused_row_is_left_out_of_the_family_and_carries_no_family_wise_p() -> None:
    rows = drawn_rows(refused=[None, None, "dense", None])
    widened = family_wise(rows)
    assert pd.isna(widened.loc[2, campaign_null.FAMILY_P])
    assert widened[campaign_null.FAMILY_P].drop(index=2).notna().all()
    alone = family_wise(rows.drop(index=2))
    assert widened[campaign_null.FAMILY_P].drop(index=2).to_numpy() == pytest.approx(
        alone[campaign_null.FAMILY_P].to_numpy()
    )


def test_a_table_with_nothing_measured_gets_the_columns_and_no_values() -> None:
    widened = family_wise(drawn_rows(refused="dense"))
    assert widened[campaign_null.FAMILY_P].isna().all()


def test_a_test_read_twice_is_refused_rather_than_counted_twice() -> None:
    rows = drawn_rows()
    with pytest.raises(RuntimeError, match="repeat a test"):
        family_wise(pd.concat([rows, rows.iloc[[0]]], ignore_index=True))


def test_rows_drawn_a_different_number_of_times_are_refused() -> None:
    rows = with_draws(drawn_rows(), 0, np.ones(NOISE_DRAWS + 1))
    with pytest.raises(RuntimeError, match="do not line up one to one"):
        family_wise(rows)


def test_a_cell_reports_its_lowest_family_wise_p_once_there_is_one() -> None:
    assert "family_p_low" not in family(family_rows()).columns
    widened = family_wise(drawn_rows())
    summary = family(widened).set_index("root")
    assert summary.loc["MNQ", "family_p_low"] == pytest.approx(
        widened.loc[widened["root"] == "MNQ", campaign_null.FAMILY_P].min()
    )


def test_the_headline_names_the_best_test_and_the_family_size() -> None:
    widened = family_wise(drawn_rows(profit_factor=[1.0, 1.5, 0.9, 1.1]))
    headline = family_headline(widened)
    assert "the best of 4 tests is OpeningRange MNQ phase=MIDDAY b" in headline


def test_the_headline_says_so_when_nothing_was_measured() -> None:
    assert family_headline(family_wise(drawn_rows(refused="dense"))) == (
        "nothing was measured, so there is no family-wise p"
    )


def test_saved_tables_read_back_as_one_family_with_their_draws_intact(tmp_path: Path) -> None:
    """Several runs, one family: the round trip through saved tables moves no family-wise p."""
    gapped = np.append(drawn_rows(seed=3)[campaign_null.DRAWS_COLUMN].iloc[0][:-2], [np.inf, np.nan])
    original = [with_draws(drawn_rows(seed=3), 0, gapped), drawn_rows(seed=4, strategy="InsideBarTrailing")]
    paths = [tmp_path / "first.parquet", tmp_path / "second.parquet"]
    for table, path in zip(original, paths, strict=True):
        table.to_parquet(path, index=False)

    read_back = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    together = pd.concat(original, ignore_index=True)
    assert np.array_equal(read_back[campaign_null.DRAWS_COLUMN].iloc[0], gapped, equal_nan=True)
    assert family_wise(read_back)[campaign_null.FAMILY_P].to_numpy() == pytest.approx(
        family_wise(together)[campaign_null.FAMILY_P].to_numpy()
    )
    assert read_family(paths) == 0


def test_saved_tables_with_nothing_measured_exit_as_a_gate_that_did_not_run(tmp_path: Path) -> None:
    """A wholly refused run is saved without a draws column, since no row was ever drawn."""
    path = tmp_path / "refused.parquet"
    family_rows(refused="dense").to_parquet(path, index=False)
    assert read_family([path]) == campaign_null.NO_NULL_AVAILABLE


def test_a_wholly_refused_table_beside_a_measured_one_still_reads(tmp_path: Path) -> None:
    paths = [tmp_path / "refused.parquet", tmp_path / "measured.parquet"]
    family_rows(refused="dense", strategy="DeadCatBounce").to_parquet(paths[0], index=False)
    drawn_rows().to_parquet(paths[1], index=False)
    assert read_family(paths) == 0


def test_a_null_with_no_spread_leaves_its_test_out_and_the_rest_in() -> None:
    """One degenerate configuration must not cost a family read that took hours to measure."""
    rows = with_draws(drawn_rows(), 1, np.ones(NOISE_DRAWS))
    widened = family_wise(rows)
    assert pd.isna(widened.loc[1, campaign_null.FAMILY_P])
    assert widened[campaign_null.FAMILY_P].drop(index=1).notna().all()
    assert "the best of 3 tests" in family_headline(widened)


def test_a_family_mixing_test_windows_is_refused() -> None:
    with pytest.raises(RuntimeError, match=r"tested on .* different questions and not one family"):
        family_wise(drawn_rows(test_window=["holdout", "holdout", "full", "holdout"]))


def test_a_family_mixing_ranking_windows_is_refused() -> None:
    with pytest.raises(RuntimeError, match=r"ranked on .* different questions and not one family"):
        family_wise(drawn_rows(ranked_on=["selection", "full", "selection", "selection"]))


def test_a_family_read_with_every_test_left_out_exits_as_a_gate_that_did_not_run(tmp_path: Path) -> None:
    path = tmp_path / "flat.parquet"
    flat = drawn_rows()
    for row in range(len(flat)):
        flat = with_draws(flat, row, np.ones(NOISE_DRAWS))
    flat.to_parquet(path, index=False)
    assert read_family([path]) == campaign_null.NO_NULL_AVAILABLE


def test_the_headline_names_which_p_is_one_sided_and_which_two_sided() -> None:
    """The per-test p is two-sided and the family-wise one one-sided, so the second can be the smaller."""
    headline = family_headline(family_wise(drawn_rows()))
    assert "one-sided family-wise p" in headline
    assert "its own two-sided p" in headline


def test_ties_at_the_floor_name_the_largest_excess_whatever_the_row_order() -> None:
    widened = family_wise(drawn_rows(profit_factor=[9.0, 8.0, 0.9, 1.1]))
    assert widened[campaign_null.FAMILY_P].iloc[0] == widened[campaign_null.FAMILY_P].iloc[1]
    assert family_headline(widened) == family_headline(widened.iloc[::-1])
    assert "MNQ phase=MIDDAY a," in family_headline(widened)


@pytest.mark.parametrize("option", ["--root", "--stratum"])
def test_a_cell_named_twice_is_refused_before_anything_is_measured(option: str) -> None:
    with pytest.raises(SystemExit) as refused:
        campaign_null.main(["campaign_null.py", "--strategy", "EmaPullback", option, "MNQ", "MNQ"])
    assert refused.value.code == 2


@pytest.mark.parametrize("extra", [["--strategy", "EmaPullback"], ["--out", "x.parquet"]])
def test_the_family_read_refuses_the_options_it_would_ignore(extra: list[str]) -> None:
    with pytest.raises(SystemExit) as refused:
        campaign_null.main(["campaign_null.py", "--family-of", "a.parquet", *extra])
    assert refused.value.code == 2


def test_one_label_on_two_stored_rows_is_two_tests() -> None:
    """A label names only what varied in its own run, so it cannot say whether two rows are one test."""
    widened = family_wise(drawn_rows(label="a"))
    assert widened[campaign_null.FAMILY_P].notna().all()


def test_campaign_only_ranks_the_archetypes_own_campaign_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later set storing rows under the cell's stratum name must not reach its shortlist."""
    asked: dict[str, object] = {}

    def record(*shortlist_args: object) -> pd.DataFrame:
        asked["variant"] = shortlist_args[7]

        return pd.DataFrame()

    monkeypatch.setattr(campaign_null, "shortlist", record)
    monkeypatch.setattr(campaign_null, "measure", lambda *_a, **_k: pd.DataFrame())
    args = argparse.Namespace(
        strategy="EmaPullback",
        window=["selection"],
        test_window="holdout",
        by="profit_factor",
        top=10,
        resolution=5,
        variant=None,
        campaign_only=True,
        iterations=2,
        n_jobs=1,
        draw=randomentry.OVER_BARS,
    )
    campaign_null.cell(args, archetypes.EMAPULLBACK, "MNQ", "phase=MIDDAY")
    assert asked["variant"] == campaign_variant_names("EmaPullback")


def test_campaign_only_and_a_named_variant_are_refused_together() -> None:
    with pytest.raises(SystemExit) as refused:
        campaign_null.main(
            ["campaign_null.py", "--strategy", "EmaPullback", "--campaign-only", "--variant", "stop=slow"]
        )
    assert refused.value.code == 2


def test_the_family_read_needs_no_strategy_and_a_measured_run_does(tmp_path: Path) -> None:
    path = tmp_path / "table.parquet"
    drawn_rows().to_parquet(path, index=False)
    assert campaign_null.main(["campaign_null.py", "--family-of", str(path)]) == 0
    with pytest.raises(SystemExit) as refused:
        campaign_null.main(["campaign_null.py"])
    assert refused.value.code == 2


# -- the bars a stored row was swept on ------------------------------------------------------


FIRST_BAR = pd.Timestamp("2021-09-19 22:05:00")
LAST_BAR = pd.Timestamp("2024-09-17 14:56:00")
"""The ends of one stored sweep, naive as ``results.save_sweep`` writes them."""


def stored_frame(**columns: object) -> pd.DataFrame:
    """Build a frame shaped like :func:`~tools.campaign_null.stored_rows`' output, unindexed."""
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
    """Run :func:`~tools.campaign_null.stored_rows` over a stubbed query."""
    stored = stored_frame() if frame is None else frame
    monkeypatch.setattr(campaign_null, "db_path", Path)
    monkeypatch.setattr(results, "query", lambda *_a, **_k: stored)

    return stored_rows("InsideBar", "MNQ", "holdout")


def assembled() -> pd.DataFrame:
    """Build the same frame without monkeypatching, for the tests that only read one row from it."""
    return stored_frame().set_index(JOIN_KEYS, drop=False)


def shortlisted(**columns: object) -> pd.Series:  # type: ignore[explicit-any]  # a row of mixed dtypes
    """Build one shortlist row, carrying the keys that identify it in another window."""
    base = {
        "sweep_id": 7,
        "combo_id": 10,
        "root": "MNQ",
        "resolution": 5,
        "variant": "bracket",
        "stratum": "unfiltered",
    }

    return pd.Series({**base, **columns})


def paired(stored: pd.DataFrame, row: pd.Series) -> pd.Series:  # type: ignore[explicit-any]  # a row of mixed dtypes
    """Return the stored row ``row`` pairs with, which the calling test expects to exist."""
    match = stored_for(stored, row)
    assert match is not None, "the window never swept this row"

    return match


def bars(first: str | pd.Timestamp, last: str | pd.Timestamp) -> pd.DataFrame:
    """Build a bar frame with only its two ends, stamped the way the archive is."""
    index = pd.DatetimeIndex([pd.Timestamp(first, tz="UTC"), pd.Timestamp(last, tz="UTC")])

    return pd.DataFrame({"close": [1.0, 2.0]}, index=index)


def test_a_stored_row_is_found_by_the_keys_that_pair_two_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ranking window and the test window are different sweeps.

    The stored counterpart has to be found by configuration rather than by ``sweep_id``.
    """
    found = stored_for(stubbed(monkeypatch), shortlisted())
    assert found is not None
    assert int(found["trades"]) == 40
    assert found["first_bar"] == FIRST_BAR


def test_a_configuration_the_test_window_never_swept_has_no_counterpart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shortlist spanning two variant sets can reach it.

    A check that could not run is not one that failed.
    """
    assert stored_for(stubbed(monkeypatch), shortlisted(combo_id=99)) is None


def test_another_roots_rows_are_not_a_counterpart(monkeypatch: pytest.MonkeyPatch) -> None:
    """NQ and MNQ hold the same ``combo_id`` at the same bar size.

    Their trade counts are equal while their money is ten times apart -- ``CLAUDE.md``, the
    tick-value rule.
    """
    stored = stubbed(monkeypatch, stored_frame(root=["NQ", "NQ"]))
    assert stored.empty
    assert stored_for(stored, shortlisted()) is None


def test_two_stored_rows_under_one_key_are_refused_rather_than_chosen_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``tools/campaign_holdout.py`` pairs the windows one-to-one on the same keys.

    An ambiguous database is a failure there too.
    """
    with pytest.raises(RuntimeError, match="more than one row under the same"):
        stubbed(monkeypatch, stored_frame(combo_id=[10, 10]))


def test_a_stored_row_carries_the_bar_range_of_its_own_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sweeps of one window can hold different ranges.

    The range travels with the row rather than being read once for the whole run.
    """
    stored = stubbed(
        monkeypatch,
        stored_frame(sweep_id=[1, 2], first_bar=[FIRST_BAR, LAST_BAR]),
    )
    assert paired(stored, shortlisted())["first_bar"] == FIRST_BAR
    assert paired(stored, shortlisted(combo_id=11))["first_bar"] == LAST_BAR


def swept(db: Path, window: str, trades: list[int], bars_frame: pd.DataFrame) -> None:
    """Store one ``sweeps`` row and its combinations the way ``campaign_sweep.run_point`` does."""
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
    """A real round trip, because the claim is about the SQL: rows under ``MIN_TRADES`` are read too.

    ``tools/README.md`` § "campaign_null.py".
    """
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
    """The stored stamps are naive UTC and a bar index is zoned.

    That is the comparison that would otherwise report every run as moved.
    """
    assert series_moved(paired(assembled(), shortlisted()), bars(FIRST_BAR, LAST_BAR)) == ""


def test_each_end_of_the_series_is_named_on_its_own() -> None:
    """Which end moved is the diagnosis.

    A later export extends the last bar, more history moves the first, and a re-split moves
    both.
    """
    reference = paired(assembled(), shortlisted())
    later = series_moved(reference, bars(FIRST_BAR, "2026-09-16 12:07"))
    earlier = series_moved(reference, bars("2019-01-02 00:00", LAST_BAR))
    both = series_moved(reference, bars("2019-01-02 00:00", "2026-09-16 12:07"))
    assert later.startswith("last bar was")
    assert "first bar" not in later
    assert earlier.startswith("first bar was")
    assert "last bar" not in earlier
    assert both.count("bar was") == 2


def test_a_rerun_on_a_series_that_has_moved_is_refused() -> None:
    """The archive was extended under every campaign stored before 2026-09-16, which moved the split.

    ``docs/roadmap.md`` § "Standing traps".
    """
    reference = stored_for(assembled(), shortlisted())
    with pytest.raises(RuntimeError, match="swept on a different series"):
        verify_bars(reference, bars(FIRST_BAR, "2026-09-16 12:07"), "a", "holdout")


def test_a_rerun_on_the_stored_series_is_not_refused() -> None:
    verify_bars(stored_for(assembled(), shortlisted()), bars(FIRST_BAR, LAST_BAR), "a", "holdout")


def test_an_unstored_configuration_is_warned_about_rather_than_refused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A check that could not run must not read as one that passed, so it is said out loud.

    The same distinction :data:`~tools.campaign_null.NO_NULL_AVAILABLE` draws.
    """
    with caplog.at_level("WARNING"):
        verify_bars(None, bars(FIRST_BAR, LAST_BAR), "a", "holdout")

    assert "unchecked" in caplog.text
    assert "holdout" in caplog.text


# -- the observation against the row the sweep stored ----------------------------------------


def null_result(statistic: str, observed: float, trades: int) -> randomentry.NullResult:
    """Build one :class:`~nqbt.randomentry.NullResult` with everything but the observation stubbed."""
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
    """Return one real :func:`~tools.campaign_null.measure_row` result, with only ``compare`` stubbed.

    Going through the producer rather than writing the dict out is the point: what ``verify``
    reads has to be what the table actually carries.
    """
    placed = {statistic: null_result(statistic, 1.0, trades) for statistic in STATISTICS}
    placed["net_pnl"] = null_result("net_pnl", net_pnl, trades)
    placed["max_drawdown"] = null_result("max_drawdown", 100.0, trades)
    monkeypatch.setattr(campaign_null, "rebuild", lambda *_: object())
    monkeypatch.setattr(randomentry, "compare", lambda *_a, **_k: placed)
    row = pd.Series(
        {
            "stratum": "unfiltered",
            "resolution": 5,
            NET_TO_DRAWDOWN: 1.0,
            "trades": 5,
            "sweep_id": 1,
            "combo_id": 0,
        }
    )

    return measure_row(row, object(), object(), "MNQ", "a", 2, 1)  # type: ignore[arg-type]  # rebuild and compare are stubbed


def test_an_observation_reproducing_the_stored_row_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The columns ``verify`` reads are the ones ``measure_row`` writes.

    That is the wiring a hand-written dict would not pin.
    """
    verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 40, 1234.5))


def test_an_observation_with_a_different_trade_count_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§M37's and §M38's reproduction control, run on every row.

    Each caught the moved split only because its plan carried a control that failed to
    reproduce.
    """
    with pytest.raises(RuntimeError, match="41 trades, not the 40 stored"):
        verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 41, 1234.5))


def test_an_observation_with_a_different_net_pnl_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same trades, different money: the bars under them were revised rather than replaced."""
    with pytest.raises(RuntimeError, match="net 1300"):
        verify_observation(stored_for(assembled(), shortlisted()), measured_row(monkeypatch, 40, 1300.0))


def test_a_configuration_the_draw_refused_is_not_checked_against_a_stored_row() -> None:
    """A refused row carries no observation at all.

    Reading one off it would raise a ``KeyError`` in place of the verdict it already has.
    """
    verify_observation(stored_for(assembled(), shortlisted()), {"refused": "no draw freedom"})


def test_an_unstored_configuration_leaves_the_observation_unchecked() -> None:
    verify_observation(None, {"refused": None, "trades": 1, "net_pnl": 0.0})


# -- what the bars are ------------------------------------------------------------------------


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Build a random walk at index prices, so a round number is a round number."""
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


def test_a_round_number_configuration_is_placed_against_its_null_rather_than_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``measure`` declares its raw bars ``RAW``, so a rule reading an absolute level runs ([#340])."""
    db = tmp_path / "EmaCrossover.duckdb"
    bars = synthetic_bars()
    frame = resample.resample(bars, 5)
    params = EmaCrossoverParams(round_number_points=25.0, bars_required_to_trade=60)
    grid = sweep.Grid.of(params, archetype=archetypes.EMACROSSOVER, atr_stop_multiple=[2.0])
    data = context.prepare(
        frame,
        grid.required_context(),
        bar_minutes=5,
        price_basis=context.PriceBasis.RAW,
    )
    table, _ = sweep.sweep(frame, grid, get_instrument("MNQ"), data=data)
    table.insert(0, "variant", "stop=atr round=on")
    table.insert(1, "stratum", "unfiltered")
    table.insert(2, "window", "full")
    table["combo_id"] = range(len(table))
    results.save_sweep(
        table,
        root="MNQ",
        instrument="MNQ",
        bars=frame,
        axes=grid.axis_values(),
        strategy="EmaCrossover",
        resolution=5,
        db_path=db,
    )
    monkeypatch.setattr(campaign_null, "db_path", lambda _: db)
    monkeypatch.setattr(campaign_report, "db_path", lambda _: db)
    monkeypatch.setattr(splice, "load_continuous", lambda *_a, **_k: bars)

    rows = campaign_report.load("EmaCrossover", ["full"])
    assert not rows.empty, "the fixture cleared no row past the trade floor; it proves nothing"

    measured = campaign_null.measure(rows, archetypes.EMACROSSOVER, "MNQ", "full", 4, 1)

    assert len(measured) == len(rows)
    assert measured["refused"].isna().all(), "the null was refused, so nothing was placed"
