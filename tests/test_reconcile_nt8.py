"""The NT8 export parser, which only fails when a real trade list is already in hand.

``tools/reconcile_nt8.py`` runs once per archetype, by hand, against an export that took
NinjaTrader time to produce. A parse bug is therefore discovered at the worst possible
moment, which is the whole reason these exist -- ``docs/nt8-fidelity.md`` §M22.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "reconcile_nt8.py"

HEADER = (
    "Trade number,Instrument,Account,Strategy,Market pos.,Quantity,Entry price,Exit price,"
    "Entry time,Exit time,Entry name,Exit name,Profit,Cum. net profit,Commission,MAE,MFE,ETD,Bars\n"
)
ROW = (
    "1,MNQ 03-24,Backtest,{strategy},Long,4,16000.00,16010.00,"
    "02/01/2024 10:00:00 AM,02/01/2024 10:05:00 AM,{entry_name},{exit_name},$40.00,$40.00,$0.00,"
    "$0.00,$0.00,$0.00,5\n"
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


def export(tmp_path, entry_name, exit_name="Profit target"):
    path = tmp_path / "trades.csv"
    path.write_text(
        HEADER + ROW.format(strategy="X", entry_name=entry_name, exit_name=exit_name),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(("entry_name", "leg"), [("S1", 1), ("S4", 4), ("L2", 2)])
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

    for name, params in tool.CONFIGS.items():
        assert archetypes.get(name).params_cls is type(params)


def test_the_insidebar_config_switches_the_wall_clock_window_off(tool) -> None:
    """The C# measures the window against the real clock, so the port's rule cannot match it.

    Both sides have to have it off for the reconciliation to be testing the same strategy --
    ``docs/nt8-fidelity.md``, "A no-entry window before the session close".
    """
    assert tool.CONFIGS["InsideBar"].no_entry_minutes_before_close == 0
