---
id: M48
title: "M48 — the conditional early exit: exits that can close a winner cost, and the one sizeable held-out gain is at a bar size the candidate is not traded at"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369]
gates: [1, 2]
outcome: mixed
verdict: >-
  Pre-registered and run: 13 of 44 cells clear the bar, the selection window's pick paying held out on both roots at p < 0.05, but seven of them by less than 0.005 of profit factor on a root, which a sign test over configurations sharing their trades calls significant; exits that can close a winner cost in both windows, the loss-only and before-close forms move almost nothing, and the one gain above 0.01 on both roots with one arm, outside the two archetypes not to trade, is the trend exit in InsideBarTrailing's midday cell at 10 minutes, +0.071 and +0.084 held out, where at 5 minutes, the bar size the cell is traded at, the same exit costs.
---

# M48 — the conditional early exit: exits that can close a winner cost, and the one sizeable held-out gain is at a bar size the candidate is not traded at ([#369])

**Every bar below was fixed before any row was read**, in [`m48-early-exit-preregistration.md`](m48-early-exit-preregistration.md); this file is what the run returned. [#395] builds four conditional early exits, and this campaign runs 26 arms of them against a control with every rule off, over every archetype's stored grid at 2, 5, 10 and 15 minutes, both roots, the 60/40 selection and held-out windows, unfiltered and in `phase=MIDDAY` for InsideBarTrailing and OpeningRange. **3,086,208 combinations unfiltered in 292.5 minutes and 259,200 at midday in 20.3 minutes**, on twelve workers, at the root's own commission and one tick of slippage.

## The control reproduces §M44 exactly

Every `exit=off` row joined to the stored §M44 row with the same base variant, parameters, root, resolution, window and stratum, and compared on every stored statistic:

| archetype         | rows joined | unmatched | rows differing |
| ----------------- | ----------: | --------: | -------------: |
| DeadCatBounce     |       4,608 |         0 |          **0** |
| PullBackAndGo     |       3,072 |         0 |          **0** |
| EmaCrossover      |      16,384 |         0 |          **0** |
| EmaPullback       |      36,864 |         0 |          **0** |
| InsideBar         |       6,912 |         0 |          **0** |
| InsideBarTrailing |      13,824 |         0 |          **0** |
| ElasticBand       |       9,216 |         0 |          **0** |
| OpeningRange      |       5,376 |         0 |          **0** |
| SqueezeBreakout   |      27,648 |         0 |          **0** |

**123,904 rows, no differences**, ElasticBand included this time because its axes are kept. The join leaves out the sizing columns §M45 and §M47 added after §M44, which read null in the stored rows.

## The verdict: 13 of 44 cells clear, and the bar is looser than it reads

In each archetype × resolution cell and on each root, the selection window picks the bound arm with the highest median paired delta; the cell clears if that pick's held-out delta is positive with the sign test at p < 0.05 on both roots.

| archetype         | stratum      | minutes | MNQ pick         | MNQ held out | NQ pick                 | NQ held out |
| ----------------- | ------------ | ------: | ---------------- | -----------: | ----------------------- | ----------: |
| DeadCatBounce     | unfiltered   |       2 | `bars5@0.5R`     |      +0.0002 | `bars3@0.5R`            |     +0.0027 |
| DeadCatBounce     | unfiltered   |       5 | `bars3@0.5R`     |      +0.0053 | `bars3@0.5R`            |     +0.0147 |
| DeadCatBounce     | unfiltered   |      10 | `regime`         |      +0.0582 | `close120m`             |     +0.0206 |
| EmaPullback       | unfiltered   |       5 | `close60m`       |      +0.0024 | `close60m`              |     +0.0035 |
| EmaPullback       | unfiltered   |      10 | `trend-opposed`  |      +0.0155 | `trend-opposed`         |     +0.0093 |
| InsideBar         | unfiltered   |       5 | `close30m`       |      +0.0034 | `trend-opposed`         |     +0.0219 |
| InsideBarTrailing | phase=MIDDAY |      10 | `trend-opposed`  |  **+0.0705** | `trend-opposed`         | **+0.0838** |
| OpeningRange      | unfiltered   |      10 | `trend-not-with` |      +0.0042 | `trend-not-with-losing` |     +0.0022 |
| PullBackAndGo     | unfiltered   |      10 | `close120m`      |      +0.0160 | `regime`                |     +0.1042 |
| PullBackAndGo     | unfiltered   |      15 | `bars3@0.5R`     |      +0.0165 | `bars3@0.5R`            |     +0.0480 |
| SqueezeBreakout   | unfiltered   |       2 | `bars20@-0.5R`   |      +0.0004 | `bars10@-0.5R`          |     +0.0013 |
| SqueezeBreakout   | unfiltered   |       5 | `bars20@-0.5R`   |      +0.0007 | `bars10@-0.5R`          |     +0.0015 |
| SqueezeBreakout   | unfiltered   |      10 | `trend-opposed`  |      +0.0017 | `trend-opposed`         |     +0.0011 |

**The sign test counts configurations, and a cell's 96 to 2,020 configurations share their trades**, so a consistent change of a few ten-thousandths reaches p < 0.0001: DeadCatBounce's 2-minute MNQ pick gains 0.0002 of profit factor. The pre-registration said as much, and seven of the thirteen clear by less than 0.005 on at least one root. **Four clear by more than 0.01 on both roots**, and three of those are DeadCatBounce and PullBackAndGo, the two archetypes [`README.md`](README.md) lists under "What not to trade", two of them with a different arm on each root. **The fourth is InsideBarTrailing's midday cell at 10 minutes**, one arm on both roots, below.

## What each rule does

Counted over the 72 archetype × root × resolution cells unfiltered, only where the arm is bound (its paired rows' average hold moved in at least half of them), and never pooled across bar sizes:

| arm                     | selection: costs / gains | held out: costs / gains | held-out range   | trades, held out |
| ----------------------- | -----------------------: | ----------------------: | ---------------- | ---------------: |
| `bars3@-0.5R`           |                  21 / 30 |                 23 / 30 | −0.013 to +0.006 |           +0.4 % |
| `bars3@0R`              |                  50 / 18 |                 48 / 19 | −0.116 to +0.031 |          +16.6 % |
| `bars3@0.25R`           |                  56 / 12 |                 54 / 15 | −0.140 to +0.024 |          +27.4 % |
| `bars3@0.5R`            |                  60 / 10 |                 58 / 14 | −0.140 to +0.048 |          +31.9 % |
| `bars5@-0.5R`           |                  18 / 35 |                 22 / 32 | −0.013 to +0.006 |           +0.3 % |
| `bars5@0R`              |                   53 / 9 |                 44 / 14 | −0.167 to +0.042 |          +12.6 % |
| `bars5@0.25R`           |                  55 / 10 |                 47 / 15 | −0.127 to +0.030 |          +20.3 % |
| `bars5@0.5R`            |                   59 / 8 |                 49 / 15 | −0.127 to +0.018 |          +25.7 % |
| `bars10@-0.5R`          |                  24 / 32 |                 18 / 34 | −0.011 to +0.011 |           +0.3 % |
| `bars10@0R`             |                   46 / 9 |                 34 / 22 | −0.060 to +0.052 |           +8.7 % |
| `bars10@0.25R`          |                   50 / 6 |                 35 / 21 | −0.081 to +0.037 |          +14.6 % |
| `bars10@0.5R`           |                   53 / 3 |                 36 / 19 | −0.114 to +0.037 |          +17.2 % |
| `bars20@-0.5R`          |                  24 / 28 |                 14 / 39 | −0.017 to +0.006 |           +0.2 % |
| `bars20@0R`             |                  37 / 19 |                 20 / 34 | −0.086 to +0.043 |           +4.7 % |
| `bars20@0.25R`          |                  45 / 11 |                 24 / 32 | −0.089 to +0.042 |           +9.2 % |
| `bars20@0.5R`           |                   47 / 9 |                 28 / 28 | −0.089 to +0.042 |          +10.3 % |
| `close15m`              |                  24 / 23 |                  25 / 9 | −0.007 to +0.001 |           +0.0 % |
| `close30m`              |                  28 / 40 |                 52 / 15 | −0.012 to +0.006 |           +0.2 % |
| `close60m`              |                  43 / 27 |                 47 / 19 | −0.014 to +0.016 |           +0.4 % |
| `close120m`             |                  52 / 19 |                 35 / 35 | −0.038 to +0.025 |           +1.6 % |
| `regime`                |                  61 / 11 |                 52 / 20 | −0.128 to +0.104 |          +31.0 % |
| `regime-losing`         |                  62 / 10 |                 44 / 28 | −0.084 to +0.051 |          +16.1 % |
| `trend-opposed`         |                  32 / 31 |                 19 / 41 | −0.055 to +0.062 |           +6.2 % |
| `trend-opposed-losing`  |                  34 / 27 |                 20 / 39 | −0.055 to +0.038 |           +5.0 % |
| `trend-not-with`        |                  37 / 21 |                 20 / 40 | −0.123 to +0.072 |           +5.4 % |
| `trend-not-with-losing` |                  37 / 20 |                 18 / 39 | −0.123 to +0.072 |           +4.2 % |

- **An exit that can close a winner costs, in both windows.** The not-working exit at a threshold of zero or above, and the regime exit, cost in most cells, more the higher the threshold and the earlier the bar. Each one frees the position for the next signal, which is where up to a third more trades come from.
- **EmaPullback is the exception, and it is the window's sign again.** Every not-working rung at zero or above costs on its selection window, 96 of 96 cells, and gains held out in 70 of 96: the §M37 and §M39 shape, not a rule that works.
- **The loss-only and before-close forms barely move anything.** At −0.5 R the not-working exit stays within 0.017 of its control held out; the before-close exit moves profit factor by at most 0.038 anywhere and adds a median of at most 1.6% of trades, and its 15-minute window is bound in only 38 of 72 held-out cells.
- **The trend exit is the one rule that gains more often than it costs held out**, in 39 to 41 of 60-odd bound cells, against 20 to 31 on the selection window.
- **The two windows agree on the sign of an arm's effect in 65% of 2,288 arm × cell pairs.**
- **DeadCatBounce and PullBackAndGo are untested by most of the not-working ladder**, as predicted: they hold two to three bars, and every rung from 5 bars up is bound in fewer than half their paired rows.

## InsideBarTrailing's midday cell

The cell §M42 and §M45 read is the 5-minute one. The trend exit there, and at every other bar size, paired against the control:

| minutes | MNQ selection | MNQ held out | NQ selection | NQ held out |
| ------: | ------------: | -----------: | -----------: | ----------: |
|       2 |        −0.018 |       −0.040 |       +0.005 |      −0.050 |
|       5 |        +0.032 |       −0.055 |       +0.028 |      −0.064 |
|      10 |        +0.076 |   **+0.071** |       +0.057 |  **+0.084** |
|      15 |        +0.094 |       −0.028 |       +0.053 |      −0.018 |

**At 10 minutes the gain is broad**: 96% of MNQ configurations and 100% of NQ ones improve held out, trades rise by 2%, and the median held-out profit factor moves from 0.914 to 0.997 on MNQ and from 0.958 to 1.067 on NQ, so the exit takes the cell from a loss to about break-even rather than to a profit. **At 5 minutes, where the cell is traded, it costs on both roots held out**, and at 15 minutes it wins the selection window and loses the holdout. `trend-opposed-losing` returns the same figures as `trend-opposed` at 10 and 15 minutes.

**OpeningRange's midday cell clears nowhere**: every pick loses held out, by 0.001 to 0.030.

## The predictions

| #   | stated before any row was read                                                                     | what came back                                                                                 |
| --- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 1   | The control reproduces the stored rows exactly                                                     | **Right**: 123,904 rows, none differing                                                        |
| 2   | The median arm's trade count is within 10% of the control's in most cells                          | **Right**: 47 of 72 held-out cells, 40 of 72 on the selection window                           |
| 3   | Exits that can close winners cost on OpeningRange, InsideBarTrailing, EmaCrossover and ElasticBand | **Right**: they cost in 81%, 69%, 88% and 57% of those archetypes' held-out cells              |
| 4   | "Only if losing" beats its unconditional twin in most cells, most clearly on InsideBar             | **Wrong**: 43% of 216 held-out cells; InsideBar 12 of 24, SqueezeBreakout clearest at 17 of 24 |
| 5   | The before-close exits move held-out profit factor by less than 0.05 in most cells                 | **Right**: all 288, at most 0.038                                                              |
| 6   | The selection window's pick pays on both roots in no more than a few of the 44 cells               | **Wrong**: 13, though seven by less than 0.005 on a root                                       |

## Gates 1 and 2

**Gate 1 moves on one archetype.** The control has a majority of configurations profitable on the selection window in 2 EmaCrossover cells, 5 EmaPullback, 1 InsideBar and 3 OpeningRange, and none elsewhere. No arm raises that anywhere except OpeningRange, where `trend-not-with`, `trend-not-with-losing` and `bars3@-0.5R` reach 4; the arms that close winners lower it.

**Gate 2 moves in a few root × stratum cells, both ways.** InsideBarTrailing's midday cell fails it on MNQ under the control and passes under eight arms that close winners, while the trend arms fail it on NQ where the control passes. Gate 2 is `tools/campaign_holdout.py`'s shortlist pooled over resolutions and base variants, which the paired read keeps apart, so the two can disagree and neither is the verdict.

## What this settles, and what it does not

- **The conditional form of §M29's lever, as a market exit, rescues no archetype.** Closing winners early costs, as §M28.12 said it would; closing only losers, at a threshold or before the close, changes almost nothing; and the pre-registered verdict clears mostly by amounts no account would register.
- **InsideBarTrailing's trend exit at 10 minutes is a candidate for [#354]'s re-read, not a change to the candidate.** It is one bar size of four, it costs at the one [#344] trades, and it has had no exclusion test, gate 4 or prop replay. It would also need porting: the trend label has no NinjaScript yet, so every row with it on is `TIER1_ONLY`.
- **Not tested here**: a stop that moves — breakeven ([#351]), a trail to structure ([#352]) or a stop tightening with age or before the close; #369's second and third tiers; any stratum but the two; and the prop replay, which the pre-registration did not name.

## How it was read

From the stored rows alone: every arm is a variant named `<base variant> exit=<arm>`, in `results/campaign/<Archetype>.duckdb`. A delta is the median, over configurations with at least 30 trades in both arms, of the treatment's profit factor minus the control's, paired with `tools/campaign_paired.py`'s functions and keyed on the base variant as `tools/campaign_hold.py` keys the hold ladder; "bound" is that tool's `bound_share` on average bars held. Gate 2 is `tools/campaign_holdout.py`'s verdict, run once per arm. The reads were run by a local script over those functions rather than a committed tool.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#351]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/351
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#395]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/395
