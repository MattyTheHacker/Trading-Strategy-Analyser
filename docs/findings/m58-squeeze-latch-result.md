---
id: M58
title: "M58 — the latched squeeze beats the unlatched rule at 2 and 5 minutes without making it profitable, and two thin cells pass gate 3 one test at a time"
archetypes: [SqueezeBreakout]
issues: [51, 439]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Pre-registered and run on the October 2026 re-sweep: the control reproduces exactly in every stratum; every latch trades less than the control in all sixteen cells, the shorter the fewer; 5 of 12 length and bar-size cells clear §M37's paired bar against a prediction of none, all at 2 and 5 minutes, by +0.005 to +0.057 of profit factor with the median configuration still losing; no latched arm beats its null unfiltered, and two thin cells pass §M19.3's gate-3 bar on both roots — 6 closes in trend=MIXED at 10 minutes and 12 in compression=EXPANDED at 2, on 28 to 49 held-out trades — neither of which clears family-wise on both roots.
---

# M58 — the latched squeeze beats the unlatched rule at 2 and 5 minutes without making it profitable, and two thin cells pass gate 3 one test at a time ([#439])

Pre-registered in [`m58-squeeze-latch-preregistration.md`](m58-squeeze-latch-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. It runs the reading of a squeeze [§M19.2](m19-2-squeeze-breakout-spec.md) deferred: wait for the squeeze to end, then trade a break of the range it ended with. [§M19.3](m19-3-squeeze-breakout-swept.md) swept the other reading and found the squeeze added nothing measurable.

## In plain terms

SqueezeBreakout waits for the market to go quiet, then buys a break above the quiet range or sells a break below it. Until now it placed that order while the market was still quiet. This run waited until the quiet spell ended, then placed the order at the edge of the range it ended with, for the next 3, 6 or 12 bars.

**Waiting helps a little on short bars.** At 2 and 5 minutes the waiting versions do slightly better than the original on both contracts, in both the earlier and the later data. At 10 and 15 minutes they do not.

**But it is a losing strategy made to lose less.** The typical setting still loses money with or without the wait. Against random entries, two narrow slices pass one test at a time, each on a few dozen trades. When the test allows for how many slices were tried, neither passes on both contracts.

## What was run

|                 |                                                                                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | `latch=off`, §M19.3's entry as the control, and a latch of 3, 6 or 12 bar closes from the window frozen at the last squeezed bar |
| **Grid**        | §M19.3's 1,728 combinations in every arm, across its four stop × target variants                                                 |
| **Strata**      | all 23, one context dimension at a time; 22 hold rows                                                                            |
| **Resolutions** | 2, 5, 10 and 15 minutes as pre-registered; 30 minutes was swept since and is shown beside them, outside the verdict              |
| **Roots**       | MNQ and NQ                                                                                                                       |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                     |
| **Windows**     | selection 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ), holdout from there to 2026-09-18                                   |

`htf=AT`, the close exactly on the 60-minute average, holds no rows.

## The reproduction holds exactly

Every `latch=off` row equals its stored twin on every statistic, in all 22 strata: 34,560 rows per stratum, 760,320 in all, at 2 to 30 minutes, with none unmatched and none differing. The stored twins are §M19.3's grid re-swept in the same run, after [#453].

## The paired read: 5 of 12 cells clear, all at 2 and 5 minutes

**A latch beats the control at a resolution only where, on both roots, the median paired delta is positive and the sign test reaches p < 0.05, in both windows.** Unfiltered, all 1,728 pairs per cell:

| latch | bars | selection, MNQ / NQ | holdout, MNQ / NQ | clears |
| ----- | ---- | ------------------- | ----------------- | ------ |
| 3     | 2    | +0.038 / +0.033     | +0.057 / +0.045   | yes    |
| 3     | 5    | +0.015 / +0.012     | +0.027 / +0.045   | yes    |
| 3     | 10   | −0.004 / +0.002     | +0.039 / +0.036   | no     |
| 3     | 15   | +0.032 / +0.003     | +0.025 / −0.009   | no     |
| 6     | 2    | +0.034 / +0.028     | +0.055 / +0.051   | yes    |
| 6     | 5    | −0.005 / −0.004     | +0.041 / +0.042   | no     |
| 6     | 10   | −0.011 / −0.000     | −0.005 / −0.011   | no     |
| 6     | 15   | +0.045 / +0.029     | +0.023 / +0.000   | no     |
| 12    | 2    | +0.029 / +0.020     | +0.047 / +0.037   | yes    |
| 12    | 5    | +0.005 / +0.010     | +0.041 / +0.040   | yes    |
| 12    | 10   | −0.005 / +0.001     | −0.008 / −0.007   | no     |
| 12    | 15   | −0.003 / −0.015     | +0.029 / +0.002   | no     |

**At 2 minutes every length clears**, and at 5 minutes the 3- and 12-close latches do. Every clearing cell's sign tests are below 0.025. At 10 and 15 minutes every length misses on at least one root in one window. At 30 minutes, outside the verdict, no length clears.

**It is a losing rule made to lose less.** The control's median configuration runs at a profit factor of 0.82 to 0.98 across the sixteen root, size and window cells, and the latched arms' at 0.82 to 1.01. At 2 minutes, where every length clears, all of them are below 0.95.

**What the latch does to the trades**, against the control, unfiltered:

- It trades less in all sixteen cells, and the shorter the latch the fewer: 43% to 56% of the control's trades at 3 closes, 57% to 69% at 6, and 68% to 78% at 12.
- Its win rate rises by 0.5 to 2.4 points in every cell.
- `session_close_share` moves by under 0.02 either way.

**Across the other 21 strata**, read as description because they share bars, 54 of the 248 length, stratum and bar-size cells at 2 to 15 minutes with rows on both roots in both windows clear the same bar, 29 of them at 2 minutes.

## Gates 1 and 2, per arm

**Gate 1 fails pooled for every arm, as it did for §M19.3.** No arm is majority-profitable in any unfiltered root, size and window cell except one: the 3-close latch on NQ at 10 minutes held out, at 51%. Split as §M19.3 split it, the opposite stop and the long side carry each arm, as they carried §M19.3's.

**Gate 2 fails unfiltered on both roots for the control and every latched arm**, except the 6-close latch on NQ, whose held-out top 20 runs at 1.03. In the strata, the latches clear on both roots in 6, 5 and 8 strata and the control in 7. Every arm holds the same 1,728 combinations, so these counts compare, and they do not separate the latch from the control.

## Gate 3: two cells pass one test at a time, and none family-wise

**Each latched arm's family is the unfiltered stratum plus the strata where it clears gate 2 on both roots, at most six**, at the pre-registered 2 to 15 minutes. The control is measured over all 13 of them. On both roots, the best five configurations over the arm's four variants by selection-window profit factor were tested on the holdout, with 200 draws over bars: 330 tests, none refused.

| arm         | family, beside unfiltered                                                                                                      | tests |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `latch=3`   | `phase=LONDON`, `phase=MIDDAY`, `regime=UNCLASSIFIABLE`, `phase=OVERNIGHT`, `htf=BELOW`, `phase=PRE_OPEN`                      | 70    |
| `latch=6`   | `trend=MIXED`, `phase=PRE_OPEN`, `volume=THIN`, `compression=NORMAL`, `regime=UNCLASSIFIABLE`                                  | 60    |
| `latch=12`  | `trend=MIXED`, `compression=EXPANDED`, `phase=LONDON`, `phase=CASH_OPEN`, `htf=ABOVE`, `phase=PRE_OPEN`, the six best of eight | 70    |
| `latch=off` | the union of the three                                                                                                         | 130   |

**A cell passes only where, on both roots, a configuration beats its null at p ≤ 0.05.** Two do:

- **The 6-close latch in `trend=MIXED`**, at 10 minutes on both roots. Three of five MNQ configurations beat their null, at p = 0.010 to 0.050, and two of five NQ ones, at 0.040 and 0.050. Each holds 28 to 32 held-out trades, at a profit factor of 2.4 to 2.8 against nulls near 1.0. NQ's other three lose, at 5 and 15 minutes.
- **The 12-close latch in `compression=EXPANDED`**, at 2 minutes on both roots. One MNQ configuration beats its null, at p = 0.010 on 49 trades, and three NQ ones do, at 0.010 to 0.020 on 46 to 49. All four use a 40-bar window cut at 0.05. Four of the five MNQ configurations and two of the NQ ones are significantly *worse* than their null.

**No latched arm beats its null unfiltered**, and the control passes in none of its 13 strata. In both passing strata the control has no configuration below 0.05 on either root.

**Read family-wise as description ([§M54](m54-family-wise-null-result.md)), neither cell clears on both roots.** The 12-close latch's `compression=EXPANDED` reaches 0.045 on NQ and 0.075 on MNQ, and the 6-close latch's `trend=MIXED` 0.408 and 0.582. Every other cell's smallest family-wise p is 0.11 or more.

**Adding 30 minutes finds the same two cells.** Gate 3 was first run with gate 2 and the shortlists over 2 to 30 minutes, by a choice made after the pre-registration because 30 minutes became a default bar size ([#479]). That run's families differ for every arm. It passes the same two cells, test for test, and no other.

## The predictions

- **"The reproduction holds, exactly, wherever the stored rows are on the same bars." Right**, on all 760,320 rows.
- **"Every length trades less than the control in all sixteen root × resolution × window cells, and the shorter the latch the fewer." Right.**
- **"No length clears the bar at any resolution." Wrong.** Five of twelve cells clear: every length at 2 minutes, and 3 and 12 closes at 5.
- **"Gate 3 fails unfiltered on both roots for every latched arm." Right.**

## What this settles, and what it does not

**It settles the latch as a paired change.** On short bars, waiting for the squeeze to end and trading a re-break of its frozen range beats trading during the squeeze, on both roots and in both windows. The prediction expected nothing, because §M19.3 found the squeeze's depth inert, and the timing turns out to matter where the depth did not.

**It does not make SqueezeBreakout a candidate.** The gain lifts a median configuration that loses into one that loses less. Gate 2 fails unfiltered for every latch, and gate 3 finds no latched arm beating a random entry unfiltered. The two cells that pass one test at a time rest on 28 to 49 held-out trades. One of them sits beside four configurations significantly worse than random in the same shortlist, and neither clears family-wise on both roots.

**It leaves gate 4 unread.** Neither passing cell has been through the exclusion, bootstrap or walk-forward reads, and the pre-registration did not ask for them.

## How it was read

- **Sweep.** `campaign_sweep.py --strategies SqueezeBreakout --variants squeeze-latch --split --strata squeeze-latch`, at 2, 5, 10 and 15 minutes, and the same set at 30 minutes in the re-sweep's 30-minute pass.
- **Reproduction.** `campaign_early_exit.py --set squeeze-latch --strategy SqueezeBreakout --reproduce --stratum <each>`.
- **Paired read.** `campaign_early_exit.py --set squeeze-latch --strategy SqueezeBreakout --window <each> --stratum <each>`, unfiltered as the verdict and the other strata as description.
- **Gates 1 and 2.** The share of each arm's unfiltered configurations above a profit factor of 1.0, pooled and split by stop and by side, and `campaign_holdout`'s `pair_windows` and `verdict` once per arm, ranked over its four variants.
- **Gate 3.** `campaign_null.py --strategy SqueezeBreakout --variant <the arm's four names> --stratum <its family> --root MNQ NQ --window selection --test-window holdout --top 5 --iterations 200`, on the stored rows narrowed to 2 to 15 minutes, then `campaign_null.py --family-of` on each arm's table; and once more over 2 to 30 with that run's families.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
