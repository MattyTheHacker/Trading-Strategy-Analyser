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
- Parallel sweeps top out around **5×, not 16×**, and that is the hardware, not the harness.
  Per-core throughput drops 1.5× when all 8 physical cores are busy (mobile Ryzen; ~5.1 GHz
  single-core boost against a much lower all-core clock). `n_jobs=8` gets 4.4×; `n_jobs=16`
  is SMT and adds ~10% for twice the memory. Measured, not guessed — don't "fix" it.

## Environment

Python 3.14 venv at `.venv`. Run tools as `./.venv/Scripts/python.exe -m ...`.

```bash
./.venv/Scripts/python.exe -m pytest          # 156 tests
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
- Everything expensive is precomputed once in `runner.prepare`; the sweep loop must stay
  cheap. Never recompute an indicator inside a combination.
- Moving-average grids keep only the boolean gate unless `keep_values=True` (66 MB vs 595 MB).
- Numba functions are `@njit(cache=True)` — required so parallel workers reuse the disk cache.
- `data/minute/` and `data/tick/` share the `.Last.txt` suffix. **Never glob across both**;
  `ingest.parse_export` hard-fails on a tick file.

## Status

Done and validated: data ingestion with incremental append, contract splicing with
back-adjustment, NT8-compatible indicators, the DeadCatBounce simulation, the sweep +
statistics + DuckDB results layer, and parallel sweeps over cores. Reconciliation against
NT8 is **1143/1144 leg exits identical (99.91%)**.

`sweep.sweep(..., n_jobs=8)` is verified to produce results byte-identical to the serial
path. The `Dataset` is shared, not copied: `Dataset.slim()` drops the 121 MB bar frame to a
13 MB index-only view, and joblib memmaps the arrays — **confirmed** by probing a live
worker, where `close`, `ema.below` and `sma.below` all arrive as `numpy.memmap`.

## Planned, not yet done

**M7 — walk-forward and Monte Carlo.** `walkforward.py`: rolling in-sample/out-of-sample
window splits over the cached series. `montecarlo.py`: permutation/resampling of a strategy's
trade sequence to test robustness beyond the single historical path. Both sit on top of the
existing results layer.

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

**M9 — split market context from strategy simulation.** Prerequisite for everything below.
`Dataset`/`prepare` are strategy-agnostic but live in `sim/runner.py`; lift them to
`nqbt/context.py`. Formalise the trade-log schema in `nqbt/trades.py` so the simulator and a
manual-trade importer produce the *same* thing — it needs `direction` (the archetype is
short-only, so nothing records it today), `instrument` (NQ and MNQ differ 10× in tick value)
and `source`. Rule: `stats.py` must not import from `nqbt.sim`.

**M10 — the conditions the review needs and we lack.** Regime classification
(`nqbt/regime.py`, Kaufman efficiency ratio → directional / consolidating / unclassifiable,
the middle band being the no-trade state); relative volume normalised **by time of day**, not
by a rolling window, or it just measures the clock; a compact trend label off the existing
MA grids.

**M11 — manual trade review.** Import real trades, annotate each against the market context
at its entry bar, stratify realised P&L by condition. Biggest trap: **annotate against the
raw series, never the back-adjusted one** — back-adjustment shifts historical prices by
hundreds of points, so the lookup succeeds and every comparison is silently wrong. Needs a
multiple-comparisons guard (minimum stratum size, permutation test, holdout); without it the
output is confident and wrong.

**M12 — web GUI.** Long term. Same lesson as the CLI: it calls the existing functions and
defines no statistic of its own. Streamlit for the read-only views, and don't start until
the review outputs are stable.

**Open items.**
- One roll is flagged as premature: MNQ 06-26 → 09-26, handover volume ratio 0.27. Sits in
  the most recent quarter. Not yet reviewed.
- **NQ is completely untested** — only MNQ exports exist. Code is instrument-aware throughout
  but no NQ data has ever been through it.
- MAE/MFE use a different definition from NT8's (mine measure to the exit bar's extreme,
  NT8's cap at the exit). Reporting only, no P&L effect. Unresolved.
- The DeadCatBounce archetype is **unprofitable across all 192 combinations tested** at
  realistic costs (best PF 0.746). **Decided: not a blocker.** Build the system out first
  and treat DeadCatBounce as the test fixture that proves it works; which archetype is
  actually worth trading is a later question.
