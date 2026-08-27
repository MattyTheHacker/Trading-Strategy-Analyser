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
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
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

PROBE_OBJECT = "the thing"
"""Filler so the probe docstring is a sentence. D401 only ever reads its first word."""

D401_REPORT_PATTERN = re.compile(r'D401 [^"]*"(\w+) ' + PROBE_OBJECT + r'\."')

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


def ruff_executable() -> str:
    """Where ruff is, preferring the interpreter's own environment over the PATH."""
    scripts = Path(sys.executable).parent
    for candidate in (scripts / "ruff.exe", scripts / "ruff", scripts / "Scripts" / "ruff.exe"):
        if candidate.exists():
            return str(candidate)
    found = shutil.which("ruff")
    if found:
        return found
    message = "ruff is needed for the imperative-mood check. Install it: pip install -e '.[dev]'"
    raise RuntimeError(message)


def non_imperative_words(words: Iterable[str]) -> frozenset[str]:
    """Ask ruff's D401 which of these opening words are not in the imperative mood.

    Reuses the stemmer and wordlist behind ruff's own rule instead of keeping a second copy
    here. Each word is posed as a one-line docstring, which is the only text D401 reads.
    ``docs/roadmap.md`` is not the place for this; CONTRIBUTING.md, "Commits", is.
    """
    vocabulary = sorted({word for word in words if word.isalpha()})
    if not vocabulary:
        return frozenset()

    stanzas = [
        f'def probe_{index}() -> None:\n    """{word} {PROBE_OBJECT}."""\n'
        for index, word in enumerate(vocabulary)
    ]
    with tempfile.TemporaryDirectory() as directory:
        probe_path = Path(directory) / "probe.py"
        probe_path.write_text("\n\n".join(stanzas), encoding="utf-8")
        completed = subprocess.run(  # noqa: S603
            [
                ruff_executable(),
                "check",
                "--isolated",
                "--select",
                "D401",
                "--output-format",
                "concise",
                "--no-cache",
                str(probe_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    if completed.returncode not in (0, 1):
        message = f"ruff could not run the D401 check: {completed.stderr.strip()}"
        raise RuntimeError(message)
    return frozenset(D401_REPORT_PATTERN.findall(completed.stdout or ""))


def verb_candidate(subject: str) -> str:
    """The word whose mood is judged: the first one after any conventional prefix."""
    _, remainder = split_conventional_prefix(subject.strip())
    return first_word(remainder)


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


def check_subject(subject: str, suffix: str, non_imperative: frozenset[str]) -> list[Finding]:
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
    if word in non_imperative:
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


def check_message(
    message: str,
    suffix: str = "",
    non_imperative: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Apply every rule to one whole commit message."""
    lines = message.rstrip().splitlines()
    if not lines:
        return [Finding("subject-empty", "The message is empty.", is_error=True)]
    return check_subject(lines[0], suffix, non_imperative) + check_body(lines[1:])


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

    # One ruff invocation for the whole run, not one per message.
    subjects = [message.strip().splitlines()[0] for message in messages if message.strip()]
    non_imperative = non_imperative_words(verb_candidate(subject) for subject in subjects)

    errors = 0
    for message in messages:
        findings = check_message(message, args.subject_suffix, non_imperative)
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
