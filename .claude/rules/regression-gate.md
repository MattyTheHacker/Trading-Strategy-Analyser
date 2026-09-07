---
paths:
  - "tests/**"
  - "tools/capture_trade_logs.py"
  - "tools/compare_trade_logs.py"
---

# The trade-log regression gate

`CONTRIBUTING.md` § "The trade-log regression gate" is the procedure. Four things it depends
on that are easy to undo:

- **numba's `cache=True` does not track cross-module dependencies**, so a change to
  `nqbt/sim/bracket.py` leaves every archetype's compiled loop holding the *old* inlined fill
  rules and the gate compares new source against old machine code. It reports no change because
  the change never ran. Measured on `AMBIGUITY_BEST_CASE`: identical source, caches deleted,
  different trade log. `tools/capture_trade_logs.py` purges `*.nbi`/`*.nbc` before each capture
  — **do not remove that purge to make a capture faster.** It disables the gate on exactly the
  file the gate exists to protect. `docs/roadmap.md` §M28.4.
- **`float_precision="round_trip"` on the read side is what makes the gate correct** — with it,
  either writer is exact. The `%.17g` on the write side fixes nothing on its own and, paired
  with a default parser, makes matters worse, because 17-digit text is what a lax parser
  mis-rounds. `float_precision="high"` fails the same way. Until #113 the gate read with a bare
  `read_csv`, so a one-ULP difference was invisible to it; `tests/test_trade_log_gate.py` pins
  that it cannot regress.
- **Verifying the gate can still fail is part of using it, and a pandas round-trip is the wrong
  way to do it** — perturbing a value via `read_csv`/`to_csv` trips a *collateral* difference
  and reports a column you did not touch, which reads like success. **Perturb the CSV text
  directly**, one field, and check the reported column is the one you edited.
- **Do not check a reconciliation by leg count** — join on `(entry_time, leg)`. See
  `.claude/rules/data-pipeline.md`.
