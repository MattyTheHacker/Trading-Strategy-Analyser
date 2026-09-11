---
id: M28.16
title: "M28.16 — the ten consistent cells through the matched null, and what a consistency score is worth"
archetypes: [DeadCatBounce, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange]
issues: [288]
gates: [3]
outcome: mixed
verdict: >-
  Four cells clear p = 0.05 on both roots — three OpeningRange's and one InsideBarTrailing's midday cell — and a consistency score does not order the null result, correlating −0.132 with it.
---

# M28.16 — the ten consistent cells through the matched null, and what a consistency score is worth ([#288])

**No new sweep.** §M28.14 scored every stratum against its unfiltered twin and named twelve cells that won in both windows on at least 8 of 10 `root x resolution` cells. Two were taken to a matched null there; **ten were not**, and a score is a consistency check rather than evidence — that section says so itself. This is gate 3 over the other ten.

## The family, stated before the run rather than counted after it

`tools/campaign_crossread.py --min-score 8` reproduces the twelve, so the family is read off the tool rather than off §M28.14's table. Removing the two already nulled leaves ten cells, each run on **both roots** at 5-minute bars, ranked on the selection window by profit factor and tested on the holdout, 400 draws, top ten: **10 cells × 2 roots × 10 configurations = 200 tests.** Nothing below was added to the family after the first run.

`tools/campaign_null.py` takes several `--root` and several `--stratum` values for that reason — the family is the command's argument and its size is printed before the first cell, where twenty single-cell invocations driven from a script leave it to be recounted afterwards. The per-cell summary it prints is `family`.

**OpeningRange's four cells run under `--draw levels`.** Its trigger is a level, so the over-bars draw is refused inside a stratum exactly as §M28.2 and §M28.14 record; the levels arm permutes which session's range is traded and holds the signal itself fixed. Every row carries the draw it was produced under.

**Every comparison against §M27's gate 3 below is a sanity check rather than a pair.** That read placed each archetype's unfiltered shortlist against its null; these are strata at one fixed bar size, so the two differ in the cut and in the resolution at once — §M27.5 on why cross-resolution rows are not twins.

## The ten cells, ranked on selection and tested on holdout

| cell                                 | root | draw   | trades  | profit factor | null        | excess          | beats null | p < 0.05     | net/drawdown |
| ------------------------------------ | ---- | ------ | ------- | ------------- | ----------- | --------------- | ---------- | ------------ | ------------ |
| EmaCrossover `phase=CASH_OPEN`       | MNQ  | bars   | 169–255 | 0.893–1.146   | 0.980–1.047 | −0.094 – +0.148 | 6 of 10    | 0 of 10      | −0.465–1.254 |
| EmaCrossover `phase=CASH_OPEN`       | NQ   | bars   | 163–257 | 0.895–1.192   | 0.999–1.091 | −0.138 – +0.182 | 5 of 10    | 0 of 10      | −0.418–1.762 |
| EmaCrossover `phase=MIDDAY`          | MNQ  | bars   | 190–379 | 0.916–1.056   | 0.934–1.089 | −0.112 – +0.059 | 3 of 10    | 0 of 10      | −0.394–0.401 |
| EmaCrossover `phase=MIDDAY`          | NQ   | bars   | 210–321 | 0.887–1.123   | 0.909–1.128 | −0.123 – +0.188 | 3 of 10    | 0 of 10      | −0.545–0.871 |
| InsideBarTrailing `phase=MIDDAY`     | MNQ  | bars   | 273–300 | 1.398–1.587   | 1.018–1.051 | +0.347 – +0.560 | 10 of 10   | **5 of 10**  | 2.679–4.494  |
| InsideBarTrailing `phase=MIDDAY`     | NQ   | bars   | 260–276 | 1.288–1.685   | 1.053–1.084 | +0.214 – +0.608 | 10 of 10   | **4 of 10**  | 1.618–5.170  |
| InsideBar `regime=UNCLASSIFIABLE`    | MNQ  | bars   | 454–634 | 0.979–1.159   | 0.888–0.931 | +0.050 – +0.271 | 10 of 10   | 0 of 10      | −0.178–1.007 |
| InsideBar `regime=UNCLASSIFIABLE`    | NQ   | bars   | 432–529 | 0.874–1.147   | 0.903–0.940 | −0.061 – +0.225 | 9 of 10    | 0 of 10      | −0.599–1.090 |
| DeadCatBounce `htf=BELOW`            | MNQ  | bars   | 68–84   | 0.834–1.258   | 0.578–0.627 | +0.249 – +0.675 | 10 of 10   | 0 of 10      | −0.555–0.849 |
| DeadCatBounce `htf=BELOW`            | NQ   | bars   | 81–121  | 1.170–1.370   | 0.675–0.712 | +0.476 – +0.658 | 10 of 10   | 0 of 10      | 0.567–1.584  |
| OpeningRange `compression=EXPANDED`  | MNQ  | levels | 301     | 1.072–1.180   | 0.912–0.929 | +0.150 – +0.266 | 10 of 10   | **6 of 10**  | 0.421–1.003  |
| OpeningRange `compression=EXPANDED`  | NQ   | levels | 293–296 | 1.087–1.144   | 0.924–0.937 | +0.161 – +0.218 | 10 of 10   | **2 of 10**  | 0.478–0.773  |
| OpeningRange `regime=UNCLASSIFIABLE` | MNQ  | levels | 143–147 | 0.964–1.382   | 0.838–0.888 | +0.122 – +0.510 | 10 of 10   | **9 of 10**  | −0.165–1.785 |
| OpeningRange `regime=UNCLASSIFIABLE` | NQ   | levels | 146–150 | 1.103–1.259   | 0.839–0.901 | +0.236 – +0.379 | 10 of 10   | **4 of 10**  | 0.486–1.161  |
| OpeningRange `volume=THIN`           | MNQ  | levels | 150–151 | 1.187–1.270   | 0.965–0.992 | +0.206 – +0.305 | 10 of 10   | 0 of 10      | 1.766–2.629  |
| OpeningRange `volume=THIN`           | NQ   | levels | 146–149 | 1.035–1.086   | 0.991–1.018 | +0.017 – +0.086 | 10 of 10   | 0 of 10      | 0.163–0.366  |
| OpeningRange `regime=DIRECTIONAL`    | MNQ  | levels | 56–58   | 1.409–1.659   | 1.079–1.131 | +0.301 – +0.533 | 10 of 10   | 0 of 10      | 2.021–2.862  |
| OpeningRange `regime=DIRECTIONAL`    | NQ   | levels | 43–59   | 1.408–1.781   | 1.099–1.199 | +0.244 – +0.683 | 10 of 10   | 0 of 10      | 2.021–4.301  |
| OpeningRange `volume=NORMAL`         | MNQ  | levels | 271–307 | 0.964–1.230   | 0.854–0.907 | +0.105 – +0.335 | 10 of 10   | **6 of 10**  | −0.236–1.320 |
| OpeningRange `volume=NORMAL`         | NQ   | levels | 304     | 1.135–1.225   | 0.926–0.945 | +0.204 – +0.293 | 10 of 10   | **10 of 10** | 0.788–1.309  |

**176 of the 200 configurations beat their own null and 46 clear p = 0.05.** Nothing was refused: the levels draw runs on all four OpeningRange cells.

## The consistency score does not order the null result, and the two largest score worst

Rank correlation between §M28.14's score and a cell's median profit-factor excess is **−0.132**, and between the score and its median p **+0.105**. Both are nothing, over ten points taking three distinct score values — so read the arrangement rather than the coefficient:

| cell                                 | score | median excess | median p |
| ------------------------------------ | ----- | ------------- | -------- |
| DeadCatBounce `htf=BELOW`            | +9    | +0.504        | 0.125    |
| InsideBarTrailing `phase=MIDDAY`     | +10   | +0.430        | 0.060    |
| OpeningRange `regime=UNCLASSIFIABLE` | +10   | +0.365        | 0.032    |
| OpeningRange `regime=DIRECTIONAL`    | +8    | +0.333        | 0.284    |
| OpeningRange `volume=NORMAL`         | +8    | +0.250        | 0.027    |
| OpeningRange `compression=EXPANDED`  | +10   | +0.197        | 0.057    |
| InsideBar `regime=UNCLASSIFIABLE`    | +8    | +0.166        | 0.409    |
| OpeningRange `volume=THIN`           | +9    | +0.146        | 0.439    |
| EmaCrossover `phase=CASH_OPEN`       | +10   | +0.033        | 0.678    |
| EmaCrossover `phase=MIDDAY`          | +10   | −0.032        | 0.793    |

**EmaCrossover's two `+10` phases are the bottom two rows.** They are the only cells whose sign count falls below 9 of 10, one of them holds the only negative median excess, and they are the only two where no configuration clears p on any statistic. §M28.14 called them the largest of the twelve and they carry nothing — which is what "a score is a consistency check and not a p-value" meant, now measured rather than asserted.

**It reads as §M27's gate 3 reproduced rather than contradicted.** That read put EmaCrossover's excess at about +0.03 and +0.05 and called it "essentially nothing"; here the two clock strata give +0.033 and −0.032. Its held-out survival is the ATR bracket, and restricting *when* it trades does not move which half earns.

## Four cells clear p = 0.05 on both roots, and OpeningRange's midday cell is no longer the only one

§M27's gate 3 ended with "no null test in the campaign reaches p < 0.05 on profit factor" and §M28.14 broke that with one cell on both roots. Four of these ten join it:

- **InsideBarTrailing `phase=MIDDAY`** — 5 and 4 of 10, at profit factors of 1.288–1.685 against a null that is itself above 1.0, and the highest net-to-drawdown in the table at 5.170.
- **OpeningRange `regime=UNCLASSIFIABLE`** — 9 and 4 of 10, and the smallest single p in the family at 0.005.
- **OpeningRange `volume=NORMAL`** — 6 and 10 of 10, and **the only cell of the ten whose median configuration clears p = 0.05 on both roots**, at 0.040 and 0.022.
- **OpeningRange `compression=EXPANDED`** — 6 and 2 of 10, on the largest OpeningRange sample here at 293–301 trades.

**InsideBarTrailing is the one that moves a standing reading.** §M27's gate 3 measured it "within 0.005 of its null on both roots" and concluded that "the trailing exit gives back exactly what the fixed bracket keeps". Confined to the midday lull at 5 minutes it runs +0.21 to +0.61 over its null on 10 of 10 configurations on both roots. That is not the trail becoming free — it is the same archetype measured over a fifth of the session — and it is the first time anything but OpeningRange has reached this level.

## What the family size allows, and the one correction that cannot be run

**Ten configurations of one cell are not ten tests.** They are overlapping shortlists over the same bars under the same context filter, so their p-values move together — which is why the count per cell sits beside the range and is never pooled into one number.

**A Bonferroni threshold over the twenty cells is α = 0.0025, and 400 draws cannot produce a p below 1/401 = 0.00249.** Nothing clears it, and that failure carries no information at all: the correction sits one resolution step inside the estimator's own floor, which is `randomentry`'s +1 correction doing what it exists to do. The smallest p observed is 0.005, which is two draws. **Raising `--iterations` is what would make a family-wise threshold testable**, and nothing here rests on a corrected one until it is.

So the guard is the arrangement rather than a corrected p. Chance alone would put about 10 of 200 rows below 0.05 and scatter them; the observed 46 sit in four cells, on both roots of each, with the other six contributing none between them. **That says where the significance is, not that any single cell is established** — and the cells were chosen after a consistency score had been looked at, which nothing here undoes.

## Four cells that are not results, for two different reasons

- **DeadCatBounce `htf=BELOW` has the largest excess in the family and the lowest null**, +0.50 median against a random entry running 0.578–0.712. Its profit factor still spans 0.834–1.258 on MNQ, so on that root it is a losing cell losing less than random — the shape [#288] predicted. On NQ it is profitable at 1.170–1.370 and returns 0.57 to 1.58 of its own drawdown. Neither root reaches p = 0.05 on 68 to 121 trades. This is §M7a inside a stratum rather than a new finding: **the entry is measurably better than random and the loss is in costs, hold time or bracket geometry**, and the standing decision that DeadCatBounce is the test fixture rather than a blocker is unchanged.
- **OpeningRange `regime=DIRECTIONAL` has the best profit factors in the table** — 1.409–1.781 at a net-to-drawdown of 2.021–4.301 — on **43 to 59 trades**, and 0 of 20 configurations below p = 0.05. It is §M28.1's verdict arriving on a different cut: what stops it is the sample rather than the idea.
- **InsideBar `regime=UNCLASSIFIABLE` lands where §M27's unfiltered InsideBar did**, at +0.207 and +0.154 median excess with median p at 0.32 and 0.43 against that read's +0.17 and +0.14 at p ≈ 0.08 and 0.16. The middle regime band buys almost nothing, and it is the largest sample of the ten at 432–634 trades — a flat result on a thick sample rather than a thin one.
- **OpeningRange `volume=THIN` does not agree across the roots.** MNQ is +0.206 to +0.305 at a net-to-drawdown of 1.766–2.629; NQ is +0.017 to +0.086 at a median p of 0.726, which is the null's own noise. §M28.14 flagged the volume rows as one raw cut per bar size rather than a fact about volume, and this is that warning landing.

## The two shares, and the fill assumption decides nothing in any cell that passed

`campaign_holdout.held_out` over the same selection ranking, holdout window, 5 minutes.

| cell                                 | `session_close_share` MNQ | NQ          | `ambiguous_share`, both roots |
| ------------------------------------ | ------------------------- | ----------- | ----------------------------- |
| EmaCrossover `phase=CASH_OPEN`       | 0.031–0.096               | 0.008–0.368 | up to 0.230                   |
| EmaCrossover `phase=MIDDAY`          | 0.087–0.626               | 0.042–0.520 | up to 0.145                   |
| InsideBarTrailing `phase=MIDDAY`     | 0.237–0.249               | 0.229–0.481 | 0.000                         |
| InsideBar `regime=UNCLASSIFIABLE`    | 0.090–0.103               | 0.083–0.102 | 0.000                         |
| DeadCatBounce `htf=BELOW`            | 0.031–0.056               | 0.021–0.042 | up to 0.083                   |
| OpeningRange `compression=EXPANDED`  | 0.547–0.679               | 0.546–0.676 | up to 0.006                   |
| OpeningRange `regime=UNCLASSIFIABLE` | 0.381–0.771               | 0.673–0.770 | 0.000                         |
| OpeningRange `volume=THIN`           | 0.646–0.755               | 0.606–0.711 | 0.000                         |
| OpeningRange `regime=DIRECTIONAL`    | 0.545–0.823               | 0.430–0.843 | 0.000                         |
| OpeningRange `volume=NORMAL`         | 0.550–0.574               | 0.546–0.673 | up to 0.006                   |

**The three cells whose ambiguity crosses `disambiguate.MIN_AMBIGUOUS_SHARE` are three of the six that clear nothing**, so no result above rests on the fill assumption: every cell reaching p = 0.05 sits at 0.006 or below, well outside the corner §M28.7 found.

**Every OpeningRange cell flattens 43% to 84% of its legs at the close**, which is §M28.12 and §M28.15 arriving on four more cuts of the same archetype — the profit centre is an account rule. InsideBarTrailing's midday cell is the one survivor outside that band on MNQ, at 0.24; its NQ twin reaches 0.48, so `tools/campaign_exits.py` is what would settle whether its excess survives the exclusion, and it has not been run here.

## What [#288] asked, answered

1. **The ten have been through gate 3.** Four clear p = 0.05 on both roots, two beat the null convincingly on too small a sample to establish it, two are positive and unconvincing, and two carry nothing.
2. **A consistency score is not evidence and does not even rank it.** Its correlation with the null excess is −0.132 and the two largest scores are the two worst cells.
3. **The multiple-comparisons load is stated rather than corrected**, because the correction that would answer it falls below the estimator's own floor at 400 draws.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_crossread.py`, `tools/campaign_null.py` and `tools/campaign_holdout.py` — not a standing property.

[#288]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/288
