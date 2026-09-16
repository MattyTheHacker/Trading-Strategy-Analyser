---
id: M19.2
title: "M19.2 — SqueezeBreakout: a break of the compressed window, one side at a time"
archetypes: [SqueezeBreakout]
issues: [51]
gates: []
outcome: spec
verdict: >-
  The squeeze is the compression filter's own rank cut at one threshold, and the order rests a tick beyond that same window's extreme through OpeningRange's loop; one side per combination, because a two-sided managed entry is still not established as expressible.
---

# M19.2 — SqueezeBreakout: a break of the compressed window, one side at a time ([#51])

**Nothing here is a campaign result.** This is the design, written before the Python and then built to, in the order [§M26](m26-elastic-band.md) and [§M34](m34-ema-pullback-spec.md) established. The rules and the NinjaScript each would be written as are in [`nt8-fidelity.md`](../nt8-fidelity.md) §M19.2; this file is the reasoning and the alternatives rejected. The one table of numbers below is the signal count §M26.5 asks for before an entry gate is crossed with anything.

## What has changed since §M19.1 parked it

[§M19.1](m19-1-compression-condition.md) put compression to seven entries that were not built for it and found it mid-pack as a filter. **It never measured the entry the condition exists for** — a break of the window that compressed — because no such entry existed. "Parked is not abandoned" asks what is new before anything parked is run again: this is a new entry rather than a re-run, and it costs no new fill code, because [§M28.1](m28-1-openingrange-swept.md)'s resting breakout already implements the order.

## The rule

Long, and the short side is the same rule with one sign multiplier:

1. the width of the last `squeeze_period` bars ranks **strictly** below `squeeze_below` of the `squeeze_baseline_bars` widths before it, under either of §M19.1's forms;
2. it has done so for `min_squeeze_bars` consecutive bars, this one included;
3. at this bar's close, rest a stop-market order `entry_offset_ticks` above the highest high of that same window;
4. resubmit it at every close while both hold, re-reading the level each time;
5. the stop and the targets are OpeningRange's, measured against the window: its other extreme, a fraction of its width, or an ATR multiple from the trigger; the R ladder, or multiples of the width.

## Five choices the design makes

### The squeeze is the filter's rule, not a second copy of it

The signal calls `Dataset.compression_gate` for `Compression.COMPRESSED` with the upper cut at 1.0, so `compression._state_of` stays the one place a rank becomes a state. **The squeeze has fields of its own** rather than borrowing the six shared `compression_*` filter fields, for two reasons. Under `ALL_STATES` the filter's axes are gated inert, so the archetype's defining axes would be refused by `dead_axes` at its own default. And keeping the filter separate keeps it usable: a bandwidth squeeze can be filtered on range-to-ATR, which matters because §M19.1 measured the two forms' held-out profit factors correlating at 0.133.

### The level is the window the width was measured over

**`squeeze_period` sets both the width and the levels**, so there is one window and not two. Under `RANGE_TO_ATR` the levels bound exactly the range the rank was taken of; under `BANDWIDTH` they are the high and low of the band's own window. A separate channel length would be an axis whose meaning changes with the form. `compression.rolling_extremes` is now the one definition of that window, `range_to_atr` reads it, and its output was checked byte-identical against the previous implementation over 6.5 million values.

### The order is one bar long and resubmitted, not a resting order

The window rolls, so the level moves whenever a bar enters or leaves it and **the trigger is not unchanged between submissions**. This is therefore not route 3's resting order ([`roadmap.md`](../roadmap.md) § "Route 3"). It is the plain three-argument managed entry re-issued at the window's current extreme on every bar the squeeze holds, which is exactly expressible and needs no `isLiveUntilCancelled` order. The squeeze usually ends on the bar that breaks, because the break widens the window, so the order that fills is the one the last squeezed close placed.

### One side per combination

The squeeze is directionless, and the classic entry rests both stops with the first fill winning. **[§M28](m28-opening-range-spec.md)'s expressibility finding 1 still stands against that**: [#67] measured the managed approach refusing an opposite-direction submission of `isLiveUntilCancelled` orders, and whether two plain opposite stops submitted on one bar are both accepted is still unprobed — the likely answer is that they are not. The simulator has the same limit from its side, one pending slot per loop. So `direction` is an axis and long and short are separate grids, as they are for OpeningRange. A two-sided form stays the open item on [#51], and it would also need an entry-side ambiguity rule NT8 has no answer to: a bar that trades through both levels.

**Resting on whichever side the close is nearer was considered and rejected.** It holds one order at a time, but on the bar the side flips, the previous bar's order is still live through that bar's close — the cancel lands at the start of the next pass ([`nt8-fidelity.md`](../nt8-fidelity.md) § "An order is live through the bar at whose close its cancel is issued") — so the flip submits the opposite-direction order the probe saw refused.

### The squeeze is a rank, never Bollinger inside Keltner

§M19's cost argument against the TTM form is gone, because Keltner is pinned ([#22]). The reason not to build it now is §M19.1's: **the TTM test is a raw threshold** — a band width at a fixed ratio to a channel width — and a raw cut admits a different share of bars at every resolution, which is the failure §M27.5 and §M27.8 recorded. A trailing rank is within five points of its nominal share in every cell §M19.1 measured.

**A latched squeeze — trade only once it releases, from a range frozen at release — is deferred.** It needs a latch and a cancel rule, and the release bar is usually the breaking bar, which the unlatched rule already trades.

## How it runs: OpeningRange's loop, one level row per bar

`simulate_openingrange` reads its level through `session_id`. SqueezeBreakout hands it one row per **bar**, the breakout mode, the per-session cap switched off and no follow-through scaling, so **no fill rule is new and no loop is forked**. The loop's per-session reset then fires on every bar, which is inert with the cap off and no break flag in use. The window's high and low are precomputed once per period in `ContextSpec.window_range_periods`, at sixteen bytes a bar.

The output is sized from the bars that could fill — a squeezed, armed bar followed by a bar reaching its level — rather than from the signal count, which ran seven to eleven times larger across the cells of the table below.

## The expressibility checklist

| question                                             | answer for SqueezeBreakout                                                                                     |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| How long must an entry order rest?                   | One bar, resubmitted at the window's current extreme — the three-argument overload                             |
| Does it need a true OCO pair?                        | Its classic form does, and that is not established as expressible; one side per combination                    |
| Does it need to reverse directly from long to short? | No. Flat between trades                                                                                        |
| Does it hold through the session close?              | No, and it must not                                                                                            |
| Does it need more than 4 entries per direction?      | No. One position at a time                                                                                     |
| Does it need an indicator NT8 computes differently?  | Bollinger and ATR are pinned; `MAX` and `MIN` are a comparison each; the rank is a loop written in NinjaScript |

## Before the campaign: the signal leaves the null room to draw

OpeningRange's unfiltered signal could not be nulled over bars at all. **A squeeze is a state most bars are not in**, so its matched draw has room. Measured on MNQ's continuous series as it stood on 2026-09-16, at the default window and baseline, both forms and both sides, at 1, 5 and 15 minutes:

| `squeeze_below` | share of bars squeezed | spare bars per signal |
| --------------- | ---------------------- | --------------------- |
| 0.05            | 0.06 to 0.08           | 11 to 16              |
| 0.10            | 0.11 to 0.13           | 6.5 to 8.4            |
| 0.25            | 0.25 to 0.28           | 2.5 to 3.0            |

Every cell clears `MIN_DRAW_FREEDOM`. The share runs above its nominal cut, proportionally most at the tightest, because width is autocorrelated and the ranks bunch at the low end. `randomentry.SessionMinutePool.draw_freedom` over `squeeze.squeeze_signal` reproduces it.

**#51 predicts a high ambiguous-bar rate, and at the default bracket it is not one.** Below 2% in every cell above, under the opposite-extreme stop, because a window many bars wide sits further from the trigger than one bar reaches. The ATR stop at a low multiple is where it can bind, so the campaign reads `ambiguous_share` per stop mode rather than this paragraph.

## What the first campaign has to answer, and what it must not be read as

The archetype is registered and has a campaign grid in `VARIANTS["SqueezeBreakout"]`, and **that is all it is**. `Tier2Status` is `TIER1_ONLY` and it has passed no gate. Four things the campaign has to get right:

- **The null is the question, not a formality.** An unconditioned break of an N-bar extreme is a Donchian breakout, and the matched random-entry arm rests the same order on random bars at the same minute of the session. **So gate 3 here reads directly as "does compression add anything to the break"**, which is the whole of #51's question.
- **Squeezes cluster in quiet regimes**, so an aggregate profit factor averages two populations — #51's third trap. Read the per-year and per-contract dispersion before the pooled figure.
- **The baseline is counted in bars, not time.** 250 bars is about four hours at one minute and nearly three sessions at fifteen, so a rank at two resolutions is a rank against two different pasts. Do not pool it across resolutions.
- **Read `session_close_share` first.** §M19.1's strongest-looking cell was the clock rather than the condition, and a runner leg with no target reaches the flatten every time.

[#22]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/22
[#51]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/51
[#67]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/67
