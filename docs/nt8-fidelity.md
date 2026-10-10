# NT8 fidelity: what the simulation reproduces, and how it was established

Everything here was verified against real NinjaTrader 8 Strategy Analyzer runs — first a summary, then a full trade-list export of 1,208 [leg](../README.md#leg) exits on [MNQ](../README.md#nq-and-mnq) 03-24 for DeadCatBounce, and later a second export of 3,156 leg exits on the same contract for PullBackAndGo, which is what put the long side under the same scrutiny. Several of these rules are invisible in a summary and only surfaced from a trade list. They are recorded because rediscovering them is expensive and because getting any one of them wrong shifts results by more than any parameter does.

**Two rules below were found only by the long side**, having been unreachable from DeadCatBounce: gapped stop [fills](../README.md#fill), which its window happened not to contain, and stop-entry submittability, which its trigger cap makes structurally impossible. A single [archetype](../README.md#archetype) is not enough to establish fill semantics, and that is the general lesson of the second run.

## Reconciliation result

Window 2023-12-09 → 2024-03-08, MNQ 03-24 single contract, EMA 21 / SMA 60 / SMA 175, all six filters on, zero commission, zero slippage:

|                      | NT8     | nqbt          |
| -------------------- | ------- | ------------- |
| leg exits            | 1144    | 1144          |
| identical exit bar   | —       | 1142 (99.83%) |
| identical exit price | —       | 1143 (99.91%) |
| identical P&L        | —       | 1143 (99.91%) |
| net P&L              | −873.00 | −892.50       |

The whole residual is **one leg worth $19.50**: on 2024-03-08 18:28 NT8 exits S1–S3 at 18076.75 but holds S4 for two more [bars](../README.md#bar) and exits it at 18067.00, despite all four sharing one stop. Seen twice in the dataset, both times on S4. Presumed an artefact of `StopTargetHandling.PerEntryExecution`; not reproduced.

The comparison window deliberately excludes both ends:

- **2023-12-07/08** — NT8 warms indicators from bars before the backtest start that the export does not contain, so early signals differ. 11 NT8-only and 5 nqbt-only entries.
- **2024-03-11** — the export stops at 00:00 that day but NT8 backtested through 12:51, so it has 4 entries from bars we do not have.

Between those boundaries, **286 of 286 entries match with identical entry prices**.

## Reconciliation result — PullBackAndGo (the long side)

Window 2023-12-11 → 2024-03-15, MNQ 03-24 single contract, EMA 21 / SMA 60 / SMA 175 and both candle filters on, VWAP off, `OrderQuantity` 4, zero commission, zero slippage:

|                              | NT8   | nqbt               |
| ---------------------------- | ----- | ------------------ |
| trades                       | 418   | 416                |
| leg exits (joined)           | 1,664 | 1,664              |
| identical entry price        | —     | 1,664 (100%)       |
| identical exit price         | —     | 1,660 (99.76%)     |
| identical exit bar           | —     | 1,662 (99.88%)     |
| identical exit reason        | —     | 1,661 (99.82%)     |
| **identical on every field** | —     | **1,659 (99.70%)** |

The residual 5 legs are all ambiguous bars resolving the other way — the same class as DeadCatBounce's single leg, at a comparable rate. Nothing new is inferred from them.

**`PullBackAndGoParams`' defaults reproduce that [configuration](../README.md#configuration), not the NinjaScript's, because the NinjaScript does not have any.** `PullBackAndGo.cs` sets only `EmaPeriod`, `SlowSMAPeriod` and `FastSMAPeriod` in `SetDefaults`; `OrderQuantity` and all six toggles are left uninitialised, so in Strategy Analyzer they present as `0` and `false` until set by hand — and an `OrderQuantity` of 0 places four orders for nothing and trades nothing at all. The reconciled configuration is the only combination with a trade list behind it, so it is what the defaults reproduce. `use_vwap` stays off within it deliberately: nothing has checked nqbt's VWAP against NT8's `OrderFlowVWAP`, so switching it on would mix an unvalidated indicator into an otherwise validated archetype.

`PullBackAndGo.cs` also has no `TPMultiplier` and no `MaxRiskPerTrade`, so there is no target scaling and no risk cap to reject a signal with, and its trigger is a bare `High[0]` with no entry offset — which is what exposes it to the stop-entry submittability rule that DeadCatBounce's 2-tick cap makes unreachable. Matching the C# text means not inventing configurability it does not have.

**nqbt takes no trade NT8 did not.** The 2 NT8-only trades are at-market buy stops NT8 accepted and filled at the expected prices, against 86 otherwise identical signals it declined — see "A stop entry must sit beyond the market". They sit inside the declined group's distribution on body, range, wick, risk and volume, so no rule is inferred from n=2; a small bar revision between NT8's live database and the archive snapshot is the most economical explanation, and both are thin bars (43 and 195 contracts).

### Why the window is not the full contract

**NT8's series is back-adjusted-merged before ~2023-12-10** and the archive's per-contract file is not, so the two tiers are not looking at the same bars there and no amount of care in the simulation would reconcile them. The arithmetic is exact rather than inferred:

|                                  |                                                  |
| -------------------------------- | ------------------------------------------------ |
| NT8's first trade                | 2023-09-10 23:31, entry 15716.00                 |
| archive MNQ 03-24 at that minute | **no bar** — 135 sparse volume-1 prints that day |
| archive MNQ 12-23 at that minute | High 15518.50, **+210.75 = 15716.00**            |

405 of 789 entries match raw MNQ 03-24 to the tick and the earliest is 2023-12-10, which is NT8's configured rollover. Re-running from 2023-12-11 would cover the same trades this window already does, so it buys nothing; a *different*, fully liquid contract is the way to add legs. Both window ends are clean: the tail needs no exclusion because both sides stop at the same trade, 2024-03-15 10:21, with nothing after it on either side.

This is the merge caveat `CLAUDE.md` records for roll dates, arriving from the other direction — NT8 stitches contracts on a **configured** date, not an observed one.

## Reconciliation result — NQ, the second instrument (#66)

NQ had inherited its fill-semantics confidence from MNQ rather than earning it. It has now earned it. Window 2023-12-07 → 2024-03-10, `NQ 03-24` single contract, same configuration as the MNQ run above, zero commission, zero slippage, both ends excluded:

|                               | NT8   | nqbt               |
| ----------------------------- | ----- | ------------------ |
| legs in window                | 1,132 | 1,124              |
| joined on `(entry_time, leg)` | —     | 1,112              |
| identical entry price         | —     | 1,108 (99.64%)     |
| identical exit price          | —     | 1,107 (99.55%)     |
| identical exit time           | —     | 1,110 (99.82%)     |
| identical exit reason         | —     | 1,111 (99.91%)     |
| **identical on every field**  | —     | **1,105 (99.37%)** |

**No instrument-dependent behaviour was found**, which was the open question. The residual is two trades. One (2023-12-08 13:38, all four legs) is an entry-price difference — NT8 entered at 16151.50 against nqbt's 16148.25 — and is the only unexplained case here; it is one signal, not a pattern, and the other 285 entries in the window agree. The other (2024-01-03 15:01) is an ambiguous entry bar where NT8 filled **S1's target and stopped S2–S4 on the same bar**, which nqbt cannot express: its ambiguity policy resolves per trade, nearest-to-open, and resolved the whole trade to the stop. Same class as the residuals already recorded above, and the same rate.

## Reconciliation result — PullBackAndGo on a second contract (#92)

The long side was previously reconciled against one contract's post-merge tail. Window 2024-03-12 → 2024-06-14, `MNQ 06-24` single contract — fully liquid, and nearly 1,800 legs:

|                               | NT8   | nqbt                |
| ----------------------------- | ----- | ------------------- |
| legs in window                | 1,800 | 1,792               |
| joined on `(entry_time, leg)` | —     | 1,792 (0 nqbt-only) |
| identical entry price         | —     | **1,792 (100%)**    |
| identical exit price          | —     | 1,787 (99.72%)      |
| identical exit time           | —     | 1,786 (99.67%)      |
| identical exit reason         | —     | 1,791 (99.94%)      |
| **identical on every field**  | —     | **1,785 (99.61%)**  |

Every entry price agrees, on a contract that had never been tested. The residual 7 legs are dominated by the **L4 runner exiting later in NT8 than in nqbt**, which is the same `StopTargetHandling.PerEntryExecution` artefact recorded against S4 in the first reconciliation — the two runs now show it on both sides of the market, which makes it a property of NT8's per-entry handling rather than of either strategy.

This run is also what corrected the export-timezone rule; see "Sessions" below.

## Rules the simulation implements

### Entry orders are not GTC

`EnterShortStopMarket` under NT8's **managed** approach is cancelled at the close of the following bar if unfilled, despite `TimeInForce.Gtc` on the strategy. A signal at the close of bar `t` places an order live for bar `t+1` only.

Getting this wrong is the difference between an order that rests indefinitely and fills on an unrelated later bar, and one that gets a single chance.

**Why, established later by reflecting over `NinjaTrader.Core.dll`.** This is not a rule NT8 imposes on all strategies — it is the default of a parameter the short overload does not expose. The long-form overload carries it:

```csharp
EnterShortStopMarket(int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double stopPrice, string signalName)
```

`DeadCatBounce.cs:177-180` calls the three-argument form `EnterShortStopMarket(int quantity, double stopPrice, string signalName)`, so `isLiveUntilCancelled` is false and the managed approach auto-cancels at bar close. `NinjaTrader.Cbi.Order.IsLiveUntilCancelled` exposes the resulting state on a live order.

**`TimeInForce` and `isLiveUntilCancelled` are different layers**, which is why setting `TimeInForce.Gtc` on the strategy changed nothing. `NinjaTrader.Cbi.TimeInForce` (`Day, Gtc, Ioc, Opg, Gtd`) instructs the *exchange* how long to keep a working order; `isLiveUntilCancelled` governs whether *NT8* submits a cancel of its own at bar close. One does not imply the other.

The simulation reproduces the one-bar lifetime because that is what `DeadCatBounce.cs` does, and it stays that way. The generalisation to longer-lived orders — needed by future archetypes, and the three routes to it — is specified in [roadmap.md](roadmap.md) under "Order lifetime in NT8", and EmaPullback's confirmation entry (§M39) is the first loop to carry it. **Reflection established the API only; the behaviour was settled separately** by a probe rather than a trade list — when the cancel lands, whether Strategy Analyzer honours a resting order at all, and how one interacts with the session-close flat. See "Order lifetime and the session edge" below.

### Trigger is capped below the close

```csharp
double entryPrice = Math.Min(Low[0], Close[0] - (TickSize * 2));
```

Not simply the bar's low. An inverted hammer closes near its low by construction, so the close-based term binds on about **a third of signals** and drags the trigger 1–2 ticks under the low — enough to turn a marginal fill into no fill. Ignoring it produced 5% too many entries.

### Fill

On bar `t+1`: a gap through the trigger fills at the open, otherwise a trade down to the trigger fills at the trigger. No touch, no fill, order gone.

### A stop entry must sit beyond the market to be submitted

A stop-market order whose trigger is not strictly beyond the price it is submitted into is not a stop order, and NT8 declines it. The market at submission is the signal bar's close, `Calculate.OnBarClose` being what it is.

`PullBackAndGo.cs` triggers on a bare `High[0]`, so a bar that **closes on its high** asks for a buy stop at the market. This was the whole of the 86 trades nqbt took and NT8 did not: the signal bar closed on its high in **86 of 86** of them, against **2 of 416** among the trades NT8 did take. `High == Close` on 24.8% of all MNQ 03-24 bars.

**DeadCatBounce cannot reach this**, which is why the first reconciliation never saw it. Its `min(Low[0], Close[0] − 2 ticks)` cap binds on exactly the bars that would otherwise be unsubmittable and puts the trigger two ticks under the close: **0 of 132,454 bars** carry a DeadCatBounce trigger at or above its close. The cap recorded above as a fill-rate detail turns out to also be what makes the short archetype structurally immune.

### A stop fills at the open when the bar gaps through it

A stop is a market order once triggered, so a bar that opens past it offers no trade at the stop level and the fill is the first price there is. Filling at the stop price regardless was worth **$222.50 of a $292.50 result** over the 1,664 reconciled legs; NT8's exit price equals the exit bar's open on **115 of the 116** disagreeing stop fills.

Traced at 2023-12-11 09:15: the ratchet reaches 16288.25 and the 09:18 bar opens at 16287.00, already through it. NT8 fills 16287.00, nqbt filled 16288.25.

**The rule does not apply on the entry bar.** The position did not exist at that bar's open, so an open beyond the initial stop says nothing — price still had to travel through the trigger to open the position at all, and only then could it come back to the stop, which it reaches at the stop's own price.

This one is not long-specific: it moved 56 of 1,380 legs on the pinned MNQ 03-24 DeadCatBounce capture, always to a worse fill and never a better one. It survived the first reconciliation because **none of those legs fall inside that run's 1,168-leg window** — all 1,168 still match on every field. A reconciliation window is evidence about the bars it contains and nothing else.

### Limit orders must trade *through*, not touch

`IsFillLimitOnTouch = false` — set in `SetDefaults` and unchecked in the Strategy Analyzer. A profit target needs `low < target`, not `low <= target`.

Verified decisively: **all 15** initial target-fill disagreements were bars whose low equalled the target to the tick. Stops are unaffected — a stop becomes a market order on touch.

### A limit order the market has passed fills at the nearest price the bar traded

**A limit order fills at its own price if its fill bar traded there, and otherwise at that bar's low for a sell limit or its high for a buy limit.** That is the price nearest the limit that the bar traded. It holds for a profit target and a limit entry alike, and for every way the market passes one: a target behind the entry's fill because the entry bar opened past it (#452), a resting target or limit entry a later bar opens beyond (#244, #454), and a limit entry sent on the wrong side of the market (#454). It is not the gapped-stop rule above: a limit fills at the open only where the open is that extreme.

Measured by `NqbtPassedTargetProbe.cs`, which places each order past the market on purpose, because no reconciled trade list holds the case. Four runs over `MNQ 03-24`, 1 minute, 2023-12-12 → 2024-03-15 (scenarios 1 and 2 from the 13th), Standard fill resolution, zero costs, 5,000 trials each, alternating long and short. The outputs are machine-local in `verification/` (#91), and `tools/reconcile_passed_target.py` reads them:

| case                                            | fills | at the limit | at the bar's low or high | at the open | elsewhere |
| ----------------------------------------------- | ----- | ------------ | ------------------------ | ----------- | --------- |
| target behind the entry's fill (scenario 1)     | 4,982 | 2,990        | 1,992                    | 0           | 0         |
| resting target a bar gapped (scenario 2)        | 638   | 550          | 88                       | 0           | 0         |
| control: the bar opens short of the target      | 4,359 | 4,359        | 0                        | 0           | 0         |
| limit entry a bar gapped (scenario 3)           | 512   | 452          | 60                       | 0           | 0         |
| control: the bar trades to the limit entry      | 3,320 | 3,320        | 0                        | 0           | 0         |
| limit entry sent on the wrong side (scenario 4) | 4,998 | 2,904        | 2,094                    | 0           | 0         |

All four runs' Trades exports match the probe's own log on every trade's entry and exit price. NinjaTrader rejected none of the 9,982 passed targets and marketable limit entries it was sent, and filled each on the first bar it could. **An entry limit has to trade through, as a target does:** of the 534 resting limit entries whose bar only touched the limit, none filled, and the two marketable entries left unfilled were one more touch and one bar that never reached the limit.

**What it replaced.** `bracket.py` filled every target at its own price. Wherever the bar lay wholly past the target, that booked a price the bar never traded, worse than the one NinjaTrader gives. ElasticBand alone closed such a leg at the entry bar's open (#451), which was right only where the open was the bar's extreme. Every leg the change moved on the trade-log gate's captures was a target exit, almost all in the thin bars before `MNQ 03-24`'s December roll, and the five stored reconciliations are unchanged because none of their windows holds such a bar.

OpeningRange's two limit entries filled a gapped limit at the open until #454, and now fill by this rule through `bracket.limit_fill_price`, the one implementation. Every retest and rejection result written before #454 was measured under the old fill, so a re-run moves each gapped entry to a worse price. A limit entry that gaps past its own stop as well still exits at a stop price outside the bar, which is #455. NinjaTrader accepting a marketable limit entry does not change which of their entries are sent, because not sending one is the archetype's own rule — §M28.2. The probe places no stop, so a bar that takes both a passed target and the stop still falls to "Ambiguous bars resolve to whichever level is nearer the open" below.

### Ambiguous bars resolve to whichever level is nearer the open

When a bar contains both the stop and a target, bar-close OHLC cannot say which came first. NT8 fills the level nearer the bar's **open**, and when the target goes first the stop still takes the remaining legs *within the same bar*.

| bar              | dist to target | dist to stop | NT8 filled |
| ---------------- | -------------- | ------------ | ---------- |
| 2023-12-19 06:29 | 0.00           | 1.00         | target     |
| 2024-01-11 16:11 | 0.50           | 6.25         | target     |
| 2024-01-30 13:51 | 1.75           | 2.75         | target     |
| 2024-02-12 14:26 | 1.75           | 2.00         | target     |
| 2024-02-28 18:07 | 2.50           | 4.00         | target     |
| 2024-01-03 08:41 | 1.75           | **1.50**     | **stop**   |
| 2024-01-16 00:31 | 4.25           | **0.75**     | **stop**   |

7 of 7. A bar-direction rule (up bar ⇒ Open→Low→High→Close) fits only 5 of 7 — all seven bars are up bars, and the two NT8 stopped out are the ones where the stop was nearer.

`ambiguity_policy` exposes this: `1` reproduces NT8 (default), `0` assumes a blanket worst case and `2` a blanket best case. Worst case is *more* pessimistic than NT8, not equal to it — a distinction that was originally stated backwards in this project and corrected only by the trade list. `0` and `2` are the two ends of the band and are never ranked on; they exist so that `nqbt/disambiguate.py` has both outcomes to select between.

**The seven bars above contain no same-bar limit entry, and that is where the rule stops being fitted.** All seven are exits from a position opened on an earlier bar, so the bar's open is also the price the trade was live from. On an entry that fills *inside* the ambiguous bar the two come apart, and measuring distance from the bar's open then asks a question the trade list never answered. Measured against the minute bars on OpeningRange's retest — the registry's only limit entry — the rule was wrong on every bar that could be settled: `docs/roadmap.md` §M28.4. That is a limit on the rule's reach, not a contradiction of the trade list, and NT8 will still fill those bars its own way.

**The sign of the error is set by the entry mechanism, and both signs have now been measured.** Run over one configuration at an `ambiguous_share` near 0.9, OpeningRange's fade returns a [profit factor](../README.md#profit-factor) of 0.016 under this rule against 0.012 at the blanket worst case and 2.171 at the blanket best case; its rejection returns 57.953 against 0.274 and 71.654. **Neither sits in the middle of its band — each sits on an opposite end of it.** A stop entry fills as price comes back through the level, so the bar's open lies beyond the fill on the stop's side and the rule books the stop; a limit entry fills as price comes to it, so the open lies on the target's side and the rule books the target. Where an archetype's [bracket](../README.md#bracket) is narrow enough for this to reach most of its legs, the resulting profit factor is a measurement of the assumption rather than of the strategy: [roadmap.md](roadmap.md) §M28.7.

The 2024-01-11 16:11 bar is the clearest evidence: NT8 filled S1's target at 16836.00 **and** stopped S2/S3/S4 at 16842.75 on that one bar.

### Ratchet reads the just-closed bar

```csharp
double newStop = High[0] + (TickSize * 2);   // not High[1]
if (previousStop < newStop) return;          // never loosens
```

The stop set at the close of bar `i` is live during bar `i+1`. `ratchet_lag` exposes the older `High[1]` variant, which holds trades roughly a third longer (2.12 vs 1.65 average bars) and behaves like a genuinely different strategy.

**`PullBackAndGo.cs` ratchets to `Low[1]`, not `Low[0]`** — lag 1, the bar *before* the just-closed one. The trade list settles it: lag 1 leaves 120 disagreeing legs of 1,664, where lags 0, 2 and 3 each leave around 1,100.

**The ratchet's offset is separate from the entry stop's**, which is why `ratchet_offset_ticks` exists beside `stop_offset_ticks`. DeadCatBounce ratchets to `High[0] + TickSize * 2`, reapplying its entry offset; PullBackAndGo ratchets to `Low[1] - TickSize * 2`. Because `ratchet_lag = 1` puts the first evaluation on the *signal* bar itself, the offset makes that first ratchet reduce to exactly the initial stop and therefore a no-op — a bare `Low[1]` instead tightened the stop by two ticks before any bar had closed with the position open.

### Targets snap to the tick grid — even when the C# does not ask for it

`RoundToTickSize` in `DeadCatBounce.cs`. A 1.5× multiple of an odd tick count otherwise lands on a half tick, which no exchange accepts.

**`PullBackAndGo.cs` never calls it, and NT8 snaps the targets anyway.** The port originally took the C# at its word and left them un-rounded, on the reasoning that matching the text beats assuming symmetry; the trade list settled it the other way. Rounding took the reconciliation from 176 to 120 disagreeing legs, and the discriminating case is a half-tick target that nqbt placed at 16504.375 and NT8 filled at 16504.50.

So the snap is the platform's, not the script's, and `round_targets` should be true for any archetype — it is a property of what an exchange will accept, which no NinjaScript can opt out of.

**And it is not only targets.** An exchange takes a stop at a half tick no more than a limit, so a stop has to be snapped too. Both stop-market ports place theirs at a bar extreme plus a whole number of ticks, so they land on the grid by construction and could not reach this; InsideBar's `Low[1] − ATRMultiplier × ATR` misses it on nearly every trade. The snap goes on before the risk is taken, so the submittability test and every `r_multiple` measure the stop that was actually submitted. **`EmaCrossover`'s ATR stop has the same shape and is not yet snapped** — it is `TIER1_ONLY` with no C# to reconcile against, so it is recorded here rather than fixed alongside.

### The entry filters' equality boundaries, which do not mirror each other

Every filter is ported as the **negation of the C#'s rejection**, not as the positive form someone would write from the description. The two differ exactly at equality, and the boundaries are not symmetric between the two archetypes.

| filter             | the C# rejects on     | so equality                 | in `conditions.py`               |
| ------------------ | --------------------- | --------------------------- | -------------------------------- |
| downtrend gate     | `Close[0] > ma[0]`    | **passes**                  | `below_series` = `~(close > ma)` |
| uptrend gate       | `Close[0] < ma[0]`    | **passes**                  | `above_series` = `~(close < ma)` |
| previous bar green | `Close[1] < Open[1]`  | **passes** (doji is green)  | `_previous_bar_green` = `>=`     |
| previous bar red   | `Close[1] >= Open[1]` | **fails** (doji is not red) | `_previous_bar_red` = `<`        |

**`above_series` is not `~below_series`.** Each strategy's own C# chose to treat its own boundary as a pass, independently, so the two *overlap* at `close == ma` rather than partitioning it. Writing either as the positive comparison would silently drop those bars.

**The doji boundary is the one place the two archetypes genuinely do not mirror.** `previous_bar_green` admits a doji-closed prior bar and `previous_bar_red` rejects one, which makes the pair exact complements rather than a pair overlapping at equality. `PullBackAndGo.cs` used to read `Close[1] > Open[1]` there, which *did* make them symmetric, and the port followed it; the strictening cost **103 of 760 signals on MNQ 03-24 — 13.6%**. Check the operator rather than assuming the mirror holds.

**Both candlestick patterns require `body > 0`, so a doji never qualifies** however long its wick — with a zero body the "wick at least twice the body" test is trivially satisfied. `_inverted_hammer` (`DeadCatBounce.cs`) wants the upper wick ≥ 2× body and the lower wick ≤ body; `_hammer` (`PullBackAndGo.cs`) is the same with the wick roles swapped.

### Max risk is in ticks, not dollars

```csharp
if (risk > maxRiskPerTrade * TickSize) return;
```

`MaxRiskPerTrade = 250` means 250 ticks = 62.5 MNQ points, **not** $250. It never binds at that default — the largest observed risk is 24.25 points.

**So one setting is a different dollar cap on each contract.** NQ and MNQ share a tick size and not a tick value, so 250 ticks is $125 a contract on MNQ and $1,250 on NQ. The port keeps the cap in ticks because the C# does.

### The reward-to-risk gate has no NinjaScript behind it

`min_reward_risk` is an optional pre-trade gate from the original build spec (#315): skip a signal unless its reward-to-risk clears a minimum. **It exists on DeadCatBounce alone and is off at `0`.** Neither `DeadCatBounce.cs` nor `PullBackAndGo.cs` has a property for it, PullBackAndGo's loop passes `0` unconditionally, and no [campaign](../README.md#campaign) in `tools/` sets it. `DeadCatParams` refuses a minimum that is negative, `nan` or infinite.

**It filters rule sets, not trades.** Every target is an R multiple, so the ratio is fixed by the parameters before a bar is read: `bracket.passes_reward_risk` compares the furthest finite entry of `target_r_multiples`, scaled by `tp_multiplier`, with the minimum, and either every signal passes or none does. A port would write it as a property compared against that multiple, returning early beside the risk cap above.

**It reads the multiples after `tp_multiplier` scales them**, because the targets it gates sit at `target_r × tp_multiplier`. At `tp_multiplier = 2` the default targets sit at 2, 3 and 4R, so a minimum of 4 passes and 4.5 blocks. It read the unscaled multiples until #373, which nothing stored could see, since the gate is off everywhere.

**It reads the multiple before the target is rounded to the tick**, so a placed target can sit just short of the minimum it passed: a short's 2.5R target at a risk of 4.25 points rounds from 10.625 to 10.5 points, about 2.47R. That is kept, because a port comparing the multiple would do the same, and gating on the placed price would make it a filter on trades.

**A minimum equal to the furthest scaled target passes**, even where the product rounds just below it: `1.5 × 1.4` is `2.0999999999999996`, which a bare `>=` against 2.1 would block. `bracket.REWARD_RISK_TOLERANCE` absorbs that rounding as a fraction of the minimum, so a rule set with no finite target still fails any positive minimum, and a port would compare with the same tolerance.

**Every params class refuses a `tp_multiplier` that is not finite and above zero**, and a port whose NinjaScript has a `TPMultiplier` refuses one below its `Range` floor: 1 on `DeadCatBounce.cs` and 0.1 on `InsideBar.cs`. InsideBarTrailing inherits the field and not the floor, because `InsideBarTrailing.cs` has no such property. `types.validate_tp_multiplier` is the one check.

### M18 — the crossover rules, and that none of them has evidence yet

`EmaCrossover` is the first archetype with **no NinjaScript**, so nothing below is backed by a trade list. It is recorded here anyway, because the point of writing the rules down before there is a C# is that the port has something to be checked *against* — and because the prime directive binds during development. A rule chosen here that NT8 cannot express makes the archetype unreconcilable later, which wastes the exploration rather than merely leaving it unvalidated. Each item below therefore names the NinjaScript it would be written as.

`Archetype.tier2` is `TIER1_ONLY`, and it reaches the results table so a ranking cannot put these rules beside the reconciled ones without saying which is which.

**`CrossAbove(a, b, n)` is a window, not a bar.** NinjaScript asks whether the cross happened within the last `n` bars, so the naive form

```python
fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
```

is the `n = 1` case and not the definition. `conditions.cross_above` implements the window, with `n` [swept](../README.md#sweep) via `cross_lookback`. Equality is resolved on the *prior* bar (`<=`), so two series that touch and then separate upward have crossed — vanishingly unlikely for EMAs and entirely reachable for SMAs of tick-grid prices, which is why the boundary is pinned rather than left to whichever operator got typed.

**The entry is market-on-next-open, and it is unconditional.** `EnterLong()` / `EnterShort()` under `Calculate.OnBarClose` submit a market order at the close of bar `i`, which NT8 fills at the open of bar `i+1`. There is no trigger price, so no "no touch, no fill" and no submittability rule — the two things that shape every DeadCatBounce entry do not apply. What does apply is the [flatten](../README.md#forced-flat) point: a bar at or past the cutoff cancels the order rather than filling it, exactly as it cancels a resting stop-market entry.

**The signal exit fills at the next bar's open too**, and takes precedence over the stop and the targets on that bar. Both follow from it being a market order: it is filled at the bar's first price, and NT8's managed approach cancels a position's brackets when something else flattens it. This is the only place `EXIT_SIGNAL` is produced.

**The protective stop has no structural anchor.** A crossover has no signal wick, so the default is an ATR multiple hung off the fill — planned risk is then exactly `atr * multiple` — read from the ATR at the **signal** bar, the last completed one. The alternative mode is the adverse extreme of the last `swing_lookback` completed bars plus the usual two ticks, which is the closest thing to DeadCatBounce's stop. Both are swept.

**The ATR stop has a hard floor in dollars per contract**, off at `0`. A quiet regime otherwise sizes a bracket smaller than the round trip costs to trade, and `min_bracket_dollars` is what stops it: the stop distance is `Math.Max(atr * multiple, floor / pointValue)`. It is expressible — `Instrument.MasterInstrument.PointValue` is the conversion, so a port writes the property in dollars and divides, exactly as `nqbt` does through `Instrument.dollars_to_points`. It applies to the ATR mode only; the swing mode's stop is a structural level rather than a distance. Reasoning and the effect on R: [roadmap.md](roadmap.md) § "ATR-multiple brackets and the dollar floor".

**An entry whose stop would sit at or through its own fill is skipped.** This is the existing "a stop entry at or through the market is never submitted" rule applied to the protective stop, and it is reachable here for the same reason the entry rule became reachable with PullBackAndGo: the fill is wherever the next bar opens rather than at a trigger the stop was placed against, so a gap can put the swing reference on the wrong side.

**Flat between trades, not stop-and-reverse.** The classic crossover reverses in a single order. Here the flip closes the position and opens the new one as two fills at the same open price, each paying its own slippage and commission and each appearing as its own trade in the log. That is a real difference from published crossover results and from what `EnterShort()` while long would do in NT8, and it is the one item on this list that a port would have to be written *around* rather than to.

**`r_multiple` means something different.** R is `stop - entry`, so with an ATR stop the four-leg scale-out is volatility-scaled rather than structure-scaled. Crossover results are **not comparable to DeadCatBounce results at the same R numbers** — the same trap as comparing profit factor across bar [resolutions](../README.md#resolution). Where the dollar floor binds it is neither: R is then dollar-scaled and the same on every ATR multiple in the sweep.

### The build spec's three loose ends: the trail, the round number and the count (#74)

Three build-spec features, all on EmaCrossover, and like the rest of M18 none of them has a trade list behind it. Each is recorded with the NinjaScript it would be written as, and each is **off in every default**, so nothing above changes.

**The moving-average trailing stop is a ratchet, not a second placement.** `SetStopLoss` is re-issued at the close of every completed bar with `ma[0] - direction * cushion`, and only when that is nearer the market than the stop already resting; NinjaScript expresses it exactly as the existing ratchet does, `if (thisStop > curStop) curStop = thisStop`, over a different level. The average is read at bar `[0]` under `Calculate.OnBarClose`, which is the just-closed bar and the same lag the ratchet already has — a trail reading an average that includes the bar it is protecting against is the lookahead this archetype exists to be able to fail. It advances at one cadence, not InsideBarTrailing's two: that one has C# behind it and this one does not, so it takes the cadence the codebase has evidence for.

**A stop landing exactly on a round number is pushed away from the entry.** In NinjaScript, `if (Math.Abs(stop % spacing) < TickSize / 2) stop -= direction * offset * TickSize` before the `SetStopLoss` call — expressible, and cheap. What NT8 cannot help with is that the rule is **only meaningful on prices that traded**: a Strategy Analyzer run on a `MergeBackAdjusted` continuous series shifts every historical level, so the port has to be validated on a single contract. That is the same constraint that makes a per-contract window the cheapest [Tier-2](../README.md#tier-1-and-tier-2) reproduction (#31), and it is why `context.PriceBasis` refuses the rule on anything it has not been told is raw.

**"At least N of M filters" is a count, and the M is the filters the rule set switched on.** NinjaScript would write it as the sum of the active gates against a `ConfluenceRequired` property, which is what `conditions.count_true` computes here. The one thing a port must not do is enter an inactive gate as `true`: each of these gates passes no mask on a bar it cannot label — a warm-up bar, a session with no volume baseline — so an inactive gate counted as satisfied changes the answer on exactly those bars. Every archetype but this one leaves `confluence_required` at `REQUIRE_ALL`, where the count and the conjunction are the same expression.

### M19.2 — the squeeze-breakout rules, written before the Python (#51)

**Written down before the Python existed and the Python written to it**, as §M28 was. There is no NinjaScript, so nothing here is backed by a trade list, and each item names the NinjaScript it would be written as. The reasoning and the alternatives rejected are in [`m19-2-squeeze-breakout-spec.md`](findings/m19-2-squeeze-breakout-spec.md); only the rules are here.

`Archetype.tier2` is `TIER1_ONLY`, and stays there until a trade list has been diffed against it.

**The width is one of §M19.1's two forms, and every indicator behind them is already pinned or trivial.** Bandwidth is two standard deviations over the moving average — Bollinger's width over its middle up to a constant factor no rank can see — and `StdDev` and `SMA` are both pinned at M16; range-to-ATR is the window's range over an `ATR` of the same length, which is pinned, and `MAX` and `MIN` are a comparison each:

```csharp
double bandwidth  = 2 * StdDev(Close, Period)[0] / SMA(Close, Period)[0];
double rangeToAtr = (MAX(High, Period)[0] - MIN(Low, Period)[0]) / ATR(Period)[0];
```

**The rank is a loop over a `Series<double>`, and it never reads the bar it ranks:**

```csharp
double below = 0;
for (int k = 1; k <= BaselineBars; k++)
    below += width[k] < width[0] ? 1.0 : width[k] == width[0] ? 0.5 : 0.0;
bool squeezed = below / BaselineBars < SqueezeBelow;
```

evaluated only once `BaselineBars` measured widths sit behind the bar. **Strictly below**, so a rank exactly at the threshold is not a squeeze, which is `Compression.COMPRESSED`'s boundary.

**The duration is a bar counter.** `squeezedBars = squeezed ? squeezedBars + 1 : 0;`, compared against `MinSqueezeBars` on the same bar.

**The order is a one-bar stop, resubmitted at the window's current extreme**, under `Calculate.OnBarClose` on every bar the squeeze holds:

```csharp
if (squeezedBars >= MinSqueezeBars)
    EnterLongStopMarket(MAX(High, Period)[0] + EntryOffsetTicks * TickSize);
```

The three-argument overload, so each order lives for the next bar only (§ "Order lifetime and the session edge"), and the trigger is re-read at every close, so a level that moves as the window rolls is followed. **This is not route 3**, whose trigger is unchanged between submissions, and it needs no `isLiveUntilCancelled` order.

**§M18's refusal applies unchanged.** A stop entry at or through the close is never submitted, so a bar closing on its own window's high cannot submit at `EntryOffsetTicks = 0`; the default is 1, as it is for §M28.

**The fill, the bracket and the targets are §M28's, read against the window.** The fill test is DeadCatBounce's. The bracket is computed from the trigger — the window's other extreme less `StopOffsetTicks` for the opposite-extreme stop, the stop fraction of `MAX - MIN` back from the broken extreme, or the floored ATR distance from the trigger, each set with `SetStopLoss(CalculationMode.Price, …)` — and the targets are the R ladder or multiples of the window's width. All of it is issued in the `OnBarUpdate` that submits the entry, so every level is the signal bar's.

**A window that has not filled has no level.** No order is submitted while `CurrentBar < Period - 1`. NinjaTrader's own `MAX` would read the bars there are, so the two can disagree only before bar `Period - 1` — which `BarsRequiredToTrade` at its default of 200 excludes for every period the campaign grid sweeps.

**One side per instance, because the managed approach allows no other.** The classic squeeze entry is both stops live with the first fill winning, and NinjaTrader ignores whichever of two opposite entries is submitted second, re-issued every bar or not — "The managed approach refuses the opposite-direction submission outright" below. `direction` is a swept [axis](../README.md#axis) and no combination ever holds two orders; a two-sided squeeze would have to be written unmanaged.

**No per-session cap and no break flag.** A break usually widens the window out of the squeeze, so the order stops being resubmitted without a counter. A resting order is tested for a fill on the force-flat bar and `BlockEntryAtSessionClose` guards a new one there, as for every archetype.

### M22 — the InsideBar rules

`InsideBar.cs` exists, so unlike M18 every rule below is a reading of real C#, and every one has now been diffed against a Strategy Analyzer trade list — "Reconciliation result — InsideBar" below. It earned its place on what it reaches rather than on what it might make: three parts of the fill model no other archetype touches, and `bracket.py` inherits whatever is wrong in them. Two of the three rules the port had to infer turned out to be wrong, which is the argument for reconciling each archetype rather than trusting the shared engine because the first one passed.

**The entry is M18's market-on-next-open.** `EnterLong(0, OrderQuantity, "entry")` under `Calculate.OnBarClose`, so there is no trigger price, no "no touch, no fill" and no submittability test on the entry itself. A bar at or past the flatten cutoff cancels the order rather than filling it.

**The signal reads two bars back, and both bounds are strict.** The inside bar is `[1]` and its mother bar is `[2]`, so `High[1] < High[2] && Low[1] > Low[2]` — a bar equalling either extreme of its predecessor is not inside it. The break is judged on `Close[0]` against the **mother** bar's extreme plus `ErrorMargin` of the mother bar's *range*, never against the inside bar's own high or low.

**The three moving-average gates are strict, and do not mirror the two ports.** `InsideBar.cs` writes the positive form — `Close[0] > ema[0] && Close[0] > smaFast[0] && Close[0] > smaSlow[0]` — where both ports write the negation of a rejection. So equality **fails** here and **passes** there, which is a third pattern for the table under "The entry filters' equality boundaries". The shared boolean grid holds `above` as `~(close < ma)`, so it is the wrong boundary for this archetype and `insidebar_trends` reads the raw values instead. That is what `needs_ma_values` costs, and why it is on.

**`BarsRequiredToTrade` costs one bar more here than in either port.** `CurrentBars[0] <= BarsRequiredToTrade` returns, against `CurrentBar < BarsRequiredToTrade` in both others. An off-by-one in warm-up is invisible in aggregate, so it is pinned by a test rather than assumed to mirror them.

**`IsFillLimitOnTouch = true`, and this is the archetype that finally checked it.** Set in `SetDefaults`, against `false` on both ports, so a profit target fills on `low <= target` rather than needing `low < target`. `fill_limit_on_touch` had been a sweepable axis all along and no archetype's defaults reached the `true` side of it, so the rule recorded under "Limit orders must trade *through*, not touch" was evidence about the `false` branch only. Both branches now have a trade list behind them.

**The bracket is computed in `OnExecutionUpdate`, from the fill, with two different anchors.**

```csharp
double atr    = ATR(ATRLength)[0];
double stop   = Low[1] - ATRMultiplier * atr;   // long
double target = price + TPMultiplier * atr;     // `price` is the actual fill
```

Both ports place a bracket against a *trigger* the fill is defined relative to. Here the target hangs off the **fill** and the stop off a bar's adverse extreme, which is two anchors in one bracket. The stop never moves afterwards: there is no ratchet, and `SetStopLoss`'s third argument is `isSimulatedStop`, not a trailing flag.

**`OnExecutionUpdate` runs with the *signal* bar still current**, not the fill bar. So `[0]` is the signal bar and `Low[1]` is the bar before it — the **inside** bar. The port originally had both terms one bar later, reasoning that the fill lands on the next bar's open so the series must have advanced by then. The trade list settled it the other way on both, decisively:

| candidate                                                   | reproduces NT8             |
| ----------------------------------------------------------- | -------------------------- |
| stop from the inside bar `[1]` × the signal bar's ATR `[0]` | **100%** of stop exits     |
| stop from the signal bar × the signal bar's ATR             | 0%                         |
| stop from the fill bar × the fill bar's ATR                 | 0%                         |
| target from the signal bar's ATR                            | **99.75%** of target exits |
| target from the fill bar's ATR                              | 19%                        |

The correct reading is also the one that reads **no bar the fill could not have seen**, which removes the open question the port shipped with. It is a warning about the general case: `[0]` inside `OnExecutionUpdate` is not the execution's bar, and any future archetype that brackets from there inherits this indexing.

**The target takes a multiplier of its own** (#197). The C# wrote `price + atr` with nothing in front of the ATR, so a sweep could move the stop across `ATRMultiplier` and not move the target by a tick — and the target is the half `docs/findings/m27-registry-campaign.md` § "Gate 4 — what stops it is the bracket, not the entry" puts the archetype's failure on. `TPMultiplier` scales that ATR target and nothing else; the stop keeps its own multiple. **Its default is `1.0`, which is exactly what the hardcoded target was**, so this reconciliation and every stored result reproduce unchanged. **A Tier 2 run at any other value needs `TPMultiplier` in `InsideBar.cs` first**: a Strategy Analyzer run of a script with no such property measures the 1x target whatever the Python was set to, and the two tiers then disagree on a parameter one of them does not have. `InsideBarTrailing.cs` hardcodes its bracketed lot's target the same way, so §M23 carries the same condition.

**The geometry is lopsided at the defaults, by design.** `ATRLength = 3` with `ATRMultiplier = 10.0` puts the target 1x ATR(3) from the fill and the stop 10x ATR(3) beyond the inside bar — a high-win-rate, rare-large-loss profile whose R multiples cluster just above zero. `r_multiple` uses planned risk, so **these R numbers are not comparable to another archetype's at the same value**, with more force than the same caveat carries for an ATR stop generally. And 1x ATR(3) on a quiet bar is a target that can be smaller than the round-trip commission, which no ranking will announce.

**The stop is snapped to the tick grid, not just the target.** An ATR multiple lands off the grid where both ports' whole-tick offsets cannot — see "Targets snap to the tick grid", which this archetype is the first to reach the stop half of.

**`ExitOnSessionCloseSeconds = 180` changes nothing, and the port must not act on it.** `InsideBar.cs` sets 180 where both ports set 30, which should put the flatten at 16:57:00 ET rather than on the session's last bar. It does not: NT8 flattened at 17:00 on every one of the eleven session-close exits in the reconciliation window, and honouring the 180 in the simulation *lowered* agreement from 99.64% to 98.42%. Whether the Strategy Analyzer resets the property or historical flattening is simply per-bar, a trade list cannot tell apart — the observable is that **a backtest flattens on the session's last bar**, which `exit_on_close_seconds=30` reproduces for every archetype at any bar resolution below a minute. The property was briefly carried per archetype and that was a regression; it is one default again, and `sessions.EXIT_ON_CLOSE_SECONDS` is where it lives. **Live it is not inert, and what that divergence costs is measured rather than argued** — at 5-minute bars the 180 and the 30 select the identical mask, so it is zero at the bar size both go-live candidates run at: [`docs/findings/m41-flatten-timing.md`](findings/m41-flatten-timing.md).

**Every property is initialised.** Unlike `PullBackAndGo.cs`, this `SetDefaults` sets every declared property, so `InsideBarParams`'s defaults are the NinjaScript's directly rather than a reconciled configuration.

**What a reconciliation of it has to hold fixed.** The no-entry window has to be off on *both* sides — `no_entry_minutes_before_close=0` here, and the Strategy Analyzer run started outside 16:00–17:00 ET so the C#'s wall-clock test cannot fire — because that is the only configuration in which the two are testing the same strategy. `tools/reconcile_nt8.py`'s `CONFIGS["InsideBar"]` is that configuration. Everything else is `SetDefaults` unchanged.

### The position guard has to read `Position`, not `PositionAccount`

```csharp
if (PositionAccount.MarketPosition != MarketPosition.Flat) return;   // never fires
if (Position.MarketPosition != MarketPosition.Flat) return;          // what it meant
```

`PositionAccount` is the **account** position, and in a Strategy Analyzer backtest it never leaves `Flat`. So the guard never fired, `EnterLong()`/`EnterShort()` reached the managed approach while a position was open, and NT8 **reversed**: `EntriesPerDirection = 1` blocks a second entry on the same side, but an opposite-side entry closes the position and opens the new one in a single transaction.

The first export made it unmissable — **2,581 of 21,884 trades exited as `Close position`, and every one handed straight over to an opposite-side entry at the same timestamp and the same price**, where no other exit type did. NT8 took 1,262 trades in the reconciliation window to the port's 956, and 96.7% of the port's entries were NT8 entries: the port was not inventing trades, it was missing the ones NT8 took while already in a position.

`InsideBar.cs` now reads `Position` and the reversals are gone — zero `Close position` exits in the second export. **This is the second property in this one script that behaves differently in Strategy Analyzer from what its author assumed**, alongside the wall-clock `Now` below, and it is the reason a port is not evidence about anything until a trade list has been diffed against it. `InsideBarTrailing.cs` is immune: it guards on `Position` as well, behind an `IgnoreAccountPosition` toggle.

### Reconciliation result — InsideBar (#126, #157)

Source: **MNQ 03-24, 1-minute, an NT8 Strategy Analyzer export of 16,744 trades** at `SetDefaults`, reconciled over **2023-12-14 → 2024-03-15**.

**The window is the front-month period, and that is forced.** Requesting `MNQ 03-24` from 2020 gives NT8's *merged* series, not that contract's own bars: before the December roll only 10.9% of exported entries land inside the archive's bar for their timestamp, against **100.0% after it — every one exactly at the bar's open**, which is the market-on-next-open entry confirmed to the tick. A reconciliation window is evidence about the bars it contains.

| field                    | agreement                |
| ------------------------ | ------------------------ |
| entry price              | 100.00%                  |
| exit price               | 100.00%                  |
| exit time                | 100.00%                  |
| exit reason              | 100.00%                  |
| net P&L                  | 100.00%                  |
| **identical everywhere** | **969 of 969 — 100.00%** |

Reproduce it with InsideBar's MNQ 03-24 Trades export as `<export.csv>`:

```bash
uv run tools/reconcile_nt8.py <export.csv> InsideBar "MNQ 03-24" 2023-12-14
```

**What this settled.** The `IsFillLimitOnTouch = true` branch, which nothing in the project had evidence for. The `OnExecutionUpdate` indexing, established against both terms independently and against an inference that had them one bar later. And that `ExitOnSessionCloseSeconds` does not move a backtest's flatten. `Archetype.tier2` is `RECONCILED`.

**The whole residual was out-of-session stray bars, and it was not InsideBar's** (#160). The export files carry occasional prints outside session hours which NT8, building bars against the ETH template, never forms; `sessions.classify` flagged them and nothing dropped them, so they sat in the array the simulation indexes. At the first bar of a Sunday session a stray becomes `[1]`, and InsideBar's inside-bar test reads `[1]` and `[2]` directly. Dropping them in `load_contract` took this reconciliation from **943/947 — 99.58%** to **968/968 — 100.00%**, NT8-only entries from 22 to 1 and nqbt-only from 7 to 0, and left the DeadCatBounce and PullBackAndGo reconciliations **bit-for-bit unchanged**, because neither reads two bars back through a strict geometric test. The rule is general and the sensitivity is not: any future archetype reading two bars back inherits the same exposure. **The last NT8-only leg went with #208** — see "A resting entry fills on the force-flat bar, and is flattened at its close" — which is what makes this reconciliation 969 of 969 with nothing unjoined on either side.

**The Presidents' Day disagreement is the one #68 fixed**, and it was the last one standing before the strays went. A trade entered at 13:00 ET on 2024-02-19, an exchange early close, which `force_flat_mask` measured against the template's fixed 17:00 and so never flattened. Deriving the session end from the observed last bar took this reconciliation from 942/947 to 943/947 and left the DeadCatBounce and PullBackAndGo reconciliations above bit-for-bit unchanged — see "The session end is the observed last bar, not the template's".

### M23 — the InsideBarTrailing rules

`InsideBarTrailing.cs` shares `InsideBar.cs`'s entry and replaces its single bracket with three exit mechanisms the simulation did not have. Every rule below has been diffed against a Strategy Analyzer trade list — "Reconciliation result — InsideBarTrailing" below — and **that list overturned three of the four the port had inferred**, which is the argument for reconciling each archetype rather than trusting a shared engine because the last one passed.

**The entry is InsideBar's, and it is shared rather than copied.** Same inside bar, same mother bar, same three strict moving-average gates, same market-on-next-open — so `InsideBarTrailingParams` subclasses `InsideBarParams` and both archetypes call `insidebar_signal`. What differs is four defaults, and one of them is not a tweak: `ErrorMargin = 0.1` against `0.01` is **ten times the breakout buffer** and a materially different strategy. The others are `SmaSlowPeriod 125` against `200`, `OrderQuantity 6` against `4`, and the one-hour session-end guard, which this script simply does not have. Entry price agreed with NT8 on **100.00%** of joined legs, so the sharing is verified rather than assumed.

**The position is split across two entry orders with different exit engines.**

```csharp
firstLotQuantity  = (int) Math.Ceiling(OrderQuantity * PartialTakeProfitPercentage);  // 4 of 6
secondLotQuantity = OrderQuantity - firstLotQuantity;                                 // 2 of 6
```

`entry1` gets a fixed stop and a profit target; `entry2` gets a trailing stop and no target at all. With `StopTargetHandling.PerEntryExecution` that is two brackets over one position rather than one bracket with two legs, which is exactly how the port resolves it: one call to `resolve_brackets` per lot per bar, each with its own stop, target and planned risk, and the shared engine unchanged. The export carries 13,043 `entry1` rows and 13,043 `entry2` rows at 4 and 2 contracts, so the split itself needed no inference. The structural argument for that shape rather than a generalised `bracket.py`: [`roadmap.md`](roadmap.md) §M23.

**Both lots are bracketed off the same fill, from the same two bars as InsideBar's.** `OnExecutionUpdate` runs with the signal bar current, so the ATR it reads at `[0]` is the signal bar's and `High[1] - Low[1]` is the **inside** bar's range — the indexing §M22 established leg-for-leg, inherited here rather than re-derived, and confirmed by the trail distances matching.

#### The trailing stop, and the two cadences that are not the same cadence

```csharp
double trailingStopDistance = (High[1] - Low[1]) / TickSize * TrailingStopMultiplier;
SetTrailStop("entry2", CalculationMode.Ticks, trailingStopDistance, false);
```

DeadCatBounce's and PullBackAndGo's ratchet moves the stop to a *lagged bar's* extreme plus an offset; an NT8 trail stop follows the **high-water mark** by a fixed tick distance. Different rule, different failure modes. The distance is a tick count in the C#, so the port computes it as one and converts back rather than multiplying the range directly.

**A resting trail advances at the bar close, so it cannot be hit on the bar that set it.** Advancing it within the bar everywhere drops agreement from 99.80% to **94.04%**, so this is measured rather than assumed — and it matches the ratchet's cadence, which is the one thing the port did guess right.

**The entry bar is the exception, and it advances within.** `SetTrailStop` is submitted *during* that bar rather than resting from its open, and the export shows it acting on that bar's own extreme: **22 of the 24 legs** that still disagreed under a uniform bar-close cadence were NT8 stopping out on the entry bar. Every one of the four cases inspected by hand is explained exactly — for a short entered at 17484.50 with a 22.50 distance, NT8 exited at 17491.00, which is the entry bar's low of 17468.50 plus 22.50 to the tick. Adding the entry-bar advance took the reconciliation from 98.42% to **99.80%**.

**A trail distance under one tick refuses the trade.** The submittability rule — "a stop at or through the price it protects is not a stop order" — applied to the trailing lot, reachable only when the inside bar has no range at all. The export contains no such trade, so what NT8 does with `SetTrailStop(..., 0, false)` is still unobserved; the port declines the entry rather than running a lot with no protective order behind it. That one is still the conservative reading rather than a measurement.

#### The `-200` gate sits above **both** branches, and the trend violation is beneath it

```csharp
if (marketPosition == MarketPosition.Flat) return;
if (position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, Close[0]) > -200) return;
if (... < -MaximumLossPerTrade && MaximumLossPerTrade > 0) { /* max loss - dead */ }
if (position.MarketPosition == MarketPosition.Long && (ema[0] < smaFast[0]))
    ExitLong("Exit Long Trend Violation", "entry1");   // and "entry2"
```

**This was the single largest correction the export made.** Reading the hardcoded `-200` as belonging to the max-loss branch beneath it — which is how it reads if you start from that branch — leaves the trend violation ungated, and the port fired it **340 times** in the reconciliation window against NT8's **12**. It is an early return at the top of the method, so the trend violation cannot fire until the open position is at least $200 down at `Close[0]`.

It is a **currency amount on the whole open position with no scaling behind it**, so it means ten times the price move on MNQ that it means on NQ. It therefore goes through `instruments.py`'s point value like every other monetary figure, and `position_update_loss_gate` carries it as a parameter because the C# will not.

#### The trend-violation exit, the second `EXIT_SIGNAL` consumer

**It fires only where the position actually changed, and only where something is left to sell.** `OnPositionUpdate` fires on position changes rather than on every bar; porting it as a per-bar check would be a different and much busier strategy. The entry fill is a position change, but with both lots just opened there is nothing for the exit to fill alongside — and the gate above would block it anyway, since a fresh position is not $200 down. In the whole export the trigger was **the trailing lot's stop, 303 times out of 303**.

**The remaining lot leaves at the price and bar the triggering fill did** — the same fill event, not a market order on the next bar. All 303 of NT8's trend-violation exits share their sibling's exit time and exit price exactly. Reading it as a next-bar market order, which is what §M18's `EXIT_SIGNAL` rule would suggest, costs 12 legs; that rule describes an exit decided in `OnBarUpdate` at a bar close, and this one is not.

**The averages are read at strategy time `i - 1`**, the same one-bar offset `OnExecutionUpdate` has, and the comparison is strict, so `ema == smaFast` holds the position. It generalises through the sign multiplier rather than as two branches.

#### The max-loss exit is dead, and the export confirms it

`MaximumLossPerTrade` defaults to `0`, so `< -MaximumLossPerTrade && MaximumLossPerTrade > 0` can never be true. **Not one `Exit Long/Short Max Loss` row appears in the export's 26,086**, so this is now a measurement rather than a reading of the C#. The port carries the reconciled behaviour the way `PullBackAndGoParams` reproduces its reconciled configuration: `maximum_loss_per_trade` exists, defaults to `0.0`, and raises on anything else. Enabling it means a second currency threshold, and it would have to go through `instruments.py` exactly as the gate above does.

### Reconciliation result — InsideBarTrailing (#127)

Source: **MNQ 03-24, 1-minute, an NT8 Strategy Analyzer export of 26,086 legs** at `SetDefaults`, reconciled over **2023-12-14 → 2024-03-15** — the same instrument, series and window as §M22's, changing only the strategy, so a difference between the two reconciliations is attributable to the exit model rather than to the data.

| field                    | agreement                    |
| ------------------------ | ---------------------------- |
| entry price              | 100.00%                      |
| exit price               | 100.00%                      |
| exit time                | 100.00%                      |
| exit reason              | 100.00%                      |
| net P&L                  | 100.00%                      |
| **identical everywhere** | **1,522 of 1,522 — 100.00%** |

Net P&L over the joined legs: NT8 −8,913.00 against nqbt −8,913.00. Reproduce it with InsideBarTrailing's MNQ 03-24 Trades export as `<export.csv>`:

```bash
uv run tools/reconcile_nt8.py <export.csv> InsideBarTrailing "MNQ 03-24" 2023-12-14
```

**What this settled**, in the order the corrections landed: that the `-200` gate governs the trend violation and not just the dead branch under it (80.18% → 97.23%); that `OnPositionUpdate` runs at the same one-bar offset `OnExecutionUpdate` does (→ 97.63%, and exit reason to 100.00%); that the exit it submits is part of the triggering fill rather than a next-bar market order (→ 98.42%); and that a trail advances within its entry bar but not within any later one (→ 99.80%). `Archetype.tier2` is `RECONCILED`.

**The last three legs went with the out-of-session strays** (#160), the same fix and the same cause as InsideBar's: this archetype shares that entry, so it reads `[1]` and `[2]` too. They were leg-1 targets off by a tick or two, and dropping the strays took the run from 1,517/1,520 to 1,522/1,522. There are 4 NT8-only and 2 nqbt-only legs left at the window edges.

**The two open questions it closed were #67's.** Both were added there before the port was written, precisely because reflection cannot answer them; both are now answered by measurement rather than by argument.

#### How the export was produced

Same settings as §M22's, changing only the strategy.

| Strategy Analyzer setting | value                                                            |
| ------------------------- | ---------------------------------------------------------------- |
| Strategy                  | `InsideBarTrailing`, every parameter left at `SetDefaults`       |
| Instrument                | `MNQ 03-24`                                                      |
| Data series               | 1 minute, `Last`, `<Use instrument settings>` — the ETH template |
| From → To                 | `2020-01-02` → `2024-03-15`                                      |
| Order fill resolution     | Standard — the script sets it, do not raise it to High           |
| Slippage                  | 0 ticks                                                          |
| Commission                | none, and no fee template                                        |
| Min. bars required        | 5, which `BarsRequiredToTrade` already sets                      |

Export via **Trades → right-click → Export**, not the Summary tab: summary statistics hide fill semantics, which is the only thing this run is for.

**The request runs to 2020 and the reconciliation starts at 2023-12-14 on purpose.** NT8 serves its *merged* series for a contract before that contract's own bars begin, which a per-contract archive cannot reproduce — the trailing date argument trims the export to the front-month window.

**Three exit names are new, and two are deliberately unmapped.** `Trail stop` maps to `stop` and both `Exit Long/Short Trend Violation` map to `signal`. `Exit Long/Short Max Loss` is **not** mapped: that branch is unreachable, so an export carrying one falsifies the reading above and must stop the run rather than be counted as agreement.

### The entry trading window, and the zone it is measured in (#349)

**The [cell](../README.md#cell) #344 ports is confined to a [session phase](../README.md#session-phase), and the NinjaScript had no way to say so.** `InsideBarTrailing.cs` carried eleven `[NinjaScriptProperty]` parameters and not one of them was a time, so `phase=MIDDAY` existed only in Python, as `context.phase_gate`. Two properties now express it, in Eastern time as `HHMMSS`:

```csharp
int barTime = ToTime(TimeZoneInfo.ConvertTime(Time[0], displayTimeZone, easternTimeZone));
if (EntryWindowStart < EntryWindowEnd) return barTime > EntryWindowStart && barTime <= EntryWindowEnd;

return barTime > EntryWindowStart || barTime <= EntryWindowEnd;   // a window that wraps midnight
```

**It gates entries only**, so an open position is still managed and flattened by the existing rules — which is what the port does, where the phase mask is ANDed into the signal by `filters.apply_context_filters` and nothing else reads it.

**`EntryWindowStart == EntryWindowEnd` is off, and that is the default**, so `SetDefaults` remains exactly the configuration reconciled above. It mirrors the port, where the same parameter's off value is `phase_filter = ALL_PHASES` rather than a second switch.

**The boundary is exclusive at the start and inclusive at the end**, because a bar is stamped at its close and belongs to the phase its *body* falls in. That is `timeofday.phase_from_minutes` reading `minutes_since_open - 1`: `MIDDAY` is minute-of-session 990 to 1199, so a bar stamped 10:30 is the last `CASH_OPEN` bar and one stamped 14:00 is the last `MIDDAY` one. Transcribed into Python and compared against `timeofday.classify(...).gate(MIDDAY)` over 132,407 MNQ 03-24 bars at 1, 2, 5, 10 and 15 minutes, the two agree on every bar at every resolution.

**It counts forward from the template's open, which is why it can be reconciled at all.** "A no-entry window before the session close" records the opposite case: a rule measured against the *observed* session end cannot agree with a C# reading the wall clock, and that is why InsideBar's one-hour guard is the one rule the two tiers cannot reconcile by construction. A wall-clock window is the wall clock on both sides.

#### `Bars.TradingHours.TimeZoneInfo` is Central, and the first run was an hour out

**CME's trading-hours template is defined in the exchange's own local time, which is Chicago, where `nqbt.timeofday` is Eastern by definition.** The first version of the property converted `Time[0]` into `Bars.TradingHours.TimeZoneInfo` and so gated 10:30–14:00 **Central** — one hour later than the [stratum](../README.md#stratum) every stored result was measured in.

**Only the trade list could have found it.** The diff joined 154 of 274 legs at one minute and 52 of 84 at five, with NT8's entries running 11:32–14:56 ET against the port's 10:32–13:56, and **every leg both sides agreed existed still agreed on all five fields**. A Central-gated run is a plausible strategy with a plausible equity curve; summary statistics show nothing at all.

**The reading was confirmed rather than inferred.** Re-running the port with the window evaluated in `America/Chicago`, and nothing else changed, joins **274 of 274 and 84 of 84 with zero unjoined on either side**, every field identical. The fill model was right and only the zone was wrong, so the script now names the zone outright:

```csharp
easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
```

**A Python-side check of the rule was blind to this**, because the transcription used Eastern on both sides. It pinned the boundary convention and could say nothing about which zone the C# resolves at runtime — the same shape as every other rule here that reflection could not settle.

**The conversion is load-bearing rather than defensive.** `Time[0]` is in NinjaTrader's display zone, which is the `Europe/London` that `EXPORT_TZ` reads the trade list in. London is ET+5 for 87 days of the MNQ 03-24 reconciliation window and **ET+4 for its last six**, because the two zones change over on different dates, so a fixed offset is wrong for several weeks of every year.

### Reconciliation result — InsideBarTrailing with the trading window (#349)

Source: **MNQ 03-24**, three Strategy Analyzer exports reconciled over **2023-12-14 → 2024-03-15** — the same instrument and window as §M22's and §M23's, so a difference is attributable to the gate rather than to the data.

| run        | configuration                       | NT8 legs | joined |   identical | NT8 only | nqbt only |
| ---------- | ----------------------------------- | -------: | -----: | ----------: | -------: | --------: |
| regression | 1 minute, `SetDefaults`, window off |    1,526 |  1,522 | **100.00%** |        4 |         2 |
| gated      | 1 minute, `SetDefaults`, window on  |      274 |    274 | **100.00%** |    **0** |     **0** |
| ported     | 5 minutes, combo 2035, window on    |       68 |     68 | **100.00%** |    **0** |     **0** |

Net P&L over the joined legs agrees exactly on all three: −8,913.00, −10,510.00 and +3,613.00.

**The regression run's export is byte-identical to §M23's**, so the window code is inert with the window off and `ExitOnSessionCloseSeconds` 180 → 30 moved nothing — the probe finding under "`ExitOnSessionCloseSeconds` is honoured but inert at bar granularity" confirmed on a real strategy rather than on a probe. `docs/findings/m41-flatten-timing.md` § "For going live" is why the value was set at all.

**Both gated runs join with nothing unmatched on either side**, which the unfiltered reconciliation does not — it still carries 4 NT8-only and 2 nqbt-only legs at the window edges.

**The gate is exercised rather than trivially satisfied.** The 1-minute run's earliest entry is 10:32 ET, the first bar the window can admit, and its latest 13:56; the 5-minute run reaches 14:00 ET. Both cover all four exit reasons, and the ported run carries 19 session-close legs of 68 — the exit this archetype's P&L rests on is inside the diff rather than beside it.

`Archetype.tier2` stays `RECONCILED`, now on a trade list that exercises the new rule instead of on one that predates it. **A row filtering on phase is nonetheless stamped `TIER1_ONLY`**, by decision — `docs/roadmap.md` § "Decisions taken".

#### How the exports were produced

§M23's settings, changing only the data series and the two window properties:

| run        | data series | Entry Window Start | Entry Window End | other parameters |
| ---------- | ----------- | ------------------ | ---------------- | ---------------- |
| regression | 1 minute    | `0`                | `0`              | `SetDefaults`    |
| gated      | 1 minute    | `103000`           | `140000`         | `SetDefaults`    |
| ported     | 5 minutes   | `103000`           | `140000`         | combo 2035       |

Reproduce the ported run with its Trades export as `<export.csv>`:

```bash
uv run tools/reconcile_nt8.py <export.csv> InsideBarTrailing-midday-2035 "MNQ 03-24" 2023-12-14
```

`CONFIGS` carries all three, keyed `InsideBarTrailing`, `InsideBarTrailing-midday` and `InsideBarTrailing-midday-2035` — one archetype with three reconciled configurations, which is why a config name is no longer always an archetype name. The last is `docs/findings/m43-midday-candidates-ranked.md` § "The cell to port" with its commission and slippage set to zero, because NT8 ran with no fee template and a cost difference would read as a fill disagreement on every leg.

### M45 — InsideBarTrailing's lot sizing per signal, written before the C# (#295, #353)

**Two rules that choose an entry's split at its signal bar, and neither is in the reconciled NinjaScript.** `InsideBarTrailing.cs` computes `firstLotQuantity` and `secondLotQuantity` once, in `State.DataLoaded`, so every entry takes the same split; both rules below compute them per signal instead. Everything in §M23 still describes the archetype — the entry, both lots' exit engines, the `-200` gate and the trend violation — and with both rules off the split is the one the C# computes. **The trade-log gate could not confirm that when the rules landed** — it captured DeadCatBounce alone until #376, and now captures InsideBarTrailing at its defaults, where both rules are off — so the InsideBar and InsideBarTrailing reconciliations were the real-data check. **Run on the base commit and on the change, all four came back identical** — InsideBar 969 of 969, InsideBarTrailing 1,522 joined, the midday configuration 68 of 68 — `docs/findings/m45-ibt-sizing-result.md` § "The change moved nothing it was not meant to". **A row using either rule is `TIER1_ONLY`** whatever the archetype's status says, through `Archetype.departs_from_port`, until a trade list has been diffed against a C# that implements it.

**The sizes are decided at the signal bar's close, in `OnBarUpdate`.** That is the only place the managed approach lets a quantity be chosen — `EnterLong(0, quantity, "entry1")` takes it as an argument — so the port reads the split at the signal bar and never at the fill bar, whose close is still in the future when the order goes in. The Python holds every split a combination can take as a table, `InsideBarTrailingParams.lot_table`, and each bar's row in `bracket.Sizing`; the loop copies the signal bar's row into the lots at the fill.

**The `-200` gate reads the trade's own size.** It is currency on the whole open position, so a larger split reaches it after a smaller move — the NQ-against-MNQ arithmetic of §M23, now varying trade by trade. `GetUnrealizedProfitLoss` does the same, so nothing new is inferred.

**The split still rounds the bracketed lot up**, `(int) Math.Ceiling(quantity * share)`. At two contracts a quarter and a half are both one lot, and at the stored `0.6` two contracts leave no runner at all, so the parameter class refuses a pair of tiers that splits every quantity the same way and any split that leaves a lot empty. **That makes quantity a live axis on this archetype and on no other**: everywhere else commission and slippage are per contract, so a quantity scales every dollar figure and leaves the profit factor exactly where it was.

#### Earliness: which share the bracketed lot takes

`earliness_mode` picks the rule. An early entry takes `early_partial_percentage`, an established one keeps `partial_take_profit_percentage`, and each is judged on the side the entry would take:

| mode             | early when                                                                           | NinjaScript                                                              |
| ---------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `first-breakout` | no setup on that side earlier in the current unbroken run of the three-average trend | a counter reset whenever `upTrend` goes false and advanced on each setup |
| `trend-age`      | the trend has run at most `early_max_trend_bars` bars, the signal bar included       | a run counter over `upTrend`                                             |
| `sma-extension`  | the close sits at most `early_max_extension_atr` ATRs from the slow SMA              | one expression at the signal bar, below                                  |

```csharp
bool early = Math.Abs(Close[0] - smaSlow[0]) / ATR(ATRLength)[0] <= EarlyMaxExtensionAtr;  // sma-extension
```

**The setup counted is the pattern alone** — the inside bar, the break and the three averages — before the entry window, the context filters and the position guard, because earliness is a property of the move and not of whether this strategy could take it. **So both counters have to sit above `if (Position.MarketPosition != MarketPosition.Flat) return;`**: below it, a setup that arrived while a position was open would not count, and the next entry would read early when it is not.

**A bar outside a trend on its side reads early** — no move has been established there — and an extension that cannot be measured, an ATR of zero, reads established. Neither is reachable by a real signal, which requires the trend and a range; both are reachable by the [random-entry arm](../README.md#matched-null), which may draw on any bar.

**The trend is the entry's own strict condition**, so a close exactly on an average breaks a run, and a run spans the session break exactly as the averages do.

#### Confluence: how many contracts

`quantity_per_confluence` contracts are added to `order_quantity` for each `size_on_*` label favouring the trade at its signal bar, and the split then applies to the total. The count is over these labels alone and is independent of the context *filters*, which narrow the signal exactly as before.

| label                      | favours a long                   | favours a short    |
| -------------------------- | -------------------------------- | ------------------ |
| `size_on_trend`            | trend label `UP`                 | trend label `DOWN` |
| `size_on_higher_timeframe` | close `ABOVE` the coarse average | close `BELOW` it   |
| `size_on_vwap`             | close above the session VWAP     | close below it     |
| `size_on_regime`           | efficiency ratio `DIRECTIONAL`   | the same           |
| `size_on_volume`           | relative volume `HEAVY`          | the same           |

**A bar a label cannot classify counts as not favourable**, as `annotate.confluence` counts it. **None of the five exists in NT8**: the trend, [regime](../README.md#regime), volume and higher-timeframe labels are this project's — "So are the regime labels (#40)" and its neighbours below — and the session VWAP has not been checked against `OrderFlowVWAP`, which is why PullBackAndGo's `use_vwap` stays off. A port of this rule is a port of every label it counts, and each needs its own pin before the size can be reconciled.

**A step and a label, both or neither.** `quantity_per_confluence` above zero with no label, or a label with no step, sizes every trade the same, and the parameter class refuses it rather than run a duplicate of fixed size.

§M47 carries this size to every archetype. The table above is InsideBarTrailing's, whose regime and volume labels read the expansion thesis there.

### M47 — the confluence size on every archetype, written before any sweep (#295)

**§M45's confluence size, generalised from InsideBarTrailing to the whole registry.** Every parameter class carries `quantity_per_confluence`, §M45's five `size_on_*` labels and `size_symmetric`. Every entry loop reads a per-signal size table in place of the fixed split. `bracket.Sizing` holds every per-leg split a combination can take and the row each bar takes, and `bracket.size_legs` copies the **signal** bar's row into the legs at the fill. The bracket engine is unchanged, because `write_leg` has always read each leg's own quantity. **With the size off the table is the one fixed split**, which is each NinjaScript as ported. **Run on the base commit and on the change**, the trade-log gate returned `ALL PRE-EXISTING COLUMNS IDENTICAL` under `--added` for the seven new parameter columns, and the seven stored reconciliations produced identical output: DeadCatBounce, PullBackAndGo, InsideBar, and InsideBarTrailing's default, trading-window, ported and regression exports. The gate then saw DeadCatBounce's loop alone (#376), so every archetype's campaign [variants](../README.md#variant) were also run on the last two years of MNQ at three combinations each. All 81 leg matrices, 281,641 legs, were identical to the base commit's. **Once #376 put every archetype's loop in the gate at its defaults**, it returned the same verdict over all 22 of its files.

**Each reconciled NinjaScript can express it, because each already passes a quantity per signal.** `DeadCatBounce.cs` and `PullBackAndGo.cs` split `orderQuantity` in `OnBarUpdate`, at the signal bar: `baseQuantity = orderQuantity / 4`, the remainder on the fourth entry. Each entry's size then goes to its own `EnterShortStopMarket` or `EnterLongStopMarket`. `InsideBar.cs` passes `OrderQuantity` to one `EnterLong` or `EnterShort`. A port replaces the fixed quantity there with the signal's own and keeps the existing split:

```csharp
int quantity = Math.Max(4, orderQuantity + 4 * QuantityPerConfluence * count);  // four entries, one per target
int baseQuantity = quantity / 4;
int remainder = quantity % 4;
```

**A row using the size is `TIER1_ONLY`** on all three and on InsideBarTrailing, through `Archetype.departs_from_port`. The originals are `TIER1_ONLY` already.

**A label adds or removes one step on every leg, so the position scales without changing shape.** On every archetype but InsideBarTrailing, `quantity_per_confluence` is contracts per leg per label. So a four-target bracket at four contracts gains four per favourable label, one at each target, rather than one on the runner; `Trading-Docs` §10 takes a position off in equal pieces, one at each target. `leg_size_table` moves the total by `legs × step × count` and applies the fixed split to it, so the remainder stays on the last leg. **InsideBarTrailing keeps §M45's rule**: the step is added to the whole position before its split, which already scales both lots.

**Add-only or symmetric.** With `size_symmetric` off, a step is added for each label favouring the trade. With it on, a step is also removed for each label opposing it, so the count runs from minus every label to plus every label. **No row falls below the smallest position the bracket takes**: one contract per leg, or on InsideBarTrailing the smallest total whose split leaves both lots non-empty. That floor is a clip, and the size table shows it. **A symmetric size whose base is already at that floor is refused**, because it can remove nothing and would be the add-only size under another name. The parameter class refuses it, and so does `Grid` before any combination runs. Every four-target bracket at four contracts is therefore add-only.

**When a label favours or opposes the trade:**

| label             | favours                                       | opposes           | neither                                        |
| ----------------- | --------------------------------------------- | ----------------- | ---------------------------------------------- |
| trend             | `UP` for a long, `DOWN` for a short           | the other         | `MIXED`, or a bar the label cannot classify    |
| higher timeframe  | close `ABOVE` for a long, `BELOW` for a short | the other         | `AT`, or a bar no coarse bar has closed before |
| VWAP              | close above for a long, below for a short     | the other         | none                                           |
| regime and volume | the state the archetype's thesis names        | the other extreme | the middle state, or an unclassifiable bar     |

A close exactly on the VWAP both favours and opposes the trade, because each C# boundary counts equality as a pass. So it adds a step when add-only and nets to nothing when symmetric.

**The thesis is a property of the archetype, `sizing_thesis`, and not a parameter.** Each entry is one of three kinds, decided from `Trading-Docs` before any sweep:

| archetype                         | thesis    | regime favoured | volume favoured | why                                                                                                   |
| --------------------------------- | --------- | --------------- | --------------- | ----------------------------------------------------------------------------------------------------- |
| DeadCatBounce                     | pullback  | `DIRECTIONAL`   | `THIN`          | a short into a bounce inside a downtrend; a healthy trend's counter-moves come on light volume, §6 Q2 |
| PullBackAndGo                     | pullback  | `DIRECTIONAL`   | `THIN`          | its long-side mirror                                                                                  |
| EmaPullback                       | pullback  | `DIRECTIONAL`   | `THIN`          | a pullback to the fast average inside a trend                                                         |
| EmaCrossover                      | expansion | `DIRECTIONAL`   | `HEAVY`         | a trend change taken at the cross, which wants participation behind it                                |
| InsideBar, InsideBarTrailing      | expansion | `DIRECTIONAL`   | `HEAVY`         | a break of the mother bar with the three averages; §M45's rule, unchanged                             |
| SqueezeBreakout                   | expansion | `DIRECTIONAL`   | `HEAVY`         | a break out of a compressed window                                                                    |
| OpeningRange, breakout and retest | expansion | `DIRECTIONAL`   | `HEAVY`         | expansion is price leaving the range and trading there, §6 Q4                                         |
| OpeningRange, fade and rejection  | rotation  | `CONSOLIDATING` | `THIN`          | trading back from the far extreme, which is §M28.5's own thesis                                       |
| ElasticBand                       | rotation  | `CONSOLIDATING` | `THIN`          | a fade to the mean wants two-way trade (§6 Q4) and an extreme nobody is pressing (§6 Q2)              |

**Two of those volume choices meet measurements already on record, and they point different ways.** On EmaPullback, `HEAVY` was a cost at every [fitted cut](../README.md#cut) (§M36), which agrees with the pullback thesis. On ElasticBand the sign belongs to the channel (§M33): `HEAVY` is a cost on the VWAP band and a benefit on the Bollinger band. The campaign grid uses the Bollinger band, so there the rotation thesis's volume choice runs against the evidence. The theses come from `Trading-Docs` and not from those results. For those two archetypes the volume label's [held-out](../README.md#holdout) test is not independent of what was seen, and `docs/findings/m47-confluence-sizing-preregistration.md` says so beside the bar.

**The size is read at the bar whose close submitted the order that fills.** On every loop but two that is the bar before the fill. EmaPullback's confirmation entry remembers the bar that submitted its resting order, and a later signal on the same side resubmits it at that bar's size. OpeningRange and SqueezeBreakout resubmit their order at every close, so the order that fills carries the size of the close before it.

**None of the labels exists in NT8** (§M45), so porting any of this means porting every label it counts.

### M26 — the elastic band rules, written before the Python (#167, #168)

**Every rule below was written down before the Python existed, and the Python was then written to it** — the order §M18 could not manage, because there the rules were recorded after the fact. There is still no NinjaScript, so nothing here is backed by a trade list. Each item names the NinjaScript it would be written as, because a rule chosen at design time that NT8 cannot express makes the archetype unreconcilable later, and the exploration is then wasted rather than merely unvalidated. The reasoning behind the choices, and the alternatives rejected, are in [roadmap.md](roadmap.md) §M26; only the rules are here.

`Archetype.tier2` is `TIER1_ONLY`, and stays there until a trade list has been diffed against it.

**The band is `Bollinger(numStdDev, period)` on close**, and both halves of it are already pinned: `Bollinger.Middle[0]` is `nt8_sma` and the half-width is `numStdDev × StdDev(period)`, each exact against the probe export on every bar of the M16 window — see "Indicators" above. `Bollinger.Upper[0]` and `.Lower[0]` are `middle ± spread`. **No new indicator is needed and no new probe run is required**, which is the property the band was chosen for.

**The entry test is a standard-deviation threshold, not a band touch.** `band_stretch` is `(Close[0] − Bollinger.Middle[0])` over `StdDev(period)`, and the gate is `band_stretch <= -entry_std` for a long and `>= entry_std` for a short. Written against the indicator instead it is `Close[0] <= Bollinger(entryStd, period).Lower[0]`, and the two forms agree on every bar except one: **at bar 0 `StdDev` is 0**, the bands collapse onto the close, and the division form reads 0 rather than infinite. Measured over 200,000 bars at three periods and three multiples, bar 0 was the only disagreement in every configuration ([roadmap.md](roadmap.md) §M26). `BarsRequiredToTrade` excludes it either way, so the choice is free; the division form is taken because it makes the multiple a free sweep axis.

**Extension depth is bounded on both sides.** `entry_std` is the floor and `max_entry_std` the ceiling — beyond some extension the move is a trend breaking out rather than a band being stretched, which is an optimal-stopping result and a practitioner observation both ([roadmap.md](roadmap.md) §M26). **Extension duration is a separate gate.** `min_bars_outside` is how many consecutive bars have been outside — `conditions.consecutive_true` over the same boolean, and in NinjaScript an `int` incremented in `OnBarUpdate` and reset to 0 whenever the bar closes back inside. Both come from [#167]'s own statement of the thesis and neither implies the other.

**The band is read from the signal bar, which includes that bar's own close.** This is not lookahead — every input is a completed bar at or before *i* — but it is self-referential: the move being tested widens σ and moves the basis, damping its own measured stretch. The alternative is the `[1]` index on both `Bollinger` and `StdDev`, tested against `Close[0]`. It is a swept toggle rather than an assumption. **The lag moves the band and never the close**: until #451 the Python lagged the close with it, so `band_lag = 1` compared the previous bar's close with its own band rather than this bar's close with the previous band, and every row stored with a lag above `0` before then measured that rather than this.

**The entry is market-on-next-open, and §M18's consequences apply unchanged.** `EnterLong()` / `EnterShort()` under `Calculate.OnBarClose` submit at the close of bar *i* and NT8 fills at the open of bar *i+1*. There is no trigger price, so no "no touch, no fill" and no submittability rule; a bar at or past the flatten cutoff cancels the order rather than filling it. The second form is a limit at the band, which rests — so it is cancelled after one bar, and it must trade *through* rather than touch to fill ("Limit orders must trade *through*, not touch").

**Direction is chosen by which band was breached, and the archetype is flat between trades.** Only one side can be extended at a time, so there is no OCO pair to express and no stop-and-reverse. `EntriesPerDirection` is not reached.

**The stop and the target are three schemes, not one rule**, and they are swept as three grids over one parameter class — the reasoning and the evidence are in [roadmap.md](roadmap.md) §M26, "Three exit schemes". What each becomes in NinjaScript:

| scheme                | stop                                                                 | target                                        |
| --------------------- | -------------------------------------------------------------------- | --------------------------------------------- |
| A, band rotation      | adverse extreme of the excursion bars, offset by `stopOffsetTicks`   | `Bollinger.Middle[0]`, then the opposite band |
| B, volatility bracket | `Math.Max(atr * multiple, floor / pointValue)` off the fill          | the R ladder, capped at `Bollinger.Middle[0]` |
| C, time and mean      | `maxRiskTicks` only, a catastrophe limit rather than a strategy stop | `Bollinger.Middle[0]`, whole position         |
| the tight stop        | `Low[0] - stopOffsetTicks * TickSize` over `swingLookback` bars      | any of the above                              |

All four are `SetStopLoss` / `SetProfitTarget` against a level the script already holds, so none of them needs anything NT8 does not express. **Only B's stop is floored**, because only it is a distance rather than a level — a structural stop pushed away from its structure stops being the rule it is. The tight stop is the same device as EmaCrossover's swing mode and shares its implementation, `bracket.swing_stop`; at `swingLookback = 1` it is the signal candle alone, which is the tightest stop the archetype can express and, measured, no better than any other ([roadmap.md](roadmap.md) §M26).

**A target that is a level is written as a price, not as an R multiple.** `Bollinger.Middle[0]` at the signal bar. Where legs scale out they do so at fractions of the distance back to it — `fill + d × (basis − fill) × fraction[leg]` — so the archetype writes `legs.target[leg]` as prices and `bracket.py` resolves them exactly as it resolves an R-multiple target. Nothing in the bracket engine changes. A target the entry bar opens past fills at the nearest price that bar traded — § "A limit order the market has passed fills at the nearest price the bar traded".

**`r_multiple` therefore means a third thing.** Under A and C, R is set by the band geometry and is identical across every combination sharing a ratio; under B it is the ratio of two different volatility measures. Elastic band results are not comparable with DeadCatBounce's or EmaCrossover's at the same R.

**Two signal exits are specified.** A's invalidation exit — price closing back outside the band beyond the excursion extreme — and C's time stop, an `int` incremented in `OnBarUpdate` against `maxHoldBars`. Both are market orders at the close of bar *i*, filled at the open of *i+1*, taking precedence over the stop and the targets on that bar because NT8's managed approach cancels a position's brackets when something else flattens it. Both wrote `EXIT_SIGNAL` and **a grid could not enable both**, because the trade log then could not say which fired: no new exit code was added here, deliberately, since one would move `trades.py` and every stored log's schema. That held until the time stop reached every archetype and earned `EXIT_TIME_LIMIT` of its own — § "The maximum hold time, and why it is its own exit code", which is also where the exclusion went. The relabel is the only thing about ElasticBand it moved.

**Flat before the session close binds harder here than on any existing archetype**, because "hold until price returns to the basis" is an unbounded hold. `IsExitOnSessionCloseStrategy` handles it identically to every other archetype and nothing new is needed, but the expected `session_close_share` is high enough that it changes what the results mean — [roadmap.md](roadmap.md) §M26.

### M26.4 — the VWAP band, the second source and the first unpinned indicator in an archetype (#221)

**`band_source` picks the channel, and everything above still describes the Bollinger one.** The rules here are the ones the VWAP source changes and nothing else: entry depth, duration, direction, all three exit schemes, the target-as-a-level geometry and the session flatten are read from the same `band_stretch` coordinate and are untouched. `Archetype.tier2` stays `TIER1_ONLY`.

**The basis is the session VWAP already in the codebase, and it is *not* pinned.** `indicators.session_vwap` is hand-rolled `Σ(typical × volume) / Σ(volume)` re-anchored at each 18:00 ET open — "Indicators" above records that it mirrors `OrderFlowVWAP(VWAPResolution.Standard, …)` and #167's port note records that nothing has ever checked it against NinjaTrader. **This is the first archetype rule built on an unpinned indicator**, and it is a deliberate exception to how every other entry gate here was arrived at: the Python is exploratory and the pin is owed before [#170], not before the measurement. The probe is `NqbtIndicatorProbe.cs` extended with the VWAP and its bands; what it has to settle is below.

**The width is the volume-weighted population standard deviation about that basis**, over the same anchored window:

```text
sigma[i] = sqrt( Σ v_j (p_j − vwap[i])^2 / Σ v_j )   over j from the session anchor to i
```

`p` is `typical_price`, matching what the VWAP itself weights, and the divisor is the summed weight rather than a corrected one — the convention `nt8_stddev` already uses. `sigma` is 0 on an anchor bar, where one observation has no dispersion about its own mean, and `band_stretch` reads 0 rather than infinite there, so **no bar can be outside the band on the bar that anchored it**.

**Written as NinjaScript this is four running doubles in `OnBarUpdate`**, reset on `Bars.IsFirstBarOfSession`, and *not* a read of `OrderFlowVWAP`'s own standard-deviation bands:

```csharp
if (Bars.IsFirstBarOfSession) { origin = Typical[0]; cumV = cumVQ = cumVQQ = 0; }
double q = Typical[0] - origin;
cumV += Volume[0]; cumVQ += Volume[0] * q; cumVQQ += Volume[0] * q * q;
double c = vwap - origin;
double variance = cumVQQ / cumV - c * (2.0 * cumVQ / cumV - c);
```

**Hand-rolling it is the point.** `OrderFlowVWAP` does expose deviation bands, but its variance definition is not readable from the C# and the plausible candidates — volume-weighted against unweighted, population against sample — differ by enough to move which bars signal. A band the script computes itself is a rule this document can state and a probe can check, where a band read off a closed indicator is an assumption. **What the probe is for is therefore the basis, not the width**: the width is ours by construction, and the width is only meaningful if the VWAP under it is NT8's.

**The sums are taken about the session's first price rather than about zero**, which is the shifted-data variance algorithm and not a rearrangement anyone should undo. At a five-figure index price the unshifted form subtracts two numbers of order 4e8 to produce a variance of order 25, and loses most of the precision doing it; the shifted form agrees with the two-pass definition to under 1e-9 points over a session. `tests/test_indicators.py::test_session_vwap_dispersion_matches_the_two_pass_definition_at_index_prices` pins that against the definition written the obvious way. In NinjaScript the same subtraction is on the same two doubles, so the shift travels with the rule rather than being a Python detail.

**A warm-up gate is a rule here and has no Bollinger equivalent.** `vwap_min_session_bars` is bars since the anchor, `Bars.BarsSinceNewTradingDay` in NinjaScript. `BarsRequiredToTrade` counts from the start of the series and so does nothing at a session open, where a band built from a handful of observations is narrow enough to put ordinary bars several deviations outside it. Under a band lag the requirement is `vwap_min_session_bars + band_lag`, which also stops a lagged read reaching back across its own anchor into the previous session.

**Every other NT8 question this archetype raises is answered above and unchanged**, including the entry mechanism, the one-bar order lifetime, the two `EXIT_SIGNAL` exits and `IsExitOnSessionCloseStrategy`. The measurements the source produced, and the standing caveats on them: [roadmap.md](roadmap.md) §M26.4.

### M26.5 — what the signal bar has to look like, written before the Python (#221)

**Two requirements on the bar that signals, and neither changes anything else.** `signal_shape` asks the extended bar's own candle to have turned, and `min_one_sided_bars` asks the move into the band to have been one-sided. Everything above still describes the archetype: the depth threshold, the run length, the direction rule, all four stops, both target schemes and the session flatten are untouched, and `Archetype.tier2` stays `TIER1_ONLY`. The reasoning, and the measurements each produced: [roadmap.md](roadmap.md) §M26.5.

**Both read completed bars only, and both are one `if` in `OnBarUpdate` after the depth test.** They narrow which bars call `EnterLong()` / `EnterShort()`; the entry stays market-on-next-open and the one-bar order lifetime is unchanged.

**`signal_shape` is three shapes and an off value**, each written against the fade's own direction so the two sides mirror exactly — `dir` below is `+1` for a long and `-1` for a short:

| mode        | the rule                                                      | NinjaScript                                                          |
| ----------- | ------------------------------------------------------------- | -------------------------------------------------------------------- |
| `any`       | no requirement                                                | the depth test alone                                                 |
| `reversal`  | the body closed back towards the basis                        | `dir * (Close[0] - Open[0]) > 0`                                     |
| `reclaim`   | took out the previous bar's extreme and closed back past it   | `Low[0] < Low[1] && Close[0] > Close[1]`, mirrored on the short side |
| `rejection` | the close is `f` of the bar's range off the stretched extreme | `Close[0] - Low[0] >= f * (High[0] - Low[0]) && High[0] > Low[0]`    |

**A doji passes no shape on either side, and that is a deliberate departure from the ported archetypes.** `PullBackAndGo.cs` and `DeadCatBounce.cs` disagree with each other about equality — `Close[1] >= Open[1]` for green against `Close[1] < Open[1]` for red — and neither boundary is inherited here, because those mirror a C# that exists and this one does not yet. The strict comparison on both sides is what the single sign multiplier asks for: a bar that closed flat ran neither way, and a rule that admitted it on one side only would make the long and short arms different rules.

**A zero-range bar never passes `rejection`**, which is `_inverted_hammer`'s `body > 0` boundary applied to the range instead of the body. Without it the comparison is `0 >= f * 0` and every flat bar passes at every depth.

**`reclaim` reads `conditions.BarGeometry`'s extremes rather than a second copy of them.** `made_new_low` is `Low[0] < Low[1]` and `made_new_high` is `High[0] > High[1]`, both already built parameter-free for every dataset, and the fade's direction selects which one is the adverse extreme.

**`min_one_sided_bars` is a count over a window, not a run**, which is what separates it from `min_bars_outside`. In NinjaScript it is a loop over the last `oneSidedLookback` bars counting `dir * (Close[k] - Open[k]) < 0`, and the bars need not be consecutive nor outside the band at all:

```csharp
int oneSided = 0;
for (int k = 0; k < oneSidedLookback; k++)
    if (dir * (Close[k] - Open[k]) < 0) oneSided++;
if (oneSided < minOneSidedBars) return;
```

`conditions.rolling_count` is the Python, and **its window is truncated at the head rather than left undefined** — an early bar counts the bars that exist, so a threshold it cannot reach simply fails. `BarsRequiredToTrade` excludes those bars either way.

**There is no engulfing mode, and the reason is a measurement rather than a preference.** It was built, run over the MNQ continuous series and removed: [roadmap.md](roadmap.md) §M26.5 has the count and the mechanism.

### M26.6 — the recovery entry, written before the Python (#278)

**One rule, and it replaces which bar signals rather than adding a condition to it.** `entry_trigger` says which bar of an extension schedules the entry: `extended` is every rule above — a bar that is still beyond the threshold — and `recovery` is the bar that closes back **inside** the band after the run outside has ended. `recovery_fraction` says how far back inside counts. Everything else still describes the archetype: the depth threshold, the direction rule, all four stops, both target schemes, the market-on-next-open entry, the one-bar order lifetime and the session flatten are untouched, and `Archetype.tier2` stays `TIER1_ONLY`. The reasoning and the measurements: [roadmap.md](roadmap.md) §M26.6.

**Why it cannot be a fifth `signal_shape`.** Every mode in that table is evaluated on a bar that is still beyond the threshold, and the threshold is defined on the close — so a bar whose body ran back towards the basis has usually stopped being 2σ from it, which is what makes a reaction expensive to require and what removed the engulfing mode. The reaction `Trading-Docs` describes happens *after* the extension: price exceeds the level, fails to hold, and returns inside. That is a different trigger.

**The whole rule is a state block captured at the end of one bar and read at the next.** Four running values rather than one, because the signal bar is inside the band and every one of them describes bars that are not:

```csharp
// read what the previous bar carried in, before this bar updates it
if (runBars >= minBarsOutside && runSide != 0)
{
    double stretch = (Close[0] - basis) / sigma;
    if (Math.Sign(stretch) == runSide
        && Math.Abs(stretch) < entryStd
        && Math.Abs(stretch) <= recoveryFraction * entryStd
        && (maxEntryStd == 0 || runStretch <= maxEntryStd))
        EnterLong();   // mirrored on the short side
}

// then update the run this bar leaves behind
double s = (Close[0] - basis) / sigma;
int side = Math.Abs(s) >= entryStd ? Math.Sign(s) : 0;
if (side == 0) { runBars = 0; runSide = 0; }
else if (side != runSide) { runBars = 1; runSide = side; runLow = Low[0]; runHigh = High[0]; runStretch = Math.Abs(s); }
else { runBars++; runLow = Math.Min(runLow, Low[0]); runHigh = Math.Max(runHigh, High[0]); runStretch = Math.Abs(s); }
```

**`min_bars_outside` no longer includes the signal bar, and that is the rule rather than an accident.** Under `extended` the run ends *at* the signal bar; under `recovery` it ends at the bar before it. `outside_run_length(..., ends_before=True)` is the one-bar shift and `runBars` read before its own update is the NinjaScript, which is the same statement written twice.

**A close exactly on the basis passes on neither side.** `Math.Sign(stretch)` is `0` there and no run carries a side of `0`, so the comparison fails on both arms. This is §M26.5's boundary rule reached again — a doji passes no shape on either side because one sign multiplier means the long and short arms have to be the same rule — and it is why the Python's `returned_inside` carries `stretch != 0.0` rather than leaning on `fade_direction`, which assigns a stretch of exactly zero to the short side. Without it a recovery all the way to the mean would be a short entry and never a long one.

**`recovery_fraction` is a share of `entry_std` and not a standard deviation of its own.** `1.0` is the band edge itself, so the requirement degenerates to "back inside at all" and the two comparisons above collapse into one; anything less is a depth. A share rather than a level because `entry_std` is swept — at an absolute 1.5σ the requirement is a different fraction of the distance travelled at each depth threshold, and cells cut by it could not be read against each other. It is refused at `0`, where the close would have to sit exactly on the basis and the rule above passes nothing.

**The two things that read the run's own bars are read one bar back too, and neither would have failed loudly.** `STOP_EXCURSION` hangs off the adverse extreme of the run being faded and `exit_on_invalidation` compares the close against that same extreme; `run_extreme` is `nan` on a bar that is not outside, so on a recovery signal bar both would have read `nan`. A `nan` stop makes `candidate_risk >= min_risk` false and the entry is declined — every `STOP_EXCURSION` trade silently gone rather than an error — and a `nan` comparison is false, so the invalidation exit would simply never fire. `runLow`/`runHigh` above are the NinjaScript and `lagged(extremes, 1)` is the Python.

**`max_entry_std` gates the bar the extension was measured on, which under this trigger is not the signal bar.** The ceiling exists to refuse a move that has become a trend rather than a stretch, and the signal bar is inside the band by construction — so gating it would make the parameter inert at every value, which is the blind spot `.claude/rules/sweep-and-context.md` names rather than a safe default. `runStretch` is the value the C# carries for it.

**Nothing else moves.** The entry is still market-on-next-open with no trigger price, so the fill rules, the resting-order lifetime and the force-flat handling are unchanged, and `signal_shape` still reads the signal bar's own candle and composes with this rather than being replaced by it.

### M26.7 — the inverted signal, written before the Python (#279)

**One rule, and it changes which side a bar is traded on rather than which bars signal.** `invert_signal` enters with the extension instead of against it: long a close above the upper band, short one below the lower. Every signal rule — the depth threshold and its ceiling, the run length, both entry triggers, the signal-bar shapes and the one-sided count — still reads the extension exactly as above, so an inverted combination fires on the same bars as its fade and the pair differs in the side alone. The market-on-next-open entry, the one-bar order lifetime and the session flatten are untouched, and `Archetype.tier2` stays `TIER1_ONLY`. Nothing has been swept with it yet.

**It is not a free toggle, because five things downstream of the entry read the fade's direction.** Three exit rules would be wrong inverted — the R target's cap at the basis, the excursion stop and the band stop — and the stretch target and the sizing thesis need a definition of their own. Each is below. The swing, ATR and catastrophe stops are a bar extreme or a distance off the fill signed by the trade's direction, so they need nothing.

**`trade_long` and `trade_short` name the side traded, not the extension.** Under the inversion `trade_long` takes the extension above the band, which the fade shorts, so a fade with `trade_long = false` and an inverted combination with `trade_short = false` trade the same bars:

```csharp
double stretch = (Close[0] - basis) / sigma;
int fadeSide = stretch < 0 ? 1 : -1;                  // the side every signal rule reads
int dir = invertSignal ? -fadeSide : fadeSide;        // the side traded
if (signal && dir > 0 && tradeLong) EnterLong();
else if (signal && dir < 0 && tradeShort) EnterShort();
```

**The shapes and the one-sided count read the extension, not the trade.** `reversal` still asks for a body closing back towards the basis, so a shaped inverted entry is a breakout taken on a bar that has turned against it. That is the cost of keeping the bars identical, and a campaign crossing the inversion with a shape should know it is measuring that.

**A stretch target is measured past the signal bar's close, so every level starts ahead of it:**

```csharp
double target = Close[0] + dir * level * sigma;
```

`sigma` is the one the signal read, at its band lag, exactly as a fade's target reads it. Measured past `entry_std` instead, the close that signalled is often already beyond the target: over the 1-minute continuous series on a 20-bar band at 2σ, 30% of signals on both roots close past +0.5σ and 7% past +1.0σ. Most of those targets would already be passed at the next open and leave there by the rule below, as instant round trips. Levels at or below `0` are refused, because they sit at or behind the close.

**An R target is not capped at the basis.** The fade caps it because a target past the mean is not a mean-reversion target; inverted, the basis is behind the fill, so the cap would put every target behind it. `SetProfitTarget(CalculationMode.Price, fill + dir * risk * r * tpMultiplier)`.

**The excursion stop hangs off the base of the run, and the invalidation exit reads the same level.** `run_extreme` takes the side traded, so inverted it is the lowest low of a run above the band for a long and the highest high of a run below it for a short — where the breakout started. Read off the fade's side it would sit beyond the fill, and the minimum-risk check would decline every entry silently. The NinjaScript is the same expression as the fade's, because §M26.6's `runLow` and `runHigh` track the run whichever side it is on:

```csharp
// at the signal bar, held for the life of the trade
entryRunBase = dir > 0 ? runLow : runHigh;
SetStopLoss(CalculationMode.Price, entryRunBase - dir * stopOffsetTicks * TickSize);
// at every later close
if (exitOnInvalidation && dir * (Close[0] - entryRunBase) < 0) ExitLong(); // mirrored on the short side
```

The level is fixed at the signal bar: `runLow` and `runHigh` keep moving with the run after the entry, and the invalidation exit reads the level the stop was placed at, not the run's current one.

**Under the recovery trigger the signal close has come back inside the band, often through the base of the run**, so inverted, the excursion stop is declined by the minimum-risk check and the invalidation exit fires at the first close, on a share of signals that grows with `recovery_fraction`'s depth. The fade has neither problem, because its close comes back away from its stop. Neither combination is refused, but crossing the inverted recovery trigger with either measures the trigger's depth rather than the stop.

**The band stop sits back inside the threshold, on the trade's side of the basis:**

```csharp
double stop = invertSignal
    ? basis + dir * (entryStd - bandStopStd) * sigma    // back inside the band the close broke out of
    : basis - dir * (entryStd + bandStopStd) * sigma;   // §M26.8
```

The same `band_stop_std` values therefore stop at the 1σ band rather than the 3σ one at `entry_std = 2.0`, and `0` is allowed here, where it is the threshold the close broke out through, rather than refused as it is on the fade. A value at or past `entry_std` puts the level at or beyond the basis, which is a wide stop rather than a refused one. The minimum-risk refusal declines an entry whose fill is at or past the level, which under the recovery trigger is typically a close that came back inside by more than `band_stop_std`.

**The sizing thesis is a breakout's.** The confluence size reads `sizing_thesis` for its regime and volume labels: the fade's is `ROTATION`, favouring a consolidating regime and thin volume, and the inversion's is `EXPANSION`, favouring a directional regime and heavy volume — OpeningRange's rule for its breakout entries (§M47). The trend, higher-timeframe and VWAP labels already read the side traded through `long_side`.

**The random-entry arm substitutes the signal and never the side**, so a drawn bar is traded on the inverted side as well. A drawn bar whose stop level is on the wrong side of its fill is still declined, as it is under the fade's excursion stop, so under the inverted band stop the null is drawn only from bars beyond `entry_std - band_stop_std`; read a band-stop null with that in mind.

#### A target the entry bar opened past

**A fade's basis is passed when the next bar opens beyond it, and so is a capped R target; an inverted target is when the open gaps past it.** Such a leg leaves by the shared rule, § "A limit order the market has passed fills at the nearest price the bar traded", as a target with no slippage. The trade is kept, because NinjaTrader cannot refuse a market entry, and the legs whose targets are still ahead rest as usual. #451 first closed such a leg at the entry bar's open; #452 measured NinjaTrader and replaced that with the shared rule.

### M26.8 — the stop on the band itself, written before the Python (#280)

**One rule, and it adds a fifth place the protective stop can go.** `stop_mode` at `band` puts the stop on the channel the entry was measured against, `band_stop_std` standard deviations past the threshold that signalled. Everything else still describes the archetype: the depth threshold, the run length, the direction rule, both entry triggers, both target schemes, the market-on-next-open entry, the one-bar order lifetime and the session flatten are untouched, and `Archetype.tier2` stays `TIER1_ONLY`. The reasoning and the measurements: [roadmap.md](roadmap.md) §M26.8.

**It is the level §M26 specified and never built.** That section's geometry table names the stop as "outside the band. Either `atr_bracket_distance` or `basis ∓ stop_std · σ`", and only the first of the two was written. The four modes that existed are a distance off the fill (`atr`, `catastrophe`) or a bar extreme (`excursion`, `swing`); none of them is a level on the channel, so none had a distance denominated in the units the entry threshold is written in.

**The level is a stretch coordinate signed away from the basis, which is the target arithmetic with one sign flipped:**

```csharp
double level = entryStd + bandStopStd;
double stop  = basis - dir * level * sigma;   // dir is +1 for a long, -1 for a short
SetStopLoss(CalculationMode.Price, stop);
```

`basis` and `sigma` are the **signal** bar's, read exactly as a `TARGET_STRETCH` leg reads them — `Bollinger.Middle[0]` and `StdDev(period)` under the Bollinger source, the four running doubles of §M26.4 under the VWAP one. So the whole rule is a price the script already holds, and `SetStopLoss` against a price is what every other mode here already compiles to.

**`band_stop_std` is measured past `entry_std` rather than stated as an absolute level, and that is the rule rather than a convenience.** `entry_std` is a swept axis, so a fixed 3σ stop sits *inside* the entry threshold wherever that axis reaches 3.0 and the minimum-risk check then declines the whole cell. Measuring past the threshold makes the same value the same distance beyond wherever the entry was taken, which is the property cells cut by it need to be readable against each other. It is §M26.6's `recovery_fraction` argument reached from the other side, and it is refused at `0`, where the stop is the threshold the signalling close has already passed.

**No floor and no offset, for two different reasons.** The dollar floor applies to `atr` alone because only that mode is a distance rather than a level — §M26's rule, unchanged. The tick offset that `excursion` and `swing` carry is *not* applied either: those levels are prices the market traded at and can be expected to be tested to the tick, where a band level is a statistic about the bars rather than a price anything rests at.

**The minimum-risk refusal is the existing one and it binds here for a new reason.** A stop at or through the price it protects is not a stop order (§M18), and `simulate_elasticband` declines the entry when `candidate_risk < STOP_MIN_TICKS × tickSize`. A band stop reaches that boundary from two directions the other modes do not: a narrow band puts the level within a tick of the fill, and a gap through the level between the signalling close and the next open puts the fill on the wrong side of it entirely.

**Both entry triggers read the same band, which is what separates this stop from `excursion`.** §M26.6 had to move three reads one bar back because `run_extreme` is `nan` on a bar inside the band. The basis and the dispersion are defined on every bar, so the level is the signal bar's own under `extended` and under `recovery` alike, and no lag travels with it.

**R means a fourth thing under this stop, and it is the only one that is exact.** With the target at the basis the reward-to-risk is `entry_std / (entry_std + band_stop_std)` by construction, identical on every combination sharing that pair and *always below 1*. §M26 recorded three meanings for R in this project; this is the arithmetic that section predicted for a σ stop with a basis target, arriving with the mode that finally implements it.

### M28 — the opening-range rules, written before the Python (#236)

**Written down before the Python existed and the Python written to it**, as §M26 was. There is still no NinjaScript, so nothing here is backed by a trade list, and each item names the NinjaScript it would be written as — a rule chosen at design time that NT8 cannot express makes the archetype unreconcilable later. The design and what was deferred are in [roadmap.md](roadmap.md) §M28.1; only the rules are here.

`Archetype.tier2` is `TIER1_ONLY`, and stays there until a trade list has been diffed against it.

**The range window is a wall-clock window on both sides, so the two forms are the same test.** `sessionrange` counts minutes from the *template's* 18:00 ET open, which `resample.minutes_since_open` computes from the wall clock and not from the session's observed first bar — so minute 930 is 09:30 ET on every session, and the NinjaScript form is the obvious one:

```csharp
if (Bars.IsFirstBarOfSession) { rangeHigh = double.MinValue; rangeLow = double.MaxValue; barsInRange = 0; }
if (ToTime(Time[0]) > 93000 && ToTime(Time[0]) <= 100000)
{ rangeHigh = Math.Max(rangeHigh, High[0]); rangeLow = Math.Min(rangeLow, Low[0]); barsInRange++; }
```

**This is the opposite of the no-entry window's trap** — "A no-entry window before the session close" above records that a rule counting back from the *observed* session end cannot be reconciled against a C# reading the wall clock. A rule counting forward from the template's open can, because that is the wall clock.

**A session missing any of its window bars has no range.** `barsInRange` has to reach `windowMinutes / barMinutes` or the session is skipped. Measuring the range over whatever bars arrived would give a narrow range and so a tight stop on precisely the sessions whose data is worst.

**The order rests for the session, and route 3 is what expresses it.** The trigger is a level that persists rather than a value computed from the signal bar, so `EnterLongStopMarket(rangeHigh + entryOffsetTicks * TickSize)` resubmitted at every bar close reproduces a resting order — and § "Route 3" in [roadmap.md](roadmap.md) establishes that in Tier 1 this is not an approximation of a GTC order but identical to one, because the fill test is the same per-bar OHLC comparison either way. **`entry_order_lifetime_bars` is therefore not needed and is not built.**

**A stop entry at or through the market is never submitted, and here it binds constantly.** §M18's rule, from "A stop-market entry must sit strictly beyond the market": the order is refused on any bar whose close has already reached the trigger — which after a break is most of them. DeadCatBounce is immune to this by construction and the opening range is not, so `entry_offset_ticks` defaults to **1 rather than 0**: at 0 a bar closing exactly on the range extreme can never submit.

**The fill test is DeadCatBounce's, unchanged.** An open at or beyond the trigger fills at the open, because a stop is a market order once triggered; otherwise the bar's favourable extreme must reach the trigger and the fill is at the trigger. `filled_at_open` is false either way, so the gapped-stop rule stays off the entry bar exactly as it does there.

**The whole bracket is computed from the trigger, not from the fill.** `SetStopLoss` and `SetProfitTarget` are set when the order is submitted and the trigger is the only price known then. Risk is `trigger − stop`; a gapped fill is worse than planned and its R is measured against the plan. This is what the reconciled DeadCatBounce port already does.

**Two stop schemes, and only one of them is floored:**

| scheme       | stop                                                          | floored |
| ------------ | ------------------------------------------------------------- | ------- |
| the opposite | `rangeLow - stopOffsetTicks * TickSize`, mirrored for a short | no      |
| ATR          | `trigger - Math.Max(atr * multiple, floor / pointValue)`      | yes     |

Same rule as §M26's: **only a distance is floored, never a level.** `min_bracket_dollars` is per contract and converted through `instruments.py`, and it is inert under the opposite-extreme stop — as `stop_offset_ticks` is under the ATR stop. Neither is visible to `dead_axes`, which is ElasticBand's blind spot reached again.

**Two target ladders.** The shared R ladder scaled by `tpMultiplier`, or per-leg multiples of the **range width** measured from the trigger. A width multiple is already a distance, so `tpMultiplier` is not applied to it — applying both would be one axis expressed twice. Either way the legs are prices by the time `bracket.py` sees them and nothing in the bracket engine changes.

**A per-session entry cap, which no other archetype has.** An `int` reset on `Bars.IsFirstBarOfSession` and incremented in `OnExecutionUpdate`, compared against `maxEntriesPerSession` before each submission. Entirely expressible, and it is what makes the one-shot form every published opening-range result measures reachable at all — [roadmap.md](roadmap.md) §M28, finding 4.

**One side per instance, and this is a limitation rather than a choice.** "The managed approach refuses the opposite-direction submission outright" below kills the classic form of both stops live with the first fill winning. §M28's finding 1 left route 3's plain stops untested, and a sixth probe scenario has since measured them refused the same way (#51), so the archetype is one-sided per combination, `direction` is a swept axis, and no combination ever holds two orders. The simulator has the same limit from the other side — one `pending_*` slot per loop.

**Flat before the session close binds hard, and the live share is the thing to read.** A cash-anchored entry around 09:45 ET against a 17:00 close leaves the hold bounded by the geometry rather than the clock, but a runner leg with no target reaches the flatten every time: `session_close_share` runs near **half of all legs**, which changes what the results mean. It is produced by `tools/campaign_sweep.py --strategies OpeningRange --split` and read out of OpeningRange's campaign database; [roadmap.md](roadmap.md) §M28.1 has what it implies.

### M28.2 — the fade, the retest and the stop fraction, written before the Python (#237)

**The same discipline as §M28 and the same standing: still no NinjaScript, so nothing here is backed by a trade list.** Each item names what it would be written as. The design and what was deferred: [roadmap.md](roadmap.md) §M28.2.

**The stop fraction is a level, so it is not floored.** `rangeHigh - stopRangeFraction * (rangeHigh - rangeLow) - stopOffsetTicks * TickSize`, mirrored for a short, measured from **the extreme the order rests at** rather than from the trigger. It replaces §M28's two-scheme table with one axis: at `1.0` it is the opposite-extreme stop exactly, offset included, and at `0.5` it is the midpoint stop. `min_bracket_dollars` stays inert under it for §M26's reason — only a distance is floored, never a level.

**A fade and a retest need a break that already happened, which is one `bool` per session.** Reset on `Bars.IsFirstBarOfSession` and set from `High[0]`/`Low[0]` against the level plus `breakConfirmTicks`; nothing reads a bar it could not have seen, and nothing reads a *future* bar, so it is expressible as written. It is **not** reset by a fill: a session's second entry re-uses the break its first one was armed by, which is what the per-session cap is there to bound.

**A fade rests its stop at the extreme it needs broken, so its trigger is the range's *other* side.** `EnterLongStopMarket(rangeLow + entryOffsetTicks * TickSize)` after price has traded below `rangeLow`. The submittability rule is §M18's unchanged — the order is only accepted while the close is still below the trigger, which is exactly the state "price is outside the range" — so no new refusal is introduced.

**A fade cannot take the opposite-extreme stop, and this is refused rather than swept.** Its entry level *is* the extreme that mode names, so the stop would land `stopOffsetTicks` from the entry and the mode would be the fraction stop at a fraction of zero. `OpeningRangeParams` raises instead of running the duplicate, because a swept space with two names for one thing is the blind spot `dead_axes` cannot see.

**The retest is the first limit entry in the registry, and its two halves are the stop entry's mirror:**

|                           | stop entry                                | retest's limit                                       |
| ------------------------- | ----------------------------------------- | ---------------------------------------------------- |
| NinjaScript               | `EnterLongStopMarket(level + offset)`     | `EnterLongLimit(level - retestOffset)`               |
| rests                     | beyond the market                         | inside the market                                    |
| a bar that gaps past it   | fills at the open, **worse** than planned | fills at the limit, or the bar's nearest price       |
| merely reaching the price | fills — a stop triggers on touch          | does **not** fill under `IsFillLimitOnTouch = false` |
| slippage                  | applied                                   | **never applied**                                    |

The last three rows are rules this project established for *exits* — "A limit order the market has passed fills at the nearest price the bar traded", "Limit orders must trade **through**, not touch" and the targets taking no slippage — reaching the entry, and #454's probe runs measured the first two on entry limits as well. `bracket.limit_filled` and `bracket.limit_fill_price` are the one implementation, and the entry reads them at `-direction`, because the limit is favourable from the other side.

**A marketable limit is not sent, and that is the archetype's rule rather than NinjaTrader's.** §M18 establishes that NT8 declines a stop entry at or through the market. A buy limit at or above the close is not declined: #454 sent 5,000 such entries, and NinjaTrader took every one and filled every one the next bar traded through, by the rule above. The simulation still does not send one, so a retest never enters at a price the market has already left, and a port has to say the same thing in its own C#: send `EnterLongLimit` only while the limit is below `Close[0]`, and `EnterShortLimit` only while it is above.

### M28.6 — the rejection entry, written to the same standing as §M28.2 (#255)

**Still no NinjaScript, so nothing here is backed by a trade list either.** The design, and what it is waiting on before it is swept: [roadmap.md](roadmap.md) §M28.6.

**The rejection is one `EnterLongLimit` at the range's own extreme, with no arming condition at all.** `EnterLongLimit(rangeLow + entryOffsetTicks * TickSize)` for a long and `EnterShortLimit(rangeHigh - entryOffsetTicks * TickSize)` for a short, resubmitted at every bar close from the bar the range completes on. There is no `bool` to reset on `Bars.IsFirstBarOfSession` and no `High[0]`/`Low[0]` comparison to make: the fill test **is** the condition, because a limit `entryOffsetTicks` inside the low fills exactly when price comes that close to the low and no closer.

**Every fill rule it takes is one already written down.** §M28.2's retest table applies unchanged — fills at its price or the nearest one the bar traded, does not fill on a touch under `IsFillLimitOnTouch = false`, takes no slippage, and a marketable limit is not sent. That last is the archetype's rule rather than NinjaTrader's, and a port carries it as a guard on `Close[0]`.

**The offset runs inward here and outward for a breakout, and it may be zero.** `entryOffsetTicks` is measured past the level in the direction traded, and this mode's level is the extreme *against* that direction. §M28's reason for defaulting it to 1 — a bar closing exactly on the level can never submit a stop entry, because NT8 declines a stop at or through the market — does not reach a limit, which is accepted from any bar that closed on the range's side of it.

**It refuses the opposite-extreme stop for the fade's reason.** Its entry level is the extreme `ORB_STOP_OPPOSITE` names, so the stop would land `entryOffsetTicks + stopOffsetTicks` from the entry and the mode would be the fraction stop at a fraction of zero. `OpeningRangeParams` raises rather than sweep the duplicate.

### M28.10 — the trailing follow-through, written to the same standing as M28.2 (#261)

**Still no NinjaScript, so nothing here is backed by a trade list either.** The measurement that produced it and the verdict it reached: [roadmap.md](roadmap.md) M28.10.

**Follow-through is a completed-session statistic, and that is what makes it expressible.** One `double` per session — the further of the two moves beyond the range, divided by the range width — accumulated over the bars past the window and closed off at the session boundary:

```csharp
if (Bars.IsFirstBarOfSession && rangeComplete)
{ double beyond = Math.Max(reachHigh - rangeHigh, rangeLow - reachLow);
  history.Add(Math.Max(beyond, 0) / (rangeHigh - rangeLow)); }
reachHigh = Math.Max(reachHigh, High[0]); reachLow = Math.Min(reachLow, Low[0]);
```

**The scale a session trades on is the median of the sessions strictly before it**, so no session contributes to its own geometry. A ring buffer of the last `followThroughSessions` values, taken at the session open and held for the whole session; nothing here reads a bar it could not have seen, which is the property the whole axis is worthless without.

**A session with fewer than `followThroughSessions` completed values submits no order.** The same rule as "A session missing any of its window bars has no range" one level up: a geometry that cannot be stated is refused rather than approximated from what happens to be there. On a 250-session lookback that costs the first year of the archive.

**The scale multiplies the range width and reaches nothing else.** `stopRangeFraction * (rangeHigh - rangeLow) * scale` and `trigger + targetWidthMultiple * (rangeHigh - rangeLow) * scale`, each under its own half of `followThroughScaling`. It is inert against the R ladder and against the opposite-extreme stop, both of which state their geometry in another unit — `OpeningRangeParams` raises rather than sweep a combination where the axis does nothing, which is the blind spot `dead_axes` cannot see.

**At `ORB_SCALE_NONE` the arithmetic is what it always was.** The scale is one everywhere and the loop multiplies rather than branches, so every stored OpeningRange row is reproducible unchanged. Checked: byte-for-byte identical over the trade-log gate's fourteen files and over 5,322 OpeningRange legs.

### M34 — the pullback rules, written before the Python (#309)

**Every rule below was written down before the Python existed, and the Python was then written to it** — §M26's order rather than §M18's. There is no NinjaScript, so nothing here is backed by a trade list, and each item names the NinjaScript it would be written as: a rule chosen at design time that NT8 cannot express makes the archetype unreconcilable later, and the exploration is then wasted rather than merely unvalidated. The reasoning behind the choices, and the alternatives rejected, are in [`m34-ema-pullback-spec.md`](findings/m34-ema-pullback-spec.md); only the rules are here.

`Archetype.tier2` is `TIER1_ONLY`, and stays there until a trade list has been diffed against it.

**The trend is the comparison §M18 already makes, read on every bar instead of on the cross.** For a long it is `fast[0] > slow[0]`, each of them an `EMA(Period)` under `Calculate.OnBarClose`, and the strict inequality on both sides means two averages exactly equal are neither an uptrend nor a downtrend. That is `crossover.regime_direction`'s boundary for the *direction* series, which resolves a tie to `SHORT`; the entry never reaches the tie, because both arms test strictly.

**The extension is a bar counter, not an indicator.** In NinjaScript, `if (Low[0] > ema[0] && ema[0] > slow[0]) barsExtended++; else barsExtended = 0;` at the end of `OnBarUpdate`, and the entry tests the value the *previous* bar left — equivalently `barsExtended` read before this bar's update. `conditions.consecutive_true` shifted one bar is the same series. A bar counts only if its **whole range** is beyond the average, because a bar that traded through it and closed back above it is the pullback rather than the extension.

**The touch bar ends the run.** So `MinBarsExtended` also reads as "how long since price last reached the average", and a signal that some other condition refuses still resets the counter. Deliberate: a chop of repeated touches then produces at most one signal per genuine extension.

**The averages are read at `[0]`, which includes the signal bar's own close.** Self-referential in exactly the sense §M26 records for the band: every input is a completed bar at or before *i*, the entry is at *i+1*'s open, and `Calculate.OnBarClose` gives NinjaScript the same value. It is not lookahead, and unlike the band there is no `[1]` variant, because an average of a pullback is not damped by the pullback the way σ is widened by the move that stretches it.

**The touch is `Low[0] <= ema[0]` for a long**, with the depth the bar has to reach set by `TouchMode`: the shallow mode adds `Close[0] > ema[0]`, the deep mode `Close[0] <= ema[0]`, and the third takes either. **A close exactly on the average is a close through it** — §M26.5's doji boundary, for the same reason: one sign multiplier means the long and short arms have to be the same rule.

**The trend-intact test is two rules, not one.** `Close[0] > slow[0]` is unconditional — a bar that closed through the level the stop is about to sit on has already invalidated the trade — and `RequireSlowIntact` adds `Low[0] > slow[0]`, which is the harder form and a swept toggle.

**The entry is market-on-next-open, and §M18's consequences apply unchanged.** `EnterLong()` / `EnterShort()` under `Calculate.OnBarClose` submit at the close of bar *i* and NT8 fills at the open of bar *i+1*. There is no trigger price, so no "no touch, no fill" and no submittability rule; a resting order is tested for a fill on the force-flat bar and the position it opens is flattened at that bar's close.

**The protective stop is the slow average as it stood on the signal bar.** `SetStopLoss(CalculationMode.Price, slow[0] - StopOffsetTicks * TickSize)`, issued in the same `OnBarUpdate` as the entry, so the level is fixed before the fill and never re-read from the bar the fill happens on. It is the shared crossover loop's third stop mode — a level it is handed rather than a distance it computes — and `nqbt` passes the slow average's own series as that level.

**It takes no dollar floor.** §M18 floors the ATR stop because a quiet regime otherwise sizes a bracket smaller than the round trip costs to trade, and does not floor the swing stop because a structural level is not a distance. An average is a level, so the same reading applies, and §M26.8's band stop is the third instance of it. What replaces the floor is the refusal below.

**It does take a tick offset, and that is a decision against §M26.8 rather than an oversight.** §M26.8 gives the band stop no offset on the grounds that `stop_offset_ticks` exists for levels the market traded at and a band is a statistic about the bars; a moving average is the same kind of object by that reading, and EmaCrossover's trail is the opposite precedent — two ticks, so the stop is not sitting exactly on the level it follows. The offset is kept because a well-watched average is repeatedly touched and a stop exactly on it is taken out by a touch that respected the level, and because `stop_offset_ticks = 0` reproduces §M26.8's reading exactly and is swept.

**The minimum-risk refusal binds here for a third reason.** A stop at or through the price it protects is not a stop order (§M18), and the entry is declined when `candidate_risk < STOP_MIN_TICKS × tickSize`. Two averages converging put the level within a tick of the fill; a gap between the signalling close and the next open puts the fill on the wrong side of it entirely. Both are ordinary states here rather than corner cases, which is the same thing §M26.8 says about a narrow band.

**R is the gap between the two averages, so it is structural.** Not volatility-scaled like EmaCrossover's ATR stop and not a fixed geometry, so **the target ladder's numbers are comparable to no other archetype's at the same values** — the same trap as comparing profit factor across bar resolutions. It also varies far more trade to trade than an ATR stop's does, because two averages converging is a routine state.

**There is no round-number avoidance.** The rule is only meaningful on prices that traded and needs the `PriceBasis.RAW` refusal beside it; a stop on a continuously-varying average lands exactly on a multiple only by coincidence, so the two axes would be inert almost everywhere.

**The trend-flip exit is §M18's `EXIT_SIGNAL`, and it is off by default.** `if (fast[0] < slow[0]) ExitLong();` decided in `OnBarUpdate`, so it fills at the next bar's open and takes precedence over the stop and the targets on that bar. Off by default because the strategy as specified is the stop and the targets; on, it is the same market exit EmaCrossover already produces.

**The trailing stop is EmaCrossover's ratchet over a different level, unchanged.** Off by default, one cadence — the close of every completed bar — and it sits on top of the level stop rather than replacing it.

**It can trail the slow average that placed the stop, at the offset that placed it** (#313). With `trail_on_slow` the ratchet's level is `slow[0] - direction * StopOffsetTicks * TickSize` rather than the third average and `trail_offset_ticks`, so in NinjaScript it is the fixed stop's own `SetStopLoss(CalculationMode.Price, …)` re-issued from `OnBarUpdate` whenever that level is nearer the market than the stop resting — EmaCrossover's cadence and EmaCrossover's comparison. Three choices, made rather than inherited, and argued in [`m37-ema-pullback-trail-on-slow.md`](findings/m37-ema-pullback-trail-on-slow.md):

- **It is a ratchet, not a follow.** An average that retreats leaves the stop where it got to; a stop that followed it back would let a losing trade widen its own risk.
- **The offset is `StopOffsetTicks`.** An average that has not moved therefore leaves the stop exactly where it was placed; reading `trail_offset_ticks` instead would move it on the first trailed bar with the average unmoved. `trail_ma_kind`, `trail_ma_period` and `trail_offset_ticks` are unread in this mode, and `dead_axes` refuses them as axes.
- **It arms at the entry bar's close**, the first completed bar after the fill — where the average has moved one bar since the signal bar placed the stop. Arming after the first target instead is a different rule and not this one.

### M39 — the pullback's confirmation entry (#311)

**The same standing as §M34: no NinjaScript, so nothing here is backed by a trade list**, and each rule names the NinjaScript it would be written as. Why it is a mode on EmaPullback rather than an archetype of its own, and what the campaign measured: [`m39-ema-pullback-confirmation-entry.md`](findings/m39-ema-pullback-confirmation-entry.md).

With `confirm_entry` on, the signal is §M34's unchanged and only the order changes. **Every rule below is an existing one reaching this archetype**, and the fill test is `bracket.stop_entry_fill`, which OpeningRange's stop entries already call.

**The order is a stop beyond the signal bar's extreme.** `EnterLongStopMarket(High[0] + EntryOffsetTicks * TickSize)` for a long, submitted in the same `OnBarUpdate` the market entry would have been, and mirrored through the low for a short. The side is §M34's trend comparison at the signal bar.

**A stop entry at or through the market is never submitted** — §M18's rule, "A stop entry must sit beyond the market to be submitted". It binds on a signal bar that closed on its own extreme, which is why `entry_offset_ticks` defaults to **1**, as OpeningRange's does: at 0 that bar can never submit.

**The fill is DeadCatBounce's.** A gap through the trigger fills at the open, otherwise the bar has to reach the trigger and fills there, and no touch is no fill. `filled_at_open` is false either way, so the gapped-stop rule stays off the entry bar.

**The whole bracket is computed from the trigger, not the fill.** `SetStopLoss(CalculationMode.Price, slow[0] - StopOffsetTicks * TickSize)` and the targets are set before the order is submitted, from the signal bar's slow average and from the trigger. Risk is `trigger − stop` and a gapped fill is worse than planned, which is OpeningRange's rule and the reconciled DeadCatBounce port's. **So R here is not the market entry's R**: it is measured from a price at least a tick beyond the signal bar's extreme rather than from the next open, and it is the wider of the two on every trade that fills.

**The minimum-risk refusal is §M34's**, applied at submission: a stop within `STOP_MIN_TICKS` of the trigger is not submitted.

**The order rests for `entry_order_lifetime_bars`, live on the bars after the signal bar through that many.** At 1 it is the three-argument overload's lifetime. Above 1 it is route 1 with a bar counter and `CancelOrder`, or route 3 resubmitting the unchanged trigger, and § "An order is live through the bar at whose close its cancel is issued" is the measurement that makes the two the same. **It is tested on the force-flat bar and cancelled there**, which is § "`isLiveUntilCancelled` is honoured, and the session-close handler is what ends it", so no order rests into the next session.

**A later signal on the same side moves the resting order to its own bar** — a new trigger, a new stop and a new lifetime — and one refused as unsubmittable leaves the resting order alone. A NinjaScript does this by re-calling the entry method under the same signal name.

**An entry on the other side is ignored while an order is still working**, which is § "The managed approach refuses the opposite-direction submission outright". "Working" is the order's live bars, the signal bar's close through the last one, so it binds only above a one-bar lifetime: a signal on the bar after a signal bar cannot exist, because the signal bar reached the fast average and so ended the extension the next signal would need.

**An order is submitted only when flat at the signal bar's close.** The market entry may schedule an entry on the other side on a bar whose trend-flip, hold-limit or early exit is still pending, because both fill at the same open (below). A stop order submitted then would be an entry against an open position on the managed approach, which nothing here has measured, so the confirmation entry does not submit one. `if (Position.MarketPosition == MarketPosition.Flat)` is the guard, and § "The position guard has to read `Position`, not `PositionAccount`" is why it reads `Position`. All three exits are off in every campaign that has run this entry.

**The market entry beside a pending exit takes the other side only** (#393). This is the market entry's rule rather than the confirmation's, and `simulate_crossover` applies it to EmaCrossover too. An `EnterLong()` submitted in the same `OnBarUpdate` as an `ExitLong()` is submitted while `Position` is still long, so `EntriesPerDirection = 1` most likely ignores it, as § "The position guard has to read `Position`, not `PositionAccount`" records for a second entry on one side. An `EnterShort()` there is the opposite side, which the managed approach closes and reverses in one transaction, so the flip keeps the reopen §M18 describes; whether it still closes only once with the exit's own `ExitLong()` submitted beside it is unmeasured. A NinjaScript states the whole entry guard as `if (Position.MarketPosition == MarketPosition.Flat || (exitDue && Position.MarketPosition == MarketPosition.Long)) EnterShort();`, mirrored for a long, where `exitDue` is any market exit submitted at the same close. Nothing here has a trade list behind it. Before this, a same-side signal on that bar reopened at the open its exit filled at, as two fills at one price. The trend flip never reached it, because after a flip the signal is on the other side; the hold cap and the early exit did, on EmaPullback, and on EmaCrossover wherever a same-side signal can arrive while a position is open — with `exit_on_opposite_cross` off, at a `cross_lookback` above 1, or under the random-entry arm.

**The exits are the market entry's**: the stop and targets through `resolve_brackets`, the trail arming at the entry bar's close, and the trend-flip and hold-limit exits filling at the next open.

### The session end is the observed last bar, not the template's (#68)

`sessions.seconds_to_session_end` counts down to each trading day's **last in-session bar**, and `force_flat_mask` cuts that countdown at `ExitOnSessionCloseSeconds`. On a session that runs to 17:00 ET the two are the same thing, so the mask is unchanged there.

It changes the sessions that stop early. NT8's trading-hours template carries the holiday calendar, so on Thanksgiving, Christmas Eve or 3 July its `ActualSessionEnd` is 13:00 and it flattens there. Measured against the template's fixed 17:00 instead, nothing on such a session ever reached the cutoff and **the mask came back empty** — the position was never forced flat at all. `is_session_close` was already data-derived, so the two disagreed precisely on the days that mattered.

Counted over the archive as it stood when this landed: **109 of MNQ's 1,269 sessions and 65 of NQ's 1,210 had an empty mask**, 63 on each [root](../README.md#root) by an hour or more, and roughly two-thirds of those a 13:00 ET exchange half-day. The rest are sessions the data truncates rather than the exchange.

**The failure was worse than a position held too long.** On MLK 2024 the array runs `… 12:59, 13:00, 18:01 …`: the exchange shuts and the next session opens five hours later, so an entry order resting from the 13:00 bar lived its one bar into **the following session** and filled there, five hours and a session boundary from the signal that placed it. Every leg the trade-log gate lost is that or its sibling — an entry filled *on* a half-day's last bar, which `block_entry_at_session_close` now guards. The trade entered at 13:00 ET on Presidents' Day 2024 in the InsideBar reconciliation above is the second kind.

**The observed end approximates a calendar the data does not carry**, and it cannot tell an exchange half-day from a session whose tail is missing. Both now flatten, which is the safe direction: a session with no later bars has nowhere else to close the position, and the alternative is the order jumping the boundary above. One consequence to know — a position still open on the **last bar of the dataset** is now written as `session_close` rather than dropped unwritten.

### A no-entry window before the session close

```csharp
sessionIterator.GetNextSession(Now, true);
if ((sessionIterator.ActualSessionEnd - Now).TotalHours <= 1) return;
```

A parameterised window, not a boolean, and **distinct from `block_entry_at_session_close`**, which guards only a new signal on the force-flat bar. The comparison is `<=`, so a bar exactly an hour out is blocked and the gate admits `remaining > window`. `sessions.seconds_to_session_end` is the quantity both this and `force_flat_mask` are cut from, so a window and the flatten cannot drift apart, and since #68 both measure against the session's observed last bar — so the window closes an hour before a half-day's 13:00 close, as `ActualSessionEnd` does.

**`Now` is the wall clock, and that is a trap the port does not reproduce.** It resolves to `Core.Globals.Now` — `Connection.PlaybackConnection` is null in Strategy Analyzer — so the C# compares the end of *today's* session against the *real current time*, whatever bar is being processed. In a backtest that makes the rule either on for every bar or off for every bar, depending on the hour the run is started. The port implements the bar's own clock, which is what the rule means and what live trading does.

**So this is the one rule the two tiers cannot agree on by construction**, and a Tier-2 reconciliation of InsideBar needs `Now` replaced by `Time[0]` in the NinjaScript before it can mean anything. Until then, running the backtest more than an hour before the session close is the only configuration in which the C# and this port are testing the same rule.

### The maximum hold time, and why it is its own exit code

**Every archetype can cap how long a position is held**, not only ElasticBand, whose scheme C shipped one (§M26). `max_hold_bars` is off at `0` everywhere and nothing measured before this rests on it.

**It is a market exit decided in `OnBarUpdate`, so it fills at the next bar's open** — §M18's rule, the same one EmaCrossover's opposite-cross exit and ElasticBand's invalidation exit already take, and not `OnPositionUpdate`'s (§M23). In NinjaScript it is an `int` incremented in `OnBarUpdate` against a `MaxHoldBars` property, or equivalently `if (BarsSinceEntryExecution() >= MaxHoldBars) { ExitLong(); ExitShort(); }`. Like every market exit it takes precedence over the stop and the targets on the bar it fills on, because NT8's managed approach cancels a position's brackets when something else flattens it.

**The count is bars *since* the entry bar, and the fill is one bar after that.** The order goes in at the close of bar `entry_bar + max_hold_bars` and fills at the open of `entry_bar + max_hold_bars + 1`, so a leg's `bars_held` reaches `max_hold_bars + 1` rather than `max_hold_bars`. That is ElasticBand's arithmetic unchanged, which is why generalising it moved no stored number: `bracket.hold_expired` is now the one comparison, and every loop reaches it through `bracket.market_exit_reason`, which also orders it before the conditional early exit.

**It is `EXIT_TIME_LIMIT`, not `EXIT_SIGNAL`.** §M26 deliberately added no exit code and made `exit_on_invalidation` and `max_hold_bars` mutually exclusive instead, because a log carrying both could not say which fired. That trade stops being affordable once the cap reaches every archetype — three of them already spend `EXIT_SIGNAL` on a rule of their own, and the question the cap exists to answer is what it is worth, which is `tools/campaign_exits.py`'s decomposition by reason. So the code was added and the exclusion dropped; the two exits are now told apart in one log. **Where a bar is both, the archetype's own rule takes it**, since it would have closed the position on that bar anyway. On EmaCrossover and ElasticBand it shares the `pending_exit` those two already carried, so on EmaCrossover a signal on the other side at the hold limit reopens at the same open the exit filled at — the flip's own behaviour, deliberately not given a second answer. A signal on the same side opens nothing, on EmaCrossover and EmaPullback's market entry alike, because the position is still open when it is submitted (§M39).

**It is a bar count and not a duration**, so it means a different amount of time at each resolution exactly as a moving-average period does — [findings/m27-registry-campaign.md](findings/m27-registry-campaign.md) § "What the campaign could not test". Nothing scales it.

**It does not replace the session flatten and cannot.** Flat before the session close is an account rule rather than a parameter, and a cap longer than the session simply never binds.

### The conditional early exit

**Every archetype can close a position before its stop, target or flatten when a condition reading price, time or market context says the trade has failed** (#369). §M29 ruled out the unconditional form; this is the conditional one, and each rule below puts price or a context label back into the decision. **No NinjaScript has any of it, so nothing here is backed by a trade list**: each rule names the NinjaScript it would be written as, and a row using any of them is `TIER1_ONLY`, on the reconciled ports as much as on the originals. Every rule is off by default everywhere, and nothing measured before this rests on it.

The first tier of #369, the market exits of its second and all of its third are built, with their fields on every parameter class:

| rule                           | fields                                                                                         | fires at a bar close where                                                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| not working by bar N           | `early_exit_bars`, `early_exit_below_r`, `early_exit_measure`, `early_exit_counter_trend_bars` | the bar is `entry_bar + N`, or the shorter count for an entry against the trend, and open profit, or the best excursion so far, is below `early_exit_below_r` R |
| not working by minute N        | `early_exit_minutes`, `early_exit_below_r`, `early_exit_measure`                               | the bar is the first close at least N minutes after the entry bar's, and the same measure is below the same                                                     |
| losing before the close        | `early_exit_minutes_before_close`                                                              | the bar is inside the window before the session close and the position is losing                                                                                |
| regime change                  | `early_exit_on_regime_change`, `early_exit_only_if_losing`                                     | the regime label differs from the one on the bar before the entry bar                                                                                           |
| trend turns against            | `early_exit_on_trend`, `early_exit_only_if_losing`                                             | the trend label is against the position and was not on the bar before the entry bar                                                                             |
| invalidated on a close         | `early_exit_on_invalidation`, `early_exit_only_if_losing`                                      | the close is strictly beyond the adverse extreme of the bar before the entry bar                                                                                |
| stalled                        | `early_exit_stall_bars`, `early_exit_only_if_losing`                                           | the best favourable price has not improved for N closes                                                                                                         |
| leaving the entry's phase      | `early_exit_on_phase_change`                                                                   | the session phase differs from the one on the bar before the entry bar and the position is losing                                                               |
| higher timeframe turns against | `early_exit_on_higher_timeframe`, `early_exit_only_if_losing`                                  | the close is on the far side of the higher-timeframe average from the position and was not on the bar before the entry bar                                      |
| thin volume                    | `early_exit_on_thin_volume`, `early_exit_only_if_losing`                                       | the bar is `THIN` and the bar before the entry bar was not                                                                                                      |
| heavy bar against              | `early_exit_on_heavy_against`, `early_exit_only_if_losing`                                     | the bar is `HEAVY` and closed worse than it opened                                                                                                              |
| volatility expands             | `early_exit_atr_expansion`, `early_exit_atr_period`                                            | the ATR is above that multiple of its value on the bar before the entry bar and the position is losing                                                          |
| adverse closes                 | `early_exit_adverse_closes`, `early_exit_only_if_losing`                                       | each of the last N closes was strictly worse than the one before, every one since the entry bar's                                                               |
| adverse move                   | `early_exit_adverse_atr`, `early_exit_atr_period`, `early_exit_only_if_losing`                 | the close is worse than the one before by at least that multiple of the earlier bar's ATR                                                                       |
| give-back                      | `early_exit_give_back`, `early_exit_give_back_from_r`, `early_exit_only_if_losing`             | the best excursion has reached `early_exit_give_back_from_r` R and the close has given back that fraction of it                                                 |

**What every rule shares.** Each is decided in `OnBarUpdate` at a bar close and submitted as `ExitLong(); ExitShort();`, so it **fills at the next bar's open** and takes precedence over the stop and the targets on that bar — the maximum hold time's arithmetic, § "The maximum hold time, and why it is its own exit code". `bracket.early_exit_due` is the one decision, `bracket.market_exit_reason` the one order between it and the hold cap, and `bracket.flatten_position` the one writer; every loop calls all three. **Where a bar is two exits at once, the archetype's own signal exit takes it, then the hold cap, then this one**; all three fill at the same open, so only the label differs. On EmaCrossover a signal on the other side, on the bar the exit is decided, reopens at the same open, as it does at the hold limit, and one on the same side opens nothing (§M39).

**A position is losing when `Close[0]` is strictly worse than its entry price**, which is `Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < 0` against the average fill, slippage included. A close exactly at the entry is not losing. **Open profit in R is measured against the planned risk the trade log's `r_multiple` uses** — from the trigger on a stop entry, from the fill on a market entry — so a threshold means the same thing in both. **InsideBarTrailing's two lots carry different stops, and its R is the bracketed lot's**, the one its `OpenTrade` holds. Every threshold is in R, never in currency, so nothing here goes through `instruments.py`.

**One exit code, `EXIT_EARLY`, with one rule on at a time.** The parameter class refuses a combination switching on two, so the code and the combination's fields together always say which rule fired, and a campaign arm is one rule. **It also refuses a combination whose setting nothing reads or that can never fire**: a threshold or a measure with the not-working exit off, a counter-trend count without the bar form or not shorter than it, "only if losing" with none of the exits it applies to on, an ATR period with neither exit in ATRs on, an arming distance with the give-back exit off, and a not-working, stalled or adverse-closes count at or past `max_hold_bars`, or the adverse move under a cap of one bar, where the hold cap closes the position first. Each would run identical trades under a different label. Under ElasticBand's stored grids, which sweep `max_hold_bars` over `[0, 30]`, the not-working exit therefore has to test a bar below 30. **The minutes form cannot be refused the same way**, because the bar size is not a parameter: a minute count at or past `max_hold_bars` bars never fires, and a campaign has to choose its values knowing that. One code per rule would let rules share a log; nothing measured yet asks for that, and it would add fifteen codes to `trades.py` instead of one.

**No stop moves.** Every rule here is a market exit, so none of them touches `tightened_stop`. The stop-moving members are breakeven, § "The breakeven stop", the stop tightening with time, § "Tightening the stop with time", and InsideBarTrailing's trail to structure, § "Trailing to structure".

#### Not working by bar N

`if (BarsSinceEntryExecution() == ExitCheckBars && Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < ExitBelowR * riskPoints) { ExitLong(); ExitShort(); }`, with `riskPoints` stored when the entry fills. **It is tested at one bar close, not at every close from there on**: a position still working at bar N is left alone for the rest of its life. A leg it closes has `bars_held` of `N + 1`, as the hold cap's does. At `early_exit_below_r = 0` it is the "losing at bar N" form; a negative threshold closes only positions already that far down, and a positive one requires a profit. **It is a bar count, so it means a different amount of time at each resolution**, exactly as the hold cap does.

**`early_exit_minutes` is the same test timed in minutes**, at the first close at least N minutes after the entry bar's: `(Time[0] - Time[BarsSinceEntryExecution()]).TotalMinutes >= ExitCheckMinutes && (Time[1] - Time[BarsSinceEntryExecution()]).TotalMinutes < ExitCheckMinutes`. **One value means the same time at every bar size** — 30 minutes is 15 bars at 2 minutes and 2 at 15 — which is §M29's bar-count problem answered directly. The clock is the bars' own timestamps in UTC seconds (`Dataset.bar_seconds`), so a daylight-saving change cannot stretch it, and a gap in the bars moves the test to the first close past the age rather than skipping it. It is one test, at one close, as the bar form is, and the two cannot both be on.

**`early_exit_measure` picks what is compared with the threshold.** `MEASURE_OPEN_PROFIT` is open profit at the close, as above. `MEASURE_EXCURSION` is the best favourable excursion so far — the highest high since the entry bar, the lowest low on a short, against the entry price — which is the trade log's MFE and #369's "the excursion has not moved": `MAX(High, BarsSinceEntryExecution() + 1)[0] - Position.AveragePrice < ExitBelowR * riskPoints` for a long. It reads the whole entry bar, including any part before an intrabar fill, as `High` does under `Calculate.OnBarClose` and as the trade log's MFE does.

#### Losing before the close

`if (secondsToClose <= ExitMinutesBeforeClose * 60 && Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < 0) { ExitLong(); ExitShort(); }`, **tested at every bar close inside the window**, so a position winning as the window opens and losing a bar later still leaves, and a winner rides to the flatten. **The window is the no-entry window's at the same minutes**, cut from `sessions.seconds_to_session_end`, so it closes against the session's observed last bar and carries the same trap: the C# has to read `Time[0]`, not `Now` — § "A no-entry window before the session close". **The window includes the bar ending exactly that many minutes before the close**, so a window one bar long holds the last two bars and exits on the second-last, filling at the last bar's open. **Only a window shorter than one bar is inert**: the one bar in it is the force-flat bar, where the position is flattened at its close before any exit could fill.

#### Regime change

**The label at the bar close is compared with the label on the bar before the entry bar.** That is the last close before the position existed, and it is the bar `OnExecutionUpdate` has current when the entry fills (§M22), so a NinjaScript records the label there and compares against it in `OnBarUpdate`. For every entry but EmaPullback's confirmation entry above a one-bar lifetime it is the signal bar. **Any change fires**, into or out of the unclassifiable middle band included, and an undefined label on either side — the lookback's warm-up — never counts as one. The label is read at this combination's own lookback and thresholds, so an exit and an entry filter on the regime mean the same thing. The efficiency ratio has no NT8 indicator, so the script computes it itself — § "So are the regime labels".

#### Trend turns against

**It fires where the trend label at the bar close is against the position and the label on the bar before the entry bar was not**, so a trade entered already against the trend is left alone. `TREND_EXIT_OPPOSED` counts only the opposite trend as against — `DOWN` for a long — and `TREND_EXIT_NOT_WITH` counts `MIXED` too. A long entered in `MIXED` was already against under the second, so it never fires on that trade, where the first still fires on a turn to `DOWN`: **the loose form is not a superset of the strict one**. An undefined label on either side never fires. It generalises InsideBarTrailing's trend violation without replacing it: that exit stays as reconciled, submitted from `OnPositionUpdate` behind a currency gate (§M23), where this one reads the compact trend label at a bar close. The label is ours — § "So is the trend label".

#### Invalidated on a close

`early_exit_on_invalidation` exits at a close strictly beyond the adverse extreme of the bar before the entry bar — the signal bar, for every entry but EmaPullback's confirmation entry above a one-bar lifetime, as for the label exits: `if (Close[0] < Low[BarsSinceEntryExecution() + 1]) { ExitLong(); }` for a long, `High` and `>` for a short. **It is tested at every close from the entry bar's own**, and a close exactly on the extreme is not beyond it. The resting stop stays where the archetype put it, as a catastrophe stop, so where that stop is already the signal bar's extreme plus an offset the rule can fire only on a close between the two, and is close to inert. **It is one rule for every archetype, OpeningRange included**: "back inside the range" would need a reference level per entry mode. ElasticBand's `exit_on_invalidation`, which reads the excursion the trade faded rather than the signal bar, is unchanged and runs beside it as `EXIT_SIGNAL`; as an archetype's own signal exit, it takes a bar both would exit on.

#### Counter-trend entries get less time

`early_exit_counter_trend_bars` is a second bar count for the not-working exit, used instead of `early_exit_bars` for a position entered against the trend (#369's D6). **Against is the opposite trend on the bar before the entry bar** — `DOWN` for a long — the label the trend exit's `TREND_EXIT_OPPOSED` reads, at this combination's own trend settings; `MIXED` and an undefined label are not against, so those entries keep the longer count. The label is recorded where `OnExecutionUpdate` has that bar current (§M22): `int checkBars = enteredAgainstTrend ? CounterTrendBars : ExitCheckBars;` and the not-working test above at `checkBars`. **It is a setting of the not-working exit rather than a rule of its own**, so an arm carrying it is still one rule. It is read in bars only, and it is refused without `early_exit_bars` and at or above it, where it would give a counter-trend entry no less time.

#### Stalled

`early_exit_stall_bars` exits at the close where the position's best favourable price has not improved for that many closes (#369's A4). **The count runs from the bar the high-water mark was last strictly raised on, not from the entry**, so every new best restarts it, and a bar that only touches the best is no improvement. The water marks the trade log's MFE comes from record that bar beside each mark (`bracket.Excursion`), and the entry bar's whole range counts, as it does for the MFE. For a long, in `OnBarUpdate`:

```csharp
if (BarsSinceEntryExecution() == 0 || High[0] > bestPrice) { bestPrice = High[0]; bestBar = CurrentBar; }
if (CurrentBar - bestBar >= StallBars) { ExitLong(); }
```

**#369 words its optional condition as "only while below +x R"; only x = 0 is built**, as the "only if losing" cross. A count at or past `max_hold_bars` is refused, because the hold cap closes the position first.

#### Leaving the entry's phase

`early_exit_on_phase_change` exits a losing position at **any close whose session phase differs from the one on the bar before the entry bar** (#369's C3), the bar a `phase_filter` stratum selected the signal on. So a midday entry still losing in `AFTERNOON` leaves, and one winning as the phase turns rides on until a later close in the new phase is losing. A bar outside every session never counts. **The loss is part of the rule**, so `early_exit_only_if_losing` is not read with it. The phases are ours rather than NT8's (§ "Session phases are ours, not NT8's"), so the script computes them from `Time[0]` in exchange time: `if (PhaseOf(Time[0]) != entryPhase && Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < 0) { ExitLong(); ExitShort(); }`.

#### Higher timeframe turns against

`early_exit_on_higher_timeframe` exits where the close is on the far side of the higher-timeframe average from the position — `BELOW` for a long — **and was not on the bar before the entry bar** (#369's D3), the trend exit's shape. Exactly on the average is neither side, and an undefined side, before the first coarse bar has closed, never turns. It reads the average at this combination's own `higher_timeframe_minutes` and `higher_timeframe_period`, the one § "And so is the higher-timeframe average" describes, so the script needs the same added data series.

#### Volume turns

Two rules (#369's D4), both read at this combination's own volume form and windows (§ "So are the volume labels"):

- **`early_exit_on_thin_volume`** exits on a `THIN` bar after an entry whose bar before was `NORMAL` or `HEAVY`. An undefined label on either side, before the baseline has filled, never counts.
- **`early_exit_on_heavy_against`** exits on a `HEAVY` bar whose close is strictly worse than its own open — `Close[0] < Open[0]` for a long. It is tested from the entry bar's own close, whose open is before the fill.

**They are two switches rather than one field with two values** because each reads one threshold alone, `volume_thin_below` and `volume_heavy_above` respectively, and the registry can then mark the other one unread, so a sweep crossing it under that exit is refused rather than run as duplicates.

#### Volatility expands

`early_exit_atr_expansion` exits a losing position at a close where **NT8's ATR is strictly above that multiple of its value on the bar before the entry bar** (#369's D5): `if (ATR(AtrPeriod).Value[0] > AtrExpansion * entryAtr && Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < 0) { ExitLong(); ExitShort(); }`, with `entryAtr` read where `OnExecutionUpdate` has that bar current. The multiple is at least 1, since below it the rule is "exit while losing" under another name. An ATR still warming up names nothing. **The loss is part of the rule**, so `early_exit_only_if_losing` is not read with it.

#### Adverse momentum

Two rules (#369's E2), both counted on **closes the position was open for**, so the entry bar's close is the first one compared against and neither is ever decided at the entry bar:

- **`early_exit_adverse_closes`** exits once each of the last N closes was strictly worse than the one before; an equal close ends the run. The earliest it can fire is N bars after the entry bar: `if (BarsSinceEntryExecution() >= N && Close[0] < Close[1] && … && Close[N - 1] < Close[N]) { ExitLong(); }` for a long. A count at or past `max_hold_bars` is refused.
- **`early_exit_adverse_atr`** exits once one close is worse than the close before by at least that multiple of the earlier bar's ATR: `if (BarsSinceEntryExecution() >= 1 && Close[1] - Close[0] >= AdverseAtr * ATR(AtrPeriod).Value[1]) { ExitLong(); }` for a long. The earlier bar's ATR is the one known before the move it measures.

`early_exit_atr_period` is the ATR both this and the volatility exit read, and is refused with neither on.

#### Give-back

`early_exit_give_back` exits once the best favourable excursion has reached `early_exit_give_back_from_r` R and the close has given back at least that fraction of it (#369's E3), a close-based relative of a trail. For a long:

```csharp
double peak = MAX(High, BarsSinceEntryExecution() + 1)[0] - Position.AveragePrice;
if (peak >= GiveBackFromR * riskPoints && Close[0] - Position.AveragePrice <= (1 - GiveBack) * peak) { ExitLong(); }
```

The excursion is the not-working exit's `MEASURE_EXCURSION`, and the arming distance is reached within a billionth of it, as the breakeven trigger's is (`BREAKEVEN_TOLERANCE`). A fraction of 1 exits at a close back at the entry. **With "only if losing" it is a different rule**: a position that once reached the arming distance exits at the first losing close, whatever the fraction.

#### Only if losing

`early_exit_only_if_losing` lets the regime, trend, invalidation, stalled, higher-timeframe, thin-volume, heavy-bar, adverse-closes, adverse-move or give-back exit fire only at a bar close where the position is losing, which is the condition the findings name (`types.LOSING_OPTIONAL_EXITS`). Those rules alone read it; the others already carry a condition on open profit of their own. On the invalidation exit it binds only where the entry filled beyond that extreme too: a gapped market entry can, and so can OpeningRange's limit entries, which fill at their own level and that level can sit beyond the bar before the fill.

### The breakeven stop

**Every archetype can move its stop to the entry once a position has run far enough** (#351). `Trading-Docs` names the rule independently: once the open gain equals what was risked, move the stop to break-even. **No NinjaScript has it, so nothing here is backed by a trade list**, and a row using it is `TIER1_ONLY`, on the reconciled ports as much as on the originals. It is off by default everywhere, so nothing measured before it rests on it.

| field                    | what it sets                                                                                               |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `breakeven_at`           | how far the position has to run before the stop moves, off at `0`                                          |
| `breakeven_unit`         | what `breakeven_at` is a multiple of: `BREAKEVEN_R`, the planned risk, or `BREAKEVEN_ATR`                  |
| `breakeven_on`           | which price has to reach it: `BREAKEVEN_ON_CLOSE`, or `BREAKEVEN_ON_EXTREME`, the bar's favourable extreme |
| `breakeven_offset_ticks` | how many ticks past the entry price the stop goes                                                          |
| `breakeven_atr_period`   | the ATR period, read only in ATRs                                                                          |

**It is decided at a bar close and is live from the next bar.** In NinjaScript it is `if (High[0] >= Position.AveragePrice + distance) SetStopLoss(CalculationMode.Price, Position.AveragePrice + BreakevenOffsetTicks * TickSize);` in `OnBarUpdate` for a long, with `Close[0]` in place of `High[0]` for the close trigger. A stop set at the close of bar `i` is in force during bar `i + 1`, the ratchet's cadence (§ "Ratchet reads the just-closed bar"), so it cannot be hit on the bar that set it. **It is tested at every close from the entry bar's own**, and on the entry bar the extreme trigger reads the whole bar, as `High[0]` does under `Calculate.OnBarClose`, including any part before an intrabar fill. An ATM strategy's auto-breakeven acts on ticks, which is finer than NT8's default fidelity, and is deliberately not what this reproduces.

**The distance is measured from the entry price, slippage included**, which is `Position.AveragePrice` and the price the early exit's open profit is measured from. In R it is a multiple of the planned risk the trade log's `r_multiple` uses: from the trigger on a stop entry, from the fill on a market entry. In ATRs it reads NT8's ATR on the bar before the entry bar, the bar `OnExecutionUpdate` has current (§M22), so like R it is fixed for the trade's life. An ATR still warming up never triggers it, and neither does a position entered on the first bar. **`breakeven_atr_period` is its own field rather than each archetype's stop ATR**, because InsideBar's stop ATR is three bars and three archetypes read theirs under one stop mode alone. **A gain exactly equal to the distance triggers it**, since the rule is "once the gain equals the risk", and it is compared within a billionth of the distance (`BREAKEVEN_TOLERANCE`), because `1.1 × 12.5` rounds above the 55 ticks it names.

**The stop goes to the entry price plus the offset, snapped to the tick wherever targets are**, and goes through `tightened_stop`, so it never loosens: a ratchet, a trail or an earlier move already past the level is left where it is. **A level at or through the close is not submitted**, which only the extreme trigger or an offset can reach. That is §M18's rule that a stop at or through the price it protects is not a stop order. What NT8 does with such a `SetStopLoss` is unobserved, so this is the conservative reading rather than a measurement, and the move is tried again at the next close where the trigger holds. EmaCrossover's round-number avoidance does not apply, because the level is the entry rather than one the archetype chose.

**A stop hit after the move is still `EXIT_STOP`**, as a ratcheted or a trailed stop is. The trade log tells them apart by price: a breakeven exit leaves at the entry plus the offset, less slippage, rather than at `initial_stop`. **InsideBarTrailing moves both lots**, and its trigger reads the bracketed lot's R, as the early exit's does. NT8's managed approach will not run `SetStopLoss` and `SetTrailStop` on one entry signal at once, and `SetStopLoss` takes precedence, so a port that moves the trailing lot's stop has to manage its trail some other way. That question belongs with the port. **It may run beside an early exit**: one moves a stop and the other submits a market order, so the exit codes still say which acted.

**A setting nothing reads is refused**: any other `breakeven_*` field off its default while `breakeven_at` is `0`, and `breakeven_atr_period` off its default in R. `bracket.breakeven_level` is the one decision and `tightened_stop` the one ratchet; every loop calls both, so **do not fork either**.

### Tightening the stop with time

**Every archetype can move its stop toward the entry as the position ages, or as the session nears its close** (#369's B1, B2 and C1). **No NinjaScript has either, so nothing here is backed by a trade list**, and a row using one is `TIER1_ONLY`. Both are off by default everywhere, so nothing measured before them rests on them.

| rule      | fields                                                                                                  | moves the stop at a bar close where                                                                                                          |
| --------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| age stop  | `age_stop_bars` or `age_stop_minutes`, `age_stop_fraction`, `age_stop_shape`, `age_stop_only_if_losing` | the position is that old (a step), or at every close until it is (a line): `age_stop_fraction` of the way from its initial stop to the entry |
| late stop | `late_stop_minutes_before_close`, `late_stop_to`, `late_stop_atr`, `late_stop_atr_period`               | the bar is inside the window before the session close: to the entry, the just-closed bar's adverse extreme, or ATRs from the close           |

**What both share is the breakeven stop's mechanics.** Each is decided at a bar close and is live from the next bar, the ratchet's cadence (§ "Ratchet reads the just-closed bar"). Each goes through `tightened_stop`, so **it never loosens**. The level is snapped to the tick wherever targets are, and **a level at or through the close is not submitted** and is tried again at the next close, as § "The breakeven stop" sets out. **A hit is still `EXIT_STOP`.** The two may run together and beside the breakeven stop and an early exit, and whichever level is nearer the market holds. `bracket.tightening_level` is the one decision, and every loop calls it beside `breakeven_level`, so **do not fork it**.

#### The age stop

The level is `initialStop + Fraction * progress * (Position.AveragePrice - initialStop)`. **Under the step, `progress` is 1 from the first close at which the position is the age, and nothing moves before.** Under the line it is the age over the full age, capped at 1, from the entry bar's own close, where it is 0 and names no level, so an initial stop off the tick grid is not snapped there. A fraction of 1 is the entry.

**The fraction is of the distance from the initial stop to the entry price, not of R.** On a market entry that is the same thing, `entry - (1 - f) * R` as #369 writes it. On a stop entry R runs from the trigger, so measuring from the fill instead starts the line from the initial stop rather than a slippage-width tighter. **InsideBarTrailing moves each lot from its own initial stop**, because its two lots start at different distances, unlike the breakeven stop, which moves both to one level.

**The age is a bar count or minutes.** In bars it is `BarsSinceEntryExecution()`. In minutes it reads the same clock as the early exit's minutes form, `(Time[0] - Time[BarsSinceEntryExecution()]).TotalMinutes`. **`age_stop_only_if_losing` moves the stop only at a close where the position is losing**, so a winner's stop is left alone, and a stop already moved stays where it went. In NinjaScript, for a long, in `OnBarUpdate`:

```csharp
int age = BarsSinceEntryExecution();
double progress = AgeShape == AgeShapes.Line ? Math.Min((double)age / AgeBars, 1.0) : (age >= AgeBars ? 1.0 : 0.0);
bool losing = Position.GetUnrealizedProfitLoss(PerformanceUnit.Points, Close[0]) < 0;
if (progress > 0 && (!AgeOnlyIfLosing || losing))
{
    double level = Instrument.MasterInstrument.RoundToTickSize(initialStop + AgeFraction * progress * (Position.AveragePrice - initialStop));
    if (level > currentStop && level < Close[0]) { currentStop = level; SetStopLoss(CalculationMode.Price, level); }
}
```

**Refused**: a fraction outside `(0, 1]`, an age in both bars and minutes, a setting with the rule off, and a step at or past `max_hold_bars`, where the hold cap closes the position before the step is live. A line reaching past the cap still moves before it, so it is accepted. **An age in minutes cannot be refused the same way**, as the early exit's cannot: a step at or past `max_hold_bars` bars never moves, and a campaign has to choose its values knowing that.

#### The late stop

**The window is the no-entry window's at the same minutes**, the one the early exit's "losing before the close" reads, cut from `sessions.seconds_to_session_end`. So the C# has to read `Time[0]`, not `Now` (§ "A no-entry window before the session close"). It is tested at every close inside the window. `late_stop_to` picks one of three levels:

- **`LATE_STOP_ENTRY`**: `Position.AveragePrice`. Only a winner's stop can move there, since a loser's would be through the close.
- **`LATE_STOP_BAR_EXTREME`**: the just-closed bar's adverse extreme, `Low[0]` for a long. That is "the previous bar" from the point of view of the bar the stop is live in, and the ratchet's `High[0]` reading. A bar closing on its own extreme names no stop.
- **`LATE_STOP_ATR`**: `Close[0] - LateStopAtr * ATR(LateStopAtrPeriod).Value[0]` for a long. It uses NT8's ATR at the bar's own close, so it moves with every close. An ATR still warming up names nothing.

**One level per combination, not the nearest of the three**, so an arm's result belongs to one level; #369 worded it as the nearest. **Refused**: a setting with the window shut, an ATR multiple or period away from its default under the other two levels, and a multiple that is not above zero and finite.

### Trailing to structure

**InsideBarTrailing's trailing lot can trail to structure instead of the high-water mark** (#352). `Trading-Docs` §11 names the rule: ratchet the stop behind the most recently completed structure plus a cushion, using the midpoint of each newly broken range so the rule is unambiguous. Here a range is the last `N` completed bars. **No NinjaScript has it, so nothing here is backed by a trade list**, and a row using it is `TIER1_ONLY`. It is off by default, so nothing measured before it rests on it.

| field                         | what it sets                                                                                 |
| ----------------------------- | -------------------------------------------------------------------------------------------- |
| `structure_trail_bars`        | how many completed bars make the box; off at `0`, which trails the high-water mark as before |
| `structure_trail_cushion_atr` | how far behind the box's midpoint the stop sits, in ATRs                                     |

**The box is the `N` bars before the bar being closed, and a break is a close strictly beyond its favourable edge.** At the close of bar `i` a long's box is bars `i - N` to `i - 1`. A high through the box with a close inside it, or a close exactly on its edge, is not a break. Every close beyond the box is a new break, so in a run of higher closes the stop moves at each one. A short is the same rule through the sign. The box reads back across a session boundary where `N` reaches past the session's first bar, and reads the bars there are where it reaches past the first bar of the data, as NT8's `MAX` and `MIN` do. That second case is reachable here, unlike SqueezeBreakout's window (§M19.2), because `BarsRequiredToTrade` is 5. In NinjaScript, for a long, in `OnBarUpdate`:

```csharp
if (Close[0] > MAX(High, StructureTrailBars)[1])
{
    double level = (MAX(High, StructureTrailBars)[1] + MIN(Low, StructureTrailBars)[1]) / 2 - cushion;
    if (level > runnerStop) { runnerStop = level; SetStopLoss("entry2", CalculationMode.Price, runnerStop, false); }
}
```

**It is decided at a bar close and is live from the next bar**, the ratchet's cadence (§ "Ratchet reads the just-closed bar"), from the entry bar's own close on. It goes through `tightened_stop`, so **it never loosens**: a break whose midpoint sits behind the standing stop leaves it there. The level is snapped to the tick wherever targets are, by the same `round_to_tick` every snapped level takes, which rounds a half tick up whichever the side: a midpoint between two ticks lands half a tick nearer the market on a long and half a tick further from it on a short. It can never be at or through the close, because the close is beyond the box's edge and the midpoint less a cushion is behind it, so §M18's submittability rule has nothing to refuse.

**It replaces the high-water trail rather than sitting beside it.** The runner's stop starts where it does today, `trailing_stop_multiplier` inside-bar ranges from the fill, so both modes open every trade with the same stop and the same planned risk; after that only a break moves it. That is the shape a port can take, because NT8's managed approach will not run `SetStopLoss` and `SetTrailStop` on one entry (§ "The breakeven stop"): the runner takes `SetStopLoss("entry2", CalculationMode.Ticks, trailingStopDistance, false)` in `OnExecutionUpdate` and the price form above. Setting a stop by price in one trade and by distance at the next fill is the pattern the reconciled script already uses for `entry1`. **Nothing moves it within the entry bar**, because §M23's entry-bar advance belongs to `SetTrailStop`, which this mode never calls. `trailing_stop_multiplier` stays live as the initial stop, so read it within the mode rather than pooled across both — [`roadmap.md`](roadmap.md) §M28.1.

**The cushion is in the signal bar's ATR**: the `atr_length` ATR that already sizes the bracketed lot's stop and target, read on the bar `OnExecutionUpdate` has current (§M22), so it is fixed for the trade's life. A negative box, a negative or non-finite cushion, and a cushion with the trail off are refused.

**A hit is still `EXIT_STOP`**, and it can trigger the trend violation exactly as the high-water trail's does (§M23). The bracketed lot is untouched. The breakeven stop still moves both lots, and whichever level is nearer the market holds. `insidebartrailing.structure_level` is the one decision and `tightened_stop` the one ratchet, so **do not fork either**.

### Filters relative to the trade's side

**Three filters on every archetype require a label to point the way the bar would be entered** (#439): `with_trend`, `with_higher_timeframe` and `with_vwap`. Each reads its label exactly as §M47's confluence size does and keeps a signal only where the label *favours* the trade, in §M47's table: the trend `UP` for a long and `DOWN` for a short, the close above the higher-timeframe average for a long and below it for a short, and the close above the session VWAP for a long and below it for a short. **A bar the label cannot classify fails the filter**: a `MIXED` trend, a close `AT` the coarse average, or a bar before any coarse bar has closed. A close exactly on the VWAP passes for either side, as it favours both in §M47.

**The side is the archetype's own `long_side`**, the series §M47's size is read against, at the signal bar: EmaCrossover's fast average above its slow one, and fixed on the one-sided archetypes. Each archetype's signal hands it to the filters, which compute it only when one of the three is on.

**Off by default, so every NinjaScript as ported is unchanged, and a row using one is `TIER1_ONLY`.** A side-relative filter beside the absolute filter on the same label is refused: `with_trend` with a `trend_filter` that admits less than every trend, and `with_higher_timeframe` with a `higher_timeframe_filter` that admits less than every side. The absolute filter names one direction for both sides, so the pair would quietly trade one side. On DeadCatBounce and PullBackAndGo, `with_vwap` beside the archetype's own `use_vwap` is refused too: each is one-sided, so the two are the same gate twice. In EmaCrossover's confluence count each side-relative filter is one more active gate.

A port tests the label against the side it is about to enter, in `OnBarUpdate`, at the signal bar, with each label computed as §M47's port computes it:

```csharp
bool goingLong = fastEMA[0] > slowEMA[0];
if (WithTrend && !(goingLong ? trendUp : trendDown)) return;
if (WithHigherTimeframe && !(goingLong ? htfAbove : htfBelow)) return;
if (WithVwap && !(goingLong ? Close[0] >= vwap[0] : Close[0] <= vwap[0])) return;
```

None of the labels exists in NT8 (§M45), so a port of any of the three ports its label too.

## Order lifetime and the session edge (#67)

Four questions reflection could not answer, settled by `NqbtOrderLifetimeProbe.cs` rather than by a trade list — three of them are questions about **cancels**, and a Trades export carries only fills, so "cancelled the resting order" and "refused the second fill" are indistinguishable in one by construction. The probe places no bracket and writes its own `OnOrderUpdate` log. Eleven runs over `MNQ 03-24`, 1 minute, `2023-12-01` → `2024-03-15`, Standard fill resolution, zero costs; the outputs are kept in `verification/` and are machine-local (#91), and every figure below is reproduced by passing each run's events log to:

```bash
uv run tools/reconcile_order_lifetime.py <stem>_events.csv
```

### Read the bar column before anything else: order callbacks lag by one

**A callback reporting a fill names the bar *before* the one it filled on.** Strategy Analyzer processes historical order fills for bar *i+1* before calling `OnBarUpdate(i+1)`, and `CurrentBar` still reads *i* during that pass. Measured by price, which is the only discriminator that settles it: across **535 fills the reported bar never reaches the trigger and the next bar always does**, with no exceptions in any run.

**It is not a blanket rule about callbacks, and reading it as one is how a session-close exit comes to look like it lands in the next session.** The `Exit on session close` fill does *not* lag — it fills at the reported bar's own close, 73 of 74 exactly equal to it, the 74th being the end-of-data liquidation. The distinction is mechanical: the lag belongs to orders *resolved against the next bar's prices*, not to an exit NinjaTrader generates from a bar close. `SUBMIT` and `CANCEL_REQUEST` rows come from `OnBarUpdate` and never lag.

`tools/reconcile_order_lifetime.py` re-measures both on every run rather than assuming either, and refuses the run if the entry-fill lag is not a clean +1.

### `isLiveUntilCancelled` is honoured, and the session-close handler is what ends it

**Strategy Analyzer keeps an LUC order resting indefinitely.** `Order.IsLiveUntilCancelled` reads true on every order the long-form overload placed, and with `IsExitOnSessionCloseStrategy` false a single unreachable buy stop rested **199,669 bars across 146 session opens** — roughly six months, weekends and holidays included — ending only when price finally reached it. Nothing cancelled it.

**With `IsExitOnSessionCloseStrategy` true, the same order is cancelled at every session's last bar: 73 of 73, zero fills.** So the session *boundary* ends nothing; the session-close *handler* does. That is the rule the simulation needs, because flat-before-close is not negotiable here — which makes `entry_order_lifetime_bars = 0` ("until cancelled") and "cancel at the force-flat point" the same behaviour under this project's own account rule, and `sessions.force_flat_mask` already the right mechanism.

### An order is live through the bar at whose close its cancel is issued

**Live from submit+1 through the cancel bar inclusive; the cancel is processed at the start of the next bar's pass, before that bar's fills.** Both halves are measured:

| overload                                          | cancel issued                   | live for              | evidence                                                                                     |
| ------------------------------------------------- | ------------------------------- | --------------------- | -------------------------------------------------------------------------------------------- |
| three-argument (`isLiveUntilCancelled` false)     | by NT8 at the close of submit+1 | submit+1 only         | cancelled at submit+2 on 480 of 480; every fill at submit+1                                  |
| long-form, then `CancelOrder` at submit+2's close | by the strategy                 | submit+1 and submit+2 | 29 filled on submit+2; **of the 450 that reached their cancel, none ever filled afterwards** |

The three-argument row is the control, and it reproduces `deadcat.py`'s `pending_bar == i - 1` exactly. The generalisation is therefore `entry_order_lifetime_bars = k` meaning live for bars *i+1 … i+k*, with **1 reproducing today byte-for-byte** — the shape #16 specified, now measured rather than assumed.

### The managed approach refuses the opposite-direction submission outright

Neither of the two readings #67 proposed. It does not cancel the resting opposite entry and it does not merely refuse the second *fill*: **the second order is never accepted at all.** A long stop and a short stop submitted together give 500 `SUBMIT` rows for the short side and **zero order updates** — NinjaTrader logs "An Enter() method to submit an entry order has been ignored", citing its internal order-handling rules.

**It is about direction, not count.** Re-running at `EntriesPerDirection = 2` produced a file differing from the `= 1` run only in NinjaTrader's execution-id counter.

**Resubmission does not get round it either (#51).** Scenario 3's orders were `isLiveUntilCancelled`, so scenario 6 repeats it with plain ones: a three-argument buy stop above the bar's high and sell stop below its low, both re-issued at the new levels on every flat bar. The refusal lands on the first bar of every trial, before anything has been re-issued, so it holds for route 3's unchanged trigger and for §M19.2's moving one alike. Two runs over `MNQ 12-26`, 1 minute, `2026-01-01` → `2026-09-15`, `EntriesPerDirection = 2`, one per submission order:

| submitted first | first side                         | second side                       |
| --------------- | ---------------------------------- | --------------------------------- |
| buy stop        | accepted on 500 trials, 499 filled | 1,142 submissions, 0 acknowledged |
| sell stop       | accepted on 500 trials, 499 filled | 1,229 submissions, 0 acknowledged |

**Submission order decides which side is refused.** Whichever entry goes in second is ignored, and re-issuing the working one every bar keeps the other out for the whole trial. This is documented behaviour rather than a Strategy Analyzer quirk: the help guide's internal order handling rules ignore an entry method when "the strategy position is flat and an order submitted by an enter method … is active and the order is used to open a position in the opposite direction" ([Managed Approach](https://ninjatrader.com/support/helpguides/nt8/managed_approach.htm)). `EntriesPerDirection = 1` was not re-run for plain orders; it caps entries on one side, and the refused order is always the other side.

So a two-sided entry is **not expressible on the managed approach by any route**. An archetype that needs both sides resting at once has to be written unmanaged (route 2), which gives up `SetStopLoss` and `SetProfitTarget` — see [roadmap.md](roadmap.md) § "Order lifetime in NT8".

### A resting entry fills on the force-flat bar, and is flattened at its close

**Fills are evaluated before the session-close handler runs**, so an order resting into the session's last bar gets its chance there and the position it opens is flattened at that bar's close. A plain three-argument buy stop resubmitted on every flat bar filled **on the session's own last bar around 40 times** over the probe window, every one of them exiting via `Exit on session close` at that same bar's close. Two independent classifications agree — NinjaTrader's own `Bars.IsLastBarOfSession` gives 39, `sessions.classify` gives 40, and 35 of them fall in the post-merge window where the archive and NinjaTrader are looking at identical bars.

Until #208 the simulation refused those fills, gating every one behind `if not bars.force_flat[i]`. The gate is gone from all five entry loops; the bar is now tested for a fill like any other, and `resolve_brackets` flattens whatever it opened at `EXIT_SESSION_CLOSE`. **The flatten is last in `resolve_brackets`, so a leg that reached its stop or target on that same bar still records that** rather than the close.

**What it was worth on the trade-log gate.** The four single-contract files are unchanged and the ten sweep files gain legs; joined on `(entry_time, leg)` every pre-existing leg is identical on every field, so the change is purely additive. Most of the added legs leave at the stop rather than at the close, which is the ordering above: the last bar of a session is wide enough to reach a bracket level before it ends. Re-measure it with `tools/capture_trade_logs.py` rather than quoting a count from here.

**A trade list corroborates the probe.** The single NT8-only leg in the InsideBar reconciliation was one of these: 2024-02-01 22:00 UTC, entered at 17632.75 and exited by `Exit on session close` at 17628.50 for −$34.00. nqbt now produces it identically, taking that reconciliation to 969 of 969 with nothing on either side unjoined.

### An entry submitted *on* the last bar never fills at the next session's open

The adjacent case, and here the simulation is right. Submitting only on `Bars.IsLastBarOfSession` gives 73 trials: **all 73 were acknowledged and reached `Working`, all 73 were cancelled, none filled** — while **43 of them had the next session's opening bar reach the trigger, 26 gapping straight through it at the open**. The cancel is processed before that bar's fills are evaluated, exactly as the LUC cancels above are.

`block_entry_at_session_close` reaches the same outcome by never placing the order, so trade logs agree even though the mechanism differs. Corroborated independently in the PullBackAndGo export: turning the block off produces exactly one such entry over `MNQ 06-24`, on 2024-04-23, whose trigger the next session's open gapped through by 19.75 points — and NinjaTrader's export has no fill there.

### `ExitOnSessionCloseSeconds` is honoured but inert at bar granularity

**NinjaTrader flattens at the session's last bar's close whatever the value is.** Runs at 30 and at 300 seconds produced files differing only in execution ids, and the probe's `_config.csv` — written at `DataLoaded`, the first bar and `Terminated` — shows `300` in force at every stage, so this is not the property being ignored, nor Strategy Analyzer's own Exit-on-close fields overriding it. On a 1-minute series at Standard fill resolution there is no sub-bar granularity for the seconds to act on.

`force_flat_mask`'s `exit_on_close_seconds` parameter therefore has no NinjaTrader counterpart to match below 60 seconds on a 1-minute series; every value under one bar picks the same bar.

**That makes it the one place the simulation can model something NinjaTrader cannot show**, because a live account does honour it. [`docs/findings/m41-flatten-timing.md`](findings/m41-flatten-timing.md) runs both go-live candidates at 30, 180, 300 and 900 seconds and reads the difference; the parameter is not a fidelity knob and moving it off its default is never a Tier-2 comparison.

### What the probe validated on nqbt's side

`sessions.classify` agreed with NinjaTrader's own `Bars.IsLastBarOfSession` on **73 of 73** session-close bars — the first direct check of the session calendar against NinjaTrader rather than against the template it was written from.

## Indicators

**TA-Lib's EMA does not match NT8's.** TA-Lib seeds with an SMA of the first `period` values and emits nothing before index `period-1`; NT8 seeds from the raw price at bar 0:

```csharp
Value[0] = CurrentBar == 0 ? Input[0]
         : Input[0] * (2/(1+Period)) + (1 - 2/(1+Period)) * Value[1]
```

For `EMA(3)` over `0..9`, TA-Lib returns exactly 8.0 and NT8 returns 8.001953125. Since `Close[0] > ema[0]` is a hard entry gate, that changes which bars signal. NT8's SMA likewise averages a *partial* window before `period` bars where TA-Lib returns NaN. Both are hand-rolled in `indicators.py`. TA-Lib is a test dependency only, kept to show these divergences; MACD and RSI are not implemented, and either would need pinning against NT8 before an archetype reads it.

### M16 — ATR, StdDev, Bollinger and Keltner, read out of NT8

Pinned by `ninjatrader-scripts/Strategies/NqbtIndicatorProbe.cs`, which places no orders and dumps NT8's own values at G17. Source: **MNQ 03-24, 1-minute, 89,330 bars from bar 0**. Every series below agrees with `indicators.py` on **all 89,330 bars** at `rtol=1e-11` — under 2e-7 of a point against a 0.25 tick, so no gate can move. Bit-exact agreement is not achievable through a float recursion and is not the standard; True Range, which accumulates nothing, *is* exact on every bar.

**True Range** is `max(H−L, |H−prevC|, |L−prevC|)`, and the bare `H−L` at bar 0. Exact on 89,330/89,330. Read directly out of `ATR(1)`, since the Wilder recursion at period 1 reduces to TR itself and NT8 exposes no TR indicator.

**ATR seeds with an expanding simple average, then switches to Wilder.** Emits from bar 0. While `CurrentBar < period` the value is the simple average of every TR so far; from `period` on it is `(prior×(period−1) + TR) / period`. This is the **same class of defect as the EMA — seeding, not formula** — and it is the one M16 predicted. It is not a rounding difference: at bar 1 with period 14, seeding Wilder from bar 0 instead differs by over 4 points on this data, and the recursion never forgets its seed.

| candidate                       | bars matching of 89,330 |
| ------------------------------- | ----------------------- |
| expanding-SMA seed, then Wilder | **89,330**              |
| pure Wilder from `TR[0]`        | 89,020                  |
| rolling SMA of TR               | 20                      |

**StdDev uses the population divisor and an expanding partial window.** Divisor is the sample count, never `n−1`; before `period` bars exist it uses everything so far, exactly as `nt8_sma` does. `StdDev[0]` is 0.

It must be computed **two-pass**, subtracting the window mean explicitly. An incremental sum-of-squares update is algebraically identical and numerically is not: pandas' `rolling(...).std(ddof=0)` differs from NT8 by up to **4.2e-07** over this window. Far below a tick, but not the exact agreement a pin exists to establish.

**Bollinger is the SMA plus that same StdDev.** Midline equals `nt8_sma` exactly on all 89,330 bars; upper and lower are `midline ± k × StdDev` exactly on all 89,330.

**Keltner matches neither half of the common definition**, which is why M16 flagged it as the one most likely to be silently wrong:

- The midline is an **SMA of typical price** `(H+L+C)/3` — matched 89,330/89,330. An SMA of close matched 354, an EMA of typical price matched 1, an EMA of close matched 0.
- The width is `offset ×` the **mean high−low range**, *not* ATR. `(upper − midline) / 1.5` matched `SMA(H−L, 20)` on 89,330/89,330 and matched `ATR(20)` on **20**.

The two quantities both average a per-bar measure of movement, so a wrong one looks plausible on a chart; they part company whenever a gap makes True Range exceed the bare range. `tests/test_indicators_nt8_parity.py` pins both halves against the export, including the negative assertions.

**True Range does not reset at a session boundary** (#23's measurement half). It reads the previous bar's close across the 17:00–18:00 ET maintenance break like any other bar. On **27 of the 65 session opens** in this window the overnight gap makes TR exceed `H−L`, so this is a material choice rather than a formality — the first is 2023-12-07 23:01, where `H−L` is 11.50 and TR is 12.50. It does not reset at a roll boundary either — see below.

**VWAP** is hand-rolled session-anchored `Σ(typical × volume) / Σ(volume)`, reset at each 18:00 ET open. `OrderFlowVWAP` at `VWAPResolution.Standard` works from bar data, so minute bars are the right input — tick data would *reduce* agreement.

### WMA and HMA, ported from the NinjaScript rather than reconciled (#72)

**These two are pinned against `@WMA.cs` and `@HMA.cs` themselves, not against an NT8 export.** Every other indicator here was read out of NinjaTrader by `NqbtIndicatorProbe.cs`; these were not, because the probe predates them. The prime directive still binds — the C# is the ground truth and it is transcribed literally — but the evidence is a class weaker than the M16 series above, and that is why `MA_KINDS` records where each came from rather than claiming an agreement rate. An archetype that switches a gate onto one of them has not been reconciled at that setting.

**WMA weights `1..k` with the heaviest on the newest bar, over an expanding window.** It emits from bar 0 exactly as `nt8_sma` does: at bar *i* the window is `min(period, i+1)` bars and the divisor is that window's triangular number, so the warm-up is a shorter WMA rather than a null.

**`@WMA.cs` has two branches and `indicators.nt8_wma` implements the one minute bars take.** Where the bar type supports `RemoveLastBar` — which time-based bars do — NT8 rebuilds the weighted sum from scratch every bar; otherwise it carries `wsum` and `sum` forward and updates them. The two are algebraically identical and numerically are not, and this is **the same choice `nt8_stddev` already faced**: the accumulating form drifts, the rebuilt one is exact, and the exact one is also what NT8 runs here. `tests/test_indicators.py::test_nt8_wma_matches_the_recursive_form_of_the_same_sum` pins that they agree, so the branch is a decision rather than an assumption.

**The cost of rebuilding is real but small**, and it is the reason the choice is recorded rather than hidden: over the 1,663,489-bar MNQ continuous series, `nt8_wma` runs 0.025 s at period 21 and 0.220 s at period 200, against 0.003 s and 0.004 s for `nt8_ema`, which is `O(n)` at any period. `nt8_hma` is roughly 1.5× its WMA — 0.052 s and 0.356 s — because it is three of them. Re-measure rather than quoting these; they are one machine's.

**HMA is NT8's composition of three WMAs and both inner lengths truncate.** `WMA(2·WMA(period/2) − WMA(period), (int)sqrt(period))`, where `period/2` is C# integer division and the square root is cast, not rounded — so period 14 is `WMA(7)`, `WMA(14)` and an outer `WMA(3)`. NT8 caps the period with `Range(2, int.MaxValue)` and `nt8_hma` refuses 1 for the same reason: its inner `WMA(0)` has nothing to average.

**VWMA is deliberately absent, and it is the one that needs a probe.** It reads volume as well as price, and the obstacle there is the shape of `MovingAverageKind.compute` — `(values, period)`, a single series — rather than the data, which `prepare` already pulls out of `bars["volume"]` for the session VWAP. What actually needs NinjaTrader is that `@VWMA.cs`'s two branches genuinely disagree during warm-up rather than merely rounding differently: the `RemoveLastBar` branch sums `min(CurrentBar, Period)` bars and returns `0` at bar 0, the other sums `CurrentBar + 1` and returns `Input[0]`. Choosing between them from the C# alone is guessing, and a wrong warm-up is exactly the seeding class of defect the EMA and the ATR were both caught by.

### True Range at a roll boundary (#23)

**Nothing is special-cased at a roll, and the reason is stronger than "NT8 would not either".** A seam bar reads the previous bar's close like any other, and on a back-adjusted series that previous close carries **no contract basis at all**.

**Back-adjustment removes the basis exactly, not approximately.** The shift comes from `front_close − back_close` at the last bar the front contract contributes, which is precisely the bar a seam reads back to, so the two cancel. Measured over both cached back-adjusted series with `splice.roll_seams`: the seam carry-over equals the *back contract's own* close-to-open move over the same interval to the last bit, on **all 36 seams** — 18 rolls in each root. `tests/test_splice.py::test_back_adjustment_leaves_no_contract_basis_at_the_seam` pins it against a basis that widens across the overlap, so an offset read off any other bar fails it.

**So the step measures the break the seam sits across, not the roll.** `roll_seams` reports that break as `gap_minutes`, and it falls in three populations:

| `gap_minutes` | what the seam spans                                  | carry-over            |
| ------------- | ---------------------------------------------------- | --------------------- |
| 61            | the 17:00–18:00 ET maintenance break alone           | a few points          |
| ~1,320–1,380  | a session the front contract's archive does not hold | up to several hundred |
| ~2,880–2,940  | a weekend                                            | tens to a few hundred |

The middle row is the larger population today and it is **not a market event**: it is the known cost of correct roll dates (`.claude/rules/data-pipeline.md`, "Correct roll dates cost bars"). The front contract owns its last session but holds only the first hour of it, so the seam carries a whole session's move in one bar. That is a data-coverage gap wearing a roll's clothing, and filling it from the neighbouring contract would splice two different prices into one session.

**What it costs ATR.** Wilder at period *n* decays a single TR spike by `(n−1)/n` per bar, so at the default 14 a seam is still 10% of its initial excess 32 bars later and 1% of it 63 bars later — the recursion never forgets, exactly as with the seed. Run `roll_seams` for the current sizes rather than quoting a figure from here; on the series as it stands, ATR(14) at a seam runs several times its value on the bar before.

Two standing consequences:

- **Do not read the step as a volatility event.** A regime, squeeze or trigger rule reading ATR will fire around every roll for a reason that has nothing to do with the market.
- **Judge an ATR-sensitive rule per contract** (`dispersion.py`, #31). A front-month window runs roll day to roll day, so it contains no seam — which is the same property that makes it directly reproducible in Strategy Analyzer.

## Sessions

CME US Index Futures ETH: 18:00 → 17:00 ET, 17:00–18:00 maintenance break, Sunday evening through Friday afternoon. A session is labelled by the date it **ends** on.

Validated against the data: median **1380 bars/session** (exactly 23 hours); 65 of 66 sessions open at 18:01 ET and 63 close at 17:00 ET. The outliers are real CME holiday early closes (MLK, Presidents' Day) and the export's truncated first and last sessions. Both kinds end before the template says they should, and the flatten follows the bars rather than the template — "The session end is the observed last bar, not the template's".

No session ever spans a DST transition — US transitions happen 02:00 Sunday and the market is closed Friday 17:00 → Sunday 18:00 — so naive wall-clock arithmetic inside a session is exact.

Exports also contain stray prints outside session hours (isolated volume-1 bars on Saturdays) — 47 of MNQ 03-24's 132,454 bars, and 0.086% on the worst of the 38 contracts cached when #160 landed. NT8 building bars against an ETH template never forms these, so they are tagged `in_session=False` in the Parquet cache, which stays lossless, and `ingest.load_contract` drops them on the way out. A per-contract frame and a spliced one are therefore the same bar set, which they were not before #160: `context.prepare` computed over every row it was handed while `build_continuous` filtered first, so a stray at a session open became `[1]` and shifted every `[n]` behind it. What that was worth is in "Reconciliation result — InsideBar".

**A large share is a broken export, not strays, and is refused rather than filtered.** `ingest.STRAY_SHARE_LIMIT` is the line; above it `load_contract` raises, because a file where the count is not a rounding error is saying the export or the session template is wrong, and quietly filtering it would hide that.

**NT8's trade-list export is in the machine's display timezone, not UTC.** This corrects an earlier claim here, and the earlier evidence contains the reason it was wrong: the entry-time histogram showed an empty 22:00 hour, which is the 17:00–18:00 ET break *in winter*. The original window (MNQ 03-24, December–March) sits entirely in GMT, where `Europe/London` and UTC coincide, so a display-zone export was indistinguishable from a UTC one.

The MNQ 06-24 reconciliation spans 31 March 2024 and settles it. Parsing as UTC joined **332 of 1,800 legs**; parsing as `Europe/London` joined **1,792 of 1,792**. The shift is exactly 0 hours before 31 March and exactly +1 after — BST, not a data problem.

So a reconciliation over any summer window fails mysteriously unless the export is read in the display zone. `tools/reconcile_nt8.py` does, via `EXPORT_TZ`, and it is stated explicitly rather than inferred because a wrong zone shifts every trade by a whole hour and still parses cleanly. Bar timestamps in `data/archive/` are unaffected — those are converted to UTC at export by the AddOn, which already handled both DST traps.

### Session phases are ours, not NT8's (#43)

`nqbt/timeofday.py`'s seven phases have **no NinjaScript counterpart and need none** — they label bars for stratification, they are not a fill rule, and nothing about them can move a trade. The one place they touch a reconciled archetype is `phase_filter`, an entry filter absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`, listed here so it is on the record beside the other options the C# does not implement.

It defaults to `ALL_PHASES` and each archetype's signal **skips it entirely** at that value, so the reconciled configurations are untouched: all 12 captured trade logs are byte-identical across the change, `sha256` included. Switch it on and the run is no longer the run the trade list was diffed against — which is fine for research and is not a Tier-2 claim.

The boundaries themselves (03:00 London, 09:30 cash open, 16:00 close) are market facts in Eastern time, not readings out of NT8, and are recorded in `docs/roadmap.md` § M10.4.

### So are the regime labels (#40)

`nqbt/regime.py` is the same shape of thing and carries the same status. Kaufman's efficiency ratio has no NinjaScript counterpart, is not a fill rule, and cannot move a trade; `regime_filter` is the one place it touches a reconciled archetype, and like `phase_filter` it is absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`. Listed here so it is on the record beside the other options the C# does not implement.

It defaults to `ALL_REGIMES` and each signal **skips it entirely** at that value, so all 12 captured trade logs are byte-identical across the change, `sha256` included. There is a second reason the skip has to be no call rather than a no-op mask: the ratio's warm-up bars are `UNDEFINED` and pass nothing, `ALL_REGIMES` included. The thresholds and the warm-up decision are in `docs/roadmap.md` § M10.1.

### So are the volume labels (#41)

`nqbt/volume.py` is the third of the same shape and carries the same status. Relative volume has no NinjaScript counterpart, is not a fill rule, and cannot move a trade; `volume_filter` is the one place it touches a reconciled archetype, and like `phase_filter` and `regime_filter` it is absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`.

It defaults to `ALL_STATES` and each signal **skips it entirely** at that value, so all 12 captured trade logs are byte-identical across the change, `sha256` included. The skip has to be no call rather than a no-op mask for the same reason it does under `regime_filter`: the first sessions have no baseline, so their bars are `UNDEFINED` and pass nothing, `ALL_STATES` included.

**The one NT8-shaped question here is what counts as volume**, and the answer is the same `sessions.classify` uses everywhere: an out-of-session print is not a bar NT8 would have formed against an ETH template, so it reads zero in all three forms rather than being counted. Everything else about the labels — the bar-of-session baseline, the three forms, the thresholds — is a research choice with no NT8 counterpart, and is recorded in `docs/roadmap.md` § M10.2.

### So is the trend label (#42)

`nqbt/trend.py` is the fourth of the same shape and carries the same status. The compact trend label has no NinjaScript counterpart, is not a fill rule, and cannot move a trade; `trend_filter` is the one place it touches a reconciled archetype, and like the three filters above it is absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`.

It defaults to `ALL_TRENDS` and each signal **skips it entirely** at that value, so 12 of the 14 captured files are byte-identical across the change, `sha256` included, the two that move being the sweep summary tables gaining the five parameter columns. The skip has to be no call rather than a no-op mask for the same reason it does under `regime_filter` and `volume_filter`: a bar whose slope cannot yet be measured is `UNDEFINED` and passes nothing, `ALL_TRENDS` included.

**The one thing here that is an NT8 question is the averages**, and it is answered by reuse: the label reads `nqbt.conditions.moving_average_grid`, so its EMAs are `indicators.nt8_ema` and carry whatever parity the gates carry rather than a second definition. Everything else — the three components, the agreement score, the thresholds — is a research choice with no NT8 counterpart, and is recorded in `docs/roadmap.md` § M10.3.

### And so is the higher-timeframe average (#73)

`nqbt/higher_timeframe.py` is the fifth of the same shape and carries the same status. A moving average computed on resampled bars has no NinjaScript counterpart *here*, is not a fill rule, and cannot move a trade; `higher_timeframe_filter` is the one place it touches a reconciled archetype, and like the four filters above it is absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`.

It defaults to `ALL_SIDES` and each signal **skips it entirely** at that value, so 12 of the 14 captured files are byte-identical across the change, `sha256` included, the two that move being the sweep summary tables gaining the three parameter columns. The skip has to be no call rather than a no-op mask for the reason it does under the other three: a bar before the first coarse bar has closed is `UNDEFINED` and passes nothing, `ALL_SIDES` included.

**Unlike the four above, this one has an NT8-shaped question — and a trade list is the wrong instrument for it.** NinjaScript expresses the same gate as an `EMA` of period 50 over a `Closes[1]` added with `AddDataSeries`, tested against `Close[0]`, and *when* that secondary series updates relative to a same-stamped primary bar is a property of NT8's event ordering, not of the arithmetic. The rule implemented here is that a coarse bar is readable from the fine bar closing alongside it and from none before it.

**For an EMA the two readings cannot be told apart by any trade list, and that is algebra rather than a measurement.** The update moves the average toward the close and never past it, so `close − EMA_new = (1 − α)(close − EMA_prev)` with `α = 2/(period+1)` keeps the sign, and the gate therefore never flips. Measured over 914,700 MNQ bars at 5/15/60 minutes × periods 3/20/50, the label differs on exactly one bar in every configuration and that one is the first coarse close, where the lagged reading is still in warm-up; where both are defined the disagreement count is zero. A reconciliation would return 100% and settle nothing.

**An SMA is a different matter, which is what makes this worth recording rather than closing.** An SMA drops the oldest value out of its window and *can* move past the close, so the boundary is observable there — 842 differing bars at 15-minute SMA(20) over the same data. [#72] made the *fine* gates' kind sweepable and left this series fixed at EMA, so the day `HigherTimeframeKey` gains a kind of its own, a trade list becomes a valid instrument.

**Reconciled ([#183]).** `NqbtHigherTimeframeProbe.cs` was run in Strategy Analyzer over `MNQ 03-24` with a 60-minute secondary series: 1,479,760 1-minute bars from 2020-01-01 to 2024-03-15, and 24,826 coarse bars. `tools/reconcile_higher_timeframe.py` compares it. All four questions are answered, and three of them exactly:

| question        | result                                                                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| projection      | **0 of 1,479,701** bars differ. On all **24,752** coarse closes NT8 reads the coarse bar stamped alongside the fine bar                            |
| seeding         | **0 differ** on EMA(3), EMA(50), SMA(3) and SMA(50) over 24,752 coarse closes                                                                      |
| warm-up         | **59 against 59** leading bars unreadable                                                                                                          |
| anchoring       | exact over the **1,525** coarse bars of the front-month window; the prefix is NT8's merged series, below                                           |
| the gate itself | **0 of 1,479,760** bars differ, composing NT8's own close against NT8's own coarse EMA into a side and comparing it with `higher_timeframe_labels` |

**The projection result settles the boundary for every moving-average kind at once, which is why the probe was worth building rather than a trading script.** It compares *which bar* NT8 reads, not what the average computed to, so it does not depend on the arithmetic being monotone — the SMA case that a trade list would have been needed for is answered by the same column. `higher_timeframe.project`'s `side="right"` is NinjaTrader's own rule.

**The anchoring prefix is NT8's merge policy, not a bucketing difference.** Asked for four years of a contract that has about six months of its own history, NinjaTrader serves its merged series for the rest. Agreement is exact from **2023-12-08 23:00** onward — 1,525 coarse bars, zero differences on open, high, low, close and volume — and before that the archive holds one to four contracts an hour against NT8's thousands, which is the back-month contract against a merged front month. The changeover bucket at 2023-12-08 22:00 agrees on open and close and differs on high, low and volume, being the one bucket straddling the handover. This is the trap `reconcile_nt8.py` documents, met again; `settled_from` in the comparison tool names the changeover so a merged prefix cannot read as a defect.

**The gate is checked as a whole and not only in its parts.** Composing NinjaTrader's own `Close[0]` against its own 50-period EMA of `Closes[1]` into a side reproduces `higher_timeframe_labels` on every one of 1,479,760 bars: 628,106 `BELOW`, 851,589 `ABOVE`, 59 `UNDEFINED`, and the 6 `AT` bars where the close falls exactly on the average — NinjaTrader lands on the same six. The boolean a sweep applies agrees bar for bar at both `BELOW` and `ABOVE`.

**A leg-for-leg trade-list diff would add nothing here, and is deliberately not planned.** What it would exercise beyond the above is the conjunction in `sim/filters.py` and the bracket, and those are shared unchanged with `phase_filter`, `regime_filter`, `volume_filter` and `trend_filter` on archetypes that are already reconciled; the trade-log gate showed 12 of 14 files byte-identical across this change. Getting one would mean writing a NinjaScript archetype with a secondary series purely to produce it, which is the NinjaTrader time `CONTRIBUTING.md` reserves for candidates worth trading.

Everything else — that the side is a three-state label, that equality gets its own state, that the kind is fixed at EMA — is a research choice with no NT8 counterpart, and is recorded in `docs/roadmap.md` § "Multi-timeframe moving averages".

## Contract data

**Exports are moving windows, not snapshots.** NinjaTrader serves each contract for a limited period and drops the tail once it expires, so a folder of exports silently loses history over time. `data/archive/` accumulates instead and is the only thing ingestion reads, which is what makes "keep the current history and use the AddOn from here" a workable plan rather than a slow erasure. `SOURCE_DIRS` merges the manual export first and the AddOn second, because the AddOn reads the provider's settled archive while a manual export is live tick aggregation plus whatever NinjaTrader happened to hold locally.

**A manual Tools → Historical Data export returns ~95 days per contract**, regardless of the range requested, ending ~4 days before expiry. On that data alone the volume crossover falls at or after the point coverage stops, so measured bar-aligned across all 18 roll pairs the back contract never overtook the front, and every roll fell back to the coverage handover (`METHOD_COVERAGE`).

**That is a limit of the export, not of NinjaTrader.** Pulling bars through `BarsRequest` (`ninjatrader-scripts/AddOns/NqbtHistoricalExporter.cs`) returns three to six months more per contract — thin, because a deferred contract barely trades, but enough to see the back contract's liquidity ramp. It also warms NinjaTrader's own local database, after which a manual re-export returns the union: MNQ 06-26 went from ending 2026-06-11 to running through 2026-06-18, its expiry week.

Re-exporting every contract after the AddOn had run returned the full contract life — roughly six months out through to expiry, against ~95 days before. With that merged into `data/archive/`, **all 18 MNQ rolls and all 18 NQ rolls now detect a genuine volume crossover** and none falls back to the coverage boundary. Handover ratios run 1.26–4.35 (MNQ) and 1.17–4.75 (NQ), and every roll in both roots is decided on a session of at least 1,251 shared bars.

The NQ re-export also added six contracts the archive had never held — 03-22 through 12-22 and 09-26 — taking the archive from 33 contracts to 38 and from 4,090,398 bars to 4,601,503. NQ's continuous series grew from 1,258,980 bars to 1,633,461 and now starts 2021-12-05 rather than 2022-10-09.

**The two roots corroborate each other, and that caught a bug.** Run side by side, 17 of 18 roll dates agreed exactly. The one that did not — MNQ 03-23 → 06-23 on 2023-03-13 against NQ's 2023-03-14 — turned out to be decided on a 120-bar stub where MNQ read 1.46 and NQ read 0.68. Neither figure is a session verdict; they are two hours of overnight trade. The crossover test now skips a session with too few shared bars to be conclusive rather than letting it decide (`conclusive` in `overlap_volume`), which moved that one roll to 2023-03-14 and left the other 35 in both roots untouched.

**Correcting the roll dates costs bars, and that is the right trade.** Rolling at the true crossover means the front contract supplies the days a coverage-boundary roll used to hand to the back contract — and NT8's per-contract data has holes there. MNQ 03-22 holds 60 bars on 2022-03-10 between full sessions either side, so the continuous series now shows those near-empty sessions rather than papering over them with the wrong contract. The gaps are real and were always there; they are simply no longer hidden. Filling them from the back contract would splice two different prices into one session — the offset across this roll is 8.75 points — so they stay visible instead.

**The hole is systematic, and it is the same hole in both roots.** Two or three days before most rolls, a contract holds only the Sunday-evening 18:00–19:00 ET hour for a whole trading day and then resumes normally. NQ 12-25 has 1,380 bars on 2025-12-12, 60 on 2025-12-15, and 1,314 on 2025-12-16. Across the spliced series that leaves 18 thin sessions in NQ (1,779 bars) and 19 in MNQ outside its early low-liquidity listing period. This is exactly where the crossover gets decided, which is why the conclusiveness guard above matters more than its size suggests.

MNQ 06-26 → 09-26 is the clearest example of the crossover itself:

| trading day    | front 06-26 | back 09-26    | ratio    | shared bars |
| -------------- | ----------- | ------------- | -------- | ----------- |
| 2026-06-11     | 3,659,192   | 52,989        | 0.014    | 1,359       |
| 2026-06-12     | 2,520,399   | 519,731       | 0.206    | 1,380       |
| **2026-06-15** | 596,993     | **1,721,764** | **2.88** | 1,380       |
| 2026-06-16     | 394,080     | 2,775,306     | 7.04     | 1,380       |

The roll moves from 2026-06-12 to 2026-06-15 — the coverage boundary was three days early.

**Handover ratios must be read against `shared_bars`.** This same roll previously reported 0.27 and was flagged as premature for weeks. That figure came from a 60-bar stub, not a session; the four full days before it sat at 0.9–1.4%. The stub was not evidence of an imminent roll, and it was not evidence against one either — it was 4% of a session. That lesson is now enforced in code rather than left to whoever reads the diagnostic table.

**Volume comparison must be bar-aligned, not calendar-aligned.** Comparing whole-day volume compares a truncated session against a full one and manufactures a crossover that isn't there; this produced a false "crossover on 2024-03-11" early in development.

Back-adjustment offsets are economically sound as a sanity check: −204 to −296 points in 2024–2026, and +2.00 / −31.50 / −75.00 across 2022, tracking the Fed hiking cycle. The residual jump at each roll equals the back contract's own move across the weekend gap exactly — real market movement, correctly preserved.

### Deferred months trade too thinly to decide a roll

**A full-length session is not the same thing as a traded one, and the stub guard above only catches the first.** `conclusive` originally asked whether a session held enough shared bars to be a session at all, which is the right question for NT8's near-empty Sunday-evening hole. It is the wrong question for two deferred months, which print all day on a few hundred lots months before either becomes the front contract. The lead changes hands there on noise, and the first such session decides the roll.

**Gold is where this surfaced, because its listed months overlap far longer than the equity index quarterlies do.** GC 02-22 and GC 04-22 share 46 sessions beginning 2021-10-11, while GC 12-21 is still the front contract. On 2021-10-12 the pair traded 228 lots against 256 over 90 shared bars — enough bars to pass the stub test — and the roll landed fifteen weeks early, out of order with its own neighbour. `_check_roll_monotonicity` caught it, so the failure was a refused splice rather than a wrong series, but the detection was what needed fixing.

The genuine handover is 2022-01-27, at 132,769 against 139,479 over 1,375 shared bars.

**`ACTIVE_VOLUME_FRACTION` adds the missing half of the test: a session decides a roll only if the pair's combined volume reaches 5% of its busiest shared session.** The floor is measured against the busiest session rather than the median because for these pairs the median *is* a deferred-month session — the same contamination that made the bar-count test insufficient. Three rolls move, and the separation is two orders of magnitude rather than a judgement call:

| roll                                     | combined volume on the chosen session | share of the pair's busiest session |
| ---------------------------------------- | ------------------------------------- | ----------------------------------- |
| GC 02-22 → 04-22                         | 484                                   | 0.0014                              |
| GC 04-22 → 06-22                         | 851                                   | 0.0027                              |
| MGC 02-22 → 04-22                        | 1,003                                 | 0.0139                              |
| weakest healthy roll in either gold root | ~55,000                               | 0.160                               |
| weakest healthy roll in NQ               | 411,516                               | 0.373                               |

**No roll in NQ, MNQ, ES or MES moves**, which is what makes this safe to land against stored campaign results: the guard is measured over all 144 adjacent pairs across the six roots and changes exactly the three above.

**The two gold roots corroborate each other the way the index roots do.** After the fix GC and MGC agree exactly on 18 of 29 rolls and the remaining 11 differ by a single session, which is the micro rolling a day later — NQ/MNQ disagree on 2 of 19 and ES/MES on 1 of 24, all by one session. Before the fix the three bad rolls disagreed by three to fifteen weeks.

**NinjaTrader will not serve an October gold contract, and it is alone in that.** GC and MGC therefore run Feb/Apr/Jun/Aug/Dec here, and the December contract carries a double window — about 120,000 bars against 60,000 for the others. The Historical Data download refuses `GC 10-25` as an invalid instrument, for every year, so there is nothing to ingest rather than something not yet ingested.

**October is a regular COMEX delivery month, not a thin serial one.** CME lists GC for delivery in any February, April, June, August, **October** and December within a 24-month window, plus three consecutive serial months on top. Databento's GC catalog carries `GCV6`, Barchart publishes `GCV25` and `GCV26`, and TradingView lists the full monthly chain. `contract_months` originally carried `GJMQVZ` for exactly that reason and it was right about the exchange.

**It is dropped anyway, because the month set here answers "what can this pipeline obtain", not "what does COMEX list".** A month NinjaTrader will not serve is a `ContractId` that parses, validates and can never have bars behind it — the failure mode #69 introduced the check to prevent. Both gold roots therefore list `GJMQZ`, and that is a statement about the data source rather than about gold. #333 carries the other direction: a source that does serve October would need this reverted and the month set made per-source.

**Nothing is missing from the continuous series, and the splice shows why.** `GC 12-25` is the front month continuously from August through November 2025 — 28,948, 30,203, 31,620 and 22,079 bars — so the window where October would sit is covered by December rather than left empty. Gold's volume concentrates in the even months regardless of what is listed, which is what makes the curated cycle the right splice and not a degraded one.

**SI, SIL and CL have since been ingested; MCL has not.** Silver's Mar/May/Jul/Sep/Dec cycle and crude's twelve months are confirmed against what NinjaTrader served — every contract parses and no month was refused. MCL remains registered and unread, so its month set is still the cycle as written down rather than anything NinjaTrader has confirmed.

### A week of bars is stamped 672 minutes early

**Sunday 2020-10-18 to Friday 2020-10-23 carries timestamps 11 hours 12 minutes ahead of the bars they label**, and it is the only such week in the archive.

The signature is visible without any analysis: the daily maintenance break sits at 05:49–06:49 ET instead of 17:00–18:00, the Sunday session opens in the early afternoon, and Friday stops before 06:00. Out-of-session share on the affected contracts runs to 1.1% against a normal rate two orders of magnitude lower, which is close enough to `ingest.STRAY_SHARE_LIMIT` to be worth knowing.

**The offset was measured rather than guessed.** Cross-correlating each contract's minute-of-day volume profile for that week against the weeks either side puts the best lag at **+672 minutes** on NQ, MNQ, CL and SI and +671 on ES, at r = 0.728–0.933, against a negative correlation at lag zero. Five instruments agreeing to the minute makes it a database-level event rather than anything per-contract. 672 minutes is not a timezone, which rules out the obvious explanation.

**Thirteen contracts across six roots are affected** — CL, ES, MES, NQ, MNQ and SI — and roughly 5,900 bars per root survive into a spliced series, because only the portion falling in the template's break window is dropped as out-of-session. The remainder looks in-session and carries the wrong time of day, so anything reading the clock is wrong for those five sessions.

**The archive is trimmed forward past it**, keeping only bars stamped from 2020-10-25 — the Sunday open of the first clean session. That is the cheapest repair and it is not free: it removes both index roots' 09-20 contracts entirely and about seven months of their history, four months of ES and MES, and rather less of the rest. `docs/findings/m44-registry-resweep.md` § "What changed in the data, and why" records what the trim cost and why a shift of this kind cannot be corrected by adding the offset back — the affected week's true extent is bounded by the surrounding sessions rather than known.

### CL's exports hold a systematic two-month hole

**Every one of the 72 crude contracts is missing about 58 days, from roughly 98 days before expiry to roughly 39.** The boundaries are consistent to within a day or two across six years, both the AddOn and the manual export agree, and re-running either does not fill it — so it is a property of what NinjaTrader serves for this root rather than a failed export. SI and SIL have no such hole, so it is not a COMEX or NYMEX trait.

**It costs nothing, and that is worth checking rather than assuming.** A contract's front-month period falls entirely inside the window that does have data. Checked across all 70 interior front-month windows, the only absent weekday sessions are market holidays — Christmas Day and Good Friday. A correctly rolled crude series would be intact.

**What the hole does break is the roll diagnostic**, by stripping the mid-life overlap a volume comparison would use. That interacts with a separate and more fundamental problem recorded in `.claude/rules/data-pipeline.md` § "Rolls": crude's liquidity is not monotonic in expiry, so the back contract can lead for months before the handover. The hole makes that harder to see; it does not cause it.
