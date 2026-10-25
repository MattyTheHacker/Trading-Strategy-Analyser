---
id: M54
title: "M54 — the family-wise null: no cell clears in either family, and family A is decided by EmaPullback's few-trade cells"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, SqueezeBreakout]
issues: [439]
gates: [3]
outcome: negative
verdict: >-
  Pre-registered and run on the October 2026 re-sweep: no cell clears family-wise on both roots in either family. Family B, §M28.16's ten cells, reproduces §M44's per-test counts, and its best test, OpeningRange's volume=NORMAL, reaches a family-wise p of 0.229; family A, named by the rule, grew from §M44's 25 cells to 99, and 384 of its 400 draws take their best from EmaPullback cells of 16 to 22 trades, so its smallest p of 0.187 says nothing about any other archetype.
---

# M54 — the family-wise null: no cell clears in either family, and family A is decided by EmaPullback's few-trade cells ([#439])

Pre-registered in [`m54-family-wise-null-preregistration.md`](m54-family-wise-null-preregistration.md) before any of it ran, and read here by that file's own rules, on the rows of the October 2026 re-sweep.

## In plain terms

The project's strongest test asks whether a strategy beats the same number of random entries placed under the same conditions. Run on many settings and many market conditions at once, some will pass by luck. This read corrects for that: each result is compared with the best that luck produced across the whole group of tests, not with its own luck alone.

**Nothing passes the corrected test**, in either group. That was the prediction.

The larger group turned out to be the wrong instrument. Two-thirds of its tests came from one strategy in market conditions where it traded rarely, some settings only 16 to 22 times. With so few trades a lucky run can look enormous, and those runs set a bar that nothing else in the group could reach.

## What was run

|              |                                                                                                                            |
| ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **Protocol** | both roots, 5-minute bars, the top ten per cell on the selection window by profit factor, tested on the holdout, 400 draws |
| **Rows**     | each archetype's own campaign variants, `--campaign-only`, in naming the cells and in ranking inside them                  |
| **Draw**     | random bars, and the level draw for OpeningRange                                                                           |
| **Family A** | the cells `campaign_crossread.py --campaign-only --min-score 8` names on the re-swept rows: **99 cells, 1,980 tests**      |
| **Family B** | §M28.16's ten cells: **200 tests**                                                                                         |
| **Refused**  | none, in either family                                                                                                     |

**Family A was scored on MNQ and NQ at 2, 5, 10 and 15 minutes**, which is where §M44 scored its 25. The cross-read as written scores every root and bar size a database holds, and the re-sweep added five markets and a 30-minute pass; either would have changed what a score of 8 means, so both were left out. The cells were named and written down before any null ran, and are listed in the last section.

**Why 99 and not 25.** The rule counts every cell that helps in both windows in all eight root × bar-size cells, and the re-swept databases hold strata §M44's did not: §M30's fitted regime cuts at every lookback, §M32's volume windows and the rungs below ten bars, and §M56's half-hour slots. EmaPullback has 64 of the 99, most of them fitted volume cells.

## The verdict: no cell clears

**A cell clears where, on both roots, at least one configuration has a family-wise p below 0.05.**

| family | cells | tests | smallest family-wise p | where                                                              | cells clearing |
| ------ | ----- | ----- | ---------------------- | ------------------------------------------------------------------ | -------------- |
| A      | 99    | 1,980 | 0.187                  | EmaPullback `volume=NORMAL@per_bar_20 q=0.20/0.80`, MNQ, 20 trades | none           |
| B      | 10    | 200   | 0.229                  | OpeningRange `volume=NORMAL`, MNQ, 378 trades                      | none           |

[§M27.8](m27-8-volume.md) asked whether the best of a family's cells beats the best of as many draws. In both families it does not.

## Family B, beside the earlier reads

Per test, family B reproduces [§M44](m44-registry-resweep.md) almost exactly; the family-wise column is new.

| cell                                 | root | beats its null | p < 0.05 | §M44's p < 0.05 | §M28.16's p < 0.05 | lowest family-wise p |
| ------------------------------------ | ---- | -------------- | -------- | --------------- | ------------------ | -------------------- |
| OpeningRange `volume=NORMAL`         | MNQ  | 10 of 10       | **10**   | 10              | 6                  | 0.229                |
| OpeningRange `volume=NORMAL`         | NQ   | 10 of 10       | **10**   | 9               | 10                 | 0.327                |
| OpeningRange `regime=UNCLASSIFIABLE` | MNQ  | 10 of 10       | **8**    | 8               | 9                  | 0.337                |
| OpeningRange `regime=UNCLASSIFIABLE` | NQ   | 10 of 10       | **7**    | 7               | 4                  | 0.696                |
| OpeningRange `compression=EXPANDED`  | MNQ  | 10 of 10       | **1**    | 2               | 6                  | 0.419                |
| OpeningRange `compression=EXPANDED`  | NQ   | 10 of 10       | **1**    | 0               | 2                  | 0.464                |
| InsideBarTrailing `phase=MIDDAY`     | MNQ  | 10 of 10       | **5**    | 5               | 5                  | 0.736                |
| InsideBarTrailing `phase=MIDDAY`     | NQ   | 10 of 10       | **3**    | 3               | 4                  | 0.581                |
| OpeningRange `regime=DIRECTIONAL`    | MNQ  | 10 of 10       | 0        | 0               | 0                  | 0.803                |
| OpeningRange `regime=DIRECTIONAL`    | NQ   | 9 of 10        | 0        | 2               | 0                  | 0.890                |
| DeadCatBounce `htf=BELOW`            | MNQ  | 10 of 10       | 0        | 0               | 0                  | 0.978                |
| DeadCatBounce `htf=BELOW`            | NQ   | 10 of 10       | 0        | 1               | 0                  | 0.930                |
| InsideBar `regime=UNCLASSIFIABLE`    | MNQ  | 10 of 10       | 0        | 0               | 0                  | 0.975                |
| InsideBar `regime=UNCLASSIFIABLE`    | NQ   | 10 of 10       | 0        | 0               | 0                  | 1.000                |
| OpeningRange `volume=THIN`           | MNQ  | 10 of 10       | 0        | 0               | 0                  | 0.973                |
| OpeningRange `volume=THIN`           | NQ   | 10 of 10       | 0        | 0               | 0                  | 1.000                |
| EmaCrossover `phase=CASH_OPEN`       | MNQ  | 6 of 10        | 0        | 0               | 0                  | 1.000                |
| EmaCrossover `phase=CASH_OPEN`       | NQ   | 7 of 10        | 0        | 0               | 0                  | 0.998                |
| EmaCrossover `phase=MIDDAY`          | MNQ  | 2 of 10        | 0        | 0               | 0                  | 1.000                |
| EmaCrossover `phase=MIDDAY`          | NQ   | 1 of 10        | 0        | 0               | 0                  | 1.000                |

**Four cells put a configuration below p = 0.05 on both roots one test at a time**, as three did in §M44: `compression=EXPANDED` is back, one configuration per root. InsideBarTrailing's midday cell repeats §M44's 5 and 3 exactly, as expected: the two stop fixes in the re-sweep, [#471] and [#472], do not reach InsideBarTrailing. **Family-wise, the strongest cell in the family, OpeningRange's `volume=NORMAL` with every configuration below 0.05 on both roots, reaches 0.229.** The best of each draw across the 200 tests has a median of 3.1 standard units and a 95th percentile of 4.6, and the best test reaches 3.7.

**OpeningRange's `regime=DIRECTIONAL` differs from §M44 for the reason the pre-registration gave.** The `orb` set is swept into the same stratum, and §M44's shortlist there ranked its arms beside the campaign's, at nulls of 1.66 to 2.66; this one ranks the campaign's variants only.

**The family B draws are spread across the archetypes**: the best of each of the 400 draws comes from EmaCrossover's tests 98 times, InsideBar's 95, OpeningRange's 77, DeadCatBounce's 72 and InsideBarTrailing's 58. That is the read working as designed.

## Family A: one archetype's thin cells set the bar

| archetype         | cells | tests | lowest family-wise p, MNQ | lowest family-wise p, NQ | median held-out trades per cell |
| ----------------- | ----- | ----- | ------------------------- | ------------------------ | ------------------------------- |
| EmaPullback       | 64    | 1,280 | 0.187                     | 0.973                    | 35–45                           |
| OpeningRange      | 23    | 460   | 0.950                     | 0.988                    | 144–155                         |
| ElasticBand       | 6     | 120   | 1.000                     | 1.000                    | 110–236                         |
| InsideBar         | 2     | 40    | 1.000                     | 1.000                    | 919–927                         |
| SqueezeBreakout   | 2     | 40    | 1.000                     | 1.000                    | 54–61                           |
| EmaCrossover      | 1     | 20    | 1.000                     | 1.000                    | 425–430                         |
| InsideBarTrailing | 1     | 20    | 1.000                     | 1.000                    | 590–673                         |

**384 of family A's 400 draws take their best from an EmaPullback test**, 14 from SqueezeBreakout and 2 from ElasticBand. EmaPullback's family A cells are mostly fitted volume cells holding a median of 35 to 45 held-out trades, and at 16 to 22 trades a configuration can post a profit factor of 14 to 24 against a null whose spread is small. Standardised, its best observation is 28.7, and the best of each draw has a median of 13.8. OpeningRange's best observation is 6.7. **No test outside EmaPullback's thin cells could have cleared, whatever its own evidence**: seven OpeningRange cells and one InsideBar cell put configurations below p = 0.05 on both roots one test at a time — OpeningRange's `regime=DIRECTIONAL@n=50 q=0.10/0.90` all twenty, on about 35 trades — and every one of them reads a family-wise p of 0.95 or more. Twenty of the 400 draws also hold an infinite value, a draw with no losing trade, which beats every observation.

**This is the failure the pre-registration named and accepted**: a few-trade null with a small spread takes the best of most draws, which costs every other test its power and never makes one look better. It errs in the safe direction. But it means family A answers one question — whether EmaPullback's best thin cell beats chance across 1,980 tests, and it does not — and no other.

## The predictions

- **"No cell clears family-wise on both roots, in either family." Right.**
- **"Family B's smallest family-wise p is above 0.05, and family A's is larger still, being the bigger family." Half right.** Family B's is 0.229. Family A's is smaller, 0.187, and for the reason above rather than for size.
- **"The three cells that cleared p = 0.05 on both roots in §M44 — InsideBarTrailing's `phase=MIDDAY` and OpeningRange's `volume=NORMAL` and `regime=UNCLASSIFIABLE` — hold the three lowest family-wise p-values in family B." Two of three.** By each cell's lowest family-wise p the order is OpeningRange's `volume=NORMAL` 0.229, `regime=UNCLASSIFIABLE` 0.337 and `compression=EXPANDED` 0.419, then InsideBarTrailing's midday cell at 0.581.

## What this settles, and what it does not

**Family B settles §M28.16's ten cells.** Each was chosen after a consistency score had been looked at, and none survives a correction for the 200 tests read together, including the two the project has built most on: InsideBarTrailing's midday cell and OpeningRange's `volume=NORMAL`. Their per-test results stand as they were; what fails is the claim that any one of them is more than the best of its family.

**Family A settles nothing beyond EmaPullback.** A family is only as fair as its scale. Standardising each test by its own null's spread puts busy and thin cells on one axis, and here the thin cells' spreads were small enough that their lucky draws dwarfed everything else. A family read over cells this unequal needs either a trade floor on its members or one family per archetype, as [§M56](m56-session-slots-result.md) used; neither is what was pre-registered, and neither is applied here.

**Nothing here is a new gate 3.** Every per-test p is the one gate 3 already reports, and §M56's slot result, read under one family per archetype, is not touched by this.

## How it was read

- **Family A named.** `campaign_crossread`'s own scoring under `--campaign-only --min-score 8`, restricted to MNQ and NQ at 2, 5, 10 and 15 minutes, written to a list before any null ran.
- **Each archetype's tests.** `campaign_null.py --strategy <archetype> --stratum <its cells> --campaign-only --root MNQ NQ --resolution 5 --window selection --test-window holdout --top 10 --iterations 400`, with `--draw levels` for OpeningRange, one archetype at a time.
- **Each family.** `campaign_null.py --family-of` over that family's saved tables; the per-cell counts and which test took each draw's best were read from the same tables through `campaign_null.family_wise` and `randomentry.standardised_excess`.

## Family A's cells

As named before the nulls ran, 99 in all.

- **EmaCrossover** (1): `phase=MIDDAY`.
- **EmaPullback** (64): `phase=MIDDAY`, `regime=DIRECTIONAL`, `regime=DIRECTIONAL@n=10 q=0.20/0.80`, `regime=DIRECTIONAL@n=20 q=0.20/0.80`, `regime=DIRECTIONAL@n=30 q=0.20/0.80`, `regime=DIRECTIONAL@n=5 q=0.20/0.80`, `regime=DIRECTIONAL@n=50 q=0.20/0.80`, `slot=1030`, `slot=1100`, `slot=1130`, `slot=1230`, `slot=1300`, `slot=1330`, `trend=UP`, `volume=NORMAL`, `volume=NORMAL@per_bar_10 q=0.10/0.90`, `volume=NORMAL@per_bar_10 q=0.20/0.80`, `volume=NORMAL@per_bar_10 q=0.33/0.67`, `volume=NORMAL@per_bar_20 q=0.10/0.90`, `volume=NORMAL@per_bar_20 q=0.20/0.80`, `volume=NORMAL@per_bar_20 q=0.33/0.67`, `volume=NORMAL@per_bar_40 q=0.10/0.90`, `volume=NORMAL@per_bar_40 q=0.20/0.80`, `volume=NORMAL@per_bar_40 q=0.33/0.67`, `volume=NORMAL@rolling_10_20 q=0.10/0.90`, `volume=NORMAL@rolling_10_20 q=0.20/0.80`, `volume=NORMAL@rolling_2_20 q=0.10/0.90`, `volume=NORMAL@rolling_2_20 q=0.20/0.80`, `volume=NORMAL@rolling_2_20 q=0.33/0.67`, `volume=NORMAL@rolling_30_10 q=0.20/0.80`, `volume=NORMAL@rolling_30_10 q=0.33/0.67`, `volume=NORMAL@rolling_30_20 q=0.10/0.90`, `volume=NORMAL@rolling_30_20 q=0.20/0.80`, `volume=NORMAL@rolling_30_40 q=0.20/0.80`, `volume=NORMAL@rolling_30_40 q=0.33/0.67`, `volume=NORMAL@rolling_3_20 q=0.10/0.90`, `volume=NORMAL@rolling_3_20 q=0.20/0.80`, `volume=NORMAL@rolling_5_20 q=0.10/0.90`, `volume=NORMAL@rolling_5_20 q=0.20/0.80`, `volume=NORMAL@rolling_7_20 q=0.10/0.90`, `volume=NORMAL@rolling_7_20 q=0.20/0.80`, `volume=NORMAL@rolling_90_20 q=0.10/0.90`, `volume=NORMAL@session_to_date_10 q=0.10/0.90`, `volume=NORMAL@session_to_date_10 q=0.20/0.80`, `volume=NORMAL@session_to_date_20 q=0.10/0.90`, `volume=NORMAL@session_to_date_20 q=0.20/0.80`, `volume=NORMAL@session_to_date_40 q=0.10/0.90`, `volume=NORMAL@session_to_date_40 q=0.20/0.80`, `volume=THIN@per_bar_10 q=0.20/0.80`, `volume=THIN@per_bar_10 q=0.33/0.67`, `volume=THIN@per_bar_20 q=0.33/0.67`, `volume=THIN@per_bar_40 q=0.33/0.67`, `volume=THIN@rolling_2_20 q=0.33/0.67`, `volume=THIN@rolling_30_10 q=0.33/0.67`, `volume=THIN@rolling_3_20 q=0.33/0.67`, `volume=THIN@rolling_5_20 q=0.33/0.67`, `volume=THIN@rolling_7_20 q=0.20/0.80`, `volume=THIN@rolling_7_20 q=0.33/0.67`, `volume=THIN@rolling_90_20 q=0.33/0.67`, `volume=THIN@session_to_date_10 q=0.10/0.90`, `volume=THIN@session_to_date_10 q=0.20/0.80`, `volume=THIN@session_to_date_10 q=0.33/0.67`, `volume=THIN@session_to_date_20 q=0.33/0.67`, `volume=THIN@session_to_date_40 q=0.33/0.67`.
- **InsideBar** (2): `regime=UNCLASSIFIABLE`, `volume=NORMAL@rolling_10_20 q=0.20/0.80`.
- **InsideBarTrailing** (1): `regime=UNCLASSIFIABLE`.
- **ElasticBand** (6): `phase=PRE_OPEN`, `regime=UNCLASSIFIABLE@n=50 q=0.20/0.80`, `volume=HEAVY@per_bar_40 q=0.10/0.90`, `volume=HEAVY@rolling_30_10 q=0.20/0.80`, `volume=HEAVY@rolling_30_20 q=0.10/0.90`, `volume=HEAVY@rolling_30_40 q=0.20/0.80`.
- **OpeningRange** (23): `phase=MIDDAY`, `regime=DIRECTIONAL`, `regime=DIRECTIONAL@n=10 q=0.10/0.90`, `regime=DIRECTIONAL@n=10 q=0.20/0.80`, `regime=DIRECTIONAL@n=10 q=0.33/0.67`, `regime=DIRECTIONAL@n=20 q=0.10/0.90`, `regime=DIRECTIONAL@n=20 q=0.20/0.80`, `regime=DIRECTIONAL@n=20 q=0.33/0.67`, `regime=DIRECTIONAL@n=30 q=0.10/0.90`, `regime=DIRECTIONAL@n=30 q=0.20/0.80`, `regime=DIRECTIONAL@n=30 q=0.33/0.67`, `regime=DIRECTIONAL@n=5 q=0.33/0.67`, `regime=DIRECTIONAL@n=50 q=0.10/0.90`, `regime=DIRECTIONAL@n=50 q=0.20/0.80`, `regime=DIRECTIONAL@n=50 q=0.33/0.67`, `regime=UNCLASSIFIABLE`, `slot=1000`, `slot=1030`, `slot=1100`, `slot=1130`, `slot=1300`, `trend=UP`, `volume=NORMAL@session_to_date_40 q=0.10/0.90`.
- **SqueezeBreakout** (2): `regime=DIRECTIONAL@n=10 q=0.20/0.80`, `regime=DIRECTIONAL@n=20 q=0.20/0.80`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#471]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/471
[#472]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/472
