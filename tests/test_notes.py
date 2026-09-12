"""Notes tests: discretionary context stored, shown, and kept out of every evaluation.

The claim pinned hardest is the one the module exists for: **free text never reaches a frame
anything groups by.** So the annotation is asserted to carry no such column, each of the three
doors into the evaluation path is asserted to refuse one, and -- because a rule nothing could
break is not a rule -- a note column is asserted to be *stratifiable* if it ever got through.

The sidecar's own hazard is a duplicate key, which is why that is an error rather than a
last-one-wins: a fanned-out join would move every number computed over the result while looking
like more rows of the same data.
"""

import numpy as np
import pandas as pd
import pytest

from nqbt import annotate, conditions, context, guard, notes, review, sessions
from nqbt.context import ContextSpec
from nqbt.notes import NotesError

BASE = 18000.0
START = "2024-01-02 15:00"
BARS = 200
SPEC = ContextSpec(ma_keys=conditions.ma_keys(ema=(3,)), needs_time_of_day=True)


def bars(count: int = BARS) -> pd.DataFrame:
    """One-minute bars whose price turns every ten bars, so a moving-average gate takes both values."""
    index = pd.date_range(START, periods=count, freq="min", tz="UTC")
    close = BASE + 0.25 * np.cumsum(np.where((np.arange(count) // 10) % 2 == 0, 1.0, -1.0))
    open_ = np.concatenate(([close[0]], close[:-1]))
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 1.0,
            "low": np.minimum(open_, close) - 1.0,
            "close": close,
            "volume": np.full(count, 100.0),
        },
        index=index,
    )
    frame["trading_day"] = sessions.classify(index).trading_day

    return frame


def dataset() -> context.Dataset:
    """Prepare the fixture bars with a gate and a clock to stratify by."""
    return context.prepare(bars(), SPEC)


def sim_log(data: context.Dataset, count: int = 30, first: int = 20, hold: int = 2) -> pd.DataFrame:
    """Build a simulated log carrying every column ``summarise`` reads, one leg per trade."""
    at = np.arange(first, first + count, dtype=np.int64)
    out = at + hold
    net = np.where(np.arange(count) % 2 == 0, -50.0, 100.0)

    return pd.DataFrame(
        {
            "source": pd.array(["sim"] * count, dtype="string"),
            "instrument": pd.array(["MNQ"] * count, dtype="string"),
            "trade_id": np.arange(1, count + 1, dtype=np.int64),
            "leg": np.ones(count, dtype=np.int64),
            "entry_bar": at,
            "exit_bar": out,
            "entry_time": data.index[at],
            "exit_time": data.index[out],
            "entry_price": data.close[at],
            "exit_price": data.close[out],
            "quantity": np.ones(count, dtype=np.int64),
            "direction": np.ones(count),
            "net_pnl": net,
            "gross_pnl": net + 1.5,
            "commission": np.full(count, 1.5),
            "exit_reason": pd.array(["target"] * count, dtype="string"),
            "bars_held": np.full(count, hold, dtype=np.int64),
            "mae_points": np.full(count, 1.0),
            "mfe_points": np.full(count, 2.0),
            "r_multiple": net / 10.0,
            "ambiguous_bar": np.zeros(count, dtype=bool),
        },
    )


def noted(*pairs: tuple[int, str]) -> notes.Notes:
    """Build a sidecar from ``(trade_id, note)`` pairs."""
    written = notes.empty()
    for trade_id, text in pairs:
        written = notes.record(written, trade_id, text)

    return written


def with_note_column(annotation: annotate.Annotation) -> annotate.Annotation:
    """Merge a note onto an annotation, which is what the three doors have to refuse."""
    frame = annotation.frame.copy()
    frame["note"] = pd.array(["chased it"] * len(frame), dtype="string")

    return annotate.Annotation(frame=frame, conditions=(*annotation.conditions, "note"))


# -- the sidecar's shape ------------------------------------------------------


def test_an_empty_sidecar_carries_the_dtypes_a_populated_one_carries() -> None:
    """The dtypes must not depend on whether anything has been written yet."""
    blank = notes.empty()
    populated = noted((1, "clean setup"))
    assert blank.trades == 0
    assert blank.frame.dtypes.to_dict() == populated.frame.dtypes.to_dict()
    assert blank.frame.index.name == notes.KEY


def test_a_note_is_keyed_by_trade_and_replaces_whatever_that_trade_already_said() -> None:
    written = notes.record(noted((4, "impatient")), 4, "reconsidered", screenshot="shots/4.png")
    assert written.trades == 1
    assert written.frame.loc[4, "note"] == "reconsidered"
    assert written.frame.loc[4, "screenshot"] == "shots/4.png"


def test_a_note_of_nothing_but_whitespace_is_refused_rather_than_stored() -> None:
    with pytest.raises(NotesError, match="empty"):
        notes.record(notes.empty(), 1, "   ")


def test_two_notes_on_one_trade_are_refused_because_a_join_would_fan_out() -> None:
    """The sidecar's own hazard: duplicate keys multiply rows and move every number over them."""
    frame = pd.DataFrame(
        {"note": pd.array(["a", "b"], dtype="string"), "screenshot": pd.array([None, None], dtype="string")},
        index=pd.Index([1, 1], name=notes.KEY),
    )
    with pytest.raises(NotesError, match="more than one note"):
        notes.Notes(frame=frame)


def test_a_frame_keyed_by_something_other_than_a_trade_is_not_a_sidecar() -> None:
    frame = notes.empty().frame.rename_axis("row")
    with pytest.raises(NotesError, match="keyed by trade_id"):
        notes.Notes(frame=frame)


def test_a_frame_holding_no_free_text_at_all_is_not_a_sidecar() -> None:
    frame = pd.DataFrame(index=pd.Index([], name=notes.KEY, dtype="int64"))
    with pytest.raises(NotesError, match="missing column"):
        notes.Notes(frame=frame)


def test_a_sidecar_says_how_many_trades_are_noted_and_how_many_name_a_screenshot() -> None:
    written = notes.record(noted((3, "clean setup")), 7, "chased it", screenshot="shots/7.png")
    assert str(notes.empty()) == "0 trade(s) noted, 0 naming a screenshot"
    assert str(written) == "2 trade(s) noted, 1 naming a screenshot"


# -- stored, and read back ----------------------------------------------------


def test_a_sidecar_survives_a_write_and_a_read_unchanged(tmp_path) -> None:
    written = noted((3, "clean setup"))
    written = notes.record(written, 7, "chased it", screenshot="shots/7.png")
    path = tmp_path / "kept" / "notes.csv"

    notes.write(written, path)
    pd.testing.assert_frame_equal(notes.read(path).frame, written.frame)


def test_a_note_containing_a_comma_and_a_newline_survives_the_round_trip(
    tmp_path,
) -> None:
    """Free text is free: the storage format may not decide what a note is allowed to say."""
    prose = "waited, then chased\nshould have skipped it"
    path = tmp_path / "notes.csv"

    notes.write(noted((1, prose)), path)
    assert notes.read(path).frame.loc[1, "note"] == prose


def test_a_mistyped_header_is_refused_rather_than_read_as_a_note_nobody_wrote(
    tmp_path,
) -> None:
    path = tmp_path / "notes.csv"
    path.write_text("trade_id,note,screenshot,mood\n1,chased it,,calm\n", encoding="utf-8")
    with pytest.raises(NotesError, match="unknown column"):
        notes.read(path)


def test_a_file_that_is_not_a_sidecar_is_refused_by_name(tmp_path) -> None:
    path = tmp_path / "notes.csv"
    path.write_text("id,text\n1,chased it\n", encoding="utf-8")
    with pytest.raises(NotesError, match="not a notes sidecar"):
        notes.read(path)


def test_a_trade_id_that_is_not_a_whole_number_names_the_row_it_is_on(
    tmp_path,
) -> None:
    path = tmp_path / "notes.csv"
    path.write_text("trade_id,note,screenshot\n1,fine,\nlast,chased it,\n", encoding="utf-8")
    with pytest.raises(NotesError, match="row 1 carries 'last'"):
        notes.read(path)


# -- shown, at the one boundary -----------------------------------------------


def test_attaching_puts_each_trades_note_on_every_leg_of_it() -> None:
    log = pd.DataFrame({"trade_id": [3, 3, 7], "net_pnl": [1.0, 2.0, -3.0]})
    attached = notes.alongside(log, noted((3, "clean setup"), (7, "chased it")))
    assert attached["note"].tolist() == ["clean setup", "clean setup", "chased it"]


def test_attaching_leaves_a_trade_with_no_note_null_rather_than_blank() -> None:
    """An unwritten note and an empty one are different statements about a trade."""
    per_trade = pd.DataFrame({"net_pnl": [1.0, 2.0]}, index=pd.Index([1, 2], name=notes.KEY))
    attached = notes.alongside(per_trade, noted((1, "clean setup")))
    assert attached.loc[1, "note"] == "clean setup"
    assert attached["note"].isna().tolist() == [False, True]


def test_attaching_changes_no_number_it_was_given() -> None:
    log = pd.DataFrame({"trade_id": [3, 7], "net_pnl": [1.0, -3.0]})
    attached = notes.alongside(log, noted((3, "clean setup")))
    pd.testing.assert_frame_equal(attached[log.columns], log)


def test_a_frame_naming_no_trade_cannot_be_attached_to() -> None:
    with pytest.raises(NotesError, match="keyed by neither"):
        notes.alongside(pd.DataFrame({"net_pnl": [1.0]}), noted((1, "clean setup")))


def test_attaching_twice_is_refused_so_a_joined_frame_cannot_travel_onwards() -> None:
    log = pd.DataFrame({"trade_id": [3], "net_pnl": [1.0]})
    written = noted((3, "clean setup"))
    with pytest.raises(NotesError, match="free-text column"):
        notes.alongside(notes.alongside(log, written), written)


# -- structurally excluded from evaluation ------------------------------------


def test_the_annotation_frame_carries_no_free_text_column() -> None:
    """#49's mechanical check: conditions come from the bars, and there is no other route in."""
    data = dataset()
    annotation = annotate.annotate_trades(sim_log(data), data)
    assert not set(notes.TEXT_COLUMNS) & set(annotation.frame.columns)
    assert not set(notes.TEXT_COLUMNS) & set(annotation.conditions)


def test_a_note_column_would_be_stratifiable_which_is_why_it_never_arrives() -> None:
    """The rule is load-bearing: a few dozen trades' notes are exactly a stratification's shape."""
    frame = pd.DataFrame({"note": pd.array(["impatient", "clean", "late"] * 10, dtype="string")})
    assert review.stratifiable(frame, ("note",)) == ("note",)


def test_a_log_carrying_notes_cannot_be_annotated() -> None:
    data = dataset()
    log = notes.alongside(sim_log(data), noted((1, "chased it")))
    with pytest.raises(NotesError, match="free-text column"):
        annotate.annotate_trades(log, data)


def test_an_annotation_carrying_notes_cannot_be_reviewed() -> None:
    data = dataset()
    log = sim_log(data)
    annotation = annotate.annotate_trades(log, data)
    assert not review.review(log, annotation, min_trades=1).strata.empty, "the clean case reviews"

    with pytest.raises(NotesError, match="free-text column"):
        review.review(log, with_note_column(annotation), min_trades=1)


def test_an_annotation_carrying_notes_cannot_be_guarded() -> None:
    data = dataset()
    log = sim_log(data)
    with pytest.raises(NotesError, match="free-text column"):
        guard.guard(log, with_note_column(annotate.annotate_trades(log, data)), min_trades=1)


def test_naming_a_note_as_a_condition_does_not_get_it_past_the_door() -> None:
    """The refusal is on the frame, so asking for the column by name reaches the same wall."""
    data = dataset()
    log = sim_log(data)
    noted_annotation = with_note_column(annotate.annotate_trades(log, data))
    with pytest.raises(NotesError, match="free-text column"):
        review.review(log, noted_annotation, conditions=["note"], min_trades=1)
