---
paths:
  - "nqbt/sweep.py"
  - "nqbt/context.py"
  - "nqbt/archetypes.py"
  - "nqbt/conditions.py"
  - "nqbt/bands.py"
  - "nqbt/results.py"
  - "nqbt/dispersion.py"
  - "nqbt/timeofday.py"
  - "nqbt/regime.py"
  - "nqbt/volume.py"
  - "nqbt/trend.py"
  - "nqbt/higher_timeframe.py"
  - "tests/test_context.py"
  - "tests/test_bands.py"
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
  than a feature. **Build the keys with `ma_keys_from_pairs` wherever the kinds come from
  separate gates** — `ma_keys(**{gate_kind: periods})` looks equivalent and silently loses a
  gate whenever two of them share a kind, which the stock `ema`/`sma`/`sma` set always does.
  `cli.py` asks for VWAP unconditionally on purpose — `--explain` exists to show what a sweep
  did *not* read.
- **`sweep_axes` is the one mechanism for strategy × resolution × contract.** The strategy axis
  is a list of grids, not archetype names; the contract axis is carried by `bars` itself. **Do
  not add a second wrapper for a new axis.** `combo_id` means the same parameters at every axis
  point but *not* across grids, which is why `strategy` is part of the log key.
- **`results` writes both DuckDB tables by name, never by position**, which is what makes a
  nullable column safe to add to a database that already has rows. A column the frame carries
  and the table does not is **added**, so one `combos` table holds several parameter classes and
  the earlier rows read null; nothing is dropped any more. Pin dtypes on a nullable tag: an
  all-null `object` column infers as INTEGER in DuckDB, and a column both sides carry keeps the
  **stored** type — `_append_or_create` raises `ResultsError` rather than let DuckDB round `2.5`
  into a BIGINT column, so a grid sweeping `[1, 2]` where an earlier one swept `[1.0, 2.0]` is a
  loud failure and not a silent one.
- **`keep_trades` changes what `run_combination` returns, never what it measures.**
- **A `Grid` is axes or an explicit combination list, never both.** `Grid.of_combinations`
  exists for a shortlist, which is an arbitrary subset of the product that produced it and
  cannot be stated as axes — twenty stored rows crossed is thousands of combinations rather
  than twenty, and the run still reports a clean number. `combo_id` stays the position in the
  list, and `axis_values` becomes the union over it so `required_context` covers every member.
  **Anything that rebuilds a grid must carry `combos` across**: `walk_forward`'s costed rebuild
  does, and dropping it there leaves the base alone while still reporting a fold of selection.
  `docs/roadmap.md` §M27.6.
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
- **A raw regime threshold is not one cut, and sweeping it against `regime_lookback` is the
  confound rather than the measurement.** `0.5` is the 59th percentile of a driftless random
  walk at a lookback of 5 and the 99.6th at 50, and the share of bars it admits moves with the
  bar size too, so cells cut by it cannot be read against each other. State the cut with
  `regime.thresholds_from_quantiles` — fitted on the selection window alone — or with
  `regime.thresholds_from_multiples` against `random_walk_ratio`, and carry the lookback in the
  stratum's name rather than crossing it with the thresholds as a second axis.
  `docs/roadmap.md` §M27.5.
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
- **The band grid is keyed by period alone, and the multiple is free.** `bands.band_grid`
  builds basis, standard deviation and stretch per period; every `entry_std`, `max_entry_std`
  and stretch target reads the same three rows, so sweeping a multiple costs nothing. Do not
  add the multiple to the key "for symmetry" with `ma_keys` — it would multiply the grid for no
  information. `docs/roadmap.md` §M26.
- **The VWAP band is the second source and has no period axis at all.** `bands.vwap_band` is one
  row rather than a grid, because its window is the session so far — so `band_period` is read
  under `BAND_BOLLINGER` alone and `vwap_min_session_bars` under `BAND_VWAP` alone.
  `elasticband_context` builds only the bands a grid's `band_source` values actually name; a
  pure-VWAP sweep builds no period grid. `docs/roadmap.md` §M26.4.
- **ElasticBand's stop and target axes cannot be gated at all, and that is a known blind spot.**
  They are inert at every `stop_mode`/`target_mode` but one, and `dead_axes` compares a toggle
  against a single off value. Sweeping `atr_stop_multiple` under `STOP_EXCURSION` runs identical
  combinations and nothing will say so — same shape as `volume_rolling_bars` below. **`band_period`
  and `vwap_min_session_bars` are the same blind spot against `band_source`**, so sweeping either
  under the source that does not read it runs identical combinations silently.
- **`dead_axes` knows one toggle per axis, and `volume_rolling_bars` has two.** It is inert while
  `volume_filter` admits everything *and* at every `volume_form` but `ROLLING`; only the first is
  caught. Sweeping the window under a per-bar form runs identical combinations.
- **Parallel sweeps top out around 5×, not 16×, and that is the hardware.** Per-core throughput
  drops when all physical cores are busy (mobile Ryzen, high single-core boost against a much
  lower all-core clock); SMT adds almost nothing for twice the memory. Measured, not guessed —
  don't "fix" it. Figures in `docs/roadmap.md`.
