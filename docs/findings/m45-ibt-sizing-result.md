---
id: M45
title: "M45 — InsideBarTrailing sized per signal: tiering fails, a confluence size clears its null, and position size read through the account"
archetypes: [InsideBarTrailing]
issues: [295, 353]
gates: [2, 3]
outcome: mixed
verdict: >-
  Pre-registered and run: no earliness tier beats the fixed half split held out — first-breakout is inert at 94% of traded entries early, and the other two improve at most 6% of MNQ pairs and 21% of NQ pairs — while one contract more per favourable label beats its own sizes shuffled across its signals at p ≤ 0.05 on 20 of 20 MNQ and 17 of 20 NQ configurations against the 4 required; through the account, MNQ's 50K presets do best at the stored six contracts, and NQ funds only on a 150K account at two to four.
---

# M45 — InsideBarTrailing sized per signal: tiering fails, a confluence size clears its null, and position size read through the account ([#295], [#353])

**Every bar below was fixed before the run**, in `docs/findings/m45-ibt-sizing-preregistration.md`; this file is what the run returned. One pass: MNQ and NQ, 5-minute bars, the 60/40 selection and held-out windows, the unfiltered stratum and `phase=MIDDAY`, nine sizing arms over InsideBarTrailing's stored grid with the split held — 31,104 combinations in 2.9 minutes. **The midday cell at five minutes is the one every verdict rests on**; the unfiltered stratum and the selection window are hypothesis-generating only.

## The change moved nothing it was not meant to

With both rules off the loop is the one the NinjaScript runs, and that was checked on real data before anything was read. The trade-log gate is byte-for-byte identical, but its fourteen files are DeadCatBounce's and cannot see this loop, so the check that can is the reconciliations, run on the base commit and on the change:

| reconciliation                           | before and after         |
| ---------------------------------------- | ------------------------ |
| InsideBar, MNQ 03-24                     | identical — 969 of 969   |
| InsideBarTrailing, MNQ 03-24             | identical — 1,522 joined |
| InsideBarTrailing, midday, combo 2035    | identical — 68 of 68     |
| InsideBarTrailing, the regression export | identical — 1,522 joined |

The gated-midday export was not re-read — the run did not recognise its file name — and the ported midday export exercises the same filter. The suite passed on the machine that ran it.

## The fit

Fitted on the selection window alone, at the stored campaign's base configuration over its unfiltered signal, and hashed before the sweep started:

| root | trend bars | extension (ATR) | labels counted                          | traded early: first-breakout / sma-extension / trend-age |
| ---- | ---------: | --------------: | --------------------------------------- | -------------------------------------------------------- |
| MNQ  |          5 |           3.459 | trend, higher timeframe, regime, volume | 94.1% / 53.5% / 54.2%                                    |
| NQ   |          5 |           3.448 | trend, higher timeframe, regime, volume | 94.5% / 54.0% / 55.7%                                    |

**VWAP was dropped on both roots**: it favours 97% of the fitted signals, because a break above an inside bar in a three-average uptrend is nearly always above the session VWAP too. The trend label, at 86%, sits just inside the band and was kept.

**First-breakout is inert on both roots, and is reported rather than tested.** 94% of the entries it trades are first breakouts — re-entering a trend run needs the previous trade to end while the run survives, and on this archetype it rarely does — so it runs as the quarter split almost everywhere. Paired against `split=0.25` held out it improves 219 and 227 pairs of 432, at p = 0.81 and 0.31: indistinguishable from it.

## Tiering: no rule clears

Held out, `phase=MIDDAY`, five minutes, profit factor — the median paired difference and the pairs of 432 the tier improved:

| tier                     | vs `split=0.5`, MNQ | vs `split=0.5`, NQ |  vs its inverse, MNQ |  vs its inverse, NQ |
| ------------------------ | ------------------: | -----------------: | -------------------: | ------------------: |
| `first-breakout` (inert) |           −0.083, 0 |          −0.052, 0 |            −0.087, 0 |           −0.058, 5 |
| `sma-extension`          |          −0.035, 26 |         −0.022, 90 | −0.002, 205 (p 0.31) | 0.000, 218 (p 0.89) |
| `trend-age`              |           −0.065, 0 |         −0.045, 29 |          −0.020, 107 |         −0.016, 144 |

Every other cell is p < 0.001, and in the wrong direction. The bar needed more than half the pairs improved at p < 0.05 against both comparisons on both roots; **no tier reaches it against either**.

**Held out, the half split beats the quarter almost everywhere**: `split=0.25` against `split=0.5` improves 0 of 432 pairs on MNQ and 7 of 432 on NQ. A tier gives some entries the quarter, so it starts behind; which entries it gives them to then decides only how far. Against its own inverse, `sma-extension` makes no difference at all and `trend-age` is worse — the young-trend entries are the ones that most wanted the half.

**And the window decides the sign.** On the selection window every tier beat `split=0.5` — in 60% and 67% of pairs for first-breakout, 55% and 75% for sma-extension, 62% and 68% for trend-age, MNQ and NQ — and every one lost held out. `trend-age` against its inverse flips the same way, from 62% and 68% improved to 25% and 33%. That is §M37's shape, an effect taking the window's sign, and a selection window would have picked the tier that the holdout then punished.

Neither the trade count nor the forced flat explains it: the median paired trade count is unchanged in every comparison, `session_close_share` moves by at most 0.004, and `ambiguous_share` is 0.000 in every tier and in the control.

## The confluence size clears its null

Held out, the twenty configurations the selection window ranked highest, each against its own sizes shuffled across its own signals 200 times:

| root | at p ≤ 0.05 | required | excess over the shuffled median |
| ---- | ----------: | -------: | ------------------------------- |
| MNQ  |    20 of 20 |        4 | +0.066 to +0.136                |
| NQ   |    17 of 20 |        4 | +0.036 to +0.113                |

Eleven of the MNQ twenty sit at p = 0.005, the floor 200 shuffles can reach. The three NQ misses are at p = 0.065 to 0.080. **What that measures is allocation, not entry**: the trades are the control's, and the count put its extra contracts on the ones that paid, beyond what the same sizes put on the same signals at random.

The two reads beside it agree. Paired against `split=0.5` over all 432 cells it raises held-out profit factor by a median 0.071 on MNQ and 0.058 on NQ, improving 398 and 395 pairs. Its held-out top twenty has the best profit factor and net-to-drawdown of any arm — 1.475 and 3.854 on MNQ, 1.502 and 4.092 on NQ, against the half split's 1.362 and 2.878, 1.423 and 3.280 — and on NQ it is the only arm that also passes the unfiltered stratum. Its median net roughly doubles, but that is mostly the larger average position and is not the reading.

What travels with it:

- **Which label carries it is not measured.** The four were counted together; the trend label adds a contract to 86% of signals, and nothing here separates its share from the other three's.
- **Its account behaviour is not measured.** The prop rungs below ran on the stored fixed-size grid. A confluence size puts on up to four more contracts at the entries it rates highest, which is exactly where an account's floor is most exposed.
- **Its own `session_close_share` was not read** in this run; its control's is 0.251 on MNQ and 0.248 on NQ.
- **It is `TIER1_ONLY`, and none of its four labels exists in NT8.** Porting the rule means porting the trend, higher-timeframe, regime and volume labels, each with its own pin — `docs/nt8-fidelity.md` §M45.

## Position size through the account

The stored campaign's midday shortlist — `--variant trailing`, the twenty the selection window ranked highest — re-run at each contract count and replayed, attempts uncapped. Median net per preset:

| MNQ          |      2 |       3 |       4 |           6 |           8 |
| ------------ | -----: | ------: | ------: | ----------: | ----------: |
| Apex 50K     | +6,443 | +10,880 | +21,372 | **+31,933** |     +11,707 |
| Apex 150K    |    −59 |  +4,805 | +11,993 |     +18,165 | **+39,682** |
| TopStep 50K  | +4,407 | +12,591 | +16,013 | **+19,155** |     +14,257 |
| TopStep 150K | +5,173 | +10,323 | +16,617 |     +17,632 | **+39,895** |

| NQ           |           2 |       3 |       4 |       6 |       8 |
| ------------ | ----------: | ------: | ------: | ------: | ------: |
| Apex 50K     |     −49,265 | −53,774 | −53,941 | −54,776 | −54,943 |
| Apex 150K    | **+60,146** | −57,991 | −87,615 | −94,446 | −96,525 |
| TopStep 50K  |      −9,957 | −13,524 | −14,480 | −15,190 | −15,680 |
| TopStep 150K | **+88,099** | +84,044 | +70,456 | −26,325 | −39,113 |

**On MNQ both 50K presets do best at the stored six contracts and fall away at eight**, where the median attempts an Apex 50K sequence takes rise from 29 to 94.5. **Both 150K presets are still rising at eight**, which is the top of the ladder — an axis whose best value is its last has been truncated, not swept, and the next read needs 10, 12 and 16.

**On NQ no position this archetype can take makes a 50K account pay**: the median sequence loses money at every rung on both firms, and at the two-contract floor Apex 50K ever passes on 11% of configurations and TopStep 50K is profitable on none. A 150K account funds at two contracts on both firms, every configuration profitable, and at TopStep up to four. §M28.13's "NQ needs a smaller position or a 150K account" turns out to be both at once.

**Size moves this archetype's trades, as predicted.** At six contracts every re-run reproduced its stored trade count, 20 of 20 on both roots; at every other size some did not, and below six most did not, because the `-200` gate reads the open position in dollars. The two-contract rung holds 16 of the 20 on MNQ and 19 on NQ: the rest carry the stored 0.6 split, which has no runner at two. Net is payout minus fees and is not a ranking — read it beside the pass rate, as §M28.13 says.

## What this settles, and what it does not

- **Tiering the first partial by earliness fails on this archetype**, at the quarter and the half, in the cell being ported, under all three rules. It is parked, not abandoned: what the holdout favoured was banking more, so a tier pair above the half — the stored grid's 0.6 and 0.8 — is a different configuration space, and it has not been run.
- **The confluence size is the first sizing rule in the registry to clear a pre-registered null.** It is one cell, one resolution and two roots of one index; its account behaviour and its labels' separate shares are the next reads, and a port needs four labels pinned against NT8 first. [#295]'s registry-wide confluence size would follow it, not precede it.
- **For an MNQ 50K account, the stored six contracts is the best size tested; for NQ, only a 150K account works, at two to four.**

[#295]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/295
[#353]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/353
