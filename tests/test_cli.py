import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from nqbt import cli, ingest, splice


@pytest.fixture
def base_args():
    """Provides a baseline Namespace with common arguments."""
    return argparse.Namespace(
        data_dir=Path("/mock/data"),
        cache_dir=Path("/mock/cache"),
    )


# --- Error Handling Tests ---


def test_main_catches_expected_errors_and_returns_1(monkeypatch) -> None:
    """The CLI entry point must catch specific known exceptions and exit gracefully[cite: 6]."""
    mock_parser = MagicMock()
    mock_args = argparse.Namespace(func=MagicMock(side_effect=FileNotFoundError))
    mock_parser.parse_args.return_value = mock_args

    monkeypatch.setattr(cli, "build_parser", MagicMock(return_value=mock_parser))

    assert cli.main(["dummy_arg"]) == 1

    # Also test SpliceError
    mock_args.func.side_effect = splice.SpliceError
    assert cli.main(["dummy_arg"]) == 1

    # Also test IngestError
    mock_args.func.side_effect = ingest.IngestError
    assert cli.main(["dummy_arg"]) == 1


# --- Ingest Command Tests ---


def test_cmd_ingest_successful_run(monkeypatch, base_args) -> None:
    """Verifies that _cmd_ingest processes merges and results correctly and returns 0[cite: 6]."""
    base_args.root = "MNQ"
    base_args.force = False

    mock_merge = MagicMock(added=True, revised=False)
    mock_result = MagicMock(warnings=["Warning 1"], rows_total=100)
    mock_ingest_all = MagicMock(return_value=([mock_merge], [mock_result]))

    monkeypatch.setattr(cli.ingest, "ingest_all", mock_ingest_all)

    exit_code = cli._cmd_ingest(base_args)

    assert exit_code == 0
    mock_ingest_all.assert_called_once_with(
        data_dir=base_args.data_dir,
        cache_dir=base_args.cache_dir,
        root="MNQ",
        force=False,
    )


# --- Contracts Command Tests ---


def test_cmd_contracts_returns_1_if_no_manifest(monkeypatch, base_args) -> None:
    """If the manifest is missing, the contracts command should exit with 1[cite: 6]."""
    monkeypatch.setattr(cli.ingest, "load_manifest", MagicMock(return_value=None))
    assert cli._cmd_contracts(base_args) == 1


def test_cmd_contracts_returns_0_if_manifest_exists(monkeypatch, base_args) -> None:
    """If the manifest exists, it iterates over it and exits with 0[cite: 6]."""
    monkeypatch.setattr(cli.ingest, "load_manifest", MagicMock(return_value={"MNQ 03-24": "data"}))
    assert cli._cmd_contracts(base_args) == 0


# --- Splice Command Tests ---


def test_cmd_splice_returns_0_on_healthy_rolls(monkeypatch, base_args) -> None:
    """A normal splice without early rolls exits with 0[cite: 6]."""
    base_args.root = "MNQ"
    base_args.back_adjust = False
    base_args.confirm_sessions = 1
    base_args.strict = False
    base_args.diagnostics = False

    mock_report = MagicMock(early_rolls=[])
    monkeypatch.setattr(cli.splice, "splice_root", MagicMock(return_value=(MagicMock(), mock_report)))

    assert cli._cmd_splice(base_args) == 0


def test_cmd_splice_returns_2_on_early_rolls(monkeypatch, base_args) -> None:
    """If the splicer identifies early rolls, it should flag this with exit code 2[cite: 6]."""
    base_args.root = "MNQ"
    base_args.back_adjust = False
    base_args.confirm_sessions = 1
    base_args.strict = False
    base_args.diagnostics = True

    mock_roll = MagicMock(notes=["Note 1"])
    mock_report = MagicMock(early_rolls=[mock_roll], rolls=[mock_roll])
    monkeypatch.setattr(cli.splice, "splice_root", MagicMock(return_value=(MagicMock(), mock_report)))

    assert cli._cmd_splice(base_args) == 2


# --- Run Command Tests ---


def test_cmd_run_empty_trades_exits_early(monkeypatch, base_args) -> None:
    """If the simulation produces no trades, it exits 0 without calculating equity[cite: 6]."""
    base_args.root = "MNQ"
    base_args.ema = 21
    base_args.slow_sma = 175
    base_args.fast_sma = 60
    base_args.quantity = 4
    base_args.commission = 0.0
    base_args.slippage = 0.0
    base_args.back_adjust = False
    base_args.start = None
    base_args.end = None
    base_args.explain = False
    base_args.trades = None

    # Patch the underlying modules directly since _cmd_run imports them locally during execution[cite: 6].
    monkeypatch.setattr(cli.splice, "load_continuous", MagicMock())
    monkeypatch.setattr("nqbt.instruments.get_instrument", MagicMock())
    monkeypatch.setattr("nqbt.context.prepare", MagicMock())

    mock_run = MagicMock(return_value=pd.DataFrame())
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", mock_run)

    mock_explain = MagicMock()
    monkeypatch.setattr("nqbt.sim.explain.explain_trades", mock_explain)

    assert cli._cmd_run(base_args) == 0
    # Calculations and explanations shouldn't be reached
    mock_explain.assert_not_called()


def test_cmd_run_writes_files_when_args_provided(monkeypatch, base_args) -> None:
    """Ensures CSV output files are written when --trades and --explain are passed[cite: 6]."""
    base_args.root = "MNQ"
    base_args.ema = 21
    base_args.slow_sma = 175
    base_args.fast_sma = 60
    base_args.quantity = 4
    base_args.commission = 0.0
    base_args.slippage = 0.0
    base_args.back_adjust = False
    base_args.start = None
    base_args.end = None
    base_args.trades = "trades_out.csv"
    base_args.explain = 20
    base_args.explain_out = "explain_out.csv"
    base_args.ratchet_out = "ratchet_out.csv"

    monkeypatch.setattr(cli.splice, "load_continuous", MagicMock())
    monkeypatch.setattr("nqbt.instruments.get_instrument", MagicMock())
    monkeypatch.setattr("nqbt.context.prepare", MagicMock())

    # Provide a minimal populated dataframe so pandas equity logic executes
    dummy_trades = pd.DataFrame({"trade_id": [1, 2], "net_pnl": [10.0, -5.0]})
    monkeypatch.setattr("nqbt.sim.runner.run_deadcat", MagicMock(return_value=dummy_trades))

    mock_detail_df = MagicMock()
    monkeypatch.setattr("nqbt.sim.explain.explain_trades", MagicMock(return_value=mock_detail_df))

    mock_ratchet_df = MagicMock()
    monkeypatch.setattr("nqbt.sim.explain.ratchet_history", MagicMock(return_value=mock_ratchet_df))

    # Intercept the trades dataframe to_csv call via mocking pandas itself
    mock_to_csv = MagicMock()
    monkeypatch.setattr(pd.DataFrame, "to_csv", mock_to_csv)

    assert cli._cmd_run(base_args) == 0

    # Assert all file writing methods were triggered[cite: 6]
    mock_to_csv.assert_any_call("trades_out.csv", index=False)
    mock_detail_df.to_csv.assert_called_once_with("explain_out.csv", index=False)
    mock_ratchet_df.to_csv.assert_called_once_with("ratchet_out.csv", index=False)
