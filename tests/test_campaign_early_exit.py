"""The conditional early exit's read: what an arm is paired against, what says it fired, and the verdict.

Every function under test but the database query is pure, so none of this needs a database. What
is worth pinning is what §M48's verdict rests on: an arm pairs inside its own base variant, an
arm that never fired is reported as unbound rather than as no effect, only a bound arm can be
the selection window's pick, and a cell clears only where the pick pays on every root.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pandas as pd
import pytest

import tools.campaign_early_exit as module
from tools.campaign_early_exit import (
    ARM,
    ARM_MARKER,
    ARM_SETS,
    CONTROL_ARM,
    EXIT_FIELD_PREFIXES,
    arm_table,
    clearing,
    exit_variants,
    exited,
    ladder,
    parse,
    picks,
    reproduced,
    reproduction,
    stored_twins,
    tagged,
)
from tools.campaign_hold import BASE_VARIANT
from tools.campaign_sweep import EARLY_EXIT, EARLY_EXIT_2, early_exit_arms, tier2_arms

if TYPE_CHECKING:
    from collections.abc import Sequence


def rows(base: str, arm: str, **columns: str | float | Sequence[float] | None) -> pd.DataFrame:
    """Build a results frame with the tag columns every stored row carries, under one arm's name."""
    frame = pd.DataFrame(
        {
            "sweep_id": 1,
            "combo_id": range(4),
            "variant": f"{base}{ARM_MARKER}{arm}" if arm else base,
            "stratum": "unfiltered",
            "window": "holdout",
            "strategy": "EmaCrossover",
            "resolution": 5,
            "contract": None,
            "tier2": "tier-1-only",
            "root": "MNQ",
            "fast_period": [9, 9, 20, 20],
            "slow_period": [30, 40, 30, 40],
            "profit_factor": [0.8, 0.9, 1.1, 1.2],
            "avg_bars_held": [30.0, 30.0, 30.0, 30.0],
            "trades": [100, 200, 300, 400],
            "commission_paid": [150.0, 300.0, 450.0, 600.0],
            "win_rate": [0.40, 0.45, 0.50, 0.55],
            "session_close_share": [0.30, 0.30, 0.30, 0.30],
            "net_pnl": [-10.0, -5.0, 5.0, 10.0],
        },
    )

    return frame.assign(**columns)


def both(*frames: pd.DataFrame) -> pd.DataFrame:
    """Stack frames and tag them, as :func:`exited` does."""
    return tagged(pd.concat(frames, ignore_index=True))


def table_row(arm: str, root: str, delta: float, p: float, bound: float, pairs: int = 4) -> dict[str, object]:
    """Build one row of an arm table for one 5-minute cell."""
    return {ARM: arm, "root": root, "resolution": 5, "delta": delta, "p": p, "bound": bound, "pairs": pairs}


# -- the names -----------------------------------------------------------------------------


def test_tagging_keeps_a_base_variant_that_has_spaces_and_tokens_of_its_own() -> None:
    frame = pd.DataFrame({"variant": [f"window=5m stop=opposite target=R{ARM_MARKER}bars3@-0.5R"]})
    tagged_frame = tagged(frame)
    assert tagged_frame[BASE_VARIANT].iloc[0] == "window=5m stop=opposite target=R"
    assert tagged_frame[ARM].iloc[0] == "bars3@-0.5R"


def test_every_arm_is_built_for_every_base_variant_on_every_root() -> None:
    names = exit_variants("EmaCrossover")
    assert len(names) == 2 * len(early_exit_arms())
    assert all(ARM_MARKER in name for name in names)


def test_the_tier_2_set_tags_by_its_own_marker_and_builds_its_own_arms() -> None:
    tier2 = ARM_SETS[EARLY_EXIT_2]
    frame = pd.DataFrame({"variant": [f"stop=atr{tier2.marker}late30m-bar-extreme"]})
    tagged_frame = tagged(frame, tier2.marker)
    assert tagged_frame[BASE_VARIANT].iloc[0] == "stop=atr"
    assert tagged_frame[ARM].iloc[0] == "late30m-bar-extreme"
    names = exit_variants("EmaCrossover", tier2)
    assert len(names) == 2 * len(tier2_arms())
    assert all(tier2.marker in name for name in names)
    assert not set(names) & set(exit_variants("EmaCrossover"))


def test_neither_set_s_marker_splits_the_other_set_s_names() -> None:
    tier1, tier2 = ARM_SETS[EARLY_EXIT], ARM_SETS[EARLY_EXIT_2]
    tier2_name = pd.DataFrame({"variant": [f"stop=atr{tier2.marker}off"]})
    tier1_name = pd.DataFrame({"variant": [f"stop=atr{tier1.marker}off"]})
    assert tagged(tier2_name, tier1.marker)[ARM].isna().all()
    assert tagged(tier1_name, tier2.marker)[ARM].isna().all()


def test_every_field_an_arm_sets_is_in_a_family_the_reproduction_leaves_out() -> None:
    """A stored row swept before a family existed reads null there, so joining on it would unmatch the row."""
    for arm_set in ARM_SETS.values():
        for fields in arm_set.arms().values():
            assert all(field.startswith(EXIT_FIELD_PREFIXES) for field in fields), arm_set.name


def test_reading_keeps_one_stratum_because_a_pair_only_forms_within_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.concat(
        [rows("bracket", CONTROL_ARM), rows("bracket", CONTROL_ARM, stratum="phase=MIDDAY")],
        ignore_index=True,
    )
    monkeypatch.setattr(module, "load", lambda _name, _windows, variants: frame)  # noqa: ARG005 - the caller passes it by keyword
    assert set(exited("InsideBar", ["holdout"])["stratum"]) == {"unfiltered"}
    assert set(exited("InsideBar", ["holdout"], "phase=MIDDAY")["stratum"]) == {"phase=MIDDAY"}


# -- the paired read -----------------------------------------------------------------------


def test_an_arm_pairs_inside_its_own_base_variant_and_not_across_them() -> None:
    """Pooled, each cell would hold one row of each base variant and the two effects would cancel."""
    table = arm_table(
        both(
            rows("stop=atr", CONTROL_ARM),
            rows("stop=swing", CONTROL_ARM),
            rows("stop=atr", "regime", profit_factor=[0.9, 1.0, 1.2, 1.3]),
            rows("stop=swing", "regime", profit_factor=[0.5, 0.6, 0.7, 0.8]),
        ),
        "regime",
        "profit_factor",
    )
    assert len(table) == 1
    assert table["pairs"].iloc[0] == 8
    assert table["improved"].iloc[0] == 4


def test_an_arm_that_never_fires_is_reported_as_unbound_rather_than_as_no_effect() -> None:
    table = arm_table(
        both(rows("bracket", CONTROL_ARM), rows("bracket", "close15m")), "close15m", "profit_factor"
    )
    assert table["bound"].iloc[0] == 0.0
    assert table["delta"].iloc[0] == 0.0


def test_an_arm_that_moves_the_hold_is_bound_and_carries_its_trade_ratio() -> None:
    treatment = rows("bracket", "bars3@0R", avg_bars_held=[4.0, 4.0, 4.0, 4.0], trades=[150, 300, 450, 600])
    table = arm_table(both(rows("bracket", CONTROL_ARM), treatment), "bars3@0R", "profit_factor")
    assert table["bound"].iloc[0] == 1.0
    assert table["trades_ratio"].iloc[0] == pytest.approx(1.5)
    assert table[ARM].iloc[0] == "bars3@0R"


def test_an_arm_nothing_was_run_at_is_empty_rather_than_an_error() -> None:
    assert arm_table(both(rows("bracket", CONTROL_ARM)), "regime", "profit_factor").empty


# -- the verdict ---------------------------------------------------------------------------


def test_the_pick_is_the_best_bound_arm_and_an_unbound_one_cannot_be_picked() -> None:
    selection = pd.DataFrame(
        [
            table_row("close15m", "MNQ", delta=0.9, p=0.01, bound=0.2),
            table_row("regime", "MNQ", delta=0.1, p=0.01, bound=1.0),
            table_row("trend-opposed", "MNQ", delta=0.2, p=0.01, bound=1.0),
        ],
    )
    holdout = selection.assign(delta=[0.5, -0.1, 0.05], p=[0.01, 0.01, 0.01])
    read = picks(selection, holdout)
    assert list(read[ARM]) == ["trend-opposed"]
    assert read["hold_delta"].iloc[0] == 0.05
    assert bool(read["pays"].iloc[0])


def test_a_pick_pays_only_with_a_positive_held_out_delta_and_a_significant_sign_test() -> None:
    selection = pd.DataFrame(
        [table_row("regime", "MNQ", 0.1, 0.01, 1.0), table_row("regime", "NQ", 0.1, 0.01, 1.0)]
    )
    holdout = pd.DataFrame(
        [table_row("regime", "MNQ", 0.1, 0.20, 1.0), table_row("regime", "NQ", -0.1, 0.01, 1.0)]
    )
    assert not picks(selection, holdout)["pays"].any()


def test_a_cell_clears_only_where_the_pick_pays_on_every_root() -> None:
    selection = pd.DataFrame(
        [table_row("regime", "MNQ", 0.1, 0.01, 1.0), table_row("regime", "NQ", 0.1, 0.01, 1.0)]
    )
    paying = picks(selection, selection)
    assert bool(clearing(paying)["clears"].iloc[0])
    one_root = picks(selection, selection.assign(delta=[0.1, -0.1]))
    assert not bool(clearing(one_root)["clears"].iloc[0])


def test_a_resolution_with_no_bound_arm_stays_in_the_verdict_and_does_not_clear() -> None:
    """Dropping it would hide an untested cell from the count of the family."""
    selection = pd.DataFrame(
        [table_row("close15m", "MNQ", 0.3, 0.01, 0.1), table_row("close15m", "NQ", 0.3, 0.01, 0.1)]
    )
    read = picks(selection, selection)
    assert len(read) == 2
    assert read[ARM].isna().all()
    assert not read["pays"].any()
    cleared = clearing(read)
    assert list(cleared["roots"]) == [2]
    assert not bool(cleared["clears"].iloc[0])


def test_a_resolution_with_no_bound_arm_does_not_hide_one_beside_it_that_has_one() -> None:
    selection = pd.DataFrame(
        [
            table_row("close15m", "MNQ", 0.3, 0.01, 0.1),
            {**table_row("regime", "MNQ", 0.1, 0.01, 1.0), "resolution": 10},
        ]
    )
    read = picks(selection, selection)
    assert list(read["resolution"]) == [5, 10]
    assert list(read["pays"]) == [False, True]


# -- the reproduction check ----------------------------------------------------------------


def test_a_control_identical_to_its_stored_twin_reproduces() -> None:
    found = reproduction(pd.concat([rows("bracket", CONTROL_ARM), rows("bracket", "")], ignore_index=True))
    assert found["joined"] == 4
    assert found["rows_differing"] == 0
    assert found["control_unmatched"] == found["stored_unmatched"] == 0


def test_a_statistic_that_moved_is_counted_by_name() -> None:
    stored = rows("bracket", "", net_pnl=[-10.0, -5.0, 5.0, 11.0])
    found = reproduction(pd.concat([rows("bracket", CONTROL_ARM), stored], ignore_index=True))
    assert found["rows_differing"] == 1
    assert found["statistics_differing"] == {"net_pnl": 1}


def test_a_parameter_the_stored_rows_never_carried_is_left_out_of_the_join() -> None:
    """A column added after the stored sweep reads null there, and joining on it would unmatch every row."""
    control = rows("bracket", CONTROL_ARM, size_symmetric=False)
    stored = rows("bracket", "", size_symmetric=None)
    found = reproduction(pd.concat([control, stored], ignore_index=True))
    assert found["joined"] == 4
    assert found["control_unmatched"] == 0


def test_rows_differing_counts_rows_rather_than_the_worst_statistic() -> None:
    stored = rows("bracket", "", profit_factor=[0.7, 0.9, 1.1, 1.2], net_pnl=[-10.0, -5.0, 5.0, 11.0])
    found = reproduction(pd.concat([rows("bracket", CONTROL_ARM), stored], ignore_index=True))
    assert found["rows_differing"] == 2
    assert found["statistics_differing"] == {"net_pnl": 1, "profit_factor": 1}


def test_a_stored_twin_kept_twice_is_refused_rather_than_joined_twice() -> None:
    stored = rows("bracket", "")
    duplicated = pd.concat(
        [rows("bracket", CONTROL_ARM), stored, stored.assign(sweep_id=2)], ignore_index=True
    )
    with pytest.raises(RuntimeError, match="no single twin"):
        reproduction(duplicated)


def test_the_tier_2_control_reproduces_through_its_own_marker_without_joining_on_an_arms_family() -> None:
    """A stored row swept before a family existed reads null there, and one swept after reads its default."""
    marker = ARM_SETS[EARLY_EXIT_2].marker
    control = rows("bracket", "", variant=f"bracket{marker}{CONTROL_ARM}", age_stop_bars=0, breakeven_at=0.0)
    stored = rows("bracket", "", age_stop_bars=None, breakeven_at=[0.0, math.nan, 0.0, math.nan])
    found = reproduction(pd.concat([control, stored], ignore_index=True), marker)
    assert found["joined"] == 4
    assert found["rows_differing"] == 0


def test_a_stratum_with_no_control_row_is_refused_rather_than_read_as_reproducing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing to join, every count reads zero, which looks like a control that reproduces."""
    monkeypatch.setattr(module, "stored_twins", lambda _name, _stratum, _arm_set: rows("bracket", ""))
    with pytest.raises(SystemExit, match="no --variants early-exit-2 control rows"):
        reproduced("InsideBar", "unfiltered", ARM_SETS[EARLY_EXIT_2])


def test_the_reproduction_reads_the_set_s_own_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = ARM_SETS[EARLY_EXIT_2].marker
    control = rows("bracket", "", variant=f"bracket{marker}{CONTROL_ARM}")
    twins = pd.concat([control, rows("bracket", "")], ignore_index=True)
    monkeypatch.setattr(module, "stored_twins", lambda _name, _stratum, _arm_set: twins)
    found = reproduced("InsideBar", "unfiltered", ARM_SETS[EARLY_EXIT_2])
    assert found["control_rows"] == found["joined"] == 4


def test_a_twin_swept_at_other_costs_is_not_a_twin() -> None:
    control = rows("bracket", CONTROL_ARM, commission_per_contract=1.5)
    stored = rows("bracket", "", commission_per_contract=0.0)
    found = reproduction(pd.concat([control, stored], ignore_index=True))
    assert found["joined"] == 0
    assert found["control_unmatched"] == found["stored_unmatched"] == 4


# -- the mechanism beside each arm ---------------------------------------------------------


def test_the_trade_ratio_is_paired_configuration_by_configuration() -> None:
    """Half the configurations lose half their trades: paired that is 0.75, as medians it is 0.8."""
    treatment = rows("bracket", "bars3@0R", trades=[50, 100, 300, 400])
    table = arm_table(both(rows("bracket", CONTROL_ARM), treatment), "bars3@0R", "profit_factor")
    assert table["trades_ratio"].iloc[0] == pytest.approx(0.75)


def test_every_column_the_pre_registration_reads_beside_an_arm_is_reported() -> None:
    treatment = rows("bracket", "bars3@0R", avg_bars_held=[4.0, 4.0, 4.0, 4.0], session_close_share=[0.1] * 4)
    table = arm_table(both(rows("bracket", CONTROL_ARM), treatment), "bars3@0R", "profit_factor")
    assert table["avg_bars_held_change"].iloc[0] == pytest.approx(-26.0)
    assert table["session_close_share_change"].iloc[0] == pytest.approx(-0.2)
    assert table["commission_paid_ratio"].iloc[0] == pytest.approx(1.0)
    assert table["win_rate_change"].iloc[0] == pytest.approx(0.0)


# -- the guards ----------------------------------------------------------------------------


def test_reading_an_archetype_that_was_never_swept_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "exited", lambda _name, _windows, _stratum, **_options: pd.DataFrame())
    with pytest.raises(SystemExit, match="no --variants early-exit rows"):
        ladder("DeadCatBounce", ["holdout"], "profit_factor")


def test_rows_with_no_arm_to_pair_say_so_rather_than_failing_to_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module, "exited", lambda _name, _windows, _stratum, **_options: both(rows("bracket", CONTROL_ARM))
    )
    with pytest.raises(SystemExit, match="no arm pairs with the control"):
        ladder("DeadCatBounce", ["holdout"], "profit_factor")


def test_a_stratum_name_holding_a_quote_is_refused_before_it_reaches_the_query() -> None:
    with pytest.raises(ValueError, match="cannot be read"):
        stored_twins("InsideBar", "regime='x")


def test_picks_and_reproduce_cannot_be_asked_for_together() -> None:
    with pytest.raises(SystemExit) as refused:
        parse(["prog", "--strategy", "InsideBar", "--picks", "--reproduce"])
    assert refused.value.code == 2


def test_a_window_the_chosen_read_does_not_use_is_refused() -> None:
    with pytest.raises(SystemExit) as refused:
        parse(["prog", "--strategy", "InsideBar", "--picks", "--window", "holdout"])
    assert refused.value.code == 2


def test_the_set_defaults_to_tier_1_and_names_its_own_rows_when_none_were_swept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert parse(["prog", "--strategy", "InsideBar"]).set == EARLY_EXIT
    assert parse(["prog", "--set", EARLY_EXIT_2, "--strategy", "InsideBar"]).set == EARLY_EXIT_2
    monkeypatch.setattr(module, "exited", lambda _name, _windows, _stratum, **_options: pd.DataFrame())
    with pytest.raises(SystemExit, match="no --variants early-exit-2 rows"):
        ladder("DeadCatBounce", ["holdout"], "profit_factor", arm_set=ARM_SETS[EARLY_EXIT_2])


def test_an_unknown_strategy_is_refused_by_name_rather_than_as_a_key_error() -> None:
    with pytest.raises(SystemExit) as refused:
        parse(["prog", "--strategy", "insidebar"])
    assert refused.value.code == 2


def test_a_strategy_the_chosen_set_builds_no_arms_for_is_refused_rather_than_a_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tier2 = ARM_SETS[EARLY_EXIT_2]
    narrower = tier2._replace(variants={k: v for k, v in tier2.variants.items() if k != "InsideBar"})
    monkeypatch.setattr(module, "ARM_SETS", {**ARM_SETS, EARLY_EXIT_2: narrower})
    with pytest.raises(SystemExit) as refused:
        parse(["prog", "--set", EARLY_EXIT_2, "--strategy", "InsideBar"])
    assert refused.value.code == 2
