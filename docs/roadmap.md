# Roadmap

Planned work, in dependency order. Nothing here is built. `CLAUDE.md` carries the one-line
summaries; this file carries the reasoning and the traps.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the
project's own docs first, [imantrading_concept_extraction.md](imantrading_concept_extraction.md)
second. The imantrading notes are a source of framing and of numeric definitions we lack, not
a source of priorities.

---

## Order of work

Dependency order, not priority order — each item's prerequisites sit above it.

| # | Work | Why here |
|---|---|---|
| ~~1~~ | ~~Re-export NQ manually~~ | **Done 2026-08-11.** 19 contracts, all 18 rolls on genuine crossovers, archive 4.09M → 4.60M bars. Also exposed a stub-session bug in roll detection, now fixed. |
| ~~2~~ | ~~Run the simulation against NQ~~ | **Done 2026-08-11.** Runs end to end including parallel sweeps. Instrument scaling proven exact: same bars through both specs give identical geometry and ×10 gross P&L on every leg. |
| 3 | **M9** — split context from simulation | Gate for everything below. Behaviour-preserving moves only, with the reconciliation re-run either side as the check. |
| 3a | **M13** — bar resolution as a sweep axis | Sits with M9 because the resampler is a context concern and lands in the same file. Independent of M10/M11, so it can move later if the review is more urgent — but doing it here means `results` gains its `resolution` column before the stale DuckDB re-run rather than after. |
| 4 | **M10** — regime, relative volume, trend, time of day | Dual-use: the review needs them, and they let existing sweep results be stratified rather than averaged. |
| 5 | **M11** — the trade review | The stated goal. Needs 3 and 4. |
| 6 | **M7** — random-entry arm first, then walk-forward and Monte Carlo | The control arm shares machinery with §11.4's permutation test, so it is cheaper right after M11 than before it. |
| 7 | Numpy-native summary path | ~3×, composes with the parallel speedup. Worth doing when walk-forward multiplies sweep runtime by the window count, not before — a 1,536-combination sweep is 10 s today. |
| 8 | **M12** — web GUI | Gated on the review's outputs being stable. |

**Next up: M9.** Steps 1 and 2 are complete, so the refactor is the live item.

### Outstanding: reconcile NQ against NT8

**Not done, and not scheduled above because it needs NinjaTrader time rather than code
time.** Do it when convenient; it does not block M9.

NQ inherits its fill-semantics confidence from MNQ rather than earning it. Everything
downstream of the bars is proven instrument-agnostic — same bars through both specs give
identical trade geometry and gross P&L of exactly ×10 on every leg — so the *simulation*
is not in doubt. What is unverified is whether NT8 itself behaves identically on NQ:
fill semantics, the managed-order cancellation, `IsFillLimitOnTouch`, ambiguous-bar
resolution. There is no reason to expect a difference, which is precisely why an
unexamined assumption could sit there indefinitely.

The recipe, matching how MNQ was done (`docs/nt8-fidelity.md`):

1. Pick one contract with a clean full window — `NQ 03-24` mirrors the MNQ run.
2. Strategy Analyzer → same window, EMA 21 / SMA 60 / SMA 175, all six filters on, zero
   commission, zero slippage.
3. Export **Trades**, not the summary. Summary statistics hide every rule that matters.
4. Compare leg-for-leg against `runner.run_deadcat(..., instrument=NQ)`.
5. Exclude both window ends: NT8 warms indicators from bars before the start, and the
   export can stop before NT8's backtest did.

Expected outcome is agreement at the MNQ level (1143/1144). **A disagreement would be the
interesting result** — it would mean something in NT8 is instrument-dependent in a way the
fidelity record does not capture, and that would be worth knowing before any NQ result is
trusted.

Not scheduled: **M8** (premise measured and mostly false — see `CLAUDE.md`), the three
unbuilt spec features, `NG 02-26`'s silent skip, and the MAE/MFE definition mismatch.

---

## Standing constraint, extended

The prime directive — match NT8's default bar-close fidelity, never exceed it — governs the
**simulation** side only.

The review side takes real fills, which are genuinely tick-precise, and that is not a
fidelity violation because nothing is being simulated. **The trap is letting that precision
leak backwards.** A real trade filled at 18076.75 mid-bar is evidence about the market; it is
not evidence that the simulator should model intrabar fills. Keep the annotation path
read-only with respect to `nqbt/sim/`: the review may *describe* what a real trade did and
compare it against what the simulator would have done, but it must never feed a fill rule
back into the `@njit` loop. If those two ever need reconciling, the trade list wins for
*facts* and NT8 wins for *fill semantics*, and they are different questions.

---

## M9 — Split market context from strategy simulation

**Why.** The review system and the backtester need the same three things: bars, indicator
conditions, and a trade log with statistics over it. Only the middle step — the strategy —
differs. Today the shared parts are physically inside the strategy-specific parts, so
building the review side against the current layout means either importing from `nqbt.sim`
(wrong: the review has no strategy) or reimplementing (wrong: two definitions of "close is
below the EMA" that will drift).

| Concern | Backtest | Review | Status |
|---|---|---|---|
| bars, splicing, sessions | ✓ | ✓ | already shared |
| indicators, condition arrays | ✓ | ✓ | already shared (`conditions.py`) |
| `Dataset` / `prepare` | ✓ | ✓ | **lives in `sim/runner.py` — must be lifted out** |
| regime classification | later | ✓ | does not exist |
| relative volume | later | ✓ | does not exist |
| trade-log schema | ✓ produced by `@njit` | ✓ produced by import | **implicit — must be formalised** |
| summary statistics | ✓ | ✓ | already shared (`stats.py`) |
| stratification by condition | later | ✓ | does not exist |
| DuckDB persistence | ✓ | ✓ | shared, needs a `source` tag |

**The work.**

1. **Lift `Dataset` and `prepare` out of `nqbt/sim/runner.py` into `nqbt/context.py`.**
   Nothing about them is DeadCatBounce-specific; `deadcat_signal` and `run_deadcat` stay
   behind in `sim/`. Keep the class name `Dataset` rather than renaming to `MarketContext` —
   the churn buys nothing and the name is already referenced across the docs and the fidelity
   record.

2. **Formalise the trade-log schema in `nqbt/trades.py`,** extracted from
   `sim/types.COLUMNS`. This is the contract both producers meet. Three additions are
   required, because the current schema quietly assumes it came from DeadCatBounce:

   - **`direction`** (+1 long / −1 short). Currently implicit: the archetype is short-only, so
     nothing records it. A manual log has both, and every P&L and MAE/MFE sign convention
     downstream depends on it.
   - **`instrument`**. A real trading history spans NQ and MNQ, whose tick values differ 10×.
     A trade log without this cannot be summed in dollars — and `instruments.py` exists
     precisely because that bug has bitten before.
   - **`source`** (`sim` / `manual`). Real and simulated trades will share a DuckDB table;
     without a tag, one careless query averages them together.

   Fields the simulator produces that a manual trade cannot — `ambiguous_bar`, `r_multiple`
   when no stop was recorded, `mae_points`/`mfe_points` until they are reconstructed from
   bars — become explicitly nullable, with the nullability documented rather than discovered.

3. **Add `trades.validate(frame)`** and call it at both producers' boundaries. A schema that
   is only a convention will drift the first time someone adds a column.

4. **Enforce the dependency rule:** `context.py` knows nothing about trades; `sim/` and the
   trade importer both depend on `context.py`; `stats.py` and the review layer depend on the
   trade schema and nothing else. Concretely: **`stats.py` must not import from `nqbt.sim`.**
   It currently doesn't — this makes that a rule instead of an accident.

**Risk.** This moves validated code. The NT8 reconciliation (1143/1144) is the thing being
protected, so: no behaviour changes in the same commit as the moves, and the full suite plus
a re-run of the reconciliation window before and after, compared byte-for-byte.

---

## M10 — Prerequisites the review needs and we don't have

The review is meant to score trades against "overall trend, MAs, volume, directional vs
consolidation, time of day". Three of those five have no implementation.

**10.1 Regime classification — `nqbt/regime.py`.** Directional / consolidating /
unclassifiable, as a 1D label array in the `conditions.py` mould, computed once in `prepare`.

Use **Kaufman's efficiency ratio** as the first classifier:
`abs(close[t] − close[t−n]) / Σ|diff(close)|` over the lookback. Bounded 0–1, ~3 lines of
numpy, no TA-Lib dependency and therefore no NT8-mismatch problem. Above the upper threshold
is directional, below the lower is consolidating, and the band between them is the
unclassifiable no-trade state — which gives the third category for free rather than as a
special case. Lookback and both thresholds are sweepable axes.

ADX is the familiar alternative and is in TA-Lib, but it is laggier, less interpretable, and
would need the same NT8-parity check the moving averages needed. Efficiency ratio first;
ADX only if ER proves inadequate.

**10.2 Relative volume.** Volume against its own recent norm, not a raw number.

**The trap:** intraday volume has a strong time-of-day shape — the 09:30 ET cash open dwarfs
03:00 — so a plain rolling average makes every morning bar "high volume" and every overnight
bar "low volume", which is a clock, not a signal. Normalise against the same time-of-day
across recent sessions (bar-of-session median over a trailing window), not against a rolling
window of adjacent bars.

**10.3 Trend summary.** A compact label rather than a wall of MA booleans: price against the
slow MA, the slow MA's slope sign, and the fast/slow stack order. Derived from the existing
`MovingAverageGrid`, so no new indicator work — but it needs `keep_values=True`, which is the
66 MB → 595 MB memory switch. For review over one account's trade history that is fine; it
must not be switched on for sweeps by default.

**10.4 Time of day — `nqbt/timeofday.py`.** A first-class dimension for both the sweep
statistics and the review, not a review-only afterthought. Two forms, because they answer
different questions:

- **Session phase**, a coarse categorical label: overnight (18:00 ET open), London, NY
  pre-open, cash open, midday, NY afternoon, close. Few enough buckets to survive the
  minimum-stratum guard on a small sample.
- **Bar of session**, an integer index from the session open. The finer form, and the one
  relative volume already needs — 10.2's normalisation is per bar-of-session by
  construction, so the two share a definition rather than each inventing one.

**Measure it in exchange local time (ET), never UTC.** The market's rhythm follows the cash
open at 09:30 ET, which is 13:30 or 14:30 UTC depending on the date. Bucketing on UTC smears
the single most distinctive hour of the day across two different buckets for half the year,
and the result looks like noise rather than an error. Bar timestamps are stored UTC and
`sessions.classify` already produces the ET conversion, so the label comes from there.

**The multiple-comparisons cost is real and compounds.** Hour of day multiplies every other
stratification: seven session phases against five regimes is 35 cells before any MA gate.
§11.4's guard applies with more force here, and the coarse label exists specifically so the
review has a form that survives a few hundred trades. Bar-of-session is for the sweep, where
the sample is 5,000+ trades.

**Second-order payoff:** once the label exists it is also a *sweepable entry filter* — trade
only during phases X and Y — which is a single extra boolean in the condition AND, not a new
`@njit` function. Worth having as an axis before concluding an archetype has no edge, since
a rule that works only at the cash open reads as unprofitable when averaged across 23 hours.

---

## M11 — Manual trade review

**11.1 Import — `nqbt/trade_import.py`.** Manual trades in, canonical schema out.

Structured as a **thin adapter per source** — the adapter is the only format-aware code in the
project, and everything downstream sees the canonical schema alone. Adding a second source
later is one function, not a second pipeline.

**Adapters must declare what they could not recover.** Which optional fields a source carries
determines what the review can compute. The adapter returns the populated field set alongside
the frame so the review *omits* unavailable statistics with a stated reason. The failure to
avoid is a column of zeros or NaNs flowing into `stats.summarise` and being reported as if
measured.

### Source decided: the NT8 executions grid

Control Center → Executions, exported as CSV. Columns: `Instrument, Action, Quantity, Price,
Time, E/X, Position, Name, Commission, Account display name`.

It carries two fields that make the whole import tractable:

- **`Position` is the trade-boundary key.** It is the running position *after* each fill —
  `4 S`, `3 S`, `-` — so a value of `-` closes a trade. Executions group into trades without
  inferring state from order ids.
- **`Name` gives the exit reason.** `Stop1..4` versus `Exit` maps directly onto the existing
  `exit_reason` field, which is normally unrecoverable from a fills export.

**Rejected: the Control Center log grid** (`Time, Category, Message`). It is the only place
stop and target *levels* live, so it is the only route to planned risk and `r_multiple` — but
the levels it holds are not usable as intent. In the sample session both stop orders were
submitted at 29919 against a 29769 entry and dragged to ~29782 within three seconds: 29919 is
an ATM template default, so "planned risk from the initial stop" computes 150 points of risk
on a trade that actually risked ~14. Recovering true intent needs a rule like "the first stop
level that is not the template default", which is exactly the kind of heuristic that silently
corrupts a dataset. A wrong R is worse than no R, because it looks like a measurement.

**Consequence, accepted:** no planned risk, no `r_multiple`, no MAE/MFE from the source. The
review reports dollars, points and exit reason. MAE/MFE could later be *reconstructed* from
bars between entry and exit, which is a different and honest calculation — flag it as derived
if it is ever added.

**Out of scope, noted:** the log also records placed-then-cancelled entry orders — roughly 20
against 3 fills in the sample. That is a real behavioural signal about order management, and
the executions grid cannot see it. It is a different question from "which trades worked", so
it stays out rather than dragging the log parser in.

### Traps, all confirmed against the sample export

- **Two date formats in one file.** Row timestamps are `10/08/2026` (DD/MM/YYYY, 12-hour with
  AM/PM); the `Time=` field *inside* log messages is `8/10/2026` (M/D/YYYY). Same instant,
  both orderings. Parse row timestamps as DD/MM and never infer the format from the values —
  the first twelve days of any month are ambiguous and will parse silently wrong.
- **Reverse-chronological, and ties need file order, not a sort.** NT8 emits newest-first.
  Three fills sharing one second (`6:07:25` → `Stop2, Stop3, Stop4`) are only correctly
  ordered by reversing the file; sorting on the timestamp scrambles them and corrupts the
  position walk. Reverse the rows, do not sort.
- **`Commission` is `$0.00` and must not be trusted.** The account is a funded prop account
  that does charge commission; NT8 simply has no schedule for it. Costs come from
  `instruments.py`, or every trade reads better than it was.
- **No timezone anywhere in the file.** Bars are UTC; these are NT8 display times. `6:07 PM`
  is equally plausible as BST or ET and the data cannot disambiguate. Require it as explicit
  configuration and record it on the imported rows.
- **NT8 matches partial exits FIFO.** After exiting 1 of 4 (entries 2 @ 29769.00 and
  2 @ 29768.50) the log reports average 29768.6667, reachable only by consuming one unit of
  the 29769.00 entry. Trade-level P&L is unaffected — total in against total out — but the
  schema is per-leg, so per-leg attribution must use FIFO to agree with NT8.
- **Trailing comma on every row** yields a phantom empty column.

### Worked example, for the adapter's first test

Reversed, the sample resolves to two trades:

```
5:58:49  Sell 2 @ 29769.00  Entry  -> 4 S total, avg 29768.75
6:00:29  Buy  2 @ 29782.75  Stop1  -> flat   trade 1: -43.25 pts = -$86.50
6:03:07  Sell 4 @ 29767.00  Entry  -> 4 S
6:07:25  Buy  1 @ 29783.25  Stop4  -> flat   trade 2: -43.50 pts = -$87.00
```

−$173.50 gross across two trades, derived from the executions file alone. Use it as the
adapter's fixture.

The remaining traps, which are about joining trades to bars rather than parsing:

- **Back-adjustment will silently corrupt this.** A real fill at 18076.75 does not appear
  anywhere in a back-adjusted continuous series, because back-adjustment shifts every
  historical price by the cumulative roll offset (−204 to −296 points in 2024–2026). Manual
  trades must be annotated against the **raw** series or the per-contract cache. Annotating a
  real trade against `MNQ_backadj.parquet` produces plausible-looking nonsense — the bar
  lookup succeeds, and every price comparison is wrong by a few hundred points.
- **Bar alignment.** Bar timestamps are end-of-bar. A fill at 14:23:47 belongs to the bar
  stamped 14:24. Off-by-one here shifts every condition by one bar and quietly biases the
  entire review; write it down and test it.
- **Timezone.** NT8 exports UTC. A broker statement or a hand-kept journal probably is not.
  Require an explicit timezone on import rather than guessing.
- **Scale-outs map to legs.** A position exited in three pieces is one `trade_id` and three
  `leg` rows, matching the existing convention — not three trades. Getting this wrong
  triples the sample size and makes the win rate meaningless.
- **Coverage gaps.** Trades on instruments or dates outside the cache must be reported and
  excluded, not silently dropped. Make this a **coverage report** the importer emits — per
  trade, whether its instrument and date are cached — so how much of the history is actually
  reviewable becomes a measured number rather than an assumption. Note that no NQ data has
  ever been through the pipeline, so any NQ trade is currently out of coverage.

**11.2 Annotate — `nqbt/trades.py` or a sibling.** Join each trade to the `Dataset` at its
entry bar (and optionally its exit bar), producing one annotation row per trade carrying
every precomputed condition. This is the piece that makes the whole thing work, and it is
deliberately strategy-agnostic: it does not care whether the trade came from a simulation or
from a broker.

**11.3 Review — `nqbt/review.py`.** The actual question: which trades worked, and what was
true when they did.

Stratify realised P&L by each annotated condition and report per stratum: n, win rate,
expectancy, profit factor, average R. Rank conditions by how much they separate winners from
losers. Reuse `stats.summarise` unchanged — that is the point of M9.

**Time of day is a headline dimension, not one condition among many.** When during the
session a trade was taken is the stratification most likely to show real structure in a
discretionary record, because it captures attention, liquidity and the trader's own routine
at once — and unlike a moving-average gate, it is not something the trader was consciously
optimising. Report it first, using 10.4's coarse session-phase label, paired with relative
volume so "this hour is always busy" is separable from "this hour was unusually busy".

Because the same annotation path runs on simulated logs, the identical breakdown applies to
a sweep's trades — which is how a time-of-day finding in a few hundred real trades gets
tested against thousands of simulated ones instead of being believed on its own.

**11.4 The statistical guard, which is not optional.**

A few hundred manual trades against a few dozen candidate conditions is a multiple-comparisons
machine. Some condition *will* split that sample impressively, and most of the time it will be
noise. A review system without a guard here is worse than no review system, because it
produces confident, specific, wrong conclusions and they feel earned.

Three mitigations, all cheap:

- A minimum sample per stratum before a split is reported at all — the same discipline
  `sweep.rank(min_trades=...)` already enforces, for the same reason.
- A **permutation test**: shuffle the condition labels against the P&L, recompute the
  separation a few thousand times, and report where the real split falls in that
  distribution. This is the same null-model machinery as the random-entry control arm in the
  imantrading notes §3.3, and building one gets most of the other.
- Hold out the most recent N trades and report the finding's performance there separately.

State the output's status plainly in the report itself: **hypothesis-generating, not
confirmatory.**

**11.5 Discretionary context — recorded, deliberately excluded from the evaluation.**

Free-text context on a trade (why it was taken, what was going on, a screenshot reference)
gets stored and shown, but is **never** an input to annotation or stratification.

This is worth enforcing structurally rather than merely intending, because the reason is
stronger than a preference. Notes are written after the fact and are contaminated by knowing
the outcome — a loser attracts "I was impatient" and a winner attracts "clean setup". Mining
them would produce findings that are perfectly circular: the review would "discover" that
trades labelled bad performed badly. That is not a weak signal, it is a guaranteed one, and it
would be the most impressive-looking result in the report.

Mechanically: keep notes in a sidecar table keyed by `trade_id`, not as columns on the trade
frame, so they cannot reach a `groupby` by accident. They surface in the trade-log viewer
(M12) and in any per-trade export, and nowhere else.

Worth revisiting only if the volume of notes ever justifies deliberate qualitative coding —
categories fixed *before* outcomes are examined, which is a different activity from what M11
does.

**11.6 The payoff, and the reason this is worth building.** Because annotation runs on any
trade log meeting the schema, a hypothesis raised by reviewing real trades ("my winners were
mostly in a directional regime") can be turned into a sweep axis and tested properly on 4.7
years of bars. The review generates candidates cheaply from a small, precious sample; the
sweep tests them on a large one. Neither does the other's job, and today only one exists.

---

## M12 — Web GUI

Long term. Not to be started until the review layer's outputs are stable, or the interface
churns with them.

**The governing lesson is the CLI's.** `nqbt sweep` and `nqbt report` were dropped because
they would have been a second, lossier front door to things the Python API already does
better. A GUI carries exactly the same risk at ten times the size. It must call the same
functions, with no analysis logic of its own — if the web layer computes a statistic, that
statistic is now defined twice.

**Scope sketch**, roughly in value order:

1. Browse sweeps and rank combinations — a UI over `results.py`'s DuckDB, which is the
   clearest current gap since ranking is SQL by hand today.
2. Trade log viewer with the annotation columns.
3. The review dashboard from M11.
4. Launching a sweep from the browser — genuinely useful because a `Grid` is a structured
   object that a form can express, which is exactly what argparse could not.

**Stack.** FastAPI plus a small single-page front end if the interaction model matters, or
Streamlit/Dash if it does not. Streamlit gets something usable in a fraction of the time and
is the right call for items 1–3; it becomes limiting around item 4. Recommend starting with
Streamlit explicitly as a throwaway, rather than starting with FastAPI and discovering the
front end is the whole project.

---

## M7 — Walk-forward, Monte Carlo, and a random-entry control arm

All three, deliberately, because they answer different questions and only one of them is
about the strategy's entries.

- **`walkforward.py`** — rolling in-sample / out-of-sample splits over the cached series.
  Tests whether a parameter choice survives being chosen on data it did not see.
- **`montecarlo.py`** — permutation and resampling of a strategy's trade sequence. Tests
  whether the equity path was luckier than the trades justify.
- **`randomentry.py`** — the null the other two cannot provide. Same bars, same bracket
  geometry, same costs, same `@njit` exit logic, entries drawn at random and matched for
  count and time-of-day distribution.

The third is the one worth building first. Against the current PF of 0.746 it separates three
diagnoses that today look identical: entries **worse than random** (the signal is real but
inverted — investigate the inverse), **indistinguishable from random** (the entry logic
contributes nothing; stop tuning this archetype), or **better than random but not past
costs** (there is signal; attack costs, hold time or bracket size). Permuting an existing
trade sequence cannot distinguish any of those, because it takes the entries as given.

It also shares machinery with §11.4's permutation test, so building it pays for part of the
review's statistical guard.

---

## Related items from the imantrading notes, not yet scheduled

Recorded so they are not lost. See
[imantrading_concept_extraction.md](imantrading_concept_extraction.md) §3 for the full
argument.

- **Regime-stratified re-reading of the existing sweeps.** M10.1 delivers the classifier;
  applying it to results already in DuckDB is then nearly free, and it addresses a real
  weakness — the current "0 of 192 profitable" cannot distinguish "no edge anywhere" from
  "edge in one regime, drowned by the others". The same argument applies to M10.4's
  time-of-day label, and for the same reason.
- **Prop-account simulator** over the trade log: trailing threshold, daily loss limit,
  consistency ratio, profit target → pass rate. Reranks results by the objective that actually
  pays, rather than by profit factor.
- **ATR-multiple brackets** with a hard dollar floor on minimum bracket size.

---

## Moving-average axes: what is sweepable and what is not

**Already sweepable, no work needed.** Both the periods and the on/off toggles, jointly:

```python
grid = sweep.Grid.of(
    DeadCatParams(commission_per_contract=0.74, slippage_ticks=1.0),
    ema_period=[9, 15, 21, 30],          # period
    fast_sma_period=[40, 60, 80],        # period
    use_slow_sma=[True, False],          # toggle
    slow_sma_period=[120, 175],          # period, gated by the toggle above
    use_vwap=[True, False],              # toggle
)
```

Every field of `DeadCatParams` except `target_r_multiples` is a legal axis
(`sweep.SWEEPABLE`), and `Grid.dead_axes()` refuses a period axis whose toggle is off in
every combination — otherwise four identical rows cost 4× the runtime. The periods are
precomputed once as a `[n_periods, n_bars]` boolean matrix per MA kind, so adding period
values to a sweep is close to free at run time.

Two MA dimensions are **not** reachable. Both are recorded here as planned, not started.

### MA kind as a swept axis

The kind is currently fixed by field name: `ema_period` always resolves through
`indicators.nt8_ema`, both SMA fields through `nt8_sma`. So "what if the fast filter were an
EMA rather than an SMA?" cannot be asked, and only those two kinds exist — no WMA, HMA or
VWMA.

Needs a `kind` alongside each period (`fast_ma_kind="sma"`), a `MovingAverageGrid` per kind
in `Dataset`, and gate lookup by `(kind, period)` instead of period alone. The grid cost is
linear in the number of kinds, and the boolean-only default keeps that cheap.

**The trap is the prime directive.** Any new kind must match NT8's recursion, not the
textbook one — this is exactly where TA-Lib's EMA already differs from NT8's through
seeding alone. A kind that is merely *a* correct HMA is a fidelity break, because Tier 1 and
Tier 2 would then disagree in a way that cannot be attributed. Each kind needs pinning
against hand-computed NT8 values the way `nt8_ema` and `nt8_sma` are.

### Multi-timeframe moving averages

Every MA is computed on the 1-minute close. A daily or hourly MA gating a 1-minute entry —
standard practice, and the natural way to express "only short below the higher-timeframe
trend" — is not expressible.

Needs the resampler from M13 below, computing the MA on the coarse series and forward-filling
back onto the 1-minute index. **The trap is lookahead**: the coarse bar covering 14:00–15:00
is not knowable until 15:00, so the value must be stamped from the *previous* completed
coarse bar or every backtest using it is silently reading the future. This is the single
easiest place in the whole project to manufacture a spectacular and entirely fictional edge.

Note this is a *different* feature from M13: here the strategy still runs on 1-minute bars
and merely consults a coarse MA. In M13 the whole strategy runs on coarse bars. Both are
wanted; they share the resampler and nothing else.

Sequencing note: this overlaps M10.3's compact trend label, which solves part of the same
problem from the other direction — a coarse trend read as a condition rather than as an MA
gate. Worth deciding which one is wanted before building either, rather than shipping two
overlapping notions of "the higher-timeframe trend".

---

## M13 — Bar resolution as a sweep dimension

Run the whole strategy on 2, 5, 15, 30-minute bars and sweep across resolutions the way
periods are swept today. Planned, not started.

### The enabling fact: resampling 1-minute bars is exact, not approximate

The obvious worry is that coarse bars should be built from `data/tick/` to be faithful. They
should not, and doing so would be the *more* precise choice the prime directive forbids.
OHLC aggregation is associative:

```
open   = first        high = max(highs)
close  = last         low  = min(lows)          volume = sum
```

A 5-minute bar assembled from five 1-minute bars is therefore **bit-identical** to one NT8
assembles from ticks. A minute with no trades contributes nothing either way, so gaps do not
break the identity. This is what makes the whole feature cheap and fidelity-neutral: no new
data, no tick pipeline, no new source of Tier-1/Tier-2 divergence.

### The trap: anchoring

Bars must be bucketed by **minutes since the session open**, not by wall clock and not with
a bare `resample()`. NT8 restarts bar building at each session start, so under the CME ETH
template a 5-minute bar runs 18:00–18:05 ET.

For the periods anyone actually sweeps this happens to be harmless — 18:00 ET is 1,080
minutes past midnight, and 2/3/5/10/15/30/60 all divide 1,080, so midnight-anchored and
session-anchored buckets coincide. **That coincidence is exactly why this must be tested
rather than assumed**: it holds for every period likely to be tried first, then silently
fails on 7 or 11 or 45. Anchoring to the session open is no harder and is correct for all of
them.

Two further boundaries the bucketing must respect: no bar may span the 17:00–18:00 ET
maintenance break, and none may span the Friday 17:00 → Sunday 18:00 weekend. Bucketing from
the session open gives both for free; bucketing on wall clock does not.

### Validation, which is unusually cheap here

`NqbtHistoricalExporter.cs:270` already builds `BarsPeriod { BarsPeriodType =
BarsPeriodType.Minute, Value = 1 }`. Changing `Value` gives NT8's own 5-minute bars for the
same contract, and `tools/compare_exports.py` already diffs two exports. So the check is:
resample our 1-minute archive to 5 minutes, pull NT8's native 5-minute series, and diff.
Any anchoring error shows up immediately as a whole-bar offset rather than as a subtly wrong
backtest months later.

**Request it with the ETH trading-hours template, not `Default 24 x 7`.** The AddOn uses
24x7 deliberately so nothing is filtered before our own session classification sees it, but
bar *building* is anchored by that template — and the Strategy Analyzer will use ETH. A
validation run against 24x7 bars would confirm the wrong thing.

### What changes about the strategy, which is the real point

Resolution is not a neutral knob. Several rules are defined per *bar*, so their meaning
moves with the bar:

| rule | at 1 min | at 5 min |
|---|---|---|
| entry order lifetime (one bar) | 1 minute | 5 minutes |
| stop ratchet (once per completed bar) | every minute | 5× less often |
| `bars_required_to_trade = 200` | 200 minutes | 1,000 minutes |
| MA period 21 | 21 minutes | 105 minutes |

So a resolution sweep is not "the same strategy, sampled differently" — it is a family of
related strategies. Two consequences: `resolution` must be a first-class column everywhere
results are stored or compared, and **comparing profit factor across resolutions at the same
period number is meaningless** unless the period is scaled with it.

**Prediction worth checking early: the ambiguous-bar rate should rise sharply.** A bigger bar
is likelier to contain both the stop and a target. At 1 minute that is 3.4% of exits and the
choice of `ambiguity_policy` is worth only ±0.009 PF. At 15 minutes it could dominate, and
the spread between the NT8 rule and the blanket worst case becomes a direct measure of how
much of any apparent coarse-resolution edge is an artefact of what bar data cannot settle.
If a coarse resolution suddenly looks profitable, **look there first.**

### Shape

`nqbt/resample.py`, and it belongs to **context, not simulation** — so it lands naturally
alongside M9's `nqbt/context.py`.

Resolution cannot be a `DeadCatParams` field: it changes the `Dataset`, not the rule, and
`sweep()` builds one `Dataset` for the whole grid. Cleanest is a wrapper that builds one
`Dataset` per resolution and runs the grid inside each, tagging every row:

```python
res = sweep.sweep_resolutions(bars, grid, resolutions=[1, 2, 5, 15])
```

Cost is mild and self-limiting, because coarser series are proportionally smaller: sweeping
1, 2, 5 and 15 minutes costs about 1 + ½ + ⅕ + 1/15 ≈ **1.8× a 1-minute sweep**, not 4×.
`results.save_sweep` needs the extra column, which is also a reason to do it before the
stale DuckDB re-run rather than after.

---

## Decisions taken

**Roll dates need no reconciliation against NT8.** All 18 MNQ roll dates moved when the
archive made volume crossovers detectable, which raised whether Tier 1 and Tier 2 still agree
across a roll — the coverage handover used to guarantee it by construction, being the point
NT8 itself ran out of one contract.

Decided: not worth chasing. NT8 merges contracts on the rollover dates **configured in its
Database window**, not on observed volume, so it is a setting rather than a measurement. It
is ground truth for fill semantics, which is what the prime directive is about; it is not
ground truth for when the market actually rolled. A data-derived crossover can reasonably be
*better* than NT8 here without that being a fidelity violation.

Residual risk, recorded rather than dismissed: a spliced-series result cannot be reproduced
in Strategy Analyzer bar-for-bar around a roll. If a sweep that crosses one ever produces
something surprising, the roll boundary is a candidate explanation, and the segment tables in
`nqbt splice --diagnostics` are where to look first.

**Stored sweeps — drop and re-run, not yet.** Everything in `results/sweeps.duckdb` was
computed against a continuous series with different roll dates, so those rows are not
comparable with anything generated now. They are not wrong, they are answers to a different
question, and nothing reads them automatically. Clear the table and re-run the grids that
still matter at the point something actually needs to query it — most cheaply once M10's
regime and time-of-day labels exist, so the re-run produces stratified results rather than
needing a third pass.

**Trade source format — deferred, by design.** An example will arrive; until then the
importer is specified as an adapter boundary (§11.1) rather than around a guessed layout.
Writing the adapter is small work once the example exists, and it is the *only* part that
should need to change per source. Everything upstream of the example — the schema (M9), the
conditions (M10), the annotation and review machinery (§11.2–11.4) — is independent of the
format and can be built first.

**Discretionary context — recorded, not analysed.** Stored, viewable, and structurally kept
out of the evaluation path. See §11.5 for why this is enforced rather than merely intended.

**Coverage — measured, not decided.** Whether the trades fall inside cached instruments and
dates becomes a report the importer emits (§11.1), so the answer arrives as data with the
first real file. The only design consequence is that out-of-coverage trades must be excluded
loudly rather than dropped quietly.

**Trade source — the NT8 executions grid**, with the Control Center log rejected. Reasoning
and the confirmed parsing traps are in §11.1. The review reports dollars, points and exit
reason; `r_multiple` is deliberately not reconstructed.

**Timezone — NT8 display time is the machine's local zone**, `GMT Standard Time`, so BST
(UTC+1) in summer. Confirmed end-to-end: converting the sample's eight fills to UTC and
mapping each to the bar stamped at the next whole minute puts every one inside its bar's
high/low range, with the 17:00:29 stop landing exactly on the 17:01 high. That simultaneously
validates the conversion, the end-of-bar alignment rule, and coverage. It should still be
explicit configuration rather than an inferred default — a wrong zone shifts every trade by
hours without erroring — but the default is now known to be right for this machine.

**Coverage — resolved for the sample.** MNQ runs to 2026-08-10 19:55 UTC, past the 16:58–17:07
trade window. Note the export lags live by roughly two hours, so the most recent session is
always partly unavailable; a review run soon after trading will find its newest trades
uncovered, and the importer's coverage report is what should say so.

## Still open

- **Sample size.** How many trades exist determines whether §11.4's guard leaves anything
  standing. A few dozen will not support stratification by more than one or two conditions at
  a time, and knowing that early sets expectations for what the review can honestly deliver.
- **Which series to annotate against.** The sample trades a single contract, `MNQ 09-26`.
  Annotating against the per-contract cache sidesteps back-adjustment and roll-date questions
  entirely and is almost certainly right; the continuous series only earns its place if a
  review needs indicators with lookbacks that cross a roll.
