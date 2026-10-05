---
id: M49
title: "M49 — InsideBarTrailing's runner trailed to structure: it pays unfiltered at 5 minutes and costs in the midday cell"
archetypes: [InsideBarTrailing]
issues: [352]
gates: [1, 2]
outcome: mixed
verdict: >-
  15-, 10- and 5-minute passes, with 2 minutes to follow; the control reproduces all 119,232 stored rows. At 5 minutes, the bar size the candidate trades at, 34 of 48 cells clear the pre-registered bar — 15 arms on both roots, every 10- and 20-bar box among them — gaining +0.013 to +0.077 held out and +0.006 to +0.056 on the selection window. At 10 minutes 5 cells clear, all on NQ by under 0.03, and at 15 none, where every arm gains held out and none on the selection window. Described rather than tested, the midday cell the epic would trade is where it costs most at 5 minutes: 13 arms cost on both roots in both windows and none clears.
---

# M49 — InsideBarTrailing's runner trailed to structure: it pays unfiltered at 5 minutes and costs in the midday cell ([#352])

[The pre-registration](m49-structure-trail-preregistration.md) fixed the arms, the bar and the predictions before any row was read. This file reads them. **So far it holds the 15-, 10- and 5-minute passes**: 15 minutes swept on 2026-10-04 in 15.3 minutes on eight workers, then 10 and 5 minutes on 2026-10-05 in 32.7 and 76.1 minutes on four. The 2-minute pass will be added here, and the bar each cell is held to does not change.

Every figure below comes from `results/campaign/InsideBarTrailing.duckdb`, batches 12 to 14: the paired reads are `tools/campaign_paired.py`'s and gate 2 is `tools/campaign_holdout.py`'s, called per arm, and the reproduction is the join `tools/campaign_early_exit.py --reproduce` makes, keyed on `structure=` instead of `exit=`.

## The control reproduces the stored rows exactly

**All 119,232 `structure=off` rows** — 432 configurations × 23 strata × 2 roots × 2 windows × 3 resolutions — join their stored `trailing` twin, and no statistic differs in any of them. Adding the mode moved no stored row.

## The pre-registered question

Each arm paired against `structure=off`, unfiltered, configuration by configuration. Every cell holds all 432 pairs. "Significantly" is the sign test at p < 0.05.

| bar size | window    | root | control's median PF | arms' median change | configurations improved, of 432 | arms significantly up / down | cells clearing |
| -------: | --------- | ---- | ------------------: | ------------------: | ------------------------------: | ---------------------------: | -------------: |
|      15m | holdout   | MNQ  |               0.904 |    +0.009 to +0.120 |                      250 to 432 |                       24 / 0 |        0 of 24 |
|      15m | holdout   | NQ   |               0.932 |    +0.012 to +0.157 |                      265 to 432 |                       24 / 0 |        0 of 24 |
|      15m | selection | MNQ  |               0.844 |    −0.034 to +0.000 |                      142 to 219 |                       0 / 20 |                |
|      15m | selection | NQ   |               0.891 |    −0.028 to +0.009 |                      125 to 230 |                       0 / 15 |                |
|      10m | holdout   | MNQ  |               0.969 |    −0.063 to +0.006 |                      130 to 242 |                       1 / 18 |        0 of 24 |
|      10m | holdout   | NQ   |               0.930 |    −0.039 to +0.030 |                      155 to 282 |                        9 / 6 |        5 of 24 |
|      10m | selection | MNQ  |               0.841 |    −0.015 to +0.046 |                      181 to 393 |                       15 / 5 |                |
|      10m | selection | NQ   |               0.881 |    −0.022 to +0.058 |                      169 to 422 |                       15 / 5 |                |
|       5m | holdout   | MNQ  |               1.039 |    −0.006 to +0.058 |                      193 to 368 |                       19 / 1 |       15 of 24 |
|       5m | holdout   | NQ   |               1.009 |    −0.016 to +0.077 |                      177 to 419 |                       20 / 1 |       19 of 24 |
|       5m | selection | MNQ  |               0.936 |    −0.007 to +0.042 |                      200 to 374 |                       17 / 0 |                |
|       5m | selection | NQ   |               0.995 |    +0.006 to +0.056 |                      234 to 369 |                       23 / 0 |                |

A cell clears where its median change is positive and the sign test reaches p < 0.05 in both windows, so "cells clearing" sits on the holdout row.

**At 5 minutes, 34 of 48 cells clear, and 15 arms clear on both roots**: the 10- and 20-bar boxes at every cushion, the 40-bar box at 0, 0.25 and 0.5 ATR, the 5-bar box at 0, 0.25 and 1.0 ATR, and the 3-bar box at 1.0 ATR. They gain +0.013 to +0.077 held out and +0.006 to +0.056 on the selection window.

**At 10 minutes, 5 of 48 clear, every one on NQ at a 1.0 ATR cushion and by under 0.03 held out**; the same five arms on MNQ, over the same bars, lose held out in four and do nothing measurable in the fifth.

**At 15 minutes none clears.** Every arm helps held out on both roots and none helps on the selection window — §M37's outcome for EmaPullback's trail, the effect taking the window's sign.

**As pre-registered, a cell that clears is a candidate for [#354]'s re-read and not a result on its own.** The 48 cells at one bar size share their bars and most of their trades, so the 34 at 5 minutes are not 34 independent results, and the same rule clears broadly at one bar size and nowhere at the one above it.

### By box and cushion

Median change in profit factor, unfiltered, over the four cushions:

| bar size | box | holdout MNQ | holdout NQ | selection MNQ | selection NQ |
| -------: | --: | ----------: | ---------: | ------------: | -----------: |
|      15m |   2 |      +0.115 |     +0.148 |        −0.006 |       −0.003 |
|      15m |   3 |      +0.080 |     +0.120 |        −0.012 |       −0.006 |
|      15m |   5 |      +0.022 |     +0.057 |        −0.011 |       −0.000 |
|      15m |  10 |      +0.038 |     +0.064 |        −0.013 |       −0.022 |
|      15m |  20 |      +0.046 |     +0.064 |        −0.005 |       −0.016 |
|      15m |  40 |      +0.016 |     +0.018 |        −0.012 |       −0.019 |
|      10m |   2 |      −0.001 |     +0.017 |        −0.011 |       −0.014 |
|      10m |   3 |      −0.011 |     +0.018 |        −0.003 |       −0.010 |
|      10m |   5 |      −0.046 |     −0.002 |        −0.000 |       −0.001 |
|      10m |  10 |      −0.050 |     −0.022 |        +0.019 |       +0.029 |
|      10m |  20 |      −0.039 |     +0.003 |        +0.039 |       +0.046 |
|      10m |  40 |      −0.037 |     −0.016 |        +0.028 |       +0.046 |
|       5m |   2 |      +0.009 |     +0.003 |        −0.006 |       +0.020 |
|       5m |   3 |      +0.021 |     +0.022 |        +0.002 |       +0.025 |
|       5m |   5 |      +0.028 |     +0.016 |        +0.013 |       +0.032 |
|       5m |  10 |      +0.048 |     +0.047 |        +0.012 |       +0.040 |
|       5m |  20 |      +0.032 |     +0.051 |        +0.023 |       +0.036 |
|       5m |  40 |      +0.026 |     +0.045 |        +0.041 |       +0.053 |

**At 5 minutes the gain grows with the box**: held out it peaks at 10 bars on MNQ and 20 on NQ, and on the selection window at 40, the widest rung. At 10 minutes the 1.0 ATR cushion is the best of the four rungs in both windows on both roots, and at 15 the narrowest box gains most held out; at 5 the cushion matters little. **Each bar size's best rung sits at a different edge of the ladder** — the narrowest box at 15 minutes, the widest cushion at 10 and the widest box on the 5-minute selection window — so the ladder is cut short at a different end at each.

### What it does to a trade

Median paired change held out, both roots pooled:

| bar size | box | session-close share | trades | bars held |
| -------: | --: | ------------------: | -----: | --------: |
|      15m |   2 |              −0.062 |    +35 |      −3.8 |
|      15m |   5 |              −0.040 |    +12 |      −1.5 |
|      15m |  10 |              −0.006 |  −15.5 |      +1.0 |
|      15m |  40 |              +0.038 |    −66 |      +6.9 |
|      10m |   2 |              −0.072 |    +99 |      −6.7 |
|      10m |   5 |              −0.052 |    +52 |      −3.9 |
|      10m |  10 |              −0.025 |   +0.5 |      −0.6 |
|      10m |  40 |              +0.033 |   −102 |      +7.9 |
|       5m |   2 |              −0.038 |   +273 |     −11.7 |
|       5m |   5 |              −0.032 |   +170 |      −8.4 |
|       5m |  10 |              −0.023 |    +47 |      −3.4 |
|       5m |  40 |              +0.029 |   −244 |     +12.8 |

**The mechanism is the same at every bar size even though the profit-factor effect is not.** A narrow box stops the runner sooner than the high-water trail does, and a wide one later: the stored grid trails at 2, 5 or 10 inside-bar ranges, so a 40-bar box's midpoint usually sits further back than that. The selection window moves the same way on all three columns, except the 10-bar box at 10 minutes, whose changes in trades and bars held are near zero in both windows.

## Gates 1 and 2

**Gate 1**, the share of unfiltered configurations with a profit factor above 1:

| bar size | window    | control MNQ | control NQ | arms MNQ    | arms NQ    |
| -------: | --------- | ----------: | ---------: | ----------- | ---------- |
|      15m | selection |          0% |       0.7% | 0%          | 0%         |
|      15m | holdout   |          6% |        22% | 7% to 70%   | 29% to 92% |
|      10m | selection |          0% |         5% | 0%          | 0% to 17%  |
|      10m | holdout   |         22% |         9% | 3.5% to 28% | 6% to 30%  |
|       5m | selection |         10% |        47% | 0.5% to 35% | 30% to 81% |
|       5m | holdout   |         67% |        57% | 58% to 98%  | 31% to 94% |

**Gate 2**, `tools/campaign_holdout.py` per arm, which ranks across the bar sizes run so far. The control clears on both roots in 10 strata, and the arms in 3 to 13, the most with the 40-bar box (11 to 13). Neither the control nor any arm clears `phase=MIDDAY` on both roots once the shortlist can draw on all three bar sizes.

## The strata, described rather than tested

The same bar, applied in every stratum as description. `htf=AT` has no configuration reaching 30 trades, so it cannot clear; `phase=CLOSE` has none held out at 15 minutes. Across the 22 strata with rows, unfiltered included, there are 528 arm × stratum cells at each bar size. They share bars, and a sign test over configurations that share trades overstates its own evidence.

| stratum                  | 15m clear / cost | 10m clear / cost | 5m clear / cost |
| ------------------------ | ---------------: | ---------------: | --------------: |
| unfiltered               |            0 / 0 |            0 / 0 |          15 / 0 |
| `phase=MIDDAY`           |           11 / 2 |            9 / 0 |      **0 / 13** |
| `phase=AFTERNOON`        |           22 / 0 |           20 / 0 |           9 / 0 |
| `phase=CLOSE`            |            0 / 0 |            3 / 0 |          23 / 0 |
| `compression=NORMAL`     |            6 / 0 |            8 / 0 |          17 / 0 |
| `regime=UNCLASSIFIABLE`  |           14 / 0 |            0 / 1 |          16 / 0 |
| `regime=DIRECTIONAL`     |            0 / 8 |            1 / 0 |          11 / 0 |
| `phase=CASH_OPEN`        |            8 / 0 |            0 / 3 |           9 / 0 |
| `phase=LONDON`           |            0 / 7 |            0 / 8 |           6 / 0 |
| `trend=UP`               |            8 / 0 |            6 / 0 |           0 / 0 |
| `compression=COMPRESSED` |            6 / 0 |            0 / 6 |           1 / 0 |
| **all 528**              |     **104 / 21** |      **70 / 24** |    **196 / 17** |

"Clear / cost" counts the arms that gain, or lose, on both roots in both windows. **At 5 minutes the trail gains almost everywhere — 196 cells against 17 — and midday is the main exception**, with 13 of the 17; `htf=ABOVE` has the other 4. `phase=CLOSE` holds the forced flat, so a change to when the runner leaves always reads as large there (`docs/roadmap.md` §M10.4).

**`phase=MIDDAY`, the cell [#344] would trade, is where it costs most at 5 minutes.** 13 arms lose on both roots in both windows and none gains: held out the median change is −0.032 on both roots, over a control of 1.219 and 1.173, and on the selection window −0.051 and −0.069. Every box loses held out; only the 40-bar box gains on the selection window, by +0.015 and +0.016. That agrees with the first look the pre-registration discloses, which lost profit factor on all ten of this cell's best configurations at 5 minutes. At 10 and 15 minutes the same cell gained held out under 20 to 24 arms on each root — the bar sizes it is not traded at.

## Predicted before the run finished

- **The control reproduces the stored rows exactly** — right at every bar size.
- **Every arm lowers the session-close share in every cell** — wrong at every bar size. Boxes of 2 to 5 lower it and boxes of 20 and 40 raise it, because a wide box sits behind the stored trail.
- **Trade count rises** — right for boxes of 2 to 5 and wrong for 20 and 40, at every bar size.
- **No arm clears the bar in any cell** — right at 15 minutes, though the trail pays held out rather than costing in both windows; wrong at 10, where five NQ cells clear, and at 5, where 34 do.
- **The cost shrinks as the box widens and the cushion grows** — partly right at 5 minutes, where wider boxes gain more, and wrong at 10 and 15.

**One of five was right outright.** The predictions came from the first look, which read §M42's ten best midday configurations at 5 minutes, chosen on the selection window under the high-water trail. That is the one cell where this campaign agrees with it.

## What this does not settle

- **The 2-minute pass is still to run.**
- **The ladder is cut short at a different end at each bar size**: a one-bar box, a box wider than 40 bars and a cushion beyond 1.0 ATR are untested.
- **The midday cell is described, not tested**, as pre-registered; the cost there is a reason to read it first in [#354], not a verdict on it.
- **No gate 3**, as pre-registered: the null for an exit is the strategy without it, which is the control.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
