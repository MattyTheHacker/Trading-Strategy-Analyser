---
id: M53
title: "M53 — EmaPullback's stop trailed on a third average takes the window's sign, as §M37's slow trail did, and gate 3 fails for every arm"
archetypes: [EmaPullback]
issues: [74, 439]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 re-sweep, and every prediction held: the controls reproduce exactly, on 529,920 rows where the third average is the slow one and 1,059,840 rows per arm against §M37's; paired over identical grids the third average costs against the fixed stop on the selection window at every bar size and gains held out from 5 minutes up, so it clears §M37's bar against neither arm at any resolution; it shortens holds, raises the trade count and moves exits off the forced flat in all sixteen cells, its own three axes barely matter, and gate 3 clears in none of its 18 cells, over the pre-registered 2-to-15-minute family or one chosen at 2 to 30.
---

# M53 — EmaPullback's stop trailed on a third average takes the window's sign, as §M37's slow trail did, and gate 3 fails for every arm ([#439])

Pre-registered in [`m53-ema-pullback-ma-trail-preregistration.md`](m53-ema-pullback-ma-trail-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. It is the first of the loose ends [`build-spec-loose-ends-measured.md`](build-spec-loose-ends-measured.md) left — the trail on an archetype whose edge is a trend — run on EmaPullback, which already carries EmaCrossover's independent-average trail.

## In plain terms

EmaPullback buys a dip back to a moving average in an uptrend, with its stop set just beyond a slower average. This run tried moving that stop up as the trade goes well, following a third moving average of any speed, and asked whether it beats leaving the stop where it was.

**It does not.** On the earlier part of the data it makes things worse at every chart size; on the later part it makes them a little better from 5-minute bars up. A change whose effect flips with the period it is measured on is not one to trade. [§M37](m37-ema-pullback-trail-on-slow.md) found exactly the same when the stop followed the slow average, and which average the stop follows barely matters.

The strict test against random entries finds nothing for any of the three versions.

## What was run

|                 |                                                                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Arms**        | `stop=slow trail2=off`, the fixed stop; `stop=slow trail2=slow`, §M37's slow-average trail; `stop=slow trail2=ma`, a third average         |
| **Grid**        | §M35's 2,304 combinations in every arm; the third arm crosses them with kind `ema`/`sma` × period 20/50/100 × offset 2/8 ticks, for 27,648 |
| **Strata**      | all 23, one context dimension at a time                                                                                                    |
| **Resolutions** | 2, 5, 10 and 15 minutes as pre-registered; 30 minutes was swept since and is shown beside them, outside the verdict                        |
| **Roots**       | MNQ and NQ                                                                                                                                 |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                               |
| **Windows**     | selection 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ), holdout from there to 2026-09-18                                             |

## The reproductions hold exactly

| check                                                                                  | rows compared | rows differing |
| -------------------------------------------------------------------------------------- | ------------- | -------------- |
| the third average where it is the slow one at the stop's offset, against `trail2=slow` | 529,920       | 0              |
| `trail2=off` against §M37's `trail=off`, same bars                                     | 1,059,840     | 0              |
| `trail2=slow` against §M37's `trail=slow`, same bars                                   | 1,059,840     | 0              |

Every stored statistic matches, on every root, bar size, window and stratum, including rows under the 30-trade floor. Both §M37 arms were re-swept in the same run, after [#453], so the second half of the check could be made.

## The paired read: no resolution clears

**The third average beats an arm at a resolution only where, on both roots, the median paired delta is positive and the sign test reaches p < 0.05, in both windows.** Unfiltered, 1,757 to 2,021 pairs per cell, each the median over the third arm's twelve trail settings:

| against        | bars | selection, MNQ / NQ | holdout, MNQ / NQ |
| -------------- | ---- | ------------------- | ----------------- |
| the fixed stop | 2    | −0.049 / −0.028     | −0.021 / −0.006   |
| the fixed stop | 5    | −0.046 / −0.030     | +0.006 / +0.016   |
| the fixed stop | 10   | −0.033 / −0.021     | +0.038 / +0.041   |
| the fixed stop | 15   | −0.033 / −0.024     | +0.032 / +0.039   |
| the fixed stop | 30   | −0.030 / −0.026     | +0.037 / +0.047   |
| the slow trail | 2    | −0.014 / −0.009     | −0.007 / −0.005   |
| the slow trail | 5    | −0.009 / −0.005     | −0.018 / −0.010   |
| the slow trail | 10   | −0.015 / −0.013     | +0.004 / +0.008   |
| the slow trail | 15   | −0.016 / −0.015     | +0.007 / +0.011   |
| the slow trail | 30   | −0.010 / −0.009     | 0.000 / +0.005    |

**With two thousand pairs every one of these deltas is significant in its own direction** — every sign test but one is below 0.001 — so the bar turns on the sign alone, and the sign changes with the window. Against the fixed stop the third average costs on the selection window at every size and gains held out from 5 minutes up; against the slow trail it costs on the selection window everywhere and gains held out by under 0.012 from 10 minutes up. Neither pair clears at any of the four pre-registered sizes, nor at 30 minutes.

**This is §M37's result again**, with a second average: [§M37](m37-ema-pullback-trail-on-slow.md) found the slow-average trail a cost on the selection window and a gain held out, a property of the period rather than of the configuration. Across the other strata, read as description because they share bars, 6 of 210 pair, stratum and bar-size cells clear the same bar.

**What the trail does to the trades** is the same in every one of the sixteen root, size and window cells, against the fixed stop: it cuts the bars held (by 82 to 92 bars at 2 minutes, by 13 to 14 at 15), lowers `session_close_share` (by 0.06 to 0.13), raises the trade count, and lowers the win rate by four to seven points. Mean R moves by under 0.011 either way.

## Inside the third arm: where the average sits is not a lever

η² of each trail axis on profit factor, unfiltered, pooled over bar sizes:

| axis                 | selection, MNQ | selection, NQ | holdout, MNQ | holdout, NQ |
| -------------------- | -------------- | ------------- | ------------ | ----------- |
| `trail_ma_period`    | 0.0228         | 0.0106        | 0.0008       | 0.0011      |
| `trail_ma_kind`      | 0.0000         | 0.0001        | 0.0000       | 0.0000      |
| `trail_offset_ticks` | 0.0002         | 0.0000        | 0.0001       | 0.0001      |

The loose ends' reading on EmaCrossover — trailing at all is the cost, and where the average sits is not a lever — holds on a second archetype.

## Gates 1 and 2, per arm

**Gate 1 follows the paired read.** Against the fixed stop, the third average has the larger profitable share held out from 5 minutes up — 0.36 and 0.47 at 10 minutes against 0.16 and 0.23 — and the smaller one on the selection window at every size, 0.43 and 0.63 at 10 minutes against 0.67 and 0.80.

**Gate 2 fails unfiltered on MNQ for every arm**, and passes on NQ for the fixed stop and the third average, at 2 to 15 minutes and at 2 to 30 alike. In the strata, at 2 to 15 minutes the third average clears on both roots in 6, the slow trail in 9 and the fixed stop in 5; at 2 to 30, in 10, 7 and 6. As the pre-registration says, these counts are not compared: the third arm's shortlist is drawn from twelve times the combinations.

## Gate 3: none of 18 cells clears

**The family is the strata where the third average clears gate 2 on both roots at the pre-registered 2 to 15 minutes**, exactly six: `trend=DOWN`, `htf=BELOW`, `phase=PRE_OPEN`, `phase=CLOSE`, `volume=HEAVY` and `trend=UP`. All three arms were measured over them: both roots, the best five configurations at 2 to 15 minutes by selection-window profit factor, tested on the holdout, 400 draws over bars. That is 180 tests. Two were refused, a fixed-stop and a slow-trail configuration on NQ in `htf=BELOW` at 15 minutes. Each has no losing trade, and no null can be compared against its infinite profit factor.

**A cell clears where, on both roots, a configuration beats its null at p ≤ 0.05. None does, in any arm.** Seven tests beat their null at that level, each cell on one root only:

- the third average on NQ, four of five in `phase=PRE_OPEN` and one in `htf=BELOW`;
- the slow trail on MNQ in `trend=DOWN` and on NQ in `htf=BELOW`.

The fixed stop's one test below 0.05, on NQ in `trend=UP`, is worse than its null. The shortlists are small: a median of 12 to 41 held-out trades per arm, stratum and root.

**Adding 30 minutes changes nothing.** The family was first run with gate 2 and the shortlists over 2 to 30 minutes, by a choice made after the pre-registration because 30 minutes became a default bar size ([#479]).

- That family took `regime=UNCLASSIFIABLE` and `volume=THIN` in place of `volume=HEAVY` and `trend=UP`.
- 30-minute configurations entered six of the twelve arm and stratum shortlists the two families share.
- It also clears in no cell, with one fixed-stop configuration refused. Its closest is the third average in `phase=PRE_OPEN`: four of five NQ configurations below 0.05, and MNQ's best at 0.055.
- Where a shortlist held no 30-minute configuration, the two runs agree test for test.

## The predictions

- **"The reproduction holds: exactly within the run, and against §M37's rows wherever they are on the same bars." Right**, on every row.
- **"Against the fixed stop, the third average lowers `session_close_share` and the bars held, and raises the trade count, in all sixteen root × resolution × window cells." Right**, all three in all sixteen.
- **"It clears the bar against the fixed stop at no resolution." Right.**
- **"It clears the bar against the slow trail at no resolution either." Right.**
- **"Inside its arm, `trail_ma_period` is the largest of the three trail axes, and all three sit below an η² of 0.04." Right**: at most 0.023.

## What this settles, and what it does not

**It settles the trail on EmaPullback.** Trailing the stop on a moving average shortens trades and moves them off the forced flat, and what that is worth in profit factor takes the sign of the period it is measured on, for the slow average and for any of twelve others. Which average, how fast and how far behind are not levers. It sits beside [§M49](m49-structure-trail-result.md), whose structure trail's sign also changed with the window and the bar size.

**It leaves open why the holdout favours trailing.** This run measures that the sign changes with the window, not why.

## How it was read

- **Sweep.** `campaign_sweep.py --variants emapullback-ma-trail --split --strata emapullback-ma-trail --resolutions 2 5 10 15`, in the re-sweep's second part, and the same set at 30 minutes in its 30-minute pass.
- **Reproductions.** Each arm's stored rows joined to the other's on every parameter they share, every statistic compared, no trade floor.
- **Paired read.** `campaign_paired`'s `paired` and `verdict` on profit factor and beside it on `session_close_share`, win rate, trades, average bars held and mean R, unfiltered and in each stratum, each window on its own.
- **η².** One-way, each trail axis on profit factor inside the third arm, unfiltered, per root and window.
- **Gates 1 and 2.** The share of each arm's configurations above a profit factor of 1.0, and `campaign_holdout`'s `pair_windows` and `verdict` run once per arm.
- **Gate 3.** `campaign_null.py --strategy EmaPullback --variant <arm> --stratum <the six> --root MNQ NQ --window selection --test-window holdout --top 5 --iterations 400`, once per arm on the stored rows narrowed to 2 to 15 minutes, and once per arm over 2 to 30 with the 2-to-30 family.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/453
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
