---
id: M39
title: "M39 — EmaPullback's confirmation entry: it wins the selection window and not the holdout"
archetypes: [EmaPullback]
issues: [311]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  A stop order beyond the signal bar's extreme, built as a mode rather than an archetype, takes about three of the market entry's five trades and raises profit factor on the selection window in all eight root x resolution cells, but held out it costs at 2 and 5 minutes and gains insignificantly at 10 and 15, so it clears the pre-registered paired bar in none; resting it three bars is worse than one on the selection window everywhere, and gate 3 fails for all three arms with nothing clearing on both roots.
---

# M39 — EmaPullback's confirmation entry: it wins the selection window and not the holdout ([#311])

[§M35](m35-ema-pullback-swept.md) measured `require_turn`, the weak form of the pullback literature's "wait for the turn", as a coin flip, and [§M34](m34-ema-pullback-spec.md) left the strong form unbuilt. This builds it: **a stop order beyond the signal bar's extreme, so the trade is taken only if the trend resumes past the touch bar and never where price keeps going.** It runs against the market entry on the same bars in one pass, at two order lifetimes.

**The strong form is not a coin flip on the selection window and it does not hold out.** Paired configuration by configuration, it raises profit factor in all eight root × resolution cells on the first 60% of the bars. On the last 40% it costs at 2 and 5 minutes and gains by amounts no sign test separates from zero at 10 and 15. It clears the bar stated before the run in no cell, and gate 3 fails for it, for the three-bar lifetime and for the market entry alike.

Every figure below is re-derivable from `results/campaign/EmaPullback.duckdb`, batch 4. It is a measurement of one dated run against the archive as it stood on 2026-09-16, not a standing property.

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
| **Size**        | **317,952 combinations in 41.0 minutes** on twelve workers                               |

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

**All four were right**, and the third only narrowly on the holdout, where the win rate moves by about a point.

## The control reproduces §M37 exactly

**All 105,984 `entry=market` rows equal §M37's stored `stop=slow trail=off` rows at `fast_kind = slow_kind = ema`, on every stored statistic**, and no row is on one side of the join only. The archive was not re-ingested between the two runs, so this is the check step 1 exists for: adding the confirmation entry, and moving the stop-entry fill into `bracket.py`, moved nothing on the sweep path the trade-log gate does not reach.

## The paired question — cleared in no cell, and the gain belongs to the selection window

`tools/campaign_paired.py`'s pairing on profit factor, unfiltered stratum, `entry=confirm life=1` against `entry=market`. Each cell holds one pair per configuration viable in both arms, at 236 to 261 pairs; `improved` is the share of pairs the confirmation raised. Pairs inside a cell are not independent, so the p-values overstate:

| root | resolution | selection Δ PF | improved | p       | holdout Δ PF | improved | p       |
| ---- | ---------- | -------------- | -------- | ------- | ------------ | -------- | ------- |
| MNQ  | 2m         | **+0.030**     | 77%      | \<0.001 | −0.014       | 40%      | 0.002   |
| MNQ  | 5m         | **+0.031**     | 69%      | \<0.001 | −0.016       | 40%      | 0.002   |
| MNQ  | 10m        | **+0.055**     | 80%      | \<0.001 | +0.014       | 56%      | 0.079   |
| MNQ  | 15m        | **+0.041**     | 69%      | \<0.001 | +0.018       | 56%      | 0.103   |
| NQ   | 2m         | **+0.029**     | 71%      | \<0.001 | −0.002       | 49%      | 0.747   |
| NQ   | 5m         | **+0.029**     | 70%      | \<0.001 | −0.016       | 37%      | \<0.001 |
| NQ   | 10m        | **+0.057**     | 83%      | \<0.001 | +0.009       | 55%      | 0.171   |
| NQ   | 15m        | **+0.055**     | 75%      | \<0.001 | +0.005       | 51%      | 0.845   |

**No cell clears the bar in both windows.** The selection window says the confirmation helps everywhere, by three to six hundredths of profit factor and in about seven pairs of ten. The holdout says it costs at 2 and 5 minutes, significantly in three of those four cells, and gains at 10 and 15 minutes by amounts no sign test in that window separates from zero. Pooled over all 23 strata the pattern is the same: a gain on the selection window in all eight cells, and a cost at 2 and 5 minutes on the holdout.

**This is §M37's shape with the sign reversed.** The trail cost profit factor on the selection window and gained on the holdout; the confirmation gains on the selection window and does not hold. Neither campaign identifies what about the two periods decides it.

**The lifetime is answered the same way, and one bar is the better of the two.** `life=3` against `life=1` costs profit factor on the selection window in all eight cells, every one at p < 0.05. Held out it is a coin flip: a gain at MNQ 2m, a cost at MNQ 15m and nothing separable elsewhere. Against the market entry, `life=3` gains on the selection window in seven cells and is mixed held out.

## What it does to a trade

Unfiltered stratum, MNQ; the medians over configurations, market entry → confirmation at one bar. NQ moves the same way by similar amounts:

| window    | resolution | trades        | win rate      | exits at the session close | bars held |
| --------- | ---------- | ------------- | ------------- | -------------------------- | --------- |
| selection | 2m         | 3,027 → 1,816 | 38.0% → 39.6% | 8.7% → 10.8%               | 83 → 92   |
| selection | 5m         | 1,633 → 873   | 40.7% → 42.8% | 13.9% → 17.4%              | 51 → 56   |
| selection | 10m        | 932 → 477     | 42.6% → 45.1% | 20.1% → 24.9%              | 35 → 37   |
| selection | 15m        | 655 → 325     | 44.5% → 46.3% | 25.0% → 29.2%              | 27 → 28   |
| holdout   | 2m         | 1,887 → 1,126 | 40.0% → 40.1% | 7.1% → 9.4%                | 99 → 107  |
| holdout   | 5m         | 1,035 → 583   | 40.8% → 41.2% | 12.2% → 16.2%              | 52 → 58   |
| holdout   | 10m        | 626 → 323     | 41.4% → 42.4% | 19.8% → 23.9%              | 35 → 36   |
| holdout   | 15m        | 444 → 229     | 42.3% → 43.2% | 25.2% → 28.3%              | 26 → 26   |

**It takes about three trades in five**: the median configuration's trade count falls to 0.58–0.68 of the market entry's in all sixteen root × resolution × window cells, and falls at all in 88% to 100% of configurations. At three bars the order fills more often than at one in every cell.

**The win rate rises in all sixteen cells, by one to two and a half points on the selection window and by about a point or less held out.** On the holdout at five minutes the share of configurations whose win rate rose is 50% on both roots.

**The session close takes more of the exits in all sixteen cells**, by two to five points. The bracket is the reason. Its R is measured from a trigger at least a tick beyond the signal bar's extreme, so both the stop and the targets sit further away: on one grid configuration (`fast_period=9 slow_period=50`) over each whole series, the median planned risk is 20% to 29% wider than the market entry's at every resolution on both roots. Wider targets are reached less often before the clock. Between 1% and 3% of the confirmation's fills gapped past the trigger.

## Gates 1 and 2 on each arm

**Gate 1**, share of unfiltered configurations with a profit factor above 1:

| root | resolution | selection, market | selection, life=1 | selection, life=3 | holdout, market | holdout, life=1 | holdout, life=3 |
| ---- | ---------- | ----------------- | ----------------- | ----------------- | --------------- | --------------- | --------------- |
| MNQ  | 2m         | 15.1%             | 30.3%             | 26.9%             | 14.2%           | 18.3%           | 15.8%           |
| MNQ  | 5m         | 30.5%             | 47.6%             | 39.0%             | 16.7%           | 17.8%           | 5.8%            |
| MNQ  | 10m        | **57.1%**         | **76.4%**         | **66.4%**         | 15.8%           | 31.8%           | 30.4%           |
| MNQ  | 15m        | **72.4%**         | **81.9%**         | **70.0%**         | 18.3%           | 30.1%           | 25.8%           |
| NQ   | 2m         | 28.6%             | 44.3%             | 33.7%             | 38.8%           | 40.0%           | 38.3%           |
| NQ   | 5m         | 40.1%             | **50.8%**         | 49.2%             | 26.2%           | 29.8%           | 18.3%           |
| NQ   | 10m        | **68.3%**         | **86.7%**         | **75.8%**         | 27.1%           | 34.7%           | 29.2%           |
| NQ   | 15m        | **86.2%**         | **95.8%**         | **83.8%**         | 21.2%           | 29.7%           | 30.5%           |

The confirmation at one bar is a majority on the selection window in five cells against the market entry's four. No arm is a majority in any holdout cell.

**Held out, the profitable share is higher under the confirmation in all eight cells, while the paired median falls at 2 and 5 minutes.** Both are true of the same rows. A configuration taking three trades in five has a wider spread of profit factors, so more of them sit above 1 *and* the typical pair is worse. The profitable share is a tail and the paired median is the centre. Read against the paired table, this is not a gain.

**Gate 2**, `tools/campaign_holdout.py` per arm. The three arms hold the same combinations in every cell, so no shortlist is a best-of-more:

| arm          | strata clearing on both roots                                                       | clearing per root | returning their drawdown                              |
| ------------ | ----------------------------------------------------------------------------------- | ----------------- | ----------------------------------------------------- |
| market       | `compression=NORMAL`, `phase=LONDON`, `regime=DIRECTIONAL`, `volume=THIN`           | 8 MNQ, 4 NQ       | MNQ `volume=THIN`                                     |
| confirm, 1 b | `htf=BELOW`, `phase=CASH_OPEN`, `regime=DIRECTIONAL`, `trend=MIXED`, `volume=THIN`  | 8 MNQ, 6 NQ       | none                                                  |
| confirm, 3 b | `compression=NORMAL`, `phase=LONDON`, `regime=DIRECTIONAL`, `regime=UNCLASSIFIABLE` | 10 MNQ, 4 NQ      | `phase=LONDON` on both roots, NQ `regime=DIRECTIONAL` |

**`regime=DIRECTIONAL` and `volume=THIN` clear on both roots under the market entry and the one-bar confirmation**, and `regime=DIRECTIONAL` under all three. The unfiltered stratum fails under every arm.

## Gate 3 — no arm clears on both roots

The family, by rule 5: five strata cleared gate 2 on both roots under `entry=confirm life=1`, under the cap of six, so all five were taken. That is **50 tests per arm** rather than 60. Every configuration's `draw_freedom` on the holdout bars was read first: the lowest of the 150 is 43, against a refusal cut of 1, so each null had room to draw.

Configurations beating their own null, MNQ / NQ:

| stratum              | market | confirm, 1 bar | confirm, 3 bars |
| -------------------- | ------ | -------------- | --------------- |
| `htf=BELOW`          | 2 / 1  | 3 / 0          | 5 / 3           |
| `phase=CASH_OPEN`    | 1 / 4  | 3 / 2          | 2 / 1           |
| `regime=DIRECTIONAL` | 5 / 4  | **5 / 5**      | **5 / 5**       |
| `trend=MIXED`        | 3 / 4  | 3 / 3          | 3 / 4           |
| `volume=THIN`        | 5 / 4  | 5 / 2          | 4 / 4           |
| **total**            | 33     | 31             | 36              |

**Tests reaching p < 0.05, which are two-sided:**

| arm             | better than random                                                   | worse than random          |
| --------------- | -------------------------------------------------------------------- | -------------------------- |
| market          | 0                                                                    | 0                          |
| confirm, 1 bar  | 6: NQ `regime=DIRECTIONAL` 3, MNQ `volume=THIN` 2, MNQ `htf=BELOW` 1 | 3: `htf=BELOW`, both roots |
| confirm, 3 bars | 1: MNQ `regime=DIRECTIONAL`                                          | 0                          |

**Gate 3 fails for all three arms.** No stratum reaches p < 0.05 in the better direction on both roots, which is the bar §M28.16 set. Fifty two-sided tests at that level give two or three by chance.

**The one-bar confirmation's six are more than chance puts in one direction, and they are not evidence of an entry.** Each cell is one root only. The three in NQ's `regime=DIRECTIONAL` are all at 2 minutes on 13, 34 and 38 held-out trades, one of them a profit factor of 10.1 on 13. Its MNQ twin beats the null in all five configurations and reaches p = 0.05 in none. `htf=BELOW` holds both significant directions on MNQ at once, which is a sample too thin to have a sign rather than an effect. The family was also chosen on this arm's gate 2, so the selection favours it.

**`regime=DIRECTIONAL` beats its null in all five configurations on both roots under both confirmation arms**, and in nine of ten under the market entry. It is the only cell that does, and it reaches p = 0.05 on one root under each confirmation arm and on none under the market entry.

**The binding constraint is the sample, as in §M35, §M36 and §M37.** The median held-out trade count is 32.5 under the one-bar confirmation, 35 under the market entry and 39 at three bars, with 22, 20 and 17 of the fifty tests under 30.

## What this does not settle

- **Why the selection window's gain does not hold.** The same question §M37 left open about the trail, with the opposite sign, and this campaign does not answer it either.
- **Cancelling the order when the setup breaks.** The resting order is cancelled only by a fill, a replacement or the session close. A close back through the slow average while it rests does not cancel it, and a rule that did is a different entry.
- **Lifetimes other than one and three bars, and an entry offset other than one tick.**
- **The kind axes.** Both were held at `ema`, so nothing here says whether the confirmation interacts with them.
- **Arming on the pending-exit bar.** The confirmation submits only when flat at the close, and the market entry may re-enter at the open its exit fills at. Both exits that create that bar were off throughout, so the difference was never exercised.
- **One minute was not swept**, as in §M35 and §M37.
- **Nothing is re-ranked.** EmaPullback remains `TIER1_ONLY` with no NinjaScript, and `docs/findings/README.md` is unchanged because nothing here reaches a recommendation.

Every figure here is one dated run over the archive as it stood on 2026-09-16, re-derivable from `results/campaign/EmaPullback.duckdb` plus `tools/campaign_sweep.py`, `tools/campaign_paired.py`, `tools/campaign_holdout.py` and `tools/campaign_null.py` — not a standing property.

[#311]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/311
