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

1. **The control is a reproduction first.** On MNQ its ten are §M31's ten (§M31.1), so its row must equal §M31's MNQ row — trades 123–126, profit factor 1.361–1.498, null 0.890–0.917, 10 and 10 of 10. On NQ nine of its ten are §M31's, so that row is compared and not required to match. A difference on MNQ is a defect, and nothing below is read until it is explained.
2. **An arm holds the cell** where at least six of its ten configurations reach p < 0.05 on both roots. It **keeps the direction only** where it does not hold but at least six of ten beat their null on both roots. Otherwise it **does not hold**.
3. **Profitability is reported and not read.** Profit factor and net-to-drawdown sit beside each row, and `session_close_share` and `ambiguous_share` from `campaign_holdout.held_out` over the same variant.
4. **The shortlist's side is reported, not restricted.** The ranking is §M31's, so a short configuration that ranks into the ten stays there. On the selection window one does on MNQ under the stop arm and two on each root under the target arm.
5. **The stop arm answers [#307].** If it holds, the cell is the archetype's. If it does not, the gate-3 result belongs to `stop=opposite` and every line quoting §M31 has to say so. The window and target arms are read by the same rule and reported beside it.
6. **Nothing is added, dropped or re-cut after the first run.**

## Predicted before the run

- **The control reproduces §M31 on MNQ exactly.**
- **The stop arm keeps the direction and does not hold.** Under `stop=opposite` the level draw moves the stop and every R target along with the range, so the excess there measures the entry and a range-derived bracket together; under `stop=atr` the bracket stays put and only the entry level moves.
- **The 5-minute window does not hold.** §M28.1 found it the weakest of the three windows on both windows of the split.

[#307]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/307
