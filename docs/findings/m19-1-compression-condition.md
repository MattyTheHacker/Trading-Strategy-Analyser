---
id: M19.1
title: "M19.1 — compression as a condition, before it is an archetype"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [51]
gates: [1, 2]
outcome: negative
verdict: >-
  The condition is real and consistently ordered across seven archetypes and two roots, and it still separates no better than four dimensions the campaign already had — a reason to keep M19 parked rather than to build it.
---

# M19.1 — compression as a condition, before it is an archetype ([#51])

M19 opens by saying "squeeze" means at least three things and that fixing the definition comes first. This fixes it in the cheapest place: **compression is a property of the bars, so it is a context filter and not a strategy.** `nqbt/compression.py` is the sixth filter beside phase, regime, volume, trend and the higher-timeframe side, which means every registered archetype can be stratified by it for the price of one module — and the question M19 exists to answer, *does compression-then-break pay*, can be asked of `InsideBar` and `OpeningRange`, both of which already implement a break of a range, before anything new is built.

`Trading-Docs/trading_concepts.md` § 3.2 puts "Bollinger bandwidth, or rolling high−low range ÷ ATR" in the same table of codeable classifiers that [#40] built `regime.py` from. Bandwidth is the sibling entry to the efficiency ratio, not a strategy of its own, and this treats it that way.

## Two forms, because a narrow band is not a short range

`CompressionForm.BANDWIDTH` is `2σ / basis`, taken off `bands.BandGrid`'s two rows rather than a second Bollinger of its own — §M26's "build that grid once, because M19 reads it too", honoured. `CompressionForm.RANGE_TO_ATR` is the window's high−low range over an ATR of the same length, which reads near 1 for a window that went nowhere and near the lookback for one that trended. One period axis serves both, so unlike the volume axes **neither form leaves an axis inert** — the blind spot `dead_axes` cannot see is avoided rather than rediscovered.

The Bollinger multiple is a constant, not an axis. It scales every bar alike, so it cannot move an ordering, a rank or a fitted quantile; sweeping it would run identical combinations.

## The rank is the design, and it is what the two siblings do not have

Neither raw width has a unit. Measured over both roots, three resolutions, both forms and three periods — 36 cells — **the raw width's median spans 0.00045 to 7.61, a factor of about 17,000.** A raw threshold on it is a different cut in every cell, which is exactly the failure §M27.5 records for the efficiency ratio (0.5 is the 59th percentile at a lookback of 5 and the 99.6th at 50) and §M27.8 for relative volume (0.7/1.5 admits 28% of bars under `PER_BAR` and 8% under `ROLLING`).

So the filter cuts a **trailing percentile rank** rather than the width: where this bar's width sits among the `baseline_bars` widths *strictly before* it. That is the device `volume.py` already uses when it divides by a trailing median, and #51 names it outright — "below a trailing percentile".

**Across the same 36 cells, a raw cut at 0.25 admits between 0.2524 and 0.2970 of the measured bars.** The worst cell is under five points off nominal and most are within two. That is a comparability neither sibling achieves, and it is why this dimension ships without a `--compression-quantiles` calibration pass: `CompressionGrid.thresholds_for` exists for a stratification that needs one, and the campaign's first pass does not. The residual drift is the shape it should be — larger for `BANDWIDTH` than for `RANGE_TO_ATR`, larger at long periods and short resolutions — because width is autocorrelated and the ranks bunch at both ends.

## The lookahead trap, closed by construction and pinned by a test

§M19 calls lookahead "the second-easiest place in the project to manufacture a fictional edge", and a compression measure that reads the breakout bar's own range trivially predicts the breakout. Two things stand against it. A bar's width is computed from bars up to and including itself and its rank against bars strictly before it, so the series is causal at every step; and the filter is ANDed into the *signal*, which the simulator tests against the **next** bar's OHLC, exactly as every other context filter is. `tests/test_compression.py::test_no_bar_contributes_to_its_own_rank` pins it by truncation — every rank taken over a prefix must equal the rank the whole series gives that bar — and the test beside it checks that a window reaching one bar forward breaks the gate, because verifying the gate can fail is part of using it.

## What this count is not, and what would settle it

**It is not the squeeze archetype**, and it does not answer M19. It supplies the condition and the stratification; the entry model M19 describes — a two-sided break of the compression range — is still unbuilt, and §M28's expressibility finding 1 still stands against the two-sided half of it. What it does is let the campaign ask whether compression is worth an archetype before one is written, which is the order §M28 and §M28.1 established for the opening range and the order the standing rubric asks for.

**The prediction written here before the sweep was wrong, and it is left recorded rather than quietly replaced.** It read: §M27 has `InsideBar` separating in the **DIRECTIONAL** regime stratum, so a squeeze thesis predicts the opposite and `compression=COMPRESSED` should be the losing half. Held out, COMPRESSED is consistently the *winning* half of the three. What the prediction got right is that the full window would say otherwise — see below, where it does, for a reason that turns out to be the clock.

## The campaign — 92,352 full-window and 188,160 held-out combinations

Every registered archetype, both roots, resolutions 1/2/5/10/15, at the real commission for the root and one tick of slippage. `--strata compression` full window, then `--split`, then `--strata compression-forms --split` on the two archetypes that already implement a break of a range. Every figure below is re-derivable from `results/campaign/*.duckdb`; it is a measurement of one dated run rather than a standing property.

**The full window and the holdout disagree, and the full window is the one that is wrong.** On the full window `compression=EXPANDED` looks strongest on `InsideBar` — 99.2% of configurations profitable at 5 minutes against an unfiltered 87.0%. Held out it has the worst decay of the three states. Pooled over seven archetypes and both roots, 42 cells:

| state          | cells passing | clears drawdown | decay     | rank corr | holdout PF |
| -------------- | ------------- | --------------- | --------- | --------- | ---------- |
| **COMPRESSED** | **71.4%**     | **42.9%**       | 0.339     | 0.413     | **1.253**  |
| NORMAL         | 57.1%         | 21.4%           | **0.265** | **0.460** | 1.024      |
| EXPANDED       | 28.6%         | 7.1%            | 0.518     | 0.220     | 0.905      |

**What EXPANDED was being credited with is the clock, and `session_close_share` says so directly.** On the holdout its median runs 0.141, 0.232 and 0.297 at 5, 10 and 15 minutes against COMPRESSED's flat 0.021, 0.032 and 0.048. Wide bars mean long holds, so the stratum that looked like the finding is the stratum most of whose legs leave at the force-flat point rather than at a bracket level — §M27.7's contamination, arriving on the cell most likely to be believed. This is the third time reading `session_close_share` before the profit factor has changed a conclusion.

**The dimension is mid-pack, and that is the headline rather than the state ordering.** Under the strict verdict — the shortlist profitable on *both* windows, beating the stratum's own holdout median, and clearing drawdown — compression passes 19.0% of its cells against trend's 27.5%, the higher-timeframe side's 21.4%, regime's 19.0%, volume's 18.8% and phase's 13.3%. Its decay of 0.374 and rank correlation of 0.365 sit inside the 0.33–0.49 and 0.22–0.46 band §M27.4 measured for every dimension there, and nowhere near §M28.1's 0.221 and 0.69. **Eight of 42 cells survive strictly and no COMPRESSED cell survives on both roots.** Two of the eight are worth naming for the reason they should not be trusted: `DeadCatBounce` MNQ COMPRESSED passes off a selection window that *lost* money, 0.826 to 1.347, which is noise reversing rather than selection working; and `PullBackAndGo` MNQ COMPRESSED rises out of sample at a rank correlation of 0.214, the shape §M27.4 recorded as unexplained for `InsideBar phase=LONDON`.

## The two forms are not the same condition, and this is what the recut was for

`--strata compression-forms` crossed both forms on `InsideBar` and `OpeningRange`. Across the twelve matched cells the two forms' holdout profit factors correlate at **0.133** — they agree on the pass/fail verdict in 9 of 12 and on almost nothing else.

The sharpest disagreement is root-consistent and therefore not noise: `InsideBar` COMPRESSED reads 1.238 and 1.196 under bandwidth and **0.709 and 0.669** under range-to-ATR, passing on both roots under one form and failing on both under the other. `OpeningRange` COMPRESSED splits the other way — 1.855 and 1.713 under range-to-ATR against 1.150 and 1.302 under bandwidth.

**A narrow band and a short range are different statements about the same bars, and which one an archetype answers to is a fact about the archetype.** That is §M28's lesson — the variety is the product of independent choices rather than a list of strategies — arriving inside the condition, and it is why the form is a swept axis rather than a decision made once in `SetDefaults`. It also means a result quoted for "compression" without naming the form is not quoting a measurement.

Bandwidth is the better-behaved half on this evidence: decay 0.163 and rank correlation 0.501 against range-to-ATR's 0.248 and 0.376. **Twelve cells over two archetypes is not enough to promote it**, and the figure is quoted here as the reason to cross the form rather than as a finding about it.

## What this changes for M19

**It is a reason to keep the archetype parked, not to build it.** The condition is real, its state ordering is consistent across seven archetypes and two roots, and it still does not separate better than four dimensions the campaign already had. §M27's standing lesson applies unchanged: a dimension that ranks mid-pack does not become an archetype because it is the one that was just built. What would change the answer is a form-specific re-cut that clears the strict verdict on both roots — which bandwidth is closest to and has not done.

## The stratum, and how a campaign asks for it

`--strata compression` is the dimension (one cell per state, at `compression_period = 20` and `compression_baseline_bars = 250`, both `sim/types.py` defaults) and joins `--strata context` and `--strata all`. `--strata compression-forms` is the recut that crosses both forms, and sits in `RECUTS` beside `volume-forms` so that `all` does not run the dimension twice under two sets of names.

Adding the fields moved no number: the trade-log gate reports every pre-existing column identical across all fourteen files, with the six new parameter columns declared. That is the property `ALL_STATES` buys — the conjunction is skipped entirely at the default, so an unfiltered run is the run that predates the fields.

[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#51]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/51
