"""Fixtures shared by more than one test module."""

from __future__ import annotations

import pytest

from nqbt import context
from tests.test_campaign_review import bars
from tools.campaign_review import review_spec


@pytest.fixture(scope="module")
def data() -> context.Dataset:
    """Provide the bars a stored log would have been simulated over, with the clock and all three forms."""
    return context.prepare(bars(), review_spec(), bar_minutes=1)
