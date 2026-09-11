---
id: M10.3
title: "M10.3 — the compact trend label: done"
archetypes: []
issues: [42]
gates: []
outcome: calibration
verdict: >-
  The higher-timeframe trend label, compact enough to sweep as a stratum.
---

# ~~M10.3~~ — the compact trend label: done ([#42])

`nqbt/trend.py`. Three facts about one pair of EMAs — where price sits against the slow one, which way the slow one is sloping, and which way round the two are stacked — each voting `+1`, `-1` or `0`, summed into an **agreement score** and cut by `min_agreement` into `DOWN`, `MIXED` and `UP`. One `int8` per bar rather than a wall of MA booleans, and `trend_filter` is a bitmask integer for exactly the reason `phase_filter`, `regime_filter` and `volume_filter` are.

**The memory switch is not switched on, and that is enforced rather than intended.** [#42] assumed the label would need `keep_values=True` on the sweep's shared moving-average grids — the 8-bytes-against-1 setting that is 285 MB of raw EMA values over the run below and grows with the period axis. It does not. `trend_grid` builds a values-carrying grid over *its own* two periods, reads the labels out of it and lets it go, so nothing outside that function ever sees an MA value and a parallel worker is handed the labels alone. Recomputing two EMAs costs milliseconds against the pass that would otherwise be paid per worker. Pinned as a property of a prepared dataset: asking for the label leaves `needs_ma_values` false, leaves every shared grid's `values` at `None`, and grows `Dataset.nbytes` by exactly the label arrays.

**The averages are the label's own, not the archetype's.** Reusing whichever periods an archetype happens to gate on would make the same label name a different measurement in each one, and a stratification that is not comparable across archetypes is not a stratification. The kind is fixed at EMA for the same reason — one definition, and `TrendKey` gains a field the day an SMA label is actually wanted.

**No label is ever taken off two components.** The slope cannot be measured for the first `slope_lookback` bars, and price and stack can. Letting those two decide would manufacture a trend out of a warm-up, so the score is `nan` there and the bar is `UNDEFINED` — five bars of 914,700 below, because the NT8 averages emit from bar 0 and this module adds no warm-up of its own. The components are still computed through it, since they are knowable and a review can report them.

**Both agreement boundaries fall in the outer bands, which is the opposite of [#40] and [#41].** Deliberately: `min_agreement` counts components that must agree rather than cutting a continuum, so exactly that many agreeing is the case the parameter names.

**And the parameter has two settings rather than three.** Two float64 averages are essentially never exactly equal, so a `0` vote essentially never happens and the score only ever takes odd values — `-3`, `-1`, `+1`, `+3`, and nothing else across all 914,700 bars below. `2` and `3` therefore produce identical labels; `1` is the distinct one, and what it does is abolish the `MIXED` band rather than widen the outer ones. Keep the parameter, because that switch is worth having, and do not read it as a resolution knob.

**Gated.** 12 of the 14 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the five added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added trend_filter trend_fast_period trend_slow_period trend_slope_lookback trend_min_agreement` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and the interesting number is not in the profit-factor column.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, EMA 20 against EMA 50 with a 5-bar slope and unanimity, one combination run once per trend:

| cell  | bar share | signals | trades | profit factor | win rate | expectancy |
| ----- | --------- | ------- | ------ | ------------- | -------- | ---------- |
| DOWN  | 37.2%     | 4,400   | 3,280  | 0.657         | 0.316    | −10.79     |
| MIXED | 18.8%     | 461     | 335    | 0.426         | 0.304    | −17.85     |
| UP    | 44.0%     | 28      | 24     | **1.815**     | 0.458    | **+14.27** |
| all   | 100%      | 4,889   | 3,639  | 0.640         | 0.316    | −11.28     |

**The UP row is 24 trades and it is not a finding.** It is the best of three cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and its own `DeadCatParams` already refuses to signal there: 4,400 of 4,889 signals fall on `DOWN` bars, which are 37% of the series. That is the row that matters. **The label is not independent of the gates it sits beside** — a short-only archetype filtered by close-under-EMA and close-under-SMA has already applied most of a trend filter, and stratifying it by one more measures the overlap rather than the market. The label earns its keep on the review, where the trades were not selected by these gates, and on an archetype that trades both directions.

**The decomposition is exact here on both counts, and only the signal one is guaranteed.** Signals sum to 4,889 against the unfiltered 4,889, and trades to 3,639 against 3,639. The signal identity is the property — no bar is undefined, so the three filters partition every one — while the trade identity is this dataset being kind: the simulation holds one position at a time, so removing an entry frees later signals and the trade-level sum is approximate in general, exactly as [#40]'s and [#41]'s were. Do not promote it to a rule.

**Cost.** 0.76 s to prepare over 914,700 bars, dominated by the two EMAs and the vote pass; 11 bytes per bar per label — one float64 score and three `int8` votes, 10.1 MB, against a 39.3 MB dataset without it. The per-combination gate is 0.16 ms. Every one of those figures is against the 285 MB the same run's shared grids would have carried had the label gone through `keep_values`.

**It does not close [#73], and the sequencing note on both issues is now settled.** This is a coarse trend read as a *condition*, computed on the 1-minute averages the project already has. [#73] is a *gate* on an average computed on genuinely coarser bars, it needs [#30]'s resampler, and its hazard — stamping from the current incomplete coarse bar — does not arise here at all. They are different things and both are still wanted.

**The fourth filter was one too many to keep copying.** All three signal functions ended with the same four-gate chain, and adding a fourth pushed two of them past the complexity limit — which is the lint rule doing its job rather than getting in the way. They now end with `sim/filters.py`'s `apply_context_filters`, one conjunction shared by every archetype and reached through a structural protocol, so the next condition is a single edit rather than three.

**Smaller choices in `trend.py`, recorded here rather than in the module ([#105]):**

- **Three states, not the eight a 3-bit composite would give.** Time of day already multiplies every other stratification, and the point of a *compact* label is to survive a minimum-stratum guard on a few hundred real trades. The components are carried separately for the review to report, which is where "*which* one dissented" belongs.
- **`UNDEFINED` is −1, not a fourth trend**, for the reason [#40]'s and [#41]'s are: it cannot be swept into a filter by accident, and it passes no mask including `ALL_TRENDS`.
- **A fast period that is not strictly shorter than the slow one is refused.** Equal periods make the stack permanently flat, and a longer fast period inverts what the label means without changing a single name — the kind of error that reads as a result.
- **The slope is a sign, not a magnitude.** A threshold on it would be in points, which is neither comparable across instruments nor across eras; the sign is scale-free and the agreement count already provides the coarseness a magnitude threshold would be reaching for.
- **Exact equality votes neither way**, so the flat case exists in the arithmetic even though float64 averages essentially never reach it. Cheaper than arguing about which side it belongs on.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#30]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/30
[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#41]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/41
[#42]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/42
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
[#73]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/73
