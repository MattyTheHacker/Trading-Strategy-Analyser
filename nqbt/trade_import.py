"""Real trades in, the canonical trade log out -- one thin adapter per source.

The NT8 **executions grid** (Control Center -> Executions, exported as CSV) is the only source
implemented, and this module is the only format-aware code in the project. Two of its fields do
the work: ``Position`` is the running position *after* each fill, so trades group without
inferring state from order ids, and ``Name`` carries the exit reason a fills export normally
loses.

What the grid cannot supply -- planned stops and targets, and therefore R, plus MAE/MFE and bar
indices -- is left null and named in :data:`UNPOPULATED` with a reason, so the review omits those
statistics rather than reporting a column of NaNs as if it had been measured. Why the Control
Center log was rejected as a source, and the traps this parser exists to survive:
``docs/roadmap.md`` §M11.1.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn, override

import numpy as np
import pandas as pd

from nqbt import costs, ingest, instruments, paths, trades
from nqbt.instruments import ContractId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from nqbt.arrays import BoolArray, IntArray, OffsetArray

__all__: Sequence[str] = [
    "ACCOUNT_FIELDS",
    "DIRECTION_FIELD",
    "POPULATED",
    "REQUIRED_FIELDS",
    "TIME_FORMATS",
    "UNPOPULATED",
    "ContractCoverage",
    "CoverageReport",
    "ImportedTrades",
    "IncompleteTrades",
    "TradeImportError",
    "import_executions",
    "read_executions",
]

REQUIRED_FIELDS: tuple[str, ...] = ("Instrument", "Action", "Quantity", "Price", "Time", "Position", "Name")
"""Grid columns the adapter cannot work without.

The Executions grid's column set is configurable, so every other column is ignored rather than
required -- two real exports off the same machine differ by six columns.
"""

DIRECTION_FIELD: str = "E/X"
"""Optional column, cross-checked against the position walk rather than trusted."""

ACCOUNT_FIELDS: tuple[str, str] = ("Account display name", "Account")
"""The names the account column goes by. Read by nothing here; the grid is exported per account."""

TIME_FORMATS: tuple[str, str] = ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S")
"""Accepted row-timestamp formats, each tried over the whole column.

Both are ``DD/MM``: NT8's clock is a display setting, but the date order is never inferred from
the values, because the first twelve days of any month parse silently wrong under ``MM/DD``.
"""

BUY = "Buy"
SELL = "Sell"
EXIT = "Exit"
FLAT = "-"

SOURCE = "manual"
"""The :data:`nqbt.trades.SOURCES` tag every row imported here carries."""

UNPOPULATED = {
    "entry_bar": "a fill has a timestamp, not a bar index",
    "exit_bar": "a fill has a timestamp, not a bar index",
    "bars_held": "needs a bar index at both ends",
    "initial_stop": "the grid records fills, not the levels the brackets were working at",
    "target_price": "the grid records fills, not the levels the brackets were working at",
    "risk_points": "needs a planned stop",
    "r_multiple": "needs planned risk, which no field of this source recovers honestly",
    "mae_points": "needs the bars the trade was open across",
    "mfe_points": "needs the bars the trade was open across",
    "ambiguous_bar": "a simulator-only concept; a real fill is not ambiguous, it happened",
}
"""Every schema column this source leaves null, and why each one.

Exactly :data:`nqbt.trades.NULLABLE`, and carried as data rather than as prose because the review
has to state the reason it omitted a statistic.
"""

POPULATED = frozenset(trades.SCHEMA) - set(UNPOPULATED)
"""Schema columns an imported row is guaranteed to carry a real value in."""

_POSITION_RE = re.compile(r"^(?:(?P<flat>-)|(?P<quantity>\d+)\s+(?P<side>[LS]))$")

_NULLABLE_DTYPES: dict[str, str] = {
    "entry_bar": "Int64",
    "exit_bar": "Int64",
    "bars_held": "Int64",
    "ambiguous_bar": "boolean",
}
"""The nullable columns whose simulated counterpart is an integer or a bool rather than a float.

Held as a nullable dtype rather than filled with NaN so that a statistic taken over an absent
column raises instead of returning a number -- ``docs/roadmap.md`` §M11.1.
"""

_LEG_FIELDS: list[str] = [
    "trade_id",
    "leg",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "direction",
    "exit_reason",
    "contract",
]

_FRAME_COLUMNS: list[str] = [
    "source",
    "instrument",
    "trade_id",
    "leg",
    "entry_time",
    "exit_time",
    *trades.COLUMNS[2:],
    "contract",
    "timezone",
]
"""The simulator's own layout -- :func:`nqbt.trades.trades_to_frame`'s -- plus two of our own.

The **contract** and not merely the root, because a real trade must be annotated against its own
per-contract series rather than against the back-adjusted continuous one. The **timezone** the
fills were read under, per row rather than per import, because rows from two machines can end up
in one table and the zone is the one thing no timestamp can be re-derived without.
"""


class TradeImportError(ValueError):
    """Raised when an export cannot be read as a complete, self-consistent fill history."""


@dataclass(frozen=True, slots=True)
class ContractCoverage:
    """The cached bar range one contract's trades could be annotated against."""

    contract: ContractId
    first_bar: pd.Timestamp | None = None
    last_bar: pd.Timestamp | None = None

    @property
    def cached(self) -> bool:
        """Whether this contract has bars in the cache at all."""
        return self.first_bar is not None

    def covers(self, first: pd.Timestamp, last: pd.Timestamp) -> bool:
        """Report whether ``first..last`` lies wholly inside the cached range."""
        if self.first_bar is None or self.last_bar is None:
            return False
        return bool(self.first_bar <= first and last <= self.last_bar)

    @override
    def __str__(self) -> str:
        """One line naming the contract and the range, or saying there is none."""
        if not self.cached:
            return f"{self.contract.nt8_name:<12} not cached"
        return f"{self.contract.nt8_name:<12} {self.first_bar} .. {self.last_bar}"


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """How much of an imported history has bars behind it, measured rather than assumed."""

    contracts: tuple[ContractCoverage, ...]
    trades: int
    covered: int

    @property
    def uncovered(self) -> int:
        """Trades with no bars behind them, which no review may be computed over."""
        return self.trades - self.covered

    @property
    def share(self) -> float:
        """Fraction of trades that can be annotated. No trades is no coverage, not full coverage."""
        return self.covered / self.trades if self.trades else 0.0

    @override
    def __str__(self) -> str:
        """Render the reviewable share, then one line per contract."""
        head: str = f"{self.covered}/{self.trades} trades reviewable ({self.share:.1%})"
        return "\n".join([head, *(f"  {c}" for c in self.contracts)])


@dataclass(frozen=True, slots=True)
class IncompleteTrades:
    """Fills at either end of the export that no complete trade could be built from."""

    leading_fills: int  # Fills before the first flat position: the export begins part-way through a trade.
    trailing_fills: int
    """Fills after the last flat position: a position was still open when it was taken.

    Never zero for a session still in progress, and the grid lags live by roughly two hours.
    """

    @property
    def total(self) -> int:
        """Fills dropped at both ends together."""
        return self.leading_fills + self.trailing_fills

    @override
    def __str__(self) -> str:
        """Render what was dropped at each end."""
        return f"{self.leading_fills} leading and {self.trailing_fills} trailing fills dropped"


@dataclass(frozen=True, slots=True)
class ImportedTrades:
    """A canonical trade log, beside everything the adapter could not recover from the source."""

    frame: pd.DataFrame  # Every complete trade, schema-validated. One row per FIFO leg exit.
    populated: frozenset[str]
    unpopulated: Mapping[str, str]
    coverage: CoverageReport
    incomplete: IncompleteTrades

    @property
    def reviewable(self) -> pd.DataFrame:
        """The legs of the trades whose bars are cached: what a review may be computed over."""
        return self.frame[self.frame["covered"]]

    @override
    def __str__(self) -> str:
        """Leg count, the coverage report, and what could not be built into a trade."""
        return f"{len(self.frame)} legs, {self.coverage}\n  {self.incomplete}"


def read_executions(path: Path | str, timezone: str) -> pd.DataFrame:
    """Parse an NT8 executions-grid CSV into chronologically ordered, position-checked fills.

    ``timezone`` is the exporting machine's NT8 display zone and is required rather than
    defaulted: the file carries none, and a wrong one shifts every trade by hours without erroring.
    """
    raw: pd.DataFrame = pd.read_csv(path, dtype="string")
    missing: list[str] = [name for name in REQUIRED_FIELDS if name not in raw.columns]
    if missing:
        msg: str = (
            f"{path}: not an NT8 executions grid -- missing column(s) {missing}. "
            f"Export it from Control Center -> Executions."
        )
        raise TradeImportError(msg)

    quantities: IntArray = _quantities(raw["Quantity"])
    fills: pd.DataFrame = pd.DataFrame(
        {
            "time": _timestamps(raw["Time"], source=str(path)),
            "contract": raw["Instrument"].str.strip(),
            "quantity": quantities,
            "price": raw["Price"].astype("float64"),
            "position": _positions(raw["Position"]),
            "name": raw["Name"].str.strip(),
            "signed": _signed(raw["Action"], quantities),
        },
    )

    # The grid exports newest first, so file order reversed is chronological. Ties within one
    # second are then resolved by the position chain, never by a sort -- ``docs/roadmap.md`` §M11.1.
    fills = fills.iloc[::-1].reset_index(drop=True)
    _check_ascending(fills["time"], source=str(path))
    fills = _order_ties_by_position(fills)

    if DIRECTION_FIELD in raw.columns:
        _check_declared_directions(fills, raw[DIRECTION_FIELD], source=str(path))

    fills["time"] = _localise(fills["time"], timezone=timezone)
    return fills


def import_executions(
    path: Path | str,
    timezone: str,
    commission_per_contract: float = costs.LIVE.commission_per_contract,
    cache_dir: Path = paths.CACHE_DIR,
) -> ImportedTrades:
    """Import an NT8 executions grid as a canonical trade log, with what it could not recover.

    ``commission_per_contract`` defaults to the real figure rather than to the simulator's zero,
    because the export's own ``Commission`` column reads ``$0.00`` on an account that is charged
    -- ``docs/roadmap.md`` §M11.1. Slippage is not applied: a real fill price already contains it.
    """
    fills, incomplete = _complete_trades(read_executions(path, timezone=timezone))
    frame: pd.DataFrame = _to_schema(
        _match_fifo(fills),
        commission_per_contract=commission_per_contract,
        timezone=timezone,
    )
    coverage: CoverageReport = _mark_coverage(frame, cache_dir=cache_dir)
    return ImportedTrades(
        frame=trades.validate(frame),
        populated=POPULATED,
        unpopulated=dict(UNPOPULATED),
        coverage=coverage,
        incomplete=incomplete,
    )


def _timestamps(column: pd.Series[str], source: str) -> pd.Series[pd.Timestamp]:
    """Parse the row timestamps under the first accepted format that fits the whole column."""
    text: pd.Series[str] = column.str.strip()
    for fmt in TIME_FORMATS:
        parsed: pd.Series[pd.Timestamp] = pd.to_datetime(text, format=fmt, errors="coerce")
        if not parsed.isna().any():
            return parsed
    bad: pd.Series[str] = text[pd.to_datetime(text, format=TIME_FORMATS[0], errors="coerce").isna()]
    msg: str = (
        f"{source}: cannot parse Time under any of {TIME_FORMATS}; first offender "
        f"{bad.iloc[0]!r} at row {bad.index[0]}. The date order is not inferred from the values."
    )
    raise TradeImportError(msg)


def _localise(times: pd.Series[pd.Timestamp], timezone: str) -> pd.Series[pd.Timestamp]:
    """Attach the export's display zone and convert to UTC, which the bar cache is in."""
    localised: pd.Series[pd.Timestamp] = times.dt.tz_localize(timezone, ambiguous="infer", nonexistent="shift_forward")
    return localised.dt.tz_convert("UTC")


def _quantities(column: pd.Series[str]) -> IntArray:
    """Fill sizes, which are unsigned; the side is carried by ``Action``."""
    quantities: IntArray = np.asarray(column.astype("int64"), dtype=np.int64)
    if (quantities <= 0).any():
        msg: str = "every fill must have a positive Quantity; the side is carried by Action"
        raise TradeImportError(msg)

    return quantities


def _signed(column: pd.Series[str], quantities: IntArray) -> IntArray:
    """Signed size of each fill: positive bought, negative sold."""
    action: pd.Series[str] = column.str.strip()
    unknown: list[str] = sorted(set(action.dropna().unique()) - {BUY, SELL})
    if unknown:
        msg: str = f"unknown Action value(s) {unknown}; expected {BUY!r} or {SELL!r}"
        raise TradeImportError(msg)

    return np.where(action.eq(BUY).to_numpy(), quantities, -quantities)


def _positions(column: pd.Series[str]) -> IntArray:
    """Parse the running-position field: ``-`` is flat, ``4 S`` short four, ``2 L`` long two."""
    text: pd.Series[str] = column.str.strip()
    if text.hasnans:
        msg: str = "every fill must carry a Position; it is the only trade boundary this source has"
        raise TradeImportError(msg)

    parsed: dict[str, int] = {}
    for value in text.unique():
        match: re.Match[str] | None = _POSITION_RE.match(value)
        if match is None:
            msg = f"cannot parse Position {value!r}; expected {FLAT!r}, '<n> L' or '<n> S'"
            raise TradeImportError(msg)

        quantity: int = 0 if match["flat"] else int(match["quantity"])
        parsed[value] = quantity if match["side"] == "L" else -quantity

    return np.asarray(text.map(parsed), dtype=np.int64)


def _check_ascending(times: pd.Series[pd.Timestamp], source: str) -> None:
    """Reversed file order must be non-decreasing in time, or the export was not newest-first."""
    if times.is_monotonic_increasing:
        return

    backwards: int = int(np.flatnonzero(times.diff().dt.total_seconds().to_numpy() < 0)[0])
    msg: str = (
        f"{source}: reversing the file does not give chronological order -- row {backwards} "
        f"goes backwards. An executions grid exports newest first."
    )
    raise TradeImportError(msg)


def _order_ties_by_position(fills: pd.DataFrame) -> pd.DataFrame:
    """Order fills sharing one timestamp by the chain their ``Position`` values form.

    File order is not dependable for a tie: two exports of one history have been seen carrying
    the same two fills in opposite order. The running position is dependable, because each fill's
    is the previous one plus its own signed size, so the chain has exactly one arrangement.
    """
    positions: IntArray = fills["position"].to_numpy(np.int64)
    signed: IntArray = fills["signed"].to_numpy(np.int64)
    times = fills["time"].to_numpy()
    order: list[int] = []
    running: int = _opening_position(positions, signed)
    start: int = 0
    while start < len(fills):
        stop: int = start + int(np.searchsorted(times[start:], times[start], side="right"))
        pending: list[int] = list(range(start, stop))
        while pending:
            nxt: int | None = next((i for i in pending if running + signed[i] == positions[i]), None)
            if nxt is None:
                _raise_broken_chain(fills, running, pending)
            order.append(nxt)
            running = int(positions[nxt])
            pending.remove(nxt)
        start = stop
    return fills.iloc[order].reset_index(drop=True)


def _opening_position(positions: IntArray, signed: IntArray) -> int:
    """Infer the position held before the first fill: flat, unless the export begins mid-trade."""
    if len(positions) == 0 or positions[0] == signed[0]:
        return 0

    return int(positions[0] - signed[0])


def _raise_broken_chain(fills: pd.DataFrame, running: int, pending: Sequence[int]) -> NoReturn:
    """Name the fill the position walk could not reach, now that we know there is one."""
    row = fills.iloc[pending[0]]
    msg: str = (
        f"the position walk breaks at {row['time']}: holding {running}, and none of the "
        f"{len(pending)} fill(s) at that timestamp lands on its stated Position. The export is "
        f"missing a fill, or Position was misread."
    )
    raise TradeImportError(msg)


def _check_declared_directions(fills: pd.DataFrame, column: pd.Series[str], source: str) -> None:
    """Cross-check ``E/X`` against the position walk, the only independent test of the parse."""
    declared: BoolArray = column.str.strip().eq(EXIT).to_numpy()[::-1]
    positions: IntArray = fills["position"].to_numpy(np.int64)
    previous: IntArray = np.concatenate(([_opening_position(positions, fills["signed"].to_numpy())], positions[:-1]))
    # A fill that crosses zero both closes and opens, so only the unambiguous ones are checked.
    crosses: BoolArray = np.sign(positions) * np.sign(previous) < 0
    walked: BoolArray = np.abs(positions) < np.abs(previous)
    disagree: OffsetArray = np.flatnonzero((walked != declared[: len(positions)]) & ~crosses)
    if disagree.size:
        row = fills.iloc[int(disagree[0])]
        msg: str = (
            f"{source}: {DIRECTION_FIELD} disagrees with the position walk at {row['time']} -- "
            f"the walk makes it {'an exit' if walked[disagree[0]] else 'an entry'}. "
            f"The columns are probably not the ones this adapter thinks they are."
        )
        raise TradeImportError(msg)


def _complete_trades(fills: pd.DataFrame) -> tuple[pd.DataFrame, IncompleteTrades]:
    """Drop the partial trades at either end, counting them rather than swallowing them."""
    if fills.empty:
        return fills, IncompleteTrades(leading_fills=0, trailing_fills=0)
    positions: IntArray = fills["position"].to_numpy(np.int64)
    signed: IntArray = fills["signed"].to_numpy(np.int64)
    flat: OffsetArray = np.flatnonzero(positions == 0)

    first: int = 0 if positions[0] == signed[0] else (int(flat[0]) + 1 if flat.size else len(fills))
    last: int = int(flat[-1]) + 1 if flat.size and flat[-1] >= first else first
    return fills.iloc[first:last].reset_index(drop=True), IncompleteTrades(
        leading_fills=first,
        trailing_fills=len(fills) - last,
    )


@dataclass(slots=True)
class _Lot:
    """One entry fill, and how much of it is still open."""

    price: float
    time: pd.Timestamp
    remaining: int


def _match_fifo(fills: pd.DataFrame) -> list[dict[str, object]]:
    """Pair each exit fill against the oldest open entry lots, one leg row per pair.

    FIFO because that is how NT8 matches a partial exit. Trade-level P&L is the same under any
    matching; per-leg attribution is not, and the schema is per leg.
    """
    rows: list[dict[str, object]] = []
    lots: deque[_Lot] = deque()
    direction: float = 0.0
    trade_id: int = 0
    leg: int = 0
    for fill in fills.itertuples(index=False):
        remaining: int = int(fill.quantity)  # type: ignore[arg-type]  # itertuples widens every column
        signed: int = int(fill.signed)  # type: ignore[arg-type]  # the same widening
        opening: float = trades.LONG if signed > 0 else trades.SHORT
        while lots and opening != direction and remaining:
            lot: _Lot = lots[0]
            matched: int = min(lot.remaining, remaining)
            leg += 1
            rows.append(
                {
                    "trade_id": trade_id,
                    "leg": leg,
                    "entry_time": lot.time,
                    "exit_time": fill.time,
                    "entry_price": lot.price,
                    "exit_price": fill.price,
                    "quantity": matched,
                    "direction": direction,
                    "exit_reason": fill.name,
                    "contract": fill.contract,
                },
            )
            lot.remaining -= matched
            remaining -= matched
            if not lot.remaining:
                lots.popleft()
        if remaining:
            if not lots:
                trade_id += 1
                leg = 0
                direction = opening
            lots.append(_Lot(price=fill.price, time=fill.time, remaining=remaining))  # type: ignore[arg-type]  # the same widening
    return rows


def _to_schema(rows: list[dict[str, object]], commission_per_contract: float, timezone: str) -> pd.DataFrame:
    """Turn matched legs into the shared trade-log schema, nulls and all."""
    frame: pd.DataFrame = pd.DataFrame(rows, columns=_LEG_FIELDS)
    for name in ("trade_id", "leg", "quantity"):
        frame[name] = frame[name].astype("int64")

    for name in ("direction", "entry_price", "exit_price"):
        frame[name] = frame[name].astype("float64")

    for name in ("exit_reason", "contract"):
        frame[name] = frame[name].astype("string")

    for name in ("entry_time", "exit_time"):
        frame[name] = pd.to_datetime(frame[name], utc=True)

    roots: pd.Series[str] = frame["contract"].map(lambda name: ContractId.parse(name).root).astype("string")
    point_values: pd.Series[float] = roots.map(lambda root: instruments.get_instrument(root).point_value)
    frame["instrument"] = roots
    frame["source"] = pd.Series(SOURCE, index=frame.index, dtype="string")
    frame["timezone"] = pd.Series(timezone, index=frame.index, dtype="string")

    move: pd.Series[float] = (frame["exit_price"] - frame["entry_price"]) * frame["direction"]
    frame["gross_pnl"] = move * point_values.astype("float64") * frame["quantity"]
    frame["commission"] = commission_per_contract * frame["quantity"]
    frame["net_pnl"] = frame["gross_pnl"] - frame["commission"]

    for name in trades.NULLABLE:
        dtype: str = _NULLABLE_DTYPES.get(name, "float64")
        blank = np.nan if dtype == "float64" else pd.NA
        frame[name] = pd.Series(blank, index=frame.index, dtype=dtype)

    return frame[_FRAME_COLUMNS]


def _mark_coverage(frame: pd.DataFrame, cache_dir: Path) -> CoverageReport:
    """Add the ``covered`` column and report how many trades have bars behind them.

    Whole trades, never individual legs: a trade split across the edge of the cache would have
    part of its P&L reviewed and the rest excluded.
    """
    contracts: tuple[ContractCoverage, ...] = tuple(
        _cached_range(ContractId.parse(name), cache_dir=cache_dir)
        for name in sorted(frame["contract"].dropna().unique())
    )
    frame["covered"] = False
    if frame.empty:
        return CoverageReport(contracts=contracts, trades=0, covered=0)

    ranges: dict[str, ContractCoverage] = {c.contract.nt8_name: c for c in contracts}
    spans: pd.DataFrame = frame.groupby("trade_id").agg(
        contract=("contract", "first"),
        first=("entry_time", "min"),
        last=("exit_time", "max"),
    )
    covered: pd.Series[bool] = spans.apply(
        lambda span: ranges[span["contract"]].covers(span["first"], span["last"]),
        axis=1,
    ).astype(bool)
    frame["covered"] = frame["trade_id"].map(covered).astype(bool)
    return CoverageReport(contracts=contracts, trades=len(spans), covered=int(covered.sum()))


def _cached_range(contract: ContractId, cache_dir: Path) -> ContractCoverage:
    """Read one contract's first and last cached bar, or an empty range if it is not cached."""
    path: Path = ingest.contract_cache_path(contract, cache_dir)
    if not path.exists():
        return ContractCoverage(contract=contract)

    index = pd.read_parquet(path, columns=[]).index
    if index.empty:
        return ContractCoverage(contract=contract)

    return ContractCoverage(
        contract=contract,
        first_bar=pd.Timestamp(index[0]),
        last_bar=pd.Timestamp(index[-1]),
    )
