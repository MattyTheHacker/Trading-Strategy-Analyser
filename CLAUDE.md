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
./.venv/Scripts/python.exe -m pytest          # 174 tests
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
  `verification/README.md` before comparing anything against it.

## Status

Done and validated: ingestion with a durable archive and exact rewrite detection, contract
splicing with back-adjustment, NT8-compatible indicators, the DeadCatBounce simulation, the
sweep + statistics + DuckDB results layer, and parallel sweeps over cores. Reconciliation
against NT8 is **1143/1144 leg exits identical (99.91%)**.

That reconciliation was re-checked after the archive and the NQ re-export landed, and still
holds — but **do not check it by leg count**. The extra leading history legitimately adds
signals, so a current run yields 1,380 legs against the stored 1,168. Join on
`(entry_time, leg)` instead: all 1,168 are present with identical times, prices, stops,
targets, exit reasons and P&L. The bar-index offset is *not* constant (38,279 → 38,296);
the drift is 17 out-of-session stray prints and is inert. `verification/README.md` has it.

**NQ now runs end to end** — ingest, splice, prepare, parallel sweep — over 1,633,461 bars.
It is unprofitable on its own data too (best PF 0.829 of 96 combinations, 0 profitable).
No NQ result has been reconciled against NT8; MNQ remains the only fill-semantics evidence.

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

## Planned, not yet done

`docs/roadmap.md` carries the dependency order and the traps; this section is the summary.
**Order: M20a → M15 → M16 → M17(+M13+M14) → M7a → M18 → numpy summary → M10 → M11 →
M7b → M19 → M12.** M9 is done — see Status.

**New archetypes are developed in Python only.** EMA crossover and squeeze breakout have no
NinjaScript, and none gets written until a candidate looks worth trading — most will not
survive costs, and NinjaTrader time is the scarce resource. Consequences: the prime directive
**still binds during development** (a Python archetype that drifts past NT8's fidelity cannot
be reconciled when it is finally ported, so the exploration is wasted, not merely
unvalidated); designs must be checked against what NT8 can express *while being written*, via
the expressibility checklist in the roadmap; and **"validated against NT8" becomes a
per-archetype property** that M17 carries as a registry field and results column, so a
ranking cannot mix a measurement with an assumption.

**M20 — code quality: a standing rubric, and three measured defects that block M15.**
A pass over the code found: `explain.py` recomputes the entry trigger as `Low[0]`, omitting
the `Close[0] − 2 ticks` cap, so the **NT8 audit trail disagrees with the simulation's
`risk_points` on 50% of trades** — and it has no tests, which is why; `stats.summarise`
raises `TypeError` on an empty log (26 arguments into a 28-field dataclass, behind a
`# pragma: no cover` whose comment is also wrong); and **the bracket machinery is already
duplicated inside `simulate_deadcat`** — ~85 near-identical lines resolving stop/target/
ambiguity/force-flat once for the in-position path and again for the entry-bar path.

That third one is why M20a is scheduled before M15 rather than whenever. M15's stated design
is "one sign, not two code paths, because forking would fork the bracket machinery" — but it
is forked already, so M15 would apply `d` to two copies. **The short-only byte-identity gate
does not protect against this**: both copies reduce to today's code at `d = −1` whether or not
they agree at `d = +1`. Unify, prove byte-identity, then apply `d`.

M20b (a type checker, `py.typed`, and dtype-parameterised `NDArray` instead of 47 bare
`np.ndarray` — the bool-vs-float64 distinction is load-bearing and currently invisible) and
M20c (23-parameter `@njit` signatures → `NamedTuple`, **verified bit-identical and free**,
`tools/numba_tuple_probe.py`) are standing work with no gate. Full findings, evidence and the
standing rubric are in `docs/roadmap.md` §M20.

**M15 — direction in the simulator.** The actual blocker on every new archetype: the `@njit`
loop is short-only in ~8 places, and EMA crossover, squeeze breakout and all three unported
NinjaScripts are long-capable. One sign multiplier `d = ±1`, not two code paths — forking
would fork the bracket machinery, which is where the 1143/1144 evidence lives. Because ×(±1.0)
is exact in IEEE 754, **the regression gate is byte-identity of every short-only trade log**,
not "the reconciliation still passes". Also adds `EXIT_SIGNAL` (every exit today is a bracket
level) and makes M9's `direction` field load-bearing. Stop-and-reverse is explicitly **not**
supported. Validated by porting `PullBackAndGo.cs` — long-only `EnterLongStopMarket`, with C#
ground truth, so a long-side fill bug is found against NT8 rather than blamed on a new
strategy.

**M16 — the indicator-parity debt: ATR, StdDev, Bollinger, Keltner.** `indicators.py` flagged
this from the start. Five consumers, not one: Keltner for the squeeze, all three unported
NinjaScripts (`ATR()`), EMA crossover's stop rule, ATR-multiple brackets, and the compression
classifiers. Expect **exactly the EMA bug — seeding, not formula**. Read each out of NT8 and
pin it; do not answer from memory. Keltner is the one most likely to be silently wrong
(platforms disagree on midline and multiplier). Note BB/KC grids are swept over period *and*
multiplier, so the 66 MB → 595 MB lesson applies with an extra factor: keep boolean gates only.

**M17 — the archetype protocol.** `sweep.py` is hardcoded to `DeadCatParams` in six places.
**Strategy is a third axis above the `Dataset`, alongside M13's resolution and M14's
contract** — same pattern, same one-`Dataset`-per-value shape, same nullable results column.
Build one mechanism, not three, and land `strategy`/`resolution`/`contract` together before
the stale DuckDB re-run so the schema settles once. Also makes `prepare` stop computing every
archetype's indicators unconditionally, which M10 needs anyway. The shared bracket engine is
extracted **during** M18 — before is designing from one example, after means duplicated
fidelity-critical code shipped.

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
(archetypes × combinations × resolutions × contracts). Against PF 0.746 it separates "worse
than random", "no better than random" and "better but not past costs". Must be matched on
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

**M13 — bar resolution as a sweep axis (2/5/15/30 min).** Planned. **The existing 1-minute
archive is sufficient — no re-export, no AddOn change.** Resampling is **exact, not
approximate**: OHLC aggregation is associative, so a 5-minute bar built from five 1-minute
bars is bit-identical to one NT8 builds from ticks. Do *not* reach for `data/tick/`; that
would be the more-precise-than-NT8 error. Bucket by **minutes since the session open**, never
wall clock: 2/3/5/10/15/30/60 all divide the 1,080-minute offset to 18:00 ET so the two
agree, which is exactly why an untested implementation looks fine until someone tries 7.
Whether NT8 anchors the same way is settled by the *existing* Tier-2 trade-list
reconciliation at that resolution, not by importing NT8's coarse bars. Resolution changes the
strategy, not just the sampling — order lifetime, the ratchet and `bars_required_to_trade`
are all per-bar — so it must be a first-class results column. Expect the ambiguous-bar rate
to climb well above 1-minute's 3.4%; if a coarse resolution looks profitable, check that
first.

**M14 — per-contract sweeps.** Planned. `sweep.sweep()` already accepts a single contract's
frame, so what is missing is the cross-contract table, a `contract` column in DuckDB, and the
framing. **Report the spread, not the winner**: a contract is ~3 months of front-month, so
"best contract" is mostly "best quarter", and picking the best of 19 × N combinations is the
multiple-comparisons trap §11.4 already guards against. Overlaps M7's walk-forward — share
the machinery. Its distinct value is that it uses **raw, not back-adjusted** prices (the only
way to test round-number stops), contains **no roll** so it is directly Tier-2 reproducible
(the cheapest route to the NQ reconciliation), and makes an outlier contract read as the data
bug it usually is. Default to the **front-month window**; full contract life overlaps its
neighbours and double-counts calendar days. Architecturally identical to M13 — both are axes
*above* the `Dataset` — so build one mechanism, not two.

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

- **NQ is fully wired up** — 19 contracts, 1,633,461 bars over 2021-12-05 → 2026-08-10, all
  18 rolls on genuine crossovers, sweeps running in parallel. Instrument scaling is proven
  exact (same bars, both specs, ×10 gross P&L per leg, commission unscaled).
- **TODO: reconcile NQ against NT8.** No NQ Strategy Analyzer export has ever been compared
  trade-for-trade, so NQ inherits its fill-semantics confidence from MNQ rather than earning
  it. Needs NinjaTrader time, not code time; blocks nothing. The recipe is written out in
  `docs/roadmap.md` under "Outstanding: reconcile NQ against NT8" — export **Trades**, not
  the summary, or every rule that matters stays hidden.
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
- The DeadCatBounce archetype is **unprofitable across all 192 combinations tested** at
  realistic costs (best PF 0.746). **Decided: not a blocker.** Build the system out first
  and treat DeadCatBounce as the test fixture that proves it works; which archetype is
  actually worth trading is a later question.
