---
id: M49
title: "M49 — InsideBarTrailing's runner trailed to structure: its sign follows the window and the bar size"
archetypes: [InsideBarTrailing]
issues: [352]
gates: [1, 2]
outcome: mixed
verdict: >-
  15- and 10-minute passes, with 2 and 5 minutes to follow: the control reproduces all 79,488 stored rows. At 15 minutes every one of the 24 structure-trail arms raises held-out profit factor on both roots and none raises it on the selection window, so 0 of 48 cells clear. At 10 minutes the signs move, wide boxes gaining on the selection window and costing held out on MNQ, and 5 of 48 cells clear, all on NQ at a 1.0 ATR cushion, by +0.008 to +0.030 held out, while the same five arms lose or do nothing held out on MNQ. Described rather than tested, the midday cell gains held out under 20 to 24 arms on each root at both bar sizes.
---

# M49 — InsideBarTrailing's runner trailed to structure: its sign follows the window and the bar size ([#352])

[The pre-registration](m49-structure-trail-preregistration.md) fixed the arms, the bar and the predictions before any row was read. This file reads them. **So far it holds the 15- and 10-minute passes**: 15 minutes swept on 2026-10-04 in 15.3 minutes on eight workers, and 10 minutes on 2026-10-05 in 32.7 minutes on four. The 2 and 5-minute passes will be added here, and the bar each cell is held to does not change.

Every figure below comes from `results/campaign/InsideBarTrailing.duckdb`, batches 12 and 13: the paired reads are `tools/campaign_paired.py`'s and gate 2 is `tools/campaign_holdout.py`'s, called per arm, and the reproduction is the join `tools/campaign_early_exit.py --reproduce` makes, keyed on `structure=` instead of `exit=`.

## The control reproduces the stored rows exactly

**All 79,488 `structure=off` rows** — 432 configurations × 23 strata × 2 roots × 2 windows × 2 resolutions — join their stored `trailing` twin, and no statistic differs in any of them. Adding the mode moved no stored row.

## The pre-registered question

Each arm paired against `structure=off`, unfiltered, configuration by configuration. Every cell holds all 432 pairs. "Significantly" is the sign test at p < 0.05.

| bar size | window    | root | control's median PF | arms' median change | configurations improved, of 432 | arms significantly up / down |
| -------: | --------- | ---- | ------------------: | ------------------: | ------------------------------: | ---------------------------: |
|      15m | holdout   | MNQ  |               0.904 |    +0.009 to +0.120 |                      250 to 432 |                       24 / 0 |
|      15m | holdout   | NQ   |               0.932 |    +0.012 to +0.157 |                      265 to 432 |                       24 / 0 |
|      15m | selection | MNQ  |               0.844 |    −0.034 to +0.000 |                      142 to 219 |                       0 / 20 |
|      15m | selection | NQ   |               0.891 |    −0.028 to +0.009 |                      125 to 230 |                       0 / 15 |
|      10m | holdout   | MNQ  |               0.969 |    −0.063 to +0.006 |                      130 to 242 |                       1 / 18 |
|      10m | holdout   | NQ   |               0.930 |    −0.039 to +0.030 |                      155 to 282 |                        9 / 6 |
|      10m | selection | MNQ  |               0.841 |    −0.015 to +0.046 |                      181 to 393 |                       15 / 5 |
|      10m | selection | NQ   |               0.881 |    −0.022 to +0.058 |                      169 to 422 |                       15 / 5 |

**At 15 minutes, every arm helps held out on both roots and none helps on the selection window**, so 0 of 48 cells clear — §M37's outcome for EmaPullback's trail, the effect taking the window's sign.

**At 10 minutes the signs move, and 5 of 48 cells clear**, every one on NQ and every one at a 1.0 ATR cushion:

| arm          | NQ selection | NQ holdout | MNQ selection | MNQ holdout |
| ------------ | -----------: | ---------: | ------------: | ----------: |
| `box2@1atr`  |       +0.030 |     +0.023 |        +0.019 |      +0.001 |
| `box3@1atr`  |       +0.032 |     +0.030 |        +0.030 |      −0.013 |
| `box5@1atr`  |       +0.024 |     +0.008 |        +0.032 |      −0.047 |
| `box10@1atr` |       +0.055 |     +0.012 |        +0.039 |      −0.036 |
| `box20@1atr` |       +0.052 |     +0.015 |        +0.039 |      −0.007 |

Median paired change in profit factor. The NQ cells clear the bar; the same arms on MNQ, over the same bars, lose held out in four of five and do nothing measurable in the fifth (`box2@1atr`, p = 0.89). **As pre-registered, a cell that clears is a candidate for [#354]'s re-read and not a result on its own**, and these five are candidates on one root at gains of under 0.03.

Unfiltered, the control's median profit factor is under 1 in every window and root at both bar sizes.

### By box and cushion

Median change in profit factor, unfiltered, over the four cushions:

| box | 15m holdout MNQ | 15m holdout NQ | 15m selection MNQ | 15m selection NQ | 10m holdout MNQ | 10m holdout NQ | 10m selection MNQ | 10m selection NQ |
| --: | --------------: | -------------: | ----------------: | ---------------: | --------------: | -------------: | ----------------: | ---------------: |
|   2 |          +0.115 |         +0.148 |            −0.006 |           −0.003 |          −0.001 |         +0.017 |            −0.011 |           −0.014 |
|   3 |          +0.080 |         +0.120 |            −0.012 |           −0.006 |          −0.011 |         +0.018 |            −0.003 |           −0.010 |
|   5 |          +0.022 |         +0.057 |            −0.011 |           −0.000 |          −0.046 |         −0.002 |            −0.000 |           −0.001 |
|  10 |          +0.038 |         +0.064 |            −0.013 |           −0.022 |          −0.050 |         −0.022 |            +0.019 |           +0.029 |
|  20 |          +0.046 |         +0.064 |            −0.005 |           −0.016 |          −0.039 |         +0.003 |            +0.039 |           +0.046 |
|  40 |          +0.016 |         +0.018 |            −0.012 |           −0.019 |          −0.037 |         −0.016 |            +0.028 |           +0.046 |

**At 15 minutes the narrowest box gains most held out and the cushion barely matters. At 10 minutes the wide boxes gain on the selection window and cost held out on MNQ, and the 1.0 ATR cushion is the best of the four rungs in both windows on both roots.** Each bar size's best rung is at an edge of the ladder — the narrowest box at 15 minutes, the widest cushion at 10 — so the ladder is cut short at a different end at each.

### What it does to a trade

Median paired change held out, both roots pooled:

| box | 15m session-close share | 15m trades | 15m bars held | 10m session-close share | 10m trades | 10m bars held |
| --: | ----------------------: | ---------: | ------------: | ----------------------: | ---------: | ------------: |
|   2 |                  −0.062 |        +35 |          −3.8 |                  −0.072 |        +99 |          −6.7 |
|   5 |                  −0.040 |        +12 |          −1.5 |                  −0.052 |        +52 |          −3.9 |
|  10 |                  −0.006 |      −15.5 |          +1.0 |                  −0.025 |       +0.5 |          −0.6 |
|  40 |                  +0.038 |        −66 |          +6.9 |                  +0.033 |       −102 |          +7.9 |

**The mechanism is the same at both bar sizes even though the profit-factor effect is not.** A narrow box stops the runner sooner than the high-water trail does, and a wide one later: the stored grid trails at 2, 5 or 10 inside-bar ranges, so a 40-bar box's midpoint usually sits further back than that. The selection window moves the same way on all three columns, except the 10-bar box at 10 minutes, whose changes in trades and bars held are near zero in both windows.

## Gates 1 and 2

**Gate 1**, the share of unfiltered configurations with a profit factor above 1:

| bar size | window    | control MNQ | control NQ | arms MNQ    | arms NQ    |
| -------: | --------- | ----------: | ---------: | ----------- | ---------- |
|      15m | selection |          0% |       0.7% | 0%          | 0%         |
|      15m | holdout   |          6% |        22% | 7% to 70%   | 29% to 92% |
|      10m | selection |          0% |         5% | 0%          | 0% to 17%  |
|      10m | holdout   |         22% |         9% | 3.5% to 28% | 6% to 30%  |

**Gate 2**, `tools/campaign_holdout.py` per arm, which ranks across the bar sizes run so far. The control clears on both roots in 5 strata, and the arms in 1 to 8, the most with the 2-bar box (6 to 8). Gate 2 reads the holdout, where the 15-minute gain sits, so it is the paired holdout column seen through a shortlist rather than a second result.

## The strata, described rather than tested

The same bar, applied in every stratum as description. `htf=AT` has no configuration reaching 30 trades, so it cannot clear; `phase=CLOSE` has none held out at 15 minutes. Across the 22 strata with rows, unfiltered included, there are 528 arm × stratum cells at each bar size. They share bars, and a sign test over configurations that share trades overstates its own evidence.

| stratum                  | 15m clear on both roots | 15m cost on both roots | 10m clear on both roots | 10m cost on both roots |
| ------------------------ | ----------------------: | ---------------------: | ----------------------: | ---------------------: |
| `phase=AFTERNOON`        |                      22 |                      0 |                      20 |                      0 |
| `phase=MIDDAY`           |                      11 |                      2 |                       9 |                      0 |
| `trend=UP`               |                       8 |                      0 |                       6 |                      0 |
| `compression=NORMAL`     |                       6 |                      0 |                       8 |                      0 |
| `regime=UNCLASSIFIABLE`  |                      14 |                      0 |                       0 |                      1 |
| `phase=CASH_OPEN`        |                       8 |                      0 |                       0 |                      3 |
| `compression=COMPRESSED` |                       6 |                      0 |                       0 |                      6 |
| `phase=LONDON`           |                       0 |                      7 |                       0 |                      8 |
| `regime=DIRECTIONAL`     |                       0 |                      8 |                       1 |                      0 |
| unfiltered               |                       0 |                      0 |                       0 |                      0 |
| **all 528**              |                 **104** |                 **21** |                  **70** |                 **24** |

**The afternoon, midday, `trend=UP` and `compression=NORMAL` gain under six or more arms at both bar sizes, and London costs at both.** Others swap: the unclassifiable regime, the cash open and compressed bars gain at 15 minutes and not at 10. Unfiltered clears at neither, because the strata pull opposite ways.

**`phase=MIDDAY`, the cell [#344] would trade.** Held out, every one of the 24 arms gains on both roots at 10 minutes (median +0.037 and +0.065 over a control of 0.914 and 0.958), as 20 and 22 did at 15. On the selection window, 13 of 24 gain on each root at 10 minutes, at a median of +0.004. Nine arms clear on both roots at 10 minutes and eleven at 15. **That is a description at two bar sizes, and the cell trades at 5**, where the first look the pre-registration discloses lost profit factor on all ten of its best configurations. What it earns is a place in the 5-minute read, not a verdict.

## Predicted before the run finished

- **The control reproduces the stored rows exactly** — right at both bar sizes.
- **Every arm lowers the session-close share in every cell** — wrong at both. Boxes of 2 to 5 lower it and boxes of 20 and 40 raise it, because a wide box sits behind the stored trail.
- **Trade count rises** — right for boxes of 2 to 5 and wrong for 20 and 40, at both.
- **No arm clears the bar in any cell** — right at 15 minutes, though the trail pays held out rather than costing in both windows; wrong at 10, where five NQ cells clear.
- **The cost shrinks as the box widens and the cushion grows** — wrong at 15 minutes, where the narrowest box gains most held out; at 10 minutes the widest cushion is the best rung, and the box has no consistent order.

**One of five was right outright.** The predictions came from the first look, which read §M42's ten best midday configurations at 5 minutes, chosen on the selection window under the high-water trail; this reads every configuration.

## What this does not settle

- **The 2 and 5-minute passes are still to run**, and 5 is where the candidate trades.
- **The ladder is cut short at a different end at each bar size**: a one-bar box and a cushion beyond 1.0 ATR are untested.
- **No gate 3**, as pre-registered: the null for an exit is the strategy without it, which is the control.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
