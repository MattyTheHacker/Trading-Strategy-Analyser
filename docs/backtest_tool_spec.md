# Build spec: NQ/MNQ strategy research & backtesting tool

## Context

I day-trade NQ/MNQ futures through a prop firm, using NinjaTrader 8 (NinjaScript/C#) as my execution platform. I already have a working NinjaScript strategy (`DeadCatBounce.cs`) and I'm developing more fixed-rule, fully-automated strategies to remove discretionary decision-making entirely.

NT8's Strategy Analyzer is my ground-truth backtester, but it's too slow for wide parameter sweeps and walk-forward testing — every combination re-runs the full bar-by-bar simulation from scratch with no way to reuse work across iterations.

This tool is a **Tier 1 research tool**, not a replacement for NT8. Its job is to rip through large parameter/rule sweeps fast and narrow the search space down to a short list of promising candidates. Every surviving candidate then gets re-validated in real NT8 Strategy Analyzer before it's trusted — that's Tier 2, and it happens outside this tool. Keep that division in mind throughout: this tool should match NT8's *default* fidelity level (bar-close OHLC fills, no intrabar tick precision), not exceed it and not fall short of it in a way I wouldn't notice. Don't build tick-level fill simulation into this — that's deliberately deferred to Tier 2.

## Tech stack (decided, please follow)

- **Python** as the base language.
- **Numba** (`@njit`) for the one part of this that doesn't vectorize cleanly: the stateful, path-dependent trade simulation loop (entry → ratcheting stop → multi-leg target tracking, bar by bar). Everything else should be plain numpy/pandas where it can be.
- **TA-Lib** for standard indicators (MACD, RSI, Bollinger Bands, moving averages, etc.) rather than hand-rolled versions — faster and avoids subtle mismatches against standard implementations.
- **multiprocessing or joblib** to parallelize the parameter sweep across CPU cores — each combination is fully independent, so this should be close to free.
- Data cache format: your call, but should load once into memory/fast local storage (e.g. Parquet) and never be re-read from the original text exports during a sweep.

## Data pipeline

**Source data**: historical bars are exported manually from NinjaTrader 8 via Tools → Historical Data, per individual futures contract (NT8 doesn't stitch continuous contracts at the export level). Format is semicolon-delimited minute bars: `yyyyMMdd HHmmss;open;high;low;close;volume`, one bar per line, **timestamps are end-of-bar and in UTC** — convert to US Eastern (or whatever session reference makes sense) during ingestion. Instrument files are named per contract, e.g. `NQ 12-25.Last.txt`.

**Contract splicing**: NQ/MNQ are quarterly contracts, so multiple contract files need to be combined into one continuous series for any backtest window longer than a few months. Build this as an explicit step:
1. Determine roll dates via volume crossover — the date the next contract's volume overtakes the current front contract's, comparing daily volume between adjacent contract files.
2. Support an optional back-adjustment: at each roll date, compute the price offset between the two contracts and shift all earlier segments by that offset, so historical price levels line up with the current contract (mirrors NT8's own `MergeBackAdjusted` behavior). Make this toggleable — I want to be able to compare adjusted vs non-adjusted, since my strategies reference absolute price levels (round-number stop avoidance, support/resistance) where adjustment technically distorts historical price memory. This mostly matters for longer lookback windows, less for short intraday ones, but I want the option.

**Keeping data current**: I'm separately building a NinjaScript AddOn inside NT8 that periodically exports new bars and appends them to these per-contract files. You don't need to build that — but design the ingestion/caching layer to support incremental appends (track the last-seen timestamp per contract and only process new rows) rather than assuming a full reprocess every time.

**Instrument handling**: I trade both NQ (full-size) and MNQ (micro) — these have different tick values ($5/tick vs $0.50/tick). Position sizing, dollar risk, and commission/slippage calculations must be instrument-aware and correct in dollar terms for whichever contract is loaded — don't assume a single tick-value constant. (This exact bug already bit me in `DeadCatBounce.cs` — a tick-based risk cap that means very different dollar risk depending on which contract is loaded.)

## Strategy definition architecture

Follow the same pattern my existing NinjaScript already uses — fixed logic, parameterized:

- **Outer layer**: a plain Python dataclass (or similar) per rule-set, holding both boolean toggles (which filters are active) and numeric parameters (periods, multipliers, thresholds). This is what gets generated across ranges for a sweep and is what a human reads/writes by hand.
- **Inner layer**: one Numba-jitted simulation function *per strategy archetype* (i.e., per distinct entry/exit logic shape), not one universal function trying to express every possible strategy, and not a separate function per parameter combination. Different parameter values of the same logic reuse the same function; genuinely different entry logic gets its own function.
- Precompute boolean condition arrays (trend filter, candlestick pattern match, volume-relative-to-average, etc.) once per dataset, outside the sweep loop, so the simulation function just reads precomputed arrays rather than recalculating indicators per combination.
- Support a "confluence count" pattern as a first-class option: instead of hardcoding that all N filter conditions must be true, make the required minimum count itself a sweepable parameter (e.g., "at least 3 of 5 conditions").

**First archetype to implement**: port the existing `DeadCatBounce.cs` logic faithfully as the first simulation function, and validate its output against a handful of trades I can check by hand before trusting the sweep results. I'll provide that file for reference — use it as the source of truth for the exact entry/stop/target logic, don't reinvent it.

## Simulation requirements

- Stop-loss must support both a tight structural mode (previous swing high/low + a small cushion, never placed exactly at a round number) and a moving-average-trailing mode (MA value + cushion, offset from round numbers) — this should be a per-run toggle, not hardcoded to one.
- Ratcheting stop logic: the stop only ever tightens toward the current price, never loosens, updated once per completed bar.
- Multi-leg position scaling with independent per-leg profit targets (matching the staggered-target structure in `DeadCatBounce.cs`).
- Realistic commission and slippage built into the P&L calculation by default — not zero-cost. Make both configurable per run.
- A reward-to-risk minimum-ratio filter should be supported as an optional pre-trade gate (computed from entry/stop/target before the trade is taken).

## Sweep execution

Build the straightforward version first: loop over parameter combinations, and for each one run the full jitted simulation over the whole dataset (combo-major). Get this correct and validated before optimizing further. Only if profiling on real sweep sizes shows it's worth it, consider restructuring to a bar-major loop (or batching state across combos into arrays for a vectorized update per bar) — that's a real speedup for large sweeps via better cache reuse, but adds real complexity, so it should be justified by measured numbers, not assumed upfront.

Parallelize the combo-major sweep across cores from the start — that's a near-free win regardless of loop structure.

## Results & analysis layer

- Trade-by-trade output (entry/exit/stop/target prices, timestamps, P&L) plus summary statistics (win rate, expectancy, average win/loss, profit factor, max drawdown, R-multiple distribution) — every result tagged with the exact parameter combination that produced it, so results are filterable/rankable across the whole sweep.
- Walk-forward support: rolling in-sample/out-of-sample window splitting over the cached data.
- Monte Carlo support: permutation/resampling of a strategy's trade sequence to sanity-check robustness beyond the single historical path.

## Suggested build order

1. Data ingestion: parse NT8 export format, handle UTC conversion.
2. Contract splicing (volume-crossover roll + optional back-adjustment).
3. Indicator layer via TA-Lib, precomputed condition arrays.
4. Single Numba simulation function porting `DeadCatBounce.cs` exactly; validate against hand-checked trades.
5. Combo-major sweep harness + results/stats layer.
6. Parallelization across cores.
7. Walk-forward and Monte Carlo on top of the results layer.
8. (Only if needed after profiling) bar-major/batched restructuring for speed.

## What I'll provide alongside this prompt

- `DeadCatBounce.cs` — existing NinjaScript strategy, source of truth for the first archetype.
- A concept reference doc summarizing course material on technical analysis, risk/reward planning, and entry archetypes, which several of these design choices (confluence counting, risk-tiered scale-outs, entry archetype structure) are drawn from — useful context if new archetypes come up later.

Ask me before making architecture decisions I haven't specified here — particularly around exact file formats, project structure, and which specific statistics to compute beyond what's listed above.
