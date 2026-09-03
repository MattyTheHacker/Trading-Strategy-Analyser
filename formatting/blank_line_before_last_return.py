"""Module to hold methods for the Blank Line Before Last Return formatting rule."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import libcst as cst

from ._leading import has_blank_line_above

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = ["EnsureBlankLineBeforeLastReturn"]


def _is_docstring(stmt: cst.BaseStatement) -> bool:
    """Whether a statement is a bare string expression, as a docstring is."""
    if not isinstance(stmt, cst.SimpleStatementLine) or len(stmt.body) != 1:
        return False

    expr = stmt.body[0]

    return isinstance(expr, cst.Expr) and isinstance(expr.value, cst.SimpleString)


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
        self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
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

        # 3. Leave it alone if it opens the block, already has its blank line, or would be
        #    separated from the docstring it belongs to
        if target_index == 0 or not isinstance(stmt, cst.SimpleStatementLine):
            return updated_node

        if has_blank_line_above(stmt.leading_lines) or _is_docstring(new_body[target_index - 1]):
            return updated_node

        new_body[target_index] = stmt.with_changes(
            leading_lines=[cst.EmptyLine(indent=False), *list(stmt.leading_lines)]
        )

        return updated_node.with_changes(body=new_body)


class EnsureBlankLineBeforeLastReturn(cst.CSTTransformer):
    """Class to ensure there is a blank line before the very last return statement in a method/function."""

    @override
    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
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
