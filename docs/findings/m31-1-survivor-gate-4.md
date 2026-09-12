---
id: M31.1
title: "M31.1 — the gate-3 survivor through gate 4, and the hold cap inside its own stratum"
archetypes: [OpeningRange]
issues: [302]
gates: [4]
outcome: mixed
verdict: >-
  The walk-forward passes on both roots and the account funds on MNQ, but not one of the twenty configurations is profitable without its session-close legs and a hold cap does not substitute for them — every rung that binds tightly is a cost, exactly as §M29 found unfiltered.
---

# M31.1 — the gate-3 survivor through gate 4, and the hold cap inside its own stratum ([#302])

§M31 left **OpeningRange `regime=DIRECTIONAL@n=20 q=0.20/0.80`** as the only cell in the registry to clear p = 0.05 on all ten configurations of both roots, and left two things about it unmeasured: it had been through no part of gate 4, and §M29's hold ladder had never been run inside a stratum. [#302] stated both before either ran.

Both roots, 5-minute bars, the ten configurations the selection window ranked highest, read on the holdout — the pair §M31's gate 3 used.

## The shortlist had to be restricted, and that is a trap rather than a choice

**Sweeping `--variants hold` into this stratum changed what a later shortlist of it returns.** The hold arms land in the same `(root, resolution, stratum)` cell as the campaign rows, so a top-ten taken after the sweep is drawn from `hold=0`, `hold=5` … `hold=80` *and* the campaign grid — 4,032 rows where there were 576. Read that way the exclusion below reports 4 of 10 surviving, and the four are all `hold=80` arms: a cap at 80 bars converts 160 of the 400 session-close legs into hold-cap exits, so excluding `session_close` removes fewer legs. **Same positions, different door, and the read says nothing about the cell §M31 tested.**

Every figure below is therefore taken with `--variant "window=30m stop=opposite target=R"`, which is **§M31's gate-3 shortlist exactly on MNQ (10 of 10) and nine of its ten on NQ**, the tenth being a `target=width` row. §M31's own numbers are unaffected — they were measured before these rows existed — but a re-run of `tools/campaign_null.py` over this stratum today would not reproduce them without the same restriction.

## Gate 4, one read at a time

### The exclusion read: nothing survives it, on either root

`tools/campaign_exits.py`, the held-out book with the `session_close` legs removed:

| root | median profit factor | without those legs | median net | without those legs | profitable without them |
| ---- | -------------------- | ------------------ | ---------- | ------------------ | ----------------------- |
| MNQ  | 1.430                | **0.238**          | +17,642    | **−21,611**        | **0 of 10**             |
| NQ   | 1.462                | **0.244**          | +179,016   | **−205,387**       | **0 of 10**             |

**Twenty of twenty configurations are profitable with the forced flat and none is without it.** §M28.15 measured the midday cell at 1.216 → 0.371 and 0 of 40; this cell is stronger on gate 3 and **weaker here** — 1.43 → 0.24, and net-to-drawdown from +3.3 to −1.04. The cell that best beats a random entry is the cell that leans hardest on the account rule.

It is a decomposition and not a counterfactual: those positions would have left some other way, and the next section is what happens when they are actually made to.

### Monte Carlo: the sample cannot exclude a loss

`tools/campaign_montecarlo.py --held-out`, 1,000 bootstrap resamples of each configuration's own trades:

| root | profit factor 5th percentile | above 1.0 | net 5th percentile above zero | resamples that lose money |
| ---- | ---------------------------- | --------- | ----------------------------- | ------------------------- |
| MNQ  | 0.856–1.017                  | 1 of 10   | 1 of 10                       | 4.2%–15.3%                |
| NQ   | 0.897–0.941                  | 0 of 10   | 0 of 10                       | 7.0%–10.1%                |

**One configuration in twenty has a bootstrap 5th percentile above a profit factor of 1.0.** That is the same verdict §M28.15 reached on the midday cell and the same one `docs/findings/README.md` already carries for the registry: about one resample in ten of a configuration's own trades loses money.

### Walk-forward: passes on both roots, on thin folds

`tools/campaign_walkforward.py`, five sliding folds, selection on train and measurement on test:

| root | train median | test median | **pooled test** | folds profitable | distinct combos chosen | passes |
| ---- | ------------ | ----------- | --------------- | ---------------- | ---------------------- | ------ |
| MNQ  | 1.441        | 1.365       | **1.439**       | 4 of 5           | 3                      | yes    |
| NQ   | 1.497        | 1.414       | **1.459**       | 4 of 5           | 2                      | yes    |

The losing fold is the same one on both roots — the window ending 2025-03, at 0.886 and 0.801 — and every fold holds **22 to 37 test trades**, which is the read's real limit. Against §M28.15's midday cell this is a slightly better selection (3 and 2 distinct configurations against that cell's 1 on NQ) at a slightly lower pooled profit factor.

### The prop-account replay: funds on MNQ, and only TopStep 150K on NQ

`tools/campaign_propaccount.py`, four contracts, attempts uncapped, medians across the ten:

| root | preset          | attempts | passes |         fees |               net | ever passed | net > 0 |
| ---- | --------------- | -------: | -----: | -----------: | ----------------: | ----------: | ------: |
| MNQ  | Apex 50K        |       18 |      2 |        6,439 |            +5,088 |        100% |     90% |
| MNQ  | Apex 150K       |        4 |      1 |        8,149 |              +938 |        100% |     50% |
| MNQ  | TopStep 50K     |       31 |      2 |        2,699 |              +772 |        100% |     80% |
| MNQ  | TopStep 150K    |        3 |      1 |        4,023 |            +4,129 |        100% |    100% |
| NQ   | TopStep 150K    |       74 |      2 |       12,516 |           +27,332 |        100% |    100% |
| NQ   | the other three |  107–111 |      0 | 5,537–32,967 | −5,537 to −32,967 |          0% |      0% |

**Every MNQ preset funds and the NQ rows reproduce §M28.13's arithmetic exactly** — 31 points of room under a trailing threshold at four NQ contracts, and only the 150K account has enough. What is new is the size: the midday cell's MNQ medians are +9,919 to +26,982 where this cell's are **+772 to +5,088**. It passes more cheaply and earns far less.

## The hold ladder inside the stratum: §M29 reproduces, and the substitution does not happen

§M29's ladder unchanged — `HOLD_BARS = (0, 5, 10, 20, 40, 80)`, uncapped as control — swept over `--strata directional --regime-quantiles` at 5 minutes, 34,560 combinations in 8.6 minutes. 288 pairs per cell, `bound` = 1.000 at every rung, so nothing failed to fire.

The survivor cell, held out, paired cell by cell:

| rung | minutes | MNQ delta  | NQ delta   | share improved | p (MNQ / NQ)  |
| ---- | ------- | ---------- | ---------- | -------------- | ------------- |
| 5    | 25      | **−0.216** | **−0.223** | 0.13 / 0.15    | 0.000 / 0.000 |
| 10   | 50      | −0.111     | −0.112     | 0.27 / 0.31    | 0.000 / 0.000 |
| 20   | 100     | −0.078     | −0.081     | 0.32 / 0.37    | 0.000 / 0.000 |
| 40   | 200     | +0.001     | −0.006     | 0.51 / 0.47    | 0.860 / 0.316 |
| 80   | 400     | −0.007     | −0.007     | 0.22 / 0.21    | 0.000 / 0.000 |

**Monotone in how tight the cap is, and every rung that binds meaningfully is a cost** — which is §M29's finding arriving inside a stratum where the forced flat takes most of the legs. The hypothesis [#302] stated is refuted: a cap tight enough to *replace* the session close, at 25 to 100 minutes, is the worst thing that can be done to this cell.

**On the selection window every rung is a cost, the 200-minute one included** — −0.048 and −0.058, improving 4.5% of pairs. So selection would never pick the rung whose holdout delta is zero, which is §M29's "the selection window picks a paying rung zero times in seven" reproducing here.

Across the four lookbacks that carried no gate-3 result the 200-minute rung is a small positive — +0.013 to +0.027, significant on both roots at n=30 and n=50 — against the −0.10 to −0.22 of the tight rungs. **It is a rung that barely binds in a 390-minute session**, and it is not positive in the one cell that passed gate 3.

## What [#302] asked, answered

1. **Gate 4 is mixed and the exclusion read is the one that decides it.** Walk-forward passes on both roots and the account funds on MNQ; not one of twenty configurations is profitable without its session-close legs, and one in twenty has a bootstrap floor above a profit factor of 1.0.
2. **A hold cap does not substitute for the forced flat.** Every rung that binds tightly costs profit factor on both roots, and selection picks none of them.
3. **So the strongest gate-3 result in the registry is still not a recommendation**, and it is a weaker candidate for trading than the midday cell it beats on gate 3 — lower prop-account net, the same bootstrap verdict, and a harder failure on the exclusion.

## What this does not settle

- **The exclusion is a decomposition, not a counterfactual.** Removing the session-close legs does not say what those positions would have done with some other exit; the hold ladder is the nearest thing to an answer and it says "worse".
- **What has never been tried is a *conditional* exit before the close.** §M29 and this section both test an unconditional bar count. A rule that closed only losing positions early, or that tightened as the session aged, is a different object and is untested — `docs/findings/README.md` names the lever and neither campaign has built it.
- **The folds are thin.** 22 to 37 test trades per fold is where a pooled 1.44 comes from, and five folds on one stratum at one bar size is not a walk-forward of the archetype.
- **Nothing here re-runs gate 3.** §M31's null stands as measured; this adds gate 4 beside it and does not revisit the family or its size.
- **The hold ladder ran at one resolution.** 5 minutes only, because that is the cell's bar size — so "40 bars" here is 200 minutes and nothing about the ladder at other resolutions is measured or implied. §M29 is the read that spans them.
- **`--variants hold` is now in this stratum permanently.** Any later shortlist of `regime=DIRECTIONAL@n=* q=0.20/0.80` needs `--variant` to mean what §M31's did.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_sweep.py`, `tools/campaign_hold.py`, `tools/campaign_exits.py`, `tools/campaign_montecarlo.py`, `tools/campaign_walkforward.py` and `tools/campaign_propaccount.py` — not a standing property.

[#302]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/302
