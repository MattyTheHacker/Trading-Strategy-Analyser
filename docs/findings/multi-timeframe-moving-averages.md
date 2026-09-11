---
title: "Multi-timeframe moving averages"
archetypes: [EmaCrossover]
issues: [73]
gates: [1]
outcome: negative
verdict: >-
  A higher-timeframe moving average is a condition rather than an archetype, and it does not separate.
---

# Multi-timeframe moving averages ([#73])

`nqbt/higher_timeframe.py`. An EMA computed on bars [#30]'s resampler aggregates, then stamped back onto the fine index so that a 1-minute strategy can gate on it. "Only short below the hourly trend" is standard practice and was not expressible before this, because every average the project computes reads the 1-minute close. Price against the coarse average is one `int8` per bar — `BELOW`, `AT`, `ABOVE`, `UNDEFINED` — and `higher_timeframe_filter` is a bitmask integer for exactly the reason `phase_filter`, `regime_filter`, `volume_filter` and `trend_filter` are.

**The projection rule is "the most recently *completed* coarse bar", and the boundary belongs to the completed side.** Both indices are end-of-bar, so the 1-minute bar stamped 19:00 and the 60-minute bar stamped 19:00 close at the same instant and the fine bar may read it; every fine bar strictly inside an unfinished coarse bar reads the one before. That is `searchsorted(..., side="right") - 1` and nothing else. The alternative reading of the ticket — lag the whole series by one bucket — was rejected: it throws away an hour of knowable information at every bucket close, and it is *not* the more conservative choice it looks like, because the existing 1-minute gates already compare `close[i]` against an `ma[i]` that includes it. One rule across both resolutions, not two.

**The hazard is not hypothetical and the test is built to fail.** `test_a_bar_inside_an_unfinished_coarse_bar_cannot_read_it` runs a series of three flat 5-minute buckets and then one whose *close alone* sits above the fine closes before it, with the period at 1 so the coarse average is the coarse close and every expected value is readable by eye. The four bars inside that bucket must read 100.0 and label `ABOVE`; a leak reads 150.0 and labels `BELOW`. Verified by introducing the leak — six tests fail, including the projection's own comparison against an explicit loop over the coarse stamps. **That loop is deliberately not a second `searchsorted`**: a test that re-derives the answer the implementation's own way cannot catch the implementation being wrong.

**`AT` is one bar in 914,700, and it is kept anyway.** Two float64 values essentially never coincide, which is the same finding [#42] recorded about a `0` vote — but "essentially never" is not "never", and giving equality its own state is cheaper than arguing about which side it belongs on. `UNDEFINED` is 59 bars, exactly the fine bars before the series' first 60-minute bar closes, and it passes no mask including `ALL_SIDES` — which is why each signal skips the gate entirely at the default rather than ANDing a no-op mask.

**Two validations that exist because their failure is silent.** A 1-minute higher timeframe is the existing moving-average gate under another name and is refused at the key. And a coarse resolution that is not a *proper multiple* of the bars it aggregates from is refused at the grid, against the frame's own resolution: asking for a 7-minute average of 5-minute bars buckets across bar boundaries and produces a number rather than an error. Both are checked whatever `higher_timeframe_filter` admits, so a nonsense resolution cannot ride along inertly until the filter is swept onto it.

**Gated.** 12 of the 14 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the three added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added higher_timeframe_filter higher_timeframe_minutes higher_timeframe_period` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**Cost.** 0.22 s to prepare over 914,700 bars on top of a 0.54 s baseline, one resample per distinct resolution however many periods share it; 9 bytes per bar per average — one float64 value and one `int8` side, 8.2 MB, against a 39.3 MB dataset without it. The per-combination gate is 0.44 ms. Nothing here touches `keep_values`: the coarse average is its own series, not a row of the shared moving-average grids.

**The stratification, and the reason it is more informative than [#42]'s was.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, a 60-minute EMA(50), one combination run once per side:

| cell  | bar share | signals | trades | profit factor | win rate | expectancy |
| ----- | --------- | ------- | ------ | ------------- | -------- | ---------- |
| BELOW | 40.9%     | 2,326   | 1,743  | 0.730         | 0.349    | −9.75      |
| AT    | 0.0%      | 0       | 0      | —             | —        | —          |
| ABOVE | 59.1%     | 2,563   | 1,895  | 0.528         | 0.285    | −12.71     |
| all   | 100%      | 4,889   | 3,638  | 0.640         | 0.316    | −11.29     |

**The signals split almost in proportion to the bars, and that is the point.** [#42]'s trend label put 4,400 of 4,889 signals on `DOWN` bars that were 37% of the series, because a short-only archetype already filtered by close-under-EMA and close-under-SMA has applied most of a 1-minute trend filter — stratifying by one more measured the overlap rather than the market. Here 2,326 of 4,889 signals fall on 40.9% of bars. **The coarse average is measuring something the archetype's own gates have not already applied**, which is what a higher timeframe was wanted for.

**No cell clears a profit factor of 1, so there is no finding to guard.** `BELOW` at 0.730 against 0.640 unfiltered is the better half of a bad strategy and is the best of three cells chosen after looking; the standing fact that DeadCatBounce is unprofitable across every combination tested is unchanged. What the run establishes is that the mechanism works and that the side is not collinear with the gates beside it — not that the gate helps.

**The decomposition is exact on both counts here, and only the signal one is guaranteed.** Signals sum to 4,889 against the unfiltered 4,889 and trades to 3,638 against 3,638. The signal identity is the property — `AT` is one bar and no signal falls on it, so the three sides partition every defined bar. The trade identity is this dataset being kind, exactly as [#40]'s, [#41]'s and [#42]'s were: the simulation holds one position at a time, so removing an entry frees later signals. Do not promote it to a rule.

**The three notions of "the higher-timeframe trend" are now separated rather than overlapping.** Here the strategy runs on 1-minute bars and *consults* a coarse average. [#42] reads a coarse *condition* off 1-minute averages. [#30] runs the whole strategy on coarse bars. All three share `nqbt/resample.py` and nothing else, and the sequencing note both tickets carried is discharged: all three were wanted.

**Smaller choices in `higher_timeframe.py`, recorded here rather than in the module ([#105]):**

- **The kind is fixed at EMA**, for the reason `trend.KIND` is: one definition, so the same parameters mean the same measurement everywhere, and `HigherTimeframeKey` gains a field the day an SMA average is actually wanted. [#72] made the fine gates' kind sweepable and deliberately did not reach here, so that day has not arrived.
- **The period counts coarse bars, never fine ones.** `higher_timeframe_period=50` at `higher_timeframe_minutes=60` is 50 hours, not 50 minutes. Naming it `period` rather than `bars` is deliberate: it is the same word `ema_period` uses, on a different series.
- **`UNDEFINED` is −1, not a fourth side**, for the reason [#40]'s, [#41]'s and [#42]'s are: it cannot be swept into a filter by accident, and it passes no mask including `ALL_SIDES`.
- **The average is projected onto every fine bar**, which is where this differs from `volume`'s baseline. A moving average is continuous across the maintenance break and across a session boundary — that is what makes it a higher timeframe — and the existing 1-minute gates do not special-case those bars either.
- **One resample per distinct resolution, whatever periods share it.** Two periods on the hourly cost one aggregation and two EMAs over a series 60 times shorter than the archive.

**The one question this cannot settle from Python, and why a trade list is the wrong tool for it.** NT8 serves a secondary series through `Closes[1][0]`, and *when* that series updates relative to a same-stamped primary bar is a property of its event ordering rather than of the arithmetic. **For an EMA the two readings are algebraically indistinguishable**: the update moves the average toward the close and never past it, so `close − EMA_new = (1 − α)(close − EMA_prev)` keeps the sign and the gate never flips. Over 914,700 MNQ bars at 5/15/60 minutes × periods 3/20/50 the label differs on exactly one bar in every configuration — the first coarse close, where the lagged reading is still in warm-up — and on zero bars where both are defined. A reconciliation would come back 100% and prove nothing. An **SMA** would: it drops the oldest value out of its window and can move past the close, giving 842 differing bars at 15-minute SMA(20), which is the case a coarse SMA would make live.

**So the instrument is a per-bar probe, not a trade list — and it has been run ([#183]).** `ninjatrader-scripts/Strategies/NqbtHigherTimeframeProbe.cs` records `Times[1][0]` against `Time[0]` on every 1-minute bar and writes the coarse series NT8 built beside it, so the boundary is decided on every coarse close rather than on the zero trades that would discriminate. Over `MNQ 03-24` with a 60-minute secondary series — 1,479,760 1-minute bars, 24,826 coarse bars — **the projection agrees on 1,479,701 of 1,479,701 comparable bars, and on all 24,752 coarse closes NT8 reads the bar stamped alongside the fine bar.** Seeding agrees exactly on EMA(3), EMA(50), SMA(3) and SMA(50); the warm-up is 59 bars against 59; anchoring is exact over the 1,525 coarse bars of the front-month window, the earlier prefix being NT8's merged series. Per-question figures: `docs/nt8-fidelity.md` § "And so is the higher-timeframe average".

**That the probe reports which *bar* was read, rather than what the average computed to, is what made it worth building.** The result does not depend on the arithmetic being monotone, so it settles the boundary for every moving-average kind at once and the SMA case above is answered without ever needing the trade list [#72] would have required.

`tools/reconcile_higher_timeframe.py` compares the export on all four questions separately, and `tests/test_reconcile_higher_timeframe.py` exercises each check against an export perturbed in the one way that check exists to catch — for the projection check, that perturbation is the other candidate rule. Two of its own defects were found by the real export and are pinned: reading `read_csv`'s microsecond stamps as nanoseconds put the whole comparison in 1970, the trap `resample.py` already records; and counting the warm-up over the *archive* rather than the probe's own bars compared 59 leading bars against 5 and called it a disagreement.

**The gate is checked whole, not only in its parts**: composing NT8's own close against NT8's own coarse EMA into a side reproduces `higher_timeframe_labels` on all 1,479,760 bars, the six `AT` bars included. A leg-for-leg trade-list diff would only re-exercise the conjunction and the bracket, which this change leaves byte-identical and which are already reconciled on other archetypes — so it is deliberately not planned rather than outstanding.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#183]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/183
[#30]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/30
[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#41]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/41
[#42]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/42
[#72]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/72
[#73]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/73
