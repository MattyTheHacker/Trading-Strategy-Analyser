"""Combine per-contract exports into one continuous series.

NQ/MNQ are quarterly, so any window longer than a few months spans several contracts. This is
an explicit, inspectable step: decide a roll date per adjacent pair, concatenate the segments,
and optionally back-adjust historical prices to line up with the current contract (NT8's
``MergeBackAdjusted`` behaviour).

**Volume comparison is bar-aligned, not calendar-aligned**, and a session with too few shared
bars is marked inconclusive rather than allowed to decide. Both rules and their evidence:
``docs/nt8-fidelity.md``, "Contract data". Why a data-derived roll date is deliberately not
reconciled against NT8: ``docs/roadmap.md``, "Decisions taken".

Two roll methods:

``volume_crossover``
    Roll on the first *conclusive* session where the back contract's volume overtakes the
    front's, measured over shared bars. The normal path; every roll in both roots uses it.
``coverage_boundary``
    The fallback for a contract exported without the crossover in range: the first session
    where the front contract's data is partial and the back contract's is complete.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

import numpy as np
import pandas as pd

from nqbt import indicators, ingest, paths

if TYPE_CHECKING:
    from pathlib import Path

    from nqbt.arrays import BoolArray, FloatArray, OffsetArray
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
        """Whether the roll day came from an observed volume crossover."""
        return self.method == METHOD_VOLUME

    @property
    def looks_early(self) -> bool:
        """Whether the roll fired while the front contract was still dominant."""
        return not self.crossover_observed and self.handover_ratio < EARLY_ROLL_RATIO

    @override
    def __str__(self) -> str:
        flag: str = "  [!] " if self.looks_early else ""
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
        """Whether every roll in the series came from an observed crossover."""
        return all(r.crossover_observed for r in self.rolls)

    @property
    def early_rolls(self) -> list[RollDecision]:
        """The rolls that fired while the front contract was still dominant."""
        return [r for r in self.rolls if r.looks_early]

    def summary(self) -> str:
        """The whole report as text, for eyeballing before trusting a sweep."""
        lines: list[str] = [
            f"{self.root} continuous series{' (back-adjusted)' if self.back_adjusted else ' (raw prices)'}",
            "",
            "Rolls:",
            *(f"  {r}" for r in self.rolls),
            "",
            "Segments:",
            *(
                f"  {r.contract:<12} {r.start:%Y-%m-%d} -> {r.end:%Y-%m-%d}  {r.bars:>7,} bars"
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


def _session_bar_counts(frame: pd.DataFrame) -> pd.Series[int]:
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
        return pd.DataFrame(columns=["front_volume", "back_volume", "shared_bars", "ratio", "back_wins"])

    fc, bc = fa.loc[common], ba.loc[common]
    days: pd.Series[int] = fc["trading_day"]
    table: pd.DataFrame = pd.DataFrame(
        {
            "front_volume": fc.groupby(days)["volume"].sum(),
            "back_volume": bc.groupby(days)["volume"].sum(),
            "shared_bars": fc.groupby(days).size(),
        },
    )
    table["ratio"] = table["back_volume"] / table["front_volume"].where(table["front_volume"] > 0)
    table["back_wins"] = table["back_volume"] > table["front_volume"]
    # A verdict is only as good as the window it was measured over. NT8's data has a
    # near-empty session a few days before most rolls -- typically the Sunday 18:00-19:00
    # ET hour and nothing else -- which lands squarely where the crossover is decided.
    table["conclusive"] = table["shared_bars"] >= (table["shared_bars"].median() * FULL_SESSION_FRACTION)
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
    table: pd.DataFrame = overlap_volume(front, back)
    notes: list[str] = []

    if table.empty:
        msg: str = (
            f"{front_id.nt8_name} and {back_id.nt8_name} share no in-session bars; "
            "cannot determine a roll date"
        )
        raise SpliceError(
            msg,
        )

    roll_day: pd.Timestamp | None = _first_confirmed_crossover(table, confirm_sessions)
    method: str = METHOD_VOLUME

    if roll_day is None:
        peak: float = table["ratio"].max()
        notes.append(
            f"no volume crossover across {len(table)} shared sessions (peak ratio "
            f"{peak:.2f}); expected with NT8 data, which stops ~4 days before expiry",
        )
        if not allow_coverage_boundary:
            msg = (
                f"{front_id.nt8_name} -> {back_id.nt8_name}: {notes[-1]}. "
                "Supply history from a source that covers the crossover, or allow the "
                "coverage-boundary roll."
            )
            raise SpliceError(
                msg,
            )
        roll_day = _coverage_boundary_roll(front, back)
        method = METHOD_COVERAGE
        if roll_day is None:
            msg = (
                f"{front_id.nt8_name} -> {back_id.nt8_name}: no volume crossover and "
                "no usable coverage boundary; the two exports may not overlap enough "
                "to splice"
            )
            raise SpliceError(
                msg,
            )
        notes.append(
            f"rolled at {roll_day.date()}, where the front contract's data ends and the "
            "back contract's takes over -- the same handover NT8 itself makes",
        )

    offset: float = _boundary_offset(front, back, roll_day, front_id, back_id)
    ratio: float = float(table["ratio"].get(roll_day, table["ratio"].iloc[-1]))

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


def _first_confirmed_crossover(table: pd.DataFrame, confirm_sessions: int) -> pd.Timestamp | None:
    """First session where the back contract leads and keeps leading.

    Inconclusive sessions are skipped rather than allowed to decide, but are still eligible to
    be *confirmed* by -- the run only has to start somewhere trustworthy. See
    ``docs/nt8-fidelity.md``, "Contract data".
    """
    wins: BoolArray = table["back_wins"].to_numpy()
    conclusive: BoolArray = table["conclusive"].to_numpy()
    n: int = wins.size
    for i in range(n):
        if not (wins[i] and conclusive[i]):
            continue
        window: BoolArray = wins[i : i + confirm_sessions]
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

    f_full: float = fcount.median() * FULL_SESSION_FRACTION
    b_full: float = bcount.median() * FULL_SESSION_FRACTION

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
        msg: str = (
            f"{front_id.nt8_name} -> {back_id.nt8_name}: no shared bar before "
            f"{roll_day.date()} to measure the back-adjustment offset from"
        )
        raise SpliceError(
            msg,
        )
    ts = common[-1]
    return float(fa.loc[ts, "close"] - ba.loc[ts, "close"])


# -- continuous series --------------------------------------------------------


def build_continuous(  # noqa: C901 - the roll rules it applies are each a branch
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
        msg: str = "need at least one contract to build a series"
        raise SpliceError(msg)
    contracts = sorted(contracts)
    root: str = contracts[0].root

    rolls: list[RollDecision] = [
        detect_roll(
            f,
            b,
            frames[f],
            frames[b],
            confirm_sessions=confirm_sessions,
            allow_coverage_boundary=allow_coverage_boundary,
        )
        for f, b in itertools.pairwise(contracts)
    ]

    _check_roll_monotonicity(rolls)

    # Shift each segment by the offsets of every roll that comes after it, so the most
    # recent contract keeps its true prices and history is dragged into line with it.
    offsets: list[float] = [r.offset for r in rolls]
    shifts: list[float] = [0.0] * len(contracts)
    if back_adjust:
        running: float = 0.0
        for i in range(len(contracts) - 2, -1, -1):
            running -= offsets[i]
            shifts[i] = running

    pieces: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for i, contract in enumerate(contracts):
        start: pd.Timestamp | None = rolls[i - 1].roll_day if i > 0 else None
        end: pd.Timestamp | None = rolls[i].roll_day if i < len(rolls) else None

        seg: pd.DataFrame = _in_session(frames[contract])
        if start is not None:
            seg = seg[seg["trading_day"] >= start]
        if end is not None:
            seg = seg[seg["trading_day"] < end]
        if seg.empty:
            warnings.append(
                f"{contract.nt8_name} contributes no bars; its window was fully "
                "consumed by the surrounding rolls",
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
            },
        )

    if not pieces:
        msg = "splicing produced no bars"
        raise SpliceError(msg)

    series: pd.DataFrame = pd.concat(pieces).sort_index(kind="stable")
    series = series.drop(columns=["in_session"])

    if not series.index.is_unique:
        dupes: int = int(series.index.duplicated().sum())
        msg = f"continuous series has {dupes} duplicate timestamps; segment boundaries overlap"
        raise SpliceError(msg)

    if back_adjust and float(series[["open", "high", "low", "close"]].min().min()) <= 0:
        warnings.append(
            "back-adjustment drove prices to or below zero; the raw series is the only "
            "usable one over this window",
        )

    # A coverage-boundary roll is the expected path for NT8 data and is not itself worth
    # warning about. Only flag one that fired while the front contract was still
    # dominant, which is the case that could actually distort a backtest.
    warnings.extend(
        f"{roll.front.nt8_name} -> {roll.back.nt8_name}: rolled at "
        f"{roll.roll_day.date()} with the back contract at only "
        f"{roll.handover_ratio:.0%} of front volume; verify this handover"
        for roll in rolls
        if roll.looks_early
    )

    report: SpliceReport = SpliceReport(
        root=root,
        rolls=rolls,
        segments=pd.DataFrame(rows),
        back_adjusted=back_adjust,
        warnings=warnings,
    )
    return series, report


def _check_roll_monotonicity(rolls: list[RollDecision]) -> None:
    for earlier, later in itertools.pairwise(rolls):
        if later.roll_day <= earlier.roll_day:
            msg: str = (
                f"roll dates are out of order: {earlier.front.nt8_name}->"
                f"{earlier.back.nt8_name} rolls {earlier.roll_day.date()} but "
                f"{later.front.nt8_name}->{later.back.nt8_name} rolls "
                f"{later.roll_day.date()}"
            )
            raise SpliceError(
                msg,
            )


# -- roll seams ---------------------------------------------------------------


SEAM_COLUMNS = [
    "previous_contract",
    "contract",
    "previous_bar",
    "gap_minutes",
    "carry_over",
    "true_range",
]
"""Columns of :func:`roll_seams`, in order."""


def roll_seams(series: pd.DataFrame) -> pd.DataFrame:
    """The first bar of each contract's segment, with the break it sits across.

    ``carry_over`` is the seam bar's open against the previous bar's close and ``gap_minutes``
    the wall-clock distance between them. On a back-adjusted series the carry-over holds no
    contract basis at all, so it is a price move rather than a splice artefact --
    ``docs/nt8-fidelity.md``, "True Range at a roll boundary".
    """
    if "contract" not in series.columns:
        msg = "series has no contract column; roll seams can only be found on a spliced series"
        raise SpliceError(msg)

    contracts = series["contract"].to_numpy()
    at: OffsetArray = np.flatnonzero(contracts[1:] != contracts[:-1]) + 1
    high, low, close = (series[column].to_numpy(np.float64) for column in ("high", "low", "close"))
    true_range: FloatArray = indicators.nt8_true_range(high, low, close)
    stamps: pd.DatetimeIndex = pd.DatetimeIndex(series.index)

    return pd.DataFrame(
        {
            "previous_contract": contracts[at - 1],
            "contract": contracts[at],
            "previous_bar": stamps[at - 1],
            "gap_minutes": (stamps[at] - stamps[at - 1]).total_seconds() / 60.0,
            "carry_over": series["open"].to_numpy(np.float64)[at] - close[at - 1],
            "true_range": true_range[at],
        },
        index=stamps[at],
        columns=SEAM_COLUMNS,
    )


def continuous_path(root: str, *, back_adjust: bool, cache_dir: Path = paths.CACHE_DIR) -> Path:
    """Where one root's spliced continuous series is cached."""
    suffix: str = "backadj" if back_adjust else "raw"
    return cache_dir / "continuous" / f"{root}_{suffix}.parquet"


def splice_root(
    root: str,
    *,
    data_dir: Path = paths.ARCHIVE_DIR,
    cache_dir: Path = paths.CACHE_DIR,
    back_adjust: bool = False,
    confirm_sessions: int = 1,
    allow_coverage_boundary: bool = True,
    write: bool = True,
) -> tuple[pd.DataFrame, SpliceReport]:
    """Build (and optionally cache) the continuous series for one root symbol."""
    scan: ingest.ExportScan = ingest.discover_exports(data_dir, root=root)
    contracts: list[ContractId] = sorted(scan.exports)
    if not contracts:
        msg: str = f"no contracts found for {root} in {data_dir}"
        raise SpliceError(msg)
    frames: dict[ContractId, pd.DataFrame] = {c: ingest.load_contract(c, cache_dir) for c in contracts}

    series, report = build_continuous(
        contracts,
        frames,
        back_adjust=back_adjust,
        confirm_sessions=confirm_sessions,
        allow_coverage_boundary=allow_coverage_boundary,
    )
    report.warnings.extend(f"skipped {skip}" for skip in scan.skipped)

    if write:
        out: Path = continuous_path(root, back_adjust=back_adjust, cache_dir=cache_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        series.to_parquet(out, engine="pyarrow", compression="zstd", index=True)

    return series, report


def load_continuous(
    root: str,
    *,
    back_adjust: bool = False,
    cache_dir: Path = paths.CACHE_DIR,
) -> pd.DataFrame:
    """Read a spliced continuous series back from the cache."""
    path: Path = continuous_path(root, back_adjust=back_adjust, cache_dir=cache_dir)
    if not path.exists():
        msg: str = (
            f"no continuous series for {root}; run `nqbt splice --root {root}"
            f"{' --back-adjust' if back_adjust else ''}` first"
        )
        raise FileNotFoundError(
            msg,
        )
    return pd.read_parquet(path)
