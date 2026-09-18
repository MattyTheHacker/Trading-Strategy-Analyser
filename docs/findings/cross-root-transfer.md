---
title: "Do the shortlists travel? NQ and MNQ configurations run on ES, MES, GC and MGC"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [330]
gates: []
outcome: mixed
verdict: >-
  Most of what a shortlist loses is selection rather than instrument — the drop from selection window to own holdout is two to five times the further drop to a market never seen — and the two inside-bar archetypes travel with almost no additional cost, while nothing clears a profit factor of 1.1 anywhere.
---

# Do the shortlists travel? NQ and MNQ configurations run on ES, MES, GC and MGC

The first read on the four roots added in [#332]. Not a campaign and not a gate: no parameter was fitted on the new data and nothing here ranks it. It asks one question — **does a configuration chosen on the Nasdaq do anything on a different market** — and the answer is mostly about selection rather than about the markets.

## In plain terms

Nine strategies had already been tuned on Nasdaq futures. Four new markets were loaded — S&P 500 and gold, full-size and micro. The 200 best-tuned settings for each strategy were run unchanged on each new market, and the question was how much worse they got.

They got worse. But **most of that loss was already there** before the market changed: taking the same settings and running them on a later slice of the *Nasdaq* loses most of it. Changing to a completely different market costs surprisingly little on top. That is a statement about how much of a tuned result is luck, and it is the useful finding here.

## What was run

7,200 configuration runs over 9.0 million simulated trades, in about 50 minutes on 16 cores.

|                   |                                                                                  |
| ----------------- | -------------------------------------------------------------------------------- |
| **Selected on**   | NQ and MNQ, selection window, ranked by profit factor                            |
| **Run on**        | ES and GC from NQ's shortlist, MES and MGC from MNQ's                            |
| **Per archetype** | the top 200 per source root, so 200 x 9 x 2 selections, each run on two targets  |
| **Costs**         | the target root's own round turn, $4.50 full-size and $1.50 micro, plus one tick |
| **Tool**          | `tools/campaign_crossroot.py`                                                    |

**Roots are paired by size class** so the round-turn commission is identical on both sides of every comparison. Pairing MNQ's shortlist onto ES would change the market and the cost structure at once and the result could not be attributed to either.

Two filters do the real work, and without them the output is not readable:

- **A floor of 500 trades.** At the campaign's own `MIN_TRADES` of 30, the median top-200 row holds 43 trades and two thirds hold under 50. The median profit factor of a top 200 falls **3.77 → 2.01 → 1.80 → 1.44** as the floor rises 30 → 100 → 200 → 500, and all nine archetypes still fill 200 at every rung. That gradient is small-sample inflation, not strategy.
- **`ambiguous_share` at or below `disambiguate.MIN_AMBIGUOUS_SHARE`.** Ranked on profit factor alone, OpeningRange's `entry=rejection` rows take the whole shortlist: 613 trades, 612 wins, one loser worth $19.40, a stored profit factor of **3,955**, an `ambiguous_share` of 0.89 and trades held under one bar. §M28.7 had already measured that family — 0 of 20 keep a profit factor above 1.00 under the other policy. The first pass of this tool reproduced it exactly, reporting OpeningRange at a source profit factor of 127.6 and 100% of configurations profitable on every new root. With the guard, OpeningRange's source median is 1.376 and no cell anywhere exceeds an ambiguous share of 0.020.

## The result: selection costs more than the instrument does

Median profit factor at each step. "Own holdout" is the same configurations on the held-out window of the root they were chosen on, so it isolates what the instrument change adds.

**From NQ:**

| archetype         | selection | own holdout | ES    | GC    | instrument cost |
| ----------------- | --------- | ----------- | ----- | ----- | --------------- |
| InsideBar         | 1.587     | 1.046       | 1.005 | 1.076 | **−0.006**      |
| InsideBarTrailing | 1.422     | 0.882       | 1.007 | 1.080 | **+0.162**      |
| EmaCrossover      | 1.369     | 0.974       | 0.927 | 0.959 | −0.031          |
| DeadCatBounce     | 0.955     | 0.792       | 0.583 | 0.862 | −0.070          |
| SqueezeBreakout   | 1.291     | 1.034       | 0.920 | 0.989 | −0.079          |
| EmaPullback       | 1.491     | 1.087       | 1.040 | 0.951 | −0.092          |
| OpeningRange      | 1.376     | 1.157       | 0.992 | 0.940 | −0.191          |
| ElasticBand       | 1.513     | 1.051       | 0.847 | 0.827 | −0.213          |
| PullBackAndGo     | 1.034     | 0.776       | 0.412 | 0.557 | −0.292          |

**From MNQ**, the same ordering holds: InsideBarTrailing +0.020 and InsideBar −0.042 at one end, ElasticBand −0.244 and OpeningRange −0.184 at the other.

**The selection step costs 0.24 to 0.54 of profit factor; the instrument step costs 0.00 to 0.29, and for two archetypes it costs nothing at all.** InsideBarTrailing does *better* on both new markets than on the held-out window of its own — which is not evidence that it is good, since its own holdout median is 0.882, but it is evidence that what it does is not Nasdaq-specific.

**Nothing clears.** No archetype reaches a median profit factor of 1.1 on any new root. The best cells are InsideBar on MGC (1.093) and GC (1.076) and InsideBarTrailing on GC (1.080).

## Share of the 200 that stay above 1.0

| archetype         | ES        | MES   | GC        | MGC       |
| ----------------- | --------- | ----- | --------- | --------- |
| InsideBar         | 0.525     | 0.240 | 0.725     | **0.785** |
| InsideBarTrailing | 0.545     | 0.005 | **0.710** | 0.430     |
| EmaPullback       | **0.670** | 0.660 | 0.295     | 0.135     |
| OpeningRange      | 0.495     | 0.760 | 0.060     | 0.120     |
| EmaCrossover      | 0.320     | 0.300 | 0.365     | 0.115     |
| SqueezeBreakout   | 0.225     | 0.040 | 0.420     | 0.270     |
| ElasticBand       | 0.055     | 0.020 | 0.080     | 0.015     |
| DeadCatBounce     | 0.000     | 0.000 | 0.045     | 0.000     |
| PullBackAndGo     | 0.000     | 0.000 | 0.000     | 0.000     |

**The two archetypes the registry already ranks worst come last here too**, on all four roots, which is the sanity check this read has to pass before any of the rest of it is worth reading.

**The inside-bar pair prefers gold and EmaPullback prefers the S&P**, consistently across both the full-size and the micro. That is the only cross-instrument structure in the table and it is one measurement, not a finding.

## Two things that would be misread

**OpeningRange's MES and MGC cells are the clock, not the strategy.** `session_close_share` runs **0.698 and 0.754** there — three legs in four are closed by the forced flat rather than by a bracket level — against 0.083 and 0.126 for the same archetype on ES and GC. The MNQ shortlist selected much longer-held configurations than the NQ one, and MES's 1.076 is a measurement of the session boundary. §M27.7 is the standing version of this trap; this is the sharpest instance of it outside that file. InsideBarTrailing sits at 0.32 to 0.38 on every root, which is high and is at least consistent across them.

**The full-size roots beat their micros in 6 of 9 archetypes on the S&P and 7 of 9 on gold**, which is the arithmetic §M26 recorded for NQ against MNQ rather than anything new: commission is a fixed sum per contract and the point value is ten times larger, so the drag per point is about a third.

## What this does not say

- **No gate was run.** There is no matched null and no walk-forward here, so nothing in this file is evidence that any archetype has an edge on any new root. It bounds how much a tuned configuration decays, and that is all.
- **Two archetypes' swept geometry is in mismatched units.** OpeningRange and SqueezeBreakout sweep `entry_offset_ticks` and `stop_offset_ticks` directly, and a 5-minute bar's ATR is **57.8 ticks on NQ, 11.6 on ES and 15.5 on gold**. The other 32 of 34 swept axes are ATR multiples, R multiples, fractions and periods, which are scale-free by construction and do transfer.
- **Two fixed guards stop binding.** `max_risk_ticks=250` on DeadCatBounce and `catastrophe_stop_ticks=400` on ElasticBand are 4.3 and 6.9 ATRs on NQ but 21 and 33 on ES, so they are effectively switched off on the new roots. Both archetypes are at the bottom of the table regardless.
- **`slippage_ticks=1.0` is harsher on the new roots in relative terms** — one tick is 1/58 of an NQ bar and 1/12 of an ES one — which is realistic in absolute terms and still a reason the S&P numbers are not directly comparable to the Nasdaq ones.
- **The prop-account read has not been run on these roots.** `tools/campaign_propobjectives.py` ranks its pool from stored campaign rows and no campaign has been swept on ES, MES, GC or MGC; that is the full sweep, not a further read of this one.

## The tooling defect this turned up

`tools/campaign_shortlist.py`'s `store_logs` prepared its re-run dataset as `PriceBasis.UNKNOWN` while loading raw bars, so any configuration reading an absolute price level was refused — [#330]. All 200 of EmaCrossover's top configurations carry `round_targets`, so the arm failed outright rather than partially. Fixed by passing `RAW`, which is what `tools/campaign_sweep.py` already declares the same bars as.

[#330]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/330
[#332]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/332
