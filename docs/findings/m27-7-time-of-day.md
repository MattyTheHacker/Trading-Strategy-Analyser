---
id: M27.7
title: "M27.7 — time of day: swept, never read, and the artefact is in the wrong phase"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [205]
gates: [3]
outcome: mixed
verdict: >-
  Against a matched random entry the edge is in the quiet phases; the forced flat lands in AFTERNOON rather than CLOSE, and InsideBar's CLOSE stratum is empty by construction.
---

# M27.7 — time of day: swept, never read, and the artefact is in the wrong phase ([#205])

Seven session phases went into the §M27 campaign as an entry filter. **One pooled row per phase came out, and no time-of-day finding reached §M27 at all** — the numbers have been in `results/campaign/*.duckdb` since, and nobody had looked. What follows is that read, plus the two mechanisms it turned up, both of which would have been invisible in the report as it stood.

## What could not be read, and what now produces it

`tools/campaign_report.py` stopped at `profile(frame, ["stratum"])`: one row per stratum, pooled over root, resolution and variant, and **nothing else in the report was phase-aware** — the η² table and the variant table both read the `unfiltered` stratum alone. It now reads every dimension the stored strata hold, **one dimension at a time and cut by resolution rather than pooled over it**, because bar size is the largest lever in the campaign and a figure taken across resolutions reports that instead of the dimension. `dimension_of` reads the dimension off the stratum name, so a database gains its tables by having the rows rather than by anyone adding a case.

`session_close_share` and `ambiguous_share` are now columns of **every** table rather than an option, for the reason `CONTRIBUTING.md` § "Statistics and results" already gives: an optional column that a coarse-resolution or late-session result is read wrong without is a column nobody adds.

The other half was never touched at all. Filtering entries to a phase and re-running the grid answers *does this work if it only trades then*; `nqbt/review.py` answers *when did these trades actually happen, and what was true when they did*, and **no tool in `tools/` called `review`, `annotate` or `guard`**. `tools/campaign_review.py` is that call, over the logs [#215] made storable: `review.time_of_day` in session order with both forms of volume beside it, and `guard.guard` over the clock and the three volume labels as one family.

## InsideBar's `CLOSE` stratum is empty by construction, and the campaign could not say so

**4,320 rows per window, every one of them zero trades**, at every resolution and on both roots. Not thin — empty, and empty everywhere.

The cause is the archetype's own rule. `InsideBarParams.no_entry_minutes_before_close` is 60, which is `InsideBar.cs`'s own hour, and `SessionPhase.CLOSE` is 16:00–17:00 ET against a 17:00 ET close. **The stratum and the guard are the same hour**, so the cell could never hold a trade. InsideBarTrailing is the control that proves it rather than a second guess: the same entry with `no_entry_minutes_before_close = 0`, and 3,456 viable `CLOSE` combinations.

Viable combinations — 30 trades or more, full window, both roots — per phase:

| strategy          | OVERNIGHT | LONDON | PRE_OPEN | CASH_OPEN | MIDDAY | AFTERNOON | CLOSE  |
| ----------------- | --------- | ------ | -------- | --------- | ------ | --------- | ------ |
| DeadCatBounce     | 2,871     | 2,784  | 2,550    | 1,608     | 2,676  | 2,265     | 1,530  |
| PullBackAndGo     | 1,917     | 1,840  | 1,767    | 1,249     | 1,833  | 1,712     | 979    |
| EmaCrossover      | 10,240    | 10,240 | 10,240   | 10,240    | 10,240 | 10,240    | 10,020 |
| InsideBar         | 4,320     | 4,320  | 4,320    | 4,320     | 4,320  | 4,320     | **0**  |
| InsideBarTrailing | 4,320     | 4,320  | 4,320    | 4,320     | 4,320  | 4,320     | 3,456  |
| ElasticBand       | 5,232     | 5,184  | 5,136    | 5,232     | 4,992  | 5,040     | 4,592  |
| OpeningRange      | **0**     | **0**  | **0**    | 1,920     | 1,920  | 1,920     | 1,920  |

**Nothing in the sweep is wrong here; the rows are correct.** What was wrong is that a report reading only viable rows cannot tell *structurally empty* from *below the trade floor*, and both leave the table the same way. OpeningRange's three zeros are the same shape from the other side and are equally invisible: a cash-anchored range cannot arm before 09:30, so three of the seven phases are unreachable by construction rather than unprofitable.

**The stratification is therefore not seven cells everywhere, and a phase count is not a sample size.** Read the viability table before reading any phase result.

## The forced flat is in AFTERNOON, not CLOSE

§M10.4 predicted that the last phase would look anomalous because it holds the forced flat, measured `session_close_share` at 0.0016 on `CLOSE` against 0.0001 overall at 1 minute, and said to expect it to matter at 15 and 30 minutes. **It was right that it grows and wrong about where it lands.** InsideBar, full window, median `session_close_share` by phase and resolution:

| phase     | 1m    | 2m    | 5m    | 10m   | 15m       |
| --------- | ----- | ----- | ----- | ----- | --------- |
| OVERNIGHT | 0.001 | 0.002 | 0.007 | 0.025 | 0.051     |
| LONDON    | 0.000 | 0.001 | 0.014 | 0.023 | 0.063     |
| PRE_OPEN  | 0.003 | 0.006 | 0.028 | 0.055 | 0.089     |
| CASH_OPEN | 0.038 | 0.105 | 0.146 | 0.227 | 0.240     |
| MIDDAY    | 0.043 | 0.093 | 0.177 | 0.298 | 0.355     |
| AFTERNOON | 0.128 | 0.187 | 0.278 | 0.404 | **0.449** |

**The stratification is by *entry* phase, and the clock closes the position that was entered earlier.** A trade taken in the afternoon on 15-minute bars is the one still open at 17:00; a trade taken in the `CLOSE` hour barely exists for this archetype and cannot exist at all for InsideBar. So the phase that carries the artefact is the one two hours *before* the flatten, and it gets worse with bar size exactly as §M10.4 expected the last phase to.

Pooled over 5, 10 and 15 minutes, the same column across the archetypes that do trade in `CLOSE`:

| phase     | DeadCatBounce | PullBackAndGo | EmaCrossover | InsideBarTrailing | ElasticBand | OpeningRange |
| --------- | ------------- | ------------- | ------------ | ----------------- | ----------- | ------------ |
| MIDDAY    | 0.000         | 0.000         | 0.208        | 0.429             | 0.160       | 0.357        |
| AFTERNOON | 0.000         | 0.005         | 0.419        | 0.566             | 0.523       | 0.607        |
| CLOSE     | 0.122         | 0.250         | 0.877        | 0.893             | 0.878       | 0.809        |

`CLOSE` is 0.88 for every archetype that holds a position for any length of time, which is §M10.4's prediction confirmed at the resolutions it could not reach. But **the contamination is a hold-time × bar-size property rather than a phase property**: DeadCatBounce and PullBackAndGo hold for minutes and read zero everywhere but `CLOSE`, while the three archetypes that hold longer are half clock in the afternoon. `FORCED_EXIT_PHASE` names the phase the flatten falls in and that is not the same thing as the phase whose results the flatten decides.

**The consequence for InsideBar is direct: the two phases with the best median profit factor at 5 and 10 minutes are the two most contaminated.** AFTERNOON medians 1.131 at 5 minutes and 1.097 at 10 with 28% and 40% of its legs closed by the clock; MIDDAY medians 1.169 and 1.024 with 18% and 30%. Neither is a claim about the hour until the exits are attributed, which is what the `session_close_share` column now sitting beside them exists to force.

## Against a matched random entry, the edge is in the quiet phases

`tools/campaign_null.py` already took `--stratum` and had been run for `unfiltered` and the three regimes only. Per phase, best configuration on the selection window, measured on the holdout against a matched random entry — 200 draws, both roots:

| phase     | root | bars | trades | PF    | null  | excess     | p         | expectancy p |
| --------- | ---- | ---- | ------ | ----- | ----- | ---------- | --------- | ------------ |
| OVERNIGHT | MNQ  | 15m  | 292    | 1.385 | 0.865 | **+0.520** | **0.030** | **0.010**    |
| OVERNIGHT | NQ   | 15m  | 259    | 1.116 | 0.889 | +0.227     | 0.239     | 0.219        |
| LONDON    | MNQ  | 10m  | 183    | 1.517 | 0.904 | **+0.613** | **0.050** | **0.030**    |
| LONDON    | NQ   | 10m  | 182    | 1.447 | 0.935 | **+0.512** | **0.040** | **0.040**    |
| PRE_OPEN  | MNQ  | 5m   | 281    | 0.907 | 0.842 | +0.065     | 0.796     | 0.786        |
| PRE_OPEN  | NQ   | 5m   | 239    | 0.919 | 0.971 | −0.052     | 0.925     | 0.925        |
| CASH_OPEN | MNQ  | 5m   | 87     | 1.062 | 1.112 | −0.050     | 0.915     | 0.945        |
| CASH_OPEN | NQ   | 5m   | 81     | 1.100 | 1.009 | +0.090     | 0.846     | 0.806        |
| MIDDAY    | MNQ  | 10m  | 129    | 0.892 | 0.970 | −0.078     | 0.726     | 0.736        |
| MIDDAY    | NQ   | 10m  | 127    | 0.905 | 0.978 | −0.073     | 0.697     | 0.697        |
| AFTERNOON | MNQ  | 15m  | 59     | 0.674 | 0.963 | −0.290     | 0.289     | 0.259        |
| AFTERNOON | NQ   | 5m   | 138    | 0.968 | 0.948 | +0.020     | 0.955     | 0.955        |

`CLOSE` has no row on either root: with no viable stored configuration there is nothing to rebuild, which is the empty stratum arriving in the null as an absence rather than as a zero.

**LONDON is the only phase whose entry beats a matched random entry on both roots**, and OVERNIGHT does it on one. Both are phases with essentially no forced-flat contamination — `session_close_share` of 0.014–0.063 in the table above. **Every phase in the second half of the session is at or below its null**, including the two whose median profit factor looked best.

Three things travel with that and none of them is optional. **Twelve cells were measured and the phase was chosen by looking**, so a nominal 0.04 is not a family-wise 0.04; at a Bonferroni threshold over twelve, nothing here clears. **Each row is its own configuration**, best-on-selection within that phase, so the table compares phases at different parameters and different bar sizes rather than one strategy across the session. And **`AFTERNOON` on MNQ rests on 59 trades**, which is below the floor everything else in the campaign is held to.

## Over the survivor's own trades, the clock separates and does not hold

The other question needs the log rather than the grid. `tools/campaign_review.py` over the top unfiltered configuration at 5 minutes, on its own selection window, 2,000 label shuffles, separation in expectancy:

| root | legs  | separation | best      | worst  | p     | family p |
| ---- | ----- | ---------- | --------- | ------ | ----- | -------- |
| MNQ  | 2,413 | 87.5       | cash_open | london | 0.112 | 0.125    |
| NQ   | 2,240 | 1,023.7    | cash_open | london | 0.059 | 0.065    |

**The clock does not separate this configuration's trades beyond what shuffling the labels produces**, on either root, and the holdout is worse than the null: the best in-sample phase, `cash_open`, is the **worst** out of sample on both roots, and the worst in-sample phase is not the worst out of sample either. §M27.8 has the same screen with the three volume labels beside it, which is where the two halves are read together.

**This does not contradict the per-phase null above**, and the difference is worth being explicit about because the two tables point opposite ways. The null asks whether the *entry* beats a random entry inside one phase, at that phase's own best parameters; the screen asks whether one configuration's realised P&L differs *between* phases. A strategy can beat a random entry everywhere it trades and still have no phase better than another.

## A simulated log does not always fit inside its own bars

The review could not run at all until this was understood, and it is a finding rather than a nuisance. `nqbt/annotate.py` checks every fill price against the bar it matched, because that is the one test that catches a back-adjusted series, and `price_tolerance` is documented as admitting a simulated run's slippage and nothing wider. On the shortlist above it refuses: **23 of 2,413 legs land outside their exit bar, every one of them a `target` exit, by up to 17.25 points against a one-tick slippage.** Entry fills are all within the tick.

The cause is a profit target that a bar gapped through. On the first of them the previous bar closes at 15,225.75, the target sits at 15,219.00 and the exit bar opens at 15,201.75 and never trades above it — and the simulation fills at the target price. `docs/nt8-fidelity.md` has the matching rule for the other side, "A stop fills at the open when the bar gaps through it", established against a real trade list; **there is no such rule recorded for a limit**, so whether NT8 fills a gapped-through target at the target or at the open is untested. [#244] carries it.

**All 23 fall before the continuous series' first roll**, which is what stops this being alarming. The spliced series begins on the earliest cached contract's *own* pre-roll bars — MNQ 03-22 from 2021-09-19 — because there is nothing older to splice, and a deferred contract barely trades. Every gap of that size is that thin leading span. Measured over the whole front-month series under the reconciled configurations of all four C#-backed archetypes, on both roots, the case is **17 instances across 11 contracts, and every one of them is a point or less**. It is real, rare and small wherever the data is a market rather than a coverage boundary.

That also says why the stored exports cannot settle it. Across all five NT8 trade lists on this machine there are **3,043 target exits whose entry price, exit time and exit reason all agree with nqbt's — and not one of them is a gapped-through target**, because each reconciliation window is a front-month period and the case needs the deferred bars NT8 will not serve for its own contract. Same shape as the gapped-*stop* rule surviving the first reconciliation: a window is evidence about the bars it contains and nothing else. [#244] names the export that would contain it.

Until it is settled `tools/campaign_review.py` takes `--price-tolerance`, defaulting to the run's own slippage and printing any widening. The numbers above were taken at 20 points, which admits every one of the 23 and is still two orders of magnitude below the offset a back-adjusted series would show — the guard survives the widening, which is the only reason it is acceptable. **The better fix is to start a review after the first roll rather than to widen anything**, and it is not taken here because §M27's windows are shares of the whole series and moving them would make this section's numbers incomparable with §M27.4's.

## What the clock does not settle

- **The per-phase null is not family-wise.** Twelve cells, the phase chosen after looking. `nqbt/guard.py` is the family-wise machinery and it works over a trade log rather than over a grid, so the two tables above answer at different levels and neither covers the other's.
- **`bar_of_session` is still unread.** Seven phases is the coarsest cut available, chosen so seven against five regimes stayed at 35 cells (§M10.4). The finer clock is on the dataset and stratifying by it is a multiple-comparisons decision rather than a free improvement.
- **The forced-exit map is one archetype's per resolution.** The cross-archetype table is pooled over 5, 10 and 15 minutes, so it shows that the effect is a hold-time property and not how it scales for each of them.
- **Nothing here re-runs a sweep.** Every number in this section comes out of the databases §M27 and §M27.4 already wrote; what changed is that they are now read.

[#205]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/205
[#215]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/215
[#244]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/244
