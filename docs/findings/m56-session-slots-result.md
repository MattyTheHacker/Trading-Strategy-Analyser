---
id: M56
title: "M56 — half-hour slots: one OpeningRange slot clears gate 3 family-wise on both roots, against a prediction of none, and it leans on the forced flat"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [439]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Pre-registered and run on the October 2026 re-sweep: 36 of 117 slot cells clear gate 2 on both roots and one clears gate 3, OpeningRange's 12:30 slot — long breaks of the 30-minute range under a 2-ATR stop — at a family-wise p below 0.05 on 10 of 10 MNQ and 8 of 10 NQ configurations, on about 75 held-out trades each; the ten are five distinct configurations and three of NQ's eight clear by 0.0001, and beyond the pre-registration the cell passes the walk-forward and fails gate 4's exclusion read on both roots, so it is a candidate for a pre-registered test of its own rather than a strategy.
---

# M56 — half-hour slots: one OpeningRange slot clears gate 3 family-wise on both roots, against a prediction of none, and it leans on the forced flat ([#439])

Pre-registered in [`m56-session-slots-preregistration.md`](m56-session-slots-preregistration.md) before the sweep started, and read here by that file's own rules. The slots were swept in the October 2026 re-sweep, on the archive §M44 repaired and with the fill fixes of [#453], [#471] and [#472] in every row.

## In plain terms

Every strategy was re-tested thirteen times, once for each half hour of the New York trading day, allowing it to open trades only in that half hour. The question was whether any strategy has a time of day where it works and survives the strict test against random entries.

**One does, and it was predicted that none would.** OpeningRange — buy when the price breaks above the high of the first 30 minutes of the day — beats random entries when it is only allowed to enter between 12:30 and 13:00 New York time, on both the full-size and the micro Nasdaq contract, after correcting for every other slot and setting tried for that strategy.

It is not ready to trade. It made about 75 trades in the most recent two years and four months, roughly one every eight trading days. And like the other OpeningRange results before it, most of its profit comes from positions still open when the session closes and the account rule forces them flat.

## What was run

|                 |                                                                                                                                                      |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Slots**       | the 13 half-hours from 09:30 to 16:00 ET, a stratum each                                                                                             |
| **Variants**    | every archetype's campaign variants                                                                                                                  |
| **Resolutions** | 2, 5, 10 and 15 minutes, as pre-registered; the 30-minute slot rows swept since are not read here                                                    |
| **Roots**       | MNQ and NQ                                                                                                                                           |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                         |
| **Selection**   | 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ)                                                                                                   |
| **Holdout**     | from there to 2026-09-18                                                                                                                             |
| **Gate 2**      | `campaign_holdout`'s verdict per root and slot, pooled over each archetype's campaign variants at the four bar sizes                                 |
| **Gate 3**      | §M54's protocol: 5-minute bars, the top ten per slot on the selection window, 400 draws, OpeningRange under the level draw, one family per archetype |

## The verdict: one slot clears, OpeningRange at 12:30

**A slot clears where, on both roots, at least one configuration has a family-wise p below 0.05.** One of the 36 slots read does:

| root | configurations | family-wise p below 0.05 | family-wise p, range | held-out PF | null PF   | excess, median | held-out trades |
| ---- | -------------- | ------------------------ | -------------------- | ----------- | --------- | -------------- | --------------- |
| MNQ  | 10             | **10**                   | 0.010 to 0.027       | 1.84–2.12   | 0.75–0.79 | +1.26          | 75–79           |
| NQ   | 10             | **8**                    | 0.030 to 0.097       | 1.99–2.15   | 0.82–0.86 | +1.22          | 73–76           |

**What the cell is.** Every one of the twenty is `window=30m stop=atr`, long only: a buy stop above the high of the first 30 minutes, submitted only on bars in 12:30–13:00 ET, with the stop two 14-bar ATRs away. Six take the R target and four the width target.

**Ten configurations are five.** Each appears twice, once with `max_entries_per_session` at 0 and once at 1, and the two trade identically on the selection window and differ by one trade held out. Both roots shortlist the same five, which differ in the target (1 R, 2 R or the range's width) and the entry offset (1 or 4 ticks). Read the counts as five configurations on each root, all clearing on MNQ and four on NQ.

**NQ's margin is thin.** Three of its eight clear at a family-wise p of 0.0499, and two do not clear at all, at 0.075 and 0.097.

**The whole slot is good, not only its shortlist.** The held-out median profit factor of every configuration in the slot is 1.60 on MNQ and 1.64 on NQ, the highest of any slot in this run on both roots at once.

**It held out better than it was selected.** Its five configurations ran at a profit factor of 1.56 to 1.65 on the selection window over 121 to 123 trades, and at 1.84 to 2.16 held out. That is the reverse of the usual decay, and the opposite of what [§M28.10](m28-10-follow-through-geometry.md) measured for OpeningRange's survivor, whose edge was absent from the most recent year.

## Gate 2: 36 of 117 slot cells clear on both roots

| archetype         | slots clearing on both roots | which                                    |
| ----------------- | ---------------------------- | ---------------------------------------- |
| DeadCatBounce     | 3                            | 09:30, 11:00, 15:30                      |
| PullBackAndGo     | 0                            |                                          |
| EmaCrossover      | 3                            | 09:30, 10:30, 11:00                      |
| EmaPullback       | 6                            | 09:30, 10:00, 12:00, 13:00, 15:00, 15:30 |
| InsideBar         | 4                            | 11:30, 12:30, 14:00, 15:00               |
| InsideBarTrailing | 5                            | 09:30, 10:00, 12:30, 14:00, 15:00        |
| ElasticBand       | 4                            | 12:00, 14:00, 14:30, 15:30               |
| OpeningRange      | 6                            | 10:00, 10:30, 12:30, 13:00, 14:00, 14:30 |
| SqueezeBreakout   | 5                            | 10:30, 11:30, 12:30, 15:00, 15:30        |

**Most of these are small samples.** Outside OpeningRange's 10:00 and 10:30 and a few other cells, the held-out top 20's median is mostly 30 to 80 trades, near the floor of 30 that a row needs to exist at all. DeadCatBounce's three are 2-minute results: every configuration in their top 20s is a 2-minute one, and it has no 5-minute row at 11:00 on either root or at 09:30 on MNQ.

**The late slots are the forced flat's.** Among the cells that clear, the held-out top 20's median session-close share reaches 0.89 for EmaPullback at 15:30 and 0.91 for SqueezeBreakout at 15:00, and OpeningRange's slots from 13:00 on run at 0.72 to 0.84. A trade entered late in the day has little time to reach anything but the close. **No clearing cell is ambiguous-bar driven**: the largest median `ambiguous_share` among them is 0.066, DeadCatBounce at 11:00. Every slot's figures are in the last section.

**Gate 1 is noisy per slot.** The selection window's profitable share runs from 0 to 1.0 slot to slot within most archetypes, on cells this small. Pooled over slots it rises with the bar size, from 0.38 at 2 minutes to 0.49 at 5 and 10 and 0.51 at 15, the campaign's usual order.

## Gate 3, archetype by archetype

| archetype         | slots tested | tests | refused | best family-wise p, MNQ | best family-wise p, NQ | clears    |
| ----------------- | ------------ | ----- | ------- | ----------------------- | ---------------------- | --------- |
| DeadCatBounce     | 1            | 6     | 0       | 0.254                   | 0.272                  | no        |
| PullBackAndGo     | 0            | —     | —       | —                       | —                      | not run   |
| EmaCrossover      | 3            | 60    | 0       | 0.823                   | 0.681                  | no        |
| EmaPullback       | 6            | 120   | 0       | 0.848                   | 0.599                  | no        |
| InsideBar         | 4            | 80    | 0       | 0.805                   | 0.953                  | no        |
| InsideBarTrailing | 5            | 100   | 0       | 0.648                   | 0.344                  | no        |
| ElasticBand       | 4            | 80    | 0       | 0.416                   | 0.504                  | no        |
| OpeningRange      | 6            | 120   | 0       | **0.010**               | **0.030**              | **12:30** |
| SqueezeBreakout   | 5            | 100   | 0       | 0.367                   | 0.297                  | no        |

**DeadCatBounce's family is one slot.** Of its three gate-2 slots, 11:00 and 09:30 hold no 5-minute selection row on at least one root, so gate 3, which reads 5-minute bars, cannot measure them; they are named and left out. At 15:30 only three configurations per root have rows.

**Two slots come close on one root and not the other.** OpeningRange at 10:00 puts every MNQ configuration and eight NQ ones below p = 0.05 on its own test, and two MNQ ones below 0.05 family-wise; NQ's best is 0.097. SqueezeBreakout at 15:00 puts eight MNQ configurations below 0.05 on its own test and none family-wise. Neither clears.

## The predictions

- **"No archetype has a slot that clears gate 3 family-wise on both roots." Wrong.** OpeningRange at 12:30 does.
- **"DeadCatBounce, PullBackAndGo and SqueezeBreakout clear gate 2 on both roots in no slot." Right for PullBackAndGo only.** DeadCatBounce clears in three slots, all on 2-minute rows, and SqueezeBreakout in five.
- **"InsideBarTrailing clears gate 2 on both roots in more of the seven midday slots, 10:30 to 14:00, than of the six outside them." Wrong.** One midday slot clears, 12:30, against four outside: 09:30, 10:00, 14:00 and 15:00.
- **"OpeningRange clears gate 2 on both roots in at least half of its slots from 10:00 on." Right, exactly**: six of twelve.

## Beyond the pre-registration: gate 4 and the prop accounts at 12:30

The pre-registration stops at gate 3. Gate 4's three reads, as [§M42](m42-insidebartrailing-gate-4.md) runs them, and the prop-account replay were then run on every OpeningRange variant in the slot at 5 minutes, each ranking its own top 20 on the selection window and reading the holdout. Every configuration was re-run from its stored row first and reproduced it exactly, on all 432 re-runs. The two variants gate 3 drew from:

| variant        | root | profit factor, whole | without the session-close legs | survive without them | bootstrap 5th pct of PF, median | above 1.0 | walk-forward, pooled test PF |
| -------------- | ---- | -------------------- | ------------------------------ | -------------------- | ------------------------------- | --------- | ---------------------------- |
| `target=R`     | MNQ  | 1.62                 | 0.80                           | 0 of 20              | 0.93                            | 10 of 20  | 1.88, passes                 |
| `target=R`     | NQ   | 1.88                 | 0.79                           | 4 of 20              | 1.06                            | 11 of 20  | 2.01, passes                 |
| `target=width` | MNQ  | 1.30                 | 0.39                           | 0 of 16              | 0.77                            | 4 of 16   | 1.97, passes                 |
| `target=width` | NQ   | 1.35                 | 0.46                           | 0 of 16              | 0.79                            | 4 of 16   | 2.08, passes                 |

**The exclusion read fails, and it is the same failure as the other OpeningRange cells.** About three in ten held-out legs end at the forced flat, and they carry the profit: without them the median configuration loses on both roots. [§M31.1](m31-1-survivor-gate-4.md) found exactly this in OpeningRange's fitted directional cell, and [§M28.15](m28-15-midday-cell.md) in its midday one. A long break at 12:30 that has not reached its target has the rest of the session to drift into the close, and this read says that is where its money is made.

**The walk-forward passes on both roots**, at a pooled test profit factor near 2 over about 98 test trades, with two or three distinct configurations chosen across five folds. **The bootstrap is split**: half the configurations put the 5th percentile of their profit factor above 1.0.

**Through the prop accounts at four contracts, MNQ funds one account.** The `target=R` variant passes TopStep's 50K Combine on 19 of 20 configurations and is profitable after fees on 13, at a median net of $2,865 over the holdout. It never passes either Apex account, and TopStep's 150K passes on half and is profitable on none. NQ at four full-size contracts is profitable on no account.

## What this settles, and what it does not

**It settles the prediction and nothing larger.** The pre-registered bar was met, and the forecast that no slot would meet it was wrong. That is worth recording before anything else is built on it.

**Eight families were read, and one cleared.** The family-wise p controls for the 120 tests inside OpeningRange's family, not for the eight families across archetypes. Had every archetype been noise, one of eight clearing its own family on both roots would not be rare. MNQ and NQ trade the same index, so their agreement rules out a cost or contract artefact rather than being a second sample.

**The sample is about 75 held-out trades per configuration**, over two years and four months, and five configurations rather than ten. That was enough for the null test and the walk-forward to reach a verdict, and not enough for the bootstrap to rule out a losing profit factor.

**What would test it:** the 12:30 slot on data it has not seen, pre-registered with this cell named, together with the question gate 4 leaves open, whether the slot's edge survives any exit other than the close. Every row here is `TIER1_ONLY`. A port is OpeningRange with its entry window set to the slot's bounds — `docs/nt8-fidelity.md`, "Entries in one half-hour slot of the session".

## How it was read

- **Sweep.** The pre-registered command, `campaign_sweep.py --split --strata slot --resolutions 2 5 10 15`, in the re-sweep's second part.
- **Gate 2.** `campaign_holdout`'s `pair_windows` and `verdict`, over each archetype's campaign variants at the four bar sizes and every slot. Beside it, the held-out top 20's median `session_close_share`, `ambiguous_share` and trades.
- **Gate 3.** `campaign_null.py --strategy <archetype> --stratum <its gate-2 slots> --campaign-only --root MNQ NQ --resolution 5 --window selection --test-window holdout --top 10 --iterations 400`, with `--draw levels` for OpeningRange, then `campaign_null.py --family-of` on each archetype's table.
- **Gate 4 and the prop accounts.** `campaign_gates.py --variants campaign --strategies OpeningRange --resolutions 5 --reads gate4 prop --gate4-strata slot=1230 --prop-strata slot=1230`.

## Every slot, gate 2

Pooled over the archetype's campaign variants at 2, 5, 10 and 15 minutes. "Held-out PF" is the selection window's top 20 measured on the holdout; "slot median" is every configuration's held-out median; the shares and trades are the held-out top 20's medians.

| archetype         | slot  | both roots | held-out PF, MNQ | held-out PF, NQ | slot median, MNQ | slot median, NQ | session-close share, MNQ | session-close share, NQ | ambiguous share, MNQ | ambiguous share, NQ | trades, MNQ | trades, NQ |
| ----------------- | ----- | ---------- | ---------------- | --------------- | ---------------- | --------------- | ------------------------ | ----------------------- | -------------------- | ------------------- | ----------- | ---------- |
| DeadCatBounce     | 09:30 | **yes**    | 1.36             | 1.32            | 1.07             | 1.10            | 0.00                     | 0.00                    | 0.032                | 0.020               | 32          | 37         |
| DeadCatBounce     | 10:00 |            | 0.57             | 1.14            | 0.50             | 0.85            | 0.00                     | 0.00                    | 0.000                | 0.028               | 32          | 34         |
| DeadCatBounce     | 10:30 |            | 0.34             | 0.74            | 0.27             | 0.61            | 0.00                     | 0.00                    | 0.062                | 0.094               | 34          | 33         |
| DeadCatBounce     | 11:00 | **yes**    | 1.37             | 1.53            | 1.34             | 1.50            | 0.00                     | 0.00                    | 0.066                | 0.050               | 38          | 40         |
| DeadCatBounce     | 11:30 |            | 1.36             | 0.96            | 1.31             | 0.92            | 0.00                     | 0.00                    | 0.052                | 0.021               | 36          | 39         |
| DeadCatBounce     | 12:00 |            | 0.54             | 0.56            | 0.62             | 0.67            | 0.00                     | 0.00                    | 0.064                | 0.056               | 32          | 31         |
| DeadCatBounce     | 12:30 |            | 0.70             | 1.31            | 0.80             | 1.29            | 0.00                     | 0.00                    | 0.000                | 0.000               | 32          | 32         |
| DeadCatBounce     | 13:00 |            | 0.82             | 1.09            | 0.90             | 1.12            | 0.00                     | 0.00                    | 0.030                | 0.021               | 34          | 36         |
| DeadCatBounce     | 13:30 |            | 0.67             | 0.93            | 0.52             | 0.82            | 0.00                     | 0.00                    | 0.106                | 0.056               | 42          | 40         |
| DeadCatBounce     | 14:00 |            | 0.49             | 0.68            | 0.51             | 0.64            | 0.00                     | 0.00                    | 0.023                | 0.000               | 32          | 34         |
| DeadCatBounce     | 14:30 |            | 0.99             | 0.99            | 0.91             | 0.90            | 0.00                     | 0.00                    | 0.053                | 0.049               | 33          | 32         |
| DeadCatBounce     | 15:00 |            | 0.33             | 0.51            | 0.31             | 0.50            | 0.00                     | 0.00                    | 0.000                | 0.000               | 36          | 39         |
| DeadCatBounce     | 15:30 | **yes**    | 1.13             | 1.12            | 1.00             | 1.10            | 0.00                     | 0.00                    | 0.026                | 0.026               | 38          | 38         |
| PullBackAndGo     | 09:30 |            | 0.70             | 0.98            | 0.77             | 0.97            | 0.00                     | 0.00                    | 0.000                | 0.000               | 41          | 39         |
| PullBackAndGo     | 10:00 |            | 1.03             | 0.83            | 0.96             | 0.74            | 0.00                     | 0.00                    | 0.011                | 0.011               | 46          | 43         |
| PullBackAndGo     | 10:30 |            | 0.31             | 0.41            | 0.34             | 0.38            | 0.00                     | 0.00                    | 0.027                | 0.011               | 38          | 45         |
| PullBackAndGo     | 11:00 |            | 0.62             | 0.77            | 0.60             | 0.72            | 0.00                     | 0.00                    | 0.014                | 0.000               | 36          | 35         |
| PullBackAndGo     | 11:30 |            | 0.49             | 0.82            | 0.48             | 0.83            | 0.00                     | 0.00                    | 0.019                | 0.000               | 54          | 46         |
| PullBackAndGo     | 12:00 |            | 0.60             | 0.83            | 0.57             | 0.77            | 0.00                     | 0.00                    | 0.036                | 0.029               | 47          | 52         |
| PullBackAndGo     | 12:30 |            | 0.66             | 0.59            | 0.63             | 0.53            | 0.00                     | 0.00                    | 0.054                | 0.000               | 34          | 32         |
| PullBackAndGo     | 13:00 |            | 0.74             | 1.57            | 0.76             | 1.44            | 0.00                     | 0.00                    | 0.000                | 0.000               | 32          | 32         |
| PullBackAndGo     | 13:30 |            | 0.71             | 0.85            | 0.75             | 0.80            | 0.00                     | 0.00                    | 0.024                | 0.034               | 33          | 40         |
| PullBackAndGo     | 14:00 |            | 0.82             | 0.79            | 0.70             | 0.66            | 0.00                     | 0.00                    | 0.000                | 0.032               | 34          | 34         |
| PullBackAndGo     | 14:30 |            | 0.45             | 0.32            | 0.28             | 0.31            | 0.00                     | 0.00                    | 0.024                | 0.019               | 52          | 52         |
| PullBackAndGo     | 15:00 |            | 1.49             | 0.92            | 1.39             | 0.88            | 0.00                     | 0.00                    | 0.000                | 0.027               | 32          | 33         |
| PullBackAndGo     | 15:30 |            | 2.16             | 1.14            | 2.02             | 1.14            | 0.00                     | 0.00                    | 0.075                | 0.058               | 30          | 30         |
| EmaCrossover      | 09:30 | **yes**    | 1.14             | 1.21            | 1.08             | 1.10            | 0.19                     | 0.21                    | 0.039                | 0.045               | 66          | 67         |
| EmaCrossover      | 10:00 |            | 1.00             | 1.08            | 1.05             | 1.07            | 0.19                     | 0.18                    | 0.035                | 0.058               | 56          | 56         |
| EmaCrossover      | 10:30 | **yes**    | 1.60             | 1.41            | 1.02             | 1.04            | 0.55                     | 0.57                    | 0.000                | 0.000               | 39          | 40         |
| EmaCrossover      | 11:00 | **yes**    | 1.13             | 1.52            | 1.03             | 1.04            | 0.15                     | 0.14                    | 0.024                | 0.000               | 42          | 34         |
| EmaCrossover      | 11:30 |            | 0.85             | 0.90            | 0.93             | 0.96            | 0.69                     | 0.68                    | 0.006                | 0.020               | 39          | 39         |
| EmaCrossover      | 12:00 |            | 0.58             | 0.58            | 0.97             | 1.00            | 0.64                     | 0.64                    | 0.000                | 0.000               | 37          | 35         |
| EmaCrossover      | 12:30 |            | 1.03             | 0.98            | 0.96             | 0.99            | 0.10                     | 0.13                    | 0.083                | 0.071               | 48          | 48         |
| EmaCrossover      | 13:00 |            | 1.05             | 1.01            | 0.98             | 1.02            | 0.20                     | 0.18                    | 0.026                | 0.051               | 40          | 39         |
| EmaCrossover      | 13:30 |            | 0.95             | 0.92            | 0.87             | 0.91            | 0.10                     | 0.10                    | 0.128                | 0.108               | 33          | 34         |
| EmaCrossover      | 14:00 |            | 0.76             | 0.74            | 0.75             | 0.78            | 0.28                     | 0.24                    | 0.057                | 0.114               | 34          | 32         |
| EmaCrossover      | 14:30 |            | 0.63             | 0.64            | 0.68             | 0.70            | 0.16                     | 0.16                    | 0.031                | 0.031               | 33          | 33         |
| EmaCrossover      | 15:00 |            | 0.67             | 0.78            | 0.81             | 0.86            | 0.29                     | 0.27                    | 0.030                | 0.029               | 31          | 46         |
| EmaCrossover      | 15:30 |            | 0.97             | 0.88            | 0.89             | 0.93            | 0.79                     | 0.73                    | 0.000                | 0.000               | 42          | 38         |
| EmaPullback       | 09:30 | **yes**    | 1.26             | 1.46            | 1.09             | 1.10            | 0.41                     | 0.48                    | 0.000                | 0.000               | 34          | 33         |
| EmaPullback       | 10:00 | **yes**    | 1.92             | 1.73            | 1.15             | 1.15            | 0.63                     | 0.63                    | 0.000                | 0.000               | 36          | 35         |
| EmaPullback       | 10:30 |            | 1.09             | 1.19            | 1.09             | 1.09            | 0.45                     | 0.46                    | 0.000                | 0.000               | 38          | 36         |
| EmaPullback       | 11:00 |            | 0.91             | 1.01            | 1.04             | 1.04            | 0.43                     | 0.43                    | 0.000                | 0.000               | 38          | 45         |
| EmaPullback       | 11:30 |            | 0.77             | 0.94            | 1.01             | 1.03            | 0.57                     | 0.57                    | 0.000                | 0.000               | 32          | 34         |
| EmaPullback       | 12:00 | **yes**    | 1.12             | 1.19            | 0.96             | 0.96            | 0.52                     | 0.55                    | 0.000                | 0.000               | 41          | 37         |
| EmaPullback       | 12:30 |            | 0.98             | 1.19            | 1.04             | 1.03            | 0.67                     | 0.74                    | 0.000                | 0.000               | 32          | 36         |
| EmaPullback       | 13:00 | **yes**    | 1.62             | 1.71            | 1.01             | 1.04            | 0.56                     | 0.56                    | 0.000                | 0.000               | 33          | 33         |
| EmaPullback       | 13:30 |            | 0.98             | 0.99            | 0.99             | 1.01            | 0.57                     | 0.61                    | 0.000                | 0.007               | 40          | 37         |
| EmaPullback       | 14:00 |            | 0.69             | 0.75            | 0.90             | 0.93            | 0.76                     | 0.74                    | 0.000                | 0.000               | 32          | 38         |
| EmaPullback       | 14:30 |            | 0.93             | 1.10            | 0.84             | 0.85            | 0.73                     | 0.71                    | 0.000                | 0.000               | 39          | 34         |
| EmaPullback       | 15:00 | **yes**    | 1.18             | 1.16            | 0.83             | 0.87            | 0.74                     | 0.76                    | 0.000                | 0.000               | 34          | 33         |
| EmaPullback       | 15:30 | **yes**    | 1.50             | 1.28            | 0.88             | 0.89            | 0.89                     | 0.83                    | 0.000                | 0.000               | 34          | 44         |
| InsideBar         | 09:30 |            | 3.41             | 0.61            | 1.26             | 1.29            | 0.06                     | 0.24                    | 0.000                | 0.000               | 36          | 44         |
| InsideBar         | 10:00 |            | 1.00             | 0.92            | 1.02             | 1.02            | 0.32                     | 0.32                    | 0.000                | 0.000               | 47          | 47         |
| InsideBar         | 10:30 |            | 0.66             | 0.72            | 1.29             | 1.07            | 0.30                     | 0.29                    | 0.000                | 0.000               | 34          | 34         |
| InsideBar         | 11:00 |            | 0.94             | 1.05            | 1.05             | 1.11            | 0.37                     | 0.29                    | 0.000                | 0.000               | 51          | 58         |
| InsideBar         | 11:30 | **yes**    | 1.76             | 2.11            | 0.93             | 0.89            | 0.26                     | 0.19                    | 0.000                | 0.000               | 30          | 30         |
| InsideBar         | 12:00 |            | 1.39             | 1.21            | 1.44             | 1.35            | 0.10                     | 0.13                    | 0.000                | 0.000               | 119         | 120        |
| InsideBar         | 12:30 | **yes**    | 2.19             | 2.15            | 1.17             | 0.96            | 0.19                     | 0.20                    | 0.000                | 0.000               | 45          | 41         |
| InsideBar         | 13:00 |            | 0.95             | 0.89            | 1.04             | 0.90            | 0.38                     | 0.21                    | 0.000                | 0.000               | 30          | 66         |
| InsideBar         | 13:30 |            | 0.93             | 0.98            | 0.95             | 1.11            | 0.08                     | 0.09                    | 0.000                | 0.000               | 121         | 124        |
| InsideBar         | 14:00 | **yes**    | 1.20             | 1.14            | 1.10             | 1.05            | 0.19                     | 0.25                    | 0.000                | 0.000               | 48          | 39         |
| InsideBar         | 14:30 |            | 0.99             | 0.75            | 0.86             | 0.81            | 0.34                     | 0.17                    | 0.000                | 0.000               | 39          | 121        |
| InsideBar         | 15:00 | **yes**    | 1.32             | 2.14            | 1.09             | 1.11            | 0.39                     | 0.37                    | 0.000                | 0.000               | 36          | 30         |
| InsideBar         | 15:30 |            | 0.75             | 0.64            | 0.89             | 0.96            | 0.58                     | 0.58                    | 0.000                | 0.000               | 42          | 35         |
| InsideBarTrailing | 09:30 | **yes**    | 3.04             | 1.92            | 1.04             | 1.02            | 0.19                     | 0.19                    | 0.000                | 0.000               | 34          | 35         |
| InsideBarTrailing | 10:00 | **yes**    | 1.39             | 1.38            | 0.89             | 0.92            | 0.51                     | 0.50                    | 0.000                | 0.000               | 93          | 90         |
| InsideBarTrailing | 10:30 |            | 1.04             | 1.15            | 1.14             | 1.02            | 0.30                     | 0.42                    | 0.000                | 0.000               | 158         | 84         |
| InsideBarTrailing | 11:00 |            | 0.85             | 0.91            | 1.02             | 1.10            | 0.64                     | 0.60                    | 0.000                | 0.000               | 51          | 53         |
| InsideBarTrailing | 11:30 |            | 1.01             | 1.61            | 1.06             | 0.96            | 0.58                     | 0.53                    | 0.000                | 0.000               | 30          | 31         |
| InsideBarTrailing | 12:00 |            | 1.00             | 0.90            | 1.27             | 1.21            | 0.05                     | 0.05                    | 0.000                | 0.000               | 133         | 138        |
| InsideBarTrailing | 12:30 | **yes**    | 1.94             | 2.14            | 1.26             | 1.13            | 0.09                     | 0.12                    | 0.000                | 0.000               | 58          | 56         |
| InsideBarTrailing | 13:00 |            | 0.96             | 0.81            | 0.98             | 0.88            | 0.42                     | 0.46                    | 0.000                | 0.000               | 30          | 67         |
| InsideBarTrailing | 13:30 |            | 0.85             | 1.12            | 0.91             | 1.01            | 0.28                     | 0.24                    | 0.000                | 0.000               | 114         | 66         |
| InsideBarTrailing | 14:00 | **yes**    | 1.30             | 1.35            | 1.01             | 1.00            | 0.21                     | 0.44                    | 0.000                | 0.000               | 48          | 40         |
| InsideBarTrailing | 14:30 |            | 0.91             | 0.94            | 1.02             | 0.97            | 0.63                     | 0.62                    | 0.000                | 0.000               | 35          | 34         |
| InsideBarTrailing | 15:00 | **yes**    | 1.48             | 1.85            | 0.88             | 0.82            | 0.54                     | 0.60                    | 0.000                | 0.000               | 51          | 30         |
| InsideBarTrailing | 15:30 |            | 0.71             | 0.68            | 0.83             | 0.83            | 0.75                     | 0.58                    | 0.000                | 0.000               | 55          | 49         |
| ElasticBand       | 09:30 |            | 0.67             | 0.68            | 0.78             | 0.79            | 0.02                     | 0.02                    | 0.014                | 0.016               | 183         | 192        |
| ElasticBand       | 10:00 |            | 0.70             | 0.60            | 0.87             | 0.88            | 0.00                     | 0.00                    | 0.000                | 0.000               | 37          | 41         |
| ElasticBand       | 10:30 |            | 0.49             | 0.57            | 0.83             | 0.85            | 0.28                     | 0.29                    | 0.000                | 0.000               | 34          | 35         |
| ElasticBand       | 11:00 |            | 0.88             | 0.93            | 0.84             | 0.88            | 0.05                     | 0.05                    | 0.000                | 0.000               | 35          | 33         |
| ElasticBand       | 11:30 |            | 0.73             | 0.68            | 0.78             | 0.81            | 0.03                     | 0.04                    | 0.000                | 0.000               | 38          | 40         |
| ElasticBand       | 12:00 | **yes**    | 1.35             | 1.40            | 0.85             | 0.90            | 0.33                     | 0.38                    | 0.000                | 0.000               | 39          | 38         |
| ElasticBand       | 12:30 |            | 0.57             | 0.66            | 0.96             | 0.98            | 0.04                     | 0.02                    | 0.000                | 0.000               | 62          | 68         |
| ElasticBand       | 13:00 |            | 0.83             | 0.70            | 0.86             | 0.88            | 0.10                     | 0.10                    | 0.000                | 0.000               | 57          | 60         |
| ElasticBand       | 13:30 |            | 0.58             | 0.55            | 0.85             | 0.87            | 0.08                     | 0.07                    | 0.000                | 0.000               | 60          | 60         |
| ElasticBand       | 14:00 | **yes**    | 1.33             | 1.33            | 1.04             | 1.06            | 0.37                     | 0.29                    | 0.000                | 0.000               | 38          | 38         |
| ElasticBand       | 14:30 | **yes**    | 1.23             | 1.17            | 1.08             | 1.11            | 0.52                     | 0.12                    | 0.000                | 0.000               | 74          | 57         |
| ElasticBand       | 15:00 |            | 0.92             | 0.76            | 1.02             | 1.04            | 0.00                     | 0.02                    | 0.000                | 0.000               | 130         | 65         |
| ElasticBand       | 15:30 | **yes**    | 1.03             | 1.06            | 0.92             | 0.97            | 0.32                     | 0.28                    | 0.003                | 0.000               | 124         | 48         |
| OpeningRange      | 09:30 |            | 1.02             | 0.97            | 0.98             | 0.96            | 0.45                     | 0.56                    | 0.000                | 0.000               | 144         | 145        |
| OpeningRange      | 10:00 | **yes**    | 1.37             | 1.36            | 0.94             | 0.95            | 0.51                     | 0.51                    | 0.000                | 0.000               | 201         | 199        |
| OpeningRange      | 10:30 | **yes**    | 1.13             | 1.11            | 1.02             | 1.04            | 0.58                     | 0.58                    | 0.000                | 0.000               | 160         | 162        |
| OpeningRange      | 11:00 |            | 0.95             | 0.91            | 1.03             | 1.03            | 0.55                     | 0.54                    | 0.008                | 0.008               | 89          | 89         |
| OpeningRange      | 11:30 |            | 1.06             | 1.04            | 1.34             | 1.36            | 0.66                     | 0.66                    | 0.000                | 0.000               | 119         | 119        |
| OpeningRange      | 12:00 |            | 1.17             | 1.03            | 1.11             | 1.07            | 0.50                     | 0.50                    | 0.000                | 0.000               | 68          | 66         |
| OpeningRange      | 12:30 | **yes**    | 2.07             | 2.03            | 1.60             | 1.64            | 0.46                     | 0.45                    | 0.000                | 0.000               | 75          | 73         |
| OpeningRange      | 13:00 | **yes**    | 1.13             | 1.33            | 1.00             | 1.07            | 0.76                     | 0.74                    | 0.000                | 0.000               | 80          | 81         |
| OpeningRange      | 13:30 |            | 1.11             | 0.94            | 1.15             | 1.22            | 0.58                     | 0.69                    | 0.009                | 0.009               | 50          | 72         |
| OpeningRange      | 14:00 | **yes**    | 1.05             | 1.13            | 0.86             | 0.94            | 0.72                     | 0.77                    | 0.000                | 0.000               | 55          | 54         |
| OpeningRange      | 14:30 | **yes**    | 1.00             | 1.03            | 0.70             | 0.73            | 0.83                     | 0.82                    | 0.000                | 0.000               | 68          | 64         |
| OpeningRange      | 15:00 |            | 0.59             | 0.59            | 0.62             | 0.67            | 0.71                     | 0.62                    | 0.000                | 0.000               | 50          | 49         |
| OpeningRange      | 15:30 |            | 0.91             | 0.96            | 0.72             | 0.71            | 0.83                     | 0.84                    | 0.006                | 0.006               | 61          | 61         |
| SqueezeBreakout   | 09:30 |            | 0.51             | 0.69            | 0.61             | 0.62            | 0.23                     | 0.50                    | 0.000                | 0.000               | 32          | 73         |
| SqueezeBreakout   | 10:00 |            | 0.90             | 0.93            | 0.81             | 0.85            | 0.63                     | 0.63                    | 0.000                | 0.000               | 33          | 33         |
| SqueezeBreakout   | 10:30 | **yes**    | 1.15             | 1.20            | 1.02             | 1.00            | 0.30                     | 0.28                    | 0.000                | 0.000               | 79          | 78         |
| SqueezeBreakout   | 11:00 |            | 0.56             | 0.97            | 0.89             | 0.90            | 0.46                     | 0.42                    | 0.000                | 0.000               | 75          | 52         |
| SqueezeBreakout   | 11:30 | **yes**    | 1.14             | 1.02            | 0.78             | 0.80            | 0.48                     | 0.29                    | 0.000                | 0.000               | 81          | 45         |
| SqueezeBreakout   | 12:00 |            | 0.80             | 0.70            | 1.02             | 1.08            | 0.15                     | 0.10                    | 0.000                | 0.000               | 42          | 39         |
| SqueezeBreakout   | 12:30 | **yes**    | 1.53             | 1.51            | 0.90             | 0.91            | 0.22                     | 0.19                    | 0.000                | 0.000               | 54          | 46         |
| SqueezeBreakout   | 13:00 |            | 0.84             | 0.91            | 0.76             | 0.77            | 0.45                     | 0.46                    | 0.000                | 0.000               | 47          | 54         |
| SqueezeBreakout   | 13:30 |            | 0.62             | 0.90            | 0.82             | 0.87            | 0.56                     | 0.57                    | 0.000                | 0.000               | 35          | 36         |
| SqueezeBreakout   | 14:00 |            | 0.72             | 0.80            | 0.77             | 0.79            | 0.13                     | 0.13                    | 0.000                | 0.000               | 39          | 42         |
| SqueezeBreakout   | 14:30 |            | 0.83             | 0.72            | 0.78             | 0.81            | 0.43                     | 0.10                    | 0.000                | 0.000               | 55          | 55         |
| SqueezeBreakout   | 15:00 | **yes**    | 1.85             | 1.95            | 0.90             | 0.95            | 0.91                     | 0.89                    | 0.000                | 0.000               | 37          | 37         |
| SqueezeBreakout   | 15:30 | **yes**    | 1.44             | 1.00            | 0.76             | 0.81            | 0.54                     | 0.63                    | 0.000                | 0.000               | 53          | 54         |

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/453
[#471]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/471
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/472
