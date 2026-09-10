---
paths:
  - "nqbt/stats.py"
  - "nqbt/trades.py"
  - "nqbt/annotate.py"
  - "nqbt/review.py"
  - "nqbt/propaccount.py"
  - "nqbt/chart.py"
  - "nqbt/guard.py"
  - "nqbt/notes.py"
  - "tests/test_numpy_summary.py"
  - "tests/test_trades_schema.py"
  - "tests/test_annotate.py"
  - "tests/test_review.py"
  - "tests/test_propaccount.py"
  - "tests/test_chart.py"
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
- **Sharpe and Sortino are refused, never approximated.** Both are annualised from daily
  totals, so a log with no `exit_time` and a leg matrix with no `day_codes` each raise
  `MissingTimesError` rather than returning the per-trade ratio the old branches scaled by
  `sqrt(252)` regardless. `docs/roadmap.md` § "Sharpe and Sortino are refused rather than
  approximated".
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
- **A simulated fill does not always land within its bar plus the slippage, and today that is
  unsettled rather than safe.** A profit target a bar gapped through fills at the target price.
  `docs/nt8-fidelity.md` records the gapped-*stop* rule and nothing for a limit, so which fill
  NT8 gives is untested (#244). On front-month bars it is 17 instances across 11 contracts and
  never more than a point; the 17-point cases are the continuous series' **leading span**, where
  the earliest cached contract supplies its own deferred bars. **Prefer excluding that span to
  widening `price_tolerance`**, and where a widening is unavoidable state it, print it, and keep
  it orders of magnitude below the roll offset so the back-adjustment guard still fires.
  `docs/roadmap.md` §M27.7.
- **A prop-account replay defines no performance statistic, exactly as a review does not.** Every
  figure about the *trades* is a `stats.summarise` field over the trades one account took; the
  fields `propaccount` owns are about the *account* — where the floor sat, what was withdrawn,
  what the attempts cost. A second definition of a win rate here would drift from the sweep's
  silently. `docs/roadmap.md` § "Replaying a prop account over the trade log".
- **It replays account rules and never adds one to the simulator.** `nqbt/sim/` models exactly one
  prop-firm rule — flat before the session close — because that one is also NT8's. A trailing
  threshold is accounting applied to a log that already exists, and moving it earlier would make
  every result conditional on a funding arrangement.
- **Open equity comes from `mae_points` and `mfe_points`, which are bar highs and lows.** Reaching
  into `data/tick/` for a truer equity path is the more-precise-than-NT8 error, the same one
  `chart` refuses when it will not draw a path between two fills. A rule set that reads open
  equity **refuses** a log whose excursion columns are null rather than reading "unknown" as
  "none", which would report a pass the account never had.
- **A firm that changes its rules when the account passes ships as two presets.** One
  `AccountRules` holds one rule set, and TakeProfitTrader trails end-of-day during its
  evaluation and intraday once funded. `TPT_50K_TEST` and `TPT_50K_PRO` are separate accounts
  rather than a phase-aware rule set, because the alternative is a second conditional
  definition of the floor inside the module whose premise is that there is one.
  `docs/roadmap.md` § "A firm that changes its rules at the pass ships as two presets".
- **`withdrawn` is what left the account and `payout` is what reached the trader.** The firm's
  `profit_split` separates them, and `net` is the payout minus the fees. They must stay apart:
  the reported `consistency` is a share of what *the account* made, so crediting the trader's
  share to `withdrawn` inflates it by the firm's cut. `1.0` is the "no rule" value, not `0.0`.
- **`propaccount` groups by the exchange trading day; `summarise` groups by the calendar date.**
  Both are right: a daily loss limit resets at the session open, and Sharpe is annualised from a
  count of calendar days. They disagree every evening, so do not "fix" one into the other.
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
- **A cross is an ordinary condition, and its cardinality is the whole check.**
  `annotate.crossed` defines no statistic; `review` ranks the composite label and `guard` puts
  it in the same family as everything else. What it must refuse is a product that outgrows the
  sample — trend × regime × phase is 81 strata over a few hundred trades — because a review
  would *skip* it silently rather than say why. `MAX_CROSSED_VALUES` is pinned equal to
  `review.MAX_STRATA` by a test and never imported, since `review` imports `annotate`.
  `docs/roadmap.md` § "Filtering trades by context and configuration".
- **A stored annotation carries the cut it was labelled at, on every row.** Two annotations
  written under different thresholds are two populations, and a query joining them reports one;
  `results.save_annotation` stamps the `LabelThresholds` under `results.CUT_PREFIX` rather than
  leaving the provenance to be remembered. `docs/roadmap.md` §M27.8.
- **`save_annotation` is the fourth door the notes rail is enforced at**, and the worst one to
  leave open: a note in a queryable column is one `GROUP BY` from rediscovering its own outcome.
- **A chart draws bar-close OHLC and never a path between two fills.** A line from the entry
  price to the exit price would depict what these bars do not record, and reaching for
  `data/tick/` to draw it truthfully is the more-precise-than-NT8 error. `tests/test_chart.py`
  pins it over the whole document: every line is a vertical wick or a horizontal level.
- **A chart is a debugging instrument and not a selection one**, and `chart.CAUTION` says so on
  every one, exactly as `review.STATUS` does in every report. It can settle whether the
  simulator did what the rule says; a dozen charts read to choose between rules is `guard`'s
  hazard in its most seductive form.
- **`annotate.resolve_bars` is shared, not copied.** It is the one route from a fill to a bar and
  it carries both checks with it — the range, and the stamps that catch a different series of the
  same shape. A chart drawn over bars an annotation would have refused is plausible at every
  stage and wrong at every price.
- **A fill outside its bar is refused by `annotate` and drawn by `chart`.** Back-adjustment is
  what puts one there, and a chart is the instrument that makes it visible, so the price domain
  is fitted to include every drawn price rather than clipping the marker away. The series is
  named in the corner of every chart, from `Dataset.price_basis`, for the same reason.
- **In `results.TRADE_VIEW` a parameter is a filter and never a grouping.** Neighbouring
  combinations share most of their entries, so grouping the view by `ema_period` counts the same
  trade many times and makes `guard`'s permutation null far too tight. Narrowing the population
  by one is fine; comparing across them is `campaign_report.axis_influence`'s job, one row per
  combination. The `combo_` prefix is load-bearing — `net_pnl` means the leg's on `trades` and
  the whole combination's on `combos`.
