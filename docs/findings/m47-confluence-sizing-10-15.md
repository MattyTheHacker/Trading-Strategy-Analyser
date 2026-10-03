---
id: M47
title: "M47 — the confluence size on every archetype at 10 and 15 minutes: it clears its null on OpeningRange and EmaCrossover, and no cell that clears passes gate 4"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [295, 391]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  The first of two pre-registered passes: at 10 and 15 minutes the all-labels size beats its own sizes shuffled in 13 of the 64 unfiltered cells read, 12 on OpeningRange and 1 on EmaCrossover. In 8 of the 13 the sized configurations still lose money held out; none passes gate 4's bootstrap or exclusion; and through the prop accounts the extra contracts cost passes in every one. InsideBarTrailing's midday cell clears 20 of 20 on both roots at 10 minutes, in the family read as hypothesis-generating. The 5-minute pass, which holds §M45's own cell, is §M47.1, and 2 minutes was dropped.
---

# M47 — the confluence size on every archetype at 10 and 15 minutes ([#295], [#391])

**The first of the two passes [the pre-registration](m47-confluence-sizing-preregistration.md) splits the run into**: every archetype at 10 and 15 minutes, every arm, both roots, all 23 strata and both windows. Its families and `k` count all four resolutions, so this pass does not move the bar the second is held to. The second pass, at 5 minutes alone after 2 minutes was dropped, is [§M47.1](m47-1-confluence-sizing-5.md). It holds F0 and §M45's own cell.

**A "yes" below is final, and a "no" was provisional until [§M47.1](m47-1-confluence-sizing-5.md).** An archetype answers F1 yes if any of its cells clears. At 5 minutes InsideBarTrailing joins OpeningRange and EmaCrossover, and the other six answer no at the three bar sizes read.

## The run reproduced its stored rows

`tools/campaign_gates.py` re-runs each configuration before reading it: 199,763 re-runs, every trade count and every net identical to the stored row. Outside InsideBarTrailing the null checks, on every configuration, that the size moved no trade before it draws a shuffle. Every read completed.

## Gate 3, unfiltered: the size clears on OpeningRange and EmaCrossover

F1 is the all-labels arm and the symmetric arm, unfiltered, `k` = 6 on both roots. 64 of its 134 cells are at 10 and 15 minutes:

| archetype         | cells at 10 min | clear | cells at 15 min | clear | most hits on the weaker root |
| ----------------- | --------------: | ----: | --------------: | ----: | ---------------------------: |
| DeadCatBounce     |               1 |     0 |               1 |     0 |                            0 |
| PullBackAndGo     |               1 |     0 |               1 |     0 |                            0 |
| EmaCrossover      |               2 |     1 |               2 |     0 |                            7 |
| EmaPullback       |               1 |     0 |               1 |     0 |                            0 |
| InsideBar         |               2 |     0 |               2 |     0 |                            0 |
| InsideBarTrailing |               2 |     0 |               2 |     0 |                            1 |
| ElasticBand       |               8 |     0 |               8 |     0 |                            0 |
| OpeningRange      |               6 |     3 |              12 |     9 |                           14 |
| SqueezeBreakout   |               6 |     0 |               6 |     0 |                            0 |
| **all**           |              29 |     4 |              35 |     9 |                              |

The 13 that clear, with each configuration's held-out profit factor under the arm and under its sizes shuffled, both as the shortlist's median:

| archetype    | minutes | arm                                                               | beat their shuffle, MNQ / NQ | held-out PF, MNQ / NQ |      shuffled |    trades | session-close share |
| ------------ | ------: | ----------------------------------------------------------------- | ---------------------------: | --------------------: | ------------: | --------: | ------------------: |
| EmaCrossover |      10 | `stop=swing size=confluence`                                      |                  9 / 7 of 20 |         1.164 / 1.180 | 1.117 / 1.131 | 816 / 823 |         0.17 / 0.16 |
| OpeningRange |      10 | `window=30m stop=atr target=R size=confluence`                    |                 10 / 8 of 20 |         0.815 / 0.802 | 0.783 / 0.774 | 578 / 580 |         0.25 / 0.24 |
| OpeningRange |      10 | `window=30m stop=atr target=width size=confluence symmetric`      |                  6 / 6 of 16 |         0.778 / 0.781 | 0.706 / 0.709 | 500 / 498 |         0.21 / 0.20 |
| OpeningRange |      10 | `window=30m stop=opposite target=R size=confluence`               |                14 / 16 of 20 |         1.138 / 1.149 | 1.032 / 1.028 | 422 / 420 |         0.55 / 0.56 |
| OpeningRange |      15 | `window=15m stop=atr target=R size=confluence`                    |                12 / 12 of 20 |         0.845 / 0.805 | 0.730 / 0.714 | 551 / 552 |         0.21 / 0.21 |
| OpeningRange |      15 | `window=15m stop=atr target=width size=confluence`                |                12 / 12 of 16 |         0.699 / 0.701 | 0.626 / 0.636 | 551 / 552 |         0.16 / 0.17 |
| OpeningRange |      15 | `window=15m stop=atr target=width size=confluence symmetric`      |                14 / 12 of 16 |         0.733 / 0.735 | 0.628 / 0.636 | 551 / 552 |         0.16 / 0.17 |
| OpeningRange |      15 | `window=15m stop=opposite target=width size=confluence`           |                  8 / 8 of 16 |         1.034 / 1.036 | 0.954 / 0.967 | 522 / 522 |         0.31 / 0.31 |
| OpeningRange |      15 | `window=15m stop=opposite target=width size=confluence symmetric` |                 12 / 9 of 16 |         1.103 / 1.085 | 0.961 / 0.975 | 522 / 522 |         0.31 / 0.31 |
| OpeningRange |      15 | `window=30m stop=atr target=R size=confluence`                    |                14 / 10 of 20 |         0.758 / 0.730 | 0.686 / 0.683 | 563 / 564 |         0.27 / 0.27 |
| OpeningRange |      15 | `window=30m stop=atr target=width size=confluence`                |                 7 / 10 of 16 |         0.671 / 0.672 | 0.620 / 0.621 | 492 / 492 |         0.21 / 0.21 |
| OpeningRange |      15 | `window=30m stop=atr target=width size=confluence symmetric`      |                 11 / 9 of 16 |         0.702 / 0.689 | 0.617 / 0.624 | 492 / 492 |         0.21 / 0.21 |
| OpeningRange |      15 | `window=30m stop=opposite target=R size=confluence`               |                11 / 15 of 20 |         1.109 / 1.132 | 1.022 / 1.015 | 421 / 420 |         0.55 / 0.55 |

**Clearing the null is not making money.** Eight of OpeningRange's twelve cells are its ATR stop, where the sized configurations return a median held-out profit factor of 0.671 to 0.845. There the size puts more contracts on the less bad trades of a configuration that loses. The four on the opposite-extreme stop, and EmaCrossover's swing stop, pay: 1.034 to 1.180. OpeningRange's `target=width` grid holds 16 configurations, so its shortlist is the whole grid and `k` is unchanged.

**Every configuration in these cells takes at least 397 held-out trades**, and each shortlist's median `ambiguous_share` is at most 0.044, below the 0.05 that calls for `tools/campaign_ambiguity.py`.

## Which label carries it

F2 is each label alone, unfiltered, `k` = 7. **16 of its 137 cells at 10 and 15 minutes clear, all on OpeningRange and EmaCrossover.** On OpeningRange the VWAP side clears 6, trend 5, regime 3 and the higher timeframe 1; volume clears none. On EmaCrossover only volume clears, in the cell whose all-labels arm clears: the swing stop at 10 minutes, 11 and 9 of 20. No label clears alone on any other archetype.

## Symmetric against add-only

22 of the 46 symmetric cells are at 10 and 15 minutes. The bar is more than half the pairs improved, or fewer than half, at a sign-test p below 0.05/46 on both roots:

| archetype         | better | worse | neither | pairs improved, held out                                     |
| ----------------- | -----: | ----: | ------: | ------------------------------------------------------------ |
| InsideBar         |      2 |     0 |       0 | 100% of 432 on both roots at both bar sizes                  |
| InsideBarTrailing |      2 |     0 |       0 | 89–95% of 432                                                |
| OpeningRange      |      4 |     0 |       2 | all 16 where better; 50–81% in the two 30-minute cells at 15 |
| ElasticBand       |      0 |     4 |       4 | 24–33% on the −0.5s and 0.0s targets at both bar sizes       |
| SqueezeBreakout   |      0 |     2 |       2 | 30–38% on the opposite stop at both bar sizes                |

**On ElasticBand and SqueezeBreakout the symmetric arm counts labels the add-only arm drops**, so what is worse there is those labels and the step they shed together, not shedding alone.

## Against the control, held out

A read, not the verdict. The all-labels arm improves held-out profit factor over its control on 88–100% of pairs in every OpeningRange cell, 84–100% on InsideBar, 80–92% on InsideBarTrailing and 58–94% on DeadCatBounce. It is worse on ElasticBand at 10 minutes, 19–30%, and on SqueezeBreakout's opposite stop, 24–37%.

**A paired share is not gate 3.** InsideBar improves all 432 MNQ pairs at 10 minutes and still clears 7 of 20 on MNQ and none on NQ against its shuffle. Its pairs share their trades, and its shortlist sits only 0.029 and 0.012 of profit factor above its shuffled median, which is inside what the same sizes shuffled produce.

## Gates 1, 2 and 4

**Gates 1 and 2 barely move.** Across the 84 unfiltered all-labels cells, one per root, gate 1 passes in 25 against the control's 23 and gate 2 in 20 against the control's 20.

In the 13 cells that clear gate 3:

| read          | result                                                                                                                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| gate 2        | passes on both roots in 3 — EmaCrossover's swing stop at 10 minutes and OpeningRange's `window=30m stop=opposite target=R` at both — and each one's control passes too; one more passes on NQ alone |
| walk-forward  | passes on both roots in 10 of 13, including five ATR-stop cells whose control fails, at a pooled profit factor of 1.001 to 1.063                                                                    |
| bootstrap     | the median configuration's 5th-percentile profit factor is 0.54 to 0.97, below 1.0 in all 13                                                                                                        |
| the exclusion | without its session-close legs the median configuration's profit factor is 0.26 to 0.63, and its net-to-drawdown negative, in all 13                                                                |

**So no cell that clears gate 3 passes gate 4**, and the bootstrap fails for the controls too: no all-labels arm and no control passes it in any of the 84 unfiltered cells.

## The strata

F3 is every arm in every other stratum, `k` = 8. **190 of its 3,680 cells at 10 and 15 minutes clear**: OpeningRange 157, InsideBarTrailing 16, InsideBar 9, SqueezeBreakout 4, DeadCatBounce 2 and EmaCrossover 2. One is above 5% ambiguous, EmaCrossover's swing stop at 15 minutes in the consolidating regime. `tools/campaign_ambiguity.py` settles it: all 20 configurations keep a profit factor above 1.0 under the worse policy, on both roots and both windows, and every correction against the minute bars raises it, by 0.000 to 0.077. So it counts.

**InsideBarTrailing's midday cell at 10 minutes repeats §M45's result at a second bar size.** Its all-labels arm beats its shuffle on 20 of 20 configurations on both roots, and so does its symmetric arm. InsideBar's midday cell at 10 minutes does the same: 19 and 19, and 20 and 20 symmetric. F3 is hypothesis-generating by pre-registration, but this is the cell §M45 passed rather than one picked out of the 3,680.

**Gate 4 on all 190: none passes all three reads on both roots.** OpeningRange passes the walk-forward in 98 and the bootstrap in 13, and the exclusion in none. InsideBar and InsideBarTrailing are the reverse: the exclusion passes in 9 of 9 and 8 of 16, and the bootstrap in none. InsideBarTrailing's midday all-labels arm at 10 minutes, taking the weaker root on each read, pools 1.006 in the walk-forward, puts its median configuration's bootstrap 5th percentile at 0.65, and without its session-close legs holds a profit factor of 1.83 and a net-to-drawdown of 3.79.

## The prop replay

Each arm's held-out shortlist at its stored base size, through §M28.13's four presets, against its control:

- **The all-labels arm raises the pass rate in 3 of 42 MNQ cells and 1 of 42 NQ cells**, and median net in 12 of 42 MNQ cells and none on NQ.
- **In the 13 cells that clear gate 3 the pass rate falls on both roots in all 13.** On MNQ median attempts rise from 14–51 to 84–247; on NQ the arm passes no account, where its control passes 4 to 27.
- **The symmetric arm, which also takes a step off, does less damage**: it raises the pass rate in 5 of 22 MNQ cells and 8 of 22 NQ cells.

**This reads the size as much as where it goes.** The arm trades more contracts than its control on every signal a label favours, and §M46 found that every step up in size buys more resets. A control at the arm's mean size would separate the two, and it was not pre-registered.

## InsideBarTrailing's tiers at 10 and 15 minutes

Read with §M45's bar: more than half the pairs improved at p < 0.05 against `split=0.5` and against the tier's inverse, on both roots. **No tier reaches it.** At 10 minutes every tier loses to `split=0.5` on both roots, improving 21–41% of 432 pairs. The nearest is `trend-age` at 15 minutes, which beats both on NQ, 61% and 85%, and loses to the half on MNQ, 38%. Hypothesis-generating only, as pre-registered.

## What this settles, and what it does not

- **#295's question has an answer on two archetypes: on OpeningRange and EmaCrossover the confluence size puts more contracts on the better trades**, at 10 and 15 minutes on both roots.
- **It makes neither tradeable.** In 8 of OpeningRange's 12 cells the sized configurations lose money held out, no cell that clears passes gate 4's bootstrap or exclusion, and the extra contracts cost passes in every prop replay of those cells.
- **The other seven archetypes were "not at 10 or 15 minutes".** At 5 minutes [§M47.1](m47-1-confluence-sizing-5.md) adds InsideBarTrailing, and the other six answer no at the three bar sizes read.
- **F0 and §M45's cell through the account are read in [§M47.1](m47-1-confluence-sizing-5.md)**: no label carries that cell alone, and on MNQ the size raises its prop pass rate on all four presets.
- **It is `TIER1_ONLY`.** None of the five labels exists in NT8, and a port needs each pinned first — `docs/nt8-fidelity.md` §M47.

[#295]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/295
[#391]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/391
