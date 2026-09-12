---
id: M32
title: "M32 — the two volume windows swept, and why a window is a cell rather than an axis"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [299]
gates: [2]
outcome: mixed
verdict: >-
  Both windows move a consistency score as much as most dimensions the campaign compares, and 43 of the registry's 56 consistent volume cells sit at a rung nobody had run — but a new rung is consistent at about the same rate as the default, so the two defaults were unexamined rather than wrong, and only 6 of the 34 positive cells return a held-out profit factor above 1.0.
---

# M32 — the two volume windows swept, and why a window is a cell rather than an axis ([#299])

§M27.8 flagged `volume_baseline_sessions` and `volume_rolling_bars` as two axes nobody had moved. §M30 made it a specific problem: the consistent volume cells it found sat mostly on the rolling form, whose window was one of the two. [#299] asked for both to be swept, and for InsideBar's missing volume rows to be put back so the registry's matrix is complete.

**4,749,120 combinations in 453 minutes.** Both roots, the spliced continuous series, resolutions 1/2/5/10/15, at the root's own commission and one tick of slippage. `--strata volume-forms --volume-quantiles --split`, with the ladders named on the command line.

## The premise, measured

**Across the 6,585,392 combination rows stored in all seven databases, `volume_rolling_bars` is 30 in every one and `volume_baseline_sessions` is 20 in every one.** Every volume result this project has quoted — §M10.2, §M26.9, §M27.8, §M28.14, §M30 — is a result at one window pair.

## A window is a cell, not an axis

[#299] called both windows "genuine axes rather than cell dimensions". **They cannot be.** A fitted cut is taken from the relative-volume series' own distribution, and the window is part of that series: move it and the ratios move, so the threshold pair moves with it — exactly as it moves with a regime lookback. An axis crossed inside one cell would read a pair fitted for a different window, which is the confound `.claude/rules/sweep-and-context.md` already refuses for the lookback and for the tail.

The other half of [#299]'s note needed nothing doing. **`volume.describe_key` has always carried both windows** — `per_bar_20`, `rolling_30_20` — so a rung was already separable in the results table and no new naming was needed. The §M31 lesson was satisfied here before anyone swept the axis.

What the machinery did need was three refusals, one per way a rung can silently say nothing:

- **A ladder without `--volume-quantiles`.** A raw pair admits a different share of bars at each window, so the rungs would not be readable against each other.
- **A rolling ladder without `ROLLING` in `--volume-forms`.** `volume.key` drops the window from the two forms that do not read it, so every rung would collapse onto one series — the pass would look like a ladder while running one. That is the `dead_axes` blind spot, made loud.
- **A window the form is degenerate at**, reported by name rather than as a traceback.

`--volume-forms` exists for the second: without it a rolling ladder re-runs the other two forms once per rung, which both wastes time and duplicates stored rows.

## What was decided before the run

- **One window at a time, not crossed.** Crossing them would run nine `rolling × baseline` cells under `ROLLING` and collapse to three under each other form — an uneven grid whose cells are not comparable across forms.
- **Two rungs beside the stored one: a third of it and three times it.** Rolling 10 and 90 against the stored 30; baseline 10 and 40 against the stored 20. One rung either side is the fewest that can show a direction, and the stored rows supply the middle rung rather than being re-run into a duplicate — which is what `campaign_holdout.py` pairing the two windows one-to-one requires.
- **All three tail sizes stay**, for §M27.8's reason as §M30 restated it: the ranking inverts when the cut moves three percentage points.
- **All seven archetypes**, with InsideBar's 27 missing cells run first so the ladder is read against a complete matrix.

## The refactor moved nothing

**All eight volume scores §M30 published reproduce exactly** under the new code: ElasticBand `HEAVY@rolling_30_20` at +10 under both the fifth and the third tail, `HEAVY@session_to_date_20 q=0.10/0.90` at +10, `HEAVY@per_bar_20 q=0.10/0.90` at +9, EmaCrossover `NORMAL@rolling_30_20` at +9 and +8, OpeningRange `THIN@per_bar_20 q=0.20/0.80` at +9 and `NORMAL@per_bar_20 q=0.20/0.80` at +8.

## The rolling window re-labels like a form; the baseline does not

`tools/campaign_labels.py --dimension windows`, MNQ selection window. Every rung is fitted to its own distribution, so each labels the same share of bars and any disagreement is about *which* bars. The share two rungs agree on:

| bars | tail      | rolling 10 vs 30 | rolling 10 vs 90 | rolling 30 vs 90 |
| ---- | --------- | ---------------- | ---------------- | ---------------- |
| 5m   | 0.10/0.90 | 87.2%            | 81.0%            | 85.4%            |
| 5m   | 0.20/0.80 | 78.1%            | **68.5%**        | 76.5%            |
| 5m   | 0.33/0.67 | 71.8%            | 61.0%            | 70.0%            |
| 15m  | 0.10/0.90 | 85.7%            | 79.2%            | 83.4%            |
| 15m  | 0.20/0.80 | 76.7%            | **65.0%**        | 72.5%            |
| 15m  | 0.33/0.67 | 70.4%            | **58.2%**        | 67.2%            |

**68.5% at the fifth tail sits inside the 63.4% to 77.9% range §M30 measured between the three *forms*.** The rolling window re-cuts the labels as hard as the choice of form does — and unlike the form it was never a choice, because nothing ever moved it. NQ agrees 1.6 to 4.2 points less than MNQ at every cell, a median of 2.3, so this is a property of the index rather than of the root.

**It also sends bars to the opposite state, which the tail size never does.** §M30's structural finding about volume was that the labels are *nested*: "at none of the nine cuts does a raw `THIN` bar become a fitted `HEAVY` one, or the reverse". The rolling ladder crosses on **18 of 18 cuts**, up to 12.1% of one rung's `HEAVY` bars landing in another's `THIN` at the third tail. The baseline ladder is milder on both counts: within a form it agrees 68.8% to 93.5% and crosses to the opposite state on 28 of 54 cuts, never above 4.1%.

So four things re-cut the volume labels, in order of how much: **the form and the rolling window, then the baseline, then the tail size.** Only the last two had ever been examined, and the tail is where §M27.8 and §M30 spent 27 cells.

## Rolling: the consistency is at the short rung, not the stored one

Cells won in both windows minus cells lost in both, ten `root × resolution` cells per stratum — §M28.14's score, the currency §M30 reported. Sixty-three families of (archetype × state × tail), three rungs each:

| cell                       | q=0.10/0.90 |     |     | q=0.20/0.80 |     |     | q=0.33/0.67 |     |     |
| -------------------------- | ----------: | --: | --: | ----------: | --: | --: | ----------: | --: | --: |
|                            |          10 |  30 |  90 |          10 |  30 |  90 |          10 |  30 |  90 |
| DeadCatBounce `THIN`       |          −5 |  −3 |  −6 |          −4 |  −5 |  −6 |          −1 |  −7 |  −3 |
| ElasticBand `HEAVY`        |          +9 |  +7 |  +6 |          +9 | +10 |  +7 |     **+10** | +10 |  +8 |
| ElasticBand `NORMAL`       |      **−8** |  −4 |  −3 |      **−8** |  −6 |  −4 |      **−8** |  −5 |  −1 |
| ElasticBand `THIN`         |          −1 |  −1 |   0 |          −5 |  −5 |  −6 |          −8 |  −8 | −10 |
| EmaCrossover `NORMAL`      |     **+10** |  +6 |  +4 |          +7 |  +9 |  +3 |          +9 |  +8 |  +2 |
| InsideBar `NORMAL`         |          +5 |  +3 |  +3 |      **+8** |  +6 |  +5 |          +4 |  +3 |  +3 |
| InsideBarTrailing `NORMAL` |          +6 |  +5 |  +7 |          +7 |  +5 |  +4 |          +5 |  +5 |  +2 |
| OpeningRange `NORMAL`      |          +2 |  −3 |  −4 |          +6 |  +2 |  +2 |          +4 |  +3 |  −2 |
| PullBackAndGo `THIN`       |          −1 |  −2 |  −3 |          −3 |  −4 |  −7 |          −3 |  −5 |  −4 |

Three figures:

- **The score's span across the three rungs is a median of 3 and a maximum of 7.** An axis nobody moved moves a §M28.14 score by as much as most of the dimensions §M28.14 set out to compare.
- **The stored rung of 30 holds the most extreme score in only 18 of the 63 families.** Rung 10 holds it in 32 and rung 90 in 13.
- **Cells reaching ±8: ten at rung 10, five at the stored rung 30, two at rung 90.**

Six families reach ±8 at some rung and not at the stored one; three lose it at the long rung:

| cell                              | rung 10 | rung 30 | rung 90 | held-out PF at the bold rung | holdout trades |
| --------------------------------- | ------: | ------: | ------: | ---------------------------: | -------------: |
| EmaCrossover `NORMAL` q=0.10/0.90 | **+10** |      +6 |      +4 |                        0.988 |          1,912 |
| InsideBar `NORMAL` q=0.20/0.80    |  **+8** |      +6 |      +5 |                    **1.051** |          1,105 |
| ElasticBand `HEAVY` q=0.10/0.90   |  **+9** |      +7 |      +6 |                        1.013 |            528 |
| ElasticBand `NORMAL` q=0.10/0.90  |  **−8** |      −4 |      −3 |                        0.904 |          1,916 |
| ElasticBand `NORMAL` q=0.20/0.80  |  **−8** |      −6 |      −4 |                        0.894 |          1,568 |
| ElasticBand `NORMAL` q=0.33/0.67  |  **−8** |      −5 |      −1 |                        0.888 |          1,104 |
| EmaCrossover `NORMAL` q=0.20/0.80 |      +7 |  **+9** |      +3 |                        0.990 |          1,494 |
| EmaCrossover `NORMAL` q=0.33/0.67 |      +9 |  **+8** |      +2 |                        0.974 |            900 |
| ElasticBand `HEAVY` q=0.20/0.80   |      +9 | **+10** |      +7 |                        0.972 |            688 |

**The short rung is where the rolling form's consistency is, and the arithmetic says why.** A ten-bar sum of contracts is closer to a single bar's count than a ninety-bar sum is, and the per-bar form is the one §M30 found to be the outlier of the three. Shortening the rolling window walks it back towards the quantity every raw result was computed on. Every ElasticBand and EmaCrossover family above is more extreme at rung 10 than at rung 90 in the same direction, so this is dilution at the long rung rather than a sign change.

**InsideBar's row is the one worth naming.** At §M30's nine cuts its volume dimension is inert — the best cell is `NORMAL@rolling_30_20 q=0.20/0.80` at +6 and nothing reaches ±8. At a rolling window of 10 that same cell is **+8, with a held-out median profit factor of 1.051 over 1,105 holdout trades — the highest of any consistent volume cell in the registry.** The gap between "this archetype's volume dimension carries nothing" and "it carries the best-paying consistent cell of the seven" was one unquestioned default.

## Baseline: a smaller effect, in the other direction, and one stored rung is a spike

189 families of (archetype × state × tail × form), three rungs each:

- **Span a median of 3 and a maximum of 11** — a wider maximum than the rolling ladder, on a flatter distribution.
- **The rungs are near-even.** Rung 10 holds the most extreme score in 73 families, the stored rung 20 in 60, rung 40 in 56.
- **Cells reaching ±8: 13 at rung 10, 13 at the stored rung 20, 18 at rung 40** — the long rung carries the most, which is the opposite of the rolling ladder.

Fifteen families reach ±8 at a rung the stored window could not see. ElasticBand holds ten of them and they run both ways: `HEAVY@session_to_date_10` is **+10** at the fifth and third tails where the stored rung gives +3 and +5, while `NORMAL@per_bar_40` and `NORMAL@session_to_date_40` reach −8 and −9 where the stored rung gives −5 to −7. The other five are one each for InsideBar, InsideBarTrailing and PullBackAndGo, and two for OpeningRange.

Nine families lose their consistency when the baseline moves, and **one of them is a spike rather than a plateau**: OpeningRange `NORMAL@session_to_date q=0.33/0.67` scores **−9 at the stored rung of 20 and +2 and −2 at the rungs either side** — a consistent cost that exists at one window and nowhere near it. ElasticBand `NORMAL@session_to_date q=0.33/0.67` is the mirror, +1 at the stored rung and −9 at 40.

## What the two defaults actually were

**Unexamined, not wrong.** Of the 693 fitted volume cells now scored across the registry, 56 reach ±8. **Thirteen sit at the windows every stored row used and 43 sit at a rung this campaign added** — but mostly because there are four times as many of the latter. The *rate* is close: 13 of the 189 cells at the stored windows are consistent (6.9%) against 43 of 504 at a new rung (8.5%). So 30 and 20 were not a bad choice; they were a choice nobody had checked, and checking it roughly quadrupled the count of consistent volume cells without finding a rung that is reliably better.

Within the rolling ladder there *is* a direction — ten of its seventeen consistent cells are at rung 10 — and within the baseline ladder a weak one towards the long rung. Neither is strong enough to replace a default with.

## InsideBar's volume rows, and the matrix completed

§M27.8 ran InsideBar's 27 fitted volume cells and those rows are no longer in `results/campaign/InsideBar.duckdb`, so §M30's volume tables covered six archetypes. Re-run here — 233,280 combinations in 16.4 minutes — **no cell reaches ±8 at any of the nine cuts**: the range is `NORMAL@rolling_30_20 q=0.20/0.80` at +6 down to `HEAVY@rolling_30_20 q=0.20/0.80` at −4, against raw `THIN` +3, `NORMAL` +2 and `HEAVY` 0. Its `regime=UNCLASSIFIABLE` +8 is unchanged.

So at §M30's windows the registry reads **three archetypes of seven acquire a consistent volume cell on re-cutting and four acquire nothing**, with InsideBar in the second group. Moving the rolling window puts it in the first.

## What this does not settle

- **Beating your own unfiltered twin is still not making money.** Of the 34 positive consistent cells across the whole matrix, **six return a held-out median profit factor at or above 1.0**: InsideBar `NORMAL@rolling_10_20 q=0.20/0.80` at 1.051, OpeningRange `THIN@per_bar_20 q=0.20/0.80` at 1.036, EmaCrossover `NORMAL@rolling_10_20 q=0.33/0.67` at 1.025, InsideBarTrailing `NORMAL@session_to_date_40 q=0.10/0.90` at 1.021, ElasticBand `HEAVY@rolling_10_20 q=0.10/0.90` at 1.013 and `HEAVY@rolling_30_20 q=0.33/0.67` at 1.001. The other 28 lose less than unfiltered rather than winning — the trap §M30 and §M28.14 both record.
- **A score is a consistency check, not a p-value, and nothing here has been through gate 3.** §M28.16 measured the rank correlation between a §M28.14 score and its matched-null excess at −0.132. These cells were chosen after the scores were looked at, so the family has to be stated: 693 fitted volume cells across seven archetypes. **InsideBar `NORMAL@rolling_10_20 q=0.20/0.80` is the candidate worth stating first**, on its held-out profit factor rather than on its rank.
- **The rungs are stated rather than fitted**, a third of each default and three times it, chosen ahead of the sweep the way §M27.8 chose its tails. The rolling form's best rung of three is also its shortest, which is the shape `.claude/rules/sweep-and-context.md` calls a truncated axis rather than a swept one — `MIN_ROLLING_BARS` is 2, so rungs below 10 exist and were not run.
- **The two windows were not crossed.** The rolling ladder ran at baseline 20 and the baseline ladder at rolling 30, so nothing here tests whether a short rolling window and a short baseline interact.
- **Nothing is re-ranked, and no archetype is retired or revived.** The stored strata are unchanged; what is new is InsideBar's 27 missing cells and 72 window cells per archetype that did not exist.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_crossread.py` and `tools/campaign_labels.py` — not a standing property.

[#299]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/299
