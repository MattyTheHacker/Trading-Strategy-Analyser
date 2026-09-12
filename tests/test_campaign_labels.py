"""Comparing a raw context label against the fitted one over the same bars.

The two table builders need the spliced series, so what is pinned here is everything that does
not: the row normalisation, the warm-up drop, and — the one that would silently lie — that the
pair called "raw" is the pair the stored strata were actually cut by.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.campaign_labels import (
    RAW_REGIME,
    RAW_VOLUME,
    REGIME_ORDER,
    VOLUME_ORDER,
    confusion,
    named,
    volume_series,
)

from tools.campaign_sweep import VOLUME_BASELINE_SESSIONS, VOLUME_ROLLING_BARS

from nqbt import regime, volume
from nqbt.sim.types import DeadCatParams


# -- the pair the stored strata were cut by ---------------------------------------------------


def test_the_raw_regime_pair_is_the_one_every_stored_stratum_was_cut_by() -> None:
    """A changed default would otherwise make this tool compare against a cut nobody ran."""
    params = DeadCatParams()
    assert RAW_REGIME == (params.regime_consolidating_below, params.regime_directional_above)


def test_the_raw_volume_pair_is_the_one_every_stored_stratum_was_cut_by() -> None:
    params = DeadCatParams()
    assert RAW_VOLUME == (params.volume_thin_below, params.volume_heavy_above)


def test_both_orders_name_every_state_of_their_dimension() -> None:
    """`regime.UNDEFINED` is a warm-up marker rather than a member, so the enum is the three."""
    assert set(REGIME_ORDER) == {state.name for state in regime.Regime}
    assert set(VOLUME_ORDER) == {state.name for state in volume.VolumeState}


# -- the warm-up drop -------------------------------------------------------------------------


def test_named_drops_the_bars_the_mask_excludes() -> None:
    labels = np.array([0, 1, 2, 1], dtype=np.int8)
    keep = np.array([False, True, True, True])

    assert named(labels, {0: "A", 1: "B", 2: "C"}, keep, "raw").tolist() == ["B", "C", "B"]


def test_named_carries_the_column_name_the_crosstab_reads() -> None:
    labels = np.array([1, 1], dtype=np.int8)

    assert named(labels, {1: "B"}, np.array([True, True]), "fitted").name == "fitted"


def test_named_on_an_all_warm_up_series_is_empty_rather_than_raising() -> None:
    labels = np.array([0, 0], dtype=np.int8)

    assert named(labels, {0: "A"}, np.array([False, False]), "raw").empty


def test_named_raises_on_a_label_the_state_map_does_not_carry() -> None:
    labels = np.array([7], dtype=np.int8)

    with pytest.raises(KeyError):
        named(labels, {0: "A"}, np.array([True]), "raw")


# -- the row normalisation --------------------------------------------------------------------


def frames(raw: list[str], fitted: list[str]) -> tuple[pd.Series, pd.Series]:
    """One bar per element, labelled twice."""
    return pd.Series(raw, name="raw"), pd.Series(fitted, name="fitted")


def test_each_raw_state_is_normalised_to_a_hundred_rather_than_to_the_whole_grid() -> None:
    """The claim is "where this state's bars went", so the row is the denominator."""
    raw, fitted = frames(["THIN"] * 4 + ["HEAVY"], ["THIN", "THIN", "THIN", "NORMAL", "HEAVY"])
    table = confusion(raw, fitted, VOLUME_ORDER)

    assert table.loc["THIN", "THIN"] == pytest.approx(75.0)
    assert table.loc["THIN", "NORMAL"] == pytest.approx(25.0)
    assert table.loc["HEAVY", "HEAVY"] == pytest.approx(100.0)


def test_a_state_no_bar_carries_is_a_row_of_nan_rather_than_a_missing_row() -> None:
    """Reindexing on the stated order, so two tables stay comparable cell by cell."""
    raw, fitted = frames(["THIN", "THIN"], ["THIN", "NORMAL"])
    table = confusion(raw, fitted, VOLUME_ORDER)

    assert list(table.index) == list(VOLUME_ORDER)
    assert list(table.columns) == list(VOLUME_ORDER)
    assert table.loc["HEAVY"].isna().all()


def test_an_unchanged_cut_is_the_identity() -> None:
    raw, fitted = frames(["THIN", "NORMAL", "HEAVY"], ["THIN", "NORMAL", "HEAVY"])
    table = confusion(raw, fitted, VOLUME_ORDER).fillna(0.0)

    assert np.allclose(table.to_numpy(), np.diag([100.0, 100.0, 100.0]))


# -- the three forms a form comparison reads --------------------------------------------------


def test_one_series_per_form_at_the_windows_the_campaign_swept() -> None:
    """`form_rows` compares these against each other, so a missing form is a missing table."""
    series = volume_series()

    assert [key.form for key in series] == list(volume.VolumeForm)
    assert {key.baseline_sessions for key in series} == {VOLUME_BASELINE_SESSIONS}


def test_the_rolling_window_is_dropped_from_every_form_that_does_not_read_it() -> None:
    """`volume.key`'s own rule, pinned here because two equal keys must not label twice."""
    rolling = [key for key in volume_series() if key.form is volume.VolumeForm.ROLLING]

    assert [key.rolling_bars for key in rolling] == [VOLUME_ROLLING_BARS]
    assert len(set(volume_series())) == len(volume.VolumeForm)
