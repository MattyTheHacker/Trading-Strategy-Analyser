---
title: "M52 — pre-registration: the conditional early exit's third tier"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369, 439]
gates: [1, 2]
outcome: spec
verdict: >-
  Written and committed before the sweep started: 36 arms — #369's third tier, nine more market exits and a shorter not-working count against the trend — against a control with every rule off, over every archetype's stored grid unchanged, at 5, 10 and 15 minutes, unfiltered and in the two midday candidates; a cell clears only if the arm the selection window picks has a positive median paired profit-factor delta against the control, held out, with a sign test at p < 0.05, on both roots — §M48's and §M50's bar, over a family of 33 cells — and a cell that clears is a candidate for #354's re-read rather than a result on its own.
---

# M52 — pre-registration: the conditional early exit's third tier ([#369])

[§M48](m48-early-exit-result.md) ran [#369]'s first tier and [§M50](m50-early-exit-tier-2-result.md) its second. Both found the same split: an exit able to close a winner costs, and one closing only losers costs less, or nothing where its bar for a loser is deep. This campaign runs the third tier, built in [#448]: a stall, leaving the entry's session phase, the higher-timeframe side turning, a thin bar, a heavy bar against, the ATR expanding while losing, closes against in a row, one close against by a distance in ATRs, a give-back from the best excursion, and a shorter not-working count for an entry against the trend — `docs/nt8-fidelity.md`, "The conditional early exit".

**This file was written and committed before the sweep started**, so unlike §M48's and §M50's it was not written while the sweep ran. The arms, the bar sizes, the bar below and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                      |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 37, one rule on in each, the control with every rule off included (below)                                            |
| **Grid**        | every archetype's stored campaign grid, unchanged, once per arm — `tools/README.md` § "Variant sets", `early-exit-3` |
| **Strata**      | unfiltered on all nine archetypes; `phase=MIDDAY` on InsideBarTrailing and OpeningRange, the two [#344] candidates   |
| **Resolutions** | 5, 10 and 15 minutes; 2 minutes is left out, as §M47.1, §M49 and §M50 left it                                        |
| **Roots**       | MNQ and NQ, spliced continuous, on the archive every stored campaign row since 2026-09-20 was swept on               |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                         |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                          |
| **Size**        | 3,182,592 combinations unfiltered and 277,056 at midday, on two workers                                              |

```bash
uv run tools/campaign_sweep.py --variants early-exit-3 --split --strata early-exit-3 \
    --resolutions 15 --n-jobs 2    # then 10, then 5
uv run tools/campaign_sweep.py --strategies InsideBarTrailing OpeningRange \
    --variants early-exit-3 --split --strata midday --resolutions 15 --n-jobs 2    # then 10, then 5
```

### The arms

| rule                              | arms                                                                                                                                                                 | count |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----: |
| control                           | `exit3=off`                                                                                                                                                          |     1 |
| stalled (A4)                      | 3, 5 and 10 closes without a new best price, each with and without "only if losing"                                                                                  |     6 |
| left the entry's phase (C3)       | a losing close in a session phase other than the one on the bar before the entry bar                                                                                 |     1 |
| higher-timeframe side turned (D3) | the close on the far side of the higher-timeframe average from the position, with and without "only if losing"                                                       |     2 |
| volume thinned (D4)               | a `THIN` bar after an entry whose bar before was not, with and without "only if losing"                                                                              |     2 |
| heavy bar against (D4)            | a `HEAVY` bar closing against the position, with and without "only if losing"                                                                                        |     2 |
| volatility expanded (D5)          | a losing close with the ATR above 1.25, 1.5 and 2 times its value on the bar before the entry bar                                                                    |     3 |
| closes against in a row (E2)      | 2, 3 and 4 closes, each worse than the one before, with and without "only if losing"                                                                                 |     6 |
| one close against (E2)            | a close worse than the one before by 0.5 and 1 ATR, with and without "only if losing"                                                                                |     4 |
| give-back (E3)                    | armed at a best excursion of 0.5 and 1 R, crossed with giving back half and all of it                                                                                |     4 |
| counter-trend gets less time (D6) | losing at bar 5, 10 and 20, and each of those again with bar 3, 5 and 10 for an entry against the trend — the three twins are in this set so the contrast pairs here |     6 |

**Every label is read at one setting, the same on every archetype**: the higher-timeframe average is a 50-period EMA of 60-minute bars; volume is the per-bar form against the median of the same bar over the last 20 sessions, `THIN` below 0.7 and `HEAVY` above 1.5; the trend label is the 20/50 EMA pair over a 5-bar slope with all three components agreeing; every ATR is 14 bars; and "losing" is a close worse than the entry. No stored grid sweeps any of them, so each arm holds exactly its control's combinations. The stall's "only while below +x R" from [#369] is built for x = 0 alone, which is its "only if losing" twin. **The give-back has no "only if losing" twin**: once armed, a losing close has given back all of the excursion, so the twin would be the all-of-it arm at either share, save a close exactly at the entry.

**Every bar count stops short of ElasticBand's stored hold cap of 30**, so no combination is refused. **The bar counts mean a different time at each resolution**, so nothing here is read pooled across resolutions (§M29). DeadCatBounce and PullBackAndGo hold two to three bars, so the longer counts will read as untested on them.

**The family is stated here.** 36 treatment arms × 9 archetypes × 3 resolutions × 2 roots is 1,944 paired cells unfiltered, and 432 more at midday. That is the best-of-many #369 warns about, which is why the verdict below is one selection per cell rather than a scan of all of them.

## What will be read

1. **The control is a reproduction first.** Every `exit3=off` row must equal the stored campaign row with the same base variant, parameters, root, resolution, window and stratum, on every stored statistic: `tools/campaign_early_exit.py --set early-exit-3 --reproduce`. The parameter families the arms set are left out of the join. A single difference is a defect, and nothing below is read until it is explained.
2. **The effect is read paired, never off a shortlist.** Each arm against `exit3=off` of the same base variant, on profit factor, one row per archetype × root × resolution, **in each window separately**, with the pair count printed and no conclusion drawn from zero pairs. Beside it: trade count, commission, win rate, average bars held and `session_close_share`, and `bound`, the share of paired rows whose average hold moved at all. **An arm bound on fewer than half its paired rows in a cell is reported as untested there, not as no effect.**
3. **The verdict is the selection window's pick, read held out**, exactly as §M48's and §M50's. In each archetype × resolution cell, and on each root separately, the selection window picks the bound arm with the highest median paired delta, over all 36 arms together. **The cell clears only if, on both roots, that pick's held-out median delta is positive and its sign test reaches p < 0.05.** 27 cells unfiltered and 6 at midday: a family of 33. The sign test's p-value is not an independent-sample one, because configurations of one cell share trades (§M29), so a cell that clears is a candidate for [#354]'s re-read and not a result on its own.
4. **Four contrasts are read the same way, as description**: each "only if losing" arm against its unconditional twin, each counter-trend arm against its twin, the give-back's two shares at each arming distance, and the volatility exit's three multiples against each other.
5. **Gates 1 and 2 are §M27's, per arm**: the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, and `tools/campaign_holdout.py`'s `passes` per root.
6. **No gate 3.** No arm is an entry rule, so the null is the same strategy without the arm, which is the control (#369).
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The control reproduces the stored rows exactly.**
- **Every exit that can close a winner costs held out in a majority of its bound cells**: the stall, the higher-timeframe, thin-bar and heavy-bar exits, the closes against in a row and the one close against, each without "only if losing", and the give-back. §M48 and §M50 both found this.
- **Each "only if losing" arm moves held-out profit factor less than its unconditional twin**, in a majority of the cells where both are bound.
- **The two exits that close only losers by construction, the phase exit and the volatility exit, cost held out in a majority of their bound cells**, as §M50's `losing` arms did: their bar for a loser is any close worse than the entry, which §M50 found shallow enough to cost.
- **The shorter count against the trend costs against its twin** in a majority of the cells where both are bound, because §M48's not-working exit cost more the earlier its bar.
- **DeadCatBounce and PullBackAndGo are untested by every arm that cannot fire before its fifth bar**, as §M48 found of its not-working ladder from 5 bars up.
- **The selection window's pick pays on both roots in no more than a few of the 33 cells.** §M29, §M37, §M39, §M48 and §M50 all found selection-window wins that did not hold out, and that is the base rate.

## What this run is not

- **Not tier 1 or 2 again.** The regime and trend exits are §M48's, and the excursion, minutes, invalidation, age, late and breakeven arms are §M50's. The three not-working twins here repeat §M48's 0 R arms under this set's own name, so the contrast with the counter-trend count pairs inside one set.
- **Not a sweep of each rule's whole range.** Each rule runs at a few settings and each label at one; a cell that clears is a reason to sweep its rule further, held out, and not a tuned setting.
- **Two strata.** A rule inert unfiltered and live in another stratum is not looked for.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#448]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/448
