"""Pairing a stratum against its unfiltered twin, and counting where the two windows agree.

Every function under test is pure, so none of this needs a database. What is worth pinning is
the join -- which columns identify "the same combination" when one of them is deliberately
different -- and the counting rule, which is the whole claim the tool makes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.campaign_crossread import (
    BACKFILLED,
    CELL_KEYS,
    MISSING,
    WINDOWS,
    agreement,
    common_variants,
    context_columns,
    is_recut,
    matrix,
    paired,
    pairing_columns,
)
from tools.campaign_report import TAGS, UNFILTERED


def rows(**columns: object) -> pd.DataFrame:
    """A results frame carrying one parameter, one context filter and the stats the tool reads."""
    base = {
        "sweep_id": 1,
        "combo_id": range(4),
        "variant": "bracket",
        "stratum": UNFILTERED,
        "window": "holdout",
        "strategy": "InsideBar",
        "resolution": 5,
        "contract": None,
        "tier2": "reconciled",
        "root": "MNQ",
        "tp_multiplier": [1.0, 2.0, 3.0, 4.0],
        "phase_filter": 127,
        "profit_factor": 1.0,
        "trades": 100,
        "net_pnl": 0.0,
        "session_close_share": 0.1,
    }

    return pd.DataFrame({**base, **columns})


def twinned(arm_pf: list[float], base_pf: list[float], stratum: str = "phase=MIDDAY") -> pd.DataFrame:
    """One filtered stratum and the unfiltered rows it pairs against, in one window."""
    arm = rows(stratum=stratum, phase_filter=16, profit_factor=arm_pf)
    base = rows(profit_factor=base_pf)

    return pd.concat([base, arm], ignore_index=True)


# -- which columns identify the same combination -------------------------------------------


def test_every_axis_a_stratum_generator_sets_is_a_context_column() -> None:
    """Derived from the generators, so a new dimension cannot leave a column behind."""
    found = context_columns()
    assert {
        "phase_filter",
        "regime_filter",
        "volume_filter",
        "trend_filter",
        "compression_filter",
        "higher_timeframe_filter",
    } <= found


def test_the_fitted_regime_axes_are_context_columns_too() -> None:
    """``_per_lookback`` sets them only under a calibration, which ``probe_cuts`` supplies."""
    assert {"regime_lookback", "regime_consolidating_below", "regime_directional_above"} <= context_columns()


def test_a_context_column_is_never_part_of_the_join_key() -> None:
    """Keeping one would pair every stratum with itself and nothing else."""
    assert set(pairing_columns(rows())).isdisjoint(context_columns())


def test_a_real_parameter_stays_in_the_join_key() -> None:
    assert "tp_multiplier" in pairing_columns(rows())


def test_a_tag_is_never_part_of_the_join_key() -> None:
    assert set(pairing_columns(rows())).isdisjoint(TAGS)


# -- the pairing ----------------------------------------------------------------------------


def test_a_filtered_row_pairs_with_the_unfiltered_row_of_the_same_parameters() -> None:
    merged = paired(twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3]))
    assert len(merged) == 4
    assert merged["profit_factor_base"].tolist() == [1.0, 1.1, 1.2, 1.3]


def test_pairing_is_by_parameter_and_not_by_row_order() -> None:
    """``combo_id`` is offset per stratum block within a sweep, so it cannot be the key."""
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame.loc[frame["stratum"] != UNFILTERED, "combo_id"] = [400, 401, 402, 403]
    shuffled = frame.iloc[::-1].reset_index(drop=True)

    merged = paired(shuffled).sort_values("tp_multiplier").reset_index(drop=True)
    assert merged["tp_multiplier"].tolist() == [1.0, 2.0, 3.0, 4.0]
    assert merged["profit_factor"].tolist() == [1.4, 1.5, 1.6, 1.7]
    assert merged["profit_factor_base"].tolist() == [1.0, 1.1, 1.2, 1.3]


def test_a_pair_is_never_formed_across_two_resolutions() -> None:
    """Bar size is the largest lever, so a cell of one size is not a twin of another."""
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame.loc[frame["stratum"] != UNFILTERED, "resolution"] = 15
    assert paired(frame).empty


def test_a_pair_is_never_formed_across_two_roots() -> None:
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame.loc[frame["stratum"] != UNFILTERED, "root"] = "NQ"
    assert paired(frame).empty


def test_resolution_and_root_are_both_cell_keys() -> None:
    assert CELL_KEYS == ["root", "resolution"]


def test_an_absent_parameter_still_pairs_rather_than_dropping_the_row() -> None:
    """A NaN never equals itself, so without the sentinel the merge would silently lose these."""
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame["stop_range_fraction"] = np.nan
    assert len(paired(frame)) == 4


def test_the_sentinel_cannot_collide_with_a_real_parameter_value() -> None:
    assert MISSING < -1e6


def test_a_column_a_sweep_predates_pairs_against_one_that_carries_its_off_value() -> None:
    """`max_hold_bars` arrived with §M29, so every earlier row is null where a later one is 0."""
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame["max_hold_bars"] = pd.array([pd.NA] * 4 + [0] * 4, dtype="Int64")
    assert len(paired(frame)) == 4


def test_backfilling_that_column_does_not_pair_two_different_caps() -> None:
    """The null stands in for the off value alone; a real cap is still a parameter."""
    frame = twinned([1.4, 1.5, 1.6, 1.7], [1.0, 1.1, 1.2, 1.3])
    frame["max_hold_bars"] = pd.array([40] * 4 + [0] * 4, dtype="Int64")
    assert paired(frame).empty


def test_every_backfilled_column_states_the_value_its_rows_ran_at() -> None:
    assert BACKFILLED == {"max_hold_bars": 0}


def test_a_frame_with_no_unfiltered_row_pairs_nothing() -> None:
    arm = rows(stratum="phase=MIDDAY", phase_filter=16)
    assert paired(arm).empty


def test_a_frame_with_no_filtered_row_pairs_nothing() -> None:
    assert paired(rows()).empty


# -- which variants the two sides are allowed to share --------------------------------------


def test_only_the_variants_every_plain_stratum_holds_are_compared() -> None:
    """A variant one stratum ran and another did not would compare the geometry, not the cell."""
    midday = rows(stratum="phase=MIDDAY", phase_filter=16, variant="fade")
    london = rows(stratum="phase=LONDON", phase_filter=2, variant="breakout")
    assert common_variants(pd.concat([rows(), midday, london], ignore_index=True)) == set()


def test_a_shared_variant_survives_the_intersection() -> None:
    midday = rows(stratum="phase=MIDDAY", phase_filter=16)
    london = rows(stratum="phase=LONDON", phase_filter=2)
    assert common_variants(pd.concat([rows(), midday, london], ignore_index=True)) == {"bracket"}


def test_a_recut_does_not_empty_the_variant_intersection() -> None:
    """ElasticBand and OpeningRange both reported nothing until re-cuts were left out."""
    midday = rows(stratum="phase=MIDDAY", phase_filter=16)
    recut = rows(stratum="volume=HEAVY@per_bar_20 q=0.20/0.80", variant="volume-campaign")
    assert common_variants(pd.concat([rows(), midday, recut], ignore_index=True)) == {"bracket"}


def test_a_cell_carrying_its_own_cut_is_a_recut() -> None:
    assert is_recut("regime=CONSOLIDATING@n=20")
    assert is_recut("volume=HEAVY@per_bar_20 q=0.20/0.80")


def test_a_plain_cell_is_not_a_recut() -> None:
    assert not is_recut("phase=MIDDAY")
    assert not is_recut(UNFILTERED)


# -- the counting rule ----------------------------------------------------------------------


def cells(selection: float, holdout: float, stratum: str = "phase=MIDDAY") -> pd.DataFrame:
    """One cell's paired delta in each window, as :func:`per_window` would report it."""
    return pd.DataFrame(
        [
            {
                "strategy": "InsideBar",
                "stratum": stratum,
                "root": "MNQ",
                "resolution": 5,
                "window": window,
                "delta": delta,
                "profit_factor": 1.0 + delta,
                "trades": 100,
                "session_close_share": 0.1,
            }
            for window, delta in zip(WINDOWS, (selection, holdout), strict=True)
        ],
    )


def test_a_filter_that_wins_in_both_windows_counts_as_helping() -> None:
    scored = agreement(cells(0.2, 0.3))
    assert scored["helped"].item() == 1
    assert scored["hurt"].item() == 0
    assert scored["score"].item() == 1


def test_a_filter_that_loses_in_both_windows_counts_as_hurting() -> None:
    scored = agreement(cells(-0.2, -0.3))
    assert scored["hurt"].item() == 1
    assert scored["score"].item() == -1


def test_a_filter_that_wins_one_window_and_loses_the_other_counts_for_neither() -> None:
    """Disagreeing across two disjoint spans is exactly what the score exists to exclude."""
    scored = agreement(cells(0.2, -0.3))
    assert scored["helped"].item() == 0
    assert scored["hurt"].item() == 0
    assert scored["score"].item() == 0


def test_a_cell_measured_in_only_one_window_is_dropped_rather_than_counted() -> None:
    one = cells(0.2, 0.3)
    assert agreement(one[one["window"] == "holdout"]).empty


def test_the_score_is_the_difference_between_the_two_counts() -> None:
    """Three cells: two winning in both windows, one losing in both."""
    block = pd.concat(
        [
            cells(0.2, 0.3).assign(resolution=1),
            cells(0.2, 0.3).assign(resolution=5),
            cells(-0.2, -0.3).assign(resolution=15),
        ],
        ignore_index=True,
    )
    scored = agreement(block)
    assert scored["cells"].item() == 3
    assert scored["helped"].item() == 2
    assert scored["hurt"].item() == 1
    assert scored["score"].item() == 1


def test_the_score_is_reported_per_stratum_rather_than_pooled_over_the_dimension() -> None:
    block = pd.concat([cells(0.2, 0.3), cells(-0.2, -0.3, "phase=CLOSE")], ignore_index=True)
    scored = agreement(block).set_index("stratum")
    assert scored.loc["phase=MIDDAY", "score"] == 1
    assert scored.loc["phase=CLOSE", "score"] == -1


def test_an_empty_frame_scores_nothing_rather_than_raising() -> None:
    assert agreement(pd.DataFrame()).empty


def test_the_dimension_and_the_cell_are_read_off_the_stratum_name() -> None:
    scored = agreement(cells(0.2, 0.3))
    assert scored["dimension"].item() == "phase"
    assert scored["cell"].item() == "MIDDAY"


# -- the matrix -----------------------------------------------------------------------------


def test_the_matrix_puts_cells_down_the_rows_and_archetypes_across() -> None:
    block = pd.concat(
        [
            cells(0.2, 0.3),
            cells(-0.2, -0.3, "phase=CLOSE"),
            cells(0.2, 0.3).assign(strategy="OpeningRange"),
        ],
        ignore_index=True,
    )
    table = matrix(agreement(block), "phase")
    assert table.loc["MIDDAY", "InsideBar"] == 1
    assert table.loc["MIDDAY", "OpeningRange"] == 1
    assert table.loc["CLOSE", "InsideBar"] == -1


def test_a_cell_no_archetype_reached_is_absent_rather_than_zero() -> None:
    """Structurally impossible and merely negative must not read the same way."""
    block = pd.concat(
        [cells(0.2, 0.3), cells(0.2, 0.3, "phase=CLOSE").assign(strategy="OpeningRange")],
        ignore_index=True,
    )
    table = matrix(agreement(block), "phase")
    assert pd.isna(table.loc["CLOSE", "InsideBar"])


def test_a_dimension_with_no_rows_gives_an_empty_matrix() -> None:
    assert matrix(agreement(cells(0.2, 0.3)), "volume").empty


# -- the windows ----------------------------------------------------------------------------


def test_both_windows_are_required_and_named() -> None:
    """The claim is agreement across two disjoint spans, so neither may be dropped."""
    assert WINDOWS == ("selection", "holdout")


@pytest.mark.parametrize("window", WINDOWS)
def test_each_window_is_one_the_campaign_actually_stores(window: str) -> None:
    assert window in {"selection", "holdout", "full"}
