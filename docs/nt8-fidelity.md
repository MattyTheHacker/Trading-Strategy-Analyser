# NT8 fidelity: what the simulation reproduces, and how it was established

Everything here was verified against real NinjaTrader 8 Strategy Analyzer runs — first a
summary, then a full trade-list export of 1,208 leg exits on MNQ 03-24 for DeadCatBounce,
and later a second export of 3,156 leg exits on the same contract for PullBackAndGo, which
is what put the long side under the same scrutiny. Several of these rules are invisible in
a summary and only surfaced from a trade list. They are recorded because rediscovering them
is expensive and because getting any one of them wrong shifts results by more than any
parameter does.

**Two rules below were found only by the long side**, having been unreachable from
DeadCatBounce: gapped stop fills, which its window happened not to contain, and stop-entry
submittability, which its trigger cap makes structurally impossible. A single archetype is
not enough to establish fill semantics, and that is the general lesson of the second run.

## Reconciliation result

Window 2023-12-09 → 2024-03-08, MNQ 03-24 single contract, EMA 21 / SMA 60 / SMA 175, all
six filters on, zero commission, zero slippage:

| | NT8 | nqbt |
|---|---|---|
| leg exits | 1144 | 1144 |
| identical exit bar | — | 1142 (99.83%) |
| identical exit price | — | 1143 (99.91%) |
| identical P&L | — | 1143 (99.91%) |
| net P&L | −873.00 | −892.50 |

The whole residual is **one leg worth $19.50**: on 2024-03-08 18:28 NT8 exits S1–S3 at
18076.75 but holds S4 for two more bars and exits it at 18067.00, despite all four sharing
one stop. Seen twice in the dataset, both times on S4. Presumed an artefact of
`StopTargetHandling.PerEntryExecution`; not reproduced.

The comparison window deliberately excludes both ends:

- **2023-12-07/08** — NT8 warms indicators from bars before the backtest start that the
  export does not contain, so early signals differ. 11 NT8-only and 5 nqbt-only entries.
- **2024-03-11** — the export stops at 00:00 that day but NT8 backtested through 12:51,
  so it has 4 entries from bars we do not have.

Between those boundaries, **286 of 286 entries match with identical entry prices**.

## Reconciliation result — PullBackAndGo (the long side)

Window 2023-12-11 → 2024-03-15, MNQ 03-24 single contract, EMA 21 / SMA 60 / SMA 175 and
both candle filters on, VWAP off, `OrderQuantity` 4, zero commission, zero slippage:

| | NT8 | nqbt |
|---|---|---|
| trades | 418 | 416 |
| leg exits (joined) | 1,664 | 1,664 |
| identical entry price | — | 1,664 (100%) |
| identical exit price | — | 1,660 (99.76%) |
| identical exit bar | — | 1,662 (99.88%) |
| identical exit reason | — | 1,661 (99.82%) |
| **identical on every field** | — | **1,659 (99.70%)** |

The residual 5 legs are all ambiguous bars resolving the other way — the same class as
DeadCatBounce's single leg, at a comparable rate. Nothing new is inferred from them.

**`PullBackAndGoParams`' defaults reproduce that configuration, not the NinjaScript's,
because the NinjaScript does not have any.** `PullBackAndGo.cs` sets only `EmaPeriod`,
`SlowSMAPeriod` and `FastSMAPeriod` in `SetDefaults`; `OrderQuantity` and all six toggles are
left uninitialised, so in Strategy Analyzer they present as `0` and `false` until set by hand —
and an `OrderQuantity` of 0 places four orders for nothing and trades nothing at all. The
reconciled configuration is the only combination with a trade list behind it, so it is what the
defaults reproduce. `use_vwap` stays off within it deliberately: nothing has checked nqbt's
VWAP against NT8's `OrderFlowVWAP`, so switching it on would mix an unvalidated indicator into
an otherwise validated archetype.

`PullBackAndGo.cs` also has no `TPMultiplier` and no `MaxRiskPerTrade`, so there is no target
scaling and no risk cap to reject a signal with, and its trigger is a bare `High[0]` with no
entry offset — which is what exposes it to the stop-entry submittability rule that
DeadCatBounce's 2-tick cap makes unreachable. Matching the C# text means not inventing
configurability it does not have.

**nqbt takes no trade NT8 did not.** The 2 NT8-only trades are at-market buy stops NT8
accepted and filled at the expected prices, against 86 otherwise identical signals it
declined — see "A stop entry must sit beyond the market". They sit inside the declined
group's distribution on body, range, wick, risk and volume, so no rule is inferred from
n=2; a small bar revision between NT8's live database and the archive snapshot is the most
economical explanation, and both are thin bars (43 and 195 contracts).

### Why the window is not the full contract

**NT8's series is back-adjusted-merged before ~2023-12-10** and the archive's per-contract
file is not, so the two tiers are not looking at the same bars there and no amount of care
in the simulation would reconcile them. The arithmetic is exact rather than inferred:

| | |
|---|---|
| NT8's first trade | 2023-09-10 23:31, entry 15716.00 |
| archive MNQ 03-24 at that minute | **no bar** — 135 sparse volume-1 prints that day |
| archive MNQ 12-23 at that minute | High 15518.50, **+210.75 = 15716.00** |

405 of 789 entries match raw MNQ 03-24 to the tick and the earliest is 2023-12-10, which is
NT8's configured rollover. Re-running from 2023-12-11 would cover the same trades this
window already does, so it buys nothing; a *different*, fully liquid contract is the way to
add legs. Both window ends are clean: the tail needs no exclusion because both sides stop at
the same trade, 2024-03-15 10:21, with nothing after it on either side.

This is the merge caveat `CLAUDE.md` records for roll dates, arriving from the other
direction — NT8 stitches contracts on a **configured** date, not an observed one.

## Reconciliation result — NQ, the second instrument (#66)

NQ had inherited its fill-semantics confidence from MNQ rather than earning it. It has now
earned it. Window 2023-12-07 → 2024-03-10, `NQ 03-24` single contract, same configuration as
the MNQ run above, zero commission, zero slippage, both ends excluded:

| | NT8 | nqbt |
|---|---|---|
| legs in window | 1,132 | 1,124 |
| joined on `(entry_time, leg)` | — | 1,112 |
| identical entry price | — | 1,108 (99.64%) |
| identical exit price | — | 1,107 (99.55%) |
| identical exit time | — | 1,110 (99.82%) |
| identical exit reason | — | 1,111 (99.91%) |
| **identical on every field** | — | **1,105 (99.37%)** |

**No instrument-dependent behaviour was found**, which was the open question. The residual
is two trades. One (2023-12-08 13:38, all four legs) is an entry-price difference — NT8
entered at 16151.50 against nqbt's 16148.25 — and is the only unexplained case here; it is
one signal, not a pattern, and the other 285 entries in the window agree. The other
(2024-01-03 15:01) is an ambiguous entry bar where NT8 filled **S1's target and stopped
S2–S4 on the same bar**, which nqbt cannot express: its ambiguity policy resolves per trade,
nearest-to-open, and resolved the whole trade to the stop. Same class as the residuals
already recorded above, and the same rate.

## Reconciliation result — PullBackAndGo on a second contract (#92)

The long side was previously reconciled against one contract's post-merge tail. Window
2024-03-12 → 2024-06-14, `MNQ 06-24` single contract — fully liquid, and nearly 1,800 legs:

| | NT8 | nqbt |
|---|---|---|
| legs in window | 1,800 | 1,792 |
| joined on `(entry_time, leg)` | — | 1,792 (0 nqbt-only) |
| identical entry price | — | **1,792 (100%)** |
| identical exit price | — | 1,787 (99.72%) |
| identical exit time | — | 1,786 (99.67%) |
| identical exit reason | — | 1,791 (99.94%) |
| **identical on every field** | — | **1,785 (99.61%)** |

Every entry price agrees, on a contract that had never been tested. The residual 7 legs are
dominated by the **L4 runner exiting later in NT8 than in nqbt**, which is the same
`StopTargetHandling.PerEntryExecution` artefact recorded against S4 in the first
reconciliation — the two runs now show it on both sides of the market, which makes it a
property of NT8's per-entry handling rather than of either strategy.

This run is also what corrected the export-timezone rule; see "Sessions" below.

## Rules the simulation implements

### Entry orders are not GTC

`EnterShortStopMarket` under NT8's **managed** approach is cancelled at the close of the
following bar if unfilled, despite `TimeInForce.Gtc` on the strategy. A signal at the close
of bar `t` places an order live for bar `t+1` only.

Getting this wrong is the difference between an order that rests indefinitely and fills on
an unrelated later bar, and one that gets a single chance.

**Why, established later by reflecting over `NinjaTrader.Core.dll`.** This is not a rule NT8
imposes on all strategies — it is the default of a parameter the short overload does not
expose. The long-form overload carries it:

```csharp
EnterShortStopMarket(int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double stopPrice, string signalName)
```

`DeadCatBounce.cs:177-180` calls the three-argument form
`EnterShortStopMarket(int quantity, double stopPrice, string signalName)`, so
`isLiveUntilCancelled` is false and the managed approach auto-cancels at bar close.
`NinjaTrader.Cbi.Order.IsLiveUntilCancelled` exposes the resulting state on a live order.

**`TimeInForce` and `isLiveUntilCancelled` are different layers**, which is why setting
`TimeInForce.Gtc` on the strategy changed nothing. `NinjaTrader.Cbi.TimeInForce`
(`Day, Gtc, Ioc, Opg, Gtd`) instructs the *exchange* how long to keep a working order;
`isLiveUntilCancelled` governs whether *NT8* submits a cancel of its own at bar close. One
does not imply the other.

The simulation reproduces the one-bar lifetime because that is what `DeadCatBounce.cs` does,
and it stays that way. The generalisation to longer-lived orders — needed by future
archetypes, and the three routes to it — is specified in
[roadmap.md](roadmap.md) under "Order lifetime in NT8". **Note that reflection establishes
the API only.** Whether Strategy Analyzer honours a resting order identically to live, when
exactly the cancel lands relative to the bar close, and how a resting order interacts with
the session-close flat are behavioural questions that still need a trade list, and nothing in
`nqbt/sim/` may assume an answer before then.

### Trigger is capped below the close

```csharp
double entryPrice = Math.Min(Low[0], Close[0] - (TickSize * 2));
```

Not simply the bar's low. An inverted hammer closes near its low by construction, so the
close-based term binds on about **a third of signals** and drags the trigger 1–2 ticks
under the low — enough to turn a marginal fill into no fill. Ignoring it produced 5% too
many entries.

### Fill

On bar `t+1`: a gap through the trigger fills at the open, otherwise a trade down to the
trigger fills at the trigger. No touch, no fill, order gone.

### A stop entry must sit beyond the market to be submitted

A stop-market order whose trigger is not strictly beyond the price it is submitted into is
not a stop order, and NT8 declines it. The market at submission is the signal bar's close,
`Calculate.OnBarClose` being what it is.

`PullBackAndGo.cs` triggers on a bare `High[0]`, so a bar that **closes on its high** asks
for a buy stop at the market. This was the whole of the 86 trades nqbt took and NT8 did not:
the signal bar closed on its high in **86 of 86** of them, against **2 of 416** among the
trades NT8 did take. `High == Close` on 24.8% of all MNQ 03-24 bars.

**DeadCatBounce cannot reach this**, which is why the first reconciliation never saw it. Its
`min(Low[0], Close[0] − 2 ticks)` cap binds on exactly the bars that would otherwise be
unsubmittable and puts the trigger two ticks under the close: **0 of 132,454 bars** carry a
DeadCatBounce trigger at or above its close. The cap recorded above as a fill-rate detail
turns out to also be what makes the short archetype structurally immune.

### A stop fills at the open when the bar gaps through it

A stop is a market order once triggered, so a bar that opens past it offers no trade at the
stop level and the fill is the first price there is. Filling at the stop price regardless
was worth **$222.50 of a $292.50 result** over the 1,664 reconciled legs; NT8's exit price
equals the exit bar's open on **115 of the 116** disagreeing stop fills.

Traced at 2023-12-11 09:15: the ratchet reaches 16288.25 and the 09:18 bar opens at
16287.00, already through it. NT8 fills 16287.00, nqbt filled 16288.25.

**The rule does not apply on the entry bar.** The position did not exist at that bar's open,
so an open beyond the initial stop says nothing — price still had to travel through the
trigger to open the position at all, and only then could it come back to the stop, which it
reaches at the stop's own price.

This one is not long-specific: it moved 56 of 1,380 legs on the pinned MNQ 03-24
DeadCatBounce capture, always to a worse fill and never a better one. It survived the first
reconciliation because **none of those legs fall inside that run's 1,168-leg window** — all
1,168 still match on every field. A reconciliation window is evidence about the bars it
contains and nothing else.

### Limit orders must trade *through*, not touch

`IsFillLimitOnTouch = false` — set in `SetDefaults` and unchecked in the Strategy Analyzer.
A profit target needs `low < target`, not `low <= target`.

Verified decisively: **all 15** initial target-fill disagreements were bars whose low
equalled the target to the tick. Stops are unaffected — a stop becomes a market order on
touch.

### Ambiguous bars resolve to whichever level is nearer the open

When a bar contains both the stop and a target, bar-close OHLC cannot say which came
first. NT8 fills the level nearer the bar's **open**, and when the target goes first the
stop still takes the remaining legs *within the same bar*.

| bar | dist to target | dist to stop | NT8 filled |
|---|---|---|---|
| 2023-12-19 06:29 | 0.00 | 1.00 | target |
| 2024-01-11 16:11 | 0.50 | 6.25 | target |
| 2024-01-30 13:51 | 1.75 | 2.75 | target |
| 2024-02-12 14:26 | 1.75 | 2.00 | target |
| 2024-02-28 18:07 | 2.50 | 4.00 | target |
| 2024-01-03 08:41 | 1.75 | **1.50** | **stop** |
| 2024-01-16 00:31 | 4.25 | **0.75** | **stop** |

7 of 7. A bar-direction rule (up bar ⇒ Open→Low→High→Close) fits only 5 of 7 — all seven
bars are up bars, and the two NT8 stopped out are the ones where the stop was nearer.

`ambiguity_policy` exposes this: `1` reproduces NT8 (default), `0` assumes a blanket worst
case. Worst case is *more* pessimistic than NT8, not equal to it — a distinction that was
originally stated backwards in this project and corrected only by the trade list.

The 2024-01-11 16:11 bar is the clearest evidence: NT8 filled S1's target at 16836.00 **and**
stopped S2/S3/S4 at 16842.75 on that one bar.

### Ratchet reads the just-closed bar

```csharp
double newStop = High[0] + (TickSize * 2);   // not High[1]
if (previousStop < newStop) return;          // never loosens
```

The stop set at the close of bar `i` is live during bar `i+1`. `ratchet_lag` exposes the
older `High[1]` variant, which holds trades roughly a third longer (2.12 vs 1.65 average
bars) and behaves like a genuinely different strategy.

**`PullBackAndGo.cs` ratchets to `Low[1]`, not `Low[0]`** — lag 1, the bar *before* the
just-closed one. The trade list settles it: lag 1 leaves 120 disagreeing legs of 1,664, where
lags 0, 2 and 3 each leave around 1,100.

**The ratchet's offset is separate from the entry stop's**, which is why
`ratchet_offset_ticks` exists beside `stop_offset_ticks`. DeadCatBounce ratchets to
`High[0] + TickSize * 2`, reapplying its entry offset; PullBackAndGo ratchets to
`Low[1] - TickSize * 2`. Because `ratchet_lag = 1` puts the first evaluation on the *signal*
bar itself, the offset makes that first ratchet reduce to exactly the initial stop and
therefore a no-op — a bare `Low[1]` instead tightened the stop by two ticks before any bar had
closed with the position open.

### Targets snap to the tick grid — even when the C# does not ask for it

`RoundToTickSize` in `DeadCatBounce.cs`. A 1.5× multiple of an odd tick count otherwise
lands on a half tick, which no exchange accepts.

**`PullBackAndGo.cs` never calls it, and NT8 snaps the targets anyway.** The port originally
took the C# at its word and left them un-rounded, on the reasoning that matching the text
beats assuming symmetry; the trade list settled it the other way. Rounding took the
reconciliation from 176 to 120 disagreeing legs, and the discriminating case is a half-tick
target that nqbt placed at 16504.375 and NT8 filled at 16504.50.

So the snap is the platform's, not the script's, and `round_targets` should be true for any
archetype — it is a property of what an exchange will accept, which no NinjaScript can opt
out of.

**And it is not only targets.** An exchange takes a stop at a half tick no more than a limit,
so a stop has to be snapped too. Both stop-market ports place theirs at a bar extreme plus a
whole number of ticks, so they land on the grid by construction and could not reach this;
InsideBar's `Low[1] − ATRMultiplier × ATR` misses it on nearly every trade. The snap goes on
before the risk is taken, so the submittability test and every `r_multiple` measure the stop
that was actually submitted. **`EmaCrossover`'s ATR stop has the same shape and is not yet
snapped** — it is `TIER1_ONLY` with no C# to reconcile against, so it is recorded here rather
than fixed alongside.

### The entry filters' equality boundaries, which do not mirror each other

Every filter is ported as the **negation of the C#'s rejection**, not as the positive form
someone would write from the description. The two differ exactly at equality, and the
boundaries are not symmetric between the two archetypes.

| filter | the C# rejects on | so equality | in `conditions.py` |
|---|---|---|---|
| downtrend gate | `Close[0] > ma[0]` | **passes** | `below_series` = `~(close > ma)` |
| uptrend gate | `Close[0] < ma[0]` | **passes** | `above_series` = `~(close < ma)` |
| previous bar green | `Close[1] < Open[1]` | **passes** (doji is green) | `_previous_bar_green` = `>=` |
| previous bar red | `Close[1] >= Open[1]` | **fails** (doji is not red) | `_previous_bar_red` = `<` |

**`above_series` is not `~below_series`.** Each strategy's own C# chose to treat its own
boundary as a pass, independently, so the two *overlap* at `close == ma` rather than
partitioning it. Writing either as the positive comparison would silently drop those bars.

**The doji boundary is the one place the two archetypes genuinely do not mirror.**
`previous_bar_green` admits a doji-closed prior bar and `previous_bar_red` rejects one, which
makes the pair exact complements rather than a pair overlapping at equality. `PullBackAndGo.cs`
used to read `Close[1] > Open[1]` there, which *did* make them symmetric, and the port followed
it; the strictening cost **103 of 760 signals on MNQ 03-24 — 13.6%**. Check the operator rather
than assuming the mirror holds.

**Both candlestick patterns require `body > 0`, so a doji never qualifies** however long its
wick — with a zero body the "wick at least twice the body" test is trivially satisfied.
`_inverted_hammer` (`DeadCatBounce.cs`) wants the upper wick ≥ 2× body and the lower wick ≤
body; `_hammer` (`PullBackAndGo.cs`) is the same with the wick roles swapped.

### Max risk is in ticks, not dollars

```csharp
if (risk > maxRiskPerTrade * TickSize) return;
```

`MaxRiskPerTrade = 250` means 250 ticks = 62.5 MNQ points, **not** $250. It never binds at
that default — the largest observed risk is 24.25 points.

### M18 — the crossover rules, and that none of them has evidence yet

`EmaCrossover` is the first archetype with **no NinjaScript**, so nothing below is backed by
a trade list. It is recorded here anyway, because the point of writing the rules down before
there is a C# is that the port has something to be checked *against* — and because the
prime directive binds during development. A rule chosen here that NT8 cannot express makes
the archetype unreconcilable later, which wastes the exploration rather than merely leaving
it unvalidated. Each item below therefore names the NinjaScript it would be written as.

`Archetype.tier2` is `TIER1_ONLY`, and it reaches the results table so a ranking cannot put
these rules beside the reconciled ones without saying which is which.

**`CrossAbove(a, b, n)` is a window, not a bar.** NinjaScript asks whether the cross happened
within the last `n` bars, so the naive form

```python
fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
```

is the `n = 1` case and not the definition. `conditions.cross_above` implements the window,
with `n` swept via `cross_lookback`. Equality is resolved on the *prior* bar (`<=`), so two
series that touch and then separate upward have crossed — vanishingly unlikely for EMAs and
entirely reachable for SMAs of tick-grid prices, which is why the boundary is pinned rather
than left to whichever operator got typed.

**The entry is market-on-next-open, and it is unconditional.** `EnterLong()` / `EnterShort()`
under `Calculate.OnBarClose` submit a market order at the close of bar `i`, which NT8 fills
at the open of bar `i+1`. There is no trigger price, so no "no touch, no fill" and no
submittability rule — the two things that shape every DeadCatBounce entry do not apply. What
does apply is the flatten point: a bar at or past the cutoff cancels the order rather than
filling it, exactly as it cancels a resting stop-market entry.

**The signal exit fills at the next bar's open too**, and takes precedence over the stop and
the targets on that bar. Both follow from it being a market order: it is filled at the bar's
first price, and NT8's managed approach cancels a position's brackets when something else
flattens it. This is the only place `EXIT_SIGNAL` is produced.

**The protective stop has no structural anchor.** A crossover has no signal wick, so the
default is an ATR multiple hung off the fill — planned risk is then exactly
`atr * multiple` — read from the ATR at the **signal** bar, the last completed one. The
alternative mode is the adverse extreme of the last `swing_lookback` completed bars plus the
usual two ticks, which is the closest thing to DeadCatBounce's stop. Both are swept.

**The ATR stop has a hard floor in dollars per contract**, off at `0`. A quiet regime
otherwise sizes a bracket smaller than the round trip costs to trade, and `min_bracket_dollars`
is what stops it: the stop distance is `Math.Max(atr * multiple, floor / pointValue)`. It is
expressible — `Instrument.MasterInstrument.PointValue` is the conversion, so a port writes the
property in dollars and divides, exactly as `nqbt` does through
`Instrument.dollars_to_points`. It applies to the ATR mode only; the swing mode's stop is a
structural level rather than a distance. Reasoning and the effect on R:
[roadmap.md](roadmap.md) § "ATR-multiple brackets and the dollar floor".

**An entry whose stop would sit at or through its own fill is skipped.** This is the
existing "a stop entry at or through the market is never submitted" rule applied to the
protective stop, and it is reachable here for the same reason the entry rule became
reachable with PullBackAndGo: the fill is wherever the next bar opens rather than at a
trigger the stop was placed against, so a gap can put the swing reference on the wrong side.

**Flat between trades, not stop-and-reverse.** The classic crossover reverses in a single
order. Here the flip closes the position and opens the new one as two fills at the same open
price, each paying its own slippage and commission and each appearing as its own trade in
the log. That is a real difference from published crossover results and from what
`EnterShort()` while long would do in NT8, and it is the one item on this list that a port
would have to be written *around* rather than to.

**`r_multiple` means something different.** R is `stop - entry`, so with an ATR stop the
four-leg scale-out is volatility-scaled rather than structure-scaled. Crossover results are
**not comparable to DeadCatBounce results at the same R numbers** — the same trap as
comparing profit factor across bar resolutions. Where the dollar floor binds it is neither:
R is then dollar-scaled and the same on every ATR multiple in the sweep.

### M22 — the InsideBar rules

`InsideBar.cs` exists, so unlike M18 every rule below is a reading of real C#, and every one has
now been diffed against a Strategy Analyzer trade list — "Reconciliation result — InsideBar"
below. It earned its place on what it reaches rather than on what it might make: three parts of
the fill model no other archetype touches, and `bracket.py` inherits whatever is wrong in them.
Two of the three rules the port had to infer turned out to be wrong, which is the argument for
reconciling each archetype rather than trusting the shared engine because the first one passed.

**The entry is M18's market-on-next-open.** `EnterLong(0, OrderQuantity, "entry")` under
`Calculate.OnBarClose`, so there is no trigger price, no "no touch, no fill" and no
submittability test on the entry itself. A bar at or past the flatten cutoff cancels the order
rather than filling it.

**The signal reads two bars back, and both bounds are strict.** The inside bar is `[1]` and its
mother bar is `[2]`, so `High[1] < High[2] && Low[1] > Low[2]` — a bar equalling either extreme
of its predecessor is not inside it. The break is judged on `Close[0]` against the **mother**
bar's extreme plus `ErrorMargin` of the mother bar's *range*, never against the inside bar's own
high or low.

**The three moving-average gates are strict, and do not mirror the two ports.** `InsideBar.cs`
writes the positive form — `Close[0] > ema[0] && Close[0] > smaFast[0] && Close[0] > smaSlow[0]`
— where both ports write the negation of a rejection. So equality **fails** here and **passes**
there, which is a third pattern for the table under "The entry filters' equality boundaries".
The shared boolean grid holds `above` as `~(close < ma)`, so it is the wrong boundary for this
archetype and `insidebar_trends` reads the raw values instead. That is what
`needs_ma_values` costs, and why it is on.

**`BarsRequiredToTrade` costs one bar more here than in either port.** `CurrentBars[0] <=
BarsRequiredToTrade` returns, against `CurrentBar < BarsRequiredToTrade` in both others. An
off-by-one in warm-up is invisible in aggregate, so it is pinned by a test rather than assumed
to mirror them.

**`IsFillLimitOnTouch = true`, and this is the archetype that finally checked it.** Set in
`SetDefaults`, against `false` on both ports, so a profit target fills on `low <= target` rather
than needing `low < target`. `fill_limit_on_touch` had been a sweepable axis all along and no
archetype's defaults reached the `true` side of it, so the rule recorded under "Limit orders
must trade *through*, not touch" was evidence about the `false` branch only. Both branches now
have a trade list behind them.

**The bracket is computed in `OnExecutionUpdate`, from the fill, with two different anchors.**

```csharp
double atr    = ATR(ATRLength)[0];
double stop   = Low[1] - ATRMultiplier * atr;   // long
double target = price + atr;                    // `price` is the actual fill
```

Both ports place a bracket against a *trigger* the fill is defined relative to. Here the target
hangs off the **fill** and the stop off a bar's adverse extreme, which is two anchors in one
bracket. The stop never moves afterwards: there is no ratchet, and `SetStopLoss`'s third
argument is `isSimulatedStop`, not a trailing flag.

**`OnExecutionUpdate` runs with the *signal* bar still current**, not the fill bar. So `[0]` is
the signal bar and `Low[1]` is the bar before it — the **inside** bar. The port originally had
both terms one bar later, reasoning that the fill lands on the next bar's open so the series
must have advanced by then. The trade list settled it the other way on both, decisively:

| candidate | reproduces NT8 |
|---|---|
| stop from the inside bar `[1]` × the signal bar's ATR `[0]` | **100%** of stop exits |
| stop from the signal bar × the signal bar's ATR | 0% |
| stop from the fill bar × the fill bar's ATR | 0% |
| target from the signal bar's ATR | **99.75%** of target exits |
| target from the fill bar's ATR | 19% |

The correct reading is also the one that reads **no bar the fill could not have seen**, which
removes the open question the port shipped with. It is a warning about the general case: `[0]`
inside `OnExecutionUpdate` is not the execution's bar, and any future archetype that brackets
from there inherits this indexing.

**The geometry is lopsided by design.** `ATRLength = 3` with `ATRMultiplier = 10.0` puts the
target 1x ATR(3) from the fill and the stop 10x ATR(3) beyond the inside bar — a high-win-rate,
rare-large-loss profile whose R multiples cluster just above zero. `r_multiple` uses planned
risk, so **these R numbers are not comparable to another archetype's at the same value**, with
more force than the same caveat carries for an ATR stop generally. And 1x ATR(3) on a quiet bar
is a target that can be smaller than the round-trip commission, which no ranking will announce.

**The stop is snapped to the tick grid, not just the target.** An ATR multiple lands off the
grid where both ports' whole-tick offsets cannot — see "Targets snap to the tick grid", which
this archetype is the first to reach the stop half of.

**`ExitOnSessionCloseSeconds = 180` changes nothing, and the port must not act on it.**
`InsideBar.cs` sets 180 where both ports set 30, which should put the flatten at 16:57:00 ET
rather than on the session's last bar. It does not: NT8 flattened at 17:00 on every one of the
eleven session-close exits in the reconciliation window, and honouring the 180 in the simulation
*lowered* agreement from 99.64% to 98.42%. Whether the Strategy Analyzer resets the property or
historical flattening is simply per-bar, a trade list cannot tell apart — the observable is that
**a backtest flattens on the session's last bar**, which `exit_on_close_seconds=30` reproduces
for every archetype at any bar resolution below a minute. The property was briefly carried per
archetype and that was a regression; it is one default again.

**Every property is initialised.** Unlike `PullBackAndGo.cs`, this `SetDefaults` sets all seven
declared properties, so `InsideBarParams`'s defaults are the NinjaScript's directly rather than
a reconciled configuration.

**What a reconciliation of it has to hold fixed.** The no-entry window has to be off on *both*
sides — `no_entry_minutes_before_close=0` here, and the Strategy Analyzer run started outside
16:00–17:00 ET so the C#'s wall-clock test cannot fire — because that is the only configuration
in which the two are testing the same strategy. `tools/reconcile_nt8.py`'s `CONFIGS["InsideBar"]`
is that configuration. Everything else is `SetDefaults` unchanged.

### The position guard has to read `Position`, not `PositionAccount`

```csharp
if (PositionAccount.MarketPosition != MarketPosition.Flat) return;   // never fires
if (Position.MarketPosition != MarketPosition.Flat) return;          // what it meant
```

`PositionAccount` is the **account** position, and in a Strategy Analyzer backtest it never
leaves `Flat`. So the guard never fired, `EnterLong()`/`EnterShort()` reached the managed
approach while a position was open, and NT8 **reversed**: `EntriesPerDirection = 1` blocks a
second entry on the same side, but an opposite-side entry closes the position and opens the new
one in a single transaction.

The first export made it unmissable — **2,581 of 21,884 trades exited as `Close position`, and
every one handed straight over to an opposite-side entry at the same timestamp and the same
price**, where no other exit type did. NT8 took 1,262 trades in the reconciliation window to the
port's 956, and 96.7% of the port's entries were NT8 entries: the port was not inventing trades,
it was missing the ones NT8 took while already in a position.

`InsideBar.cs` now reads `Position` and the reversals are gone — zero `Close position` exits in
the second export. **This is the second property in this one script that behaves differently in
Strategy Analyzer from what its author assumed**, alongside the wall-clock `Now` below, and it
is the reason a port is not evidence about anything until a trade list has been diffed against
it. `InsideBarTrailing.cs` is immune: it guards on `Position` as well, behind an
`IgnoreAccountPosition` toggle.

### Reconciliation result — InsideBar (#126, #157)

Source: **MNQ 03-24, 1-minute, an NT8 Strategy Analyzer export of 16,744 trades** at
`SetDefaults`, reconciled over **2023-12-14 → 2024-03-15**.

**The window is the front-month period, and that is forced.** Requesting `MNQ 03-24` from 2020
gives NT8's *merged* series, not that contract's own bars: before the December roll only 10.9%
of exported entries land inside the archive's bar for their timestamp, against **100.0% after
it — every one exactly at the bar's open**, which is the market-on-next-open entry confirmed to
the tick. A reconciliation window is evidence about the bars it contains.

| field | agreement |
|---|---|
| entry price | 100.00% |
| exit price | 100.00% |
| exit time | 100.00% |
| exit reason | 100.00% |
| net P&L | 100.00% |
| **identical everywhere** | **968 of 968 — 100.00%** |

Reproduce it with the export in place:

```bash
./.venv/Scripts/python.exe tools/reconcile_nt8.py \
  verification/nt8_trades/nt8_trades_MNQ_03-24_insidebar.csv InsideBar "MNQ 03-24" 2023-12-14
```

**What this settled.** The `IsFillLimitOnTouch = true` branch, which nothing in the project had
evidence for. The `OnExecutionUpdate` indexing, established against both terms independently and
against an inference that had them one bar later. And that `ExitOnSessionCloseSeconds` does not
move a backtest's flatten. `Archetype.tier2` is `RECONCILED`.

**The whole residual was out-of-session stray bars, and it was not InsideBar's** (#160). The
export files carry occasional prints outside session hours which NT8, building bars against the
ETH template, never forms; `sessions.classify` flagged them and nothing dropped them, so they
sat in the array the simulation indexes. At the first bar of a Sunday session a stray becomes
`[1]`, and InsideBar's inside-bar test reads `[1]` and `[2]` directly. Dropping them in
`load_contract` took this reconciliation from **943/947 — 99.58%** to **968/968 — 100.00%**,
NT8-only entries from 22 to 1 and nqbt-only from 7 to 0, and left the DeadCatBounce and
PullBackAndGo reconciliations **bit-for-bit unchanged**, because neither reads two bars back
through a strict geometric test. The rule is general and the sensitivity is not: any future
archetype reading two bars back inherits the same exposure.

**The Presidents' Day disagreement is the one #68 fixed**, and it was the last one standing
before the strays went. A trade entered at 13:00 ET on 2024-02-19, an exchange early close,
which `force_flat_mask` measured against the template's fixed 17:00 and so never flattened.
Deriving the session end from the observed last bar took this reconciliation from 942/947 to
943/947 and left the DeadCatBounce and PullBackAndGo reconciliations above bit-for-bit
unchanged — see "The session end is the observed last bar, not the template's".

### M23 — the InsideBarTrailing rules

`InsideBarTrailing.cs` shares `InsideBar.cs`'s entry and replaces its single bracket with three
exit mechanisms the simulation did not have. Every rule below has been diffed against a
Strategy Analyzer trade list — "Reconciliation result — InsideBarTrailing" below — and **that
list overturned three of the four the port had inferred**, which is the argument for
reconciling each archetype rather than trusting a shared engine because the last one passed.

**The entry is InsideBar's, and it is shared rather than copied.** Same inside bar, same mother
bar, same three strict moving-average gates, same market-on-next-open — so
`InsideBarTrailingParams` subclasses `InsideBarParams` and both archetypes call
`insidebar_signal`. What differs is four defaults, and one of them is not a tweak:
`ErrorMargin = 0.1` against `0.01` is **ten times the breakout buffer** and a materially
different strategy. The others are `SmaSlowPeriod 125` against `200`, `OrderQuantity 6` against
`4`, and the one-hour session-end guard, which this script simply does not have. Entry price
agreed with NT8 on **100.00%** of joined legs, so the sharing is verified rather than assumed.

**The position is split across two entry orders with different exit engines.**

```csharp
firstLotQuantity  = (int) Math.Ceiling(OrderQuantity * PartialTakeProfitPercentage);  // 4 of 6
secondLotQuantity = OrderQuantity - firstLotQuantity;                                 // 2 of 6
```

`entry1` gets a fixed stop and a profit target; `entry2` gets a trailing stop and no target at
all. With `StopTargetHandling.PerEntryExecution` that is two brackets over one position rather
than one bracket with two legs, which is exactly how the port resolves it: one call to
`resolve_brackets` per lot per bar, each with its own stop, target and planned risk, and the
shared engine unchanged. The export carries 13,043 `entry1` rows and 13,043 `entry2` rows at 4
and 2 contracts, so the split itself needed no inference. The structural argument for that shape
rather than a generalised `bracket.py`: [`roadmap.md`](roadmap.md) §M23.

**Both lots are bracketed off the same fill, from the same two bars as InsideBar's.**
`OnExecutionUpdate` runs with the signal bar current, so the ATR it reads at `[0]` is the signal
bar's and `High[1] - Low[1]` is the **inside** bar's range — the indexing §M22 established
leg-for-leg, inherited here rather than re-derived, and confirmed by the trail distances
matching.

#### The trailing stop, and the two cadences that are not the same cadence

```csharp
double trailingStopDistance = (High[1] - Low[1]) / TickSize * TrailingStopMultiplier;
SetTrailStop("entry2", CalculationMode.Ticks, trailingStopDistance, false);
```

DeadCatBounce's and PullBackAndGo's ratchet moves the stop to a *lagged bar's* extreme plus an
offset; an NT8 trail stop follows the **high-water mark** by a fixed tick distance. Different
rule, different failure modes. The distance is a tick count in the C#, so the port computes it
as one and converts back rather than multiplying the range directly.

**A resting trail advances at the bar close, so it cannot be hit on the bar that set it.**
Advancing it within the bar everywhere drops agreement from 99.80% to **94.04%**, so this is
measured rather than assumed — and it matches the ratchet's cadence, which is the one thing the
port did guess right.

**The entry bar is the exception, and it advances within.** `SetTrailStop` is submitted *during*
that bar rather than resting from its open, and the export shows it acting on that bar's own
extreme: **22 of the 24 legs** that still disagreed under a uniform bar-close cadence were NT8
stopping out on the entry bar. Every one of the four cases inspected by hand is explained
exactly — for a short entered at 17484.50 with a 22.50 distance, NT8 exited at 17491.00, which
is the entry bar's low of 17468.50 plus 22.50 to the tick. Adding the entry-bar advance took the
reconciliation from 98.42% to **99.80%**.

**A trail distance under one tick refuses the trade.** The submittability rule — "a stop at or
through the price it protects is not a stop order" — applied to the trailing lot, reachable only
when the inside bar has no range at all. The export contains no such trade, so what NT8 does
with `SetTrailStop(..., 0, false)` is still unobserved; the port declines the entry rather than
running a lot with no protective order behind it. That one is still the conservative reading
rather than a measurement.

#### The `-200` gate sits above **both** branches, and the trend violation is beneath it

```csharp
if (marketPosition == MarketPosition.Flat) return;
if (position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, Close[0]) > -200) return;
if (... < -MaximumLossPerTrade && MaximumLossPerTrade > 0) { /* max loss - dead */ }
if (position.MarketPosition == MarketPosition.Long && (ema[0] < smaFast[0]))
    ExitLong("Exit Long Trend Violation", "entry1");   // and "entry2"
```

**This was the single largest correction the export made.** Reading the hardcoded `-200` as
belonging to the max-loss branch beneath it — which is how it reads if you start from that
branch — leaves the trend violation ungated, and the port fired it **340 times** in the
reconciliation window against NT8's **12**. It is an early return at the top of the method, so
the trend violation cannot fire until the open position is at least $200 down at `Close[0]`.

It is a **currency amount on the whole open position with no scaling behind it**, so it means
ten times the price move on MNQ that it means on NQ. It therefore goes through
`instruments.py`'s point value like every other monetary figure, and `position_update_loss_gate`
carries it as a parameter because the C# will not.

#### The trend-violation exit, the second `EXIT_SIGNAL` consumer

**It fires only where the position actually changed, and only where something is left to sell.**
`OnPositionUpdate` fires on position changes rather than on every bar; porting it as a per-bar
check would be a different and much busier strategy. The entry fill is a position change, but
with both lots just opened there is nothing for the exit to fill alongside — and the gate above
would block it anyway, since a fresh position is not $200 down. In the whole export the trigger
was **the trailing lot's stop, 303 times out of 303**.

**The remaining lot leaves at the price and bar the triggering fill did** — the same fill event,
not a market order on the next bar. All 303 of NT8's trend-violation exits share their sibling's
exit time and exit price exactly. Reading it as a next-bar market order, which is what §M18's
`EXIT_SIGNAL` rule would suggest, costs 12 legs; that rule describes an exit decided in
`OnBarUpdate` at a bar close, and this one is not.

**The averages are read at strategy time `i - 1`**, the same one-bar offset `OnExecutionUpdate`
has, and the comparison is strict, so `ema == smaFast` holds the position. It generalises
through the sign multiplier rather than as two branches.

#### The max-loss exit is dead, and the export confirms it

`MaximumLossPerTrade` defaults to `0`, so `< -MaximumLossPerTrade && MaximumLossPerTrade > 0`
can never be true. **Not one `Exit Long/Short Max Loss` row appears in the export's 26,086**, so
this is now a measurement rather than a reading of the C#. The port carries the reconciled
behaviour the way `PullBackAndGoParams` reproduces its reconciled configuration:
`maximum_loss_per_trade` exists, defaults to `0.0`, and raises on anything else. Enabling it
means a second currency threshold, and it would have to go through `instruments.py` exactly as
the gate above does.

### Reconciliation result — InsideBarTrailing (#127)

Source: **MNQ 03-24, 1-minute, an NT8 Strategy Analyzer export of 26,086 legs** at
`SetDefaults`, reconciled over **2023-12-14 → 2024-03-15** — the same instrument, series and
window as §M22's, changing only the strategy, so a difference between the two reconciliations is
attributable to the exit model rather than to the data.

| field | agreement |
|---|---|
| entry price | 100.00% |
| exit price | 100.00% |
| exit time | 100.00% |
| exit reason | 100.00% |
| net P&L | 100.00% |
| **identical everywhere** | **1,522 of 1,522 — 100.00%** |

Net P&L over the joined legs: NT8 −8,913.00 against nqbt −8,913.00. Reproduce it with the export
in place:

```bash
./.venv/Scripts/python.exe tools/reconcile_nt8.py \
  verification/nt8_trades/nt8_trades_MNQ_03-24_insidebartrailing.csv \
  InsideBarTrailing "MNQ 03-24" 2023-12-14
```

**What this settled**, in the order the corrections landed: that the `-200` gate governs the
trend violation and not just the dead branch under it (80.18% → 97.23%); that `OnPositionUpdate`
runs at the same one-bar offset `OnExecutionUpdate` does (→ 97.63%, and exit reason to 100.00%);
that the exit it submits is part of the triggering fill rather than a next-bar market order
(→ 98.42%); and that a trail advances within its entry bar but not within any later one
(→ 99.80%). `Archetype.tier2` is `RECONCILED`.

**The last three legs went with the out-of-session strays** (#160), the same fix and the same
cause as InsideBar's: this archetype shares that entry, so it reads `[1]` and `[2]` too. They
were leg-1 targets off by a tick or two, and dropping the strays took the run from 1,517/1,520
to 1,522/1,522. There are 4 NT8-only and 2 nqbt-only legs left at the window edges.

**The two open questions it closed were #67's.** Both were added there before the port was
written, precisely because reflection cannot answer them; both are now answered by measurement
rather than by argument.

#### How the export was produced

Same settings as §M22's, changing only the strategy.

| Strategy Analyzer setting | value |
|---|---|
| Strategy | `InsideBarTrailing`, every parameter left at `SetDefaults` |
| Instrument | `MNQ 03-24` |
| Data series | 1 minute, `Last`, `<Use instrument settings>` — the ETH template |
| From → To | `2020-01-02` → `2024-03-15` |
| Order fill resolution | Standard — the script sets it, do not raise it to High |
| Slippage | 0 ticks |
| Commission | none, and no fee template |
| Min. bars required | 5, which `BarsRequiredToTrade` already sets |

Export via **Trades → right-click → Export**, not the Summary tab: summary statistics hide fill
semantics, which is the only thing this run is for.

**The request runs to 2020 and the reconciliation starts at 2023-12-14 on purpose.** NT8 serves
its *merged* series for a contract before that contract's own bars begin, which a per-contract
archive cannot reproduce — the trailing date argument trims the export to the front-month window.

**Three exit names are new, and two are deliberately unmapped.** `Trail stop` maps to `stop` and
both `Exit Long/Short Trend Violation` map to `signal`. `Exit Long/Short Max Loss` is **not**
mapped: that branch is unreachable, so an export carrying one falsifies the reading above and
must stop the run rather than be counted as agreement.

### The session end is the observed last bar, not the template's (#68)

`sessions.seconds_to_session_end` counts down to each trading day's **last in-session bar**, and
`force_flat_mask` cuts that countdown at `ExitOnSessionCloseSeconds`. On a session that runs to
17:00 ET the two are the same thing, so the mask is unchanged there.

It changes the sessions that stop early. NT8's trading-hours template carries the holiday
calendar, so on Thanksgiving, Christmas Eve or 3 July its `ActualSessionEnd` is 13:00 and it
flattens there. Measured against the template's fixed 17:00 instead, nothing on such a session
ever reached the cutoff and **the mask came back empty** — the position was never forced flat at
all. `is_session_close` was already data-derived, so the two disagreed precisely on the days that
mattered.

Counted over the archive as it stood when this landed: **109 of MNQ's 1,269 sessions and 65 of
NQ's 1,210 had an empty mask**, 63 on each root by an hour or more, and roughly two-thirds of
those a 13:00 ET exchange half-day. The rest are sessions the data truncates rather than the
exchange.

**The failure was worse than a position held too long.** On MLK 2024 the array runs
`… 12:59, 13:00, 18:01 …`: the exchange shuts and the next session opens five hours later, so an
entry order resting from the 13:00 bar lived its one bar into **the following session** and
filled there, five hours and a session boundary from the signal that placed it. Every leg the
trade-log gate lost is that or its sibling — an entry filled *on* a half-day's last bar, which
`block_entry_at_session_close` now guards. The trade entered at 13:00 ET on Presidents' Day 2024
in the InsideBar reconciliation above is the second kind.

**The observed end approximates a calendar the data does not carry**, and it cannot tell an
exchange half-day from a session whose tail is missing. Both now flatten, which is the safe
direction: a session with no later bars has nowhere else to close the position, and the
alternative is the order jumping the boundary above. One consequence to know — a position still
open on the **last bar of the dataset** is now written as `session_close` rather than dropped
unwritten.

### A no-entry window before the session close

```csharp
sessionIterator.GetNextSession(Now, true);
if ((sessionIterator.ActualSessionEnd - Now).TotalHours <= 1) return;
```

A parameterised window, not a boolean, and **distinct from `block_entry_at_session_close`**,
which guards only a new signal on the force-flat bar. The comparison is `<=`, so a bar exactly
an hour out is blocked and the gate admits `remaining > window`. `sessions.seconds_to_session_end`
is the quantity both this and `force_flat_mask` are cut from, so a window and the flatten cannot
drift apart, and since #68 both measure against the session's observed last bar — so the window
closes an hour before a half-day's 13:00 close, as `ActualSessionEnd` does.

**`Now` is the wall clock, and that is a trap the port does not reproduce.** It resolves to
`Core.Globals.Now` — `Connection.PlaybackConnection` is null in Strategy Analyzer — so the C#
compares the end of *today's* session against the *real current time*, whatever bar is being
processed. In a backtest that makes the rule either on for every bar or off for every bar,
depending on the hour the run is started. The port implements the bar's own clock, which is what
the rule means and what live trading does.

**So this is the one rule the two tiers cannot agree on by construction**, and a Tier-2
reconciliation of InsideBar needs `Now` replaced by `Time[0]` in the NinjaScript before it can
mean anything. Until then, running the backtest more than an hour before the session close is
the only configuration in which the C# and this port are testing the same rule.

## Indicators

**TA-Lib's EMA does not match NT8's.** TA-Lib seeds with an SMA of the first `period`
values and emits nothing before index `period-1`; NT8 seeds from the raw price at bar 0:

```csharp
Value[0] = CurrentBar == 0 ? Input[0]
         : Input[0] * (2/(1+Period)) + (1 - 2/(1+Period)) * Value[1]
```

For `EMA(3)` over `0..9`, TA-Lib returns exactly 8.0 and NT8 returns 8.001953125. Since
`Close[0] > ema[0]` is a hard entry gate, that changes which bars signal. NT8's SMA
likewise averages a *partial* window before `period` bars where TA-Lib returns NaN. Both
are hand-rolled in `indicators.py`. TA-Lib remains in use for MACD and RSI, which no
archetype reads yet and which carry the same unpinned discrepancy.

### M16 — ATR, StdDev, Bollinger and Keltner, read out of NT8

Pinned by `ninjatrader-scripts/Strategies/NqbtIndicatorProbe.cs`, which places no orders and
dumps NT8's own values at G17. Source: **MNQ 03-24, 1-minute, 89,330 bars from bar 0**.
Every series below agrees with `indicators.py` on **all 89,330 bars** at `rtol=1e-11` —
under 2e-7 of a point against a 0.25 tick, so no gate can move. Bit-exact agreement is not
achievable through a float recursion and is not the standard; True Range, which accumulates
nothing, *is* exact on every bar.

**True Range** is `max(H−L, |H−prevC|, |L−prevC|)`, and the bare `H−L` at bar 0. Exact on
89,330/89,330. Read directly out of `ATR(1)`, since the Wilder recursion at period 1 reduces
to TR itself and NT8 exposes no TR indicator.

**ATR seeds with an expanding simple average, then switches to Wilder.** Emits from bar 0.
While `CurrentBar < period` the value is the simple average of every TR so far; from
`period` on it is `(prior×(period−1) + TR) / period`. This is the **same class of defect as
the EMA — seeding, not formula** — and it is the one M16 predicted. It is not a rounding
difference: at bar 1 with period 14, seeding Wilder from bar 0 instead differs by over 4
points on this data, and the recursion never forgets its seed.

| candidate | bars matching of 89,330 |
|---|---|
| expanding-SMA seed, then Wilder | **89,330** |
| pure Wilder from `TR[0]` | 89,020 |
| rolling SMA of TR | 20 |

**StdDev uses the population divisor and an expanding partial window.** Divisor is the
sample count, never `n−1`; before `period` bars exist it uses everything so far, exactly as
`nt8_sma` does. `StdDev[0]` is 0.

It must be computed **two-pass**, subtracting the window mean explicitly. An incremental
sum-of-squares update is algebraically identical and numerically is not: pandas'
`rolling(...).std(ddof=0)` differs from NT8 by up to **4.2e-07** over this window. Far below
a tick, but not the exact agreement a pin exists to establish.

**Bollinger is the SMA plus that same StdDev.** Midline equals `nt8_sma` exactly on all
89,330 bars; upper and lower are `midline ± k × StdDev` exactly on all 89,330.

**Keltner matches neither half of the common definition**, which is why M16 flagged it as
the one most likely to be silently wrong:

- The midline is an **SMA of typical price** `(H+L+C)/3` — matched 89,330/89,330. An SMA of
  close matched 354, an EMA of typical price matched 1, an EMA of close matched 0.
- The width is `offset ×` the **mean high−low range**, *not* ATR. `(upper − midline) / 1.5`
  matched `SMA(H−L, 20)` on 89,330/89,330 and matched `ATR(20)` on **20**.

The two quantities both average a per-bar measure of movement, so a wrong one looks
plausible on a chart; they part company whenever a gap makes True Range exceed the bare
range. `tests/test_indicators_nt8_parity.py` pins both halves against the export, including
the negative assertions.

**True Range does not reset at a session boundary** (#23's measurement half). It reads the
previous bar's close across the 17:00–18:00 ET maintenance break like any other bar. On
**27 of the 65 session opens** in this window the overnight gap makes TR exceed `H−L`, so
this is a material choice rather than a formality — the first is 2023-12-07 23:01, where
`H−L` is 11.50 and TR is 12.50. It does not reset at a roll boundary either — see below.

**VWAP** is hand-rolled session-anchored `Σ(typical × volume) / Σ(volume)`, reset at each
18:00 ET open. `OrderFlowVWAP` at `VWAPResolution.Standard` works from bar data, so minute
bars are the right input — tick data would *reduce* agreement.

### WMA and HMA, ported from the NinjaScript rather than reconciled (#72)

**These two are pinned against `@WMA.cs` and `@HMA.cs` themselves, not against an NT8 export.** Every other indicator here was read out of NinjaTrader by `NqbtIndicatorProbe.cs`; these were not, because the probe predates them. The prime directive still binds — the C# is the ground truth and it is transcribed literally — but the evidence is a class weaker than the M16 series above, and that is why `MA_KINDS` records where each came from rather than claiming an agreement rate. An archetype that switches a gate onto one of them has not been reconciled at that setting.

**WMA weights `1..k` with the heaviest on the newest bar, over an expanding window.** It emits from bar 0 exactly as `nt8_sma` does: at bar *i* the window is `min(period, i+1)` bars and the divisor is that window's triangular number, so the warm-up is a shorter WMA rather than a null.

**`@WMA.cs` has two branches and `indicators.nt8_wma` implements the one minute bars take.** Where the bar type supports `RemoveLastBar` — which time-based bars do — NT8 rebuilds the weighted sum from scratch every bar; otherwise it carries `wsum` and `sum` forward and updates them. The two are algebraically identical and numerically are not, and this is **the same choice `nt8_stddev` already faced**: the accumulating form drifts, the rebuilt one is exact, and the exact one is also what NT8 runs here. `tests/test_indicators.py::test_nt8_wma_matches_the_recursive_form_of_the_same_sum` pins that they agree, so the branch is a decision rather than an assumption.

**The cost of rebuilding is real but small**, and it is the reason the choice is recorded rather than hidden: over the 1,663,489-bar MNQ continuous series, `nt8_wma` runs 0.025 s at period 21 and 0.220 s at period 200, against 0.003 s and 0.004 s for `nt8_ema`, which is `O(n)` at any period. `nt8_hma` is roughly 1.5× its WMA — 0.052 s and 0.356 s — because it is three of them. Re-measure rather than quoting these; they are one machine's.

**HMA is NT8's composition of three WMAs and both inner lengths truncate.** `WMA(2·WMA(period/2) − WMA(period), (int)sqrt(period))`, where `period/2` is C# integer division and the square root is cast, not rounded — so period 14 is `WMA(7)`, `WMA(14)` and an outer `WMA(3)`. NT8 caps the period with `Range(2, int.MaxValue)` and `nt8_hma` refuses 1 for the same reason: its inner `WMA(0)` has nothing to average.

**VWMA is deliberately absent, and it is the one that needs a probe.** It reads volume as well as price, and the obstacle there is the shape of `MovingAverageKind.compute` — `(values, period)`, a single series — rather than the data, which `prepare` already pulls out of `bars["volume"]` for the session VWAP. What actually needs NinjaTrader is that `@VWMA.cs`'s two branches genuinely disagree during warm-up rather than merely rounding differently: the `RemoveLastBar` branch sums `min(CurrentBar, Period)` bars and returns `0` at bar 0, the other sums `CurrentBar + 1` and returns `Input[0]`. Choosing between them from the C# alone is guessing, and a wrong warm-up is exactly the seeding class of defect the EMA and the ATR were both caught by.

### True Range at a roll boundary (#23)

**Nothing is special-cased at a roll, and the reason is stronger than "NT8 would not either".**
A seam bar reads the previous bar's close like any other, and on a back-adjusted series that
previous close carries **no contract basis at all**.

**Back-adjustment removes the basis exactly, not approximately.** The shift comes from
`front_close − back_close` at the last bar the front contract contributes, which is precisely
the bar a seam reads back to, so the two cancel. Measured over both cached back-adjusted series
with `splice.roll_seams`: the seam carry-over equals the *back contract's own* close-to-open
move over the same interval to the last bit, on **all 36 seams** — 18 rolls in each root.
`tests/test_splice.py::test_back_adjustment_leaves_no_contract_basis_at_the_seam` pins it
against a basis that widens across the overlap, so an offset read off any other bar fails it.

**So the step measures the break the seam sits across, not the roll.** `roll_seams` reports
that break as `gap_minutes`, and it falls in three populations:

| `gap_minutes` | what the seam spans | carry-over |
|---|---|---|
| 61 | the 17:00–18:00 ET maintenance break alone | a few points |
| ~1,320–1,380 | a session the front contract's archive does not hold | up to several hundred |
| ~2,880–2,940 | a weekend | tens to a few hundred |

The middle row is the larger population today and it is **not a market event**: it is the known
cost of correct roll dates (`.claude/rules/data-pipeline.md`, "Correct roll dates cost bars").
The front contract owns its last session but holds only the first hour of it, so the seam
carries a whole session's move in one bar. That is a data-coverage gap wearing a roll's
clothing, and filling it from the neighbouring contract would splice two different prices into
one session.

**What it costs ATR.** Wilder at period *n* decays a single TR spike by `(n−1)/n` per bar, so at
the default 14 a seam is still 10% of its initial excess 32 bars later and 1% of it 63 bars
later — the recursion never forgets, exactly as with the seed. Run `roll_seams` for the current
sizes rather than quoting a figure from here; on the series as it stands, ATR(14) at a seam runs
several times its value on the bar before.

Two standing consequences:

- **Do not read the step as a volatility event.** A regime, squeeze or trigger rule reading ATR
  will fire around every roll for a reason that has nothing to do with the market.
- **Judge an ATR-sensitive rule per contract** (`dispersion.py`, #31). A front-month window runs
  roll day to roll day, so it contains no seam — which is the same property that makes it
  directly reproducible in Strategy Analyzer.

## Sessions

CME US Index Futures ETH: 18:00 → 17:00 ET, 17:00–18:00 maintenance break, Sunday evening
through Friday afternoon. A session is labelled by the date it **ends** on.

Validated against the data: median **1380 bars/session** (exactly 23 hours); 65 of 66
sessions open at 18:01 ET and 63 close at 17:00 ET. The outliers are real CME holiday
early closes (MLK, Presidents' Day) and the export's truncated first and last sessions.
Both kinds end before the template says they should, and the flatten follows the bars rather
than the template — "The session end is the observed last bar, not the template's".

No session ever spans a DST transition — US transitions happen 02:00 Sunday and the market
is closed Friday 17:00 → Sunday 18:00 — so naive wall-clock arithmetic inside a session is
exact.

Exports also contain stray prints outside session hours (isolated volume-1 bars on
Saturdays) — 47 of MNQ 03-24's 132,454 bars, and 0.086% on the worst of the 38 contracts
cached when #160 landed. NT8 building bars against an ETH template never forms these, so
they are tagged
`in_session=False` in the Parquet cache, which stays lossless, and `ingest.load_contract` drops
them on the way out. A per-contract frame and a spliced one are therefore the same bar set,
which they were not before #160: `context.prepare` computed over every row it was handed while
`build_continuous` filtered first, so a stray at a session open became `[1]` and shifted every
`[n]` behind it. What that was worth is in "Reconciliation result — InsideBar".

**A large share is a broken export, not strays, and is refused rather than filtered.**
`ingest.STRAY_SHARE_LIMIT` is the line; above it `load_contract` raises, because a file where
the count is not a rounding error is saying the export or the session template is wrong, and
quietly filtering it would hide that.

**NT8's trade-list export is in the machine's display timezone, not UTC.** This corrects an
earlier claim here, and the earlier evidence contains the reason it was wrong: the
entry-time histogram showed an empty 22:00 hour, which is the 17:00–18:00 ET break *in
winter*. The original window (MNQ 03-24, December–March) sits entirely in GMT, where
`Europe/London` and UTC coincide, so a display-zone export was indistinguishable from a UTC
one.

The MNQ 06-24 reconciliation spans 31 March 2024 and settles it. Parsing as UTC joined
**332 of 1,800 legs**; parsing as `Europe/London` joined **1,792 of 1,792**. The shift is
exactly 0 hours before 31 March and exactly +1 after — BST, not a data problem.

So a reconciliation over any summer window fails mysteriously unless the export is read in
the display zone. `tools/reconcile_nt8.py` does, via `EXPORT_TZ`, and it is stated
explicitly rather than inferred because a wrong zone shifts every trade by a whole hour and
still parses cleanly. Bar timestamps in `data/archive/` are unaffected — those are converted
to UTC at export by the AddOn, which already handled both DST traps.

### Session phases are ours, not NT8's (#43)

`nqbt/timeofday.py`'s seven phases have **no NinjaScript counterpart and need none** — they
label bars for stratification, they are not a fill rule, and nothing about them can move a
trade. The one place they touch a reconciled archetype is `phase_filter`, an entry filter
absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`, listed here so it is on the
record beside the other options the C# does not implement.

It defaults to `ALL_PHASES` and each archetype's signal **skips it entirely** at that value,
so the reconciled configurations are untouched: all 12 captured trade logs are byte-identical
across the change, `sha256` included. Switch it on and the run is no longer the run the trade
list was diffed against — which is fine for research and is not a Tier-2 claim.

The boundaries themselves (03:00 London, 09:30 cash open, 16:00 close) are market facts in
Eastern time, not readings out of NT8, and are recorded in `docs/roadmap.md` § M10.4.

### So are the regime labels (#40)

`nqbt/regime.py` is the same shape of thing and carries the same status. Kaufman's efficiency
ratio has no NinjaScript counterpart, is not a fill rule, and cannot move a trade; `regime_filter`
is the one place it touches a reconciled archetype, and like `phase_filter` it is absent from
both `DeadCatBounce.cs` and `PullBackAndGo.cs`. Listed here so it is on the record beside the
other options the C# does not implement.

It defaults to `ALL_REGIMES` and each signal **skips it entirely** at that value, so all 12
captured trade logs are byte-identical across the change, `sha256` included. There is a second
reason the skip has to be no call rather than a no-op mask: the ratio's warm-up bars are
`UNDEFINED` and pass nothing, `ALL_REGIMES` included. The thresholds and the warm-up decision
are in `docs/roadmap.md` § M10.1.

### So are the volume labels (#41)

`nqbt/volume.py` is the third of the same shape and carries the same status. Relative volume has
no NinjaScript counterpart, is not a fill rule, and cannot move a trade; `volume_filter` is the
one place it touches a reconciled archetype, and like `phase_filter` and `regime_filter` it is
absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`.

It defaults to `ALL_STATES` and each signal **skips it entirely** at that value, so all 12
captured trade logs are byte-identical across the change, `sha256` included. The skip has to be
no call rather than a no-op mask for the same reason it does under `regime_filter`: the first
sessions have no baseline, so their bars are `UNDEFINED` and pass nothing, `ALL_STATES`
included.

**The one NT8-shaped question here is what counts as volume**, and the answer is the same
`sessions.classify` uses everywhere: an out-of-session print is not a bar NT8 would have formed
against an ETH template, so it reads zero in all three forms rather than being counted. Everything
else about the labels — the bar-of-session baseline, the three forms, the thresholds — is a
research choice with no NT8 counterpart, and is recorded in `docs/roadmap.md` § M10.2.

### So is the trend label (#42)

`nqbt/trend.py` is the fourth of the same shape and carries the same status. The compact trend
label has no NinjaScript counterpart, is not a fill rule, and cannot move a trade;
`trend_filter` is the one place it touches a reconciled archetype, and like the three filters
above it is absent from both `DeadCatBounce.cs` and `PullBackAndGo.cs`.

It defaults to `ALL_TRENDS` and each signal **skips it entirely** at that value, so 12 of the
14 captured files are byte-identical across the change, `sha256` included, the two that move
being the sweep summary tables gaining the five parameter columns. The skip has to be no call
rather than a no-op mask for the same reason it does under `regime_filter` and `volume_filter`:
a bar whose slope cannot yet be measured is `UNDEFINED` and passes nothing, `ALL_TRENDS`
included.

**The one thing here that is an NT8 question is the averages**, and it is answered by reuse:
the label reads `nqbt.conditions.moving_average_grid`, so its EMAs are `indicators.nt8_ema` and
carry whatever parity the gates carry rather than a second definition. Everything else — the
three components, the agreement score, the thresholds — is a research choice with no NT8
counterpart, and is recorded in `docs/roadmap.md` § M10.3.

### And so is the higher-timeframe average (#73)

`nqbt/higher_timeframe.py` is the fifth of the same shape and carries the same status. A moving
average computed on resampled bars has no NinjaScript counterpart *here*, is not a fill rule,
and cannot move a trade; `higher_timeframe_filter` is the one place it touches a reconciled
archetype, and like the four filters above it is absent from both `DeadCatBounce.cs` and
`PullBackAndGo.cs`.

It defaults to `ALL_SIDES` and each signal **skips it entirely** at that value, so 12 of the 14
captured files are byte-identical across the change, `sha256` included, the two that move being
the sweep summary tables gaining the three parameter columns. The skip has to be no call rather
than a no-op mask for the reason it does under the other three: a bar before the first coarse
bar has closed is `UNDEFINED` and passes nothing, `ALL_SIDES` included.

**Unlike the four above, this one has an NT8-shaped question — and a trade list is the wrong
instrument for it.** NinjaScript expresses the same gate as an `EMA` of period 50 over a
`Closes[1]` added with `AddDataSeries`, tested against `Close[0]`, and *when* that secondary
series updates relative to a same-stamped primary bar is a property of NT8's event ordering,
not of the arithmetic. The rule implemented here is that a coarse bar is readable from the fine
bar closing alongside it and from none before it.

**For an EMA the two readings cannot be told apart by any trade list, and that is algebra
rather than a measurement.** The update moves the average toward the close and never past it,
so `close − EMA_new = (1 − α)(close − EMA_prev)` with `α = 2/(period+1)` keeps the sign, and the
gate therefore never flips. Measured over 914,700 MNQ bars at 5/15/60 minutes × periods
3/20/50, the label differs on exactly one bar in every configuration and that one is the first
coarse close, where the lagged reading is still in warm-up; where both are defined the
disagreement count is zero. A reconciliation would return 100% and settle nothing.

**An SMA is a different matter, which is what makes this worth recording rather than closing.**
An SMA drops the oldest value out of its window and *can* move past the close, so the boundary
is observable there — 842 differing bars at 15-minute SMA(20) over the same data. [#72] made
the *fine* gates' kind sweepable and left this series fixed at EMA, so the day
`HigherTimeframeKey` gains a kind of its own, a trade list becomes a valid instrument.

**Reconciled ([#183]).** `NqbtHigherTimeframeProbe.cs` was run in Strategy Analyzer over
`MNQ 03-24` with a 60-minute secondary series: 1,479,760 1-minute bars from 2020-01-01 to
2024-03-15, and 24,826 coarse bars. `tools/reconcile_higher_timeframe.py` compares it. All four
questions are answered, and three of them exactly:

| question | result |
|---|---|
| projection | **0 of 1,479,701** bars differ. On all **24,752** coarse closes NT8 reads the coarse bar stamped alongside the fine bar |
| seeding | **0 differ** on EMA(3), EMA(50), SMA(3) and SMA(50) over 24,752 coarse closes |
| warm-up | **59 against 59** leading bars unreadable |
| anchoring | exact over the **1,525** coarse bars of the front-month window; the prefix is NT8's merged series, below |
| the gate itself | **0 of 1,479,760** bars differ, composing NT8's own close against NT8's own coarse EMA into a side and comparing it with `higher_timeframe_labels` |

**The projection result settles the boundary for every moving-average kind at once, which is
why the probe was worth building rather than a trading script.** It compares *which bar* NT8
reads, not what the average computed to, so it does not depend on the arithmetic being
monotone — the SMA case that a trade list would have been needed for is answered by the same
column. `higher_timeframe.project`'s `side="right"` is NinjaTrader's own rule.

**The anchoring prefix is NT8's merge policy, not a bucketing difference.** Asked for four
years of a contract that has about six months of its own history, NinjaTrader serves its merged
series for the rest. Agreement is exact from **2023-12-08 23:00** onward — 1,525 coarse bars,
zero differences on open, high, low, close and volume — and before that the archive holds one
to four contracts an hour against NT8's thousands, which is the back-month contract against a
merged front month. The changeover bucket at 2023-12-08 22:00 agrees on open and close and
differs on high, low and volume, being the one bucket straddling the handover. This is the
trap `reconcile_nt8.py` documents, met again; `settled_from` in the comparison tool names the
changeover so a merged prefix cannot read as a defect.

**The gate is checked as a whole and not only in its parts.** Composing NinjaTrader's own
`Close[0]` against its own 50-period EMA of `Closes[1]` into a side reproduces
`higher_timeframe_labels` on every one of 1,479,760 bars: 628,106 `BELOW`, 851,589 `ABOVE`, 59
`UNDEFINED`, and the 6 `AT` bars where the close falls exactly on the average — NinjaTrader
lands on the same six. The boolean a sweep applies agrees bar for bar at both `BELOW` and
`ABOVE`.

**A leg-for-leg trade-list diff would add nothing here, and is deliberately not planned.** What
it would exercise beyond the above is the conjunction in `sim/filters.py` and the bracket, and
those are shared unchanged with `phase_filter`, `regime_filter`, `volume_filter` and
`trend_filter` on archetypes that are already reconciled; the trade-log gate showed 12 of 14
files byte-identical across this change. Getting one would mean writing a NinjaScript archetype
with a secondary series purely to produce it, which is the NinjaTrader time `CONTRIBUTING.md`
reserves for candidates worth trading.

Everything else — that the side is a three-state label, that equality gets its own state, that
the kind is fixed at EMA — is a research choice with no NT8 counterpart, and is recorded in
`docs/roadmap.md` § "Multi-timeframe moving averages".

## Contract data

**Exports are moving windows, not snapshots.** NinjaTrader serves each contract for a limited
period and drops the tail once it expires, so a folder of exports silently loses history over
time. `data/archive/` accumulates instead and is the only thing ingestion reads, which is what
makes "keep the current history and use the AddOn from here" a workable plan rather than a slow
erasure. `SOURCE_DIRS` merges the manual export first and the AddOn second, because the AddOn
reads the provider's settled archive while a manual export is live tick aggregation plus
whatever NinjaTrader happened to hold locally.

**A manual Tools → Historical Data export returns ~95 days per contract**, regardless of
the range requested, ending ~4 days before expiry. On that data alone the volume crossover
falls at or after the point coverage stops, so measured bar-aligned across all 18 roll
pairs the back contract never overtook the front, and every roll fell back to the coverage
handover (`METHOD_COVERAGE`).

**That is a limit of the export, not of NinjaTrader.** Pulling bars through `BarsRequest`
(`ninjatrader-scripts/AddOns/NqbtHistoricalExporter.cs`) returns three to six months more
per contract — thin, because a deferred contract barely trades, but enough to see the back
contract's liquidity ramp. It also warms NinjaTrader's own local database, after which a
manual re-export returns the union: MNQ 06-26 went from ending 2026-06-11 to running
through 2026-06-18, its expiry week.

Re-exporting every contract after the AddOn had run returned the full contract life —
roughly six months out through to expiry, against ~95 days before. With that merged into
`data/archive/`, **all 18 MNQ rolls and all 18 NQ rolls now detect a genuine volume
crossover** and none falls back to the coverage boundary. Handover ratios run 1.26–4.35
(MNQ) and 1.17–4.75 (NQ), and every roll in both roots is decided on a session of at least
1,251 shared bars.

The NQ re-export also added six contracts the archive had never held — 03-22 through 12-22
and 09-26 — taking the archive from 33 contracts to 38 and from 4,090,398 bars to
4,601,503. NQ's continuous series grew from 1,258,980 bars to 1,633,461 and now starts
2021-12-05 rather than 2022-10-09.

**The two roots corroborate each other, and that caught a bug.** Run side by side, 17 of 18
roll dates agreed exactly. The one that did not — MNQ 03-23 → 06-23 on 2023-03-13 against
NQ's 2023-03-14 — turned out to be decided on a 120-bar stub where MNQ read 1.46 and NQ read
0.68. Neither figure is a session verdict; they are two hours of overnight trade. The
crossover test now skips a session with too few shared bars to be conclusive rather than
letting it decide (`conclusive` in `overlap_volume`), which moved that one roll to
2023-03-14 and left the other 35 in both roots untouched.

**Correcting the roll dates costs bars, and that is the right trade.** Rolling at the true
crossover means the front contract supplies the days a coverage-boundary roll used to hand
to the back contract — and NT8's per-contract data has holes there. MNQ 03-22 holds 60 bars
on 2022-03-10 between full sessions either side, so the continuous series now shows those
near-empty sessions rather than papering over them with the wrong contract. The gaps are
real and were always there; they are simply no longer hidden. Filling them from the back
contract would splice two different prices into one session — the offset across this roll is
8.75 points — so they stay visible instead.

**The hole is systematic, and it is the same hole in both roots.** Two or three days before
most rolls, a contract holds only the Sunday-evening 18:00–19:00 ET hour for a whole trading
day and then resumes normally. NQ 12-25 has 1,380 bars on 2025-12-12, 60 on 2025-12-15, and
1,314 on 2025-12-16. Across the spliced series that leaves 18 thin sessions in NQ (1,779
bars) and 19 in MNQ outside its early low-liquidity listing period. This is exactly where
the crossover gets decided, which is why the conclusiveness guard above matters more than
its size suggests.

MNQ 06-26 → 09-26 is the clearest example of the crossover itself:

| trading day | front 06-26 | back 09-26 | ratio | shared bars |
|---|---|---|---|---|
| 2026-06-11 | 3,659,192 | 52,989 | 0.014 | 1,359 |
| 2026-06-12 | 2,520,399 | 519,731 | 0.206 | 1,380 |
| **2026-06-15** | 596,993 | **1,721,764** | **2.88** | 1,380 |
| 2026-06-16 | 394,080 | 2,775,306 | 7.04 | 1,380 |

The roll moves from 2026-06-12 to 2026-06-15 — the coverage boundary was three days early.

**Handover ratios must be read against `shared_bars`.** This same roll previously reported
0.27 and was flagged as premature for weeks. That figure came from a 60-bar stub, not a
session; the four full days before it sat at 0.9–1.4%. The stub was not evidence of an
imminent roll, and it was not evidence against one either — it was 4% of a session. That
lesson is now enforced in code rather than left to whoever reads the diagnostic table.

**Volume comparison must be bar-aligned, not calendar-aligned.** Comparing whole-day volume
compares a truncated session against a full one and manufactures a crossover that isn't
there; this produced a false "crossover on 2024-03-11" early in development.

Back-adjustment offsets are economically sound as a sanity check: −204 to −296 points in
2024–2026, and +2.00 / −31.50 / −75.00 across 2022, tracking the Fed hiking cycle. The
residual jump at each roll equals the back contract's own move across the weekend gap
exactly — real market movement, correctly preserved.
