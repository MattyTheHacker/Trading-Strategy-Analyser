"""What decides whether a pull request runs the trade-log gate, and whether it passes.

A trigger that misses a path or a verdict that passes a failure disables the gate silently,
the same way a stale JIT cache does, so both are pinned here rather than trusted to the YAML.
"""

import importlib.util
import io
import json
import logging
import re
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from tools.trade_log_gate_ci import (
    ACCEPT_LABEL,
    DOCUMENTATION_DIRECTORIES,
    DOCUMENTATION_FILES,
    Verdict,
    applies,
    main,
    verdict,
)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "trade-log-gate.yaml"
COMPARE_TOOL = ROOT / "tools" / "compare_trade_logs.py"


def load_compare_tool() -> ModuleType:
    """Import the comparison script by path, as ``tests/test_trade_log_gate.py`` does."""
    spec = importlib.util.spec_from_file_location("_compare_trade_logs_for_ci", COMPARE_TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def compare_output(tmp_path: Path, caplog: pytest.LogCaptureFixture, *, moved: bool) -> tuple[int, str]:
    """Run the real comparison over two one-file captures and return its status and output."""
    tool = load_compare_tool()
    before, after = tmp_path / "before", tmp_path / "after"
    for directory, pnl in ((before, 10.0), (after, 10.25 if moved else 10.0)):
        directory.mkdir()
        pd.DataFrame({"trade_id": [1], "net_pnl": [pnl]}).to_csv(directory / "live_mnq.csv", index=False)

    with caplog.at_level(logging.INFO, logger=tool.__name__):
        status = 1 if tool.compare(before, after, set()) else 0

    return status, "\n".join(caplog.messages)


# -- which pull requests run it ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "nqbt/sim/bracket.py",
        "nqbt/indicators.py",
        "pyproject.toml",
        ".python-version",
        "tools/capture_trade_logs.py",
        "tools/campaign_null.py",
        "tests/test_numeric_pins.py",
        ".github/workflows/checks.yaml",
        "ninjatrader-scripts",
    ],
)
def test_a_change_to_anything_but_documentation_runs_the_gate(path: str) -> None:
    assert applies([path])


@pytest.mark.parametrize(
    "path",
    [
        "docs/roadmap.md",
        "docs/findings/m45-ibt-sizing-result.md",
        "README.md",
        "CONTRIBUTING.md",
        ".claude/rules/regression-gate.md",
        "Trading-Docs",
    ],
)
def test_a_documentation_only_change_skips_it(path: str) -> None:
    assert not applies([path])


@pytest.mark.parametrize("path", ["nqbt/docs/labels.py", "Trading-Docs-extra", "README.md.orig"])
def test_a_path_that_only_resembles_documentation_runs_it(path: str) -> None:
    assert applies([path])


def test_one_changed_file_that_is_not_documentation_is_enough() -> None:
    assert applies(["docs/roadmap.md", "README.md", "nqbt/stats.py", "CONTRIBUTING.md"])


def test_no_changed_paths_skips_it() -> None:
    assert not applies([])


def test_the_exempt_documentation_still_exists() -> None:
    """A renamed docs folder or submodule would quietly start running the gate, or stop exempting."""
    assert all((ROOT / directory).is_dir() for directory in DOCUMENTATION_DIRECTORIES)
    submodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert all(f"path = {name}" in submodules for name in DOCUMENTATION_FILES)


def test_the_workflow_asks_this_tool_both_questions() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"tools/trade_log_gate_ci\.py\"?\s+applies", text)
    assert re.search(r"tools/trade_log_gate_ci\.py\"?\s+verdict", text)
    assert "--no-renames" in text, "a file moved into docs/ would show only its new path"


# -- whether a run passes ------------------------------------------------------


def test_identical_captures_pass(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    status, output = compare_output(tmp_path, caplog, moved=False)
    assert status == 0
    assert verdict(status, output, []) is Verdict.IDENTICAL


def test_a_moved_number_fails(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    status, output = compare_output(tmp_path, caplog, moved=True)
    assert status == 1
    assert verdict(status, output, ["sync", "area:sim"]) is Verdict.MOVED


def test_a_moved_number_passes_only_with_the_label(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    status, output = compare_output(tmp_path, caplog, moved=True)
    assert verdict(status, output, ["sync", ACCEPT_LABEL]) is Verdict.ACCEPTED


def test_a_comparison_that_did_not_finish_fails_whatever_the_labels() -> None:
    """A traceback exits 1 exactly as a difference does; a label must not wave it through."""
    traceback = 'Traceback (most recent call last):\n  File "compare_trade_logs.py"\nKeyError: x'
    assert verdict(1, traceback, [ACCEPT_LABEL]) is Verdict.BROKEN


def test_a_failure_count_mentioned_mid_line_is_not_a_finished_comparison() -> None:
    assert verdict(1, "error: expected '3 FAILURE(S)' in the log", [ACCEPT_LABEL]) is Verdict.BROKEN


def test_an_identical_run_passes_whatever_the_labels() -> None:
    assert verdict(0, "BYTE-FOR-BYTE IDENTICAL", [ACCEPT_LABEL]) is Verdict.IDENTICAL


# -- the command line the workflow calls ---------------------------------------


def test_applies_reads_the_changed_paths_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("docs/roadmap.md\n\nnqbt/sim/bracket.py\n"))
    assert main(["applies"]) == 0
    assert capsys.readouterr().out == "applies=true\n"


def test_applies_says_false_when_only_documentation_changed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("docs/roadmap.md\n"))
    assert main(["applies"]) == 0
    assert capsys.readouterr().out == "applies=false\n"


@pytest.mark.parametrize(
    ("moved", "labels", "expected_status", "annotation"),
    [
        (False, [], 0, ""),
        (True, [], 1, "::error::"),
        (True, [ACCEPT_LABEL], 0, "::warning::"),
    ],
)
def test_verdict_exits_by_whether_the_run_passes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    moved: bool,  # noqa: FBT001 - a parametrised case, not a flag
    labels: list[str],
    expected_status: int,
    annotation: str,
) -> None:
    status, output = compare_output(tmp_path, caplog, moved=moved)
    written = tmp_path / "compare.txt"
    written.write_text(output, encoding="utf-8")

    args = ["verdict", "--status", str(status), "--output", str(written), "--labels", json.dumps(labels)]
    assert main(args) == expected_status
    assert capsys.readouterr().out.startswith(annotation)
