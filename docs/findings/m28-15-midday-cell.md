---
id: M28.15
title: "M28.15 — the midday cell through the three reads that stopped it being a recommendation"
archetypes: [OpeningRange]
issues: [287]
gates: [4]
outcome: mixed
verdict: >-
  Ten of ten walk-forward folds are profitable out of sample and the account funds on MNQ, but without the flatten there is no book to read — and 2026 remains the weakest year.
---

# M28.15 — the midday cell through the three reads that stopped it being a recommendation ([#287])

**No new sweep.** §M28.14 found the first cell in the registry to clear gates 2, 3 and 4 on both roots — `OpeningRange phase=MIDDAY` at 5 minutes — and named three things that stopped it being a recommendation. Two of them needed tooling that did not exist: §M28.13 replayed the registry through `nqbt/propaccount.py` from a script that was never committed, and nothing anywhere could say what a configuration is worth *without* one exit reason. Both are tools now — `tools/campaign_propaccount.py` and `tools/campaign_exits.py` — and every figure below comes out of the stored rows plus those two and the two gate-4 tools that already existed.

## The cell, stated before it was read

**One variant, chosen on a rule rather than on a result.** §M28.14's null ran the cell pooled over the variants its shortlist happened to draw, which is the dilution §M28.9 measured the cost of; `campaign_walkforward` and `campaign_montecarlo` both take `--variant` for that reason. The arm taken here is the one §M28.14's own shortlist is most made of — `window=30m stop=opposite target=R`, 4 of the 10 MNQ rows and 6 of the 10 NQ rows, and the top row on NQ. That confinement leaves 32 stored rows per root, of which the shortlist is 20.

**Every read below is the held-out pair.** `tools/campaign_shortlist.py --held-out` stores the logs of the configurations the *selection* window ranked highest, and `campaign_holdout.held_out` is the function; nothing here is ranked on the window it is then read from, which is the trap §M28.12 records. It also means these 20 rows are not §M28.14's 10, so the figures sit beside that section's rather than reproducing them.

## Walk-forward: five folds each, and ten of the ten are profitable out of sample

`tools/campaign_walkforward.py`, sliding, train 50% / test 10% of the 5-minute series.

| root | bars    | folds | selected | distinct picks | train median | test median | test pooled | test trades | passes |
| ---- | ------- | ----- | -------- | -------------- | ------------ | ----------- | ----------- | ----------- | ------ |
| MNQ  | 338,431 | 5     | 5        | 2              | 1.403        | 1.365       | **1.279**   | 311         | yes    |
| NQ   | 326,895 | 5     | 5        | 1              | 1.493        | 1.270       | **1.302**   | 297         | yes    |

Every fold's own out-of-sample profit factor is above 1 on both roots, at 1.096–1.461 on MNQ and 1.125–1.471 on NQ. **NQ picks the same configuration in all five folds and MNQ picks between two**, so what the folds test is barely a selection — which is the honest reading of a 32-row population and not a strength.

**The last fold is the weakest on both roots** — 1.096 and 1.125, over 2026-02 to 2026-08 — which is §M28.10's collapse arriving again on a cut nothing here chose.

Two things this does not say. The pool was ranked on stored selection rows while the folds run over the whole spliced series, so the pool has seen part of every fold; what survives is **picking within the pool**, not the pool. And five folds of one instrument at one bar size are nowhere near five independent trials.

## Monte Carlo: the drawdown is not the ordering's, and the sample cannot exclude a loss

`tools/campaign_montecarlo.py --held-out`, 1,000 resamples, 20 configurations per root.

The permutation test reorders the same trades and asks whether the drawdown was the sequence's doing. It was not: p runs **0.457–0.900 on MNQ and 0.411–0.831 on NQ**, and the observed drawdown sits *below* its own null median on 18 of 20 MNQ configurations and 12 of 20 NQ ones. Reshuffling these trades makes the equity path worse more often than better.

The bootstrap is the one that bites:

| root | observed PF (median) | bootstrap p05 PF | bootstrap p05 net  | share of resamples below zero |
| ---- | -------------------- | ---------------- | ------------------ | ----------------------------- |
| MNQ  | 1.216                | 0.794–0.964      | −23,491 – −3,459   | 0.075–0.359, median 0.139     |
| NQ   | 1.251                | 0.822–0.985      | −191,318 – −13,780 | 0.057–0.276, median 0.113     |

**Not one of the 40 configurations has a 5th percentile above a profit factor of 1.0 or above zero net.** About one resample in eight of a configuration's own trades loses money. That is §M28.1's sample-size objection sized rather than asserted, and it is the strongest thing said against this cell by anything in this section: the walk-forward says the choice survives and the bootstrap says the sample cannot rule out that the whole result is noise at the 5% level.

## The account: it funds on MNQ on every rule set, and on NQ on one

`tools/campaign_propaccount.py`, the four presets §M28.13 read the registry through, attempts uncapped — the cap that bound on 98% of §M28.13's population run cannot bind here, and every row says so. Four contracts throughout, which is the log's own `order_quantity`.

Medians across the 20 configurations, `PEAK_FIRST` — the order every preset carries:

| root | preset       | attempts | passes | net         | ever passed | net > 0 |
| ---- | ------------ | -------- | ------ | ----------- | ----------- | ------- |
| MNQ  | Apex 50K     | 31       | 4.5    | **+17,718** | 100%        | 100%    |
| MNQ  | Apex 150K    | 8        | 2      | **+21,327** | 100%        | 100%    |
| MNQ  | TopStep 50K  | 64       | 7      | **+9,919**  | 100%        | 100%    |
| MNQ  | TopStep 150K | 7        | 2      | **+26,982** | 100%        | 100%    |
| NQ   | Apex 50K     | 233      | 0      | −38,911     | 0%          | 0%      |
| NQ   | Apex 150K    | 227      | 0      | −68,013     | 0%          | 0%      |
| NQ   | TopStep 50K  | 226      | 0      | −11,123     | 0%          | 0%      |
| NQ   | TopStep 150K | 165      | 2      | **+8,797**  | 90%         | 80%     |

**On MNQ every configuration passes every rule set and every one is profitable after fees.** No cell in §M28.13's read of the registry did that; the closest was InsideBar MNQ at 95% of configurations profitable on Apex 50K, on a different shortlist and with a higher median net. The comparison is a direction, not a ranking — §M28.13's figures are a subsample of a different selection.

**On NQ a median of 233 attempts over 236 trades means every account died on its first trade**, and that is the arithmetic §M28.13 recorded rather than anything about the entry: four NQ contracts leave 31 points of room under Apex 50K's trailing threshold and 313 under the same account on MNQ. TopStep 150K is the one preset with room enough (56 points) to fund the same trades.

`excursion_order` moves NQ and leaves MNQ where it is, exactly as §M28.13 measured:

| root | preset       | net, `PEAK_FIRST` | net, `TROUGH_FIRST` | ever passed |
| ---- | ------------ | ----------------- | ------------------- | ----------- |
| NQ   | Apex 50K     | −38,911           | **+139,891**        | 0% → 100%   |
| NQ   | Apex 150K    | −68,013           | **+203,116**        | 0% → 60%    |
| NQ   | TopStep 50K  | −11,123           | −11,123             | 0% → 0%     |
| NQ   | TopStep 150K | +8,797            | +8,797              | 90% → 90%   |
| MNQ  | Apex 50K     | +17,718           | +18,025             | 100% → 100% |

**TopStep does not move at all because it trails end-of-day**, so no intraday peak reaches its high-water mark and the order within a trade cannot matter. That is the mechanism named rather than a coincidence, and it is why the two Apex rows are the ones the assumption decides.

## Without the flatten there is no book to read

`tools/campaign_exits.py`, `stats.summarise` over the legs that did not leave by `session_close`.

| root | legs | flatten legs | flatten net | whole PF | whole net | rest PF | rest net | rest trades | survives |
| ---- | ---- | ------------ | ----------- | -------- | --------- | ------- | -------- | ----------- | -------- |
| MNQ  | 968  | 628 (65%)    | +59,557     | 1.216    | +19,088   | 0.371   | −45,981  | 106 of 242  | 0 of 20  |
| NQ   | 944  | 619 (66%)    | +598,853    | 1.251    | +212,904  | 0.392   | −421,649 | 101 of 236  | 0 of 20  |

Medians across the 20 configurations per root. **Every one of the 40 is profitable whole and none of the 40 is profitable without the flatten**, at a residual profit factor of 0.149 to 0.734 — the legs the bracket closed won about a third of what they lost. Fewer than half the trades have any leg left at all, and the residual drawdown is roughly four times the whole book's.

**It is a decomposition and not a counterfactual**, exactly as §M28.12 states it: a leg the clock closed is a leg the stop did not take, and these bars do not say where it would have gone instead. What it settles is the weaker and sufficient claim — this cell's result is the flatten's, measured on the residual rather than inferred from the split. The lever that would change it is a bracket that closes the position before 17:00, and that is [#262]'s truncated `stop_range_fraction` on a different cell.

## The verdict, and what [#287] asked

- **Gate 4's own machinery agrees with §M28.14 and adds one thing it could not.** The walk-forward passes on both roots with every fold profitable out of sample, the permutation test clears the drawdown of being an ordering artefact — and the bootstrap says the sample is too small to exclude a losing outcome at 5% on any of the 40 configurations.
- **The account reading is the best in the registry on MNQ and an empty one on NQ**, and the NQ half is contract size rather than the strategy. Position size is a campaign axis nothing has ever swept — §M28.13, "What travels and what does not" — and this is the second cell where it decides the answer.
- **The flatten is the whole result, now measured rather than inferred.** §M28.12 diagnosed it across the registry, §M28.14 reproduced it inside the cell by exit reason, and the residual read closes it: nothing survives the exclusion on either root.
- **Still not a recommendation.** Two of [#287]'s three objections now have measurements behind them and the third has not moved: 2026 remains the weakest year, it carries the largest drawdown, and the walk-forward's final fold is the weakest on both roots. Trading this is a bet that a regime returns — §M28.10 — sized by an account that funds on MNQ and cannot be opened at this position size on NQ.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_shortlist.py --held-out` and the four tools named above — not a standing property.

[#262]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/262
[#287]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/287
