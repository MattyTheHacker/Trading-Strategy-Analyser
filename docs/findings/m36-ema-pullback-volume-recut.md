---
id: M36
title: "M36 — EmaPullback's volume dimension re-cut, and the first raw cell whose direction transfers"
archetypes: [EmaPullback]
issues: [311]
gates: [2, 3]
outcome: mixed
verdict: >-
  Volume stays the largest context dimension at all nine fitted cuts and the raw pair understated it at five minutes; HEAVY is a cost at every cut and six fitted cells clear gate 2 on both roots where no raw cell does — and then 1 of 120 matched-null tests reaches p = 0.05, in the wrong direction, on a shortlist whose median holdout sample is 22 trades.
---

# M36 — EmaPullback's volume dimension re-cut, and the first raw cell whose direction transfers ([#311])

[§M35](m35-ema-pullback-swept.md) measured volume as EmaPullback's largest context dimension and `volume=THIN` as its strongest cell, at the campaign's raw 0.7/1.5 pair. [§M30](m30-volume-regime-recut.md) is why that could not be quoted as a claim about thin volume: a gate result holds for the cut it was run at, and no calibrated cell reproduced InsideBar's raw `regime=UNCLASSIFIABLE`. This is the fitted re-cut. **The dimension survives it and the direction survives it — and the archetype still fails gate 3, on a sample too small to have answered either way.**

`THIN` matters more here than a re-cut usually does, because it is **pre-registered**: the pullback-continuation literature asks for the pullback to arrive on declining volume (`Trading-Docs` §7.4), so the hypothesis was written down before §M35 rather than turned up by it.

Every figure below is re-derivable from `results/campaign/EmaPullback.duckdb`. It is a measurement of one dated run against the archive as it stood, not a standing property.

## What was run

|                 |                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| **Grid**        | §M35's 2,304 combinations, unchanged — both averages over kind and period, plus the entry's own three axes |
| **Cells**       | 27: three forms × three tail sizes × three states, each form's pair fitted to its own distribution         |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                                                    |
| **Roots**       | MNQ and NQ, spliced continuous                                                                             |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                               |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%; every fit taken on the selection window       |
| **Size**        | **995,328 combinations in 87.1 minutes** on twelve workers                                                 |

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies EmaPullback \
    --strata volume-forms --split --volume-quantiles --resolutions 2 5 10 15 --n-jobs 12
```

**The grid was not cut.** [#311] budgeted for dropping `fast_kind` and `slow_kind` if the pass did not fit; at 87.1 minutes against §M35's 75 it did, so the two kind axes stay and the two campaigns are the same grid over different cells.

**A score here is out of ±8 and not ±10.** `tools/campaign_crossread.py` counts `root × resolution` cells, and this pass ran four resolutions where §M30 ran five. A `+8` below is every cell agreeing; a `+8` in §M30 is eight of ten.

## The family, stated before the run finished

Written down and committed while the sweep was still running, so that nothing below could be chosen after a score had been looked at — [§M31](m31-calibrated-cells-null.md)'s procedure and the trap `docs/roadmap.md` § "Standing traps" names.

1. **Gate 2 is `tools/campaign_holdout.py`'s `passes`** — the twenty-configuration shortlist's held-out profit factor above 1.0 *and* above the held-out median of every configuration in the same cell.
2. **A cell enters the family when it clears gate 2 on both roots.** A `THIN` cell enters when it clears on **either** root, and that asymmetry is the pre-registered direction; §M35 carried `volume=THIN` into its own gate-3 family on the same ground.
3. **At most twelve cells.** If more qualify, the twelve with the highest mean of the two roots' held-out shortlist profit factor are taken — the statistic gate 2 already ranks on, so the cap adds no new selection.
4. **Per cell: both roots, the best five configurations by selection-window profit factor**, ranked on the selection window and measured on the holdout, 400 draws, the over-bars draw.
5. **Nothing is added, dropped or re-cut after the first run**, and the family size is reported beside the p-values rather than counted afterwards.

**Exactly twelve qualified**, so the cap bound nothing: nine fitted `THIN` cells — every one of them — the raw `THIN` cell, one `NORMAL` cell and one `HEAVY` cell.

## The read reproduces §M35 exactly, which is what makes the comparison a comparison

The raw rows are §M35's and were not re-run. Read back under this pass's code they give `volume=THIN` at **67.6% of configurations profitable, median profit factor 1.086** and `volume=HEAVY` at **26.6% and 0.919**, and an η² of **0.216 at fifteen minutes and 0.198 at ten** — §M35's published figures to the digit. Everything below is the same statistic over 27 more cells.

## Volume is the largest context dimension at every cut, and the raw pair understated it

η² on profit factor, within a resolution, over the three states of each cut:

| cut                              | 2m        | 5m        | 10m       | 15m       |
| -------------------------------- | --------- | --------- | --------- | --------- |
| `raw 0.7/1.5`                    | 0.011     | 0.100     | 0.198     | 0.216     |
| `per_bar_20 q=0.10/0.90`         | 0.022     | 0.073     | 0.156     | **0.297** |
| `per_bar_20 q=0.20/0.80`         | 0.018     | 0.106     | 0.194     | 0.227     |
| `per_bar_20 q=0.33/0.67`         | 0.019     | 0.079     | 0.135     | 0.169     |
| `rolling_30_20 q=0.10/0.90`      | 0.067     | 0.226     | **0.273** | 0.266     |
| `rolling_30_20 q=0.20/0.80`      | 0.080     | **0.269** | **0.273** | 0.207     |
| `rolling_30_20 q=0.33/0.67`      | 0.078     | 0.230     | 0.235     | 0.200     |
| `session_to_date_20 q=0.10/0.90` | 0.019     | 0.086     | 0.247     | 0.258     |
| `session_to_date_20 q=0.20/0.80` | 0.066     | 0.177     | 0.227     | 0.153     |
| `session_to_date_20 q=0.33/0.67` | **0.099** | 0.205     | 0.248     | 0.190     |

Against the other five dimensions, all still at their own single cut:

| dimension     | 2m        | 5m    | 10m   | 15m   |
| ------------- | --------- | ----- | ----- | ----- |
| `phase`       | **0.137** | 0.068 | 0.051 | 0.079 |
| `regime`      | 0.097     | 0.046 | 0.054 | 0.129 |
| `trend`       | 0.043     | 0.062 | 0.048 | 0.051 |
| `htf`         | 0.013     | 0.036 | 0.032 | 0.026 |
| `compression` | 0.031     | 0.003 | 0.050 | 0.004 |

**§M35's largest-dimension reading was not the cut's.** At 5, 10 and 15 minutes every one of the nine fitted cuts puts volume above every other dimension, and the smallest of them — `per_bar_20 q=0.33/0.67` at 0.135 on 10-minute bars — is still more than twice `phase`'s 0.051 there.

**The raw pair was reading low, not high.** At five minutes it gives 0.100 where the fitted rolling form gives 0.269, and at fifteen the tenth-tail per-bar cut reaches 0.297 against its 0.216. That is the opposite of the §M30 failure mode: there a raw cell was a mixture no fitted cell reproduced, here a raw cell is a blurred version of something the fit sharpens.

## `HEAVY` is a cost at every cut; `THIN` reproduces at six of nine

`tools/campaign_crossread.py`, each cell against the unfiltered twin at identical parameters, scored in both windows independently. Beside each score, the twenty-configuration held-out shortlist profit factor on MNQ and NQ, **bold where it clears gate 2**:

| cut                              | `THIN`                   | `NORMAL`                 | `HEAVY`                  |
| -------------------------------- | ------------------------ | ------------------------ | ------------------------ |
| `raw 0.7/1.5`                    | +8 — **1.11** / 1.06     | +8 — 0.82 / 0.78         | −6 — 0.79 / 0.76         |
| `per_bar_20 q=0.10/0.90`         | +6 — **1.39** / **1.25** | +8 — 0.92 / **1.10**     | −8 — 0.70 / **1.31**     |
| `per_bar_20 q=0.20/0.80`         | +8 — **1.20** / **1.15** | +8 — 0.77 / 0.96         | −7 — 0.76 / 0.77         |
| `per_bar_20 q=0.33/0.67`         | +8 — **1.35** / 0.98     | +8 — **1.14** / 1.03     | −6 — 0.79 / 0.81         |
| `rolling_30_20 q=0.10/0.90`      | +6 — **1.35** / **1.05** | +8 — **1.05** / 0.96     | −8 — 0.76 / 0.75         |
| `rolling_30_20 q=0.20/0.80`      | +8 — **1.19** / **1.09** | +7 — **1.33** / 1.01     | −8 — 0.86 / 0.89         |
| `rolling_30_20 q=0.33/0.67`      | +8 — 1.04 / **1.17**     | +4 — **1.20** / **1.30** | −7 — 0.60 / 0.72         |
| `session_to_date_20 q=0.10/0.90` | +5 — **1.16** / 1.09     | +7 — 0.92 / 0.99         | −8 — **1.11** / 0.86     |
| `session_to_date_20 q=0.20/0.80` | +8 — **1.17** / 1.08     | +7 — **1.26** / 1.02     | −8 — **1.00** / **1.05** |
| `session_to_date_20 q=0.33/0.67` | +8 — 0.84 / **1.17**     | +4 — 0.88 / **1.09**     | −7 — 0.95 / 0.89         |

**`HEAVY` is negative at all nine fitted cuts and at the raw one**, reaching the maximum −8 at five of them. That is the one statement in this campaign that no choice of form or tail can move.

**`THIN` reaches the maximum +8 at six of the nine fitted cuts and at the raw one**, and the three that fall short are the three **tenth-tail** cuts — +6, +6 and +5. §M31 found the same shape on OpeningRange's regime cell and named the mechanism: a tenth at each end halves the sample, and a cell that thin stops agreeing across every `root × resolution` point whatever it is measuring. Here the median holdout sample per configuration falls from 204–223 trades at a fifth to 117–124 at a tenth.

**This is the first pre-registered context result in the register whose direction survives its own re-cut.** §M30's counter-cases stand: InsideBar's raw `regime=UNCLASSIFIABLE` was reproduced by no calibrated cell, and OpeningRange's `volume=NORMAL` came out +8 under one form and −9 under another. EmaPullback's `THIN` is neither — it is +5 or better at all ten cuts.

## What does not survive is `THIN` above `NORMAL`

Share of configurations profitable, by state, read in each window separately:

| cut                              | selection ordering        | holdout ordering          |
| -------------------------------- | ------------------------- | ------------------------- |
| `raw 0.7/1.5`                    | NORMAL > THIN > HEAVY     | THIN > NORMAL > HEAVY     |
| `per_bar_20 q=0.10/0.90`         | NORMAL > THIN > HEAVY     | THIN > NORMAL > HEAVY     |
| `per_bar_20 q=0.20/0.80`         | **THIN > NORMAL > HEAVY** | **THIN > NORMAL > HEAVY** |
| `per_bar_20 q=0.33/0.67`         | **THIN > NORMAL > HEAVY** | **THIN > NORMAL > HEAVY** |
| `rolling_30_20 q=0.10/0.90`      | THIN > NORMAL > HEAVY     | NORMAL > THIN > HEAVY     |
| `rolling_30_20 q=0.20/0.80`      | THIN > NORMAL > HEAVY     | NORMAL > THIN > HEAVY     |
| `rolling_30_20 q=0.33/0.67`      | THIN > NORMAL > HEAVY     | NORMAL > THIN > HEAVY     |
| `session_to_date_20 q=0.10/0.90` | THIN > NORMAL > HEAVY     | NORMAL > THIN > HEAVY     |
| `session_to_date_20 q=0.20/0.80` | NORMAL > THIN > HEAVY     | THIN > NORMAL > HEAVY     |
| `session_to_date_20 q=0.33/0.67` | **THIN > NORMAL > HEAVY** | **THIN > NORMAL > HEAVY** |

**`HEAVY` is last in all twenty readings. `THIN` above `NORMAL` holds in both windows at three of the ten cuts, and the raw pair is not one of them** — it says `NORMAL` first on the selection window and `THIN` first on the holdout. The rolling form inverts across the split at all three tails, in the same direction each time.

So the pre-registered hypothesis splits into two claims that do not survive equally. **"The pullback works worse into heavy volume" is invariant to the cut. "It works best into thin volume" is not** — that half is a statement about which of two adjacent states is in front, and the cut and the window both move it.

## Gate 2 — six fitted cells clear on both roots, and no raw cell does

| cells          | clear on both roots | clear on at least one |
| -------------- | ------------------- | --------------------- |
| 27 fitted      | **6**               | 19                    |
| 3 raw (§M35's) | 0                   | 1                     |

Four of the six are `THIN`, one `NORMAL` and one `HEAVY`. **Re-cutting is what put them there**: the raw `volume=THIN` cell clears gate 2 on MNQ and misses on NQ — §M35's reading — where `THIN@per_bar_20 q=0.10/0.90` clears on both at 1.39 and 1.25, the highest pair in the dimension.

Three cells return their own drawdown on one root, which is the thing gate 2 rarely answers: MNQ `NORMAL@session_to_date_20 q=0.20/0.80` at a net-to-drawdown of 1.07, NQ `HEAVY@per_bar_20 q=0.10/0.90` at 1.32 and NQ `NORMAL@rolling_30_20 q=0.33/0.67` at 1.10. **None of the three does it on both roots**, and the second is a `HEAVY` cell whose crossread score is −8.

## Gate 3 — 1 of 120, and it is in the wrong direction

Twelve cells × two roots × the best five configurations = **120 tests**, ranked on the selection window and measured on the holdout against a matched random entry taking the same number of trades with the same time-of-session profile, 400 draws each. Nothing was refused.

| root | cell                                          | median trades | median excess | median p | beat null  | p < 0.05 |
| ---- | --------------------------------------------- | ------------- | ------------- | -------- | ---------- | -------- |
| MNQ  | `volume=THIN@per_bar_20 q=0.10/0.90`          | 19            | +0.020        | 0.933    | 3 of 5     | 0        |
| MNQ  | `volume=THIN@per_bar_20 q=0.20/0.80`          | 29            | +0.188        | 0.738    | 3 of 5     | 0        |
| MNQ  | `volume=THIN@per_bar_20 q=0.33/0.67`          | 12            | +0.226        | 0.853    | 3 of 5     | 0        |
| MNQ  | `volume=THIN@rolling_30_20 q=0.10/0.90`       | 20            | −0.311        | 0.479    | 1 of 5     | 0        |
| MNQ  | `volume=THIN@rolling_30_20 q=0.20/0.80`       | 14            | −0.524        | 0.274    | 2 of 5     | 0        |
| MNQ  | `volume=THIN@rolling_30_20 q=0.33/0.67`       | 27            | +0.067        | 0.807    | 3 of 5     | 0        |
| MNQ  | `volume=THIN@session_to_date_20 q=0.10/0.90`  | 13            | +0.892        | 0.504    | 4 of 5     | 0        |
| MNQ  | `volume=THIN@session_to_date_20 q=0.20/0.80`  | 15            | −0.605        | 0.279    | 0 of 5     | 0        |
| MNQ  | `volume=THIN@session_to_date_20 q=0.33/0.67`  | 19            | −0.231        | 0.584    | 1 of 5     | 0        |
| MNQ  | `volume=THIN`                                 | 4             | +0.985        | 0.711    | 4 of 5     | 0        |
| MNQ  | `volume=NORMAL@rolling_30_20 q=0.33/0.67`     | 16            | +0.669        | 0.299    | **5 of 5** | 0        |
| MNQ  | `volume=HEAVY@session_to_date_20 q=0.20/0.80` | 14            | +0.063        | 0.569    | 3 of 5     | 0        |
| NQ   | `volume=THIN@per_bar_20 q=0.10/0.90`          | 17            | +0.720        | 0.249    | 3 of 5     | 0        |
| NQ   | `volume=THIN@per_bar_20 q=0.20/0.80`          | 30            | +0.226        | 0.419    | 3 of 5     | 0        |
| NQ   | `volume=THIN@per_bar_20 q=0.33/0.67`          | 46            | −0.136        | 0.708    | 2 of 5     | 0        |
| NQ   | `volume=THIN@rolling_30_20 q=0.10/0.90`       | 59            | −0.222        | 0.364    | 2 of 5     | 0        |
| NQ   | `volume=THIN@rolling_30_20 q=0.20/0.80`       | 25            | +1.379        | 0.209    | **5 of 5** | 0        |
| NQ   | `volume=THIN@rolling_30_20 q=0.33/0.67`       | 28            | +0.065        | 0.898    | 3 of 5     | 0        |
| NQ   | `volume=THIN@session_to_date_20 q=0.10/0.90`  | 29            | −0.028        | 0.843    | 2 of 5     | **1**    |
| NQ   | `volume=THIN@session_to_date_20 q=0.20/0.80`  | 10            | +0.121        | 0.693    | 3 of 5     | 0        |
| NQ   | `volume=THIN@session_to_date_20 q=0.33/0.67`  | 21            | −0.004        | 0.923    | 2 of 5     | 0        |
| NQ   | `volume=THIN`                                 | 35            | +0.541        | 0.279    | 3 of 5     | 0        |
| NQ   | `volume=NORMAL@rolling_30_20 q=0.33/0.67`     | 27            | +0.672        | 0.349    | 4 of 5     | 0        |
| NQ   | `volume=HEAVY@session_to_date_20 q=0.20/0.80` | 33            | +0.332        | 0.439    | 4 of 5     | 0        |

**Gate 3 fails, and more completely than §M35's did.** 68 of 120 configurations beat their own null, where chance alone would give 60. **One test of 120 reaches p = 0.05, and the p-value is two-sided: the observed profit factor is 0.378 against a null of 0.998**, so the single significant result in the family is a configuration that lost significantly *more* than a random entry would have. **Zero of 120 show a significant improvement**, against the six that 120 tests at the 5% level are expected to produce by chance.

**The binding constraint is the sample, and it is worse than §M35's.** The shortlisted configurations hold **3 to 80 trades on the holdout, median 22, and 85 of the 120 hold fewer than 30**. Two of the tested rows are degenerate — MNQ `volume=THIN` reaches a profit factor of 19.8 on 3 trades and MNQ `THIN@rolling_30_20 q=0.20/0.80` reaches 9.5 on 4 — because the shortlist ranks on the selection window's profit factor and nothing in that ranking is a floor on the *holdout* count.

**The two gates do not shortlist the same rows, and that is a gap rather than a detail.** `tools/campaign_holdout.py` pairs configurations viable in **both** windows, so its twenty hold 30 to 84 holdout trades; `tools/campaign_null.py` shortlists on the selection window alone and re-runs on the holdout, so its five can collapse to three. A cell can therefore clear gate 2 on a healthy sample and be taken into gate 3 on a different, thinner one.

## The two shares, and the fill assumption decides nothing

`campaign_holdout.held_out` over the same selection ranking and holdout window, the twelve family cells on both roots: `session_close_share` runs **0.05 to 0.65** and `ambiguous_share` reaches **0.10**, at or above `disambiguate.MIN_AMBIGUOUS_SHARE` on nine of the 120 rows, spread over six cells.

`tools/campaign_ambiguity.py` over all 24 root × cell shortlists — which rank on the holdout, so their profit factors are in-sample on that window and are attribution rather than a result:

- **All 24 keep every one of their five configurations above a profit factor of 1.0 under the pessimistic policy.**
- **The median spread is 0.000 in 22 of the 24**, 0.012 and 0.171 in the other two. The widest single row is 3.627 → 3.450.
- Three cells crossed the 5% share and were settled against the minute bars. The corrections are +0.025, −0.082 and −0.035 of profit factor.

**Nothing here turns on the ambiguous-bar assumption.** The session-close share does matter — a cell flattening 65% of its legs at the close is §M28.12's problem again — but no exit decomposition was run.

## What this does not settle

- **A dimension that survives its re-cut is still a dimension that carries no null result.** Six new cells clear gate 2 on both roots and none of them, nor the six that clear on one, beats a random entry at any level. §M28.16's finding stands: a consistency score does not order a null result, and neither does a gate-2 pass.
- **The sample was the binding constraint and this pass did not move it.** §M35 said a stratum tight enough to have an edge is tight enough to have no power, and a fitted cut makes the tightest cells tighter rather than wider. A tenth-tail `THIN` cell holds 117 to 124 median holdout trades before a shortlist is drawn from it, and the five drawn have a median of 22.
- **Nothing tested here is the pre-registered claim in its own right.** `Trading-Docs` §7.4 asks for volume to be **declining into the pullback**, which is a statement about the signal bar against the bars before it. Every state used here is a bar's volume against a *baseline*, which is a different quantity — [§M32](m32-volume-windows.md) moved the two windows behind that baseline and this pass held both at their defaults of 30 and 20.
- **The tail sizes are still stated rather than fitted**, exactly as §M27.8 and §M30 left them, and the three forms are still the three the codebase has.
- **One minute was not swept**, so this shares §M35's four-point reading of the bar-size lever, and a score here is out of ±8 rather than ±10 for the same reason.
- **The `HEAVY` cell in the family is in it on a gate-2 pass, not on a hypothesis.** `HEAVY@session_to_date_20 q=0.20/0.80` scores −8 on the crossread and clears gate 2 on both roots at 1.00 and 1.05. Both readings are of the same rows, and the disagreement is what the two tools mean: the crossread pairs every configuration against its unfiltered twin, the shortlist takes twenty. Neither is wrong and the cell carries nothing under the null.
- **Nothing is re-ranked and no archetype is revived.** EmaPullback remains `TIER1_ONLY` with no NinjaScript, and `docs/findings/README.md` is unchanged because nothing here reaches a recommendation.
- **The confirmation entry [#311] asks for second is not in this pass.** It is the other half of that issue and lands separately.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/EmaPullback.duckdb` plus `tools/campaign_sweep.py`, `tools/campaign_crossread.py`, `tools/campaign_holdout.py`, `tools/campaign_null.py` and `tools/campaign_ambiguity.py` — not a standing property.

[#311]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/311
