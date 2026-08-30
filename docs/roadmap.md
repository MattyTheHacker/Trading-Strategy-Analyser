# Roadmap

**How this file relates to the issue tracker.** The issues carry **everything that changes** — scope, acceptance criteria, checklists, ordering, dependencies and status. This file carries **what stays true after the work lands** — the findings, the constraints that span milestones, the traps that cost real time, and the decisions taken so they are not silently re-litigated. When the two disagree about scope or order, the issue wins; when they disagree about reasoning, this file wins.

**Plans do not live here.** Ordering is GitHub's `blocked-by`/`blocking` dependency graph, status is the issue's own state, and grouping is its epic and milestone. This file used to carry a hand-maintained order-of-work table; it duplicated all three, went stale on every landing, and was removed for that reason. To see what is next, ask the tracker:

```bash
gh issue list --state open --label next-up
gh issue list --state open --milestone "Phase 3 — Review system"
gh issue view <n>                       # blocked-by / blocking / sub-issues
```

Four things live here and nowhere else, because an issue is the wrong home for them: the **standing constraint** and its expressibility checklist, the **order-lifetime research**, the **standing rubric**, and the **decision record**. A closed issue is not read; a finding that outlives its milestone therefore belongs in this file rather than in the issue that produced it. Everything else is a paragraph of context with a link.

Precedence when sources disagree: [backtest_tool_spec.md](backtest_tool_spec.md) and the project's own docs first, [trading_concepts.md](trading_concepts.md) Part II second. The discretionary-practice notes are a source of framing and of numeric definitions we lack, not a source of priorities.

______________________________________________________________________

## Why the order is what it is

The order itself is in the tracker (see above). What follows is the reasoning behind it, which the tracker has no field for.

**Why the order looks like this.** The request was "add EMA crossover and squeeze breakout", but neither was reachable and neither was where the cost is: the simulator was **short-only** (M15, now paid), the indicators they need have an unpaid NT8-parity debt (M16), and `sweep.py` is hardcoded to `DeadCatParams` (M17). That infrastructure is ~all the work; the archetypes themselves are then small. It also pays for the NinjaScripts written and never ported — `PullBackAndGo.cs` is now done, leaving `InsideBar.cs` and `InsideBarTrailing.cs`, both long-capable and both using `ATR()`.

**Why M16 left the code queue.** M16 was scheduled ahead of M17, but its three substantive sub-issues are each *"read the value out of NT8 and pin it"* — the milestone's own instruction is **do not answer from memory**, so hand-rolling the recursions before the readings exist is precisely the failure it was written to prevent. That makes M16 NinjaTrader time, and it now shares that constraint with [#66] and [#67]. M17 has no NT8 dependency, is an equally hard prerequisite for M18, and is therefore the better use of code time. **Split the queue by resource, not by milestone number.**

Work needing NinjaTrader time and work needing code time form two queues, and neither blocks the other in the general case — though a single milestone can need both, as M18 did. The `needs-ninjatrader` label is the live split; do not restate its contents here.

**A booked NinjaTrader session pays for itself several times over, and the reason is not the tickets it closes.** The 2026-08-16 session closed M16 and both outstanding reconciliations, and it found two things reasoning would not have: Keltner matching neither half of the common definition, and the trade-list export being in the machine's display timezone rather than UTC. Both were invisible from the Python side. Book the session for the questions, not the queue — `gh issue list --label needs-ninjatrader` is what is actually outstanding.

**[#23] is settled on both halves, and the roll half needed no NinjaTrader time after all.** True Range does not reset at a session boundary, and there is nothing to reset it to at a roll either: back-adjustment cancels the contract basis exactly at the seam, so the step is the price move over whatever break the seam spans. Rule and evidence in `docs/nt8-fidelity.md`, "True Range at a roll boundary"; the decision and what it cost to reach are under "Decisions taken".

### What M15.5 changed, and the lesson that outlives it

The `PullBackAndGo` reconciliation was not a formality. It found **two direction-general fill-semantics defects**, both recorded with their evidence in `docs/nt8-fidelity.md`:

- **A stop that gaps fills at the open.** Modelled on the entry side since the beginning and never on the exit side, so every gapped stop exit was optimistic. **It moved the short side too** — always to a worse fill, never a better one — which is why nothing in the existing suite caught it.
- **A stop entry at or through the market is never submitted.** DeadCatBounce's trigger cap makes this structurally impossible for it, so the simulator had no notion of submittability at all.

**The lesson is the one worth carrying forward: a single archetype cannot exercise the fill model.** Both defects were unreachable from DeadCatBounce by construction, not by luck, and both had been live for the entire life of the project. **M18 confirmed it, and confirmed that two archetypes are not enough either:** its market-on-next-open entry reached a rule neither port could — an entry whose protective stop lands at or through its own fill — because both ports place the stop against a trigger the fill is defined relative to. Each new mechanism is a new part of the fill model with no evidence behind it yet, and `bracket.py` inherits whatever is wrong. This is the argument for reconciling each archetype rather than trusting the shared engine because the first one passed.

**Cheap, and unblocked:** porting `InsideBarTrailing.cs`. It has C# ground truth, which makes it the cheapest *trustworthy* archetype available, unlike M18 and M19. `InsideBar` — the structural form of the squeeze idea, and the reason to do it before M19 is built from scratch — is done (M22 below). `InsideBarTrailing` is the second consumer of `EXIT_SIGNAL`, which M18 has now made a working exit rather than a reservation — and it is the first chance to check the signal exit against a trade list.

Deliberately unscheduled work carries no label of its own — the reasoning for each is in its milestone note below, and the issue is the record of whether it is queued.

______________________________________________________________________

## Standing constraint, extended

The prime directive — match NT8's default bar-close fidelity, never exceed it — governs the **simulation** side only.

The review side takes real fills, which are genuinely tick-precise, and that is not a fidelity violation because nothing is being simulated. **The trap is letting that precision leak backwards.** A real trade filled at 18076.75 mid-bar is evidence about the market; it is not evidence that the simulator should model intrabar fills. Keep the annotation path read-only with respect to `nqbt/sim/`: the review may *describe* what a real trade did and compare it against what the simulator would have done, but it must never feed a fill rule back into the `@njit` loop. If those two ever need reconciling, the trade list wins for *facts* and NT8 wins for *fill semantics*, and they are different questions.

### An original archetype has no C# to lose to

`CLAUDE.md` says "when the C# and intuition disagree, the C# wins". DeadCatBounce was a **port**, so that rule always had a referent. EMA crossover and squeeze breakout are **originals** — there is no NinjaScript, so the rule has nothing to point at. That inverts the workflow and it needs stating before the first original is written, not after.

- **The prime directive still binds**, in full. It constrains the *simulator* — bar-close OHLC fills, no intrabar tick precision — and the simulator is shared by every archetype. Nothing about inventing a rule set licenses a more precise fill model for it.
- **For an original, the Python is the specification** and the NinjaScript is written *from* it, not the other way round. The reconciliation is unchanged in form: export Trades, diff leg-for-leg.
- **Development stays in Python. The port happens on promotion, not on creation.** Decided deliberately — see "Decisions taken". An archetype is explored, swept and discarded entirely in Python; only one that looks worth trading earns the C# work.
- **So a developing archetype is Tier-1 only, and that has to stay visible.** Today "validated against NT8" is a project-wide property, true of the only archetype there is. With Python-first originals it becomes a **per-archetype** property, and a sweep table that ranks a reconciled archetype against an unreconciled one is comparing a measurement with an assumption. M17 records it as a registry field and a results column for exactly this reason.
- **The failure mode is accumulation** — three archetypes, none ever opened in Strategy Analyzer, all quietly trusted because the *first* one was. Mitigations: port `PullBackAndGo.cs` early so the new long path is proven against real C# while it is cheap to fix ([#17]), and make Tier-1-only status a visible column rather than a remembered caveat.

**The constraint runs the other way too, and this is the non-obvious half.** Writing Python first means the platform gets no vote until the port, so a strategy can be built that NT8 cannot express — and discovering that after a promising sweep is the expensive order to find out. The mitigation is to know the platform's limits *before* designing against them, which is what "Order lifetime in NT8" below exists for.

**Expressibility checklist, to be run against a new archetype's design before building it.** Each item is somewhere NT8's managed approach constrains what a strategy can be:

| question                                             | current answer                                                 |
| ---------------------------------------------------- | -------------------------------------------------------------- |
| How long must an entry order rest?                   | Any lifetime is expressible — see "Order lifetime in NT8"      |
| Does it need a true OCO pair?                        | Only via the unmanaged approach, which costs the whole bracket |
| Does it need to reverse directly from long to short? | Not supported by the simulator either; see [#13]               |
| Does it hold through the session close?              | **It cannot.** Flat before the close is mandatory — see below  |
| Does it need more than 4 entries per direction?      | `EntriesPerDirection` is a strategy property, not a limit      |
| Does it need an indicator NT8 computes differently?  | Assume yes until pinned — see [#19]                            |

The list is short because most of it has now been researched. Extend it rather than rediscovering an item the hard way.

### Flat before the session close is a hard constraint, not a detail

**Every position must be flat before the session close.** This is a prop-firm account rule, so it is not a preference, a parameter, or something a promising strategy gets to negotiate with. It also matches NT8, where every strategy in the submodule sets `IsExitOnSessionCloseStrategy = true`, so Tier 1 and Tier 2 agree on it today. `ExitOnSessionCloseSeconds` varies between them — 30 on both stop-market ports, 180 on both InsideBar scripts — and **a backtest ignores the difference**, flattening on the session's last bar either way, so it stays one default rather than a per-archetype setting ([nt8-fidelity.md](nt8-fidelity.md) §M22).

**It is already implemented — do not "add" it.** `sessions.force_flat_mask` produces the per-bar mask, the `@njit` loop exits everything still open at `EXIT_SESSION_CLOSE`, and `block_entry_at_session_close` stops a signal firing on a bar that would immediately be flattened. The maintenance break falls out of the same machinery: sessions are the unit, so no position can span 17:00–18:00 ET, and none can span the Friday-to-Sunday weekend.

**What it means for design, which is the part worth writing down.** Maximum hold time is bounded by the session — roughly 23 hours, and in practice far less. Any archetype whose edge depends on holding overnight or across a weekend is not buildable under these rules, and that is a design constraint to apply *while* writing the Python, not a discovery to make at port time. Concretely, for planned work:

- ~~**M15** ([#16])~~ — **done, and half of it later reversed by [#208].** A resting entry order is *not* cancelled at the flatten point: NinjaTrader tests it for a fill and flattens the position it opens at that bar's close, and the simulation now does the same in all five entry loops. What survives is the distinction M15 drew — `block_entry_at_session_close` only ever guarded a *new* signal on that bar, never an order resting from the one before — and it is the half that was right. [nt8-fidelity.md](nt8-fidelity.md), "A resting entry fills on the force-flat bar, and is flattened at its close".
- **M13** ([#30]). The forced-exit share should rise sharply with bar size. At 30-minute bars a position opened near the close has almost no bars in which to reach a target, so more of its outcomes are decided by the clock than by the rules. Worth measuring alongside the ambiguous-bar rate, and for the same reason — both are ways a coarse resolution can look different without the strategy being different.
- ~~**M10.4**~~ ([#43]) — **done, and measured.** The final session phase has *structurally* forced exits, so a time-of-day stratification will show it as anomalous; **that is an artefact, not a finding**, and any result touching the last phase has to separate "this hour trades badly" from "this hour's trades were closed by the clock". `timeofday.FORCED_EXIT_PHASE` names the phase so a caller can exclude it. On costed MNQ from 2024 the effect is real and small — `session_close_share` reads 0.0016 on `CLOSE` against 0.0001 overall, because a 1-minute DeadCatBounce holds for minutes. Expect it to matter at 15 and 30 minutes.
- **M18 and M19** ([#34], [#51]). The prediction here was that crossover, holding until an opposite cross, would take a large fraction of its exits from the clock. **Measured: 1.0%** on costed MNQ from 2024 at EMA(9)/EMA(21). The reasoning was sound and the premise was wrong — crosses on 1-minute bars are frequent enough (one signal every ~22 bars) that holds end long before the session does. Expect the share to climb with the MA periods and with bar size, and read it rather than predicting it. A squeeze rests orders, which the flatten point ends only after that bar has been tested for a fill ([#208]).
- **Statistics.** The share of exits at `EXIT_SESSION_CLOSE` deserves to be a reported column rather than something buried in the trade log. A strategy taking 40% of its exits from the clock is not really the strategy its rules describe, and the aggregate profit factor will not say so.
- **The prop-account simulator** ([#75]) treats the daily flat as one of the rules it replays, alongside trailing drawdown and the consistency ratio.

~~**Holiday early closes are probably not handled — [#68].**~~ **Confirmed and fixed.** `force_flat_mask` derived its cutoff from the *template's* fixed 17:00 ET close, so on a CME half-day nothing reached it and the mask came back empty. It now counts down to the session's observed last bar, which is what `is_session_close` always did. The measured scale, the two things the observed end cannot distinguish, and what it did to the InsideBar reconciliation are in [nt8-fidelity.md](nt8-fidelity.md), "The session end is the observed last bar, not the template's".

______________________________________________________________________

## Order lifetime in NT8: making an entry rest longer than one bar

Researched ahead of need, because it was the open question that made M19's design look possibly unbuildable. **It is buildable.** Recording the mechanism now means future archetypes can be designed against what the platform actually does rather than against the one behaviour DeadCatBounce happens to use.

**How this was established.** NinjaTrader 8 is installed locally, so `NinjaTrader.NinjaScript.StrategyBase` in `NinjaTrader.Core.dll` was reflected over directly for method signatures, parameter names and enum members. That is primary evidence about the **API**. It is *not* evidence about **behaviour** — see "What reflection could not settle, and what did" below, which matters more than usual here.

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

`DeadCatBounce.cs` calls the **three-argument** overload `EnterShortStopMarket(int quantity, double stopPrice, string signalName)`, which has no such parameter and therefore leaves it false. So "entry orders are not GTC" is not a rule NT8 imposes — it is the default of a parameter the short overload does not expose. `NinjaTrader.Cbi.Order` carries `IsLiveUntilCancelled` as a readable property, so it can be asserted on a live order rather than inferred.

**Why `TimeInForce.Gtc` never helped — two different layers.** `DeadCatBounce.cs` sets `TimeInForce = TimeInForce.Gtc` and the order still expires after one bar. `NinjaTrader.Cbi.TimeInForce` is `{ Day, Gtc, Ioc, Opg, Gtd }` — an **exchange-level** instruction about how long a venue keeps a *working* order. `isLiveUntilCancelled` is **NT8's own managed-approach bookkeeping** about whether to auto-submit a cancel at bar close. Different layers, different owners, and neither implies the other. This is precisely the confusion that cost real time, and it is worth stating in those terms so it is not re-derived.

### Route 1 — `isLiveUntilCancelled`, and the obligation it creates

Setting the flag true means **nothing cancels the order for you**. That obligation is the whole cost of this route:

- Capture the order reference in `OnOrderUpdate`, whose confirmed signature is `OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity, int filled, double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)`, matching on `order.Name` against the signal name.
- Cancel with `CancelOrder(Order order)`.
- Release the reference on terminal states. `NinjaTrader.Cbi.OrderState` has **16** members — `Accepted, Cancelled, Filled, Initialized, PartFilled, CancelSubmitted, ChangeSubmitted, Submitted, TriggerPending, Rejected, Working, CancelPending, ChangePending, Suspended, AcceptedByRisk, Unknown` — so "terminal" must be enumerated deliberately. Treating anything not `Filled` as still-live is how a stale reference gets cancelled after it already filled.

**This is also how an N-bar lifetime is built.** NT8 offers exactly two native options: one bar (flag false) or indefinite (flag true). Anything in between is your own bar counter in `OnBarUpdate` plus `CancelOrder`. That is unglamorous but it means **every lifetime is expressible**, which is the thing that needed settling.

### Route 2 — unmanaged, the only native OCO

```csharp
SubmitOrderUnmanaged(int selectedBarsInProgress, OrderAction orderAction, OrderType orderType,
                     int quantity, double limitPrice, double stopPrice,
                     string oco, string signalName)
```

Confirmed, including the `oco` parameter; `Order.Oco` is a string tag and two orders sharing one cancel each other on fill. Unmanaged orders are not auto-cancelled at all.

**The cost is large and it is not a flag.** `IsUnmanaged = true` gives up `SetStopLoss`, `SetProfitTarget`, `EntriesPerDirection`, `EntryHandling` and managed position tracking. `DeadCatBounce.cs` uses **all** of them — four `SetStopLoss` calls, three `SetProfitTarget`, `EntriesPerDirection = 4`, `EntryHandling.AllEntries`. Going unmanaged means hand-rolling the entire four-leg bracket, which is a rewrite of the strategy, not a change of order call.

**Recommendation: never go unmanaged for lifetime alone** — route 1 covers that completely. Reserve it for a genuine two-sided OCO requirement, and even then check route 3 first.

### Route 3 — resubmit each bar, and why it is exactly equivalent for Tier 1

Keep the default one-bar behaviour and simply re-place the order every bar while the condition still holds. No order references, no cancellation logic, no unmanaged rewrite.

**For a bar-close backtest this is not an approximation of route 1 — it is identical**, provided the trigger price is unchanged on each resubmission. The fill test is the same per-bar OHLC comparison either way, and the simulator has no concept of queue position for it to differ on. If the strategy *recomputes* the trigger each bar then the two genuinely differ, but that is a strategy design choice rather than a platform artefact.

Live, they are not identical: each resubmission is a new order, so queue position resets, and the order churn is visible to a broker or prop-firm risk system in a way one resting order is not. Record the distinction so a live port does not silently inherit the backtest's convenience.

### What the simulator would need — specification only, no code yet

`deadcat.py` encodes the lifetime as a single equality, `elif pending_bar == i - 1:`. The generalisation is an expiry bar rather than a flag: hold `pending_expires_at`, keep the order live while `i <= pending_expires_at`, and add an `entry_order_lifetime_bars` parameter where **1 reproduces today's behaviour exactly** and 0 means "until cancelled". The force-flat bar is a fill opportunity rather than a cancel for all values ([#208]); cancellation on signal invalidation is archetype-specific and belongs in the driver, not the shared bracket code.

Same gate as every other change to this loop: at `entry_order_lifetime_bars = 1`, every existing trade log must come back **byte-identical**. Do not build it before M19 needs it ([#16] says so explicitly).

### What this changes about M19

The earlier note said the squeeze's resting orders "may simply not be expressible in NT8". **That is resolved — they are expressible**, and the trap downgrades accordingly: a one-sided rest is route 1, cheap and managed; a true two-sided OCO is route 2 and costs the unmanaged rewrite; route 3 gets the two-sided behaviour with no NT8 work at all in backtest and differs only live.

So the M19 design question is no longer "can this be built" but **"do I actually need native OCO, or is resubmission enough"** — and for a Tier-1 research backtester the answer is resubmission, with the OCO question deferred to a live port.

### What reflection could not settle, and what did

The API surface above is fact. **None of the behaviour below was**, and it was settled by a probe rather than by a trade list — `NqbtOrderLifetimeProbe.cs`, which places no bracket and writes its own `OnOrderUpdate` log. A Trades export was the wrong instrument for three of the four: they are questions about **cancels**, and a trade list carries only fills, so "cancelled the resting order" and "refused the second fill" are indistinguishable in one by construction. That is worth keeping stated, because [#67] originally specified a Trades export for all four.

The findings and their evidence are in [nt8-fidelity.md](nt8-fidelity.md) § "Order lifetime and the session edge"; in short:

- **Strategy Analyzer honours `isLiveUntilCancelled`.** An unreachable LUC order rested 199,669 bars across 146 session opens with the session-close handler off.
- **The cancel lands at the start of the next bar's pass**, so an order is live from submit+1 *through* the bar at whose close its cancel was issued. The three-argument overload reproduces `deadcat.py`'s `pending_bar == i - 1` exactly, which makes `entry_order_lifetime_bars = 1` byte-for-byte compatible.
- **`IsExitOnSessionCloseStrategy` is what ends a resting entry, not the session boundary.** With it false, nothing cancels. That collapses "until cancelled" and "cancel at the force-flat point" into the same behaviour here, because flat-before-close is not negotiable — but the cancel lands *after* that bar's fills, not before ([#208]).
- **The managed approach refuses an opposite-direction submission outright** — the second order is never accepted, at either `EntriesPerDirection`. So route 1 cannot express a two-sided OCO at all, and M19 falls to route 3 or route 2.

**Two things the probe found that nobody asked it for.** Order callbacks report the bar *before* the one a fill resolved against, which shifts every reading by a bar if taken at face value; and a resting entry **can** fill on the force-flat bar, which every entry loop refused. The second was a defect rather than a rule and was fixed by [#208]; the InsideBar trade list had been carrying an unjoined leg of exactly that shape the whole time.

## The standing rubric

What every change — including every milestone below — is checked against. These are ordered by how much trouble each has actually caused in this codebase, not by general principle.

1. **Is there now more than one definition of the same rule?** The most expensive defects here are all this: two triggers ([#10]), two empty-log policies ([#11]), two bracket engines ([#12]), and a third profit factor in `cli.py` ([#63]). In a project whose premise is *matching an external system exactly*, a duplicated rule is a duplicated place to diverge from it.

2. **Does the type say what the array actually holds?** `np.ndarray` does not distinguish the bool grid from the float grid, and that distinction is load-bearing. See [#54].

3. **Is the expensive work outside the loop?** Already a convention (`.claude/rules/sweep-and-context.md`), and the measurement discipline behind it is the strongest habit in the project — keep requiring the number, not the argument. M9 found a 9.4% regression this way that reasoning alone would have shipped.

4. **Would this pass if the code were wrong?** Applies hardest to tests asserting an absence. M9's layering tests were written, passed, and checked nothing. Mutation-test them.

5. **Is a class earning its place, or is it a namespace?** Prefer a dataclass with `slots=True` for a group of values that travel together; prefer a function for behaviour that does not need state. Do not introduce a class hierarchy to express one archetype.

6. **Is the abstraction extracted from two examples or invented from one?** M17 gets this right about the bracket engine ([#38]). M20a's bracket unification is the opposite case — deleting a copy, not inventing a shape.

7. **Is the reasoning in the code, where it does not belong?** ([#105]) Code should be readable on its own terms — prefer a clearer name or a smaller function over a comment explaining an unclear one. Docstrings say **what** a thing is and how to use it, and stay short. A brief comment is fine where something is genuinely non-obvious: a subtle index, a deliberate deviation, a workaround. **Reasoning, justification, measurements, decision records and traps go in `docs/`**, with at most a one-line pointer from the source.

   **This reverses what this item used to say**, which was *"does the docstring say why, not what — already the house style"*. That rubric produced a package where **33% of every line is prose** and the four highest prose-to-code ratios are the four newest modules, while the oldest sit near 0.3×. The homes were always here: this file's own header claims the **why**, and `docs/nt8-fidelity.md` claims the fidelity evidence. The source drifted into doing their job. [#105] carries the migration — and it *is* a migration, not a deletion, because much of that prose is evidence the project paid for.

### Standing traps

- **Do not "fix" a duplicated rule by copying the corrected version across.** That is what created the `explain.py` bug. One implementation, called twice.
- **A byte-identity gate on short-only logs does not cover a change that is symmetric in `d`.** Both copies of a forked bracket reduce to today's behaviour at `d = −1` regardless of whether they agree at `d = +1`. Unify *before* introducing `d`, and gate the unification separately.
- **A byte-identity gate cannot see a rule that is missing from both directions**, and this is no longer hypothetical — it passed cleanly through all of M15 while two fill rules were absent from the simulator entirely ([#18]). It proves *"this change moved nothing"*, which is a different claim from *"the model is right"*. Only a trade list makes the second one.
- **One archetype cannot exercise the fill model.** Both of [#18]'s defects were unreachable from DeadCatBounce **by construction** — its trigger cap makes an unsubmittable entry impossible, and its reconciled window happened to contain no gapped stop exit — so neither was a gap in test coverage that more tests would have closed. Every new entry or exit mechanism is a new part of the fill model with no evidence behind it, and [#38]'s shared engine will inherit whatever is wrong. Reconcile per archetype; do not trust the engine because the first one passed.
- **Documentation must not carry a figure that goes stale.** State the rule; point at where the live number is produced. Reconciliation rates, leg counts, P&L and test counts all move on ordinary PRs, and `CLAUDE.md` is loaded into every session, so a stale number there is a wrong fact asserted with authority.
- **`# pragma: no cover` marks code that is never run, which is exactly where a defect can sit indefinitely.** The empty-log defect sat behind one, and the audit that found it turned up a second of the same shape ([#81]). A pragma is a claim about coverage, not about correctness.
- **A type checker introduced with a strict config and 400 errors gets switched off.** Start permissive on the project's own modules and tighten; do not gate CI on it in the same change that introduces it. See [#56], [#57].
- **Re-measure the Numba `NamedTuple` result before relying on it.** It is a property of the installed Numba, not of the language, and `cache=True` interacts with it. `tools/numba_tuple_probe.py` is the probe.
- **M20 may not move a number.** Every M20 item is behaviour-preserving. Anything that moves a trade log is out of scope and belongs in the milestone that intends it.
- **A prefix of a trade log is not a sample of it.** The `explain.py` defect was justified with "50% of trades", measured over a 200-trade prefix; the whole-window rate is 35.7%. Quote whole-window rates.

______________________________________________________________________

## Milestone notes

One paragraph of reasoning each. Scope and acceptance criteria are in the linked issue.

### The trade-log gate, and the two times it was wrong ([#113])

`CONTRIBUTING.md` § "The trade-log regression gate" is the procedure and `.claude/rules/regression-gate.md` carries the rules. This section is the evidence behind both — it lived in `CLAUDE.md` until plans and findings were separated, and it is here because a finding outlives the milestone that produced it.

**The float64 precision problem was on the read side all along, and was blamed on the write side until #113.** Measured on the 1,664-leg `live_mnq.csv` capture, 18,304 float values across 11 columns:

|               | read default | read `round_trip` |
| ------------- | ------------ | ----------------- |
| write default | 342 moved    | **exact**         |
| write `%.17g` | 576 moved    | **exact**         |

Read the diagonal, not the margins. `float_precision="round_trip"` is what makes the gate correct — with it *either* writer is exact. `%.17g` on its own fixes nothing, and paired with the default parser it makes matters **worse**, because 17-digit text is precisely what a lax parser mis-rounds. `float_precision="high"` is not enough either; it fails the same way. The `%.17g` is kept because it is explicit and costs nothing, **not** because it is load-bearing — the earlier note claiming it was, and citing "4 of 1,664 `r_multiple` values", was measuring the reader and attributing it to the writer.

Until #113 the gate read with a bare `pd.read_csv`, so **a one-ULP difference was invisible to it** — a two-byte textual change in a captured log reported `BYTE-FOR-BYTE IDENTICAL`. `tests/test_trade_log_gate.py` now pins that it cannot regress.

**Every historical claim was re-run through the fixed gate (#113) and all of them hold.** One capture script was run at each commit rather than each commit's own copy, so the harness is a constant and any difference is library code; `prepare`'s signature is unchanged across M9, M15 and M20a, and only its module moved, so one shim covers them all.

| claim               | commits             | gate                           | `sha256`                 |
| ------------------- | ------------------- | ------------------------------ | ------------------------ |
| M9 move             | `6975a56`→`f71baa3` | identical                      | identical                |
| M9 schema           | `f71baa3`→`8b2c5ab` | pre-existing columns identical | differ (3 columns added) |
| M15.1 sign          | `4be9980`→`96be12a` | identical                      | **differ — see below**   |
| M15.4 PullBackAndGo | `cc1be25`→`cb2e2c7` | identical                      | identical                |
| M20a                | `f992c05`→`9caf653` | identical                      | identical                |
| M15.2/3 cancel      | `96be12a`→`cc1be25` | 10 files differ                | differ                   |
| M15.5 fills         | `cb2e2c7`→`0871831` | 14 files differ                | differ                   |
| #113 ruff auto-fix  | `2243779`→`752155c` | identical                      | identical                |

**#113 was gated retroactively (2026-08-19), because it should not have been ungated.** A "Ruff auto-fix" PR reached into the `@njit` loop: `simulate_deadcat`'s MAE/MFE tracking went from `if run_high < high[i]` to `run_high = max(run_high, high[i])`, and `archive.py`'s merge inverted the branch that implements "the newest bar may insert but never overwrite". Both are equivalent on inspection — and inspection is not the gate. All 14 files come back identical on both the gate and `sha256`. **The lesson is where the change was, not what it was:** a lint PR is the last place anyone looks for a simulator change, so read what an auto-fixer touched under `nqbt/sim/` before merging, not after.

The last two *should* differ — force-flat cancellation removes real legs (113,164 → 113,116) and M15.5 changed fill semantics. Both are the fix working, not a regression.

**M15.1 is numerically identical but not textually identical, and that is new information.** `d = ±1` turns `0.0` into `-0.0`, so 6,908 values across `gross_pnl`, `net_pnl`, `r_multiple`, `mae_points` and `mfe_points` flip their sign bit. **Every one of them is zero** — verified, none non-zero — and `-0.0 == 0.0`, so sums, the `pnl == 0` scratch test and every statistic are unaffected. The right phrase for M15.1 is therefore *numerically* identical; only the CSV text moved.

That is also why **`sha256sum` is a cross-check, not the gate**. It is strictly stronger than `assert_frame_equal(check_exact=True)` and will flag a benign signed zero as a difference. Use it to catch the gate itself being broken — it is code, and it has been wrong — but when the two disagree, find out which kind of difference it is before believing either. Verifying the gate can still *fail* is part of using it, and a pandas round-trip is the wrong way to do that: perturbing a value via `read_csv`/`to_csv` trips a *collateral* difference and reports a column you did not touch, which reads like success. **Perturb the CSV text directly**, one field, and check the reported column is the one you edited.

### What CI can gate on a dependency bump ([#161])

The trade-log gate above is the right instrument and it cannot run on a pull request: `data/` and `verification/` are both gitignored, so CI has no bars and no NT8 exports. What CI *does* have is the whole suite twice, JIT on and JIT off — and until #161 every assertion over a simulated number stated a property rather than a value, which is precisely what a dependency bump does not violate. `CONTRIBUTING.md` § "Dependencies are pinned exactly" says each bump runs "the full suite plus both gates"; the gates were a local step nothing enforced, and a dependency pull request touches no file under `nqbt/sim/` that would prompt anyone to run them.

**A bump to numpy, numba, pandas or pyarrow is a `nqbt/sim/` change in effect**, and the three tests #161 adds are the part of the gate that needs no data:

| test                               | what a failure means                                                                            |
| ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| `tests/test_rng_stream_pins.py`    | the `Generator` stream moved, so every null distribution and the M7a arm have to be re-measured |
| `tests/test_numeric_pins.py`       | the numeric pipeline moved — run the real trade-log gate before believing anything else         |
| `tests/test_parquet_round_trip.py` | the cache reader, the writer, or the session labels moved                                       |

Three things about them that are deliberate and read as mistakes otherwise:

- **`test_numeric_pins.py` pins the transcript, not the property**, against `CONTRIBUTING.md` § "Tests". That rule is right for behaviour and wrong here: a stated property cannot see a one-ULP drift, and a one-ULP drift is what a numba bump moves. The simulation compares floats against tick-grid levels, so at a fill boundary one ULP is a different trade, not a rounding difference.
- **Its bars are built from integer arithmetic and never from `numpy.random`.** Every other synthetic fixture in the suite draws from `default_rng`, which would make a stream change and a simulation change indistinguishable — the first thing that test asserts is that its *input* is unchanged, so a failure can be attributed before it is investigated.
- **`tests/fixtures/cached_bars.parquet` is a real cache file kept on purpose.** Every other test writes and reads parquet inside one process under one version, which cannot catch a reader that changed; only a file written by the *previous* version can. The test pins the `created_by` string for that reason. Regenerate it when the cached schema changes, never to make the test pass.

The fixture's bars straddle the 2024-03-10 US DST transition and the 17:00 ET break, and the session labels stored at ingest are re-derived from the index and compared. That is the tzdata check: `tzdata` is pinned like everything else, and it is the one dependency whose bump moves session boundaries rather than arithmetic — so it earns a different check from the other three, and this is it.

**What none of this replaces.** These are canaries, not the gate. The real gate is fourteen files over real bars, and the MNQ 03-24 agreement rate in `docs/nt8-fidelity.md` is still the only thing that says Tier 1 and Tier 2 agree. When a pin here fails, the answer is to run the real gate and find out what moved — not to re-pin.

### ~~M9~~ — the trade-log schema: done

`nqbt/trades.py` is the contract between every producer of a trade log — the jitted simulation today, an importer for real NT8 executions under M11 — so that a statistic computed over one means the same thing computed over the other. It knows nothing about strategies, bars or indicators, and a test enforces that by import analysis rather than by habit.

**One row per leg exit, not per trade.** A four-leg entry that scales out at three targets and trails the runner produces four rows sharing a `trade_id`, which lets `stats` aggregate either way. NT8's "total trades" is the leg count, so `stats.leg_summary` is what a reconciliation compares against.

**`NULLABLE` states which columns a producer may legitimately leave empty, and why each one**, so the nullability is a documented property rather than something discovered by a `NaN` reaching a chart:

- `entry_bar` / `exit_bar` / `bars_held` — positional indices into a specific bar series. A real fill has a timestamp but no bar number until one is matched to it.
- `initial_stop` / `target_price` / `risk_points` / `r_multiple` — need the *planned* levels, and are deliberately absent on imported trades. The only stop levels the Control Center log records are ATM-template defaults dragged to intent seconds later, so a risk computed from them is wrong by an order of magnitude (§11.1).
- `mae_points` / `mfe_points` — need the bars the trade was open across.
- `ambiguous_bar` — a simulator-only concept. A real fill is not ambiguous; it happened.

Everything else is required on every row from every producer.

**`EXIT_REASONS` is what the *simulator* may write, and an imported trade is not restricted to it.** NT8's executions grid names its exits `Stop1..4` and `Exit`, which do not map onto the enum without inventing information, so `validate` requires `exit_reason` to be a string rather than a member of the set. `validate_legs` *does* check the codes, because only the simulator can have written a matrix.

**`direction` is carried per row, not per run**, because a bidirectional archetype takes both sides within one run and a real trading history certainly does. Every P&L and MAE/MFE sign convention downstream reads it rather than assuming the short side the first archetype happened to have. `source` is carried for the same reason: real and simulated trades share one DuckDB table, so without a tag one careless `GROUP BY` averages a backtest into a trading record.

**`validate` is written to short-circuit, and that is a measurement.** It runs once per combination inside a sweep. Every check is a whole-column test that stops at the first failure, and the per-row accounting that makes a good error message is only paid for once there is an error to describe. End to end on a 12-combination sweep it costs **1.3%**; the obvious form — `frame[REQUIRED].isna().sum()` plus `isin` — costs **9.4%**. Integer columns are skipped entirely, since one cannot hold a null, which is a third of the loop's cost. Beware of microbenchmarking it by validating one frame repeatedly: `Series.hasnans` is a cached property, so the second call onwards is free and the result is meaningless.

### ~~M15~~ — direction in the simulator: done ([#13])

Kept because the reasoning generalises, and because one part of it turned out to be wrong in an instructive way.

`simulate_deadcat` was short-only in roughly eight places — stop hit, target fill, P&L, MAE/MFE, entry trigger, entry fill test, ratchet, slippage sign. The design was **one sign multiplier `d = ±1`, not two code paths**, because the bracket machinery carries the fidelity evidence: the ambiguous-bar rule, `IsFillLimitOnTouch`, the ratchet and the force-flat path are what the reconciliation actually validated, and forking gives Tier 1 and Tier 2 two places to drift. That held — the machinery was not forked, and `_sided()` is the single exception, picking which raw OHLC value is adverse or favourable because that is a data selection rather than something a sign multiplication can express.

Because ×(±1.0) is exact in IEEE 754 and `fl(a − b) = −fl(b − a)` always, the gate was **byte-identity of every short-only trade log**, chosen as stronger and cheaper than re-running the reconciliation. **That was right about what it covered and wrong about what that was worth.** It caught nothing because there was nothing to catch, and it is structurally blind to a rule that is *missing from both directions* — which is exactly what [#18] then found, twice. The gate remains correct for a direction-symmetric refactor; it is not a substitute for a reconciliation, and the two answer different questions.

The long path was proven by porting `PullBackAndGo.cs` ([#17]) and reconciling it ([#18]) — long-only `EnterLongStopMarket` with C# ground truth, so a long-side fill bug is found against NT8 rather than blamed on a new strategy. **That decision paid for itself immediately**: both defects [#18] found were in the *shared* bracket code, present since the beginning, and on an original archetype they would have been indistinguishable from the strategy simply being bad. Stop-and-reverse remains out of scope; see "Decisions taken".

### ~~M16~~ — the indicator-parity debt: done ([#19])

Every value is in `docs/nt8-fidelity.md` §M16 with its evidence; this is what the exercise taught, which is the part that generalises.

**The prediction was right, and it was worth making.** M16 said to expect *seeding, not formula*, and that is exactly what ATR turned out to be: an expanding simple average of True Range until the period fills, then Wilder. Pure Wilder from bar 0 — the textbook form — agreed on 89,020 of 89,330 bars, which is the dangerous kind of wrong: it looks correct everywhere except the warm-up, and the recursion never forgets its seed.

**"Do not answer from memory" earned its keep on Keltner.** It was flagged here as the one most likely to be silently wrong, and it was wrong in *both* halves at once — the midline is an SMA of typical price rather than an EMA of close, and the width is the mean high−low range rather than ATR. ATR agreed on **20 bars out of 89,330**. Any implementation written from memory would have been wrong twice, and both mistakes produce a plausible-looking channel.

**One probe answered four issues.** `NqbtIndicatorProbe.cs` exports every candidate series side by side from bar 0, so the questions are settled by reading a table rather than by running an experiment per hypothesis. Exporting `ATR(1)` was the trick worth keeping: NT8 exposes no True Range indicator, but Wilder at period 1 reduces to TR exactly.

**A pin is about method as well as formula.** StdDev's rule is unremarkable — population divisor, expanding window — but reproducing it requires a *two-pass* computation. pandas' `rolling(...).std(ddof=0)` is algebraically identical and drifts by up to 4.2e-07. That is far below a tick and would never show up in a result; it would simply mean the pin was not a pin.

Still true and still unpaid: BB and KC are swept over period *and* multiplier, so the 66 MB → 595 MB lesson applies with an extra factor — **keep boolean gates only**. [#23]'s roll-boundary half is now settled too — see "Decisions taken".

### ~~M17~~ — the archetype protocol: done ([#24])

`sweep.py` used to name `DeadCatParams` in six places, so a second archetype meant forking it. It now names none: `nqbt/archetypes.py` supplies the parameter class, the legal axes, the toggle map, the context spec and the run function, and a new archetype registers rather than forking.

The insight that shaped the rest was that **strategy, resolution and contract are the same feature**: all three add an axis that sits *above* the `Dataset` rather than inside a params class, all three need one `Dataset` per value, and all three need a nullable results column. So it is one mechanism ([#28]), not three wrappers that diverge, landed together before the stale DuckDB re-run ([#71]) so the schema settled once instead of three times. That is why M13 ([#30]) and M14 ([#31]) came before [#28] rather than after it.

**What `sweep_axes` settled, worth not relitigating.** The strategy axis is a **list of grids, not a list of archetype names** — each archetype has its own parameter class, so `ema_period=[9, 21]` is not necessarily a legal axis of the next one, and a single grid re-based onto another archetype would raise or, worse, silently sweep a different field. The contract axis is **carried by `bars` itself** (one frame, or a `{contract: frame}` mapping), because a contract axis *is* which bars; that avoids a mutually-exclusive parameter pair and lets `dispersion.sweep_contracts` hand its frames straight in. Every grid at one axis point **shares a single `Dataset`**, built from the union of their `ContextSpec`s — a dataset each would multiply what the parallel path memmaps to every worker by the number of strategies, and a test pins the call count rather than trusting it. And `combo_id` stays the grid's own index so it means the same parameters at every axis point, which is what makes a cross-resolution comparison a comparison; it deliberately does *not* carry across grids, which is why `strategy` is part of the log key.

`dispersion.sweep_contracts` is now a thin wrapper over it, as its own docstring asked for. All 48 dispersion tests passed unchanged through that refactor, and the whole capture set is byte-for-byte identical.

Three smaller `sweep_axes` decisions, recorded here rather than in the module ([#105]). **Every axis defaults to a single value**, so cost is opt-in one axis at a time — but they compose and the product is a product: three grids over four resolutions over nineteen contracts is 228 datasets, each paying the full `prepare` cost. **`AxisPoint.tier2` is carried, not swept** — a property of the strategy rather than an axis of its own, riding along because it has to reach the results row. And **the axis columns lead the table rather than trailing it**, because they are what the row *is*; a table whose leading column is `combo_id` invites reading two resolutions as one population.

Three things the landed part settled, worth not relitigating:

- **`Grid.dead_axes()` was preserved, not reinvented**, and its gate map now comes from the archetype — so a new archetype inherits the guard instead of getting its own version of the same mistake. A test asserts every gate names a real field of its own params class, because a typo'd gate does not raise, it just stops guarding.
- **`sweepable` reads `dataclasses.fields()`** ([#60]), not `__slots__`. This was folded in rather than deferred because M17 is exactly the change that would have triggered it.
- **`ContextSpec` lives in `context.py`, not beside the registry** — it describes a `Dataset`, and `context.py` must not import from `nqbt.sim`. Grids are keyed by `(kind, period)`, which is the half of [#72] this milestone did for free.

**The results schema ([#29]) settled first**, before [#28] filled it and before the stale-database re-run ([#71]). `strategy`, `resolution`, `contract` and `tier2` exist on both DuckDB tables, nullable, with `batch_id` on `sweeps`; a database written before them gains them by migration and keeps its rows. `stats.Summary` gained `session_close_share` in the same change — measured at **0.0001 on DeadCatBounce over 1-minute continuous MNQ** (one leg in 9,824), which is the baseline the resolution sweep is expected to move sharply. The reasoning for the row granularity is in "Decisions taken".

**How `results.py` stores it**, recorded here rather than in the module ([#105]):

- **The axis columns are migrated explicitly; every other column arrives with the frame carrying it.** `_append_or_create` *widens* the table rather than dropping what it does not recognise ([#201]), so a new statistic, a new parameter and a second parameter class all store in full, and the rows written before the column existed read null. It used to drop them, which was the accepted trade for a statistic — a gap in one column, obvious on inspection — and never right for the four axis columns, because those are *identity* rather than measurement: dropping `resolution` leaves no gap, it relabels the row as some other run, and a 15-minute result then sits in the same column as a 1-minute one with nothing to say so. They stay migrated up front because `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, and so that a query against an untouched old database can group by `contract` before anything is written to it.
- **A type cannot be widened away, so that is where the raise is** ([#201]). A column the frame and the table share keeps the *stored* type and DuckDB casts into it silently, which sends `2.5` into a BIGINT column as `2`. `_append_or_create` round-trips each differing column through both types and raises `ResultsError` naming the columns and the row counts when the value does not come back. Measured rather than ruled: `5.0` into that same BIGINT column loses nothing and inserts.
- **One wide `combos` table costs nothing to store, which is what settled widening against raising.** Six parameter classes give 91 columns of mostly-null rows; over 20,000 rows each that is 7,876,608 bytes in one file against 7,938,048 across the six-database split, because DuckDB compresses a constant-null column away — and a cross-archetype query is one scan rather than six `ATTACH`es. `ALTER TABLE ADD COLUMN` is metadata: 40 columns onto a 500,000-row table took 0.216 s and added zero bytes. Synthetic frames, so read these as orders of magnitude rather than as a benchmark.
- **An existing table is written by name, not by position.** Otherwise adding a statistic would make `INSERT ... SELECT *` shift every column one place right and store numbers under the wrong headings — which reads as a result rather than as an error. It is also why the stale-database re-run ([#71]) is scheduled after the axis columns land rather than before.
- **`_tag_axes` pins dtypes, and that is the point rather than decoration.** DuckDB infers a new table's column types from the frame it is created from, and an all-null `object` column infers as **INTEGER** — so a first sweep over the spliced series, where `contract` is null by definition, would create `combos.contract` as an integer column no contract name could ever be inserted into. A caller may also supply the tags per row (`sweep_axes` does), and then the frame's own values win; overwriting them with a scalar `None` is how a multi-axis run would lose exactly the tags it exists to produce.
- **A null does not mean the same thing in every column** — `results.NULL_MEANS` states it per column. `contract` is the odd one out and deliberately so: null is a real, expected value there, naming the spliced series. Everywhere else it means the row predates the column.
- **The axis arguments to `save_sweep` default to `None` rather than being inferred from `bars`.** Resolution in particular is guessable from the index spacing and that guess would be right nearly always — which is the problem: a tag that is usually right is worse than one that is absent, because nothing downstream can tell the two apart.
- **`next_batch_id` locks nothing.** Fine for a single-user research tool and not for a shared one: two runs started in the same second would share a batch. Recorded rather than defended.

**`Summary.session_close_share` is reported rather than buried in the trade log**, because a strategy taking 40% of its exits at the session close **is not the strategy its rules describe** — the profit factor of such a run is largely a measurement of the flatten time, and no other aggregate says so. Flat-before-the-close is a prop-account rule, so this is never a bug to be fixed; it is a property of the archetype at that bar size. It is computed over **legs**, matching `ambiguous_share`'s denominator, since a leg exit is an exit. An imported real-fill log carries an `exit_reason` NT8 wrote (`Stop1..4`, `Exit`), none of which is this label, so it reports 0.0 rather than a wrong number. `ambiguous_share` is its counterpart: the one statistic saying how much of a result rests on an assumption the bar data cannot settle.

The `tier2` registry field ([#25]) is not bookkeeping: per the standing constraint, "validated against NT8" stops being a project-wide fact once originals exist, and M18 is what made it one — `EmaCrossover` is `TIER1_ONLY` beside two `RECONCILED` ports. A results table ranking a reconciled archetype against an unreconciled one compares a measurement against an assumption, and carrying the status as a column is what stops the ranking hiding that. The shared bracket engine was extracted **during** M18 ([#38]); see below for what the second shape moved.

**What each `Archetype` field is for**, recorded here rather than in the module ([#105]):

- **`legs` is registered beside `run`, not derived from it.** It is the *earlier* of the two — `run` is this plus a DataFrame — and a sweep summarises the matrix directly, which is where [#33]'s speedup comes from. It is required, because an archetype registered with only `run` would silently be the slow one in a sweep and the reason to notice would be a wall clock.
- **`signal` is registered because M7a needs the *real* signal** to match its draws against before handing a substitute back to `run`. Without it the null would carry a second definition of the entry rule, which is exactly what the registry exists to prevent.
- **`not_sweepable` is listed, not inferred.** The rule today happens to be "the tuple-valued fields", but deriving it from the value's type would silently start sweeping a new tuple field, or stop sweeping a scalar that gained a `None` default — and a disappearing axis is [#60]'s failure mode, because it multiplies nothing rather than raising.
- **`run` is typed `Callable[..., pd.DataFrame]`, deliberately.** Each archetype's `run` accepts only *its own* parameter class, which needs a generic `Archetype[P]` rather than a plain callable type; that belongs with the typing work ([#55]). The runtime check that matters — base against `params_cls` — is enforced in `Grid.__post_init__`.
- **`Archetype` is a frozen dataclass, not a base class.** There is no behaviour to inherit, only facts and function references, and the standing rubric's warning against a class hierarchy for one archetype applies just as well to three.
- **`register` refuses a duplicate name** because `name` is written into the results table, so two archetypes sharing one would merge into a single DuckDB row group and read as one strategy measured twice. `for_params` raises on ambiguity for the same reason: guessing would attribute a whole sweep to the wrong strategy.
- **`DEFAULT` is DeadCatBounce** because it is the archetype every stored result, captured trade log and reconciliation was produced with. Changing it would silently reinterpret them.

**A `ContextSpec` is built from what the grid will actually try.** VWAP, the time-of-day labels and the ATR grids are each requested only when some combination switches them on — they are the series no combination reads by accident, so leaving them out when unused is free. The MA periods cannot be treated that way, because `dead_axes` already refuses the case where a swept period's toggle is off everywhere, so every surviving case is live. `crossover_context` additionally sets `needs_ma_values`, since comparing two averages to *each other* is something no close-versus-average boolean gate can answer; that is the 8× memory the grids otherwise avoid, requested by the one archetype that needs it rather than switched on globally. `CROSSOVER_GATES` guards the ATR fields but cannot guard `swing_lookback`: `dead_axes` asks whether a toggle is true *somewhere*, which cannot express "dead when this one is never false".

### ~~M18~~ — EMA crossover: done ([#34])

The first original archetype, chosen to prove M15 and M17 because it is the cheapest thing that exercises both: bidirectional, and it exits on a signal rather than a bracket level. Everything below is the record of what it actually cost and what it actually read; the rules themselves are in `docs/nt8-fidelity.md` § M18, marked as having no evidence behind them yet.

**It reads as a known negative, which is the result it was built to produce.** On costed MNQ from 2024 (914,700 bars, EMA(9)/EMA(21), commission $1.24, 1 tick slippage) it returns a profit factor of 0.866 on 41,784 trades. Against 200 matched random-entry draws (M7a) it sits at the **49th percentile on profit factor**, the 47th on expectancy and the **1st on win rate** — indistinguishable from random on two of the three and *worse* than random on the third. The direction split is 83,532 long legs against 83,604 short.

**That reading is also the lookahead check.** The stated worry was that a crossover is unusually easy to compute one bar early, and that the symptom would be an exciting profit factor rather than an exception. A rule that read the fill bar's own cross would have come back spectacularly profitable; this one comes back at the null's median. There is a direct test as well — `crossover_signal` recomputed over a prefix must equal the prefix of the full computation — but the control arm is the one that would have caught a defect the direct test was not shaped to see.

**The trade-count explosion is real but a third of the guess.** One combination:

|                 | per combination | legs    |
| --------------- | --------------- | ------- |
| `EmaCrossover`  | 49.0 ms         | 167,136 |
| `DeadCatBounce` | 3.3 ms          | 14,556  |

**~11.5× the legs and ~15× the time**, against the "tens of thousands against ~1,400" this section predicted, which was closer to 30×. Of the 49 ms, 4.9 ms is the signal (two EMA comparisons plus the cross window, computed per combination because `cross_lookback` is an axis) and 11.4 ms is `summarise_legs`. `allocate_output` reserves **27 MB per worker** at these settings — the `n_signals × n_legs` bound stays correct and stops being free, so a permissive grid should have its signal count read off before it is launched, not after.

**The exit mix is not what was predicted.** 51.3% signal, 25.2% stop, 22.4% target, **1.0% session close**. The forced-exit share was expected to be a large fraction; see the M10.4 note above for why the reasoning was sound and the premise was not.

**Three defaults were wrong and each is now a swept field rather than a constant.** NT8's `CrossAbove(a, b, n)` semantics rather than the naive one-bar form ([#35]); market-on-next-open entry ([#36]), a third mechanism with no trigger price and no "no touch, no fill"; and an ATR multiple for the stop ([#37]), which is what made M16 a hard prerequisite rather than a convenience. The swing-extreme stop survives as the alternative mode, sweepable via `use_atr_stop`.

**One thing the loop needed that was not on the list.** An entry whose protective stop would land at or through its own fill is skipped — the existing stop-entry submittability rule applied to the protective stop. It is unreachable in both ports, because their stop is placed against a trigger the fill is defined relative to; here the fill is wherever the next bar opens, so a gap can put the swing reference on the wrong side of it. **Second time an archetype has reached a rule the first two could not**, after M15.5's two fill-semantics defects. One archetype cannot exercise the fill model, and it turns out two cannot either.

**Flat between trades, not stop-and-reverse, is a real difference and not a limitation worked around.** The flip closes the position and opens the new one as two fills at the same open price, each paying its own slippage and commission. Economically a reversal; in the log, two trades. Any comparison against published crossover results has to say so. It is also what `pending_exit` exists for: without allowing the entry to be scheduled on the bar the exit is scheduled, a one-bar lookback would only ever go long, because crosses alternate.

**The bracket engine came out during M18, per [#38].** `nqbt/sim/bracket.py` holds the stop, the targets, the ambiguity policy, the limit-fill rule and the leg writer; `simulate_deadcat` keeps what is specific to a stop-market entry with a ratcheting stop. The second real shape is what showed the split falls between the **entry** half and the **bracket** half rather than anywhere else — crossover replaces the whole entry mechanism and reuses the bracket half untouched. All 14 captured DeadCatBounce trade logs are byte-for-byte identical across the extraction and across the whole milestone.

**What M19 inherits.** `EXIT_SIGNAL` is now exercised rather than reserved. The bracket engine is a set of `@njit` device functions any loop can call, so a squeeze breakout needs to write only its two-sided OCO entry. And the per-combination cost of a high-leg archetype is now known rather than assumed, which is what the numpy summary path ([#33]) was moved ahead of M18 to buy.

### M22 — InsideBar, the third C#-backed port ([#126])

The archetype earns its place on what it reaches rather than on what it might make: three parts of the fill model no other archetype touches — `IsFillLimitOnTouch = true`, a bracket anchored to the fill and the signal bar at once, and a no-entry window before the session close. Each rule, the two the port inferred wrongly, and the wall-clock trap that still has to be fixed in the NinjaScript before that one rule can be reconciled: [nt8-fidelity.md](nt8-fidelity.md) §M22 and "A no-entry window before the session close".

**Its trade list paid for itself twice over.** It settled the `IsFillLimitOnTouch = true` branch, corrected both `OnExecutionUpdate` anchors, showed `ExitOnSessionCloseSeconds` does not move a backtest's flatten, caught a `PositionAccount` guard that made NT8 reverse, and turned up out-of-session stray bars sitting in the array every archetype indexes.

**Read its results with the geometry in mind.** A target 1x ATR(3) from the fill against a stop 10x ATR(3) beyond the signal bar is a high-win-rate, rare-large-loss shape: a win rate near the top of the range and R multiples just above zero are what it looks like working, not what it looks like broken, and neither number compares to another archetype's. Judge it on net P&L at realistic costs — where a 1x ATR(3) target on a quiet bar can be smaller than the round trip.

### M23 — InsideBarTrailing, split lots and a trailing stop ([#127])

The same entry as M22 and a materially harder exit model: the position splits across two entry orders with different exit engines, the runner's stop trails a high-water mark rather than ratcheting off a lagged bar, and a trend violation flattens whatever is left. Each rule and which of them has no evidence: [nt8-fidelity.md](nt8-fidelity.md) §M23.

**The entry is shared, not forked.** `InsideBarTrailingParams` subclasses `InsideBarParams` and both archetypes call `insidebar_signal`, because the two NinjaScripts differ in defaults rather than in rules. That is what makes `sweepable` reading `dataclasses.fields()` rather than `__slots__` load-bearing rather than merely correct — see "Moving-average axes" — and the difference the defaults make is not cosmetic: ten times the breakout buffer is a different strategy.

**Decision: the split-lot model sits beside `bracket.py` rather than generalising it.** The engine takes one stop for the whole position and per-leg targets, which is the wrong shape for two independent brackets. Two ways out were available and only one was taken:

- *Generalise the engine* — make the stop per-leg, so `resolve_brackets` resolves each leg against its own. That is a real restructure of the fidelity-critical code, on the evidence of a single archetype, and it would put "the stop takes the whole position" — a rule three reconciliations rest on — behind a rewrite.
- *Resolve each lot through the engine as it stands*, which is what shipped. `insidebartrailing.resolve_lots` calls `resolve_brackets` once per lot per bar with every other leg masked out, so each bracket meets the one implementation of every fill rule and `bracket.py` is not touched at all. Under `StopTargetHandling.PerEntryExecution` that is also the more literal reading of what NT8 does.

The rule this follows is **extract the abstraction from two examples, not from one**. If a second split-lot archetype arrives and wants the same thing, the shape to extract will be visible in two places instead of guessed at from one — and the trade-log gate stayed byte-for-byte identical across all fourteen files precisely because the shared engine was left alone.

**`EXIT_SIGNAL` now has two consumers, and this is the first with C# behind it.** EmaCrossover reserved it with no NinjaScript to be checked against; `InsideBarTrailing.cs` has a real rule-driven exit, so the semantics M18 wrote down — a managed market exit filling at the next bar's open, taking precedence over the brackets — finally have something to be reconciled against. The structural test that pinned single use now pins the set, both halves.

**Its trade list overturned three of the four exit rules the port inferred**, and the port was written to be checked rather than trusted: the two questions it turned on were on [#67] *before* the code existed. What moved, in the order the corrections landed — the `-200` gate governing the trend violation and not just the dead branch under it, `OnPositionUpdate`'s one-bar offset, the exit being part of the triggering fill, and a trail advancing within its entry bar but not within any later one — is in [nt8-fidelity.md](nt8-fidelity.md), "Reconciliation result — InsideBarTrailing". Agreement went 80.18% → 99.80% across those four.

**The generalisation worth keeping: a guard clause belongs to the method, not to the branch below it.** Reading `if (pnl > -200) return;` as part of the max-loss check under it is what produced 340 spurious signal exits against NT8's 12 — a plain misreading of C# scope, made easy by the ticket describing the two together, and invisible to every test written from the same misreading. Only the trade list caught it.

### ATR-multiple brackets and the dollar floor ([#76])

Two archetypes size a bracket off ATR for opposite reasons — EmaCrossover because a crossover has no structural swing to anchor to ([#37]), the two InsideBar ports because their NinjaScript does — so the sizing is one `@njit` device function in `bracket.py` rather than a multiplication written out three times. `atr_bracket_distance` is what every ATR-derived stop distance goes through, and the ports pass `NO_BRACKET_FLOOR` because their C# has no floor to reproduce.

**Why the floor is in dollars and not in points.** A quiet regime can size an ATR bracket smaller than the round trip costs to trade, which is a bracket that cannot win. The floor that fixes it is a *money* quantity: NQ and MNQ share a tick size and differ 10× in tick value, so a floor written in points is $300 of risk on one root and $30 on the other, and a sweep across both roots would be comparing two different rules. `min_bracket_dollars` is per contract — which is the unit commission is quoted in — and `Instrument.dollars_to_points` converts it once per run, so the axis means the same thing on every instrument.

**It applies to the ATR stop only, not to the swing stop.** An ATR stop *is* a distance from the fill, so widening it is the same kind of quantity; a swing stop is a structural level, and pushing it away from the structure would stop it being the rule it is. `dead_axes` therefore gates the axis on `use_atr_stop`, alongside the period and the multiple.

**What it does to R, which is the consequence [#34] recorded.** EmaCrossover's R was already ATR-scaled rather than structure-scaled, so its numbers do not compare to DeadCatBounce's at the same values. The floor adds a second break: on every combination where it binds, R is neither — it is dollar-scaled, and identical across every ATR multiple in the sweep, because the multiple stopped setting the distance. **A grid swept over `atr_stop_multiple` with a floor high enough to bind collapses that axis without emptying it**, which `dead_axes` cannot see because whether the floor binds is a property of the bars. Read the realised `risk_points` spread before attributing anything to the multiple.

### M19 — squeeze breakout ([#51])

Queued rather than scheduled; the expensive archetype. "Squeeze" means at least three things, and fixing the definition is the first task: TTM-style (Bollinger inside Keltner — the full M16 debt), bandwidth (`(upper − lower) / mid` below a trailing percentile — Bollinger only), or structural (inside bars — no new indicators at all). **Recommend the bandwidth form first:** one indicator rather than three, it drops the Keltner parity question flagged above as most likely to be silently wrong, and it is the same quantity M10.1's regime classifier wants anyway, so the two share it instead of each inventing one. **`InsideBar.cs` is ported ahead of either** (M22 below) — it is the same compression-then-break idea, needs no new indicator work beyond ATR, and is the only version of this strategy with C# ground truth. Its trade list also settled two questions M19 would otherwise inherit: the `IsFillLimitOnTouch = true` branch, and what `[0]` means inside `OnExecutionUpdate`. The real structural cost is a two-sided OCO entry model the loop lacks; the order-lifetime research above resolves that resubmission is exactly equivalent for Tier 1. Traps: lookahead (bands must come from *completed* bars — this is the second-easiest place in the project to manufacture a fictional edge), a high ambiguous-bar rate, and results that cluster by volatility regime so the aggregate PF averages two populations.

### M26 — the elastic band, the first mean-reversion archetype ([#167])

Price mostly stays inside a band; when it closes far enough outside one, take the other side and target the middle. [#168] is the design and the indicator work, [#169] the Python, [#170] the port — and [#170] happens only if the Python clears the promotion criteria under "Decisions taken", not because the Python exists.

**Why build it, when the last four archetypes were continuation rules that did not work.** DeadCatBounce, PullBackAndGo and both InsideBar ports buy strength or sell weakness, and EmaCrossover follows a regime; every result the project holds is about one family. Mean reversion is the first genuinely different hypothesis, and the machinery already leans towards it — `regime.py`'s consolidating label exists to name the state this archetype wants and every other archetype wants to avoid, so it can be gated on from the first run rather than after a rewrite. It also inverts the bracket geometry, target inside the range and stop outside it, which is a shape nothing in `bracket.py` has been exercised on.

#### The band is Bollinger, and the two alternatives are rejected for different reasons

**Decided: `nt8_sma` ± k · `nt8_stddev` on close**, which is the TradingView listing on [#167] line for line. It is the cheapest correct option and the best-evidenced: both halves were read out of NinjaTrader by `NqbtIndicatorProbe.cs` and agree with `indicators.py` on every bar of the probe window — [nt8-fidelity.md](nt8-fidelity.md) §M16 holds the count. NT8 exposes `Bollinger(numStdDev, period)` natively, so the eventual port has no indicator to hand-roll and no seeding question to get wrong.

**Keltner is rejected even though it is already implemented.** Its width is `offset ×` the mean high−low range and *not* ATR — it agreed with `ATR(20)` on 20 bars out of 89,330 — so a band built on it is not the band anybody reading the result would picture. The cost of that is not fidelity, which is pinned either way; it is that a promising number could not be explained to anyone, ourselves included, six months later.

**VWAP ± k·σ is rejected for now and is the obvious second form.** Three costs, in order of size. It has **no pin**: `session_vwap` is reconciled, a standard-deviation band around it is not, so it needs `NqbtIndicatorProbe.cs` extended and re-run — NinjaTrader time, the scarce resource, spent before knowing whether the idea works at all. Its band width **shrinks monotonically through a session** as volume accumulates, so a fixed k is a different extremity threshold at 09:00 than at 15:00, and that confound lands on top of the session-phase artefact [#43] already records. And the anchor resets at 18:00 ET, so the first bars of every session have a band that is not yet a band. If the Bollinger form shows anything, this is the variant worth the probe; if it shows nothing, the probe was not worth booking.

#### The reduction: one dimensionless series per period, and k for free

The entry test "close is at least k standard deviations from the basis" does not need the bands as objects. `indicators.band_stretch` is `(close − basis) / stddev`, which **depends only on the period**, so a grid holds one float array per period and *every* multiple in a sweep reads the same array. **`num_std` is therefore a free axis** — no memory, no precompute, nothing for `dead_axes` to gate — which is the opposite of how `regime_lookback` or `higher_timeframe_period` behave, and is worth knowing before [#169] designs the grid. It is also what makes the entry threshold and the stop threshold different multiples at no cost, which is what the geometry below needs.

**Measured, because the two forms are not obviously identical.** `stretch >= k` and `close >= upper` are the same test algebraically and floating point does not have to agree. Over 200,000 synthetic bars at periods 10/20/50 and k of 1/2/3 they disagree on **exactly one bar in every configuration: bar 0**, where `nt8_stddev` is 0 and the bands collapse onto the close. Rounding never separated them anywhere else. `tests/test_indicators.py::test_band_stretch_crosses_a_multiple_exactly_where_the_bollinger_band_does` pins it, including that bar 0 is the only flat window, so a silently widening exclusion fails the test. `bars_required_to_trade` excludes bar 0 regardless.

#### The thesis has two axes, and [#168] added the primitive each one needed

[#167] says the reversion gets more likely the **further** and the **longer** price sits outside the band. Those are two separate quantities and both are now measurable:

| half of the thesis | quantity                                                               | added by |
| ------------------ | ---------------------------------------------------------------------- | -------- |
| further            | `indicators.band_stretch` — signed extension in standard deviations    | [#168]   |
| longer             | `conditions.consecutive_true` — unbroken run length ending at each bar | [#168]   |

`consecutive_true` is the other axis from `count_true`, which counts conditions on one bar where this counts bars for one condition; the confluence pattern had no way to say "for how long". Neither is an indicator in the fidelity sense — one is a division of two pinned series, the other is arithmetic on a boolean — so **nothing in this archetype needs a new NT8 pin**, which is the main reason the Bollinger form was chosen.

Both are entry *gates*, and both are worth carrying into the trade log as context as well, because "deeper extensions revert more often" is a claim the review side ([#47]) can test directly and an aggregate profit factor cannot.

#### ATR is for the bracket, not for the signal — [#167]'s open question

**Not in the entry rule.** ATR and a standard deviation over the same window are two measures of the same per-bar movement, and the entry is already normalised by one of them. A second would add an axis that mostly duplicates `band_period` while making the rule harder to state.

**Yes in the stop, and it is not optional there.** Sizing off σ alone means a quiet window gives a near target *and* a near stop, which is the exact failure `min_bracket_dollars` exists to prevent — and mean reversion is the archetype most exposed to it, because it fires precisely when dispersion is low. `atr_bracket_distance` with the dollar floor is already the answer for a strategy with no structural swing to anchor to (§ "ATR-multiple brackets and the dollar floor") and it applies unchanged. Sweep it against a band-relative stop rather than choosing by argument.

#### The geometry inverts, and that changes what R means for the third time

- **Entry**: market on the next open, which is EmaCrossover's mechanism and the one with no fill-rule risk attached. A limit at the band is the more natural execution and is the second form to try — it rests, so it dies after one bar and has to trade *through* to fill, both already implemented and reconciled.
- **Stop**: outside the band. Either `atr_bracket_distance` or `basis ∓ stop_std · σ`.
- **Target**: the **basis** — a level, not an R multiple. Legs scale out at fractions of the way back to it, so `legs.target[leg]` is `fill + d · (basis − fill) · fraction[leg]` rather than an R multiple of risk. `bracket.py` needs nothing new for this: the archetype has always written the target prices and the engine has always just resolved them.
- **R is therefore neither structure-scaled nor volatility-scaled.** With a σ stop and a basis target it is `entry_std / stop_std` by construction, identical on every combination sharing that ratio; with an ATR stop it is the ratio of two different volatility measures. **Elastic band results do not compare to any other archetype's at the same R**, which is the third distinct meaning R has taken — [nt8-fidelity.md](nt8-fidelity.md) §M18's last paragraph is the second.

#### Three exit schemes, and they are three grids rather than three archetypes

The entry rule is one hypothesis; **what to do once filled is a second one, and it is not settled by the first**. Three coherent schemes are worth sweeping, and `sweep_axes` already takes a *list of grids* as its strategy axis — so they are three grids over one `ElasticBandParams`, not three archetypes and certainly not a forked sweep. `combo_id` means the same parameters within a grid and nothing across grids, which is exactly the distinction these three need.

**Evidence classes, because they are not equal.** The project's own reconciled machinery comes first, `Trading-Docs` second as framing and as numeric definitions we lack, and the outside reading below **last** — it is a source of hypotheses for the sweep, never an input to it. It is recorded because two of its findings are specific enough to be wrong in a useful way.

##### A — Band Rotation: levels, not multiples

- **Target ladder on chart levels.** TP1 is the basis; TP2 is the *opposite* band. This is the discretionary rotation trade written out — the `Trading-Docs` target sequence is POC then the far value-area edge, recorded there with the explicit caveat that the rotation is the whole trade rather than a launchpad — and it is where the practitioner literature lands too.
- **Stop beyond the excursion, plus a cushion.** The adverse extreme of the bars that were outside the band, offset by the usual ticks — never *at* the level, because price sitting on a reference level is expected to get tested. The elastic band's analogue of DeadCatBounce's swing stop, and the only one of the three whose stop is structural rather than a number.
- **A signal exit on invalidation**: price closing back outside the band beyond the excursion extreme means the range broke and held, which is `Trading-Docs`' definition of a failed trade — the conditions changed while you were in it, rather than you picking the wrong side.
- **Why it earns a slot**: the fewest fitted numbers of the three, and every level is derived from the chart rather than optimised. **Its weakness is the cost floor**: a shallow excursion gives a stop so close that the round trip dominates, and a deep one gives the fat tail.

##### B — Volatility Bracket: the existing device, applied to a new entry

- **Stop is `atr_bracket_distance` off the fill**, with `min_bracket_dollars` underneath it. Nothing new: the same `@njit` device EmaCrossover and both InsideBar ports use, floor included.
- **Targets are the existing four-leg R ladder**, capped at the basis — a target beyond the mean is not a mean-reversion target.
- **Why it earns a slot**: it costs no new bracket code, it removes the absolute-price parameter that `Trading-Docs` flags as DeadCatBounce's overfitting fingerprint, and it is **the only scheme whose results are directly comparable with EmaCrossover's**, because the risk denominator is the same quantity. The outside reading lands in the same place from a different direction, recommending a stop roughly half to one-and-a-half ATR beyond the band that triggered the entry.
- **Its weakness is that it is the least like the strategy being tested** — an ATR distance has nothing to do with the band, so a stop can sit inside the range the trade is betting on.

##### C — Time and Mean: no strategy stop at all

- **One target, the basis, for the whole position.** No ladder.
- **No price stop except a catastrophe limit** — `max_risk_ticks`, which is a prop-account rule rather than a strategy rule.
- **A time stop in bars**, on top of the session flatten every archetype already has.
- **Why it earns a slot, and it is the most interesting of the three.** The strongest outside finding for mean reversion is that a stop *hurts*: on a long SPY mean-reversion system over 2000–2026, adding a 5% stop to identical entries took the annual return from 8.22% to 1.05%, took the worst drawdown from −18.63% to −41.78%, and took the win rate from 66.71% to 49.05%. The mechanism is not mysterious — the stop realises exactly the adverse excursions the strategy exists to hold through — and it is the one hypothesis `nqbt` has never tested, because every archetype so far has been bracketed by construction.
- **The translation is not direct, and that is the point.** That result is a multi-day equity system with no session constraint. Here the position **must** be flat before the close, so a hold is bounded whether or not a stop exists: the session already plays the role "no stop" played there. C therefore tests the sharp version of the question — *does an explicit price stop add anything over the clock?* — which is answerable and which the SPY figure is not.
- The bar count is a real axis rather than a constant: the outside rules of thumb are "if it has not reverted in about fifteen bars it is a trend, leave", and the `Trading-Docs` claim that a failed break resolves within about thirty minutes. Both are specific enough to test and neither is evidence.

##### What the three have in common, and the two predictions worth writing down first

**Stop and target are not independent knobs.** Leung and Li's optimal double-stopping solution for a mean-reverting price with transaction costs proves that **a higher stop-loss level always implies a lower optimal take-profit level** — the two co-move, and sweeping them as independent axes will find a downward-sloping ridge rather than a best corner. This is the analytic form of the same point `Trading-Docs` makes about R:R and win rate not being independent knobs, and it predicts the shape of the results surface before the sweep runs. Read the ridge; do not report the corner.

**The entry has a ceiling as well as a floor.** The same result characterises the optimal entry region as a *bounded* interval — it is optimal to wait when price is too far as well as when it is too near — and the practitioner literature reaches it from the other end, observing that the catastrophic mean-reversion losses are almost all trades taken while a trend was accelerating. Both say the naive reading of [#167], *further is always better*, is wrong beyond some point. **`max_entry_std` is therefore an axis in all three grids**, and a design change the exit research produced rather than the entry research.

**A time stop needs an exit reason and should reuse `EXIT_SIGNAL` rather than add one.** It is a strategy-decided market order at the next open, which is what that code already means, and a grid only ever enables one signal exit at a time so the scheme identifies the cause. Adding `EXIT_TIME` would move `trades.py` and therefore every stored log's schema, for a distinction the grid already carries. **If two signal exits are ever enabled together the log becomes ambiguous** — that is the cost of this choice, and it is the thing to check before enabling both.

**Build B and C first.** Between them they bracket the question that matters — whether a price stop helps at all — and neither needs new bracket code beyond a level target and a bar counter. A is third: its structural stop is a new device, and its stop distance is the least controlled of the three.

##### Where the outside figures came from

Named so they can be checked, and so nothing here is quoted as ours. **None of it is evidence about NQ**, and the only claim below that carries a proof rather than a backtest is the first.

- Leung and Li, *Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit* ([arXiv:1411.5062](https://arxiv.org/abs/1411.5062)) — the analytic double-stopping result: a higher stop-loss level always implies a lower optimal take-profit level, and the optimal entry region is a bounded interval. Both predictions above are this paper's.
- [setup4alpha](https://setup4alpha.substack.com/p/stop-loss-mean-reversion-backtest) — the SPY figures. **One backtest, one instrument, daily bars, long only, no session constraint**, and a 5% stop is nothing like a bracket on 1-minute MNQ. It is quoted for the mechanism, not the numbers.
- The band-exit conventions — middle band as first target, opposite band as second, a stop half to one-and-a-half ATR beyond the triggering band, and a bar-count time stop — are practitioner consensus rather than a result, and are consistent across [LuxAlgo](https://www.luxalgo.com/blog/mean-reversion-playbook-fade-scale-exit/), [Babypips](https://www.babypips.com/trading/system-rules-short-term-bollinger-reversion-strategy) and [QuantifiedStrategies](https://www.quantifiedstrategies.com/mean-reversion-trading-strategy/).
- Mesfin, *Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures* ([arXiv:2605.04004](https://arxiv.org/abs/2605.04004)) — **the closest thing to a matched null that exists**: fourteen signal families on 5-minute MNQ over 947 days, none clearing a two-point friction assumption, with gross edge of roughly 0.07 to 1.50 points per trade. It is momentum rather than mean reversion, so it does not test this archetype — but it is the scale of edge to expect on this instrument, and it says the friction floor is the binding constraint, which is what this project already found.

#### Expressibility checklist, run before building

| question                                | answer                                                    |
| --------------------------------------- | --------------------------------------------------------- |
| How long must an entry order rest?      | None on market-on-next-open; one bar on the limit form    |
| Does it need a true OCO pair?           | No — the breached side picks the direction, one at a time |
| Reverse directly from long to short?    | No — flat between trades, as EmaCrossover is              |
| Does it hold through the session close? | **No, and this binds harder here than anywhere**          |
| More than 4 entries per direction?      | No                                                        |
| An indicator NT8 computes differently?  | SMA and StdDev, both already pinned                       |

**The session-close row is the one to take seriously.** "Hold until price returns to the basis" is an unbounded hold, and the basis is moving while you wait. EmaCrossover took **1.0%** of its exits from the clock and the prediction that it would take many more was wrong — the mechanism there was that crosses are frequent, and that mechanism does not transfer, because nothing bounds a reversion. Expect `session_close_share` to be much higher, and read it before reading anything else: a high share means the archetype being measured is not the archetype the rules describe. Fixing it is then a design choice rather than a bug — a maximum hold in bars, a time stop, or accepting the clock as the third exit.

#### Traps, in the order they are likely to bite

- **Both σ and ATR step at every roll seam.** Back-adjustment cancels the contract basis exactly at the seam, so the jump a seam carries is the price move over whatever break it spans — and a standard-deviation window spanning that bar inflates exactly as True Range does ([nt8-fidelity.md](nt8-fidelity.md), "True Range at a roll boundary"). An archetype that fires on extension will therefore fire around every roll for a reason that is not a market event, and it will fade a move that never happened. **Judge it per contract** (`dispersion.py`, [#31]) before believing any continuous-series number.
- **The band contains the bar being tested, and that damps the signal.** A large move widens σ and drags the basis towards itself, reducing its own measured stretch. This is not lookahead — every input is a completed bar at or before *i* — but it is not neutral either, and the alternative is a band from bars up to *i−1* tested against `close[i]`, which is the `[1]` index in NinjaScript. Make it a toggle and measure it; do not assume either way.
- **Fading extension on an index future is structurally short-gamma.** Many small wins and rare large losses, which is the shape that flatters a profit factor over a short window and hides in an aggregate. The archetype will look best in exactly the sample where no trend happened. Walk-forward ([#50]) and the loss tail matter more here than anywhere; the aggregate profit factor matters less.
- **The band is a multi-parameter family and the temptation to search it is large.** `band_period × entry_std × stop_std × target fraction` is a large grid before any of the shared context filters are switched on, and the best cell of it is the expected output of noise. Test a combination chosen for a reason, and quote the random-entry arm ([#32]) beside any number — which for a bidirectional archetype means overriding the signal and *not* the side, exactly as EmaCrossover does.
- **`ambiguous_share` should fall rather than rise, and that is a prediction.** A near target with a far stop puts both inside one bar less often than the reverse does. Read it rather than assuming it; the mechanism is what the next decision gets made from.

#### What [#169] built, and the first measurement against the null

`nqbt/bands.py` holds the grid, keyed by period alone: basis, standard deviation and stretch, one row each. `ElasticBandParams` carries all three exit schemes as parameters, `nqbt/sim/elasticband.py` is the entry half, and the registry entry is `TIER1_ONLY`. `sweep_axes` takes the three schemes as three grids, which is what the strategy axis is for.

**The band multiple really is free, and the archetype builds no moving-average grid at all** — the first one that does not, because the basis is the band's own.

**Two things `dead_axes` cannot see here.** The stop and target axes are inert at every `stop_mode` and `target_mode` but one, and it only knows how to compare a toggle against a single off value, so sweeping `atr_stop_multiple` under `STOP_EXCURSION` runs identical combinations silently. Same shape as `volume_rolling_bars`, recorded in `.claude/rules/sweep-and-context.md` rather than worked around.

**The invalidation exit and the time stop are guarded against each other rather than merely documented.** Both write `EXIT_SIGNAL`, so `__post_init__` refuses a combination with both on — a log carrying both cannot say which fired, and that was the cost this design accepted when it declined to add an exit code.

##### The result: the entry beats the null on one scheme, and is still not profitable

Measured on **four MNQ front-month contracts — 03-24, 09-24, 03-25 and 09-25 — per contract rather than spliced**, because both σ and ATR step at every roll seam and this archetype fires on extension. One parameter set per scheme, not a sweep. Costs are the real ones: $1.50 round trip per contract and one tick of slippage. 200 null iterations, so the smallest reachable *p* is about 0.005.

| scheme           | profit factor     | expectancy    | win rate          |
| ---------------- | ----------------- | ------------- | ----------------- |
| A, rotation      | same on 4/4       | same on 4/4   | same on 4/4       |
| B, ATR bracket   | same on 4/4       | same on 4/4   | **better on 3/4** |
| C, time and mean | **better on 4/4** | better on 3/4 | **worse on 4/4**  |

**Read the consistency across contracts, not the individual p-values.** Thirty-six comparisons were run; a single one clearing 0.05 is the expected output of that many. Four contracts agreeing on the sign is the part that is hard to get by chance, and it is what the table reports.

**C is the finding, and its shape is the opposite of the usual mean-reversion story.** Its profit factor beats the matched null on every contract while its win rate is *worse* than the null on every contract. So the entry is not finding trades that win more often — it is finding trades whose payoff distribution is better, and the extension threshold is selecting for size rather than for frequency. Anything that tunes this archetype on win rate is tuning against the only thing it has.

**Every scheme is still unprofitable at realistic costs**, which is the same result DeadCatBounce reached and for the same reason: there is signal, and it does not cover the round trip. This is a measurement of three chosen configurations rather than of the archetype — nothing has been swept yet, and the promotion criteria under "Decisions taken" are not close to met.

**The null arm's trade counts do not match on two of the three schemes, and that bounds what the table can say.** The matched null holds the signal *count* fixed and randomises the day, but a drawn bar then meets a different stop geometry: under `STOP_EXCURSION` most draws fail the minimum-risk test, so A trades about 10,000 times against a null median near 1,900, and C trades about 5,800 against a null median near 8,600. **Only B is cleanly matched** — roughly 1,400 against 1,300 — which makes B's win-rate result the best-evidenced cell in the table and A's blanket "indistinguishable" the weakest. This is a property of pairing a *structural* stop with a day-randomising null, not a defect in either; it belongs on [#32]'s caveat list.

##### The sweep, and why the exit geometry is not the deciding factor after all

The working expectation was that the TP/SL logic would decide this archetype's profitability more than anything else — it is the one whose geometry inverts, and three whole schemes were built for it. **Measured at one minute it is not true**, and the way it fails is more useful than the expectation was. **Read this whole subsection as one-minute-only**: the full sweep below adds bar size as an axis and finds it dominates everything here, which the η² table cannot show because it holds resolution fixed.

**The run.** 11,808 combinations per contract over the four MNQ front-months named above: `band_period × entry_std × min_bars_outside × max_entry_std × band_lag` crossed with each scheme's own exit axes, at $1.50 round trip and one tick. 40,672 of the 47,232 rows clear 30 trades. **6.3% of them are profitable**, and **7 of the 10,168 configurations present on all four contracts are profitable on all four**.

**Which axis moves the profit factor**, as the share of PF variance a single axis explains (η², within scheme, over the ranges swept):

| scheme           | entry axes | exit axes | largest single axis      |
| ---------------- | ---------- | --------- | ------------------------ |
| A, rotation      | 0.44       | 0.08      | `entry_std` 0.25         |
| B, ATR bracket   | 0.06       | 0.09      | `atr_stop_multiple` 0.06 |
| C, time and mean | 0.22       | 0.12      | `entry_std` 0.10         |

`entry_std` is the largest single axis in every scheme. **η² is a property of the ranges swept, not of the strategy** — a wider `tp_multiplier` range would raise the exit column — so read the table as "over ranges a person would actually try", not as a law.

**The surface only half replicates.** Spearman rank correlation of PF between contracts, over configurations present on all four: A **+0.51**, C **+0.50**, B **+0.07** (one pair negative). So B's geometry surface carries essentially no information that survives to another contract, and A's and C's carry some — most of it in the entry axes above.

**Selecting on one contract is worse than not selecting.** The best 20 configurations on 03-24 average PF 1.489 there and 1.320 on 03-25, but **0.760 and 0.832** on 09-24 and 09-25 — *below the median of every configuration* on those two contracts, which is 0.839 and 0.883. This is the multiple-comparisons trap producing exactly what the standing rubric says it produces, on this project's own data, and it is worth quoting whenever a sweep result is being read.

##### The method that does answer the question: excess over the matched null

A sweep can say which geometry has the highest profit factor. It cannot say **whether that geometry earned it**, because a bracket that suits the bars flatters a random entry just as much. The random-entry arm splits the two, per geometry:

- **`null_median`** — what this TP/SL yields on these bars with no entry edge at all. The geometry's own contribution.
- **`observed − null_median`** — what the entry rule adds *at that geometry*. The excess.

Run with the entry **fixed** at the middle of every axis, chosen before looking at any result, varying only the exit geometry, 200 iterations, MNQ 03-24:

| scheme           | observed PF spread    | null PF spread        | excess spread   | verdicts                           |
| ---------------- | --------------------- | --------------------- | --------------- | ---------------------------------- |
| B, ATR bracket   | 0.638 → 0.990 (0.352) | 0.640 → 0.864 (0.224) | −0.003 → +0.125 | indistinguishable from random, 9/9 |
| C, time and mean | 0.724 → 0.825 (0.101) | 0.483 → 0.802 (0.319) | +0.023 → +0.252 | better than random, 11/12          |

**Observed PF correlates +0.71 with null PF across geometries.** Most of what a geometry sweep is ranking is what the geometry does to *any* entry.

**B is the pure case of the trap.** Widening the bracket takes observed PF from 0.638 to 0.990 and looks like tuning; roughly two thirds of that move is present in the random arm, the excess never clears significance, and the highest cell is still under 1. This is `Trading-Docs`' "R:R and win rate are not independent knobs" measured rather than argued.

**C is the finding, and it inverts the ranking.** Its observed PF barely moves across geometries while its null moves three times as much, so the excess is where all the information is — and **the excess is largest at the nearest target and smallest at the furthest**, which is the opposite order to the profit factor:

| C geometry   | observed PF   | null PF | excess            |
| ------------ | ------------- | ------- | ----------------- |
| target −0.5σ | 0.724 (worst) | 0.483   | **+0.241 (best)** |
| target +0.0σ | 0.740         | 0.637   | +0.103            |
| target +0.5σ | 0.755 (best)  | 0.709   | +0.047 (worst)    |

Picking the geometry on profit factor picks the one where the entry's advantage has been given away. The mechanism is that a near target is a *bad* geometry for a random entry — small wins against an unbounded stop — and a good one for an entry that genuinely reverts, so the near target is where the entry's information is worth most.

**The standing instruction that follows: rank exit geometries by excess over the matched null, never by profit factor.** The two agree on B, where neither is significant, and point in opposite directions on C, where one of them is — so the case that matters is the case where profit factor misleads, and nothing in a sweep table says so. `tools/geometry_contribution.py` runs the comparison and reports the two rankings side by side with the word DISAGREE when they part.

##### Two axes that do nothing, and neither is visible to `dead_axes`

- **`max_entry_std` at 4.0 is inert** — mean PF moves by about 0.002 in every scheme, because the stretch rarely reaches 4 standard deviations. The ceiling from Leung and Li is a real idea and this parameterisation of it is not a test of that idea; it needs a value close to `entry_std` to bite at all.
- **`exit_on_invalidation` is structurally unreachable under `STOP_EXCURSION` at `stop_offset_ticks = 0`.** It changes the profit factor in **0%** of cells there, against 80% at two ticks and 88% at eight: the stop sits *at* the excursion extreme, so price reaching it intrabar exits the trade before any close beyond it can be observed. Two rules that look independent are one rule plus an offset.

Both are the same class as the ATR dollar floor collapsing `atr_stop_multiple`: whether an axis does anything is a property of the *data* and of another parameter, not of the grid, so `dead_axes` cannot see it and only a spread check on the realised numbers will.

##### The full sweep: every contract, five resolutions, and a tight stop

**The sweep above was one minute only, and that made its headline wrong.** Resolution was not an axis in it, so "the exit geometry is not the deciding factor" was measured with the largest lever held fixed. Re-run properly — **both roots, all 19 contracts each, resolutions 1, 2, 5, 10 and 15 minutes, 1,026 combinations per point, 194,940 rows** — the picture changes and the earlier η² table should be read as a within-one-minute result rather than a general one.

**Bar size is the biggest lever there is.** Median profit factor, MNQ, over every combination at that resolution:

| resolution | ATR stop | tight stop |
| ---------- | -------- | ---------- |
| 1 min      | 0.861    | 0.791      |
| 5 min      | 0.922    | 0.884      |
| 15 min     | 0.955    | 0.955      |

Monotone in both columns, on both roots. **The mechanism is friction, and it was predicted before it was measured**: commission is a fixed sum per trade, so it is a shrinking share of a larger bar's range — median 7.6% of an average losing trade at 1 minute against 3.0% at 15. Nothing about the strategy improves with bar size; what improves is how much of it survives the round trip.

##### A stop just beyond the signal candle: measured, and it does not help

The idea is a cheap repeated attempt — put the stop a tick or two past the candle that signalled, so a move that keeps going costs almost nothing and the next bar can try again. It is now `STOP_SWING` and `swing_lookback = 1` is exactly that stop.

**It makes no difference.** Median profit factor across the whole MNQ sweep, by how far beyond the extreme the stop sits and how many bars it looks back over:

| offset, ticks | lookback 1 | lookback 2 | lookback 3 |
| ------------- | ---------- | ---------- | ---------- |
| 0             | 0.858      | 0.859      | 0.858      |
| 2             | 0.866      | 0.866      | 0.866      |
| 8             | 0.869      | 0.869      | 0.869      |

Flat to three decimal places in every direction. **At one minute the tight stop is materially worse than the ATR bracket** (0.791 against 0.861) and it only pulls level by 10 minutes. The reason it cannot win is the one the cost floor already predicts: a tighter stop shrinks R while the round trip stays the same size, so it buys more attempts at a worse price each. It is a sound idea about *market* structure defeated by *cost* structure.

##### Profit-taking: less aggressive is better, and it is the one exit axis that matters

Median profit factor by where the target sits, in standard deviations from the basis, signed towards the trade — −1.5 exits well before the mean, +2.0 holds through it to the far band:

| target | 1 min | 5 min | 15 min    | win rate at 15 min |
| ------ | ----- | ----- | --------- | ------------------ |
| −1.5σ  | 0.689 | 0.805 | 0.873     | 0.23               |
| −0.5σ  | 0.773 | 0.867 | 0.949     | 0.17               |
| +0.0σ  | 0.803 | 0.888 | 0.970     | 0.15               |
| +1.0σ  | 0.831 | 0.917 | 1.000     | 0.13               |
| +2.0σ  | 0.841 | 0.941 | **1.007** | 0.11               |

**Monotone across every resolution**, and the only cells in the whole table that reach 1.0 are the two most patient targets at 15 minutes. So the answer to "would more or less aggressive profit taking help" is **less**: take the win rate from 23% down to 11% and hold for the bigger move. That is the opposite of the usual mean-reversion instinct, and it is the same direction §M26's earlier null decomposition found for the *observed* profit factor — with the same warning attached, that observed profit factor and excess over the null rank geometries differently.

##### Held out, and then the test it fails

Selecting on the oldest half of the contracts by expiry and confirming on the newest half:

| root | top 20 on the selection half | the same 20 on the held-out half | all configurations |
| ---- | ---------------------------- | -------------------------------- | ------------------ |
| MNQ  | 1.386                        | **1.022**                        | 0.903 / 0.882      |
| NQ   | 1.497                        | **1.202**                        | 0.970 / 0.938      |

Rank correlation between the halves is **+0.79** on both roots, so the surface genuinely replicates — mostly because resolution is in it and resolution replicates. **This is a real improvement on the one-minute result**, where selection landed below the median of everything.

**It still fails the null.** The configuration the split chose — 15 minutes, band period 20, entry at 3σ, stop one tick beyond the signal candle, target +0.5σ — run against a matched random entry on eight contracts per root, with trade counts matching closely enough to trust the comparison:

| root                  | observed PF | null PF | excess | profitable | **beats the null** |
| --------------------- | ----------- | ------- | ------ | ---------- | ------------------ |
| MNQ, $1.50 round trip | 1.180       | 0.954   | +0.226 | 4/8        | **2/8**            |
| NQ, $4.50 round trip  | 1.258       | 0.953   | +0.305 | 4/8        | **1/8**            |

The mean excess is positive and it is **two quarters carrying it** — 03-23 and 09-24 both show about +0.8, and the rest sit at or below zero. Per contract the chosen configuration is profitable through 2022 and 2023 and loses through 2024 to 2026, with a $16,204 drawdown on a single MNQ contract against $42,164 of profit summed over all nineteen. That is not an edge that decayed; it is an edge that was never separable from two good quarters.

##### NQ beats MNQ on the same rules, and it is arithmetic rather than edge

Costed honestly — **$1.50 round trip on MNQ against $4.50 on NQ**, rather than the sweep's mistake of applying MNQ's figure to both — NQ still comes out ahead: 32.2% of combinations profitable against 21.0%, and a median profit factor above 1.0 at 15 minutes where MNQ reaches 0.955. Commission is three times larger and the point value is ten times larger, so the drag per point is about a third of MNQ's.

**It buys money, not edge**: NQ beats the matched null on *fewer* contracts than MNQ, not more. Any rule this marginal is worth more on the big contract, and that is a fact about the contract rather than about the rule. It also cuts the other way for a prop account, where the position size that clears the friction floor may exceed what the account permits.

**Build that grid once, because M19 reads it too.** The bandwidth form recommended above for the squeeze is `(upper − lower) / basis`, which is `2 · num_std · σ / basis` off the same two rows — so the two archetypes share one grid rather than each inventing a Bollinger of its own, which is the first item on the standing rubric.

**What [#170] would be checked against is already written down**: [nt8-fidelity.md](nt8-fidelity.md) §M26 names the NinjaScript every rule becomes. **It is not earned.** The full sweep is the one the promotion criteria under "Decisions taken" asked for, and the archetype fails them: the configuration that survives held-out selection beats a matched random entry on two contracts out of eight, and its profit is two quarters wide.

### M27 — the registry-wide campaign: every archetype, every axis ([#195], [#196])

The first sweep that treats the registry as one question rather than six. Every archetype across bar resolution, market regime, session phase, relative volume, trend label, higher-timeframe side and every moving-average axis it owns, on both roots, at the real commission for the root — then through the three tests a sweep table cannot pass on its own.

#### In plain terms

Six trading strategies were each tried with every sensible combination of their settings, on five different bar sizes, in every market condition the codebase can label, on both the big and the small Nasdaq contract, with realistic commission and slippage. That is 760,960 runs.

Then the obvious trap was avoided. Trying 760,960 things and keeping the best one is how you find something that worked *by luck* — the more you try, the luckier the best one looks. So three further checks were run:

1. **Would you have picked it in advance?** Choose the best settings using only the first 60% of the history, then see how those same settings do on the last 40%, which the choice never saw.
2. **Is it the entry rule, or just the exit?** Re-run the same strategy with its entry replaced by a coin flip that trades the same number of times at the same times of day. If the coin flip does just as well, the entry rule is contributing nothing and the money is coming from the stop-and-target geometry.
3. **Could you survive trading it?** Compare the profit to the worst losing streak it went through to earn that profit.

**Five of the six fail one of those. One passes the first two and fails the third**, and the reason it fails the third is a single missing parameter rather than a broken idea.

The vocabulary, once:

- **Profit factor** — gross winnings divided by gross losses. Above 1.0 makes money, below 1.0 loses it. It says nothing about how bumpy the ride was.
- **Bar size / resolution** — how much time one candle covers. A 5-minute bar is five 1-minute bars added together.
- **Regime** — whether the market is trending (DIRECTIONAL), chopping sideways (CONSOLIDATING) or neither (UNCLASSIFIABLE), measured by the efficiency ratio (§M10.1).
- **Stratum** — one slice of the data, such as "only trending markets". Slices are taken one at a time and never crossed, so each answers its own question with a full sample behind it.
- **The null** — the coin-flip comparison in point 2, built by `nqbt/randomentry.py` (§M7a).

#### What was run

760,960 combinations in about 98 minutes across four passes, on the spliced continuous series for both roots:

- Six archetypes, each with the axes it owns — moving-average periods **and kinds**, entry thresholds, stop modes, target ladders, trailing multipliers.
- Resolutions 1, 2, 5, 10 and 15 minutes.
- Twenty strata, **one dimension at a time and never crossed**: unfiltered, three regimes, seven session phases, three relative-volume states, three trend labels and three sides of a 60-minute average.
- Real costs, per root: **$1.50 round trip on MNQ and $4.50 on NQ**, both with one tick of slippage. Never one figure for both — the point value differs tenfold and the commission does not, so MNQ's number applied to NQ flatters it.

Every figure below is re-derivable from `results/campaign/<Archetype>.duckdb` with `tools/campaign_report.py` and `tools/campaign_holdout.py`; nothing here is a figure that moves on an ordinary pull request, but all of it is a measurement of one dated run rather than a standing property.

#### The four gates, and what each removed

| gate                 | question                                                                                                            | survivors             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------- |
| 1 · the screen       | a majority of configurations profitable in at least one root × resolution cell                                      | 4 of 6                |
| 2 · held out         | best 20 chosen on the first 60%, measured on the last 40%, above 1.0 **and** above the holdout median of everything | 3 of 6                |
| 3 · the matched null | does the entry beat a random entry with the same count and time-of-session profile                                  | 1 of 6                |
| 4 · drawdown         | does the median configuration make more than its own worst peak-to-trough                                           | 1 cell, and only just |

**Gate 3 is the one that matters most and the one a sweep table never shows.** Gate 4 is where the survivor is currently stopped.

#### Gate 1 — bar size is the largest lever, and the moving averages barely matter

The median configuration of every archetype loses money at 1 minute on both roots, and the median net P&L over the whole campaign is negative for all six. What separates them is where they peak:

- **The two ported reversal archetypes and EmaCrossover improve monotonically with bar size**, which is §M26's friction mechanism showing up outside ElasticBand for the first time: a fixed commission is a shrinking share of a larger bar's range.
- **The two inside-bar archetypes do not.** They peak at 5 minutes and fall away by 15. That is a real optimum rather than a cost effect, and it is the first non-monotone resolution result in the project.

Share of profit-factor variance a single axis explains (η², unfiltered stratum), largest first per archetype: resolution 0.76 on InsideBar, 0.56 on DeadCatBounce, 0.47 on PullBackAndGo, 0.34 on EmaCrossover; `trailing_stop_multiplier` 0.46 on InsideBarTrailing; resolution 0.14 and `stop_mode` 0.12 on ElasticBand.

**Every moving-average axis on every archetype falls below 0.04, and most below 0.01** — beaten by the bar size everywhere and by the root on four of the six. All four kinds were swept on DeadCatBounce, PullBackAndGo and EmaCrossover, EMA and HMA on both inside-bar archetypes. Choosing the kind is worth roughly a fiftieth of choosing the bar size. **η² is a property of the ranges swept**, so read it as "over ranges a person would actually try" rather than as a law — but the moving-average ranges here are wide and the answer is not close.

The practical consequence: **stop tuning periods.** The lever is the bar size and, after that, the exit geometry.

#### Gate 2 — held out, and ElasticBand inverts

The benchmark is not zero. It is the holdout median of *every* configuration, which is what you get by not selecting at all.

- **InsideBar survives on both roots** — 19 of 20 shortlisted configurations still profitable out of sample, above the holdout median on both.
- **EmaCrossover survives on both roots**, 15 of 20.
- **InsideBarTrailing is marginal**, landing barely above 1.0.
- **DeadCatBounce and PullBackAndGo fail**, as the standing finding says they do.
- **ElasticBand fails hard, and the shape of the failure is the useful part.** Its shortlist averages a profit factor of 1.834 where it was chosen and 0.592 where it was not, with 1 of 20 configurations profitable on MNQ and 0 of 20 on NQ — *below* the holdout median of every configuration. It also owns the single highest profit factor in the whole campaign. **The archetype with the best number in a 760,960-row sweep is the one eliminated first.** That is the multiple-comparisons trap the standing rubric warns about, measured again on this project's own data and worth quoting whenever a sweep result is being read.

**The regime filter is where InsideBar separates.** The split pass was re-run once per regime: in the DIRECTIONAL stratum **every one of the 20 shortlisted configurations stays profitable out of sample on both roots**, and the holdout median across **every** configuration in that stratum is above 1.0 on both — so it is the whole parameter space rather than a shortlist. CONSOLIDATING is the mirror image at 2 of 20. The separation is sharpest at 10 minutes, where 99.7% of the 864 DIRECTIONAL configurations are profitable on the holdout against 6.1% of the CONSOLIDATING ones.

That is mechanically what an inside-bar *breakout* should do, which is the reason to believe it rather than the reason to be suspicious of it.

#### Gate 3 — only one archetype's entry contributes anything

Each configuration was chosen on the selection window and placed against its matched null on the holdout, so the choice never sees the test data. Trade counts match the null closely in every row, which is what makes these comparisons clean — unlike §M26's, where two of three exit schemes were badly mismatched.

- **InsideBar: excess of about +0.17 and +0.14 profit factor over its null, at the 96th and 93rd percentile of the null distribution.** Positive on both roots, and *not* significant on either (p ≈ 0.08 and 0.16).
- **EmaCrossover: essentially nothing** — about +0.03 and +0.05, near the 60th percentile. Its null median profit factor is close to 1.0, meaning **a random entry inside its ATR bracket is roughly break-even after real costs at 15 minutes.** Its held-out survival is the geometry, not the crossover. It remains a useful known-negative control arm and is not a candidate.
- **InsideBarTrailing: within 0.005 of its null on both roots**, on either side of it. Read against InsideBar, which shares its entry, that says the trailing exit gives back exactly what the fixed bracket keeps.
- **ElasticBand: worse than random**, significantly so on win rate (p = 0.01) and mean R (p = 0.04), on both roots.

Per contract, which is thirty-eight samples rather than one: the InsideBar configuration beats its own null on 13 of 19 MNQ contracts and 12 of 19 NQ ones. Split honestly into the contracts the selection window covered and the ones it did not, that is **16 of 22 in sample and 9 of 16 out of sample**, with the mean excess staying positive on both roots and roughly halving.

**The honest reading is "there is probably something here", not "this is established."** No null test in the campaign reaches p < 0.05 on profit factor. What InsideBar has is a consistent sign across two roots, thirty-eight contracts and a held-out window — which is more than anything else in this project has produced, and less than proof.

#### Gate 4 — what stops it is the bracket, not the entry

InsideBar's profit factor comes from a deliberately lopsided bracket: a stop 5–20× ATR beyond the signal bar against a target of a bare 1× ATR from the fill. Across the holdout window that produces an **85–90% win rate with an average loss three to five and a half times the average win**, and a maximum drawdown that swallows the profit — unfiltered at 5 minutes, the median configuration ends the window with less than a third of its own worst peak-to-trough in profit.

Only **one cell of InsideBar's holdout** has a majority of configurations finishing with more profit than their own drawdown: DIRECTIONAL at 10 minutes, at 60% of them, and even there the median ratio is about 0.9. Net-to-drawdown was measured on InsideBar because it is the only archetype that reached this gate; the others fail an earlier one.

**A profit factor above 1.0 built from an 87% win rate and a 5:1 loss-to-win size is not an edge that survives a bad quarter.** Reading profit factor without the drawdown beside it is how this cell would have been mistaken for a result.

**And the reward half of that geometry was never swept, because it does not exist.** `InsideBarParams` carries an `atr_multiplier` for the stop and **no multiplier at all for the target** — the 1× ATR target is hardcoded, following `InsideBar.cs`, which hardcodes it too. So the campaign moved the stop across 5×, 10× and 20× ATR and could not move the target by a tick. Half of what produces the asymmetry was structurally outside the grid. [#197] adds the field and [#198] re-sweeps against it, and it is the single highest-value change available because it is the only gate InsideBar fails.

#### What the campaign could not test

- **Sixteen of the twenty strata were never held out.** Session phase, relative volume, trend label and higher-timeframe side have full-window numbers only. Several look strong there, and the full window is exactly where ElasticBand's 1.834 came from — so treat them as unmeasured until [#199] runs them through the split.
- **The DIRECTIONAL cell is too thin per contract**, leaving about 30 trades per front-month contract at 5 minutes, so the per-contract null test cannot run on the strongest cell in the campaign. [#200] loosens the threshold to restore the sample.
- **The held-out split is a single time cut** at 60% of the bars, so it tests one regime transition rather than many. The two roots track the same index over the same dates, so the thirty-eight per-contract samples are not thirty-eight independent ones.
- **`max_hold_bars` means a different amount of time at each resolution**, exactly as a moving-average period does. Nothing scales it, and no result here rests on it.
- **Everything is Tier 1.** EmaCrossover and ElasticBand have no NinjaScript at all, which is why InsideBar surviving matters more than EmaCrossover surviving would have.

#### The tools, and why there are five databases

`tools/campaign_sweep.py` runs the sweep — `--strata core|context|regime|phase|volume|trend|htf|all` so a later pass appends the dimensions an earlier one skipped, and `--split` for the selection and holdout windows. `tools/campaign_report.py` produces the distribution tables and the η² figures, `tools/campaign_holdout.py` the held-out test, and `tools/campaign_null.py` and `tools/campaign_contracts.py` the matched null on the continuous holdout and per contract.

**One DuckDB per archetype**, under `results/campaign/`. At the time, `results._append_or_create` wrote `combos` by name and silently dropped a column the table did not have, so six parameter classes could not share one table — appending an `InsideBarParams` row to a table created from `DeadCatParams` would have stored it with `error_margin`, `atr_length` and `atr_multiplier` thrown away and nothing would have said so. [#201] closed that: the table widens instead, so the split is now a convention rather than a constraint, and the campaign keeps it because its results are already there.

Two things the sweep machinery still cannot see, both already recorded in `.claude/rules/sweep-and-context.md` and both worked around here rather than fixed: ElasticBand's stop and target axes are inert outside their own mode, and `volume_rolling_bars` has two toggles where `dead_axes` knows one. The campaign avoids both by making a stop geometry a *variant* — its own base parameters and its own axes — rather than an axis inside one grid.

### ~~The numpy-native summary path~~ — done ([#33])

`stats.summarise_legs` reads the simulation's raw `LegMatrix` and never builds a DataFrame. `stats.summarise` stays exactly where it was, as the reference; `tests/test_numpy_summary.py` is what says the two agree.

**Measured on the full spliced MNQ series** — 1,663,489 bars, the 8-combination grid `tools/capture_trade_logs.py` uses, 218,164 legs, best of three:

|                                          | per combination |
| ---------------------------------------- | --------------- |
| frame + `summarise` (what this replaces) | 28.3 ms         |
| `summarise_legs`                         | 9.0 ms          |
| the `@njit` simulation alone             | 9.3 ms          |

**3.1× on a combination, and the summary is now inside the noise of the simulation** — the 19 ms of pandas is gone, not reduced. That is the whole of the 71% the profile attributed to `trades_to_frame` plus `stats.summarise`, and it composes with the parallel speedup because it is per-combination work rather than shared setup.

**Both paths share every statistic.** `_summarise_arrays` takes the per-trade vectors and returns the `Summary`; the two entry points differ *only* in how they get those vectors — `groupby` on one side, a boundary scan on the other. That is deliberate, and it is what makes "do they agree?" a question about the grouping rather than about twenty-eight formulas. Do not re-inline it into either caller.

**Pandas' `groupby.sum` is Kahan-compensated, and a plain running sum does not reproduce it.** Measured: over 50,000 four-element groups of random doubles, `np.add.reduceat` disagrees with pandas on 35% of groups and a naive accumulation on 21%, always in the last bit. The exactness `#33` asks for is therefore only reachable by carrying the compensation term, which `_grouped_sum` does. `tests/test_numpy_summary.py::test_the_grouped_sum_is_compensated_like_pandas` guards it with a four-value group that sums to 0.0 naively and 2.0 compensated, and the test above it pins that those two summations genuinely differ — verifying the gate can fail is part of using it. The costed DeadCatBounce case in `test_the_two_summary_paths_agree_exactly` also catches a naive sum on real trades, so this is live rather than adversarial-only.

**`_ordered_starts` refuses keys that are not already ascending.** `groupby` returns groups sorted by key whatever order the rows arrived in, so a boundary scan only reproduces it for sorted keys. The simulation writes every leg of a trade before the next trade can open — it cannot be in two positions at once — so this holds by construction, and the check guards against a future producer rather than being a branch anyone takes.

**Everything else agrees for free, and that was checked rather than assumed.** Whole-array `Series.sum`, `.mean`, `.std(ddof=1)`, `.max`, `.min`, `.cumsum`, `.cummax`, `.median` and `.quantile` are all bit-identical to their numpy equivalents here (no `bottleneck` installed), strided column views included. Only the grouped reductions needed care.

**A gapless day index is not the same as a UTC one.** `Dataset.day_codes` is each bar's calendar day *in the index's own timezone*, because `summarise` groups daily P&L by `DatetimeIndex.date` and that is local. On the UTC archive the two coincide, which is exactly why reading them off UTC would have passed every test here and been an hour out on a `Europe/London` index — the same shape as the trade-list timezone bug in `tools/reconcile_nt8.py`. Precomputed in `context.prepare` rather than per combination: the conversion over 1.65M bars costs about as much as a whole combination.

**The leg matrix is now a producer's output, not an intermediate.** `runner.deadcat_legs` and `pullback.pullbackandgo_legs` stop at `trades.LegMatrix`; `run_deadcat` and `run_pullbackandgo` are those plus the frame. `Archetype.legs` is a required registry field beside `run`, deliberately not derived from it — an archetype registered with only `run` would silently be the slow one in a sweep, and the symptom would be a wall clock rather than an error.

**The schema guarantee survives.** A sweep no longer calls `trades.validate`, so `trades.validate_legs` asserts the same invariants on the matrix — nulls in required columns, `direction ∈ {±1}`, positive quantity, leg numbering from 1. It adds one check `validate` deliberately omits: `exit_reason` must be in `EXIT_REASONS`. On a *frame* that column may hold a label NT8 wrote (`Stop3`, `Exit`), but a matrix can only have come from the simulator, so a code outside the enum there is a bug. It is written column by column with an early exit for the same reason `validate` is — the readable `rows[:, REQUIRED_INDICES]` form copies ten columns on every combination and cost 12% of one.

**Two things this deliberately did not change.** `run_combination` still computes its summary the same way whether or not `keep_trades` is set, so the flag changes what is *returned* and never what is *measured*. And `summarise` remains the definition: where the two ever disagree, the pandas one is right.

**The evidence it moved nothing** is `tools/capture_trade_logs.py`: all 14 files byte-for-byte identical across the change, including `sweep_serial.csv` and `sweep_parallel.csv`, which are the summary tables now produced by the new path over 218,164 legs, and `live_summary.csv`, which is the refactored `summarise`.

**Where the next win is, if anyone wants it.** `sweep.sweep` end to end is 12.3 ms per combination against `summarise_legs`' 9.0 — the 3.3 ms difference is `dataclasses.replace` per combination, `params.as_dict()` and `Summary.as_dict()`'s `asdict` deep copy. Small in absolute terms, but it is now a quarter of a combination rather than a tenth, and M18's wide grids multiply it. Not worth doing before there is a workload that needs it.

### ~~M7a~~ — the random-entry control arm: done ([#32])

`nqbt/randomentry.py`. This section is the methodology, the reasoning behind it and the first result; the module carries a pointer here rather than a copy ([#105]).

**A backtest reports numbers, not evidence.** "Profit factor 0.746" is only interpretable against what the *same bracket, the same costs and the same exits* would have produced with entries chosen at random, and until that arm exists three very different diagnoses look identical: *worse than random* (the rule carries real information and points the wrong way), *indistinguishable from random* (the rule contributes nothing, and further tuning is a search over noise), and *better than random but still unprofitable* (there is signal; the loss is in costs, hold time or bracket geometry). Permuting an existing trade sequence separates none of them, because it takes the entries as given.

**The design principle is hold everything fixed, randomize only what is under test.** The quantity under test is *when the strategy chooses to enter*, so the null holds the bars, the instrument, the costs, the bracket geometry, the ratchet, the force-flat rule, the direction, the number of entry signals and the time-of-session distribution, and randomizes only which trading day each signal lands on.

**Time-of-session matching is the load-bearing part, and it is exact rather than coarsened.** Intraday index futures have a pronounced volume and volatility seasonality, and a bracket built from fixed tick offsets has materially different hit probabilities in a volatile hour than a thin one. A null scattering entries uniformly across 23 hours would trade mostly in thin overnight bars and lose for reasons unrelated to entry quality — **it would flatter every strategy ever tested against it**. Minute-of-session is discrete and low cardinality against millions of bars, so exact matching is feasible and bucketing into session phases would leave real confounding inside each bucket. That also keeps M7a independent of M10.4 ([#43]), whose labels exist to stratify results rather than to condition a null.

**The day is randomized rather than matched, deliberately.** Choosing which days to be active on is part of what an entry rule does, so it is under test; matching on it too would reduce the question to intraday timing alone.

**The null runs the archetype's own `run` with a substituted signal.** `run_deadcat` and `run_pullbackandgo` gained a `signal=` override for this, and `Archetype` gained a `signal` field so the registry can hand over the real signal to match against. That is what makes the two arms share one `simulate_deadcat` call rather than two implementations that were reviewed and found to agree — the standing trap about forking the bracket applies to a control arm exactly as it does to an archetype.

**Many draws, not one.** A single random-entry backtest is the folk version of this idea and is not evidence. The output is a Monte Carlo randomization test in the same shape `spread_vs_resampling` already uses. Two differences from that test, both real: this one **may** report time-dependent statistics, because every draw is a genuine simulation over real bars rather than a relabelling; and its p-value carries the add-one correction, so a statistic no draw beat reports 1/(n+1) rather than claiming zero.

**The p-value is two-sided on purpose.** An entry rule reading *worse* than random is a finding — real information pointing the wrong way — and a one-sided test would report it as an unremarkable failure to beat the null.

**`DEFAULT_ITERATIONS` is 200, not `spread_vs_resampling`'s 1,000.** Each draw here is a full simulation over every bar rather than a regrouping of an existing trade list, so an iteration costs two orders of magnitude more. 200 gives a p-value resolution of 0.005, finer than the decision being made with it; raise it when a result lands near the threshold. The numpy-native summary path ([#33]) is what makes a larger default affordable at all.

**Drawing is without replacement within a minute, and the guarantee is structural.** The pool for a minute is *every* bar sharing it, and the real signals at that minute are a subset of that pool, so it can never be smaller than the number of draws. That is why there is no resample-on-collision loop to get subtly wrong.

**The pool is deliberately not narrowed to in-session bars.** The null must face the same bar universe the strategy faced, and narrowing one side and not the other would compare two different bar universes and break the subset guarantee above. Since [#160] the question is moot on both series — `ingest.load_contract` and `build_continuous` filter alike — but the rule is the reason it stays moot rather than something to reinstate.

**`SessionMinutePool` is hoisted out of the Monte Carlo loop because of a measurement.** Grouping means an argsort over the whole series, and rebuilding it per draw was **89% of an iteration** on 914,700 bars — 106 ms against the 13 ms simulation it exists to feed. Same reasoning that hoists `context.prepare` out of a sweep.

**A non-finite observed statistic raises rather than being compared.** "Infinite profit factor beats the null" is an artefact of a run with no losing trade, not a result.

#### What the test still does not do

- **It does not correct for multiple comparisons.** Running it across a sweep and keeping the combinations that beat the null is the trap [#48] exists to guard, with an extra step. Test a combination chosen for a reason, not the best of two hundred.
- **A small p-value is not a tradeable edge.** It says the entry timing is unlikely to be noise; profitability after costs is a separate question the module reports but does not answer.
- **It assumes the signal count is worth matching.** A rule that fires four times is not rescued by a null that also fires four times; the trade floor still applies.

#### The first result, which reframes DeadCatBounce

Costed MNQ from 2024 (914,700 bars, 1.24 commission, 1 tick slippage), 500 draws:

| statistic     | observed | null median | percentile | p     |
| ------------- | -------- | ----------- | ---------- | ----- |
| profit factor | 0.666    | 0.551       | 99.6       | 0.012 |
| expectancy    | −10.24   | −14.78      | 99.8       | 0.008 |
| win rate      | 32.2%    | 29.3%       | 99.8       | 0.008 |

**The entry rule is better than random and still loses money.** That is the third of the three diagnoses this milestone was built to separate — *there is signal; the loss is coming from costs, hold time or bracket geometry rather than from entry selection* — and it is a different conclusion from "unprofitable, therefore worthless", which is what every previous number supported. It does **not** make DeadCatBounce tradeable and does not change its role as the test fixture; it changes what the next question about it is.

Three caveats, recorded so the result is not over-read. It is **one pre-specified parameter combination on one root**, not a sweep, so no multiple-comparisons correction applies and none is implied. **The arms match on signals and diverge on fills** — 74.4% against 47.7%, because the `min(Low[0], Close[0] − 2 ticks)` trigger sits just under an inverted hammer and well below an average bar — so per-trade rates are the fair comparison and `net_pnl` is not; that is why the defaults are `RATE_STATISTICS` and why both trade counts sit on every row. And the rule being tested is *bar selection*, which carries bracket geometry with it, so "better than random" is a property of the whole rule rather than of directional timing alone.

On that last point the win-rate result is the more informative one: an R-multiple bracket scales stop and target together, so win rate is close to scale-invariant and a 3-point edge is not obviously explained by the strategy's bars simply being wider. **A null that also matched the risk distribution would isolate pure directional timing** and is the natural refinement — worth doing before anyone acts on this, not before it is believed.

### M7 — the null, split into M7a and M7b ([#32], [#50])

Three tools answering different questions: `walkforward.py` tests whether a parameter choice survives data it did not see, `montecarlo.py` tests whether an equity path was luckier than the trades justify, and `randomentry.py` supplies the null the other two cannot — same bars, same bracket geometry, same costs, same exit logic, entries drawn at random. **M7a was pulled ahead of the archetypes.** The roadmap originally scheduled it after M11 because it shares machinery with §11.4's permutation test, but **that sharing is symmetric and the interpretive need is not** — build the null first and M11's guard inherits it, whereas the *need* arrives the moment a second archetype exists. Against PF 0.746 it separates three diagnoses that currently look identical: worse than random (the signal is real but inverted), indistinguishable from random (stop tuning this archetype), and better than random but not past costs (attack costs, hold time or bracket size). Permuting an existing trade sequence cannot distinguish any of those, because it takes the entries as given. **It must be matched on direction** as well as count and time of day, or a long-only null against a bidirectional archetype measures market drift.

### M7b — walk-forward and Monte Carlo: done ([#50])

`nqbt/walkforward.py`, `nqbt/montecarlo.py` and `nqbt/costs.py`. The third is not scope creep — see below.

**Costs are an argument with no default, because an uncosted walk-forward is worse than none.** Every archetype's parameter class defaults `commission_per_contract` and `slippage_ticks` to zero, which is right for NT8 reconciliation and wrong for every ranking. Selection on gross P&L selects for *trade frequency*, which is the one thing costs punish, so an uncosted walk-forward reports a clean result that inverts the moment costs are applied — a failure that looks like success. `walk_forward` therefore raises on `costs.FREE` rather than defaulting, and `costs.LIVE` carries the real account's terms. **Do not "simplify" this to a default.**

The defaults themselves stay zero and must: `tools/capture_trade_logs.py` uses them for the reconciliation captures, so flipping them breaks the trade-log gate.

**The split geometry is asserted as a property, not as arithmetic.** `splits()` returns half-open positions and the tests check directly that no test bar is ever a train bar and that the out-of-sample windows *tile* the tested region — the latter is what makes concatenating their trade logs legitimate rather than double-counting. A test that recomputed the arithmetic would pass over the same off-by-one it was meant to catch.

**Each window is simulated independently, and that is a stated approximation.** A trade open at a boundary is not carried across it: every window starts flat. The alternative — one run with the selection changing mid-flight — cannot be measured per window at all. The cost is that a position spanning `test_start` would have blocked an entry that the sliced run now takes.

**`warmup_bars` prefixes each window and its trades are discarded by entry position.** Without it every window's indicators start cold, so an SMA(200) grid measures its own warm-up for the first 200 bars of each split. `entry_bar` is already a position into the sliced frame, which is what the prefix is measured in — do not reach for `entry_time` and an index lookup.

**Selection is capped to `TRADE_PNL_STATISTICS`.** Every one of them is higher-is-better, so one comparison serves both sides. Admitting `max_drawdown` would need the opposite sense and a direction bug there is invisible — it would simply select the worst combination every time.

**`trade_id` restarts at 1 in every window, and pooling on it silently merges trades.** `stats.per_trade` groups on `trade_id` alone, so collapsing the concatenated log counted 5 trades where there were 14. `WalkForwardResult.pooled_pnl` groups per split *before* the leg collapse. Found by a test asserting the pooled count equals the sum of the per-split counts; without that assertion every downstream statistic would have been quietly computed over a quarter of the data.

**Monte Carlo's two halves answer different questions, and the guard between them is the point.** `permutation_test` reorders the trades, which moves only `PATH_STATISTICS`; `bootstrap` resamples with replacement, which moves the values too. Permuting a `TRADE_PNL_STATISTICS` value is **refused**, because reordering cannot change profit factor, net P&L, expectancy or win rate — such a test returns `p_value` 1.0 for every input and reads exactly like a passed check. `stats.PATH_STATISTICS` is the exact complement of `TRADE_PNL_STATISTICS` and `stats.path_statistic` is the single definition, sharing `_max_drawdown` and `_max_consecutive` with `summarise`. A test pins both halves: that reordering *cannot* move a value statistic, and that it *can* move a path statistic.

**Neither test says the entries are any good.** Both take the trades as given, so they cannot separate "worse than random" from "no better than random" — that is `randomentry.py`'s job ([#32]), and a Monte Carlo result quoted without it is half an argument.

**Drawdown is measured from the running peak of the equity curve, which starts at the first trade rather than at zero.** Ten $10 losses followed by ten $10 wins reports 90, not 100. That is `summarise`'s existing definition and this must not fork it; a test pins the two together.

**First result, and it is a confirmation rather than a finding.** Costed MNQ from 2025-01-01 (564,927 bars, `DeadCatParams`, 9 combinations, 120,000-bar train / 40,000-bar test, 11 splits): training profit factor runs a median 0.611 against a pooled out-of-sample 0.563, four different combinations win a training window across the eleven, and the bootstrap puts net P&L below zero in every resample. The permutation test reads p = 0.70 on max drawdown — **the losses are systematic, not an unlucky ordering**, which is the correct reading and the one that matters: this is the machinery reproducing a result the project already holds, on an archetype whose unprofitability is settled. Re-run it rather than quoting these numbers.

### M10 — the conditions the review needs and we lack ([#39])

The review is meant to score trades against "overall trend, MAs, volume, directional vs consolidation, time of day", and three of those five had no implementation. **All four sub-milestones have landed** — time of day ([#43]), the regime classifier ([#40]), volume ([#41]) and the compact trend label ([#42]), each below. Every one is a 1D label array computed once in `prepare` behind [#27]'s `required_context`, and every one carries its filter as a bitmask integer so it is a legal sweep axis.

**The multiple-comparisons cost is now real and compounds.** Seven session phases against three regimes, three volume states and three trends is 189 cells before an MA gate is touched. That is the argument for the coarse labels rather than an accident of them, and [#48]'s guard applies with more force here than anywhere else in the project.

### ~~M10.4~~ — time of day: done ([#43])

`nqbt/timeofday.py`. Two forms of one clock: `SessionPhase`, seven coarse Eastern-time buckets, and `bar_of_session`, the integer index from the session open. Both come out of one `classify()` pass, both go through `resample.minutes_since_open`, and neither is a second session clock.

**The ET requirement is pinned by a test that states the failure, not only the behaviour.** Two sessions either side of the 2024-03-10 transition are labelled, and the test asserts both that the cash-open bars carry the same *Eastern* minutes and that their *UTC* minutes differ. Without the second half the test is a tautology and would pass over a UTC implementation on a winter window — which is exactly how this bug survives review.

**The end-of-bar convention decides the boundaries.** A bar stamped 09:30 covers 09:29–09:30 and is the pre-open; the first cash-open bar is stamped 09:31. Same off-by-one M13 found in `bucket_index`, and it is invisible in aggregate — the phase totals are right and only the edges move.

**Bar of session is derived from the clock, never counted off the data.** An ordinal count renumbers everything after a hole, so index *k* would mean a different time of day in different sessions — precisely the confound [#41]'s relative volume exists to divide out. It is therefore literally `resample.bucket_index`'s bucket, which is also what makes the two share a definition rather than each inventing one. `prepare` takes `bar_minutes` explicitly and `sweep_axes` passes the resolution it already knows; inference off the index's own gaps is the fallback, not the path.

**The filter is a bitmask integer, and that is what makes it sweepable.** A tuple of phases would have to join `not_sweepable`; a scalar mask is one value per combination, so `phase_filter=[CASH_OPEN.bit, ALL_PHASES]` is two combinations and "does this only work at the open?" is a sweep rather than a set of hand-run backtests. `ALL_PHASES` is the default and each archetype's signal **skips the conjunction entirely** at that value, which is why adding the field to two reconciled archetypes moved nothing.

That skip is not an optimisation. A bar carrying no label passes *no* mask, `ALL_PHASES` included, so ANDing the gate at the default would quietly drop those bars and move a result. The no-op has to be no call.

**Gated.** All 12 captured trade logs are byte-identical (`sha256` too); the two sweep summary tables differ by the added `phase_filter` column and are identical on every pre-existing column, dtypes included — `compare_trade_logs.py --added phase_filter` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First result, and it is a stratification rather than a finding.** Costed MNQ from 2024 (914,700 bars, stock `DeadCatParams`, $1.24 and 1 tick), one combination run once per phase:

| phase     | trades | profit factor | win rate | expectancy |
| --------- | ------ | ------------- | -------- | ---------- |
| OVERNIGHT | 1,550  | 0.561         | 0.297    | −9.76      |
| LONDON    | 656    | 0.599         | 0.326    | −10.70     |
| PRE_OPEN  | 348    | 0.665         | 0.342    | −10.88     |
| CASH_OPEN | 151    | 0.677         | 0.325    | −23.76     |
| MIDDAY    | 478    | **0.871**     | 0.383    | −5.57      |
| AFTERNOON | 297    | 0.709         | 0.327    | −12.54     |
| CLOSE     | 159    | 0.631         | 0.321    | −8.47      |
| all       | 3,639  | 0.666         | 0.322    | −10.24     |

The seven counts sum to the unfiltered 3,639 exactly, which is the property that makes this a decomposition and not seven overlapping subsets; a test pins it. **Do not read the MIDDAY row as an edge.** It is the best of seven cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and no cell reaches a profit factor of 1. What it does say is that the aggregate 0.666 was averaging populations that differ by 55%, which is the argument for the milestone rather than a result from it.

**The prediction about the last phase was directionally right and quantitatively small.** `session_close_share` reads 0.0016 on CLOSE against 0.0001 overall — an order of magnitude, and still tiny, because a 1-minute DeadCatBounce holds for minutes. The artefact is real and will grow with bar size ([#30]); on this data it is not what makes the CLOSE row look the way it does. Read the column before attributing anything to the clock, and expect it to matter at 15 and 30 minutes where it does not here.

**Cost.** `needs_time_of_day` is requested the way VWAP is — only when some combination actually narrows the phases — and adds three arrays (`int8`, `uint8`, `int32`) over the series. The eight-combination sweep above took 0.6 s over 914,700 bars, so the gate itself is not measurable against the simulation.

**Smaller choices in `timeofday.py`, recorded here rather than in the module ([#105]):**

- **Seven buckets, chosen for what happens in them rather than for equal length.** The overnight hours are one bucket because little distinguishes 20:00 from 01:00; the hour after the cash open gets one to itself because it is the most distinctive hour of the day. Fewer buckets is the point — time of day multiplies every other stratification, and seven phases against five regimes is already 35 cells, which a minimum-stratum guard on a few hundred real trades has to survive.
- **`SessionPhase.CLOSE` is structurally anomalous**, because it contains the forced flat ([#16]). Its exits are decided by the clock rather than the rules, so a stratification will show it as different whatever the market did. `FORCED_EXIT_PHASE` names it so a caller can exclude it without working out which one it is.
- **`OUT_OF_SESSION` is −1, not an eighth phase**, so it cannot be swept into a filter by accident and a `groupby` over the labels reads as obviously wrong rather than quietly counting stray prints as an eighth hour of the day.
- **`PHASE_STARTS` is written as ET wall-clock times**, because that is what the boundaries mean: `time(9, 30)` is the cash open, where an offset of 930 minutes is a number nobody can check. `phase_start_minutes` converts them and validates on **every** call rather than once at import — the boundaries are relative to the template's own open, so a template opening elsewhere reorders them, and a set that no longer ascends would mislabel whole phases through `searchsorted` without raising.
- **`infer_bar_minutes` takes the mode of the gaps**, not the minimum or the mean: every session has a one-hour break and the archive has holes, so both of those measure the gaps rather than the bars.

### ~~M10.1~~ — market regime: done ([#40])

`nqbt/regime.py`. Kaufman's efficiency ratio — `|close[t] − close[t−n]| / Σ|diff(close)|` over the lookback — cut by two thresholds into `CONSOLIDATING`, `UNCLASSIFIABLE` and `DIRECTIONAL`. Bounded 0–1, three lines of arithmetic, no TA-Lib dependency and therefore none of the NT8-parity work the moving averages needed. The lookback and both thresholds are sweepable and `regime_filter` is a bitmask integer, for exactly the reason `phase_filter` is one.

**The band between the thresholds is a label, not a gap.** Strictly below the lower is consolidating, strictly above the upper is directional, and everything in between — **including both boundaries** — is unclassifiable. That makes the third category free rather than a special case, and it makes the equality question one decision instead of two: no bar can satisfy two regimes, and `validate_thresholds` refuses a pair that cross rather than silently ordering them.

**The warm-up is `UNDEFINED`, which is not a fourth regime and not consolidating.** The house convention for an NT8 indicator is an expanding warm-up, and it is wrong here: over two bars the numerator and the denominator are the same quantity, so an expanding ratio reads exactly 1.0 and would label the start of every dataset `DIRECTIONAL`. Not measured and measured inconclusive are different states, and folding the first into the second would put unmeasured bars into a stratification cell while leaving the counts adding up — the failure that looks like a result. `UNDEFINED` is −1 for the same reason `OUT_OF_SESSION` is, and an undefined bar passes **no** mask, `ALL_REGIMES` included, so each archetype's signal skips the conjunction entirely at the default rather than ANDing a gate that would drop 20 bars from a reconciled run.

**The window sum is recomputed per bar rather than maintained incrementally.** A rolling add/subtract over a million bars drifts, and this is a denominator that legitimately reaches zero: a flat window would turn a −1e−13 of accumulated error into a large negative ratio. The exact version costs 15 ms per lookback over 914,700 bars, paid once in `prepare`, which is not worth trading for that. A window that genuinely never moved scores 0.0 — the extreme of consolidation — rather than dividing by zero.

**The grid holds ratios, not labels.** Both thresholds are swept as well as the lookback, so a grid keyed by all three would multiply out; `EfficiencyRatioGrid` is `[n_lookbacks, n_bars]` float64 and the thresholds are applied at gate time. That is the opposite of `MovingAverageGrid`'s default and the reason `_regime_lookbacks` returns nothing unless some combination actually narrows the filter — eight bytes per element is the most expensive thing a `ContextSpec` can ask for by accident. It is also the shape [#51]'s bandwidth squeeze wants, so the two share a scalar-plus-thresholds classifier instead of each inventing one.

**One function owns the rule.** `_regime_of` is the `@njit` device function both `label` and `gate` call, so the stratification key and the entry filter cannot drift apart. The filter still never builds a label array: `gate` tests `1 << regime` against the mask inside the same pass, which reads 0.23 ms over 914,700 bars against the ~30 ms a combination of the run below costs.

**`dead_axes` had to learn that a mask is off at its everything value.** `ALL_REGIMES` is 7, so the existing truthiness test read the filter as switched on and would have let `regime_lookback=[5, 20]` run every combination twice for identical rows. `archetypes.INERT_AT` states the off value where it is not `False`; nothing else changes.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the four added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added regime_filter regime_lookback regime_consolidating_below regime_directional_above` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, **$1.50 per contract** and 1 tick, lookback 20 and thresholds 0.3/0.5, one combination run once per regime:

| regime         | bar share | trades | profit factor | win rate | expectancy |
| -------------- | --------- | ------ | ------------- | -------- | ---------- |
| CONSOLIDATING  | 71.3%     | 2,396  | 0.611         | 0.312    | −12.04     |
| UNCLASSIFIABLE | 21.9%     | 975    | **0.721**     | 0.331    | −8.40      |
| DIRECTIONAL    | 6.8%      | 270    | 0.616         | 0.296    | −14.97     |
| all            |           | 3,639  | 0.640         | 0.316    | −11.28     |

**Do not read the UNCLASSIFIABLE row as an edge**, and do not diff this table against M10.4's: that one was run at the roadmap's older $1.24. It is the best of three cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and no cell reaches a profit factor of 1. And 270 trades in `DIRECTIONAL` is where a minimum-stratum guard starts to bind — against seven session phases it is 35 cells, and this is the coarsest of the two labels.

**The signals partition exactly and the trade counts do not, which is the point worth keeping.** All three single-regime filters admit 4,889 signals between them, exactly the unfiltered count, and their union is the unfiltered signal bar-for-bar. The trade lists sum to **3,641 against 3,639**. Nothing is double-counted: the simulation holds one position at a time, so removing an entry can free a later signal the unfiltered run was still in a position for. A regime label flips bar to bar where a session phase is a contiguous block, which is why M10.4's seven phases did sum exactly and these three do not. **Stratify the signal, or accept that the trade-level decomposition is approximate** — and never conclude a filter "found" trades from a count that went up.

**71% of 1-minute bars are `CONSOLIDATING` at 0.3/0.5.** The thresholds are resolution-dependent — a minute of noise has a low efficiency ratio almost by construction — so the defaults are conventional starting points to be swept, not a calibration, and they will want different values at 15 and 30 minutes. Read `ambiguous_share` before believing any of the rows: it runs 0.029 / 0.041 / 0.044 against 0.033 overall, highest in `DIRECTIONAL`, which is what a regime of larger bars should do.

**Cost.** Requested the way VWAP is, and adds one float64 series per lookback — 7.32 MB over 914,700 bars, about a sixth of the 47 MB dataset the run above was handed. `prepare` pays 15 ms per lookback and the per-combination gate 0.23 ms, so neither is measurable against the simulation.

**Smaller choices, recorded here rather than in the module ([#105]):**

- **Efficiency ratio rather than ADX**, which is laggier, less interpretable, and would need the same NT8-parity check the moving averages needed. ADX only if this proves inadequate.
- **A lookback of 1 is refused**, because numerator and denominator are then the same quantity and every bar reads 1.0 — a whole axis of `DIRECTIONAL` that looks like a measurement.
- **Three regimes, and deliberately no more.** Time of day already multiplies every other stratification; three against seven phases is 21 cells before an MA gate, and [#48]'s guard has to survive it on a few hundred real trades.
- **The ratio is invariant to direction, level and scale**, which is what makes one pair of thresholds meaningful across both roots and across years of back-adjusted history. A test pins all three.

### ~~M10.2~~ — volume: done ([#41])

`nqbt/volume.py`. **One quantity and its decomposition, not three conditions.** Absolute volume is the raw contract count, the time of day is its dominant systematic component, and relative volume is absolute with that component divided out. `VolumeForm` names the three absolute forms — per bar, a trailing *N*-bar sum, and session-cumulative-to-date — and each is divided by its own bar-of-session baseline to give the ratio the three `VolumeState` labels are cut from. `volume_filter` is a bitmask integer, for exactly the reason `phase_filter` and `regime_filter` are.

**The baseline is the median of the same bar of session over a trailing window of prior sessions, and that is the whole point of the module.** Measured on the run below, a plain trailing median over the 60 *adjacent* bars labels **82% of `CLOSE` bars thin and 57% of `CASH_OPEN` bars heavy** — a table that reads as a discovery and is a clock. Against the bar-of-session baseline the same data gives a heavy share of 16–31% and a thin share of 19–30% across all seven phases. It is not flat, and it should not be: the cash open is the hour whose volume is most predictable, so it is the hour that is least often extreme. What is gone is the part that was only the time of day. A test pins both halves — a series that is a pure function of the bar of session must produce **no state at all**, and the naive normalisation over the same series must manufacture both extremes.

**No bar contributes to its own baseline.** The window is the sessions strictly *before* this one, so a bar's whole session is excluded rather than merely the bar itself. A normalisation that reads the present is a lookahead that flatters every stratification taken through it, and it would be invisible in the output. Pinned as a property: rewriting the last session's volume leaves every earlier session's ratios untouched and scales that session's own ratios exactly.

**Absolute volume is carried and deliberately not filtered on.** It answers the one question relative volume cannot — *can this be traded here at all?* — and it carries when in history a bar happened, which is a cross-check on [#31] rather than a duplicate of it. But it is comparable neither across roots (NQ and MNQ trade different counts for the same exposure) nor across time, so there is no absolute threshold to sweep. Expressing one as a trailing percentile just makes it relative volume again, **which is the honest conclusion rather than a workaround** — and it is why the per-instrument scale in `instruments.py` that [#41] anticipated turned out not to be needed. Two tests state the pair: relative volume is unchanged by scaling the whole series by any positive constant, and a tenfold secular drift moves the absolute series by more than 4× while the relative one spans less than 1.5×. The residual there is worth knowing — a trailing median lags a rising trend, so a strongly trending series sits *above* 1 throughout. The level shifts; the shape is removed.

**It steps at every roll, and that is data rather than an event.** Prices are back-adjusted, volume is not and should not be. A step reaches relative volume for the length of the baseline window and then leaves, so a discontinuity there is dated by the roll rather than by the market. A test pins the arithmetic: an incoming contract ten times the size of the outgoing one reads exactly 10 on the roll session and exactly 1 a baseline window later.

**The warm-up is `UNDEFINED`, for the reason [#40]'s is.** A baseline needs `MIN_BASELINE_SESSIONS` observations before it means anything, so the first five sessions carry no label — 0.8% of the run below, out-of-session strays included. An undefined bar passes **no** mask, `ALL_STATES` included, so each signal skips the conjunction entirely at the default.

**Three forms, and they are three different statements rather than three views worth averaging.** The window a form does not read is dropped from its grid key, so sweeping `volume_rolling_bars` alongside the per-bar form builds one series rather than one per window. What `dead_axes` **cannot** catch is the other half of that: it understands one toggle per axis, so it knows the five volume axes are inert while `volume_filter` admits everything, and it does not know that `volume_rolling_bars` is inert at every form but `ROLLING`. Sweeping the window under a per-bar form runs identical combinations. Known, and not worth a second toggle mechanism for.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the six added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added volume_filter volume_form volume_rolling_bars volume_baseline_sessions volume_thin_below volume_heavy_above` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, thresholds 0.7/1.5 over a 20-session baseline, one combination run once per state:

| form            | cell   | bar share | trades | profit factor | win rate | expectancy |
| --------------- | ------ | --------- | ------ | ------------- | -------- | ---------- |
| per bar         | THIN   | 27.5%     | 992    | 0.534         | 0.300    | −10.54     |
| per bar         | NORMAL | 44.3%     | 1,678  | 0.653         | 0.309    | −11.23     |
| per bar         | HEAVY  | 27.5%     | 942    | 0.686         | 0.346    | −12.27     |
| rolling 30      | THIN   | 18.1%     | 631    | 0.470         | 0.265    | −11.31     |
| rolling 30      | NORMAL | 61.3%     | 2,202  | 0.665         | 0.322    | −10.50     |
| rolling 30      | HEAVY  | 19.8%     | 775    | 0.659         | 0.342    | −13.57     |
| session to date | THIN   | 13.4%     | 513    | 0.526         | 0.263    | −10.27     |
| session to date | NORMAL | 69.8%     | 2,525  | 0.635         | 0.316    | −11.76     |
| session to date | HEAVY  | 16.0%     | 571    | 0.721         | 0.368    | −10.24     |
| any             | all    | 99.2%     | 3,639  | 0.640         | 0.316    | −11.28     |

**Read those nine rows as three, and then as one.** Profit factor and win rate rise with the volume state under all three forms, which looks like three confirmations and is one: the three forms are three views of the same quantity over the same bars, and the time of day has already been divided out of all of them. That is exactly the failure [#41]'s opening table exists to prevent, and quoting it as corroboration would be the mistake it names. No cell reaches a profit factor of 1, expectancy does **not** follow profit factor — HEAVY is the best per-bar cell on profit factor and the worst on expectancy — and [#48]'s guard applies with the usual force. What the table does say is that the three forms decompose the same 3,639 trades very differently: the per-bar form splits them 27/44/28 and the session-to-date form 13/70/16, so "an unusually busy bar" and "an unusually busy session so far" are not the same statement about the same trade.

**The signals partition exactly and the trade counts do not.** For every form the three single-state filters admit exactly the measured signal, bar for bar and in total — 4,841 of the unfiltered 4,889 for the per-bar form, the difference being the warm-up and the strays. The trade lists sum to 3,612 against 3,639. Same cause as [#40]'s and the same conclusion: the simulation holds one position at a time, so removing an entry moves which later signals are free, and the trade-level decomposition is approximate where the signal-level one is exact. **Stratify the signal, or accept the approximation** — and never read a count that moved as a filter having found trades.

**Cost, and it is the most expensive condition so far.** `prepare` pays about 0.2 s per series over 914,700 bars against `regime`'s 15 ms per lookback, because the baseline is a sliding median down each bar-of-session column of a `[session, bar of session]` grid rather than a pass along the series. Sixteen bytes per bar per series — 14.6 MB for one and 43.9 MB for all three, against a 37.5 MB dataset without them. The per-combination gate is 0.14 ms against 3.6 ms for the combination itself, so the filter is cheap and the preparation is what to watch when a sweep asks for several series at once.

**Smaller choices in `volume.py`, recorded here rather than in the module ([#105]):**

- **The median, not the mean.** The baseline window straddles roll dates and holiday sessions, and a mean would carry a half-empty session or a rolled contract straight into the normalisation. A median of twenty ignores one or two of them.
- **Out-of-session prints are not volume here, in any of the three forms.** NT8 building bars against an ETH template would never form them, so they read zero rather than entering a sum or a per-bar count. Their labels are `UNDEFINED` either way, because a bar in no session has no bar of session to be compared against.
- **The rolling window does not reset at the session open.** "Volume over the last thirty bars" reaches back across the maintenance break at the start of a session, which is what the words mean, and the bar-of-session baseline divides out the systematic part of it exactly — the first bars of a session are compared against the first bars of other sessions.
- **A one-bar rolling window is refused**, because it is the per-bar form under another name and would otherwise build the same series under a second key.
- **A zero baseline is undefined rather than infinite.** A bar of session whose prior sessions traded nothing has no scale to be relative to.
- **`MIN_BASELINE_SESSIONS` is a floor rather than a parameter**, and it is both the shortest legal window and the number of observations the window must actually hold. Holes mean the two are different questions.
- **The thresholds are conventional starting points, not a calibration.** 0.7 and 1.5 against a median put roughly a quarter of bars in each tail on this data; they are resolution-dependent the way [#40]'s are and will want different values at 15 and 30 minutes.

### ~~M10.3~~ — the compact trend label: done ([#42])

`nqbt/trend.py`. Three facts about one pair of EMAs — where price sits against the slow one, which way the slow one is sloping, and which way round the two are stacked — each voting `+1`, `-1` or `0`, summed into an **agreement score** and cut by `min_agreement` into `DOWN`, `MIXED` and `UP`. One `int8` per bar rather than a wall of MA booleans, and `trend_filter` is a bitmask integer for exactly the reason `phase_filter`, `regime_filter` and `volume_filter` are.

**The memory switch is not switched on, and that is enforced rather than intended.** [#42] assumed the label would need `keep_values=True` on the sweep's shared moving-average grids — the 8-bytes-against-1 setting that is 285 MB of raw EMA values over the run below and grows with the period axis. It does not. `trend_grid` builds a values-carrying grid over *its own* two periods, reads the labels out of it and lets it go, so nothing outside that function ever sees an MA value and a parallel worker is handed the labels alone. Recomputing two EMAs costs milliseconds against the pass that would otherwise be paid per worker. Pinned as a property of a prepared dataset: asking for the label leaves `needs_ma_values` false, leaves every shared grid's `values` at `None`, and grows `Dataset.nbytes` by exactly the label arrays.

**The averages are the label's own, not the archetype's.** Reusing whichever periods an archetype happens to gate on would make the same label name a different measurement in each one, and a stratification that is not comparable across archetypes is not a stratification. The kind is fixed at EMA for the same reason — one definition, and `TrendKey` gains a field the day an SMA label is actually wanted.

**No label is ever taken off two components.** The slope cannot be measured for the first `slope_lookback` bars, and price and stack can. Letting those two decide would manufacture a trend out of a warm-up, so the score is `nan` there and the bar is `UNDEFINED` — five bars of 914,700 below, because the NT8 averages emit from bar 0 and this module adds no warm-up of its own. The components are still computed through it, since they are knowable and a review can report them.

**Both agreement boundaries fall in the outer bands, which is the opposite of [#40] and [#41].** Deliberately: `min_agreement` counts components that must agree rather than cutting a continuum, so exactly that many agreeing is the case the parameter names.

**And the parameter has two settings rather than three.** Two float64 averages are essentially never exactly equal, so a `0` vote essentially never happens and the score only ever takes odd values — `-3`, `-1`, `+1`, `+3`, and nothing else across all 914,700 bars below. `2` and `3` therefore produce identical labels; `1` is the distinct one, and what it does is abolish the `MIXED` band rather than widen the outer ones. Keep the parameter, because that switch is worth having, and do not read it as a resolution knob.

**Gated.** 12 of the 14 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the five added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added trend_filter trend_fast_period trend_slow_period trend_slope_lookback trend_min_agreement` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and the interesting number is not in the profit-factor column.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, EMA 20 against EMA 50 with a 5-bar slope and unanimity, one combination run once per trend:

| cell  | bar share | signals | trades | profit factor | win rate | expectancy |
| ----- | --------- | ------- | ------ | ------------- | -------- | ---------- |
| DOWN  | 37.2%     | 4,400   | 3,280  | 0.657         | 0.316    | −10.79     |
| MIXED | 18.8%     | 461     | 335    | 0.426         | 0.304    | −17.85     |
| UP    | 44.0%     | 28      | 24     | **1.815**     | 0.458    | **+14.27** |
| all   | 100%      | 4,889   | 3,639  | 0.640         | 0.316    | −11.28     |

**The UP row is 24 trades and it is not a finding.** It is the best of three cells chosen after looking, on the archetype [#48] exists to guard against exactly this on, and its own `DeadCatParams` already refuses to signal there: 4,400 of 4,889 signals fall on `DOWN` bars, which are 37% of the series. That is the row that matters. **The label is not independent of the gates it sits beside** — a short-only archetype filtered by close-under-EMA and close-under-SMA has already applied most of a trend filter, and stratifying it by one more measures the overlap rather than the market. The label earns its keep on the review, where the trades were not selected by these gates, and on an archetype that trades both directions.

**The decomposition is exact here on both counts, and only the signal one is guaranteed.** Signals sum to 4,889 against the unfiltered 4,889, and trades to 3,639 against 3,639. The signal identity is the property — no bar is undefined, so the three filters partition every one — while the trade identity is this dataset being kind: the simulation holds one position at a time, so removing an entry frees later signals and the trade-level sum is approximate in general, exactly as [#40]'s and [#41]'s were. Do not promote it to a rule.

**Cost.** 0.76 s to prepare over 914,700 bars, dominated by the two EMAs and the vote pass; 11 bytes per bar per label — one float64 score and three `int8` votes, 10.1 MB, against a 39.3 MB dataset without it. The per-combination gate is 0.16 ms. Every one of those figures is against the 285 MB the same run's shared grids would have carried had the label gone through `keep_values`.

**It does not close [#73], and the sequencing note on both issues is now settled.** This is a coarse trend read as a *condition*, computed on the 1-minute averages the project already has. [#73] is a *gate* on an average computed on genuinely coarser bars, it needs [#30]'s resampler, and its hazard — stamping from the current incomplete coarse bar — does not arise here at all. They are different things and both are still wanted.

**The fourth filter was one too many to keep copying.** All three signal functions ended with the same four-gate chain, and adding a fourth pushed two of them past the complexity limit — which is the lint rule doing its job rather than getting in the way. They now end with `sim/filters.py`'s `apply_context_filters`, one conjunction shared by every archetype and reached through a structural protocol, so the next condition is a single edit rather than three.

**Smaller choices in `trend.py`, recorded here rather than in the module ([#105]):**

- **Three states, not the eight a 3-bit composite would give.** Time of day already multiplies every other stratification, and the point of a *compact* label is to survive a minimum-stratum guard on a few hundred real trades. The components are carried separately for the review to report, which is where "*which* one dissented" belongs.
- **`UNDEFINED` is −1, not a fourth trend**, for the reason [#40]'s and [#41]'s are: it cannot be swept into a filter by accident, and it passes no mask including `ALL_TRENDS`.
- **A fast period that is not strictly shorter than the slow one is refused.** Equal periods make the stack permanently flat, and a longer fast period inverts what the label means without changing a single name — the kind of error that reads as a result.
- **The slope is a sign, not a magnitude.** A threshold on it would be in points, which is neither comparable across instruments nor across eras; the sign is scale-free and the agreement count already provides the coarseness a magnitude threshold would be reaching for.
- **Exact equality votes neither way**, so the flat case exists in the arithmetic even though float64 averages essentially never reach it. Cheaper than arguing about which side it belongs on.

### Multi-timeframe moving averages ([#73])

`nqbt/higher_timeframe.py`. An EMA computed on bars [#30]'s resampler aggregates, then stamped back onto the fine index so that a 1-minute strategy can gate on it. "Only short below the hourly trend" is standard practice and was not expressible before this, because every average the project computes reads the 1-minute close. Price against the coarse average is one `int8` per bar — `BELOW`, `AT`, `ABOVE`, `UNDEFINED` — and `higher_timeframe_filter` is a bitmask integer for exactly the reason `phase_filter`, `regime_filter`, `volume_filter` and `trend_filter` are.

**The projection rule is "the most recently *completed* coarse bar", and the boundary belongs to the completed side.** Both indices are end-of-bar, so the 1-minute bar stamped 19:00 and the 60-minute bar stamped 19:00 close at the same instant and the fine bar may read it; every fine bar strictly inside an unfinished coarse bar reads the one before. That is `searchsorted(..., side="right") - 1` and nothing else. The alternative reading of the ticket — lag the whole series by one bucket — was rejected: it throws away an hour of knowable information at every bucket close, and it is *not* the more conservative choice it looks like, because the existing 1-minute gates already compare `close[i]` against an `ma[i]` that includes it. One rule across both resolutions, not two.

**The hazard is not hypothetical and the test is built to fail.** `test_a_bar_inside_an_unfinished_coarse_bar_cannot_read_it` runs a series of three flat 5-minute buckets and then one whose *close alone* sits above the fine closes before it, with the period at 1 so the coarse average is the coarse close and every expected value is readable by eye. The four bars inside that bucket must read 100.0 and label `ABOVE`; a leak reads 150.0 and labels `BELOW`. Verified by introducing the leak — six tests fail, including the projection's own comparison against an explicit loop over the coarse stamps. **That loop is deliberately not a second `searchsorted`**: a test that re-derives the answer the implementation's own way cannot catch the implementation being wrong.

**`AT` is one bar in 914,700, and it is kept anyway.** Two float64 values essentially never coincide, which is the same finding [#42] recorded about a `0` vote — but "essentially never" is not "never", and giving equality its own state is cheaper than arguing about which side it belongs on. `UNDEFINED` is 59 bars, exactly the fine bars before the series' first 60-minute bar closes, and it passes no mask including `ALL_SIDES` — which is why each signal skips the gate entirely at the default rather than ANDing a no-op mask.

**Two validations that exist because their failure is silent.** A 1-minute higher timeframe is the existing moving-average gate under another name and is refused at the key. And a coarse resolution that is not a *proper multiple* of the bars it aggregates from is refused at the grid, against the frame's own resolution: asking for a 7-minute average of 5-minute bars buckets across bar boundaries and produces a number rather than an error. Both are checked whatever `higher_timeframe_filter` admits, so a nonsense resolution cannot ride along inertly until the filter is swept onto it.

**Gated.** 12 of the 14 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the three added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added higher_timeframe_filter higher_timeframe_minutes higher_timeframe_period` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**Cost.** 0.22 s to prepare over 914,700 bars on top of a 0.54 s baseline, one resample per distinct resolution however many periods share it; 9 bytes per bar per average — one float64 value and one `int8` side, 8.2 MB, against a 39.3 MB dataset without it. The per-combination gate is 0.44 ms. Nothing here touches `keep_values`: the coarse average is its own series, not a row of the shared moving-average grids.

**The stratification, and the reason it is more informative than [#42]'s was.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, a 60-minute EMA(50), one combination run once per side:

| cell  | bar share | signals | trades | profit factor | win rate | expectancy |
| ----- | --------- | ------- | ------ | ------------- | -------- | ---------- |
| BELOW | 40.9%     | 2,326   | 1,743  | 0.730         | 0.349    | −9.75      |
| AT    | 0.0%      | 0       | 0      | —             | —        | —          |
| ABOVE | 59.1%     | 2,563   | 1,895  | 0.528         | 0.285    | −12.71     |
| all   | 100%      | 4,889   | 3,638  | 0.640         | 0.316    | −11.29     |

**The signals split almost in proportion to the bars, and that is the point.** [#42]'s trend label put 4,400 of 4,889 signals on `DOWN` bars that were 37% of the series, because a short-only archetype already filtered by close-under-EMA and close-under-SMA has applied most of a 1-minute trend filter — stratifying by one more measured the overlap rather than the market. Here 2,326 of 4,889 signals fall on 40.9% of bars. **The coarse average is measuring something the archetype's own gates have not already applied**, which is what a higher timeframe was wanted for.

**No cell clears a profit factor of 1, so there is no finding to guard.** `BELOW` at 0.730 against 0.640 unfiltered is the better half of a bad strategy and is the best of three cells chosen after looking; the standing fact that DeadCatBounce is unprofitable across every combination tested is unchanged. What the run establishes is that the mechanism works and that the side is not collinear with the gates beside it — not that the gate helps.

**The decomposition is exact on both counts here, and only the signal one is guaranteed.** Signals sum to 4,889 against the unfiltered 4,889 and trades to 3,638 against 3,638. The signal identity is the property — `AT` is one bar and no signal falls on it, so the three sides partition every defined bar. The trade identity is this dataset being kind, exactly as [#40]'s, [#41]'s and [#42]'s were: the simulation holds one position at a time, so removing an entry frees later signals. Do not promote it to a rule.

**The three notions of "the higher-timeframe trend" are now separated rather than overlapping.** Here the strategy runs on 1-minute bars and *consults* a coarse average. [#42] reads a coarse *condition* off 1-minute averages. [#30] runs the whole strategy on coarse bars. All three share `nqbt/resample.py` and nothing else, and the sequencing note both tickets carried is discharged: all three were wanted.

**Smaller choices in `higher_timeframe.py`, recorded here rather than in the module ([#105]):**

- **The kind is fixed at EMA**, for the reason `trend.KIND` is: one definition, so the same parameters mean the same measurement everywhere, and `HigherTimeframeKey` gains a field the day an SMA average is actually wanted. [#72] made the fine gates' kind sweepable and deliberately did not reach here, so that day has not arrived.
- **The period counts coarse bars, never fine ones.** `higher_timeframe_period=50` at `higher_timeframe_minutes=60` is 50 hours, not 50 minutes. Naming it `period` rather than `bars` is deliberate: it is the same word `ema_period` uses, on a different series.
- **`UNDEFINED` is −1, not a fourth side**, for the reason [#40]'s, [#41]'s and [#42]'s are: it cannot be swept into a filter by accident, and it passes no mask including `ALL_SIDES`.
- **The average is projected onto every fine bar**, which is where this differs from `volume`'s baseline. A moving average is continuous across the maintenance break and across a session boundary — that is what makes it a higher timeframe — and the existing 1-minute gates do not special-case those bars either.
- **One resample per distinct resolution, whatever periods share it.** Two periods on the hourly cost one aggregation and two EMAs over a series 60 times shorter than the archive.

**The one question this cannot settle from Python, and why a trade list is the wrong tool for it.** NT8 serves a secondary series through `Closes[1][0]`, and *when* that series updates relative to a same-stamped primary bar is a property of its event ordering rather than of the arithmetic. **For an EMA the two readings are algebraically indistinguishable**: the update moves the average toward the close and never past it, so `close − EMA_new = (1 − α)(close − EMA_prev)` keeps the sign and the gate never flips. Over 914,700 MNQ bars at 5/15/60 minutes × periods 3/20/50 the label differs on exactly one bar in every configuration — the first coarse close, where the lagged reading is still in warm-up — and on zero bars where both are defined. A reconciliation would come back 100% and prove nothing. An **SMA** would: it drops the oldest value out of its window and can move past the close, giving 842 differing bars at 15-minute SMA(20), which is the case a coarse SMA would make live.

**So the instrument is a per-bar probe, not a trade list — and it has been run ([#183]).** `ninjatrader-scripts/Strategies/NqbtHigherTimeframeProbe.cs` records `Times[1][0]` against `Time[0]` on every 1-minute bar and writes the coarse series NT8 built beside it, so the boundary is decided on every coarse close rather than on the zero trades that would discriminate. Over `MNQ 03-24` with a 60-minute secondary series — 1,479,760 1-minute bars, 24,826 coarse bars — **the projection agrees on 1,479,701 of 1,479,701 comparable bars, and on all 24,752 coarse closes NT8 reads the bar stamped alongside the fine bar.** Seeding agrees exactly on EMA(3), EMA(50), SMA(3) and SMA(50); the warm-up is 59 bars against 59; anchoring is exact over the 1,525 coarse bars of the front-month window, the earlier prefix being NT8's merged series. Per-question figures: `docs/nt8-fidelity.md` § "And so is the higher-timeframe average".

**That the probe reports which *bar* was read, rather than what the average computed to, is what made it worth building.** The result does not depend on the arithmetic being monotone, so it settles the boundary for every moving-average kind at once and the SMA case above is answered without ever needing the trade list [#72] would have required.

`tools/reconcile_higher_timeframe.py` compares the export on all four questions separately, and `tests/test_reconcile_higher_timeframe.py` exercises each check against an export perturbed in the one way that check exists to catch — for the projection check, that perturbation is the other candidate rule. Two of its own defects were found by the real export and are pinned: reading `read_csv`'s microsecond stamps as nanoseconds put the whole comparison in 1970, the trap `resample.py` already records; and counting the warm-up over the *archive* rather than the probe's own bars compared 59 leading bars against 5 and called it a disagreement.

**The gate is checked whole, not only in its parts**: composing NT8's own close against NT8's own coarse EMA into a side reproduces `higher_timeframe_labels` on all 1,479,760 bars, the six `AT` bars included. A leg-for-leg trade-list diff would only re-exercise the conjunction and the bracket, which this change leaves byte-identical and which are already reconciled on other archetypes — so it is deliberately not planned rather than outstanding.

### M11 — manual trade review ([#44])

The stated goal. Import real trades, annotate each against the market context at its entry bar, stratify realised P&L by condition. The source is the **NT8 executions grid** ([#45]), not the Control Center log: `Position` gives trade boundaries (`-` = flat) and `Name` gives the exit reason (`Stop1..4` vs `Exit`). The log is rejected because its stop levels are ATM template defaults dragged to intent seconds later — in the sample, 29919 against a 29769 entry, computing 150 points of risk on a trade that actually risked ~14. Recovering intent would need a heuristic like "the first stop level that is not the template default", which is exactly the kind of rule that silently corrupts a dataset. **A wrong R is worse than no R, because it looks like a measurement**, so `r_multiple` is deliberately not reconstructed. The biggest annotation trap is back-adjustment ([#46]): it shifts historical prices by hundreds of points, so annotating a real trade against the continuous series succeeds at the lookup and is silently wrong at every comparison — use the raw or per-contract series. The statistical guard ([#48]) is not optional: a few hundred trades against a few dozen conditions is a multiple-comparisons machine, and a review without a minimum stratum size, a permutation test and a holdout is worse than no review, because it produces confident, specific, wrong conclusions that feel earned. All three are `nqbt/guard.py`, and the correction that matters is family-wise rather than per condition. Free-text notes are stored but structurally excluded from evaluation ([#49]) — written knowing the outcome, they would yield perfectly circular findings.

#### M11.1 — Import: the NT8 executions-grid adapter ([#45])

`nqbt/trade_import.py` is the only format-aware code in the project, and adding a second source is meant to be one more function rather than a second pipeline. The grid is exported from Control Center → Executions; `tests/test_trade_import.py` carries a real export verbatim as its first fixture, so every claim below is pinned rather than remembered.

**Ties are ordered by the position chain, never by file order.** The export is newest-first, so reversing it gives chronological order — but that is not sufficient, and the counter-example is two real exports of *one* history taken a day apart, which carry the same two fills at `2:30:42 PM` in **opposite** order. File order is therefore not a dependable tiebreak, and sorting on the timestamp is worse. `Position` is dependable: it is the running position *after* each fill, so within a tied group each fill's value is the previous one plus its own signed size, and the chain has exactly one arrangement. The adapter reconstructs it, which also makes the walk a whole-file consistency check — a missing fill cannot be bridged, and is refused rather than silently absorbed.

**The date order is never inferred from the values.** Row timestamps are `DD/MM/YYYY`; the `Time=` field inside Control Center *log* messages is `M/D/YYYY`, and the first twelve days of any month parse to a real but wrong date under the other reading. Two formats are accepted and each is tried over the whole column, but both are day-first: NT8's 12- versus 24-hour clock is a display setting, whereas the date order is not something a value can be asked about.

**The timezone is required configuration, with no default.** The file carries none, and a wrong zone shifts every trade by hours without erroring. `Europe/London` is right for this machine — converting the sample's fills to UTC puts every one inside its bar's high/low range — but that is a fact about the machine, not a property of the format.

**Legs are FIFO matches, not fills.** NT8 matches a partial exit FIFO, and the schema is per leg, so each pairing of an entry lot with an exit fill is one row. The distinction is invisible in the total and decides every row: the sample's first trade has two entry lots at different prices, and averaging them reproduces the trade's P&L exactly while getting all three legs wrong. A fill that crosses zero falls out of the same matcher as two trades, which is what `stats` already assumes a flip to be.

**Costs come from the project and never from the file.** `Commission` reads `$0.00` on an account that is charged, so `commission_per_contract` defaults to `costs.LIVE`'s figure here — deliberately the opposite of the simulator's zero, which is correct only for reconciling against a Strategy Analyzer run. Slippage is not applied at all: a real fill price already contains it.

**What the source cannot supply is null, named, and refuses to be summarised.** `UNPOPULATED` is exactly `trades.NULLABLE` and carries a reason per column, because the review has to *state* why it omitted a statistic ([#48]). The absent integer columns keep a nullable dtype rather than a NaN-filled float one, so `stats.summarise` raises on an imported log instead of returning a bar count nobody measured. Refusing is only half of the fix; omitting with the reason is [#48]'s job, and [#81] is the same hazard reached through times.

**Coverage is measured per trade and whole trades are excluded together.** Whether a trade's contract and dates are cached is a report the importer emits, not an assumption, and a trade straddling the edge of the cache is set aside entire — half its P&L reviewed and half excluded would misstate the trade itself. Nothing is dropped: `covered` is a column, and `reviewable` is the subset a review may be computed over. The export lags live by roughly two hours, so the newest session is routinely uncovered and that is a normal reading rather than a fault.

**Both ends of an export can hold a trade that is not a trade.** Fills before the first flat position belong to a trade that began before the window, and fills after the last flat belong to a position still open. Both are dropped and both are counted, so "some trades are missing" is always visible as a number.

#### M11.2 — Annotate: the market context at a trade's bars ([#46])

`nqbt/annotate.py` joins a trade log to a `Dataset` and returns one row per trade carrying every condition that dataset holds. It knows nothing about where the trades came from, which is the point rather than a nicety: [#44]'s payoff needs the identical breakdown over a sweep's log and over a real history, so a hypothesis raised on a few hundred real trades can be tested against thousands of simulated ones.

**Annotate against the per-contract bars, never the back-adjusted series.** Back-adjustment shifts every historical price by the cumulative roll offset, so a real fill at 18076.75 appears nowhere in the continuous series — and **the lookup still succeeds**, because a timestamp is a timestamp. What comes back is plausible at every stage and wrong at every comparison. The defence is not documentation: every fill price is checked against the bar it matched, and an excursion is refused rather than ranked. That is the cheapest guard in the project. `contract_bars` exists so that reaching for the right series is easier than reaching for the wrong one, and it excludes the *raw* continuous series too, which splices two contracts' prices across a roll. The live roll offsets are `nqbt splice --diagnostics`; they are hundreds of points over the window this review covers, which is why a tick of tolerance cannot admit one.

**`price_tolerance` is in points and defaults to zero.** A real fill is inside its bar by construction. A *simulated* one need not be: a stop that gapped fills at the bar's open, moved by the run's slippage, which is a tick or two outside. That is the only legitimate excursion, so it is a number the caller states rather than slack the check carries.

**A fill belongs to the bar stamped strictly after it**, so the bar stamped `s` covers `[s - bar_minutes, s)` and a fill at 14:23:47 is in the bar stamped 14:24. The boundary decides more than it looks: the executions grid prints whole seconds, so a fill printed at 14:24:00 happened somewhere inside the second beginning there and belongs to the bar stamped 14:25. Confirmed end-to-end on the sample — converting the eight fills to UTC and mapping each this way puts every one inside its bar's high/low range, with the 17:00:29 stop landing exactly on the 17:01 high.

**A bar's own stamp is not a fill time, so a log that carries bar indices keeps them.** The simulator writes `entry_bar` and an `entry_time` that *is* `index[entry_bar]`; resolving that timestamp under the fill rule would move every simulated trade one bar forward, and nothing downstream would look wrong. Where a log carries both, the two are cross-checked, which is the one test that catches a log being annotated against a different series of the same shape — another contract, or the same bars at another resolution.

**A trade matches whole or not at all**, across every leg and at both ends, whether or not the exit side is being annotated. Half a trade's context recorded and half discarded would misstate the trade itself, and it is the rule [#45] already applies to coverage. Nothing is dropped: `matched` is a column and `reviewable` is the subset a review may be computed over. One level down, a fill inside a hole in the bars is unmatched rather than joined to the next bar, because the next bar is not the bar it happened in.

**Raw series always, labels only where the thresholds were chosen.** An efficiency ratio is a fact about a bar and a regime is a cut through it, so `LabelThresholds` has no defaults and takes each pair or neither. [#48]'s guard has to be able to state which cut it tested, and a default would let a review report a threshold nobody picked. Every column is held as a nullable dtype chosen from what it holds rather than from whether anything is missing, so an unmatched trade's condition cannot read as `False`.

#### M11.3 — Review: stratifying realised P&L by condition ([#47])

`nqbt/review.py` groups one trade log by one condition at a time and reads a `stats.summarise` over each group. **Nothing in it defines a statistic**, which is the whole point of M9: a review computing its own win rate would eventually disagree with the sweep's, and the disagreement would be invisible because both numbers would look reasonable. A stratum's row is therefore literally the summary's fields, and `tests/test_review.py` asserts a row equals `summarise` over exactly that stratum's legs.

**Time of day is reported first, and paired with both forms of volume.** It is the stratification most likely to show real structure in a discretionary record, because it captures attention, liquidity and the trader's own routine at once, and unlike a moving-average gate it is not something the trader was consciously optimising. Both forms of volume travel with it because neither answers the question alone: relative volume is normalised per bar of session by construction ([#41]) and says whether a bar was unusual *for the time*, while the absolute count says whether there was anything there to trade at all. "This hour is always busy" is a high absolute median beside a relative one near 1; "this hour was unusually busy" is the relative median moving. Phases print in session order rather than alphabetically, which is the one ordering error that would pass every other assertion.

**The final phase is an artefact until it is separated from the clock.** It contains the session-close flatten ([#16]), so a time-of-day stratification will always show it as anomalous. The report carries `session_close_share` per phase for exactly that reason — and omits it, rather than printing zero, when the log's exit reasons are its source's own vocabulary instead of the simulator's, because an imported grid's `Name` field cannot name the clock and a zero would read as "none of these were closed by the clock".

**Only a categorical condition is a stratification.** A raw series is excluded rather than bucketed: where to cut it is the review's most consequential decision and `LabelThresholds` is where a review states the cut it tested, so a default here would let a report claim a threshold nobody picked. The rule is dtype plus cardinality — a float column is a series, one value separates nothing, and past a dozen values the split is a list of trades rather than a comparison. The report says how many conditions it could not cut by, so an excluded condition is visible as a number rather than as silence.

**A log that leaves a column empty omits the statistics that column feeds, in the producer's own words.** `summarise` refuses an imported log rather than reporting a bar count nobody measured ([#45]), which is the correct half of the fix; the other half is this module's, and the wording comes from `trade_import.UNPOPULATED` rather than being reinvented here. Mechanically the absent columns are filled with a placeholder so that `summarise` runs at all, and every field a filled column feeds is dropped by name before a row is built — so **no placeholder can reach a reported number**, which is a property a test pins rather than a convention held in someone's head. The mapping from column to fields is data (`STATISTICS_FROM`), so an absent `r_multiple` costs the R statistics and nothing else.

**The separation is a range across strata, and it is a candidate rather than a finding.** Conditions are ranked by how far the chosen statistic sits between their best and worst reported stratum, over strata meeting a minimum sample — the floor `sweep.rank` already enforces, for the same reason: the smallest samples produce the most extreme statistics and would otherwise lead every ranking. A stratum under the floor is still reported, and marked. An infinite profit factor, which a stratum with no losing trade reports, is dropped from the range rather than allowed to top it.

**What [#48] owns.** The minimum stratum is one of its three mitigations. The permutation test against shuffled condition labels and the recent-trades holdout are `nqbt/guard.py`'s, and `review.STATUS` names it, because the failure mode here is not a wrong number but a right number read without its context — and that number would feel earned.

#### M11.4 — The statistical guard ([#48])

`nqbt/guard.py` is what stands between a stratification and a confident wrong conclusion, and the reason it is not optional is arithmetic rather than caution. A few hundred trades against a few dozen conditions is a multiple-comparisons machine: **some condition will split that sample impressively, and most of the time it will be noise.** A review without this is worse than no review, because what it produces is specific, confident and wrong, and feels earned.

**The minimum stratum was already there, and is one third of the guard.** [#47] enforces the floor `sweep.rank` enforces, for the same reason, so this module imports it rather than restating it.

**The permutation test shuffles the P&L and leaves the strata alone.** Every stratum keeps the size it had and only the association is destroyed, which is the null the question actually needs: *would labels that carried nothing have split these trades this far?* Mechanically the trades are sorted into contiguous strata once and each draw is a `np.split` of a permuted vector, because `summarise` per stratum per draw is two orders of magnitude too slow — the same move, for the same reason, that `stats.trade_statistic` was added for in [#31].

**The correction is a maximum over one shared shuffle, not a Bonferroni.** A per-condition p-value answers the right question only for a condition chosen for a reason; taking the widest separation on offer and reading its p-value is the same machine one level up. So each draw permutes the P&L once, every condition is re-separated under *that* permutation, and the maximum across them is the family's null — a max-statistic correction, which is far less harsh than Bonferroni precisely because conditions measured over the same trades move together, and these do. `tests/test_guard.py` demonstrates it on a dozen conditions drawn from nothing: the best of them is unremarkable against the family and would have looked publishable alone.

**A screen narrows to the trades every condition labels.** A maximum is only meaningful over comparable numbers, and conditions measured on different subsets are not comparable. The count set aside is reported rather than absorbed, which is the rule [#46] already applies to a trade that matches only in part.

**A separation may only be measured in a rate.** `STATISTICS` is `review.REPORTED` intersected with `stats.TRADE_PNL_STATISTICS`: outside the first a statistic is not one the review printed, outside the second it cannot be had from a P&L vector and thousands of draws would be unaffordable. That drops `net_pnl` for a third reason that would have applied anyway — a sum separates strata by how many trades they hold.

**The holdout re-reads the split; it never re-chooses it.** The best and worst strata are picked on the earlier trades and then evaluated on the most recent ones as they stand. Picking again on the recent trades would hold nothing out and would return the in-sample answer wearing a different name. The share defaults to a quarter rather than a fixed count because both halves have to clear the floor and the sample size is not known in advance.

**What the guard still cannot say**, and the report says so itself:

- **A null is not a cause.** A small p-value says the split is unlikely if the labels carried nothing. It cannot say the cause is this condition rather than something travelling with it — and time of day travels with almost everything ([#43]).
- **The family is the conditions in *this* screen.** Not the ones tried in an earlier one, and not the threshold a raw series was cut at: a `LabelThresholds` pair chosen after looking is a comparison the screen cannot see. That is why [#46] refuses to default one.
- **The holdout's two halves are not independent samples.** What is held out is the *choice* of strata, not the trades — they are inside the screened sample. And its strata are small by construction, so `reported` is usually false on a few hundred trades and the row is a direction check rather than a measurement.
- **It guards a review, and the same argument binds [#31] and [#24].** The best of nineteen contracts, and a ranking over archetypes × combinations × resolutions × contracts, are the same machine with more cells. The array-level functions take a P&L vector and one label per trade for that reason; `dispersion.spread_vs_resampling` is the contract-shaped instance built first.

#### M11.5 — Discretionary context ([#49])

`nqbt/notes.py` stores what a trade log cannot: why a trade was taken, what was going on at the time, a screenshot to look at later. It is kept, it is shown, and it is never an input to annotation, stratification or the guard.

**The exclusion is enforced rather than intended, because the finding it would produce is guaranteed rather than merely likely.** A note is written after the fact, knowing the outcome, so a loser attracts "I was impatient" and a winner attracts "clean setup". Stratifying by one would rediscover the outcome and report it as structure — and it would be the widest separation in the report and the most impressive-looking result in it. Nothing downstream could tell that from a real one, because every number in it would be correctly computed.

**A note column would pass every filter the review already has.** `review.stratifiable` excludes a raw series by dtype and a split by cardinality, and free text is neither a float nor high-cardinality on a small sample — three recurring phrases across thirty trades is exactly a stratification's shape. The rule therefore cannot rest on a note failing to look like a condition, and `tests/test_notes.py` pins that it does look like one.

**Structurally that means a sidecar and three doors.** Notes live in a frame keyed by `trade_id` and never as columns on a trade log or an annotation, so there is nothing to group by; an annotation's conditions are read off the bars, which leaves a log column no route into one in the first place. `notes.check_excluded` is called by `annotate.annotate_trades`, `review.review` and `guard.guard` and refuses free text at each. `notes.alongside` is the only join that attaches a note to anything — for the trade-log viewer ([#52]) and for a per-trade export — and it refuses a frame already carrying one, so a joined frame cannot travel onwards.

**A duplicate key is an error rather than a last-one-wins.** Two notes on one trade fan a join out into extra rows, and extra rows that look like more of the same data move every number computed over them.

**Worth revisiting only for deliberate qualitative coding** — a fixed set of categories chosen *before* any outcome is examined. That is a different activity from what M11 does, and it would be a different column with a different provenance rather than this one relabelled.

### M12 — web GUI ([#52])

Long term, and gated on the review's outputs being stable or the interface churns with them. **The governing lesson is the CLI's:** `nqbt sweep` and `nqbt report` were dropped because they would have been a second, lossier front door to things the Python API already does better. A GUI carries the same risk at ten times the size, so it must call the same functions and define no statistic of its own. Streamlit for the read-only views, explicitly as a throwaway, rather than starting with FastAPI and discovering the front end is the whole project.

### M13 — bar resolution as a sweep axis ([#30])

**The existing 1-minute archive is sufficient — no re-export, no AddOn change.** OHLC aggregation is associative, so a 5-minute bar built from five 1-minute bars is *bit-identical* to one NT8 builds from ticks; reaching for `data/tick/` would be the more-precise-than-NT8 error the prime directive forbids. The trap is anchoring: bucket by **minutes since the session open**, never wall clock. For the periods anyone actually sweeps this is harmless, and **that coincidence is exactly why it must be tested rather than assumed**. The precise condition was established while building [#30] and is sharper than the one this file used to state: agreement needs a boundary at the session *open* **and** its *close*, so with 18:00 ET at 1,080 minutes past midnight and 17:00 ET at 1,020, it is `N | gcd(1080, 1020)` — **N divides 60**. Dividing 1,080 alone is not enough: 45 does, and still diverges, because a wall-clock grid then runs a bucket from 16:45 to 17:30 through the maintenance break. Whether NT8 anchors the same way is settled by the *existing* Tier-2 reconciliation at that resolution, not by importing NT8's coarse bars. Resolution changes the strategy, not just the sampling — order lifetime, the ratchet and `bars_required_to_trade` are all per-bar — so it must be a first-class results column, and comparing profit factor across resolutions at the same period number is meaningless. Expect the ambiguous-bar rate to climb well above 1-minute's 3.4%; **if a coarse resolution looks profitable, check that first.** Cost is self-limiting: 1, 2, 5 and 15 minutes is ≈1.8× a 1-minute sweep, not 4×.

Three further conventions `nqbt/resample.py` implements, recorded here rather than in the module ([#105]):

- **Timestamps are end-of-bar**, so a bar stamped 18:01 is the session's *first* minute and a bucket covering 18:00–18:05 is stamped 18:05. A bar at minute *m* therefore *occupies* index *m − 1*; off by one there is invisible at 1 minute and wrong everywhere else.
- **The final bucket of a session is stamped at the observed last bar, not the theoretical end.** Two cases need it: a period that does not divide the session (7 would put the last bucket's end past the 17:00 close) and a holiday early close. Deriving it from the data is the same choice `is_session_close` makes, and it avoids the trap [#68] records against `force_flat_mask`.
- **`minutes=1` returns the frame unchanged, and `minutes >= 2` drops out-of-session bars.** The identity is not merely an optimisation — the 1-minute path is what every reconciliation and every captured trade log was produced against, so resampling must not perturb it even by dropping a row. A stray out-of-session print has no session to be anchored to and so no bucket it could honestly join. Since [#160] the filter is belt-and-braces on a frame from `load_contract` or `build_continuous`, both of which have already dropped them.

Because the grouping key includes the trading day, no bucket can span the 17:00–18:00 maintenance break or the weekend. That falls out of the anchoring rather than needing its own rule.

### M14 — per-contract sweeps ([#31])

**`nqbt/dispersion.py` has landed, and [#28] has since absorbed its loop.** `sweep_contracts` is now a wrapper over `sweep.sweep_axes` that keeps what this module is actually for — the front-month windows, the coverage join, and the statistics below — and moves `contract` back to the leading column because that is its own promise. All 48 tests here passed unchanged through that refactor, which is the evidence it moved nothing.

Two things the build settled that are worth not relitigating. **Both spread measures are reported, because the milestone has two jobs that disagree** — the IQR answers "does the bulk of contracts differ?" and the range answers "is any one contract extreme?", which is the data-integrity question below. Reporting only the robust measure would discard the signal this milestone is most useful for, and a test pins that a single rogue contract moves the range while leaving the IQR alone. And **`stats.trade_statistic` was added rather than a second profit-factor implementation** — the permutation test needs thousands of evaluations and `summarise` is too slow, so the fast path shares `_ratio` and a test asserts exact equality with `summarise` on real logs. That is the same discipline [#33] went on to apply to the numpy-native summary path, worked out here first because this is where it became necessary.

**The first result is the argument for the framing.** DeadCatBounce's per-contract variation on MNQ is indistinguishable from relabelling the same trades, on both measures, even though the best contract reads roughly double the worst.

**How the permutation test is built, and what it does not say** ([#105]):

- **A permutation, not a bootstrap.** Contract labels are shuffled over the *same* set of trades, keeping every group's count exactly as observed — cut points rather than resampling, so the null cannot mix a spread effect with a sample-size effect. That answers the only question the raw spread poses: if which contract a trade happened in were arbitrary, would the contracts still look this different?
- **Trades are permuted whole.** Each contract's legs are collapsed by `stats.per_trade` first, so a trade's legs cannot be split across two groups and invent trades that never happened.
- **`by` is restricted to `stats.TRADE_PNL_STATISTICS`.** Permuting destroys entry and exit times, so Sharpe, max drawdown or consecutive losses would be computed over an ordering that never happened. Refusing is better than returning it.
- **A small p-value means "not obviously noise", never "a real per-contract effect".** Permutation destroys serial correlation and within-contract regime persistence, so the null has *less* spread than reality and the test **over-rejects**. It is a floor on scepticism, not a verdict. The stronger version — block resampling that keeps runs intact — shares machinery with [#50] and belongs there.
- **`dispersion()` returns rows in `combo_id` order and a test fails if that changes.** Sorting by the median would hand back the leaderboard the milestone exists to refuse; reaching for the best row has to be deliberate, and then the caller owns the multiple-comparisons problem. `contracts_dropped` is as informative as the spread — a combination clearing `min_trades` on three of nineteen contracts has not been measured across contracts at all.
- **`MIN_TRADES` is 30 because noise has the widest spread.** A profit factor from a handful of trades does not merely add uncertainty to the dispersion, it dominates the quantity being measured. Small contracts are still reported, just excluded from the spread.

**What this is not: a contract is a ~3-month bucket, so it surfaces regime shifts, not events.** An election or a CPI print is a day or an hour, and averaging it across a quarter dilutes it to nothing. For events the tools are the regime and time-of-day labels ([#40], [#43]) plus a date filter.

The original reasoning follows, and still holds.

`sweep.sweep()` already accepts a single contract's frame, so what was missing is the cross-contract table, a `contract` column, and the framing. **Report the spread, not the winner:** a contract is ~3 months of front-month, so "best contract" is very nearly "best quarter", and picking the best of 19 × N combinations is the multiple-comparisons trap §11.4 guards against. The useful output is how much performance varies and whether that variation exceeds what resampling the same trades would produce. Three things it does that M7's time-slicing does not: it is a **data-integrity instrument** (an outlier contract is usually a bad roll date or a hole, not a market insight, and given how much archive work came from exactly such defects it is a cheap standing check); it uses **raw, not back-adjusted** prices, which is the only way to test round-number stops; and it contains **no roll**, so it is directly Tier-2 reproducible — the cheapest route to the outstanding NQ reconciliation ([#66]). Default to the **front-month window**; full contract life overlaps its neighbours and double-counts calendar days. Report `bars`, `sessions` and `trades` per contract, or a PF from 30 trades sits in the same column as one from 400.

### ~~M20a~~ — the three findings that blocked M15: done ([#9])

**`bracket.resolve_brackets` is the single bracket implementation.** Until M20a it existed twice: once for a bar while in a position and once, textually independently, for the bar an entry filled on. The two were behaviourally equivalent — the entry-bar copy dropped the `leg_open` guards because every leg had just been opened, which makes them no-ops rather than a difference — but every rule the 1143/1144 NT8 reconciliation validated appeared in both, so there were two places for Tier 1 and Tier 2 to drift and the reconciliation only ever covered one of them. Unifying it is what let M15 multiply *one* copy by its direction sign: the short-only byte-identity gate cannot catch a sign applied inconsistently across two copies, because at `d = −1` both reduce to today's code whether or not they agree at `d = +1`.

**`bracket.entry_bracket` is the single trigger/stop/risk computation**, called by the `@njit` loop and by `explain.py`. It too used to be written out twice, and the two copies disagreed: the audit trail took the trigger to be simply `Low[0]`, dropping the `Close[0] − 2 ticks` cap the simulation applies. So `nqbt run --explain` — the tool a human uses to tick a trade off against a chart before trusting anything downstream — reported the wrong `trigger`, `risk_points`, `risk_ticks` and `fill_type`, while agreeing on the stop, which is what made it look right on inspection. The audit trail is now by construction the arithmetic under audit.

**The 50% figure that justified that fix was a prefix, not a rate.** Measured over the whole window the cap binds on roughly a **third** of signals; it reads far higher over the first twenty trades and decays from there, because capped signals are not evenly distributed. **Quote whole-window rates** — a prefix of a trade log is not a sample of it. The defect was real either way.

**`Summary.empty()`** replaces a splat that put 26 arguments into a 28-field dataclass and raised on every call, which went unnoticed because the only caller had grown a second, divergent empty-log policy of its own. `sweep.run_combination` no longer keeps one.

Two things M20a deliberately did **not** change, because M20 may not move a number: `stats.py`'s silent branch computing Sharpe and Sortino per trade rather than per day for a log with no times ([#81]) — unreachable today, same shape as the empty-log defect — and `verification/explain_2024Q1.csv`, annotated rather than regenerated, because it is the record of what the audit trail said while it was being trusted.

### M8 — bar-major restructuring: measured, and not scheduled

`sweep.py` is **combo-major**: build the dataset once, then loop combinations and run the whole jitted simulation over the whole series for each. That is the straightforward shape, and it was chosen for correctness first — a bar-major restructuring would reuse cache better across combinations at a real complexity cost, which had to be justified by profiling rather than assumed.

It was, and the premise came back mostly false. Profiling one combination over 1.65M bars put `stats.summarise` at 51%, `trades_to_frame` at 20%, the `@njit` loop at 23% and the signal ANDs at 2%. Bar-major restructures the 23%, so making the simulation *entirely free* was worth about 1.3× — Amdahl caps it there. [#33] took the 71% instead, and a combination is now 9.0 ms against 28.3 ms, of which 9.3 ms is the loop.

The ceiling is unchanged and the loop's share of a combination is now most of it, so **M8 is still not scheduled**: re-profile before believing any figure here, and do it only if the loop is genuinely what a real sweep is waiting on.

### M20b — typing and tooling ([#53])

**Done.** `ruff` and `mypy` both report zero on `nqbt/` and both gate CI; `CONTRIBUTING.md` §"Linting and typing" is the rule and the workflow is the live check. What is recorded here is the reasoning that outlives the counts.

**The gap that mattered was dtype, not coverage** ([#54]). The package annotated well and none of it was checked, so a bare `np.ndarray` read as a type while saying only "some array" — and here the element type is load-bearing. `MovingAverageGrid.below` is bool where `.values` is float64, which is the whole 66 MB against 595 MB decision; `SessionInfo.trading_day` is `datetime64[D]` where `.in_session` is bool; and the `@njit` loop's `out` is a float64 matrix into which `exit_reason` and `direction` are written as floats and mapped back to strings later, the one place a wrong dtype is silently lossy. `nqbt/arrays.py` names each dtype once and `tests/test_array_dtypes.py` asserts the arrays really carry them, because an annotation nothing checks is worse than none. **Do not annotate inside an `@njit` function expecting numba to use it** — it infers from the call, ignores the annotation, and a wrong one reads as a guarantee.

**Locals carry their type too, and mypy is what says they are right.** The signatures were already annotated; the bodies were not, so a reader had to re-derive from the expression what the signature stated once. Roughly 750 locals now name their type, derived from what mypy itself infers rather than from reading each expression, and the two constraints that shaped where they do not are worth keeping: a name can be annotated only **once per scope**, so the first binding is the declaration and one bound in two arms of a branch is declared above it; and `AnyArray` is a concrete `dtype[generic[object]]` rather than a wildcard, so annotating a local with it type-checks at the assignment and fails at every use after it.

**The stubs are still not the runtime.** mypy proves an annotation is consistent with the stubs, which is what `DateArray` was before numpy 2.5. So the 178 array-alias locals were also checked the other way, by instrumenting a throwaway copy of the package with a dtype assertion after each one and running the suite over it — all 178 match. `OffsetArray` is the one alias this pass added: `np.intp` is what `flatnonzero`, `argsort` and `searchsorted` return, and it is not `int64` on every platform, so `IntArray` would have been a promise the package cannot keep.

Three decisions the configuration now carries, each with its reason beside it in `pyproject.toml`:

- **`D401` is off.** It wants an imperative verb where `CONTRIBUTING.md` says a docstring names *what* a thing is, which is a noun phrase. The two rules cannot both hold.
- **`max-args` is 10, not ruff's 5.** An entry point taking one keyword per choice its caller must state is the shape of this codebase. What is left above ten is the parameter blobs [#59] fixes, and each of those carries its own `noqa` naming the issue — so the rule still points at the real problem instead of being blanket-disabled.
- **numba has no keyword-only arguments**, so a jitted loop's toggles are positional booleans and `FBT001`/`FBT003` are ignored for exactly the five modules that contain one — per file rather than per line, because a jitted module's every toggle is one and an inline `noqa` at each of the 27 sites would say the same thing 27 times.

`Any` survives where it is the honest type — a condition's labels are whatever pandas holds them as, an archetype's `run`/`legs`/`signal` differ in signature per archetype — and every such site says so. joblib is the one untyped import: three symbols in one function did not earn a stub under `mypy_path`.

**The order was the point.** A type checker introduced with a strict config and hundreds of errors gets switched off, so both tools reached zero *before* the CI job that enforces it existed, in a separate commit each.

**The stubs move under you, and a clean local run does not prove a clean CI run.** `DateArray` was `NDArray[np.datetime64]` and type-checked against the numpy in the venv; CI installs the newest, and numpy 2.5 changed that parameter's default from `dt.date | int | None` to `Any`, so the alias smuggled in an explicit `Any` and the new gate failed on a machine nobody had run. Every alias that could carry a defaulted parameter now states it.

**The fix was to stop letting the resolver choose.** Every dependency and dev dependency is now pinned `==` rather than `>=`, so a local zero and a CI zero are the same measurement; dependabot raises the bumps and each is tested like any other change. The failure mode that forced it is worth keeping in mind whenever a pin is loosened: CI resolves fresh, one minor version behind locally is enough to hide a failure, and `extend-select = ["ALL"]` gives ruff the same reach — a release that adds a rule fails a build nobody touched.

### M20c — structural cleanups ([#58])

Worth doing when adjacent rather than as a project. **~~Parameter blobs~~ ([#59]) — done.** `simulate_deadcat` took 23 parameters and `_write` 18, all passed positionally, where one transposition writes plausible numbers into the wrong columns. Every loop now takes at most ten arguments, and the seven `NamedTuple` blobs they travel in live in `nqbt/sim/bracket.py`. Two groupings are worth more than the argument count: `Bars` carries `force_flat` beside the OHLC and `resolve_brackets` indexes it at the `i` it was given, so a bar can no longer be split across callers; and `OpenTrade.filled_at_open` replaces the `held_from_bar_open` flag each call site used to assert for itself.

The Numba question was **measured, not assumed**, and `tools/numba_tuple_probe.py` is what measures it: bit-identical result, 1.01× the scalar version over 5M iterations, arrays inside a blob compile, and the disk cache is reused. That last claim had to be tightened. **A blob defined in `__main__` writes a cache and then misses it on every run, silently** — the probe originally checked only that `cache=True` raised nothing at definition, which is a weaker claim than the one parallel workers depend on. It is why the blobs live in an importable module rather than beside the loops that read them, and the probe now demonstrates both halves.

The rest, in descending order of value: `sweep.SWEEPABLE` reads `__slots__` rather than `dataclasses.fields()` ([#60]) and will break quietly at M17 by dropping an axis rather than raising; `results.best()` interpolates `by` into SQL ([#61]); `bars[...].to_numpy(np.float64)` appears 12 times ([#62]); and `explain.py` and `cli.py` are untested ([#64] — `explain.py` gained `tests/test_explain.py` during M20a, so this is now `cli.py` alone).

**~~The third profit factor~~ ([#63]) — done.** `_cmd_run` reimplemented `per_trade`, profit factor and max drawdown inline; it now calls `stats.summarise` and reads the fields off, with `_log_run` printing and computing nothing. **The corner the two definitions disagreed in is settled in `stats`' favour**: a run of nothing but scratches reported an infinite profit factor from the CLI and `0.0` from `_ratio`, and now reports `_ratio`'s. Nothing else moved — the command's output over the whole MNQ history is identical before and after, which is the check worth repeating on the next one of these, since the reimplementation had drifted in a place no test looked. **Resist adding classes beyond the parameter blobs and M17's protocol**, and specifically resist `numba.jitclass` inside the loop: it carries real compilation and boxing costs, and the loop is 23% of a combination, so there is nothing to win and fidelity-critical code to lose.

### Moving-average axes — what is sweepable and what is not

**Already sweepable, jointly, with no work needed:** every field of `DeadCatParams` except `target_r_multiples` is a legal axis, periods and on/off toggles alike, and `Grid.dead_axes()` refuses a period axis whose toggle is off in every combination. Both of the dimensions this section was opened for are now reachable. **~~Multi-timeframe MAs~~ ([#73]) — done**, and the trap it names is discharged in § "Multi-timeframe moving averages" rather than here: `nqbt/higher_timeframe.py` stamps a coarse EMA from the last *completed* coarse bar, and the test that would fail if the current one leaked is named there. **~~MA kind as an axis~~ ([#72]) — done**, and it was as cheap as the ticket predicted once [#19] and [#27] had landed.

### Moving-average kind as a swept axis ([#72])

**Every gate carries a `<gate>_kind` beside its `<gate>_period`**, defaulting to the kind the NinjaScript hardcodes, so "what if the fast filter were an EMA rather than an SMA?" is now one axis. `ContextSpec.ma_keys` is a tuple of `(kind, period)` pairs in place of the two kind-specific period tuples, `Dataset.mas` was already a grid per kind, and `archetypes._ma_keys` crosses each gate's two axes so a sweep builds exactly the grids some combination could read. Grid cost is linear in the number of kinds, and every default is unchanged: the trade-log gate is byte-identical on 12 of 14 files, the two sweep summaries differing only by the three added parameter columns.

**The gates keep their NinjaScript names, and `ema_kind="wma"` is the price of that.** Renaming `ema_period` to something neutral would have broken the rule that a name mirroring a NinjaScript property keeps NT8's word, and would have renamed columns in every stored results table. The awkward reading is deliberate: the gate is named after what `DeadCatBounce.cs` computes into it, the kind says what this simulation actually computes.

**Two new kinds, and the third is the one that needs NinjaTrader.** `nt8_wma` and `nt8_hma` are transcribed from NT8's own `@WMA.cs` and `@HMA.cs`, which are on disk under `bin/Custom/Indicators/`, and pinned against hand-computed values from that source rather than against an export — a class weaker than the M16 indicators, and recorded as such in `docs/nt8-fidelity.md` § "WMA and HMA, ported from the NinjaScript rather than reconciled". **VWMA is deliberately not here**, and the reason is the second half rather than the first. Volume is not missing — `prepare` already reads `bars["volume"]` for the session VWAP — so carrying it into a grid is a signature change, `MovingAverageKind.compute` being `(values, period)` over a single series. What needs NinjaTrader is that `@VWMA.cs`'s two branches disagree during warm-up rather than merely rounding differently, so picking one from the C# alone would be guessing at exactly the seeding question the EMA and the ATR were each caught by. That is a probe's job, not a port's.

**A kind sweep used to need a fresh results database, and nothing said so.** `_append_or_create` wrote `combos` by name and dropped a column the stored table did not already have, with only `AXIS_COLUMNS` migrated in — so appending a kind sweep to a database written before [#72] silently lost `ema_kind`, `fast_sma_kind` and `slow_sma_kind`, leaving rows that differed only by kind indistinguishable. That was the standing rule for any new parameter column rather than something this change introduced, but it was the first parameter whose *absence* changed what a row means, and it is why [#201] made widening the general answer. Rows written into such a database before [#201] still carry no kind, and no migration can invent one.

**Which `@WMA.cs` branch to implement was the one real fidelity decision**, and it is the same one `nt8_stddev` faced: NT8 rebuilds the weighted sum every bar for a bar type supporting `RemoveLastBar`, which time bars do, and carries it forward otherwise. The rebuilt form is exact and is what minute bars run, so that is what `nt8_wma` does. It costs `O(n·period)` — 0.220 s against `nt8_ema`'s 0.004 s at period 200 over 1.66M bars, and an HMA is three WMAs — which is affordable and is only paid by a sweep that asks for those kinds.

### Tier-2 verification — [#67] is all that remains ([#65])

**~~A second long-side contract~~ ([#92]) — done.** `MNQ 06-24`, fully liquid: 1,792 of 1,792 legs joined, **100% identical entry price**, 99.61% identical on every field. The residual is dominated by the L4 runner exiting later in NT8, which is the same `StopTargetHandling.PerEntryExecution` artefact already recorded against S4 — now seen on both sides of the market, which makes it a property of NT8's per-entry handling rather than of either strategy.

**~~Reconcile NQ against NT8~~ ([#66]) — done.** 1,105 of 1,112 joined legs identical on every field (99.37%), and **no instrument-dependent behaviour was found**, which was the open question. NQ no longer inherits its confidence from MNQ.

That run also corrected a rule this project had been carrying since the first reconciliation: **the trade-list export is in the machine's display timezone, not UTC.** The original evidence — an empty 22:00 hour — was sound but window-specific, because December–March is GMT and London coincides with UTC there. Over the summer MNQ 06-24 window the difference is a full hour, and parsing as UTC joined 332 of 1,800 legs against 1,792 of 1,792. **A wrong timezone parses cleanly and reads as a failed reconciliation**, so it is now explicit configuration in `tools/reconcile_nt8.py` rather than an inferred default.

`tools/reconcile_nt8.py` is the reusable mechanism these produced. Per the standing rule that each archetype earns its own reconciliation, the next one does not start from scratch.

**Settle the four order-lifetime questions** ([#67]) that reflection cannot answer — listed above. It is the only NinjaTrader item left, and it gates M19, which is queued rather than scheduled.

______________________________________________________________________

## Decisions taken

**True Range crosses a roll boundary unchanged, and the splice is not special-cased** ([#23]). The prediction that reached the ticket was "back-adjustment makes the gap small but not zero, so ATR steps at each of the 18 rolls". Half of that is wrong and the half that is right is right for another reason, which is why measuring it was worth the afternoon.

The gap is not small-but-not-zero — the residual basis is **exactly zero**, on all 36 seams across both roots. The shift is `front_close − back_close` at the last bar the front contract contributes, and that is precisely the bar a seam reads its previous close from, so the two cancel bit for bit rather than approximately. Nothing is left at a seam except the back contract's own move over the break, which is measurable inside one contract with no splice in it. `splice.roll_seams` produces the table and a test pins the property against a *drifting* basis, so an offset read off any other bar fails it.

ATR does still step, so both standing consequences hold — do not read the step as a volatility event, and judge an ATR-sensitive rule per contract ([#31]). What changed is what the step means, and therefore what a fix would have to fix: **the largest steps are missing sessions, not roll artefacts.** The front contract owns its final session and NT8's archive holds only its first hour, so most seams today span a whole absent trading day rather than the maintenance break. That is the already-recorded cost of correct roll dates, and nothing about the splice or about True Range would improve it — resetting TR at a roll would have hidden a data gap behind a plausible-looking number, which is the more expensive failure.

The cheap generalisation: **a prediction with a mechanism in it is worth measuring even when the conclusion turns out unchanged**, because the mechanism is what the next decision is made from.

**New archetypes: infrastructure now, one archetype now, M11 keeps its slot.** `CLAUDE.md` records "which archetype is actually worth trading is a later question" and treats DeadCatBounce as the test fixture. Adding EMA crossover and squeeze breakout partly reverses that, so the extent was decided deliberately rather than by drift: **the infrastructure lands now** (M15, M16, M17 — which is where essentially all the cost is, and much of which M9 and M10 needed anyway), **one archetype is built to prove it** (M18), and **M11 is not displaced**. The second archetype (M19) is specified and queued, not scheduled.

The reasoning is that the infrastructure is not archetype-specific work at all. M15 is a `direction` field M9 was already adding; M16 is a debt `indicators.py` recorded from the start; M17 is the same axis-above-the-`Dataset` mechanism M13 and M14 already needed. Only M18 and M19 are genuinely new scope, and they are the small part.

**Strategy development stays in Python; the C# port happens on promotion, not on creation.** Decided explicitly. An archetype is designed, swept, stratified and — most often — discarded without any NinjaScript existing. Only one that looks like it works earns the port back to C#, at which point the Python is the specification and the usual leg-for-leg reconciliation applies.

The reasoning is throughput: most archetypes will not survive contact with costs, and writing a NinjaScript for each one before knowing that spends NinjaTrader time — the project's scarcest resource — on candidates that are about to be thrown away.

Three things this buys and one it costs, all worth recording:

- The prime directive **still binds during development**, and this is what protects the eventual port. A Python archetype that drifts into intrabar precision cannot be reconciled when it is finally written in C#, so the exploration would be wasted rather than merely unvalidated. "It's only Python for now" is not a licence to exceed NT8's fidelity.
- The design must be **checked against what NT8 can express while it is being written**, not at port time. That is what the expressibility checklist is for, and it is why the order-lifetime research was done now rather than when M19 starts.
- **Tier-1-only status becomes per archetype and must be visible**, not remembered — M17's registry field and results column. A ranking that mixes a reconciled archetype with an unpromoted one is comparing a measurement with an assumption.
- The cost is that a promising Python result carries **unquantified port risk** until the reconciliation runs. Accepted, on the grounds that it is only paid for candidates worth paying it for.

**Promotion criteria — what "we believe we have something that works" should mean.** Left loose it will collapse into "the profit factor looked good", which is the multiple-comparisons trap §11.4 exists to prevent, and the port is expensive enough to be worth a bar. A candidate should clear the null before it earns C# time: beat the random-entry arm ([#32]), survive walk-forward ([#50]), and hold up across contracts rather than resting on one quarter ([#31]). Not a gate to enforce mechanically, but the checks to have run before spending NinjaTrader time.

**`PullBackAndGo.cs` is ported before any original is built.** The alternative was to let EMA crossover be the first exercise of the new long-side code. Rejected: a long-side fill bug found against `PullBackAndGo`'s NT8 trade list is a bug, whereas the same bug found on an original archetype is indistinguishable from the strategy simply being bad. It is long-only `EnterLongStopMarket`, the exact mirror of DeadCatBounce's entry, so it tests the new path precisely and it has ground truth. `InsideBar.cs` followed for the same reason (M22); `InsideBarTrailing.cs` remains unported and is the cheapest further archetype available.

**~~The bracket engine is extracted during M18~~ — done ([#38]).** Before would have been designing an abstraction from one example; after would have meant fidelity-critical code sitting duplicated on `main`. Extracted mid-M18 with byte-identity as the gate, so the abstraction was designed against two real shapes and the duplication never shipped. The split it found is entry half versus bracket half: `nqbt/sim/bracket.py` is the second, and a new archetype writes only the first.

**Archetypes are flat between trades; stop-and-reverse is not supported.** Each loop's `in_position` boolean assumes flat-to-flat, and for the stop-market archetypes reversal also collides with the one-bar entry lifetime. Recorded as a deliberate limitation rather than discovered as a position-tracking bug. M18 is what it costs in practice: a crossover's regime flip closes and reopens as **two fills at the same open price**, each paying its own slippage and commission, where the classic form reverses in one order. That is a real difference from published crossover results and belongs in any comparison against them. See [#13].

**Contract validity is the instrument registry's answer** ([#69]). Whether a file in `data/archive/` names a contract used to be decided in three places, and the one that fired first was the one least related to whether the thing is tradeable here. `ContractId.__post_init__` checked the month against a module-level quarterly set; the root was never checked at all. So `NG 02-26` was rejected for **being February**, not for being natural gas — and `NG 03-26` passed every gate, was cached under `cache/bars/NG/`, and failed only much later at `contract.instrument`, as a `KeyError`, at the point something asked for its money spec.

Validity is now one question asked of `INSTRUMENTS`: the root must be a registered `Instrument`, and the month must be one that root's `contract_months` lists. `MONTH_CODES` carries all twelve CME letters, because `cache_key` needs them regardless, and the *listed* cycle moved onto the instrument where it varies — the equity index roots list `HMUZ`, gold `GJMQVZ`, silver `FHKNUZ`, crude all twelve. Adding a root is one `Instrument(...)` entry and nothing else.

ES, GC, SI and CL are registered on that basis, together with the micro beside each full-size root — MES, MGC, SIL and MCL. Each entry's `tick_size` × `point_value` reproduces the tick value CME publishes — $12.50, $10.00, $25.00 and $10.00 full-size, $1.25, $1.00, $5.00 and $1.00 micro — which cross-checks both figures at once, and `tests/test_instruments.py` pins them.

**Micros are registered explicitly, not derived, and silver is why.** The obvious rule is "prefix M, divide the point value by ten", and it holds for four of the five pairs. Micro silver is **SIL**, not MSI, and it is 1,000 troy ounces against SI's 5,000 — a fifth, not a tenth. A derived registry would therefore have produced a symbol nothing exports under *and* a silver point value **2× too large**, in the one place every dollar figure in the project is obliged to route through. The tick *size* is genuinely shared within each pair, which is what makes the pairs look derivable in the first place. `test_a_micro_cannot_be_derived_from_its_full_size_root` exists to stop the registry being "simplified" into that rule later.

A root may also carry a digit now (`M2K`, `6E`). The regex was letters-only, so those failed with "cannot parse contract name" — a parse error standing in front of the real answer. Which roots exist is the registry's question, and the regex should not be answering a different one.

**The registry is deliberately ahead of the rest of the system.** Registering a root makes its exports nameable and its dollars convertible; it does not make it tradeable here. Two known gaps, neither closed:

- `Instrument.session_template` is a bare `str` that nothing resolves — `SessionTemplate` is threaded through `sessions`, `resample` and `randomentry` as an argument with the index-ETH default instead. Nothing diverges today, because the Globex ETH window is 18:00–17:00 ET for equity index, metals and energy alike, but the field must be wired from NT8's Data Series window before anything consumes it.
- The $1.50 round-turn commission is an index-futures figure and does not transfer. Costs are per-caller and default to zero, so this is the standing free-money trap rather than a new one.

**Roll dates need no reconciliation against NT8.** All 18 MNQ roll dates moved when the archive made volume crossovers detectable, which raised whether Tier 1 and Tier 2 still agree across a roll. Decided: not worth chasing. NT8 merges contracts on the rollover dates **configured in its Database window**, not on observed volume, so it is a setting rather than a measurement. It is ground truth for fill semantics, which is what the prime directive is about; it is not ground truth for when the market actually rolled. A data-derived crossover can reasonably be *better* than NT8 here without that being a fidelity violation.

Residual risk, recorded rather than dismissed: a spliced-series result cannot be reproduced in Strategy Analyzer bar-for-bar around a roll. If a sweep that crosses one ever produces something surprising, the roll boundary is a candidate explanation, and the segment tables in `nqbt splice --diagnostics` are where to look first.

**One `sweeps` row per axis point, tied by `batch_id`** ([#29]). A run varying strategy, resolution or contract is several **datasets**, and `bars`, `first_bar` and `last_bar` are properties of a dataset — one row spanning nineteen contracts could not honestly fill them, and sweep-level tags would have to read "varies", which is the state that makes the tag useless exactly when it matters. So each axis point writes its own row with its own honest counts, and a nullable `batch_id` says which rows were one experiment. Without it the only way to regroup them is `created_utc` plus a matching `axes` blob, which is fragile in the direction that silently merges two experiments.

Two things the build settled, both of which were latent bugs rather than choices. **`save_sweep` now inserts by name**, because `ALTER TABLE` appends the new columns at the end while a fresh `CREATE TABLE` declares them in the middle — one positional statement cannot serve both, and `root`/`instrument`/`strategy`/`contract` are four adjacent VARCHARs, so a transposition stores a plausible row rather than raising. That is the same rule M9 applied to `combos`, arriving at `sweeps` for the same reason. And **the axis columns are migrated explicitly** rather than left to `_append_or_create`'s drop-what-you-do-not-know policy: dropping a *statistic* leaves a visible gap, which is the accepted trade, but dropping `contract` does not leave a gap — it relabels the row as a different run.

**Pin the dtypes when a tag can be null.** DuckDB types a new table from the frame that creates it, and an all-null `object` column infers as **INTEGER** — so a first sweep over the spliced series, where `contract` is null by definition, would have created `combos.contract` as an integer column that no contract name could ever afterwards be inserted into. Measured, not reasoned about; `tests/test_sweep_stats.py` pins it.

**Stored sweeps — dropped and re-run, stratified** ([#71]). Everything previously in `results/sweeps.duckdb` was computed against a continuous series with different roll dates, at $0.74 commission, and before the M10 labels existed. Those rows were answers to a different question, so they were dropped rather than added to. `tools/rerun_sweeps.py` is the re-run, and it is a committed tool rather than a shell session because the drop had to happen for a reason that was not obvious: `_append_or_create` wrote an existing table **by name** and silently dropped a column the table did not have, so appending stratified rows to the pre-#39 schema would have stored them with `regime_filter` and `phase_filter` thrown away. Since [#201] it would widen instead, and the drop stays for the reason above — those rows answer a different question.

**Eleven strata per root, one dimension at a time.** Unfiltered, then once per regime, then once per session phase — not the 32 cells the product would give. Each label answers "no edge anywhere, or edge in one stratum drowned by the others?" on its own, and crossing them is what [#48]'s guard exists to refuse. Every stratum runs the same 96-combination grid, so the stratum is the only thing that varies between two comparable rows. **`ambiguity_policy` is not swept**: `0` is a blanket worst case, deliberately *more* pessimistic than NT8 rather than equal to it, so half the stored rows would have ranked a combination against a fill rule the prime directive rejects. The trade is that the 0.009 profit factor between the two policies came from the rows that were dropped and is no longer re-derivable from `combos`; re-add the axis to re-measure it.

**The answer is "no edge anywhere", and one cell needed ruling out to say so.** 21 of the 2,112 rows reach a profit factor above 1, and all 21 are the same cell: NQ, `phase=CLOSE`, every one of them with `use_vwap` on. Nothing else in either root, either label, crosses 1.0 — MNQ's own `CLOSE` stratum tops out at 0.954. Three reasons that cell is not a finding, in ascending order of how much they settle it:

- It is the best of 22 stratum-cells chosen after looking, at 105–180 trades each.
- `CLOSE` is the structurally anomalous phase ([#16]): its exits are decided by the clock rather than by the rules, and `session_close_share` reads 0.5–2.5% there against 0.03–0.04% unfiltered — the order of magnitude M10.4 predicted, arriving as predicted.
- **The same trade list reads 1.390 through the NQ spec and 1.020 through the MNQ spec.** Same 110 trades, same geometry, the same $660 of commission, gross P&L ×10. The apparent edge is almost entirely the commission-to-point-value ratio and almost none of it is the clock, which is exactly the free-money trap `instruments.py` exists to make visible.

**The decomposition behaved as M10.1 and M10.4 said it would**, which is the check that the run is sane rather than a result from it: the seven phase strata sum to the unfiltered trade count exactly, on all 96 combinations of both roots, and the three regime strata never do — they run 1 to 7 trades over, because a regime label flips bar to bar where a phase is a contiguous block.

Live numbers rather than the ones above: `results.query` over `combos` joined to `sweeps`, which carries the stratum in `notes` and ties the whole re-run together with one `batch_id`.

**Trade source format — deferred, by design.** An example will arrive; until then the importer is specified as an adapter boundary ([#45]) rather than around a guessed layout. Everything upstream of the example — the schema (M9), the conditions (M10), the annotation and review machinery — is independent of the format and can be built first.

**Trade source — the NT8 executions grid**, with the Control Center log rejected. The review reports dollars, points and exit reason; `r_multiple` is deliberately not reconstructed.

**Discretionary context — recorded, not analysed** ([#49]). Stored, viewable, and structurally kept out of the evaluation path in a sidecar table so it cannot reach a `groupby`.

**Coverage — measured, not decided** ([#45]). Whether trades fall inside cached instruments and dates becomes a report the importer emits, so the answer arrives as data with the first real file. The only design consequence is that out-of-coverage trades must be excluded loudly rather than dropped quietly. Resolved for the sample: MNQ runs to 2026-08-10 19:55 UTC, past the 16:58–17:07 trade window. Note the export lags live by roughly two hours, so the most recent session is always partly unavailable.

**Timezone — NT8 display time is the machine's local zone**, `GMT Standard Time`, so BST (UTC+1) in summer. Confirmed end-to-end: converting the sample's eight fills to UTC and mapping each to the bar stamped at the next whole minute puts every one inside its bar's high/low range, with the 17:00:29 stop landing exactly on the 17:01 high. That simultaneously validates the conversion, the end-of-bar alignment rule, and coverage. It should still be explicit configuration rather than an inferred default — a wrong zone shifts every trade by hours without erroring — but the default is now known to be right for this machine.

**Parked is not abandoned: a failed campaign retires a *configuration space*, not an archetype** ([#195]). §M27 eliminates five of the six archetypes, and it is worth being precise about what that does and does not license, because "we tested it and it did not work" decays into "it does not work" within about two months.

What the campaign is evidence of: the logic behind those five, **as currently written, over the ranges swept, on the data held today, at today's costs**, does not produce something worth trading. That is a real result and it should stop anyone spending another week tuning periods on DeadCatBounce.

What it is not evidence of: that no version of them can work. Each of the following would make a parked archetype worth re-running, and none of them is exotic:

- **A condition that does not exist yet.** The order-flow and dealer-gamma labels ([#124]) are the obvious case — every archetype here was stratified against the five conditions the codebase happens to have, and a sixth could separate a cell that today looks like noise.
- **A bracket it was never given.** InsideBar's own result turns on a target multiplier that does not exist yet ([#197]); PullBackAndGo has a ratchet and no ATR bracket at all, and DeadCatBounce has never been run against a structural stop.
- **A range the sweep did not reach.** η² is a property of the ranges swept and nothing else.
- **More data, or different data.** Five years, two roots and one index. A regime the sample does not contain is not a regime the sample rules out.

So the tracker keeps them: an archetype that fails a campaign is **not deleted, not un-registered and not removed from the sweep**, because the cost of keeping it is one entry in `archetypes.py` and the cost of deleting it is re-deriving everything §M27 measured. Its `Tier2Status` and its reconciliation evidence stay exactly as they are. DeadCatBounce is already the model for this — it has been unprofitable since M7a and it stays registered because it is the fixture that proves the system works.

**The rule to apply when picking one back up**: say what has changed since §M27 before re-running it. A re-run with no new condition, no new geometry and no new data is the same measurement with a new random seed, and reading it as a second opinion is the multiple- comparisons trap wearing a calendar.

______________________________________________________________________

## Still open

- **Sample size.** How many real trades exist determines whether [#48]'s guard leaves anything standing. A few dozen will not support stratification by more than one or two conditions at a time, and knowing that early sets expectations for what the review can honestly deliver.
- **Which series to annotate against.** The sample trades a single contract, `MNQ 09-26`. Annotating against the per-contract cache sidesteps back-adjustment and roll-date questions entirely and is almost certainly right; the continuous series only earns its place if a review needs indicators with lookbacks that cross a roll.
- **Documentation must not carry figures that go stale.** State the rule; point at where the live number is produced — `docs/nt8-fidelity.md` for agreement rates, a `pytest` run for the test count, `nqbt splice --diagnostics` for bar and roll counts. `CLAUDE.md` loads into every session, so a stale figure there is a wrong fact asserted with authority, and these numbers move on almost every fill-rule change.
- **`verification/` is gitignored in its entirety** ([#91]), including its `README.md` — which `.claude/rules/data-pipeline.md` cites as the authority on what the stored captures mean. The CSVs are regenerable; the prose is not, and it exists on one machine.

[#10]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/10
[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#11]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/11
[#113]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/113
[#12]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/12
[#124]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/124
[#126]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/126
[#127]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/127
[#13]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/13
[#16]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/16
[#160]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/160
[#161]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/161
[#167]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/167
[#168]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/168
[#169]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/169
[#17]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/17
[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#18]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/18
[#183]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/183
[#19]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/19
[#195]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/195
[#196]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/196
[#197]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/197
[#198]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/198
[#199]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/199
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
[#201]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/201
[#208]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/208
[#23]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/23
[#24]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/24
[#25]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/25
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
[#9]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/9
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
[#92]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/92
