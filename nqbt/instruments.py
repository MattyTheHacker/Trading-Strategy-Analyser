"""Instrument specifications and contract identity.

Every dollar figure in this project must flow through an :class:`Instrument`. NQ and MNQ
share a tick size but their tick values differ by 10x ($5.00 vs $0.50), so any risk cap,
position size or commission expressed in ticks means a completely different dollar amount
depending on which contract is loaded. There is no single tick-value constant anywhere.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, override

# CME quarterly futures month codes.
MONTH_CODES: dict[int, str] = {3: "H", 6: "M", 9: "U", 12: "Z"}
CODE_MONTHS: dict[str, int] = {v: k for k, v in MONTH_CODES.items()}

RoundMode = Literal["nearest", "up", "down"]

ON_TICK_TOLERANCE = 1e-9
"""How far off the tick grid a price may sit and still count as on it."""


@dataclass(frozen=True, slots=True)
class Instrument:
    """Contract specification for a single futures root."""

    symbol: str
    name: str
    tick_size: float
    point_value: float
    """Dollars per 1.00 of price movement, per contract."""
    exchange: str = "CME"
    currency: str = "USD"
    session_template: str = "CME US Index Futures ETH"

    @property
    def tick_value(self) -> float:
        """Dollars per tick, per contract."""
        return self.tick_size * self.point_value

    @property
    def price_decimals(self) -> int:
        """Decimal places needed to represent any valid price on this instrument.

        Taken from the tick size's own decimal representation rather than its
        magnitude: a 0.25 tick needs two places even though log10(0.25) suggests one,
        and rounding to one place produces prices that do not exist on the grid.
        """
        exponent = Decimal(str(self.tick_size)).normalize().as_tuple().exponent
        return max(0, -int(exponent))

    # -- conversions -----------------------------------------------------------

    def ticks_to_dollars(self, ticks: float, quantity: int = 1) -> float:
        """Value of ``ticks`` on this instrument, for ``quantity`` contracts."""
        return ticks * self.tick_value * quantity

    def points_to_dollars(self, points: float, quantity: int = 1) -> float:
        """Value of ``points`` on this instrument, for ``quantity`` contracts."""
        return points * self.point_value * quantity

    def dollars_to_points(self, dollars: float, quantity: int = 1) -> float:
        """Price distance ``dollars`` buys, for ``quantity`` contracts."""
        return dollars / (self.point_value * quantity)

    def points_to_ticks(self, points: float) -> float:
        """``points`` expressed in ticks."""
        return points / self.tick_size

    def ticks_to_points(self, ticks: float) -> float:
        """``ticks`` expressed in points."""
        return ticks * self.tick_size

    # -- price alignment -------------------------------------------------------

    def round_to_tick(self, price: float, mode: RoundMode = "nearest") -> float:
        """Snap ``price`` onto the instrument's tick grid.

        Prices arriving from arithmetic (a target at ``entry - risk * 1.5``) are not
        guaranteed to land on a tradeable tick, and an order at an untradeable price is
        not a thing NT8 would ever fill. A small epsilon absorbs float representation
        error so that a value already sitting on the grid is never nudged off it.
        """
        n: float = price / self.tick_size
        eps: float = 1e-9
        if mode == "nearest":
            n = math.floor(n + 0.5)
        elif mode == "up":
            n = math.ceil(n - eps)
        elif mode == "down":
            n = math.floor(n + eps)
        else:  # pragma: no cover - guarded by the Literal type
            msg = f"unknown round mode: {mode!r}"  # type: ignore[unreachable]  # a caller may ignore it
            raise ValueError(msg)
        return round(n * self.tick_size, self.price_decimals)

    def is_on_tick(self, price: float) -> bool:
        """Whether ``price`` sits exactly on this instrument's tick grid."""
        return abs(price - self.round_to_tick(price)) < ON_TICK_TOLERANCE

    # -- risk ------------------------------------------------------------------

    def position_size_for_risk(self, risk_dollars: float, stop_distance_points: float) -> int:
        """Largest whole contract count whose worst case stays within ``risk_dollars``.

        Rounds down, so the realised risk is always at or below the cap. Returns 0 when
        even a single contract would breach it -- callers must treat 0 as "no trade"
        rather than silently trading one lot.
        """
        if stop_distance_points <= 0:
            msg: str = "stop_distance_points must be positive"
            raise ValueError(msg)
        per_contract: float = self.points_to_dollars(stop_distance_points)
        if per_contract <= 0:
            msg = "stop distance rounds to zero dollars of risk"
            raise ValueError(msg)
        return int(risk_dollars // per_contract)


NQ = Instrument(
    symbol="NQ",
    name="E-mini Nasdaq-100",
    tick_size=0.25,
    point_value=20.0,
)

MNQ = Instrument(
    symbol="MNQ",
    name="Micro E-mini Nasdaq-100",
    tick_size=0.25,
    point_value=2.0,
)

INSTRUMENTS: dict[str, Instrument] = {inst.symbol: inst for inst in (NQ, MNQ)}


def get_instrument(symbol: str) -> Instrument:
    """Look up an instrument by root symbol, case-insensitively."""
    try:
        return INSTRUMENTS[symbol.strip().upper()]
    except KeyError:
        known: str = ", ".join(sorted(INSTRUMENTS))
        msg: str = f"unknown instrument {symbol!r}; known instruments: {known}"
        raise KeyError(msg) from None


# "MNQ 03-24", "NQ 12-25" -- the naming NT8's Historical Data export produces.
_CONTRACT_RE = re.compile(r"^\s*(?P<root>[A-Za-z]{1,4})\s+(?P<month>\d{2})-(?P<year>\d{2})\s*$")


@dataclass(frozen=True, slots=True, order=True)
class ContractId:
    """A single quarterly contract, e.g. MNQ 03-24.

    Ordered by (year, month) first so that a sorted list of contracts is in expiry
    order -- which is what the splicer needs to find adjacent pairs.
    """

    year: int
    month: int
    root: str

    def __post_init__(self) -> None:
        if self.month not in MONTH_CODES:
            msg: str = (
                f"{self.root} {self.month:02d}-{self.year}: month must be one of "
                f"{sorted(MONTH_CODES)} (NQ/MNQ are quarterly contracts)"
            )
            raise ValueError(
                msg,
            )

    @classmethod
    def parse(cls, text: str) -> ContractId:
        """Parse an NT8-style contract name such as ``"MNQ 03-24"``."""
        m: re.Match[str] | None = _CONTRACT_RE.match(text)
        if not m:
            msg: str = f"cannot parse contract name {text!r}; expected e.g. 'MNQ 03-24'"
            raise ValueError(msg)
        return cls(
            root=m["root"].upper(),
            month=int(m["month"]),
            year=2000 + int(m["year"]),
        )

    @property
    def month_code(self) -> str:
        """The futures month letter, ``H`` for March and so on."""
        return MONTH_CODES[self.month]

    @property
    def nt8_name(self) -> str:
        """The name as NT8 writes it, e.g. ``"MNQ 03-24"``."""
        return f"{self.root} {self.month:02d}-{self.year % 100:02d}"

    @property
    def cache_key(self) -> str:
        """Filesystem-safe identifier, e.g. ``"MNQ_2024H"``."""
        return f"{self.root}_{self.year}{self.month_code}"

    @property
    def instrument(self) -> Instrument:
        """The :class:`Instrument` this contract's root names."""
        return get_instrument(self.root)

    @override
    def __str__(self) -> str:
        return self.nt8_name
