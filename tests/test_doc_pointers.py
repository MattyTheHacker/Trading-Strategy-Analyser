"""Every `docs/*.md` § "heading" pointer names something that is actually there.

A section that moves leaves its pointers behind silently, so this is a test rather than a
one-off check. The comparison is loose about whitespace, emphasis and dash style: a docstring
wraps a heading across lines and writes `--` where the Markdown has an em dash, and neither is
a broken pointer.

No committed doc names a file inside a gitignored output folder either --
``CONTRIBUTING.md`` § "Data and generated files".
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.findings_index import FINDINGS, NOT_A_FINDING

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
    """List every source and Markdown file that could carry a pointer."""
    found = [p for name in SEARCHED for p in (ROOT / name).rglob("*") if p.suffix in (".py", ".md")]

    return [*found, *[ROOT / name for name in LOOSE]]


def pointers() -> list[tuple[Path, str, str]]:
    """Find every pointer in the repository, as (source, target file, heading)."""
    out: list[tuple[Path, str, str]] = []
    for path in documents():
        text = path.read_text(encoding="utf-8", errors="ignore")
        out.extend((path, target, heading) for target, heading in POINTER.findall(text))

    return out


@pytest.fixture(scope="module")
def contents() -> dict[str, str]:
    """Read each pointed-at file, normalised once."""
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


OUTPUT_PATH = re.compile(r"(?<![\w-])(?:results|verification)/[\w./<>{}*-]*")
"""A path into one of the two gitignored output folders."""

NAMEABLE = frozenset(
    {
        "results/",
        "verification/",
        "results/campaign/",
        "results/campaign/<Strategy>.duckdb",
        "results/sweeps.duckdb",
        "results/charts/trade-{drawn.trade_id}.svg",
        "verification/README.md",
    }
)
"""The folders, the defaults the code writes to and the committed README. Anything else is in words."""


def is_campaign_record(path: Path) -> bool:
    """Say whether a file is one of the findings files, which are dated records left as written."""
    return path.parent == FINDINGS and path.name not in NOT_A_FINDING


def tracked(pattern: str) -> list[Path]:
    """List the committed files matching a git pathspec."""
    git = shutil.which("git")
    assert git is not None, "git is needed to tell committed files from local ones"
    listing = subprocess.run(  # noqa: S603 - a fixed argument list with nothing from outside it
        [git, "ls-files", "-z", "--", pattern], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout

    return [ROOT / name for name in listing.split("\0") if name]


def committed_docs() -> list[Path]:
    """List the committed Markdown, less the campaign records."""
    return [path for path in tracked("*.md") if not is_campaign_record(path)]


def unnameable(text: str) -> list[str]:
    """Return every output-folder path in the text that a committed doc may not name."""
    return [path for path in OUTPUT_PATH.findall(text) if path not in NAMEABLE]


def test_a_file_inside_an_output_folder_is_caught() -> None:
    """A specific file under either folder is flagged, a placeholder in it included."""
    text = "`verification/trades.csv`, `results/campaign/OpeningRange.duckdb`, `verification/x/<stem>.csv`"

    assert unnameable(text) == [
        "verification/trades.csv",
        "results/campaign/OpeningRange.duckdb",
        "verification/x/<stem>.csv",
    ]


def test_the_folders_and_the_code_defaults_pass() -> None:
    """Every path the docs may name passes the check."""
    assert unnameable(" ".join(f"`{path}`" for path in sorted(NAMEABLE))) == []


def test_a_folder_name_inside_a_longer_name_is_not_an_output_folder() -> None:
    """A module or folder whose name only ends in one of the two is not flagged."""
    assert unnameable("`nqbt/results.py`, `sweep_results/a.csv` and `pre-verification/b.csv`") == []


def test_the_scan_reads_committed_docs_and_skips_the_campaign_records() -> None:
    """An empty listing would make the check below vacuous, and a campaign record is exempt."""
    scanned = {path.relative_to(ROOT).as_posix() for path in committed_docs()}

    assert {"CONTRIBUTING.md", "docs/roadmap.md", "tools/README.md", "docs/findings/register.md"} <= scanned
    assert "docs/findings/m27-registry-campaign.md" not in scanned


def test_the_verification_readme_is_committed() -> None:
    """The docs name it as the authority on what the captures mean, so it cannot be local."""
    assert tracked("verification/README.md") == [ROOT / "verification" / "README.md"]


def test_no_committed_doc_names_a_file_inside_an_output_folder() -> None:
    """Outside the campaign records, the docs name only the paths in `NAMEABLE`."""
    found = [
        f"{path.relative_to(ROOT).as_posix()}:{number}: {output_path}"
        for path in committed_docs()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for output_path in unnameable(line)
    ]

    assert found == [], (
        "name these in words instead -- CONTRIBUTING.md, 'Data and generated files':\n" + "\n".join(found)
    )
