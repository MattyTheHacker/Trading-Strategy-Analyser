# Roadmap

**How this file relates to the issue tracker.** The issues carry **everything that
changes** — scope, acceptance criteria, checklists, ordering, dependencies and status. This
file carries **what stays true after the work lands** — the findings, the constraints that
span milestones, the traps that cost real time, and the decisions taken so they are not
silently re-litigated. When the two disagree about scope or order, the issue wins; when they
disagree about reasoning, this file wins.

**Plans do not live here.** Ordering is GitHub's `blocked-by`/`blocking` dependency graph,
status is the issue's own state, and grouping is its epic and milestone. This file used to
carry a hand-maintained order-of-work table; it duplicated all three, went stale on every
landing, and was removed for that reason. To see what is next, ask the tracker:

```bash
gh issue list --state open --label next-up
gh issue list --state open --milestone "Phase 3 — Review system"
gh issue view <n>                       # blocked-by / blocking / sub-issues
```

Four things live here and nowhere else, because an issue is the wrong home for them: the
**standing constraint** and its expressibility checklist, the **order-lifetime research**, the
**standing rubric**, and the **decision record**. A closed issue is not read; a finding that
outlives its milestone therefore belongs in this file rather than in the issue that produced
it. Everything else is a paragraph of context with a link.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the
project's own docs first, [trading_concepts.md](trading_concepts.md) Part II second. The
discretionary-practice notes are a source of framing and of numeric definitions we lack, not a
source of priorities.

---

## Why the order is what it is

The order itself is in the tracker (see above). What follows is the reasoning behind it,
which the tracker has no field for.

**Why the order looks like this.** The request was "add EMA crossover and squeeze breakout",
but neither was reachable and neither was where the cost is: the simulator was
**short-only** (M15, now paid), the indicators they need have an unpaid NT8-parity debt
(M16), and `sweep.py` is hardcoded to `DeadCatParams` (M17). That infrastructure is ~all the
work; the archetypes themselves are then small. It also pays for the NinjaScripts written and
never ported — `PullBackAndGo.cs` is now done, leaving `InsideBar.cs` and
`InsideBarTrailing.cs`, both long-capable and both using `ATR()`.

**Why M16 left the code queue.** M16 was scheduled ahead of M17, but its three substantive
sub-issues are each *"read the value out of NT8 and pin it"* — the milestone's own instruction
is **do not answer from memory**, so hand-rolling
the recursions before the readings exist is precisely the failure it was written to prevent.
That makes M16 NinjaTrader time, and it now shares that constraint with [#66] and [#67].
M17 has no NT8 dependency, is an equally hard prerequisite for M18, and is therefore the
better use of code time. **Split the queue by resource, not by milestone number.**

Work needing NinjaTrader time and work needing code time form two queues, and neither
blocks the other in the general case — though a single milestone can need both, as M18 did.
The `needs-ninjatrader` label is the live split; do not restate its contents here.

**A booked NinjaTrader session pays for itself several times over, and the reason is not the
tickets it closes.** The 2026-08-16 session closed M16 and both outstanding reconciliations,
and it found two things reasoning would not have: Keltner matching neither half of the common
definition, and the trade-list export being in the machine's display timezone rather than UTC.
Both were invisible from the Python side. Book the session for the questions, not the queue —
`gh issue list --label needs-ninjatrader` is what is actually outstanding.

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
both had been live for the entire life of the project. **M18 confirmed it, and confirmed that
two archetypes are not enough either:** its market-on-next-open entry reached a rule neither
port could — an entry whose protective stop lands at or through its own fill — because both
ports place the stop against a trigger the fill is defined relative to. Each new mechanism is
a new part of the fill model with no evidence behind it yet, and `bracket.py` inherits
whatever is wrong. This is the argument for reconciling each archetype rather than trusting
the shared engine because the first one passed.

**Cheap, and unblocked:** porting `InsideBar.cs` and `InsideBarTrailing.cs`. Both have C# ground truth, which makes them the cheapest *trustworthy*
archetypes available, unlike M18 and M19. `InsideBar` is the structural form of the squeeze
idea and is worth porting before M19 is built from scratch. `InsideBarTrailing` is the second
consumer of `EXIT_SIGNAL`, which M18 has now made a working exit rather than a reservation —
and it is the first chance to check the signal exit against a trade list.

Deliberately unscheduled work carries no label of its own — the reasoning for each is in its
milestone note below, and the issue is the record of whether it is queued.

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
- ~~**M10.4**~~ ([#43]) — **done, and measured.** The final session phase has *structurally*
  forced exits, so a time-of-day stratification will show it as anomalous; **that is an
  artefact, not a finding**, and any result touching the last phase has to separate "this hour
  trades badly" from "this hour's trades were closed by the clock". `timeofday.FORCED_EXIT_PHASE`
  names the phase so a caller can exclude it. On costed MNQ from 2024 the effect is real and
  small — `session_close_share` reads 0.0016 on `CLOSE` against 0.0001 overall, because a
  1-minute DeadCatBounce holds for minutes. Expect it to matter at 15 and 30 minutes.
- **M18 and M19** ([#34], [#51]). The prediction here was that crossover, holding until an
  opposite cross, would take a large fraction of its exits from the clock. **Measured: 1.0%**
  on costed MNQ from 2024 at EMA(9)/EMA(21). The reasoning was sound and the premise was
  wrong — crosses on 1-minute bars are frequent enough (one signal every ~22 bars) that holds
  end long before the session does. Expect the share to climb with the MA periods and with
  bar size, and read it rather than predicting it. A squeeze rests orders, which must be
  cancelled at the flatten point.
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
3. **Is the expensive work outside the loop?** Already a convention
   (`.claude/rules/sweep-and-context.md`), and the measurement discipline behind it is the
   strongest habit in the project — keep requiring the
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

### The trade-log gate, and the two times it was wrong ([#113])

`CONTRIBUTING.md` § "The trade-log regression gate" is the procedure and
`.claude/rules/regression-gate.md` carries the rules. This section is the evidence behind both — it lived in `CLAUDE.md` until plans and
findings were separated, and it is here because a finding outlives the milestone that produced
it.

**The float64 precision problem was on the read side
all along, and was blamed on the write side until #113.** Measured on the 1,664-leg
`live_mnq.csv` capture, 18,304 float values across 11 columns:

| | read default | read `round_trip` |
|---|---|---|
| write default | 342 moved | **exact** |
| write `%.17g`  | 576 moved | **exact** |

Read the diagonal, not the margins. `float_precision="round_trip"` is what makes the gate
correct — with it *either* writer is exact. `%.17g` on its own fixes nothing, and paired
with the default parser it makes matters **worse**, because 17-digit text is precisely what
a lax parser mis-rounds. `float_precision="high"` is not enough either; it fails the same
way. The `%.17g` is kept because it is explicit and costs nothing, **not** because it is
load-bearing — the earlier note claiming it was, and citing "4 of 1,664 `r_multiple`
values", was measuring the reader and attributing it to the writer.

Until #113 the gate read with a bare `pd.read_csv`, so **a one-ULP difference was invisible
to it** — a two-byte textual change in a captured log reported `BYTE-FOR-BYTE IDENTICAL`.
`tests/test_trade_log_gate.py` now pins that it cannot regress.

**Every historical claim was re-run through the fixed gate (#113) and all of them hold.**
One capture script was run at each commit rather than each commit's own copy, so the
harness is a constant and any difference is library code; `prepare`'s signature is
unchanged across M9, M15 and M20a, and only its module moved, so one shim covers them all.

| claim | commits | gate | `sha256` |
|---|---|---|---|
| M9 move | `6975a56`→`f71baa3` | identical | identical |
| M9 schema | `f71baa3`→`8b2c5ab` | pre-existing columns identical | differ (3 columns added) |
| M15.1 sign | `4be9980`→`96be12a` | identical | **differ — see below** |
| M15.4 PullBackAndGo | `cc1be25`→`cb2e2c7` | identical | identical |
| M20a | `f992c05`→`9caf653` | identical | identical |
| M15.2/3 cancel | `96be12a`→`cc1be25` | 10 files differ | differ |
| M15.5 fills | `cb2e2c7`→`0871831` | 14 files differ | differ |
| #113 ruff auto-fix | `2243779`→`752155c` | identical | identical |

**#113 was gated retroactively (2026-08-19), because it should not have been ungated.** A
"Ruff auto-fix" PR reached into the `@njit` loop: `simulate_deadcat`'s MAE/MFE tracking went
from `if run_high < high[i]` to `run_high = max(run_high, high[i])`, and `archive.py`'s
merge inverted the branch that implements "the newest bar may insert but never overwrite".
Both are equivalent on inspection — and inspection is not the gate. All 14 files come back
identical on both the gate and `sha256`. **The lesson is where the change was, not what it
was:** a lint PR is the last place anyone looks for a simulator change, so read what an
auto-fixer touched under `nqbt/sim/` before merging, not after.

The last two *should* differ — force-flat cancellation removes real legs (113,164 → 113,116)
and M15.5 changed fill semantics. Both are the fix working, not a regression.

**M15.1 is numerically identical but not textually identical, and that is new information.**
`d = ±1` turns `0.0` into `-0.0`, so 6,908 values across `gross_pnl`, `net_pnl`,
`r_multiple`, `mae_points` and `mfe_points` flip their sign bit. **Every one of them is
zero** — verified, none non-zero — and `-0.0 == 0.0`, so sums, the `pnl == 0` scratch test
and every statistic are unaffected. The right phrase for M15.1 is therefore *numerically*
identical; only the CSV text moved.

That is also why **`sha256sum` is a cross-check, not the gate**. It is strictly stronger
than `assert_frame_equal(check_exact=True)` and will flag a benign signed zero as a
difference. Use it to catch the gate itself being broken — it is code, and it has been
wrong — but when the two disagree, find out which kind of difference it is before believing
either. Verifying the gate can still *fail* is part of using it, and a pandas round-trip is
the wrong way to do that: perturbing a value via `read_csv`/`to_csv` trips a *collateral*
difference and reports a column you did not touch, which reads like success. **Perturb the
CSV text directly**, one field, and check the reported column is the one you edited.

### ~~M9~~ — the trade-log schema: done

`nqbt/trades.py` is the contract between every producer of a trade log — the jitted
simulation today, an importer for real NT8 executions under M11 — so that a statistic computed
over one means the same thing computed over the other. It knows nothing about strategies, bars
or indicators, and a test enforces that by import analysis rather than by habit.

**One row per leg exit, not per trade.** A four-leg entry that scales out at three targets and
trails the runner produces four rows sharing a `trade_id`, which lets `stats` aggregate either
way. NT8's "total trades" is the leg count, so `stats.leg_summary` is what a reconciliation
compares against.

**`NULLABLE` states which columns a producer may legitimately leave empty, and why each one**,
so the nullability is a documented property rather than something discovered by a `NaN`
reaching a chart:

- `entry_bar` / `exit_bar` / `bars_held` — positional indices into a specific bar series. A
  real fill has a timestamp but no bar number until one is matched to it.
- `initial_stop` / `target_price` / `risk_points` / `r_multiple` — need the *planned* levels,
  and are deliberately absent on imported trades. The only stop levels the Control Center log
  records are ATM-template defaults dragged to intent seconds later, so a risk computed from
  them is wrong by an order of magnitude (§11.1).
- `mae_points` / `mfe_points` — need the bars the trade was open across.
- `ambiguous_bar` — a simulator-only concept. A real fill is not ambiguous; it happened.

Everything else is required on every row from every producer.

**`EXIT_REASONS` is what the *simulator* may write, and an imported trade is not restricted to
it.** NT8's executions grid names its exits `Stop1..4` and `Exit`, which do not map onto the
enum without inventing information, so `validate` requires `exit_reason` to be a string rather
than a member of the set. `validate_legs` *does* check the codes, because only the simulator
can have written a matrix.

**`direction` is carried per row, not per run**, because a bidirectional archetype takes both
sides within one run and a real trading history certainly does. Every P&L and MAE/MFE sign
convention downstream reads it rather than assuming the short side the first archetype happened
to have. `source` is carried for the same reason: real and simulated trades share one DuckDB
table, so without a tag one careless `GROUP BY` averages a backtest into a trading record.

**`validate` is written to short-circuit, and that is a measurement.** It runs once per
combination inside a sweep. Every check is a whole-column test that stops at the first failure,
and the per-row accounting that makes a good error message is only paid for once there is an
error to describe. End to end on a 12-combination sweep it costs **1.3%**; the obvious form —
`frame[REQUIRED].isna().sum()` plus `isin` — costs **9.4%**. Integer columns are skipped
entirely, since one cannot hold a null, which is a third of the loop's cost. Beware of
microbenchmarking it by validating one frame repeatedly: `Series.hasnans` is a cached property,
so the second call onwards is free and the result is meaningless.

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

Three smaller `sweep_axes` decisions, recorded here rather than in the module ([#105]).
**Every axis defaults to a single value**, so cost is opt-in one axis at a time — but they
compose and the product is a product: three grids over four resolutions over nineteen contracts
is 228 datasets, each paying the full `prepare` cost. **`AxisPoint.tier2` is carried, not
swept** — a property of the strategy rather than an axis of its own, riding along because it
has to reach the results row. And **the axis columns lead the table rather than trailing it**,
because they are what the row *is*; a table whose leading column is `combo_id` invites reading
two resolutions as one population.

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

**How `results.py` stores it**, recorded here rather than in the module ([#105]):

- **The axis columns are migrated explicitly; a new statistic is not.** `_append_or_create`
  drops a column the table does not have, and for a statistic that is the right trade — a gap
  in one column, obvious on inspection. The four axis columns are *identity*, not measurement,
  so dropping one does not leave a gap: it silently relabels the row as some other run, and a
  15-minute result then sits in the same column as a 1-minute one with nothing to say so.
  `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so
  `ADD COLUMN IF NOT EXISTS` is what covers the database that already has years of rows.
- **An existing table is written by name, not by position.** Otherwise adding a statistic
  would make `INSERT ... SELECT *` shift every column one place right and store numbers under
  the wrong headings — which reads as a result rather than as an error. It is also why the
  stale-database re-run ([#71]) is scheduled after the axis columns land rather than before.
- **`_tag_axes` pins dtypes, and that is the point rather than decoration.** DuckDB infers a
  new table's column types from the frame it is created from, and an all-null `object` column
  infers as **INTEGER** — so a first sweep over the spliced series, where `contract` is null by
  definition, would create `combos.contract` as an integer column no contract name could ever
  be inserted into. A caller may also supply the tags per row (`sweep_axes` does), and then the
  frame's own values win; overwriting them with a scalar `None` is how a multi-axis run would
  lose exactly the tags it exists to produce.
- **A null does not mean the same thing in every column** — `results.NULL_MEANS` states it per
  column. `contract` is the odd one out and deliberately so: null is a real, expected value
  there, naming the spliced series. Everywhere else it means the row predates the column.
- **The axis arguments to `save_sweep` default to `None` rather than being inferred from
  `bars`.** Resolution in particular is guessable from the index spacing and that guess would
  be right nearly always — which is the problem: a tag that is usually right is worse than one
  that is absent, because nothing downstream can tell the two apart.
- **`next_batch_id` locks nothing.** Fine for a single-user research tool and not for a shared
  one: two runs started in the same second would share a batch. Recorded rather than defended.

**`Summary.session_close_share` is reported rather than buried in the trade log**, because a
strategy taking 40% of its exits at the session close **is not the strategy its rules
describe** — the profit factor of such a run is largely a measurement of the flatten time, and
no other aggregate says so. Flat-before-the-close is a prop-account rule, so this is never a
bug to be fixed; it is a property of the archetype at that bar size. It is computed over
**legs**, matching `ambiguous_share`'s denominator, since a leg exit is an exit. An imported
real-fill log carries an `exit_reason` NT8 wrote (`Stop1..4`, `Exit`), none of which is this
label, so it reports 0.0 rather than a wrong number. `ambiguous_share` is its counterpart: the
one statistic saying how much of a result rests on an assumption the bar data cannot settle.

The `tier2` registry field ([#25]) is not bookkeeping: per the standing constraint,
"validated against NT8" stops being a project-wide fact once originals exist, and M18 is what
made it one — `EmaCrossover` is `TIER1_ONLY` beside two `RECONCILED` ports. A results table
ranking a reconciled archetype against an unreconciled one compares a measurement against an
assumption, and carrying the status as a column is what stops the ranking hiding that. The
shared bracket engine was extracted **during** M18 ([#38]); see below for what the second shape
moved.

**What each `Archetype` field is for**, recorded here rather than in the module ([#105]):

- **`legs` is registered beside `run`, not derived from it.** It is the *earlier* of the two —
  `run` is this plus a DataFrame — and a sweep summarises the matrix directly, which is where
  [#33]'s speedup comes from. It is required, because an archetype registered with only `run`
  would silently be the slow one in a sweep and the reason to notice would be a wall clock.
- **`signal` is registered because M7a needs the *real* signal** to match its draws against
  before handing a substitute back to `run`. Without it the null would carry a second
  definition of the entry rule, which is exactly what the registry exists to prevent.
- **`not_sweepable` is listed, not inferred.** The rule today happens to be "the tuple-valued
  fields", but deriving it from the value's type would silently start sweeping a new tuple
  field, or stop sweeping a scalar that gained a `None` default — and a disappearing axis is
  [#60]'s failure mode, because it multiplies nothing rather than raising.
- **`run` is typed `Callable[..., pd.DataFrame]`, deliberately.** Each archetype's `run`
  accepts only *its own* parameter class, which needs a generic `Archetype[P]` rather than a
  plain callable type; that belongs with the typing work ([#55]). The runtime check that
  matters — base against `params_cls` — is enforced in `Grid.__post_init__`.
- **`Archetype` is a frozen dataclass, not a base class.** There is no behaviour to inherit,
  only facts and function references, and the standing rubric's warning against a class
  hierarchy for one archetype applies just as well to three.
- **`register` refuses a duplicate name** because `name` is written into the results table, so
  two archetypes sharing one would merge into a single DuckDB row group and read as one
  strategy measured twice. `for_params` raises on ambiguity for the same reason: guessing would
  attribute a whole sweep to the wrong strategy.
- **`DEFAULT` is DeadCatBounce** because it is the archetype every stored result, captured
  trade log and reconciliation was produced with. Changing it would silently reinterpret them.

**A `ContextSpec` is built from what the grid will actually try.** VWAP, the time-of-day
labels and the ATR grids are each requested only when some combination switches them on — they
are the series no combination reads by accident, so leaving them out when unused is free. The
MA periods cannot be treated that way, because `dead_axes` already refuses the case where a
swept period's toggle is off everywhere, so every surviving case is live. `crossover_context`
additionally sets `needs_ma_values`, since comparing two averages to *each other* is something
no close-versus-average boolean gate can answer; that is the 8× memory the grids otherwise
avoid, requested by the one archetype that needs it rather than switched on globally.
`CROSSOVER_GATES` guards the ATR fields but cannot guard `swing_lookback`: `dead_axes` asks
whether a toggle is true *somewhere*, which cannot express "dead when this one is never false".

### ~~M18~~ — EMA crossover: done ([#34])

The first original archetype, chosen to prove M15 and M17 because it is the cheapest thing
that exercises both: bidirectional, and it exits on a signal rather than a bracket level.
Everything below is the record of what it actually cost and what it actually read; the rules
themselves are in `docs/nt8-fidelity.md` § M18, marked as having no evidence behind them yet.

**It reads as a known negative, which is the result it was built to produce.** On costed MNQ
from 2024 (914,700 bars, EMA(9)/EMA(21), commission $1.24, 1 tick slippage) it returns a
profit factor of 0.866 on 41,784 trades. Against 200 matched random-entry draws (M7a) it sits
at the **49th percentile on profit factor**, the 47th on expectancy and the **1st on win
rate** — indistinguishable from random on two of the three and *worse* than random on the
third. The direction split is 83,532 long legs against 83,604 short.

**That reading is also the lookahead check.** The stated worry was that a crossover is
unusually easy to compute one bar early, and that the symptom would be an exciting profit
factor rather than an exception. A rule that read the fill bar's own cross would have come
back spectacularly profitable; this one comes back at the null's median. There is a direct
test as well — `crossover_signal` recomputed over a prefix must equal the prefix of the full
computation — but the control arm is the one that would have caught a defect the direct test
was not shaped to see.

**The trade-count explosion is real but a third of the guess.** One combination:

| | per combination | legs |
|---|---|---|
| `EmaCrossover` | 49.0 ms | 167,136 |
| `DeadCatBounce` | 3.3 ms | 14,556 |

**~11.5× the legs and ~15× the time**, against the "tens of thousands against ~1,400" this
section predicted, which was closer to 30×. Of the 49 ms, 4.9 ms is the signal (two EMA
comparisons plus the cross window, computed per combination because `cross_lookback` is an
axis) and 11.4 ms is `summarise_legs`. `allocate_output` reserves **27 MB per worker** at
these settings — the `n_signals × n_legs` bound stays correct and stops being free, so a
permissive grid should have its signal count read off before it is launched, not after.

**The exit mix is not what was predicted.** 51.3% signal, 25.2% stop, 22.4% target, **1.0%
session close**. The forced-exit share was expected to be a large fraction; see the M10.4
note above for why the reasoning was sound and the premise was not.

**Three defaults were wrong and each is now a swept field rather than a constant.** NT8's
`CrossAbove(a, b, n)` semantics rather than the naive one-bar form ([#35]); market-on-next-open
entry ([#36]), a third mechanism with no trigger price and no "no touch, no fill"; and an ATR
multiple for the stop ([#37]), which is what made M16 a hard prerequisite rather than a
convenience. The swing-extreme stop survives as the alternative mode, sweepable via
`use_atr_stop`.

**One thing the loop needed that was not on the list.** An entry whose protective stop would
land at or through its own fill is skipped — the existing stop-entry submittability rule
applied to the protective stop. It is unreachable in both ports, because their stop is placed
against a trigger the fill is defined relative to; here the fill is wherever the next bar
opens, so a gap can put the swing reference on the wrong side of it. **Second time an
archetype has reached a rule the first two could not**, after M15.5's two fill-semantics
defects. One archetype cannot exercise the fill model, and it turns out two cannot either.

**Flat between trades, not stop-and-reverse, is a real difference and not a limitation
worked around.** The flip closes the position and opens the new one as two fills at the same
open price, each paying its own slippage and commission. Economically a reversal; in the log,
two trades. Any comparison against published crossover results has to say so. It is also what
`pending_exit` exists for: without allowing the entry to be scheduled on the bar the exit is
scheduled, a one-bar lookback would only ever go long, because crosses alternate.

**The bracket engine came out during M18, per [#38].** `nqbt/sim/bracket.py` holds the stop,
the targets, the ambiguity policy, the limit-fill rule and the leg writer; `simulate_deadcat`
keeps what is specific to a stop-market entry with a ratcheting stop. The second real shape
is what showed the split falls between the **entry** half and the **bracket** half rather
than anywhere else — crossover replaces the whole entry mechanism and reuses the bracket half
untouched. All 14 captured DeadCatBounce trade logs are byte-for-byte identical across the
extraction and across the whole milestone.

**What M19 inherits.** `EXIT_SIGNAL` is now exercised rather than reserved. The bracket engine
is a set of `@njit` device functions any loop can call, so a squeeze breakout needs to write
only its two-sided OCO entry. And the per-combination cost of a high-leg archetype is now
known rather than assumed, which is what the numpy summary path ([#33]) was moved ahead of
M18 to buy.

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

**`_ordered_starts` refuses keys that are not already ascending.** `groupby` returns groups
sorted by key whatever order the rows arrived in, so a boundary scan only reproduces it for
sorted keys. The simulation writes every leg of a trade before the next trade can open — it
cannot be in two positions at once — so this holds by construction, and the check guards
against a future producer rather than being a branch anyone takes.

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

`nqbt/randomentry.py`. This section is the methodology, the reasoning behind it and the first
result; the module carries a pointer here rather than a copy ([#105]).

**A backtest reports numbers, not evidence.** "Profit factor 0.746" is only interpretable
against what the *same bracket, the same costs and the same exits* would have produced with
entries chosen at random, and until that arm exists three very different diagnoses look
identical: *worse than random* (the rule carries real information and points the wrong way),
*indistinguishable from random* (the rule contributes nothing, and further tuning is a search
over noise), and *better than random but still unprofitable* (there is signal; the loss is in
costs, hold time or bracket geometry). Permuting an existing trade sequence separates none of
them, because it takes the entries as given.

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

**The p-value is two-sided on purpose.** An entry rule reading *worse* than random is a
finding — real information pointing the wrong way — and a one-sided test would report it as an
unremarkable failure to beat the null.

**`DEFAULT_ITERATIONS` is 200, not `spread_vs_resampling`'s 1,000.** Each draw here is a full
simulation over every bar rather than a regrouping of an existing trade list, so an iteration
costs two orders of magnitude more. 200 gives a p-value resolution of 0.005, finer than the
decision being made with it; raise it when a result lands near the threshold. The numpy-native
summary path ([#33]) is what makes a larger default affordable at all.

**Drawing is without replacement within a minute, and the guarantee is structural.** The pool
for a minute is *every* bar sharing it, and the real signals at that minute are a subset of
that pool, so it can never be smaller than the number of draws. That is why there is no
resample-on-collision loop to get subtly wrong.

**The pool is deliberately not narrowed to in-session bars.** The null must face the same bar
universe the strategy faced. A per-contract frame keeps a handful of out-of-session stray
prints and the strategy's own signal is computed over them too; narrowing one side and not the
other would compare two different bar universes, and would break the subset guarantee above.
On the spliced series the question does not arise — `build_continuous` has already filtered
them out.

**`SessionMinutePool` is hoisted out of the Monte Carlo loop because of a measurement.**
Grouping means an argsort over the whole series, and rebuilding it per draw was **89% of an
iteration** on 914,700 bars — 106 ms against the 13 ms simulation it exists to feed. Same
reasoning that hoists `context.prepare` out of a sweep.

**A non-finite observed statistic raises rather than being compared.** "Infinite profit factor
beats the null" is an artefact of a run with no losing trade, not a result.

#### What the test still does not do

- **It does not correct for multiple comparisons.** Running it across a sweep and keeping the
  combinations that beat the null is the trap [#48] exists to guard, with an extra step. Test
  a combination chosen for a reason, not the best of two hundred.
- **A small p-value is not a tradeable edge.** It says the entry timing is unlikely to be
  noise; profitability after costs is a separate question the module reports but does not
  answer.
- **It assumes the signal count is worth matching.** A rule that fires four times is not
  rescued by a null that also fires four times; the trade floor still applies.

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

### M7b — walk-forward and Monte Carlo: done ([#50])

`nqbt/walkforward.py`, `nqbt/montecarlo.py` and `nqbt/costs.py`. The third is not scope creep —
see below.

**Costs are an argument with no default, because an uncosted walk-forward is worse than none.**
Every archetype's parameter class defaults `commission_per_contract` and `slippage_ticks` to
zero, which is right for NT8 reconciliation and wrong for every ranking. Selection on gross P&L
selects for *trade frequency*, which is the one thing costs punish, so an uncosted walk-forward
reports a clean result that inverts the moment costs are applied — a failure that looks like
success. `walk_forward` therefore raises on `costs.FREE` rather than defaulting, and
`costs.LIVE` carries the real account's terms. **Do not "simplify" this to a default.**

The defaults themselves stay zero and must: `tools/capture_trade_logs.py` uses them for the
reconciliation captures, so flipping them breaks the trade-log gate.

**The split geometry is asserted as a property, not as arithmetic.** `splits()` returns
half-open positions and the tests check directly that no test bar is ever a train bar and that
the out-of-sample windows *tile* the tested region — the latter is what makes concatenating
their trade logs legitimate rather than double-counting. A test that recomputed the arithmetic
would pass over the same off-by-one it was meant to catch.

**Each window is simulated independently, and that is a stated approximation.** A trade open at
a boundary is not carried across it: every window starts flat. The alternative — one run with
the selection changing mid-flight — cannot be measured per window at all. The cost is that a
position spanning `test_start` would have blocked an entry that the sliced run now takes.

**`warmup_bars` prefixes each window and its trades are discarded by entry position.** Without
it every window's indicators start cold, so an SMA(200) grid measures its own warm-up for the
first 200 bars of each split. `entry_bar` is already a position into the sliced frame, which is
what the prefix is measured in — do not reach for `entry_time` and an index lookup.

**Selection is capped to `TRADE_PNL_STATISTICS`.** Every one of them is higher-is-better, so one
comparison serves both sides. Admitting `max_drawdown` would need the opposite sense and a
direction bug there is invisible — it would simply select the worst combination every time.

**`trade_id` restarts at 1 in every window, and pooling on it silently merges trades.**
`stats.per_trade` groups on `trade_id` alone, so collapsing the concatenated log counted 5
trades where there were 14. `WalkForwardResult.pooled_pnl` groups per split *before* the leg
collapse. Found by a test asserting the pooled count equals the sum of the per-split counts;
without that assertion every downstream statistic would have been quietly computed over a
quarter of the data.

**Monte Carlo's two halves answer different questions, and the guard between them is the
point.** `permutation_test` reorders the trades, which moves only `PATH_STATISTICS`;
`bootstrap` resamples with replacement, which moves the values too. Permuting a
`TRADE_PNL_STATISTICS` value is **refused**, because reordering cannot change profit factor,
net P&L, expectancy or win rate — such a test returns `p_value` 1.0 for every input and reads
exactly like a passed check. `stats.PATH_STATISTICS` is the exact complement of
`TRADE_PNL_STATISTICS` and `stats.path_statistic` is the single definition, sharing
`_max_drawdown` and `_max_consecutive` with `summarise`. A test pins both halves: that
reordering *cannot* move a value statistic, and that it *can* move a path statistic.

**Neither test says the entries are any good.** Both take the trades as given, so they cannot
separate "worse than random" from "no better than random" — that is `randomentry.py`'s job
([#32]), and a Monte Carlo result quoted without it is half an argument.

**Drawdown is measured from the running peak of the equity curve, which starts at the first
trade rather than at zero.** Ten $10 losses followed by ten $10 wins reports 90, not 100. That
is `summarise`'s existing definition and this must not fork it; a test pins the two together.

**First result, and it is a confirmation rather than a finding.** Costed MNQ from 2025-01-01
(564,927 bars, `DeadCatParams`, 9 combinations, 120,000-bar train / 40,000-bar test, 11 splits):
training profit factor runs a median 0.611 against a pooled out-of-sample 0.563, four different
combinations win a training window across the eleven, and the bootstrap puts net P&L below zero
in every resample. The permutation test reads p = 0.70 on max drawdown — **the losses are
systematic, not an unlucky ordering**, which is the correct reading and the one that matters:
this is the machinery reproducing a result the project already holds, on an archetype whose
unprofitability is settled. Re-run it rather than quoting these numbers.

### M10 — the conditions the review needs and we lack ([#39])

The review is meant to score trades against "overall trend, MAs, volume, directional vs
consolidation, time of day", and three of those five had no implementation. **Time of day
([#43]) and the regime classifier ([#40]) have both landed** — see below. **Volume is one quantity
and its decomposition, not three conditions** ([#41]): absolute volume is the raw count, time of
day is its dominant systematic component, and relative volume is absolute with that component
divided out. Treating all three as independent findings confirms one signal three times.
Absolute earns its place regardless because it alone answers **execution feasibility** — a rule
that only works in thin overnight bars looks fine on relative volume and is untradeable — but
that same secular trend means a raw absolute threshold must not be a sweepable filter, since
expressing it as a trailing percentile just makes it relative volume again. The compact trend
label ([#42]) comes off the existing MA grids and is the cheapest of the four.

### ~~M10.4~~ — time of day: done ([#43])

`nqbt/timeofday.py`. Two forms of one clock: `SessionPhase`, seven coarse Eastern-time
buckets, and `bar_of_session`, the integer index from the session open. Both come out of one
`classify()` pass, both go through `resample.minutes_since_open`, and neither is a second
session clock.

**The ET requirement is pinned by a test that states the failure, not only the behaviour.**
Two sessions either side of the 2024-03-10 transition are labelled, and the test asserts both
that the cash-open bars carry the same *Eastern* minutes and that their *UTC* minutes differ.
Without the second half the test is a tautology and would pass over a UTC implementation on a
winter window — which is exactly how this bug survives review.

**The end-of-bar convention decides the boundaries.** A bar stamped 09:30 covers 09:29–09:30
and is the pre-open; the first cash-open bar is stamped 09:31. Same off-by-one M13 found in
`bucket_index`, and it is invisible in aggregate — the phase totals are right and only the
edges move.

**Bar of session is derived from the clock, never counted off the data.** An ordinal count
renumbers everything after a hole, so index *k* would mean a different time of day in
different sessions — precisely the confound [#41]'s relative volume exists to divide out. It
is therefore literally `resample.bucket_index`'s bucket, which is also what makes the two
share a definition rather than each inventing one. `prepare` takes `bar_minutes` explicitly
and `sweep_axes` passes the resolution it already knows; inference off the index's own gaps is
the fallback, not the path.

**The filter is a bitmask integer, and that is what makes it sweepable.** A tuple of phases
would have to join `not_sweepable`; a scalar mask is one value per combination, so
`phase_filter=[CASH_OPEN.bit, ALL_PHASES]` is two combinations and "does this only work at the
open?" is a sweep rather than a set of hand-run backtests. `ALL_PHASES` is the default and each
archetype's signal **skips the conjunction entirely** at that value, which is why adding the
field to two reconciled archetypes moved nothing.

That skip is not an optimisation. An out-of-session stray print passes *no* mask, `ALL_PHASES`
included, so ANDing the gate at the default would quietly drop the strays and move a
per-contract result — the same asymmetry `context.prepare` and `build_continuous` already
disagree on. The no-op has to be no call.

**Gated.** All 12 captured trade logs are byte-identical (`sha256` too); the two sweep summary
tables differ by the added `phase_filter` column and are identical on every pre-existing
column, dtypes included — `compare_trade_logs.py --added phase_filter` reports
`ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First result, and it is a stratification rather than a finding.** Costed MNQ from 2024
(914,700 bars, stock `DeadCatParams`, $1.24 and 1 tick), one combination run once per phase:

| phase | trades | profit factor | win rate | expectancy |
|---|---|---|---|---|
| OVERNIGHT | 1,550 | 0.561 | 0.297 | −9.76 |
| LONDON | 656 | 0.599 | 0.326 | −10.70 |
| PRE_OPEN | 348 | 0.665 | 0.342 | −10.88 |
| CASH_OPEN | 151 | 0.677 | 0.325 | −23.76 |
| MIDDAY | 478 | **0.871** | 0.383 | −5.57 |
| AFTERNOON | 297 | 0.709 | 0.327 | −12.54 |
| CLOSE | 159 | 0.631 | 0.321 | −8.47 |
| all | 3,639 | 0.666 | 0.322 | −10.24 |

The seven counts sum to the unfiltered 3,639 exactly, which is the property that makes this a
decomposition and not seven overlapping subsets; a test pins it. **Do not read the MIDDAY row
as an edge.** It is the best of seven cells chosen after looking, on the archetype [#48] exists
to guard against exactly this on, and no cell reaches a profit factor of 1. What it does say is
that the aggregate 0.666 was averaging populations that differ by 55%, which is the argument
for the milestone rather than a result from it.

**The prediction about the last phase was directionally right and quantitatively small.**
`session_close_share` reads 0.0016 on CLOSE against 0.0001 overall — an order of magnitude, and
still tiny, because a 1-minute DeadCatBounce holds for minutes. The artefact is real and will
grow with bar size ([#30]); on this data it is not what makes the CLOSE row look the way it
does. Read the column before attributing anything to the clock, and expect it to matter at 15
and 30 minutes where it does not here.

**Cost.** `needs_time_of_day` is requested the way VWAP is — only when some combination
actually narrows the phases — and adds three arrays (`int8`, `uint8`, `int32`) over the series.
The eight-combination sweep above took 0.6 s over 914,700 bars, so the gate itself is not
measurable against the simulation.

**Smaller choices in `timeofday.py`, recorded here rather than in the module ([#105]):**

- **Seven buckets, chosen for what happens in them rather than for equal length.** The
  overnight hours are one bucket because little distinguishes 20:00 from 01:00; the hour after
  the cash open gets one to itself because it is the most distinctive hour of the day. Fewer
  buckets is the point — time of day multiplies every other stratification, and seven phases
  against five regimes is already 35 cells, which a minimum-stratum guard on a few hundred real
  trades has to survive.
- **`SessionPhase.CLOSE` is structurally anomalous**, because it contains the forced flat
  ([#16]). Its exits are decided by the clock rather than the rules, so a stratification will
  show it as different whatever the market did. `FORCED_EXIT_PHASE` names it so a caller can
  exclude it without working out which one it is.
- **`OUT_OF_SESSION` is −1, not an eighth phase**, so it cannot be swept into a filter by
  accident and a `groupby` over the labels reads as obviously wrong rather than quietly
  counting stray prints as an eighth hour of the day.
- **`PHASE_STARTS` is written as ET wall-clock times**, because that is what the boundaries
  mean: `time(9, 30)` is the cash open, where an offset of 930 minutes is a number nobody can
  check. `phase_start_minutes` converts them and validates on **every** call rather than once
  at import — the boundaries are relative to the template's own open, so a template opening
  elsewhere reorders them, and a set that no longer ascends would mislabel whole phases through
  `searchsorted` without raising.
- **`infer_bar_minutes` takes the mode of the gaps**, not the minimum or the mean: every
  session has a one-hour break and the archive has holes, so both of those measure the gaps
  rather than the bars.

### ~~M10.1~~ — market regime: done ([#40])

`nqbt/regime.py`. Kaufman's efficiency ratio — `|close[t] − close[t−n]| / Σ|diff(close)|` over
the lookback — cut by two thresholds into `CONSOLIDATING`, `UNCLASSIFIABLE` and `DIRECTIONAL`.
Bounded 0–1, three lines of arithmetic, no TA-Lib dependency and therefore none of the
NT8-parity work the moving averages needed. The lookback and both thresholds are sweepable and
`regime_filter` is a bitmask integer, for exactly the reason `phase_filter` is one.

**The band between the thresholds is a label, not a gap.** Strictly below the lower is
consolidating, strictly above the upper is directional, and everything in between —
**including both boundaries** — is unclassifiable. That makes the third category free rather
than a special case, and it makes the equality question one decision instead of two: no bar can
satisfy two regimes, and `validate_thresholds` refuses a pair that cross rather than silently
ordering them.

**The warm-up is `UNDEFINED`, which is not a fourth regime and not consolidating.** The house
convention for an NT8 indicator is an expanding warm-up, and it is wrong here: over two bars
the numerator and the denominator are the same quantity, so an expanding ratio reads exactly
1.0 and would label the start of every dataset `DIRECTIONAL`. Not measured and measured
inconclusive are different states, and folding the first into the second would put unmeasured
bars into a stratification cell while leaving the counts adding up — the failure that looks
like a result. `UNDEFINED` is −1 for the same reason `OUT_OF_SESSION` is, and an undefined bar
passes **no** mask, `ALL_REGIMES` included, so each archetype's signal skips the conjunction
entirely at the default rather than ANDing a gate that would drop 20 bars from a reconciled run.

**The window sum is recomputed per bar rather than maintained incrementally.** A rolling
add/subtract over a million bars drifts, and this is a denominator that legitimately reaches
zero: a flat window would turn a −1e−13 of accumulated error into a large negative ratio. The
exact version costs 15 ms per lookback over 914,700 bars, paid once in `prepare`, which is not
worth trading for that. A window that genuinely never moved scores 0.0 — the extreme of
consolidation — rather than dividing by zero.

**The grid holds ratios, not labels.** Both thresholds are swept as well as the lookback, so a
grid keyed by all three would multiply out; `EfficiencyRatioGrid` is `[n_lookbacks, n_bars]`
float64 and the thresholds are applied at gate time. That is the opposite of
`MovingAverageGrid`'s default and the reason `_regime_lookbacks` returns nothing unless some
combination actually narrows the filter — eight bytes per element is the most expensive thing
a `ContextSpec` can ask for by accident. It is also the shape [#51]'s bandwidth squeeze wants,
so the two share a scalar-plus-thresholds classifier instead of each inventing one.

**One function owns the rule.** `_regime_of` is the `@njit` device function both `label` and
`gate` call, so the stratification key and the entry filter cannot drift apart. The filter still
never builds a label array: `gate` tests `1 << regime` against the mask inside the same pass,
which reads 0.23 ms over 914,700 bars against the ~30 ms a combination of the run below
costs.

**`dead_axes` had to learn that a mask is off at its everything value.** `ALL_REGIMES` is 7,
so the existing truthiness test read the filter as switched on and would have let
`regime_lookback=[5, 20]` run every combination twice for identical rows.
`archetypes.INERT_AT` states the off value where it is not `False`; nothing else changes.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep
summary tables differ by the four added parameter columns and are identical on every
pre-existing column — `compare_trade_logs.py --added regime_filter regime_lookback
regime_consolidating_below regime_directional_above` reports `ALL PRE-EXISTING COLUMNS
IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ
continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, **$1.50 per contract** and 1
tick, lookback 20 and thresholds 0.3/0.5, one combination run once per regime:

| regime | bar share | trades | profit factor | win rate | expectancy |
|---|---|---|---|---|---|
| CONSOLIDATING | 71.3% | 2,396 | 0.611 | 0.312 | −12.04 |
| UNCLASSIFIABLE | 21.9% | 975 | **0.721** | 0.331 | −8.40 |
| DIRECTIONAL | 6.8% | 270 | 0.616 | 0.296 | −14.97 |
| all | | 3,639 | 0.640 | 0.316 | −11.28 |

**Do not read the UNCLASSIFIABLE row as an edge**, and do not diff this table against M10.4's:
that one was run at the roadmap's older $1.24. It is the best of three cells chosen after
looking, on the archetype [#48] exists to guard against exactly this on, and no cell reaches a
profit factor of 1. And 270 trades in `DIRECTIONAL` is where a minimum-stratum guard starts to
bind — against seven session phases it is 35 cells, and this is the coarsest of the two labels.

**The signals partition exactly and the trade counts do not, which is the point worth keeping.**
All three single-regime filters admit 4,889 signals between them, exactly the unfiltered count,
and their union is the unfiltered signal bar-for-bar. The trade lists sum to **3,641 against
3,639**. Nothing is double-counted: the simulation holds one position at a time, so removing an
entry can free a later signal the unfiltered run was still in a position for. A regime label
flips bar to bar where a session phase is a contiguous block, which is why M10.4's seven phases
did sum exactly and these three do not. **Stratify the signal, or accept that the trade-level
decomposition is approximate** — and never conclude a filter "found" trades from a count that
went up.

**71% of 1-minute bars are `CONSOLIDATING` at 0.3/0.5.** The thresholds are resolution-dependent
— a minute of noise has a low efficiency ratio almost by construction — so the defaults are
conventional starting points to be swept, not a calibration, and they will want different
values at 15 and 30 minutes. Read `ambiguous_share` before believing any of the rows: it runs
0.029 / 0.041 / 0.044 against 0.033 overall, highest in `DIRECTIONAL`, which is what a regime
of larger bars should do.

**Cost.** Requested the way VWAP is, and adds one float64 series per lookback — 7.32 MB over
914,700 bars, about a sixth of the 47 MB dataset the run above was handed. `prepare` pays 15 ms
per lookback and the per-combination gate 0.23 ms, so neither is measurable against the
simulation.

**Smaller choices, recorded here rather than in the module ([#105]):**

- **Efficiency ratio rather than ADX**, which is laggier, less interpretable, and would need
  the same NT8-parity check the moving averages needed. ADX only if this proves inadequate.
- **A lookback of 1 is refused**, because numerator and denominator are then the same quantity
  and every bar reads 1.0 — a whole axis of `DIRECTIONAL` that looks like a measurement.
- **Three regimes, and deliberately no more.** Time of day already multiplies every other
  stratification; three against seven phases is 21 cells before an MA gate, and [#48]'s guard
  has to survive it on a few hundred real trades.
- **The ratio is invariant to direction, level and scale**, which is what makes one pair of
  thresholds meaningful across both roots and across years of back-adjusted history. A test
  pins all three.

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

Three further conventions `nqbt/resample.py` implements, recorded here rather than in the module
([#105]):

- **Timestamps are end-of-bar**, so a bar stamped 18:01 is the session's *first* minute and a
  bucket covering 18:00–18:05 is stamped 18:05. A bar at minute *m* therefore *occupies* index
  *m − 1*; off by one there is invisible at 1 minute and wrong everywhere else.
- **The final bucket of a session is stamped at the observed last bar, not the theoretical
  end.** Two cases need it: a period that does not divide the session (7 would put the last
  bucket's end past the 17:00 close) and a holiday early close. Deriving it from the data is the
  same choice `is_session_close` makes, and it avoids the trap [#68] records against
  `force_flat_mask`.
- **`minutes=1` returns the frame unchanged, and `minutes >= 2` drops out-of-session bars.**
  The identity is not merely an optimisation — the 1-minute path is what every reconciliation
  and every captured trade log was produced against, so resampling must not perturb it even by
  dropping a row. A stray out-of-session print has no session to be anchored to and so no bucket
  it could honestly join; dropping it matches `splice.build_continuous` and differs from a
  per-contract 1-minute frame, which keeps them.

Because the grouping key includes the trading day, no bucket can span the 17:00–18:00
maintenance break or the weekend. That falls out of the anchoring rather than needing its own
rule.

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

**How the permutation test is built, and what it does not say** ([#105]):

- **A permutation, not a bootstrap.** Contract labels are shuffled over the *same* set of
  trades, keeping every group's count exactly as observed — cut points rather than resampling,
  so the null cannot mix a spread effect with a sample-size effect. That answers the only
  question the raw spread poses: if which contract a trade happened in were arbitrary, would
  the contracts still look this different?
- **Trades are permuted whole.** Each contract's legs are collapsed by `stats.per_trade` first,
  so a trade's legs cannot be split across two groups and invent trades that never happened.
- **`by` is restricted to `stats.TRADE_PNL_STATISTICS`.** Permuting destroys entry and exit
  times, so Sharpe, max drawdown or consecutive losses would be computed over an ordering that
  never happened. Refusing is better than returning it.
- **A small p-value means "not obviously noise", never "a real per-contract effect".**
  Permutation destroys serial correlation and within-contract regime persistence, so the null
  has *less* spread than reality and the test **over-rejects**. It is a floor on scepticism,
  not a verdict. The stronger version — block resampling that keeps runs intact — shares
  machinery with [#50] and belongs there.
- **`dispersion()` returns rows in `combo_id` order and a test fails if that changes.** Sorting
  by the median would hand back the leaderboard the milestone exists to refuse; reaching for
  the best row has to be deliberate, and then the caller owns the multiple-comparisons problem.
  `contracts_dropped` is as informative as the spread — a combination clearing `min_trades` on
  three of nineteen contracts has not been measured across contracts at all.
- **`MIN_TRADES` is 30 because noise has the widest spread.** A profit factor from a handful of
  trades does not merely add uncertainty to the dispersion, it dominates the quantity being
  measured. Small contracts are still reported, just excluded from the spread.

**What this is not: a contract is a ~3-month bucket, so it surfaces regime shifts, not
events.** An election or a CPI print is a day or an hour, and averaging it across a quarter
dilutes it to nothing. For events the tools are the regime and time-of-day labels ([#40],
[#43]) plus a date filter.

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

### ~~M20a~~ — the three findings that blocked M15: done ([#9])

**`bracket.resolve_brackets` is the single bracket implementation.** Until M20a it existed
twice: once for a bar while in a position and once, textually independently, for the bar an
entry filled on. The two were behaviourally equivalent — the entry-bar copy dropped the
`leg_open` guards because every leg had just been opened, which makes them no-ops rather than a
difference — but every rule the 1143/1144 NT8 reconciliation validated appeared in both, so
there were two places for Tier 1 and Tier 2 to drift and the reconciliation only ever covered
one of them. Unifying it is what let M15 multiply *one* copy by its direction sign: the
short-only byte-identity gate cannot catch a sign applied inconsistently across two copies,
because at `d = −1` both reduce to today's code whether or not they agree at `d = +1`.

**`bracket.entry_bracket` is the single trigger/stop/risk computation**, called by the `@njit`
loop and by `explain.py`. It too used to be written out twice, and the two copies disagreed:
the audit trail took the trigger to be simply `Low[0]`, dropping the `Close[0] − 2 ticks` cap
the simulation applies. So `nqbt run --explain` — the tool a human uses to tick a trade off
against a chart before trusting anything downstream — reported the wrong `trigger`,
`risk_points`, `risk_ticks` and `fill_type`, while agreeing on the stop, which is what made it
look right on inspection. The audit trail is now by construction the arithmetic under audit.

**The 50% figure that justified that fix was a prefix, not a rate.** Measured over the whole
window the cap binds on roughly a **third** of signals; it reads far higher over the first
twenty trades and decays from there, because capped signals are not evenly distributed.
**Quote whole-window rates** — a prefix of a trade log is not a sample of it. The defect was
real either way.

**`Summary.empty()`** replaces a splat that put 26 arguments into a 28-field dataclass and
raised on every call, which went unnoticed because the only caller had grown a second,
divergent empty-log policy of its own. `sweep.run_combination` no longer keeps one.

Two things M20a deliberately did **not** change, because M20 may not move a number:
`stats.py`'s silent branch computing Sharpe and Sortino per trade rather than per day for a log
with no times ([#81]) — unreachable today, same shape as the empty-log defect — and
`verification/explain_2024Q1.csv`, annotated rather than regenerated, because it is the record
of what the audit trail said while it was being trusted.

### M8 — bar-major restructuring: measured, and not scheduled

`sweep.py` is **combo-major**: build the dataset once, then loop combinations and run the
whole jitted simulation over the whole series for each. That is the straightforward shape, and
it was chosen for correctness first — a bar-major restructuring would reuse cache better across
combinations at a real complexity cost, which had to be justified by profiling rather than
assumed.

It was, and the premise came back mostly false. Profiling one combination over 1.65M bars put
`stats.summarise` at 51%, `trades_to_frame` at 20%, the `@njit` loop at 23% and the signal ANDs
at 2%. Bar-major restructures the 23%, so making the simulation *entirely free* was worth about
1.3× — Amdahl caps it there. [#33] took the 71% instead, and a combination is now 9.0 ms
against 28.3 ms, of which 9.3 ms is the loop.

The ceiling is unchanged and the loop's share of a combination is now most of it, so **M8 is
still not scheduled**: re-profile before believing any figure here, and do it only if the loop
is genuinely what a real sweep is waiting on.

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

**~~The bracket engine is extracted during M18~~ — done ([#38]).** Before would have been
designing an abstraction from one example; after would have meant fidelity-critical code
sitting duplicated on `main`. Extracted mid-M18 with byte-identity as the gate, so the
abstraction was designed against two real shapes and the duplication never shipped. The split
it found is entry half versus bracket half: `nqbt/sim/bracket.py` is the second, and a new
archetype writes only the first.

**Archetypes are flat between trades; stop-and-reverse is not supported.** Each loop's
`in_position` boolean assumes flat-to-flat, and for the stop-market archetypes reversal also
collides with the one-bar entry lifetime. Recorded as a deliberate limitation rather than
discovered as a position-tracking bug. M18 is what it costs in practice: a crossover's regime
flip closes and reopens as **two fills at the same open price**, each paying its own slippage
and commission, where the classic form reverses in one order. That is a real difference from
published crossover results and belongs in any comparison against them.
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
  `.claude/rules/data-pipeline.md` cites as the authority on what the stored captures mean. The CSVs are
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
[#42]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/42
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
[#55]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/55
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
[#71]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/71
[#72]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/72
[#73]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/73
[#75]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/75
[#76]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/76
[#81]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/81
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
[#92]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/92
[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#113]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/113
