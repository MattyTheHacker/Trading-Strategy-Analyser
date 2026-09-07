"""Ask the minute bars inside an ambiguous bar which level price reached first.

    from nqbt import disambiguate

A bar holding both the stop and a target cannot say which came first, so the simulation
assumes -- ``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the
open". The minute bars *inside* that bar usually can say, and §M13 is what makes reading them
exact rather than approximate: OHLC aggregation is associative, so a 5-minute bar **is** five
1-minute bars and no tick data is involved.

**This is a diagnostic and must never reach ``nqbt/sim/``.** NT8 guesses on the same bars, so a
simulation resolving them truthfully would disagree with Tier 2 on exactly the bars where a
disagreement cannot be attributed -- the more-precise-than-NT8 error. Nothing here is
simulated: an assumption already made is being scored, which is the trade-review side's
reasoning rather than the simulator's. ``docs/roadmap.md`` §M28.4.

It also runs **after** a result exists rather than inside one, and only where the assumption is
common enough to be worth the pass -- :data:`MIN_AMBIGUOUS_SHARE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nqbt.sim.bracket import AMBIGUITY_BEST_CASE, AMBIGUITY_WORST_CASE, limit_filled, sided

if TYPE_CHECKING:
    from nqbt.arrays import FloatArray, IntArray, OffsetArray

TARGET_FIRST = "target_first"
STOP_FIRST = "stop_first"
"""What the minute bars settle, and the only two verdicts a resolved log is rebuilt from."""

STILL_AMBIGUOUS = "still_ambiguous"
"""One minute bar held both levels, so a minute is not fine enough.

The residue this module sizes rather than resolves; only ``data/tick/`` goes further, and that
is a separate question from this one."""

MISALIGNED = "misaligned"
"""The minute bars picked out do not aggregate back to the coarse bar they should be inside.

A refusal rather than a verdict: the window is wrong, so anything read from it would be read
off the wrong bars."""

ENTRY_UNLOCATED = "entry_unlocated"
"""The trade opened inside this very bar and no minute bar in it holds the entry fill.

A refusal: without knowing which minute the position opened in, the minutes before it would be
read as if the trade were already live."""

STOP_MOVED = "stop_moved"
"""The stop at the exit differs from the one the trade opened with, so the log's ``initial_stop``
is not the level that was live.

A trailing archetype reaches this on every leg, which is the intended outcome: refused with a
reason beats resolved against the wrong level."""

DECIDED = (TARGET_FIRST, STOP_FIRST)
"""The verdicts :func:`resolved_log` acts on. Everything else keeps NT8's guess and is counted."""

MIN_AMBIGUOUS_SHARE = 0.05
"""Below this share of ambiguous leg exits, the pass is not run at all.

Stated as a meaning rather than tuned: **a result whose verdict the assumption could not have
decided does not need the assumption scored.** The registry's healthy archetypes sit two orders
of magnitude under it and §M28.2's retest sits seven times over it -- ``docs/roadmap.md`` §M28.4.
"""


class DisambiguationError(ValueError):
    """Raised when the three arms cannot be read as one configuration's three outcomes."""


def worth_resolving(ambiguous_share: float) -> bool:
    """Whether a result resolves enough bars by assumption for the pass to be worth running."""
    return ambiguous_share >= MIN_AMBIGUOUS_SHARE


def owning_bar(fine_index: pd.DatetimeIndex, coarse_index: pd.DatetimeIndex) -> IntArray:
    """Which coarse bar each minute bar was aggregated into.

    Bars are stamped end-of-bar, so a minute bar belongs to the first coarse bar stamped at or
    after it. Non-decreasing by construction, which is what lets :func:`sub_bars` slice it.
    """
    return np.asarray(coarse_index.searchsorted(fine_index, side="left"), dtype=np.int64)


def sub_bars(fine: pd.DataFrame, owner: IntArray, position: int) -> pd.DataFrame:
    """The minute bars one coarse bar was built from, in order."""
    start, stop = np.searchsorted(owner, [position, position + 1])

    return fine.iloc[int(start) : int(stop)]


def rebuilds(window: pd.DataFrame, coarse_bar: pd.Series[float]) -> bool:
    """Whether these minute bars aggregate back to exactly the coarse bar they came from.

    §M13's associativity used as a **guard on the alignment** rather than as an argument for it:
    if the window is off by a bar the four prices stop matching, and the leg is refused instead
    of answered off the wrong bars.
    """
    if window.empty:
        return False

    return bool(
        window["open"].iloc[0] == coarse_bar["open"]
        and window["close"].iloc[-1] == coarse_bar["close"]
        and window["high"].max() == coarse_bar["high"]
        and window["low"].min() == coarse_bar["low"],
    )


def entry_minute(window: pd.DataFrame, coarse_bar: pd.Series[float], entry_price: float) -> int:
    """Which minute bar the position opened inside, or ``-1`` if it was open from the start.

    ``-1`` covers both a trade that opened on an earlier bar and one that filled at this bar's
    open, since either way the whole window is held. Otherwise the fill is somewhere inside one
    minute and that minute's internal order is unknowable -- the earliest minute whose range
    holds the fill price is the earliest the position can have existed.
    """
    if entry_price == coarse_bar["open"]:
        return -1

    low: FloatArray = window["low"].to_numpy()
    high: FloatArray = window["high"].to_numpy()
    inside: OffsetArray = np.flatnonzero((low <= entry_price) & (entry_price <= high))
    if inside.size == 0:
        return len(window)

    return int(inside[0])


def first_level_reached(
    window: pd.DataFrame,
    stop: float,
    target: float,
    direction: float,
    *,
    fill_limit_on_touch: bool,
    opened_in: int = -1,
) -> str:
    """Which level the minute bars reach first, or why they cannot say.

    Reads the simulator's own two predicates rather than restating them, so the question asked
    of a minute bar is the question ``resolve_brackets`` asks of the bar above it.

    ``opened_in`` is the minute the position opened inside, and the minutes before it are not
    the trade's -- **the case is the rule rather than the exception here**, since a limit entry
    that exits on its own entry bar is most of what makes a bar ambiguous at all
    (``docs/roadmap.md`` §M28.2). A level reached inside that same minute cannot be ordered
    against the fill, so it is reported as unsettled rather than guessed at a second time.
    """
    low: FloatArray = window["low"].to_numpy()
    high: FloatArray = window["high"].to_numpy()
    if opened_in >= low.size:
        return ENTRY_UNLOCATED

    for i in range(max(opened_in, 0), low.size):
        adverse, favourable = sided(low[i], high[i], direction)
        stop_hit: bool = direction * adverse <= direction * stop
        target_hit: bool = limit_filled(favourable, target, fill_limit_on_touch, direction)
        if not stop_hit and not target_hit:
            continue

        if i == opened_in or (stop_hit and target_hit):
            return STILL_AMBIGUOUS

        return STOP_FIRST if stop_hit else TARGET_FIRST

    return MISALIGNED


def first_target(
    legs: pd.DataFrame, coarse_bar: pd.Series[float], direction: float, *, fill_limit_on_touch: bool
) -> float:
    """The reachable target price would reach first, which is the one nearest the **fill**.

    Not the one nearest the bar's open. That is what ``resolve_brackets`` compares distances
    against, but the question here is which level price touches first once the position exists,
    and on a ladder that is the closest rung to the entry -- measuring from the open instead
    puts a further target in the walk and biases every verdict towards the stop.

    ``nan`` when no leg's target is reachable on the bar, which cannot happen on a bar the
    simulation called ambiguous and is therefore a refusal rather than a case.
    """
    _, favourable = sided(coarse_bar["low"], coarse_bar["high"], direction)
    targets: FloatArray = legs["target_price"].to_numpy()
    reachable: FloatArray = np.array(
        [
            target
            for target in targets
            if not np.isnan(target) and limit_filled(favourable, target, fill_limit_on_touch, direction)
        ],
    )
    if reachable.size == 0:
        return float("nan")

    entry: float = float(legs["entry_price"].iloc[0])

    return float(reachable[np.argmin(np.abs(reachable - entry))])


def stop_is_the_one_it_opened_with(legs: pd.DataFrame, worst_legs: pd.DataFrame, slippage: float) -> bool:
    """Whether ``initial_stop`` was still the live stop when the bar resolved.

    The worst-case arm exits **every** open leg at the stop on an ambiguous bar, so its fill is
    the live stop's fill and disagreeing with ``initial_stop`` means the stop moved. Derived
    from the arms rather than declared per archetype, so a trailing one is caught by the data.
    """
    if worst_legs.empty:
        return False

    stop: float = float(legs["initial_stop"].iloc[0])
    direction: float = float(legs["direction"].iloc[0])
    expected: float = stop - direction * slippage
    fills: FloatArray = worst_legs["exit_price"].to_numpy()

    return bool(np.isclose(fills, expected).all())


def _verdict(
    legs: pd.DataFrame,
    worst_legs: pd.DataFrame,
    window: pd.DataFrame,
    coarse_bar: pd.Series[float],
    slippage: float,
    *,
    fill_limit_on_touch: bool,
) -> tuple[str, float, float]:
    """One ambiguous bar's verdict and the two levels it was read against."""
    direction: float = float(legs["direction"].iloc[0])
    stop: float = float(legs["initial_stop"].iloc[0])
    target: float = first_target(legs, coarse_bar, direction, fill_limit_on_touch=fill_limit_on_touch)
    if not stop_is_the_one_it_opened_with(legs, worst_legs, slippage):
        return STOP_MOVED, stop, target

    if np.isnan(target) or not rebuilds(window, coarse_bar):
        return MISALIGNED, stop, target

    opened_here: bool = int(legs["entry_bar"].iloc[0]) == int(legs["exit_bar"].iloc[0])
    opened_in: int = (
        entry_minute(window, coarse_bar, float(legs["entry_price"].iloc[0])) if opened_here else -1
    )
    reached: str = first_level_reached(
        window,
        stop,
        target,
        direction,
        fill_limit_on_touch=fill_limit_on_touch,
        opened_in=opened_in,
    )

    return reached, stop, target


def guessed(legs: pd.DataFrame) -> str:
    """What the simulation assumed on this bar, read back from how its legs left."""
    if (legs["exit_reason"] == "target").any():
        return TARGET_FIRST

    return STOP_FIRST


def resolve(
    ranked: pd.DataFrame,
    worst: pd.DataFrame,
    fine: pd.DataFrame,
    coarse: pd.DataFrame,
    *,
    slippage: float,
    fill_limit_on_touch: bool,
) -> pd.DataFrame:
    """One row per ambiguous bar, saying what the minute bars inside it show.

    ``ranked`` is the log NT8's rule produced and ``worst`` the same configuration under
    ``AMBIGUITY_WORST_CASE``; the second is read only to check that the stop had not moved.
    """
    ambiguous: pd.DataFrame = ranked[ranked["ambiguous_bar"]]
    if ambiguous.empty:
        return pd.DataFrame()

    owner: IntArray = owning_bar(pd.DatetimeIndex(fine.index), pd.DatetimeIndex(coarse.index))
    rows: list[dict[str, object]] = []
    for (trade_id, exit_bar), legs in ambiguous.groupby(["trade_id", "exit_bar"], sort=True):
        position = int(exit_bar)  # type: ignore[call-overload]  # an index by construction
        coarse_bar: pd.Series[float] = coarse.iloc[position]
        worst_legs: pd.DataFrame = worst[(worst["trade_id"] == trade_id) & (worst["exit_bar"] == exit_bar)]
        status, stop, target = _verdict(
            legs,
            worst_legs,
            sub_bars(fine, owner, position),
            coarse_bar,
            slippage,
            fill_limit_on_touch=fill_limit_on_touch,
        )
        rows.append(
            {
                "trade_id": int(trade_id),  # type: ignore[call-overload]  # an id by construction
                "exit_bar": position,
                "exit_time": legs["exit_time"].iloc[0] if "exit_time" in legs.columns else pd.NaT,
                "legs": len(legs),
                "opened_here": int(legs["entry_bar"].iloc[0]) == position,
                "direction": float(legs["direction"].iloc[0]),
                "stop": stop,
                "target": target,
                "assumed": guessed(legs),
                "resolved": status,
            },
        )
    table: pd.DataFrame = pd.DataFrame(rows)
    settled = table["resolved"].isin(DECIDED)
    table["agrees"] = (table["assumed"] == table["resolved"]).astype("boolean").where(settled)

    return table


def accuracy(table: pd.DataFrame) -> dict[str, object]:
    """How often the assumption was right, over the bars the minute bars could settle."""
    decided: pd.DataFrame = table[table["resolved"].isin(DECIDED)] if not table.empty else table
    agreed: int = int(decided["agrees"].sum()) if not decided.empty else 0

    return {
        "ambiguous_bars": len(table),
        "decided": len(decided),
        "assumption_correct": agreed,
        "assumption_accuracy": agreed / len(decided) if len(decided) else float("nan"),
        "still_ambiguous": int((table["resolved"] == STILL_AMBIGUOUS).sum()) if not table.empty else 0,
        "opened_here": int(table["opened_here"].sum()) if not table.empty else 0,
        "refused": int((~table["resolved"].isin([*DECIDED, STILL_AMBIGUOUS])).sum())
        if not table.empty
        else 0,
    }


ARM_FOR = {STOP_FIRST: AMBIGUITY_WORST_CASE, TARGET_FIRST: AMBIGUITY_BEST_CASE}
"""Which arm's rows a settled bar takes. The two ends of the band are the two outcomes, so a
resolved log is a **row selection** rather than a recomputation -- nothing here does arithmetic
on a price."""


def aligned(ranked: pd.DataFrame, worst: pd.DataFrame, best: pd.DataFrame) -> bool:
    """Whether the three arms are the same trades, leg for leg, in the same order.

    They are, because the whole position closes on an ambiguous bar under either policy, so the
    next bar starts flat in every arm. Checked rather than assumed, since a resolved log built
    on a false alignment would attribute one configuration's legs to another's.
    """
    keys = ["trade_id", "leg", "entry_bar", "exit_bar"]

    return all(
        len(arm) == len(ranked)
        and arm[keys].reset_index(drop=True).equals(ranked[keys].reset_index(drop=True))
        for arm in (worst, best)
    )


def resolved_log(
    ranked: pd.DataFrame,
    worst: pd.DataFrame,
    best: pd.DataFrame,
    table: pd.DataFrame,
) -> pd.DataFrame:
    """``ranked`` with every settled ambiguous trade replaced by the arm the minute bars name.

    A bar the minute bars could not settle keeps NT8's guess, so the result is "the assumption,
    corrected where the data can correct it" rather than a different assumption.
    """
    if not aligned(ranked, worst, best):
        msg = "the three ambiguity arms are not the same trades leg for leg; a resolved log cannot be built"
        raise DisambiguationError(msg)

    resolved: pd.DataFrame = ranked.reset_index(drop=True).copy()
    if table.empty:
        return resolved

    arms = {
        AMBIGUITY_WORST_CASE: worst.reset_index(drop=True),
        AMBIGUITY_BEST_CASE: best.reset_index(drop=True),
    }
    for status, policy in ARM_FOR.items():
        settled = table.loc[table["resolved"] == status, "trade_id"]
        taking = resolved["trade_id"].isin(settled)
        if taking.any():
            resolved.loc[taking, :] = arms[policy].loc[taking, :]

    return resolved
