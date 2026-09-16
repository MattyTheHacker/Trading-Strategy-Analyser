---
id: M37
title: "M37 — EmaPullback's stop trailed on the slow average: the effect takes the window's sign"
archetypes: [EmaPullback]
issues: [313]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Trailing the stop on the slow average cuts session-close exits and holding time in every cell, but its profit-factor effect takes the window's sign — a cost on the selection window in seven of eight root x resolution cells and a gain on the holdout in six — so it clears the pre-registered paired bar in none; seven strata clear gate 2 on both roots against the fixed stop's four, and gate 3 fails for both arms at 1 of 60.
---

# M37 — EmaPullback's stop trailed on the slow average: the effect takes the window's sign ([#313])

[§M34](m34-ema-pullback-spec.md) places EmaPullback's stop on the slow average as it stood on the signal bar and never reads it again. This adds a mode that trails the stop on that same average and runs it against the fixed stop in one pass over [§M35](m35-ema-pullback-swept.md)'s grid. **The trail does what it was built to do in every cell — fewer exits at the session close, shorter trades — and what that is worth in profit factor depends on which window is asked**: a cost on the selection window, a gain on the holdout at five minutes and coarser, and a cost at two minutes in both. It clears the pre-registered bar nowhere, and gate 3 fails for both arms.

Every figure below is re-derivable from `results/campaign/EmaPullback.duckdb`, batch 3. It is a measurement of one dated run against the archive as it stood on 2026-09-16, not a standing property.

## The mode, and the three choices in it

The trail already existed — EmaCrossover's ratchet, carried over — but on a third average with its own kind, period and offset, so "trail the slow one" was one variant per `(slow_kind, slow_period)` pair with the trail pinned to match. `trail_on_slow` is that as one boolean. The rule and its NinjaScript are in `docs/nt8-fidelity.md` §M34; the reasons are here.

**A ratchet, not a follow.** A stop that followed the average back down would let a losing trade widen its own risk past the R it was sized on. In the thirty-trade review that prompted [#313] the slow average moved against the position over the trade's life once, so the ratchet gives up almost nothing against a follow — and it keeps `bracket.tightened_stop` the one comparison.

**One offset.** `stop_offset_ticks` places both the initial stop and every trailed one. With `trail_offset_ticks` read instead, a smaller trail offset moves the stop on the first trailed bar with the average unmoved — a move nothing in the market caused. Tied, the trail's only input is how far the average has travelled. `stop_offset_ticks` is not a swept axis in §M35's grid, so the tie costs no axis.

**A modifier on `trail_ma_stop`, not a three-valued mode.** `trail_ma_stop` is a stored column on every EmaPullback and EmaCrossover row, and a mode would rename it. The cost is that the modifier leaves three axes unread while it is on, which `dead_axes` could not see: an axis in `gated_by` can now name several toggles and is dead where any one of them is inert, and `archetypes.INERT_AT` records that `trail_on_slow` is inert at `True`. The third average is not built where every combination trails on the slow one.

**It arms at the entry bar's close**, EmaCrossover's cadence, where the average has moved one bar since the signal bar placed the stop. Arming only after the first target fills is a different rule and is not tested here.

## What was run

|                 |                                                                                |
| --------------- | ------------------------------------------------------------------------------ |
| **Arms**        | `stop=slow trail=off`, the fixed stop, and `stop=slow trail=slow`, in one pass |
| **Grid**        | §M35's 2,304 combinations in each arm, every axis shared                       |
| **Strata**      | §M35's 23, one context dimension at a time                                     |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                        |
| **Roots**       | MNQ and NQ, spliced continuous, the archive as re-ingested on 2026-09-16       |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage   |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                    |
| **Size**        | **1,695,744 combinations in 141.8 minutes** on twelve workers                  |

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants emapullback-trail --split \
    --strata emapullback-trail --resolutions 2 5 10 15 --n-jobs 12
```

## What will be read, stated before the run finished

Committed while the sweep was still running, so that nothing below could be chosen after a result had been looked at.

**The run.** §M35's grid, strata, resolutions, roots, costs and split, twice in one pass: `stop=slow trail=off`, the fixed stop, and `stop=slow trail=slow`, the same stop trailed on the slow average at `stop_offset_ticks`. Every axis is shared, so the two arms are the same 2,304 combinations in every cell and differ by the trail alone.

1. **The control is a reproduction first.** Every `trail=off` row must equal §M35's stored `stop=slow` row at the same root, resolution, window, stratum and parameters, on every stored statistic. A single difference is a defect, and nothing below is read until it is explained.
2. **The question is answered paired, not by a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, one row per root × resolution, **in the unfiltered stratum and in each window separately**. The trail is read as an improvement in a cell only where the median delta is positive *and* the sign test reaches p < 0.05 in **both** windows. The same pairing over all 23 strata is reported beside it as a description, not a test, because the strata share bars.
3. **The mechanism is read off the same pairs**: `session_close_share`, `win_rate`, `avg_bars_held` and `mean_r`, and the profit-factor delta by `slow_period`, since a faster average is one the trail can follow further.
4. **Gates 1 and 2 are §M35's, on each arm.** Gate 1 is the share of unfiltered configurations with a profit factor above 1 at 30 trades or more. Gate 2 is `tools/campaign_holdout.py`'s `passes` per root and stratum, run once per arm with `--variant`.
5. **Gate 3's family is the strata where `trail=slow` clears gate 2 on both roots**, at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. **Both arms are measured over that one family** — both roots, the best five configurations by selection-window profit factor, measured on the holdout, 400 draws, the over-bars draw — so a gate-3 difference belongs to the trail and not to a different set of cells. If no stratum qualifies, gate 3 is not run and that is the result.
6. **Nothing is added, dropped or re-cut after the first run.**

## Predicted before the run finished

- **The control reproduces §M35 exactly.**
- **The trail lowers `session_close_share` in all eight root × resolution cells in both windows**, and lowers `avg_bars_held` with it — the trail can only end a trade earlier.
- **It does not clear the bar in (2) in a majority of the eight cells.** EmaCrossover's trail cost profit factor in nineteen of twenty cells ([`build-spec-loose-ends-measured.md`](build-spec-loose-ends-measured.md)), and the runner the trail would protect is the leg the forced flat already closes at a small profit.
- **Its effect is largest at `slow_period = 30`** and smallest at 200.

**Two of the four were right.** The first was wrong for a reason outside the code — the next section — and the last is not borne out: the delta by `slow_period` has no monotone order in either window.

## The control does not reproduce §M35, because the archive changed under it

**Every statistic differs on roughly three rows in four** between `trail=off` and §M35's stored `stop=slow`. Read as step 1 requires, before anything else:

- **The archive and the continuous cache were re-ingested on 2026-09-16, before the sweep started.** Both roots now end on 2026-09-16 where §M35's ended on 2026-08-10, and NQ now starts on 2021-09-19 where it started on 2021-12-05. The 60/40 split point therefore moved — to 2024-10-09 on MNQ from 2024-09-17 — so both windows hold different bars.
- **On §M35's own bar span, the selection window reproduces exactly**: all 2,304 unfiltered rows, every statistic, on both roots at fifteen minutes. That is the check that the code moved nothing, on the sweep path the trade-log gate does not reach.
- **The holdout does not, even on that span, so bars inside it changed too.** Re-running the five held-out logs §M36's review stored: the ten- and fifteen-minute logs reproduce trade for trade, and all three two-minute logs depart in the middle of December 2025.

**So the defect step 1 exists to catch is absent, and §M35's and §M36's stored rows no longer reproduce on the current archive.** Both arms here ran on the same bars in one pass, which is what the paired reading needs; the `trail=off` arm is the fixed-stop reference on this archive, and nothing below compares against a §M35 figure.

## The paired question — cleared in no cell, and the sign is the window's

`tools/campaign_paired.py`'s pairing on profit factor, unfiltered stratum. Each cell holds one pair per configuration viable in both arms, at 1,775 to 2,232 pairs; `improved` is the share of pairs the trail raised. Every sign test is p < 0.001 except the two marked, and pairs inside a cell are not independent, so the p-values overstate:

| root | resolution | selection Δ PF | improved | holdout Δ PF   | improved |
| ---- | ---------- | -------------- | -------- | -------------- | -------- |
| MNQ  | 2m         | −0.021         | 29%      | −0.007         | 44%      |
| MNQ  | 5m         | −0.028         | 33%      | **+0.036**     | 73%      |
| MNQ  | 10m        | −0.017         | 39%      | **+0.036**     | 73%      |
| MNQ  | 15m        | −0.014         | 40%      | **+0.014**     | 57%      |
| NQ   | 2m         | +0.003 (p=.08) | 52%      | −0.003 (p=.02) | 47%      |
| NQ   | 5m         | −0.011         | 43%      | **+0.028**     | 70%      |
| NQ   | 10m        | −0.008         | 44%      | **+0.030**     | 69%      |
| NQ   | 15m        | −0.010         | 43%      | **+0.016**     | 58%      |

**No cell clears the bar in both windows.** The trail costs profit factor on the selection window in seven of eight cells and gains it on the holdout in six, and at two minutes it is a cost or a coin flip in both. Pooled over all 23 strata the pattern is the same, with the selection window a cost in all eight cells. The effects are small either way — a median of two to four hundredths of profit factor.

**The sign follows the window, not the configuration, and the obvious split says the opposite.** Bucketing each pair by the fixed stop's own profit factor in the same window says the trail mostly helps the configurations that lose and hurts the ones that win, in both windows — and that is regression to the mean, since the delta is taken against the value that chose the bucket. Bucketed by the fixed stop's profit factor in the **other** window instead, it reverses: at 5 and 10 minutes the holdout gain is roughly twice as large on configurations that were profitable on the selection window (+0.054 against +0.022 on MNQ at five minutes), and on the selection window at ten minutes the trail pays on configurations profitable on the holdout and costs on the rest. So the trail is not rescuing bad configurations; it pays in one period and costs in the other across the grid.

## What it does to a trade, which is the same in every cell

Unfiltered stratum, MNQ, selection window; the medians over configurations, fixed stop → trailed, and the median paired change in win rate. NQ and the holdout move the same way by similar amounts:

| resolution | exits at the session close | bars held | win rate | trades        |
| ---------- | -------------------------- | --------- | -------- | ------------- |
| 2m         | 11.2% → 5.4%               | 98 → 29   | −2.4 pts | 2,622 → 3,980 |
| 5m         | 18.6% → 11.0%              | 57 → 27   | −3.3 pts | 1,461 → 1,780 |
| 10m        | 24.8% → 16.1%              | 39 → 24   | −3.8 pts | 967 → 1,065   |
| 15m        | 30.7% → 20.7%              | 30 → 21   | −3.9 pts | 734 → 776     |

**The session-close share and the holding time fall in all sixteen root × resolution × window cells**, as predicted, and the win rate falls with them in all sixteen.

**The trade count rises in all sixteen, by half or more at two minutes, and that makes the comparison wider than the exit.** The loop enters only when flat, so a position the trail closes early frees the next signal, and the trailed arm trades signals the fixed stop was still holding a position through. The paired delta is therefore the trail's exit *and* the entries it lets in, not the exit alone — and at two minutes, where holding time falls from 98 bars to 29, the added entries are most of what changed.

**Drawdown follows the profit factor's window.** On the holdout at 5, 10 and 15 minutes the trail lowers the median paired maximum drawdown on both roots, by a sixth to a quarter; on the selection window at two minutes it raises it.

## Gates 1 and 2 on each arm

**Gate 1**, share of unfiltered configurations with a profit factor above 1:

| root | resolution | selection, fixed | selection, trailed | holdout, fixed | holdout, trailed |
| ---- | ---------- | ---------------- | ------------------ | -------------- | ---------------- |
| MNQ  | 2m         | 22.7%            | 16.8%              | 18.2%          | 11.9%            |
| MNQ  | 5m         | 42.9%            | 32.9%              | 23.7%          | **39.0%**        |
| MNQ  | 10m        | **61.4%**        | **55.2%**          | 18.2%          | 30.7%            |
| MNQ  | 15m        | **73.9%**        | **69.7%**          | 17.4%          | 25.4%            |
| NQ   | 2m         | 28.7%            | 28.2%              | 31.6%          | 26.8%            |
| NQ   | 5m         | **52.1%**        | 49.0%              | 38.3%          | **54.1%**        |
| NQ   | 10m        | **74.7%**        | **73.9%**          | 27.0%          | 38.9%            |
| NQ   | 15m        | **79.8%**        | **78.4%**          | 24.7%          | 32.4%            |

On the selection window the fixed stop is a majority in five cells and the trail in four; held out, the trail's NQ five-minute cell is the only majority in either arm. Same shape as the paired table: lower on the selection window everywhere, higher on the holdout from five minutes up.

**Gate 2**, `tools/campaign_holdout.py` per arm. The two arms hold the same combinations in every cell, so neither shortlist is a best-of-more:

| arm     | strata clearing on both roots                                                                                          | clearing per root | returning their drawdown      |
| ------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------- | ----------------------------- |
| fixed   | `phase=CASH_OPEN`, `phase=LONDON`, `phase=MIDDAY`, `volume=THIN`                                                       | 6 MNQ, 6 NQ       | MNQ `phase=CASH_OPEN`         |
| trailed | `phase=CASH_OPEN`, `phase=LONDON`, `phase=MIDDAY`, `phase=PRE_OPEN`, `compression=NORMAL`, `htf=BELOW`, `volume=HEAVY` | 9 MNQ, 10 NQ      | `phase=CASH_OPEN`, both roots |

**Seven strata clear on both roots under the trail against four under the fixed stop, and `phase=CASH_OPEN` returns its own drawdown on both roots** — 3.09 and 1.17 — which no EmaPullback cell had done on both. Gate 2 reads the holdout, which is the window the trail is better on, so this is the paired table's holdout column seen through a shortlist rather than a separate result. The unfiltered stratum fails in both arms.

## Gate 3 — 1 of 60 in each arm, and neither is evidence

The family, by rule 5: seven strata cleared on both roots under the trail, so the lowest mean held-out profit factor, `volume=HEAVY` at 1.136, was dropped against `htf=BELOW` at 1.139. Six cells × two roots × five configurations = **60 tests per arm**, ranked on the selection window, measured on the holdout, 400 draws. Configurations beating their own null, MNQ / NQ:

| stratum              | fixed | trailed |
| -------------------- | ----- | ------- |
| `phase=CASH_OPEN`    | 1 / 4 | 4 / 3   |
| `phase=LONDON`       | 2 / 5 | 4 / 4   |
| `phase=PRE_OPEN`     | 2 / 2 | 3 / 2   |
| `compression=NORMAL` | 1 / 1 | 3 / 1   |
| `phase=MIDDAY`       | 5 / 5 | 5 / 5   |
| `htf=BELOW`          | 0 / 2 | 0 / 4   |

**Gate 3 fails for both arms.** Each reaches p < 0.05 once, where sixty tests at that level give three by chance. The trailed arm's one is a profit factor of 78.8 on **five** held-out trades on NQ `htf=BELOW` — a degenerate row, not a result. The fixed arm's one is MNQ `phase=CASH_OPEN` at five minutes, 3.89 against a null of 1.09 over 30 trades, and its NQ twin clears nothing. **`phase=MIDDAY` beats its null in all five configurations on both roots in both arms, and reaches p = 0.05 in none**, on 14 to 17 trades — §M35's reading of the same cell repeated.

**The trail beats its null in 38 of 60 against the fixed stop's 30**, which is a description and was not a pre-registered test. The family was chosen on the trailed arm's gate 2, so the selection favours it.

**The binding constraint is the sample, as in §M35 and §M36**: median held-out trades 15 trailed and 14 fixed, and 43 and 45 of the 60 tests under 30.

## What this does not settle

- **Why the two windows disagree.** The trail pays where the fixed stop's median configuration loses — every holdout cell — and costs where it wins, and bucketing by the other window says that is a property of the period rather than of the configuration. This campaign does not identify what about the period decides it, so it cannot say which window the next one resembles.
- **The exit alone.** The trailed arm takes up to half again as many trades, so the paired delta carries the entries the earlier exit let in. A comparison over a fixed set of entries would separate them, and nothing here does.
- **Arming after the first target, and a follow.** Only the ratchet armed at the entry bar was tested; the two alternatives [#313] named are unmeasured.
- **The motivating cell.** The thirty trades that prompted [#313] came from §M36's fitted `volume=THIN@per_bar_20 q=0.10/0.90` cell, which this pass did not run — it ran §M35's raw strata.
- **The runner's missing target.** `target_r_multiples` still ends in `nan`, so leg 4 can leave only at the stop or the clock; that is a bracket question [#313] left out of scope.
- **One minute was not swept**, as in §M35.
- **Nothing is re-ranked.** EmaPullback remains `TIER1_ONLY` with no NinjaScript, and `docs/findings/README.md` is unchanged because nothing here reaches a recommendation.

Every figure here is one dated run over the archive as it stood on 2026-09-16, re-derivable from `results/campaign/EmaPullback.duckdb` plus `tools/campaign_sweep.py`, `tools/campaign_paired.py`, `tools/campaign_holdout.py` and `tools/campaign_null.py` — not a standing property.

[#313]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/313
