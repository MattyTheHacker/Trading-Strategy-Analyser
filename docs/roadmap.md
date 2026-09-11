# Roadmap

**Results do not live here any more.** Every campaign — what it swept, what it returned and what it settles — is one file in [`findings/`](findings/), indexed three ways by `tools/findings_index.py`: the [register](findings/README.md), [by archetype](findings/by-archetype.md) and [by gate](findings/by-gate.md). They were extracted because they had grown to three quarters of this file and buried the four things below that have no other home, and because milestone order is the one order that cannot answer "what do we know about this archetype" or "what has cleared gate 3". Each `§Mxx` keeps a stub under "Milestone notes" naming its file, so an existing pointer still resolves.

**How this file relates to the issue tracker.** The issues carry **everything that changes** — scope, acceptance criteria, checklists, ordering, dependencies and status. This file carries **what stays true after the work lands** — the constraints that span milestones, the traps that cost real time, and the decisions taken so they are not silently re-litigated. When the two disagree about scope or order, the issue wins; when they disagree about reasoning, this file wins.

**Plans do not live here.** Ordering is GitHub's `blocked-by`/`blocking` dependency graph, status is the issue's own state, and grouping is its epic and milestone. This file used to carry a hand-maintained order-of-work table; it duplicated all three, went stale on every landing, and was removed for that reason. To see what is next, ask the tracker:

```bash
gh issue list --state open --label next-up
gh issue list --state open --milestone "Phase 3 — Review system"
gh issue view <n>                       # blocked-by / blocking / sub-issues
```

Four things live here and nowhere else, because an issue is the wrong home for them: the **standing constraint** and its expressibility checklist, the **order-lifetime research**, the **standing rubric**, and the **decision record**. A closed issue is not read; a rule that outlives its milestone therefore belongs in this file rather than in the issue that produced it. A *measurement* that outlives its milestone belongs in `findings/`. Everything else is a paragraph of context with a link.

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
- ~~**The prop-account simulator** ([#75])~~ — **done.** It treats the daily flat as one of the rules it replays, alongside the trailing drawdown, the daily loss limit and the consistency ratio. It replays them over a finished trade log and adds nothing to `nqbt/sim/`, which still models this one rule and no other — § "Replaying a prop account over the trade log".

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
- **A union of axis values is not a union of parameter sets**, and `Grid.of_combinations` is where the two come apart. `axis_values` collapses a combination list to one list per parameter, so any rule that reads two of them back as a *pair* gets pairs no member holds. For `OpeningRange` that is unbuildable rather than merely wasteful: a pooled shortlist asked for a 930-minute range anchored 990 minutes past the open, `sessionrange.validate_key` refused it, and the pool could not be prepared at all — so the walk-forward and Monte Carlo gates crashed on any shortlist spanning ranges. `required_context` therefore unions member by member; `axis_values` still reports the union, because the stored `axes` column describes the pool rather than specifying a build.
- **A consistency count does not order the evidence, and the largest one is not the strongest case.** §M28.14 scored twelve context cells on how many `root x resolution` cells a filter won in both windows; §M28.16 took the ten of them that had never been nulled to a matched null and found the rank correlation between the score and the null excess to be −0.132, with the two `+10` cells at the bottom of the table. A score says a direction repeated; only a null says it was worth anything.
- **A prefix of a trade log is not a sample of it.** The `explain.py` defect was justified with "50% of trades", measured over a 200-trade prefix; the whole-window rate is 35.7%. Quote whole-window rates.

______________________________________________________________________

## Milestone notes

One paragraph of reasoning each. Scope and acceptance criteria are in the linked issue.

**A milestone that produced a measurement is a stub here** — its heading, its verdict in a sentence, and a link to its file in [`findings/`](findings/README.md). The heading stays so a `§Mxx` pointer still resolves; the numbers, the tables and the caveats are in the file, and that is what to quote.

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

### The build spec's three loose ends ([#74])

**The trail is a ratchet over a different level, round numbers need a stated price basis, and the confluence count is refused at construction rather than gated by an axis.** Moved to [`docs/findings/build-spec-loose-ends.md`](findings/build-spec-loose-ends.md).

### The build spec's three loose ends, measured ([#74])

**None of the three features improves EmaCrossover; the trail costs in nineteen of twenty cells and the confluence count moves results without being edge.** Moved to [`docs/findings/build-spec-loose-ends-measured.md`](findings/build-spec-loose-ends-measured.md).

### Counting the confluence a trade actually had ([#74])

**The gradient in confluence is monotone and the matched null removes it, so the count sorts trades rather than adding edge.** Moved to [`docs/findings/confluence-count-per-trade.md`](findings/confluence-count-per-trade.md).

### Filtering trades by context and configuration ([#251])

**There are two questions about a condition and only one of them is the review's.** *Does this strategy work if it only trades in an uptrend* changes the strategy: `trend_filter` and its five siblings are swept, and `tools/campaign_sweep.py` measures the result. *Of the trades it took, which worked and what was true then* changes nothing, and it is the one a person actually asks first. Both existed already; what did not was any way to ask the second one as a **filter** rather than as a report — `review.stratify` cuts by one condition at a time, an annotation lived only in the Python session that built it, and three context families had no per-trade columns at all.

#### Three gaps, and the third is the one that made it a query

**Compression, session ranges and bands were unreviewable.** `Dataset.compression_labels`' docstring has read *"for stratifying results"* since [#51] and had no caller; `annotate.py` mentioned compression nowhere. So an entry could be gated on a condition that could never be read back off the trades it produced, and OpeningRange and ElasticBand — the two newest archetypes — could not be stratified by their own geometry at all. `_compression_conditions`, `_band_conditions` and `_range_conditions` close it, and `LabelThresholds` gains the compression pair on the same both-or-neither rule as the other two.

**Nothing crossed two conditions.** `annotate.crossed` builds the composite label, and it is deliberately not a new kind of thing: the result is an ordinary condition, so `review.stratify` ranks it and `guard.screen` puts it in the same family as everything else. **No statistic is defined by it**, which is the property that keeps a cross from drifting away from the sweep's numbers.

**The cardinality limit is the substance of that function, not its validation.** The product grows multiplicatively while the sample does not: trend × regime × phase is 81 strata over a few hundred trades, every one of them under `review.MIN_TRADES`, and the failure mode is a report that silently skips the condition rather than one that says why. `MAX_CROSSED_VALUES` refuses above `review.MAX_STRATA` and names the count — pinned equal to it by a test rather than imported, because `review` imports `annotate` and the dependency cannot run both ways. Same arrangement as `guard.separate` against `review.rank_conditions`.

#### The parameter dimension stays in the sweeps table, and that is a measurement rather than a preference

The obvious next step — pool every combination's trades and stratify by `ema_period` — is wrong, and the reason is in the data rather than in taste. **Two combinations differing in one axis share most of their entries.** A grid varying only `tp_multiplier` produces the same signals with different exits, so pooling twenty of them and treating each trade as an independent observation inflates every sample size roughly twentyfold. `guard`'s permutation test assumes exchangeable trades; near-duplicate trades from neighbouring cells are not exchangeable, and the null it draws would be far too tight. The p-value would look excellent and mean nothing.

`tools/campaign_report.py`'s `axis_influence` already answers the parameter question correctly, one row per combination, and §M27's η² tables are what it produces.

**The join gives the filter anyway, which is what makes the restraint cheap.** `trades` joins `combos` on `(sweep_id, combo_id)`, so `results.TRADE_VIEW` carries every parameter beside every trade. A parameter can therefore *narrow the population* — "the trades a 20-period EMA configuration took" — while the review still refuses it as a *ranking*. Filtering by a column and grouping by it are different acts, and only the second is unsound here. The view prefixes every `combos` column with `combo_`, which is not only collision avoidance: `net_pnl` means the leg's on one side and the whole combination's on the other, and a query that confused them would report a plausible number.

#### What a stored annotation has to carry with it

**The cut, on every row.** An annotation is meaningless without the thresholds it was labelled at — §M27.8 is the case where a whole volume ranking turned out to be decided by its cut, and a raw pair admits 28% of bars under one form and 8% under another. Two annotations written under different cuts are two populations, and a query joining them would silently report one. `save_annotation` therefore stamps the `LabelThresholds` onto each row under `results.CUT_PREFIX` rather than leaving the provenance to be remembered.

There is a weaker case inside that: where a configuration's filter was inert, the stored threshold is the params-class default that nobody chose. `tools/campaign_annotate.py` reads it anyway, because *the cut this row was measured at* is the only honest answer available and the stamp is what lets a reader see that it was a default.

**And the notes rail.** `annotate_trades`, `review` and `guard` are the three doors that refuse free text. Persisting to a queryable table is a fourth door onto the same data and a worse one, because a note reaching a column is one `GROUP BY` away from the perfectly circular finding §M11.5 describes — so `save_annotation` refuses it too.

#### What needed no code

"Profitable **and** taken in an uptrend" is `review.stratify` over the trend label: a row per state carrying win rate, expectancy and profit factor. Filtering *to* the winners and asking what they had in common is the same question read backwards, and it is the weaker direction — it cannot show whether a relationship is monotone, and it will always find something. `review.by_outcome` is the honest form of the backwards read and says so; § "Counting the confluence a trade actually had" is where that argument was first made.

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

### M19.1 — compression as a condition, before it is an archetype ([#51])

**The condition is real and consistently ordered across seven archetypes and two roots, and it still separates no better than four dimensions the campaign already had — a reason to keep M19 parked rather than to build it.** Moved to [`docs/findings/m19-1-compression-condition.md`](findings/m19-1-compression-condition.md).

### M26 — the elastic band, the first mean-reversion archetype ([#167])

**The first mean-reversion archetype: Bollinger as the band, three exit schemes as three grids, and a first measurement whose held-out behaviour does not survive the test it is put to.** Moved to [`docs/findings/m26-elastic-band.md`](findings/m26-elastic-band.md).

### M26.4 — the VWAP band: the second source, and the first thing to survive a holdout here ([#221])

**`band_source` clears the holdout and not the matched null, so what it buys cannot be separated from the bracket; depth is the axis that separates the two sources and 2 sigma is not deep enough.** Moved to [`docs/findings/m26-4-vwap-band.md`](findings/m26-4-vwap-band.md).

### M26.5 — the signal bar's own shape: the first thing here whose excess is not the bracket's ([#221])

**Requiring the signal bar's body to have turned raises the observation while leaving the matched null where it was — the first ElasticBand excess that measures the entry rather than the bracket, and still not a pass on 34 to 56 trades.** Moved to [`docs/findings/m26-5-signal-bar-shape.md`](findings/m26-5-signal-bar-shape.md).

### M26.6 — the recovery entry: the reaction §M26.5 deferred, and the one the later window punishes ([#278])

**A well-powered negative rather than an underpowered one: the recovery entry wins the selection window, gives all of it back held out, and pays for the reaction out of both ends of the bracket at once.** Moved to [`docs/findings/m26-6-recovery-entry.md`](findings/m26-6-recovery-entry.md).

### M26.8 — the stop on the band itself: the level §M26 specified and never built ([#280])

**A stop at the band beats the tightest stop and never the widest; every arm beats the matched null and the stop scheme is not what moves the margin.** Moved to [`docs/findings/m26-8-stop-on-band.md`](findings/m26-8-stop-on-band.md).

### M26.9 — a volume requirement on the break: the state it asks for is the one that costs ([#281])

**A `HEAVY` requirement is a cost on both roots under all three forms; `NORMAL` is the state that helps, which is the second archetype to answer the volume question that way.** Moved to [`docs/findings/m26-9-volume-requirement.md`](findings/m26-9-volume-requirement.md).

### M27 — the registry-wide campaign: every archetype, every axis ([#195], [#196])

**Bar size is the largest lever and the moving averages are nearly inert; four of six pass gate 1, three gate 2, one gate 3 — and what stops InsideBar is its bracket rather than its entry.** Moved to [`docs/findings/m27-registry-campaign.md`](findings/m27-registry-campaign.md).

### M27.3 — InsideBar's bracket, crossed at last ([#198])

**The target is the largest axis on the holdout and almost inert on the selection window; the re-sweep is a held-out failure, and the negative rank correlation is a finding with no explanation yet.** Moved to [`docs/findings/m27-3-insidebar-bracket.md`](findings/m27-3-insidebar-bracket.md).

### M27.4 — the sixteen strata that were never held out ([#199])

**The shortlist decays by about the same amount in every stratum, it is not noise, and InsideBar's DIRECTIONAL cell turns out to have two larger siblings.** Moved to [`docs/findings/m27-4-strata-held-out.md`](findings/m27-4-strata-held-out.md).

### M27.5 — the regime threshold, calibrated rather than swept blind ([#200])

**The regime threshold is fitted rather than guessed, which restores the per-contract sample in most places but not everywhere; cross-resolution rows are not twins.** Moved to [`docs/findings/m27-5-regime-threshold.md`](findings/m27-5-regime-threshold.md).

### M27.6 — walk-forward and Monte Carlo, wired into the campaign ([#203])

**The shortlist becomes the candidate pool for gate 4, which `Grid` had no way to express before.** Moved to [`docs/findings/m27-6-walkforward-montecarlo.md`](findings/m27-6-walkforward-montecarlo.md).

### M27.7 — time of day: swept, never read, and the artefact is in the wrong phase ([#205])

**Against a matched random entry the edge is in the quiet phases; the forced flat lands in AFTERNOON rather than CLOSE, and InsideBar's CLOSE stratum is empty by construction.** Moved to [`docs/findings/m27-7-time-of-day.md`](findings/m27-7-time-of-day.md).

### M27.8 — volume: one form, one cut, and the answer is the cut's ([#206])

**Which volume state helps is decided by the form and the cut rather than by volume; held out it is a coin flip, and `NORMAL` is the best cell under two forms of three.** Moved to [`docs/findings/m27-8-volume.md`](findings/m27-8-volume.md).

### M28 — the opening range: what "ORB" actually names, and what of it is expressible ([#235])

**Every ORB variant is a point in six axes; the outside evidence establishes less than it appears to, and the expressibility checklist says which of it NT8 can hold.** Moved to [`docs/findings/m28-opening-range-spec.md`](findings/m28-opening-range-spec.md).

### M28.1 — OpeningRange: built, swept, and the first archetype through three gates ([#236])

**The first archetype ever to pass gates 1 to 3: the stop mode splits it into a half that always passes and a half that always fails, and gate 4 is a sample-size verdict rather than a failure.** Moved to [`docs/findings/m28-1-openingrange-swept.md`](findings/m28-1-openingrange-swept.md).

### M28.2 — the deferral list, built: three entry mechanisms, one stop axis, and a null over levels ([#237])

**The breakout reproduces §M28.1 and gains a level null; the fade fails gate 1 everywhere and is parked; the retest has no verdict because its gate-2 pass measures `ambiguity_policy` rather than a strategy.** Moved to [`docs/findings/m28-2-deferral-list.md`](findings/m28-2-deferral-list.md).

### M28.3 — the ambiguity spread: a shortlist's second arm ([#248])

**A ceiling on `ambiguous_share` is the wrong instrument; the spread between the two policies is reported rather than gated, and that is the decision.** Moved to [`docs/findings/m28-3-ambiguity-spread.md`](findings/m28-3-ambiguity-spread.md).

### M28.4 — settling the ambiguous bar instead of bounding it ([#248])

**Minute bars settle 17% of ambiguous bars and all of them against the assumption, which bounds the retest's profit factor from above; it stays a diagnostic and never enters `nqbt/sim/`.** Moved to [`docs/findings/m28-4-settling-ambiguous-bar.md`](findings/m28-4-settling-ambiguous-bar.md).

### M28.5 — the fade's bracket, tightened: monotone the other way, and zero of 15,360 ([#256])

**The stop axis is monotone across the whole of 0.02 to 1.0 of the range width because the stop sits inside the bar the order fills on; the held-out test reproduces gate 1 exactly.** Moved to [`docs/findings/m28-5-fade-bracket.md`](findings/m28-5-fade-bracket.md).

### M28.6 — the rejection: the fade's level, the retest's order type, and no break at all ([#255])

**Four modes and three properties, built from the fade's level and the retest's order type with no new machinery.** Moved to [`docs/findings/m28-6-rejection-spec.md`](findings/m28-6-rejection-spec.md).

### M28.7 — the rejection, swept: every profitable cell is one the fill assumption decides ([#255])

**Profitability tracks the fill assumption and nothing else — every profitable cell in 245,760 is one the assumption decides, which is a stronger negative than the retest's no-verdict.** Moved to [`docs/findings/m28-7-rejection-swept.md`](findings/m28-7-rejection-swept.md).

### M28.8 — the range as a cross: every anchor by every length, and the hour that was missing ([#258])

**The anchor and the length are one cell rather than two axes; the one-hour cash range sits on a plateau with no excess on it, and §M28's 5, 15 and 30 turn out to have been the right set.** Moved to [`docs/findings/m28-8-range-cross.md`](findings/m28-8-range-cross.md).

### M28.9 — the survivor, read for tradeability rather than for rank ([#261], [#262], [#263], [#264])

**Held out, one cell in thirteen across the registry returns its own drawdown; the binding constraint is net-to-drawdown rather than profit factor, and the edge is absent from 2026.** Moved to [`docs/findings/m28-9-survivor-tradeability.md`](findings/m28-9-survivor-tradeability.md).

### M28.10 — the geometry denominated in trailing follow-through: no, and the reason is arithmetic ([#261])

**Normalising the geometry against trailing follow-through does not restore 2026 on either root; follow-through fell 18% while the median range rose 136%, so the width is what is worth normalising against.** Moved to [`docs/findings/m28-10-follow-through-geometry.md`](findings/m28-10-follow-through-geometry.md).

### M28.11 — the two truncated bracket axes, swept to their end ([#262])

**Both axes are now swept to their end: the wider stop fails the acceptance cell, costs two thirds of net-to-drawdown, and lowers the excess over a permuted range as `session_close_share` doubles.** Moved to [`docs/findings/m28-11-truncated-bracket-axes.md`](findings/m28-11-truncated-bracket-axes.md).

### M28.12 — the bracket decomposition, read across the registry ([#264])

**One archetype in seven has a bracket that pays for itself held out; InsideBar's stop is nearly inert and its forced flat hands back about 90% of what the bracket earns.** Moved to [`docs/findings/m28-12-bracket-decomposition.md`](findings/m28-12-bracket-decomposition.md).

### M28.13 — the registry read through an account, and the assumption that turned out to be a parameter ([#75])

**Survival is not the question and reading it as one inverts the answer; the binding constraint is position size rather than the strategy, and the excursion order was an assumption and is now `excursion_order`.** Moved to [`docs/findings/m28-13-account-read.md`](findings/m28-13-account-read.md).

### M28.14 — every stratum against its unfiltered twin, and the cell that survives it ([#285])

**The clock separates the registry while volume and trend mostly do not; the midday cell clears four gates and the flatten is still what earns it.** Moved to [`docs/findings/m28-14-stratum-cross-read.md`](findings/m28-14-stratum-cross-read.md).

### M28.15 — the midday cell through the three reads that stopped it being a recommendation ([#287])

**Ten of ten walk-forward folds are profitable out of sample and the account funds on MNQ, but without the flatten there is no book to read — and 2026 remains the weakest year.** Moved to [`docs/findings/m28-15-midday-cell.md`](findings/m28-15-midday-cell.md).

### M28.16 — the ten consistent cells through the matched null, and what a consistency score is worth ([#288])

**Four cells clear p = 0.05 on both roots — three OpeningRange's and one InsideBarTrailing's midday cell — and a consistency score does not order the null result, correlating −0.132 with it.** Moved to [`docs/findings/m28-16-consistent-cells.md`](findings/m28-16-consistent-cells.md).

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

### ~~Sharpe and Sortino are refused rather than approximated~~ — done ([#81])

Both summary paths carried a branch for a trade log with no times: `summarise` when the frame had no `exit_time` column, `summarise_legs` when `day_codes` was `None`. Each fell back to the **per-trade** P&L vector and then annualised it by `sqrt(252)` anyway, so the output was a per-trade ratio scaled as though it were daily. The parameter `_risk_adjusted` receives is called `daily`, and its docstring says why per trade is the wrong denominator.

**Refusing was chosen over returning `nan`, and `0.0` was never an option.** `_risk_adjusted` already returns `0.0` for a log with fewer than two days in it, so a `0.0` from the no-times path would have been indistinguishable from a real answer. `nan` would have been visible, but the branch is not a statistic anyone asked for and cannot be computed correctly at all, so `MissingTimesError` says so at the point the log arrives. That is the same choice [#11] made for the empty-log constructor, one step louder: an empty log is a valid input with a defined answer, and a timeless one is a producer that has not wired its index through.

**Both paths refuse, because agreeing about a refusal is the same invariant as agreeing about a number.** Fixing only the pandas one would have left a sweep quietly producing the old figure into the same DuckDB column. `summarise_legs`' `day_codes` lost its `= None` default at the same time: the default made the wrong denominator the path of least resistance, and every caller already passed `Dataset.day_codes`. The type stays `IndexArray | None`, since `context.day_codes` returns `None` for a non-datetime index and that call site should read as passing it on rather than as suppressing a check.

**A null `exit_time` is refused for the same reason as a missing one.** `groupby` drops null keys, so a log with times on some rows would have produced a Sharpe over a denominator quietly smaller than the trade count while every other statistic still counted every trade — the same failure with a subtler surface.

**It moved no number**, which was the condition of doing it at all: no producer in the repository reaches either branch. `trades_to_frame` attaches times whenever it is given an index, `trade_import` always parses them, and `Dataset.day_codes` is `None` only for a non-datetime index, which `context.prepare` does not survive anyway. The one caller that reached it was a test asserting the two paths agreed about the wrong answer.

### ~~M7a~~ — the random-entry control arm: done ([#32])

**DeadCatBounce's entry rule is measurably better than random at p = 0.012 while still losing money, which makes the loss one of costs, hold time or bracket geometry rather than of the entry.** Moved to [`docs/findings/m7a-random-entry-control.md`](findings/m7a-random-entry-control.md).

### M7 — the null, split into M7a and M7b ([#32], [#50])

Three tools answering different questions: `walkforward.py` tests whether a parameter choice survives data it did not see, `montecarlo.py` tests whether an equity path was luckier than the trades justify, and `randomentry.py` supplies the null the other two cannot — same bars, same bracket geometry, same costs, same exit logic, entries drawn at random. **M7a was pulled ahead of the archetypes.** The roadmap originally scheduled it after M11 because it shares machinery with §11.4's permutation test, but **that sharing is symmetric and the interpretive need is not** — build the null first and M11's guard inherits it, whereas the *need* arrives the moment a second archetype exists. Against PF 0.746 it separates three diagnoses that currently look identical: worse than random (the signal is real but inverted), indistinguishable from random (stop tuning this archetype), and better than random but not past costs (attack costs, hold time or bracket size). Permuting an existing trade sequence cannot distinguish any of those, because it takes the entries as given. **It must be matched on direction** as well as count and time of day, or a long-only null against a bidirectional archetype measures market drift.

### M7b — walk-forward and Monte Carlo: done ([#50])

**Walk-forward and Monte Carlo exist as the fourth gate, resampling the trade order to separate a drawdown from its ordering.** Moved to [`docs/findings/m7b-walkforward-montecarlo.md`](findings/m7b-walkforward-montecarlo.md).

### M10 — the conditions the review needs and we lack ([#39])

The review is meant to score trades against "overall trend, MAs, volume, directional vs consolidation, time of day", and three of those five had no implementation. **All four sub-milestones have landed** — time of day ([#43]), the regime classifier ([#40]), volume ([#41]) and the compact trend label ([#42]), each below. Every one is a 1D label array computed once in `prepare` behind [#27]'s `required_context`, and every one carries its filter as a bitmask integer so it is a legal sweep axis.

**The multiple-comparisons cost is now real and compounds.** Seven session phases against three regimes, three volume states and three trends is 189 cells before an MA gate is touched. That is the argument for the coarse labels rather than an accident of them, and [#48]'s guard applies with more force here than anywhere else in the project.

### ~~M10.4~~ — time of day: done ([#43])

**The session phase label, cut on the exchange's own clock rather than the calendar's.** Moved to [`docs/findings/m10-4-time-of-day.md`](findings/m10-4-time-of-day.md).

### ~~M10.1~~ — market regime: done ([#40])

**The regime label — DIRECTIONAL, UNCLASSIFIABLE and the rest — and the thresholds that separate them.** Moved to [`docs/findings/m10-1-market-regime.md`](findings/m10-1-market-regime.md).

### ~~M10.2~~ — volume: done ([#41])

**The volume label, and the choice of form and cut that §M27.8 later found to be what decides the answer.** Moved to [`docs/findings/m10-2-volume.md`](findings/m10-2-volume.md).

### ~~M10.3~~ — the compact trend label: done ([#42])

**The higher-timeframe trend label, compact enough to sweep as a stratum.** Moved to [`docs/findings/m10-3-trend-label.md`](findings/m10-3-trend-label.md).

### Multi-timeframe moving averages ([#73])

**A higher-timeframe moving average is a condition rather than an archetype, and it does not separate.** Moved to [`docs/findings/multi-timeframe-moving-averages.md`](findings/multi-timeframe-moving-averages.md).

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

#### Charting a trade ([#239])

`nqbt/chart.py` draws one trade on the bars it happened on and returns an SVG: the candles either side of it, the bracket it carried, where every leg left, and how far price ran each way while it was open. It reads a trade log and a `Dataset` and nothing else, so a simulated leg and an imported fill are drawn by the same code — which is the property `sim/explain.py` does not have and cannot be given. That module takes `DeadCatParams`, recomputes the signal and reports each gate's operands, which is a stronger answer to *why did this fire* available for exactly one archetype. The two are complements: `explain` says why the order was placed, a chart says what happened to it.

**It is a debugging instrument and not a selection one, and it states that on itself.** A chart can settle whether the simulator did what the rule says — the class of question [#44] was built to be able to ask at all. It cannot settle whether the rule is any good, and trades read one at a time for that purpose are the multiple-comparisons machine [#48] exists for, in its most seductive form: a human looking at a dozen charts will produce a specific, confident, wrong conclusion that feels earned, and no p-value will ever be attached to it. `chart.CAUTION` is drawn on every chart for the reason `review.STATUS` is printed in every report — the failure mode is not a wrong picture but a right one read without its context.

**No line joins an entry to its exit.** The obvious thing to draw is a segment from the entry fill to the exit fill, and it would depict the one thing bar-close OHLC does not record: the path between them. Tick data would draw it truthfully and must not be reached for here, because the prime directive's trap is precisely this — an instrument that reads the simulation more finely than the simulation ran. What joins the two ends instead is a shaded span over the bars the position was open for, which claims only the duration. `tests/test_chart.py` pins it as a property of the whole document: every line is either a vertical wick or a horizontal level, so a sloped one cannot appear without failing.

**The levels span only the bars the leg carried them, and `initial_stop` is the stop as placed.** A stop line drawn across the whole window would claim a bracket that did not exist before the fill. A stop line drawn across the whole *hold* is honest for a fixed bracket and a lie for a trailing one, since a trailed stop's path is nowhere in the trade log — InsideBarTrailing is the case, and the label says "stop" rather than "the stop" for it.

**The excursions are the point rather than a decoration.** MAE and MFE put the target against where price actually went while the position was open, which is the question §M27.3 left standing: InsideBar's target distance is the largest axis on the holdout and the selection window cannot point at it. A chart cannot answer that — a few dozen trades read by eye is not a measurement — but it is the cheapest way to see *what shape* the answer has before a sweep is designed around it. The caveat travels with the number: MAE and MFE here are this project's definition and not NT8's ([#70]).

**A fill outside its bar is drawn rather than refused.** `annotate` refuses one, because a price hundreds of points outside its bar is what a back-adjusted series produces and every downstream comparison would be silently wrong. A chart is the instrument that makes that visible, so refusing it here would suppress exactly the picture worth looking at: the price domain is fitted to include every drawn price, and the marker lands on the panel far from its candle. The series is named in the corner of every chart from `Dataset.price_basis` for the same reason.

**Bars of a different series are refused, and through the annotation's own check.** `annotate.resolve_bars` was made public rather than copied: it resolves each fill to a bar from the log's own indices where it has them and from its timestamps where it does not, and it cross-checks both against the dataset. A second copy would eventually disagree, and the disagreement would be a chart drawn over bars an annotation would have rejected — plausible at every stage and wrong at every price.

**SVG, hand-written, and no plotting dependency.** Every dependency is pinned exactly and CI resolves a fresh environment on every run, so a chart library is a standing cost paid on every build for a few hundred lines of geometry. Writing the document directly also makes the output *assertable*: a test parses the XML and checks that the stop marker sits at `plot.y(stop_price)`, which is a property, where a rendered raster could only be compared against a stored image. `Plot` is public so a caller can overlay its own marks on the same axes.

**No CLI command.** The CLI covers the four pipeline steps by design, and a chart takes a trade log and a prepared `Dataset` — neither of which survives being flattened into argparse flags. `chart.charts(log, data, ids)` and `TradeChart.save(path)` are the interface.

**The indicators are drawn, and the module still knows nothing about archetypes** ([#273]). The original objection was that which indicators are relevant is per archetype — true, and it rules out a chart that names any. It does not rule out one that draws what its `Dataset` holds: `sweep.prepare_for` builds exactly what the archetype's `ContextSpec` declares, so the dataset *is* that archetype's own statement of what its signal reads, and `chart.overlays_for(data)` turns it into a set of overlays without asking what produced it. A caller wanting three of them names three — `chart.moving_average`, `chart.bollinger`, `chart.session_vwap`, `chart.vwap_band`, `chart.higher_timeframe_average`, `chart.opening_range` — and one asking for a series the dataset does not hold gets the `ContextError` naming the spec field to set, which is the same refusal every other reader gets.

Four decisions travel with it, each of which would otherwise draw a plausible and wrong picture rather than raise:

- **An overlay does not widen the price domain; it is clipped to the panel.** Fitting one would let a long average sitting far from the window squash the trade it was drawn as context for — the opposite of the point. The clip is an SVG `clipPath` over the panel rect, so a line that leaves simply stops.
- **That clip path is named after its own rectangle, because an SVG id is document-scoped and a page of charts is one document.** A fixed name was written first and was wrong within the hour: twelve charts inlined into one contact sheet each defined `id="nqbt-panel"`, every `url(#nqbt-panel)` resolved to the first, and every chart after it was clipped to the narrowest panel on the page. The failure is silent and reads as a bug in the data — the series appear to stop a quarter of the way along, while their coordinates are correct to within a bar. Hashing the rectangle means two ids collide only where the two rectangles are identical, which is the one case where sharing a clip path is right. `tests/test_chart.py` pins it, and M12's web GUI is the reason it matters beyond a scratch page.
- **An overlay is a per-bar series, not a path between two points**, and that is what the no-sloped-line pin becomes now that a moving average is allowed to slope. Wicks and levels stay `line` elements; an overlay is a `polyline` whose vertices sit on the bar-centre grid and step one bar at a time, so the segment from an entry fill to an exit fill cannot be drawn as an overlay either. `tests/test_chart.py` asserts the step, not the tag name.
- **`nan` is a gap rather than a value, which is what keeps a per-session level off the session beside it.** The opening range is one fact per session; a run joining one session's level to the next's would state a level that never existed. `chart.opening_range` is null wherever `range_armed` is false, and the break falls out of that — every session has one, because a range is not armed before its window completes.
- **The trade's own geometry is dashed and the market's context is solid.** The bracket and the excursions were already dashed; overlays are solid, cycled through six colours, and named in a legend that makes its own room above the panel. Colour is positional rather than semantic, so the legend is what identifies a line.

**Price-panel series only, and that is the boundary rather than the current extent.** An ATR, an efficiency ratio, a relative volume or a compression rank is not a price and would need a second panel — which is ruled out below for volume, for the same reason. Nothing here builds a series: an overlay reads what `context.prepare` already computed.

**What it deliberately does not draw**, each for its own reason: volume, because a second panel doubles the layout for a quantity `review.time_of_day` already reports properly; and notes, because §M11.5's sidecar attaches at `notes.alongside` and a chart that grew a note argument would be a fourth door onto the same hazard.

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

Two things M20a deliberately did **not** change, because M20 may not move a number: `stats.py`'s silent branch computing Sharpe and Sortino per trade rather than per day for a log with no times ([#81]) — unreachable today, same shape as the empty-log defect, and since closed by § "Sharpe and Sortino are refused rather than approximated" — and `verification/explain_2024Q1.csv`, annotated rather than regenerated, because it is the record of what the audit trail said while it was being trusted.

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

The rest, in descending order of value: `sweep.SWEEPABLE` reads `__slots__` rather than `dataclasses.fields()` ([#60]) and will break quietly at M17 by dropping an axis rather than raising; `results.best()` interpolates `by` into SQL ([#61]); and `explain.py` and `cli.py` are untested ([#64] — `explain.py` gained `tests/test_explain.py` during M20a, so this is now `cli.py` alone).

**~~The repeated `bars[...].to_numpy(np.float64)`~~ ([#62]) — done.** `nqbt/arrays.py` carries `float_column` and `ohlc` beside the aliases, and every bar-column read in `conditions.py`, `context.py`, `higher_timeframe.py` and `splice.py` goes through them, so the dtype is chosen in one place rather than restated at each call site. **It is `ohlc` and not the `ohlcv` the ticket named, because volume is ingested as `int64`** — widening it is a full column copy, and folding it into the tuple would have charged that to every caller, where `conditions.py` never reads volume at all and `prepare` reads it only for a volume grid or the session VWAP. The four price columns are already `float64`, so converting all four and discarding three costs nothing, which is what makes the single-column `float_column` worth having beside it rather than instead of it. Behaviour held: the trade-log gate is byte-for-byte identical across all fourteen files.

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

## Replaying a prop account over the trade log

`nqbt/propaccount.py` ([#75]). Profit factor cannot say whether an account survived, and survival is what decides whether a strategy can be funded at all. The instrument replays one firm's rules over a trade log and reports what a live-trading decision actually reads: whether the account passed, where the floor sat when it died, and what the sequence of attempts was worth after fees. The measurements that pulled this forward from a reranking convenience to the go/no-go instrument are in [#75]'s own comment thread; they are dated and re-derivable from `results/campaign/*.duckdb`, so quote them from there rather than from here.

**It replays account rules; it does not add any.** Nothing in this module reaches into `nqbt/sim/`, and nothing may. The simulation models exactly one prop-firm rule — flat before the session close — because that one is also NT8's behaviour, and both prop and non-prop accounts have to work. A trailing threshold is not a trading rule, it is an accounting rule applied afterwards to a log that already exists; wiring one into the simulation would make every result conditional on a funding arrangement.

### Two axes, because one is not enough

Firms disagree about the trailing threshold in two independent ways, and collapsing them loses the commonest real configuration.

- `trail_basis` — what advances the **high-water mark**. Apex counts open equity, so a trade's best excursion raises the floor even after it gives it all back. TopStep advances it only on the day's closing balance.
- `trail_breach` — what the **floor is tested against**. Both firms liquidate on open equity.

TopStep's actual rule is the mixed case: an end-of-day high-water mark, breached intraday. One enum cannot express it, which is why there are two. TakeProfitTrader's evaluation is the same shape, and its funded account is Apex's.

`daily_loss_basis` is the same question asked of the daily loss limit, kept separate because a firm may count open equity for one limit and not for the other.

### Three assumptions, all made where bar data cannot decide

Each is the harsher reading. That is deliberate: this is a go/no-go instrument, and an optimistic account model is worse than no account model.

1. **A trade's peak is applied before its trough** — `excursion_order`, which **defaults** to that and is the one of the three that is a parameter rather than a fixed choice. Bar-close OHLC cannot order the two, and applying the peak first raises the floor before the trough is tested against it; the other ordering can only ever be kinder. It was fixed until §M28.13 measured what it was worth and found it too load-bearing to leave hard-coded.
2. **A trade tripping both limits at once is read as a trailing breach**, which ends the account, rather than as a daily breach, which under `DailyBreach.LOCKOUT` would not. Same reason, and the same inability to order two events inside one trade.
3. **The adverse excursion is summed over a trade's legs**, rather than taken as the trade's worst excursion at its full entry size. A leg that scaled out early stopped accruing excursion, so the per-leg sum is the closer of the two available answers.

**The excursion comes from `mae_points` and `mfe_points`, which are bar highs and lows.** Reaching into `data/tick/` for a truer open-equity path is the more-precise-than-NT8 error wearing a new hat, and it is refused for the same reason a chart may not draw a path between two fills. A rule set that reads open equity refuses a log whose excursion columns are null rather than treating "unknown" as "none" — that substitution would report a pass the account never had.

### The trading day is the exchange's, not the calendar's

A daily loss limit resets at the session open, so the replay groups by `sessions.classify(...).trading_day`. `stats.summarise` groups its daily totals by calendar date instead, and that is not an inconsistency to fix: Sharpe is annualised from a count of calendar days, while a daily loss limit is a session rule. The two disagree every evening between 18:00 and midnight Eastern, which is why each uses the definition its own question needs.

### Passing, withdrawing, and what a blown account is still worth

An account that passes **keeps trading under the same rules**, and begins withdrawing everything above `starting_balance + withdrawal_threshold` at each day's end. That threshold is the safety net a firm requires a trader to leave behind. Accurate for Apex and TopStep; TakeProfitTrader is why "the same rules" is no longer a property of the module — see "A firm that changes its rules at the pass ships as two presets" below.

**`profit_split` is what reaches the trader, and it is not what leaves the account.** The firm takes the whole withdrawal out of the balance and pays a share of it, so `AccountRun.withdrawn` is the gross and `payout` is the share, with `net = payout − fees_paid`. Keeping the two apart is load-bearing rather than tidy: the consistency ratio is a share of what *the account* made, so crediting the trader's half to `withdrawn` would inflate every reported consistency figure by the firm's cut. It defaults to `1.0` rather than `0.0`, which is the one field where "no rule" is not zero — a firm paying `0.0` would be one that pays nothing.

**A withdrawal is not stopped from breaching the account.** Withdrawing lowers the balance without lowering the high-water mark, so a rule set combining no safety net with a floor that never locks walks the balance onto its own floor, and the next trade kills it. That is what such a rule set would really do; special-casing it would hide the footgun rather than the consequence. Every shipped preset leaves a net above its locked floor, and a test pins that for all of them.

The headline figure is **withdrawn minus fees**, across however many attempts `max_accounts` allows. A strategy that blows three accounts while withdrawing more than the four of them cost is profitable, and ranking it by whether any single account survived would say the opposite.

### Where the preset numbers came from

**Dated, and not quotable terms.** Published rules and prices move, discounts on evaluation fees are close to permanent at one of these firms, and nothing here re-checks them. Every field is overridable with `dataclasses.replace` for exactly that reason, and a decision resting on a preset should re-read the firm's current terms first.

| field                                                                 | standing                                                                                                              |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| starting balance, profit target, trailing threshold, daily loss limit | published account terms, and the most stable of them                                                                  |
| consistency ratio, minimum trading days                               | published, and the ones most often revised                                                                            |
| Apex `withdrawal_threshold`                                           | the published safety-net balance                                                                                      |
| TopStep `withdrawal_threshold`                                        | **a conservative stand-in** — set to the trailing threshold, since TopStep's payout policy is not a simple safety net |
| TakeProfitTrader `withdrawal_threshold`                               | the published buffer zone, which the firm defines as equal to the drawdown                                            |
| Apex and TopStep fees                                                 | **list prices** — override them, especially Apex's                                                                    |
| TakeProfitTrader monthly fees                                         | the **discounted** price, not the list one — see below                                                                |

**TakeProfitTrader's presets carry the discounted subscription rather than the list price**, which is the opposite of the choice made for the other two firms and is deliberate. The list prices are $150 / $170 / $360 at 25K / 50K / 150K; a 40% discount code has been continuously available for years, so $90 / $102 / $216 is what an account actually costs and the list price is the fiction. Apex's discounts are as reliable and are *not* baked in, because that preset predates the decision — re-check both against the firm's current terms before a figure decides anything.

**Its commission is not the project's $1.50.** TakeProfitTrader charges $4.50 per round trip per full-size contract and $1.50 per micro, so a TPT replay of an **NQ** log costed at the project's usual figure is understating commission threefold. That is the standing free-money trap arriving through a preset rather than through a default, and `propaccount` cannot catch it: costs are applied when the trade log is produced, long before an account replays it.

### A firm that changes its rules at the pass ships as two presets

TakeProfitTrader runs an **end-of-day** trailing drawdown during the evaluation and an **intraday** one on the funded account, with the consistency ratio and the minimum-days rule applying to the first and neither to the second. One `AccountRules` cannot hold both, and the alternative to two presets — a phase-aware rule set — would put a second, conditional definition of the floor inside the module whose whole premise is that there is one. So `TPT_50K_TEST` and `TPT_50K_PRO` are separate accounts and a full picture reads both.

That difference is not cosmetic. §M28.13 measures the intraday basis and `excursion_order` as the single largest lever in the model on a full-size contract, so the funded preset is the harsher of the two by the largest margin any axis here produces.

Three consequences of the split worth stating, because each looks like a defect from one side:

- **The PRO preset's `profit_target` is `0.0`,** because a funded account has no target. The replay reads a pass as "eligible to withdraw", which is exactly right for a funded account that may withdraw above its buffer from day one — so a PRO run reports `passed` on its first profitable day and that is the model working, not a pass it did not earn.
- **The $130 activation fee is the PRO preset's `evaluation_fee`,** since it is what opening that account costs, and the Test preset's `activation_fee`, since it is what passing costs. The same $130 under two field names because it is charged at the boundary the two presets share.
- **What the Test preset does after it passes is a fiction** — it keeps trading under evaluation rules, because that is what the module does with any passed account. Read the Test preset for whether the evaluation is survivable and what it cost; read the PRO preset for what the funded account then does.

**`monthly_fee_ends_at_pass` exists for the same reason.** TakeProfitTrader's subscription is cancelled the day the account passes and the funded account carries no recurring fee, where Apex's and TopStep's run for the life of the account. Without the flag a passed TPT account would be billed monthly for the remaining length of the trade log, which on a multi-year log is a larger error than every other fee in the model put together.

### What is deliberately not modelled

- **TopStep's winning-day requirement** — N days each clearing a dollar floor. The consistency ratio catches the same pathology from the other side, which is a strategy that passed on one lucky session.
- **TakeProfitTrader's raised target when the consistency rule is missed.** Failing it does not end the evaluation there; it lifts the target to twice the net P&L until the best day is back inside the ratio. The replay re-tests the pass every day and never records one until every condition holds at once, which reaches the same verdict by a different route — an account that would have had its target raised simply has not passed yet.
- **Position-size limits, which TakeProfitTrader publishes per account size** (3/6/15 minis, ten times that in micros). Contract size is whatever the trade log says, as for every other firm here.
- **The prohibition on automated execution.** Both TakeProfitTrader's Universal Trading Policies and its PRO contract require every trade to be placed by hand. That governs how a strategy may be traded, not whether its trade log survives the account's risk rules, and the replay answers only the second.
- **Payout caps and cadence.** A withdrawal is taken whenever it is eligible, in full.
- **A funded phase whose rules differ from the evaluation's, *within one preset*.** One `AccountRules` covers both phases. Where a firm changes its rules at the pass, it ships as two presets instead — see above.
- **Scaling plans and position-size limits.** Contract size is whatever the trade log says.
- **The consistency rule at payout time.** It gates the pass only.

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

**Eleven strata per root, one dimension at a time.** Unfiltered, then once per regime, then once per session phase — not the 32 cells the product would give. Each label answers "no edge anywhere, or edge in one stratum drowned by the others?" on its own, and crossing them is what [#48]'s guard exists to refuse. Every stratum runs the same 96-combination grid, so the stratum is the only thing that varies between two comparable rows. **`ambiguity_policy` is not swept**: `0` is a blanket worst case, deliberately *more* pessimistic than NT8 rather than equal to it, so half the stored rows would have ranked a combination against a fill rule the prime directive rejects. The trade is that the 0.009 profit factor between the two policies came from the rows that were dropped and is no longer re-derivable from `combos`; re-add the axis to re-measure it, or re-run a shortlist under both policies, which is what §M28.3 does instead.

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
[#17]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/17
[#18]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/18
[#19]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/19
[#195]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/195
[#196]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/196
[#197]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/197
[#198]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/198
[#199]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/199
[#200]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/200
[#201]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/201
[#203]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/203
[#205]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/205
[#206]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/206
[#208]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/208
[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
[#23]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/23
[#235]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/235
[#236]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/236
[#237]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/237
[#239]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/239
[#24]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/24
[#248]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/248
[#25]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/25
[#251]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/251
[#255]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/255
[#256]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/256
[#258]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/258
[#261]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/261
[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
[#263]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/263
[#264]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/264
[#27]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/27
[#273]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/273
[#278]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/278
[#28]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/28
[#280]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/280
[#281]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/281
[#285]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/285
[#287]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/287
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
[#70]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/70
[#71]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/71
[#72]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/72
[#73]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/73
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
[#75]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/75
[#76]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/76
[#81]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/81
[#9]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/9
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
[#92]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/92
