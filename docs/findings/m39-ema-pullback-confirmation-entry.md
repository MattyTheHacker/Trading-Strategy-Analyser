---
id: M39
title: "M39 — EmaPullback's confirmation entry"
archetypes: [EmaPullback]
issues: [311]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Pending: the campaign is running, and the reading plan below was committed before it finished.
---

# M39 — EmaPullback's confirmation entry ([#311])

[§M35](m35-ema-pullback-swept.md) measured `require_turn`, the weak form of the pullback literature's "wait for the turn", as a coin flip, and [§M34](m34-ema-pullback-spec.md) left the strong form unbuilt. This builds it: **a stop order beyond the signal bar's extreme, so the trade is taken only if the trend resumes past the touch bar and never where price keeps going.** It runs against the market entry on the same bars in one pass, at two order lifetimes.

The rules and the NinjaScript each would be written as are in [`nt8-fidelity.md`](../nt8-fidelity.md) §M39; this file is the design decision and the campaign.

## A mode on EmaPullback, not an archetype of its own

[#311] asked for this to be decided explicitly, because two precedents here disagree. §M34 said a resting-stop entry folded into EmaPullback "would make the archetype two archetypes wearing one name". OpeningRange has four entry modes, stop and limit orders both, in one archetype. [#311] named the difference that might matter: OpeningRange's four entries share one trigger level and differ in the order placed at it, where this shares one setup and changes the order type.

**It is a mode, `confirm_entry`, and the difference [#311] named is the reason rather than the objection.** Four things decide it:

**What the registry keys a strategy on is its signal, and the signal does not change.** The bars the setup arms on and the side it takes are §M34's, bar for bar, under both orders. The matched random-entry null is drawn over that signal, so one archetype keeps one signal population and the two orders are compared on it. OpeningRange's entries do not share a signal, since a fade waits for a break the breakout does not. So OpeningRange's modes are the harder case for one name, and it already carries four.

**§M34's objection was to pooling, and a stored column does not pool.** Its argument was that two mechanisms under one name "pool into one row group, and no later query can separate them". That was true of an EmaCrossover mode, which would have put two setups under one control. Here `confirm_entry` is a column on every row and the variant name carries an `entry=` token, so every reading tool separates the two with `--variant`, as it does OpeningRange's entries.

**`dead_axes` sees everything the mode makes inert.** `entry_offset_ticks` and `entry_order_lifetime_bars` go unread under the market order and gate on `confirm_entry`, and no existing axis goes unread under the stop order. This is not ElasticBand's or OpeningRange's blind spot. A separate archetype would instead need a parameter class copying EmaPullback's field for field, because §M34 writes them out rather than inheriting, and the two would differ by three fields and have to be kept in step.

**What §M34 got right is kept, just not as a second name.** It is a different mechanism: a trigger price, a submittability rule, an order that may not fill, and R measured from the trigger rather than the fill. So it gets its own rules section in `nt8-fidelity.md` and its own entry loop, and its results are never pooled with the market entry's.

### Why it is its own loop

`simulate_crossover` has no trigger price, and it is EmaCrossover's loop too, so a mode inside it would have put the registry's known-negative control under the change. OpeningRange's loop, which SqueezeBreakout reuses, takes the side as one value per combination, because a two-sided resting order cannot be expressed. EmaPullback takes both sides in one run, reading the side bar by bar, and running that loop once per side would let a long and a short be open at the same time.

So `simulate_confirmation` is a new entry half: the pending order's trigger, stop, side and lifetime. The exits are `bracket.resolve_brackets`, the ratchet, `hold_expired` and `flatten_position`, as the market entry's are. The fill test is `bracket.stop_entry_fill`, moved out of `openingrange.py` so both callers share one copy.

## What was run

|                 |                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------- |
| **Arms**        | `entry=market`, `entry=confirm life=1` and `entry=confirm life=3`, in one pass           |
| **Grid**        | 288 combinations in each arm: §M35's grid with `fast_kind` and `slow_kind` held at `ema` |
| **Strata**      | §M35's 23, one context dimension at a time                                               |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                                  |
| **Roots**       | MNQ and NQ, spliced continuous, the archive as re-ingested on 2026-09-16                 |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage             |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                              |
| **Size**        | 635,904 combinations                                                                     |

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants emapullback-confirm --split \
    --strata emapullback-confirm --resolutions 2 5 10 15 --n-jobs 12
```

**The kind axes are held rather than swept**, and they are the two [#311] named as the ones to cut. §M35 measured both as inert and as inverting across the split, and three arms over §M35's full grid would take about three and a half hours at §M37's rate. Both are held at `ema`, EmaPullback's default. Every other axis is §M35's, so each arm holds the same 288 combinations in every cell and the arms differ by the order alone.

**The entry offset is one tick and is not swept.** At zero, a signal bar that closed on its own extreme can never submit (§M39).

## What will be read, stated before the run finished

Committed while the sweep was still running, so nothing below could be chosen after a result had been looked at.

1. **The control is a reproduction first.** The archive's first and last bars equal §M37's stored batch on both roots, checked before the run. So every `entry=market` row must equal §M37's stored `stop=slow trail=off` row with the same root, resolution, window, stratum and parameters, on every stored statistic. A single difference is a defect, and nothing below is read until it is explained.
2. **The question is answered paired, not by a shortlist.** `tools/campaign_paired.py` pairs on profit factor, one row per root × resolution, **in the unfiltered stratum and in each window separately**. The comparison is `entry=confirm life=1` against `entry=market`. The confirmation entry counts as an improvement in a cell only where the median delta is positive *and* the sign test reaches p < 0.05 in **both** windows. The lifetime is read the same way, `life=3` against `life=1`. The same pairing over all 23 strata is reported as a description, not a test, because the strata share bars.
3. **The mechanism is read off the same pairs**: the trade count against the market arm's, `win_rate`, `mean_r`, `avg_bars_held` and `session_close_share`. **`mean_r` is not comparable across the orders**, because the confirmation's R is measured from its trigger.
4. **Gates 1 and 2 are §M35's, on each arm.** Gate 1 is the share of unfiltered configurations with a profit factor above 1 at 30 trades or more. Gate 2 is `tools/campaign_holdout.py`'s `passes` per root and stratum, run once per arm with `--variant`.
5. **Gate 3's family is the strata where `entry=confirm life=1` clears gate 2 on both roots.** That is at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. **All three arms are measured over that one family**: both roots, the best five configurations by selection-window profit factor, measured on the holdout, 400 draws, the draw over bars. That is 60 tests per arm. If no stratum qualifies, gate 3 is not run and that is the result.
6. **The null matches the signal, not the fills.** A drawn bar submits the same stop order a signal bar would, so both the observation and the null lose the orders that never fill, and the rate statistics carry the verdict. `draw_freedom` is read for every shortlisted configuration before any p-value.
7. **Nothing is added, dropped or re-cut after the first run.**

## Predicted before the run finished

- **The control reproduces §M37 exactly.**
- **The confirmation takes fewer trades than the market entry in every root × resolution × window cell**, and `life=3` takes more than `life=1` in every cell.
- **Its win rate is higher than the market entry's in a majority of the sixteen cells.** An entry that needs price to go its way first should win more often.
- **It does not clear the bar in (2) in a majority of the eight cells.** The weak form was a coin flip, and a trigger beyond the signal bar's extreme pays for its confirmation with a worse entry price on every trade it takes.

[#311]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/311
