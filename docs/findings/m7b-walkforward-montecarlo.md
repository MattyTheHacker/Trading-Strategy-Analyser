---
id: M7b
title: "M7b — walk-forward and Monte Carlo: done"
archetypes: []
issues: [50]
gates: [4]
outcome: tooling
verdict: >-
  Walk-forward and Monte Carlo exist as the fourth gate, resampling the trade order to separate a drawdown from its ordering.
---

# M7b — walk-forward and Monte Carlo: done ([#50])

`nqbt/walkforward.py`, `nqbt/montecarlo.py` and `nqbt/costs.py`. The third is not scope creep — see below.

**Costs are an argument with no default, because an uncosted walk-forward is worse than none.** Every archetype's parameter class defaults `commission_per_contract` and `slippage_ticks` to zero, which is right for NT8 reconciliation and wrong for every ranking. Selection on gross P&L selects for *trade frequency*, which is the one thing costs punish, so an uncosted walk-forward reports a clean result that inverts the moment costs are applied — a failure that looks like success. `walk_forward` therefore raises on `costs.FREE` rather than defaulting, and `costs.LIVE` carries the real account's terms. **Do not "simplify" this to a default.**

The defaults themselves stay zero and must: `tools/capture_trade_logs.py` uses them for the reconciliation captures, so flipping them breaks the trade-log gate.

**The split geometry is asserted as a property, not as arithmetic.** `splits()` returns half-open positions and the tests check directly that no test bar is ever a train bar and that the out-of-sample windows *tile* the tested region — the latter is what makes concatenating their trade logs legitimate rather than double-counting. A test that recomputed the arithmetic would pass over the same off-by-one it was meant to catch.

**Each window is simulated independently, and that is a stated approximation.** A trade open at a boundary is not carried across it: every window starts flat. The alternative — one run with the selection changing mid-flight — cannot be measured per window at all. The cost is that a position spanning `test_start` would have blocked an entry that the sliced run now takes.

**`warmup_bars` prefixes each window and its trades are discarded by entry position.** Without it every window's indicators start cold, so an SMA(200) grid measures its own warm-up for the first 200 bars of each split. `entry_bar` is already a position into the sliced frame, which is what the prefix is measured in — do not reach for `entry_time` and an index lookup.

**Selection is capped to `TRADE_PNL_STATISTICS`.** Every one of them is higher-is-better, so one comparison serves both sides. Admitting `max_drawdown` would need the opposite sense and a direction bug there is invisible — it would simply select the worst combination every time.

**`trade_id` restarts at 1 in every window, and pooling on it silently merges trades.** `stats.per_trade` groups on `trade_id` alone, so collapsing the concatenated log counted 5 trades where there were 14. `WalkForwardResult.pooled_pnl` groups per split *before* the leg collapse. Found by a test asserting the pooled count equals the sum of the per-split counts; without that assertion every downstream statistic would have been quietly computed over a quarter of the data.

**Monte Carlo's two halves answer different questions, and the guard between them is the point.** `permutation_test` reorders the trades, which moves only `PATH_STATISTICS`; `bootstrap` resamples with replacement, which moves the values too. Permuting a `TRADE_PNL_STATISTICS` value is **refused**, because reordering cannot change profit factor, net P&L, expectancy or win rate — such a test returns `p_value` 1.0 for every input and reads exactly like a passed check. `stats.PATH_STATISTICS` is the exact complement of `TRADE_PNL_STATISTICS` and `stats.path_statistic` is the single definition, sharing `_max_drawdown` and `_max_consecutive` with `summarise`. A test pins both halves: that reordering *cannot* move a value statistic, and that it *can* move a path statistic.

**Neither test says the entries are any good.** Both take the trades as given, so they cannot separate "worse than random" from "no better than random" — that is `randomentry.py`'s job ([#32]), and a Monte Carlo result quoted without it is half an argument.

**Drawdown is measured from the running peak of the equity curve, which starts at the first trade rather than at zero.** Ten $10 losses followed by ten $10 wins reports 90, not 100. That is `summarise`'s existing definition and this must not fork it; a test pins the two together.

**First result, and it is a confirmation rather than a finding.** Costed MNQ from 2025-01-01 (564,927 bars, `DeadCatParams`, 9 combinations, 120,000-bar train / 40,000-bar test, 11 splits): training profit factor runs a median 0.611 against a pooled out-of-sample 0.563, four different combinations win a training window across the eleven, and the bootstrap puts net P&L below zero in every resample. The permutation test reads p = 0.70 on max drawdown — **the losses are systematic, not an unlucky ordering**, which is the correct reading and the one that matters: this is the machinery reproducing a result the project already holds, on an archetype whose unprofitability is settled. Re-run it rather than quoting these numbers.

[#32]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/32
[#50]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/50
