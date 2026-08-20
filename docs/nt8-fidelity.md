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
comparing profit factor across bar resolutions.

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
`H−L` is 11.50 and TR is 12.50. The roll-boundary half of #23 remains a decision, not a
measurement: ATR will step at each roll on a back-adjusted series, and a per-contract run
(`dispersion.py`) is the way to judge an ATR-sensitive rule.

**VWAP** is hand-rolled session-anchored `Σ(typical × volume) / Σ(volume)`, reset at each
18:00 ET open. `OrderFlowVWAP` at `VWAPResolution.Standard` works from bar data, so minute
bars are the right input — tick data would *reduce* agreement.

## Sessions

CME US Index Futures ETH: 18:00 → 17:00 ET, 17:00–18:00 maintenance break, Sunday evening
through Friday afternoon. A session is labelled by the date it **ends** on.

Validated against the data: median **1380 bars/session** (exactly 23 hours); 65 of 66
sessions open at 18:01 ET and 63 close at 17:00 ET. The outliers are real CME holiday
early closes (MLK, Presidents' Day) and the export's truncated first and last sessions.

No session ever spans a DST transition — US transitions happen 02:00 Sunday and the market
is closed Friday 17:00 → Sunday 18:00 — so naive wall-clock arithmetic inside a session is
exact.

Exports also contain stray prints outside session hours (isolated volume-1 bars on
Saturdays). NT8 building bars against an ETH template never forms these, so they are
tagged `in_session=False` at ingest and dropped from the continuous series.

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
