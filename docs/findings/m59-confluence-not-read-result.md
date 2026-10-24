---
id: M59
title: "M59 — EmaCrossover's confluence count over conditions it does not read sorts nothing either: the top count does not beat a random entry in either window"
archetypes: [EmaCrossover]
issues: [74, 439]
gates: [3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 archive: counted over five conditions that read no moving average, at the signal bar, EmaCrossover's top count of five has a negative excess over 200 matched random entries on both roots on the selection window and on MNQ held out, and on NQ held out sits inside its null, so the count is not edge; its profit factor does not rise with the count either, against the prediction — the best count in the full window is one, on both roots — and the VWAP side holds on 59% to 70% of trades rather than the predicted three quarters.
---

# M59 — EmaCrossover's confluence count over conditions it does not read sorts nothing either: the top count does not beat a random entry in either window ([#439])

Pre-registered in [`m59-confluence-not-read-preregistration.md`](m59-confluence-not-read-preregistration.md) before the run, and read here by that file's own rules. It is the cleaner test [counting the confluence a trade actually had](confluence-count-per-trade.md) ([#74]) asked for: the same count over conditions that share none of EmaCrossover's machinery, read at the signal bar rather than the fill bar.

## In plain terms

EmaCrossover buys when a fast moving average crosses above a slow one. This run counted, for every trade, how many of five other signs agreed with it: the day's average price, the shape of the signal bar, a new high or low, a Bollinger midline and the morning's range. None of the five uses a moving average.

**More agreement does not mean better trades.** Trades where all five agreed did no better than random entries taken at the same times of day, in both the earlier and the later data. Trades where only one agreed did best of all, which is the opposite of what a useful count would show.

## What was run

|                   |                                                                                                                   |
| ----------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Configuration** | EmaCrossover at its defaults, both sides                                                                          |
| **Conditions**    | `vwap`, `body`, `new_extreme`, `midline` and `cash_range`, each for the trade's own side at its signal bar        |
| **Resolution**    | 5 minutes                                                                                                         |
| **Roots**         | MNQ and NQ, spliced continuous                                                                                    |
| **Costs**         | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                      |
| **Windows**       | the full series, then selection on its first 60% of bars and holdout on the last 40%, each warmed on its own bars |
| **Null**          | 200 matched random entries over bars, seed 0                                                                      |

About 18,700 trades on each root in the full window: 11,300 on the selection window and 7,300 held out.

## How often each condition held

Share of trades, full window, both sides:

| root | `vwap` | `body` | `new_extreme` | `midline` | `cash_range` |
| ---- | ------ | ------ | ------------- | --------- | ------------ |
| MNQ  | 65.9%  | 82.3%  | 80.9%         | 97.1%     | 7.1%         |
| NQ   | 66.2%  | 82.1%  | 80.9%         | 97.1%     | 7.1%         |

**The midline is near-constant, as expected**: a 20-bar midline sits beside the 21-bar average the cross has just gone through. The VWAP side holds less often than predicted, 70% for longs and 62% for shorts. The cash range is the rare one, because it is false overnight and inside the range. Between the windows each share above moves by under three points. Between the sides the VWAP's moves by up to 11 points, and the others' by under 2.

## The count against its null

Both sides together. A count with fewer than 30 trades is left out: count 0 holds 5 to 20 trades in every window. Each cell shows the profit factor, then the null's median, then the null's 95th percentile:

| count | selection, MNQ     | selection, NQ      | holdout, MNQ       | holdout, NQ        |
| ----- | ------------------ | ------------------ | ------------------ | ------------------ |
| 1     | 0.88 / 0.84 / 0.96 | 0.85 / 0.87 / 1.04 | 1.43 / 0.95 / 1.19 | 1.39 / 0.97 / 1.22 |
| 2     | 0.85 / 0.87 / 0.98 | 0.92 / 0.92 / 1.04 | 0.76 / 0.95 / 1.09 | 0.82 / 0.99 / 1.14 |
| 3     | 0.87 / 0.91 / 1.03 | 0.92 / 0.96 / 1.06 | 0.96 / 0.99 / 1.11 | 0.98 / 1.01 / 1.15 |
| 4     | 0.96 / 0.94 / 1.04 | 0.97 / 0.97 / 1.07 | 1.04 / 1.01 / 1.14 | 1.06 / 1.02 / 1.14 |
| 5     | 0.96 / 1.00 / 1.25 | 0.99 / 1.05 / 1.33 | 0.83 / 0.90 / 1.18 | 0.92 / 0.88 / 1.17 |

Count 5 holds 628 and 627 trades on the selection window, and 348 and 350 held out.

**The verdict needs three things on both roots in both windows, and it fails on the first.** The top count is 5.

- **(a)** It has a negative excess on both roots on the selection window, −0.042 and −0.054, and on MNQ held out, −0.073.
- **(b)** On NQ held out its excess is +0.037, but at 0.92 it sits well inside its null, whose 95th percentile is 1.17.
- **(c)** It also falls short of count 1's excess in every cell.

**Count 1 is the odd one out.** On the selection window it sits at its null. Held out it is the best on both roots: 1.43 and 1.39, above its null's 95th percentile. Read as description it is 330 to 343 trades in one window, and the verdict was written for the top count.

## The predictions

- **"`midline` holds on more than 90% of trades and `vwap` on more than 75%, on both roots and both sides." Half right.** `midline` holds on 96.6% to 97.6% in every root, side and window, and `vwap` on 59% to 70%.
- **"The rule's profit factor rises with the count in the full window on both roots." Wrong.** In the full window, both sides, count 1 has the highest profit factor on both roots, 1.13 and 1.09, and count 5 sits at 0.90 and 0.96 below count 4's 0.99 and 1.01. The win rate mostly rises with the count, from 32% to 33% at count 1 to 43% to 44% at count 5. The count picks winners more often but smaller ones.
- **"The verdict in (3) fails." Right.**

## What this settles, and what it does not

**It settles the earlier count's open question.** With conditions that share none of the entry's machinery, read at the last bar known when the order went in, the count still does not separate EmaCrossover from a random entry. The earlier count's verdict, that it sorts trades rather than adding edge, holds, and here it barely sorts them.

**It leaves count 1's held-out showing unexplained.** The trades on which only one condition held, usually the midline, did well held out and not on the selection window. Nothing here was set up to read that, and a result chosen after the fact is not a finding.

## How it was read

- **Run.** `campaign_confluence.py --out m59.parquet`, at its defaults: EmaCrossover's defaults, 5 minutes, both roots, the three windows and 200 draws.
- **Verdict.** The count table for both sides together, on the selection and held-out windows: the highest and lowest counts holding at least 30 trades, their excess over the null's median, and the top count's profit factor against the null's 95th percentile.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
