"""The registry of strategy archetypes, and what a sweep needs to know about each.

Before this existed, :mod:`nqbt.sweep` named ``DeadCatParams`` in six places, so a second
archetype meant forking the sweep rather than registering with it. An
:class:`Archetype` is the small bundle of facts that lets one sweep drive any of them:
which parameter class it takes, which of those fields are legal axes, which periods and
series its signal will read, and how to run one combination.

**Strategy is an axis *above* the dataset**, in the same sense that bar resolution (M13)
and contract (M14) are: it selects which :class:`~nqbt.context.Dataset` gets built, rather
than varying a value inside one. That is why it lives here and not in
:class:`~nqbt.sim.types.DeadCatParams`.

This module deliberately holds **no strategy logic**. Each archetype's signal and run
functions stay in :mod:`nqbt.sim`; what is recorded here is only how to reach them. The
shared bracket engine is extracted during M18 (#38), not here -- with two archetypes it
would be an abstraction designed from one example wearing a second as a disguise, since
PullBackAndGo already reuses ``simulate_deadcat`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from nqbt import timeofday
from nqbt.context import ContextSpec
from nqbt.sim import crossover, pullback, runner
from nqbt.sim.types import DeadCatParams, EmaCrossoverParams, PullBackAndGoParams

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import numpy as np
    import pandas as pd

    from nqbt.trades import LegMatrix


@runtime_checkable
class Params(Protocol):
    """One combination's parameters: what the sweep requires of any ``params_cls``.

    Structural rather than a union of the concrete classes, because the point of the
    registry is that :mod:`nqbt.sweep` does not name them. Two requirements, both of which
    the sweep genuinely exercises: ``__dataclass_fields__`` so
    :func:`dataclasses.replace` can build a combination from the base, and ``as_dict`` so
    the parameters can be written alongside the summary as results columns.
    """

    __dataclass_fields__: ClassVar[dict[str, Any]]  # type: ignore[explicit-any]

    def as_dict(self) -> dict: ...


class ArchetypeError(KeyError):
    """Raised for an unknown or ambiguous archetype."""


class Tier2Status(StrEnum):
    """How much NinjaTrader evidence an archetype's results carry.

    **Not bookkeeping.** "Validated against NT8" used to be a project-wide fact, true of
    the only archetype there was. Once originals exist -- developed in Python with no
    NinjaScript until one looks worth trading -- it becomes a per-archetype property, and a
    results table that ranks a reconciled archetype against an unreconciled one is
    comparing a measurement against an assumption. Carrying it as a column means the
    ranking cannot hide that. See ``docs/roadmap.md`` § "An original archetype has no C#
    to lose to".
    """

    RECONCILED = "reconciled"
    """Diffed leg-for-leg against a real NT8 Strategy Analyzer Trades export."""

    TIER1_ONLY = "tier-1-only"
    """Ported from C#, or original, but never checked against a trade list."""

    NOT_CHECKED = "not-checked"
    """No reconciliation attempted and none planned yet."""


def _needs_time_of_day(values: Mapping[str, Sequence]) -> bool:
    """Whether any combination actually restricts its entries to some session phases.

    The same treatment VWAP gets, and for the same reason: the default admits every phase,
    so a grid that never narrows it reads nothing and should not pay for three arrays over
    the whole series.
    """
    return any(int(v) != timeofday.ALL_PHASES for v in values.get("phase_filter", ()))


def moving_average_context(values: Mapping[str, Sequence]) -> ContextSpec:
    """The context spec shared by every archetype built on the MA grids plus VWAP.

    ``values`` maps each parameter name to every value the sweep will try for it, so a
    period that is only swept still gets its grid built. Both current archetypes read
    exactly these series -- one below its averages and one above -- which is why this is a
    module-level function rather than a method each of them overrides.

    VWAP is requested only when some combination actually switches it on. It is the one
    series here that no combination reads by accident, so leaving it out when unused is
    free; the periods cannot be treated that way, because ``dead_axes`` already refuses the
    case where a swept period's toggle is off everywhere and the surviving cases are all
    live.
    """
    ema = {int(v) for v in values.get("ema_period", ())}
    sma = {int(v) for v in values.get("fast_sma_period", ())}
    sma |= {int(v) for v in values.get("slow_sma_period", ())}
    return ContextSpec(
        ema_periods=tuple(sorted(ema)),
        sma_periods=tuple(sorted(sma)),
        needs_vwap=any(values.get("use_vwap", ())),
        needs_time_of_day=_needs_time_of_day(values),
    )


def crossover_context(values: Mapping[str, Sequence]) -> ContextSpec:
    """What EmaCrossover reads: two EMA grids, their raw values, and an ATR.

    Two things separate it from :func:`moving_average_context`. It needs
    ``needs_ma_values`` because its rule compares two averages to *each other*, which no
    boolean close-versus-average gate can answer -- and that is the 8x memory the grids
    otherwise avoid, so it is requested by the one archetype that needs it rather than
    switched on globally. And the ATR is requested only when some combination uses the ATR
    stop, the same way VWAP is: a swing-stop-only sweep should not build one.
    """
    fast = {int(v) for v in values.get("fast_period", ())}
    slow = {int(v) for v in values.get("slow_period", ())}
    atr = {int(v) for v in values.get("atr_period", ())} if any(values.get("use_atr_stop", ())) else set()
    return ContextSpec(
        ema_periods=tuple(sorted(fast | slow)),
        atr_periods=tuple(sorted(atr)),
        needs_time_of_day=_needs_time_of_day(values),
        needs_ma_values=True,
    )


# A period only matters when its filter is switched on. Shared by both archetypes because
# both spell the toggles the same way; an archetype that does not can pass its own.
MA_GATES: Mapping[str, str] = {
    "ema_period": "use_ema",
    "fast_sma_period": "use_fast_sma",
    "slow_sma_period": "use_slow_sma",
}

CROSSOVER_GATES: Mapping[str, str] = {
    "atr_period": "use_atr_stop",
    "atr_stop_multiple": "use_atr_stop",
}
"""EmaCrossover has no MA toggles -- both averages are always read -- but its two stop modes
are exclusive, so the ATR fields are dead when every combination uses the swing stop.

``swing_lookback`` cannot be guarded the same way: ``dead_axes`` asks whether a toggle is
true *somewhere*, which cannot express "dead when this one is never false".
"""


@dataclass(frozen=True, slots=True)
class Archetype:
    """How to sweep one strategy.

    A dataclass rather than a base class with subclasses: there is no behaviour to
    inherit, only a handful of facts and two function references, and the rubric's warning
    against a class hierarchy for one archetype applies with two just as well. Frozen so a
    registered archetype cannot be mutated by the code that looks it up.
    """

    name: str
    """The registry key, and the value written to the results table's ``strategy``."""

    params_cls: type
    """The dataclass a combination is an instance of. Replaces ``Grid.base``'s hardcoding."""

    run: Callable[..., pd.DataFrame]
    """Simulate one combination and return its leg-level trade log.

    Spelled with ``...`` rather than ``[Dataset, Params, Instrument]`` because each
    archetype's ``run`` accepts only *its own* parameter class, which is a generic
    ``Archetype[P]`` rather than anything a plain callable type can say. Making the
    class generic belongs with the rest of the typing work (#55); until then the
    runtime check that matters -- base against ``params_cls`` -- is enforced in
    ``Grid.__post_init__``.
    """

    legs: Callable[..., LegMatrix]
    """The same simulation, stopping at the raw leg matrix.

    Registered beside :attr:`run` rather than derived from it because it is the *earlier*
    of the two: ``run`` is this plus a DataFrame. A sweep takes this one and summarises the
    matrix directly, which is where #33's speedup comes from -- building and aggregating a
    trade log it discards was 71% of a combination.

    Not optional. An archetype registered with only ``run`` would silently be the slow one
    in a sweep, and the reason to notice would be a wall clock rather than an error.
    """

    tier2: Tier2Status
    """See :class:`Tier2Status` -- this reaches the results table, deliberately."""

    signal: Callable[..., np.ndarray]
    """Compute this archetype's per-bar entry signal from a :class:`Dataset`.

    Recorded separately from :attr:`run` because the random-entry control arm (M7a) needs
    the *real* signal in order to match its own draws against it -- how many entries there
    were and at which times of session -- before handing a substitute back to :attr:`run`.
    Without it the null would have to recompute the signal itself, which is a second
    definition of the entry rule and exactly what this registry exists to prevent.
    """

    gated_by: Mapping[str, str] = field(default_factory=lambda: MA_GATES)
    """Axis -> the toggle that has to be on for it to change anything. Feeds ``dead_axes``."""

    context_for: Callable[[Mapping[str, Sequence]], ContextSpec] = moving_average_context
    """Which precomputed series this archetype's signal reads."""

    not_sweepable: frozenset[str] = frozenset({"target_r_multiples"})
    """Fields that are not legal axes.

    Listed rather than inferred. The rule today happens to be "the tuple-valued ones", but
    deriving it from the value's type would silently start sweeping a new tuple field, or
    silently stop sweeping a scalar one that gained a default of ``None`` -- and a
    disappearing axis is the failure mode #60 was filed about, because it multiplies
    nothing rather than raising.
    """

    @property
    def sweepable(self) -> frozenset[str]:
        """Every field of :attr:`params_cls` that may be given a list of values.

        Read from :func:`dataclasses.fields` rather than ``__slots__``. ``__slots__``
        holds only the fields declared on the class itself, so the moment a params class
        inherits one it would vanish from this set -- and an axis that is silently dropped
        does not raise, it just makes every combination along it identical. See #60.
        """
        return frozenset(f.name for f in fields(self.params_cls)) - self.not_sweepable


DEADCATBOUNCE = Archetype(
    name="DeadCatBounce",
    params_cls=DeadCatParams,
    run=runner.run_deadcat,
    legs=runner.deadcat_legs,
    signal=runner.deadcat_signal,
    tier2=Tier2Status.RECONCILED,
)

PULLBACKANDGO = Archetype(
    name="PullBackAndGo",
    params_cls=PullBackAndGoParams,
    run=pullback.run_pullbackandgo,
    legs=pullback.pullbackandgo_legs,
    signal=pullback.pullback_signal,
    tier2=Tier2Status.RECONCILED,
)

EMACROSSOVER = Archetype(
    name="EmaCrossover",
    params_cls=EmaCrossoverParams,
    run=crossover.run_crossover,
    legs=crossover.crossover_legs,
    signal=crossover.crossover_signal,
    tier2=Tier2Status.TIER1_ONLY,
    gated_by=CROSSOVER_GATES,
    context_for=crossover_context,
)
"""The first original archetype: no NinjaScript, and TIER1_ONLY until there is one.

Registering it is the point of M17 -- ``sweep.py`` names neither its parameter class nor its
run function, so the second entry mechanism and the first signal exit arrive without the
sweep changing at all.
"""

_REGISTRY: dict[str, Archetype] = {a.name: a for a in (DEADCATBOUNCE, EMACROSSOVER, PULLBACKANDGO)}

DEFAULT = DEADCATBOUNCE
"""What a ``Grid`` assumes when nothing says otherwise.

DeadCatBounce keeps the slot because it is the archetype every stored result, captured
trade log and reconciliation was produced with. Changing it would silently reinterpret
them.
"""


def register(archetype: Archetype) -> Archetype:
    """Add an archetype, refusing to shadow one that already exists.

    Rejecting a duplicate name matters more than it looks: ``name`` is written into the
    results table, so two archetypes sharing one would merge into a single row group in
    DuckDB and read as one strategy measured twice.
    """
    if archetype.name in _REGISTRY:
        msg = f"archetype {archetype.name!r} is already registered"
        raise ArchetypeError(msg)
    _REGISTRY[archetype.name] = archetype
    return archetype


def get(name: str) -> Archetype:
    if name not in _REGISTRY:
        msg = f"unknown archetype {name!r}; known: {sorted(_REGISTRY)}"
        raise ArchetypeError(msg)
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


def all_archetypes() -> list[Archetype]:
    return [_REGISTRY[n] for n in names()]


def for_params(params: Params) -> Archetype:
    """The archetype whose ``params_cls`` is exactly ``type(params)``.

    Lets ``Grid.of(base=PullBackAndGoParams())`` pick the right archetype without the
    caller naming it twice. Ambiguity raises rather than picking one, because guessing
    here would attribute a whole sweep to the wrong strategy.
    """
    matches = [a for a in all_archetypes() if a.params_cls is type(params)]
    if not matches:
        msg = (
            f"no registered archetype takes {type(params).__name__}; "
            f"pass archetype= explicitly. Known: {names()}"
        )
        raise ArchetypeError(
            msg,
        )
    if len(matches) > 1:
        msg = f"{type(params).__name__} is shared by {[a.name for a in matches]}; pass archetype= explicitly"
        raise ArchetypeError(
            msg,
        )
    return matches[0]
