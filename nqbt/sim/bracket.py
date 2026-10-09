"""The bracket engine every archetype's exits go through, in one copy that must not be forked.

One stop, up to four R-multiple targets, an ambiguity policy for the bar that holds both, and a
forced exit at the session close, resolved identically for every archetype and either side. A
new archetype writes the entry half only. Each rule and its evidence: ``docs/nt8-fidelity.md``;
the design: ``nqbt/README.md`` § "sim/bracket.py".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import higher_timeframe, regime, timeofday, trend, volume
from nqbt.trades import (
    C_AMBIGUOUS,
    C_BARS_HELD,
    C_COMMISSION,
    C_DIRECTION,
    C_ENTRY_BAR,
    C_ENTRY_PRICE,
    C_EXIT_BAR,
    C_EXIT_PRICE,
    C_EXIT_REASON,
    C_GROSS_PNL,
    C_INITIAL_STOP,
    C_LEG,
    C_MAE,
    C_MFE,
    C_NET_PNL,
    C_QUANTITY,
    C_R_MULTIPLE,
    C_RISK_POINTS,
    C_TARGET_PRICE,
    C_TRADE_ID,
    EXIT_EARLY,
    EXIT_SESSION_CLOSE,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME_LIMIT,
    N_COLUMNS,
)

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IntArray, LabelArray


class Bars(NamedTuple):
    """The per-bar series every loop indexes, held together so one bar cannot be split.

    ``force_flat`` marks bars at or past the exit-on-session-close cutoff.
    """

    open_: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    force_flat: BoolArray


class Costs(NamedTuple):
    """What one contract costs to trade, and the grid its prices sit on.

    ``slippage_ticks`` is a tick count, as every NinjaScript expresses it;
    :func:`slippage_points` is the one place it becomes a price.
    """

    tick_size: float
    point_value: float
    commission_per_contract: float
    slippage_ticks: float


class FillRules(NamedTuple):
    """The three NT8 settings that decide how a price level becomes a fill.

    Each one and the evidence behind it: ``docs/nt8-fidelity.md``.
    """

    fill_limit_on_touch: bool
    ambiguity_policy: int
    round_targets: bool


class OpenTrade(NamedTuple):
    """The position as it opened -- fixed for its whole life, whatever the stop does after.

    ``filled_at_open`` is false for an entry that filled intrabar, which keeps the gapped-stop
    rule off its entry bar -- ``docs/nt8-fidelity.md``, "A stop fills at the open when the bar
    gaps through it".
    """

    trade_id: int
    entry_bar: int
    entry_price: float
    initial_stop: float
    risk: float
    direction: float
    filled_at_open: bool


class Legs(NamedTuple):
    """The three parallel per-leg arrays, one entry per leg.

    Mutated through the arrays -- ``legs.is_open[leg] = False`` -- never by rebinding, which a
    tuple would not allow.
    """

    is_open: BoolArray
    target: FloatArray
    quantity: IntArray


class Sizing(NamedTuple):
    """Each entry's per-leg sizes: every split a combination can take, and the row each bar takes.

    ``quantities`` is ``[rows, legs]``. ``row_at`` is read at the **signal** bar, whose close
    submits the order, and never at the fill bar -- ``docs/nt8-fidelity.md`` §M47.
    """

    quantities: IntArray
    row_at: IntArray


class Excursion(NamedTuple):
    """The high- and low-water marks the position has reached, which MAE and MFE come from."""

    run_high: float
    run_low: float
    high_bar: int
    """The bar :attr:`run_high` was last raised on, which the stalled exit counts from."""

    low_bar: int


class LegExit(NamedTuple):
    """Where, at what and why one leg left."""

    bar: int
    price: float
    reason: float
    ambiguous: bool


class EarlyExit(NamedTuple):
    """The conditional early exit: its thresholds and the per-bar context its one rule reads.

    Every rule is off at its default and at most one is on. A rule that reads a series is on
    exactly where that series is non-empty, and each label is the one known at that bar's close
    -- ``docs/nt8-fidelity.md``, "The conditional early exit".
    """

    at_bar: int
    at_minutes: float
    """The not-working exit's age in minutes rather than bars, measured on :attr:`clock`."""

    counter_trend_bar: int
    """The not-working exit's age in bars for a position entered against the trend, read only
    beside :attr:`at_bar` and where :attr:`trend_labels` is non-empty."""

    below_r: float
    measure: int
    """One of :data:`EARLY_EXIT_MEASURES`: what the not-working exit compares with :attr:`below_r`."""

    trend_form: int
    """Read only where :attr:`trend_labels` is non-empty."""

    only_if_losing: bool
    on_invalidation: bool
    stall_bars: int
    adverse_closes: int
    adverse_atr: float
    """The adverse move, in ATRs, one close-to-close change has to reach; read only where :attr:`atr`
    is non-empty."""

    atr_expansion: float
    """The multiple of its entry value the ATR has to exceed; read only where :attr:`atr` is non-empty."""

    give_back: float
    give_back_from_r: float
    volume_form: int
    """One of :data:`VOLUME_EXIT_FORMS`, read only where :attr:`volume_labels` is non-empty."""

    near_close: BoolArray
    regime_labels: LabelArray
    trend_labels: LabelArray
    phase_labels: LabelArray
    higher_timeframe_labels: LabelArray
    volume_labels: LabelArray
    atr: FloatArray
    clock: FloatArray
    """Each bar's timestamp in epoch seconds, read only for an age in minutes."""


TREND_EXIT_OFF = 0
TREND_EXIT_OPPOSED = 1
TREND_EXIT_NOT_WITH = 2
TREND_EXIT_FORMS = {
    TREND_EXIT_OFF: "off",
    TREND_EXIT_OPPOSED: "opposed",
    TREND_EXIT_NOT_WITH: "not_with",
}
"""Which trend labels count as against a position: the opposite trend, or that and ``MIXED``."""

TREND_MIXED = int(trend.Trend.MIXED)
"""The middle trend label, which a position's side is measured either side of."""

SIDE_AT = int(higher_timeframe.Side.AT)
"""The middle higher-timeframe side, which a position's side is measured either side of."""

VOLUME_EXIT_OFF = 0
VOLUME_EXIT_THINNED = 1
VOLUME_EXIT_HEAVY_AGAINST = 2
VOLUME_EXIT_FORMS = {
    VOLUME_EXIT_OFF: "off",
    VOLUME_EXIT_THINNED: "thinned",
    VOLUME_EXIT_HEAVY_AGAINST: "heavy_against",
}
"""Which turn in volume exits: a ``THIN`` bar after a busier entry, or a ``HEAVY`` bar closing against."""

VOLUME_THIN = int(volume.VolumeState.THIN)
VOLUME_HEAVY = int(volume.VolumeState.HEAVY)

MEASURE_OPEN_PROFIT = 0
MEASURE_EXCURSION = 1
EARLY_EXIT_MEASURES = {MEASURE_OPEN_PROFIT: "open_profit", MEASURE_EXCURSION: "excursion"}
"""What the not-working exit measures: open profit at the close, or the best favourable excursion so far."""

SECONDS_PER_MINUTE = 60.0

NO_CLOCK = np.zeros(0, dtype=np.bool_)
NO_LABELS = np.zeros(0, dtype=np.int8)
NO_SECONDS = np.zeros(0, dtype=np.float64)
NO_ATR = np.zeros(0, dtype=np.float64)
"""Stand-ins for a series the active rule never reads, which numba still needs typed."""

EARLY_EXIT_OFF = EarlyExit(
    at_bar=0,
    at_minutes=0.0,
    counter_trend_bar=0,
    below_r=0.0,
    measure=MEASURE_OPEN_PROFIT,
    trend_form=TREND_EXIT_OFF,
    only_if_losing=False,
    on_invalidation=False,
    stall_bars=0,
    adverse_closes=0,
    adverse_atr=0.0,
    atr_expansion=0.0,
    give_back=0.0,
    give_back_from_r=1.0,
    volume_form=VOLUME_EXIT_OFF,
    near_close=NO_CLOCK,
    regime_labels=NO_LABELS,
    trend_labels=NO_LABELS,
    phase_labels=NO_LABELS,
    higher_timeframe_labels=NO_LABELS,
    volume_labels=NO_LABELS,
    atr=NO_ATR,
    clock=NO_SECONDS,
)
"""Every rule off, which is every loop's default."""

NO_MARKET_EXIT = -1.0
"""What :func:`market_exit_reason` returns on a bar whose close submits no market exit; no exit
code is negative."""


class Breakeven(NamedTuple):
    """The breakeven stop: how far a position has to run before its stop moves to the entry.

    Off at an ``at`` of ``0`` -- ``docs/nt8-fidelity.md``, "The breakeven stop".
    """

    at: float
    unit: int
    """One of :data:`BREAKEVEN_UNITS`."""

    on: int
    """One of :data:`BREAKEVEN_TRIGGERS`."""

    offset_ticks: float
    atr: FloatArray
    """Read only under :data:`BREAKEVEN_ATR`."""


BREAKEVEN_R = 0
BREAKEVEN_ATR = 1
BREAKEVEN_UNITS = {BREAKEVEN_R: "r", BREAKEVEN_ATR: "atr"}
"""What the trigger distance is a multiple of: the trade's planned risk, or the ATR."""

BREAKEVEN_ON_CLOSE = 0
BREAKEVEN_ON_EXTREME = 1
BREAKEVEN_TRIGGERS = {BREAKEVEN_ON_CLOSE: "close", BREAKEVEN_ON_EXTREME: "extreme"}
"""Which price has to reach the trigger at a bar close: the close, or the bar's favourable extreme."""

BREAKEVEN_TOLERANCE = 1e-9
"""The fraction of the trigger distance a gain may round short by and still reach it; the give-back
exit's arming distance reads it too."""

BREAKEVEN_OFF = Breakeven(at=0.0, unit=BREAKEVEN_R, on=BREAKEVEN_ON_CLOSE, offset_ticks=0.0, atr=NO_ATR)
"""The breakeven stop off, which is every loop's default."""


class StopTightening(NamedTuple):
    """The stop tightening as the position ages, or as the session nears its close.

    The age stop is off at an ``age_after`` of ``0`` and the late stop where ``late_window`` is
    empty -- ``docs/nt8-fidelity.md``, "Tightening the stop with time".
    """

    age_after: float
    """The position's age at which the stop has moved all the way, in bars, or in minutes where
    :attr:`clock` is non-empty."""

    age_fraction: float
    age_shape: int
    """One of :data:`AGE_STOP_SHAPES`."""

    age_only_if_losing: bool
    clock: FloatArray
    """Each bar's timestamp in epoch seconds, read only for an age in minutes."""

    late_window: BoolArray
    late_to: int
    """One of :data:`LATE_STOP_LEVELS`."""

    late_atr_multiple: float
    late_atr: FloatArray
    """Read only under :data:`LATE_STOP_ATR`."""


AGE_STOP_STEP = 0
AGE_STOP_LINE = 1
AGE_STOP_SHAPES = {AGE_STOP_STEP: "step", AGE_STOP_LINE: "line"}
"""How the age stop moves: all at once when the age is reached, or a little at every close until then."""

LATE_STOP_ENTRY = 0
LATE_STOP_BAR_EXTREME = 1
LATE_STOP_ATR = 2
LATE_STOP_LEVELS = {LATE_STOP_ENTRY: "entry", LATE_STOP_BAR_EXTREME: "bar_extreme", LATE_STOP_ATR: "atr"}
"""Where the late stop goes: the entry, the just-closed bar's adverse extreme, or ATRs from the close."""

STOP_TIGHTENING_OFF = StopTightening(
    age_after=0.0,
    age_fraction=1.0,
    age_shape=AGE_STOP_STEP,
    age_only_if_losing=False,
    clock=NO_SECONDS,
    late_window=NO_CLOCK,
    late_to=LATE_STOP_ENTRY,
    late_atr_multiple=1.0,
    late_atr=NO_ATR,
)
"""Both off, which is every loop's default."""


@njit(cache=True)
def slippage_points(costs: Costs) -> float:
    """Convert slippage to a price, from the tick count the NinjaScript expresses it in."""
    return costs.slippage_ticks * costs.tick_size


@njit(cache=True)
def start_excursion(high: float, low: float, i: int) -> Excursion:
    """Return the water marks of a position entered on bar ``i``, which reads the whole bar."""
    return Excursion(high, low, i, i)


@njit(cache=True)
def extend_excursion(excursion: Excursion, high: float, low: float, i: int) -> Excursion:
    """Extend the water marks by bar ``i``, noting the bar each was last moved on."""
    high_bar = i if high > excursion.run_high else excursion.high_bar
    low_bar = i if low < excursion.run_low else excursion.low_bar

    return Excursion(max(excursion.run_high, high), min(excursion.run_low, low), high_bar, low_bar)


@njit(cache=True)
def resolve_brackets(  # noqa: C901, PLR0912 - one branch per NT8 exit rule, in the order they resolve
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    stop: float,
    legs: Legs,
    excursion: Excursion,
    bars: Bars,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> tuple[int, bool]:
    """Resolve bar ``i`` against the live stop and targets, closing whatever leaves.

    Returns the new write count and whether the position is still open. A write count of ``-1``
    means ``out`` overflowed and the caller must abandon the run.

    Order of resolution: the stop takes the whole position unless the ambiguity policy says the
    targets were reached first; targets fill with no slippage, at their own price or the nearest
    one the bar traded (``limit_fill_price``); anything still open after a targets-first bar leaves at
    the stop on that same bar; and force-flat is last.
    Called by both the in-position path and the entry-bar path.
    """
    n_legs = legs.is_open.size
    direction = trade.direction
    open_px = bars.open_[i]
    adverse_px, favourable_px = sided(bars.low[i], bars.high[i], direction)
    slippage = slippage_points(costs)
    # The position was held from this bar's open unless it filled intrabar on this very bar.
    held_from_bar_open = i > trade.entry_bar or trade.filled_at_open

    # The stop fills at the open when the bar gapped through it, otherwise at its own price.
    stop_fill = stop
    if held_from_bar_open and direction * open_px < direction * stop:
        stop_fill = open_px

    stop_hit = direction * adverse_px <= direction * stop
    any_target_hit = False
    nearest_target = 0.0
    for leg in range(n_legs):
        if legs.is_open[leg] and not np.isnan(legs.target[leg]):  # noqa: SIM102 - needs a continue guard; #146
            if limit_filled(favourable_px, legs.target[leg], fills.fill_limit_on_touch, direction):
                if not any_target_hit or abs(legs.target[leg] - open_px) < abs(nearest_target - open_px):
                    nearest_target = legs.target[leg]

                any_target_hit = True
    ambiguous = stop_hit and any_target_hit
    targets_first = ambiguous and targets_reached_first(open_px, stop, nearest_target, fills.ambiguity_policy)

    if stop_hit and not targets_first:
        # The whole position leaves at the stop, adverse slippage meaning a worse fill.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_STOP, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False
        return written, False

    for leg in range(n_legs):
        if legs.is_open[leg] and not np.isnan(legs.target[leg]):  # noqa: SIM102 - needs a continue guard; #146
            if limit_filled(favourable_px, legs.target[leg], fills.fill_limit_on_touch, direction):
                # Limit order: fills at its price or the nearest one the bar traded, no slippage.
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(
                        i, limit_fill_price(legs.target[leg], adverse_px, direction), EXIT_TARGET, ambiguous
                    ),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False

    if targets_first:
        # The inferred path reached the targets first and the stop on the way back,
        # so whatever is still open leaves on this same bar.
        fill = stop_fill - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_STOP, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False

    still_open = False
    for leg in range(n_legs):
        if legs.is_open[leg]:
            still_open = True
            break

    if still_open and bars.force_flat[i]:
        fill = bars.close[i] - direction * slippage
        for leg in range(n_legs):
            if legs.is_open[leg]:
                written = write_leg(
                    out,
                    written,
                    trade,
                    legs,
                    leg,
                    LegExit(i, fill, EXIT_SESSION_CLOSE, ambiguous),
                    excursion,
                    costs,
                )
                if written < 0:
                    return -1, False

                legs.is_open[leg] = False
        still_open = False

    return written, still_open


@njit(cache=True)
def flatten_position(
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    legs: Legs,
    leg_exit: LegExit,
    excursion: Excursion,
    costs: Costs,
) -> int:
    """Close every still-open leg at one price for one reason. Returns the new row count.

    The writer for a market order flattening the whole position. Not a fill rule: the caller
    decides the bar, the price and the reason.
    """
    for leg in range(legs.is_open.size):
        if not legs.is_open[leg]:
            continue

        written = write_leg(out, written, trade, legs, leg, leg_exit, excursion, costs)
        if written < 0:
            return -1

        legs.is_open[leg] = False

    return written


@njit(cache=True)
def size_legs(legs: Legs, sizing: Sizing, signal_bar: int) -> None:
    """Give every leg the size the signal bar's row names, as the entry fills."""
    row = sizing.row_at[signal_bar]
    for leg in range(legs.quantity.size):
        legs.quantity[leg] = sizing.quantities[row, leg]


@njit(cache=True)
def hold_expired(entry_bar: int, i: int, max_hold_bars: int) -> bool:
    """Return whether bar ``i``'s close is where the maximum-hold-time exit is submitted.

    Off at ``0``. The order goes in at the close of bar ``entry_bar + max_hold_bars`` and fills
    at the next bar's open -- ``docs/nt8-fidelity.md``, "The maximum hold time, and why it is its
    own exit code".
    """
    return max_hold_bars > 0 and i - entry_bar >= max_hold_bars


@njit(cache=True)
def early_exit_due(rule: EarlyExit, trade: OpenTrade, bars: Bars, excursion: Excursion, i: int) -> bool:
    """Return whether bar ``i``'s close is where the conditional early exit is submitted.

    Off at :data:`EARLY_EXIT_OFF`. ``excursion`` includes bar ``i``. A position is losing when
    the close is strictly worse than its entry price, and the order fills at the next bar's open
    -- ``docs/nt8-fidelity.md``, "The conditional early exit".
    """
    close = float(bars.close[i])
    losing = trade.direction * (close - trade.entry_price) < 0.0
    if rule.at_bar > 0 or rule.at_minutes > 0.0:
        at_bar = not_working_bar(rule, trade)
        return reached_age(at_bar, rule.at_minutes, rule.clock, trade.entry_bar, i) and not_working(
            rule, trade, excursion, close
        )

    if rule.near_close.size > 0 or rule.phase_labels.size > 0 or rule.atr_expansion > 0.0:
        return losing and losing_exit_holds(rule, trade.entry_bar - 1, i)

    if rule.only_if_losing and not losing:
        return False

    if rule.stall_bars > 0 or rule.adverse_closes > 0 or rule.adverse_atr > 0.0 or rule.give_back > 0.0:
        return price_failed(rule, trade, bars, excursion, i)

    at_entry = trade.entry_bar - 1
    if at_entry < 0:
        return False

    return turned_against(rule, trade, bars, at_entry, i)


@njit(cache=True)
def turned_against(rule: EarlyExit, trade: OpenTrade, bars: Bars, at_entry: int, i: int) -> bool:
    """Return whether the invalidation exit or a label exit, whichever is on, fires at bar ``i``'s close."""
    if rule.on_invalidation:
        return closed_beyond(bars, at_entry, i, trade.direction)

    if rule.regime_labels.size > 0:
        return regime_changed(rule.regime_labels, at_entry, i)

    if rule.trend_form != TREND_EXIT_OFF and rule.trend_labels.size > 0:
        return trend_turned(rule.trend_labels, at_entry, i, trade.direction, rule.trend_form)

    if rule.higher_timeframe_labels.size > 0:
        return side_turned(rule.higher_timeframe_labels, at_entry, i, trade.direction)

    if rule.volume_labels.size > 0:
        return volume_turned(rule, bars, at_entry, i, trade.direction)

    return False


@njit(cache=True)
def losing_exit_holds(rule: EarlyExit, at_entry: int, i: int) -> bool:
    """Return whether the window, phase or volatility exit, which all need a loss, holds at bar ``i``."""
    if rule.near_close.size > 0:
        return bool(rule.near_close[i])

    if at_entry < 0:
        return False

    if rule.phase_labels.size > 0:
        return phase_left(rule.phase_labels, at_entry, i)

    return volatility_expanded(rule.atr, rule.atr_expansion, at_entry, i)


@njit(cache=True)
def price_failed(rule: EarlyExit, trade: OpenTrade, bars: Bars, excursion: Excursion, i: int) -> bool:
    """Return whether the stalled, adverse-move or give-back exit, whichever is on, fires at bar ``i``."""
    if rule.stall_bars > 0:
        return stalled(excursion, trade.direction, i, rule.stall_bars)

    if rule.adverse_closes > 0:
        return closes_against(bars, trade, i, rule.adverse_closes)

    if rule.adverse_atr > 0.0:
        return moved_against(bars, rule.atr, rule.adverse_atr, trade, i)

    return gave_back(rule, trade, excursion, float(bars.close[i]))


@njit(cache=True)
def not_working_bar(rule: EarlyExit, trade: OpenTrade) -> int:
    """Return the bar the not-working exit tests a position at: the shorter one if entered against the trend.

    Against is the opposite trend on the bar before the entry bar; an undefined label is against nothing.
    """
    at_entry = trade.entry_bar - 1
    if rule.counter_trend_bar == 0 or at_entry < 0 or at_entry >= rule.trend_labels.size:
        return rule.at_bar

    if trend_against(int(rule.trend_labels[at_entry]), trade.direction, TREND_EXIT_OPPOSED):
        return rule.counter_trend_bar

    return rule.at_bar


@njit(cache=True)
def reached_age(at_bar: int, at_minutes: float, clock: FloatArray, entry_bar: int, i: int) -> bool:
    """Return whether bar ``i``'s close is the one a rule tested at a single age is tested at.

    In bars, the close ``at_bar`` bars after the entry bar's; in minutes, the first close at
    least ``at_minutes`` after the entry bar's, timed on ``clock``.
    """
    if at_bar > 0:
        return i - entry_bar == at_bar

    horizon = at_minutes * SECONDS_PER_MINUTE
    if float(clock[i] - clock[entry_bar]) < horizon:
        return False

    return float(clock[i - 1] - clock[entry_bar]) < horizon


@njit(cache=True)
def not_working(rule: EarlyExit, trade: OpenTrade, excursion: Excursion, close: float) -> bool:
    """Return whether the position is below the not-working exit's threshold, in R, on its measure."""
    reached = close
    if rule.measure == MEASURE_EXCURSION:
        _, reached = sided(excursion.run_low, excursion.run_high, trade.direction)

    return trade.direction * (reached - trade.entry_price) < rule.below_r * trade.risk


@njit(cache=True)
def closed_beyond(bars: Bars, at_entry: int, i: int, direction: float) -> bool:
    """Return whether bar ``i`` closed strictly beyond the adverse extreme of bar ``at_entry``."""
    adverse, _ = sided(bars.low[at_entry], bars.high[at_entry], direction)

    return direction * (float(bars.close[i]) - adverse) < 0.0


@njit(cache=True)
def market_exit_reason(
    trade: OpenTrade,
    bars: Bars,
    excursion: Excursion,
    i: int,
    max_hold_bars: int,
    early_exit: EarlyExit,
) -> float:
    """Return the exit code of the market exit bar ``i``'s close submits, or :data:`NO_MARKET_EXIT`.

    The hold cap takes a bar both it and the early exit would leave on. An archetype's own
    signal exit is decided before either -- ``docs/nt8-fidelity.md``, "The conditional early exit".
    """
    if hold_expired(trade.entry_bar, i, max_hold_bars):
        return EXIT_TIME_LIMIT

    if early_exit_due(early_exit, trade, bars, excursion, i):
        return EXIT_EARLY

    return NO_MARKET_EXIT


@njit(cache=True)
def regime_changed(labels: LabelArray, at_entry: int, i: int) -> bool:
    """Return whether bar ``i``'s regime label differs from the one at entry; an undefined one never does."""
    entry = int(labels[at_entry])
    now = int(labels[i])
    if regime.UNDEFINED in (entry, now):
        return False

    return now != entry


@njit(cache=True)
def trend_against(label: int, direction: float, form: int) -> bool:
    """Return whether a trend label is against a position on ``direction``, in the form ``form`` names.

    ``form`` is one of :data:`TREND_EXIT_FORMS`, and an undefined label is against nothing.
    """
    if label == trend.UNDEFINED:
        return False

    lean = direction * (label - TREND_MIXED)
    if form == TREND_EXIT_OPPOSED:
        return lean < 0.0

    return lean <= 0.0


@njit(cache=True)
def trend_turned(labels: LabelArray, at_entry: int, i: int, direction: float, form: int) -> bool:
    """Return whether bar ``i``'s trend label is against the position when the one at entry was not.

    An undefined label at entry never turns.
    """
    entry = int(labels[at_entry])
    if entry == trend.UNDEFINED:
        return False

    return trend_against(int(labels[i]), direction, form) and not trend_against(entry, direction, form)


@njit(cache=True)
def side_against(label: int, direction: float) -> bool:
    """Return whether a higher-timeframe side is the far side of the average from a position on ``direction``.

    An undefined side is against nothing.
    """
    if label == higher_timeframe.UNDEFINED:
        return False

    return direction * (label - SIDE_AT) < 0.0


@njit(cache=True)
def side_turned(labels: LabelArray, at_entry: int, i: int, direction: float) -> bool:
    """Return whether bar ``i``'s higher-timeframe side is against the position when the one at entry was not.

    An undefined side at entry never turns.
    """
    entry = int(labels[at_entry])
    if entry == higher_timeframe.UNDEFINED:
        return False

    return side_against(int(labels[i]), direction) and not side_against(entry, direction)


@njit(cache=True)
def volume_turned(rule: EarlyExit, bars: Bars, at_entry: int, i: int, direction: float) -> bool:
    """Return whether bar ``i``'s volume turned in :attr:`EarlyExit.volume_form`'s sense.

    Thinned is a ``THIN`` bar after an entry that was not; heavy against is a ``HEAVY`` bar whose
    close is strictly worse than its open. An undefined label never turns.
    """
    now = int(rule.volume_labels[i])
    if rule.volume_form == VOLUME_EXIT_HEAVY_AGAINST:
        return now == VOLUME_HEAVY and direction * (bars.close[i] - bars.open_[i]) < 0.0

    entry = int(rule.volume_labels[at_entry])

    return now == VOLUME_THIN and entry not in (VOLUME_THIN, volume.UNDEFINED)


@njit(cache=True)
def phase_left(labels: LabelArray, at_entry: int, i: int) -> bool:
    """Return whether bar ``i``'s session phase differs from the entry's; one outside a session never does."""
    entry = int(labels[at_entry])
    now = int(labels[i])
    if timeofday.OUT_OF_SESSION in (entry, now):
        return False

    return now != entry


@njit(cache=True)
def volatility_expanded(atr: FloatArray, multiple: float, at_entry: int, i: int) -> bool:
    """Return whether bar ``i``'s ATR is above ``multiple`` of the one at entry; a warming-up one never is."""
    if i >= atr.size:
        return False

    return float(atr[i]) > multiple * float(atr[at_entry])


@njit(cache=True)
def stalled(excursion: Excursion, direction: float, i: int, stall_bars: int) -> bool:
    """Return whether the best price has not improved over the ``stall_bars`` closes up to bar ``i``."""
    _, improved_at = sided(float(excursion.low_bar), float(excursion.high_bar), direction)

    return i - improved_at >= stall_bars


@njit(cache=True)
def closes_against(bars: Bars, trade: OpenTrade, i: int, count: int) -> bool:
    """Return whether each of the ``count`` closes up to bar ``i`` was strictly worse than the one before.

    Only closes the position was open for count, so the first one compared against is the entry bar's.
    """
    if i - count < trade.entry_bar:
        return False

    for j in range(i - count + 1, i + 1):
        if trade.direction * (bars.close[j] - bars.close[j - 1]) >= 0.0:
            return False

    return True


@njit(cache=True)
def moved_against(bars: Bars, atr: FloatArray, multiple: float, trade: OpenTrade, i: int) -> bool:
    """Return whether bar ``i`` closed worse than the bar before by at least ``multiple`` of that bar's ATR.

    Both closes have to be ones the position was open for, and an ATR still warming up names nothing.
    """
    if i <= trade.entry_bar or i > atr.size:
        return False

    return trade.direction * float(bars.close[i] - bars.close[i - 1]) <= -multiple * float(atr[i - 1])


@njit(cache=True)
def gave_back(rule: EarlyExit, trade: OpenTrade, excursion: Excursion, close: float) -> bool:
    """Return whether the close has given back :attr:`EarlyExit.give_back` of the best excursion.

    Armed only once that excursion reached :attr:`EarlyExit.give_back_from_r` R, within
    :data:`BREAKEVEN_TOLERANCE`.
    """
    _, best = sided(excursion.run_low, excursion.run_high, trade.direction)
    peak = trade.direction * (best - trade.entry_price)
    if peak < rule.give_back_from_r * trade.risk * (1.0 - BREAKEVEN_TOLERANCE):
        return False

    return trade.direction * (close - trade.entry_price) <= (1.0 - rule.give_back) * peak


@njit(cache=True)
def entry_bracket(
    high: float,
    low: float,
    close: float,
    entry_offset: float,
    stop_offset: float,
    direction: float,
) -> tuple[float, float, float]:
    """Compute one signal bar's order arithmetic: trigger, initial stop, planned risk.

    The trigger is the *favourable* side of the signal bar, capped by whichever of it and
    ``close +/- entry_offset`` is further favourable still; the stop sits ``stop_offset``
    beyond the *adverse* side. ``direction`` is ``+1.0`` long / ``-1.0`` short.

    Shared by the jitted loop and by ``explain.py`` -- ``docs/roadmap.md`` §M20a.
    """
    adverse, favourable = sided(low, high, direction)
    close_based = close + direction * entry_offset
    trigger = favourable
    if direction * close_based > direction * trigger:
        trigger = close_based

    stop = adverse - direction * stop_offset
    risk = direction * (trigger - stop)

    return trigger, stop, risk


@njit(cache=True)
def stop_entry_fill(
    bars: Bars,
    i: int,
    trigger: float,
    slippage: float,
    direction: float,
) -> tuple[bool, float]:
    """Return whether a resting stop-market entry fills on bar ``i``, and at what price.

    A market order once triggered, so a gap through the trigger fills at the open; otherwise the
    bar's favourable extreme has to reach it and the fill is the trigger. Shared by OpeningRange's
    stop entries and EmaPullback's confirmation entry -- ``docs/nt8-fidelity.md``, "Fill".
    """
    if direction * bars.open_[i] >= direction * trigger:
        return True, bars.open_[i] + direction * slippage

    _, touch = sided(bars.low[i], bars.high[i], direction)
    if direction * touch >= direction * trigger:
        return True, trigger + direction * slippage

    return False, 0.0


NO_BRACKET_FLOOR = 0.0
"""The floor value that switches :func:`atr_bracket_distance` off, which every port passes."""


@njit(cache=True)
def atr_bracket_distance(atr_value: float, multiple: float, floor_points: float) -> float:
    """Return how far an ATR multiple puts a bracket level from what it is measured against.

    ``floor_points`` is a per-contract dollar floor already converted on the instrument by
    :meth:`nqbt.instruments.Instrument.dollars_to_points`, and :data:`NO_BRACKET_FLOOR`
    switches it off. The one ATR sizing in the codebase -- ``docs/roadmap.md`` § "ATR-multiple
    brackets and the dollar floor".
    """
    return max(atr_value * multiple, floor_points)


@njit(cache=True)
def swing_stop(
    bars: Bars,
    signal_bar: int,
    lookback: int,
    offset: float,
    direction: float,
) -> float:
    """Return a structural stop: the adverse extreme of the last ``lookback`` completed bars, offset.

    The window ends at ``signal_bar`` and includes it. ``offset`` is a price rather than a tick
    count, and pushes the stop *beyond* the extreme. Not floored. Shared by EmaCrossover's swing
    mode and ElasticBand's :data:`~nqbt.sim.types.STOP_SWING`.
    """
    start = signal_bar - lookback + 1
    start = max(start, 0)
    extreme = 0.0
    for j in range(start, signal_bar + 1):
        adverse, _ = sided(bars.low[j], bars.high[j], direction)
        if j == start or direction * adverse < direction * extreme:
            extreme = adverse

    return extreme - direction * offset


@njit(cache=True)
def tightened_stop(stop: float, candidate: float, direction: float) -> float:
    """Return whichever of the two is nearer the market, which is the one ratchet in the codebase.

    A ``nan`` candidate leaves the stop alone -- ``docs/nt8-fidelity.md``, "Ratchet reads the
    just-closed bar".
    """
    if direction * candidate > direction * stop:
        return candidate

    return stop


@njit(cache=True)
def breakeven_level(
    rule: Breakeven,
    trade: OpenTrade,
    bars: Bars,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> float:
    """Return the level bar ``i``'s close moves the stop to under the breakeven rule, or ``nan``.

    ``nan`` where the rule is off, the trigger was not reached within :data:`BREAKEVEN_TOLERANCE`, or
    the level is at or through the close. Pass the result to :func:`tightened_stop`, which never
    loosens -- ``docs/nt8-fidelity.md``, "The breakeven stop".
    """
    if rule.at <= 0.0:
        return np.nan

    direction = trade.direction
    distance = rule.at * trade.risk
    if rule.unit == BREAKEVEN_ATR:
        at_entry = trade.entry_bar - 1
        if at_entry < 0 or at_entry >= rule.atr.size:
            return np.nan

        distance = rule.at * rule.atr[at_entry]

    reached = bars.close[i]
    if rule.on == BREAKEVEN_ON_EXTREME:
        _, reached = sided(bars.low[i], bars.high[i], direction)

    gain = direction * (reached - trade.entry_price)
    if np.isnan(distance) or gain < distance * (1.0 - BREAKEVEN_TOLERANCE):
        return np.nan

    level = trade.entry_price + direction * rule.offset_ticks * costs.tick_size

    return submittable_stop(level, bars.close[i], direction, costs, fills)


@njit(cache=True)
def submittable_stop(level: float, close: float, direction: float, costs: Costs, fills: FillRules) -> float:
    """Return a stop level snapped to the tick wherever targets are, or ``nan`` at or through ``close``.

    §M18's rule that a stop at or through the price it protects is not a stop order --
    ``docs/nt8-fidelity.md``, "The breakeven stop".
    """
    if fills.round_targets:
        level = round_to_tick(level, costs.tick_size)

    if direction * (close - level) <= 0.0:
        return np.nan

    return level


@njit(cache=True)
def tightening_level(
    rule: StopTightening,
    trade: OpenTrade,
    initial_stop: float,
    bars: Bars,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> float:
    """Return the level bar ``i``'s close tightens the stop to with time, or ``nan``.

    The nearer the market of the age stop's level and the late stop's. ``initial_stop`` is the
    stop the age stop moves from, which is per lot where lots differ. Pass the result to
    :func:`tightened_stop`, which never loosens -- ``docs/nt8-fidelity.md``, "Tightening the stop
    with time".
    """
    aged = age_stop_level(rule, trade, initial_stop, bars.close[i], i, costs, fills)
    late = late_stop_level(rule, trade, bars, i, costs, fills)
    if np.isnan(aged):
        return late

    return tightened_stop(aged, late, trade.direction)


@njit(cache=True)
def age_stop_level(
    rule: StopTightening,
    trade: OpenTrade,
    initial_stop: float,
    close: float,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> float:
    """Return the age stop's level at bar ``i``'s close, part of the way from ``initial_stop`` to the entry.

    The part is ``age_fraction``, scaled by the age under the line shape. ``nan`` where the rule
    is off, the step has not been reached, the line is at age 0, the position is not losing under
    ``age_only_if_losing``, or the level is at or through the close.
    """
    if rule.age_after <= 0.0:
        return np.nan

    direction = trade.direction
    if rule.age_only_if_losing and direction * (close - trade.entry_price) >= 0.0:
        return np.nan

    age = float(i - trade.entry_bar)
    horizon = rule.age_after
    if rule.clock.size > 0:
        age = rule.clock[i] - rule.clock[trade.entry_bar]
        horizon = rule.age_after * SECONDS_PER_MINUTE

    progress = min(age / horizon, 1.0)
    if rule.age_shape == AGE_STOP_STEP:
        if age < horizon:
            return np.nan

        progress = 1.0

    if progress <= 0.0:
        return np.nan

    level = initial_stop + rule.age_fraction * progress * (trade.entry_price - initial_stop)

    return submittable_stop(level, close, direction, costs, fills)


@njit(cache=True)
def late_stop_level(
    rule: StopTightening,
    trade: OpenTrade,
    bars: Bars,
    i: int,
    costs: Costs,
    fills: FillRules,
) -> float:
    """Return the late stop's level at bar ``i``'s close, or ``nan`` outside its window or past the close."""
    if rule.late_window.size == 0 or not rule.late_window[i]:
        return np.nan

    direction = trade.direction
    close = float(bars.close[i])
    level = trade.entry_price
    if rule.late_to == LATE_STOP_BAR_EXTREME:
        level, _ = sided(bars.low[i], bars.high[i], direction)
    elif rule.late_to == LATE_STOP_ATR:
        level = close - direction * rule.late_atr_multiple * rule.late_atr[i]

    return submittable_stop(level, close, direction, costs, fills)


@njit(cache=True)
def avoid_round_number(
    stop: float,
    spacing: float,
    offset: float,
    tick_size: float,
    direction: float,
) -> float:
    """Push a stop that lands exactly on a multiple of ``spacing`` further from the entry.

    ``spacing`` is a price -- 25 points, say -- and a spacing of ``0`` switches the rule off.
    Only an exact landing moves. Meaningless on a back-adjusted series -- ``docs/roadmap.md``
    § "The build spec's three loose ends".
    """
    if spacing <= 0.0:
        return stop

    remainder = stop - spacing * np.floor(stop / spacing + 0.5)
    if abs(remainder) >= 0.5 * tick_size:
        return stop

    return stop - direction * offset


@njit(cache=True)
def sided(low: float, high: float, direction: float) -> tuple[float, float]:
    """Return which raw price is adverse and which is favourable for this direction."""
    if direction > 0.0:
        return low, high

    return high, low


AMBIGUITY_WORST_CASE = 0
AMBIGUITY_NEAREST_TO_OPEN = 1
AMBIGUITY_BEST_CASE = 2
"""NT8's guess, and the two outcomes it is guessing between.

Only ``AMBIGUITY_NEAREST_TO_OPEN`` reproduces NT8, and it is the only one anything is ranked on;
the other two are for ``nqbt/disambiguate.py`` -- ``docs/roadmap.md`` §M28.4."""


@njit(cache=True)
def targets_reached_first(open_px: float, stop_px: float, target_px: float, policy: int) -> bool:
    """Return whether price reached the target first, on a bar holding both the stop and a target.

    ``AMBIGUITY_NEAREST_TO_OPEN`` reproduces NT8; the other two answer always-no and always-yes
    -- ``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the open".
    """
    if policy == AMBIGUITY_NEAREST_TO_OPEN:
        return abs(open_px - target_px) < abs(stop_px - open_px)

    return policy == AMBIGUITY_BEST_CASE


@njit(cache=True)
def limit_filled(favourable_px: float, limit: float, on_touch: bool, direction: float) -> bool:
    """Return whether a limit order at ``limit`` fills, given the bar's favourable-side extreme.

    Unless ``on_touch``, price has to trade through the limit -- ``docs/nt8-fidelity.md``, "Limit
    orders must trade *through*, not touch".
    """
    if on_touch:
        return direction * favourable_px >= direction * limit

    return direction * favourable_px > direction * limit


@njit(cache=True)
def limit_fill_price(limit: float, near_px: float, direction: float) -> float:
    """Return the price a filled limit order fills at: its own, or the bar's extreme nearest it.

    ``direction`` is read as :func:`limit_filled` reads it, and ``near_px`` is the bar's other
    extreme, its low for a sell limit and its high for a buy limit -- ``docs/nt8-fidelity.md``, "A
    limit order the market has passed fills at the nearest price the bar traded".
    """
    if direction * near_px > direction * limit:
        return near_px

    return limit


@njit(cache=True)
def round_to_tick(price: float, tick_size: float) -> float:
    """Snap a price onto the tick grid, as ``RoundToTickSize`` does in NinjaScript."""
    return float(np.floor(price / tick_size + 0.5) * tick_size)


REWARD_RISK_TOLERANCE = 1e-9
"""The fraction of the minimum a scaled R multiple may round short by and still pass the gate."""


@njit(cache=True)
def passes_reward_risk(target_r: FloatArray, tp_multiplier: float, minimum: float) -> bool:
    """Check the optional pre-trade gate on the furthest target's R multiple, off at ``minimum`` of 0.

    Each multiple is scaled by ``tp_multiplier``, as the targets are, and compared within
    :data:`REWARD_RISK_TOLERANCE` -- ``docs/nt8-fidelity.md``, "The reward-to-risk gate has no
    NinjaScript behind it". Every target is in R, so the check passes for the whole rule set or
    for none of it.
    """
    if minimum <= 0.0:
        return True

    best = 0.0
    for k in range(target_r.size):
        scaled = target_r[k] * tp_multiplier
        if not np.isnan(scaled) and scaled > best:
            best = scaled

    return best >= minimum * (1.0 - REWARD_RISK_TOLERANCE)


@njit(cache=True)
def write_leg(
    out: FloatArray,
    written: int,
    trade: OpenTrade,
    legs: Legs,
    leg: int,
    leg_exit: LegExit,
    excursion: Excursion,
    costs: Costs,
) -> int:
    """Append one leg exit. Returns the new row count, or -1 if ``out`` is full."""
    if written >= out.shape[0]:
        return -1

    direction = trade.direction
    quantity = legs.quantity[leg]
    # Positive when the trade made money, whichever side it was on.
    pnl_per_unit = (leg_exit.price - trade.entry_price) * direction
    gross = pnl_per_unit * quantity * costs.point_value
    commission = costs.commission_per_contract * quantity
    net = gross - commission

    out[written, C_TRADE_ID] = trade.trade_id
    out[written, C_LEG] = leg + 1
    out[written, C_ENTRY_BAR] = trade.entry_bar
    out[written, C_EXIT_BAR] = leg_exit.bar
    out[written, C_ENTRY_PRICE] = trade.entry_price
    out[written, C_EXIT_PRICE] = leg_exit.price
    out[written, C_INITIAL_STOP] = trade.initial_stop
    out[written, C_TARGET_PRICE] = legs.target[leg]
    out[written, C_QUANTITY] = quantity
    out[written, C_DIRECTION] = direction
    out[written, C_EXIT_REASON] = leg_exit.reason
    out[written, C_GROSS_PNL] = gross
    out[written, C_COMMISSION] = commission
    out[written, C_NET_PNL] = net
    out[written, C_R_MULTIPLE] = pnl_per_unit / trade.risk if trade.risk > 0.0 else np.nan
    out[written, C_RISK_POINTS] = trade.risk
    # run_high/run_low are tracked regardless of direction, so the adverse one is whichever
    # term is larger; the other is negative or smaller by construction.
    out[written, C_MAE] = max(
        direction * (trade.entry_price - excursion.run_high),
        direction * (trade.entry_price - excursion.run_low),
    )
    out[written, C_MFE] = max(
        direction * (excursion.run_high - trade.entry_price),
        direction * (excursion.run_low - trade.entry_price),
    )
    out[written, C_BARS_HELD] = leg_exit.bar - trade.entry_bar
    out[written, C_AMBIGUOUS] = 1.0 if leg_exit.ambiguous else 0.0

    return written + 1


def fixed_sizing(leg_quantities: tuple[int, ...], n_bars: int) -> Sizing:
    """Return one split for every entry: what each NinjaScript does, and every loop with sizing off."""
    return Sizing(np.asarray([leg_quantities], dtype=np.int64), np.zeros(n_bars, dtype=np.int64))


def allocate_output(n_signals: int, n_legs: int = 4) -> FloatArray:
    """Preallocate the result matrix.

    Every filled signal writes at most one row per leg, and fills can only be fewer than
    signals, so ``n_signals * n_legs`` is a safe upper bound.
    """
    return np.zeros((max(int(n_signals) * n_legs, 1), N_COLUMNS), dtype=np.float64)
