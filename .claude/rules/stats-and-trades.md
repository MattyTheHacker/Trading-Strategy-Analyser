---
paths:
  - "nqbt/stats.py"
  - "nqbt/trades.py"
  - "tests/test_numpy_summary.py"
  - "tests/test_trades_schema.py"
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
