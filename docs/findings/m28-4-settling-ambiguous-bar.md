---
id: M28.4
title: "M28.4 — settling the ambiguous bar instead of bounding it"
archetypes: [OpeningRange]
issues: [248]
gates: []
outcome: tooling
verdict: >-
  Minute bars settle 17% of ambiguous bars and all of them against the assumption, which bounds the retest's profit factor from above; it stays a diagnostic and never enters `nqbt/sim/`.
---

# M28.4 — settling the ambiguous bar instead of bounding it ([#248])

§M28.3 measures how wide the band is. It cannot say where inside it the truth sits, and on §M28.2's retest the band is wide enough that the difference decides whether the archetype has a result at all. **The minute bars inside an ambiguous bar can usually say**, and §M13 is what makes reading them exact rather than approximate: OHLC aggregation is associative, so a 5-minute bar *is* five 1-minute bars, already in the archive, with no tick data involved.

`nqbt/disambiguate.py` is that pass, and `tools/campaign_ambiguity.py` runs it as a third step above `MIN_AMBIGUOUS_SHARE`.

## It is a diagnostic, and the prime directive is why it stays one

**Nothing here reaches `nqbt/sim/`, and nothing may.** NT8 guesses on the same bars, so a simulation that resolved them truthfully would disagree with Tier 2 on exactly the bars where a disagreement cannot be attributed — the more-precise-than-NT8 error, in its purest form. What this does instead is score an assumption *already made*, on a result that already exists, which is the trade-review side's reasoning rather than the simulator's.

Three things keep it there. It runs **after** a shortlist rather than inside a sweep. It runs **only above `MIN_AMBIGUOUS_SHARE`**, because a result the assumption cannot have decided does not need the assumption scored. And the ranking statistic is still `AMBIGUITY_NEAREST_TO_OPEN`: a resolved profit factor is reported beside the ranked one and never in place of it.

## A resolved log is a row selection, not a recomputation

`AMBIGUITY_BEST_CASE` was added to `bracket.py` for this, beside the worst case that was already there. With all three policies run, the two ends of the band **are** the two outcomes an ambiguous bar is choosing between, so a bar the minute bars settle takes that trade's rows from the arm that resolved it that way. No price is recomputed anywhere in the diagnostic, which is what keeps the fill rules in the one place that owns them.

That works because of a property of `resolve_brackets` rather than of the diagnostic: **on an ambiguous bar the whole position closes, under either policy** — targets-first fills what it can and stops the remainder on the same bar. So the next bar starts flat in every arm, every downstream trade is identical, and the three logs are the same trades leg for leg. `tests/test_disambiguate.py` checks that rather than assuming it, and `resolved_log` refuses to build anything if it does not hold.

## Four refusals, each of which would otherwise be a confident wrong answer

- **The window is checked by rebuilding the bar.** §M13's associativity says the minutes inside a coarse bar must aggregate back to it exactly, so `rebuilds` uses that as a guard on the alignment rather than as an argument for it. A window off by one bar still looks like bars.
- **The stop is checked against the arm that always takes it.** The worst-case arm exits every open leg at the stop, so its fill *is* the live stop's fill; disagreeing with the log's `initial_stop` means the stop moved between entry and exit. A trailing archetype hits this on every leg, which is the intended outcome — refused with a reason beats resolved against the wrong level. Derived from the data rather than declared per archetype, so the next trailing archetype is caught too.
- **A minute holding both levels is the residue, not a verdict.** This is where `data/tick/` would be needed, and it is reported and counted rather than assumed a second time.
- **The minutes before the fill are not the trade's.** See below; this is the one that mattered.

## The correction that changed the answer, and why it is not an edge case

The first working version walked every minute of the ambiguous bar. That is right for a position held from the bar's open and wrong for one that opened inside it — and **every ambiguous leg in the retest shortlist exits on its own entry bar**, so it was wrong for all of them. The walk now starts at the minute holding the entry fill, and a level reached inside that same minute is reported unsettled, because it cannot be ordered against the fill.

That is not a detail bolted on. It is §M28.2's mechanism seen from the other side: a limit entry fills as price moves *away* from its target, so the favourable extreme that made the bar look ambiguous usually **predates the fill entirely**. The simulation counts it because it reads the whole bar; the minute bars show it was not available to the trade.

A second correction the same walk needed: the target it asks about is the one nearest the **fill**, not the one nearest the bar's open. Nearest-to-open is what `targets_reached_first` compares distances against, but the question here is which level price touches first once the position exists, and on a ladder that is the closest rung. Measuring from the open puts a further target in the walk and biases every verdict towards the stop — measured, and it moved 40 of 368 bars.

## The first result: the retest's profit factor is not attributable, and now it is bounded from above

Top 20 by held-out profit factor, `cash=5m entry=retest target=R`, MNQ, re-derivable from `results/campaign/OpeningRange.duckdb` and a measurement of one dated run:

- 368 ambiguous bars, **100% of them same-bar entries**.
- **304 (83%) are still ambiguous at one minute** — the residue that genuinely needs `data/tick/`, and the first time this project has sized it.
- **64 settle, and all 64 settle against the assumption.** Nearest-to-open guessed target-first on every one of them; the minute bars say stop-first on every one of them.
- Resolved profit factors fall by 0.17 to 1.15 — for example 4.82 to 3.68, and 4.03 to 2.87.

**The resolved figure is an upper bound rather than an estimate**, and the reason is in the numbers above: every bar that settled went against the trade, and the 83% that did not settle keep NT8's optimistic guess. If the residue resolves the way the settled bars did, the retest's real profit factor is materially below even the corrected number.

**An accuracy of zero on 64 bars is a finding about the heuristic, not about this archetype.** Nearest-to-open measures distance from the *bar's* open, and on a same-bar limit entry the bar's open is not where the trade started — so the heuristic is being asked a question it was never fitted to. §M22's seven-bar trade list that established the rule contains no same-bar limit entry, because no archetype had one until the retest.

## What the minute bars do not settle

It does not make nearest-to-open wrong *for NT8*: NT8 will still fill those bars its own way, so Tier 2 will re-validate the unattributable number rather than contradict it. This is a live-trading risk, not a tier-disagreement risk, and no amount of reconciliation touches it — which is exactly why the diagnostic had to exist outside the simulator.

It also does not touch the residue. 83% unsettled at one minute is the honest ceiling on what bar data can do here, and `data/tick/` is the only thing below it. That is now a sized question rather than an open one, and it is its own issue.

## The gate was not running on `bracket.py` changes, and that is a fourth way to disable it

Found while building this and fixed here. **numba's `cache=True` does not track cross-module dependencies**: a change to `bracket.py` leaves every archetype's compiled loop holding the *old* inlined fill rules. Adding `AMBIGUITY_BEST_CASE` and running the trade-log gate over stale caches reported no change, because the new policy was never compiled in — identical source, caches deleted, different trade log.

Every fill rule lives in `bracket.py`, so this disabled the gate precisely on the file it exists to protect. `tools/capture_trade_logs.py` now purges `*.nbi`/`*.nbc` before each capture. `.claude/rules/regression-gate.md` carries it as the fourth item.

[#248]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/248
