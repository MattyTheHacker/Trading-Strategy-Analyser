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
- `MaxRiskPerTrade` is in **ticks**, not dollars.
- **A resting entry order is cancelled on a `force_flat` bar**, not tested for fill.
  `block_entry_at_session_close` guards only a *new* signal on that bar.

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
- **One archetype cannot exercise the fill model, and two are not enough either.** Each new
  entry mechanism reaches rules the others made unreachable *by construction*, and `bracket.py`
  inherits whatever is wrong — which is why each archetype earns its own reconciliation.
  `docs/roadmap.md` § "What M15.5 changed".
- **Stop-and-reverse is not supported.** The loop's `in_position` boolean assumes flat-to-flat
  and reversal collides with the one-bar entry lifetime. A deliberate limitation.
- **`EXIT_SIGNAL` is spent by EmaCrossover alone** — a rule-driven exit with no bracket level. A
  test guards structurally that DeadCatBounce, PullBackAndGo and `bracket.py` never import it.
- **`ratchet_offset_ticks` is separate from `stop_offset_ticks`**, and `above_series` is not
  `~below_series` — each C# treats its own equality boundary as a pass, so the two overlap at
  `close == ma` rather than partition it. `docs/nt8-fidelity.md`.
- **`PullBackAndGoParams`'s defaults reproduce the reconciled configuration, not the
  NinjaScript's** — `PullBackAndGo.cs` leaves seven properties uninitialised in `SetDefaults`.
  `use_vwap` stays off: nothing has checked nqbt's VWAP against `OrderFlowVWAP`.
