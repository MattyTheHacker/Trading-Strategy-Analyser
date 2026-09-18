"""Running one root's shortlist on another root.

The selection half is what the tool exists to get right -- a ranking floor that admits
small-sample noise makes every number downstream meaningless -- so it is pinned without a
database. The running half is checked for the two things that would silently corrupt a
result: the target root's costs, and its own instrument.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nqbt import disambiguate
from tools import campaign_crossroot
from tools.campaign_crossroot import COMMISSION, PAIRS, selected, summarise


def stored(n: int = 40) -> pd.DataFrame:
    """Stored rows spanning both roots, two variants and a wide range of trade counts."""
    rng = np.random.default_rng(3)

    return pd.DataFrame(
        {
            "root": ["NQ"] * n + ["MNQ"] * n,
            "variant": (["bracket", "bracket hold=20"] * n),
            "trades": np.tile(np.linspace(30, 1200, n).astype(int), 2),
            "profit_factor": rng.uniform(0.5, 3.0, 2 * n),
            "resolution": 5,
            "stratum": "unfiltered",
            "ambiguous_share": 0.01,
        },
    )


@pytest.fixture
def loaded(monkeypatch):
    frame = stored()
    monkeypatch.setattr(campaign_crossroot, "load", lambda name, windows: frame)

    return frame


def test_the_trade_floor_drops_every_row_below_it(loaded) -> None:
    """The defect the floor exists for: ranked at the campaign's own 30, two thirds of a
    top-200 holds under 50 trades and the profit factor being ranked is small-sample noise."""
    picked = selected("InsideBar", "NQ", top=200, min_trades=500)

    assert len(picked) > 0
    assert picked["trades"].min() >= 500


def test_an_infinite_profit_factor_is_dropped_rather_than_ranked_first(loaded) -> None:
    """Nine stored OpeningRange rows have no losing trade at all, so they sort above every
    real configuration and would take the top of any shortlist."""
    loaded.loc[loaded.index[0], ["trades", "profit_factor"]] = [900, np.inf]

    picked = selected("InsideBar", "NQ", top=200, min_trades=500)

    assert np.isfinite(picked["profit_factor"]).all()


def test_a_row_its_fill_assumption_decided_is_dropped_before_ranking(loaded) -> None:
    """OpeningRange's entry=rejection rows store a profit factor of 3,955 on 613 trades with
    one loser, an ambiguous_share of 0.89 and trades held under a bar. §M28.7 measured that
    family: 0 of 20 keep a profit factor above 1.00 under the other policy. Ranked on profit
    factor alone they take the whole shortlist."""
    loaded.loc[loaded.index[0], ["trades", "profit_factor", "ambiguous_share"]] = [900, 3955.0, 0.89]

    picked = selected("InsideBar", "NQ", top=200, min_trades=500)

    assert (picked["ambiguous_share"] <= disambiguate.MIN_AMBIGUOUS_SHARE).all()
    assert 3955.0 not in set(picked["profit_factor"])


def test_a_variant_swept_into_a_stratum_is_excluded(loaded) -> None:
    """A hold= arm is a later variant set swept into the same database, so a top-N drawn over
    it mixes the campaign grid with six hold arms -- docs/roadmap.md, "Standing traps"."""
    picked = selected("InsideBar", "NQ", top=200, min_trades=500)

    assert not picked["variant"].str.contains("hold=").any()


def test_only_the_named_source_roots_rows_are_selected(loaded) -> None:
    picked = selected("InsideBar", "MNQ", top=200, min_trades=500)

    assert set(picked["root"]) == {"MNQ"}


def test_a_source_root_with_nothing_above_the_floor_raises(loaded) -> None:
    """Returning an empty shortlist would report a target root as untested rather than
    untestable, and the difference matters."""
    with pytest.raises(RuntimeError, match="no stored row clears"):
        selected("InsideBar", "NQ", top=200, min_trades=10_000)


def test_each_pair_matches_its_size_class_on_commission() -> None:
    """Pairing a micro shortlist onto a full-size root would change the market and the cost
    structure at once, and the result could not be attributed to either."""
    for source_root, targets in PAIRS.items():
        for target in targets:
            assert COMMISSION[target] == COMMISSION[source_root], (source_root, target)


def test_every_paired_root_is_a_registered_instrument() -> None:
    from nqbt.instruments import get_instrument

    for source_root, targets in PAIRS.items():
        assert get_instrument(source_root).symbol == source_root
        for target in targets:
            assert get_instrument(target).symbol == target


def test_the_summary_reports_a_distribution_and_never_a_ranking() -> None:
    """Picking the best performer on the target root would re-introduce the selection bias
    one level up, so the tool reports spread and never sorts by it."""
    rows = pd.DataFrame(
        {
            "strategy": ["InsideBar"] * 4,
            "target_root": ["ES"] * 4,
            "source_pf": [1.8, 1.7, 1.6, 1.5],
            "target_pf": [1.4, 1.1, 0.9, 0.6],
            "target_trades": [900, 800, 700, 600],
            "target_session_close_share": [0.1, 0.1, 0.2, 0.2],
            "target_ambiguous_share": [0.01, 0.02, 0.01, 0.03],
        },
    )

    out = summarise(rows)

    assert out.loc[0, "n"] == 4
    assert out.loc[0, "target_pf_median"] == pytest.approx(1.0)
    assert out.loc[0, "share_above_1"] == pytest.approx(0.5)
    assert "best" not in "".join(out.columns)
