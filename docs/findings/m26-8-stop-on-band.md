---
id: M26.8
title: "M26.8 — the stop on the band itself: the level §M26 specified and never built"
archetypes: [ElasticBand]
issues: [280]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  A stop at the band beats the tightest stop and never the widest; every arm beats the matched null and the stop scheme is not what moves the margin.
---

# M26.8 — the stop on the band itself: the level §M26 specified and never built ([#280])

**What has changed since §M26.6, stated first**, because [#221] is a parked configuration space and § "Parked is not abandoned" requires it: **a condition that did not exist** — `stop_mode` at `band`, a fifth place the protective stop can go. Not a new range, not new data, not a re-seeded sweep. The rules and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) §M26.8.

**It is this milestone's own specification, arriving four sub-milestones late.** § "The geometry inverts" above named the stop as "outside the band. Either `atr_bracket_distance` or `basis ∓ stop_std · σ`", and only the first of the two was ever written. The four modes that existed are a distance off the fill (`atr`, `catastrophe`) or a bar extreme (`excursion`, `swing`); none of them is a level on the channel the entry was measured against, so none of them has a width denominated in the units the entry threshold is written in. That is the whole hypothesis: enter at 2σ, stop at 3σ, and let one dispersion set both.

## The depth is measured past the threshold rather than stated as a level

`band_stop_std` is how far beyond `entry_std` the stop sits, so at `entry_std = 2.0` a value of `1.0` is the 3σ band. **An absolute level cannot be swept against this entry.** `entry_std` runs to 3.0 in every ElasticBand grid since §M26.4, and a fixed 3σ stop is *the entry threshold itself* there — the minimum-risk check declines the cell and the axis reports a hole rather than a result. Measuring past the threshold makes one value the same distance beyond wherever the entry was taken, which is §M26.6's argument for `recovery_fraction` reached from the other side.

**It also makes R exact for the first time in this archetype.** With the target at the basis, reward-to-risk is `entry_std / (entry_std + band_stop_std)` by construction — 0.80, 0.67, 0.57 and 0.50 at the four depths swept, identical on every combination sharing the pair and always below 1. § "The geometry inverts" predicted that arithmetic for a σ stop with a basis target and had no mode to attach it to; this is the mode.

## The campaign, and the two entries it is asked over

**3,360 rows**: seven arms — the three stops §M26.5 and §M26.9 swept, plus the band stop at 0.5σ, 1.0σ, 1.5σ and 2.0σ past the threshold — each crossed with both signal-bar entries §M26.9 ran, over `entry_std` × `min_bars_outside` × `max_hold_bars` at 12 combinations, on both roots, resolutions 1/2/5/10/15, split 60/40 into a selection and a held-out window, at the root's own commission and one tick of slippage. **The VWAP source and the 0.0σ ladder alone**, both held for the reasons §M26.9 held them. 88.0% of rows clear 30 trades — 97.7% under `shape=any` and 78.3% under `shape=reversal`. `--variants elastic-band-stop --strata elastic-band-stop --split`.

**`stop_mode` leaves the axes and becomes the arm**, because `band_stop_std` is inert under the other four schemes and crossing them would run identical combinations `dead_axes` cannot see. Every arm therefore differs from every other by where the stop went and by nothing else, which is what makes `tools/campaign_paired.py` readable over them. The three existing stops are re-run here rather than read out of §M26.5's stored rows, for §M26.6's reason: a stored row came out of a different grid.

**Two entries rather than one, and neither is what is being measured.** §M26.5 found an excess over the matched null for `shape=reversal` and none for the control, so running both bounds the question a stop pass has to answer — is a stop scheme being ranked, or are the bars under it? An entry with a measured edge and one without answer it from opposite ends.

**`min_bars_outside` is a duplicate in one arm and live in the other, which costs the shortlist rather than the grid.** Measured here: it produces byte-identical cells on 64.7% of `shape=reversal` rows and 0% of `shape=any` rows — §M26.5's 82.7% reproduced on a different channel. So a top-20 shortlist drawn inside a reversal arm is nearer a top 10 counted twice, and a sign test over paired cells counts each pair twice. It is recorded in `.claude/rules/sweep-and-context.md` because `dead_axes` cannot see it: the axis is not dead, another rule in the same variant set collapses it.

## The distribution, which is monotone in one variable — and it is not the coordinate system

Held-out window, every cell of every root and resolution that clears 30 trades, arms ordered by how long they hold:

| arm         | bars held (any) | PF (any) | profitable (any) | bars held (rev) | PF (rev) | profitable (rev) |
| ----------- | --------------: | -------: | ---------------: | --------------: | -------: | ---------------: |
| swing       |             5.2 |    0.963 |            0.422 |             9.2 |    1.060 |            0.696 |
| band @0.5σ  |             7.3 |    0.987 |            0.440 |            10.2 |    1.024 |            0.543 |
| band @1.0σ  |            13.6 |    1.027 |            0.603 |            18.3 |    1.062 |            0.728 |
| atr         |            18.1 |    1.049 |            0.672 |            19.7 |    1.153 |            0.826 |
| band @1.5σ  |            19.2 |    1.051 |            0.681 |            24.3 |    1.125 |            0.804 |
| band @2.0σ  |            23.9 |    1.054 |            0.724 |            27.5 |    1.142 |            0.848 |
| catastrophe |            27.9 |    1.066 |            0.690 |            28.9 |    1.169 |            0.848 |

**Sort the seven arms by median hold and the profit factors come out sorted too** — exactly, on `shape=any`, where the rank correlation between the two columns is 1.00, and at 0.86 on `shape=reversal`. The band stop does not sit in a group of its own: it interleaves with the ATR stop at precisely the width its depth gives it. **So what the arm axis measures is how wide the stop is, not what it is measured against**, and the four band depths are a width ladder that happens to be denominated in σ.

**This is §M26's outside finding arriving on the archetype's own data.** § "Three exit schemes" recorded that the strongest published result for mean reversion is that a stop *hurts* — a 5% stop on an SPY reversion system took the annual return from 8.22% to 1.05% — and that `catastrophe` exists to test it. The widest stop in the grid wins on both entries here, and the catastrophe arm's `session_close_share` is 0.226 and 0.248 against the tightest arm's 0.033 and 0.073: what "wider" buys is a hold that runs into the flatten rather than one that ends at a level.

## Paired, cell by cell: it beats the tightest stop and never beats the widest

Median change in profit factor at the same root, resolution and axis values, both arms clearing 30 trades, held-out window. Ten cells per figure — two roots by five resolutions:

| entry    | against     |  @0.5σ |  @1.0σ |  @1.5σ |  @2.0σ |
| -------- | ----------- | -----: | -----: | -----: | -----: |
| any      | swing       | +0.005 | +0.038 | +0.072 | +0.069 |
| any      | atr         | −0.061 | −0.006 | +0.004 | +0.005 |
| any      | catastrophe | −0.076 | −0.026 | +0.002 | −0.004 |
| reversal | swing       | −0.001 | +0.049 | +0.093 | +0.087 |
| reversal | atr         | −0.092 | −0.072 | −0.023 | +0.004 |
| reversal | catastrophe | −0.090 | −0.048 | −0.013 | +0.002 |

Cells improved of ten, in the same order: 5/10/8/9 and 5/9/9/9 against `swing`; 1/3/5/7 and 0/1/3/5 against `atr`; 2/2/5/4 and 2/2/4/5 against `catastrophe`.

**Monotone in depth against every control, and the sign flips in the same place twice.** Against the tightest stop the band stop is a gain from 1.0σ on both entries; against either wide stop it is a cost until 1.5σ and a draw at 2.0σ. **Nothing in this table is a win over a stop that already existed** — the largest positive figure against a wide control is +0.005, which is inside the spread of a single resolution's cells.

**The selection window cannot see any of it.** The same medians there run −0.047 to +0.065 with no monotone structure and no consistent sign, so a shortlist drawn on it would have picked a depth for the wrong reason. The sign is a property of the second window, as §M26.5's shape result and §M26.9's volume result both were, and it carries the same warning: this is the period rather than the rule until something separates them.

## Held out, where the drawdown check is what separates the arms

Best 20 on the selection window by profit factor, measured on the holdout, one arm at a time — `--variant` is what confines the shortlist to the arm, for the reason §M28.8 records. **26 of the 28 root × entry × arm cells pass the held-out gate**, which says more about the gate than about the arms: it is defined on the test window alone, so a space containing nothing profitable can clear it. The two failures are `band @1.5σ` and `band @0.5σ`, both on NQ and on different entries.

**The drawdown check separates them, and it rises with depth without being monotone.** Cells whose held-out shortlist returns its own drawdown, of the four available per arm — two roots by two entries — with the median net-to-drawdown beside it:

| arm         | clears of 4 | median net/drawdown |
| ----------- | ----------: | ------------------: |
| swing       |           0 |               0.461 |
| band @0.5σ  |           1 |               0.595 |
| band @1.0σ  |           2 |               0.976 |
| atr         |           1 |               0.689 |
| band @1.5σ  |           1 |               0.446 |
| band @2.0σ  |           3 |               1.322 |
| catastrophe |           4 |               1.402 |

Against the registry-wide rate §M28.9 measured — one cell in thirteen — three of four is a strong figure, and it belongs to the arm that is a *draw* with the widest existing stop rather than a win over it. `band @1.5σ` breaking the run at 1 is the reminder that four cells is four cells.

## The matched null: every arm beats it, and the stop scheme is not what moves the margin

Best 20 on the selection window by profit factor, each placed against its own matched random entry on the held-out bars, 200 draws per configuration. Median excess in profit factor, with the cells of 20 that beat the null in brackets:

| arm         |   MNQ / any | MNQ / reversal |    NQ / any | NQ / reversal |
| ----------- | ----------: | -------------: | ----------: | ------------: |
| swing       | +0.227 (20) |    +0.393 (20) | +0.122 (18) |   +0.177 (16) |
| band @0.5σ  | +0.238 (15) |    +0.305 (16) | +0.097 (19) |   +0.075 (14) |
| band @1.0σ  | +0.264 (20) |    +0.095 (14) | +0.107 (19) |   +0.172 (20) |
| atr         | +0.153 (16) |    +0.401 (20) | +0.090 (18) |   +0.275 (20) |
| band @1.5σ  | +0.085 (19) |    +0.173 (19) | +0.077 (18) |   +0.163 (18) |
| band @2.0σ  | +0.193 (18) |    +0.771 (18) | +0.116 (18) |   +0.212 (18) |
| catastrophe | +0.155 (15) |    +0.442 (20) | +0.143 (18) |   +0.214 (20) |

**Every arm clears the null on a clear majority of its shortlist** — 14 to 20 cells of 20 on profit factor and the same range on expectancy, median 18 of 20 on both. That is §M26.5's finding holding across all seven geometries at once: the entry is what carries this archetype, and it carries it whatever the stop is.

**The width ladder that orders the profit factor does not order the excess.** Rank-correlating the arms' width order against the excess over these 28 cells gives **0.038**, against the 1.00 and 0.86 the same order gives against the held-out profit factor of the whole cell population. The four band arms' median excess is +0.168 and the three existing stops' is +0.195. **So the stop scheme decides what the bars pay and not what the entry adds** — which is the same statement §M26 made about geometry in general, arriving on a scheme chosen to be geometrically different.

**One caveat travels with every row.** The observed trade count differs from the null's by a median of 21%, which is the mismatch §M26.4 named as what makes a null comparison unclean. It is not evenly spread: the two widest existing stops are the worst — `catastrophe` on MNQ under `shape=any` is 310 observed against a null median of 633 — and the band arms are the best, `band @1.0σ` on NQ matching at 793 against 792. **The arm with the cleanest match is a band arm and the arm with the largest excess is a band arm, and they are not the same arm.**

## Ranked by excess over the null instead of by profit factor, the target axis inverts

[#280] asked for this explicitly, and `tools/geometry_contribution.py` is what it exists for: the entry is held at the middle of every axis, only the geometry varies, and both terms are reported. The band stop is now a fourth scheme there. MNQ 03-24, the Bollinger source, 200 null draws per geometry, at half the real round trip and one tick of slippage:

| stop  | target | observed PF | null PF | excess | verdict               |
| ----- | -----: | ----------: | ------: | -----: | --------------------- |
| +0.5σ |  −0.5σ |       0.640 |   0.487 | +0.153 | better than random    |
| +0.5σ |   0.0σ |       0.684 |   0.675 | +0.009 | indistinguishable     |
| +0.5σ |  +0.5σ |       0.714 |   0.758 | −0.044 | **worse than random** |
| +1.0σ |  −0.5σ |       0.710 |   0.540 | +0.170 | better than random    |
| +1.0σ |   0.0σ |       0.744 |   0.711 | +0.033 | indistinguishable     |
| +1.0σ |  +0.5σ |       0.772 |   0.791 | −0.019 | indistinguishable     |
| +1.5σ |  −0.5σ |       0.738 |   0.569 | +0.169 | better than random    |
| +1.5σ |   0.0σ |       0.775 |   0.734 | +0.041 | better than random    |
| +1.5σ |  +0.5σ |       0.804 |   0.807 | −0.004 | indistinguishable     |
| +2.0σ |  −0.5σ |       0.779 |   0.592 | +0.188 | better than random    |
| +2.0σ |   0.0σ |       0.802 |   0.745 | +0.057 | better than random    |
| +2.0σ |  +0.5σ |       0.821 |   0.811 | +0.010 | indistinguishable     |

**Observed profit factor rises monotonically with the target and the excess falls monotonically with it, to below zero.** Within this scheme the two correlate at **−0.29**, while observed profit factor correlates with its own null at **+0.70**. So the geometry a profit-factor ranking picks — the most patient target — is the one where the entry contributes least, and at the shallowest stop it is a geometry measurably *worse* than dropping the entry rule altogether. `report()` prints `DISAGREE` for this scheme and for `C-time-mean`, and `agree` for `B-atr`.

**The depth axis is the half where the two rankings do agree**: excess rises with the stop's width at every target, which is the direction the campaign's paired table found. So [#280]'s instruction was right about the target and unnecessary about the stop — and there was no way to know which in advance, which is the argument for reporting both terms rather than one.

**Read this table beside the campaign's rather than instead of it.** It is one contract, one source and one entry, where the campaign is two roots, five resolutions and two windows. Its role is the ranking comparison, which the campaign cannot make: a matched null per cell over 3,360 rows is not affordable.

## Which axis moves the profit factor, and the stop scheme is third

η² over every cell of the grid, both entries pooled:

| axis               | selection | held out |
| ------------------ | --------: | -------: |
| resolution         |    0.0238 |   0.1302 |
| `entry_std`        |    0.0366 |   0.1153 |
| stop arm           |    0.0266 |   0.0383 |
| `signal_shape`     |    0.0064 |   0.0333 |
| `min_bars_outside` |    0.0016 |   0.0120 |
| `max_hold_bars`    |    0.0008 |   0.0020 |
| root               |    0.0184 |   0.0008 |

Within the four band arms alone, `band_stop_std` is 0.0043 on the selection window and 0.0170 on the holdout.

**Bar size is the largest lever and the entry depth the second**, which is the standing registry fact holding on a grid built to measure something else. The stop scheme is third at 0.0383, below the 0.070 §M26.5 measured for `stop_mode` over three schemes — seven arms spread the same variance further. **No axis swaps rank between the windows except the root**, whose η² collapses from 0.0184 to 0.0008: that is the two roots agreeing on the holdout and not on the selection window, which is a better sign than the size of the number suggests.

## What this rules out, and what is left

- **The band stop works and is not worth trading over what already exists.** It is monotone, well-behaved, and beats the tightest stop in the registry's mean-reversion archetype from 1.0σ on both entries; it never beats either wide stop by more than +0.005 in a paired median. [#170] is no closer.
- **The interesting result is the one [#280] asked for rather than the one it proposed.** Ranked by excess over the matched null, the band scheme's *target* axis runs the opposite way to its profit factor and reaches "worse than random" — so the geometry a sweep would pick is the geometry where the entry contributes least. That is §M26's +0.71 correlation reproduced at −0.29, on a scheme that did not exist when it was measured.
- **The arm axis is a width ladder wearing a coordinate system's name.** Sorting the seven arms by median hold sorts their profit factors exactly on one entry and to a rank correlation of 0.86 on the other, and the band arms interleave with the ATR arm at the width their depth implies. A stop denominated in the entry's own dispersion is not, on this evidence, a different *kind* of stop.
- **What the whole ladder says is that the stop hurts**, which is §M26's own reading of the outside literature and the reason `catastrophe` is in the grid at all. The widest arm wins on both entries held out, and the direction is the same against every control in the paired table.
- **Everything §M26.5 owed is still owed.** The VWAP basis is unpinned, and every figure here is off the back-adjusted continuous series rather than per contract — §M26's first trap, that both σ and the basis step at every roll seam. Two are added: `min_bars_outside` duplicates the shortlist under one of the two entries, and the sign of every paired comparison is invisible on the selection window.

[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
[#280]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/280
