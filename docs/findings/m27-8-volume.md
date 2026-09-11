---
id: M27.8
title: "M27.8 — volume: one form, one cut, and the answer is the cut's"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [206]
gates: [2, 3]
outcome: mixed
verdict: >-
  Which volume state helps is decided by the form and the cut rather than by volume; held out it is a coin flip, and `NORMAL` is the best cell under two forms of three.
---

# M27.8 — volume: one form, one cut, and the answer is the cut's ([#206])

The §M27 campaign's volume stratum was three values of one field. `_volume()` yielded `{"volume_filter": [state.bit]}` per state and moved nothing else, so **every volume row in every campaign database was produced at the `sim/types.py` defaults** — the `PER_BAR` form, a 30-bar window, a 20-session baseline and the thresholds 0.7 and 1.5. The five other volume axes never moved, and like session phase the result was never reported: §M27 contains no volume finding either.

## The raw pair is a different cut under each form, and at each resolution

§M10.2 says the thresholds "are conventional starting points, not a calibration" and predicted they would want different values at coarser bars. Measured on the selection window, the share of labelled bars each tail admits:

| root | bars | form            | below 0.7 | above 1.5 | fitted q20 | fitted q80 |
| ---- | ---- | --------------- | --------- | --------- | ---------- | ---------- |
| MNQ  | 1m   | per bar         | 27.3%     | 28.2%     | 0.602      | 1.828      |
| MNQ  | 1m   | rolling 30      | 17.5%     | 19.6%     | 0.727      | 1.487      |
| MNQ  | 1m   | session to date | 12.9%     | 14.5%     | 0.771      | 1.358      |
| MNQ  | 15m  | per bar         | 20.2%     | 22.3%     | 0.697      | 1.577      |
| MNQ  | 15m  | rolling 30      | 11.5%     | 12.7%     | 0.788      | 1.317      |
| MNQ  | 15m  | session to date | 13.0%     | 15.4%     | 0.770      | 1.376      |
| NQ   | 15m  | per bar         | 19.2%     | 18.9%     | 0.708      | 1.469      |
| NQ   | 15m  | rolling 30      | 9.5%      | 8.2%      | 0.807      | 1.252      |
| NQ   | 15m  | session to date | 11.8%     | 11.8%     | 0.786      | 1.290      |

**`HEAVY` is a 28%-of-bars population under one form and an 8%-of-bars population under another, at the same two numbers.** [#206]'s own premise — that 0.7 and 1.5 place roughly a fifth to a third of bars in each tail — is right for the per-bar form and wrong by a factor of three for the other two. The cut also moves with the bar size *within* a form, which is the defect §M27.5 records for the regime threshold arriving in a second place: cells cut by a raw pair cannot be read against each other across either axis.

So the thresholds are stated the way §M27.5 states the regime's — `volume.thresholds_from_quantiles`, fitted per (root, resolution, form) on the selection window alone, with the tail size as a cell dimension rather than an axis because the thresholds move with it. `--strata volume-forms` crosses three forms, three tail sizes and three states into 27 cells, and `volume.key` drops the rolling window from every form that does not read it, so the axis does not vary where it is inert — the `dead_axes` blind spot avoided by construction rather than rediscovered. It is a **re-cut** of the volume dimension rather than a new one, so `--strata all` leaves it out, as it already leaves out `directional`.

## Which state helps is decided by the form and the cut, not by volume

InsideBar, 5-minute bars, selection window, both roots, 864 combinations per cell — median profit factor and the share of combinations that made money:

| state  | per bar 10/90 | per bar 20/80 | per bar 33/67 | rolling 10/90 | rolling 20/80 | rolling 33/67  | to date 10/90 | to date 20/80    | to date 33/67 |
| ------ | ------------- | ------------- | ------------- | ------------- | ------------- | -------------- | ------------- | ---------------- | ------------- |
| THIN   | 0.883 / 23%   | 0.971 / 39%   | 1.047 / 66%   | 0.781 / 8%    | 0.902 / 11%   | 0.858 / **0%** | 0.875 / 14%   | 0.823 / 2%       | 0.958 / 40%   |
| NORMAL | 1.055 / 84%   | 1.035 / 75%   | 0.986 / 40%   | 1.067 / 94%   | 1.054 / 82%   | 1.098 / 97%    | 1.070 / 92%   | **1.134 / 100%** | 1.084 / 69%   |
| HEAVY  | 1.001 / 50%   | 1.038 / 64%   | 1.008 / 55%   | 0.992 / 49%   | 1.012 / 54%   | 1.051 / 73%    | 0.891 / 27%   | 0.935 / 30%      | 1.021 / 61%   |

The unfiltered control in the same cell is 1.032 with 71% profitable.

**Under the per-bar form `THIN` is the worst state at a tenth-tail and the best at a third-tail**, moving 0.883 → 1.047 while nothing but the cut changes. **Under the rolling form `THIN` is the worst state at every tail**, and at a third-tail not one of 864 combinations made money. `NORMAL` — the state that is not an extreme at all — is the best cell under two of the three forms at every tail, and its best cell has every one of its 864 combinations profitable.

**That is the answer to which of the three statements the survivor's edge belongs to: none of them.** The stored campaign reading is not reproduced at a fitted cut of its own form — §M27's `volume=THIN` is the best of its three states at 5 minutes (1.038, 66% profitable), and at the 20/80 fit of the same per-bar form `THIN` is 0.971 with 39% profitable while `HEAVY` is the best. A stratification whose ranking inverts when the cut moves three percentage points is reporting the cut.

## Held out, and it is a coin flip

Every cell through §M27.4's test — best 20 on the selection window, measured on the holdout, per root and per stratum, never pooled.

**16 of the 31 volume cells pass on both roots, and not one of them clears the drawdown check on either.** Passing is not stable within a state or within a form: `HEAVY` under the per-bar form passes at all three tails, under the rolling form at one of three, and under the session-to-date form at one of three. `NORMAL` under the per-bar form passes at one of three. Unfiltered passes too, on both roots, and also fails the drawdown check — so no volume cell buys anything the baseline did not already have.

Read against §M27.3, this is the same verdict from a second direction: **what stops InsideBar is the bracket, and no cut of the volume axis reaches it.** The drawdown column is failed by all 31 cells and by the unfiltered baseline alike.

## The clock and the volume label over the survivor's own trades

`tools/campaign_review.py` over the top unfiltered configuration at 5 minutes, its own selection-window log, 2,000 label shuffles, separation in expectancy — 2,413 legs on MNQ, 2,240 on NQ:

| condition                | separation MNQ | p MNQ     | family p MNQ | separation NQ | p NQ      | family p NQ |
| ------------------------ | -------------- | --------- | ------------ | ------------- | --------- | ----------- |
| `entry_phase`            | 87.5           | 0.112     | 0.125        | 1,023.7       | 0.059     | 0.065       |
| volume state, per bar    | 57.6           | **0.043** | 0.595        | 761.7         | **0.010** | 0.295       |
| volume state, rolling 30 | 50.2           | 0.135     | 0.769        | 443.9         | 0.269     | 0.902       |
| volume state, to date    | 28.0           | 0.552     | 0.994        | 750.2         | **0.036** | 0.316       |

**The three forms disagree about their own significance over one set of trades.** The per-bar form reaches a nominal p of 0.043 and 0.010, the rolling form nothing on either root, and the session-to-date form on one root only. Same trades, three views, three answers — §M10.2's decomposition finding restated as a p-value, and the reason a form cannot be chosen once and then reported as a fact about volume.

**Nothing survives the family-wise null.** Once the four conditions are shuffled together the smallest family p is 0.295. The holdout half is where the two questions part: the volume label's direction holds out on both roots under the per-bar form — `heavy` above `thin` in and out of sample — while `entry_phase`'s does not, its best in-sample stratum `cash_open` being the worst out of sample on both roots. **The clock separates and does not hold; the volume label holds and does not separate.**

## Absolute volume, which is the half a profit factor cannot see

§M10.2 settled that absolute volume is carried and never filtered on, and this does not reopen it. What it is for is the question no relative measure can answer, and the review reports it beside the clock. Median contracts in the entry bar of the same configuration:

| phase     | MNQ per bar | NQ per bar | MNQ session to date | NQ session to date | MNQ trades |
| --------- | ----------- | ---------- | ------------------- | ------------------ | ---------- |
| OVERNIGHT | 923         | 364        | 40,736              | 18,486             | 946        |
| LONDON    | 1,990       | 836        | 122,945             | 52,385             | 436        |
| PRE_OPEN  | 2,967       | 1,341      | 202,074             | 91,350             | 291        |
| CASH_OPEN | 21,224      | 11,545     | 388,930             | 199,656            | 154        |
| MIDDAY    | 9,367       | 5,400      | 739,349             | 382,144            | 372        |
| AFTERNOON | 8,612       | 5,408      | 1,079,614           | 540,453            | 214        |

**The survivor takes 39% of its trades in the phase with 4% of the cash open's depth.** A 5-minute overnight bar trades 923 MNQ contracts at the median against 21,224 at the open — a 23× difference that no profit factor in the campaign reports, and the phase carrying it holds twice the trades of any other.

That is a statement about where the trades are and not a fill model: bar volume bounds what could have traded and says nothing about the book. At one to four contracts the constraint is not binding anywhere in the table, and it is a fifth of a median overnight bar at 200 lots; where between those it starts to bite is not something these tables can say.

**On NQ against MNQ it settles the half of the comparison that is not arithmetic.** NQ trades roughly half MNQ's contract count in every phase and each contract is worth ten times as much, so **NQ is the deeper market by about 5.4× in notional** — 11,545 NQ contracts against 21,224 MNQ ones at the open. §M27 found NQ ahead on arithmetic rather than edge; this points the same way for a different reason.

## What the volume axis does not settle

- **One archetype.** The form and threshold sweep was run for InsideBar on both roots at all five resolutions, and the other six archetypes' volume rows are still the single cut. Their re-run is a flag rather than a change: `--strata volume-forms --volume-quantiles`.
- **The baseline window never moved.** `volume_baseline_sessions` is still 20 everywhere and `volume_rolling_bars` still 30 under the one form that reads it. Both are axes and neither has been swept; the form and the cut are the two [#206] argued were load-bearing.
- **Three tail sizes is not a calibration either.** A tenth, a fifth and a third are stated ahead of the sweep rather than fitted, exactly as §M27.5's pair is. What the fit buys is that a cell means the same share of bars under every form and at every bar size, not that the share chosen is the right one.
- **The family-wise null is over four conditions, not over the 31 cells.** The screen above asks whether the clock or a volume label separates one configuration's trades. Whether the best of 31 held-out cells beats the best of 31 draws is a different test and has not been run.

[#206]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/206
