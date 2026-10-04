---
id: M49
title: "M49 — InsideBarTrailing's runner trailed to structure: held out it pays, and on the selection window it does not"
archetypes: [InsideBarTrailing]
issues: [352]
gates: [1, 2]
outcome: mixed
verdict: >-
  15-minute pass, with 2, 5 and 10 minutes to follow: the control reproduces all 39,744 stored rows; unfiltered, every one of the 24 structure-trail arms raises held-out profit factor on both roots and lowers it or leaves it flat on the selection window, so none clears the pre-registered bar in any of the 48 cells — §M37's outcome again, the effect taking the window's sign; described rather than tested, 104 of 528 arm × stratum cells gain in both windows on both roots, including 11 arms at midday.
---

# M49 — InsideBarTrailing's runner trailed to structure: held out it pays, and on the selection window it does not ([#352])

[The pre-registration](m49-structure-trail-preregistration.md) fixed the arms, the bar and the predictions before any row was read. This file reads them. **So far it holds the 15-minute pass alone**, swept on 2026-10-04 from 22:33 in 15.3 minutes; the 2, 5 and 10-minute passes will be added here, and the bar each cell is held to does not change.

Every figure below comes from `results/campaign/InsideBarTrailing.duckdb`, batch 12: the paired reads are `tools/campaign_paired.py`'s and gate 2 is `tools/campaign_holdout.py`'s, called per arm, and the reproduction is the join `tools/campaign_early_exit.py --reproduce` makes, keyed on `structure=` instead of `exit=`.

## The control reproduces the stored rows exactly

**All 39,744 `structure=off` rows** — 432 configurations × 23 strata × 2 roots × 2 windows — join their stored `trailing` twin, and no statistic differs in any of them. Adding the mode moved no stored row.

## The pre-registered question: cleared in no cell, and the sign is the window's

Each arm paired against `structure=off`, unfiltered, configuration by configuration. Every cell holds all 432 pairs.

| window    | root | control's median PF | arms' median change | configurations improved, of 432 | arms significantly up / down |
| --------- | ---- | ------------------: | ------------------: | ------------------------------: | ---------------------------: |
| holdout   | MNQ  |               0.904 |    +0.009 to +0.120 |                      250 to 432 |                       24 / 0 |
| holdout   | NQ   |               0.932 |    +0.012 to +0.157 |                      265 to 432 |                       24 / 0 |
| selection | MNQ  |               0.844 |    −0.034 to +0.000 |                      142 to 219 |                       0 / 20 |
| selection | NQ   |               0.891 |    −0.028 to +0.009 |                      125 to 230 |                       0 / 15 |

"Significantly" is the sign test at p < 0.05. **Held out, every arm helps on both roots; on the selection window, none does, and most cost.** The bar needs both, so **0 of 48 cells clear**. This is §M37's outcome for EmaPullback's trail, the second time a trailing stop has taken the window's sign.

Both arms are a losing configuration space here. Unfiltered InsideBarTrailing at 15 minutes has no configuration with a profit factor above 1 on the selection window under any structure arm, and 3 of 432 under the control on NQ; held out, the median arm's median is 0.960 on MNQ and 1.019 on NQ.

### By box and cushion

Median change in profit factor, unfiltered, over the four cushions:

| box | holdout MNQ | holdout NQ | selection MNQ | selection NQ |
| --: | ----------: | ---------: | ------------: | -----------: |
|   2 |      +0.115 |     +0.148 |        −0.006 |       −0.003 |
|   3 |      +0.080 |     +0.120 |        −0.012 |       −0.006 |
|   5 |      +0.022 |     +0.057 |        −0.011 |       −0.000 |
|  10 |      +0.038 |     +0.064 |        −0.013 |       −0.022 |
|  20 |      +0.046 |     +0.064 |        −0.005 |       −0.016 |
|  40 |      +0.016 |     +0.018 |        −0.012 |       −0.019 |

**Held out, the narrowest box gains most and the widest least; the cushion barely matters** (+0.034 to +0.079 across its four rungs). The best rung is the first one, so the ladder is cut short at its narrow end, where only a one-bar box is left untested.

### What it does to a trade

Median paired change held out, both roots pooled:

| box | session-close share | trades | bars held | win rate |
| --: | ------------------: | -----: | --------: | -------: |
|   2 |              −0.062 |    +35 |      −3.8 |   +0.040 |
|   5 |              −0.040 |    +12 |      −1.5 |   +0.020 |
|  10 |              −0.006 |  −15.5 |      +1.0 |   +0.015 |
|  40 |              +0.038 |    −66 |      +6.9 |   −0.020 |

**A narrow box stops the runner sooner than the high-water trail does, and a wide one later.** The stored grid trails at 2, 5 or 10 inside-bar ranges, so a 40-bar box's midpoint usually sits further back than that. The selection window moves the same way on the first three columns.

## Gates 1 and 2

**Gate 1**, the share of unfiltered configurations with a profit factor above 1: on the selection window, 0% in every structure arm on both roots, and 0% and 0.7% under the control. Held out it is 6% on MNQ and 22% on NQ under the control, and 7% to 70% and 29% to 92% under the arms. The highest are at a 2-bar box with a cushion of 0.25 to 1.0 ATR.

**Gate 2**, `tools/campaign_holdout.py` per arm, at 15 minutes alone until the other passes run. The control clears on both roots in 4 strata. The arms clear in 1 to 10, the most at `box3@1atr` (10, unfiltered among them) and `box2@1atr` (8). Gate 2 reads the holdout, the window the trail is better on, so this is the paired holdout column seen through a shortlist rather than a second result.

## The strata, described rather than tested

The same bar, applied in every stratum as description. `htf=AT` has no configuration reaching 30 trades and `phase=CLOSE` none held out, so neither can clear; across the 22 strata with rows, unfiltered included, there are 528 arm × stratum cells. They share bars, and a sign test over configurations that share trades overstates its own evidence.

| stratum                                    | arms clearing on both roots | arms costing on both roots |
| ------------------------------------------ | --------------------------: | -------------------------: |
| `phase=AFTERNOON`                          |                          22 |                          0 |
| `regime=UNCLASSIFIABLE`                    |                          14 |                          0 |
| `phase=MIDDAY`                             |                          11 |                          2 |
| `trend=UP`, `phase=CASH_OPEN`, `htf=ABOVE` |                      8 each |                          0 |
| `phase=LONDON`                             |                           0 |                          7 |
| `regime=DIRECTIONAL`                       |                           0 |                          8 |
| unfiltered                                 |                           0 |                          0 |

**104 of 528 cells clear on both roots and 21 cost on both.** Unfiltered sits at neither because the strata pull opposite ways: London and the directional regime cost where the afternoon and the unclassifiable regime gain.

**`phase=MIDDAY`, the cell [#344] would trade**: held out, 20 of 24 arms gain on MNQ and 22 on NQ, at a median of +0.049 and +0.061 over a control of 1.169 and 1.137; on the selection window, 12 and 20. The 11 arms clearing on both roots are the 20- and 40-bar boxes at every cushion and the 2-, 5- and 10-bar boxes at 1.0 ATR. **That is a description at 15 minutes, and the cell trades at 5**, where the first look the pre-registration discloses lost profit factor on all ten of its best configurations. What it earns is a place in the 5-minute read, not a verdict.

## Predicted before the run finished

- **The control reproduces the stored rows exactly** — right.
- **Every arm lowers the session-close share in every cell** — wrong. Boxes of 2 to 5 lower it and boxes of 20 and 40 raise it, because a wide box sits behind the stored trail.
- **Trade count rises** — right for boxes of 2 to 5 and wrong from 10 up, for the same reason.
- **No arm clears the bar in any cell** — right, but not for the reason given: the trail does not cost in both windows, it pays held out and costs on the selection window.
- **The cost shrinks as the box widens and the cushion grows** — wrong. Held out the gain is largest at the narrowest box and the cushion barely moves it.

**Two of five were right, and the three that were wrong came from the first look.** It read §M42's ten best midday configurations at 5 minutes, chosen on the selection window under the high-water trail; this reads every configuration.

## What this does not settle

- **15 minutes only.** The 2, 5 and 10-minute passes are still to run, and 5 is where the candidate trades.
- **A one-bar box is untested**, and the narrowest rung is the best one held out.
- **No gate 3**, as pre-registered: the null for an exit is the strategy without it, which is the control.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
