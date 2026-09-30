---
title: "M47 — pre-registration: the confluence size on every archetype"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, EmaPullback, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo, SqueezeBreakout]
issues: [295]
gates: [1, 2, 3, 4]
outcome: spec
verdict: >-
  Written before any arm runs: one contract per leg more per favourable label, and one fewer per opposing label where the base can shed one, on every archetype at 2, 5, 10 and 15 minutes in every stratum; an arm clears gate 3 in a cell if k of its 20 held-out configurations beat their own sizes shuffled at p ≤ 0.05 on both roots, with k set by Bonferroni over the family the cell belongs to — 6 for the all-labels arms unfiltered, 7 for each label alone, 5 for InsideBarTrailing's midday cell and 8 in the other strata; gate 4 and the prop replay are read, not tested.
---

# M47 — pre-registration: the confluence size on every archetype ([#295])

**This file is written before the campaign it describes runs.** No §M47 arm is stored anywhere at the time of writing. The cuts every arm reads are fitted on the selection window alone and recorded below before the sweep starts. The point is the one `docs/findings/gold-strata-preregistration.md` makes: commit to the bar before looking.

## What is already known, and so cannot be predicted

| established before this run                                                                                                                         | where                                                  |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| In InsideBarTrailing's midday cell at five minutes, the confluence size beats its own sizes shuffled on 20 of 20 MNQ and 17 of 20 NQ configurations | `docs/findings/m45-ibt-sizing-result.md`               |
| Which of its four labels carries that, and how it behaves in an account, were not measured                                                          | the same file, § "The confluence size clears its null" |
| Outside InsideBarTrailing a size moves only the dollars, at every rung, on real data                                                                | `docs/findings/m46-registry-size-ladder.md`            |
| A bracket cannot trade below one contract per leg, so every four-target archetype starts at four                                                    | the same file                                          |

So **outside InsideBarTrailing a confluence size can only reweight the trades the control already takes.** Its profit factor moves only through which trades carry more contracts, which makes shuffling its sizes across its own trades an exact null. On InsideBarTrailing a size also moves trades, through the `-200` gate, so its null stays §M45's re-simulated one.

## The rules

`docs/nt8-fidelity.md` §M47 carries them and the C# each would be. In short:

- **A label adds or removes one contract on every leg**, so the position scales without changing shape. InsideBarTrailing keeps §M45's rule: one contract on the whole position, then its split.
- **Add-only by default. Symmetric also removes one per opposing label**, clipped at one contract per leg, and is refused where the base is already there. So every four-target bracket at four contracts is add-only.
- **The trend, higher-timeframe and VWAP labels favour the trade on their own side.** Regime and volume follow the archetype's thesis:

| thesis    | archetypes                                                                                      | regime favoured | volume favoured |
| --------- | ----------------------------------------------------------------------------------------------- | --------------- | --------------- |
| expansion | EmaCrossover, InsideBar, InsideBarTrailing, SqueezeBreakout, OpeningRange's breakout and retest | `DIRECTIONAL`   | `HEAVY`         |
| pullback  | DeadCatBounce, PullBackAndGo, EmaPullback                                                       | `DIRECTIONAL`   | `THIN`          |
| rotation  | ElasticBand, OpeningRange's fade and rejection                                                  | `CONSOLIDATING` | `THIN`          |

The opposite extreme opposes and the middle state is neutral. **Two theses meet earlier measurements.** EmaPullback's `THIN` agrees with §M36, where `HEAVY` was a cost at every cut, so its volume-alone arm is not an independent test of the thesis and is read with that beside it. ElasticBand's `THIN` runs against §M33, where `HEAVY` was a benefit on the Bollinger band this campaign's grid uses. The fit keeps its volume label for the symmetric arm alone (below), which takes a step off in heavy volume, so that thesis is tested only there, against a measurement that expects the opposite.

## The arms

Every stored campaign variant in `tools/campaign_sweep.py`'s `VARIANTS`, the grids §M44 re-swept, unchanged, at the cut fitted for it and one step per label:

| arm                         | what it is                                                        | where                                          |
| --------------------------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| `size=fixed`                | the control: the stored grid at the fitted thresholds, sizing off | every variant                                  |
| `size=confluence`           | one contract per leg more per kept label favouring the trade      | every variant keeping a label                  |
| `size=<label>`              | one kept label alone, add-only: which label carries the size      | every variant keeping two or more              |
| `size=confluence symmetric` | one more per favouring and one fewer per opposing label it keeps  | where every base is above one contract per leg |

**The symmetric arm keeps its own labels**: every label the add-only arms keep, and any they drop that still sorts once a step comes off (below). **Symmetric applies at the stored sizes** on InsideBar (four contracts on one leg), ElasticBand (four on two), OpeningRange's and SqueezeBreakout's `target=width` variants (four on two) and InsideBarTrailing. It does not apply to DeadCatBounce, PullBackAndGo, EmaCrossover, EmaPullback or any R-ladder variant, because each is four contracts on four legs.

**InsideBarTrailing runs §M45's nine arms** on §M45's grid — the split held and `order_quantity` crossed at 3/4/6/8, with `split=0.5` the control — **plus `size=<label>` and `size=confluence symmetric`**, both at a half. §M45's cells, the nine arms at five minutes in the unfiltered and midday strata, are stored and are skipped rather than re-run.

Every arm on a variant shares that variant's axes, so arm and control pair cell by cell.

## The cells

MNQ and NQ; 2, 5, 10 and 15 minutes, with OpeningRange's windows only where the bar size divides them; the 60/40 selection and held-out windows; 23 strata:

| dimension     | cells                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------ |
| unfiltered    | 1                                                                                          |
| regime        | 3, cut at the fit's own thresholds and named `regime=<state>@n=20 q=0.20/0.80`             |
| session phase | 7                                                                                          |
| volume        | 3, cut at the fit's own thresholds and named `volume=<state>@<per-bar series> q=0.20/0.80` |
| compression   | 3                                                                                          |
| trend         | 3                                                                                          |
| htf           | 3                                                                                          |

**Regime and volume are cut where the labels are**, so a stratum and a label mean the same thing. The raw volume cells are refused by the sweep, because a sizing run would otherwise cut them at the fit under the campaign's raw names. **Inside its own stratum a regime or volume label sizes every trade alike**, so `size=regime` in a regime cell and `size=volume` in a volume cell are run and reported but belong to no test family.

At the cuts below that is **17,109,056 combinations**, of which the 31,104 in §M45's stored cells are skipped.

## The cuts, fitted before the run

`tools/campaign_sizing.py fit --strategy <archetype>` fits each root, resolution and variant on the **selection window alone**, at the variant's base configuration over its unfiltered signal. §M45's rules, unchanged, and one for the symmetric arm:

- the regime and volume thresholds at the **top and bottom fifth** of their own series;
- a label kept for the add-only arms only if it favours **between 10% and 90%** of the fitted signals, **pooled over both sides** where the variant sweeps `direction`;
- **a label kept for the symmetric arm unless one step it moves the count by covers more than 90%** of the same signals: up where it favours, down where it opposes, none where it does neither. Every label the add-only band keeps passes it. It also keeps a label that favours few signals and opposes many, which adds almost nothing and sheds a step at a third of the signals or more;
- on InsideBarTrailing, the earliness cuts at the median of its signals.

**The symmetric rule was added after the first fit and before any arm ran.** §M45 had no symmetric arm, and the first fit applied the add-only band to it. That dropped labels that oppose 32–70% of ElasticBand's and SqueezeBreakout's signals, and so would shed a step there under symmetric sizing.

**InsideBarTrailing's five-minute cut is §M45's**, kept in its file rather than refitted, so the new arms in §M45's cells read the cut the stored ones ran at. Its 2-, 10- and 15-minute cuts are new. **The symmetric labels were added to every stored cut, §M45's included, at the cut's own thresholds**. Nothing else in any cut changed, and each cut's favourable shares were checked to read back exactly as stored before anything was added.

**Fitted on 2026-09-27 and transcribed here before any §M47 arm ran**, as §M45's was. Every variant of an archetype kept the same labels at each root and resolution, so the table has one row per resolution. These are the add-only arms' labels:

| archetype         | minutes | MNQ                              | NQ                               |
| ----------------- | ------: | -------------------------------- | -------------------------------- |
| DeadCatBounce     |       2 | htf, vwap, regime, volume        | trend, htf, vwap, regime, volume |
| DeadCatBounce     |       5 | htf, regime, volume              | htf, regime, volume              |
| DeadCatBounce     |      10 | htf, regime, volume              | htf, regime, volume              |
| DeadCatBounce     |      15 | trend, htf, vwap, regime, volume | htf, vwap, regime, volume        |
| PullBackAndGo     |       2 | htf, regime, volume              | htf, regime, volume              |
| PullBackAndGo     |       5 | htf, regime, volume              | htf, regime, volume              |
| PullBackAndGo     |      10 | vwap, regime, volume             | vwap, regime, volume             |
| PullBackAndGo     |      15 | vwap, regime, volume             | vwap, regime, volume             |
| EmaCrossover      |       2 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| EmaCrossover      |       5 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| EmaCrossover      |      10 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| EmaCrossover      |      15 | trend, htf, volume               | trend, htf, volume               |
| EmaPullback       |       2 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| EmaPullback       |       5 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| EmaPullback       |      10 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| EmaPullback       |      15 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| InsideBar         |       2 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| InsideBar         |       5 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| InsideBar         |      10 | trend, regime, volume            | trend, regime, volume            |
| InsideBar         |      15 | trend, regime, volume            | trend, regime, volume            |
| InsideBarTrailing |       2 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| InsideBarTrailing |       5 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| InsideBarTrailing |      10 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| InsideBarTrailing |      15 | trend, htf, regime, volume       | trend, htf, regime, volume       |
| ElasticBand       |       2 | htf, vwap                        | htf, vwap                        |
| ElasticBand       |       5 | htf, vwap                        | htf, vwap                        |
| ElasticBand       |      10 | htf                              | htf                              |
| ElasticBand       |      15 | htf                              | htf                              |
| OpeningRange      |       2 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| OpeningRange      |       5 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| OpeningRange      |      10 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| OpeningRange      |      15 | trend, htf, vwap, regime, volume | trend, htf, vwap, regime, volume |
| SqueezeBreakout   |       2 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| SqueezeBreakout   |       5 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| SqueezeBreakout   |      10 | trend, htf, vwap, volume         | trend, htf, vwap, volume         |
| SqueezeBreakout   |      15 | trend, htf, vwap                 | trend, htf, vwap                 |

**The symmetric arm counts the same labels and more on two archetypes**, on both roots and in every variant:

| archetype       | minutes | the symmetric arm also counts | favours | opposes |
| --------------- | ------: | ----------------------------- | ------: | ------: |
| ElasticBand     |     all | trend                         |    4–5% |     69% |
| ElasticBand     |     all | regime                        |      5% |     36% |
| ElasticBand     |     all | volume                        |    5–7% |  38–47% |
| SqueezeBreakout |     all | regime                        |    2–6% |  32–35% |
| SqueezeBreakout |      15 | volume                        |     10% |  38–39% |

EmaCrossover's regime passes the symmetric rule too, but its base is at its floor, so it has no symmetric arm. Every other label the add-only arms drop favours over 90% of signals and opposes under 10%, so the symmetric arm drops it as well, as it does ElasticBand's VWAP at 10 and 15 minutes, which opposes 96–99%.

**What the fit dropped, and why it matters.** ElasticBand's add-only arms keep only the higher-timeframe side, and the VWAP side below ten minutes: its trend, regime and volume labels each favour between 3.6% and 7.1% of its signals, because a close two deviations past its band is rarely in a consolidating regime, on thin volume or in a trend on the fade's side. DeadCatBounce's trend label favours between 89.8% and 92.2% of its signals, so it is kept on one root and not the other at 2 and 15 minutes. **An arm kept on one root only is run and reported but belongs to no family**, because the bar needs both roots. Where the two roots keep different labels, each root's all-labels arm counts its own.

**InsideBarTrailing's two §M45 entries read back unchanged**, so its file's hash below is not the one §M45 recorded: the file now also holds the 2-, 10- and 15-minute cuts and every cut's symmetric labels. Each file is one archetype's, fitted on the selection window alone. The hashes are taken after the symmetric labels were added, and replace the first fit's:

| archetype         | SHA-256                                                            | written                 |
| ----------------- | ------------------------------------------------------------------ | ----------------------- |
| DeadCatBounce     | `a5515f7a6dbf7fa121c9156e05a6a9cb60ec27db7311b5802320cdad320b0ff8` | 2026-09-27 09:41:33 UTC |
| PullBackAndGo     | `dd75ae18ed2f80914f0dd99fadc656449db96a6e6033f90f7eb6b27e3c48cf7b` | 2026-09-27 09:41:45 UTC |
| EmaCrossover      | `08dedb5ab1b8eec3a1985fb0b661a45eaf5d1a2e3792412b64c3a3e82dc0c7a3` | 2026-09-27 09:42:00 UTC |
| EmaPullback       | `6a3887bf7fa7b3964f6bc284b39d1563e5fb4cfddc6d4cf90597131573c769a3` | 2026-09-27 09:42:12 UTC |
| InsideBar         | `4d5b80e9c77dd99985ec2f25e3c2c5661d84bec4c2436ee9df295a178833576a` | 2026-09-27 09:42:24 UTC |
| InsideBarTrailing | `2ba467c13f116c1f77a2c9ec99f88389c83c0cf43a9fafa199716196764c10fd` | 2026-09-27 09:42:36 UTC |
| ElasticBand       | `fe9381b3fcab2156ab5e96b1bf07b643b026d33445a8eae1d08d0c92ffbdc2ef` | 2026-09-27 09:42:57 UTC |
| OpeningRange      | `146d58fdacf067016a1ab8a78fa96b245ba221cfc3a02f2bbf439998cc69d809` | 2026-09-27 09:43:26 UTC |
| SqueezeBreakout   | `fe531e9424e29d0164d8b759b0505b20852cabffd5003d3e3178490a16bbc11f` | 2026-09-27 09:43:51 UTC |

## The gates, and what counts as a pass

**Gate 1, the screen:** an arm passes in a root × resolution × stratum cell if a majority of its configurations are profitable on the selection window. Read per cell, as §M27 did, and not tested.

**Gate 2, held out:** `tools/campaign_holdout.py --variant <arm>`. The 20 configurations the selection window ranks highest pass if their mean held-out profit factor is above 1.0 **and** above the held-out median of every configuration of that arm, per root and stratum. Beside it, `tools/campaign_paired.py` sets each sizing arm against its control on held-out profit factor, cell by cell, as §M45 did: read, not the verdict.

**Gate 3, the shuffled-size null:** `tools/campaign_sizing.py null --variant <arm>`. The 20 held-out configurations the selection window ranks highest are each set against their own sizes shuffled 200 times: across the trades taken, recomputed exactly, or on InsideBarTrailing across the signals, re-simulated. **An arm clears a cell if at least `k` of the 20 beat their shuffle at p ≤ 0.05, on both roots.** `k` is the smallest count whose chance of arising by luck, under a binomial of 20 at 0.05, is at most 0.05 divided by the number of cells in the family:

| `k` | chance by luck | families it covers |
| --: | -------------: | ------------------ |
|   4 |         0.0159 | up to 3 cells      |
|   5 |        0.00257 | up to 19           |
|   6 |       0.000329 | up to 151          |
|   7 |      0.0000339 | up to 1,472        |
|   8 |     0.00000286 | up to 17,501       |

The families, counted from the fitted files over the arms the sweep builds on both roots, before any arm ran:

| family | what it holds                                                                                  | cells | `k` |
| ------ | ---------------------------------------------------------------------------------------------- | ----: | --: |
| **F1** | `size=confluence` and `size=confluence symmetric`, unfiltered, every variant × resolution      |   134 |   6 |
| **F2** | every `size=<label>`, unfiltered, every variant × resolution                                   |   321 |   7 |
| **F0** | InsideBarTrailing's midday cell at five minutes: each `size=<label>` and the symmetric arm     |     5 |   5 |
| **F3** | every sizing arm in every other stratum, less the own-stratum pairs, F0 and §M45's stored cell | 9,656 |   8 |

F1 holds 88 all-labels cells and 46 symmetric ones. F0 is InsideBarTrailing's four kept labels alone and its symmetric arm.

**F1 is #295's question: does the confluence size carry anything on this archetype?** An archetype's answer is yes if any of its F1 cells clears. **F0 is §M45's open question**, which label carries the size in the cell §M45 passed, so it is its own small family. F2 and F3 are read against their own bars and are hypothesis-generating for anything F1 did not already settle.

The binomial treats the 20 configurations as independent, and a shortlist's neighbours are not, so `k` is a floor rather than an exact rate. **Both roots is a weak replication**, because MNQ and NQ trade the same prices; it is kept because every earlier campaign asked it.

**Symmetric against add-only:** `tools/campaign_paired.py`, `size=confluence symmetric` against `size=confluence` on held-out profit factor, per variant × resolution, unfiltered. Symmetric is better in a cell if more than half the pairs improve at a sign-test p below 0.05 divided by the number of symmetric cells, on both roots, and worse if fewer than half do at that p. **On ElasticBand and SqueezeBreakout the two arms count different labels**, so a difference there belongs to the extra labels and the step they shed together, and is reported as that rather than as shedding alone.

**§M45's tiers at the new resolutions** are read with §M45's own paired bar, against `split=0.5` and against their inverse, and are hypothesis-generating only: they failed in the one cell that was a test.

**Gate 4, read on every arm, unfiltered, at every resolution**, and in any stratum cell that clears gate 3:

| read          | tool                                                      | passes if                                                                                                         |
| ------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| walk-forward  | `tools/campaign_walkforward.py --variant <arm>`           | pooled out-of-sample profit factor above 1.0, per resolution                                                      |
| bootstrap     | `tools/campaign_montecarlo.py --held-out --variant <arm>` | the median configuration's 5th-percentile profit factor above 1.0                                                 |
| the exclusion | `tools/campaign_exits.py --variant <arm>`                 | with its session-close legs removed, profit factor and net-to-drawdown both above 1.0 on the median configuration |

**The prop replay:** `tools/campaign_propaccount.py --variant <arm>` over every arm's held-out unfiltered shortlist at its stored base size, through the four presets §M28.13 read. It is read against the arm's control on pass rate, attempts and median net, and is not tested. That includes InsideBarTrailing's midday confluence arm at five minutes, which §M45 never put through an account.

## Before believing any result

- **Outside InsideBarTrailing the trades are the control's by construction**, so an arm's trade count, `session_close_share` and `ambiguous_share` are its control's. The null prints all three per configuration and refuses one where the size moved a trade. On InsideBarTrailing they are read per pair, as §M45 did.
- **A cell whose shortlist's median `ambiguous_share` is above `disambiguate.MIN_AMBIGUOUS_SHARE` (0.05)** is reported, and counts as a pass only after `tools/campaign_ambiguity.py` has settled it.
- **A paired read prints its pair count**, and a cell with no pairs concludes nothing.

## What this run is not

- **Not gate 3 for any entry.** Every arm takes its control's entries; the entry's own gate 3 stands where §M44 left it.
- **Not NT8-validated.** Every sizing row is `TIER1_ONLY`, none of the five labels exists in NT8, and a port needs each pinned first — `docs/nt8-fidelity.md` §M47.
- **Not fixed-risk sizing**, which is `Trading-Docs` §9's different idea.
- **Not a position-size ladder.** §M46 read that, and each arm runs at its stored base size.

## How to run it

```bash
for s in DeadCatBounce PullBackAndGo EmaCrossover EmaPullback InsideBar InsideBarTrailing \
         ElasticBand OpeningRange SqueezeBreakout; do
    ./.venv/Scripts/python.exe tools/campaign_sizing.py fit --strategy $s --resolutions 2 5 10 15
done
# each archetype's sizing-cuts file hashed and transcribed here, before the sweep
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants confluence-sizing --split \
    --strata confluence-sizing --resolutions 2 5 10 15 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_holdout.py --strategy ElasticBand --variant "target=0.0s size=confluence"
./.venv/Scripts/python.exe tools/campaign_paired.py --strategy ElasticBand --window holdout \
    --stratum unfiltered --control "target=0.0s size=fixed" --treatment "target=0.0s size=confluence"
./.venv/Scripts/python.exe tools/campaign_sizing.py null --strategy ElasticBand --root MNQ \
    --resolution 5 --stratum unfiltered --variant "target=0.0s size=confluence"
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy ElasticBand --held-out \
    --variant "target=0.0s size=confluence"
./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy ElasticBand \
    --variant "target=0.0s size=confluence"
```

The last five run once per archetype, arm, root, resolution and stratum the families above name. `tools/campaign_gates.py` runs them, and gates 1, 2 and 4, over every such cell in one pass, calling the same functions and ranking inside one cell as each command does when given all four. So gate 2 is read per resolution as well, rather than pooled over a variant's resolutions as `tools/campaign_holdout.py` pools them. **The sweep skips any cell already stored** and refuses one stored on other bars, so a pass interrupted part-way is resumed by running it again.

**The run is split in two by bar size**: 10 and 15 minutes first, with their gates, then 2 and 5 minutes. Nothing in this file changes between the two passes, and every family and `k` above counts all four resolutions, so reading the first pass does not move the bar the second is held to.

**Two checks run before any of it, because every loop changed.** The trade-log gate has to pass, and its captures are DeadCatBounce's alone, so the seven stored reconciliations run on `main` and on this change and have to agree exactly. Both did: `docs/nt8-fidelity.md` §M47.

[#295]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/295
