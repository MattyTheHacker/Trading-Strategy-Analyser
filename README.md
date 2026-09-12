# nqbt — NQ/MNQ strategy research and backtesting

A **Tier 1** research tool: rip through large parameter sweeps fast and narrow them to a shortlist. NinjaTrader 8's Strategy Analyzer stays the ground truth — every surviving candidate gets re-validated there (Tier 2) before it's trusted.

The governing constraint is **fidelity parity, not fidelity maximisation**. This matches NT8's default bar-close OHLC fill behaviour exactly. Being *more* precise than NT8 is as much a bug as being less precise, because it makes the two tiers disagree in ways that can't be attributed. See [docs/nt8-fidelity.md](docs/nt8-fidelity.md) for the fill semantics and the reconciliation record.

## Status

**Status lives in the issue tracker**, which is the only copy that cannot go stale. This section used to hold a milestone table, a test count and a reconciliation figure; all three were wrong by the time anyone read them.

```bash
gh issue list --state open                   # everything outstanding
gh issue list --state open --label next-up   # what is at the front
gh issue view <n>                            # blocked-by, blocking, sub-issues
```

Where the live numbers are produced:

| number                        | source                                        |
| ----------------------------- | --------------------------------------------- |
| agreement rates against NT8   | [docs/nt8-fidelity.md](docs/nt8-fidelity.md)  |
| test count and coverage       | `./.venv/Scripts/python.exe -m pytest`        |
| bar, contract and roll counts | `nqbt contracts`, `nqbt splice --diagnostics` |

[docs/roadmap.md](docs/roadmap.md) carries the reasoning behind the order, the findings each milestone produced, and the decision record — not the plan itself.

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) is the working agreement — code style, tests, linting, commits, pull requests, and the trade-log gate that anything touching `nqbt/sim/` has to pass.

## Setup

Python 3.14 with cp314 wheels for every dependency — no downgrade needed.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

## Data layout

Raw NT8 exports are gitignored and split by resolution, because tick and minute exports share the same `.Last.txt` naming and must never be globbed together:

```text
data/minute/ MNQ 03-24.Last.txt    manual export   yyyyMMdd HHmmss;o;h;l;c;v (UTC)
data/addon/  MNQ 03-24.Last.txt    AddOn snapshot  same format
data/archive/MNQ 03-24.Last.txt    the durable union -- the only thing ingest reads
data/tick/   MNQ 09-26.Last.txt    yyyyMMdd HHmmss fffffff;last;bid;ask;volume
cache/bars/MNQ/MNQ_2024H.parquet   cleaned, session-tagged, one file per contract
cache/manifest.json                incremental-append bookkeeping
cache/continuous/MNQ_raw.parquet   spliced series (and MNQ_backadj.parquet)
results/sweeps.duckdb              every sweep, queryable together
```

Currently cached: **38 contracts (19 MNQ, 19 NQ), 4,601,503 bars**, splicing to continuous series of **1,663,489 in-session bars over 2021-09-19 → 2026-08-10** (MNQ) and **1,633,461 over 2021-12-05 → 2026-08-10** (NQ), each raw and back-adjusted.

**Exports are moving windows, not snapshots.** NinjaTrader serves each contract for a limited period and drops the tail once it expires, so a folder of exports quietly loses history. `data/archive/` is the durable union that ingestion actually reads.

The two sources **compound, and the order matters**. On its own a manual export returns the last ~95 days through expiry, and the AddOn ([NqbtHistoricalExporter.cs](ninjatrader-scripts/AddOns/NqbtHistoricalExporter.cs)) reaches 3–6 months further back but stops at the turn of the expiry month. But the AddOn's `BarsRequest` calls warm NinjaTrader's own local database, and a manual export dumps that database — so **run the AddOn, then re-export manually** and NT8 returns the full contract life from one source. That took the archive from 3.0M bars to 4.6M; every MNQ and NQ contract now runs from ~6 months out through to expiry, and **all 36 rolls across both roots detect a genuine volume crossover** where none did before.

Ingest also hashes the entire consumed byte range to distinguish an append from a rewrite; checking only the file head cannot see a rewritten tail, which froze stale bars in the cache and silently dropped real ones at the seam.

Tick data is present but deliberately **not** wired into the simulation — the spec defers tick-level fills to Tier 2. Its one high-value use would be measuring how often the same-bar stop/target assumption actually binds.

## Usage

```bash
nqbt ingest                      # refresh data/archive from every source, then cache it
nqbt contracts                   # what is cached
nqbt splice --root MNQ           # build the continuous series
nqbt splice --root MNQ --back-adjust --diagnostics
nqbt run --root MNQ --commission 1.50 --slippage 1 --explain 10
```

`nqbt run --explain N` writes a hand-checkable audit trail: the signal bar's geometry, each gate's operands and verdict, the trigger and stop arithmetic, how the entry filled, and where every leg left — plus a bar-by-bar ratchet history.

Sweeps are driven from Python rather than the CLI, deliberately — a `Grid` takes arbitrary lists per axis with toggle interactions, and flattening that into argparse flags would be a lossier way of saying the same thing:

```python
from nqbt import splice, sweep, results
from nqbt.sim.types import DeadCatParams

bars = splice.load_continuous("MNQ")
grid = sweep.Grid.of(
    DeadCatParams(commission_per_contract=1.50, slippage_ticks=1.0),
    ema_period=[9, 15, 21, 30],
    fast_sma_period=[40, 60, 80],
    use_slow_sma=[True, False],
    slow_sma_period=[120, 175],
    use_vwap=[True, False],
    ambiguity_policy=[1, 0],
)
res, _ = sweep.sweep(bars, grid, n_jobs=8)  # n_jobs=1 (default) stays in-process
results.save_sweep(res, root="MNQ", instrument="MNQ", bars=bars, axes=grid.axes)
print(sweep.rank(res, "profit_factor", top=10, min_trades=200))
```

## Architecture

```text
nqbt/
  instruments.py   NQ/MNQ specs. Every dollar figure flows through here — NQ and MNQ
                   share a tick size but their tick values differ 10x.
  sessions.py      CME ETH calendar, UTC -> US/Eastern, trading-day assignment.
  archive.py       Merges every export source into the durable union ingest reads.
  ingest.py        NT8 parser, rewrite detection, per-contract Parquet.
  splice.py        Roll detection and back-adjustment.
  indicators.py    NT8-compatible EMA/SMA, session-anchored VWAP.
  conditions.py    1D parameter-free gates, 2D [period, bar] moving-average grids.
  context.py       Dataset: bars plus every derived condition, computed once per
                   series. Strategy-agnostic by rule — the review layer needs the
                   same conditions with no strategy at all.
  trades.py        The trade-log schema and validate(). The contract between the
                   simulator and the manual-trade importer; imports neither.
  sim/
    types.py       DeadCatParams.
    deadcat.py     @njit simulation — the only path-dependent code.
    runner.py      Signal assembly and the call into the jitted loop.
    explain.py     Per-trade audit trail for hand-verification.
  sweep.py         Grid, combo-major sweep, ranking; n_jobs spreads chunks over
                   processes sharing one memmapped copy of the dataset.
  stats.py         Per-trade summary statistics.
  results.py       DuckDB persistence.
```

**Why it's fast.** Everything expensive is hoisted out of the sweep loop into `context.prepare`: candlestick geometry, session VWAP, and a `[n_periods, n_bars]` boolean matrix per moving-average gate covering every period in the grid. A combination then costs a boolean AND plus one simulation pass.

| operation                                                        | cost          |
| ---------------------------------------------------------------- | ------------- |
| ingest 33 contracts / 4.09M bars, forced reparse                 | 26.5 s        |
| ingest, nothing changed (rebuilds the archive, reparses nothing) | 10.4 s        |
| prepare (1.65M bars)                                             | 0.71 s        |
| one combination                                                  | 30 ms         |
| 1,536-combination sweep, serial                                  | 45.4 s        |
| 1,536-combination sweep, `n_jobs=8`                              | 10.4 s (4.4×) |

**Parallelism tops out near 5×, and that is the hardware.** Per-core throughput drops 1.5× once all 8 physical cores are busy — 30.8 ms/combination alone against 46.1 ms with eight running — so ~5.3× is the ceiling and the harness gets 4.4× of it. `n_jobs=16` is SMT: it adds 10% for twice the memory. Worker startup is ~1.5 s, so serial is the right default below a few hundred combinations.

The dataset is shared rather than copied. `Dataset.slim()` drops the 121 MB bar frame to a 13 MB index-only view, and joblib memmaps the arrays — verified by probing a live worker, where `close` and both moving-average grids arrive as `numpy.memmap`.

**Where a combination's 30 ms actually goes**, which is not where M8 assumed: `stats.summarise` 51%, `trades_to_frame` 20%, the `@njit` simulation 23%, signal ANDs 2%. Bar-major restructuring targets that 23%; the 71% of pandas overhead — building and aggregating a DataFrame per combination, in a sweep that then discards the trade log — is the bigger prize and should come first.

Two memory notes: moving-average grids keep only the boolean gate by default (`keep_values=True` for the raw values, needed solely by an MA trailing stop) — 66 MB versus 595 MB for 40 periods. And `Grid` refuses an axis whose filter is off in every combination, which otherwise multiplies runtime for byte-identical rows.

## Current finding

**Every registered archetype has been swept across every axis it owns** — five bar sizes, both roots, twenty market-context slices, every moving-average period and kind — at $1.50 round trip on MNQ, $4.50 on NQ, and one tick of slippage. The findings, the method and the caveats are [docs/roadmap.md](docs/roadmap.md) §M27; re-derive any figure with `tools/campaign_report.py` over `results/campaign/`.

In plain terms: trying every combination and keeping the best one finds something that worked by luck, so the campaign ran three further checks — would you have picked it in advance, does the entry beat a coin flip that trades the same number of times, and is the profit bigger than the worst losing streak it took to earn.

|                              | result                                                                |
| ---------------------------- | --------------------------------------------------------------------- |
| survives held-out selection  | InsideBar, EmaCrossover, and InsideBarTrailing marginally             |
| beats a matched random entry | **InsideBar only**, positive on both roots and significant on neither |
| clears its own drawdown      | one cell, and only just                                               |
| profitable at 1-minute bars  | no archetype's median configuration, on either root                   |

**InsideBar is the one worth more work**, and what stops it is its bracket rather than its entry: a stop of 5–20× ATR against a hardcoded 1× ATR target gives an 87% win rate with an average loss five and a half times the average win, so the profit factor is real and the drawdown eats it. The target has no multiplier to sweep, which is [#197].

**The other five are parked, not abandoned.** The campaign is evidence that their logic does not work *as currently written, over the ranges swept, on the data held today*. It is not evidence that no version of them can work, and all six stay registered and swept — a new condition, a different bracket, a wider range or more data would each be a reason to re-run one. See [docs/roadmap.md](docs/roadmap.md) § "Parked is not abandoned" for the rule that applies when picking one back up.

**Bar size is the largest lever there is.** It explains an order of magnitude more profit-factor variance than any moving-average period or kind, on every archetype. Tune the bar size and the exit geometry; do not tune periods.

**DeadCatBounce specifically** stays the reconciled test fixture. It is unprofitable across every combination tested, stratifying by regime or session phase does not rescue it ([docs/roadmap.md](docs/roadmap.md) § "Stored sweeps — dropped and re-run, stratified"), and its entry rule is still measurably better than random (§M7a) — which is "the loss is in costs, hold time or bracket geometry", not "the entry rule is worthless".

**Instrument scaling is exact.** Running the same NQ bars through both instrument specs gives byte-identical trade geometry — entry and exit bars, prices, stops, targets, `r_multiple`, `risk_points` — and gross P&L of exactly ×10 on *every individual leg* (min ratio = max ratio = 10.0000000000), while per-contract commission correctly does not scale. That is the check that would catch a dollar figure hardcoded to one instrument.

## Known limitations

- **Thin sessions are visible rather than papered over.** NT8's data holds only the Sunday 18:00–19:00 ET hour for one trading day before most rolls, and a correct roll date makes the front contract supply that day. 18 such sessions in NQ (1,779 bars) and a comparable set in MNQ. The gaps are real and were previously hidden behind the wrong contract, not absent — filling them from the neighbour would splice two different prices into one session.

- **`r_multiple` uses planned risk** (`stop − trigger`), which is how the NinjaScript places its targets. Consequence: target exits land just under their nominal multiples, and stop exits can print below −1R when slippage or a gap made the risk actually taken exceed the planned risk.

- **MAE/MFE differ from NT8's definition** — mine measure to the exit bar's extreme, NT8's cap at the exit. Reporting only; no effect on P&L.

[#197]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/197
