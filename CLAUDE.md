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

- **Reasoning goes in `docs/`, not in the source** (#105). Code should be readable on its own
  terms — prefer a clearer name or a smaller function over a comment explaining an unclear
  one. Docstrings say **what** a thing is and how to use it, and stay short. A brief comment is
  fine where something is genuinely non-obvious: a subtle index, a deliberate deviation, a
  workaround. Arguments, justifications, measurements, decision records and traps belong in
  `docs/roadmap.md` or `docs/nt8-fidelity.md`, with at most a one-line pointer from the code.
  **This reverses the earlier "docstrings say why" rule**, which drove `nqbt/` to 33% prose by
  line; #105 carries the migration, which is a migration and not a deletion.
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
PullBackAndGo simulations, the sweep + statistics + DuckDB results layer, parallel sweeps
over cores, the numpy-native summary path that keeps a combination off pandas, and
**M18's EmaCrossover** — the first original archetype, with the shared bracket engine
extracted out from under all three.

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
its own data too. **NQ is now reconciled against NT8 (#66)**: 1,105 of 1,112 joined legs
identical on every field (99.37%) on NQ 03-24, with no instrument-dependent behaviour found.
Both roots therefore carry fill-semantics evidence of their own.

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
kept because M15 needs the same one. **The float64 precision problem was on the read side
all along, and was blamed on the write side until #113.** Measured on the 1,664-leg
`live_mnq.csv` capture, 18,304 float values across 11 columns:

| | read default | read `round_trip` |
|---|---|---|
| write default | 342 moved | **exact** |
| write `%.17g`  | 576 moved | **exact** |

Read the diagonal, not the margins. `float_precision="round_trip"` is what makes the gate
correct — with it *either* writer is exact. `%.17g` on its own fixes nothing, and paired
with the default parser it makes matters **worse**, because 17-digit text is precisely what
a lax parser mis-rounds. `float_precision="high"` is not enough either; it fails the same
way. The `%.17g` is kept because it is explicit and costs nothing, **not** because it is
load-bearing — the earlier note claiming it was, and citing "4 of 1,664 `r_multiple`
values", was measuring the reader and attributing it to the writer.

Until #113 the gate read with a bare `pd.read_csv`, so **a one-ULP difference was invisible
to it** — a two-byte textual change in a captured log reported `BYTE-FOR-BYTE IDENTICAL`.
`tests/test_trade_log_gate.py` now pins that it cannot regress.

**Every historical claim was re-run through the fixed gate (#113) and all of them hold.**
One capture script was run at each commit rather than each commit's own copy, so the
harness is a constant and any difference is library code; `prepare`'s signature is
unchanged across M9, M15 and M20a, and only its module moved, so one shim covers them all.

| claim | commits | gate | `sha256` |
|---|---|---|---|
| M9 move | `6975a56`→`f71baa3` | identical | identical |
| M9 schema | `f71baa3`→`8b2c5ab` | pre-existing columns identical | differ (3 columns added) |
| M15.1 sign | `4be9980`→`96be12a` | identical | **differ — see below** |
| M15.4 PullBackAndGo | `cc1be25`→`cb2e2c7` | identical | identical |
| M20a | `f992c05`→`9caf653` | identical | identical |
| M15.2/3 cancel | `96be12a`→`cc1be25` | 10 files differ | differ |
| M15.5 fills | `cb2e2c7`→`0871831` | 14 files differ | differ |
| #113 ruff auto-fix | `2243779`→`752155c` | identical | identical |

**#113 was gated retroactively (2026-08-19), because it should not have been ungated.** A
"Ruff auto-fix" PR reached into the `@njit` loop: `simulate_deadcat`'s MAE/MFE tracking went
from `if run_high < high[i]` to `run_high = max(run_high, high[i])`, and `archive.py`'s
merge inverted the branch that implements "the newest bar may insert but never overwrite".
Both are equivalent on inspection — and inspection is not the gate. All 14 files come back
identical on both the gate and `sha256`. **The lesson is where the change was, not what it
was:** a lint PR is the last place anyone looks for a simulator change, so read what an
auto-fixer touched under `nqbt/sim/` before merging, not after.

The last two *should* differ — force-flat cancellation removes real legs (113,164 → 113,116)
and M15.5 changed fill semantics. Both are the fix working, not a regression.

**M15.1 is numerically identical but not textually identical, and that is new information.**
`d = ±1` turns `0.0` into `-0.0`, so 6,908 values across `gross_pnl`, `net_pnl`,
`r_multiple`, `mae_points` and `mfe_points` flip their sign bit. **Every one of them is
zero** — verified, none non-zero — and `-0.0 == 0.0`, so sums, the `pnl == 0` scratch test
and every statistic are unaffected. The right phrase for M15.1 is therefore *numerically*
identical; only the CSV text moved.

That is also why **`sha256sum` is a cross-check, not the gate**. It is strictly stronger
than `assert_frame_equal(check_exact=True)` and will flag a benign signed zero as a
difference. Use it to catch the gate itself being broken — it is code, and it has been
wrong — but when the two disagree, find out which kind of difference it is before believing
either. Verifying the gate can still *fail* is part of using it, and a pandas round-trip is
the wrong way to do that: perturbing a value via `read_csv`/`to_csv` trips a *collateral*
difference and reports a column you did not touch, which reads like success. **Perturb the
CSV text directly**, one field, and check the reported column is the one you edited.

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

**#33 has landed: a sweep no longer builds a trade log it throws away.**
`stats.summarise_legs` reads the simulation's raw `trades.LegMatrix`; `stats.summarise` is
unchanged and remains the reference. A combination over the full 1.65M-bar spliced series
went **28.3 ms → 9.0 ms** against the `@njit` loop's own 9.3 ms — the summary is now inside
the noise of the simulation. All 14 captured files are byte-identical across the change,
including the two sweep summary tables the new path produced over 218,164 legs. What a
caller needs to know:

- **Both paths share `_summarise_arrays`** and differ only in how the per-trade vectors are
  obtained. That is what reduces "do they agree?" to "do they group the legs the same way?"
  — **do not re-inline it into either caller.**
- **Pandas' `groupby.sum` is Kahan-compensated**, and `_grouped_sum` carries the same
  compensation term for that reason alone. A plain running sum disagrees with pandas in the
  last bit on ~21% of four-leg groups, `np.add.reduceat` on ~35%, and the costed
  DeadCatBounce case catches it on real trades. Every *ungrouped* pandas reduction is
  bit-identical to numpy's, strided column views included; only the grouping needed care.
- **`Dataset.day_codes` is local, not UTC.** `summarise` groups daily P&L by
  `DatetimeIndex.date`, which is the index's timezone. On the UTC archive the two coincide,
  so a UTC-only version would have passed every test and been an hour out on a
  `Europe/London` index.
- **`Archetype.legs` is required beside `run`.** An archetype registered with only `run`
  would silently be the slow one in a sweep, and the symptom would be a wall clock.
- **`trades.validate_legs` is the producer boundary a sweep now crosses**, since it never
  calls `validate`. Same invariants, plus one `validate` deliberately omits: on a matrix,
  `exit_reason` must be in `EXIT_REASONS`, because only the simulator can have written it.
- **`keep_trades` changes what `run_combination` returns, never what it measures.**

**M18 has landed: EmaCrossover is the first original archetype, and it reads as a known
negative.** On costed MNQ from 2024 (914,700 bars, EMA(9)/EMA(21)) it returns a profit factor
of 0.866 over 41,784 trades, and against 200 matched random-entry draws it sits at the **49th
percentile on profit factor**, the 47th on expectancy and the **1st on win rate**. That is the
result it was built to produce, and it is also the lookahead check: a crossover computed one
bar early would have come back spectacularly profitable, not at the null's median. Quote
`docs/roadmap.md` § M18, not this line. What a caller needs to know:

- **`nqbt/sim/bracket.py` is the shared bracket engine**, extracted during M18 per #38. Stop,
  targets, ambiguity policy, limit-fill rule, leg writer. The split is **entry half versus
  bracket half** — a new archetype writes only the first. All 14 captured DeadCatBounce trade
  logs are byte-for-byte identical across the extraction and across the whole milestone.
  **Do not fork it**; the reconciliation evidence lives there.
- **`CrossAbove(a, b, n)` is a window, not a bar.** `conditions.cross_above` implements NT8's
  form, with `n` swept. The naive one-bar form is the `n = 1` case and not the definition, and
  equality on the *prior* bar counts as a cross.
- **Nothing in EmaCrossover has NT8 evidence behind it.** `tier2` is `TIER1_ONLY` and reaches
  the results table, so a ranking cannot silently put it beside the two reconciled ports.
  `docs/nt8-fidelity.md` § M18 records each rule and the NinjaScript it would be written as.
- **A third mechanism reached a fill rule the first two could not.** An entry whose protective
  stop would land at or through its own fill is skipped — the stop-entry submittability rule
  applied to the protective stop. Unreachable in both ports by construction. **Two archetypes
  are not enough to exercise the fill model either.**
- **R means something different here.** With an ATR stop, `r_multiple` is volatility-scaled
  rather than structure-scaled, so crossover results are **not comparable to DeadCatBounce
  results at the same R numbers**.
- **Flat between trades, not stop-and-reverse.** The flip closes and reopens as two fills at
  the same open price, each paying its own costs. Economically a reversal, two trades in the
  log — say so in any comparison against published crossover results.
- **A combination is 49.0 ms and 167,136 legs** against DeadCatBounce's 3.3 ms and 14,556 —
  ~11.5× the legs, not the ~30× predicted. `allocate_output` reserves **27 MB per worker**, so
  read a permissive grid's signal count before launching it, not after.

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
**Order: M10 → M11 → M7b → M19 → M12.** M9, M20a, M15, **M16**,
**M17(+M13+M14)**, **M7a**, **the numpy summary path (#33)** and **M18** are all done — see
Status.

**The NinjaTrader queue is empty except #67, and nothing is waiting on it.** That session
(2026-08-16) closed #20, #21, #22, #23's measurement half, #66 and #92 in one sitting. #67
(order lifetime) gates only M19, which is queued rather than scheduled. **Do not re-read
this section as a reason to book NT8 time** — the code column is what is short.

**~~M18~~ — EMA crossover: done, and it reads as the known negative it was built to be.**
See Status. **Next is M10.**

**#23's roll-boundary half is still open**, and it is a decision rather than a measurement,
so it can be taken any time. The session half is settled: True Range does not reset.

**New archetypes are developed in Python only.** EmaCrossover and squeeze breakout have no
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
- **The gate for a direction-symmetric change is identity of every short-only trade
  log**, not "the reconciliation still passes" — ×(±1.0) is exact in IEEE 754, so both halves
  of a forked bracket reduce to today's behaviour at `d = −1` whether or not they agree at
  `d = +1`. `tools/capture_trade_logs.py` + `tools/compare_trade_logs.py` are that gate.
  **Read "identity" as numerical, not textual**: ×(−1.0) sends `0.0` to `-0.0`, which is a
  different 8 bytes and an equal number, so M15.1 moved 6,908 zeros without moving a result
  (re-verified in #113). `assert_frame_equal(check_exact=True)` is the right comparison and
  a file hash is too strict — a signed zero is the one difference to accept.
- **`EXIT_SIGNAL` is now spent, by EmaCrossover alone.** A rule-driven exit with no bracket
  level of its own. DeadCatBounce, PullBackAndGo and `bracket.py` have no such exit, and a
  test guards structurally that none of the three imports the constant.
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

**~~M16 — the indicator-parity debt~~ — done.** `nt8_atr`, `nt8_stddev`, `nt8_bollinger` and
`nt8_keltner` are in `indicators.py`, pinned against 89,330 bars read out of NT8; the
evidence is `docs/nt8-fidelity.md` §M16 and the gotcha above. It was **exactly the EMA bug —
seeding, not formula** — except Keltner, which matched neither half of the usual definition.
What survives for its consumers: BB/KC grids are swept over period *and* multiplier, so the
66 MB → 595 MB lesson applies with an extra factor — **keep boolean gates only**.

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
  `ambiguous_share`. Reads 0.0001 on DeadCatBounce and 0.010 on EmaCrossover at 1 minute;
  expect it to climb sharply with bar size, and read it before believing a coarse resolution.
  **The prediction that a hold-until-opposite-cross archetype would be dominated by it was
  wrong** — crosses on 1-minute bars are frequent enough that holds end long before the
  session does.

**M19 — squeeze breakout.** Queued, not scheduled; the expensive archetype. It inherits a
working `EXIT_SIGNAL`, a bracket engine that is already a set of callable `@njit` device
functions, and a measured per-combination cost for a high-leg archetype (see M18 in Status). "Squeeze" means at
least three things — recommend the **Bollinger-bandwidth** form first (one indicator, drops
the Keltner parity question, shares its quantity with M10.1's regime classifier), and port
`InsideBar.cs` before building anything from scratch since it is the same compression-then-break
idea **with C# ground truth**. Real cost is a two-sided OCO entry model the loop lacks. Traps:
lookahead (bands must come from *completed* bars), a high ambiguous-bar rate, and results that
cluster by volatility regime so the aggregate PF averages two populations.

**~~M7a~~ — the random-entry null: done.** `nqbt/randomentry.py`. What a caller needs to
know: it matches **count, time-of-session and direction** and randomizes only which trading
day each signal lands on. Time-of-session matching is **exact, not bucketed** — a null that
drifts toward thin overnight bars loses for reasons unrelated to entry quality and flatters
every strategy tested against it. It runs the archetype's **own** `run` via a `signal=`
override rather than its own copy of the simulation, so brackets, costs and direction are
identical by construction; `Archetype` carries a `signal` field for this and it is
**required**, so a new archetype cannot be registered without one. Output is a Monte Carlo
test (default 200 draws), not a single random backtest. Defaults to `RATE_STATISTICS`
because the arms match on signals and diverge on fills — read `net_pnl` only against the two
trade counts, which are on every row. **Hoist `SessionMinutePool`**: rebuilding the grouping
per draw was 89% of an iteration.

**M7b — walk-forward and Monte Carlo** stays late. `walkforward.py` and `montecarlo.py` are
unbuilt; they answer different questions from M7a — whether a *parameter choice* survives
unseen data, and whether an equity path was luckier than its trades justify. M7a's
machinery is what #48's permutation guard inherits.

**Moving-average axes.** Periods *and* on/off toggles are both already sweepable, jointly —
every `DeadCatParams` field except `target_r_multiples` is a legal axis, and `dead_axes()`
refuses a period whose toggle is off everywhere. Two dimensions are **not** reachable and are
planned: **MA kind as an axis** (kind is fixed by field name; only `nt8_ema`/`nt8_sma`
exist), and **multi-timeframe MAs** (everything is computed on the 1-minute close). Traps for
both are in `docs/roadmap.md` — a new kind must match NT8's recursion rather than the
textbook one, and a higher-timeframe MA must be stamped from the previous *completed* coarse
bar or the backtest reads the future. **Both are now much cheaper, because M16 and M17 have
landed**: M16 established the pin-it-against-NT8 procedure a new kind needs, and M17's
`required_context` already keys grids by `(kind, period)`. Due a reconsideration.

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

**M8 — bar-major restructuring. The premise was measured, found mostly false, and the
overhead that capped it has since been removed.** Profiling one combination over 1.65M bars
put `stats.summarise` at 51%, `trades_to_frame` at 20%, the `@njit` loop at 23% and the
signal ANDs at 2%. Bar-major restructures the 23%, so making the simulation *entirely free*
was only ever worth ~1.3× — Amdahl caps it there. **#33 took the 71% instead**, and a
combination is now 9.0 ms against 28.3 ms, of which 9.3 ms is the loop. M8's ceiling is
unchanged and its share of a combination is now most of it, so **it is still not scheduled**:
re-profile before believing any figure here, and do M8 only if the loop is genuinely what a
real sweep is waiting on.

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
- ~~**Reconcile NQ against NT8 (#66)**~~ — **done.** 99.37% of joined legs identical on every
  field, no instrument-dependent behaviour. `docs/nt8-fidelity.md` has the table and the two
  residual trades. `tools/reconcile_nt8.py` is the mechanism, reusable for the next archetype.
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
- **But its entry rule is measurably better than random** (M7a, `nqbt/randomentry.py`). On
  costed MNQ from 2024, against 500 matched random-entry draws, it sits at the 99.6–99.8th
  percentile on profit factor, expectancy and win rate (p ≈ 0.008–0.012) — while still
  losing money. That is "there is signal; the loss is in costs, hold time or bracket
  geometry", **not** "the entry rule is worthless", and the two were indistinguishable
  before this existed. It does not make the archetype tradeable. Caveats that must travel
  with the number: one pre-specified combination on one root, not a sweep; the arms match on
  **signals** and diverge on **fills** (74.4% vs 47.7%), so per-trade rates are the fair
  comparison and `net_pnl` is not; and the rule under test is bar *selection*, which carries
  bracket geometry with it. **Quote `docs/roadmap.md` §M7a, not this line**, and re-run
  rather than citing these figures after any fill-rule change.
