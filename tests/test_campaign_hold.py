"""The maximum-hold-time ladder read: what a rung is paired against, and what says it fired.

Every function under test is pure, so none of this needs a database. What is worth pinning is
the two things the §M29 conclusion rests on -- that a rung pairs inside its own base variant
rather than across all of them, and that an arm which cannot bind is reported as not having
bound rather than as a cap that did nothing.
"""

from __future__ import annotations

import pandas as pd
import pytest

import tools.campaign_hold as module
from tools.campaign_hold import (
    BASE_VARIANT,
    CONTROL_BARS,
    bound_share,
    held,
    ladder,
    rung,
)
from tools.campaign_sweep import HOLD_BARS


def arm(variant: str, bars: int, **columns: object) -> pd.DataFrame:
    """A results frame with the tag columns every stored row carries."""
    base = {
        "sweep_id": 1,
        "combo_id": range(4),
        "variant": f"{variant} hold={bars}",
        "max_hold_bars": bars,
        "stratum": "unfiltered",
        "window": "holdout",
        "strategy": "EmaCrossover",
        "resolution": 5,
        "contract": None,
        "tier2": "tier-1-only",
        "root": "MNQ",
        "fast_period": [9, 9, 20, 20],
        "profit_factor": [0.8, 0.9, 1.1, 1.2],
        "avg_bars_held": [30.0, 30.0, 30.0, 30.0],
        "trades": [100, 200, 300, 400],
        "net_pnl": [-10.0, -5.0, 5.0, 10.0],
    }
    frame = pd.DataFrame({**base, **columns})
    frame[BASE_VARIANT] = variant

    return frame


# -- the ladder's shape --------------------------------------------------------------------


def test_the_control_rung_is_zero_and_the_ladder_never_pairs_it_against_itself() -> None:
    assert CONTROL_BARS == 0
    assert CONTROL_BARS in HOLD_BARS, "the uncapped arm has to be run for anything to pair against"
    assert len(set(HOLD_BARS)) == len(HOLD_BARS)


def test_a_rung_pairs_inside_its_own_base_variant_and_not_across_them() -> None:
    """Two arms of the same archetype are different strategies; pooling them invents cells.

    Pooled, the same rows give two pairs and zero improved rather than four and two, because
    each cell would hold one row of each arm. Two mechanisms keep them apart and either is
    enough -- the explicit cell key, and ``shared_columns`` deriving the same column.
    """
    control = pd.concat([arm("stop=atr", 0), arm("stop=swing", 0)], ignore_index=True)
    treatment = pd.concat(
        [
            arm("stop=atr", 20, profit_factor=[0.9, 1.0, 1.2, 1.3]),
            arm("stop=swing", 20, profit_factor=[0.5, 0.6, 0.7, 0.8]),
        ],
        ignore_index=True,
    )
    rows = pd.concat([control, treatment], ignore_index=True)
    table = rung(rows, 20, "profit_factor")

    # One root x resolution, and both base variants' cells inside it: the ATR arm gained
    # 0.1 on every cell and the swing arm lost 0.4, so a pooled read would report neither.
    assert len(table) == 1
    assert table["pairs"].iloc[0] == 4
    assert table["improved"].iloc[0] == 2


def test_the_rung_carries_the_minutes_its_bar_count_means_at_this_resolution() -> None:
    """The cap is a bar count, so the ladder is unreadable without the resolution beside it."""
    rows = pd.concat([arm("stop=atr", 0), arm("stop=atr", 20)], ignore_index=True)
    table = rung(rows, 20, "profit_factor")
    assert table["hold_bars"].iloc[0] == 20
    assert table["hold_minutes"].iloc[0] == 100  # 20 bars of 5 minutes


# -- whether the rung fired at all ---------------------------------------------------------


def test_a_cap_longer_than_the_hold_is_reported_as_never_having_bound() -> None:
    """The check that separates "the cap did nothing" from "the cap never fired"."""
    control = arm("stop=atr", 0)
    treatment = arm("stop=atr", 80)  # identical rows: the position never lived that long
    table = rung(pd.concat([control, treatment], ignore_index=True), 80, "profit_factor")
    assert table["bound"].iloc[0] == 0.0
    assert table["delta"].iloc[0] == 0.0


def test_a_cap_that_shortens_the_hold_is_reported_as_having_bound() -> None:
    control = arm("stop=atr", 0)
    treatment = arm("stop=atr", 5, avg_bars_held=[6.0, 6.0, 6.0, 6.0])
    table = rung(pd.concat([control, treatment], ignore_index=True), 5, "profit_factor")
    assert table["bound"].iloc[0] == 1.0


def test_bound_share_is_a_share_of_cells_rather_than_a_pooled_median() -> None:
    """Half the cells binding and half not must read 0.5, not "the median moved"."""
    control = arm("stop=atr", 0)
    treatment = arm("stop=atr", 5, avg_bars_held=[6.0, 6.0, 30.0, 30.0])
    keys = ["root", "resolution", "stratum", BASE_VARIANT, "fast_period"]
    fired = bound_share(control, treatment, keys)
    assert fired["bound"].mean() == 0.5


# -- the guards ----------------------------------------------------------------------------


def test_a_rung_nothing_was_run_at_is_empty_rather_than_an_error() -> None:
    rows = pd.concat([arm("stop=atr", 0), arm("stop=atr", 5)], ignore_index=True)
    assert rung(rows, 40, "profit_factor").empty


def test_reading_an_archetype_that_was_never_swept_says_so(monkeypatch) -> None:
    monkeypatch.setattr(module, "held", lambda name, windows: pd.DataFrame())
    with pytest.raises(SystemExit, match="no --variants hold rows"):
        ladder("DeadCatBounce", ["holdout"], "profit_factor")


def test_held_strips_the_rung_token_so_the_base_variant_survives_it(monkeypatch) -> None:
    frame = pd.DataFrame(
        {
            "variant": ["stop=atr hold=0", "stop=atr hold=80", "window=5m stop=opposite hold=5"],
            "trades": [100, 100, 100],
        },
    )
    monkeypatch.setattr(module, "load", lambda name, windows: frame)
    rows = held("EmaCrossover", ["holdout"])

    assert list(rows[BASE_VARIANT]) == ["stop=atr", "stop=atr", "window=5m stop=opposite"]
