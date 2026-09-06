"""Compressed, normal or expanded: how tight this bar's range is against its own recent past.

One scalar per bar, cut by two thresholds into three labels. The scalar is a **trailing
percentile rank**: a raw width measure, then where that measure sits among the
``baseline_bars`` values before it. Both halves are swept -- :class:`CompressionForm` chooses
the width measure, and the rank is what makes it comparable.

**The rank is the point, not a convenience.** Neither raw form has a natural unit: Bollinger
bandwidth is a fraction of price and reads about ``1e-3`` on NQ, a range-to-ATR ratio reads
about the lookback, and both move with the resolution and the period. A raw threshold on
either is therefore a different cut in every cell of a sweep, which is the failure
``docs/roadmap.md`` §M27.5 and §M27.8 record for the efficiency ratio and for relative volume.
Ranking against a trailing window is the same device :mod:`nqbt.volume` uses when it divides by
a trailing median, and it leaves a quantity in ``0..1`` that a raw pair of thresholds can cut.

**Nothing here reads a bar it does not close.** A bar's width comes from bars up to and
including itself, and its rank compares that against the ``baseline_bars`` bars **strictly
before** it, so no bar contributes to its own baseline. Lookahead is the trap this condition
exists next to -- ``docs/roadmap.md`` §M19.

The band period is not this module's to invent: the bandwidth form reads
:class:`nqbt.bands.BandGrid`, so a sweep that already builds a Bollinger grid shares it --
``docs/roadmap.md`` §M26.

A state set is carried as a bitmask integer so that it is a legal sweep axis, exactly as
:mod:`nqbt.regime`, :mod:`nqbt.volume` and :mod:`nqbt.timeofday` carry theirs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import indicators

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BoolArray, FloatArray, LabelArray
    from nqbt.bands import BandGrid

__all__ = [
    "ALL_STATES",
    "BANDWIDTH_MULTIPLE",
    "MIN_BASELINE_BARS",
    "MIN_PERIOD",
    "UNDEFINED",
    "Compression",
    "CompressionError",
    "CompressionForm",
    "CompressionGrid",
    "CompressionKey",
    "bandwidth",
    "compression_grid",
    "describe_key",
    "describe_mask",
    "gate",
    "key",
    "label",
    "range_to_atr",
    "states_in",
    "states_mask",
    "thresholds_from_quantiles",
    "trailing_rank",
    "validate_baseline_bars",
    "validate_form",
    "validate_mask",
    "validate_period",
    "validate_quantiles",
    "validate_thresholds",
]

UNDEFINED = -1
"""Label for a bar with no rank: inside a form's warm-up, or inside the trailing window's.
Negative, not a fourth state -- the same convention :mod:`nqbt.regime` uses.
"""

MIN_PERIOD = 2
"""Shortest window either width measure accepts. A one-bar standard deviation is identically
zero and a one-bar range is the bar itself, so neither form says anything at ``1``.
"""

MIN_BASELINE_BARS = 20
"""Fewest bars a rank may be taken against. Below this the rank moves in visible steps -- at
ten bars it can only take eleven values -- and the thresholds stop meaning what they say.
"""

BANDWIDTH_MULTIPLE = 2.0
"""The conventional Bollinger multiple, so :func:`bandwidth` matches the published quantity.

**Not a parameter.** It is a constant scale factor on every bar alike, so it cannot move an
ordering, a trailing rank, or a threshold fitted as a quantile -- sweeping it would run
identical combinations.
"""


class CompressionError(ValueError):
    """Raised for an impossible state mask, form, window or pair of thresholds."""


class Compression(IntEnum):
    """The three states of the trailing rank, ordered by it.

    The integer values ascend with the rank, and are also the bit positions in a filter mask.
    """

    COMPRESSED = 0
    """Below the lower threshold: tighter than this series has recently been."""
    NORMAL = 1
    """Between the thresholds, both boundaries included."""
    EXPANDED = 2
    """Above the upper threshold: wider than this series has recently been."""

    @property
    def bit(self) -> int:
        """The bit this state occupies in a filter mask."""
        return 1 << int(self)


class CompressionForm(IntEnum):
    """Which width measure the rank is taken of.

    Two genuinely different statements, which is why the form is a sweep axis rather than a
    choice made once: a narrow band is not a short range. Both are named in
    ``Trading-Docs/trading_concepts.md`` § 3.2 as codeable compression measures.
    """

    BANDWIDTH = 0
    """Bollinger band width over its own midline -- see :func:`bandwidth`."""
    RANGE_TO_ATR = 1
    """The window's high-low range in ATRs of the same length -- see :func:`range_to_atr`."""


ALL_STATES = (1 << len(Compression)) - 1
"""Every state: the mask that filters nothing, and the default for every archetype."""


class CompressionKey(NamedTuple):
    """What one compression series is determined by, and the grid's lookup key."""

    form: CompressionForm
    period: int
    """Bars the width measure spans: the band period under :attr:`CompressionForm.BANDWIDTH`,
    the range and ATR length under :attr:`CompressionForm.RANGE_TO_ATR`. One window either way,
    so no axis is inert under either form."""
    baseline_bars: int
    """Bars the rank is taken against, all strictly before the bar being ranked."""


def states_mask(states: Iterable[Compression]) -> int:
    """Combine states into the bitmask an archetype's ``compression_filter`` takes."""
    mask: int = 0
    for state in states:
        mask |= Compression(state).bit

    return mask


def states_in(mask: int) -> tuple[Compression, ...]:
    """Unpack a mask into the states it admits, in ascending-rank order."""
    validate_mask(mask)

    return tuple(s for s in Compression if mask & s.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no state owns."""
    if mask < 0 or mask & ~ALL_STATES:
        msg: str = (
            f"compression mask {mask} sets bits outside 0..{ALL_STATES}; use Compression.bit or states_mask()"
        )
        raise CompressionError(msg)

    if mask == 0:
        msg = "compression mask 0 admits no state, so every combination along it would trade nothing"
        raise CompressionError(msg)

    return mask


def describe_mask(mask: int) -> str:
    """Render a mask as a state list, for a results table or an error message."""
    return "+".join(s.name for s in states_in(mask))


def describe_key(wanted: CompressionKey) -> str:
    """Name one series by what determines it, for a stratum name or a results table."""
    return f"{CompressionForm(wanted.form).name.lower()}_{wanted.period}_{wanted.baseline_bars}"


def validate_form(form: int) -> CompressionForm:
    """Resolve a form to its enum member, naming the legal ones when it is not one."""
    try:
        return CompressionForm(int(form))
    except ValueError:
        legal: str = ", ".join(f"{f.name}={int(f)}" for f in CompressionForm)
        msg: str = f"unknown compression form {form}; use one of {legal}"
        raise CompressionError(msg) from None


def validate_period(period: int) -> int:
    """Reject a width window either form is degenerate at -- see :data:`MIN_PERIOD`."""
    if period < MIN_PERIOD:
        msg: str = (
            f"compression period must span >= {MIN_PERIOD} bars, got {period}; "
            "a one-bar width is zero under BANDWIDTH and the bar itself under RANGE_TO_ATR"
        )
        raise CompressionError(msg)

    return period


def validate_baseline_bars(baseline_bars: int) -> int:
    """Reject a trailing window too short to rank against -- see :data:`MIN_BASELINE_BARS`."""
    if baseline_bars < MIN_BASELINE_BARS:
        msg: str = f"compression baseline must span >= {MIN_BASELINE_BARS} bars, got {baseline_bars}"
        raise CompressionError(msg)

    return baseline_bars


def validate_thresholds(compressed_below: float, expanded_above: float) -> None:
    """Reject thresholds that would put a bar in two states at once, or fall outside 0-1.

    Equal thresholds are legal and collapse the normal band onto the boundary itself. The rank
    is a share of a trailing window, so both bounds are real rather than conventional.
    """
    if not 0.0 <= compressed_below <= 1.0:
        msg: str = f"compressed_below must lie in 0..1, got {compressed_below}"
        raise CompressionError(msg)

    if not 0.0 <= expanded_above <= 1.0:
        msg = f"expanded_above must lie in 0..1, got {expanded_above}"
        raise CompressionError(msg)

    if compressed_below > expanded_above:
        msg = (
            f"compressed_below {compressed_below} exceeds expanded_above {expanded_above}, "
            "which would put a bar in both states at once"
        )
        raise CompressionError(msg)


def validate_quantiles(compressed_quantile: float, expanded_quantile: float) -> None:
    """Reject quantiles outside 0-1, or a pair that would put a bar in two states at once."""
    if not 0.0 <= compressed_quantile <= 1.0:
        msg: str = f"compressed_quantile must lie in 0..1, got {compressed_quantile}"
        raise CompressionError(msg)

    if not 0.0 <= expanded_quantile <= 1.0:
        msg = f"expanded_quantile must lie in 0..1, got {expanded_quantile}"
        raise CompressionError(msg)

    if compressed_quantile > expanded_quantile:
        msg = (
            f"compressed_quantile {compressed_quantile} exceeds expanded_quantile "
            f"{expanded_quantile}, which would cross the thresholds they fit"
        )
        raise CompressionError(msg)


def thresholds_from_quantiles(
    values: FloatArray,
    compressed_quantile: float,
    expanded_quantile: float,
) -> tuple[float, float]:
    """Both thresholds as quantiles of the ranks in ``values``, unranked bars excluded.

    A trailing rank is already close to uniform, so this and the raw pair nearly agree -- which
    is the property neither :mod:`nqbt.regime` nor :mod:`nqbt.volume` has. *Close* is not
    *equal*: width is strongly autocorrelated, so the ranks bunch at both ends. Fit on the
    selection window alone -- fitting on the whole series leaks the holdout.
    """
    validate_quantiles(compressed_quantile, expanded_quantile)
    measured: FloatArray = np.asarray(values, dtype=np.float64)
    measured = measured[np.isfinite(measured)]
    if measured.size == 0:
        msg: str = "no measured compression rank to take a quantile of; every bar is undefined"
        raise CompressionError(msg)

    cuts: FloatArray = np.quantile(measured, [compressed_quantile, expanded_quantile])

    return float(cuts[0]), float(cuts[1])


def key(form: int, period: int, baseline_bars: int) -> CompressionKey:
    """Build a grid key, validating every field.

    Both forms read every field, so nothing is dropped here -- unlike
    :func:`nqbt.volume.key`, whose rolling window belongs to one form only.
    """
    return CompressionKey(
        validate_form(form),
        validate_period(period),
        validate_baseline_bars(baseline_bars),
    )


@njit(cache=True)
def _rolling_range(high: FloatArray, low: FloatArray, period: int) -> FloatArray:
    """Highest high less lowest low over ``period`` bars, ``nan`` until that many exist.

    Recomputed per bar rather than maintained: a running extreme cannot be un-extended when the
    bar holding it leaves the window, so the state a rolling form would need is the window
    itself -- the same reasoning ``docs/roadmap.md`` §M10.1 records for the efficiency ratio.
    """
    n = high.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(period - 1, n):
        top = high[i]
        bottom = low[i]
        for j in range(i - period + 1, i):
            top = max(top, high[j])
            bottom = min(bottom, low[j])
        out[i] = top - bottom

    return out


@njit(cache=True)
def _ratio(values: FloatArray, scale: FloatArray) -> FloatArray:
    """``values / scale``, ``nan`` wherever there is nothing positive to divide by."""
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        denominator = scale[i]
        if not np.isnan(values[i]) and not np.isnan(denominator) and denominator > 0.0:
            out[i] = values[i] / denominator

    return out


@njit(cache=True)
def _trailing_rank(values: FloatArray, baseline_bars: int) -> FloatArray:
    """Share of the ``baseline_bars`` values before each bar that are below it.

    ``nan`` until a full window of *measured* values exists behind the bar, so a form's own
    warm-up cannot shorten the window a rank is taken over. A tie counts as half, which keeps a
    flat stretch at 0.5 rather than sending it to either extreme.
    """
    n = values.size
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        current = values[i]
        if np.isnan(current) or i < baseline_bars:
            continue

        below = 0.0
        held = 0
        for j in range(i - baseline_bars, i):
            prior = values[j]
            if np.isnan(prior):
                continue

            held += 1
            if prior < current:
                below += 1.0
            elif prior == current:
                below += 0.5

        if held == baseline_bars:
            out[i] = below / held

    return out


@njit(cache=True)
def _state_of(rank: float, compressed_below: float, expanded_above: float) -> int:
    """Classify one rank -- the only place this rule lives, shared by ``label`` and ``gate``."""
    if np.isnan(rank):
        return UNDEFINED

    if rank < compressed_below:
        return Compression.COMPRESSED

    if rank > expanded_above:
        return Compression.EXPANDED

    return Compression.NORMAL


@njit(cache=True)
def _label(ranks: FloatArray, compressed_below: float, expanded_above: float) -> LabelArray:
    n = ranks.size
    out = np.empty(n, dtype=np.int8)
    for i in range(n):
        out[i] = _state_of(ranks[i], compressed_below, expanded_above)

    return out


@njit(cache=True)
def _gate(ranks: FloatArray, compressed_below: float, expanded_above: float, mask: int) -> BoolArray:
    """One pass from rank to boolean, so a sweep combination never builds a label array."""
    n = ranks.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        found = _state_of(ranks[i], compressed_below, expanded_above)
        if found != UNDEFINED:
            out[i] = (mask & (1 << found)) != 0

    return out


def bandwidth(basis: FloatArray, stddev: FloatArray) -> FloatArray:
    """Bollinger band width as a fraction of its own midline: ``2 * sigma / basis``.

    Taken off :class:`nqbt.bands.BandGrid`'s two rows rather than recomputed, so an archetype
    already sweeping a Bollinger shares one grid -- ``docs/roadmap.md`` §M26.
    """
    return _ratio(
        BANDWIDTH_MULTIPLE * np.ascontiguousarray(stddev, dtype=np.float64),
        np.ascontiguousarray(basis, dtype=np.float64),
    )


def range_to_atr(high: FloatArray, low: FloatArray, close: FloatArray, period: int) -> FloatArray:
    """The last ``period`` bars' high-low range, in ATRs of that same length.

    Scale-free by construction: a window that trended reads near ``period`` and one that went
    nowhere reads near ``1``. One length for both halves rather than two axes, because the
    quantity being asked for is how far the range falls short of the movement inside it.
    """
    validate_period(period)
    high = np.ascontiguousarray(high, dtype=np.float64)
    low = np.ascontiguousarray(low, dtype=np.float64)

    return _ratio(
        _rolling_range(high, low, int(period)),
        indicators.nt8_atr(high, low, np.ascontiguousarray(close, dtype=np.float64), int(period)),
    )


def trailing_rank(values: FloatArray, baseline_bars: int) -> FloatArray:
    """Rank every bar's value against the ``baseline_bars`` values before it, in ``0..1``.

    ``nan`` wherever the window behind a bar is not a full one of measured values.
    """
    validate_baseline_bars(baseline_bars)

    return _trailing_rank(np.ascontiguousarray(values, dtype=np.float64), int(baseline_bars))


def label(ranks: FloatArray, compressed_below: float, expanded_above: float) -> LabelArray:
    """Cut trailing ranks into ``int8`` :class:`Compression`, :data:`UNDEFINED` for ``nan``.

    **Both boundaries fall in the normal band**: strictly below the lower threshold is
    compressed, strictly above the upper is expanded, and equality on either is normal.
    """
    validate_thresholds(compressed_below, expanded_above)

    return _label(
        np.ascontiguousarray(ranks, dtype=np.float64),
        float(compressed_below),
        float(expanded_above),
    )


def gate(ranks: FloatArray, mask: int, compressed_below: float, expanded_above: float) -> BoolArray:
    """Test every bar's compression state against ``mask``, one boolean per bar.

    An :data:`UNDEFINED` bar passes nothing, :data:`ALL_STATES` included, which is why an
    archetype's signal skips this call entirely at the default.
    """
    validate_mask(mask)
    validate_thresholds(compressed_below, expanded_above)

    return _gate(
        np.ascontiguousarray(ranks, dtype=np.float64),
        float(compressed_below),
        float(expanded_above),
        int(mask),
    )


@dataclass(frozen=True, slots=True)
class CompressionGrid:
    """Every compression series a sweep needs, and the raw width behind each.

    Ranks rather than labels, because both thresholds are swept as well and a grid over all of
    them would multiply out. ``keys`` is sorted and deduplicated, so :meth:`row` is the only
    supported way from a key back to its row.
    """

    keys: tuple[CompressionKey, ...]
    width: FloatArray
    """The raw width measure, ``[n_keys, n_bars]`` float64. Read for reporting, never filtered
    on -- its scale belongs to the form, the period and the resolution at once."""
    rank: FloatArray
    """The same, ranked against each bar's trailing window, ``nan`` where there is none."""

    def __len__(self) -> int:
        """Count the bars, not the keys."""
        return int(self.rank.shape[1])

    def row(self, wanted: CompressionKey) -> int:
        """Find the row holding ``wanted``, or say what the grid was built for."""
        try:
            return self.keys.index(wanted)
        except ValueError:
            msg: str = f"compression series {wanted} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg) from None

    def width_for(self, wanted: CompressionKey) -> FloatArray:
        """Read one series' raw width measure, in whatever unit its form is in."""
        return np.asarray(self.width[self.row(wanted)])

    def rank_for(self, wanted: CompressionKey) -> FloatArray:
        """Read one series' trailing rank -- the quantity behind the labels."""
        return np.asarray(self.rank[self.row(wanted)])

    def thresholds_for(
        self,
        wanted: CompressionKey,
        compressed_quantile: float,
        expanded_quantile: float,
    ) -> tuple[float, float]:
        """Fit both thresholds to one series' own distribution of ranks.

        See :func:`thresholds_from_quantiles` for what a fit must be fitted on.
        """
        return thresholds_from_quantiles(self.rank_for(wanted), compressed_quantile, expanded_quantile)

    def labels_for(
        self,
        wanted: CompressionKey,
        compressed_below: float,
        expanded_above: float,
    ) -> LabelArray:
        """Label every bar of one series, the stratification key -- see :func:`label`."""
        return label(self.rank_for(wanted), compressed_below, expanded_above)

    def gate_for(
        self,
        wanted: CompressionKey,
        mask: int,
        compressed_below: float,
        expanded_above: float,
    ) -> BoolArray:
        """Test every bar of one series against ``mask``, the entry filter -- see :func:`gate`."""
        return gate(self.rank_for(wanted), mask, compressed_below, expanded_above)

    @property
    def nbytes(self) -> int:
        """Bytes the series occupy -- what a parallel worker is handed."""
        return self.width.nbytes + self.rank.nbytes


def _width_of(
    wanted: CompressionKey,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    band: BandGrid | None,
) -> FloatArray:
    """One key's raw width measure, taking the bandwidth form's two rows off ``band``."""
    if wanted.form is CompressionForm.RANGE_TO_ATR:
        return range_to_atr(high, low, close, wanted.period)

    if band is None:
        msg: str = (
            f"compression series {wanted} is a bandwidth form and needs a band grid; "
            "prepare() builds one from ContextSpec.band_periods_needed()"
        )
        raise CompressionError(msg)

    return bandwidth(band.basis_for(wanted.period), band.stddev_for(wanted.period))


def compression_grid(
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    keys: Iterable[CompressionKey],
    band: BandGrid | None = None,
) -> CompressionGrid:
    """Compute every distinct compression series a sweep needs, once.

    Sixteen bytes per bar per key, and the rank is the expensive pass: it reads
    ``baseline_bars`` values for every bar rather than maintaining a window.
    """
    ordered: tuple[CompressionKey, ...] = tuple(
        sorted({key(k.form, k.period, k.baseline_bars) for k in keys}),
    )
    if not ordered:
        msg: str = "no compression series supplied"
        raise CompressionError(msg)

    n_bars: int = int(np.asarray(close).size)
    width: FloatArray = np.empty((len(ordered), n_bars), dtype=np.float64)
    rank: FloatArray = np.empty((len(ordered), n_bars), dtype=np.float64)
    for i, wanted in enumerate(ordered):
        measured: FloatArray = _width_of(wanted, high, low, close, band)
        width[i] = measured
        rank[i] = trailing_rank(measured, wanted.baseline_bars)

    return CompressionGrid(keys=ordered, width=width, rank=rank)
