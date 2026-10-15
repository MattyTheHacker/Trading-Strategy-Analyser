"""Read a ``NqbtPassedTargetProbe`` run and check where each passed limit order and stop filled.

    uv run tools/reconcile_passed_target.py <..._events.csv>

The companion ``_bars.csv`` and ``_config.csv`` are found beside it.
``tools/README.md`` § "reconcile_passed_target.py".
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import logsetup
from tools.reconcile_order_lifetime import EXECUTION, ORDER_UPDATE, SUBMIT, Run, read_run

if TYPE_CHECKING:
    from collections.abc import Collection

    from nqbt.arrays import BoolArray, FloatArray

logger = logging.getLogger(__name__)

EXPECTED_ARGV = 2

ENTRY_SIDES = {"probeLong": 1.0, "probeShort": -1.0}
"""The probe's two entry signals and the side each trades, +1 long."""

LEG_NAME = rf"^({'|'.join(ENTRY_SIDES)})(\d*)$"
"""A probe entry's name: an entry signal, then the leg's number on every leg after the first."""

PROFIT_TARGET = "Profit target"
"""The name NinjaTrader gives every order ``SetProfitTarget`` places."""

STOP_LOSS = "Stop loss"
"""The name NinjaTrader gives every order ``SetStopLoss`` places."""

PROBE_EXIT = "probeExit"
"""The probe's own market exit."""

TARGET_SET = "TARGET_SET"
STOP_SET = "STOP_SET"
STUCK = "STUCK"
"""The probe's row for an entry NinjaTrader left working past the bar it lives for."""
REJECTED = "Rejected"
MARKET = "Market"
LIMIT = "Limit"
STOP_MARKET = "StopMarket"

ENTRY_GROUPS = {
    "resting": "limit entry a bar trades to (#454)",
    "gapped": "limit entry a bar opens past (#454)",
    "marketable": "limit entry sent marketable (#454)",
}
"""How :func:`limit_entry_fills` splits the limit entries, and what the report calls each."""

STOP_GROUPS = {
    "beyond": "stop the entry filled beyond, on a bar opening past it (#455)",
    "gapped": "stop the entry bar opened past, the entry filling short of it (#455)",
    "control": "stop the entry bar opened at or short of (#455)",
}
"""How :func:`stops_after_entry` splits the stops, and what the report calls each."""


def executions(run: Run, names: Collection[str]) -> pd.DataFrame:
    """Return each trial's first execution of an order named in ``names``, indexed by trial."""
    events = run.events
    rows = events[(events["kind"] == EXECUTION) & events["signal_name"].isin(names)]

    return rows.drop_duplicates("trial").set_index("trial")


def unrecorded_trials(run: Run, lag: int = 1) -> set[int]:
    """Return the trials with an order live on, or filled on, a bar after the last one the probe recorded.

    ``lag`` is read as :func:`trials` reads it -- ``tools/README.md`` § "reconcile_passed_target.py".
    """
    events = run.events
    live = events.loc[events["kind"] == SUBMIT, ["trial", "bar"]].assign(bar=events["bar"] + 1)
    filled = events.loc[events["kind"] == EXECUTION, ["trial", "bar"]].assign(bar=events["bar"] + lag)
    reached = pd.concat([live, filled])

    return {int(trial) for trial in reached.loc[~reached["bar"].isin(run.bars.index), "trial"]}


def market_fills(run: Run) -> pd.DataFrame:
    """Select the execution rows of the probe's own market orders, entries and exits alike."""
    events = run.events
    names = [*ENTRY_SIDES, PROBE_EXIT]

    return events[
        (events["kind"] == EXECUTION) & events["signal_name"].isin(names) & (events["order_type"] == MARKET)
    ]


def measure_lag(run: Run) -> dict[str, int]:
    """Count the market fills at the reported bar's open, against the next bar's.

    A market order fills at an open, so whichever bar's open explains every fill is the bar the
    callback was really reporting on. A fill both opens explain decides nothing.
    """
    fills = market_fills(run)
    opens = run.bars["open"]
    price: FloatArray = fills["execution_price"].to_numpy(dtype=np.float64)
    at_reported: BoolArray = opens.reindex(fills["bar"]).to_numpy(dtype=np.float64) == price
    at_next: BoolArray = opens.reindex(fills["bar"] + 1).to_numpy(dtype=np.float64) == price

    return {
        "fills": len(fills),
        "reported": int((at_reported & ~at_next).sum()),
        "reported_plus_one": int((at_next & ~at_reported).sum()),
        "both": int((at_reported & at_next).sum()),
        "neither": int((~at_reported & ~at_next).sum()),
    }


def measure_lag_on_entries(run: Run) -> dict[str, int]:
    """Count the entry fills inside the reported bar's range, against the next bar's.

    Every fill is at a price its bar traded, so whichever bar's range holds every fill is the bar
    the callback was really reporting on. A fill both ranges hold decides nothing.
    """
    fills = executions(run, ENTRY_SIDES)
    price: FloatArray = fills["execution_price"].to_numpy(dtype=np.float64)

    def inside(offset: int) -> BoolArray:
        at = fills["bar"] + offset
        low: FloatArray = run.bars["low"].reindex(at).to_numpy(dtype=np.float64)
        high: FloatArray = run.bars["high"].reindex(at).to_numpy(dtype=np.float64)

        return (low <= price) & (price <= high)

    at_reported = inside(0)
    at_next = inside(1)

    return {
        "fills": len(fills),
        "reported": int((at_reported & ~at_next).sum()),
        "reported_plus_one": int((at_next & ~at_reported).sum()),
        "both": int((at_reported & at_next).sum()),
        "neither": int((~at_reported & ~at_next).sum()),
    }


def lag_is_clean(counts: dict[str, int]) -> bool:
    """Return whether every fill that decides anything says the callback lags one bar."""
    return counts["reported_plus_one"] > 0 and counts["reported"] == 0 and counts["neither"] == 0


def trials(run: Run, lag: int = 1) -> pd.DataFrame:
    """Return one row per filled entry: its side, its target and where that target filled.

    Bars are the bars the fills happened on, the reported bar plus ``lag``. ``target_at_entry``
    is the price set before the entry was sent, and ``target`` the one in force when it filled.
    """
    events = run.events
    entries = executions(run, ENTRY_SIDES)
    targets = executions(run, [PROFIT_TARGET]).reindex(entries.index)
    target_sets = events[events["kind"] == TARGET_SET]
    rejections = events[
        (events["kind"] == ORDER_UPDATE)
        & (events["signal_name"] == PROFIT_TARGET)
        & (events["order_state"] == REJECTED)
    ]

    frame = pd.DataFrame(index=entries.index)
    frame["entry_signal"] = entries["signal_name"]
    frame["side"] = entries["signal_name"].map(ENTRY_SIDES)
    frame["entry_bar"] = entries["bar"] + lag
    frame["entry_price"] = entries["execution_price"]
    frame["target_at_entry"] = target_sets.groupby("trial")["limit_price"].first().reindex(entries.index)
    frame["target_rejected"] = frame.index.isin(rejections["trial"])
    frame["target_entry_signal"] = targets["from_entry_signal"]
    frame["target"] = targets["limit_price"]
    frame["target_bar"] = targets["bar"] + lag
    frame["target_fill"] = targets["execution_price"]

    return frame


def misattributed_targets(run: Run, frame: pd.DataFrame) -> int:
    """Count the target fills that cannot be tied to the entry their trial number names."""
    orphaned = int((~executions(run, [PROFIT_TARGET]).index.isin(frame.index)).sum())
    filled = frame.dropna(subset=["target_fill"])

    return orphaned + int((filled["target_entry_signal"] != filled["entry_signal"]).sum())


def fill_prices(
    fill: FloatArray, limit: FloatArray, low: FloatArray, high: FloatArray, open_: FloatArray
) -> dict[str, int]:
    """Count limit fills at the limit's own price, at the bar's extreme nearest it, at the open, or elsewhere.

    The first two are the one rule, the limit's price clamped into its fill bar's range --
    ``docs/nt8-fidelity.md``, "A limit order the market has passed fills at the nearest price the
    bar traded". The open is counted apart -- ``tools/README.md`` § "reconcile_passed_target.py".
    """
    follows: BoolArray = fill == np.clip(limit, low, high)
    at_limit: BoolArray = fill == limit
    at_open: BoolArray = ~follows & (fill == open_)

    return {
        "at_limit": int((follows & at_limit).sum()),
        "at_bar_extreme": int((follows & ~at_limit).sum()),
        "at_open": int(at_open.sum()),
        "other": int((~follows & ~at_open).sum()),
    }


def target_fill_prices(filled: pd.DataFrame, bars: pd.DataFrame) -> dict[str, int]:
    """Apply :func:`fill_prices` to rows of :func:`trials` whose target filled."""
    at_bar = filled["target_bar"]

    return fill_prices(
        filled["target_fill"].to_numpy(dtype=np.float64),
        filled["target"].to_numpy(dtype=np.float64),
        bars["low"].reindex(at_bar).to_numpy(dtype=np.float64),
        bars["high"].reindex(at_bar).to_numpy(dtype=np.float64),
        bars["open"].reindex(at_bar).to_numpy(dtype=np.float64),
    )


def passed_at_entry(frame: pd.DataFrame, bars: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Count the targets already behind their entry's fill, and the prices they filled at.

    The prices are split by whether the target filled on the entry bar itself or on a later one.
    """
    passed = frame[frame["side"] * (frame["entry_price"] - frame["target_at_entry"]) > 0]
    filled = passed.dropna(subset=["target_fill"])
    unfilled = passed[passed["target_fill"].isna()]
    bars_after_entry = filled["target_bar"] - filled["entry_bar"]

    return {
        "trials": {
            "entries": len(frame),
            "passed": len(passed),
            "rejected": int(unfilled["target_rejected"].sum()),
            "not_filled": int((~unfilled["target_rejected"]).sum()),
            "filled_before_entry": int((bars_after_entry < 0).sum()),
        },
        "on_entry_bar": target_fill_prices(filled[bars_after_entry == 0], bars),
        "on_a_later_bar": target_fill_prices(filled[bars_after_entry > 0], bars),
    }


def gapped_while_resting(frame: pd.DataFrame, bars: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Count the target fills after the entry bar, split by whether their bar opened beyond the target.

    Only a target the previous bar closed short of is resting. One already behind the market was
    passed, which :func:`passed_at_entry` reads.
    """
    later = frame[frame["target_bar"] > frame["entry_bar"]].dropna(subset=["target_fill"])
    side: FloatArray = later["side"].to_numpy(dtype=np.float64)
    target: FloatArray = later["target"].to_numpy(dtype=np.float64)
    fill: FloatArray = later["target_fill"].to_numpy(dtype=np.float64)
    open_: FloatArray = bars["open"].reindex(later["target_bar"]).to_numpy(dtype=np.float64)
    low: FloatArray = bars["low"].reindex(later["target_bar"]).to_numpy(dtype=np.float64)
    high: FloatArray = bars["high"].reindex(later["target_bar"]).to_numpy(dtype=np.float64)
    previous_close: FloatArray = bars["close"].reindex(later["target_bar"] - 1).to_numpy(dtype=np.float64)
    resting: BoolArray = side * (target - previous_close) > 0
    gapped: BoolArray = resting & (side * (open_ - target) > 0)
    control: BoolArray = resting & ~gapped

    return {
        "gapped": fill_prices(fill[gapped], target[gapped], low[gapped], high[gapped], open_[gapped]),
        "control": fill_prices(fill[control], target[control], low[control], high[control], open_[control]),
    }


def limit_entries(run: Run, lag: int = 1) -> pd.DataFrame:
    """Return one row per limit entry sent: its side, its price, the bar it was live on and its fill.

    ``fill_bar`` is the reported bar plus ``lag``.
    """
    events = run.events
    named = events["signal_name"].isin(ENTRY_SIDES)
    sent = events[(events["kind"] == SUBMIT) & named & (events["order_type"] == LIMIT)]
    sent = sent.drop_duplicates("trial").set_index("trial")
    updates = events[(events["kind"] == ORDER_UPDATE) & named]
    fills = executions(run, ENTRY_SIDES).reindex(sent.index)

    frame = pd.DataFrame(index=sent.index)
    frame["side"] = sent["signal_name"].map(ENTRY_SIDES)
    frame["limit"] = sent["limit_price"]
    frame["live_bar"] = sent["bar"] + 1
    frame["acknowledged"] = frame.index.isin(updates["trial"])
    frame["rejected"] = frame.index.isin(updates.loc[updates["order_state"] == REJECTED, "trial"])
    frame["fill_bar"] = fills["bar"] + lag
    frame["fill"] = fills["execution_price"]

    return frame


def limit_entry_fills(frame: pd.DataFrame, bars: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Count the limit entries by how the bar they were live on met them, and where each filled.

    ``marketable`` were sent at or past the signal bar's close, ``gapped`` met a bar opening past
    the limit, and ``resting`` were left for the bar to trade to. A limit is met by the bar's low
    when it buys and its high when it sells.
    """
    live = frame["live_bar"]
    side: FloatArray = frame["side"].to_numpy(dtype=np.float64)
    limit: FloatArray = frame["limit"].to_numpy(dtype=np.float64)
    fill: FloatArray = frame["fill"].to_numpy(dtype=np.float64)
    sent_close: FloatArray = bars["close"].reindex(live - 1).to_numpy(dtype=np.float64)
    open_: FloatArray = bars["open"].reindex(live).to_numpy(dtype=np.float64)
    low: FloatArray = bars["low"].reindex(live).to_numpy(dtype=np.float64)
    high: FloatArray = bars["high"].reindex(live).to_numpy(dtype=np.float64)
    met_by: FloatArray = np.where(side > 0, low, high)
    filled: BoolArray = ~np.isnan(fill)
    on_live_bar: BoolArray = (frame["fill_bar"] == live).to_numpy()
    acknowledged: BoolArray = frame["acknowledged"].to_numpy(dtype=bool)
    rejected: BoolArray = frame["rejected"].to_numpy(dtype=bool)
    marketable: BoolArray = side * (limit - sent_close) >= 0
    gapped: BoolArray = ~marketable & (side * (open_ - limit) < 0)
    resting: BoolArray = ~marketable & ~gapped
    touched: BoolArray = met_by == limit
    through: BoolArray = side * (limit - met_by) > 0
    working: BoolArray = acknowledged & ~rejected

    def counted(group: BoolArray) -> dict[str, int]:
        read = group & filled & on_live_bar

        return {
            "sent": int(group.sum()),
            "acknowledged": int((group & acknowledged).sum()),
            "rejected": int((group & rejected).sum()),
            "filled": int((group & filled).sum()),
            **fill_prices(fill[read], limit[read], low[read], high[read], open_[read]),
            "through_unfilled": int((group & working & through & ~filled).sum()),
        }

    return {
        "marketable": counted(marketable),
        "gapped": counted(gapped),
        "resting": {
            **counted(resting),
            "touched_filled": int((resting & touched & filled).sum()),
            "touched_unfilled": int((resting & touched & ~filled).sum()),
        },
        "checks": {"filled_off_the_live_bar": int((filled & ~on_live_bar).sum())},
    }


def stuck_entries(run: Run) -> int:
    """Count the entries NinjaTrader left working past the bar they live for, which the probe cancels."""
    return int((run.events["kind"] == STUCK).sum())


def set_stops(run: Run) -> bool:
    """Return whether the run set a stop before any of its entries."""
    return bool((run.events["kind"] == STOP_SET).any())


def entry_legs(events: pd.DataFrame) -> pd.DataFrame:
    """Split each event's order name into its entry signal and leg number, both NaN on any other order."""
    legs = events["signal_name"].str.extract(LEG_NAME)
    legs.columns = pd.Index(["signal", "leg"])
    legs["leg"] = legs["leg"].replace("", "1")

    return legs


def stop_trials(run: Run, lag: int = 1) -> pd.DataFrame:
    """Return one row per filled entry leg that had a stop set: its entry order, its stop and both fills.

    Indexed by trial, which a trial of several legs repeats. Bars are the bars the fills happened
    on, the reported bar plus ``lag``. ``entry_level`` is a stop entry's trigger or a limit
    entry's price, ``stop`` the leg's own stop order's price where it filled, otherwise the one
    the probe set, and ``last_leg`` marks the trial's last entry. Only a run that set a stop has
    the ``stop_price`` column this reads -- see :func:`set_stops`.
    """
    events = run.events
    stop_sets = events[events["kind"] == STOP_SET]
    legs = entry_legs(events)
    is_leg = legs["signal"].notna()
    key = ["trial", "signal_name"]
    entries = events[(events["kind"] == EXECUTION) & is_leg & events["trial"].isin(stop_sets["trial"])]
    entries = entries.drop_duplicates(key)
    at = pd.MultiIndex.from_frame(entries[key])
    sent = events[(events["kind"] == SUBMIT) & is_leg].drop_duplicates(key).set_index(key).reindex(at)
    stop_orders = events[events["signal_name"] == STOP_LOSS]
    own = ["trial", "from_entry_signal"]
    stops = stop_orders[stop_orders["kind"] == EXECUTION].drop_duplicates(own).set_index(own).reindex(at)
    rejections = stop_orders[(stop_orders["kind"] == ORDER_UPDATE) & (stop_orders["order_state"] == REJECTED)]
    stop_as_set = stop_sets.groupby("trial")["stop_price"].last().reindex(entries["trial"])
    own_stop: FloatArray = stops["stop_price"].to_numpy(dtype=np.float64)

    frame = pd.DataFrame(index=pd.Index(entries["trial"].to_numpy(), name="trial"))
    frame["entry_signal"] = entries["signal_name"].to_numpy()
    frame["side"] = legs.loc[entries.index, "signal"].map(ENTRY_SIDES).to_numpy()
    frame["leg"] = legs.loc[entries.index, "leg"].astype(int).to_numpy()
    frame["last_leg"] = frame["leg"] == frame.groupby(level="trial")["leg"].transform("max")
    frame["entry_type"] = sent["order_type"].to_numpy()
    frame["entry_level"] = (
        sent["stop_price"].where(sent["order_type"] == STOP_MARKET, sent["limit_price"]).to_numpy()
    )
    frame["entry_bar"] = (entries["bar"] + lag).to_numpy()
    frame["entry_price"] = entries["execution_price"].to_numpy()
    frame["stop"] = np.where(np.isnan(own_stop), stop_as_set.to_numpy(dtype=np.float64), own_stop)
    frame["stop_rejected"] = at.isin(
        list(zip(rejections["trial"], rejections["from_entry_signal"], strict=True))
    )
    frame["stop_bar"] = (stops["bar"] + lag).to_numpy()
    frame["stop_fill"] = stops["execution_price"].to_numpy()

    return frame


def misattributed_stops(run: Run, frame: pd.DataFrame) -> int:
    """Count the stop fills that cannot be tied to a filled entry of the trial their trial number names."""
    events = run.events
    fills = events[(events["kind"] == EXECUTION) & (events["signal_name"] == STOP_LOSS)]
    fills = fills.drop_duplicates(["trial", "from_entry_signal"])
    legs = set(zip(frame.index, frame["entry_signal"], strict=True))

    return sum(
        (trial, entry) not in legs
        for trial, entry in zip(fills["trial"], fills["from_entry_signal"], strict=True)
    )


def bar_path(open_: float, high: float, low: float, close: float) -> tuple[float, float, float, float]:
    """Return the order a bar's prices are walked in: the extreme nearer the open first, the high on a tie.

    ``docs/nt8-fidelity.md``, "A stop on its entry bar is read along the bar's path".
    """
    if open_ - low < high - open_:
        return (open_, low, high, close)

    return (open_, high, low, close)


def entry_point(entry_type: str, side: float, level: float, path: tuple[float, ...]) -> int | None:
    """Return the point on a bar's path where an entry fills, or None if the path never fills it.

    A market entry and a limit the bar opened past fill at the open, point 0, a stop entry the bar
    opened past too, and otherwise the entry fills where the path first trades its level --
    through it, for a limit.
    """
    if entry_type == MARKET:
        return 0

    for point, price in enumerate(path):
        if has_traded(entry_type, side, price, level):
            return point

    return None


def path_after_entry(
    entry_type: str, side: float, level: float, path: tuple[float, ...]
) -> tuple[float, ...] | None:
    """Return the prices a bar's path visits from the entry's fill on, or None if the path never fills it."""
    point = entry_point(entry_type, side, level, path)
    if point is None:
        return None

    return path if point == 0 else (level, *path[point:])


def has_traded(entry_type: str, side: float, price: float, level: float) -> bool:
    """Return whether ``price`` has traded an entry's level: reached it for a stop, through it for a limit."""
    if entry_type == STOP_MARKET:
        return side * (price - level) >= 0

    return side * (price - level) < 0


def stop_on_path(after_entry: tuple[float, ...], side: float, stop: float) -> float | None:
    """Return where the stop fills on the path after the entry, or None if the path never reaches it.

    It fills at the path's first price if that is already past the stop, otherwise at its own.
    """
    if side * (after_entry[0] - stop) <= 0:
        return after_entry[0]

    if any(side * (price - stop) <= 0 for price in after_entry[1:]):
        return stop

    return None


class StoppedEntry(NamedTuple):
    """One stop and the entry it guards, as :func:`entry_bar_outcome` reads them."""

    entry_type: str
    side: float
    level: float
    stop: float
    last_leg: bool
    """Whether the stop guards its trial's last entry, which is its only one outside scenario 9."""

    fill_on_entry_bar: float | None
    """Where the stop filled on its entry bar, or None where it did not fill there."""


def stop_on_entry_bar(trade: StoppedEntry, path: tuple[float, ...], point: int) -> float | None:
    """Return where a stop fills on its entry bar, the entry filling at ``point`` on the bar's path.

    None where it does not fill there. The trial's last leg sees the path from its entry's fill
    on. An earlier leg sees the whole stretch of the path its entry filled in, and only the open
    fills it past its own price.
    """
    if trade.last_leg:
        after_entry = path if point == 0 else (trade.level, *path[point:])
        return stop_on_path(after_entry, trade.side, trade.stop)

    start = max(point - 1, 0)
    if start == 0:
        return stop_on_path(path, trade.side, trade.stop)

    if any(trade.side * (price - trade.stop) <= 0 for price in path[start:]):
        return trade.stop

    return None


def entry_bar_outcome(trade: StoppedEntry, ohlc: tuple[float, float, float, float]) -> str:
    """Return what a stop did on its entry bar, read against the bar's path.

    ``at_open``, ``at_stop`` and ``not_reached`` are the stop doing what the path says, and
    ``against_path`` is anything else, a path that never fills the entry included.
    """
    path = bar_path(*ohlc)
    point = entry_point(trade.entry_type, trade.side, trade.level, path)
    if point is None:
        return "against_path"

    actual = trade.fill_on_entry_bar
    if stop_on_entry_bar(trade, path, point) != actual:
        return "against_path"

    if actual is None:
        return "not_reached"

    return "at_stop" if actual == trade.stop else "at_open"


ENTRY_BAR_OUTCOMES = ("at_open", "at_stop", "not_reached", "against_path")
"""What :func:`entry_bar_outcome` returns, in the order the report prints them."""


def stop_fill_prices(
    side: FloatArray, fill: FloatArray, stop: FloatArray, bar: dict[str, FloatArray]
) -> dict[str, int]:
    """Count stop fills at the open of a bar that opened past the stop, at the stop's own price, or elsewhere.

    ``bar`` holds the fill bar's ``open``, ``low`` and ``high``. The first two are the gapped-stop
    rule -- ``docs/nt8-fidelity.md``, "A stop fills at the open when the bar gaps through it". A
    fill at the stop's price on a bar that opened past it is counted apart, because it breaks the
    rule.
    """
    open_ = bar["open"]
    adverse: FloatArray = np.where(side > 0, bar["low"], bar["high"])
    opened_past: BoolArray = side * (open_ - stop) < 0
    reached: BoolArray = side * (adverse - stop) <= 0
    at_open: BoolArray = opened_past & (fill == open_)
    at_stop: BoolArray = reached & (fill == stop)

    return {
        "at_open": int(at_open.sum()),
        "at_stop": int((at_stop & ~opened_past).sum()),
        "at_stop_past_open": int((at_stop & opened_past).sum()),
        "other": int((~at_open & ~at_stop).sum()),
    }


def stops_after_entry(frame: pd.DataFrame, bars: pd.DataFrame) -> dict[str, dict[str, dict[str, int]]]:
    """Count the stops by how their entry bar opened against them, and what each did.

    ``beyond`` and ``gapped`` met an entry bar opening past the stop, the first with the entry
    filling beyond the stop as well, and ``control`` an entry bar opening at or short of it. Each
    entry bar is read against its path (:func:`entry_bar_outcome`), the trials' last legs under
    ``entry_bar`` and any earlier legs under ``entry_bar_earlier_legs``, and a stop filling on a
    later bar against the gapped-stop rule (:func:`stop_fill_prices`).
    """
    side: FloatArray = frame["side"].to_numpy(dtype=np.float64)
    stop: FloatArray = frame["stop"].to_numpy(dtype=np.float64)
    entry_bars = bars.reindex(frame["entry_bar"])
    entry_open: FloatArray = entry_bars["open"].to_numpy(dtype=np.float64)
    opened_past: BoolArray = side * (entry_open - stop) < 0
    beyond: BoolArray = opened_past & (side * (frame["entry_price"].to_numpy(dtype=np.float64) - stop) < 0)
    groups = {"beyond": beyond, "gapped": opened_past & ~beyond, "control": ~opened_past}
    filled: BoolArray = frame["stop_fill"].notna().to_numpy()
    rejected: BoolArray = frame["stop_rejected"].to_numpy(dtype=bool)
    bars_after_entry = (frame["stop_bar"] - frame["entry_bar"]).to_numpy(dtype=np.float64)
    fill_bar = {
        column: bars[column].reindex(frame["stop_bar"]).to_numpy(dtype=np.float64)
        for column in ("open", "low", "high")
    }
    fill: FloatArray = frame["stop_fill"].to_numpy(dtype=np.float64)
    level: FloatArray = frame["entry_level"].to_numpy(dtype=np.float64)
    last: BoolArray = frame["last_leg"].to_numpy(dtype=bool)
    on_entry_bar: BoolArray = bars_after_entry == 0
    entry_ohlc = entry_bars[["open", "high", "low", "close"]].to_numpy(dtype=np.float64).tolist()
    outcomes = np.array(
        [
            entry_bar_outcome(
                StoppedEntry(
                    str(kind),
                    float(side[row]),
                    float(level[row]),
                    float(stop[row]),
                    bool(last[row]),
                    float(fill[row]) if on_entry_bar[row] else None,
                ),
                (open_, high, low, close),
            )
            for row, (kind, (open_, high, low, close)) in enumerate(
                zip(frame["entry_type"], entry_ohlc, strict=True)
            )
        ],
        dtype=object,
    )

    def later_prices(read: BoolArray) -> dict[str, int]:
        return stop_fill_prices(side[read], fill[read], stop[read], {k: v[read] for k, v in fill_bar.items()})

    def on_entry_bar_of(legs: BoolArray) -> dict[str, int]:
        return {outcome: int((legs & (outcomes == outcome)).sum()) for outcome in ENTRY_BAR_OUTCOMES}

    def counted(group: BoolArray) -> dict[str, dict[str, int]]:
        return {
            "trials": {
                "entries": int(group.sum()),
                "rejected": int((group & rejected).sum()),
                "not_filled": int((group & ~rejected & ~filled).sum()),
                "filled_before_entry": int((group & filled & (bars_after_entry < 0)).sum()),
            },
            "entry_bar": on_entry_bar_of(group & last),
            "entry_bar_earlier_legs": on_entry_bar_of(group & ~last),
            "on_a_later_bar": later_prices(group & filled & (bars_after_entry > 0)),
        }

    return {name: counted(group) for name, group in groups.items()}


def path_verdict(counts: dict[str, int]) -> str:
    """Return whether every entry bar's stop did what the bar's path says, in a few words."""
    broken = counts["against_path"]
    total = sum(counts.values())
    if total == 0:
        return "no instances in this run"

    if broken:
        return f"{broken} of {total} break the rule"

    return f"all {total} as the bar's path says"


def stop_breaks(counts: dict[str, int]) -> int:
    """Return how many of a set's later-bar stop fills break the gapped-stop rule."""
    return counts["at_stop_past_open"] + counts["other"]


def stop_verdict(counts: dict[str, int]) -> str:
    """Return whether every later-bar stop fill follows the gapped-stop rule, in a few words."""
    broken = stop_breaks(counts)
    total = sum(counts.values())
    if total == 0:
        return "no instances in this run"

    if broken == 0:
        return f"all {total} at the open where the bar opened past the stop, otherwise at the stop"

    return f"{broken} of {total} break the rule"


def breaks(counts: dict[str, int]) -> int:
    """Return how many of a set's fills break the rule."""
    return counts["at_open"] + counts["other"]


def verdict(counts: dict[str, int]) -> str:
    """Return whether every fill follows the rule, in a few words."""
    broken = breaks(counts)
    total = counts["at_limit"] + counts["at_bar_extreme"] + broken
    if total == 0:
        return "no instances in this run"

    if broken == 0:
        return f"all {total} at the nearest price the bar traded"

    return f"{broken} of {total} break the rule"


def report_stops(run: Run) -> int:
    """Print where each stop filled, and return how many stop fills break the rule or cannot be read."""
    frame = stop_trials(run)
    misattributed = misattributed_stops(run, frame)
    if misattributed:
        logger.warning(
            "  %d stop fills do not belong to their trial's entry; no stop below can be read", misattributed
        )
        return misattributed

    stops = stops_after_entry(frame, run.bars)
    several_legs = bool((~frame["last_leg"]).any())
    broken = 0
    for group, label in STOP_GROUPS.items():
        entry_bar = stops[group]["entry_bar"]
        earlier = stops[group]["entry_bar_earlier_legs"]
        later = stops[group]["on_a_later_bar"]
        logger.info("%s: %s", label, stops[group]["trials"])
        if several_legs:
            logger.info("  on the entry bar, the last leg: %s -- %s", entry_bar, path_verdict(entry_bar))
            logger.info("  on the entry bar, the earlier legs: %s -- %s", earlier, path_verdict(earlier))
        else:
            logger.info("  on the entry bar: %s -- %s", entry_bar, path_verdict(entry_bar))
        logger.info("  filled on a later bar: %s -- %s", later, stop_verdict(later))
        broken += (
            stops[group]["trials"]["filled_before_entry"]
            + entry_bar["against_path"]
            + earlier["against_path"]
            + stop_breaks(later)
        )

    return broken


def report(run: Run) -> bool:
    """Print every measurement the run supports. False if any check the readings rest on fails."""
    logger.info("run: %s", run.stem)
    if run.config is not None and not run.config.empty:
        effective = run.config.iloc[-1]
        logger.info(
            "  effective: fill=%s fill_limit_on_touch=%s slippage=%s stop_target_handling=%s",
            effective["order_fill_resolution"],
            effective["is_fill_limit_on_touch"],
            effective["slippage"],
            effective["stop_target_handling"],
        )

    logger.info("entries left working past their bar: %d", stuck_entries(run))
    unrecorded = unrecorded_trials(run)
    if len(unrecorded):
        logger.info("  %d trials reach a bar after the last one recorded and are left out", len(unrecorded))
        run = replace(run, events=run.events[~run.events["trial"].isin(unrecorded)])

    # Whether NinjaTrader took each entry needs no fill bar, so it is reported before the lag check.
    entries = limit_entry_fills(limit_entries(run), run.bars)
    taken = {
        group: {key: entries[group][key] for key in ("sent", "acknowledged", "rejected")}
        for group in ENTRY_GROUPS
    }
    logger.info("limit entries sent: %s", taken)

    lag = measure_lag(run)
    logger.info("callback lag on market fills: %s", lag)
    if lag["fills"] == 0:
        lag = measure_lag_on_entries(run)
        logger.info("  no market fill to measure it on, so on the entries' prices: %s", lag)

    if not lag_is_clean(lag):
        logger.warning("  callback lag is NOT a clean +1 in this run; no fill bar below can be trusted")
        return False

    frame = trials(run)
    misattributed = misattributed_targets(run, frame)
    if misattributed:
        logger.warning(
            "  %d target fills do not belong to their trial's entry; nothing below can be read", misattributed
        )
        return False

    passed = passed_at_entry(frame, run.bars)
    logger.info("target passed at the entry (#452): %s", passed["trials"])
    for when in ("on_entry_bar", "on_a_later_bar"):
        logger.info("  filled %s: %s -- %s", when.replace("_", " "), passed[when], verdict(passed[when]))

    resting = gapped_while_resting(frame, run.bars)
    logger.info(
        "target gapped through while resting (#244): %s -- %s", resting["gapped"], verdict(resting["gapped"])
    )
    logger.info(
        "  control, a bar opening short of the target: %s -- %s",
        resting["control"],
        verdict(resting["control"]),
    )
    every = target_fill_prices(frame.dropna(subset=["target_fill"]), run.bars)
    logger.info("every target fill: %s -- %s", every, verdict(every))

    for group, label in ENTRY_GROUPS.items():
        logger.info("%s: %s -- %s", label, entries[group], verdict(entries[group]))
    logger.info("  limit entries filled off the bar they were live on: %s", entries["checks"])

    broken = (
        passed["trials"]["filled_before_entry"]
        + breaks(every)
        + sum(breaks(entries[group]) + entries[group]["through_unfilled"] for group in ENTRY_GROUPS)
        + entries["checks"]["filled_off_the_live_bar"]
    )
    if set_stops(run):
        broken += report_stops(run)

    if broken:
        logger.warning("  %d fills break the rule, name the wrong bar, or are missing", broken)
        return False

    return True


def main(argv: list[str]) -> int:
    """Check where the passed targets in one run filled and return the process exit code."""
    logsetup.configure(__name__)
    if len(argv) != EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    return 0 if report(read_run(Path(argv[1]))) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
