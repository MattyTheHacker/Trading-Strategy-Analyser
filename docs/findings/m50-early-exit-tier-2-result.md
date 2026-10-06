---
id: M50
title: "M50 — the conditional early exit's second tier, and the breakeven stop: at 10 and 15 minutes one cell in 22 clears, by 0.004"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369, 351]
gates: [1, 2]
outcome: negative
verdict: >-
  Run at 15 and 10 minutes, with 5 minutes not yet run: the control reproduces all 61,568 stored rows it joins to; 1 of the 22 pre-registered cells read clears, EmaPullback at 10 minutes with the breakeven stop at 1 R, +0.004 of profit factor held out on each root while its median configuration still loses; the market exits repeat §M48's split, every stop moved toward the entry with age costs more often than it gains in both windows, the late stop moves held-out profit factor by at most 0.024 unfiltered, and on InsideBar, where it was predicted to help, it costs in 34 of 36 held-out cells. InsideBarTrailing's midday cell is traded at 5 minutes, which is the bar size not yet run.
---

# M50 — the conditional early exit's second tier, and the breakeven stop: at 10 and 15 minutes one cell in 22 clears, by 0.004 ([#369])

**Every bar below was fixed before any row was read**, in [`m50-early-exit-tier-2-preregistration.md`](m50-early-exit-tier-2-preregistration.md); this file is what the run returned. [#430] built [#369]'s second tier, three more market exits and two stop moves, and this campaign runs 38 arms against a control with every rule off: those rules at a few settings each, and two arms of [#351]'s breakeven stop. Every archetype's stored grid ran once per arm at 15 and 10 minutes, on both roots, over the 60/40 selection and held-out windows, unfiltered and in `phase=MIDDAY` for InsideBarTrailing and OpeningRange. **2,221,440 combinations unfiltered in 283.5 minutes and 179,712 at midday in 9.7 minutes**, on two workers, at the root's own commission and one tick of slippage.

## Not yet run: 5 minutes

**The pre-registration covers 5, 10 and 15 minutes, and only 15 and 10 have run.** The 5-minute pass is deferred with no date set; 2 minutes was left out by the pre-registration and has not been run either. The family read here is therefore 22 of the 33 cells, 18 unfiltered and 4 at midday, and nothing below says anything about 5 minutes. **That matters most for InsideBarTrailing's midday cell**, which [#344] trades at 5 minutes, and where §M48 and §M49 both found the 5-minute result differing from the 10-minute one. The 5-minute pass is the pre-registration's two commands at `--resolutions 5`, read the same way, and its cells join the family when it runs.

## The control reproduces the stored rows exactly

Every `exit2=off` row joined to the stored campaign row with the same base variant, parameters, root, resolution, window and stratum, and compared on every stored statistic:

| archetype         | rows joined | unmatched | rows differing |
| ----------------- | ----------: | --------: | -------------: |
| DeadCatBounce     |       2,304 |         0 |          **0** |
| PullBackAndGo     |       1,536 |         0 |          **0** |
| EmaCrossover      |       8,192 |         0 |          **0** |
| EmaPullback       |      18,432 |         0 |          **0** |
| InsideBar         |       3,456 |         0 |          **0** |
| InsideBarTrailing |       6,912 |         0 |          **0** |
| ElasticBand       |       4,608 |         0 |          **0** |
| OpeningRange      |       2,304 |         0 |          **0** |
| SqueezeBreakout   |      13,824 |         0 |          **0** |

**61,568 rows, no differences.** The join leaves out the sizing columns §M45 and §M47 added and, on InsideBarTrailing, the earliness and structure-trail columns §M45 and §M49 added, all of which read null in the stored rows.

## The verdict: 1 of 22 cells clears, by 0.004

In each archetype × resolution cell and on each root, the selection window picks the bound arm with the highest median paired delta; the cell clears if that pick's held-out delta is positive with the sign test at p < 0.05 on both roots. A root's pick that pays is in bold, and a positive one that misses p < 0.05 carries its p.

| archetype         | stratum      | minutes | MNQ pick              |     MNQ held out | NQ pick               | NQ held out |
| ----------------- | ------------ | ------: | --------------------- | ---------------: | --------------------- | ----------: |
| DeadCatBounce     | unfiltered   |      10 | `late30m-entry`       |      0 (unbound) | `breakeven@1R`        |     −0.0104 |
| DeadCatBounce     | unfiltered   |      15 | `breakeven@0.5R`      |      **+0.0056** | `breakeven@0.5R`      |     −0.0019 |
| ElasticBand       | unfiltered   |      10 | `late60m-bar-extreme` |          −0.0009 | `late60m-bar-extreme` | **+0.0014** |
| ElasticBand       | unfiltered   |      15 | `late60m-bar-extreme` |      **+0.0018** | `step10@0.5-losing`   |     −0.0070 |
| EmaCrossover      | unfiltered   |      10 | `late60m-bar-extreme` |          −0.0077 | `losing15m`           |     −0.0206 |
| EmaCrossover      | unfiltered   |      15 | `late60m-bar-extreme` |          −0.0064 | `losing15m`           |     −0.0352 |
| EmaPullback       | unfiltered   |      10 | `breakeven@1R`        |      **+0.0038** | `breakeven@1R`        | **+0.0039** |
| EmaPullback       | unfiltered   |      15 | `late60m-bar-extreme` |          −0.0081 | `late60m-bar-extreme` |     −0.0061 |
| InsideBar         | unfiltered   |      10 | `late60m-bar-extreme` |          −0.0174 | `losing30m`           |     −0.0322 |
| InsideBar         | unfiltered   |      15 | `losing30m`           |          −0.0552 | `excursion30m@0.5R`   |     −0.0516 |
| InsideBarTrailing | phase=MIDDAY |      10 | `late30m-atr`         |          −0.0178 | `late60m-entry`       |     −0.0006 |
| InsideBarTrailing | phase=MIDDAY |      15 | `step5@0.5-losing`    |          −0.0019 | `losing60m`           |     −0.0646 |
| InsideBarTrailing | unfiltered   |      10 | `losing30m`           |          −0.0482 | `losing30m`           | **+0.0194** |
| InsideBarTrailing | unfiltered   |      15 | `losing30m`           |          −0.0159 | `losing30m`           |     −0.0124 |
| OpeningRange      | phase=MIDDAY |      10 | `losing60m`           |          −0.0249 | `losing60m`           |     −0.0144 |
| OpeningRange      | phase=MIDDAY |      15 | `line20`              |          −0.0312 | `step3@0.5`           |     −0.0315 |
| OpeningRange      | unfiltered   |      10 | `late60m-entry`       | +0.0006 (p 0.48) | `late30m-entry`       |     −0.0007 |
| OpeningRange      | unfiltered   |      15 | `invalidated`         |          −0.0077 | `invalidated`         |     −0.0070 |
| PullBackAndGo     | unfiltered   |      10 | `excursion15m@0.5R`   |          −0.0063 | `excursion15m@0.5R`   |     −0.0077 |
| PullBackAndGo     | unfiltered   |      15 | `excursion15m@0.5R`   |      **+0.0249** | `excursion15m@0.5R`   |     −0.0238 |
| SqueezeBreakout   | unfiltered   |      10 | `excursion20@0.5R`    | +0.0004 (p 0.08) | `losing30m`           |     −0.0096 |
| SqueezeBreakout   | unfiltered   |      15 | `excursion60m@0.5R`   |          −0.0076 | `excursion60m@0.5R`   |     −0.0025 |

**The one cell that clears is EmaPullback at 10 minutes, with the stop moved to the entry once a bar closes 1 R in profit.** Both roots pick it, and held out it gains +0.0038 on MNQ and +0.0039 on NQ over 1,809 and 1,814 paired configurations. The median held-out profit factor moves from 0.935 to 0.938 on MNQ and from 0.952 to 0.957 on NQ, so the cell still loses money with the arm on. That is the size §M48 warned about: the sign test counts configurations that share their trades, so a consistent change of a few thousandths reaches p < 0.0001. At 15 minutes the same archetype picks the late stop on both roots, and it costs on both.

**Five more picks pay on one root only**, by +0.0014 to +0.0249, and in each of those cells the other root's pick costs. **The selection window's picks mostly gain there and lose held out**: 34 of the 44 root picks have a negative held-out delta. InsideBar's 15-minute picks are the largest case, +0.137 and +0.143 on the selection window and −0.055 and −0.052 held out.

## What each rule does

Counted over the 36 archetype × root × resolution cells unfiltered, only where the arm is bound (its paired rows' average hold moved in at least half of them), and never pooled across bar sizes. The second column is how many of the 36 held-out cells that is; the selection counts are over that window's own bound cells.

| arm                   | bound, held out | selection: costs / gains | held out: costs / gains | held-out range   | trades, held out |
| --------------------- | --------------: | -----------------------: | ----------------------: | ---------------- | ---------------: |
| `excursion3@0.5R`     |              35 |                   23 / 9 |                 23 / 11 | −0.140 to +0.033 |          +19.6 % |
| `excursion3@1R`       |              36 |                   26 / 9 |                  28 / 8 | −0.140 to +0.027 |          +23.3 % |
| `excursion5@0.5R`     |              30 |                   24 / 5 |                  18 / 9 | −0.127 to +0.033 |          +17.2 % |
| `excursion5@1R`       |              31 |                   25 / 6 |                  24 / 7 | −0.127 to +0.019 |          +22.9 % |
| `excursion10@0.5R`    |              28 |                   21 / 5 |                  9 / 15 | −0.081 to +0.027 |          +13.2 % |
| `excursion10@1R`      |              28 |                   24 / 4 |                  16 / 9 | −0.081 to +0.014 |          +15.8 % |
| `excursion20@0.5R`    |              28 |                   16 / 7 |                  5 / 16 | −0.089 to +0.042 |           +8.0 % |
| `excursion20@1R`      |              28 |                   17 / 8 |                  8 / 18 | −0.089 to +0.036 |           +8.8 % |
| `losing15m`           |              36 |                  25 / 11 |                  27 / 9 | −0.115 to +0.028 |          +16.2 % |
| `excursion15m@0.5R`   |              36 |                   29 / 7 |                  32 / 4 | −0.189 to +0.025 |          +26.8 % |
| `losing30m`           |              34 |                  20 / 13 |                  26 / 8 | −0.116 to +0.023 |          +13.6 % |
| `excursion30m@0.5R`   |              36 |                   24 / 9 |                 24 / 10 | −0.140 to +0.015 |          +20.4 % |
| `losing60m`           |              28 |                   23 / 5 |                  22 / 6 | −0.107 to +0.032 |          +13.4 % |
| `excursion60m@0.5R`   |              30 |                   23 / 6 |                  21 / 9 | −0.082 to +0.031 |          +17.6 % |
| `invalidated`         |              28 |                  14 / 11 |                 11 / 13 | −0.100 to +0.062 |          +16.0 % |
| `invalidated-losing`  |              28 |                  14 / 11 |                 11 / 13 | −0.100 to +0.062 |          +16.0 % |
| `step3@0.5`           |              28 |                   22 / 7 |                 16 / 12 | −0.049 to +0.030 |           +9.1 % |
| `step3@1`             |              35 |                   29 / 4 |                 24 / 11 | −0.086 to +0.088 |          +14.7 % |
| `step5@0.5`           |              28 |                   21 / 7 |                 16 / 12 | −0.042 to +0.025 |           +7.8 % |
| `step5@1`             |              30 |                   28 / 0 |                 17 / 12 | −0.051 to +0.059 |          +14.2 % |
| `step10@0.5`          |              28 |                   21 / 7 |                 15 / 13 | −0.038 to +0.034 |           +5.2 % |
| `step10@1`            |              28 |                   27 / 1 |                 17 / 11 | −0.051 to +0.024 |          +11.9 % |
| `line10`              |              28 |                   24 / 4 |                 18 / 10 | −0.094 to +0.044 |          +17.3 % |
| `line20`              |              28 |                   24 / 4 |                 15 / 13 | −0.100 to +0.067 |          +13.0 % |
| `step3@0.5-losing`    |              28 |                   22 / 7 |                 16 / 12 | −0.049 to +0.030 |           +9.0 % |
| `step5@0.5-losing`    |              28 |                   21 / 7 |                 16 / 12 | −0.042 to +0.025 |           +7.6 % |
| `step10@0.5-losing`   |              28 |                   20 / 8 |                 15 / 13 | −0.038 to +0.039 |           +5.0 % |
| `late15m-entry`       |               0 |                    1 / 0 |                      -- | --               |               -- |
| `late15m-bar-extreme` |               9 |                   13 / 0 |                   9 / 0 | −0.008 to −0.002 |           +0.0 % |
| `late15m-atr`         |               0 |                    0 / 2 |                      -- | --               |               -- |
| `late30m-entry`       |              30 |                   9 / 23 |                 19 / 11 | −0.003 to +0.004 |           +0.0 % |
| `late30m-bar-extreme` |              32 |                  21 / 10 |                  28 / 4 | −0.013 to +0.003 |           +0.1 % |
| `late30m-atr`         |              29 |                  14 / 11 |                  21 / 8 | −0.008 to +0.001 |           +0.0 % |
| `late60m-entry`       |              33 |                  14 / 19 |                 21 / 11 | −0.014 to +0.011 |           +0.1 % |
| `late60m-bar-extreme` |              32 |                  11 / 21 |                  28 / 4 | −0.024 to +0.012 |           +0.8 % |
| `late60m-atr`         |              30 |                  12 / 17 |                  27 / 3 | −0.013 to +0.003 |           +0.2 % |
| `breakeven@0.5R`      |              28 |                   20 / 8 |                 17 / 11 | −0.040 to +0.028 |           +6.5 % |
| `breakeven@1R`        |              27 |                   19 / 9 |                 15 / 12 | −0.014 to +0.010 |           +2.0 % |

- **The market exits repeat §M48's split.** The excursion exit at bars 3 and 5 costs in most held-out cells; at bar 20, and at bar 10 for 0.5 R, it gains more often held out while costing on the selection window, which is the window's sign §M48 found on EmaPullback rather than a rule that works. The minute-timed forms cost in both windows, and every market exit adds trades, up to a median of 27% more.
- **Closing only losers costs when the bar for a loser is shallow.** The `losing` arms close a position whose close is worse than its entry at 15, 30 or 60 minutes. They cost in 22 to 27 of their bound held-out cells, by up to 0.116, which is how §M48's 0 R rung behaved rather than its −0.5 R one.
- **The invalidation exit gains about as often as it costs**, 13 to 11 held out, and **"only if losing" changes no configuration held out**: a close beyond the signal bar's far extreme is a losing close unless the entry filled beyond it too. On the selection window it changes some configurations in 4 cells, all at 10 minutes on EmaCrossover and EmaPullback, and the median in none.
- **A stop moved toward the entry with age costs more often than it gains, in both windows.** Every step and line costs on the selection window in 20 to 29 of its bound cells and held out in 15 to 24, and frees the position early enough to add 5% to 17% more trades. "Only while losing" returns almost the same figures as the plain step.
- **The late stop barely moves anything.** Held out it moves profit factor by at most 0.024 in any cell, and trade counts by under 1%. It costs held out more often than it gains at every level, having gained more often on the selection window at four of the six bound settings.
- **The last-15-minute late stops are untested.** At 15 minutes they never change the bar a trade leaves on, and at 10 minutes only the bar-extreme form does, in 9 of 36 cells. They still move the exit price on the bar the trade leaves on, by at most 0.009 of profit factor anywhere, so "untested" is the pre-registered rule's word for them, not a claim that they do nothing.
- **The breakeven stop costs more often than it gains in both windows**, and **never binds on InsideBar**: its stored grid puts the target 1 ATR from the fill and the stop 5 to 20 ATRs beyond the inside bar, so the target is reached long before 0.5 R. On InsideBarTrailing it binds at 0.5 R in a third of its paired rows and at 1 R in none.
- **DeadCatBounce and PullBackAndGo are untested by most of the bar-timed arms**, as predicted: they hold two to three bars, which is where the 28 in the second column comes from.
- **The two windows agree on the sign of an arm's effect in 66% of 1,672 arm × cell pairs**, against §M48's 65%.

## The four contrasts

Read the same way, one arm against another, as description. A count is of the 36 unfiltered held-out cells, where the second arm is better / worse.

- **"Only if losing" against the plain step**: worse more often than better, 5 / 21, 7 / 17 and 6 / 16 at bars 3, 5 and 10, by at most 0.008. On the invalidation exit it changes nothing held out, above.
- **The minutes form against bar 3**: 15 minutes, which is one or two bars here, costs more than bar 3 in 34 of 36 cells; 30 minutes is worse in 15 and better in 3, with a median of zero; 60 minutes is better in 21 and worse in 14.
- **The line against the step, both reaching the entry at bar 10**: even, 16 / 17, with a median of zero.
- **The late stop's three levels**: the bar's extreme costs more than the entry, worse in 29, 32 and 28 cells at 15, 30 and 60 minutes, and 1 ATR sits between the two. None of the differences exceeds 0.022.

## The two midday cells

**InsideBarTrailing's midday cell clears at neither bar size read**: every pick on both roots loses held out at 10 and at 15 minutes. The arms that gain there held out lost on the selection window: at 10 minutes the half-way steps at bars 5 and 10 gain +0.017 to +0.026 held out, as the median of the two roots, and lose 0.001 to 0.002 on the selection window. **The cell is traded at 5 minutes, which has not been run.**

**OpeningRange's midday cell clears nowhere**: every pick loses held out, by 0.014 to 0.032, and no arm gains more than +0.010 there held out on the median of the two roots.

## The predictions

| #   | stated before any row was read                                                                                                                                                        | what came back                                                                                                                                 |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | The control reproduces the stored rows exactly                                                                                                                                        | **Right**: 61,568 rows, none differing                                                                                                         |
| 2   | The market exits repeat §M48's split: an arm that can close a winner costs held out in a majority of cells, and one closing only losers moves profit factor by less than 0.05 in most | **Right**: the excursion arms cost in 208 of 346 bound held-out cells, and the loss-only arms move less than 0.05 in 131 of 154, at most 0.116 |
| 3   | The invalidation exit is unbound on DeadCatBounce and PullBackAndGo, and "only if losing" barely changes it where it binds                                                            | **Right**: bound in none of their cells; the paired delta between the two arms is zero in all 88 cells                                         |
| 4   | The late stop helps InsideBar and costs on OpeningRange, InsideBarTrailing, EmaCrossover and ElasticBand, in a majority of each one's held-out cells                                  | **Wrong for InsideBar**, where it costs in 34 of 36 held-out cells; **right for the four**, at 24, 32, 19 and 22 of 36                         |
| 5   | A stop moved to the entry costs more than one moved half way, in a majority of cells                                                                                                  | **Right**, narrowly: 59 of 108 held-out cells                                                                                                  |
| 6   | The selection window's pick pays on both roots in no more than a few of the 33 cells                                                                                                  | **Right** for the 22 read: 1                                                                                                                   |

## Gates 1 and 2

**Gate 1 does not rise anywhere unfiltered.** The control has a majority of configurations profitable on the selection window in 2 EmaCrossover cells, 4 EmaPullback and 1 OpeningRange, and none elsewhere; no arm raises any of them, and most of the market exits lower them. **At midday it moves both ways**: InsideBarTrailing's control has 3 of 4 cells, which no arm raises, while on OpeningRange, where the control has none, five arms reach 2 and three reach 3, and those three all lose held out there.

**Gate 2 moves in most root × stratum cells, in both directions.** Where the control passes, on EmaCrossover, InsideBar, OpeningRange unfiltered and InsideBarTrailing's midday NQ, between 2 and 19 arms fail; where it fails, on EmaPullback, SqueezeBreakout, InsideBarTrailing unfiltered, InsideBarTrailing's midday MNQ and PullBackAndGo's NQ, between 1 and 19 arms pass. OpeningRange's midday cell passes on both roots under every arm. Gate 2 is `tools/campaign_holdout.py`'s shortlist pooled over resolutions and base variants, which the paired read keeps apart, so the two can disagree and neither is the verdict.

## What this settles, and what it does not

- **At 10 and 15 minutes, #369's second tier rescues no archetype.** Moving the stop with age or to breakeven costs more often than it gains in both windows, and before the close it costs more often held out at every level, having gained more often on the selection window at four of its six bound settings; the market exits repeat §M48; and the one cell that clears does so by 0.004 with its configurations still losing.
- **EmaPullback's breakeven cell is a candidate for [#354]'s re-read and nothing more**, as the pre-registration says of any cell that clears. At 15 minutes the same archetype picks something else, which costs.
- **Not run**: the 5-minute pass, above, and 2 minutes; the prop-account replay of the picks, which §M48 ran after its verdict and which was not pre-registered here; #369's third tier; and any stratum but the two.

## How it was read

From the stored rows alone: every arm is a variant named `<base variant> exit2=<arm>`, in each archetype's campaign database under `results/campaign/`. A delta is the median, over configurations with at least 30 trades in both arms, of the treatment's profit factor minus the control's, paired with `tools/campaign_paired.py`'s functions and keyed on the base variant; "bound" is `tools/campaign_hold.py`'s `bound_share` on average bars held. Gate 2 is `tools/campaign_holdout.py`'s verdict, run once per arm. **`tools/campaign_early_exit.py --set early-exit-2` reproduces the verdict (`--picks`) and the control's reproduction (`--reproduce`)**; the per-arm table, the contrasts, gate 1 and the counts behind the predictions were computed from the same functions by a local script. The trade figures are each cell's ratio of the two arms' median trade counts, then the median over cells.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#351]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/351
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#430]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/430
