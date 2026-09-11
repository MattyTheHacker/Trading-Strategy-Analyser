---
id: M26.5
title: "M26.5 — the signal bar's own shape: the first thing here whose excess is not the bracket's"
archetypes: [ElasticBand]
issues: [221]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Requiring the signal bar's body to have turned raises the observation while leaving the matched null where it was — the first ElasticBand excess that measures the entry rather than the bracket, and still not a pass on 34 to 56 trades.
---

# M26.5 — the signal bar's own shape: the first thing here whose excess is not the bracket's ([#221])

**What has changed since §M26.4, stated first**, because [#221] is a parked configuration space and § "Parked is not abandoned" requires it: **two conditions that did not exist**, both on the bar that signals rather than on the band it is measured against. Not a new range, not new data, not a re-seeded sweep. `signal_shape` asks that bar's own candle to have turned; `min_one_sided_bars` asks the move into the band to have been one-sided. The rules and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) §M26.5.

**Where the idea comes from, and it is not this project.** `Trading-Docs` states the reaction requirement twice and in two forms. The volume-area version is explicit that a blind limit at the edge is not the trade — *wait for a reaction first, an engulfing candle or a change of structure*, before entering — and the failed-break version gives the reaction a shape: price exceeds the level, fails to hold, and returns inside. The one-sidedness count is the other half of the same document's overextension gauge, which pairs *how far beyond the band* with *how many of the last ten candles closed in the trend's direction* and is explicit that both halves are simple countable quantities. §M26.4 left the archetype needing exactly this: a profit factor of 1.03 sitting inside its own null distribution is the bracket working, and only the entry can move it.

## Three shapes, and the fourth was removed before it reached a grid

`SHAPE_REVERSAL` is a body that closed back towards the basis, `SHAPE_RECLAIM` a bar that took out the previous bar's extreme and closed back past its close, and `SHAPE_REJECTION` a close within a swept fraction of the bar's range of the extreme it stretched to. **An engulfing mode was built first, measured, and deleted.** Over the MNQ continuous series at one minute on the Bollinger band — period 20, entry at 2σ, 1,663,489 bars — it fires on **138 signals against the unfiltered rule's 196,816**:

| requirement      | signals | share of the unfiltered rule |
| ---------------- | ------: | ---------------------------: |
| none             | 196,816 |                         100% |
| one-sided ≥ 6/10 | 151,655 |                          77% |
| rejection at 0.5 |  27,312 |                        13.9% |
| reversal         |  14,052 |                         7.1% |
| rejection at 0.7 |   9,050 |                         4.6% |
| reclaim          |   7,074 |                         3.6% |
| engulfing        |     138 |                        0.07% |

**The mechanism is that the extension threshold is defined on the close**, so a bar whose body ran the other way *and* covered its predecessor's has usually stopped being 2σ from the basis by the time it closes. Requiring a turn at all costs 93% of the signal for that reason; requiring a turn that swallows the bar before it costs 99.93%. This is not a tuning problem and no range fixes it — the reaction Trading-Docs describes happens *after* the extension, and an entry that reads it needs a trigger that survives the bar closing back inside. **That is the recovery entry, and it is deferred rather than built** — see below.

**Count the signals a new entry gate leaves before crossing it with anything.** An axis this thin does not announce itself in a sweep: `MIN_TRADES` drops its cells and the table reports a smaller shortlist rather than a broken rule.

## The campaign, and the control that runs beside it

**28,800 rows**: five shapes × two of §M26's target ladders as ten variants, each crossing `entry_std` × `min_one_sided_bars` × `min_bars_outside` × `stop_mode` × `max_hold_bars` at 144 combinations, on both roots, resolutions 1/2/5/10/15, split 60/40 into a selection and a held-out window, at the root's own commission and one tick of slippage. **The VWAP source alone**, because §M26.4 is what established that the Bollinger one does not survive a holdout — so the question here is the signal bar and not the channel. 78.7% of rows clear 30 trades. `--variants elastic-shape --strata elastic-shape --split`.

**`shape=any` is a control run in the same pass**, not a stored row from another campaign, which is what makes every comparison below a paired one. §M27's own lesson about shortlists applies with full force here: a treatment carries the axes its rule reads and wins on size, so the instrument is `tools/campaign_paired.py` cell by cell and not a best-of ranking.

## Paired, cell by cell: the sign depends on the window and not on the root

Median change in profit factor against `shape=any` at the same root, resolution, ladder and axis values, both arms clearing 30 trades:

| window    | root | reversal   | reclaim    | rejection@0.4 | rejection@0.6 |
| --------- | ---- | ---------- | ---------- | ------------- | ------------- |
| selection | MNQ  | +0.028     | +0.010     | +0.000        | −0.035        |
| selection | NQ   | −0.029     | −0.069     | −0.061        | −0.059        |
| holdout   | MNQ  | **+0.131** | **+0.124** | +0.059        | +0.120        |
| holdout   | NQ   | **+0.094** | **+0.123** | +0.079        | +0.094        |

Share of paired cells the treatment wins: 73–85% on the holdout window against 27–57% on the selection window, on every shape and both roots.

**Read this as a property of the period rather than of the rule, until something separates them.** The two arms run on the same bars, so window difficulty cancels out of a paired difference — what does not cancel is that the requirement earns its cost after September 2024 and does not before it. That is §M28.10's finding on OpeningRange with the sign reversed, and it carries the same warning: a rule whose paid-for window is the recent one is a bet on the recent regime continuing.

**Selecting on the selection window would therefore pick `shape=any`**, and the holdout would then reward the shapes. §M26.4 drew the same lesson from Bollinger owning the higher selection-window number and being eliminated first.

## Held out, where the shape is the only thing that clears the drawdown check

Top twenty ranked on the selection window and read on the held-out one, per variant:

| variant               | root | sel top-20 PF | hold top-20 PF | hold all-cell median | profitable | passes | returns its drawdown |
| --------------------- | ---- | ------------- | -------------- | -------------------- | ---------- | ------ | -------------------- |
| any, target 0.0σ      | MNQ  | 1.313         | 1.176          | 1.016                | 16/20      | yes    | **no**               |
| any, target 0.0σ      | NQ   | 1.213         | 1.254          | 1.046                | 15/20      | yes    | **no**               |
| reversal, target 0.0σ | MNQ  | 1.786         | 1.596          | 1.146                | **20/20**  | yes    | **yes**              |
| reversal, target 0.0σ | NQ   | 1.241         | 2.199          | 1.093                | 16/20      | yes    | **yes**              |
| reclaim, target 0.0σ  | MNQ  | 1.744         | 1.119          | 1.112                | 16/20      | yes    | no                   |
| reclaim, target 0.0σ  | NQ   | 1.210         | 1.485          | 1.131                | 16/20      | yes    | yes                  |
| rejection@0.6, 0.0σ   | MNQ  | 1.606         | 0.939          | 1.083                | 4/20       | **no** | no                   |
| rejection@0.6, 0.0σ   | NQ   | 1.159         | 1.071          | 1.091                | 16/20      | **no** | no                   |

**`reversal` clears the drawdown check on four of four root × ladder cells and `shape=any` on none of them**, which is the comparison that matters: §M28.9 measured one cell in thirteen across the whole registry returning its own drawdown held out, and this archetype has never been one of them. `reclaim` manages two of four and `rejection` none.

**Rank correlation between the windows is 0.35 on MNQ and 0.12 on NQ**, so the surface barely replicates and the top twenty is a best-of-540. The drawdown result is the robust half of this table; the profit factors in it are not.

## The matched null, which is what §M26.4 could not answer

The same twenty, ranked on the selection window and run against `randomentry.compare` on the holdout — 200 draws, entry days randomised, geometry and direction held:

| root | variant  | median PF | median null PF | median excess | *p* < 0.05 on PF | on expectancy | median trades |
| ---- | -------- | --------- | -------------- | ------------- | ---------------- | ------------- | ------------- |
| MNQ  | any      | 1.034     | 0.908          | +0.073        | 3/20             | 5/20          | 98            |
| MNQ  | reversal | 1.526     | 0.902          | **+0.645**    | 4/20             | 6/20          | **34**        |
| NQ   | any      | 1.136     | 0.948          | +0.248        | 5/20             | 5/20          | 189           |
| NQ   | reversal | 2.301     | 0.931          | **+1.355**    | **12/20**        | **16/20**     | **56**        |

**The null does not move and the observation does.** 0.908 → 0.902 on MNQ and 0.948 → 0.931 on NQ: the bracket is doing exactly what it was doing, on the same bars, with the same geometry. What changed is the entry, and that is the thing §M26.4 said had never been shown — *"a profit factor of 1.03 sitting inside its own null distribution is what 'the geometry is doing the work' looks like"* is no longer the description of this archetype's best cell.

**It is still not a pass, and the reason is the sample.** The median shortlisted cell has **34 trades on MNQ and 56 on NQ** over a two-year window, so most of the excess cannot clear significance whatever its size — 4 of 20 on MNQ is barely the control's 3 of 20. NQ's 12 of 20 and 16 of 20 are the strongest cells this archetype has produced and they rest on a median of 56 trades. This is §M28.1's position for OpeningRange arrived at from the other direction: what stops it is the sample size rather than the idea.

## The one-sidedness count does not work, and its low end is a dead value

Paired against its own off value with the shape held:

| `min_one_sided_bars` | paired cells | median ΔPF | treatment wins | trade ratio |
| -------------------- | ------------ | ---------- | -------------- | ----------- |
| 4 of 10              | 5,936        | +0.000     | 36.0%          | **1.00**    |
| 6 of 10              | 5,840        | +0.004     | 53.9%          | 0.88        |
| 8 of 10              | 4,944        | −0.014     | 46.7%          | 0.30        |

**At four of ten it is not a filter at all** — the trade count is unchanged, because a bar sitting 2σ below a twenty-period basis has nearly always been preceded by four down closes in ten. At six it is within noise and at eight it is a cost. **The gauge Trading-Docs describes is not wrong so much as already spent**: the depth threshold and the one-sidedness count are two readings of the same move, and `entry_std` has the information. Its η² on profit factor is 0.0016 against `entry_std`'s 0.0941.

## The shape makes `min_bars_outside` a duplicate, which is a new instance of an old hazard

Share of cells whose profit factor is identical across the whole `min_bars_outside` axis:

| shape         | identical |
| ------------- | --------- |
| any           | 0.0%      |
| rejection@0.4 | 9.3%      |
| rejection@0.6 | 34.4%     |
| reversal      | 82.7%     |
| reclaim       | **100%**  |

**Under `reclaim` the run length cannot bite at all.** Requiring a long's close above the previous bar's close means the previous bar closed lower, and a lower close against a basis and a dispersion that move over twenty bars is a *more* negative stretch — so the previous bar was outside the band too, and `min_bars_outside = 2` is satisfied wherever `= 1` is. The shape implies the run. `reversal` is the same mechanism weakened to a tendency.

This is the family `.claude/rules/sweep-and-context.md` already names — `dead_axes` compares an axis against one off value and cannot see an axis another parameter has made unreachable — with a new member: **here it is the interaction of two entry conditions rather than of a mode and the axis it reads.** Sweeping the run length under either shape runs identical combinations and nothing reports it.

## Which axis moves the profit factor

η² on profit factor over the ranges swept, both roots pooled, cells clearing 30 trades:

| axis                 | holdout    | selection |
| -------------------- | ---------- | --------- |
| `entry_std`          | **0.0941** | 0.0319    |
| `stop_mode`          | 0.0699     | 0.0035    |
| resolution           | 0.0609     | 0.0469    |
| `signal_shape`       | 0.0185     | 0.0110    |
| `max_hold_bars`      | 0.0070     | 0.0004    |
| `min_bars_outside`   | 0.0016     | 0.0011    |
| `min_one_sided_bars` | 0.0016     | 0.0003    |
| target ladder        | 0.0000     | 0.0020    |

**The shape is a small lever and the depth is a large one**, which is the calibration the paired table needs beside it: a requirement that consistently helps is not the same as a requirement that dominates. Read this table with §M28.1's warning attached — `min_bars_outside` is inert under two of the five shapes and carries its default there, so its pooled figure understates what it does under the other three. The registry-wide finding that bar size is the largest lever does **not** reproduce here: `entry_std` and `stop_mode` both beat it, on a grid that holds the band source fixed and sweeps depth over three values rather than two.

## What this changes, and what it does not

- **The entry contributes something, measurably, for the first time in this archetype.** §M26.4 could not separate the entry from the bracket; a matched null whose median does not move while the observation rises ninefold on MNQ and fivefold on NQ does.
- **`reversal` is the shape to carry forward** — three of three tests, against `reclaim`'s two of four on the drawdown check and `rejection`'s failure of the held-out gate on both roots.
- **The promotion criteria under "Decisions taken" are still not met, and [#170] is still not earned.** The blocking facts are the sample size, the window dependence, and everything §M26.4 already owed — the VWAP basis is still unpinned, and every number here is off the back-adjusted continuous series rather than per contract.
- **The one-sidedness axis should not be swept again as it stands.** Its low end is a dead value and its high end is a cost. If the idea is worth another attempt it needs the count taken over closes rather than bodies, or over a window that does not overlap the one `entry_std` already measures.

## What is deferred, and where it went

[#221] carried six ideas at once and has been split so each can be measured on its own, which is what the tracker is for — **read the issues rather than this list**, which records only why each one is a separate change:

- **The recovery entry** ([#278]) is what "wait for a reaction" actually asks for: the run of bars outside ends at *i−1* and bar *i* closes back **inside** the band. Every shape here is evaluated on a bar that is still beyond the threshold, which is what makes the reaction so expensive to require and what killed the engulfing mode. A different trigger rather than a fourth shape. **§M26.6 is that pass**: it wins the selection window at every depth and gives all of it back, and the reason is geometric — a close that has come back inside has spent the move the basis target exists to capture while the stop still has to cover the whole run.
- **Inverting the signal** ([#279]) is not free here: `TARGET_R` caps every target at the basis and that cap is a mean-reversion rule, `STOP_EXCURSION` hangs off the extreme of the run being faded, and the stretch ladder would need mirroring — three exit-side changes to answer an entry-side question.
- **A stop at a band level** ([#280]) is the half of "specific TP/SL points" that does not already exist. `TARGET_STRETCH` places every leg on a band coordinate, so "take profit at VWAP" is `target_stretch_levels = (0.0, …)` under `BAND_VWAP` and is what half of this campaign ran; no `stop_mode` is a level on the channel the entry was measured against.
- **A volume requirement on the break** ([#281]) **needed no code**: `volume_filter` at `HEAVY` on the signal bar is exactly it, and §M27.8 had already swept the volume dimension across the registry. Crossing it with the shape was a stratum on a later pass rather than a parameter. **§M26.9 is that pass**: the two are not the same cut, and the requirement is a cost while the state that is not an extreme at all is a gain.

Two of the six needed nothing. The **band source** landed as §M26.4, and **profit-taking aggression as a sweepable axis** was answered by §M26 — "less aggressive is better, and it is the one exit axis that matters" — over a ladder that `ELASTIC_LADDERS` still varies.

[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
[#278]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/278
[#279]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/279
[#280]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/280
[#281]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/281
