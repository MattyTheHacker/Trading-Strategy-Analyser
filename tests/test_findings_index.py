"""The findings register's front matter, and the three views generated from it.

Two claims are worth pinning. The parser reads a **closed** subset of YAML and must raise on
anything outside it rather than guess, because a silently mis-parsed field reaches the index as
a wrong fact. And the committed views must match what the findings files currently say -- that
is the staleness gate, and it is the reason the views are generated at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.findings_index import (
    BY_ARCHETYPE,
    BY_GATE,
    GATES,
    NOT_A_FINDING,
    OUTCOMES,
    REGISTER,
    SUMMARY,
    Finding,
    FrontMatterError,
    load,
    main,
    parse_front_matter,
    views,
)

from nqbt import archetypes

FINDINGS = Path(__file__).resolve().parent.parent / "docs" / "findings"

VALID = """---
id: M28.16
title: "A campaign"
archetypes: [OpeningRange]
issues: [288]
gates: [3]
outcome: mixed
verdict: >-
  It cleared the null.
---

# A campaign
"""


def write(directory: Path, slug: str, text: str) -> Path:
    """Put one findings file on disk."""
    path = directory / f"{slug}.md"
    path.write_text(text, encoding="utf-8")

    return path


def test_the_committed_views_match_the_findings_files() -> None:
    """The staleness gate: regenerate with tools/findings_index.py when this fails."""
    findings = load(FINDINGS)
    for name, content in views(findings).items():
        assert (FINDINGS / name).read_text(encoding="utf-8") == content, (
            f"{name} is out of date -- run tools/findings_index.py"
        )


def test_check_returns_zero_when_the_views_are_current() -> None:
    assert main(["findings_index.py", "--check"]) == 0


def test_check_returns_one_when_a_view_is_stale(tmp_path: Path) -> None:
    """The gate has to be able to fail, so make it."""
    write(tmp_path, "a-campaign", VALID)
    assert main(["findings_index.py", "--directory", str(tmp_path)]) == 0
    (tmp_path / REGISTER).write_text("stale\n", encoding="utf-8")
    assert main(["findings_index.py", "--check", "--directory", str(tmp_path)]) == 1


def test_every_finding_parses_and_validates() -> None:
    findings = load(FINDINGS)
    assert findings, "docs/findings/ holds no findings"
    for finding in findings:
        assert finding.title
        assert finding.verdict
        assert finding.outcome in OUTCOMES
        assert set(finding.gates) <= set(GATES)
        assert set(finding.archetypes) <= set(archetypes.names())


def test_generated_views_are_not_read_as_findings() -> None:
    """A view carries no front matter, so loading one would raise rather than mislead."""
    slugs = {f.slug for f in load(FINDINGS)}
    assert slugs.isdisjoint({Path(name).stem for name in NOT_A_FINDING})


def test_the_hand_written_summary_is_never_generated(tmp_path: Path) -> None:
    """README.md is the front door and is authored, so the tool must not touch or read it."""
    assert SUMMARY not in views(load(FINDINGS))

    write(tmp_path, "a-campaign", VALID)
    summary = tmp_path / SUMMARY
    summary.write_text("# Findings\n\nAuthored by hand.\n", encoding="utf-8")
    assert main(["findings_index.py", "--directory", str(tmp_path)]) == 0
    assert summary.read_text(encoding="utf-8") == "# Findings\n\nAuthored by hand.\n"


def test_the_summary_points_at_the_strategies_it_names() -> None:
    """Its two sections are the reason the directory has a front door at all."""
    summary = (FINDINGS / SUMMARY).read_text(encoding="utf-8")
    assert "## For a prop-firm account" in summary
    assert "## For a regular account" in summary
    for view in (REGISTER, BY_ARCHETYPE, BY_GATE):
        assert f"({view})" in summary, f"the summary does not link {view}"


def test_findings_are_ordered_by_milestone_not_by_filename() -> None:
    """M7a before M10.1 before M26 before M26.4, which a filename sort gets wrong."""
    ids = [f.id for f in load(FINDINGS) if f.id]
    assert ids.index("M7a") < ids.index("M10.1") < ids.index("M26") < ids.index("M26.4")
    assert ids.index("M26.9") < ids.index("M27") < ids.index("M28.16")


def test_a_finding_without_an_id_is_cited_by_its_title() -> None:
    """Three sections have no milestone number and are cited by quoted heading."""
    untitled = [f for f in load(FINDINGS) if not f.id]
    assert untitled
    for finding in untitled:
        assert finding.cite == f'§ "{finding.title}"'


def test_every_cite_resolves_to_a_roadmap_stub() -> None:
    """A moved section keeps its heading in the roadmap so existing pointers still land."""
    roadmap = (FINDINGS.parent / "roadmap.md").read_text(encoding="utf-8")
    for finding in load(FINDINGS):
        assert f"findings/{finding.slug}.md" in roadmap, f"{finding.slug} has no stub in docs/roadmap.md"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("no front matter at all\n", "no front matter"),
        ('---\nid: M1\ntitle: "x"\n', "unterminated front matter"),
        (VALID.replace("outcome: mixed", "nonsense: mixed"), "unknown front-matter field"),
        (VALID.replace("archetypes: [OpeningRange]", "archetypes: OpeningRange"), "must be a flow list"),
        (VALID.replace('title: "A campaign"\n', ""), "is missing"),
        (VALID.replace("outcome: mixed", "outcome"), "cannot parse front-matter line"),
    ],
)
def test_unparseable_front_matter_raises_rather_than_guessing(text: str, expected: str) -> None:
    with pytest.raises(FrontMatterError, match=expected):
        parse_front_matter(text, "a-campaign")


def test_an_unregistered_archetype_raises(tmp_path: Path) -> None:
    write(tmp_path, "a-campaign", VALID.replace("OpeningRange", "NotAnArchetype"))
    with pytest.raises(FrontMatterError, match="unknown archetypes"):
        load(tmp_path)


def test_an_unknown_outcome_raises(tmp_path: Path) -> None:
    write(tmp_path, "a-campaign", VALID.replace("outcome: mixed", "outcome: brilliant"))
    with pytest.raises(FrontMatterError, match="unknown outcome"):
        load(tmp_path)


def test_an_unknown_gate_raises(tmp_path: Path) -> None:
    write(tmp_path, "a-campaign", VALID.replace("gates: [3]", "gates: [9]"))
    with pytest.raises(FrontMatterError, match="unknown gates"):
        load(tmp_path)


def test_empty_lists_are_read_as_empty(tmp_path: Path) -> None:
    """A calibration is about no archetype and reports on no gate; both are legal."""
    write(
        tmp_path,
        "a-campaign",
        VALID.replace("archetypes: [OpeningRange]", "archetypes: []").replace("gates: [3]", "gates: []"),
    )
    finding = load(tmp_path)[0]
    assert finding.archetypes == ()
    assert finding.gates == ()


def test_a_quoted_title_keeps_its_own_quotes(tmp_path: Path) -> None:
    """§M28's title contains "ORB", which must survive the YAML escaping round trip."""
    write(tmp_path, "a-campaign", VALID.replace('title: "A campaign"', 'title: "what \\"ORB\\" names"'))
    assert load(tmp_path)[0].title == 'what "ORB" names'


def test_a_folded_verdict_joins_onto_one_line(tmp_path: Path) -> None:
    write(tmp_path, "a-campaign", VALID.replace("  It cleared the null.", "  It cleared\n  the null."))
    assert load(tmp_path)[0].verdict == "It cleared the null."


def test_a_registry_wide_roster_is_labelled_rather_than_listed(tmp_path: Path) -> None:
    """Seven names would widen every table, and "all but X" stays truthful at six."""
    everything = ", ".join(archetypes.names())
    write(tmp_path, "all-of-them", VALID.replace("[OpeningRange]", f"[{everything}]"))
    register = views(load(tmp_path))[REGISTER]
    assert f"all {len(archetypes.names())}" in register

    six = [n for n in archetypes.names() if n != "OpeningRange"]
    write(tmp_path, "all-of-them", VALID.replace("[OpeningRange]", f"[{', '.join(six)}]"))
    assert "all but OpeningRange" in views(load(tmp_path))[REGISTER]


def test_every_archetype_gets_a_heading_even_with_no_findings(tmp_path: Path) -> None:
    """An archetype registered and never swept must still be visible as unswept."""
    write(tmp_path, "a-campaign", VALID)
    by_archetype = views(load(tmp_path))[BY_ARCHETYPE]
    for name in archetypes.names():
        assert f"## {name}" in by_archetype
    assert "Nothing yet." in by_archetype


def test_every_gate_gets_a_heading_and_ungated_work_has_a_home(tmp_path: Path) -> None:
    write(tmp_path, "gated", VALID)
    write(tmp_path, "ungated", VALID.replace("gates: [3]", "gates: []"))
    by_gate = views(load(tmp_path))[BY_GATE]
    for gate in GATES:
        assert f"## Gate {gate} --" in by_gate
    assert "## Reports on no gate" in by_gate
    assert "ungated.md" in by_gate


def test_a_view_names_the_tool_that_wrote_it(tmp_path: Path) -> None:
    """So an edit lands in the findings file rather than in a file that is overwritten."""
    write(tmp_path, "a-campaign", VALID)
    for content in views(load(tmp_path)).values():
        assert "tools/findings_index.py" in content.splitlines()[0]


def test_sort_key_orders_a_lettered_milestone_before_a_numbered_one() -> None:
    def key(ident: str) -> tuple[int, int, int, str]:
        return Finding(
            slug="x", id=ident, title="t", archetypes=(), issues=(), gates=(), outcome="spec", verdict="v"
        ).sort_key

    assert key("M7a") < key("M7b") < key("M10.1")
    assert key("M26") < key("M26.4") < key("M26.10")
