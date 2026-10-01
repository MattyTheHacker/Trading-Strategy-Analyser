---
title: "M48 — pre-registration: the conditional early exit on every archetype"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369]
gates: [1, 2]
outcome: spec
verdict: >-
  Written while the sweep ran and before any row of it was read: 26 early-exit arms against a control with every rule off, over every archetype's stored grid unchanged, at 2, 5, 10 and 15 minutes, unfiltered and in the two midday candidates; a cell clears only if the arm the selection window picks has a positive median paired profit-factor delta against the control, held out, with a sign test at p < 0.05, on both roots — 44 cells in the family, and a cell that clears is a candidate for #354's re-read rather than a result on its own.
---

# M48 — pre-registration: the conditional early exit on every archetype ([#369])

[§M29](m29-maximum-hold-time.md) ruled out closing a position on a bar count, because a clock knows nothing about price. [#369] asks for the conditional form: an exit that fires only when price, time or context says the trade has failed. [#395] builds the four rules #369 pre-registers first — `docs/nt8-fidelity.md`, "The conditional early exit" — and this campaign runs every one of them over the whole registry.

**This file was written after the sweep started, at 16:55 on 2026-09-30, and committed before any row it wrote was read**, as §M39's reads were. The sweep's log prints one pooled best and median profit factor per sweep call, across all 27 arms at once, and nothing below was chosen after one of those lines had been looked at.

## What was run

|                 |                                                                                                                         |
| --------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 27, one rule on in each, the control with every rule off included (below)                                               |
| **Grid**        | every archetype's stored campaign grid, unchanged, once per arm — `tools/README.md` § "campaign_sweep.py", `early-exit` |
| **Strata**      | unfiltered on all nine archetypes; `phase=MIDDAY` on InsideBarTrailing and OpeningRange, the two [#344] candidates      |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                                                                 |
| **Roots**       | MNQ and NQ, spliced continuous, the archive §M44 re-swept and §M47 ran on                                               |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                            |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                             |
| **Size**        | 3,086,208 combinations unfiltered and 259,200 at midday, on twelve workers                                              |

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants early-exit --split --strata early-exit \
    --resolutions 2 5 10 15 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies InsideBarTrailing OpeningRange \
    --variants early-exit --split --strata midday --resolutions 2 5 10 15 --n-jobs 12
```

### The arms

| rule                    | arms                                                                             | count |
| ----------------------- | -------------------------------------------------------------------------------- | ----: |
| control                 | `exit=off`                                                                       |     1 |
| not working by bar N    | N of 3, 5, 10 and 20 bars, crossed with a threshold of −0.5, 0, +0.25 and +0.5 R |    16 |
| losing before the close | a window of 15, 30, 60 and 120 minutes                                           |     4 |
| regime change           | with and without "only if losing"                                                |     2 |
| trend turns against     | `opposed` and `not_with`, each with and without "only if losing"                 |     4 |

**Every stored axis is kept.** ElasticBand sweeps `max_hold_bars` over `[0, 30]`, past the ladder's top bar of 20, so no combination is refused as unable to fire and every arm holds exactly its control's combinations. **The not-working ladder is a bar count**, so N bars is 6 minutes at 2-minute bars and 5 hours at 15-minute bars, and it is never read pooled across resolutions (§M29).

**The family is stated here.** 26 treatment arms × 9 archetypes × 4 resolutions × 2 roots is 1,872 paired cells unfiltered, and 416 more at midday. That is the best-of-many #369 warns about, which is why the verdict below is one selection per cell rather than a scan of all of them.

## What will be read, stated before the run finished

1. **The control is a reproduction first.** Every `exit=off` row must equal the stored §M44 campaign row with the same base variant, parameters, root, resolution, window and stratum, on every stored statistic; the `early_exit_*` columns, null in the stored rows, are left out of the join. ElasticBand is in the join this time, because its axes are kept. A single difference is a defect, and nothing below is read until it is explained.
2. **The effect is read paired, never off a shortlist.** Each arm against `exit=off` of the same base variant, on profit factor, one row per archetype × root × resolution, **in each window separately**, with the pair count printed and no conclusion drawn from zero pairs. Beside it: trade count, commission, win rate, average bars held and `session_close_share` — the columns that decided §M29 — and `bound`, the share of paired rows whose median moved at all. **An arm bound on fewer than half its paired rows in a cell is reported as untested there, not as no effect**; DeadCatBounce and PullBackAndGo hold two to three bars, so most of the not-working ladder will read that way on them.
3. **The verdict is the selection window's pick, read held out** — §M29's "zero times in seven". In each archetype × resolution cell, and on each root separately, the selection window picks the bound arm with the highest median paired delta. **The cell clears only if, on both roots, that pick's held-out median delta is positive and its sign test reaches p < 0.05.** 36 cells unfiltered and 8 at midday: a family of 44. The sign test's p-value is not an independent-sample one, because configurations of one cell share trades (§M29), so a cell that clears is a candidate for [#354]'s re-read and not a result on its own.
4. **Four contrasts are read the same way, as description**: each "only if losing" arm against its unconditional twin, `not_with` against `opposed`, the four thresholds within each N, and the four close windows against each other.
5. **Gates 1 and 2 are §M27's, per arm**: the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, and `tools/campaign_holdout.py`'s `passes` per root. They say whether an arm's configurations are worth trading, which the paired delta does not.
6. **No gate 3.** This is not an entry rule, so the null is the same strategy without the exit, which is the control (#369).
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run finished

- **The control reproduces the stored rows exactly.**
- **Trade count moves far less than under §M29's cap.** In a majority of archetype × root × resolution cells, the median arm's trade count is within 10% of the control's. A conditional exit leaves most positions alone.
- **An arm that can close winners costs profit factor on OpeningRange, InsideBarTrailing, EmaCrossover and ElasticBand** in a majority of their held-out cells: the not-working exit at a positive threshold, and the regime and trend exits without "only if losing". §M28.12 found the flatten a net gain on those four.
- **"Only if losing" beats its unconditional twin in a majority of cells, and most clearly on InsideBar**, whose flatten §M28.12 found a net cost.
- **The losing-before-close arms move held-out profit factor by less than 0.05 in most cells.** §M41 measured the unconditional form at no more than 0.040.
- **The selection window's pick pays on both roots in no more than a few of the 44 cells.** §M37, §M39 and §M29 all found selection-window wins that did not hold out, and that is the base rate.

## What this run is not

- **No stop moves.** Breakeven ([#351]), a trail to structure ([#352]) and a stop that tightens with age or before the close are not built.
- **Only #369's first tier.** The excursion, stalled, clock-minute, invalidation, momentum and give-back rules are not built.
- **Two strata.** A rule that is inert unfiltered and live in some other stratum is not looked for, because 23 strata would multiply the family by 23 for cells nobody would trade.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#351]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/351
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#395]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/395
