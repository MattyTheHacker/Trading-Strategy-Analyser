"""Fitting InsideBarTrailing's sizing cuts, and reading a confluence size against shuffled sizes.

Two things carry this module. **A fit reads the selection window and nothing else**, because the
cuts it writes are what the held-out window is later read at. And **the null keeps the entries**:
only which size each signal took is shuffled, so a confluence size that beats it put its larger
sizes on the better trades rather than trading different ones.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from nqbt import context, splice, stats, sweep
from nqbt.instruments import MNQ
from nqbt.sim import insidebar, insidebartrailing
from nqbt.sim.types import EARLINESS_TREND_AGE, SIZING_LABELS, InsideBarTrailingParams
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_sizing, campaign_sweep
from tools.campaign_sizing import (
    EARLY_QUANTILE,
    MAX_FAVOURABLE_SHARE,
    MIN_FAVOURABLE_SHARE,
    age_at,
    extension_at,
    fit,
    fit_cut,
    kept_labels,
    permuted_sizing,
    probe_params,
    selection_window,
    shuffled_null,
)

BARS = 40_000
"""Enough one-minute sessions for the relative-volume baseline to be defined on most of them."""


def base() -> InsideBarTrailingParams:
    """Periods short enough that a synthetic walk holds many setups."""
    return InsideBarTrailingParams(ema_period=5, fast_sma_period=8, slow_sma_period=13, error_margin=0.01)


@pytest.fixture(scope="module")
def bars():
    return walk_bars(BARS, seed=5)


@pytest.fixture(scope="module")
def fitted(bars):
    return fit_cut(bars, "MNQ", 1, base())


def prepared(bars, params):
    return context.prepare(bars, sweep.Grid.of(params).required_context(), bar_minutes=1)


# -- the fit ---------------------------------------------------------------------------------


def test_the_cuts_put_the_fitted_quantile_of_signals_on_the_early_side(bars, fitted) -> None:
    cut, _ = fitted
    data = prepared(bars, probe_params(base()))
    signal = insidebar.insidebar_signal(data, base())
    direction_at = insidebar.insidebar_direction(data, base())
    extension = extension_at(data, base())[signal]
    age = age_at(data, base(), direction_at)[signal]
    assert signal.sum() > 50, "too few signals for a quantile to mean anything"
    assert np.mean(extension <= cut.early_max_extension_atr) >= EARLY_QUANTILE
    assert np.mean(age <= cut.early_max_trend_bars) >= EARLY_QUANTILE
    assert np.mean(age < cut.early_max_trend_bars) < 1.0, "the cut admits every signal"


def test_the_label_thresholds_are_the_top_fifth_of_their_own_series(bars, fitted) -> None:
    cut, _ = fitted
    data = prepared(bars, probe_params(base()))
    ratios = data.regime_values(base().regime_lookback)
    relative = data.relative_volume(base().volume_key)
    ratios, relative = ratios[np.isfinite(ratios)], relative[np.isfinite(relative)]
    assert np.mean(ratios > cut.regime_directional_above) == pytest.approx(0.2, abs=0.01)
    assert np.mean(relative > cut.volume_heavy_above) == pytest.approx(0.2, abs=0.02)
    assert cut.regime_consolidating_below < cut.regime_directional_above
    assert cut.volume_thin_below < cut.volume_heavy_above


def test_every_label_gets_a_share_and_only_the_informative_ones_are_kept(fitted) -> None:
    cut, report = fitted
    shares = report["favourable_share"]
    assert list(shares) == list(SIZING_LABELS)
    assert all(0.0 <= share <= 1.0 for share in shares.values())
    assert cut.labels == kept_labels(shares)


def test_a_label_the_signal_nearly_always_or_never_has_is_dropped() -> None:
    shares = {
        "size_on_trend": 0.97,
        "size_on_higher_timeframe": MAX_FAVOURABLE_SHARE,
        "size_on_vwap": 0.5,
        "size_on_regime": MIN_FAVOURABLE_SHARE,
        "size_on_volume": 0.02,
    }
    assert kept_labels(shares) == ("size_on_higher_timeframe", "size_on_vwap", "size_on_regime")


def test_the_fit_reads_the_selection_window_alone() -> None:
    bars = walk_bars(1000)
    assert len(selection_window(bars)) == 600
    assert selection_window(bars).index[-1] < bars.index[600]


def test_a_window_with_no_signal_cannot_be_fitted(monkeypatch, bars) -> None:
    monkeypatch.setattr(
        campaign_sizing.insidebar, "insidebar_signal", lambda data, _: np.zeros(len(data), bool)
    )
    with pytest.raises(SystemExit, match="no signal"):
        fit_cut(bars, "MNQ", 1, base())


def test_fit_writes_cuts_the_sizing_arms_can_read(monkeypatch, tmp_path) -> None:
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setattr(
        campaign_sizing,
        "insidebartrailing_variants",
        lambda root: [
            campaign_sweep.Variant("trailing", campaign_sweep.archetypes.INSIDEBARTRAILING, base())
        ],
    )
    path = tmp_path / "cuts.json"
    written = fit(["MNQ"], [1], path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == json.loads(json.dumps(written))
    assert set(stored[0]["favourable_share"]) == set(SIZING_LABELS)
    assert set(stored[0]["traded_early_share"]) == {"first-breakout", "sma-extension", "trend-age"}
    (cut,) = campaign_sweep.sizing_cuts(path)
    assert (cut.root, cut.minutes) == ("MNQ", 1)
    assert list(cut.labels) == stored[0]["labels"]


# -- the shuffled-size null ------------------------------------------------------------------


def sized() -> InsideBarTrailingParams:
    return InsideBarTrailingParams(
        ema_period=5,
        fast_sma_period=8,
        slow_sma_period=13,
        error_margin=0.01,
        order_quantity=3,
        partial_take_profit_percentage=0.5,
        quantity_per_confluence=2,
        size_on_vwap=True,
        size_on_trend=True,
    )


def test_a_shuffle_moves_rows_among_signal_bars_and_nowhere_else() -> None:
    quantities = np.array([[1, 1], [2, 2], [3, 3]], dtype=np.int64)
    rows = np.array([0, 1, 2, 2, 0, 1, 2, 0], dtype=np.int64)
    signal = np.array([False, True, True, False, False, True, True, False])
    shuffled = permuted_sizing(
        insidebartrailing.LotSizing(quantities, rows), signal, np.random.default_rng(1)
    )
    assert shuffled.quantities is quantities
    assert np.array_equal(shuffled.row_at[~signal], rows[~signal])
    assert sorted(shuffled.row_at[signal]) == sorted(rows[signal])
    assert list(rows) == [0, 1, 2, 2, 0, 1, 2, 0], "the original is left untouched"


def test_the_null_reports_the_configurations_own_figure_and_a_p_that_is_never_zero() -> None:
    bars = walk_bars(6000, seed=9)
    params = sized()
    data = prepared(bars, params)
    result = shuffled_null(data, params, MNQ, by="profit_factor", draws=5, seed=0)
    own = stats.summarise_legs(insidebartrailing.insidebartrailing_legs(data, params, MNQ), data.day_codes)
    assert result["observed"] == pytest.approx(own.profit_factor)
    assert 1 / 6 <= result["p"] <= 1.0
    assert result["excess"] == pytest.approx(result["observed"] - result["null_median"])


def test_the_null_is_reproducible_from_its_seed() -> None:
    bars = walk_bars(6000, seed=9)
    params = sized()
    data = prepared(bars, params)
    first = shuffled_null(data, params, MNQ, by="net_pnl", draws=4, seed=3)
    again = shuffled_null(data, params, MNQ, by="net_pnl", draws=4, seed=3)
    assert first == again


def test_a_fixed_size_is_its_own_null() -> None:
    """With one row to shuffle, every draw is the observation: p is exactly one."""
    bars = walk_bars(6000, seed=9)
    params = InsideBarTrailingParams(ema_period=5, fast_sma_period=8, slow_sma_period=13, error_margin=0.01)
    data = prepared(bars, params)
    result = shuffled_null(data, params, MNQ, by="profit_factor", draws=3, seed=0)
    assert result["p"] == 1.0
    assert result["excess"] == 0.0


def test_the_traded_early_share_is_counted_over_trades_taken(bars, fitted) -> None:
    """A setup that arrives in a position is never traded, so the share is not the signals' own."""
    cut, report = fitted
    traded = report["traded_early_share"]
    assert set(traded) == {"first-breakout", "sma-extension", "trend-age"}
    assert all(0.0 <= share <= 1.0 for share in traded.values())
    tiered = dataclasses.replace(
        base(),
        earliness_mode=EARLINESS_TREND_AGE,
        early_max_trend_bars=cut.early_max_trend_bars,
    )
    data = prepared(bars, probe_params(base()))
    log = insidebartrailing.run_insidebartrailing(data, tiered, MNQ, with_times=False)
    signal_bars = log.groupby("trade_id")["entry_bar"].first().to_numpy() - 1
    early = insidebartrailing.early_entries(data, tiered, insidebar.insidebar_direction(data, tiered))
    assert traded["trend-age"] == pytest.approx(early[signal_bars].mean())


# -- the shortlist and the command line ------------------------------------------------------


def stored_confluence_row(combo_id: int) -> pd.Series:
    """One held-out confluence-arm row, carrying the fields ``rebuild`` restores it from."""
    return pd.Series(
        {
            "sweep_id": 7,
            "combo_id": combo_id,
            "resolution": 1,
            "stratum": "unfiltered",
            "variant": campaign_sizing.CONFLUENCE_VARIANT,
            **dataclasses.asdict(sized()),
        },
    )


def test_every_shortlisted_row_is_nulled_on_the_bars_it_was_swept_on(monkeypatch) -> None:
    bars = walk_bars(6000, seed=9)
    monkeypatch.setattr(campaign_sizing, "stored_rows", lambda *_: pd.DataFrame())
    monkeypatch.setattr(splice, "load_continuous", lambda _root: bars)
    monkeypatch.setattr(campaign_sizing, "candidate_bars", lambda stored, archive: (archive,))
    monkeypatch.setattr(
        campaign_sizing, "bars_for", lambda candidates, stored, block, minutes: (candidates[0], True)
    )
    rows = pd.DataFrame([stored_confluence_row(1), stored_confluence_row(2)])
    table = campaign_sizing.null_for_shortlist(rows, "MNQ", by="profit_factor", draws=3, seed=0)
    assert list(table["combo_id"]) == [1, 2]
    assert set(table["labels"]) == {"size_on_trend,size_on_vwap"}
    assert table["swept_bars"].all()
    assert table["p"].between(1 / 4, 1.0).all()


def test_fit_is_the_default_path_of_its_subcommand(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(
        campaign_sizing, "fit", lambda roots, resolutions, path: called.append((roots, resolutions, path))
    )
    assert (
        campaign_sizing.main(["campaign_sizing.py", "fit", "--roots", "NQ", "--resolutions", "5", "10"]) == 0
    )
    assert called == [(["NQ"], [5, 10], campaign_sweep.SIZING_CUTS)]


def test_the_null_reads_the_confluence_arm_and_fails_where_it_has_no_rows(monkeypatch) -> None:
    asked = []

    def held_out(*args):
        asked.append(args)

        return pd.DataFrame()

    monkeypatch.setattr(campaign_sizing, "held_out", held_out)
    assert (
        campaign_sizing.main(["campaign_sizing.py", "null", "--stratum", "phase=MIDDAY", "--resolution", "5"])
        == 1
    )
    (args,) = asked
    assert args[-1] == campaign_sizing.CONFLUENCE_VARIANT
    assert args[-3:-1] == ("phase=MIDDAY", 5)


def test_the_null_reports_its_shortlist(monkeypatch) -> None:
    rows = pd.DataFrame([stored_confluence_row(1)])
    monkeypatch.setattr(campaign_sizing, "held_out", lambda *_: rows)
    monkeypatch.setattr(
        campaign_sizing,
        "null_for_shortlist",
        lambda shortlist, root, *, by, draws, seed: pd.DataFrame({"combo_id": [1], "p": [0.01]}),
    )
    assert campaign_sizing.main(["campaign_sizing.py", "null", "--draws", "10"]) == 0
