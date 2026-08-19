"""Per-trade audit trail for hand-verification against a chart.

Nothing downstream of the simulation is trustworthy until a human has checked a handful of
trades bar by bar and NT8 Strategy Analyzer has been reconciled against the same window.
This module exposes every intermediate value the simulation used -- the signal bar's
geometry, each gate's operands and verdict, the trigger and stop arithmetic, how the entry
filled, and where every leg left -- so a trade can be ticked off without reading the code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt.sim.deadcat import entry_bracket
from nqbt.sim.runner import deadcat_signal
from nqbt.trades import SHORT

if TYPE_CHECKING:
    from nqbt.context import Dataset
    from nqbt.instruments import Instrument
    from nqbt.sim.types import DeadCatParams


def explain_trades(
    data: Dataset,
    params: DeadCatParams,
    trades: pd.DataFrame,
    instrument: Instrument,
    limit: int = 20,
) -> pd.DataFrame:
    """Annotate the first ``limit`` trades with everything that produced them.

    The dataset must have been prepared with ``keep_ma_values=True``; the moving-average
    values themselves are needed to show *why* each trend gate passed, not just that it did.
    """
    if any(g.values is None for g in data.mas.values()):
        msg = "explain_trades needs raw indicator values; call context.prepare(..., keep_ma_values=True)"
        raise ValueError(
            msg,
        )

    signal = deadcat_signal(data, params)
    index = data.index
    tick = instrument.tick_size

    ema = data.ma_values("ema", params.ema_period)
    fast = data.ma_values("sma", params.fast_sma_period)
    slow = data.ma_values("sma", params.slow_sma_period)
    # The audit trail reports every gate whether or not this combination reads it, so VWAP
    # is required here even when ``use_vwap`` is off. That is why ``cli.py`` sets
    # ``needs_vwap=True`` unconditionally rather than taking the spec from the grid: a
    # sweep declares what it reads, but ``--explain`` exists to show what it did not.
    vwap = data.vwap_values()

    rows = []
    for trade_id, legs in list(trades.groupby("trade_id"))[:limit]:
        entry_bar = int(legs["entry_bar"].iloc[0])
        s = entry_bar - 1  # the signal bar: the order rests for exactly one bar
        p = s - 1  # the bar the "previous green" and "new high" gates look back at

        o, h, l, c = data.open[s], data.high[s], data.low[s], data.close[s]
        body = abs(c - o)
        upper = h - max(c, o)
        lower = min(c, o) - l

        # Shared with the loop, not restated. See ``entry_bracket``: the copy that used to
        # sit here dropped the Close[0] - 2 ticks cap and was wrong on half of all trades.
        trigger, stop, risk = entry_bracket(
            h,
            l,
            c,
            params.entry_offset_ticks * tick,
            params.stop_offset_ticks * tick,
            SHORT,  # DeadCatBounce is short-only; see nqbt.sim.deadcat.entry_bracket.
        )

        entry_price = float(legs["entry_price"].iloc[0])
        gapped = data.open[entry_bar] <= trigger

        row = {
            "trade_id": trade_id,
            "signal_time": index[s],
            "signal_bar": s,
            "sig_open": o,
            "sig_high": h,
            "sig_low": l,
            "sig_close": c,
            # -- inverted hammer -------------------------------------------------
            "body": body,
            "upper_wick": upper,
            "lower_wick": lower,
            "upper_ge_2x_body": upper >= body * 2,
            "lower_le_body": lower <= body,
            "body_positive": body > 0,
            # -- lookback gates --------------------------------------------------
            "prev_open": data.open[p] if p >= 0 else np.nan,
            "prev_close": data.close[p] if p >= 0 else np.nan,
            "prev_green_ok": (data.close[p] >= data.open[p]) if p >= 0 else False,
            "prev_high": data.high[p] if p >= 0 else np.nan,
            "new_high_ok": (h > data.high[p]) if p >= 0 else False,
            # -- trend gates: operands, so the verdict is checkable ---------------
            "ema": ema[s],
            "below_ema": not (c > ema[s]),
            "fast_sma": fast[s],
            "below_fast_sma": not (c > fast[s]),
            "slow_sma": slow[s],
            "below_slow_sma": not (c > slow[s]),
            "vwap": vwap[s],
            "below_vwap": not (c > vwap[s]),
            "signal_fired": bool(signal[s]),
            # -- order arithmetic -------------------------------------------------
            "trigger": trigger,
            "initial_stop": stop,
            "risk_points": risk,
            "risk_ticks": risk / tick,
            # -- fill --------------------------------------------------------------
            "entry_time": index[entry_bar],
            "entry_open": data.open[entry_bar],
            "entry_low": data.low[entry_bar],
            "entry_price": entry_price,
            "fill_type": "gap_at_open" if gapped else "trigger_touched",
        }

        for leg in legs.sort_values("leg").itertuples():
            n = leg.leg
            row[f"leg{n}_target"] = leg.target_price
            row[f"leg{n}_exit_time"] = index[int(leg.exit_bar)]
            row[f"leg{n}_exit"] = leg.exit_price
            row[f"leg{n}_reason"] = leg.exit_reason
            row[f"leg{n}_r"] = leg.r_multiple
            row[f"leg{n}_net"] = leg.net_pnl
            row[f"leg{n}_ambiguous"] = leg.ambiguous_bar

        row["trade_net"] = float(legs["net_pnl"].sum())
        rows.append(row)

    return pd.DataFrame(rows)


def ratchet_history(
    data: Dataset,
    params: DeadCatParams,
    trades: pd.DataFrame,
    trade_id: int,
    instrument: Instrument,
) -> pd.DataFrame:
    """Bar-by-bar stop history for one trade, to check the ratchet by hand.

    Reproduces the rule from ``DeadCatBounce.cs``: at the close of each bar the stop
    becomes ``High[bar-1] + 2 ticks`` when that is tighter, and the stop set at the close
    of bar ``i`` is the one live during bar ``i+1``.
    """
    legs = trades[trades["trade_id"] == trade_id]
    if legs.empty:
        msg = f"no trade with id {trade_id}"
        raise KeyError(msg)

    entry_bar = int(legs["entry_bar"].iloc[0])
    last_bar = int(legs["exit_bar"].max())
    offset = params.stop_offset_ticks * instrument.tick_size

    stop = float(legs["initial_stop"].iloc[0])
    rows = []
    for i in range(entry_bar, last_bar + 1):
        live = stop  # set at the close of bar i-1
        candidate = data.high[i - 1] + offset if i >= 1 else np.nan
        tightened = candidate < stop
        rows.append(
            {
                "bar": i,
                "time": data.index[i],
                "high": data.high[i],
                "low": data.low[i],
                "close": data.close[i],
                "stop_live_this_bar": live,
                "stop_hit": data.high[i] >= live,
                "candidate_from_prev_high": candidate,
                "tightened": bool(tightened),
            },
        )
        if tightened:
            stop = candidate
    return pd.DataFrame(rows)
