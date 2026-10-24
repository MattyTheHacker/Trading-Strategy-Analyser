---
id: M26.7
title: "M26.7 — ElasticBand's signal inverted wins the selection window and loses the holdout against the fade, at every bar size, and fails gate 2"
archetypes: [ElasticBand]
issues: [279, 439]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 re-sweep at 2 to 15 minutes, with 1 minute still to run: paired on the same signal bars, every inverted arm beats its fade twin on the selection window and loses to it held out, at every bar size on both roots, so no pair clears §M37's bar; held out the inversion wins less often than the fade on R in all eight cells, against a prediction that it would win more; it fails gate 2 unfiltered on both roots and clears it in one stratum per arm against the fades' 14 and 15, and gate 3 finds nothing on both roots.
---

# M26.7 — ElasticBand's signal inverted wins the selection window and loses the holdout against the fade, at every bar size, and fails gate 2 ([#279])

Pre-registered in [`m26-7-inverted-signal-preregistration.md`](m26-7-inverted-signal-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. [#279] asked whether ElasticBand's fade "may be more valuable inverted": the same signal bars, traded with the move rather than against it.

**One minute is not read yet.** The pre-registration names 1, 2, 5, 10 and 15 minutes, and the re-sweep's 1-minute pass has not reached this set. Everything below is the four larger bar sizes, so the paired read's family is 12 cells rather than 15, and gates 2 and 3 were read at 2 to 15 minutes.

## In plain terms

ElasticBand bets that a stretched price snaps back toward its average. This run took exactly the same moments and bet the other way: that the stretch carries on.

**On the earlier data, betting the other way looks better at every chart size. On the later data, it is worse at every one.** A change whose effect flips with the period it is measured on is not one to trade. On the later data the original snap-back bet is the one that holds up: its best settings stay profitable, and the reversed version's do not.

## What was run

|                 |                                                                                                                         |
| --------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | the fade on R and on its midline ladder, and the inverted signal on R and on stretch ladders 1σ and 2σ past the close   |
| **Grid**        | §M26.5's VWAP channel; `entry_std` × `min_bars_outside` × `stop_mode` × `max_hold_bars`, 36 combinations in every arm   |
| **Strata**      | all 23, one context dimension at a time; 22 hold rows                                                                   |
| **Resolutions** | 2, 5, 10 and 15 minutes; 1 minute not yet run; 30 minutes was swept since and is shown beside them, outside the verdict |
| **Roots**       | MNQ and NQ                                                                                                              |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                            |
| **Windows**     | selection 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ), holdout from there to 2026-09-18                          |

`htf=AT`, the close exactly on the 60-minute average, holds no rows. As pre-registered there is no reproduction step: the fade arms are the control, run in the same pass.

## The paired read: no pair clears, and the sign follows the window

**The inversion beats the fade at a resolution only where, on both roots, the median paired delta is positive and the sign test reaches p < 0.05, in both windows.** Unfiltered, 36 pairs per cell, 30 at 15 minutes held out:

| inverted arm, against | bars | selection, MNQ / NQ | holdout, MNQ / NQ |
| --------------------- | ---- | ------------------- | ----------------- |
| R, the fade on R      | 2    | +0.139 / +0.189     | −0.010 / −0.013   |
| R, the fade on R      | 5    | +0.097 / +0.148     | −0.050 / −0.086   |
| R, the fade on R      | 10   | +0.053 / +0.118     | −0.128 / −0.141   |
| R, the fade on R      | 15   | +0.286 / +0.331     | −0.209 / −0.338   |
| +1σ, the midline      | 2    | +0.068 / +0.096     | −0.051 / −0.067   |
| +1σ, the midline      | 5    | +0.061 / +0.080     | −0.170 / −0.196   |
| +1σ, the midline      | 10   | +0.035 / +0.047     | −0.216 / −0.178   |
| +1σ, the midline      | 15   | +0.172 / +0.263     | −0.357 / −0.407   |
| +2σ, the midline      | 2    | +0.095 / +0.130     | −0.057 / −0.090   |
| +2σ, the midline      | 5    | +0.063 / +0.087     | −0.197 / −0.209   |
| +2σ, the midline      | 10   | +0.041 / +0.058     | −0.193 / −0.159   |
| +2σ, the midline      | 15   | +0.168 / +0.257     | −0.398 / −0.405   |

**Every selection-window delta is positive and every held-out one is negative**, in all 24 root, size and pair cells of each window. The sign tests reach 0.05 on both roots in both windows nowhere, and the bar would fail on the sign alone. At 30 minutes, outside the verdict, the same holds: positive on the selection window, negative held out, by up to 0.61.

**This is the window's sign again**, as [§M37](m37-ema-pullback-trail-on-slow.md) and [§M53](m53-ema-pullback-ma-trail-result.md) found for EmaPullback's trail. The fade's median configuration loses on the selection window at every size, at 0.81 to 0.98, and runs at 0.91 to 1.16 held out, above 1.0 in 11 of 16 cells. Trading the same bars the other way takes the opposite of whatever the fade did in that period.

**Across the other 21 strata**, read as description because they share bars, 3 of the 252 pair, stratum and bar-size cells clear the same bar: the inversion on R in `phase=CASH_OPEN` at 2 and 5 minutes, and the 2σ ladder in `phase=MIDDAY` at 2.

**What the inversion does to the trades**, against the fade, unfiltered:

- It trades less: 13 to 515 fewer trades per configuration, the most at 2 minutes.
- On the R pair, its win rate is 1 to 8 points lower held out at every size, and 0.3 to 4 points higher on the selection window.
- Its mean R is 0.003 to 0.20 lower held out in every cell, and higher on the selection window in every cell.
- On the R pair, `session_close_share` rises by up to 0.07.

## Gates 1 and 2, per arm

**Gate 1 splits by window, the other way round for each side.** Held out, 22% to 83% of the fades' configurations are profitable and 0% to 14% of the inversions'. On the selection window the fades reach at most 39% and the inversions 11% to 81%. Every inverted arm's median configuration loses held out at every size, at 0.79 to 0.92.

**Gate 2: the fades pass unfiltered on both roots and the inversions fail on both.** The fades' held-out top 20 runs at 1.10 to 1.36, with 15 to 19 of 20 profitable. The inversions' runs at 0.81 to 0.85, with one or two profitable. In the strata, the fades clear on both roots in 14 (midline) and 15 (R) of 21. Each inverted arm clears in one, `trend=MIXED`.

## Gate 3: nothing on both roots

**Each inverted arm's family is the strata where it clears gate 2 on both roots**, at the pre-registered 2 to 15 minutes: `trend=MIXED` alone, for all three. Its fade twin was measured over the same family: both roots, the best five configurations by selection-window profit factor, tested on the holdout, 400 draws over bars. That is 50 tests, none refused.

**A cell clears where, on both roots, a configuration beats its null at p ≤ 0.05. None does.** One test reaches that level: the 1σ ladder on NQ at 5 minutes, at p = 0.015 on 69 trades. Its family-wise p over its arm's ten tests is 0.137. Neither fade beats its null in `trend=MIXED`.

**Adding 30 minutes moves the family, not the answer.** Gate 3 was first run with gate 2 and the shortlists over 2 to 30 minutes, by a choice made after the pre-registration because 30 minutes became a default bar size ([#479]).

- That family added `regime=DIRECTIONAL`, where the inverted arms clear gate 2 on both roots at 2 to 30 minutes alone; the R arm's family was `regime=DIRECTIONAL` only.
- No inverted arm clears there either.
- Its fade twins each put one configuration below 0.05 on both roots in `regime=DIRECTIONAL`, at 10 minutes, on 94 and 149 held-out trades.
- That is the control in a stratum chosen on the inversion's gate 2. It is outside both the pre-registered family and the pre-registered question, and is reported as description.

## The predictions

- **"The inverted signal wins more often than the fade: its win rate is above its R twin's in a majority of the ten unfiltered held-out root × resolution cells." Wrong.** It is below in all eight read so far, so one minute cannot make it a majority. On the selection window it is above in all eight.
- **"It does not clear the bar in (2) for any pair at any resolution." Right**, at the four sizes read.
- **"Fewer strata clear gate 2 on both roots under each inverted arm than under its fade twin." Right**: one against 15 on R, and one against 14 for both ladders.
- **"At one minute every arm's median configuration loses on both roots."** Not yet read.

## What this settles, and what it does not

**It settles #279's question at 2 to 15 minutes.** The fade is not more valuable inverted. Held out, the inversion loses to the fade in every cell and fails gate 2 where the fade passes. What it gains on the selection window is where the fade loses.

**It does not make the fade a candidate.** The fade's gains are held out and its losses on the selection window, so this run measures a period effect on both sides of the same bars, not an edge on either. The fade's own gates belong to §M26.5 and the re-sweep, not to this file.

**One minute is owed**, and with it the fourth prediction and the rest of the family of 15.

## How it was read

- **Sweep.** `campaign_sweep.py --strategies ElasticBand --variants elastic-invert --split --strata elastic-invert`, at 2, 5, 10 and 15 minutes; 1 minute is in the re-sweep's fourth part, and 30 minutes was in its 30-minute pass.
- **Paired read.** `campaign_paired`'s `paired` and `verdict` on profit factor for the three pairs, unfiltered and in each stratum, each window on its own; the same pairing on trades, win rate, average bars held, `session_close_share` and mean R beside it.
- **Gates 1 and 2.** The share of each arm's unfiltered configurations above a profit factor of 1.0, and `campaign_holdout`'s `pair_windows` and `verdict` once per arm.
- **Gate 3.** `campaign_null.py --strategy ElasticBand --variant <arm> --stratum trend=MIXED --root MNQ NQ --window selection --test-window holdout --top 5 --iterations 400`, once per arm on the stored rows narrowed to 2 to 15 minutes; and once per arm over 2 to 30 with that run's families.

[#279]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/279
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
