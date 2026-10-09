"""Read a ``NqbtPassedTargetProbe`` run and check where each passed limit order filled.

    uv run tools/reconcile_passed_target.py <..._events.csv>

The companion ``_bars.csv`` and ``_config.csv`` are found beside it.
``tools/README.md`` § "reconcile_passed_target.py".
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

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

PROFIT_TARGET = "Profit target"
"""The name NinjaTrader gives every order ``SetProfitTarget`` places."""

PROBE_EXIT = "probeExit"
"""The probe's own market exit."""

TARGET_SET = "TARGET_SET"
REJECTED = "Rejected"
MARKET = "Market"
LIMIT = "Limit"

ENTRY_GROUPS = {
    "resting": "limit entry a bar trades to (#454)",
    "gapped": "limit entry a bar opens past (#454)",
    "marketable": "limit entry sent marketable (#454)",
}
"""How :func:`limit_entry_fills` splits the limit entries, and what the report calls each."""


def executions(run: Run, names: Collection[str]) -> pd.DataFrame:
    """Return each trial's first execution of an order named in ``names``, indexed by trial."""
    events = run.events
    rows = events[(events["kind"] == EXECUTION) & events["signal_name"].isin(names)]

    return rows.drop_duplicates("trial").set_index("trial")


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


def lag_is_clean(counts: dict[str, int]) -> bool:
    """Return whether every market fill that decides anything says the callback lags one bar."""
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
    ``docs/nt8-fidelity.md``, "A target the market has passed fills at the nearest price the bar
    traded". The open is counted apart -- ``tools/README.md`` § "reconcile_passed_target.py".
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

    # Whether NinjaTrader took each entry needs no fill bar, so it is reported before the lag check.
    entries = limit_entry_fills(limit_entries(run), run.bars)
    taken = {
        group: {key: entries[group][key] for key in ("sent", "acknowledged", "rejected")}
        for group in ENTRY_GROUPS
    }
    logger.info("limit entries sent: %s", taken)

    lag = measure_lag(run)
    logger.info("callback lag on market fills: %s", lag)
    if not lag_is_clean(lag):
        logger.warning("  market-fill lag is NOT a clean +1 in this run; no fill bar below can be trusted")
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
