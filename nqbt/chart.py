"""One trade drawn on the bars it happened on: candles, the bracket it carried, and where it left.

Archetype-agnostic, where :mod:`nqbt.sim.explain` is DeadCatBounce's alone, and reading a trade
log rather than a strategy's parameters -- so a simulated leg and an imported one are drawn by
the same code from the same schema.

**Bar-close OHLC and nothing finer.** The candles are the bars the simulation ran on, and no
line joins an entry to its exit, because the path between them is the one thing these bars do
not record. Tick data would draw it and must not -- ``docs/roadmap.md`` § "Charting a trade".

**A chart is a debugging instrument, not a selection instrument.** It can settle whether the
simulator did what the rule says; it cannot settle whether the rule is any good, and a handful
of charts read for that is the multiple-comparisons machine :mod:`nqbt.guard` exists to defend
against. :data:`CAUTION` is drawn on every chart for the reason :data:`nqbt.review.STATUS` is
printed in every report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from nqbt import annotate, stats, trades

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import pandas as pd

    from nqbt.arrays import FloatArray, IntArray
    from nqbt.context import Dataset

__all__ = [
    "BARS_EITHER_SIDE",
    "BAR_WIDTH",
    "CAUTION",
    "EXIT_CLASSES",
    "LEVELS",
    "PLOT_HEIGHT",
    "ChartError",
    "Plot",
    "TradeChart",
    "chart",
    "charts",
]

BARS_EITHER_SIDE = 30
"""Bars drawn either side of the trade by default: enough context to see what it entered into."""

BAR_WIDTH = 9.0
"""Horizontal pixels per bar. The candle body takes :data:`_BODY_SHARE` of it."""

PLOT_HEIGHT = 360.0
"""Vertical pixels the price panel occupies, excluding the header, the axis and the footer."""

CAUTION = (
    "A DEBUGGING INSTRUMENT, NOT A SELECTION ONE -- a chart can settle whether the simulator did "
    "what the rule says. It cannot settle whether the rule is any good: trades read one at a time "
    "for that are the multiple-comparisons machine nqbt.guard exists for. Take what this raises "
    "to a sweep, never to a decision."
)
"""What every chart states about itself, rather than leaving it to be remembered."""

EXIT_CLASSES = {
    "stop": "stop",
    "target": "target",
    "session_close": "clock",
    "end_of_data": "unfinished",
    "signal": "signal",
}
"""Simulator exit reason -> the CSS class its marker carries, pinned equal to
:data:`nqbt.trades.EXIT_REASONS` by a test. An imported log's own vocabulary falls through to
:data:`OTHER_EXIT`, so a reason nobody here knows is drawn and named rather than dropped.
"""

OTHER_EXIT = "other"
"""The class an exit reason outside :data:`EXIT_CLASSES` is drawn with."""

LEVELS = ("initial_stop", "target_price")
"""The bracket levels drawn as spans, in drawing order. Both are :data:`nqbt.trades.NULLABLE`,
so a log leaving one empty simply has no line for it.
"""

_NEEDED = (
    "trade_id",
    "leg",
    "entry_price",
    "exit_price",
    "direction",
    "exit_reason",
    "net_pnl",
    "commission",
    "bars_held",
    "mae_points",
    "mfe_points",
    "r_multiple",
    "ambiguous_bar",
)
"""Columns a chart reads. The last seven are :func:`nqbt.stats.per_trade`'s, which the headline
is read off rather than re-derived -- a chart defines no statistic, exactly as a review does not.
"""

_SIDES = ("entry", "exit")

_FIGURES = ("net_pnl", "r_multiple", "bars_held", "mae_points", "mfe_points")
""":class:`Figures`' numeric fields, in field order, so one array read fills them all."""

_BODY_SHARE = 0.6
_MIN_BODY = 1.0
"""Pixels a doji's body still occupies, so a bar whose open equals its close is not invisible."""

_MARKER = 5.0
"""Half-width of an entry triangle, in pixels. The exit disc is drawn a little smaller."""

_MARGIN_LEFT = 10.0
_MARGIN_RIGHT = 96.0
_HEADER = 48.0
_TIME_AXIS = 22.0
_FOOTER = 30.0
"""Pixels below the time axis before the caution starts, which the per-leg line occupies. The
caution's own height is added to it, so a narrow chart that wraps it over five lines grows
rather than clipping.
"""

_LINE_HEIGHT = 11.0
_CHARACTER_WIDTH = 5.3

_PRICE_PADDING = 0.08
"""Share of the price span left clear above and below, so a level on the extreme is not on the
frame.
"""

_MIN_SPAN = 0.5
"""Price span a window with no range is given, so the domain is never a single point."""

_GRIDLINES = 5
_TIME_LABELS = 6
_DECIMALS = 2

_STYLE = """
  .bg { fill: #ffffff }
  .panel { fill: none; stroke: #d0d5dd; stroke-width: 1 }
  .grid { stroke: #eef0f4; stroke-width: 1 }
  .held { fill: #eef3fa }
  .wick { stroke: #4a5567; stroke-width: 1 }
  .body { stroke: #4a5567; stroke-width: 1 }
  .body.up { fill: #ffffff }
  .body.down { fill: #4a5567 }
  .level { stroke-width: 1.5; stroke-dasharray: 5 3; fill: none }
  .level.stop { stroke: #c0392b }
  .level.target { stroke: #1e8449 }
  .excursion { stroke-width: 1; stroke-dasharray: 2 3; fill: none }
  .excursion.adverse { stroke: #c0392b }
  .excursion.favourable { stroke: #1e8449 }
  .entry { fill: #1f3a68; stroke: #ffffff; stroke-width: 1 }
  .exit { stroke: #ffffff; stroke-width: 1 }
  .exit.stop { fill: #c0392b }
  .exit.target { fill: #1e8449 }
  .exit.clock { fill: #b9770e }
  .exit.unfinished { fill: #7f8c8d }
  .exit.signal { fill: #1f618d }
  .exit.other { fill: #4a5567 }
  text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #2c3440 }
  .title { font-size: 14px; font-weight: 600 }
  .subtitle { font-size: 11px; fill: #667085 }
  .tick { font-size: 10px; fill: #667085 }
  .tag { font-size: 10px }
  .caution { font-size: 9.5px; fill: #98531a }
"""


class ChartError(ValueError):
    """Raised when a trade cannot honestly be drawn on the bars it was handed."""


@dataclass(frozen=True, slots=True)
class Plot:
    """The mapping from a bar index and a price to a point on the canvas.

    Carried on the result so a caller can place its own overlay on the same axes, and so a test
    can assert a mark sits at a price rather than at a coordinate somebody wrote down.
    """

    first_bar: int
    bar_width: float
    left: float
    top: float
    height: float
    price_min: float
    price_max: float

    def x(self, bar: int) -> float:
        """Canvas x of one bar's centre."""
        return self.left + (bar - self.first_bar + 0.5) * self.bar_width

    def y(self, price: float) -> float:
        """Canvas y of one price. Inverted, since prices rise up the page and y grows down it."""
        return self.top + (self.price_max - price) / (self.price_max - self.price_min) * self.height


@dataclass(frozen=True, slots=True)
class Figures:
    """One trade's numbers, read off :func:`nqbt.stats.per_trade` and never recomputed here."""

    net_pnl: float
    r_multiple: float
    bars_held: int
    mae_points: float
    mfe_points: float
    ambiguous_bar: bool


@dataclass(frozen=True, slots=True)
class TradeChart:
    """One trade's chart, and the window and axes it was drawn on."""

    trade_id: int
    svg: str
    first_bar: int
    last_bar: int
    entry_bars: tuple[int, ...]
    exit_bars: tuple[int, ...]
    plot: Plot
    figures: Figures

    def save(self, path: Path | str) -> Path:
        """Write the SVG to ``path``, creating the parent directory, and return where it went."""
        destination: Path = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.svg, encoding="utf-8")

        return destination

    @override
    def __str__(self) -> str:
        return self.svg


def chart(
    log: pd.DataFrame,
    data: Dataset,
    trade_id: int,
    *,
    bars_either_side: int = BARS_EITHER_SIDE,
    bar_width: float = BAR_WIDTH,
    height: float = PLOT_HEIGHT,
    title: str | None = None,
) -> TradeChart:
    """Draw one trade of ``log`` on ``data``'s bars, with ``bars_either_side`` of context.

    The window is clipped to the dataset, so a trade at either end is drawn with what there is.
    ``title`` replaces the headline; the default states the trade's own figures.

    Draw against the bars the trade happened on -- the per-contract series for an imported log,
    never the back-adjusted continuous one, which shifts every historical price by the roll
    offset while every lookup still succeeds. :func:`nqbt.annotate.contract_bars` reaches them.
    """
    _check_columns(log)
    if bars_either_side < 0:
        msg: str = f"bars_either_side is a count of bars either side, so it cannot be {bars_either_side}"
        raise ChartError(msg)

    legs: pd.DataFrame = _legs_for(log, trade_id)
    entry_bars, exit_bars = _bars_for(legs, data)
    first, last = _window(entry_bars, exit_bars, len(data), bars_either_side)
    figures: Figures = _figures(legs, trade_id)
    plot: Plot = _axes(legs, data, figures, first, last, bar_width=bar_width, height=height)

    return TradeChart(
        trade_id=trade_id,
        svg=_render(legs, data, figures, plot, (first, last), (entry_bars, exit_bars), title),
        first_bar=first,
        last_bar=last,
        entry_bars=tuple(int(bar) for bar in entry_bars),
        exit_bars=tuple(int(bar) for bar in exit_bars),
        plot=plot,
        figures=figures,
    )


def charts(
    log: pd.DataFrame,
    data: Dataset,
    trade_ids: Iterable[int],
    *,
    bars_either_side: int = BARS_EITHER_SIDE,
    bar_width: float = BAR_WIDTH,
    height: float = PLOT_HEIGHT,
) -> list[TradeChart]:
    """Draw each of ``trade_ids`` in turn, in the order given."""
    return [
        chart(log, data, trade_id, bars_either_side=bars_either_side, bar_width=bar_width, height=height)
        for trade_id in trade_ids
    ]


# -- the trade, and the bars it is drawn on -----------------------------------


def _check_columns(log: pd.DataFrame) -> None:
    """Refuse a frame that is not a trade log before anything reads a column of it."""
    missing: list[str] = [name for name in _NEEDED if name not in log.columns]
    if missing:
        msg: str = f"trade log is missing required column(s): {missing}. The schema is nqbt.trades.SCHEMA."
        raise ChartError(msg)


def _legs_for(log: pd.DataFrame, trade_id: int) -> pd.DataFrame:
    """Every leg of one trade, in leg order, or an error naming what the log does hold."""
    legs: pd.DataFrame = log[log["trade_id"] == trade_id]
    if legs.empty:
        known: list[int] = sorted(int(value) for value in log["trade_id"].dropna().unique())
        held: str = f" from {known[0]} to {known[-1]}" if known else ""
        msg: str = f"no trade {trade_id} in this log, which holds {len(known)} trade(s){held}."
        raise ChartError(msg)

    return legs.sort_values("leg", kind="stable")


def _bars_for(legs: pd.DataFrame, data: Dataset) -> tuple[IntArray, IntArray]:
    """Resolve both ends of every leg to a bar of ``data``, refusing a fill no bar covers.

    :func:`nqbt.annotate.resolve_bars` is the shared route, so a chart is refused wherever an
    annotation would be -- a bar index outside the dataset, or a log whose stamps say these are
    different bars of the same shape.
    """
    resolved: dict[str, IntArray] = {side: annotate.resolve_bars(legs, data, side) for side in _SIDES}
    for side, bars in resolved.items():
        unmatched: int = int((bars == annotate.UNMATCHED).sum())
        if not unmatched:
            continue

        msg: str = (
            f"{unmatched} {side} fill(s) of this trade fall in no bar of the dataset, so there is "
            f"no bar to draw them on; these are not the bars that trade happened on."
        )
        raise ChartError(msg)

    return resolved["entry"], resolved["exit"]


def _window(entry_bars: IntArray, exit_bars: IntArray, bars: int, either_side: int) -> tuple[int, int]:
    """The bars to draw: the trade, plus ``either_side`` of context, clipped to the dataset."""
    first: int = max(0, int(entry_bars.min()) - either_side)
    last: int = min(bars - 1, int(exit_bars.max()) + either_side)

    return first, last


def _figures(legs: pd.DataFrame, trade_id: int) -> Figures:
    """Collapse the legs into the trade's numbers through the one function that defines them.

    ``na_value`` is what makes an imported log chartable: the columns it leaves empty are the
    ones read here, and a nullable dtype refuses to become a float array without it.
    """
    summary: pd.DataFrame = stats.per_trade(legs).loc[[trade_id]]
    values: FloatArray = summary[list(_FIGURES)].to_numpy(dtype=np.float64, na_value=np.nan)[0]
    net_pnl, r_multiple, bars_held, mae_points, mfe_points = (float(value) for value in values)

    return Figures(
        net_pnl=net_pnl,
        r_multiple=r_multiple,
        bars_held=0 if np.isnan(bars_held) else int(bars_held),
        mae_points=mae_points,
        mfe_points=mfe_points,
        ambiguous_bar=bool(summary["ambiguous_bar"].to_numpy(np.bool_)[0]),
    )


# -- the axes -----------------------------------------------------------------


def _axes(
    legs: pd.DataFrame,
    data: Dataset,
    figures: Figures,
    first: int,
    last: int,
    *,
    bar_width: float,
    height: float,
) -> Plot:
    """Fit the price domain to the window and to every price the chart is about to draw.

    A fill outside its own bar is drawn rather than refused: that is what a back-adjusted series
    produces, and a chart is the instrument that makes it visible.
    """
    drawn: list[float] = [value for value in _drawn_prices(legs, figures) if np.isfinite(value)]
    low: float = min([float(data.low[first : last + 1].min()), *drawn])
    high: float = max([float(data.high[first : last + 1].max()), *drawn])
    span: float = max(high - low, _MIN_SPAN)
    padding: float = span * _PRICE_PADDING

    return Plot(
        first_bar=first,
        bar_width=bar_width,
        left=_MARGIN_LEFT,
        top=_HEADER,
        height=height,
        price_min=low - padding,
        price_max=high + padding,
    )


def _drawn_prices(legs: pd.DataFrame, figures: Figures) -> list[float]:
    """Every price the chart places a mark at, so none of them can land off the panel."""
    prices: list[float] = [
        *legs["entry_price"].astype(float),
        *legs["exit_price"].astype(float),
    ]
    for level in LEVELS:
        prices += [float(value) for value in legs[level]] if level in legs.columns else []

    return prices + [price for _, price in _excursions(legs, figures)]


def _excursions(legs: pd.DataFrame, figures: Figures) -> list[tuple[str, float]]:
    """The trade's worst and best price while it was open, as a level each.

    The pair that says whether a target was ever within reach of where price actually went. Read
    off :func:`nqbt.stats.per_trade`, so it is the trade's excursion rather than a leg's, and
    absent on a log that leaves the columns null. **MAE and MFE here are this project's
    definition, which is not NT8's** (#70).
    """
    entry: float = float(legs["entry_price"].to_numpy(np.float64)[0])
    direction: float = float(legs["direction"].to_numpy(np.float64)[0])
    excursions: list[tuple[str, float]] = [
        ("adverse", entry - direction * figures.mae_points),
        ("favourable", entry + direction * figures.mfe_points),
    ]

    return [(name, price) for name, price in excursions if np.isfinite(price)]


# -- the drawing --------------------------------------------------------------


def _render(
    legs: pd.DataFrame,
    data: Dataset,
    figures: Figures,
    plot: Plot,
    window: tuple[int, int],
    bars: tuple[IntArray, IntArray],
    title: str | None,
) -> str:
    """Assemble the whole document, back to front: panel, then bars, then what happened on them."""
    first, last = window
    entry_bars, exit_bars = bars
    count: int = last - first + 1
    width: float = _MARGIN_LEFT + count * plot.bar_width + _MARGIN_RIGHT
    caution: list[str] = _wrap(CAUTION, width - 2 * _MARGIN_LEFT)
    total: float = _HEADER + plot.height + _TIME_AXIS + _FOOTER + len(caution) * _LINE_HEIGHT
    right: float = plot.left + count * plot.bar_width
    elements: list[str] = [
        f'<rect class="bg" x="0" y="0" width="{width:.2f}" height="{total:.2f}"/>',
        *_headline(legs, data, figures, bars, title, width),
        *_held(plot, entry_bars, exit_bars),
        *_price_axis(plot, right),
        *_candles(data, plot, first, last),
        *_excursion_lines(legs, figures, plot, right),
        *_level_lines(legs, plot, entry_bars, exit_bars),
        *_markers(legs, plot, entry_bars, exit_bars),
        (
            f'<rect class="panel" x="{plot.left:.2f}" y="{plot.top:.2f}" '
            f'width="{count * plot.bar_width:.2f}" height="{plot.height:.2f}"/>'
        ),
        *_time_axis(data, plot, first, last),
        *_footer(legs, plot, caution),
    ]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}" height="{total:.2f}" '
        f'viewBox="0 0 {width:.2f} {total:.2f}">\n<style>{_STYLE}</style>\n'
        + "\n".join(elements)
        + "\n</svg>\n"
    )


def _candles(data: Dataset, plot: Plot, first: int, last: int) -> list[str]:
    """One wick and one body per bar of the window. Bar-close OHLC, and nothing between."""
    body_width: float = plot.bar_width * _BODY_SHARE
    drawn: list[str] = []
    for bar in range(first, last + 1):
        centre: float = plot.x(bar)
        top: float = plot.y(max(data.open[bar], data.close[bar]))
        bottom: float = plot.y(min(data.open[bar], data.close[bar]))
        rising: str = "up" if data.close[bar] >= data.open[bar] else "down"
        drawn += [
            (
                f'<line class="wick" x1="{centre:.2f}" y1="{plot.y(data.high[bar]):.2f}" '
                f'x2="{centre:.2f}" y2="{plot.y(data.low[bar]):.2f}"/>'
            ),
            (
                f'<rect class="body {rising}" x="{centre - body_width / 2:.2f}" y="{top:.2f}" '
                f'width="{body_width:.2f}" height="{max(bottom - top, _MIN_BODY):.2f}"/>'
            ),
        ]

    return drawn


def _held(plot: Plot, entry_bars: IntArray, exit_bars: IntArray) -> list[str]:
    """Shade the bars the position was open for, which is the only thing joining entry to exit.

    A line from the entry price to the exit price would draw a path through the bars, and the
    path is exactly what bar-close OHLC does not record.
    """
    left: float = plot.x(int(entry_bars.min())) - plot.bar_width / 2
    right: float = plot.x(int(exit_bars.max())) + plot.bar_width / 2

    return [
        (
            f'<rect class="held" x="{left:.2f}" y="{plot.top:.2f}" '
            f'width="{max(right - left, plot.bar_width):.2f}" height="{plot.height:.2f}"/>'
        ),
    ]


def _level_lines(legs: pd.DataFrame, plot: Plot, entry_bars: IntArray, exit_bars: IntArray) -> list[str]:
    """The stop and the target each leg carried, spanning the bars over which it carried them.

    ``initial_stop`` is the stop **as placed**: a trailed stop's path is not in the log, so a
    line drawn across the whole hold would claim a level that moved.
    """
    drawn: list[str] = []
    for row, (entry, leaving) in enumerate(zip(entry_bars, exit_bars, strict=True)):
        left: float = plot.x(int(entry)) - plot.bar_width / 2
        right: float = plot.x(int(leaving)) + plot.bar_width / 2
        for level, name in zip(LEVELS, ("stop", "target"), strict=True):
            if level not in legs.columns:
                continue

            price: float = float(legs[level].to_numpy(np.float64)[row])
            if not np.isfinite(price):
                continue

            drawn += _labelled_line(f"level {name}", price, (left, right), plot, name)

    return drawn


def _excursion_lines(legs: pd.DataFrame, figures: Figures, plot: Plot, right: float) -> list[str]:
    """How far price ran each way while the position was open, as a level each."""
    drawn: list[str] = []
    for name, price in _excursions(legs, figures):
        drawn += _labelled_line(f"excursion {name}", price, (plot.left, right), plot, name[:3].upper())

    return drawn


def _labelled_line(
    classes: str,
    price: float,
    span: tuple[float, float],
    plot: Plot,
    label: str,
) -> list[str]:
    """One horizontal level with its name and price at the right-hand end."""
    left, right = span
    y: float = plot.y(price)
    text: str = f"{label} {price:.{_DECIMALS}f}"

    return [
        f'<line class="{classes}" x1="{left:.2f}" y1="{y:.2f}" x2="{right:.2f}" y2="{y:.2f}"/>',
        f'<text class="tag" x="{right + 4:.2f}" y="{y + 3:.2f}">{escape(text)}</text>',
    ]


def _markers(legs: pd.DataFrame, plot: Plot, entry_bars: IntArray, exit_bars: IntArray) -> list[str]:
    """A triangle where each leg entered, pointing the way it was taken, and a disc where it left."""
    entry_prices: FloatArray = legs["entry_price"].to_numpy(np.float64)
    exit_prices: FloatArray = legs["exit_price"].to_numpy(np.float64)
    directions: FloatArray = legs["direction"].to_numpy(np.float64)
    reasons: Sequence[str] = [str(value) for value in legs["exit_reason"]]
    drawn: list[str] = []
    for row, (entry, leaving) in enumerate(zip(entry_bars, exit_bars, strict=True)):
        drawn.append(_entry_marker(plot.x(int(entry)), plot.y(entry_prices[row]), directions[row]))
        drawn += _exit_marker(plot.x(int(leaving)), plot.y(exit_prices[row]), reasons[row])

    return drawn


def _entry_marker(x: float, y: float, direction: float) -> str:
    """A triangle at the fill, apex up for a long and down for a short."""
    long: bool = direction == trades.LONG
    apex: float = y - _MARKER if long else y + _MARKER
    base: float = y + _MARKER / 2 if long else y - _MARKER / 2
    points: str = f"{x:.2f},{apex:.2f} {x - _MARKER:.2f},{base:.2f} {x + _MARKER:.2f},{base:.2f}"

    return f'<polygon class="entry" points={quoteattr(points)}/>'


def _exit_marker(x: float, y: float, reason: str) -> list[str]:
    """A disc at the fill, coloured and labelled by why the leg left."""
    css: str = EXIT_CLASSES.get(reason, OTHER_EXIT)

    return [
        f'<circle class="exit {css}" cx="{x:.2f}" cy="{y:.2f}" r="{_MARKER * 0.8:.2f}"/>',
        f'<text class="tag" x="{x + _MARKER + 2:.2f}" y="{y + 3:.2f}">{escape(reason)}</text>',
    ]


# -- the axes' labels, the headline and the footer ----------------------------


def _price_axis(plot: Plot, right: float) -> list[str]:
    """Evenly spaced gridlines across the price domain, each labelled at the right-hand edge."""
    drawn: list[str] = []
    for step in range(_GRIDLINES):
        price: float = plot.price_min + (plot.price_max - plot.price_min) * step / (_GRIDLINES - 1)
        y: float = plot.y(price)
        drawn += [
            f'<line class="grid" x1="{plot.left:.2f}" y1="{y:.2f}" x2="{right:.2f}" y2="{y:.2f}"/>',
            f'<text class="tick" x="{right + 46:.2f}" y="{y + 3:.2f}">{price:.{_DECIMALS}f}</text>',
        ]

    return drawn


def _time_axis(data: Dataset, plot: Plot, first: int, last: int) -> list[str]:
    """Clock labels under the panel, at a spacing that keeps about :data:`_TIME_LABELS` of them."""
    step: int = max(1, (last - first + 1) // _TIME_LABELS)
    y: float = plot.top + plot.height + 14.0

    return [
        f'<text class="tick" text-anchor="middle" x="{plot.x(bar):.2f}" y="{y:.2f}">'
        f"{data.index[bar]:%H:%M}</text>"
        for bar in range(first, last + 1, step)
    ]


def _headline(
    legs: pd.DataFrame,
    data: Dataset,
    figures: Figures,
    bars: tuple[IntArray, IntArray],
    title: str | None,
    width: float,
) -> list[str]:
    """What this trade was, and when. Every figure is :class:`Figures`', not one computed here."""
    entry_bars, exit_bars = bars
    entered = data.index[int(entry_bars.min())]
    left = data.index[int(exit_bars.max())]
    reasons: str = ", ".join(dict.fromkeys(str(value) for value in legs["exit_reason"]))
    subtitle: str = (
        f"{entered:%Y-%m-%d %H:%M} to {left:%H:%M}  |  {len(legs)} leg(s), exit: {reasons}  |  "
        f"{figures.bars_held} bars held{'  |  AMBIGUOUS BAR' if figures.ambiguous_bar else ''}"
    )

    return [
        (
            f'<text class="title" x="{_MARGIN_LEFT:.2f}" y="20">'
            f"{escape(title if title is not None else _title(legs, figures))}</text>"
        ),
        f'<text class="subtitle" x="{_MARGIN_LEFT:.2f}" y="36">{escape(subtitle)}</text>',
        (
            f'<text class="subtitle" text-anchor="end" x="{width - 8:.2f}" y="20">'
            f"bars: {escape(data.price_basis.value)}</text>"
        ),
    ]


def _title(legs: pd.DataFrame, figures: Figures) -> str:
    """The default headline: which trade, which way, how big, and what it made."""
    trade_id: int = int(legs["trade_id"].to_numpy(np.int64)[0])
    side: str = "long" if float(legs["direction"].to_numpy(np.float64)[0]) == trades.LONG else "short"
    quantity: int = int(legs["quantity"].sum()) if "quantity" in legs.columns else len(legs)
    instrument: str = f"  {legs['instrument'].iloc[0]}" if "instrument" in legs.columns else ""
    r_multiple: str = "" if np.isnan(figures.r_multiple) else f"  {figures.r_multiple:+.2f}R"

    return f"Trade {trade_id}  {side} {quantity}{instrument}  net {figures.net_pnl:+.2f}{r_multiple}"


def _footer(legs: pd.DataFrame, plot: Plot, caution: Sequence[str]) -> list[str]:
    """The per-leg figures, and the sentence every chart states about itself."""
    y: float = plot.top + plot.height + _TIME_AXIS + 14.0
    per_leg: str = "  ".join(
        f"leg {number}: {reason} {value:+.2f}"
        for number, reason, value in zip(
            legs["leg"].to_numpy(np.int64),
            (str(value) for value in legs["exit_reason"]),
            legs["net_pnl"].to_numpy(np.float64),
            strict=True,
        )
    )

    return [
        f'<text class="tag" x="{_MARGIN_LEFT:.2f}" y="{y:.2f}">{escape(per_leg)}</text>',
        *(
            f'<text class="caution" x="{plot.left:.2f}" y="{y + 15.0 + row * _LINE_HEIGHT:.2f}">'
            f"{escape(line)}</text>"
            for row, line in enumerate(caution)
        ),
    ]


def _wrap(text: str, width: float) -> list[str]:
    """Break one sentence into lines that fit ``width``, since SVG will not wrap text itself.

    Measured in characters against a monospace face, which is what :data:`_STYLE` asks for.
    """
    per_line: int = max(1, int(width / _CHARACTER_WIDTH))
    lines: list[str] = [""]
    for word in text.split(" "):
        if lines[-1] and len(lines[-1]) + len(word) + 1 > per_line:
            lines.append("")

        lines[-1] = f"{lines[-1]} {word}".strip()

    return lines
