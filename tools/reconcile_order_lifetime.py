"""Read a ``NqbtOrderLifetimeProbe`` run and answer the order-lifetime questions from it.

    ./.venv/Scripts/python.exe tools/reconcile_order_lifetime.py <..._events.csv>

The companion ``_bars.csv`` and ``_config.csv`` are found beside it. Each measurement is
reported separately, and one that the run carries no data for is reported as such rather than
silently passing -- a scenario answers some of these and not others.

**Nothing here assumes the callback lag; every run re-measures it.** A probe callback reports
``CurrentBar``, which for an order resolved against the *next* bar's prices is one behind the
bar it filled on, because Strategy Analyzer processes those fills before calling
``OnBarUpdate`` for that bar. The session-close exit does not lag, filling at the reported
bar's own close. Reading one rule as the other moves every conclusion by a bar, so both are
checked against price before anything else is reported.

Findings and the evidence: ``docs/nt8-fidelity.md``, "Order lifetime and the session edge".
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nqbt import logsetup

logger = logging.getLogger(__name__)

EXPECTED_ARGV = 2

PROBE_SIGNALS = ("probe1", "probe2")
SESSION_CLOSE_EXIT = "Exit on session close"

SUBMIT = "SUBMIT"
CANCEL_REQUEST = "CANCEL_REQUEST"
ORDER_UPDATE = "ORDER_UPDATE"
EXECUTION = "EXECUTION"

CALLBACK_KINDS = (ORDER_UPDATE, EXECUTION)
"""Rows carrying the lag. SUBMIT and CANCEL_REQUEST come from ``OnBarUpdate`` and do not."""

TERMINAL_STATES = ("Filled", "Cancelled", "Rejected")


@dataclass(frozen=True, slots=True)
class Run:
    """One probe run: its event log, the bars it recorded, and its effective settings."""

    stem: str
    events: pd.DataFrame
    bars: pd.DataFrame
    config: pd.DataFrame | None


def read_run(events_path: Path) -> Run:
    """Load a run from its ``_events.csv``, pulling the two companions in beside it."""
    name = events_path.name
    if not name.endswith("_events.csv"):
        msg = f"expected a probe _events.csv, got {name}"
        raise ValueError(msg)

    bars_path = events_path.with_name(name.replace("_events.csv", "_bars.csv"))
    if not bars_path.exists():
        msg = f"no bar export beside {name}; expected {bars_path.name}"
        raise FileNotFoundError(msg)

    config_path = events_path.with_name(name.replace("_events.csv", "_config.csv"))
    config = None
    if config_path.exists():
        config = pd.read_csv(config_path, sep=";")

    events = pd.read_csv(events_path, sep=";", float_precision="round_trip", low_memory=False)
    bars = pd.read_csv(bars_path, sep=";", float_precision="round_trip").set_index("bar")
    return Run(stem=name[: -len("_events.csv")], events=events, bars=bars, config=config)


def entry_fills(run: Run) -> pd.DataFrame:
    """Execution rows for the probe's own entry orders, which are the price-triggered ones."""
    events = run.events
    return events[(events["kind"] == EXECUTION) & events["signal_name"].isin(PROBE_SIGNALS)]


def reaches(bar: pd.Series, trigger: float, action: str) -> bool:
    """Whether a bar's range reaches a stop trigger, on the side the order sits."""
    if action == "Buy":
        return bool(bar["high"] >= trigger)
    return bool(bar["low"] <= trigger)


def measure_entry_lag(run: Run) -> dict[str, int]:
    """How many entry fills the reported bar explains, against the bar after it.

    The discriminator is price: a stop fills only on a bar whose range reaches the trigger, so
    whichever candidate explains every fill is the bar the callback was really reporting on.
    """
    counts = {"fills": 0, "reported": 0, "reported_plus_one": 0, "unresolved": 0}
    for _, fill in entry_fills(run).iterrows():
        counts["fills"] += 1
        resolved = False
        for offset, key in ((0, "reported"), (1, "reported_plus_one")):
            bar = fill["bar"] + offset
            if bar not in run.bars.index:
                continue
            resolved = True
            if reaches(run.bars.loc[bar], fill["stop_price"], fill["order_action"]):
                counts[key] += 1
        if not resolved:
            counts["unresolved"] += 1
    return counts


def measure_session_close_exit_lag(run: Run) -> dict[str, int]:
    """Whether the session-close exit fills at the reported bar's own close.

    Separate from :func:`measure_entry_lag` because it is a different mechanism: NinjaTrader
    generates this exit from a bar close rather than resolving it against the next bar.
    """
    events = run.events
    exits = events[(events["kind"] == EXECUTION) & (events["signal_name"] == SESSION_CLOSE_EXIT)]
    counts = {"exits": 0, "at_reported_close": 0, "inside_reported": 0, "unresolved": 0}
    for _, row in exits.iterrows():
        counts["exits"] += 1
        if row["bar"] not in run.bars.index:
            counts["unresolved"] += 1
            continue
        bar = run.bars.loc[row["bar"]]
        price = row["average_fill_price"]
        counts["at_reported_close"] += int(price == bar["close"])
        counts["inside_reported"] += int(bar["low"] <= price <= bar["high"])
    return counts


def lifetimes(run: Run, signal: str, lag: int = 1) -> pd.DataFrame:
    """One row per trial: the submit bar, and the corrected bar each terminal state landed on."""
    rows = run.events[run.events["signal_name"] == signal]
    submits = rows[rows["kind"] == SUBMIT].groupby("trial")["bar"].min()
    out = pd.DataFrame({"submit_bar": submits})

    updates = rows[rows["kind"] == ORDER_UPDATE].copy()
    updates["corrected"] = updates["bar"] + lag
    for state in TERMINAL_STATES:
        hit = updates[updates["order_state"] == state]
        out[state.lower()] = hit.groupby("trial")["corrected"].min()

    reached = updates[updates["order_state"] == "Working"]
    out["acknowledged"] = out.index.isin(reached["trial"])

    requests = rows[rows["kind"] == CANCEL_REQUEST].groupby("trial")["bar"].min()
    out["cancel_requested"] = requests
    return out


MAX_DISTINCT_OFFSETS = 8
"""Above this an offset distribution is summarised. A hundred-key dict reports nothing."""


def offsets_from_submit(frame: pd.DataFrame, column: str) -> dict[int, int]:
    """Distribution of ``column`` measured in bars after the submit bar."""
    delta = (frame[column] - frame["submit_bar"]).dropna()
    if delta.empty:
        return {}
    return {int(k): int(v) for k, v in delta.astype(int).value_counts().sort_index().items()}


def describe_offsets(frame: pd.DataFrame, column: str) -> str:
    """The distribution where it is short enough to read, its shape where it is not.

    A one-bar lifetime is the whole finding for a three-argument entry, so the exact
    distribution matters; an until-cancelled order spreads over hundreds of values and only its
    range says anything.
    """
    counts = offsets_from_submit(frame, column)
    if not counts:
        return "none"
    if len(counts) <= MAX_DISTINCT_OFFSETS:
        return str(counts)

    delta = (frame[column] - frame["submit_bar"]).dropna()
    return (
        f"{int(delta.size)} over {len(counts)} distinct offsets, "
        f"min {int(delta.min())} median {int(delta.median())} max {int(delta.max())}"
    )


def last_bar_fills(run: Run, lag: int = 1) -> dict[str, int]:
    """Entry fills landing on a bar the probe recorded as the session's last.

    Uses NinjaTrader's own ``Bars.IsLastBarOfSession``, carried on every event row, rather than
    a session calendar -- the question is what NinjaTrader did on the bar *it* considers last.
    """
    events = run.events
    if "is_last_bar_of_session" not in events.columns:
        return {}

    flagged = events[events["is_last_bar_of_session"] == 1]
    last_bars = set(flagged["bar"].unique())
    if not last_bars:
        return {}

    fills = entry_fills(run)
    corrected = fills["bar"] + lag
    submits = events[(events["kind"] == SUBMIT) & events["signal_name"].isin(PROBE_SIGNALS)]
    return {
        "bars_flagged_last": len(last_bars),
        "entry_fills": len(fills),
        "fills_on_a_last_bar": int(corrected.isin(last_bars).sum()),
        "submits_on_a_last_bar": int(submits["bar"].isin(last_bars).sum()),
    }


def refused_submissions(run: Run) -> dict[str, int]:
    """Submissions NinjaTrader never acknowledged, per signal name.

    An ``Enter()`` the internal order-handling rules drop leaves a SUBMIT row with no order
    update behind it, which is how "refused the submission" is told from "cancelled the order".
    """
    events = run.events
    out: dict[str, int] = {}
    for signal in PROBE_SIGNALS:
        rows = events[events["signal_name"] == signal]
        submits = rows[rows["kind"] == SUBMIT]
        if submits.empty:
            continue
        acknowledged = rows[rows["kind"] == ORDER_UPDATE]["trial"].unique()
        out[signal] = int((~submits["trial"].isin(acknowledged)).sum())
    return out


def fills_after_cancel(run: Run, lag: int = 1) -> dict[str, int]:
    """Whether any order filled on or after the bar whose close issued its cancel."""
    frame = lifetimes(run, "probe1", lag)
    both = frame.dropna(subset=["filled", "cancel_requested"])
    return {
        "cancel_requested": int(frame["cancel_requested"].notna().sum()),
        "filled_on_the_request_bar": int((both["filled"] == both["cancel_requested"]).sum()),
        "filled_after_the_request_bar": int((both["filled"] > both["cancel_requested"]).sum()),
    }


def report(run: Run) -> bool:
    """Print every measurement the run supports. False if the lag checks did not resolve."""
    logger.info("run: %s", run.stem)
    if run.config is not None and not run.config.empty:
        effective = run.config.iloc[-1]
        logger.info(
            "  effective: exit_on_session_close=%s seconds=%s entries_per_direction=%s fill=%s",
            effective["is_exit_on_session_close_strategy"],
            effective["exit_on_session_close_seconds"],
            effective["entries_per_direction"],
            effective["order_fill_resolution"],
        )

    entry = measure_entry_lag(run)
    logger.info("callback lag on entry fills: %s", entry)
    consistent = entry["fills"] == 0 or (
        entry["reported_plus_one"] == entry["fills"] and entry["reported"] == 0
    )
    if not consistent:
        logger.warning("  entry-fill lag is NOT a clean +1 in this run; every bar below is suspect")

    exits = measure_session_close_exit_lag(run)
    if exits["exits"]:
        logger.info("session-close exit: %s", exits)

    for signal in PROBE_SIGNALS:
        frame = lifetimes(run, signal)
        if frame.empty:
            continue
        logger.info(
            "%s: %d trials, acknowledged %d, filled at submit+%s, cancelled at submit+%s",
            signal,
            len(frame),
            int(frame["acknowledged"].sum()),
            describe_offsets(frame, "filled"),
            describe_offsets(frame, "cancelled"),
        )

    refused = refused_submissions(run)
    if refused:
        logger.info("submissions never acknowledged: %s", refused)

    cancels = fills_after_cancel(run)
    if cancels["cancel_requested"]:
        logger.info("explicit cancels: %s", cancels)

    edge = last_bar_fills(run)
    if edge:
        logger.info("session edge: %s", edge)

    return consistent


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    if len(argv) != EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2
    return 0 if report(read_run(Path(argv[1]))) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
