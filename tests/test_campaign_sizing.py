"""Fitting InsideBarTrailing's sizing cuts, and reading a confluence size against shuffled sizes.

Two things carry this module. **A fit reads the selection window and nothing else**, because the
cuts it writes are what the held-out window is later read at. And **the null keeps the entries**:
only which size each signal took is shuffled, so a confluence size that beats it put its larger
sizes on the better trades rather than trading different ones.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from nqbt import archetypes, context, splice, stats, sweep, trades, trend
from nqbt.instruments import MNQ
from nqbt.sim import bracket, insidebar, insidebartrailing, runner, squeeze
from nqbt.sim.types import (
    EARLINESS_TREND_AGE,
    SIZING_LABELS,
    DeadCatParams,
    InsideBarParams,
    InsideBarTrailingParams,
    SqueezeBreakoutParams,
)
from nqbt.trades import C_QUANTITY, LONG, SHORT
from tests.test_insidebartrailing_sim import walk_bars
from tools import campaign_sizing, campaign_sweep
from tools.campaign_sizing import (
    EARLY_QUANTILE,
    MAX_FAVOURABLE_SHARE,
    MAX_STEP_SHARE,
    MIN_FAVOURABLE_SHARE,
    age_at,
    extension_at,
    fit,
    fit_cut,
    kept_labels,
    label_shares,
    permuted_sizing,
    probe_params,
    recomputed_null,
    resized,
    same_trades,
    selection_window,
    shuffled_null,
    symmetric_kept_labels,
    trade_rows,
    unsized,
)
from tools.campaign_sweep import VARIANTS

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.arrays import IntArray
    from nqbt.instruments import Instrument
    from tools.campaign_sweep import SizingCut

BARS = 40_000
"""Enough one-minute sessions for the relative-volume baseline to be defined on most of them."""


def base() -> InsideBarTrailingParams:
    """Build a base with periods short enough that a synthetic walk holds many setups."""
    return InsideBarTrailingParams(ema_period=5, fast_sma_period=8, slow_sma_period=13, error_margin=0.01)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return walk_bars(BARS, seed=5)


def ibt_variant(params: InsideBarTrailingParams | None = None) -> campaign_sweep.Variant:
    """Return InsideBarTrailing's one stored variant, over :func:`base` unless told otherwise."""
    return campaign_sweep.Variant(
        "trailing", archetypes.INSIDEBARTRAILING, base() if params is None else params
    )


type Fitted = tuple[SizingCut, dict[str, dict[str, float]]]
"""One fitted cut, with what it was read off."""


@pytest.fixture(scope="module")
def fitted(bars: pd.DataFrame) -> Fitted:
    return fit_cut(bars, "MNQ", 1, ibt_variant())


def prepared(bars: pd.DataFrame, params: archetypes.Params) -> context.Dataset:
    return context.prepare(bars, sweep.Grid.of(params).required_context(), bar_minutes=1)


# -- the fit ---------------------------------------------------------------------------------


def test_the_cuts_put_the_fitted_quantile_of_signals_on_the_early_side(
    bars: pd.DataFrame, fitted: Fitted
) -> None:
    cut, _ = fitted
    data = prepared(bars, probe_params(base()))
    signal = insidebar.insidebar_signal(data, base())
    direction_at = insidebar.insidebar_direction(data, base())
    extension = extension_at(data, base())[signal]
    age = age_at(data, base(), direction_at)[signal]
    assert signal.sum() > 50, "too few signals for a quantile to mean anything"
    assert cut.early_max_extension_atr is not None
    assert cut.early_max_trend_bars is not None
    assert np.mean(extension <= cut.early_max_extension_atr) >= EARLY_QUANTILE
    assert np.mean(age <= cut.early_max_trend_bars) >= EARLY_QUANTILE
    assert np.mean(age < cut.early_max_trend_bars) < 1.0, "the cut admits every signal"


def test_the_label_thresholds_are_the_top_fifth_of_their_own_series(
    bars: pd.DataFrame, fitted: Fitted
) -> None:
    cut, _ = fitted
    data = prepared(bars, probe_params(base()))
    ratios = data.regime_values(base().regime_lookback)
    relative = data.relative_volume(base().volume_key)
    ratios, relative = ratios[np.isfinite(ratios)], relative[np.isfinite(relative)]
    assert np.mean(ratios > cut.regime_directional_above) == pytest.approx(0.2, abs=0.01)
    assert np.mean(relative > cut.volume_heavy_above) == pytest.approx(0.2, abs=0.02)
    assert cut.regime_consolidating_below < cut.regime_directional_above
    assert cut.volume_thin_below < cut.volume_heavy_above


def test_every_label_gets_a_share_and_only_the_informative_ones_are_kept(
    fitted: Fitted,
) -> None:
    cut, report = fitted
    for name in ("favourable_share", "opposing_share", "neutral_share"):
        assert list(report[name]) == list(SIZING_LABELS)
        assert all(0.0 <= share <= 1.0 for share in report[name].values())
    assert cut.labels == kept_labels(report["favourable_share"])
    assert cut.symmetric_labels == symmetric_kept_labels(report)
    assert set(cut.labels) <= set(cut.symmetric_labels), "a label sorting added-only sorts symmetric too"


def test_the_three_steps_a_symmetric_count_moves_by_cover_every_signal(
    fitted: Fitted,
) -> None:
    """Up where a label favours alone, down where it opposes alone, none elsewhere."""
    _, report = fitted
    for label in SIZING_LABELS:
        up = 1.0 - report["opposing_share"][label] - report["neutral_share"][label]
        assert 0.0 <= up <= report["favourable_share"][label] + 1e-12


def test_a_label_the_signal_nearly_always_or_never_has_is_dropped() -> None:
    shares = {
        "size_on_trend": 0.97,
        "size_on_higher_timeframe": MAX_FAVOURABLE_SHARE,
        "size_on_vwap": 0.5,
        "size_on_regime": MIN_FAVOURABLE_SHARE,
        "size_on_volume": 0.02,
    }
    assert kept_labels(shares) == ("size_on_higher_timeframe", "size_on_vwap", "size_on_regime")


def test_the_symmetric_count_keeps_a_label_the_add_only_band_drops_when_it_opposes_enough() -> None:
    """ElasticBand's trend favours 4% of its signals and opposes 69%: nothing added, plenty shed."""
    report = {
        "favourable_share": {
            "size_on_trend": 0.04,
            "size_on_higher_timeframe": 0.42,
            "size_on_vwap": 0.013,
            "size_on_regime": 0.05,
            "size_on_volume": 0.03,
        },
        "opposing_share": {
            "size_on_trend": 0.69,
            "size_on_higher_timeframe": 0.58,
            "size_on_vwap": 0.987,
            "size_on_regime": 0.05,
            "size_on_volume": 0.02,
        },
        "neutral_share": {
            "size_on_trend": 0.27,
            "size_on_higher_timeframe": 0.0,
            "size_on_vwap": 0.0,
            "size_on_regime": MAX_STEP_SHARE,
            "size_on_volume": 0.95,
        },
    }
    assert kept_labels(report["favourable_share"]) == ("size_on_higher_timeframe",)
    assert symmetric_kept_labels(report) == ("size_on_trend", "size_on_higher_timeframe", "size_on_regime")


def test_the_fit_reads_the_selection_window_alone() -> None:
    bars = walk_bars(1000)
    assert len(selection_window(bars)) == 600
    assert selection_window(bars).index[-1] < bars.index[600]


def test_a_window_with_no_signal_cannot_be_fitted(bars: pd.DataFrame) -> None:
    silent = dataclasses.replace(
        archetypes.INSIDEBARTRAILING, signal=lambda data, _: np.zeros(len(data), dtype=np.bool_)
    )
    with pytest.raises(SystemExit, match="no signal"):
        fit_cut(bars, "MNQ", 1, campaign_sweep.Variant("trailing", silent, base()))


def test_fit_writes_cuts_the_sizing_arms_can_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBarTrailing", lambda _root: [ibt_variant()])
    path = tmp_path / "cuts.json"
    written = fit("InsideBarTrailing", ["MNQ"], [1], path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == json.loads(json.dumps(written))
    for name in ("favourable_share", "opposing_share", "neutral_share"):
        assert set(stored[0][name]) == set(SIZING_LABELS)
    assert set(stored[0]["traded_early_share"]) == {"first-breakout", "sma-extension", "trend-age"}
    (cut,) = campaign_sweep.sizing_cuts(path)
    assert (cut.root, cut.minutes) == ("MNQ", 1)
    assert list(cut.labels) == stored[0]["labels"]
    assert cut.symmetric_labels is not None
    assert list(cut.symmetric_labels) == stored[0]["symmetric_labels"]


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
    shuffled = permuted_sizing(bracket.Sizing(quantities, rows), signal, np.random.default_rng(1))
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


def test_the_traded_early_share_is_counted_over_trades_taken(bars: pd.DataFrame, fitted: Fitted) -> None:
    """A setup that arrives in a position is never traded, so the share is not the signals' own."""
    cut, report = fitted
    traded = report["traded_early_share"]
    assert set(traded) == {"first-breakout", "sma-extension", "trend-age"}
    assert all(0.0 <= share <= 1.0 for share in traded.values())
    assert cut.early_max_trend_bars is not None
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


def stored_confluence_row(combo_id: int) -> pd.Series:  # type: ignore[explicit-any]  # a row of mixed dtypes
    """Build one held-out confluence-arm row, carrying the fields ``rebuild`` restores it from."""
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


def test_every_shortlisted_row_is_nulled_on_the_bars_it_was_swept_on(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = walk_bars(6000, seed=9)
    monkeypatch.setattr(campaign_sizing, "stored_rows", lambda *_: pd.DataFrame())
    monkeypatch.setattr(splice, "load_continuous", lambda _root: bars)
    monkeypatch.setattr(campaign_sizing, "candidate_bars", lambda _stored, archive: (archive,))
    monkeypatch.setattr(
        campaign_sizing, "bars_for", lambda candidates, _stored, _block, _minutes: (candidates[0], True)
    )
    rows = pd.DataFrame([stored_confluence_row(1), stored_confluence_row(2)])
    table = campaign_sizing.null_for_shortlist(rows, "MNQ", by="profit_factor", draws=3, seed=0)
    assert list(table["combo_id"]) == [1, 2]
    assert set(table["labels"]) == {"size_on_trend,size_on_vwap"}
    assert table["swept_bars"].all()
    assert table["p"].between(1 / 4, 1.0).all()


def test_fit_is_the_default_path_of_its_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    monkeypatch.setattr(
        campaign_sizing,
        "fit",
        lambda name, roots, resolutions, path: called.append((name, roots, resolutions, path)),
    )
    assert (
        campaign_sizing.main(["campaign_sizing.py", "fit", "--roots", "NQ", "--resolutions", "5", "10"]) == 0
    )
    assert called == [("InsideBarTrailing", ["NQ"], [5, 10], campaign_sweep.SIZING_CUTS)]


def test_the_null_reads_the_confluence_arm_and_fails_where_it_has_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = []

    def held_out(*args: object) -> pd.DataFrame:
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


def test_the_null_reports_its_shortlist(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = pd.DataFrame([stored_confluence_row(1)])
    monkeypatch.setattr(campaign_sizing, "held_out", lambda *_: rows)
    monkeypatch.setattr(
        campaign_sizing,
        "null_for_shortlist",
        lambda _shortlist, _root, *, by, draws, seed, archetype: pd.DataFrame({"combo_id": [1], "p": [0.01]}),  # noqa: ARG005 - the caller passes these by keyword
    )
    assert campaign_sizing.main(["campaign_sizing.py", "null", "--draws", "10"]) == 0


# -- every other archetype: the fit ------------------------------------------------------------


def insidebar_base(**fields: object) -> InsideBarParams:
    """Return InsideBar at periods short enough that the synthetic walk holds many setups."""
    return InsideBarParams(
        ema_period=5,
        fast_sma_period=8,
        slow_sma_period=13,
        error_margin=0.01,
        no_entry_minutes_before_close=0,
        **fields,  # type: ignore[arg-type]  # each caller passes a field's own type
    )


def prepared_as(
    bars: pd.DataFrame, params: archetypes.Params, archetype: archetypes.Archetype
) -> context.Dataset:
    return context.prepare(
        bars,
        sweep.Grid.of(params, archetype=archetype).required_context(),
        bar_minutes=1,
        price_basis=context.PriceBasis.RAW,
    )


def two_insidebar_variants(_root: str) -> list[campaign_sweep.Variant]:
    return [
        campaign_sweep.Variant("a", archetypes.INSIDEBAR, insidebar_base()),
        campaign_sweep.Variant("b", archetypes.INSIDEBAR, insidebar_base(tp_multiplier=2.0)),
    ]


def test_an_archetype_with_several_variants_records_each_and_no_earliness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBar", two_insidebar_variants)
    path = tmp_path / "cuts.json"
    written = fit("InsideBar", ["MNQ"], [1], path)
    assert [cut["variant"] for cut in written] == ["a", "b"]
    assert all(cut["early_max_trend_bars"] is None for cut in written)
    assert all("traded_early_share" not in cut for cut in written)
    first, second = campaign_sweep.sizing_cuts(path)
    assert first.fits("a")
    assert not first.fits("b")
    assert first.regime_directional_above == second.regime_directional_above, "a cut is a fact about the bars"


def test_a_cut_already_in_the_file_is_kept_and_only_the_rest_are_fitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBar", two_insidebar_variants)
    kept = campaign_sweep.SizingCut(
        root="MNQ",
        minutes=1,
        regime_consolidating_below=0.01,
        regime_directional_above=0.99,
        volume_thin_below=0.1,
        volume_heavy_above=9.0,
        labels=("size_on_trend",),
        symmetric_labels=("size_on_trend",),
        variant="a",
    )
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps([dataclasses.asdict(kept)]), encoding="utf-8")
    fit("InsideBar", ["MNQ"], [1], path)
    stored = campaign_sweep.sizing_cuts(path)
    assert stored[0] == kept
    assert [cut.variant for cut in stored] == ["a", "b"]
    assert stored[1].regime_directional_above != kept.regime_directional_above


def test_a_resolution_or_root_named_twice_is_fitted_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second copy of a cut would emit every arm twice, and each would be swept and stored."""
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBar", two_insidebar_variants)
    written = fit("InsideBar", ["MNQ", "MNQ"], [1, 1], tmp_path / "cuts.json")
    assert [(cut["root"], cut["minutes"], cut["variant"]) for cut in written] == [
        ("MNQ", 1, "a"),
        ("MNQ", 1, "b"),
    ]


SYMMETRIC_FIELDS = ("symmetric_labels", "opposing_share", "neutral_share")
"""What a cut stored before the fit read its symmetric labels lacks."""


def without_symmetric_fields(path: Path) -> list[dict[str, object]]:
    """Return the stored cuts at ``path`` as the fit wrote them before it read symmetric labels."""
    rows = json.loads(path.read_text(encoding="utf-8"))

    return [{key: value for key, value in row.items() if key not in SYMMETRIC_FIELDS} for row in rows]


def test_a_cut_stored_without_symmetric_labels_gains_them_and_nothing_else_moves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The labels come back as a fresh fit reads them, at the stored cut's own thresholds."""
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBar", two_insidebar_variants)
    path = tmp_path / "cuts.json"
    fresh = json.loads(json.dumps(fit("InsideBar", ["MNQ"], [1], path)))
    stripped = without_symmetric_fields(path)
    path.write_text(json.dumps(stripped), encoding="utf-8")
    assert all(cut.symmetric_labels is None for cut in campaign_sweep.sizing_cuts(path))
    fit("InsideBar", ["MNQ"], [1], path)
    assert json.loads(path.read_text(encoding="utf-8")) == fresh


def test_a_stored_cut_whose_signals_have_moved_is_refused_rather_than_filled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    long_walk = walk_bars(int(BARS / campaign_sweep.SELECTION_SHARE) + 1, seed=5)
    monkeypatch.setattr(splice, "load_continuous", lambda _root: long_walk)
    monkeypatch.setitem(VARIANTS, "InsideBar", two_insidebar_variants)
    path = tmp_path / "cuts.json"
    fit("InsideBar", ["MNQ"], [1], path)
    stripped = without_symmetric_fields(path)
    stripped[0]["favourable_share"] = dict.fromkeys(SIZING_LABELS, 0.5)
    path.write_text(json.dumps(stripped), encoding="utf-8")
    with pytest.raises(SystemExit, match="signals have moved"):
        fit("InsideBar", ["MNQ"], [1], path)


def test_a_one_sided_archetype_reads_its_labels_on_its_own_side(bars: pd.DataFrame) -> None:
    """DeadCatBounce only sells, so its trend label favours a signal in a downtrend."""
    base = DeadCatParams(use_ema=False, use_fast_sma=False, require_new_high=False, bars_required_to_trade=20)
    probe = probe_params(base)
    assert isinstance(probe, DeadCatParams)
    data = prepared_as(bars, probe, archetypes.DEADCATBOUNCE)
    shares = label_shares(data, probe, campaign_sweep.Variant("bracket", archetypes.DEADCATBOUNCE, base))
    signal = runner.deadcat_signal(data, base)
    down = data.trend_gate(probe.trend_key, trend.trends_mask([trend.Trend.DOWN]), probe.trend_min_agreement)
    up = data.trend_gate(probe.trend_key, trend.trends_mask([trend.Trend.UP]), probe.trend_min_agreement)
    assert signal.sum() > 50
    assert shares["favourable_share"]["size_on_trend"] == pytest.approx(down[signal].mean())
    assert shares["opposing_share"]["size_on_trend"] == pytest.approx((up & ~down)[signal].mean())
    assert shares["opposing_share"]["size_on_trend"] > 0.0, "the walk never trends up at a signal"


def test_a_variant_sweeping_both_sides_pools_its_shares_over_them(bars: pd.DataFrame) -> None:
    base = SqueezeBreakoutParams(squeeze_period=10, squeeze_below=0.5)
    probe = probe_params(base)
    data = prepared_as(bars, probe, archetypes.SQUEEZEBREAKOUT)

    def on(side: float) -> dict[str, float]:
        variant = campaign_sweep.Variant(
            "one side", archetypes.SQUEEZEBREAKOUT, dataclasses.replace(base, direction=side)
        )

        return label_shares(data, dataclasses.replace(probe, direction=side), variant)["favourable_share"]

    both = campaign_sweep.Variant("both", archetypes.SQUEEZEBREAKOUT, base, axes={"direction": [LONG, SHORT]})
    pooled = label_shares(data, probe, both)["favourable_share"]
    counts = {
        side: squeeze.squeeze_signal(data, dataclasses.replace(base, direction=side)).sum()
        for side in (LONG, SHORT)
    }
    for label in SIZING_LABELS:
        expected = sum(on(side)[label] * counts[side] for side in counts) / sum(counts.values())
        assert pooled[label] == pytest.approx(expected)
    assert pooled["size_on_trend"] != pytest.approx(on(LONG)["size_on_trend"]), "pooling changed nothing"


# -- every other archetype: the recomputed null -------------------------------------------------


def sized_insidebar(**fields: object) -> InsideBarParams:
    return insidebar_base(
        quantity_per_confluence=1,
        size_on_vwap=True,
        size_on_trend=True,
        size_on_regime=True,
        commission_per_contract=1.5,
        slippage_ticks=1.0,
        **fields,
    )


@pytest.fixture(scope="module")
def short_walk() -> pd.DataFrame:
    return walk_bars(6000, seed=9)


def test_the_recomputed_null_reports_the_configurations_own_figures(short_walk: pd.DataFrame) -> None:
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    result = shuffled_null(
        data, params, MNQ, by="profit_factor", draws=5, seed=0, archetype=archetypes.INSIDEBAR
    )
    own = stats.summarise_legs(archetypes.INSIDEBAR.legs(data, params, MNQ), data.day_codes)
    assert result["observed"] == own.profit_factor
    assert result["trades"] == own.trades
    assert result["session_close_share"] == own.session_close_share
    assert result["ambiguous_share"] == own.ambiguous_share
    assert 1 / 6 <= result["p"] <= 1.0


def test_recomputing_the_sizes_taken_reproduces_the_simulation_to_the_bit(short_walk: pd.DataFrame) -> None:
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    legs = archetypes.INSIDEBAR.legs(data, params, MNQ)
    table = np.asarray(params.size_table, dtype=np.int64)
    trade_of_leg, leg, rows = trade_rows(legs, table)
    again = resized(legs, table[rows[trade_of_leg], leg], MNQ.point_value, params.commission_per_contract)
    assert np.array_equal(again.matrix, legs.matrix[: legs.count], equal_nan=True)
    assert len(set(rows)) > 1, "every trade took one size"


def test_a_shuffle_keeps_every_trade_and_moves_only_the_sizes_among_them(short_walk: pd.DataFrame) -> None:
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    legs = archetypes.INSIDEBAR.legs(data, params, MNQ)
    table = np.asarray(params.size_table, dtype=np.int64)
    trade_of_leg, leg, rows = trade_rows(legs, table)
    shuffled = resized(
        legs,
        table[np.random.default_rng(1).permutation(rows)[trade_of_leg], leg],
        MNQ.point_value,
        params.commission_per_contract,
    )
    assert same_trades(shuffled, legs)
    assert sorted(shuffled.matrix[:, C_QUANTITY]) == sorted(legs.matrix[: legs.count, C_QUANTITY])
    assert not np.array_equal(shuffled.matrix[:, C_QUANTITY], legs.matrix[: legs.count, C_QUANTITY])


def test_a_symmetric_size_is_nulled_the_same_way(short_walk: pd.DataFrame) -> None:
    params = sized_insidebar(order_quantity=6, size_symmetric=True)
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    result = shuffled_null(data, params, MNQ, by="net_pnl", draws=4, seed=2, archetype=archetypes.INSIDEBAR)
    again = shuffled_null(data, params, MNQ, by="net_pnl", draws=4, seed=2, archetype=archetypes.INSIDEBAR)
    assert result == again
    assert 1 / 5 <= result["p"] <= 1.0


def test_a_fixed_size_is_its_own_null_on_every_archetype(short_walk: pd.DataFrame) -> None:
    params = unsized(sized_insidebar())
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    result = shuffled_null(
        data, params, MNQ, by="profit_factor", draws=3, seed=0, archetype=archetypes.INSIDEBAR
    )
    assert result["p"] == 1.0
    assert result["excess"] == 0.0


def test_the_null_is_refused_where_the_size_moved_a_trade(short_walk: pd.DataFrame) -> None:
    def dropping_a_leg_when_sized(
        data: context.Dataset, params: archetypes.Params, instrument: Instrument
    ) -> trades.LegMatrix:
        legs = archetypes.INSIDEBAR.legs(data, params, instrument)
        assert isinstance(params, InsideBarParams)
        if params.quantity_per_confluence == 0:
            return legs

        return trades.LegMatrix(legs.matrix, legs.count - 1)

    moving = dataclasses.replace(archetypes.INSIDEBAR, legs=dropping_a_leg_when_sized)
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    with pytest.raises(RuntimeError, match="moved a trade"):
        recomputed_null(data, params, MNQ, moving, by="profit_factor", draws=1, seed=0)


def test_a_trade_at_a_size_its_table_does_not_hold_is_refused(short_walk: pd.DataFrame) -> None:
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)
    legs = archetypes.INSIDEBAR.legs(data, params, MNQ)
    matrix = legs.matrix.copy()
    matrix[0, C_QUANTITY] = 99
    with pytest.raises(RuntimeError, match="no row for"):
        trade_rows(trades.LegMatrix(matrix, legs.count), np.asarray(params.size_table, dtype=np.int64))


def test_a_strategy_other_than_insidebartrailing_needs_its_arm_named(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="--variant names"):
        campaign_sizing.main(["campaign_sizing.py", "null", "--strategy", "ElasticBand"])

    asked = []

    def held_out(*args: object) -> pd.DataFrame:
        asked.append(args)

        return pd.DataFrame()

    monkeypatch.setattr(campaign_sizing, "held_out", held_out)
    arm = "target=0.0s size=confluence"
    assert (
        campaign_sizing.main(["campaign_sizing.py", "null", "--strategy", "ElasticBand", "--variant", arm])
        == 1
    )
    (args,) = asked
    assert (args[0], args[-1]) == ("ElasticBand", arm)


def test_a_shortlist_is_nulled_through_its_own_archetype(
    monkeypatch: pytest.MonkeyPatch, short_walk: pd.DataFrame
) -> None:
    monkeypatch.setattr(campaign_sizing, "stored_rows", lambda *_: pd.DataFrame())
    monkeypatch.setattr(splice, "load_continuous", lambda _root: short_walk)
    monkeypatch.setattr(campaign_sizing, "candidate_bars", lambda _stored, archive: (archive,))
    monkeypatch.setattr(
        campaign_sizing, "bars_for", lambda candidates, _stored, _block, _minutes: (candidates[0], True)
    )
    row = {
        "sweep_id": 3,
        "combo_id": 4,
        "resolution": 1,
        "stratum": "unfiltered",
        "variant": "bracket size=confluence",
        **dataclasses.asdict(sized_insidebar()),
    }
    table = campaign_sizing.null_for_shortlist(
        pd.DataFrame([row]), "MNQ", by="profit_factor", draws=3, seed=0, archetype=archetypes.INSIDEBAR
    )
    assert list(table["labels"]) == ["size_on_trend,size_on_vwap,size_on_regime"]
    assert table["trades"].iloc[0] > 0
    assert table["p"].between(1 / 4, 1.0).all()


def test_the_null_is_refused_where_recomputing_the_sizes_taken_misses_the_simulation(
    monkeypatch: pytest.MonkeyPatch, short_walk: pd.DataFrame
) -> None:
    params = sized_insidebar()
    data = prepared_as(short_walk, params, archetypes.INSIDEBAR)

    def off_by_a_dollar(
        legs: trades.LegMatrix, quantities: IntArray, point_value: float, commission: float
    ) -> trades.LegMatrix:
        moved = resized(legs, quantities, point_value, commission)
        moved.matrix[0, trades.C_NET_PNL] += 1.0

        return moved

    monkeypatch.setattr(campaign_sizing, "resized", off_by_a_dollar)
    with pytest.raises(RuntimeError, match="did not reproduce"):
        recomputed_null(data, params, MNQ, archetypes.INSIDEBAR, by="profit_factor", draws=1, seed=0)
