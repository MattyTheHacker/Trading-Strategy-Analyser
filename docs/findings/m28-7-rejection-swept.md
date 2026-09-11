---
id: M28.7
title: "M28.7 — the rejection, swept: every profitable cell is one the fill assumption decides"
archetypes: [OpeningRange]
issues: [255]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  Profitability tracks the fill assumption and nothing else — every profitable cell in 245,760 is one the assumption decides, which is a stronger negative than the retest's no-verdict.
---

# M28.7 — the rejection, swept: every profitable cell is one the fill assumption decides ([#255])

§M28.6 built the fourth entry and recorded that nothing had been swept. This is the run. **The headline looks like the best result in the project's history and is not a result at all**: unfiltered, on the holdout, 79.9% of MNQ combinations and 84.4% of NQ combinations are profitable at 15-minute bars, with profit factors reaching infinity. What produces that number is `ambiguity_policy`, and this archetype is the sharpest instance of §M28.2's trap yet found — sharp enough to measure the trap itself rather than merely to be defeated by it.

## The grid, and why it is the fade's

245,760 combinations across 20 sweeps in 13.2 minutes, both roots, five ranges, selection and held-out windows, at the real commission for the root and one tick of slippage. Re-derivable from `results/campaign/OpeningRange.duckdb` under the variant names `<range> entry=rejection target=<scheme>`, and a measurement of one dated run.

**Every bracket axis is held at exactly what §M28.5 swept** — `stop_range_fraction` over `ORB_TIGHT_FRACTIONS`, `stop_offset_ticks` crossed at `[2, 8]`, and the same three target schemes including the midpoint ladder. The entry axis is the only thing that moved: `entry_offset_ticks` over `[0, 1, 4, 8]` replaces the fade's `[1, 4]` crossed with `break_confirm_ticks`, which the rejection does not read. The two grids are therefore the same size, which is what lets the two entries be compared as entries rather than as two unrelated runs. Strata stated in advance and shared with the fade: `unfiltered` and `regime=CONSOLIDATING`, split per lookback by `--regime-quantiles`.

`entry_offset_ticks=0` is in the axis because it is the one value that is not the setup: a limit resting on the extreme needs price to trade **through** it under `IsFillLimitOnTouch = false`, which is the break the mode exists to do without.

## Gate 1 — profitability tracks the fill assumption and nothing else

Unfiltered, holdout, both roots, binned on `ambiguous_share`:

| ambiguous_share | n (MNQ) | median PF | profitable | n (NQ) | median PF | profitable |
| --------------- | ------- | --------- | ---------- | ------ | --------- | ---------- |
| < 0.05          | 4,011   | 0.846     | 0.177      | 4,036  | 0.897     | 0.272      |
| 0.05 – 0.15     | 1,821   | 1.053     | 0.582      | 1,803  | 1.132     | 0.730      |
| 0.15 – 0.30     | 1,263   | 1.457     | 0.931      | 1,266  | 1.589     | 0.953      |
| 0.30 – 0.50     | 1,073   | 2.537     | **1.000**  | 1,076  | 2.866     | **1.000**  |
| ≥ 0.50          | 2,072   | 10.395    | **1.000**  | 2,059  | 11.987    | **1.000**  |

**Every configuration whose fill assumption decides three legs in ten is profitable, on both roots, without exception.** Below `disambiguate.MIN_AMBIGUOUS_SHARE` — the threshold the project already uses to mean "the assumption could not have decided this" — the median profit factor is 0.846 and 0.897 and the best reached is 1.386 and 1.514.

**The bar-size gradient is the assumption in disguise, and controlling for it removes the gradient entirely.** Raw, the profitable share climbs 0.416 → 0.469 → 0.629 → 0.695 → 0.794 across 1/2/5/10/15-minute bars on MNQ, exactly as mean `ambiguous_share` climbs 0.131 → 0.147 → 0.268 → 0.285 → 0.355. Among readable rows only, the median profit factor is 0.844, 0.835, 0.855, 0.860, 0.858 — flat, and below 1.0 at every resolution on both roots. `CONTRIBUTING.md`'s "always before believing a coarse resolution" is the rule that catches this, and here it is the whole finding.

The target scheme tells the same story from another side, because an R target scales with the stop: at `stop_range_fraction=0.02` the R ladder puts both bracket levels within a couple of points and reaches an `ambiguous_share` of 0.702, where the width ladder stays at 0.029. Profitable share at that fraction, unfiltered holdout, MNQ / NQ: `R` 1.000 / 1.000 against `width` 0.219 / 0.270.

## The spread, and the minute bars cannot narrow it

`tools/campaign_ambiguity.py` over the top twenty of `cash=30m entry=rejection target=R`, ranked on the holdout: **0 of 20 keep a profit factor above 1.00 under the other policy.** The widest runs 105.919 → 0.107 on an `ambiguous_share` of 0.959.

§M28.4's minute-bar pass, which settled the retest, cannot settle this: every leg comes back `still_ambiguous`, because at these fractions the whole bracket is narrower than a one-minute bar. **A bracket smaller than the finest bar in the archive is not a measurement the archive can make**, whichever policy is chosen, and no further data this project holds would change it.

## Why the rejection wins where the fade loses, measured rather than argued

The two entries share a bracket, a set of ranges and a set of resolutions, and their results are mirror images. Median profit factor, unfiltered holdout, R targets, MNQ:

| `stop_range_fraction` | fade `amb` | fade PF | rejection `amb` | rejection PF | geometric mean |
| --------------------- | ---------- | ------- | --------------- | ------------ | -------------- |
| 0.02                  | 0.569      | 0.057   | 0.705           | 10.738       | 0.779          |
| 0.05                  | 0.384      | 0.142   | 0.512           | 4.475        | 0.798          |
| 0.10                  | 0.218      | 0.274   | 0.305           | 2.020        | 0.744          |
| 0.25                  | 0.063      | 0.581   | 0.087           | 1.086        | 0.794          |

**Both are monotone in ambiguity and they run in opposite directions.** The individual figures span a factor of 235; the geometric mean of each pair moves only between 0.744 and 0.798 on MNQ, and between 0.800 and 0.931 on NQ — and that constant is the same number the readable rows report independently, 0.846 and 0.897. Two routes to one answer, and it is below 1.0.

The reason is which side of the bar each entry fills on, and it is a measurement rather than a reading. One configuration, 60,000 MNQ bars at 15 minutes, `stop_range_fraction=0.02`, both entries at an `ambiguous_share` near 0.9, run under all three policies:

| entry     | worst case | nearest to open (NT8) | best case | win rate under NT8's rule |
| --------- | ---------- | --------------------- | --------- | ------------------------- |
| fade      | 0.012      | **0.016**             | 2.171     | 0.013                     |
| rejection | 0.274      | **57.953**            | 71.654    | 0.986                     |

**Neither lands in the middle of its band; each lands on an opposite end of it.** A fade's stop entry fills as price comes back *up* through the level, so the bar's open sits below the fill and nearer the stop, and the nearest-to-open rule books the stop on almost every ambiguous bar. A rejection's limit fills as price comes *down* to it, so the open sits above the fill and nearer the target, and the same rule books the target. `docs/nt8-fidelity.md`, "The seven bars above contain no same-bar limit entry", is the rule this exercises, and this run says the sign of its error is set by the entry mechanism.

## Gates 2 and 3, on the rows that can be read

The raw shortlist passes gate 2 in 146 of 180 variant × root × stratum cells, which is the trap rather than a result — a shortlist ranked on profit factor selects for `ambiguous_share`, exactly as §M28.2 predicted it would on the next archetype. Confined to rows readable on the selection window, 46 of 180 cells clear 1.0 and the best reaches 1.325; the `london=60m` pass that looked strongest raw, at held-out 1.642 and 1.845, falls to 0.980 and 1.024.

The one cell whose whole variant is readable is `overnight entry=rejection target=width`, at an `ambiguous_share` of 0.003 to 0.014. Its population fails gate 1 — median profit factor 0.808 to 0.939 across every root, direction and resolution, with 5% to 31% profitable — and its top twenty, chosen on the selection window, hold out at 1.01 to 1.09. Gate 3 on those twenty against `matched_random_ranges`, the null a level-based trigger needs: the profit-factor excess is **+0.069 to +0.131, consistent in sign across all twenty, at p = 0.35 to 0.68**. Nothing approaches significance, and the shortlist it is measured on came from a population whose median loses money.

## The verdict, and what §M28.5 predicted

**The rejection fails gate 1 wherever the number can be read, and every profitable cell in 245,760 is one where the fill assumption decides the trade.** That is a stronger statement than the retest's "no verdict" at §M28.2, because there the readable region was too small to answer anything; here it is 8,047 of 20,480 unfiltered rows and it answers gate 1 on both roots.

§M28.5 predicted this mode would "behave differently rather than merely be untested", on the grounds that a limit fills as price comes to it where a stop fills after price has already traded through. **That is confirmed, and the difference is not the one the prediction hoped for**: the rejection's exposure to the entry bar is not smaller than the fade's, it is inverted. The fade's floor was the entry bar's adverse excursion exceeding a tight stop; the rejection's ceiling is the entry bar's favourable extreme reaching a near target under a rule that measures from the open. Both are the same bar deciding the trade.

**Parked, with a reason** — § "Parked is not abandoned". What would justify a re-run is not a different bracket, a different stratum or a different range: it is **an NT8 trade list containing a same-bar limit entry**, which would say which end of the band NT8 actually sits on and would settle the fade, the retest and the rejection together. That is the probe `docs/nt8-fidelity.md` §M28.2 already wants for the marketable limit, and this run raises what it is worth rather than adding a new one.

[#255]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/255
