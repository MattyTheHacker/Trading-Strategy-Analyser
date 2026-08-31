"""A compact trend label, cut from moving averages the project already computes.

Three facts about one pair of averages -- where price sits against the slow one, which way the
slow one is sloping, and which way round the fast and slow are stacked -- reduced to a single
``int8`` per bar instead of a wall of MA booleans. Each fact votes ``+1``, ``-1`` or ``0``, the
votes sum to an **agreement score** in ``-3..+3``, and ``min_agreement`` cuts that score into
:attr:`Trend.DOWN`, :attr:`Trend.MIXED` and :attr:`Trend.UP`.

**No new indicator work**: the averages come from :func:`nqbt.conditions.moving_average_grid`,
so they are the same NT8-seeded EMAs every gate reads. **And no new memory**: the grid this
module builds for its own periods is dropped with only the labels kept, so asking for a trend
label never switches ``keep_values`` on for the sweep's shared grids -- ``docs/roadmap.md``
§M10.3.

A trend set is carried as a bitmask integer so that it is a legal sweep axis, exactly as
:mod:`nqbt.regime`, :mod:`nqbt.timeofday` and :mod:`nqbt.volume` carry theirs. Why the label is
unanimity rather than a composite of eight states, why the boundary belongs to the outer bands
here and to the middle band there, and why the kind is fixed at EMA: ``docs/roadmap.md`` §M10.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numba import njit

from nqbt import conditions

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nqbt.arrays import BoolArray, FloatArray, LabelArray
    from nqbt.conditions import MovingAverageGrid

__all__ = [
    "ALL_TRENDS",
    "KIND",
    "MIN_SLOPE_LOOKBACK",
    "N_COMPONENTS",
    "UNDEFINED",
    "Trend",
    "TrendComponent",
    "TrendError",
    "TrendGrid",
    "TrendKey",
    "components",
    "describe_mask",
    "gate",
    "key",
    "label",
    "trend_grid",
    "trends_in",
    "trends_mask",
    "validate_mask",
    "validate_min_agreement",
    "validate_periods",
    "validate_slope_lookback",
]

UNDEFINED = -1
"""Label for a bar whose slope the lookback cannot reach back from. Negative, not a fourth
trend -- ``docs/roadmap.md`` §M10.3.
"""

KIND = "ema"
"""The moving average the label is built on. Fixed rather than swept -- ``docs/roadmap.md``
§M10.3.
"""

MIN_SLOPE_LOOKBACK = 1
"""A zero-bar slope compares a value with itself, so every bar would read flat and neither
outer band would ever be reached. Refused rather than labelled MIXED everywhere.
"""

N_COMPONENTS = 3
"""How many facts vote, and therefore the largest agreement a bar can reach."""


class TrendError(ValueError):
    """Raised for an impossible trend mask, period pair, slope lookback or agreement."""


class Trend(IntEnum):
    """The three states of the agreement score, ordered by it.

    The integer values ascend with the score, and are also the bit positions in a filter mask.
    """

    DOWN = 0
    """Enough components bearish: price under the slow average, it falling, fast beneath it."""
    MIXED = 1
    """Too few components agreeing either way. The deliberate no-trade state."""
    UP = 2
    """Enough components bullish -- :attr:`DOWN` with every test mirrored."""

    @property
    def bit(self) -> int:
        """The bit this trend occupies in a filter mask."""
        return 1 << int(self)


class TrendComponent(IntEnum):
    """The three facts that vote, and the rows of a :class:`TrendGrid`'s vote block.

    Carried beside the score so a review can say *which* one dissented, which a label
    collapsed to a single number cannot.
    """

    PRICE_VS_SLOW = 0
    """Close against the slow average."""
    SLOW_SLOPE = 1
    """The slow average against itself ``slope_lookback`` bars ago."""
    STACK = 2
    """The fast average against the slow one."""


ALL_TRENDS = (1 << len(Trend)) - 1
"""Every trend: the mask that filters nothing, and the default for every archetype."""


class TrendKey(NamedTuple):
    """What one trend label is determined by, and the grid's lookup key."""

    fast_period: int
    slow_period: int
    slope_lookback: int


def trends_mask(trends: Iterable[Trend]) -> int:
    """Combine trends into the bitmask an archetype's ``trend_filter`` takes."""
    mask: int = 0
    for state in trends:
        mask |= Trend(state).bit
    return mask


def trends_in(mask: int) -> tuple[Trend, ...]:
    """Unpack a mask into the trends it admits, in ascending-score order."""
    validate_mask(mask)
    return tuple(t for t in Trend if mask & t.bit)


def validate_mask(mask: int) -> int:
    """Reject a mask that admits nothing, or that sets a bit no trend owns."""
    if mask < 0 or mask & ~ALL_TRENDS:
        msg: str = f"trend mask {mask} sets bits outside 0..{ALL_TRENDS}; use Trend.bit or trends_mask()"
        raise TrendError(msg)
    if mask == 0:
        msg = "trend mask 0 admits no trend, so every combination along it would trade nothing"
        raise TrendError(msg)
    return mask


def describe_mask(mask: int) -> str:
    """Render a mask as a trend list, for a results table or an error message."""
    return "+".join(t.name for t in trends_in(mask))


def validate_periods(fast_period: int, slow_period: int) -> None:
    """Reject a pair the stack component is degenerate or inverted at.

    Equal periods make the stack permanently flat; a fast period longer than the slow one
    reverses what the label means without changing a single name.
    """
    if fast_period < 1:
        msg: str = f"trend_fast_period must be >= 1, got {fast_period}"
        raise TrendError(msg)
    if fast_period >= slow_period:
        msg = (
            f"trend_fast_period {fast_period} is not shorter than trend_slow_period "
            f"{slow_period}, so the stack component would be flat or inverted"
        )
        raise TrendError(msg)


def validate_slope_lookback(slope_lookback: int) -> int:
    """Reject a slope the label is degenerate at -- see :data:`MIN_SLOPE_LOOKBACK`."""
    if slope_lookback < MIN_SLOPE_LOOKBACK:
        msg: str = f"trend slope lookback must be >= {MIN_SLOPE_LOOKBACK}, got {slope_lookback}"
        raise TrendError(msg)
    return slope_lookback


def validate_min_agreement(min_agreement: int) -> int:
    """Reject an agreement no bar could reach, or one every bar reaches.

    ``0`` would put a bar whose components cancel in an outer band; anything past
    :data:`N_COMPONENTS` is unreachable and would label the whole series MIXED.
    """
    if not 1 <= min_agreement <= N_COMPONENTS:
        msg: str = f"trend_min_agreement must lie in 1..{N_COMPONENTS}, got {min_agreement}"
        raise TrendError(msg)
    return min_agreement


def key(fast_period: int, slow_period: int, slope_lookback: int) -> TrendKey:
    """Build a grid key, validating the pair and the slope it will be measured over."""
    validate_periods(int(fast_period), int(slow_period))
    return TrendKey(int(fast_period), int(slow_period), validate_slope_lookback(int(slope_lookback)))


@njit(cache=True)
def _vote(value: float, reference: float) -> int:
    """``+1`` above, ``-1`` below, ``0`` on exact equality -- one definition for all three."""
    if value > reference:
        return 1
    if value < reference:
        return -1
    return 0


@njit(cache=True)
def _components(
    close: FloatArray,
    fast: FloatArray,
    slow: FloatArray,
    slope_lookback: int,
) -> tuple[LabelArray, FloatArray]:
    """Cast the three votes per bar and sum them, ``nan`` until the slope can reach back.

    Price and stack are computed through the warm-up because they are knowable there; the slope
    reads ``0`` because there is nothing to measure, and the score stays ``nan`` so that no
    label is ever taken off two components -- ``docs/roadmap.md`` §M10.3.
    """
    n = close.size
    votes = np.zeros((N_COMPONENTS, n), dtype=np.int8)
    agreement = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        price = _vote(close[i], slow[i])
        stack = _vote(fast[i], slow[i])
        votes[0, i] = price
        votes[2, i] = stack
        if i >= slope_lookback:
            slope = _vote(slow[i], slow[i - slope_lookback])
            votes[1, i] = slope
            agreement[i] = price + slope + stack
    return votes, agreement


@njit(cache=True)
def _trend_of(score: float, min_agreement: int) -> int:
    """Classify one score -- the only place this rule lives, shared by ``label`` and ``gate``."""
    if np.isnan(score):
        return UNDEFINED
    if score <= -min_agreement:
        return Trend.DOWN
    if score >= min_agreement:
        return Trend.UP
    return Trend.MIXED


@njit(cache=True)
def _label(agreement: FloatArray, min_agreement: int) -> LabelArray:
    n = agreement.size
    out = np.empty(n, dtype=np.int8)
    for i in range(n):
        out[i] = _trend_of(agreement[i], min_agreement)
    return out


@njit(cache=True)
def _gate(agreement: FloatArray, min_agreement: int, mask: int) -> BoolArray:
    """One pass from score to boolean, so a sweep combination never builds a label array."""
    n = agreement.size
    out = np.zeros(n, dtype=np.bool_)
    for i in range(n):
        found = _trend_of(agreement[i], min_agreement)
        if found != UNDEFINED:
            out[i] = (mask & (1 << found)) != 0
    return out


def components(
    close: FloatArray,
    fast: FloatArray,
    slow: FloatArray,
    slope_lookback: int,
) -> tuple[LabelArray, FloatArray]:
    """Compute the ``[3, n_bars]`` vote block and the agreement score behind one label.

    Rows are indexed by :class:`TrendComponent`. The score is ``nan`` for the first
    ``slope_lookback`` bars and defined everywhere after, because the NT8 averages emit from
    bar 0 and this module adds no warm-up of its own -- ``docs/roadmap.md`` §M10.3.
    """
    validate_slope_lookback(slope_lookback)
    return _components(
        np.ascontiguousarray(close, dtype=np.float64),
        np.ascontiguousarray(fast, dtype=np.float64),
        np.ascontiguousarray(slow, dtype=np.float64),
        int(slope_lookback),
    )


def label(agreement: FloatArray, min_agreement: int) -> LabelArray:
    """Cut agreement scores into ``int8`` :class:`Trend` values, :data:`UNDEFINED` for ``nan``.

    **Both boundaries fall in the outer bands**, the opposite of :mod:`nqbt.regime` and
    :mod:`nqbt.volume`, because ``min_agreement`` counts components that must agree rather than
    cutting a continuum: exactly ``min_agreement`` agreeing is the case the parameter names.
    """
    validate_min_agreement(min_agreement)
    return _label(np.ascontiguousarray(agreement, dtype=np.float64), int(min_agreement))


def gate(agreement: FloatArray, mask: int, min_agreement: int) -> BoolArray:
    """Test every bar's trend against ``mask``, one boolean per bar.

    An :data:`UNDEFINED` bar passes nothing, :data:`ALL_TRENDS` included, which is why an
    archetype's signal skips this call entirely at the default -- ``docs/roadmap.md`` §M10.3.
    """
    validate_mask(mask)
    validate_min_agreement(min_agreement)
    return _gate(np.ascontiguousarray(agreement, dtype=np.float64), int(min_agreement), int(mask))


@dataclass(frozen=True, slots=True)
class TrendGrid:
    """Every trend label a sweep needs, as scores and the votes behind them.

    Scores rather than labels, because ``min_agreement`` is swept as well and a grid over it
    too would multiply out. ``keys`` is sorted and deduplicated, so :meth:`row` is the only
    supported way from a key back to its row.
    """

    keys: tuple[TrendKey, ...]
    agreement: FloatArray
    """Summed votes, ``[n_keys, n_bars]`` float64, ``nan`` through each slope warm-up."""
    votes: LabelArray
    """The three components, ``[n_keys, 3, n_bars]`` int8 -- see :class:`TrendComponent`."""

    def __len__(self) -> int:
        """Count the bars, not the keys."""
        return int(self.agreement.shape[1])

    def row(self, wanted: TrendKey) -> int:
        """Find the row holding ``wanted``, or say what the grid was built for."""
        try:
            return self.keys.index(wanted)
        except ValueError:
            msg: str = f"trend label {wanted} is not in this grid; built for {list(self.keys)}"
            raise KeyError(msg) from None

    def agreement_for(self, wanted: TrendKey) -> FloatArray:
        """Read one label's agreement score, the raw quantity behind it."""
        return np.asarray(self.agreement[self.row(wanted)])

    def votes_for(self, wanted: TrendKey) -> LabelArray:
        """Read one label's ``[3, n_bars]`` vote block -- rows are :class:`TrendComponent`."""
        return np.asarray(self.votes[self.row(wanted)])

    def component_for(self, wanted: TrendKey, component: TrendComponent) -> LabelArray:
        """Read one component of one label, the form a review reports."""
        return np.asarray(self.votes[self.row(wanted), int(TrendComponent(component))])

    def labels_for(self, wanted: TrendKey, min_agreement: int) -> LabelArray:
        """Label every bar of one series, the stratification key -- see :func:`label`."""
        return label(self.agreement_for(wanted), min_agreement)

    def gate_for(self, wanted: TrendKey, mask: int, min_agreement: int) -> BoolArray:
        """Test every bar of one series against ``mask``, the entry filter -- see :func:`gate`."""
        return gate(self.agreement_for(wanted), mask, min_agreement)

    @property
    def nbytes(self) -> int:
        """Bytes the labels occupy -- what a parallel worker is handed."""
        return self.agreement.nbytes + self.votes.nbytes


def trend_grid(close: FloatArray, keys: Iterable[TrendKey]) -> TrendGrid:
    """Compute every distinct trend label a sweep needs, once.

    The averages are built here and dropped here: a values-carrying
    :class:`~nqbt.conditions.MovingAverageGrid` over the handful of periods these keys name
    costs a fraction of the shared grid's, and nothing outside this function ever sees it --
    ``docs/roadmap.md`` §M10.3.
    """
    ordered: tuple[TrendKey, ...] = tuple(sorted({key(k.fast_period, k.slow_period, k.slope_lookback) for k in keys}))
    if not ordered:
        msg: str = "no trend labels supplied"
        raise TrendError(msg)

    close = np.ascontiguousarray(close, dtype=np.float64)
    periods: list[int] = sorted({p for k in ordered for p in (k.fast_period, k.slow_period)})
    averages: MovingAverageGrid = conditions.moving_average_grid(close, periods, KIND, keep_values=True)

    agreement: FloatArray = np.empty((len(ordered), close.size), dtype=np.float64)
    votes: LabelArray = np.empty((len(ordered), N_COMPONENTS, close.size), dtype=np.int8)
    for i, wanted in enumerate(ordered):
        votes[i], agreement[i] = _components(
            close,
            averages.values_for(wanted.fast_period),
            averages.values_for(wanted.slow_period),
            wanted.slope_lookback,
        )
    return TrendGrid(keys=ordered, agreement=agreement, votes=votes)
