---
id: M27
title: "M27 — the registry-wide campaign: every archetype, every axis"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, PullBackAndGo]
issues: [195, 196]
gates: [1, 2, 3, 4]
outcome: mixed
verdict: >-
  Bar size is the largest lever and the moving averages are nearly inert; four of six pass gate 1, three gate 2, one gate 3 — and what stops InsideBar is its bracket rather than its entry.
---

# M27 — the registry-wide campaign: every archetype, every axis ([#195], [#196])

The first sweep that treats the registry as one question rather than six. Every archetype across bar resolution, market regime, session phase, relative volume, trend label, higher-timeframe side and every moving-average axis it owns, on both roots, at the real commission for the root — then through the three tests a sweep table cannot pass on its own.

## In plain terms

Six trading strategies were each tried with every sensible combination of their settings, on five different bar sizes, in every market condition the codebase can label, on both the big and the small Nasdaq contract, with realistic commission and slippage. That is 760,960 runs.

Then the obvious trap was avoided. Trying 760,960 things and keeping the best one is how you find something that worked *by luck* — the more you try, the luckier the best one looks. So three further checks were run:

1. **Would you have picked it in advance?** Choose the best settings using only the first 60% of the history, then see how those same settings do on the last 40%, which the choice never saw.
2. **Is it the entry rule, or just the exit?** Re-run the same strategy with its entry replaced by a coin flip that trades the same number of times at the same times of day. If the coin flip does just as well, the entry rule is contributing nothing and the money is coming from the stop-and-target geometry.
3. **Could you survive trading it?** Compare the profit to the worst losing streak it went through to earn that profit.

**Five of the six fail one of those. One passes the first two and fails the third**, and the reason it fails the third is a single missing parameter rather than a broken idea.

The vocabulary, once:

- **Profit factor** — gross winnings divided by gross losses. Above 1.0 makes money, below 1.0 loses it. It says nothing about how bumpy the ride was.
- **Bar size / resolution** — how much time one candle covers. A 5-minute bar is five 1-minute bars added together.
- **Regime** — whether the market is trending (DIRECTIONAL), chopping sideways (CONSOLIDATING) or neither (UNCLASSIFIABLE), measured by the efficiency ratio (§M10.1).
- **Stratum** — one slice of the data, such as "only trending markets". Slices are taken one at a time and never crossed, so each answers its own question with a full sample behind it.
- **The null** — the coin-flip comparison in point 2, built by `nqbt/randomentry.py` (§M7a).

## What was run

760,960 combinations in about 98 minutes across four passes, on the spliced continuous series for both roots:

- Six archetypes, each with the axes it owns — moving-average periods **and kinds**, entry thresholds, stop modes, target ladders, trailing multipliers.
- Resolutions 1, 2, 5, 10 and 15 minutes.
- Twenty strata, **one dimension at a time and never crossed**: unfiltered, three regimes, seven session phases, three relative-volume states, three trend labels and three sides of a 60-minute average.
- Real costs, per root: **$1.50 round trip on MNQ and $4.50 on NQ**, both with one tick of slippage. Never one figure for both — the point value differs tenfold and the commission does not, so MNQ's number applied to NQ flatters it.

Every figure below is re-derivable from `results/campaign/<Archetype>.duckdb` with `tools/campaign_report.py` and `tools/campaign_holdout.py`; nothing here is a figure that moves on an ordinary pull request, but all of it is a measurement of one dated run rather than a standing property.

## The four gates, and what each removed

| gate                 | question                                                                                                            | survivors             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------- |
| 1 · the screen       | a majority of configurations profitable in at least one root × resolution cell                                      | 4 of 6                |
| 2 · held out         | best 20 chosen on the first 60%, measured on the last 40%, above 1.0 **and** above the holdout median of everything | 3 of 6                |
| 3 · the matched null | does the entry beat a random entry with the same count and time-of-session profile                                  | 1 of 6                |
| 4 · drawdown         | does the median configuration make more than its own worst peak-to-trough                                           | 1 cell, and only just |

**Gate 3 is the one that matters most and the one a sweep table never shows.** Gate 4 is where the survivor is currently stopped.

## Gate 1 — bar size is the largest lever, and the moving averages barely matter

The median configuration of every archetype loses money at 1 minute on both roots, and the median net P&L over the whole campaign is negative for all six. What separates them is where they peak:

- **The two ported reversal archetypes and EmaCrossover improve monotonically with bar size**, which is §M26's friction mechanism showing up outside ElasticBand for the first time: a fixed commission is a shrinking share of a larger bar's range.
- **The two inside-bar archetypes do not.** They peak at 5 minutes and fall away by 15. That is a real optimum rather than a cost effect, and it is the first non-monotone resolution result in the project.

Share of profit-factor variance a single axis explains (η², unfiltered stratum), largest first per archetype: resolution 0.76 on InsideBar, 0.56 on DeadCatBounce, 0.47 on PullBackAndGo, 0.34 on EmaCrossover; `trailing_stop_multiplier` 0.46 on InsideBarTrailing; resolution 0.14 and `stop_mode` 0.12 on ElasticBand.

**Every moving-average axis on every archetype falls below 0.04, and most below 0.01** — beaten by the bar size everywhere and by the root on four of the six. All four kinds were swept on DeadCatBounce, PullBackAndGo and EmaCrossover, EMA and HMA on both inside-bar archetypes. Choosing the kind is worth roughly a fiftieth of choosing the bar size. **η² is a property of the ranges swept**, so read it as "over ranges a person would actually try" rather than as a law — but the moving-average ranges here are wide and the answer is not close.

The practical consequence: **stop tuning periods.** The lever is the bar size and, after that, the exit geometry.

## Gate 2 — held out, and ElasticBand inverts

The benchmark is not zero. It is the holdout median of *every* configuration, which is what you get by not selecting at all.

- **InsideBar survives on both roots** — 19 of 20 shortlisted configurations still profitable out of sample, above the holdout median on both.
- **EmaCrossover survives on both roots**, 15 of 20.
- **InsideBarTrailing is marginal**, landing barely above 1.0.
- **DeadCatBounce and PullBackAndGo fail**, as the standing finding says they do.
- **ElasticBand fails hard, and the shape of the failure is the useful part.** Its shortlist averages a profit factor of 1.834 where it was chosen and 0.592 where it was not, with 1 of 20 configurations profitable on MNQ and 0 of 20 on NQ — *below* the holdout median of every configuration. It also owns the single highest profit factor in the whole campaign. **The archetype with the best number in a 760,960-row sweep is the one eliminated first.** That is the multiple-comparisons trap the standing rubric warns about, measured again on this project's own data and worth quoting whenever a sweep result is being read.

**The regime filter is where InsideBar separates.** The split pass was re-run once per regime: in the DIRECTIONAL stratum **every one of the 20 shortlisted configurations stays profitable out of sample on both roots**, and the holdout median across **every** configuration in that stratum is above 1.0 on both — so it is the whole parameter space rather than a shortlist. CONSOLIDATING is the mirror image at 2 of 20. The separation is sharpest at 10 minutes, where 99.7% of the 864 DIRECTIONAL configurations are profitable on the holdout against 6.1% of the CONSOLIDATING ones.

That is mechanically what an inside-bar *breakout* should do, which is the reason to believe it rather than the reason to be suspicious of it. **Read it with §M27.4 beside it**, which held out the other sixteen strata and found the same separation under two other names, on a much larger sample.

## Gate 3 — only one archetype's entry contributes anything

Each configuration was chosen on the selection window and placed against its matched null on the holdout, so the choice never sees the test data. Trade counts match the null closely in every row, which is what makes these comparisons clean — unlike §M26's, where two of three exit schemes were badly mismatched.

- **InsideBar: excess of about +0.17 and +0.14 profit factor over its null, at the 96th and 93rd percentile of the null distribution.** Positive on both roots, and *not* significant on either (p ≈ 0.08 and 0.16).
- **EmaCrossover: essentially nothing** — about +0.03 and +0.05, near the 60th percentile. Its null median profit factor is close to 1.0, meaning **a random entry inside its ATR bracket is roughly break-even after real costs at 15 minutes.** Its held-out survival is the geometry, not the crossover. It remains a useful known-negative control arm and is not a candidate.
- **InsideBarTrailing: within 0.005 of its null on both roots**, on either side of it. Read against InsideBar, which shares its entry, that says the trailing exit gives back exactly what the fixed bracket keeps.
- **ElasticBand: worse than random**, significantly so on win rate (p = 0.01) and mean R (p = 0.04), on both roots.

Per contract, which is thirty-eight samples rather than one: the InsideBar configuration beats its own null on 13 of 19 MNQ contracts and 12 of 19 NQ ones. Split honestly into the contracts the selection window covered and the ones it did not, that is **16 of 22 in sample and 9 of 16 out of sample**, with the mean excess staying positive on both roots and roughly halving.

**Those signs were counted on profit-factor excess, and the tool no longer reports it that way** — § "Reading the per-contract tally" below. A re-run reports a different excess column, and may count different signs, because the two estimators separate a contract's winners from its losers by size rather than only by number.

**The honest reading is "there is probably something here", not "this is established."** No null test in the campaign reaches p < 0.05 on profit factor. What InsideBar has is a consistent sign across two roots, thirty-eight contracts and a held-out window — which is more than anything else in this project has produced, and less than proof.

## Gate 4 — what stops it is the bracket, not the entry

InsideBar's profit factor comes from a deliberately lopsided bracket: a stop 5–20× ATR beyond the signal bar against a target of a bare 1× ATR from the fill. Across the holdout window that produces an **85–90% win rate with an average loss three to five and a half times the average win**, and a maximum drawdown that swallows the profit — unfiltered at 5 minutes, the median configuration ends the window with less than a third of its own worst peak-to-trough in profit.

Only **one cell of InsideBar's holdout** has a majority of configurations finishing with more profit than their own drawdown: DIRECTIONAL at 10 minutes, at 60% of them, and even there the median ratio is about 0.9. Net-to-drawdown was measured on InsideBar because it is the only archetype that reached this gate; the others fail an earlier one.

**A profit factor above 1.0 built from an 87% win rate and a 5:1 loss-to-win size is not an edge that survives a bad quarter.** Reading profit factor without the drawdown beside it is how this cell would have been mistaken for a result.

**And the reward half of that geometry was never swept, because at the time it did not exist.** `InsideBarParams` carried an `atr_multiplier` for the stop and **no multiplier at all for the target** — the 1× ATR target was hardcoded, following `InsideBar.cs`, which hardcoded it too. So the campaign moved the stop across 5×, 10× and 20× ATR and could not move the target by a tick, and half of what produces the asymmetry was structurally outside the grid. [#197] added `tp_multiplier`, defaulting to the 1× the campaign ran at so nothing above moves, and §M27.3 is the re-sweep that crosses it against the stop. **It found the target to be the largest axis on the holdout and the selection window to point the other way**, so Gate 4 is still failed and the diagnosis in this section is now the narrower one recorded there.

## What the campaign could not test

- **Time of day and relative volume were swept as entry filters and never reported.** Seven phases and three volume states went into the sweep and one pooled row per stratum came out; no time-of-day or volume finding reached this section at all. That is not the same defect as the bullet below, which is about the *split* — these cells had full-window numbers nobody read. §M27.7 and §M27.8 are the read, and both turned up something the report as it stood could not have shown: a stratum that is empty by construction, and a stratification whose ranking is decided by where it cut.
- **Sixteen of the twenty strata were never held out.** Session phase, relative volume, trend label and higher-timeframe side had full-window numbers only. [#199] has since run them through the split — §M27.4, which is where those cells' numbers now live.
- **The DIRECTIONAL cell is too thin per contract**, leaving about 30 trades per front-month contract at 5 minutes, so the per-contract null test cannot run on the strongest cell in the campaign. [#200] carries it, and **not** by loosening the threshold to restore the sample: the cut is uncalibrated rather than merely tight (§M10.1), and choosing it by the trade count it leaves would pick the stratum's definition from the statistic the stratum is about to be tested on. §M27.5 is where it landed — the threshold restated as a quantile of the ratio's own distribution, and the sample restored at 5 minutes and not at 15. The infinite profit factors seen alongside were a separate defect ([#218]), fixed in § "Reading the per-contract tally".
- **The held-out split is a single time cut** at 60% of the bars, so it tests one regime transition rather than many. The two roots track the same index over the same dates, so the thirty-eight per-contract samples are not thirty-eight independent ones.
- **`max_hold_bars` means a different amount of time at each resolution**, exactly as a moving-average period does. Nothing scales it, and no result here rests on it.
- **Everything is Tier 1.** EmaCrossover and ElasticBand have no NinjaScript at all, which is why InsideBar surviving matters more than EmaCrossover surviving would have.
- **Neither `nqbt/walkforward.py` nor `nqbt/montecarlo.py` was run at all** ([#203]). The four gates are the screen, one time cut, the matched null and the drawdown check; a multi-fold walk-forward and a resampling of the trade sequence are two further questions and neither was asked. Walk-forward is a named promotion criterion — § "Decisions taken" — so the survivor has the random-entry arm and the per-contract read and not that one. §M27.6 is the wiring; the run is still owed.

## The tools, and why there are five databases

`tools/campaign_sweep.py` runs the sweep — `--strata core|context|regime|phase|volume|volume-forms|trend|htf|all` so a later pass appends the dimensions an earlier one skipped, and `--split` for the selection and holdout windows. `tools/campaign_report.py` produces the distribution tables and the η² figures, `tools/campaign_holdout.py` the held-out test, and `tools/campaign_null.py` and `tools/campaign_contracts.py` the matched null on the continuous holdout and per contract. `tools/campaign_shortlist.py` is the trade-log path: the sweep stores summary rows only, so a bootstrap, a permutation test or a time-of-day review gets its per-trade vector by re-running a shortlisted row with `keep_trades=True` and storing the log under the same `(sweep_id, combo_id)` the summary carries. `tools/campaign_walkforward.py` and `tools/campaign_montecarlo.py` are the fifth gate — §M27.6, and `tools/campaign_review.py` reads a shortlist's own trades by the clock — §M27.7.

**One DuckDB per archetype**, under `results/campaign/`. At the time, `results._append_or_create` wrote `combos` by name and silently dropped a column the table did not have, so six parameter classes could not share one table — appending an `InsideBarParams` row to a table created from `DeadCatParams` would have stored it with `error_margin`, `atr_length` and `atr_multiplier` thrown away and nothing would have said so. [#201] closed that: the table widens instead, so the split is now a convention rather than a constraint, and the campaign keeps it because its results are already there.

Two things the sweep machinery still cannot see, both already recorded in `.claude/rules/sweep-and-context.md` and both worked around here rather than fixed: ElasticBand's stop and target axes are inert outside their own mode, and `volume_rolling_bars` has two toggles where `dead_axes` knows one. The campaign avoids both by making a stop geometry a *variant* — its own base parameters and its own axes — rather than an axis inside one grid.

## Reading the per-contract tally

**A profit factor is unbounded above, so it cannot be averaged over contracts** ([#218]). A contract with no losing trade has a gross loss of zero and an infinite profit factor, and one such contract sent `tools/campaign_contracts.py`'s `mean_pf` and `mean_excess` to infinity for its whole root — silently, because an infinity in a table of ratios reads as an extreme contract rather than as a destroyed row. The excess column made it worse by construction: the non-finite draws were filtered out of the *null's* profit factor and never out of the observed one, so the two sides of the subtraction did not have the same domain.

**The tally is taken on `expectancy` instead**, which `stats.Summary` already carries. Mean P&L per trade is bounded by the largest win, defined when gross loss is zero, and sits in the same units as `net_pnl`, which the row already reports. `mean_r` is the other bounded candidate and was not chosen because it is zero rather than undefined on a log with no finite planned risk, which reads as "no edge" instead of "no measurement". Profit factor is still reported *per contract*, where an infinity is visible and belongs to one contract; nothing aggregates it.

**The verdict is the sign count, not the average** — `beats_null` and `profitable` over the contracts, which is what the module docstring already told the reader to do and what §M26 and Gate 3 above actually quote. The medians beside them describe the spread and can never carry it: no single contract moves a median of nineteen, however extreme it is.

**There is no minimum trade count**, and removing it is the same finding rather than a second one. `MIN_TRADES = 30` was doing statistical work nothing stated — the justification in §M14 is specifically that *a profit factor* from a handful of trades dominates the quantity being measured, which is true there and does not transfer to a bounded statistic under a sign count. Every contract that traded is counted, and `median_trades` and `fewest_trades` are reported beside the signs so that a verdict resting on thin contracts says so. The one cut left is `trades > 0`, which is not a threshold: there is no statistic to count.

[#195]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/195
[#196]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/196
[#197]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/197
[#199]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/199
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
[#201]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/201
[#203]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/203
[#218]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/218
