"""The noise area: a band around the cash open, as wide as the move from the open usually is by then.

Zarattini, Aziz and Barbon's intraday-momentum band, in the coordinate system :mod:`nqbt.bands`
uses, so ElasticBand reads it as a third band source. Its rules and the NinjaScript each would
become: ``docs/nt8-fidelity.md``, "The noise area".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import indicators, sessionrange, timeofday, volume

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BoolArray, FloatArray, IntArray

__all__ = [
    "CASH_CLOSE_MINUTES",
    "CASH_OPEN_MINUTES",
    "DECISION_MINUTES",
    "LAST_ENTRY_MINUTES",
    "MIN_LOOKBACK_SESSIONS",
    "NoiseBand",
    "NoiseBandGrid",
    "NoiseError",
    "noise_band_grid",
    "noise_stretch",
    "validate_lookback",
]

CASH_OPEN_MINUTES = sessionrange.CASH_OPEN_MINUTES
"""Minutes past the session open the cash session opens at, where the band is anchored."""

CASH_CLOSE_MINUTES = sessionrange.anchor_for(timeofday.SessionPhase.CLOSE)
"""Minutes past the session open the cash session closes at, which the previous close is read at."""

DECISION_MINUTES = 30
"""The paper's decision cadence: the closes on the half hour."""

LAST_ENTRY_MINUTES = CASH_CLOSE_MINUTES - DECISION_MINUTES
"""Minutes past the session open of the last close an entry off the noise area is decided on: the
last decision before the cash close."""

CASH_MARKS = math.gcd(CASH_OPEN_MINUTES, LAST_ENTRY_MINUTES, CASH_CLOSE_MINUTES)
"""Every bar size the band can be read at divides this, so a bar opens or closes on each mark."""

MIN_LOOKBACK_SESSIONS = volume.MIN_BASELINE_SESSIONS
"""Fewest prior sessions the width may be averaged over, and the observations a bar's average must hold."""


class NoiseError(ValueError):
    """Raised for a lookback too short to average anything, or bars that cannot open at the cash open."""


def validate_lookback(sessions: int) -> int:
    """Reject a lookback shorter than :data:`MIN_LOOKBACK_SESSIONS`."""
    if sessions < MIN_LOOKBACK_SESSIONS:
        msg: str = f"the noise band's lookback must span >= {MIN_LOOKBACK_SESSIONS} sessions, got {sessions}"
        raise NoiseError(msg)

    return sessions


@dataclass(frozen=True, slots=True)
class NoiseBand:
    """One lookback's band: its two anchors, its width and where each close sits against them."""

    upper_anchor: FloatArray
    """The higher of the session's cash open and the previous session's cash close, ``nan``
    outside the cash session or on a session with no bar at the open."""
    lower_anchor: FloatArray
    """The lower of the two, ``nan`` where the upper one is."""
    width: FloatArray
    """The mean absolute move from the cash open, as a share of it, at this bar of session over
    the prior sessions: the band's half-width at ``k=1`` as a fraction of its anchor."""
    stretch: FloatArray
    """Signed extension in widths past the nearer anchor: ``0`` between the anchors, ``nan``
    where there is no band."""
    basis: FloatArray
    """The anchor a close is measured from: the lower one below it, the upper one otherwise."""
    stddev: FloatArray
    """That anchor times the width, the band's half-width at ``k=1`` in price."""
    side: FloatArray
    """What a bar's side is read off: the stretch, or between the anchors the close less their
    midpoint."""

    def __len__(self) -> int:
        return int(self.stretch.size)

    @property
    def nbytes(self) -> int:
        """Bytes the band occupies -- what a parallel worker is handed."""
        return sum(series.nbytes for series in self.series())

    def series(self) -> tuple[FloatArray, ...]:
        """Return every per-bar series the band holds."""
        return (
            self.upper_anchor,
            self.lower_anchor,
            self.width,
            self.stretch,
            self.basis,
            self.stddev,
            self.side,
        )


@dataclass(frozen=True, slots=True)
class NoiseBandGrid:
    """The band at every lookback a sweep needs, and the VWAP anchored where they are."""

    bands: dict[int, NoiseBand]
    vwap: FloatArray
    """The volume-weighted average price from the cash open, ``nan`` where there is no band."""

    def band(self, lookback: int) -> NoiseBand:
        """Return one lookback's band, or raise an error naming what the grid was built for."""
        if lookback not in self.bands:
            msg: str = f"noise lookback {lookback} is not in this grid; built for {sorted(self.bands)}"
            raise KeyError(msg)

        return self.bands[lookback]

    @property
    def nbytes(self) -> int:
        """Bytes the grid occupies -- what a parallel worker is handed. The lookbacks share their anchors."""
        held: dict[int, FloatArray] = {id(self.vwap): self.vwap}
        for band in self.bands.values():
            held |= {id(series): series for series in band.series()}

        return sum(series.nbytes for series in held.values())


class _Anchors(NamedTuple):
    """Each session's cash open and cash close, and the contract each was read on."""

    cash_open: FloatArray
    cash_close: FloatArray
    open_contract: IntArray
    close_contract: IntArray


@njit(cache=True)
def _session_anchors(
    open_: FloatArray,
    close: FloatArray,
    contract: IntArray,
    session_id: IntArray,
    body_start: IntArray,
    bar_minutes: int,
    n_sessions: int,
) -> _Anchors:
    """Return each session's cash open and cash close, and the contract each was read on.

    The open is the bar whose body starts at the cash open, so a session joined after it has
    none. The close is the last cash bar whose body ends by the cash close.
    """
    cash_open = np.full(n_sessions, np.nan, dtype=np.float64)
    cash_close = np.full(n_sessions, np.nan, dtype=np.float64)
    open_contract = np.full(n_sessions, -1, dtype=np.int64)
    close_contract = np.full(n_sessions, -1, dtype=np.int64)
    for i in range(open_.size):
        session = session_id[i]
        if session < 0 or body_start[i] < CASH_OPEN_MINUTES:
            continue

        if body_start[i] == CASH_OPEN_MINUTES:
            cash_open[session] = open_[i]
            open_contract[session] = contract[i]

        if body_start[i] + bar_minutes <= CASH_CLOSE_MINUTES:
            cash_close[session] = close[i]
            close_contract[session] = contract[i]

    return _Anchors(cash_open, cash_close, open_contract, close_contract)


@njit(cache=True)
def _trailing_means(grid: FloatArray, window: int, min_observations: int) -> FloatArray:
    """Return, per cell, the mean of its column over the ``window`` sessions before its row, summed afresh."""
    n_sessions, n_indices = grid.shape
    means = np.full((n_sessions, n_indices), np.nan, dtype=np.float64)
    for session in range(n_sessions):
        first = max(0, session - window)
        for index in range(n_indices):
            total = 0.0
            held = 0
            for prior in range(first, session):
                value = grid[prior, index]
                if not np.isnan(value):
                    total += value
                    held += 1

            if held >= min_observations:
                means[session, index] = total / held

    return means


def noise_stretch(close: FloatArray, upper: FloatArray, lower: FloatArray, width: FloatArray) -> FloatArray:
    """Return each close's signed extension in widths past the nearer anchor.

    ``0`` between the anchors, where a gap leaves room, and ``nan`` where any input is missing or
    the width is not positive.
    """
    defined: BoolArray = np.isfinite(upper) & np.isfinite(lower) & (width > 0.0)
    safe_upper: FloatArray = np.where(defined, upper, 1.0)
    safe_lower: FloatArray = np.where(defined, lower, 1.0)
    safe_width: FloatArray = np.where(defined, width, 1.0)
    above: FloatArray = (close - safe_upper) / (safe_upper * safe_width)
    below: FloatArray = (close - safe_lower) / (safe_lower * safe_width)
    stretch: FloatArray = np.where(close > safe_upper, above, np.where(close < safe_lower, below, 0.0))

    return np.where(defined, stretch, np.nan)


def _cash_vwap(
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    traded: FloatArray,
    anchor_bar: BoolArray,
    anchored: BoolArray,
) -> FloatArray:
    """Return the VWAP from each session's cash open, ``nan`` outside an anchored cash session."""
    typical: FloatArray = indicators.typical_price(high, low, close)
    vwap: FloatArray = indicators.session_vwap(
        typical, np.ascontiguousarray(traded, dtype=np.float64), anchor_bar
    )

    return np.where(anchored, vwap, np.nan)


def noise_band_grid(
    open_: FloatArray,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    traded: FloatArray,
    contract: IntArray,
    session_id: IntArray,
    clock: timeofday.TimeOfDay,
    lookbacks: Iterable[int],
) -> NoiseBandGrid:
    """Compute the band once per lookback, and the VWAP from the cash open, over the whole series.

    ``contract`` codes each bar's contract, so a previous close read on another contract is
    dropped -- ``docs/nt8-fidelity.md``, "The noise area". ``session_id`` is
    :func:`nqbt.volume.session_ids`'s and ``clock`` the dataset's own. Bars that miss the cash
    session's marks are refused.
    """
    if CASH_MARKS % clock.bar_minutes:
        msg: str = (
            f"{clock.bar_minutes}-minute bars do not open at 09:30 and close at 15:30 and 16:00 ET, "
            "so the noise area has no anchor to read"
        )
        raise NoiseError(msg)

    wanted: list[int] = sorted({validate_lookback(int(lookback)) for lookback in lookbacks})
    sessions: IntArray = np.ascontiguousarray(session_id, dtype=np.int64)
    bar_of_session: IntArray = np.ascontiguousarray(clock.bar_of_session, dtype=np.int64)
    body_start: IntArray = np.where(bar_of_session >= 0, bar_of_session * clock.bar_minutes, -1)
    n_sessions: int = int(sessions.max()) + 1 if sessions.size and sessions.max() >= 0 else 0
    n_indices: int = int(bar_of_session.max()) + 1 if bar_of_session.size and bar_of_session.max() >= 0 else 0
    if n_sessions == 0 or n_indices == 0:
        empty: FloatArray = np.full(close.size, np.nan, dtype=np.float64)

        return NoiseBandGrid(dict.fromkeys(wanted, NoiseBand(*(empty,) * 7)), empty)

    anchors: _Anchors = _session_anchors(
        np.ascontiguousarray(open_, dtype=np.float64),
        np.ascontiguousarray(close, dtype=np.float64),
        np.ascontiguousarray(contract, dtype=np.int64),
        sessions,
        body_start,
        clock.bar_minutes,
        n_sessions,
    )
    cash: BoolArray = (sessions >= 0) & (body_start >= CASH_OPEN_MINUTES)
    opened: FloatArray = np.where(cash, anchors.cash_open[np.where(sessions >= 0, sessions, 0)], np.nan)
    anchored: BoolArray = cash & np.isfinite(opened)
    previous: FloatArray = np.full(close.size, np.nan, dtype=np.float64)
    after_first: BoolArray = anchored & (sessions > 0)
    prior: IntArray = sessions[after_first] - 1
    # A previous close read on another contract carries the calendar spread, not a gap.
    same_contract: BoolArray = anchors.close_contract[prior] == anchors.open_contract[sessions[after_first]]
    previous[after_first] = np.where(same_contract, anchors.cash_close[prior], np.nan)
    # fmax and fmin ignore a missing previous close, which leaves both anchors at the open.
    upper: FloatArray = np.fmax(opened, previous)
    lower: FloatArray = np.fmin(opened, previous)

    move: FloatArray = np.abs(close / opened - 1.0)
    grid: FloatArray = volume.session_grid(move, sessions, bar_of_session, n_sessions, n_indices)
    built: dict[int, NoiseBand] = {}
    for lookback in wanted:
        width: FloatArray = volume.read_back(
            _trailing_means(grid, lookback, MIN_LOOKBACK_SESSIONS),
            sessions,
            bar_of_session,
        )
        stretch: FloatArray = noise_stretch(close, upper, lower, width)
        basis: FloatArray = np.where(stretch < 0.0, lower, upper)
        extended: BoolArray = np.isfinite(stretch) & (stretch != 0.0)
        side: FloatArray = np.where(extended, stretch, close - 0.5 * (upper + lower))
        built[lookback] = NoiseBand(upper, lower, width, stretch, basis, basis * width, side)

    anchor_bar: BoolArray = anchored & (body_start == CASH_OPEN_MINUTES)

    return NoiseBandGrid(built, _cash_vwap(high, low, close, traded, anchor_bar, anchored))
