---
id: M19.3
title: "M19.3 — SqueezeBreakout swept: the squeeze's depth is nearly inert, and one short pocket clears the null on 31 trades"
archetypes: [SqueezeBreakout]
issues: [51]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  Pooled, no root x resolution cell is majority-profitable, and unfiltered nothing beats a random entry on either root — the question #51 exists to ask gets no; six strata clear gate 2 on both roots and one, trend=UP, clears the null on both, but it is one short entry measured ten times on about 31 held-out trades, and how deep the squeeze is barely moves a paired profit factor.
---

# M19.3 — SqueezeBreakout swept: the squeeze's depth is nearly inert, and one short pocket clears the null on 31 trades ([#51])

[§M19.2](m19-2-squeeze-breakout-spec.md) specified the archetype and built it. This is its first campaign: **635,904 combinations in 21 minutes**, both roots, through the gates §M35 ran, with the gate-3 family written down before the sweep started. **The question the spec said the null would answer — does compression add anything to a break of the window — is answered no on the unfiltered series**, and what does survive is narrower than the archetype.

Every figure below is re-derivable from `results/campaign/SqueezeBreakout.duckdb`. It is a measurement of one dated run against the archive as it stood on 2026-09-16, not a standing property.

## What was run

|                 |                                                                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Grid**        | 1,728 combinations: `direction` × `squeeze_form` × `squeeze_period` × `squeeze_below` × `min_squeeze_bars` × `entry_offset_ticks`, across four stop × target variants |
| **Squeeze**     | bandwidth and range-to-ATR; windows of 10, 20 and 40 bars; cuts at 0.05, 0.10 and 0.25; held for 1 or 5 bars; baseline 250 bars                                       |
| **Bracket**     | the opposite extreme at 1 or 8 ticks, or 1 or 2 ATRs; the R ladder at 1× or 2×, or one width then a runner                                                            |
| **Strata**      | 23, one context dimension at a time, never crossed                                                                                                                    |
| **Resolutions** | 2, 5, 10 and 15 minutes                                                                                                                                               |
| **Roots**       | MNQ and NQ, spliced continuous, 2021-09-19 to 2026-09-16                                                                                                              |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                          |
| **Windows**     | selection to 2024-10-09 on MNQ and 2024-10-14 on NQ, holdout after — the first 60% of bars and the last 40%                                                           |

**One minute was not run**, for §M35's reason.

## Gate 1 — pooled it fails everywhere; split, the opposite stop and the long side carry it

Share of configurations with a profit factor above 1, at 30 trades or more, in the **unfiltered** stratum, selection window first and holdout second:

| root | resolution | pooled      | opposite stop   | ATR stop    | long            | short       |
| ---- | ---------- | ----------- | --------------- | ----------- | --------------- | ----------- |
| MNQ  | 2m         | 5.0 / 12.0  | 9.6 / 21.4      | 0.3 / 2.7   | 10.0 / 24.1     | 0.0 / 0.0   |
| MNQ  | 5m         | 18.0 / 15.7 | 31.6 / 23.8     | 4.4 / 7.5   | 33.0 / 29.3     | 3.0 / 2.1   |
| MNQ  | 10m        | 30.5 / 37.2 | 47.2 / 53.5     | 13.8 / 20.8 | **55.3** / 51.5 | 5.7 / 22.8  |
| MNQ  | 15m        | 35.2 / 31.1 | **53.6** / 44.0 | 16.8 / 18.3 | **63.9** / 42.1 | 6.5 / 20.1  |
| NQ   | 2m         | 13.8 / 19.9 | 24.4 / 31.0     | 3.2 / 8.8   | 26.6 / 38.2     | 1.0 / 1.6   |
| NQ   | 5m         | 25.5 / 24.6 | 42.6 / 35.2     | 8.3 / 14.0  | 42.5 / 44.3     | 8.4 / 4.9   |
| NQ   | 10m        | 37.6 / 41.4 | **59.1** / 57.8 | 16.0 / 25.0 | **63.0** / 56.8 | 12.2 / 25.9 |
| NQ   | 15m        | 42.0 / 37.6 | **64.2** / 53.5 | 19.7 / 21.8 | **67.9** / 47.1 | 16.0 / 28.1 |

**Pooled, no cell of eight is majority-profitable**, and pooled over every stratum and variant the median profit factor is below 1 at every root × resolution × window. Split, the archetype divides the way §M28.1's OpeningRange did: **the opposite-extreme stop clears gate 1 in three cells and the ATR stop in none**, reaching at best 25% held out. A stop at the window's far side is the stop a break of that window wants, and one or two ATRs from the trigger is not.

**The long side is the other half of the split and it is not evidence of anything yet.** Every long cell at 10 and 15 minutes clears on the selection window and no short cell reaches 30% in either window. NQ roughly doubled across the archive, so a long break is paid by drift before it is paid by the squeeze — which is exactly what the matched null below holds fixed, and where it is answered.

**Neither exit share distorts the read.** Across the unfiltered medians the opposite stop sends 9% to 18% of legs out at the session close and the ATR stop 3% to 7%; `ambiguous_share` stays at or below 1.7% everywhere, confirming §M19.2's measurement on the whole grid.

**The selection window's ordering mostly holds.** Paired over 13,824 unfiltered configurations the rank correlation between the windows' profit factors is **+0.732**, positive in all eight cells and highest at two minutes (MNQ 0.829, NQ 0.772), where §M35 measured −0.160 on EmaPullback's. Averaged over `tools/campaign_holdout.py`'s 44 root × stratum cells it is 0.498, against OpeningRange's 0.69 at §M28.1.

## Gate 2 — six strata survive on both roots, and the unfiltered case survives on one

`tools/campaign_holdout.py`: the best twenty by selection-window profit factor, measured on the holdout, against the holdout median of everything. **18 of 44 root × stratum cells pass.** Every stratum that passes on both roots, and the unfiltered one:

| stratum              | MNQ holdout PF | NQ holdout PF | clears drawdown | median held-out trades, MNQ / NQ |
| -------------------- | -------------- | ------------- | --------------- | -------------------------------- |
| `phase=PRE_OPEN`     | 1.255          | 1.795         | both            | 136 / 62                         |
| `compression=NORMAL` | 1.370          | 1.588         | both            | 37 / 48.5                        |
| `volume=THIN`        | 1.338          | 1.401         | MNQ             | 63.5 / 54                        |
| `trend=UP`           | 1.278          | 1.114         | MNQ             | 31 / 31                          |
| `volume=HEAVY`       | 1.068          | 1.127         | neither         | 42.5 / 43                        |
| `regime=DIRECTIONAL` | 1.017          | 1.251         | neither         | 42 / 33                          |
| `unfiltered`         | 1.138          | 0.932         | neither         | 128.5 / 104                      |

**`compression=NORMAL` is partly empty by construction and should be read as such.** Its filter is the 20-bar bandwidth at 250 bars, which is the squeeze's own series for one sixth of the grid; there a squeeze and a normal state cannot both hold and the cell trades nothing. What the stratum holds is a squeeze on some *other* window or form while the 20-bar band is not narrow, and the median configuration in its MNQ shortlist sends **40% of its legs out at the session close**.

**The shortlists are narrow in two senses.** In five of the six the median shortlisted configuration holds 31 to 64 trades on the holdout, and they disagree about direction: the unfiltered shortlist is long on both roots, `trend=UP`'s is 18 of 20 short on both.

## Gate 3 — nothing unfiltered, and one short entry clears the stated bar

**The family, stated before the sweep:** the unfiltered stratum on both roots whatever gate 2 said, because it is the archetype's own question, plus every stratum clearing gate 2 on both roots. Seven cells × two roots × the best five configurations each = **70 tests**, ranked on the selection window and measured on the holdout against a matched random entry taking the same trades at the same minute of the session, 200 draws each. A cell passes only at p = 0.05 on both roots, §M28.16's bar.

| root | stratum              | held-out trades | beat the null | p ≤ 0.05                      |
| ---- | -------------------- | --------------- | ------------- | ----------------------------- |
| MNQ  | `unfiltered`         | 55 to 56        | 5             | 0                             |
| MNQ  | `compression=NORMAL` | 37              | 5             | 0                             |
| MNQ  | `phase=PRE_OPEN`     | 27 to 138       | 3             | 0                             |
| MNQ  | `trend=UP`           | 31              | 5             | **5**                         |
| MNQ  | `volume=THIN`        | 37 to 64        | 5             | 0                             |
| MNQ  | `volume=HEAVY`       | 16 to 24        | 3             | 0                             |
| MNQ  | `regime=DIRECTIONAL` | 13 to 16        | 1             | 0                             |
| NQ   | `unfiltered`         | 104 to 268      | 2             | 2, both **worse** than random |
| NQ   | `compression=NORMAL` | 18 to 49        | 5             | 0                             |
| NQ   | `phase=PRE_OPEN`     | 62 to 131       | 5             | **2**                         |
| NQ   | `trend=UP`           | 30 to 31        | 5             | **1**                         |
| NQ   | `volume=THIN`        | 41 to 55        | 5             | 0                             |
| NQ   | `volume=HEAVY`       | 14 to 46        | 3             | 0                             |
| NQ   | `regime=DIRECTIONAL` | 10 to 12        | 0             | 0                             |

**The unfiltered question gets no, and the long side's gate 1 is where the drift went.** MNQ's five configurations all beat their null, by +0.28 to +0.50 of profit factor, at p from 0.29 to 0.50 — because **a random long taking the same order at the same minute already makes 1.07 to 1.11**. On NQ two of five beat it and the two that reach p = 0.05 are significantly *worse* than random. A break of a compressed window is not measurably better than a break of the same window on an uncompressed bar.

**`trend=UP` clears the stated bar on both roots, and what it is matters more than that it does.** It is **one entry**, chosen independently on each root's selection window: short, range-to-ATR over 40 bars, cut at 0.10 and held five bars, at ten minutes, stopped at the window's far side. The ten tests differ only in the entry offset, the stop offset and the target, so they are one measurement taken ten times. MNQ reaches p = 0.01 to 0.03 at a held-out profit factor of 1.45 to 1.51 against a null of about 0.92; NQ reaches p = 0.03 on one configuration of five, at 1.28 against 0.91. **Both roots rest on 30 or 31 held-out trades**, and MNQ and NQ are the same underlying, so the second root is less independent than §M28.16's bar treats it as being.

**The family's count is not far above chance once that is accounted for.** Seventy tests at the 5% level produce 3.5 false positives in expectation. Ten reached it; two were in the wrong direction, five were one entry on one root, and the remaining three are that same entry on NQ and NQ's `phase=PRE_OPEN`, which is a short out of a 40-bar bandwidth squeeze at 0.10 held five bars — the same shape as `trend=UP`'s on the other form, and one root only.

## The axes

Read on a **balanced panel**: a level counts only where every level of that axis cleared 30 trades with every other parameter, the root, the resolution, the stratum and the window held identical. Share of configurations profitable, and the ordering's Spearman ρ across the windows:

| axis                 | selection                             | holdout                               | ρ      |
| -------------------- | ------------------------------------- | ------------------------------------- | ------ |
| `direction`          | long 41.6, short 15.5                 | long 40.8, short 19.0                 | +1.000 |
| `atr_stop_multiple`  | 2.0 → 26.0, 1.0 → 4.8                 | 2.0 → 34.1, 1.0 → 6.4                 | +1.000 |
| `squeeze_below`      | 0.05 → 30.0, 0.10 → 27.6, 0.25 → 26.6 | 0.05 → 32.4, 0.10 → 29.1, 0.25 → 26.7 | +1.000 |
| `min_squeeze_bars`   | 5 → 29.8, 1 → 26.8                    | 5 → 32.1, 1 → 27.5                    | +1.000 |
| `target_mode`        | width 31.5, R 26.4                    | width 31.6, R 28.3                    | +1.000 |
| `tp_multiplier`      | 2.0 → 28.7, 1.0 → 26.4                | 2.0 → 31.1, 1.0 → 28.3                | +1.000 |
| `stop_offset_ticks`  | 1 → 43.7, 8 → 41.0                    | 1 → 41.4, 8 → 39.7                    | +1.000 |
| `entry_offset_ticks` | 1 → 29.9, 4 → 27.7                    | 1 → 31.0, 4 → 29.6                    | +1.000 |
| `squeeze_period`     | 10 → 28.9, 20 → 27.9, 40 → 27.8       | 20 → 32.2, 40 → 31.1, 10 → 23.9       | −0.500 |
| `squeeze_form`       | bandwidth 29.1, range-to-ATR 27.8     | range-to-ATR 31.3, bandwidth 29.0     | −1.000 |

**Almost every ordering holds, which is this campaign's one clean result**, and it matches the positive rank correlation above. The two that do not are both squeeze axes: the window length and the form, whose spread held out is 8.3 and 2.3 points.

**The squeeze's depth orders monotonically and is nearly worthless, and the table alone would say otherwise.** A tighter cut is profitable more often, but it also trades about a third as often, and a thinner sample spreads further either side of 1. **Paired exactly** — every other parameter identical — a squeeze at 0.05 against one at 0.25 wins **52.7%** of 4,608 held-out pairs at a median profit-factor difference of **+0.009**, and 50.7% on the selection window. Requiring the squeeze to have held five bars is the one squeeze axis with a paired effect: it wins 61.2% of 6,912 held-out pairs at +0.020. **What moves this archetype is its direction and its stop, not how compressed the window was** — the archetype-sized version of §M19.1's finding that compression ranks mid-pack as a filter.

## What this does not settle

- **Gate 4 was not run on `trend=UP`.** Thirty-one held-out trades is §M28.1's sample-size verdict before a walk-forward is asked anything, and the cell was one entry chosen on each root's own selection window.
- **The volume and regime strata used the raw threshold pairs.** §M30 is why a raw-cut gate result does not transfer to the label; `volume=THIN` and `regime=DIRECTIONAL` are raw-cut cells.
- **The two-sided entry was not measured, and on the managed approach it cannot be built**: NinjaTrader ignores whichever opposite entry is submitted second — [`nt8-fidelity.md`](../nt8-fidelity.md) § "The managed approach refuses the opposite-direction submission outright". The long/short split above says what it would have measured unmanaged: a squeeze taken on whichever side breaks first pools a side that pays with a side that does not.
- **Per-year and per-contract dispersion were not read.** §M19.2 asked for them before a pooled figure is believed; nothing here reached the gate that reads them.
- **One minute was not swept**, and the latched squeeze §M19.2 deferred is still deferred.
- **Nothing here is a Tier-2 measurement.** `Tier2Status` is `TIER1_ONLY` and no NinjaScript exists.

[#51]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/51
