# NT8 fidelity: what the simulation reproduces, and how it was established

Everything here was verified against a real NinjaTrader 8 Strategy Analyzer run — first a
summary, then a full trade-list export of 1,208 leg exits on MNQ 03-24. Several of these
rules are invisible in a summary and only surfaced from the trade list. They are recorded
because rediscovering them is expensive and because getting any one of them wrong shifts
results by more than any parameter does.

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

## Rules the simulation implements

### Entry orders are not GTC

`EnterShortStopMarket` under NT8's **managed** approach is cancelled at the close of the
following bar if unfilled, despite `TimeInForce.Gtc` on the strategy. A signal at the close
of bar `t` places an order live for bar `t+1` only.

Getting this wrong is the difference between an order that rests indefinitely and fills on
an unrelated later bar, and one that gets a single chance.

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

### Targets snap to the tick grid

`RoundToTickSize` in the NinjaScript. A 1.5× multiple of an odd tick count otherwise lands
on a half tick, which no exchange accepts.

### Max risk is in ticks, not dollars

```csharp
if (risk > maxRiskPerTrade * TickSize) return;
```

`MaxRiskPerTrade = 250` means 250 ticks = 62.5 MNQ points, **not** $250. It never binds at
that default — the largest observed risk is 24.25 points.

## Indicators

**TA-Lib's EMA does not match NT8's.** TA-Lib seeds with an SMA of the first `period`
values and emits nothing before index `period-1`; NT8 seeds from the raw price at bar 0:

```
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

**NT8 serves ~95 days per contract**, regardless of the range requested. A 2020–2027
request returned each contract's front-month window and nothing else, ending ~4 days before
expiry, across all 19 MNQ contracts.

Consequence: the volume crossover happens at or after the point coverage stops, so
measured bar-aligned across all 18 roll pairs, the back contract **never** overtakes the
front. This is a provider limit, not an export mistake — re-exporting cannot fix it.

The splicer therefore rolls at the coverage handover (`METHOD_COVERAGE`), which is the same
switch NT8 itself makes, and only warns when the handover volume ratio falls below 0.4 —
meaning the data ran out well before the market actually rolled.

**Volume comparison must be bar-aligned, not calendar-aligned.** Comparing whole-day volume
compares a truncated session against a full one and manufactures a crossover that isn't
there; this produced a false "crossover on 2024-03-11" early in development.

Back-adjustment offsets are economically sound as a sanity check: −204 to −296 points in
2024–2026, and +2.00 / −31.50 / −75.00 across 2022, tracking the Fed hiking cycle. The
residual jump at each roll equals the back contract's own move across the weekend gap
exactly — real market movement, correctly preserved.
