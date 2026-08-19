# Roadmap

**How this file relates to the issue tracker.** The issues carry the **what** — scope,
acceptance criteria, checklists, the definition of done. This file carries the **why** — the
reasoning behind the ordering, the constraints that span milestones, the traps that cost real
time to find, and the decisions taken so they are not silently re-litigated. When the two
disagree about scope, the issue wins; when they disagree about reasoning, this file wins.

Four things live here and nowhere else, because an issue is the wrong home for them: the
**standing constraint** and its expressibility checklist, the **order-lifetime research**, the
**standing rubric**, and the **decision record**. Everything else is a paragraph of context
with a link.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the
project's own docs first, [trading_concepts.md](trading_concepts.md) Part II second. The
discretionary-practice notes are a source of framing and of numeric definitions we lack, not a
source of priorities.

---

## Order of work

Dependency order, not priority order — each item's prerequisites sit above it.

| # | Work | Issue | Why here |
|---|---|---|---|
| ~~1~~ | ~~Re-export NQ manually~~ | — | **Done 2026-08-11.** 19 contracts, all 18 rolls on genuine crossovers, archive 4.09M → 4.60M bars. Also exposed a stub-session bug in roll detection, now fixed. |
| ~~2~~ | ~~Run the simulation against NQ~~ | — | **Done 2026-08-11.** Runs end to end including parallel sweeps. Instrument scaling proven exact. |
| ~~3~~ | ~~**M9** — split context from simulation~~ | — | **Done 2026-08-12.** `nqbt/context.py` and `nqbt/trades.py` exist, layering enforced by import-analysis tests, every producer path byte-identical across all 14 files. |
| ~~3a~~ | ~~**M20a** — the three findings that block M15~~ | [#9] | **Done 2026-08-14.** `_resolve_brackets` is the single bracket implementation, `entry_bracket` the single trigger computation, `Summary.empty()` replaces the splat that raised. |
| ~~3b~~ | ~~**M15** — direction in the simulator~~ | [#13] | **Done 2026-08-15**, reconciled included. `d = ±1` through the whole loop, `PullBackAndGo` ported and diffed leg-for-leg against a real NT8 trade list. That reconciliation found two fill-semantics defects — see below. |
| ~~—~~ | ~~**M16** — NT8-parity ATR, StdDev, Bollinger, Keltner~~ | [#19] | **Done 2026-08-16.** One probe run answered [#20], [#21], [#22] and [#23]'s measurement half over 89,330 bars. Keltner matched neither half of the usual definition. **M18 is unblocked.** |
| ~~3c~~ | ~~**M17 + M13 + M14** — strategy, resolution and contract as axes~~ | [#24], [#30], [#31] | **Done 2026-08-16.** The registry landed 2026-08-15; `resample.py` ([#30]) and `dispersion.py` ([#31]) followed, then the results schema ([#29]) and `sweep_axes` ([#28]) — **one mechanism, not three**, so the schema settled once before the stale DuckDB re-run ([#71]). |
| ~~4~~ | ~~**M7a** — `randomentry.py`~~ | [#32] | **Done 2026-08-16.** Matched on count, time-of-session and direction; Monte Carlo rather than a single draw. First result reframes DeadCatBounce — better than random, still unprofitable. See below. |
| 5 | **M18** — EMA crossover | [#34] | The one archetype built now, to prove the protocol. A legitimate known-negative control. |
| ~~6~~ | ~~Numpy-native summary path~~ | [#33] | **Done 2026-08-19**, and taken *before* M18 rather than after — 3.1× on a combination, with the summary now inside the noise of the simulation. M18's ~30× legs land on a sweep that no longer pays for a DataFrame per combination. |
| 7 | **M10** — regime, volume, trend, time of day | [#39] | Dual-use: the review needs them, and they let existing sweep results be stratified rather than averaged. |
| 8 | **M11** — the trade review | [#44] | The stated goal. Needs 3 and 7. Deliberately *not* displaced by the archetype work. |
| 9 | **M7b** — walk-forward and Monte Carlo | [#50] | Shares machinery with M14 and with §11.4's permutation test. |
| 10 | **M19** — squeeze breakout | [#51] | Queued, not scheduled. Needs an OCO entry model the loop lacks, so it is the expensive archetype. |
| 11 | **M12** — web GUI | [#52] | Gated on the review's outputs being stable. |

**Standing work, no gate:** M20b typing and tooling ([#53]), M20c structural cleanups ([#58]),
the Tier-2 verification epic ([#65]) which needs NinjaTrader time rather than code time, and
tracking `verification/` in git ([#91]).

**Why the order looks like this.** The request was "add EMA crossover and squeeze breakout",
but neither was reachable and neither was where the cost is: the simulator was
**short-only** (M15, now paid), the indicators they need have an unpaid NT8-parity debt
(M16), and `sweep.py` is hardcoded to `DeadCatParams` (M17). That infrastructure is ~all the
work; the archetypes themselves are then small. It also pays for the NinjaScripts written and
never ported — `PullBackAndGo.cs` is now done, leaving `InsideBar.cs` and
`InsideBarTrailing.cs`, both long-capable and both using `ATR()`.

**Why M16 left the code queue, which is a change from the order above.** M16 was scheduled
ahead of M17, but its three substantive sub-issues are each *"read the value out of NT8 and
pin it"* — the milestone's own instruction is **do not answer from memory**, so hand-rolling
the recursions before the readings exist is precisely the failure it was written to prevent.
That makes M16 NinjaTrader time, and it now shares that constraint with [#66] and [#67].
M17 has no NT8 dependency, is an equally hard prerequisite for M18, and is therefore the
better use of code time. **Split the queue by resource, not by milestone number:**

| resource | work |
|---|---|
| code time | ~~M13 ([#30]) → M14 ([#31]) → M17.4/M17.5 ([#28], [#29]) → M7a ([#32]) → the numpy summary path ([#33])~~ — **all done**. Next: M18 ([#34]) |
| NinjaTrader time | ~~[#20], [#21], [#22], [#23], [#66], [#92]~~ — **all done 2026-08-16**. Only [#67] (order lifetime) remains, and M19 is not scheduled |

Nothing in the NinjaTrader column blocks anything in the code column. The reverse is not
true — M18 needs both.

**The NinjaTrader queue is now empty except [#67], and M18 is unblocked.** That session
paid for itself several times over: it closed M16 and both outstanding reconciliations, and
it found two things that reasoning would not have — Keltner matching neither half of the
common definition, and the trade-list export being in the machine's display timezone rather
than UTC. [#67] is the only item left and it gates M19, which is queued rather than
scheduled, so nothing is waiting on it.

**[#23]'s roll-boundary half is still a decision, not a measurement.** The session-boundary
half is settled: True Range does not reset. On a back-adjusted series ATR will step at each
roll, and the guidance is to judge an ATR-sensitive rule per contract ([#31]) rather than to
special-case the splice.

### What M15.5 changed, and the lesson that outlives it

The `PullBackAndGo` reconciliation was not a formality. It found **two direction-general
fill-semantics defects**, both recorded with their evidence in `docs/nt8-fidelity.md`:

- **A stop that gaps fills at the open.** Modelled on the entry side since the beginning and
  never on the exit side, so every gapped stop exit was optimistic. **It moved the short side
  too** — always to a worse fill, never a better one — which is why nothing in the existing
  suite caught it.
- **A stop entry at or through the market is never submitted.** DeadCatBounce's trigger cap
  makes this structurally impossible for it, so the simulator had no notion of
  submittability at all.

**The lesson is the one worth carrying forward: a single archetype cannot exercise the fill
model.** Both defects were unreachable from DeadCatBounce by construction, not by luck, and
both had been live for the entire life of the project. Expect the same when M18 introduces
market-on-next-open entries and `EXIT_SIGNAL` exits — each new mechanism is a new part of the
fill model with no evidence behind it yet, and [#38]'s shared bracket engine will inherit
whatever is wrong. This is the argument for reconciling each archetype rather than trusting
the shared engine because the first one passed.

**Unscheduled, and cheap once M16 lands — M15 is no longer the blocker:** porting `InsideBar.cs` and
`InsideBarTrailing.cs`. Both have C# ground truth, which makes them the cheapest *trustworthy*
archetypes available, unlike M18 and M19. `InsideBar` is the structural form of the squeeze
idea and is worth porting before M19 is built from scratch. `InsideBarTrailing` is the second
consumer of `EXIT_SIGNAL`.

**Not scheduled:** M8 (premise measured and mostly false, and [#33] has since removed the
overhead that capped it — see `CLAUDE.md`), the three unbuilt
spec features ([#74]), `NG 02-26`'s silent skip ([#69]), and the MAE/MFE definition mismatch
([#70]).

---

## Standing constraint, extended

The prime directive — match NT8's default bar-close fidelity, never exceed it — governs the
**simulation** side only.

The review side takes real fills, which are genuinely tick-precise, and that is not a fidelity
violation because nothing is being simulated. **The trap is letting that precision leak
backwards.** A real trade filled at 18076.75 mid-bar is evidence about the market; it is not
evidence that the simulator should model intrabar fills. Keep the annotation path read-only
with respect to `nqbt/sim/`: the review may *describe* what a real trade did and compare it
against what the simulator would have done, but it must never feed a fill rule back into the
`@njit` loop. If those two ever need reconciling, the trade list wins for *facts* and NT8 wins
for *fill semantics*, and they are different questions.

### An original archetype has no C# to lose to

`CLAUDE.md` says "when the C# and intuition disagree, the C# wins". DeadCatBounce was a
**port**, so that rule always had a referent. EMA crossover and squeeze breakout are
**originals** — there is no NinjaScript, so the rule has nothing to point at. That inverts the
workflow and it needs stating before the first original is written, not after.

- **The prime directive still binds**, in full. It constrains the *simulator* — bar-close OHLC
  fills, no intrabar tick precision — and the simulator is shared by every archetype. Nothing
  about inventing a rule set licenses a more precise fill model for it.
- **For an original, the Python is the specification** and the NinjaScript is written *from*
  it, not the other way round. The reconciliation is unchanged in form: export Trades, diff
  leg-for-leg.
- **Development stays in Python. The port happens on promotion, not on creation.** Decided
  deliberately — see "Decisions taken". An archetype is explored, swept and discarded entirely
  in Python; only one that looks worth trading earns the C# work.
- **So a developing archetype is Tier-1 only, and that has to stay visible.** Today "validated
  against NT8" is a project-wide property, true of the only archetype there is. With
  Python-first originals it becomes a **per-archetype** property, and a sweep table that ranks
  a reconciled archetype against an unreconciled one is comparing a measurement with an
  assumption. M17 records it as a registry field and a results column for exactly this reason.
- **The failure mode is accumulation** — three archetypes, none ever opened in Strategy
  Analyzer, all quietly trusted because the *first* one was. Mitigations: port
  `PullBackAndGo.cs` early so the new long path is proven against real C# while it is cheap to
  fix ([#17]), and make Tier-1-only status a visible column rather than a remembered caveat.

**The constraint runs the other way too, and this is the non-obvious half.** Writing Python
first means the platform gets no vote until the port, so a strategy can be built that NT8
cannot express — and discovering that after a promising sweep is the expensive order to find
out. The mitigation is to know the platform's limits *before* designing against them, which is
what "Order lifetime in NT8" below exists for.

**Expressibility checklist, to be run against a new archetype's design before building it.**
Each item is somewhere NT8's managed approach constrains what a strategy can be:

| question | current answer |
|---|---|
| How long must an entry order rest? | Any lifetime is expressible — see "Order lifetime in NT8" |
| Does it need a true OCO pair? | Only via the unmanaged approach, which costs the whole bracket |
| Does it need to reverse directly from long to short? | Not supported by the simulator either; see [#13] |
| Does it hold through the session close? | **It cannot.** Flat before the close is mandatory — see below |
| Does it need more than 4 entries per direction? | `EntriesPerDirection` is a strategy property, not a limit |
| Does it need an indicator NT8 computes differently? | Assume yes until pinned — see [#19] |

The list is short because most of it has now been researched. Extend it rather than
rediscovering an item the hard way.

### Flat before the session close is a hard constraint, not a detail

**Every position must be flat before the session close.** This is a prop-firm account rule, so
it is not a preference, a parameter, or something a promising strategy gets to negotiate with.
It also matches NT8, where `DeadCatBounce.cs` sets `IsExitOnSessionCloseStrategy = true` with
`ExitOnSessionCloseSeconds = 30`, so Tier 1 and Tier 2 agree on it today.

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

- ~~**M15** ([#16])~~ — **done.** A resting entry order is cancelled at the flatten point
  rather than left to expire. It is the one cancellation condition that applies to every
  archetype regardless of its own invalidation logic, so a new archetype inherits it and must
  not re-implement it. Note it was **not** a no-op: `block_entry_at_session_close` only ever
  guarded a *new* signal on that bar, never an order resting from the one before.
- **M13** ([#30]). The forced-exit share should rise sharply with bar size. At 30-minute bars a
  position opened near the close has almost no bars in which to reach a target, so more of its
  outcomes are decided by the clock than by the rules. Worth measuring alongside the
  ambiguous-bar rate, and for the same reason — both are ways a coarse resolution can look
  different without the strategy being different.
- **M10.4** ([#43]). The final session phase has *structurally* forced exits, so a time-of-day
  stratification will show it as anomalous. **That is an artefact, not a finding.** Any
  time-of-day result touching the last phase has to separate "this hour trades badly" from
  "this hour's trades were closed by the clock".
- **M18 and M19** ([#34], [#51]). Crossover holds until an opposite cross, so it will hit
  force-flat often — expect the forced-exit share to be a large fraction of its exits. A
  squeeze rests orders, which must be cancelled at the flatten point.
- **Statistics.** The share of exits at `EXIT_SESSION_CLOSE` deserves to be a reported column
  rather than something buried in the trade log. A strategy taking 40% of its exits from the
  clock is not really the strategy its rules describe, and the aggregate profit factor will not
  say so.
- **The prop-account simulator** ([#75]) treats the daily flat as one of the rules it replays,
  alongside trailing drawdown and the consistency ratio.

**Holiday early closes are probably not handled — [#68].** `force_flat_mask` derives its cutoff
from the *template's* fixed 17:00 ET close, not from the session's observed last bar, so on a
CME half-day nothing reaches the cutoff and the mask appears to come back empty. Note the
asymmetry: `is_session_close` *is* data-derived and does handle early closes, so the two
disagree precisely on the days that matter. Roughly 5–8 sessions a year. **Verify with a query
before fixing**, and note that a fix changes Tier-1 results on those days.

---

## Order lifetime in NT8: making an entry rest longer than one bar

Researched ahead of need, because it was the open question that made M19's design look possibly
unbuildable. **It is buildable.** Recording the mechanism now means future archetypes can be
designed against what the platform actually does rather than against the one behaviour
DeadCatBounce happens to use.

**How this was established.** NinjaTrader 8 is installed locally, so
`NinjaTrader.NinjaScript.StrategyBase` in `NinjaTrader.Core.dll` was reflected over directly for
method signatures, parameter names and enum members. That is primary evidence about the **API**.
It is *not* evidence about **behaviour** — see "What reflection cannot settle" below, which
matters more than usual here.

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

`DeadCatBounce.cs` calls the **three-argument** overload `EnterShortStopMarket(int quantity,
double stopPrice, string signalName)`, which has no such parameter and therefore leaves it
false. So "entry orders are not GTC" is not a rule NT8 imposes — it is the default of a
parameter the short overload does not expose. `NinjaTrader.Cbi.Order` carries
`IsLiveUntilCancelled` as a readable property, so it can be asserted on a live order rather than
inferred.

**Why `TimeInForce.Gtc` never helped — two different layers.** `DeadCatBounce.cs` sets
`TimeInForce = TimeInForce.Gtc` and the order still expires after one bar.
`NinjaTrader.Cbi.TimeInForce` is `{ Day, Gtc, Ioc, Opg, Gtd }` — an **exchange-level**
instruction about how long a venue keeps a *working* order. `isLiveUntilCancelled` is **NT8's
own managed-approach bookkeeping** about whether to auto-submit a cancel at bar close. Different
layers, different owners, and neither implies the other. This is precisely the confusion that
cost real time, and it is worth stating in those terms so it is not re-derived.

### Route 1 — `isLiveUntilCancelled`, and the obligation it creates

Setting the flag true means **nothing cancels the order for you**. That obligation is the whole
cost of this route:

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

**This is also how an N-bar lifetime is built.** NT8 offers exactly two native options: one bar
(flag false) or indefinite (flag true). Anything in between is your own bar counter in
`OnBarUpdate` plus `CancelOrder`. That is unglamorous but it means **every lifetime is
expressible**, which is the thing that needed settling.

### Route 2 — unmanaged, the only native OCO

```csharp
SubmitOrderUnmanaged(int selectedBarsInProgress, OrderAction orderAction, OrderType orderType,
                     int quantity, double limitPrice, double stopPrice,
                     string oco, string signalName)
```

Confirmed, including the `oco` parameter; `Order.Oco` is a string tag and two orders sharing one
cancel each other on fill. Unmanaged orders are not auto-cancelled at all.

**The cost is large and it is not a flag.** `IsUnmanaged = true` gives up `SetStopLoss`,
`SetProfitTarget`, `EntriesPerDirection`, `EntryHandling` and managed position tracking.
`DeadCatBounce.cs` uses **all** of them — four `SetStopLoss` calls, three `SetProfitTarget`,
`EntriesPerDirection = 4`, `EntryHandling.AllEntries`. Going unmanaged means hand-rolling the
entire four-leg bracket, which is a rewrite of the strategy, not a change of order call.

**Recommendation: never go unmanaged for lifetime alone** — route 1 covers that completely.
Reserve it for a genuine two-sided OCO requirement, and even then check route 3 first.

### Route 3 — resubmit each bar, and why it is exactly equivalent for Tier 1

Keep the default one-bar behaviour and simply re-place the order every bar while the condition
still holds. No order references, no cancellation logic, no unmanaged rewrite.

**For a bar-close backtest this is not an approximation of route 1 — it is identical**, provided
the trigger price is unchanged on each resubmission. The fill test is the same per-bar OHLC
comparison either way, and the simulator has no concept of queue position for it to differ on.
If the strategy *recomputes* the trigger each bar then the two genuinely differ, but that is a
strategy design choice rather than a platform artefact.

Live, they are not identical: each resubmission is a new order, so queue position resets, and
the order churn is visible to a broker or prop-firm risk system in a way one resting order is
not. Record the distinction so a live port does not silently inherit the backtest's convenience.

### What the simulator would need — specification only, no code yet

`deadcat.py` encodes the lifetime as a single equality, `elif pending_bar == i - 1:`. The
generalisation is an expiry bar rather than a flag: hold `pending_expires_at`, keep the order
live while `i <= pending_expires_at`, and add an `entry_order_lifetime_bars` parameter where **1
reproduces today's behaviour exactly** and 0 means "until cancelled". Cancellation on force-flat
is required for all values; cancellation on signal invalidation is archetype-specific and
belongs in the driver, not the shared bracket code.

Same gate as every other change to this loop: at `entry_order_lifetime_bars = 1`, every existing
trade log must come back **byte-identical**. Do not build it before M19 needs it ([#16] says so
explicitly).

### What this changes about M19

The earlier note said the squeeze's resting orders "may simply not be expressible in NT8".
**That is resolved — they are expressible**, and the trap downgrades accordingly: a one-sided
rest is route 1, cheap and managed; a true two-sided OCO is route 2 and costs the unmanaged
rewrite; route 3 gets the two-sided behaviour with no NT8 work at all in backtest and differs
only live.

So the M19 design question is no longer "can this be built" but **"do I actually need native
OCO, or is resubmission enough"** — and for a Tier-1 research backtester the answer is
resubmission, with the OCO question deferred to a live port.

### What reflection cannot settle

The API surface above is fact. **None of the following is**, and none of it may be encoded in
`nqbt/sim/` until a trade list settles it — the prime directive applies here exactly as it does
everywhere else. These are tracked as [#67], and each is a one-run question in Strategy Analyzer
with a Trades export:

- Whether Strategy Analyzer honours `isLiveUntilCancelled` identically to live execution.
- Precisely when the cancel lands relative to the bar close, and therefore whether a resting
  order can fill on the same bar its cancel was issued.
- Whether a resting entry survives a session boundary, and how it interacts with
  `IsExitOnSessionCloseStrategy` / `ExitOnSessionCloseSeconds`.
- Whether the managed approach cancels a resting *opposite-direction* entry when one fills, or
  merely refuses the second fill. A managed strategy cannot hold both directions at once, but
  "cannot hold" and "cancels the resting order" are different claims and only a trade list
  distinguishes them.

Each is far cheaper to answer before an archetype depends on it than after.

---

## The standing rubric

What every change — including every milestone below — is checked against. These are ordered by
how much trouble each has actually caused in this codebase, not by general principle.

1. **Is there now more than one definition of the same rule?** The most expensive defects here
   are all this: two triggers ([#10]), two empty-log policies ([#11]), two bracket engines
   ([#12]), and a third profit factor in `cli.py` ([#63]). In a project whose premise is
   *matching an external system exactly*, a duplicated rule is a duplicated place to diverge
   from it.
2. **Does the type say what the array actually holds?** `np.ndarray` does not distinguish the
   bool grid from the float grid, and that distinction is load-bearing. See [#54].
3. **Is the expensive work outside the loop?** Already a convention (`CLAUDE.md`), and the
   measurement discipline behind it is the strongest habit in the project — keep requiring the
   number, not the argument. M9 found a 9.4% regression this way that reasoning alone would have
   shipped.
4. **Would this pass if the code were wrong?** Applies hardest to tests asserting an absence.
   M9's layering tests were written, passed, and checked nothing. Mutation-test them.
5. **Is a class earning its place, or is it a namespace?** Prefer a dataclass with `slots=True`
   for a group of values that travel together; prefer a function for behaviour that does not
   need state. Do not introduce a class hierarchy to express one archetype.
6. **Is the abstraction extracted from two examples or invented from one?** M17 gets this right
   about the bracket engine ([#38]). M20a's bracket unification is the opposite case — deleting
   a copy, not inventing a shape.
7. **Is the reasoning in the code, where it does not belong?** ([#105]) Code should be readable
   on its own terms — prefer a clearer name or a smaller function over a comment explaining an
   unclear one. Docstrings say **what** a thing is and how to use it, and stay short. A brief
   comment is fine where something is genuinely non-obvious: a subtle index, a deliberate
   deviation, a workaround. **Reasoning, justification, measurements, decision records and
   traps go in `docs/`**, with at most a one-line pointer from the source.

   **This reverses what this item used to say**, which was *"does the docstring say why, not
   what — already the house style"*. That rubric produced a package where **33% of every line
   is prose** and the four highest prose-to-code ratios are the four newest modules, while the
   oldest sit near 0.3×. The homes were always here: this file's own header claims the
   **why**, and `docs/nt8-fidelity.md` claims the fidelity evidence. The source drifted into
   doing their job. [#105] carries the migration — and it *is* a migration, not a deletion,
   because much of that prose is evidence the project paid for.

### Standing traps

- **Do not "fix" a duplicated rule by copying the corrected version across.** That is what
  created the `explain.py` bug. One implementation, called twice.
- **A byte-identity gate on short-only logs does not cover a change that is symmetric in `d`.**
  Both copies of a forked bracket reduce to today's behaviour at `d = −1` regardless of whether
  they agree at `d = +1`. Unify *before* introducing `d`, and gate the unification separately.
- **A byte-identity gate cannot see a rule that is missing from both directions**, and this is
  no longer hypothetical — it passed cleanly through all of M15 while two fill rules were
  absent from the simulator entirely ([#18]). It proves *"this change moved nothing"*, which is
  a different claim from *"the model is right"*. Only a trade list makes the second one.
- **One archetype cannot exercise the fill model.** Both of [#18]'s defects were unreachable
  from DeadCatBounce **by construction** — its trigger cap makes an unsubmittable entry
  impossible, and its reconciled window happened to contain no gapped stop exit — so neither
  was a gap in test coverage that more tests would have closed. Every new entry or exit
  mechanism is a new part of the fill model with no evidence behind it, and [#38]'s shared
  engine will inherit whatever is wrong. Reconcile per archetype; do not trust the engine
  because the first one passed.
- **Documentation must not carry a figure that goes stale.** State the rule; point at where the
  live number is produced. Reconciliation rates, leg counts, P&L and test counts all move on
  ordinary PRs, and `CLAUDE.md` is loaded into every session, so a stale number there is a
  wrong fact asserted with authority.
- **`# pragma: no cover` marks code that is never run, which is exactly where a defect can sit
  indefinitely.** The empty-log defect sat behind one, and the audit that found it turned up a
  second of the same shape ([#81]). A pragma is a claim about coverage, not about correctness.
- **A type checker introduced with a strict config and 400 errors gets switched off.** Start
  permissive on the project's own modules and tighten; do not gate CI on it in the same change
  that introduces it. See [#56], [#57].
- **Re-measure the Numba `NamedTuple` result before relying on it.** It is a property of the
  installed Numba, not of the language, and `cache=True` interacts with it.
  `tools/numba_tuple_probe.py` is the probe.
- **M20 may not move a number.** Every M20 item is behaviour-preserving. Anything that moves a
  trade log is out of scope and belongs in the milestone that intends it.
- **A prefix of a trade log is not a sample of it.** The `explain.py` defect was justified with
  "50% of trades", measured over a 200-trade prefix; the whole-window rate is 35.7%. Quote
  whole-window rates.

---

## Milestone notes

One paragraph of reasoning each. Scope and acceptance criteria are in the linked issue.

### ~~M15~~ — direction in the simulator: done ([#13])

Kept because the reasoning generalises, and because one part of it turned out to be wrong in
an instructive way.

`simulate_deadcat` was short-only in roughly eight places — stop hit, target fill, P&L,
MAE/MFE, entry trigger, entry fill test, ratchet, slippage sign. The design was **one sign
multiplier `d = ±1`, not two code paths**, because the bracket machinery carries the fidelity
evidence: the ambiguous-bar rule, `IsFillLimitOnTouch`, the ratchet and the force-flat path
are what the reconciliation actually validated, and forking gives Tier 1 and Tier 2 two places
to drift. That held — the machinery was not forked, and `_sided()` is the single exception,
picking which raw OHLC value is adverse or favourable because that is a data selection rather
than something a sign multiplication can express.

Because ×(±1.0) is exact in IEEE 754 and `fl(a − b) = −fl(b − a)` always, the gate was
**byte-identity of every short-only trade log**, chosen as stronger and cheaper than
re-running the reconciliation. **That was right about what it covered and wrong about what
that was worth.** It caught nothing because there was nothing to catch, and it is structurally
blind to a rule that is *missing from both directions* — which is exactly what [#18] then
found, twice. The gate remains correct for a direction-symmetric refactor; it is not a
substitute for a reconciliation, and the two answer different questions.

The long path was proven by porting `PullBackAndGo.cs` ([#17]) and reconciling it ([#18]) —
long-only `EnterLongStopMarket` with C# ground truth, so a long-side fill bug is found against
NT8 rather than blamed on a new strategy. **That decision paid for itself immediately**: both
defects [#18] found were in the *shared* bracket code, present since the beginning, and on an
original archetype they would have been indistinguishable from the strategy simply being bad.
Stop-and-reverse remains out of scope; see "Decisions taken".

### ~~M16~~ — the indicator-parity debt: done ([#19])

Every value is in `docs/nt8-fidelity.md` §M16 with its evidence; this is what the exercise
taught, which is the part that generalises.

**The prediction was right, and it was worth making.** M16 said to expect *seeding, not
formula*, and that is exactly what ATR turned out to be: an expanding simple average of True
Range until the period fills, then Wilder. Pure Wilder from bar 0 — the textbook form —
agreed on 89,020 of 89,330 bars, which is the dangerous kind of wrong: it looks correct
everywhere except the warm-up, and the recursion never forgets its seed.

**"Do not answer from memory" earned its keep on Keltner.** It was flagged here as the one
most likely to be silently wrong, and it was wrong in *both* halves at once — the midline is
an SMA of typical price rather than an EMA of close, and the width is the mean high−low range
rather than ATR. ATR agreed on **20 bars out of 89,330**. Any implementation written from
memory would have been wrong twice, and both mistakes produce a plausible-looking channel.

**One probe answered four issues.** `NqbtIndicatorProbe.cs` exports every candidate series
side by side from bar 0, so the questions are settled by reading a table rather than by
running an experiment per hypothesis. Exporting `ATR(1)` was the trick worth keeping: NT8
exposes no True Range indicator, but Wilder at period 1 reduces to TR exactly.

**A pin is about method as well as formula.** StdDev's rule is unremarkable — population
divisor, expanding window — but reproducing it requires a *two-pass* computation. pandas'
`rolling(...).std(ddof=0)` is algebraically identical and drifts by up to 4.2e-07. That is
far below a tick and would never show up in a result; it would simply mean the pin was not a
pin.

Still true and still unpaid: BB and KC are swept over period *and* multiplier, so the
66 MB → 595 MB lesson applies with an extra factor — **keep boolean gates only**. And
[#23]'s roll-boundary half remains a decision rather than a measurement.

### ~~M17~~ — the archetype protocol: done ([#24])

`sweep.py` used to name `DeadCatParams` in six places, so a second archetype meant forking
it. It now names none: `nqbt/archetypes.py` supplies the parameter class, the legal axes, the
toggle map, the context spec and the run function, and a new archetype registers rather than
forking.

The insight that shaped the rest was that **strategy, resolution and contract are the same
feature**: all three add an axis that sits *above* the `Dataset` rather than inside a params
class, all three need one `Dataset` per value, and all three need a nullable results column.
So it is one mechanism ([#28]), not three wrappers that diverge, landed together before the
stale DuckDB re-run ([#71]) so the schema settled once instead of three times. That is why
M13 ([#30]) and M14 ([#31]) came before [#28] rather than after it.

**What `sweep_axes` settled, worth not relitigating.** The strategy axis is a **list of
grids, not a list of archetype names** — each archetype has its own parameter class, so
`ema_period=[9, 21]` is not necessarily a legal axis of the next one, and a single grid
re-based onto another archetype would raise or, worse, silently sweep a different field. The
contract axis is **carried by `bars` itself** (one frame, or a `{contract: frame}` mapping),
because a contract axis *is* which bars; that avoids a mutually-exclusive parameter pair and
lets `dispersion.sweep_contracts` hand its frames straight in. Every grid at one axis point
**shares a single `Dataset`**, built from the union of their `ContextSpec`s — a dataset each
would multiply what the parallel path memmaps to every worker by the number of strategies,
and a test pins the call count rather than trusting it. And `combo_id` stays the grid's own
index so it means the same parameters at every axis point, which is what makes a
cross-resolution comparison a comparison; it deliberately does *not* carry across grids,
which is why `strategy` is part of the log key.

`dispersion.sweep_contracts` is now a thin wrapper over it, as its own docstring asked for.
All 48 dispersion tests passed unchanged through that refactor, and the whole capture set is
byte-for-byte identical.

Three things the landed part settled, worth not relitigating:

- **`Grid.dead_axes()` was preserved, not reinvented**, and its gate map now comes from the
  archetype — so a new archetype inherits the guard instead of getting its own version of the
  same mistake. A test asserts every gate names a real field of its own params class, because
  a typo'd gate does not raise, it just stops guarding.
- **`sweepable` reads `dataclasses.fields()`** ([#60]), not `__slots__`. This was folded in
  rather than deferred because M17 is exactly the change that would have triggered it.
- **`ContextSpec` lives in `context.py`, not beside the registry** — it describes a
  `Dataset`, and `context.py` must not import from `nqbt.sim`. Grids are keyed by
  `(kind, period)`, which is the half of [#72] that no longer needs doing.

**The results schema ([#29]) settled first**, before [#28] filled it and before the
stale-database re-run ([#71]). `strategy`, `resolution`, `contract` and `tier2` exist on both
DuckDB tables, nullable, with `batch_id` on `sweeps`; a database written before them gains
them by migration and keeps its rows. `stats.Summary` gained `session_close_share` in the
same change — measured at **0.0001 on DeadCatBounce over 1-minute continuous MNQ** (one leg
in 9,824), which is the baseline the resolution sweep is expected to move sharply. The
reasoning for the row granularity is in "Decisions taken".

The `tier2` registry field ([#25]) is not bookkeeping: per the standing constraint,
"validated against NT8" stops being a project-wide fact once originals exist. The shared
bracket engine is extracted **during** M18 ([#38]) — before is designing from one example,
after means duplicated fidelity-critical code shipped.

### M18 — EMA crossover ([#34])

The first original archetype, chosen to prove M15 and M17 because it is the cheapest thing that
exercises both: bidirectional, and it exits on a signal rather than a bracket level. **Treat it
as a known-negative control, not an edge candidate.** MA crossover on 1-minute index futures is
the most-tested idea in retail futures and is reliably unprofitable at realistic costs, so if it
reads meaningfully better than M7a's random arm the first hypothesis is a **bug** — specifically
lookahead, since crossover is unusually easy to compute one bar early. Recording that now
matters because a PF above 1 will otherwise be exciting rather than suspicious. Three defaults
are all wrong and must be fixed explicitly: use NT8's `CrossAbove(a, b, n)` semantics rather
than the naive one-bar form ([#35]) or a later NinjaScript will disagree; the entry is
market-on-next-open ([#36]), a third mechanism with no trigger price and no "no touch, no fill";
and the stop has no structural swing to anchor to, so it needs an ATR multiple ([#37]), which
makes M16 a hard prerequisite rather than a convenience. It will also break the sweep's
performance assumptions — tens of thousands of legs per combination against DeadCatBounce's
~1,400 — which is why the numpy-native summary path ([#33]) moved ahead of M10, and then
ahead of M18 itself. **That is now paid**: a combination no longer builds a DataFrame, so the
per-leg cost that would have dominated a crossover sweep is the `@njit` loop rather than
pandas. Still do a single-combination timing before running a wide grid.

### M19 — squeeze breakout ([#51])

Queued rather than scheduled; the expensive archetype. "Squeeze" means at least three things,
and fixing the definition is the first task: TTM-style (Bollinger inside Keltner — the full M16
debt), bandwidth (`(upper − lower) / mid` below a trailing percentile — Bollinger only), or
structural (inside bars — no new indicators at all). **Recommend the bandwidth form first:** one
indicator rather than three, it drops the Keltner parity question flagged above as most likely
to be silently wrong, and it is the same quantity M10.1's regime classifier wants anyway, so the
two share it instead of each inventing one. **And port `InsideBar.cs` before either** — it is
the same compression-then-break idea, needs no new indicator work beyond ATR, and is the only
version of this strategy with C# ground truth. The real structural cost is a two-sided OCO entry
model the loop lacks; the order-lifetime research above resolves that resubmission is exactly
equivalent for Tier 1. Traps: lookahead (bands must come from *completed* bars — this is the
second-easiest place in the project to manufacture a fictional edge), a high ambiguous-bar rate,
and results that cluster by volatility regime so the aggregate PF averages two populations.

### ~~The numpy-native summary path~~ — done ([#33])

`stats.summarise_legs` reads the simulation's raw `LegMatrix` and never builds a DataFrame.
`stats.summarise` stays exactly where it was, as the reference; `tests/test_numpy_summary.py`
is what says the two agree.

**Measured on the full spliced MNQ series** — 1,663,489 bars, the 8-combination grid
`tools/capture_trade_logs.py` uses, 218,164 legs, best of three:

| | per combination |
|---|---|
| frame + `summarise` (what this replaces) | 28.3 ms |
| `summarise_legs` | 9.0 ms |
| the `@njit` simulation alone | 9.3 ms |

**3.1× on a combination, and the summary is now inside the noise of the simulation** — the
19 ms of pandas is gone, not reduced. That is the whole of the 71% the profile attributed to
`trades_to_frame` plus `stats.summarise`, and it composes with the parallel speedup because
it is per-combination work rather than shared setup.

**Both paths share every statistic.** `_summarise_arrays` takes the per-trade vectors and
returns the `Summary`; the two entry points differ *only* in how they get those vectors —
`groupby` on one side, a boundary scan on the other. That is deliberate, and it is what makes
"do they agree?" a question about the grouping rather than about twenty-eight formulas. Do not
re-inline it into either caller.

**Pandas' `groupby.sum` is Kahan-compensated, and a plain running sum does not reproduce it.**
Measured: over 50,000 four-element groups of random doubles, `np.add.reduceat` disagrees with
pandas on 35% of groups and a naive accumulation on 21%, always in the last bit. The exactness
`#33` asks for is therefore only reachable by carrying the compensation term, which
`_grouped_sum` does. `tests/test_numpy_summary.py::test_the_grouped_sum_is_compensated_like_pandas`
guards it with a four-value group that sums to 0.0 naively and 2.0 compensated, and the test
above it pins that those two summations genuinely differ — verifying the gate can fail is part
of using it. The costed DeadCatBounce case in `test_the_two_summary_paths_agree_exactly` also
catches a naive sum on real trades, so this is live rather than adversarial-only.

**Everything else agrees for free, and that was checked rather than assumed.** Whole-array
`Series.sum`, `.mean`, `.std(ddof=1)`, `.max`, `.min`, `.cumsum`, `.cummax`, `.median` and
`.quantile` are all bit-identical to their numpy equivalents here (no `bottleneck` installed),
strided column views included. Only the grouped reductions needed care.

**A gapless day index is not the same as a UTC one.** `Dataset.day_codes` is each bar's
calendar day *in the index's own timezone*, because `summarise` groups daily P&L by
`DatetimeIndex.date` and that is local. On the UTC archive the two coincide, which is exactly
why reading them off UTC would have passed every test here and been an hour out on a
`Europe/London` index — the same shape as the trade-list timezone bug in
`tools/reconcile_nt8.py`. Precomputed in `context.prepare` rather than per combination: the
conversion over 1.65M bars costs about as much as a whole combination.

**The leg matrix is now a producer's output, not an intermediate.** `runner.deadcat_legs` and
`pullback.pullbackandgo_legs` stop at `trades.LegMatrix`; `run_deadcat` and
`run_pullbackandgo` are those plus the frame. `Archetype.legs` is a required registry field
beside `run`, deliberately not derived from it — an archetype registered with only `run` would
silently be the slow one in a sweep, and the symptom would be a wall clock rather than an
error.

**The schema guarantee survives.** A sweep no longer calls `trades.validate`, so
`trades.validate_legs` asserts the same invariants on the matrix — nulls in required columns,
`direction ∈ {±1}`, positive quantity, leg numbering from 1. It adds one check `validate`
deliberately omits: `exit_reason` must be in `EXIT_REASONS`. On a *frame* that column may hold
a label NT8 wrote (`Stop3`, `Exit`), but a matrix can only have come from the simulator, so a
code outside the enum there is a bug. It is written column by column with an early exit for the
same reason `validate` is — the readable `rows[:, REQUIRED_INDICES]` form copies ten columns on
every combination and cost 12% of one.

**Two things this deliberately did not change.** `run_combination` still computes its summary
the same way whether or not `keep_trades` is set, so the flag changes what is *returned* and
never what is *measured*. And `summarise` remains the definition: where the two ever disagree,
the pandas one is right.

**The evidence it moved nothing** is `tools/capture_trade_logs.py`: all 14 files
byte-for-byte identical across the change, including `sweep_serial.csv` and
`sweep_parallel.csv`, which are the summary tables now produced by the new path over 218,164
legs, and `live_summary.csv`, which is the refactored `summarise`.

**Where the next win is, if anyone wants it.** `sweep.sweep` end to end is 12.3 ms per
combination against `summarise_legs`' 9.0 — the 3.3 ms difference is `dataclasses.replace` per
combination, `params.as_dict()` and `Summary.as_dict()`'s `asdict` deep copy. Small in
absolute terms, but it is now a quarter of a combination rather than a tenth, and M18's wide
grids multiply it. Not worth doing before there is a workload that needs it.

### ~~M7a~~ — the random-entry control arm: done ([#32])

`nqbt/randomentry.py`. The methodology is in the module docstring; what belongs here is the
reasoning that outlives it and the first result, which is not what anyone expected.

**The design principle is hold everything fixed, randomize only what is under test.** The
quantity under test is *when the strategy chooses to enter*, so the null holds the bars, the
instrument, the costs, the bracket geometry, the ratchet, the force-flat rule, the direction,
the number of entry signals and the time-of-session distribution, and randomizes only which
trading day each signal lands on.

**Time-of-session matching is the load-bearing part, and it is exact rather than coarsened.**
Intraday index futures have a pronounced volume and volatility seasonality, and a bracket
built from fixed tick offsets has materially different hit probabilities in a volatile hour
than a thin one. A null scattering entries uniformly across 23 hours would trade mostly in
thin overnight bars and lose for reasons unrelated to entry quality — **it would flatter
every strategy ever tested against it**. Minute-of-session is discrete and low cardinality
against millions of bars, so exact matching is feasible and bucketing into session phases
would leave real confounding inside each bucket. That also keeps M7a independent of M10.4
([#43]), whose labels exist to stratify results rather than to condition a null.

**The day is randomized rather than matched, deliberately.** Choosing which days to be active
on is part of what an entry rule does, so it is under test; matching on it too would reduce
the question to intraday timing alone.

**The null runs the archetype's own `run` with a substituted signal.** `run_deadcat` and
`run_pullbackandgo` gained a `signal=` override for this, and `Archetype` gained a `signal`
field so the registry can hand over the real signal to match against. That is what makes the
two arms share one `simulate_deadcat` call rather than two implementations that were reviewed
and found to agree — the standing trap about forking the bracket applies to a control arm
exactly as it does to an archetype.

**Many draws, not one.** A single random-entry backtest is the folk version of this idea and
is not evidence. The output is a Monte Carlo randomization test in the same shape
`spread_vs_resampling` already uses. Two differences from that test, both real: this one
**may** report time-dependent statistics, because every draw is a genuine simulation over
real bars rather than a relabelling; and its p-value carries the add-one correction, so a
statistic no draw beat reports 1/(n+1) rather than claiming zero.

#### The first result, which reframes DeadCatBounce

Costed MNQ from 2024 (914,700 bars, 1.24 commission, 1 tick slippage), 500 draws:

| statistic | observed | null median | percentile | p |
|---|---|---|---|---|
| profit factor | 0.666 | 0.551 | 99.6 | 0.012 |
| expectancy | −10.24 | −14.78 | 99.8 | 0.008 |
| win rate | 32.2% | 29.3% | 99.8 | 0.008 |

**The entry rule is better than random and still loses money.** That is the third of the
three diagnoses this milestone was built to separate — *there is signal; the loss is coming
from costs, hold time or bracket geometry rather than from entry selection* — and it is a
different conclusion from "unprofitable, therefore worthless", which is what every previous
number supported. It does **not** make DeadCatBounce tradeable and does not change its role
as the test fixture; it changes what the next question about it is.

Three caveats, recorded so the result is not over-read. It is **one pre-specified parameter
combination on one root**, not a sweep, so no multiple-comparisons correction applies and
none is implied. **The arms match on signals and diverge on fills** — 74.4% against 47.7%,
because the `min(Low[0], Close[0] − 2 ticks)` trigger sits just under an inverted hammer and
well below an average bar — so per-trade rates are the fair comparison and `net_pnl` is not;
that is why the defaults are `RATE_STATISTICS` and why both trade counts sit on every row.
And the rule being tested is *bar selection*, which carries bracket geometry with it, so
"better than random" is a property of the whole rule rather than of directional timing alone.

On that last point the win-rate result is the more informative one: an R-multiple bracket
scales stop and target together, so win rate is close to scale-invariant and a 3-point
edge is not obviously explained by the strategy's bars simply being wider. **A null that also
matched the risk distribution would isolate pure directional timing** and is the natural
refinement — worth doing before anyone acts on this, not before it is believed.

### M7 — the null, split into M7a and M7b ([#32], [#50])

Three tools answering different questions: `walkforward.py` tests whether a parameter choice
survives data it did not see, `montecarlo.py` tests whether an equity path was luckier than the
trades justify, and `randomentry.py` supplies the null the other two cannot — same bars, same
bracket geometry, same costs, same exit logic, entries drawn at random. **M7a was pulled ahead
of the archetypes.** The roadmap originally scheduled it after M11 because it shares machinery
with §11.4's permutation test, but **that sharing is symmetric and the interpretive need is
not** — build the null first and M11's guard inherits it, whereas the *need* arrives the moment
a second archetype exists. Against PF 0.746 it separates three diagnoses that currently look
identical: worse than random (the signal is real but inverted), indistinguishable from random
(stop tuning this archetype), and better than random but not past costs (attack costs, hold time
or bracket size). Permuting an existing trade sequence cannot distinguish any of those, because
it takes the entries as given. **It must be matched on direction** as well as count and time of
day, or a long-only null against a bidirectional archetype measures market drift.

### M10 — the conditions the review needs and we lack ([#39])

The review is meant to score trades against "overall trend, MAs, volume, directional vs
consolidation, time of day", and three of those five have no implementation. Kaufman's
efficiency ratio ([#40]) is the first classifier — bounded 0–1, ~3 lines of numpy, no TA-Lib
dependency and therefore no NT8-mismatch problem, and the band between its thresholds gives the
unclassifiable no-trade state for free rather than as a special case. **Volume is one quantity
and its decomposition, not three conditions** ([#41]): absolute volume is the raw count, time of
day is its dominant systematic component, and relative volume is absolute with that component
divided out. Treating all three as independent findings confirms one signal three times.
Absolute earns its place regardless because it alone answers **execution feasibility** — a rule
that only works in thin overnight bars looks fine on relative volume and is untradeable — but
that same secular trend means a raw absolute threshold must not be a sweepable filter, since
expressing it as a trailing percentile just makes it relative volume again. Time of day ([#43])
is a first-class dimension for sweeps as well as the review, **measured in ET, never UTC**, or
the cash open smears across two buckets for half the year. It doubles as a sweepable entry
filter: a rule that only works at the open reads as unprofitable when averaged over 23 hours.

### M11 — manual trade review ([#44])

The stated goal. Import real trades, annotate each against the market context at its entry bar,
stratify realised P&L by condition. The source is the **NT8 executions grid** ([#45]), not the
Control Center log: `Position` gives trade boundaries (`-` = flat) and `Name` gives the exit
reason (`Stop1..4` vs `Exit`). The log is rejected because its stop levels are ATM template
defaults dragged to intent seconds later — in the sample, 29919 against a 29769 entry, computing
150 points of risk on a trade that actually risked ~14. Recovering intent would need a heuristic
like "the first stop level that is not the template default", which is exactly the kind of rule
that silently corrupts a dataset. **A wrong R is worse than no R, because it looks like a
measurement**, so `r_multiple` is deliberately not reconstructed. The biggest annotation trap is
back-adjustment ([#46]): it shifts historical prices by hundreds of points, so annotating a real
trade against the continuous series succeeds at the lookup and is silently wrong at every
comparison — use the raw or per-contract series. The statistical guard ([#48]) is not optional:
a few hundred trades against a few dozen conditions is a multiple-comparisons machine, and a
review without a minimum stratum size, a permutation test and a holdout is worse than no review,
because it produces confident, specific, wrong conclusions that feel earned. Free-text notes are
stored but structurally excluded from evaluation ([#49]) — written knowing the outcome, they
would yield perfectly circular findings.

### M12 — web GUI ([#52])

Long term, and gated on the review's outputs being stable or the interface churns with them.
**The governing lesson is the CLI's:** `nqbt sweep` and `nqbt report` were dropped because they
would have been a second, lossier front door to things the Python API already does better. A GUI
carries the same risk at ten times the size, so it must call the same functions and define no
statistic of its own. Streamlit for the read-only views, explicitly as a throwaway, rather than
starting with FastAPI and discovering the front end is the whole project.

### M13 — bar resolution as a sweep axis ([#30])

**The existing 1-minute archive is sufficient — no re-export, no AddOn change.** OHLC
aggregation is associative, so a 5-minute bar built from five 1-minute bars is *bit-identical*
to one NT8 builds from ticks; reaching for `data/tick/` would be the more-precise-than-NT8 error
the prime directive forbids. The trap is anchoring: bucket by **minutes since the session open**,
never wall clock. For the periods anyone actually sweeps this is harmless, and **that
coincidence is exactly why it must be tested rather than assumed**. The precise condition was
established while building [#30] and is sharper than the one this file used to state:
agreement needs a boundary at the session *open* **and** its *close*, so with 18:00 ET at
1,080 minutes past midnight and 17:00 ET at 1,020, it is `N | gcd(1080, 1020)` — **N divides
60**. Dividing 1,080 alone is not enough: 45 does, and still diverges, because a wall-clock
grid then runs a bucket from 16:45 to 17:30 through the maintenance break. Whether NT8 anchors the same way is settled by the *existing*
Tier-2 reconciliation at that resolution, not by importing NT8's coarse bars. Resolution changes
the strategy, not just the sampling — order lifetime, the ratchet and `bars_required_to_trade`
are all per-bar — so it must be a first-class results column, and comparing profit factor across
resolutions at the same period number is meaningless. Expect the ambiguous-bar rate to climb
well above 1-minute's 3.4%; **if a coarse resolution looks profitable, check that first.** Cost
is self-limiting: 1, 2, 5 and 15 minutes is ≈1.8× a 1-minute sweep, not 4×.

### M14 — per-contract sweeps ([#31])

**`nqbt/dispersion.py` has landed, and [#28] has since absorbed its loop.**
`sweep_contracts` is now a wrapper over `sweep.sweep_axes` that keeps what this module is
actually for — the front-month windows, the coverage join, and the statistics below — and
moves `contract` back to the leading column because that is its own promise. All 48 tests
here passed unchanged through that refactor, which is the evidence it moved nothing.

Two things the build settled that are worth not relitigating. **Both spread measures are
reported, because the milestone has two jobs that disagree** — the IQR answers "does the bulk
of contracts differ?" and the range answers "is any one contract extreme?", which is the
data-integrity question below. Reporting only the robust measure would discard the signal
this milestone is most useful for, and a test pins that a single rogue contract moves the
range while leaving the IQR alone. And **`stats.trade_statistic` was added rather than a
second profit-factor implementation** — the permutation test needs thousands of evaluations
and `summarise` is too slow, so the fast path shares `_ratio` and a test asserts exact
equality with `summarise` on real logs. That is the same discipline [#33] went on to apply to
the numpy-native summary path, worked out here first because this is where it became necessary.

**The first result is the argument for the framing.** DeadCatBounce's per-contract variation
on MNQ is indistinguishable from relabelling the same trades, on both measures, even though
the best contract reads roughly double the worst.

The original reasoning follows, and still holds.

`sweep.sweep()` already accepts a single contract's frame, so what was missing is the
cross-contract table, a `contract` column, and the framing. **Report the spread, not the
winner:** a contract is ~3 months of front-month, so "best contract" is very nearly "best
quarter", and picking the best of 19 × N combinations is the multiple-comparisons trap §11.4
guards against. The useful output is how much performance varies and whether that variation
exceeds what resampling the same trades would produce. Three things it does that M7's
time-slicing does not: it is a **data-integrity instrument** (an outlier contract is usually a
bad roll date or a hole, not a market insight, and given how much archive work came from exactly
such defects it is a cheap standing check); it uses **raw, not back-adjusted** prices, which is
the only way to test round-number stops; and it contains **no roll**, so it is directly Tier-2
reproducible — the cheapest route to the outstanding NQ reconciliation ([#66]). Default to the
**front-month window**; full contract life overlaps its neighbours and double-counts calendar
days. Report `bars`, `sessions` and `trades` per contract, or a PF from 30 trades sits in the
same column as one from 400.

### M20b — typing and tooling ([#53])

The package annotates well — only 5 functions have an untyped parameter and only 2 lack a return
type — but **nothing checks any of it**, so the annotations are documentation that happens to be
in the type position. Note this section's earlier claim that no linter or type checker existed is
**stale**: `[tool.ruff]` and `[tool.mypy]` are both configured in `pyproject.toml` and
`.github/workflows/checks.yaml` exists. What is missing is that **nothing runs them** — CI runs
pytest and `pymarkdown scan .`, and nothing else. **The gap that matters is dtype, not
coverage** ([#54]): there are **56 bare `np.ndarray` annotations across 7 modules and zero uses
of `numpy.typing.NDArray`**, and in this codebase the element type is load-bearing in a way that
is invisible today. `MovingAverageGrid.below` is `bool` and `.values` is `float64` — the whole
66 MB vs 595 MB decision is that distinction, and both are annotated `np.ndarray`.
`SessionInfo.trading_day` is `datetime64[D]` and `.in_session` is `bool`; both are `np.ndarray`.
The `@njit` loop's `out` is a `float64` matrix into which `exit_reason` and `direction` are
written as floats and mapped back to strings later — the one place a wrong dtype is silently
lossy. Define `FloatArray`/`BoolArray`/`IntArray` once rather than spelling `NDArray[np.float64]`
56 times; that is the same extract-and-reuse rule applied to types. **Do not annotate inside the
`@njit` functions expecting Numba to use it** — it infers from the call, ignores the annotations,
and a wrong one there is worse than none because it reads as a guarantee.

### M20c — structural cleanups ([#58])

Worth doing when adjacent rather than as a project. `simulate_deadcat` takes 23 parameters and
`_write` takes 18, all passed positionally at 8 call sites, where one transposition writes
plausible numbers into the wrong columns ([#59]). The question was whether Numba tolerates a
`NamedTuple`, and it is **measured, not assumed**: bit-identical result, 1.01× the scalar version
over 5M iterations, and `@njit(cache=True)` still compiles — which matters because the disk cache
is what makes parallel workers cheap. The rest, in descending order of value: `sweep.SWEEPABLE`
reads `__slots__` rather than `dataclasses.fields()` ([#60]) and will break quietly at M17 by
dropping an axis rather than raising; `results.best()` interpolates `by` into SQL ([#61]);
`bars[...].to_numpy(np.float64)` appears 12 times ([#62]); `_cmd_run` reimplements `per_trade`,
profit factor and max drawdown inline, a **third independent definition** that already differs
from `stats` in a corner ([#63]); and `explain.py` and `cli.py` are untested ([#64] — `explain.py`
gained `tests/test_explain.py` during M20a, so this is now `cli.py` alone). **Resist adding
classes beyond the parameter blobs and M17's protocol**, and specifically resist
`numba.jitclass` inside the loop: it carries real compilation and boxing costs, and the loop is
23% of a combination, so there is nothing to win and fidelity-critical code to lose.

### Moving-average axes — what is sweepable and what is not

**Already sweepable, jointly, with no work needed:** every field of `DeadCatParams` except
`target_r_multiples` is a legal axis, periods and on/off toggles alike, and `Grid.dead_axes()`
refuses a period axis whose toggle is off in every combination. Two dimensions are **not**
reachable. **MA kind as an axis** ([#72]) — kind is fixed by field name, so "what if the fast
filter were an EMA rather than an SMA?" cannot be asked, and only `nt8_ema` and `nt8_sma` exist.
The trap is the prime directive: a new kind must match NT8's recursion rather than the textbook
one, which is exactly where TA-Lib's EMA already differs through seeding alone. **Multi-timeframe
MAs** ([#73]) — everything is computed on the 1-minute close, so a coarse MA gating a 1-minute
entry is not expressible. The trap there is lookahead: the coarse bar covering 14:00–15:00 is not
knowable until 15:00, so the value must be stamped from the *previous completed* coarse bar or
the backtest reads the future. **Both get much cheaper once M16 and M17 land** — M16 establishes
the pin-it-against-NT8 procedure a new kind needs, and M17's `required_context` already has to
key grids by `(kind, period)`. Reconsider after those rather than now.

### Tier-2 verification — [#67] is all that remains ([#65])

**~~A second long-side contract~~ ([#92]) — done.** `MNQ 06-24`, fully liquid: 1,792 of 1,792
legs joined, **100% identical entry price**, 99.61% identical on every field. The residual is
dominated by the L4 runner exiting later in NT8, which is the same
`StopTargetHandling.PerEntryExecution` artefact already recorded against S4 — now seen on
both sides of the market, which makes it a property of NT8's per-entry handling rather than
of either strategy.

**~~Reconcile NQ against NT8~~ ([#66]) — done.** 1,105 of 1,112 joined legs identical on
every field (99.37%), and **no instrument-dependent behaviour was found**, which was the
open question. NQ no longer inherits its confidence from MNQ.

That run also corrected a rule this project had been carrying since the first
reconciliation: **the trade-list export is in the machine's display timezone, not UTC.** The
original evidence — an empty 22:00 hour — was sound but window-specific, because
December–March is GMT and London coincides with UTC there. Over the summer MNQ 06-24 window
the difference is a full hour, and parsing as UTC joined 332 of 1,800 legs against 1,792 of
1,792. **A wrong timezone parses cleanly and reads as a failed reconciliation**, so it is now
explicit configuration in `tools/reconcile_nt8.py` rather than an inferred default.

`tools/reconcile_nt8.py` is the reusable mechanism these produced. Per the standing rule that
each archetype earns its own reconciliation, the next one does not start from scratch.

**Settle the four order-lifetime questions** ([#67]) that reflection cannot answer — listed
above. It is the only NinjaTrader item left, and it gates M19, which is queued rather than
scheduled.

---

## Decisions taken

**New archetypes: infrastructure now, one archetype now, M11 keeps its slot.** `CLAUDE.md`
records "which archetype is actually worth trading is a later question" and treats
DeadCatBounce as the test fixture. Adding EMA crossover and squeeze breakout partly reverses
that, so the extent was decided deliberately rather than by drift: **the infrastructure lands
now** (M15, M16, M17 — which is where essentially all the cost is, and much of which M9 and M10
needed anyway), **one archetype is built to prove it** (M18), and **M11 is not displaced**. The
second archetype (M19) is specified and queued, not scheduled.

The reasoning is that the infrastructure is not archetype-specific work at all. M15 is a
`direction` field M9 was already adding; M16 is a debt `indicators.py` recorded from the start;
M17 is the same axis-above-the-`Dataset` mechanism M13 and M14 already needed. Only M18 and M19
are genuinely new scope, and they are the small part.

**Strategy development stays in Python; the C# port happens on promotion, not on creation.**
Decided explicitly. An archetype is designed, swept, stratified and — most often — discarded
without any NinjaScript existing. Only one that looks like it works earns the port back to C#,
at which point the Python is the specification and the usual leg-for-leg reconciliation applies.

The reasoning is throughput: most archetypes will not survive contact with costs, and writing a
NinjaScript for each one before knowing that spends NinjaTrader time — the project's scarcest
resource — on candidates that are about to be thrown away.

Three things this buys and one it costs, all worth recording:

- The prime directive **still binds during development**, and this is what protects the eventual
  port. A Python archetype that drifts into intrabar precision cannot be reconciled when it is
  finally written in C#, so the exploration would be wasted rather than merely unvalidated.
  "It's only Python for now" is not a licence to exceed NT8's fidelity.
- The design must be **checked against what NT8 can express while it is being written**, not at
  port time. That is what the expressibility checklist is for, and it is why the order-lifetime
  research was done now rather than when M19 starts.
- **Tier-1-only status becomes per archetype and must be visible**, not remembered — M17's
  registry field and results column. A ranking that mixes a reconciled archetype with an
  unpromoted one is comparing a measurement with an assumption.
- The cost is that a promising Python result carries **unquantified port risk** until the
  reconciliation runs. Accepted, on the grounds that it is only paid for candidates worth paying
  it for.

**Promotion criteria — what "we believe we have something that works" should mean.** Left loose
it will collapse into "the profit factor looked good", which is the multiple-comparisons trap
§11.4 exists to prevent, and the port is expensive enough to be worth a bar. A candidate should
clear the null before it earns C# time: beat the random-entry arm ([#32]), survive walk-forward
([#50]), and hold up across contracts rather than resting on one quarter ([#31]). Not a gate to
enforce mechanically, but the checks to have run before spending NinjaTrader time.

**`PullBackAndGo.cs` is ported before any original is built.** The alternative was to let EMA
crossover be the first exercise of the new long-side code. Rejected: a long-side fill bug found
against `PullBackAndGo`'s NT8 trade list is a bug, whereas the same bug found on an original
archetype is indistinguishable from the strategy simply being bad. It is long-only
`EnterLongStopMarket`, the exact mirror of DeadCatBounce's entry, so it tests the new path
precisely and it has ground truth. `InsideBar.cs` and `InsideBarTrailing.cs` remain unported and
are the cheapest further archetypes available.

**The bracket engine is extracted during M18, not before it and not after.** Before is designing
an abstraction from one example; after means fidelity-critical code sat duplicated on `main`.
Extracting mid-M18 with byte-identity as the gate gets an abstraction designed against two real
shapes without the duplication ever shipping. See [#38].

**Archetypes are flat between trades; stop-and-reverse is not supported.** The loop's
`in_position` boolean assumes flat-to-flat and reversal collides with the one-bar entry
lifetime. Recorded as a deliberate limitation rather than discovered as a position-tracking bug.
See [#13].

**Roll dates need no reconciliation against NT8.** All 18 MNQ roll dates moved when the archive
made volume crossovers detectable, which raised whether Tier 1 and Tier 2 still agree across a
roll. Decided: not worth chasing. NT8 merges contracts on the rollover dates **configured in its
Database window**, not on observed volume, so it is a setting rather than a measurement. It is
ground truth for fill semantics, which is what the prime directive is about; it is not ground
truth for when the market actually rolled. A data-derived crossover can reasonably be *better*
than NT8 here without that being a fidelity violation.

Residual risk, recorded rather than dismissed: a spliced-series result cannot be reproduced in
Strategy Analyzer bar-for-bar around a roll. If a sweep that crosses one ever produces something
surprising, the roll boundary is a candidate explanation, and the segment tables in
`nqbt splice --diagnostics` are where to look first.

**One `sweeps` row per axis point, tied by `batch_id`** ([#29]). A run varying strategy,
resolution or contract is several **datasets**, and `bars`, `first_bar` and `last_bar` are
properties of a dataset — one row spanning nineteen contracts could not honestly fill them,
and sweep-level tags would have to read "varies", which is the state that makes the tag
useless exactly when it matters. So each axis point writes its own row with its own honest
counts, and a nullable `batch_id` says which rows were one experiment. Without it the only
way to regroup them is `created_utc` plus a matching `axes` blob, which is fragile in the
direction that silently merges two experiments.

Two things the build settled, both of which were latent bugs rather than choices.
**`save_sweep` now inserts by name**, because `ALTER TABLE` appends the new columns at the
end while a fresh `CREATE TABLE` declares them in the middle — one positional statement
cannot serve both, and `root`/`instrument`/`strategy`/`contract` are four adjacent VARCHARs,
so a transposition stores a plausible row rather than raising. That is the same rule M9
applied to `combos`, arriving at `sweeps` for the same reason. And **the axis columns are
migrated explicitly** rather than left to `_append_or_create`'s drop-what-you-do-not-know
policy: dropping a *statistic* leaves a visible gap, which is the accepted trade, but
dropping `contract` does not leave a gap — it relabels the row as a different run.

**Pin the dtypes when a tag can be null.** DuckDB types a new table from the frame that
creates it, and an all-null `object` column infers as **INTEGER** — so a first sweep over the
spliced series, where `contract` is null by definition, would have created `combos.contract`
as an integer column that no contract name could ever afterwards be inserted into. Measured,
not reasoned about; `tests/test_sweep_stats.py` pins it.

**Stored sweeps — drop and re-run, not yet** ([#71]). Everything in `results/sweeps.duckdb` was
computed against a continuous series with different roll dates, so those rows are not comparable
with anything generated now. They are not wrong, they are answers to a different question, and
nothing reads them automatically. Clear the table and re-run at the point something actually
needs to query it — most cheaply once M10's labels exist, so the re-run produces stratified
results rather than needing a third pass.

**Trade source format — deferred, by design.** An example will arrive; until then the importer is
specified as an adapter boundary ([#45]) rather than around a guessed layout. Everything upstream
of the example — the schema (M9), the conditions (M10), the annotation and review machinery — is
independent of the format and can be built first.

**Trade source — the NT8 executions grid**, with the Control Center log rejected. The review
reports dollars, points and exit reason; `r_multiple` is deliberately not reconstructed.

**Discretionary context — recorded, not analysed** ([#49]). Stored, viewable, and structurally
kept out of the evaluation path in a sidecar table so it cannot reach a `groupby`.

**Coverage — measured, not decided** ([#45]). Whether trades fall inside cached instruments and
dates becomes a report the importer emits, so the answer arrives as data with the first real
file. The only design consequence is that out-of-coverage trades must be excluded loudly rather
than dropped quietly. Resolved for the sample: MNQ runs to 2026-08-10 19:55 UTC, past the
16:58–17:07 trade window. Note the export lags live by roughly two hours, so the most recent
session is always partly unavailable.

**Timezone — NT8 display time is the machine's local zone**, `GMT Standard Time`, so BST (UTC+1)
in summer. Confirmed end-to-end: converting the sample's eight fills to UTC and mapping each to
the bar stamped at the next whole minute puts every one inside its bar's high/low range, with the
17:00:29 stop landing exactly on the 17:01 high. That simultaneously validates the conversion,
the end-of-bar alignment rule, and coverage. It should still be explicit configuration rather
than an inferred default — a wrong zone shifts every trade by hours without erroring — but the
default is now known to be right for this machine.

---

## Still open

- **Sample size.** How many real trades exist determines whether [#48]'s guard leaves anything
  standing. A few dozen will not support stratification by more than one or two conditions at a
  time, and knowing that early sets expectations for what the review can honestly deliver.
- **Which series to annotate against.** The sample trades a single contract, `MNQ 09-26`.
  Annotating against the per-contract cache sidesteps back-adjustment and roll-date questions
  entirely and is almost certainly right; the continuous series only earns its place if a review
  needs indicators with lookbacks that cross a roll.
- **Documentation must not carry figures that go stale.** State the rule; point at where the
  live number is produced — `docs/nt8-fidelity.md` for agreement rates, a `pytest` run for the
  test count, `nqbt splice --diagnostics` for bar and roll counts. `CLAUDE.md` loads into every
  session, so a stale figure there is a wrong fact asserted with authority, and these numbers
  move on almost every fill-rule change.
- **`verification/` is gitignored in its entirety** ([#91]), including its `README.md` — which
  `CLAUDE.md` cites as the authority on what the stored captures mean. The CSVs are
  regenerable; the prose is not, and it exists on one machine.

[#9]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/9
[#10]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/10
[#11]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/11
[#12]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/12
[#13]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/13
[#16]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/16
[#17]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/17
[#18]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/18
[#19]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/19
[#20]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/20
[#21]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/21
[#22]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/22
[#23]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/23
[#24]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/24
[#25]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/25
[#26]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/26
[#27]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/27
[#28]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/28
[#29]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/29
[#30]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/30
[#31]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/31
[#32]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/32
[#33]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/33
[#34]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/34
[#35]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/35
[#36]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/36
[#37]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/37
[#38]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/38
[#39]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/39
[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#41]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/41
[#43]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/43
[#44]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/44
[#45]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/45
[#46]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/46
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
[#49]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/49
[#50]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/50
[#51]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/51
[#52]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/52
[#53]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/53
[#54]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/54
[#56]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/56
[#57]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/57
[#58]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/58
[#59]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/59
[#60]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/60
[#61]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/61
[#62]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/62
[#63]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/63
[#64]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/64
[#65]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/65
[#66]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/66
[#67]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/67
[#68]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/68
[#69]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/69
[#70]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/70
[#71]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/71
[#72]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/72
[#73]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/73
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
[#75]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/75
[#76]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/76
[#81]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/81
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
[#92]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/92
[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
