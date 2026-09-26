---
id: M46
title: "M46 — every archetype's held-out shortlist through the prop accounts at each contract count"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [295]
gates: []
outcome: mixed
verdict: >-
  Size moves nothing but the dollars on every archetype but InsideBarTrailing, now shown on real data at every rung; a bracket cannot be traded below one contract per target, which shuts every four-target archetype out of an NQ 50K account; on a 50K account only InsideBar, InsideBarTrailing and OpeningRange's opposite-extreme stop pay at any size, and every step up in size buys more resets.
---

# M46 — every archetype's held-out shortlist through the prop accounts at each contract count ([#295])

**The plain quantity axis [#295] asks for, read across the whole registry.** §M45 put one cell through the account at five sizes; this puts every archetype's own campaign grid through it at ten. It is a read rather than a test, as §M45's was, and it answers one question: at what size does each archetype pay on each account, if at all?

## What was run

`tools/campaign_propaccount.py --quantities`, once per archetype, campaign variant and root: **54 shortlists across the nine archetypes**, each on the unfiltered stratum. Each shortlist is the 20 configurations the selection window ranks highest on profit factor, re-run on the held-out window at each contract count and replayed through the four presets §M28.13 read, attempts uncapped:

|         | contract counts                     |
| ------- | ----------------------------------- |
| **MNQ** | 1, 2, 3, 4, 6, 8, 10, 12, 16 and 20 |
| **NQ**  | 1, 2, 3 and 4                       |

InsideBarTrailing's midday cell at five minutes, §M45's, also took the MNQ ladder, carrying it past the eight §M45 stopped at. Costs are the campaign's own. Everything ran on `main` at the commit that merged §M45 and on the archive §M44 left. All 55 shortlists finished cleanly and no replay reached an attempt cap.

**Every figure below is a median over one shortlist of 20.** A preset's figure is not any single configuration's.

## Size moves nothing but the dollars, now on real data

§M45's pre-registration showed on synthetic bars that quantity only rescales money on every archetype but InsideBarTrailing. **This run is the same check on real data, at every rung.** Each rung prints whether its re-run was on the bars the stored row was swept on, and how many configurations reproduced their stored trade count. Of 653 such checks, every one was on the swept bars. **Every archetype but InsideBarTrailing reproduced its stored trade count at every size**, 20 of 20 where the shortlist had 20.

**InsideBarTrailing is the exception, as §M45 said it would be.** At its stored six contracts all 20 configurations reproduce, on both of its MNQ shortlists. At every other size fewer do: between 0 and 10 of 20, because the `-200` gate reads the open position in dollars. Its midday ladder reproduces every figure §M45 printed for two to eight contracts to the dollar.

## A bracket cannot be traded below one contract per target

The refusals name a floor that is structural rather than chosen:

| bracket                                                                                                         | legs |       smallest size |
| --------------------------------------------------------------------------------------------------------------- | ---: | ------------------: |
| DeadCatBounce, EmaCrossover, EmaPullback, PullBackAndGo, and OpeningRange's and SqueezeBreakout's R-ladder arms |    4 |                   4 |
| ElasticBand, and OpeningRange's and SqueezeBreakout's `target=width` arms                                       |    2 |                   2 |
| InsideBarTrailing                                                                                               |    2 | 2, 3 at a 0.6 split |
| InsideBar                                                                                                       |    1 |                   1 |

DeadCatBounce's and PullBackAndGo's refusals note that their NinjaScript enforces the same floor, with a `Range(4, ...)` attribute on `OrderQuantity`.

**On NQ that floor decides the answer.** Four NQ contracts is the position §M28.13 found fatal on a 50K account, and it is the smallest a four-target bracket can take. **Not one four-target shortlist pays on either NQ 50K preset.** Nor does any two-target shortlist at two contracts. The four-target archetypes cannot be traded on an NQ 50K account in the form they were swept in. That is a statement about the bracket, not the entry: trading one there needs fewer targets.

## Which archetypes pay at any size

Shortlists with at least one size at which the median net is positive:

| root | Apex 50K | TopStep 50K | Apex 150K | TopStep 150K |
| ---- | -------: | ----------: | --------: | -----------: |
| MNQ  |  7 of 28 |    20 of 28 |   7 of 28 |     22 of 28 |
| NQ   |  1 of 27 |     1 of 27 |   1 of 27 |     13 of 27 |

MNQ counts the midday shortlist as a 28th.

**On Apex 50K the seven are three archetypes**: InsideBar, InsideBarTrailing (unfiltered and midday), and OpeningRange's opposite-extreme stop at the 15- and 30-minute windows. That is the half §M28.1 found passes gate 1 in every cell. **On NQ, only InsideBar pays on a 50K account**, the one archetype whose bracket can be traded at a single contract.

### MNQ, 50K accounts

The best size by median net, with the attempts and passes the median configuration takes there:

| shortlist                                 |                    Apex 50K |                TopStep 50K |
| ----------------------------------------- | --------------------------: | -------------------------: |
| InsideBar                                 | 20: +168,600, 309.5 att, 10 | 10: +60,200, 304.5 att, 20 |
| InsideBarTrailing, unfiltered             |     4: +33,700, 58.5 att, 7 |    6: +36,100, 278 att, 12 |
| InsideBarTrailing, midday                 |     6: +31,900, 29 att, 3.5 |    6: +19,200, 89.5 att, 7 |
| OpeningRange 30m, opposite stop, width    |       4: +23,600, 56 att, 6 |  4: +22,100, 119.5 att, 12 |
| OpeningRange 15m, opposite stop, width    |       4: +22,100, 45 att, 3 |    4: +19,500, 127 att, 12 |
| OpeningRange 15m, opposite stop, R ladder |       4: +15,000, 69 att, 4 |    4: +19,700, 128 att, 10 |
| OpeningRange 30m, opposite stop, R ladder |        4: +9,900, 63 att, 4 |    4: +19,600, 119 att, 10 |

Figures rounded to the nearest hundred dollars.

**For every shortlist in the table but InsideBar the answer is close to the size it was swept at.** OpeningRange's best is its stored four on both presets, and InsideBarTrailing's is four to six. **InsideBar is the exception, and it rests on two things the replay does not limit.** On Apex 50K its median passes hold at 14 from four to ten contracts and fall to 10 at twenty, while its attempts climb from 77 to 309.5. What grows past four is the payout per funded account: withdrawals rise from $72,400 at four to $163,900 at ten on the same 14 passes, against fees rising from $18,700 to $40,600. The replay takes every withdrawal in full with no payout cap, and each blown account costs only its fee — §M28.13's "net rewards variance", visible along one axis.

### MNQ, 150K accounts

| shortlist                                 |          Apex 150K |       TopStep 150K |
| ----------------------------------------- | -----------------: | -----------------: |
| InsideBar                                 | 20: +271,500 (top) | 20: +169,900 (top) |
| InsideBarTrailing, unfiltered             |        12: +95,200 | 20: +151,300 (top) |
| InsideBarTrailing, midday                 |        12: +56,900 |        16: +90,000 |
| OpeningRange 30m, opposite stop, width    |         8: +51,000 |       16: +101,300 |
| OpeningRange 15m, opposite stop, R ladder |         6: +38,400 |       16: +133,400 |

**§M45's truncated axis is closed.** Its midday cell was still rising at eight on both 150K presets. Carried on, it peaks at ten to twelve contracts on Apex 150K and at sixteen on TopStep 150K, then falls. On the 50K presets it confirms §M45's six.

**TopStep 150K admits almost anything**: 22 of 28 MNQ shortlists pay on it at some size, EmaCrossover and SqueezeBreakout among them, against 7 of 28 on Apex 150K. What separates the two presets is not measured here.

### NQ

| shortlist                              |               Apex 50K |         TopStep 50K |   Apex 150K | TopStep 150K |
| -------------------------------------- | ---------------------: | ------------------: | ----------: | -----------: |
| InsideBar                              | 3: +105,000, 414.5 att | 1: +58,100, 322 att | 3: +213,400 |  3: +223,100 |
| OpeningRange 30m, opposite stop, width |                  loses |               loses |       loses |  2: +102,400 |
| InsideBarTrailing, unfiltered          |                  loses |               loses |       loses |   2: +84,800 |

**On NQ the stored four contracts is the wrong size even where the archetype pays.** InsideBar nets +72,700 at four on Apex 50K against +105,000 at three, and +6,700 at four on TopStep 50K against +58,100 at one. It does so as a sequence of three to four hundred accounts over the held-out window. **The single contract is not a way to keep one account alive**: InsideBar at one NQ contract still takes 228 attempts on Apex 50K and 322 on TopStep 50K. InsideBarTrailing's unfiltered shortlist pays on NQ only on TopStep 150K, at two; its midday cell, in §M45, paid at two on both 150K presets.

## Every step up in size buys more resets

**Across all 55 shortlists and four presets, the median attempt count rises at 898 of 912 steps from one size to the next**, stays level at 11 and falls at 3, by at most three attempts. **More contracts means more blown accounts, almost without exception**; whether it also means more net depends on whether the extra payouts outrun the extra fees.

So **a size that maximises net is a size that maximises net per sequence of accounts**, and the sequence can run to hundreds. Where the best net sits at the top of the ladder — InsideBar on three of the four MNQ presets, and on MNQ's TopStep 150K InsideBarTrailing's unfiltered shortlist and three others — the ladder was not carried further. For InsideBar on Apex 50K at least, the extra size is already past the point where passes stop rising, so a longer ladder would lean harder on the two limits the replay leaves out — the firm's contract limit and its payout cap — rather than find a better size.

## What this is not

- **Not a gate.** It reads shortlists; it tests nothing against a null.
- **Not a ranking at the new size.** Each shortlist was chosen on the selection window at its stored size. On InsideBarTrailing the size changes the trades, so the configurations the selection window would pick at twelve contracts are not necessarily these.
- **Not inside any firm's contract limit, scaling plan or payout cap.** None is modelled for Apex or TopStep — `docs/roadmap.md` § "What is deliberately not modelled". Twenty MNQ contracts or four NQ may not be allowed on a given account, a funded account's scaling plan may hold it below that for a while, and a payout cap would trim exactly the larger withdrawals that make a larger size net more. Check each size against the firm's current rules before reading it as tradeable.
- **Not the confluence size.** §M45's one-contract-more-per-label arm still has no account read. That, and the same arm on the rest of the registry, is what remains of [#295].
- **The unfiltered stratum only**, apart from InsideBarTrailing's midday cell.

## What this settles

- **On an MNQ 50K account, three archetypes pay and the sizes they were swept at are close to right**: OpeningRange's opposite-extreme stop at four and InsideBarTrailing at four to six. InsideBar's passes stop rising at four, and above that it nets more only through larger withdrawals the replay does not cap, and more blown accounts.
- **On an MNQ 150K account the best sizes are larger**: six to twelve on Apex 150K and sixteen to twenty on TopStep 150K for the shortlists in the table, and twenty on both for InsideBar.
- **On NQ, only InsideBar pays on a 50K account, at one to three contracts**, because it is the only archetype whose bracket can be traded that small. A four-target bracket cannot be sized down onto one at all.
- **Attempts rise with almost every step up in size, and passes do not.** Read a size by the passes and attempts beside it, never by its net alone.

[#295]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/295
