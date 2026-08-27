"""Check commit messages against the house rules in CONTRIBUTING.md, "Commits".

Two callers, and they deliberately check different text:

    # what GitHub squashes onto main -- the PR title, plus the suffix it appends
    python tools/lint_commit_messages.py --subject-suffix " (#165)" --message-file pr.txt

    # every commit on the branch, NUL-separated on stdin
    git log --format=%B -z origin/main..HEAD | python tools/lint_commit_messages.py --stdin

Exits 1 when any error-level rule fails; warnings never fail the run. ``--github`` emits
workflow annotations alongside the text.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SUBJECT_MAX_LENGTH = 72
"""Where GitHub truncates a subject with an ellipsis. Measured as the subject lands, suffix included."""

GENERATED_SUBJECT_PREFIXES = ("Merge ", "Revert ")
"""Subjects GitHub writes itself. Exempt from length, because their shape is not ours to pick."""

CONVENTIONAL_TYPES = frozenset("build chore ci docs feat fix perf refactor revert style test".split())
"""Accepted but not recommended, so a bare imperative subject stays the house style."""

CONVENTIONAL_PREFIX_PATTERN = re.compile(r"^(?P<type>\w+)(\([^)]*\))?!?: ")

STRAY_PREFIX_PATTERN = re.compile(r"^(?:\[[^\]]*\]\s*|[^\s:]+:\s|\S+\s+--\s)")
"""``Docs:``, ``instruments.py:``, ``[DevTools]`` and ``M17.4 --``: the old conventions."""

BOT_SCOPE_PATTERN = re.compile(r"^\w+\(deps[^)]*\)!?: ")
"""Dependabot writes its own titles and they run past 72. Not ours to control either."""

NON_IMPERATIVE_FIRST_WORDS = frozenset(
    """
    added adds adding
    allowed allows allowing
    applied applies applying
    bumped bumps bumping
    changed changes changing
    cleaned cleans cleaning
    corrected corrects correcting
    created creates creating
    deleted deletes deleting
    deprecated deprecates deprecating
    disabled disables disabling
    documented documents documenting
    dropped drops dropping
    enabled enables enabling
    ensured ensures ensuring
    extracted extracts extracting
    fixed fixes fixing
    handled handles handling
    implemented implements implementing
    improved improves improving
    included includes including
    introduced introduces introducing
    made makes making
    merged merges merging
    migrated migrates migrating
    modified modifies modifying
    moved moves moving
    prevented prevents preventing
    refactored refactors refactoring
    released releases releasing
    removed removes removing
    renamed renames renaming
    replaced replaces replacing
    resolved resolves resolving
    restored restores restoring
    reverted reverts reverting
    simplified simplifies simplifying
    started starts starting
    stopped stops stopping
    supported supports supporting
    switched switches switching
    tested tests testing
    tidied tidies tidying
    updated updates updating
    used uses using
    wrote writes writing
    """.split()
)
"""The offenders CONTRIBUTING.md names, and their nearest relatives."""

IMPERATIVES_ENDING_IN_S = frozenset(
    """
    address bypass compress cross discuss dismiss express focus
    harness miss pass process progress stress suppress toss
    """.split()
)
"""Imperative verbs the third-person -s fallback would otherwise reject."""

IMPERATIVES_ENDING_IN_ED = frozenset(
    """
    bleed breed embed exceed feed need proceed read seed shed speed spread succeed
    """.split()
)
"""Imperative verbs the past-tense -ed fallback would otherwise reject."""


@dataclass(frozen=True)
class Finding:
    """One rule failing on one message."""

    rule: str
    message: str
    is_error: bool


def split_conventional_prefix(subject: str) -> tuple[str | None, str]:
    """Split a valid ``type(scope):`` prefix off the subject, returning the type and the rest.

    The type must be one the Conventional Commits spec names. ``Docs:`` and
    ``instruments.py:`` are not prefixes, they are a subject that fails to start with a verb.
    """
    match = CONVENTIONAL_PREFIX_PATTERN.match(subject)
    if match and match.group("type") in CONVENTIONAL_TYPES:
        return match.group("type"), subject[match.end() :]
    return None, subject


def first_word(subject: str) -> str:
    """The first word of the subject, lowercased and stripped of surrounding punctuation."""
    word = subject.strip().split(" ", maxsplit=1)[0]
    return word.strip("\"'`*_.,:;()[]").lower()


def is_non_imperative(word: str) -> bool:
    """Whether the subject's first word reads as past tense, third person or a gerund.

    Conservative by design: it misses novel verbs rather than flagging correct ones,
    because a false positive here blocks a merge. CONTRIBUTING.md, "Commits".
    """
    if not word.isalpha():
        return False
    if word in NON_IMPERATIVE_FIRST_WORDS:
        return True
    if word.endswith("ing"):
        # No morphological fallback here: "reasoning", "handling" and "caching" are nouns in
        # this codebase's vocabulary, and blocking a correct subject is worse than missing one.
        return False
    if word.endswith("ed"):
        return word not in IMPERATIVES_ENDING_IN_ED
    if word.endswith("s") and not word.endswith("ss"):
        return word not in IMPERATIVES_ENDING_IN_S
    return False


def check_subject_shape(remainder: str, conventional_type: str | None) -> list[Finding]:
    """Whether the subject starts with a verb, once a valid conventional prefix is removed."""
    if conventional_type is not None:
        return []

    stray = STRAY_PREFIX_PATTERN.match(remainder)
    if stray:
        return [
            Finding(
                "subject-shape",
                f"{stray.group(0).strip()!r} is not a prefix the rules recognise. Start with a verb "
                "in the imperative mood, or with a Conventional Commits type.",
                is_error=True,
            ),
        ]

    if not first_word(remainder).isalpha():
        return [
            Finding(
                "subject-shape",
                "The subject must begin with a verb in the imperative mood.",
                is_error=True,
            ),
        ]
    return []


def check_subject(subject: str, suffix: str) -> list[Finding]:
    """Apply every subject-level rule."""
    if not subject.strip():
        return [Finding("subject-empty", "The subject line is empty.", is_error=True)]

    findings: list[Finding] = []
    if subject != subject.strip():
        findings.append(
            Finding("subject-trim", "The subject has leading or trailing whitespace.", is_error=True),
        )
    if subject.startswith(GENERATED_SUBJECT_PREFIXES):
        return findings

    findings.extend(check_subject_length(subject, suffix))
    if subject.rstrip().endswith("."):
        findings.append(Finding("subject-full-stop", "The subject ends in a full stop.", is_error=True))

    conventional_type, remainder = split_conventional_prefix(subject.strip())
    if conventional_type is not None and not BOT_SCOPE_PATTERN.match(subject):
        findings.append(
            Finding(
                "subject-conventional-prefix",
                f'"{conventional_type}:" is accepted but not the house style; a bare imperative '
                "subject is preferred.",
                is_error=False,
            ),
        )

    shape = check_subject_shape(remainder, conventional_type)
    findings.extend(shape)
    if shape:
        return findings

    word = first_word(remainder)
    if is_non_imperative(word):
        findings.append(
            Finding(
                "subject-imperative",
                f'The subject opens with "{word}". Use the imperative mood: "Add", not "Added" or "Adds".',
                is_error=True,
            ),
        )
    return findings


def check_subject_length(subject: str, suffix: str) -> list[Finding]:
    """Measure the subject as it will land, including the suffix GitHub appends."""
    if BOT_SCOPE_PATTERN.match(subject):
        return []

    landed = f"{subject}{suffix}"
    if len(landed) <= SUBJECT_MAX_LENGTH:
        return []

    becomes = f", which becomes {len(landed)} once GitHub appends {suffix!r}" if suffix else ""
    return [
        Finding(
            "subject-max-length",
            f"The subject is {len(subject)} characters{becomes}. The limit is {SUBJECT_MAX_LENGTH}.",
            is_error=True,
        ),
    ]


def check_body(lines: list[str]) -> list[Finding]:
    """The one structural body rule. Wrapping is deliberately not checked.

    The body that reaches ``main`` is the pull request description, which GitHub renders as
    markdown and which is never hard-wrapped. CONTRIBUTING.md, "Commits".
    """
    if not any(line.strip() for line in lines):
        return []
    if not lines[0].strip():
        return []
    return [
        Finding(
            "body-leading-blank",
            "The body must be separated from the subject by a blank line.",
            is_error=True,
        ),
    ]


def check_message(message: str, suffix: str = "") -> list[Finding]:
    """Apply every rule to one whole commit message."""
    lines = message.rstrip().splitlines()
    if not lines:
        return [Finding("subject-empty", "The message is empty.", is_error=True)]
    return check_subject(lines[0], suffix) + check_body(lines[1:])


def emit(text: str) -> None:
    """Write one line to stdout, which logging would prefix."""
    sys.stdout.write(f"{text}\n")


def report(subject: str, findings: list[Finding], *, github: bool) -> None:
    """Print one message's findings, as text and optionally as workflow annotations."""
    if not findings:
        emit(f"  ok  {subject}")
        return

    emit(f"  !!  {subject}")
    for finding in findings:
        level = "error" if finding.is_error else "warning"
        emit(f"      {level}: {finding.message} [{finding.rule}]")
        if github:
            emit(f"::{level} title=commit message ({finding.rule})::{subject}{chr(10)}{finding.message}")


def read_messages(args: argparse.Namespace) -> list[str]:
    """Collect the messages to check, from stdin or from a file."""
    if args.stdin:
        return [chunk for chunk in sys.stdin.read().split("\0") if chunk.strip()]
    return [Path(args.message_file).read_text(encoding="utf-8")]


def build_parser() -> argparse.ArgumentParser:
    """The command line, one source of messages and two presentation switches."""
    parser = argparse.ArgumentParser(description="Lint commit messages against CONTRIBUTING.md.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message-file", help="a file holding one whole commit message")
    source.add_argument("--stdin", action="store_true", help="read NUL-separated messages from stdin")
    parser.add_argument(
        "--subject-suffix",
        default="",
        help="text GitHub appends to the subject, for example ' (#165)'",
    )
    parser.add_argument("--github", action="store_true", help="also emit GitHub workflow annotations")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check every supplied message and return the process exit code."""
    args = build_parser().parse_args(argv)
    messages = read_messages(args)
    if not messages:
        emit("No commit messages to check.")
        return 0

    errors = 0
    for message in messages:
        findings = check_message(message, args.subject_suffix)
        errors += sum(1 for finding in findings if finding.is_error)
        subject = message.strip().splitlines()[0] if message.strip() else "(empty)"
        report(subject, findings, github=args.github)

    emit("")
    if errors:
        emit(f'{errors} error(s). The rules are in CONTRIBUTING.md, "Commits".')
        return 1
    emit(f"{len(messages)} message(s) checked, no errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
