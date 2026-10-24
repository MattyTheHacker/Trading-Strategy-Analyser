---
id: M61
title: "M61 — every older campaign re-read on the October 2026 re-sweep: most findings hold, and they move where the fill fixes reached a stop entry"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [439]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  Re-read on the October 2026 re-sweep, most of the registry's findings hold and InsideBarTrailing's reproduce to the third decimal; what moved is where the fill fixes reached a stop entry. Read along its fill bar's path, OpeningRange's fade at its tightest stop now holds out profitably on all forty shortlisted configurations, and EmaPullback's confirmation entry now clears its pre-registered paired bar in five of eight cells; OpeningRange's trend=UP and its 10-bar regime cell no longer clear gate 3, and SqueezeBreakout's unfiltered entry is now worse than a random one.
---

# M61 — every older campaign re-read on the October 2026 re-sweep: most findings hold, and they move where the fill fixes reached a stop entry ([#439])

The second re-sweep of every stored campaign. §M44 re-swept the registry onto a repaired archive; since then four fixes to how orders fill have changed rows in every archetype, so no stored control could reproduce itself and [#439] re-swept them all again before any new campaign ran. The campaigns pre-registered before the run have result files of their own. This file re-reads the headline of every campaign that ran before it, on the new rows, against the figures each one published.

## In plain terms

In October 2026 four mistakes in how the backtester fills orders were fixed, each found by checking against NinjaTrader itself. Three of the four affect stops, which every strategy uses. So every stored result was re-run on the corrected code, on the same price history as before.

The fixes moved most results by very little: the typical setting's profit factor changed by less than 0.01 on seven of the nine strategies. The two that moved more are the two that enter on a stop order at a level, OpeningRange and SqueezeBreakout, and both moved up.

The question this file answers is whether anything the project concluded before the re-run still holds. Each older campaign's main claim is re-measured the way it was first measured and set beside its original figure.

**Most of it does.** Which strategies rank where, which settings matter, the held-out tests and most of the comparisons against random entries came back close to what they were; InsideBarTrailing's came back to the third decimal. **What changed is where the fixes reached.** A strategy that enters with a stop order now has its entry bar read the way NinjaTrader reads it, and two results that had been negative are now open questions: OpeningRange fading a broken range with a very tight stop, and EmaPullback waiting for a confirming break before entering. Neither is a strategy yet. A few positive results weakened the same way: OpeningRange in an uptrend no longer beats random entries, and one of its two calibrated trend cells no longer does so convincingly.

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

**Both reproduce.** The walk-forward still passes, the drawdown is still not the trades' ordering, the bootstrap still cannot exclude a loss, and neither cell has a configuration profitable without its forced flat. The prop accounts are not comparable: the gate reads replay the 2026 presets, an evaluation linked to its funded account, where both campaigns replayed the evaluations alone; §M46's re-run below replays the 2026 evaluations alone for that reason, the nearest the replay still has to the presets it used. §M31.1's hold ladder inside the stratum was not re-swept and is not re-read.

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

## ElasticBand

Its stops moved onto the tick grid with [#471], and its passed targets with [#451] and then [#453]. Its campaigns since §M26.5 ran at 1 to 15 minutes; everything here is read at 2 to 15. §M26.4 is not re-run: its comparison of the two band sources needs a shortlist chosen by source, which the null tool cannot take.

### §M26 — the band built

([`m26-elastic-band.md`](m26-elastic-band.md).) §M26's measurements were a per-contract sweep that the campaign grid does not repeat, so only its shape can be re-read here, from the campaign grid's four target ladders on MNQ over the whole series. **The ordering holds: the more patient the target, the higher the median profit factor, at every bar size from 1 to 15 minutes**, and the win rate falls as the target recedes, from 36.2% at −0.5σ to 33.9% at +2.0σ at 15 minutes. No ladder's median reaches 1.0 at any bar size; the best is +2.0σ at 10 minutes, at 0.946. Its gate-2 and gate-3 verdicts are §M27's, above.

### §M26.5 — the signal bar's shape

([`m26-5-signal-bar-shape.md`](m26-5-signal-bar-shape.md).) **The paired reading reproduces: the shape's sign is the window's.** Each shape against `shape=any`, target 0.0σ, median paired difference in profit factor:

| window    | root | reversal            | reclaim         | rejection@0.4   | rejection@0.6   |
| --------- | ---- | ------------------- | --------------- | --------------- | --------------- |
| selection | MNQ  | +0.028 → +0.042     | +0.010 → −0.010 | +0.000 → +0.010 | −0.035 → −0.032 |
| selection | NQ   | −0.029 → −0.057     | −0.069 → −0.086 | −0.061 → −0.070 | −0.059 → −0.067 |
| holdout   | MNQ  | +0.131 → **+0.162** | +0.124 → +0.110 | +0.059 → +0.087 | +0.120 → +0.148 |
| holdout   | NQ   | +0.094 → **+0.102** | +0.123 → +0.113 | +0.079 → +0.090 | +0.094 → +0.104 |

**The drawdown reading weakens.** Across the two ladders and two roots, `reversal`'s held-out shortlist returns its own drawdown in two of four cells rather than four, both on NQ, at net-to-drawdown 2.73 and 3.81; on MNQ it reaches 0.54 and 0.64. `shape=any` now clears one of four, NQ at the 0.0σ ladder, where §M26.5 had it clearing none.

| root | arm      | §M26.5: PF / null / excess, p < 0.05 PF / expectancy, trades | re-swept                               |
| ---- | -------- | ------------------------------------------------------------ | -------------------------------------- |
| MNQ  | any      | 1.034 / 0.908 / +0.073, 3 / 5, 98                            | 1.012 / 0.937 / +0.123, 3 / 6, 88      |
| MNQ  | reversal | 1.526 / 0.902 / +0.645, 4 / 6, 34                            | 1.285 / **0.736** / +0.540, 4 / 10, 68 |
| NQ   | any      | 1.136 / 0.948 / +0.248, 5 / 5, 189                           | 1.243 / 0.953 / +0.284, 2 / 2, 53      |
| NQ   | reversal | 2.301 / 0.931 / +1.355, **12 / 16**, 56                      | 2.545 / 1.015 / +1.469, 8 / 14, **21** |

**It is still not a pass, and the reading that made it worth quoting no longer holds.** §M26.5's case was that requiring a turn left the matched null where it was and moved only the observation, so the excess measured the entry. Now the reversal's null sits 0.20 below the control's on MNQ and 0.06 above it on NQ. And NQ's strongest counts rest on a median of 21 held-out trades.

### §M26.6 — the recovery entry

([`m26-6-recovery-entry.md`](m26-6-recovery-entry.md).) **It reproduces: the recovery entry wins the selection window and gives it back held out.** Median paired difference against each control:

| window    | control  | root | recovery@1.0    | recovery@0.9    | recovery@0.75   |
| --------- | -------- | ---- | --------------- | --------------- | --------------- |
| selection | any      | MNQ  | +0.040 → +0.051 | +0.120 → +0.112 | +0.245 → +0.199 |
| selection | any      | NQ   | +0.059 → +0.071 | +0.131 → +0.131 | +0.156 → +0.141 |
| selection | reversal | MNQ  | +0.018 → +0.029 | +0.077 → +0.076 | +0.219 → +0.190 |
| selection | reversal | NQ   | +0.071 → +0.093 | +0.163 → +0.164 | +0.211 → +0.186 |
| holdout   | any      | MNQ  | −0.001 → −0.013 | −0.012 → +0.003 | −0.025 → +0.024 |
| holdout   | any      | NQ   | +0.007 → +0.003 | +0.007 → +0.017 | −0.016 → +0.001 |
| holdout   | reversal | MNQ  | −0.143 → −0.183 | −0.142 → −0.188 | −0.215 → −0.245 |
| holdout   | reversal | NQ   | −0.085 → −0.091 | −0.094 → −0.102 | −0.117 → −0.109 |

Against the reversal control the held-out cost still deepens with depth, and on the selection window the gain still does. Against `shape=any` the held-out rows no longer worsen with depth: they sit within 0.025 of zero either way. Held out, the deepest arm still fails gate 2 on NQ, and on MNQ it now returns its own drawdown, at 1.06, where §M26.6 had no recovery arm doing so. Under the null the recovery arms are still the worst result with the best-matched trade counts: 0 to 5 of 20 configurations below p = 0.05 on profit factor against the two controls' 8 to 10, each recovery shortlist within 4% of its null's trade count.

### §M26.8 — the stop on the band

([`m26-8-stop-on-band.md`](m26-8-stop-on-band.md).) **It reproduces.** Held out, sorting the seven stop arms by median hold sorts their median profit factor exactly under `shape=any`, as before, and at a rank correlation of 0.71 under `shape=reversal`, against 0.86. The band stop against each other stop, held out, median of the two roots:

| entry    | against     | @0.5σ           | @1.0σ           | @1.5σ           | @2.0σ           |
| -------- | ----------- | --------------- | --------------- | --------------- | --------------- |
| any      | swing       | +0.005 → −0.029 | +0.038 → +0.032 | +0.072 → +0.058 | +0.069 → +0.075 |
| any      | atr         | −0.061 → −0.074 | −0.006 → −0.017 | +0.004 → −0.000 | +0.005 → +0.005 |
| any      | catastrophe | −0.076 → −0.103 | −0.026 → −0.041 | +0.002 → −0.018 | −0.004 → −0.011 |
| reversal | swing       | −0.001 → −0.016 | +0.049 → −0.006 | +0.093 → +0.035 | +0.087 → +0.058 |
| reversal | atr         | −0.092 → −0.128 | −0.072 → −0.096 | −0.023 → −0.021 | +0.004 → −0.026 |
| reversal | catastrophe | −0.090 → −0.131 | −0.048 → −0.080 | −0.013 → −0.024 | +0.002 → −0.006 |

Still monotone in depth against every control but for one step against the ATR stop under `shape=reversal`, still a gain over the tightest stop from 1.0σ or 1.5σ, and **now a cost against the widest at every depth on both entries**, where §M26.8 had it level at 2.0σ. The drawdown check still rises toward the wide stops: of four root × entry cells, `catastrophe` clears three, `band@2.0σ` and `band@1.5σ` two each, and `swing` none. Every arm still beats its null on most of its shortlist — 15 to 20 configurations of 20, median 18 — and the width order still does not order the excess, at a rank correlation of 0.062 against 0.038.

### §M26.9 — the volume requirement

([`m26-9-volume-requirement.md`](m26-9-volume-requirement.md).) Each volume state against its own unfiltered twin under `shape=reversal`, held out, over the nine fitted cuts:

| state  | root | §M26.9: median ΔPF, cuts favourable | re-swept           |
| ------ | ---- | ----------------------------------- | ------------------ |
| HEAVY  | MNQ  | −0.056, 0 of 9                      | −0.025, **5 of 9** |
| HEAVY  | NQ   | −0.081, 1 of 9                      | −0.067, 1 of 9     |
| NORMAL | MNQ  | +0.071, 9 of 9                      | +0.085, 9 of 9     |
| NORMAL | NQ   | +0.043, 8 of 9                      | +0.047, 8 of 9     |

**`NORMAL` is still a gain on 17 of 18 cuts; `HEAVY` is a cost on 12 of 18 rather than 17**, the MNQ half now a coin flip. The selection window still cannot see either. `NORMAL` still returns its own drawdown held out in 15 of its 18 cells, against 16, and `HEAVY` in one, as before. Under the null, `NORMAL` still carries MNQ's strongest count and almost nothing on NQ, 13 and 3 of 20 against 14 and 5; `HEAVY` still fails below the unfiltered baseline on both roots, at 1 and 4 of 20 against 6 and 9.

### §M33 — the channel against the shape

([`m33-channel-volume.md`](m33-channel-volume.md).) The same pairing on both channels, held out:

| shape    | state  | channel   | §M33, MNQ / NQ: median ΔPF, cuts favourable | re-swept              |
| -------- | ------ | --------- | ------------------------------------------- | --------------------- |
| any      | HEAVY  | bollinger | +0.044, 9 / +0.041, 9                       | +0.021, 7 / +0.031, 7 |
| any      | HEAVY  | vwap      | −0.013, 4 / +0.003, 5                       | −0.013, 6 / +0.005, 5 |
| any      | NORMAL | bollinger | −0.019, 1 / −0.025, 1                       | −0.005, 2 / −0.011, 2 |
| any      | NORMAL | vwap      | +0.023, 6 / +0.007, 5                       | +0.043, 7 / +0.025, 7 |
| reversal | HEAVY  | bollinger | +0.015, 7 / +0.023, 5                       | −0.019, 3 / +0.000, 5 |
| reversal | HEAVY  | vwap      | −0.056, 0 / −0.081, 1                       | −0.025, 5 / −0.067, 1 |
| reversal | NORMAL | bollinger | −0.036, 2 / −0.027, 2                       | −0.025, 3 / −0.020, 4 |
| reversal | NORMAL | vwap      | +0.071, 9 / +0.043, 8                       | +0.085, 9 / +0.047, 8 |

**`NORMAL`'s sign is still the channel's**, on both roots under both shapes: a gain on the VWAP band and a cost on Bollinger. **`HEAVY`'s flip is now partial**: on Bollinger it is still a gain under `shape=any`, at 7 of 9 cuts on each root, but under `shape=reversal` it is level or a cost. The finding that a context result belongs to a configuration rather than to the archetype holds; that both states flip with the channel does not.

## The gate-3 families named by a rule, and the bar sizes they are named at

§M19.3, §M35, §M36, §M37 and §M39 each named its gate-3 family by a rule over gate 2 — the strata clearing on both roots, at most so many, by mean held-out profit factor. On the re-swept rows the rule was first applied over 2 to 30 minutes, which let 30-minute configurations into both the naming and the shortlists. **Here every family is re-named and re-run at 2 to 15 minutes, as each campaign first ran, and all five name different strata than they did at 2 to 30.** That is a measure of how much a family named by a rule depends on what it is named over.

## SqueezeBreakout

### §M19.3 — the squeeze swept

([`m19-3-squeeze-breakout-swept.md`](m19-3-squeeze-breakout-swept.md).) **Gate 1 reproduces closely, gate 2 names different strata, and gate 3 turns its unfiltered "no" into "worse than random".**

| claim                                                     | §M19.3                                                                          | re-swept                                                                                   |
| --------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| pooled, cells majority-profitable on the selection window | 0 of 8                                                                          | 0 of 8, best 46.3%                                                                         |
| opposite-extreme stop                                     | 3 cells: MNQ 15m, NQ 10m and 15m                                                | the same 3, at 59.5%, 55.4% and 61.9%                                                      |
| long side                                                 | every cell at 10 and 15 minutes                                                 | the same, 55.0% to 77.1%                                                                   |
| short side                                                | below 30% everywhere                                                            | below 30% everywhere                                                                       |
| rank correlation across the split, pooled                 | +0.732, highest at 2 minutes                                                    | +0.674, highest at 2 minutes (0.823, 0.763)                                                |
| axes whose ordering holds across the split                | 8 of 10; not the squeeze's window or form                                       | 6 of 10; not the squeeze's form, window or depth, nor `tp_multiplier`                      |
| strata clearing gate 2 on both roots                      | 6: `PRE_OPEN`, `compression=NORMAL`, `THIN`, `trend=UP`, `HEAVY`, `DIRECTIONAL` | 7: `htf=BELOW`, `LONDON`, `MIDDAY`, `PRE_OPEN`, `DIRECTIONAL`, `trend=DOWN`, `trend=MIXED` |

Gate 3, the family named at 2 to 15 minutes — unfiltered plus the seven — best five per cell, 200 draws: **1 of 80 tests clears p = 0.05 in the better direction, NQ's `MIDDAY`, and 10 clear in the worse direction, nine of them unfiltered.** §M19.3's unfiltered answer was that nothing beat a random entry; now no unfiltered configuration beats its null on either root, and four on MNQ and five on NQ are significantly worse than one, at a median p of 0.010 and 0.030, on a median of 124 and 119 held-out trades. `trend=UP`, the one short entry that cleared §M19.3's bar on both roots, is no longer in the family, since it no longer clears gate 2 on both roots. The squeeze adds nothing measurable, as before, and its unfiltered break of a compressed window is now worse than a random entry at the same minute.

## EmaPullback

Its stop on the slow average moved onto the tick grid with [#471], and its confirmation entry, a stop order, is read along the fill bar's path with [#472]. §M35 ran on a series from 2024 only; §M37 and §M39 on the archive §M38 describes; all of them before §M44.

### §M35 — the pullback swept

([`m35-ema-pullback-swept.md`](m35-ema-pullback-swept.md).) **Gate 1 reproduces exactly in count; gate 3 still fails.** Five of eight root × resolution cells are majority-profitable on the selection window, the same five — MNQ at 10 and 15 minutes and NQ at 5, 10 and 15 — and every cell but MNQ at 2 minutes loses profitable share across the split, the coarse ones most. The rank correlation across the split is −0.069, negative in four of eight cells against seven, still most negative at 15 minutes on both roots, where gate 1 likes it best. Five strata clear gate 2 on both roots, as before: `CASH_OPEN`, `LONDON` and `MIDDAY` again, now with `CLOSE` and `volume=THIN` where §M35 had `compression=NORMAL` and `trend=MIXED`. `phase=CASH_OPEN` returns its own drawdown on both roots now, and `LONDON` too, where §M35 had MNQ's `CASH_OPEN` alone.

**The two axes the archetype invented still hold their ordering across the split**, `touch_mode` and `min_bars_extended`. The slow average's two axes still invert — `slow_period` again the largest, monotone the other way in each window — but the fast average's kind and period now keep their order, at 0.8 and 0.4. `require_turn`, which §M35 called a coin flip at 3.3 points of held-out profitable share on a balanced panel, is now worth 15 points on the unfiltered rows held out: 30.9% against 15.9%.

Gate 3 on the family named at 2 to 15 minutes, best five per cell, 400 draws: **0 of 50 tests clear p = 0.05 in the better direction and 3 in the worse**, all NQ's `volume=THIN`. 35 of the 50 hold fewer than 30 held-out trades, median 21.

### §M36 — volume re-cut

([`m36-ema-pullback-volume-recut.md`](m36-ema-pullback-volume-recut.md).) Scored over the same eight root × resolution cells §M36 used:

| cut                              | `THIN`, score and held-out PF | `NORMAL`      | `HEAVY`       |
| -------------------------------- | ----------------------------- | ------------- | ------------- |
| raw 0.7/1.5                      | +8 → +7, 1.01                 | +8 → +8, 0.99 | −6 → −6, 0.91 |
| `per_bar_20 q=0.10/0.90`         | +6 → +6, 1.01                 | +8 → +8, 0.98 | −8 → −8, 0.89 |
| `per_bar_20 q=0.20/0.80`         | +8 → +7, 1.02                 | +8 → +8, 0.99 | −7 → −8, 0.90 |
| `per_bar_20 q=0.33/0.67`         | +8 → +8, 1.01                 | +8 → +8, 1.01 | −6 → −6, 0.92 |
| `rolling_30_20 q=0.10/0.90`      | +6 → +3, 0.91                 | +8 → +8, 1.01 | −8 → −8, 0.78 |
| `rolling_30_20 q=0.20/0.80`      | +8 → +6, 0.98                 | +7 → +8, 1.03 | −8 → −8, 0.83 |
| `rolling_30_20 q=0.33/0.67`      | +8 → +6, 0.99                 | +4 → +6, 1.06 | −7 → −7, 0.87 |
| `session_to_date_20 q=0.10/0.90` | +5 → +6, 0.99                 | +7 → +8, 1.00 | −8 → −7, 0.85 |
| `session_to_date_20 q=0.20/0.80` | +8 → +4, 0.95                 | +7 → +8, 1.01 | −8 → −6, 0.88 |
| `session_to_date_20 q=0.33/0.67` | +8 → +8, 1.00                 | +4 → +5, 0.98 | −7 → −7, 0.90 |

**`HEAVY` is still negative at every cut**, which §M36 called the one statement no choice of form or tail could move, and it still is. **`THIN` is no longer the state that reaches the maximum**: +8 at two fitted cuts rather than six, while `NORMAL` now reaches it at seven. The held-out profit factors beside the scores run 0.91 to 1.06 for `THIN` and `NORMAL` and 0.78 to 0.92 for `HEAVY`. Gate 2 reproduces in count: six fitted cells clear on both roots and 19 on at least one, as before; one raw cell now clears on both, where none did. Gate 3 on the 11 cells named at 2 to 15 minutes: **2 of 110 tests clear in the better direction and 6 in the worse**, on a median of 28 held-out trades with 62 of the 110 under 30. It fails, as before.

### §M37 — trailing the stop on the slow average

([`m37-ema-pullback-trail-on-slow.md`](m37-ema-pullback-trail-on-slow.md).) **It reproduces: the trail's effect takes the window's sign.** Paired against the fixed stop, unfiltered:

| root | resolution | §M37, selection Δ / holdout Δ | re-swept            |
| ---- | ---------: | ----------------------------- | ------------------- |
| MNQ  |          2 | −0.021 / −0.007               | −0.033 / −0.004     |
| MNQ  |          5 | −0.028 / **+0.036**           | −0.035 / **+0.036** |
| MNQ  |         10 | −0.017 / **+0.036**           | −0.015 / **+0.030** |
| MNQ  |         15 | −0.014 / **+0.014**           | −0.018 / **+0.020** |
| NQ   |          2 | +0.003 / −0.003               | −0.015 / +0.003     |
| NQ   |          5 | −0.011 / **+0.028**           | −0.025 / **+0.033** |
| NQ   |         10 | −0.008 / **+0.030**           | −0.008 / **+0.029** |
| NQ   |         15 | −0.010 / **+0.016**           | −0.012 / **+0.023** |

A cost on the selection window in all eight cells now, against seven, and a gain held out in seven, six of them significant, so it still clears §M37's bar in none. The trail still clears gate 2 in more strata than the fixed stop, nine on both roots against five. Gate 3 on the six strata named at 2 to 15 minutes: **0 of 60 tests clear in either direction under either arm**, against one each; the trail beats its null in 46 of 60 and the fixed stop in 44.

**§M37's own deferral, the trail inside §M36's fitted volume cells, is read here for the first time**, over §M36's 11 cells named at 2 to 15 minutes, best five per cell, 400 draws. The trailed arm clears in the better direction on 6 of 110 tests and the fixed stop on 2, against 3 and 6 in the worse; the cells hold a median of 28 held-out trades under both. Neither is evidence of anything.

### §M39 — the confirmation entry, and the verdict reverses

([`m39-ema-pullback-confirmation-entry.md`](m39-ema-pullback-confirmation-entry.md).) **This is the second-largest change the fills made to a finding.** §M39's pre-registered bar: the one-bar confirmation against the market entry, unfiltered, paired per root × resolution, counts as an improvement only where its median difference is positive and the sign test reaches p < 0.05 in both windows.

| root | resolution | §M39, selection Δ (p) / holdout Δ (p) | re-swept                            | clears  |
| ---- | ---------: | ------------------------------------- | ----------------------------------- | :-----: |
| MNQ  |          2 | +0.030 (\<0.001) / −0.014 (0.002)     | +0.022 (\<0.001) / +0.001 (0.95)    |   no    |
| MNQ  |          5 | +0.031 (\<0.001) / −0.016 (0.002)     | +0.014 (0.001) / −0.005 (0.14)      |   no    |
| MNQ  |         10 | +0.055 (\<0.001) / +0.014 (0.079)     | +0.044 (\<0.001) / +0.018 (\<0.001) | **yes** |
| MNQ  |         15 | +0.041 (\<0.001) / +0.018 (0.103)     | +0.014 (0.007) / +0.051 (\<0.001)   | **yes** |
| NQ   |          2 | +0.029 (\<0.001) / −0.002 (0.75)      | +0.024 (\<0.001) / +0.012 (0.012)   | **yes** |
| NQ   |          5 | +0.029 (\<0.001) / −0.016 (\<0.001)   | +0.014 (0.001) / −0.005 (0.40)      |   no    |
| NQ   |         10 | +0.057 (\<0.001) / +0.009 (0.171)     | +0.052 (\<0.001) / +0.037 (\<0.001) | **yes** |
| NQ   |         15 | +0.055 (\<0.001) / +0.005 (0.845)     | +0.022 (\<0.001) / +0.039 (\<0.001) | **yes** |

**The one-bar confirmation now clears its bar in five of eight cells, at 10 and 15 minutes on both roots and at 2 minutes on NQ, where §M39 had it clearing none.** Its held-out gains at 10 and 15 minutes, which §M39 found no sign test could separate from zero, now improve 64% to 80% of pairs. At 5 minutes it still costs held out, now insignificantly. The confirmation is a stop order beyond the signal bar, which [#472] reads along the fill bar's path, and the market entry is not, so the fix moved one arm of the pair and not the other.

**Gate 3 changes with it.** On the six strata the rule names at 2 to 15 minutes, best five per cell, 400 draws, the market entry now clears p = 0.05 in the better direction on both roots in `phase=LONDON`, at two configurations on MNQ and one on NQ, and the one-bar confirmation in `phase=CLOSE`, at two and one. §M39's verdict was that no arm cleared any stratum on both roots. Two cautions travel with it: three tests of sixty at that level are what chance gives, and `CLOSE` is the hour the forced flat closes. Resting the order three bars is still worse than one on the selection window, now significantly in five of eight cells against eight, and still mostly level held out.

**It is a candidate for a pre-registered test, not a strategy.** The paired gain held out is one to five hundredths of profit factor, on an archetype whose median configuration loses held out, and no gate-4 read has been run on it.

## EmaCrossover's loose ends, the other markets and the context re-cuts

### The build spec's three loose ends

([`build-spec-loose-ends-measured.md`](build-spec-loose-ends-measured.md).) **All three verdicts hold.** The trail on the moving average costs held out in all 16 stop × root × resolution cells, against 19 of 20, and on the selection window in 14 of 16. The round-number rule moves median profit factor by 0.001 or less in every cell, while several sign tests still reach p = 0.05, which is the multiple-comparisons pattern the file named. The confluence count is no longer even a gradient: held out, requiring all three conditions gives a median profit factor of 0.956 on 62 trades, two of three 1.034, and any one 0.986, where the file had them ordered 1.063, 1.024 and 0.987. Its matched null over counts was not re-run, because the null tool cannot shortlist by count; [§M59](m59-confluence-not-read-result.md) re-asked the question over conditions that read no moving average and found no edge either ([`confluence-count-per-trade.md`](confluence-count-per-trade.md) is the earlier read).

### The gold strata

([`gold-strata-result.md`](gold-strata-result.md).) Re-picked on the re-swept rows by the pre-registration's own rule — gate-2 passes at 5, 10 and 15 minutes with a held-out `session_close_share` at or below 0.30, held on both roots of a pair — the stratified layer is **112 pairs and 4,480 tests**, against 68 and 2,720. The rule's verdict is the same:

|        | prediction                              | required                                   | §M61                               |          |
| ------ | --------------------------------------- | ------------------------------------------ | ---------------------------------- | -------- |
| **P1** | EmaCrossover's gold pairs clear         | ≥ 4 of its pairs, and gold rate > S&P rate | **1 of 18** (0.056), S&P 0.375     | **FAIL** |
| **P2** | the advantage is gold-specific          | S&P clears at a lower rate                 | **S&P clears about 7× as often**   | **FAIL** |
| **P3** | the family is not noise                 | > 1.5× the chance count                    | 509 of 4,480 against 224 by chance | pass     |
| **P4** | InsideBar clears fewer gold pairs       | fewer than EmaCrossover                    | 0 of 5 against 1 of 18             | pass     |
| **P5** | SqueezeBreakout clears fewer gold pairs | fewer than EmaCrossover                    | 0 of 13 against 1 of 18            | pass     |

**EmaCrossover-on-gold is still one lucky cell rather than an edge.** Its one clearing gold pair is now `volume=HEAVY` at 10 minutes, the unfiltered cell being outside the stratified layer; its S&P pairs clear three of eight, `htf=BELOW` at 20 and 19 of 20 configurations. Every other clearing pair in the family is S&P: EmaCrossover's three at 5 minutes, and InsideBar's and InsideBarTrailing's two each at 10 and 15.

### Cross-root transfer

([`cross-root-transfer.md`](cross-root-transfer.md).) The re-sweep stored the campaign grids on ES, MES, GC and MGC, so the transfer is read from stored rows rather than re-run: the top 200 per archetype on the source root's selection window, at 500 trades or more and an `ambiguous_share` within `disambiguate`'s floor, looked up on the target roots' whole series. Unlike the original, the pool is each archetype's campaign variants in the raw strata at 2 to 15 minutes. From NQ:

| archetype         | selection | own holdout | ES    | GC    | instrument cost, §M61 | the file's |
| ----------------- | --------- | ----------- | ----- | ----- | --------------------- | ---------- |
| InsideBar         | 1.332     | 1.032       | 1.060 | 0.964 | −0.020                | −0.006     |
| InsideBarTrailing | 1.349     | 1.012       | 0.980 | 1.044 | +0.000                | +0.162     |
| EmaCrossover      | 1.308     | 0.995       | 0.974 | 1.004 | −0.006                | −0.031     |
| SqueezeBreakout   | 1.375     | 0.989       | 0.911 | 0.988 | −0.040                | −0.079     |
| EmaPullback       | 1.374     | 1.050       | 0.982 | 0.984 | −0.067                | −0.092     |
| OpeningRange      | 1.266     | 1.128       | 1.039 | 1.062 | −0.077                | −0.191     |
| PullBackAndGo     | 0.915     | 0.844       | 0.622 | 0.788 | −0.139                | −0.292     |
| ElasticBand       | 1.324     | 1.010       | 0.847 | 0.827 | −0.173                | −0.213     |
| DeadCatBounce     | 0.877     | 0.960       | 0.540 | 0.728 | −0.326                | −0.070     |

**From NQ the finding holds**: most of what a shortlist loses is the selection, and the inside-bar pair and EmaCrossover travel at almost no further cost. **From MNQ it no longer does for the inside-bar pair**, which loses 0.18 more on the micros, against the file's +0.020 and −0.042. Nothing reaches a median profit factor of 1.1 on any new root, as before; the best are OpeningRange on GC at 1.062 and InsideBar on ES at 1.060. The cross-instrument preference the file named, the inside-bar pair for gold and EmaPullback for the S&P, does not reproduce: InsideBar now does better on ES, and EmaPullback is level between the two. **OpeningRange's clock is now on all four roots**, with 0.45 to 0.55 of its legs closed by the flatten, where the file had it on the micros alone. The full-size roots still beat their micros, on all nine archetypes on the S&P and eight on gold.

### §M30 and §M32 — the context re-cuts

([`m30-volume-regime-recut.md`](m30-volume-regime-recut.md), [`m32-volume-windows.md`](m32-volume-windows.md).) Re-scored by §M54 on the re-swept rows over eight root × resolution cells rather than ten, so a score now runs to ±8. The labels are properties of the bars, which have not changed since §M44, so what is re-read is the scores and the held-out profit factors beside them.

| cell                                                 | §M30 or §M32: score, held-out PF | §M61: score of 8, held-out PF |
| ---------------------------------------------------- | -------------------------------- | ----------------------------- |
| ElasticBand `HEAVY@rolling_30_20 q=0.20/0.80`        | +10, 0.972                       | +7, 0.985                     |
| ElasticBand `HEAVY@rolling_30_20 q=0.33/0.67`        | +10, 1.001                       | +6, 0.978                     |
| ElasticBand `HEAVY@session_to_date_20 q=0.10/0.90`   | +10, 0.981                       | +7, 0.981                     |
| EmaCrossover `NORMAL@rolling_30_20 q=0.20/0.80`      | +9, 0.990                        | **+1**, 0.958                 |
| EmaCrossover `NORMAL@rolling_30_20 q=0.33/0.67`      | +8, 0.974                        | **+2**, 0.946                 |
| OpeningRange `THIN@per_bar_20 q=0.20/0.80`           | +9, 1.036                        | +6, 1.078                     |
| OpeningRange `NORMAL@per_bar_20 q=0.20/0.80`         | +8, 0.949                        | +4, 0.973                     |
| OpeningRange `NORMAL@session_to_date_20 q=0.33/0.67` | −9                               | −4, 0.838                     |
| InsideBar `NORMAL@rolling_10_20 q=0.20/0.80`         | +8, **1.051**                    | **+8, 1.091**                 |
| EmaCrossover `NORMAL@rolling_10_20 q=0.10/0.90`      | +10, 0.988                       | +7, 0.992                     |

**ElasticBand's `HEAVY` re-cut still holds and still loses money; EmaCrossover's `NORMAL` cells no longer score as consistent; and InsideBar's ten-bar rolling cell, the one §M32 named, holds**, at the maximum score and a held-out profit factor of 1.091. OpeningRange's fitted `DIRECTIONAL` cells still score at or near the maximum at every lookback. §M32's reading that a new rung is consistent at about the default's rate also holds: of 1,215 fitted volume cells across the nine archetypes, 14 of 243 at the default windows reach ±8 and 66 of 972 at the other rungs.

### §M41 — when the flatten happens

([`m41-flatten-timing.md`](m41-flatten-timing.md).) **It reproduces exactly where it matters.** At 5 minutes, the bar size the two candidate cells trade at, the live 180-second cutoff selects the same bars as the backtested 30 seconds: no configuration of either midday cell moves on either root. A whole 5-minute bar earlier moves the median held-out profit factor by at most 0.002 on InsideBarTrailing and 0.011 on OpeningRange, and a whole 15-minute bar earlier by at most 0.019 at any bar size.

## The prop accounts

The re-sweep's prop reads replay each firm's 2026 evaluation linked to its funded account ([#440]), as §M51 did. §M40, §M43, §M46 and §M28.13 read the evaluations alone, on presets that have since been replaced ([#441]), so their re-reads below are on different accounts and compare in direction rather than in dollars. §M46's and §M28.13's were run for this file on the 2026 evaluations without their funded accounts, the nearest the replay still has to the presets they used.

### §M40 — ranking by what a prop trader wants

([`m40-prop-objectives.md`](m40-prop-objectives.md).) Every objective's top 20 against the profit-factor top 20, held out, over the eleven unfiltered and midday cells on both roots and 30 account presets:

| objective        | better at its own objective, held out | net better / worse | change in the share ever funded |
| ---------------- | ------------------------------------- | ------------------ | ------------------------------- |
| `pass_rate`      | 129 to 50, p 3e-9                     | 101 / 133          | +7.5 points                     |
| `fees_per_pass`  | 142 to 43, p 2e-13                    | 119 / 125          | +12.0                           |
| `days_to_payout` | 124 to 31, p 2e-14                    | **149 / 97**       | +15.7                           |
| `funded_days`    | 157 to 52, p 2e-13                    | 73 / 91            | −3.9                            |

**It reproduces: every objective's ordering transfers, and only `days_to_payout` also pays**, now at p = 0.001 on net. The level still does not transfer: a funded account the selection window expected to last a median 898 trading days lasts 68 held out on MNQ.

### §M43 — the two midday candidates ranked

([`m43-midday-candidates-ranked.md`](m43-midday-candidates-ranked.md).) InsideBarTrailing's `phase=MIDDAY` against OpeningRange's, each objective's top 20, across the fifteen 2026 accounts:

| ranked by        | root | the objective itself, IBT – OR | net held out | profit factor | session-close share lower |
| ---------------- | ---- | ------------------------------ | ------------ | ------------- | ------------------------- |
| `days_to_payout` | MNQ  | **13 – 1** (4 – 3 in §M43)     | 13 – 2       | 11 – 4        | 15 – 0                    |
| `days_to_payout` | NQ   | **13 – 0**                     | 10 – 5       | 13 – 2        | 15 – 0                    |
| `fees_per_pass`  | MNQ  | **9 – 5** (3 – 4 in §M43)      | 10 – 5       | 13 – 2        | 15 – 0                    |
| `fees_per_pass`  | NQ   | **12 – 1**                     | 6 – 9        | 13 – 2        | 15 – 0                    |

**The choice holds, and the objectives now agree with what they are read beside.** §M43's MNQ objectives split evenly between the two cells; on the re-swept rows InsideBarTrailing wins both, and its session-close share is still well below OpeningRange's, 0.23 to 0.37 against 0.61 to 0.64. **The configuration §M43 named does not survive.** Its rule took the configurations that pass the exclusion read on both of gate 4's thresholds, and none of the re-swept held-out twenty does (§M42 above), so the rule names nothing; the stored configuration numbers also changed with the re-sweep.

### §M51 — when each account pays back

([`m51-prop-payback-timing.md`](m51-prop-payback-timing.md).) **InsideBarTrailing's midday cell reproduces to the dollar on its account**: TopStep 50K pays back on every configuration, at a median +$13,378 in 36 trading days, and LucidFlex 50K is second at +$8,956, both exactly §M51's. **OpeningRange's midday cell pays back less**: TopStep 50K at +$1,179 in 235 days on 90% of configurations, against +$6,806, and LucidFlex 50K at +$2,472 against +$6,580. The stop entry is again the archetype the fills moved. Apex still pays only on its 50K end-of-day account, and every 150K account is still weak.

### §M46 — every shortlist at each contract count

([`m46-registry-size-ladder.md`](m46-registry-size-ladder.md).) The same 55 shortlists through the same ladder, one to twenty MNQ contracts and one to four NQ, attempts uncapped. [#441] removed the four presets §M46 replayed, so this replays the nearest the replay still has: each firm's 2026 evaluation without its funded account, Apex's intraday-trail evaluations and TopStep's Combines at 50K and 150K. Apex's trail is now $2,000 on 50K and $4,000 on 150K, against §M46's $2,500 and $5,000. TopStep's Combine, as `propaccount` models it, has no daily loss limit, where §M46's TopStep presets failed an account on a $1,000 day on 50K and a $3,300 one on 150K. **So the dollars do not compare, and nor does TopStep's count of shortlists that pay**; what follows compares in direction.

**InsideBarTrailing's midday cell shows how much the accounts alone move.** Its trades did not move (§M51 above reproduces to the dollar), yet its best size on Apex 50K is now four at +$4,500, against §M46's six at +$31,900, and on Apex 150K it loses at every size, where §M46 had it peak at ten to twelve. Both TopStep Combines now rise to the top of the ladder, where §M46's TopStep 150K peaked at sixteen.

**Size still moves nothing but the dollars.** All 645 rung checks ran on the bars the stored row was swept on, and every archetype but InsideBarTrailing reproduced its stored trade count at every size. InsideBarTrailing again reproduces only at its stored six, 20 of 20 on both MNQ shortlists, and between 0 and 10 of 20 at every other size. The floor of one contract per target is unchanged, shortlist by shortlist.

Shortlists with at least one size at which the median net is positive, §M46's count in brackets:

| root | Apex 50K     | TopStep 50K   | Apex 150K   | TopStep 150K  |
| ---- | ------------ | ------------- | ----------- | ------------- |
| MNQ  | 10 of 28 (7) | 23 of 28 (20) | 3 of 28 (7) | 22 of 28 (22) |
| NQ   | 1 of 27 (1)  | 22 of 27 (1)  | 1 of 27 (1) | 21 of 27 (13) |

**On Apex 50K the three archetypes that pay on MNQ are still the three**: InsideBar, InsideBarTrailing (unfiltered and midday) and OpeningRange's opposite-extreme stop at 15 and 30 minutes, joined now by three of its ATR-stop shortlists, one of them by a dollar. On Apex 150K only three pay at all, InsideBar, InsideBarTrailing's unfiltered shortlist and OpeningRange's 30-minute R ladder, the last two by under $1,000.

The best size on Apex 50K, MNQ, with the attempts and passes the median configuration takes there:

| shortlist                                 |                        §M46 |                       §M61 |
| ----------------------------------------- | --------------------------: | -------------------------: |
| InsideBar                                 | 20: +168,600, 309.5 att, 10 | 10: +37,100, 360.5 att, 25 |
| InsideBarTrailing, unfiltered             |     4: +33,700, 58.5 att, 7 |    4: +8,600, 171.5 att, 9 |
| InsideBarTrailing, midday                 |     6: +31,900, 29 att, 3.5 |       4: +4,500, 62 att, 4 |
| OpeningRange 30m, opposite stop, width    |       4: +23,600, 56 att, 6 |       3: +4,200, 88 att, 4 |
| OpeningRange 15m, opposite stop, width    |       4: +22,100, 45 att, 3 |       3: +4,300, 96 att, 4 |
| OpeningRange 15m, opposite stop, R ladder |       4: +15,000, 69 att, 4 |      4: +1,600, 172 att, 4 |
| OpeningRange 30m, opposite stop, R ladder |        4: +9,900, 63 att, 4 |        4: +700, 142 att, 2 |

Figures rounded to the nearest hundred dollars.

**The sizes hold and the dollars fall four- to fourteenfold.** Everything but InsideBar is best at three or four contracts: OpeningRange at its stored four or one below, InsideBarTrailing at four, below its stored six. On the midday cell, whose trades are unchanged, sevenfold is the accounts alone; OpeningRange's R-ladder shortlists fall further, nine- and fourteenfold, as its midday cell fell in §M51 above, but the ladder cannot separate the fills from the accounts. **InsideBar is again the exception, and on the 2026 evaluation its ladder turns**: its median passes reach 25 at six and at ten contracts and fall to 5.5 at twenty, where the median configuration loses, so its best is ten rather than the top of the ladder; on Apex 150K its best is ten too.

**On NQ the floor still decides Apex and no longer decides TopStep.** At four NQ contracts all 27 shortlists lose at the median on Apex 50K, and InsideBar pays there only at one contract, +$34,200 over 367 attempts, losing from two (§M46: best at three, +$105,000). On the TopStep 50K Combine 22 of 27 pay at four NQ contracts, every four-target archetype but DeadCatBounce among them: EmaCrossover's ATR stop at +$237,600 and OpeningRange's 30-minute opposite-stop R ladder at +$218,500, for instance. **§M46's "the four-target archetypes cannot be traded on an NQ 50K account" holds on the 2026 Apex evaluation and not on the 2026 Combine as modelled.** The plainest difference is the daily loss limit, which at four NQ contracts is 12.5 points, but the ladder does not measure it. **None of that reaches a funded account.** The ladder replays the Combine alone; the Express Funded Account a pass opens allows two contracts until it has made $1,500 and three until $2,000, so a bracket of four NQ contracts that passes the Combine can never trade the account that pays. TopStep 150K's funded account and Apex 50K's start below four as well. MNQ is not affected, since twenty micros count as two full-size contracts. A ladder through the linked accounts was not run.

**Every step up in size still buys more resets**: across the 55 shortlists and four presets the median attempt count rises at 874 of 912 steps from one size to the next, stays level at 37 and falls at 1 (§M46: 898, 11 and 3).

No replay was cut short. 94 report reaching the attempt cap, all of them OpeningRange on NQ at four contracts on Apex 50K; the cap is the replay's trade count, so each held-out trade there opened a fresh account.

### §M28.13 — the registry read through an account

([`m28-13-account-read.md`](m28-13-account-read.md).) Its population run, every stored held-out configuration capped at five attempts, is not rebuilt. Its three findings are re-read from the §M46 ladder above at four contracts, the campaign's fixed size, and from one added check that changes only the excursion order, run on two of the ladder's shortlists through the same 2026 evaluations.

**Survival is still not the question.** At four contracts no NQ configuration survives its first account on any of the four presets, 0 of 532 (§M28.13: 0 of 526), and on MNQ 93% breach their first Apex 50K evaluation (98%). The sequence still pays where the accounts die: InsideBar's MNQ shortlist takes a median 147.5 attempts on Apex 50K and nets a profit on every configuration. **And net still rewards variance.** Of the MNQ configurations that lose held out, 39 of 325 net a profit on Apex 50K, and on the TopStep 50K Combine 208 of 325 do, with 258 of 336 on NQ.

**The binding constraint is still position size**, which is the ladder above.

**The excursion order still decides NQ, and no longer leaves MNQ alone.** Apex 50K at four contracts, **only the order changes**:

|                  | n   |      attempts |   passes |                 net |     net > 0 |
| ---------------- | --- | ------------: | -------: | ------------------: | ----------: |
| InsideBar MNQ    | 20  | 147.5 → 139.5 |  19 → 23 | +$29,653 → +$41,481 | 100% → 100% |
| OpeningRange MNQ | 20  |    138 → 96.5 |   5 → 18 |  +$3,616 → +$25,265 | 100% → 100% |
| InsideBar NQ     | 20  | 574.5 → 524.5 | 1 → 27.5 | −$10,344 → +$68,492 |   0% → 100% |
| OpeningRange NQ  | 20  |   420 → 379.5 |   0 → 32 | −$8,366 → +$207,976 |   0% → 100% |

Medians, peak-first → trough-first. OpeningRange is the 30-minute opposite-stop `width` shortlist; §M28.13's rows were every fourth stored configuration.

**On NQ every configuration of both goes from a loss to a profit**, on Apex 150K as well; §M28.13 had InsideBar's going from 42% profitable to 77%. **On MNQ the order is no longer nearly free**: OpeningRange's median net rises sevenfold and its passes from 5 to 18, against §M28.13's +$14,045 to +$23,323. The 2026 evaluation's trail is $500 tighter and the shortlist is not §M28.13's subsample, so whether the fills, the account or the configurations moved it is not separated. **TopStep's Combines do not move at all**, 160 of 160 replays unchanged, as an end-of-day trail must not.

### What there is nothing to re-read in

The four labels' calibrations, §M10.1 to §M10.4, and the regime threshold of §M27.5 are properties of the bars; the specifications, §M19.2, §M28, §M28.6 and §M34, and the tooling, §M7b, §M27.6, §M28.3 and §M28.4, hold no measurement the fills could move. Each stands as written.

## Thirty minutes

Every campaign grid was swept at 30 minutes, and no campaign above reads it, because each one's protocol fixed its own bar sizes. What it adds, read here as a description and tested nowhere:

- **More of the registry clears gate 1 at 30 minutes than at any other bar size.** Over the whole series, 81% and 88% of EmaCrossover's configurations are profitable there, 83% and 84% of InsideBar's, 71% and 65% of InsideBarTrailing's and 72% of PullBackAndGo's on NQ (§M27's table above), where no other bar size has more than two archetypes over half. On the selection window seven of the nine archetypes have a campaign variant majority-profitable at 30 minutes on at least one root; only DeadCatBounce and ElasticBand do not.
- **The inside-bar pair's bar-size curve is not single-peaked once 30 minutes is in it.** Both collapse at 10 and 15 minutes after peaking at 5 and recover at 30, so §M27's "peak at 5 and fall away by 15" is true of the range it measured and not beyond it.
- **A 30-minute configuration enters a shortlist easily.** The result files of §M53, §M58 and §M26.7 carry 2–30 runs beside their pre-registered families for that reason, and here every family named by a rule named different strata over 2–30 minutes than over 2–15.

A campaign that wants 30 minutes should name it before it runs, which those three could not.

## What this does not settle

- **One minute is still running.** §M28.8, §M28.10, §M28.11 and §M28.9's table by year read 1-minute bars and are not re-read. Every other campaign that ran 1 minute is read here at 2 to 15, which is all the split windows hold until the last part of the re-sweep finishes.
- **Two reads cannot be re-run, because the null tool cannot shortlist the way they did**: §M26.4's, by band source, and the loose ends' null over the confluence count, by count.
- **Reads that need trade logs or contracts were not re-run**: the per-contract tallies of §M27 and §M27.3, the clock and volume screens over the survivor's own trades in §M27.7 and §M27.8, §M28.1's long-and-short null, §M28.15's fold-by-fold profit factors, and §M28.9's diversification.
- **Three passes were not re-swept**: §M19.1's crossing of the two compression forms, §M31.1's hold ladder inside the fitted `DIRECTIONAL` cell, and the higher-timeframe file's one-off DeadCatBounce run.
- **A difference against a campaign before §M44 has two causes**, the repaired archive and the fills, and this file separates them only where §M44 had already re-read the campaign or where the part-one table speaks for the whole archetype.
- **The two results the fills created are gate-2 results, not candidates.** OpeningRange's tight-stop fade (§M28.5) and EmaPullback's one-bar confirmation (§M39) both turn on what a stop entry's own bar does after its fill, which NinjaTrader's backtest walks one way and a live market need not. The minute bars could check both before either is pre-registered, as §M28.4 checked the retest.
- **Every family named by a rule was named on the re-swept rows**, so a stratum that cleared in the original and is absent here was not tested here: §M19.3's `trend=UP` is the instance that mattered.
- **The gold strata were re-picked, at 112 pairs against 68**, by the pre-registration's own rule; the pairs are not the same pairs.
- **The prop replays use the 2026 presets** wherever the stored gate reads made them, and the original campaigns used presets since replaced. §M46's ladder and §M28.13's excursion check replay the 2026 evaluations alone, so neither separates the fills from the account terms, and §M28.13's population run is not rebuilt.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#440]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/440
[#441]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/441
[#451]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/451
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
[#454]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/454
[#455]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/455
[#471]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/471
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/472
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
