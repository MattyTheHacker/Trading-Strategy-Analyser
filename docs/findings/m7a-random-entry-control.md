---
id: M7a
title: "M7a — the random-entry control arm: done"
archetypes: [DeadCatBounce]
issues: [32]
gates: [3]
outcome: mixed
verdict: >-
  DeadCatBounce's entry rule is measurably better than random at p = 0.012 while still losing money, which makes the loss one of costs, hold time or bracket geometry rather than of the entry.
---

# ~~M7a~~ — the random-entry control arm: done ([#32])

`nqbt/randomentry.py`. This section is the methodology, the reasoning behind it and the first result; the module carries a pointer here rather than a copy ([#105]).

**A backtest reports numbers, not evidence.** "Profit factor 0.746" is only interpretable against what the *same bracket, the same costs and the same exits* would have produced with entries chosen at random, and until that arm exists three very different diagnoses look identical: *worse than random* (the rule carries real information and points the wrong way), *indistinguishable from random* (the rule contributes nothing, and further tuning is a search over noise), and *better than random but still unprofitable* (there is signal; the loss is in costs, hold time or bracket geometry). Permuting an existing trade sequence separates none of them, because it takes the entries as given.

**The design principle is hold everything fixed, randomize only what is under test.** The quantity under test is *when the strategy chooses to enter*, so the null holds the bars, the instrument, the costs, the bracket geometry, the ratchet, the force-flat rule, the direction, the number of entry signals and the time-of-session distribution, and randomizes only which trading day each signal lands on.

**Time-of-session matching is the load-bearing part, and it is exact rather than coarsened.** Intraday index futures have a pronounced volume and volatility seasonality, and a bracket built from fixed tick offsets has materially different hit probabilities in a volatile hour than a thin one. A null scattering entries uniformly across 23 hours would trade mostly in thin overnight bars and lose for reasons unrelated to entry quality — **it would flatter every strategy ever tested against it**. Minute-of-session is discrete and low cardinality against millions of bars, so exact matching is feasible and bucketing into session phases would leave real confounding inside each bucket. That also keeps M7a independent of M10.4 ([#43]), whose labels exist to stratify results rather than to condition a null.

**The day is randomized rather than matched, deliberately.** Choosing which days to be active on is part of what an entry rule does, so it is under test; matching on it too would reduce the question to intraday timing alone.

**The null runs the archetype's own `run` with a substituted signal.** `run_deadcat` and `run_pullbackandgo` gained a `signal=` override for this, and `Archetype` gained a `signal` field so the registry can hand over the real signal to match against. That is what makes the two arms share one `simulate_deadcat` call rather than two implementations that were reviewed and found to agree — the standing trap about forking the bracket applies to a control arm exactly as it does to an archetype.

**Many draws, not one.** A single random-entry backtest is the folk version of this idea and is not evidence. The output is a Monte Carlo randomization test in the same shape `spread_vs_resampling` already uses. Two differences from that test, both real: this one **may** report time-dependent statistics, because every draw is a genuine simulation over real bars rather than a relabelling; and its p-value carries the add-one correction, so a statistic no draw beat reports 1/(n+1) rather than claiming zero.

**The p-value is two-sided on purpose.** An entry rule reading *worse* than random is a finding — real information pointing the wrong way — and a one-sided test would report it as an unremarkable failure to beat the null.

**`DEFAULT_ITERATIONS` is 200, not `spread_vs_resampling`'s 1,000.** Each draw here is a full simulation over every bar rather than a regrouping of an existing trade list, so an iteration costs two orders of magnitude more. 200 gives a p-value resolution of 0.005, finer than the decision being made with it; raise it when a result lands near the threshold. The numpy-native summary path ([#33]) is what makes a larger default affordable at all.

**Drawing is without replacement within a minute, and the guarantee is structural.** The pool for a minute is *every* bar sharing it, and the real signals at that minute are a subset of that pool, so it can never be smaller than the number of draws. That is why there is no resample-on-collision loop to get subtly wrong.

**The pool is deliberately not narrowed to in-session bars.** The null must face the same bar universe the strategy faced, and narrowing one side and not the other would compare two different bar universes and break the subset guarantee above. Since [#160] the question is moot on both series — `ingest.load_contract` and `build_continuous` filter alike — but the rule is the reason it stays moot rather than something to reinstate.

**`SessionMinutePool` is hoisted out of the Monte Carlo loop because of a measurement.** Grouping means an argsort over the whole series, and rebuilding it per draw was **89% of an iteration** on 914,700 bars — 106 ms against the 13 ms simulation it exists to feed. Same reasoning that hoists `context.prepare` out of a sweep.

**A non-finite observed statistic raises rather than being compared.** "Infinite profit factor beats the null" is an artefact of a run with no losing trade, not a result.

## What the test still does not do

- **It does not correct for multiple comparisons.** Running it across a sweep and keeping the combinations that beat the null is the trap [#48] exists to guard, with an extra step. Test a combination chosen for a reason, not the best of two hundred.
- **A small p-value is not a tradeable edge.** It says the entry timing is unlikely to be noise; profitability after costs is a separate question the module reports but does not answer.
- **It assumes the signal count is worth matching.** A rule that fires four times is not rescued by a null that also fires four times; the trade floor still applies.

## The first result, which reframes DeadCatBounce

Costed MNQ from 2024 (914,700 bars, 1.24 commission, 1 tick slippage), 500 draws:

| statistic     | observed | null median | percentile | p     |
| ------------- | -------- | ----------- | ---------- | ----- |
| profit factor | 0.666    | 0.551       | 99.6       | 0.012 |
| expectancy    | −10.24   | −14.78      | 99.8       | 0.008 |
| win rate      | 32.2%    | 29.3%       | 99.8       | 0.008 |

**The entry rule is better than random and still loses money.** That is the third of the three diagnoses this milestone was built to separate — *there is signal; the loss is coming from costs, hold time or bracket geometry rather than from entry selection* — and it is a different conclusion from "unprofitable, therefore worthless", which is what every previous number supported. It does **not** make DeadCatBounce tradeable and does not change its role as the test fixture; it changes what the next question about it is.

Three caveats, recorded so the result is not over-read. It is **one pre-specified parameter combination on one root**, not a sweep, so no multiple-comparisons correction applies and none is implied. **The arms match on signals and diverge on fills** — 74.4% against 47.7%, because the `min(Low[0], Close[0] − 2 ticks)` trigger sits just under an inverted hammer and well below an average bar — so per-trade rates are the fair comparison and `net_pnl` is not; that is why the defaults are `RATE_STATISTICS` and why both trade counts sit on every row. And the rule being tested is *bar selection*, which carries bracket geometry with it, so "better than random" is a property of the whole rule rather than of directional timing alone.

On that last point the win-rate result is the more informative one: an R-multiple bracket scales stop and target together, so win rate is close to scale-invariant and a 3-point edge is not obviously explained by the strategy's bars simply being wider. **A null that also matched the risk distribution would isolate pure directional timing** and is the natural refinement — worth doing before anyone acts on this, not before it is believed.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#160]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/160
[#32]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/32
[#33]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/33
[#43]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/43
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
