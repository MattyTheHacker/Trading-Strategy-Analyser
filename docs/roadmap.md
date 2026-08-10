# Roadmap

Planned work, in dependency order. Nothing here is built. `CLAUDE.md` carries the one-line
summaries; this file carries the reasoning and the traps.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the
project's own docs first, [imantrading_concept_extraction.md](imantrading_concept_extraction.md)
second. The imantrading notes are a source of framing and of numeric definitions we lack, not
a source of priorities.

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
consolidation". Two of those four have no implementation.

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

## Related items from the imantrading notes, not yet scheduled

These are not part of the above and are recorded so they are not lost. See
`imantrading_concept_extraction.md` §3 for the full argument.

- **Regime-stratified re-reading of the existing 192 combinations.** M10.1 delivers the
  classifier; applying it to results already in DuckDB is then nearly free, and it addresses a
  real weakness — the current "0 of 192 profitable" cannot distinguish "no edge anywhere" from
  "edge in one regime, drowned by the others".
- **Random-entry control arm.** Same bars, same brackets, same costs, entries drawn at random.
  Distinguishes "worse than random" from "no better than random" from "better but not past
  costs" — three findings that currently look identical. Shares its machinery with the
  permutation test in M11.4.
- **Prop-account simulator** over the trade log: trailing threshold, daily loss limit,
  consistency ratio, profit target → pass rate. Reranks results by the objective that actually
  pays, rather than by profit factor.
- **ATR-multiple brackets** with a hard dollar floor on minimum bracket size.

---

## Decisions taken

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

**Coverage — resolved for the sample.** MNQ runs to 2026-08-10 18:19 UTC, past the 16:58–17:07
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
