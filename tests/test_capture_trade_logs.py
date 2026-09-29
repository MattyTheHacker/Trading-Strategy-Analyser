"""The trade-log capture runs every registered archetype's loop, and refuses a log that gates nothing."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, costs, sessions
from tools.capture_trade_logs import EmptyCaptureError, capture_archetypes

if TYPE_CHECKING:
    from pathlib import Path


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Build random-walk minute bars on which every registered archetype trades at its defaults."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day

    return frame


@pytest.fixture(scope="module")
def captured(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Capture every registered archetype once over the synthetic bars."""
    outdir = tmp_path_factory.mktemp("capture")
    capture_archetypes(synthetic_bars(), outdir)

    return outdir


def test_every_registered_archetype_gets_its_own_log(captured: Path) -> None:
    """The capture writes exactly one log per registered archetype, named for it."""
    written = sorted(path.name for path in captured.iterdir())

    assert written == sorted(f"defaults_{name}.csv" for name in archetypes.names())


def test_every_log_is_charged_live_costs(captured: Path) -> None:
    """Every log carries the live commission, not the parameter classes' zero default."""
    for path in captured.iterdir():
        log = pd.read_csv(path)

        assert (log["commission"] == costs.LIVE.commission_per_contract * log["quantity"]).all(), path.name


def test_an_archetype_that_trades_nothing_stops_the_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An archetype that trades nothing raises, rather than writing a log that could never move."""
    silent = dataclasses.replace(archetypes.PULLBACKANDGO, name="Silent", run=lambda *_: pd.DataFrame())
    monkeypatch.setattr(archetypes, "all_archetypes", lambda: [silent])

    with pytest.raises(EmptyCaptureError, match="Silent traded nothing"):
        capture_archetypes(synthetic_bars(), tmp_path)

    assert not any(tmp_path.iterdir())
