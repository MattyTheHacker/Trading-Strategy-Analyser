---
title: "M63 — pre-registration: EmaPullback's one-bar confirmation entry through gate 4"
archetypes: [EmaPullback]
issues: [311]
gates: [4]
outcome: spec
verdict: >-
  Written and committed before the outputs were opened: gate 4 on EmaPullback's one-bar confirmation entry and its market-entry control, unfiltered, each root and bar size's selection-window top 20 re-run held out, at 2, 5, 10, 15 and 30 minutes. The confirmation passes at a bar size if on both roots the walk-forward pools above a profit factor of 1.0, the median configuration's bootstrap 5th percentile is above 1.0, and without its session-close legs the median configuration keeps a profit factor and a net-to-drawdown above 1.0. The verdict is read at 10 and 15 minutes, where it cleared §M39's paired bar on both roots.
---

# M63 — pre-registration: EmaPullback's one-bar confirmation entry through gate 4 ([#311])

Re-read on the October 2026 re-sweep, EmaPullback's one-bar confirmation entry now clears [§M39](m39-ema-pullback-confirmation-entry.md)'s pre-registered paired bar in five of eight cells, at 10 and 15 minutes on both roots and at 2 minutes on NQ, where §M39 had it clearing none. The minute bars inside its fill bars show that the gain does not rest on how NinjaTrader's path model reads that bar ([§M61](m61-registry-resweep-fill-fixes.md), § "§M39 — the confirmation entry, and the verdict reverses"). §M61 called it a candidate for a pre-registered test, not a strategy: its paired gain held out is one to five hundredths of profit factor, on an archetype whose median configuration loses held out. This is that test.

**What has changed since §M39**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: the fills. [#472] reads a stop entry's own bar along NinjaTrader's path, and the confirmation is a stop order where the market entry is not, so the fix moved one arm of the pair and not the other. The bars are the re-swept archive's.

**The reads have already run, and this file was written before any of their outputs were opened.** They ran on 20 October 2026, in the reads that followed the re-sweep, the same run that produced §M61's paired and gate-3 figures for this arm. Nobody has opened their gate-4 or prop tables. The cells, the bar and the predictions below were chosen without them. What was known when they were chosen is under § "What was already known".

## What is read

|               |                                                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**      | `stop=slow entry=confirm life=1`, the one-bar confirmation, and `stop=slow entry=market`, its control. `stop=slow entry=confirm life=3` is read and decides nothing |
| **Stratum**   | unfiltered                                                                                                                                                          |
| **Roots**     | MNQ and NQ, spliced continuous                                                                                                                                      |
| **Bar sizes** | 2, 5, 10, 15 and 30 minutes                                                                                                                                         |
| **Shortlist** | per root, bar size and arm, the selection window's top 20 by profit factor, re-run on the holdout                                                                   |
| **Costs**     | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                        |
| **Windows**   | selection on the first 60% of bars, holdout on the last 40%                                                                                                         |

One command per bar size for gate 4, and one for the prop replay:

```bash
uv run tools/campaign_gates.py --variants emapullback-confirm --strategies EmaPullback --resolutions 10 \
    --reads gates paired null gate4 --gate4-strata unfiltered --out <folder>
uv run tools/campaign_gates.py --variants emapullback-confirm --strategies EmaPullback --resolutions 10 \
    --reads prop --prop-strata unfiltered --out <folder>
```

## The bar

Gate 4's three reads, each passed as [§M47](m47-confluence-sizing-preregistration.md) defined it:

| read          | passes if                                                                                                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------- |
| walk-forward  | the pooled out-of-sample profit factor is above 1.0. Five sliding folds over the whole series, selection on train    |
| bootstrap     | the median configuration's 5th-percentile profit factor is above 1.0, over 1,000 resamples of its own trades         |
| the exclusion | with its session-close legs removed, the median configuration's profit factor and net-to-drawdown are both above 1.0 |

**The confirmation passes gate 4 at a bar size if it passes all three reads on both roots.** The verdict is read at 10 and 15 minutes, the two bar sizes where it cleared §M39's paired bar on both roots. So the family is two cells and a pass in either counts, named as one of two. 2, 5 and 30 minutes are read and reported, and decide nothing. At 2 minutes the paired bar cleared on NQ alone.

**The control is read the same way and is not a bar.** The confirmation earns its place over the market entry only where it passes and the control fails. A pass both arms make belongs to the archetype or its bracket, not to the entry.

**Two more reads are reported and decide nothing.** One is the permutation test's p for each configuration's drawdown against its own trades reordered, as §M42 read it. The other is the prop replay of each held-out shortlist through the 2026 linked presets, read against the control on pass rate and median net.

## What was already known

- **§M61's paired results for these two arms.** At 10 and 15 minutes the confirmation's held-out gain improves 64% to 80% of pairs. At 5 minutes it still costs held out, insignificantly. In gate 3, each arm clears p = 0.05 on both roots in one stratum, the market entry in `phase=LONDON` and the confirmation in `phase=CLOSE`.
- **§M61's minute-bar check**, which ran on the twenty confirmation configurations the *holdout* ranks first in each cell, at held-out profit factors of 1.03 to 1.90. Gate 4's shortlists rank on the selection window instead, so they are a different twenty.
- **§M61's §M28.12 read of EmaPullback's campaign variants**: their bracket is negative held out on 99% to 100% of configurations, so they carry their results on the forced flat. That read is of the campaign set, not this one.
- **§M35**: the median EmaPullback configuration loses held out.

## Predictions

Written so that they can be wrong.

- **The exclusion fails in every cell, for both arms.** The confirmation changes the entry, not the exit, and §M61 has EmaPullback's campaign variants earning their results on the forced flat.
- **The bootstrap fails in every cell, for both arms.** §M47 found it failing in every unfiltered cell of every archetype, controls included.
- **The walk-forward passes on both roots for the confirmation at 15 minutes**, where its paired gain is clearest. It fails on at least one root at 2 and 5 minutes for both arms.
- **So the confirmation does not pass gate 4** at any bar size, and the reason is the exclusion and the bootstrap, not the walk-forward.

## What this cannot settle

- **The holdout is not fresh.** §M39, §M61's paired read and its gate-3 read all used it, and the arm was named a candidate on it. A pass would be a pass on the window it was picked on. The walk-forward runs its own folds over the whole series and is the one read here that does not lean on that split.
- **`phase=CLOSE` is not read.** Gate 4 ran on the unfiltered stratum only, and `CLOSE` is the hour the forced flat closes, which the exclusion read would remove.

[#311]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/311
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/472
