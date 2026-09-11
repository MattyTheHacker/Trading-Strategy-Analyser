---
id: M27.5
title: "M27.5 — the regime threshold, calibrated rather than swept blind"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, PullBackAndGo]
issues: [200]
gates: []
outcome: calibration
verdict: >-
  The regime threshold is fitted rather than guessed, which restores the per-contract sample in most places but not everywhere; cross-resolution rows are not twins.
---

# M27.5 — the regime threshold, calibrated rather than swept blind ([#200])

**`regime_directional_above = 0.5` is not one filter, and §M27 compared cells that had been cut by it as though it were.** Measured over the selection window of both continuous series, the share of measured bars it labels `DIRECTIONAL` on MNQ:

| lookback | 1 m   | 5 m   | 15 m  |
| -------- | ----- | ----- | ----- |
| 5        | 0.395 | 0.411 | 0.422 |
| 10       | 0.202 | 0.219 | 0.236 |
| 20       | 0.066 | 0.078 | 0.099 |
| 30       | 0.025 | 0.034 | 0.052 |
| 50       | 0.005 | 0.009 | 0.019 |

From half a percent of the bars to forty-two percent of them, across a grid whose cells were read against each other. §M10.1 records both halves of why: `1/√n` is a driftless random walk's expected efficiency ratio, so a raw cut is a different percentile of noise at every lookback, and the real series' efficiency drifts with resolution where a shuffle of its own returns does not.

**The fix is a change of units and not a looser cut.** `nqbt/regime.py` states a threshold two ways that survive both axes:

- `thresholds_from_quantiles` fits the pair to the ratio's own distribution at that `(resolution, lookback)`. **The cell size becomes the parameter** — a directional quantile of 0.8 labels a fifth of the measured bars `DIRECTIONAL` at every point of the grid, by construction, so trades per contract is a design input rather than an artefact.
- `thresholds_from_multiples` expresses the pair as a multiple of `random_walk_ratio(n)`, which is `1/√n`. `ER × √n` is scale-free under the null, so the same multiple is the same amount of directionality at every lookback.

**The campaign's cell size is a decision, and it is a fifth at each end.** `tools/campaign_sweep.py --regime-quantiles` fits `(0.20, 0.80)` and splits the regime stratum into one cell per lookback — `regime=DIRECTIONAL@n=20`, and `regime_lookback` is swept again because it sets the horizon the label describes. A cell rather than an axis because the thresholds move *with* the lookback and a sweep crosses its axes; pairing them any other way rebuilds the confound inside one grid. **The fit is taken on the selection window at every window**, `--split` or not, so a held-out run reads a cut it did not see, and the run logs the pair and its multiple before the first sweep.

## What the fit lands on, and how close the two units are

MNQ selection window, directional quantile 0.80, with the multiple of `1/√n` beside each threshold:

| lookback | 1 m          | 5 m          | 15 m         | `1/√n` |
| -------- | ------------ | ------------ | ------------ | ------ |
| 5        | 0.731 (1.63) | 0.737 (1.65) | 0.753 (1.68) | 0.447  |
| 10       | 0.505 (1.60) | 0.521 (1.65) | 0.536 (1.69) | 0.316  |
| 20       | 0.358 (1.60) | 0.372 (1.66) | 0.394 (1.76) | 0.224  |
| 30       | 0.294 (1.61) | 0.308 (1.69) | 0.337 (1.85) | 0.183  |
| 50       | 0.230 (1.63) | 0.248 (1.75) | 0.282 (1.99) | 0.141  |

**NQ agrees with MNQ to within 0.003 at every cell of that grid**, which is what a calibration of the index rather than of the root should look like — the two roots track the same underlying and the ratio is invariant to level and scale.

**The two units agree at one minute and part at fifteen, which is itself a measurement.** A driftless Gaussian walk's own quintile cuts sit at 0.32–0.35 and 1.61–1.67 of its anchor, near-flat across the lookback exactly as `ER × √n` being scale-free predicts — 400,000 trials per lookback. One-minute MNQ lands on top of that, at 0.33–0.35 and 1.60–1.63, so **at the finest bar the directional quintile is a random walk's**. Both cuts then rise with the bar size and the lookback together, reaching 0.38 and 1.99 at 15 minutes over 50 bars. **Prefer the quantile form**: it tracks the distribution actually being cut, where a multiple pins the cell against a null the series only matches in one corner of the grid.

**The old `CONSOLIDATING` cut moved much further than the directional one.** The 0.20 quantile is 0.33–0.38 of the anchor across the whole grid, which is where a random walk's bottom fifth also sits; the raw 0.3 is **1.34×** the anchor at a lookback of 20, well above the walk's *mean*. So `CONSOLIDATING` as configured was most of the series — 71.3% of 1-minute bars, §M10.1 — and the new cell is a fifth of it by definition. That is the larger of the two changes and the one least likely to be noticed, because no result was ever quoted from the low cell.

## The per-contract sample it restores, and where it does not

InsideBar, `DIRECTIONAL` only, under the configuration §M27's selection window chose for that stratum, with nothing changed but the threshold pair and the lookback held at 20. Trades per front-month contract, nineteen contracts per root:

| root | resolution | cut    | threshold | median | fewest | most | under 30 trades |
| ---- | ---------- | ------ | --------- | ------ | ------ | ---- | --------------- |
| MNQ  | 5 m        | raw    | 0.500     | 30     | 9      | 59   | 9               |
| MNQ  | 5 m        | fitted | 0.372     | 67     | 24     | 136  | 1               |
| MNQ  | 15 m       | raw    | 0.500     | 14     | 8      | 28   | 19              |
| MNQ  | 15 m       | fitted | 0.394     | 24     | 14     | 51   | 13              |
| NQ   | 5 m        | raw    | 0.500     | 30     | 9      | 44   | 8               |
| NQ   | 5 m        | fitted | 0.373     | 63     | 24     | 89   | 1               |
| NQ   | 15 m       | raw    | 0.500     | 15     | 11     | 23   | 19              |
| NQ   | 15 m       | fitted | 0.396     | 26     | 16     | 40   | 13              |

**At 5 minutes the per-contract null the campaign could not run is now runnable**: the sample roughly doubles and one contract of nineteen on each root falls under thirty trades, against nine and eight before. **At 15 minutes it is still not**: thirteen of nineteen stay under thirty on both roots, so the per-contract step stays out of reach there at this cell size. [#198]'s "5 and 10 minutes only" therefore holds for a second reason to the one it was written for.

## What this does not settle

- **The fitted cell is not the cell that motivated the work, and §M27's result does not transfer into it.** `DIRECTIONAL` at 0.5 is 7.8% of 5-minute bars and the fitted cell is 20% of them. Whatever separates inside the wider cell has to be established inside it — [#198] re-runs the measurement, it does not inherit it.
- **A lower threshold is still a lower threshold**, and what makes this not the circular rule [#200] rejected is the order and the input rather than the direction of travel: the cell size was stated before the sweep, chosen for sample rather than for separation, and fitted where the holdout could not reach it. **It does not buy a cut clear of noise, and nothing here claims one** — the fitted quintile sits within a few percent of a random walk's own quintile at every fine-bar cell, and the raw 0.5 was not clear of noise either, at 1.12× the anchor over five bars against 2.24× over twenty. What the change of units buys is one cell size across the grid, and nothing else.
- **Nothing in §M10.1's stratification table survives the change of units**, because all three cells are redefined. It is not a like-for-like comparison and neither is any other stored regime row; the calibrated cells are stored under their own names for that reason.
- **The sweep is [#198]'s.** What is here is the reparameterisation, the calibration and the cell size; no ranking has been run on it.

[#198]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/198
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
