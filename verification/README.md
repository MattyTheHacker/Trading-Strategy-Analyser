# Verification artefacts

Outputs kept from the NT8 reconciliation work, and one regression-gate capture. Only this README is committed; everything else here is gitignored and exists only on the machine that produced it (#91). The docs name these files in words, and this README is where their exact paths live (#368).

The four files at the top level are **nqbt's own output**, not NinjaTrader's — the DeadCatBounce trade list they were compared against was a one-off Strategy Analyzer export and is not stored here.

| file                               | what it is                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------- |
| `nt8_reconciliation_MNQ_03-24.csv` | **A pre-fix run. Do not read this as the reconciled result.**                    |
| `trades_2024Q1.csv`                | Leg-level trade log, `nqbt run` with costs applied                               |
| `explain_2024Q1.csv`               | Per-trade audit trail. **Also a pre-fix run — its trigger arithmetic is wrong.** |
| `ratchet_2024Q1.csv`               | Bar-by-bar stop ratchet for one trade                                            |

Five of the six folders hold **NinjaTrader's output**:

| file                                                               | what it is                                                                                                                                                                                          |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebar.csv`                    | The Trades export InsideBar is reconciled against — `docs/nt8-fidelity.md` § "Reconciliation result — InsideBar (#126, #157)"                                                                       |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebar_positionaccount.csv`    | InsideBar's first export, taken while the C# guarded on `PositionAccount` and NT8 reversed — `docs/nt8-fidelity.md` § "The position guard has to read `Position`, not `PositionAccount`"            |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebartrailing.csv`            | The Trades export InsideBarTrailing is reconciled against — `docs/nt8-fidelity.md` § "Reconciliation result — InsideBarTrailing (#127)"                                                             |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebartrailing_regression.csv` | The trading window's regression run, byte-identical to the export above — `docs/nt8-fidelity.md` § "Reconciliation result — InsideBarTrailing with the trading window (#349)"                       |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebartrailing_gate.csv`       | The trading window's gated run, 1 minute at `SetDefaults` — `docs/nt8-fidelity.md` § "Reconciliation result — InsideBarTrailing with the trading window (#349)"                                     |
| `nt8_trades/nt8_trades_MNQ_03-24_insidebartrailing_ported.csv`     | The ported midday configuration's export — `docs/nt8-fidelity.md` § "Reconciliation result — InsideBarTrailing with the trading window (#349)"                                                      |
| `nt8_trades/nt8_trades_MNQ_06-24_pullback.csv`                     | PullBackAndGo's export on its second contract — `docs/nt8-fidelity.md` § "Reconciliation result — PullBackAndGo on a second contract (#92)"                                                         |
| `nt8_trades/nt8_trades_NQ_03-24_deadcat.csv`                       | DeadCatBounce's NQ export — `docs/nt8-fidelity.md` § "Reconciliation result — NQ, the second instrument (#66)"                                                                                      |
| `nt8_trades/nt8_trades_MNQ_03-24_passedtarget_s1.csv` to `_s4.csv` | The Trades exports of the four `NqbtPassedTargetProbe` runs, scenarios 1 to 4 — `docs/nt8-fidelity.md` § "A limit order the market has passed fills at the nearest price the bar traded"            |
| `nt8_order_lifetime/<stem>_events.csv`, `_bars.csv`, `_config.csv` | One `NqbtOrderLifetimeProbe` run per stem — `docs/nt8-fidelity.md` § "Order lifetime and the session edge (#67)"                                                                                    |
| `nt8_passed_target/<stem>_events.csv`, `_bars.csv`, `_config.csv`  | One `NqbtPassedTargetProbe` run per stem — `docs/nt8-fidelity.md` § "A limit order the market has passed fills at the nearest price the bar traded"                                                 |
| `nt8_indicators/MNQ-03-24_1min_20231206_20240310.csv`              | NT8's own indicator values, one row per bar, from `NqbtIndicatorProbe` — `docs/nt8-fidelity.md` § "M16 — ATR, StdDev, Bollinger and Keltner, read out of NT8"                                       |
| `nt8_higher_timeframe/<stem>_primary.csv`, `_coarse.csv`           | One `NqbtHigherTimeframeProbe` run: the 1-minute bars with the 60-minute series beside them, and the 60-minute bars alone — `docs/nt8-fidelity.md` § "And so is the higher-timeframe average (#73)" |

The sixth, `gate-263b/`, is **nqbt's output** again: a `tools/capture_trade_logs.py` capture taken `before/` and `after/` one change, 14 files each and byte-identical between the two. No doc names it; its name and its date, 2026-09-09, match #263, which #268 closed that day.

## The reconciliation file is mislabelled, deliberately kept

`nt8_reconciliation_MNQ_03-24.csv` was written **before** two fill-semantics fixes landed, so it does not show the 1143/1144 agreement `docs/nt8-fidelity.md` reports. Re-running the current code over the same contract reproduces it exactly — 1,168 of 1,168 legs — only when both fixes are switched back off:

```python
DeadCatParams(..., fill_limit_on_touch=True, ambiguity_policy=0)
```

Those two settings account for all 19 differences against a current run: 15 legs where a target filled on a touch rather than trading through (`IsFillLimitOnTouch = false`), and 4 where an ambiguous bar resolved to the stop rather than to whichever level sat nearer the open. Both counts match the evidence tables in the fidelity record exactly, which is what identifies the file as the *before* state used to diagnose those fixes.

It is worth keeping precisely because it pins that behaviour: if a future change to the fill logic stops reproducing this file under those two settings, something moved that should not have.

### Two later fixes that the recipe leaves on

Reconciling PullBackAndGo in #87 found two more fill rules after this file was written. Neither has a setting, so the recipe above runs with both of them on:

- **A stop fills at the open when the bar gaps through it.** It moves legs on this contract, but #87 measured none of them inside this file's window: all 1,168 legs still matched on every field — `docs/nt8-fidelity.md` § "A stop fills at the open when the bar gaps through it".
- **A stop entry must sit beyond the market to be submitted.** DeadCatBounce cannot reach it, because its trigger is capped two ticks under the close — `docs/nt8-fidelity.md` § "A stop entry must sit beyond the market to be submitted".

## The audit trail file is also pre-fix, for a different reason

`explain_2024Q1.csv` was produced by `explain.py` before M20a, when it recomputed the entry arithmetic independently of the simulation and got it wrong: the trigger was taken to be simply `Low[0]`, dropping the `min(Low[0], Close[0] − 2 ticks)` cap. So in this file `trigger`, `risk_points`, `risk_ticks` and `fill_type` are wrong on every row where the cap bound, and `initial_stop` is right on all of them — which is exactly why the file looks plausible and why the defect survived.

**Kept rather than regenerated**, on the same reasoning as the reconciliation file above: it is the record of what the audit trail actually said while it was being trusted. Nothing downstream depends on it, and no simulated P&L was ever affected — the defect was confined to the reporting tool, never to `deadcat.py`.

Measured over the *current* MNQ 03-24 window, the cap binds on **123 of 345 trades (35.7%)**, which is the "~⅓ of signals" `.claude/rules/simulator.md` records. The 50% figure in the issue and the roadmap came from a 200-trade sample of the shorter, pre-archive log; the rate is strongly subset-dependent — 80% over the first 20 trades, 48% over the first 100, 41% over the first 200 — because the capped signals are not evenly distributed through the window. Re-measure it against the whole log rather than quoting a prefix.

## Re-checked after the archive landed

The archive added ~38k bars of leading history to MNQ 03-24 and revised volumes elsewhere, which raised the question of whether the reconciliation still held. It does — but the check that establishes it is not the obvious one, and the obvious one is misleading.

Last re-run on 2026-10-01, after #367 repaired the archive, through `tools/capture_trade_logs.py`'s first path. The current code under `fill_limit_on_touch=True, ambiguity_policy=0` yields **1,380 legs against the stored 1,168**. That is not a regression: the extra leading history starts the series on 2023-09-10 instead of 2023-12-07, so the simulation gets ~3 months of bars the stored run never saw and finds real signals in them. Comparing leg *counts* is therefore meaningless. Joining on `(entry_time, leg)` instead:

- all **1,168 stored legs are present**, none missing;
- every field is **identical on every one** except `trade_id`, `entry_bar` and `exit_bar`, which count from the earlier start;
- of the 212 extra legs, 144 are before the stored run's first entry and 68 after its last, so none fall inside its window.

Read the stored file with `float_precision="round_trip"`. pandas' default parser misreads 208 of its `r_multiple` values by up to 4.4e-16, which reads as a difference that is not there.

**The bar-index offset is a constant 38,265.** Before #185 it drifted 38,279 → 38,296 across the window, because 17 out-of-session stray prints inside it shifted the frame's positional index. `ingest.load_contract` has dropped those strays since #185, so the run never sees them. Before that, running with and without MNQ 03-24's 47 strays gave 1,380 legs either way, with no differing field on any of them.
