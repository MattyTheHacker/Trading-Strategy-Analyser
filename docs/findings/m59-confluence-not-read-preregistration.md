---
title: "M59 — pre-registration: EmaCrossover's confluence count over conditions it does not read"
archetypes: [EmaCrossover]
issues: [74, 439]
gates: [3]
outcome: spec
verdict: >-
  Written and committed before the run: each EmaCrossover trade at its defaults counted over five conditions that read no moving average — the VWAP side, the signal bar's body, a new high or low, the Bollinger midline side and a break of the cash opening range, each for the trade's own side at its signal bar — against 200 matched random entries, at 5 minutes on both roots in the full, selection and held-out windows; the count is read as edge only where its top stratum beats its null's 95th percentile and outruns its bottom stratum's excess on both roots in both windows.
---

# M59 — pre-registration: EmaCrossover's confluence count over conditions it does not read ([#439])

[Counting the confluence a trade actually had](confluence-count-per-trade.md) found EmaCrossover's profit factor rising with how many of five conditions held at entry, and a matched random entry removing most of the rise: **the count sorted trades rather than adding edge.** It named its own weakness: `above_ema_21` held on 88.6% of the entries of an EMA(9)/EMA(21) long, so the count and the entry shared machinery, and "a set drawn from indicators the archetype does not read would be the cleaner test and has not been run". This is that test.

**What has changed since that count**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks:

- **The conditions**, which are the point. None reads a moving average of any kind the archetype computes, nor the trend or higher-timeframe labels, which are built from averages too.
- **The bar they are read at**, which is the signal bar rather than the fill bar — § "Read at the signal bar".
- **The sample**: both sides rather than the long side alone, both roots rather than MNQ, the whole spliced series rather than the series after its first roll, and the campaign's own 60/40 windows. The earlier count dropped the bars before the first roll for a gapped-target case [#452] has since settled.
- **The null**: 200 draws rather than 20, `randomentry`'s default.

The run is [`tools/campaign_confluence.py`](../../tools/campaign_confluence.py), and its options are [`tools/README.md`](../../tools/README.md) § "campaign_confluence.py".

**This file was written and committed before the run.** The conditions, the cells, the bar below and the predictions were all chosen before any of it ran.

## The five conditions

Each is read for the side the trade was taken on, so a condition that favours a long is its mirror for a short:

| condition     | favours a long                                                  | favours a short                      | reads                             |
| ------------- | --------------------------------------------------------------- | ------------------------------------ | --------------------------------- |
| `vwap`        | the close at or above the session VWAP                          | the close at or below it             | the session VWAP                  |
| `body`        | the signal bar closed above its open                            | the signal bar closed below its open | the bar                           |
| `new_extreme` | the signal bar's high above the bar before's                    | its low below the bar before's       | two bars                          |
| `midline`     | the close above the 20-bar Bollinger midline                    | the close below it                   | ElasticBand's default band        |
| `cash_range`  | the close above the high of the cash session's first 30 minutes | the close below that range's low     | OpeningRange's default cash range |

**The VWAP side is the one already in the registry**: the side filters' rule, under which a close exactly on the VWAP favours both sides — [`nt8-fidelity.md`](../nt8-fidelity.md), "Filters relative to the trade's side". **The other four are strict**: a doji, a close on the midline and a close inside the range favour neither side, the boundary one sign multiplier asks for — [`nt8-fidelity.md`](../nt8-fidelity.md) §M26.5. `new_extreme` is the one that can favour both, on an outside bar that makes a new high and a new low at once. **A bar before its session's cash range is complete favours neither side on `cash_range`**, so the condition is false through the overnight session and the first half hour of the cash one.

**The set was chosen knowing two of its members are likely near-constant at the entry.** A 20-bar midline sits next to the 21-bar EMA a cross has just gone through, and [§M55](m55-side-count-preregistration.md) measured the VWAP side keeping 78% to 98% of EmaCrossover's signals. The run reports the share of trades each condition held on beside the count, so a near-constant one reads as near-constant rather than hiding in it.

## Read at the signal bar

EmaCrossover's entry is a market order sent at the signal bar's close and filled at the next bar's open, so **the signal bar is the last bar known when the order went in**. Every condition is read there. The fill bar's close, high and low are in the future at the fill, so reading a condition at the fill bar is lookahead — [`nt8-fidelity.md`](../nt8-fidelity.md) §M45, the rule every sizing input keeps. The earlier count read its conditions through `nqbt.annotate`, which reads the bar a log names as the entry, and that is the fill bar.

## What will be run

|                   |                                                                                                                   |
| ----------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Configuration** | EmaCrossover at its defaults, both sides                                                                          |
| **Resolution**    | 5 minutes, the earlier count's                                                                                    |
| **Roots**         | MNQ and NQ, spliced continuous                                                                                    |
| **Costs**         | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                      |
| **Windows**       | the full series, then selection on its first 60% of bars and holdout on the last 40%, each warmed on its own bars |
| **Null**          | 200 matched random entries over bars, `randomentry`'s draw, seed 0                                                |
| **Size**          | a few minutes: one run and 200 draws per root and window                                                          |

```bash
uv run tools/campaign_confluence.py --out m59.parquet
```

**The null draws the archetype's own signal count and time-of-session profile and keeps its bracket**, and a drawn bar is taken on whichever side the averages were on, as every EmaCrossover null is. Each draw's trades are counted over the same five conditions at their own signal bars, so the null's gradient is what the market gives a random entry at each count.

## What will be read

1. **The share of trades each condition held on**, per root, window and side, before anything else.
2. **The count table**, per root, window and side: at each count from 0 to 5, the trades, win rate and profit factor, the null's median trades and its median, 5th and 95th percentile profit factor over the draws that traded at that count, a draw with no losing trade there included, and the excess — the profit factor less the null's median. A count no trade reached has no rate, and a count fewer than two draws traded at has no null.
3. **The verdict reads both sides together.** The count is read as edge only where all three hold **on both roots, in both the selection and the held-out windows**: (a) the highest count holding at least 30 trades has a positive excess; (b) its profit factor sits above its null's 95th percentile; (c) its excess is larger than that of the lowest count holding at least 30 trades. Anything else is the earlier count's verdict — it sorts trades rather than adding edge.
4. **The full window and each side alone are description**, beside the verdict and never part of it.
5. **Nothing is added, dropped or re-cut after the first run.** A run that stops part-way is resumed, not redesigned.

## Predicted before the run

- **`midline` holds on more than 90% of trades and `vwap` on more than 75%**, on both roots and both sides, so most of the count's spread comes from the other three.
- **The rule's profit factor rises with the count** in the full window on both roots, as a trend-following entry's does whatever the conditions.
- **The verdict in (3) fails.** The earlier count's matched null removed most of its gradient with conditions that shared the entry's machinery; conditions that share none of it have less reason to separate the rule from a random entry.

## What this run is not

- **Not a gate on the entry.** Requiring a count before entering is `confluence_required`, which [§M55](m55-side-count-preregistration.md) runs; this counts what held on the trades the rule took.
- **Not the other archetypes**, nor other bar sizes, nor other settings of the band or the range.
- **Not the earlier count re-read at the signal bar.** Its own five conditions are not re-run here.
- **Not a port.** EmaCrossover has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#452]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/452
