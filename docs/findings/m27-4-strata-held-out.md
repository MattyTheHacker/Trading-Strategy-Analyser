---
id: M27.4
title: "M27.4 — the sixteen strata that were never held out"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, PullBackAndGo]
issues: [199]
gates: [2]
outcome: mixed
verdict: >-
  The shortlist decays by about the same amount in every stratum, it is not noise, and InsideBar's DIRECTIONAL cell turns out to have two larger siblings.
---

# M27.4 — the sixteen strata that were never held out ([#199])

§M27 ran twenty context strata over the full series and only four of them — unfiltered and the three regimes, and those only on the two inside-bar archetypes and EmaCrossover — through the selection/holdout split. Session phase, relative volume, trend label and higher-timeframe side had full-window numbers and no out-of-sample test at all. This is that test: **1,005,440 combinations in 73 minutes across five passes**, after which every archetype has all twenty strata on both split windows.

## Two defects came first, and the second one mattered more

- **`--strata volume|trend|htf` did not exist.** The paragraph above advertised them and `STRATUM_SETS` carried only `unfiltered`, `regime`, `phase`, `core`, `context` and `all`, so a dimension could be added only in threes. The sets are now built from `STRATUM_GROUPS`, which makes the documented command line true and cannot drift from it again.
- **`campaign_holdout.verdict` pooled every stratum into one shortlist.** It grouped by root alone, so `nlargest(20, profit_factor_sel)` drew from all strata at once and the fattest-tailed one supplied the shortlist that every other stratum was then reported as having. With four strata in the split that already misattributed InsideBar's DIRECTIONAL result to its unfiltered row; with twenty it would have been the dominant effect, and the tool would have answered [#199] with the opposite of the truth. **A shortlist is now chosen within one root and one stratum**, because choosing the stratum is a comparison too. The per-regime figures under Gate 2 above were derived per stratum by hand and are unaffected.

## The shortlist decays by about the same amount everywhere

Mean profit factor of the best twenty, selection window against holdout, per dimension:

| dimension  | cells | selection | holdout | decay | mean rank corr |
| ---------- | ----- | --------- | ------- | ----- | -------------- |
| unfiltered | 12    | 1.27      | 0.94    | 0.33  | 0.46           |
| trend      | 34    | 1.37      | 1.03    | 0.34  | 0.30           |
| volume     | 36    | 1.42      | 1.04    | 0.38  | 0.32           |
| htf        | 24    | 1.34      | 0.93    | 0.41  | 0.28           |
| regime     | 36    | 1.46      | 1.04    | 0.42  | 0.32           |
| phase      | 82    | 1.45      | 0.96    | 0.49  | 0.22           |

**The decay is a property of selecting, not of the strata that had never been tested.** The whole spread is 0.17, the smallest decay belongs to a dimension §M27 had already held out and the largest to one it had not. The fear that motivated [#199] — that the untested strata were hiding ElasticBand's 1.834-to-0.592 collapse — is not what the split found.

## It is also not noise, and that needed a null

99 of the 224 testable cells clear Gate 2 — holdout shortlist above 1.0 **and** above the stratum's own holdout median. On its own that number says nothing, because a shortlist drawn at random from the same stratum passes the same gate some of the time. **Drawn at random, 400 times per cell: 20.1%. Chosen on the selection window: 44.2%**, with the real shortlist at the 93rd percentile of its own null in the median cell. The selection-window ranking carries real information about the holdout; it carries much less than the selection window's own numbers suggest.

**Twenty-six percent of cells still invert outright** — selection above 1.3, holdout below 1.0 — and **ElasticBand owns eight of the twelve worst**. Its §M27 elimination was measured on three strata and now holds across seventeen. Stratifying does not rescue it in any dimension.

## `htf=AT` is not a stratum

It clears the thirty-trade floor for no archetype on either root, on the full window or on either split window — price sitting exactly on the 60-minute average is too rare to trade. **The higher-timeframe dimension has two states, not three**, and §M27's twenty strata are really nineteen.

## What changes: DIRECTIONAL has two larger siblings

InsideBar's separation under `regime=DIRECTIONAL`, §M27's strongest cell, reappears under two strata that were never held out, on six to nine times the sample:

| stratum              | holdout shortlist PF, MNQ / NQ | stratum's holdout median | of 20 profitable | median holdout trades |
| -------------------- | ------------------------------ | ------------------------ | ---------------- | --------------------- |
| `regime=DIRECTIONAL` | 1.38 / 1.85                    | 1.12 / 1.07              | 20 / 20          | 122 / 115             |
| `trend=UP`           | 1.31 / 1.23                    | 1.13 / 1.13              | 20 / 20          | 857 / 784             |
| `htf=ABOVE`          | 1.15 / 1.09                    | 1.11 / 1.08              | 20 / 20          | 1013 / 1117           |

All three have a holdout median above 1.0 on both roots, which is the whole parameter space rather than a shortlist, and all three are one mechanism wearing three labels — an inside-bar breakout with the larger trend behind it. **They are one finding, not three.** What they add is sample: [#200] exists because DIRECTIONAL leaves about thirty trades per front-month contract and the per-contract null cannot run on it, and `trend=UP` and `htf=ABOVE` do not have that problem. §M27.5 has since restored that sample at 5 minutes by restating the cut, at the cost of a cell three times the width — so the two larger siblings are still the ones carrying sample rather than borrowing it.

`InsideBar phase=LONDON` is the other cell worth naming, for the opposite reason: its shortlist *rises* out of sample, 1.22 to 1.87 on MNQ and 1.47 on NQ, on 168 and 183 trades. Its stratum median is 0.91 and 0.94, so the stratum loses money and the selection picks well inside it — the reverse of the pattern everywhere else, and unexplained.

## What this does not license

- **None of it has been through Gate 3.** Gate 2 is the weakest of the four, and the matched null is what eliminated two of the three that survived it last time. Nothing above is a candidate until `tools/campaign_null.py` has run on it.
- **224 cells is a heavier multiple-comparisons load than §M27 carried**, and the best of 224 is the expected output of noise. The three strata named above are quoted because they agree with each other and with a mechanism, not because they are the largest numbers in the table — `PullBackAndGo trend=MIXED` is the largest at 2.02 on NQ and rests on 39 holdout trades.
- **Passing on one root is a coin flip.** 38 of the 112 testable archetype × stratum pairs pass on both, and every claim above is a both-roots claim.
- **The strata are not independent of each other.** `regime=DIRECTIONAL`, `trend=UP` and `htf=ABOVE` overlap heavily by construction, which is why they agree and why their agreement is not three confirmations.

[#199]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/199
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
