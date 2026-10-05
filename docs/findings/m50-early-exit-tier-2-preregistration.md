---
title: "M50 — pre-registration: the conditional early exit's second tier, and the breakeven stop"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [369, 351]
gates: [1, 2]
outcome: spec
verdict: >-
  Written while the sweep ran and before any row of it was read: 38 arms — #369's second tier and two breakeven arms — against a control with every rule off, over every archetype's stored grid unchanged, at 5, 10 and 15 minutes, unfiltered and in the two midday candidates; a cell clears only if the arm the selection window picks has a positive median paired profit-factor delta against the control, held out, with a sign test at p < 0.05, on both roots — §M48's bar, over a family of 33 cells — and a cell that clears is a candidate for #354's re-read rather than a result on its own.
---

# M50 — pre-registration: the conditional early exit's second tier, and the breakeven stop ([#369])

[§M48](m48-early-exit-result.md) ran [#369]'s first tier, the market exits the findings name, and found that an exit able to close a winner costs while one closing only losers barely moves. This campaign runs the second tier: three more market exits and two stop moves, built in [#430] — `docs/nt8-fidelity.md`, "The conditional early exit" and "Tightening the stop with time". It adds the breakeven stop ([#351]), built in [#406] and never swept, because #369 asks for it to be swept beside the rest so the arms pair.

**This file was written after the sweep started and committed before any row it wrote was read**, as §M48's was. The sweep's log prints one pooled best and median profit factor per sweep call, across all 39 arms at once, and nothing below was chosen after one of those lines had been looked at. The arms, the bar sizes, the breakeven arms and the bar below were chosen before the sweep started.

## What was run

|                 |                                                                                                                           |
| --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 39, one rule on in each, the control with every rule off included (below)                                                 |
| **Grid**        | every archetype's stored campaign grid, unchanged, once per arm — `tools/README.md` § "campaign_sweep.py", `early-exit-2` |
| **Strata**      | unfiltered on all nine archetypes; `phase=MIDDAY` on InsideBarTrailing and OpeningRange, the two [#344] candidates        |
| **Resolutions** | 5, 10 and 15 minutes; 2 minutes is left out, as §M47.1 and §M49 left it                                                   |
| **Roots**       | MNQ and NQ, spliced continuous, on the archive every stored campaign row since 2026-09-20 was swept on                    |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                              |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                               |
| **Size**        | 3,354,624 combinations unfiltered and 292,032 at midday, on two workers                                                   |

```bash
uv run tools/campaign_sweep.py --variants early-exit-2 --split --strata early-exit-2 \
    --resolutions 15 --n-jobs 2    # then 10, then 5
uv run tools/campaign_sweep.py --strategies InsideBarTrailing OpeningRange \
    --variants early-exit-2 --split --strata midday --resolutions 15 --n-jobs 2    # then 10, then 5
```

### The arms

| rule                             | arms                                                                                      | count |
| -------------------------------- | ----------------------------------------------------------------------------------------- | ----: |
| control                          | `exit2=off`                                                                               |     1 |
| no excursion by bar N (A3)       | N of 3, 5, 10 and 20 bars, crossed with a best excursion of 0.5 and 1 R                   |     8 |
| not working by minute N (A5)     | N of 15, 30 and 60 minutes, crossed with losing, and short of a 0.5 R excursion           |     6 |
| invalidated on a close (E1)      | with and without "only if losing"                                                         |     2 |
| age stop, a step (B1)            | at bars 3, 5 and 10, crossed with a fraction of 0.5 and 1 of the way to the entry         |     6 |
| age stop, a line (B1)            | to the entry over 10 and 20 bars                                                          |     2 |
| age stop, only while losing (B2) | a step at bars 3, 5 and 10, half way to the entry                                         |     3 |
| late stop (C1)                   | the last 15, 30 and 60 minutes, crossed with the entry, the bar's extreme and 1 ATR of 14 |     9 |
| breakeven ([#351])               | at 0.5 and 1 R, on the close                                                              |     2 |

**Every stored axis is kept.** ElasticBand sweeps `max_hold_bars` over `[0, 30]`, and every bar-timed arm acts before bar 30, so no combination is refused and every arm holds exactly its control's combinations. **The bar-timed arms mean a different time at each resolution**, so they are never read pooled across resolutions (§M29); the minute-timed arms mean the same time at every one, which is what they are for. DeadCatBounce and PullBackAndGo hold two to three bars, so most of the bar-timed arms will read as unbound on them.

**The family is stated here.** 38 treatment arms × 9 archetypes × 3 resolutions × 2 roots is 2,052 paired cells unfiltered, and 456 more at midday. That is the best-of-many #369 warns about, which is why the verdict below is one selection per cell rather than a scan of all of them.

## What will be read, stated before the run finished

1. **The control is a reproduction first.** Every `exit2=off` row must equal the stored campaign row with the same base variant, parameters, root, resolution, window and stratum, on every stored statistic: `tools/campaign_early_exit.py --set early-exit-2 --reproduce`. The parameter families the arms set are left out of the join. A single difference is a defect, and nothing below is read until it is explained.
2. **The effect is read paired, never off a shortlist.** Each arm against `exit2=off` of the same base variant, on profit factor, one row per archetype × root × resolution, **in each window separately**, with the pair count printed and no conclusion drawn from zero pairs. Beside it: trade count, commission, win rate, average bars held and `session_close_share`, and `bound`, the share of paired rows whose average hold moved at all. **An arm bound on fewer than half its paired rows in a cell is reported as untested there, not as no effect.** A stop move binds the same way a market exit does, by ending a position on another bar.
3. **The verdict is the selection window's pick, read held out**, exactly as §M48's. In each archetype × resolution cell, and on each root separately, the selection window picks the bound arm with the highest median paired delta, over all 38 arms together. **The cell clears only if, on both roots, that pick's held-out median delta is positive and its sign test reaches p < 0.05.** 27 cells unfiltered and 6 at midday: a family of 33. The sign test's p-value is not an independent-sample one, because configurations of one cell share trades (§M29), so a cell that clears is a candidate for [#354]'s re-read and not a result on its own.
4. **Four contrasts are read the same way, as description**: each "only if losing" arm against its unconditional twin, the minutes form against the bar form at the nearest matching age, the step against the line, and the three late-stop levels against each other.
5. **Gates 1 and 2 are §M27's, per arm**: the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, and `tools/campaign_holdout.py`'s `passes` per root.
6. **No gate 3.** No arm is an entry rule, so the null is the same strategy without the arm, which is the control (#369).
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run finished

- **The control reproduces the stored rows exactly.**
- **The market-exit arms repeat §M48's split.** The excursion exit and the minutes form at a losing threshold behave as §M48's not-working exit did at the matching ages: an arm that can close a position still in profit costs held out in a majority of cells, and one closing only losers moves profit factor by less than 0.05 in most cells.
- **The invalidation exit is unbound on DeadCatBounce and PullBackAndGo**, whose stop is the signal bar's extreme plus two ticks, so a close past that extreme is nearly always a stop already hit. **Wherever it binds, "only if losing" barely changes it**, because a close past the signal bar's adverse extreme is a losing close unless the entry filled beyond it too.
- **The late stop helps InsideBar and costs on OpeningRange, InsideBarTrailing, EmaCrossover and ElasticBand**, in a majority of each one's held-out cells. It takes positions out before the flatten, and §M28.12 found the flatten a net cost for InsideBar alone and a net gain for those four.
- **A stop moved to the entry costs more than one moved half way**, in a majority of cells: a stop at the entry turns more winners that come back into scratches.
- **The selection window's pick pays on both roots in no more than a few of the 33 cells.** §M29, §M37, §M39 and §M48 all found selection-window wins that did not hold out, and that is the base rate.

## What this run is not

- **Not #369's third tier.** The stalled, session-phase, regime-flip, higher-timeframe, volume, volatility, counter-trend, momentum and give-back rules are not built.
- **Not a sweep of each rule's whole range.** Each rule runs at a few settings; a cell that clears is a reason to sweep its rule further, held out, and not a tuned setting.
- **Two strata.** A rule inert unfiltered and live in another stratum is not looked for.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#351]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/351
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#369]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/369
[#406]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/406
[#430]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/430
