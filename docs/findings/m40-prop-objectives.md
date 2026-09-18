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

## What travels and what does not

- **The comparison is between rankings, not a gate.** Nothing here is put to a matched random entry or a bootstrap; a shortlist chosen by pass rate is still a shortlist chosen from the same pool, and the pool's own edge is whatever the rest of the register says it is.
- **The cells chosen as "best" below were chosen after the holdout was read.** They describe where a value happened to land, and none is a recommendation.
- **The 120 paired units per root are not independent.** Ten presets over twelve cells share archetypes, and the two 150K presets of one firm often shortlist the same rows.
- **`days_to_payout` is a floor and the payout rules are not modelled**, so the ordering is more trustworthy than the number of days.
- **NQ remains a different question from MNQ at four contracts** — §M28.13's arithmetic is unchanged, and Apex's presets fund no NQ shortlist in any cell.

Every figure here is one dated run over the archive as it stood on 2026-09-16, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_propobjectives.py` — not a standing property.

[#326]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/326
