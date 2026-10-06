---
id: M51
title: "M51 — when the money comes back: every archetype's shortlist through every preset"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [411]
gates: []
outcome: mixed
verdict: >-
  Through every preset, at most 22% of a root's 180 shortlisted configurations ever have payouts exceeding fees inside the holdout, and those that do take a median 341 of about 612 trading days; in the last 12 whole months the median configuration had no profitable month on any preset. TakeProfitTrader's linked Test and PRO almost never pay back. The one cell every configuration of which pays back is InsideBar's 10-minute volume=THIN bracket on NQ, on Apex and TopStep only, and late. 22 of the 85 configurations that pay back anywhere lose money held out. These are the default top-20 shortlists, not the findings' recommended cells.
---

# M51 — when the money comes back: every archetype's shortlist through every preset ([#411])

**What has changed, stated first.** No new sweep, condition or archetype. `tools/campaign_propaccount.py` now dates every fee and payout, chains TakeProfitTrader's Test to the PRO its pass opens, and reports how many trading days pass before payouts exceed fees and how the last whole months went. `tools/README.md` § "campaign_propaccount.py" says what each figure is measured over. This is its first run across the registry.

## What was run

- **Every registered archetype on MNQ and NQ**, each through its default held-out shortlist: the top 20 configurations by selection-window profit factor, across every stratum and bar size. That is 360 configurations, with 11 to 20 distinct trade logs per cell.
- **Logs re-run on the bars each row was swept on** (`--rerun`), since most shortlists have no stored log. All 360 reproduced their stored trade count and net exactly.
- **`--preset all`:** Apex and TopStep at 50K and 150K, and TakeProfitTrader's three linked pairs. That is 2,520 replays, each with 12 fresh starts.
- **The holdout** runs 13 May 2024 to 18 September 2026: 613 trading days on MNQ and 611 on NQ. The monthly figures cover September 2025 to August 2026, the default `--last-months 12`.
- Costs are the campaign's own, as `docs/findings/README.md` states them. The run took 27 minutes on two cores, and its output is in `results/prop-replay/`.

## This is not the findings' recommended cells

The default shortlist ranks a whole archetype by profit factor, so it does not hold the cells `docs/findings/README.md` recommends. InsideBarTrailing's MNQ top 20 is its `phase=CLOSE` and `volume=THIN` strata at 10 and 15 minutes, not `phase=MIDDAY` at 5. OpeningRange's is its rejection-entry arms, mostly unfiltered at 15 minutes, not the `phase=MIDDAY` opposite-extreme stop at 5. Those rejection arms' held-out profit factors, a median of 180 on MNQ and 260 on NQ, belong to the fill assumption rather than the strategy (`docs/findings/m40-prop-objectives.md` § "The pool, and the archive it was re-run on"). **Nothing here speaks for or against the recommended cells.**

## Few configurations ever pay back their fees

"Pays back" means total payouts exceeded total fees on some day of the holdout; "net > 0" means they still did at its end. Each row is 180 configurations.

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

85 of the 360 configurations pay back on at least one of the seven presets, but that is the best of seven per configuration, so the per-preset shares are the fair read. By archetype the 85 are: InsideBar 30, OpeningRange 11, DeadCatBounce 12, SqueezeBreakout 12, InsideBarTrailing 9 (all on NQ), EmaPullback 6, PullBackAndGo 3, ElasticBand 2 and EmaCrossover none.

## When it happens, it happens late

Of the 198 configuration and preset pairs that pay back, **the median takes 341 trading days, more than half the holdout**, and the fastest takes 73. Before that point the median trader is $1,639 out of pocket, and at most $8,910. Days to profit is a best case, because every payout is taken in full on the first day it is allowed.

## The last twelve months rarely pay

On every preset, the median configuration had no month of the twelve in which payouts beat fees, and no fresh start that ended ahead. Among the pairs that pay back, the median is one profitable month of twelve, and 73 of the 198 would not have ended ahead starting in any of those months.

## TakeProfitTrader's linked accounts almost never pay back

0 to 5% of configurations pay back on any size or root, and the median number of Tests passed is 0 everywhere. Between 9% and 39% of configurations pass a Test at all, depending on size and root, but of the 309 runs that passed one only 38 were ever paid anything: the PRO rarely gets far enough above its starting balance to withdraw. TakeProfitTrader is the fastest preset for 3 of the 85 configurations, where TopStep is fastest for 72.

## InsideBar on NQ

This is the one cell where every configuration pays back on all four Apex and TopStep presets: 20 of 20, from 18 distinct logs, all in one cell. That cell is 10-minute bars, `volume=THIN` and the bracket, with held-out profit factors from 1.31 to 3.40. **It pays back late**: a median of 200 trading days on TopStep 150K and 503 on Apex 50K, after $800 to $5,500 out of pocket, with one or two profitable months of twelve. On TakeProfitTrader it pays back for only 1 or 2 of the 20. It is one cell of 18, picked by looking at the results, so it is a candidate rather than a finding.

## Losing strategies pay back too

22 of the 85 configurations that pay back somewhere, and 47 of the 198 pairs, lose money held out with a profit factor below 1. A blown account costs its fees and not its trading losses, so variance alone can pay back the fees (`docs/findings/m28-13-account-read.md` § "The reset economics subsidise a losing strategy, so `net` is not a ranking"). Read every row beside its held-out profit factor.

## What this settles

For the registry's default shortlists, an evaluation that pays back its fees at all mostly does so after more than half of a holdout of about two and a third years, and the last year rarely produced a profitable month. It does not test the recommended cells. Running `campaign_propaccount.py --stratum phase=MIDDAY --resolution 5 --rerun --preset all` on InsideBarTrailing and OpeningRange would be that read.

[#411]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/411
