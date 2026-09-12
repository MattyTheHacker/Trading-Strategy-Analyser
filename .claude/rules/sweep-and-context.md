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
  - "nqbt/compression.py"
  - "nqbt/trend.py"
  - "nqbt/higher_timeframe.py"
  - "tests/test_context.py"
  - "tests/test_bands.py"
  - "tests/test_regime.py"
  - "tests/test_volume.py"
  - "tests/test_compression.py"
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
  under the source that does not read it runs identical combinations silently. **So are the two
  signal-bar requirements**: `rejection_close_fraction` is read under `SHAPE_REJECTION` alone and
  `one_sided_lookback` only while `min_one_sided_bars` is above 0, which is why the shape is a
  variant dimension in `campaign_sweep.py` and the count is an axis carrying its own off value —
  `ELASTIC_SHAPES` is the shape. **`recovery_fraction` joins them**: it is read under
  `TRIGGER_RECOVERY` alone, so the trigger and its depth are one variant dimension
  (`ELASTIC_RECOVERY_ARMS`) rather than two crossed axes. `docs/roadmap.md` §M26.5 and §M26.6.
- **An axis another entry rule made a duplicate can come back to life, and nothing reports that
  either.** §M26.5 measured `min_bars_outside` as inert under `reclaim` on 100% of cells and
  under `reversal` on 82.7%, because those shapes imply the run; the recovery trigger reads the
  run at the bar *before* the signal and so does not, and its η² is an order of magnitude higher
  there. **Do not carry an axis's measured deadness across to a variant set with a different
  entry rule** — re-measure it, because the interaction that killed it was with the rule and not
  with the axis. `docs/roadmap.md` §M26.6.
- **`dead_axes` knows one toggle per axis, and `volume_rolling_bars` has two.** It is inert while
  `volume_filter` admits everything *and* at every `volume_form` but `ROLLING`; only the first is
  caught. Sweeping the window under a per-bar form runs identical combinations. **Build the axes
  through `volume.key`** wherever a sweep crosses the form with the window — it drops the window
  from every form that does not read it, so the axis cannot vary where it is inert;
  `campaign_sweep._volume_axes` is the shape.
- **A raw volume threshold pair is not one cut either**, for the same reason a raw regime
  threshold is not. 0.7/1.5 admits 28% of bars under `PER_BAR` and 8% under `ROLLING` on the same
  series, and the share moves with the bar size within a form too, so cells cut by it cannot be
  read against each other across either axis. State the cut with
  `volume.thresholds_from_quantiles`, fitted on the selection window alone, and carry the tail
  size in the stratum name rather than crossing it with the thresholds. `docs/roadmap.md` §M27.8.
- **The two volume windows are cells and not axes, and so is anything else the fit reads.**
  `volume_rolling_bars` and `volume_baseline_sessions` change the ratio's own distribution, so
  the fitted pair moves with them exactly as it moves with the lookback -- an axis crossed
  inside one cell would read a cut fitted for a different window. `volume.describe_key` has
  always carried both, so a ladder needs no new naming; `campaign_sweep.volume_series` takes the
  rungs and `volume.key` drops the rolling one from the two forms that do not read it, which is
  what keeps a rung from being one series wearing three names.
  `docs/findings/m32-volume-windows.md`.
- **Measure what an entry already selects before adding a filter that selects the same thing.**
  ElasticBand's unfiltered 2σ VWAP extension already sits in `HEAVY` at 2.1× the base rate under
  `PER_BAR` and *below* it under `SESSION_TO_DATE`, so "require volume on the break" was partly
  already in force and partly its own reverse, decided by a form nobody had chosen. A gate's
  overlap with the signal is one boolean AND to measure and it bounds what the sweep can find.
  `docs/roadmap.md` §M26.9.
- **A stratification yields one state per cell, so a multi-state mask is never among the cells.**
  `volume_filter` is a bitmask and `NORMAL | HEAVY` is a legal value, but `_volume_cells` — and
  every other generator in `STRATUM_GROUPS` — yields exactly one state each. A campaign that
  finds one state helping and its neighbour hurting has therefore not tested the union of them,
  and nothing in the table says so. `docs/roadmap.md` §M26.9.
- **Compression is filtered on a trailing rank, never on the raw width, and that is what makes
  its raw thresholds comparable.** The width spans a factor of 17,000 across the roots,
  resolutions, forms and periods a campaign crosses, so a threshold on it is a different cut in
  every cell; the rank puts every cell within five points of the share it names. Do not "simplify"
  `compression.py` into gating the width, and do not add a quantile calibration pass to
  `campaign_sweep.py` for it without re-measuring the table first -- `docs/roadmap.md` §M19.1.
- **The bandwidth form reads `bands.BandGrid` rather than building a Bollinger of its own**, so
  `ContextSpec.band_periods_needed()` -- not `band_periods` -- is what `prepare` builds the band
  from. A bandwidth key implies its period the way `needs_vwap_band` implies `needs_vwap`.
  `docs/roadmap.md` §M26.
- **A session range is stored per session, not per bar.** `sessionrange.SessionRangeGrid` holds
  the levels as `[n_keys, n_sessions]` and only the armed flag per bar, read through a per-bar
  `session_id`. Stamping the level per bar instead costs 16 bytes a bar **per window**, which
  every parallel worker pays; as stored it is about 5 bytes a bar whatever a sweep asks for. Do
  not "simplify" it into a per-bar level. `docs/roadmap.md` §M28.1.
- **The range window and anchor are not free axes: the bar size has to divide both.** A
  cash-anchored range needs `N | 930`, which with §M13's `N | 60` leaves **`N | 30`** and rules
  60-minute bars out entirely. `sessionrange.validate_key` raises rather than measuring a window
  over a different span than it names, so a sweep crossing an unbuildable pair fails loudly.
  That is also why `campaign_sweep.Variant` carries `resolutions`: which windows exist depends on
  the resolution, and a grid crosses its axes uniformly at every axis point, so the window is a
  variant dimension rather than an axis. `tests/test_sessionrange.py` pins the divisor set.
- **OpeningRange's stop and entry axes are ElasticBand's blind spot again.** `atr_period`,
  `atr_stop_multiple` and `min_bracket_dollars` are read under `ORB_STOP_ATR` alone,
  `stop_range_fraction` under `ORB_STOP_FRACTION` alone, `entry_offset_ticks` under every entry
  mode but `ORB_ENTRY_RETEST`, `retest_offset_ticks` under that one alone, and
  `break_confirm_ticks` under neither `ORB_ENTRY_BREAKOUT`; `dead_axes` knows one off value per
  axis, so none of them is caught. The *memory* cost is avoided — `openingrange_context` builds
  no ATR unless some combination selects the ATR stop — but sweeping any of them under a mode
  that does not read it runs identical combinations silently. **The stop mode and the entry mode
  are therefore variant dimensions rather than axes** in `campaign_sweep.py`, which is what keeps
  each variant's axes to the ones it actually reads — `ORB_ENTRIES` is the shape.
- **A parameter in `not_sweepable` is held at its default forever unless a variant moves it, and
  nothing reports that either.** `target_r_multiples` and `target_width_multiples` are tuples, so
  no axis can reach them; every ORB campaign from §M28.1 to §M28.8 therefore ran
  `ORB_TARGET_WIDTH` at `(1.0, nan)` and read a target axis that only the R scheme varied. This is
  worse than an inert axis rather than milder: an inert axis at least appears in the stored `axes`
  column. **Check `not_sweepable` before claiming a campaign swept a bracket** — `ORB_WIDTH_LADDERS`
  and `ELASTIC_LADDERS` are the shape a ladder has to take. `docs/roadmap.md` §M28.11.
- **An axis whose best value is its last value has been truncated, not swept**, and extending it
  belongs in a new variant set built from the stored list rather than a rewritten one, so the two
  tables share cells — `ORB_LADDER_FRACTIONS` is `[*ORB_FRACTIONS, ...]` for exactly that, and the
  1,024 shared rows are checked to agree exactly. `docs/roadmap.md` §M28.11.
- **A gate can be near-empty rather than inert, and a sweep reports that as too few trades
  rather than as a defect.** ElasticBand's engulfing shape was built, measured at **138 signals in
  1.66M MNQ bars** and removed before it reached a grid: the extension threshold is defined on the
  close, so a bar whose body ran the other way *and* covered its predecessor has usually stopped
  being beyond the band. Count the signals a new entry gate leaves before crossing it with
  anything — `MIN_TRADES` would have dropped the cells silently. `docs/roadmap.md` §M26.5.
- **A re-sweep that adds an axis is its own variant set, never an edit to `VARIANTS`.** That dict
  is what §M27 and §M28.1 measured, so an added axis would leave the stored rows and the code
  that produced them disagreeing. `VARIANT_SETS` names them and each carries a `STRATUM_SETS`
  entry naming its strata **before** it runs — `docs/roadmap.md` §M28.2. **The variant name is
  the only thing separating two runs in one database**, so a set that re-runs a stored range
  has to name it differently: `ORB_GEOMETRY_VARIANTS` writes `cash-open+30m` where
  `ORB_VARIANTS` wrote `cash=30m`, and `campaign_holdout` pairs the two windows one-to-one.
- **A price basis is stated, never inferred, and the default is the refusing one.**
  `prepare(price_basis=...)` defaults to `PriceBasis.UNKNOWN`, and a rule that reads an
  absolute level -- round-number stop avoidance is the only one -- runs on `RAW` alone. An
  attribute carried on the frame was rejected: it fails to propagate silently and the default
  would then be the permissive answer. `sweep.sweep` does not forward it, so a sweep that
  needs it builds its `Dataset` and passes `data=`. `docs/roadmap.md` § "The build spec's
  three loose ends".
- **A shortlist is the wrong instrument for an A/B variant pair, and the bias is in the design
  rather than the data.** Two arms of a variant set rarely hold the same number of
  combinations -- a treatment carries the axes its rule reads -- so its shortlist is a
  best-of-more and wins on size. Measured: EmaCrossover's trailing arm has 384 combinations
  against its control's 32, its best beats the control's best in several cells, and paired
  cell by cell it is a consistent *cost*. Use `tools/campaign_paired.py` for a control/treatment
  pair and `tools/campaign_holdout.py` for a ranking. `docs/roadmap.md` § "The build spec's
  three loose ends, measured".
- **A shortlist drawn over a mixture of geometries dilutes the one that works.** Ranking across
  every range a grid swept and then testing the top twenty against a matched null pools the
  cells that separate with the cells that do not, and the excess reported is the average of
  both. Measured on OpeningRange: §M28.2's null over all five ranges put one cell under
  p < 0.05, and the same null confined to one range put seven to twelve of twenty under it on
  both roots — at two of the four lengths and neither of the others. **Rank within the variant
  when the variant dimension is the thing being measured**, which is what `--variant` is for.
  `docs/roadmap.md` §M28.8.
- **An axis that is a duplicate in one arm and live in another duplicates the shortlist rather
  than shrinking it.** `dead_axes` reports an axis nothing reads; it cannot report one whose
  values a *different* rule in the same variant set collapses. Measured on ElasticBand's
  §M26.8 grid: `min_bars_outside` produced byte-identical cells on 64.7% of `shape=reversal`
  rows and 0% of `shape=any` rows, so a top-20 shortlist drawn inside a reversal arm is closer
  to a top 10 counted twice — and the sign test over paired cells counts each pair twice with
  it. Count the distinct cells a shortlist actually holds before quoting its size.
- **A stored log read from the window that ranked it is a selected maximum, not a result.**
  `campaign_shortlist.shortlist` ranks and reads one window at a time, so `--window holdout`
  takes the twenty best *holdout* rows and every figure computed off their logs carries that
  selection. `campaign_holdout.held_out` is the pair instead — the held-out rows of the
  configurations the **selection** window ranked highest — and `--held-out` is the flag that
  reaches it from `campaign_shortlist.py` and `campaign_montecarlo.py`.
  `tools/campaign_propaccount.py` and `tools/campaign_exits.py` take no `--window` at all for
  the same reason. `docs/roadmap.md` §M28.13.
- **Read `sel_top20_pf` beside `passes`.** The held-out gate is defined on the test window
  alone, so a shortlist drawn from a space containing nothing profitable can clear it by
  luck -- DeadCatBounce does, on MNQ, with a selection-window shortlist averaging 0.940.
- **Parallel sweeps top out around 5×, not 16×, and that is the hardware.** Per-core throughput
  drops when all physical cores are busy (mobile Ryzen, high single-core boost against a much
  lower all-core clock); SMT adds almost nothing for twice the memory. Measured, not guessed —
  don't "fix" it. Figures in `docs/roadmap.md`.
- **The `annotations` table widens by name exactly as `combos` does**, so a dataset prepared
  with one more series needs no migration and the earlier rows read null. It is keyed
  `(sweep_id, combo_id, trade_id)` and joined to the other two by `results.create_trade_view`;
  the reason a parameter may filter that view but never group it is in
  `.claude/rules/stats-and-trades.md`.
- **A `combos` table widening by name is what breaks the paired read, and it fails silently.**
  `campaign_crossread.paired` joins a stratum to its unfiltered twin on every parameter, so a
  column a later campaign added is null in the earlier rows and equal to nothing — **every pair
  across that column is dropped and the tool reports a clean zero**. It cost §M30 an entire
  first read: ten columns across three archetypes, from §M29, §M28.10 and three §M26 campaigns.
  `campaign_crossread.ran_at` fills a null parameter with the archetype's own default, which is
  what a row stored before the column ran at. **Do not turn that back into a list of column
  names** — the list was ten long after one campaign. `docs/findings/m30-volume-regime-recut.md`.
