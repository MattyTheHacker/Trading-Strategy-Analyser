---
id: M35
title: "M35 — EmaPullback swept: the entry axes hold their order and the moving averages reverse it"
archetypes: [EmaPullback]
issues: [309]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Gate 1 passes in five of eight root x resolution cells and five strata clear gate 2 on both roots, but 2 of 60 matched-null tests reach p = 0.05 and both are one root of one cell; the moving-average kind is worth two points of held-out profitable share and what ordering it has inverts, while the archetype's own two entry axes are the only ones whose ordering survives the holdout.
---

# M35 — EmaPullback swept: the entry axes hold their order and the moving averages reverse it ([#309])

[§M34](m34-ema-pullback-spec.md) specified the archetype and built it. This is its first campaign: **847,872 combinations in 75 minutes**, both roots, through §M27's four gates. It passes the first two and stops at the third, and the axis table is the more useful half of the result — **the two axes this archetype invented hold their ordering out of sample and every moving-average axis reverses it.**

Every figure below is re-derivable from `results/campaign/EmaPullback.duckdb`. It is a measurement of one dated run against the archive as it stood, not a standing property.

## What was run

|                 |                                                                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Grid**        | 2,304 combinations: `fast_kind` × `fast_period` × `slow_kind` × `slow_period` × `min_bars_extended` × `touch_mode` × `require_turn` |
| **Kinds**       | `ema`, `sma`, `wma`, `hma` on the fast average; `ema`, `sma` on the slow one                                                        |
| **Periods**     | 5, 9, 13, 20 fast; 30, 50, 100, 200 slow                                                                                            |
| **Strata**      | 23, one context dimension at a time, never crossed                                                                                  |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                                                                             |
| **Roots**       | MNQ and NQ, spliced continuous, 2024-01-01 to 2026-08-10                                                                            |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                        |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                         |

**Both averages are swept over kind and period, which no earlier campaign here did** — EmaCrossover swept the fast kind alone. §M34 argued this was the archetype where §M27's "the moving averages are nearly inert" reading was least safe, because the two averages are the level price returns to *and* the level the stop sits on. That argument was wrong, and the table below is why.

**One minute was not run.** §M27's standing finding is that every archetype's median configuration loses money there, and a four-resolution pass costs less than half of a five-resolution one at the same grid. The bar-size lever is still measured, on four points rather than five.

**The trail was held off.** `trail_ma_stop` is a second exit hypothesis and doubling the grid to carry it would have bought a worse test of the first one.

## Gate 1 — passes, and the coarse resolutions are where it passes

Share of configurations with a profit factor above 1, at 30 trades or more, in the **unfiltered** stratum:

| root | resolution | selection | holdout |
| ---- | ---------- | --------- | ------- |
| MNQ  | 2m         | 26.1%     | 21.4%   |
| MNQ  | 5m         | 46.2%     | 31.1%   |
| MNQ  | 10m        | **67.1%** | 22.4%   |
| MNQ  | 15m        | **77.7%** | 18.2%   |
| NQ   | 2m         | 35.0%     | 36.8%   |
| NQ   | 5m         | **57.4%** | 42.9%   |
| NQ   | 10m        | **78.6%** | 29.5%   |
| NQ   | 15m        | **80.6%** | 25.5%   |

**Five of eight cells clear gate 1**, which is a majority of configurations profitable in at least one root × resolution cell. The bar-size lever is the registry's usual one and it points the usual way on the selection window.

**It points the other way on the holdout, and that is the campaign's first real finding.** The selection window's best cell — NQ at 15 minutes, 80.6% profitable — is its second-worst held out at 25.5%. Every cell loses profitable share across the split and the coarse ones lose the most: MNQ at 15 minutes goes from 77.7% to 18.2%.

## Gate 2 — five strata survive on both roots, and the unfiltered case is not one of them

The best twenty by selection-window profit factor, measured on the holdout, against the holdout median of everything:

| stratum              | MNQ holdout PF | NQ holdout PF | passes both |
| -------------------- | -------------- | ------------- | ----------- |
| `phase=CASH_OPEN`    | 2.015          | 1.404         | **yes**     |
| `phase=MIDDAY`       | 1.213          | 1.082         | **yes**     |
| `phase=LONDON`       | 1.207          | 1.239         | **yes**     |
| `compression=NORMAL` | 1.170          | 1.003         | **yes**     |
| `trend=MIXED`        | 1.061          | 1.070         | **yes**     |
| `volume=THIN`        | 1.109          | 1.060         | MNQ only    |
| `regime=DIRECTIONAL` | 0.917          | 1.230         | NQ only     |
| `unfiltered`         | 0.783          | 0.934         | no          |
| `trend=UP`           | 0.603          | 0.890         | no          |
| `htf=ABOVE`          | 0.658          | 0.679         | no          |

**`phase=CASH_OPEN` on MNQ is the only cell in the campaign that clears its own drawdown** — the one thing gate 4 asks that gate 2 already answers.

Two cells are worth naming for what they are *not*. **`trend=UP` and `htf=ABOVE` are the two strata that agree with the archetype's own thesis** — a pullback continuation ought to work best in an uptrend and above a higher-timeframe average — and both are among the worst cells held out, on both roots, having been among the better ones on the selection window. The strata that survive are the ones that say nothing about direction.

## Gate 3 — 2 of 60, and both are one root of one cell

**The family, stated before it was run:** the five strata that cleared gate 2 on both roots, plus `volume=THIN`, which is a pre-registered hypothesis rather than a chosen cell — the pullback-continuation literature asks for the pullback to arrive on declining volume, and that was written down before the campaign. Six cells × two roots × the best five configurations each = **60 tests**, ranked on the selection window and measured on the holdout, against a matched random entry taking the same number of trades with the same time-of-session profile.

| root | stratum              | measured | beat the null | p < 0.05 |
| ---- | -------------------- | -------- | ------------- | -------- |
| MNQ  | `phase=CASH_OPEN`    | 5        | 3             | 0        |
| MNQ  | `phase=LONDON`       | 5        | 2             | 0        |
| MNQ  | `phase=MIDDAY`       | 5        | **5**         | 0        |
| MNQ  | `compression=NORMAL` | 5        | 1             | 0        |
| MNQ  | `trend=MIXED`        | 4        | 2             | 0        |
| MNQ  | `volume=THIN`        | 5        | 4             | 0        |
| NQ   | `phase=CASH_OPEN`    | 5        | 4             | **2**    |
| NQ   | `phase=LONDON`       | 5        | 3             | 0        |
| NQ   | `phase=MIDDAY`       | 5        | 3             | 0        |
| NQ   | `compression=NORMAL` | 5        | **5**         | 0        |
| NQ   | `trend=MIXED`        | 5        | 4             | 0        |
| NQ   | `volume=THIN`        | 5        | 3             | 0        |

**Gate 3 fails.** Two tests of sixty reach p = 0.05 and both are NQ's `phase=CASH_OPEN`, whose MNQ twin clears none. Sixty tests at the 5% level are expected to produce three by chance, so two is not evidence of anything. Nothing clears on both roots, which is the bar §M28.16 set.

**The binding constraint is the sample, not the sign.** The shortlisted cells hold 3 to 52 trades on the holdout; MNQ's `phase=MIDDAY` has all five configurations beating their null by +1.35 to +1.96 of profit factor with a net-to-drawdown of 1.6 to 3.2, and not one of them reaches p = 0.05, because a 14-trade null spans most of the range the observation sits in. That is §M28.1's verdict again: a stratum tight enough to have an edge is tight enough to have no power.

## The axes, which is what a campaign is for

Read on a **balanced panel** — a level counts only in cells where every level of that axis cleared 30 trades in the same root, resolution, stratum and window — because the marginal is confounded by the trade count and says the opposite in one case. Share of configurations profitable:

| axis                | selection order                              | holdout order                                | Spearman ρ |
| ------------------- | -------------------------------------------- | -------------------------------------------- | ---------- |
| `touch_mode`        | wick 58.4 > any 56.0 > close 49.2            | wick 42.5 > any 38.2 > close 36.9            | **+1.000** |
| `min_bars_extended` | 5 → 57.4, 3 → 56.9, 1 → 52.7                 | 5 → 43.6, 3 → 40.9, 1 → 39.1                 | **+1.000** |
| `fast_kind`         | hma 57.8 > wma 56.0 > sma 54.5 > ema 46.9    | ema 41.4 > wma 39.9 > hma 39.2 > sma 39.1    | −0.400     |
| `fast_period`       | 5 → 63.0, 13 → 54.5, 9 → 53.6, 20 → 49.4     | 20 → 44.2, 5 → 40.8, 9 → 39.1, 13 → 36.3     | −0.400     |
| `slow_period`       | 200 → 67.9, 100 → 59.4, 50 → 52.2, 30 → 46.6 | 50 → 46.3, 30 → 44.6, 100 → 39.6, 200 → 33.0 | **−0.800** |
| `slow_kind`         | ema 57.0 > sma 55.2                          | sma 42.2 > ema 39.7                          | inverts    |

**The two axes the archetype invented are the two that hold.** `touch_mode` and `min_bars_extended` reproduce their ordering exactly across the split, and both point the same way: the shallow touch — a wick to the fast average that closes back beyond it — beats closing through it by 5.6 points of held-out profitable share, and a longer extension before the touch beats a shorter one monotonically. Neither is a large effect. Both are real orderings rather than noise, which is more than any other axis here manages.

**Every moving-average axis reverses.** Ranked as eight fast/slow kind pairs, the selection window's order against the holdout's has a Spearman ρ of **−0.595**: choosing a kind on the selection window is worse than not choosing. The held-out spread across all four fast kinds is 2.3 points of profitable share and across the two slow kinds 2.5 — so **ema against sma is worth about two points and the sign of it is not stable.** §M27's registry-wide reading survives its hardest case.

**`slow_period` is the largest inversion in the campaign and the one with a mechanism.** It is the stop distance, and lengthening it does this on the selection window:

| `slow_period` | trades | mean R | win rate | bars held | exits at the session close |
| ------------- | ------ | ------ | -------- | --------- | -------------------------- |
| 30            | 1,373  | −0.017 | 40.4%    | 32.2      | 12.0%                      |
| 50            | 1,271  | −0.005 | 41.6%    | 40.9      | 16.1%                      |
| 100           | 1,108  | +0.015 | 43.3%    | 55.8      | 23.4%                      |
| 200           | 993    | +0.035 | 45.2%    | 72.3      | 31.3%                      |

A wider stop wins more often and holds far longer, and **by `slow_period = 200` almost a third of the exits are the forced flat rather than the strategy**. On the selection window that is the best rung; on the holdout it is the worst. A configuration whose exits are mostly the clock is not the strategy its rules describe, and this axis buys that trade directly.

**The pooled selection-to-holdout rank correlation is negative.** Over 14,631 unfiltered configurations paired across the split it is **−0.160**, and it is negative in seven of the eight root × resolution cells — most negative at exactly the resolutions gate 1 liked best (MNQ 15m −0.204, NQ 10m −0.203, NQ 15m −0.289). Selecting on this window actively harmed the holdout. §M27.3 found the same shape on InsideBar's bracket and had no explanation; `slow_period` is a mechanism for this one, and it is the first time the negative correlation here has had a named cause.

## The three things the pullback literature asks for, measured

`Trading-Docs` §7.4 states the setup as five steps and names the failure modes. Three of them are expressible against what this codebase already has, and all three were tested:

**"Wait for the turn" — the step the material says is most often skipped — is a coin flip.** `require_turn` asks the signal bar's own body to have turned back into the trend. On the balanced panel it is worth +3.3 points of held-out profitable share (43.5% against 40.2%). **Paired exactly** — every other axis held identical, both arms at 30 trades or more — it wins 52.0% of 56,738 pairs on MNQ and **49.2%** of 57,271 on NQ, with a median profit-factor delta of +0.005 and −0.002. It roughly halves the trade count, and that is what the unbalanced marginal was reading: it says +11.7 points, and it is wrong. **A requirement that changes the trade count cannot be read off a marginal.**

**"The pullback on declining volume" is the largest context dimension, and it is measured at a cut that does not transfer.** Pooled over both windows, `volume=THIN` is 67.6% profitable at a median profit factor of 1.086 and `volume=HEAVY` is 26.6% at 0.919; within a resolution, volume's η² is 0.216 at 15 minutes and 0.198 at 10, the largest of any context dimension here. It clears gate 2 on MNQ and misses on NQ, and reaches p = 0.05 in neither. **These are the campaign's raw 0.7/1.5 thresholds**, and §M30 established that a gate result holds for the cut it was run at and does not transfer to the label — so this is a reason to run the calibrated re-cut, not a finding about thin volume.

**"Higher timeframe trend" is a cost.** `htf=ABOVE` looked like the archetype's own thesis and is among the worst cells held out on both roots (0.658 and 0.679). Agreeing with a 60-minute average did not help.

## What this does not settle

- **The calibrated cuts were not run.** The volume and regime strata here use the campaign's raw threshold pairs. §M27.5 and §M27.8 are why that matters and §M30 is why a raw-cut result must not be quoted as a claim about the label. The volume re-cut is the obvious next pass, because volume is the dimension with the largest η² and the pre-registered hypothesis behind it.
- **One minute was not swept**, so the resolution reading rests on four points.
- **The trail was not swept**, so the archetype's second exit scheme is untested.
- **The confirmation entry §M34 deferred is still deferred** — a resting stop above the touch bar's high, which is the literature's step 3 in its strong form where `require_turn` is its weak one. Given that the weak form is a coin flip, the strong one is the more interesting test rather than the less.
- **Nothing here is a Tier-2 measurement.** `Tier2Status` is `TIER1_ONLY` and no NinjaScript exists.
