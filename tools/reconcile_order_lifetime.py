"""Read a ``NqbtOrderLifetimeProbe`` run and answer the order-lifetime questions from it.

    uv run tools/reconcile_order_lifetime.py <..._events.csv>

The companion ``_bars.csv`` and ``_config.csv`` are found beside it.
``tools/README.md`` § "reconcile_order_lifetime.py".
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt import logsetup

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray

logger = logging.getLogger(__name__)

EXPECTED_ARGV = 2

PROBE_SIGNALS = ("probe1", "probe2")
SESSION_CLOSE_EXIT = "Exit on session close"

EXIT_LONG = "Sell"
"""NinjaTrader's name for an ``ExitLong()`` order, which scenario 7's SUBMIT row carries too."""

CLOSE_POSITION = "Close position"
"""The order NinjaTrader adds itself when an entry reverses an open position."""

SECOND_ENTRY = "probe2"
"""Scenario 7's entry beside the exit."""

PAIR_SIDES = {"Buy": "same side", "SellShort": "other side"}
"""Scenario 7's second entry, by its action, against the long it is sent beside."""

UNKNOWN_SIDE = "unknown side"
"""A pair whose second entry is missing, or carries an action :data:`PAIR_SIDES` does not name."""

MARKET = "Market"

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

    events = pd.read_csv(events_path, sep=";", low_memory=False)
    bars = pd.read_csv(bars_path, sep=";").set_index("bar")

    return Run(stem=name[: -len("_events.csv")], events=events, bars=bars, config=config)


def entry_fills(run: Run) -> pd.DataFrame:
    """Select the execution rows for the probe's own entry orders, stop and market alike."""
    events = run.events

    return events[(events["kind"] == EXECUTION) & events["signal_name"].isin(PROBE_SIGNALS)]


def reaches(bar: pd.Series[float], trigger: float, action: str) -> bool:
    """Return whether a bar's range reaches a stop trigger, on the side the order sits."""
    if action == "Buy":
        return bool(bar["high"] >= trigger)

    return bool(bar["low"] <= trigger)


def measure_entry_lag(run: Run) -> dict[str, int]:
    """Count how many stop entry fills the reported bar explains, against the bar after it.

    The discriminator is price: a stop fills only on a bar whose range reaches the trigger, so
    whichever candidate explains every fill is the bar the callback was really reporting on.
    """
    fills = entry_fills(run)
    counts = {"fills": 0, "reported": 0, "reported_plus_one": 0, "unresolved": 0}
    for _, fill in fills[fills["order_type"] != MARKET].iterrows():
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
    """Measure whether the session-close exit fills at the reported bar's own close.

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


def stop_lag_is_clean(counts: dict[str, int]) -> bool:
    """Return whether every stop entry fill says the callback lags one bar, or there is none."""
    return counts["fills"] == 0 or (
        counts["reported_plus_one"] == counts["fills"] and counts["reported"] == 0
    )


def count_fills_at_opens(fills: pd.DataFrame, bars: pd.DataFrame, price_column: str) -> dict[str, int]:
    """Count market fills at the reported bar's open, against the next bar's.

    ``tools/README.md`` § "reconcile_order_lifetime.py".
    """
    opens = bars["open"]
    price: FloatArray = fills[price_column].to_numpy(dtype=np.float64)
    at_reported: BoolArray = opens.reindex(fills["bar"]).to_numpy(dtype=np.float64) == price
    at_next: BoolArray = opens.reindex(fills["bar"] + 1).to_numpy(dtype=np.float64) == price

    return {
        "fills": len(fills),
        "reported": int((at_reported & ~at_next).sum()),
        "reported_plus_one": int((at_next & ~at_reported).sum()),
        "both": int((at_reported & at_next).sum()),
        "neither": int((~at_reported & ~at_next).sum()),
    }


def lag_is_clean(counts: dict[str, int]) -> bool:
    """Return whether every market fill that decides anything says the callback lags one bar."""
    return counts["reported_plus_one"] > 0 and counts["reported"] == 0 and counts["neither"] == 0


def measure_market_entry_lag(run: Run) -> dict[str, int]:
    """Count the probe's market entry fills at the reported bar's open, against the next bar's."""
    fills = entry_fills(run)

    return count_fills_at_opens(fills[fills["order_type"] == MARKET], run.bars, "average_fill_price")


def exit_and_entry_pairs(run: Run, lag: int = 1) -> pd.DataFrame:
    """Return one row per scenario 7 pair: its side, what NinjaTrader did with it, and the position after.

    The pair goes in at ``pair_bar``'s close and fills at the next bar's open, so ``fill_bar`` is
    that bar and its bar row holds the position the fills left. ``lag`` corrects the execution
    rows' bars as :func:`lifetimes` does. ``tools/README.md`` § "reconcile_order_lifetime.py".
    """
    events = run.events
    submits = events[events["kind"] == SUBMIT]
    exits = submits[submits["signal_name"] == EXIT_LONG].drop_duplicates("trial").set_index("trial")
    entries = submits[submits["signal_name"] == SECOND_ENTRY].drop_duplicates("trial").set_index("trial")
    pairs = pd.DataFrame({"pair_bar": exits["bar"]})
    pairs["fill_bar"] = pairs["pair_bar"] + 1
    pairs["side"] = entries["order_action"].map(PAIR_SIDES).reindex(pairs.index).fillna(UNKNOWN_SIDE)
    acknowledged = lifetimes(run, SECOND_ENTRY, lag)["acknowledged"]
    pairs["acknowledged"] = acknowledged.reindex(pairs.index).fillna(value=False).astype(bool)

    updates = events[(events["kind"] == ORDER_UPDATE) & (events["signal_name"] == CLOSE_POSITION)]
    on_pair_bar = updates.merge(pairs[["pair_bar"]].reset_index().rename(columns={"pair_bar": "bar"}))
    pairs["close_position_sent"] = pairs.index.isin(on_pair_bar["trial"])

    executions = events[(events["kind"] == EXECUTION) & (events["signal_name"] != SESSION_CLOSE_EXIT)]
    executions = executions.assign(fill_bar=executions["bar"] + lag)
    at_fill = executions.merge(pairs[["fill_bar"]].reset_index(), on=["trial", "fill_bar"])
    open_at_fill: FloatArray = run.bars["open"].reindex(at_fill["fill_bar"]).to_numpy(dtype=np.float64)
    at_fill = at_fill.assign(at_open=at_fill["average_fill_price"].to_numpy(dtype=np.float64) == open_at_fill)
    by_trial = at_fill.sort_values("signal_name").groupby("trial")
    pairs["filled"] = by_trial["signal_name"].agg("+".join).reindex(pairs.index).fillna("none")
    pairs["all_at_open"] = by_trial["at_open"].all().reindex(pairs.index).fillna(value=False).astype(bool)
    pairs["close_position_filled"] = pairs.index.isin(
        at_fill.loc[at_fill["signal_name"] == CLOSE_POSITION, "trial"]
    )

    bars = run.bars.reindex(pairs["fill_bar"])
    pairs["recorded"] = pairs["fill_bar"].isin(run.bars.index).to_numpy()
    quantity = bars["position_quantity"].astype("Int64").astype(str)
    pairs["position"] = (bars["market_position"].astype(str) + " " + quantity).to_numpy()

    return pairs


def close_position_states(run: Run) -> dict[str, int]:
    """Count the rows of NinjaTrader's own ``Close position`` orders by kind and state, over the whole run."""
    rows = run.events[run.events["signal_name"] == CLOSE_POSITION]
    labels = rows["kind"] + " " + rows["order_state"].astype(str)

    return {str(k): int(v) for k, v in labels.value_counts().sort_index().items()}


def pair_outcomes(pairs: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Return scenario 7's outcome counts per side, over the pairs whose fill bar the probe recorded."""
    out: dict[str, dict[str, object]] = {}
    recorded = pairs[pairs["recorded"]]
    for side, group in recorded.groupby("side"):
        out[str(side)] = {
            "pairs": len(group),
            "entry_acknowledged": int(group["acknowledged"].sum()),
            "position_after": {str(k): int(v) for k, v in group["position"].value_counts().items()},
            "filled": {str(k): int(v) for k, v in group["filled"].value_counts().items()},
            "all_fills_at_the_open": int(group["all_at_open"].sum()),
            "close_position_sent": int(group["close_position_sent"].sum()),
            "close_position_filled": int(group["close_position_filled"].sum()),
        }
    unrecorded = int((~pairs["recorded"]).sum())
    if unrecorded:
        out["unrecorded"] = {"pairs": unrecorded}

    return out


def lifetimes(run: Run, signal: str, lag: int = 1) -> pd.DataFrame:
    """Return one row per trial: the submit bar, and the corrected bar each terminal state landed on."""
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
    """Return the distribution of ``column`` measured in bars after the submit bar."""
    delta = (frame[column] - frame["submit_bar"]).dropna()
    if delta.empty:
        return {}

    return {int(k): int(v) for k, v in delta.astype(int).value_counts().sort_index().items()}  # type: ignore[call-overload]  # a value_counts label


def describe_offsets(frame: pd.DataFrame, column: str) -> str:
    """Describe the distribution where it is short enough to read, and its shape where it is not."""
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
    """Count entry fills landing on a bar the probe recorded as the session's last.

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
    """Count submissions NinjaTrader never acknowledged, per signal name.

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
    """Check whether any order filled on or after the bar whose close issued its cancel."""
    frame = lifetimes(run, "probe1", lag)
    both = frame.dropna(subset=["filled", "cancel_requested"])

    return {
        "cancel_requested": int(frame["cancel_requested"].notna().sum()),
        "filled_on_the_request_bar": int((both["filled"] == both["cancel_requested"]).sum()),
        "filled_after_the_request_bar": int((both["filled"] > both["cancel_requested"]).sum()),
    }


def report_entry_lag(run: Run) -> bool:
    """Print the callback lag on the stop and market entry fills. False if either did not resolve."""
    stop = measure_entry_lag(run)
    market = measure_market_entry_lag(run)
    # A run with no entry fills at all still prints the stop line, as it did before market entries.
    if stop["fills"] or not market["fills"]:
        logger.info("callback lag on entry fills: %s", stop)

    if market["fills"]:
        logger.info("callback lag on market entry fills: %s", market)

    consistent = stop_lag_is_clean(stop) and (market["fills"] == 0 or lag_is_clean(market))
    if not consistent:
        logger.warning("  entry-fill lag is NOT a clean +1 in this run; every bar below is suspect")

    return consistent


def report_pairs(run: Run) -> None:
    """Print scenario 7's outcomes per side, and every row of NinjaTrader's own ``Close position`` orders."""
    for side, outcome in pair_outcomes(exit_and_entry_pairs(run)).items():
        logger.info("exit and entry on one bar, %s: %s", side, outcome)

    states = close_position_states(run)
    if states:
        logger.info("Close position order rows over the run: %s", states)


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

    consistent = report_entry_lag(run)

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

    report_pairs(run)

    return consistent


def main(argv: list[str]) -> int:
    """Answer the order-lifetime questions from one run and return the process exit code."""
    logsetup.configure(__name__)
    if len(argv) != EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    return 0 if report(read_run(Path(argv[1]))) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
