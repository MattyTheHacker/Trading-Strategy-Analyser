---
title: "M60 — pre-registration: a null over the level's kind"
archetypes: [OpeningRange]
issues: [439]
gates: [3]
outcome: spec
verdict: >-
  Written and committed before the run: OpeningRange's unfiltered shortlist placed against a third null, which keeps each session's own range width and the price its window closed at and places the bracket at random around that price, beside §M28.2's null over which session's range is traded, at 5, 10 and 15 minutes on both roots, the top ten ranked on the selection window and tested on the holdout, 400 draws; a bar size clears where, on each root, a configuration reaches a family-wise p below 0.05 against the new draw over its family of 60.
---

# M60 — pre-registration: a null over the level's kind ([#439])

[§M28.2](m28-2-deferral-list.md) gave OpeningRange's unfiltered breakout the null it never had: permute which session's range is traded, holding the bars and the signal fixed. It named what that null cannot ask — "a null over *which* range is traded, not over whether a range is the right kind of level at all" — and deferred **a null over the level's kind rather than its identity**. This is that null.

**What has changed since §M28.2**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: the null. The archetype, its grid and the protocol are what earlier gate-3 runs used; the rows are the planned re-sweep's.

**This file was written and committed before the run.** The draw, the cells, the bar and the predictions were all chosen before any of it ran. The size below comes from single timings of both draws on MNQ's held-out bars, and no statistic from those timings was read.

## The draw

Every level draw holds the bars, the costs, the bracket rules and the armed flags, and so the signal; only the levels each session trades move.

| draw                     | each session trades                                                                        | holds                         | moves                                               |
| ------------------------ | ------------------------------------------------------------------------------------------ | ----------------------------- | --------------------------------------------------- |
| `levels`, §M28.2's       | another session's range, carried as two offsets from the price its window closed at        | the price                     | which range: its width and where the price sits     |
| `kinds`, this campaign's | a bracket as wide as its own range, placed at random around the price its window closed at | the price and the range width | where the edges are, so not where the market turned |

The price its window closed at is the close of the first bar that may read the range, as in §M28.2. **The low is placed a whole number of ticks below that price, drawn uniformly from none to the width in ticks, and the high one width above the low.** Four things follow:

- **The bracket always holds that price**, as the real range does, and either edge may sit on it.
- **Both levels are on the tick grid**, so every order rests at a price the market quotes.
- **No bracket distance changes.** The opposite-extreme and fraction stops and the width target are measured off the width, and the ATR stop never read the range.
- **One placement in the width in ticks plus one is the real one**, so a range a hundred ticks wide gets its own levels back about once in a hundred sessions. **The draw is refused where the sessions would get their own levels back more than one time in twenty on average**, which is `MIN_DONOR_SESSIONS`'s rule for the level draw read for this one, and where no session has a range at all.

**Read together, the two draws say where an edge comes from:**

| beats `levels` | beats `kinds` | reading                                                                                               |
| -------------- | ------------- | ----------------------------------------------------------------------------------------------------- |
| yes            | yes           | the levels the market printed carry something a bracket of the same width does not                    |
| yes            | no            | what separates the trade from another session's range is the session's width, not its edges           |
| no             | yes           | how a real range sits around the price matters, which donors keep, and which session's it is does not |
| no             | no            | neither the range nor its width separates the trade from the bracket and the time of day              |

### The alternatives not taken

- **Another session's width, centred on the price.** It moves the width and the placement at once, so it cannot say which one mattered.
- **A volatility band**, the price plus or minus a multiple of the ATR scaled to the median range width. That is another kind of level, but its width also differs from the session's, so it mixes the two questions.
- **The real positions of the price inside its range, shuffled across sessions**, at each session's own width. That keeps how real ranges sit around the price, which is part of what a range is. A uniform placement keeps none of it.

## What will be run

|                 |                                                                                                                                                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Archetype**   | OpeningRange's own campaign variants, §M28.1's grid, every range window stored at each bar size (`--campaign-only`)                                                                                                          |
| **Stratum**     | `unfiltered` alone: the configuration with no stratum choice in it, which §M28.2's draw was built for                                                                                                                        |
| **Resolutions** | 5, 10 and 15 minutes                                                                                                                                                                                                         |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                                                               |
| **Costs**       | each stored row's own: $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                                          |
| **Shortlist**   | the top ten per root and bar size by selection-window profit factor, measured on the holdout: [§M54](m54-family-wise-null-preregistration.md)'s protocol                                                                     |
| **Draws**       | 400 per configuration under `kinds`, and again under `levels`, from seed 0 in both, so draw *j* of one configuration is seeded the same under each                                                                           |
| **Rows**        | the ones the planned re-sweep of every stored campaign writes, as §M54's are                                                                                                                                                 |
| **Size**        | 120 tests and 48,000 simulations of the held-out window. Single timings at the defaults put a draw at about 25 ms at 5 minutes and 9 ms at 15, about 12 core-minutes in all: under half an hour on two workers, read as ±30% |

Once per bar size and draw, then one family read per draw:

```bash
uv run tools/campaign_null.py --strategy OpeningRange --root MNQ NQ --stratum unfiltered \
    --campaign-only --resolution <5|10|15> --window selection --test-window holdout \
    --top 10 --iterations 400 --draw <kinds|levels> --out <its table>
uv run tools/campaign_null.py --family-of <the three kinds tables>
uv run tools/campaign_null.py --family-of <the three levels tables>
```

## What will be read

1. **The observation is a reproduction first.** `campaign_null.py` checks each configuration against its stored holdout row, the bars, the trade count and the net P&L, before any draw. A configuration that does not reproduce is a defect to explain, and nothing below is read until it is.
2. **The verdict reads the kind draw family-wise**, over its 60 tests: 2 roots × 3 bar sizes × 10 configurations. **A bar size clears where, on each root, at least one of its ten configurations reaches a family-wise p below 0.05**, §M54's bar. The level's kind is read as worth something only if at least one bar size clears.
3. **The level draw is read the same way, beside it**, on the same shortlist and seeds, so each bar size can be named by the table above. It re-reads §M28.2's null on the current rows and tests nothing new. `--family-of` refuses a family holding one archetype under both draws, so the two cannot be read as one by mistake.
4. **Per test, as description**: the profit factor, each null's median, the excess over each and its per-test p, and the observed and null median trade counts. The two excesses are set side by side, configuration by configuration.
5. **Nothing is added, dropped or re-cut after the first run.** A run that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The kind null makes more than the level null.** Its median profit factor is above the level null's in at least five of the six root × bar-size cells, taking each cell's median configuration, because it keeps the session's own width, which the level draw throws away.
- **The observation still beats the kind null on sign.** The excess over it is positive in the median configuration of at least five of the six cells.
- **No bar size clears the kind null at the bar.** §M28.2's level draw reached p < 0.05 in one cell of six, and a null that keeps the width sits closer to the observation than one that does not.

## What this run is not

- **Not the fade, the retest or the rejection**, which are §M28.2's and later variant sets, and not any stratum but `unfiltered`.
- **Not a replacement for the level draw.** The two draws ask different questions, and the reading needs both.
- **Not §M28.2's figures re-quoted.** Those were measured on the archive before §M44 and on a different shortlist.
- **Not a change to the simulation.** The draw moves the levels a session trades and touches nothing under `nqbt/sim/`.
- **Not a port.** OpeningRange has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
