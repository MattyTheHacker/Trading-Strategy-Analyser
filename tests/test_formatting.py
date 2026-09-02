"""The custom formatting rules, and the one thing they must never do.

The rules only ever *insert* blank lines. That is what keeps them independent of
``ruff format``: going from no blank line to one can never break a ruff rule, because
everywhere ruff requires two the zero-blank original was already unformatted. The property
tests at the bottom pin that, and ``test_the_rules_only_ever_insert_blank_lines`` is the one
to look at first if a rule ever starts fighting the formatter.

The comment cases are the ones that have been wrong. Both rules put the blank line *above*
a comment attached to the following statement, rather than between the comment and the
statement it belongs to -- see ``CONTRIBUTING.md`` § "Where the blank line goes".
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import libcst as cst
import pytest

from formatting import ACTIVE_RULES
from formatting._leading import has_blank_line_above
from formatting.blank_line_after_if import EnsureBlankLineAfterIf
from formatting.blank_line_before_last_return import EnsureBlankLineBeforeLastReturn
from formatting.cli import EXIT_ERROR, EXIT_OK, EXIT_WOULD_REFORMAT, Outcome, format_file, main, python_files

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def apply(source: str, rules: Sequence[cst.CSTTransformer] | None = None) -> str:
    """The source as the formatter would rewrite it."""
    tree = cst.parse_module(textwrap.dedent(source))
    for rule in ACTIVE_RULES if rules is None else rules:
        tree = tree.visit(rule)

    return tree.code


def run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """``main`` with a command line, returning its exit status."""
    monkeypatch.setattr("sys.argv", ["formatting.cli", *argv])

    return main()


# -- blank line after an if ---------------------------------------------------


def test_a_statement_after_an_if_block_gets_a_blank_line() -> None:
    assert apply("""
        def f(x):
            if x:
                y = 1
            print(y)
    """) == textwrap.dedent("""
        def f(x):
            if x:
                y = 1

            print(y)
    """)


def test_an_if_that_ends_its_block_needs_no_blank_line_after_it() -> None:
    source = "def f(x):\n    y = 1\n    if x:\n        print(y)\n"

    assert apply(source) == source


def test_a_module_level_statement_after_an_if_gets_a_blank_line_too() -> None:
    assert apply("if X:\n    A = 1\nB = 2\n") == "if X:\n    A = 1\n\nB = 2\n"


def test_an_existing_blank_line_is_not_doubled() -> None:
    source = "def f(x):\n    if x:\n        y = 1\n\n    print(y)\n"

    assert apply(source) == source


# -- blank line before the last return ----------------------------------------


def test_the_last_return_in_a_function_gets_a_blank_line() -> None:
    assert apply("def f():\n    x = 1\n    return x\n") == "def f():\n    x = 1\n\n    return x\n"


def test_a_return_that_opens_its_block_is_left_against_it() -> None:
    source = "def f(x):\n    if x:\n        return 1\n    print(x)\n"

    # The `if` rule still fires; the return is the first statement of its own block
    assert apply(source) == "def f(x):\n    if x:\n        return 1\n\n    print(x)\n"


def test_only_the_last_return_gets_a_blank_line() -> None:
    assert apply("""
        def f(x):
            if x:
                return 1
            y = 2
            return y
    """) == textwrap.dedent("""
        def f(x):
            if x:
                return 1

            y = 2

            return y
    """)


def test_a_return_below_its_docstring_stays_against_it() -> None:
    source = 'def f():\n    """Doc."""\n    return 1\n'

    assert apply(source) == source


def test_a_nested_function_gets_its_own_last_return() -> None:
    assert apply("""
        def outer():
            def inner():
                a = 1
                return a
            return inner
    """) == textwrap.dedent("""
        def outer():
            def inner():
                a = 1

                return a

            return inner
    """)


def test_a_class_nested_in_a_function_keeps_its_returns_to_itself() -> None:
    """The collector stops at a nested class, so its methods are spaced by their own pass."""
    assert apply("""
        def outer():
            class C:
                def m(self):
                    a = 1
                    return a
            return C
    """) == textwrap.dedent("""
        def outer():
            class C:
                def m(self):
                    a = 1

                    return a

            return C
    """)


def test_a_one_line_function_body_is_left_alone() -> None:
    source = "def f():\n    return 1\n"

    assert apply(source) == source


def test_a_function_with_no_return_is_left_alone() -> None:
    source = "def f():\n    x = 1\n    print(x)\n"

    assert apply(source) == source


def test_an_async_function_is_treated_like_any_other() -> None:
    assert apply("async def f():\n    x = 1\n    return x\n") == "async def f():\n    x = 1\n\n    return x\n"


# -- where a comment puts the blank line --------------------------------------


def test_the_blank_line_goes_above_a_comment_attached_to_the_return() -> None:
    assert apply("""
        def f():
            x = 1
            # why
            return x
    """) == textwrap.dedent("""
        def f():
            x = 1

            # why
            return x
    """)


def test_the_blank_line_goes_above_a_comment_attached_to_a_statement_after_an_if() -> None:
    assert apply("""
        def f(x):
            if x:
                y = 1
            # why
            print(y)
    """) == textwrap.dedent("""
        def f(x):
            if x:
                y = 1

            # why
            print(y)
    """)


def test_a_blank_line_below_a_comment_does_not_satisfy_either_rule() -> None:
    """The comment still butts against the block above it, so the rule has not been met."""
    assert apply("""
        def f(x):
            if x:
                y = 1
            # why

            return y
    """) == textwrap.dedent("""
        def f(x):
            if x:
                y = 1

            # why

            return y
    """)


def test_both_rules_agree_on_where_a_comment_puts_the_blank_line() -> None:
    """The two rules held separate copies of this test and disagreed. They share one now."""
    commented = "    # why\n"
    after_if = apply(f"def f(x):\n    if x:\n        y = 1\n{commented}    print(y)\n")
    before_return = apply(f"def f(x):\n    y = 1\n{commented}    return y\n")

    assert after_if.splitlines()[-3:] == ["", "    # why", "    print(y)"]
    assert before_return.splitlines()[-3:] == ["", "    # why", "    return y"]


@pytest.mark.parametrize(
    ("leading", "expected"),
    [
        ([], False),
        ([cst.EmptyLine(comment=None)], True),
        ([cst.EmptyLine(comment=cst.Comment("# why"))], False),
        ([cst.EmptyLine(comment=cst.Comment("# why")), cst.EmptyLine(comment=None)], False),
        ([cst.EmptyLine(comment=None), cst.EmptyLine(comment=cst.Comment("# why"))], True),
    ],
)
def test_has_blank_line_above_reads_only_the_topmost_line(
    leading: list[cst.EmptyLine],
    *,
    expected: bool,
) -> None:
    assert has_blank_line_above(leading) is expected


# -- properties ---------------------------------------------------------------


SOURCES = [
    "def f(x):\n    if x:\n        y = 1\n    return y\n",
    "def f(x):\n    if x:\n        y = 1\n    # why\n    return y\n",
    "if X:\n    A = 1\nB = 2\n",
    "class C:\n    def m(self):\n        x = 1\n        return x\n",
    "def outer():\n    def inner():\n        return 1\n    return inner\n",
    'def f():\n    """Doc."""\n    return 1\n',
    "def outer():\n    class C:\n        def m(self):\n            return 1\n    return C\n",
]


@pytest.mark.parametrize("source", SOURCES)
def test_formatting_is_idempotent(source: str) -> None:
    once = apply(source)

    assert apply(once) == once


@pytest.mark.parametrize("source", SOURCES)
def test_the_rules_do_not_depend_on_their_order(source: str) -> None:
    forwards = [EnsureBlankLineAfterIf(), EnsureBlankLineBeforeLastReturn()]
    backwards = [EnsureBlankLineBeforeLastReturn(), EnsureBlankLineAfterIf()]

    assert apply(source, forwards) == apply(source, backwards)


@pytest.mark.parametrize("source", SOURCES)
def test_the_rules_only_ever_insert_blank_lines(source: str) -> None:
    """Nothing but blank lines moves. This is what keeps the rules clear of ``ruff format``."""
    before = [line for line in source.splitlines() if line.strip()]
    after = [line for line in apply(source).splitlines() if line.strip()]

    assert before == after


@pytest.mark.parametrize("source", SOURCES)
def test_no_rule_inserts_a_blank_line_at_the_top_of_a_block(source: str) -> None:
    """A blank line opening a block is the one insertion ``ruff format`` would strip back out."""
    lines = apply(source).splitlines()

    assert not [
        line
        for previous, line in zip(lines, lines[1:], strict=False)
        if previous.rstrip().endswith(":") and not line.strip()
    ]


# -- the command line ---------------------------------------------------------


UNFORMATTED = "def f():\n    x = 1\n    return x\n"
FORMATTED = "def f():\n    x = 1\n\n    return x\n"
UNPARSEABLE = "def f(\n    return 1\n"


def test_a_formatted_file_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "clean.py").write_text(FORMATTED, encoding="utf-8")

    assert run(["--check", str(tmp_path)], monkeypatch) == EXIT_OK


def test_check_exits_one_when_a_file_would_be_reformatted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "dirty.py").write_text(UNFORMATTED, encoding="utf-8")

    assert run(["--check", str(tmp_path)], monkeypatch) == EXIT_WOULD_REFORMAT


def test_check_leaves_the_file_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "dirty.py"
    target.write_text(UNFORMATTED, encoding="utf-8")

    run(["--check", str(tmp_path)], monkeypatch)

    assert target.read_text(encoding="utf-8") == UNFORMATTED


def test_a_run_without_check_writes_the_formatted_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "dirty.py"
    target.write_text(UNFORMATTED, encoding="utf-8")

    assert run([str(tmp_path)], monkeypatch) == EXIT_OK
    assert target.read_text(encoding="utf-8") == FORMATTED


def test_an_unparseable_file_exits_with_the_error_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file the formatter could not read is not a file it checked."""
    (tmp_path / "broken.py").write_text(UNPARSEABLE, encoding="utf-8")

    assert run(["--check", str(tmp_path)], monkeypatch) == EXIT_ERROR


def test_an_unparseable_file_outranks_a_clean_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "broken.py").write_text(UNPARSEABLE, encoding="utf-8")
    (tmp_path / "clean.py").write_text(FORMATTED, encoding="utf-8")

    assert run(["--check", str(tmp_path)], monkeypatch) == EXIT_ERROR


def test_a_path_that_is_not_there_exits_with_the_error_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in the checked path must not read as a clean run."""
    assert run(["--check", str(tmp_path / "absent")], monkeypatch) == EXIT_ERROR


def test_a_file_that_is_not_python_exits_with_the_error_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("not python", encoding="utf-8")

    assert run(["--check", str(notes)], monkeypatch) == EXIT_ERROR


def test_the_syntax_error_names_the_file_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken = tmp_path / "broken.py"
    broken.write_text(UNPARSEABLE, encoding="utf-8")

    run(["--check", str(broken)], monkeypatch)

    assert "broken.py" in capsys.readouterr().err


def test_format_file_reports_an_unparseable_file_as_failed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.py"
    broken.write_text(UNPARSEABLE, encoding="utf-8")

    assert format_file(broken, check=True) is Outcome.FAILED


def test_format_file_distinguishes_a_changed_file_from_an_unchanged_one(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.py"
    dirty.write_text(UNFORMATTED, encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text(FORMATTED, encoding="utf-8")

    assert format_file(dirty, check=True) is Outcome.CHANGED
    assert format_file(clean, check=True) is Outcome.UNCHANGED


# -- which files a directory yields -------------------------------------------


def test_dot_directories_are_skipped(tmp_path: Path) -> None:
    """``formatting.cli .`` at the repository root would otherwise rewrite ``.venv``."""
    (tmp_path / "kept.py").write_text(FORMATTED, encoding="utf-8")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "vendored.py").write_text(UNFORMATTED, encoding="utf-8")

    assert [path.name for path in python_files(tmp_path)] == ["kept.py"]


def test_a_dot_directory_named_explicitly_is_still_walked(tmp_path: Path) -> None:
    """The skip is about what a directory sweep picks up, not a refusal to be pointed at one."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "vendored.py").write_text(UNFORMATTED, encoding="utf-8")

    assert [path.name for path in python_files(venv)] == ["vendored.py"]


def test_nested_python_files_are_found(tmp_path: Path) -> None:
    package = tmp_path / "pkg" / "sub"
    package.mkdir(parents=True)
    (package / "deep.py").write_text(FORMATTED, encoding="utf-8")
    (tmp_path / "top.py").write_text(FORMATTED, encoding="utf-8")

    assert [path.name for path in python_files(tmp_path)] == ["deep.py", "top.py"]


def test_files_that_are_not_python_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text(FORMATTED, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not python", encoding="utf-8")
    (tmp_path / "data.json").write_text("{}", encoding="utf-8")

    assert [path.name for path in python_files(tmp_path)] == ["keep.py"]
