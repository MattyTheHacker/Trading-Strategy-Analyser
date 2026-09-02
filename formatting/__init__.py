"""Module to handle custom formatting rules for the project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .blank_line_after_if import EnsureBlankLineAfterIf
from .blank_line_before_last_return import EnsureBlankLineBeforeLastReturn

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: Sequence[str] = ["ACTIVE_RULES"]

ACTIVE_RULES = [
    EnsureBlankLineAfterIf(),
    EnsureBlankLineBeforeLastReturn(),
]
