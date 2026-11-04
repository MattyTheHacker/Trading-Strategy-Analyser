---
title: "The November 2026 NT8 sim: 21 of 21 trades match, and one was skipped"
archetypes: [InsideBar, InsideBarTrailing]
issues: [350]
gates: []
outcome: mixed
verdict: >-
  Over three sessions on MNQ 12-26, all 21 sim trades match Strategy Analyzer and nqbt on their entry bar, none is extra, and every account was flat before every close. The whole-session account skipped one trade both backtests took, for a reason this data cannot settle, so #350's pass bar is not yet met. An exit order sent and cancelled on 4 November could misfire on a live account.
---

# The November 2026 NT8 sim: 21 of 21 trades match, and one was skipped ([#350])

## In plain terms

Three NT8 sim accounts traded MNQ 12-26 on 5-minute bars for three sessions, closing on 2, 3 and 4 November 2026. This was a trial of whether the strategies run and fill correctly, not the eight weeks #350 proposes, and it cannot measure profit.

**The strategies ran as the backtests say, with one open question.** All 21 sim trades match both NT8's Strategy Analyzer and nqbt on their entry bar, and no sim trade is extra. No account held past a close, and no order was rejected. But the whole-session account skipped a trade both backtests took, and the cause can't be told from what was saved. **Turn `TraceOrders` on next time**, which should settle it.

All times are UK (GMT). A bar is stamped at its close.

## What ran

| Account      | Strategy                         | EMA | Fast SMA | Slow SMA | Error margin | ATR length | ATR multiplier | Size | Entry window (ET) |
| ------------ | -------------------------------- | --- | -------- | -------- | ------------ | ---------- | -------------- | ---- | ----------------- |
| SimAccount1  | InsideBarTrailing, midday        | 44  | 20       | 125      | 0.05         | 14         | 10             | 6    | 10:30 to 14:00    |
| SimAccount12 | InsideBarTrailing, whole session | 44  | 20       | 125      | 0.05         | 14         | 10             | 6    | off               |
| Sim101       | InsideBar                        | 44  | 50       | 200      | 0.10         | 14         | 20             | 4    | off               |

InsideBarTrailing also ran a 0.6 partial take-profit and a trailing multiplier of 5, and InsideBar a target multiplier of 1. Strategies were enabled by 22:26 on 1 November and disabled at 22:02 on 4 November. The script sources on the sim machine and on the machine that ran Strategy Analyzer matched `ninjatrader-scripts` by hash.

## Against #350's pass bar

| Check                                                | Result                                                                                   |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Every sim trade matches by signal bar, none extra    | **Yes**, 21 of 21 against Strategy Analyzer and against nqbt                             |
| None missing, apart from logged outages              | **No**: one missing and unexplained, below                                               |
| Flat before the close on every session               | **Yes**. InsideBar flattened at 21:57:00 to 21:57:01, InsideBarTrailing at 21:59:30      |
| Price gaps averaging over one tick are explained     | **Mostly**: entries probably by the fill delay, flattens by their earlier time           |
| No entry outside the window                          | **Yes**, but its two entries, at 10:45 and 12:25 ET, did not test the edges              |
| No order left resting past its bar                   | **Yes**: all 33 entry orders were market orders, filled within 351 ms of the bar opening |
| No fault: errors, rejections, the strategy disabling | **None** in 791 order lines                                                              |

Ten connection drops were logged, the longest 2 seconds, none within a minute of an entry or exit. Early closes and the contract roll fell outside these dates.

## The trades

| Account       | Sim trades matched | Backtest trades not in the sim | Sim P&L    | Backtest P&L, same trades |
| ------------- | ------------------ | ------------------------------ | ---------- | ------------------------- |
| Midday        | 2 of 2             | none                           | −$1,199.00 | −$1,224.00                |
| Whole session | 10 of 10           | 1, at 21:20 on 4 November      | +$2,613.00 | +$2,675.00                |
| InsideBar     | 9 of 9             | 1, at 22:00 on 2 November      | +$1,753.50 | +$1,846.00                |

P&L is before commission, on both sides. Strategy Analyzer and nqbt agree with each other here, so the sim's comparison against each gave the same legs. The InsideBar trade at 22:00 is expected: the script's one-hour no-entry window reads the wall clock, so it blocks that entry live and not in Strategy Analyzer, and nqbt's sim configuration carries the window and matches the sim.

**Strategy Analyzer against nqbt, over the whole 26 October to 4 November run, is identical on every leg** at the settings it ran: midday 6 of 6, whole session 46 of 46, InsideBar 21 of 21. `reconcile_nt8.py` leaves out each run's first and last trade.

## The skipped trade

Strategy Analyzer and nqbt both enter long on the 21:15 signal bar on 4 November, at 28627.00, and flatten at the close for +$231.00. The whole-session account submitted nothing and was flat at the time. The last connection drop was at 19:27:17. There are two explanations and this data can't separate them:

1. **The live bars differed slightly from the server's.** On the server's bars the signal passes by little: the inside bar's low clears by 0.75 points, the close clears the break level by 0.80, and it is 1.65 above the EMA. A few ticks' difference would remove the signal. Live bars were not saved, so this can't be checked.
2. **The strategy could not enter after the exit below.** This was that account's first signal since the 18:46 exit. It placed no flatten order at 21:59:30, so it seems to have believed it was flat, which counts against a position it thought was still open but not against an entry NT8 ignored. An ignored entry would not appear in the log with `TraceOrders` off. The midday account had the same exit and no later signal to test it.

## An exit order that could misfire live

At 18:46:32 on 4 November, on both InsideBarTrailing accounts, the second lot's entry had filled in two parts, and because stops are placed per entry execution, it held two 1-lot trail stops. On the midday account:

| Time (ms past 18:46:32) | Event                                                                 |
| ----------------------- | --------------------------------------------------------------------- |
| 553                     | First trail stop fills, leaving 5 long, and `OnPositionUpdate` runs   |
| 561 and 567             | The trend exit sends market orders for 4 lots and for the other 1 lot |
| 574                     | Second trail stop fills, so that 1-lot order now has nothing to close |
| 673                     | The 4-lot order finishes filling, leaving the account flat            |
| 795                     | NT8 cancels the 1-lot order                                           |

The whole-session account did the same, 224 ms from sending the order to its cancel. **The sim cancelled it in time. Live, a market order could fill first and leave the account short 1 contract**, which this sim can't show, and what NT8 would then do has not been tested. A backtest fills an entry in one piece, holds one trail stop, and never reaches this. It is worth resolving before a live account.

## The price gaps

The backtests fill at the next bar's open with no slippage, so a gap here is the live fill against that open. These are simulated fills, which a live account may not reproduce.

| Price                     | Mean gap, ticks per leg              | Note                                                         |
| ------------------------- | ------------------------------------ | ------------------------------------------------------------ |
| Entries                   | 3.4 midday, 7.2 whole, 3.5 InsideBar | Per trade: median 2 worse, mean 3.2 worse                    |
| Stop exits                | 0.25                                 | The stop's level is fixed, not measured from the fill        |
| Target exits              | 0 midday, 8.1 whole, 3.4 InsideBar   | Targets are measured from the fill, so they follow the entry |
| InsideBar flatten         | 21.5, over 2 legs                    | 8.25 and 34.75 worse                                         |
| InsideBarTrailing flatten | 3.25, over 2 legs                    | One better, one worse                                        |

**Entries go both ways, from 5.6 ticks better to 36.6 worse.** The largest is 4 November's 01:05 entry on the whole-session account: price fell about 100 points in that minute, and Sim101's fill, 35 ms earlier, was 31 ticks better. Without that one the mean is 1.5 worse. Orders fill about 0.25 seconds after the bar opens (median 247 ms), and all 79 entry rows lie within the range of their bar's first minute, which fits price moving during the delay. There are no ticks to prove it. It is a real cost against the one tick assumed, though little of it reaches P&L where the target moves with the fill.

**InsideBar's flatten is a real difference and its sign is chance.** [§M41](m41-flatten-timing.md) recorded that nothing had measured a market order placed three minutes before the close, and these are the first two. Both were long while price rose into the close, which cost $86.00 of InsideBar's $92.50 P&L gap.

## Mismatches that are not problems

- **Exit reason, on 4 legs of 33.** The 4 November trade at 17:30 is filed differently on both InsideBarTrailing accounts: the sim's trade list puts the trail stop fills against `entry1`, where a backtest puts them against `entry2`. The exit prices differ by at most a tick and the whole trade's P&L by $9.00 and $3.50.
- **Exit bar, on 1 leg of 33.** A trail stop filled at 12:05:00.124 on 4 November, on the first tick of the next bar. The export drops the fraction, so it reads a bar early, as `tools/README.md` § "reconcile_sim.py" warns.

## The InsideBar Strategy Analyzer run's stop setting

**That run used `ATRMultiplier` 10, the script's default, where the sim used 20.** Its stop on 29 October filled at 29256.00, which fits 10 (29256.05) and not 20 (28867.60). All nine live stops fit 20 to within a tick. nqbt at 20 matches 20 of 21 legs, and at 10 matches all 21. No stop was hit in the sim's window, so nothing above changes, and the run was not repeated.

## Next time

**Run the next sim with `TraceOrders = true`.** Both scripts set it to `false` in `SetDefaults`, which is where NinjaTrader's documentation says to set it, so change it there and add the strategy afresh. It reports each order method the strategy calls and why NT8 ignores one, so it separates the skipped trade's two explanations: a trace of an ignored `EnterLong` means the second, and no trace at all means the signal never fired, the first.

**Its output goes to the NinjaScript Output window, not the Log tab or any export.** Keep that window open and save it before closing NT8.

## To repeat this

Each account against nqbt, or against its Strategy Analyzer run with `--analyzer` in place of `--bars`:

```bash
uv run tools/reconcile_sim.py <trades.csv> InsideBarTrailing-midday-2035 "MNQ 12-26" --from "2026-11-01 22:27" --to "2026-11-04 21:55" --bars <minute export> --month-first
```

The other two configurations are `InsideBarTrailing-2035` and `InsideBar-sim`. Strategy Analyzer against nqbt uses `tools/reconcile_nt8.py`, with `InsideBar-sim-analyzer` for InsideBar.

[#350]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/350
