---
id: M44
title: "M44 — the registry re-swept on a repaired archive, and the three gates re-read against it"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [360]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  Gate 3 reproduces almost exactly — 47 of 200 tests clear p = 0.05 against §M28.16's 46, and three of its four both-root cells hold — while §M42's exclusion reading does not, falling from nine survivors of twenty to one; and the archive is now one series on both roots, so every stored row is re-derivable for the first time since it was extended.
---

# M44 — the registry re-swept on a repaired archive, and the three gates re-read against it ([#360])

The first re-sweep since the registry was built. [#344] froze the archive so that no stored campaign would lose its series; [#360] found that the NQ half had already lost it, and named the decision this campaign takes: **re-sweep rather than keep reading rows nothing can reproduce.**

## In plain terms

Every result this project has recorded was measured against a particular stretch of price history. That history got extended in September 2026, which quietly moved the boundary between the half used to choose settings and the half used to test them. For the small Nasdaq contract the extension was only at the recent end, so the old boundary could be recovered by trimming back. For the full-size contract it was not, and nothing could re-derive the stored numbers at all.

So the whole thing was measured again from scratch: one archive, one boundary, both contracts, all nine strategies. Then the three tests that decide whether a result means anything were re-run on it.

**Almost everything reproduced.** The strategy rankings, the held-out ordering, and — most importantly — the significance test came back nearly identical. One reading did not, and it is the one that had been the most encouraging.

## What changed in the data, and why

Three things, in the order they were found.

**A week of bars was stamped 672 minutes early.** Sunday 2020-10-18 to Friday 2020-10-23 sits in the archive with its timestamps 11 hours 12 minutes ahead of the bars they label, across thirteen contracts on six roots. `docs/nt8-fidelity.md` § "A week of bars is stamped 672 minutes early" carries the measurement and the evidence. The archive is trimmed forward past it, which is what forced the re-sweep to be a re-sweep rather than an extension.

**Three roots were added and one of them does not splice.** CL, SI and SIL were staged and deliberately unread under [#344]; all three are now ingested. SI splices and reconciles against SIL to within a single session. **CL and SIL do not splice at all**, for two unrelated reasons recorded in `.claude/rules/data-pipeline.md` § "Rolls". Neither is in the campaign — that is both index roots only — so neither blocks anything here.

**The series is about 30% longer than the one every earlier campaign ran on.** It now begins 2020-10-26 on both roots rather than 2022-03, which is the single largest reason any figure below differs from its predecessor. More bars, more regimes, and a selection/holdout boundary in a different place.

## What was run

The full registry grid on both index roots at the root's own commission and one tick of slippage, then the same grids again split into a selection window and a held-out one, then every variant grid each archetype owns, then the hold ladder and the fitted volume re-cut. Resolutions 2, 5, 10 and 15 throughout; **one minute was run only on the unsplit pass and deliberately not backfilled**, because it is 54% of the bar-work and every archetype's median configuration loses money there (§M27).

Every pass is count-exact against its grid — the stored row count for each archetype × stratum-set × window equals combinations × cells × resolutions × roots with no remainder, so no pass is partial.

## Gate 2 — the ordering is unchanged

412 of 890 root × stratum cells clear the held-out bar and 124 return their own drawdown. The ranking is what §M27 and §M28.1 already describe: OpeningRange and InsideBar at the top, DeadCatBounce and PullBackAndGo at the bottom, with nothing above them that was not above them before.

**The 124-in-890 rate is not comparable to §M28.9's "one cell in thirteen".** That figure was measured over a smaller and differently-cut set of cells; this one includes the fitted volume re-cuts, which §M30 added afterwards. Two rates over two populations.

## Gate 3 — reproduces, closely

§M28.16's ten pre-registered cells, both roots, 5-minute bars, ranked on the selection window by profit factor and tested on the holdout, 400 draws, top ten per cell: **10 cells × 2 roots × 10 configurations = 200 tests**, the same family as before, with OpeningRange's five cells under `--draw levels` for the reason §M28.2 records.

| cell                                 | root | trades  | profit factor | null        | beats null | p < 0.05 | §M28.16 |
| ------------------------------------ | ---- | ------- | ------------- | ----------- | ---------- | -------- | ------- |
| InsideBarTrailing `phase=MIDDAY`     | MNQ  | 348–382 | 1.298–1.411   | 1.022–1.060 | 10 of 10   | **5**    | 5       |
| InsideBarTrailing `phase=MIDDAY`     | NQ   | 332–392 | 1.171–1.464   | 1.020–1.068 | 10 of 10   | **3**    | 4       |
| OpeningRange `volume=NORMAL`         | MNQ  | 377–415 | 1.075–1.188   | 0.871–0.900 | 10 of 10   | **10**   | 6       |
| OpeningRange `volume=NORMAL`         | NQ   | 379–380 | 1.080–1.179   | 0.906–0.926 | 10 of 10   | **9**    | 10      |
| OpeningRange `regime=UNCLASSIFIABLE` | MNQ  | 184–206 | 1.081–1.416   | 0.860–0.916 | 10 of 10   | **8**    | 9       |
| OpeningRange `regime=UNCLASSIFIABLE` | NQ   | 189–195 | 1.186–1.278   | 0.876–0.930 | 10 of 10   | **7**    | 4       |
| OpeningRange `compression=EXPANDED`  | MNQ  | 374     | 1.034–1.116   | 0.904–0.924 | 10 of 10   | 2        | 6       |
| OpeningRange `compression=EXPANDED`  | NQ   | 371–375 | 1.025–1.101   | 0.902–0.922 | 10 of 10   | 0        | 2       |
| OpeningRange `volume=THIN`           | MNQ  | 181–192 | 1.066–1.202   | 0.924–0.962 | 10 of 10   | 0        | 0       |
| OpeningRange `volume=THIN`           | NQ   | 187–194 | 0.997–1.044   | 0.957–0.970 | 10 of 10   | 0        | 0       |
| OpeningRange `regime=DIRECTIONAL`    | MNQ  | 49–61   | 0.951–2.490   | 1.661–2.450 | 2 of 10    | 0        | 0       |
| OpeningRange `regime=DIRECTIONAL`    | NQ   | 50–60   | 0.827–2.368   | 1.701–2.656 | 0 of 10    | 2        | 0       |
| InsideBar `regime=UNCLASSIFIABLE`    | MNQ  | 563–644 | 1.091–1.169   | 0.870–0.921 | 10 of 10   | 0        | 0       |
| InsideBar `regime=UNCLASSIFIABLE`    | NQ   | 550–627 | 0.988–1.109   | 0.911–0.956 | 10 of 10   | 0        | 0       |
| DeadCatBounce `htf=BELOW`            | MNQ  | 86–141  | 0.861–1.184   | 0.586–0.647 | 10 of 10   | 0        | 0       |
| DeadCatBounce `htf=BELOW`            | NQ   | 119–158 | 1.076–1.351   | 0.663–0.708 | 10 of 10   | 1        | 0       |
| EmaCrossover `phase=CASH_OPEN`       | MNQ  | 155–306 | 0.842–1.168   | 0.944–1.043 | 6 of 10    | 0        | 0       |
| EmaCrossover `phase=CASH_OPEN`       | NQ   | 153–311 | 0.901–1.163   | 0.954–1.079 | 7 of 10    | 0        | 0       |
| EmaCrossover `phase=MIDDAY`          | MNQ  | 287–473 | 0.894–1.057   | 0.966–1.081 | 2 of 10    | 0        | 0       |
| EmaCrossover `phase=MIDDAY`          | NQ   | 290–443 | 0.941–1.076   | 0.993–1.120 | 1 of 10    | 0        | 0       |

**47 of 200 clear p = 0.05, against §M28.16's 46.** Nothing was refused; the levels draw runs on all five OpeningRange cells as before.

**Three of the four both-root cells hold.** InsideBarTrailing's midday cell, OpeningRange's `volume=NORMAL` and OpeningRange's `regime=UNCLASSIFIABLE` all clear on both roots again. **`compression=EXPANDED` drops out**, falling from 6 and 2 to 2 and 0 — the one cell of the four whose result was a window's rather than a property. Two cells gain a single root each, DeadCatBounce's and OpeningRange's `regime=DIRECTIONAL`, and neither is a both-root pass.

**The arrangement is what reproduces, not just the count.** §M28.16's reading was that chance alone would scatter about 10 of 200 below 0.05 while the observed 46 sat in four cells. The observed 47 sit in the same places: OpeningRange and InsideBarTrailing carry all but three of them, EmaCrossover's two phases carry none on either root exactly as before, and `volume=THIN` still carries none. An independent 30% of extra history moved the count by one.

Two things that were true then and are true now. **Ten configurations of one cell are not ten tests** — they are overlapping shortlists over the same bars under the same filter, so their p-values move together. And **the cells were chosen after a consistency score had been looked at**, which this re-run does not undo; it inherits that.

**The family that nominated them no longer reproduces.** `tools/campaign_crossread.py --min-score 8` now names 25 consistent cells rather than §M28.14's twelve, and **InsideBarTrailing's midday cell is not among them** — its `regime=UNCLASSIFIABLE` sibling is instead. Part of that is a stricter bar, because one-minute rows are absent from the split windows so a perfect score is 8 of 8 rather than 8 of 10. But the membership genuinely moved, and four of §M28.16's ten cells are no longer consistent. **The nomination route is less stable than the null result it produced**, which is an argument for the null and against the score — the same direction §M28.16 found when it measured the score's rank correlation with the outcome at −0.132.

## Gate 4 — §M42's cell, and the one reading that does not reproduce

§M42's protocol on the midday cell: the held-out book at 5 minutes, variant `trailing`, ten configurations per root, `--rerun` so each read simulates a fresh book rather than reading a stored log.

**The bootstrap reproduces.** All ten MNQ configurations put a 5th percentile above a profit factor of 1.0, at 1.007–1.077 against observations of 1.298–1.411 — still the only place in the project that holds. NQ manages 7 of 10.

**The walk-forward reproduces.** Five folds, selection on train and measurement on test, passing on both roots: pooled 1.312 on MNQ over 438 test trades and 1.342 on NQ over 450, against §M42's 1.44.

**The exclusion does not.**

| | §M42 | M44 |
| --- | --- | --- |
| profitable without `session_close` legs, MNQ | 5 of 10 | **1 of 10** |
| profitable without `session_close` legs, NQ | 4 of 10 | **0 of 10** |
| clearing both gate-4 thresholds | 5 of 20 | **0 of 20** |
| median profit factor, whole → excluded, MNQ | 1.482 → 0.975 | 1.381 → 0.761 |
| median profit factor, whole → excluded, NQ | — | 1.361 → 0.581 |

The session-close legs are about a quarter of all legs, which is the share §M42 recorded, and they carry more than the entire net: MNQ's median book is +38,594 whole and −20,176 with them removed. §M42's nine survivors of twenty become one.

**This is not a disqualification, and [#344] is why.** The exclusion read is a decomposition and not a counterfactual — a leg the clock closed is a leg the stop did not take — and that epic settled that a forced-flat-dependent result is not discounted. Three of its reasons apply directly here. Gate 3's matched random entry runs through the same simulator and is flattened identically, so the p-values above are already net of the flatten. The flatten is mandatory live, so the whole book is the book that trades. And close share does not order the null result (§M38).

So what this changes is narrower than it looks. **§M42's claim to be the first cell in the registry to survive the exclusion at all does not hold on more data** — the pattern it broke, §M28.15's 0 of 40 and §M31.1's 0 of 20, reasserts itself. What it does not change is the cell's standing as the candidate: its whole-book edge survives the holdout, the matched null at p = 0.05 on both roots, bootstrap resampling and a five-fold walk-forward, and [#344]'s deciding factor was never the exclusion but the reconciled C# port.

The honest reading is that the exclusion result was the most window-dependent of §M42's three, and that a campaign which had run it once had no way to know which.

## #360 answered, and what it cost

Every archetype now holds stored trade logs for both the full and the held-out window on **both** roots — the thing [#360] reported as impossible on NQ, where `campaign_shortlist` and everything downstream refused outright. There is no longer a stored row whose series differs from the current archive, so the register's instruction to re-derive any figure from the campaign databases is true again.

It is true only for campaigns from this one forward. **Every gate-3 and gate-4 figure in §M28.16, §M42 and §M43 is now re-derivable only from the set moved aside before this re-sweep**, and the NQ half of it was already unrecoverable for the reason [#360] gives. Those campaigns are not wrong; they are measurements of an archive that no longer exists, and this file is the second measurement rather than a correction of the first.

## What this does not settle

- **One minute is unmeasured in every split window.** A deliberate omission, not a gap, but any cross-resolution reading of the new tables has four rungs rather than five.
- **The cells are still §M28.14's**, chosen after looking, and the family that chose them no longer reproduces. A pre-registered family over the 25 consistent cells this campaign names is the next honest step and is not taken here.
- **CL and SIL have no continuous series**, so two of the three new roots are ingested and unusable.
- **`compression=EXPANDED` losing its both-root pass is one observation**, not a refutation; at 371–375 trades and a null spread that tight, 2 and 0 against 6 and 2 is within what ten overlapping shortlists can move.
- **Nothing here re-reads the prop-account objectives.** §M40's and §M43's rankings were computed on the older set; the replay has been re-run across all nine archetypes on both roots but is not analysed in this file.

Every figure here is one dated run over the archive as it stands, re-derivable from the campaign databases and the campaign tools named above — not a standing property.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#360]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/360
