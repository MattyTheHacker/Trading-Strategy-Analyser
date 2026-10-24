---
id: M62
title: "M62 — a book of copied prop accounts: the money scales with the book, and the worst day takes all of it"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [446]
gates: []
outcome: mixed
verdict: >-
  Read on the October 2026 re-sweep through every linked 2026 account: copying one strategy's trades onto a book of up to twenty accounts multiplies what one account makes, at 0.82 to 1.04 of its profit per account on InsideBarTrailing's midday cell, and does not spread the risk, since in 96% of that cell's replays every account in a book of twenty breaches on the same day with openings five trading days apart. A book makes nothing pay that one account does not. Opening each account out of the book's payouts keeps InsideBarTrailing's midday cell profitable on four of the seven accounts it pays on alone, from at most about $1,000 of cash, and turns OpeningRange's midday cell into a loss on all six.
---

# M62 — a book of copied prop accounts: the money scales with the book, and the worst day takes all of it ([#446])

[#446] asked what copying one strategy's trades onto 5, 10, 15 or 20 prop accounts at once would make, cost and risk, as a trade copier would run them. [#477] built the read, `replay_book` and `--book-sizes`, with its design in `docs/roadmap.md` § "A book of accounts". This is its first run, on the rows of the October 2026 re-sweep, beside §M61. It is a read rather than a test.

## In plain terms

A trade copier places the same trades on several prop accounts at once. The question was whether that only multiplies one account's result, or whether opening the accounts at different times spreads the risk.

**It multiplies the result, and the risk with it.** For the best candidate, InsideBarTrailing in the midday lull, twenty accounts make 16 to 21 times what one makes. But on its worst days every account blows at once, even when they were opened a week apart, so twenty accounts are one bet made twenty times, not twenty separate bets.

Copying cannot rescue a strategy that loses on one account. Paying for each new account out of the earlier ones' payouts works for InsideBarTrailing on four of the seven accounts it pays on, from about $1,000 or less of your own money. For OpeningRange, the other candidate, it loses money on every account.

## What was run

`tools/campaign_propaccount.py --rerun --preset all --book-sizes 5 10 15 20`, once with each way of opening the accounts:

- **`--stagger 5`**: one account every five trading days, so the twentieth opens 95 trading days after the first.
- **`--stagger funded`**: the first account paid out of pocket and each next one opened once the book's payouts less its fees cover it.

Every account in a book takes the same preset, and a breached account is replaced the next trading day, as in the single-account replay. The presets are the fifteen linked 2026 accounts, each firm's evaluation linked to the funded account its pass opens ([#440]), at each configuration's stored size.

Two kinds of shortlist were replayed, each 20 configurations ranked on the selection window by profit factor and replayed held out:

- **The two midday cells §M43 and §M51 read**: InsideBarTrailing's `trailing` and OpeningRange's `window=30m stop=opposite target=R`, both `phase=MIDDAY` at 5 minutes on MNQ.
- **Every archetype on both roots, on the replay's default shortlist**: the 20 the selection window ranks highest across every stratum, mostly filtered cells of 30 to 60 held-out trades.

All 40 reads ran at the commit that merged [#479], between 2026-10-20 and 2026-10-21. **Every figure below is a median over one shortlist of 20.**

## A book makes nothing pay that one account does not

Of the 300 pairs of a shortlist and an account, **14 pay with one account**: 13 are the two midday cells', and the fourteenth is OpeningRange's MNQ shortlist on LucidPro 50K. With twenty accounts opened five trading days apart, 16 pay. The two added are both midday cells that lose $220 and $1,442 on one account and make $1,304 and $4,239 across twenty, which is break-even spread over a book. Opened from the book's payouts, 4 pay. Everything below reads the two midday cells.

## The money scales with the book

InsideBarTrailing's midday cell on the seven accounts it pays on alone, with openings five trading days apart:

| account        | one account | five accounts | twenty accounts | most out of pocket, 1 → 20 | trading days to profit, 1 → 20 |
| -------------- | ----------: | ------------: | --------------: | -------------------------: | -----------------------------: |
| TopStep 50K    |     +13,400 |       +63,800 |        +224,500 |              $247 → $1,380 |                        36 → 38 |
| LucidFlex 50K  |      +9,000 |       +42,200 |        +156,900 |                $105 → $947 |                        36 → 36 |
| Apex 50K EOD   |      +6,100 |       +30,700 |        +121,400 |           $1,001 → $16,571 |                      196 → 199 |
| LucidPro 50K   |      +4,300 |       +19,700 |         +70,800 |              $140 → $1,544 |                        40 → 42 |
| LucidDaily 50K |      +3,300 |       +15,800 |         +64,200 |              $125 → $1,127 |                      37.5 → 39 |
| LucidPro 150K  |      +3,000 |       +14,800 |         +61,400 |           $2,104 → $40,718 |                      496 → 494 |
| LucidFlex 150K |      +2,800 |       +11,600 |         +49,600 |           $1,182 → $25,824 |                    480.5 → 484 |

Net rounded to the nearest hundred dollars.

**Twenty accounts make 0.82 to 1.04 times one account's profit per account**, the shortfall being the later accounts' shorter time trading. The time to profit and the count of profitable months barely move, because every account takes the same trades. **What a book changes is the cash it needs**: on the four 50K accounts that pay back in about forty trading days, twenty accounts never have more than about $1,500 out, while on Apex 50K EOD and the two 150K accounts they have $16,600 to $40,700 out before payouts catch up.

OpeningRange's midday cell scales the same way at a tenth to a half of InsideBarTrailing's profit per account on the same account: +$28,900 to +$52,700 across twenty accounts on its six paying accounts, with $13,400 to $23,300 out and 234 to 520 trading days to profit.

## The worst day takes the whole book

Of each cell's 300 replays, one per configuration and account, the share in which every account in the book breached on a single day, and the median count of days on which more than half the book breached together:

| cell              | openings        | every account on one day, 5 accounts | every account on one day, 20 accounts | days most of a book of 20 breached |
| ----------------- | --------------- | -----------------------------------: | ------------------------------------: | ---------------------------------: |
| InsideBarTrailing | five days apart |                                  98% |                                   96% |                               24.5 |
| InsideBarTrailing | from payouts    |                                  89% |                                   75% |                                 24 |
| OpeningRange      | five days apart |                                  94% |                                   94% |                                 12 |
| OpeningRange      | from payouts    |                                  82% |                                   82% |                               21.5 |

**Opening accounts five trading days apart does not spread the risk.** In nearly every replay a book of twenty loses all twenty on one day, and on InsideBarTrailing's midday cell more than half the book goes together on about 24 days of the held-out window. The likeliest reason is that a breached account is replaced the next day, so most of a book's accounts are fresh at any time, and a day bad enough for one fresh account is bad enough for all of them. Opening from payouts spreads it a little, because those accounts open further apart.

## Opening from payouts works for one of the two cells

A book of twenty, both ways of opening it:

| cell, account                         |         five days apart: net, most out |       from payouts: net, most out |
| ------------------------------------- | -------------------------------------: | --------------------------------: |
| InsideBarTrailing, TopStep 50K        |                       +224,500, $1,380 |                    +179,100, $247 |
| InsideBarTrailing, LucidFlex 50K      |                         +156,900, $947 |                     +88,200, $105 |
| InsideBarTrailing, Apex 50K EOD       |                      +121,400, $16,571 |                   +72,100, $1,001 |
| InsideBarTrailing, LucidDaily 50K     |                        +64,200, $1,127 |                     +12,100, $125 |
| InsideBarTrailing, LucidPro 50K       |                        +70,800, $1,544 |                         −29, $140 |
| InsideBarTrailing, LucidPro 150K      |                       +61,400, $40,718 |                      −312, $2,104 |
| InsideBarTrailing, LucidFlex 150K     |                       +49,600, $25,824 |                    −1,492, $1,182 |
| OpeningRange, its six paying accounts | +28,900 to +52,700, $13,400 to $23,300 | −4,200 to −20,200, $600 to $1,400 |

**A book grown from its own payouts needs only the first account's cash**, and on InsideBarTrailing's midday cell it still makes +$12,100 to +$179,100 on four accounts, its three best among them. It breaks even on LucidPro 50K and loses on both 150K accounts, whose books open only 8 and 12 accounts in the window. **OpeningRange's midday cell loses on all six of its paying accounts**, profitable in 0% to 30% of configurations. Neither how fast one account pays back nor how much it makes separates the books that work from those that do not: Apex 50K EOD takes 196 trading days and works, LucidPro 50K takes 40 and does not. Part of the shortfall is where the window ends: a book still buying accounts near its last day is charged for them and credited nothing they would go on to earn, so this reading is harsher than a book that kept running would be.

## What this is not

- **Not a test.** It reads shortlists; it tests nothing against a null.
- **Not inside any firm's limit on accounts per trader.** None is modelled (`docs/roadmap.md` § "A book of accounts"), and twenty accounts may be more than a firm allows one trader.
- **A best case on timing.** A payout counts on the day it falls due, as `days_to_profit` does.
- **Not independent evidence.** The accounts share almost every trade, so their agreeing is not confirmation.
- **One preset per book, replaced on breach, and two ways of opening.** Mixing firms (`--book-mix`), letting the book shrink (`--no-replace`) and other gaps between openings were not run, so [#446]'s question whether mixing firms spreads the risk is still open.
- **The per-archetype books read thin cells.** Their default shortlist ranks across every stratum, so they are not the unfiltered shortlists §M46 laddered, and they say little beyond that only one of them pays.

## What this settles

- **A copied book is one strategy's bet made N times.** Its profit and its cash scale with the number of accounts, and its worst day takes every account in nearly every replay, with openings five trading days apart.
- **It makes nothing pay that one account does not.**
- **Growing a book from its payouts works for InsideBarTrailing's midday cell on TopStep 50K, LucidFlex 50K, Apex 50K EOD and LucidDaily 50K**, from about $100 to $1,000 of cash, and does not work for OpeningRange's midday cell on any account.

[#440]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/440
[#446]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/446
[#477]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/477
[#479]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/479
