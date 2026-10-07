---
id: M51
title: "M51 — when the money comes back: the recommended cells and every default shortlist through every preset"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [411, 440]
gates: []
outcome: mixed
verdict: >-
  Re-run through each firm's 2026 evaluation linked to its funded account (#440), InsideBarTrailing's midday cell still leads and TopStep 50K is still its account, at a median +$13,378 paid back on every configuration in 36 trading days, against OpeningRange's +$6,806 in 235; LucidFlex 50K comes second for both, Apex pays only on its 50K end-of-day account, and every 150K account is weak. On the presets before #440 the two cells paid back on every Apex and TopStep preset with every configuration, InsideBarTrailing in a median 24 to 57 trading days and OpeningRange in 42 to 230. Through TakeProfitTrader's Test linked to the PRO its pass opens, both cells lose money at every size, so the Test-alone figures quoted before overstate that firm. The registry's default top-20 shortlists mostly never pay back: at most 22% on any one preset, at a median 341 of about 612 trading days, and 22 of the 85 configurations that pay back anywhere lose money held out.
---

# M51 — when the money comes back: the recommended cells and every default shortlist through every preset ([#411])

**What has changed, stated first.** No new sweep, condition or archetype. `tools/campaign_propaccount.py` now dates every fee and payout, chains TakeProfitTrader's Test to the PRO its pass opens, and reports how many trading days pass before payouts exceed fees and how the last whole months went. `tools/README.md` § "campaign_propaccount.py" says what each figure is measured over. This is its first run.

## What was run

Two reads, both with `--preset all`: Apex and TopStep at 50K and 150K, and TakeProfitTrader's three linked pairs. Both re-ran every log on the bars its row was swept on (`--rerun`), since most shortlists have no stored log, and every re-run reproduced its stored trade count and net exactly. The holdout runs 13 May 2024 to 18 September 2026, 613 trading days on MNQ and 611 on NQ, and the monthly figures cover September 2025 to August 2026, the default `--last-months 12`. Costs are the campaign's own, as `docs/findings/README.md` states them.

1. **The two cells `docs/findings/README.md` recommends**, with §M43's filters, on MNQ, top 20 each: InsideBarTrailing `phase=MIDDAY` at 5 minutes under `--variant trailing`, at 6 contracts, and OpeningRange `phase=MIDDAY` at 5 minutes under `--variant "window=30m stop=opposite target=R"`, at 4. This took 5½ minutes, and its output is in `results/prop-replay-recommended/`.
2. **Every registered archetype's default shortlist on both roots**: the top 20 configurations by selection-window profit factor, across every stratum and bar size. That is 360 configurations, with 11 to 20 distinct trade logs per cell. It took 27 minutes, and its output is in `results/prop-replay/`. The README's third cell, InsideBar on MNQ, is read on this shortlist (§M46), so this read covers it.

## The recommended cells pay back on Apex and TopStep

Medians over each cell's 20 configurations. "Pays back" means total payouts exceeded total fees on some day of the holdout.

| preset                         | InsideBarTrailing pays back |  days | net          | OpeningRange pays back |  days | net          |
| ------------------------------ | --------------------------: | ----: | ------------ | ---------------------: | ----: | ------------ |
| Apex 50K                       |                        100% |    24 | **+$31,933** |                   100% |    66 | +$20,342     |
| Apex 150K                      |                        100% |    57 | +$18,165     |                   100% |   230 | **+$19,296** |
| TopStep 50K                    |                        100% |    24 | **+$19,155** |                   100% |    42 | +$13,375     |
| TopStep 150K                   |                        100% |    57 | +$17,632     |                   100% |   230 | **+$25,304** |
| TakeProfitTrader 25K Test+PRO  |                         95% |  26.5 | −$4,772      |                     0% | never | −$8,160      |
| TakeProfitTrader 50K Test+PRO  |                         90% |    37 | −$1,772      |                    50% | never | −$6,387      |
| TakeProfitTrader 150K Test+PRO |                          0% | never | −$6,200      |                     0% | never | −$6,164      |

- **Every configuration of both cells pays back on all four Apex and TopStep presets.** InsideBarTrailing does it sooner on all four, which agrees with §M44's time to the first payout. On net it leads on the two 50K accounts and OpeningRange leads on the two 150K ones.
- **TopStep 50K is the fastest preset for 39 of the 40 configurations.** The other is one InsideBarTrailing configuration, fastest on TakeProfitTrader 25K at 27 days.
- **The months are lumpy.** Of the last twelve, the median configuration had 1 to 4 profitable months on InsideBarTrailing and 3 to 5 on OpeningRange, and the longest run of losing months has a median of 4 to 11 months on InsideBarTrailing and 3 to 6 on OpeningRange, depending on the preset. Yet a fresh account opened in most of those months still ended ahead: 7 to 11.5 of 12 on InsideBarTrailing and 7 to 9 on OpeningRange. Payouts come in lumps, while fees come every month.
- Days to profit is a best case, because every payout is taken in full on the first day it is allowed.

## TakeProfitTrader: the Test alone overstated it

Every TakeProfitTrader figure quoted before this campaign replays the Test preset alone. After its pass that preset keeps trading and withdrawing under evaluation rules, which the firm does not offer (`docs/roadmap.md` § "A firm that changes its rules at the pass ships as two presets"). That is how §M43 had these two cells netting +$17,601 to +$31,564 there. **Linked to the PRO account its pass opens, both cells lose money at every size.**

Both cells pass Tests readily, 12 and 14 per configuration at 25K. The PROs then mostly breach: at 25K, a median of 54 of InsideBarTrailing's 55 attempts end in one. So the fees, a median $6,900 to $8,500 per configuration, outrun the payouts, which are $4,200 to $6,100 on InsideBarTrailing at 25K and 50K and $0 to $1,500 elsewhere. Across the default shortlists the picture is the same: of 309 runs that passed a Test, 38 were ever paid anything.

## The registry's default shortlists mostly never pay back

The default shortlist ranks a whole archetype by profit factor, so it does not hold the recommended cells. InsideBarTrailing's MNQ top 20 is its `phase=CLOSE` and `volume=THIN` strata at 10 and 15 minutes, and OpeningRange's is its rejection-entry arms, whose held-out profit factors of 180 on MNQ and 260 on NQ belong to the fill assumption rather than the strategy (`docs/findings/m40-prop-objectives.md` § "The pool, and the archive it was re-run on").

"Net > 0" means payouts still exceeded fees at the end of the holdout. Each row is 180 configurations.

| root | preset                         | pays back | net > 0 | median days to pay back, where it does | median attempts |
| ---- | ------------------------------ | --------: | ------: | -------------------------------------: | --------------: |
| MNQ  | Apex 50K                       |      8.3% |    3.9% |                                    167 |               2 |
| MNQ  | Apex 150K                      |      2.2% |    2.2% |                                    195 |               1 |
| MNQ  | TopStep 50K                    | **15.0%** |   11.7% |                                    144 |             5.5 |
| MNQ  | TopStep 150K                   |      8.9% |    8.9% |                                    448 |               1 |
| MNQ  | TakeProfitTrader 25K Test+PRO  |      5.0% |    0.0% |                                    167 |             4.5 |
| MNQ  | TakeProfitTrader 50K Test+PRO  |      1.1% |    1.1% |                                    578 |               3 |
| MNQ  | TakeProfitTrader 150K Test+PRO |      0.0% |    0.0% |                                  never |               1 |
| NQ   | Apex 50K                       |     14.4% |   14.4% |                                    503 |              24 |
| NQ   | Apex 150K                      |     15.0% |   15.0% |                                    452 |              16 |
| NQ   | TopStep 50K                    |     14.4% |   14.4% |                                    337 |              27 |
| NQ   | TopStep 150K                   | **22.2%** |   21.7% |                                    364 |              13 |
| NQ   | TakeProfitTrader 25K Test+PRO  |      0.6% |    0.0% |                                    187 |              21 |
| NQ   | TakeProfitTrader 50K Test+PRO  |      0.6% |    0.6% |                                    211 |              19 |
| NQ   | TakeProfitTrader 150K Test+PRO |      2.2% |    1.1% |                                    292 |            10.5 |

- **85 of the 360 configurations pay back on at least one of the seven presets.** That is the best of seven per configuration, so the per-preset shares above are the fair read. By archetype the 85 are InsideBar 30, DeadCatBounce 12, SqueezeBreakout 12, OpeningRange 11, InsideBarTrailing 9 (all on NQ), EmaPullback 6, PullBackAndGo 3, ElasticBand 2 and EmaCrossover none.
- **When it happens, it happens late.** Of the 198 configuration and preset pairs that pay back, the median takes 341 trading days, more than half the holdout, and the fastest takes 73. Before that point the median trader is $1,639 out of pocket, and at most $8,910.
- **The last twelve months rarely pay.** On every preset the median configuration had no month in which payouts beat fees, and no fresh start that ended ahead.
- **InsideBar on NQ is the one cell where every configuration pays back** on all four Apex and TopStep presets: 20 of 20, from 18 distinct logs, all at 10 minutes, `volume=THIN` and the bracket. It pays back late, though: a median of 200 trading days on TopStep 150K and 503 on Apex 50K. It was picked by looking at the results, so it is a candidate rather than a finding.
- **Losing strategies pay back too.** 22 of the 85 configurations that pay back somewhere lose money held out, with a profit factor below 1. A blown account costs its fees and not its trading losses (`docs/findings/m28-13-account-read.md` § "The reset economics subsidise a losing strategy, so `net` is not a ranking"), so read every row beside its held-out profit factor.

## Re-run through the 2026 presets ([#440])

**What has changed:** the presets, and nothing else. [#440] replaced the single Apex and TopStep presets, which kept an account on its evaluation rules after its pass, with each firm's evaluation linked to the funded account its pass opens, on the terms read on 2026-10-06 and 2026-10-07, with their payout caps, qualifying days, consistency at payout, size limits and Apex's 30-day deadline. It added Lucid's three account types. `docs/roadmap.md` § "Payout rules, size limits and the evaluation's deadline" says how each is replayed. The cells, configurations, contract counts and holdout are the first read's: both re-ran with `--rerun --preset all`, and every TakeProfitTrader row, whose presets did not change, reproduces the first read to the cent. No trade was over any size limit.

Medians over each cell's 20 configurations, as in the first table. "Net > 0" is the share of configurations still ahead at the end of the holdout.

| preset                           | InsideBarTrailing pays back |  days | net          | net > 0 | OpeningRange pays back |  days | net         | net > 0 |
| -------------------------------- | --------------------------: | ----: | ------------ | ------: | ---------------------: | ----: | ----------- | ------: |
| Apex 50K EOD Evaluation+PA       |                        100% |   196 | +$5,976      |    100% |                   100% |   238 | +$2,111     |    100% |
| Apex 50K Intraday Evaluation+PA  |                         65% |   210 | −$1,108      |     35% |                     0% | never | −$2,336     |      0% |
| Apex 150K EOD Evaluation+PA      |                         25% | never | −$5,383      |     25% |                     0% | never | −$5,240     |      0% |
| Apex 150K Intraday Evaluation+PA |                          5% | never | −$3,698      |      5% |                     0% | never | −$3,237     |      0% |
| TopStep 50K Combine+XFA          |                        100% |    36 | **+$13,378** |    100% |                   100% |   235 | **+$6,806** |     85% |
| TopStep 150K Combine+XFA         |                         75% |   498 | −$220        |     45% |                    80% |   247 | −$1,533     |      0% |
| LucidPro 50K                     |                        100% |    40 | +$4,328      |     85% |                    85% |   307 | +$2,196     |     85% |
| LucidPro 150K                    |                         85% |   496 | +$2,950      |     85% |                    60% |   546 | +$1,498     |     55% |
| LucidFlex 50K                    |                        100% |    36 | +$8,956      |    100% |                    85% |   235 | +$6,580     |     80% |
| LucidFlex 150K                   |                         95% |   481 | +$2,846      |     80% |                    85% |   245 | +$1,379     |     85% |
| LucidDaily 50K                   |                        100% |    38 | +$3,259      |     65% |                    60% |   295 | −$2,205     |      0% |
| LucidDaily 150K                  |                         50% | never | −$889        |     45% |                    50% | never | −$731       |     20% |

The three TakeProfitTrader pairs are as the first table has them.

- **The order holds and every figure shrinks.** InsideBarTrailing nets more than OpeningRange on nine of the twelve presets, and the three it does not are ones where both lose money; it pays back sooner on every 50K account; and TopStep 50K nets the most for both. Against the first read's +$19,155 in 24 days, this cell's TopStep 50K figure is about 70% as large and half again as slow; OpeningRange's is about half as large and more than five times as slow.
- **LucidFlex 50K is the second account for both cells**, $226 behind TopStep 50K's median net on OpeningRange and $4,422 behind it on InsideBarTrailing. Every Lucid 50K account pays back on every one of InsideBarTrailing's configurations.
- **Apex pays only on its 50K end-of-day account, and slowly**, a median 196 and 238 trading days before its payouts first exceed its fees. The intraday 50K account breaches a median 82 to 85 of the 87.5 to 88.5 evaluations bought, and **roughly half to two thirds of the 150K evaluations end at the 30-day deadline** rather than in a breach or a pass: by the medians, 28.5 to 37 bought, 9 to 19 breached and 0 to 2 passed.
- **Every 150K account is weak.** None nets more than +$2,950 on either cell, and four of the six lose money on OpeningRange. Their targets, payout rules and size are large beside what six or four micro contracts make.
- **The fastest preset to profit is not a profitable one.** It is TakeProfitTrader 25K for 16 of InsideBarTrailing's 20 configurations and LucidDaily 50K or TakeProfitTrader 50K for 10 of OpeningRange's, and each of those presets loses money at its median by the end of the holdout.

## What this settles

- **For a prop account, both recommended cells pay back on Apex and TopStep**, InsideBarTrailing sooner, and TopStep 50K soonest. That agrees with the choice `docs/findings/README.md` already makes.
- **Neither cell pays on TakeProfitTrader once its Test is linked to its PRO.** Every earlier Test-alone net overstates that firm, and `docs/findings/README.md` now says so where it quotes one.
- **The registry's default shortlists mostly do not pay back their fees,** and when they do it takes more than half of a holdout of about two and a third years.
- **Apex's and TopStep's funded accounts are now modelled, and they pay less than the first read said.** The re-run above keeps InsideBarTrailing ahead and TopStep 50K as its account, at about 70% of the net and half again the time, and leaves Apex worth trading only on its 50K end-of-day account.

[#411]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/411
[#440]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/440
