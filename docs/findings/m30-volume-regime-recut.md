---
id: M30
title: "M30 — volume and regime re-cut across the registry, and what the raw pair was reporting"
archetypes: [DeadCatBounce, ElasticBand, EmaCrossover, InsideBar, InsideBarTrailing, OpeningRange, PullBackAndGo]
issues: [289]
gates: [2]
outcome: mixed
verdict: >-
  Re-cutting turns three of six volume dimensions from inert to consistent and sorts the regime dimension by what each archetype is; almost none of the new cells makes money, and the raw regime labels agree with a calibrated cut about a fifth of the time at a lookback of 50.
---

# M30 — volume and regime re-cut across the registry, and what the raw pair was reporting ([#289])

§M27.8 swept the volume forms and tails for InsideBar alone and left the rest as a flag: "the other six archetypes' volume rows are still the single cut". §M28.14 then read every stratum against its unfiltered twin and found **relative volume close to inert everywhere but OpeningRange**, offering two readings it could not separate — volume carries less information than the clock, or the single raw cut is the wrong cut for six of the seven. This is the run that separates them, and the regime half beside it.

**2,420,400 combinations in 326 minutes of sweep time.** The volume half is 27 cells — three forms × three tail sizes × three states — for the six archetypes that were still on the raw pair, 1,479,600 rows. The regime half is 15 cells — three states × five lookbacks, each carrying its own fitted pair — for all seven, 940,800 rows. Both windows, both roots, resolutions 1/2/5/10/15, at the root's own commission and one tick of slippage. `--strata volume-forms --volume-quantiles --split` and `--strata regime --regime-quantiles --split`.

## What was decided before the run, because 27 cells is not free

[#289] asked for the tail sizes and the archetypes to be settled first rather than sweeping all six blind. Three decisions, each stated ahead of the sweep:

- **All three tail sizes stay.** §M27.8's central finding is that the ranking inverts when the cut moves three percentage points, so running one tail would reintroduce exactly the defect the campaign exists to detect. The cost is 3× on the cheapest axis in the grid.
- **All six archetypes for volume.** §M28.14's question is a cross-archetype one, and answering it for a subset leaves the rest's inertness unattributed — which is the ambiguity being spent on.
- **All seven for regime, OpeningRange included.** Its only calibrated cells were `regime=CONSOLIDATING@n=*`, run by the fade and rejection campaigns on their own variants; its campaign-grid `DIRECTIONAL` — §M28.14's largest paired delta — was still raw. It cost 28 minutes.

**InsideBar's volume half is §M27.8's and is not re-run here.** Those rows are no longer in `results/campaign/InsideBar.duckdb`, so InsideBar appears in the regime tables and in the volume tables only at its raw cut.

## The defect that had to be fixed first, and it silently returned a null result

`tools/campaign_crossread.py` pairs a filtered row against the unfiltered row of **identical parameters**. A campaign that adds a parameter column leaves it null in every row stored before it, and null is not the value those rows ran at — so every pair between a row stored before the column and one stored after is dropped. Completely, and with no error.

The first read of this campaign reported `27 strata have no unfiltered twin` and scored only the three pre-existing raw cells. **Ten columns across three archetypes** were doing it: `max_hold_bars` from §M29, `follow_through_scaling` and `follow_through_sessions` from §M28.10, and seven ElasticBand columns from §M26.5, §M26.6 and §M26.8 — `signal_shape`, `entry_trigger`, `band_stop_std`, `recovery_fraction`, `min_one_sided_bars`, `one_sided_lookback`, `rejection_close_fraction`.

The fix is the rule rather than the list: **a null parameter means the sweep predated it, so the value it ran at is the archetype's own default**, read off `archetypes.get(name).params_cls()`. A list would have been ten entries long after one campaign and stale after the next. §M28.14's published numbers reproduce exactly under it — PullBackAndGo `phase=MIDDAY` +7, `CASH_OPEN` +3, `CLOSE` −3, `htf=ABOVE` +2, `BELOW` −1 — so the change is behaviour-preserving on the rows that already paired.

**Every score §M28.14 reported for a dimension swept after it was reported against a partial pairing.** Nothing in that section is wrong, because its rows all predate §M29; anything read from these databases after it needed this fix.

## The regime labels do not name the same bars, and the disagreement grows with the lookback

`tools/campaign_labels.py --dimension regime`, MNQ selection window, raw 0.3/0.5 against the fitted 0.20/0.80 pair. The share of each raw state's bars the fitted cut puts elsewhere, at 5-minute bars:

| lookback | fitted pair     | agreement | raw `UNCLASSIFIABLE` → fitted `DIRECTIONAL` | raw `CONSOLIDATING` → fitted `UNCLASSIFIABLE` |
| -------- | --------------- | --------- | ------------------------------------------- | --------------------------------------------- |
| 5        | 0.1613 / 0.7371 | 62.3%     | 0.0%                                        | 45.4%                                         |
| 10       | 0.1088 / 0.5207 | 65.9%     | 0.0%                                        | 61.6%                                         |
| 20       | 0.0755 / 0.3717 | **38.3%** | **53.8%**                                   | **71.2%**                                     |
| 30       | 0.0613 / 0.3084 | 24.7%     | 92.7%                                       | 74.6%                                         |
| 50       | 0.0490 / 0.2480 | **20.9%** | **100.0%**                                  | 68.2%                                         |

**At a lookback of 50 the stored stratification and a calibrated one agree about one bar in five**, and every bar the raw pair calls `UNCLASSIFIABLE` is in the calibrated top quintile. The raw thresholds are fixed while the efficiency ratio's distribution shrinks as `1/√n`, so the raw labels slide down the distribution as the lookback grows — §M10.1 and §M27.5 predicted this from the arithmetic; this measures it as label agreement. NQ agrees with MNQ to within a tenth of a percentage point at every cell, as a calibration of the index rather than of the root should.

**Every stored campaign regime row sits at lookback 20**, where the raw `UNCLASSIFIABLE` band straddles the calibrated boundary 46/54 and raw `CONSOLIDATING` is 69.5% of bars against the calibrated 20%. A result quoted under one of those labels is a result about that cut.

## The volume labels do name nearly the same bars — within a form

The same read for volume never crosses a state to its opposite: **at none of the nine cuts does a raw `THIN` bar become a fitted `HEAVY` one, or the reverse.** The disagreement always runs through `NORMAL`, and agreement runs 58.3% to 97.5%. The raw pair is closest to the fifth-tail fit of the per-bar form — 92.3% at 5 minutes and 97.5% at 15 — which is what it is: `volume_form` defaults to `PER_BAR`.

That is the structural difference between the two dimensions. **The regime labels are shifted a whole notch; the volume labels are nested.** It is why re-cutting the tail size moves a volume score much less than re-cutting the lookback moves a regime one.

## The forms disagree about which bars are busy, and that is what moves a volume score

`--dimension forms` holds the tail size fixed and varies only which quantity "relative volume" names. Every form then labels exactly the same share of bars `HEAVY` by construction, so any disagreement is about *which* bars. MNQ, 5-minute bars:

| tail      | per bar vs rolling | per bar vs session to date | rolling vs session to date |
| --------- | ------------------ | -------------------------- | -------------------------- |
| 0.10/0.90 | 79.5%              | 78.9%                      | 86.9%                      |
| 0.20/0.80 | 65.0%              | **63.4%**                  | 77.9%                      |
| 0.33/0.67 | 56.7%              | 54.5%                      | 71.7%                      |

**The per-bar form is the outlier and it is the one the raw cut is.** At the fifth tail it agrees with the session-to-date form about 63.4% of bars where the other two agree with each other about 77.9%; at the fifth tail, 47.2% of the bars the session-to-date form calls `HEAVY` the per-bar form does not, 43.3% of them landing in `NORMAL`. §M10.2's decomposition finding, arriving again as a disagreement rate.

## Volume: three of six acquire a consistent cell, and the raw row was reporting the form

Cells won in both windows minus cells lost in both, ten `root × resolution` cells per stratum. Condensed to the extremes of each archetype's nine fitted cuts, with the raw cell beside them:

| archetype         | `THIN` raw → fitted range | `NORMAL` raw → fitted range | `HEAVY` raw → fitted range |
| ----------------- | ------------------------- | --------------------------- | -------------------------- |
| DeadCatBounce     | −6 → −7 … −3              | +2 → −2 … +6                | +3 → −2 … +4               |
| ElasticBand       | −6 → **−9** … −1          | **−8** → −7 … +1            | +7 → +3 … **+10**          |
| EmaCrossover      | −2 → −4 … +4              | +2 → 0 … **+9**             | +1 → −5 … +3               |
| InsideBarTrailing | +2 → −6 … +3              | +2 → +2 … +5                | +2 → −5 … +1               |
| OpeningRange      | **+9** → −5 … **+9**      | **+8** → **−9** … **+8**    | +2 → −2 … +5               |
| PullBackAndGo     | −5 → −7 … −2              | +3 → 0 … +3                 | +1 → 0 … +4                |

**Three of the six acquire a volume cell at or above the ±8 bar §M28.14 used to call a cell consistent**, and none of them had one before:

| cell                                            | score   | held-out PF | holdout trades |
| ----------------------------------------------- | ------- | ----------- | -------------- |
| ElasticBand `HEAVY@rolling_30_20 q=0.20/0.80`   | **+10** | 0.972       | 688            |
| ElasticBand `HEAVY@rolling_30_20 q=0.33/0.67`   | **+10** | 1.001       | 906            |
| ElasticBand `HEAVY@session_to_date q=0.10/0.90` | **+10** | 0.981       | 308            |
| ElasticBand `HEAVY@per_bar_20 q=0.10/0.90`      | +9      | 0.947       | 1,012          |
| EmaCrossover `NORMAL@rolling_30_20 q=0.20/0.80` | +9      | 0.990       | 1,494          |
| EmaCrossover `NORMAL@rolling_30_20 q=0.33/0.67` | +8      | 0.974       | 900            |
| OpeningRange `THIN@per_bar_20 q=0.20/0.80`      | +9      | 1.036       | 122            |
| OpeningRange `NORMAL@per_bar_20 q=0.20/0.80`    | +8      | 0.949       | 335            |

**ElasticBand is the clearest case, and it inverts §M28.14's reading of it.** Under the raw cut its only cell reaching ±8 was `NORMAL` at −8, a *cost*; re-cut, `HEAVY` is positive at all nine cuts and reaches +10 at three of them. The two cells §M28.14 could see were the two the per-bar form happened to produce.

**The re-cut also exposes costs the raw cut missed.** ElasticBand's `THIN` reaches −8 or −9 under four different cuts, and OpeningRange's `NORMAL` — +8 under the per-bar form — is **−9 under the session-to-date form at a third-tail**. That is the largest sign reversal in the campaign and nothing but the form changed.

**OpeningRange's raw `volume=THIN` and `volume=NORMAL` are per-bar results.** §M28.16 took both through gate 3, where `volume=NORMAL` cleared p = 0.05 on 6 of 10 MNQ configurations and 10 of 10 on NQ. Those rows are the per-bar form at roughly a fifth-tail; the same label under the session-to-date form scores −9 here. The gate-3 result stands for the cut it was run at and does not transfer to the label.

## Regime: the calibrated cut sorts the registry by what each archetype is

Cells won in both windows minus cells lost in both, seven archetypes, five fitted lookbacks and the raw cell:

| cell                  | DeadCat | Elastic | EmaCross | InsideBar | IBTrailing | OpenRange | PullBack |
| --------------------- | ------- | ------- | -------- | --------- | ---------- | --------- | -------- |
| `DIRECTIONAL@n=5`     | −1      | +1      | **+8**   | −1        | +1         | **+10**   | −1       |
| `DIRECTIONAL@n=10`    | +2      | 0       | +6       | 0         | 0          | **+10**   | +1       |
| `DIRECTIONAL@n=20`    | 0       | −1      | +4       | +2        | +2         | **+10**   | 0        |
| `DIRECTIONAL@n=30`    | +3      | **−3**  | +4       | +4        | +6         | **+10**   | +6       |
| `DIRECTIONAL@n=50`    | +2      | 0       | +4       | +4        | +7         | **+10**   | +4       |
| `UNCLASSIFIABLE@n=5`  | +1      | +5      | **−8**   | +6        | +6         | 0         | −4       |
| `UNCLASSIFIABLE@n=30` | +1      | **+8**  | −3       | −2        | −1         | 0         | −7       |
| `UNCLASSIFIABLE@n=50` | +2      | **+8**  | −4       | 0         | 0          | −1        | −4       |
| `CONSOLIDATING@n=5`   | −4      | 0       | **−10**  | −1        | −4         | **+10**   | +3       |
| `CONSOLIDATING@n=50`  | −7      | −7      | +2       | −2        | −4         | −2        | 0        |
| `DIRECTIONAL` raw     | −1      | −2      | +5       | +4        | +4         | +8        | +5       |
| `UNCLASSIFIABLE` raw  | +2      | +5      | +4       | **+8**    | +7         | **+10**   | 0        |

**At a lookback of 30, six of the seven prefer the calibrated top quintile and the seventh is the registry's only mean-reversion archetype.** ElasticBand is −3 at `DIRECTIONAL@n=30` and +8 at `UNCLASSIFIABLE@n=30` and `@n=50`; every breakout, momentum and continuation archetype has the opposite sign. **EmaCrossover and ElasticBand are exact mirrors** — +8 against +5 at `DIRECTIONAL@n=5`, −8 against +5 at `UNCLASSIFIABLE@n=5` — which is the structure §M28.14 found in the *phase* dimension appearing in a second dimension.

**The raw cut cannot show it.** Raw `UNCLASSIFIABLE` is positive for five of seven including both EmaCrossover and ElasticBand, so the mirror is invisible; raw `DIRECTIONAL` is negative for DeadCatBounce, whose calibrated cells are positive at three lookbacks of five.

**InsideBar's raw `regime=UNCLASSIFIABLE` +8 is not reproduced by any calibrated cell** — its five are −2, +3, −2, +6 and 0 — and its median holdout trade count inverts, 577 raw against about 1,110 fitted. §M28.16 took that raw cell through gate 3, where it beat its null on 10 of 10 MNQ configurations and cleared p = 0.05 on none. At lookback 20 the raw band is 46% calibrated-middle and 54% calibrated-directional, so it is a mixture no single calibrated cell reproduces rather than a cell that moved.

## OpeningRange's `DIRECTIONAL` is +10 at every lookback

The one cell in the campaign that is invariant to the calibration: **+10 at n=5, 10, 20, 30 and 50** — the filter won in both windows on all ten `root × resolution` cells, five times over, against +8 raw. Held-out median profit factor 0.993 to 1.101 and 80 to 203 median holdout trades against the raw cell's 56, which is the per-contract sample §M27.5 said a fitted cut restores.

It is also the only family here whose held-out profit factor clears 1.0 at more than one cut. A breakout archetype wanting a directional regime is the least surprising statement in the campaign; what is new is that it now survives the threshold and the lookback both moving, where §M28.14's +8 was one cut at one lookback.

## What this does not settle

- **Beating your own unfiltered twin is not making money.** Of the eight new consistent volume cells, six have a held-out median profit factor **below 1.0** — ElasticBand's three +10 cells sit at 0.972, 0.981 and 1.001. They lose less than unfiltered rather than winning. §M28.14 records the same trap.
- **A score is a consistency check and not a p-value, and no cell here has been through gate 3.** §M28.16 measured the rank correlation between a §M28.14 score and its matched-null excess at −0.132 — nothing. Running a null on cells picked *after* looking at these scores is the multiple-comparisons trap that section names, so the family has to be stated in advance: 162 fitted volume cells and 105 fitted regime cells were swept, and any null over a handful chosen from them has to carry that. **OpeningRange `regime=DIRECTIONAL@n=30` is the candidate worth stating first**, on its invariance rather than on its rank.
- **The tail sizes are still stated rather than fitted.** A tenth, a fifth and a third were chosen ahead of the sweep exactly as §M27.8 chose them. What the fit buys is that a cell means the same share of bars under every form and at every bar size, not that the share chosen is right.
- **`volume_baseline_sessions` and `volume_rolling_bars` never moved.** Still 20 and 30, as §M27.8 left them. The rolling window is the axis carrying EmaCrossover's +9 and two of ElasticBand's +10s, and it has never been swept.
- **The regime quantile pair is one cell size.** `(0.20, 0.80)` throughout, so "calibrated" here means a fifth at each end and nothing has tested whether a different cell size reorders any of this.
- **ElasticBand's volume answer here contradicts §M26.9's**, and both used the same nine fitted cuts. That section found `HEAVY` a cost on both roots at all nine and `NORMAL` the state that helps; this finds the reverse. The grids differ — §M26.9 is the VWAP band with the §M26.5 shape over one held bracket, this is the campaign's Bollinger-band variants over the target ladder — so **the volume answer belongs to a configuration and not to an archetype.** Neither reading generalises to "ElasticBand likes heavy volume".
- **Nothing is re-ranked and no archetype is retired or revived.** The stored strata are unchanged; what is new is 267 cells that did not exist and a pairing that now forms.

Every figure here is one dated run over the archive as it stands, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_crossread.py` and `tools/campaign_labels.py` — not a standing property.

[#289]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/289
