---
id: M28.9
title: "M28.9 — the survivor, read for tradeability rather than for rank"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [261, 262, 263, 264]
gates: [4]
outcome: mixed
verdict: >-
  Held out, one cell in thirteen across the registry returns its own drawdown; the binding constraint is net-to-drawdown rather than profit factor, and the edge is absent from 2026.
---

# M28.9 — the survivor, read for tradeability rather than for rank ([#261], [#262], [#263], [#264])

**No new campaign.** Every figure here comes from §M28.8's own stored rows plus one single-configuration re-run, and four findings came out of reading them for a different statistic.

**The statistic is not new and this section does not claim it is.** `campaign_report.NET_TO_DRAWDOWN` is Gate 4's own ranking, `ratio_to_drawdown` has been its definition since §M27.3, and `campaign_holdout` has reported `hold_top20_ntd` beside a `clears_drawdown` column for as long. Gates 1 to 3 are expressed in **profit factor**, so a configuration can pass all three while returning less than its own worst peak-to-trough — but Gate 4 was built to catch exactly that. What had not been done is reading it **across the registry in one place**, which is all the table below is.

Two things this section does not claim. It does not rank anything — the shortlists below are §M28.8's, unchanged. And it does not retire OpeningRange; § "Parked is not abandoned" governs, and [#261] is what would settle the question either way.

## One archetype in seven returns its own drawdown

`tools/campaign_holdout.py` over every registered archetype, unfiltered stratum, shortlist ranked on profit factor as the campaigns rank it. The column is the tool's own `hold_top20_ntd` — the median of `net_to_drawdown` across the twenty, not a ratio of medians — beside the `clears_drawdown` boolean it already computes:

| archetype         | MNQ        | NQ         | clears |
| ----------------- | ---------- | ---------- | ------ |
| InsideBar         | 0.468      | **1.022**  | NQ     |
| InsideBarTrailing | 0.328      | 0.196      | no     |
| EmaCrossover      | 0.059      | −0.414     | no     |
| DeadCatBounce     | −0.292     | −0.259     | no     |
| PullBackAndGo     | −0.572     | −0.527     | no     |
| ElasticBand       | −0.583     | −0.633     | no     |
| OpeningRange      | *unusable* | *unusable* | —      |

**One cell of thirteen clears, and six of seven archetypes return less than nothing.** OpeningRange's unfiltered row comes back at 264.7 and 269.2 because the pooled shortlist ranks straight into the `ambiguous_share` corner §M28.7 found — [#248]'s hazard and [#263]'s dilution arriving in the same cell, and the reason the confined figures elsewhere in this section carry a readability filter the tool does not apply.

**The grids are drawn short, and the geometry beyond them only sometimes survives being chosen.** That second clause is the whole of it, and it is narrower than "the grids are the constraint".

Twice now a bracket parameter the main campaign could not reach has produced net-to-drawdown above 1.0, and **the two instances are not the same kind of result**:

- **§M27.3's target multiplier is reachable and not selectable.** Its 1.458 is a median *pooled over the stop, the resolution and the six strata* at `tp_multiplier=1.5` on **MNQ only** — NQ is 0.771 there, and 2.0 is the multiple that clears both at 1.434 / 1.123. It is not a shortlist's `hold_top20_ntd` and does not compare with the 0.468 in the table above. Worse for the precedent, §M27.3's own measurement is that the axis **reverses**: the holdout's ridge is 1.5–2.0, the selection window's is 5.0–6.0, and the rank correlation runs +0.194 selection against −0.455 holdout. Its verdict is the sentence to quote — *"the geometry that clears Gate 4 exists inside the grid and the selection window will not hand it to you"* — and re-measured through Gate 4 it still passes only 1 of 12 cells.
- **§M28.10's stop scale is both, and it is the number rather than the protocol that says so.** §M27.3's narrow grid was ranked on the selection window and tested on the holdout too, and still reversed — so "ranked then tested" establishes nothing on its own, and any argument of that shape is worth no more than §M27.3's was. What separates them is the rank correlation across the split: **0.82 to 0.90** on the clearing arms against §M27.3's **−0.161**, with held-out profit factor above the selection window's in seven of the eight cells and level in the eighth (`both@20` runs 1.210 → 1.248 on MNQ and 1.173 → 1.225 on NQ, 20 of 20 profitable). **Selection does not decay here**, which is the property §M27.3's target multiplier lacks and the only thing that makes the two comparable at all.

So the pattern is real and its useful form is a **question rather than a precedent**: when [#262] extends the truncated `stop_range_fraction`, does it behave like the target multiplier and reverse, or like the stop scale and hold? That is what [#262]'s stated acceptance cell is for, and it is why the answer cannot be read off a pooled holdout median.

[#75] is still what turns any of this into a fundable answer — it replays account rules over a trade log rather than reporting one ratio — which is why it moved to the front.

**[#261] then found cells that clear it comfortably, and they belong to [#262]'s axis rather than to the one that found them.** §M28.10 has the per-arm table and it is not restated here; what matters to this section is which half does the work. Every arm that clears has the **stop** half switched on and no `target`-only arm clears, while §M28.10 measures the tracking itself as worth −0.004 against a constant stop of the same size with the matched null rising alongside it. **So what clears the bar is the stop *level*, not the normalisation** — which is the selectable instance in the pair above, and what makes [#262]'s truncated `stop_range_fraction` the cheapest thing outstanding.

§M28.10 records one caveat that travels with it and is not small: the clearing arms exit at the forced flat on 0.476 to 0.586 of their shortlisted legs against the control's 0.299, so the drawdown they return is bought with roughly twice the reliance on the flatten. It does not order them — the highest close share of the ten is `both@250` at 0.618, whose net-to-drawdown is 0.459 — but it is the same reliance the bracket decomposition below measures, arriving on the arm that looks best.

§ "Standing traps" on choosing the best of twenty still binds: agreement across two roots is the guard, and it is not the same as pre-registering.

Two smaller readings, both on the confined survivor and InsideBar's readable shortlist rather than on the table above. **Diversification is real and insufficient**: daily P&L correlation between the two is 0.101 on the held-out window, genuinely uncorrelated, and a 50/50 blend still returns 0.73 against the opening range's 0.79 alone, because InsideBar's readable ratio is 0.41. **Cost sensitivity is mild**: two ticks of slippage rather than one moves the opening range's held-out profit factor from 1.124 to 1.115 and InsideBar's from 1.068 to 1.061, so nothing here is a cost artefact.

## The pooled shortlist dilutes, and two of the four gate tools cannot be told not to

§M28.8 named this from the null's side — *"a shortlist drawn over a mixture of geometries dilutes the one that works"*. It is visible on gate 2 in the same rows:

| ranking pool                                    | selection PF | holdout PF |
| ----------------------------------------------- | ------------ | ---------- |
| pooled over all 472 variants, NQ                | 1.609        | **0.940**  |
| confined to `cash-open+30m entry=breakout`, MNQ | 1.235        | 1.137      |

The pooled arm does not hold out at all. `campaign_holdout.py` and `campaign_null.py` both took `--variant`; **`campaign_walkforward.py` and `campaign_montecarlo.py` did not, and passed seven positional arguments to `shortlist()` that stopped at `resolution`.** So gate 4 — the gate OpeningRange is currently stopped at — had been ranking across the mixture by construction ever since the database grew past one variant, and **every gate-4 figure taken before [#263] is a pooled one**. On the stored rows today the pooled top 20 draws from four variants on MNQ and eight on NQ, and on the holdout window it lands almost entirely in the corner §M28.7 found — `ambiguous_share` median 0.893 and 0.925, against 0.004 and 0.005 for the same shortlist confined to one variant.

**`campaign_report.py` stays pooled and takes no `--variant`**, which is the other half of [#263] and not an oversight. The dilution above is a *selection* effect — a shortlist drawn over a mixture ranks the fattest tail in it — and `campaign_report` selects nothing: it reports medians, profitable shares and eta² over every stored row, and already cuts a `by variant, unfiltered only` table wherever more than one is stored. Confining it would narrow the distribution the dimension tables exist to describe and hide the mixture the shortlisting tools now have to be told to avoid. The one table there that does rank — `top 5 by profit factor` — carries the caveat in its own title and names the variant in a column.

## The bracket is a net cost, which `session_close_share` cannot say

`campaign_report` counts exits by reason. It does not report what they were worth, and on the survivor the two answers point opposite ways. The confined configuration over the full window, MNQ, 4 contracts, at the root's real commission and one tick of slippage:

| exit reason     | legs | net P&L      | median bars held |
| --------------- | ---- | ------------ | ---------------- |
| target          | 313  | +134,079     | 118              |
| stop            | 577  | **-264,631** | 83               |
| `session_close` | 790  | **+183,020** | 396              |

**The bracket legs together net -130,552**, and the whole of the configuration's +52,468 is the forced flatten. The median surviving trade is held 396 bars — six and a half hours — so this is a day-long directional hold wearing a bracket, not the breakout scalp the archetype's name suggests. Per leg the split is even: the bracketed lot returns +26,754 and the runner +25,714.

`session_close_share` for these rows is 0.53, which reads as the caveat §M28.1 already recorded. The decomposition is a **stronger and different claim**, and it is what pointed at the stop axis.

**It is a decomposition and not a counterfactual.** A leg that reached the close is a leg the stop did not take, so these columns cannot be read as "remove the bracket and keep the 183,020". What they support is the weaker and sufficient statement that the bracket as configured does not pay for itself. [#264] adds the columns.

## Two axes were never swept to their end

`ORB_FRACTIONS` is `[0.25, 0.5, 0.75, 1.0]` and **1.0 wins on both roots and both windows** — 0.833 / 0.875 at the tightest against 1.151 / 1.173 at the widest on the two holdouts, monotone across both selection windows. An axis whose best value is its last value has not been swept. Separately, `_orb_further_targets` hands `target=width` the parameter default `(1.0, nan)` on every cell of every ORB campaign to date, so **the width target has never been varied at all** and §M28's reading of the target axis rests entirely on the R scheme.

Re-run past the boundary, held-out profit factor and net-to-drawdown, MNQ / NQ:

| `stop_range_fraction` | ladder     | holdout PF        | net / drawdown  |
| --------------------- | ---------- | ----------------- | --------------- |
| 1.0 — the grid's edge | (1.0, nan) | 1.124 / 1.149     | 0.79 / 0.89     |
| 3.0                   | (1.0, nan) | 1.200 / 1.223     | 1.18 / 1.28     |
| **5.0**               | (1.0, nan) | **1.228 / 1.252** | **1.43 / 1.54** |
| 5.0                   | (nan, nan) | 1.190 / 1.215     | 1.21 / 1.33     |

Two results that have to be kept apart. **The stop is a cost across the whole tested range** — at 5.0 it fires so rarely that `session_close_share` reaches 0.81, and that is still the best cell. **The target is not**: `(1.0, nan)` beats the tighter, the wider and the no-target ladder on the holdout at every stop width on both roots, while `(nan, nan)` wins on both *selection* windows. Ranking on the selection window picks the target scheme wrong, which is a second small finding about the instrument.

**The acceptance cell is 2022 and not the pool**, because part of that gain is a rising tape. In the one falling year in the sample the wide stop returns the same P&L for two and a half times the drawdown — -8,001 at `stop_range_fraction` 1.0 against -18,467 at 3.0 and -20,357 at 5.0. A configuration that earns its held-out figure by removing the stop from a tape that went up has learnt the tape. [#262].

## 2026, and the quantity the geometry is denominated in

The confined survivor, per year, at the stored `stop_range_fraction` of 1.0:

| year     | profit factor | net P&L | max drawdown |
| -------- | ------------- | ------- | ------------ |
| 2022     | 1.144         | 9,576   | -8,001       |
| 2023     | 1.214         | 9,406   | -5,544       |
| 2024     | 1.252         | 12,040  | -7,669       |
| 2025     | 1.262         | 17,197  | -6,694       |
| **2026** | **1.008**     | **441** | **-22,625**  |

**The most recent eight months are flat with the largest drawdown in the sample**, and 2026 holds 156 sessions to the end of the archive, so this is a year that traded rather than thin coverage. It is not the bracket: every stop width is at or below breakeven there, 0.992 at 3.0 and 1.069 at 5.0.

Nor is it the scale of the target, and that is the useful part. The obvious reading — a target denominated in range widths has grown too far away to be reached — predicts that tightening it helps. Measured at multiples of 0.33, 0.5 and 0.75 against 1.0's 1.008, the year returns **0.959, 0.949 and 0.999**. Tightening the target makes 2026 worse.

What did change is the archetype's own environment. Median 30-minute cash range, and follow-through — the further of the two extensions beyond the range, over the range width — per year on MNQ:

| year | median 30m range | median follow-through |
| ---- | ---------------- | --------------------- |
| 2022 | 122.6            | 1.158                 |
| 2023 | 78.8             | 1.105                 |
| 2024 | 91.5             | 1.168                 |
| 2025 | 124.1            | 0.994                 |
| 2026 | **182.4**        | **0.921**             |

**The range has more than doubled since 2023 while price now travels less than one range width beyond it.** Both halves of the bracket are denominated in the quantity that moved, and the edge was fitted where follow-through sat near 1.15.

The standing caution binds and is not small: follow-through per year is five numbers, and a mechanism that explains one bad year after the fact is the easiest thing in this project to find. Two things separate this from that failure — the mechanism was read off the range statistics rather than off the P&L, and the competing explanation it displaces made a prediction that was tested and lost. It is a hypothesis with a failed rival, not a finding. [#261] is what would settle it, by asking whether a geometry normalised against *trailing* follow-through restores the year.

## The verdict

- **The one configuration through three gates is not tradeable as it stands**, and the binding constraint is net-to-drawdown rather than profit factor. Gate 4 does measure that and `clears_drawdown` does report it; what no campaign had done is read the column across the registry at once, which is the only thing the table above adds.
- **Its recent behaviour is the open question and its bracket is the cheap one.** [#261] decides whether the space is still live; [#262] and [#263] are small and improve whatever [#261] measures; [#264] is the column that would have caught the bracket several campaigns earlier.
- **A negative answer on [#261] is a result.** An archetype calibrated to a regime that has ended is a verdict worth more than another campaign, and it parks a configuration space without retiring the archetype.
- **`OpeningRange` is still `TIER1_ONLY`.** It is the only archetype ever to pass gates 1 to 3 and **no leg of it has been diffed against an NT8 trade list** — its stop-market entry, its measurement from the trigger rather than the fill, and its re-arming order lifetime are all unevidenced parts of the fill model. § "Standing traps", *"one archetype cannot exercise the fill model"*. [#265] is that export, and it gates the C# rather than following it.

Every figure above is a measurement of one dated run against the archive as it stands, re-derivable from `results/campaign/*.duckdb` and a single-configuration re-run — not a standing property.

[#248]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/248
[#261]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/261
[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
[#263]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/263
[#264]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/264
[#265]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/265
[#75]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/75
