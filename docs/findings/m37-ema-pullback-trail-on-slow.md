---
id: M37
title: "M37 — EmaPullback's stop trailed on the slow average that placed it"
archetypes: [EmaPullback]
issues: [313]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Pending: the campaign is running, and this file holds only what will be read and what was predicted before it finished.
---

# M37 — EmaPullback's stop trailed on the slow average that placed it ([#313])

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

[#313]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/313
