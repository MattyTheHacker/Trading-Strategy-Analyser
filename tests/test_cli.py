"""The CLI's job is to report, so every test here asserts on what it wrote.

Exit codes alone would pass against a command that computed the answer and discarded it,
which is exactly the regression these tests exist to catch.
"""

import argparse
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from nqbt import cli, conditions, ingest, splice, stats


@pytest.fixture(autouse=True)
def console(caplog):
    """Capture what the CLI logs, at the level its own entry point sets.

    Deliberately does not call ``nqbt.logsetup.configure``: it uses ``basicConfig(force=True)``,
    which would tear ``caplog``'s own handler off the root logger. Tests that need the real
    handlers -- the stdout/stderr split -- go through ``main`` and read ``capsys`` instead.
    """
    caplog.set_level(logging.INFO, logger="nqbt")

    return caplog


@pytest.fixture
def base_args():
    return argparse.Namespace(data_dir=Path("/mock/data"), cache_dir=Path("/mock/cache"))


def output(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


# --- error handling ----------------------------------------------------------


def failing_main(monkeypatch, error: Exception) -> None:
    parser = MagicMock()
    parser.parse_args.return_value = argparse.Namespace(func=MagicMock(side_effect=error))
    monkeypatch.setattr(cli, "build_parser", MagicMock(return_value=parser))


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("no cached bars"), splice.SpliceError("no crossover"), ingest.IngestError("no bars")],
)
def test_main_explains_an_expected_failure_on_stderr(monkeypatch, capsys, error) -> None:
    """An expected failure is explained, not swallowed into a bare exit code.

    Reading ``capsys`` rather than ``caplog`` is the point: it exercises the real handler
    split, so a diagnostic that leaked onto stdout and corrupted a pipe would fail here.
    """
    failing_main(monkeypatch, error)

    assert cli.main(["dummy_arg"]) == 1
    captured = capsys.readouterr()
    assert captured.err == f"error: {error}\n"
    assert captured.out == ""


def test_main_writes_results_to_stdout_so_they_can_be_piped(monkeypatch, capsys) -> None:
    parser = MagicMock()
    parser.parse_args.return_value = argparse.Namespace(func=lambda _: _log_and_succeed())
    monkeypatch.setattr(cli, "build_parser", MagicMock(return_value=parser))

    assert cli.main(["dummy_arg"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "a result\n"
    assert captured.err == ""


def _log_and_succeed() -> int:
    cli.logger.info("a result")

    return 0


# --- ingest ------------------------------------------------------------------


def test_cmd_ingest_reports_the_merge_and_the_bar_count(monkeypatch, base_args, console) -> None:
    base_args.root = "MNQ"
    base_args.force = False

    merge = MagicMock(added=True, revised=False, bars=500)
    merge.__str__ = lambda self: "MNQ 03-24: +12 bars"
    result = MagicMock(warnings=["a stray print"], rows_total=100)
    result.__str__ = lambda self: "MNQ 03-24 appended"
    ingest_all = MagicMock(return_value=([merge], [result], ["NG 02-26.Last.txt: not quarterly"]))
    monkeypatch.setattr(cli.ingest, "ingest_all", ingest_all)

    assert cli._cmd_ingest(base_args) == 0
    ingest_all.assert_called_once_with(
        data_dir=base_args.data_dir,
        cache_dir=base_args.cache_dir,
        root="MNQ",
        force=False,
    )

    text = output(console)
    assert "archive: 1 contracts, 500 bars (1 changed by this merge)" in text
    assert "MNQ 03-24: +12 bars" in text
    assert "MNQ 03-24 appended" in text
    assert "[!] a stray print" in text
    assert "[!] skipped NG 02-26.Last.txt: not quarterly" in text
    assert "1 contracts, 100 bars cached in" in text


# --- contracts ---------------------------------------------------------------


def test_cmd_contracts_says_so_when_nothing_is_ingested(monkeypatch, base_args, console) -> None:
    monkeypatch.setattr(cli.ingest, "load_manifest", MagicMock(return_value=None))
    assert cli._cmd_contracts(base_args) == 1
    assert "nothing ingested yet" in output(console)


def test_cmd_contracts_tabulates_every_cached_contract(monkeypatch, base_args, console) -> None:
    entry = MagicMock(rows=132454, last_timestamp="2024-03-17T14:55:00+00:00")
    monkeypatch.setattr(cli.ingest, "load_manifest", MagicMock(return_value={"MNQ 03-24": entry}))

    assert cli._cmd_contracts(base_args) == 0
    text = output(console)
    assert "contract" in text
    # Thousands separators are the point of the column; a bare 132454 is unreadable.
    assert "132,454" in text
    assert "2024-03-17T14:55:00+00:00" in text


# --- splice ------------------------------------------------------------------


def splice_args(base_args, diagnostics: bool):
    base_args.root = "MNQ"
    base_args.back_adjust = False
    base_args.confirm_sessions = 1
    base_args.strict = False
    base_args.diagnostics = diagnostics

    return base_args


def spliced(monkeypatch, early_rolls, rolls=()):
    series = pd.DataFrame(
        {"close": [1.0, 2.0]},
        index=pd.to_datetime(["2024-03-01", "2024-03-02"], utc=True),
    )
    report = MagicMock(early_rolls=list(early_rolls), rolls=list(rolls))
    report.summary.return_value = "MNQ continuous series (raw prices)"
    monkeypatch.setattr(cli.splice, "splice_root", MagicMock(return_value=(series, report)))

    return series


def test_cmd_splice_reports_the_series_it_wrote(monkeypatch, base_args, console) -> None:
    spliced(monkeypatch, early_rolls=[])
    assert cli._cmd_splice(splice_args(base_args, diagnostics=False)) == 0

    text = output(console)
    assert "MNQ continuous series (raw prices)" in text
    assert "2 bars" in text
    assert "written to" in text


def test_cmd_splice_prints_the_volume_tables_under_diagnostics(monkeypatch, base_args, console) -> None:
    roll = MagicMock(notes=["rolled at the coverage boundary"])
    roll.front.nt8_name = "MNQ 03-24"
    roll.back.nt8_name = "MNQ 06-24"
    roll.diagnostics.to_string.return_value = "  day  front_volume  back_volume"
    spliced(monkeypatch, early_rolls=[roll], rolls=[roll])

    assert cli._cmd_splice(splice_args(base_args, diagnostics=True)) == 2

    text = output(console)
    assert "--- MNQ 03-24 -> MNQ 06-24 ---" in text
    assert "front_volume" in text
    assert "note: rolled at the coverage boundary" in text


def test_cmd_splice_stays_quiet_about_rolls_without_diagnostics(monkeypatch, base_args, console) -> None:
    roll = MagicMock(notes=["rolled at the coverage boundary"])
    spliced(monkeypatch, early_rolls=[], rolls=[roll])

    cli._cmd_splice(splice_args(base_args, diagnostics=False))
    assert "note:" not in output(console)


# --- run ---------------------------------------------------------------------


def run_args(base_args, **overrides):
    base_args.root = "MNQ"
    base_args.ema = 21
    base_args.slow_sma = 175
    base_args.fast_sma = 60
    base_args.ema_kind = "ema"
    base_args.slow_sma_kind = "sma"
    base_args.fast_sma_kind = "sma"
    base_args.quantity = 4
    base_args.commission = 0.0
    base_args.slippage = 0.0
    base_args.back_adjust = False
    base_args.start = None
    base_args.end = None
    base_args.trades = None
    base_args.explain = None
    base_args.explain_out = "explain_out.csv"
    base_args.ratchet_out = "ratchet_out.csv"
    for name, value in overrides.items():
        setattr(base_args, name, value)

    return base_args


@pytest.fixture
def stub_run(monkeypatch):
    """Stub everything ``_cmd_run`` calls; these tests are about what it reports."""
    bars = pd.DataFrame(
        {"close": [1.0, 2.0]},
        index=pd.to_datetime(["2024-01-02", "2024-03-01"], utc=True),
    )
    monkeypatch.setattr(cli.splice, "load_continuous", MagicMock(return_value=bars))
    monkeypatch.setattr("nqbt.instruments.get_instrument", MagicMock())
    monkeypatch.setattr("nqbt.context.prepare", MagicMock())

    return bars


def trade_log() -> pd.DataFrame:
    """A two-leg winner and a one-leg loser, carrying every column ``summarise`` reads.

    The figures are deliberately all different from each other -- net $15.00, drawdown
    $25.00, expectancy $7.50, profit factor 1.600. They were not: net P&L and max drawdown
    were both $20.00, so the drawdown assertion passed against the net P&L line.
    """
    return pd.DataFrame(
        {
            "trade_id": [1, 1, 2],
            "net_pnl": [30.0, 10.0, -25.0],
            "commission": [1.5, 1.5, 1.5],
            "bars_held": [4, 9, 3],
            "mae_points": [2.0, 2.0, 5.0],
            "mfe_points": [8.0, 12.0, 1.0],
            "r_multiple": [1.5, 0.5, -1.0],
            "ambiguous_bar": [False, False, True],
            "exit_reason": ["target", "target", "stop"],
            "entry_time": pd.to_datetime(["2024-01-02 15:00"] * 3, utc=True),
            "exit_time": pd.to_datetime(["2024-01-02 15:04", "2024-01-02 15:09", "2024-01-03 15:03"], utc=True),
        }
    )


def test_cmd_run_says_so_when_there_are_no_trades(monkeypatch, base_args, stub_run, console) -> None:
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=pd.DataFrame()))
    explain = MagicMock()
    monkeypatch.setattr("nqbt.sim.explain.explain_trades", explain)

    assert cli._cmd_run(run_args(base_args)) == 0
    assert "no trades" in output(console)
    explain.assert_not_called()


def test_cmd_run_builds_a_grid_for_every_gate_when_two_of_them_share_a_kind(
    monkeypatch,
    base_args,
    stub_run,
    console,
) -> None:
    """The stock gates are ema/sma/sma, so a spec keyed by kind loses the fast SMA entirely.

    ``use_fast_sma`` is on by default, so the loss is not silent at run time -- the signal
    raises reading a grid ``prepare`` was never asked to build.
    """
    prepare = MagicMock()
    monkeypatch.setattr("nqbt.context.prepare", prepare)
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=pd.DataFrame()))

    assert cli._cmd_run(run_args(base_args)) == 0

    spec = prepare.call_args.args[1]
    assert spec.ma_keys == conditions.ma_keys(ema=(21,), sma=(60, 175))


def test_cmd_run_asks_for_the_kind_each_gate_was_given(
    monkeypatch,
    base_args,
    stub_run,
    console,
) -> None:
    prepare = MagicMock()
    monkeypatch.setattr("nqbt.context.prepare", prepare)
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=pd.DataFrame()))

    assert cli._cmd_run(run_args(base_args, fast_sma_kind="wma", ema_kind="hma")) == 0

    spec = prepare.call_args.args[1]
    assert spec.ma_keys == conditions.ma_keys(hma=(21,), wma=(60,), sma=(175,))


@pytest.mark.parametrize(("explain", "kept"), [(None, False), (20, True)])
def test_cmd_run_keeps_the_indicator_values_exactly_when_explain_asked_for_them(
    monkeypatch,
    base_args,
    stub_run,
    explain,
    kept,
) -> None:
    """``explain_trades`` raises without them, so this coupling is what makes --explain work.

    Both halves of it are stubbed in the tests that read the audit trail, which is what let
    ``keep_ma_values`` be set to a constant without a test failing -- and ``nqbt run
    --explain`` would then have died on the ValueError ``explain_trades`` raises.
    """
    prepare = MagicMock()
    monkeypatch.setattr("nqbt.context.prepare", prepare)
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=pd.DataFrame()))

    assert cli._cmd_run(run_args(base_args, explain=explain)) == 0
    assert prepare.call_args.kwargs["keep_ma_values"] is kept


def test_cmd_run_reports_the_statistics_it_computed(monkeypatch, base_args, stub_run, console) -> None:
    """The profit factor and drawdown were computed and dropped on the floor once."""
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=trade_log()))

    assert cli._cmd_run(run_args(base_args)) == 0

    text = output(console)
    assert "MNQ 2024-01-02 -> 2024-03-01  2 bars" in text
    assert "params        EMA(21), SMA(60)/SMA(175)" in text
    assert "trades        2  (3 leg exits)" in text  # a two-leg winner and a one-leg loser
    assert "profit factor 1.600" in text  # +40 against -25
    assert "net P&L       $15.00" in text
    assert "expectancy    $7.50 / trade" in text
    assert "max drawdown  $25.00" in text
    assert "win rate      50.00%" in text
    assert "mean R        +0.333" in text
    assert "ambiguous     33.33% of leg exits" in text
    assert "exit reasons  target 2, stop 1" in text


def test_cmd_run_reports_an_infinite_profit_factor_rather_than_dividing_by_zero(
    monkeypatch, base_args, stub_run, console
) -> None:
    winners = trade_log().assign(net_pnl=[30.0, 10.0, 20.0])
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=winners))

    assert cli._cmd_run(run_args(base_args)) == 0
    assert "profit factor inf" in output(console)


def test_cmd_run_reports_the_profit_factor_stats_defines_when_nothing_won_or_lost(
    monkeypatch, base_args, stub_run, console
) -> None:
    """Scratches only. Two definitions disagreed here, and ``stats._ratio``'s is the one."""
    scratches = trade_log().assign(net_pnl=[0.0, 0.0, 0.0])
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=scratches))

    assert cli._cmd_run(run_args(base_args)) == 0
    assert stats.summarise(scratches).profit_factor == 0.0
    assert "profit factor 0.000" in output(console)


def test_cmd_run_names_every_file_it_wrote(monkeypatch, base_args, stub_run, console, tmp_path) -> None:
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=trade_log()))
    detail = pd.DataFrame({"trade_id": [1, 2]})
    monkeypatch.setattr("nqbt.sim.explain.explain_trades", MagicMock(return_value=detail))
    monkeypatch.setattr("nqbt.sim.explain.ratchet_history", MagicMock(return_value=pd.DataFrame({"bar": [1]})))

    args = run_args(
        base_args,
        trades=str(tmp_path / "trades.csv"),
        explain=20,
        explain_out=str(tmp_path / "explain.csv"),
        ratchet_out=str(tmp_path / "ratchet.csv"),
    )
    assert cli._cmd_run(args) == 0

    # Written for real, not asserted through a patched to_csv.
    assert (tmp_path / "trades.csv").exists()
    assert (tmp_path / "explain.csv").exists()
    assert (tmp_path / "ratchet.csv").exists()

    text = output(console)
    assert "trade log -> " in text
    assert "hand-check detail for 2 trades -> " in text
    assert "ratchet history for trade 1 -> " in text


# --- parser ------------------------------------------------------------------


def test_the_parser_builds_paths_rather_than_strings() -> None:
    args = cli.build_parser().parse_args(["--cache-dir", "somewhere", "contracts"])
    assert isinstance(args.cache_dir, Path)


def test_every_subcommand_is_wired_to_a_handler() -> None:
    parser = cli.build_parser()
    for command in ("ingest", "contracts", "splice", "run"):
        assert callable(parser.parse_args([command]).func)
