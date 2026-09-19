"""The NT8 export parser, which only fails when a real trade list is already in hand.

``tools/reconcile_nt8.py`` runs once per archetype, by hand, against an export that took
NinjaTrader time to produce. A parse bug is therefore discovered at the worst possible
moment, which is the whole reason these exist -- ``docs/nt8-fidelity.md`` §M22.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "reconcile_nt8.py"

# Copied from ``verification/nt8_trades/``: the real export's columns, trailing comma and
# all. A fixture that is not the export's own shape pins nothing about parsing it.
HEADER = (
    "Trade number,Instrument,Account,Strategy,Market pos.,Qty,Entry price,Exit price,"
    "Entry time,Exit time,Entry name,Exit name,Profit,Cum. net profit,Commission,"
    "Clearing Fee,Exchange Fee,IP Fee,NFA Fee,MAE,MFE,ETD,Bars,\n"
)
ROW = (
    "1,MNQ 03-24,Backtest,{strategy},Long,4,16000.00,16010.00,"
    "02/01/2024 10:00:00 AM,02/01/2024 10:05:00 AM,{entry_name},{exit_name},{profit},$80.00,$0.00,"
    "$0.00,$0.00,$0.00,$0.00,$0.00,$80.00,$0.00,5,\n"
)


def load_tool():
    """Import the script by path; ``tools/`` is deliberately not a package."""
    spec = importlib.util.spec_from_file_location("_reconcile_nt8", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


@pytest.fixture(scope="module")
def tool():
    return load_tool()


def export(tmp_path, entry_name, exit_name="Profit target", profit="$80.00"):
    path = tmp_path / "trades.csv"
    path.write_text(
        HEADER + ROW.format(strategy="X", entry_name=entry_name, exit_name=exit_name, profit=profit),
        encoding="utf-8",
    )

    return path


@pytest.mark.parametrize(
    ("entry_name", "leg"),
    [("S1", 1), ("S4", 4), ("L2", 2), ("entry1", 1), ("entry2", 2)],
)
def test_a_scale_out_port_carries_its_leg_in_the_entry_name(tool, tmp_path, entry_name, leg) -> None:
    assert tool.parse_nt8(export(tmp_path, entry_name))["leg"].iloc[0] == leg


def test_an_entry_name_with_no_digit_is_leg_one(tool, tmp_path) -> None:
    """``InsideBar.cs`` brackets one order called "entry" and never scales out.

    Before the fallback this raised on ``astype(int)`` -- with the export already produced,
    which is when it costs the most.
    """
    assert tool.parse_nt8(export(tmp_path, "entry"))["leg"].iloc[0] == 1


def test_an_unmapped_exit_name_is_refused_rather_than_left_null(tool, tmp_path) -> None:
    with pytest.raises(SystemExit, match="Sell short"):
        tool.parse_nt8(export(tmp_path, "entry", exit_name="Sell short"))


def test_every_configured_archetype_is_one_the_registry_knows(tool) -> None:
    """A typo'd key is a ``KeyError`` at the end of a NinjaTrader session, not before it."""
    from nqbt import archetypes

    for config in tool.CONFIGS.values():
        assert archetypes.for_params(config.params).params_cls is type(config.params)


def test_an_unknown_config_names_the_ones_that_exist(tool) -> None:
    """The export has already cost a NinjaTrader session by the time this can be typed wrong."""
    with pytest.raises(SystemExit, match="InsideBarTrailing-midday"):
        tool.run_nqbt("InsideBarTrailingMidday", "MNQ 03-24")


@pytest.mark.parametrize(
    ("exit_name", "reason"),
    [
        ("Trail stop", "stop"),
        ("Exit Long Trend Violation", "signal"),
        ("Exit Short Trend Violation", "signal"),
    ],
)
def test_insidebartrailings_three_new_exit_names_are_mapped(tool, tmp_path, exit_name, reason) -> None:
    """The names NT8 will write for `SetTrailStop` and for the two `ExitLong`/`ExitShort` calls.

    A trail is still a stop, and the trend violation is the archetype's ``EXIT_SIGNAL``. Getting
    either wrong stops the run after the export already cost a NinjaTrader session.
    """
    parsed = tool.parse_nt8(export(tmp_path, "entry1", exit_name=exit_name))
    assert parsed["exit_reason"].iloc[0] == reason


@pytest.mark.parametrize("exit_name", ["Exit Long Max Loss", "Exit Short Max Loss"])
def test_the_max_loss_exit_is_left_unmapped_on_purpose(tool, tmp_path, exit_name) -> None:
    """It is unreachable at ``MaximumLossPerTrade = 0``, so an export carrying one is a finding.

    Mapping it would let the branch the port declares dead pass silently through a
    reconciliation -- ``docs/nt8-fidelity.md`` §M23.
    """
    with pytest.raises(SystemExit, match="Max Loss"):
        tool.parse_nt8(export(tmp_path, "entry1", exit_name=exit_name))


def test_the_insidebartrailing_config_is_setdefaults_unchanged(tool) -> None:
    """Unlike InsideBar's, nothing has to be switched off: there is no wall-clock rule here.

    Pinned because "the defaults" is the whole configuration a reconciliation of it assumes --
    ``docs/nt8-fidelity.md`` §M23, "What a reconciliation of it will have to hold fixed".
    """
    from nqbt.sim.types import InsideBarTrailingParams

    assert tool.CONFIGS["InsideBarTrailing"].params == InsideBarTrailingParams()


def test_the_trading_window_is_the_only_thing_the_midday_config_moves(tool) -> None:
    """The gated run has to differ from the baseline in the gate and nothing else.

    Otherwise a disagreement cannot be attributed to the new rule, which is the whole design
    of the pair -- ``docs/nt8-fidelity.md``, "The entry trading window, and the zone it is
    measured in".
    """
    from nqbt import timeofday

    baseline = tool.CONFIGS["InsideBarTrailing"].params.as_dict()
    midday = tool.CONFIGS["InsideBarTrailing-midday"].params.as_dict()

    assert {k for k in midday if midday[k] != baseline[k]} == {"phase_filter"}
    assert midday["phase_filter"] == timeofday.SessionPhase.MIDDAY.bit


def test_the_ported_config_is_combo_2035_from_the_findings_file(tool) -> None:
    """Every swept parameter, bar size and contract size of the cell Phase 0 named.

    ``docs/findings/m43-midday-candidates-ranked.md`` § "The cell to port" is the source, and
    porting a configuration that is not the one measured is the failure this exists to stop.
    Costs are the one deliberate departure -- see the zero-cost test below.
    """
    config = tool.CONFIGS["InsideBarTrailing-midday-2035"]
    params = config.params.as_dict()

    assert config.resolution == 5
    assert params["order_quantity"] == 6
    assert params["ema_period"] == 44
    assert params["ema_kind"] == "ema"
    assert params["fast_sma_period"] == 20
    assert params["fast_sma_kind"] == "sma"
    assert params["slow_sma_period"] == 125
    assert params["slow_sma_kind"] == "sma"
    assert params["error_margin"] == 0.05
    assert params["atr_length"] == 14
    assert params["atr_multiplier"] == 10.0
    assert params["tp_multiplier"] == 1.0
    assert params["partial_take_profit_percentage"] == 0.6
    assert params["trailing_stop_multiplier"] == 5.0
    assert params["position_update_loss_gate"] == 200.0
    assert params["maximum_loss_per_trade"] == 0.0
    assert params["bars_required_to_trade"] == 5
    assert params["no_entry_minutes_before_close"] == 0
    assert params["max_hold_bars"] == 0
    assert params["ambiguity_policy"] == 1
    assert params["fill_limit_on_touch"] is True
    assert params["block_entry_at_session_close"] is True
    assert params["round_targets"] is True


def test_the_ported_config_leaves_every_context_filter_but_the_phase_off(tool) -> None:
    """The findings file's "every other filter is off" row, which is easy to lose silently.

    A filter left on would thin the signal and the two tiers would disagree on entries the
    NinjaScript has no rule for at all.
    """
    from nqbt import compression, higher_timeframe, regime, timeofday, trend, volume

    params = tool.CONFIGS["InsideBarTrailing-midday-2035"].params.as_dict()

    assert params["phase_filter"] == timeofday.SessionPhase.MIDDAY.bit
    assert params["regime_filter"] == regime.ALL_REGIMES
    assert params["volume_filter"] == volume.ALL_STATES
    assert params["compression_filter"] == compression.ALL_STATES
    assert params["trend_filter"] == trend.ALL_TRENDS
    assert params["higher_timeframe_filter"] == higher_timeframe.ALL_SIDES


def test_every_config_reconciles_at_zero_cost(tool) -> None:
    """NT8 ran with no fee template and no slippage, so both sides have to be at zero.

    ``docs/findings/m43-midday-candidates-ranked.md`` costs the campaign at $1.50 a contract
    and a tick of slippage; carrying those here would move every entry price and every P&L
    and read as a fill-semantics failure rather than as a cost difference.
    """
    for name, config in tool.CONFIGS.items():
        params = config.params.as_dict()
        assert params["commission_per_contract"] == 0.0, name
        assert params["slippage_ticks"] == 0.0, name


def test_only_the_ported_config_runs_at_five_minutes(tool) -> None:
    """Resolution is per configuration, and the default has to stay 1 for the older four."""
    at_five = {name for name, config in tool.CONFIGS.items() if config.resolution == 5}

    assert at_five == {"InsideBarTrailing-midday-2035"}
    assert all(c.resolution == 1 for n, c in tool.CONFIGS.items() if n not in at_five)


def test_the_insidebar_config_switches_the_wall_clock_window_off(tool) -> None:
    """The C# measures the window against the real clock, so the port's rule cannot match it.

    Both sides have to have it off for the reconciliation to be testing the same strategy --
    ``docs/nt8-fidelity.md``, "A no-entry window before the session close".
    """
    assert tool.CONFIGS["InsideBar"].params.no_entry_minutes_before_close == 0


@pytest.mark.parametrize("profit", ["-$80.00", "($80.00)"])
def test_a_loss_stays_a_loss_in_either_of_nt8s_sign_conventions(tool, tmp_path, profit) -> None:
    """Accounting format is a regional setting, and stripping the brackets is not enough.

    A dropped sign still joins, so it reads as a P&L disagreement on every losing leg rather
    than as a parse bug -- which is the expensive way to find out.
    """
    assert tool.parse_nt8(export(tmp_path, "entry", profit=profit))["net_pnl"].iloc[0] == -80.0


def test_a_profit_is_left_alone(tool, tmp_path) -> None:
    assert tool.parse_nt8(export(tmp_path, "entry", profit="$1080.00"))["net_pnl"].iloc[0] == 1080.0


@pytest.mark.parametrize(
    ("contract", "point_value"),
    [
        ("NQ 03-24", 20.0),
        ("MNQ 03-24", 2.0),
        ("ES 03-24", 50.0),
        ("MES 03-24", 5.0),
        ("GC 02-24", 100.0),
        ("MGC 02-24", 10.0),
    ],
)
def test_the_instrument_comes_from_the_contract_root(tool, monkeypatch, contract, point_value) -> None:
    """Every root but NQ was reconciled as MNQ.

    Chosen off a ``startswith("NQ")`` test, ES priced at $2 a point instead of $50 does not
    fail -- it just disagrees with the trade list.
    """
    seen = {}

    class SpyArchetype:
        def context_for(self, axes):
            return None

        def run(self, data, params, instrument):
            seen["instrument"] = instrument

            return pd.DataFrame({"entry_time": [], "leg": []})

    def spy_prepare(bars, spec, **kwargs):
        seen["price_basis"] = kwargs.get("price_basis")

        return None

    monkeypatch.setattr(tool.ingest, "load_contract", lambda contract_id: None)
    monkeypatch.setattr(tool.context, "prepare", spy_prepare)
    monkeypatch.setattr(tool.archetypes, "for_params", lambda params: SpyArchetype())

    tool.run_nqbt("DeadCatBounce", contract)

    assert seen["instrument"].symbol == contract.split()[0]
    assert seen["instrument"].point_value == point_value
    # One contract's own prices are never adjusted, and the reconciliation is the one place
    # an absolute level has to mean what NT8 meant by it -- [#341].
    assert seen["price_basis"] is tool.context.PriceBasis.RAW


def test_an_unknown_root_is_refused_rather_than_priced_as_something_else(tool) -> None:
    with pytest.raises(ValueError, match="unknown root"):
        tool.run_nqbt("DeadCatBounce", "ZZ 03-24")


def test_the_bars_are_resampled_to_the_configs_own_resolution(tool, monkeypatch) -> None:
    """A 5-minute configuration run on 1-minute bars disagrees on almost every leg.

    The bar size is part of the configuration rather than of the invocation, so nothing at
    the command line can put the two out of step.
    """
    seen = {}

    class SpyArchetype:
        def context_for(self, axes):
            return None

        def run(self, data, params, instrument):
            return pd.DataFrame({"entry_time": [], "leg": []})

    def spy_resample(bars, minutes):
        seen["minutes"] = minutes

        return bars

    def spy_prepare(bars, spec, **kwargs):
        seen["bar_minutes"] = kwargs.get("bar_minutes")

        return None

    monkeypatch.setattr(tool.ingest, "load_contract", lambda contract_id: None)
    monkeypatch.setattr(tool.resample, "resample", spy_resample)
    monkeypatch.setattr(tool.context, "prepare", spy_prepare)
    monkeypatch.setattr(tool.archetypes, "for_params", lambda params: SpyArchetype())

    tool.run_nqbt("InsideBarTrailing-midday-2035", "MNQ 03-24")

    assert seen["minutes"] == 5
    assert seen["bar_minutes"] == 5
