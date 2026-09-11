---
id: M27.3
title: "M27.3 — InsideBar's bracket, crossed at last"
archetypes: [InsideBar]
issues: [198]
gates: [2, 3, 4]
outcome: negative
verdict: >-
  The target is the largest axis on the holdout and almost inert on the selection window; the re-sweep is a held-out failure, and the negative rank correlation is a finding with no explanation yet.
---

# M27.3 — InsideBar's bracket, crossed at last ([#198])

§M27 stopped InsideBar at Gate 4 and named the reason: the target was hardcoded at 1× ATR, so the campaign moved the stop across three values and could not move the reward half of the same geometry by a tick. [#197] added `tp_multiplier`; this is the re-sweep that crosses the two.

**The missing parameter was real, and it is not selectable.** On the held-out window the target multiplier is the largest axis in the grid by an order of magnitude, and the geometry it reaches does clear Gate 4. On the selection window the same axis is nearly inert and points the *other way*, so a protocol that chooses before it measures picks the 1× the campaign was already stuck with. Gate 4 is still failed, and it is now failed for a different reason than §M27 recorded.

## What the re-sweep ran

2,688 combinations in 42 seconds, appended to `results/campaign/InsideBar.duckdb` under the variant name `narrow`:

- **The bracket pair crossed**, which is what §M27 could not do: `tp_multiplier` over 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0 and 8.0 against `atr_multiplier` over 2.0, 3.0, 5.0, 7.5, 10.0, 15.0 and 20.0. The range opens at the campaign's own cell — a 1× target and §M27's three stop distances are all inside it — and extends below and above.
- **The entry held at what §M27 chose**, per resolution, so the crossed pair is the only thing varying: `ema_kind=hma` and `error_margin=0.1` at both bar sizes, with `ema_period=22`/`atr_length=14` at five minutes and `ema_period=11`/`atr_length=3` at ten. Those are the modal values of §M27's own DIRECTIONAL top twenty pooled over both roots; where that twenty is tied — `fast_sma_period` at both resolutions, `slow_sma_period` at ten minutes — the NinjaScript default stands, which is the campaign's own finding that the moving-average axes barely matter. Chosen on profit factor because §M27 ranked that way, and **held rather than re-tuned**.
- **Five and ten minutes only**, for the two reasons the issue and §M27.5 each give: every archetype in the campaign is unprofitable at one and two minutes on both roots and InsideBar falls away by fifteen, and the per-contract null is out of reach at fifteen at this cell size.
- **`unfiltered` and `regime=DIRECTIONAL`**, the latter through `--regime-quantiles`, so the stratum is the fitted quintile of §M27.5 rather than the uncalibrated 0.5 cut and splits into one cell per lookback. Six cells, both roots, both split windows. **n=20 was named as the cell the verdict is read on before the run**, because it is the lookback §M27.5's per-contract sample table used.

Nothing in §M27's own grid moved: the re-sweep is its own entry in `VARIANT_SETS`, so the campaign's stored rows and the code that produced them still agree.

## The target is the largest axis on the holdout, and almost inert on the selection window

Share of variance one axis explains, over the whole narrow grid (η², both roots pooled):

| axis             | net-to-drawdown, holdout | net-to-drawdown, selection | profit factor, holdout | profit factor, selection |
| ---------------- | ------------------------ | -------------------------- | ---------------------- | ------------------------ |
| `tp_multiplier`  | **0.284**                | 0.063                      | **0.270**              | 0.055                    |
| `atr_multiplier` | 0.011                    | 0.021                      | 0.006                  | 0.034                    |
| resolution       | 0.015                    | 0.001                      | 0.006                  | 0.048                    |
| stratum          | 0.055                    | 0.204                      | 0.109                  | 0.256                    |

**This is the first axis in the project to beat the bar size on InsideBar.** §M27 measured resolution at η² 0.76 for this archetype across 1–15 minutes and every moving-average axis below 0.04; inside a grid that holds the resolution to two values, the target explains a quarter of the holdout's variance and the stop explains one part in ninety of it. The asymmetry §M27 described was being produced almost entirely by the half of it that could not be swept.

Median net-to-drawdown per target distance, pooled over the stop, the resolution and the six strata:

| `tp_multiplier` | holdout MNQ | holdout NQ | selection MNQ | selection NQ |
| --------------- | ----------- | ---------- | ------------- | ------------ |
| 1.0             | 0.589       | 0.414      | 0.849         | 0.734        |
| 1.5             | **1.458**   | 0.771      | 0.605         | 0.385        |
| 2.0             | **1.434**   | **1.123**  | 0.435         | 0.275        |
| 3.0             | 0.661       | 0.707      | 1.056         | 0.864        |
| 4.0             | 0.011       | 0.193      | 0.832         | 0.925        |
| 5.0             | −0.110      | 0.080      | 1.050         | **1.363**    |
| 6.0             | −0.010      | 0.161      | **1.351**     | 1.321        |
| 8.0             | −0.056      | −0.039     | 1.244         | 0.877        |

**The two windows are close to inverted.** The holdout's ridge is 1.5–2.0 on both roots and collapses to zero or below from 4.0; the selection window's ridge is 5.0–6.0 and 1.5–2.0 is its *worst* region. It is an interior optimum in both cases rather than a monotone preference for a wider target, and the optima sit at opposite ends of the axis.

Measured as a rank correlation of `tp_multiplier` against net-to-drawdown, per root × stratum cell: **+0.194 on the selection window and −0.455 on the holdout, with the sign flipping in 8 of the 12 cells.** The axis does not merely weaken out of sample; it reverses.

## Gate 4, re-measured, and still failed

`tools/campaign_holdout.py --variant narrow`, best twenty on the selection window measured on the holdout, per root and stratum:

- **Ranked on net-to-drawdown, 1 of 12 cells finishes with more profit than its own worst peak-to-trough** — NQ at `regime=DIRECTIONAL@n=30`, at 1.132. The pre-registered n=20 cell lands at 0.032 on MNQ and 0.335 on NQ.
- **Ranked on profit factor instead: the same 1 of 12**, the same cell, at 1.110. Across the twelve cells the net-to-drawdown ranking beats the profit-factor ranking on holdout net-to-drawdown in seven, loses in three and ties in two. **Choosing on the drawdown-aware statistic is a wash**, which is worth recording because the standing instruction was written expecting it to matter.
- **The shortlist barely beats not shortlisting**, and the mean rank correlation between the windows is **−0.161 on net-to-drawdown and −0.098 on profit factor**. Set against §M27.4's table, where every dimension ran between +0.22 and +0.46, and §M28.1's OpeningRange at +0.69: **this grid's ranking is anti-correlated across the split.** It is the only negative figure of its kind in the project.

**So the geometry that clears Gate 4 exists inside the grid and the selection window will not hand it to you.** Ranked on net-to-drawdown over the selection window, the configuration chosen on both roots is `tp_multiplier=1.0` with `atr_multiplier=10.0` — the campaign's own bracket, at a 91% selection-window win rate. Adding the parameter changed what is reachable and did not change what gets picked.

## Gate 3 over the grid, and the two rankings disagree identically on both roots

Every one of the 56 bracket cells in `regime=DIRECTIONAL@n=20` at five minutes, placed against its own matched null on the holdout, 200 iterations. Median profit-factor excess over the null, per target distance:

| `tp_multiplier` | MNQ excess | MNQ p | NQ excess  | NQ p | win rate |
| --------------- | ---------- | ----- | ---------- | ---- | -------- |
| 1.0             | +0.106     | 0.51  | +0.110     | 0.54 | 0.86     |
| 1.5             | **+0.192** | 0.13  | **+0.125** | 0.28 | 0.82     |
| 2.0             | +0.142     | 0.36  | +0.100     | 0.47 | 0.77     |
| 3.0             | +0.039     | 0.76  | +0.043     | 0.68 | 0.70     |
| 4.0             | −0.015     | 0.87  | −0.039     | 0.82 | 0.65     |
| 5.0             | −0.067     | 0.52  | −0.031     | 0.80 | 0.60     |
| 6.0             | −0.031     | 0.86  | −0.030     | 0.81 | 0.57     |
| 8.0             | +0.006     | 0.89  | −0.010     | 0.92 | 0.53     |

**The excess peaks where net-to-drawdown peaks, on both roots**, which is the first time in this project that the drawdown reading and the matched null have agreed about a geometry. **Nothing is significant**: 3 of 56 cells on MNQ and 2 of 56 on NQ clear p < 0.05, against the 2.8 that 56 comparisons produce by chance. 34 of 56 and 29 of 56 beat their own null at all, against the 28 a coin flip gives.

**The rankings split two against one, identically on both roots.** Profit factor and net-to-drawdown both pick `atr_multiplier=2.0 tp_multiplier=1.5`; the excess over the matched null picks `atr_multiplier=20.0 tp_multiplier=2.0`. Two independent roots landing on the same pair of disagreeing answers is a stronger statement than either ranking is on its own — and it is the second place in this run where the drawdown statistic sides with profit factor rather than correcting it.

**That is the standing instruction meeting a case it did not anticipate.** § "The method that does answer the question" pairs profit factor against the excess and tells you to believe the excess; §M27's Gate 4 pairs profit factor against the drawdown and tells you to believe the drawdown. Here those two corrections point at *different* cells, so "never rank on profit factor" does not settle which one to take. Nothing above resolves it, because neither cell is significant.

The win-rate column is the mechanism §M27 asked about. The 85–90% win rate against a 3–5.5× loss size that §M27 called fragile by construction is what `tp_multiplier=1.0` produces; the 1.5–2.0 band trades it for 0.77–0.82, and by 8.0 the archetype is a coin flip that no longer makes money.

## Per contract

`tools/campaign_contracts.py --variant narrow`, the configuration the selection window's net-to-drawdown ranking chose, nineteen front-month contracts per root at five minutes:

| root | contracts | beats its null | profitable | median excess | fewest trades | total net |
| ---- | --------- | -------------- | ---------- | ------------- | ------------- | --------- |
| MNQ  | 19        | 14             | 13         | +37.32        | 24            | +$36,736  |
| NQ   | 19        | 15             | 15         | +441.62       | 24            | +$399,254 |

Split into the contracts the selection window covered and the ones it did not — eleven and eight per root — that is **19 of 22 in sample and 10 of 16 out of sample.** §M27's figures were 16 of 22 and 9 of 16 on the profit-factor estimator the tool no longer uses, so this is the same picture rather than a better one: the configuration is the same configuration.

**§M27.5's promise about the sample holds.** Median trades per contract are 67 and 64 against the raw cut's 30, and one contract of nineteen on each root falls under thirty, exactly as its table predicted.

## What this settles, and what it does not

- **Gate 4's diagnosis in §M27 was right and its prognosis was wrong.** The lopsided bracket really was the thing stopping InsideBar, and the target multiplier really does move it — median holdout net-to-drawdown goes from 0.59 to 1.46 on MNQ by changing one number the campaign could not reach. What §M27 assumed, without saying it was assuming it, is that a parameter which fixes a result out of sample can be found in sample. It cannot be found here.
- **The re-sweep is a held-out failure, not a held-out success with a caveat.** Eleven of twelve cells finish the holdout with less profit than their own worst drawdown, and the shortlist's rank correlation with the holdout is negative. Quoting the 1.5–2.0 ridge as a result would be reading the holdout as though it were a selection window, which is the specific error § "Selecting on one contract is worse than not selecting" exists to prevent.
- **A negative rank correlation is a finding in its own right and has no explanation yet.** Every other dimension the project has split has decayed toward zero; this one crosses it. Whether that is the single time cut at 60% of the bars catching one volatility regime, or something about the bracket geometry specifically, is not answered here — and the single time cut is already on §M27's own list of what the campaign could not test.
- **The stratum is the fitted cell, so the comparison to §M27 is loose.** §M27.5 is explicit that its result does not transfer into the wider quintile, and this re-run measured inside it rather than inheriting anything. Where a figure above is set beside a §M27 one, that is a comparison of two measurements on different cuts.
- **Twelve cells and 56 bracket combinations are a multiple-comparisons load**, and the one cell that clears Gate 4 is one of twelve. It is quoted as a count, not as a candidate.
- **The narrow grid holds the entry fixed, so nothing here re-tests the entry.** It re-tests the bracket around an entry §M27 chose on profit factor. An entry re-tuned inside the fitted stratum is a different run and has not been done.

[#197]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/197
[#198]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/198
