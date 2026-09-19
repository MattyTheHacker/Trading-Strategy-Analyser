"""Every dataset built for a simulation says what its bars are.

`context.prepare` defaults to `PriceBasis.UNKNOWN` on purpose, so a rule reading an absolute
level is refused rather than run on levels that may not be the traded ones -- `docs/roadmap.md`
§ "The build spec's three loose ends". The cost of that default falls on the caller, and it was
paid twice before anything checked: [#330] for `campaign_shortlist.store_logs` and [#340] for
`campaign_null.measure`, each of which blocked a whole gate on EmaCrossover's round-number arm.

This is the check that was missing. It reads the source rather than running anything, because
what has to hold is a property of every call site including the ones no test reaches --
`tools/campaign_sweep.py`'s own `test_the_campaign_runs_on_the_prices_that_traded` is the same
idea over one file.

**A call that genuinely cannot state a basis is exempt by name in :data:`EXEMPT`, with its
reason.** Adding an entry is the deliberate act; forgetting a keyword is not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SEARCHED = ("nqbt", "tools")

BUILDERS = ("context.prepare", "prepare_for", "sweep_axes")
"""Calls that build a :class:`~nqbt.context.Dataset` a simulation will read.

`sweep.sweep` is **not** here: it takes an already-prepared ``data``, which is the route
`.claude/rules/sweep-and-context.md` names for a caller that needs a basis."""

EXEMPT: dict[tuple[str, str], str] = {
    ("nqbt/sweep.py", "prepare_for"): "the wrapper itself; it forwards PrepareOptions verbatim",
    ("nqbt/sweep.py", "sweep"): "takes a prepared data= instead, which is the documented route",
    ("tools/capture_trade_logs.py", "capture"): (
        "the regression gate's own capture; it runs DeadCatBounce alone, which reads no "
        "absolute level, and .claude/rules/regression-gate.md is why it is not edited casually"
    ),
    ("tools/campaign_sweep.py", "calibrate_volume"): "fits thresholds and runs no legs",
    ("tools/campaign_annotate.py", "store_annotations"): "annotates a stored log and runs no legs",
    ("tools/campaign_labels.py", "labelled"): "builds context labels and runs no legs",
    ("tools/campaign_labels.py", "volume_rows"): "builds context labels and runs no legs",
    ("tools/campaign_review.py", "review_shortlist"): "reviews a stored log and runs no legs",
}
"""Where a basis is not stated, and why. Keyed by ``(file, enclosing function)``."""


def enclosing(tree: ast.Module) -> dict[ast.AST, str]:
    """Each node's nearest enclosing function name, for naming a call site stably.

    By name rather than by line, so the exemption list survives an edit above it.
    """
    found: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for child in ast.walk(node):
            found.setdefault(child, node.name)

    return found


def builders_in(path: Path) -> list[tuple[str, str, bool]]:
    """Every dataset-building call in one file, as ``(function, call, states_a_basis)``."""
    tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"))
    names: dict[ast.AST, str] = enclosing(tree)

    return [
        (
            names.get(node, "<module>"),
            ast.unparse(node.func),
            any(keyword.arg == "price_basis" for keyword in node.keywords),
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(BUILDERS)
    ]


def call_sites() -> list[tuple[str, str, str, bool]]:
    """Every dataset-building call in the searched packages."""
    found: list[tuple[str, str, str, bool]] = []
    for package in SEARCHED:
        for path in sorted((ROOT / package).rglob("*.py")):
            relative: str = path.relative_to(ROOT).as_posix()
            found.extend((relative, function, call, stated) for function, call, stated in builders_in(path))

    return found


def test_the_search_finds_call_sites_to_check() -> None:
    """A matcher that silently stopped matching would make the assertion below vacuous."""
    sites = call_sites()
    assert len(sites) > 15
    assert {"nqbt/cli.py", "nqbt/sweep.py", "tools/campaign_null.py"} <= {path for path, _, _, _ in sites}


@pytest.mark.parametrize(
    ("path", "function", "call", "stated"),
    [pytest.param(*site, id=f"{site[0]}:{site[1]}:{site[2]}") for site in call_sites()],
)
def test_every_prepared_dataset_states_its_price_basis(
    path: str, function: str, call: str, stated: bool
) -> None:
    """A dataset built without a basis refuses a round-number configuration at run time, and
    the refusal is a crash in the middle of a campaign rather than a number to read ([#341])."""
    if (path, function) in EXEMPT:
        assert not stated, f"{path}:{function} states a basis now; drop it from EXEMPT"

        return

    assert stated, (
        f"{path}:{function} calls {call} without price_basis. State it, or add "
        f"({path!r}, {function!r}) to EXEMPT with the reason it cannot be stated."
    )


def test_every_exemption_names_a_call_that_exists() -> None:
    """An exemption left behind after its call moved is a hole nothing reports."""
    sites = {(path, function) for path, function, _, _ in call_sites()}
    assert set(EXEMPT) <= sites, f"stale exemptions: {sorted(set(EXEMPT) - sites)}"


def test_every_exemption_carries_a_reason() -> None:
    assert all(reason.strip() for reason in EXEMPT.values())
