---
id: M28.11
title: "M28.11 — the two truncated bracket axes, swept to their end"
archetypes: [OpeningRange]
issues: [262]
gates: [2, 3, 4]
outcome: negative
verdict: >-
  Both axes are now swept to their end: the wider stop fails the acceptance cell, costs two thirds of net-to-drawdown, and lowers the excess over a permuted range as `session_close_share` doubles.
---

# M28.11 — the two truncated bracket axes, swept to their end ([#262])

[#262] named two axes nothing had measured. `ORB_FRACTIONS` ended at `1.0` and `1.0` won on both roots and both windows, so the stop was truncated rather than swept; and `target_width_multiples` is in `OpeningRange`'s `not_sweepable` set, so every ORB campaign to date ran `ORB_TARGET_WIDTH` at the parameter default `(1.0, nan)` and no axis could ever have reached it. `--variants orb-bracket` carries the first out to `5.0` and makes the second a variant dimension, over the two ranges §M28.8's gate 3 separated.

**Three separable answers, and they do not point the same way.** The stop axis was genuinely truncated and extending it raises pooled held-out profit factor and net-to-drawdown; it **fails the acceptance cell [#262] stated in advance**, costs the entry's excess over a permuted range, and turns the archetype into a hold-to-close. The width ladder had never been varied and turns out to have been sitting on a good value all along. And the selection window ranks the target scheme wrong in sixteen cells of sixteen, which is a finding about the instrument rather than about the bracket.

## The new rows extend the stored table rather than running beside it

`ORB_LADDER_FRACTIONS` is built from `ORB_FRACTIONS` rather than rewritten, and `target=w1.0` is the parameter default object rather than a copy of it, so every cell the stored runs measured is re-run at exactly the values that produced it. Measured: the 1,024 rows where `cash-br+<n>m target=w1.0` at a fraction of `1.0` or below meets §M28.10's `cash-ft+<n>m scale=off` control pair one-to-one and agree exactly on trades, net P&L, profit factor, drawdown, wins, losses, `session_close_share` and `ambiguous_share`. The extension is readable against the stored figure rather than adjacent to it.

## The stop axis past its boundary, and it depends on the range

Held-out median profit factor over the 32 (side × offset × re-entry) cells, 1-minute bars, unfiltered, `target=w1.0`, MNQ / NQ:

| `stop_range_fraction`      | `cash-br+15m`     | `cash-br+30m`     |
| -------------------------- | ----------------- | ----------------- |
| 0.25                       | 0.799 / 0.848     | 0.768 / 0.815     |
| 0.50                       | 0.967 / 1.007     | 0.927 / 0.957     |
| 0.75                       | 1.041 / 1.067     | 0.979 / 1.017     |
| **1.00** — the stored edge | **1.133 / 1.156** | 1.062 / 1.090     |
| 1.50                       | 1.089 / 1.099     | 1.080 / 1.109     |
| 2.00                       | 1.075 / 1.096     | 1.063 / 1.065     |
| 3.00                       | 1.090 / 1.104     | 1.092 / 1.109     |
| **5.00**                   | 1.069 / 1.085     | **1.107 / 1.125** |

**At 15 minutes `1.0` is an interior maximum**: the axis rises to it and falls away past it on both roots, so the truncation cost nothing there and the stored table's boundary win was the real optimum. **At 30 minutes it is not**, and the axis keeps climbing — non-monotonically, with a dip at `2.0` — to a best value at the end of the extended ladder. The two ranges answer [#262]'s premise differently, which no single-cell measurement could have shown.

## The width ladder was never swept and was already at a good value

Held-out median profit factor by ladder, same cells, `cash-br+30m`, MNQ / NQ:

| ladder                         | at `stop_range_fraction` 1.0 | at 5.0            |
| ------------------------------ | ---------------------------- | ----------------- |
| `(0.5, nan)`                   | 1.039 / 1.071                | 1.078 / 1.096     |
| **`(1.0, nan)` — the default** | **1.062 / 1.090**            | **1.107 / 1.125** |
| `(1.0, 2.0, nan)`              | 1.033 / 1.062                | 1.078 / 1.095     |
| `(2.0, nan)`                   | 1.008 / 1.035                | 1.050 / 1.066     |
| `(3.0, nan)`                   | 1.012 / 1.049                | 1.048 / 1.077     |
| `(nan, nan)` — no target       | 1.034 / 1.071                | 1.069 / 1.097     |

**The parameter default is the best or joint-best ladder in all eight stop cells on both roots at 30 minutes**, ahead of a tighter target, two wider ones, the scale-out and the no-target arm. At 15 minutes it wins at the stop widths the stored axis reached and `(0.5, nan)` takes the wide end. So the axis that had never been varied turns out to have been set well, and §M28's reading of the target — which rested entirely on the R scheme — is not overturned by the width scheme finally being swept.

## The selection window picks the target scheme wrong in sixteen cells of sixteen

For each (root × range × resolution), which ladder each window's median points at:

| window    | `(nan, nan)` | `(1.0, nan)` | `(0.5, nan)` |
| --------- | ------------ | ------------ | ------------ |
| selection | **16 of 16** | 0            | 0            |
| holdout   | 1 of 16      | 11           | 4            |

**The selection window names the no-target arm every single time and the holdout names it once.** A runner that never takes profit is the best-looking ladder on a rising tape and among the worst out of sample, and this is the strongest form of [#262]'s "small finding about the instrument": ranking a target scheme on the selection window is not a weak instrument here, it is a wrong one. The stop axis is not affected the same way — both windows agree the 30-minute ladder keeps rising and disagree only about where it stops.

## Gate 4, size-matched, which is the comparison §M28.10 deferred to here

§M28.10 could not put its constant-fraction control through the same shortlist because the swept axis did not reach the treatment's geometry. It does now. Each arm is drawn from **four fractions**, so no arm wins on being bigger — `tools/campaign_holdout.py`, held-out top-20 net-to-drawdown, MNQ / NQ:

| variant                   | stored, ≤ 1.0     | extended, > 1.0   |
| ------------------------- | ----------------- | ----------------- |
| `cash-br+15m target=w0.5` | 0.856 / 0.804     | **1.832 / 1.776** |
| `cash-br+15m target=w1.0` | **0.763 / 0.897** | **1.494 / 1.567** |
| `cash-br+30m target=w1.0` | 0.626 / 0.721     | **1.319 / 1.280** |
| `cash-br+30m target=w0.5` | 0.228 / 0.409     | 0.931 / 0.960     |

**The stored arm of `target=w1.0` returns 0.763 / 0.897, which is §M28.10's `scale=off` control exactly** — the same 96 rows ranked the same way — so the two tables are on one scale. Against that, a plain constant fraction past `1.0` reaches **1.494 / 1.567**, and with the tighter target **1.832 / 1.776**. §M28.10's tracked arms are `stop@20` at 1.720 / 1.651 and `both@20` at 2.026 / 1.710. **A constant fraction of the range width gets there**, above `stop@20` on both roots with the tighter target and above `both@20` on NQ. That settles the question §M28.10 left open in its own favour: what cleared the drawdown check was the stop's **level** and not the trailing normalisation, and the level was reachable without a new primitive.

§M28.9 asked which of two shapes this axis would have — §M27.3's target multiplier, which reverses across the split, or §M28.10's stop scale, which holds. **It holds at 15 minutes and decays at 30.** The extended 15-minute arms return held-out profit factor *above* their selection-window figure in 4 of 4 cells (1.254 against 1.231, 1.263 against 1.202, 1.222 against 1.204, 1.231 against 1.189) at a rank correlation of 0.710 to 0.770; the 30-minute arms return 1.228 against 1.334 and 1.239 against 1.361 — still passing, but selection now flatters. Nothing here reverses, and the −0.161 shape §M27.3 found does not reappear.

## The acceptance cell, stated in advance: 2022

[#262] fixed the gate before the run: *does the wider stop survive the one falling year in the sample?* `cash+30m entry=breakout target=width`, `direction=1`, `entry_offset_ticks=1`, `max_entries_per_session=1`, 1-minute, the root's real costs, the equity curve restarted each year as §M28.10's tables do — 2022 alone:

| `stop_range_fraction` | profit factor | net / drawdown    | `session_close_share` |
| --------------------- | ------------- | ----------------- | --------------------- |
| **1.00**              | 1.144 / 1.178 | **1.243 / 1.505** | 0.440                 |
| 1.50                  | 1.128 / 1.164 | 0.752 / 0.945     | 0.572                 |
| 2.00                  | 1.121 / 1.133 | 0.623 / 0.682     | 0.652                 |
| 3.00                  | 1.148 / 1.159 | 0.611 / 0.658     | 0.730                 |
| 5.00                  | 1.122 / 1.132 | 0.466 / 0.506     | 0.767                 |

**It fails.** Profit factor is flat across the whole ladder — every value within 0.03 of every other on both roots — while net-to-drawdown falls monotonically to **a third of its value at the stored boundary**. In dollars on MNQ that is the same P&L for two and a half times the drawdown: 9,576 against a drawdown of 7,706 at `1.0`, 11,285 against 18,467 at `3.0`, 9,491 against 20,357 at `5.0`. [#262]'s own figures reproduce to the digit, the 2022 drawdown differing only by §M28.10's stated year-restart convention (-7,706 here against -8,001 sliced from a continuous curve).

The other four years are where the pooled gain comes from, and they are the rising ones: on MNQ at `target=w1.0`, net-to-drawdown runs 1.697 → 3.198 in 2023, 1.570 → 3.902 in 2024 and 2.569 → 3.441 in 2025 between fractions `1.0` and `5.0`. **A configuration that earns its held-out figure by removing the stop from a tape that went up has learnt the tape**, which is what the acceptance cell was stated in advance to catch.

**The 15-minute range does not rescue it and comes close once.** At `target=w0.5` 2022's net-to-drawdown runs 0.164 → **1.320** at `1.5` → 0.258 → 0.179 → 0.197 on MNQ and 0.202 → 1.053 → 0.191 → 0.151 → 0.167 on NQ. One fraction on one ladder clears 1.0 on both roots, with every neighbouring value at a fifth of it — that is a single cell of eighty, and reading it as the answer is the multiple-comparisons failure § "Standing traps" names.

## Gate 3 — the null rises with the stop, which is §M28.10's finding on the plain ladder

`matched_random_ranges` over the top twenty of each arm, ranked on the selection window and tested on the held-out one, 100 draws, 1-minute, `cash-br+15m`. Median over the shortlisted long cells at each fraction, MNQ / NQ:

| `stop_range_fraction` | observed      | null          | excess              | p             |
| --------------------- | ------------- | ------------- | ------------------- | ------------- |
| 1.00                  | 1.189 / 1.200 | 0.951 / 0.950 | **+0.238 / +0.250** | 0.050 / 0.020 |
| 1.50                  | 1.210 / 1.215 | 0.994 / 0.990 | +0.218 / +0.228     | 0.030 / 0.020 |
| 2.00                  | 1.232 / 1.246 | 1.013 / 1.008 | +0.218 / +0.239     | 0.020 / 0.020 |
| 3.00                  | 1.252 / 1.260 | 1.041 / 1.040 | +0.212 / +0.220     | 0.040 / 0.020 |
| 5.00                  | 1.233 / 1.224 | 1.061 / 1.046 | +0.172 / +0.178     | 0.099 / 0.059 |

**The observed statistic rises and the excess falls, because the permuted-range arm rises faster.** A stop the width of the range is worth +0.24 over a random range; a stop five times the width is worth +0.17 and is no longer significant at the conventional cut on MNQ. §M28.10 measured this from the follow-through side and read it as a property of the bracket rather than of the entry; here it is the same shape across a plain constant ladder, which is what makes that reading general. **The entry's edge over a permuted range is largest at the stop width the truncated axis already contained.**

Both shares read before any of it is believed. Ambiguity is negligible throughout — a median shortlisted `ambiguous_share` of 0.0000 to 0.0028, so §M28.7's corner does not reach a breakout-only variant set.

## What the wide end actually is

`session_close_share` on the shortlisted rows moves from **0.271–0.300** on the stored arms to **0.465–0.560** on the extended ones at 15 minutes, and the pooled 30-minute median reaches **0.801** at `target=w1.0` and **0.996** at the no-target ladder with a fraction of `5.0`. At the wide end this is not a bracketed breakout that sometimes runs to the close; it is a hold-to-close that occasionally stops out. That is a different risk object whatever its profit factor, it is entirely dependent on `IsExitOnSessionCloseStrategy` firing, and no leg of it has been checked against an NT8 trade list — see [#265].

## The verdict, and what [#262] asked

- **Both axes are now swept to their end.** The stop was truncated at 30 minutes and not at 15; the width ladder had never been varied at all and its default is the best value in it.
- **The extension fails the acceptance cell.** In the one falling year the wider stop buys nothing in profit factor and costs two thirds of net-to-drawdown, on both roots, monotonically. Pooled held-out profit factor rises and that rise is drift.
- **It also costs the thing that makes the archetype worth having.** The excess over a permuted range falls from +0.24 to +0.17 as the stop widens, and `session_close_share` roughly doubles. Two independent readings of the same fact: past about one range width, what improves is the bars rather than the entry.
- **§M28.10's deferred comparison is settled and its conclusion stands.** A plain constant fraction reaches the drawdown figures the trailing scale reached, so the trailing scale bought nothing the level did not — and this is now measured on matched shortlists rather than inferred.
- **What is worth keeping is the readable half.** `stop_range_fraction` of about `1.0` to `1.5` at `target=w1.0` is where profit factor, excess over the null, 2022 and the close share all still agree; everything past it is bought from one direction of one tape.
- **The width ladder is parked, not abandoned** — § "Parked is not abandoned". `ORB_WIDTH_LADDERS` stays registered and swept. What would justify re-running it is a target that is not a multiple of the session's own range width at all, which §M28.10's arithmetic already points at and which is a different primitive rather than another value of this one.
- **`OpeningRange` is still `TIER1_ONLY`**, and this section widens the reason: the wide end of the ladder leans on the forced flat for over half its exits, and the forced flat is one of the unevidenced parts of the fill model. [#265] is that export.

Every figure above is a measurement of one dated run over the archive as it stands, re-derivable from `results/campaign/OpeningRange.duckdb` under the variant names `cash-br+<length>m target=<ladder>` and a single-configuration re-run — not a standing property.

[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
[#265]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/265
