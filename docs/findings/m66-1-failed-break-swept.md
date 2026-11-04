---
id: M66.1
title: "M66.1 — FailedBreak swept: its levels do not beat random ones, and no cell beats a random entry on 100 trades"
archetypes: [FailedBreak]
issues: [355]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  Pre-registered before the sweep, and it is not a candidate. Unfiltered it fails gate 2 at all three levels on both roots, no cell beats a matched random entry on 100 held-out trades, and no level and bar size beats a level placed at random, so gate 4 did not run. The one striking cell, first-hour `compression=COMPRESSED` at 30 minutes, rests on 27 to 29 trades and misses the family-wise bar on MNQ. The re-break exit clears §M37's bar in 4 of 54 cells, all on yesterday's range at 15 and 30 minutes, on arms that still lose held out. Three of seven predictions held.
---

# M66.1 — FailedBreak swept: its levels do not beat random ones, and no cell beats a random entry on 100 trades ([#355])

Pre-registered in [`m66-failed-break-preregistration.md`](m66-failed-break-preregistration.md), committed before the sweep started. [§M66](m66-failed-break-spec.md) specified and built the archetype.

## In plain terms

FailedBreak waits for price to trade through an obvious level, yesterday's range, the overnight range or the first hour's, and then close back inside it. It enters at market on the next open, on the idea that stops resting beyond the level have just been forced out.

**On this data that idea isn't supported.** At the overnight and yesterday levels the median configuration roughly breaks even on the earlier 60% of bars, and the configurations picked there lose on the later 40%. The first-hour level loses on both. No configuration with 100 trades clears the bar against a random entry at any level, and none clears it against the same rule run on a level placed at random, which is the direct test of the claim that these levels are special.

**FailedBreak is not a candidate.** It stays registered and parked, `TIER1_ONLY`.

## The verdict

A candidate needs one level, bar size and stratum to pass the entry test family-wise, the level test under `kinds`, and gate 4 together. A family-wise p asks how often the best of the whole family of tests would do this well by chance. None of the three is met:

| read                                              | bar                                             | result                                        |
| ------------------------------------------------- | ----------------------------------------------- | --------------------------------------------- |
| Item 5, the entry against a random entry          | family-wise p below 0.05 on each root           | 0 of 14 cells, eight of them too thin to pass |
| Item 6, the rule against a level placed at random | family-wise p below 0.05 on each root           | 0 of 15, best p on either root 0.264          |
| Item 8, gate 4                                    | only on what passes item 5 at p ≤ 0.05, floored | not run: 0 of 14 cells passed                 |

## The reads, in the pre-registered order

### 1. `session_close_share`

The median across cells of each cell's median `session_close_share`, unfiltered on the selection window:

| target          | 1 minute |    2 |     5 |    10 |    15 |    30 |
| --------------- | -------: | ---: | ----: | ----: | ----: | ----: |
| `opposite+next` |     6.5% | 7.8% | 10.9% | 13.6% | 16.1% | 20.5% |
| `mid+opposite`  |     3.1% | 3.9% |  5.5% |  7.5% |  9.2% | 11.9% |
| `R`             |     3.1% | 3.9% |  6.2% |  8.7% | 11.7% | 19.4% |

**The far target doesn't turn this into a hold the clock closes.** No cell's median passes 25.6%. `opposite+next` is the highest in all 72 level, root, bar size and re-break cells, and the lowest is `mid+opposite` in 51 of them and `R` in 21.

### 2. Gate 1

Cells where most unfiltered configurations are profitable on the selection window, out of 12 per level and bar size (six variants on two roots):

| level        | 1 minute |   2 |   5 |  10 |  15 |  30 |
| ------------ | -------: | --: | --: | --: | --: | --: |
| `overnight`  |        2 |   0 |   5 |   9 |   8 |   8 |
| `yesterday`  |        1 |   1 |   8 |   7 |   7 |   7 |
| `first-hour` |        0 |   0 |   0 |   0 |   0 |   0 |

**63 of 216 cells clear: 19 on MNQ and 44 on NQ.** No first-hour cell clears at any bar size.

### 3. The axes

Median eta-squared on held-out profit factor across the 36 root and variant cells, unfiltered:

| axis                      | all bar sizes | within 15 minutes | within 30 minutes |
| ------------------------- | ------------: | ----------------: | ----------------: |
| bar size                  |         0.165 |                 — |                 — |
| `direction`               |         0.129 |             0.114 |             0.103 |
| `max_sweep_minutes`       |         0.083 |             0.200 |             0.210 |
| `max_signals_per_session` |         0.004 |             0.129 |             0.266 |
| `stop_offset_ticks`       |         0.004 |             0.008 |             0.005 |

Bar size or `direction` is the largest axis over all bar sizes in 31 of 36 cells, and `max_sweep_minutes` in the other 5. `stop_offset_ticks` is the smallest of the four in 27 of 36 at 15 minutes and 26 of 36 at 30.

### 4. Gate 2

**Unfiltered, the shortlist passes at no level on either root**, and it falls below the unselected median in five of the six cells:

| level        | held-out shortlist PF, MNQ / NQ | unselected median PF, MNQ / NQ |
| ------------ | ------------------------------: | -----------------------------: |
| `yesterday`  |                   0.687 / 0.780 |                  0.825 / 0.855 |
| `overnight`  |                   0.953 / 0.921 |                  0.936 / 0.954 |
| `first-hour` |                   0.943 / 0.939 |                  0.953 / 1.004 |

**11 of the 59 level and stratum cells with rows pass on both roots**, which sets item 5's families:

- `yesterday`: `htf=BELOW`, `phase=PRE_OPEN`, `phase=LONDON`, `trend=DOWN`, `regime=DIRECTIONAL`
- `overnight`: `volume=NORMAL`, `phase=AFTERNOON`
- `first-hour`: `compression=COMPRESSED`, `phase=CLOSE`, `phase=AFTERNOON`, `compression=NORMAL`

No level had more than the six strata the pre-registration allows, so none was dropped. Only first-hour `compression=COMPRESSED` returns its drawdown on both roots, at 3.19 and 4.71.

### 5. Gate 3, the entry

14 cells and 140 tests, each root's best five against a matched random entry, 200 draws, none refused:

| level        | stratum                  | held-out trades, MNQ / NQ | best PF, MNQ / NQ | tests at p ≤ 0.05, MNQ / NQ | best family-wise p, MNQ / NQ |
| ------------ | ------------------------ | ------------------------: | ----------------: | --------------------------: | ---------------------------: |
| `yesterday`  | unfiltered               |         267–393 / 218–390 |     0.685 / 1.037 |                       0 / 0 |                1.000 / 1.000 |
| `yesterday`  | `htf=BELOW`              |                   32 / 28 |     1.660 / 1.049 |                       0 / 0 |                1.000 / 1.000 |
| `yesterday`  | `phase=PRE_OPEN`         |                76 / 71–72 |     2.003 / 2.368 |                       2 / 0 |                0.786 / 0.468 |
| `yesterday`  | `phase=LONDON`           |               72–102 / 72 |     1.557 / 1.880 |                       0 / 0 |                1.000 / 0.985 |
| `yesterday`  | `trend=DOWN`             |         161–302 / 197–315 |     1.190 / 1.324 |                       0 / 0 |                1.000 / 1.000 |
| `yesterday`  | `regime=DIRECTIONAL`     |             38–47 / 38–42 |     1.514 / 1.296 |                       0 / 0 |                1.000 / 1.000 |
| `overnight`  | unfiltered               |         301–322 / 297–314 |     1.048 / 1.001 |                       0 / 0 |                1.000 / 1.000 |
| `overnight`  | `volume=NORMAL`          |         275–278 / 282–283 |     1.242 / 1.143 |                       0 / 0 |                1.000 / 1.000 |
| `overnight`  | `phase=AFTERNOON`        |             65–74 / 67–78 |     1.192 / 1.125 |                       0 / 0 |                1.000 / 1.000 |
| `first-hour` | unfiltered               |                 233 / 235 |     1.006 / 1.003 |                       0 / 0 |                1.000 / 1.000 |
| `first-hour` | `compression=COMPRESSED` |                   29 / 27 |     3.204 / 4.024 |                       5 / 5 |                0.154 / 0.020 |
| `first-hour` | `compression=NORMAL`     |           95–120 / 99–123 |     1.241 / 1.256 |                       0 / 0 |                1.000 / 1.000 |
| `first-hour` | `phase=AFTERNOON`        |             80–85 / 68–91 |     1.138 / 1.480 |                       0 / 1 |                1.000 / 0.985 |
| `first-hour` | `phase=CLOSE`            |             32–40 / 35–47 |     1.203 / 0.922 |                       0 / 0 |                1.000 / 1.000 |

**With the 100-trade floor, no cell passes, and eight of the 14 never could**, because only six cells hold a test of 100 trades on each root. All 13 tests at p ≤ 0.05 are on 27 to 91 trades. Of the 55 tests with 100 trades or more, 40 beat their null's median, and the best of those reaches only p = 0.169. Unfiltered, 7 of 30 tests are profitable, the best at a profit factor of 1.048. No test is significantly worse than random.

**The floor decides one cell, and not the verdict.** Without it, first-hour `compression=COMPRESSED` at 30 minutes passes on both roots and would have gone to gate 4. That is 1 of 14 cells, about what this bar passes by chance, and it was chosen by a read of the same holdout. It still misses the family-wise bar on MNQ, at 0.154, so it could not have made FailedBreak a candidate.

### 6. The level test

The best family-wise p per level and bar size, MNQ / NQ, over 300 tests per draw at 400 draws each, none refused. Unfiltered, 2 to 30 minutes:

| draw     | level        |     2 minutes |             5 |            10 |            15 |            30 |
| -------- | ------------ | ------------: | ------------: | ------------: | ------------: | ------------: |
| `kinds`  | `yesterday`  | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| `kinds`  | `overnight`  | 1.000 / 1.000 | 0.978 / 1.000 | 1.000 / 1.000 | 1.000 / 0.968 | 1.000 / 1.000 |
| `kinds`  | `first-hour` | 0.895 / 0.950 | 0.264 / 0.489 | 1.000 / 1.000 | 0.990 / 0.950 | 1.000 / 1.000 |
| `levels` | `yesterday`  | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 0.998 |
| `levels` | `overnight`  | 1.000 / 1.000 | 0.995 / 1.000 | 0.990 / 1.000 | 0.995 / 0.978 | 1.000 / 1.000 |
| `levels` | `first-hour` | 0.995 / 0.995 | 0.526 / 0.638 | 1.000 / 1.000 | 1.000 / 0.995 | 1.000 / 1.000 |

**No level and bar size clears either draw, so the setup's claim doesn't hold here.** The configurations do tend to sit above their null's median, 201 of 300 under `kinds` and 195 under `levels`, but only 107 of the 300 are profitable, and the best test, at 5 minutes on the first-hour range on MNQ, reaches a family-wise p of 0.264.

### 7. The re-break exit

**It earns its place in 4 of 54 cells, all on `yesterday` at 15 and 30 minutes.** The median change in profit factor, with the bar met on both roots and in both windows:

| target          | minutes | selection, MNQ / NQ | holdout, MNQ / NQ | held-out median PF with the exit, MNQ / NQ |
| --------------- | ------: | ------------------: | ----------------: | -----------------------------------------: |
| `opposite+next` |      15 |     +0.022 / +0.034 |   +0.051 / +0.043 |                              0.737 / 0.821 |
| `opposite+next` |      30 |     +0.021 / +0.022 |   +0.028 / +0.036 |                              0.749 / 0.773 |
| `mid+opposite`  |      15 |     +0.027 / +0.039 |   +0.031 / +0.027 |                              0.712 / 0.821 |
| `mid+opposite`  |      30 |     +0.016 / +0.024 |   +0.028 / +0.035 |                              0.741 / 0.775 |

**It is a gain on arms that still lose.** Every held-out median above is below 0.83. The gains are well above the 0.005 §M48 warned about, though the 64 pairs in a cell share their trades, so the sign test's p overstates the evidence. Across all 216 root, window and cell rows the exit gains significantly in 43 and costs significantly in 67.

### 8. Gate 4

**Not run.** Nothing passed item 5, and the pre-registration says gate 4 then does not run.

### 9. The prop replay

**Not run, by choice**, which the pre-registration allows: it runs last, decides nothing and can be cut without touching a verdict. It can still be run from the stored rows.

## The predictions

- **"`session_close_share` is highest under `opposite+next` and lowest under `R`, in every level, root and bar size on the selection window." Half right.** Highest in all 72, lowest in only 21, so wrong as written.
- **"No cell clears gate 1 at 1 or 2 minutes." Wrong**: 4 of 72 do, all on NQ.
- **"Over all bar sizes, within each variant, bar size or `direction` is the largest axis on every root. At 15 and at 30 minutes `stop_offset_ticks` is the smallest of the four." Wrong as written, right in the main**: 31 of 36, then 27 and 26 of 36.
- **"Item 5 fails unfiltered at all three levels, at most one of the 21 possible cells passes, which is about chance, and none clears family-wise." Right**, on 14 cells rather than 21.
- **"No level and bar size clears `kinds`, as nothing did on OpeningRange (§M60), and at most one clears `levels`." Right**: none clears either.
- **"The re-break exit clears §M37's bar in none of the 54 cells." Wrong**: 4 do.
- **"So FailedBreak is not a candidate." Right.**

## What this settles, and what it does not

**It settles this version of FailedBreak as a candidate: it is not one.** Unfiltered, its shortlists lose held out and its levels do not beat random ones.

**It does not settle first-hour `compression=COMPRESSED`.** Its results are large and its sample is 27 to 29 trades, picked on the holdout it was then tested on. Reading more into it would need a test on bars it hasn't seen.

**The level test is unfiltered only**, so a level that carries something in one stratum would read as a fail. **The holdout is not fresh**, and §M28.9 finds its most recent year different from the rest, which may be part of why gate 1's passes do not survive. **Nothing here touches NinjaTrader**, and the rest of §M66's "Not in this version" stays unmeasured.

## How it was run

- **Where.** One 16-core Azure spot VM on 3 November 2026, at `c6d72df`, with no evictions. All 24 sweep calls ran on the same bars as the October 2026 re-sweep. The commands are the pre-registration's at 16 workers, apart from the scripted reads below and item 9.
- **Time.** The sweep took 7.5 minutes, at a peak of 8 GB, and the reads to item 7 took 12, with their memory not measured. **The pre-registration's estimate was about ten times too high**: it scaled EmaCrossover's rates to 40 minutes on 32 cores and about 8 hours on two, so an hour or more on 16. FailedBreak's own cost was 29 ms per combination per worker at 1 minute and 2 ms at 30.
- **The rows are all there.** The database holds all 635,904 combinations from 24 sweep calls.
- **The re-runs reproduce.** `campaign_null.py` stops on a configuration that misses its stored trades and net, and all 740 tests ran.
- **Scripted reads.** Items 3, 4 and 7 called the tools' own functions from a script so that their tables could be saved, and the counts above were read from the saved tables. Nothing beyond the pre-registered reads was simulated.

[#355]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/355
