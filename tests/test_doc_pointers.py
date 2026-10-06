"""Every `docs/*.md` § "heading" pointer names something that is actually there.

A section that moves leaves its pointers behind silently, so this is a test rather than a
one-off check. The comparison is loose about whitespace, emphasis and dash style: a docstring
wraps a heading across lines and writes `--` where the Markdown has an em dash, and neither is
a broken pointer.

No committed doc names a file inside a gitignored output folder either --
``CONTRIBUTING.md`` § "Data and generated files".

Every link into a heading of ``README.md``, the glossary's entries included, names a heading
that is there.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.findings_index import FINDINGS, NOT_A_FINDING

ROOT = Path(__file__).resolve().parent.parent

SEARCHED = ("nqbt", "tools", "tests", "docs", ".claude", "verification")
LOOSE = ("CLAUDE.md", "CONTRIBUTING.md", "README.md")

POINTER = re.compile(r'`{1,2}([A-Za-z0-9_/.\-]+\.md)`{1,2},?\s*§?\s*"([^"]+)"')
"""A pointer in the form the house style uses -- a file in backticks, then a quoted heading."""


def normalise(text: str) -> str:
    """Collapse the differences a pointer is allowed to have from its heading."""
    text = text.replace("—", "--").replace("–", "--").replace("‑", "-")  # noqa: RUF001 - the dashes a heading may hold

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


README = ROOT / "README.md"

ANCHOR_LINK = re.compile(r"\]\(([^)\s]*)#([\w-]+)\)")
"""A Markdown link carrying a fragment, as (path, anchor); an empty path is the file it sits in."""

MIN_LINKS_INTO_README = 100
"""Fewer than this means the link pattern has stopped matching, not that the links went away."""


def slug(heading: str) -> str:
    """Return the anchor GitHub gives a heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def readme_anchors() -> set[str]:
    """Return the anchor of every heading in the README, outside its code blocks."""
    anchors: set[str] = set()
    in_fence = False
    for line in README.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue

        if not in_fence and line.startswith("#"):
            anchors.add(slug(line.lstrip("#")))

    return anchors


def links_into_readme(source: Path, text: str) -> list[tuple[int, str]]:
    """Return every link in the text that resolves to a README heading, as (line, anchor)."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for target, anchor in ANCHOR_LINK.findall(line):
            if "://" in target:
                continue

            resolved: Path = (source.parent / target).resolve() if target else source
            if resolved == README:
                found.append((number, anchor))

    return found


def every_link_into_readme() -> list[tuple[Path, int, str]]:
    """Find every link into a README heading in the committed Markdown, as (source, line, anchor)."""
    return [
        (path, number, anchor)
        for path in tracked("*.md")
        for number, anchor in links_into_readme(path, path.read_text(encoding="utf-8"))
    ]


def test_the_slug_matches_githubs_for_the_glossary_headings() -> None:
    """Spaces become hyphens, case folds, and punctuation other than `-` and `_` is dropped."""
    assert slug("Tier 1 and Tier 2") == "tier-1-and-tier-2"
    assert slug("`campaign_sweep.py`") == "campaign_sweeppy"
    assert slug("M10.4 — time of day") == "m104--time-of-day"


def test_a_link_is_resolved_from_the_file_it_sits_in() -> None:
    """Only links landing on the README count, however many folders up they climb."""
    source = ROOT / "docs" / "findings" / "example.md"
    text = (
        "[a](../../README.md#sweep) [b](../roadmap.md#gate) [c](#cell)\n[d](https://example.com/README.md#x)"
    )

    assert links_into_readme(source, text) == [(1, "sweep")]
    assert links_into_readme(README, "[c](#cell)") == [(1, "cell")]


def test_the_readme_anchors_hold_the_glossary_and_nothing_invented() -> None:
    """A missing entry is caught, so the check below can fail."""
    anchors = readme_anchors()

    assert {"glossary", "sweep", "tier-1-and-tier-2", "nq-and-mnq"} <= anchors
    assert "no-such-heading" not in anchors


def test_the_repository_carries_links_into_the_readme() -> None:
    """A regex that silently stopped matching would make the check below vacuous."""
    assert len(every_link_into_readme()) > MIN_LINKS_INTO_README


def test_every_link_into_the_readme_names_a_heading_there() -> None:
    """A renamed or removed glossary entry fails here rather than leaving links that go nowhere."""
    anchors = readme_anchors()
    missing = [
        f"{path.relative_to(ROOT).as_posix()}:{number}: #{anchor}"
        for path, number, anchor in every_link_into_readme()
        if anchor not in anchors
    ]

    assert missing == [], "these links name no README heading:\n" + "\n".join(missing)
