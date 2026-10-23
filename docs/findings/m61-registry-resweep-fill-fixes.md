---
id: M61
title: "M61 — every older campaign re-read on the October 2026 re-sweep, after the fill fixes"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [439]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  Written in sections; the verdict is set once every section is in.
---

# M61 — every older campaign re-read on the October 2026 re-sweep, after the fill fixes ([#439])

The second re-sweep of every stored campaign. §M44 re-swept the registry onto a repaired archive; since then four fixes to how orders fill have changed rows in every archetype, so no stored control could reproduce itself and [#439] re-swept them all again before any new campaign ran. The campaigns pre-registered before the run have result files of their own. This file re-reads the headline of every campaign that ran before it, on the new rows, against the figures each one published.

## In plain terms

In October 2026 four mistakes in how the backtester fills orders were fixed, each found by checking against NinjaTrader itself. Three of the four affect stops, which every strategy uses. So every stored result was re-run on the corrected code, on the same price history as before.

The fixes moved most results by very little: the typical setting's profit factor changed by less than 0.01 on seven of the nine strategies. The two that moved more are the two that enter on a stop order at a level, OpeningRange and SqueezeBreakout, and both moved up.

The question this file answers is whether anything the project concluded before the re-run still holds. Each older campaign's main claim is re-measured the way it was first measured and set beside its original figure.

## What changed since §M44

**The bars did not.** The archive is the one §M44 repaired, beginning 2020-10-26 on both roots and ending 2026-09-18, and the selection window still ends on 2024-05-13 on MNQ and 2024-05-10 on NQ. The re-sweep's first part re-ran exactly the cells the databases held on 2026-10-16, and all 104,456 of them ran on the same bars as their stored twins (`tools/resweep.md`).

**What did is how four things fill**, each measured against NinjaTrader and recorded in `docs/nt8-fidelity.md`:

- **A limit order the market has passed fills at the nearest price the bar traded** ([#453]), where every target had filled at its own price. It reaches every archetype's targets, and OpeningRange's two limit entries ([#454]). It replaced [#451]'s narrower rule, which closed such a leg of ElasticBand's at the entry bar's open.
- **Stops snap to the tick grid** ([#471]), as targets already did. EmaCrossover's, EmaPullback's and ElasticBand's stops moved, and OpeningRange's and SqueezeBreakout's ATR and range-fraction stops. A stop that is a bar extreme plus whole ticks was already on the grid.
- **A stop on its entry bar is read along the bar's path** ([#472]): open, the nearer extreme, the other, the close, with each entry's stop seeing only the path after its own fill. It reaches every stop entry: DeadCatBounce, PullBackAndGo, OpeningRange's breakout and fade, SqueezeBreakout and EmaPullback's confirmation entry.
- **A limit entry that gaps past its own stop exits at the open** ([#455], in [#472]), where it had exited at a stop price outside its bar. It reaches OpeningRange's retest and rejection.

Against the stored rows, cell by cell (one cell is one archetype × root × resolution × window × variant × stratum, read at its median configuration):

| archetype         | cells  | cells with a changed row | median change in profit factor, changed cells | changed cells whose median rose | median change in trades |
| ----------------- | ------ | ------------------------ | --------------------------------------------- | ------------------------------- | ----------------------- |
| OpeningRange      | 41,440 | 90.5%                    | **+0.040**                                    | 89%                             | −2.5%                   |
| SqueezeBreakout   | 14,192 | 96.7%                    | **+0.014**                                    | 88%                             | −0.6%                   |
| PullBackAndGo     | 3,226  | 85.2%                    | +0.009                                        | 89%                             | 0.0%                    |
| InsideBarTrailing | 13,354 | 3.9%                     | +0.009                                        | 94%                             | 0.0%                    |
| DeadCatBounce     | 3,364  | 86.5%                    | +0.005                                        | 87%                             | 0.0%                    |
| InsideBar         | 3,610  | 6.3%                     | +0.003                                        | 86%                             | 0.0%                    |
| ElasticBand       | 12,856 | 97.5%                    | −0.001                                        | 16%                             | 0.0%                    |
| EmaCrossover      | 6,980  | 76.8%                    | −0.001                                        | 19%                             | 0.0%                    |
| EmaPullback       | 5,434  | 96.7%                    | −0.002                                        | 9%                              | 0.0%                    |

**Each archetype moved in the direction its fix points.** The two stop entries at a level gain most and trade less: the old rule for a bar holding both the fill and the stop booked the stop whenever the open lay on the stop's side, which for a stop entry it does, and reading the bar along its path books it only when the path after the fill reaches it (`docs/nt8-fidelity.md`, "A stop on its entry bar is read along the bar's path"). The ported stop entries gain a little. The three archetypes whose stops moved onto the tick grid lose a little. InsideBar and InsideBarTrailing changed only where a target was gapped through, in about one cell in twenty. 3,459 cells' median configurations crossed a profit factor of 1.0 in one direction or the other, 2,760 of them OpeningRange's and 451 SqueezeBreakout's.

**Thirty minutes became a campaign bar size** after the run started ([#479]), and every campaign grid was swept at it. **One minute is still running**: the re-sweep's last part sweeps every set at 1 minute, and nothing here reads it beyond the whole-series campaign grid at 1 minute, which the first part ran. **And the campaign grids were swept on five more roots**, ES, MES, GC, MGC and SI, which the gold strata below read.

## How each campaign was re-read

**By its own tool, at its own bar sizes, on its own roots.** Each figure below comes from the read that produced the original, run on the re-swept rows: `tools/campaign_report.py` for the whole-series tables, `tools/campaign_holdout.py`'s verdict for gate 2, `tools/campaign_null.py` for gate 3, and `tools/campaign_gates.py` and the prop tools for gate 4 and the accounts. Every shortlist is ranked within the archetype's own campaign variants unless the campaign read a variant set of its own, and every read is held to the bar sizes and the roots the campaign first used, so the 30-minute rows sit beside it rather than inside it.

**Every gate-3 re-run in this file ran in one batch for it**, at each campaign's own shortlist size, draw, roots and bar sizes, with 200 draws each except §M7a's 500. That is 5,424 tests, none refused for want of a draw.

**A difference has two causes for most campaigns, and this file separates them only where §M44 already did.** Every campaign before §M44 measured a series about 30% shorter than the one §M44 repaired, which began in 2022 rather than 2020. So a figure set beside one of theirs moved for the archive as well as for the fills. The part-one table above isolates the fills alone, against §M44's rows on the same bars.

## The registry

### §M27 — the registry campaign

Six archetypes, every axis each owns, the whole series and the selection/holdout split ([`m27-registry-campaign.md`](m27-registry-campaign.md)). **Every gate reads as it did, except gate 1, which loses one archetype.**

| claim                                                                      | §M27                                    | re-swept                                                                 |
| -------------------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------ |
| gate 1: a majority profitable in some root × resolution cell, 1–15 minutes | 4 of 6                                  | **3 of 6**: EmaCrossover 59.6%, InsideBar 74.8%, InsideBarTrailing 58.8% |
| η² of the bar size, unfiltered                                             | 0.76 IB, 0.56 DCB, 0.47 PBG, 0.34 EC    | 0.76 IB, 0.50 DCB, 0.53 PBG, 0.36 EC                                     |
| InsideBarTrailing's largest axis                                           | trailing multiplier, 0.46               | trailing multiplier, 0.50                                                |
| ElasticBand's two largest                                                  | resolution 0.14, stop mode 0.12         | stop mode 0.20, resolution 0.17                                          |
| the largest moving-average axis                                            | below 0.04, below the root on 4 of 6    | 0.030 (EmaCrossover's slow period), below the root on all six            |
| bar size, median configuration                                             | DCB, PBG, EC monotone; inside bars at 5 | EC monotone; **DCB and PBG peak at 10 and fall at 15**; inside bars at 5 |
| gate 2: InsideBar                                                          | passes both roots, 19 of 20 profitable  | passes both, 20 and 20                                                   |
| gate 2: EmaCrossover                                                       | passes both roots, 15 of 20             | passes both, 11 and 14                                                   |
| gate 2: InsideBarTrailing                                                  | marginal, barely above 1.0              | passes on MNQ at 1.048, fails on NQ at 0.995                             |
| gate 2: ElasticBand, selection → holdout                                   | 1.834 → 0.592; 1 and 0 of 20 profitable | 1.491 → 0.710 and 1.620 → 0.693; 0 and 0                                 |
| gate 2: InsideBar `regime=DIRECTIONAL`                                     | 20 of 20 on both; median above 1.0      | 20 of 20 on both; medians 1.198 and 1.155                                |
| the same at 10 minutes, every configuration                                | 99.7% profitable, CONSOLIDATING 6.1%    | 100% of 864, CONSOLIDATING 13.9%                                         |
| gate 4: InsideBar unfiltered at 5 minutes, median net-to-drawdown          | below a third                           | 0.397                                                                    |
| gate 4: cells of the four held out where most return their drawdown        | `DIRECTIONAL` at 10 minutes, 60%        | the same cell alone, 68%, median 1.29                                    |

**DeadCatBounce and PullBackAndGo no longer improve with every step up in bar size.** Their median configuration peaks at 10 minutes, 0.915 and 0.894, and falls back to 0.778 and 0.836 at 15; EmaCrossover still rises at every step, to 1.005 at 15. **InsideBar's `regime=CONSOLIDATING` cell now passes gate 2 on NQ**, with 11 of 20 profitable, where §M27 had it as the mirror image of `DIRECTIONAL` at 2 of 20; on MNQ it still fails. §M27 does not name its four gate-1 passes, so which archetype dropped out cannot be read from the file; the best cells of the other three are DeadCatBounce's 28.5%, PullBackAndGo's 34.9% and ElasticBand's 22.0%.

Gate 3, the configuration the selection window ranks first on each root, against its matched null on the holdout:

| archetype         | §M27                                       | MNQ excess, p | NQ excess, p  | trades, MNQ / NQ |
| ----------------- | ------------------------------------------ | ------------- | ------------- | ---------------- |
| InsideBar         | +0.17 and +0.14, p ≈ 0.08 and 0.16         | +0.162, 0.080 | +0.174, 0.060 | 1,895 / 1,853    |
| EmaCrossover      | +0.03 and +0.05                            | +0.097, 0.438 | −0.025, 0.846 | 395 / 442        |
| InsideBarTrailing | within 0.005 of its null                   | +0.041, 0.537 | +0.013, 0.896 | 1,385 / 1,415    |
| ElasticBand       | worse than random; win rate p 0.01, R 0.04 | −0.283, 0.229 | −0.098, 0.726 | 151 / 146        |
| PullBackAndGo     | —                                          | −0.054, 0.876 | +0.116, 0.746 | 136 / 132        |
| DeadCatBounce     | —                                          | +0.059, 0.915 | −0.133, 0.836 | 35 / 39          |

**InsideBar's is again the largest excess on both roots and again short of p = 0.05 on either**, at almost the same size. InsideBarTrailing's is now positive on both roots rather than either side of its null, by 0.041 and 0.013. **ElasticBand is again worse than random on win rate and on mean R on both roots**, at p 0.010 for win rate on both and 0.040 and 0.030 for R, which is §M27's reading to the second decimal. Nothing in the table clears p = 0.05 on profit factor, as nothing did.

### §M27.3 — InsideBar's bracket crossed

The target crossed against the stop at 5 and 10 minutes, unfiltered and in the fitted `regime=DIRECTIONAL` cells, read on the `narrow` set ([`m27-3-insidebar-bracket.md`](m27-3-insidebar-bracket.md)). Its entries were re-read from the new rows before it ran and none moved; it now runs at 2 and 15 minutes too, which are left out here.

| claim                                                       | §M27.3                                                                                                | re-swept                                                                  |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| η² of the target, holdout / selection, net-to-drawdown      | **0.284** / 0.063                                                                                     | **0.167** / 0.046                                                         |
| the same on profit factor                                   | **0.270** / 0.055                                                                                     | **0.125** / 0.025                                                         |
| η² of the stratum, holdout, net-to-drawdown / profit factor | 0.055 / 0.109                                                                                         | **0.214 / 0.304**                                                         |
| the holdout's ridge, median net-to-drawdown, MNQ            | 1.458 and 1.434 at 1.5 and 2.0                                                                        | 1.652 and 1.697                                                           |
| the same, NQ                                                | 0.771 and 1.123                                                                                       | 0.593 and 0.786                                                           |
| the selection window's ridge                                | 5.0 to 6.0                                                                                            | 5.0 to 8.0                                                                |
| rank correlation of the target with net-to-drawdown         | +0.194 selection, −0.455 holdout, 8 of 12 flip                                                        | +0.222, −0.370, 9 of 12 flip                                              |
| cells clearing the drawdown, ranked on net-to-drawdown      | 1 of 12                                                                                               | 1 of 12                                                                   |
| the same, ranked on profit factor                           | 1 of 12                                                                                               | **4 of 12**                                                               |
| mean rank correlation across the split                      | −0.161 and −0.098                                                                                     | −0.142 on both rankings                                                   |
| what the selection window ranks first on net-to-drawdown    | target 1.0, stop 10.0, on both roots                                                                  | at `n=20`: target 1.0; stop 10.0 on MNQ, 20.0 on NQ                       |
| gate 3, 56 cells per root at `n=20`: p < 0.05               | 3 on MNQ, 2 on NQ                                                                                     | 1 on MNQ, 0 on NQ                                                         |
| gate 3: cells beating their null                            | 34 and 29                                                                                             | 49 and 29                                                                 |
| gate 3: the excess peaks at                                 | target 1.5 on both roots                                                                              | 1.5 on MNQ (+0.239), 1.0 on NQ (+0.176)                                   |
| the two rankings                                            | PF and net-to-drawdown pick stop 2.0 target 1.5; the excess picks stop 20.0 target 2.0, on both roots | the same first pick; the excess picks stop 20.0 target 1.0, on both roots |

**The finding holds: the target is not selectable.** The two windows still rank it close to inverted, its correlation with net-to-drawdown still changes sign across the split in most cells, and the selection window still picks the 1× target §M27 was stuck with. **The target is no longer the largest axis on the holdout**, though: the stratum now explains more of its variance. And ranked on profit factor, four cells finish the holdout with more than their own drawdown rather than one — all four the 30- and 50-bar lookbacks, which were not the cell named before the run.

### §M27.4 — the sixteen strata held out

The twenty strata §M27 ran, six archetypes, both roots ([`m27-4-strata-held-out.md`](m27-4-strata-held-out.md)). **It reproduces closely.**

| dimension  | cells | selection   | holdout     | decay       | mean rank correlation |
| ---------- | ----- | ----------- | ----------- | ----------- | --------------------- |
| unfiltered | 12    | 1.27 → 1.24 | 0.94 → 0.91 | 0.33 → 0.32 | 0.46 → 0.39           |
| trend      | 34    | 1.37 → 1.33 | 1.03 → 0.99 | 0.34 → 0.34 | 0.30 → 0.21           |
| htf        | 24    | 1.34 → 1.34 | 0.93 → 0.96 | 0.41 → 0.39 | 0.28 → 0.23           |
| volume     | 36    | 1.42 → 1.39 | 1.04 → 0.99 | 0.38 → 0.40 | 0.32 → 0.23           |
| phase      | 82    | 1.45 → 1.43 | 0.96 → 1.00 | 0.49 → 0.43 | 0.22 → 0.15           |
| regime     | 36    | 1.46 → 1.38 | 1.04 → 0.95 | 0.42 → 0.43 | 0.32 → 0.24           |

The first figure in each pair is §M27.4's. **The decay is still about the same in every dimension**, now within 0.11 of itself rather than 0.17, and the rank correlation has fallen by 0.05 to 0.10 in every dimension. 92 of the 224 testable cells pass gate 2, against 99; a shortlist drawn at random from the same stratum passes 21.6% of the time against 20.1%, and the chosen shortlist sits at the 89th percentile of its own null in the median cell, against the 93rd. 27.7% of cells invert outright, against 26%, and ElasticBand still owns eight of the twelve largest decays. `htf=AT` still holds no row above the trade floor. 32 of the 112 archetype × stratum pairs pass on both roots, against 38.

**InsideBar's three siblings are still one finding**, and still the whole parameter space rather than a shortlist:

| stratum              | holdout shortlist PF, MNQ / NQ | stratum's holdout median  | of 20 profitable | median holdout trades         |
| -------------------- | ------------------------------ | ------------------------- | ---------------- | ----------------------------- |
| `regime=DIRECTIONAL` | 1.38 / 1.85 → 1.31 / 1.20      | 1.12 / 1.07 → 1.20 / 1.15 | 20 / 20          | 122 / 115 → 286 / 301         |
| `trend=UP`           | 1.31 / 1.23 → 1.25 / 1.21      | 1.13 / 1.13 → 1.10 / 1.08 | 20 / 20          | 857 / 784 → 1,066 / 1,084     |
| `htf=ABOVE`          | 1.15 / 1.09 → 1.11 / 1.10      | 1.11 / 1.08 → 1.10 / 1.08 | 20 / 20          | 1,013 / 1,117 → 1,178 / 1,190 |

The shortlists now trade more, `DIRECTIONAL`'s more than twice as much, and this file does not separate the archive's share of that from the fills'. **`InsideBar phase=LONDON` still rises out of sample**, 1.08 to 1.36 on MNQ and 1.10 to 1.52 on NQ, on 396 and 243 trades, inside a stratum whose holdout median loses money on both roots.

### §M27.5 and §M27.6 — a calibration and the wiring

Nothing to re-read. §M27.5 fits the regime threshold from the efficiency ratio's distribution on the selection window, and neither the ratio nor the window changed; §M27.6 is tooling ([`m27-5-regime-threshold.md`](m27-5-regime-threshold.md), [`m27-6-walkforward-montecarlo.md`](m27-6-walkforward-montecarlo.md)).

### §M27.7 — the time of day

([`m27-7-time-of-day.md`](m27-7-time-of-day.md).) **The structure holds and the per-phase null does not.** The empty cells are where they were: InsideBar's `CLOSE` holds no viable row, and OpeningRange's `OVERNIGHT`, `LONDON` and `PRE_OPEN` none. The forced flat still lands in `AFTERNOON`: InsideBar's median `session_close_share` there runs 0.126, 0.192, 0.286, 0.405 and 0.459 from 1 to 15 minutes, against 0.128 to 0.449, and every archetype that holds a position for long is about 0.84 to 0.93 clock in `CLOSE`.

The best configuration per phase against its matched null, as §M27.7 tabled it:

| phase     | §M27.7, MNQ / NQ                      | re-swept MNQ                      | re-swept NQ                       |
| --------- | ------------------------------------- | --------------------------------- | --------------------------------- |
| OVERNIGHT | **+0.520, p 0.030** / +0.227, 0.239   | 5m, +0.202, 0.249                 | 5m, +0.236, 0.109                 |
| LONDON    | **+0.613, 0.050** / **+0.512, 0.040** | 10m, **+0.840, 0.010**            | 10m, **+0.691, 0.030**            |
| PRE_OPEN  | +0.065, 0.796 / −0.052, 0.925         | 5m, +0.078, 0.726                 | 5m, +0.224, 0.498                 |
| CASH_OPEN | −0.050, 0.915 / +0.090, 0.846         | 15m, **+2.744, 0.010**, 61 trades | 15m, **+2.337, 0.010**, 62 trades |
| MIDDAY    | −0.078, 0.726 / −0.073, 0.697         | 10m, +0.142, 0.577                | 10m, +0.169, 0.517                |
| AFTERNOON | −0.290, 0.289 / +0.020, 0.955         | 15m, −0.341, 0.229                | 5m, +0.063, 0.756                 |

**LONDON still beats its null on both roots, and more firmly.** **OVERNIGHT no longer does on MNQ**: the selection window now picks a 5-minute configuration there rather than a 15-minute one. **And the cash open now beats its null on both roots**, which contradicts §M27.7's reading that every phase in the second half of the session is at or below its null. It rests on 61 and 62 held-out trades at 15 minutes, with profit factors of 3.85 and 3.39 against nulls of 1.11 and 1.05, in a phase whose median configuration closes 24% of its legs on the clock at that bar size. All twelve cells were chosen by looking, as before: at a Bonferroni threshold over twelve none of them clears, and at 200 draws none could.

At 5 and 10 minutes the two most clock-contaminated phases no longer both hold the best median profit factor: `AFTERNOON` leads at 5 minutes with 1.145, but `LONDON` leads at 10 with 1.130. The screen over the survivor's own trades, `tools/campaign_review.py`, was not re-run.

### §M27.8 — volume

([`m27-8-volume.md`](m27-8-volume.md).) The re-sweep stores the fitted volume cells on the two split windows and not over the whole series, so the state table below is read on the selection window, where §M27.8's was read over the whole series. InsideBar, 5 minutes, median profit factor and share profitable:

| state  | per bar 10/90 | per bar 20/80 | per bar 33/67 | rolling 10/90 | rolling 20/80 | rolling 33/67  | to date 10/90 | to date 20/80     | to date 33/67 |
| ------ | ------------- | ------------- | ------------- | ------------- | ------------- | -------------- | ------------- | ----------------- | ------------- |
| THIN   | 0.962 / 44%   | 1.018 / 56%   | 1.061 / 69%   | 0.848 / 21%   | 0.859 / 3%    | 0.882 / **0%** | 0.815 / 2%    | 0.766 / 0%        | 0.933 / 22%   |
| NORMAL | 1.010 / 59%   | 0.981 / 35%   | 0.946 / 17%   | 1.004 / 54%   | 1.011 / 59%   | 1.053 / 78%    | 1.044 / 86%   | **1.125 / 99.9%** | 1.051 / 66%   |
| HEAVY  | 1.010 / 52%   | 1.045 / 66%   | 1.000 / 50%   | 1.057 / 60%   | 1.015 / 55%   | 1.003 / 52%    | 0.852 / 22%   | 0.888 / 13%       | 0.994 / 46%   |

**The ranking is still the cut.** Under the per-bar form `THIN` is still the worst state at a tenth-tail and the best at a third, and under the rolling form it is still the worst at every tail, with none of 864 configurations profitable at a third. **`NORMAL` is now the best state under one form at every tail rather than two**: the session-to-date form, whose 20/80 cell is again all but every configuration profitable. Under the rolling form it is best at a third only, and under the per-bar form at no tail outright.

**Held out it is still a coin flip, but no longer a uniform failure of the drawdown.** Of the thirty volume cells, the 27 fitted and the three raw, 18 pass on both roots against §M27.8's 16 of 31, and **10 return their own drawdown on at least one root** where §M27.8 had none on either. One does on both, `NORMAL` under the rolling form at a tenth-tail. Unfiltered still passes on both roots and still fails the drawdown on both, at 0.919 and 0.924. The trade-log screen was not re-run.

### §M19.1 — the compression condition

([`m19-1-compression-condition.md`](m19-1-compression-condition.md).) **Its held-out ordering does not reproduce, and its verdict holds more firmly for it.** The three states, seven archetypes, both roots:

| state      | cells passing | clears drawdown | decay         | rank correlation | holdout PF    |
| ---------- | ------------- | --------------- | ------------- | ---------------- | ------------- |
| COMPRESSED | 71.4% → 50.0% | 42.9% → 7.1%    | 0.339 → 0.688 | 0.413 → 0.214    | 1.253 → 0.956 |
| NORMAL     | 57.1% → 57.1% | 21.4% → 28.6%   | 0.265 → 0.267 | 0.460 → 0.404    | 1.024 → 0.987 |
| EXPANDED   | 28.6% → 42.9% | 7.1% → 21.4%    | 0.518 → 0.443 | 0.220 → 0.246    | 0.905 → 0.940 |

**`COMPRESSED` is no longer the winning half held out; `NORMAL` is.** Its decay is now the largest of the three, carried by EmaCrossover's 1.43 on both roots and OpeningRange's 1.22 and 1.34, and its median cell's holdout profit factor is 0.922 against `NORMAL`'s 1.020. What reproduces is the rest: on the whole series `EXPANDED` still looks strongest on InsideBar at 5 minutes, 90.5% profitable against 69.8% unfiltered, and held out it is still the clock, with a median `session_close_share` of 0.151, 0.237 and 0.267 at 5, 10 and 15 minutes against `COMPRESSED`'s 0.019, 0.030 and 0.055.

**The dimension is still mid-pack.** Under the strict verdict it passes 16.7% of its cells, against the higher-timeframe side's 25.0%, trend's 22.5%, volume's 19.0%, phase's 16.7% and regime's 11.9%, so it still separates no better than the dimensions the campaign already had. The crossing of the two forms on InsideBar and OpeningRange was not re-swept, so its 0.133 correlation between them is not re-read.

### The higher-timeframe average

([`multi-timeframe-moving-averages.md`](multi-timeframe-moving-averages.md).) Its one-off DeadCatBounce run was not repeated. In the campaign rows the dimension still has two states rather than three, since `htf=AT` holds no row above the trade floor, and it sits mid-pack in §M27.4's table, at a decay of 0.39.

### §M7a — the random-entry control

DeadCatBounce at its defaults on MNQ's 1-minute bars from 2024, $1.24 commission and one tick of slippage, 500 draws, as §M7a ran it ([`m7a-random-entry-control.md`](m7a-random-entry-control.md)). The series is 954,545 bars against 914,700, the archive now running to 2026-09-18.

| statistic     | observed        | null median     | percentile  | p                 |
| ------------- | --------------- | --------------- | ----------- | ----------------- |
| profit factor | 0.666 → 0.659   | 0.551 → 0.571   | 99.6 → 98.2 | 0.012 → **0.040** |
| expectancy    | −10.24 → −10.46 | −14.78 → −13.80 | 99.8 → 98.2 | 0.008 → **0.040** |
| win rate      | 32.2% → 32.0%   | 29.3% → 29.6%   | 99.8 → 99.6 | 0.008 → **0.012** |

**The entry is still better than random and still loses money**, and less clearly so: the null's median rose and the observation fell, so profit factor and expectancy sit at p = 0.040 rather than 0.012 and 0.008. Win rate, which §M7a called the more informative of the three, holds at 0.012. The arms still match on signals and diverge on fills, 3,766 trades against the null's median of 2,419.

## OpeningRange

The archetype the fills moved most: its breakout and fade are stop entries, which [#472] reads along the fill bar's path, and its retest and rejection are limit entries, which [#453] and [#455] reach. Three of its campaigns, §M28.8, §M28.10 and §M28.11, and §M28.9's table by year read 1-minute bars and wait for the last part of the re-sweep. §M28.3, §M28.4 and §M28.6 are tooling and a specification, with nothing to re-read.

### §M28.1 — OpeningRange swept

([`m28-1-openingrange-swept.md`](m28-1-openingrange-swept.md).) **Gate 1 reproduces exactly, gate 2 weakens, and gate 3 holds in one of its two strata.**

| claim                                                                  | §M28.1                                          | re-swept                                        |
| ---------------------------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------- |
| gate 1, opposite-extreme stop: cells with a majority profitable        | **10 of 10**, 50.7%–97.9%, PF 1.004–1.103       | **10 of 10**, 59.4%–100%, PF 1.024–1.103        |
| gate 1, ATR stop                                                       | **0 of 10**, 1.0%–10.4%, PF 0.660–0.805         | **0 of 10**, 5.6%–22.9%, PF 0.764–0.885         |
| η² within the opposite stop                                            | direction 0.381, window 0.272, resolution 0.138 | direction 0.472, window 0.313, resolution 0.076 |
| η² within the ATR stop                                                 | ATR multiple 0.776                              | ATR multiple 0.683                              |
| gate 2: root × stratum cells passing                                   | 51 of 62                                        | **42 of 62**                                    |
| the shortlist above its stratum's holdout median                       | 91.9% of cells                                  | 71.0%                                           |
| mean decay, mean rank correlation                                      | 0.221, **0.69**                                 | 0.231, **0.35**                                 |
| `session_close_share` of the unfiltered shortlist, selection / holdout | 0.40 / 0.45                                     | 0.47 / 0.52                                     |

The stop mode is still a partition rather than an axis, and within the half that works the bar size is still only the third-largest axis. At 30 minutes the opposite stop is profitable in exactly half its configurations on both roots, so the new bar size adds no gate-1 cell. **What weakens is the held-out ranking**: the rank correlation across the split halves, to the top of the range §M27.4's re-read gives the six earlier archetypes rather than well above it, though the decay stays below theirs.

**`phase=CASH_OPEN` now passes gate 2 on both roots**, with 20 and 19 of 20 profitable, where §M28.1 had it failing on both with none of 20 profitable and called it the cell worth staring at. The other four strata §M28.1 had failing on both roots still do — `AFTERNOON`, `CLOSE`, `htf=BELOW` and the raw `regime=UNCLASSIFIABLE` — and three fitted regime cells join them. The raw `regime=DIRECTIONAL` now misses on NQ, by 0.016 of the stratum's own median.

Gate 3, the configuration the selection window ranks first on each root, 200 draws over bars as §M28.1 drew:

| stratum                     | §M28.1, MNQ / NQ                 | re-swept MNQ                   | re-swept NQ                            |
| --------------------------- | -------------------------------- | ------------------------------ | -------------------------------------- |
| `regime=DIRECTIONAL@n=50`   | **better, p 0.010** / **0.010**  | **+1.104, p 0.010**, 50 trades | **+1.056, p 0.010**, 52 trades         |
| `trend=UP`                  | **better, p 0.010** / **0.010**  | +0.005, p 0.985                | −0.294, **worse than random**, p 0.010 |
| `regime=CONSOLIDATING@n=50` | indistinguishable, 0.109 / 0.070 | −0.276, p 0.080                | −0.334, **worse than random**, p 0.030 |
| `volume=THIN`               | indistinguishable, 0.965 / 0.587 | +0.090, p 0.517                | −0.114, p 0.418                        |

**The archetype's own thesis, the fitted `DIRECTIONAL` cell, still beats a random entry on both roots; `trend=UP` no longer does on either.** So OpeningRange now passes gate 3 in one of §M28.1's strata rather than two, and the roots agree on two of the four rather than all four. The long-and-short null that settled §M28.1's drift question was not re-run.

### §M28.2 — the deferral list built

([`m28-2-deferral-list.md`](m28-2-deferral-list.md).) Profitable share, unfiltered, whole series, MNQ / NQ, at 2 to 15 minutes where §M28.2 read 1 to 15:

| entry    | stop fraction 0.25            | 0.50                          | 0.75                          | 1.00                              |
| -------- | ----------------------------- | ----------------------------- | ----------------------------- | --------------------------------- |
| breakout | 0.000 / 0.006 → 0.011 / 0.011 | 0.135 / 0.146 → 0.103 / 0.139 | 0.383 / 0.438 → 0.378 / 0.428 | **0.615 / 0.633 → 0.522 / 0.589** |
| fade     | 0.036 / 0.054 → 0.044 / 0.058 | 0.073 / 0.143 → 0.008 / 0.057 | 0.139 / 0.185 → 0.092 / 0.140 | 0.190 / 0.246 → 0.142 / 0.197     |
| retest   | 0.611 / 0.709 → 0.637 / 0.756 | 0.542 / 0.609 → 0.592 / 0.637 | 0.546 / 0.603 → 0.574 / 0.642 | 0.619 / 0.654 → 0.626 / 0.665     |

**All three verdicts hold.** The breakout clears gate 1 only at the opposite-extreme stop and degrades smoothly as the stop tightens. The fade fails gate 1 at every fraction on both roots. And the retest's gate-2 pass is still the ambiguity assumption: it passes 16 of 16 cells at held-out profit factors of 2.00 to 3.85, against 2.15 to 3.87, and its unfiltered shortlist is again all at the tightest fraction, with a held-out `ambiguous_share` of 0.357 and 0.365 against its population's 0.029. The breakout passes 15 of 16 cells rather than 16, and the fade 3 of 16 rather than none. Its level null, re-run beside §M60, now clears on both roots at 15 minutes, where §M28.2 had one cell of six clearing: [§M60](m60-level-kind-null-result.md).

### §M28.5 — the fade's tight stops, and the verdict reverses

([`m28-5-fade-bracket.md`](m28-5-fade-bracket.md).) **This is the largest change the fills made to any finding in the registry.** §M28.5 swept the fade's stop down to 2% of the range width and found nothing: not one of its combinations below the shared endpoint profitable, on either root. Read on the selection window, as its rows are stored:

| target      | 0.02                              | 0.05                          | 0.10                          | 0.25                          |
| ----------- | --------------------------------- | ----------------------------- | ----------------------------- | ----------------------------- |
| `R`         | 0.000 / 0.000 → 0.000 / 0.000     | 0.000 / 0.000 → 0.000 / 0.000 | 0.000 / 0.000 → 0.000 / 0.000 | 0.028 / 0.052 → 0.026 / 0.028 |
| `width`     | 0.000 / 0.000 → **0.221 / 0.415** | 0.000 / 0.000 → 0.031 / 0.054 | 0.000 / 0.000 → 0.015 / 0.008 | 0.052 / 0.069 → 0.067 / 0.074 |
| `width+mid` | 0.000 / 0.000 → **0.223 / 0.404** | 0.000 / 0.000 → 0.031 / 0.048 | 0.000 / 0.000 → 0.013 / 0.008 | 0.041 / 0.064 → 0.067 / 0.073 |

706 of the 11,520 combinations below the endpoint are now profitable. The best profit factor at the three tight fractions is 1.530, 1.194 and 1.114, against 0.545, 0.641 and 0.922, and the median no longer rises with the fraction. Held out, the twenty the selection window ranks first at each fraction:

| fraction | §M28.5, held-out PF MNQ / NQ, profitable of 20 | re-swept                   |
| -------- | ---------------------------------------------- | -------------------------- |
| 0.02     | 0.210 / 0.274, 0 / 0                           | **1.774 / 1.744, 20 / 20** |
| 0.05     | 0.477 / 0.512, 0 / 0                           | 1.113 / 1.045, 11 / 12     |
| 0.10     | 0.811 / 0.789, 0 / 0                           | 0.664 / 0.622, 0 / 0       |
| 0.25     | 1.006 / 1.037, 10 / 14                         | 1.004 / 1.013, 12 / 12     |

**At a stop 2% of the range beyond the extreme, every one of the forty held-out configurations makes money and returns its own drawdown**, at profit factors of 1.30 to 2.09 on MNQ and 1.31 to 2.39 on NQ and net-to-drawdown of 1.2 to 18. They are not thin: 261 to 871 held-out trades on MNQ, a median of 292, and 344 to 1,998 on NQ. They win 13% and 7% of the time against a target one range width away, and all but four of the forty are 15-minute configurations.

**The mechanism is [#472], and it retires §M28.5's own.** The fade is a stop entry that fills as price comes back through the level, so on its fill bar the extreme on the stop's side can come before the fill. §M28.5 measured the whole entry bar's adverse excursion against the stop, found it exceeded a 2% stop 84.7% of the time, and concluded that the stop sat inside the bar the order fills on. NinjaTrader reads the bar along its path and lets the stop see only what came after the fill, and the simulation now does the same (`docs/nt8-fidelity.md`, "A stop on its entry bar is read along the bar's path"), so an extreme that came before the fill no longer stops the trade. `ambiguous_share` at the tightest fraction falls from 0.287 to 0.087 for the same reason: a leg is flagged only where its own part of the path reached both levels.

**It is a gate-2 result, not a candidate.** No gate-3 or gate-4 read has been run on it. The stop is narrower than a typical bar, so whether a trade survives its fill bar is decided by a walk from the open to the nearer extreme, which is NinjaTrader's model of a bar and not a record of one. The second tier would agree with it; the minute bars could test it on these 15-minute rows, as §M28.4 did for the retest, and that has not been done. §M28.5's verdict does not hold under the fill rule now in force: the stop axis is not monotone, and its tightest end is the fade's best. The rejection, §M28.7, is the test of the same question from a limit entry, and it is unchanged.

### §M28.7 — the rejection

([`m28-7-rejection-swept.md`](m28-7-rejection-swept.md).) **It reproduces: profitability still tracks the fill assumption.** Unfiltered, selection window:

| `ambiguous_share` | median PF, MNQ / NQ              | profitable, MNQ / NQ              |
| ----------------- | -------------------------------- | --------------------------------- |
| below 0.05        | 0.846 / 0.897 → 0.868 / 0.915    | 0.177 / 0.272 → 0.157 / 0.256     |
| 0.05 – 0.15       | 1.053 / 1.132 → 1.007 / 1.081    | 0.582 / 0.730 → 0.520 / 0.714     |
| 0.15 – 0.30       | 1.457 / 1.589 → 1.307 / 1.453    | 0.931 / 0.953 → 0.849 / 0.944     |
| 0.30 – 0.50       | 2.537 / 2.866 → 2.431 / 2.792    | **1.000 / 1.000 → 1.000 / 1.000** |
| 0.50 and above    | 10.395 / 11.987 → 8.281 / 10.684 | **1.000 / 1.000 → 1.000 / 1.000** |

Every configuration whose assumption decides three legs in ten is still profitable, and the readable rows still lose: on MNQ their median profit factor runs 0.843 to 0.906 across 2 to 15 minutes, nearly flat, while the share profitable climbs from 0.385 to 0.802 with the mean `ambiguous_share`. On the holdout at 15 minutes 78.1% and 81.7% of configurations are profitable, against 79.9% and 84.4%. The rejection is a limit entry, which the path rule does not reach, and its verdict stands. **What no longer holds is the mirror §M28.7 drew between it and the fade**: the fade's median profit factor on MNQ now runs 0.57, 0.51, 0.57 and 0.70 across the four fractions, rather than falling with its ambiguity as the rejection's rises.

### §M28.9 — the survivor's drawdown

([`m28-9-survivor-tradeability.md`](m28-9-survivor-tradeability.md).) **One cell in thirteen returned its own drawdown held out; now none of fourteen does.** The unfiltered shortlist, pooled over each archetype's campaign variants:

| archetype         | §M28.9, MNQ / NQ  | re-swept        |
| ----------------- | ----------------- | --------------- |
| InsideBar         | 0.468 / **1.022** | 0.919 / 0.924   |
| InsideBarTrailing | 0.328 / 0.196     | 0.687 / −0.080  |
| EmaCrossover      | 0.059 / −0.414    | 0.179 / 0.924   |
| DeadCatBounce     | −0.292 / −0.259   | −0.841 / −0.870 |
| PullBackAndGo     | −0.572 / −0.527   | −0.787 / −0.449 |
| ElasticBand       | −0.583 / −0.633   | −0.606 / −0.494 |
| OpeningRange      | unusable          | 0.834 / 0.711   |

OpeningRange's row is readable now because the shortlist ranks its campaign variants alone rather than every set in its database. The verdict holds: the binding constraint is net-to-drawdown rather than profit factor. Its table by year, and so its finding that the edge is absent from 2026, is 1-minute and waits for the last part.

### §M28.12 — the bracket against the flatten

([`m28-12-bracket-decomposition.md`](m28-12-bracket-decomposition.md).) **It reproduces.** Read from gate 4's exclusion pass over every campaign variant's held-out shortlist at 2 to 15 minutes, the bracket's net is what each configuration made less what its session-close legs made:

| archetype         | bracket negative, MNQ / NQ | median bracket net, MNQ / NQ | median flatten net, MNQ / NQ |
| ----------------- | -------------------------- | ---------------------------- | ---------------------------- |
| **InsideBar**     | **5.0% / 8.8%**            | **+103,799 / +1,054,205**    | −96,192 / −1,013,082         |
| InsideBarTrailing | 96.2% / 95.0%              | −125,147 / −1,182,396        | +98,320 / +938,196           |
| EmaCrossover      | 100% / 100%                | −140,373 / −1,367,071        | +150,970 / +1,425,156        |
| ElasticBand       | 100% / 100%                | −84,538 / −628,279           | +68,920 / +616,443           |
| OpeningRange      | 100% / 100%                | −101,699 / −1,007,282        | +96,208 / +952,157           |
| DeadCatBounce     | 71.2% / 83.8%              | −1,953 / −19,968             | +118 / +1,815                |
| PullBackAndGo     | 91.2% / 76.2%              | −4,811 / −22,112             | +27 / +386                   |

**InsideBar is still the only archetype whose bracket pays for itself held out**, and its flatten still loses on every configuration. At 5 minutes, the bar size §M28.12 read it at, the flatten hands back 0.89 of what the bracket earns on MNQ and 0.92 on NQ, against 0.92 and 0.89. EmaPullback and SqueezeBreakout, read the same way, carry their results on the flatten too, with the bracket negative on 99% to 100% of their configurations. These are shortlists per variant and bar size, where §M28.12 pooled each archetype's into one.

### §M28.14 — the stratum cross-read

([`m28-14-stratum-cross-read.md`](m28-14-stratum-cross-read.md).) Re-scored by §M54 on the re-swept rows, over eight root × resolution cells where §M28.14 had ten, so a score now runs from −8 to +8. **The structure holds.** EmaCrossover and ElasticBand are still mirror images by phase: the cash open and midday at +7 and +8 for the first, −6 and −7 for the second, and the pre-open at −6 against +8. Midday is still the best phase for the breakout family — +8 for OpeningRange, +7 for InsideBarTrailing, +8 for EmaCrossover. OpeningRange still scores +7 above the hourly average and −6 below it, volume is still close to inert outside OpeningRange's `THIN` (+7) and ElasticBand (+7 `HEAVY`, −8 `NORMAL`), and `regime=UNCLASSIFIABLE` is still the best regime cell for InsideBar, InsideBarTrailing and ElasticBand, and level with `DIRECTIONAL` for OpeningRange. `CLOSE` is no longer negative for every archetype: PullBackAndGo scores +1 there.

Its two cells taken to a null are in §M54's family A. **OpeningRange's `phase=MIDDAY` still clears**: 10 of 10 configurations below p = 0.05 on MNQ and 7 of 10 on NQ, one test at a time, against 9 and 10. ElasticBand's `phase=PRE_OPEN` still beats its null on most configurations and clears on none.

### §M28.15 and §M31.1 — gate 4 on the two OpeningRange candidates

([`m28-15-midday-cell.md`](m28-15-midday-cell.md), [`m31-1-survivor-gate-4.md`](m31-1-survivor-gate-4.md).) Both are `window=30m stop=opposite target=R` at 5 minutes, the held-out top twenty: §M28.15's `phase=MIDDAY` and §M31.1's `regime=DIRECTIONAL@n=20 q=0.20/0.80`.

| read                                       | §M28.15               | re-swept              | §M31.1                | re-swept              |
| ------------------------------------------ | --------------------- | --------------------- | --------------------- | --------------------- |
| walk-forward, pooled test PF, MNQ / NQ     | 1.279 / 1.302, passes | 1.243 / 1.273, passes | 1.439 / 1.459, passes | 1.450 / 1.437, passes |
| permutation p of the drawdown              | 0.41–0.90             | 0.29–0.87             | —                     | 0.34–0.98             |
| bootstrap 5th percentile of PF above 1.0   | 0 of 40               | 0 of 40               | 1 of 20               | 0 of 40               |
| resamples that lose money, median MNQ / NQ | 0.139 / 0.113         | 0.138 / 0.132         | —                     | 0.120 / 0.106         |
| profitable without the session-close legs  | 0 of 40               | **0 of 40**           | 0 of 20               | **0 of 40**           |
| median PF whole → without them, MNQ        | 1.216 → 0.371         | 1.181 → 0.311         | 1.430 → 0.238         | 1.312 → 0.234         |

**Both reproduce.** The walk-forward still passes, the drawdown is still not the trades' ordering, the bootstrap still cannot exclude a loss, and neither cell has a configuration profitable without its forced flat. The prop accounts are not comparable: the gate reads replay the 2026 presets, an evaluation linked to its funded account, where both campaigns replayed the evaluations alone; §M46's re-run below uses the old presets for that reason. §M31.1's hold ladder inside the stratum was not re-swept and is not re-read.

### §M28.16 — the consistent cells

([`m28-16-consistent-cells.md`](m28-16-consistent-cells.md).) Re-run as §M54's family B, which reproduces §M44's per-test counts almost exactly: four cells put a configuration below p = 0.05 on both roots, as §M28.16's did, and none clears family-wise ([§M54](m54-family-wise-null-result.md)).

### §M31 — the calibrated cells under the null

([`m31-calibrated-cells-null.md`](m31-calibrated-cells-null.md).) Re-run as phase 2b ran it: the nine cells, both roots, 5 minutes, top ten, 400 draws, OpeningRange under the level draw. **Two cells cleared on both roots; one still does.**

| cell                                                 | §M31, p < 0.05 MNQ / NQ | re-swept   | excess, re-swept | held-out trades |
| ---------------------------------------------------- | ----------------------- | ---------- | ---------------- | --------------- |
| OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`   | **10 / 10**             | **9 / 10** | +0.357 – +0.451  | 152–158         |
| OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`   | **9 / 8**               | 0 / 0      | +0.164 – +0.274  | 209–225         |
| OpeningRange `regime=DIRECTIONAL@n=5 q=0.20/0.80`    | 0 / 0                   | 0 / 0      | +0.139 – +0.275  | 241–256         |
| OpeningRange `regime=DIRECTIONAL@n=30 q=0.20/0.80`   | 0 / 0                   | 0 / 0      | +0.084 – +0.250  | 125–131         |
| OpeningRange `regime=DIRECTIONAL@n=50 q=0.20/0.80`   | 0 / 0                   | 0 / 1      | +0.031 – +0.442  | 80–109          |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.20/0.80` | 3 / 0                   | 3 / 0      | −0.217 – +0.603  | 25–382          |
| ElasticBand, the other three cells                   | 0 / 0                   | 0 / 0      | −0.401 – +0.255  | 45–1,461        |

**The 20-bar lookback is still the strongest gate-3 cell OpeningRange has**, now at a median p of 0.042 and 0.025 rather than 0.010, on more trades. The 10-bar lookback no longer clears anywhere: every configuration still beats its null, by less. ElasticBand's mirror still carries nothing — its two `UNCLASSIFIABLE` cells beat their null on 2, 4, 7 and 4 of 10 configurations.

### §M38 — the cell across configurations

([`m38-openingrange-cell-across-configurations.md`](m38-openingrange-cell-across-configurations.md).) §M31's cell, each arm ranked within itself, 400 draws, the level draw, read by §M38's own rule: an arm holds where six of ten configurations reach p < 0.05 on both roots, and keeps the direction only where six of ten beat their null on both.

| arm                     | §M38, p < 0.05 MNQ / NQ | verdict        | re-swept  | verdict            |
| ----------------------- | ----------------------- | -------------- | --------- | ------------------ |
| control, 30m opposite R | 9 / 10                  | holds          | 9 / 10    | holds              |
| stop, ATR               | 0 / 0                   | direction only | 1 / 0     | direction only     |
| window, 15m             | 8 / 8                   | holds          | **2 / 4** | **direction only** |
| window, 5m              | 10 / 10                 | holds          | 10 / 10   | holds              |
| target, width           | 8 / 8                   | holds          | 8 / 8     | holds              |

**Its answer holds: the cell's gate-3 result belongs to the opposite-extreme stop.** Under the ATR stop the entry still beats its null on 10 and 9 of 10 configurations and clears on one. Within the opposite stop three arms hold rather than four, the 15-minute window falling to the direction only, and the 5-minute window is still the strongest arm, at 10 of 10 on both roots on the most held-out trades.

## InsideBarTrailing

The fixes barely reach it: its stops sit on bar extremes, so only [#453]'s gapped targets moved it, in 3.9% of its cells. And every campaign here from §M45 on ran on §M44's bars. **So its campaigns are the cleanest test of the re-sweep itself, and they reproduce almost to the digit.**

### §M42 — gate 4 on the midday cell

([`m42-insidebartrailing-gate-4.md`](m42-insidebartrailing-gate-4.md).) `phase=MIDDAY` at 5 minutes, the held-out shortlist, from gate 4's reads over the twenty the selection window ranks first, where §M42 read ten:

| read                                              | §M42, MNQ / NQ                | re-swept, MNQ / NQ            |
| ------------------------------------------------- | ----------------------------- | ----------------------------- |
| median PF, whole → without the session-close legs | 1.482 → 0.975 / 1.316 → 0.939 | 1.358 → 0.747 / 1.363 → 0.585 |
| profitable without those legs                     | **5 of 10 / 4 of 10**         | **4 of 20 / 1 of 20**         |
| both gate-4 thresholds without them               | 2 of 10 / 3 of 10             | 0 of 20 / 0 of 20             |
| bootstrap 5th percentile of PF above 1.0          | **10 of 10** / 4 of 10        | **17 of 20 / 13 of 20**       |
| walk-forward, pooled test PF                      | 1.439 / 1.451, passes         | 1.342 / 1.308, passes         |

**The exclusion reading that made §M42 the first cell to survive it does not reproduce, and the bootstrap reading does, on both roots now.** §M44 had already found the first half: nine of twenty survivors fell to one on its rows. The fills changed little more: five of forty configurations are profitable without their forced flat. The bootstrap is the stronger result than before: 30 of the 40 put a 5th percentile above a profit factor of 1.0 and above zero net, against 14 of 20.

### §M45 — sizing the midday cell

([`m45-ibt-sizing-result.md`](m45-ibt-sizing-result.md).) **It reproduces exactly.** Every tier's paired difference against the half split and against its own inverse matches §M45's table to the third decimal and the pair: `first-breakout` −0.083 and −0.052 with no pair improved, `sma-extension` −0.035 with 26 and −0.022 with 90, `trend-age` −0.065 with none and −0.045 with 29. The confluence size beats its own sizes shuffled on 20 of 20 MNQ configurations and 17 of 20 NQ ones, against the 4 required, and raises held-out profit factor over the half split by a median 0.071 and 0.058, improving 398 and 395 pairs of 432. Its account replay is in the prop section.

### §M47 and §M47.1 — the confluence size everywhere

([`m47-confluence-sizing-10-15.md`](m47-confluence-sizing-10-15.md), [`m47-1-confluence-sizing-5.md`](m47-1-confluence-sizing-5.md).) Family F1, the all-labels and symmetric arms unfiltered, read by its pre-registered rule: a cell clears where at least 6 of its 20 held-out configurations beat their own sizes shuffled at p ≤ 0.05 on both roots.

| bar size | cells | §M47, clearing                          | re-swept, clearing                         |
| -------: | ----: | --------------------------------------- | ------------------------------------------ |
|       15 |    35 | 9, all OpeningRange                     | **5**, all OpeningRange                    |
|       10 |    29 | 4: EmaCrossover 1, OpeningRange 3       | **2**: EmaCrossover 1, OpeningRange 1      |
|        5 |    41 | 10: OpeningRange 8, InsideBarTrailing 2 | **4**: OpeningRange 2, InsideBarTrailing 2 |

**The answer per archetype does not change**: yes on OpeningRange, EmaCrossover and InsideBarTrailing, no on the other six. InsideBarTrailing's two cells reproduce exactly, at 13 and 18 and at 15 and 20 of 20, and so does EmaCrossover's swing stop at 10 minutes, at 9 and 7. **OpeningRange clears 8 of its 36 cells rather than 20**, losing most of its ATR-stop arms, which is the stop entry the fills moved. In §M45's midday cell, family F0, every label reads exactly as before: the symmetric arm and `volume` clear, at 20 and 13 and at 11 and 7 of 20, and `regime`, `htf` and `trend` do not.

### §M49 — the structure trail

([`m49-structure-trail-result.md`](m49-structure-trail-result.md).) Its held-out half reproduces exactly: arms significantly up and down against `structure=off`, unfiltered.

| bar size | §M49, MNQ / NQ | re-swept, MNQ / NQ | held-out range of the median change, re-swept |
| -------: | -------------- | ------------------ | --------------------------------------------- |
|       15 | 24 / 0, 24 / 0 | 24 / 0, 24 / 0     | +0.009 to +0.120, +0.012 to +0.157            |
|       10 | 1 / 18, 9 / 6  | 1 / 19, 9 / 6      | −0.062 to +0.007, −0.039 to +0.029            |
|        5 | 19 / 1, 20 / 1 | 19 / 1, 20 / 1     | −0.006 to +0.058, −0.016 to +0.077            |
|        2 | not run        | 18 / 0, 23 / 0     | +0.004 to +0.030, +0.007 to +0.056            |

The selection-window half of §M49's bar was not re-read. In the midday cell at 5 minutes the trail still costs: 20 of 24 arms significantly down on both roots, none up on NQ. **At 2 minutes, the bar size §M49 dropped, every arm gains held out on both roots** and 18 and 23 of 24 significantly.

## The exits

### §M29 — the maximum hold

([`m29-maximum-hold-time.md`](m29-maximum-hold-time.md).) Median within-cell change in profit factor against the uncapped arm, at 2 to 15 minutes where §M29 read 1 to 15, now with EmaPullback and SqueezeBreakout beside the seven:

| archetype         | selection, 5 / 10 / 20 / 40 / 80 bars      | held out, 5 / 10 / 20 / 40 / 80 bars           |
| ----------------- | ------------------------------------------ | ---------------------------------------------- |
| DeadCatBounce     | −0.004 / +0.001 / 0 / 0 / 0                | +0.000 / 0 / 0 / 0 / 0                         |
| PullBackAndGo     | −0.005 / −0.002 / 0 / 0 / 0                | +0.003 / −0.002 / 0 / 0 / 0                    |
| InsideBar         | −0.058 / −0.052 / −0.015 / −0.002 / −0.000 | −0.046 / −0.017 / +0.004 / −0.013 / +0.008     |
| InsideBarTrailing | −0.052 / −0.023 / −0.000 / −0.004 / +0.001 | −0.039 / −0.016 / −0.014 / −0.005 / +0.002     |
| EmaCrossover      | −0.063 / −0.047 / −0.023 / −0.010 / −0.001 | −0.049 / −0.025 / −0.013 / −0.008 / −0.003     |
| ElasticBand       | −0.083 / −0.053 / −0.030 / −0.017 / −0.009 | −0.028 / −0.017 / −0.015 / −0.022 / −0.017     |
| OpeningRange      | −0.131 / −0.103 / −0.083 / −0.029 / −0.001 | −0.063 / −0.026 / +0.006 / −0.005 / 0          |
| EmaPullback       | −0.084 / −0.058 / −0.036 / −0.021 / −0.009 | **+0.003 / +0.006 / +0.019 / +0.023 / +0.027** |
| SqueezeBreakout   | −0.059 / −0.048 / −0.037 / −0.019 / −0.010 | −0.075 / −0.046 / −0.020 / −0.007 / −0.004     |

**On the selection window the cap is still a cost on every archetype that holds long enough to reach it, and the cost still shrinks as it loosens**, but for a step of 0.004 on InsideBarTrailing between 20 and 40 bars. Held out, two of §M29's seven picks now pay where none did: the selection window's best binding rung on InsideBar and InsideBarTrailing is the loosest, 80 bars, and it returns +0.008 and +0.002, on both roots at two of four bar sizes. **EmaPullback, read here for the first time, gains held out at every rung while costing on the selection window at every rung** — the window's sign again, as §M37 found for its trail.

### §M48 — the conditional early exit

([`m48-early-exit-result.md`](m48-early-exit-result.md).) The selection window's pick per archetype × resolution cell, read held out, paying on both roots at p < 0.05: **11 of the 44 cells clear, against 13.** The two that no longer clear are OpeningRange at 10 minutes and SqueezeBreakout at 10, the two stop entries at a level. Every other clearing cell is the one §M48 had, mostly with the same pick and to the third decimal:

| cell                             | §M48, held out MNQ / NQ | re-swept              |
| -------------------------------- | ----------------------- | --------------------- |
| DeadCatBounce 2m                 | +0.0002 / +0.0027       | +0.0002 / +0.0027     |
| DeadCatBounce 5m                 | +0.0053 / +0.0147       | +0.0053 / +0.0148     |
| DeadCatBounce 10m                | +0.0582 / +0.0206       | +0.0581 / +0.0209     |
| EmaPullback 5m                   | +0.0025 / +0.0036       | +0.0026 / +0.0036     |
| EmaPullback 10m                  | +0.0156 / +0.0093       | +0.0158 / +0.0092     |
| InsideBar 5m                     | +0.0034 / +0.0219       | +0.0034 / +0.0219     |
| **InsideBarTrailing midday 10m** | **+0.0705 / +0.0838**   | **+0.0719 / +0.0838** |
| PullBackAndGo 10m                | +0.0160 / +0.1042       | +0.0205 / +0.1064     |
| PullBackAndGo 15m                | +0.0165 / +0.0480       | +0.0174 / +0.0494     |
| SqueezeBreakout 2m               | +0.0004 / +0.0013       | +0.0010 / +0.0016     |
| SqueezeBreakout 5m               | +0.0007 / +0.0015       | +0.0011 / +0.0020     |

Five of the eleven clear by less than 0.005 on a root, against seven of thirteen. **The one sizeable gain is still the trend exit in InsideBarTrailing's midday cell at 10 minutes, and at 5 minutes, where the cell is traded, the pick still costs**: −0.187 and −0.148 held out.

### §M50 — the exit's second tier, now with 5 minutes

([`m50-early-exit-tier-2-result.md`](m50-early-exit-tier-2-result.md).) At 15 and 10 minutes **1 of the 22 cells still clears, the same one**: EmaPullback at 10 minutes with the breakeven stop at 1 R, +0.0037 and +0.0042 held out against §M50's +0.004 on each root. Its 5-minute pass, which §M50 had not run, was swept in the re-sweep and read by the same rule. **3 of its 11 cells clear**: DeadCatBounce, with an excursion exit at 1 R, by +0.0036 and +0.0140; EmaPullback, with the same breakeven stop, by +0.0021 and +0.0020; and InsideBar, with a stepped stop, by +0.0126 and +0.0569. InsideBar is the archetype §M50 predicted the late stop would help and found it cost in 34 of 36 held-out cells at 10 and 15 minutes; at 5 minutes the selection window picks a different arm, and it pays. Neither midday cell clears at 5 minutes.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#451]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/451
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
[#454]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/454
[#455]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/455
[#471]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/471
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/472
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
