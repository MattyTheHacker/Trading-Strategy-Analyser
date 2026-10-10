---
title: "M53 — pre-registration: EmaPullback's stop trailed on an average of its own"
archetypes: [EmaPullback]
issues: [74, 439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: EmaCrossover's moving-average trail on the trend archetype, in three arms over §M35's grid — the fixed stop, §M37's slow-average trail and the stop trailed on a third average over exactly the grid EmaCrossover's trail ran — in all 23 strata at 2, 5, 10 and 15 minutes; the third average beats an arm at a resolution only where, on both roots, the paired median profit-factor delta is positive with a sign test at p < 0.05 in both windows — §M37's bar, over a family of 8 — and gate 3 is read over the strata where it clears gate 2 on both roots, at most six, with the other two arms measured over the same family.
---

# M53 — pre-registration: EmaPullback's stop trailed on an average of its own ([#439])

[The build spec's three loose ends](build-spec-loose-ends-measured.md) measured EmaCrossover's moving-average trail as a cost in nineteen of twenty cells, and left one test un-run: **the trail has never been given an archetype whose edge is a trend**. EmaPullback is one — it buys a pullback to its fast average while that average is above the slow one, and sells the mirror image ([§M34](m34-ema-pullback-spec.md)) — and it already carries EmaCrossover's trail, a ratchet along a third average with its own kind, period and offset. [§M37](m37-ema-pullback-trail-on-slow.md) ran only the form tied to the slow average at the stop's own offset. This runs the free form, over the grid EmaCrossover's trail ran, so the archetype is the only thing that changed against the loose ends' test.

**What has changed since that test**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: the archetype, and nothing about the trail. Against §M37, the trail is no longer tied to the slow average and the stop's offset: this run sweeps its own, which the archetype could always do and no campaign had asked it to. No simulator code is new; the rules are `docs/nt8-fidelity.md` § "The build spec's three loose ends: the trail, the round number and the count" and §M34.

**This file was written and committed before the sweep started.** The arms, the strata, the bar sizes, the bar below and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                                                                                                                                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 3, in one pass (below)                                                                                                                                                                                                                                                           |
| **Grid**        | §M35's 2,304 combinations in every arm; the third-average arm crosses them with EmaCrossover's trail grid, kind `ema`/`sma` × period 20/50/100 × offset 2/8 ticks, for 27,648                                                                                                    |
| **Strata**      | all 23, one context dimension at a time, as §M35 and §M37 ran                                                                                                                                                                                                                    |
| **Resolutions** | 2, 5, 10 and 15 minutes, as §M35 and §M37 ran                                                                                                                                                                                                                                    |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                                                                                                                   |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                                                                                                                     |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                                                                                                                      |
| **Size**        | 11,870,208 combinations, both windows counted, seven times §M37's — about 16.5 hours on twelve workers at §M37's recorded rate, and about 50 on two at the 3.1× slowdown [#439] measured between the two, read as ±30%. A measure of size: the worker count is set where it runs |

```bash
uv run tools/campaign_sweep.py --variants emapullback-ma-trail --split \
    --strata emapullback-ma-trail --resolutions 2 5 10 15
```

### The arms

| arm                     | the stop                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| `stop=slow trail2=off`  | fixed where §M34 placed it: the control                                                        |
| `stop=slow trail2=slow` | trailed on the slow average at `stop_offset_ticks`: §M37's treatment                           |
| `stop=slow trail2=ma`   | trailed on a third average at `trail_offset_ticks`, its kind, period and offset swept as above |

**The first two are §M37's arms under new names**, so they cannot collide with §M37's rows in one database and can be checked against them.

**The third contains the second.** Where its average is the slow one, same kind and period, and its offset is the stop's 2 ticks, it trails the same stop as the slow arm: one combination in 24 of the arm, 1,152 per cell. `tests/test_emapullback_sim.py` pins that the two trade identically there.

## What will be read

1. **The control is a reproduction first.** Every `trail2=ma` row whose average is the slow one at the stop's offset must equal the `trail2=slow` row with the same §M35 parameters, on every stored statistic. And every `trail2=off` and `trail2=slow` row must equal §M37's `trail=off` and `trail=slow` row, where the database holds those rows on the same bars and swept after [#453], which the planned re-sweep of every stored campaign provides; otherwise that half is skipped and the read says so. A single difference is a defect, and nothing below is read until it is explained.
2. **The effect is read paired, never off a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, one row per root × resolution, **in the unfiltered stratum and in each window separately**, for two pairs: the third average against the fixed stop, which is the question the loose ends left, and the third average against the slow trail, which asks whether freeing the average from the one that placed the stop adds anything. The pairing takes the median over the third arm's twelve trail settings inside each cell, as the loose ends' read did. The pair count is printed and nothing is concluded from zero. Beside it: `session_close_share`, win rate, trades, average bars held and mean R.
3. **The verdict is §M37's bar.** The third average beats an arm at a resolution only where, **on both roots**, the pair's median delta is positive **and** the sign test reaches p < 0.05 **in both windows**. Two pairs × four resolutions is a family of 8. The same pairing over the other 22 strata is reported beside it as description, not a test, because the strata share bars.
4. **Whether the trail is mistuned is read inside its arm**: the η² of `trail_ma_kind`, `trail_ma_period` and `trail_offset_ticks` on profit factor, unfiltered, per root and window, the measure the loose ends used on EmaCrossover. Description, not a test.
5. **Gates 1 and 2 are §M35's, per arm.** Gate 1 is the share of unfiltered configurations with a profit factor above 1 at 30 trades or more. Gate 2 is `tools/campaign_holdout.py`'s `passes` per root and stratum, run once per arm with `--variant`. **A gate-2 count is not compared across arms**: the third arm's shortlist is drawn from twelve times the combinations, so it is a best-of-more and wins on size — `docs/roadmap.md` § "The build spec's three loose ends, measured".
6. **Gate 3's family is the strata where the third average clears gate 2 on both roots**, at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. **The fixed stop and the slow trail are measured over the same family** — both roots, the best five configurations by selection-window profit factor, measured on the holdout, 400 draws, the over-bars draw — so the three arms are read over the same cells. **A gate-3 difference between arms is description, not evidence for the trail**: the family is chosen on the third average's own gate 2, and its five are the best of twelve times the combinations, so both choices favour it, as §M37 said of its own family. If no stratum qualifies, gate 3 is not run, and that is the result.
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The reproduction holds**: exactly within the run, and against §M37's rows wherever they are on the same bars.
- **Against the fixed stop, the third average lowers `session_close_share` and the bars held, and raises the trade count, in all sixteen root × resolution × window cells**, as §M37's slow trail did in all sixteen.
- **It clears the bar against the fixed stop at no resolution.** §M37's slow trail cost where the fixed stop's median configuration won and paid where it lost, a property of the period rather than of the configuration: a cost on the selection window in seven of eight cells and a gain held out in six.
- **It clears the bar against the slow trail at no resolution either.**
- **Inside its arm, `trail_ma_period` is the largest of the three trail axes, and all three sit below an η² of 0.04** — the loose ends' "trailing at all is the cost; where the average sits is not a lever", repeated on a second archetype.

## What this run is not

- **Not EmaCrossover's other two loose ends.** The round-number rule per contract and the confluence count over informative filters are separate items in [#439].
- **Not the per-contract dispersion read** the loose ends owe for the trail. It runs with `tools/campaign_contracts.py` over a shortlist and is not pre-registered here.
- **Not §M37's deferrals**: arming after the first target, a follow rather than a ratchet, and §M36's fitted `volume=THIN` cell.
- **Not one minute**, which EmaPullback has never been swept at with a split.
- **Not a port.** EmaPullback has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
