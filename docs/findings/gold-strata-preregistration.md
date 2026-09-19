---
title: "Pre-registration: does EmaCrossover's gold result survive stratification?"
archetypes: [EmaCrossover, InsideBar, InsideBarTrailing, SqueezeBreakout, EmaPullback, ElasticBand]
issues: []
gates: [3, 4]
outcome: spec
verdict: >-
  Written before the matched null runs on 136 stratified cells: EmaCrossover's gold cells must clear at a higher rate than its own S&P cells and at least 4 of 16 gold pairs must clear on both roots, or the unfiltered result is one lucky cell of twenty-three.
---

# Pre-registration: does EmaCrossover's gold result survive stratification?

**This file is written before the test it describes is run.** Nothing in `results/gates-5-10-15/strata/` exists at the time of writing. The point is to commit to a threshold in advance, because the result it is testing was found by looking — twenty-three cells were taken through gates 3 and 4 after gate 2 picked them, and EmaCrossover-on-gold came out of that search rather than into it.

## What is already known, and therefore cannot be predicted

Being precise about this is the whole value of the file.

| already measured                                        | status                                                   |
| ------------------------------------------------------- | -------------------------------------------------------- |
| The 5/10/15 sweep on ES, MES, GC and MGC, all 23 strata | done — 5.94M rows                                        |
| Gate 1 and gate 2 on every stratum                      | done — read as queries, used to pick the 136 cells below |
| Gates 3 and 4 on the 23 **unfiltered** cells            | done                                                     |
| **Gates 3 and 4 on the 136 stratified cells**           | **not run — this is what is predicted**                  |

The narrowing to 136 used gate-2 results, so these are not a random sample of cells and the predictions below are conditional on that narrowing. What they are not conditioned on is any null test in a stratified cell, because none has been run.

## The cells

136 cells, from gate-2 passes filtered to `session_close_share` at or below 0.30 and then to those holding on **both roots of a pair** — GC with MGC, ES with MES. That is 68 pairs, 20 configurations each, **2,720 matched-null tests**, of which **136 are expected significant at p ≤ 0.05 by chance alone**.

| archetype         | gold cells (pairs) | S&P cells (pairs) |
| ----------------- | ------------------ | ----------------- |
| EmaCrossover      | 32 (16)            | 12 (6)            |
| InsideBar         | 14 (7)             | 14 (7)            |
| SqueezeBreakout   | 12 (6)             | 16 (8)            |
| InsideBarTrailing | 8 (4)              | 12 (6)            |
| EmaPullback       | 8 (4)              | 0                 |
| ElasticBand       | 0                  | 8 (4)             |

EmaCrossover's 32 gold cells span 14 distinct strata at 5 and 10 minutes, so the question is whether the edge is a property of the archetype on this market or of one context cut.

## Definitions, fixed now

- **A cell clears** when at least **5 of its 20** configurations show a positive profit-factor excess over the matched random entry at **p ≤ 0.05**. Five is 5× the one-in-twenty expected by chance, and is what EmaCrossover managed unfiltered on each gold root.
- **A pair clears** when both its roots clear. Single-root results do not count, for the reason `docs/nt8-fidelity.md` gives for running the two roots against each other.
- **The draw** is `bars` for every archetype except OpeningRange, which has none here.

## The predictions

**P1 — primary.** At least **4 of EmaCrossover's 16 gold pairs** clear, **and** EmaCrossover's gold clear rate exceeds its own S&P clear rate.

**P2 — specificity.** EmaCrossover's advantage is gold-specific. If its 6 S&P pairs clear at the same rate or better, the finding is not "gold behaves differently" but "EmaCrossover travels" — a different and weaker claim, given it failed gate 1 on ES and MES outright.

**P3 — the family is not noise.** Across all 2,720 tests, the count of positive results at p ≤ 0.05 exceeds **204**, which is 1.5× the 136 expected by chance. Tests within a cell are correlated, so this is a coarse check on the whole exercise rather than a per-cell one: a total near 136 means the stratified layer adds nothing whatever any single cell does.

**P4 — the clock control.** InsideBar has the only balanced split, 7 gold pairs against 7 S&P, and cleared nothing at gate 4 unfiltered. It clears fewer gold pairs than EmaCrossover does.

**P5 — the contamination control.** SqueezeBreakout posted the largest unfiltered gate-4 numbers — 18 of 20 configurations above the bootstrap floor on GC at 15 minutes — on a `session_close_share` of 0.466 and 0.525. Those cells are excluded here by the 0.30 filter. With the clock removed, SqueezeBreakout clears a **lower** share of its gold pairs than EmaCrossover does.

## What falsifies the headline

**If P1 fails, EmaCrossover-on-gold does not survive stratification**, and the unfiltered result should be read as one cell that got lucky among the twenty-three taken through gate 3 — not as an edge. That reading is then the finding, and it should be written up as such rather than quietly dropped.

**If P1 passes but P2 fails**, the claim changes from a statement about gold to a statement about the archetype, and the S&P evidence contradicts it. Report both.

**If P3 fails while P1 passes**, one archetype is carrying a family that is otherwise noise. That is possible and it is also exactly what a multiple-comparisons artefact looks like, so P1 would need re-testing on data this campaign has not touched before being believed.

## Rules fixed in advance

- **The 5-of-20 threshold does not move** after results are seen, and neither does the 0.30 `session_close_share` filter or the both-roots requirement.
- **No cell is added or dropped** once the run starts. The 136 are in `results/gates-5-10-15/strata-narrowed.csv`.
- **No stratum is excluded post hoc** for looking anomalous.
- **A cell whose null is refused** — `randomentry` below `MIN_DRAW_FREEDOM` — counts as not clearing, never as absent. A gate that could not run is not a gate that passed.
- Everything is read on the **holdout**, ranked on the **selection** window, which is what `--held-out` pairs.

## Running it

```bash
bash results/gates-5-10-15/run-strata-gates.sh 2>&1 | tee results/gates-5-10-15/strata-progress.log
```

About 2.6 hours: 1.51h for the nulls, 0.38h walk-forward, 0.76h for the stored logs and the bootstrap. Resumable — every step writes a marker and is skipped on restart. `--n-jobs` stays at 8.

**The runner and the cell list are under `results/`, which is gitignored**, so they exist only on the machine that produced them — the same gap [#91] records for `verification/`. The 136 cells are re-derivable from the criteria in "The cells" above, and that definition rather than the CSV is what this pre-registration binds.

## What this cannot settle

Even a clean pass leaves the hypothesis tested on the archive that produced it. The 1 and 2-minute resolutions are the same bars re-aggregated and are not independent. **The strongest available test is another metal** — silver and crude are already in `nqbt/instruments.py` and neither has been ingested — and that is the test to run before any of this reaches NinjaTrader.

[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
