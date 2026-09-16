---
id: M38
title: "M38 — OpeningRange's gate-3 cell belongs to the stop mode, not the window or target"
archetypes: [OpeningRange]
issues: [307]
gates: [3]
outcome: mixed
verdict: >-
  With the opposite-extreme stop the calibrated DIRECTIONAL cell clears p = 0.05 on at least eight of ten configurations on both roots at all three range windows and both targets. With the ATR stop its entry beats a matched random entry on all twenty configurations and reaches p = 0.05 on none, so §M31's result belongs to the stop mode rather than to the archetype.
---

# M38 — OpeningRange's gate-3 cell belongs to the stop mode, not the window or target ([#307])

**What has changed since §M31, stated first.** No new code, condition or sweep. §M31 put OpeningRange's `regime=DIRECTIONAL@n=20 q=0.20/0.80` through the matched null, and 19 of the 20 configurations it shortlisted were `window=30m stop=opposite target=R`, the twentieth the same with the width target (§M31.1). §M33 has since shown a context cell reversing sign when the configuration under it changes. This campaign reads the same cell under the stored configurations it was never read under, moving one dimension at a time.

**The answer is the stop mode.** With the opposite-extreme stop, the cell holds at every range window and under both targets. With the ATR stop, the entry still beats its null on every configuration and is significant on none.

## What will be read, stated before the run

Committed before the null ran, so that nothing below could be chosen after a result had been looked at.

**The cell and the protocol are §M31's, unchanged.** `regime=DIRECTIONAL@n=20 q=0.20/0.80`, both roots, 5-minute bars, the ten configurations the selection window ranks highest by profit factor, measured on the holdout, 400 draws, `--draw levels`. No new sweep: every arm below is already stored, from the campaign grid §M31 ranked over.

**Five arms, each ranked within itself with `--variant`**, each moving one dimension away from the configuration 19 of §M31's 20 shortlisted rows came from:

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

**The tools did not move; the archive did.** Cut back to its old ends, the series reproduces the stored bar counts exactly on both roots — 1,663,489 minute bars on MNQ and 1,633,461 on NQ — and 13 of the control's 20 stored holdout rows exactly. The other seven keep their trade count and move by $16.00–$16.50 of net on MNQ and ten times that on NQ, which is one small price change showing up on both roots. No backup of the old series survives, so §M31's exact bars cannot be rebuilt.

**So every arm runs on today's holdout.** The ranking and the fitted cut are still §M31's, both read from the stored selection rows, and the new holdout starts after the stored selection window ends on both roots, so nothing is tested on bars it was ranked on. The control is re-measured on that window and the four other arms are read against it rather than against §M31's table.

## Predicted before the run

- ~~**The control reproduces §M31 on MNQ exactly.**~~ Void: see the amendment above.
- **The stop arm keeps the direction and does not hold.** Under `stop=opposite` the level draw moves the stop and every R target along with the range, so the excess there measures the entry and a range-derived bracket together; under `stop=atr` the bracket stays put and only the entry level moves.
- **The 5-minute window does not hold.** §M28.1 found it the weakest of the three windows on both windows of the split.

**The second was right and the third was wrong**: the 5-minute window is the strongest arm in the family.

## The five arms, ranked on selection and tested on today's holdout

| arm        | root | trades  | profit factor | null        | excess          | beats null | p < 0.05     | median p | net/drawdown |
| ---------- | ---- | ------- | ------------- | ----------- | --------------- | ---------- | ------------ | -------- | ------------ |
| control    | MNQ  | 125–128 | 1.290–1.418   | 0.892–0.915 | +0.379 – +0.522 | 10 of 10   | **9 of 10**  | 0.025    | 2.122–3.069  |
| control    | NQ   | 118–122 | 1.406–1.455   | 0.890–0.941 | +0.469 – +0.565 | 10 of 10   | **10 of 10** | 0.010    | 2.759–3.551  |
| stop       | MNQ  | 119–136 | 0.684–1.085   | 0.598–0.884 | +0.079 – +0.208 | 10 of 10   | 0 of 10      | 0.272    | −0.972–0.709 |
| stop       | NQ   | 118–131 | 0.679–1.124   | 0.626–0.885 | +0.048 – +0.260 | 10 of 10   | 0 of 10      | 0.237    | −0.966–0.995 |
| window 15m | MNQ  | 123–132 | 1.507–1.596   | 1.118–1.187 | +0.323 – +0.468 | 10 of 10   | **8 of 10**  | 0.037    | 1.536–1.858  |
| window 15m | NQ   | 118–127 | 1.531–1.622   | 1.101–1.134 | +0.398 – +0.517 | 10 of 10   | **8 of 10**  | 0.030    | 1.639–1.941  |
| window 5m  | MNQ  | 134–146 | 1.553–1.684   | 1.003–1.052 | +0.539 – +0.647 | 10 of 10   | **10 of 10** | 0.005    | 2.216–3.268  |
| window 5m  | NQ   | 126–136 | 1.626–1.910   | 1.022–1.084 | +0.593 – +0.830 | 10 of 10   | **10 of 10** | 0.005    | 2.895–4.330  |
| target     | MNQ  | 119–128 | 1.084–1.489   | 0.821–0.918 | +0.263 – +0.581 | 10 of 10   | **8 of 10**  | 0.027    | 0.315–3.444  |
| target     | NQ   | 117–122 | 1.137–1.542   | 0.819–0.944 | +0.318 – +0.613 | 10 of 10   | **8 of 10**  | 0.010    | 0.546–3.942  |

**All 100 configurations beat their own null and 71 reach p = 0.05**, 52 of them among the 80 that are new. Nothing was refused. By the rule stated in advance, **four arms hold the cell and the stop arm keeps the direction only.**

**On today's holdout the control is weaker than §M31 measured it and still holds**: 9 and 10 of 10 where §M31 had 10 and 10, at an MNQ profit factor of 1.290–1.418 against §M31's 1.361–1.498.

## The stop arm: the entry beats its null every time and never significantly

- **Twenty of twenty configurations beat their null, and none reaches p = 0.05.** The nearest is 0.055 on NQ; the median excess is +0.152 on MNQ and +0.184 on NQ, against the control's +0.449 and +0.517.
- **It is not a sample-size verdict.** The stop arm trades 118–136 times per configuration held out, against the control's 118–128, and its entry rule is the same breakout of the same range under the same regime filter. The significance goes with the stop.
- **Its one short configuration is not what separates it.** Nine of MNQ's ten and all of NQ's are long, and the best long row on each root still reaches only p = 0.105 and 0.055.
- **It loses money, as §M28.1 would predict**: a median held-out profit factor of 1.004 on MNQ and 1.050 on NQ, and net-to-drawdown from −0.972 to +0.995.

**So the entry's edge over a random level is significant only when the range also sets the stop.** The prediction's mechanism would account for that — under the opposite stop the null's bracket is a donor session's range, under the ATR stop it is the session's own ATR — but nothing here separates the entry's share of the excess from the bracket's, so it is an explanation that fits rather than a measurement.

## Under the opposite stop the cell survives every window and both targets

- **The 15-minute window holds at 8 of 10 on both roots**, with a null that makes money on its own — 1.10 to 1.19 — and an excess still near the control's.
- **The 5-minute window holds at 10 of 10 on both roots, every configuration at the estimator's floor of p = 0.005**, with the largest excesses in the family: +0.54 to +0.65 on MNQ and +0.59 to +0.83 on NQ.
- **The width target holds at 8 of 10 on both roots, and the four configurations that miss are exactly its four short ones** — p = 0.060 to 0.150. Every long configuration under the width target reaches p = 0.05.

## The selection window orders the range windows backwards

Not part of the stated reading, reported because it bears on any later choice of window. Median profit factor of each arm's ten:

| window | selection MNQ | selection NQ | holdout MNQ | holdout NQ |
| ------ | ------------- | ------------ | ----------- | ---------- |
| 30m    | **1.646**     | **1.732**    | 1.354       | 1.425      |
| 15m    | 1.449         | 1.567        | 1.566       | 1.576      |
| 5m     | 1.243         | 1.276        | **1.658**   | **1.812**  |

**The order inverts completely, on both roots.** §M31's shortlist was all 30-minute because the selection window put that window first by a wide margin, and on today's holdout it is last. §M28.1 had already found the order of the two longer windows flipping between the windows of the split; inside this cell the shortest one flips as well.

## The two shares

| arm        | `session_close_share` MNQ | NQ          | largest `ambiguous_share` |
| ---------- | ------------------------- | ----------- | ------------------------- |
| control    | 0.728–0.805               | 0.727–0.803 | 0.000                     |
| stop       | 0.113–0.412               | 0.114–0.420 | 0.000                     |
| window 15m | 0.538–0.689               | 0.525–0.677 | 0.000                     |
| window 5m  | 0.326–0.448               | 0.337–0.461 | 0.019                     |
| target     | 0.626–0.707               | 0.611–0.701 | 0.009                     |

**Nothing is near `disambiguate.MIN_AMBIGUOUS_SHARE`.** The forced-flat share does not order the null result: the 5-minute window flattens the fewest legs of the four arms that hold and carries the largest excess, while the stop arm flattens fewer still and carries none.

## What [#307] asked, answered

1. **The cell holds only on `stop=opposite`.** Its gate-3 result belongs to the stop mode, and every line quoting §M31 has to name it.
2. **Within that stop mode it is not one configuration's.** It holds at all three range windows and under both targets, which is wider than §M31's shortlist could show.
3. **Under the ATR stop the entry still beats its null on every configuration**, so the reading is "significant only with the range as the stop" rather than "no edge without it".

## What this does not settle

- **This is today's holdout, not §M31's.** The control is re-measured rather than reproduced, and no figure here is set against §M31's table except as a comparison of two windows.
- **The null's excess means something different under each stop mode.** Under the opposite stop the draw moves the bracket with the level; under the ATR stop it moves only the level. Separating the entry's share from the bracket's needs a draw that keeps the session's own range width and moves only its placement, which does not exist.
- **Two dimensions were never moved together.** The 5-minute window under the ATR stop, or under the width target, is untested, and so is every other lookback of the cell.
- **The family is 100 overlapping tests, not 100 independent ones.** Ten configurations of one arm share bars and a filter, so counts sit beside ranges and are never pooled into a rate. A family-wise threshold is still untestable at 400 draws: the 5-minute arm sits at the estimator's floor of 2/401 on all twenty configurations and cannot show anything lower.
- **The 5-minute window's strength is not a shortlist anyone would have chosen.** The selection window ranks it last, so reading it as the cell's best configuration is selecting on the holdout.
- **No gate 4 and no exclusion read on any new arm.** §M31.1's finding that the control is profitable only with its session-close legs has not been checked on the 5-minute or 15-minute windows, whose forced-flat shares are lower.
- **Nothing is re-ranked and no archetype is revived or retired.** The stop arm keeping the direction is not a reason to sweep the ATR stop again; `docs/roadmap.md` § "Parked is not abandoned".

## Reproducing it

Once per arm, with the variant from the first table:

```bash
./.venv/Scripts/python.exe tools/campaign_null.py --strategy OpeningRange --root MNQ NQ \
    --stratum "regime=DIRECTIONAL@n=20 q=0.20/0.80" --resolution 5 --window selection \
    --test-window holdout --top 10 --iterations 400 --draw levels \
    --variant "window=30m stop=atr target=R"
```

Every figure here is one dated run over the archive as it stood on 2026-09-16, ranked on the rows `results/campaign/OpeningRange.duckdb` stored at §M31 — not a standing property. It cannot be reproduced after the archive next moves.

[#307]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/307
