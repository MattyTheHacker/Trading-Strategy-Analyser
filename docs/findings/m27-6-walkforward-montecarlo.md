---
id: M27.6
title: "M27.6 — walk-forward and Monte Carlo, wired into the campaign"
archetypes: []
issues: [203]
gates: [4]
outcome: tooling
verdict: >-
  The shortlist becomes the candidate pool for gate 4, which `Grid` had no way to express before.
---

# M27.6 — walk-forward and Monte Carlo, wired into the campaign ([#203])

Both modules have existed since [#50] and §M27 used neither, which is how a gap becomes invisible: a step someone remembers to run by hand is a step that does not get run. This makes them the campaign's fifth gate, between the matched null and the drawdown check — `tools/campaign_walkforward.py` and `tools/campaign_montecarlo.py`, selected the same way every other campaign tool selects.

**Two tools rather than one, because they take different inputs.** Walk-forward needs bars and re-simulates; Monte Carlo needs a stored trade log and re-samples one. Gate 3 already has two tools for the same reason.

## The shortlist is the candidate pool, and `Grid` had no way to say so

Walk-forward selects on each training window, so it needs a set to select *from*. The whole grid through several folds is unaffordable and the shortlist is what any claim rests on — but a shortlist is an arbitrary subset of the product that produced it, and `sweep.Grid` could only express a product. Twenty rows of five parameters stated as axes is not twenty candidates, it is thousands, and the run would still report a clean number.

So `Grid` takes the combinations outright: `Grid.of_combinations` sets `combos` instead of `axes`, and the two are refused together. Everything downstream is unchanged — `combo_id` is the position in the list, the parallel workers regenerate it from the grid as before, and `axis_values` becomes the union over the list so `required_context` still covers every member. `walk_forward` carries the list through its costed rebuild; dropping it there would leave the base alone, and every fold would "select" the one combination left to it while reporting five folds of selection.

**The pool is itself a selection, and that is the honest limit of the result.** Rows ranked on the full window and then walked forward over the full series have seen the folds. Ranking on `selection`, or widening `--top` until the pool stops being a selection, is what makes a fold result clean; the tool defaults to the first and says so.

**The fold geometry is stated in shares, not bar counts**, because a bar count means a different amount of time at each resolution — the same defect §M27 records for `max_hold_bars`. Half the series to train on and a tenth to test gives five sliding folds at any bar size. **The warm-up is derived from the shortlist's own `ContextSpec` rather than guessed**, since each fold is prepared independently and would otherwise measure its own cold start; relative volume is the gap, because its baseline is counted in sessions and not in bars.

## What the resampling arm asks, and what it cannot

`permutation_test` reorders the same trades, which moves only the path statistics, and answers whether a drawdown was the ordering's doing. `bootstrap` resamples with replacement, which moves the values too, and puts percentiles beside the observed profit factor and drawdown — the spread Gate 4 read the shape of and could not size.

**`randomentry.py` looks like this machinery and is not**, which is the confusion worth pre-empting: it draws hundreds of samples per comparison, but it replaces the *entry* and holds the geometry and the ordering fixed. These two take the entries as given and can therefore never separate "worse than random" from "no better than random". The two arms are complementary and a run needs both; a figure quoted from here without the null beside it is half an argument.

A configuration with no stored log is named and skipped rather than dropped, because a report resampling four of twenty rows reads exactly like one resampling all twenty.

[#203]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/203
[#50]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/50
