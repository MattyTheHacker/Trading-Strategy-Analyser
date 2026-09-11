---
id: M28.6
title: "M28.6 — the rejection: the fade's level, the retest's order type, and no break at all"
archetypes: [OpeningRange]
issues: [255]
gates: []
outcome: spec
verdict: >-
  Four modes and three properties, built from the fade's level and the retest's order type with no new machinery.
---

# M28.6 — the rejection: the fade's level, the retest's order type, and no break at all ([#255])

§M28.5 ended by naming the one thing the fade had never been given: a different *trigger*. This is it. It is a fourth entry mode rather than a parameter on the fade, because what it changes is the order type.

## Why the fade could not express it, and the reason is not the arming condition

`ORB_ENTRY_FADE` trades the **failed** break: `break_confirmed` compares the bar's adverse extreme against the range extreme, and `break_confirm_ticks` is validated `>= 0`, so the level has to be traded through before the order arms. The setup [#255] describes is the one where it is not — price comes down to within a few ticks of the range low, turns, and the trade is long back toward the middle with a stop just under the low.

**Relaxing the confirmation would not have reached it, because a fade rests a stop.** `submittable` refuses a stop entry at or through the market (§M18), and a long fade's trigger is `range_low + entry_offset_ticks`, so submission needs `close < range_low + entry_offset_ticks` — the bar has to have closed *below* the low. On an approach that never breaks, the close is still inside the range and the order is refused on every bar of it. A negative `break_confirm_ticks` would have armed a trigger that could never be submitted.

A buy limit below the market is legal where a buy stop is not. That is the same refusal read from the other side, and it is what `ORB_ENTRY_RETEST` already rests on.

## Four modes, three properties, and no new machinery

|           | waits for a break                      | rests at             | order     |
| --------- | -------------------------------------- | -------------------- | --------- |
| breakout  | nothing                                | the extreme traded   | stop      |
| fade      | that extreme broken *against* the side | the opposite extreme | stop      |
| retest    | that extreme broken *with* the side    | the extreme traded   | **limit** |
| rejection | nothing                                | the opposite extreme | **limit** |

The rejection is the fade's level, the retest's order type and the breakout's lack of an arming condition, so `ORB_OPPOSITE_EXTREME_ENTRIES`, `ORB_BREAK_ENTRIES` and `ORB_LIMIT_ENTRIES` replace the loop's four mode comparisons with three membership tests and nothing else moves. `bracket.py` is untouched, as it was for §M28.2.

**And the arming condition collapses into the fill.** A limit resting `k` ticks inside the low fills when price trades down to it, so "came within `k` ticks and turned" is what the fill test already measures. There is no proximity flag to carry and no per-session `bool` to reset, which makes the mode smaller than the fade it sits beside rather than larger.

## What it inherits, and what that costs

Everything the retest's limit does: fills at its price or better, does not fill on a touch, takes no slippage, and **a marketable limit is refused** — the one OpeningRange rule that deviates from an *unmeasured* NT8 behaviour rather than from a measured one (§M28.2). A second mode now rests on it, which raises what the two-sided-range probe is worth rather than changing what it would settle.

The signal is **dense** again, in the breakout's way rather than the fade's: no break gate thins it, so every armed bar resubmits, `randomentry.matched_random_signal` will refuse the draw below `MIN_DRAW_FREEDOM`, and `matched_random_ranges` is the null any gate 3 on it has to be drawn against — §M28.1 and §M28.2.

`entry_offset_ticks` changes meaning with the level rather than with the mode: it is measured past the level in the direction traded, so a breakout's runs outward and this one's runs inward. §M28's reason for defaulting it to 1 — a bar closing exactly on the level can never submit a stop entry — does not reach a limit, so `0` is a legal rejection and rests on the extreme itself.

## What it needs before it is swept, and both are already in the tooling

The two come from the fade's own campaign, which is what makes this a changed mechanism rather than a re-run with a new seed — § "Parked is not abandoned":

- **A stop the fraction axis as originally swept never reached.** `ORB_STOP_FRACTION` measures outward from the extreme the order rests at, and §M28.2 swept 0.25 to 1.0 of the range width outside it. §M28.5's `ORB_TIGHT_FRACTIONS` runs 0.02 to 0.25, which is where "a stop just under the low" lives. The opposite-extreme stop is refused here for the fade's reason: the entry level *is* that extreme, so it would be the fraction stop at a fraction of zero.
- **A target that reaches the middle.** §M28.5's `target=width+mid` ladder, `(0.5, 1.0, nan)`, is the first in the swept space to carry the midpoint, which is what a rejection trade is aiming at.

**Nothing has been swept here, and §M28.5's verdict does not transfer.** That campaign bounded the fade's *bracket* and found the floor set by its entry — the bar that fills a fade is the bar the break is happening on, so the stop is inside it. § "Why the axis is monotone" states the prediction that follows for this mode and it stands as written: a limit fills as price comes *to* it rather than after price has traded through, so the bar that fills a rejection is not by construction the bar a move is happening on. That is the thing a campaign here would measure first.

[#255]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/255
