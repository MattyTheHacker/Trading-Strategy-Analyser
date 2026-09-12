---
id: M34
title: "M34 — EmaPullback: the pullback to the fast average, with the stop on the slow one"
archetypes: [EmaPullback]
issues: [309]
gates: []
outcome: spec
verdict: >-
  The two averages EmaCrossover already builds, read for the trend they leave behind rather than for the cross; the entry is a touch of the fast average after an extension away from it and the stop is the slow average itself, which makes R structural for the first time in an original.
---

# M34 — EmaPullback: the pullback to the fast average, with the stop on the slow one ([#309])

**Nothing here is a measurement.** This is the design, written before the Python and then built to, in the order [§M26](m26-elastic-band.md) established and §M18 could not manage. The rules and the NinjaScript each would be written as are in [`nt8-fidelity.md`](../nt8-fidelity.md) §M34; this file is the reasoning and the alternatives rejected.

## The rule

Long, and the short side is the same rule with one sign multiplier:

1. the fast average is above the slow one;
2. price has spent `min_bars_extended` completed bars **entirely** above the fast average — every low above it;
3. this bar's low reaches the fast average;
4. this bar closes above the slow average, and — `require_slow_intact` — has not traded through it either;
5. enter at market on the next bar's open, with the protective stop at **the slow average as it stood on the signal bar**, `stop_offset_ticks` beyond it.

Targets are the usual four-leg ladder in R. There is no ATR anywhere in the archetype.

## Why a new archetype rather than a mode on EmaCrossover

The two share their parameters almost exactly and share the simulation loop outright, so the question is real. Three things settle it against a mode:

**The archetype name is the unit every measurement is keyed on.** `strategy` is a results column, the matched random-entry null is drawn per archetype, and the gates are reported per archetype. Two entry mechanisms under one name pool into one row group, and no later query can separate them.

**EmaCrossover has a job that pooling would destroy.** It is the registry's deliberate known-negative control — "if it reads meaningfully better than the random-entry arm, the first hypothesis is lookahead". A control that is half a different strategy is not a control.

**An axis nothing reads is a hazard here rather than an inconvenience.** Inheriting `EmaCrossoverParams` would carry `cross_lookback`, four ATR fields, `swing_lookback`, the two round-number fields and `confluence_required` into a class that reads none of them, and `sweepable` reads `dataclasses.fields()`, so every one stays a legal axis producing identical rows. `dead_axes` compares one toggle per axis and would report nothing. The params class is therefore written out rather than inherited, which is what the other five originals and ports already do.

**What is shared is shared for real.** `simulate_crossover` is not forked: it was already a market-on-next-open loop with a per-bar direction, an R-multiple leg bracket and an optional moving-average trail, which is the whole of this archetype's mechanism. The one thing it lacked is a stop placed on a level it is handed, added as a third mode beside the ATR and swing ones. That is `PullBackAndGo` reusing `simulate_deadcat`, one archetype later.

## The four choices the entry makes

### The extension is a run of bars, not a distance

The alternative is a distance — "price is at least *k* ATRs, or *k* standard deviations, above the average". That is [ElasticBand](m26-elastic-band.md)'s coordinate system, and ElasticBand exists; building a second archetype on it would be measuring the band again with a different name on it. A run of bars asks the other question: not how far price went, but how long it stayed there. It also needs no indicator at all — the count is a bar counter, which is the cheapest thing NT8 can express.

**A bar counts as extended only if its whole range is beyond the average**, low above it for a long. A close-based definition would count a bar that traded through the average and closed back above it as extension, and that bar *is* a pullback — the archetype would then be arming on the event it exists to trade.

**The touch bar ends the run**, which is what makes `min_bars_extended` also read as "how long since the last touch". The consequence is deliberate and worth stating: a signal that is filtered out — by a context filter, by the touch mode, by the trend-intact test — still ends the run, so the next touch needs a fresh extension behind it. A chop of repeated touches produces at most one signal per genuine extension rather than one per bar.

### The touch is the low against the average, not a close through it

A wick to the average is the shallow reading and a close through it is the deep one, and there is no argument in the literature that settles which is the pullback. So both are axis values rather than a decision: `TOUCH_WICK` asks the bar to close back beyond the average it reached, `TOUCH_CLOSE` asks it to close through, `TOUCH_ANY` takes either. **A close exactly on the average is a close through it** — one sign multiplier means the long and short arms have to be the same rule, which is the boundary [§M26.5](m26-5-signal-bar-shape.md) already settled for the doji.

The three modes are an axis rather than a variant dimension because **every mode reads every other axis**: none of them makes `min_bars_extended`, `require_slow_intact` or the stop offset inert, so `dead_axes` has nothing to miss. That is the opposite of ElasticBand's shapes and of OpeningRange's stop modes, both of which had to become variants for exactly that reason.

**How much rarer the deep mode is depends on the bar size rather than being a constant** — a bar that closes through the average is a far larger move at thirty minutes than at one, so the three modes are not three depths of one measurement and the gap between their trade counts widens with the resolution. Read the count per mode per resolution before comparing profit factors across them.

### The trend-intact test is the close, and the stop level is the low

Two separate requirements, and they are separate because they fail differently. The close beyond the slow average is unconditional: a bar that closed through the level the stop is about to sit on is a bar whose trade is already wrong. `require_slow_intact` adds the harder one — the bar has not so much as *traded* through it — and is an axis because it is the difference between a stop at a level the market has just rejected and a stop at a level the market has just reached. Off is not obviously worse; it is a wider entry with a stop the signal bar already touched.

### There is no confirmation entry

The obvious fifth choice — rest a stop order above the touch bar's high and enter only if the trend resumes — is deliberately absent. It is a different entry mechanism (a resting stop order with a trigger price, a submittability rule and a one-bar lifetime), which means a different null and a different set of fill semantics; folding it in as a mode would make the archetype two archetypes wearing one name, which is the thing this file has already argued against once. It is the natural second campaign, not part of the first.

## The stop, and the two precedents that disagree about the offset

**The stop is the slow average at the signal bar**, never the fill bar's. Every other read in the archetype is from the signal bar and this is the one that matters most: the average moves, and reading the bar the fill happens on would place a stop against information the order did not have.

**It takes no dollar floor.** [§M18](../nt8-fidelity.md) floors the ATR stop because a quiet regime otherwise sizes a bracket smaller than the round trip costs, and does not floor the swing stop because a structural level is not a distance. An average is a level, so the same reading applies. What replaces the floor is the minimum-risk refusal that already exists: a stop within one tick of the fill is not a stop order and the entry is skipped.

**The tick offset is the one place two precedents in this repository disagree**, and it is worth recording rather than quietly picking one:

| precedent                                                                                       | offset    | reasoning                                                                                            |
| ----------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------- |
| [§M26.8](m26-8-stop-on-band.md)'s band stop                                                     | none      | `stop_offset_ticks` exists for levels the market traded at, and a band is a statistic about the bars |
| EmaCrossover's moving-average trail ([§ the build spec's loose ends](build-spec-loose-ends.md)) | two ticks | so the stop is not sitting exactly on the level it follows                                           |

A moving average is a statistic by the first reading and a level by the second. This archetype takes the offset, because a well-watched average is repeatedly touched and a stop exactly on it is taken out by a touch that respected the level — and because the disagreement is settled by sweeping rather than by argument: `stop_offset_ticks = 0` reproduces the band stop's reading exactly, and it is an axis.

**Round-number avoidance is not carried over.** It would need the `PriceBasis.RAW` refusal alongside it, and a stop on a continuously-varying average lands exactly on a round number only by coincidence. Two axes that would be inert almost everywhere are worse than an absent feature.

## What R means here, and what it is not comparable to

R is the distance from the fill to the slow average, so it is **structural** — the gap between two averages, which widens with trend strength and collapses when they converge. That is the first original archetype whose R is neither volatility-scaled (EmaCrossover's ATR stop) nor a fixed geometry.

Two consequences for reading any result: **the target ladder's numbers are not comparable to any other archetype's at the same values**, which is the same trap as comparing profit factor across bar resolutions; and R varies far more trade to trade than an ATR stop's does, because two averages converging is a routine state and a collapsed ATR is not. A campaign should read the distribution of `risk_points`, not just its mean.

## The expressibility checklist

Run against the design before it was built, per [`roadmap.md`](../roadmap.md) § "Standing constraint, extended":

| question                                             | answer for EmaPullback                                                                         |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| How long must an entry order rest?                   | Not at all — the entry is a market order at the next bar's open                                |
| Does it need a true OCO pair?                        | No. The trend picks the side, and only one side can be in trend                                |
| Does it need to reverse directly from long to short? | No. Flat between trades, like every other archetype here                                       |
| Does it hold through the session close?              | No, and it must not — the hold is bounded by the session like everything else                  |
| Does it need more than 4 entries per direction?      | No. One position at a time                                                                     |
| Does it need an indicator NT8 computes differently?  | Yes, and it is already pinned — `indicators.nt8_ema`, exact against the M16 probe on every bar |

Nothing on the list bites. The archetype is expressible in the managed approach with `SetStopLoss`, `SetProfitTarget` and an `int` counter, which is the cheapest shape a port can have.

## What the first campaign has to answer, and what it must not be read as

The archetype is registered, swept and reconcilable, and **that is all it is**. `Tier2Status` is `TIER1_ONLY` and stays there until a Strategy Analyzer trade list has been diffed against it. It has passed no gate, because it has been put to none.

Three things the campaign has to get right, each of which cost an earlier one:

- **The signal is not dense**, unlike OpeningRange's — it is an event on a bar rather than a level resting all session — so the matched random-entry null draws normally. Check `draw_freedom` anyway before reading a p-value, because the deep touch mode thins the signal by more than an order of magnitude.
- **`min_bars_extended` interacts with the bar size**, which [§M27](m27-registry-campaign.md) measured as the largest lever on every archetype. Three bars is a different amount of extension at one minute and at thirty, so the axis cannot be read pooled across resolutions.
- **The stop and the entry are not separable by construction here.** The slow average sets the stop *and* half the entry condition, so `slow_period` moves the bracket and the signal at once. An η² table will attribute the whole of that to one axis; the decomposition [§M28.12](m28-12-bracket-decomposition.md) uses is the way to separate them.
