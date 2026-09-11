---
id: M28
title: "M28 — the opening range: what \"ORB\" actually names, and what of it is expressible"
archetypes: [OpeningRange]
issues: [235]
gates: []
outcome: spec
verdict: >-
  Every ORB variant is a point in six axes; the outside evidence establishes less than it appears to, and the expressibility checklist says which of it NT8 can hold.
---

# M28 — the opening range: what "ORB" actually names, and what of it is expressible ([#235])

[#234] opens by saying there is a massive variety of ORB strategies, "some of which are named different things". **That is the finding rather than the problem: the variety is the product of six independent choices, not a list of strategies**, and once the axes are named the count stops being alarming — every folk name in circulation is one point in the same space, and the space is a `Grid`. What follows names the axes, maps the named versions onto them, separates the published evidence from the marketing, runs the expressibility checklist, and ends with the single configuration [#236] should build.

## The six axes every ORB variant is a point in

| axis         | what it decides                                  | values in circulation                                                                                                                                                                                                                             |
| ------------ | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **anchor**   | which clock the range starts on                  | the cash open, 09:30 ET; the ETH session open, 18:00 ET; London, 03:00 ET                                                                                                                                                                         |
| **window**   | how much of it the range measures                | 5, 15, 30 or 60 minutes; the first bar alone; everything before the cash open                                                                                                                                                                     |
| **level**    | what the range *is*                              | the window's high and low; the opening *price* ± an offset; a volatility band around the open or the VWAP                                                                                                                                         |
| **trigger**  | what counts as a break                           | trade through; close beyond; close beyond, then retest and hold; any of those ± an offset in ticks, in ATR, or in a fraction of the range                                                                                                         |
| **side**     | which breaks are taken                           | the first break only; both sides live at once; the break in a direction decided beforehand; the *failed* break, faded                                                                                                                             |
| **geometry** | stop, target, and how long the position may live | stop at the opposite extreme, at the midpoint, at an ATR multiple, at a fraction of the range; target as an R multiple, as a multiple of the range width, at the opposite extreme, at the close, or trailed; one trade a day, or re-entry allowed |

**Anchor and window are separate axes, and conflating them is where most of the naming confusion comes from.** "The 30-minute ORB" and "the initial balance" differ only in window; "the opening range" and FX's "London breakout" differ only in anchor; Crabel's original has a level with *no window at all*. Three arguments about which ORB is meant collapse into three coordinates.

**The sixth axis decides the result and the names never carry it.** Every source agrees on how to draw the range and disagrees on what to do once filled — which is §M26's lesson repeated: the entry rule is one hypothesis, the exit geometry is a second one, and the first does not settle it. Three exit schemes as three grids over one params class is the device that already exists for this.

## The named versions, as coordinates

| name                                                 | anchor | window               | level                                                               | side                                          |
| ---------------------------------------------------- | ------ | -------------------- | ------------------------------------------------------------------- | --------------------------------------------- |
| Crabel's ORB (1990), the original                    | cash   | none                 | the open ± the "stretch"                                            | both, first fill wins                         |
| Fisher's ACD (*The Logical Trader*)                  | cash   | a dwell, not a range | the open ± a fraction of a 30-day ATR                               | both, plus an inner pair for the failed break |
| the retail time-window ORB                           | cash   | 5, 15 or 30 min      | the window's high and low                                           | both                                          |
| the initial-balance break                            | cash   | 60 min               | the window's high and low                                           | both, usually on the retest                   |
| Zarattini, Barbon and Aziz's "5-minute ORB"          | cash   | one bar              | **none — the first bar's *direction***                              | one, chosen by that bar                       |
| the overnight-range break, and FX's London breakout  | ETH    | to the cash open     | the overnight high and low                                          | both                                          |
| the ORB fade                                         | any    | any                  | the same levels                                                     | the failed break only                         |
| the noise-area break (Zarattini's intraday momentum) | cash   | none                 | a band around the open or the VWAP, scaled by recent daily movement | both                                          |

**Two of those are not opening-range breakouts at all, and both are cited as though they were.** The most-quoted academic result — over 1,600% net and a Sharpe of 2.81 — belongs to a rule with **no range in it**: the first 5-minute bar's direction is the signal, entry is the next bar's open, the stop is that bar's opposite extreme, and the target is 10R or the close. The noise-area rule replaces the time window with a volatility band. Anyone comparing "the ORB" against either is comparing against a different strategy.

**The noise-area form is nearly free here, which is worth knowing before [#236] spends its budget.** A band around the session VWAP, scaled by dispersion, traded *in the direction* of the extension is `bands.VwapBand` with ElasticBand's sign flipped — §M26.4 built and swept the band already, and only the sign and the geometry are new.

## What the outside evidence establishes, and what it does not

**Evidence classes, as §M26 set them out**: this project's own reconciled machinery first, `Trading-Docs` second, outside reading **last** — a source of hypotheses for a sweep, never an input to one. The vendor and blog material on ORB is unusually bad even by that standard, and the win rates quoted in it appear with no sample, no window, no costs and no definition of a break. **None of it is evidence and none of it should reach a parameter range.**

What survives:

- **The cross-sectional result does not transfer.** Zarattini, Barbon and Aziz tested opening ranges over more than 7,000 US stocks, 2016-2023; the plain version was weak, and the performance came from selecting, each day, the stocks with abnormal opening volume. **That selection mechanism does not exist for a single futures contract**, and `Trading-Docs` records the point twice already.
- **The single-instrument replication is the relevant one, and it is the discouraging one.** An independent replication of the companion QQQ study reproduced it closely — 1,775 trades against the paper's 1,795, a Sharpe of 1.06 against 1.12 — and then priced it: net P&L crosses zero at roughly 2.2¢ per share of entry slippage, against a spread of about 1¢. Bootstrap Sharpe intervals for the best variant overlapped buy-and-hold's, and 76% of that variant's profit sat in 2022 alone. **What survives costs is per-trade significance in one regime, not a portfolio edge** — and QQQ is the same underlying as NQ, so this is the closest thing to direct evidence the literature offers.
- **A falsification study on this exact instrument reports nothing passing.** Fourteen signal families over 5-minute MNQ OHLCV, 947 trading days from 2021 to 2025, gated on out-of-sample validation, t ≥ 2.0, at least 30 trades, profitability after two points of friction, and consistent yearly performance: none of the tested strategies satisfied all of them. It does not enumerate the fourteen, so it is not specifically an ORB result — but it is the prior to hold about *any* rule built from MNQ OHLCV, and it is the prior §M27 reached from this project's own data.
- **`Trading-Docs` is candid where the vendors are not**, and its verdict is already recorded: opening-range breaks are not high-probability, they are scouting trades, and its own advice to take most of the position at 1:1 **contradicts its own arithmetic** — a 1:1 MNQ bracket needs 60.6% at 4 points and 71.3% at 2. Either the bracket is much wider than 4 points or the 1:1 partial goes. That contradiction is a constraint on the geometry axis, and it is the sharpest thing any source says.

**So the opening range is worth testing on NQ and no published figure is transferable evidence about it** — the position every archetype here has started from.

## The expressibility checklist, run against ORB

Four findings, in decreasing order of how much each constrains [#236].

**1. A two-sided range is not established as expressible, and the probe that would settle it has not been run.** [#67] measured that the managed approach *refuses the opposite-direction submission outright* — the second order is never accepted, at either `EntriesPerDirection` — which kills the classic form of both stops live with the first fill winning. But `NqbtOrderLifetimeProbe.cs`'s scenario 3 submits two **`isLiveUntilCancelled`** orders, so what was measured is route 1. **Whether two plain three-argument opposite stops submitted on the same bar are both accepted is untested**, and § "What this changes about M19" above reads as though route 3 settles it. It does not. The refusal cited NinjaTrader's internal order-handling rules, which are about the managed approach's direction bookkeeping rather than about lifetime, so the likely answer is that route 3 fails the same way — but likely is not measured, and this is the first question an ORB baseline runs into. A sixth probe scenario is the cheap answer, and it is worth booking with any other NinjaTrader time rather than on its own.

**The simulator has the same limit from the other side.** Every entry loop holds one `pending_*` slot, so a second resting order in the opposite direction is new `@njit` work in fidelity-critical code, not a parameter. **And a two-sided range has an entry-side ambiguous bar that NT8 has no answer to at all**: a bar trading through both extremes is `ambiguity_policy`'s problem moved to the entry, and NT8 cannot arbitrate it because it cannot hold both orders. Expect the rate to be far worse than the bracket's, because the two levels sit a range width apart rather than a bracket apart.

**2. The bar grid decides which windows exist, and 60-minute bars cannot express a cash-anchored range at all.** §M13's condition for a resample grid aligned with the session is `N | 60`. A cash-open anchor adds a second: the cash open sits **930 minutes** past the 18:00 ET session open, so a bucket boundary lands on it only when `N | 930`. Together that is `N | gcd(60, 930)` — **`N` divides 30**, giving `N ∈ {1, 2, 3, 5, 6, 10, 15, 30}` and **excluding 60-minute bars**, because 930/60 is 15.5 and 09:30 falls mid-bucket. The window adds a third, `window_minutes % N == 0`: a 5-minute range needs `N ∈ {1, 5}` and a 15-minute range `N ∈ {1, 3, 5, 15}`. A 60-minute *window* is fine on any of them; a 60-minute *bar* is not. **This is a property to pin with a test rather than a comment**, on §M13's own reasoning — that the alignment holding for the periods anyone sweeps is exactly why it must be tested and not assumed.

**3. The resting order is free, and the reason generalises.** An ORB's trigger is a **level that persists**, not an event on one bar, so route 3 — resubmit each bar with an unchanged trigger — reproduces an order resting at the range extreme for the whole session. § "Route 3" establishes that this is not an approximation of a GTC order in Tier 1 but identical to one, because the fill test is the same per-bar OHLC comparison and the simulator has no queue position to differ on. The signal array is simply true on every bar after the range sets, and **`entry_order_lifetime_bars` is not needed** — the generalisation [#16] specified stays unbuilt. DeadCatBounce's entry mechanism carries the rest: a trigger price, the gap-at-open case and the submittability test, all reconciled.

**4. Flat-before-close does not bite; the *absence* of a per-day cap does.** A cash-anchored ORB enters around 09:45 ET against a 17:00 close, so `session_close_share` should be near zero and the hold is bounded by the geometry rather than by the clock — the opposite of §M13's warning about coarse bars. What has no counterpart in the simulator is "one trade a day": **no archetype carries a per-session entry cap**, and every loop re-enters as soon as it is flat. With a level-based trigger re-arming every bar, a stopped-out ORB re-enters at the same level on the next break, repeatedly. **That is the largest divergence between what would be simulated and what the published results measure**, since almost all of them are one-shot, and it lands on the cost bill: at $1.50 per round trip MNQ pays 3 ticks a trade, so four re-entries cost 3 points before the strategy does anything. It is either a parameter [#236] adds or a difference every comparison against outside work has to carry.

## What [#236] should build

**One variant, one side per grid, and nothing new in `bracket.py`:**

- **Anchor and window** — the cash open, with `window_minutes` swept over 5, 15 and 30, the three every source means; `timeofday.SessionPhase.CASH_OPEN` already names the hour they sit in. Resolution is constrained by the divisibility above, which makes it a validated axis rather than a free one.
- **Level and trigger** — the window's high and low, entered on a stop-market at the extreme ± `entry_offset_ticks`, re-armed every bar. Crabel's stretch and Fisher's ATR fraction are the same axis in a different unit, so they are ranges on one parameter rather than three archetypes.
- **Side** — **long-only and short-only as two grids over one params class**, exactly as §M26's exit schemes are three grids. This is what finding 1 forces, and it is not only a compromise: which break to take is a separate hypothesis, and it cannot be measured as "whichever fills first" until the probe says whether NT8 can hold both orders.
- **Geometry** — the existing four-leg R ladder, and the existing stops: the opposite range extreme, and `atr_bracket_distance` with `min_bracket_dollars` under it. A target in range widths is the second grid, the range width being the natural unit here in the way the basis was for ElasticBand.
- **The five context filters come free** by declaring the fields, and `regime` is the interesting one — the whole thesis is that a break out of a compressed range runs, and that is the label `regime.py` already produces.

**Deferred with reasons rather than by omission**: the retest entry, which is a second entry mechanism and a limit rather than a stop, so it should follow the baseline rather than confound it; the fade, cheap once the levels exist and rated by `Trading-Docs` as its best-supported setup, so it earns its own grid rather than a place in the first one; the overnight-range anchor, free once the range primitive is session-anchored and a genuinely different level; and the noise-area form, which belongs on the ElasticBand thread.

## Two predictions worth writing down before the sweep

**The range width will do most of the work, and it will do it through costs rather than through signal.** §M27's standing finding is that bar size explains an order of magnitude more variance than any period, and the opening range makes that quantity explicit: a stop at the opposite extreme is a stop whose size *is* the range, so the window length sets risk per trade directly. A 5-minute NQ range can be a few points wide against 3 ticks of commission — the floor `min_bracket_dollars` exists for, met from a new direction. Expect the short windows to lose to costs and the long ones to lose to the clock, and read `session_close_share` and the trade count before believing either.

**The matched random-entry arm matters more here than on anything built so far.** An ORB fires at a level price has already reached, on a day it has already moved, so its trades are conditioned on volatility twice over and a raw profit factor reflects that before it reflects any edge. `randomentry.py` matched on the same bars is what separates the two, and by the standing rubric a number with no null is not a finding.

[#16]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/16
[#234]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/234
[#235]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/235
[#236]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/236
[#67]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/67
