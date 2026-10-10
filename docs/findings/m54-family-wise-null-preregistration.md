---
title: "M54 — pre-registration: a family-wise null over the consistent cells"
archetypes: [DeadCatBounce, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange]
issues: [439]
gates: [3]
outcome: spec
verdict: >-
  Written and committed before any of it ran: gate 3's matched null read family-wise, each test's standardised profit-factor excess against the best of every draw across its family, over two families — §M44's consistent cells, named by the cross-read on the re-swept rows, and §M28.16's ten cells — each read on its own, with both chosen and ranked from each archetype's own campaign variants; a cell clears where, on both roots, a configuration reaches a family-wise p below 0.05.
---

# M54 — pre-registration: a family-wise null over the consistent cells ([#439])

Gate 3 places each configuration against its own matched random entry and reports that test's p. Its families are large — §M28.16's was 200 tests over cells chosen after a consistency score had been looked at — and nothing reads them as a family. [§M28.16](m28-16-consistent-cells.md) found the obvious correction untestable: a Bonferroni threshold over its twenty cells is 0.0025, and 400 draws cannot produce a p below 1/401. [§M27.8](m27-8-volume.md) left the other half open: whether the best of a family's cells beats the best of as many draws.

This adds that read. **Each test is measured against the best of every draw across its family**, which needs no more draws than gate 3 already takes, and [§M44](m44-registry-resweep.md)'s own next step — a pre-registered family over the cells it found consistent — is the first family it reads.

**This file was written and committed before any of it ran.** The read, the families, the rows they come from, the bar and the predictions were all chosen first.

## The read

For each test — one configuration in one cell on one root — gate 3 keeps every profit-factor draw of its matched null, in seed order. Then:

1. **Standardise.** The test's excess over its null median, divided by the null's robust spread: 1.4826 times the median absolute deviation of its finite draws, which is a standard deviation for normal data. Every draw is scaled the same way. This is what makes a few-trade cell with a wide null comparable with a busy one; raw profit-factor excess would let the widest null dominate. A few-trade null whose draws take only a handful of values can have a very small spread instead, and its draws then take the best of most draws: that costs the other tests power and never makes one look better.
2. **Take the best of each draw.** For draw *j*, the largest standardised value across every test in the family.
3. **The family-wise p** of a test is the share of draws whose best reached its own standardised excess, one-sided, with gate 3's add-one correction. The family's answer is its smallest one. Gate 3's own p is two-sided, so a lone test's family-wise p can come out below it; the two are reported side by side and labelled.

**Every test seeds its draw *j* from the same seed**, so the draws line up: tests on the same bars share randomness, and tests on different bars do not. Where tests move together more than their draws do, the family-wise p comes out larger than it needs to be, never smaller. **A draw with no losing trade has an infinite profit factor and beats every observation**, which also errs large; a draw a test could not define is skipped for that test. A test the null refused, or whose null has no spread to scale by, is left out of the family and named.

**Ten configurations of one cell are not ten independent tests**, as §M44 says. The best of each draw is taken over all of them, so overlap makes the read cautious rather than generous.

`tools/campaign_null.py` reports it beside every test's own p, one run at a time, and over several saved runs as one family — `tools/README.md` § "campaign_null.py".

## The rows both families come from

**Each archetype's own campaign variants, and no later set's.** Once every stored campaign is re-swept, each database also holds later sets — sizing arms, structure trails, early exits — under the same stratum names, so InsideBarTrailing's `phase=MIDDAY` holds §M49's structure-trail arms beside the campaign's. Both the cross-read that names the cells and the shortlist inside each cell read the campaign's variants only: `--campaign-only` on both tools. Where §M28.16's strata held other sets' rows, its shortlist ranked them as well, so a cell here can differ from §M28.16's for that reason alone.

## What will be run

Both families run on the rows the planned re-sweep of every stored campaign writes, under one protocol, which is §M28.16's and §M44's: **both roots, 5-minute bars, ranked on the selection window by profit factor, the top ten per cell, tested on the holdout, 400 draws**, and OpeningRange's cells under the level draw (§M28.2). One run per archetype, each saved, then one family read over the saved runs:

```bash
uv run tools/campaign_null.py --strategy <archetype> --stratum <its cells> --campaign-only \
    --root MNQ NQ --resolution 5 --window selection --test-window holdout --top 10 \
    --iterations 400 [--draw levels] --out <its table>
uv run tools/campaign_null.py --family-of <every table of the family>
```

### Family A — §M44's consistent cells

**Named by the rule, not by a list**, because §M44 found the membership moves when the data does:

```bash
uv run tools/campaign_crossread.py --campaign-only --min-score 8
```

The cells it names on the re-swept rows are the family, whatever their number. The list is recorded with the result before any null runs. At §M44's 25 cells this is 500 tests.

### Family B — §M28.16's ten cells

| archetype         | cells                                                                                                 | draw   |
| ----------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| EmaCrossover      | `phase=CASH_OPEN`, `phase=MIDDAY`                                                                     | bars   |
| InsideBarTrailing | `phase=MIDDAY`                                                                                        | bars   |
| InsideBar         | `regime=UNCLASSIFIABLE`                                                                               | bars   |
| DeadCatBounce     | `htf=BELOW`                                                                                           | bars   |
| OpeningRange      | `compression=EXPANDED`, `regime=UNCLASSIFIABLE`, `volume=THIN`, `regime=DIRECTIONAL`, `volume=NORMAL` | levels |

10 cells × 2 roots × 10 configurations = 200 tests, the family §M28.16 and §M44 read one test at a time.

**The two families are read separately**, each its own family-wise null. They share cells, and pooling them would count those tests twice, which the tool refuses.

## What will be read

1. **Every test's family-wise p beside its own p**, and per cell the lowest family-wise p on each root, beside §M28.16's counts — configurations beating their null and below p = 0.05 — so the result reads against the earlier ones.
2. **A cell clears family-wise where, on both roots, at least one of its configurations has a family-wise p below 0.05.**
3. **A family's answer is its smallest family-wise p**: whether its best test beats the best of chance across the whole family.
4. **A refused test is named and left out**, and the family's size is stated as the number of tests actually measured.
5. **Nothing is added, dropped or re-cut after the first run.** A family A cell the cross-read names is run whatever it holds.

## Predicted before the run

- **No cell clears family-wise on both roots, in either family.** The smallest single p §M28.16 measured in family B was 0.005, two draws in 400, which is about the smallest of 200 p-values by chance alone.
- **Family B's smallest family-wise p is above 0.05**, and family A's is larger still, being the bigger family.
- **The cells keep their order**: the three cells that cleared p = 0.05 on both roots in §M44 — InsideBarTrailing's `phase=MIDDAY` and OpeningRange's `volume=NORMAL` and `regime=UNCLASSIFIABLE` — hold the three lowest family-wise p-values in family B.

## What this run is not

- **Not a fix for how the cells were chosen.** Family A is named by a consistency score, and the read counts every cell that score names; the score itself was still chosen by looking, and neither family undoes that.
- **Not a new gate 3.** Every per-test p is the one gate 3 already reports; this adds a column, not a different null.
- **Not the other bar sizes, or gate 4.** 5 minutes only, as both earlier reads.
- **Not a ranking.** A family-wise p says which tests survive the family, not which configuration to trade.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
