---
title: "The build spec's three loose ends, measured"
archetypes: [EmaCrossover]
issues: [74]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  None of the three features improves EmaCrossover; the trail costs in nineteen of twenty cells and the confluence count moves results without being edge.
---

# The build spec's three loose ends, measured ([#74])

The registry-wide campaign re-run with the three new axes in it: **2,190,720 combinations in 271 minutes across nine passes**, both roots, resolutions 1/2/5/10/15, real costs per root, on the raw spliced continuous series. Pass 1 is every stratum dimension over the whole window; pass 2 the held-out split unfiltered; pass 3 the new axes; passes 4-9 hold out one context dimension at a time.

**What had changed, stated first**, because § "Parked is not abandoned" requires it: **only EmaCrossover**. Three axes it did not have, and nothing else — no new condition, no new range, no new data, no cost change for any other archetype. So six of the seven were re-run as the **control**, not as a second opinion, and their agreement with §M27 is the thing worth reading about them rather than any number in isolation.

## Four predictions, written before the sweep finished, and all four right

That last clause is worth distrusting rather than celebrating. Three of the four followed from arithmetic or from a finding §M27 had already made, so they were cheap; a prediction that could not have failed is not evidence that the analysis is strong.

1. **The round-number rule is nearly inert, by construction.** It moves a stop only where the stop lands *exactly* on a multiple, and prices sit on a 0.25 tick grid — so a 5-point spacing is one tick in twenty and a 25-point spacing one in a hundred. **The number worth reading is the share of stops it moves, not its profit factor.**
2. **The trail costs profit factor.** §M27's gate 3 found EmaCrossover's held-out survival is its ATR bracket rather than its crossover, and that InsideBarTrailing "gives back exactly what the fixed bracket keeps". A ratcheting stop is the same intervention on the same half.
3. **The confluence count buys sample size rather than edge**, with `REQUIRE_ALL` sample-starved and the union diluted. The shape that would make it a finding is 2-of-3 beating both neighbours.
4. **The other six reproduce §M27 rather than adding to it**, and a *disagreement* would be a finding about reproducibility rather than about a strategy.

## The control reproduced §M27 to the third decimal, which is the most reassuring thing here

Largest axis on profit factor, unfiltered stratum, whole window (η²), against what §M27 recorded:

| archetype         | this run                            | §M27       |
| ----------------- | ----------------------------------- | ---------- |
| InsideBar         | resolution 0.757                    | 0.76       |
| DeadCatBounce     | resolution 0.541                    | 0.56       |
| PullBackAndGo     | resolution 0.465                    | 0.47       |
| EmaCrossover      | resolution 0.343                    | 0.34       |
| InsideBarTrailing | `trailing_stop_multiplier` 0.455    | 0.46       |
| ElasticBand       | resolution 0.136, `stop_mode` 0.122 | 0.14, 0.12 |

Every moving-average axis is again below 0.04 and most below 0.01. Gate 2 reproduces as well: InsideBar 19 of 20 on both roots, EmaCrossover 15 and 16 of 20, InsideBarTrailing marginal at 1.021 and 1.018, ElasticBand inverting again — a shortlist averaging 1.576 and 1.832 where it was chosen against 0.684 and 0.591 where it was not, 1 of 20 profitable on MNQ and 0 of 20 on NQ.

**OpeningRange enters the campaign's own gate 2 for the first time and posts the strongest result in it**: 20 of 20 shortlisted configurations profitable on the holdout on both roots, above the holdout median on both. That is consistent with §M28.1 having called it the widest-margin holdout in the project, now measured on the campaign grid rather than its own.

**One divergence, and it is a defect in how the gate is read rather than in the data.** DeadCatBounce comes back `passes = True` on MNQ where §M27 records it as failing. Its shortlist's *selection-window* profit factor is **0.940** — the best twenty configurations were losers where they were chosen — and they then cleared 1.0 on the holdout. **A shortlist drawn from a space containing nothing profitable can still clear a bar defined only on the test window.** Read `sel_top20_pf` beside `passes`, always; the standing finding that DeadCatBounce is unprofitable is unchanged.

## The trail costs, in nineteen of twenty cells, and its own tuning is inert

Paired cell by cell with `tools/campaign_paired.py`, holding every shared parameter equal and collapsing the trail's three axes to their median inside each cell:

- **Under the ATR stop, the median delta is negative in all ten root × resolution cells**, between −0.022 and −0.064 profit factor, with the treatment improving 0 to 25% of cells and an exact sign test at p < 0.001 in nine of the ten.
- **Under the swing stop, negative in eight of ten.** The two exceptions are both 15-minute, both +0.004, at p = 0.60 and p = 0.86 — coin flips, not the mechanism working somewhere.
- **It is not mistuned.** Inside the trailing arm, `trail_ma_period` explains η² of 0.0067 and 0.0025, `trail_ma_kind` 0.0008 and 0.0000, `trail_offset_ticks` 0.0004 and 0.0001 — every one below the moving-average axes §M27 already called nearly inert. **Trailing at all is the cost; where the average sits is not a lever.**

**This arm is also the clearest demonstration in the project of why a shortlist is the wrong instrument for an A/B.** The trailing variant's *best* configuration beats the control's best in several cells — 1.286 against 1.223 at MNQ 10 minutes — purely because it has 384 combinations against the control's 32. Read on the shortlist, the trail is an improvement. Read paired, it is a consistent cost. `tools/campaign_paired.py` exists because of exactly that gap.

## The round-number rule does precisely what it was specified to do, and that is all

**Measured directly against the tick arithmetic**, over the whole MNQ continuous series:

| spacing   | resolution | trades | stops moved |
| --------- | ---------- | ------ | ----------- |
| 5 points  | 5 min      | 15,145 | 4.88%       |
| 5 points  | 15 min     | 4,901  | 5.06%       |
| 25 points | 5 min      | 15,145 | 0.91%       |
| 25 points | 15 min     | 4,901  | 0.94%       |

Against a predicted 1-in-20 and 1-in-100 from the 0.25 tick grid alone. The rule fires exactly as often as arithmetic says it must, and **the paired delta is 0.000 to three decimals in all twenty cells**, with `round_number_points` and `round_number_offset_ticks` both at η² of 0.0000 to four.

**Several of its sign tests nonetheless reach p < 0.05, and that is the multiple-comparisons trap rather than an effect** — 22 of 32 cells improved at MNQ 1 minute (p = 0.05) against 8 of 32 at MNQ 15 minutes (p = 0.007). Forty sign tests were run across the four paired tables; two or three at p < 0.05 are the expected output of noise, and the direction disagrees across resolutions *on the same root*, which a real effect would not do. **A rule that moves one stop in twenty by two ticks cannot move an aggregate, and the significance here is the test's, not the rule's.**

## The confluence count is the one that moves results, and it is still not edge

`confluence_required` is **the largest axis inside its own variant** — η² of 0.0494 under the ATR stop and 0.0180 under the swing stop, larger than every moving-average axis §M27 measured on any archetype. It is a real lever, which the other two are not.

What it levers is the sample. Medians over 640 stored rows per count, three side-neutral filters (DIRECTIONAL, HEAVY, EXPANDED):

| count                           | trades | profit factor | rows under the 30-trade floor |
| ------------------------------- | ------ | ------------- | ----------------------------- |
| 1 of 3 (the union)              | 1,204  | 0.987         | 0 of 640                      |
| 2 of 3                          | 357    | 1.024         | 0 of 640                      |
| `REQUIRE_ALL` (the conjunction) | 57     | 1.063         | 152 of 640                    |

Strictly ordered, exactly as predicted. **2-of-3 keeps 96% of the conjunction's median profit factor at 6.3× the trades and loses no cell to the floor**, which is the honest case for having the axis at all. On the holdout it beats both neighbours at 2 and 5 minutes and beats the union at four resolutions of five.

**And then it fails the matched null, at every count, on both roots.** Ranked on the selection window and tested on the holdout over 200 draws, the profit-factor excess over a matched random entry is at or below zero in seventeen of eighteen configurations; the single positive one is **+0.001 at p = 0.995**. The conjunction's high profit factor is a 23-to-25-trade artefact on the holdout — below the floor the campaign applies everywhere else. **The count dials sample size against dilution, and neither end of the dial contains an edge**, which is what §M27's gate 3 already said about this archetype's entry and what no re-weighting of the same entry could have changed.

## Where this leaves the three features

All three are built, tested, sweepable and reconciled against nothing, because EmaCrossover has no NinjaScript. **None of them improves EmaCrossover, and that is the result.** Per § "Parked is not abandoned" it parks a configuration space rather than retiring a feature, and each one has an obvious un-run test that this campaign is not:

- **The trail has never been given an archetype whose edge is a trend.** It was measured on the one archetype §M27 had already shown to be carried by its bracket, which is the least favourable place for it. A trailing stop is a trend-following device.
- **The round-number rule has never been run per contract.** A splice is raw here, but a level's meaning is local to a contract, and [#31]'s per-contract windows are the series where "20,000" is a number a person watched. The share it moves would not change; whether the trades it moves are different ones might.
- **The confluence count has never been given three filters that are individually informative.** DIRECTIONAL, HEAVY and EXPANDED were chosen for side-neutrality, not because any of them separates EmaCrossover — and §M27.4 found the separation for this archetype in none of them.

**What is owed before any of this is quoted**: the per-contract dispersion arm for all three, and a second archetype for the trail. Every figure above is re-derivable from `results/campaign/<Archetype>.duckdb` with `tools/campaign_report.py`, `tools/campaign_holdout.py`, `tools/campaign_paired.py` and `tools/campaign_null.py`.

[#31]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/31
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
