"""The trade-log schema, and the layering M9 exists to establish.

Two producers will write trade logs -- the jitted simulation and, later, an importer for
real NT8 executions -- and a statistic is only comparable across them if they agree on
what a row means. These tests pin that agreement and the module boundaries that keep it
enforceable.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nqbt import trades
from nqbt.trades import TradeSchemaError

PACKAGE = Path(__file__).resolve().parents[1] / "nqbt"


def leg_log(n: int = 3, **overrides) -> pd.DataFrame:
    """A minimal schema-conforming log, in the shape an importer would produce."""
    frame = pd.DataFrame(
        {
            "source": pd.array(["manual"] * n, dtype="string"),
            "instrument": pd.array(["MNQ"] * n, dtype="string"),
            "trade_id": np.arange(1, n + 1, dtype="int64"),
            "leg": np.ones(n, dtype="int64"),
            "entry_bar": np.arange(n, dtype="int64"),
            "exit_bar": np.arange(1, n + 1, dtype="int64"),
            "entry_price": np.full(n, 100.0),
            "exit_price": np.full(n, 99.0),
            "initial_stop": np.full(n, 101.0),
            "target_price": np.full(n, 98.0),
            "quantity": np.ones(n, dtype="int64"),
            "direction": np.full(n, trades.SHORT),
            "exit_reason": pd.array(["target"] * n, dtype="string"),
            "gross_pnl": np.full(n, 2.0),
            "commission": np.full(n, 0.5),
            "net_pnl": np.full(n, 1.5),
            "r_multiple": np.full(n, 1.0),
            "risk_points": np.full(n, 1.0),
            "mae_points": np.full(n, 0.5),
            "mfe_points": np.full(n, 1.5),
            "bars_held": np.ones(n, dtype="int64"),
            "ambiguous_bar": np.zeros(n, dtype=bool),
        },
    )
    for name, value in overrides.items():
        frame[name] = value

    return frame


# -- the schema itself --------------------------------------------------------


def test_the_schema_is_the_tags_plus_the_matrix_columns() -> None:
    assert trades.SCHEMA == trades.TAGS + trades.COLUMNS
    assert len(trades.COLUMNS) == trades.N_COLUMNS


def test_column_indices_address_their_own_names() -> None:
    # The jitted loop writes by index and everything else reads by name; if these ever
    # disagree the trade log is silently transposed rather than wrong in an obvious way.
    for index, name in (
        (trades.C_TRADE_ID, "trade_id"),
        (trades.C_DIRECTION, "direction"),
        (trades.C_NET_PNL, "net_pnl"),
        (trades.C_AMBIGUOUS, "ambiguous_bar"),
    ):
        assert trades.COLUMNS[index] == name


def test_exit_signal_is_reserved_for_a_future_rule_driven_exit() -> None:
    # DeadCatBounce has no rule-driven exit -- every exit today is a bracket level or the
    # session close. EXIT_SIGNAL exists for EMA crossover (M18) and InsideBarTrailing.cs.
    assert trades.EXIT_REASONS[trades.EXIT_SIGNAL] == "signal"
    other_reasons = {
        trades.EXIT_STOP,
        trades.EXIT_TARGET,
        trades.EXIT_SESSION_CLOSE,
        trades.EXIT_END_OF_DATA,
    }
    assert trades.EXIT_SIGNAL not in other_reasons


def test_every_nullable_column_is_actually_in_the_schema() -> None:
    assert set(trades.SCHEMA) >= trades.NULLABLE


def test_required_and_nullable_partition_the_schema() -> None:
    assert set(trades.REQUIRED) | trades.NULLABLE == set(trades.SCHEMA)
    assert not set(trades.REQUIRED) & trades.NULLABLE


# -- validate -----------------------------------------------------------------


def test_a_conforming_log_passes_and_is_returned_unchanged() -> None:
    log = leg_log()
    assert trades.validate(log) is log


def test_an_empty_log_with_the_right_columns_passes() -> None:
    trades.validate(leg_log(0))


def test_a_missing_column_is_named_in_the_error() -> None:
    with pytest.raises(TradeSchemaError, match="direction"):
        trades.validate(leg_log().drop(columns=["direction"]))


def test_a_missing_tag_is_rejected_like_any_other_column() -> None:
    with pytest.raises(TradeSchemaError, match="instrument"):
        trades.validate(leg_log().drop(columns=["instrument"]))


def test_nulls_are_allowed_exactly_where_documented() -> None:
    # An imported trade has no planned stop and no bars to measure excursions across.
    log = leg_log()
    for name in trades.NULLABLE:
        log[name] = np.nan
    trades.validate(log)


def test_a_null_in_a_required_column_is_rejected_with_a_count() -> None:
    log = leg_log()
    log.loc[0, "net_pnl"] = np.nan
    with pytest.raises(TradeSchemaError, match=r"net_pnl \(1\)"):
        trades.validate(log)


def test_a_null_tag_is_rejected() -> None:
    log = leg_log()
    log.loc[1, "instrument"] = None
    with pytest.raises(TradeSchemaError, match="instrument"):
        trades.validate(log)


def test_direction_must_be_plus_or_minus_one() -> None:
    with pytest.raises(TradeSchemaError, match="direction"):
        trades.validate(leg_log(direction=0.0))


def test_a_long_log_is_accepted() -> None:
    # Nothing produces one yet -- M15 does -- but the schema must not assume short.
    trades.validate(leg_log(direction=trades.LONG))


def test_a_negative_quantity_is_rejected_rather_than_read_as_a_short() -> None:
    # The one encoding mistake that would silently double-count direction.
    with pytest.raises(TradeSchemaError, match="direction, not by a negative size"):
        trades.validate(leg_log(quantity=np.int64(-1)))


def test_leg_numbering_starts_at_one() -> None:
    with pytest.raises(TradeSchemaError, match="leg numbering"):
        trades.validate(leg_log(leg=np.int64(0)))


def test_an_unknown_source_is_rejected() -> None:
    with pytest.raises(TradeSchemaError, match="backtest"):
        trades.validate(leg_log(source="backtest"))


def test_an_exit_reason_outside_the_simulator_enum_is_allowed() -> None:
    # NT8's executions grid names exits Stop1..4 and Exit. Constraining exit_reason to
    # EXIT_REASONS would force the importer to invent a mapping it has no basis for.
    trades.validate(leg_log(exit_reason="Stop3"))


# -- validate_legs, the boundary a caller that never builds a frame crosses -----


def leg_matrix(n: int = 3, **overrides) -> trades.LegMatrix:
    """A minimal schema-conforming leg matrix, as the jitted loop would leave it."""
    matrix = np.zeros((n + 2, trades.N_COLUMNS))  # a tail of unwritten rows, like the real one
    matrix[:n, trades.C_TRADE_ID] = np.arange(1, n + 1)
    matrix[:n, trades.C_LEG] = 1
    matrix[:n, trades.C_QUANTITY] = 1
    matrix[:n, trades.C_DIRECTION] = trades.SHORT
    matrix[:n, trades.C_EXIT_REASON] = trades.EXIT_TARGET
    matrix[:n, trades.C_TARGET_PRICE] = np.nan  # nullable, and the loop really writes this
    for name, value in overrides.items():
        matrix[:n, getattr(trades, name)] = value

    return trades.LegMatrix(matrix, n)


def test_a_conforming_leg_matrix_passes_and_is_returned_unchanged() -> None:
    legs = leg_matrix()
    assert trades.validate_legs(legs) is legs


def test_the_unwritten_tail_is_not_inspected() -> None:
    """``allocate_output`` sizes to an upper bound, so the rows past ``count`` are zeros.

    A zero row has ``quantity`` 0 and ``direction`` 0, both of which the checks below
    reject -- reading past ``count`` would fail every run.
    """
    trades.validate_legs(leg_matrix(n=1))


def test_an_empty_leg_matrix_passes() -> None:
    trades.validate_legs(trades.LegMatrix(np.zeros((4, trades.N_COLUMNS)), 0))


def test_a_matrix_of_the_wrong_width_is_refused() -> None:
    with pytest.raises(TradeSchemaError, match="leg matrix is"):
        trades.validate_legs(trades.LegMatrix(np.zeros((3, 4)), 3))


def test_a_count_past_the_end_of_the_matrix_is_refused() -> None:
    with pytest.raises(TradeSchemaError, match="exceeds"):
        trades.validate_legs(trades.LegMatrix(np.zeros((3, trades.N_COLUMNS)), 9))


def test_a_null_in_a_required_column_names_the_column() -> None:
    with pytest.raises(TradeSchemaError, match=r"net_pnl \(3\)"):
        trades.validate_legs(leg_matrix(C_NET_PNL=np.nan))


def test_a_null_in_a_nullable_column_is_accepted() -> None:
    # target_price is null on any leg with no target, which is how the loop writes a runner.
    trades.validate_legs(leg_matrix(C_R_MULTIPLE=np.nan, C_MAE=np.nan))


def test_a_direction_that_is_neither_long_nor_short_is_refused() -> None:
    with pytest.raises(TradeSchemaError, match="direction must be"):
        trades.validate_legs(leg_matrix(C_DIRECTION=0.0))


def test_a_non_positive_quantity_is_refused() -> None:
    with pytest.raises(TradeSchemaError, match="quantity must be positive"):
        trades.validate_legs(leg_matrix(C_QUANTITY=-1.0))


def test_leg_numbering_below_one_is_refused() -> None:
    with pytest.raises(TradeSchemaError, match="leg numbering"):
        trades.validate_legs(leg_matrix(C_LEG=0.0))


def test_an_exit_reason_outside_the_simulator_enum_is_refused_on_a_matrix() -> None:
    """The mirror of the frame rule above, and deliberately the opposite answer.

    A frame's ``exit_reason`` may be a label NT8 wrote; a matrix can only have come from
    the simulator, so a code outside the enum there is a bug rather than an import.
    """
    with pytest.raises(TradeSchemaError, match="unknown exit_reason"):
        trades.validate_legs(leg_matrix(C_EXIT_REASON=9.0))


# -- trades_to_frame ----------------------------------------------------------


def test_trades_to_frame_tags_every_row() -> None:
    matrix = np.zeros((2, trades.N_COLUMNS))
    matrix[:, trades.C_QUANTITY] = 1
    matrix[:, trades.C_LEG] = 0  # written as leg + 1 by the loop
    matrix[:, trades.C_DIRECTION] = trades.SHORT
    frame = trades.trades_to_frame(matrix, 2, instrument="NQ")
    assert tuple(frame.columns[:2]) == trades.TAGS
    assert (frame["instrument"] == "NQ").all()
    assert (frame["source"] == "sim").all()


def test_trades_to_frame_requires_an_instrument() -> None:
    # A trade log without one cannot be summed in dollars: NQ and MNQ differ 10x.
    with pytest.raises(TypeError):
        trades.trades_to_frame(np.zeros((1, trades.N_COLUMNS)), 1)


# -- the layering M9 establishes ----------------------------------------------


def imports_of(module: str) -> set[str]:
    """Every module a file could be reaching, fully qualified.

    ``from nqbt import trades`` has to resolve to ``nqbt.trades`` and not merely to
    ``nqbt``, or a rule written as a prefix match passes while the import it forbids sits
    in plain sight. That is exactly how these tests were vacuous when first written, so
    both halves of a ``from`` are recorded: the package and each name under it.
    """
    tree = ast.parse((PACKAGE / module).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)

    return found


def names_used_in(module: str) -> set[str]:
    """Every attribute name the file reads off something, so ``trades.EXIT_SIGNAL`` is seen.

    ``imports_of`` cannot see it: the constant arrives through ``from nqbt import trades`` and
    is spent as an attribute, so a rule about who *produces* an exit reason has to read the
    uses rather than the imports.
    """
    tree = ast.parse((PACKAGE / module).read_text(encoding="utf-8"))

    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_the_import_analysis_sees_both_forms_of_import() -> None:
    """Guards the guard. Without this the layering tests silently pass on anything."""
    seen = imports_of("sim/runner.py")
    assert "nqbt.context.Dataset" in seen, "from X import Y must resolve to X.Y"
    assert "nqbt.trades" in seen, "from nqbt import trades must resolve to nqbt.trades"


def test_stats_does_not_import_from_the_simulator() -> None:
    """The rule the review layer depends on.

    ``stats.py`` must work on any trade log, including one imported from real fills that
    no strategy produced. It already did not import from ``nqbt.sim``; this makes that a
    rule instead of an accident.
    """
    assert not {m for m in imports_of("stats.py") if m.startswith("nqbt.sim")}


def test_the_trade_schema_knows_nothing_about_bars_or_strategies() -> None:
    offenders = {
        m
        for m in imports_of("trades.py")
        if m.startswith(("nqbt.sim", "nqbt.context", "nqbt.conditions", "nqbt.indicators"))
    }
    assert not offenders, f"nqbt/trades.py must stay standalone; found {offenders}"


def test_only_the_archetypes_with_a_rule_driven_exit_reference_exit_signal() -> None:
    # A structural guard, not just a today-it-doesn't-happen-to-fire one. DeadCatBounce and
    # InsideBar have no rule-driven exit and the shared bracket engine has no rules at all, so
    # none of them should import the constant it would need to produce one. The two that do
    # are EmaCrossover, which the reservation was made for, and InsideBarTrailing, whose
    # NinjaScript exits on a trend violation -- docs/nt8-fidelity.md §M23. ElasticBand is the
    # third: its invalidation exit and its time stop both write it -- §M26.
    assert "nqbt.trades.EXIT_SIGNAL" not in imports_of("sim/deadcat.py")
    assert "nqbt.trades.EXIT_SIGNAL" not in imports_of("sim/bracket.py")
    assert "nqbt.trades.EXIT_SIGNAL" not in imports_of("sim/pullback.py")
    assert "nqbt.trades.EXIT_SIGNAL" not in imports_of("sim/insidebar.py")
    # And the positive half, without which the negatives would pass on a typo.
    assert "nqbt.trades" in imports_of("sim/crossover.py")
    assert "nqbt.trades" in imports_of("sim/insidebartrailing.py")
    assert "nqbt.trades" in imports_of("sim/elasticband.py")
    assert {"EXIT_SIGNAL"} <= names_used_in("sim/crossover.py")
    assert {"EXIT_SIGNAL"} <= names_used_in("sim/insidebartrailing.py")
    assert {"EXIT_SIGNAL"} <= names_used_in("sim/elasticband.py")


def test_the_registry_sits_above_the_layers_it_names_rather_than_inside_them() -> None:
    """``archetypes.py`` may reach down; nothing below it may reach back up.

    It imports ``nqbt.sim`` by design -- knowing how to reach an archetype is exactly its
    job. The rule that matters is the other direction: if ``context.py`` ever imported it,
    the market context would depend transitively on the simulator and the review layer
    could no longer annotate real trades with it.
    """
    for lower in ("context.py", "trades.py", "stats.py", "conditions.py", "indicators.py"):
        assert "nqbt.archetypes" not in imports_of(lower), f"nqbt/{lower} must not import the archetype registry"
    # And the premise: it really does reach down, so the rule above is a rule and not a
    # description of a module that happens to import nothing.
    assert "nqbt.sim" in imports_of("archetypes.py")


def test_the_time_of_day_labels_sit_below_the_market_context() -> None:
    """``timeofday.py`` is a clock, not a strategy.

    ``context.py`` imports it, so it may not import back; and the review layer has to be
    able to label a real trade's entry bar without a simulator anywhere in the graph.
    """
    forbidden = ("nqbt.sim", "nqbt.trades", "nqbt.context", "nqbt.archetypes")
    offenders = {m for m in imports_of("timeofday.py") if m.startswith(forbidden)}
    assert not offenders, f"nqbt/timeofday.py must stay below the context layer; found {offenders}"


def test_market_context_knows_nothing_about_trades() -> None:
    """``context.py`` is the half of a backtest with no strategy in it.

    It has to stay that way for the review layer to annotate real trades against the same
    conditions a sweep reads.
    """
    offenders = {m for m in imports_of("context.py") if m.startswith(("nqbt.sim", "nqbt.trades"))}
    assert not offenders, f"nqbt/context.py must not depend on trades or sim; found {offenders}"
