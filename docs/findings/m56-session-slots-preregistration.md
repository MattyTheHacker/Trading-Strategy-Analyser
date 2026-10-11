---
title: "M56 — pre-registration: every archetype in half-hour slots of the cash session"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: every archetype's campaign variants in the 13 half-hour slots from 09:30 to 16:00 ET, a stratum each, at 2, 5, 10 and 15 minutes on both roots; gates 1 and 2 are §M27's per slot, and gate 3 runs on every slot that clears gate 2 on both roots under §M54's protocol, read family-wise with one family per archetype.
---

# M56 — pre-registration: every archetype in half-hour slots of the cash session ([#439])

[§M27.7](m27-7-time-of-day.md) left the fine clock unread: **"`bar_of_session` is still unread. ... stratifying by it is a multiple-comparisons decision rather than a free improvement."** Seven phases are the coarsest cut, and the cells that matter most sit inside one of them: InsideBarTrailing's live candidate trades `phase=MIDDAY`, three and a half hours wide. [§M54](m54-family-wise-null-preregistration.md) has since built the family-wise null that decision needs, so the slots run with it.

**What has changed since §M27**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: a new condition, the slot. The grids, the costs and the windows are the campaign's own.

**This file was written and committed before the sweep started.** The slots, the bar sizes, the read and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Slots**       | the 13 half-hours from 09:30 to 16:00 ET, a stratum each, `slot=0930` to `slot=1530`, through `slot_filter` — `docs/nt8-fidelity.md`, "Entries in one half-hour slot of the session" |
| **Variants**    | every archetype's campaign variants, the grids §M27 and §M44 swept                                                                                                                   |
| **Strata**      | the slots alone; the unfiltered and phase strata are the core pass's, re-swept first ([#439])                                                                                        |
| **Resolutions** | 2, 5, 10 and 15 minutes, as §M44's split passes ran                                                                                                                                  |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                       |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                         |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                          |
| **Size**        | 1,485,952 combinations, both windows: 13/7 of the core pass's seven phase cells, which recorded about an hour of sweep time                                                          |

```bash
uv run tools/campaign_sweep.py --split --strata slot --resolutions 2 5 10 15
```

**A slot gates the signal bar, as a phase does**, so an order submitted on a slot's last bar fills in the next one.

### Measured before the run: what each slot leaves

The sweep rules ask for the signals a new gate leaves before it is crossed with anything. Each archetype at its defaults on MNQ's whole spliced series, signals in the cash hours and in the thinnest and busiest slot:

| archetype         | 5m cash | 5m fewest     | 5m most       | 15m cash | 15m fewest    | 15m most      |
| ----------------- | ------- | ------------- | ------------- | -------- | ------------- | ------------- |
| DeadCatBounce     | 451     | 22 (15:00)    | 44 (10:00)    | 184      | 9 (15:00)     | 20 (13:30)    |
| PullBackAndGo     | 832     | 42 (09:30)    | 78 (13:00)    | 293      | 16 (09:30)    | 35 (15:30)    |
| EmaCrossover      | 5,319   | 316 (11:30)   | 738 (09:30)   | 1,820    | 84 (15:00)    | 292 (09:30)   |
| EmaPullback       | 3,885   | 200 (09:30)   | 362 (10:30)   | 1,365    | 18 (10:00)    | 153 (09:30)   |
| InsideBar         | 2,469   | 147 (15:30)   | 244 (10:00)   | 872      | 27 (15:30)    | 89 (10:00)    |
| InsideBarTrailing | 2,079   | 119 (15:00)   | 214 (10:00)   | 820      | 45 (13:00)    | 85 (09:30)    |
| ElasticBand       | 14,561  | 536 (11:00)   | 3,414 (09:30) | 6,077    | 127 (13:30)   | 1,315 (09:30) |
| OpeningRange      | 108,213 | 1,508 (09:30) | 9,048 (10:30) | 37,081   | 1,508 (09:30) | 3,016 (10:00) |
| SqueezeBreakout   | 886     | 5 (10:30)     | 166 (15:30)   | 390      | 2 (13:30)     | 96 (09:30)    |

These are signals over the whole series, and the holdout is its last 40%; a signal taken while a position is open does not trade. **DeadCatBounce and PullBackAndGo leave 9 to 78 signals a slot at 5 and 15 minutes**, so most of their held-out cells will fall under the 30-trade floor and leave no row. **SqueezeBreakout's squeeze is rare at midday**, down to 2 signals a slot at 15 minutes. **OpeningRange's signal is dense** — an armed bar is a signal — so its counts are bars an order rests on rather than trades, and under its 30-minute range the 09:30 slot holds one bar a session, the one whose close completes the range. None of this changes the slots; it says where a cell can only read as empty.

## What will be read

1. **Gates 1 and 2 are §M27's, per slot.** `tools/campaign_report.py --window selection holdout` reads the slot dimension cut by bar size, and `tools/campaign_holdout.py` gives one row per root and slot: the best 20 on the selection window, measured on the holdout, above 1.0 **and** above the slot's own held-out median.

2. **Gate 3 runs on every slot that clears gate 2 on both roots**, under §M54's protocol: both roots, 5-minute bars, the top ten per slot ranked on the selection window by profit factor, tested on the holdout, 400 draws, and OpeningRange under the level draw (§M28.2). One run per archetype, saved, then read as its own family:

   ```bash
   uv run tools/campaign_null.py --strategy <archetype> --stratum <its slots that clear gate 2> --campaign-only \
       --root MNQ NQ --resolution 5 --window selection --test-window holdout --top 10 \
       --iterations 400 [--draw levels] --out <its table>
   uv run tools/campaign_null.py --family-of <its table>
   ```

3. **One family per archetype**, at most 13 slots × 2 roots × 10 configurations = 260 tests. **A slot clears where, on both roots, at least one of its configurations has a family-wise p below 0.05.** A refused test is named and left out, and each family's size is stated as the tests actually measured. If no slot of an archetype clears gate 2, its gate 3 is not run, and that is its result.

4. **Beside every slot, `session_close_share` and `ambiguous_share`**, because a late slot's exits are the forced flat's at coarse bars, as §M27.7 found for the afternoon phase.

5. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **No archetype has a slot that clears gate 3 family-wise on both roots.** No cash-hours phase beat its matched null on both roots in §M27.7. The one cash-hours cell that has since, InsideBarTrailing's midday (§M28.16, §M44), is seven slots wide, and §M54 predicts that even it does not clear family-wise.
- **DeadCatBounce, PullBackAndGo and SqueezeBreakout clear gate 2 on both roots in no slot**, from the counts above.
- **InsideBarTrailing clears gate 2 on both roots in more of the seven midday slots, 10:30 to 14:00, than of the six outside them.**
- **OpeningRange clears gate 2 on both roots in at least half of its slots from 10:00 on**, as it does unfiltered.

## What this run is not

- **Not the hours outside the cash session.** §M27.7's LONDON and OVERNIGHT results stay at the phase cut.
- **Not a slot crossed with anything.** Strata are one dimension at a time, and a slot is never crossed with a phase or a label.
- **Not finer than half an hour, or one minute.** The slot is 30 minutes, and 1-minute bars are absent from the split passes, as in §M44.
- **Not a port.** Every slot row is `TIER1_ONLY`. A port is InsideBarTrailing's entry window set to the slot's bounds — `docs/nt8-fidelity.md`, "Entries in one half-hour slot of the session".

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
