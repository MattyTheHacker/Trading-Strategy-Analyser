import io
from pathlib import Path

import pytest

from tools.lint_commit_messages import (
    ALLOWED_VERBS,
    CONVENTIONAL_TYPES,
    SUBJECT_MAX_LENGTH,
    check_message,
    first_word,
    main,
    verb_candidate,
)


def rules(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix)}


def errors(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix) if finding.is_error}


@pytest.mark.parametrize("verb", ALLOWED_VERBS)
def test_every_verb_in_the_vocabulary_is_accepted(verb: str) -> None:
    assert check_message(f"{verb} the thing that needed doing") == []


@pytest.mark.parametrize(
    "subject",
    [
        "Add the phase filter to the sweep axes",
        "Reconcile InsideBar against its NT8 trade list",
        "Port PullBackAndGo.cs as the long-side proof",
        "Document guard clauses as the house control-flow style",
        "Refactor the bracket engine behind one entry point",
    ],
)
def test_real_subjects_in_the_house_style_pass(subject: str) -> None:
    assert check_message(subject) == []


def test_the_vocabulary_is_case_insensitive() -> None:
    assert errors("add the phase filter") == set()
    assert errors("ADD the phase filter") == set()


@pytest.mark.parametrize("subject", ["Added the filter", "Adds the filter", "Adding the filter"])
def test_the_mood_is_settled_by_the_vocabulary_not_a_heuristic(subject: str) -> None:
    # No stemmer and no mood rule: the inflected forms simply are not in the list.
    assert "subject-verb" in errors(subject)


@pytest.mark.parametrize("subject", ["Built the filter", "Rewrote the engine", "Sent the order"])
def test_irregular_past_tense_fails_too(subject: str) -> None:
    # The gap the ruff-backed check could not close, closed by construction.
    assert "subject-verb" in errors(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "Derive the session end from the observed last bar",
        "Gate dependency bumps in CI with three pins",
        "Store discretionary notes in a sidecar",
        "Implement the archetype registry",
    ],
)
def test_verbs_outside_the_vocabulary_are_rejected(subject: str) -> None:
    # Deliberate: precise-but-unlisted verbs are the cost of a fixed vocabulary.
    assert "subject-verb" in errors(subject)


def test_the_verb_error_names_the_whole_vocabulary() -> None:
    (finding,) = check_message("Derive the session end")
    assert finding.rule == "subject-verb"
    for verb in ALLOWED_VERBS:
        assert verb in finding.message


@pytest.mark.parametrize("conventional_type", sorted(CONVENTIONAL_TYPES))
def test_a_conventional_type_stands_in_for_the_verb(conventional_type: str) -> None:
    # Agreed design: the type satisfies the requirement, so the word after it is unconstrained.
    findings = check_message(f"{conventional_type}: derive the session end")
    assert [f.rule for f in findings] == ["subject-conventional-prefix"]
    assert not findings[0].is_error


@pytest.mark.parametrize(
    "subject",
    [
        "fix(sim): derive the session end from the last bar",
        "refactor(sweep)!: take resolution and contract",
    ],
)
def test_a_scope_and_a_breaking_marker_are_accepted(subject: str) -> None:
    assert errors(subject) == set()


def test_dependabot_raises_neither_the_warning_nor_the_ceiling() -> None:
    assert check_message("build(deps): bump numba from 0.66.0 to 0.67.0", " (#153)") == []
    bot = "build(deps): bump the python group across 1 directory with 5 updates"
    assert len(bot) + len(" (#153)") > SUBJECT_MAX_LENGTH
    assert errors(bot, " (#153)") == set()


@pytest.mark.parametrize(
    "subject",
    [
        "M17.4 -- sweep_axes takes resolution and contract",
        "Docs: record the M15 findings and stop quoting figures",
        "instruments.py: route every monetary figure through the spec",
        "[DevTools] Remove the dead profiler code",
        "WIP: still poking at the bracket engine",
    ],
)
def test_the_old_prefix_conventions_get_their_own_message(subject: str) -> None:
    assert "subject-shape" in errors(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "Add a guard: the sweep must not rank free money",
        "Fix the 09:30 bar label",
    ],
)
def test_a_colon_later_in_the_subject_is_not_read_as_a_prefix(subject: str) -> None:
    assert check_message(subject) == []


def test_verb_candidate_looks_past_a_conventional_prefix() -> None:
    assert verb_candidate("fix(sim): derive the session end") == "derive"
    assert verb_candidate("Add the session end") == "add"
    assert first_word("Add the phase filter") == "add"


def test_the_suffix_github_appends_counts_towards_the_limit() -> None:
    # Exactly at the ceiling bare, over it once GitHub appends the number.
    subject = "Add the session end derivation from the observed last bar".ljust(SUBJECT_MAX_LENGTH, "x")
    assert len(subject) <= SUBJECT_MAX_LENGTH
    assert errors(subject) == set()
    assert "subject-max-length" in errors(subject, " (#164)")


def test_the_reported_length_is_the_bare_subject_and_the_landed_one() -> None:
    # Exactly at the ceiling bare, over it once GitHub appends the number.
    subject = "Add the session end derivation from the observed last bar".ljust(SUBJECT_MAX_LENGTH, "x")
    (finding,) = check_message(subject, " (#164)")
    assert f"is {len(subject)} characters" in finding.message
    assert f"becomes {len(subject) + len(' (#164)')}" in finding.message


def test_a_subject_at_the_ceiling_passes_and_one_past_it_fails() -> None:
    assert "subject-max-length" not in errors("Add " + "x" * (SUBJECT_MAX_LENGTH - 4))
    assert "subject-max-length" in errors("Add " + "x" * (SUBJECT_MAX_LENGTH - 3))


@pytest.mark.parametrize(
    ("message", "rule"),
    [
        ("", "subject-empty"),
        ("   ", "subject-empty"),
        ("Add the phase filter.", "subject-full-stop"),
        ("  Add the phase filter", "subject-trim"),
    ],
)
def test_subject_level_rules_each_fire(message: str, rule: str) -> None:
    assert rule in errors(message)


def test_a_body_must_be_separated_from_the_subject_by_a_blank_line() -> None:
    assert "body-leading-blank" in errors("Add the phase filter\nWhy it was needed")
    assert errors("Add the phase filter\n\nWhy it was needed") == set()


def test_body_line_length_is_deliberately_not_checked() -> None:
    # The body reaching main is the PR description, which is never hard-wrapped.
    unwrapped = "w" * 400 + " and more words after it"
    assert check_message(f"Add the phase filter\n\n{unwrapped}") == []


@pytest.mark.parametrize(
    "subject",
    ["Merge branch 'main' into topic", 'Revert "Add the phase filter that was wrong all along"'],
)
def test_github_generated_subjects_are_exempt(subject: str) -> None:
    assert errors(f"{subject}{'!' * 60}") == set()


def test_a_clean_message_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "msg.txt"
    path.write_text("Add the phase filter\n\nBecause the sweep could not express it.\n", encoding="utf-8")
    assert main(["--message-file", str(path)]) == 0
    assert "no errors" in capsys.readouterr().out


def test_a_dirty_message_exits_one_and_names_the_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "msg.txt"
    path.write_text("Added the phase filter\n", encoding="utf-8")
    assert main(["--message-file", str(path)]) == 1
    assert "subject-verb" in capsys.readouterr().out


def test_the_github_switch_emits_a_workflow_annotation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "msg.txt"
    path.write_text("Added the phase filter\n", encoding="utf-8")
    main(["--message-file", str(path), "--github"])
    assert "::error title=commit message (subject-verb)::" in capsys.readouterr().out


def test_stdin_checks_every_nul_separated_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("Add the filter\0Added the filter\0"))
    assert main(["--stdin"]) == 1
    assert capsys.readouterr().out.count("error:") == 1


def test_an_empty_stdin_stream_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["--stdin"]) == 0
    assert "No commit messages" in capsys.readouterr().out


def test_a_source_must_be_given() -> None:
    with pytest.raises(SystemExit):
        main([])
