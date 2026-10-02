# nqbt

Design notes for the package that have no other home. Most modules' reasoning already lives in [`docs/roadmap.md`](../docs/roadmap.md), [`docs/nt8-fidelity.md`](../docs/nt8-fidelity.md) or a [`docs/findings/`](../docs/findings/) file, and their docstrings point there directly. This file holds the rest: why a module is shaped the way it is where no [campaign](../README.md#campaign), NT8 rule or decision record covers it. [`README.md`](../README.md) § "Repository layout" lists what each module is for.

## Data

### ingest.py

**The manifest hashes every byte already parsed, not a fixed-size head.** Two producers write the export files, and they give different guarantees: the NinjaScript AddOn appends, while a manual Tools → Historical Data export regenerates the file. A regenerated file routinely differs in its tail -- a [bar](../README.md#bar) exported mid-formation comes back with different values once it completes, and bars occasionally vanish between exports -- while its head is untouched. A head-only hash therefore calls a rewrite an append, and the stale or withdrawn bars survive in the cache indefinitely; before the fix it froze stale bars in the cache and dropped real ones at the seam. Why the archive exists at all: `docs/nt8-fidelity.md`, "Contract data".

### splice.py

**`EARLY_ROLL_RATIO` is read off the [MNQ](../README.md#nq-and-mnq) set.** At a healthy handover the back contract is already closing on the front, and the observed back/front volume ratio on the roll session runs 0.49 to 0.95 across the MNQ contracts. A ratio far below that means the front contract was still dominant when its data ran out, so only a coverage-boundary roll under the ratio is flagged; the coverage boundary itself is the normal path for NT8 data.

## Context

### context.py

- **A `ContextSpec` is declared up front** rather than discovered mid-loop, because the grids refuse a period they were not built for rather than return a wrong row. It lives here rather than beside the [archetype](../README.md#archetype) registry because it describes a `Dataset`, and `context.py` must not import from `nqbt.sim` -- `docs/roadmap.md` §M17.
- **Some series imply others, and `prepare` builds them in that order.** The VWAP band's basis is the session VWAP, so a dataset holding both takes the VWAP from the band rather than computing it twice. A bandwidth compression key is defined off the Bollinger grid's own rows, so it asks for that period (`band_periods_needed`). Relative volume is defined per bar of session, so it builds the time-of-day clock. Follow-through is measured against a range, so it needs `range_keys`.
- **The session range is the only series whose existence depends on the bar size**, so it takes a stated bar size rather than one inferred per key -- `docs/roadmap.md` §M28.
- **`DEFAULT_SPEC` is the set `prepare` built unconditionally before specs existed** (#27).

## Simulation

Every archetype's loop is an entry half over the shared [bracket](../README.md#bracket) engine. **The trade-log gate runs each loop at its defaults**, so it sees only the rules on at them -- `CONTRIBUTING.md` § "The trade-log regression gate".

### sim/types.py

One parameter dataclass per archetype. A ported archetype's fields mirror its NinjaScript properties and its defaults are the script's `SetDefaults`, except `PullBackAndGoParams` -- `docs/nt8-fidelity.md`, "Reconciliation result -- PullBackAndGo".

- **ElasticBand's `swing_lookback` defaults to 1**, a stop just beyond the signal candle: the cheapest attempt the archetype can make, where a move that keeps going costs a few ticks and the next bar can try again.
- **`vwap_min_session_bars` exists because the VWAP anchor resets at every session open**, so a session's first bars have a band built from too few observations to be one.
- **OpeningRange's width target is not scaled by `tp_multiplier`**, because a width multiple is already a distance and scaling it too would be the same [axis](../README.md#axis) twice.
- **The follow-through scale refuses a bracket half whose mode states its geometry in another unit.** There is then no width for it to multiply, and the axis would be silently inert.
- **A limit entry that gaps [fills](../README.md#fill) at the open, which makes the trade better than planned**, the mirror of a stop entry's gapped fill.

#### Context-filter fields

Every archetype carries the same six context filters; `DeadCatParams` documents them and every other class points there. Each is a bitmask integer so it is a legal [sweep](../README.md#sweep) axis -- `docs/roadmap.md` §M10 -- and each is skipped entirely at its everything value -- §M10.4. The threshold defaults are conventional starting points, not measurements -- §M10.1, §M10.2 and §M19.1.

- **`ContextFilterParams` is a structural `Protocol`** so that `validate_context_filters` is one definition rather than a copy per parameter class. It checks every sub-field whatever its filter admits, so a nonsense window or [resolution](../README.md#resolution) cannot ride along inertly until a sweep turns its filter on.
- **`REQUIRE_ALL` is zero rather than the number of gates**, because how many gates are active is a property of the [combination](../README.md#configuration), and a rule set has to be able to say "all of them" without knowing it. Counting the active gates is also what lets a count be validated at construction -- `docs/roadmap.md` § "The build spec's three loose ends".

### sim/bracket.py

One copy of every exit rule the reconciliations validated -- `docs/roadmap.md` §M20a. Every function is an `@njit(cache=True)` device function, which numba inlines into the calling loop at no cost.

- **`force_flat` rides in `Bars`** because it is a fact about the bar rather than about a strategy; holding it with the OHLC stops the engine being handed a different bar's flag from the one it is resolving.
- **[Force-flat](../README.md#forced-flat) resolves last** in `resolve_brackets`, so a position that reached a target and then ran out of session records both exits.
- **`flatten_position` is not a fill rule.** It takes a level from nowhere: the maximum-hold-time exit, the conditional early exit, an archetype's signal exit and the end-of-series liquidation each decide the bar, the price and the reason before calling it. The hold cap's and the early exit's reason comes from `market_exit_reason`, the one order between the two, which every loop calls; `resolve_brackets` never produces either.
- **`swing_stop` is never floored**, because a structural level widened to clear a cost floor stops being the level it is.

### sim/filters.py

- **`ContextFiltered` is a structural `Protocol`** rather than a union of the concrete parameter classes, so a new archetype gets all six filters by declaring the fields. `ConfluenceFiltered` is separate because declaring `confluence_required` is what opts an archetype into the confluence pattern.
- **The sizing labels are not the context gates.** `label_sides` reads whether each label favours or opposes each bar's own side, whereas the gates are side-blind masks, so an `UP` trend filter admits shorts in an uptrend. A `size_on_*` label adds contracts and narrows no entry; `confluence_required` narrows the entry and sizes nothing -- `docs/nt8-fidelity.md` §M45.

## Search

### archetypes.py

- **`Params` is a structural `Protocol`** rather than a union of the concrete classes, because the point of the registry is that `sweep.py` does not name them.
- **Each `*_context` builds only what some combination reads**, because every series costs memory in every parallel worker. Per bar, a [regime](../README.md#regime) lookback is eight bytes (the most expensive thing a context can add -- `docs/roadmap.md` §M10.1), a volume or compression series sixteen, a trend label eleven and a higher-timeframe average nine.
- **`INERT_AT` exists because a filter mask is off at its everything value, not at zero.** `dead_axes` compares against that value rather than testing truthiness: `ALL_REGIMES` is 7 and would read as on.
- **The gate maps cannot catch an axis that is inert under a mode rather than a toggle**, because `dead_axes` compares each toggle against one off value. ElasticBand's stop and target axes are each read under one `stop_mode` or `target_mode` alone, so sweeping `atr_stop_multiple` under `STOP_EXCURSION` runs identical combinations and nothing says so. OpeningRange's stop axes are the same blind spot -- `atr_period`, `atr_stop_multiple` and `min_bracket_dollars` under `ORB_STOP_ATR` alone, `stop_range_fraction` under `ORB_STOP_FRACTION` alone -- and so is `follow_through_sessions` against `ORB_SCALE_NONE`; SqueezeBreakout's stop axes inherit it. The memory cost is still avoided, because each context builds the ATR and the follow-through only where a combination selects the mode that reads it, and `tools/campaign_sweep.py` avoids the duplicate rows by making each mode a [variant](../README.md#variant) dimension -- `tools/README.md` § "campaign_sweep.py".
