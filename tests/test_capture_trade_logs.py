"""The trade-log capture runs every registered archetype's loop, and refuses a log that gates nothing."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, costs, ingest, sessions
from nqbt.context import PriceBasis
from nqbt.instruments import MNQ, NQ
from tools.capture_trade_logs import (
    EmptyCaptureError,
    capture,
    capture_archetypes,
    clear_previous_capture,
)

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.arrays import FloatArray
    from nqbt.context import Dataset
    from nqbt.instruments import Instrument


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Build random-walk minute bars on which every registered archetype trades at its defaults."""
    rng: np.random.Generator = np.random.default_rng(seed)
    idx: pd.DatetimeIndex = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close: FloatArray = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_: FloatArray = np.concatenate([[close[0]], close[:-1]])
    high: FloatArray = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n))
    low: FloatArray = np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n))
    frame: pd.DataFrame = pd.DataFrame(
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
def captured() -> dict[str, pd.DataFrame]:
    """Capture every gated archetype once over the synthetic bars."""
    return capture_archetypes(synthetic_bars(), MNQ, price_basis=PriceBasis.RAW)


def test_every_archetype_but_deadcatbounce_gets_its_own_log(captured: dict[str, pd.DataFrame]) -> None:
    """The capture returns one log per registered archetype, named for it, but DeadCatBounce's."""
    expected: list[str] = [
        f"defaults_{name}.csv" for name in archetypes.names() if name != archetypes.DEADCATBOUNCE.name
    ]

    assert sorted(captured) == expected


def test_every_log_is_charged_the_live_commission(captured: dict[str, pd.DataFrame]) -> None:
    """Every log carries the live commission, not the parameter classes' zero default."""
    for name, log in captured.items():
        assert (log["commission"] == costs.LIVE.commission_per_contract * log["quantity"]).all(), name


def test_every_loop_is_handed_the_live_costs_and_the_callers_instrument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slippage leaves no column in a log, so both costs are read off what each loop is handed."""
    handed: list[tuple[dict[str, object], Instrument]] = []

    def record(_data: Dataset, params: archetypes.Params, instrument: Instrument) -> pd.DataFrame:
        fields: dict[str, object] = params.as_dict()
        handed.append(({name: fields[name] for name in costs.COST_FIELDS}, instrument))

        return pd.DataFrame({"leg": [1]})

    recording: list[archetypes.Archetype] = [
        dataclasses.replace(archetype, run=record) for archetype in archetypes.all_archetypes()
    ]
    monkeypatch.setattr(archetypes, "all_archetypes", lambda: recording)

    capture_archetypes(synthetic_bars(), NQ, price_basis=PriceBasis.RAW)

    live: dict[str, object] = {
        "commission_per_contract": costs.LIVE.commission_per_contract,
        "slippage_ticks": costs.LIVE.slippage_ticks,
    }
    assert handed == [(live, NQ)] * (len(recording) - 1)


def test_a_refused_capture_leaves_nothing_to_compare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An archetype that trades nothing stops the capture before any log is written, stale ones included."""
    silent: archetypes.Archetype = dataclasses.replace(
        archetypes.PULLBACKANDGO,
        name="Silent",
        run=lambda *_: pd.DataFrame(),
    )
    monkeypatch.setattr(archetypes, "all_archetypes", lambda: [archetypes.PULLBACKANDGO, silent])
    monkeypatch.setattr(ingest, "load_contract", lambda _contract: synthetic_bars())
    (tmp_path / "defaults_Silent.csv").write_text("left by an earlier capture\n")

    with pytest.raises(EmptyCaptureError, match="Silent traded nothing"):
        capture(tmp_path)

    assert not any(tmp_path.iterdir())


def test_a_capture_clears_only_what_an_earlier_capture_wrote(tmp_path: Path) -> None:
    """An earlier capture's logs go, so an unregistered archetype's cannot compare present."""
    stale: list[str] = ["recon.csv", "live_mnq.csv", "sweep_trades_3.csv", "defaults_Unregistered.csv"]
    for name in [*stale, "notes.csv", "defaults.txt"]:
        (tmp_path / name).write_text("x\n")

    assert clear_previous_capture(tmp_path) == len(stale)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["defaults.txt", "notes.csv"]


def test_clearing_an_empty_directory_deletes_nothing(tmp_path: Path) -> None:
    """A first capture into a new directory has nothing to clear."""
    assert clear_previous_capture(tmp_path) == 0
