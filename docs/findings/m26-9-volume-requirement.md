---
id: M26.9
title: "M26.9 — a volume requirement on the break: the state it asks for is the one that costs"
archetypes: [ElasticBand]
issues: [281]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  A `HEAVY` requirement is a cost on both roots under all three forms; `NORMAL` is the state that helps, which is the second archetype to answer the volume question that way.
---

# M26.9 — a volume requirement on the break: the state it asks for is the one that costs ([#281])

**What has changed since §M26.5, stated first.** No condition and no code: `volume_filter` has gated the signal bar through `sim/filters.py` since §M10.2, and §M27.8 swept the volume dimension across the whole registry. What is new is the pairing — the volume states crossed with the signal-bar shape §M26.5 carried forward, over one held bracket, with the no-requirement control in the same pass. [#221]'s wording was *"break of bands need to have a certain level of volume (absolute or relative) for the signal to be valid"*, and §M26.5 read that as `HEAVY` on the signal bar.

**The absolute half of that question was settled in §M10.2 and is not reopened here.** Absolute volume is carried for reporting and never filtered on, because a contract count means different things in 2021 and 2026 and is not comparable across roots; §M27.8's absolute table is what that half gets. What was open is whether requiring volume does anything the shape does not already do — both are ways of asking whether the extension was real, so §M26.5 predicted they might be the same cut twice, which is what it found for the one-sidedness count against `entry_std`.

## Count the signals before crossing, and the two cuts are not the same one

Selection window, VWAP band, `entry_std = 2.0`, `min_bars_outside = 1`, one-minute bars, each form's thresholds fitted on that window. **MNQ signals on 91,729 of 998,093 bars unfiltered and 30,916 with the reversal shape (33.7%); NQ on 80,690 of 980,076 and 26,657 (33.0%).** Share of those signal bars sitting in `HEAVY`, and what the shape does to it:

| form            | tail      | MNQ any | MNQ reversal | lift | NQ any | NQ reversal | lift |
| --------------- | --------- | ------: | -----------: | ---: | -----: | ----------: | ---: |
| per bar         | 0.10/0.90 |   20.9% |        15.5% | 0.74 |  23.6% |       17.5% | 0.74 |
| per bar         | 0.20/0.80 |   35.6% |        29.8% | 0.84 |  39.1% |       33.1% | 0.85 |
| per bar         | 0.33/0.67 |   51.0% |        46.3% | 0.91 |  54.7% |       49.5% | 0.90 |
| rolling 30      | 0.10/0.90 |   16.7% |        18.0% | 1.08 |  19.7% |       21.8% | 1.11 |
| rolling 30      | 0.20/0.80 |   31.7% |        34.3% | 1.08 |  34.9% |       38.1% | 1.09 |
| rolling 30      | 0.33/0.67 |   47.4% |        50.6% | 1.07 |  50.8% |       54.4% | 1.07 |
| session to date | 0.10/0.90 |    7.0% |         7.0% | 0.99 |   6.7% |        6.6% | 0.99 |
| session to date | 0.20/0.80 |   15.3% |        15.4% | 1.00 |  15.3% |       15.2% | 0.99 |
| session to date | 0.33/0.67 |   27.9% |        28.1% | 1.01 |  27.3% |       27.5% | 1.01 |

**The unfiltered entry is already a heavy-volume rule under the per-bar form, and nobody chose that.** A tenth-tail admits 9.9% of all bars and 20.9% of MNQ's signal bars — a 2.1× enrichment, 2.4× on NQ — because a close 2σ outside a session VWAP band is a bar that traded. Under the session-to-date form the same signal is *under*-represented in `HEAVY`, 7.0% against 9.9%. The three forms disagree about whether this is a busy-market entry at all, which is §M10.2's decomposition finding arriving a third time.

**The shape moves that enrichment the wrong way for the hypothesis.** Requiring the signal bar's own body to have turned *lowers* the share in `HEAVY` under the per-bar form — 0.74× at the tenth tail on both roots — and leaves it alone under the other two. A bar that closed back towards the basis stopped extending, and the contracts follow the extension. So it is not the same cut twice: under the per-bar form the two pull in opposite directions and under the session-to-date form they are very nearly independent.

**The shape is far cheaper on this channel than §M26.5's table shows**, and the two numbers are not comparable. That table is the Bollinger band, where `reversal` costs 93% of the signal; on the VWAP band it costs 66%. The VWAP basis is session-anchored and its width shrinks through a session, so the population of 2σ closes is a different one — read a signal count against the channel it was measured on.

## The campaign, and the axes held still to make room for the cells

**20,160 rows**: `shape=any` and `shape=reversal` as two variants over one bracket, each crossing `entry_std` × `stop_mode` × `max_hold_bars` at 18 combinations, across the unfiltered stratum and 27 volume cells — three forms × three tail sizes × three states — on both roots, resolutions 1/2/5/10/15, split 60/40 into a selection and a held-out window, at the root's own commission and one tick of slippage. `--variants elastic-volume --strata elastic-volume --volume-quantiles --split`.

**Three of §M26.5's five axes are held rather than swept**, so that what this pass adds is the volume strata and not a wider grid: `min_one_sided_bars` because §M26.5 measured its low end as a dead value and its high end as a cost, `min_bars_outside` because the reversal shape makes it a duplicate on 82.7% of cells, and the target ladder at `0.0σ` because its η² on the held-out profit factor there was 0.0000. The cut is `volume.thresholds_from_quantiles`, fitted per (root, resolution, form) on the selection window alone with the tail size in the cell name, for the reason §M27.8 gives: 0.7/1.5 admits 28% of bars under one form and 8% under another, so cells cut by a raw pair cannot be read against each other.

**77.4% of rows clear 30 trades, and the crossing is what spends the rest.** Under `shape=any` it is 93% and under `shape=reversal` 62%; on the held-out window it falls from 0.99 of rows at one minute to 0.34 at fifteen for `NORMAL`, and 0.96 to 0.27 for `HEAVY`. Two entry gates in conjunction is the sample cost §M26.5's own rule warns about, met as predicted rather than discovered.

## Paired, cell by cell: the requirement is a cost and its complement is not

Median change in profit factor against the **unfiltered stratum** at the same root, resolution, form, tail and axis values, both arms clearing 30 trades. The last column counts how many of the nine form × tail cuts have a median above zero:

| window    | shape    | state  | root | pairs | median ΔPF | wins  | cuts favourable |
| --------- | -------- | ------ | ---- | ----: | ---------- | ----- | --------------- |
| holdout   | reversal | HEAVY  | MNQ  |   526 | **−0.056** | 28.9% | **0 of 9**      |
| holdout   | reversal | HEAVY  | NQ   |   470 | **−0.081** | 22.3% | **1 of 9**      |
| holdout   | reversal | NORMAL | MNQ  |   578 | **+0.071** | 74.7% | **9 of 9**      |
| holdout   | reversal | NORMAL | NQ   |   534 | **+0.043** | 63.3% | **8 of 9**      |
| holdout   | reversal | THIN   | MNQ  |   402 | −0.083     | 38.1% | 2 of 9          |
| holdout   | reversal | THIN   | NQ   |   375 | +0.023     | 54.4% | 5 of 9          |
| selection | reversal | HEAVY  | MNQ  |   526 | +0.026     | 58.2% | 5 of 9          |
| selection | reversal | HEAVY  | NQ   |   492 | −0.000     | 49.8% | 5 of 9          |
| selection | reversal | NORMAL | MNQ  |   628 | −0.006     | 46.8% | 4 of 9          |
| selection | reversal | NORMAL | NQ   |   562 | +0.012     | 56.0% | 7 of 9          |

**`HEAVY` is a cost on 17 of the 18 held-out cuts and `NORMAL` a gain on 17 of 18**, on both roots and under all three forms. That is the answer to what [#281] asks, and it is the opposite of what it expected: the state the requirement names is the one that loses, and the state that is not an extreme at all is the one that pays. It is not a thin-sample artefact either — under the per-bar form `HEAVY` is the state with the *most* signal bars behind it.

**The selection window cannot see any of it.** Both states sit at a coin flip there, and `HEAVY`'s median is the positive one on MNQ — so a shortlist drawn on the selection window would have picked the requirement, and the requirement is what costs on the holdout. The sign is a property of the second window exactly as §M26.5's shape result was, and it carries the same warning: this is the period rather than the rule until something separates them.

**The control says the two conditions compose rather than duplicate.** Under `shape=any` the same split is several times weaker — `HEAVY` at −0.013 on MNQ and +0.003 on NQ, `NORMAL` at +0.023 and +0.007, four to six of nine cuts either way on every state. The volume state does most of its work only once the shape is required, which is not what two readings of one move look like.

## Held out, where `NORMAL` is the only stratum that returns its own drawdown

Best 20 on the selection window measured on the held-out one, **within each stratum**, for the reversal arm. Counts are over the nine form × tail cuts of each state:

| stratum    | root | passes | clears drawdown | hold top-20 PF | hold all-cell PF | paired cells |
| ---------- | ---- | ------ | --------------- | -------------- | ---------------- | ------------ |
| unfiltered | MNQ  | 1 of 1 | **0 of 1**      | 1.371          | 1.186            | 72           |
| unfiltered | NQ   | 1 of 1 | 1 of 1          | 1.481          | 1.104            | 66           |
| HEAVY      | MNQ  | 5 of 9 | **1 of 9**      | 1.128          | 1.042            | 60           |
| HEAVY      | NQ   | 4 of 9 | **0 of 9**      | 1.083          | 1.023            | 54           |
| NORMAL     | MNQ  | 9 of 9 | **9 of 9**      | **1.635**      | 1.215            | 66           |
| NORMAL     | NQ   | 8 of 9 | **7 of 9**      | **1.337**      | 1.171            | 58           |
| THIN       | MNQ  | 7 of 9 | 0 of 9          | 1.140          | 1.005            | 46           |
| THIN       | NQ   | 7 of 9 | 3 of 9          | 1.270          | 1.153            | 44           |

Every figure in the last four columns is the median over that state's nine cuts.

**Sixteen of the eighteen `NORMAL` cells return their own drawdown held out**, against §M28.9's registry-wide rate of one cell in thirteen and against `HEAVY`'s one in eighteen. The unfiltered baseline of this grid fails that check on MNQ and clears it on NQ, so it is not the baseline being carried through; under `shape=any` the same `NORMAL` count is 7 of 18, which is the composition result again from the other side.

**Read the eighteen as eighteen tests and not as one.** Fifty-six held-out tests were run per arm, so a consistent sign across the nine cuts of one dimension is what makes the `NORMAL` column readable — the individual profit factors in it are a best-of-sixty and are not.

## The matched null, where the two roots part

Top twenty ranked on the selection window and run against `randomentry.compare` on the holdout — 200 draws, entry days randomised, geometry and direction held. The cut is `per_bar_20` at `0.20/0.80`, **named before the run** as the middle tail of the form §M27 itself ran rather than picked out of the tables above:

| root | stratum    | median PF | median null PF | median excess | *p* < 0.05 on PF | on expectancy | median trades |
| ---- | ---------- | --------- | -------------- | ------------- | ---------------- | ------------- | ------------- |
| MNQ  | unfiltered | 1.313     | 0.916          | +0.453        | 3/20             | 6/20          | 81            |
| MNQ  | NORMAL     | **1.591** | 0.881          | **+0.677**    | **14/20**        | **15/20**     | 65            |
| MNQ  | HEAVY      | 1.124     | 0.904          | +0.234        | **1/20**         | 4/20          | 76            |
| NQ   | unfiltered | 1.229     | 0.949          | +0.248        | 9/20             | 12/20         | 386           |
| NQ   | NORMAL     | 1.229     | 0.926          | +0.285        | 5/20             | 5/20          | 234           |
| NQ   | HEAVY      | 1.070     | 0.980          | +0.101        | **1/20**         | 6/20          | 156           |

**The null does not move and the observation does**, which is §M26.5's reading holding on a second grid: 0.88 to 0.92 across every stratum on MNQ and 0.93 to 0.98 on NQ, so the bracket is doing the same thing on the same bars whatever the volume cell. The MNQ unfiltered row also reproduces §M26.5's own best cell closely enough — 1.313 against 1.526, +0.453 against +0.645 — that holding three axes did not throw the archetype away.

**`HEAVY` fails gate 3 on both roots and fails it below the baseline it was meant to beat**, at 1 of 20 on profit factor against the unfiltered arm's 3 and 9. That is the third instrument in a row saying the same thing about the requirement [#281] asked for.

**`NORMAL` gives this archetype its strongest MNQ null result and nothing at all on NQ.** 14 of 20 on profit factor is the highest count either root has produced here — §M26.5's best was NQ's 12 — and 15 of 20 on expectancy sits just under its 16, which also came from NQ; MNQ had produced 4 and 6 there and produces 3 and 6 as the control here. On NQ the state is *worse* than that control — 5 of 20 against 9, 5 against 12 — for a 39% smaller sample and an excess barely above it. **One root is not a finding**, and this is the shape §M27.4 warns about: a genuine improvement on MNQ, and on this evidence an even trade at best on NQ.

## What this settles, and what it leaves

- **[#221]'s volume idea is measured and it does not work as asked.** A `HEAVY` requirement on the break is a cost on both roots, under all three forms, at all three tail sizes, on the paired holdout, the held-out gate and the matched null alike.
- **It is the second archetype to answer the volume question with `NORMAL`.** §M27.8 found the same for InsideBar — *"`NORMAL` — the state that is not an extreme at all — is the best cell under two of the three forms at every tail"* — from a campaign that was asking which extreme helps. Two archetypes with opposite theses agreeing on the middle state is worth more than either result alone, and it is the thing to state about relative volume here.
- **The volume state and the signal-bar shape compose**, which is what [#281] asked and §M26.5 doubted. They are near-independent cuts under two of the three forms and mildly opposed under the third, and the state's paired effect is several times larger once the shape is required.
- **It is not a promotion and [#170] is no closer.** Everything §M26.5 owed is still owed — the sample size, the window dependence, the unpinned VWAP basis, every figure being off the back-adjusted continuous series rather than per contract — and this adds two: the sign of the volume effect is invisible on the selection window, and the null splits by root.
- **The campaign runs one state per cell, so "at least normal" was never tested.** `volume_filter` is a bitmask and `NORMAL | HEAVY` is a legal value, but `_volume_cells` yields one state per cell by construction — a blind spot of the stratification rather than of any axis, now recorded in `.claude/rules/sweep-and-context.md`. Given that `NORMAL` alone beats both the baseline and `HEAVY`, a union containing `HEAVY` is not the cell worth running; the point is that nothing in the table would have said so.

[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
[#281]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/281
