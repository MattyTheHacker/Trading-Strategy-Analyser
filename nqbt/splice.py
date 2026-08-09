"""Combine per-contract exports into one continuous series.

NQ/MNQ are quarterly, so any window longer than a few months spans several contracts.
Splicing is an explicit, inspectable step: it decides a roll date per adjacent pair,
concatenates the resulting segments, and optionally back-adjusts historical prices so
they line up with the current contract (NT8's ``MergeBackAdjusted`` behaviour).

**Volume comparison is bar-aligned, not calendar-aligned.** Comparing whole-day volume
between two contracts silently compares a truncated session against a full one whenever
an export stops mid-roll, which makes the back contract look dominant days before it
really is. Restricting the comparison to timestamps both contracts actually have removes
that bias -- at the cost of revealing that some exports simply do not contain the roll.

**NT8 only serves ~95 days of history per contract.** Measured across all 11 MNQ
contracts, a request for a 7-year range returns each contract's front-month window and
nothing else, ending 4 days before expiry -- the Monday of expiry week. The volume
crossover happens at or just after that boundary, so with NT8 as the data source it is
usually not observable at all.

That is not a defect to work around. NT8 Strategy Analyzer draws on the same coverage, so
the point where one contract's data hands over to the next *is* where NT8 itself switches.
Rolling there keeps Tier 1 and Tier 2 aligned, which matters more than reproducing a
textbook roll rule.

Two roll methods:

``volume_crossover``
    The textbook rule: roll on the first session where the back contract's volume
    overtakes the front's, measured over shared bars. Used automatically when the data
    supports it -- which needs history from a source less restrictive than NT8's.
``coverage_boundary``
    The normal path for NT8-sourced data. Rolls on the first session where the front
    contract's data is partial and the back contract's is complete. The handover volume
    ratio is recorded so a roll that fires suspiciously early can still be spotted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nqbt import ingest, paths
from nqbt.instruments import ContractId

FULL_SESSION_FRACTION = 0.5
"""Share of a contract's median session length below which a session counts as partial."""

METHOD_VOLUME = "volume_crossover"
METHOD_COVERAGE = "coverage_boundary"

EARLY_ROLL_RATIO = 0.4
"""Handover volume ratio below which a coverage-boundary roll looks premature.

At a healthy handover the back contract is already closing on the front -- observed
ratios across the MNQ set run 0.49-0.95. A ratio far below that means the front contract
was still overwhelmingly dominant when its data ran out, so the roll is worth a look.
"""


class SpliceError(RuntimeError):
    """Raised when a continuous series cannot be built from the available contracts."""


@dataclass(slots=True)
class RollDecision:
    """Where and why one contract hands over to the next."""

    front: ContractId
    back: ContractId
    roll_day: pd.Timestamp
    """First trading day served by the *back* contract."""
    method: str
    offset: float
    """``front_close - back_close`` at the last shared bar before the roll."""
    handover_ratio: float
    """Back/front volume over shared bars on the roll session. Above 1.0 means the
    crossover was directly observed; well below :data:`EARLY_ROLL_RATIO` means the roll
    fired while the front contract was still dominant."""
    diagnostics: pd.DataFrame
    notes: list[str] = field(default_factory=list)

    @property
    def crossover_observed(self) -> bool:
        return self.method == METHOD_VOLUME

    @property
    def looks_early(self) -> bool:
        return not self.crossover_observed and self.handover_ratio < EARLY_ROLL_RATIO

    def __str__(self) -> str:
        flag = "  [!] " if self.looks_early else ""
        return (
            f"{flag}{self.front.nt8_name} -> {self.back.nt8_name}  "
            f"roll {self.roll_day.date()}  via {self.method}  "
            f"offset {self.offset:+8.2f}  handover ratio {self.handover_ratio:.2f}"
        )


@dataclass(slots=True)
class SpliceReport:
    """Everything the splicer decided, for eyeballing before trusting a sweep."""

    root: str
    rolls: list[RollDecision]
    segments: pd.DataFrame
    back_adjusted: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def all_crossovers_observed(self) -> bool:
        return all(r.crossover_observed for r in self.rolls)

    @property
    def early_rolls(self) -> list[RollDecision]:
        return [r for r in self.rolls if r.looks_early]

    def summary(self) -> str:
        lines = [
            f"{self.root} continuous series"
            f"{' (back-adjusted)' if self.back_adjusted else ' (raw prices)'}",
            "",
            "Rolls:",
            *(f"  {r}" for r in self.rolls),
            "",
            "Segments:",
            *(
                f"  {r.contract:<12} {r.start.date()} -> {r.end.date()}  {r.bars:>7,} bars"
                f"  shift {r.shift:+.2f}"
                for r in self.segments.itertuples()
            ),
        ]
        if self.warnings:
            lines += ["", "Warnings:", *(f"  [!] {w}" for w in self.warnings)]
        return "\n".join(lines)


# -- roll detection -----------------------------------------------------------


def _in_session(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["in_session"]]


def _session_bar_counts(frame: pd.DataFrame) -> pd.Series:
    return frame.groupby("trading_day").size()


def overlap_volume(front: pd.DataFrame, back: pd.DataFrame) -> pd.DataFrame:
    """Per-session volume for both contracts over the bars they share.

    Restricting to shared timestamps is what makes the comparison meaningful when one
    export ends mid-session: otherwise a 120-bar stub is compared against a 1380-bar
    day and the back contract wins for the wrong reason.
    """
    fa, ba = _in_session(front), _in_session(back)
    common = fa.index.intersection(ba.index)
    if len(common) == 0:
        return pd.DataFrame(
            columns=["front_volume", "back_volume", "shared_bars", "ratio", "back_wins"]
        )

    fc, bc = fa.loc[common], ba.loc[common]
    days = fc["trading_day"]
    table = pd.DataFrame(
        {
            "front_volume": fc.groupby(days)["volume"].sum(),
            "back_volume": bc.groupby(days)["volume"].sum(),
            "shared_bars": fc.groupby(days).size(),
        }
    )
    table["ratio"] = table["back_volume"] / table["front_volume"].where(
        table["front_volume"] > 0
    )
    table["back_wins"] = table["back_volume"] > table["front_volume"]
    return table


def detect_roll(
    front_id: ContractId,
    back_id: ContractId,
    front: pd.DataFrame,
    back: pd.DataFrame,
    *,
    confirm_sessions: int = 1,
    allow_coverage_boundary: bool = True,
) -> RollDecision:
    """Choose the roll date for one adjacent contract pair."""
    table = overlap_volume(front, back)
    notes: list[str] = []

    if table.empty:
        raise SpliceError(
            f"{front_id.nt8_name} and {back_id.nt8_name} share no in-session bars; "
            "cannot determine a roll date"
        )

    roll_day = _first_confirmed_crossover(table, confirm_sessions)
    method = METHOD_VOLUME

    if roll_day is None:
        peak = table["ratio"].max()
        notes.append(
            f"no volume crossover across {len(table)} shared sessions (peak ratio "
            f"{peak:.2f}); expected with NT8 data, which stops ~4 days before expiry"
        )
        if not allow_coverage_boundary:
            raise SpliceError(
                f"{front_id.nt8_name} -> {back_id.nt8_name}: {notes[-1]}. "
                "Supply history from a source that covers the crossover, or allow the "
                "coverage-boundary roll."
            )
        roll_day = _coverage_boundary_roll(front, back)
        method = METHOD_COVERAGE
        if roll_day is None:
            raise SpliceError(
                f"{front_id.nt8_name} -> {back_id.nt8_name}: no volume crossover and "
                "no usable coverage boundary; the two exports may not overlap enough "
                "to splice"
            )
        notes.append(
            f"rolled at {roll_day.date()}, where the front contract's data ends and the "
            "back contract's takes over -- the same handover NT8 itself makes"
        )

    offset = _boundary_offset(front, back, roll_day, front_id, back_id)
    ratio = float(table["ratio"].get(roll_day, table["ratio"].iloc[-1]))

    return RollDecision(
        front=front_id,
        back=back_id,
        roll_day=roll_day,
        method=method,
        offset=offset,
        handover_ratio=ratio,
        diagnostics=table,
        notes=notes,
    )


def _first_confirmed_crossover(
    table: pd.DataFrame, confirm_sessions: int
) -> pd.Timestamp | None:
    """First session where the back contract leads and keeps leading."""
    wins = table["back_wins"].to_numpy()
    n = wins.size
    for i in range(n):
        if not wins[i]:
            continue
        window = wins[i : i + confirm_sessions]
        # Near the end of the overlap, accept a short window rather than miss the roll.
        if window.all():
            return pd.Timestamp(table.index[i])
    return None


def _coverage_boundary_roll(front: pd.DataFrame, back: pd.DataFrame) -> pd.Timestamp | None:
    """First session where the front contract is partial but the back is complete."""
    fa, ba = _in_session(front), _in_session(back)
    fcount, bcount = _session_bar_counts(fa), _session_bar_counts(ba)
    if fcount.empty or bcount.empty:
        return None

    f_full = fcount.median() * FULL_SESSION_FRACTION
    b_full = bcount.median() * FULL_SESSION_FRACTION

    shared_days = fcount.index.intersection(bcount.index)
    for day in shared_days:
        if fcount[day] < f_full and bcount[day] >= b_full:
            return pd.Timestamp(day)

    # No shared partial day: hand over the first session the back contract covers
    # beyond the front contract's data.
    beyond = bcount.index[bcount.index > fcount.index.max()]
    return pd.Timestamp(beyond[0]) if len(beyond) else None


def _boundary_offset(
    front: pd.DataFrame,
    back: pd.DataFrame,
    roll_day: pd.Timestamp,
    front_id: ContractId,
    back_id: ContractId,
) -> float:
    """Price gap between the two contracts at the last bar they share before the roll."""
    fa, ba = _in_session(front), _in_session(back)
    fa = fa[fa["trading_day"] < roll_day]
    ba = ba[ba["trading_day"] < roll_day]
    common = fa.index.intersection(ba.index)
    if len(common) == 0:
        raise SpliceError(
            f"{front_id.nt8_name} -> {back_id.nt8_name}: no shared bar before "
            f"{roll_day.date()} to measure the back-adjustment offset from"
        )
    ts = common[-1]
    return float(fa.loc[ts, "close"] - ba.loc[ts, "close"])


# -- continuous series --------------------------------------------------------


def build_continuous(
    contracts: list[ContractId],
    frames: dict[ContractId, pd.DataFrame],
    *,
    back_adjust: bool = False,
    confirm_sessions: int = 1,
    allow_coverage_boundary: bool = True,
) -> tuple[pd.DataFrame, SpliceReport]:
    """Splice contracts into one continuous in-session series.

    Returns the series and a :class:`SpliceReport` describing every decision made.
    """
    if len(contracts) < 1:
        raise SpliceError("need at least one contract to build a series")
    contracts = sorted(contracts)
    root = contracts[0].root

    rolls = [
        detect_roll(
            f,
            b,
            frames[f],
            frames[b],
            confirm_sessions=confirm_sessions,
            allow_coverage_boundary=allow_coverage_boundary,
        )
        for f, b in zip(contracts, contracts[1:])
    ]

    _check_roll_monotonicity(rolls)

    # Shift each segment by the offsets of every roll that comes after it, so the most
    # recent contract keeps its true prices and history is dragged into line with it.
    offsets = [r.offset for r in rolls]
    shifts = [0.0] * len(contracts)
    if back_adjust:
        running = 0.0
        for i in range(len(contracts) - 2, -1, -1):
            running -= offsets[i]
            shifts[i] = running

    pieces: list[pd.DataFrame] = []
    rows: list[dict] = []
    warnings: list[str] = []

    for i, contract in enumerate(contracts):
        start = rolls[i - 1].roll_day if i > 0 else None
        end = rolls[i].roll_day if i < len(rolls) else None

        seg = _in_session(frames[contract])
        if start is not None:
            seg = seg[seg["trading_day"] >= start]
        if end is not None:
            seg = seg[seg["trading_day"] < end]
        if seg.empty:
            warnings.append(
                f"{contract.nt8_name} contributes no bars; its window was fully "
                "consumed by the surrounding rolls"
            )
            continue

        seg = seg.copy()
        if shifts[i]:
            seg[["open", "high", "low", "close"]] += shifts[i]
        seg["contract"] = contract.nt8_name

        pieces.append(seg)
        rows.append(
            {
                "contract": contract.nt8_name,
                "start": seg["trading_day"].iloc[0],
                "end": seg["trading_day"].iloc[-1],
                "bars": len(seg),
                "shift": shifts[i],
            }
        )

    if not pieces:
        raise SpliceError("splicing produced no bars")

    series = pd.concat(pieces).sort_index(kind="stable")
    series = series.drop(columns=["in_session"])

    if not series.index.is_unique:
        dupes = int(series.index.duplicated().sum())
        raise SpliceError(
            f"continuous series has {dupes} duplicate timestamps; segment boundaries overlap"
        )

    if back_adjust and float(series[["open", "high", "low", "close"]].min().min()) <= 0:
        warnings.append(
            "back-adjustment drove prices to or below zero; the raw series is the only "
            "usable one over this window"
        )

    # A coverage-boundary roll is the expected path for NT8 data and is not itself worth
    # warning about. Only flag one that fired while the front contract was still
    # dominant, which is the case that could actually distort a backtest.
    for roll in rolls:
        if roll.looks_early:
            warnings.append(
                f"{roll.front.nt8_name} -> {roll.back.nt8_name}: rolled at "
                f"{roll.roll_day.date()} with the back contract at only "
                f"{roll.handover_ratio:.0%} of front volume; verify this handover"
            )

    report = SpliceReport(
        root=root,
        rolls=rolls,
        segments=pd.DataFrame(rows),
        back_adjusted=back_adjust,
        warnings=warnings,
    )
    return series, report


def _check_roll_monotonicity(rolls: list[RollDecision]) -> None:
    for earlier, later in zip(rolls, rolls[1:]):
        if later.roll_day <= earlier.roll_day:
            raise SpliceError(
                f"roll dates are out of order: {earlier.front.nt8_name}->"
                f"{earlier.back.nt8_name} rolls {earlier.roll_day.date()} but "
                f"{later.front.nt8_name}->{later.back.nt8_name} rolls "
                f"{later.roll_day.date()}"
            )


def continuous_path(root: str, back_adjust: bool, cache_dir: Path = paths.CACHE_DIR) -> Path:
    suffix = "backadj" if back_adjust else "raw"
    return cache_dir / "continuous" / f"{root}_{suffix}.parquet"


def splice_root(
    root: str,
    *,
    data_dir=paths.DATA_DIR,
    cache_dir=paths.CACHE_DIR,
    back_adjust: bool = False,
    confirm_sessions: int = 1,
    allow_coverage_boundary: bool = True,
    write: bool = True,
) -> tuple[pd.DataFrame, SpliceReport]:
    """Build (and optionally cache) the continuous series for one root symbol."""
    contracts = sorted(ingest.discover_exports(data_dir, root=root))
    if not contracts:
        raise SpliceError(f"no contracts found for {root} in {data_dir}")
    frames = {c: ingest.load_contract(c, cache_dir) for c in contracts}

    series, report = build_continuous(
        contracts,
        frames,
        back_adjust=back_adjust,
        confirm_sessions=confirm_sessions,
        allow_coverage_boundary=allow_coverage_boundary,
    )

    if write:
        out = continuous_path(root, back_adjust, cache_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        series.to_parquet(out, engine="pyarrow", compression="zstd", index=True)

    return series, report


def load_continuous(
    root: str, *, back_adjust: bool = False, cache_dir=paths.CACHE_DIR
) -> pd.DataFrame:
    path = continuous_path(root, back_adjust, cache_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no continuous series for {root}; run `nqbt splice --root {root}"
            f"{' --back-adjust' if back_adjust else ''}` first"
        )
    return pd.read_parquet(path)
