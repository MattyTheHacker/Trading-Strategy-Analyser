---
id: M65
title: "M65 — OpeningRange's 1-minute campaigns on the October 2026 re-sweep: 2026 is now a small loss, and the entry's excess no longer peaks at a stop one range wide"
archetypes: [OpeningRange]
issues: [439]
gates: [2, 3, 4]
outcome: mixed
verdict: >-
  The four campaigns §M61 left waiting for 1-minute bars, re-read on the October 2026 re-sweep. The confined survivor's 2022 to 2025 reproduce to the dollar and 2026, now to 18 September, turns from a profit factor of 1.008 to 0.985 on MNQ and 1.002 to 0.978 on NQ, and no follow-through arm restores it. The break in gate 3 between 30 and 45 minutes holds and the wider stop still fails 2022. Two readings do not hold: the entry's excess over a permuted range now peaks at a stop of 1.5 to 2 range widths rather than 1, and a target-only arm now returns its drawdown.
---

# M65 — OpeningRange's 1-minute campaigns on the October 2026 re-sweep: 2026 is now a small loss, and the entry's excess no longer peaks at a stop one range wide ([#439])

[§M61](m61-registry-resweep-fill-fixes.md) re-read every older campaign except four that need 1-minute bars: [§M28.8](m28-8-range-cross.md), [§M28.10](m28-10-follow-through-geometry.md), [§M28.11](m28-11-truncated-bracket-axes.md) and [§M28.9](m28-9-survivor-tradeability.md)'s table by year. The re-sweep's 1-minute pass finished on 2026-10-29, so this file re-reads them the way they were first read and sets each figure beside its original.

## In plain terms

OpeningRange buys or sells the break of the day's opening range. Earlier work found it made money from 2022 to 2025 and nothing in 2026, and that adjusting its stop and target to recent market behaviour did not fix that.

**That still stands, and 2026 is slightly worse.** With another month of data the year is a small loss on both contracts. The earlier years came back identical to the dollar, and no way of scaling the bracket brings 2026 back.

**The earlier conclusions about which opening ranges work also hold.** The 15- and 30-minute ranges beat a random range and the 45- and 60-minute ranges do not.

**One conclusion moved.** A stop 1.5 to 2 range widths away now beats a random range by at least as much as a stop one width away. It still fails the check set in advance: in the one falling year, the wider stop made about the same money for up to two and a half times the drawdown.

**This does not make OpeningRange a better candidate.** Trading it live is still a bet that a past regime returns.

## What was read

The bars are the ones §M61 read: 2020-10-25 to 2026-09-18, the selection window ending 2024-05-13 on MNQ and 2024-05-10 on NQ. Costs are $1.50 per contract on MNQ and $4.50 on NQ, plus one tick of slippage, at four contracts. The original figures ran on an archive starting in 2022 and ending in August 2026, before the fill fixes, so a difference can be either.

**What reproduces shows how little the fills moved these rows.** All 860 of the geometry cross's arms reproduced every stored row their gate-4 read re-ran, and all 70 configurations re-run by year reproduced their stored held-out rows.

## §M28.9: 2026

The confined survivor: `cash+30m entry=breakout target=width`, long, stop one range wide, one entry per session, offset one tick, MNQ. The equity curve restarts each year, as §M28.10's tables do:

| year     | trades | profit factor |  net P&L | max drawdown | §M28.10                         |
| -------- | -----: | ------------: | -------: | -----------: | ------------------------------- |
| 2020     |     37 |         1.112 |      798 |        2,212 | before its archive              |
| 2021     |    185 |         1.387 |   15,793 |        4,797 | before its archive              |
| 2022     |    174 |         1.144 |    9,576 |        7,706 | identical                       |
| 2023     |    178 |         1.214 |    9,406 |        5,544 | identical                       |
| 2024     |    183 |         1.252 |   12,040 |        7,669 | identical                       |
| 2025     |    179 |         1.262 |   17,197 |        6,694 | identical                       |
| **2026** |    127 |     **0.985** | **−971** |   **22,625** | 110, 1.008, +441, same drawdown |

**Seventeen more trades take 2026 from a profit factor of 1.008 to 0.985, and the drawdown is unchanged.** On NQ the same year is 0.978 on −$13,748, against 1.002 before.

## §M28.10: nothing restores 2026

**The environment moved further the same way.** Median per session, MNQ:

| year | sessions | median 30m range | median follow-through | trailing@20 | trailing@60 |
| ---- | -------: | ---------------: | --------------------: | ----------: | ----------: |
| 2022 |      253 |            123.5 |                 1.183 |       1.172 |       1.197 |
| 2023 |      253 |             78.8 |                 1.171 |       1.139 |       1.153 |
| 2024 |      254 |             91.4 |                 1.239 |       1.249 |       1.242 |
| 2025 |      254 |            124.1 |                 1.043 |       1.086 |       1.039 |
| 2026 |      185 |            180.5 |                 0.906 |       0.913 |       0.895 |

§M28.10 had 186.0 and 0.960 in 2026, on 156 sessions. Between 2023 and 2026 follow-through has now fallen 23% and the range has risen 129%, so its arithmetic stands: a 0.77× correction cannot offset a 2.3× move.

Profit factor in 2026, `cash+30m`, the control against all nine arms:

| arm          | off   | target@20 | target@60 | target@250 | stop@20 | stop@60 | stop@250 | both@20 | both@60 | both@250 |
| ------------ | ----- | --------- | --------- | ---------- | ------- | ------- | -------- | ------- | ------- | -------- |
| §M28.10, MNQ | 1.008 | 0.961     | 0.971     | 1.001      | 0.987   | 1.022   | 1.031    | 0.943   | 0.987   | 1.024    |
| now, MNQ     | 0.985 | 0.944     | 0.944     | 0.980      | 0.991   | 1.016   | 1.007    | 0.949   | 0.976   | 1.002    |
| now, NQ      | 0.978 | 0.932     | 0.948     | 0.949      | 0.967   | 1.002   | 0.988    | 0.926   | 0.973   | 0.959    |

**The best arm is `stop@60`, at 1.016 on MNQ and 1.002 on NQ**, against 1.15 to 1.26 in the years before, and each of those is under $1,000 net against a drawdown of 23,535 and 244,232. Three arms clear 1.0 on MNQ and one on NQ.

**The drawdown check holds and has one more arm.** Held-out top 20 at `cash+15m`, ranked on the selection window, median net-to-drawdown, pooled over the bar sizes each arm was swept at:

| arm          | §M28.10, MNQ / NQ |     now, MNQ / NQ | clears now | `session_close_share`, MNQ |
| ------------ | ----------------: | ----------------: | ---------- | -------------------------: |
| `both@20`    |     2.026 / 1.710 | **1.954 / 1.826** | yes        |                      0.566 |
| `stop@20`    |     1.720 / 1.651 |     1.501 / 1.370 | yes        |                      0.475 |
| `both@60`    |     1.600 / 1.634 |     1.364 / 1.467 | yes        |                      0.582 |
| `stop@60`    |     1.615 / 1.614 |     1.260 / 1.376 | yes        |                      0.488 |
| `target@20`  |     0.982 / 0.914 |     1.104 / 1.011 | **newly**  |                      0.410 |
| `off`        |     0.763 / 0.897 |     0.640 / 0.624 | no         |                      0.297 |
| `target@60`  |     0.707 / 0.590 |     0.737 / 0.732 | no         |                      0.399 |
| `stop@250`   |     0.460 / 0.136 |     0.495 / 0.295 | no         |                      0.515 |
| `both@250`   |     0.459 / 0.136 |     0.556 / 0.292 | no         |                      0.616 |
| `target@250` |    0.195 / −0.041 |     0.077 / 0.070 | no         |                      0.414 |

**"No target-only arm clears it" no longer holds, by 0.104 and 0.011.** The ambiguous share of every shortlist here is at most 0.002, and the rank correlation of the four stop-side arms is 0.816 to 0.903.

**The stop's level still does the work.** At `cash+15m`, `stop@20` gains +0.066 to +0.113 held out in all six root × resolution cells, at p ≤ 0.007. At `cash+30m` it gains under 0.01 at 1 minute, with p above 0.8. §M28.10's direct comparison against a fixed fraction of the same size was a one-off run and was not repeated; the ladder below answers the same question.

## §M28.8: the range as a cross

**The shape holds at the medians.** Held-out median profit factor, 1-minute bars, readable rows, cash anchor, MNQ / NQ. The fills moved the fade, whose stop entry they reach, more than any other column:

| length | breakout, §M28.8 |     breakout, now |        retest |          fade |     rejection |
| ------ | ---------------: | ----------------: | ------------: | ------------: | ------------: |
| 5m     |    0.910 / 0.931 |     0.920 / 0.945 | 0.949 / 0.956 | 0.663 / 0.752 | 0.878 / 0.947 |
| 15m    |    1.026 / 1.044 | **1.014 / 1.026** | 0.988 / 1.015 | 0.672 / 0.697 | 0.818 / 0.866 |
| 30m    |    0.937 / 0.978 |     0.954 / 0.982 | 0.901 / 0.933 | 0.646 / 0.626 | 0.773 / 0.804 |
| 45m    |    0.917 / 0.978 |     0.942 / 0.968 | 0.900 / 0.922 | 0.797 / 0.805 | 0.906 / 0.924 |
| 60m    |    0.942 / 0.988 |     0.974 / 0.988 | 0.891 / 0.911 | 0.866 / 0.924 | 0.922 / 0.957 |
| 90m    |    0.924 / 0.970 |     0.943 / 0.954 | 0.898 / 0.921 | 0.902 / 0.905 | 0.872 / 0.924 |
| 120m   |    0.941 / 0.983 |     0.981 / 0.973 | 1.008 / 1.027 | 0.774 / 0.802 | 0.850 / 0.882 |

**The 15-minute range is still the only breakout length above 1.0**, and from 30 minutes up the medians sit at 0.942 to 0.981 on MNQ and 0.954 to 0.988 on NQ.

**The anchor and the length are still one cell.** Across the six anchors the breakout's MNQ spread falls from 0.242 at 5 minutes to 0.128 at two hours. Across lengths the cash open spreads 0.094 on MNQ and 0.081 on NQ against 0.175 to 0.218 and 0.138 to 0.192 for the other anchors. The cell's eta-squared exceeds the sum of the anchor's and the length's on all four entries and both roots, and the stop fraction outweighs both the anchor and the length on the breakout, fade and rejection.

**The forced flat is still not what produces the level.** Along the cash row `session_close_share` rises from 0.103 to 0.676, while the profit factor moves within 0.094.

**Gate 2 at 1 minute**, per entry, for cells whose shortlist is readable in both windows, MNQ / NQ:

| entry     | readable cells | passing |
| --------- | -------------: | ------: |
| breakout  |        86 / 86 | 10 / 26 |
| retest    |        76 / 71 | 22 / 30 |
| fade      |      128 / 128 |  9 / 16 |
| rejection |        74 / 73 |  5 / 15 |

**The retest still has the highest share and the fade among the lowest, now at about a third and about a tenth.** Far more cells are readable than §M28.8's 489 of 860: 722 here, and most of the new ones are the retest's and the rejection's, the two limit entries the fill fixes reached. §M28.7's trap is still there: `midday+5m entry=rejection target=R` returns a held-out profit factor of 39.6 on NQ at an ambiguous share of 0.79.

**The one-hour cash range now fails gate 2 at 1 minute on both roots under both target schemes**, at 0.969 to 0.999. §M28.8 read it passing on three of the four, over every bar size it was swept at, so this is not a like-for-like change.

### Gate 3: the break between 30 and 45 minutes holds

`matched_random_ranges` over the top 20 of `cash-open+<n>m entry=breakout target=width`, 1-minute bars, 100 draws, ranked on the selection window and tested on the held-out one. Medians over the twenty, MNQ / NQ:

| length | observed      | null          | excess          | p below 0.05, §M28.8 | p below 0.05, now | family-wise p of 40 |
| ------ | ------------- | ------------- | --------------- | -------------------: | ----------------: | ------------------: |
| 15m    | 1.058 / 1.069 | 0.953 / 0.970 | +0.119 / +0.075 |                7 / 8 |             7 / 5 |               0.030 |
| 30m    | 1.007 / 1.017 | 0.932 / 0.947 | +0.110 / +0.114 |               8 / 12 |           10 / 10 |               0.010 |
| 45m    | 0.996 / 1.002 | 0.957 / 0.967 | +0.035 / +0.040 |                0 / 0 |             0 / 0 |               0.762 |
| 60m    | 0.992 / 0.982 | 0.950 / 0.949 | +0.037 / +0.022 |                0 / 0 |             0 / 0 |               0.564 |

**Thirty-two of the eighty tests at 15 and 30 minutes clear p = 0.05 and none of the eighty at 45 and 60 does.** The excess is smaller than §M28.8's +0.159 to +0.195, and at 30 minutes it now clears family-wise. As in §M28.8 the null is flat across the lengths and the observation is what falls.

## §M28.11: the two truncated axes

**The stop axis holds, more narrowly at 15 minutes.** Held-out median profit factor over the 32 cells, 1-minute bars, `target=w1.0`, MNQ / NQ:

| `stop_range_fraction` | `cash-br+15m`, §M28.11 | `cash-br+15m`, now | `cash-br+30m`, §M28.11 | `cash-br+30m`, now |
| --------------------: | ---------------------: | -----------------: | ---------------------: | -----------------: |
|                  0.25 |          0.799 / 0.848 |      0.904 / 0.960 |          0.768 / 0.815 |      0.828 / 0.870 |
|                  0.50 |          0.967 / 1.007 |      0.986 / 1.004 |          0.927 / 0.957 |      0.948 / 0.960 |
|                  0.75 |          1.041 / 1.067 |      1.030 / 1.043 |          0.979 / 1.017 |      0.998 / 1.023 |
|                  1.00 |          1.133 / 1.156 |  **1.086 / 1.091** |          1.062 / 1.090 |      1.061 / 1.077 |
|                  1.50 |          1.089 / 1.099 |      1.083 / 1.086 |          1.080 / 1.109 |      1.079 / 1.096 |
|                  2.00 |          1.075 / 1.096 |      1.065 / 1.072 |          1.063 / 1.065 |      1.073 / 1.068 |
|                  3.00 |          1.090 / 1.104 |      1.079 / 1.085 |          1.092 / 1.109 |      1.110 / 1.121 |
|                  5.00 |          1.069 / 1.085 |      1.055 / 1.066 |          1.107 / 1.125 |  **1.130 / 1.143** |

**At 15 minutes 1.0 is still the maximum, now by 0.003 and 0.005 over 1.5. At 30 minutes the axis still climbs to the end of the ladder.**

**The default ladder is still the best at 30 minutes**, `(1.0, nan)` leading at every stop width from 1.0 to 5.0 on both roots. At 15 minutes the leader varies with the stop, between the runner, `w2.0`, `w1.0+2.0` and `w0.5`.

**The selection window still picks the target wrong.** Over the same 16 cells, it names the no-target arm in 15 and `w3.0` in one, and the holdout names `w1.0` in 10, the no-target arm in 4 and `w2.0` in 2. §M28.11 had 16 and 1, reading three ladders where this reads all six.

**The fixed fraction still reaches what the trailing scale reached.** Held-out top-20 net-to-drawdown, pooled over bar sizes, each arm drawn from four fractions, MNQ / NQ:

| variant                   | stored, ≤ 1.0, §M28.11 |   stored, now | extended, > 1.0, §M28.11 |     extended, now |
| ------------------------- | ---------------------: | ------------: | -----------------------: | ----------------: |
| `cash-br+15m target=w0.5` |          0.856 / 0.804 | 0.626 / 0.419 |            1.832 / 1.776 | **1.809 / 1.725** |
| `cash-br+15m target=w1.0` |          0.763 / 0.897 | 0.640 / 0.624 |            1.494 / 1.567 | **1.590 / 1.708** |
| `cash-br+30m target=w1.0` |          0.626 / 0.721 | 0.890 / 0.913 |            1.319 / 1.280 |     1.168 / 1.065 |
| `cash-br+30m target=w0.5` |          0.228 / 0.409 | 0.481 / 0.506 |            0.931 / 0.960 |     0.887 / 0.855 |

**The stored arm of `target=w1.0` is the same figure as `scale=off` above**, the two sets' same rows, and the extended arm is above `stop@20` on both roots. The extended 15-minute arms still hold out above their selection figure, and the 30-minute arm still falls below it: 1.193 / 1.188 against 1.257 / 1.272.

### The acceptance cell: 2022 fails exactly as it did

`cash+30m entry=breakout target=width`, long, offset one tick, one entry per session, 1 minute, 2022 alone:

| `stop_range_fraction` | profit factor |    net / drawdown | `session_close_share` |
| --------------------: | ------------: | ----------------: | --------------------: |
|                  1.00 | 1.144 / 1.178 | **1.243 / 1.505** |                 0.440 |
|                  1.50 | 1.129 / 1.165 |     0.753 / 0.947 |                 0.572 |
|                  2.00 | 1.121 / 1.133 |     0.623 / 0.682 |                 0.652 |
|                  3.00 | 1.148 / 1.159 |     0.611 / 0.658 |                 0.730 |
|                  5.00 | 1.122 / 1.132 |     0.466 / 0.506 |                 0.767 |

**The same P&L for two and a half times the drawdown**, to the dollar on MNQ: 9,576 against 7,706 at 1.0, 11,285 against 18,467 at 3.0 and 9,491 against 20,357 at 5.0. At `target=w0.5` on the 15-minute range the one neighbouring cell still clears: 1.325 / 1.057 at 1.5, with every other fraction under 0.26. In 2026 the wider stops do not restore the year either: their best is 1.024 and 1.023, at a fraction of 5.0, against 1.15 to 1.26 in the years before.

### Gate 3: the excess no longer peaks at one range width

`matched_random_ranges` at `cash-br+15m target=w1.0`, 1 minute, 100 draws, the top 20 of the stored and extended arms, the median over the long cells at each fraction, four per root, MNQ / NQ:

| `stop_range_fraction` | observed      | null          |              excess | p             | excess, §M28.11 |
| --------------------: | ------------- | ------------- | ------------------: | ------------- | --------------: |
|                  1.00 | 1.143 / 1.141 | 0.960 / 0.977 |     +0.185 / +0.165 | 0.040 / 0.059 | +0.238 / +0.250 |
|                  1.50 | 1.196 / 1.188 | 0.984 / 0.988 | **+0.212** / +0.199 | 0.020 / 0.020 | +0.218 / +0.228 |
|                  2.00 | 1.206 / 1.210 | 1.009 / 1.002 | +0.200 / **+0.208** | 0.040 / 0.040 | +0.218 / +0.239 |
|                  3.00 | 1.218 / 1.220 | 1.032 / 1.015 |     +0.186 / +0.204 | 0.020 / 0.059 | +0.212 / +0.220 |
|                  5.00 | 1.196 / 1.198 | 1.053 / 1.052 |     +0.143 / +0.146 | 0.149 / 0.109 | +0.172 / +0.178 |

**§M28.11's "the entry's edge over a permuted range is largest at the stop width the truncated axis already contained" does not hold on these rows.** It is largest at 1.5 to 2 range widths, and only 5 widths still falls away. What holds is that the null rises with the stop throughout.

**§M28.10's version moved the same way.** At the long cells at a fraction of 1.0 at `cash-ft+15m`, `scale=off` returns +0.185 / +0.165 and `stop@20` +0.191 / +0.202, where §M28.10 had the excess falling. Its whole shortlist is also stronger: 14 and 13 of 20 below p = 0.05 against the control's 7 and 5, family-wise 0.020 against 0.030.

**The wide end is still a hold-to-close.** The 30-minute `target=w1.0` at a fraction of 5.0 exits at the flatten on 0.80 of legs, and the no-target ladder on 0.995.

## What this settles, and what it does not

**It settles that the 2026 finding survives the fill fixes and another month**, and it is now a small loss rather than flat. The candidate's own case in [`README.md`](README.md) still has to be read as a bet that a regime returns.

**It moves one reading of the stop.** §M28.11 kept "about 1.0 to 1.5" because profit factor, the excess, 2022 and the close share all agreed there. The excess no longer argues against 1.5 to 2. **2022 still does**, costing over a third of net-to-drawdown at 1.5 and half of it at 2. So the kept range stands on the acceptance cell and the close share, and no longer on the excess.

**It settles nothing about NinjaTrader.** OpeningRange is still `TIER1_ONLY` and no leg of it has been diffed against a trade list.

**The tests are not independent.** Forty configurations in a grid share most of their trades, and these lengths and stops were chosen after §M28.8's look at them. The reproduction is the part to read, not any one p-value.

## How it was read

- **Row tables.** `tools/campaign_report.py`'s load, `tools/campaign_holdout.py`'s `pair_windows` and `verdict`, `tools/campaign_paired.py`'s `paired` and `verdict`, and `eta_squared`, from the stored rows, in a one-off script. Bar sizes are as each table says: `orb-geometry` at 1 minute, and the follow-through and bracket arms at 1 minute or pooled over 1 to 15.
- **By year.** One-off re-runs of the stored parameters on the whole series with `tools/campaign_shortlist.py`'s `prepared` and `run_logged`, cut by the entry's year and summarised with `stats.summarise`. Each was first checked against its stored held-out row with `verify`.
- **Gate 3.** `tools/campaign_null.py --strategy OpeningRange --variant <arm> --stratum unfiltered --root MNQ NQ --resolution 1 --window selection --test-window holdout --top 20 --iterations 100 --draw levels`, with the rows narrowed to a fraction arm for §M28.11. None was refused. §M28.8's table does not state the bar size its shortlists were drawn at, so 1 minute is this file's choice.
- **Not repeated:** §M28.10's comparison against a fixed fraction of the same size, and §M28.9's stop and target tables by year.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
