import pytest

from nqbt.instruments import MNQ, NQ, ContractId, get_instrument


def test_tick_values_differ_tenfold_between_nq_and_mnq() -> None:
    # The bug that bit DeadCatBounce.cs: a tick-based risk cap means 10x the dollars
    # on NQ that it does on MNQ.
    assert NQ.tick_value == pytest.approx(5.00)
    assert MNQ.tick_value == pytest.approx(0.50)
    assert NQ.ticks_to_dollars(8, quantity=4) == pytest.approx(160.0)
    assert MNQ.ticks_to_dollars(8, quantity=4) == pytest.approx(16.0)


def test_point_and_tick_conversions_round_trip() -> None:
    assert MNQ.points_to_ticks(2.5) == pytest.approx(10.0)
    assert MNQ.ticks_to_points(10) == pytest.approx(2.5)
    assert MNQ.dollars_to_points(MNQ.points_to_dollars(37.25)) == pytest.approx(37.25)


@pytest.mark.parametrize(
    ("price", "mode", "expected"),
    [
        (16019.26, "nearest", 16019.25),
        (16019.40, "nearest", 16019.50),
        (16019.26, "up", 16019.50),
        (16019.26, "down", 16019.25),
        (16019.25, "up", 16019.25),  # already on the grid, must not be nudged
        (16019.25, "down", 16019.25),
    ],
)
def test_round_to_tick(price, mode, expected) -> None:
    assert MNQ.round_to_tick(price, mode) == pytest.approx(expected)


def test_round_to_tick_handles_arithmetic_residue() -> None:
    # A 1.5R target computed from a fractional risk lands off-grid; it must snap back.
    entry, risk = 16017.25, 3.75
    target = entry - risk * 1.5
    assert not MNQ.is_on_tick(target)
    assert MNQ.is_on_tick(MNQ.round_to_tick(target))


def test_price_decimals() -> None:
    assert MNQ.price_decimals == 2


def test_position_size_rounds_down_and_can_refuse_the_trade() -> None:
    # 10 points of stop distance = $20/contract on MNQ.
    assert MNQ.position_size_for_risk(100.0, 10.0) == 5
    assert MNQ.position_size_for_risk(95.0, 10.0) == 4
    # Same stop on NQ is $200/contract, so a $100 cap allows nothing.
    assert NQ.position_size_for_risk(100.0, 10.0) == 0


def test_position_size_rejects_nonpositive_stop() -> None:
    with pytest.raises(ValueError):
        MNQ.position_size_for_risk(100.0, 0.0)


def test_contract_id_parses_nt8_export_names() -> None:
    c = ContractId.parse("MNQ 03-24")
    assert (c.root, c.month, c.year) == ("MNQ", 3, 2024)
    assert c.month_code == "H"
    assert c.nt8_name == "MNQ 03-24"
    assert c.cache_key == "MNQ_2024H"
    assert c.instrument is MNQ


def test_contract_ids_sort_into_expiry_order() -> None:
    names = ["MNQ 09-25", "MNQ 03-24", "MNQ 12-24", "MNQ 06-24"]
    ordered = sorted(ContractId.parse(n) for n in names)
    assert [c.nt8_name for c in ordered] == [
        "MNQ 03-24",
        "MNQ 06-24",
        "MNQ 12-24",
        "MNQ 09-25",
    ]


def test_contract_id_rejects_non_quarterly_months() -> None:
    with pytest.raises(ValueError, match="quarterly"):
        ContractId(year=2024, month=1, root="MNQ")


def test_contract_id_rejects_unparseable_names() -> None:
    with pytest.raises(ValueError, match="cannot parse"):
        ContractId.parse("MNQ-03-24")


def test_unknown_instrument_names_the_known_ones() -> None:
    with pytest.raises(KeyError, match="MNQ"):
        get_instrument("ES")
