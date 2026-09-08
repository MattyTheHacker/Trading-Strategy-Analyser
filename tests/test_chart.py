"""Chart tests: one trade drawn on the bars it happened on.

Every geometric claim is asserted against ``chart.plot``'s own mapping rather than against a
coordinate written down here, so a change to the layout cannot silently move a mark off its
price. Three claims are pinned harder than the rest, because each would draw a plausible and
wrong picture rather than raise. **No line joins an entry to its exit**, because the path
between them is what bar-close OHLC does not record. **A fill outside its bar is drawn rather
than refused**, since that is what a back-adjusted series produces and a chart is the instrument
that makes it visible. **Bars of a different series are refused**, through the same check an
annotation applies.
"""

from xml.etree import ElementTree

import numpy as np
import pandas as pd
import pytest

from nqbt import annotate, chart, context, sessions, stats, trades
from nqbt.chart import ChartError
from nqbt.context import ContextSpec, PriceBasis

BASE = 18000.0
BARS = 200
SVG = "{http://www.w3.org/2000/svg}"
ROUNDING = 0.005
"""Half of the last decimal the document is written to."""
FIRST_MINUTE = "2024-01-03 14:00"


def bars(count: int = BARS, *, flat: bool = False) -> pd.DataFrame:
    """``count`` one-minute bars with a zig-zag close, or one flat price when ``flat``.

    The zig-zag gives every bar a body and a wick either side; the flat case is the degenerate
    window whose price span would otherwise be zero.
    """
    index = pd.date_range(FIRST_MINUTE, periods=count, freq="min", tz="UTC")
    close = (
        np.full(count, BASE)
        if flat
        else BASE + 0.25 * np.cumsum(np.where((np.arange(count) // 15) % 2 == 0, 1.0, -1.0))
    )
    open_ = np.concatenate(([close[0]], close[:-1]))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + (0.0 if flat else 1.0),
            "low": np.minimum(open_, close) - (0.0 if flat else 1.0),
            "close": close,
            "volume": np.full(count, 100.0),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


def dataset(**kwargs: int | bool) -> context.Dataset:
    """The fixture bars as a dataset. No conditions: a chart reads bars and a log, nothing else."""
    return context.prepare(bars(**kwargs), ContextSpec(), price_basis=PriceBasis.RAW)


def log(
    entries: list[int],
    exits: list[int],
    data: context.Dataset,
    *,
    direction: float = trades.LONG,
    exit_reasons: list[str] | None = None,
    trade_ids: list[int] | None = None,
) -> pd.DataFrame:
    """A simulated log, one leg per row, entering and leaving on the bars named.

    Every column a chart reads carries a value, so nothing is omitted for want of one. Rows
    sharing a ``trade_id`` are a scale-out.
    """
    entered = np.asarray(entries, dtype=np.int64)
    left = np.asarray(exits, dtype=np.int64)
    count = len(entered)
    ids = np.asarray(trade_ids or list(range(1, count + 1)), dtype=np.int64)
    entry_price = data.close[entered]
    risk = 10.0

    return pd.DataFrame(
        {
            "source": pd.array(["sim"] * count, dtype="string"),
            "instrument": pd.array(["MNQ"] * count, dtype="string"),
            "trade_id": ids,
            "leg": np.array([1 + int((ids[:i] == ids[i]).sum()) for i in range(count)], dtype=np.int64),
            "entry_bar": entered,
            "exit_bar": left,
            "entry_time": data.index[entered],
            "exit_time": data.index[left],
            "entry_price": entry_price,
            "exit_price": data.close[left],
            "initial_stop": entry_price - direction * risk,
            "target_price": entry_price + direction * risk * 2.0,
            "quantity": np.ones(count, dtype=np.int64),
            "direction": np.full(count, direction),
            "gross_pnl": np.full(count, 20.0),
            "commission": np.full(count, 1.5),
            "net_pnl": np.full(count, 18.5),
            "r_multiple": np.full(count, 2.0),
            "risk_points": np.full(count, risk),
            "exit_reason": pd.array(exit_reasons or ["target"] * count, dtype="string"),
            "bars_held": (left - entered).astype(np.int64),
            "mae_points": np.full(count, 3.0),
            "mfe_points": np.full(count, 12.0),
            "ambiguous_bar": np.zeros(count, dtype=bool),
        },
    )


def case(**kwargs: object) -> tuple[chart.TradeChart, context.Dataset, pd.DataFrame]:
    """One long trade entering on bar 100 and taking its target on bar 110."""
    data = dataset()
    trades_log = log([100], [110], data)

    return chart.chart(trades_log, data, 1, **kwargs), data, trades_log  # type: ignore[arg-type]  # keyword passthrough for the options under test


def elements(drawn: chart.TradeChart, tag: str, css: str | None = None) -> list[ElementTree.Element]:
    """Every ``tag`` element of the document, optionally only those carrying one CSS class."""
    root = ElementTree.fromstring(drawn.svg)

    return [
        element
        for element in root.iter(f"{SVG}{tag}")
        if css is None or css in (element.get("class") or "").split()
    ]


def only(drawn: chart.TradeChart, tag: str, css: str) -> ElementTree.Element:
    """The one element of that tag and class, asserting there is exactly one."""
    found = elements(drawn, tag, css)
    assert len(found) == 1, f"expected one {tag}.{css}, found {len(found)}"

    return found[0]


def at(value: float) -> object:
    """A coordinate comparison at the precision the document is written to.

    Every number in the SVG is rounded to two decimals, so a tolerance tighter than half of one
    would only be asserting that rounding did not happen.
    """
    return pytest.approx(value, abs=ROUNDING)


def number(element: ElementTree.Element, attribute: str) -> float:
    """One numeric attribute of an element."""
    value = element.get(attribute)
    assert value is not None, f"{element.tag} carries no {attribute}"

    return float(value)


# -- what the chart says about the trade --------------------------------------


def test_the_exit_disc_sits_at_the_exit_price_on_the_exit_bar():
    drawn, _, trades_log = case()
    disc = only(drawn, "circle", "exit")

    assert number(disc, "cx") == at(drawn.plot.x(110))
    assert number(disc, "cy") == at(drawn.plot.y(float(trades_log["exit_price"].iloc[0])))


def test_the_entry_triangle_straddles_the_entry_price_on_the_entry_bar():
    """The mark points at the fill, whatever size the marker happens to be drawn at."""
    drawn, _, trades_log = case()
    points = _points(drawn)
    fill = drawn.plot.y(float(trades_log["entry_price"].iloc[0]))

    assert points[0][0] == at(drawn.plot.x(100))
    assert min(point[1] for point in points) <= fill <= max(point[1] for point in points)


def test_the_entry_triangle_points_the_way_the_trade_was_taken():
    data = dataset()
    long_apex, long_base = _triangle(chart.chart(log([100], [110], data), data, 1))
    short = log([100], [110], data, direction=trades.SHORT)
    short_apex, short_base = _triangle(chart.chart(short, data, 1))

    assert long_apex < long_base, "a long's apex must sit above its base, and y grows down"
    assert short_apex > short_base, "a short's apex must sit below its base"


def _points(drawn: chart.TradeChart) -> list[tuple[float, ...]]:
    """The entry triangle's three corners, apex first."""
    triangle = only(drawn, "polygon", "entry")

    return [
        tuple(float(part) for part in point.split(",")) for point in (triangle.get("points") or "").split()
    ]


def _triangle(drawn: chart.TradeChart) -> tuple[float, float]:
    """The apex's y and the base's y of one chart's entry marker."""
    points = _points(drawn)

    return points[0][1], points[1][1]


def test_the_exit_disc_names_why_the_leg_left():
    data = dataset()
    for reason, css in chart.EXIT_CLASSES.items():
        drawn = chart.chart(log([100], [110], data, exit_reasons=[reason]), data, 1)

        assert elements(drawn, "circle", css), f"{reason} was not drawn as .{css}"


def test_the_exit_reason_label_clears_the_level_label_it_lands_on():
    """A leg leaving at its target sits on the target line, so the two labels must not share a spot."""
    drawn, _, _ = case()
    tags = {
        "".join(tag.itertext()): (number(tag, "x"), number(tag, "y"))
        for tag in elements(drawn, "text", "tag")
    }
    reason = tags["target"]
    level = next(place for text, place in tags.items() if text.startswith("target "))

    assert abs(reason[1] - level[1]) > 8.0, "the exit reason must not be drawn over the level's own label"


def test_an_exit_reason_the_simulator_never_writes_is_drawn_rather_than_dropped():
    data = dataset()
    drawn = chart.chart(log([100], [110], data, exit_reasons=["Stop1"]), data, 1)

    assert elements(drawn, "circle", chart.OTHER_EXIT)
    assert "Stop1" in drawn.svg


def test_every_simulator_exit_reason_has_a_class_of_its_own():
    assert set(chart.EXIT_CLASSES) == set(trades.EXIT_REASONS.values())
    assert chart.OTHER_EXIT not in set(chart.EXIT_CLASSES.values()) - {chart.OTHER_EXIT}


def test_the_stop_and_target_span_only_the_bars_the_leg_carried_them():
    drawn, _, trades_log = case()
    for css, column in zip(("stop", "target"), chart.LEVELS, strict=True):
        line = only(drawn, "line", css)

        assert number(line, "y1") == at(drawn.plot.y(float(trades_log[column].iloc[0])))
        assert number(line, "x1") == at(drawn.plot.x(100) - drawn.plot.bar_width / 2)
        assert number(line, "x2") == at(drawn.plot.x(110) + drawn.plot.bar_width / 2)


def test_the_excursions_are_drawn_at_the_prices_the_log_recorded_them_at():
    drawn, _, trades_log = case()
    entry = float(trades_log["entry_price"].iloc[0])

    assert number(only(drawn, "line", "adverse"), "y1") == at(drawn.plot.y(entry - 3.0))
    assert number(only(drawn, "line", "favourable"), "y1") == at(drawn.plot.y(entry + 12.0))


def test_the_figures_are_the_ones_stats_per_trade_computes():
    drawn, _, trades_log = case()
    expected = stats.per_trade(trades_log).loc[1]

    assert drawn.figures.net_pnl == pytest.approx(float(expected["net_pnl"]))
    assert drawn.figures.r_multiple == pytest.approx(float(expected["r_multiple"]))
    assert drawn.figures.bars_held == int(expected["bars_held"])
    assert drawn.figures.mfe_points == pytest.approx(float(expected["mfe_points"]))


def test_a_scale_out_draws_one_entry_and_one_exit_per_leg():
    data = dataset()
    scaled = log([100, 100], [108, 116], data, trade_ids=[1, 1], exit_reasons=["target", "session_close"])
    drawn = chart.chart(scaled, data, 1)

    assert len(elements(drawn, "polygon", "entry")) == 2
    assert len(elements(drawn, "circle", "exit")) == 2
    assert drawn.exit_bars == (108, 116)


# -- the two things a chart must not draw -------------------------------------


def test_no_line_joins_the_entry_to_the_exit():
    drawn, _, _ = case()
    sloped = [
        line
        for line in elements(drawn, "line")
        if number(line, "x1") != number(line, "x2") and number(line, "y1") != number(line, "y2")
    ]

    assert not sloped, (
        "every line must be a vertical wick or a horizontal level; a sloped one would draw a "
        "path between two fills, which bar-close OHLC does not record"
    )


def test_a_chart_states_the_caution_it_must_not_be_read_without():
    drawn, _, _ = case()
    printed = " ".join("".join(element.itertext()) for element in elements(drawn, "text", "caution"))

    assert printed.split() == chart.CAUTION.split()


# -- the window ---------------------------------------------------------------


def test_the_caution_stays_inside_the_canvas_however_narrow_the_chart():
    """The narrowest chart wraps the caution over many lines; the canvas has to grow with it."""
    drawn, _, _ = case(bars_either_side=0)
    root = ElementTree.fromstring(drawn.svg)
    lowest = max(number(line, "y") for line in elements(drawn, "text", "caution"))

    assert len(elements(drawn, "text", "caution")) > 1
    assert lowest <= float(root.get("height") or 0)


def test_the_window_is_the_trade_plus_the_bars_either_side_asked_for():
    drawn, _, _ = case(bars_either_side=12)

    assert (drawn.first_bar, drawn.last_bar) == (88, 122)
    assert len(elements(drawn, "line", "wick")) == 35


def test_zero_bars_either_side_draws_the_trade_and_nothing_around_it():
    drawn, _, _ = case(bars_either_side=0)

    assert (drawn.first_bar, drawn.last_bar) == (100, 110)


def test_the_window_is_clipped_to_the_dataset_at_both_ends():
    data = dataset()
    drawn = chart.chart(log([1], [BARS - 2], data), data, 1, bars_either_side=50)

    assert (drawn.first_bar, drawn.last_bar) == (0, BARS - 1)


def test_a_window_with_no_price_range_still_has_a_span_to_draw_on():
    data = dataset(flat=True)
    drawn = chart.chart(log([100], [110], data), data, 1)

    assert drawn.plot.price_max > drawn.plot.price_min


# -- what a log may leave out -------------------------------------------------


def test_a_log_with_no_bar_indices_is_drawn_from_its_fill_times():
    data = dataset()
    imported = log([100], [110], data)
    for name in ("entry_bar", "exit_bar"):
        imported[name] = pd.Series(pd.NA, index=imported.index, dtype="Int64")

    # A fill inside the bar rather than on its stamp, which belongs to the next one.
    imported["entry_time"] = data.index[100] - pd.Timedelta(seconds=30)
    imported["exit_time"] = data.index[110] - pd.Timedelta(seconds=30)
    drawn = chart.chart(imported, data, 1)
    expected = annotate.bars_for_fills(data.index, pd.DatetimeIndex(imported["entry_time"]))

    assert drawn.entry_bars == (int(expected[0]),)


def test_a_log_leaving_the_excursions_null_draws_no_excursion_line():
    data = dataset()
    blanked = log([100], [110], data)
    for name in ("mae_points", "mfe_points", "r_multiple"):
        blanked[name] = pd.Series(np.nan, index=blanked.index, dtype="float64")

    blanked["bars_held"] = pd.Series(pd.NA, index=blanked.index, dtype="Int64")
    blanked["ambiguous_bar"] = pd.Series(pd.NA, index=blanked.index, dtype="boolean")
    drawn = chart.chart(blanked, data, 1)

    assert not elements(drawn, "line", "excursion")
    assert np.isnan(drawn.figures.r_multiple)
    assert drawn.figures.bars_held == 0


def test_a_log_carrying_no_bracket_draws_no_level_line():
    data = dataset()
    bracketless = log([100], [110], data).drop(columns=list(chart.LEVELS))
    drawn = chart.chart(bracketless, data, 1)

    assert not elements(drawn, "line", "level")
    assert elements(drawn, "circle", "exit")


def test_a_leg_carrying_no_target_still_draws_the_stop_it_did_carry():
    """A signal exit has a stop and no target, and both levels are nullable per row."""
    data = dataset()
    targetless = log([100], [110], data, exit_reasons=["signal"])
    targetless["target_price"] = np.nan
    drawn = chart.chart(targetless, data, 1)

    assert elements(drawn, "line", "stop")
    assert not elements(drawn, "line", "target")


def test_a_fill_outside_its_bar_is_drawn_rather_than_refused():
    data = dataset()
    shifted = log([100], [110], data)
    shifted["exit_price"] = float(shifted["exit_price"].iloc[0]) + 500.0
    drawn = chart.chart(shifted, data, 1)
    disc = only(drawn, "circle", "exit")

    assert drawn.plot.top <= number(disc, "cy") <= drawn.plot.top + drawn.plot.height


# -- what a chart refuses -----------------------------------------------------


def test_a_trade_the_log_does_not_hold_is_refused():
    data = dataset()
    with pytest.raises(ChartError, match="no trade 99"):
        chart.chart(log([100], [110], data), data, 99)


def test_a_frame_that_is_not_a_trade_log_is_refused():
    data = dataset()
    with pytest.raises(ChartError, match="mae_points"):
        chart.chart(log([100], [110], data).drop(columns=["mae_points"]), data, 1)


def test_a_negative_context_window_is_refused():
    data = dataset()
    with pytest.raises(ChartError, match="bars_either_side"):
        chart.chart(log([100], [110], data), data, 1, bars_either_side=-1)


def test_bars_of_a_different_series_of_the_same_shape_are_refused():
    data = dataset()
    trades_log = log([100], [110], data)
    other = context.prepare(
        bars().set_axis(bars().index + pd.Timedelta(hours=1)),
        ContextSpec(),
        price_basis=PriceBasis.RAW,
    )
    with pytest.raises(annotate.AnnotationError, match="produced over different bars"):
        chart.chart(trades_log, other, 1)


def test_a_fill_no_bar_of_the_dataset_covers_is_refused():
    data = dataset()
    adrift = log([100], [110], data)
    for name in ("entry_bar", "exit_bar"):
        adrift[name] = pd.Series(pd.NA, index=adrift.index, dtype="Int64")

    adrift["entry_time"] = data.index[0] - pd.Timedelta(days=1)
    with pytest.raises(ChartError, match="fall in no bar"):
        chart.chart(adrift, data, 1)


# -- the document ------------------------------------------------------------


def test_the_canvas_grows_by_one_bar_width_for_each_extra_bar_of_window():
    """Sized to its window, without pinning the margins the layout is free to change."""
    narrow, _, _ = case(bars_either_side=5)
    wide, _, _ = case(bars_either_side=25)
    extra = (wide.plot.bars - narrow.plot.bars) * narrow.plot.bar_width

    assert ElementTree.fromstring(narrow.svg).tag == f"{SVG}svg"
    assert _canvas(wide) - _canvas(narrow) == at(extra)
    assert number(only(narrow, "rect", "panel"), "width") == at(narrow.plot.width)


def _canvas(drawn: chart.TradeChart) -> float:
    """The document's own width."""
    return float(ElementTree.fromstring(drawn.svg).get("width") or 0)


def test_charts_draws_each_trade_asked_for_in_order():
    data = dataset()
    many = log([50, 100, 150], [60, 110, 160], data)
    drawn = chart.charts(many, data, [3, 1])

    assert [one.trade_id for one in drawn] == [3, 1]


def test_save_writes_the_svg_where_it_was_asked_to(tmp_path):
    drawn, _, _ = case()
    written = drawn.save(tmp_path / "charts" / "trade-1.svg")

    assert written.read_text(encoding="utf-8") == drawn.svg == str(drawn)


def test_a_title_replaces_the_headline_and_nothing_else():
    drawn, _, _ = case(title="Trade 1 <the one that got away>")

    assert "Trade 1 &lt;the one that got away&gt;" in drawn.svg
    assert elements(drawn, "circle", "exit")
