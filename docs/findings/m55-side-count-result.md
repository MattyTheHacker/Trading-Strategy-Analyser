---
id: M55
title: "M55 — EmaCrossover's side-relative confluence count: the phase gate clears the paired bar at every bar size on the swing stop, and nothing clears gate 3"
archetypes: [EmaCrossover]
issues: [74, 439]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Pre-registered and run on the October 2026 re-sweep at 2 to 15 minutes, with 1 minute still to run: 14 of 64 arm, stop and bar-size cells clear §M37's paired bar against the ungated control, against a prediction of none — the phase gate at all four sizes under the swing stop and at 2 and 5 under the ATR stop, by +0.04 to +0.17 of held-out profit factor — but none clears gate 3 family-wise, at a smallest p of 0.41 over 140 tests, and three clearing cells still lose held out; the gates make EmaCrossover better than itself without making it better than a random entry.
---

# M55 — EmaCrossover's side-relative confluence count: the phase gate clears the paired bar at every bar size on the swing stop, and nothing clears gate 3 ([#439])

Pre-registered in [`m55-side-count-preregistration.md`](m55-side-count-preregistration.md) before the sweep started, and read here by that file's own rules, on the rows of the October 2026 re-sweep. It is the third of the loose ends [`build-spec-loose-ends-measured.md`](build-spec-loose-ends-measured.md) left: the confluence count over filters that point the trade's way, where [the first count](confluence-count-per-trade.md) ([#74]) used filters that did not.

**One minute is not read yet.** The pre-registration names 1, 2, 5, 10 and 15 minutes, and the re-sweep's 1-minute pass has not reached this set. Everything below is the four larger bar sizes, so the paired read's family is 64 cells rather than 80; one minute will be read when its rows exist.

## In plain terms

EmaCrossover buys when a fast average crosses above a slow one. This run asked whether it does better when it waits for other things to agree with the trade first: the time of day, the trend, a longer-term average and the day's average price.

**Waiting for the right time of day helps, clearly and on both contracts.** Taking only crosses in the first hour of the cash session or at midday raises the held-out profit factor at every bar size with the swing stop.

**But it does not make the strategy good.** The strict test against random entries placed under the same conditions finds nothing, and with the swing stop several of the helped versions still lose money. The filters make a weak strategy less weak; they do not turn it into one worth trading.

## What was run

|                 |                                                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 9 per stop: `gates=none`, each of `phase`, `trend`, `htf` and `vwap` alone, and at least one, two, three or all four of them |
| **Stops**       | `stop=atr` and `stop=swing`, 32 combinations in every arm                                                                    |
| **Stratum**     | unfiltered alone                                                                                                             |
| **Resolutions** | 2, 5, 10 and 15 minutes; 1 minute not yet run                                                                                |
| **Roots**       | MNQ and NQ                                                                                                                   |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                 |
| **Windows**     | selection 2020-10-25 to 2024-05-13 on MNQ (2024-05-10 on NQ), holdout from there to 2026-09-18                               |

Every cell pairs all 32 combinations in both windows, so no pair count is short.

## The paired read: 14 of 64 cells clear

**An arm beats the control at a bar size only where, on both roots, the median paired delta is positive and the sign test reaches p < 0.05, in both windows.**

| stop    | arm     | clears at    | held-out delta, MNQ / NQ, at each size it clears                   |
| ------- | ------- | ------------ | ------------------------------------------------------------------ |
| `swing` | `phase` | 2, 5, 10, 15 | +0.107 / +0.112, +0.138 / +0.120, +0.051 / +0.037, +0.151 / +0.167 |
| `atr`   | `phase` | 2, 5         | +0.047 / +0.040, +0.081 / +0.088                                   |
| `swing` | `4of4`  | 2, 5         | +0.124 / +0.129, +0.067 / +0.065                                   |
| `swing` | `3of4`  | 10, 15       | +0.069 / +0.051, +0.079 / +0.076                                   |
| `atr`   | `4of4`  | 15           | +0.193 / +0.228                                                    |
| `atr`   | `3of4`  | 15           | +0.051 / +0.058                                                    |
| `swing` | `htf`   | 10           | +0.030 / +0.036                                                    |
| `swing` | `vwap`  | 15           | +0.008 / +0.011                                                    |

**The phase gate is the result.** It is the only arm that clears at more than two sizes, and under the swing stop it clears at all four. The others clear at one or two sizes, mostly where three or four gates must agree, or by margins as small as the VWAP gate's +0.01, which a sign test over 32 configurations sharing most of their trades can call significant — the caution [§M48](m48-early-exit-result.md) recorded.

**What the phase gate does to the trades**, held out, against the ungated control: it keeps a quarter to a third of them, raises the win rate by three to seven points, and sends more of what is left to the forced flat — at 15 minutes the session-close share rises from 0.27 to 0.40 under the ATR stop and from 0.16 to 0.30 under the swing stop. Mean R rises under both stops and stays negative under the swing stop at every size.

## Gate 3: nothing clears

**Gate 3 ran on each of the 14 cells**: both roots, ranked within the arm, the best five configurations by selection-window profit factor, tested on the holdout, 400 draws over bars, the 140 tests read as one family.

**The smallest family-wise p is 0.41**, so no cell clears. One test at a time, two cells put a configuration below p = 0.05 on both roots: the swing stop's `3of4` at 10 minutes and `4of4` at 2 minutes. None was refused.

**Three of the clearing cells lose held out.** Their gate-3 shortlists' median profit factor is below 1.0 on both roots: the swing stop's `3of4` at 15 minutes (0.95 and 0.97), `4of4` at 5 minutes (0.96 and 0.95) and `vwap` at 15 minutes (0.96 and 0.97). Beating the ungated control is a relative bar, and the swing stop's control loses.

## Gates 1 and 2, per arm

**Every arm passes gate 2 on both roots but one**: the swing stop with all four gates, whose held-out top 20 runs at 0.95 and 0.92. Every arm holds the same 32 combinations, so none of these shortlists is a best-of-more.

**The phase gate has the strongest shortlists and the widest share of profitable configurations**: a held-out top-20 profit factor of 1.20 and 1.23 under the ATR stop and 1.17 and 1.22 under the swing stop, and 66% to 77% of configurations profitable held out, against 23% to 56% for the controls.

## The predictions

- **"No arm clears the bar in (2) at any resolution." Wrong.** Fourteen cells clear, eight of them outside the phase gate's.
- **"`gates=vwap`'s paired delta is the smallest in size of the four single gates at every resolution." Wrong.** It is the smallest in 16 of the 32 root, bar-size, window and stop cells; `htf` is in 9, `trend` in 6 and `phase` in 1.
- **"`gates=htf` under the 200-bar average reads as its control at 15 minutes, on both roots." Right.** On the 200-bar average at 15 minutes it trades identically to the control in 10 to 16 of 16 configurations per root and window, and never differs by more than 0.002 of profit factor.
- **"The count arms order by trades: `1of4` above `2of4` above `3of4` above `4of4` in every cell, and `4of4` under the 30-trade floor held out in most of them." Half right.** The order holds in all 32 cells. `4of4` is under the floor in none: its configurations keep a median of 137 to 319 held-out trades.
- **"At one minute every arm's median configuration loses on both roots."** Not yet read.

**The loose ends' own question**, read as description: `gates=2of4` beats both its neighbours, `1of4` and `3of4`, on held-out profit factor in 3 of 16 root, bar-size and stop cells. The two-of-four sweet spot the first count suggested is not here.

## What this settles, and what it does not

**It settles which gate matters.** Of the four, the time of day carries EmaCrossover's improvement, and it does so on both stops and both roots. The three side-relative gates, which the loose ends hoped would be informative where the first count's filters were not, add little alone; their counts help only when they bind hard enough to discard most of the trades.

**It does not make EmaCrossover a candidate.** Gate 3 finds no gated arm beating a random entry under the same gate. And the phase gate sends more of its trades to the forced flat, the dependence gate 4's exclusion read exists to catch, which was not run here.

**One minute is owed**, and with it the last of the five predictions and the rest of the family of 80.

## How it was read

- **Sweep.** `campaign_sweep.py --strategies EmaCrossover --variants side-count --split --strata side-count`, at 2, 5, 10 and 15 minutes in the re-sweep's second part; 1 minute is in its fourth.
- **Paired read.** `campaign_paired`'s `paired` and `verdict` on profit factor, each gated arm against `gates=none` under the same stop, unfiltered, each window on its own; the same pairing on trades, win rate, average bars held, `session_close_share` and mean R beside it.
- **Gate 3.** `campaign_null.py --strategy EmaCrossover --variant <arm> --stratum unfiltered --root MNQ NQ --resolution <its size> --window selection --test-window holdout --top 5 --iterations 400` for each of the 14 cells, then `campaign_null.py --family-of` over all fourteen tables.
- **Gates 1 and 2.** The share of each arm's configurations above a profit factor of 1.0, and `campaign_holdout`'s verdict run once per arm.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
