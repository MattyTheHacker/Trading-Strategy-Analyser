---
id: M28.10
title: "M28.10 — the geometry denominated in trailing follow-through: no, and the reason is arithmetic"
archetypes: [OpeningRange]
issues: [261]
gates: [3, 4]
outcome: negative
verdict: >-
  Normalising the geometry against trailing follow-through does not restore 2026 on either root; follow-through fell 18% while the median range rose 136%, so the width is what is worth normalising against.
---

# M28.10 — the geometry denominated in trailing follow-through: no, and the reason is arithmetic ([#261])

[#261] asked one question and asked for the answer either way: **does a bracket normalised against trailing follow-through, rather than against the current session's range, restore 2026?** It does not, on either root, at either range that carries an excess, under any of the nine ways the scale can be applied. The mechanism was built, it works, and it is measurably the wrong size to fix what broke.

**What has changed since §M28.8, stated first**, because § "Parked is not abandoned" requires it before a parked configuration space is re-run: **a quantity the archetype could not previously express** — `sessionrange.follow_through_grid`, one completed-session statistic and its trailing median, with `ORB_SCALE_TARGET` and `ORB_SCALE_STOP` reading it. Not a new range, not new data, not a re-seeded sweep. The rules it adds and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) §M28.10.

## The control reproduces [#261]'s table, which is what makes the rest of it comparable

`cash+30m entry=breakout target=width`, `direction=1`, `stop_range_fraction=1.0`, `max_entries_per_session=1`, `entry_offset_ticks=1`, 1-minute bars, MNQ, 4 contracts, at the root's real commission and one tick of slippage — the confined geometry, unscaled:

| year     | trades | profit factor | net P&L | max drawdown |
| -------- | ------ | ------------- | ------- | ------------ |
| 2022     | 174    | 1.144         | 9,576   | -7,706       |
| 2023     | 178    | 1.214         | 9,406   | -5,544       |
| 2024     | 183    | 1.252         | 12,040  | -7,669       |
| 2025     | 179    | 1.262         | 17,197  | -6,694       |
| **2026** | 110    | **1.008**     | **441** | **-22,625**  |

**Net P&L and profit factor are identical to §M28.9's table above in all five years**, both aggregated per trade as `stats.summarise` does rather than per leg, so the two sections are reading the same trades the same way. The drawdown differs in 2022 alone and the convention is the reason: §M28.9 runs one continuous equity curve across the archive and slices it to the year, where this restarts the curve each year — -8,001 the first way against -7,706 the second, agreeing exactly from 2023 on. Neither section's conclusions turn on it.

## The scale tracks the regime, so a negative result is about the idea rather than the estimate

Per session, median over each year, MNQ. The trailing columns are the median over the previous *n* sessions with a value, taken strictly before the session that reads it:

| year | sessions | median 30m range | median follow-through | trailing@20 | trailing@60 | trailing@250 |
| ---- | -------- | ---------------- | --------------------- | ----------- | ----------- | ------------ |
| 2022 | 253      | 123.5            | 1.183                 | 1.174       | 1.176       | 1.196        |
| 2023 | 253      | 78.8             | 1.171                 | 1.139       | 1.153       | 1.113        |
| 2024 | 254      | 91.4             | 1.239                 | 1.249       | 1.242       | 1.209        |
| 2025 | 254      | 124.1            | 1.043                 | 1.086       | 1.039       | 1.168        |
| 2026 | 156      | 186.0            | 0.960                 | 0.936       | 0.936       | 0.985        |

**The estimate is within 0.03 of the quantity it estimates in every year at the two shorter lookbacks**, and it is lookahead-free by construction. The range and the direction of the follow-through move are [#261]'s, reproduced: the range more than doubles and price travels less than one width past it by 2026.

**The level differs and the reason is stated rather than reconciled.** [#261] reports 1.105 in 2023 falling to 0.921 in 2026 where this reports 1.171 to 0.960, because follow-through here is measured over the whole armed span — to the session's last bar, which is where the flatten is and therefore how far a trade could have reached. The trend, the size of the fall and the crossing below 1.0 are the same.

## Nothing restores 2026

Profit factor by year, MNQ `cash+30m`, the control against all nine arms. The `@250` arm needs a year of history before it arms, which is why its 2022 column rests on 16 trades against the others' 174; 2023 onward every arm trades the same sessions.

| year     | off       | target@20 | target@60 | target@250 | stop@20 | stop@60 | stop@250  | both@20 | both@60 | both@250 |
| -------- | --------- | --------- | --------- | ---------- | ------- | ------- | --------- | ------- | ------- | -------- |
| 2023     | 1.214     | 1.205     | 1.225     | 1.227      | 1.166   | 1.167   | 1.135     | 1.150   | 1.167   | 1.147    |
| 2024     | 1.252     | 1.217     | 1.246     | 1.245      | 1.353   | 1.339   | 1.301     | 1.312   | 1.316   | 1.292    |
| 2025     | 1.262     | 1.309     | 1.267     | 1.305      | 1.189   | 1.212   | 1.265     | 1.239   | 1.218   | 1.307    |
| **2026** | **1.008** | 0.961     | 0.971     | 1.001      | 0.987   | 1.022   | **1.031** | 0.943   | 0.987   | 1.024    |

**The best of the nine moves 2026 from 1.008 to 1.031 and its drawdown from 22,625 to 21,361** — about a tenth of the way back to the 1.15-1.26 of the four years before it, on 110 trades. On NQ the control returns 1.002 in 2026 and only two of the nine beat it, both by under 0.006, while seven are worse and the worst returns 0.927 on -43,138.

## The one place it looks like a gain is the stop's *level*, and that belongs to [#262]

`tools/campaign_paired.py`, held-out window, each treatment against the control cell by cell over the 32 combinations they share. At `cash+30m` every median difference sits inside ±0.02 with no consistent sign. At `cash+15m` the stop-scaled arms are large and consistent — `stop@20` returns +0.09 to +0.21 in 6 of 6 root × resolution cells, all six at p < 0.05.

**That is the scale's size rather than its tracking, and the two separate cleanly.** The median trailing follow-through at 15 minutes is **1.709**, so `stop@20` at a fraction of *f* places the stop *f* × 1.709 range widths back — and `stop_range_fraction` has never been swept past 1.0. Against an unscaled arm whose fraction is multiplied by that same constant, over the eight (side × fraction) configurations on the held-out window:

| cell               | tracked − constant | tracked − plain | cells tracking wins |
| ------------------ | ------------------ | --------------- | ------------------- |
| MNQ `cash+15m` @20 | **-0.004**         | +0.092          | 3 of 8              |
| NQ `cash+15m` @20  | **-0.001**         | +0.087          | 4 of 8              |
| MNQ `cash+15m` @60 | **-0.010**         | +0.062          | 3 of 8              |
| MNQ `cash+30m` @60 | **-0.030**         | -0.005          | 2 of 8              |
| NQ `cash+30m` @60  | **-0.013**         | +0.008          | 2 of 8              |

**Tracking never beats a constant of the same size**, on either root, at either range, at either lookback — and the constant is fitted with hindsight on the whole sample, which is the conservative side. The whole of the +0.09 is the level. [#262] is where a stop ladder past 1.0 belongs, and this is independent evidence for its premise.

## The matched null rises with the stop, which is the same finding from the other side

`matched_random_ranges` over the top twenty of each arm, ranked on the selection window and tested on the held-out one, 100 draws, 1-minute bars, `cash+15m`. The long cells at a fraction of 1.0, which both shortlists contain:

| arm             | root | observed      | null          | excess              |
| --------------- | ---- | ------------- | ------------- | ------------------- |
| `scale=off`     | MNQ  | 1.199 / 1.179 | 0.950 / 0.952 | **+0.249 / +0.227** |
| `scale=stop@20` | MNQ  | 1.238 / 1.220 | 1.017 / 1.013 | **+0.221 / +0.206** |
| `scale=off`     | NQ   | 1.213 / 1.188 | 0.946 / 0.954 | **+0.267 / +0.233** |
| `scale=stop@20` | NQ   | 1.236 / 1.218 | 1.014 / 1.010 | **+0.222 / +0.207** |

**The wider stop lifts the permuted-range arm by more than it lifts the observed one, so the excess falls.** A change that improves a random range as much as the real one is a property of the bracket and not of the entry, and this is what that looks like measured rather than argued. The entry's edge over a permuted range is §M28.8's, unchanged by anything here.

## The drawdown check, cleared for the first time, and why it is not this axis's

Held-out top-20 net-to-drawdown at `cash+15m`, `tools/campaign_holdout.py`, MNQ / NQ. **Four of the nine arms clear the drawdown check on both roots and every one of them has the stop half switched on:**

| arm          | MNQ       | NQ        | clears |
| ------------ | --------- | --------- | ------ |
| `both@20`    | **2.026** | **1.710** | yes    |
| `stop@20`    | 1.720     | 1.651     | yes    |
| `stop@60`    | 1.615     | 1.614     | yes    |
| `both@60`    | 1.600     | 1.634     | yes    |
| `target@20`  | 0.982     | 0.914     | no     |
| `off`        | 0.763     | 0.897     | no     |
| `target@60`  | 0.707     | 0.590     | no     |
| `stop@250`   | 0.460     | 0.136     | no     |
| `both@250`   | 0.459     | 0.136     | no     |
| `target@250` | 0.195     | -0.041    | no     |

`both@20` also carries the best held-out profit factor of the ten, 1.248 / 1.225 against the control's 1.078 / 1.098, with 20 of 20 shortlisted configurations profitable on both roots. **No cash-anchored §M28.8 variant reaches any of the four**: the breakout and retest cells at both lengths and both target schemes run 0.446 to 0.982, and the one figure above 1.0 anywhere near them — the 15-minute retest at 3.011 on NQ — fails gate 2 and returns -0.674 on MNQ.

**Both shares read before any of that is believed**, which the standing rule asks for once and an OpeningRange number asks for twice. Across all 3,840 stored `cash+15m` rows the ambiguity is negligible — a median `ambiguous_share` of 0.0000 to 0.0054 per arm, and 10 rows in 3,840 reaching `disambiguate.MIN_AMBIGUOUS_SHARE` at all — and **no shortlisted row on either root exceeds 0.0058**, so §M28.7's corner does not reach a breakout-only variant set the way it reaches the retest and the rejection.

`session_close_share` does move, and it is the caveat this result travels with: the four clearing arms exit at the forced flat on **0.476 to 0.586** of their shortlisted legs against the control's 0.299. That is what a wider stop does — fewer legs stopped out, more surviving to the clock — and it means the drawdown these arms return is bought with roughly twice the reliance on the flatten. **It does not order them**, which is worth saying because it would be the easy explanation: `both@250` carries the highest close share of the ten at 0.618 and a net-to-drawdown of 0.459.

**This geometry is selectable, and that is the part §M27.3 warns it might not be.** The four clearing arms return a shortlist rank correlation between the two windows of **0.817 to 0.899** on both roots, and their held-out profit factor is *above* their selection profit factor in seven of the eight cells and level in the eighth — the selection window ranks the geometry the way the holdout does, and picking on it does not decay. §M27.3's drawdown ridge is the opposite shape: a rank correlation of **−0.161**, "the only negative figure of its kind in the project", with a selection window whose own optimum is the campaign's bracket rather than the one that clears. **So the geometry that clears Gate 4 exists inside the grid and the selection window will not hand it to you** is a finding about that axis rather than about brackets in general, and this is the first counter-example to it. Which of the two shapes [#262]'s truncated `stop_range_fraction` turns out to have is the question this hands it.

**No target-only arm clears it and every clearing arm is stop-side, which is the level reading from the variant side.** Read it against the two subsections above before it is believed: over the matched geometry the tracked arm's median held-out net-to-drawdown is *below* the plain arm's — 0.226 against 0.376 on MNQ and 0.506 against 0.672 on NQ — so what a shortlist reports is which cells it picked rather than a property of the arm. The constant-fraction control has **not** been through the same shortlist, because the swept fraction axis does not reach the treatment's geometry; that is precisely [#262]'s gap, and settling it needs [#262]'s ladder rather than this axis.

## The verdict, and what [#261] asked

- **No. A geometry normalised against trailing follow-through does not restore 2026**, and the answer is the same on both roots, at both ranges, at all three lookbacks and under all three ways of applying the scale.
- **The estimate is not what failed.** The trailing median tracks the observed follow-through to within 0.03 and reads no bar it could not have seen. The idea was measured, not approximated.
- **The arithmetic says why, and it is the more useful half of the answer.** Follow-through fell by 18% between 2023 and 2026 while the median range **rose by 136%**. A bracket denominated in range widths therefore carries 2.4× the dollar risk per trade in 2026 that it did in 2023, and 2026's drawdown is 4.1× 2023's on a nearly unchanged trade count. **A 0.82× correction cannot offset a 2.4× move**, and no lookback of this quantity could have.
- **So the quantity worth normalising against is the width itself, not the reach past it** — which is a position-sizing question rather than a geometry one, and it is the first OpeningRange finding that points outside the bracket entirely.
- **Parked, with a reason** — § "Parked is not abandoned". `ORB_SCALE_*` stays registered, swept and reconciled. What would justify a re-run is not another lookback, another range or another stratum: the axis is measured across all three and is a wash against a constant everywhere. What is untested is a bracket sized in **dollars or in a trailing width**, which is a different primitive rather than a different parameterisation of this one.
- **The archetype's edge is still absent from the most recent year of data, and that is not a units problem.** Trading it live remains a bet on the regime returning, which is what [#261] asked to have stated either way.

Every figure above is a measurement of one dated run over the archive as it stands, re-derivable from `results/campaign/OpeningRange.duckdb` under the variant names `cash-ft+<length>m scale=<mode>@<sessions>` and a single-configuration re-run — not a standing property.

[#261]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/261
[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
