---
id: M28.12
title: "M28.12 — the bracket decomposition, read across the registry"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [264]
gates: []
outcome: mixed
verdict: >-
  One archetype in seven has a bracket that pays for itself held out; InsideBar's stop is nearly inert and its forced flat hands back about 90% of what the bracket earns.
---

# M28.12 — the bracket decomposition, read across the registry ([#264])

[#264] added the column §M28.9 said would have caught the opening range's bracket several campaigns earlier: leg count, net P&L and median bars held per `exit_reason`, beside the two shares, on the one table `campaign_report` ranks. This is the first reading of it across every archetype, and **it does not say the same thing twice** — the two archetypes at the front of the registry are exact mirror images of each other.

**No new sweep.** Every figure is a decomposition of stored rows plus the re-runs `tools/campaign_shortlist.py` does to keep a log, and each of those is refused by `campaign_shortlist.verify` unless it reproduces the stored trade count and net P&L.

**The protocol is `campaign_holdout`'s and not a fresh selection.** Twenty configurations per archetype per root, ranked on the **selection** window's profit factor, unfiltered stratum, paired into the **held-out** window on `JOIN_KEYS`, at the root's real commission and one tick of slippage. A shortlist ranked on the window it is then read from measures the selection and not the strategy: taken that way DeadCatBounce's bracket reads as profitable on both roots, and under the protocol above it is negative on 8 of 11 and 11 of 17.

**It is a decomposition and not a counterfactual**, exactly as §M28.9 states it. A leg the clock closed is a leg the stop did not take, so no row below supports "remove this half and keep the other". What they support is the weaker and sufficient statement about which half of a configuration's geometry pays for itself.

## One archetype in seven has a bracket that pays

Median across the paired twenty, MNQ / NQ. `bracket` is `stop` plus `target`; `flatten` is `session_close`:

| archetype         | paired  | bracket net               | flatten net           | bracket negative on  |
| ----------------- | ------- | ------------------------- | --------------------- | -------------------- |
| **InsideBar**     | 20 / 20 | **+172,538 / +1,809,532** | −158,386 / −1,626,819 | **0 of 20, 0 of 20** |
| InsideBarTrailing | 20 / 20 | −56,774 / −51,719         | +99,284 / +807,284    | 15 of 20, 12 of 20   |
| EmaCrossover      | 10 / 8  | −17,155 / −203,629        | +15,118 / +141,111    | 8 of 10, 8 of 8      |
| ElasticBand       | 20 / 20 | −15,320 / −133,167        | +6,480 / +43,544      | 20 of 20, 20 of 20   |
| OpeningRange      | 20 / 20 | −65,519 / −634,403        | +79,927 / +804,908    | 20 of 20, 20 of 20   |
| DeadCatBounce     | 11 / 17 | −1,310 / −18,047          | +148 / +422           | 8 of 11, 11 of 17    |
| PullBackAndGo     | 20 / 20 | −1,176 / −7,003           | +27 / −193            | 15 of 20, 15 of 20   |

**InsideBar is the only archetype whose bracket pays for itself held out**, and it does so on every one of the forty shortlisted configurations. Everything else is carried by the forced flat or is not carried at all.

Two readings that need keeping apart. **DeadCatBounce and PullBackAndGo never reach the flatten**: their close share is 0.0 and their exits sit one to four bars after the fill, so the flatten is not a factor in either result and the loss is entirely in the bracket and its costs. That sharpens §M7a rather than contradicting it — "the loss is in costs, hold time or bracket geometry" can now drop the third possibility for these two. **ElasticBand, EmaCrossover, InsideBarTrailing and OpeningRange all have a flatten carrying a losing bracket**, and only two of the four end up net positive.

## The two at the front are mirror images

`session_close_share` is 0.1 for InsideBar and 0.5 for OpeningRange, which reads as "a caveat" and "a large caveat". The decomposition says something different and opposite about each:

- **OpeningRange's bracket is a net cost and the whole of its result is the flatten.** §M28.9 measured this on one configuration over the full window; it is now 20 of 20 on both roots on the **held-out** window, at a median of −65,519 / −634,403 against a flatten of +79,927 / +804,908. The single-configuration finding generalises to the confined shortlist.
- **InsideBar's flatten is a net cost and the whole of its result is the bracket.** The flatten loses on 20 of 20 configurations on both roots, and it hands back **about 90% of what the bracket earns** — 0.92 of it on MNQ, 0.89 on NQ.

An archetype whose `session_close_share` is 0.1 is not thereby safe from the clock. A tenth of InsideBar's legs carry nine tenths of its gross back out.

## InsideBar's stop is nearly inert and the flatten is doing its work

The shortlist picks `atr_multiplier = 20.0` on 20 of 20 configurations on both roots — the **largest value in a grid of `[5, 10, 20]`**, on an archetype whose default geometry is already lopsided at a 1× ATR target against a 10× ATR stop. At that width the stop takes 32 legs on MNQ against the target's 1,412.

The same twenty parameter sets at each stop width, 5-minute bars, held out, MNQ / NQ:

| stop                          | bracket net               | flatten net               | net P&L          | PF            | close share   | stop legs | close legs | close bars |
| ----------------------------- | ------------------------- | ------------------------- | ---------------- | ------------- | ------------- | --------- | ---------- | ---------- |
| 5× ATR                        | +64,103 / +720,691        | −57,340 / −664,453        | 7,987 / 52,569   | 1.031 / 1.018 | 0.049 / 0.054 | 178 / 198 | 85 / 102   | 40 / 41    |
| 10× ATR                       | +111,537 / +1,280,796     | −104,547 / −1,126,585     | 9,437 / 166,619  | 1.038 / 1.061 | 0.070 / 0.076 | 88 / 92   | 116 / 132  | 49 / 49    |
| **20× ATR** — the grid's edge | **+172,538 / +1,809,532** | **−158,386 / −1,626,819** | 13,668 / 195,762 | 1.057 / 1.080 | 0.085 / 0.089 | 32 / 36   | 134 / 149  | 58 / 56    |

**The flatten loses on 20 of 20 at every stop width on both roots**, so its cost is a property of the archetype rather than of the widest stop. What the stop axis changes is *who* takes the loser: stop legs fall 178 → 32 while close legs rise 85 → 134, and the target's leg count barely moves at all (1,448 → 1,412). **Widening the stop does not convert stops into targets; it converts them into flattens**, held a median of 40 bars at 5× and 58 bars at 20×.

That trade is worth taking on the stored numbers — net P&L rises across the axis on both roots — but the ratio does not improve: the flatten hands back 0.88 to 0.94 of the bracket's net at every width tested. And the distribution over all 432 stored 5-minute rows per root says the axis is not simply "wider is better":

| `atr_multiplier` | profitable %    | pf median         | net median           | `session_close_share` |
| ---------------- | --------------- | ----------------- | -------------------- | --------------------- |
| 5                | 72.2 / 72.2     | 1.036 / 1.032     | 9,351 / 81,044       | 0.054 / 0.056         |
| 10               | 93.1 / 91.0     | 1.057 / 1.055     | 14,948 / **141,386** | 0.073 / 0.075         |
| 20               | **96.5** / 92.4 | **1.060** / 1.052 | **15,677** / 130,900 | 0.087 / 0.090         |

**On MNQ the grid's last value is its best, so the axis is truncated** — the defect §M28.9 named on `ORB_FRACTIONS` and [#262] extended. **On NQ it is not**: both profit factor and net P&L peak at 10 and fall away at 20, and the selection window picks 20 there anyway, on 20 of 20. That is a small decay finding about the instrument on the same axis, in the shape §M27.3 recorded for the target multiplier.

## What it costs to read this, and what it cannot say

- **Bars held are counted in bars, so a figure pooled over resolutions is not a duration.** InsideBar's shortlist is 5-minute on both roots and its column is readable directly; OpeningRange's spans all five resolutions and its 198-bar median is a mixture. The column is comparable within a bar size and nowhere else.
- **`paired` below 20 is a selection shortlist with no held-out partner**, not a filter — DeadCatBounce and EmaCrossover lose rows to the `MIN_TRADES` floor on the shorter window.
- **Two of the seven are pooled over variants** — ElasticBand over four ladders and EmaCrossover over two — which is [#263]'s dilution and it is not corrected here. OpeningRange is confined to `cash-open+30m entry=breakout target=width` for the reason §M28.9 gives; every other database holds one variant.
- **Choosing the best of twenty still binds**, and agreement across two roots is the only guard applied.
- **The decomposition is arithmetic on the stored logs and adds no assumption.** Across the two readings, **526 of 526 shortlisted rows** have their exit reasons sum to the stored `net_pnl` exactly, so the columns partition the sweep's own figure rather than approximating it. `ambiguous_share` is at or below 0.04 on every row here, so none of this sits in the corner §M28.7 found.

## The verdict, and what it changes about the registry

- **The column changes what the registry looks like.** `session_close_share` orders the archetypes one way and the decomposition orders them another, and the archetype whose reading it most changes is the one with the *smallest* share.
- **InsideBar's largest single cost is the forced flat**, which is a prop-firm account rule and not a parameter — § "Flat before the session close". The usual response to a losing exit is therefore unavailable: the flatten cannot be widened, delayed or switched off, and the only lever on it is a bracket that closes the position first.
- **Its stop axis trades one cost for another**, and the grid ends where the selection window wants to go on both roots while the holdout agrees on only one. That is the truncation [#262] answered for the opening range, on a different archetype, and it is cheap to settle.
- **§M28.9's opening-range finding generalises.** One configuration on the full window is now 40 of 40 held out on two roots, so "the bracket as configured does not pay for itself" is a property of the confined space rather than of the cell that found it.
- **Nothing here re-ranks anything.** The decomposition is attribution, it enters no gate, and no configuration changed position because of it.

Every figure above is a measurement of one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_shortlist.py` — not a standing property.

[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
[#263]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/263
[#264]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/264
