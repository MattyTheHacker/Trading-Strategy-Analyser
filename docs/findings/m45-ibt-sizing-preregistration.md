---
id: M45
title: "M45 — pre-registration: InsideBarTrailing's position size, tiered scale-out and confluence size"
archetypes: [InsideBarTrailing]
issues: [295, 353]
gates: [2, 3]
outcome: spec
verdict: >-
  Written before any sizing arm runs: an earliness tier clears only if, held out in the midday cell at five minutes, it beats both the fixed half split and its own inverse on a paired sign test at p < 0.05 on both roots; the confluence size clears only if at least 4 of 20 held-out configurations beat their own sizes shuffled at p ≤ 0.05 on both roots; and position size is read through the account replay rather than tested.
---

# M45 — pre-registration: InsideBarTrailing's position size, tiered scale-out and confluence size ([#295], [#353])

**This file is written before the campaign it describes runs.** No sizing arm is stored anywhere at the time of writing, and the cuts every arm reads are fitted on the selection window alone and recorded below before the sweep starts. The point is the one `docs/findings/gold-strata-preregistration.md` makes: commit to the bar before looking.

## What is already known, and so cannot be predicted

| established before this run                                                                       | how                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| On every archetype but InsideBarTrailing, quantity rescales every dollar figure and nothing else  | commission and slippage are both per contract, so a leg's net is its quantity times its per-contract net; on synthetic bars DeadCatBounce and InsideBar at 4 and 8 contracts take identical trades at a net ratio of exactly 2.0000 and an unchanged profit factor |
| On InsideBarTrailing, quantity moves the trades themselves                                        | the `-200` gate is currency on the open position and the split rounds up; the same bars at 6 and 12 contracts take 474 and 486 legs                                                                                                                                |
| The stored `0.6` split cannot run below three contracts, and a quarter and a half coincide at two | `(int) Math.Ceiling(quantity * share)` — `docs/nt8-fidelity.md` §M45                                                                                                                                                                                               |
| The first-breakout tier can be close to inert on the trades actually taken                        | on synthetic bars at short periods, every traded signal was a first breakout although later setups in a run existed: re-entering a run needs the previous trade to end while the run survives                                                                      |

So **the plain quantity axis [#295] asks for is only a question on this archetype and in the account replay**, and [#353]'s caveat that commission makes quantity a non-pure scaling of P&L does not hold: commission is per contract and scales with it. What does not scale is every fixed-dollar rule — the account's thresholds, and this archetype's `-200` gate.

## The arms

InsideBarTrailing's stored grid — `ema_period` 11/22/44, `fast_sma_period` 20/35/50, `error_margin` 0.05/0.1, `atr_length` 3/14, `trailing_stop_multiplier` 2/5/10 — with `partial_take_profit_percentage` held rather than swept and `order_quantity` 3/4/6/8 crossed in. 432 combinations per arm and the same 432 in every arm, so each is read against its control cell by cell with `tools/campaign_paired.py` rather than as two shortlists of different sizes. Nine arms, one pass, every stored name prefixed `trailing`:

| arm                            | early share | established share | what it is                                     |
| ------------------------------ | ----------: | ----------------: | ---------------------------------------------- |
| `split=0.5`                    |           — |               0.5 | control                                        |
| `split=0.25`                   |           — |              0.25 | control                                        |
| `tier=first-breakout`          |        0.25 |               0.5 | `Trading-Docs` §11 as written                  |
| `tier=first-breakout inverted` |         0.5 |              0.25 | its placebo                                    |
| `tier=sma-extension`           |        0.25 |               0.5 | as written                                     |
| `tier=sma-extension inverted`  |         0.5 |              0.25 | placebo                                        |
| `tier=trend-age`               |        0.25 |               0.5 | as written                                     |
| `tier=trend-age inverted`      |         0.5 |              0.25 | placebo                                        |
| `size=confluence`              |           — |               0.5 | one contract more per favourable label counted |

**The quarter and the half are `Trading-Docs` §11's**, held rather than swept. **The inverse is the placebo**: a tier that helps only because mixing two sizes helps will help inverted as well. Three contracts is the floor because two splits a quarter and a half identically, and the parameter class refuses a tier pair that never splits differently.

## The cuts, fitted before the run

`tools/campaign_sizing.py fit` fits each root and resolution on the **selection window alone**, at the stored campaign's base configuration over its unfiltered signal:

- `early_max_trend_bars` and `early_max_extension_atr` at the **median** over the signals, so half the signals are early under each;
- the regime and volume labels' thresholds at the **top fifth** of their own series — the campaign's regime pair and one of its volume tails, so a sizing label and a stratum mean the same thing;
- the labels the confluence arm counts: those favouring **between 10% and 90%** of the signals. A label outside that band is near-constant at the signal, adds the same contract to almost every trade and sorts nothing — `annotate.confluence`'s own `above_ema_21` caveat, `docs/findings/confluence-count-per-trade.md`;
- per earliness rule, the share of the base configuration's **traded** entries that come out early.

**Record the fitted file here before the sweep runs.** A rule whose traded early share is below 10% or above 90% on a root is reported as inert on that root and not tested there, which removes it from the count below rather than letting it fail.

| root | minutes | trend bars | extension (ATR) | labels counted | traded early: first-breakout / sma-extension / trend-age |
| ---- | ------: | ---------: | --------------: | -------------- | -------------------------------------------------------- |
| MNQ  |       5 |            |                 |                |                                                          |
| NQ   |       5 |            |                 |                |                                                          |

## The cells

Both roots, both windows, the unfiltered stratum and **`phase=MIDDAY`**. **The midday cell at five minutes is the one every verdict below rests on**, because that is the cell being ported — `docs/findings/m43-midday-candidates-ranked.md`. The unfiltered stratum and any other resolution run in the same pass and are hypothesis-generating only.

## What counts as a pass

Every comparison is on the holdout, over configurations whose arms were fixed before it ran.

1. **An earliness tier clears** if, in the midday cell at five minutes, it beats `split=0.5` **and** its own inverse on held-out profit factor — each on `campaign_paired`'s sign test at p < 0.05 with more than half the pairs improved — on **both** roots. Three tiers, two comparisons each, two roots: twelve tests, and a tier needs all four of its own.
2. **The confluence size clears** if at least **4 of the 20** held-out configurations the selection window ranks highest beat their own sizes shuffled across their signals at p ≤ 0.05 — `tools/campaign_sizing.py null` — on **both** roots. One in twenty is the chance rate; four or more happens about 1.6% of the time by chance.
3. **Position size is read, not tested.** `tools/campaign_propaccount.py --quantities 2 3 4 6 8` over the midday shortlist on each root reports pass rate, fees and net per rung and preset; a stored row whose split cannot take a rung is named and skipped. On NQ the question it answers is narrow: the smallest position this archetype can take there is two contracts, which leaves 62 points under Apex 50K's $2,500 against the 31 at four that §M28.13 found fatal.

**Before believing any pass**, read `ambiguous_share` and `session_close_share` for the treatment and its control, and the trade count per pair: a tier or a size that thins the sample loses pairs rather than scoring badly in them.

## What this run is not

- **Not gate 3 for the entry.** Every arm takes the same entries; sizing can only change which later entries are reached, through the `-200` gate and the exits it moves. InsideBarTrailing's gate 3 stands where §M44 left it.
- **Not NT8-validated.** Every tier and the confluence size are stored `TIER1_ONLY`, where the two fixed splits keep the archetype's `RECONCILED`, and none of it reaches NT8 until the C# computes the split per signal and a trade list is diffed against it — `docs/nt8-fidelity.md` §M45.
- **Not fixed-risk sizing.** `Trading-Docs` §9's contracts-from-a-risk-budget rule is a different sizing idea and neither issue asks for it.
- **One archetype.** The live candidate first; the confluence size on the rest of the registry would follow a pass here, not precede one.

## How to run it

```bash
./.venv/Scripts/python.exe tools/campaign_sizing.py fit
# record the fitted file in the table above, commit it, then:
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies InsideBarTrailing \
    --variants ibt-sizing --split --strata ibt-sizing --resolutions 5 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_paired.py --strategy InsideBarTrailing --window holdout \
    --stratum phase=MIDDAY --control "trailing split=0.5" --treatment "trailing tier=trend-age"
./.venv/Scripts/python.exe tools/campaign_sizing.py null --root MNQ --resolution 5 --stratum phase=MIDDAY
./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy InsideBarTrailing \
    --stratum phase=MIDDAY --resolution 5 --quantities 2 3 4 6 8
```

The trade-log gate runs before any of it, because the loop changed: with both rules off, every one of the fourteen files has to reproduce.

[#295]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/295
[#353]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/353
