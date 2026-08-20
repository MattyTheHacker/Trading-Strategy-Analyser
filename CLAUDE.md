# CLAUDE.md

Tier 1 research backtester for NQ/MNQ futures (`nqbt`). Sweeps parameters fast to produce a
shortlist; **NinjaTrader 8 Strategy Analyzer stays the ground truth** and re-validates every
survivor (Tier 2).

## Prime directive

**Match NT8's default fidelity exactly — do not exceed it.** Being more precise than NT8 is
as much a bug as being less precise, because it makes the two tiers disagree in ways that
cannot be attributed. Specifically: bar-close OHLC fills, no intrabar tick precision. Tick
data exists in `data/tick/` and is deliberately **not** wired into the simulation.

When the C# and intuition disagree, the C# wins. When the C# and a real NT8 trade list
disagree, the trade list wins.

This governs the **simulation** side only. The planned trade-review side analyses real
fills, which are genuinely tick-precise; that is not a violation because nothing is being
simulated. The trap is letting that precision leak backwards into `nqbt/sim/` — see
`docs/roadmap.md`.

## Ground truth

- `ninjatrader-scripts/Strategies/DeadCatBounce.cs` (submodule) — the strategy source.
  **Check it is current before porting**; it has been ahead of the committed version before.
- `docs/nt8-fidelity.md` — every NT8 rule the simulation implements and the evidence for it.
  Read this before changing anything in `nqbt/sim/`.
- `docs/roadmap.md` — the reasoning behind the order, the milestone findings, the standing
  rubric and the decision record. Read it before starting anything.
- `CONTRIBUTING.md` — **the working agreement, and it is not optional.** Code style, naming,
  tests, coverage, linting, the trade-log gate, commits and pull requests. Read it before
  writing code and follow it; where it and this file overlap, `CONTRIBUTING.md` wins on *how*
  to change the codebase and this file wins on *what is true about the domain*.
- **The issue tracker is where plans, ordering and status live** — not these files. `gh issue
  list`, and `gh issue view <n>` for `blocked-by`/`blocking`.
- An NT8 trade-list export (Strategy Analyzer → Trades → Export) is the only way to settle
  fill-semantics questions. Summary statistics hide them.

## Gotchas that cost real time to find

- Entry orders are **not GTC** — NT8's managed approach cancels them after one bar. **This is
  an unset parameter, not a platform limit**: the long-form overload takes
  `isLiveUntilCancelled` and `DeadCatBounce.cs` calls the three-argument one. `TimeInForce.Gtc`
  is a different layer (exchange-side) and does not affect it. Longer-lived orders are fully
  expressible — `docs/roadmap.md`, "Order lifetime in NT8", has the three routes and their
  costs. The simulation keeps the one-bar lifetime because that is what the C# does.
- The trigger is `min(Low[0], Close[0] - 2 ticks)`, not the bar's low. Binds on ~⅓ of signals.
- `IsFillLimitOnTouch = false`: targets need `low < target`, not `<=`.
- Ambiguous bars (stop and target both in range) resolve to whichever is **nearer the open**.
  A blanket worst case is *more* pessimistic than NT8, not equal to it.
- **A stop that gaps fills at the open, not at the stop price.** A stop is a market order
  once triggered, so a bar opening past it offers no trade at the level. This holds for
  **exits as well as entries** — the entry path always modelled it and the exit path did not,
  which made every gapped stop exit optimistic until M15.5. It does *not* apply on the entry
  bar: the position did not exist at that bar's open, so price still had to travel through
  the trigger to open it and only then back to the stop.
- **A stop entry at or through the market is never submitted.** `EnterLongStopMarket(High[0])`
  on a bar that closed on its high is a buy stop at the price the market is already at; that
  is not a stop order and NT8 declines it. DeadCatBounce is immune **by construction** — its
  `min(Low[0], Close[0] - 2 ticks)` cap puts the trigger below the close on exactly the bars
  that would otherwise be unsubmittable — which is why this only surfaced once a second
  archetype used a bare `High[0]`. One archetype cannot exercise the fill model.
- `MaxRiskPerTrade` is in **ticks**, not dollars.
- **TA-Lib's EMA ≠ NT8's EMA** (different seeding). `indicators.py` hand-rolls NT8's
  recursion. ATR/StdDev/Bollinger/Keltner are now pinned too (see below); TA-Lib is left
  only for MACD and RSI, which no archetype reads and which carry the same problem unfixed.
- **Exports are moving windows, not snapshots.** NT8 serves each contract for a limited
  period and drops the tail once it expires, so a folder of exports loses history over time.
  `data/archive/` is the durable union and **the only thing ingestion reads**; `archive.py`
  merges `data/minute/` (manual) and `data/addon/` (AddOn) into it. Never point a real
  ingest at a source folder — `ingest` mirrors its input exactly, so it would propagate the
  loss straight into the cache.
- The two sources **compound, and the order matters**. On its own the AddOn reaches ~3–6
  months further back but stops at the turn of the expiry month, while a manual export holds
  only the last ~95 days through expiry. But the AddOn's requests warm NinjaTrader's own
  local database, so **running the AddOn and then re-exporting manually** returns the full
  contract life from one source. That took the archive from 3.0M bars to 4.09M.
- A manual export **regenerates the file; it does not append**. Bars get revised between
  exports and occasionally withdrawn. Ingest hashes the **whole consumed byte range** to
  tell an append from a rewrite — a head-only hash calls a rewrite an append, which froze
  stale bars and silently dropped real ones.
- **The last bar of any export may be mid-formation** — one showed 294 contracts of an
  eventual 890, with a high and close that had not happened yet. The archive merge lets a
  file's newest bar insert but never overwrite.
- **Handover ratios must be read against `shared_bars`.** MNQ 06-26 → 09-26 read 0.27 and was
  flagged as premature for weeks; that figure came from a 60-bar stub, not a session.
- **Volume-crossover rolls are no longer undetectable.** Run the AddOn, then re-export
  manually: NT8 returns the full contract life instead of ~95 days, because the AddOn warms
  its local database. **All 36 rolls across both roots now find a genuine crossover**, each
  decided on a session of ≥1,251 shared bars. `docs/nt8-fidelity.md` has the evidence.
- **A stub session cannot decide a roll.** Both roots hold only the Sunday 18:00–19:00 ET
  hour for one trading day two or three days before most rolls, and that lands exactly where
  the crossover is judged. Sessions below half the median shared-bar count are marked
  `conclusive=False` and skipped. Without this MNQ 03-23 → 06-23 rolled a day early on a
  120-bar window reading 1.46, where NQ's identical stub read 0.68 — neither is a verdict.
- **Run the two roots against each other.** They rolled identically on 17 of 18 pairs, and
  the disagreement was the bug above. It is the cheapest correctness check available and
  needs no NT8.
- Correct roll dates **cost bars**. The front contract now supplies days an early roll gave
  to the back contract, and NT8's data has holes there — 18 thin sessions in NQ (1,779 bars)
  and a comparable set in MNQ. They were always missing; an early roll hid them behind the
  wrong contract. Do not fill them from the neighbouring contract: that splices two
  different prices into one session.
- **Out-of-session stray prints reach the indicators on a per-contract run but not on a
  spliced one.** `context.prepare` computes over every row it is handed; `build_continuous`
  filters to in-session first. Measured on MNQ 03-24: including all 47 strays changes
  nothing — 1,380 legs either way, no differing field — so this is a known asymmetry, not a
  live bug. Re-measure rather than assume if the parser ever starts keeping more of them.
- **NT8 trade-list exports are in the machine's display timezone (`Europe/London`), not UTC.**
  They only looked like UTC because the first reconciliation window was December–March, when
  London *is* UTC. Over a summer window the export is BST and every trade is an hour out —
  parsing MNQ 06-24 as UTC joined 332 of 1,800 legs; as `Europe/London`, 1,792 of 1,792.
  `tools/reconcile_nt8.py` handles it. Bar timestamps in `data/archive/` are **end-of-bar,
  UTC** — the AddOn converts at export.
- **TA-Lib's ATR/StdDev/Bollinger/Keltner are all wrong for NT8 too, and Keltner doubly so.**
  Pinned in M16 against 89,330 bars: ATR seeds with an *expanding simple average* of True
  Range before switching to Wilder; StdDev uses the *population* divisor over an expanding
  window and must be computed two-pass; Bollinger is `SMA ± k·StdDev`. **Keltner matches
  neither half of the usual definition** — its midline is an SMA of *typical price*, and its
  width is the mean *high−low range*, **not ATR** (ATR agreed on 20 bars of 89,330). Use
  `indicators.nt8_*`; `docs/nt8-fidelity.md` §M16 has the evidence.
- **True Range does not reset at a session boundary.** It reads the previous bar's close
  across the maintenance break, and on 27 of 65 session opens the gap makes TR exceed `H−L`.
- **Every position must be flat before the session close** — a prop-firm account rule, so it is
  not negotiable and not a parameter. Already implemented (`sessions.force_flat_mask`,
  `EXIT_SESSION_CLOSE`, `block_entry_at_session_close`) and matching NT8's
  `IsExitOnSessionCloseStrategy`; don't re-add it. The design consequence is that **maximum hold
  time is bounded by the session**, so any archetype needing an overnight hold is unbuildable —
  apply that while writing the Python, not at port time. `docs/roadmap.md`, "Flat before the
  session close", has the per-milestone consequences.
- NQ and MNQ share a tick size but their tick values differ 10×. Everything monetary must go
  through `instruments.py`. Verified by running the same NQ bars through both specs: trade
  geometry identical, gross P&L exactly ×10 on every leg, per-contract commission unscaled.
- Parallel sweeps top out around **5×, not 16×**, and that is the hardware, not the harness.
  Per-core throughput drops 1.5× when all 8 physical cores are busy (mobile Ryzen; ~5.1 GHz
  single-core boost against a much lower all-core clock). `n_jobs=8` gets 4.4×; `n_jobs=16`
  is SMT and adds ~10% for twice the memory. Measured, not guessed — don't "fix" it.

## Environment

Python 3.14 venv at `.venv`. Run tools as `./.venv/Scripts/python.exe -m ...`.

```bash
./.venv/Scripts/python.exe -m pytest
nqbt ingest | contracts | splice | run
```

The CLI covers the four pipeline steps and stops there **by design**. `nqbt run --explain N`
is the NT8 audit trail and earns its keep; sweeps, reports and walk-forward are driven from
Python because a `Grid` does not survive being flattened into argparse flags. Do not add
commands that duplicate the Python API.

## Conventions

**`CONTRIBUTING.md` is the working agreement, and following it is not optional.** Code style,
naming, tests, coverage, linting, the trade-log gate, commits and pull requests all live there.
**Read it before writing code or opening a PR, every time** — not once and from memory. This
section is only the conventions specific to the domain; where the two overlap, it wins on *how*
to change the codebase and this file wins on *what is true about the domain*.

- **~~Reasoning goes in `docs/`, not in the source~~ (#105) — done, and the migration with
  it.** Docstrings say **what** a thing is and stay short; arguments, measurements, decision
  records and traps live in `docs/roadmap.md` or `docs/nt8-fidelity.md` behind a one-line
  pointer. Prose across `nqbt/` went from **0.54 : 1 to 0.32 : 1** against code, and the
  fourteen captured trade logs are byte-identical (`sha256` too). Every pointer in the source
  names a section that exists. **This reversed the earlier "docstrings say why" rule** — do
  not reintroduce it.
- Trade logs are **one row per leg exit**; `stats.summarise` aggregates to one row per trade.
  NT8's "total trades" is the leg count, so use `stats.leg_summary` when reconciling.
- `r_multiple` uses **planned** risk (`stop − trigger`), matching how the C# places targets.
- Everything expensive is precomputed once in `context.prepare`; the sweep loop must stay
  cheap. Never recompute an indicator inside a combination.
- Moving-average grids keep only the boolean gate unless `keep_values=True` (66 MB vs 595 MB).
- Numba functions are `@njit(cache=True)` — required so parallel workers reuse the disk cache.
- Every folder under `data/` uses the `.Last.txt` suffix, including `data/tick/`, whose files
  are a different format and orders of magnitude larger. **Never glob across resolutions**;
  `ingest.parse_export` hard-fails on a tick file.
- `verification/nt8_reconciliation_MNQ_03-24.csv` is a **pre-fix** run despite its name — see
  `verification/README.md` before comparing anything against it. The whole `verification/`
  folder is **gitignored and exists only on this machine** (#91).

## Invariants that outlive a milestone

Rules that a future change can violate, extracted from the milestones that established them.
Each names where the evidence lives. **The evidence is not repeated here** — quote the pointer,
not this list, and re-run rather than citing a figure from memory.

### The simulator

- **One sign multiplier `d = ±1`, never two code paths.** Every stop/target/fill/P&L/MAE/MFE
  comparison in `simulate_deadcat`, `_resolve_brackets`, `entry_bracket`, `_limit_filled` and
  `_write` runs through it. `_sided()` is the one place that picks which raw OHLC value is
  adverse or favourable, because that is a data selection and not something a sign
  multiplication can express. **Do not fork it for a new direction or archetype.**
  `docs/roadmap.md` §M15.
- **`nqbt/sim/bracket.py` is the shared bracket engine and `_resolve_brackets` its one
  implementation**, called by both the in-position and entry-bar paths. **Do not fork either** —
  the reconciliation evidence lives there. `entry_bracket` is likewise the single
  trigger/stop/risk computation, shared by the `@njit` loop and `explain.py`, so the audit
  trail is by construction the arithmetic under audit. `docs/roadmap.md` §M20a.
- **A new archetype writes the entry half only.** `CONTRIBUTING.md` § "Adding an archetype".
- **One archetype cannot exercise the fill model, and two are not enough either.** Each new
  entry mechanism reaches fill rules the others made unreachable *by construction*, and
  `bracket.py` inherits whatever is wrong. This is why each archetype earns its own
  reconciliation rather than inheriting confidence from the last. `docs/roadmap.md` § "What
  M15.5 changed".
- **Stop-and-reverse is not supported.** The loop's `in_position` boolean assumes flat-to-flat
  and reversal collides with the one-bar entry lifetime. A deliberate limitation, not an
  unfound bug.
- **`EXIT_SIGNAL` is spent by EmaCrossover alone** — a rule-driven exit with no bracket level.
  A test guards structurally that DeadCatBounce, PullBackAndGo and `bracket.py` never import it.
- **A resting entry order is cancelled on a `force_flat` bar**, not tested for fill.
  `block_entry_at_session_close` guards only a *new* signal on that bar.
- **`ratchet_offset_ticks` is separate from `stop_offset_ticks`**, and `above_series` is not
  `~below_series` — each C# treats its own equality boundary as a pass, so the two overlap at
  `close == ma` rather than partition it. `docs/nt8-fidelity.md`.
- **`PullBackAndGoParams`'s defaults reproduce the reconciled configuration, not the
  NinjaScript's** — `PullBackAndGo.cs` leaves seven properties uninitialised in `SetDefaults`.
  `use_vwap` stays off: nothing has checked nqbt's VWAP against `OrderFlowVWAP`.

### The sweep and the context

- **Register an archetype; do not fork the sweep.** `nqbt/archetypes.py` is the registry and
  `sweep.py` names no parameter class and no run function.
- **`sweepable` reads `dataclasses.fields()`, never `__slots__`** — `__slots__` holds only the
  fields declared on the class itself, so an inherited axis would vanish, and a dropped axis
  does not raise, it makes every combination along it identical.
- **`prepare` builds what a `ContextSpec` declares, not everything.** Reading a series nobody
  declared raises `ContextError` naming the field to set, rather than returning `None` into a
  boolean AND. Grids are keyed by `(kind, period)`. `cli.py` asks for VWAP unconditionally on
  purpose — `--explain` exists to show what a sweep did *not* read.
- **`sweep.sweep_axes` is the one mechanism for strategy × resolution × contract.** The
  strategy axis is a list of grids, not archetype names; the contract axis is carried by `bars`
  itself. **Do not add a second wrapper for a new axis.** `combo_id` means the same parameters
  at every axis point but *not* across grids, which is why `strategy` is part of the log key.
- **`results` writes both DuckDB tables by name, never by position**, which is what makes a
  nullable column safe to add to a database that already has rows. Pin dtypes on a nullable
  tag: an all-null `object` column infers as INTEGER in DuckDB.
- **`keep_trades` changes what `run_combination` returns, never what it measures.**

### Statistics

- **Both summary paths share `_summarise_arrays`** and differ only in how the per-trade vectors
  are obtained — which is what reduces "do they agree?" to "do they group the legs the same
  way?". **Do not re-inline it into either caller.** `docs/roadmap.md` § "The numpy-native
  summary path".
- **Pandas' `groupby.sum` is Kahan-compensated**, and `_grouped_sum` carries the same
  compensation term for that reason alone. A plain running sum disagrees with pandas in the
  last bit on real trades; `np.add.reduceat` disagrees more often.
- **`Dataset.day_codes` is local, not UTC.** `summarise` groups daily P&L by `DatetimeIndex.date`,
  which is the index's timezone — a UTC-only version passes every test on the UTC archive and is
  an hour out on a `Europe/London` index.
- **`trades.validate_legs` is the producer boundary a sweep crosses**, since it never calls
  `validate`. Same invariants plus one: `exit_reason` must be in `EXIT_REASONS`, because only
  the simulator can have written it.
- **R means something different under an ATR stop.** `r_multiple` is volatility-scaled rather
  than structure-scaled, so EmaCrossover results are **not comparable to DeadCatBounce results
  at the same R numbers**.
- **A flip is two trades in the log**, each paying its own costs — economically a reversal, and
  it must be described that way against published crossover results.

### Time, bars and data

- **A bar is labelled by the minute it covers, not the minute it is stamped at.** Timestamps are
  end-of-bar, so a bar stamped 09:30 is the pre-open and the first cash-open bar is stamped
  09:31. Invisible at 1 minute and wrong everywhere else.
- **Bucket by minutes since the session open, never wall clock**, and note the usual
  justification is wrong: agreement with a midnight-anchored grid needs `N | gcd(1080, 1020)`,
  i.e. **N divides 60**. Dividing 1,080 is not sufficient. `docs/roadmap.md` §M13.
- **Bar of session is clock-derived, never counted off the data** — an ordinal count renumbers
  everything after a hole, so index *k* would mean a different time of day in different sessions.
- **`phase_filter` is a bitmask int so it is sweepable**, and each signal skips the conjunction
  entirely at `ALL_PHASES` — not an optimisation: an out-of-session stray passes *no* mask, so
  ANDing at the default would quietly drop the strays.
- **Resampling is exact, not approximate** — OHLC aggregation is associative, so a 5-minute bar
  built from five 1-minute bars is bit-identical to one NT8 builds from ticks. Do not reach for
  `data/tick/`; that is the more-precise-than-NT8 error.
- **Annotate real trades against the raw series, never the back-adjusted one.** The lookup
  succeeds and every comparison is silently wrong. `docs/roadmap.md` §M11.
- **`data/archive/` is the durable union and the only thing ingestion reads.** Never point a
  real ingest at a source folder.

### The regression gate

`CONTRIBUTING.md` § "The trade-log regression gate" is the procedure. Three things it depends on
that are easy to undo:

- **`float_precision="round_trip"` on the read side is what makes the gate correct** — with it,
  either writer is exact. The `%.17g` on the write side fixes nothing on its own and, paired
  with a default parser, makes matters worse, because 17-digit text is what a lax parser
  mis-rounds. `float_precision="high"` fails the same way. Until #113 the gate read with a bare
  `read_csv`, so a one-ULP difference was invisible to it; `tests/test_trade_log_gate.py` pins
  that it cannot regress.
- **Verifying the gate can still fail is part of using it, and a pandas round-trip is the wrong
  way to do it** — perturbing a value via `read_csv`/`to_csv` trips a *collateral* difference and
  reports a column you did not touch, which reads like success. **Perturb the CSV text
  directly**, one field, and check the reported column is the one you edited.
- **Do not check a reconciliation by leg count.** Leading history legitimately adds signals and
  `trade_id` shifts after any earlier removal, so join on `(entry_time, leg)`. The bar-index
  offset is not constant either — that drift is out-of-session stray prints and is inert.

## Where things stand

**This file does not track status, and neither does `docs/roadmap.md`.** Both went stale on
every landing when they did. The tracker is the answer:

```bash
gh issue list --state open                      # everything outstanding
gh issue list --state open --label next-up      # what is at the front
gh issue view <n>                               # blocked-by, blocking, sub-issues
```

`docs/roadmap.md` carries the reasoning behind the order, the milestone findings, the standing
rubric and the decision record — read it before starting anything, and quote its sections rather
than a summary of them. `docs/nt8-fidelity.md` is the live record of agreement rates and
per-rule evidence; **quote it rather than any figure repeated elsewhere**, because these numbers
move whenever a fill rule changes.

Three standing facts that are not status and do not move:

- **DeadCatBounce is unprofitable across every combination tested**, on both roots, at realistic
  costs. **Decided: not a blocker** — it is the test fixture that proves the system works.
- **Its entry rule is nonetheless measurably better than random** (`nqbt/randomentry.py`), which
  is "there is signal; the loss is in costs, hold time or bracket geometry", not "the entry rule
  is worthless". Quote `docs/roadmap.md` §M7a for the numbers and the caveats that must travel
  with them.
- **Roll dates are data-derived and deliberately not reconciled against NT8**, which merges on
  dates configured in its Database window — a setting, not a measurement. The residual risk is
  that a spliced result cannot be reproduced bar-for-bar around a roll.
