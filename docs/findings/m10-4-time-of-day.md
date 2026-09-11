---
id: M10.4
title: "M10.4 — time of day: done"
archetypes: []
issues: [43]
gates: []
outcome: calibration
verdict: >-
  The session phase label, cut on the exchange's own clock rather than the calendar's.
---

# ~~M10.4~~ — time of day: done ([#43])

`nqbt/timeofday.py`. Two forms of one clock: `SessionPhase`, seven coarse Eastern-time buckets, and `bar_of_session`, the integer index from the session open. Both come out of one `classify()` pass, both go through `resample.minutes_since_open`, and neither is a second session clock.

**The ET requirement is pinned by a test that states the failure, not only the behaviour.** Two sessions either side of the 2024-03-10 transition are labelled, and the test asserts both that the cash-open bars carry the same *Eastern* minutes and that their *UTC* minutes differ. Without the second half the test is a tautology and would pass over a UTC implementation on a winter window — which is exactly how this bug survives review.

**The end-of-bar convention decides the boundaries.** A bar stamped 09:30 covers 09:29–09:30 and is the pre-open; the first cash-open bar is stamped 09:31. Same off-by-one M13 found in `bucket_index`, and it is invisible in aggregate — the phase totals are right and only the edges move.

**Bar of session is derived from the clock, never counted off the data.** An ordinal count renumbers everything after a hole, so index *k* would mean a different time of day in different sessions — precisely the confound [#41]'s relative volume exists to divide out. It is therefore literally `resample.bucket_index`'s bucket, which is also what makes the two share a definition rather than each inventing one. `prepare` takes `bar_minutes` explicitly and `sweep_axes` passes the resolution it already knows; inference off the index's own gaps is the fallback, not the path.

**The filter is a bitmask integer, and that is what makes it sweepable.** A tuple of phases would have to join `not_sweepable`; a scalar mask is one value per combination, so `phase_filter=[CASH_OPEN.bit, ALL_PHASES]` is two combinations and "does this only work at the open?" is a sweep rather than a set of hand-run backtests. `ALL_PHASES` is the default and each archetype's signal **skips the conjunction entirely** at that value, which is why adding the field to two reconciled archetypes moved nothing.

That skip is not an optimisation. A bar carrying no label passes *no* mask, `ALL_PHASES` included, so ANDing the gate at the default would quietly drop those bars and move a result. The no-op has to be no call.

**Gated.** All 12 captured trade logs are byte-identical (`sha256` too); the two sweep summary tables differ by the added `phase_filter` column and are identical on every pre-existing column, dtypes included — `compare_trade_logs.py --added phase_filter` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First result, and it is a stratification rather than a finding.** Costed MNQ from 2024 (914,700 bars, stock `DeadCatParams`, $1.24 and 1 tick), one combination run once per phase:

| phase     | trades | profit factor | win rate | expectancy |
| --------- | ------ | ------------- | -------- | ---------- |
| OVERNIGHT | 1,550  | 0.561         | 0.297    | −9.76      |
| LONDON    | 656    | 0.599         | 0.326    | −10.70     |
| PRE_OPEN  | 348    | 0.665         | 0.342    | −10.88     |
| CASH_OPEN | 151    | 0.677         | 0.325    | −23.76     |
| MIDDAY    | 478    | **0.871**     | 0.383    | −5.57      |
| AFTERNOON | 297    | 0.709         | 0.327    | −12.54     |
| CLOSE     | 159    | 0.631         | 0.321    | −8.47      |
| all       | 3,639  | 0.666         | 0.322    | −10.24     |

The seven counts sum to the unfiltered 3,639 exactly, which is the property that makes this a decomposition and not seven overlapping subsets; a test pins it. **Do not read the MIDDAY row as an edge.** It is the best of seven cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and no cell reaches a profit factor of 1. What it does say is that the aggregate 0.666 was averaging populations that differ by 55%, which is the argument for the milestone rather than a result from it.

**The prediction about the last phase was directionally right and quantitatively small.** `session_close_share` reads 0.0016 on CLOSE against 0.0001 overall — an order of magnitude, and still tiny, because a 1-minute DeadCatBounce holds for minutes. The artefact is real and will grow with bar size ([#30]); on this data it is not what makes the CLOSE row look the way it does. Read the column before attributing anything to the clock, and expect it to matter at 15 and 30 minutes where it does not here.

**Cost.** `needs_time_of_day` is requested the way VWAP is — only when some combination actually narrows the phases — and adds three arrays (`int8`, `uint8`, `int32`) over the series. The eight-combination sweep above took 0.6 s over 914,700 bars, so the gate itself is not measurable against the simulation.

**Smaller choices in `timeofday.py`, recorded here rather than in the module ([#105]):**

- **Seven buckets, chosen for what happens in them rather than for equal length.** The overnight hours are one bucket because little distinguishes 20:00 from 01:00; the hour after the cash open gets one to itself because it is the most distinctive hour of the day. Fewer buckets is the point — time of day multiplies every other stratification, and seven phases against five regimes is already 35 cells, which a minimum-stratum guard on a few hundred real trades has to survive.
- **`SessionPhase.CLOSE` is structurally anomalous**, because it contains the forced flat ([#16]). Its exits are decided by the clock rather than the rules, so a stratification will show it as different whatever the market did. `FORCED_EXIT_PHASE` names it so a caller can exclude it without working out which one it is.
- **`OUT_OF_SESSION` is −1, not an eighth phase**, so it cannot be swept into a filter by accident and a `groupby` over the labels reads as obviously wrong rather than quietly counting stray prints as an eighth hour of the day.
- **`PHASE_STARTS` is written as ET wall-clock times**, because that is what the boundaries mean: `time(9, 30)` is the cash open, where an offset of 930 minutes is a number nobody can check. `phase_start_minutes` converts them and validates on **every** call rather than once at import — the boundaries are relative to the template's own open, so a template opening elsewhere reorders them, and a set that no longer ascends would mislabel whole phases through `searchsorted` without raising.
- **`infer_bar_minutes` takes the mode of the gaps**, not the minimum or the mean: every session has a one-hour break and the archive has holes, so both of those measure the gaps rather than the bars.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#16]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/16
[#30]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/30
[#41]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/41
[#43]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/43
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
