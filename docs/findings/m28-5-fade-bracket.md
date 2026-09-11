---
id: M28.5
title: "M28.5 — the fade's bracket, tightened: monotone the other way, and zero of 15,360"
archetypes: [OpeningRange]
issues: [256]
gates: [1, 2]
outcome: negative
verdict: >-
  The stop axis is monotone across the whole of 0.02 to 1.0 of the range width because the stop sits inside the bar the order fills on; the held-out test reproduces gate 1 exactly.
---

# M28.5 — the fade's bracket, tightened: monotone the other way, and zero of 15,360 ([#256])

§M28.2 parked the fade with a reason rather than a verdict on the idea: "its stop is the axis that never suited it, since the range extreme it enters at is the one thing it cannot stop behind". § "Parked is not abandoned" asks what has changed before a re-run, and two things had — both properties of the swept space rather than new code.

**The fade's stop was never tight, and the fraction axis is why.** `ORB_STOP_FRACTION` measures a fraction of the range width back from the extreme the order rests at. For a breakout that runs *inward*, so `1.0` reproduces the opposite-extreme stop and `0.25` is a quarter-range stop. For a fade the same formula runs *outward*, because the extreme it enters at is the one it must stop behind. §M28.2's `[0.25, 0.5, 0.75, 1.0]` therefore placed a fade's stop between a quarter of the range width outside the extreme and a full width outside it: on a 30-point range, from 8.25 points away to 31.5. "Fails gate 1 at every fraction" was a measurement of stops between moderately wide and absurdly wide.

**And the width ladder had never carried a midpoint target.** `(1.0, nan)` is the opposite extreme and a runner. The half-range target — the middle of the range, which is what a rejection trade is aiming at, and the first target in the band-reversion convention §M26 records — was not in the swept space.

## The grid, and the endpoint that makes it comparable rather than adjacent

`--variants orb-fade` is the fade alone over five ranges, with `stop_range_fraction` at `[0.02, 0.05, 0.10, 0.25]`, `stop_offset_ticks` crossed at `[2, 8]` so the absolute floor separates from the proportional part, and a third target scheme `(0.5, 1.0, nan)`. **Every entry axis is held at exactly what §M28.2 swept**, so the bracket is the only thing that moved — which is what § "Parked is not abandoned" asks a re-run to be able to say.

`0.25` is the axis endpoint for the reason `1.0` was §M28.2's: it is the cell both runs share. **It reproduces §M28.2 exactly** — 1,920 configurations matched one-to-one on root, resolution, variant, direction and every entry axis, with identical trades, identical net P&L and profit factors equal to ten decimal places. The tighter fractions are the only thing new in the table.

Strata stated before the run, as §M28.2 established: `unfiltered` and `regime=CONSOLIDATING`. **The fade's own thesis rather than the breakout's** — `regime=DIRECTIONAL` is the hypothesis that a break out of a compressed range runs, and a fade asserts the opposite.

## Gate 1 — the axis is monotone, and below the shared endpoint it is empty

327,680 combinations in 22.5 minutes over the three passes, both roots, at the real commission for the root and one tick of slippage. Re-derivable from `results/campaign/OpeningRange.duckdb` and a measurement of one dated run. Share of combinations profitable, unfiltered, full window, MNQ / NQ:

| target      | frac 0.02     | 0.05          | 0.10          | 0.25          |
| ----------- | ------------- | ------------- | ------------- | ------------- |
| `R`         | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 | 0.028 / 0.052 |
| `width`     | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 | 0.052 / 0.069 |
| `width+mid` | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 | 0.041 / 0.064 |

**Those zeros are exact.** Not one of the **15,360** viable combinations below the shared endpoint is profitable on either root, and the best profit factor reached at each fraction rises with it — 0.545, 0.641, 0.922 — never touching 1.0. The median profit factor does the same: 0.088, 0.177, 0.315, 0.626.

**So the fade's stop axis is monotone in the same direction as the breakout's, and the fade is on the wrong side of the range to benefit.** §M28.2 found a breakout degrades smoothly to nothing as its stop tightens; the same gradient measured from the other extreme says a fade degrades smoothly to nothing as its stop approaches the level it entered at. The tight stop this re-run existed to test is not a bracket the archetype was denied. It is the bad end of an axis already known to be monotone, reached from the side where every value is the bad end.

**The midpoint target changes nothing, which retires the other half of the deferral.** `width+mid` sits between the other two schemes at the endpoint and is identically zero everywhere below it. The target was not what parked the fade either.

## Why the axis is monotone: the stop is inside the bar the order fills on

Gate 1 says the fade degrades smoothly as its stop tightens. This says why, and the reason is a property of **the entry** rather than of the stop — which is what makes it a finding rather than a restatement.

Measured on the configuration gate 1 ranks highest among the tight stops — NQ, 1-minute bars, the `overnight` range, short, `stop_offset_ticks=8`, 613 trades, a measurement of one dated run — the **adverse excursion inside the entry bar alone**. It is independent of the stop by construction: it is the bar the order filled on and nothing after it, so it is not the endogenous quantity `avg_mae_points` is.

| entry bar's adverse excursion | p25  | median    | p75   | p90   |
| ----------------------------- | ---- | --------- | ----- | ----- |
| points                        | 7.75 | **12.00** | 18.25 | 26.60 |

Against that, the stops the fraction axis produces on the same configuration:

| stop distance                   | 5.77 (frac 0.02) | 11.00 (0.05) | 18.85 (0.10) | 43.38 (0.25) |
| ------------------------------- | ---------------- | ------------ | ------------ | ------------ |
| exceeded by the entry bar alone | **84.7%**        | 56.0%        | 22.3%        | **2.4%**     |

**Profitability appears exactly where the stop clears the bar it enters on**, and the two tables are the same gradient read from either end. The corroborating counts move with it: same-bar exits run 89.6%, 24.3% and 1.9% across the three fractions, and stop exits 91%, 69% and 56%.

**A fade enters against a move that has just traded through the level, so the bar that fills it is the bar that move is happening on.** The stop distance is therefore not free: it is bounded below by the size of the bar the break happens on. A stop tighter than that is removed by the market before the thesis it protects has been tested.

Two controls, both on the same logs, rule out the alternatives:

- **Not a target mismatch.** `ORB_TARGET_R` scales the target down with the stop — 1.4 to 1.5 R at every fraction — and fails *harder* than the fixed-width target, at a profit factor of 0.19 against 0.35 at `frac=0.02`. Tightening both ends together is worse than tightening one.
- **Not the overnight range's width.** The `cash=30m` range, 105 points wide against the overnight's 163, shows the same shape at the same fractions: a 4.61-point stop, 92.1% same-bar exits and a profit factor of 0.11. The floor tracks the bar, not the range.

**What it adds to the verdict.** §M28.2 could say the fade failed across the stops it happened to sweep, and gate 1 above adds that it fails monotonically. This says the floor is set by the entry rule, so "a very tight stop just outside the range" is not a bracket the archetype was denied — it is one the entry cannot carry. It also makes a prediction the sweep did not need: **the floor should move with bar size and not with range width**. Half of that is measured here, in the two ranges above; the resolution half is not, and would be the cheapest way to falsify this.

**And it is the first reason to expect [#255] to behave differently rather than merely to be untested.** A limit resting inside the extreme fills as price comes *to* it, where a stop fills after price has already traded through — so the bar that fills a reversion entry is not by construction the bar the break is happening on. That is a different exposure to the quantity measured above, and it is the only part of this archetype the fade's own campaigns have not now bounded.

## The two shares move in opposite directions, and one of them is §M28.2's mechanism again

|                       | frac 0.02 | 0.05  | 0.10  | 0.25  |
| --------------------- | --------- | ----- | ----- | ----- |
| `ambiguous_share`     | 0.287     | 0.199 | 0.121 | 0.046 |
| `session_close_share` | 0.004     | 0.011 | 0.026 | 0.087 |

**A tight stop puts both bracket levels inside one bar**, so the fill assumption decides 29% of legs at the tightest fraction against 4.6% at the endpoint. That is the retest's mechanism reached by a different route: §M28.2 got there through a limit entry whose favourable extreme predates the fill, this gets there through a bracket narrow enough that one bar spans it. `.claude/rules/simulator.md`'s prediction holds a second time — each new geometry reaches rules the others made unreachable.

**It does not weaken the negative, and §M28.3 is why.** The ambiguity spread is one-sided by construction: every ambiguous bar the worst case resolves is one the ranked arm may have given to the target, so `AMBIGUITY_NEAREST_TO_OPEN` is the optimistic end of the band. Zero profitable combinations under the optimistic arm is zero under both, so the spread was not run — there is no shortlist whose attribution is in question.

The second row is the same geometry seen from the other side: a stop tight enough to be hit is a stop that resolves the trade long before the session close, so almost nothing is left to be flattened.

## Gate 2 — the held-out test reproduces gate 1 exactly

Through `campaign_holdout`'s own `verdict()`, unfiltered, per stop fraction — the shortlist's held-out profit factor, and how many of its twenty were profitable:

| frac | MNQ hold PF | NQ hold PF | profitable of 20, MNQ / NQ |
| ---- | ----------- | ---------- | -------------------------- |
| 0.02 | 0.210       | 0.274      | 0 / 0                      |
| 0.05 | 0.477       | 0.512      | 0 / 0                      |
| 0.10 | 0.811       | 0.789      | 0 / 0                      |
| 0.25 | 1.006       | 1.037      | 10 / 14                    |

**A shortlist of the twenty best tight-stop configurations, chosen on 60% of the series, does not contain one profitable configuration on the other 40%** — on either root, at any of the three fractions. The endpoint scrapes over 1.0, which is §M28.2's cell being marginal rather than anything this run added.

## One stratum passes on both roots, and it is the trade floor rather than a result

`regime=CONSOLIDATING@n=50` passes with held-out shortlist profit factors of 1.122 on MNQ and 1.495 on NQ, and NQ clears the drawdown gate as well. It is not a finding, for three reasons the standing rubric names and the run itself measures:

- **The shortlist sits on `MIN_TRADES`.** Held-out trades are a median of 31 and a *minimum* of 31 on MNQ, and 30 and 30 on NQ — every one of the forty configurations cleared the floor by at most a trade. §M28.1 could not call gate 4 on roughly 460 held-out trades; this is 960 and 615 spread across twenty configurations each.
- **The pre-registered cell fails.** `regime=CONSOLIDATING` at the campaign's raw thresholds fails on both roots. What passes is one of the five lookbacks `--regime-quantiles` splits it into, and choosing the lookback after the run is the comparison § "The strata, stated before the run" exists to refuse.
- **It is entirely one side and one range.** All forty are short fades of the `overnight` range, and every NQ row carries `stop_range_fraction=0.25` — the endpoint, not the tight stops the cell is being read for.

## The prediction, and it was the boring half that was right

[#256] stated the fork before the run: a tight stop that fails the same way is a stronger negative than the one already recorded, and a tight stop that does not is the first evidence that the bracket rather than the entry is what parked it. It is the first. **The fade's bracket now has a verdict rather than a parked configuration space** — the archetype is not retired, and § "Parked is not abandoned" is why — and it is a stronger negative than §M28.2's, because §M28.2 could only say the fade failed across the stops it happened to sweep, while the gradient beneath those stops now says which direction it fails in and that the failure deepens monotonically toward the geometry the setup is defined by.

**What that leaves.** The fade is not re-runnable on its bracket again: the stop axis has been swept from 0.02 to 1.0 of the range width and is monotone across the whole of it, and both target schemes are measured. What has *not* been tested is the entry, which § "Why the axis is monotone: the stop is inside the bar the order fills on" now names as the binding constraint rather than merely the untried half — [#255]'s limit resting at the extreme with no break required, which is a different trigger rather than a different bracket, and which reaches an order type the fade cannot express at all. § "Parked is not abandoned" is satisfied by that and by nothing else currently written down.

[#255]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/255
[#256]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/256
