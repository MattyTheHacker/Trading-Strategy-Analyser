---
id: M28.14
title: "M28.14 — every stratum against its unfiltered twin, and the cell that survives it"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [285]
gates: [3]
outcome: mixed
verdict: >-
  The clock separates the registry while volume and trend mostly do not; the midday cell clears four gates and the flatten is still what earns it.
---

# M28.14 — every stratum against its unfiltered twin, and the cell that survives it ([#285])

**No new sweep.** §M27 and §M27.4 stored twenty context strata per archetype on both split windows, and §M27.7 recorded that nobody had read the phase rows; §M27.8 said the same of volume. `tools/campaign_report.py` reads them as distributions and `tools/campaign_holdout.py` reads a *shortlist* out of them, which measures selection as much as strategy. This is the paired read neither does: **for the same parameters, does pinning one context filter on beat leaving it off?**

Every filtered row has an unfiltered twin at identical parameters, root, resolution and variant, so the difference is a matched pair and the shortlist-size bias § "The build spec's three loose ends, measured" records cannot enter. `tools/campaign_crossread.py` is the read.

## The score, and what it is not

Each pair is measured in **both** windows independently. A cell is one `root x resolution`, ten per stratum, and the score is the cells the filter won in both windows minus the cells it lost in both — so +10 is a filter that helped everywhere twice and −10 one that hurt everywhere twice. A cell that wins one window and loses the other counts for neither side, which is the point: the two windows are disjoint spans and agreeing across them is the claim.

**Pairing happens inside a resolution and the counting only then crosses them.** Bar size is the largest lever in the campaign, so a cell of one size is never a twin of another — and that is also what makes the cross-archetype comparison legitimate where §M27.5 and §M27.8 say the cross-resolution one is not. The volume and regime strata are cut by the raw pairs those sections show are a different cut at every bar size; at a fixed `(root, resolution)` every archetype is cutting the same bars the same way, so the archetypes can be read against each other even though the resolutions cannot.

**A score is a consistency check and not a p-value.** Ten cells are two roots tracking one index at five overlapping bar sizes, nowhere near independent, and about 142 archetype × stratum rows were scanned. Binomial arithmetic over the cells overstates it badly. Only a matched null carries evidence, which is why two cells below were taken to one.

## Two defects the read had to avoid, and the second changed an answer

- **`combo_id` cannot be the join key.** `campaign_holdout` pairs the *same* stratum across two windows and equal ids are equal parameters there. Across two strata they are not: a sweep concatenates its strata into one `combos` block, so `phase=LONDON` starts at 432 where `unfiltered` starts at 0. The join is on the parameters, minus the ones a stratum exists to move — and those are read out of `STRATUM_GROUPS` rather than listed, so a dimension added later cannot leave a column behind in the key.
- **A stratum run by a later campaign carries that campaign's variants.** OpeningRange's `regime=CONSOLIDATING` holds 27, including the fade and rejection arms only the reversion campaigns ran, where every other stratum holds the 12 breakout arms. Confined to the 12 they share, `regime=CONSOLIDATING` moves from **+7 to −10** — a breakout archetype scoring well in chop was the fade variants wearing the regime's name.

## The clock separates the registry; volume and trend mostly do not

Session phase, cells won in both windows minus cells lost in both. `--` is structurally impossible rather than untested: InsideBar's `no_entry_minutes_before_close` is the `CLOSE` hour and a cash-anchored range cannot arm before 09:30, both as §M27.7 records.

| phase     | DeadCatBounce | PullBackAndGo | EmaCrossover | InsideBar | InsideBarTrailing | ElasticBand | OpeningRange |
| --------- | ------------- | ------------- | ------------ | --------- | ----------------- | ----------- | ------------ |
| OVERNIGHT | 2             | −3            | −1           | −5        | −4                | −2          | --           |
| LONDON    | −1            | −2            | **−9**       | −2        | −5                | 5           | --           |
| PRE_OPEN  | 1             | 0             | −5           | −7        | −5                | **9**       | --           |
| CASH_OPEN | 2             | 3             | **10**       | 0         | 0                 | −7          | −1           |
| MIDDAY    | 2             | 7             | **10**       | 6         | **10**            | −6          | **10**       |
| AFTERNOON | 4             | 2             | −4           | 1         | 3                 | 4           | −4           |
| CLOSE     | −2            | −3            | **−8**       | --        | −2                | −2          | **−8**       |

**EmaCrossover and ElasticBand are near-perfect mirrors of each other**, which is the cleanest cross-strategy structure in the read: momentum wants the US cash session and mean reversion wants the quiet hours before it. **`CLOSE` is negative for all seven**, at a `session_close_share` of 0.64–0.84 for everything that holds a position — the flatten arriving as a result rather than an hour with a character of its own, §M27.7's finding from the other side.

**The midday lull is the best phase for the breakout family, and for OpeningRange that is not structural.** It takes *more* trades in `CASH_OPEN` than in `MIDDAY` — 393 against 234 at 5 minutes, 302 against 212 at 15 — and loses with them. The immediate break is the losing one.

The higher-timeframe side sorts the registry by what each archetype is, and does it far more cleanly than the compact trend label:

| side  | DeadCatBounce | PullBackAndGo | EmaCrossover | InsideBar | InsideBarTrailing | ElasticBand | OpeningRange |
| ----- | ------------- | ------------- | ------------ | --------- | ----------------- | ----------- | ------------ |
| ABOVE | **−7**        | 2             | −2           | 1         | 4                 | −1          | **7**        |
| BELOW | **9**         | −1            | 2            | −3        | 0                 | 2           | **−7**       |

DeadCatBounce is short-only and OpeningRange takes one side per combination; split by side, **OpeningRange traded long is +10 above the average and −10 below it**. `htf=AT` has no row at all, as §M27.4 already established.

**Relative volume is close to inert everywhere but OpeningRange**, whose `THIN` is +9 and +8 on the short side alone; no other archetype's volume dimension reaches ±8 except ElasticBand's `NORMAL` at −8. Read that against §M27.8 rather than as a fact about volume: every row is the raw per-bar 0.7/1.5 pair, and which state helps is decided by the form and the cut.

**`regime=UNCLASSIFIABLE` — the middle band, not a warm-up state — is the best regime cell for four of the seven**: +10 OpeningRange, +8 InsideBar, +7 InsideBarTrailing, +5 ElasticBand. Only OpeningRange prefers `DIRECTIONAL`, at +8 and the largest paired delta in the table.

## Two cells taken to a matched null, and they do not agree

`tools/campaign_null.py`, ranked on the selection window and tested on the holdout, 400 draws, top ten, 5-minute bars.

| cell                         | root | draw   | trades  | profit factor | null        | excess          | p < 0.05     | net/drawdown |
| ---------------------------- | ---- | ------ | ------- | ------------- | ----------- | --------------- | ------------ | ------------ |
| OpeningRange `phase=MIDDAY`  | MNQ  | levels | 240–246 | 1.142–1.296   | 0.907–0.954 | +0.188 – +0.380 | **9 of 10**  | 1.07–2.26    |
| OpeningRange `phase=MIDDAY`  | NQ   | levels | 235–240 | 1.237–1.332   | 0.922–0.946 | +0.311 – +0.395 | **10 of 10** | 1.85–2.47    |
| ElasticBand `phase=PRE_OPEN` | MNQ  | bars   | 38–220  | best 1.179    | 0.844–0.960 | best +0.335     | 0 of 10      | up to 0.47   |
| ElasticBand `phase=PRE_OPEN` | NQ   | bars   | 39–234  | best 1.468    | 0.876–1.045 | best +0.488     | 0 of 10      | up to 1.70   |

**The over-bars draw refuses OpeningRange outright even inside the phase stratum** — 20,129 signals leaving 0.0019 spare bars each — so the null is `--draw levels`, the arm §M28.2 built for exactly this. **ElasticBand's pre-open is positive and underpowered**: 16 of 20 configurations beat their own null and not one clears p = 0.05, smallest 0.239. At 15 minutes, where its paired effect is strongest, the shortlist rebuilds to 17 holdout trades and is below the floor.

## The midday cell clears four gates and the flatten is still what earns it

`ambiguous_share` is 0.004 on both roots, so none of it sits in the corner §M28.7 found. The holdout runs 2024-09 to 2026-08 and therefore already contains the collapse §M28.10 measured. Profit factor by year, top five configurations by selection profit factor run over the whole spliced series — 2022–2024 is in-sample, 2025 and 2026 are not, and 2021 is a coverage boundary at 32 trades on MNQ and 5 on NQ:

| root | config | 2022  | 2023  | 2024  | 2025  | 2026      | flat share |
| ---- | ------ | ----- | ----- | ----- | ----- | --------- | ---------- |
| MNQ  | 0      | 1.294 | 1.427 | 1.200 | 1.425 | **1.026** | 0.47       |
| MNQ  | 1      | 1.310 | 1.685 | 1.101 | 1.520 | 1.208     | 0.67       |
| MNQ  | 2      | 1.230 | 1.846 | 1.083 | 1.507 | 1.135     | 0.78       |
| NQ   | 0      | 1.223 | 1.884 | 1.227 | 1.525 | 1.119     | 0.78       |
| NQ   | 1      | 1.300 | 1.714 | 1.221 | 1.540 | 1.198     | 0.67       |

§M28.10's control returns **1.008 on MNQ and 1.002 on NQ in 2026**, and none of its nine follow-through scaling arms moved it by more than 0.03. The midday restriction moves it to 1.026–1.208 and 1.112–1.198 — a real improvement on the thing nine arms could not shift, and **still nowhere near the 1.43–1.88 the same configurations posted in 2023**. 2026 also carries the largest drawdown of any year on both roots, and the *highest-ranked* MNQ configuration is the weakest of the five in it.

The exit decomposition reproduces §M28.12 inside the cell. Holdout window, net P&L by exit reason:

| root | config | session close | stop     | target   | bracket  | total net |
| ---- | ------ | ------------- | -------- | -------- | -------- | --------- |
| MNQ  | 1      | +57,256       | −66,531  | +34,073  | −32,458  | +24,798   |
| MNQ  | 2      | +78,476       | −68,542  | +11,078  | −57,464  | +21,011   |
| NQ   | 0      | +783,929      | −659,178 | +102,961 | −556,217 | +227,712  |

**The bracket is a net cost and the flatten is the whole result**, median hold 66–67 bars. So the midday filter does not fix the bracket §M27.3 and §M28.12 both diagnose; it improves entry timing enough that a flatten-carried result clears the gates. What the cell actually describes is "break the midday range and hold to the close", and its profit centre is an account rule that cannot be widened, delayed or switched off — § "Flat before the session close".

## What the pairing does not settle

- **Nothing here is re-ranked and nothing is retired.** The stored rows are §M27's, §M27.4's and §M28's, unchanged; what is new is the pairing.
- **Beating your own unfiltered twin is not making money.** `compression=EXPANDED` scores +10 for OpeningRange at a median holdout profit factor of 0.978, and `htf=BELOW` scores +9 for DeadCatBounce at 0.909.
- **Ten of the twelve consistent helpers have never been through gate 3.** EmaCrossover's two +10 phases and InsideBarTrailing's are the largest of them.
- **The phase result after 14:00 is contaminated by the forced flat** at 0.28–0.84 of legs, and the clock closing a position entered earlier is a hold-time × bar-size property rather than a property of the hour — §M27.7.
- **The six archetypes that are not InsideBar still have volume and regime strata cut once, raw.** §M27.8 left that as a flag rather than a change, and the near-inertness above is a reason to spend it.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_crossread.py` and `tools/campaign_null.py` — not a standing property.

[#285]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/285
