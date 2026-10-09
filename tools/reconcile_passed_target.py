"""Read a ``NqbtPassedTargetProbe`` run and report where a passed profit target fills.

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
from tools.reconcile_order_lifetime import EXECUTION, ORDER_UPDATE, Run, read_run

if TYPE_CHECKING:
    from collections.abc import Collection

    from nqbt.arrays import BoolArray, FloatArray

logger = logging.getLogger(__name__)

EXPECTED_ARGV = 2

ENTRY_SIDES = {"probeLong": 1.0, "probeShort": -1.0}
"""The probe's two entry signals and the side each trades, +1 long."""

PROFIT_TARGET = "Profit target"
"""The name NinjaTrader gives every order ``SetProfitTarget`` places."""

TARGET_SET = "TARGET_SET"
REJECTED = "Rejected"


def executions(run: Run, names: Collection[str]) -> pd.DataFrame:
    """Return each trial's first execution of an order named in ``names``, indexed by trial."""
    events = run.events
    rows = events[(events["kind"] == EXECUTION) & events["signal_name"].isin(names)]

    return rows.drop_duplicates("trial").set_index("trial")


def measure_entry_lag(run: Run) -> dict[str, int]:
    """Count the market entries filled at the reported bar's open, against the next bar's.

    A market entry fills at an open, so whichever bar's open explains every fill is the bar the
    callback was really reporting on. A fill both opens explain decides nothing.
    """
    fills = executions(run, ENTRY_SIDES)
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
    """Return whether every entry fill that decides anything says the callback lags one bar."""
    return counts["reported_plus_one"] > 0 and counts["reported"] == 0 and counts["neither"] == 0


def trials(run: Run, lag: int = 1) -> pd.DataFrame:
    """Return one row per filled entry: its side, its target and where that target filled.

    Bars are the bars the fills happened on, the reported bar plus ``lag``. ``target_at_entry``
    is the price set before the entry was sent, and ``target`` the one in force when it filled.
    """
    events = run.events
    entries = executions(run, ENTRY_SIDES)
    targets = executions(run, [PROFIT_TARGET])
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
    frame["target_at_entry"] = target_sets.groupby("trial")["limit_price"].first()
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


def fill_prices(fill: FloatArray, target: FloatArray, open_: FloatArray) -> dict[str, int]:
    """Count fills at the target's own price, at the fill bar's open, and at neither."""
    at_target: BoolArray = fill == target
    at_open: BoolArray = (fill == open_) & ~at_target

    return {
        "at_target": int(at_target.sum()),
        "at_open": int(at_open.sum()),
        "other": int((~at_target & ~at_open).sum()),
    }


def target_fill_prices(filled: pd.DataFrame, bars: pd.DataFrame) -> dict[str, int]:
    """Apply :func:`fill_prices` to rows of :func:`trials` whose target filled."""
    open_: FloatArray = bars["open"].reindex(filled["target_bar"]).to_numpy(dtype=np.float64)

    return fill_prices(
        filled["target_fill"].to_numpy(dtype=np.float64), filled["target"].to_numpy(dtype=np.float64), open_
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
    passed, which :func:`passed_at_entry` reads. ``control_bar`` counts the control fills at the
    target whose fill bar's range holds the target, and those whose range does not.
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
    control_at_target: BoolArray = control & (fill == target)
    inside: BoolArray = (low <= target) & (target <= high)

    return {
        "gapped": fill_prices(fill[gapped], target[gapped], open_[gapped]),
        "control": fill_prices(fill[control], target[control], open_[control]),
        "control_bar": {
            "inside": int((control_at_target & inside).sum()),
            "outside": int((control_at_target & ~inside).sum()),
        },
    }


def verdict(counts: dict[str, int]) -> str:
    """Return what the fills say in a few words: at the target, at the open, mixed, or nothing."""
    total = counts["at_target"] + counts["at_open"] + counts["other"]
    if total == 0:
        return "no instances in this run"

    if counts["at_target"] == total:
        return f"all {total} at the target's own price"

    if counts["at_open"] == total:
        return f"all {total} at the fill bar's open"

    return f"mixed over {total} -- read the counts"


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

    lag = measure_entry_lag(run)
    logger.info("callback lag on entry fills: %s", lag)
    if not lag_is_clean(lag):
        logger.warning("  entry-fill lag is NOT a clean +1 in this run; no fill bar below can be trusted")
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
    if resting["control_bar"]["outside"]:
        logger.warning(
            "  %d control fills at the target lie outside their bar; the target fills' lag is not +1",
            resting["control_bar"]["outside"],
        )
        return False

    return True


def main(argv: list[str]) -> int:
    """Report where the passed targets in one run filled and return the process exit code."""
    logsetup.configure(__name__)
    if len(argv) != EXPECTED_ARGV:
        logger.info("%s", __doc__)
        return 2

    return 0 if report(read_run(Path(argv[1]))) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
