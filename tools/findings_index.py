"""Generate the findings register's three index views from each file's front matter.

    ./.venv/Scripts/python.exe tools/findings_index.py
    ./.venv/Scripts/python.exe tools/findings_index.py --check

``docs/findings/`` holds one file per campaign. This reads the YAML front matter off each and
writes ``register.md``, ``by-archetype.md`` and ``by-gate.md`` beside them. ``README.md`` is
hand-written and is not touched. ``--check`` exits 1
when a generated file is out of date, which is what ``tests/test_findings_index.py`` runs.

Generated rather than hand-maintained -- ``docs/roadmap.md`` § "Documentation must not carry a
figure that goes stale".
"""

from __future__ import annotations

import argparse
import difflib
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import mdformat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, logsetup

logger = logging.getLogger(__name__)

FINDINGS = Path(__file__).resolve().parent.parent / "docs" / "findings"

SUMMARY = "README.md"
"""The hand-written front door. Never generated, and never read as a finding."""

REGISTER = "register.md"
BY_ARCHETYPE = "by-archetype.md"
BY_GATE = "by-gate.md"

GENERATED = (REGISTER, BY_ARCHETYPE, BY_GATE)
"""The views this tool writes. Skipped when loading, so they are never read as findings."""

NOT_A_FINDING = (SUMMARY, *GENERATED)
"""Everything in the directory that carries no front matter."""

FIELDS = ("id", "title", "archetypes", "issues", "gates", "outcome", "verdict")
LIST_FIELDS = ("archetypes", "issues", "gates")
REQUIRED = ("title", "archetypes", "issues", "gates", "outcome", "verdict")

OUTCOMES = {
    "positive": "cleared the gates it was put to",
    "mixed": "some gates cleared, some not, or the sample cannot settle it",
    "negative": "measured and it does not work",
    "calibration": "a label or threshold fitted, not a strategy result",
    "spec": "what was specified and why, before anything was swept",
    "tooling": "machinery a later campaign reads",
}

GATES = {
    1: "the selection window -- does it make money at all",
    2: "held out -- does it survive a window it was not chosen on",
    3: "the matched null -- does the entry beat a random entry",
    4: "walk-forward, Monte Carlo and the drawdown it has to return",
}

ISSUE_URL = "https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/{}"


class FrontMatterError(ValueError):
    """Raised for front matter this tool cannot parse or validate."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One campaign's file, as the index views read it."""

    slug: str
    id: str | None
    title: str
    archetypes: tuple[str, ...]
    issues: tuple[int, ...]
    gates: tuple[int, ...]
    outcome: str
    verdict: str

    @property
    def cite(self) -> str:
        """How the rest of the repository refers to this finding."""
        return f"§{self.id}" if self.id else f'§ "{self.title}"'

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        """Milestone order, so M7a precedes M10.1 and M26 precedes M26.4."""
        if not self.id:
            return (1, 0, 0, self.title)

        digits = self.id.removeprefix("M")
        major, _, minor = digits.partition(".")
        suffix = "".join(c for c in major if c.isalpha())

        return (0, int(major.rstrip(suffix) or 0), int(minor or 0), suffix)


def parse_front_matter(text: str, slug: str) -> dict[str, object]:
    """Read the closed YAML subset the findings files use, raising on anything else."""
    if not text.startswith("---\n"):
        msg = f"{slug}: no front matter"
        raise FrontMatterError(msg)

    _, _, rest = text.partition("---\n")
    block, sep, _ = rest.partition("\n---\n")
    if not sep:
        msg = f"{slug}: unterminated front matter"
        raise FrontMatterError(msg)

    fields: dict[str, object] = {}
    key = ""
    for line in block.splitlines():
        if line.startswith("  ") and key:
            fields[key] = f"{fields[key]} {line.strip()}".strip()
            continue

        name, colon, value = line.partition(":")
        if not colon:
            msg = f"{slug}: cannot parse front-matter line {line!r}"
            raise FrontMatterError(msg)

        key = name.strip()
        if key not in FIELDS:
            msg = f"{slug}: unknown front-matter field {key!r}; known: {list(FIELDS)}"
            raise FrontMatterError(msg)

        value = value.strip()
        if key in LIST_FIELDS:
            fields[key] = _parse_list(value, key, slug)
        elif value == ">-":
            fields[key] = ""
        else:
            fields[key] = _unquote(value)

    missing = [f for f in REQUIRED if f not in fields]
    if missing:
        msg = f"{slug}: front matter is missing {missing}"
        raise FrontMatterError(msg)

    return fields


def _unquote(value: str) -> str:
    """Read a double-quoted YAML scalar, so a title may hold a quote of its own."""
    if not (value.startswith('"') and value.endswith('"') and len(value) > 1):
        return value

    return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")


def _parse_list(value: str, key: str, slug: str) -> list[str]:
    """Read a flow-style list, which is the only list form the files use."""
    if not (value.startswith("[") and value.endswith("]")):
        msg = f"{slug}: {key} must be a flow list, got {value!r}"
        raise FrontMatterError(msg)

    inner = value[1:-1].strip()

    return [item.strip() for item in inner.split(",")] if inner else []


def load(directory: Path = FINDINGS) -> list[Finding]:
    """Read every findings file, validated, in milestone order."""
    known = set(archetypes.names())
    findings: list[Finding] = []
    for path in sorted(directory.glob("*.md")):
        if path.name in NOT_A_FINDING:
            continue

        fields = parse_front_matter(path.read_text(encoding="utf-8"), path.stem)
        named = [str(a) for a in fields["archetypes"]]  # type: ignore[union-attr]
        unknown = sorted(set(named) - known)
        if unknown:
            msg = f"{path.stem}: unknown archetypes {unknown}; registered: {sorted(known)}"
            raise FrontMatterError(msg)

        outcome = str(fields["outcome"])
        if outcome not in OUTCOMES:
            msg = f"{path.stem}: unknown outcome {outcome!r}; known: {sorted(OUTCOMES)}"
            raise FrontMatterError(msg)

        gates = [int(g) for g in fields["gates"]]  # type: ignore[union-attr]
        unknown_gates = sorted(set(gates) - set(GATES))
        if unknown_gates:
            msg = f"{path.stem}: unknown gates {unknown_gates}; known: {sorted(GATES)}"
            raise FrontMatterError(msg)

        findings.append(
            Finding(
                slug=path.stem,
                id=str(fields["id"]) if fields.get("id") else None,
                title=str(fields["title"]),
                archetypes=tuple(named),
                issues=tuple(int(i) for i in fields["issues"]),  # type: ignore[union-attr]
                gates=tuple(gates),
                outcome=outcome,
                verdict=str(fields["verdict"]),
            )
        )

    return sorted(findings, key=lambda f: f.sort_key)


def _link(finding: Finding) -> str:
    """The finding's title, linked to its file."""
    return f"[{finding.title}]({finding.slug}.md)"


def _archetype_label(finding: Finding) -> str:
    """The roster, compactly, so a registry-wide campaign does not widen the table."""
    registered = set(archetypes.names())
    covered = set(finding.archetypes)
    if not covered:
        return "--"

    missing = sorted(registered - covered)
    if not missing:
        return f"all {len(registered)}"

    if len(missing) == 1:
        return f"all but {missing[0]}"

    return ", ".join(finding.archetypes)


def _issues(finding: Finding) -> str:
    """The finding's issues as reference-style links."""
    return ", ".join(f"[#{n}]" for n in finding.issues) if finding.issues else "--"


def _definitions(findings: list[Finding]) -> list[str]:
    """Link definitions for every issue the rendered view refers to."""
    used = sorted({n for f in findings for n in f.issues})

    return ["", *[f"[#{n}]: {ISSUE_URL.format(n)}" for n in used]]


def _header() -> list[str]:
    """The line every generated view carries, so nobody edits one by hand."""
    return [
        "<!-- Generated by tools/findings_index.py. Edit the findings files, not this one. -->",
        "",
    ]


def render_register(findings: list[Finding]) -> str:
    """The register: every campaign, its verdict, and how to cite it."""
    out = [
        *_header(),
        "# The register",
        "",
        "Every campaign this project has run, what it measured and what it returned. One file per",
        "campaign; the prose is the campaign's own and moved here unchanged.",
        "",
        "**Every figure in these files is one dated run over the archive as it stood, re-derivable from**",
        "**`results/campaign/*.duckdb` and the `tools/campaign_*.py` the file names -- not a standing**",
        "**property.** Quote the file rather than any summary of it.",
        "",
        "Start at [the summary](README.md) for what any of this means for trading. Two other views of",
        "the same set: [by archetype](by-archetype.md), [by gate](by-gate.md).",
        "",
        "## What the columns mean",
        "",
        "**Cite** is how the rest of the repository points at a finding, and it does not change when a",
        "file is renamed. `docs/roadmap.md` keeps a stub at each one so an existing pointer still",
        "resolves.",
        "",
        "**Gates** are the four the standing rubric asks of any result, in the order a campaign runs",
        "them:",
        "",
        *[f"{n}. **Gate {n}** -- {text}" for n, text in sorted(GATES.items())],
        "",
        "**Outcome:**",
        "",
        *[f"- `{name}` -- {text}" for name, text in OUTCOMES.items()],
        "",
        "## Every campaign",
        "",
        "| cite | campaign | archetypes | gates | outcome | issues |",
        "| ---- | -------- | ---------- | ----- | ------- | ------ |",
    ]
    for finding in findings:
        gates = ", ".join(str(g) for g in finding.gates) if finding.gates else "--"
        out.append(
            f"| `{finding.cite}` | {_link(finding)} | {_archetype_label(finding)} | {gates} "
            f"| `{finding.outcome}` | {_issues(finding)} |"
        )
    out.extend(["", "## The verdicts", ""])
    for finding in findings:
        out.extend([f"**{_link(finding)}**", "", finding.verdict, ""])
    out.extend(_definitions(findings))

    return "\n".join(out).rstrip() + "\n"


def render_by_archetype(findings: list[Finding]) -> str:
    """Every finding that touches each archetype, so one archetype reads as one story."""
    out = [
        *_header(),
        "# Findings by archetype",
        "",
        "The same campaigns as the [register](register.md), grouped by what they were run over. A",
        "registry-wide campaign appears under every archetype it covered.",
        "",
    ]
    for name in archetypes.names():
        covering = [f for f in findings if name in f.archetypes]
        out.extend([f"## {name}", ""])
        if not covering:
            out.extend(["Nothing yet.", ""])
            continue

        out.extend(
            [
                "| cite | campaign | outcome | verdict |",
                "| ---- | -------- | ------- | ------- |",
            ]
        )
        out.extend(f"| `{f.cite}` | {_link(f)} | `{f.outcome}` | {f.verdict} |" for f in covering)
        out.append("")

    loose = [f for f in findings if not f.archetypes]
    out.extend(["## Not about one archetype", ""])
    if loose:
        out.extend(
            [
                "Condition labels, thresholds and gate machinery. Every archetype is read through",
                "these, so a result that turns on one of them is really a result about the label.",
                "",
                "| cite | campaign | outcome | verdict |",
                "| ---- | -------- | ------- | ------- |",
            ]
        )
        out.extend(f"| `{f.cite}` | {_link(f)} | `{f.outcome}` | {f.verdict} |" for f in loose)
        out.append("")
    else:
        out.extend(["Nothing yet.", ""])

    out.extend(_definitions(findings))

    return "\n".join(out).rstrip() + "\n"


def render_by_gate(findings: list[Finding]) -> str:
    """Every finding that reports on each gate, which is what "has anything passed" asks."""
    out = [
        *_header(),
        "# Findings by gate",
        "",
        "The same campaigns as the [register](register.md), grouped by which of the four gates each",
        "one reports on. A campaign reporting on gate 3 appears here whether it passed or failed --",
        "the `outcome` column and the file itself are what say which.",
        "",
    ]
    for gate, text in sorted(GATES.items()):
        reporting = [f for f in findings if gate in f.gates]
        out.extend([f"## Gate {gate} -- {text}", ""])
        if not reporting:
            out.extend(["Nothing yet.", ""])
            continue

        out.extend(
            [
                "| cite | campaign | archetypes | outcome |",
                "| ---- | -------- | ---------- | ------- |",
            ]
        )
        out.extend(f"| `{f.cite}` | {_link(f)} | {_archetype_label(f)} | `{f.outcome}` |" for f in reporting)
        out.append("")
    reporting_none = [f for f in findings if not f.gates]
    out.extend(["## Reports on no gate", ""])
    if reporting_none:
        out.extend(
            [
                "Specifications, calibrations and tooling -- the work a gated campaign is built on.",
                "",
                "| cite | campaign | outcome |",
                "| ---- | -------- | ------- |",
            ]
        )
        out.extend(f"| `{f.cite}` | {_link(f)} | `{f.outcome}` |" for f in reporting_none)
        out.append("")
    else:
        out.extend(["Nothing yet.", ""])

    out.extend(_definitions(findings))

    return "\n".join(out).rstrip() + "\n"


def formatted(markdown: str) -> str:
    """Canonicalise exactly as ``mdformat`` would, so the two checks cannot disagree.

    The options mirror `.mdformat.toml`, which only the command line discovers.
    """
    return mdformat.text(markdown, options={"number": True, "wrap": "no"}, extensions={"gfm"})


def views(findings: list[Finding]) -> dict[str, str]:
    """Each generated file's name and the content it should hold."""
    return {
        REGISTER: formatted(render_register(findings)),
        BY_ARCHETYPE: formatted(render_by_archetype(findings)),
        BY_GATE: formatted(render_by_gate(findings)),
    }


def main(argv: list[str]) -> int:
    """Write the three views, or check them and report what is out of date."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if a view is out of date")
    parser.add_argument("--directory", type=Path, default=FINDINGS)
    args = parser.parse_args(argv[1:])
    logsetup.configure(__name__)

    findings = load(args.directory)
    logger.info("read %d findings from %s", len(findings), args.directory)

    stale: list[str] = []
    for name, content in views(findings).items():
        path = args.directory / name
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == content:
            continue

        if not args.check:
            path.write_text(content, encoding="utf-8")
            logger.info("wrote %s", path)
            continue

        stale.append(name)
        diff = difflib.unified_diff(
            current.splitlines(),
            content.splitlines(),
            f"{name} (committed)",
            f"{name} (generated)",
            lineterm="",
        )
        logger.error("%s is out of date:\n%s", name, "\n".join(diff))

    if stale:
        logger.error("run tools/findings_index.py to regenerate: %s", ", ".join(stale))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
