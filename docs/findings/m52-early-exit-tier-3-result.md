---
id: M52
title: "M52 — the conditional early exit's third tier: 5 of 33 cells clear, three of them EmaPullback's"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369, 439]
gates: [1, 2]
outcome: mixed
verdict: >-
  Pre-registered and run on the October 2026 re-sweep: the control reproduces all 93,504 stored rows it joins to; 5 of the 33 pre-registered cells clear, three of them EmaPullback's, where MNQ picks giving back half of a 1 R excursion at every bar size and NQ at 5 and 10 minutes, by +0.008 to +0.011 of held-out profit factor with the median configuration still losing, and the others InsideBarTrailing unfiltered at 15 minutes and SqueezeBreakout at 5; neither midday cell clears. Every exit that can close a winner costs held out in a majority of its bound cells, "only if losing" moves profit factor less in 9 of 11 pairs, the volatility exit gains held out from 1.5 ATRs up against the prediction, and the shorter count against the trend changes almost nothing.
---

# M52 — the conditional early exit's third tier: 5 of 33 cells clear, three of them EmaPullback's ([#369])

Pre-registered in [`m52-early-exit-tier-3-preregistration.md`](m52-early-exit-tier-3-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. [§M48](m48-early-exit-result.md) ran [#369]'s first tier and [§M50](m50-early-exit-tier-2-result.md) its second; this is the third, built in [#448]: a stall, leaving the entry's session phase, the higher-timeframe side turning, a thin bar, a heavy bar against, the ATR expanding while losing, closes against in a row, one close against by a distance in ATRs, a give-back from the best excursion, and a shorter not-working count for an entry against the trend.

**3,182,592 combinations unfiltered and 277,056 at midday**, both roots, at 5, 10 and 15 minutes, over the 60/40 selection and held-out windows, at the root's own commission and one tick of slippage: every archetype's stored grid once per arm, 36 arms and a control with every rule off.

## In plain terms

Each of these rules closes a trade early when something about it looks wrong: the price has stalled, a heavy bar has gone against it, it has handed back most of its gain. Earlier rounds tried other versions and found that closing early mostly costs money.

**This round is mostly the same.** Rules that can close a winning trade cost more often than they help. **The exception is EmaPullback**: closing once a trade has given back half of a decent gain helps a little at every chart size, on both contracts and in both periods. But EmaPullback still loses money with the rule on; it just loses less. A handful of other wins appear on one contract only, or in one period only.

Neither of the two midday slices that matter for a prop account is helped.

## The control reproduces the stored rows exactly

Every `exit3=off` row joined to the stored campaign row with the same base variant, parameters, root, resolution, window and stratum, and compared on every stored statistic:

| archetype         | stratum      | rows joined | unmatched | rows differing |
| ----------------- | ------------ | ----------: | --------: | -------------: |
| DeadCatBounce     | unfiltered   |       3,456 |         0 |          **0** |
| ElasticBand       | unfiltered   |       6,912 |         0 |          **0** |
| EmaCrossover      | unfiltered   |      12,288 |         0 |          **0** |
| EmaPullback       | unfiltered   |      27,648 |         0 |          **0** |
| InsideBar         | unfiltered   |       5,184 |         0 |          **0** |
| InsideBarTrailing | unfiltered   |       5,184 |         0 |          **0** |
| InsideBarTrailing | phase=MIDDAY |       5,184 |         0 |          **0** |
| OpeningRange      | unfiltered   |       2,304 |         0 |          **0** |
| OpeningRange      | phase=MIDDAY |       2,304 |         0 |          **0** |
| PullBackAndGo     | unfiltered   |       2,304 |         0 |          **0** |
| SqueezeBreakout   | unfiltered   |      20,736 |         0 |          **0** |

**93,504 rows, no differences.** The parameter families the arms set are left out of the join, as pre-registered.

## The verdict: 5 of 33 cells clear

In each archetype × resolution cell and on each root, the selection window picks the bound arm with the highest median paired delta; the cell clears if that pick's held-out delta is positive with the sign test at p < 0.05 on both roots. A root's pick that pays is in bold, and a positive one that misses p < 0.05 carries its p.

| archetype         | stratum      | minutes | MNQ pick               | MNQ held out     | NQ pick                | NQ held out     |
| ----------------- | ------------ | ------: | ---------------------- | ---------------- | ---------------------- | --------------- |
| DeadCatBounce     | unfiltered   |       5 | `heavy-against-losing` | −0.0121          | `heavy-against-losing` | −0.0124         |
| DeadCatBounce     | unfiltered   |      10 | `heavy-against-losing` | +0.0024 (p 0.11) | `phase`                | **+0.0082**     |
| DeadCatBounce     | unfiltered   |      15 | `giveback0.5@1R`       | −0.0388          | `giveback0.5@1R`       | −0.0319         |
| ElasticBand       | unfiltered   |       5 | `atr1.5x`              | −0.0017          | `atr1.5x`              | 0.0000 (p 0.51) |
| ElasticBand       | unfiltered   |      10 | `atr1.5x`              | −0.0015          | `closes4`              | **+0.0163**     |
| ElasticBand       | unfiltered   |      15 | `closes3-losing`       | −0.0076          | `closes3`              | −0.0179         |
| EmaCrossover      | unfiltered   |       5 | `bars10@0R-counter5`   | −0.0046          | `adverse0.5atr-losing` | −0.0348         |
| EmaCrossover      | unfiltered   |      10 | `heavy-against-losing` | −0.0177          | `atr1.25x`             | **+0.0016**     |
| EmaCrossover      | unfiltered   |      15 | `heavy-against-losing` | −0.0114          | `heavy-against-losing` | −0.0120         |
| EmaPullback       | unfiltered   |       5 | `giveback0.5@1R`       | **+0.0113**      | `giveback0.5@1R`       | **+0.0078**     |
| EmaPullback       | unfiltered   |      10 | `giveback0.5@1R`       | **+0.0108**      | `giveback0.5@1R`       | **+0.0079**     |
| EmaPullback       | unfiltered   |      15 | `giveback0.5@1R`       | **+0.0113**      | `heavy-against-losing` | **+0.0451**     |
| InsideBar         | unfiltered   |       5 | `htf`                  | −0.0037          | `htf`                  | −0.0157         |
| InsideBar         | unfiltered   |      10 | `atr2x`                | 0.0000           | `heavy-against`        | −0.1061         |
| InsideBar         | unfiltered   |      15 | `closes2-losing`       | −0.0626          | `heavy-against`        | **+0.0557**     |
| InsideBarTrailing | phase=MIDDAY |       5 | `adverse1atr-losing`   | −0.0497          | `bars20@0R`            | −0.1483         |
| InsideBarTrailing | phase=MIDDAY |      10 | `heavy-against`        | −0.1412          | `atr1.5x`              | **+0.0118**     |
| InsideBarTrailing | phase=MIDDAY |      15 | `htf`                  | −0.0723          | `adverse0.5atr`        | −0.1493         |
| InsideBarTrailing | unfiltered   |       5 | `giveback0.5@0.5R`     | **+0.0043**      | `giveback0.5@0.5R`     | 0.0000 (p 0.53) |
| InsideBarTrailing | unfiltered   |      10 | `closes3-losing`       | −0.0817          | `bars20@0R`            | **+0.0164**     |
| InsideBarTrailing | unfiltered   |      15 | `adverse1atr`          | **+0.0522**      | `heavy-against`        | **+0.0644**     |
| OpeningRange      | phase=MIDDAY |       5 | `bars5@0R`             | −0.0173          | `bars5@0R`             | −0.0166         |
| OpeningRange      | phase=MIDDAY |      10 | `adverse1atr-losing`   | −0.0337          | `adverse0.5atr-losing` | −0.0629         |
| OpeningRange      | phase=MIDDAY |      15 | `heavy-against-losing` | −0.0733          | `closes3-losing`       | −0.0300         |
| OpeningRange      | unfiltered   |       5 | `atr1.25x`             | −0.0072          | `atr1.25x`             | −0.0060         |
| OpeningRange      | unfiltered   |      10 | `adverse1atr-losing`   | −0.0353          | `adverse1atr-losing`   | −0.0307         |
| OpeningRange      | unfiltered   |      15 | `heavy-against-losing` | −0.0364          | `closes3-losing`       | −0.0133         |
| PullBackAndGo     | unfiltered   |       5 | `giveback1@0.5R`       | −0.0338          | `giveback1@0.5R`       | −0.0092         |
| PullBackAndGo     | unfiltered   |      10 | `giveback0.5@1R`       | −0.0085          | `thin-losing`          | **+0.0059**     |
| PullBackAndGo     | unfiltered   |      15 | `giveback0.5@0.5R`     | −0.0729          | `thin`                 | −0.0984         |
| SqueezeBreakout   | unfiltered   |       5 | `atr1.5x`              | **+0.0044**      | `atr1.25x`             | **+0.0085**     |
| SqueezeBreakout   | unfiltered   |      10 | `heavy-against-losing` | **+0.0058**      | `adverse0.5atr-losing` | −0.0080         |
| SqueezeBreakout   | unfiltered   |      15 | `thin-losing`          | −0.0033          | `heavy-against`        | −0.0312         |

**EmaPullback clears at all three bar sizes, and at 5 and 10 minutes both roots pick the same arm**: close once the trade has given back half of an excursion that reached 1 R. Held out it gains +0.0078 to +0.0113 over about 1,800 paired configurations, and it gained on the selection window too, +0.010 to +0.019. **The median configuration still loses**: held out it moves from 0.92–0.97 to 0.93–0.98. At 15 minutes NQ picks closing a losing trade on a heavy bar against it, which gains +0.045 held out and +0.024 on the selection window. At 5 minutes that arm costs on the selection window and gains held out, by +0.05 and +0.06: the window's sign again.

**InsideBarTrailing clears at 15 minutes unfiltered**, with a different arm on each root: one close 1 ATR against on MNQ, +0.052 held out, and a heavy bar against on NQ, +0.064. The median configuration moves from 0.90 to 0.97 on MNQ and from 0.93 to 1.04 on NQ. **SqueezeBreakout clears at 5 minutes**, closing a losing trade once the ATR has expanded, at +0.004 and +0.009, with the median still at 0.87 to 0.93.

**These are the sizes §M48 and §M50 warned about.** The sign test counts configurations that share their trades, so a consistent change of a few thousandths reaches p < 0.0001. The pre-registration says a clearing cell is a candidate for [#354]'s re-read, not a result on its own.

**Nine more picks pay on one root only**, and **43 of the 66 root picks lose held out.** On InsideBar at 5 minutes and on MNQ at 10, every bound arm cost on the selection window, so the pick is the arm that cost least.

## What each rule does

Counted over the 54 archetype × root × resolution cells unfiltered, only where the arm is bound (its paired rows' average hold moved in at least half of them), and never pooled across bar sizes. The second column is how many of the 54 held-out cells that is; the selection counts are over that window's own bound cells.

| arm                    | bound, held out | selection: costs / gains | held out: costs / gains | held-out range   | trades, held out |
| ---------------------- | --------------: | -----------------------: | ----------------------: | ---------------- | ---------------: |
| `phase`                |              52 |                  42 / 12 |                 32 / 20 | −0.122 to +0.050 |           +4.3 % |
| `htf`                  |              47 |                  34 / 11 |                 25 / 22 | −0.038 to +0.017 |           +0.5 % |
| `htf-losing`           |              47 |                  32 / 10 |                 25 / 21 | −0.038 to +0.017 |           +0.5 % |
| `thin`                 |              54 |                   50 / 4 |                 43 / 11 | −0.098 to +0.049 |          +11.2 % |
| `thin-losing`          |              54 |                   46 / 8 |                 32 / 21 | −0.056 to +0.054 |           +4.4 % |
| `heavy-against`        |              54 |                  40 / 14 |                 40 / 14 | −0.152 to +0.120 |          +11.8 % |
| `heavy-against-losing` |              53 |                  30 / 24 |                 31 / 22 | −0.163 to +0.118 |           +6.8 % |
| `atr1.25x`             |              42 |                  21 / 21 |                 24 / 18 | −0.065 to +0.016 |           +1.2 % |
| `atr1.5x`              |              42 |                  17 / 25 |                 20 / 21 | −0.019 to +0.050 |           +0.3 % |
| `atr2x`                |              38 |                   9 / 29 |                  7 / 26 | −0.005 to +0.006 |           +0.0 % |
| `stall3`               |              53 |                  42 / 10 |                 37 / 16 | −0.140 to +0.036 |          +18.2 % |
| `stall3-losing`        |              45 |                   41 / 5 |                 33 / 11 | −0.120 to +0.052 |          +12.6 % |
| `stall5`               |              46 |                   41 / 6 |                 30 / 16 | −0.091 to +0.048 |          +16.6 % |
| `stall5-losing`        |              42 |                   36 / 8 |                 24 / 18 | −0.088 to +0.053 |          +11.4 % |
| `stall10`              |              42 |                   38 / 4 |                 22 / 20 | −0.086 to +0.066 |          +11.8 % |
| `stall10-losing`       |              42 |                   33 / 9 |                 23 / 19 | −0.082 to +0.064 |           +5.7 % |
| `closes2`              |              54 |                  43 / 10 |                  44 / 9 | −0.111 to +0.034 |          +17.7 % |
| `closes2-losing`       |              50 |                  35 / 14 |                 38 / 12 | −0.069 to +0.044 |          +12.1 % |
| `closes3`              |              43 |                   35 / 7 |                 33 / 10 | −0.102 to +0.050 |          +14.5 % |
| `closes3-losing`       |              42 |                  27 / 15 |                 28 / 14 | −0.103 to +0.054 |           +8.7 % |
| `closes4`              |              42 |                   34 / 8 |                 24 / 18 | −0.086 to +0.074 |           +8.2 % |
| `closes4-losing`       |              42 |                  28 / 14 |                 20 / 22 | −0.084 to +0.074 |           +3.9 % |
| `adverse0.5atr`        |              54 |                   46 / 8 |                  45 / 9 | −0.155 to +0.046 |          +17.7 % |
| `adverse0.5atr-losing` |              52 |                  42 / 12 |                 40 / 12 | −0.149 to +0.065 |          +11.8 % |
| `adverse1atr`          |              52 |                  33 / 19 |                 29 / 23 | −0.084 to +0.082 |          +10.4 % |
| `adverse1atr-losing`   |              46 |                  27 / 20 |                 23 / 23 | −0.086 to +0.049 |           +4.7 % |
| `giveback0.5@0.5R`     |              48 |                  37 / 10 |                 33 / 13 | −0.081 to +0.151 |           +4.4 % |
| `giveback1@0.5R`       |              43 |                   37 / 5 |                 28 / 14 | −0.054 to +0.060 |           +4.8 % |
| `giveback0.5@1R`       |              43 |                  29 / 13 |                 29 / 13 | −0.056 to +0.030 |           +2.1 % |
| `giveback1@1R`         |              40 |                  22 / 19 |                 23 / 17 | −0.018 to +0.017 |           +1.3 % |
| `bars5@0R`             |              42 |                   38 / 8 |                 31 / 11 | −0.167 to +0.032 |           +8.0 % |
| `bars5@0R-counter3`    |              42 |                   38 / 8 |                  34 / 8 | −0.166 to +0.031 |           +8.9 % |
| `bars10@0R`            |              42 |                   32 / 8 |                 21 / 21 | −0.060 to +0.052 |           +5.2 % |
| `bars10@0R-counter5`   |              42 |                  32 / 10 |                 20 / 22 | −0.057 to +0.052 |           +6.3 % |
| `bars20@0R`            |              42 |                  27 / 15 |                 13 / 28 | −0.086 to +0.043 |           +2.2 % |
| `bars20@0R-counter10`  |              42 |                  29 / 13 |                 15 / 27 | −0.085 to +0.045 |           +2.9 % |

- **The market exits repeat §M48's and §M50's split.** Every exit that can close a winner costs held out in a majority of its bound cells, 485 of 715 together. The 3-close stall, the thin bar, two closes against and half an ATR against cost most often and add 11% to 18% more trades.
- **"Only if losing" softens most of them**: it moves profit factor less than the plain arm does. On the higher-timeframe exit it is identical to the plain arm in 37 of 47 cells, because a close on the far side of the higher-timeframe average from the position is almost always a losing close already.
- **The volatility exit gains more often than it costs from 1.5 ATRs up**: 21 to 20 held out at 1.5 ATRs and 26 to 7 at 2 ATRs, though at 2 ATRs it moves profit factor by at most 0.006 anywhere. At 1.25 ATRs it costs more often, 24 to 18.
- **The give-back exit costs more often than it gains at every setting**, in 23 to 33 of its 40 to 48 cells, though it holds EmaPullback's clearing picks. Giving back all of the excursion costs less than giving back half.
- **The not-working count at 20 bars gains more often than it costs held out**, 28 to 13, having cost on the selection window 27 to 15. That is the window's sign again, as §M50 found for its excursion exit at bar 20.
- **The two windows agree on the sign of an arm's effect in 64% of 1,620 bound arm × cell pairs**, against §M48's 65% and §M50's 66%.

## The four contrasts

Read the same way, one arm against another, as description. A count is of the unfiltered held-out cells where both arms are bound, the second arm better / worse.

- **"Only if losing" against the plain arm**: better more often in 10 of 11 pairs, by medians up to +0.020, the most for the 3-close stall, the thin bar and half an ATR against. On the higher-timeframe exit the two are identical in 37 of 47 cells.
- **The shorter count against the trend against its twin**: barely different. At bars 5, 10 and 20 the counter-trend arm is better in 20, 10 and 10 of 42 cells, worse in 5, 11 and 9, and identical in the rest, by at most 0.010 either way.
- **The give-back's two shares**: giving back all of the excursion beats half in 32 of 43 cells armed at 0.5 R and in 27 of 40 armed at 1 R, by medians of +0.018 and +0.011.
- **The volatility exit's three multiples**: 1.5 ATRs beats 1.25 in 25 of 42 cells, 2 ATRs beats 1.25 in 20 of 38, and 2 ATRs loses to 1.5 in 23 of 38. Every median is within 0.003.

## The two midday cells

**InsideBarTrailing's midday cell clears at no bar size.** Every pick loses held out but NQ's at 10 minutes. At 5 minutes, where the cell is traded, the picks lose 0.050 and 0.148. **At 5 minutes 2 of 33 bound arms gain held out on both roots**: the volatility exit at 1.5 ATRs, by +0.017 and +0.012, and giving back half of a 0.5 R excursion, by under 0.002. Neither gained on both roots on the selection window. At 15 minutes, closing a losing trade on a thin bar gains +0.219 and +0.145 held out, having cost 0.074 and 0.019 on the selection window.

**OpeningRange's midday cell clears nowhere**: every pick loses held out, by 0.017 to 0.073. Its largest gain held out on both roots is the 5-close stall at 15 minutes, +0.048 and +0.049.

## The predictions

| #   | stated before the run                                                                                                                    | what came back                                                                                                                                          |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The control reproduces the stored rows exactly                                                                                           | **Right**: 93,504 rows, none differing                                                                                                                  |
| 2   | Every exit that can close a winner costs held out in a majority of its bound cells                                                       | **Right** for all 15 arms, narrowly for the 10-close stall, 22 of 42, and the higher-timeframe exit, 25 of 47                                           |
| 3   | Each "only if losing" arm moves held-out profit factor less than its unconditional twin, in a majority of the cells where both are bound | **Right for 9 of 11 pairs**; not for the higher-timeframe exit, identical in 37 of 47 cells, nor for two closes against, 25 of 50                       |
| 4   | The phase exit and the volatility exit cost held out in a majority of their bound cells                                                  | **Right for the phase exit**, 32 of 52, and the volatility exit at 1.25 ATRs, 24 of 42; **wrong at 1.5 and 2 ATRs**, which cost in 20 of 42 and 7 of 38 |
| 5   | The shorter count against the trend costs against its twin in a majority of the cells where both are bound                               | **Wrong**: it costs in 5, 11 and 9 of 42 cells at bars 5, 10 and 20, and is identical in 17 to 23                                                       |
| 6   | DeadCatBounce and PullBackAndGo are untested by every arm that cannot fire before its fifth bar                                          | **Right but for one arm**: the 5-close stall binds in 4 of their 12 cells; the 10-close stall and every not-working count bind in none                  |
| 7   | The selection window's pick pays on both roots in no more than a few of the 33 cells                                                     | **Borderline**: five, three of them EmaPullback's                                                                                                       |

## Gates 1 and 2

**Gate 1 moves both ways.** Unfiltered, the control has a majority of configurations profitable in 18 of the 108 root, size and window cells. 14 more reach a majority under at least one arm: 11 held out, on EmaPullback, InsideBar, InsideBarTrailing and SqueezeBreakout, and 3 on the selection window. Some arm takes the control's majority away in five of the six archetypes where it has one.

**Gate 2 moves wherever arms bind.** Where the control passes, on EmaCrossover, InsideBar, OpeningRange unfiltered, InsideBarTrailing unfiltered on MNQ and its midday cell on NQ, between 4 and 24 of the 36 arms fail. Where it fails, on EmaPullback, SqueezeBreakout, InsideBarTrailing unfiltered on NQ, its midday cell on MNQ and PullBackAndGo on NQ, between 1 and 20 arms pass. On DeadCatBounce, ElasticBand, OpeningRange's midday cell and PullBackAndGo on MNQ no arm changes the verdict. Gate 2 pools the resolutions and base variants that the paired read keeps apart, so the two can disagree, and neither is the verdict.

## What this settles, and what it does not

**At 5 to 15 minutes, #369's third tier rescues nothing for a prop account.** Neither midday cell clears, and at 5 minutes InsideBarTrailing's best arms gain under 0.02. The market exits repeat what §M48 and §M50 found.

**It leaves one candidate for [#354]'s re-read**: EmaPullback's give-back exit, which the selection window picks at every bar size and which gains in both windows. It gains a hundredth of profit factor on an archetype whose median configuration loses, and the sign test that clears it counts configurations that share their trades.

**InsideBarTrailing's unfiltered 15-minute cell and SqueezeBreakout's 5-minute cell clear with a different arm on each root**, so they name a bar size, not a rule.

## How it was read

- **Sweep.** `campaign_sweep.py --variants early-exit-3 --split --strata early-exit-3` at 15, 10 and 5 minutes, and `--strategies InsideBarTrailing OpeningRange --strata midday` the same, in the re-sweep.
- **Reproduction and verdict.** `campaign_early_exit.py --set early-exit-3 --strategy <each> --reproduce`, and `--picks` in the unfiltered stratum and in `phase=MIDDAY`.
- **Per-arm table and contrasts.** `campaign_early_exit`'s `ladder` per archetype, stratum and window, and the same pairing with one arm in place of the control for the contrasts. "Bound" is `campaign_hold`'s share of paired rows whose average hold moved.
- **Gates 1 and 2.** The share of each arm's unfiltered configurations above a profit factor of 1.0, and `campaign_holdout`'s `pair_windows` and `verdict` once per arm, pooled over its base variants.

[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#448]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/448
