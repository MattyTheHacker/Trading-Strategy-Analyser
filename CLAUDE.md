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
- `docs/roadmap.md` — planned work in dependency order, with the traps. Read before starting
  anything in the "Planned" section below.
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
  recursion. TA-Lib is reserved for MACD/RSI/BB/ATR, which have the same problem unfixed.
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
- NT8 trade-list exports are in **UTC**. Bar timestamps are **end-of-bar, UTC**.
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

## Status

Done and validated: ingestion with a durable archive and exact rewrite detection, contract
splicing with back-adjustment, NT8-compatible indicators, the DeadCatBounce and
PullBackAndGo simulations, the sweep + statistics + DuckDB results layer, and parallel
sweeps over cores.

**Both archetypes are reconciled against real NT8 trade lists. `docs/nt8-fidelity.md` is
the live record** — agreement rates, per-rule evidence, and what each residual disagreement
is. Quote it rather than a figure from here: these numbers move whenever a fill rule
changes, and M15.5 changed two.

**Do not check a reconciliation by leg count.** Leading history legitimately adds signals,
so a current run yields more legs than any stored capture, and `trade_id` shifts after any
earlier removal. Join on `(entry_time, leg)` instead. The bar-index offset is *not*
constant either; that drift is out-of-session stray prints and is inert.
`verification/README.md` has the detail — note it is **gitignored and local-only** (#91).

**NQ runs end to end** — ingest, splice, prepare, parallel sweep — and is unprofitable on
its own data too. No NQ result has been reconciled against NT8 (#66); MNQ remains the only
fill-semantics evidence.

**M9 has landed.** `Dataset`/`prepare` are now `nqbt/context.py`; the trade-log schema is
`nqbt/trades.py` with `validate()` called at the producer boundary, and it carries
`direction`, `instrument` and `source`. The layering is enforced by tests rather than by
habit: `stats.py` must not import from `nqbt.sim`, `context.py` must not import trades or
sim, `trades.py` must not import bars or strategies. Those tests analyse imports with
`ast`, and **the first version of them was vacuous** — `from nqbt import trades` records
the module as `nqbt`, so a prefix match on `nqbt.trades` never fired. `imports_of` now
resolves both halves of a `from` import, and `test_the_import_analysis_sees_both_forms_of_import`
guards that.

The regression gate is now `tools/capture_trade_logs.py` + `tools/compare_trade_logs.py`,
kept because M15 needs the same one. **They write `float_format="%.17g"` deliberately**:
pandas' default CSV writer is not round-trip exact for float64 and moves 4 of 1,664
`r_multiple` values by one ULP, which would let a sign or ordering error slip through the
very gate meant to catch it. Verified to fail on a deliberate one-ULP perturbation.

The refactor was verified by capturing every producer path before and after — the pinned
MNQ 03-24 reconciliation window, a costed run, the same bars through the NQ spec, and an
8-combination sweep serial and parallel. The moves alone are **byte-identical across all 14
files**; the schema commit adds three columns and leaves **every pre-existing column
identical**, dtypes included. `direction` is `SHORT` on every row, written by the loop as a
constant that M15 replaces with its sign `d`.

`sweep.sweep(..., n_jobs=8)` is verified to produce results byte-identical to the serial
path. The `Dataset` is shared, not copied: `Dataset.slim()` drops the 121 MB bar frame to a
13 MB index-only view, and joblib memmaps the arrays — **confirmed** by probing a live
worker, where `close`, `ema.below` and `sma.below` all arrive as `numpy.memmap`.

**M20a has landed**, so M15 is unblocked. All three defects are fixed, every captured trade
log is byte-identical to the pre-M20a baseline, and the whole point was to leave M15 one
copy of the bracket machinery to multiply by `d` instead of two.

- **The bracket machinery is now `_resolve_brackets`**, called by both the in-position path
  and the entry-bar path. The entry-bar copy's `leg_open` guards were no-ops, not a
  difference, so the unified version reduces to the old behaviour exactly. This is where the
  reconciliation evidence lives; **do not fork it again**.
- **`entry_bracket` is the one trigger/stop/risk computation**, called by the `@njit` loop
  and by `explain.py`. The audit trail is now by construction the arithmetic under audit —
  previously it recomputed the trigger as `Low[0]`, dropping the `Close[0] − 2 ticks` cap.
- **`Summary.empty()`** replaces a splat that put 26 arguments into a 28-field dataclass and
  raised on every call. `sweep.run_combination` no longer keeps a second, all-int empty-log
  policy of its own.

**The 50% figure that justified the explain fix was a prefix, not a rate.** Measured over
the whole window the trigger cap binds on roughly a third of signals, but it reads far
higher over the first twenty trades and decays from there, because capped signals are not
evenly distributed. **Quote whole-window rates**; a prefix of a trade log is not a sample of
it. The defect was real either way, and `verification/README.md` records this.

Two things M20a deliberately did **not** change, because M20 may not move a number:
`stats.py:140` is a silent branch computing Sharpe and Sortino per trade rather than per day
for a log with no times — unreachable today, same shape as the empty-log defect, and it wants
an issue. And `verification/explain_2024Q1.csv` is annotated rather than regenerated: it is
the record of what the audit trail said while it was being trusted.

## Planned, not yet done

`docs/roadmap.md` carries the dependency order and the traps; this section is the summary.
**Order: M7a → numpy summary → M18 → M10 → M11 → M7b → M19 → M12**, with **M16 batched into
a NinjaTrader session** rather than sitting in the code queue. M9, M20a, M15 and
**M17(+M13+M14)** are all done — see Status.

**The code queue no longer reaches M18.** M7a (#32) and the numpy summary path (#33) are
unblocked and pure Python, but after them Phase 2 is gated on M16: #37's ATR stop is a hard
prerequisite and M16 is readings, not code. Six items share that one NinjaTrader sitting
(#20, #21, #22, half of #23, #66, #67, #92) — book it before the code column empties.

**M16 moved out of the code queue deliberately.** Its three substantive sub-issues
(#20 ATR, #21 StdDev/Bollinger, #22 Keltner) each require reading values out of NT8, and the
own rule is *do not answer from memory* — so writing the recursions before the readings exist
is the mistake it was written to prevent. It is NinjaTrader time, and it shares that
constraint with #66 and #67. **M17 is the next code work**: pure Python, no NT8 dependency,
and an equally hard prerequisite for M18. #23 (True Range at session and roll boundaries) is
the one part of M16 that is a decision rather than a measurement, so it can be taken any time.

**New archetypes are developed in Python only.** EMA crossover and squeeze breakout have no
NinjaScript, and none gets written until a candidate looks worth trading — most will not
survive costs, and NinjaTrader time is the scarce resource. Consequences: the prime directive
**still binds during development** (a Python archetype that drifts past NT8's fidelity cannot
be reconciled when it is finally ported, so the exploration is wasted, not merely
unvalidated); designs must be checked against what NT8 can express *while being written*, via
the expressibility checklist in the roadmap; and **"validated against NT8" becomes a
per-archetype property** that M17 carries as a registry field and results column, so a
ranking cannot mix a measurement with an assumption.

**~~M20a~~ — done.** See Status. The standing rubric it carries is in `docs/roadmap.md` §M20
and still governs every change.

M20b (a type checker, `py.typed`, and dtype-parameterised `NDArray` instead of bare
`np.ndarray` — the bool-vs-float64 distinction is load-bearing and currently invisible) and
M20c (23-parameter `@njit` signatures → `NamedTuple`, **verified bit-identical and free**,
`tools/numba_tuple_probe.py`) are standing work with no gate. Full findings, evidence and the
standing rubric are in `docs/roadmap.md` §M20. Note the ruff/mypy/CI finding there is stale —
all three now exist; what is missing is that nothing runs ruff or mypy.

**~~M15~~ — direction in the simulator: done, reconciled, closed.** The whole epic
(M15.1–M15.5) has landed. What its dependents need to know:

- **One sign multiplier `d = ±1`, never two code paths.** Every stop/target/fill/P&L/MAE/MFE
  comparison in `simulate_deadcat`, `_resolve_brackets`, `entry_bracket`, `_limit_filled` and
  `_write` runs through it. `_sided()` is the one place that picks which raw OHLC value is
  adverse or favourable, because that is a data selection and not something a sign
  multiplication can express. **Do not fork this for a new direction or archetype.**
- **The gate for a direction-symmetric change is byte-identity of every short-only trade
  log**, not "the reconciliation still passes" — ×(±1.0) is exact in IEEE 754, so both halves
  of a forked bracket reduce to today's behaviour at `d = −1` whether or not they agree at
  `d = +1`. `tools/capture_trade_logs.py` + `tools/compare_trade_logs.py` are that gate.
- **`EXIT_SIGNAL` is reserved but unused.** For a rule-driven exit with no bracket level of
  its own — M18 and `InsideBarTrailing.cs` need it, DeadCatBounce does not, and a test guards
  structurally that `nqbt/sim/deadcat.py` never imports it.
- **A resting entry order is cancelled on a `force_flat` bar**, not tested for fill.
  `block_entry_at_session_close` only guards a *new* signal on that bar, not an order resting
  from the one before. This removes real legs from a continuous sweep; that is the fix
  working.
- **`ratchet_offset_ticks` is separate from `stop_offset_ticks`.** DeadCatBounce ratchets to
  `High[0] + 2 ticks`, reapplying its entry offset; PullBackAndGo ratchets to a bare `Low[1]`.
  With `ratchet_lag=1` the first evaluation lands on the *signal* bar, so the offset
  difference tightens the stop before any bar has closed with the position open.
- **`above_series` is not `~below_series`.** Each C# treats its own equality boundary as a
  pass independently, so the two overlap at `close == ma` rather than partition it.
- **Stop-and-reverse is explicitly not supported.** The loop's `in_position` boolean assumes
  flat-to-flat, and reversal collides with the one-bar entry lifetime. A deliberate
  limitation, not an unfound bug.

`PullBackAndGoParams`'s defaults **reproduce the reconciled configuration, not the
NinjaScript's** — `PullBackAndGo.cs` leaves seven properties uninitialised in `SetDefaults`,
so it has no defaults to copy and an `OrderQuantity` of 0 trades nothing. `use_vwap` stays
off: nothing has checked nqbt's VWAP against `OrderFlowVWAP`.

Two lessons from the epic worth keeping. **Checking the C# before porting paid immediately**
— #19 was recorded as a prerequisite because PullBackAndGo "needs ATR", and the current
source never calls `ATR()`. And **one archetype cannot exercise the fill model** — M15.5 found two
real fill-semantics defects that DeadCatBounce's own geometry made unreachable, one of which
had been silently making every gapped stop exit optimistic. See the gotchas above.

**M16 — the indicator-parity debt: ATR, StdDev, Bollinger, Keltner.** `indicators.py` flagged
this from the start. Five consumers, not one: Keltner for the squeeze, all three unported
NinjaScripts (`ATR()`), EMA crossover's stop rule, ATR-multiple brackets, and the compression
classifiers. Expect **exactly the EMA bug — seeding, not formula**. Read each out of NT8 and
pin it; do not answer from memory. Keltner is the one most likely to be silently wrong
(platforms disagree on midline and multiplier). Note BB/KC grids are swept over period *and*
multiplier, so the 66 MB → 595 MB lesson applies with an extra factor: keep boolean gates only.

**~~M17 — the archetype protocol~~ — done, with M13 and M14.**

What a new archetype inherits:

- **`nqbt/archetypes.py` is the registry.** An `Archetype` records the parameter class, the
  legal axes, the toggle map `dead_axes` guards with, the series its signal reads, the run
  function, and a `Tier2Status`. `sweep.py` names no parameter class and no run function.
  **Register a new archetype; do not fork the sweep.**
- **`sweepable` reads `dataclasses.fields()`, never `__slots__`** — `__slots__` holds only
  the fields declared on the class itself, so an inherited one would vanish, and a dropped
  axis does not raise, it makes every combination along it identical.
- **`prepare` builds what a `ContextSpec` declares, not everything.** `ContextSpec` lives in
  `context.py` because it describes a `Dataset`. Grids are keyed by **`(kind, period)`** —
  `data.ma_gate(kind, period, above=)` — which is what MA-kind-as-an-axis needs. Reading a
  series nobody declared raises `ContextError` naming the spec field to set, rather than
  returning `None` into a boolean AND. Measured saving on the stock DeadCatBounce grid: VWAP
  alone is ~20% of the dataset, and the parallel path memmaps it per worker.
- **`cli.py` asks for VWAP unconditionally on purpose.** A sweep declares what it reads;
  `--explain` exists to show what it did *not*, so taking its spec from the grid would
  silently drop a column from the NT8 audit trail.

- **`sweep.sweep_axes` is the one mechanism for strategy × resolution × contract.** The
  strategy axis is a **list of grids, not archetype names** — each archetype has its own
  parameter class, so one grid re-based onto another would raise or silently sweep a
  different field. The contract axis is carried by `bars` itself: one frame means the
  spliced series, a `{contract: frame}` mapping runs each separately. Every grid at one axis
  point **shares one `Dataset`**, built from the union of their `ContextSpec`s, and a test
  pins the `prepare` call count. `combo_id` is the grid's own index so it means the same
  parameters at every axis point — but *not* across grids, which is why `strategy` is part
  of the log key. **Do not add a second wrapper for a new axis.**
- **The results schema carries `strategy`, `resolution`, `contract`, `tier2`** on both
  DuckDB tables, nullable, plus `batch_id` on `sweeps`. One `sweeps` row per axis point,
  because `bars`/`first_bar`/`last_bar` are properties of a dataset. **`contract` null means
  the spliced series**; null elsewhere means the row predates the columns. `save_sweep`
  inserts **by name** — a migrated database has the new columns at the end and a fresh one
  has them in the middle. Pin dtypes on a nullable tag: an all-null `object` column infers
  as **INTEGER** in DuckDB, which would have made `combos.contract` unwritable.
- **`stats.Summary.session_close_share`** — exits taken by the clock, over legs, matching
  `ambiguous_share`. Reads 0.0001 on DeadCatBounce at 1 minute; expect it to climb sharply
  with bar size, and read it before believing a coarse resolution.

The shared bracket engine is still extracted **during** M18 — before is designing from one
example, after means duplicated fidelity-critical code shipped.

**M18 — EMA crossover.** The one archetype built now, to prove M15 and M17. **Treat it as a
known-negative control, not an edge candidate**: MA crossover on 1-minute index futures is
reliably unprofitable, so if it reads better than random the first hypothesis is a bug —
specifically lookahead. Use NT8's `CrossAbove(a, b, n)` semantics, not the naive one-bar form,
or a later NinjaScript will disagree. Third entry mechanism (market-on-next-open, no trigger).
Needs an ATR stop, so M16 is a hard prerequisite. **It will break the sweep's performance
assumptions** — tens of thousands of legs per combination against DeadCatBounce's ~1,400,
which is why the numpy-native summary path moved ahead of M10.

**M19 — squeeze breakout.** Queued, not scheduled; the expensive archetype. "Squeeze" means at
least three things — recommend the **Bollinger-bandwidth** form first (one indicator, drops
the Keltner parity question, shares its quantity with M10.1's regime classifier), and port
`InsideBar.cs` before building anything from scratch since it is the same compression-then-break
idea **with C# ground truth**. Real cost is a two-sided OCO entry model the loop lacks. Traps:
lookahead (bands must come from *completed* bars), a high ambiguous-bar rate, and results that
cluster by volatility regime so the aggregate PF averages two populations.

**M7 — split into M7a and M7b, with M7a pulled forward.** `randomentry.py` moves ahead of the
archetypes; `walkforward.py` and `montecarlo.py` stay late. The roadmap had scheduled the null
after M11 because it shares machinery with the permutation test, but **that sharing is
symmetric and the interpretive need is not** — the moment a second archetype exists, every
comparison between archetypes is a ranking with no scale, and M17 multiplies that surface
(archetypes × combinations × resolutions × contracts). Against a losing archetype it
separates "worse than random", "no better than random" and "better but not past costs" —
three diagnoses that look identical today. Must be matched on
**direction** as well as count and time of day, or it measures market drift.

**Moving-average axes.** Periods *and* on/off toggles are both already sweepable, jointly —
every `DeadCatParams` field except `target_r_multiples` is a legal axis, and `dead_axes()`
refuses a period whose toggle is off everywhere. Two dimensions are **not** reachable and are
planned: **MA kind as an axis** (kind is fixed by field name; only `nt8_ema`/`nt8_sma`
exist), and **multi-timeframe MAs** (everything is computed on the 1-minute close). Traps for
both are in `docs/roadmap.md` — a new kind must match NT8's recursion rather than the
textbook one, and a higher-timeframe MA must be stamped from the previous *completed* coarse
bar or the backtest reads the future. **Both get much cheaper once M16 and M17 land**: M16
establishes the pin-it-against-NT8 procedure a new kind needs, and M17's `required_context`
already has to key grids by `(kind, period)`. Reconsider after those rather than now.

**~~M13~~ — bar resolution as a sweep axis (2/5/15/30 min): done.** `nqbt/resample.py` (#30)
is wired into `sweep_axes` (#28). **The existing 1-minute archive is sufficient — no re-export,
no AddOn change.** Resampling is **exact, not approximate**: OHLC aggregation is associative,
so a 5-minute bar built from five 1-minute bars is bit-identical to one NT8 builds from
ticks. Do *not* reach for `data/tick/`; that would be the more-precise-than-NT8 error.

Bucket by **minutes since the session open**, never wall clock — and note the usual
one-line justification for why this rarely bites is **wrong**. Agreement with a
midnight-anchored grid needs a boundary at the session *open* **and** its *close*: 18:00 ET
is 1,080 minutes past midnight and 17:00 ET is 1,020, so the condition is
`N | gcd(1080, 1020)`, i.e. **N divides 60**. Dividing 1,080 is not sufficient — 45 divides
it and still diverges, because a wall-clock grid then runs a bucket from 16:45 to 17:30,
through the maintenance break. Every period anyone tries first divides 60, which is exactly
why an untested implementation looks fine.

Timestamps are **end-of-bar**, so a bar stamped 18:01 is the session's first minute and a
5-minute bucket covering 18:00–18:05 is stamped 18:05. Off by one there is invisible at
1 minute and wrong everywhere else. The final bucket of a session is stamped at the
**observed** last bar, not the theoretical end — that is what handles a period that does not
divide the session and a holiday early close, and it is the same data-derived choice
`is_session_close` makes.

Whether NT8 anchors the same way is settled by the *existing* Tier-2 trade-list
reconciliation at that resolution, not by importing NT8's coarse bars. Resolution changes the
strategy, not just the sampling — order lifetime, the ratchet and `bars_required_to_trade`
are all per-bar — so it must be a first-class results column. **The ambiguous-bar rate does
climb with bar size**, roughly doubling by 15 minutes on MNQ, and the forced-exit share rises
with it; if a coarse resolution looks profitable, check both before believing it.

**~~M14~~ — per-contract sweeps: done.** `nqbt/dispersion.py` (#31) keeps the windows,
coverage and statistics; its per-contract loop is now `sweep.sweep_axes` (#28), and the
`contract` results column is #29.

**Report the spread, not the winner.** A contract is ~3 months of front-month, so "best
contract" is mostly "best quarter", and picking the best of 19 × N combinations is the
multiple-comparisons trap §11.4 guards against. `dispersion()` is therefore returned in
`combo_id` order and never sorted by performance, and a test fails if it starts.

**A spread with no null is a number, not a finding.** `spread_vs_resampling()` permutes
trades between contracts, keeping group sizes exactly, and asks whether the observed spread
survives. It reports **two** measures because the milestone has two jobs that disagree: the
IQR answers "does the bulk of contracts differ?" and is robust, while the range answers "is
any one contract extreme?", which is the data-integrity question — the IQR is blind to a
single rogue contract *by construction*. Restricted to `stats.TRADE_PNL_STATISTICS`, since
permuting destroys the ordering Sharpe or max drawdown depend on. **A small p-value means
"not obviously noise", never "a real per-contract effect"**: permutation destroys
within-contract regime persistence, so the null has less spread than reality and the test
over-rejects.

Its distinct value is that it uses **raw, not back-adjusted** prices (the only way to test
round-number stops), contains **no roll** so it is directly Tier-2 reproducible (the cheapest
route to the NQ reconciliation, #66), and makes an outlier contract read as the data bug it
usually is. Windows default to the **front-month** one, read off the continuous series' own
`contract` column so they are the splicer's decisions rather than a second opinion — they are
non-overlapping and sum to the continuous series exactly, which a test pins. `full_life=True`
exists but adjacent contracts then overlap by months and aggregates double-count.

**First result: DeadCatBounce's per-contract variation on MNQ is indistinguishable from
noise** on both measures, despite the best contract reading roughly double the worst. Treat
a per-contract difference as a hypothesis, not a finding, until it clears this.

**Spec features not yet built.** The build spec calls for these; none exist yet:

- Moving-average **trailing stop mode** as a per-run toggle (only the structural
  swing-high stop is implemented). Needs `MovingAverageGrid(keep_values=True)`.
- **Round-number stop avoidance** — never place a stop exactly on a round number.
  Note this is incoherent with back-adjustment, which shifts absolute price levels.
- **Confluence counting** wired into an archetype. `conditions.count_true` exists and is
  tested, but no archetype consumes it, so "at least N of M filters" is not yet sweepable.

**M8 — bar-major restructuring. The premise has now been measured and is mostly false.**
Profiling one combination over 1.65M bars:

| | share of a combination |
|---|---|
| `stats.summarise` (pandas aggregation) | **51%** |
| `trades_to_frame` (pandas construction) | **20%** |
| `simulate_deadcat` (the `@njit` loop) | 23% |
| `deadcat_signal` (boolean ANDs) | 2% |

Bar-major restructures the 23%. Making the simulation *entirely free* would still only be
~1.3× — Amdahl caps it there. **The real target is the 71% spent building a DataFrame per
combination and aggregating it with pandas**, which is pure overhead in a sweep that
throws the trade log away. A numpy-native summary path — keeping `stats.summarise` as the
reference implementation and testing the two agree exactly — is worth roughly 3×, and
composes with the parallel speedup. Do M8 only if that lands first and profiling still
points at the loop.

**~~M9~~ — done.** See Status. What it leaves for its dependents: `direction` exists on every
trade row but is a constant until M15 makes it load-bearing; `nqbt/trades.NULLABLE` states
which columns an importer may leave empty and why, so M11 does not have to rediscover that
`r_multiple` is unavailable on real fills; and `results._append_or_create` now writes both
DuckDB tables **by name rather than by position**, which is what makes M17's nullable
`strategy`/`resolution`/`contract` columns safe to add to a database that already has rows.

**M10 — the conditions the review needs and we lack.** Regime classification
(`nqbt/regime.py`, Kaufman efficiency ratio → directional / consolidating / unclassifiable,
the middle band being the no-trade state); volume, absolute *and* relative; a compact trend
label off the existing MA grids; and time of day itself (`nqbt/timeofday.py`) as a
first-class dimension for both sweeps and the review — a coarse session-phase label plus a
bar-of-session index, **measured in ET, never UTC**, or the cash open smears across two
buckets for half the year. It doubles as a sweepable entry filter: a rule that only works at
the open reads as unprofitable when averaged over 23 hours.

**Volume is one quantity and its decomposition, not three conditions.** Absolute volume is
the raw count; time of day is its dominant systematic component; relative volume is absolute
with that component divided out (normalise per bar-of-session over a trailing window, never
against adjacent bars, or it just measures the clock). Treating all three as independent
findings confirms one signal three times. Absolute earns its place regardless, because it
alone answers **execution feasibility** — a rule that only works in thin overnight bars looks
fine on relative volume and is untradeable — and because it carries the secular trend
relative volume deliberately removes. But that same trend means **a raw absolute threshold
must not be a sweepable filter**: it means different things in 2021 and 2026, and expressing
it as a trailing percentile just makes it relative volume again. Absolute is also
per-instrument (NQ and MNQ trade different counts) and **steps at every roll**, since prices
are back-adjusted and volume is not.

**M11 — manual trade review.** Import real trades, annotate each against the market context
at its entry bar, stratify realised P&L by condition. Biggest trap: **annotate against the
raw series, never the back-adjusted one** — back-adjustment shifts historical prices by
hundreds of points, so the lookup succeeds and every comparison is silently wrong. Needs a
multiple-comparisons guard (minimum stratum size, permutation test, holdout); without it the
output is confident and wrong.

Source is the **NT8 executions grid**, not the Control Center log: `Position` gives trade
boundaries (`-` = flat) and `Name` gives the exit reason (`Stop1..4` vs `Exit`). The log is
rejected because its stop levels are ATM template defaults dragged to intent seconds later,
so planned risk computed from them is wrong by 10×. Consequence: **no `r_multiple`** on real
trades, by choice. Parsing traps are in `docs/roadmap.md` §11.1 — two date formats in one
file, ties resolved by reversing rather than sorting, and `Commission` always `$0.00`.

Free-text trade context is **stored but never analysed**, in a sidecar table so it cannot
reach a `groupby`: notes are written knowing the outcome, so stratifying on them yields
circular findings.

**M12 — web GUI.** Long term. Same lesson as the CLI: it calls the existing functions and
defines no statistic of its own. Streamlit for the read-only views, and don't start until
the review outputs are stable.

**Open items.**

- **NQ is fully wired up** — every roll on a genuine volume crossover, sweeps running in
  parallel. `nqbt contracts` and `nqbt splice --diagnostics` report the current contract,
  bar and roll counts; don't cite them from here. Instrument scaling is proven exact (same
  bars, both specs, ×10 gross P&L per leg, commission unscaled).
- **TODO: reconcile NQ against NT8 (#66).** No NQ Strategy Analyzer export has ever been
  compared trade-for-trade, so NQ inherits its fill-semantics confidence from MNQ rather
  than earning it. Needs NinjaTrader time, not code time; blocks nothing. The recipe is in
  `docs/roadmap.md` — export **Trades**, not the summary, or every rule that matters stays
  hidden.
- **Holiday early closes are probably not force-flatted.** `force_flat_mask` derives its cutoff
  from the template's fixed 17:00 ET close, not from the session's observed last bar, so on a
  CME half-day (Thanksgiving, Christmas Eve, July 3) nothing reaches the cutoff and the mask
  appears to come back empty — while `is_session_close`, which *is* data-derived, handles those
  days correctly. ~5–8 sessions a year. Unverified: confirm with a query over the archive before
  changing anything, and note a fix changes Tier-1 results on those days. `docs/roadmap.md`,
  "Flat before the session close", has the recipe.
- NG 02-26 sits in `data/minute/` and is **silently ignored**: `ContractId` rejects month 02
  (NQ/MNQ are quarterly) and `discover_exports` swallows the `ValueError`. Harmless, but a
  file disappearing without a warning would hide a real mistake.
- **Roll dates are data-derived and deliberately not reconciled against NT8.** NT8 merges on
  the rollover dates *configured in its Database window*, not on observed volume — a setting,
  not a measurement. It is ground truth for fill semantics, not for when the market rolled,
  so a crossover date may reasonably be better than NT8's without violating the prime
  directive. Residual risk: a spliced result cannot be reproduced in Strategy Analyzer
  bar-for-bar around a roll, so if a sweep crossing one surprises you, look there first.
- **`results/sweeps.duckdb` is stale** — computed against a series with different roll dates.
  Plan is drop and re-run, once M10's labels exist so the re-run comes back stratified.
- MAE/MFE use a different definition from NT8's (mine measure to the exit bar's extreme,
  NT8's cap at the exit). Reporting only, no P&L effect. Unresolved.
- The DeadCatBounce archetype is **unprofitable across every combination tested so far** at
  realistic costs, on both roots, with no combination reaching a profit factor of 1.
  **Decided: not a blocker.** Build the system out first and treat DeadCatBounce as the test
  fixture that proves it works; which archetype is actually worth trading is a later
  question. Note the M15.5 gapped-stop fix moved results *worse* across the board, so any
  figure predating it is optimistic.
