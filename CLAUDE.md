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

## Ground truth

- `ninjatrader-scripts/Strategies/DeadCatBounce.cs` (submodule) — the strategy source.
  **Check it is current before porting**; it has been ahead of the committed version before.
- `docs/nt8-fidelity.md` — every NT8 rule the simulation implements and the evidence for it.
  Read this before changing anything in `nqbt/sim/`.
- An NT8 trade-list export (Strategy Analyzer → Trades → Export) is the only way to settle
  fill-semantics questions. Summary statistics hide them.

## Gotchas that cost real time to find

- Entry orders are **not GTC** — NT8's managed approach cancels them after one bar.
- The trigger is `min(Low[0], Close[0] - 2 ticks)`, not the bar's low. Binds on ~⅓ of signals.
- `IsFillLimitOnTouch = false`: targets need `low < target`, not `<=`.
- Ambiguous bars (stop and target both in range) resolve to whichever is **nearer the open**.
  A blanket worst case is *more* pessimistic than NT8, not equal to it.
- `MaxRiskPerTrade` is in **ticks**, not dollars.
- **TA-Lib's EMA ≠ NT8's EMA** (different seeding). `indicators.py` hand-rolls NT8's
  recursion. TA-Lib is reserved for MACD/RSI/BB/ATR, which have the same problem unfixed.
- NT8 serves only **~95 days of history per contract** regardless of the range requested, so
  volume-crossover rolls are undetectable. The splicer rolls at the coverage handover.
- NT8 trade-list exports are in **UTC**. Bar timestamps are **end-of-bar, UTC**.
- NQ and MNQ share a tick size but their tick values differ 10×. Everything monetary must go
  through `instruments.py`.

## Environment

Python 3.14 venv at `.venv`. Run tools as `./.venv/Scripts/python.exe -m ...`.

```bash
./.venv/Scripts/python.exe -m pytest          # 149 tests
nqbt ingest | contracts | splice | run
```

Sweeps are currently **Python-only** — see the README for the API.

## Conventions

- Trade logs are **one row per leg exit**; `stats.summarise` aggregates to one row per trade.
  NT8's "total trades" is the leg count, so use `stats.leg_summary` when reconciling.
- `r_multiple` uses **planned** risk (`stop − trigger`), matching how the C# places targets.
- Everything expensive is precomputed once in `runner.prepare`; the sweep loop must stay
  cheap. Never recompute an indicator inside a combination.
- Moving-average grids keep only the boolean gate unless `keep_values=True` (66 MB vs 595 MB).
- Numba functions are `@njit(cache=True)` — required so parallel workers reuse the disk cache.
- `data/minute/` and `data/tick/` share the `.Last.txt` suffix. **Never glob across both**;
  `ingest.parse_export` hard-fails on a tick file.

## Status

Done and validated: data ingestion with incremental append, contract splicing with
back-adjustment, NT8-compatible indicators, the DeadCatBounce simulation, and the sweep +
statistics + DuckDB results layer. Reconciliation against NT8 is **1143/1144 leg exits
identical (99.91%)**.

## Planned, not yet done

**M6 — parallelise the sweep.** joblib/loky over chunked combinations. `@njit(cache=True)` is
already set so workers reuse the compiled cache rather than each re-JITing. The `Dataset`
must be shared rather than pickled per worker — joblib auto-memmaps arrays above 1 MB, which
should cover the condition matrices, but verify rather than assume. Only worth it above a few
thousand combinations; a combination currently costs 26 ms.

**M7 — walk-forward and Monte Carlo.** `walkforward.py`: rolling in-sample/out-of-sample
window splits over the cached series. `montecarlo.py`: permutation/resampling of a strategy's
trade sequence to test robustness beyond the single historical path. Both sit on top of the
existing results layer.

**CLI gaps.** No `nqbt sweep` command — sweeps run from Python only. No `nqbt report` for
querying `results/sweeps.duckdb`.

**Spec features not yet built.** The build spec calls for these; none exist yet:
- Moving-average **trailing stop mode** as a per-run toggle (only the structural
  swing-high stop is implemented). Needs `MovingAverageGrid(keep_values=True)`.
- **Round-number stop avoidance** — never place a stop exactly on a round number.
  Note this is incoherent with back-adjustment, which shifts absolute price levels.
- **Confluence counting** wired into an archetype. `conditions.count_true` exists and is
  tested, but no archetype consumes it, so "at least N of M filters" is not yet sweepable.

**M8 — bar-major restructuring.** Only if profiling a real sweep size justifies it. Do not
start on assumption.

**Open items.**
- One roll is flagged as premature: MNQ 06-26 → 09-26, handover volume ratio 0.27. Sits in
  the most recent quarter. Not yet reviewed.
- **NQ is completely untested** — only MNQ exports exist. Code is instrument-aware throughout
  but no NQ data has ever been through it.
- MAE/MFE use a different definition from NT8's (mine measure to the exit bar's extreme,
  NT8's cap at the exit). Reporting only, no P&L effect. Unresolved.
- The DeadCatBounce archetype is **unprofitable across all 192 combinations tested** at
  realistic costs (best PF 0.746). Worth deciding whether to keep sweeping it or move to a
  second archetype before investing further in this one.
