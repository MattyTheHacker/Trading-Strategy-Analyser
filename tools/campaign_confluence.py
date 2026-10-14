"""Count each EmaCrossover trade's confluence from conditions it does not read, against a matched null.

    uv run tools/campaign_confluence.py
    uv run tools/campaign_confluence.py --roots MNQ --windows full --iterations 20 --out mnq.parquet

``tools/README.md`` § "campaign_confluence.py".
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

# Lets a tool run directly import its siblings -- ``tools/README.md`` § "Running a tool".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import (
    archetypes,
    conditions,
    context,
    logsetup,
    randomentry,
    resample,
    splice,
    stats,
    sweep,
    trades,
)
from nqbt.costs import TradingCosts
from nqbt.instruments import get_instrument
from nqbt.sim.types import ElasticBandParams, EmaCrossoverParams, OpeningRangeParams
from tools.campaign_shortlist import source
from tools.campaign_sweep import COMMISSION, RESOLUTIONS, ROOTS, SLIPPAGE_TICKS

if TYPE_CHECKING:
    from nqbt.arrays import BoolArray, FloatArray, IndexArray, IntArray
    from nqbt.instruments import Instrument
    from nqbt.sessionrange import RangeKey

logger = logging.getLogger(__name__)

CONDITIONS = ("vwap", "body", "new_extreme", "midline", "cash_range")
"""The five conditions counted, in the order :func:`favouring` stacks them --
``docs/findings/m59-confluence-not-read-preregistration.md`` § "The five conditions"."""

BAND_PERIOD: int = ElasticBandParams().band_period
"""The Bollinger midline's period: ElasticBand's default, the registry's one Bollinger band."""

RANGE_KEY: RangeKey = OpeningRangeParams().range_key
"""The cash opening range: OpeningRange's default anchor and window."""

WINDOWS = ("full", "selection", "holdout")

SIDES: dict[str, float | None] = {"both": None, "long": trades.LONG, "short": trades.SHORT}
"""Which trades a row reads: every one, or one side's."""

KEYS = ["side", "confluences"]
"""What one row of a count table is, within one root, bar size and window."""


class Favours(NamedTuple):
    """Per condition and bar, whether it favours a long and a short signalled at that bar's close."""

    long: BoolArray
    short: BoolArray


def costed(root: str) -> EmaCrossoverParams:
    """Return EmaCrossover at its defaults with this root's real costs on it."""
    return TradingCosts(commission_per_contract=COMMISSION[root], slippage_ticks=SLIPPAGE_TICKS).apply(
        EmaCrossoverParams(),
    )


def context_spec(params: EmaCrossoverParams) -> context.ContextSpec:
    """Return what the archetype reads, and the VWAP, band and range the five conditions read."""
    own: context.ContextSpec = sweep.Grid.of(params, archetype=archetypes.EMACROSSOVER).required_context()

    return own | context.ContextSpec(needs_vwap=True, band_periods=(BAND_PERIOD,), range_keys=(RANGE_KEY,))


def favouring(data: context.Dataset) -> Favours:
    """Return each condition for each side, rows in :data:`CONDITIONS` order.

    A bar before its session's cash range is complete favours neither side on that condition.
    """
    stretch: FloatArray = data.band_stretch(BAND_PERIOD)
    armed: BoolArray = data.range_armed(RANGE_KEY)
    session: IndexArray = data.range_session_id()
    range_high: FloatArray = data.range_high(RANGE_KEY)[session]
    range_low: FloatArray = data.range_low(RANGE_KEY)[session]
    long_side: BoolArray = np.stack(
        [
            data.vwap_gate(above=True),
            conditions.closed_towards(data.open, data.close, trades.LONG),
            data.geometry.made_new_high,
            stretch > 0.0,
            armed & (data.close > range_high),
        ],
    )
    short_side: BoolArray = np.stack(
        [
            data.vwap_gate(above=False),
            conditions.closed_towards(data.open, data.close, trades.SHORT),
            data.geometry.made_new_low,
            stretch < 0.0,
            armed & (data.close < range_low),
        ],
    )

    return Favours(long_side, short_side)


def held(rows: FloatArray, favours: Favours) -> BoolArray:
    """Return which conditions held for each leg's own side, at the signal bar before its fill.

    ``docs/findings/m59-confluence-not-read-preregistration.md`` § "Read at the signal bar".
    """
    signal_bar: IntArray = rows[:, trades.C_ENTRY_BAR].astype(np.int64) - 1
    if (signal_bar < 0).any():
        msg: str = "a leg filled on the first bar, so it has no signal bar to read its conditions at"
        raise ValueError(msg)

    is_long: BoolArray = rows[:, trades.C_DIRECTION] == trades.LONG
    for_its_side: BoolArray = np.where(is_long, favours.long[:, signal_bar], favours.short[:, signal_bar])

    return for_its_side


def on_side(rows: FloatArray, direction: float | None) -> BoolArray:
    """Return which legs one side reads: every leg, or those traded in ``direction``."""
    if direction is None:
        return np.ones(len(rows), dtype=np.bool_)

    traded_that_way: BoolArray = rows[:, trades.C_DIRECTION] == direction

    return traded_that_way


def by_count(legs: trades.LegMatrix, favours: Favours, day_codes: IndexArray | None) -> pd.DataFrame:
    """Summarise the trades at each confluence count, for each side and for both together.

    A count no trade reached has no rate, rather than the zero summary's.
    """
    rows: FloatArray = legs.matrix[: legs.count]
    counts: IntArray = conditions.count_true(held(rows, favours))
    records: list[dict[str, object]] = []
    for side, direction in SIDES.items():
        sided: BoolArray = on_side(rows, direction)
        for count in range(len(CONDITIONS) + 1):
            kept: FloatArray = rows[sided & (counts == count)]
            summary: stats.Summary = stats.summarise_legs(trades.LegMatrix(kept, len(kept)), day_codes)
            traded: bool = summary.trades > 0
            records.append(
                {
                    "side": side,
                    "confluences": count,
                    "trades": summary.trades,
                    "win_rate": summary.win_rate if traded else np.nan,
                    "profit_factor": summary.profit_factor if traded else np.nan,
                },
            )

    return pd.DataFrame(records)


def condition_shares(legs: trades.LegMatrix, favours: Favours) -> pd.DataFrame:
    """Return the share of trades each condition held on, for each side and for both together."""
    rows: FloatArray = legs.matrix[: legs.count]
    first: FloatArray = rows[rows[:, trades.C_LEG] == 1]
    held_on_trade: BoolArray = held(first, favours)
    records: list[dict[str, object]] = []
    for side, direction in SIDES.items():
        sided: BoolArray = on_side(first, direction)
        shares: FloatArray = (
            held_on_trade[:, sided].mean(axis=1) if sided.any() else np.full(len(CONDITIONS), np.nan)
        )
        records.append(
            {"side": side, "trades": int(sided.sum()), **dict(zip(CONDITIONS, shares, strict=True))}
        )

    return pd.DataFrame(records)


def null_by_count(
    data: context.Dataset,
    params: EmaCrossoverParams,
    instrument: Instrument,
    favours: Favours,
    *,
    iterations: int,
    seed: int,
) -> pd.DataFrame:
    """Return :func:`by_count` for every matched random draw, seeded as ``randomentry`` seeds its own."""
    if iterations < 1:
        msg: str = "iterations must be at least 1"
        raise ValueError(msg)

    archetype: archetypes.Archetype = archetypes.EMACROSSOVER
    signal: BoolArray = archetype.signal(data, params)
    pool: randomentry.SessionMinutePool = randomentry.SessionMinutePool.build(data.index)
    tables: list[pd.DataFrame] = []
    for draw, draw_seed in enumerate(np.random.SeedSequence(seed).generate_state(iterations)):
        drawn: BoolArray = randomentry.matched_random_signal(
            data, signal, np.random.default_rng(int(draw_seed)), pool=pool
        )
        legs: trades.LegMatrix = archetype.legs(data, params, instrument, signal=drawn)
        tables.append(by_count(legs, favours, data.day_codes).assign(draw=draw))

    return pd.concat(tables, ignore_index=True)


def placed(observed: pd.DataFrame, null: pd.DataFrame) -> pd.DataFrame:
    """Place each row's profit factor against its draws' median and spread, and give the excess.

    Every draw that traded at a count places it, a draw with no losing trade there included, and
    a row with fewer than ``randomentry.MIN_FINITE_DRAWS`` of them has no null. The percentiles
    are draws rather than interpolations, each taken on the outside of its rank.
    """
    traded: pd.DataFrame = null[null["profit_factor"].notna()]
    grouped = traded.groupby(KEYS)["profit_factor"]
    spread: pd.DataFrame = pd.DataFrame(
        {
            "null_draws": grouped.size(),
            "null_profit_factor": grouped.median(),
            "null_p05": grouped.quantile(0.05, interpolation="lower"),
            "null_p95": grouped.quantile(0.95, interpolation="higher"),
        },
    )
    null_trades: pd.Series[float] = null.groupby(KEYS)["trades"].median().rename("null_trades")
    out: pd.DataFrame = observed.join(null_trades, on=KEYS).join(spread, on=KEYS)
    out["null_draws"] = out["null_draws"].fillna(0).astype(int)
    too_few: pd.Series[bool] = out["null_draws"] < randomentry.MIN_FINITE_DRAWS
    out.loc[too_few, ["null_profit_factor", "null_p05", "null_p95"]] = np.nan
    out["excess"] = out["profit_factor"] - out["null_profit_factor"]

    return out


def measure(
    bars: pd.DataFrame,
    root: str,
    minutes: int,
    *,
    iterations: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return one window's count table against its null, and the share each condition held on."""
    params: EmaCrossoverParams = costed(root)
    instrument: Instrument = get_instrument(root)
    data: context.Dataset = context.prepare(
        resample.resample(bars, minutes),
        context_spec(params),
        bar_minutes=minutes,
        price_basis=context.PriceBasis.RAW,
    )
    favours: Favours = favouring(data)
    legs: trades.LegMatrix = archetypes.EMACROSSOVER.legs(data, params, instrument)
    null: pd.DataFrame = null_by_count(data, params, instrument, favours, iterations=iterations, seed=seed)

    return placed(by_count(legs, favours, data.day_codes), null), condition_shares(legs, favours)


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading."""
    logger.info("")
    logger.info("--- %s ---", title)
    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.max_rows", 200):
        logger.info(
            "%s", frame.to_string(index=False, float_format=lambda value: f"{value:.3f}", na_rep="--")
        )


def main(argv: list[str]) -> int:
    """Print each window's count table against its null and return the process exit code."""
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(
        description="EmaCrossover's confluence from conditions it does not read."
    )
    parser.add_argument("--roots", nargs="+", default=list(ROOTS))
    parser.add_argument("--resolution", type=int, choices=RESOLUTIONS, default=5)
    parser.add_argument("--windows", nargs="+", choices=WINDOWS, default=list(WINDOWS))
    parser.add_argument("--iterations", type=int, default=randomentry.DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, help="write the count tables here, and the shares beside them")
    args = parser.parse_args(argv[1:])

    counts: list[pd.DataFrame] = []
    shares: list[pd.DataFrame] = []
    for root in args.roots:
        archive: pd.DataFrame = splice.load_continuous(root)
        for window in args.windows:
            counted, held_on = measure(
                source(archive, window), root, args.resolution, iterations=args.iterations, seed=args.seed
            )
            where: str = f"{root} {args.resolution}m {window}"
            show(f"{where}: the share of trades each condition held on", held_on)
            show(f"{where}: trades by confluence, against {args.iterations} matched random draws", counted)
            cell: dict[str, str | int] = {"root": root, "resolution": args.resolution, "window": window}
            counts.append(counted.assign(**cell))
            shares.append(held_on.assign(**cell))

    if args.out is not None:
        pd.concat(counts, ignore_index=True).to_parquet(args.out)
        pd.concat(shares, ignore_index=True).to_parquet(shares_path(args.out))
        logger.info("wrote %s and %s", args.out, shares_path(args.out))

    return 0


def shares_path(out: Path) -> Path:
    """Return where the shares go beside a count file: its name with ``-shares`` before the suffix."""
    return out.with_name(f"{out.stem}-shares{out.suffix}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
