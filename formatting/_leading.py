"""The blank-line test every formatting rule shares.

Stated once because the two rules disagreed while each held its own copy of it. See
``CONTRIBUTING.md`` § "Where the blank line goes".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    import libcst as cst

__all__: Sequence[str] = ["has_blank_line_above"]


def has_blank_line_above(leading_lines: Sequence[cst.EmptyLine]) -> bool:
    """Whether a blank line already sits above a statement and everything attached to it."""
    return bool(leading_lines) and leading_lines[0].comment is None
