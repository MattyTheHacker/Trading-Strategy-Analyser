---
paths:
  - "nqbt/sim/**"
  - "tests/test_*_sim.py"
  - "tests/test_explain.py"
---

# The simulator

`docs/nt8-fidelity.md` § "Rules the simulation implements" is the evidence for every fill rule
below and is what you quote; this file is the index, not the record.

## NT8 fill rules

- The DeadCatBounce trigger is **`min(Low[0], Close[0] - 2 ticks)`**, not the bar's low. It binds on ~1/3 of signals.
- `IsFillLimitOnTouch = false`: a limit must trade **through**, so targets need `low < target`,
  not `<=`.
- **Ambiguous bars** (stop and target both in range) resolve to whichever is **nearer the
  open**. A blanket worst case is *more* pessimistic than NT8, not equal to it.
- **A stop that gaps fills at the open, not at the stop price** — a stop is a market order once
  triggered. This holds for **exits as well as entries**; the exit path missed it until M15.5.
  It does *not* apply on the entry bar: the position did not exist at that bar's open, so price
  had to travel through the trigger and only then back to the stop.
- **A stop entry at or through the market is never submitted.** `EnterLongStopMarket(High[0])`
  on a bar that closed on its high is not a stop order and NT8 declines it. DeadCatBounce is
  immune by construction — the `min(...)` cap puts the trigger below the close on exactly those
  bars — which is why this only surfaced once a second archetype used a bare `High[0]`.
- **Entry orders are not GTC**: NT8's managed approach cancels them after one bar. That is an
  unset parameter, not a platform limit — `docs/roadmap.md` § "Order lifetime in NT8" has the
  three routes and their costs. The simulation keeps the one-bar lifetime because that is what
  the C# does.
- **`IsFillLimitOnTouch = true` is InsideBar's, and its branch now has a trade list behind it.**
  Both other ports set `false`, so their targets need `low < target`; InsideBar needs
  `low <= target`. `docs/nt8-fidelity.md` §M22.
- **`OnExecutionUpdate` runs with the *signal* bar current, not the fill bar.** So `[0]` is the
  signal bar and `Low[1]` is the bar before it. Established at 100% of stop exits and 99.75% of
  target exits against an inference that had both one bar later — any archetype bracketing from
  `OnExecutionUpdate` inherits this. `docs/nt8-fidelity.md` §M22.
- **`ExitOnSessionCloseSeconds` does not move a backtest's flatten**, which lands on the
  session's last bar whatever the script sets. Carrying it per archetype was a regression;
  `exit_on_close_seconds=30` is one default. `docs/nt8-fidelity.md` §M22.
- **A position guard must read `Position`, not `PositionAccount`**, which never leaves Flat in a
  Strategy Analyzer backtest — InsideBar reversed on 2,581 of 21,884 trades until its C# was
  fixed. `docs/nt8-fidelity.md`, "The position guard has to read `Position`".
- **Out-of-session stray bars are flagged and not dropped**, so they sit in the array the
  simulation indexes and become `[1]` at a session open. Worth 25 legs of InsideBar's
  reconciliation; harmless to the two ports, which never read two bars back. `docs/nt8-fidelity.md`,
  "Reconciliation result — InsideBar".
- **The no-entry window before the close is not `block_entry_at_session_close`.** One is a
  parameterised window over `sessions.seconds_to_session_end`, the other guards a signal on the
  force-flat bar alone. The C#'s version reads the wall clock and so cannot be reconciled as
  written. `docs/nt8-fidelity.md`, "A no-entry window before the session close".
- `MaxRiskPerTrade` is in **ticks**, not dollars.
- **A resting entry order is cancelled on a `force_flat` bar**, not tested for fill.
  `block_entry_at_session_close` guards only a *new* signal on that bar.
- **The session end is the observed last bar, not the template's 17:00.** A CME half-day
  otherwise never reaches the cutoff and is never flattened at all, and the order resting from
  its last bar fills in the *next* session. `docs/nt8-fidelity.md`, "The session end is the
  observed last bar, not the template's".
- **`ExitOnSessionCloseSeconds` is per strategy, not one global 30.** Both stop-market ports set
  30 and both InsideBar scripts set 180. It lives on `Archetype` and `sweep.prepare_for` reads
  it; `context.prepare` called directly still defaults to 30 and has to be told.

## Structure

- **One sign multiplier `d = ±1`, never two code paths.** Every stop/target/fill/P&L/MAE/MFE
  comparison in `simulate_deadcat`, `resolve_brackets`, `entry_bracket`, `limit_filled` and
  `write_leg` runs through it. `sided()` is the one place that picks which raw OHLC value is
  adverse or favourable, because that is a data selection a sign multiplication cannot express.
  **Do not fork it for a new direction or archetype.** `docs/roadmap.md` §M15.
- **`bracket.py` is the shared bracket engine and `resolve_brackets` its one implementation**,
  called by both the in-position and entry-bar paths. **Do not fork either.** `entry_bracket`
  is likewise the single trigger/stop/risk computation, shared by the `@njit` loop and
  `explain.py`, so the audit trail is by construction the arithmetic under audit.
  `docs/roadmap.md` §M20a.
- **A new archetype writes the entry half only.** `CONTRIBUTING.md` § "Adding an archetype".
- **The loops' parameters travel as `NamedTuple` blobs declared in `bracket.py`** — `Bars`,
  `Costs`, `FillRules`, `OpenTrade`, `Legs`, `Excursion`, `LegExit`, plus one `*Rules` per
  archetype. **Do not add a loose scalar back to a signature**: ruff's `max-args = 10` is what
  every loop now sits under, and #59 is why. They must also stay in an **importable module** —
  a blob declared beside its loop writes a `cache=True` disk cache and then misses it on every
  run, silently, which costs the parallel workers their compile. `docs/roadmap.md` §M20c.
- **The four market-context filters live in `sim/filters.py`, not in each signal.** Session
  phase, regime, volume and trend are properties of the bars rather than of a strategy, so every
  archetype's signal ends with the one shared conjunction and a new one gets them by declaring
  the fields. **Do not inline the chain back into a signal.**
- **One archetype cannot exercise the fill model, and two are not enough either.** Each new
  entry mechanism reaches rules the others made unreachable *by construction*, and `bracket.py`
  inherits whatever is wrong — which is why each archetype earns its own reconciliation.
  `docs/roadmap.md` § "What M15.5 changed".
- **Stop-and-reverse is not supported.** The loop's `in_position` boolean assumes flat-to-flat
  and reversal collides with the one-bar entry lifetime. A deliberate limitation.
- **`EXIT_SIGNAL` is spent by EmaCrossover and InsideBarTrailing** — a rule-driven exit with no
  bracket level, and the second is the first with C# behind it. A test guards structurally that
  DeadCatBounce, PullBackAndGo, InsideBar and `bracket.py` never produce it, *and* that the two
  that should still do.
- **`ratchet_offset_ticks` is separate from `stop_offset_ticks`**, and `above_series` is not
  `~below_series` — each C# treats its own equality boundary as a pass, so the two overlap at
  `close == ma` rather than partition it. `docs/nt8-fidelity.md`.
- **The shared boolean MA grid is the wrong boundary for InsideBar**, whose C# tests positively
  so equality *fails*. It reads the raw values instead, which is what `needs_ma_values` buys.
- **The split-lot model sits beside `bracket.py`, not inside it.** `InsideBarTrailing`'s two
  lots resolve through `resolve_brackets` one at a time with the other legs masked out, so the
  engine takes one stop for the whole position exactly as it always has. Deliberate: the
  abstraction gets extracted when a second archetype needs it. `docs/roadmap.md` §M23.
- **A trailing stop is not the ratchet.** It follows the high-water mark by a fixed distance;
  the ratchet moves to a lagged bar's extreme. **It advances within its entry bar and at the
  close of every bar after**, which is two cadences and not one — a uniform within-bar rule
  costs 5.8 points of agreement. `docs/nt8-fidelity.md` §M23.
- **A C# guard clause belongs to its method, not to the branch below it.** `if (pnl > -200)
  return;` at the top of `OnPositionUpdate` gates InsideBarTrailing's *trend violation* as well
  as the dead max-loss check under it; reading it as the max-loss branch's own fired the exit
  340 times against NT8's 12. It is a **currency** amount, so it goes through `instruments.py`.
  `docs/nt8-fidelity.md` §M23.
- **An exit submitted from `OnPositionUpdate` is part of the triggering fill**, taking its bar
  and its price — not a market order at the next bar's open, which is §M18's rule for an exit
  decided in `OnBarUpdate`. Two different `EXIT_SIGNAL` semantics, and the archetype says which.
  `docs/nt8-fidelity.md` §M23.
- **`PullBackAndGoParams`'s defaults reproduce the reconciled configuration, not the
  NinjaScript's** — `PullBackAndGo.cs` leaves seven properties uninitialised in `SetDefaults`.
  `use_vwap` stays off: nothing has checked nqbt's VWAP against `OrderFlowVWAP`.
