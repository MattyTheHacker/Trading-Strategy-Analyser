---
id: M29
title: "M29 — the maximum hold time: the one axis whose best value is off on every archetype"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [292]
gates: [1, 2]
outcome: negative
verdict: >-
  Capping a trade's length is a cost on all seven archetypes and the cost is monotone in the cap; the selection window picks a paying rung zero times in seven, and the two ported archetypes hold too briefly to reach one at all.
---

# M29 — the maximum hold time: the one axis whose best value is off on every archetype ([#292])

**The capability was the request; this is what it returned.** [#292] asked for a limit on how long a trade can last, and for a sweep to say whether one helps. The rules the cap implements, and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) § "The maximum hold time, and why it is its own exit code".

Nothing in the registry had one before except ElasticBand, whose scheme C shipped `max_hold_bars` at §M26 and whose campaign grids have swept it at `[0, 30]` ever since. **That axis is the only prior measurement, and it was never read**: §M26.5 put its η² at 0.0070 and 0.0004 on the two windows, §M26.6 at 0.0030 and 0.0000, §M26.8 at 0.0008 and 0.0020 — four separate campaigns reporting it as the smallest thing on the table and none of them asking what its sign was.

## What was run

**341,760 rows**: every archetype's stored §M27 campaign grid, re-emitted once per rung of a five-step ladder plus the uncapped control — `max_hold_bars` at 0, 5, 10, 20, 40 and 80 bars — on both roots, resolutions 1/2/5/10/15, split 60/40 into a selection and a held-out window, at the root's own commission and one tick of slippage, unfiltered stratum only. 99.1% of rows clear 30 trades. 40.7 minutes of wall clock.

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants hold --split --strata hold --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_hold.py --strategy <name> --window holdout
```

**The cap is a variant dimension and not an axis, and that is what makes the reading paired.** Each rung carries §M27's axes unchanged, so every arm holds exactly the same number of combinations and two rows differ by the cap and by nothing else. A treatment arm with axes of its own would have made its shortlist a best-of-more — the bias [`sweep-and-context.md`](../../.claude/rules/sweep-and-context.md) records as sitting *in the design rather than in the data*, measured at §M27 on EmaCrossover's trailing arm. `tools/campaign_paired.py` is the instrument, with the base variant added to its cell key so the ladder pairs inside each of them.

**The ladder is a bar count and is never pooled across resolutions.** Twenty bars is twenty minutes at one resolution and five hours at another, which is the confound a raw regime threshold has (§M27.5); the remedy is the same one — every reported row is a single root × resolution, and `hold_minutes` is printed beside `hold_bars`. The top of the ladder is deliberately past where the session flatten binds at the coarse resolutions.

### The control arm reproduces §M27 exactly, which is the strongest check this change has

The `hold=0` arm is the stored configuration re-run, so it is also a regression test far wider than the trade-log gate — which covers DeadCatBounce alone. Joined on every parameter, root, resolution and window:

| archetype         | paired rows | rows differing on trades, net P&L, profit factor, average hold or session-close share |
| ----------------- | ----------: | ------------------------------------------------------------------------------------: |
| DeadCatBounce     |       5,760 |                                                                                 **0** |
| PullBackAndGo     |       3,840 |                                                                                 **0** |
| EmaCrossover      |      20,480 |                                                                                 **0** |
| InsideBar         |       8,640 |                                                                                 **0** |
| InsideBarTrailing |       8,640 |                                                                                 **0** |
| OpeningRange      |       3,840 |                                                                                 **0** |

**51,200 rows, no differences.** ElasticBand is absent because its stored campaign rows sweep `max_hold_bars` as an axis and so have no uncapped twin to join to; the OpeningRange join drops `follow_through_scaling` and `follow_through_sessions`, which §M28.10 added after those rows were written and which read null in them.

## The ladder is a cost, and the cost is monotone in the cap

Median within-cell change in profit factor against the uncapped arm, over the ten root × resolution cells:

### Selection window

| archetype         | 5 bars |  10 bars | 20 bars |  40 bars | 80 bars |
| ----------------- | -----: | -------: | ------: | -------: | ------: |
| DeadCatBounce     | −0.001 | +0.000\* |   0.000 |    0.000 |   0.000 |
| PullBackAndGo     | −0.005 |   −0.000 |   0.000 |    0.000 |   0.000 |
| InsideBar         | −0.060 |   −0.033 |  −0.002 |   −0.001 |  −0.002 |
| InsideBarTrailing | −0.046 |   −0.024 |  −0.005 | +0.000\* |  −0.000 |
| EmaCrossover      | −0.070 |   −0.044 |  −0.024 |   −0.010 |  −0.002 |
| ElasticBand       | −0.059 |   −0.037 |  −0.027 |   −0.010 |  −0.004 |
| OpeningRange      | −0.120 |   −0.106 |  −0.072 |   −0.041 |  −0.001 |

\* +0.0004 and +0.0005 respectively — the only two non-negative entries in the table, and both are a rounding artefact rather than an effect.

**Read the rows left to right.** On all five original archetypes the cost shrinks monotonically as the cap loosens and reaches zero only where the cap stops binding. That is the shape of an axis whose best value is its off value: there is no interior optimum to find, and the ladder is measuring how much damage a cap does rather than how much good.

### Held out

| archetype         | 5 bars | 10 bars | 20 bars | 40 bars | 80 bars |
| ----------------- | -----: | ------: | ------: | ------: | ------: |
| DeadCatBounce     | +0.004 |   0.000 |   0.000 |   0.000 |   0.000 |
| PullBackAndGo     | +0.008 |  −0.000 |   0.000 |   0.000 |   0.000 |
| InsideBar         | −0.038 |  −0.014 |  −0.010 |  −0.019 |  +0.010 |
| InsideBarTrailing | −0.057 |  −0.018 |  −0.025 |  −0.006 |  −0.000 |
| EmaCrossover      | −0.048 |  −0.027 |  −0.014 |  −0.005 |  −0.003 |
| ElasticBand       | −0.048 |  −0.037 |  −0.037 |  −0.030 |  −0.029 |
| OpeningRange      | −0.031 |  −0.013 |  +0.005 |  −0.002 |   0.000 |

**The four positives are each contradicted by the window that would have had to choose them.** OpeningRange at 20 bars reads +0.005 held out and −0.072 on selection; InsideBar at 80 reads +0.010 against −0.002; the two ports' 5-bar entries read +0.004 and +0.008 against −0.001 and −0.005. Every one is a maximum picked on the test window, which is the thing §M28.13 exists to stop being quoted.

**Ranking on net-to-drawdown instead of profit factor does not change the sign anywhere it matters** — held out, the 5-bar rung costs EmaCrossover 0.293, ElasticBand 0.233, InsideBarTrailing 0.142 and InsideBar 0.113, and only DeadCatBounce's +0.002 is positive.

## Would the selection window have picked a rung that pays? Zero times in seven

Taking each archetype's best-scoring rung on the selection window among those that bind, and reading what it returned held out:

| archetype         | rung picked | selection Δ | held-out Δ | held out on both roots at |
| ----------------- | ----------: | ----------: | ---------: | ------------------------: |
| DeadCatBounce     |          10 |     +0.0004 |     0.0000 |          2 of 5 bar sizes |
| PullBackAndGo     |          10 |     −0.0000 |    −0.0001 |          2 of 5 bar sizes |
| InsideBar         |          40 |     −0.0014 |    −0.0190 |          1 of 5 bar sizes |
| InsideBarTrailing |          40 |     +0.0005 |    −0.0056 |          1 of 5 bar sizes |
| EmaCrossover      |          80 |     −0.0015 |    −0.0028 |          0 of 5 bar sizes |
| ElasticBand       |          80 |     −0.0039 |    −0.0292 |          0 of 5 bar sizes |
| OpeningRange      |          80 |     −0.0007 |     0.0000 |          1 of 5 bar sizes |

**Not one archetype's selection-window choice pays held out**, and the same table computed on net-to-drawdown gives the same answer. **And of the 58 archetype × rung × window rows in which the cap binds at all, zero have all five bar sizes agreeing on both roots that it helped** — the agreement standard §M28.16 used. 50 of those 58 have a negative median.

**It lowers the ceiling as well as the median.** The best cell in each arm falls too, by 0.20 on EmaCrossover, 0.37 on ElasticBand and 0.11 on InsideBar at the tightest rung: the cap is not trimming a tail of bad configurations, it is removing the good ones.

## The mechanism — it does exactly what it is asked to, and that is the problem

Held out, median across every cell, control against the capped arm:

| archetype         | average hold, uncapped | at 5 bars |  at 20 bars | trades at 5 bars | session-close share, uncapped | at 5 bars |
| ----------------- | ---------------------: | --------: | ----------: | ---------------: | ----------------------------: | --------: |
| DeadCatBounce     |                    2.0 |       1.9 | 2.0 (inert) |            +0.0% |                         0.007 |     0.007 |
| PullBackAndGo     |                    3.0 |       2.7 | 3.0 (inert) |            +0.1% |                         0.010 |     0.010 |
| InsideBar         |                   18.3 |       3.9 |         8.9 |           +26.4% |                         0.074 |     0.000 |
| InsideBarTrailing |                   33.2 |       5.6 |        15.5 |           +48.3% |                         0.103 |     0.014 |
| EmaCrossover      |                   23.6 |       4.5 |        10.9 |           +39.3% |                         0.074 |     0.011 |
| ElasticBand       |                   31.6 |       4.8 |        12.5 |          +218.1% |                         0.128 |     0.006 |
| OpeningRange      |                   31.5 |       4.9 |        13.1 |           +19.7% |                         0.227 |     0.005 |

**The cap works.** It cuts the average hold by a factor of six or seven, and it very nearly eliminates the forced flat — OpeningRange's session-close share falls from 22.7% of legs to 0.5%. It also turns the book over far faster: ElasticBand takes **three times as many trades**.

**That last column is the whole result.** Each of those extra trades pays a full round trip, and the cap has bought nothing in exchange — it exits at whatever price the next bar opens at, which is uninformative by construction. So the ladder converts held time into commission, and the conversion is a loss at every rung.

**This is the answer to a question §M28.12 left open, and it is the opposite of the hoped-for one.** That campaign found InsideBar's forced flat losing on every shortlisted configuration and handing back about 90% of what the bracket earns — which reads like an invitation to close the position *earlier*, on a rule of one's own, rather than let the clock do it. Measured here: replacing the flatten with a time cap is worse than the flatten. The problem is not that the position is closed by a clock; it is that it is closed by something that knows nothing about price.

## The two ported archetypes cannot reach the cap at all

DeadCatBounce and PullBackAndGo hold for a median of 2.0 and 3.0 bars, so at 20 bars and above **the cap never binds on a single cell** and the arm is byte-identical to its control — the ladder returns exactly 0.000 there, which is the check that an arm that cannot fire reads as its control. Their ratcheting stop has already closed the position long before any cap could.

**So for those two the finding is narrower than for the rest**: the cap is untested above 10 bars rather than measured and rejected, because there is nothing there to measure.

## What this cannot say

- **It is one shape of time stop.** `max_hold_bars` is an unconditional cap: at bar *N* the position leaves at the next open whatever it is doing. **A conditional time exit is a different rule and is not tested here** — "leave if not in profit by bar *N*", or "leave if the excursion has not moved", would exit the same trades on a criterion that reads price, which is precisely what this one is missing. The result below is evidence against the unconditional form and says nothing about the conditional one.
- **The unfiltered stratum only.** Every context cell is unmeasured, and §M28.14 is the precedent for a rule that is inert pooled and live in one stratum.
- **The p-values `tools/campaign_hold.py` prints are not independent-sample p-values, and are not quoted above.** A cell holds 192 to 1,024 combinations of one strategy on one series, so the sign test's null — a fair coin over cells — is wrong by orders of magnitude. The effect size and the root × resolution agreement are what carry the reading; the p column is there because the tool it reuses reports it.
- **Five rungs is a coarse ladder** and the monotone shape is read off five points. What it rules out is an interior optimum large enough to matter, not one worth 0.005.
- **No matched null, and gate 3 does not apply.** The cap is not an entry rule; its control is the same strategy uncapped, which is a stronger comparison than a random entry rather than a weaker one.

## Two traps this campaign walked into, both now fixed

**An axis beats the base it is crossed with, silently.** The first pass ran ElasticBand's six arms against a grid that swept `max_hold_bars` at `[0, 30]` itself, so the axis overrode every arm's base and six identical arms were produced and reported as an inert ladder. Nothing raises: the arms differ in name and in nothing else. `_held` now drops the axis from the arms it builds. **Check the stored grid for the parameter a variant dimension is about to set** — `dead_axes` sees an axis nothing reads, never a base nothing reads.

**`tools/campaign_paired.py`'s exact sign test overflowed above 1,023 pairs.** `2.0 ** total` is `inf` in float64 there, so a cell holding a whole grid raised `OverflowError` rather than returning a p-value. Nothing had reached it because no previous pair had that many cells. The division now stays in integers until the last step; the quotient is always in [0, 1].

[#292]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/292
