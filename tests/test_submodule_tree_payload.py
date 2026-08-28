from pathlib import Path

import pytest

from tools.submodule_tree_payload import SUBMODULE_MODE, main, parse_moved, tree_payload


def test_each_line_becomes_a_path_and_a_commit_id() -> None:
    assert parse_moved("a 1111111\nb 2222222\n") == [("a", "1111111"), ("b", "2222222")]


def test_blank_lines_are_not_submodules() -> None:
    assert parse_moved("\n\na 1111111\n\n") == [("a", "1111111")]


def test_nothing_moved_reads_as_no_submodules() -> None:
    assert parse_moved("") == []


@pytest.mark.parametrize("line", ["justapath", "a 1111111 extra"])
def test_a_line_that_is_not_a_path_and_a_sha_raises(line: str) -> None:
    with pytest.raises(ValueError, match="is not '<path> <sha>'"):
        parse_moved(line)


def test_every_entry_is_a_submodule_pointer_on_the_base_tree() -> None:
    payload = tree_payload("basesha", [("Trading-Docs", "1111111"), ("scripts", "2222222")])

    assert payload["base_tree"] == "basesha"
    assert payload["tree"] == [
        {"path": "Trading-Docs", "mode": SUBMODULE_MODE, "type": "commit", "sha": "1111111"},
        {"path": "scripts", "mode": SUBMODULE_MODE, "type": "commit", "sha": "2222222"},
    ]


def test_the_mode_is_the_one_git_uses_for_a_submodule() -> None:
    assert SUBMODULE_MODE == "160000"


def test_a_payload_with_no_entries_raises_rather_than_writing_an_empty_tree() -> None:
    with pytest.raises(ValueError, match="no submodule moved"):
        tree_payload("basesha", [])


def test_the_command_writes_the_payload_the_api_expects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    moved = tmp_path / "moved.txt"
    moved.write_text("Trading-Docs 1111111\n", encoding="utf-8")

    assert main(["basesha", str(moved)]) == 0
    assert capsys.readouterr().out == (
        '{"base_tree": "basesha", "tree": [{"path": "Trading-Docs", '
        '"mode": "160000", "type": "commit", "sha": "1111111"}]}'
    )
