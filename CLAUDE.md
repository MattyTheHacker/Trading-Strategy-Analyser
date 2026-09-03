<!--
  Maintainer note (stripped before this file enters Claude's context, so it costs nothing).

  This file is deliberately short. Anything that only bites while editing one area of the
  codebase lives in .claude/rules/*.md with `paths:` frontmatter, so it loads only when a
  matching file is opened. Keep this file to what is true in every session regardless of
  which file is being touched, and keep it under ~150 lines.

  Do not paste measured figures in here. Name the doc section that produces them.
-->

# CLAUDE.md

Tier 1 research backtester for NQ/MNQ futures (`nqbt`). Sweeps parameters fast to produce a shortlist; **NinjaTrader 8 Strategy Analyzer stays the ground truth** and re-validates every survivor (Tier 2).

## Prime directive

**Match NT8's default fidelity exactly — do not exceed it.** Being more precise than NT8 is as much a bug as being less precise, because it makes the two tiers disagree in ways that cannot be attributed. Specifically: bar-close OHLC fills, no intrabar tick precision. Tick data exists in `data/tick/` and is deliberately **not** wired into the simulation.

When the C# and intuition disagree, the C# wins. When the C# and a real NT8 trade list disagree, the trade list wins.

This governs the **simulation** side only. The planned trade-review side analyses real fills, which are genuinely tick-precise; that is not a violation because nothing is being simulated. The trap is letting that precision leak backwards into `nqbt/sim/` — see `docs/roadmap.md`.

## Ground truth

- `ninjatrader-scripts/Strategies/DeadCatBounce.cs` (submodule) — the strategy source. **Check it is current before porting**; it has been ahead of the committed version before.
- `docs/nt8-fidelity.md` — every NT8 rule the simulation implements and the evidence for it, plus the live agreement rates. **Quote it rather than any figure repeated elsewhere**, because these numbers move whenever a fill rule changes. Read it before changing `nqbt/sim/`.
- `docs/roadmap.md` — the reasoning behind the order, the milestone findings, the standing rubric and the decision record. Read it before starting anything, and quote its sections rather than a summary of them.
- `CONTRIBUTING.md` — **the working agreement, and it is not optional.** Code style, naming, tests, coverage, linting, the trade-log gate, commits and pull requests. **Read it before writing code or opening a PR, every time** — not once and from memory. Where it and this file overlap, it wins on *how* to change the codebase and this file wins on *what is true about the domain*.
- **The issue tracker is where plans, ordering and status live** — not these files. `gh issue list`, and `gh issue view <n>` for `blocked-by`/`blocking`.
- An NT8 trade-list export (Strategy Analyzer → Trades → Export) is the only way to settle fill-semantics questions. Summary statistics hide them.

## The rest of the rules

Area-specific invariants live in `.claude/rules/` and load automatically when you open a matching file. Read the relevant one **before** writing code in that area — especially if you are creating a new file there rather than editing an existing one:

| File                   | Covers                                                                 |
| ---------------------- | ---------------------------------------------------------------------- |
| `simulator.md`         | NT8 fill semantics; the sign multiplier; the shared bracket engine     |
| `sweep-and-context.md` | The archetype registry, `ContextSpec`, sweep axes, results tables      |
| `stats-and-trades.md`  | Leg vs trade aggregation, R, the shared summary path, `validate_legs`  |
| `data-pipeline.md`     | Archive and exports, contract rolls, bar labelling, NT8 reconciliation |
| `indicators.md`        | Where TA-Lib disagrees with NT8, and which indicators are pinned       |
| `regression-gate.md`   | The trade-log gate and the three things that silently disable it       |

## Environment

Python 3.14 venv at `.venv`. Run tools as `./.venv/Scripts/python.exe -m ...`.

```bash
./.venv/Scripts/python.exe -m pytest
nqbt ingest | contracts | splice | run
```

The CLI covers the four pipeline steps and stops there **by design**. `nqbt run --explain N` is the NT8 audit trail and earns its keep; sweeps, reports and walk-forward are driven from Python because a `Grid` does not survive being flattened into argparse flags. Do not add commands that duplicate the Python API.

## True everywhere, whatever you are editing

- **Every position must be flat before the session close** — a prop-firm account rule, so it is not negotiable and not a parameter. Already implemented (`sessions.force_flat_mask`, `EXIT_SESSION_CLOSE`, `block_entry_at_session_close`) and matching NT8's `IsExitOnSessionCloseStrategy`; don't re-add it. The design consequence is that **maximum hold time is bounded by the session**, so any archetype needing an overnight hold is unbuildable — apply that while writing the Python, not at port time. `docs/roadmap.md`, "Flat before the session close", has the per-milestone consequences. It is also the *only* prop-firm rule modelled: both prop and non-prop accounts must work.
- **Entry orders live one bar.** NT8's managed approach cancels them, which bounds what an archetype can express. It is an unset parameter rather than a platform limit — `docs/roadmap.md` § "Order lifetime in NT8" — but the simulation keeps the one-bar lifetime because that is what the C# does.
- **NQ and MNQ share a tick size but their tick values differ 10×.** Everything monetary must go through `instruments.py`. Verified by running the same NQ bars through both specs: trade geometry identical, gross P&L exactly ×10 on every leg, per-contract commission unscaled.
- **Costs default to zero and a free-money result will not announce itself.** `--commission` and `--slippage` default to `0.0`, so any ranking done without setting them is not a realistic ranking. Real round-trip commission is **$1.50 per contract**, not the figure `docs/roadmap.md` carries in its older worked examples.
- **TA-Lib does not match NT8.** Use `indicators.nt8_*` for anything NT8 will be compared against — EMA, ATR, StdDev, Bollinger and Keltner all diverge, and Keltner is not the usual definition at all. `.claude/rules/indicators.md`.
- **Numba functions are `@njit(cache=True)`** — required so parallel workers reuse the disk cache.
- **Reasoning goes in `docs/`, not in the source.** Docstrings say **what** a thing is and stay short; arguments, measurements, decision records and traps live in `docs/roadmap.md` or `docs/nt8-fidelity.md` behind a one-line pointer, and every pointer must name a section that exists. This reversed an earlier "docstrings say why" rule (#105) — do not reintroduce it.

## Where things stand

**This file does not track status, and neither does `docs/roadmap.md`.** Both went stale on every landing when they did. The tracker is the answer:

```bash
gh issue list --state open                      # everything outstanding
gh issue list --state open --label next-up      # what is at the front
gh issue view <n>                               # blocked-by, blocking, sub-issues
```

Five standing facts that are not status and do not move:

- **Every registered archetype was swept across every axis it owned at §M27** — `docs/roadmap.md` §M27, the section to quote rather than any line here. **InsideBar is the only one that survives held-out selection *and* shows a positive excess over a matched random entry**, and what stops it is its bracket rather than its entry. ElasticBand's `band_source` is the one axis added since, and it clears the first of those two tests and not the second — §M26.4.
- **A failed campaign parks a configuration space; it does not retire an archetype.** Five of the six failed §M27 and **all six stay registered, swept and reconciled**. Before re-running a parked one, say what has changed since §M27 — a new condition, bracket, range or data — because a re-run with none of those is the same measurement with a new seed. `docs/roadmap.md` § "Parked is not abandoned".
- **Bar size is the largest lever and the moving averages are nearly inert.** Resolution explains an order of magnitude more profit-factor variance than any period or kind on every archetype, and each one's median configuration loses money at one minute. Tune the bar size and the exit geometry; not periods.
- **DeadCatBounce is unprofitable across every combination tested**, and **stratifying by regime or by session phase does not rescue it** — the one cell that clears a profit factor of 1 is ruled out in `docs/roadmap.md` § "Stored sweeps — dropped and re-run, stratified". **Decided: not a blocker** — it is the test fixture that proves the system works. Its entry rule is nonetheless measurably better than random (`nqbt/randomentry.py`), which is "there is signal; the loss is in costs, hold time or bracket geometry", not "the entry rule is worthless". Quote `docs/roadmap.md` §M7a for the numbers and the caveats that travel with them.
- **Roll dates are data-derived and deliberately not reconciled against NT8**, which merges on dates configured in its Database window — a setting, not a measurement. The residual risk is that a spliced result cannot be reproduced bar-for-bar around a roll.
