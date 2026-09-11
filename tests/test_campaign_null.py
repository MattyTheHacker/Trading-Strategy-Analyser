"""The matched null over a shortlist rather than one row.

The null draws themselves are pinned in ``tests/test_randomentry.py``; what is testable without
data is the part §M27.3 added -- that three rankings are reported side by side, that they are
allowed to disagree, and that a configuration the draw refused carries no verdict instead of a
missing one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import randomentry
from tools import campaign_null
from tools.campaign_null import RANKINGS, STATISTICS, family, label_of, measure_row, rankings
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
    statistic and its own null together -- ``docs/roadmap.md`` § "The method that does answer
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
