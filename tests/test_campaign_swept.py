"""Re-running a stored shortlist on the bars it was swept on, and saying how far it reproduced.

Three claims carry this module. **A window is recovered by cutting the archive back or it is not
recovered at all**, and which of the two happened has to reach the caller rather than being
assumed either way. **A re-run is read back against the rows it came from and not refused by
them**, because the archive moving under a campaign is what makes the re-run necessary. And **a
reconciliation is per bar size**, since one figure spanning two of them would hide a root that
reproduced at one and not the other.

The helpers here are shared with ``tests/test_campaign_flatten.py``, which measures the same
bars through the flatten ladder.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nqbt import archetypes, resample
from tests.test_campaign_shortlist import synthetic_bars
from tools import campaign_swept as module
from tools.campaign_holdout import JOIN_KEYS
from tools.campaign_shortlist import source
from tools.campaign_swept import (
    CELL_KEYS,
    HELD_OUT,
    SWEPT_BARS,
    bars_for,
    candidate_bars,
    last_swept,
    logs_for,
    on_swept_bars,
    reconciliation,
    stored_figures,
)


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


def measured(**columns: object) -> pd.DataFrame:
    """A frame of the shape :func:`reconciliation` reads, reproducing its stored rows exactly."""
    base = {
        "root": "MNQ",
        "resolution": 5,
        "trades": [100, 200],
        "net_pnl": [-10.0, 5.0],
        "stored_trades": [100, 200],
        "stored_net_pnl": [-10.0, 5.0],
        SWEPT_BARS: True,
    }

    return pd.DataFrame({**base, **columns})


# -- which bars a re-run lands on ------------------------------------------------------------


def test_the_stored_stamp_is_read_back_into_the_archives_own_zone() -> None:
    """``save_sweep`` stores it naive and the spliced series is tz-aware, so a bare compare
    would raise rather than cut."""
    bars = synthetic_bars(n=200)
    stored = stored_frame(bars, 0, 150)

    assert last_swept(stored, bars) == bars.index[150]


def test_the_archive_cut_back_is_tried_before_the_archive_as_it_stands() -> None:
    """The order is the whole behaviour: preferring today's bars would silently read a holdout
    the stored row never measured."""
    bars = synthetic_bars(n=200)
    cut, whole = candidate_bars(stored_frame(bars, 0, 150), bars)

    assert cut.index[-1] == bars.index[150]
    assert whole is bars


def test_a_cell_is_run_on_the_window_its_rows_were_swept_on_where_that_survives() -> None:
    bars = synthetic_bars(n=3000)
    frame = resample.resample(source(bars, HELD_OUT), 5)
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
    bars = resample.resample(synthetic_bars(n=3000), 5)
    stored = stored_frame(bars, 0, len(bars) - 1)
    other = stored_row()
    other.loc[0, "combo_id"] = 99

    assert on_swept_bars(stored, other, bars) is False


# -- reading a re-run back against what the sweep stored -------------------------------------


def test_a_re_run_that_reproduces_its_stored_rows_reconciles_on_both_figures() -> None:
    table = reconciliation(measured(), CELL_KEYS)

    assert table["rows"].iloc[0] == 2
    assert table["same_trades"].iloc[0] == 2
    assert table["same_net"].iloc[0] == 2
    assert table["net_gap"].iloc[0] == 0.0


def test_a_re_run_that_no_longer_reproduces_is_counted_rather_than_raised() -> None:
    """The weakening this module exists for: an archive that moved under a stored row makes the
    *levels* this run's, and refusing the run would leave a gate-4 read with no book at all."""
    table = reconciliation(measured(net_pnl=[-10.0, 68.0]), CELL_KEYS)

    assert table["same_trades"].iloc[0] == 2
    assert table["same_net"].iloc[0] == 1
    assert table["net_gap"].iloc[0] == pytest.approx(63.0)


def test_two_bar_sizes_are_never_pooled_into_one_reconciliation_row() -> None:
    """A root recovered at one resolution and not another is the case this has to show."""
    coarse = measured(resolution=15, **{SWEPT_BARS: False})
    table = reconciliation(pd.concat([measured(), coarse], ignore_index=True), CELL_KEYS)

    assert list(table["resolution"]) == [5, 15]
    assert list(table[SWEPT_BARS]) == [True, False]


def test_reconciling_nothing_is_empty_rather_than_a_group_by_on_missing_columns() -> None:
    assert reconciliation(pd.DataFrame(), CELL_KEYS).empty


def test_the_stored_figures_a_re_run_is_read_back_against_are_tagged_as_stored() -> None:
    """An untagged column would collide with the re-run's own and one of the two would win."""
    figures = stored_figures(stored_row().iloc[0])

    assert figures == {"stored_trades": 0, "stored_net_pnl": 0.0}


# -- the logs a gate-4 read works from -------------------------------------------------------


def test_every_configuration_gets_a_log_keyed_by_the_ids_its_row_carries(monkeypatch) -> None:
    """A log filed under the wrong key would attribute a whole decomposition to another
    configuration, which is the failure ``campaign_shortlist.verify`` exists to stop."""
    bars = synthetic_bars(n=6000)
    frame = resample.resample(source(bars, HELD_OUT), 5)
    monkeypatch.setattr(module.splice, "load_continuous", lambda root: bars)
    monkeypatch.setattr(
        module, "stored_rows", lambda name, root, window: stored_frame(frame, 0, len(frame) - 1)
    )
    logs, reconciled = logs_for(archetypes.INSIDEBAR.name, stored_row(), "MNQ")

    assert list(logs) == [(1, 0)]
    assert len(reconciled) == 1
    assert bool(reconciled[SWEPT_BARS].iloc[0]) is True
    assert set(reconciled.columns) >= {"rows", "same_trades", "same_net", "net_gap", SWEPT_BARS}


def test_a_cell_read_off_bars_it_was_not_swept_on_reaches_the_reconciliation(monkeypatch) -> None:
    bars = synthetic_bars(n=6000)
    monkeypatch.setattr(module.splice, "load_continuous", lambda root: bars)
    monkeypatch.setattr(module, "stored_rows", lambda name, root, window: stored_frame(bars, 0, 10))
    _, reconciled = logs_for(archetypes.INSIDEBAR.name, stored_row(), "MNQ")

    assert bool(reconciled[SWEPT_BARS].iloc[0]) is False
