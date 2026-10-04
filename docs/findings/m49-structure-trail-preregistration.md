---
title: "M49 — pre-registration: InsideBarTrailing's runner trailed to structure"
archetypes: [InsideBarTrailing]
issues: [352]
gates: [1, 2]
outcome: spec
verdict: >-
  Written while the 15-minute sweep ran and before any row of it was read: 24 structure-trail arms against the runner trailing the high-water mark, over InsideBarTrailing's stored grid unchanged, in all 23 strata; an arm improves a root × resolution cell only where, unfiltered, its median paired profit-factor delta is positive and the sign test reaches p < 0.05 in both windows — §M37's bar, over a family of 192 cells if all four resolutions run — and a cell that clears is a candidate for #354's re-read rather than a result on its own.
---

# M49 — pre-registration: InsideBarTrailing's runner trailed to structure ([#352])

`Trading-Docs` §11 says to trail a stop to structure rather than at a fixed distance, and InsideBarTrailing's runner trails a fixed multiple of the inside bar's range behind the high-water mark. [#427] builds the alternative — `docs/nt8-fidelity.md`, "Trailing to structure" — and this campaign runs it against the trail it would replace.

**This file was written after the 15-minute sweep started, at 22:33 on 2026-10-04, and committed before any row it wrote was read.** The sweep's log prints a pooled line per sweep call, and none had been looked at.

**One look came first, and it shaped two choices below.** Before this campaign was planned, 12 settings — boxes of 2, 3, 5 and 10 bars, cushions of 0, 0.25 and 0.5 ATR — were run against the high-water trail on §M42's ten midday configurations per root at 5 minutes, in both windows. Every one of the 480 paired comparisons lost profit factor, and the loosest setting lost least. That look is why the ladder here reaches 40 bars and 1.0 ATR, and it informs the predictions. It is not part of the read.

## What will be run

|                 |                                                                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 25: the runner trailing the high-water mark (`structure=off`), and 24 structure-trail arms (below)                                  |
| **Grid**        | InsideBarTrailing's stored 432-combination grid, unchanged, once per arm — `tools/README.md` § "campaign_sweep.py", `ibt-structure` |
| **Strata**      | all 23, one context dimension at a time, at the raw regime and volume cuts the stored campaign ran                                  |
| **Resolutions** | 15 minutes first; 2, 5 and 10 minutes as later passes                                                                               |
| **Roots**       | MNQ and NQ, spliced continuous, the archive every stored InsideBarTrailing row was swept on, ending 2026-09-18                      |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                        |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                         |
| **Size**        | 993,600 combinations per resolution, on eight workers                                                                               |

```bash
uv run tools/campaign_sweep.py --variants ibt-structure --split --strata ibt-structure --resolutions 15
```

### The arms

`structure_trail_bars` of 2, 3, 5, 10, 20 and 40, crossed with `structure_trail_cushion_atr` of 0, 0.25, 0.5 and 1.0: 24 arms, each named `structure=box{bars}@{cushion}atr`. **Every arm starts the runner at the stop the control does**, so the two take the same risk on every trade and differ only in how the stop moves once the trade is open.

**The resolutions run one at a time, and whether to run 2, 5 and 10 minutes is decided after the 15-minute pass is read.** That decision changes which cells exist, never the bar a cell is held to.

**The family is stated here**: 24 arms × 2 roots × 4 resolutions is 192 cells unfiltered if every resolution runs, and 48 at 15 minutes alone.

## What will be read, stated before the run finished

1. **The control is a reproduction first.** Every `structure=off` row must equal the stored `trailing` row at the same root, resolution, window, stratum and parameters, on every stored statistic; the `structure_trail_*` columns, null in the stored rows, are left out of the join. A single difference is a defect, and nothing below is read until it is explained.
2. **The question is answered paired, not by a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, each arm against `structure=off`, one row per root × resolution, **in the unfiltered stratum and in each window separately**, with the pair count printed and no conclusion drawn from zero pairs. **An arm improves a cell only where its median delta is positive and the sign test reaches p < 0.05 in both windows** — §M37's bar. Configurations in one cell share trades, so the sign test's p-value overstates the evidence, and a cell that clears is a candidate for [#354]'s re-read rather than a result on its own.
3. **The mechanism is read off the same pairs**: `session_close_share`, trade count, `win_rate`, `avg_bars_held` and `mean_r`, and the profit-factor delta laid out by box and by cushion.
4. **The other 22 strata are description, not a test**, because they share bars. `phase=MIDDAY`, the cell [#344] would trade, is reported first among them.
5. **Gates 1 and 2 are §M27's, per arm**: the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, and `tools/campaign_holdout.py`'s `passes` per root and stratum with `--variant`.
6. **No gate 3.** This changes an exit, not the entry, so the null is the same strategy with the runner trailing the high-water mark, which is the control.
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run finished

- **The control reproduces the stored rows exactly.**
- **Every arm lowers `session_close_share` in every root × resolution cell, in both windows.** A stop moved to each broken box ends the runner before the close more often than one several inside-bar ranges behind the high-water mark.
- **Trade count rises**, because a position that ends earlier leaves the strategy free to enter again.
- **No arm clears the bar in any cell.** The first look lost profit factor on 480 comparisons of 480, and the runner reaching the close is where this archetype's money is made (§M42).
- **The cost shrinks as the box widens and the cushion grows.** If the loosest arm is still the least bad, the ladder has been cut short, and that is reported.

## What this run is not

- **InsideBarTrailing only.** No other archetype has a runner trailing a high-water mark.
- **One definition of structure**: the box of the last N bars and its midpoint. Swing pivots and the raw swing extreme are not built.
- **No breakeven.** Every arm runs with the breakeven stop off.
- **Not a port.** Every row with an arm on is `TIER1_ONLY` until a trade list is diffed against it.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#352]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/352
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#427]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/427
