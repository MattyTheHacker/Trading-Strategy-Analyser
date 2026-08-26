"""Pinned draws from ``numpy.random``, so a changed stream is a finding rather than a mystery.

NEP 19 permits ``Generator``'s stream to move between numpy releases. Nothing else in the suite
would notice: every p-value assertion states a property (``> 0.05``), never a draw, so a numpy
bump could shift every stored p-value and the random-entry benchmark while CI stayed green.

One call shape per site that draws in anger -- ``nqbt/guard.py``, ``nqbt/montecarlo.py``,
``nqbt/dispersion.py`` and ``nqbt/randomentry.py`` -- plus the shapes the test fixtures build
their bars from, because a change there moves dozens of unrelated tests at once.

**A failure here is not a defect to fix by re-pinning.** It says the null distributions and the
matched random-entry arm have moved, and what depends on them has to be re-measured --
``docs/roadmap.md`` § "What CI can gate on a dependency bump".
"""

import numpy as np

PNL = np.arange(10, dtype=np.float64) - 4.5
"""Stands in for a per-trade P&L vector: ten distinct values, both signs, no zero."""


# -- the draws the statistics rest on ------------------------------------------


def test_permutation_of_a_float_vector_is_unchanged() -> None:
    """``guard.permutation_test``, ``montecarlo.permutation_test`` and ``dispersion``."""
    rng = np.random.default_rng(0)
    assert rng.permutation(PNL).tolist() == [-0.5, 1.5, -2.5, 2.5, -1.5, 0.5, 4.5, -4.5, 3.5, -3.5]


def test_permutation_of_an_integer_range_is_unchanged() -> None:
    rng = np.random.default_rng(0)
    assert rng.permutation(np.arange(12)).tolist() == [9, 2, 7, 4, 5, 11, 0, 3, 6, 10, 8, 1]


def test_bootstrap_choice_with_replacement_is_unchanged() -> None:
    """``montecarlo.bootstrap``, which resamples the P&L vector to its own length."""
    rng = np.random.default_rng(0)
    drawn = rng.choice(PNL, size=PNL.size, replace=True)
    assert drawn.tolist() == [3.5, 1.5, 0.5, -2.5, -1.5, -4.5, -4.5, -4.5, -3.5, 3.5]


def test_choice_without_replacement_is_unchanged() -> None:
    """``randomentry.matched_random_signal``, which draws entry bars from a minute's pool."""
    rng = np.random.default_rng(0)
    assert rng.choice(np.arange(20), size=6, replace=False).tolist() == [4, 10, 8, 5, 0, 12]


def test_the_per_draw_seeds_are_unchanged() -> None:
    """``randomentry.null_summaries`` seeds every iteration from one ``SeedSequence``."""
    seeds = np.random.SeedSequence(0).generate_state(6)
    assert seeds.tolist() == [2968811710, 3677149159, 745650761, 2884920346, 2642120001, 549907821]


# -- the draws the fixtures rest on --------------------------------------------


def test_normal_draws_are_unchanged() -> None:
    rng = np.random.default_rng(3)
    assert rng.normal(0, 1.0, 5).tolist() == [
        2.0409191213851825,
        -2.5556650313141818,
        0.41809884672577885,
        -0.5677696061279298,
        -0.45264929211044586,
    ]


def test_integer_draws_are_unchanged() -> None:
    rng = np.random.default_rng(3)
    assert rng.integers(1, 500, 8).tolist() == [405, 43, 90, 119, 91, 400, 434, 291]


def test_uniform_draws_are_unchanged() -> None:
    rng = np.random.default_rng(3)
    assert rng.random(5).tolist() == [
        0.08564916714362436,
        0.2368105065960997,
        0.8012744652063969,
        0.5821620360643678,
        0.09412864224039919,
    ]


# -- the pins have to mean something -------------------------------------------


def test_the_same_seed_gives_the_same_draw_twice() -> None:
    """Without this the pins above could be passing on an accident of call order."""
    first = np.random.default_rng(0).permutation(PNL)
    second = np.random.default_rng(0).permutation(PNL)
    assert np.array_equal(first, second)


def test_a_different_seed_gives_a_different_draw() -> None:
    """A pin that any seed satisfies would be checking nothing."""
    assert not np.array_equal(
        np.random.default_rng(0).permutation(PNL),
        np.random.default_rng(1).permutation(PNL),
    )
