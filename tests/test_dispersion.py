"""Tests for per-contract sweeps and the dispersion framing around them.

Two things are being guarded. The **statistics** must not become a second definition of
what `stats.py` already computes, which is the most expensive defect class this codebase
has. And the **framing** must survive: the module exists to report a spread rather than a
winner, so the tests that matter are the ones that would fail if it quietly started ranking.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import dispersion, sessions, stats
from nqbt.dispersion import DispersionError


def leg_log(pnl_per_trade, *, legs: int = 2, start: str = "2024-01-02") -> pd.DataFrame:
    """A leg-level log whose trades sum to ``pnl_per_trade``.

    Split across legs on purpose: everything here has to survive the leg -> trade collapse,
    and a one-leg-per-trade fixture would never exercise it.
    """
    rows = []
    base = pd.Timestamp(start, tz="UTC")
    for trade_id, total in enumerate(pnl_per_trade, start=1):
        share = total / legs
        for leg in range(1, legs + 1):
            rows.append(
                {
                    "trade_id": trade_id,
                    "leg": leg,
                    "net_pnl": share,
                    "commission": 0.5,
                    "bars_held": 5,
                    "mae_points": 1.0,
                    "mfe_points": 2.0,
                    "r_multiple": share / 10.0,
                    "ambiguous_bar": False,
                    "exit_reason": "target",
                    "entry_time": base + pd.Timedelta(days=trade_id),
                    "exit_time": base + pd.Timedelta(days=trade_id, minutes=5),
                },
            )

    return pd.DataFrame(rows)


# -- trade_statistic must not become a second definition -----------------------


@pytest.mark.parametrize("name", stats.TRADE_PNL_STATISTICS)
@pytest.mark.parametrize(
    "pnl",
    [
        [100.0, -50.0, 200.0, -75.0, 30.0],
        [-10.0] * 8,  # no wins: profit factor must not divide by a zero numerator
        [10.0] * 8,  # no losses: the guarded division reports infinity
        [0.0, 5.0, -5.0, 0.0],  # scratches
    ],
)
def test_the_fast_statistic_equals_the_reference_exactly(name, pnl) -> None:
    """``summarise`` is the reference; ``trade_statistic`` only exists to be faster.

    Exact equality rather than ``approx``: they share ``_ratio`` and operate on the same
    float64 sums, so any difference at all means they have drifted into two definitions.
    """
    log = leg_log(pnl)
    fast = stats.trade_statistic(stats.per_trade(log)["net_pnl"].to_numpy(float), name)
    reference = getattr(stats.summarise(log), name)
    assert fast == reference, f"{name}: {fast!r} != {reference!r}"


def test_a_time_dependent_statistic_is_refused_rather_than_approximated() -> None:
    with pytest.raises(ValueError, match="per-trade P&L alone"):
        stats.trade_statistic(np.array([1.0, -1.0]), "sharpe")


def test_an_empty_trade_vector_is_zero_not_a_crash() -> None:
    for name in stats.TRADE_PNL_STATISTICS:
        assert stats.trade_statistic(np.array([]), name) == 0.0


# -- the framing: dispersion reports a spread, not a winner --------------------


def results_table(rows) -> pd.DataFrame:
    """``(contract, combo_id, trades, profit_factor)`` tuples as a results frame."""
    return pd.DataFrame(rows, columns=["contract", "combo_id", "trades", "profit_factor"])


def test_dispersion_is_returned_in_combo_order_not_performance_order() -> None:
    """The leaderboard this module exists to refuse must not appear by accident."""
    table = results_table([("A", 0, 100, 0.5), ("B", 0, 100, 0.6), ("A", 1, 100, 2.0), ("B", 1, 100, 2.2)])
    out = dispersion.dispersion(table)
    assert list(out["combo_id"]) == [0, 1], "sorted by performance; combo 1 is far better"


def test_a_contract_below_the_trade_floor_is_excluded_and_counted() -> None:
    """A profit factor from four trades is noise, and noise has the widest spread."""
    table = results_table([("A", 0, 400, 0.9), ("B", 0, 350, 1.0), ("C", 0, 4, 12.0)])
    out = dispersion.dispersion(table, min_trades=30).iloc[0]
    assert out["contracts"] == 3
    assert out["contracts_used"] == 2
    assert out["contracts_dropped"] == 1
    assert out["profit_factor_max"] == 1.0, "the 4-trade outlier reached the spread"
    assert out["profit_factor_range"] == pytest.approx(0.1)


def test_an_infinite_profit_factor_is_dropped_rather_than_poisoning_the_spread() -> None:
    """A contract with no losing trade reports inf, which would make every spread inf."""
    table = results_table([("A", 0, 100, 0.9), ("B", 0, 100, 1.1), ("C", 0, 100, np.inf)])
    out = dispersion.dispersion(table).iloc[0]
    assert out["contracts_used"] == 2
    assert np.isfinite(out["profit_factor_range"])


def test_trades_total_counts_every_contract_including_the_dropped_ones() -> None:
    table = results_table([("A", 0, 400, 0.9), ("C", 0, 4, 12.0)])
    assert dispersion.dispersion(table).iloc[0]["trades_total"] == 404


def test_an_unknown_statistic_names_what_is_available() -> None:
    with pytest.raises(DispersionError, match="no column 'sharpe_ratio'"):
        dispersion.dispersion(results_table([("A", 0, 50, 1.0)]), by="sharpe_ratio")


# -- the permutation test ------------------------------------------------------


def test_spread_from_one_pooled_population_looks_like_noise() -> None:
    """Every contract drawn from the same distribution: neither measure should fire."""
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(8)}
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)
    assert out["contracts"] == 8
    for name, result in out["spread"].items():
        assert result["p_value"] > 0.05, f"{name} flagged one population as differing"


def test_a_broadly_different_set_of_contracts_moves_the_iqr() -> None:
    """Half the contracts from a different population: the robust measure should see it."""
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(5)}
    logs.update({f"H{i}": leg_log(rng.normal(80, 100, 200).tolist()) for i in range(5)})
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)
    assert out["spread"]["iqr"]["p_value"] < 0.05, "no power against a real bulk difference"


def test_one_rogue_contract_moves_the_range_and_not_the_iqr() -> None:
    """The documented division of labour between the two measures.

    A single bad contract -- which in practice means a bad roll date or a hole, not a market
    insight -- is exactly what the IQR is built to ignore. If only the robust measure were
    reported, the data-integrity signal would be discarded silently.
    """
    rng = np.random.default_rng(4)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 200).tolist()) for i in range(9)}
    logs["ROGUE"] = leg_log(rng.normal(220, 150, 200).tolist())
    out = dispersion.spread_vs_resampling(logs, iterations=400, seed=1)

    assert out["spread"]["range"]["p_value"] < 0.05, "the rogue contract went unseen"
    assert out["spread"]["iqr"]["p_value"] > 0.05, (
        "the IQR moved on one outlier; it is supposed to be robust to exactly that"
    )


def test_every_permutation_reproduces_the_observed_group_sizes() -> None:
    """Otherwise the null mixes a spread effect with a sample-size effect.

    Checked by construction: unequal groups whose small member is the one that would move.
    """
    rng = np.random.default_rng(2)
    logs = {
        "BIG": leg_log(rng.normal(0, 100, 400).tolist()),
        "SMALL": leg_log(rng.normal(0, 100, 40).tolist()),
        "MID": leg_log(rng.normal(0, 100, 120).tolist()),
    }
    out = dispersion.spread_vs_resampling(logs, iterations=50, seed=3)
    assert out["trades"] == 400 + 40 + 120
    assert out["contracts"] == 3
    assert set(out["spread"]) == set(dispersion.SPREAD_MEASURES)


def test_the_permutation_test_is_deterministic_for_a_seed() -> None:
    rng = np.random.default_rng(5)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 120).tolist()) for i in range(4)}
    a = dispersion.spread_vs_resampling(logs, iterations=100, seed=7)
    b = dispersion.spread_vs_resampling(logs, iterations=100, seed=7)
    assert a == b


def test_a_time_dependent_statistic_is_refused_by_the_permutation_test() -> None:
    """Shuffling trades between contracts destroys the ordering Sharpe is computed over."""
    rng = np.random.default_rng(6)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 80).tolist()) for i in range(3)}
    with pytest.raises(DispersionError, match="not permutable"):
        dispersion.spread_vs_resampling(logs, by="sharpe")


def test_one_usable_contract_cannot_have_a_spread() -> None:
    logs = {"A": leg_log([10.0] * 100), "B": leg_log([10.0] * 3)}
    with pytest.raises(DispersionError, match="at least 2 contracts"):
        dispersion.spread_vs_resampling(logs, min_trades=30)


def test_the_observed_statistic_matches_the_reference_per_contract() -> None:
    """The reported per-contract numbers are the same ones ``summarise`` would give."""
    rng = np.random.default_rng(8)
    logs = {f"C{i}": leg_log(rng.normal(5, 100, 100).tolist()) for i in range(3)}
    out = dispersion.spread_vs_resampling(logs, iterations=10, seed=0)
    for contract, value in out["per_contract"].items():
        assert value == stats.summarise(logs[contract]).profit_factor


# -- a synthetic cache, so the data path is tested rather than skipped ---------
#
# These used to be real-data tests guarded by ``pytest.skip`` when the MNQ cache was absent,
# which meant CI -- the only place that measures coverage -- exercised none of them. Writing
# a two-contract cache into ``tmp_path`` costs a few hundred bars and tests the same code.


def synthetic_contract(start: str, sessions_wanted: int, seed: int) -> pd.DataFrame:
    """One contract's cached bars: whole ETH sessions, wicks wide enough to trade."""
    rng = np.random.default_rng(seed)
    stamps: list[pd.Timestamp] = []
    open_et = pd.Timestamp(start, tz=sessions.EASTERN)
    for _ in range(sessions_wanted):
        # Skipped before generating, not after: a session opening on a Friday evening ends on
        # a Saturday, and every bar of it is out of session.
        while open_et.dayofweek in (4, 5):
            open_et += pd.Timedelta(days=1)
        stamps.extend(open_et + pd.Timedelta(minutes=m) for m in range(1, 1381))
        open_et += pd.Timedelta(days=1)

    idx = pd.DatetimeIndex(stamps).tz_convert("UTC")
    idx.name = "ts_utc"
    n = len(idx)
    close = 16000.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0, 3.0, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0, 3.0, n)),
            "close": close,
            "volume": rng.integers(1, 500, n).astype(float),
        },
        index=idx,
    )
    info = sessions.classify(idx)
    frame["trading_day"] = info.trading_day
    frame["in_session"] = info.in_session

    return frame


@pytest.fixture
def cache(tmp_path):
    """A cache holding two contracts and the continuous series spliced from them.

    The contracts **overlap in time** on purpose -- real ones do, and that overlap is the
    whole reason the front-month window exists.
    """
    pytest.importorskip("pyarrow")
    from nqbt import ingest, splice
    from nqbt.instruments import ContractId

    frames = {
        "MNQ 03-24": synthetic_contract("2024-01-01 18:00", 8, seed=1),
        "MNQ 06-24": synthetic_contract("2024-01-05 18:00", 8, seed=2),
    }
    for name, frame in frames.items():
        path = ingest.contract_cache_path(ContractId.parse(name), tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, engine="pyarrow", index=True)

    front, back = frames["MNQ 03-24"], frames["MNQ 06-24"]
    roll = pd.Timestamp("2024-01-09 18:00", tz=sessions.EASTERN).tz_convert("UTC")
    series = pd.concat(
        [
            front[(front.index < roll) & front["in_session"]].assign(contract="MNQ 03-24"),
            back[(back.index >= roll) & back["in_session"]].assign(contract="MNQ 06-24"),
        ],
    ).drop(columns=["in_session"])

    out = splice.continuous_path("MNQ", back_adjust=True, cache_dir=tmp_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    series.to_parquet(out, engine="pyarrow", index=True)

    return tmp_path, frames, series


def test_front_month_windows_are_contiguous_and_do_not_overlap(cache) -> None:
    tmp_path, _, _ = cache
    windows = dispersion.front_month_windows("MNQ", cache_dir=tmp_path)
    assert list(windows.index) == ["MNQ 03-24", "MNQ 06-24"]
    assert windows["start"].is_monotonic_increasing
    assert (windows["start"].to_numpy()[1:] > windows["end"].to_numpy()[:-1]).all()


def test_the_windows_account_for_the_continuous_series_exactly(cache) -> None:
    """The strongest available check that these are the splicer's own decisions.

    Front-month windows are non-overlapping and sum to the continuous series. If they did
    not, some calendar days would be double-counted or missing, and every cross-contract
    aggregate would be wrong by that amount.
    """
    tmp_path, _, series = cache
    windows = dispersion.front_month_windows("MNQ", cache_dir=tmp_path)
    assert int(windows["continuous_bars"].sum()) == len(series)


def test_the_front_month_window_is_a_strict_subset_of_a_contracts_life(cache) -> None:
    """The contracts overlap; the windows must not, or aggregates double-count."""
    tmp_path, frames, _ = cache
    windowed = dispersion.contract_frames("MNQ", cache_dir=tmp_path)
    full = dispersion.contract_frames("MNQ", cache_dir=tmp_path, full_life=True)

    for name in frames:
        assert len(windowed[name]) < len(full[name]), f"{name} was not trimmed"
        assert len(full[name]) == len(frames[name])

    a, b = windowed["MNQ 03-24"], windowed["MNQ 06-24"]
    assert a.index.max() < b.index.min(), "front-month windows overlap"
    overlap = full["MNQ 03-24"].index.intersection(full["MNQ 06-24"].index)
    assert len(overlap) > 0, "the fixture's contracts do not overlap; the test proves nothing"


def test_contract_frames_return_the_cached_prices_untouched(cache) -> None:
    """Raw, never back-adjusted -- see the module docstring on round-number stops."""
    tmp_path, frames, _ = cache
    got = dispersion.contract_frames("MNQ", cache_dir=tmp_path)
    for name, frame in got.items():
        pd.testing.assert_series_equal(frame["close"], frames[name].loc[frame.index, "close"])


def test_coverage_reports_a_sample_size_for_every_contract(cache) -> None:
    tmp_path, _, _ = cache
    cover = dispersion.coverage(dispersion.contract_frames("MNQ", cache_dir=tmp_path))
    assert len(cover) == 2
    assert (cover["sessions"] > 0).all()
    assert (cover["in_session_bars"] <= cover["bars"]).all()
    assert cover["contract"].is_unique
    assert cover["start"].is_monotonic_increasing


def test_a_cache_with_no_contract_bars_says_so(cache, tmp_path) -> None:
    """The continuous series names contracts whose per-contract cache is missing."""
    from nqbt import splice

    empty = tmp_path / "empty"
    src = splice.continuous_path("MNQ", back_adjust=True, cache_dir=cache[0])
    dst = splice.continuous_path("MNQ", back_adjust=True, cache_dir=empty)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())

    with pytest.raises(FileNotFoundError, match="no cached bars"):
        dispersion.contract_frames("MNQ", cache_dir=empty)


def test_a_window_that_selects_no_bars_leaves_the_contract_out(cache) -> None:
    """Guards the ``if len(bars)`` skip, which would otherwise ship an empty frame."""
    tmp_path, _, series = cache
    moved = series.copy()
    moved.loc[moved["contract"] == "MNQ 06-24", "contract"] = "MNQ 09-24"
    from nqbt import ingest, splice
    from nqbt.instruments import ContractId

    # A contract in the continuous series whose own cache holds only far-earlier bars.
    stale = synthetic_contract("2023-01-02 18:00", 2, seed=3)
    path = ingest.contract_cache_path(ContractId.parse("MNQ 09-24"), tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale.to_parquet(path, engine="pyarrow", index=True)
    moved.to_parquet(splice.continuous_path("MNQ", back_adjust=True, cache_dir=tmp_path), engine="pyarrow")

    frames = dispersion.contract_frames("MNQ", cache_dir=tmp_path)
    assert set(frames) == {"MNQ 03-24"}, "a contract with no bars in its window was kept"


def test_a_root_where_no_window_selects_any_bars_says_so(cache) -> None:
    """Every contract cached, none of them covering its own window.

    The shape of a stale cache: the continuous series was spliced from bars that have since
    been re-ingested elsewhere. Returning ``{}`` here would surface much later as an
    unexplained empty results table.
    """
    from nqbt import ingest
    from nqbt.instruments import ContractId

    tmp_path, _, _ = cache
    for name in ("MNQ 03-24", "MNQ 06-24"):
        stale = synthetic_contract("2019-01-02 18:00", 2, seed=9)
        stale.to_parquet(
            ingest.contract_cache_path(ContractId.parse(name), tmp_path),
            engine="pyarrow",
            index=True,
        )

    with pytest.raises(DispersionError, match="no cached per-contract bars"):
        dispersion.contract_frames("MNQ", cache_dir=tmp_path)


# -- sweep_contracts, end to end ----------------------------------------------


@pytest.fixture
def swept(cache):
    from nqbt import sweep
    from nqbt.instruments import NQ
    from nqbt.sim.types import DeadCatParams

    tmp_path, _, _ = cache
    grid = sweep.Grid.of(DeadCatParams(bars_required_to_trade=200), ema_period=[9, 21])

    return dispersion.sweep_contracts("MNQ", grid, NQ, cache_dir=tmp_path, keep_trades=True)


def test_sweep_contracts_returns_one_row_per_contract_and_combination(swept) -> None:
    results, _, _ = swept
    assert len(results) == 2 * 2
    assert set(results["contract"]) == {"MNQ 03-24", "MNQ 06-24"}
    assert sorted(results["combo_id"].unique()) == [0, 1]
    assert results["trades"].sum() > 0, "the fixture traded nothing; the test proves nothing"


def test_every_result_row_carries_its_own_sample_size(swept) -> None:
    """A profit factor from 30 trades must not sit unlabelled beside one from 400."""
    results, cover, _ = swept
    for column in ("bars", "in_session_bars", "sessions", "trades"):
        assert column in results.columns
        assert (results[column] > 0).all()

    joined = results.merge(cover, on="contract", suffixes=("", "_cover"))
    assert (joined["bars"] == joined["bars_cover"]).all(), "coverage joined to the wrong row"


def test_contract_is_the_leading_column_so_no_row_is_anonymous(swept) -> None:
    results, _, _ = swept
    assert results.columns[0] == "contract"


def test_trade_logs_come_back_keyed_by_contract_and_combination(swept) -> None:
    _, _, logs = swept
    assert set(logs) == {
        ("MNQ 03-24", 0),
        ("MNQ 03-24", 1),
        ("MNQ 06-24", 0),
        ("MNQ 06-24", 1),
    }
    for (_, combo_id), log in logs.items():
        assert len(log), f"combo {combo_id} produced an empty log"
        assert {"trade_id", "net_pnl"} <= set(log.columns)


def test_no_logs_are_kept_unless_asked_for(cache) -> None:
    """A wide sweep's logs do not fit in memory, so the default must not hold them."""
    from nqbt import sweep
    from nqbt.instruments import NQ
    from nqbt.sim.types import DeadCatParams

    tmp_path, _, _ = cache
    grid = sweep.Grid.of(DeadCatParams(bars_required_to_trade=200))
    _, _, logs = dispersion.sweep_contracts("MNQ", grid, NQ, cache_dir=tmp_path)
    assert logs == {}


def test_the_per_contract_results_match_running_that_contract_directly(swept, cache) -> None:
    """The loop must not perturb what a single-contract sweep would have produced."""
    from nqbt import sweep
    from nqbt.instruments import NQ
    from nqbt.sim.types import DeadCatParams

    results, _, _ = swept
    tmp_path, _, _ = cache
    frames = dispersion.contract_frames("MNQ", cache_dir=tmp_path)
    grid = sweep.Grid.of(DeadCatParams(bars_required_to_trade=200), ema_period=[9, 21])

    direct, _ = sweep.sweep(frames["MNQ 03-24"], grid, NQ)
    mine = results[results["contract"] == "MNQ 03-24"].reset_index(drop=True)
    for column in ("combo_id", "trades", "net_pnl", "profit_factor"):
        pd.testing.assert_series_equal(mine[column], direct[column], check_names=False, check_dtype=False)


def test_a_root_where_nothing_trades_says_so_rather_than_returning_an_empty_table(cache) -> None:
    """``bars_required_to_trade`` past the end of every contract produces no rows at all."""
    from nqbt import sweep
    from nqbt.instruments import NQ
    from nqbt.sim.types import DeadCatParams

    tmp_path, _, _ = cache
    grid = sweep.Grid.of(DeadCatParams(bars_required_to_trade=10**9))
    results, _, _ = dispersion.sweep_contracts("MNQ", grid, NQ, cache_dir=tmp_path)
    assert (results["trades"] == 0).all()


def test_the_whole_pipeline_runs_from_a_sweep_through_to_a_p_value(swept) -> None:
    """The path a user actually walks, rather than each piece in isolation."""
    results, _, logs = swept
    spread = dispersion.dispersion(results, min_trades=1)
    assert list(spread["combo_id"]) == [0, 1]
    assert (spread["contracts"] == 2).all()

    combo0 = {c: log for (c, combo_id), log in logs.items() if combo_id == 0}
    out = dispersion.spread_vs_resampling(combo0, iterations=50, seed=0, min_trades=1)
    assert set(out["spread"]) == set(dispersion.SPREAD_MEASURES)
    assert 0.0 <= out["spread"]["iqr"]["p_value"] <= 1.0
    assert out["contracts"] == 2


def test_a_contract_with_no_losing_trade_is_refused_rather_than_reported_as_infinite() -> None:
    """An infinite profit factor would make every spread infinite and every p-value 1."""
    logs = {"A": leg_log([10.0] * 40), "B": leg_log([5.0, -5.0] * 20)}
    with pytest.raises(DispersionError, match="not finite"):
        dispersion.spread_vs_resampling(logs, min_trades=1)
