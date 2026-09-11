---
id: M28.13
title: "M28.13 — the registry read through an account, and the assumption that turned out to be a parameter"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [75]
gates: []
outcome: mixed
verdict: >-
  Survival is not the question and reading it as one inverts the answer; the binding constraint is position size rather than the strategy, and the excursion order was an assumption and is now `excursion_order`.
---

# M28.13 — the registry read through an account, and the assumption that turned out to be a parameter ([#75])

The first reading of the whole stored registry through `nqbt/propaccount.py`. It answers a question none of the gates in §M27 or §M28 can be expressed in — **not "is the edge real" but "would the account have survived it, and would it have made more than it cost"** — and it changes the ordering of the registry rather than confirming it.

**Two runs, and every figure below says which it came from.** The **population** run replays all **1,066 stored held-out configurations** across all seven archetypes and both roots, capped at five attempts. The **subsample** run replays every fourth stored row in `combo_id` order — 178 configurations, InsideBar and OpeningRange only — with the attempt cap raised past what any of them reach, which is what the economics need. Both take the holdout shortlists exactly as `campaign_holdout` chose them on the selection window: **nothing here is re-ranked on the window it is then read from**, which is the trap §M28.12 records.

Costs are the campaign's own — $1.50 per contract on MNQ, $4.50 on NQ, one tick of slippage, four contracts throughout. That last number turns out to be the finding.

## Survival is not the question, and reading it as one inverts the answer

**No NQ configuration survives its first account, on any of the four presets: 0 of 526.** On MNQ roughly 98% of configurations breach their first Apex 50K somewhere in the ~430-day holdout. Read as a verdict that is an empty registry.

It is the wrong reading, and the capped run is what makes it look right. The five-attempt cap binds on **98%** of configurations, so the population run stops while most of them are still trading and its net figures are truncated — badly enough to be **wrong in sign**. Uncapped, on the subsample, Apex 50K:

|                  | n   | attempts | passes | withdrawn |    fees |          net | net > 0 |
| ---------------- | --- | -------: | -----: | --------: | ------: | -----------: | ------: |
| InsideBar MNQ    | 80  |       56 |      8 |   $40,292 | $13,417 | **+$26,585** | **95%** |
| OpeningRange MNQ | 12  |       48 |    2.5 |   $26,171 | $11,635 | **+$14,045** |     75% |

Medians. The accounts nearly all die; the **sequence** of accounts is overwhelmingly profitable, because a blown account costs its fees and not its trading losses. **"Did it survive" and "was it worth trading" are close to independent questions here**, and only the second one is about money.

## It re-ranks, which is what [#75] was for

Spearman rank correlation of the prop verdict against the two bases the registry is currently ordered by, MNQ, 100-trade floor, population run: **+0.199 with profit factor and +0.144 with net-to-max-drawdown**. Near-orthogonal. Whatever this measures, the existing columns do not already contain it.

Where it puts the two archetypes at the front is a straight reversal of their bracket reading in §M28.12. Ever-passed on the population run, MNQ: **OpeningRange 82.2% against InsideBar 43.8% on TopStep 150K** (n = 45 and 320). OpeningRange is the archetype that *funds*; InsideBar has the higher ceiling and the worse median, and is negative at the median on every preset.

## The binding constraint is position size, not the strategy

Four contracts is the campaign's fixed size and it is a full-size position on NQ. The trailing threshold divided by the dollar value of a point is the entire account's room to move:

| account      | threshold | 4 NQ ($80/pt) | 4 MNQ ($8/pt) |
| ------------ | --------: | ------------: | ------------: |
| Apex 50K     |    $2,500 |    **31 pts** |       313 pts |
| TopStep 50K  |    $2,000 |    **25 pts** |       250 pts |
| Apex 150K    |    $5,000 |        63 pts |       625 pts |
| TopStep 150K |    $4,500 |        56 pts |       563 pts |

Twenty-five points is smaller than a single stop at the resolutions these archetypes are swept at. The best NQ InsideBar configuration on the holdout — 668 trades, profit factor 1.229, **$320,236 net on paper** — is dead on its first trade. **That is arithmetic about contract size and says nothing about the entry rule**, and it is the reason the NQ column above is not a verdict on NQ.

## The excursion order was an assumption and is now `excursion_order`

The replay could not order a trade's favourable and adverse excursions — the bars do not record which came first — and it took the harsher reading, applying the peak so that it raises the floor before the same trade's trough is tested against it. That was recorded as a deliberate assumption. Measuring it says it is not a tiebreak.

Apex 50K, subsample, **only the order changes**:

|                  | n   | trades before the first breach |                      net |   net > 0 |
| ---------------- | --- | -----------------------------: | -----------------------: | --------: |
| InsideBar MNQ    | 80  |                        17 → 17 |      +$26,585 → +$28,029 | 95% → 95% |
| OpeningRange MNQ | 12  |                      6.5 → 6.5 |      +$14,045 → +$23,323 | 75% → 83% |
| InsideBar NQ     | 79  |                      **1 → 5** |  **−$10,020 → +$21,540** | 42% → 77% |
| OpeningRange NQ  | 7   |                          1 → 1 | **−$10,020 → +$303,486** |  0% → 71% |

Medians, peak-first → trough-first. **On MNQ the assumption is nearly free; on NQ it decides the answer**, and the mechanism is the table above it: with 31 points of room a single trade's own peak can lock the floor above its own trough, and with 313 points it almost never can. 27% of configurations are unaffected either way.

So it became a parameter rather than staying a comment. `ExcursionOrder.PEAK_FIRST` remains the default and every preset carries it, so nothing already measured moved; `TROUGH_FIRST` defers the peak past the trough test and **still records it**, so the floor it raised binds every later trade under both orders.

**The earlier proxy for this overstated it.** Comparing `TrailBasis.INTRADAY` against `END_OF_DAY` changes whether *any* intraday peak reaches the high-water mark, not just the order within one trade, and read that way InsideBar NQ came out at +$61,722 against the +$21,540 the isolated parameter gives. Use the isolated figure; the proxy changes two things at once.

## The reset economics subsidise a losing strategy, so `net` is not a ranking

From the subsample, uncapped, Apex 50K:

| combo | trades | profit factor | attempts | passes | withdrawn |         net |
| ----: | -----: | ------------: | -------: | -----: | --------: | ----------: |
|    34 |  7,384 |     **0.932** |       60 |      6 |   $17,260 | **+$3,120** |
|    42 |  7,513 |     **0.917** |       60 |      3 |   $11,030 |     −$2,219 |

Combination 34 **loses money as a strategy and makes money as a business**, because each blown account caps the loss at the fee while the wins were already withdrawn. That is real prop economics rather than a modelling artefact — it is what the firms price their fees and consistency rules against — but it means **`net` rewards variance and can rank a losing configuration above a winning one.** Read it beside the profit factor and the pass rate; it does not replace either, and no gate should be expressed in it alone.

## What travels and what does not

- **Position size is now a campaign axis whether or not it is swept.** Every figure in the registry is four contracts, and four contracts is a different instrument-sized bet on each root.
- **The preset fees are list prices** and TopStep's `withdrawal_threshold` is a conservative stand-in, so every dollar total above is a floor rather than an estimate — § "Replaying a prop account over the trade log" has the provenance.
- **OpeningRange NQ is n = 7.** Its +$303,486 is one or two configurations and is quoted as a direction, not a magnitude.
- **The replay costs one `stats.summarise` per attempt per configuration**, which is why the uncapped run is a subsample rather than the population. Worth fixing before this becomes a routine campaign step.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_shortlist.py` — not a standing property.

[#75]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/75
