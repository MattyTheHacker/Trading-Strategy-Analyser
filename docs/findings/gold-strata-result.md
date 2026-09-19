---
title: "The gold strata test: EmaCrossover's edge does not survive stratification"
archetypes: [EmaCrossover, InsideBar, InsideBarTrailing, SqueezeBreakout, EmaPullback, ElasticBand]
issues: []
gates: [3, 4]
outcome: negative
verdict: >-
  Pre-registered and falsified: 1 of EmaCrossover's 16 gold pairs clears against the 4 required, the one that does is the unfiltered cell already known, and the direction inverts — it clears 3 of 6 S&P pairs against gold's 1 of 16.
---

# The gold strata test: EmaCrossover's edge does not survive stratification

The test [`gold-strata-preregistration.md`](gold-strata-preregistration.md) committed to, run afterwards and scored against the thresholds fixed in advance. **The primary prediction fails**, and the honest reading is the one the pre-registration named: the unfiltered gold result was one cell that got lucky among the twenty-three taken through gate 3.

## In plain terms

A strategy called EmaCrossover looked good on gold. Before checking further, a set of thresholds was written down: for the result to be real, it had to keep working when the data was sliced by market conditions — at least 4 of 16 slices, and more often on gold than on the S&P.

It managed **1 of 16**, and that one slice was the un-sliced case already known about. On the S&P — where it was supposed to be *worse* — it managed 3 of 6. The edge was not a property of gold, and on this evidence it was not an edge.

## What was run

136 cells, 20 configurations each, **2,720 matched-null tests**, all 544 steps completing with no failures and **no cell refused a null**. About 3.5 hours.

The scoring rules were fixed in advance and are not restated here from memory — a cell clears at **5 of 20** configurations with a positive profit-factor excess at **p ≤ 0.05**, and a pair clears when **both roots** of GC/MGC or ES/MES clear.

## The scorecard

|        | prediction                              | required                            | measured                       |          |
| ------ | --------------------------------------- | ----------------------------------- | ------------------------------ | -------- |
| **P1** | EmaCrossover's gold pairs clear         | ≥ 4 of 16, and gold rate > S&P rate | **1 of 16** (0.062), S&P 0.500 | **FAIL** |
| **P2** | the advantage is gold-specific          | S&P clears at a lower rate          | **S&P clears 8× more often**   | **FAIL** |
| **P3** | the family is not noise                 | > 204 positives of 2,720            | 357                            | pass     |
| **P4** | InsideBar clears fewer gold pairs       | fewer than EmaCrossover             | 0 of 7 against 1 of 16         | pass     |
| **P5** | SqueezeBreakout clears fewer gold pairs | fewer than EmaCrossover             | 0 of 6 against 1 of 16         | pass     |

**The two that mattered both fail, and P4 and P5 pass only because everything on gold is near zero.** A control that is satisfied by the thing it controls for also collapsing is not evidence of anything, and it is recorded that way rather than as three passes out of five.

## P1: one cell, and it is the one already known

EmaCrossover's significant count per gold cell, out of 20:

| resolution | stratum                                                                         | GC    | MGC   |
| ---------- | ------------------------------------------------------------------------------- | ----- | ----- |
| 5          | **unfiltered**                                                                  | **5** | **5** |
| 5          | phase=OVERNIGHT                                                                 | 5     | 3     |
| 5          | compression=NORMAL                                                              | 4     | 1     |
| 5          | htf=ABOVE                                                                       | 4     | 3     |
| 10         | htf=ABOVE                                                                       | 2     | 5     |
| 5          | volume=HEAVY                                                                    | 2     | 2     |
| 5          | trend=UP                                                                        | 0     | 2     |
| 5          | volume=THIN                                                                     | 2     | 0     |
| 5          | htf=BELOW, regime=CONSOLIDATING, regime=UNCLASSIFIABLE, trend=DOWN, trend=MIXED | 0     | 0     |
| 10         | compression=COMPRESSED, compression=NORMAL, trend=MIXED                         | 0–1   | 0–1   |

**Zero of the fourteen stratified gold cells clear on both roots.** The only pair that clears is `unfiltered` at 5 minutes, at exactly 5 and 5 — the threshold, not past it, and the cell the hypothesis was built from. Five gold cells return **not one** significant configuration in twenty on either root.

## P2: the direction inverts

EmaCrossover clears **3 of 6 S&P pairs** — `htf=BELOW`, `phase=OVERNIGHT` and `regime=UNCLASSIFIABLE`, all at 5 minutes — against 1 of 16 on gold. The pre-registration anticipated equality as the failure mode and called it "EmaCrossover travels". What happened is worse than that for the hypothesis: **gold is where it stops working once the data is sliced.**

This is not a new finding in the other direction. EmaCrossover failed gate 1 outright on ES and MES — 0.0% to 15.4% of configurations profitable — so three cleared pairs out of six sit on an archetype that loses money across that market's parameter space. Six pairs is also a small denominator. It is an observation that would need its own pre-registered test, on data neither this campaign nor this file has touched, and it is recorded here so that it cannot later be presented as a prediction.

## P3 passes, and the concentration is why it should not be read as support

357 of 2,720 tests are positive at p ≤ 0.05 against 136 expected, clearing the pre-registered bar of 204. But:

- **284 of the 357 sit inside the 25 cells that clear.** The family is not diffusely elevated; a handful of cells carry almost all of it.
- **79 of 136 cells return zero significant configurations.**
- Tests within a cell share an archetype and a set of bars, so twenty of them are nowhere near twenty independent trials — which is exactly why the pre-registration called P3 "a coarse check on the whole exercise rather than a per-cell one".

P3 passing while P1 fails means the stratified layer does contain more than noise, and that **whatever it contains is not where the hypothesis said it would be**.

## What this settles, and what it does not

**Settled: the gold result does not survive stratification, and should not be carried forward as an edge.** `docs/findings/cross-root-transfer.md` and the unfiltered gate reads stand as measurements of what they measured; what does not stand is the inference that EmaCrossover has found something on gold.

**Not settled: whether anything is there at all.** One cell clearing at exactly the threshold is consistent with a weak real effect and with luck, and 2,720 tests cannot separate them. The pre-registration already named the only test that could — **another metal**. Silver and crude are in `nqbt/instruments.py` and neither has been ingested.

**Method note worth keeping.** This is the first pre-registered test in the project, and it is the cheapest useful thing done in this sequence: the run was going to happen anyway, the document cost no compute, and it converted a result that would have been read as encouraging into one that is read correctly. The five-of-twenty threshold and the both-roots rule were what made the answer unambiguous, and both were chosen before any stratified cell had been tested.
