"""The per-contract tally, and the unbounded statistic it used to be carried by.

``tally`` is pure -- a frame of contract rows in, one row per root out -- and it is where the
defect lived, so most of this builds the rows directly. ``one_contract`` is exercised on
synthetic bars only to pin that every figure it reports is finite, which is a property of the
statistic it chose rather than of the bars.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, sessions
from nqbt.sim.types import InsideBarParams
from tools.campaign_contracts import one_contract, tally

ROOT = "MNQ"

MEDIAN_COLUMNS = ["median_expectancy", "median_null_expectancy", "median_excess", "total_net"]


def contract_rows(**columns: object) -> pd.DataFrame:
    """Three front-month contracts of one root, as ``run_root`` assembles them."""
    base = {
        "root": ROOT,
        "contract": ["MNQ 03-24", "MNQ 06-24", "MNQ 09-24"],
        "trades": [120, 90, 60],
        "profit_factor": [1.4, 0.8, 1.1],
        "expectancy": [12.0, -8.0, 4.0],
        "net_pnl": [1440.0, -720.0, 240.0],
        "null_expectancy": [2.0, 2.0, 6.0],
        "null_trades": [118.0, 92.0, 61.0],
        "excess": [10.0, -10.0, -2.0],
    }
    return pd.DataFrame({**base, **columns})


# -- the statistic the tally is taken on ---------------------------------------------------


def test_a_contract_with_no_losing_trade_leaves_every_tallied_figure_finite() -> None:
    """The defect (#218): a gross loss of zero makes that contract's profit factor infinite,
    and a mean over the column took the whole root's row infinite with it."""
    frame = contract_rows(profit_factor=[1.4, 0.8, float("inf")])
    assert not math.isfinite(frame["profit_factor"].mean()), "the fixture no longer poses the defect"
    assert np.isfinite(tally(frame)[MEDIAN_COLUMNS].to_numpy(np.float64)).all()


def test_no_tallied_column_is_a_profit_factor() -> None:
    """Which is what makes the row above finite by construction rather than by this fixture."""
    assert [column for column in tally(contract_rows()).columns if "profit_factor" in column] == []


def test_one_contract_cannot_carry_the_verdict_however_extreme_it_is() -> None:
    """A mean is what a single contract dominates. A sign count and a median are not."""
    modest = tally(contract_rows()).iloc[0]
    frame = contract_rows(expectancy=[1e9, -8.0, 4.0], excess=[1e9, -10.0, -2.0])
    extreme = tally(frame).iloc[0]
    assert extreme["beats_null"] == modest["beats_null"]
    assert extreme["median_excess"] == modest["median_excess"]


# -- what the tally counts -----------------------------------------------------------------


def test_the_verdict_is_the_sign_count_across_contracts() -> None:
    row = tally(contract_rows()).iloc[0]
    assert row["contracts"] == 3
    assert row["beats_null"] == 1
    assert row["profitable"] == 2


def test_a_thin_contract_is_counted_and_its_trade_count_is_reported() -> None:
    """There is no minimum. The exclusion existed to keep a handful of trades out of an
    unbounded mean, and there is no longer an unbounded mean to keep them out of."""
    row = tally(contract_rows(trades=[120, 90, 3], excess=[10.0, -10.0, 5.0])).iloc[0]
    assert row["contracts"] == 3
    assert row["fewest_trades"] == 3
    assert row["beats_null"] == 2


def test_a_contract_the_configuration_never_traded_is_reported_but_not_counted() -> None:
    """No trades is the one cut that is not a threshold: there is no statistic to count."""
    frame = contract_rows(
        trades=[120, 90, 0],
        expectancy=[12.0, -8.0, float("nan")],
        excess=[10.0, -10.0, float("nan")],
    )
    row = tally(frame).iloc[0]
    assert row["contracts"] == 2
    assert row["fewest_trades"] == 90
    assert len(frame) == 3


def test_each_root_is_tallied_on_its_own_row() -> None:
    """NQ and MNQ share a tick size and differ tenfold in tick value, so an expectancy pooled
    across the two would be reporting the root rather than the rule."""
    both = pd.concat(
        [
            contract_rows(),
            contract_rows(root="NQ", expectancy=[120.0, -80.0, 40.0], excess=[100.0, -100.0, -20.0]),
        ],
    )
    rows = tally(both)
    assert list(rows["root"]) == ["MNQ", "NQ"]
    assert rows.set_index("root").loc["NQ", "median_expectancy"] == pytest.approx(40.0)


# -- one contract's row --------------------------------------------------------------------


def synthetic_bars(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-02 00:00", periods=n, freq="min", tz="UTC")
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    frame["trading_day"] = sessions.classify(idx).trading_day
    return frame


def params() -> InsideBarParams:
    return InsideBarParams(slow_sma_period=50, bars_required_to_trade=60, atr_multiplier=5.0)


def row_for(bars: pd.DataFrame) -> dict[str, object]:
    return one_contract(bars, params(), archetypes.INSIDEBAR, ROOT, 5, 3, 1)


def test_a_contract_reports_a_finite_excess_over_its_own_null() -> None:
    row = {key: float(value) for key, value in row_for(synthetic_bars()).items()}  # type: ignore[arg-type]  # every reported field is a number
    assert row["trades"] > 0, "fixture produced no trades; the test proves nothing"
    assert math.isfinite(row["expectancy"])
    assert math.isfinite(row["null_expectancy"])
    assert row["excess"] == pytest.approx(row["expectancy"] - row["null_expectancy"])


def test_a_contract_too_short_to_trade_still_fills_every_column() -> None:
    """``run_root`` logs a field per contract and ``tally`` reads a column per row, so a key
    this path omitted would surface as a silent NaN column rather than as an error."""
    short = row_for(synthetic_bars(n=200))
    assert short["trades"] == 0
    assert short.keys() == row_for(synthetic_bars()).keys()
