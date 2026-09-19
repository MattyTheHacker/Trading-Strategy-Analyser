"""The flatten-cutoff ladder read: what a rung is paired against, and what says it fired.

Every function under test is pure, so none of this needs a database or a simulation. What is
worth pinning is the three things the §M41 conclusion rests on -- that a rung pairs against the
control configuration by configuration rather than across a cell, that a cutoff which cannot
reach past the last bar is reported as never having bound rather than as a cutoff that did
nothing, and that the control's disagreement with the stored rows is counted rather than
swallowed.
"""

from __future__ import annotations

import pandas as pd
import pytest

import tools.campaign_flatten as module
from nqbt import archetypes, sessions
from tests.test_campaign_shortlist import synthetic_bars
from tools.campaign_flatten import (
    CONTROL,
    CUTOFF,
    CUTOFFS,
    SWEPT_BARS,
    bars_for,
    ladder,
    last_swept,
    measure,
    on_swept_bars,
    reconcile,
    resolutions_for,
    rung,
    shortlisted,
)
from tools.campaign_holdout import JOIN_KEYS


def arm(seconds: int, **columns: object) -> pd.DataFrame:
    """A measured frame with the tag columns every rung carries."""
    base = {
        "root": "MNQ",
        "resolution": 5,
        "variant": "trailing",
        "stratum": "phase=MIDDAY",
        "window": "holdout",
        "sweep_id": 1,
        "combo_id": range(4),
        CUTOFF: seconds,
        "trades": [100, 200, 300, 400],
        "profit_factor": [0.8, 0.9, 1.1, 1.2],
        "net_pnl": [-10.0, -5.0, 5.0, 10.0],
        "max_drawdown": [100.0, 100.0, 100.0, 100.0],
        "session_close_share": [0.5, 0.5, 0.5, 0.5],
        "avg_bars_held": [30.0, 30.0, 30.0, 30.0],
        "stored_trades": [100, 200, 300, 400],
        "stored_net_pnl": [-10.0, -5.0, 5.0, 10.0],
        SWEPT_BARS: True,
    }

    return pd.DataFrame({**base, **columns})


# -- the ladder's shape --------------------------------------------------------------------


def test_the_control_rung_is_the_simulations_one_default_and_is_in_the_ladder() -> None:
    """The ladder is read against what every stored row was swept at, so it has to be run."""
    assert CONTROL == sessions.EXIT_ON_CLOSE_SECONDS
    assert CONTROL in CUTOFFS
    assert len(set(CUTOFFS)) == len(CUTOFFS)


def test_a_rung_pairs_configuration_by_configuration_and_not_across_the_cell() -> None:
    """Two configurations are two strategies; pooling them would report neither's difference.

    The first two gain 0.1 and the last two lose 0.4, so a cell-level median would report a
    loss on four pairs rather than two gains and two losses.
    """
    control = arm(CONTROL)
    treatment = arm(180, profit_factor=[0.9, 1.0, 0.7, 0.8])
    table = rung(pd.concat([control, treatment], ignore_index=True), 180, "profit_factor")

    assert len(table) == 1
    assert table["pairs"].iloc[0] == 4
    assert table["improved"].iloc[0] == 2


def test_a_cutoff_that_cannot_reach_past_the_last_bar_reads_as_never_having_bound() -> None:
    """The check that separates "the cutoff did nothing" from "the cutoff never fired"."""
    rows = pd.concat([arm(CONTROL), arm(180)], ignore_index=True)
    table = rung(rows, 180, "profit_factor")

    assert table["moved"].iloc[0] == 0.0
    assert table["delta"].iloc[0] == 0.0
    assert table["net_delta"].iloc[0] == 0.0


def test_a_cutoff_that_moves_the_book_reads_as_having_bound() -> None:
    rows = pd.concat(
        [arm(CONTROL), arm(300, net_pnl=[-10.0, -5.0, 5.0, 40.0])],
        ignore_index=True,
    )
    table = rung(rows, 300, "profit_factor")

    assert table["moved"].iloc[0] == 0.25
    assert table["net_delta"].iloc[0] == 0.0, "a median over four pairs, three of which held"


def test_the_close_share_the_rung_reports_is_the_treatments_and_the_delta_is_the_move() -> None:
    """A later cutoff flattens more legs, and the two columns have to say so separately."""
    rows = pd.concat([arm(CONTROL), arm(300, session_close_share=[0.6] * 4)], ignore_index=True)
    table = rung(rows, 300, "profit_factor")

    assert table["close_share"].iloc[0] == pytest.approx(0.6)
    assert table["close_share_delta"].iloc[0] == pytest.approx(0.1)


def test_a_cutoff_nothing_was_run_at_is_empty_rather_than_an_error() -> None:
    rows = pd.concat([arm(CONTROL), arm(180)], ignore_index=True)

    assert rung(rows, 300, "profit_factor").empty


def test_a_ladder_with_nothing_but_the_control_says_so_rather_than_returning_nothing() -> None:
    with pytest.raises(SystemExit, match="only one rung"):
        ladder(arm(CONTROL), "profit_factor")


def test_the_ladder_stacks_every_rung_above_the_control_in_order() -> None:
    rows = pd.concat([arm(CONTROL), arm(900), arm(180)], ignore_index=True)
    table = ladder(rows, "profit_factor")

    assert list(table[CUTOFF]) == [180, 900]


# -- reconciling the control against what the sweep stored ---------------------------------


def test_a_control_reproducing_its_stored_rows_reconciles_on_both_figures() -> None:
    table = reconcile(pd.concat([arm(CONTROL), arm(180)], ignore_index=True))

    assert table["rows"].iloc[0] == 4
    assert bool(table[SWEPT_BARS].iloc[0]) is True
    assert table["same_trades"].iloc[0] == 4
    assert table["same_net"].iloc[0] == 4
    assert table["net_gap"].iloc[0] == 0.0


def test_a_control_that_no_longer_reproduces_is_counted_rather_than_raised() -> None:
    """The weakening this campaign rests on: an archive that has moved under a stored row makes
    the *levels* this run's, and the ladder's differences are still the cutoff's."""
    drifted = arm(CONTROL, net_pnl=[-10.0, -5.0, 5.0, 133.0])
    table = reconcile(pd.concat([drifted, arm(180)], ignore_index=True))

    assert table["same_trades"].iloc[0] == 4
    assert table["same_net"].iloc[0] == 3
    assert table["net_gap"].iloc[0] == pytest.approx(123.0)


def test_a_cell_read_off_bars_it_was_not_swept_on_says_so() -> None:
    """The archive gaining history earlier than its tail moves the 60/40 split, and a cell read
    off the window that produces is this run's rather than the registry's."""
    rows = pd.concat([arm(CONTROL, **{SWEPT_BARS: False}), arm(180)], ignore_index=True)

    assert bool(reconcile(rows)[SWEPT_BARS].iloc[0]) is False


def test_only_the_control_rung_is_reconciled() -> None:
    """A treatment rung is *meant* to differ from the stored row, so counting it would report
    the measurement as a failure to reproduce."""
    rows = pd.concat([arm(CONTROL), arm(300, net_pnl=[0.0] * 4)], ignore_index=True)
    table = reconcile(rows)

    assert len(table) == 1
    assert table["same_net"].iloc[0] == 4


# -- which rows a run measures -------------------------------------------------------------


def test_the_resolutions_are_read_off_the_stored_cell_rather_than_assumed(monkeypatch) -> None:
    frame = pd.DataFrame(
        {
            "root": ["MNQ", "MNQ", "MNQ", "NQ"],
            "stratum": ["phase=MIDDAY", "phase=MIDDAY", "unfiltered", "phase=MIDDAY"],
            "variant": ["trailing"] * 4,
            "resolution": [15, 5, 1, 2],
        },
    )
    monkeypatch.setattr(module, "load", lambda name, windows: frame)

    assert resolutions_for("InsideBarTrailing", "MNQ", "phase=MIDDAY", "trailing") == [5, 15]
    assert resolutions_for("InsideBarTrailing", "MNQ", None, "trailing") == [1, 5, 15]


def test_a_shortlist_is_taken_inside_each_bar_size_rather_than_pooled(monkeypatch) -> None:
    """Bar size is the largest lever in the campaign, so a pooled shortlist would rank it."""
    asked: list[int | None] = []

    def fake(name, root, by, top, stratum, resolution, variant):  # noqa: ANN001, ANN202, PLR0913
        asked.append(resolution)

        return pd.DataFrame({"resolution": [resolution]})

    monkeypatch.setattr(module, "held_out", fake)
    args = argparse_namespace(resolution=[5, 15])
    rows = shortlisted(args, "InsideBarTrailing", "MNQ")

    assert asked == [5, 15]
    assert list(rows["resolution"]) == [5, 15]


def test_a_cell_nothing_was_stored_for_says_so_rather_than_measuring_nothing(monkeypatch) -> None:
    empty = pd.DataFrame({"root": [], "stratum": [], "variant": [], "resolution": []})
    monkeypatch.setattr(module, "load", lambda name, windows: empty)
    with pytest.raises(SystemExit, match="no stored holdout rows"):
        shortlisted(argparse_namespace(resolution=None), "InsideBarTrailing", "MNQ")


def argparse_namespace(**overrides: object):  # noqa: ANN201 - argparse's own namespace type
    """The subset of ``main``'s parsed arguments the selection helpers read."""
    import argparse

    base = {
        "by": "profit_factor",
        "top": 20,
        "stratum": "phase=MIDDAY",
        "variant": "trailing",
        "resolution": None,
    }

    return argparse.Namespace(**{**base, **overrides})


# -- which bars a rung runs on -------------------------------------------------------------


def stored_frame(bars: pd.DataFrame, first: int, last: int) -> pd.DataFrame:
    """A stored-rows frame keyed the way ``campaign_null.stored_rows`` keys one."""
    frame = pd.DataFrame(
        [
            {
                "root": "MNQ",
                "resolution": 5,
                "variant": "bracket",
                "stratum": "unfiltered",
                "combo_id": 0,
                "sweep_id": 1,
                "trades": 0,
                "net_pnl": 0.0,
                "first_bar": bars.index[first].tz_localize(None),
                "last_bar": bars.index[last].tz_localize(None),
            },
        ],
    )

    return frame.set_index(JOIN_KEYS, drop=False)


def stored_row() -> pd.DataFrame:
    """The one shortlisted row those stored bars belong to."""
    return pd.DataFrame(
        [
            {
                "root": "MNQ",
                "resolution": 5,
                "variant": "bracket",
                "stratum": "unfiltered",
                "window": "holdout",
                "sweep_id": 1,
                "combo_id": 0,
                "trades": 0,
                "net_pnl": 0.0,
                "atr_multiplier": 5.0,
            },
        ],
    )


def test_the_stored_stamp_is_read_back_into_the_archives_own_zone() -> None:
    """``save_sweep`` stores it naive and the spliced series is tz-aware, so a bare compare
    would raise rather than cut."""
    bars = synthetic_bars(n=200)
    stored = stored_frame(bars, 0, 150)

    assert last_swept(stored, bars) == bars.index[150]


def test_a_cell_is_run_on_the_window_its_rows_were_swept_on_where_that_survives() -> None:
    bars = synthetic_bars(n=3000)
    holdout = module.source(bars, module.HELD_OUT)
    frame = module.resample.resample(holdout, 5)
    stored = stored_frame(frame, 0, len(frame) - 1)
    chosen, swept = bars_for((bars,), stored, stored_row(), 5)

    assert swept is True
    assert chosen.index[0] == frame.index[0]
    assert chosen.index[-1] == frame.index[-1]


def test_a_window_no_truncation_recovers_falls_back_and_says_so() -> None:
    """NQ gained history earlier than its tail, so its 60/40 split moved and nothing recovers
    it -- the run still happens and the cell is reported as not being on the swept bars."""
    bars = synthetic_bars(n=3000)
    stored = stored_frame(bars, 0, 10)
    chosen, swept = bars_for((bars,), stored, stored_row(), 5)

    assert swept is False
    assert len(chosen) > 0


def test_a_row_with_no_stored_counterpart_is_not_counted_as_agreeing() -> None:
    """A check that could not run is not a check that passed."""
    bars = module.resample.resample(synthetic_bars(n=3000), 5)
    stored = stored_frame(bars, 0, len(bars) - 1)
    other = stored_row()
    other.loc[0, "combo_id"] = 99

    assert on_swept_bars(stored, other, bars) is False


# -- the measured rows ----------------------------------------------------------------------


def test_every_configuration_is_measured_once_per_cutoff_and_carries_which(monkeypatch) -> None:
    """The plumbing the ladder reads: one row per (configuration, cutoff), tagged with the
    cutoff it was run at and with what the sweep stored for it."""
    bars = synthetic_bars(n=6000)
    monkeypatch.setattr(module.splice, "load_continuous", lambda root: bars)
    frame = module.resample.resample(module.source(bars, module.HELD_OUT), 5)
    monkeypatch.setattr(
        module,
        "stored_rows",
        lambda name, root, window: stored_frame(frame, 0, len(frame) - 1),
    )
    table = measure(stored_row(), archetypes.INSIDEBAR, "MNQ", (CONTROL, 900))

    assert list(table[CUTOFF]) == [CONTROL, 900]
    assert list(table[SWEPT_BARS]) == [True, True]
    assert list(table["stored_trades"]) == [0, 0]
    assert set(module.REPORTED) <= set(table.columns)


# -- the command line -----------------------------------------------------------------------


def test_a_ladder_without_the_control_rung_is_refused_before_anything_runs(monkeypatch) -> None:
    """Every rung is read against the control, so a run without it measures nothing."""
    monkeypatch.setattr(module, "cell", lambda *_: pd.DataFrame())
    with pytest.raises(SystemExit, match="has to include the control rung"):
        module.main(["campaign_flatten.py", "--strategy", "InsideBar", "--seconds", "180", "300"])


def test_a_run_prints_the_reconciliation_before_the_ladder(monkeypatch) -> None:
    """The reconciliation is part of the reading rather than a footnote, so it comes first."""
    shown: list[str] = []
    measured = pd.concat([arm(CONTROL), arm(900)], ignore_index=True)
    monkeypatch.setattr(module, "cell", lambda *_: measured)
    monkeypatch.setattr(module, "show", lambda title, frame: shown.append(title))

    assert module.main(["campaign_flatten.py", "--strategy", "InsideBarTrailing"]) == 0
    assert [title.split(" ")[1] for title in shown] == ["30s", "flatten"]
