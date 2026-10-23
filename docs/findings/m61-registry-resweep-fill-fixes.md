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

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#451]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/451
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
[#454]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/454
[#455]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/455
[#471]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/471
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/472
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
