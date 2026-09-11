---
id: M28.2
title: "M28.2 — the deferral list, built: three entry mechanisms, one stop axis, and a null over levels"
archetypes: [OpeningRange]
issues: [237]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  The breakout reproduces §M28.1 and gains a level null; the fade fails gate 1 everywhere and is parked; the retest has no verdict because its gate-2 pass measures `ambiguity_policy` rather than a strategy.
---

# M28.2 — the deferral list, built: three entry mechanisms, one stop axis, and a null over levels ([#237])

§M28 and §M28.1 each ended with a list of things deferred with reasons rather than by omission. [#237] is that list, built — and then swept, under strata named before the run. **The headline is a negative result and a trap**: of the two entry mechanisms added, one fails outright and the other cannot be read at all, because the campaign ranked it straight into a corner where the simulation assumption decides the trade. The breakout reproduces §M28.1 and gains the null it never had.

## What was deferred, and where each one landed

| deferred in | what                                  | landed as                                                     |
| ----------- | ------------------------------------- | ------------------------------------------------------------- |
| §M28        | the retest entry                      | `ORB_ENTRY_RETEST` — the first limit entry in the registry    |
| §M28        | the fade                              | `ORB_ENTRY_FADE`                                              |
| §M28        | the overnight-range anchor            | `ORB_RANGES["overnight"]`, and London beside it               |
| §M28        | the noise-area form                   | **still deferred** — it is ElasticBand's thread, not this one |
| §M28.1      | the midpoint and range-fraction stops | one axis, `stop_range_fraction`                               |
| §M28.1      | a null that randomises the level      | `randomentry.matched_random_ranges`                           |
| §M28.1      | the ATR stop's removal                | gone from the re-sweep's variant set                          |

## The stop axis absorbed a mode rather than sitting beside one

§M28.1 deferred "the midpoint and range-fraction stops" as two things. They are one: **a fraction of the range width measured back from the extreme the order rests at**, where `0.5` is the midpoint and `1.0` reproduces the opposite-extreme stop *exactly*, offset included, on both sides.

That exactness is the point rather than a coincidence, and `tests/test_openingrange_sim.py` pins it. §M28.1's gate 1 found the archetype split cleanly in two by stop mode — 10 of 10 cells one way, 0 of 10 the other — so the one thing a new stop axis must not do is fail to contain the half that worked. It contains it as an endpoint, which makes every other value on the axis directly comparable against it instead of against a different mode.

The ATR stop is gone from the re-sweep for §M28.1's own reason: 0 of 10 cells and half the runtime. **It is parked, not retired** — it stays in `ORB_STOP_MODES`, and § "Parked is not abandoned" is the rule. What retires it, if anything does, is a campaign that says so with a reason that is not "it lost once".

## The fade and the retest are the same primitive read twice

Both wait for a break that already happened, which is one `bool` per session, reset at the session boundary and set from the bar's own extreme against the level. What differs is only **which extreme** and **which order type**:

|          | waits for                                          | rests                                      | order     |
| -------- | -------------------------------------------------- | ------------------------------------------ | --------- |
| breakout | nothing                                            | beyond the extreme in the direction traded | stop      |
| fade     | that extreme broken *against* the direction traded | back inside the range                      | stop      |
| retest   | that extreme broken *with* the direction traded    | at the level it broke                      | **limit** |

So `entry_level` is three lines and `break_confirmed` is one comparison, both sided through `bracket.sided` — the sign multiplier doing the work it was built for. **The retest is the only one that reaches new fill semantics**, and it reaches them at the entry for the first time: a limit fills at its price or better, does not fill on a touch, and takes no slippage. All three rules already existed for exits; `bracket.limit_filled` is the one implementation and the entry reads it at `-direction`.

**One decision in there is a deviation rather than a port, and it is flagged as such.** NT8 refuses a stop entry at or through the market (§M18). What it does with a *marketable limit* — a buy limit submitted at or above the close — is unmeasured, and the likely answer is that it accepts and fills at market. The simulation refuses it, so a retest never enters at a price the market has already left. That is the conservative side of an unmeasured behaviour, and `docs/nt8-fidelity.md` §M28.2 books it against the two-sided-range probe §M28 already wants. **It is the one thing here that a trade list could contradict.**

## The anchor was free, and the divisor rule is why it stayed unbuilt

`anchor_minutes` has been a parameter since §M28.1; what was missing was a sweep that moved it, because `orb_resolutions` had the 930-minute cash anchor written into it. Generalised to take the anchor, it produces §M28's second finding as arithmetic rather than as a comment:

| range        | anchor | window | resolutions |
| ------------ | ------ | ------ | ----------- |
| `cash=5m`    | 930    | 5      | 1, 5        |
| `cash=15m`   | 930    | 15     | 1, 5, 15    |
| `cash=30m`   | 930    | 30     | all five    |
| `overnight`  | 0      | 930    | all five    |
| `london=60m` | 540    | 60     | all five    |

**The overnight range survives at every resolution where a 5-minute cash range survives at two**, which is not a quirk: its anchor is the session open, which every bar boundary lands on, and its window is the 930 that constrains the cash anchor from the other side. The London anchor is `anchor_for(SessionPhase.LONDON)` — derived from the same phase clock as `CASH_OPEN_MINUTES`, so neither can drift if the template's open ever moves.

## The null over levels, which is what §M28.1 could not run

§M28.1's sharpest open question was that **the configuration with no stratum choice in it — the unfiltered one — had no null at all**, because a trigger that is a level fires on every armed bar and `matched_random_signal` had nothing left to relocate. Its own refusal message named the fix: "an entry whose trigger is a level rather than an event is dense by construction and needs a null over the level rather than over the bars."

`randomentry.matched_random_ranges` is that null. It holds the bars, the costs, the geometry and **the armed flags** fixed — so the entry signal is bit-identical and only the level moves — and permutes which session's range is traded. The question it asks is the one the archetype's thesis actually makes: *is the range this session printed worth more than a range of some other session's shape, placed at this session's price?*

**Every range travels as two offsets from the price its own window closed at, never as a pair of prices.** That is the whole of why this works: NQ drifts thousands of points across a campaign window, so a donor transplanted absolutely would sit out of reach all day and the "null" would be a run of no trades — a p-value manufactured by the transplant rather than measured. Carried as offsets, a donor from six months away arrives at today's price with its width and its asymmetry intact.

`MIN_DONOR_SESSIONS` is its `MIN_DRAW_FREEDOM`, and it is stated the same way — as a meaning rather than a tuned number. **A uniform permutation has exactly one expected fixed point whatever its size**, so the share of sessions handed back the level they actually traded is `1/n`; twenty sessions is "at most one in twenty keeps its own".

**What it does not settle.** It is a null over *which* range is traded, not over whether a range is the right kind of level at all — a permutation of observed ranges cannot answer the second question, and neither could the draw over bars. And it is a second null rather than a replacement: the two arms ask different questions, and an archetype that beat one and not the other would be telling you which.

## The strata, stated before the run

§M28.1's first caveat was that its strata "were chosen after looking at which held out best, and choosing the stratum is a comparison too", and it asked [#237] to state the stratum before running it. `STRATUM_SETS["orb"]` is that statement, in code:

- **`unfiltered`** — the only cell with no choice of stratum in it, and now the only one with a null it can use.
- **`regime=DIRECTIONAL`** — the archetype's own thesis, that a break out of a compressed range runs.
- **`trend=UP`** — the other cell that passed gate 3 on **both** roots in §M28.1.

Two and three are the two §M28.1 passed, named in advance so the re-sweep is a test of them rather than another search over twenty. **This is weaker than pre-registration and stronger than nothing**: the strata were chosen from an earlier run's results, so what it buys is that the *next* result cannot be the best of twenty presented as though it were the only one.

The re-sweep is its own variant set for the reason `VARIANTS` already gives — §M28.1's stored rows were produced by that grid, and adding axes to it would leave the rows and the code that produced them disagreeing. `--variants orb --strata orb` is the pass.

## Two predictions, before the sweep rather than after

Written down so they can be scored the way §M28's two were, and §M28's two were half wrong in an informative way.

**The retest will trade a little less than the breakout rather than far less, and the sample-size verdict will still be what stops it.** The obvious reading — it needs a break *and* a return, so it is strictly more selective — is wrong, and the reason is §M18. A breakout's stop is refused on every bar that closes past the trigger, which after a break is most of them; a retest's limit is refused on every bar that closes *inside* it, which after a break is few of them. **The two rules lose their opportunities to opposite halves of the same refusal**, so the selectivity mostly cancels. Measured on a 60-session random-walk fixture at the one-shot cap: 136 breakout trades against 128 retest trades on the same bars, and 18–29% fewer per combination once the `break_confirm_ticks` axis is divided out. §M28.1 could not call gate 4 on roughly 460 held-out trades, so a fifth fewer is still the wrong side of the line: expect gate 4 to bind at least as hard.

**The fade will be the one that separates the roots, and drift is why.** §M28.1's null showed the long side carrying almost all of the raw result in a tape that nearly doubled. A fade of the *low* is a long trade that fires when the day has gone down — the opposite conditioning to the breakout's — so it is the first configuration here whose long side is not aligned with the drift. If the fade's long side survives its matched null, that is a stronger signal than anything §M28.1 measured; if it collapses, that is the drift being visible from the other side.

## The campaign, and the finding is a negative one

`tools/campaign_sweep.py --variants orb --strata orb` over three passes — the full window, the selection/holdout split, and the quantile-fitted regime cells — is **364,800 combinations in 31 minutes**, both roots, at the real commission for the root and one tick of slippage. Every figure below is re-derivable from `results/campaign/OpeningRange.duckdb` and is a measurement of one dated run rather than a standing property; the rows carry `entry_mode`, which is what separates them from §M28.1's.

**Gate 1 — the stop fraction is monotone, and it recovers §M28.1 at its endpoint.** Share of combinations profitable, unfiltered, full window, MNQ / NQ:

| entry    | frac 0.25     | 0.50          | 0.75          | 1.00              |
| -------- | ------------- | ------------- | ------------- | ----------------- |
| breakout | 0.000 / 0.006 | 0.135 / 0.146 | 0.383 / 0.438 | **0.615 / 0.633** |
| fade     | 0.036 / 0.054 | 0.073 / 0.143 | 0.139 / 0.185 | 0.190 / 0.246     |
| retest   | 0.611 / 0.709 | 0.542 / 0.609 | 0.546 / 0.603 | 0.619 / 0.654     |

The breakout clears only at `1.0`, which *is* the opposite-extreme stop — so the axis reproduced §M28.1's gate-1 finding from a new direction and put a gradient under it. **A stop that is not the range is not merely worse; it degrades smoothly to nothing as it tightens.** The midpoint stop the literature recommends is the 0.50 column, and it is not close. **The fade fails gate 1 on both roots at every fraction**, which is the clearest verdict in the table.

**Gate 2 — the retest appears to pass, and it is an artefact.** Through `campaign_holdout`'s own `verdict()`, per entry mode: breakout 16 of 16 cells pass, fade 0 of 16, retest 16 of 16 with held-out profit factors of **2.15 to 3.87**.

That number is not a result, and the standing rubric is what catches it:

| entry      | top-20 held-out PF | top-20 `ambiguous_share` | its population's mean |
| ---------- | ------------------ | ------------------------ | --------------------- |
| breakout   | 1.101 / 1.123      | 0.003 / 0.000            | 0.024                 |
| fade       | 0.901 / 0.768      | 0.001 / 0.001            | 0.019                 |
| **retest** | **2.755 / 2.780**  | **0.345 / 0.338**        | 0.021                 |

**The selection window picked, almost exclusively, the configurations whose outcome is decided by the ambiguity assumption rather than by the data** — sixteen times the population rate. Every one of the top twenty carries `stop_range_fraction=0.25`, and both directions score about 2.7, which is the tell: an assumption does not care which way you trade.

**The mechanism is specific to the entry type, and no earlier archetype could have found it.** A stop entry fills as price moves *toward* its target, so the bar's favourable extreme plausibly comes after the fill. A limit entry fills as price moves *away* from its target, so on the fill bar that extreme usually **predates the fill** — and bar-close OHLC cannot say so. Measured at `frac=0.25`: the retest exits on its own entry bar 22.9% of the time with 49% of those being targets, against the breakout's 5%. A one-bar range (`cash=5m` on 5-minute bars) with a quarter-range stop and an R ladder on top puts both bracket levels inside a single bar, and then the policy decides the trade.

**This is not a bug to fix in the fill model.** NT8 under bar-close OHLC has exactly the same ambiguity, and resolving it more pessimistically would breach the prime directive in the other direction — § "Ambiguous bars resolve to whichever level is nearer the open". What is new is that a configuration's *result* is now dominated by it, so the result is not attributable. `.claude/rules/simulator.md` predicted the shape of this: **each new entry mechanism reaches rules the others made unreachable by construction.**

**Gate 3 — the level draw runs where the bar draw refuses, and that is the whole point of it.** On the unfiltered breakout, ranked on the selection window and tested on the held-out one, 200 draws:

| root | observed PF   | level-null PF | excess           | p             |
| ---- | ------------- | ------------- | ---------------- | ------------- |
| MNQ  | 1.095 – 1.116 | 0.928 – 0.959 | +0.125 to +0.167 | 0.040 – 0.159 |
| NQ   | 1.095 – 1.143 | 0.953 – 0.972 | +0.136 to +0.178 | 0.090 – 0.209 |

The draw over **bars** refused on both roots with the message §M28.1 wrote, and `campaign_null.py` exited 2 — a gate that could not be run rather than one that passed. The draw over **levels** ran on the same rows.

**The excess is consistent in sign and size across both roots and all three resolutions, and only one cell clears p < 0.05.** By the standing rubric that is *suggestive, not significant* — but it is strictly more than §M28.1 could say, because there this configuration had no null at all.

**What the level null settles that the bar null could not.** Its arm holds the bars, the signal and the armed flags fixed and moves only the level — and it **loses money**, −5,850 to −9,804 net on MNQ, where the observation makes +16,254 on the same rising tape. So the drift is in both arms and cannot be what separates them, which is §M28.1's own drift argument reached for the configuration that had no way to make it.

## Both predictions were wrong, and the second one usefully

**"The retest will trade a little less than the breakout."** Right about the mechanism and wrong about what would matter. Per combination it does trade about a fifth less, and the §M18 cancellation is real — but the trade count was never what stopped it. What stopped it was that its geometry makes ambiguous bars common where every earlier archetype made them rare, which no part of the prediction anticipated.

**"The fade will be the one that separates the roots."** Wrong twice over. The fade does not separate the roots — NQ runs about five points of profitable share above MNQ in every fade cell, which is the same gap the other two show — and it does not survive to a stage where separation would mean anything, failing gate 1 at every fraction on both roots. **The entry that turned out to be interesting was the retest, and it was interesting for a reason that is not about trading at all.**

## Where that leaves the three entries

- **Breakout** — reproduces §M28.1 and adds the gradient beneath it. It is still the only OpeningRange entry with a defensible result, and the level null now gives its unfiltered form a control it did not have.
- **Fade** — fails gate 1 on both roots at every stop fraction. **Parked, with a reason**: § "Parked is not abandoned". What would justify a re-run is a different bracket, not a different seed — its stop is the axis that never suited it, since the range extreme it enters at is the one thing it cannot stop behind.
- **Retest** — **no verdict, and that is the finding.** Its gate-2 pass is a measurement of `ambiguity_policy`, not of a strategy. It cannot be read at all until its shortlist is constrained to configurations whose brackets do not both sit inside one bar, which is a change to how the campaign selects rather than to the archetype.

## What this campaign says the tooling needs

**A shortlist that ranks on profit factor will select for `ambiguous_share` whenever an archetype has configurations where it is high**, and nothing in the campaign tools says so. §M28.1 knew to read the number and read it once, by hand, for one configuration. That worked because OpeningRange's ambiguity was 0.003 everywhere; it does not survive an archetype whose ambiguity ranges from 0.006 to 0.35 across its own swept space.

**The guard belongs in the campaign tools rather than in the archetype**, beside the trade floor `MIN_TRADES` that is already there for the same reason: a statistic that is undefined or unattributable should not be rankable. What that guard should be, and what it should not be, is [#248], answered in §M28.3 and §M28.4: the spread between the ambiguity policies, reported beside the shares and gating nothing, and then the minute bars inside each ambiguous bar settling what they can of it.

## What is still deferred

The **noise-area form**, which §M28 put on ElasticBand's thread and which stays there. The **two-sided range**, which is not a parameter but a probe — §M28's finding 1, unanswered. The **marketable-limit question** above, which is the same booking. And a **null over the level's kind rather than its identity**, which is the thing neither null asks.

[#237]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/237
[#248]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/248
