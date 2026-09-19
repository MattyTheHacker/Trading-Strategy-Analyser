---
id: M42
title: "M42 — InsideBarTrailing's midday cell through the exclusion test and gate 4"
archetypes: [InsideBarTrailing]
issues: [345]
gates: [4]
outcome: mixed
verdict: >-
  The first cell in the registry to survive the exclusion at all — 5 of 10 configurations on MNQ and 4 of 10 on NQ are profitable without their session-close legs — and the first to put a bootstrap 5th percentile above a profit factor of 1.0, on all ten MNQ configurations; the walk-forward passes on both roots, and on each root one bracket axis separates every surviving configuration from every failing one.
---

# M42 — InsideBarTrailing's midday cell through the exclusion test and gate 4 ([#345])

**No new sweep and no ingest.** §M28.16 found `InsideBarTrailing phase=MIDDAY` at 5 minutes to be the strongest gate-3 result outside OpeningRange and ended its row by naming the one measurement that would settle it: *"`tools/campaign_exits.py` is what would settle whether its excess survives the exclusion, and it has not been run here."* [#345] is that run, plus the rest of gate 4.

Both roots, 5-minute bars, **the ten configurations the selection window ranked highest** — the same family §M28.16's gate 3 was measured over, so the two reads are about the same rows rather than about two shortlists of different depths.

## The contamination trap [#345] named is clear, and a different one is not

[#345] required a control before anything was drawn, because §M29's hold ladder, §M30's recut and §M32's volume windows have all been swept into `InsideBarTrailing.duckdb` since §M28.16 — and §M31.1 is what an exclusion read over a contaminated stratum looks like, four survivors that were all `hold=80` arms leaving by a different door.

**That trap is absent here.** `phase=MIDDAY` holds one variant, `trailing`, and 432 rows per root × resolution × window — the campaign grid exactly. The hold arms went into `unfiltered`, and §M30's and §M32's recuts into their own `@`-suffixed strata, so none of them can reach this cell. Read off the stored rows, the shortlist reproduces §M28.16's table figure for figure: 273–300 trades at 1.398–1.587 on MNQ and 260–276 at 1.288–1.685 on NQ, `session_close_share` 0.237–0.249 and 0.229–0.481, `ambiguous_share` 0.000.

**A different trap stopped the run instead, and it is §M41's.** The archive was extended on 2026-09-16, after this campaign was swept, so `campaign_shortlist.py --held-out` refuses to store a log for any of these rows — the guard doing exactly its job, and leaving gate 4 with no book to read. `tools/campaign_swept.py` is new here and is the way round it that does not weaken the guard: re-run the shortlist, hand each log straight to the reader rather than storing it, over the archive cut back to where it stood when the row was swept, and **report the agreement instead of requiring it** — the weakening `tools/campaign_flatten.py` already makes for the same reason.

What that recovers, per root:

| root | swept window recovered                                                      | trade counts reproduced | largest net gap | as a share of the book |
| ---- | --------------------------------------------------------------------------- | ----------------------: | --------------: | ---------------------: |
| MNQ  | **yes**, neither end moved                                                  |                10 of 10 |             $63 |                   0.2% |
| NQ   | **no** — holdout now 2024-10-14 to 2026-09-16, was 2024-09-25 to 2026-08-10 |                 0 of 10 |         $41,530 |                    13% |

**So the two roots are not the same kind of read, and every figure below is labelled accordingly.** MNQ is §M28.16's book with a handful of revised bars in it — profit factor moves by at most 0.0008. NQ gained history *earlier* than its tail, which moved the 60/40 split and which no truncation recovers, so its ten configurations are read on today's holdout. That is still a held-out read and not a leak: today's split point is 2024-10-14 and the selection window those ten were chosen on ended 2024-09-25, so the choice was made strictly before the bars it is measured on. It is simply not §M28.16's window, and its levels are this run's.

## The exclusion read: the first cell in the registry that survives it at all

`tools/campaign_exits.py --rerun`, the held-out book with the `session_close` legs removed. `survives` is both gate-4 thresholds at once — residual profit factor above 1.0 **and** residual net-to-drawdown above 1.0.

| root | median PF | without those legs | median net | without those legs | PF > 1 without them | survives |
| ---- | --------- | ------------------ | ---------- | ------------------ | ------------------- | -------- |
| MNQ  | 1.482     | **0.975**          | +39,131    | −1,680             | **5 of 10**         | 2 of 10  |
| NQ   | 1.316     | **0.939**          | +335,997   | −38,190            | **4 of 10**         | 3 of 10  |

**Nine of the twenty configurations are profitable without the forced flat.** Every previous run of this read returned zero: §M28.15's midday OpeningRange cell is 0 of 40 at 1.216 → 0.371, and §M31.1's gate-3 survivor is 0 of 20 at 1.430 → 0.238. This cell's median falls from 1.482 to 0.975 — it still loses the argument at the median, and it is the first one to win it anywhere.

## One bracket axis separates every survivor from every failure, and it is a different axis on each root

The nine are not scattered. On each root a single swept parameter partitions the ten exactly.

**MNQ — `partial_take_profit_percentage`.** Five configurations take 60% of the position off at one R and five take 50%; the rest of the grid varies freely across both halves.

| `partial_take_profit_percentage` | n   | residual PF | residual net     | residual net/drawdown | flatten net   | survives |
| -------------------------------- | --- | ----------- | ---------------- | --------------------- | ------------- | -------- |
| **0.6**                          | 5   | 1.080–1.243 | +5,128 – +13,507 | 0.373–1.465           | 26,725–28,896 | 2 of 5   |
| 0.5                              | 5   | 0.786–0.870 | −8,488 – −15,648 | −0.416 – −0.705       | 51,489–53,165 | 0 of 5   |

**Ten of ten sort on it**, and the mechanism is visible in the flatten column rather than inferred: banking six tenths of the position at the target instead of five leaves less of it running into the close, so the flatten carries about half as much money and what the bracket did stands on its own.

**NQ — `trailing_stop_multiplier`.** Four configurations trail at 5× the inside bar's range and six at 10×.

| `trailing_stop_multiplier` | n   | `session_close_share` | residual PF | residual net       | survives |
| -------------------------- | --- | --------------------- | ----------- | ------------------ | -------- |
| **5.0**                    | 4   | 0.229–0.243           | 0.902–1.708 | −63,310 – +354,090 | 3 of 4   |
| 10.0                       | 6   | 0.468–0.481           | 0.601–1.016 | −241,434 – +8,038  | 0 of 6   |

**Ten of ten sort on this one too**, and it is the same mechanism from the other end: the looser trail is hit far less often, so twice as many legs reach the clock. It is also what produced §M28.16's `session_close_share` range of 0.229–0.481 on NQ — that spread is two halves of the shortlist, not a distribution.

**This is a post-hoc reading of ten rows per root and it was found by looking at the table.** Neither axis was nominated in advance, the two roots name different parameters, and each split is a single grid axis inside a shortlist already chosen on profit factor. What it is good for is naming the thing to pre-register and test next, not for concluding that 0.6 and 5.0 are the settings to trade.

## Monte Carlo: the first bootstrap floor in the registry above a profit factor of 1.0

`tools/campaign_montecarlo.py --held-out --rerun`, 1,000 resamples of each configuration's own trades.

| root | observed PF (median) | bootstrap p05 PF | above 1.0    | bootstrap p05 net above zero | resamples that lose money |
| ---- | -------------------- | ---------------- | ------------ | ---------------------------- | ------------------------- |
| MNQ  | 1.482                | 1.030–1.156      | **10 of 10** | **10 of 10**                 | 0.5%–3.7%                 |
| NQ   | 1.316                | 0.884–1.229      | 4 of 10      | 4 of 10                      | 0.3%–14.2%                |

**This is what [#345] pre-registered as the thing nothing in the project had ever done.** §M28.15 is 0 of 40 and §M31.1 is 1 of 20; here every MNQ configuration's 5th percentile clears a profit factor of 1.0 and zero net at once, and a median of 1.5% of resamples loses money against the registry's usual one in eight.

**The NQ four are the `trailing_stop_multiplier = 5.0` four**, at 1.174–1.229 against the 10× half's 0.884–0.960 — the same partition as the exclusion read, reached by a different instrument.

**The permutation test is the one reading that is worse than §M28.15's.** Reordering the same trades puts p at 0.231–0.554 on MNQ and 0.200–0.551 on NQ, so nothing here is significant — but the observed drawdown sits *above* its own null median on **18 of the 20**, where §M28.15's midday cell sat below on 30 of 40. Reshuffling these books tends to improve the equity path rather than worsen it. At these p-values that is a direction and not a finding, and it is the opposite direction from the cell this one is being compared with.

## Walk-forward: passes on both roots, and the last fold is the strongest

`tools/campaign_walkforward.py`, five sliding folds, selection on train and measurement on test. **This read runs its own folds over the whole series and reads no stored log**, so it ran on today's archive on both roots — 345,742 MNQ bars and 339,384 NQ bars through 2026-09-16.

| root | train median | test median | **pooled test** | folds profitable | test trades/fold | distinct combos chosen | passes |
| ---- | ------------ | ----------- | --------------- | ---------------- | ---------------- | ---------------------- | ------ |
| MNQ  | 1.330        | 1.381       | **1.439**       | 4 of 5           | 68–79            | 3                      | yes    |
| NQ   | 1.451        | 1.526       | **1.451**       | 5 of 5           | 66–75            | 2                      | yes    |

**The weak fold is the same window §M31.1's was** — the one ending 2025-03, at 0.995 on MNQ — and NQ has no losing fold at all. **The final fold is the strongest on both roots**, 1.665 and 1.936 over 2026-03 to 2026-09, which is the reverse of §M28.15, where the last fold was the weakest on both roots and §M28.10's collapse was what that meant. It is also the fold that runs furthest into the bars added on 2026-09-16, so it is the least comparable of the five to anything measured before that date.

**Three folds each choose the same configuration and two roots pick between three and two of them**, so what the folds test is picking within a ten-row pool rather than a selection worth the name — the same limit §M28.15 recorded.

## What [#345] asked, answered

1. **The excess survives the exclusion, in part and for the first time.** Nine of twenty configurations are profitable without their session-close legs where every earlier run of this read returned none, and five of twenty clear both gate-4 thresholds. The median configuration still does not, so this is not "the result is not the account rule" — it is "this is the first cell where that is a question with a positive answer in it".
2. **Gate 4 is cleared in full on MNQ by the bootstrap and not by the exclusion.** All ten MNQ configurations put a 5th percentile above a profit factor of 1.0 and above zero net, which nothing in the project's history had done; 2 of those 10 also survive the exclusion. The walk-forward passes on both roots.
3. **On the epic's first decision this is the better candidate, not the disqualified one.** [#344] settled that a forced-flat-dependent result is not discounted; this cell is the least flat-dependent thing in the registry either way, and the axis that decides it is bracket geometry that a port would have to set anyway.

## What this does not settle

- **The levels are this run's, and on NQ the window is too.** MNQ reproduces §M28.16's book to within $63 on $33,000–$43,000; NQ is the same ten configurations on a holdout that moved by three weeks at the front and five at the back. Quote §M28.16 for gate 3 and this file for gate 4, and do not mix the two roots' NQ figures with that section's.
- **The exclusion is a decomposition, not a counterfactual**, exactly as §M28.12 and §M28.15 state it. A leg the clock closed is a leg the trail did not take, and these bars do not say where it would have gone. What is new is only that the residual book stands up on nine of twenty rows rather than none.
- **The two separating axes are post-hoc and they disagree across the roots.** Ten rows per root, chosen on profit factor, with the split found by reading the table. Nothing here tests whether `partial_take_profit_percentage = 0.6` or `trailing_stop_multiplier = 5.0` survives being the thing selected on.
- **Gate 3 has not been re-run.** §M28.16's null stands as measured on the bars it was measured on; this adds gate 4 beside it. A re-run of `tools/campaign_null.py` over this cell today would be refused on NQ for the same reason the log store was.
- **The prop-account replay is not here.** It is [#347]'s, which ranks both midday candidates on `days_to_payout` and `fees_per_pass` rather than on profit factor, and §M40 is why that is a different question from this one.
- **Five folds of one stratum at one bar size is not a walk-forward of the archetype**, and 66 to 79 test trades per fold is where a pooled 1.44 comes from.
- **One cell, one resolution, ten configurations per root.** The unfiltered stratum, where this archetype's session-close share runs much higher, is untouched by any of it.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/InsideBarTrailing.duckdb` plus `tools/campaign_exits.py --rerun`, `tools/campaign_montecarlo.py --held-out --rerun` and `tools/campaign_walkforward.py` — not a standing property.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#345]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/345
[#347]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/347
