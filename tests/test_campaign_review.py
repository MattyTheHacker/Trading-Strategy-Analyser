"""Reading a shortlisted configuration's own trades by the clock, and guarding what that shows.

Two claims are pinned harder than the rest, because each would produce a confident table rather
than an error. **Both forms of volume travel with the clock**, since relative volume cannot say
whether there was anything there to trade and absolute volume cannot say whether an hour was
unusual -- and the campaign asked only the first. **The family screened is the one that was
looked at**: the clock and the three volume labels, not every gate the dataset happens to hold,
because a family-wise null diluted with conditions nobody asked about is not the null for the
question that was asked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import annotate, context, guard, results, review, sessions, timeofday, trades, volume
from tools import campaign_review
from tools.campaign_review import (
    BY,
    SLIPPAGE_TOLERANCE,
    VOLUME_STATE_PREFIX,
    conditions_of,
    labelled,
    main,
    review_row,
    review_spec,
    thresholds_for,
    tolerance_for,
    volume_keys,
)
from tools.campaign_sweep import VOLUME_BASELINE_SESSIONS, VOLUME_ROLLING_BARS

BASE = 18000.0
SESSIONS = 26
"""Enough sessions for a 20-session volume baseline to exist, which is what the tool reads."""

MINUTES = 480
"""One-minute bars from 09:00 ET, which reaches the pre-open through to the session close."""

SWEEP_ID = 12
COMBO_ID = 340
THIN = 0.7
HEAVY = 1.5


def bars() -> pd.DataFrame:
    """``MINUTES`` one-minute bars from 09:00 ET on each of ``SESSIONS`` weekdays."""
    days = pd.bdate_range("2024-01-02", periods=SESSIONS)
    stamps = [pd.date_range(f"{day:%Y-%m-%d} 14:00", periods=MINUTES, freq="min", tz="UTC") for day in days]
    index = stamps[0].append(stamps[1:])

    count = len(index)
    rng = np.random.default_rng(11)
    close = BASE + 0.25 * np.cumsum(np.where((np.arange(count) // 20) % 2 == 0, 1.0, -1.0))
    opened = np.concatenate(([close[0]], close[:-1]))
    frame = pd.DataFrame(
        {
            "open": opened,
            "high": np.maximum(opened, close) + 1.0,
            "low": np.minimum(opened, close) - 1.0,
            "close": close,
            "volume": rng.integers(50, 500, count).astype(np.float64),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


@pytest.fixture(scope="module")
def data() -> context.Dataset:
    """The bars a stored log would have been simulated over, with the clock and all three forms."""
    return context.prepare(bars(), review_spec(), bar_minutes=1)


def entry_bars(data: context.Dataset, per_phase: int = 60) -> np.ndarray:  # type: ignore[type-arg]  # a bar index array
    """``per_phase`` labelled bars from each session phase, so every phase clears the floor."""
    phases = data.phase_values()
    labelled_volume = np.isfinite(data.relative_volume(volume_keys()[0]))
    chosen: list[int] = []
    for phase in sorted(set(phases.tolist()) - {-1}):
        at = np.flatnonzero((phases == phase) & labelled_volume)
        chosen.extend(at[-per_phase:].tolist())

    return np.array(sorted(chosen), dtype=np.int64)


def trade_log(data: context.Dataset, seed: int = 5) -> pd.DataFrame:
    """A one-leg-per-trade log entered on those bars, in the shape ``save_trades`` stores.

    Prices are the bars' own closes, which is what lets the annotation's price check pass with
    no tolerance -- a fill outside its bar is how a back-adjusted series announces itself.
    """
    at = entry_bars(data)
    out = np.minimum(at + 3, len(data) - 1)
    rng = np.random.default_rng(seed)
    pnl = rng.normal(4.0, 50.0, at.size)

    return pd.DataFrame(
        {
            "source": "sim",
            "instrument": "MNQ",
            "trade_id": np.arange(1, at.size + 1, dtype=np.int64),
            "leg": 1,
            "entry_bar": at,
            "exit_bar": out,
            "entry_time": data.index[at],
            "exit_time": data.index[out],
            "entry_price": data.close[at],
            "exit_price": data.close[out],
            "direction": trades.LONG,
            "quantity": 1,
            "exit_reason": np.where(pnl > 0.0, "target", "stop"),
            "gross_pnl": pnl + 1.5,
            "commission": 1.5,
            "net_pnl": pnl,
            "r_multiple": pnl / 50.0,
            "risk_points": 10.0,
            "mae_points": 1.0,
            "mfe_points": 2.0,
            "bars_held": out - at,
            "ambiguous_bar": False,
        },
    )


def stored_row(**columns: object) -> pd.Series:  # type: ignore[type-arg]  # duckdb's dtypes
    """One ranked row, carrying the tags and the cut the configuration was measured at."""
    base: dict[str, object] = {
        "sweep_id": SWEEP_ID,
        "combo_id": COMBO_ID,
        "root": "MNQ",
        "resolution": 1,
        "variant": "bracket",
        "stratum": "unfiltered",
        "window": "full",
        "slippage_ticks": 0.0,
        "volume_thin_below": THIN,
        "volume_heavy_above": HEAVY,
        "profit_factor": 1.1,
    }

    return pd.Series({**base, **columns})


@pytest.fixture
def stocked(tmp_path, data):
    """A database holding one stored log, at the ids the ranked row names."""
    db = tmp_path / "InsideBar.duckdb"
    results.save_trades(trade_log(data), SWEEP_ID, COMBO_ID, db)

    return db


def annotation_of(data: context.Dataset) -> annotate.Annotation:
    """The annotation the tool builds, for the tests that do not need the whole report."""
    return annotate.annotate_trades(
        trade_log(data),
        data,
        thresholds=annotate.LabelThresholds(volume_thin_below=THIN, volume_heavy_above=HEAVY),
    )


# -- the clock, and what has to travel with it ---------------------------------------------


def test_the_clock_carries_both_forms_of_volume_for_every_form_the_campaign_did_not_sweep(
    stocked,
    data,
) -> None:
    """§M27 swept the per-bar form alone. Absolute volume is the execution question no relative
    measure can answer, and the pair is what separates an always-busy hour from an unusual one."""
    clock = review_row(stored_row(), data, stocked, "MNQ", 50)
    for key in volume_keys():
        suffix = volume.describe_key(key)
        assert f"median_entry_volume_{suffix}" in clock.columns
        assert f"median_entry_relative_volume_{suffix}" in clock.columns


def test_the_clock_carries_the_forced_exit_share_beside_every_phase(stocked, data) -> None:
    """A phase table without it will be read as a finding and be the clock -- §M10.4."""
    clock = review_row(stored_row(), data, stocked, "MNQ", 50)
    assert "session_close_share" in clock.columns
    assert clock["session_close_share"].notna().any()


def test_the_clock_is_in_session_order_rather_than_alphabetical(stocked, data) -> None:
    """Alphabetical ordering passes every other assertion here and reads as a different day."""
    position = {phase.name.lower(): int(phase) for phase in timeofday.SessionPhase}
    clock = review_row(stored_row(), data, stocked, "MNQ", 50)
    order = [str(value) for value in clock[review.PHASE_COLUMN]]
    assert order == sorted(order, key=lambda name: position[name])


# -- the family that is screened -----------------------------------------------------------


def test_the_family_is_the_clock_and_one_label_per_volume_form(data) -> None:
    named = conditions_of(annotation_of(data))
    assert named[0] == review.PHASE_COLUMN
    assert len(named) == 1 + len(volume.VolumeForm)
    assert all(name.startswith(VOLUME_STATE_PREFIX) for name in named[1:])


def test_a_gate_nobody_asked_about_is_not_in_the_family(data) -> None:
    """Every stratifiable condition would dilute the family-wise null with questions the
    campaign never put -- :data:`nqbt.guard.FAMILY_COLUMN`."""
    annotation = annotation_of(data)
    assert set(conditions_of(annotation)) < set(annotation.conditions)
    assert not any(name.startswith("above_") for name in conditions_of(annotation))


def test_the_separation_is_measured_in_a_statistic_a_guard_accepts() -> None:
    """``profit_factor`` is unbounded above and ``net_pnl`` separates strata by their size."""
    assert BY in guard.STATISTICS


# -- the cut the review states -------------------------------------------------------------


def test_the_review_cuts_at_the_thresholds_the_configuration_was_measured_with(data) -> None:
    """Where to cut a raw series is the review's most consequential choice, and the stored row
    is the only answer that describes the rows being read."""
    cut = thresholds_for(stored_row(volume_thin_below=0.5, volume_heavy_above=2.0))
    assert (cut.volume_thin_below, cut.volume_heavy_above) == (0.5, 2.0)
    assert cut.labels_volume


def test_the_three_series_are_the_three_forms_at_the_campaigns_own_window() -> None:
    keys = volume_keys()
    assert {key.form for key in keys} == set(volume.VolumeForm)
    assert {key.baseline_sessions for key in keys} == {VOLUME_BASELINE_SESSIONS}
    rolling = next(key for key in keys if key.form is volume.VolumeForm.ROLLING)
    assert rolling.rolling_bars == VOLUME_ROLLING_BARS


# -- how far a fill may land outside its bar ------------------------------------------------


def test_the_tolerance_is_the_runs_own_slippage_unless_it_is_overridden() -> None:
    """MNQ ticks at 0.25, so one tick of slippage is a quarter point of latitude."""
    assert tolerance_for(stored_row(slippage_ticks=1.0), "MNQ", SLIPPAGE_TOLERANCE) == pytest.approx(0.25)
    assert tolerance_for(stored_row(slippage_ticks=1.0), "MNQ", 20.0) == pytest.approx(20.0)


def test_a_log_whose_fill_lands_outside_its_bar_is_named_and_skipped(tmp_path, data) -> None:
    """A simulated target that its bar gapped through fills at the target price, which is
    further out than any slippage -- ``docs/roadmap.md`` §M27.7. Refusing the whole shortlist
    over one such configuration would report nothing at all."""
    log = trade_log(data)
    log.loc[0, "exit_price"] = float(log.loc[0, "exit_price"]) + 40.0
    db = tmp_path / "InsideBar.duckdb"
    results.save_trades(log, SWEEP_ID, COMBO_ID, db)

    assert review_row(stored_row(), data, db, "MNQ", 50).empty


def test_a_widened_tolerance_admits_the_fill_the_default_refuses(tmp_path, data) -> None:
    """And the widening is a choice the caller makes and the report prints, never a default."""
    log = trade_log(data)
    log.loc[0, "exit_price"] = float(log.loc[0, "exit_price"]) + 40.0
    db = tmp_path / "InsideBar.duckdb"
    results.save_trades(log, SWEEP_ID, COMBO_ID, db)

    assert not review_row(stored_row(), data, db, "MNQ", 50, 50.0).empty


# -- attribution and absence ---------------------------------------------------------------


def test_every_clock_row_names_the_configuration_it_came_from(stocked, data) -> None:
    """One report holds several configurations' tables, so a row that does not say which is a
    number attributed by position."""
    clock = review_row(stored_row(), data, stocked, "MNQ", 50)
    assert set(clock["combo_id"]) == {COMBO_ID}
    assert set(clock["stratum"]) == {"unfiltered"}
    assert "profit_factor" not in labelled(stored_row()), "a statistic is not a tag"


def test_a_row_with_no_stored_log_is_named_and_skipped(stocked, data) -> None:
    """A shortlist quietly reviewing four of its twenty reads exactly like one reviewing all."""
    assert review_row(stored_row(combo_id=999), data, stocked, "MNQ", 50).empty


def test_a_database_that_was_never_given_a_shortlist_yields_nothing(tmp_path, data) -> None:
    """``trades`` is created lazily, so before ``campaign_shortlist.py`` runs there is no table."""
    empty = tmp_path / "InsideBar.duckdb"
    results.query("SELECT 1", empty)
    assert review_row(stored_row(), data, empty, "MNQ", 50).empty


# -- the report over a whole shortlist ------------------------------------------------------


def run_main(monkeypatch, rows: pd.DataFrame, db, frame: pd.DataFrame) -> int:
    monkeypatch.setattr(campaign_review, "shortlist", lambda *_: rows)
    monkeypatch.setattr(campaign_review, "db_path", lambda _: db)
    monkeypatch.setattr(campaign_review, "source", lambda bars, _window: bars)
    monkeypatch.setattr(campaign_review.splice, "load_continuous", lambda _root: frame)
    monkeypatch.setattr(campaign_review.resample, "resample", lambda bars, _minutes: bars)

    return main(["campaign_review.py", "--strategy", "InsideBar", "--iterations", "50"])


def test_a_shortlist_with_a_stored_log_reports_and_succeeds(monkeypatch, stocked) -> None:
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), stocked, bars()) == 0


def test_a_shortlist_with_no_stored_logs_fails_rather_than_printing_an_empty_table(
    monkeypatch,
    tmp_path,
) -> None:
    """An empty report is indistinguishable from a configuration with nothing to say."""
    db = tmp_path / "InsideBar.duckdb"
    assert run_main(monkeypatch, pd.DataFrame([stored_row()]), db, bars()) == 1


def test_the_rows_that_do_have_logs_are_still_reviewed(monkeypatch, stocked) -> None:
    """One missing log must not cost the others their tables."""
    rows = pd.DataFrame([stored_row(), stored_row(combo_id=999)])
    assert run_main(monkeypatch, rows, stocked, bars()) == 0
