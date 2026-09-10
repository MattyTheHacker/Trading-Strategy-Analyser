"""Chart tests: one trade drawn on the bars it happened on.

Every geometric claim is asserted against ``chart.plot``'s own mapping rather than against a
coordinate written down here, so a change to the layout cannot silently move a mark off its
price. Three claims are pinned harder than the rest, because each would draw a plausible and
wrong picture rather than raise. **No line joins an entry to its exit**, because the path
between them is what bar-close OHLC does not record. **A fill outside its bar is drawn rather
than refused**, since that is what a back-adjusted series produces and a chart is the instrument
that makes it visible. **Bars of a different series are refused**, through the same check an
annotation applies.

The overlays add two more of the same kind. **An overlay is a per-bar series and not a path
between two points**, which is what the no-sloped-line pin becomes once a moving average is
allowed to slope. **A per-session level is never drawn across the session beside it**, or a
chart would state a level that never existed.
"""

import re
from itertools import pairwise
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import pytest

from nqbt import (
    annotate,
    archetypes,
    chart,
    conditions,
    context,
    higher_timeframe,
    paths,
    sessionrange,
    sessions,
    splice,
    stats,
    sweep,
    trades,
)
from nqbt.chart import ChartError
from nqbt.context import ContextSpec, PriceBasis

BASE = 18000.0
BARS = 200
SVG = "{http://www.w3.org/2000/svg}"
ROUNDING = 0.005
"""Half of the last decimal the document is written to."""
FIRST_MINUTE = "2024-01-03 14:00"
SECOND_DAY = "2024-01-04 14:00"
"""The next trading day, so a per-session level has a session beside it to be smeared onto."""
LIFT = 50.0
"""Points the second day sits above the first, so the two sessions' ranges cannot coincide."""
RANGE_KEY = sessionrange.validate_key(sessionrange.CASH_OPEN_MINUTES, 15, 1)
HTF_KEY = higher_timeframe.key(5, 3)
INDICATOR_SPEC = ContextSpec(
    ma_keys=conditions.ma_keys(ema=(9,), sma=(20,)),
    band_periods=(20,),
    needs_vwap=True,
    needs_vwap_band=True,
    higher_timeframe_keys=(HTF_KEY,),
    range_keys=(RANGE_KEY,),
    needs_ma_values=True,
)
"""Every price-panel series a chart can overlay, and nothing that is not one."""


def bars(
    count: int = BARS,
    *,
    flat: bool = False,
    start: str = FIRST_MINUTE,
    base: float = BASE,
) -> pd.DataFrame:
    """``count`` one-minute bars with a zig-zag close, or one flat price when ``flat``.

    The zig-zag gives every bar a body and a wick either side; the flat case is the degenerate
    window whose price span would otherwise be zero.
    """
    index = pd.date_range(start, periods=count, freq="min", tz="UTC")
    close = (
        np.full(count, base)
        if flat
        else base + 0.25 * np.cumsum(np.where((np.arange(count) // 15) % 2 == 0, 1.0, -1.0))
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


def with_indicators() -> tuple[context.Dataset, list[chart.Overlay]]:
    """Two trading days of bars carrying every series a chart can overlay, and those overlays."""
    frame = pd.concat([bars(), bars(start=SECOND_DAY, base=BASE + LIFT)])
    data = context.prepare(frame, INDICATOR_SPEC, price_basis=PriceBasis.RAW)

    return data, chart.overlays_for(data)


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


def vertices(element: ElementTree.Element) -> list[tuple[float, float]]:
    """One polyline's points, in the order it draws them."""
    points = (element.get("points") or "").split()

    return [(float(x), float(y)) for x, y in (point.split(",") for point in points)]


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


# -- the indicators drawn over the bars ---------------------------------------


def test_overlays_for_draws_every_price_series_the_dataset_holds():
    """What a dataset holds is what the archetype it was prepared for declared it reads."""
    data, drawn = with_indicators()
    labels = [one.label for one in drawn]

    assert labels == sorted(set(labels), key=labels.index), "no series may be drawn twice"
    assert {"ema(9)", "sma(20)"} <= set(labels), "one entry per moving-average key"
    assert [one for one in labels if one.startswith("bb(20")], "one entry per band period"
    assert [one for one in labels if one.startswith("ema(3) @ 5m")], "one entry per coarse average"
    assert [one for one in labels if one.startswith("range(930")], "one entry per session range"
    assert data.band is not None and data.session_ranges is not None


def test_a_vwap_band_is_drawn_instead_of_the_vwap_and_never_beside_it():
    """The band's basis is that VWAP, so drawing both would draw one series twice."""
    data, drawn = with_indicators()
    banded = [one.label for one in drawn]
    bare = context.prepare(bars(), ContextSpec(needs_vwap=True), price_basis=PriceBasis.RAW)

    assert "vwap" not in banded
    assert [one for one in banded if one.startswith("vwap band")]
    assert [one.label for one in chart.overlays_for(bare)] == ["vwap"]


def test_a_dataset_that_declared_nothing_has_nothing_to_overlay():
    assert chart.overlays_for(dataset()) == []


def test_a_grid_that_kept_only_its_gate_is_skipped_rather_than_refused():
    """``needs_ma_values`` is off by default, and a boolean gate has no line in it to draw."""
    spec = ContextSpec(ma_keys=conditions.ma_keys(ema=(9,)))
    data = context.prepare(bars(), spec, price_basis=PriceBasis.RAW)

    assert chart.overlays_for(data) == []
    with pytest.raises(ValueError, match="keep_values"):
        chart.moving_average(data, "ema", 9)


def test_asking_for_a_series_the_dataset_does_not_hold_names_the_field_to_set():
    data = dataset()
    with pytest.raises(context.ContextError, match="needs_vwap"):
        chart.session_vwap(data)


def test_an_overlay_that_is_not_one_value_per_bar_is_refused():
    data = dataset()
    trades_log = log([100], [110], data)
    short = chart.Overlay(label="short", values=np.zeros(len(data) - 1))
    cube = chart.Overlay(label="cube", values=np.zeros((2, 2, len(data))))

    with pytest.raises(ChartError, match="one per bar"):
        chart.chart(trades_log, data, 1, overlays=[short])

    with pytest.raises(ChartError, match="'cube'"):
        chart.chart(trades_log, data, 1, overlays=[cube])


def test_an_overlay_is_a_per_bar_series_rather_than_a_path_between_two_points():
    """The no-sloped-line pin, once a moving average is allowed to slope.

    Every vertex sits on a bar centre of the window and steps one bar at a time, so a two-point
    path from an entry fill to an exit fill cannot be drawn as an overlay either.
    """
    data, drawn_overlays = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=drawn_overlays)
    centres = {round(drawn.plot.x(bar), 2) for bar in range(drawn.first_bar, drawn.last_bar + 1)}

    assert elements(drawn, "polyline")
    for line in elements(drawn, "polyline"):
        drawn_at = [round(x, 2) for x, _ in vertices(line)]
        steps = {round(later - earlier, 2) for earlier, later in pairwise(drawn_at)}

        assert set(drawn_at) <= centres, "every vertex must sit on a bar of the window"
        assert steps <= {0.0, round(drawn.plot.bar_width, 2)}, "a series steps one bar at a time"


def test_an_overlay_far_from_the_window_does_not_move_the_price_axis():
    """A long average sitting off the window would squash the trade it is context for."""
    data = dataset()
    trades_log = log([100], [110], data)
    adrift = chart.Overlay(label="adrift", values=np.full(len(data), BASE + 5000.0))
    plain = chart.chart(trades_log, data, 1)
    drawn = chart.chart(trades_log, data, 1, overlays=[adrift])

    assert (drawn.plot.price_min, drawn.plot.price_max) == (plain.plot.price_min, plain.plot.price_max)
    assert elements(drawn, "polyline"), "and it is drawn rather than dropped"


def test_every_overlay_is_drawn_inside_the_panel_it_may_not_rescale():
    data, drawn_overlays = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=drawn_overlays)
    root = ElementTree.fromstring(drawn.svg)
    clip = root.find(f"{SVG}defs/{SVG}clipPath")
    assert clip is not None, "an overlay is clipped rather than fitted"

    box = clip.find(f"{SVG}rect")
    panel = only(drawn, "rect", "panel")
    clipped = [group for group in root.iter(f"{SVG}g") if group.get("clip-path") == f"url(#{clip.get('id')})"]

    assert box is not None
    assert [number(box, name) for name in ("x", "y", "width", "height")] == [
        number(panel, name) for name in ("x", "y", "width", "height")
    ]
    inside = [line.tag for group in clipped for line in group]

    assert inside == [f"{SVG}polyline"] * len(elements(drawn, "polyline"))


def test_two_charts_in_one_document_are_clipped_to_their_own_panels():
    """An SVG id is document-scoped, and a page of charts is one document.

    A fixed clip-path name makes every chart after the first resolve to the first one's panel,
    which silently draws every series as though it stopped part-way along.
    """
    data, drawn_overlays = with_indicators()
    trades_log = log([100], [110], data)
    wide = chart.chart(trades_log, data, 1, bars_either_side=BARS, overlays=drawn_overlays)
    narrow = chart.chart(trades_log, data, 1, bars_either_side=2, overlays=drawn_overlays)
    again = chart.chart(trades_log, data, 1, bars_either_side=BARS, overlays=drawn_overlays)

    assert _clip(wide) != _clip(narrow), "two panels, two clip paths"
    assert _clip(wide) == _clip(again), "one panel is one clip path, however often it is drawn"
    for one in (wide, narrow):
        box = ElementTree.fromstring(one.svg).find(f"{SVG}defs/{SVG}clipPath/{SVG}rect")
        panel = only(one, "rect", "panel")

        assert box is not None
        assert box.attrib == {name: panel.get(name) for name in ("x", "y", "width", "height")}


def _clip(drawn: chart.TradeChart) -> str:
    """The id of the clip path one chart's overlays are drawn inside."""
    found = ElementTree.fromstring(drawn.svg).find(f"{SVG}defs/{SVG}clipPath")
    assert found is not None, "an overlaid chart clips its overlays"

    return found.get("id") or ""


def test_a_gap_in_a_series_breaks_the_line_rather_than_being_drawn_through_it():
    data = dataset()
    gapped = np.full(len(data), BASE)
    gapped[105] = np.nan
    drawn = chart.chart(
        log([100], [110], data),
        data,
        1,
        overlays=[chart.Overlay(label="gapped", values=gapped)],
    )
    missing = round(drawn.plot.x(105), 2)

    assert len(elements(drawn, "polyline")) == 2
    assert all(
        missing not in [round(x, 2) for x, _ in vertices(line)] for line in elements(drawn, "polyline")
    )


def test_a_run_of_one_bar_is_drawn_rather_than_dropped():
    """A range completing on a session's last bar is one bar wide, and still happened."""
    data = dataset()
    lone = np.full(len(data), np.nan)
    lone[105] = BASE
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=[chart.Overlay(label="lone", values=lone)])
    points = vertices(only(drawn, "polyline", "series"))

    assert points == [(at(drawn.plot.x(105)), at(drawn.plot.y(BASE)))] * 2


def test_a_session_range_is_never_drawn_across_the_session_beside_it():
    """A range is one fact per session; a run joining two of them states a level that never was."""
    data, _ = with_indicators()
    overlay = chart.opening_range(data, RANGE_KEY)
    drawn = chart.chart(log([100], [110], data), data, 1, bars_either_side=BARS, overlays=[overlay])

    assert np.array_equal(np.isfinite(overlay.rows).all(axis=0), data.range_armed(RANGE_KEY))
    assert len(elements(drawn, "polyline")) == 4, "a high and a low, on each of the two sessions"
    for line in elements(drawn, "polyline"):
        assert len({round(y, 2) for _, y in vertices(line)}) == 1, "a range does not slope"


def test_a_band_is_one_legend_entry_and_one_colour_whatever_its_row_count():
    data, _ = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=[chart.bollinger(data, 20)])
    lines = elements(drawn, "polyline")

    assert len(lines) == 3, "upper, midline and lower"
    assert len({line.get("class") for line in lines}) == 1
    assert len(elements(drawn, "text", "legend")) == 1


def test_every_overlay_is_named_in_the_legend():
    data, drawn_overlays = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=drawn_overlays)
    named = ["".join(entry.itertext()) for entry in elements(drawn, "text", "legend")]

    assert named == [one.label for one in drawn_overlays]


def test_the_legend_makes_its_own_room_above_the_panel():
    data, drawn_overlays = with_indicators()
    trades_log = log([100], [110], data)
    plain = chart.chart(trades_log, data, 1)
    drawn = chart.chart(trades_log, data, 1, overlays=drawn_overlays)

    assert drawn.plot.top > plain.plot.top
    assert all(number(entry, "y") < drawn.plot.top for entry in elements(drawn, "text", "legend"))
    assert float(ElementTree.fromstring(drawn.svg).get("height") or 0) > _canvas_height(plain)


def _canvas_height(drawn: chart.TradeChart) -> float:
    """The document's own height."""
    return float(ElementTree.fromstring(drawn.svg).get("height") or 0)


def test_a_legend_too_wide_for_the_panel_wraps_rather_than_running_off_it():
    data, drawn_overlays = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, bars_either_side=0, overlays=drawn_overlays)
    rows = {number(entry, "y") for entry in elements(drawn, "text", "legend")}

    assert len(rows) > 1
    assert max(rows) < drawn.plot.top


def test_the_trade_geometry_is_dashed_where_the_market_context_is_solid():
    """A reader has to be able to tell what the trade carried from what the market was doing."""
    data, _ = with_indicators()
    drawn = chart.chart(log([100], [110], data), data, 1, overlays=[chart.session_vwap(data)])
    style = ElementTree.fromstring(drawn.svg).find(f"{SVG}style")

    assert style is not None
    assert re.search(r"\.level \{[^}]*stroke-dasharray", style.text or "")
    assert re.search(r"\.excursion \{[^}]*stroke-dasharray", style.text or "")
    assert not re.search(r"\.series \{[^}]*stroke-dasharray", style.text or "")


def test_a_chart_asked_for_no_overlays_draws_neither_a_line_nor_a_legend():
    drawn, _, _ = case()

    assert not elements(drawn, "polyline")
    assert not elements(drawn, "text", "legend")
    assert "clipPath" not in drawn.svg


def test_charts_draws_the_same_overlays_on_every_trade():
    data, drawn_overlays = with_indicators()
    many = log([50, 100], [60, 110], data)
    drawn = chart.charts(many, data, [1, 2], overlays=drawn_overlays)

    assert [len(elements(one, "polyline")) for one in drawn] == [len(elements(drawn[0], "polyline"))] * 2


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


def test_the_readme_worked_example_names_things_that_still_exist():
    """A rotted worked example is worse than none, and nothing else here would catch a rename.

    The example itself needs ``cache/`` and cannot run in CI, so what is pinned is the surface
    it calls: every name it uses, in both directions.
    """
    readme = (paths.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    fence = "```"
    found = re.search(rf"#+ Looking at one trade.*?{fence}python\n(.*?){fence}", readme, re.DOTALL)
    assert found, "the README no longer carries a chart example"

    example = found.group(1)
    compile(example, "README.md", "exec")
    for module, name in (
        (splice, "load_continuous"),
        (sweep, "Grid"),
        (sweep, "prepare_for"),
        (sweep, "run_combination"),
        (archetypes, "get"),
        (chart, "charts"),
        (chart, "overlays_for"),
    ):
        used = f"{module.__name__.removeprefix('nqbt.')}.{name}"

        assert used in example, f"the example no longer calls {used}"
        assert hasattr(module, name), f"the example calls {used}, which no longer exists"

    assert "drawn.save(" in example
    assert hasattr(chart.TradeChart, "save")


def test_save_writes_the_svg_where_it_was_asked_to(tmp_path):
    drawn, _, _ = case()
    written = drawn.save(tmp_path / "charts" / "trade-1.svg")

    assert written.read_text(encoding="utf-8") == drawn.svg == str(drawn)


def test_a_title_replaces_the_headline_and_nothing_else():
    drawn, _, _ = case(title="Trade 1 <the one that got away>")

    assert "Trade 1 &lt;the one that got away&gt;" in drawn.svg
    assert elements(drawn, "circle", "exit")
