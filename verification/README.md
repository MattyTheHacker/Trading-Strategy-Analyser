# Verification artefacts

Outputs kept from the NT8 reconciliation work. All of them are **nqbt's own output**, not NinjaTrader's — the NT8 trade list they were compared against was a one-off Strategy Analyzer export and is not stored here.

| file                               | what it is                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------- |
| `nt8_reconciliation_MNQ_03-24.csv` | **A pre-fix run. Do not read this as the reconciled result.**                    |
| `trades_2024Q1.csv`                | Leg-level trade log, `nqbt run` with costs applied                               |
| `explain_2024Q1.csv`               | Per-trade audit trail. **Also a pre-fix run — its trigger arithmetic is wrong.** |
| `ratchet_2024Q1.csv`               | Bar-by-bar stop ratchet for one trade                                            |

## The reconciliation file is mislabelled, deliberately kept

`nt8_reconciliation_MNQ_03-24.csv` was written **before** two fill-semantics fixes landed, so it does not show the 1143/1144 agreement `docs/nt8-fidelity.md` reports. Re-running the current code over the same contract reproduces it exactly — 1,168 of 1,168 legs — only when both fixes are switched back off:

```python
DeadCatParams(..., fill_limit_on_touch=True, ambiguity_policy=0)
```

Those two settings account for all 19 differences against a current run: 15 legs where a target filled on a touch rather than trading through (`IsFillLimitOnTouch = false`), and 4 where an ambiguous bar resolved to the stop rather than to whichever level sat nearer the open. Both counts match the evidence tables in the fidelity record exactly, which is what identifies the file as the *before* state used to diagnose those fixes.

It is worth keeping precisely because it pins that behaviour: if a future change to the fill logic stops reproducing this file under those two settings, something moved that should not have.

## The audit trail file is also pre-fix, for a different reason

`explain_2024Q1.csv` was produced by `explain.py` before M20a, when it recomputed the entry arithmetic independently of the simulation and got it wrong: the trigger was taken to be simply `Low[0]`, dropping the `min(Low[0], Close[0] − 2 ticks)` cap. So in this file `trigger`, `risk_points`, `risk_ticks` and `fill_type` are wrong on every row where the cap bound, and `initial_stop` is right on all of them — which is exactly why the file looks plausible and why the defect survived.

**Kept rather than regenerated**, on the same reasoning as the reconciliation file above: it is the record of what the audit trail actually said while it was being trusted. Nothing downstream depends on it, and no simulated P&L was ever affected — the defect was confined to the reporting tool, never to `deadcat.py`.

Measured over the *current* MNQ 03-24 window, the cap binds on **123 of 345 trades (35.7%)**, which is the "~⅓ of signals" `.claude/rules/simulator.md` records. The 50% figure in the issue and the roadmap came from a 200-trade sample of the shorter, pre-archive log; the rate is strongly subset-dependent — 80% over the first 20 trades, 48% over the first 100, 41% over the first 200 — because the capped signals are not evenly distributed through the window. Re-measure it against the whole log rather than quoting a prefix.

## Re-checked after the archive landed

The archive added ~38k bars of leading history to MNQ 03-24 and revised volumes elsewhere, which raised the question of whether the reconciliation still held. It does — but the check that establishes it is not the obvious one, and the obvious one is misleading.

Re-running the current code under `fill_limit_on_touch=True, ambiguity_policy=0` now yields **1,380 legs against the stored 1,168**. That is not a regression: the extra leading history starts the series on 2023-09-09 instead of 2023-12-07, so the simulation gets ~3 months of bars the stored run never saw and finds real signals in them. Comparing leg *counts* is therefore meaningless. Joining on `(entry_time, leg)` instead:

- all **1,168 stored legs are present**, none missing;
- `entry_time`, `exit_time`, `entry_price`, `exit_price`, `initial_stop`, `target_price`, `exit_reason` and `net_pnl` are **identical on every one**;
- the 68 extra legs inside the stored window are all before the stored run's first entry.

**The bar-index offset is *not* constant, and that is fine.** An earlier note here recorded a constant 38,265; measured across the window it actually drifts 38,279 → 38,296. The 17 extra bars are out-of-session stray prints the archive picked up — single-contract trades at 22:31 ET on a Saturday, and inside the 17:00–18:00 ET maintenance break. They shift the frame's positional index without being tradeable.

They do enter the indicator recursion, though, because `runner.prepare` computes over every row of the frame it is handed and does not filter by `in_session`. So the question of whether they perturb anything is a real one, and it was answered by measurement rather than argument: running MNQ 03-24 with and without its 47 out-of-session bars gives **1,380 legs either way, with no differing field on any of them**. The spliced continuous series never faces this at all — `build_continuous` filters to in-session bars before splicing.
