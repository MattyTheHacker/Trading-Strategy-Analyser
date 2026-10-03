---
id: M47.1
title: "M47.1 — the confluence size on every archetype at 5 minutes: InsideBarTrailing clears unfiltered, no label carries §M45's cell alone, and no cell passes gate 4"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [391, 295]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  The second and last pass of §M47, at 5 minutes; 2 minutes was dropped. The all-labels size beats its own sizes shuffled in 10 of 41 unfiltered cells, 8 on OpeningRange and 2 on InsideBarTrailing, so over 5, 10 and 15 minutes the answer is yes on OpeningRange, EmaCrossover and InsideBarTrailing and no on the other six. In §M45's midday cell no label carries the size alone: only volume, narrowly, and the symmetric arm clear F0. No cell that clears passes all three gate-4 reads. Through the prop accounts the size costs passes on OpeningRange and leaves InsideBarTrailing's unfiltered pass rate level; in §M45's midday cell it raises the MNQ pass rate on all four presets, a read rather than a test.
---

# M47.1 — the confluence size on every archetype at 5 minutes ([#391])

**The second pass [the pre-registration](m47-confluence-sizing-preregistration.md) splits the run into, at 5 minutes alone**: every archetype, every arm, both roots, all 23 strata and both windows. The first pass, at 10 and 15 minutes, is [§M47](m47-confluence-sizing-10-15.md).

**The 2-minute half was dropped before it ran**, on 2026-10-03, to save compute time and so the archive could take new data ([#354]). Its cells are not read here. A 2-minute read later would be a new campaign, with its own fit and pre-registration. **The bar does not move**: every family and `k` still counts all four resolutions, so the 5-minute cells are held to the same `k` over fewer tests, which is conservative.

**So every F1 answer below is final at the three bar sizes read.** An archetype that clears no F1 cell at 5, 10 or 15 minutes answers no at those three, and 2 minutes stays unread.

## What ran

Every 5-minute cell, on the archive and the fitted cuts the first pass used: the nine cut files still hash to the values the pre-registration transcribes. The sweep planned 4,570,560 combinations and skipped the 31,104 in §M45's stored cells, its nine InsideBarTrailing arms in the unfiltered and midday strata, as pre-registered.

**Code merged between the two passes moves no row here.** [#402]'s fix to a same-side entry at a pending exit acts only with a hold cap or an early exit on, and no arm sets either. [#403]'s reward-to-risk check is off at `min_reward_risk = 0` in every grid, and every swept `tp_multiplier` is at least 1.0, its new floor. [#406]'s breakeven stop and [#395]'s early exit are off by default.

**The run reproduced its stored rows.** `tools/campaign_gates.py` re-runs each configuration before reading it: 121,699 re-runs across the batch and the stratum reads, every trade count and every net identical to the stored row. Every read completed.

## Gate 3, unfiltered: InsideBarTrailing joins OpeningRange

F1 is the all-labels arm and the symmetric arm, unfiltered, `k` = 6 on both roots. 41 of its 134 cells are at 5 minutes:

| archetype         | cells | clear | most hits on the weaker root |
| ----------------- | ----: | ----: | ---------------------------: |
| DeadCatBounce     |     1 |     0 |                            1 |
| PullBackAndGo     |     1 |     0 |                            0 |
| EmaCrossover      |     2 |     0 |                            0 |
| EmaPullback       |     1 |     0 |                            0 |
| InsideBar         |     2 |     0 |                            0 |
| InsideBarTrailing |     2 |     2 |                           15 |
| ElasticBand       |     8 |     0 |                            1 |
| OpeningRange      |    18 |     8 |                           11 |
| SqueezeBreakout   |     6 |     0 |                            2 |
| **all**           |    41 |    10 |                              |

OpeningRange has 18 cells here against 6 at 10 minutes and 12 at 15, because only the 5-minute bar divides all three of its windows, 5, 15 and 30 minutes.

The 10 that clear, with the shortlist's median held-out profit factor under the arm and under its sizes shuffled:

| archetype         | arm                                                               | beat their shuffle, MNQ / NQ | held-out PF, MNQ / NQ |      shuffled |      trades | session-close share |
| ----------------- | ----------------------------------------------------------------- | ---------------------------: | --------------------: | ------------: | ----------: | ------------------: |
| InsideBarTrailing | `trailing size=confluence`                                        |                13 / 18 of 20 |         1.098 / 1.029 | 1.068 / 0.997 | 1835 / 1411 |         0.10 / 0.18 |
| InsideBarTrailing | `trailing size=confluence symmetric`                              |                15 / 20 of 20 |         1.110 / 1.039 | 1.069 / 0.995 | 1824 / 1411 |         0.10 / 0.18 |
| OpeningRange      | `window=5m stop=atr target=R size=confluence`                     |                 7 / 10 of 20 |         0.828 / 0.856 | 0.769 / 0.774 |   925 / 924 |         0.11 / 0.11 |
| OpeningRange      | `window=5m stop=atr target=width size=confluence`                 |                10 / 12 of 16 |         0.700 / 0.722 | 0.645 / 0.667 |   716 / 717 |         0.10 / 0.10 |
| OpeningRange      | `window=5m stop=atr target=width size=confluence symmetric`       |                 9 / 12 of 16 |         0.742 / 0.777 | 0.648 / 0.664 |   716 / 717 |         0.10 / 0.10 |
| OpeningRange      | `window=30m stop=atr target=R size=confluence`                    |                 8 / 12 of 20 |         0.887 / 0.908 | 0.844 / 0.843 |   623 / 631 |         0.18 / 0.17 |
| OpeningRange      | `window=30m stop=atr target=width size=confluence`                |                  6 / 9 of 16 |         0.765 / 0.796 | 0.745 / 0.761 |   522 / 525 |         0.17 / 0.17 |
| OpeningRange      | `window=30m stop=atr target=width size=confluence symmetric`      |                  6 / 8 of 16 |         0.796 / 0.820 | 0.739 / 0.757 |   522 / 525 |         0.17 / 0.17 |
| OpeningRange      | `window=30m stop=opposite target=R size=confluence`               |                11 / 13 of 20 |         1.163 / 1.156 | 1.067 / 1.062 |   422 / 420 |         0.56 / 0.56 |
| OpeningRange      | `window=30m stop=opposite target=width size=confluence symmetric` |                  7 / 8 of 16 |         1.126 / 1.134 | 1.063 / 1.061 |   435 / 434 |         0.49 / 0.49 |

**Clearing the null is still not making money on OpeningRange.** Six of its eight cells are the ATR stop, where the sized configurations return a median held-out profit factor of 0.700 to 0.908, as at 10 and 15 minutes. The two on the opposite-extreme stop pay, 1.126 to 1.163, with about half their legs closed at the session close. **InsideBarTrailing's two cells pay on both roots**, 1.029 to 1.110, the first unfiltered cells of that archetype to clear in §M47.

**Every configuration in these cells takes at least 398 held-out trades**, and each shortlist's median `ambiguous_share` is at most 0.010, below the 0.05 that calls for `tools/campaign_ambiguity.py`.

**Over 5, 10 and 15 minutes F1 answers yes on OpeningRange, EmaCrossover and InsideBarTrailing, and no on DeadCatBounce, PullBackAndGo, EmaPullback, InsideBar, ElasticBand and SqueezeBreakout.** EmaCrossover's yes is its swing stop at 10 minutes; at 5 its best cell reaches no hits on the weaker root.

## F0: no label carries the size in §M45's cell alone

F0 is §M45's open question: in InsideBarTrailing's midday cell at 5 minutes, which label carries the size? `k` = 5 on both roots:

| arm                                  | beat their shuffle, MNQ / NQ | clears |
| ------------------------------------ | ---------------------------: | :----: |
| `trailing size=confluence symmetric` |                20 / 13 of 20 |  yes   |
| `trailing size=volume`               |                 11 / 7 of 20 |  yes   |
| `trailing size=regime`               |                  3 / 9 of 20 |   no   |
| `trailing size=htf`                  |                  6 / 4 of 20 |   no   |
| `trailing size=trend`                |                  0 / 4 of 20 |   no   |

**Volume clears, narrowly, and nothing else alone does.** Trend beats its shuffle on no MNQ configuration. The all-labels arm, §M45's own cell, belongs to no family; read again by this pass's null it beats its shuffle on 20 of 20 MNQ and 17 of 20 NQ configurations, exactly §M45's result. So the size in this cell is mostly the labels together: each label alone lifts the shortlist's median profit factor about 0.02 above its shuffle, or not at all, against 0.08 to 0.11 for all four.

## Which label carries it, unfiltered

F2 is each label alone, unfiltered, `k` = 7. **14 of its 111 cells at 5 minutes clear, 13 on OpeningRange and 1 on SqueezeBreakout.** On OpeningRange the VWAP side clears 5, trend 4 and regime 4; the higher timeframe and volume clear none. SqueezeBreakout's is volume on the opposite stop, 8 and 9 of 20, in a variant whose all-labels arm does not clear. No label clears alone on InsideBarTrailing unfiltered, where the best reaches 4 of 20 on the weaker root.

## Symmetric against add-only

14 of the 46 symmetric cells are at 5 minutes. The bar is more than half the pairs improved, or fewer than half, at a sign-test p below 0.05/46 on both roots:

| archetype         | better | worse | neither | pairs improved, held out                                |
| ----------------- | -----: | ----: | ------: | ------------------------------------------------------- |
| InsideBar         |      1 |     0 |       0 | 84–100% of 432                                          |
| InsideBarTrailing |      1 |     0 |       0 | 82–94% of 432                                           |
| OpeningRange      |      3 |     0 |       3 | all 16 where better; 75–94% in the three that are not   |
| ElasticBand       |      1 |     0 |       3 | 65–73% of 132 on the +2.0s target; 61–75% where neither |
| SqueezeBreakout   |      0 |     0 |       2 | 45–57% of 288                                           |

**No symmetric cell is worse at 5 minutes**, where 6 of 22 were at 10 and 15, all on ElasticBand and SqueezeBreakout. Those two still count labels the add-only arm drops, so a difference there belongs to those labels and the step they shed together.

## Against the control, held out

A read, not the verdict. The all-labels arm improves held-out profit factor over its control on 75–100% of pairs in every OpeningRange cell, 75–98% on InsideBar and 85–90% on InsideBarTrailing. It is worse on ElasticBand, 21–30%, as at 10 minutes.

## Gates 1, 2 and 4

**Gates 1 and 2 barely move.** Across the 54 unfiltered all-labels cells, one per root, gate 1 passes in 11 against the control's 11 and gate 2 in 19 against the control's 16.

In the 10 cells that clear gate 3:

| read          | result                                                                                                                                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| gate 2        | passes on both roots in 3: InsideBarTrailing's all-labels arm, whose control passes on MNQ alone, and OpeningRange's two opposite-stop cells, one of whose controls passes on both; InsideBarTrailing's symmetric arm passes on MNQ alone |
| walk-forward  | passes on both roots in 7 of 10, at a pooled profit factor of 1.019 to 1.275 on the weaker root, including OpeningRange's three 30-minute ATR cells, whose controls fail it on both                                                       |
| bootstrap     | the median configuration's 5th-percentile profit factor is 0.565 to 0.957, below 1.0 in all 10                                                                                                                                            |
| the exclusion | without its session-close legs the median configuration's profit factor is 0.235 to 0.923, and its net-to-drawdown negative, in all 10                                                                                                    |

**So no cell that clears gate 3 passes gate 4**, and the bootstrap fails for every all-labels arm and every control in all 54 unfiltered cells, as it did at 10 and 15 minutes.

## The strata

F3 is every arm in every other stratum, `k` = 8. **118 of its 2,775 cells read at 5 minutes clear**: OpeningRange 99, SqueezeBreakout 8, InsideBarTrailing 7 and InsideBar 4. None is above 5% ambiguous, so `tools/campaign_ambiguity.py` had nothing to settle.

**Gate 4 on those 118 and F0's 2: none passes all three reads on both roots.**

- **OpeningRange** passes the walk-forward in 54 of 99 and the bootstrap in 1, and the exclusion in none.
- **InsideBar** is the reverse: the walk-forward and the exclusion pass in 4 of 4 and the bootstrap in none. Three of the four are arms in its midday cell, where without its session-close legs the median configuration holds a profit factor above 2.0 on both roots.
- **InsideBarTrailing's F0 cells are the nearest**: the symmetric arm and volume alone pass the walk-forward and the bootstrap, with a median configuration's 5th percentile of 1.151 and 1.055 on the weaker root. Both fail the exclusion: without their session-close legs the profit factor is 0.890 and 0.790. At 10 minutes the same cell's all-labels arm passed the exclusion and failed the bootstrap.

## The prop replay

Each arm's held-out unfiltered shortlist at its stored base size, through §M28.13's four presets, against its control:

- **The all-labels arm raises the pass rate in 2 of 27 MNQ cells and 1 of 27 NQ cells**, and median net in 8 MNQ cells and 1 NQ cell.
- **In OpeningRange's eight clearing cells the MNQ pass rate falls in every one**, from 0.012–0.075 under the control to 0.005–0.026. On NQ neither passes more than a handful of accounts.
- **InsideBarTrailing's unfiltered pass rate is level**: 0.075 and 0.077 on MNQ against the control's 0.076, with the median net up from $35,598 to about $53,200. On NQ almost nothing passes under either.
- **The symmetric arm raises the pass rate in 5 of 14 cells on each root.**

As at 10 and 15 minutes, the arm trades more contracts than its control wherever a label favours the trade, and a control at the arm's mean size was not pre-registered.

### InsideBarTrailing's midday cell through the accounts

The read §M45 never made, and the one [#344] waits on: each arm's held-out shortlist in the midday cell, through the four presets, against `split=0.5`. **On MNQ the all-labels arm raises the pass rate on all four presets:**

| preset       | pass rate, all-labels | pass rate, `split=0.5` | median net, all-labels | median net, `split=0.5` |
| ------------ | --------------------: | ---------------------: | ---------------------: | ----------------------: |
| Apex 150K    |                 0.490 |                  0.336 |                $41,001 |                 $31,433 |
| Apex 50K     |                 0.086 |                  0.067 |                $36,879 |                 $35,876 |
| TopStep 150K |                 0.290 |                  0.235 |                $26,817 |                 $20,523 |
| TopStep 50K  |                 0.071 |                  0.065 |                $19,893 |                 $18,836 |

Pooled over the presets it passes 336 accounts in 3,134 attempts, against the control's 318 in 3,545, and the symmetric arm's pooled rate is 0.110 against 0.090. The higher timeframe alone passes the most often, 0.141, on the fewest attempts. **On NQ almost nothing passes**: the all-labels arm 24 accounts in 24,571 attempts and the control 72 in 23,615, because each NQ contract carries ten times an MNQ contract's dollars.

**This is a read, not a test**, and it reads the extra contracts as much as where they go. Unlike the clearing cells unfiltered, here the size buys passes rather than costing them.

## What this settles, and what it does not

- **#295's question is answered at three bar sizes: the confluence size puts more contracts on the better trades on OpeningRange, EmaCrossover and InsideBarTrailing**, and not on the other six.
- **It makes none of them tradeable on its own.** On OpeningRange most clearing cells lose money held out, and no cell that clears passes all three gate-4 reads.
- **F0's answer is that no single label carries §M45's cell**: volume clears narrowly and the other three do not, while all four together clear 20 and 17 of 20.
- **In that cell on MNQ the size raises prop passes on all four presets.** It is the read [#344]'s port waits on, untested and not size-matched.
- **2 minutes is unread**, and a read there would be a new campaign.
- **It is `TIER1_ONLY`.** None of the five labels exists in NT8, and a port needs each pinned first — `docs/nt8-fidelity.md` §M47.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#391]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/391
[#395]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/395
[#402]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/402
[#403]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/403
[#406]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/406
