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

### Max risk is in ticks, not dollars

```csharp
if (risk > maxRiskPerTrade * TickSize) return;
```

`MaxRiskPerTrade = 250` means 250 ticks = 62.5 MNQ points, **not** $250. It never binds at
that default — the largest observed risk is 24.25 points.

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
are hand-rolled in `indicators.py`; TA-Lib is reserved for MACD/RSI/BB/ATR, which carry
their own NT8 discrepancies and will need the same treatment when an archetype first
depends on one.

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

**NT8's trade-list export is in UTC.** Confirmed by the entry-time histogram: the 22:00
hour is completely empty, which is the 17:00–18:00 ET break in winter.

## Contract data

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
