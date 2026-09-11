# nqbt

**A backtester for Nasdaq futures strategies that spends most of its effort trying to prove its own results wrong.**

`nqbt` takes a trading strategy, tries every combination of its settings against several years of price history, and ranks the results. A search that would take days in a typical backtester takes minutes here.

Ranking is the easy part, and on its own it lies to you. Try enough combinations and one of them will look brilliant purely by chance. Most of this project is the machinery for telling luck and skill apart.

A few words used throughout, defined once:

| word          | means                                                                                                      |
| ------------- | ---------------------------------------------------------------------------------------------------------- |
| **NQ / MNQ**  | two Nasdaq-100 futures contracts. Same price, but MNQ is a tenth the size, so a tenth the money per point. |
| **bar**       | one candle. A 5-minute bar holds the open, high, low and close of five minutes of trading.                 |
| **sweep**     | running one strategy many times, once per combination of its settings, and collecting the results.         |
| **archetype** | one strategy's shape, such as "buy a breakout". Its settings are what a sweep varies.                      |
| **leg**       | one exit. A trade that sells half the position at one price and half at another has two legs.              |
| **fill**      | an order actually becoming a trade, at a particular price.                                                 |

## How this fits with NinjaTrader

These strategies are meant to run in NinjaTrader 8, and NinjaTrader's own Strategy Analyzer is the thing to be believed. `nqbt` is the fast first pass that narrows thousands of candidates down to a handful. NinjaTrader is the slow second pass that confirms them.

The two passes have names, used everywhere in this repository:

- **Tier 1** is this project. Fast, deliberately approximate, and never the final word.
- **Tier 2** is NinjaTrader 8's Strategy Analyzer. Slow, authoritative, and what a candidate must survive before anyone trades it.

That split produces the one rule everything else follows:

> **Match NinjaTrader's default accuracy exactly. Do not exceed it.**

In plain terms: NinjaTrader decides trades using only each bar's open, high, low and close, so `nqbt` does the same. Tick-by-tick data sits in `data/tick/`, would be more realistic, and is deliberately left unused. If `nqbt` were more accurate than NinjaTrader, the two would disagree, and nobody could tell whether the difference was a real bug or just the extra precision. Being more accurate is as much a bug here as being less accurate.

Four of the seven strategies are translations of real NinjaScript, checked exit by exit against actual Strategy Analyzer exports. Every trading rule the simulation reproduces, and the evidence behind it, is in [docs/nt8-fidelity.md](docs/nt8-fidelity.md).

## What you get

- **A sweep that finishes quickly.** All the expensive maths is done once and then shared by every combination, so trying one more set of settings is nearly free. Searches of hundreds of thousands of combinations run in about an hour and a half rather than over a week.
- **Seven strategies behind one registry.** They all present the same interface, so "which of these is worth more work?" is a single query instead of seven separate runs that cannot be compared.
- **Four tests a ranking table cannot pass by itself**, plus three more. They ask whether a good result would have been *pickable in advance*, whether the entry rule beats a coin flip, and whether the profit is bigger than the losing streak it took to earn.
- **The market described separately from any strategy.** Is it trending or chopping? Is volume unusual for this time of day? Is the range unusually tight? These labels are worked out independently, which means they serve both as strategy filters and as a way of reviewing trades that no strategy produced.
- **Real trades analysed by the same code as simulated ones.** Your actual fills, exported from NinjaTrader, become the identical format the simulator writes, so any statistic means the same thing over both.
- **Every sweep in one database.** Results accumulate in DuckDB, so comparing today's run against one from three weeks ago is a SQL query.

## Requirements

- **Python 3.14.** Every dependency has a matching wheel, so nothing needs downgrading.
- **NinjaTrader 8.** It is both the only source of price data and the Tier 2 authority. **No market data ships with this repository.** Everything under `data/` and `cache/` is gitignored, and you build it from your own exports.
- **Disk space.** Minute-bar exports run to a few hundred MB per instrument, and the processed cache is smaller again. Tick exports are roughly forty times larger, and nothing in the simulation reads them.

## Install

```bash
git clone --recurse-submodules git@github.com:MattyTheHacker/Trading-Strategy-Analyser.git
cd Trading-Strategy-Analyser
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

Run everything through the virtual environment, as `./.venv/Scripts/python.exe -m ...`.

There are two submodules. [ninjatrader-scripts](ninjatrader-scripts) holds the NinjaScript source the Python translations are checked against, and `Trading-Docs` is private.

## Get some data

1. In NinjaTrader, go to **Tools → Historical Data → Export** and export one contract at a time into `data/minute/`. Each line is one minute, semicolon-separated, timestamped at the *end* of the bar in UTC: `yyyyMMdd HHmmss;open;high;low;close;volume`.
2. Optionally, run [NqbtHistoricalExporter.cs](ninjatrader-scripts/AddOns/NqbtHistoricalExporter.cs) first and export into `data/addon/`.

Step 2 is worth doing, and the order matters. A manual export alone gives you roughly the last 95 days of each contract. The add-on reaches several months further back, and it also fills NinjaTrader's own local database as a side effect. Export manually *afterwards* and NinjaTrader hands over the whole life of the contract. Do it the other way round and you get the short version. [Data layout and two traps](#data-layout-and-two-traps) explains why this matters so much.

## The pipeline

Four commands, in order. The command line stops there on purpose.

```bash
nqbt ingest                    # read the exports, clean them up, save them as Parquet
nqbt contracts                 # show what is currently cached
nqbt splice --root MNQ         # join the separate contracts into one continuous price history
nqbt splice --root MNQ --back-adjust --diagnostics
nqbt run --root MNQ --commission 1.50 --slippage 1 --explain 10
```

**Why `splice` exists.** Futures contracts expire every three months, so five years of history is really twenty separate contracts sitting end to end. `splice` works out the day traders moved from one contract to the next and joins them into a single series. `--back-adjust` additionally shifts the older prices so the joins line up smoothly, which matters because each new contract starts at a slightly different price.

**What `--explain` gives you.** It writes a step-by-step record of the first N trades: what the signal bar looked like, what each condition was checking and whether it passed, how the entry and stop prices were worked out, how the order filled, and where each exit landed. If `nqbt` and NinjaTrader ever disagree, this is what turns "the numbers are different" into "this specific rule is wrong".

Sweeps, reviews and the validation tools run from Python instead. That is on purpose: a sweep takes an arbitrary list of values for each setting, and squeezing that through command-line flags would lose most of what it can express.

## Your first sweep

```python
from nqbt import archetypes, costs, results, splice, sweep

insidebar = archetypes.get("InsideBar")
bars = splice.load_continuous("MNQ")

grid = sweep.Grid.of(
    costs.LIVE.apply(insidebar.params_cls()),  # which strategy is inferred from these settings
    atr_multiplier=[5.0, 10.0, 15.0, 20.0],  # how far away the stop loss sits
    atr_length=[3, 7, 14],  # how many bars the volatility measure looks back over
    tp_multiplier=[1.0, 2.0, 3.0],  # how far away the profit target sits
)

table, _ = sweep.sweep(bars, grid, n_jobs=8)  # n_jobs=1, the default, avoids starting workers
results.save_sweep(
    table,
    root="MNQ",
    instrument="MNQ",
    bars=bars,
    axes=grid.axes,
    strategy=grid.archetype.name,
)
print(sweep.rank(table, "profit_factor", top=10, min_trades=200))
```

That runs 36 combinations, being 4 × 3 × 3, and prints the ten with the best profit factor. **Profit factor** is total winnings divided by total losses: above 1.0 makes money, below 1.0 loses it. It says nothing about how bumpy the ride was.

**Always pass `costs.LIVE`.** Every strategy defaults its commission and slippage to zero. That is correct when checking against NinjaTrader and wrong for everything else, because a free sweep quietly ranks strategies that only work when trading costs nothing. Real costs are **$1.50 per round trip on MNQ and $4.50 on NQ**, plus a tick of slippage. Use one figure for both and you flatter NQ, which moves ten times as much money per point while costing only three times as much to trade.

`sweep.sweep` gives one summary row per combination. `sweep.sweep_axes` runs the same thing across several bar sizes, both instruments and individual contracts at once. `Grid.of_combinations` takes an explicit list of settings when you already know which ones you want.

Treat that example as a demonstration of the mechanics, not a suggestion. It runs on 1-minute bars, where none of these strategies makes money. Try larger bars first, with `sweep.sweep_axes(..., resolutions=(5, 15))`, and read the top of any ranking table as a question rather than an answer. The next section is why.

## Proving a sweep winner wrong

Try a few hundred thousand things and keep the best one, and you have almost certainly found something that got lucky. The more you try, the luckier the winner looks. Everything below exists to take that back.

| the question                                  | how it is answered                                                                                                               | module               |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| Would you have picked this in advance?        | choose the best settings using only the first 60% of the history, then measure them on the last 40%, which the choice never saw  | `guard.holdout_test` |
| Is it the entry, or just the exit?            | run the strategy again with its entry replaced by a coin flip that trades equally often, at the same times of day                | `randomentry`        |
| Does it keep working as time moves on?        | repeat the choose-then-measure step across many overlapping windows                                                              | `walkforward`        |
| Was it the trades, or the order they came in? | shuffle the trades into a different order and see whether the losing streak was just bad luck                                    | `montecarlo`         |
| Does it work on more than one contract?       | run it separately on each three-month contract and report the spread rather than the best one                                    | `dispersion`         |
| Is this pattern just noise?                   | shuffle the labels so any apparent pattern is known to be fake, then check how often that alone produces something as impressive | `guard.screen`       |

The second row matters most, and a ranking table never shows it. If a coin flip does as well as the strategy, then the money is coming from where the stop and target were placed, not from the rule deciding when to trade.

Two of these refuse to answer instead of guessing, which is the point. **A strategy that signals on nearly every bar has no coin flip to compare against.** The comparison works by moving the trades onto randomly chosen other bars, so if the strategy already traded almost everywhere, there is nowhere left to move them. It hands back the original trades and reports a perfect match with itself. `randomentry` therefore refuses when there is less than one spare bar per signal, and `tools/campaign_null.py` exits with code `2`, which stops a test that could not run from being recorded as a test that passed. `docs/roadmap.md` §M28.1 is the case where this was found the hard way.

All seven strategies are driven through these checks by the scripts in [tools/](tools/), each a standalone command:

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --n-jobs 8 --split         # sweep everything, split into two windows
./.venv/Scripts/python.exe tools/campaign_report.py                           # summarise the spread, not the winners
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar   # re-run the best few, keeping every trade
./.venv/Scripts/python.exe tools/campaign_null.py --strategy InsideBar        # compare those against the coin flip
```

`campaign_holdout`, `campaign_walkforward`, `campaign_montecarlo`, `campaign_contracts`, `campaign_review`, `campaign_annotate`, `campaign_paired` and `campaign_ambiguity` complete the set. Each writes to `results/campaign/<Strategy>.duckdb`, so any figure they print can be recalculated later from stored data.

## The strategies

An **archetype** is one strategy's shape, not one set of its settings. Changing a number gives you another run of the same archetype; changing the logic gives you a new one. Add new ones to [nqbt/archetypes.py](nqbt/archetypes.py) rather than copying the sweep code.

| archetype           | what it does                                                        | checked against NinjaTrader? |
| ------------------- | ------------------------------------------------------------------- | ---------------------------- |
| `DeadCatBounce`     | sells a failed bounce during a downtrend                            | yes                          |
| `PullBackAndGo`     | the same idea upside down: buys a dip during an uptrend             | yes                          |
| `InsideBar`         | trades a breakout from a quiet bar, whichever way it breaks         | yes                          |
| `InsideBarTrailing` | the same entry, but half the position runs with a trailing stop     | yes                          |
| `EmaCrossover`      | the textbook moving-average cross, kept as a known-bad control      | no                           |
| `ElasticBand`       | fades a move that has stretched too far, expecting a snap back      | no                           |
| `OpeningRange`      | trades a break out of the range set in the first minutes of the day | no                           |

**That last column is load-bearing.** A *yes* means the Python was compared exit by exit against a real Strategy Analyzer export and matched it. A *no* means the rules are written down and believed but never verified, because no NinjaScript version exists yet. The status appears in the results table on purpose, so a verified strategy is never silently compared against an unverified one.

Every archetype writes only the entry half. All the exits go through one shared piece of code, [nqbt/sim/bracket.py](nqbt/sim/bracket.py), which handles the stop loss, up to four profit targets, the awkward case of one bar containing both, and the forced close at the end of the session. They all apply the same six market filters too, in [nqbt/sim/filters.py](nqbt/sim/filters.py), after their own conditions.

## Reviewing real trades

The other half of the tool looks at trades you actually took. Export them from NinjaTrader (**Control Center → Executions**, saved as CSV) and `nqbt` pairs the buys with the sells, converts them into the same format the simulator produces, and reports what the market was doing at the moment you entered each one.

```python
from nqbt import annotate, context, review, trade_import

imported = trade_import.import_executions("executions.csv", timezone="Europe/London")
bars = annotate.contract_bars(imported.frame)
data = context.prepare(
    bars,
    context.ContextSpec(needs_time_of_day=True),
    price_basis=context.PriceBasis.RAW,
)
annotation = annotate.annotate_trades(imported.frame, data)
print(review.review(imported.frame, annotation, unpopulated=imported.unpopulated))
```

Time of day is reported first, because it is usually the biggest single factor.

**Anything a review turns up is a question, not a conclusion**, and the printed report says so itself. A few hundred trades measured against a few dozen conditions will always throw up something that looks like a pattern. Take what a review suggests to `guard`, and then to a sweep, before believing it.

Notes you write on a trade are stored and shown but can never enter a calculation. You write a note knowing how the trade turned out, so losers attract "I was impatient" and winners attract "clean setup". Grouping by those would rediscover the outcome and dress it up as a finding.

## Looking at one trade

`nqbt.chart` draws a single trade on the bars it happened on and writes a standalone SVG: the candles either side of it, the stop and target it was carrying, where each exit landed and why, how far price moved in each direction while the position was open, and the indicators the strategy was reading at the time. It works for any strategy, and for real trades as readily as simulated ones.

```python
from nqbt import archetypes, chart, splice, sweep
from nqbt.context import PriceBasis
from nqbt.instruments import MNQ

bars = splice.load_continuous("MNQ")
grid = sweep.Grid(archetype=archetypes.get("InsideBar"))
data = sweep.prepare_for(bars, grid, price_basis=PriceBasis.RAW)
_, log = sweep.run_combination(data, grid.base, MNQ, grid.archetype)

worst = log.groupby("trade_id")["net_pnl"].sum().nsmallest(5).index
indicators = chart.overlays_for(data)
for drawn in chart.charts(log, data, worst, bars_either_side=25, overlays=indicators):
    drawn.save(f"results/charts/trade-{drawn.trade_id}.svg")
```

Use `sweep.prepare_for` to build the dataset. It reads the strategy's own declaration of which price series it needs, which is the only reliable way to get that right. Assemble one by hand and you get an error naming whatever you left out.

That declaration is also what `chart.overlays_for` draws: every moving average, band, VWAP, higher-timeframe average and session range the dataset holds, and nothing else. Name them one at a time — `chart.moving_average(data, "ema", 21)`, `chart.opening_range(data, key)` — when the whole set is too much to read. Moving averages need `needs_ma_values` on the spec, since a sweep otherwise keeps only the boolean gate.

Five things worth knowing before you read a chart:

- **A chart can tell you whether the simulator behaved correctly. It cannot tell you whether the strategy is any good.** Reading a dozen charts and forming an opinion is exactly the trap [nqbt/guard.py](nqbt/guard.py) exists to prevent, because you will find the pattern you went looking for. Every chart carries that warning along the bottom.
- **Draw real trades against single-contract bars**, using `annotate.contract_bars`. The back-adjusted continuous series has had all its historical prices shifted, so the lookup still succeeds while every price is quietly wrong. A fill appearing nowhere near its candle is the chart showing you this has happened. The series being drawn is named in the corner.
- **Nothing is drawn between entry and exit.** The shaded band marks the bars the position was open for. A line from one to the other would imply a path through those bars that the data does not record.
- **The window is measured in bars, not minutes**, so a trade held for hundreds of bars produces a very wide image. `bars_either_side` controls how much context is drawn around the trade, not the trade itself.
- **The trade's own geometry is dashed and the market's context is solid.** An overlay is clipped to the panel rather than fitted into it, so a long average sitting far from the window cannot squash the trade you were looking at. Only price-panel series can be drawn; an ATR or a relative volume would need a second panel and there isn't one.

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
tools/         the campaign scripts, the NinjaTrader reconciliation scripts, the commit linter
tests/         one file per source module, plus a regression gate on the trade log
docs/          nt8-fidelity.md · roadmap.md · backtest_tool_spec.md
```

Three rules keep this from tangling:

- **`context.py` knows nothing about strategies.** It has to stay that way, because reviewing your real trades needs all the same market labels and involves no strategy at all.
- **`trades.py` defines the trade format and imports neither side.** It is the shared contract between the simulator and the importer, which is what lets one statistic mean the same thing for both.
- **`instruments.py` is the only place a dollar amount is defined.** NQ and MNQ move in the same increments but are worth ten times different amounts, so a figure hardcoded anywhere else would be right for one and silently wrong for the other. This is verified by running identical bars through both and confirming the trades come out the same while the money comes out exactly ten times apart.

## Performance

All the expensive work happens once, before the sweep starts, so no combination repeats it. That is what makes a large search practical: 760,960 combinations took about 98 minutes, and a later run of 172,800 took 45, both across two instruments at realistic costs.

Three things to know before trying to speed it up:

- **More cores stop helping at around 5×.** The limit is the hardware, not the code. Once every core is busy each one runs about 1.5 times slower, so eight cores buy roughly five. Setting `n_jobs=16` uses virtual cores and gains about 10% for twice the memory. Starting workers costs a second and a half, so **leave it single-process below a few hundred combinations.**
- **Workers share one copy of the data.** The dataset is mapped into memory, so eight workers do not need eight times the RAM.
- **Only the yes/no answers are kept, not the numbers behind them.** For the moving averages that is roughly ten times smaller, and the raw values are needed by just one kind of trailing stop. The sweep also refuses a setting that cannot change any result, which would otherwise multiply the runtime for identical rows.

Measure before believing any of this. `docs/roadmap.md` §M8 has the current breakdown of where the time goes, and explains why one obvious optimisation was measured and deliberately not done.

## Data layout and two traps

```text
data/minute/  MNQ 03-24.Last.txt    manual export     yyyyMMdd HHmmss;o;h;l;c;v (UTC)
data/addon/   MNQ 03-24.Last.txt    add-on export     same format
data/archive/ MNQ 03-24.Last.txt    the permanent union of the two, and the only thing ingest reads
data/tick/    MNQ 09-26.Last.txt    yyyyMMdd HHmmss fffffff;last;bid;ask;volume
cache/bars/MNQ/MNQ_2024H.parquet    cleaned and session-tagged, one file per contract
cache/continuous/MNQ_raw.parquet    the joined-up series (and MNQ_backadj.parquet)
results/sweeps.duckdb               every sweep, in one queryable place
```

Minute and tick exports live in separate folders because they share the same `.Last.txt` naming while being completely different formats. **Never read across both at once.**

**Trap one: exports are a moving window, not a snapshot.** NinjaTrader serves each contract for a limited period and drops the oldest data as it ages. Re-export the same contract six months later and you get *less* history, not more. That is why `data/archive/` exists. It accumulates everything ever exported, only ever grows, and is the only folder ingestion actually reads.

**Trap two: the two export methods add to each other, and the order matters.** A manual export gives about 95 days. The add-on reaches three to six months further back but stops at the start of the expiry month. Because the add-on's requests also populate NinjaTrader's own database, running the add-on and *then* re-exporting manually returns the entire life of the contract from a single source. Doing that turned every contract handover into one decided by a real change in trading volume, where previously every single one had to fall back to guessing from wherever the data happened to stop.

One more thing worth knowing, since it was live for a while. Ingestion hashes the whole range of bytes it reads, not just the start of each file. Checking only the beginning cannot detect a file whose *end* was rewritten, which had frozen stale bars in the cache and quietly dropped real ones at the join. Both traps are recorded in [docs/nt8-fidelity.md](docs/nt8-fidelity.md), "Contract data".

## Where the live numbers are

**Current status lives in the issue tracker**, which is the only copy that cannot go stale.

```bash
gh issue list --state open                   # everything outstanding
gh issue list --state open --label next-up   # what is at the front of the queue
gh issue view <n>                            # what blocks it, and what it blocks
```

Figures are not repeated here, because they change with almost every merge. Regenerate them instead:

| number                         | where it comes from                                 |
| ------------------------------ | --------------------------------------------------- |
| how closely `nqbt` matches NT8 | [docs/nt8-fidelity.md](docs/nt8-fidelity.md)        |
| test count and coverage        | `./.venv/Scripts/python.exe -m pytest`              |
| bars, contracts and roll dates | `nqbt contracts`, `nqbt splice --diagnostics`       |
| anything from a campaign       | `tools/campaign_report.py` over `results/campaign/` |

## What the search has found so far

Every strategy has been swept across every setting it has, on both instruments, at realistic costs. [docs/findings/](docs/findings/) is the register of what each search returned — [by archetype](docs/findings/by-archetype.md) if you want one strategy's whole story, [by gate](docs/findings/by-gate.md) if you want what has survived which check. The full method and the caveats are in §M27 and §M28.1, which are worth reading before quoting any of this:

- **Only two strategies have ever beaten the coin flip: `InsideBar` and `OpeningRange`.** `OpeningRange` is the only one to pass the first three checks. What stops it at the fourth is not having enough trades to be sure, rather than evidence that it fails.
- **What holds `InsideBar` back is where its exits are placed, not its entry.** The distance to the profit target matters enormously on the untouched half of the history and barely at all on the half used for choosing. The good setting exists, and there is no way to know in advance that it is the good one, which is the whole problem (§M27.3).
- **Bar size matters far more than any indicator setting.** Which bar size you use explains roughly ten times more of the variation in results than any moving-average length or type, on every strategy. Spend your time on bar size and on where the stop and target go, not on tuning indicator periods.
- **A failed test retires a set of settings, not a strategy.** All seven stay registered and swept. Before re-running one that previously failed, be able to say what has actually changed: a new condition, a different exit, a wider range, or more data. Re-running with none of those is the same measurement with a different random seed. See `docs/roadmap.md` § "Parked is not abandoned".
- **`DeadCatBounce` loses money in every combination tried**, and slicing the results by market condition or time of day does not rescue it. It stays as the known-quantity test case that proves the machinery works. Its entry rule is still measurably better than a coin flip, which means the loss is in the costs, the holding time or the exit placement, not in the idea.

## Known limitations

- **Every position closes before the session ends.** This comes from the prop firm's account rules, so it is not something you can switch off, and it matches what NinjaTrader does anyway. The consequence is that nothing here can hold overnight, so any strategy needing a multi-day hold cannot be built. It is also the *only* prop-firm rule modelled, because the tool has to work for ordinary accounts too.
- **Entry orders last exactly one bar.** If the order does not fill on the next bar, NinjaTrader cancels it. NinjaTrader can be told otherwise, so this is a default and not a hard limit. The simulation copies it because it is what the live strategies do.
- **Thin trading sessions are left visible.** For one day before most contract handovers, NinjaTrader holds only the Sunday evening hour. Those gaps are real, and they used to be hidden because the wrong contract was being used. Filling them from the neighbouring contract would splice two different prices into one day.
- **Contract handover dates are worked out from the data and deliberately not matched to NinjaTrader's.** NinjaTrader uses dates typed into a preferences window, which makes them somebody's choice, not a measurement. The cost is that results very close to a handover may not reproduce bar for bar.
- **Risk is measured from the intended stop, not the achieved one.** The strategies place their targets relative to where the stop was *meant* to go, so profit targets land slightly under their nominal multiples, and a stop can lose a little more than planned when a gap or slippage made the real risk larger.
- **Best and worst prices during a trade are measured differently from NinjaTrader.** These run to the extreme of the exit bar where NinjaTrader stops at the exit itself. It affects reporting only, never profit and loss.
- **TA-Lib does not agree with NinjaTrader.** Use the `indicators.nt8_*` functions for anything that will be compared against it. EMA, ATR, standard deviation, Bollinger and Keltner all differ, and NinjaTrader's Keltner is not the usual definition at all.

## Documentation

| file                                         | what it holds                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------------------ |
| [docs/findings/](docs/findings/)             | every search that has been run, what it returned, and what it settles                |
| [docs/nt8-fidelity.md](docs/nt8-fidelity.md) | every NinjaTrader rule the simulation copies, and the evidence for each one          |
| [docs/roadmap.md](docs/roadmap.md)           | why the work happened in this order, the standing traps, and the decisions taken     |
| [CONTRIBUTING.md](CONTRIBUTING.md)           | how to change the code: style, tests, commits, pull requests and the regression gate |
| [CLAUDE.md](CLAUDE.md)                       | the same ground rules, written for an AI assistant working in this repository        |

Explanations live in `docs/`, not in the code. Docstrings say what something is and stay short, and every reference to a document names a specific section.

## License

[GPL-3.0](LICENSE).
