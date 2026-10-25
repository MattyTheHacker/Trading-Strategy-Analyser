---
id: M57
title: "M57 — the noise-area rule clears gate 2 on both roots and not gate 3, and no arm clears the paired bar against it, though dropping its trail raises profit factor in every cell"
archetypes: [ElasticBand]
issues: [439]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 re-sweep at 2 to 15 minutes, with 1 minute still to run: the noise-area rule passes gate 2 unfiltered on both roots and in 11 of 18 strata, against a prediction that it would fail, and then clears gate 3 in no cell, at a smallest family-wise p of 0.115 over 216 tests; no arm clears §M37's paired bar against it — the fade costs in every cell, deciding on every bar costs on the selection window at every size, and dropping the trail raises the median profit factor in all 16 root, size and window cells but reaches the sign test on NQ's selection window at none.
---

# M57 — the noise-area rule clears gate 2 on both roots and not gate 3, and no arm clears the paired bar against it, though dropping its trail raises profit factor in every cell ([#439])

Pre-registered in [`m57-noise-area-preregistration.md`](m57-noise-area-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. It is the noise-area break, Zarattini, Aziz and Barbon's intraday momentum rule, which [§M28](m28-opening-range-spec.md) listed and [§M28.2](m28-2-deferral-list.md) deferred, run as a band source on ElasticBand.

**One minute is not read yet.** The pre-registration names 1, 2, 5, 10 and 15 minutes, and the re-sweep's 1-minute pass has not reached this set. Everything below is the four larger bar sizes, so the paired read's family is 12 cells rather than 15. Gates 2 and 3 were also read at 2 to 15 minutes; one minute's rows could change which strata clear gate 2, and so gate 3's family.

## In plain terms

The noise-area rule draws a band around the day's open, as wide as the market usually moves from the open by that time of day. Every half hour it buys a close above the band or sells a close below it, and follows the trade with a stop on the band's edge or the day's average price.

**On its own it looks promising.** Nearly every setting made money on both the earlier and the later data, and the best settings picked on the earlier data still made money on the later data.

**But it does not beat random entries.** The strict test, which compares it against the same number of trades taken at random times under the same conditions, finds nothing that passes on both contracts.

Of the three changes tried, betting the other way loses everywhere, and checking every bar instead of every half hour makes it worse. Dropping the trailing stop and holding to the close does better on every comparison. The pre-registered test needs that improvement to be consistent across settings on both contracts in both periods, and on the full-size contract in the earlier period it is not.

## What was run

|                 |                                                                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | `noise=rule target=runner`, the rule; `noise=every-bar`, decided on every bar; `noise=no-trail`, without the trail; `noise=fade`, faded |
| **Grid**        | `entry_std` 1.0, 1.5 and 2.0 × `exit_at_cash_close` off and on × the account stop and the ATR stop, 12 combinations in every arm        |
| **Strata**      | all 23, one context dimension at a time; 18 hold rows                                                                                   |
| **Resolutions** | 2, 5, 10 and 15 minutes; 1 minute not yet run                                                                                           |
| **Roots**       | MNQ and NQ                                                                                                                              |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                            |
| **Windows**     | selection 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ), holdout from there to 2026-09-18                                          |

**Five strata hold no rows**: the four session phases outside the cash session, where the rule never decides, and `htf=AT`, the close exactly on the 60-minute average. Every unfiltered cell pairs all 12 combinations in both windows, so no pair count is short.

## The paired read: no arm clears

**An arm beats the rule at a resolution only where, on both roots, the median paired delta is positive and the sign test reaches p < 0.05, in both windows.** Unfiltered, 12 pairs per cell:

| arm       | bars | selection, MNQ / NQ | holdout, MNQ / NQ |
| --------- | ---- | ------------------- | ----------------- |
| every bar | 2    | −0.285 / −0.239     | −0.068 / −0.078   |
| every bar | 5    | −0.094 / −0.060     | −0.045 / −0.052   |
| every bar | 10   | −0.053 / −0.030     | +0.012 / −0.028   |
| every bar | 15   | −0.055 / −0.040     | −0.018 / −0.032   |
| no trail  | 2    | +0.068 / +0.059     | +0.029 / +0.020   |
| no trail  | 5    | +0.043 / +0.050     | +0.024 / +0.033   |
| no trail  | 10   | +0.041 / +0.062     | +0.058 / +0.044   |
| no trail  | 15   | +0.039 / +0.046     | +0.104 / +0.088   |
| the fade  | 2    | −0.651 / −0.654     | −0.245 / −0.307   |
| the fade  | 5    | −0.646 / −0.658     | −0.264 / −0.341   |
| the fade  | 10   | −0.642 / −0.656     | −0.288 / −0.330   |
| the fade  | 15   | −0.634 / −0.664     | −0.283 / −0.333   |

**The fade loses in every pair of every cell**, so the rule is on the right side of its own band: faded, the median configuration runs at a profit factor of 0.74 to 0.81 in both windows.

**Deciding on every bar costs** on the selection window at every size on both roots, and held out in seven of eight cells; its sign test reaches 0.05 only at 2 minutes, and on NQ held out at 5.

**Dropping the trail is the closest to clearing.** Its median delta is positive in all 16 root, size and window cells, and its sign test reaches p < 0.05 in 9 of them. On NQ's selection window it improves 8 of 12 pairs at every size, p = 0.39, so it clears at no resolution. With 12 pairs, the sign test needs 10 to reach 0.05.

**What each change does to the trades**, against the rule, unfiltered:

- **Without the trail**, a trade is held 6 to 42 bars longer, and its `session_close_share` rises by 0.19 to 0.39. It trades 86 to 131 fewer times, because a trade still open blocks the next signal. From 5 minutes up its win rate rises by 3 to 6 points, and its mean R rises by 0.04 to 0.08.
- **On every bar**, it trades about 140 to 1,530 more times and holds each trade 2 to 35 bars less. Its win rate falls by 4 to 12 points.
- **The fade** holds each trade 4 to 24 bars longer than the rule, and its mean R is 0.12 to 0.24 lower.

**Across the other 17 strata**, read as description because they share bars, 1 of the 198 arm, stratum and bar-size cells with rows on both roots in both windows clears the same bar: no trail in `compression=EXPANDED` at 10 minutes.

## Gates 1 and 2, per arm

**Gate 1: the rule is profitable almost everywhere.** 100% of its configurations are above a profit factor of 1.0 on the selection window and 92% (MNQ) and 100% (NQ) held out, at every size. Its median configuration runs at 1.39 to 1.42 on the selection window and 1.06 to 1.14 held out. No faded configuration is profitable in any cell.

**Gate 2: the rule passes unfiltered on both roots**, its held-out top 20 at 1.11 and 1.17 with all 20 profitable, and in 11 of 18 strata on both roots. It does not return its own drawdown held out: the top 20's net is 0.32 and 0.69 of it. Without the trail it passes in 9 strata and returns its drawdown 1.67 and 2.41 times over unfiltered. Deciding on every bar passes in 3 and the fade in 2.

## Gate 3: none of 22 cells clears family-wise

**The family is the rule's 11 gate-2 strata on both roots, 22 cells**: 5-minute bars, the top ten configurations by selection-window profit factor, tested on the holdout, 400 draws over bars. `trend=MIXED` has eight configurations per root, so the family is 216 tests. None was refused.

**A cell clears where, on both roots, a configuration reaches a family-wise p below 0.05. None does.** The smallest is 0.115, MNQ `htf=ABOVE` at `entry_std=1.0` under the account stop and out at the cash close, whose own p is 0.005; on NQ the same stratum's smallest is 0.135.

**One test at a time, 28 of the 216 are below p = 0.05**, in `unfiltered`, `htf=ABOVE`, `trend=UP` and `trend=MIXED` on both roots and `volume=NORMAL` on MNQ alone, and 186 are profitable held out. `regime=DIRECTIONAL` has the strongest shortlists, at a median held-out profit factor of 1.36 and 1.37, and none of its 20 tests reaches 0.05. They hold 95 to 190 trades, and their nulls run as high as 1.06 and 1.08.

## The predictions

- **"The rule does not clear gate 3 family-wise on both roots in any stratum." Right.**
- **"Unfiltered, the rule fails gate 2 on at least one root." Wrong.** It passes on both, with all 20 of each shortlist profitable held out.
- **"No arm clears §M37's bar against the rule at any resolution: deciding on every bar, dropping the trail and fading the same bars each cost or do nothing." Half right.** No arm clears, but dropping the trail does not cost or do nothing: it raises the median profit factor in all 16 cells, and fails the bar on NQ's selection window alone.
- **"The rule's unfiltered median profit factor under the account stop moves by less than 0.02 between 1 and 15 minutes on each root."** Not yet read. From 2 to 15 minutes it moves by 0.008 and 0.012 on MNQ's two windows, and by 0.021 and 0.005 on NQ's. Under the account stop the held-out trade count is 353 to 357 at every size.

## What this settles, and what it does not

**It settles the rule's direction.** The noise area is traded the right way round, and deciding on the half hour is better than deciding on every bar, as the paper has it.

**It does not make the rule a candidate.** It clears gate 2 in 11 strata, and then no cell beats a random entry family-wise. Its best shortlists do not return their own drawdown held out.

**It leaves the trail open.** Holding to the close without the trail beats the trail in every cell, and returns its drawdown held out where the rule does not, but it misses the pre-registered bar. Gate 3 was pre-registered on the rule alone, so it has not been run on the no-trail arm.

**One minute is owed**, and with it the fourth prediction and the rest of the family of 15.

## How it was read

- **Sweep.** `campaign_sweep.py --strategies ElasticBand --variants elastic-noise --split --strata elastic-noise`, at 2, 5, 10 and 15 minutes in the re-sweep; 1 minute is in its fourth part.
- **Paired read.** `campaign_paired`'s `paired` and `verdict` on profit factor, each arm against the rule, unfiltered and in each stratum, each window on its own; the same pairing on trades, win rate, average bars held, `session_close_share` and mean R beside it.
- **Gates 1 and 2.** The share of each arm's configurations above a profit factor of 1.0, and `campaign_holdout`'s `pair_windows` and `verdict` run once per arm.
- **Gate 3.** `campaign_null.py --strategy ElasticBand --variant 'noise=rule target=runner' --stratum <the 11> --root MNQ NQ --window selection --test-window holdout --resolution 5 --top 10 --iterations 400`, then `campaign_null.py --family-of` over its table.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
