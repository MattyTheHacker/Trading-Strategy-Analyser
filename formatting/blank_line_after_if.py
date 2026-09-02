"""File to hold methods for the Blank Line After If formatting rule."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import libcst as cst

from ._leading import has_blank_line_above

if TYPE_CHECKING:
    from collections.abc import Sequence


class EnsureBlankLineAfterIf(cst.CSTTransformer):
    """A LibCST transformer that ensures there is a blank line after every `if` statement."""

    @override
    def leave_IndentedBlock(
        self,
        original_node: cst.IndentedBlock,
        updated_node: cst.IndentedBlock,
    ) -> cst.IndentedBlock:
        return updated_node.with_changes(body=self._insert_spacing(updated_node.body))

    @override
    def leave_Module(
        self,
        original_node: cst.Module,
        updated_node: cst.Module,
    ) -> cst.Module:
        return updated_node.with_changes(body=self._insert_spacing(updated_node.body))

    def _insert_spacing(
        self, body: Sequence[cst.BaseStatement | cst.BaseSmallStatement]
    ) -> list[cst.BaseStatement | cst.BaseSmallStatement]:
        new_body: list[cst.BaseStatement | cst.BaseSmallStatement] = []

        for i, stmt in enumerate(body):
            new_stmt = stmt

            # Check if the previous statement in this block was an If statement
            if (
                i > 0
                and isinstance(body[i - 1], cst.If)
                and hasattr(stmt, "leading_lines")
                and not has_blank_line_above(stmt.leading_lines)
            ):
                new_stmt = stmt.with_changes(
                    leading_lines=[cst.EmptyLine(indent=False), *list(stmt.leading_lines)]
                )

            new_body.append(new_stmt)

        return new_body
