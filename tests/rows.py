"""Read the loosely typed rows the campaign tools return, checked as the tests read them."""

from __future__ import annotations

from numbers import Real
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def number(row: Mapping[str, object], field: str) -> float:
    """Return ``row[field]`` as a float, checked to be a real number and not a flag."""
    value = row[field]
    assert not isinstance(value, bool), f"{field} is a flag"
    assert isinstance(value, Real), f"{field} is a {type(value).__name__}"

    return float(value)
