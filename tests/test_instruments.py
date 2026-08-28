import pytest

from nqbt.instruments import (
    CL,
    ES,
    GC,
    MCL,
    MES,
    MGC,
    MNQ,
    NQ,
    SI,
    SIL,
    ContractId,
    get_instrument,
    months_from_codes,
)


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


def test_contract_id_rejects_a_month_its_root_does_not_list() -> None:
    with pytest.raises(ValueError, match=r"MNQ lists \[3, 6, 9, 12\] \(HMUZ\)"):
        ContractId(year=2024, month=1, root="MNQ")

    # March is quarterly, but gold lists the even months instead.
    with pytest.raises(ValueError, match=r"GC lists .* \(GJMQVZ\)"):
        ContractId.parse("GC 03-26")


def test_contract_id_rejects_a_root_that_is_not_registered() -> None:
    """The gate that lets NG 02-26 be rejected for being natural gas, not for February."""
    with pytest.raises(ValueError, match="unknown root 'NG'"):
        ContractId.parse("NG 03-26")


def test_each_root_lists_the_months_its_exchange_lists() -> None:
    assert ContractId.parse("ES 12-25").cache_key == "ES_2025Z"
    assert ContractId.parse("GC 02-26").cache_key == "GC_2026G"
    assert ContractId.parse("SI 07-26").cache_key == "SI_2026N"
    # Crude lists every month, including ones no other registered root does.
    assert ContractId.parse("CL 11-26").cache_key == "CL_2026X"


def test_tick_values_match_the_published_contract_specs() -> None:
    """tick_size x point_value is the figure CME publishes, which cross-checks both."""
    assert ES.tick_value == pytest.approx(12.50)
    assert GC.tick_value == pytest.approx(10.00)
    assert SI.tick_value == pytest.approx(25.00)
    assert CL.tick_value == pytest.approx(10.00)


def test_every_micro_shares_its_full_size_root_tick_grid() -> None:
    """A micro is a smaller multiplier on the same prices, so only point_value moves."""
    for full, micro in [(NQ, MNQ), (ES, MES), (GC, MGC), (SI, SIL), (CL, MCL)]:
        assert micro.tick_size == full.tick_size
        assert micro.contract_months == full.contract_months
        assert micro.point_value < full.point_value


def test_micro_tick_values_match_the_published_contract_specs() -> None:
    assert MNQ.tick_value == pytest.approx(0.50)
    assert MES.tick_value == pytest.approx(1.25)
    assert MGC.tick_value == pytest.approx(1.00)
    assert SIL.tick_value == pytest.approx(5.00)
    assert MCL.tick_value == pytest.approx(1.00)


def test_a_micro_cannot_be_derived_from_its_full_size_root() -> None:
    """Silver breaks both halves of the obvious rule, so the registry stays explicit.

    A derived micro would be named MSI and priced at a tenth of SI. Both are wrong, and
    the price half is wrong by 2x in a project where every dollar figure routes here.
    """
    assert SIL.symbol != "MSI"
    assert SI.point_value / SIL.point_value == pytest.approx(5.0)
    for full, micro in [(NQ, MNQ), (ES, MES), (GC, MGC), (CL, MCL)]:
        assert full.point_value / micro.point_value == pytest.approx(10.0)


def test_a_root_may_carry_a_digit_and_the_registry_still_decides() -> None:
    """M2K used to fail the regex, which hid the real answer behind a parse error."""
    with pytest.raises(ValueError, match="unknown root 'M2K'"):
        ContractId.parse("M2K 03-26")


def test_price_decimals_follow_each_tick_grid() -> None:
    assert (GC.price_decimals, SI.price_decimals, CL.price_decimals) == (1, 3, 2)


def test_month_codes_round_trip_through_their_letters() -> None:
    assert months_from_codes("HMUZ") == frozenset({3, 6, 9, 12})
    assert months_from_codes("") == frozenset()
    with pytest.raises(ValueError, match="not futures month codes"):
        months_from_codes("HMUZY")


def test_contract_id_rejects_unparseable_names() -> None:
    with pytest.raises(ValueError, match="cannot parse"):
        ContractId.parse("MNQ-03-24")


def test_unknown_instrument_names_the_known_ones() -> None:
    with pytest.raises(KeyError, match="MNQ"):
        get_instrument("NG")
