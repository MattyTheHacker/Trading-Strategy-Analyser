---
id: M40
title: "M40 — Prop accounts ranked by what they are scored on rather than by profit factor"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [326]
gates: []
outcome: mixed
verdict: >-
  Ranking the selection window by pass rate, fees per pass, time to the first payout or funded life beats ranking by profit factor at each objective held out, on sign tests clearing 0.05 in all four; the largest part of the gain is that the account gets funded at all, 42 pairs to 1 for fees per pass. Only time to the first payout also improves net (+$1,862 median on MNQ); funded life loses money more often than not. Every objective's held-out level is far below the window that chose it -- a funded account lasts 12 trading days against the 138 selection showed -- so the ordering transfers and the number does not.
---

# M40 — Prop accounts ranked by what they are scored on rather than by profit factor ([#326])

**What has changed since §M28.13, stated first.** No new sweep, condition or archetype. Every prop-account figure so far replays a shortlist that selection-window profit factor chose, and reads it for net. A prop trader may want something else: the most passes per attempt, the cheapest funded account, the first payout soonest, or a funded account that lasts. This campaign ranks the selection window by each of those four directly, and reads the shortlist held out beside the profit-factor shortlist.

The tool is `tools/campaign_propobjectives.py`. It needed one new field in `nqbt/propaccount.py`, `AccountRun.first_withdrawal_on`, since nothing recorded when money first left an account.

## What each objective measures

| objective        | per configuration, per preset                                               | better | when it never happens | read from                                     |
| ---------------- | --------------------------------------------------------------------------- | ------ | --------------------- | --------------------------------------------- |
| `pass_rate`      | passes ÷ attempts                                                           | higher | `0`                   | every preset with a profit target             |
| `fees_per_pass`  | every fee the sequence paid ÷ passes                                        | lower  | `inf`                 | every preset with a profit target             |
| `days_to_payout` | trading days from opening the first account to the first withdrawal         | lower  | `inf`                 | every preset with a profit target             |
| `funded_days`    | median, over the accounts that were funded, of trading days each one lasted | higher | `0`                   | every preset but TakeProfitTrader's Test ones |

- **A trading day is a session in the window's bars**, not a day the strategy traded, so a funded account that sat through a week of no signals lived that week.
- **Funded life starts the day after the pass and ends on the breach day.** An account still alive when the window ends is counted to the window's last session and marked as cut off; the share cut off is reported beside every figure, so a long life that is mostly censoring is visible.
- **TakeProfitTrader is read the way `docs/roadmap.md` § "A firm that changes its rules at the pass ships as two presets" says to read it.** The Test preset answers the three evaluation objectives and not funded life, because what it does after passing is a fiction. The PRO preset answers funded life only, counted from its first day, because it is funded from the day it opens and its "pass" is its first profitable day.
- **`days_to_payout` is a floor.** The replay withdraws whenever a withdrawal is eligible, in full, and models no payout cadence or cap (`docs/roadmap.md` § "What is deliberately not modelled").
- **Every figure is the replay's own.** Attempts are uncapped, positions are each archetype's default size, and the excursion order is `PEAK_FIRST`, as in §M28.13.

## The pool, and the archive it was re-run on

**A configuration has to be re-run before it can be replayed, so the objective ranks a pool rather than the whole grid.** The pool is the 500 distinct configurations the stored selection window ranks highest by profit factor, per archetype and root. Three things are taken out first:

- **the maximum-hold arms**, which §M29 ruled out;
- **a configuration stored under a second variant name at the same bar size**, since re-run on one archive those are the same trades and two copies would take two shortlist places. The same parameters at two bar sizes are two configurations, because resolution is not a parameter and it is the largest lever in the registry;
- **any row whose stored `ambiguous_share` exceeds `disambiguate.MIN_AMBIGUOUS_SHARE`**, the threshold that already means "the fill assumption could not have decided this".

**That third filter is not a refinement, it is what makes the pool readable at all.** Ranking on profit factor selects for `ambiguous_share`, exactly as §M28.2 predicted and §M28.7 measured. Unfiltered, OpeningRange's pool came back **100% above the threshold on both roots**, at a median share of 0.879 and held-out profit factors between 28 and 266 — every one of them an `entry=rejection` arm, which is the configuration space §M28.7 parked for this reason. DeadCatBounce's pool was 23% above it and PullBackAndGo's 26%; every other cell was at 0%. Both shares are reported on every row of the output, per `CONTRIBUTING.md` § "Statistics and results".

**Twelve cells, both roots each:**

- every archetype's `unfiltered` stratum, every stored variant but the hold caps;
- OpeningRange `phase=MIDDAY`, 5 minutes, `window=30m stop=opposite target=R` — the README's best cell (§M28.15);
- OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`, 5 minutes, the same variant (§M31, §M31.1);
- InsideBarTrailing `phase=MIDDAY`, 5 minutes (§M28.16).

**Every cell was re-run on the archive as it stands, to 2026-09-16.** Seven of the nine archetypes were stored before the archive was extended on 2026-09-16, so their stored rows describe a 60/40 split the series no longer makes and `tools/campaign_shortlist.py`'s `verify` would refuse every one (`docs/roadmap.md` § "Standing traps"). The pool is still ranked on those stored rows. Everything after that is re-measured on today's split:

- **Nothing ranked touches the holdout.** A stored selection window ends on 2024-09-17 on MNQ and 2024-09-25 on NQ, or on today's split for rows stored since. Today's selection windows run to 2024-10-09 and 2024-10-14 and contain both, and today's holdout starts after them.
- **Every figure below is the re-run's.** That includes the profit factor the control ranks by and the trade count; none is the stored row's.
- **The bars are prepared as `PriceBasis.RAW`**, because `splice.load_continuous` is called without back-adjustment, exactly as `tools/campaign_sweep.py` prepares them. Without it EmaCrossover's round-number arms refuse to run at all.
- **The cost is the reproduction check.** A re-run that no longer matches its stored row cannot be told apart from one rebuilt wrong, so nothing here checks the rebuild against the row. The rebuild is `campaign_shortlist.rebuild`, the one every gate-3 and gate-4 read already uses.

**The control is the top 20 by profit factor on the re-run selection window**, the ranking §M28.13 and §M28.15 read. Each objective's top 20 is read beside it on the holdout, with selection-window profit factor breaking ties.

## The ordering transfers and the level does not

**Every objective's ranking beats the control at its own objective held out.** Counted over the cell × root × preset pairs where the two shortlists actually differ, and the objective is readable on both sides:

| objective        | better | worse |       p | median gain where both are readable |
| ---------------- | -----: | ----: | ------: | ----------------------------------- |
| `pass_rate`      |     63 |    10 | 1.6e-10 | +0.002 passes per attempt           |
| `fees_per_pass`  |     41 |    17 | 2.2e-03 | $283 cheaper per funded account     |
| `days_to_payout` |     36 |    16 | 7.8e-03 | 9.5 trading days sooner             |
| `funded_days`    |     39 |    19 | 1.2e-02 | no change at the median             |

Two-sided sign tests, ties dropped. **This is four tests on one family and every one clears 0.05**, which is what a real effect looks like rather than the best of four.

**The level it transfers at is far worse than the window it was chosen on.** Medians over MNQ's cells and presets, the ranked arm only:

| objective        | selection | holdout | never happens held out |
| ---------------- | --------: | ------: | ---------------------: |
| `pass_rate`      |     0.455 |   0.137 |                     0% |
| `fees_per_pass`  |    $1,453 |  $1,818 |                  19.8% |
| `days_to_payout` |        52 |     120 |                  20.5% |
| `funded_days`    |     138.5 |      12 |                     0% |

**A funded account lasts 12 trading days held out where the selection window said 138.** Choose the configuration by the objective if you like; do not quote the number it was chosen at.

## What it is worth: the account gets funded, and only one objective also pays

**Every objective raises the share of a shortlist that ever gets funded**, paired by cell and preset, held out:

| objective        | MNQ, mean change | better | worse |       p | NQ, mean change |       p |
| ---------------- | ---------------: | -----: | ----: | ------: | --------------: | ------: |
| `fees_per_pass`  |           +0.214 |     37 |     5 | 4.4e-07 |          +0.202 | 1.2e-07 |
| `days_to_payout` |           +0.208 |     38 |     4 | 5.7e-08 |          +0.157 | 2.4e-05 |
| `pass_rate`      |           +0.061 |     32 |     9 | 4.3e-04 |          +0.151 | 3.6e-07 |
| `funded_days`    |           +0.051 |     22 |     7 | 8.1e-03 |          +0.030 | 8.8e-02 |

**The largest part of that is not a better number, it is a number at all.** Where the shortlists differ, there are **42 pairs whose objective-ranked arm gets funded when the control never does, against 1 the other way** for `fees_per_pass`, and 41 against 4 for `days_to_payout`. A control shortlist that never passes has no fees per pass and no payout to time.

**Net is a different question, and only `days_to_payout` answers it.** Paired, MNQ, median change in net against the control:

| objective        | net better | worse | median change |     p |
| ---------------- | ---------: | ----: | ------------: | ----: |
| `days_to_payout` |         50 |    18 |       +$1,862 | 0.000 |
| `fees_per_pass`  |         42 |    26 |           +$8 |  0.07 |
| `pass_rate`      |         28 |    33 |            $0 |  0.61 |
| `funded_days`    |         28 |    41 |            $0 |  0.15 |

**Ranking by how long it takes to get paid is the only one of the four that is free**, and it is the one a trader waiting on a first withdrawal would have picked anyway. **Ranking by funded life is the one to avoid**: it is the weakest at funding the account and it loses money more often than not.

## Two objectives that reward the wrong thing

**A pass rate of 1.000 is one attempt.** The three MNQ shortlists that reach it are DeadCatBounce cells making **one to 1.5 accounts on 82 to 93 trades** across the whole holdout, and two of the three are net-negative — −$1,125 on TakeProfitTrader 50K and −$98 on TopStep 50K. Passing every account you open is what a strategy that barely trades looks like, not what a good account looks like. Read `attempts` beside it, which is why the tool reports both.

**Funded life is mostly censoring.** Its best MNQ cell per preset runs to 501 trading days on TakeProfitTrader 150K PRO — one attempt, 95% of it cut off by the end of the window, on a profit factor of 0.922 and a net of −$130. Every `funded_days` figure carries `censored_share` for that reason.

## The configurations behind each objective

**Every cell below was chosen after the holdout was read**, by taking each objective's best held-out value per preset and asking which cell it came from. That makes this a description of where the values landed, not a selection anything survived. The shortlist is a different twenty per preset, since each preset ranks its own; a parameter listed as swept is one the union of those shortlists varies over.

### `fees_per_pass` and `pass_rate`: InsideBarTrailing, `phase=MIDDAY`, 5 minutes

One cell leads both objectives, on three of the seven MNQ presets each. It is §M28.16's cell — the strongest gate-3 result outside OpeningRange, and the one that leans least on the forced flat.

| held fixed across every shortlisted configuration                                                                                               | swept                                                                                                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `order_quantity` 6, `atr_multiplier` 10.0, `tp_multiplier` 1.0, `slow_sma_period` 125, `phase_filter` MIDDAY, `variant` trailing, 5-minute bars | `ema_period` 11/22/44, `fast_sma_period` 20/35/50, `error_margin` 0.05/0.1, `atr_length` 3/14, `partial_take_profit_percentage` 0.3/0.5/0.6/0.8, `trailing_stop_multiplier` 2.0/5.0/10.0 |

Ranked by `fees_per_pass`, medians over each preset's twenty:

| root | preset                     |     cost | attempts | passes |    fees |                  net | ever passed | net > 0 | profit factor |
| ---- | -------------------------- | -------: | -------: | -----: | ------: | -------------------: | ----------: | ------: | ------------: |
| MNQ  | TakeProfitTrader 25K Test  | **$444** |     44.5 |     16 |  $7,205 |         **+$24,917** |        100% |    100% |         1.388 |
| MNQ  | TakeProfitTrader 50K Test  |     $617 |     29.5 |     10 |  $5,955 |         **+$29,038** |        100% |    100% |         1.493 |
| MNQ  | TopStep 50K                |     $800 |     78.5 |      7 |  $5,600 |         **+$18,211** |        100% |    100% |         1.418 |
| MNQ  | Apex 50K                   |   $1,233 |       23 |    6.5 |  $7,943 |         **+$22,652** |        100% |    100% |         1.297 |
| MNQ  | TakeProfitTrader 150K Test |   $2,722 |        4 |      2 |  $5,660 |         **+$23,143** |        100% |    100% |         1.428 |
| MNQ  | TopStep 150K               |   $3,129 |       18 |      2 |  $6,109 |          **+$9,860** |        100% |    100% |         1.299 |
| MNQ  | Apex 150K                  |   $8,149 |        3 |      1 |  $7,852 |         **+$25,538** |         75% |     65% |         1.412 |
| NQ   | TakeProfitTrader 50K Test  |   $1,707 |    184.5 |   12.5 | $20,773 |        **+$135,342** |        100% |    100% |         1.384 |
| NQ   | TakeProfitTrader 150K Test |   $1,738 |    127.5 |     18 | $32,300 |        **+$202,019** |        100% |    100% |         1.450 |
| NQ   | TakeProfitTrader 25K Test  |   $1,746 |      205 |   11.5 | $20,125 |        **+$123,025** |        100% |    100% |         1.586 |
| NQ   | TopStep 150K               |   $6,929 |      172 |      4 | $27,267 |         **+$29,856** |        100% |    100% |         1.400 |
| NQ   | Apex 150K                  |  $68,440 |      230 |      1 | $69,693 |         **+$14,562** |         90% |     85% |         1.287 |
| NQ   | Apex 50K, TopStep 50K      |      inf |  237–290 |      0 |       — | −$11,760 to −$48,514 |        0–5% |      0% |    1.31, 1.40 |

**Every MNQ preset's median configuration is profitable after fees**, and six of the seven fund all twenty; Apex 150K funds 15 of 20, having the least room of any preset at six contracts. On NQ it splits exactly where §M28.13's room arithmetic says it must: the presets with 56 points or more fund it, and Apex 50K and TopStep 50K never pass in twenty configurations.

**The single cheapest pass held out** is TakeProfitTrader 25K Test at **$395 per funded account** — 44 attempts, 19 passes, +$26,064 net at a profit factor of 1.630 over 308 trades — on `ema_period` 22, `fast_sma_period` 35, `error_margin` 0.05, `atr_length` 14, `partial_take_profit_percentage` 0.8, `trailing_stop_multiplier` 5.0.

Ranked by `pass_rate` the same cell returns 0.097 to 0.536 on MNQ, at nets of +$12,436 to +$28,254 and profit factors of 1.19 to 1.52. **Its best single configuration passes both accounts it opens** — `pass_rate` 1.000 on Apex 150K from two attempts, +$27,100 at 1.549 over 288 trades — which is the same one-attempt caveat the DeadCatBounce cell shows below, in a milder form.

**The 150K presets are cheaper per pass on `InsideBar` unfiltered**, at $1,560 (TakeProfitTrader 150K Test, +$40,962) and $1,788 (TopStep 150K, +$37,971) over 1,600 to 1,900 trades rather than 300, and at least 80% of its shortlist is funded on every preset on both roots, which no other cell here manages. Its profit factor is 1.06 to 1.09 against this cell's 1.30 to 1.49.

### `days_to_payout`: InsideBarTrailing, `unfiltered`

The same archetype with the phase filter off, leading five of the seven MNQ presets. The shortlist spans every bar size — 39% at 5 minutes, 27% at 10, 18% at 15, 16% at 1 and 2 — and the axes are the same six.

| root | preset                     | days | attempts | passes |     fees |                    net | ever passed | net > 0 | profit factor |
| ---- | -------------------------- | ---: | -------: | -----: | -------: | ---------------------: | ----------: | ------: | ------------: |
| MNQ  | TakeProfitTrader 25K Test  |   21 |      133 |     20 |  $15,865 |           **+$68,666** |        100% |    100% |     **1.034** |
| MNQ  | TakeProfitTrader 50K Test  |   22 |    103.5 |     19 |  $14,283 |           **+$48,002** |        100% |    100% |     **0.991** |
| MNQ  | TopStep 50K                |   24 |    174.5 |   11.5 |  $11,423 |           **+$17,736** |        100% |     90% |     **1.007** |
| MNQ  | Apex 50K                   | 35.5 |     98.5 |    9.5 |  $20,756 |           **+$20,515** |        100% |     95% |     **0.990** |
| MNQ  | TakeProfitTrader 150K Test | 51.5 |     54.5 |      8 |  $17,046 |           **+$49,293** |        100% |    100% |     **0.987** |
| MNQ  | TopStep 150K               |   53 |       80 |      8 |  $16,167 |           **+$54,332** |        100% |    100% |     **0.951** |
| MNQ  | Apex 150K                  |  113 |       47 |      4 |  $20,438 |           **+$20,041** |        100% |     95% |     **0.946** |
| NQ   | TakeProfitTrader 150K Test |   27 |    275.5 |     17 |  $64,462 |          **+$403,064** |        100% |    100% |     **0.932** |
| NQ   | TakeProfitTrader 25K/50K   |   35 |  361–394 |   9–12 |  $37–39k | +$161,571 to +$195,718 |        100% |    100% |  0.996, 1.059 |
| NQ   | Apex 150K                  |   41 |    462.5 |      1 | $137,790 |               −$85,594 |         80% |     20% |         1.104 |
| NQ   | Apex 50K, TopStep 50K      |  inf |  450–481 |  0–0.5 |  $22–80k |   −$15,119 to −$80,244 |       0–50% |      0% |  1.083, 1.115 |

**The profit factor is the column to read.** This is the fastest route to a first withdrawal anywhere in the register and it is **below 1.0 on five of seven MNQ presets and on the best NQ preset**. §M28.13's reset economics are the whole mechanism: the accounts die faster than the strategy makes money, and the withdrawals taken before each death outrun the fees. **A first payout in 21 trading days at a profit factor of 1.034 is not an edge**, it is a sequence of accounts whose losses the firm caps.

**The single fastest payout held out is 3 trading days**, on EmaPullback's unfiltered cell at 10 minutes on TakeProfitTrader 25K Test — 26 attempts, 4 passes, +$4,695 net at a **profit factor of 0.579**. That is the same reading in its sharpest form.

### `funded_days`: ElasticBand, `unfiltered`, and the case against the objective

It leads only two of seven presets, which is itself the finding — no cell leads this objective the way one cell leads the other three.

| held fixed                                                                                                      | swept                                                                                                                                                   |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `order_quantity` 4, `atr_stop_multiple` 2.0, `atr_period` 14, `tp_multiplier` 1.0, `catastrophe_stop_ticks` 400 | `band_source`, `band_period` 10/20, `entry_std` 2.0/2.5/3.0, `stop_mode`, `signal_shape`, `min_bars_outside`, `recovery_fraction`, `max_hold_bars` 0/30 |

| root | preset                    |  days | attempts | passes |   fees |               net | ever passed | net > 0 |
| ---- | ------------------------- | ----: | -------: | -----: | -----: | ----------------: | ----------: | ------: |
| MNQ  | TakeProfitTrader 150K PRO |   135 |        3 |      2 |   $390 |           +$1,116 |        100% |     65% |
| MNQ  | TakeProfitTrader 50K PRO  |    96 |        4 |      2 |   $520 |             +$716 |        100% |     55% |
| MNQ  | TopStep 50K               |    61 |        4 |      1 | $1,472 |             +$424 |         80% |     65% |
| MNQ  | Apex 50K                  |    60 |        4 |      1 | $4,556 |             +$962 |         70% |     60% |
| MNQ  | TakeProfitTrader 25K PRO  | 30.25 |        6 |      3 |   $780 |              +$20 |         95% |     50% |
| MNQ  | Apex 150K                 |     0 |      2.5 |      0 | $7,639 |       **−$7,425** |         25% |     25% |
| MNQ  | TopStep 150K              |     0 |        2 |      0 | $3,725 |       **−$3,725** |         35% |     35% |
| NQ   | TopStep 150K              |    15 |       18 |    0.5 | $5,066 |           +$1,669 |         50% |     50% |
| NQ   | every other preset        |   0–4 |   24–183 |    0–3 | $3–31k | −$112 to −$26,730 |      25–90% |   0–50% |

**The two largest accounts never get funded at all on MNQ and lose their fees**, the five that do are worth $20 to $1,116, and on NQ every preset is negative. **The longest lives are mostly censoring**: the 135-day figure is 95% cut off by the end of the holdout, and the single longest funded life in the whole campaign — **502 trading days**, ElasticBand at 2 minutes on TakeProfitTrader 150K PRO — is **one account that never breached**, at +$2,032 on 235 trades.

That is the objective's defect rather than this cell's bad luck. A long funded life is either an account that survived the window, which is censoring, or an account that was never risked, which is a strategy that barely trades. Neither is a reason to choose a configuration, and the paired test agrees: `funded_days` is the one objective that loses net more often than it gains it.

### The pass rate's own trap: DeadCatBounce, `unfiltered`

DeadCatBounce leads `pass_rate` on three MNQ presets, at exactly 1.000, and the mechanism is worth stating in full because the number looks like the best result in the campaign.

| held fixed                                                                                                            | swept                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `order_quantity` 4, `bars_required_to_trade` 200, `stop_offset_ticks` 2, `entry_offset_ticks` 2, `max_risk_ticks` 250 | `ema_period` 9/15/21/30, `fast_sma_period` 40/60/80, `ema_kind` ema/hma/sma/wma, `use_vwap`, `tp_multiplier` 1.0/1.5/2.0, 5/10/15-minute bars |

| root | preset                                      | pass rate | attempts | passes |    fees |                net | ever passed | net > 0 |
| ---- | ------------------------------------------- | --------: | -------: | -----: | ------: | -----------------: | ----------: | ------: |
| MNQ  | TakeProfitTrader 25K Test                   | **1.000** |      1.5 |      1 |  $1,025 |              +$622 |        100% |     70% |
| MNQ  | TakeProfitTrader 50K Test                   | **1.000** |        1 |      1 |  $2,221 |        **−$1,125** |         60% |     30% |
| MNQ  | TopStep 50K                                 | **1.000** |        1 |      1 |  $1,276 |               −$98 |         55% |     45% |
| MNQ  | Apex 50K, Apex 150K, TopStep 150K, TPT 150K |     0.000 |        1 |      0 | $3.5–7k | −$3,841 to −$6,980 |       0–45% |      0% |

**The whole shortlist opens one account.** Its configurations take 82 to 93 trades across the entire holdout, so a single account either passes and is never breached, or never passes at all — and the pass rate is 1.000 or 0.000 accordingly. Net is negative on five of the seven presets, and the cell's held-out profit factor of 1.57 to 1.70 is measured on those 82 trades.

**So a pass rate has to be read with `attempts` beside it**, which is why the tool reports both and why this section gives attempts in every table. The objective is still the one that transfers most strongly of the four (63 better against 10 worse, p = 1.6e-10); what it cannot do alone is tell a reliable account from a rare one.

## What travels and what does not

- **The comparison is between rankings, not a gate.** Nothing here is put to a matched random entry or a bootstrap; a shortlist chosen by pass rate is still a shortlist chosen from the same pool, and the pool's own edge is whatever the rest of the register says it is.
- **The cells chosen as "best" below were chosen after the holdout was read.** They describe where a value happened to land, and none is a recommendation.
- **The 120 paired units per root are not independent.** Ten presets over twelve cells share archetypes, and the two 150K presets of one firm often shortlist the same rows.
- **`days_to_payout` is a floor and the payout rules are not modelled**, so the ordering is more trustworthy than the number of days.
- **NQ remains a different question from MNQ at four contracts** — §M28.13's arithmetic is unchanged, and Apex's presets fund no NQ shortlist in any cell.

Every figure here is one dated run over the archive as it stood on 2026-09-16, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_propobjectives.py` — not a standing property.

[#326]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/326
