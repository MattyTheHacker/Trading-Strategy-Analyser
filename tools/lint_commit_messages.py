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
"""Where GitHub splits the subject and moves the remainder into the body, suffix included."""

SUBJECT_WARN_LENGTH = 55
"""Where the repository file table clips it instead. Warning-level: CONTRIBUTING.md, "Commits"."""

GENERATED_SUBJECT_PREFIXES = ("Merge ", "Revert ")
"""Subjects GitHub writes itself. Exempt from length, because their shape is not ours to pick."""

CONVENTIONAL_TYPES = frozenset("build chore ci docs feat fix perf refactor revert style test".split())
"""Accepted but not recommended, so a bare imperative subject stays the house style."""

CONVENTIONAL_PREFIX_PATTERN = re.compile(r"^(?P<type>\w+)(\([^)]*\))?!?: ")

STRAY_PREFIX_PATTERN = re.compile(r"^(?:\[[^\]]*\]\s*|[^\s:]+:\s|\S+\s+--\s)")
"""``Docs:``, ``instruments.py:``, ``[DevTools]`` and ``M17.4 --``: the old conventions."""

ALLOWED_VERBS = (
    "Add",
    "Bump",
    "Document",
    "Fix",
    "Move",
    "Port",
    "Reconcile",
    "Refactor",
    "Remove",
    "Update",
)
"""The whole subject vocabulary. CONTRIBUTING.md, "Commits", maps the near-misses onto it."""

ALLOWED_VERB_SET = frozenset(verb.lower() for verb in ALLOWED_VERBS)

BOT_SCOPE_PATTERN = re.compile(r"^\w+\(deps[^)]*\)!?: ")
"""Dependabot writes its own titles and they run past 72. Not ours to control either."""


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


def verb_candidate(subject: str) -> str:
    """The word whose mood is judged: the first one after any conventional prefix."""
    _, remainder = split_conventional_prefix(subject.strip())
    return first_word(remainder)


def check_subject_shape(remainder: str, conventional_type: str | None) -> list[Finding]:
    """Catch the old prefix conventions, which need a clearer message than the verb rule gives."""
    if conventional_type is not None:
        return []

    stray = STRAY_PREFIX_PATTERN.match(remainder)
    if not stray:
        return []
    return [
        Finding(
            "subject-shape",
            f"{stray.group(0).strip()!r} is not a prefix the rules recognise. Start with one of "
            f"{', '.join(ALLOWED_VERBS)}, or with a Conventional Commits type.",
            is_error=True,
        ),
    ]


def check_subject_verb(remainder: str, conventional_type: str | None) -> list[Finding]:
    """The subject must open with one of the ten verbs, unless a conventional type stands in.

    An allowlist of base forms settles the mood by construction: "Added" is simply not one of
    them, so no stemmer or mood heuristic is needed.
    """
    if conventional_type is not None:
        return []

    word = first_word(remainder)
    if word in ALLOWED_VERB_SET:
        return []
    opener = f'"{word}"' if word else "nothing"
    return [
        Finding(
            "subject-verb",
            f"The subject opens with {opener}. Start with one of: {', '.join(ALLOWED_VERBS)}.",
            is_error=True,
        ),
    ]


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
                f'"{conventional_type}:" is accepted but not the house style; one of '
                f"{', '.join(ALLOWED_VERBS)} is preferred.",
                is_error=False,
            ),
        )

    shape = check_subject_shape(remainder, conventional_type)
    if shape:
        return [*findings, *shape]
    return findings + check_subject_verb(remainder, conventional_type)


def check_subject_length(subject: str, suffix: str) -> list[Finding]:
    """Measure the subject as it will land, including the suffix GitHub appends."""
    if BOT_SCOPE_PATTERN.match(subject):
        return []

    landed = f"{subject}{suffix}"
    if len(landed) <= SUBJECT_WARN_LENGTH:
        return []

    becomes = f", which becomes {len(landed)} once GitHub appends {suffix!r}" if suffix else ""
    if len(landed) > SUBJECT_MAX_LENGTH:
        return [
            Finding(
                "subject-max-length",
                f"The subject is {len(subject)} characters{becomes}. The limit is {SUBJECT_MAX_LENGTH}.",
                is_error=True,
            ),
        ]
    return [
        Finding(
            "subject-clipped",
            f"The subject is {len(subject)} characters{becomes}. Past {SUBJECT_WARN_LENGTH} the "
            f"repository file table clips it.",
            is_error=False,
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
