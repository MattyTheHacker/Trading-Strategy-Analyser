"""Volume in three forms, and each form against what is normal for its bar of session.

**One quantity and its decomposition, not three conditions.** Absolute volume is the raw
contract count and answers *can this be traded here at all?*; the time of day is its dominant
systematic component; relative volume is the absolute count with that component divided out and
answers *is this unusual for the time?* The labels here are cut from the **relative** form only,
because an absolute threshold means different things in 2021 and 2026 and is not comparable
across roots -- ``docs/roadmap.md`` §M10.2. The absolute series is carried beside it for
reporting, which is the one question relative volume cannot answer.

The baseline is the **median of the same bar of session over a trailing window of prior
sessions**, never a rolling window of adjacent bars. Intraday volume has a strong time-of-day
shape, so a plain rolling average marks every cash-open bar heavy and every overnight bar thin
-- that is a clock, not a signal. The bar-of-session index is :mod:`nqbt.timeofday`'s, so the
two share one definition rather than each inventing one.

A state set is carried as a bitmask integer so that it is a legal sweep axis, exactly as
:mod:`nqbt.regime` and :mod:`nqbt.timeofday` carry theirs. Thresholds, the roll discontinuity
and the multiple-comparisons cost of reading the three forms as three findings:
``docs/roadmap.md`` §M10.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from nqbt.arrays import (
        BoolArray,
        DateArray,
        FloatArray,
        IndexArray,
        IntArray,
        LabelArray,
        OffsetArray,
    )

__all__: Sequence[str] = [
    "ALL_STATES",
    "MIN_BASELINE_SESSIONS",
    "MIN_ROLLING_BARS",
    "NO_ROLLING",
    "UNDEFINED",
    "VolumeError",
    "VolumeForm",
    "VolumeGrid",
    "VolumeKey",
    "VolumeState",
    "absolute_form",
    "describe_mask",
    "gate",
    "key",
    "label",
    "relative_to_bar_of_session",
    "session_ids",
    "states_in",
    "states_mask",
    "validate_baseline_sessions",
    "validate_form",
    "validate_mask",
    "validate_rolling_bars",
    "validate_thresholds",
    "volume_grid",
]

UNDEFINED: int = -1
"""Label for a bar with no baseline to be relative to: out of session, inside a warm-up, or in
a bar of session whose prior sessions traded nothing. Negative, not a fourth state --
``docs/roadmap.md`` §M10.2.
"""

MIN_ROLLING_BARS: int = 2
"""A one-bar rolling window is :attr:`VolumeForm.PER_BAR` under another name. Refused rather
than silently duplicating a form.
"""

MIN_BASELINE_SESSIONS: int = 5
"""Fewest prior sessions a baseline may be taken over, and the number of observations the
window must actually hold before a bar is labelled at all.
"""

NO_ROLLING: int = 0
"""The rolling window a form that does not read one carries in its :class:`VolumeKey`."""


class VolumeError(ValueError):
    """Raised for an impossible state mask, form, window or pair of thresholds."""


class VolumeState(IntEnum):
    """The three states of relative volume, ordered by it.

    The integer values ascend with the ratio, and are also the bit positions in a filter mask.
    """

    THIN = 0  # Below the lower threshold: quieter than this bar of session usually is.
    NORMAL = 1  # Between the thresholds, both boundaries included.
    HEAVY = 2  # Above the upper threshold: busier than this bar of session usually is.

    @property
    def bit(self) -> int:
        """The bit this state occupies in a filter mask."""
        return 1 << int(self)


class VolumeForm(IntEnum):
    """Which absolute quantity the relative ratio is taken of.

    Three genuinely different statements, which is why the form is a sweep axis rather than a
    choice made once: an unusually busy bar is not an unusually busy session so far.
    """

    PER_BAR = 0  # Contracts traded in this bar alone.
    ROLLING = 1  # Contracts traded over the trailing ``rolling_bars`` bars, this one included.
    SESSION_TO_DATE = 2  # Contracts traded since this bar's session opened. Pairs with the bar-of-session index.


ALL_STATES = (1 << len(VolumeState)) - 1
"""Every state: the mask that filters nothing, and the default for every archetype."""


class VolumeKey(NamedTuple):
    """What one relative-volume series is determined by, and the grid's lookup key."""

    form: VolumeForm
    rolling_bars: int  # :data:`NO_ROLLING` for every form but :attr:`VolumeForm.ROLLING` -- see :func:`key`.
    baseline_sessions: int


def states_mask(states: Iterable[VolumeState]) -> int:
    """Combine states into the bitmask an archetype's ``volume_filter`` takes."""
    mask: int = 0
    for state in states:
        mask |= VolumeState(state).bit

    return mask


def states_in(mask: int) -> tuple[VolumeState, ...]:
    """Unpack a mask into the states it admits, in ascending-ratio order."""
    validate_mask(mask)

    return tuple(s for s in VolumeState if mask & s.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no state owns."""
    if mask < 0 or mask & ~ALL_STATES:
        msg: str = f"volume mask {mask} sets bits outside 0..{ALL_STATES}; use VolumeState.bit or states_mask()"
        raise VolumeError(msg)

    if mask == 0:
        msg = "volume mask 0 admits no state, so every combination along it would trade nothing"
        raise VolumeError(msg)

    return mask


def describe_mask(mask: int) -> str:
    """Render a mask as a state list, for a results table or an error message."""
    return "+".join(s.name for s in states_in(mask))


def validate_form(form: int) -> VolumeForm:
    """Resolve a form to its enum member, naming the legal ones when it is not one."""
    try:
        return VolumeForm(int(form))
    except ValueError:
        legal: str = ", ".join(f"{f.name}={int(f)}" for f in VolumeForm)
        msg: str = f"unknown volume form {form}; use one of {legal}"
        raise VolumeError(msg) from None


def validate_rolling_bars(rolling_bars: int) -> int:
    """Reject a rolling window the form is degenerate at -- see :data:`MIN_ROLLING_BARS`."""
    if rolling_bars < MIN_ROLLING_BARS:
        msg: str = (
            f"rolling volume must span >= {MIN_ROLLING_BARS} bars, got {rolling_bars}; "
            "a one-bar window is VolumeForm.PER_BAR"
        )
        raise VolumeError(msg)

    return rolling_bars


def validate_baseline_sessions(baseline_sessions: int) -> int:
    """Reject a baseline too short to normalise anything -- :data:`MIN_BASELINE_SESSIONS`."""
    if baseline_sessions < MIN_BASELINE_SESSIONS:
        msg: str = f"baseline must span >= {MIN_BASELINE_SESSIONS} sessions, got {baseline_sessions}"
        raise VolumeError(msg)

    return baseline_sessions


def validate_thresholds(thin_below: float, heavy_above: float) -> None:
    """Reject thresholds that would put a bar in two states at once, or below zero.

    Equal thresholds are legal and collapse the normal band onto the boundary itself. There is
    no upper bound: relative volume is a ratio to a median and is unbounded above.
    """
    if thin_below < 0.0:
        msg: str = f"thin_below must be >= 0, got {thin_below}"
        raise VolumeError(msg)

    if heavy_above < 0.0:
        msg = f"heavy_above must be >= 0, got {heavy_above}"
        raise VolumeError(msg)

    if thin_below > heavy_above:
        msg = f"thin_below {thin_below} exceeds heavy_above {heavy_above}, which would put a bar in both states at once"
        raise VolumeError(msg)


def key(form: int, rolling_bars: int, baseline_sessions: int) -> VolumeKey:
    """Build a grid key, dropping the window a form does not read.

    ``rolling_bars`` becomes :data:`NO_ROLLING` for every form but :attr:`VolumeForm.ROLLING`,
    so sweeping the window alongside a per-bar form does not build one identical series per
    window.
    """
    resolved: VolumeForm = validate_form(form)
    window: int = validate_rolling_bars(rolling_bars) if resolved is VolumeForm.ROLLING else NO_ROLLING

    return VolumeKey(resolved, window, validate_baseline_sessions(baseline_sessions))


def session_ids(trading_day: DateArray, in_session: BoolArray) -> IntArray:
    """Give each in-session bar the index of the session it falls in, :data:`UNDEFINED` outside.

    Ascending timestamp order is assumed, which ingestion guarantees.
    """
    days: DateArray = np.asarray(trading_day)
    ids: IntArray = np.full(days.size, UNDEFINED, dtype=np.int64)
    inside: OffsetArray = np.flatnonzero(np.asarray(in_session))

    if inside.size == 0:
        return ids

    ordered: DateArray = days[inside]
    boundary: BoolArray = np.empty(inside.size, dtype=bool)
    boundary[0] = True
    boundary[1:] = ordered[1:] != ordered[:-1]
    ids[inside] = np.cumsum(boundary) - 1

    return ids


@njit(cache=True)
def _rolling_sum(values: FloatArray, window: int) -> FloatArray:
    """Trailing ``window``-bar sum, ``nan`` until the window is full.

    Maintained by add and subtract rather than re-summed. Unlike an efficiency ratio's path
    length this cannot drift: contract counts are exact in float64, so the running total is the
    same number a recomputed sum would be -- ``docs/roadmap.md`` §M10.2.
    """
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    total = 0.0
    for i in range(n):
        total += values[i]
        if i >= window:
            total -= values[i - window]

        if i >= window - 1:
            out[i] = total

    return out


@njit(cache=True)
def _session_cumulative(values: FloatArray, session_id: IntArray) -> FloatArray:
    """Volume since this bar's session opened, ``nan`` for a bar in no session."""
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    total = 0.0
    current = -1
    for i in range(n):
        session = session_id[i]
        if session < 0:
            continue

        if session != current:
            current = session
            total = 0.0

        total += values[i]
        out[i] = total

    return out


@njit(cache=True)
def _insert_sorted(buffer: FloatArray, held: int, value: float) -> int:
    """Insert one value into a sorted buffer, returning how many it now holds."""
    slot = held - 1
    while slot >= 0 and buffer[slot] > value:
        buffer[slot + 1] = buffer[slot]
        slot -= 1
    buffer[slot + 1] = value

    return held + 1


@njit(cache=True)
def _remove_sorted(buffer: FloatArray, held: int, value: float) -> int:
    """Drop one occurrence of a value from a sorted buffer, returning how many are left.

    The value is always present: it was inserted ``window`` sessions ago and each session's
    value leaves exactly once. The search is for the first slot not less than it, which is that
    value's first occurrence when the buffer holds it more than once.
    """
    low = 0
    high = held
    while low < high:
        middle = (low + high) // 2
        if buffer[middle] < value:
            low = middle + 1
        else:
            high = middle
    for slot in range(low, held - 1):
        buffer[slot] = buffer[slot + 1]

    return held - 1


@njit(cache=True)
def _median_of(buffer: FloatArray, held: int) -> float:
    """Take the median of the first ``held`` entries of a sorted buffer."""
    middle = held // 2
    if held % 2 == 1:
        return float(buffer[middle])

    return float(0.5 * (buffer[middle - 1] + buffer[middle]))


@njit(cache=True)
def _session_grid(
    values: FloatArray,
    session_id: IntArray,
    bar_of_session: IntArray,
    n_sessions: int,
    n_indices: int,
) -> FloatArray:
    """Lay the series out as ``[session, bar of session]``, ``nan`` where the archive has a hole."""
    grid = np.full((n_sessions, n_indices), np.nan, dtype=np.float64)
    for i in range(values.size):
        session = session_id[i]
        index = bar_of_session[i]

        if session >= 0 and 0 <= index < n_indices:
            grid[session, index] = values[i]

    return grid


@njit(cache=True)
def _trailing_medians(grid: FloatArray, window: int, min_observations: int) -> FloatArray:
    """Per cell, the median of its column over the ``window`` sessions *before* its row.

    Strictly prior: no session contributes to its own baseline. The window is a sorted buffer
    each session's value enters and leaves exactly once, which is exact because nothing
    accumulates. One entry longer than the window, since the arriving session joins before the
    departing one drops.
    """
    n_sessions, n_indices = grid.shape
    medians = np.full((n_sessions, n_indices), np.nan, dtype=np.float64)
    buffer = np.empty(window + 1, dtype=np.float64)
    for index in range(n_indices):
        held = 0
        for session in range(n_sessions):
            if held >= min_observations:
                medians[session, index] = _median_of(buffer, held)

            entering = grid[session, index]
            if not np.isnan(entering):
                held = _insert_sorted(buffer, held, entering)

            oldest = session - window
            if oldest >= 0 and not np.isnan(grid[oldest, index]):
                held = _remove_sorted(buffer, held, grid[oldest, index])

    return medians


@njit(cache=True)
def _gather(medians: FloatArray, session_id: IntArray, bar_of_session: IntArray) -> FloatArray:
    """Read one value per bar back out of a ``[session, bar of session]`` layout."""
    n_indices = medians.shape[1]
    out = np.full(session_id.size, np.nan, dtype=np.float64)
    for i in range(session_id.size):
        session = session_id[i]
        index = bar_of_session[i]
        if session >= 0 and 0 <= index < n_indices:
            out[i] = medians[session, index]

    return out


@njit(cache=True)
def _ratio(values: FloatArray, baseline: FloatArray) -> FloatArray:
    """``values / baseline``, ``nan`` wherever there is no baseline to divide by.

    A bar of session whose prior sessions traded nothing has no scale to be relative to, so a
    zero baseline is undefined rather than infinite.
    """
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        scale = baseline[i]
        if not np.isnan(values[i]) and not np.isnan(scale) and scale > 0.0:
            out[i] = values[i] / scale

    return out


@njit(cache=True)
def _state_of(relative: float, thin_below: float, heavy_above: float) -> int:
    """Classify one ratio -- the only place this rule lives, shared by ``label`` and ``gate``."""
    if np.isnan(relative):
        return UNDEFINED

    if relative < thin_below:
        return VolumeState.THIN

    if relative > heavy_above:
        return VolumeState.HEAVY

    return VolumeState.NORMAL


@njit(cache=True)
def _label(relative: FloatArray, thin_below: float, heavy_above: float) -> LabelArray:
    n = relative.size
    out = np.empty(n, dtype=np.int8)
    for i in range(n):
        out[i] = _state_of(relative[i], thin_below, heavy_above)

    return out


@njit(cache=True)
def _gate(relative: FloatArray, thin_below: float, heavy_above: float, mask: int) -> BoolArray:
    """One pass from ratio to boolean, so a sweep combination never builds a label array."""
    n = relative.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        found = _state_of(relative[i], thin_below, heavy_above)
        if found != UNDEFINED:
            out[i] = (mask & (1 << found)) != 0

    return out


def absolute_form(
    volume: FloatArray,
    form: VolumeForm,
    rolling_bars: int,
    session_id: IntArray,
) -> FloatArray:
    """One of the three absolute forms, over volume already zeroed outside the session.

    ``PER_BAR`` is the count itself; ``ROLLING`` is the trailing sum, ``nan`` through its
    warm-up; ``SESSION_TO_DATE`` restarts at each open and is ``nan`` for a bar in no session.
    Every form therefore reads zero or ``nan`` outside a session, never a stray print's count.
    """
    if form is VolumeForm.PER_BAR:
        return volume

    if form is VolumeForm.ROLLING:
        return _rolling_sum(volume, validate_rolling_bars(rolling_bars))

    return _session_cumulative(volume, session_id)


def relative_to_bar_of_session(
    values: FloatArray,
    session_id: IntArray,
    bar_of_session: IntArray,
    baseline_sessions: int,
    min_observations: int = MIN_BASELINE_SESSIONS,
) -> FloatArray:
    """Divide out what is normal for this bar of session over the preceding sessions.

    ``nan`` wherever the window holds fewer than ``min_observations`` observations, which is
    every bar of the first few sessions and every bar in no session at all.
    """
    validate_baseline_sessions(baseline_sessions)
    values = np.ascontiguousarray(values, dtype=np.float64)
    sessions: IntArray = np.ascontiguousarray(session_id, dtype=np.int64)
    indices: IntArray = np.ascontiguousarray(bar_of_session, dtype=np.int64)
    n_sessions: int = max(int(sessions.max()) + 1, 0) if sessions.size else 0
    n_indices: int = max(int(indices.max()) + 1, 0) if indices.size else 0
    if n_sessions == 0 or n_indices == 0:
        return np.full(values.size, np.nan, dtype=np.float64)

    grid: FloatArray = _session_grid(values, sessions, indices, n_sessions, n_indices)
    medians: FloatArray = _trailing_medians(grid, int(baseline_sessions), int(min_observations))

    return _ratio(values, _gather(medians, sessions, indices))


def label(relative: FloatArray, thin_below: float, heavy_above: float) -> LabelArray:
    """Cut relative volume into ``int8`` :class:`VolumeState`, :data:`UNDEFINED` for ``nan``.

    **Both boundaries fall in the normal band**: strictly below the lower threshold is thin,
    strictly above the upper is heavy, and equality on either is normal.
    """
    validate_thresholds(thin_below, heavy_above)

    return _label(np.ascontiguousarray(relative, dtype=np.float64), float(thin_below), float(heavy_above))


def gate(relative: FloatArray, mask: int, thin_below: float, heavy_above: float) -> BoolArray:
    """Test every bar's volume state against ``mask``, one boolean per bar.

    An :data:`UNDEFINED` bar passes nothing, :data:`ALL_STATES` included, which is why an
    archetype's signal skips this call entirely at the default -- ``docs/roadmap.md`` §M10.2.
    """
    validate_mask(mask)
    validate_thresholds(thin_below, heavy_above)

    return _gate(
        np.ascontiguousarray(relative, dtype=np.float64),
        float(thin_below),
        float(heavy_above),
        int(mask),
    )


@dataclass(frozen=True, slots=True)
class VolumeGrid:
    """Every relative-volume series a sweep needs, and the absolute one behind each.

    Ratios rather than labels, because both thresholds are swept as well and a grid over all of
    them would multiply out. ``keys`` is sorted and deduplicated, so :meth:`row` is the only
    supported way from a key back to its row.
    """

    keys: tuple[VolumeKey, ...]
    absolute: FloatArray
    """Contracts traded, ``[n_keys, n_bars]`` float64. Read, never filtered on -- an absolute
    threshold is comparable neither across time nor across roots."""
    relative: FloatArray  # The same, divided by its bar-of-session baseline, ``nan`` where there is none.

    def __len__(self) -> int:
        """Count the bars, not the keys."""
        return int(self.relative.shape[1])

    def row(self, wanted: VolumeKey) -> int:
        """Find the row holding ``wanted``, or say what the grid was built for."""
        try:
            return self.keys.index(wanted)
        except ValueError:
            msg: str = f"volume series {wanted} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg) from None

    def absolute_for(self, wanted: VolumeKey) -> FloatArray:
        """Read one series' absolute volume -- the execution-feasibility question."""
        return np.asarray(self.absolute[self.row(wanted)])

    def relative_for(self, wanted: VolumeKey) -> FloatArray:
        """Read one series' relative volume."""
        return np.asarray(self.relative[self.row(wanted)])

    def labels_for(self, wanted: VolumeKey, thin_below: float, heavy_above: float) -> LabelArray:
        """Label every bar of one series, the stratification key -- see :func:`label`."""
        return label(self.relative_for(wanted), thin_below, heavy_above)

    def gate_for(self, wanted: VolumeKey, mask: int, thin_below: float, heavy_above: float) -> BoolArray:
        """Test every bar of one series against ``mask``, the entry filter -- see :func:`gate`."""
        return gate(self.relative_for(wanted), mask, thin_below, heavy_above)

    @property
    def nbytes(self) -> int:
        """Bytes the series occupy -- what a parallel worker is handed."""
        return self.absolute.nbytes + self.relative.nbytes


def volume_grid(
    volume: FloatArray,
    trading_day: DateArray,
    in_session: BoolArray,
    bar_of_session: IndexArray,
    keys: Iterable[VolumeKey],
) -> VolumeGrid:
    """Compute every distinct volume series a sweep needs, once.

    Out-of-session prints read zero in every form: NT8 building bars against an ETH template
    would never form them, so they are not session volume. Sixteen bytes per bar per key, and
    the baseline is the expensive pass -- ``docs/roadmap.md`` §M10.2.
    """
    ordered: tuple[VolumeKey, ...] = tuple(sorted({key(k.form, k.rolling_bars, k.baseline_sessions) for k in keys}))
    if not ordered:
        msg: str = "no volume series supplied"
        raise VolumeError(msg)

    raw: FloatArray = np.ascontiguousarray(volume, dtype=np.float64)
    session_id: IntArray = session_ids(trading_day, in_session)
    traded: FloatArray = np.where(np.asarray(in_session), raw, 0.0)
    indices: IntArray = np.ascontiguousarray(bar_of_session, dtype=np.int64)

    absolute: FloatArray = np.empty((len(ordered), raw.size), dtype=np.float64)
    relative: FloatArray = np.empty((len(ordered), raw.size), dtype=np.float64)
    for i, wanted in enumerate(ordered):
        series: FloatArray = absolute_form(traded, wanted.form, wanted.rolling_bars, session_id)
        absolute[i] = series
        relative[i] = relative_to_bar_of_session(series, session_id, indices, wanted.baseline_sessions)

    return VolumeGrid(keys=ordered, absolute=absolute, relative=relative)
