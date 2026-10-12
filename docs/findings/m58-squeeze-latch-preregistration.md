---
title: "M58 — pre-registration: the latched squeeze"
archetypes: [SqueezeBreakout]
issues: [51, 439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: SqueezeBreakout traded only once its squeeze ends, from the window frozen at the last squeezed bar, for 3, 6 or 12 bar closes beside the unlatched control, over §M19.3's grid in all 23 strata at 2, 5, 10 and 15 minutes; a latch length beats the control at a resolution only where, on both roots, the paired median profit-factor delta is positive with a sign test at p < 0.05 in both windows — §M37's bar, over a family of 12 — and gate 3 is §M19.3's, read per arm over the unfiltered stratum and the strata where that arm clears gate 2 on both roots.
---

# M58 — pre-registration: the latched squeeze ([#439])

[§M19.2](m19-2-squeeze-breakout-spec.md) built SqueezeBreakout to rest a stop beyond a compressed window **while** the squeeze holds, and deferred the other reading of a squeeze: wait for it to end, then trade a break of the range it ended with. [§M19.3](m19-3-squeeze-breakout-swept.md) swept the first form and found the squeeze adds nothing measurable to a break of its window: unfiltered, nothing beats a random entry on either root, and how deep the squeeze was barely moves a paired profit factor. This runs the second form over the same grid.

**What has changed since §M19.3**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: the entry, and nothing else. The bracket, the grid, the strata and the bar sizes are §M19.3's. The rules and the NinjaScript a port would use are [`nt8-fidelity.md`](../nt8-fidelity.md), "The latched squeeze"; no fill code is new, and the latch runs through OpeningRange's loop as the squeeze does.

**This file was written and committed before the sweep started.** The arms, the strata, the bar sizes, the bar below and the predictions were all chosen before any of it ran.

## The rule, and the alternatives not taken

A latch opens on the first bar the squeeze no longer holds, freezes the window at the bar before, and rests §M19.2's stop beyond the frozen extreme for `latch_bars` closes, the release bar's included. It ends early when the squeeze holds again, on the session's last bar, at a close beyond the frozen window's other side, or at a fill. Three choices are in that:

- **No order while the squeeze holds.** Keeping the unlatched order during the squeeze and adding a tail after it would share most of its trades with the stored rows, so it could barely differ from them.
- **Frozen at the last squeezed bar, not at the release bar.** The release bar is usually the one that breaks, which widens the window, so freezing there makes the level the breakout bar's own extreme: a confirmation entry, which is §M39's question on another archetype. Frozen a bar earlier the level is the compressed range, and since §M18 refuses a stop at or through the close, **the latch trades only a re-break**: a release that broke and came back inside, or one that ended the squeeze without breaking.
- **A bar limit, and a close beyond the other side as a cancel.** A latch with no limit would live until a fill, a new squeeze or the close, and drop the one axis the arms vary. A setup that has closed through the wrong side has failed, and resting above it trades a different setup.

## The signal, measured before the sweep

**The latched signal leaves the matched null room to draw, and trades a little over a third to nine tenths as often as the unlatched rule.** On MNQ's continuous series, 2020-10-25 to 2026-09-18, at the default 20-bar window and 250-bar baseline, one bar of squeeze, the opposite stop and the R ladder, both forms, cuts of 0.05 and 0.25, both sides, at 2, 5, 10 and 15 minutes:

| latch     | spare bars per signal | trades, as a share of the unlatched rule's |
| --------- | --------------------- | ------------------------------------------ |
| off       | 2.6 to 16.2           | —                                          |
| 3 closes  | 15.1 to 43.5          | 37% to 64%                                 |
| 6 closes  | 8.3 to 26.0           | 48% to 77%                                 |
| 12 closes | 4.6 to 15.9           | 56% to 90%                                 |

Every cell clears `MIN_DRAW_FREEDOM`. A latched combination took about as long to simulate as the unlatched one on the same bars, single timings, so the size below scales the stored sweep's time by the combination count.

## What will be run

|                 |                                                                                                                                                                                                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 4, in one pass (below)                                                                                                                                                                                                                                                                                |
| **Grid**        | §M19.3's 1,728 combinations in every arm, across its four stop × target variants                                                                                                                                                                                                                      |
| **Strata**      | all 23, one context dimension at a time, as §M19.3 ran                                                                                                                                                                                                                                                |
| **Resolutions** | 2, 5, 10 and 15 minutes, as §M19.3 ran                                                                                                                                                                                                                                                                |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                                                                                                                                        |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                                                                                                                                          |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                                                                                                                                           |
| **Size**        | 2,543,616 combinations, both windows counted, four times §M44's re-sweep of §M19.3's grid, which recorded about 29 minutes — about 2 hours on twelve workers, taking that sweep to have run on twelve as [#439] takes that month's, and about 6 on two at the 3.1× slowdown it measured, read as ±30% |

```bash
uv run tools/campaign_sweep.py --strategies SqueezeBreakout --variants squeeze-latch --split \
    --strata squeeze-latch --resolutions 2 5 10 15
```

### The arms

| arm         | the entry                                                                              |
| ----------- | -------------------------------------------------------------------------------------- |
| `latch=off` | §M19.3's: beyond the rolling window while the squeeze holds — the control              |
| `latch=3`   | beyond the window frozen at the last squeezed bar, for up to 3 closes from the release |
| `latch=6`   | the same, for up to 6                                                                  |
| `latch=12`  | the same, for up to 12                                                                 |

Each name is a stored variant's followed by its arm, as in `stop=opposite target=R latch=6`, so an arm spans §M19.3's four stop × target variants. **`latch=off` is §M19.3's grid under names no stored row carries**, so it cannot collide with those rows in one database and can be checked against them. **The lengths are bar closes, not minutes** — 12 closes is 24 minutes at 2 minutes and three hours at 15 — so a length is never read pooled across resolutions.

## What will be read

1. **The control is a reproduction first.** `tools/campaign_early_exit.py --set squeeze-latch --strategy SqueezeBreakout --reproduce`, in every stratum: every `latch=off` row must equal its stored twin on every statistic, where the database holds that twin on the same bars and swept after [#453], which the planned re-sweep of every stored campaign provides; otherwise that half is skipped and the read says so. A single difference is a defect, and nothing below is read until it is explained.
2. **The effect is read paired, never off a shortlist.** `tools/campaign_early_exit.py --set squeeze-latch --strategy SqueezeBreakout --window <window>`: each length against `latch=off`, configuration by configuration within each stop × target variant, one row per root × resolution, **in the unfiltered stratum and in each window separately**, with that tool's columns beside it — trades and commission as ratios, win rate, average bars held and `session_close_share` as differences. The pair count is printed and nothing is concluded from zero.
3. **The verdict is §M37's bar.** A length beats the control at a resolution only where, **on both roots**, the median delta is positive **and** the sign test reaches p < 0.05 **in both windows**. Three lengths × four resolutions is a family of 12. The same read over the other 22 strata, with `--stratum`, is reported beside it as description, not a test, because the strata share bars.
4. **Gate 1 is §M19.3's, per arm**: the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, per root × resolution × window, split by stop and by side as §M19.3's table was.
5. **Gate 2 is §M19.3's, per arm**: `tools/campaign_holdout.py --strategies SqueezeBreakout --variant` with the arm's four names, so each arm's shortlist is ranked over its four variants as §M19.3's was over them; `passes` per root and stratum. Every arm holds the same 1,728 combinations, so unlike §M53's arms no shortlist is a best-of-more, and a count is compared across arms as description; the verdict is still item 3's.
6. **Gate 3 is §M19.3's, per arm.** Each latched arm's family is the unfiltered stratum on both roots, whatever gate 2 says, because it is the archetype's own question, plus every stratum where that arm clears gate 2 on both roots, at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. Both roots, the best five configurations by selection-window profit factor, measured on the holdout against the matched random entry over bars, 200 draws: `tools/campaign_null.py --strategy SqueezeBreakout --root MNQ NQ --window selection --test-window holdout --top 5 --iterations 200 --variant <the arm's four names> --stratum <the family>`. **A drawn bar outside every latch rests at its own rolling window**, so each arm's null is a random break of the window at the minutes that arm entered, the question §M19.2 set, and the excess carries the latch's timing and its frozen level together. **A cell passes only at p ≤ 0.05 on both roots**, §M19.3's bar. `latch=off` is measured over the union of the three families, so every latched cell has its control beside it, and each family is also read family-wise with `--out` and `--family-of` ([§M54](m54-family-wise-null-preregistration.md)) as description. If no stratum but the unfiltered one qualifies for an arm, its family is that one cell.
7. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The reproduction holds**, exactly, wherever the stored rows are on the same bars.
- **Every length trades less than the control in all sixteen root × resolution × window cells, and the shorter the latch the fewer**, as the table above measured at the defaults.
- **No length clears the bar at any resolution.** §M19.3 found how deep the squeeze was nearly inert; a latch changes when the break is taken, not what the squeeze before it measured.
- **Gate 3 fails unfiltered on both roots for every latched arm**, as it did for §M19.3's rule.

## What this run is not

- **Not the two-sided squeeze**, which the managed approach cannot express — [`nt8-fidelity.md`](../nt8-fidelity.md) § "The managed approach refuses the opposite-direction submission outright".
- **Not §M19.3's own deferrals**: gate 4 and the per-year and per-contract dispersion on `trend=UP`, a separate item in [#439].
- **Not the other freeze points or cancel rules** above, which were considered and not chosen.
- **Not one minute**, which SqueezeBreakout has never been swept at.
- **Not a port.** SqueezeBreakout has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
