---
id: M63
title: "M63 — EmaPullback's one-bar confirmation entry fails gate 4 at every bar size"
archetypes: [EmaPullback]
issues: [311]
gates: [4]
outcome: negative
verdict: >-
  Pre-registered before its outputs were opened, and it fails. At 10 and 15 minutes, where it cleared §M39's paired bar on both roots, no shortlisted configuration survives without its session-close legs, and the median configuration's bootstrap 5th-percentile profit factor is 0.58 to 0.71, so the confirmation passes gate 4 at no bar size. The walk-forward fails too, on both roots at 10 minutes and on MNQ at 15. Its shortlists beat the market entry's, which fail every read as well, so the paired gain is real and is a gain over a losing entry.
---

# M63 — EmaPullback's one-bar confirmation entry fails gate 4 at every bar size ([#311])

Pre-registered in [`m63-ema-pullback-confirmation-gate-4-preregistration.md`](m63-ema-pullback-confirmation-gate-4-preregistration.md), committed before any of the outputs read here were opened.

## In plain terms

EmaPullback waits for a dip back to a moving average in an uptrend. Its confirmation entry only goes in if price then breaks the signal bar, through a stop order. On the October 2026 re-sweep it beat entering at market ([§M61](m61-registry-resweep-fill-fixes.md)), so this asked the harder questions. Do its best configurations, chosen on the earlier data, make money when walked forward through the whole series? Do they hold up when their own trades are resampled? Do they make money without the forced exit at the session close?

**They don't.** At the two bar sizes that mattered, none makes money once the session-close exits are taken out, every resampling floor is well below break-even, and the walk-forward fails on at least one root at both. In three of the four cells, the median of the best twenty loses money on the later data. It does beat the market entry, which fails every one of the same reads, but beating a losing entry is not an edge.

## The verdict cells

The one-bar confirmation, unfiltered, the selection window's top 20 per root and bar size re-run on the holdout:

| root | minutes | held-out PF, median | walk-forward, pooled | bootstrap p05 PF, median | without the session-close legs, PF / net-to-drawdown | reads passed |
| ---- | ------: | ------------------: | -------------------: | -----------------------: | ---------------------------------------------------- | ------------ |
| MNQ  |      10 |               0.927 |                0.554 |                    0.576 | 0.540 / −0.89                                        | none         |
| NQ   |      10 |               0.974 |                0.813 |                    0.711 | 0.557 / −0.88                                        | none         |
| MNQ  |      15 |               0.951 |                0.862 |                    0.678 | 0.539 / −0.93                                        | none         |
| NQ   |      15 |               1.098 |            **1.209** |                    0.679 | 0.568 / −0.93                                        | walk-forward |

**The confirmation fails gate 4 at both verdict bar sizes, and at 2, 5 and 30 minutes too.** No configuration survives the exclusion in any of the four cells, and at most 1 of 20 is profitable without its session-close legs, which make 29% to 35% of its legs. No configuration's bootstrap 5th percentile clears 1.0, and the median configuration loses money in 37% to 66% of resamples.

The market entry in the same four cells:

| root | minutes | held-out PF, median | walk-forward, pooled | bootstrap p05 PF, median | without the session-close legs, PF / net-to-drawdown |
| ---- | ------: | ------------------: | -------------------: | -----------------------: | ---------------------------------------------------- |
| MNQ  |      10 |               0.859 |                0.990 |                    0.661 | 0.482 / −0.97                                        |
| NQ   |      10 |               0.895 |                0.965 |                    0.679 | 0.529 / −0.95                                        |
| MNQ  |      15 |               0.853 |                0.848 |                    0.589 | 0.430 / −0.97                                        |
| NQ   |      15 |               0.871 |                0.827 |                    0.580 | 0.454 / −0.95                                        |

**The confirmation's shortlists are better than the market entry's in every cell**, by 0.07 to 0.23 of held-out profit factor at the median, which is §M61's paired gain seen from the shortlist. Both lose.

## Every bar size

The walk-forward's pooled profit factor, MNQ / NQ, in bold above 1.0. The exclusion and the bootstrap pass in none of these cells, so a bar size passes gate 4 nowhere:

| arm                    | 2 minutes             | 5             | 10            | 15                | 30                    |
| ---------------------- | --------------------- | ------------- | ------------- | ----------------- | --------------------- |
| one-bar confirmation   | 0.894 / **1.172**     | 0.755 / 0.829 | 0.554 / 0.813 | 0.862 / **1.209** | **1.267** / **2.223** |
| market entry           | **1.063** / **1.071** | 0.907 / 0.955 | 0.990 / 0.965 | 0.848 / 0.827     | **1.217** / 0.815     |
| three-bar confirmation | **1.371** / **1.003** | 0.801 / 0.891 | 0.861 / 0.826 | 0.785 / 0.947     | **1.190** / **1.664** |

**Not one of the thirty arm × root × bar size cells survives the exclusion or passes the bootstrap.** Without its session-close legs the median configuration's profit factor is 0.35 to 0.62 and its net-to-drawdown negative in every cell. Its bootstrap 5th percentile is 0.43 to 0.90, and at most 2 of 20 configurations in any cell clear 1.0. So the walk-forward passes at 30 minutes do not rescue anything. At 30 minutes the shortlist's median configuration loses held out on both roots under the one-bar confirmation and the market entry, and breaks even under the three-bar confirmation on NQ alone, at 1.005.

**The permutation test finds nothing either way.** Its p-values run from 0.00 to 1.00 across configurations, and the observed drawdown sits above its reordered null's median on 8 to 19 of 20, with no pattern by arm or bar size.

## The prop replay

Read, not tested: each held-out shortlist through the four 2026 linked presets at its stored size.

- **On NQ, no replay of either arm is profitable**, on any account at any bar size. TopStep's scaling plans refuse 47% to 96% of the trades.
- **On MNQ the confirmation is the better entry at 15 minutes and the worse at 10.** On TopStep 50K, half its 15-minute replays are profitable, at a median net of −$175, against none of the market entry's at −$2,262. At 10 minutes it is 30% at −$1,300 against 50% at +$406. On both Apex accounts, at most 5% of either arm's replays are profitable, at a negative median net.

## The predictions

- **"The exclusion fails in every cell, for both arms." Right.** No configuration of any arm survives it anywhere.
- **"The bootstrap fails in every cell, for both arms." Right.**
- **"The walk-forward passes on both roots for the confirmation at 15 minutes." Wrong**: 1.209 on NQ, 0.862 on MNQ. **"It fails on at least one root at 2 and 5 minutes for both arms." Wrong for the market entry at 2 minutes**, which passes on both roots at 1.063 and 1.071, and right for the rest.
- **"So the confirmation does not pass gate 4 at any bar size, and the reason is the exclusion and the bootstrap, not the walk-forward." Right that it passes at none, wrong about the reason**: at 10 minutes the walk-forward fails on both roots too, and at 15 on MNQ.

## What this settles, and what it does not

**It settles the confirmation entry as a candidate: it is not one.** It improves on EmaPullback's market entry, as §M61 found, and both fail gate 4 in every cell. What fails them is the same thing that fails EmaPullback's campaign variants in §M61's read of §M28.12: every shortlisted configuration earns its result on the forced flat. The paired gain stands as a comparison between two arms. It does not make either one tradeable, and the archetype stays parked with its `Tier2Status`.

**It leaves `phase=CLOSE` unread**, the one stratum where §M61's gate-3 family found the confirmation clearing on both roots. Gate 4 ran on the unfiltered stratum only, and `CLOSE` is the hour the forced flat closes, so the exclusion would remove what that cell trades on.

**The holdout is not fresh**, as the pre-registration said. That cuts the other way here: the read was the confirmation's best chance, on the window it was named a candidate on, and it failed.

## How it was read

- **The reads.** `tools/campaign_gates.py --variants emapullback-confirm --strategies EmaPullback --resolutions N --reads gates paired null gate4 --gate4-strata unfiltered`, then the same with `--reads prop --prop-strata unfiltered`, once per bar size, in the reads that followed the re-sweep on 20 October 2026. That is 1,000 permutation reorderings and 1,000 bootstrap resamples per configuration, and five sliding walk-forward folds.
- **The verdict.** Per root, bar size and arm: the walk-forward's pooled out-of-sample profit factor; the median, across the 20 configurations, of each one's bootstrap 5th-percentile profit factor; and the medians of their profit factor and net-to-drawdown with the session-close legs removed. A read passes above 1.0, and the arm passes gate 4 at a bar size where all three pass on both roots.
- **The re-runs reproduce.** Every held-out configuration these reads re-ran matches the trades and net its sweep stored.

[#311]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/311
