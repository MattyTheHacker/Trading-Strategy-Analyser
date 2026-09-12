---
id: M31
title: "M31 — the nine calibrated cells through the matched null, and the lookback a consistency score cannot see"
archetypes: [ElasticBand, OpeningRange]
issues: [298]
gates: [3]
outcome: mixed
verdict: >-
  Two cells clear p = 0.05 on both roots — OpeningRange's calibrated DIRECTIONAL at lookbacks of 20 and 10, the strongest gate-3 result the registry has produced — while the five lookbacks that all score +10 span a median p from 0.010 to 0.72, and ElasticBand's mean-reversion mirror carries nothing.
---

# M31 — the nine calibrated cells through the matched null, and the lookback a consistency score cannot see ([#298])

§M30 swept 267 fitted cells and scored every one against its unfiltered twin. **None had been through gate 3**, and §M28.16 had already measured what a score is worth: its rank correlation with the matched-null excess was −0.132. This is gate 3 over nine of them, and the family was written down in [#298] before the run rather than counted afterwards.

**Nine cells, both roots, 5-minute bars, ranked on the selection window by profit factor and tested on the holdout, 400 draws, top ten: 9 × 2 × 10 = 180 tests.** Nothing was added after the first run. OpeningRange's five run under `--draw levels`, because its trigger is a level and the over-bars draw is refused inside a stratum — §M28.2. Nothing was refused: all 180 measured.

## The regime cell's name now carries the cut it was fitted at

A robustness check needs two cell sizes in one database and `_per_lookback` named a fitted regime cell `regime=DIRECTIONAL@n=20` — the lookback but not the quantile pair — so a second pair would have landed two different cuts under one stratum name. It now names the pair as a volume form's cut has always named its tail size: **`regime=DIRECTIONAL@n=20 q=0.20/0.80`**.

The rows §M30 wrote carry the earlier bare `@n=20` and are the stated pair. The stated pair was re-run under the name that says so, and **all 19,200 rows reproduce exactly** — identical trades, profit factor, net P&L, maximum drawdown and `session_close_share`, paired on parameters rather than on `combo_id`, which is a position in a product and moves when the cell count does. `tools/campaign_crossread.py` scores the two names identically, so nothing below rests on the rename.

## The robustness check, run and read before the null

`(0.20, 0.80)` is a stated design decision — §M27.5, "the campaign's cell size is a decision, and it is a fifth at each end" — and §M30's "+10 at every lookback" is a statement about that one pair. [#298] asked for a second cell size **before** the null, so that the family could not grow afterwards. A tenth and a third at each end, `--strata directional --split --regime-quantiles`, both roots, 5 resolutions:

| lookback | q=0.10/0.90         | q=0.20/0.80          | q=0.33/0.67          |
| -------- | ------------------- | -------------------- | -------------------- |
| n=5      | +7 — PF 0.998, 124  | **+10** — 0.993, 203 | **+10** — 0.966, 268 |
| n=10     | +7 — 1.070, 103     | **+10** — 1.045, 173 | **+10** — 1.048, 234 |
| n=20     | **+10** — 1.235, 66 | **+10** — 1.101, 124 | +9 — 1.118, 195      |
| n=30     | **+10** — 1.267, 52 | **+10** — 1.078, 105 | **+10** — 1.077, 175 |
| n=50     | +9 — 1.210, 41      | **+10** — 1.073, 81  | **+10** — 1.059, 140 |

Score, then median held-out profit factor and median holdout trades.

**The invariance survives a wider cell and frays at a narrower one.** At a third each end the cell is +10 at four lookbacks of five; at a tenth it falls to +7 at the two shortest. The mechanism is in the third column of each pair: **a tenth at each end halves the sample** — 41 to 66 median holdout trades where the fifth gives 81 to 203 — and a cell that thin stops agreeing across ten `root × resolution` points whatever it is measuring. Its profit factors are the highest in the table for the same reason.

So the +10 is quotable as invariance across the fifth and the third, and not across every cell size. **The family was not changed by this**, which is the point of having run it first.

## The nine cells, ranked on selection and tested on holdout

| cell                                                 | root | draw   | trades  | profit factor | null        | excess          | beats null | p < 0.05     | net/drawdown  |
| ---------------------------------------------------- | ---- | ------ | ------- | ------------- | ----------- | --------------- | ---------- | ------------ | ------------- |
| OpeningRange `regime=DIRECTIONAL@n=5 q=0.20/0.80`    | MNQ  | levels | 194–203 | 1.061–1.212   | 0.923–0.933 | +0.134 – +0.283 | 10 of 10   | 0 of 10      | 0.240–0.989   |
| OpeningRange `regime=DIRECTIONAL@n=5 q=0.20/0.80`    | NQ   | levels | 185–194 | 1.144–1.213   | 0.938–0.955 | +0.201 – +0.266 | 10 of 10   | 0 of 10      | 0.672–1.160   |
| OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`   | MNQ  | levels | 173–178 | 1.065–1.224   | 0.798–0.842 | +0.265 – +0.387 | 10 of 10   | **9 of 10**  | 0.564–2.044   |
| OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`   | NQ   | levels | 168–172 | 1.150–1.315   | 0.827–0.864 | +0.313 – +0.454 | 10 of 10   | **8 of 10**  | 1.332–2.696   |
| OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`   | MNQ  | levels | 123–126 | 1.361–1.498   | 0.890–0.917 | +0.451 – +0.608 | 10 of 10   | **10 of 10** | 2.511–3.470   |
| OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`   | NQ   | levels | 116–120 | 1.443–1.541   | 0.886–0.931 | +0.521 – +0.610 | 10 of 10   | **10 of 10** | 2.925–3.747   |
| OpeningRange `regime=DIRECTIONAL@n=30 q=0.20/0.80`   | MNQ  | levels | 106–107 | 1.047–1.099   | 0.981–1.002 | +0.053 – +0.113 | 10 of 10   | 0 of 10      | 0.201–0.414   |
| OpeningRange `regime=DIRECTIONAL@n=30 q=0.20/0.80`   | NQ   | levels | 100–103 | 1.073–1.174   | 0.993–1.014 | +0.064 – +0.171 | 10 of 10   | 0 of 10      | 0.297–0.655   |
| OpeningRange `regime=DIRECTIONAL@n=50 q=0.20/0.80`   | MNQ  | levels | 70–71   | 1.110–1.344   | 0.881–1.063 | +0.058 – +0.420 | 10 of 10   | 0 of 10      | 0.374–2.156   |
| OpeningRange `regime=DIRECTIONAL@n=50 q=0.20/0.80`   | NQ   | levels | 70–80   | 0.872–0.964   | 0.871–1.005 | −0.103 – +0.088 | 5 of 10    | 0 of 10      | −0.621–−0.191 |
| ElasticBand `regime=UNCLASSIFIABLE@n=30`             | MNQ  | bars   | 41–287  | 0.718–0.929   | 0.872–0.957 | −0.186 – −0.014 | 0 of 10    | 0 of 10      | −0.798–−0.345 |
| ElasticBand `regime=UNCLASSIFIABLE@n=30`             | NQ   | bars   | 42–742  | 0.347–0.903   | 0.889–0.992 | −0.542 – −0.058 | 0 of 10    | 0 of 10      | −0.988–−0.306 |
| ElasticBand `regime=UNCLASSIFIABLE@n=50`             | MNQ  | bars   | 50–979  | 0.771–1.027   | 0.845–0.966 | −0.082 – +0.068 | 2 of 10    | 0 of 10      | −0.693–0.317  |
| ElasticBand `regime=UNCLASSIFIABLE@n=50`             | NQ   | bars   | 53–109  | 0.646–1.288   | 0.786–1.008 | −0.335 – +0.361 | 4 of 10    | 0 of 10      | −0.765–0.479  |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.20/0.80` | MNQ  | bars   | 75–203  | 1.180–1.876   | 0.798–0.967 | +0.247 – +1.078 | 10 of 10   | **3 of 10**  | 1.179–4.165   |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.20/0.80` | NQ   | bars   | 59–298  | 0.913–1.387   | 0.795–0.976 | +0.008 – +0.449 | 10 of 10   | 0 of 10      | −0.248–1.927  |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.33/0.67` | MNQ  | bars   | 116–337 | 0.959–1.177   | 0.897–0.975 | +0.051 – +0.221 | 10 of 10   | 0 of 10      | −0.299–1.191  |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.33/0.67` | NQ   | bars   | 35–90   | 0.634–0.834   | 0.783–0.974 | −0.292 – +0.036 | 2 of 10    | 0 of 10      | −1.028–−0.240 |

**133 of the 180 configurations beat their own null and 40 clear p = 0.05.** The 40 sit in three of the eighteen root × cell rows.

## Two cells clear p = 0.05 on both roots, and only the lookback separates them from the three that do not

- **OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`** — 10 and 10 of 10, at a held-out profit factor of 1.361–1.541 against a null of 0.886–0.931, a net-to-drawdown of 2.5 to 3.7, and the smallest p the estimator can produce on both roots. **It is the strongest gate-3 result in the registry**: no cell in §M28.16 cleared on every configuration of both roots, and the largest median excess there — DeadCatBounce `htf=BELOW` at +0.504 — cleared p on none of its twenty, against this cell's +0.52 on MNQ and +0.57 on NQ on all twenty.
- **OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`** — 9 and 8 of 10, excess +0.27 to +0.45, net-to-drawdown up to 2.7.

**This is §M27.5's claim arriving as a gate-3 result.** §M28.16 put the *raw* `regime=DIRECTIONAL` through the same test: the excesses were comparable at +0.24 to +0.68, and it cleared p = 0.05 on **0 of 20** configurations, on 43 to 59 trades. The fitted cut at a lookback of 20 is the same idea on 116 to 126 trades, and it clears on 20 of 20. Nothing about the entry changed — the raw pair was simply reporting a much thinner slice of the same regime, which is what §M30 measured as 20.9% label agreement at n=50 and what §M27.5 predicted from the arithmetic.

**ElasticBand's mirror does not hold.** §M30's reading was that `UNCLASSIFIABLE` at n=30 and n=50 is the mean-reversion counterpart of OpeningRange's `DIRECTIONAL`, both at +8, "because the mirror is the claim §M30 actually makes about the registry". Under the null **neither cell beats a random entry on either root** — 0, 0, 2 and 4 of 10 — and all four medians are negative. The volume cells are better and one-sided: `HEAVY@rolling_30_20 q=0.20/0.80` reaches +0.29 median excess and 3 of 10 on MNQ against 0 of 10 on NQ, and the third-tail cut is +0.21 on MNQ and −0.18 on NQ. **A cell that disagrees across the roots is the shape §M28.16 flagged for `volume=THIN`**, arriving again.

## The score is constant across five cells whose null result is not

Every OpeningRange cell here scores **+10** — §M30's invariance — and their median p runs from **0.010 to 0.72**:

| cell                                                 | score | median excess | median p |
| ---------------------------------------------------- | ----- | ------------- | -------- |
| OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`   | +10   | +0.556        | 0.010    |
| OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`   | +10   | +0.337        | 0.032    |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.20/0.80` | +10   | +0.280        | 0.197    |
| OpeningRange `regime=DIRECTIONAL@n=5 q=0.20/0.80`    | +10   | +0.228        | 0.170    |
| OpeningRange `regime=DIRECTIONAL@n=30 q=0.20/0.80`   | +10   | +0.087        | 0.621    |
| OpeningRange `regime=DIRECTIONAL@n=50 q=0.20/0.80`   | +10   | +0.061        | 0.721    |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.33/0.67` | +10   | +0.043        | 0.509    |
| ElasticBand `regime=UNCLASSIFIABLE@n=50`             | +8    | −0.046        | 0.713    |
| ElasticBand `regime=UNCLASSIFIABLE@n=30`             | +8    | −0.143        | 0.571    |

The rank correlation across the nine is +0.725 against excess, and **it is an artefact of two score values**: the two `+8` cells happen to be the two worst, and every other cell is tied at +10. Read the seven tied rows on their own and the score explains nothing — a median excess from +0.04 to +0.56 and a median p from 0.010 to 0.72, all at the same score.

**That is §M28.16's finding with the score held fixed rather than varied.** There it was measured as a correlation of −0.132 over three score values; here five cells of one archetype agree on every one of ten `root × resolution` points, five times over, and two of them carry a result while three carry nothing. **The lookback is a dimension the consistency count cannot see**, because winning in both windows is a claim about direction and says nothing about size against a null.

## The two shares, and the profit centre is still the account rule

`campaign_holdout.held_out` over the same selection ranking and holdout window, 5 minutes.

| cell                                                 | `session_close_share` MNQ | NQ          | `ambiguous_share`, both roots |
| ---------------------------------------------------- | ------------------------- | ----------- | ----------------------------- |
| OpeningRange `regime=DIRECTIONAL@n=5 q=0.20/0.80`    | 0.631–0.658               | 0.623–0.647 | up to 0.004                   |
| OpeningRange `regime=DIRECTIONAL@n=10 q=0.20/0.80`   | 0.663–0.762               | 0.408–0.760 | up to 0.004                   |
| OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`   | 0.728–0.810               | 0.695–0.808 | 0.000                         |
| OpeningRange `regime=DIRECTIONAL@n=30 q=0.20/0.80`   | 0.691–0.769               | 0.694–0.785 | 0.000                         |
| OpeningRange `regime=DIRECTIONAL@n=50 q=0.20/0.80`   | 0.486–0.600               | 0.087–0.221 | 0.000                         |
| ElasticBand `regime=UNCLASSIFIABLE@n=30`             | 0.047–0.138               | 0.019–0.167 | up to 0.024                   |
| ElasticBand `regime=UNCLASSIFIABLE@n=50`             | 0.041–0.151               | 0.037–0.208 | up to 0.019                   |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.20/0.80` | 0.017–0.173               | 0.008–0.059 | up to 0.003                   |
| ElasticBand `volume=HEAVY@rolling_30_20 q=0.33/0.67` | 0.031–0.284               | 0.006–0.057 | 0.000                         |

**No cell here is anywhere near `disambiguate.MIN_AMBIGUOUS_SHARE`**, so the fill assumption decides nothing in any of them — unlike §M28.16, where three cells crossed it.

**The cell that passed flattens 70% to 81% of its legs at the session close**, high within the 38–84% §M28.16 reported across four cuts and with the highest floor of any of them. §M28.12 and §M28.15 are what that means: the profit centre is an account rule rather than the breakout, and excluding those legs has never left an OpeningRange cell profitable. **`tools/campaign_exits.py` has not been run here**, so that is an expectation carried over rather than a measurement of this cell.

## What [#298] asked, answered

1. **The nine have been through gate 3, as a family of 180 fixed before the run.** Two cells clear p = 0.05 on both roots, one clears on one root, and six carry nothing.
2. **The robustness check was run first and the +10 survives a wider cell size and not a narrower one**, because a tenth at each end halves the sample.
3. **A score still does not order the null result**, and this measures it in the harder direction: five cells at an identical +10 span a median p from 0.010 to 0.72.

## What this does not settle

- **The family was stated before the null and the cells were still chosen from a table of scores.** [#298] picked nine of §M30's 267 on invariance and on being the mean-reversion mirror. What is guarded is the *test* — nothing was added, dropped or re-cut after the first run — and not the *selection*: 267 cells were looked at before these nine were named, and no correction here carries that.
- **A family-wise threshold is still untestable at 400 draws.** Bonferroni over eighteen root × cell rows is α = 0.0028 and the estimator's floor is 2/401 = 0.005, which is exactly what `regime=DIRECTIONAL@n=20` reaches on both roots. It cannot go lower without more iterations, so "clears a corrected threshold" remains a claim nothing here can make — §M28.16 says the same about its own.
- **Ten configurations of one cell are not ten tests.** They are overlapping shortlists over the same bars under one context filter, so the count per cell sits beside the range and is never pooled.
- **Two of the forty shortlisted ElasticBand rows are not the grid §M30 scored.** `campaign_null` shortlists the stratum as stored and both `volume=HEAVY@rolling_30_20` cells also hold §M26.9's break-volume arm; one such row reaches the top ten on MNQ in each of the two cells. The other 38 are the campaign's target ladder, which is what §M30's crossread paired. Neither cell's verdict turns on those two rows.
- **Gate 4 has not been run on the cell that passed.** No walk-forward, no Monte Carlo, no prop-account replay and no exit-exclusion read — §M28.15 is what that would look like, and it is the read that turned the midday cell from a gate-3 result into a qualified recommendation.
- **Nothing is re-ranked and no archetype is revived.** ElasticBand's regime mirror failing is a result about two cells, not about the archetype; `docs/roadmap.md` § "Parked is not abandoned".

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_sweep.py`, `tools/campaign_crossread.py`, `tools/campaign_null.py` and `tools/campaign_holdout.py` — not a standing property.

[#298]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/298
