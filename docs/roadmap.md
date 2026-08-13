# Roadmap

Planned work, in dependency order. Nothing here is built. `CLAUDE.md` carries the one-line
summaries; this file carries the reasoning and the traps.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the
project's own docs first, [trading_concepts.md](trading_concepts.md) Part II
second. The discretionary-practice notes are a source of framing and of numeric definitions we
lack, not a source of priorities.

---

## Order of work

Dependency order, not priority order — each item's prerequisites sit above it.

| # | Work | Why here |
|---|---|---|
| ~~1~~ | ~~Re-export NQ manually~~ | **Done 2026-08-11.** 19 contracts, all 18 rolls on genuine crossovers, archive 4.09M → 4.60M bars. Also exposed a stub-session bug in roll detection, now fixed. |
| ~~2~~ | ~~Run the simulation against NQ~~ | **Done 2026-08-11.** Runs end to end including parallel sweeps. Instrument scaling proven exact: same bars through both specs give identical geometry and ×10 gross P&L on every leg. |
| ~~3~~ | ~~**M9** — split context from simulation~~ | **Done 2026-08-12.** `nqbt/context.py` and `nqbt/trades.py` exist, the layering is enforced by import-analysis tests, and every producer path was captured before and after: the moves are byte-identical across all 14 files, the schema additions leave every pre-existing column identical. |
| 3a | **M20a** — code review: the three findings that block M15 | A pass over the code found `explain.py` disagreeing with the simulation on **50%** of trades, `stats.summarise` raising on an empty log, and the bracket machinery **already duplicated** inside `simulate_deadcat`. The third is the one that matters: M15 must apply `d` to every line of it, and there are two copies. Unify first. |
| 3b | **M15** — direction in the simulator, then port `PullBackAndGo.cs` | The actual blocker on every new archetype, and it is half of M9 already: M9 adds `direction` to the trade schema for the importer's sake, M15 makes it load-bearing in the `@njit` loop. PullBackAndGo is long-only with existing C#, so it proves the long path against a real NT8 trade list before anything un-groundable is built. |
| 3c | **M16** — NT8-parity ATR, StdDev, Bollinger, Keltner | Five consumers, not one. Blocks the squeeze, blocks all three unported NinjaScripts, and gives EMA crossover a stop rule. Paying it once here stops it being rediscovered per archetype. |
| 3d | **M17 + M13 + M14** — strategy, resolution and contract as axes above the `Dataset` | **One mechanism, not three.** All three add an axis outside `DeadCatParams`, all three need one `Dataset` per value, all three need a nullable results column. Doing them together settles the schema once, before the stale DuckDB re-run rather than after. |
| 4 | **M7a** — `randomentry.py`, pulled forward from step 6 | The null that makes a *second* archetype interpretable. Without it "EMA crossover beats DeadCatBounce" is a comparison of two numbers with no scale. Cheap once M15 lands, because it reuses the bidirectional exit machinery. |
| 5 | **M18** — EMA crossover | The one archetype built now, to prove the protocol. Cheapest real test of M15 and M17, and a legitimate known-negative control (see §M18). |
| 6 | Numpy-native summary path | **Pulled forward from step 7.** Crossover generates tens of thousands of trades per combination where DeadCatBounce generates ~1,400, so the 71% of runtime that is pandas stops being an annoyance and starts being the sweep. |
| 7 | **M10** — regime, relative volume, trend, time of day | Dual-use: the review needs them, and they let existing sweep results be stratified rather than averaged. |
| 8 | **M11** — the trade review | The stated goal. Needs 3 and 7. Deliberately *not* displaced by the archetype work above — see "Decisions taken". |
| 9 | **M7b** — walk-forward and Monte Carlo | The remaining two thirds of M7. Share machinery with M14 and with §11.4's permutation test. |
| 10 | **M19** — squeeze breakout | Queued, not scheduled. Needs an OCO entry model the loop does not have (§M19), so it is the expensive archetype; build it once M18 has proven the protocol. |
| 11 | **M12** — web GUI | Gated on the review's outputs being stable. |

**Next up: M20a, then M15.** Steps 1–3 are complete. M20a is three measured defects that sit directly in M15's path — see §M20. M20b (typing and tooling) and M20c (structural cleanups) are standing work with no gate on them.

**What changed and why.** Steps 3a–3c, 5 and 10 are new; steps 4 and 6 moved earlier. The
request was "add EMA crossover and squeeze breakout", but neither is reachable today and
neither is where the cost is: the simulator is **short-only** (M15), the indicators they need
have an unpaid NT8-parity debt (M16), and `sweep.py` is hardcoded to `DeadCatParams` (M17).
That infrastructure is ~all the work; the archetypes themselves are then small. It also pays
for the three NinjaScripts already written and never ported — `InsideBar.cs`,
`InsideBarTrailing.cs`, `PullBackAndGo.cs`, all long-capable, all using `ATR()`.

### Outstanding: reconcile NQ against NT8

**Not done, and not scheduled above because it needs NinjaTrader time rather than code
time.** Do it when convenient; it does not block M9.

NQ inherits its fill-semantics confidence from MNQ rather than earning it. Everything
downstream of the bars is proven instrument-agnostic — same bars through both specs give
identical trade geometry and gross P&L of exactly ×10 on every leg — so the *simulation*
is not in doubt. What is unverified is whether NT8 itself behaves identically on NQ:
fill semantics, the managed-order cancellation, `IsFillLimitOnTouch`, ambiguous-bar
resolution. There is no reason to expect a difference, which is precisely why an
unexamined assumption could sit there indefinitely.

The recipe, matching how MNQ was done (`docs/nt8-fidelity.md`):

1. Pick one contract with a clean full window — `NQ 03-24` mirrors the MNQ run.
2. Strategy Analyzer → same window, EMA 21 / SMA 60 / SMA 175, all six filters on, zero
   commission, zero slippage.
3. Export **Trades**, not the summary. Summary statistics hide every rule that matters.
4. Compare leg-for-leg against `runner.run_deadcat(..., instrument=NQ)`.
5. Exclude both window ends: NT8 warms indicators from bars before the start, and the
   export can stop before NT8's backtest did.

Expected outcome is agreement at the MNQ level (1143/1144). **A disagreement would be the
interesting result** — it would mean something in NT8 is instrument-dependent in a way the
fidelity record does not capture, and that would be worth knowing before any NQ result is
trusted.

Not scheduled: **M8** (premise measured and mostly false — see `CLAUDE.md`), the three
unbuilt spec features, `NG 02-26`'s silent skip, and the MAE/MFE definition mismatch.

Also unscheduled but now much cheaper: porting **`InsideBar.cs`** and
**`InsideBarTrailing.cs`**. Both are long-capable and ATR-based, so M15 and M16 remove
essentially all of their cost, and both have C# ground truth — which makes them the cheapest
*trustworthy* archetypes available, unlike M18 and M19. `InsideBar` is the structural form of
the squeeze idea and is worth porting before M19 is built from scratch (§M19).
`InsideBarTrailing` is the second consumer of `EXIT_SIGNAL`.

---

## Standing constraint, extended

The prime directive — match NT8's default bar-close fidelity, never exceed it — governs the
**simulation** side only.

The review side takes real fills, which are genuinely tick-precise, and that is not a
fidelity violation because nothing is being simulated. **The trap is letting that precision
leak backwards.** A real trade filled at 18076.75 mid-bar is evidence about the market; it is
not evidence that the simulator should model intrabar fills. Keep the annotation path
read-only with respect to `nqbt/sim/`: the review may *describe* what a real trade did and
compare it against what the simulator would have done, but it must never feed a fill rule
back into the `@njit` loop. If those two ever need reconciling, the trade list wins for
*facts* and NT8 wins for *fill semantics*, and they are different questions.

### An original archetype has no C# to lose to

`CLAUDE.md` says "when the C# and intuition disagree, the C# wins". DeadCatBounce was a
**port**, so that rule always had a referent. EMA crossover and squeeze breakout are
**originals** — there is no NinjaScript, so the rule has nothing to point at. That inverts
the workflow and it needs stating before the first original is written, not after.

- **The prime directive still binds**, in full. It constrains the *simulator* — bar-close
  OHLC fills, no intrabar tick precision — and the simulator is shared by every archetype.
  Nothing about inventing a rule set licenses a more precise fill model for it.
- **For an original, the Python is the specification** and the NinjaScript is written *from*
  it, not the other way round. The reconciliation is unchanged in form: export Trades, diff
  leg-for-leg.
- **Development stays in Python. The port happens on promotion, not on creation.** Decided
  deliberately — see "Decisions taken". An archetype is explored, swept and discarded
  entirely in Python; only one that looks worth trading earns the C# work.
- **So a developing archetype is Tier-1 only, and that has to stay visible.** Today
  "validated against NT8" is a project-wide property, true of the only archetype there is.
  With Python-first originals it becomes a **per-archetype** property, and a sweep table that
  ranks a reconciled archetype against an unreconciled one is comparing a measurement with an
  assumption. M17 records it as a registry field and a results column for exactly this reason.
- **The failure mode is accumulation** — three archetypes, none ever opened in Strategy
  Analyzer, all quietly trusted because the *first* one was. Mitigations: port
  `PullBackAndGo.cs` early so the new long path is proven against real C# while it is cheap
  to fix (M15), and make Tier-1-only status a visible column rather than a remembered caveat.

**The constraint runs the other way too, and this is the non-obvious half.** Writing Python
first means the platform gets no vote until the port, so a strategy can be built that NT8
cannot express — and discovering that after a promising sweep is the expensive order to find
out. The mitigation is to know the platform's limits *before* designing against them, which
is what the "Order lifetime in NT8" section below exists for.

**Expressibility checklist, to be run against a new archetype's design before building it.**
Each item is somewhere NT8's managed approach constrains what a strategy can be:

| question | current answer |
|---|---|
| How long must an entry order rest? | Any lifetime is expressible — see "Order lifetime in NT8" |
| Does it need a true OCO pair? | Only via the unmanaged approach, which costs the whole bracket |
| Does it need to reverse directly from long to short? | Not supported by the simulator either; see M15 |
| Does it hold through the session close? | **It cannot.** Flat before the close is mandatory — see below |
| Does it need more than 4 entries per direction? | `EntriesPerDirection` is a strategy property, not a limit |
| Does it need an indicator NT8 computes differently? | Assume yes until pinned — see M16 |

The list is short because most of it has now been researched. Extend it rather than
rediscovering an item the hard way.

### Flat before the session close is a hard constraint, not a detail

**Every position must be flat before the session close.** This is a prop-firm account rule, so
it is not a preference, a parameter, or something a promising strategy gets to negotiate with.
It also matches NT8, where `DeadCatBounce.cs:54-55` sets `IsExitOnSessionCloseStrategy = true`
with `ExitOnSessionCloseSeconds = 30`, so Tier 1 and Tier 2 agree on it today.

**It is already implemented — do not "add" it.** `sessions.force_flat_mask` produces the
per-bar mask, the `@njit` loop exits everything still open at `EXIT_SESSION_CLOSE`, and
`block_entry_at_session_close` stops a signal firing on a bar that would immediately be
flattened. The maintenance break falls out of the same machinery: sessions are the unit, so no
position can span 17:00–18:00 ET, and none can span the Friday-to-Sunday weekend.

**What it means for design, which is the part worth writing down.** Maximum hold time is
bounded by the session — roughly 23 hours, and in practice far less. Any archetype whose edge
depends on holding overnight or across a weekend is not buildable under these rules, and that
is a design constraint to apply *while* writing the Python, not a discovery to make at port
time. Concretely, for planned work:

- **M15.** A resting entry order must be cancelled at the flatten point, not merely left to
  expire. Already in M15's specification; restated because it is the one cancellation condition
  that applies to every archetype regardless of its own invalidation logic.
- **M13.** The forced-exit share should rise sharply with bar size. At 30-minute bars a
  position opened near the close has almost no bars in which to reach a target, so more of its
  outcomes are decided by the clock than by the rules. Worth measuring alongside the
  ambiguous-bar rate, and for the same reason — both are ways a coarse resolution can look
  different without the strategy being different.
- **M10.4.** The final session phase has *structurally* forced exits, so a time-of-day
  stratification will show it as anomalous. **That is an artefact, not a finding.** Any
  time-of-day result touching the last phase has to separate "this hour trades badly" from
  "this hour's trades were closed by the clock".
- **M18 and M19.** Crossover holds until an opposite cross, so it will hit force-flat often —
  expect the forced-exit share to be a large fraction of its exits. A squeeze rests orders,
  which must be cancelled at the flatten point.
- **Statistics.** The share of exits at `EXIT_SESSION_CLOSE` deserves to be a reported column
  rather than something buried in the trade log. A strategy taking 40% of its exits from the
  clock is not really the strategy its rules describe, and the aggregate profit factor will not
  say so.
- **The prop-account simulator** (`trading_concepts.md` Part II §3.5) treats the daily flat as
  one of the rules it replays, alongside trailing drawdown and the consistency ratio.

**Open question found while writing this: early closes are probably not handled.**
`force_flat_mask` derives its cutoff from the *template's* fixed 17:00 ET close
(`session_end = trading_day + template.close_seconds`), not from the session's observed last
bar. On a holiday half-day — the CME closes early around Thanksgiving, Christmas Eve and
July 3 — the last bar is stamped 13:00 ET, which never reaches the 16:59:30 cutoff, so **the
mask is empty for that session and nothing forces the position flat.** Note the asymmetry:
`is_session_close` *is* data-derived and does handle early closes, so the two disagree
precisely on the days that matter.

If that reading is right, a position opened late on a half-day rides into the next session,
which is exactly what the account rules forbid and what NT8 — whose trading-hours templates
carry the holiday calendar — would not do. Roughly 5–8 sessions a year, so perhaps 30 of ~1,200
in the archive: small, real, and invisible in aggregate statistics.

**Verify before fixing**, and do it as a query rather than by reasoning: group the archive by
trading day, find sessions whose last in-session bar is stamped well before 17:00 ET, and check
whether `force_flat_mask` flags anything on them. If it does not, the fix is to derive the
cutoff from the observed session end rather than the template — but note that changes Tier-1
results on those days, so it needs the usual byte-identity comparison on every *other* day and
a note in the fidelity record. It does not appear to affect the MNQ reconciliation, which is a
December-to-March window, but that should be confirmed rather than assumed.

---

## ~~M9~~ — Split market context from strategy simulation  **(done 2026-08-12)**

**Why.** The review system and the backtester need the same three things: bars, indicator
conditions, and a trade log with statistics over it. Only the middle step — the strategy —
differs. Today the shared parts are physically inside the strategy-specific parts, so
building the review side against the current layout means either importing from `nqbt.sim`
(wrong: the review has no strategy) or reimplementing (wrong: two definitions of "close is
below the EMA" that will drift).

| Concern | Backtest | Review | Status |
|---|---|---|---|
| bars, splicing, sessions | ✓ | ✓ | already shared |
| indicators, condition arrays | ✓ | ✓ | already shared (`conditions.py`) |
| `Dataset` / `prepare` | ✓ | ✓ | **done** — `nqbt/context.py` |
| regime classification | later | ✓ | does not exist |
| relative volume | later | ✓ | does not exist |
| trade-log schema | ✓ produced by `@njit` | ✓ produced by import | **done** — `nqbt/trades.py`, with `validate()` |
| summary statistics | ✓ | ✓ | already shared (`stats.py`) |
| stratification by condition | later | ✓ | does not exist |
| DuckDB persistence | ✓ | ✓ | **done** — `source` and `instrument` tag every row |

**The work.**

1. **Lift `Dataset` and `prepare` out of `nqbt/sim/runner.py` into `nqbt/context.py`.**
   Nothing about them is DeadCatBounce-specific; `deadcat_signal` and `run_deadcat` stay
   behind in `sim/`. Keep the class name `Dataset` rather than renaming to `MarketContext` —
   the churn buys nothing and the name is already referenced across the docs and the fidelity
   record.

2. **Formalise the trade-log schema in `nqbt/trades.py`,** extracted from
   `sim/types.COLUMNS`. This is the contract both producers meet. Three additions are
   required, because the current schema quietly assumes it came from DeadCatBounce:

   - **`direction`** (+1 long / −1 short). Currently implicit: the archetype is short-only, so
     nothing records it. A manual log has both, and every P&L and MAE/MFE sign convention
     downstream depends on it.
   - **`instrument`**. A real trading history spans NQ and MNQ, whose tick values differ 10×.
     A trade log without this cannot be summed in dollars — and `instruments.py` exists
     precisely because that bug has bitten before.
   - **`source`** (`sim` / `manual`). Real and simulated trades will share a DuckDB table;
     without a tag, one careless query averages them together.

   Fields the simulator produces that a manual trade cannot — `ambiguous_bar`, `r_multiple`
   when no stop was recorded, `mae_points`/`mfe_points` until they are reconstructed from
   bars — become explicitly nullable, with the nullability documented rather than discovered.

3. **Add `trades.validate(frame)`** and call it at both producers' boundaries. A schema that
   is only a convention will drift the first time someone adds a column.

4. **Enforce the dependency rule:** `context.py` knows nothing about trades; `sim/` and the
   trade importer both depend on `context.py`; `stats.py` and the review layer depend on the
   trade schema and nothing else. Concretely: **`stats.py` must not import from `nqbt.sim`.**
   It currently doesn't — this makes that a rule instead of an accident.

**Risk.** This moves validated code. The NT8 reconciliation (1143/1144) is the thing being
protected, so: no behaviour changes in the same commit as the moves, and the full suite plus
a re-run of the reconciliation window before and after, compared byte-for-byte.

### What actually happened, and the three things worth keeping

**The verification worked exactly as designed and is the template for M15.** It is now
`tools/capture_trade_logs.py` and `tools/compare_trade_logs.py` rather than a throwaway,
because M15's gate is the same shape and strictly stronger. Four producer
paths are captured to CSV before touching anything — the pinned MNQ 03-24 reconciliation
window under `fill_limit_on_touch=True, ambiguity_policy=0`, a costed run, the same bars
through the NQ spec, and an 8-combination sweep run both serially and in parallel. The moves
alone reproduced **all 14 files byte-for-byte**; the schema commit left **every pre-existing
column identical**, dtypes included, adding only `source`, `instrument` and `direction`.
**One thing the harness got wrong at first, and it matters for M15.** Pandas' default CSV
writer is *not* round-trip exact for float64 — writing and re-reading a real trade log moves
4 of 1,664 `r_multiple` values by one ULP. A byte-identity gate written in the default format
is therefore comparing text-rounded numbers, and can miss a sub-ULP difference: exactly the
class of error a wrong sign or a changed order of operations produces, which is the entire
thing M15's gate exists to catch. The capture tool now writes `float_format="%.17g"`, which
round-trips float64 exactly, and the gate is verified to fail on a deliberate one-ULP
perturbation. **Do not relax that back to the default for readability.**

**1. `validate()` is in a hot loop, and the obvious implementation costs 9.4%.**
`run_deadcat` is called once per combination, so the schema check is too. Written the
natural way — `frame[REQUIRED].isna().sum()` plus `Series.isin` — it cost **9.4% of a
sweep**, which is the wrong direction in a sweep whose bottleneck is already pandas (`M8`).
Short-circuiting each check, skipping the null scan on integer columns (they cannot hold
one), and using `unique()` over `isin()` brought it to **1.3%**. That is a fair permanent
price for catching an M15 sign error on every combination instead of never.

*The measurement trap:* `Series.hasnans` is a **cached property**. Timing `validate` against
one frame in a loop says 0.5 ms and means nothing, because every call after the first is
free. Only an A/B of the whole sweep, where each combination validates a frame it has just
built, gives a real number. The first attempt here read 2.6× too fast.

**2. Import-analysis tests are vacuous by default.** The rule "`stats.py` must not import
from `nqbt.sim`" was implemented by walking the AST and prefix-matching module names — and
it passed happily with `from nqbt import sim` inserted into `stats.py`, because
`ast.ImportFrom.module` is `"nqbt"` and the names are in `node.names`. Every layering test
was checking nothing for the one import form most likely to be used. `imports_of` now
records both the package and `package.name` for each alias, and
`test_the_import_analysis_sees_both_forms_of_import` guards the guard. **Mutation-test any
test that asserts an absence**: it was written, passed, and was wrong, and only deliberately
breaking the code it protects exposed that.

**3. `direction` is a constant, deliberately.** The `@njit` loop writes `SHORT` at
`C_DIRECTION` on every row. That is not a placeholder to be tidied away — it is the column
M15 fills with its sign `d`, sitting in the matrix and in the schema so that adding
bidirectionality changes one write rather than the layout, the frame builder, the DuckDB
schema and the tests at the same time.

**Also landed, out of scope but adjacent.** `results.save_trades` inserted with
`INSERT INTO trades SELECT *` and no column alignment, so the three new columns would have
shifted every value one place to the right in an existing table — reading as a result rather
than as an error. `save_sweep` already guarded `combos` against this; both now go through
`_append_or_create`, which writes **by name, not by position**. M17 adds nullable
`strategy`/`resolution`/`contract` columns to these tables, so this had to be right first.

---

## M20 — Code quality: a standing review, and the debt it has already found

**Why now, and not later.** The codebase is about to roughly triple in surface: M15 makes
every comparison in the simulation bidirectional, M16 adds four indicators, M17 adds three
axes above the `Dataset`, M18 and M19 add archetypes. Every one of those multiplies whatever
structure exists today. Two things follow. The **fidelity evidence lives in code**, so a
duplicated fill rule is a duplicated place for Tier 1 and Tier 2 to disagree — and the
reconciliation only ever covered one copy. And the review is **cheapest before the
multiplication**, because a rule fixed once now is a rule not re-broken four times.

This section is both a **standing rubric** — what every change is checked against — and the
**specific debt an actual pass over the code found**. The findings below were measured
against the real MNQ archive rather than inferred from reading, and each carries the evidence
and the line it sits on. Line references were current at the time of writing; re-check them
rather than trusting them, since the code they point at is scheduled to move.

### What the review found

| # | Finding | Evidence | Severity |
|---|---|---|---|
| 1 | `explain.py` computes the entry trigger as `Low[0]`, omitting the `Close[0] − 2 ticks` cap the simulation applies | `risk_points` disagrees with the trade log on **100 of 200 trades (50%)** on MNQ 03-24 | **High** — this is the NT8 audit trail |
| 2 | `stats.summarise` raises `TypeError` on an empty trade log | `Summary` has 28 fields; the empty guard supplies 26 | **Medium** — latent |
| 3 | The bracket-resolution logic in `simulate_deadcat` is duplicated between the in-position branch and the entry-bar branch | ~85 near-identical lines, `deadcat.py:144–227` against `262–342` | **High** — directly obstructs M15 |
| 4 | `simulate_deadcat` takes 23 positional parameters, `_write` takes 18 | 8 call sites, all positional | Medium |
| 5 | 47 bare `np.ndarray` annotations carry no dtype | zero uses of `numpy.typing.NDArray` in the package | Medium |
| 6 | No type checker, no linter, no CI, no `py.typed` | `pyproject.toml` configures pytest and nothing else | Medium |
| 7 | `explain.py` and `cli.py` have no tests | no test file imports either | Medium — explains finding 1 |
| 8 | `sweep.SWEEPABLE` reads `DeadCatParams.__slots__` | `sweep.py:36` | Low now, **blocks M17** |
| 9 | `results.best()` interpolates its `by` argument into SQL | `results.py:182` | Low |
| 10 | `bars[...].to_numpy(np.float64)` repeated 12 times across `conditions.py` and `context.py` | grep | Low |

---

### M20a — the three that block M15, and must land before it

**1. `explain.py` disagrees with the simulation on half of all trades.**

`nqbt run --explain N` is described in `CLAUDE.md` as "the NT8 audit trail" and it "earns its
keep". It is the tool a human uses to tick a trade off against a chart before trusting
anything downstream. It recomputes the order arithmetic **independently of `deadcat.py`**,
and it gets it wrong:

```python
# nqbt/sim/explain.py                    # nqbt/sim/deadcat.py
trigger = l                              trigger = low[i]
                                         close_based = close[i] - entry_offset
                                         if close_based < trigger:
                                             trigger = close_based
```

The missing branch is the single gotcha `CLAUDE.md` lists first: *"The trigger is
`min(Low[0], Close[0] − 2 ticks)`, not the bar's low. Binds on ~⅓ of signals."* Measured
against the trade log it binds on **50%** of trades, and `trigger`, `risk_points`,
`risk_ticks` and `fill_type` are all wrong on those. `initial_stop` is correct, which is
what makes it plausible on inspection.

**Why this is the highest-severity item.** M15's validation plan is to port
`PullBackAndGo.cs` and hand-check the long side. Hand-checking is done with this tool. A
verification instrument that is wrong half the time does not fail loudly — it agrees with
the chart on the stop, disagrees on the risk, and invites the reader to conclude the
*simulation* is wrong. Also check `verification/explain_2024Q1.csv`, which was produced by
this code and is kept as an artefact.

**The fix is not to patch the arithmetic — it is to stop having two of it.** Patching
reproduces the bug's cause. Extract the trigger/stop/risk computation from the loop into one
`@njit` helper that both `deadcat.py` and `explain.py` call, so the audit trail is *by
construction* the arithmetic under audit. Then add the test that would have caught it:
`explain_trades`' `trigger`, `initial_stop` and `risk_points` must equal the trade log's on
every trade, not a sampled few.

**2. `stats.summarise` cannot summarise an empty log.**

```python
if trades.empty:
    return Summary(*([0] * 5 + [0.0] * 20 + [0]))  # pragma: no cover - guarded below
```

26 positional arguments into a 28-field dataclass. The `pragma` comment is also wrong about
*where* the guard is: nothing below guards it, the caller does (`sweep.run_combination`
checks `trades.empty` first and builds a zero dict itself). So there are two empty-log
policies, one of which has never run and does not work.

Fix with a `Summary.empty()` classmethod built from `fields(cls)` rather than a positional
splat, and have `run_combination` call it instead of hand-rolling `{c: 0 for c in
columns()}`. **This is a prerequisite for the numpy-native summary path** (order-of-work
step 6): that work adds a second `Summary` producer which must agree with this one exactly,
and "exactly" cannot include a constructor that raises.

**3. The bracket machinery is already forked — and M15 assumes it is not.**

M15's design section says, correctly:

> Forking the loop into a long copy and a short copy is the tempting alternative and it is
> wrong for a specific reason: **the bracket machinery carries the fidelity evidence.**

The problem is that inside `simulate_deadcat` it is *already forked*. `deadcat.py:144–227`
resolves stop / targets / ambiguity / force-flat for a bar while in a position;
`deadcat.py:262–342` does the same thing again for the bar the entry filled on. They are
behaviourally equivalent — the entry-bar copy omits the `leg_open[leg]` guards because every
leg was just opened — but they are textually independent, and every fidelity rule the
1143/1144 reconciliation validated appears twice.

**M15 must change every one of those lines to carry `d`.** Against two copies that is two
chances to get a sign wrong, in the one function where a wrong sign is hardest to see. The
short-only byte-identity gate does **not** protect against this: at `d = −1` both copies
reduce to today's code whether or not they agree at `d = +1`.

So: **unify the two copies first, prove byte-identity, then apply `d` once.** Two commits,
the same shape as M9's split, with the same evidence. The extraction is one `@njit` helper
taking the leg arrays and the bar; the entry-bar path calls it after opening the legs.

Note this is the same extraction M17 defers — *"the shared bracket engine is extracted
**during** M18 — before is designing from one example, after means duplicated
fidelity-critical code shipped."* That reasoning stands for the cross-archetype engine. It
does not apply here: this is not designing an abstraction across archetypes, it is deleting
a copy inside one function, and it is worth doing now because M15 is what makes the copy
expensive.

---

### M20b — typing: annotations are not verification

The package annotates well — only 5 functions have an untyped parameter and only 2 lack a
return type — but **nothing checks any of it**, so the annotations are documentation that
happens to be in the type position. `pyproject.toml` configures pytest and nothing else.

**The gap that matters is dtype, not coverage.** There are 47 bare `np.ndarray`
annotations and zero uses of `numpy.typing.NDArray`. In this codebase the element type is
load-bearing in a way that is invisible today:

- `MovingAverageGrid.below` is `bool`, `.values` is `float64` — the whole 66 MB vs 595 MB
  decision is that distinction, and both are annotated `np.ndarray`.
- `SessionInfo.trading_day` is `datetime64[D]`, `.in_session` is `bool` — both `np.ndarray`.
- The `@njit` loop's `out` is a `float64` matrix into which `exit_reason` and `direction` are
  written as floats and mapped back to strings later — the one place a wrong dtype is
  silently lossy.

`NDArray[np.float64]` vs `NDArray[np.bool_]` in the signatures is a real check, not
decoration.

**Do it in this order, and stop where the cost exceeds the value:**

1. Add `mypy` (or `pyright`) to the dev extras and a config in `pyproject.toml`. Start at the
   project's own modules only, with third-party stubs ignored — pandas and Numba types are
   not worth fighting on day one.
2. Add `py.typed`.
3. Replace `np.ndarray` with dtype-parameterised `NDArray` aliases. Define them once
   (`FloatArray`, `BoolArray`, `IntArray`) rather than spelling `NDArray[np.float64]` 47
   times — that is the same extract-and-reuse rule applied to types.
4. Close the 5 untyped parameters: `moving_average_grid(periods)`,
   `context.prepare(ema_periods, sma_periods)` (all three are `Iterable[int]`),
   `splice_root`/`load_continuous` (`Path`), `results._jsonable` (needs `Any` and should say
   so).
5. Add a linter — `ruff` covers the unused-import and unused-variable class of finding that
   this review had to write an `ast` script to detect.
6. **Only then** consider making the type check a gate. A check nobody can pass is deleted.

**Do not annotate inside the `@njit` functions expecting Numba to use it.** Numba infers from
the call, ignores the annotations, and a wrong one there is worse than none because it reads
as a guarantee.

---

### M20c — structural, worth doing when adjacent rather than as a project

**Parameter blobs → `NamedTuple`, and this is verified to be free.** `simulate_deadcat` takes
23 parameters and `_write` takes 18, all passed positionally at 8 call sites; one
transposition writes plausible numbers into the wrong columns. The obvious grouping is
`Costs(tick_size, point_value, commission, slippage)` and `Rules(...)`.

The question was whether Numba tolerates it. **Measured:** a `NamedTuple` parameter gives a
bit-identical result, runs at 1.01× the scalar version over 5M iterations, and
`@njit(cache=True)` still compiles — which matters because the disk cache is what makes
parallel workers cheap. The probe is
`tools/numba_tuple_probe.py`; re-run it before relying on this, as it is a Numba-version
property rather than a language guarantee.

**Where classes are already right, and where they are not.** The codebase uses dataclasses
well — `Dataset`, `MovingAverageGrid`, `BarGeometry`, `SessionInfo`, `Summary`, `Instrument`,
`ContractId` are all doing real work, and `slots=True` is used consistently. The gaps are the
parameter blobs above and the archetype protocol M17 already covers. **Resist adding classes
beyond that**, and specifically resist `numba.jitclass` inside the loop: it carries real
compilation and boxing costs, and the loop is 23% of a combination, so there is nothing to
win and fidelity-critical code to lose.

**The rest, in descending order of value:**

- **`sweep.SWEEPABLE` reads `DeadCatParams.__slots__`.** Use `dataclasses.fields()`. `__slots__`
  is an implementation detail that silently excludes inherited fields, and M17 makes strategy
  parameters polymorphic — this breaks then, quietly, by dropping an axis rather than raising.
- **`results.best()` interpolates `by` into SQL** (`ORDER BY {by}`). A local research tool, so
  not a security finding, but a typo yields a DuckDB parse error rather than "unknown column";
  validate against `Summary.columns()`.
- **`bars[...].to_numpy(np.float64)` appears 12 times.** One `ohlcv(bars)` helper returning the
  four arrays removes the repetition and gives one place to enforce the dtype.
- **`explain.py` and `cli.py` are untested.** Finding 1 is the direct cost of the first. `cli.py`
  needs only smoke tests — it is thin by design — but "thin by design" is a claim that should
  fail loudly when it stops being true.
- **`_cmd_run` is 76 lines mixing computation with 16 `print` calls**, and the computation is
  `stats` reimplemented inline: `per_trade`, profit factor and max drawdown all have a **second
  independent definition** there (`cli.py:109–115` against `stats.py:70`, `81`, `106`). They
  agree today, and the profit-factor pair already differs in a corner — `_ratio` returns `0.0`
  for no-wins-no-losses where `cli` returns `inf`. This is rubric item 1 in its cheapest form:
  call `stats.summarise` and print its fields.

---

### The standing rubric

What every change — including every milestone below — is checked against. These are ordered
by how much trouble each has actually caused in this codebase, not by general principle.

1. **Is there now more than one definition of the same rule?** The most expensive defects here
   are all this: two triggers (finding 1), two empty-log policies (finding 2), two bracket
   engines (finding 3), and a third profit factor in `cli.py`. In a project whose premise is
   *matching an external system exactly*, a duplicated rule is a duplicated place to diverge
   from it.
2. **Does the type say what the array actually holds?** `np.ndarray` does not distinguish the
   bool grid from the float grid, and that distinction is load-bearing.
3. **Is the expensive work outside the loop?** Already a convention (`CLAUDE.md`), and the
   measurement discipline behind it is the strongest habit in the project — keep requiring the
   number, not the argument. Note M9 found a 9.4% regression this way that reasoning alone
   would have shipped.
4. **Would this pass if the code were wrong?** Applies hardest to tests asserting an absence.
   M9's layering tests were written, passed, and checked nothing. Mutation-test them.
5. **Is a class earning its place, or is it a namespace?** Prefer a dataclass with `slots=True`
   for a group of values that travel together; prefer a function for behaviour that does not
   need state. Do not introduce a class hierarchy to express one archetype.
6. **Is the abstraction extracted from two examples or invented from one?** M17 gets this right
   about the bracket engine. M20a's finding 3 is the opposite case — deleting a copy, not
   inventing a shape.
7. **Does the docstring say why, not what?** Already the house style and the reason this
   codebase is navigable. The bar for new code is the existing bar.

### Traps

- **Do not "fix" `explain.py` by copying the two-line branch across.** That is what created the
  bug. One implementation, called twice.
- **The short-only byte-identity gate does not cover the bracket unification.** Both copies
  reduce to today's behaviour at `d = −1` regardless of whether they agree at `d = +1`.
  Unify *before* introducing `d`, and gate the unification on byte-identity separately.
- **`# pragma: no cover` marks code that is never run, which is exactly where a defect can sit
  indefinitely.** Finding 2 sat behind one. Audit the others rather than trusting the comment
  — a pragma is a claim about coverage, not about correctness.
- **A type checker introduced with a strict config and 400 errors gets switched off.** Start
  permissive on the project's own modules and tighten; do not gate CI on it in the same change
  that introduces it.
- **Re-measure the Numba `NamedTuple` result before relying on it.** It is a property of the
  installed Numba, not of the language, and `cache=True` interacts with it.
- **None of this changes a number.** Every item here is behaviour-preserving except finding 1,
  which changes only the audit trail's reported `trigger`/`risk_points`/`fill_type` and no
  simulated P&L. Anything that moves a trade log is out of scope for M20 and belongs in the
  milestone that intends it.

---

## M15 — Direction: making the simulator bidirectional

**This is the blocker, and it is not a strategy feature.** EMA crossover, squeeze breakout,
and all three unported NinjaScripts are long-capable. `simulate_deadcat` is short-only, and
not by a flag — direction is baked into roughly eight places:

| line of reasoning | short form today |
|---|---|
| stop hit | `high[i] >= stop` |
| target fill | `_limit_filled(low[i], …)` — a *buy* limit below entry |
| P&L | `gross = (entry_price - exit_price) * qty * point_value` |
| MAE / MFE | `run_high - entry`, `entry - run_low` |
| entry trigger | `min(low[i], close[i] - entry_offset)` |
| entry fill test | `open_[i] <= trigger`, `low[i] <= trigger` |
| ratchet | `if new_stop < stop` — tightens downward only |
| slippage sign | `trigger - slippage` on entry, `stop + slippage` on exit |

### The design: one sign, not two code paths

Carry `d = +1.0` long / `−1.0` short and express every comparison through it. Forking the
loop into a long copy and a short copy is the tempting alternative and it is wrong for a
specific reason: **the bracket machinery carries the fidelity evidence.** The ambiguous-bar
rule, `IsFillLimitOnTouch`, the ratchet and the force-flat path are what the 1143/1144
reconciliation actually validated. Two copies means two places for Tier 1 and Tier 2 to
drift, and the reconciliation only ever covered one of them.

| quantity | generalised form | check at `d = −1` |
|---|---|---|
| risk | `d * (trigger − stop)` | `stop − trigger` ✓ |
| leg target | `trigger + d * risk * R * tp_mult` | `trigger − risk·R·tp` ✓ |
| stop hit | `d * adverse <= d * stop`, adverse = `low` long / `high` short | `high >= stop` ✓ |
| entry fill | `d * open_[i] >= d * trigger`, else `d * favourable >= d * trigger` | `open <= trigger` ✓ |
| entry slippage | `trigger + d * slippage` | `trigger − slippage` ✓ |
| exit slippage | `stop − d * slippage` | `stop + slippage` ✓ |
| ratchet | tighten when `d * new_stop > d * stop` | `new_stop < stop` ✓ |
| gross P&L | `(exit − entry) * d * qty * point_value` | `(entry − exit)·qty·pv` ✓ |
| MAE / MFE | `d * (entry − adverse)`, `d * (favourable − entry)` | `run_high − entry` ✓ |

**`_targets_reached_first` needs no change and must not be given one.** It compares
`abs(open − target) < abs(stop − open)` — pure distance from the open, already
direction-free. Someone will eventually "fix" it to take a sign; the test that stops them is
asserting a long and a short bar with mirrored geometry resolve the same way.

### The regression gate is exact equality, not "close enough"

Multiplying by ±1.0 is exact in IEEE 754, and `fl(a − b) = −fl(b − a)` always. Every
substitution in the table above therefore preserves the *bit pattern* of every short result,
provided `d` multiplies rather than branches. So the gate for this refactor is not "the
reconciliation still passes" — it is **every short-only trade log byte-identical before and
after**, which is a far stronger and much cheaper check. If a single float moves, the
generalisation is wrong somewhere and the table above says where to look.

### Two additions the loop does not have

1. **`EXIT_SIGNAL = 4.0`.** Every exit today is stop, target, ratchet, force-flat or
   end-of-data. A rule-driven exit — "close when the MAs cross back" — has no
   representation. EMA crossover needs it and so does `InsideBarTrailing.cs`, which is why
   it belongs here rather than in M18. Additive to `EXIT_REASONS`; `results.py` stores the
   string, so no migration.
2. **`direction` on the trade record** — **already there.** M9 added the column and the
   loop writes the constant `SHORT` at `C_DIRECTION`. M15's job is to replace that one
   write with `d`; the matrix layout, the frame builder, `validate()`'s
   `direction ∈ {+1, −1}` check and the DuckDB schema all already accommodate a long row.
   The regression gate therefore also covers this column for free: if `d` is wrong anywhere,
   the short-only byte-identity check fails on `direction` before it fails on P&L.

**Explicitly not supported: stop-and-reverse.** `in_position` is a boolean and the loop
assumes flat-to-flat. Reversing means exiting and entering on the same bar, which collides
with the one-bar entry lifetime and with the same-bar stop-out path. **Decide now that
archetypes are flat between trades**, and treat reversal as a separate feature with its own
reconciliation if it is ever wanted. Retro-fitting it into a loop that assumes flatness is
how a position-tracking bug gets introduced somewhere the tests do not look.

### Validation: port `PullBackAndGo.cs`

`PullBackAndGo.cs` is long-only and enters with `EnterLongStopMarket` — the exact mirror of
DeadCatBounce's entry mechanism on the other side. It is therefore the cheapest possible
proof that the long path is right, and unlike EMA crossover it has **C# to lose to** and can
be reconciled against a real NT8 trade list.

Sequence: generalise, prove short-side byte-identity, port PullBackAndGo, reconcile it
against NT8, *then* build anything original. A long-side fill-semantics bug found here is
found against ground truth; found later it is indistinguishable from the new strategy being
bad.

---

## M16 — The indicator-parity debt: ATR, StdDev, Bollinger, Keltner

`indicators.py` says it plainly: "TA-Lib is still the right tool for MACD, RSI, Bollinger
Bands and ATR, which no archetype uses yet. Those carry their own NT8 discrepancies and will
need the same treatment when an archetype first depends on one." **Squeeze breakout is that
moment**, and it is not the only consumer.

**Five consumers, which is why this is its own milestone and not a squeeze detail:**

1. Keltner Channels for the squeeze (M19) — ATR is the channel width.
2. `InsideBar.cs`, `InsideBarTrailing.cs`, `PullBackAndGo.cs` — all three call `ATR()`.
3. EMA crossover's stop rule (M18), which has no structural swing to anchor to.
4. ATR-multiple brackets, already recorded as unscheduled in "Related items".
5. `trading_concepts` Part II §3.2's compression classifiers — Bollinger bandwidth and range ÷ ATR — one
   of which is the cheap form of the squeeze itself.

### Expect exactly the EMA bug again

The EMA discrepancy was **seeding**, not formula: TA-Lib warms up with a simple average and
emits nothing before index `period-1`; NT8 seeds from bar 0 and emits from bar 0. ATR is the
same shape of problem — Wilder smoothing is a recursion with a seed, and the seed is where
implementations diverge. `nt8_sma` already reproduces NT8's *partial-window* warm-up for the
same reason.

So: hand-roll each one against NT8's recursion, pin it with a unit test against values read
off an NT8 chart, and do not assume the formula — **read it out of NT8 and record the
evidence in `docs/nt8-fidelity.md`** the way `nt8_ema` and `nt8_sma` were. The specific
questions to settle, none of which should be answered from memory:

- **ATR:** what is `Value[0]`, and is the recursion `(prior·(n−1) + TR) / n`? Does it emit
  before `n` bars, and if so what is it averaging?
- **StdDev:** population divisor `n` or sample `n−1`, and does it use the same expanding
  partial window `nt8_sma` does?
- **Bollinger:** which mean does NT8 centre on, and does the band use that same StdDev?
- **Keltner:** NT8's midline and width are *not* universally agreed on between platforms —
  some use an SMA of typical price, some an EMA of close, and the multiplier may apply to
  ATR or to a mean deviation. This is the one most likely to be silently wrong.

### True Range crosses session and roll boundaries

TR reads the *previous* close, so two boundaries need a decision rather than a default:

- **The 17:00–18:00 ET maintenance break.** The prior close is an hour old. NT8 does not
  reset TR at a session boundary under a continuous `Bars` object, so matching it probably
  means not resetting either — but that is a claim to verify, not assume.
- **Roll boundaries on the spliced series.** Back-adjustment makes the gap small but not
  zero, so ATR will step at each of the 18 rolls. Same family as M10.2's note that absolute
  volume steps there too. Do not read it as a volatility event, and prefer per-contract runs
  (M14) when an ATR-sensitive rule is being judged.

### Memory: these grids are two-dimensional, not one

`MovingAverageGrid` is `[n_periods, n_bars]`. Bollinger and Keltner are swept over **period
*and* multiplier**, so the natural grid is `[n_periods, n_multipliers, n_bars]` and the 66 MB
→ 595 MB lesson applies with an extra factor. Keep the same discipline: **store the boolean
gate, not the values**, unless something explicitly needs the level. A squeeze gate is a
boolean ("bands inside channels"), so the default case is cheap — but only if it is built
that way from the start.

---

## M17 — The archetype protocol, built with M13 and M14 as one mechanism

Adding a second archetype today means forking `sweep.py`. Everything in it is hardcoded to
`DeadCatParams`:

| what | where |
|---|---|
| `SWEEPABLE = {f for f in DeadCatParams.__slots__} - {…}` | `sweep.py:36` |
| `Grid.base: DeadCatParams` | `sweep.py:52` |
| `_GATED_BY` — DeadCatBounce's toggle map | `sweep.py:74` |
| `required_periods()` returning exactly `(ema, sma)` | `sweep.py:115` |
| `run_combination` calling `runner.run_deadcat` by name | `sweep.py:137` |
| `prepare()` computing geometry, VWAP and both MA grids unconditionally | `runner.py:59` |

The build spec already anticipated this: *"one Numba-jitted simulation function per strategy
archetype … Different parameter values of the same logic reuse the same function; genuinely
different entry logic gets its own function."* That is the right split — the argument in M15
is that the *bracket* half stays shared while the *entry* half forks.

### Strategy is the third axis above the `Dataset`

M14 already records that it and M13 are "architecturally the same feature — both add an axis
that sits *above* the `Dataset` rather than inside `DeadCatParams`, both need one `Dataset`
per value, and both need a nullable column in the results schema." **Strategy is a third
instance of exactly that pattern**, and it arrived last only by accident of when it was
asked for.

So build one mechanism covering all three, not three wrappers that diverge:

```python
sweep.sweep_axes(bars, grid, strategies=[...], resolutions=[1, 5, 15], contracts=[...])
```

with `strategy`, `resolution` and `contract` all landing in `save_sweep` together, all
nullable (`contract` null meaning "spliced series"). **Do this before the stale DuckDB
re-run**, which is already the plan for M13/M14 and is now worth more, because otherwise the
schema settles three times.

### The protocol, kept minimal

```python
class Archetype(Protocol):
    name: str                      # the results column, and the registry key
    params_cls: type               # replaces DeadCatParams in Grid
    sweepable: frozenset[str]      # replaces the __slots__ scrape
    gated_by: dict[str, str]       # replaces _GATED_BY; keeps dead_axes() working
    tier2: Tier2Status             # reconciled / tier-1-only / not-checked

    def required_context(self, grid) -> ContextSpec: ...
    def run(self, data, params, instrument) -> pd.DataFrame: ...
```

`Grid.dead_axes()` is the piece worth preserving rather than reinventing — it is the guard
that stops a swept period whose toggle is off everywhere multiplying runtime for nothing, and
every archetype will have its own version of that mistake available.

**`tier2` is not bookkeeping.** Per the standing-constraint section above, "validated against
NT8" stops being a project-wide fact once originals exist. Putting the status on the
archetype and into the results table is what stops a ranking silently mixing a measurement
with an assumption.

### `prepare` must stop computing everything

Today `prepare` unconditionally builds bar geometry, session VWAP and both MA grids — fine
for one archetype, wrong for four. With M16's Bollinger/Keltner grids and M10's regime,
volume and time-of-day labels added, every sweep would pay for every archetype's needs and
the `Dataset` would balloon well past the 121 MB that `slim()` exists to manage.

`required_context(grid)` returning a declared spec — which MA kinds and periods, whether
VWAP is needed, which channel grids — is the fix, and it is **load-bearing at M10 regardless
of how many archetypes exist**. Doing it here is therefore free rather than speculative.

### The extraction is timed, deliberately

Pulling a shared bracket engine out of `deadcat.py` *before* a second archetype exists is
designing an abstraction from one example. Pulling it out *after* two land means the
duplicated fidelity-critical code sat on `main` in the meantime. Neither is right, so:

**extract during M18, in its own commit, with byte-identity as the gate.** Copy to get EMA
crossover working, then factor the common half into `nqbt/sim/bracket.py` as `@njit` device
functions — Numba inlines those at no cost — with the DeadCatBounce trade log required to
come back byte-identical. The abstraction is then designed against two real shapes and the
duplication never ships.

---

## M18 — EMA crossover

The first original archetype, and the one chosen to prove M15 and M17 because it is the
cheapest thing that exercises both: it is bidirectional and it exits on a signal rather than
a bracket level.

### Be honest about what this is for

**MA crossover on 1-minute index futures is the most-tested idea in retail futures and is
reliably unprofitable at realistic costs.** That is not a reason to skip it — it is the
reason it is a good first original. It serves three purposes, none of which is "find edge":

1. **A protocol test.** If `sweep_axes` can run DeadCatBounce and crossover side by side and
   tag both correctly, M17 works.
2. **A known-negative control.** Paired with M7a's random-entry arm, crossover should read
   as *no better than random*. If it reads meaningfully better, the first hypothesis is a
   **bug, not an edge** — and specifically lookahead, since crossover is unusually easy to
   compute one bar early.
3. **It exercises `EXIT_SIGNAL`,** which nothing else does until `InsideBarTrailing.cs`.

Recording this now matters because a PF above 1 on a crossover sweep will otherwise be
exciting rather than suspicious.

### Rules to fix explicitly, because the defaults are all wrong

- **Cross semantics.** NT8's `CrossAbove(a, b, n)` asks whether `a` crossed above `b` *within
  the last n bars*, not on this bar. The naive `fast[i] > slow[i] and fast[i-1] <= slow[i-1]`
  is a **different rule** and will disagree with any NinjaScript written later. Pick NT8's
  form, with `n` as a swept axis. Equality on the prior bar is a real edge case for SMAs on
  tick-grid prices even though it is vanishingly unlikely for EMAs.
- **A third entry mechanism.** DeadCatBounce rests a stop-market for one bar; the squeeze
  rests one until the range breaks; crossover enters **market-on-next-open**. There is no
  trigger price and no "no touch, no fill" — the fill is `open[i+1] + d·slippage` and it is
  unconditional. The loop's `pending_trigger` machinery does not apply, which is precisely
  why this is a good test of whether M17's split is in the right place.
- **The stop has nothing to anchor to.** DeadCatBounce's stop is the signal bar's high plus
  two ticks — structural, and meaningless for a crossover where there is no signal wick.
  Use an **ATR multiple** (M16), which makes M16 a hard prerequisite rather than a
  convenience, and keep the swing-high mode available as an alternative axis.
- **`target_r_multiples` still works but changes meaning.** R is `stop − trigger`, so with an
  ATR stop the four-leg scale-out becomes ATR-scaled rather than structure-scaled. Fine, but
  it means crossover results are not comparable to DeadCatBounce results at the same R
  numbers — the same trap M13 records for comparing profit factor across resolutions.
- **Flat between trades, not stop-and-reverse** — per M15. The classic form reverses; this
  one will not, and that difference must be in the results notes or the comparison to
  published crossover results is meaningless.

### It will break the sweep's performance assumptions

DeadCatBounce produces ~1,400 legs over 1.65M bars because six filters conjoin down to a rare
signal. A crossover fires **whenever two lines cross**, which on 1-minute bars is tens of
thousands of trades per combination.

Two consequences, both of which are why the numpy-native summary path moved up the order:

- The M8 profiling result — `stats.summarise` 51%, `trades_to_frame` 20%, the `@njit` loop
  23% — is measured at DeadCatBounce's trade count. At 30× the legs, the pandas share grows
  and the loop's share shrinks further. **The 71% overhead becomes the entire sweep.**
- `allocate_output`'s `n_signals × n_legs` bound stays correct but stops being cheap: a
  permissive crossover grid allocates a matrix orders of magnitude larger, per worker, and
  the parallel path memmaps the `Dataset` but not the output buffer.

Do a single-combination timing before running a wide crossover grid, rather than discovering
this as a stalled sweep.

---

## M19 — Squeeze breakout

Queued rather than scheduled. It is the more interesting of the two requested archetypes and
also the more expensive, because it needs an entry model the loop does not have.

### Fix the definition first — "squeeze" means at least three things

| form | compression measure | cost |
|---|---|---|
| **TTM-style** | Bollinger(20, 2) sitting *inside* Keltner(20, 1.5·ATR); fires when they expand back outside | Needs BB **and** KC — the full M16 debt, Keltner included |
| **Bandwidth** | `(upper − lower) / mid` below a trailing percentile | Needs BB only. `trading_concepts` Part II §3.2 lists it as the cheap compression classifier |
| **Structural** | An inside bar, or *k* consecutive inside bars | No new indicators at all — and `InsideBar.cs` already implements it, **with C# ground truth** |

**Recommendation: build the bandwidth form first.** It is one indicator rather than three, it
drops the Keltner parity question — flagged in M16 as the one most likely to be silently
wrong — and it is the same quantity the regime classifier wants anyway, so M10.1 and M19
share it instead of each inventing one. Promote to TTM only if bandwidth shows something.

**And port `InsideBar.cs` before either.** It is structurally the same idea — compression,
then a break of the range — it needs no new indicator work beyond ATR, and it is the only
version of this strategy that can be reconciled against NT8. It is the cheapest way to find
out whether compression-then-break is worth pursuing at all before paying for BB or KC.

### The real cost: two resting orders, not one

The squeeze is **directionless**; the break supplies the direction. So the natural entry is a
stop-market resting on *both* sides of the compression range, first fill cancelling the
other — an OCO pair. The loop tracks a single `pending_bar` / `pending_trigger` /
`pending_stop`. This is a genuine addition to the entry model and the main structural cost of
the archetype, which is why it sits behind M18 rather than beside it.

### Traps

- **Order lifetime — researched, and no longer a blocker.** The design wants the orders
  resting until the squeeze resolves, which the one-bar managed expiry appeared to forbid.
  It does not: the expiry is an unset `isLiveUntilCancelled` parameter, not a platform rule,
  and every lifetime is expressible. See "Order lifetime in NT8" above for the three routes
  and their costs. The live question is now **whether a native OCO pair is needed** — that
  one costs the unmanaged rewrite — or whether resubmitting each bar is enough, which for a
  bar-close backtest is exactly equivalent and free. Default to resubmission.
- **Lookahead.** The squeeze state must be determined from **completed** bars: bands computed
  at the close of bar `i`, break tested on bar `i+1`. Same family as the multi-timeframe MA
  trap, and the same reason — a compression measure that includes the breakout bar's own
  range trivially predicts the breakout. This is the second-easiest place in the project to
  manufacture a fictional edge.
- **The ambiguous-bar rate will be high.** A breakout entry with a stop back inside the range
  puts the stop and the first target close together and often both inside the entry bar. M13
  makes the same prediction for coarse resolutions and gives the same instruction: if it
  looks profitable, **check the ambiguous-bar rate first**, and check the spread between
  `ambiguity_policy` 0 and 1 before believing anything.
- **Compression is a volatility state, so results will cluster in time.** A squeeze archetype
  will fire heavily in quiet regimes and barely at all in violent ones, which makes the
  aggregate profit factor an average over two different populations. This is the archetype
  that most needs M10's regime stratification and M14's per-contract dispersion, and reading
  it without them is close to meaningless.

---

## Order lifetime in NT8: making an entry rest longer than one bar

Researched ahead of need, because it was the open question that made M19's design look
possibly unbuildable. **It is buildable.** Recording the mechanism now means future
archetypes can be designed against what the platform actually does rather than against the
one behaviour DeadCatBounce happens to use.

**How this was established.** NinjaTrader 8 is installed locally, so
`NinjaTrader.NinjaScript.StrategyBase` in `C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Core.dll`
was reflected over directly for method signatures, parameter names and enum members. That is
primary evidence about the **API**. It is *not* evidence about **behaviour** — see
"What reflection cannot settle" at the end, which matters more than usual here.

### The one-bar expiry is an unset parameter, not a platform rule

This is the headline, and it reframes a gotcha the project has carried since the beginning.

Every managed entry method has a long-form overload carrying an `isLiveUntilCancelled` flag:

```csharp
EnterShortStopMarket(int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double stopPrice,  string signalName)
EnterLongStopMarket (int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double stopPrice,  string signalName)
EnterLongLimit      (int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double limitPrice, string signalName)
EnterLongStopLimit  (int barsInProgressIndex, bool isLiveUntilCancelled, int quantity,
                     double limitPrice, double stopPrice, string signalName)
```

`DeadCatBounce.cs:177-180` calls the **three-argument** overload
`EnterShortStopMarket(int quantity, double stopPrice, string signalName)`, which has no such
parameter and therefore leaves it false. So "entry orders are not GTC" is not a rule NT8
imposes — it is the default of a parameter the short overload does not expose.
`NinjaTrader.Cbi.Order` carries `IsLiveUntilCancelled` as a readable property, so it can be
asserted on a live order rather than inferred.

**Why `TimeInForce.Gtc` never helped — two different layers.** `DeadCatBounce.cs:61` sets
`TimeInForce = TimeInForce.Gtc` and the order still expires after one bar.
`NinjaTrader.Cbi.TimeInForce` is `{ Day, Gtc, Ioc, Opg, Gtd }` — an **exchange-level**
instruction about how long a venue keeps a *working* order. `isLiveUntilCancelled` is
**NT8's own managed-approach bookkeeping** about whether to auto-submit a cancel at bar
close. Different layers, different owners, and neither implies the other. This is precisely
the confusion that cost real time, and it is worth stating in those terms so it is not
re-derived.

### Route 1 — `isLiveUntilCancelled`, and the obligation it creates

Setting the flag true means **nothing cancels the order for you**. That obligation is the
whole cost of this route:

- Capture the order reference in `OnOrderUpdate`, whose confirmed signature is
  `OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity, int filled,
  double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error,
  string comment)`, matching on `order.Name` against the signal name.
- Cancel with `CancelOrder(Order order)`.
- Release the reference on terminal states. `NinjaTrader.Cbi.OrderState` has **16** members —
  `Accepted, Cancelled, Filled, Initialized, PartFilled, CancelSubmitted, ChangeSubmitted,
  Submitted, TriggerPending, Rejected, Working, CancelPending, ChangePending, Suspended,
  AcceptedByRisk, Unknown` — so "terminal" must be enumerated deliberately. Treating anything
  not `Filled` as still-live is how a stale reference gets cancelled after it already filled.

**This is also how an N-bar lifetime is built.** NT8 offers exactly two native options: one
bar (flag false) or indefinite (flag true). Anything in between is your own bar counter in
`OnBarUpdate` plus `CancelOrder`. That is unglamorous but it means **every lifetime is
expressible**, which is the thing that needed settling.

### Route 2 — unmanaged, the only native OCO

```csharp
SubmitOrderUnmanaged(int selectedBarsInProgress, OrderAction orderAction, OrderType orderType,
                     int quantity, double limitPrice, double stopPrice,
                     string oco, string signalName)
```

Confirmed, including the `oco` parameter; `Order.Oco` is a string tag and two orders sharing
one cancel each other on fill. Unmanaged orders are not auto-cancelled at all.

**The cost is large and it is not a flag.** `IsUnmanaged = true` gives up `SetStopLoss`,
`SetProfitTarget`, `EntriesPerDirection`, `EntryHandling` and managed position tracking.
`DeadCatBounce.cs` uses **all** of them — four `SetStopLoss` calls, three `SetProfitTarget`,
`EntriesPerDirection = 4`, `EntryHandling.AllEntries`. Going unmanaged means hand-rolling the
entire four-leg bracket, which is a rewrite of the strategy, not a change of order call.

**Recommendation: never go unmanaged for lifetime alone** — route 1 covers that completely.
Reserve it for a genuine two-sided OCO requirement, and even then check route 3 first.

### Route 3 — resubmit each bar, and why it is exactly equivalent for Tier 1

Keep the default one-bar behaviour and simply re-place the order every bar while the
condition still holds. No order references, no cancellation logic, no unmanaged rewrite.

**For a bar-close backtest this is not an approximation of route 1 — it is identical**,
provided the trigger price is unchanged on each resubmission. The fill test is the same
per-bar OHLC comparison either way, and the simulator has no concept of queue position for
it to differ on. If the strategy *recomputes* the trigger each bar then the two genuinely
differ, but that is a strategy design choice rather than a platform artefact.

Live, they are not identical: each resubmission is a new order, so queue position resets, and
the order churn is visible to a broker or prop-firm risk system in a way one resting order is
not. Record the distinction so a live port does not silently inherit the backtest's
convenience.

### What the simulator would need — specification only, no code yet

`deadcat.py` encodes the lifetime as a single equality, `elif pending_bar == i - 1:`. The
generalisation is an expiry bar rather than a flag: hold `pending_expires_at`, keep the order
live while `i <= pending_expires_at`, and add an `entry_order_lifetime_bars` parameter where
**1 reproduces today's behaviour exactly** and 0 means "until cancelled". Cancellation on
force-flat is required for all values; cancellation on signal invalidation is
archetype-specific and belongs in the driver, not the shared bracket code.

Same gate as every other change to this loop: at `entry_order_lifetime_bars = 1`, every
existing trade log must come back **byte-identical**.

### What this changes about M19

The earlier note said the squeeze's resting orders "may simply not be expressible in NT8".
**That is resolved — they are expressible**, and the trap downgrades accordingly:

- A one-sided rest is route 1: cheap, managed, keeps the bracket.
- A true two-sided OCO is route 2 and costs the unmanaged rewrite.
- Route 3 gets the two-sided behaviour with no NT8 work at all in backtest, and differs only
  live.

So the M19 design question is no longer "can this be built" but **"do I actually need native
OCO, or is resubmission enough"** — and for a Tier-1 research backtester the answer is
resubmission, with the OCO question deferred to a live port.

### What reflection cannot settle

The API surface above is fact. **None of the following is**, and none of it may be encoded in
`nqbt/sim/` until a trade list settles it — the prime directive applies here exactly as it
does everywhere else:

- Whether Strategy Analyzer honours `isLiveUntilCancelled` identically to live execution.
- Precisely when the cancel lands relative to the bar close, and therefore whether a
  resting order can fill on the same bar its cancel was issued.
- Whether a resting entry survives a session boundary, and how it interacts with
  `IsExitOnSessionCloseStrategy` / `ExitOnSessionCloseSeconds`.
- Whether the managed approach cancels a resting *opposite-direction* entry when one fills,
  or merely refuses the second fill. A managed strategy cannot hold both directions at once,
  but "cannot hold" and "cancels the resting order" are different claims and only a trade
  list distinguishes them.

Each is a one-run question in Strategy Analyzer with a Trades export, and each is far cheaper
to answer before an archetype depends on it than after.

---

## M10 — Prerequisites the review needs and we don't have

The review is meant to score trades against "overall trend, MAs, volume, directional vs
consolidation, time of day". Three of those five have no implementation. Only the MA gates
exist; raw per-bar volume is carried in the bar frame but nothing consumes it.

**10.1 Regime classification — `nqbt/regime.py`.** Directional / consolidating /
unclassifiable, as a 1D label array in the `conditions.py` mould, computed once in `prepare`.

Use **Kaufman's efficiency ratio** as the first classifier:
`abs(close[t] − close[t−n]) / Σ|diff(close)|` over the lookback. Bounded 0–1, ~3 lines of
numpy, no TA-Lib dependency and therefore no NT8-mismatch problem. Above the upper threshold
is directional, below the lower is consolidating, and the band between them is the
unclassifiable no-trade state — which gives the third category for free rather than as a
special case. Lookback and both thresholds are sweepable axes.

ADX is the familiar alternative and is in TA-Lib, but it is laggier, less interpretable, and
would need the same NT8-parity check the moving averages needed. Efficiency ratio first;
ADX only if ER proves inadequate.

**10.2 Volume — absolute and relative.** Both, and the relationship between them stated
rather than left to be rediscovered.

They are not two independent conditions. They are **one quantity and its decomposition**:

| | what it is | what it answers |
|---|---|---|
| absolute volume | contracts traded, raw | *Can this be traded here at all?* |
| time of day (10.4) | the dominant systematic component of it | *When?* |
| relative volume | absolute with that component divided out | *Is this unusual for the time?* |

Writing that down is the point. Stratify by all three as if they were independent findings
and you will "confirm" one signal three times, inflate the multiple-comparisons surface
§11.4 guards against, and report a coincidence as corroboration. They should be read
together — or, in a sweep, one of them chosen deliberately rather than all three switched on
because all three exist.

**Relative volume — the trap.** Intraday volume has a strong time-of-day shape (the 09:30 ET
cash open dwarfs 03:00), so a plain rolling average makes every morning bar "high volume" and
every overnight bar "low volume", which is a clock, not a signal. Normalise against the same
time-of-day across recent sessions — bar-of-session median over a trailing window — not
against a rolling window of adjacent bars.

**Absolute volume — what it uniquely answers.** It is worth having *despite* correlating with
time of day, for two reasons relative volume cannot cover by construction:

1. **Execution feasibility.** Whether a fill is realistic at size depends on contracts
   actually available, not on whether the bar was busy relative to its norm. A rule that only
   works in thin overnight bars can look excellent on relative volume and be untradeable —
   relative volume normalises away precisely the thing that decides this. It is also the
   honest input to any later slippage model, which is currently a flat tick count.
2. **Secular drift and era.** Absolute volume trends over years with participation and
   contract growth, so it carries information about *when in history* a trade happened that
   relative volume deliberately removes. That makes it a cross-check on M14's per-contract
   table rather than a duplicate of it.

**Absolute volume — the traps, which are different from relative's.**

- **Not comparable across roots.** NQ and MNQ trade different contract counts for the same
  economic exposure. Any absolute threshold is per-instrument, and reusing one across roots
  is meaningless. `instruments.py` is the natural home for the scale.
- **Not comparable across time.** The same secular trend that makes absolute volume useful
  makes a fixed threshold mean different things in 2021 and 2026. So: **absolute volume is
  for feasibility, reporting and stratification; it should not be a raw-threshold sweepable
  filter.** If a volume gate is wanted in a sweep, express it as a trailing percentile — at
  which point it is relative volume again, which is the honest conclusion rather than a
  workaround.
- **It steps at every roll** on the spliced series, because volume switches to the incoming
  contract. Prices are back-adjusted; volume is not, and should not be. Expect a
  discontinuity at each of the 18 roll dates and do not read it as a market event.

**Three forms, each answering something different**, and worth building together since they
share one pass: per-bar volume, rolling *N*-bar volume, and session-cumulative-to-date. The
last is the one that pairs with 10.4's bar-of-session index — "unusually busy session so far"
is a different statement from "unusually busy bar".

**10.3 Trend summary.** A compact label rather than a wall of MA booleans: price against the
slow MA, the slow MA's slope sign, and the fast/slow stack order. Derived from the existing
`MovingAverageGrid`, so no new indicator work — but it needs `keep_values=True`, which is the
66 MB → 595 MB memory switch. For review over one account's trade history that is fine; it
must not be switched on for sweeps by default.

**10.4 Time of day — `nqbt/timeofday.py`.** A first-class dimension for both the sweep
statistics and the review, not a review-only afterthought. Two forms, because they answer
different questions:

- **Session phase**, a coarse categorical label: overnight (18:00 ET open), London, NY
  pre-open, cash open, midday, NY afternoon, close. Few enough buckets to survive the
  minimum-stratum guard on a small sample.
- **Bar of session**, an integer index from the session open. The finer form, and the one
  relative volume already needs — 10.2's normalisation is per bar-of-session by
  construction, so the two share a definition rather than each inventing one.

**Measure it in exchange local time (ET), never UTC.** The market's rhythm follows the cash
open at 09:30 ET, which is 13:30 or 14:30 UTC depending on the date. Bucketing on UTC smears
the single most distinctive hour of the day across two different buckets for half the year,
and the result looks like noise rather than an error. Bar timestamps are stored UTC and
`sessions.classify` already produces the ET conversion, so the label comes from there.

**The multiple-comparisons cost is real and compounds.** Hour of day multiplies every other
stratification: seven session phases against five regimes is 35 cells before any MA gate.
§11.4's guard applies with more force here, and the coarse label exists specifically so the
review has a form that survives a few hundred trades. Bar-of-session is for the sweep, where
the sample is 5,000+ trades.

**Second-order payoff:** once the label exists it is also a *sweepable entry filter* — trade
only during phases X and Y — which is a single extra boolean in the condition AND, not a new
`@njit` function. Worth having as an axis before concluding an archetype has no edge, since
a rule that works only at the cash open reads as unprofitable when averaged across 23 hours.

---

## M11 — Manual trade review

**11.1 Import — `nqbt/trade_import.py`.** Manual trades in, canonical schema out.

Structured as a **thin adapter per source** — the adapter is the only format-aware code in the
project, and everything downstream sees the canonical schema alone. Adding a second source
later is one function, not a second pipeline.

**Adapters must declare what they could not recover.** Which optional fields a source carries
determines what the review can compute. The adapter returns the populated field set alongside
the frame so the review *omits* unavailable statistics with a stated reason. The failure to
avoid is a column of zeros or NaNs flowing into `stats.summarise` and being reported as if
measured.

### Source decided: the NT8 executions grid

Control Center → Executions, exported as CSV. Columns: `Instrument, Action, Quantity, Price,
Time, E/X, Position, Name, Commission, Account display name`.

It carries two fields that make the whole import tractable:

- **`Position` is the trade-boundary key.** It is the running position *after* each fill —
  `4 S`, `3 S`, `-` — so a value of `-` closes a trade. Executions group into trades without
  inferring state from order ids.
- **`Name` gives the exit reason.** `Stop1..4` versus `Exit` maps directly onto the existing
  `exit_reason` field, which is normally unrecoverable from a fills export.

**Rejected: the Control Center log grid** (`Time, Category, Message`). It is the only place
stop and target *levels* live, so it is the only route to planned risk and `r_multiple` — but
the levels it holds are not usable as intent. In the sample session both stop orders were
submitted at 29919 against a 29769 entry and dragged to ~29782 within three seconds: 29919 is
an ATM template default, so "planned risk from the initial stop" computes 150 points of risk
on a trade that actually risked ~14. Recovering true intent needs a rule like "the first stop
level that is not the template default", which is exactly the kind of heuristic that silently
corrupts a dataset. A wrong R is worse than no R, because it looks like a measurement.

**Consequence, accepted:** no planned risk, no `r_multiple`, no MAE/MFE from the source. The
review reports dollars, points and exit reason. MAE/MFE could later be *reconstructed* from
bars between entry and exit, which is a different and honest calculation — flag it as derived
if it is ever added.

**Out of scope, noted:** the log also records placed-then-cancelled entry orders — roughly 20
against 3 fills in the sample. That is a real behavioural signal about order management, and
the executions grid cannot see it. It is a different question from "which trades worked", so
it stays out rather than dragging the log parser in.

### Traps, all confirmed against the sample export

- **Two date formats in one file.** Row timestamps are `10/08/2026` (DD/MM/YYYY, 12-hour with
  AM/PM); the `Time=` field *inside* log messages is `8/10/2026` (M/D/YYYY). Same instant,
  both orderings. Parse row timestamps as DD/MM and never infer the format from the values —
  the first twelve days of any month are ambiguous and will parse silently wrong.
- **Reverse-chronological, and ties need file order, not a sort.** NT8 emits newest-first.
  Three fills sharing one second (`6:07:25` → `Stop2, Stop3, Stop4`) are only correctly
  ordered by reversing the file; sorting on the timestamp scrambles them and corrupts the
  position walk. Reverse the rows, do not sort.
- **`Commission` is `$0.00` and must not be trusted.** The account is a funded prop account
  that does charge commission; NT8 simply has no schedule for it. Costs come from
  `instruments.py`, or every trade reads better than it was.
- **No timezone anywhere in the file.** Bars are UTC; these are NT8 display times. `6:07 PM`
  is equally plausible as BST or ET and the data cannot disambiguate. Require it as explicit
  configuration and record it on the imported rows.
- **NT8 matches partial exits FIFO.** After exiting 1 of 4 (entries 2 @ 29769.00 and
  2 @ 29768.50) the log reports average 29768.6667, reachable only by consuming one unit of
  the 29769.00 entry. Trade-level P&L is unaffected — total in against total out — but the
  schema is per-leg, so per-leg attribution must use FIFO to agree with NT8.
- **Trailing comma on every row** yields a phantom empty column.

### Worked example, for the adapter's first test

Reversed, the sample resolves to two trades:

```
5:58:49  Sell 2 @ 29769.00  Entry  -> 4 S total, avg 29768.75
6:00:29  Buy  2 @ 29782.75  Stop1  -> flat   trade 1: -43.25 pts = -$86.50
6:03:07  Sell 4 @ 29767.00  Entry  -> 4 S
6:07:25  Buy  1 @ 29783.25  Stop4  -> flat   trade 2: -43.50 pts = -$87.00
```

−$173.50 gross across two trades, derived from the executions file alone. Use it as the
adapter's fixture.

The remaining traps, which are about joining trades to bars rather than parsing:

- **Back-adjustment will silently corrupt this.** A real fill at 18076.75 does not appear
  anywhere in a back-adjusted continuous series, because back-adjustment shifts every
  historical price by the cumulative roll offset (−204 to −296 points in 2024–2026). Manual
  trades must be annotated against the **raw** series or the per-contract cache. Annotating a
  real trade against `MNQ_backadj.parquet` produces plausible-looking nonsense — the bar
  lookup succeeds, and every price comparison is wrong by a few hundred points.
- **Bar alignment.** Bar timestamps are end-of-bar. A fill at 14:23:47 belongs to the bar
  stamped 14:24. Off-by-one here shifts every condition by one bar and quietly biases the
  entire review; write it down and test it.
- **Timezone.** NT8 exports UTC. A broker statement or a hand-kept journal probably is not.
  Require an explicit timezone on import rather than guessing.
- **Scale-outs map to legs.** A position exited in three pieces is one `trade_id` and three
  `leg` rows, matching the existing convention — not three trades. Getting this wrong
  triples the sample size and makes the win rate meaningless.
- **Coverage gaps.** Trades on instruments or dates outside the cache must be reported and
  excluded, not silently dropped. Make this a **coverage report** the importer emits — per
  trade, whether its instrument and date are cached — so how much of the history is actually
  reviewable becomes a measured number rather than an assumption. Note that no NQ data has
  ever been through the pipeline, so any NQ trade is currently out of coverage.

**11.2 Annotate — `nqbt/trades.py` or a sibling.** Join each trade to the `Dataset` at its
entry bar (and optionally its exit bar), producing one annotation row per trade carrying
every precomputed condition. This is the piece that makes the whole thing work, and it is
deliberately strategy-agnostic: it does not care whether the trade came from a simulation or
from a broker.

**11.3 Review — `nqbt/review.py`.** The actual question: which trades worked, and what was
true when they did.

Stratify realised P&L by each annotated condition and report per stratum: n, win rate,
expectancy, profit factor, average R. Rank conditions by how much they separate winners from
losers. Reuse `stats.summarise` unchanged — that is the point of M9.

**Time of day is a headline dimension, not one condition among many.** When during the
session a trade was taken is the stratification most likely to show real structure in a
discretionary record, because it captures attention, liquidity and the trader's own routine
at once — and unlike a moving-average gate, it is not something the trader was consciously
optimising. Report it first, using 10.4's coarse session-phase label, paired with relative
volume so "this hour is always busy" is separable from "this hour was unusually busy".

Because the same annotation path runs on simulated logs, the identical breakdown applies to
a sweep's trades — which is how a time-of-day finding in a few hundred real trades gets
tested against thousands of simulated ones instead of being believed on its own.

**11.4 The statistical guard, which is not optional.**

A few hundred manual trades against a few dozen candidate conditions is a multiple-comparisons
machine. Some condition *will* split that sample impressively, and most of the time it will be
noise. A review system without a guard here is worse than no review system, because it
produces confident, specific, wrong conclusions and they feel earned.

Three mitigations, all cheap:

- A minimum sample per stratum before a split is reported at all — the same discipline
  `sweep.rank(min_trades=...)` already enforces, for the same reason.
- A **permutation test**: shuffle the condition labels against the P&L, recompute the
  separation a few thousand times, and report where the real split falls in that
  distribution. This is the same null-model machinery as the random-entry control arm in the
  concept notes' Part II §3.3, and building one gets most of the other.
- Hold out the most recent N trades and report the finding's performance there separately.

State the output's status plainly in the report itself: **hypothesis-generating, not
confirmatory.**

**11.5 Discretionary context — recorded, deliberately excluded from the evaluation.**

Free-text context on a trade (why it was taken, what was going on, a screenshot reference)
gets stored and shown, but is **never** an input to annotation or stratification.

This is worth enforcing structurally rather than merely intending, because the reason is
stronger than a preference. Notes are written after the fact and are contaminated by knowing
the outcome — a loser attracts "I was impatient" and a winner attracts "clean setup". Mining
them would produce findings that are perfectly circular: the review would "discover" that
trades labelled bad performed badly. That is not a weak signal, it is a guaranteed one, and it
would be the most impressive-looking result in the report.

Mechanically: keep notes in a sidecar table keyed by `trade_id`, not as columns on the trade
frame, so they cannot reach a `groupby` by accident. They surface in the trade-log viewer
(M12) and in any per-trade export, and nowhere else.

Worth revisiting only if the volume of notes ever justifies deliberate qualitative coding —
categories fixed *before* outcomes are examined, which is a different activity from what M11
does.

**11.6 The payoff, and the reason this is worth building.** Because annotation runs on any
trade log meeting the schema, a hypothesis raised by reviewing real trades ("my winners were
mostly in a directional regime") can be turned into a sweep axis and tested properly on 4.7
years of bars. The review generates candidates cheaply from a small, precious sample; the
sweep tests them on a large one. Neither does the other's job, and today only one exists.

---

## M12 — Web GUI

Long term. Not to be started until the review layer's outputs are stable, or the interface
churns with them.

**The governing lesson is the CLI's.** `nqbt sweep` and `nqbt report` were dropped because
they would have been a second, lossier front door to things the Python API already does
better. A GUI carries exactly the same risk at ten times the size. It must call the same
functions, with no analysis logic of its own — if the web layer computes a statistic, that
statistic is now defined twice.

**Scope sketch**, roughly in value order:

1. Browse sweeps and rank combinations — a UI over `results.py`'s DuckDB, which is the
   clearest current gap since ranking is SQL by hand today.
2. Trade log viewer with the annotation columns.
3. The review dashboard from M11.
4. Launching a sweep from the browser — genuinely useful because a `Grid` is a structured
   object that a form can express, which is exactly what argparse could not.

**Stack.** FastAPI plus a small single-page front end if the interaction model matters, or
Streamlit/Dash if it does not. Streamlit gets something usable in a fraction of the time and
is the right call for items 1–3; it becomes limiting around item 4. Recommend starting with
Streamlit explicitly as a throwaway, rather than starting with FastAPI and discovering the
front end is the whole project.

---

## M7 — Walk-forward, Monte Carlo, and a random-entry control arm

All three, deliberately, because they answer different questions and only one of them is
about the strategy's entries.

- **`walkforward.py`** — rolling in-sample / out-of-sample splits over the cached series.
  Tests whether a parameter choice survives being chosen on data it did not see.
- **`montecarlo.py`** — permutation and resampling of a strategy's trade sequence. Tests
  whether the equity path was luckier than the trades justify.
- **`randomentry.py`** — the null the other two cannot provide. Same bars, same bracket
  geometry, same costs, same `@njit` exit logic, entries drawn at random and matched for
  count and time-of-day distribution.

The third is the one worth building first. Against the current PF of 0.746 it separates three
diagnoses that today look identical: entries **worse than random** (the signal is real but
inverted — investigate the inverse), **indistinguishable from random** (the entry logic
contributes nothing; stop tuning this archetype), or **better than random but not past
costs** (there is signal; attack costs, hold time or bracket size). Permuting an existing
trade sequence cannot distinguish any of those, because it takes the entries as given.

It also shares machinery with §11.4's permutation test, so building it pays for part of the
review's statistical guard.

### Split into M7a and M7b, with M7a moved ahead of the archetypes

`randomentry.py` was scheduled after M11 on the argument that it shares machinery with
§11.4's permutation test and is therefore cheaper built alongside it. **That argument is
symmetric and the interpretive need is not.** Sharing works in either direction — build the
null first and M11's guard inherits it — whereas the *need* for a null arrives the moment
there is more than one archetype, which is now.

Concretely: with DeadCatBounce alone, "PF 0.746" is a number about one strategy. With
DeadCatBounce, PullBackAndGo and EMA crossover, every comparison between them is a ranking
over a widening surface — and per M14's framing, picking the best of *k* candidates is the
multiple-comparisons trap whether *k* counts contracts, combinations or archetypes. M17 makes
that surface multiply: archetypes × combinations × resolutions × contracts. The random-entry
arm is the only thing on the roadmap that supplies a **scale** for those comparisons rather
than another number to sort.

So:

- **M7a — `randomentry.py`**, at step 4, after M15 and before M18. It needs the bidirectional
  loop (random entries in a bidirectional world must be drawn on both sides) and it makes
  M18's result interpretable on arrival rather than retrospectively.
- **M7b — `walkforward.py` and `montecarlo.py`**, at step 9, unchanged in content. Both still
  want to share machinery with M14's per-contract dispersion, which is the overlap M14
  already records.

One consequence worth stating: M7a must be **matched on direction as well as count and
time of day**. A long-only random arm compared against a bidirectional archetype measures
market drift, not entry quality.

---

## Related items from the discretionary-practice notes, not yet scheduled

Recorded so they are not lost. See
[trading_concepts.md](trading_concepts.md) Part II §3 for the full
argument.

- **Regime-stratified re-reading of the existing sweeps.** M10.1 delivers the classifier;
  applying it to results already in DuckDB is then nearly free, and it addresses a real
  weakness — the current "0 of 192 profitable" cannot distinguish "no edge anywhere" from
  "edge in one regime, drowned by the others". The same argument applies to M10.4's
  time-of-day label, and for the same reason.
- **Prop-account simulator** over the trade log: trailing threshold, daily loss limit,
  consistency ratio, profit target → pass rate. Reranks results by the objective that actually
  pays, rather than by profit factor.
- **ATR-multiple brackets** with a hard dollar floor on minimum bracket size.

---

## Moving-average axes: what is sweepable and what is not

**Already sweepable, no work needed.** Both the periods and the on/off toggles, jointly:

```python
grid = sweep.Grid.of(
    DeadCatParams(commission_per_contract=0.74, slippage_ticks=1.0),
    ema_period=[9, 15, 21, 30],          # period
    fast_sma_period=[40, 60, 80],        # period
    use_slow_sma=[True, False],          # toggle
    slow_sma_period=[120, 175],          # period, gated by the toggle above
    use_vwap=[True, False],              # toggle
)
```

Every field of `DeadCatParams` except `target_r_multiples` is a legal axis
(`sweep.SWEEPABLE`), and `Grid.dead_axes()` refuses a period axis whose toggle is off in
every combination — otherwise four identical rows cost 4× the runtime. The periods are
precomputed once as a `[n_periods, n_bars]` boolean matrix per MA kind, so adding period
values to a sweep is close to free at run time.

Two MA dimensions are **not** reachable. Both are recorded here as planned, not started.

### MA kind as a swept axis

The kind is currently fixed by field name: `ema_period` always resolves through
`indicators.nt8_ema`, both SMA fields through `nt8_sma`. So "what if the fast filter were an
EMA rather than an SMA?" cannot be asked, and only those two kinds exist — no WMA, HMA or
VWMA.

Needs a `kind` alongside each period (`fast_ma_kind="sma"`), a `MovingAverageGrid` per kind
in `Dataset`, and gate lookup by `(kind, period)` instead of period alone. The grid cost is
linear in the number of kinds, and the boolean-only default keeps that cheap.

**The trap is the prime directive.** Any new kind must match NT8's recursion, not the
textbook one — this is exactly where TA-Lib's EMA already differs from NT8's through
seeding alone. A kind that is merely *a* correct HMA is a fidelity break, because Tier 1 and
Tier 2 would then disagree in a way that cannot be attributed. Each kind needs pinning
against hand-computed NT8 values the way `nt8_ema` and `nt8_sma` are.

**Both halves of this are now cheaper than when it was written**, because M16 and M17 pay for
most of it as a side effect. M16 establishes the read-it-out-of-NT8-and-pin-it discipline for
a whole family of indicators, so a new MA kind is one more application of an existing
procedure rather than a fresh argument. M17's `required_context(grid)` is exactly the
"grid per kind, keyed by `(kind, period)`" lookup this needs — it has to solve the same
problem to stop `prepare` computing every archetype's indicators unconditionally.
Reconsider this item once both have landed; it may be nearly free by then.

### Multi-timeframe moving averages

Every MA is computed on the 1-minute close. A daily or hourly MA gating a 1-minute entry —
standard practice, and the natural way to express "only short below the higher-timeframe
trend" — is not expressible.

Needs the resampler from M13 below, computing the MA on the coarse series and forward-filling
back onto the 1-minute index. **The trap is lookahead**: the coarse bar covering 14:00–15:00
is not knowable until 15:00, so the value must be stamped from the *previous* completed
coarse bar or every backtest using it is silently reading the future. This is the single
easiest place in the whole project to manufacture a spectacular and entirely fictional edge.

Note this is a *different* feature from M13: here the strategy still runs on 1-minute bars
and merely consults a coarse MA. In M13 the whole strategy runs on coarse bars. Both are
wanted; they share the resampler and nothing else.

Sequencing note: this overlaps M10.3's compact trend label, which solves part of the same
problem from the other direction — a coarse trend read as a condition rather than as an MA
gate. Worth deciding which one is wanted before building either, rather than shipping two
overlapping notions of "the higher-timeframe trend".

---

## M13 — Bar resolution as a sweep dimension

Run the whole strategy on 2, 5, 15, 30-minute bars and sweep across resolutions the way
periods are swept today. Planned, not started.

### The enabling fact: resampling 1-minute bars is exact, not approximate

The obvious worry is that coarse bars should be built from `data/tick/` to be faithful. They
should not, and doing so would be the *more* precise choice the prime directive forbids.
OHLC aggregation is associative:

```
open   = first        high = max(highs)
close  = last         low  = min(lows)          volume = sum
```

A 5-minute bar assembled from five 1-minute bars is therefore **bit-identical** to one NT8
assembles from ticks. A minute with no trades contributes nothing either way, so gaps do not
break the identity. This is what makes the whole feature cheap and fidelity-neutral: no new
data, no tick pipeline, no new source of Tier-1/Tier-2 divergence.

### The trap: anchoring

Bars must be bucketed by **minutes since the session open**, not by wall clock and not with
a bare `resample()`. NT8 restarts bar building at each session start, so under the CME ETH
template a 5-minute bar runs 18:00–18:05 ET.

For the periods anyone actually sweeps this happens to be harmless — 18:00 ET is 1,080
minutes past midnight, and 2/3/5/10/15/30/60 all divide 1,080, so midnight-anchored and
session-anchored buckets coincide. **That coincidence is exactly why this must be tested
rather than assumed**: it holds for every period likely to be tried first, then silently
fails on 7 or 11 or 45. Anchoring to the session open is no harder and is correct for all of
them.

Two further boundaries the bucketing must respect: no bar may span the 17:00–18:00 ET
maintenance break, and none may span the Friday 17:00 → Sunday 18:00 weekend. Bucketing from
the session open gives both for free; bucketing on wall clock does not.

### Validation needs no new data

**The existing 1-minute archive is sufficient to build every resolution.** Nothing needs
re-exporting and the AddOn needs no change. Three checks, all local:

1. **Aggregation is exact** — assert a resampled bar's OHLCV against the 1-minute bars it
   came from. This is arithmetic, and a unit test pins it.
2. **Boundaries land where intended** — assert every bucket starts at session open + *k*·N
   minutes, that none spans the 17:00–18:00 ET break, and that none spans the weekend.
3. **Anchoring is provably moot for the periods that matter** — assert directly that
   session-anchored and midnight-anchored bucketing agree for 2/3/5/10/15/30/60 and diverge
   for 7. That converts the coincidence above from a hazard into a documented property, and
   it is the test that stops someone "simplifying" to a bare `resample()` later.

Anchoring from the session open is correct for every period, so this is belt-and-braces
rather than a dependency.

**Tier 2 already covers the residual risk.** The one thing local tests cannot settle is what
*NT8* does, and the prime directive is parity. But that is exactly what the existing
reconciliation workflow checks: re-validating a 5-minute survivor in Strategy Analyzer and
diffing the trade list catches an anchoring mismatch immediately, and does it better than a
bar diff would, because it tests bars and fills together. No extra step is needed — it is
the step that already exists.

Only if such a reconciliation disagrees is it worth pulling NT8's own coarse bars as a
diagnostic, to separate "our bars differ" from "our fills differ".
`NqbtHistoricalExporter.cs:270` builds `BarsPeriod { BarsPeriodType = BarsPeriodType.Minute,
Value = 1 }`, so that is a one-value change, and `tools/compare_exports.py` already diffs two
export folders. Note that it would have to be requested under the ETH template rather than
`Default 24 x 7`, since bar building is anchored by the template and Strategy Analyzer uses
ETH — but this is a debugging path, not a prerequisite.

### What changes about the strategy, which is the real point

Resolution is not a neutral knob. Several rules are defined per *bar*, so their meaning
moves with the bar:

| rule | at 1 min | at 5 min |
|---|---|---|
| entry order lifetime (one bar) | 1 minute | 5 minutes |
| stop ratchet (once per completed bar) | every minute | 5× less often |
| `bars_required_to_trade = 200` | 200 minutes | 1,000 minutes |
| MA period 21 | 21 minutes | 105 minutes |

So a resolution sweep is not "the same strategy, sampled differently" — it is a family of
related strategies. Two consequences: `resolution` must be a first-class column everywhere
results are stored or compared, and **comparing profit factor across resolutions at the same
period number is meaningless** unless the period is scaled with it.

**Prediction worth checking early: the ambiguous-bar rate should rise sharply.** A bigger bar
is likelier to contain both the stop and a target. At 1 minute that is 3.4% of exits and the
choice of `ambiguity_policy` is worth only ±0.009 PF. At 15 minutes it could dominate, and
the spread between the NT8 rule and the blanket worst case becomes a direct measure of how
much of any apparent coarse-resolution edge is an artefact of what bar data cannot settle.
If a coarse resolution suddenly looks profitable, **look there first.**

### Shape

`nqbt/resample.py`, and it belongs to **context, not simulation** — so it lands naturally
alongside M9's `nqbt/context.py`.

Resolution cannot be a `DeadCatParams` field: it changes the `Dataset`, not the rule, and
`sweep()` builds one `Dataset` for the whole grid. Cleanest is a wrapper that builds one
`Dataset` per resolution and runs the grid inside each, tagging every row:

```python
res = sweep.sweep_resolutions(bars, grid, resolutions=[1, 2, 5, 15])
```

Cost is mild and self-limiting, because coarser series are proportionally smaller: sweeping
1, 2, 5 and 15 minutes costs about 1 + ½ + ⅕ + 1/15 ≈ **1.8× a 1-minute sweep**, not 4×.
`results.save_sweep` needs the extra column, which is also a reason to do it before the
stale DuckDB re-run rather than after.

---

## M14 — Per-contract sweeps

Run a sweep across individual contracts rather than only the spliced series, so a strategy's
performance can be compared contract by contract. Planned, not started.

### What already works, and what is missing

`sweep.sweep()` takes a bars frame, so passing one contract's cache runs a sweep on it today:

```python
sweep.sweep(ingest.load_contract(ContractId.parse("MNQ 06-24")), grid)
```

Missing is everything around that: a way to run the whole set and get one table with a
`contract` column, a `contract` field in the DuckDB schema (`save_sweep` records `root` and
`instrument` only), and — most importantly — the framing that stops the output being
misread.

### Frame it as dispersion, not selection

Each contract is front-month for roughly three months, so **"which contract is the strategy
best on" is very nearly "which quarter of history was it best in"**. That reframing matters,
because the two questions have different failure modes. Ranking 19 contracts and taking the
winner is the multiple-comparisons trap §11.4 already guards against on real trades: with 19
contracts × N combinations, a good-looking best is the expected output of noise, not
evidence.

The useful output is **the spread**, not the maximum. How much does performance vary across
contracts, and is that variation larger than resampling the same trades would produce? That
is a stability measure, and it is worth having precisely because a single continuous-series
profit factor hides it completely.

This overlaps **M7's walk-forward** substantially — rolling IS/OOS splits answer "does this
hold across time" with finer and non-calendar-aligned windows. Build the two to share
machinery and report compatibly rather than as two independent verdicts on the same
question.

### Three things it does that time-slicing does not

Given that overlap, the distinct value is worth being explicit about, because it is what
justifies the feature separately from M7:

1. **It is a data-integrity instrument.** An outlier contract is a strong signal of a data
   bug — a bad roll date, a hole, a bad splice — not a market insight. Given how much of the
   archive work came from exactly such defects, a per-contract table is a cheap standing
   check that would have caught several of them earlier.
2. **It uses raw prices.** The continuous series is back-adjusted, which shifts historical
   prices by hundreds of points. Any rule sensitive to absolute price level — round-number
   stop avoidance, already recorded as incoherent with back-adjustment — can *only* be
   tested per contract.
3. **It is directly Tier-2 reproducible.** A spliced result cannot be reproduced in Strategy
   Analyzer bar-for-bar around a roll, which is the standing residual risk of data-derived
   roll dates. A single-contract run contains no roll, so it can be checked against NT8
   exactly. This is also the cheapest route to the outstanding NQ reconciliation.

### Decide explicitly: full contract life or front-month window

The archive now holds roughly six months per contract, but each is front-month for about
three. The choice is not cosmetic:

- **Front-month window** (roll date to roll date) — non-overlapping, sums to the continuous
  series, contracts are comparable to each other. **This should be the default.**
- **Full contract life** — each contract is a clean standalone series, but adjacent contracts
  overlap by months, so the same calendar days appear in two rows. Aggregating across them
  double-counts. Useful for asking "how does the strategy behave on a back-month contract's
  thinner liquidity", which is a genuinely different question.

Report `bars`, `sessions` and `trades` per contract alongside any performance figure. Contract
windows are not equal — MNQ 03-22 carries 47 thin early-listing sessions, and the current
front contract is always partial — and a profit factor from 30 trades will otherwise sit in
the same column as one from 400.

### On identifying political and economic events

Worth being straight about the resolution this gives. A contract is a ~3-month bucket, so a
per-contract table will surface **regime shifts** — a volatility era, a trending year — but
will not isolate an **event**. An election, a CPI print or a rate decision is a day or an
hour, and averaging it across a quarter dilutes it to nothing.

For events, the tools are M10's regime classifier and time-of-day labels plus a date-range
filter, at which point the question becomes "how does the strategy behave on high-volatility
days" rather than "on this contract". The two are complements: per-contract finds *where* to
look, the M10 labels resolve *what* is happening there.

### Shape

`sweep.sweep_contracts(root, grid, ...)`, building one `Dataset` per contract and tagging
every row with its `contract`.

**This is architecturally the same feature as M13 — and as M17.** All three add an axis that
sits *above* the `Dataset` rather than inside `DeadCatParams`, all three need one `Dataset`
per value, and all three need a nullable column in the results schema — `resolution`,
`contract` (null meaning "spliced series") and `strategy`. Design them together and build one
mechanism, or they will arrive as three near-identical wrappers that diverge. Doing all three
before the stale DuckDB re-run means the schema settles once instead of three times; see
M17 for the combined shape.

**One interaction worth pricing before committing to the full cross-product.** These axes
multiply: archetypes × combinations × resolutions × contracts. M13's cost note (1, 2, 5 and
15 minutes ≈ 1.8× a 1-minute sweep, because coarser series are smaller) does *not* extend to
contracts or archetypes, which are closer to linear. The runtime is manageable; the
*statistical* surface is the problem, and it is what M7a exists to give a scale for. Default
to running one axis at a time and treat the full cross-product as a deliberate act.

---

## Decisions taken

**New archetypes: infrastructure now, one archetype now, M11 keeps its slot.** `CLAUDE.md`
records "which archetype is actually worth trading is a later question" and treats
DeadCatBounce as the test fixture. Adding EMA crossover and squeeze breakout partly reverses
that, so the extent was decided deliberately rather than by drift: **the infrastructure lands
now** (M15, M16, M17 — which is where essentially all the cost is, and much of which M9 and
M10 needed anyway), **one archetype is built to prove it** (M18), and **M11 is not
displaced**. The second archetype (M19) is specified and queued, not scheduled.

The reasoning is that the infrastructure is not archetype-specific work at all. M15 is a
`direction` field M9 was already adding; M16 is a debt `indicators.py` recorded from the
start; M17 is the same axis-above-the-`Dataset` mechanism M13 and M14 already needed. Only
M18 and M19 are genuinely new scope, and they are the small part.

**Strategy development stays in Python; the C# port happens on promotion, not on creation.**
Decided explicitly. An archetype is designed, swept, stratified and — most often — discarded
without any NinjaScript existing. Only one that looks like it works earns the port back to
C#, at which point the Python is the specification and the usual leg-for-leg reconciliation
applies.

The reasoning is throughput: most archetypes will not survive contact with costs, and writing
a NinjaScript for each one before knowing that spends NinjaTrader time — the project's
scarcest resource, per the outstanding NQ reconciliation — on candidates that are about to be
thrown away.

Three things this buys and one it costs, all worth recording:

- The prime directive **still binds during development**, and this is what protects the
  eventual port. A Python archetype that drifts into intrabar precision cannot be reconciled
  when it is finally written in C#, so the exploration would be wasted rather than merely
  unvalidated. "It's only Python for now" is not a licence to exceed NT8's fidelity.
- The design must be **checked against what NT8 can express while it is being written**, not
  at port time. That is what the expressibility checklist in the standing-constraint section
  is for, and it is why the order-lifetime research was done now rather than when M19 starts.
- **Tier-1-only status becomes per archetype and must be visible**, not remembered — M17's
  registry field and results column. A ranking that mixes a reconciled archetype with an
  unpromoted one is comparing a measurement with an assumption.
- The cost is that a promising Python result carries **unquantified port risk** until the
  reconciliation runs. Accepted, on the grounds that it is only paid for candidates worth
  paying it for.

**Promotion criteria — what "we believe we have something that works" should mean.** Left
loose it will collapse into "the profit factor looked good", which is the multiple-comparisons
trap §11.4 exists to prevent, and the port is expensive enough to be worth a bar. A candidate
should clear the null before it earns C# time: beat the random-entry arm (M7a), survive
walk-forward (M7b), and hold up across contracts rather than resting on one quarter (M14).
Not a gate to enforce mechanically, but the checks to have run before spending
NinjaTrader time.

**`PullBackAndGo.cs` is ported before any original is built.** The alternative was to let
EMA crossover be the first exercise of the new long-side code. Rejected: a long-side fill
bug found against `PullBackAndGo`'s NT8 trade list is a bug, whereas the same bug found on an
original archetype is indistinguishable from the strategy simply being bad. It is long-only
`EnterLongStopMarket`, the exact mirror of DeadCatBounce's entry, so it tests the new path
precisely and it has ground truth. `InsideBar.cs` and `InsideBarTrailing.cs` remain unported
and are the cheapest further archetypes available — `InsideBar` in particular is the
compression-then-break idea with C# attached, which is why M19 recommends porting it before
building a squeeze from scratch.

**The bracket engine is extracted during M18, not before it and not after.** Before is
designing an abstraction from one example; after means fidelity-critical code sat duplicated
on `main`. Extracting mid-M18 with byte-identity as the gate gets an abstraction designed
against two real shapes without the duplication ever shipping. See M17.

**Archetypes are flat between trades; stop-and-reverse is not supported.** The loop's
`in_position` boolean assumes flat-to-flat and reversal collides with the one-bar entry
lifetime. Recorded as a deliberate limitation rather than discovered as a position-tracking
bug. See M15.

**Roll dates need no reconciliation against NT8.** All 18 MNQ roll dates moved when the
archive made volume crossovers detectable, which raised whether Tier 1 and Tier 2 still agree
across a roll — the coverage handover used to guarantee it by construction, being the point
NT8 itself ran out of one contract.

Decided: not worth chasing. NT8 merges contracts on the rollover dates **configured in its
Database window**, not on observed volume, so it is a setting rather than a measurement. It
is ground truth for fill semantics, which is what the prime directive is about; it is not
ground truth for when the market actually rolled. A data-derived crossover can reasonably be
*better* than NT8 here without that being a fidelity violation.

Residual risk, recorded rather than dismissed: a spliced-series result cannot be reproduced
in Strategy Analyzer bar-for-bar around a roll. If a sweep that crosses one ever produces
something surprising, the roll boundary is a candidate explanation, and the segment tables in
`nqbt splice --diagnostics` are where to look first.

**Stored sweeps — drop and re-run, not yet.** Everything in `results/sweeps.duckdb` was
computed against a continuous series with different roll dates, so those rows are not
comparable with anything generated now. They are not wrong, they are answers to a different
question, and nothing reads them automatically. Clear the table and re-run the grids that
still matter at the point something actually needs to query it — most cheaply once M10's
regime and time-of-day labels exist, so the re-run produces stratified results rather than
needing a third pass.

**Trade source format — deferred, by design.** An example will arrive; until then the
importer is specified as an adapter boundary (§11.1) rather than around a guessed layout.
Writing the adapter is small work once the example exists, and it is the *only* part that
should need to change per source. Everything upstream of the example — the schema (M9), the
conditions (M10), the annotation and review machinery (§11.2–11.4) — is independent of the
format and can be built first.

**Discretionary context — recorded, not analysed.** Stored, viewable, and structurally kept
out of the evaluation path. See §11.5 for why this is enforced rather than merely intended.

**Coverage — measured, not decided.** Whether the trades fall inside cached instruments and
dates becomes a report the importer emits (§11.1), so the answer arrives as data with the
first real file. The only design consequence is that out-of-coverage trades must be excluded
loudly rather than dropped quietly.

**Trade source — the NT8 executions grid**, with the Control Center log rejected. Reasoning
and the confirmed parsing traps are in §11.1. The review reports dollars, points and exit
reason; `r_multiple` is deliberately not reconstructed.

**Timezone — NT8 display time is the machine's local zone**, `GMT Standard Time`, so BST
(UTC+1) in summer. Confirmed end-to-end: converting the sample's eight fills to UTC and
mapping each to the bar stamped at the next whole minute puts every one inside its bar's
high/low range, with the 17:00:29 stop landing exactly on the 17:01 high. That simultaneously
validates the conversion, the end-of-bar alignment rule, and coverage. It should still be
explicit configuration rather than an inferred default — a wrong zone shifts every trade by
hours without erroring — but the default is now known to be right for this machine.

**Coverage — resolved for the sample.** MNQ runs to 2026-08-10 19:55 UTC, past the 16:58–17:07
trade window. Note the export lags live by roughly two hours, so the most recent session is
always partly unavailable; a review run soon after trading will find its newest trades
uncovered, and the importer's coverage report is what should say so.

## Still open

- **Sample size.** How many trades exist determines whether §11.4's guard leaves anything
  standing. A few dozen will not support stratification by more than one or two conditions at
  a time, and knowing that early sets expectations for what the review can honestly deliver.
- **Which series to annotate against.** The sample trades a single contract, `MNQ 09-26`.
  Annotating against the per-contract cache sidesteps back-adjustment and roll-date questions
  entirely and is almost certainly right; the continuous series only earns its place if a
  review needs indicators with lookbacks that cross a roll.
