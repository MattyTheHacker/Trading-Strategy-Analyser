---
id: M38
title: "M38 — OpeningRange's gate-3 cell read under the configurations it was never read under"
archetypes: [OpeningRange]
issues: [307]
gates: [3]
outcome: spec
verdict: >-
  Pending: the null is running, and this file holds only what will be read and what was predicted before it finished.
---

# M38 — OpeningRange's gate-3 cell read under the configurations it was never read under ([#307])

## What will be read, stated before the run

Committed before the null ran, so that nothing below could be chosen after a result had been looked at.

**The cell and the protocol are §M31's, unchanged.** `regime=DIRECTIONAL@n=20 q=0.20/0.80`, both roots, 5-minute bars, the ten configurations the selection window ranks highest by profit factor, measured on the holdout, 400 draws, `--draw levels`. No new sweep: every arm below is already stored, from the campaign grid §M31 ranked over.

**Five arms, each ranked within itself with `--variant`**, each moving one dimension away from the configuration all of §M31's shortlist came from:

| arm     | variant                                 | what moves       |
| ------- | --------------------------------------- | ---------------- |
| control | `window=30m stop=opposite target=R`     | nothing          |
| stop    | `window=30m stop=atr target=R`          | the stop mode    |
| window  | `window=15m stop=opposite target=R`     | the range window |
| window  | `window=5m stop=opposite target=R`      | the range window |
| target  | `window=30m stop=opposite target=width` | the target       |

**5 arms × 2 roots × 10 configurations = 100 tests**, 20 of them the control's re-measurement.

1. **The control is the reference the other arms are read against, not a reproduction of §M31** — amended below, before any arm but the control had run.
2. **An arm holds the cell** where at least six of its ten configurations reach p < 0.05 on both roots. It **keeps the direction only** where it does not hold but at least six of ten beat their null on both roots. Otherwise it **does not hold**.
3. **Profitability is reported and not read.** Profit factor and net-to-drawdown sit beside each row, and `session_close_share` and `ambiguous_share` from re-running each configuration on the same holdout the null runs on.
4. **The shortlist's side is reported, not restricted.** The ranking is §M31's, so a short configuration that ranks into the ten stays there. On the selection window one does on MNQ under the stop arm and two on each root under the target arm.
5. **The stop arm answers [#307].** If it holds, the cell is the archetype's. If it does not, the gate-3 result belongs to `stop=opposite` and every line quoting §M31 has to say so. The window and target arms are read by the same rule and reported beside it.
6. **Nothing is added, dropped or re-cut after the first run.**

### Amended after the control's MNQ cell, before any other arm ran

The plan first required the control to reproduce §M31's MNQ row exactly. **It could not: the archive was extended on 2026-09-16, after §M31 and before this run.** Both roots now end on 2026-09-16 rather than 2026-08-10, and NQ's history starts on 2021-09-19 rather than 2021-12-05, so the 60/40 split has moved and `campaign_null` measures a later and longer holdout than §M31's — from 2024-10-09 on MNQ and 2024-10-14 on NQ, against §M31's 2024-09-17 and 2024-09-25.

**The tools did not move; the archive did.** Cut back to its old ends, the series reproduces the stored bar counts exactly on both roots — 1,663,489 minutes on MNQ and 1,633,461 on NQ — and 13 of the control's 20 stored holdout rows exactly. The other seven keep their trade count and move by $16.00–$16.50 of net on MNQ and ten times that on NQ, which is one small price change showing up on both roots. No backup of the old series survives, so §M31's exact bars cannot be rebuilt.

**So every arm runs on today's holdout.** The ranking and the fitted cut are still §M31's, both read from the stored selection rows, and the new holdout starts after the stored selection window ends on both roots, so nothing is tested on bars it was ranked on. The control is re-measured on that window and the four other arms are read against it rather than against §M31's table.

## Predicted before the run

- ~~**The control reproduces §M31 on MNQ exactly.**~~ Void: see the amendment above.
- **The stop arm keeps the direction and does not hold.** Under `stop=opposite` the level draw moves the stop and every R target along with the range, so the excess there measures the entry and a range-derived bracket together; under `stop=atr` the bracket stays put and only the entry level moves.
- **The 5-minute window does not hold.** §M28.1 found it the weakest of the three windows on both windows of the split.

[#307]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/307
