---
id: M28.1
title: "M28.1 — OpeningRange: built, swept, and the first archetype through three gates"
archetypes: [OpeningRange]
issues: [236]
gates: [1, 2, 3, 4]
outcome: positive
verdict: >-
  The first archetype ever to pass gates 1 to 3: the stop mode splits it into a half that always passes and a half that always fails, and gate 4 is a sample-size verdict rather than a failure.
---

# M28.1 — OpeningRange: built, swept, and the first archetype through three gates ([#236])

§M28 named one configuration to build and three findings that constrained it. This is what was built, the four decisions that were not obvious, and the campaign — 172,800 combinations through §M27's four gates. **It passes the first three**, which nothing in this project has done before, and the gate that stops it is a sample-size verdict rather than a failure. The reasons to keep calling it a candidate are at the end.

## What was built, as coordinates in §M28's own six axes

**Anchor** the cash open, derived rather than written down: `sessionrange.CASH_OPEN_MINUTES` is `timeofday.phase_start_minutes` read at `CASH_OPEN`, so the 930 moves if the template's open ever does. **Window** 5, 15 or 30 minutes. **Level** the window's high and low. **Trigger** a stop-market order at the extreme ± `entry_offset_ticks`, resubmitted every armed bar. **Side** one per combination, `direction` being a swept axis. **Geometry** the opposite extreme or an ATR multiple for the stop, and the four-leg R ladder or a multiple of the range width for the targets.

The primitive is `nqbt/sessionrange.py` and the archetype `nqbt/sim/openingrange.py`, registered as `OpeningRange` and `TIER1_ONLY`. `bracket.py` was not touched: the archetype writes the entry half only.

## Four decisions that were not obvious

**A range is one fact about a session, so it is stored per session.** `SessionRangeGrid` holds the levels as `[n_keys, n_sessions]` and only the armed flag as `[n_keys, n_bars]`, read through a per-bar `session_id`. Stamping the levels per bar instead would cost 16 bytes a bar per window against the flag's one, which a parallel worker pays for every window a sweep tries. Measured on the fixtures at three windows: about 5 bytes a bar in total.

**A session short of window bars gets no range at all.** The alternative — measure whatever bars were there — produces a silently narrow range and therefore a silently tight stop, on exactly the sessions where the data is worst. One flag carries both "not yet" and "not at all", so the loop asks one question.

**Everything is measured from the trigger, never from the fill.** The stop, the risk and every target are known when the order is submitted, which is what a NinjaScript setting `SetStopLoss` at submission does and what the reconciled DeadCatBounce port already does. A gapped fill is therefore worse than planned and its R is measured against the plan, not against itself.

**The per-session entry cap is a parameter rather than a caveat.** §M28's finding 4 said a level-based trigger re-arms every bar, so a simulated ORB re-enters after every stop where the published results are one-shot. `max_entries_per_session` defaults to 1 and 0 is uncapped, which makes the divergence a swept axis. Measured below: uncapped runs roughly a fifth to a quarter more trades for a lower profit factor on the selection window (1.020 against 1.086) and no better on the held-out one, so the one-shot form the published results measure is also the better one here.

## The bar grid, pinned rather than commented

§M28's finding 2 asked for a test rather than a comment, and `tests/test_sessionrange.py` has it: over the bar sizes §M13 admits, a cash-anchored range is buildable at exactly `N ∈ {1, 2, 3, 5, 6, 10, 15, 30}` and **not at 60**. The general rule the validator enforces is that the anchor and the window must each be a whole number of bars; `N | 30` is the consequence of crossing that with §M13's `N | 60`, and the two conditions are genuinely separate — 31 divides 930 and not 60.

That makes the window a **variant dimension rather than a sweep axis** in `tools/campaign_sweep.py`: which windows exist depends on the resolution, and a sweep crosses its axes uniformly across every axis point. `Variant.resolutions` is what carries it, and the opening range is the only variant that sets it.

## The finding §M28 predicted backwards: the unfiltered signal has no matched null

§M28 predicted that "the matched random-entry arm matters more here than on anything built so far". It matters, and **on the unfiltered signal it cannot be drawn at all.**

A trigger that is a level persists, so the order is resubmitted on every armed bar and the signal is dense by construction. `matched_random_signal` draws, for each minute-of-session the rule fired at, that many bars without replacement from every bar sharing that minute — so when the rule has fired on nearly all of them the draw has almost nothing left to choose and returns the signal it was matched to. The quantity is **spare bars per signal**, and `SessionMinutePool.draw_freedom` reports it:

| configuration                           | signals | spare bars per signal |
| --------------------------------------- | ------- | --------------------- |
| DeadCatBounce, 1m                       | 3,456   | 173.8                 |
| InsideBar, 5m                           | 2,558   | 48.1                  |
| ElasticBand, 1m                         | 77,590  | 7.6                   |
| OpeningRange, `regime=DIRECTIONAL@n=50` | 4,267   | 3.8                   |
| **OpeningRange, unfiltered**            | 99,974  | **0.0019**            |

Three orders of magnitude separate the last row from everything else, which is why `MIN_DRAW_FREEDOM` is stated as **one spare bar per signal** — a meaning ("the draw must be able to relocate at least as many bars as it places") rather than a tuned number, with nothing real anywhere near it.

**A zero-freedom test is not enough, and finding that out cost a wrong answer.** The first guard refused only a draw with *no* freedom; the unfiltered OpeningRange has 185 spare bars against 99,974 signals, passed it, and `tools/campaign_null.py` then reported a p-value of 1.0 with a null spread of 1e-4 and the verdict "indistinguishable from random". That is the wrong conclusion arrived at honestly, which is the kind this project exists to catch. Two guards now stand: `matched_random_signal` refuses below `MIN_DRAW_FREEDOM` before spending the simulations, and `compare` refuses a null whose draws all agree — the same failure seen from the result rather than from the signal, and it holds whatever caused it. `campaign_null.py` catches the refusal and exits **2**, so a gate that could not be run cannot be read as a gate that passed.

**The consequence is narrower than it first looked.** A context filter that thins the signal restores the null, and the strata below are where gate 3 is answered.

## The campaign

`tools/campaign_sweep.py --strategies OpeningRange` over three passes — the full window at all twenty strata, the selection/holdout split at all twenty, and the quantile-fitted regime cells of §M27.5 — is **172,800 combinations in 45 minutes**, both roots, at the real commission for the root and one tick of slippage. Then §M27's four gates. Every figure below is re-derivable from `results/campaign/OpeningRange.duckdb`; it is a measurement of one dated run rather than a standing property.

## Gate 1 — the archetype splits cleanly in two, and half of it is dead

**The stop mode is not an axis so much as a partition.** Taking §M27's own gate — a majority of configurations profitable in at least one root × resolution cell — on the unfiltered stratum:

| stop                 | cells with a majority profitable | profitable share | median profit factor |
| -------------------- | -------------------------------- | ---------------- | -------------------- |
| the opposite extreme | **10 of 10**                     | 50.7% – 97.9%    | 1.004 – 1.103        |
| ATR multiple         | **0 of 10**                      | 1.0% – 10.4%     | 0.660 – 0.805        |

Pooled over both, the archetype fails gate 1; split, one half passes it in every cell and the other fails it in every cell. **A stop that is not the range is the wrong stop for a range breakout**, and half the swept space is dead weight that drags every pooled figure down. Everything below is therefore read within the opposite-extreme stop.

**`campaign_report`'s η² table is misleading here and the reason is the known blind spot.** It reports `atr_stop_multiple` at 0.761 and `stop_offset_ticks` at 0.506, but each is inert under the mode the other belongs to, so its column carries a default there and the "axis" is really the stop mode wearing a disguise. Computed **within** each mode:

| axis                      | within the opposite stop | within the ATR stop |
| ------------------------- | ------------------------ | ------------------- |
| `direction`               | **0.381**                | 0.060               |
| `window_minutes`          | 0.272                    | 0.008               |
| `resolution`              | 0.138                    | 0.032               |
| `max_entries_per_session` | 0.039                    | 0.022               |
| `atr_stop_multiple`       | —                        | **0.776**           |
| `stop_offset_ticks`       | 0.001                    | —                   |

**This is the first archetype whose largest live axis is not the bar size.** Resolution comes third behind which side is traded and how long the range is, and it is monotone but shallow — holding the window at 30 minutes, the median profit factor falls from 1.152 at one minute to 1.087 at fifteen on the selection window, a spread of 0.065 against the stop mode's 0.33.

## Gate 2 — it holds out, and by a wider margin than anything before it

`tools/campaign_holdout.py`: best 20 chosen on the first 60%, measured on the last 40%. **51 of 62 root × stratum cells pass**, the holdout top-20 beats the holdout median of everything in 91.9% of cells, and the mean decay is **0.221 with a mean rank correlation of 0.69**. Set against §M27.4's table for the six earlier archetypes, whose decay ran 0.33 to 0.49 and whose rank correlation ran 0.22 to 0.46, **both numbers are better than every dimension measured there.**

The unfiltered cell — the only one that involves no choice of stratum — passes on both roots: 1.227 → 1.125 on MNQ and 1.242 → 1.135 on NQ, all twenty configurations profitable held out, rank correlation 0.88, against holdout medians of 0.929 and 0.947.

Five strata fail on **both** roots: `phase=AFTERNOON`, `phase=CASH_OPEN`, `phase=CLOSE`, `htf=BELOW` and the raw-threshold `regime=UNCLASSIFIABLE` — whose quantile-fitted counterparts all pass, which is §M27.5's point arriving unprompted. **`phase=CASH_OPEN` failing on both roots with zero of twenty profitable is the one worth staring at**: it is the phase the range is anchored in, and restricting entries to the hour the range is measured in is the one cut that destroys the strategy. Phase is the worst dimension overall (decay 0.398, rank correlation 0.431, a quarter of cells passing), exactly as §M27.4 found for everything else.

`tools/campaign_walkforward.py` agrees across five sliding folds: pooled out-of-sample profit factor 1.139 to 1.171 on MNQ at every resolution, with the test median at or above the training median.

## Gate 3 — the entry beats a random entry, and this is what answers the drift question

Ranked on the selection window and tested on the held-out one, 200 draws, both roots:

| stratum                     | MNQ                             | NQ                              |
| --------------------------- | ------------------------------- | ------------------------------- |
| `regime=DIRECTIONAL@n=50`   | **better than random**, p=0.010 | **better than random**, p=0.010 |
| `trend=UP`                  | **better than random**, p=0.010 | **better than random**, p=0.010 |
| `regime=CONSOLIDATING@n=50` | indistinguishable, p=0.109      | indistinguishable, p=0.070      |
| `volume=THIN`               | indistinguishable, p=0.965      | indistinguishable, p=0.587      |

**Both roots agree on all four**, which is the consistency the standing rubric asks for in place of any single p-value. `regime=DIRECTIONAL` is the archetype's own thesis — a break out of a compressed range runs — rather than the best of twenty, which is the only reason it is quotable at all.

**And the null is what settles the drift objection.** MNQ rose about 4,500 points across the selection window and about 9,900 across the held-out one, which nearly doubled the index; a long-only breakout held to the close in that tape is close to a levered long, and the long side does carry almost all of the raw result (median profit factor 1.104 held out against the short side's 0.962). But **the matched null runs on the same bars and inherits the same drift**, so it is the control that comparison needed. Holding the `trend=UP` configuration and flipping only the side:

| side  | MNQ observed / null    | NQ observed / null     | verdict                       |
| ----- | ---------------------- | ---------------------- | ----------------------------- |
| long  | 1.441 / 1.085, p=0.010 | 1.440 / 1.104, p=0.010 | better than random            |
| short | 0.973 / 0.945, p=0.716 | 0.968 / 0.933, p=0.726 | indistinguishable from random |

A random entry on the same bars earns 1.085; the opening-range entry earns 1.441. **The drift is in both arms, so it cannot be what separates them** — the long-side entry rule is contributing something the drift does not. The short side is a different matter: it loses money, its null loses money too, and it has no measurable entry edge either way.

## Gate 4 — the equity path is honest, and the sample is not big enough to call it

`tools/campaign_montecarlo.py` on the held-out unfiltered shortlist. **The permutation test clears it**: reordering the same trades puts the observed maximum drawdown at p = 0.635 to 0.786 of its own reordering distribution, and usually *better* than the median reordering — the drawdown is not an artefact of a lucky sequence. The bootstrap is where it stops: the 90% interval on profit factor runs from about 0.96–0.99 up to 1.43–1.51, so **it brushes 1.0**, and net P&L comes back at p = 0.064 to 0.091 — not significant at 5% on a held-out window of roughly 460 trades. That is the same shape as the QQQ replication §M28 quoted, and it is a statement about the sample size rather than about the strategy.

## Where that leaves it

**Gates 1, 2 and 3 pass and gate 4 is a sample-size verdict rather than a failure** — which no archetype in this project has managed before. §M27's tally was four of six through gate 1, three through gate 2, one through gate 3. OpeningRange passes gate 3 on two strata on both roots, and is the **second** archetype to beat a matched null at all.

Three things keep it a candidate rather than a result:

- **The strata were chosen after looking at which held out best**, and choosing the stratum is a comparison too — §M27.4. Both roots agreeing is a real guard against that and is not the same as pre-registering. [#237] should state the stratum before running it.
- **The unfiltered configuration, which is the one with no stratum choice in it, has no matched null at all**, so the strongest gate cannot be applied to the cleanest configuration. A null that randomises the *level* rather than the bars is what would fix that, and it is new machinery.
- **`session_close_share` is 0.40 on the selection window and 0.45 on the held-out one.** Nearly half the legs leave at the session flatten rather than at a bracket level, so a large part of what is being measured is a hold-to-close trade rather than the bracket geometry. `ambiguous_share` is negligible at 0.003, which is the one number here needing no caveat.

## Corrections to §M28's two predictions

**"The range width will do most of the work, and it will do it through costs."** Half right, and wrong about the mechanism. The window is the second-largest live axis (η² 0.272) and the 5-minute range is the weakest of the three on both windows — but the ordering between 15 and 30 minutes flips between them, so no window is selectable on this evidence, and `min_bracket_dollars` never binds because the stop that works is a level rather than a distance. What actually dominates is the stop *mode*, which the prediction did not consider an axis at all.

**"The matched random-entry arm matters more here than on anything built so far."** Right about the importance and wrong about the availability — see above. It is also the gate that ended up carrying the whole argument, so the prediction was right for a reason it did not give.

## What is deferred, and why

**Every deferral below except the noise-area form has since been built — §M28.2 has the table.** What follows is the list as it stood at this milestone.

The retest entry, the fade, the overnight anchor and the noise-area form are §M28's own deferrals and are unchanged. Three more are added here: the **midpoint and range-fraction stops**, which are one axis over a level that already works rather than a new mechanism; a **null that randomises the level**, which the unfiltered configuration needs before it can be gated at all; and the **ATR stop's removal from the swept space**, which is 0 of 10 cells and half the runtime — kept for now only because §M28 named it and a parked configuration space is not retired on one campaign.

[#236]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/236
[#237]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/237
