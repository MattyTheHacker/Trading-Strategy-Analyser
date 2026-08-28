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

**[#23] is settled on both halves, and the roll half needed no NinjaTrader time after all.**
True Range does not reset at a session boundary, and there is nothing to reset it to at a roll
either: back-adjustment cancels the contract basis exactly at the seam, so the step is the
price move over whatever break the seam spans. Rule and evidence in `docs/nt8-fidelity.md`,
"True Range at a roll boundary"; the decision and what it cost to reach are under "Decisions
taken".

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

**Cheap, and unblocked:** porting `InsideBarTrailing.cs`. It has C# ground truth, which makes it the cheapest *trustworthy*
archetype available, unlike M18 and M19. `InsideBar` — the structural form of the squeeze
idea, and the reason to do it before M19 is built from scratch — is done (M22 below).
`InsideBarTrailing` is the second consumer of `EXIT_SIGNAL`, which M18 has now made a working
exit rather than a reservation — and it is the first chance to check the signal exit against a
trade list.

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
It also matches NT8, where every strategy in the submodule sets
`IsExitOnSessionCloseStrategy = true`, so Tier 1 and Tier 2 agree on it today.
`ExitOnSessionCloseSeconds` varies between them — 30 on both stop-market ports, 180 on both
InsideBar scripts — and **a backtest ignores the difference**, flattening on the session's last
bar either way, so it stays one default rather than a per-archetype setting
([nt8-fidelity.md](nt8-fidelity.md) §M22).

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

~~**Holiday early closes are probably not handled — [#68].**~~ **Confirmed and fixed.**
`force_flat_mask` derived its cutoff from the *template's* fixed 17:00 ET close, so on a CME
half-day nothing reached it and the mask came back empty. It now counts down to the session's
observed last bar, which is what `is_session_close` always did. The measured scale, the two
things the observed end cannot distinguish, and what it did to the InsideBar reconciliation are
in [nt8-fidelity.md](nt8-fidelity.md), "The session end is the observed last bar, not the
template's".

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

### What CI can gate on a dependency bump ([#161])

The trade-log gate above is the right instrument and it cannot run on a pull request:
`data/` and `verification/` are both gitignored, so CI has no bars and no NT8 exports. What
CI *does* have is the whole suite twice, JIT on and JIT off — and until #161 every assertion
over a simulated number stated a property rather than a value, which is precisely what a
dependency bump does not violate. `CONTRIBUTING.md` § "Dependencies are pinned exactly" says
each bump runs "the full suite plus both gates"; the gates were a local step nothing enforced,
and a dependency pull request touches no file under `nqbt/sim/` that would prompt anyone to
run them.

**A bump to numpy, numba, pandas or pyarrow is a `nqbt/sim/` change in effect**, and the three
tests #161 adds are the part of the gate that needs no data:

| test | what a failure means |
| --- | --- |
| `tests/test_rng_stream_pins.py` | the `Generator` stream moved, so every null distribution and the M7a arm have to be re-measured |
| `tests/test_numeric_pins.py` | the numeric pipeline moved — run the real trade-log gate before believing anything else |
| `tests/test_parquet_round_trip.py` | the cache reader, the writer, or the session labels moved |

Three things about them that are deliberate and read as mistakes otherwise:

- **`test_numeric_pins.py` pins the transcript, not the property**, against `CONTRIBUTING.md`
  § "Tests". That rule is right for behaviour and wrong here: a stated property cannot see a
  one-ULP drift, and a one-ULP drift is what a numba bump moves. The simulation compares
  floats against tick-grid levels, so at a fill boundary one ULP is a different trade, not a
  rounding difference.
- **Its bars are built from integer arithmetic and never from `numpy.random`.** Every other
  synthetic fixture in the suite draws from `default_rng`, which would make a stream change
  and a simulation change indistinguishable — the first thing that test asserts is that its
  *input* is unchanged, so a failure can be attributed before it is investigated.
- **`tests/fixtures/cached_bars.parquet` is a real cache file kept on purpose.** Every other
  test writes and reads parquet inside one process under one version, which cannot catch a
  reader that changed; only a file written by the *previous* version can. The test pins the
  `created_by` string for that reason. Regenerate it when the cached schema changes, never to
  make the test pass.

The fixture's bars straddle the 2024-03-10 US DST transition and the 17:00 ET break, and the
session labels stored at ingest are re-derived from the index and compared. That is the
tzdata check: `tzdata` is pinned like everything else, and it is the one dependency whose bump
moves session boundaries rather than arithmetic — so it earns a different check from the other
three, and this is it.

**What none of this replaces.** These are canaries, not the gate. The real gate is fourteen
files over real bars, and the MNQ 03-24 agreement rate in `docs/nt8-fidelity.md` is still the
only thing that says Tier 1 and Tier 2 agree. When a pin here fails, the answer is to run the
real gate and find out what moved — not to re-pin.

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
66 MB → 595 MB lesson applies with an extra factor — **keep boolean gates only**. [#23]'s
roll-boundary half is now settled too — see "Decisions taken".

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

### M22 — InsideBar, the third C#-backed port ([#126])

The archetype earns its place on what it reaches rather than on what it might make: three parts
of the fill model no other archetype touches — `IsFillLimitOnTouch = true`, a bracket anchored
to the fill and the signal bar at once, and a no-entry window before the session close. Each
rule, the two the port inferred wrongly, and the wall-clock trap that still has to be fixed in
the NinjaScript before that one rule can be reconciled:
[nt8-fidelity.md](nt8-fidelity.md) §M22 and "A no-entry window before the session close".

**Its trade list paid for itself twice over.** It settled the `IsFillLimitOnTouch = true`
branch, corrected both `OnExecutionUpdate` anchors, showed `ExitOnSessionCloseSeconds` does not
move a backtest's flatten, caught a `PositionAccount` guard that made NT8 reverse, and turned up
out-of-session stray bars sitting in the array every archetype indexes.

**Read its results with the geometry in mind.** A target 1x ATR(3) from the fill against a stop
10x ATR(3) beyond the signal bar is a high-win-rate, rare-large-loss shape: a win rate near the
top of the range and R multiples just above zero are what it looks like working, not what it
looks like broken, and neither number compares to another archetype's. Judge it on net P&L at
realistic costs — where a 1x ATR(3) target on a quiet bar can be smaller than the round trip.

### M23 — InsideBarTrailing, split lots and a trailing stop ([#127])

The same entry as M22 and a materially harder exit model: the position splits across two entry
orders with different exit engines, the runner's stop trails a high-water mark rather than
ratcheting off a lagged bar, and a trend violation flattens whatever is left. Each rule and
which of them has no evidence: [nt8-fidelity.md](nt8-fidelity.md) §M23.

**The entry is shared, not forked.** `InsideBarTrailingParams` subclasses `InsideBarParams` and
both archetypes call `insidebar_signal`, because the two NinjaScripts differ in defaults rather
than in rules. That is what makes `sweepable` reading `dataclasses.fields()` rather than
`__slots__` load-bearing rather than merely correct — see "Moving-average axes" — and the
difference the defaults make is not cosmetic: ten times the breakout buffer is a different
strategy.

**Decision: the split-lot model sits beside `bracket.py` rather than generalising it.** The
engine takes one stop for the whole position and per-leg targets, which is the wrong shape for
two independent brackets. Two ways out were available and only one was taken:

- *Generalise the engine* — make the stop per-leg, so `resolve_brackets` resolves each leg
  against its own. That is a real restructure of the fidelity-critical code, on the evidence of
  a single archetype, and it would put "the stop takes the whole position" — a rule three
  reconciliations rest on — behind a rewrite.
- *Resolve each lot through the engine as it stands*, which is what shipped.
  `insidebartrailing.resolve_lots` calls `resolve_brackets` once per lot per bar with every
  other leg masked out, so each bracket meets the one implementation of every fill rule and
  `bracket.py` is not touched at all. Under `StopTargetHandling.PerEntryExecution` that is also
  the more literal reading of what NT8 does.

The rule this follows is **extract the abstraction from two examples, not from one**. If a
second split-lot archetype arrives and wants the same thing, the shape to extract will be
visible in two places instead of guessed at from one — and the trade-log gate stayed
byte-for-byte identical across all fourteen files precisely because the shared engine was left
alone.

**`EXIT_SIGNAL` now has two consumers, and this is the first with C# behind it.** EmaCrossover
reserved it with no NinjaScript to be checked against; `InsideBarTrailing.cs` has a real
rule-driven exit, so the semantics M18 wrote down — a managed market exit filling at the next
bar's open, taking precedence over the brackets — finally have something to be reconciled
against. The structural test that pinned single use now pins the set, both halves.

**Its trade list overturned three of the four exit rules the port inferred**, and the port was
written to be checked rather than trusted: the two questions it turned on were on [#67] *before*
the code existed. What moved, in the order the corrections landed — the `-200` gate governing
the trend violation and not just the dead branch under it, `OnPositionUpdate`'s one-bar offset,
the exit being part of the triggering fill, and a trail advancing within its entry bar but not
within any later one — is in [nt8-fidelity.md](nt8-fidelity.md), "Reconciliation result —
InsideBarTrailing". Agreement went 80.18% → 99.80% across those four.

**The generalisation worth keeping: a guard clause belongs to the method, not to the branch
below it.** Reading `if (pnl > -200) return;` as part of the max-loss check under it is what
produced 340 spurious signal exits against NT8's 12 — a plain misreading of C# scope, made
easy by the ticket describing the two together, and invisible to every test written from the
same misreading. Only the trade list caught it.

### M19 — squeeze breakout ([#51])

Queued rather than scheduled; the expensive archetype. "Squeeze" means at least three things,
and fixing the definition is the first task: TTM-style (Bollinger inside Keltner — the full M16
debt), bandwidth (`(upper − lower) / mid` below a trailing percentile — Bollinger only), or
structural (inside bars — no new indicators at all). **Recommend the bandwidth form first:** one
indicator rather than three, it drops the Keltner parity question flagged above as most likely
to be silently wrong, and it is the same quantity M10.1's regime classifier wants anyway, so the
two share it instead of each inventing one. **`InsideBar.cs` is ported ahead of either** (M22
below) — it is the same compression-then-break idea, needs no new indicator work beyond ATR, and
is the only version of this strategy with C# ground truth. Its trade list also settled two
questions M19 would otherwise inherit: the `IsFillLimitOnTouch = true` branch, and what `[0]`
means inside `OnExecutionUpdate`. The real structural cost is a two-sided OCO entry
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
consolidation, time of day", and three of those five had no implementation. **All four
sub-milestones have landed** — time of day ([#43]), the regime classifier ([#40]), volume
([#41]) and the compact trend label ([#42]), each below. Every one is a 1D label array computed
once in `prepare` behind [#27]'s `required_context`, and every one carries its filter as a
bitmask integer so it is a legal sweep axis.

**The multiple-comparisons cost is now real and compounds.** Seven session phases against three
regimes, three volume states and three trends is 189 cells before an MA gate is touched. That
is the argument for the coarse labels rather than an accident of them, and [#48]'s guard
applies with more force here than anywhere else in the project.

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

### ~~M10.2~~ — volume: done ([#41])

`nqbt/volume.py`. **One quantity and its decomposition, not three conditions.** Absolute volume
is the raw contract count, the time of day is its dominant systematic component, and relative
volume is absolute with that component divided out. `VolumeForm` names the three absolute
forms — per bar, a trailing *N*-bar sum, and session-cumulative-to-date — and each is divided by
its own bar-of-session baseline to give the ratio the three `VolumeState` labels are cut from.
`volume_filter` is a bitmask integer, for exactly the reason `phase_filter` and `regime_filter`
are.

**The baseline is the median of the same bar of session over a trailing window of prior
sessions, and that is the whole point of the module.** Measured on the run below, a plain
trailing median over the 60 *adjacent* bars labels **82% of `CLOSE` bars thin and 57% of
`CASH_OPEN` bars heavy** — a table that reads as a discovery and is a clock. Against the
bar-of-session baseline the same data gives a heavy share of 16–31% and a thin share of 19–30%
across all seven phases. It is not flat, and it should not be: the cash open is the hour whose
volume is most predictable, so it is the hour that is least often extreme. What is gone is the
part that was only the time of day. A test pins both halves — a series that is a pure function
of the bar of session must produce **no state at all**, and the naive normalisation over the
same series must manufacture both extremes.

**No bar contributes to its own baseline.** The window is the sessions strictly *before* this
one, so a bar's whole session is excluded rather than merely the bar itself. A normalisation
that reads the present is a lookahead that flatters every stratification taken through it, and
it would be invisible in the output. Pinned as a property: rewriting the last session's volume
leaves every earlier session's ratios untouched and scales that session's own ratios exactly.

**Absolute volume is carried and deliberately not filtered on.** It answers the one question
relative volume cannot — *can this be traded here at all?* — and it carries when in history a
bar happened, which is a cross-check on [#31] rather than a duplicate of it. But it is
comparable neither across roots (NQ and MNQ trade different counts for the same exposure) nor
across time, so there is no absolute threshold to sweep. Expressing one as a trailing percentile
just makes it relative volume again, **which is the honest conclusion rather than a workaround**
— and it is why the per-instrument scale in `instruments.py` that [#41] anticipated turned out
not to be needed. Two tests state the pair: relative volume is unchanged by scaling the whole
series by any positive constant, and a tenfold secular drift moves the absolute series by more
than 4× while the relative one spans less than 1.5×. The residual there is worth knowing — a
trailing median lags a rising trend, so a strongly trending series sits *above* 1 throughout.
The level shifts; the shape is removed.

**It steps at every roll, and that is data rather than an event.** Prices are back-adjusted,
volume is not and should not be. A step reaches relative volume for the length of the baseline
window and then leaves, so a discontinuity there is dated by the roll rather than by the market.
A test pins the arithmetic: an incoming contract ten times the size of the outgoing one reads
exactly 10 on the roll session and exactly 1 a baseline window later.

**The warm-up is `UNDEFINED`, for the reason [#40]'s is.** A baseline needs
`MIN_BASELINE_SESSIONS` observations before it means anything, so the first five sessions carry
no label — 0.8% of the run below, out-of-session strays included. An undefined bar passes **no**
mask, `ALL_STATES` included, so each signal skips the conjunction entirely at the default.

**Three forms, and they are three different statements rather than three views worth
averaging.** The window a form does not read is dropped from its grid key, so sweeping
`volume_rolling_bars` alongside the per-bar form builds one series rather than one per window.
What `dead_axes` **cannot** catch is the other half of that: it understands one toggle per axis,
so it knows the five volume axes are inert while `volume_filter` admits everything, and it does
not know that `volume_rolling_bars` is inert at every form but `ROLLING`. Sweeping the window
under a per-bar form runs identical combinations. Known, and not worth a second toggle mechanism
for.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep
summary tables differ by the six added parameter columns and are identical on every pre-existing
column — `compare_trade_logs.py --added volume_filter volume_form volume_rolling_bars
volume_baseline_sessions volume_thin_below volume_heavy_above` reports `ALL PRE-EXISTING COLUMNS
IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ
continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick,
thresholds 0.7/1.5 over a 20-session baseline, one combination run once per state:

| form | cell | bar share | trades | profit factor | win rate | expectancy |
|---|---|---|---|---|---|---|
| per bar | THIN | 27.5% | 992 | 0.534 | 0.300 | −10.54 |
| per bar | NORMAL | 44.3% | 1,678 | 0.653 | 0.309 | −11.23 |
| per bar | HEAVY | 27.5% | 942 | 0.686 | 0.346 | −12.27 |
| rolling 30 | THIN | 18.1% | 631 | 0.470 | 0.265 | −11.31 |
| rolling 30 | NORMAL | 61.3% | 2,202 | 0.665 | 0.322 | −10.50 |
| rolling 30 | HEAVY | 19.8% | 775 | 0.659 | 0.342 | −13.57 |
| session to date | THIN | 13.4% | 513 | 0.526 | 0.263 | −10.27 |
| session to date | NORMAL | 69.8% | 2,525 | 0.635 | 0.316 | −11.76 |
| session to date | HEAVY | 16.0% | 571 | 0.721 | 0.368 | −10.24 |
| any | all | 99.2% | 3,639 | 0.640 | 0.316 | −11.28 |

**Read those nine rows as three, and then as one.** Profit factor and win rate rise with the
volume state under all three forms, which looks like three confirmations and is one: the three
forms are three views of the same quantity over the same bars, and the time of day has already
been divided out of all of them. That is exactly the failure [#41]'s opening table exists to
prevent, and quoting it as corroboration would be the mistake it names. No cell reaches a profit
factor of 1, expectancy does **not** follow profit factor — HEAVY is the best per-bar cell on
profit factor and the worst on expectancy — and [#48]'s guard applies with the usual force. What
the table does say is that the three forms decompose the same 3,639 trades very differently: the
per-bar form splits them 27/44/28 and the session-to-date form 13/70/16, so "an unusually busy
bar" and "an unusually busy session so far" are not the same statement about the same trade.

**The signals partition exactly and the trade counts do not.** For every form the three
single-state filters admit exactly the measured signal, bar for bar and in total — 4,841 of the
unfiltered 4,889 for the per-bar form, the difference being the warm-up and the strays. The
trade lists sum to 3,612 against 3,639. Same cause as [#40]'s and the same conclusion: the
simulation holds one position at a time, so removing an entry moves which later signals are
free, and the trade-level decomposition is approximate where the signal-level one is exact.
**Stratify the signal, or accept the approximation** — and never read a count that moved as a
filter having found trades.

**Cost, and it is the most expensive condition so far.** `prepare` pays about 0.2 s per series
over 914,700 bars against `regime`'s 15 ms per lookback, because the baseline is a sliding
median down each bar-of-session column of a `[session, bar of session]` grid rather than a pass
along the series. Sixteen bytes per bar per series — 14.6 MB for one and 43.9 MB for all three,
against a 37.5 MB dataset without them. The per-combination gate is 0.14 ms against 3.6 ms for
the combination itself, so the filter is cheap and the preparation is what to watch when a sweep
asks for several series at once.

**Smaller choices in `volume.py`, recorded here rather than in the module ([#105]):**

- **The median, not the mean.** The baseline window straddles roll dates and holiday sessions,
  and a mean would carry a half-empty session or a rolled contract straight into the
  normalisation. A median of twenty ignores one or two of them.
- **Out-of-session prints are not volume here, in any of the three forms.** NT8 building bars
  against an ETH template would never form them, so they read zero rather than entering a sum or
  a per-bar count. Their labels are `UNDEFINED` either way, because a bar in no session has no
  bar of session to be compared against.
- **The rolling window does not reset at the session open.** "Volume over the last thirty bars"
  reaches back across the maintenance break at the start of a session, which is what the words
  mean, and the bar-of-session baseline divides out the systematic part of it exactly — the
  first bars of a session are compared against the first bars of other sessions.
- **A one-bar rolling window is refused**, because it is the per-bar form under another name and
  would otherwise build the same series under a second key.
- **A zero baseline is undefined rather than infinite.** A bar of session whose prior sessions
  traded nothing has no scale to be relative to.
- **`MIN_BASELINE_SESSIONS` is a floor rather than a parameter**, and it is both the shortest
  legal window and the number of observations the window must actually hold. Holes mean the two
  are different questions.
- **The thresholds are conventional starting points, not a calibration.** 0.7 and 1.5 against a
  median put roughly a quarter of bars in each tail on this data; they are resolution-dependent
  the way [#40]'s are and will want different values at 15 and 30 minutes.

### ~~M10.3~~ — the compact trend label: done ([#42])

`nqbt/trend.py`. Three facts about one pair of EMAs — where price sits against the slow one,
which way the slow one is sloping, and which way round the two are stacked — each voting `+1`,
`-1` or `0`, summed into an **agreement score** and cut by `min_agreement` into `DOWN`, `MIXED`
and `UP`. One `int8` per bar rather than a wall of MA booleans, and `trend_filter` is a bitmask
integer for exactly the reason `phase_filter`, `regime_filter` and `volume_filter` are.

**The memory switch is not switched on, and that is enforced rather than intended.** [#42]
assumed the label would need `keep_values=True` on the sweep's shared moving-average grids —
the 8-bytes-against-1 setting that is 285 MB of raw EMA values over the run below and grows
with the period axis. It does not. `trend_grid` builds a values-carrying grid over *its own*
two periods, reads the labels out of it and lets it go, so nothing outside that function ever
sees an MA value and a parallel worker is handed the labels alone. Recomputing two EMAs costs
milliseconds against the pass that would otherwise be paid per worker. Pinned as a property of
a prepared dataset: asking for the label leaves `needs_ma_values` false, leaves every shared
grid's `values` at `None`, and grows `Dataset.nbytes` by exactly the label arrays.

**The averages are the label's own, not the archetype's.** Reusing whichever periods an
archetype happens to gate on would make the same label name a different measurement in each
one, and a stratification that is not comparable across archetypes is not a stratification. The
kind is fixed at EMA for the same reason — one definition, and `TrendKey` gains a field the day
an SMA label is actually wanted.

**No label is ever taken off two components.** The slope cannot be measured for the first
`slope_lookback` bars, and price and stack can. Letting those two decide would manufacture a
trend out of a warm-up, so the score is `nan` there and the bar is `UNDEFINED` — five bars of
914,700 below, because the NT8 averages emit from bar 0 and this module adds no warm-up of its
own. The components are still computed through it, since they are knowable and a review can
report them.

**Both agreement boundaries fall in the outer bands, which is the opposite of [#40] and
[#41].** Deliberately: `min_agreement` counts components that must agree rather than cutting a
continuum, so exactly that many agreeing is the case the parameter names.

**And the parameter has two settings rather than three.** Two float64 averages are essentially
never exactly equal, so a `0` vote essentially never happens and the score only ever takes odd
values — `-3`, `-1`, `+1`, `+3`, and nothing else across all 914,700 bars below. `2` and `3`
therefore produce identical labels; `1` is the distinct one, and what it does is abolish the
`MIXED` band rather than widen the outer ones. Keep the parameter, because that switch is worth
having, and do not read it as a resolution knob.

**Gated.** 12 of the 14 captured trade logs are byte-identical, `sha256` included; the two
sweep summary tables differ by the five added parameter columns and are identical on every
pre-existing column — `compare_trade_logs.py --added trend_filter trend_fast_period
trend_slow_period trend_slope_lookback trend_min_agreement` reports `ALL PRE-EXISTING COLUMNS
IDENTICAL`.

**First stratification, and the interesting number is not in the profit-factor column.** Costed
MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1
tick, EMA 20 against EMA 50 with a 5-bar slope and unanimity, one combination run once per
trend:

| cell | bar share | signals | trades | profit factor | win rate | expectancy |
|---|---|---|---|---|---|---|
| DOWN | 37.2% | 4,400 | 3,280 | 0.657 | 0.316 | −10.79 |
| MIXED | 18.8% | 461 | 335 | 0.426 | 0.304 | −17.85 |
| UP | 44.0% | 28 | 24 | **1.815** | 0.458 | **+14.27** |
| all | 100% | 4,889 | 3,639 | 0.640 | 0.316 | −11.28 |

**The UP row is 24 trades and it is not a finding.** It is the best of three cells chosen after
looking, on the archetype [#48] exists to guard against exactly this on, and its own
`DeadCatParams` already refuses to signal there: 4,400 of 4,889 signals fall on `DOWN` bars,
which are 37% of the series. That is the row that matters. **The label is not independent of
the gates it sits beside** — a short-only archetype filtered by close-under-EMA and
close-under-SMA has already applied most of a trend filter, and stratifying it by one more
measures the overlap rather than the market. The label earns its keep on the review, where the
trades were not selected by these gates, and on an archetype that trades both directions.

**The decomposition is exact here on both counts, and only the signal one is guaranteed.**
Signals sum to 4,889 against the unfiltered 4,889, and trades to 3,639 against 3,639. The
signal identity is the property — no bar is undefined, so the three filters partition every
one — while the trade identity is this dataset being kind: the simulation holds one position at
a time, so removing an entry frees later signals and the trade-level sum is approximate in
general, exactly as [#40]'s and [#41]'s were. Do not promote it to a rule.

**Cost.** 0.76 s to prepare over 914,700 bars, dominated by the two EMAs and the vote pass;
11 bytes per bar per label — one float64 score and three `int8` votes, 10.1 MB, against a
39.3 MB dataset without it. The per-combination gate is 0.16 ms. Every one of those figures is
against the 285 MB the same run's shared grids would have carried had the label gone through
`keep_values`.

**It does not close [#73], and the sequencing note on both issues is now settled.** This is a
coarse trend read as a *condition*, computed on the 1-minute averages the project already has.
[#73] is a *gate* on an average computed on genuinely coarser bars, it needs [#30]'s resampler,
and its hazard — stamping from the current incomplete coarse bar — does not arise here at all.
They are different things and both are still wanted.

**The fourth filter was one too many to keep copying.** All three signal functions ended with
the same four-gate chain, and adding a fourth pushed two of them past the complexity limit —
which is the lint rule doing its job rather than getting in the way. They now end with
`sim/filters.py`'s `apply_context_filters`, one conjunction shared by every archetype and
reached through a structural protocol, so the next condition is a single edit rather than three.

**Smaller choices in `trend.py`, recorded here rather than in the module ([#105]):**

- **Three states, not the eight a 3-bit composite would give.** Time of day already multiplies
  every other stratification, and the point of a *compact* label is to survive a
  minimum-stratum guard on a few hundred real trades. The components are carried separately for
  the review to report, which is where "*which* one dissented" belongs.
- **`UNDEFINED` is −1, not a fourth trend**, for the reason [#40]'s and [#41]'s are: it cannot
  be swept into a filter by accident, and it passes no mask including `ALL_TRENDS`.
- **A fast period that is not strictly shorter than the slow one is refused.** Equal periods
  make the stack permanently flat, and a longer fast period inverts what the label means
  without changing a single name — the kind of error that reads as a result.
- **The slope is a sign, not a magnitude.** A threshold on it would be in points, which is
  neither comparable across instruments nor across eras; the sign is scale-free and the
  agreement count already provides the coarseness a magnitude threshold would be reaching for.
- **Exact equality votes neither way**, so the flat case exists in the arithmetic even though
  float64 averages essentially never reach it. Cheaper than arguing about which side it
  belongs on.

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
because it produces confident, specific, wrong conclusions that feel earned. All three are
`nqbt/guard.py`, and the correction that matters is family-wise rather than per condition. Free-text notes are
stored but structurally excluded from evaluation ([#49]) — written knowing the outcome, they
would yield perfectly circular findings.

#### M11.1 — Import: the NT8 executions-grid adapter ([#45])

`nqbt/trade_import.py` is the only format-aware code in the project, and adding a second source
is meant to be one more function rather than a second pipeline. The grid is exported from
Control Center → Executions; `tests/test_trade_import.py` carries a real export verbatim as its
first fixture, so every claim below is pinned rather than remembered.

**Ties are ordered by the position chain, never by file order.** The export is newest-first, so
reversing it gives chronological order — but that is not sufficient, and the counter-example is
two real exports of *one* history taken a day apart, which carry the same two fills at
`2:30:42 PM` in **opposite** order. File order is therefore not a dependable tiebreak, and
sorting on the timestamp is worse. `Position` is dependable: it is the running position *after*
each fill, so within a tied group each fill's value is the previous one plus its own signed
size, and the chain has exactly one arrangement. The adapter reconstructs it, which also makes
the walk a whole-file consistency check — a missing fill cannot be bridged, and is refused
rather than silently absorbed.

**The date order is never inferred from the values.** Row timestamps are `DD/MM/YYYY`; the
`Time=` field inside Control Center *log* messages is `M/D/YYYY`, and the first twelve days of
any month parse to a real but wrong date under the other reading. Two formats are accepted and
each is tried over the whole column, but both are day-first: NT8's 12- versus 24-hour clock is
a display setting, whereas the date order is not something a value can be asked about.

**The timezone is required configuration, with no default.** The file carries none, and a wrong
zone shifts every trade by hours without erroring. `Europe/London` is right for this machine —
converting the sample's fills to UTC puts every one inside its bar's high/low range — but that
is a fact about the machine, not a property of the format.

**Legs are FIFO matches, not fills.** NT8 matches a partial exit FIFO, and the schema is per
leg, so each pairing of an entry lot with an exit fill is one row. The distinction is invisible
in the total and decides every row: the sample's first trade has two entry lots at different
prices, and averaging them reproduces the trade's P&L exactly while getting all three legs
wrong. A fill that crosses zero falls out of the same matcher as two trades, which is what
`stats` already assumes a flip to be.

**Costs come from the project and never from the file.** `Commission` reads `$0.00` on an
account that is charged, so `commission_per_contract` defaults to `costs.LIVE`'s figure here —
deliberately the opposite of the simulator's zero, which is correct only for reconciling
against a Strategy Analyzer run. Slippage is not applied at all: a real fill price already
contains it.

**What the source cannot supply is null, named, and refuses to be summarised.** `UNPOPULATED`
is exactly `trades.NULLABLE` and carries a reason per column, because the review has to *state*
why it omitted a statistic ([#48]). The absent integer columns keep a nullable dtype rather
than a NaN-filled float one, so `stats.summarise` raises on an imported log instead of
returning a bar count nobody measured. Refusing is only half of the fix; omitting with the
reason is [#48]'s job, and [#81] is the same hazard reached through times.

**Coverage is measured per trade and whole trades are excluded together.** Whether a trade's
contract and dates are cached is a report the importer emits, not an assumption, and a trade
straddling the edge of the cache is set aside entire — half its P&L reviewed and half excluded
would misstate the trade itself. Nothing is dropped: `covered` is a column, and `reviewable` is
the subset a review may be computed over. The export lags live by roughly two hours, so the
newest session is routinely uncovered and that is a normal reading rather than a fault.

**Both ends of an export can hold a trade that is not a trade.** Fills before the first flat
position belong to a trade that began before the window, and fills after the last flat belong
to a position still open. Both are dropped and both are counted, so "some trades are missing"
is always visible as a number.

#### M11.2 — Annotate: the market context at a trade's bars ([#46])

`nqbt/annotate.py` joins a trade log to a `Dataset` and returns one row per trade carrying every
condition that dataset holds. It knows nothing about where the trades came from, which is the
point rather than a nicety: [#44]'s payoff needs the identical breakdown over a sweep's log and
over a real history, so a hypothesis raised on a few hundred real trades can be tested against
thousands of simulated ones.

**Annotate against the per-contract bars, never the back-adjusted series.** Back-adjustment
shifts every historical price by the cumulative roll offset, so a real fill at 18076.75 appears
nowhere in the continuous series — and **the lookup still succeeds**, because a timestamp is a
timestamp. What comes back is plausible at every stage and wrong at every comparison. The
defence is not documentation: every fill price is checked against the bar it matched, and an
excursion is refused rather than ranked. That is the cheapest guard in the project.
`contract_bars` exists so that reaching for the right series is easier than reaching for the
wrong one, and it excludes the *raw* continuous series too, which splices two contracts' prices
across a roll. The live roll offsets are `nqbt splice --diagnostics`; they are hundreds of points
over the window this review covers, which is why a tick of tolerance cannot admit one.

**`price_tolerance` is in points and defaults to zero.** A real fill is inside its bar by
construction. A *simulated* one need not be: a stop that gapped fills at the bar's open, moved
by the run's slippage, which is a tick or two outside. That is the only legitimate excursion, so it is a number
the caller states rather than slack the check carries.

**A fill belongs to the bar stamped strictly after it**, so the bar stamped `s` covers
`[s - bar_minutes, s)` and a fill at 14:23:47 is in the bar stamped 14:24. The boundary decides
more than it looks: the executions grid prints whole seconds, so a fill printed at 14:24:00
happened somewhere inside the second beginning there and belongs to the bar stamped 14:25.
Confirmed end-to-end on the sample — converting the eight fills to UTC and mapping each this way
puts every one inside its bar's high/low range, with the 17:00:29 stop landing exactly on the
17:01 high.

**A bar's own stamp is not a fill time, so a log that carries bar indices keeps them.** The
simulator writes `entry_bar` and an `entry_time` that *is* `index[entry_bar]`; resolving that
timestamp under the fill rule would move every simulated trade one bar forward, and nothing
downstream would look wrong. Where a log carries both, the two are cross-checked, which is the
one test that catches a log being annotated against a different series of the same shape —
another contract, or the same bars at another resolution.

**A trade matches whole or not at all**, across every leg and at both ends, whether or not the
exit side is being annotated. Half a trade's context recorded and half discarded would misstate
the trade itself, and it is the rule [#45] already applies to coverage. Nothing is dropped:
`matched` is a column and `reviewable` is the subset a review may be computed over. One level
down, a fill inside a hole in the bars is unmatched rather than joined to the next bar, because
the next bar is not the bar it happened in.

**Raw series always, labels only where the thresholds were chosen.** An efficiency ratio is a
fact about a bar and a regime is a cut through it, so `LabelThresholds` has no defaults and takes
each pair or neither. [#48]'s guard has to be able to state which cut it tested, and a default
would let a review report a threshold nobody picked. Every column is held as a nullable dtype
chosen from what it holds rather than from whether anything is missing, so an unmatched trade's
condition cannot read as `False`.

#### M11.3 — Review: stratifying realised P&L by condition ([#47])

`nqbt/review.py` groups one trade log by one condition at a time and reads a `stats.summarise`
over each group. **Nothing in it defines a statistic**, which is the whole point of M9: a review
computing its own win rate would eventually disagree with the sweep's, and the disagreement would
be invisible because both numbers would look reasonable. A stratum's row is therefore literally
the summary's fields, and `tests/test_review.py` asserts a row equals `summarise` over exactly
that stratum's legs.

**Time of day is reported first, and paired with both forms of volume.** It is the
stratification most likely to show real structure in a discretionary record, because it captures
attention, liquidity and the trader's own routine at once, and unlike a moving-average gate it is
not something the trader was consciously optimising. Both forms of volume travel with it because
neither answers the question alone: relative volume is normalised per bar of session by
construction ([#41]) and says whether a bar was unusual *for the time*, while the absolute count
says whether there was anything there to trade at all. "This hour is always busy" is a high
absolute median beside a relative one near 1; "this hour was unusually busy" is the relative
median moving. Phases print in session order rather than alphabetically, which is the one
ordering error that would pass every other assertion.

**The final phase is an artefact until it is separated from the clock.** It contains the
session-close flatten ([#16]), so a time-of-day stratification will always show it as anomalous.
The report carries `session_close_share` per phase for exactly that reason — and omits it, rather
than printing zero, when the log's exit reasons are its source's own vocabulary instead of the
simulator's, because an imported grid's `Name` field cannot name the clock and a zero would read
as "none of these were closed by the clock".

**Only a categorical condition is a stratification.** A raw series is excluded rather than
bucketed: where to cut it is the review's most consequential decision and `LabelThresholds` is
where a review states the cut it tested, so a default here would let a report claim a threshold
nobody picked. The rule is dtype plus cardinality — a float column is a series, one value
separates nothing, and past a dozen values the split is a list of trades rather than a
comparison. The report says how many conditions it could not cut by, so an excluded condition is
visible as a number rather than as silence.

**A log that leaves a column empty omits the statistics that column feeds, in the producer's own
words.** `summarise` refuses an imported log rather than reporting a bar count nobody measured
([#45]), which is the correct half of the fix; the other half is this module's, and the wording
comes from `trade_import.UNPOPULATED` rather than being reinvented here. Mechanically the absent
columns are filled with a placeholder so that `summarise` runs at all, and every field a filled
column feeds is dropped by name before a row is built — so **no placeholder can reach a reported
number**, which is a property a test pins rather than a convention held in someone's head. The
mapping from column to fields is data (`STATISTICS_FROM`), so an absent `r_multiple` costs the R
statistics and nothing else.

**The separation is a range across strata, and it is a candidate rather than a finding.**
Conditions are ranked by how far the chosen statistic sits between their best and worst reported
stratum, over strata meeting a minimum sample — the floor `sweep.rank` already enforces, for the
same reason: the smallest samples produce the most extreme statistics and would otherwise lead
every ranking. A stratum under the floor is still reported, and marked. An infinite profit factor,
which a stratum with no losing trade reports, is dropped from the range rather than allowed to top
it.

**What [#48] owns.** The minimum stratum is one of its three mitigations. The permutation test
against shuffled condition labels and the recent-trades holdout are `nqbt/guard.py`'s, and
`review.STATUS` names it, because the failure mode here is not a wrong number but a right number
read without its context — and that number would feel earned.

#### M11.4 — The statistical guard ([#48])

`nqbt/guard.py` is what stands between a stratification and a confident wrong conclusion, and
the reason it is not optional is arithmetic rather than caution. A few hundred trades against a
few dozen conditions is a multiple-comparisons machine: **some condition will split that sample
impressively, and most of the time it will be noise.** A review without this is worse than no
review, because what it produces is specific, confident and wrong, and feels earned.

**The minimum stratum was already there, and is one third of the guard.** [#47] enforces the
floor `sweep.rank` enforces, for the same reason, so this module imports it rather than
restating it.

**The permutation test shuffles the P&L and leaves the strata alone.** Every stratum keeps the
size it had and only the association is destroyed, which is the null the question actually
needs: *would labels that carried nothing have split these trades this far?* Mechanically the
trades are sorted into contiguous strata once and each draw is a `np.split` of a permuted
vector, because `summarise` per stratum per draw is two orders of magnitude too slow — the same
move, for the same reason, that `stats.trade_statistic` was added for in [#31].

**The correction is a maximum over one shared shuffle, not a Bonferroni.** A per-condition
p-value answers the right question only for a condition chosen for a reason; taking the widest
separation on offer and reading its p-value is the same machine one level up. So each draw
permutes the P&L once, every condition is re-separated under *that* permutation, and the
maximum across them is the family's null — a max-statistic correction, which is far less harsh
than Bonferroni precisely because conditions measured over the same trades move together, and
these do. `tests/test_guard.py` demonstrates it on a dozen conditions drawn from nothing: the
best of them is unremarkable against the family and would have looked publishable alone.

**A screen narrows to the trades every condition labels.** A maximum is only meaningful over
comparable numbers, and conditions measured on different subsets are not comparable. The count
set aside is reported rather than absorbed, which is the rule [#46] already applies to a trade
that matches only in part.

**A separation may only be measured in a rate.** `STATISTICS` is `review.REPORTED` intersected
with `stats.TRADE_PNL_STATISTICS`: outside the first a statistic is not one the review printed,
outside the second it cannot be had from a P&L vector and thousands of draws would be
unaffordable. That drops `net_pnl` for a third reason that would have applied anyway — a sum
separates strata by how many trades they hold.

**The holdout re-reads the split; it never re-chooses it.** The best and worst strata are
picked on the earlier trades and then evaluated on the most recent ones as they stand. Picking
again on the recent trades would hold nothing out and would return the in-sample answer wearing
a different name. The share defaults to a quarter rather than a fixed count because both halves
have to clear the floor and the sample size is not known in advance.

**What the guard still cannot say**, and the report says so itself:

- **A null is not a cause.** A small p-value says the split is unlikely if the labels carried
  nothing. It cannot say the cause is this condition rather than something travelling with it —
  and time of day travels with almost everything ([#43]).
- **The family is the conditions in *this* screen.** Not the ones tried in an earlier one, and
  not the threshold a raw series was cut at: a `LabelThresholds` pair chosen after looking is a
  comparison the screen cannot see. That is why [#46] refuses to default one.
- **The holdout's two halves are not independent samples.** What is held out is the *choice* of
  strata, not the trades — they are inside the screened sample. And its strata are small by
  construction, so `reported` is usually false on a few hundred trades and the row is a
  direction check rather than a measurement.
- **It guards a review, and the same argument binds [#31] and [#24].** The best of nineteen
  contracts, and a ranking over archetypes × combinations × resolutions × contracts, are the
  same machine with more cells. The array-level functions take a P&L vector and one label per
  trade for that reason; `dispersion.spread_vs_resampling` is the contract-shaped instance
  built first.

#### M11.5 — Discretionary context ([#49])

`nqbt/notes.py` stores what a trade log cannot: why a trade was taken, what was going on at the
time, a screenshot to look at later. It is kept, it is shown, and it is never an input to
annotation, stratification or the guard.

**The exclusion is enforced rather than intended, because the finding it would produce is
guaranteed rather than merely likely.** A note is written after the fact, knowing the outcome,
so a loser attracts "I was impatient" and a winner attracts "clean setup". Stratifying by one
would rediscover the outcome and report it as structure — and it would be the widest separation
in the report and the most impressive-looking result in it. Nothing downstream could tell that
from a real one, because every number in it would be correctly computed.

**A note column would pass every filter the review already has.** `review.stratifiable` excludes
a raw series by dtype and a split by cardinality, and free text is neither a float nor
high-cardinality on a small sample — three recurring phrases across thirty trades is exactly a
stratification's shape. The rule therefore cannot rest on a note failing to look like a
condition, and `tests/test_notes.py` pins that it does look like one.

**Structurally that means a sidecar and three doors.** Notes live in a frame keyed by `trade_id`
and never as columns on a trade log or an annotation, so there is nothing to group by; an
annotation's conditions are read off the bars, which leaves a log column no route into one in
the first place. `notes.check_excluded` is called by `annotate.annotate_trades`, `review.review`
and `guard.guard` and refuses free text at each. `notes.alongside` is the only join that
attaches a note to anything — for the trade-log viewer ([#52]) and for a per-trade export — and
it refuses a frame already carrying one, so a joined frame cannot travel onwards.

**A duplicate key is an error rather than a last-one-wins.** Two notes on one trade fan a join
out into extra rows, and extra rows that look like more of the same data move every number
computed over them.

**Worth revisiting only for deliberate qualitative coding** — a fixed set of categories chosen
*before* any outcome is examined. That is a different activity from what M11 does, and it would
be a different column with a different provenance rather than this one relabelled.

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

**Done.** `ruff` and `mypy` both report zero on `nqbt/` and both gate CI; `CONTRIBUTING.md`
§"Linting and typing" is the rule and the workflow is the live check. What is recorded here is
the reasoning that outlives the counts.

**The gap that mattered was dtype, not coverage** ([#54]). The package annotated well and none
of it was checked, so a bare `np.ndarray` read as a type while saying only "some array" — and
here the element type is load-bearing. `MovingAverageGrid.below` is bool where `.values` is
float64, which is the whole 66 MB against 595 MB decision; `SessionInfo.trading_day` is
`datetime64[D]` where `.in_session` is bool; and the `@njit` loop's `out` is a float64 matrix
into which `exit_reason` and `direction` are written as floats and mapped back to strings later,
the one place a wrong dtype is silently lossy. `nqbt/arrays.py` names each dtype once and
`tests/test_array_dtypes.py` asserts the arrays really carry them, because an annotation nothing
checks is worse than none. **Do not annotate inside an `@njit` function expecting numba to use
it** — it infers from the call, ignores the annotation, and a wrong one reads as a guarantee.

**Locals carry their type too, and mypy is what says they are right.** The signatures were
already annotated; the bodies were not, so a reader had to re-derive from the expression what the
signature stated once. Roughly 750 locals now name their type, derived from what mypy itself
infers rather than from reading each expression, and the two constraints that shaped where they
do not are worth keeping: a name can be annotated only **once per scope**, so the first binding is
the declaration and one bound in two arms of a branch is declared above it; and `AnyArray` is a
concrete `dtype[generic[object]]` rather than a wildcard, so annotating a local with it
type-checks at the assignment and fails at every use after it.

**The stubs are still not the runtime.** mypy proves an annotation is consistent with the stubs,
which is what `DateArray` was before numpy 2.5. So the 178 array-alias locals were also checked
the other way, by instrumenting a throwaway copy of the package with a dtype assertion after each
one and running the suite over it — all 178 match. `OffsetArray` is the one alias this pass
added: `np.intp` is what `flatnonzero`, `argsort` and `searchsorted` return, and it is not
`int64` on every platform, so `IntArray` would have been a promise the package cannot keep.

Three decisions the configuration now carries, each with its reason beside it in
`pyproject.toml`:

- **`D401` is off.** It wants an imperative verb where `CONTRIBUTING.md` says a docstring names
  *what* a thing is, which is a noun phrase. The two rules cannot both hold.
- **`max-args` is 10, not ruff's 5.** An entry point taking one keyword per choice its caller
  must state is the shape of this codebase. What is left above ten is the parameter blobs [#59]
  fixes, and each of those carries its own `noqa` naming the issue — so the rule still points at
  the real problem instead of being blanket-disabled.
- **numba has no keyword-only arguments**, so a jitted loop's toggles are positional booleans
  and `FBT001`/`FBT003` are ignored for exactly the five modules that contain one — per file
  rather than per line, because a jitted module's every toggle is one and an inline `noqa` at
  each of the 27 sites would say the same thing 27 times.

`Any` survives where it is the honest type — a condition's labels are whatever pandas holds them
as, an archetype's `run`/`legs`/`signal` differ in signature per archetype — and every such site
says so. joblib is the one untyped import: three symbols in one function did not earn a stub
under `mypy_path`.

**The order was the point.** A type checker introduced with a strict config and hundreds of
errors gets switched off, so both tools reached zero *before* the CI job that enforces it
existed, in a separate commit each.

**The stubs move under you, and a clean local run does not prove a clean CI run.** `DateArray`
was `NDArray[np.datetime64]` and type-checked against the numpy in the venv; CI installs the
newest, and numpy 2.5 changed that parameter's default from `dt.date | int | None` to `Any`, so
the alias smuggled in an explicit `Any` and the new gate failed on a machine nobody had run.
Every alias that could carry a defaulted parameter now states it.

**The fix was to stop letting the resolver choose.** Every dependency and dev dependency is now
pinned `==` rather than `>=`, so a local zero and a CI zero are the same measurement; dependabot
raises the bumps and each is tested like any other change. The failure mode that forced it is
worth keeping in mind whenever a pin is loosened: CI resolves fresh, one minor version behind
locally is enough to hide a failure, and `extend-select = ["ALL"]` gives ruff the same reach —
a release that adds a rule fails a build nobody touched.

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

**True Range crosses a roll boundary unchanged, and the splice is not special-cased** ([#23]).
The prediction that reached the ticket was "back-adjustment makes the gap small but not zero,
so ATR steps at each of the 18 rolls". Half of that is wrong and the half that is right is
right for another reason, which is why measuring it was worth the afternoon.

The gap is not small-but-not-zero — the residual basis is **exactly zero**, on all 36 seams
across both roots. The shift is `front_close − back_close` at the last bar the front contract
contributes, and that is precisely the bar a seam reads its previous close from, so the two
cancel bit for bit rather than approximately. Nothing is left at a seam except the back
contract's own move over the break, which is measurable inside one contract with no splice in
it. `splice.roll_seams` produces the table and a test pins the property against a *drifting*
basis, so an offset read off any other bar fails it.

ATR does still step, so both standing consequences hold — do not read the step as a volatility
event, and judge an ATR-sensitive rule per contract ([#31]). What changed is what the step
means, and therefore what a fix would have to fix: **the largest steps are missing sessions,
not roll artefacts.** The front contract owns its final session and NT8's archive holds only
its first hour, so most seams today span a whole absent trading day rather than the maintenance
break. That is the already-recorded cost of correct roll dates, and nothing about the splice or
about True Range would improve it — resetting TR at a roll would have hidden a data gap behind
a plausible-looking number, which is the more expensive failure.

The cheap generalisation: **a prediction with a mechanism in it is worth measuring even when
the conclusion turns out unchanged**, because the mechanism is what the next decision is made
from.

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
precisely and it has ground truth. `InsideBar.cs` followed for the same reason (M22);
`InsideBarTrailing.cs` remains unported and is the cheapest further archetype available.

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

**Contract validity is the instrument registry's answer** ([#69]). Whether a file in `data/archive/` names a contract used to be decided in three places, and the one that fired first was the one least related to whether the thing is tradeable here. `ContractId.__post_init__` checked the month against a module-level quarterly set; the root was never checked at all. So `NG 02-26` was rejected for **being February**, not for being natural gas — and `NG 03-26` passed every gate, was cached under `cache/bars/NG/`, and failed only much later at `contract.instrument`, as a `KeyError`, at the point something asked for its money spec.

Validity is now one question asked of `INSTRUMENTS`: the root must be a registered `Instrument`, and the month must be one that root's `contract_months` lists. `MONTH_CODES` carries all twelve CME letters, because `cache_key` needs them regardless, and the *listed* cycle moved onto the instrument where it varies — the equity index roots list `HMUZ`, gold `GJMQVZ`, silver `FHKNUZ`, crude all twelve. Adding a root is one `Instrument(...)` entry and nothing else.

ES, GC, SI and CL are registered on that basis, together with the micro beside each full-size root — MES, MGC, SIL and MCL. Each entry's `tick_size` × `point_value` reproduces the tick value CME publishes — $12.50, $10.00, $25.00 and $10.00 full-size, $1.25, $1.00, $5.00 and $1.00 micro — which cross-checks both figures at once, and `tests/test_instruments.py` pins them.

**Micros are registered explicitly, not derived, and silver is why.** The obvious rule is "prefix M, divide the point value by ten", and it holds for four of the five pairs. Micro silver is **SIL**, not MSI, and it is 1,000 troy ounces against SI's 5,000 — a fifth, not a tenth. A derived registry would therefore have produced a symbol nothing exports under *and* a silver point value **2× too large**, in the one place every dollar figure in the project is obliged to route through. The tick *size* is genuinely shared within each pair, which is what makes the pairs look derivable in the first place. `test_a_micro_cannot_be_derived_from_its_full_size_root` exists to stop the registry being "simplified" into that rule later.

A root may also carry a digit now (`M2K`, `6E`). The regex was letters-only, so those failed with "cannot parse contract name" — a parse error standing in front of the real answer. Which roots exist is the registry's question, and the regex should not be answering a different one.

**The registry is deliberately ahead of the rest of the system.** Registering a root makes its exports nameable and its dollars convertible; it does not make it tradeable here. Two known gaps, neither closed:

- `Instrument.session_template` is a bare `str` that nothing resolves — `SessionTemplate` is threaded through `sessions`, `resample` and `randomentry` as an argument with the index-ETH default instead. Nothing diverges today, because the Globex ETH window is 18:00–17:00 ET for equity index, metals and energy alike, but the field must be wired from NT8's Data Series window before anything consumes it.
- The $1.50 round-turn commission is an index-futures figure and does not transfer. Costs are per-caller and default to zero, so this is the standing free-money trap rather than a new one.

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
[#47]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/47
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
[#69]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/69
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
[#126]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/126
[#127]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/127
[#161]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/161
