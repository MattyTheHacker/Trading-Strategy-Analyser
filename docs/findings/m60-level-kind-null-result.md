---
id: M60
title: "M60 — OpeningRange beats a random bracket of its own range's width on sign everywhere and family-wise nowhere, and the width is a fifth to three tenths of its excess over another session's range"
archetypes: [OpeningRange]
issues: [439]
gates: [3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 re-sweep, and every prediction held: against a null that keeps each session's range width and places the bracket at random around its price, all 60 shortlisted configurations beat their null's median, by +0.10 to +0.17 of held-out profit factor, and none reaches a family-wise p below 0.05 — the smallest is 0.057, on MNQ at 5 minutes — so no bar size clears; the kind null sits above §M28.2's level null in every configuration, and beside it the level null is cleared family-wise on both roots at 15 minutes alone, NQ at 0.0499.
---

# M60 — OpeningRange beats a random bracket of its own range's width on sign everywhere and family-wise nowhere, and the width is a fifth to three tenths of its excess over another session's range ([#439])

Pre-registered in [`m60-level-kind-null-preregistration.md`](m60-level-kind-null-preregistration.md) before the run, and read here by that file's own rules, on the rows of the October 2026 re-sweep. It is the null [§M28.2](m28-2-deferral-list.md) deferred: one over the level's kind rather than its identity.

## In plain terms

OpeningRange trades a break of the range the market made in its first minutes. Earlier tests compared it with trading another day's range instead. This one compares it with a bracket exactly as wide as today's range but placed at random around today's price, so the only thing missing is where the market actually turned.

**The real range does better than the random bracket on every setting tested, but not by enough to pass the strict test.** When the test allows for the 60 settings tried at once, none clears. Against another day's range, the comparison made before, the 15-minute version does just clear. Most of the edge over another day's range comes from where today's range sits, not from how wide it is.

## What was run

|                 |                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| **Archetype**   | OpeningRange's own campaign variants, §M28.1's grid, every range window stored at each bar size            |
| **Stratum**     | `unfiltered` alone                                                                                         |
| **Resolutions** | 5, 10 and 15 minutes                                                                                       |
| **Roots**       | MNQ and NQ                                                                                                 |
| **Shortlist**   | the top ten per root and bar size by selection-window profit factor, tested on the holdout                 |
| **Draws**       | 400 per configuration under `kinds`, the new null, and again under `levels`, §M28.2's, from seed 0 in both |
| **Family**      | 60 tests per draw: 2 roots × 3 bar sizes × 10 configurations                                               |

**Every configuration reproduced its stored holdout row**, trades and net P&L, before any draw, and none was refused. Each configuration holds 420 to 480 held-out trades.

## The kind null: no bar size clears

**A bar size clears where, on each root, at least one of its ten configurations reaches a family-wise p below 0.05.** Each cell's median configuration, and its smallest family-wise p:

| root | bars | profit factor | kind null | excess | per-test p ≤ 0.05 | smallest family-wise p |
| ---- | ---- | ------------- | --------- | ------ | ----------------- | ---------------------- |
| MNQ  | 5    | 1.110         | 0.965     | +0.141 | 4 of 10           | 0.057                  |
| MNQ  | 10   | 1.101         | 0.967     | +0.139 | 3 of 10           | 0.085                  |
| MNQ  | 15   | 1.090         | 0.955     | +0.142 | 3 of 10           | 0.070                  |
| NQ   | 5    | 1.092         | 0.961     | +0.123 | 0 of 10           | 0.112                  |
| NQ   | 10   | 1.095         | 0.974     | +0.128 | 1 of 10           | 0.120                  |
| NQ   | 15   | 1.078         | 0.951     | +0.124 | 1 of 10           | 0.110                  |

**Every one of the 60 configurations beats its kind null's median**, by +0.10 to +0.17, and 12 reach a per-test p of 0.05. None reaches a family-wise p below 0.05, on either root, at any bar size. MNQ comes closest, at 0.057 at 5 minutes. NQ's best is 0.110.

## Beside it, the level null

The same shortlist and seeds under §M28.2's draw, which trades another session's range:

| root | bars | level null | excess | per-test p ≤ 0.05 | smallest family-wise p |
| ---- | ---- | ---------- | ------ | ----------------- | ---------------------- |
| MNQ  | 5    | 0.936      | +0.176 | 3 of 10           | 0.057                  |
| MNQ  | 10   | 0.920      | +0.181 | 7 of 10           | 0.052                  |
| MNQ  | 15   | 0.895      | +0.195 | 8 of 10           | 0.015                  |
| NQ   | 5    | 0.936      | +0.154 | 0 of 10           | 0.137                  |
| NQ   | 10   | 0.923      | +0.175 | 2 of 10           | 0.070                  |
| NQ   | 15   | 0.895      | +0.176 | 3 of 10           | 0.0499                 |

**At 15 minutes the level null is cleared family-wise on both roots**, NQ by a hair. At 5 and 10 minutes it is not.

**The kind null makes more than the level null in all 60 configurations**, because it keeps the session's own width. The excess over the kind null is 70% to 80% of the excess over the level null in every cell. So a fifth to three tenths of what the real range earns over another session's range is its width, and the rest is where its edges sit.

**Read by the pre-registration's table:**

- **At 15 minutes the shortlist beats the level null and not the kind null**, the row the table reads as "the session's width, not its edges".
- **At 5 and 10 minutes it beats neither family-wise**, the row read as "neither the range nor its width separates the trade from the bracket and the time of day".

Both readings are family-wise, and they are about what clears, not about size. By size the width is the smaller part of the excess. What it does at 15 minutes is narrow the gap enough that a family of 60 can no longer call it: MNQ goes from 0.015 to 0.070 and NQ from 0.0499 to 0.110. One test at a time, every configuration beats both nulls on sign.

## The predictions

- **"The kind null makes more than the level null, its median profit factor above the level null's in at least five of the six cells." Right**, in all six, and in all 60 configurations.
- **"The observation still beats the kind null on sign, the excess positive in the median configuration of at least five of the six cells." Right**, in all six, and in all 60 configurations.
- **"No bar size clears the kind null at the bar." Right.**

## What this settles, and what it does not

**It settles the level's kind as not proven.** A random bracket as wide as the session's own range, around the same price at the same time, comes within 0.10 to 0.17 of the real range. With 60 tests, that gap is not large enough to call. The real range's edges are worth something on every configuration, and not enough on any to clear a family-wise bar.

**It does not overturn OpeningRange's earlier gate-3 passes**, which were read one test at a time: in strata against a random entry, and unfiltered against the level null. It says the unfiltered breakout's advantage over a random bracket of the same width is real in sign and not yet in strength.

## How it was read

- **Draws.** `campaign_null.py --strategy OpeningRange --root MNQ NQ --stratum unfiltered --campaign-only --resolution <5|10|15> --window selection --test-window holdout --top 10 --iterations 400 --draw <kinds|levels>`, once per bar size and draw.
- **Family.** `campaign_null.py --family-of` over each draw's three tables, and the same family-wise p computed to four places from those tables.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
