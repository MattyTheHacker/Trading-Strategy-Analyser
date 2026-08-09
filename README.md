# nqbt — NQ/MNQ strategy research and backtesting

A **Tier 1** research tool: rip through large parameter sweeps fast and narrow them to a
shortlist. NinjaTrader 8's Strategy Analyzer stays the ground truth — every surviving
candidate gets re-validated there (Tier 2) before it's trusted.

The governing constraint is **fidelity parity, not fidelity maximisation**. This matches
NT8's default bar-close OHLC fill behaviour exactly. Being *more* precise than NT8 is as
much a bug as being less precise, because it makes the two tiers disagree in ways that
can't be attributed. See [docs/nt8-fidelity.md](docs/nt8-fidelity.md) for the fill
semantics and the reconciliation record.

## Status

| Milestone | State |
|---|---|
| M1 Data foundation — instruments, sessions, ingest, Parquet cache | done |
| M2 Contract splicing — roll detection, back-adjustment | done |
| M3 Indicators & conditions — NT8-compatible EMA/SMA, session VWAP | done |
| M4 DeadCatBounce simulation + NT8 reconciliation | done, **gate passed** |
| M5 Sweep harness, DuckDB results, statistics | done |
| M6 Parallelise the sweep across cores | done |
| M7 Walk-forward and Monte Carlo | not started |
| M8 Bar-major restructuring | premise measured — see below |

**156 tests passing.**

**Reconciliation against NT8: 1143 of 1144 leg exits identical (99.91%).** The single
remaining leg is worth $19.50 and is an NT8 order-handling artefact.

## Setup

Python 3.14 with cp314 wheels for every dependency — no downgrade needed.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pip install -e . --no-deps
.venv/Scripts/python -m pytest
```

## Data layout

Raw NT8 exports are gitignored and split by resolution, because tick and minute exports
share the same `.Last.txt` naming and must never be globbed together:

```
data/minute/MNQ 03-24.Last.txt     yyyyMMdd HHmmss;o;h;l;c;v   (end-of-bar, UTC)
data/tick/  MNQ 09-26.Last.txt     yyyyMMdd HHmmss fffffff;last;bid;ask;volume
cache/bars/MNQ/MNQ_2024H.parquet   cleaned, session-tagged, one file per contract
cache/manifest.json                incremental-append bookkeeping
cache/continuous/MNQ_raw.parquet   spliced series (and MNQ_backadj.parquet)
results/sweeps.duckdb              every sweep, queryable together
```

Currently cached: **19 MNQ contracts, 1,704,672 bars**, splicing to a continuous series of
**1,651,911 in-session bars covering 2021-12-05 → 2026-08-07**.

Tick data is present but deliberately **not** wired into the simulation — the spec defers
tick-level fills to Tier 2. Its one high-value use would be measuring how often the
same-bar stop/target assumption actually binds.

## Usage

```bash
nqbt ingest                      # parse exports into the Parquet cache (incremental)
nqbt contracts                   # what is cached
nqbt splice --root MNQ           # build the continuous series
nqbt splice --root MNQ --back-adjust --diagnostics
nqbt run --root MNQ --commission 0.74 --slippage 1 --explain 10
```

`nqbt run --explain N` writes a hand-checkable audit trail: the signal bar's geometry,
each gate's operands and verdict, the trigger and stop arithmetic, how the entry filled,
and where every leg left — plus a bar-by-bar ratchet history.

Sweeps are driven from Python rather than the CLI, deliberately — a `Grid` takes arbitrary
lists per axis with toggle interactions, and flattening that into argparse flags would be a
lossier way of saying the same thing:

```python
from nqbt import splice, sweep, results
from nqbt.sim.types import DeadCatParams

bars = splice.load_continuous("MNQ")
grid = sweep.Grid.of(
    DeadCatParams(commission_per_contract=0.74, slippage_ticks=1.0),
    ema_period=[9, 15, 21, 30],
    fast_sma_period=[40, 60, 80],
    use_slow_sma=[True, False], slow_sma_period=[120, 175],
    use_vwap=[True, False],
    ambiguity_policy=[1, 0],
)
res, _ = sweep.sweep(bars, grid, n_jobs=8)   # n_jobs=1 (default) stays in-process
results.save_sweep(res, root="MNQ", instrument="MNQ", bars=bars, axes=grid.axes)
print(sweep.rank(res, "profit_factor", top=10, min_trades=200))
```

## Architecture

```
nqbt/
  instruments.py   NQ/MNQ specs. Every dollar figure flows through here — NQ and MNQ
                   share a tick size but their tick values differ 10x.
  sessions.py      CME ETH calendar, UTC -> US/Eastern, trading-day assignment.
  ingest.py        NT8 parser, incremental append, per-contract Parquet.
  splice.py        Roll detection and back-adjustment.
  indicators.py    NT8-compatible EMA/SMA, session-anchored VWAP.
  conditions.py    1D parameter-free gates, 2D [period, bar] moving-average grids.
  sim/
    types.py       DeadCatParams, trade-record layout.
    deadcat.py     @njit simulation — the only path-dependent code.
    runner.py      Dataset: everything expensive, computed once per series.
    explain.py     Per-trade audit trail for hand-verification.
  sweep.py         Grid, combo-major sweep, ranking; n_jobs spreads chunks over
                   processes sharing one memmapped copy of the dataset.
  stats.py         Per-trade summary statistics.
  results.py       DuckDB persistence.
```

**Why it's fast.** Everything expensive is hoisted out of the sweep loop into
`runner.prepare`: candlestick geometry, session VWAP, and a `[n_periods, n_bars]` boolean
matrix per moving-average gate covering every period in the grid. A combination then costs
a boolean AND plus one simulation pass.

| operation | cost |
|---|---|
| ingest, cold / warm | 5.2 s / 0.02 s |
| prepare (1.65M bars) | 0.71 s |
| one combination | 30 ms |
| 1,536-combination sweep, serial | 45.4 s |
| 1,536-combination sweep, `n_jobs=8` | 10.4 s (4.4×) |

**Parallelism tops out near 5×, and that is the hardware.** Per-core throughput drops 1.5×
once all 8 physical cores are busy — 30.8 ms/combination alone against 46.1 ms with eight
running — so ~5.3× is the ceiling and the harness gets 4.4× of it. `n_jobs=16` is SMT: it
adds 10% for twice the memory. Worker startup is ~1.5 s, so serial is the right default
below a few hundred combinations.

The dataset is shared rather than copied. `Dataset.slim()` drops the 121 MB bar frame to a
13 MB index-only view, and joblib memmaps the arrays — verified by probing a live worker,
where `close` and both moving-average grids arrive as `numpy.memmap`.

**Where a combination's 30 ms actually goes**, which is not where M8 assumed:
`stats.summarise` 51%, `trades_to_frame` 20%, the `@njit` simulation 23%, signal ANDs 2%.
Bar-major restructuring targets that 23%; the 71% of pandas overhead — building and
aggregating a DataFrame per combination, in a sweep that then discards the trade log — is
the bigger prize and should come first.

Two memory notes: moving-average grids keep only the boolean gate by default
(`keep_values=True` for the raw values, needed solely by an MA trailing stop) — 66 MB
versus 595 MB for 40 periods. And `Grid` refuses an axis whose filter is off in every
combination, which otherwise multiplies runtime for byte-identical rows.

## Current finding

Over 4.7 years at $0.74/RT commission and 1 tick of slippage, across 192 combinations:

```
profitable combinations (PF > 1.0):   0 of 192
best PF 0.746        median PF 0.706
```

Nothing in the tested space survives costs; the best combination still loses ~$7/trade
over 5,224 trades. The fill assumption is not what's causing it — NT8's ambiguity rule
versus a blanket worst case differs by only **+0.009 PF** on average, with ambiguous bars
at 3.4% of exits. The losses are structural.

## Known limitations

- **Volume-crossover rolls are undetectable from NT8 data.** NT8 serves ~95 days per
  contract regardless of the range requested, ending ~4 days before expiry, and the
  crossover happens at or after that point. The splicer rolls at the coverage handover
  instead, which is the same switch NT8 itself makes. Three 2022 rolls are flagged because
  their coverage ends 8 days before expiry rather than 4, so volume had not yet migrated.
- **NQ is untested** — only MNQ exports exist. The code is instrument-aware throughout.
- **`r_multiple` uses planned risk** (`stop − trigger`), which is how the NinjaScript
  places its targets. Consequence: target exits land just under their nominal multiples,
  and stop exits can print below −1R when slippage or a gap made the risk actually taken
  exceed the planned risk.
- **MAE/MFE differ from NT8's definition** — mine measure to the exit bar's extreme, NT8's
  cap at the exit. Reporting only; no effect on P&L.
