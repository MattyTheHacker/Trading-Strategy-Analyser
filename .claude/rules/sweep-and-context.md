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
  - "tests/test_context.py"
  - "tests/test_regime.py"
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
  boolean AND. Grids are keyed by `(kind, period)`. `cli.py` asks for VWAP unconditionally on
  purpose — `--explain` exists to show what a sweep did *not* read.
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
- **`phase_filter` and `regime_filter` are bitmask ints so they are sweepable**, and each signal
  skips the conjunction entirely at `ALL_PHASES`/`ALL_REGIMES`. That is not an optimisation: an
  out-of-session stray and an efficiency-ratio warm-up bar each pass *no* mask, so ANDing at the
  default would quietly drop them. A mask is therefore off at its everything value, not at zero,
  which is what `archetypes.INERT_AT` tells `dead_axes`.
- **Parallel sweeps top out around 5×, not 16×, and that is the hardware.** Per-core throughput
  drops when all physical cores are busy (mobile Ryzen, high single-core boost against a much
  lower all-core clock); SMT adds almost nothing for twice the memory. Measured, not guessed —
  don't "fix" it. Figures in `docs/roadmap.md`.
