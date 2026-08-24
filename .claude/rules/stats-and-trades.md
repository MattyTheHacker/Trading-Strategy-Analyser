---
paths:
  - "nqbt/stats.py"
  - "nqbt/trades.py"
  - "nqbt/annotate.py"
  - "nqbt/review.py"
  - "nqbt/guard.py"
  - "nqbt/notes.py"
  - "tests/test_numpy_summary.py"
  - "tests/test_trades_schema.py"
  - "tests/test_annotate.py"
  - "tests/test_review.py"
  - "tests/test_guard.py"
  - "tests/test_notes.py"
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
- **A separation is a candidate, not a finding**, and it stays one after the guard. The minimum
  stratum is one third of it; `nqbt/guard.py` is the shuffled-label null and the holdout, and
  both reports say so themselves. `docs/roadmap.md` §M11.4.
- **Read the family p-value, not the per-condition one**, unless the condition was chosen for a
  reason. `screen` permutes the P&L once per draw and re-separates every condition under that
  same permutation, so the maximum across them is the null for "the best of these" — which is
  what a ranking actually picked. Per-condition p-values are the multiple-comparisons machine
  one level up, and the noise-only test in `tests/test_guard.py` is what that looks like.
- **A shuffle moves the P&L and never the strata.** Sizes stay fixed, so the floor selects the
  same strata in every draw and only the association is destroyed. `guard.separate` is
  `review.rank_conditions`' number by a faster route — pinned equal, never re-derived — because
  `summarise` per stratum per draw is unaffordable.
- **A holdout re-reads the split, it never re-chooses it.** Best and worst are picked on the
  earlier trades and read on the most recent ones as they stand; re-picking there would hold
  nothing out. Its strata are small by construction, so `reported` gates `direction_held`.
- **A free-text note is stored and never evaluated.** It lives in an `nqbt.notes` sidecar keyed
  by `trade_id`, attaches only at `notes.alongside` for a viewer or an export, and
  `notes.check_excluded` refuses it at each of `annotate_trades`, `review` and `guard`. A note is
  written knowing the outcome, so stratifying by one would rediscover that outcome and lead the
  ranking — and `stratifiable` would *accept* one, so the rule cannot rest on a note failing to
  look like a condition. `docs/roadmap.md` §M11.5.
