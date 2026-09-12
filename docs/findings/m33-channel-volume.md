---
id: M33
title: "M33 — the volume answer belongs to the channel, and the two campaigns were both right"
archetypes: [ElasticBand]
issues: [300]
gates: [1, 2]
outcome: mixed
verdict: >-
  Holding the bracket and the shape still and swapping the channel flips `HEAVY` from a cost to a benefit and `NORMAL` from a benefit to a cost on both roots in both windows, so a context result belongs to a configuration; the channel flips 50 of 108 held-out cuts against the shape's 36, and the arm that reproduces §M30's answer does it at a median held-out profit factor of 0.94.
---

# M33 — the volume answer belongs to the channel, and the two campaigns were both right ([#300])

**What has changed since §M30, stated first.** No new condition and no new simulation code. What is new is one variant set — `--variants elastic-channel`, four arms crossing the channel with the signal-bar shape over §M26.9's bracket — so that exactly one thing differs between two rows. §M26.9 and §M30 put the same nine fitted volume cuts through grids differing in three ways at once (the channel, the shape, and a held bracket against a swept target ladder) and returned opposite answers; neither could say which of the three carried it. This varies two of them and holds the third.

**The answer is the channel.** `HEAVY` is a cost on the VWAP band and a benefit on the Bollinger band; `NORMAL` is the reverse. Both readings reproduce, on both roots, in both windows, at the same bracket and the same shape — so neither earlier campaign was wrong, and neither was measuring ElasticBand.

## The VWAP arm reproduces §M26.9 exactly, which is what makes the Bollinger arm readable

The set's two VWAP arms are §M26.9's two variants parameter for parameter — the ladder, the bracket, `min_one_sided_bars`, the costs and the pinned `band_period` all agree, and `tests/test_campaign_sweep.py` pins that they do. Joined on 44 columns across both windows, **15,610 stored rows agree to zero difference on profit factor, trades, net P&L, win rate, maximum drawdown and session-close share.**

**That check silently passed on nothing the first time it was run.** §M26.9 is batch 10 and `entry_trigger`, `recovery_fraction` and `band_stop_std` were added to the `combos` table by §M26.6 and §M26.8 afterwards, so they are null in its rows and populated in these — and a null equals nothing, so all 15,610 pairs were dropped and every statistic reported `exact` over an empty frame. `campaign_crossread.ran_at` fills a null parameter with the archetype's own default and is what makes the join work. This is §M30's own loose end arriving a second time; the lesson is that a paired read has to report its pair count and refuse to conclude from zero.

## Paired, cell by cell: the sign is the channel's

Median change in profit factor against the **unfiltered stratum** of the same arm, at the same root, resolution, form, tail and axis values, both sides clearing 30 trades. `cuts favourable` counts how many of the nine form × tail cuts have a median above zero. Held-out window:

| shape    | state  | root | channel   | pairs | median ΔPF | wins  | cuts favourable |
| -------- | ------ | ---- | --------- | ----: | ---------- | ----- | --------------- |
| any      | HEAVY  | MNQ  | bollinger |   810 | **+0.044** | 71.9% | **9 of 9**      |
| any      | HEAVY  | MNQ  | vwap      |   768 | −0.013     | 43.1% | 4 of 9          |
| any      | HEAVY  | NQ   | bollinger |   810 | **+0.041** | 71.0% | **9 of 9**      |
| any      | HEAVY  | NQ   | vwap      |   747 | +0.003     | 51.3% | 5 of 9          |
| any      | NORMAL | MNQ  | bollinger |   810 | −0.019     | 36.0% | 1 of 9          |
| any      | NORMAL | MNQ  | vwap      |   800 | +0.023     | 61.3% | 6 of 9          |
| any      | NORMAL | NQ   | bollinger |   810 | −0.025     | 31.6% | 1 of 9          |
| any      | NORMAL | NQ   | vwap      |   791 | +0.007     | 53.4% | 5 of 9          |
| reversal | HEAVY  | MNQ  | bollinger |   429 | +0.015     | 54.5% | 7 of 9          |
| reversal | HEAVY  | MNQ  | vwap      |   526 | **−0.056** | 28.9% | **0 of 9**      |
| reversal | HEAVY  | NQ   | bollinger |   444 | +0.023     | 56.3% | 5 of 9          |
| reversal | HEAVY  | NQ   | vwap      |   470 | **−0.081** | 22.3% | **1 of 9**      |
| reversal | NORMAL | MNQ  | bollinger |   462 | −0.036     | 38.3% | 2 of 9          |
| reversal | NORMAL | MNQ  | vwap      |   578 | **+0.071** | 74.7% | **9 of 9**      |
| reversal | NORMAL | NQ   | bollinger |   480 | −0.027     | 39.4% | 2 of 9          |
| reversal | NORMAL | NQ   | vwap      |   534 | **+0.043** | 63.3% | **8 of 9**      |

**The four bold VWAP rows are §M26.9's table, to three decimal places and the same pair counts.** The four bold Bollinger rows are §M30's direction: `HEAVY` favourable at all nine cuts on both roots, `NORMAL` favourable at one of nine on both. Both campaigns reproduce at one bracket, so what separated them was never the bracket or the target ladder.

`THIN` is a cost under every arm and is the one state the channel does not reorder — −0.018 to −0.083 across the eight rows, favourable in 2 to 5 cuts of nine.

## One cell settles it

`volume=NORMAL@per_bar_20 q=0.20/0.80`, `shape=reversal`, the same bracket, scored the §M28.14 way over ten `root × resolution` cells:

| channel   | score  | median ΔPF held out | median PF held out | median trades |
| --------- | ------ | ------------------- | ------------------ | ------------: |
| vwap      | **+6** | +0.067              | **1.235**          |           274 |
| bollinger | **−8** | −0.080              | **0.901**          |           393 |

Same archetype, same cut, same tail, same shape, same bracket, same two windows. **A consistent helper at a profit factor of 1.235 and a consistent cost at 0.901, separated by which channel the extension was measured from.** Reproduce with `tools/campaign_crossread.py --variant`, which is what this campaign added to that tool: its `common_variants` intersects the *plain* strata, and a campaign whose every filtered stratum is a re-cut has none, so the arms had to be named outright.

## The channel reorders more than the shape does

Each of the nine cuts × three states × two roots read under all four arms, so both dimensions are measured over the same 54 cuts per window. Median absolute move in a cut's ΔPF, and how many cuts change sign:

| window    | channel, at `shape=any` | channel, at `shape=reversal` | shape, on vwap | shape, on bollinger |
| --------- | ----------------------- | ---------------------------- | -------------- | ------------------- |
| holdout   | 0.047                   | **0.080**                    | 0.058          | 0.027               |
| selection | 0.037                   | **0.073**                    | 0.018          | 0.043               |

| window    | channel flips | shape flips |
| --------- | ------------- | ----------- |
| holdout   | **50 of 108** | 36 of 108   |
| selection | **44 of 108** | 20 of 108   |

**Read the flip counts rather than the magnitudes.** On magnitude the two dimensions trade places depending on which arm they are measured at — the channel moves a cut more under `shape=reversal` and less under `shape=any`. On *direction* the channel is consistently the larger lever, and direction is what a stratum table reports.

## Beating your own unfiltered twin is still not making money

The arm that reproduces §M30 does not reproduce a profit. Held-out medians over the cells whose ΔPF is positive:

| channel   | shape    | state  | root | median ΔPF | median PF | share above 1.0 |
| --------- | -------- | ------ | ---- | ---------- | --------- | --------------- |
| vwap      | reversal | NORMAL | MNQ  | +0.071     | **1.212** | 80.1%           |
| vwap      | reversal | NORMAL | NQ   | +0.043     | **1.165** | 77.9%           |
| bollinger | any      | HEAVY  | MNQ  | +0.044     | **0.938** | 28.4%           |
| bollinger | any      | HEAVY  | NQ   | +0.041     | **0.967** | 38.1%           |

**§M30's `HEAVY` cells beat their own unfiltered twin at nine of nine cuts and lose money doing it**, 0.938 and 0.967 with about a third of configurations above 1.0. §M26.9's `NORMAL` cells clear their twin and clear 1.0, four fifths of them. So the two answers are not symmetric even though both reproduce: one is attached to a configuration that returns something and the other is a smaller loss than the loss beside it. §M28.14 and §M30 both record this trap; this is the first time the same dimension has been caught on both sides of it at once.

## The sample cost the issue predicted, met rather than discovered

**76.9% of rows clear 30 trades**, against §M26.9's 77.4% — the channel is a fourth arm rather than a second gate in conjunction, so it thins nothing further. Per arm it is 98.4% and 92.9% under `shape=any` on Bollinger and VWAP, and 54.4% and 62.0% under `shape=reversal`. MNQ `HEAVY` cells by resolution:

| resolution | bollinger any | bollinger reversal | vwap any | vwap reversal |
| ---------- | ------------- | ------------------ | -------- | ------------- |
| 1m         | 1.00          | 0.71               | 1.00     | 0.96          |
| 5m         | 1.00          | 0.56               | 0.97     | 0.63          |
| 15m        | 1.00          | 0.41               | 0.88     | **0.31**      |

The coarse `shape=reversal` cells are the thin ones in both channels, and every figure quoted above pools five resolutions — so the medians lean on the fine bars, where `docs/roadmap.md` § "Stored sweeps" records that the archetype's median configuration loses money.

## What this does not settle

- **No cell here has been through gate 3.** This is a paired read of gate 1 and gate 2 and nothing else. The family would have to be stated in advance, and a matched null over cells chosen from this table is the multiple-comparisons trap §M28.16 names.
- **"A context result belongs to a configuration" is demonstrated for one dimension of one archetype.** The channel is the entry's own definition, so this is close to the strongest case such a flip could have — the volume state is being read against a differently-defined signal population, which §M26.9 already measured as 2.1× enriched in `HEAVY` under one form and under-represented under another. It generalises as a warning to read every stratum figure in the register against the grid it was run at, not as a proof that any particular one moves.
- **`band_period` is pinned at 20 where §M30 swept three rungs.** The parameter's own default and the middle rung, chosen before the run rather than off this table, but it costs the Bollinger arm the best-of-three every §M30 cell had — so the Bollinger rows here are a slightly weaker version of that campaign's and the reproduction is of its *direction*.
- **`min_bars_outside` is held out of the bracket, carried across from §M26.9 rather than re-measured.** §M26.5 measured it as a duplicate on 82.7% of `shape=reversal` cells *on the VWAP band*; `.claude/rules/sweep-and-context.md` says not to carry a measured deadness across to a different entry rule, and the Bollinger channel is a different population of 2σ closes. It may be live on that arm and nothing here would show it.
- **The tail sizes and the two volume windows are §M27.8's and §M32's, not re-examined.** A tenth, a fifth and a third, at `volume_rolling_bars = 30` and `volume_baseline_sessions = 20`.
- **Nothing is re-ranked and no archetype is retired or revived.** §M26.9's and §M30's stored rows are untouched; what is new is 40,320 rows under four names nobody had run.

## Reproducing it

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants elastic-channel --split \
    --strata elastic-channel --volume-quantiles --n-jobs 1
./.venv/Scripts/python.exe tools/campaign_crossread.py --strategies ElasticBand \
    --dimension volume --min-score 6 --variant "channel-volume channel=vwap shape=reversal target=0.0s" \
    "channel-volume channel=bollinger shape=reversal target=0.0s"
```

**`--n-jobs 1` is not a typo and is worth about half the runtime.** `run_point` opens a joblib pool per (variant × cell), which here is 112 pools of 18 combinations each, and a pool costs more than the parallelism returns at that size: measured at the dearest of the twenty points, 76.4 s serial against 94.9 s at eight workers and 105.5 s at sixteen. The whole 40,320-row run took **7.6 minutes of simulation and 6.8 minutes of wall clock**, against an estimate of fifteen made by scaling §M26.9's stored timings — the estimate was right about the fine bars and far too pessimistic about the coarse ones, where the pool overhead is most of the cost. `.claude/rules/sweep-and-context.md` § "Parallel sweeps top out around 5×" is the all-core figure for one large sweep and is not in conflict: it measures a pool that is already open.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/ElasticBand.duckdb` plus `tools/campaign_sweep.py` and `tools/campaign_crossread.py` — not a standing property.

[#300]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/300
