"""Every `docs/*.md` § "heading" pointer names something that is actually there.

`CLAUDE.md` and `CONTRIBUTING.md` both require it and nothing enforced it, so a section that
moved left its pointers behind silently. Splitting the findings out of the roadmap is exactly
the change that breaks these, which is why the check is a test rather than a one-off.

The comparison is deliberately loose about whitespace, emphasis and dash style: a docstring
wraps a heading across lines and writes `--` where the Markdown has an em dash, and neither is
a broken pointer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SEARCHED = ("nqbt", "tools", "tests", "docs", ".claude")
LOOSE = ("CLAUDE.md", "CONTRIBUTING.md", "README.md")

POINTER = re.compile(r'`{1,2}([A-Za-z0-9_/.\-]+\.md)`{1,2},?\s*§?\s*"([^"]+)"')
"""A pointer in the form the house style uses -- a file in backticks, then a quoted heading."""


def normalise(text: str) -> str:
    """Collapse the differences a pointer is allowed to have from its heading."""
    text = text.replace("—", "--").replace("–", "--").replace("‑", "-")

    return re.sub(r"[\s#*`]+", " ", text).strip()


def documents() -> list[Path]:
    """Every source and Markdown file that could carry a pointer."""
    found = [p for name in SEARCHED for p in (ROOT / name).rglob("*") if p.suffix in (".py", ".md")]

    return [*found, *[ROOT / name for name in LOOSE]]


def pointers() -> list[tuple[Path, str, str]]:
    """Every pointer in the repository, as (source, target file, heading)."""
    out: list[tuple[Path, str, str]] = []
    for path in documents():
        text = path.read_text(encoding="utf-8", errors="ignore")
        out.extend((path, target, heading) for target, heading in POINTER.findall(text))

    return out


@pytest.fixture(scope="module")
def contents() -> dict[str, str]:
    """Each pointed-at file, normalised once."""
    return {}


def test_the_repository_carries_pointers_to_check() -> None:
    """A regex that silently stopped matching would make every assertion below vacuous."""
    assert len(pointers()) > 100


@pytest.mark.parametrize(
    ("source", "target", "heading"),
    [pytest.param(s, t, h, id=f"{s.name}->{t}:{h[:40]}") for s, t, h in pointers()],
)
def test_every_pointer_names_a_section_that_exists(
    source: Path, target: str, heading: str, contents: dict[str, str]
) -> None:
    path = ROOT / target
    assert path.exists(), f"{source.name} points at {target}, which does not exist"
    if target not in contents:
        contents[target] = normalise(path.read_text(encoding="utf-8"))

    assert normalise(heading) in contents[target], (
        f'{source.name} points at {target} § "{heading}", which is not in it'
    )
