---
title: "M55 — pre-registration: EmaCrossover's confluence count over filters that point the trade's way"
archetypes: [EmaCrossover]
issues: [74, 439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: EmaCrossover's confluence count over four gates — the cash-open and midday phases, and the trend, the higher-timeframe side and the VWAP side each required to point the trade's way — in nine arms per stop, the control, each gate alone and at least one to all four, unfiltered at 1, 2, 5, 10 and 15 minutes; an arm beats the control at a resolution only where, on both roots, the paired median profit-factor delta is positive with a sign test at p < 0.05 in both windows — §M37's bar, over a family of 80 — and gate 3, read family-wise as §M54 reads it, runs on the arms that clear.
---

# M55 — pre-registration: EmaCrossover's confluence count over filters that point the trade's way ([#439])

[The build spec's three loose ends](build-spec-loose-ends-measured.md) left the confluence count with one un-run test: **it has never been given filters that are individually informative.** Its three, `DIRECTIONAL`, `HEAVY` and `EXPANDED`, were chosen because each admits both sides alike, not because any separates EmaCrossover.

**Side-neutral filters cannot supply three.** In [§M28.14](m28-14-stratum-cross-read.md)'s cross-read only session phase separates EmaCrossover, `CASH_OPEN` and `MIDDAY` at +10 each, while relative volume is close to inert and the higher-timeframe side scores ±2. The labels [§M47](m47-confluence-sizing-10-15.md) kept as favourable for EmaCrossover — the trend, the higher-timeframe side and the VWAP side — are relative to the trade's side, and the context filters were side-blind masks. **#439 added filters that read those labels against the side the bar would be entered on**, on every archetype — `docs/nt8-fidelity.md`, "Filters relative to the trade's side". This counts them beside the phase.

**What has changed since the loose ends**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: the gates counted, and nothing else. The grid, the stops and the costs are the loose ends' own.

**This file was written and committed before the sweep started.** The arms, the gates, the cells, the bar below and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 9 per stop, in one pass (below)                                                                                                                                                         |
| **Grid**        | the loose ends' shared grid — `fast_period`, `slow_period`, `tp_multiplier`, `exit_on_opposite_cross` — under the ATR stop and the swing stop as variants, 32 combinations in every arm |
| **Gates**       | the phase at `CASH_OPEN` or `MIDDAY`, one gate; the trend, the higher-timeframe side and the VWAP side relative to the trade's side, each label at its default settings                 |
| **Strata**      | unfiltered alone, since a stratum is a filter too and would collide with the gates                                                                                                      |
| **Resolutions** | 1, 2, 5, 10 and 15 minutes, as the loose ends ran                                                                                                                                       |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                          |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                            |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                             |
| **Size**        | 11,520 combinations, both windows counted: minutes, not hours                                                                                                                           |

```bash
uv run tools/campaign_sweep.py --strategies EmaCrossover --variants side-count --split \
    --strata side-count --resolutions 1 2 5 10 15
```

### The arms

| arm           | gates on                  | entry needs          |
| ------------- | ------------------------- | -------------------- |
| `gates=none`  | none                      | the cross alone      |
| `gates=phase` | the phase                 | that gate            |
| `gates=trend` | the trend                 | that gate            |
| `gates=htf`   | the higher-timeframe side | that gate            |
| `gates=vwap`  | the VWAP side             | that gate            |
| `gates=1of4`  | all four                  | at least one of them |
| `gates=2of4`  | all four                  | at least two         |
| `gates=3of4`  | all four                  | at least three       |
| `gates=4of4`  | all four                  | every one            |

Each arm runs under `stop=atr` and `stop=swing`, and every name carries a `gates=` token no stored EmaCrossover row has.

### Measured before the run: what each gate leaves

The sweep rules ask for the signals a new entry gate leaves before it is crossed with anything. EmaCrossover's signals on MNQ's whole spliced series, two averages pairs at two bar sizes:

| bars | averages | none   | phase | trend | htf   | vwap  | ≥ 1    | ≥ 2   | ≥ 3   | all four |
| ---- | -------- | ------ | ----- | ----- | ----- | ----- | ------ | ----- | ----- | -------- |
| 5m   | 9 / 50   | 11,558 | 2,470 | 1,979 | 5,942 | 9,025 | 10,300 | 6,439 | 2,362 | 315      |
| 5m   | 20 / 200 | 3,592  | 1,067 | 2,839 | 2,098 | 3,306 | 3,560  | 3,260 | 1,960 | 530      |
| 15m  | 9 / 50   | 3,749  | 1,073 | 679   | 2,121 | 3,520 | 3,704  | 2,466 | 1,028 | 195      |
| 15m  | 20 / 200 | 1,105  | 394   | 892   | 1,103 | 1,054 | 1,104  | 1,083 | 924   | 332      |

**The VWAP side is mostly in force already**: a cross up usually closes above the session VWAP, so it keeps 78% to 98% of the signals. **The higher-timeframe side is inert at 15 minutes on the 200-bar average**, keeping 1,103 of 1,105. **All four together leaves 195 to 530 signals over the whole series**, so its held-out cells will often sit under the 30-trade floor. None of this changes the arms; it says where an arm can only read as its control.

## What will be read

1. **The effect is read paired, never off a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, each of the eight gated arms against `gates=none` under the same stop, one row per root × resolution, in the unfiltered stratum and **in each window separately**. Beside it: trades, win rate, average bars held, `session_close_share` and mean R. The pair count is printed and nothing is concluded from zero.
2. **The verdict is §M37's bar.** An arm beats the control at a resolution only where, **on both roots**, the median delta is positive **and** the sign test reaches p < 0.05 **in both windows**. Eight arms × two stops × five resolutions is a family of 80.
3. **The loose ends' own question is reported as description**: whether `gates=2of4` beats both of its neighbours, `1of4` and `3of4`, on held-out profit factor.
4. **Gates 1 and 2 are §M27's, per arm.** Every arm holds the same 32 combinations under a stop, so no shortlist is a best-of-more.
5. **Gate 3 runs on every arm, stop and resolution that clears (2)**: both roots, ranked within the arm with `--variant`, the best five configurations by selection-window profit factor, tested on the holdout, 400 draws, the over-bars draw. **The family is every one of those tests**, saved with `--out` and read with `--family-of` as §M54 reads its families. If nothing clears (2), gate 3 is not run, and that is the result.
6. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **No arm clears the bar in (2) at any resolution.** The loose ends found the count moving results without being edge, and EmaCrossover's held-out survival sits in its bracket rather than its entry (§M27).
- **`gates=vwap`'s paired delta is the smallest in size of the four single gates at every resolution**, since it leaves most signals where they were.
- **`gates=htf` under the 200-bar average reads as its control at 15 minutes**, on both roots.
- **The count arms order by trades**: `1of4` above `2of4` above `3of4` above `4of4` in every cell, and `4of4` under the 30-trade floor held out in most of them.
- **At one minute every arm's median configuration loses on both roots**, as every archetype's does there.

## What this run is not

- **Not the absolute trend and higher-timeframe filters**, which name one direction for both sides.
- **Not relative volume**, which §M47 found favourable for EmaCrossover only as a size and §M28.14 found inert as a filter.
- **Not the other archetypes.** The filters exist on all nine; only EmaCrossover's count is run here.
- **Not the labels' own settings.** Each label is read at its default; none is swept.
- **Not a port.** EmaCrossover has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
