---
id: M10.1
title: "M10.1 — market regime: done"
archetypes: []
issues: [40]
gates: []
outcome: calibration
verdict: >-
  The regime label — DIRECTIONAL, UNCLASSIFIABLE and the rest — and the thresholds that separate them.
---

# ~~M10.1~~ — market regime: done ([#40])

`nqbt/regime.py`. Kaufman's efficiency ratio — `|close[t] − close[t−n]| / Σ|diff(close)|` over the lookback — cut by two thresholds into `CONSOLIDATING`, `UNCLASSIFIABLE` and `DIRECTIONAL`. Bounded 0–1, three lines of arithmetic, no TA-Lib dependency and therefore none of the NT8-parity work the moving averages needed. The lookback and both thresholds are sweepable and `regime_filter` is a bitmask integer, for exactly the reason `phase_filter` is one.

**The band between the thresholds is a label, not a gap.** Strictly below the lower is consolidating, strictly above the upper is directional, and everything in between — **including both boundaries** — is unclassifiable. That makes the third category free rather than a special case, and it makes the equality question one decision instead of two: no bar can satisfy two regimes, and `validate_thresholds` refuses a pair that cross rather than silently ordering them.

**The warm-up is `UNDEFINED`, which is not a fourth regime and not consolidating.** The house convention for an NT8 indicator is an expanding warm-up, and it is wrong here: over two bars the numerator and the denominator are the same quantity, so an expanding ratio reads exactly 1.0 and would label the start of every dataset `DIRECTIONAL`. Not measured and measured inconclusive are different states, and folding the first into the second would put unmeasured bars into a stratification cell while leaving the counts adding up — the failure that looks like a result. `UNDEFINED` is −1 for the same reason `OUT_OF_SESSION` is, and an undefined bar passes **no** mask, `ALL_REGIMES` included, so each archetype's signal skips the conjunction entirely at the default rather than ANDing a gate that would drop 20 bars from a reconciled run.

**The window sum is recomputed per bar rather than maintained incrementally.** A rolling add/subtract over a million bars drifts, and this is a denominator that legitimately reaches zero: a flat window would turn a −1e−13 of accumulated error into a large negative ratio. The exact version costs 15 ms per lookback over 914,700 bars, paid once in `prepare`, which is not worth trading for that. A window that genuinely never moved scores 0.0 — the extreme of consolidation — rather than dividing by zero.

**The grid holds ratios, not labels.** Both thresholds are swept as well as the lookback, so a grid keyed by all three would multiply out; `EfficiencyRatioGrid` is `[n_lookbacks, n_bars]` float64 and the thresholds are applied at gate time. That is the opposite of `MovingAverageGrid`'s default and the reason `_regime_lookbacks` returns nothing unless some combination actually narrows the filter — eight bytes per element is the most expensive thing a `ContextSpec` can ask for by accident. It is also the shape [#51]'s bandwidth squeeze wants, so the two share a scalar-plus-thresholds classifier instead of each inventing one.

**One function owns the rule.** `_regime_of` is the `@njit` device function both `label` and `gate` call, so the stratification key and the entry filter cannot drift apart. The filter still never builds a label array: `gate` tests `1 << regime` against the mask inside the same pass, which reads 0.23 ms over 914,700 bars against the ~30 ms a combination of the run below costs.

**`dead_axes` had to learn that a mask is off at its everything value.** `ALL_REGIMES` is 7, so the existing truthiness test read the filter as switched on and would have let `regime_lookback=[5, 20]` run every combination twice for identical rows. `archetypes.INERT_AT` states the off value where it is not `False`; nothing else changes.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the four added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added regime_filter regime_lookback regime_consolidating_below regime_directional_above` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, **$1.50 per contract** and 1 tick, lookback 20 and thresholds 0.3/0.5, one combination run once per regime:

| regime         | bar share | trades | profit factor | win rate | expectancy |
| -------------- | --------- | ------ | ------------- | -------- | ---------- |
| CONSOLIDATING  | 71.3%     | 2,396  | 0.611         | 0.312    | −12.04     |
| UNCLASSIFIABLE | 21.9%     | 975    | **0.721**     | 0.331    | −8.40      |
| DIRECTIONAL    | 6.8%      | 270    | 0.616         | 0.296    | −14.97     |
| all            |           | 3,639  | 0.640         | 0.316    | −11.28     |

**Do not read the UNCLASSIFIABLE row as an edge**, and do not diff this table against M10.4's: that one was run at the roadmap's older $1.24. It is the best of three cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and no cell reaches a profit factor of 1. And 270 trades in `DIRECTIONAL` is where a minimum-stratum guard starts to bind — against seven session phases it is 35 cells, and this is the coarsest of the two labels.

**The signals partition exactly and the trade counts do not, which is the point worth keeping.** All three single-regime filters admit 4,889 signals between them, exactly the unfiltered count, and their union is the unfiltered signal bar-for-bar. The trade lists sum to **3,641 against 3,639**. Nothing is double-counted: the simulation holds one position at a time, so removing an entry can free a later signal the unfiltered run was still in a position for. A regime label flips bar to bar where a session phase is a contiguous block, which is why M10.4's seven phases did sum exactly and these three do not. **Stratify the signal, or accept that the trade-level decomposition is approximate** — and never conclude a filter "found" trades from a count that went up.

**71% of 1-minute bars are `CONSOLIDATING` at 0.3/0.5.** The thresholds are resolution-dependent — a minute of noise has a low efficiency ratio almost by construction — so the defaults are conventional starting points to be swept, not a calibration, and they will want different values at 15 and 30 minutes. Read `ambiguous_share` before believing any of the rows: it runs 0.029 / 0.041 / 0.044 against 0.033 overall, highest in `DIRECTIONAL`, which is what a regime of larger bars should do.

**Worse: 0.5 is not a fixed amount of directionality, and the two axes are confounded** ([#200]). A driftless random walk has an expected efficiency ratio of `1/√n` — reproduced to three decimal places over 200,000 trials per lookback, and robust to fat tails — so a threshold held at 0.5 while the lookback is swept runs from the 59th percentile of pure noise to the 99.6th:

| lookback | mean ER under a random walk | `1/√n` | P(ER > 0.5) |
| -------- | --------------------------- | ------ | ----------- |
| 5        | 0.453                       | 0.447  | 0.412       |
| 10       | 0.318                       | 0.316  | 0.215       |
| 20       | 0.224                       | 0.224  | 0.071       |
| 30       | 0.183                       | 0.183  | 0.025       |
| 50       | 0.141                       | 0.141  | 0.004       |

**Sweeping `regime_directional_above` and `regime_lookback` as two independent axes therefore produces cells that cannot be compared with each other.** `ER × √n` is scale-free under the null — mean 1.000 at every lookback tested — so a threshold expressed as a multiple of `1/√n`, or as a quantile of the ratio's own distribution at that resolution and lookback, is one number across the axis where a raw 0.5 is not. Note also that `consolidating_below = 0.3` sits *above* the random-walk mean at a lookback of 20, so `CONSOLIDATING` as configured means "at or below what noise does" rather than chop.

**And the real series is less efficient than a shuffle of its own returns**, at every resolution and lookback tested — the same 914,700 MNQ bars, lookback 20, against a null that permutes the bar-to-bar returns and preserves nothing else:

| resolution | share ER > 0.5, real | same, shuffled |
| ---------- | -------------------- | -------------- |
| 1 m        | 0.067                | 0.160          |
| 5 m        | 0.079                | 0.158          |
| 10 m       | 0.091                | 0.159          |
| 15 m       | 0.097                | 0.158          |
| 30 m       | 0.116                | 0.154          |

Short-horizon mean reversion is the ordinary explanation and nothing here isolates it. What the table settles is narrower and enough: the real share moves with resolution where the null's does not, so a fixed threshold is a different filter at each bar size as well as at each lookback, and `DIRECTIONAL` is a top-of-distribution cut rather than an unusual amount of trend. **There is no standard value to substitute** — Kaufman introduced the ratio as KAMA's smoothing input rather than as a classifier, and the 0.3 that circulates is disclaimed by the vendors publishing it on exactly this ground. Calibrate it or state it as a quantile; do not sweep it blind. §M27.5 does both, and is what `regime.thresholds_from_quantiles` and `regime.thresholds_from_multiples` exist for.

**Cost.** Requested the way VWAP is, and adds one float64 series per lookback — 7.32 MB over 914,700 bars, about a sixth of the 47 MB dataset the run above was handed. `prepare` pays 15 ms per lookback and the per-combination gate 0.23 ms, so neither is measurable against the simulation.

**Smaller choices, recorded here rather than in the module ([#105]):**

- **Efficiency ratio rather than ADX**, which is laggier, less interpretable, and would need the same NT8-parity check the moving averages needed. ADX only if this proves inadequate.
- **A lookback of 1 is refused**, because numerator and denominator are then the same quantity and every bar reads 1.0 — a whole axis of `DIRECTIONAL` that looks like a measurement.
- **Three regimes, and deliberately no more.** Time of day already multiplies every other stratification; three against seven phases is 21 cells before an MA gate, and [#48]'s guard has to survive it on a few hundred real trades.
- **The ratio is invariant to direction, level and scale**, which is what makes one pair of thresholds meaningful across both roots and across years of back-adjusted history. A test pins all three.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
[#51]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/51
