"""Module to hold methods for the Blank Line Before Last Return formatting rule."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import libcst as cst

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = ["EnsureBlankLineBeforeLastReturn"]


class ReturnCollector(cst.CSTVisitor):
    """Visitor to collect all return statements in a function, ignoring nested functions/classes."""

    def __init__(self) -> None:
        self.returns: list[cst.SimpleStatementLine] = []

    @override
    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> None:
        if len(node.body) == 1 and isinstance(node.body[0], cst.Return):
            self.returns.append(node)

    @override
    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        # Return False to prevent recursing into nested functions
        return False

    @override
    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        return False


class ReturnModifier(cst.CSTTransformer):
    """Transformer to add a blank line before a specific target return statement."""

    def __init__(self, target_node: cst.SimpleStatementLine) -> None:
        self.target_node = target_node

    @override
    def leave_IndentedBlock(
        self,
        original_node: cst.IndentedBlock,
        updated_node: cst.IndentedBlock,
    ) -> cst.IndentedBlock:
        # 1. Match object identity using the original, unaltered node tree
        target_index = -1
        for i, orig_stmt in enumerate(original_node.body):
            if orig_stmt is self.target_node:
                target_index = i
                break

        if target_index == -1:
            return updated_node

        # 2. Extract the matched statement from the updated tree
        new_body = list(updated_node.body)
        stmt = new_body[target_index]

        has_blank_line: bool = any(line.comment is None for line in stmt.leading_lines)

        has_comment_above: bool = stmt.leading_lines[-1].comment is not None if stmt.leading_lines else False

        prev_stmt = new_body[target_index - 1] if target_index > 0 else None
        has_docstring_above: bool = (
            prev_stmt is not None
            and isinstance(prev_stmt, cst.SimpleStatementLine)
            and len(prev_stmt.body) == 1
            and isinstance(prev_stmt.body[0], cst.Expr)
            and isinstance(prev_stmt.body[0].value, cst.SimpleString)
        )

        # 3. Apply changes if it isn't the first statement in the block
        if target_index > 0 and not has_blank_line and not has_comment_above and not has_docstring_above:
            new_stmt = stmt.with_changes(
                leading_lines=[cst.EmptyLine(indent=False), *list(stmt.leading_lines)]
            )
            new_body[target_index] = new_stmt
            return updated_node.with_changes(body=new_body)

        return updated_node


class EnsureBlankLineBeforeLastReturn(cst.CSTTransformer):
    """Class to ensure there is a blank line before the very last return statement in a method/function."""

    @override
    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        # 1. Collect all returns in this function's scope
        collector = ReturnCollector()
        updated_node.body.visit(collector)

        if not collector.returns:
            return updated_node

        # 2. Identify the very last one
        last_return = collector.returns[-1]

        # 3. Apply the modifier specifically for that exact node and satisfy mypy
        modifier = ReturnModifier(last_return)
        return cst.ensure_type(updated_node.visit(modifier), cst.FunctionDef)
