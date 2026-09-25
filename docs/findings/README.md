# Findings

Every search this project has run, and what each one returned. [The register](register.md) is the full list; [by archetype](by-archetype.md) gathers one strategy's whole story; [by gate](by-gate.md) says what has survived which check.

This page is the short answer: **which strategies look best, for whom, and how much of that to believe.** Everything below is held out — measured on a window no configuration was chosen on — and every figure names the campaign that produced it, because these are dated runs against the archive as it stood rather than standing properties.

______________________________________________________________________

## Read this first

**Nothing here is a recommendation, and one number explains why.** The cell that led this register until §M43 makes its money from the forced flat at the session close: exclude those legs and its profit factor falls from 1.216 to 0.371, and **none of its 40 configurations is profitable without them** (§M28.15). The flatten is an account rule, not a strategy — so what has been found is closer to "a directional hold that the clock closes at a good time" than to the breakout the strategy is named after.

**One cell looked like it had broken that, and a second measurement says otherwise.** InsideBarTrailing confined to midday was the first in the registry where the exclusion left anything standing — nine of twenty configurations profitable without their session-close legs (§M42) — and it is on that, rather than on the account objectives it was ranked by, that **§M43 chose it as the cell to port**. **§M44 re-ran the same read on about 30% more history and found one survivor of twenty, and none clearing both gate-4 thresholds.** So the exclusion behaves here as it does everywhere else, and §M42's reading was the most window-dependent of the three it took.

**That does not unseat the cell**, for the reason [#344] gives: the exclusion is a decomposition rather than a counterfactual, a forced-flat-dependent result is not discounted, and the flatten is mandatory live so the whole book is the book that trades. What survives on both roots and on both series is the part that matters — the holdout, the matched null at p = 0.05, a bootstrap 5th percentile above a profit factor of 1.0 on every MNQ configuration, and a five-fold walk-forward (§M42, §M44).

**OpeningRange's edge is also absent from the most recent year.** Its survivor returns a profit factor of 1.008 in 2026 on its largest drawdown in the sample, against 1.14–1.26 in every prior year (§M28.9). Normalising the geometry against trailing follow-through does not restore it, and the arithmetic says why: the median 30-minute range has more than doubled since 2023 while price now travels less than one range width beyond it (§M28.10). **Trading any of this is a bet that a regime returns.**

**And OpeningRange's midday sample cannot exclude a loss.** Not one of its 40 shortlisted configurations has a bootstrap 5th percentile above a profit factor of 1.0 or above zero net, and about one resample in eight of a configuration's own trades loses money (§M28.15) — the floor InsideBarTrailing's midday cell clears on every MNQ configuration.

**Most of what a tuned configuration is worth turns out to be selection rather than strategy, and a second market now says so.** Running each archetype's top 200 unchanged on ES, MES, GC and MGC — markets nothing here was fitted on — costs far less than the move from the selection window to the holdout already cost: the selection step takes 0.24 to 0.54 of profit factor and the instrument step takes 0.00 to 0.29, and for the two inside-bar archetypes it takes nothing at all. Nothing clears a median profit factor of 1.1 on any new root (§ "Do the shortlists travel?"). A 5/10/15 campaign has since been swept on all four, and the one candidate it produced — EmaCrossover on gold — was pre-registered and then falsified: 1 of 16 gold pairs clears the matched null against the 4 required, and it clears 3 of 6 S&P pairs against gold's 1 of 16 (§ "The gold strata test: EmaCrossover's edge does not survive stratification").

With that said, the two sections below are what the evidence supports, and they differ — because a prop account and your own account are scored on different things.

______________________________________________________________________

## What was measured, and over what

|                      |                                                                                                                |
| -------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Instruments**      | MNQ and NQ, raw spliced continuous series — the prices that traded, so a round-number rule runs                |
| **Period**           | 2022 to 2026-08 for every campaign up to §M43; **2020-10 to 2026-09 from §M44**, which re-swept it             |
| **Selection window** | the first 60% of bars — where configurations are chosen                                                        |
| **Holdout**          | the remaining 40% — where every figure below is measured                                                       |
| **Costs**            | $1.50 per contract on MNQ, $4.50 on NQ, plus one tick of slippage                                              |
| **Position size**    | each archetype's own default — 4 contracts, except InsideBarTrailing's 6. On NQ this decides the answer        |
| **Bar size**         | 5 minutes for every cell below unless it says otherwise; resolution is the largest lever in the whole campaign |
| **Session rule**     | every position flat before the close, which is a prop rule and not a parameter                                 |

**The four gates**, in the order a campaign runs them: **1** does it make money at all, **2** does it survive a window it was not chosen on, **3** does the entry beat a random entry taking the same number of trades, **4** does it return its own drawdown under walk-forward and resampling. OpeningRange was the first archetype to pass 1 to 3 (§M28.1); InsideBarTrailing has since done it inside its midday cell (§M28.16, reproduced by §M44), and SqueezeBreakout on one short entry measured on about 31 held-out trades (§M19.3).

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

**So on a prop account at this size, trade MNQ.** NQ needs either a smaller position or a 150K account, and position size is an axis no campaign has ever swept — [§M45](m45-ibt-sizing-preregistration.md) pre-registers the first that does, on InsideBarTrailing, and has not run yet.

### The best cell: InsideBarTrailing, midday, on MNQ

The break of an inside bar, confined to the midday lull, with a trailing runner. **This is what [#344]'s Phase 0 chose to port** (§M43), and it displaced the OpeningRange cell below on evidence rather than on the tie-breaker that was expected to decide it.

|            |                                                                                              |
| ---------- | -------------------------------------------------------------------------------------------- |
| **Entry**  | the break of an inside bar, whichever way it breaks                                          |
| **When**   | `phase=MIDDAY` only, 10:30 to 14:00 ET                                                       |
| **Stop**   | 10 × ATR, with the trailing half following the high-water mark at 5 × the inside bar's range |
| **Target** | one R, taken on 60% of the position; the rest runs on the trailing stop                      |
| **Bars**   | 5 minutes                                                                                    |
| **Size**   | 6 contracts, this archetype's default                                                        |
| **Exit**   | whatever the bracket does not close is flattened before the session close                    |

Replayed through `nqbt/propaccount.py` over 20 held-out configurations, attempts uncapped, six contracts — median net, beside the cell it displaced at four contracts (§M43):

| preset                     | InsideBarTrailing | OpeningRange |
| -------------------------- | ----------------: | -----------: |
| Apex 50K                   |       **+30,045** |      +17,718 |
| Apex 150K                  |       **+24,396** |      +21,327 |
| TopStep 50K                |       **+14,872** |       +9,919 |
| TopStep 150K               |           +12,208 |  **+26,982** |
| TakeProfitTrader 25K Test  |       **+31,564** |      +22,085 |
| TakeProfitTrader 50K Test  |       **+29,223** |      +17,601 |
| TakeProfitTrader 150K Test |       **+21,856** |      +19,945 |

**It nets more on nine of the ten presets §M43 ran**, seven of them in the table above, at a median held-out profit factor of 1.49 against 1.22, and every configuration of both is funded on every preset but one. **Ranked on what a prop account is actually scored on, the two are level** — 4–3 to it on time to the first payout across the seven MNQ presets and 4–3 against it on the cost of a pass — so what decides it is what those objectives have to be read beside: profit factor in all fourteen cells, net in eleven, and a session-close share of 0.09–0.49 against 0.65–0.66 (§M43).

**§M44 re-ran that comparison on the re-swept archive and the objectives are no longer level: 12 of the 14 go to it**, 7 of 7 on time to the first payout and 5 of 7 on the cost of a pass, at 13–42 sessions to payout against 19.5–232. Both cells still pass and pay out on every preset, so the margin is how long the account takes to be worth anything rather than whether it survives — and the choice needs fewer tiebreakers than it did.

**The configuration to port**, chosen among the ten §M42 put through gate 4, restricted to those that survive the exclusion, and ranked by `days_to_payout` — **note that the restriction it was chosen under no longer selects the same way**, because §M44 finds one of ten surviving the exclusion rather than five, so this parameter set is §M43's pick on §M43's archive: `ema_period` 44, `fast_sma_period` 20, `slow_sma_period` 125, `error_margin` 0.05, `atr_length` 14, `atr_multiplier` 10.0, `tp_multiplier` 1.0, `partial_take_profit_percentage` 0.6, `trailing_stop_multiplier` 5.0, 6 contracts, 5-minute bars, chosen for TakeProfitTrader 25K Test. Held out it takes 300 trades at a profit factor of 1.553 and a net-to-drawdown of 4.143, and **+$13,507 at 1.465 with its session-close legs removed** — the best residual in the registry. §M43 has every parameter and the per-preset figures.

**Two warnings travel with it.** The choice rule was applied to a table that had already been read, so "it leads `days_to_payout` among the survivors" is a description rather than a result. And inside this cell the two objectives barely agree with each other (rho −0.085 over ten configurations) and point opposite ways at the exclusion — a cheap pass goes *against* a book that stands up without the forced flat, which is the one reading that would have picked the wrong configuration.

### The one it displaces: OpeningRange, midday, on MNQ

The opening range's break, confined to the midday lull. It clears gates 2 and 3 on both roots (§M28.14), and **gate 4 is mixed** (§M28.15): the walk-forward and the permutation test pass, but not one of its 40 configurations has a bootstrap 5th percentile above a profit factor of 1.0 or above zero net — and none of the 40 is profitable without its session-close legs.

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

**A second cut of the same archetype has the stronger gate-3 result and the worse case for trading.** Confined to a calibrated directional regime at a lookback of 20 rather than to the midday lull, OpeningRange clears p = 0.05 on **all ten configurations of both roots** — the only cell in the registry to do so (§M31). Gate 4 then split (§M31.1): the walk-forward passes on both roots at a pooled test profit factor of 1.439 and 1.459, and every MNQ preset funds, but only one of its twenty configurations has a bootstrap 5th percentile above a profit factor of 1.0 and **not one is profitable without its session-close legs** — 1.43 to 0.24 on MNQ, 1.46 to 0.24 on NQ — and its prop-account net runs +772 to +5,088 against the midday cell's +9,919 to +26,982. **The cell that best beats a random entry is the one that leans hardest on the account rule**, so the midday cell above remains the better candidate. **That gate-3 result belongs to the opposite-extreme stop** (§M38): it holds at every range window and under both targets, and under the ATR stop the entry beats its null on all twenty configurations and clears p = 0.05 on none.

### The other one worth knowing: InsideBar on MNQ

Higher median net, lower pass rate. Uncapped on Apex 50K, medians (§M28.13):

|                  |   n | attempts | passes |    fees |          net | net > 0 |
| ---------------- | --: | -------: | -----: | ------: | -----------: | ------: |
| InsideBar MNQ    |  80 |       56 |      8 | $13,417 | **+$26,585** | **95%** |
| OpeningRange MNQ |  12 |       48 |    2.5 | $11,635 | **+$14,045** |     75% |

**OpeningRange is the archetype that *funds*; InsideBar has the higher ceiling and the worse median.** On ever-passed over the full population run, OpeningRange reaches 82.2% against InsideBar's 43.8% on TopStep 150K. InsideBar also has the advantage of being **reconciled against a real NT8 trade list**, which OpeningRange is not.

### If you are optimising for something other than net

**Everything above ranks configurations by profit factor and reads them for net. A prop account can be scored on other things**, and §M40 ranks the selection window by four of them directly — the pass rate, what a funded account costs in fees, how long until the first payout, and how long a funded account lasts — then reads each shortlist on the holdout beside the profit-factor one.

**All four orderings transfer, and none of the levels do.** Each objective beats the profit-factor shortlist at its own objective held out, on sign tests clearing 0.05 in all four cases; held out, a funded account then lasts 12 trading days where the selection window promised 138. **Pick a configuration with these; do not quote the number it was picked at.**

| if you want                     | rank by          | what it buys held out                                                                                                 | what it costs                     |
| ------------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **to be paid soonest**          | `days_to_payout` | +0.208 on the share of shortlists ever funded, and it is **the only one that also raises net**, by a median of $1,862 | nothing measurable                |
| **the cheapest funded account** | `fees_per_pass`  | +0.214 on the same share, and $283 off the cost of a pass                                                             | net unchanged (p = 0.07)          |
| **the highest pass rate**       | `pass_rate`      | +0.061 on that share                                                                                                  | net unchanged                     |
| **the longest funded account**  | `funded_days`    | +0.051 on that share, the weakest of the four                                                                         | **loses net more often than not** |

Paired by cell and preset on MNQ (§M40). **The largest part of the gain is that the account gets funded at all**: where the shortlists differ, 42 pairs have a cost per pass under the objective ranking and none under the control, against 1 the other way.

**The cells below were chosen after the holdout was read.** They are where each objective landed best, not a recommendation, and every figure is a median over that preset's own shortlist of 20.

#### Cheapest to get funded, and highest pass rate: InsideBarTrailing, midday, on MNQ

**One cell wins both**, and it is the cell §M28.16 found to be the strongest gate-3 result outside OpeningRange:

|            |                                                                                                       |
| ---------- | ----------------------------------------------------------------------------------------------------- |
| **Entry**  | the break of an inside bar, whichever way it breaks                                                   |
| **When**   | `phase=MIDDAY` only, 10:30 to 14:00 ET                                                                |
| **Stop**   | 10 × ATR, with the trailing half following the high-water mark at 2, 5 or 10 × the inside bar's range |
| **Target** | one R, taken on 30% to 80% of the position; the rest runs on the trailing stop                        |
| **Bars**   | 5 minutes                                                                                             |
| **Size**   | 6 contracts, this archetype's default                                                                 |
| **Swept**  | `ema_period` 11/22/44, `fast_sma_period` 20/35/50, `atr_length` 3/14, `error_margin` 0.05/0.1         |

Ranked by `fees_per_pass`, MNQ — `cost` is what one funded account cost in fees:

| preset                     |     cost | attempts | passes |   fees |          net | ever passed | net > 0 |
| -------------------------- | -------: | -------: | -----: | -----: | -----------: | ----------: | ------: |
| TakeProfitTrader 25K Test  | **$444** |     44.5 |     16 | $7,205 | **+$24,917** |        100% |    100% |
| TakeProfitTrader 50K Test  |     $617 |     29.5 |     10 | $5,955 | **+$29,038** |        100% |    100% |
| TopStep 50K                |     $800 |     78.5 |      7 | $5,600 | **+$18,211** |        100% |    100% |
| Apex 50K                   |   $1,233 |       23 |    6.5 | $7,943 | **+$22,652** |        100% |    100% |
| TakeProfitTrader 150K Test |   $2,722 |        4 |      2 | $5,660 | **+$23,143** |        100% |    100% |
| TopStep 150K               |   $3,129 |       18 |      2 | $6,109 |  **+$9,860** |        100% |    100% |
| Apex 150K                  |   $8,149 |        3 |      1 | $7,852 | **+$25,538** |         75% |     65% |

**Every preset's median configuration is profitable after fees**, at held-out profit factors of 1.30 to 1.49 on 278 to 315 trades, and six of the seven fund all twenty — Apex 150K funds 15 of 20, with the least room of any preset at this size. Ranked by `pass_rate` instead, the same cell returns 0.10 to 0.54 passes per attempt across those presets, at nets of +$12,436 to +$28,254.

**On NQ it splits exactly where the room does.** The three TakeProfitTrader presets and TopStep 150K fund it — TakeProfitTrader 150K Test at $1,738 a pass and +$202,019 — while Apex 50K and TopStep 50K never pass at all, which is §M28.13's 25-to-31-point arithmetic rather than anything about the entry.

**The 150K presets are cheaper per pass on `InsideBar` unfiltered**: $1,560 on TakeProfitTrader 150K Test and $1,788 on TopStep 150K, at +$40,962 and +$37,971, over 1,600 to 1,900 trades instead of 300. At least 80% of its shortlist gets funded on every preset on both roots, which no other cell here manages, but at a profit factor of 1.06 to 1.09 rather than 1.30 to 1.49 — and its NQ TopStep 50K median net is −$7,908.

#### Paid soonest: InsideBarTrailing, unfiltered, on MNQ

The same archetype with the midday filter taken off, which is what buys the trade count:

|           |                                                                                 |
| --------- | ------------------------------------------------------------------------------- |
| **Entry** | as above, in every session phase                                                |
| **Bars**  | mixed — 39% of the shortlist at 5 minutes, 27% at 10, 18% at 15, 16% at 1 and 2 |
| **Size**  | 6 contracts                                                                     |

Ranked by `days_to_payout`, MNQ — `days` is trading days from opening the first account to the first withdrawal:

| preset                     | days | attempts | passes |    fees |           net | ever passed | net > 0 | profit factor |
| -------------------------- | ---: | -------: | -----: | ------: | ------------: | ----------: | ------: | ------------: |
| TakeProfitTrader 25K Test  |   21 |      133 |     20 | $15,865 |  **+$68,666** |        100% |    100% |         1.034 |
| TakeProfitTrader 50K Test  |   22 |    103.5 |     19 | $14,283 |  **+$48,002** |        100% |    100% |         0.991 |
| TopStep 50K                |   24 |    174.5 |   11.5 | $11,423 |  **+$17,736** |        100% |     90% |         1.007 |
| Apex 50K                   | 35.5 |     98.5 |    9.5 | $20,756 |  **+$20,515** |        100% |     95% |         0.990 |
| TakeProfitTrader 150K Test | 51.5 |     54.5 |      8 | $17,046 |  **+$49,293** |        100% |    100% |         0.987 |
| TopStep 150K               |   53 |       80 |      8 | $16,167 |  **+$54,332** |        100% |    100% |         0.951 |
| Apex 150K                  |  113 |       47 |      4 | $20,438 |  **+$20,041** |        100% |     95% |         0.946 |
| NQ, TakeProfitTrader 150K  |   27 |    275.5 |     17 | $64,462 | **+$403,064** |        100% |    100% |         0.932 |

**Read the last column before anything else.** This is the fastest route to a first withdrawal in the registry and its profit factor is **below 1.0 on five of the seven presets**. It is §M28.13's reset economics in their purest form: the sequence withdraws faster than the accounts die, so it makes money as a business while losing it as a strategy.

#### Longest funded account: ElasticBand, unfiltered — and it is the one to avoid

|           |                                                                           |
| --------- | ------------------------------------------------------------------------- |
| **Entry** | a fade of a stretch past a band, over various sources, periods and shapes |
| **Bars**  | mixed, 42% of the shortlist at 5 minutes                                  |
| **Size**  | 4 contracts                                                               |

Ranked by `funded_days`, MNQ — `days` is how long a funded account survived:

| preset                    |  days | attempts | passes |   fees |         net | ever passed | net > 0 |
| ------------------------- | ----: | -------: | -----: | -----: | ----------: | ----------: | ------: |
| TakeProfitTrader 150K PRO |   135 |        3 |      2 |   $390 |     +$1,116 |        100% |     65% |
| TakeProfitTrader 50K PRO  |    96 |        4 |      2 |   $520 |       +$716 |        100% |     55% |
| TopStep 50K               |    61 |        4 |      1 | $1,472 |       +$424 |         80% |     65% |
| Apex 50K                  |    60 |        4 |      1 | $4,556 |       +$962 |         70% |     60% |
| TakeProfitTrader 25K PRO  | 30.25 |        6 |      3 |   $780 |        +$20 |         95% |     50% |
| Apex 150K                 |     0 |      2.5 |      0 | $7,639 | **−$7,425** |         25% |     25% |
| TopStep 150K              |     0 |        2 |      0 | $3,725 | **−$3,725** |         35% |     35% |

**Two presets never get funded at all and lose their fees**, the surviving lives are worth $20 to $1,116, and the longest of them is mostly the window ending rather than the account surviving — 95% of the TakeProfitTrader 150K PRO figure is cut off at the end of the holdout. On NQ every preset is negative. This is the objective the evidence argues against using.

#### The trap in the pass rate

**A pass rate of 1.000 is one attempt.** Ranked by `pass_rate`, DeadCatBounce's unfiltered cell reaches exactly that on three MNQ presets — by opening **one account on 82 to 93 trades in the whole holdout** and never breaching it. On the four presets where that single account does not pass, the same configurations return a pass rate of 0.0 and lose their fees: −$3,841 on Apex 50K, −$6,980 on Apex 150K, −$5,076 on TakeProfitTrader 150K Test. Net is negative on five of the seven.

Read `attempts` beside a pass rate and `censored_share` beside a funded life; the tool reports both. **None of this changes which strategy is best**, since the pool it ranks is the same stored registry. It changes which configurations inside one you would pick, and on what basis.

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

**It is also the one cell that leans least on the forced flat** — 24% to 48% of legs, against 43% to 84% for every OpeningRange cell. That matters more for a regular account than a prop one, because it is the difference between an edge and an artefact of an exit rule.

**The exclusion test has now been run on it, and it is the first cell in the registry to survive any of it** (§M42):

| root | median PF | without the flatten | profitable without it | bootstrap p05 PF above 1.0 | walk-forward         |
| ---- | --------- | ------------------- | --------------------- | -------------------------- | -------------------- |
| MNQ  | 1.482     | 0.975               | **5 of 10**           | **10 of 10**               | passes, pooled 1.439 |
| NQ   | 1.316     | 0.939               | **4 of 10**           | 4 of 10                    | passes, pooled 1.451 |

Every earlier run of that read returned zero — 0 of 40 on the OpeningRange midday cell and 0 of 20 on the gate-3 survivor — and only one configuration anywhere had previously put a bootstrap floor above a profit factor of 1.0, one of §M31.1's twenty. **On each root one bracket axis separates every survivor from every failure**: on MNQ taking 60% off at one R rather than 50%, on NQ trailing at 5× the inside bar's range rather than 10×. Both were found by reading a table of ten rows, so they are what to pre-register next rather than settings to trade. **NQ's half of this is on a holdout that moved** — the archive was extended after the campaign was swept, and cutting it back recovers MNQ's window exactly and NQ's not at all (§M41, §M42).

**One configuration of it is now named in full** — §M43 picked it for the prop account and it is the same cell, so a regular account reading this section can take the parameter set from there rather than the range.

Note what this contradicts: read unfiltered, InsideBarTrailing sits within 0.005 of its own null, and the trailing exit was measured as giving back exactly what the fixed bracket keeps (§M27). Confined to a fifth of the session it runs well clear of it. Same archetype, different slice.

### What not to trade

**DeadCatBounce, PullBackAndGo, ElasticBand and EmaCrossover** all return less than nothing held out on both roots. DeadCatBounce is kept deliberately as the test fixture that proves the system works — its entry rule is measurably better than random at p = 0.012 while still losing money, which puts the loss in costs, hold time or bracket geometry rather than in the entry (§M7a). ElasticBand's most promising variant clears its own drawdown on four of four cells but on a median of 34 to 56 trades, which is too few to establish anything (§M26.5).

**A failed campaign parks a configuration space; it does not retire an archetype.** All nine stay registered and swept.

______________________________________________________________________

## Before you act on any of this

- **The best result's profit centre is an account rule.** Excluding the forced flat, nothing survives on either root — §M28.15, §M31.1 on the gate-3 survivor, and **§M44, which re-ran §M42's exclusion on about 30% more history and found one survivor of twenty where §M42 found nine**. That makes §M42 the exception rather than the rule it looked like, and the lever below is named everywhere and found nowhere. **This is a decomposition and not a disqualification** — [#344] settled that a forced-flat-dependent result is not discounted, because a leg the clock closed is a leg the stop did not take, the flatten is mandatory live, and gate 3's matched entry is flattened identically so its p-values are already net of it. **The obvious lever has now been tried and does not work**: an unconditional cap on how long a trade may last is a cost at every rung that binds, inside the stratum as well as unfiltered, and the selection window picks a paying rung nowhere (§M29, §M31.1). What remains untested is a *conditional* early exit — one that closes losing positions, or tightens as the session ages — which is a different object from a bar count. **The related worry that the live flatten happens at a different moment from the backtested one turns out not to exist at these bar sizes**: at 5 minutes the 180 seconds the C# sets picks exactly the same bars as the 30 the simulation runs at, and a whole 15-minute bar earlier is worth at most 0.040 of profit factor, with the sign belonging to the archetype (§M41).
- **2026 is flat with the largest drawdown in the sample** and the walk-forward's final fold is the weakest on both roots.
- **OpeningRange has never been checked against NinjaTrader.** It was the first archetype to pass gates 1 to 3 and **no leg of it has been diffed against a real trade list** — its stop-market entry, its measurement from the trigger rather than the fill, and its re-arming order are all unverified. `InsideBar`, `InsideBarTrailing`, `DeadCatBounce` and `PullBackAndGo` are reconciled; `OpeningRange`, `ElasticBand`, `EmaCrossover`, `EmaPullback` and `SqueezeBreakout` are not.
- **The cells were chosen after looking, and one family since was not.** Agreement across both roots is the guard used throughout, and it is not the same thing as deciding in advance. Of 200 gate-3 tests, 46 clear p = 0.05 where chance alone would give about 10 — but they sit in four cells rather than scattering, which says *where* the significance is, not that any single cell is established (§M28.16). **§M44 re-ran that family on a longer series and got 47, with three of the four cells still clearing on both roots** — so the arrangement is the part that reproduces. §M31 is the first family written down before its run: 180 tests, 40 clear, concentrated in three cells — though its nine cells were still picked from 267 that had been scored.
- **Bar size matters far more than any indicator setting**, and every archetype's median configuration loses money at one minute. Tune the bar size and the exit geometry, not periods.
- **Costs are not the problem**, and neither is slippage: doubling it to two ticks moves the opening range's held-out profit factor from 1.124 to 1.115 (§M28.9).

### Reproducing any figure here

Every number above comes out of the stored campaign databases and the campaign tools, not from anything committed to this repository:

```bash
./.venv/Scripts/python.exe tools/campaign_holdout.py      # the held-out shortlists
./.venv/Scripts/python.exe tools/campaign_propaccount.py  # the prop-account replay
./.venv/Scripts/python.exe tools/campaign_exits.py        # P&L with one exit reason removed
./.venv/Scripts/python.exe tools/campaign_null.py         # gate 3, against a matched random entry
./.venv/Scripts/python.exe tools/campaign_propobjectives.py  # shortlists ranked by an account objective
./.venv/Scripts/python.exe tools/campaign_flatten.py      # the same cell at several flatten cutoffs
```

**The campaign databases are not committed, and two sets of them exist.** Figures from §M44 onwards come out of the current set; everything earlier comes out of the set moved aside before that re-sweep, because §M44 replaced the archive those rows were swept on. The machine holding them carries a local README naming both. Follow the `§Mxx` pointer beside any figure to the campaign that produced it, which names the tool and the arguments it was run under — and note that the NQ half of the older set cannot be re-derived at all ([#360]).

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#360]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/360
