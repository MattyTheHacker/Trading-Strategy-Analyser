---
paths:
  - "nqbt/sweep.py"
  - "nqbt/context.py"
  - "nqbt/archetypes.py"
  - "nqbt/conditions.py"
  - "nqbt/results.py"
  - "nqbt/dispersion.py"
  - "nqbt/timeofday.py"
  - "nqbt/regime.py"
  - "nqbt/volume.py"
  - "nqbt/trend.py"
  - "nqbt/higher_timeframe.py"
  - "tests/test_context.py"
  - "tests/test_regime.py"
  - "tests/test_volume.py"
  - "tests/test_trend.py"
  - "tests/test_higher_timeframe.py"
  - "tests/test_sweep_stats.py"
  - "tests/test_archetypes.py"
---

# The sweep and the context

- **Register an archetype; do not fork the sweep.** `archetypes.py` is the registry, and
  `sweep.py` names no parameter class and no run function.
- **`sweepable` reads `dataclasses.fields()`, never `__slots__`** — `__slots__` holds only the
  fields declared on the class itself, so an inherited axis would vanish. A dropped axis does
  not raise; it makes every combination along it identical.
- **`prepare` builds what a `ContextSpec` declares, not everything.** Reading an undeclared
  series raises `ContextError` naming the field to set, rather than returning `None` into a
  boolean AND. **Grids are keyed by `(kind, period)` the whole way through** —
  `ContextSpec.ma_keys` carries the pairs, each gate has a `<gate>_kind` beside its
  `<gate>_period`, and a kind is a legal sweep axis. Adding a kind means adding it to
  `conditions.MA_KINDS`, and one that does not match NT8's recursion is a fidelity break rather
  than a feature. `cli.py` asks for VWAP unconditionally on purpose — `--explain` exists to
  show what a sweep did *not* read.
- **`sweep_axes` is the one mechanism for strategy × resolution × contract.** The strategy axis
  is a list of grids, not archetype names; the contract axis is carried by `bars` itself. **Do
  not add a second wrapper for a new axis.** `combo_id` means the same parameters at every axis
  point but *not* across grids, which is why `strategy` is part of the log key.
- **`results` writes both DuckDB tables by name, never by position**, which is what makes a
  nullable column safe to add to a database that already has rows. Pin dtypes on a nullable
  tag: an all-null `object` column infers as INTEGER in DuckDB.
- **`keep_trades` changes what `run_combination` returns, never what it measures.**
- **Everything expensive is precomputed once in `prepare`; the sweep loop must stay cheap.**
  Never recompute an indicator inside a combination. Moving-average grids keep only the boolean
  gate unless `keep_values=True` — an order-of-magnitude difference in memory.
- **`phase_filter`, `regime_filter`, `volume_filter`, `trend_filter` and
  `higher_timeframe_filter` are bitmask ints so they are sweepable**, and each signal skips the
  conjunction entirely at `ALL_PHASES`/`ALL_REGIMES`/`ALL_STATES`/`ALL_TRENDS`/`ALL_SIDES`.
  That is not an optimisation: an efficiency-ratio warm-up bar, a session with no volume
  baseline yet, a bar whose slope cannot be measured and a bar no coarse bar has closed before
  each pass *no* mask, so ANDing at the default would quietly drop them. A mask is therefore
  off at its everything value, not at zero, which is what `archetypes.INERT_AT` tells
  `dead_axes`.
- **A higher-timeframe average is stamped from the last *completed* coarse bar, and that is the
  one thing in this module that fails silently.** A fine bar reads the coarse bar closing
  alongside it and never one closing after; anything else manufactures an edge no summary
  statistic would show. `tests/test_higher_timeframe.py` pins it with a series whose current
  coarse close is the only thing that could flip the label — do not "simplify" the projection
  without running it. `docs/roadmap.md` § "Multi-timeframe moving averages".
- **The trend label must not switch `keep_values` on, and does not.** `trend.trend_grid` builds
  a values-carrying grid over its own two periods and drops it, so the shared grids stay
  boolean-only however a sweep is configured. Do not "simplify" it into reading
  `Dataset.ma_values` — that is the 8-bytes-against-1 switch, per period, per worker.
- **`dead_axes` knows one toggle per axis, and `volume_rolling_bars` has two.** It is inert while
  `volume_filter` admits everything *and* at every `volume_form` but `ROLLING`; only the first is
  caught. Sweeping the window under a per-bar form runs identical combinations.
- **Parallel sweeps top out around 5×, not 16×, and that is the hardware.** Per-core throughput
  drops when all physical cores are busy (mobile Ryzen, high single-core boost against a much
  lower all-core clock); SMT adds almost nothing for twice the memory. Measured, not guessed —
  don't "fix" it. Figures in `docs/roadmap.md`.
