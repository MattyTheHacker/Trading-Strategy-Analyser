---
paths:
  - "nqbt/stats.py"
  - "nqbt/trades.py"
  - "nqbt/annotate.py"
  - "nqbt/review.py"
  - "tests/test_numpy_summary.py"
  - "tests/test_trades_schema.py"
  - "tests/test_annotate.py"
  - "tests/test_review.py"
---

# Statistics and the trade log

- **Trade logs are one row per leg exit**; `summarise` aggregates to one row per trade. NT8's
  "total trades" is the leg count, so use `leg_summary` when reconciling.
- **`r_multiple` uses planned risk (`stop − trigger`)**, matching how the C# places targets.
  Under an ATR stop it is volatility-scaled rather than structure-scaled, so EmaCrossover
  results are **not comparable to DeadCatBounce results at the same R numbers**.
- **Both summary paths share `_summarise_arrays`** and differ only in how the per-trade vectors
  are obtained — which is what reduces "do they agree?" to "do they group the legs the same
  way?". **Do not re-inline it into either caller.** `docs/roadmap.md` § "The numpy-native
  summary path".
- **Pandas' `groupby.sum` is Kahan-compensated**, and `_grouped_sum` carries the same
  compensation term for that reason alone. A plain running sum disagrees with pandas in the
  last bit on real trades; `np.add.reduceat` disagrees more often.
- **`Dataset.day_codes` is local, not UTC.** `summarise` groups daily P&L by
  `DatetimeIndex.date`, which is the index's timezone — a UTC-only version passes every test on
  the UTC archive and is an hour out on a `Europe/London` index.
- **`validate_legs` is the producer boundary a sweep crosses**, since a sweep never calls
  `validate`. Same invariants plus one: `exit_reason` must be in `EXIT_REASONS`, because only
  the simulator can have written it.
- **A flip is two trades in the log**, each paying its own costs — economically a reversal, and
  it must be described that way against published crossover results.
- **Annotation joins a fill to the bar stamped *strictly after* it**, so a bar's own stamp is a
  fill time one bar late and a log carrying bar indices keeps them. Getting this wrong shifts
  every condition by one bar and biases the whole review silently. `docs/roadmap.md` §M11.2.
- **Every annotated fill price is checked against its bar's range**, because that is the only
  thing that catches a back-adjusted series — the lookup succeeds and every comparison is out by
  the roll offset. `price_tolerance` admits a simulated run's slippage and nothing wider.
- **A review is `summarise` over subsets and defines no statistic of its own.** A stratum's
  row is the summary's fields read off; a second definition of a win rate would drift from the
  sweep's silently, because both numbers would look reasonable. `docs/roadmap.md` §M11.3.
- **A log leaving a column null omits the statistics that column feeds, and says why.**
  `summarise` refusing an imported log is the correct half; the review's half is the omission
  with the producer's reason. The absent columns are filled only so `summarise` runs, and every
  field a filled column feeds is dropped by name first — **no placeholder may reach a reported
  number.**
- **Only a categorical condition is stratifiable.** Cutting a raw series is a threshold choice,
  and `LabelThresholds` is where a review states the cut it tested.
- **The final session phase contains the forced flat**, so a poor result there is the clock
  until `session_close_share` says otherwise — and that share is omitted, never zeroed, when a
  log's exit reasons are its source's own vocabulary.
- **A separation is a candidate, not a finding.** The minimum stratum is the whole guard so
  far; the permutation test and the holdout are #48, and the report says so itself.
