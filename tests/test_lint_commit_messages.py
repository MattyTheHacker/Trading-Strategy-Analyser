import io
from pathlib import Path

import pytest

from tools.lint_commit_messages import (
    SUBJECT_MAX_LENGTH,
    check_message,
    first_word,
    is_non_imperative,
    main,
)


def rules(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix)}


def errors(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix) if finding.is_error}


def test_a_subject_matching_the_house_rules_produces_nothing() -> None:
    assert rules("Derive the session end from the observed last bar, not the template") == set()


@pytest.mark.parametrize(
    "subject",
    [
        "Add the phase filter",
        "Gate dependency bumps in CI with three pins that need no data",
        "Reconcile InsideBar against its NT8 trade list",
        "build(deps): bump the python group across 1 directory with 5 updates",
    ],
)
def test_real_subjects_from_this_repo_pass(subject: str) -> None:
    assert errors(subject) == set()


@pytest.mark.parametrize(
    ("subject", "offender"),
    [
        ("Added the phase filter", "added"),
        ("Adds the phase filter", "adds"),
        ("Adding the phase filter", "adding"),
        ("Fixed the fill rule", "fixed"),
        ("Refactoring the bracket engine", "refactoring"),
        ("build(deps): bumps the python group", "bumps"),
    ],
)
def test_past_tense_third_person_and_gerunds_are_rejected(subject: str, offender: str) -> None:
    assert "subject-imperative" in errors(subject)
    assert offender in check_message(subject)[0].message


@pytest.mark.parametrize(
    "word",
    ["embed", "exceed", "feed", "need", "proceed", "read", "seed", "speed", "spread", "succeed"],
)
def test_imperatives_ending_in_ed_are_not_mistaken_for_past_tense(word: str) -> None:
    assert not is_non_imperative(word)


@pytest.mark.parametrize("word", ["address", "bypass", "discuss", "express", "pass", "process"])
def test_imperatives_ending_in_s_are_not_mistaken_for_third_person(word: str) -> None:
    assert not is_non_imperative(word)


@pytest.mark.parametrize("word", ["bring", "string"])
def test_imperatives_ending_in_ing_are_not_mistaken_for_gerunds(word: str) -> None:
    assert not is_non_imperative(word)


def test_a_non_alphabetic_opener_is_left_alone() -> None:
    # "M17.4 -- sweep_axes: one mechanism ..." is the shape half this repo's history uses.
    assert not is_non_imperative("m17.4")
    assert errors("M17.4 -- sweep_axes: one mechanism for strategy and contract") == set()


def test_a_scope_prefix_is_stripped_before_the_mood_is_judged() -> None:
    assert first_word("build(deps): bump the python group") == "bump"
    assert first_word("Derive the session end") == "derive"
    # A colon that is not a type prefix must not eat the subject.
    assert first_word("M17.4 -- sweep_axes: one mechanism") == "m17.4"


def test_the_suffix_github_appends_counts_towards_the_limit() -> None:
    # Real, from main: comfortably under the ceiling bare, over it once GitHub appends the
    # number. Measuring the bare subject is the whole bug this rule exists to catch.
    subject = "Derive the session end from the observed last bar, not the template"
    assert len(subject) <= SUBJECT_MAX_LENGTH
    assert errors(subject) == set()
    assert "subject-max-length" in errors(subject, " (#164)")


def test_the_reported_length_is_the_bare_subject_and_the_landed_one() -> None:
    subject = "Derive the session end from the observed last bar, not the template"
    (finding,) = check_message(subject, " (#164)")
    assert f"is {len(subject)} characters" in finding.message
    assert f"becomes {len(subject) + len(' (#164)')}" in finding.message


def test_a_subject_at_the_ceiling_passes_and_one_past_it_fails() -> None:
    assert errors("x" * SUBJECT_MAX_LENGTH) == set()
    assert "subject-max-length" in errors("x" * (SUBJECT_MAX_LENGTH + 1))


def test_a_dependabot_title_is_exempt_from_the_ceiling() -> None:
    # Dependabot writes its own titles and they run past 72; that is not ours to control.
    bot = "build(deps): bump the python group across 1 directory with 5 updates"
    assert len(bot) + len(" (#153)") > SUBJECT_MAX_LENGTH
    assert errors(bot, " (#153)") == set()
    assert errors("chore(deps-dev): bump ruff from 0.16.2 to 0.16.4 " + "x" * 40) == set()
    # A human subject of the same length is not exempt.
    assert "subject-max-length" in errors("Derive " + "x" * 80)


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


@pytest.mark.parametrize(
    "subject",
    ["Merge branch 'main' into topic", 'Revert "Add the phase filter that was wrong all along here"'],
)
def test_github_generated_subjects_are_exempt_from_the_length_rule(subject: str) -> None:
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
    assert "subject-imperative" in capsys.readouterr().out


def test_the_github_switch_emits_a_workflow_annotation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "msg.txt"
    path.write_text("Added the phase filter\n", encoding="utf-8")
    main(["--message-file", str(path), "--github"])
    assert "::error title=commit message (subject-imperative)::" in capsys.readouterr().out


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


@pytest.mark.parametrize(
    "subject",
    [
        # Real, from main. A morphological -ing rule reads "reasoning" as a gerund and
        # blocks it; it is the noun subject of "belongs".
        "Docs: reasoning belongs in docs/, not in the source",
        "Caching of the numba kernels survives a parallel worker",
        "Rounding of the ambiguous bar follows NT8",
    ],
)
def test_nouns_ending_in_ing_are_not_mistaken_for_gerunds(subject: str) -> None:
    assert errors(subject) == set()


def test_the_gerunds_on_the_blocklist_still_fire() -> None:
    # Dropping the -ing fallback is not the same as dropping the -ing rule: the words that
    # are gerunds in practice stay listed, and "Handling" is one of them.
    assert "subject-imperative" in errors("Handling of the ambiguous bar moves into bracket.py")
    assert "subject-imperative" in errors("Adding the phase filter")


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("[DevTools] Remove the dead Timeline profiler code", "remove"),
        ("[flags] Enable enableParallelTransitions", "enable"),
        ("build(deps): bump the python group", "bump"),
        ("Docs: reasoning belongs in docs/", "reasoning"),
    ],
)
def test_a_bracketed_scope_is_stripped_like_a_type_prefix(subject: str, expected: str) -> None:
    # Without this, "[DevTools]" is read as the verb, ends in "s", and trips the
    # third-person rule. Measured as a false positive against facebook/react.
    assert first_word(subject) == expected


def test_a_bracketed_scope_does_not_make_a_correct_subject_fail() -> None:
    assert errors("[DevTools] Remove the dead Timeline profiler code") == set()
    assert "subject-imperative" in errors("[DevTools] Added component search to the Profiler")
