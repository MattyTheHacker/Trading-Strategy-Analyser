import io
from pathlib import Path

import pytest

from tools.lint_commit_messages import (
    CONVENTIONAL_TYPES,
    SUBJECT_MAX_LENGTH,
    check_message,
    first_word,
    main,
    non_imperative_words,
    verb_candidate,
)


# The mood verdict comes from ruff at run time. Unit tests inject it instead, so they
# stay deterministic and never shell out; the integration tests below exercise the real call.
MOOD: frozenset[str] = frozenset(
    "added adds adding fixed fixes fixing refactoring bumps derived handling".split()
)


def rules(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix, MOOD)}


def errors(message: str, suffix: str = "") -> set[str]:
    return {finding.rule for finding in check_message(message, suffix, MOOD) if finding.is_error}


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
    assert offender in check_message(subject, "", MOOD)[0].message


def test_the_suffix_github_appends_counts_towards_the_limit() -> None:
    # Real, from main: comfortably under the ceiling bare, over it once GitHub appends the
    # number. Measuring the bare subject is the whole bug this rule exists to catch.
    subject = "Derive the session end from the observed last bar, not the template"
    assert len(subject) <= SUBJECT_MAX_LENGTH
    assert errors(subject) == set()
    assert "subject-max-length" in errors(subject, " (#164)")


def test_the_reported_length_is_the_bare_subject_and_the_landed_one() -> None:
    subject = "Derive the session end from the observed last bar, not the template"
    (finding,) = check_message(subject, " (#164)", MOOD)
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
        "M17.4 -- sweep_axes takes resolution and contract",
        "M17.1 + M17.2 -- the archetype registry",
        "Docs: record the M15 findings and stop quoting figures",
        "instruments.py: route every monetary figure through the spec",
        "[DevTools] Remove the dead profiler code",
        "WIP: still poking at the bracket engine",
    ],
)
def test_the_old_prefix_conventions_are_rejected(subject: str) -> None:
    # A milestone tag, a filename or a capitalised word is not a prefix the rules know:
    # the subject has to start with a verb, or with a real Conventional Commits type.
    assert "subject-shape" in errors(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "Add the phase filter to the sweep axes",
        "Derive the session end from the observed last bar",
        "Move the leg writer behind a single entry point",
    ],
)
def test_a_bare_imperative_subject_passes_without_a_warning(subject: str) -> None:
    assert check_message(subject, "", MOOD) == []


@pytest.mark.parametrize("conventional_type", sorted(CONVENTIONAL_TYPES))
def test_every_conventional_type_is_accepted_but_warned_about(conventional_type: str) -> None:
    findings = check_message(f"{conventional_type}: drop the stale roadmap figures", "", MOOD)
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


def test_the_mood_is_still_judged_behind_a_conventional_prefix() -> None:
    assert "subject-imperative" in errors("fix(sim): derived the session end")
    assert "subject-imperative" in errors("build(deps): bumps the python group")


def test_dependabot_is_exempt_from_the_prefix_warning_as_well_as_the_ceiling() -> None:
    # It cannot act on either, so warning about them is noise on every dependency PR.
    assert check_message("build(deps): bump numba from 0.66.0 to 0.67.0", " (#153)", MOOD) == []


@pytest.mark.parametrize(
    "subject",
    [
        "Add a guard: the sweep must not rank free money",
        "Handle the 09:30 bar as the pre-open",
    ],
)
def test_a_colon_later_in_the_subject_is_not_read_as_a_prefix(subject: str) -> None:
    assert check_message(subject, "", MOOD) == []


def test_verb_candidate_looks_past_a_conventional_prefix() -> None:
    assert verb_candidate("fix(sim): derive the session end") == "derive"
    assert verb_candidate("Derive the session end") == "derive"
    assert verb_candidate("build(deps): bump numba") == "bump"


def test_ruff_supplies_the_mood_verdict() -> None:
    # The integration point: no wordlist of ours, ruff's D401 decides. It answers only for
    # verbs it knows, and stays silent rather than guessing -- which is why "built" is absent.
    verdict = non_imperative_words(["added", "adds", "returns", "sends", "derive", "add", "built"])
    assert {"added", "adds", "returns", "sends"} <= verdict
    assert "derive" not in verdict
    assert "add" not in verdict


def test_the_oracle_does_not_flag_plural_nouns() -> None:
    # The failure mode of the suffix heuristic this replaced: it read every -s word as a
    # third-person verb, so "Sessions", "Refs" and "Docs" were all reported.
    assert non_imperative_words(["sessions", "refs", "docs", "plugins", "dashboards"]) == frozenset()


def test_an_empty_vocabulary_does_not_invoke_ruff() -> None:
    assert non_imperative_words([]) == frozenset()
    assert non_imperative_words(["M17.4", "9000", ""]) == frozenset()
