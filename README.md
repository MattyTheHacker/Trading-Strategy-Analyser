# nqbt

**Fast parameter search for Nasdaq futures strategies, built to disprove its own winners.**

`nqbt` sweeps hundreds of thousands of strategy configurations across years of NQ/MNQ minute bars in minutes, then spends most of its effort asking whether the survivors were luck. It is **Tier 1** — a fast filter that produces a shortlist. NinjaTrader 8's Strategy Analyzer is **Tier 2** and stays the ground truth: every candidate that survives here is re-validated there before it is trusted.

That split produces the rule everything else follows from:

> **Match NT8's default fidelity exactly — do not exceed it.** Bar-close OHLC fills, no intrabar tick precision. Being *more* precise than NT8 is as much a bug as being less precise, because the two tiers then disagree in ways that cannot be attributed to anything. Tick data sits in `data/tick/` and is deliberately not wired into the simulation.

Four of the seven strategies here are ports of real NinjaScript, diffed leg for leg against Strategy Analyzer trade exports. Every fill rule the simulation implements, and the evidence that established it, is in [docs/nt8-fidelity.md](docs/nt8-fidelity.md).

## What you get

- **A sweep that finishes.** Indicators, session VWAP, moving-average grids and every market label are computed once per dataset and shared, so one parameter combination costs a boolean AND plus a single `@njit` pass. Parallel workers memmap that dataset rather than copying it.
- **Seven strategy archetypes behind one registry**, so "which strategy is worth improving" is a query rather than seven incomparable runs.
- **Four gates a sweep table cannot pass on its own** — a screen, a held-out selection, a matched random entry and a drawdown check — plus walk-forward, Monte Carlo and per-contract dispersion.
- **The market labelled independently of any strategy**: regime, relative volume, range compression, trend, session phase, higher-timeframe trend and session-anchored ranges. Each is a sweepable filter *and* a lens a review can use with no strategy at all.
- **Real fills reviewed by the same code as simulated ones.** An NT8 executions export becomes the same trade-log schema the simulator writes, so a statistic means the same thing over both.
- **Every sweep in one DuckDB**, so shortlisting is a SQL question rather than a directory of files to glob.

## Requirements

- **Python 3.14.** Every dependency has a cp314 wheel; no downgrade needed.
- **NinjaTrader 8.** It is both the only data source and the Tier 2 ground truth. **No market data ships with this repository** — everything under `data/` and `cache/` is gitignored and built from your own exports.
- **Disk.** Minute exports run to a few hundred MB per root, and the derived Parquet cache is smaller again. Tick exports are an order of magnitude larger and nothing in the simulation reads them.

## Install

```bash
git clone --recurse-submodules git@github.com:MattyTheHacker/Trading-Strategy-Analyser.git
cd Trading-Strategy-Analyser
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

Run the tools as `./.venv/Scripts/python.exe -m ...`. Of the two submodules, [ninjatrader-scripts](ninjatrader-scripts) holds the NinjaScript the ports are checked against; `Trading-Docs` is private.

## Get some data

1. In NinjaTrader, **Tools → Historical Data → Export**, one contract at a time, into `data/minute/`. The format is semicolon-delimited, end-of-bar, UTC: `yyyyMMdd HHmmss;open;high;low;close;volume`.
2. Optionally run [NqbtHistoricalExporter.cs](ninjatrader-scripts/AddOns/NqbtHistoricalExporter.cs) first, exporting into `data/addon/`. It reaches months further back **and** warms NinjaTrader's own database, so a manual re-export afterwards returns the full contract life instead of the last ~95 days. The order matters — see [Data layout and two traps](#data-layout-and-two-traps).

## The pipeline

Four commands, and the CLI stops there by design.

```bash
nqbt ingest                    # merge every export source into data/archive, then cache it as Parquet
nqbt contracts                 # what is cached, and how much of it
nqbt splice --root MNQ         # detect the rolls, build the continuous series
nqbt splice --root MNQ --back-adjust --diagnostics
nqbt run --root MNQ --commission 1.50 --slippage 1 --explain 10
```

`nqbt run --explain N` writes the NT8 audit trail: the signal bar's geometry, each gate's operands and verdict, the trigger and stop arithmetic, how the entry filled, where every leg left, and a bar-by-bar ratchet history. It is what makes a disagreement with a real NT8 trade list attributable to a rule rather than to "the numbers differ".

Sweeps, reviews and walk-forward are driven from Python rather than the CLI, deliberately: a `Grid` takes arbitrary lists per axis with toggle interactions, and flattening that into argparse flags would be a lossier way of saying the same thing.

## Your first sweep

```python
from nqbt import archetypes, costs, results, splice, sweep

insidebar = archetypes.get("InsideBar")
bars = splice.load_continuous("MNQ")

grid = sweep.Grid.of(
    costs.LIVE.apply(insidebar.params_cls()),   # the archetype is inferred from the params
    atr_multiplier=[5.0, 10.0, 15.0, 20.0],     # stop distance
    atr_length=[3, 7, 14],
    tp_multiplier=[1.0, 2.0, 3.0],              # target distance
)

table, _ = sweep.sweep(bars, grid, n_jobs=8)    # n_jobs=1, the default, stays in-process
results.save_sweep(
    table, root="MNQ", instrument="MNQ", bars=bars,
    axes=grid.axes, strategy=grid.archetype.name,
)
print(sweep.rank(table, "profit_factor", top=10, min_trades=200))
```

**`costs.LIVE` is not decoration.** Every parameter class defaults `commission_per_contract` and `slippage_ticks` to zero, which is correct for reconciling against NT8 and wrong for every ranking — an uncosted sweep silently ranks free money first. The real figures are **$1.50 round trip on MNQ and $4.50 on NQ**, both with a tick of slippage; one figure applied to both flatters NQ, whose point value is ten times larger where its commission is not.

`sweep.sweep` returns one summary row per combination. `sweep.sweep_axes` runs grids across resolution, root and contract at once, and `Grid.of_combinations` takes a shortlist outright when no product describes it.

That example is the mechanics, not a recommendation: it runs on 1-minute bars, where no archetype's median configuration makes money on either root. Resample first — `sweep.sweep_axes(..., resolutions=(5, 15))` — and read the top of a sweep table as a candidate rather than a result. The next section is why.

## Proving a sweep winner wrong

Trying a few hundred thousand things and keeping the best one is how you find something that worked *by luck* — the more you try, the luckier the best one looks. Everything below exists to take that back, and each is one module:

| the question                                 | what it does                                                                  | module               |
| -------------------------------------------- | ----------------------------------------------------------------------------- | -------------------- |
| Would you have picked it in advance?         | choose on the first 60% of the history, measure on the last 40%               | `guard.holdout_test` |
| Is it the entry, or just the bracket?        | re-run against a random entry matched on count, direction and time of session | `randomentry`        |
| Does it survive being chosen repeatedly?     | rolling in-sample selection, out-of-sample measurement, many folds            | `walkforward`        |
| Was the equity path luckier than the trades? | permute the trade order; bootstrap the values                                 | `montecarlo`         |
| Does it hold across contracts?               | per-contract spread, reported as dispersion rather than as a winner           | `dispersion`         |
| Is this separation just noise?               | family-wise shuffled-label null, and a minimum sample per stratum             | `guard.screen`       |

Two of them refuse rather than answer, which is the point. A **dense entry signal has no matched random-entry null**: when the rule fires on nearly every bar there is nothing left for the draw to relocate, so it hands back the signal it was matched to. `randomentry` refuses below one spare bar per signal, and `tools/campaign_null.py` exits `2` — a gate that could not run is never read as a gate that passed. `docs/roadmap.md` §M28.1 is the case that established it, and the level-based null that answers it.

The whole registry is driven through these by the campaign harness in [tools/](tools/), each script a standalone CLI:

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --n-jobs 8 --split         # every archetype, every axis, split windows
./.venv/Scripts/python.exe tools/campaign_report.py                           # distributions, not winners
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar   # re-run, keeping the trade logs
./.venv/Scripts/python.exe tools/campaign_null.py --strategy InsideBar        # against the matched random entry
```

`campaign_holdout`, `campaign_walkforward`, `campaign_montecarlo`, `campaign_contracts`, `campaign_review`, `campaign_annotate`, `campaign_paired` and `campaign_ambiguity` complete the set. Each writes to `results/campaign/<Strategy>.duckdb`, and every figure any of them prints is re-derivable from there.

## The archetypes

An **archetype** is a distinct entry/exit shape, not a parameter set — different parameter values reuse the same compiled function. Register a new one in [nqbt/archetypes.py](nqbt/archetypes.py) rather than forking the sweep.

| archetype           | shape                                                          | Tier 2      |
| ------------------- | -------------------------------------------------------------- | ----------- |
| `DeadCatBounce`     | short an inverted hammer into an established downtrend         | reconciled  |
| `PullBackAndGo`     | the exact long mirror, sharing the same jitted loop            | reconciled  |
| `InsideBar`         | break an inside bar out of its mother bar, both sides          | reconciled  |
| `InsideBarTrailing` | InsideBar's entry, split across two exit engines               | reconciled  |
| `EmaCrossover`      | the first original: no NinjaScript, a known-negative control   | tier-1-only |
| `ElasticBand`       | fade an extension, target the middle; the first mean reversion | tier-1-only |
| `OpeningRange`      | rest a stop at the opening range's extreme, one side at a time | tier-1-only |

**Reconciled** means diffed leg for leg against a real Strategy Analyzer export; **tier-1-only** means every rule is written down rather than checked. The status reaches the results table deliberately, so an original archetype's result is never read as a ported one's.

Every archetype ANDs the same six market-context filters after its own conditions ([nqbt/sim/filters.py](nqbt/sim/filters.py)), and every exit goes through one shared bracket engine ([nqbt/sim/bracket.py](nqbt/sim/bracket.py)) — one stop, up to four R-multiple targets, an ambiguity policy for the bar that holds both, and the forced flat at the session close.

## Reviewing real trades

The other half of the tool takes an NT8 **executions** export (Control Center → Executions → CSV), matches the fills FIFO into the same trade-log schema the simulator writes, and asks what was true when each trade was taken:

```python
from nqbt import annotate, context, review, trade_import

imported = trade_import.import_executions("executions.csv", timezone="Europe/London")
bars = annotate.contract_bars(imported.frame)   # per-contract bars, never back-adjusted
data = context.prepare(
    bars,
    context.ContextSpec(needs_time_of_day=True),
    price_basis=context.PriceBasis.RAW,
)
annotation = annotate.annotate_trades(imported.frame, data)
print(review.review(imported.frame, annotation, unpopulated=imported.unpopulated))
```

Time of day is the headline, and everything a review prints is **hypothesis-generating, not confirmatory** — the report says so itself. A few hundred trades against a few dozen conditions is a multiple-comparisons machine, so what a review raises goes to `guard` and then to a sweep. Free-text notes on a trade are stored and displayed by [nqbt/notes.py](nqbt/notes.py) and are structurally barred from reaching a `groupby`: a note is written knowing the outcome, so stratifying by one would rediscover the outcome.

## Drawing one trade

`nqbt.chart` draws a single trade on the bars it happened on and writes a self-contained SVG — the candles either side, the bracket each leg carried, where every leg left and why, and how far price ran each way while it was open. Any archetype, and an imported trade log as readily as a simulated one:

```python
from nqbt import archetypes, chart, splice, sweep
from nqbt.context import PriceBasis
from nqbt.instruments import MNQ

bars = splice.load_continuous("MNQ")
grid = sweep.Grid(archetype=archetypes.get("InsideBar"))
data = sweep.prepare_for(bars, grid, price_basis=PriceBasis.RAW)
_, log = sweep.run_combination(data, grid.base, MNQ, grid.archetype)

worst = log.groupby("trade_id")["net_pnl"].sum().nsmallest(5).index
for drawn in chart.charts(log, data, worst, bars_either_side=25):
    drawn.save(f"results/charts/trade-{drawn.trade_id}.svg")
```

`sweep.prepare_for` is what builds the `Dataset`, because `Grid.required_context` is the only thing that reliably knows which series an archetype reads — a hand-rolled `ContextSpec` gets a `ContextError` naming the one it missed.

Four things worth knowing before reading a chart:

- **A chart is a debugging instrument, not a selection one.** It can settle whether the simulator did what the rule says; it cannot settle whether the rule is any good, and a dozen charts read for that are exactly the multiple-comparisons machine [nqbt/guard.py](nqbt/guard.py) exists for. Every chart says so along the bottom.
- **Draw an imported log against per-contract bars**, via `annotate.contract_bars` — never the back-adjusted series, which shifts every historical price while the lookup still succeeds. A fill landing far off its candle is the chart showing you exactly that, and the series it drew is named in the corner.
- **Nothing is drawn between the two fills.** The shaded band is the bars the position was open for; a line from entry to exit would depict an intrabar path these bars do not record.
- **The window is bars, not minutes**, so a trade held for hundreds of bars makes a very wide document. `bars_either_side` controls the context, not the trade.

## Repository layout

```text
nqbt/
  pipeline     archive · ingest · splice · resample · sessions · instruments · paths
  context      context · conditions · indicators · bands · sessionrange
               regime · volume · compression · trend · timeofday · higher_timeframe
  sim/         bracket · filters · runner · explain · types
               deadcat · pullback · insidebar · insidebartrailing · crossover · elasticband · openingrange
  search       archetypes · sweep · results · costs · disambiguate
  validation   guard · randomentry · walkforward · montecarlo · dispersion
  review       trade_import · annotate · review · notes · chart · stats · trades
tools/         the campaign harness, the NT8 reconciliation scripts, the commit linter
tests/         one module per source module, plus the trade-log regression gate
docs/          nt8-fidelity.md · roadmap.md · backtest_tool_spec.md
```

Three boundaries hold the design up. **`context.py` is strategy-agnostic** — it has to be, because the review layer needs the same conditions with no strategy at all. **`trades.py` is the contract between the simulator and the importer**, and imports neither. **`instruments.py` is the only place a dollar figure is defined**: NQ and MNQ share a tick size but their tick values differ tenfold, verified by running the same bars through both specs and getting identical trade geometry with gross P&L exactly ×10 on every leg and per-contract commission unscaled.

## Performance

Everything expensive is hoisted out of the sweep loop into `context.prepare`, which is what makes a six-figure sweep a coffee break rather than an afternoon: §M27's 760,960 combinations took about 98 minutes and §M28.1's 172,800 took 45, both across two roots at real costs.

Three things are worth knowing before tuning it:

- **Parallelism tops out near 5× on eight physical cores**, and that is the hardware rather than the harness — per-core throughput drops about 1.5× once every core is busy. `n_jobs=16` is SMT: roughly 10% more for twice the memory. Worker startup is ~1.5 s, so **serial is the right default below a few hundred combinations.**
- **The dataset is shared, not copied.** `Dataset.slim()` drops the bar frame to an index-only view and joblib memmaps the arrays into each worker.
- **Moving-average grids keep only the boolean gate by default** — an order of magnitude smaller than keeping the values, which only an MA trailing stop needs. And `Grid` refuses an axis whose filter is off in every combination, which would otherwise multiply runtime for byte-identical rows.

Re-profile before believing any figure here. `docs/roadmap.md` §M8 carries the current per-combination breakdown and the reason bar-major restructuring is measured and *not* scheduled.

## Data layout and two traps

```text
data/minute/  MNQ 03-24.Last.txt    manual export     yyyyMMdd HHmmss;o;h;l;c;v (UTC)
data/addon/   MNQ 03-24.Last.txt    AddOn snapshot    same format
data/archive/ MNQ 03-24.Last.txt    the durable union -- the only thing ingest reads
data/tick/    MNQ 09-26.Last.txt    yyyyMMdd HHmmss fffffff;last;bid;ask;volume
cache/bars/MNQ/MNQ_2024H.parquet    cleaned, session-tagged, one file per contract
cache/continuous/MNQ_raw.parquet    the spliced series (and MNQ_backadj.parquet)
results/sweeps.duckdb               every sweep, queryable together
```

Raw exports are split by resolution because tick and minute exports share the same `.Last.txt` naming and must never be globbed together.

**Exports are moving windows, not snapshots.** NinjaTrader serves each contract for a limited period and drops the tail once it expires, so a folder of exports quietly loses history. `data/archive/` is the durable union that ingestion actually reads, and it only ever grows.

**The two sources compound, and the order matters.** A manual export alone returns the last ~95 days through expiry; the AddOn reaches three to six months further back but stops at the turn of the expiry month. Because the AddOn's `BarsRequest` calls warm NinjaTrader's own local database, running the AddOn **and then** re-exporting manually returns the full contract life from one source — after which every roll in both roots detects a genuine volume crossover, where before every one of them fell back to the coverage boundary. Ingest also hashes the entire consumed byte range, because checking only the file head cannot see a rewritten tail — which had frozen stale bars in the cache and silently dropped real ones at the seam. Both are recorded in [docs/nt8-fidelity.md](docs/nt8-fidelity.md), "Contract data".

## Where the live numbers are

**Status lives in the issue tracker**, which is the only copy that cannot go stale.

```bash
gh issue list --state open                   # everything outstanding
gh issue list --state open --label next-up   # what is at the front
gh issue view <n>                            # blocked-by, blocking, sub-issues
```

| number                         | where it is produced                                |
| ------------------------------ | --------------------------------------------------- |
| agreement rates against NT8    | [docs/nt8-fidelity.md](docs/nt8-fidelity.md)        |
| test count and coverage        | `./.venv/Scripts/python.exe -m pytest`              |
| bars, contracts and roll dates | `nqbt contracts`, `nqbt splice --diagnostics`       |
| any campaign figure            | `tools/campaign_report.py` over `results/campaign/` |

## What the campaign found

Every registered archetype has been swept across every axis it owns, on both roots, at real costs. The method, the findings and the caveats that travel with them are `docs/roadmap.md` §M27 and §M28.1 — quote those rather than this summary, which is deliberately short:

- **Two archetypes have ever beaten a matched random entry: `InsideBar` and `OpeningRange`.** OpeningRange is the only one through the first three gates, and what stops it at the fourth is sample size rather than the idea.
- **What holds `InsideBar` back is its bracket, not its entry** — specifically the target distance. It is the largest axis on the held-out window and nearly inert on the selection window, so a protocol that chooses before it measures cannot point at the geometry that works. The bracket is diagnosed and still not fixed (§M27.3).
- **Bar size is the largest lever and the moving averages are nearly inert.** Resolution explains an order of magnitude more profit-factor variance than any period or kind, on every archetype. Tune the bar size and the exit geometry, not periods.
- **A failed campaign parks a configuration space; it does not retire an archetype.** All seven stay registered, swept and reconciled. Before re-running a parked one, say what has changed — a new condition, bracket, range or data — because a re-run with none of those is the same measurement with a new seed. `docs/roadmap.md` § "Parked is not abandoned".
- **`DeadCatBounce` is unprofitable across every combination tested**, and stratifying by regime or session phase does not rescue it. It stays as the reconciled test fixture that proves the system works, and its entry rule is still measurably better than random — which is "the loss is in costs, hold time or bracket geometry", not "the entry rule is worthless".

## Known limitations

- **Every position is flat before the session close.** A prop-firm account rule, matching NT8's `IsExitOnSessionCloseStrategy` — not a parameter, and it bounds maximum hold time by the session, so an archetype needing an overnight hold is unbuildable here. It is also the *only* prop-firm rule modelled; both prop and non-prop accounts must work.
- **Entry orders live one bar.** NT8's managed approach cancels them, which bounds what an archetype can express. It is an unset parameter rather than a platform limit — `docs/roadmap.md` § "Order lifetime in NT8" — but the simulation keeps the one-bar lifetime because that is what the C# does.
- **Thin sessions are visible rather than papered over.** NT8's data holds only the Sunday 18:00–19:00 ET hour for one trading day before most rolls. Those gaps are real and were previously hidden behind the wrong contract; filling them from the neighbour would splice two different prices into one session.
- **Roll dates are data-derived and deliberately not reconciled against NT8**, which merges on dates configured in its Database window — a setting, not a measurement. So a spliced result may not reproduce bar-for-bar around a roll.
- **`r_multiple` uses planned risk** (`stop − trigger`), which is how the NinjaScript places its targets. Target exits therefore land just under their nominal multiples, and a stop exit can print below −1R when slippage or a gap made the risk actually taken exceed the planned risk.
- **MAE/MFE differ from NT8's definition** — these measure to the exit bar's extreme where NT8's cap at the exit. Reporting only; no effect on P&L.
- **TA-Lib does not match NT8.** Use `indicators.nt8_*` for anything NT8 will be compared against: EMA, ATR, StdDev, Bollinger and Keltner all diverge, and Keltner is not the usual definition at all.

## Documentation

| file                                         | what it holds                                                                           |
| -------------------------------------------- | --------------------------------------------------------------------------------------- |
| [docs/nt8-fidelity.md](docs/nt8-fidelity.md) | every NT8 rule the simulation reproduces, and the evidence that established it          |
| [docs/roadmap.md](docs/roadmap.md)           | the reasoning behind the order of work, the milestone findings, and the decision record |
| [CONTRIBUTING.md](CONTRIBUTING.md)           | the working agreement: style, tests, coverage, commits, PRs, and the trade-log gate     |
| [CLAUDE.md](CLAUDE.md)                       | the same ground rules, addressed to an AI assistant working in this repository          |

Reasoning belongs in `docs/`, not in the source: docstrings say *what* a thing is and stay short, and every pointer must name a section that exists.

## License

[GPL-3.0](LICENSE).
