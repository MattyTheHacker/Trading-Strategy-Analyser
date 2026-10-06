"""The regression gate has to be able to fail.

``tools/compare_trade_logs.py`` reports success either way, so these pin its sensitivity rather
than its implementation -- ``docs/roadmap.md`` § "The trade-log gate, and the two times it was
wrong".
"""

from __future__ import annotations

import importlib.util
import logging
import math
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pytest

if TYPE_CHECKING:
    from types import ModuleType

TOOL = Path(__file__).resolve().parent.parent / "tools" / "compare_trade_logs.py"


def load_tool() -> ModuleType:
    """Import the script by path, as a module of its own."""
    spec = importlib.util.spec_from_file_location("_compare_trade_logs", TOOL)
    assert spec is not None, f"cannot import {TOOL}"
    assert spec.loader is not None, f"cannot import {TOOL}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return load_tool()


type Capture = tuple[Path, Path]
"""The before and after directories, each holding the same trade log."""


@pytest.fixture
def capture(tmp_path: Path) -> Capture:
    """Provide a pair of directories holding one identical trade-log-shaped CSV."""
    frame = pd.DataFrame(
        {
            "trade_id": [1, 2, 3],
            "leg": [1, 1, 1],
            "net_pnl": [10.0, -5.0, 0.0],
            "r_multiple": [0.5789473684210527, -1.0, 0.0],
        }
    )
    before, after = tmp_path / "before", tmp_path / "after"
    for d in (before, after):
        d.mkdir()
        frame.to_csv(d / "live_mnq.csv", index=False, float_format="%.17g")

    return before, after


def edit_field(path: Path, column: str, row: int, value: str) -> int:
    """Rewrite one CSV field textually, and report how many bytes changed.

    Textual rather than through pandas on purpose: a ``read_csv``/``to_csv`` round trip
    perturbs other columns too, so the gate would fail for a collateral reason and the test
    would pass without proving anything.
    """
    original = path.read_bytes()
    lines = path.read_text().splitlines()
    col = lines[0].split(",").index(column)
    fields = lines[row + 1].split(",")
    fields[col] = value
    lines[row + 1] = ",".join(fields)
    path.write_text("\n".join(lines) + "\n")

    # The two differ in length by design, so this pairs the common prefix and adds the tail.
    edited = path.read_bytes()
    common = sum(a != b for a, b in zip(original, edited, strict=False))

    return common + abs(len(original) - len(edited))


def test_identical_captures_pass(gate: ModuleType, capture: Capture) -> None:
    before, after = capture
    assert gate.compare(before, after, set()) == 0


def test_a_one_ulp_difference_is_detected(gate: ModuleType, capture: Capture) -> None:
    """The case the gate missed: two adjacent float64 values, a two-byte textual change."""
    before, after = capture
    original = 0.5789473684210527
    perturbed = math.nextafter(original, math.inf)
    assert perturbed != original, "fixture value has no neighbour to move to"

    changed = edit_field(after / "live_mnq.csv", "r_multiple", 0, f"{perturbed:.17g}")
    assert changed <= 2, f"meant to be a minimal edit, changed {changed} bytes"

    assert gate.compare(before, after, set()) == 1


def test_the_lax_parser_really_would_have_missed_it(capture: Capture) -> None:
    """Pins *why* the gate needs ``round_trip``, so the fix is not silently reverted.

    If pandas ever fixes its default parser this fails, and the guard above becomes
    belt-and-braces rather than load-bearing -- which is worth being told about.
    """
    _, after = capture
    perturbed = math.nextafter(0.5789473684210527, math.inf)
    edit_field(after / "live_mnq.csv", "r_multiple", 0, f"{perturbed:.17g}")

    lax = pd.read_csv(after / "live_mnq.csv")["r_multiple"].iloc[0]
    exact = pd.read_csv(after / "live_mnq.csv", float_precision="round_trip")["r_multiple"].iloc[0]
    assert lax != exact, "the default parser no longer loses the ULP"
    assert exact == perturbed


def test_a_signed_zero_is_not_a_difference(gate: ModuleType, capture: Capture) -> None:
    """``0.0`` against ``-0.0`` is not a difference, though a file hash calls it one.

    ``docs/roadmap.md`` § "The trade-log gate, and the two times it was wrong".
    """
    before, after = capture
    changed = edit_field(after / "live_mnq.csv", "net_pnl", 2, "-0")
    assert changed >= 1, "the fixture row was already negative zero"

    assert gate.compare(before, after, set()) == 0


def test_an_added_column_is_only_tolerated_when_declared(gate: ModuleType, capture: Capture) -> None:
    before, after = capture
    frame = pd.read_csv(after / "live_mnq.csv")
    frame["direction"] = -1.0
    frame.to_csv(after / "live_mnq.csv", index=False, float_format="%.17g")

    assert gate.compare(before, after, set()) == 1
    assert gate.compare(before, after, {"direction"}) == 0


def test_a_dropped_column_always_fails(gate: ModuleType, capture: Capture) -> None:
    before, after = capture
    frame = pd.read_csv(after / "live_mnq.csv").drop(columns=["r_multiple"])
    frame.to_csv(after / "live_mnq.csv", index=False, float_format="%.17g")

    assert gate.compare(before, after, {"r_multiple"}) == 1


def test_a_missing_file_fails(gate: ModuleType, capture: Capture) -> None:
    before, after = capture
    (after / "live_mnq.csv").unlink()
    assert gate.compare(before, after, set()) == 1


def test_a_file_only_in_after_is_named_rather_than_skipped(
    gate: ModuleType,
    capture: Capture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A newly registered archetype's log has nothing to compare against, and the output says so."""
    before, after = capture
    shutil.copy(after / "live_mnq.csv", after / "defaults_New.csv")

    with caplog.at_level(logging.INFO):
        assert gate.compare(before, after, set()) == 0

    assert "new defaults_New.csv: absent from" in caplog.text
