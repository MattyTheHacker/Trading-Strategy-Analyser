# Findings

Every search this project has run, and what each one returned. [The register](register.md) is the full list; [by archetype](by-archetype.md) gathers one strategy's whole story; [by gate](by-gate.md) says what has survived which check.

This page is the short answer: **which strategies look best, for whom, and how much of that to believe.** Everything below is held out — measured on a window no configuration was chosen on — and every figure names the campaign that produced it, because these are dated runs against the archive as it stood rather than standing properties.

______________________________________________________________________

## Read this first

**Nothing here is a recommendation, and one number explains why.** The best cell in the registry makes its money from the forced flat at the session close: exclude those legs and its profit factor falls from 1.216 to 0.371, and **none of its 40 configurations is profitable without them** (§M28.15). The flatten is an account rule, not a strategy — so what has been found is closer to "a directional hold that the clock closes at a good time" than to the breakout the strategy is named after.

**The edge is also absent from the most recent year.** The survivor returns a profit factor of 1.008 in 2026 on its largest drawdown in the sample, against 1.14–1.26 in every prior year (§M28.9). Normalising the geometry against trailing follow-through does not restore it, and the arithmetic says why: the median 30-minute range has more than doubled since 2023 while price now travels less than one range width beyond it (§M28.10). **Trading any of this is a bet that a regime returns.**

**And the sample cannot exclude a loss.** Not one of the 40 shortlisted configurations has a bootstrap 5th percentile above a profit factor of 1.0 or above zero net; about one resample in eight of a configuration's own trades loses money (§M28.15).

With that said, the two sections below are what the evidence supports, and they differ — because a prop account and your own account are scored on different things.

______________________________________________________________________

## What was measured, and over what

|                      |                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| **Instruments**      | MNQ and NQ, back-adjusted continuous series                                                             |
| **Period**           | 2022 to 2026-08, the archive as it stands; 2026 holds 156 sessions                                      |
| **Selection window** | the first 60% of bars — where configurations are chosen                                                 |
| **Holdout**          | the remaining 40% — where every figure below is measured                                                |
| **Costs**            | $1.50 per contract on MNQ, $4.50 on NQ, plus one tick of slippage                                       |
| **Position size**    | each archetype's own default — 4 contracts, except InsideBarTrailing's 6. On NQ this decides the answer |
| **Bar size**         | 5 minutes for every cell below; resolution is the largest lever in the whole campaign                   |
| **Session rule**     | every position flat before the close, which is a prop rule and not a parameter                          |

**The four gates**, in the order a campaign runs them: **1** does it make money at all, **2** does it survive a window it was not chosen on, **3** does the entry beat a random entry taking the same number of trades, **4** does it return its own drawdown under walk-forward and resampling. One archetype has ever passed 1 to 3.

______________________________________________________________________

## For a prop-firm account

**The scoring question is different, and reading it wrong inverts the answer.** A prop account is not asking "did it survive" — nearly all accounts eventually breach. It is asking "was the *sequence* of accounts worth more than it cost", because a blown account costs its fees and not its trading losses. Survival and profitability are close to independent here, and only the second is about money (§M28.13).

### The binding constraint is position size, not the strategy

At 4 contracts a full-size NQ position leaves almost no room under a trailing threshold:

| account      | threshold | room, 4 NQ | room, 4 MNQ |
| ------------ | --------: | ---------: | ----------: |
| Apex 50K     |    $2,500 | **31 pts** |     313 pts |
| TopStep 50K  |    $2,000 | **25 pts** |     250 pts |
| Apex 150K    |    $5,000 |     63 pts |     625 pts |
| TopStep 150K |    $4,500 |     56 pts |     563 pts |

Twenty-five points is smaller than a single stop at these resolutions. **No NQ configuration survives its first account on any preset — 0 of 526** — and that is arithmetic about contract size rather than anything about an entry rule (§M28.13). The best NQ InsideBar configuration on the holdout, 668 trades at a profit factor of 1.229 and $320,236 net on paper, is dead on its first trade.

**So on a prop account at this size, trade MNQ.** NQ needs either a smaller position or a 150K account, and position size is an axis no campaign has ever swept.

### The best cell: OpeningRange, midday, on MNQ

The opening range's break, confined to the midday lull. This is the only cell in the registry to clear gates 2, 3 and 4 on both roots (§M28.14, §M28.15).

|            |                                                                                        |
| ---------- | -------------------------------------------------------------------------------------- |
| **Range**  | the first 30 minutes after the cash open — 09:30 to 10:00 ET                           |
| **Entry**  | a stop order on the break of that range, one entry per session                         |
| **When**   | `phase=MIDDAY` only, 10:30 to 14:00 ET                                                 |
| **Stop**   | `opposite` — the other extreme of the range, so the stop distance *is* the range width |
| **Target** | the shared R ladder                                                                    |
| **Bars**   | 5 minutes                                                                              |
| **Exit**   | whatever the bracket does not close is flattened before the session close              |

Replayed through `nqbt/propaccount.py` over 20 held-out configurations, attempts uncapped, four contracts — medians:

| root | preset          | attempts | passes |                net | ever passed | net > 0 |
| ---- | --------------- | -------: | -----: | -----------------: | ----------: | ------: |
| MNQ  | Apex 50K        |       31 |    4.5 |        **+17,718** |        100% |    100% |
| MNQ  | Apex 150K       |        8 |      2 |        **+21,327** |        100% |    100% |
| MNQ  | TopStep 50K     |       64 |      7 |         **+9,919** |        100% |    100% |
| MNQ  | TopStep 150K    |        7 |      2 |        **+26,982** |        100% |    100% |
| NQ   | TopStep 150K    |      165 |      2 |         **+8,797** |         90% |     80% |
| NQ   | the other three |  226–233 |      0 | −11,123 to −68,013 |          0% |      0% |

**On MNQ every configuration passes every rule set and every one is profitable after fees.** No other cell in the registry has done that. TopStep 150K is the one preset with enough room (56 points) to fund the same trades on NQ.

Its walk-forward passes on both roots with all ten folds profitable out of sample, at a pooled test profit factor of 1.279 on MNQ and 1.302 on NQ — though NQ picks the same configuration in all five folds, so what the folds test is barely a selection (§M28.15).

### The runner-up: InsideBar on MNQ

Higher median net, lower pass rate. Uncapped on Apex 50K, medians (§M28.13):

|                  |   n | attempts | passes |    fees |          net | net > 0 |
| ---------------- | --: | -------: | -----: | ------: | -----------: | ------: |
| InsideBar MNQ    |  80 |       56 |      8 | $13,417 | **+$26,585** | **95%** |
| OpeningRange MNQ |  12 |       48 |    2.5 | $11,635 | **+$14,045** |     75% |

**OpeningRange is the archetype that *funds*; InsideBar has the higher ceiling and the worse median.** On ever-passed over the full population run, OpeningRange reaches 82.2% against InsideBar's 43.8% on TopStep 150K. InsideBar also has the advantage of being **reconciled against a real NT8 trade list**, which OpeningRange is not.

### Three traps specific to prop accounts

- **`net` rewards variance and can rank a losing strategy above a winning one.** One configuration in the sample runs a profit factor of **0.932** and still nets +$3,120, because each blown account caps the loss at the fee while the wins were already withdrawn. That is real prop economics, not a modelling artefact — but read net beside the profit factor and the pass rate, never instead of them (§M28.13).
- **On NQ the result depends on an assumption the bars cannot settle.** Whether a trade's peak or its trough came first flips Apex 50K on NQ from −$38,911 to +$139,891. On MNQ it is nearly free. It is now the `excursion_order` parameter rather than a silent assumption, and `PEAK_FIRST` — the harsher reading — is the default (§M28.13).
- **TopStep trails end-of-day, so intraday peaks never reach its high-water mark.** That is why the excursion order moves the Apex rows and not the TopStep ones — a mechanism, not a coincidence.

______________________________________________________________________

## For a regular account

**Here the question is whether a strategy returns its own drawdown**, because nothing caps your loss at a fee. That is net-to-max-drawdown, and it is a far harsher test than profit factor — it correlates only +0.144 with the prop verdict, so the two sections genuinely disagree (§M28.13).

### Held out, almost nothing clears

Median net-to-drawdown across each archetype's shortlist of 20, unfiltered (§M28.9):

| archetype         |    MNQ |        NQ | returns its drawdown |
| ----------------- | -----: | --------: | -------------------- |
| InsideBar         |  0.468 | **1.022** | NQ only              |
| InsideBarTrailing |  0.328 |     0.196 | no                   |
| EmaCrossover      |  0.059 |    −0.414 | no                   |
| DeadCatBounce     | −0.292 |    −0.259 | no                   |
| PullBackAndGo     | −0.572 |    −0.527 | no                   |
| ElasticBand       | −0.583 |    −0.633 | no                   |

**One cell of thirteen clears, and six of seven archetypes return less than nothing.** A ratio below 1.0 means the strategy made less over the whole holdout than its worst peak-to-trough loss along the way.

### The two worth looking at

**InsideBar on NQ** is the only unfiltered cell that returns its own drawdown, at 1.022. It is reconciled against a real NT8 trade list, and unlike the prop case it is perfectly tradeable on a regular account at four contracts — the 31-point constraint above is a prop rule, not a market one. What holds it back is its bracket rather than its entry: its target distance is the largest axis on the holdout and almost inert on the selection window, so **the good setting exists inside the grid and selection will not hand it to you** (§M27.3). Its own largest single cost is the forced flat, which cannot be widened or switched off (§M28.12).

**InsideBarTrailing confined to midday** is the strongest gate-3 result outside OpeningRange, and it is the first time any other archetype has reached that level (§M28.16):

| root |  trades | profit factor | vs. random entry | beats null | p < 0.05 | net/drawdown |
| ---- | ------: | ------------- | ---------------- | ---------- | -------- | ------------ |
| MNQ  | 273–300 | 1.398–1.587   | +0.347 – +0.560  | 10 of 10   | 5 of 10  | 2.679–4.494  |
| NQ   | 260–276 | 1.288–1.685   | +0.214 – +0.608  | 10 of 10   | 4 of 10  | 1.618–5.170  |

**It is also the one cell that leans least on the forced flat** — 24% to 48% of legs, against 43% to 84% for every OpeningRange cell. That matters more for a regular account than a prop one, because it is the difference between an edge and an artefact of an exit rule. **It has not been put through the exclusion test**, though, so that is a reason to look rather than a result.

Note what this contradicts: read unfiltered, InsideBarTrailing sits within 0.005 of its own null, and the trailing exit was measured as giving back exactly what the fixed bracket keeps (§M27). Confined to a fifth of the session it runs well clear of it. Same archetype, different slice.

### What not to trade

**DeadCatBounce, PullBackAndGo, ElasticBand and EmaCrossover** all return less than nothing held out on both roots. DeadCatBounce is kept deliberately as the test fixture that proves the system works — its entry rule is measurably better than random at p = 0.012 while still losing money, which puts the loss in costs, hold time or bracket geometry rather than in the entry (§M7a). ElasticBand's most promising variant clears its own drawdown on four of four cells but on a median of 34 to 56 trades, which is too few to establish anything (§M26.5).

**A failed campaign parks a configuration space; it does not retire an archetype.** All seven stay registered and swept.

______________________________________________________________________

## Before you act on any of this

- **The best result's profit centre is an account rule.** Excluding the forced flat, nothing survives on either root (§M28.15). The lever that would change this is a bracket that closes the position before the session end, and that is untested.
- **2026 is flat with the largest drawdown in the sample** and the walk-forward's final fold is the weakest on both roots.
- **OpeningRange has never been checked against NinjaTrader.** It is the only archetype to pass gates 1 to 3 and **no leg of it has been diffed against a real trade list** — its stop-market entry, its measurement from the trigger rather than the fill, and its re-arming order are all unverified. `InsideBar`, `InsideBarTrailing`, `DeadCatBounce` and `PullBackAndGo` are reconciled; `OpeningRange`, `ElasticBand` and `EmaCrossover` are not.
- **The cells were chosen after looking.** Agreement across both roots is the guard used throughout, and it is not the same thing as deciding in advance. Of 200 gate-3 tests, 46 clear p = 0.05 where chance alone would give about 10 — but they sit in four cells rather than scattering, which says *where* the significance is, not that any single cell is established (§M28.16).
- **Bar size matters far more than any indicator setting**, and every archetype's median configuration loses money at one minute. Tune the bar size and the exit geometry, not periods.
- **Costs are not the problem**, and neither is slippage: doubling it to two ticks moves the opening range's held-out profit factor from 1.124 to 1.115 (§M28.9).

### Reproducing any figure here

Every number above comes out of the stored campaign databases and the campaign tools, not from anything committed to this repository:

```bash
./.venv/Scripts/python.exe tools/campaign_holdout.py      # the held-out shortlists
./.venv/Scripts/python.exe tools/campaign_propaccount.py  # the prop-account replay
./.venv/Scripts/python.exe tools/campaign_exits.py        # P&L with one exit reason removed
./.venv/Scripts/python.exe tools/campaign_null.py         # gate 3, against a matched random entry
```

`results/` is not committed. Follow the `§Mxx` pointer beside any figure to the campaign that produced it, which names the tool and the arguments it was run under.
