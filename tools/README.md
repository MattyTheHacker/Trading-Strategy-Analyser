# Tools

The scripts in this folder drive `nqbt` from the command line: sweeping a campaign, reading what it stored, reconciling against NinjaTrader, and the checks CI runs. Each one is a thin command line over the package. This file says what each tool is for, how to run it, and why its options and defaults are what they are; the module docstring of each tool carries its one-line summary, its usage lines and a pointer back here.

## Running a tool

Run every tool from the repository root with the project's venv:

```bash
./.venv/Scripts/python.exe tools/campaign_report.py --help
```

Run directly, `sys.path[0]` is `tools/` rather than the repository root, so a tool importing a sibling (`from tools.campaign_report import load`) would fail. Each such tool therefore puts the repository root on `sys.path` before its sibling imports, and a test importing `tools.campaign_*` relies on the same thing.

The campaign tools read and write **one DuckDB database per archetype**, `results/campaign/<Strategy>.duckdb`, which `tools/campaign_sweep.py` creates. `results/` is not committed.

## Rules every campaign reader shares

These hold across the reading tools below, so they are stated once here rather than in each section.

- **A shortlist is chosen on the selection window and read on the held-out one.** A figure read from the window that chose it measures a selected maximum, not the strategy -- `docs/roadmap.md` §M28.13. `--held-out` (or `campaign_holdout.held_out`, which the tools use internally) builds that pair: the held-out rows of the configurations the *selection* window ranked highest.
- **A database holding more than one variant needs `--variant`.** A shortlist drawn over a mixture of geometries ranks the fattest tail in it rather than the one being asked about -- `docs/roadmap.md` §M28.9.
- **Tools that read per-trade logs need `tools/campaign_shortlist.py` to have stored them first.** A row with no log, or one that cannot honestly be joined to its bars, is named and skipped rather than silently dropped.
- **`--rerun` builds the logs in the tool instead**, on the bars the stored rows were swept on. That is the only way to read a campaign the archive has moved under -- see `campaign_swept.py` below.
- **A stored row belongs to the archive it was swept on.** Extending the archive moves the 60/40 split under every campaign stored before it, so a re-run on different bars is refused (by `campaign_null.py`) or reported (by the re-running readers) -- `docs/roadmap.md` § "Standing traps".
- **Re-runs use raw prices.** `splice.load_continuous` is called without `back_adjust`, so the bars are `PriceBasis.RAW`: the prices that traded, which is what the sweep measured them as. A rule reading an absolute level therefore runs rather than being refused -- `docs/roadmap.md` § "The build spec's three loose ends".
- **Re-runs are grouped by window and resolution**, because the resample and the prepared dataset are the expensive parts and every row sharing those two can share both.
- **Nothing a reader prints is a ranking unless it says so.** The distribution of a pre-chosen set is the reading; picking the best row of an output re-introduces the selection bias one level up -- `docs/findings/README.md`.

## The tools at a glance

| group                             | tools                                                                                                                                                                                                                                                              |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sweeping                          | `campaign_sweep.py`, `rerun_sweeps.py`                                                                                                                                                                                                                             |
| Storing and re-running trade logs | `campaign_shortlist.py`, `campaign_swept.py`, `campaign_annotate.py`                                                                                                                                                                                               |
| Reading a campaign                | `campaign_report.py`, `campaign_holdout.py`, `campaign_paired.py`, `campaign_crossread.py`, `campaign_crossroot.py`, `campaign_labels.py`, `campaign_hold.py`, `campaign_early_exit.py`                                                                            |
| Testing a shortlist               | `campaign_null.py`, `campaign_contracts.py`, `campaign_montecarlo.py`, `campaign_walkforward.py`, `campaign_exits.py`, `campaign_ambiguity.py`, `campaign_review.py`, `campaign_flatten.py`, `campaign_sizing.py`, `geometry_contribution.py`, `campaign_gates.py` |
| Prop-firm accounts                | `campaign_propaccount.py`, `campaign_propobjectives.py`                                                                                                                                                                                                            |
| Reconciling against NinjaTrader   | `reconcile_nt8.py`, `reconcile_higher_timeframe.py`, `reconcile_order_lifetime.py`, `compare_exports.py`                                                                                                                                                           |
| The regression gate and CI        | `capture_trade_logs.py`, `compare_trade_logs.py`, `trade_log_gate_ci.py`, `lint_commit_messages.py`, `submodule_tree_payload.py`, `numba_tuple_probe.py`                                                                                                           |
| Documentation                     | `findings_index.py`                                                                                                                                                                                                                                                |

A campaign usually runs in this order: `campaign_sweep.py --split` to store the grid on both windows; `campaign_report.py` and `campaign_holdout.py` to read it; `campaign_shortlist.py --held-out` to store the shortlist's logs; then the tests of that shortlist. `campaign_gates.py` runs those per-cell reads over every cell of a variant set in one pass.

## Sweeping

### campaign_sweep.py

Sweeps every registered archetype across resolution, market regime and session phase, so "which strategy is worth improving" is a query rather than six incomparable runs.

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --strata context --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --split --strata phase --n-jobs 8
```

Both roots, the spliced continuous series, resolutions 1/2/5/10/15, at the root's real commission and one tick of slippage. `--split` re-runs the same grids on a selection window and a held-out window instead of the whole series, which is what makes a shortlist testable rather than a ranking of noise -- `docs/findings/m26-elastic-band.md` § "Held out, and then the test it fails".

**`--n-jobs` is applied to each sweep call**, one per (variant x stratum), and a call smaller than `SERIAL_BELOW_COMBINATION_BARS` (combinations x bars) stays in-process whatever it asks for, because below that a pool costs more than its workers return -- `docs/roadmap.md` § "A sweep call's worker count".

**One database per archetype**, under `results/campaign/`. A convention rather than a constraint since `_append_or_create` learned to widen a table instead of dropping what it does not recognise -- `docs/roadmap.md` §M27. Rows carry their variant's own name, so a re-sweep lands in the same database as the campaign it follows and stays separable: pass `--variant <name>` to the reading tools. **A cell already stored is skipped**, keyed by variant, stratum, root, resolution and window, and one stored on other bars is refused: no reading tool de-duplicates, and `tools/campaign_holdout.py` pairs the windows one-to-one, so a second copy of a cell would be counted twice. A pass interrupted part-way is resumed by running it again. **The skip compares the bars alone**, not the grid, the costs or the code that produced the rows, so every skip is logged as a warning; a cell re-run after any of those changed has to be moved aside or run under another name.

**Commission is per root and never one figure for both sizes**: the point value differs tenfold and the commission does not, so MNQ's number applied to NQ flatters it. The micros take MNQ's figure and the full-size roots take NQ's -- `docs/roadmap.md` § "Commission on the roots beyond NQ".

#### Strata

**Strata are one dimension at a time, never crossed.** `--strata core` is unfiltered, then once per regime and once per session phase; `--strata context` adds the volume, compression, trend and higher-timeframe cuts and appends to the same databases. Each dimension is also nameable on its own -- `unfiltered`, `regime`, `phase`, `volume`, `compression`, `trend`, `htf` -- which is how a held-out pass adds one at a time. A held-out test of a stratified shortlist is a smaller sample twice over, so `--split` defaults to the unfiltered stratum alone unless one is named.

Some groups **re-cut** a dimension another group already owns, so `--strata all` leaves them out rather than running that dimension twice under two sets of names: `directional` and `consolidating` (one regime cell each, without its four siblings), `trend-up` (one trend cell), `midday` (one phase), `volume-forms` (the volume dimension under all three forms and a fitted cut) and `compression-forms` (the compression dimension under both its forms).

- **`--strata volume-forms`** makes a cell per (form, tail size, state), so "an unusually busy bar" and "an unusually busy session so far" are separable statements rather than one of three the campaign happened to ask. **`--volume-quantiles`** fits each form's thresholds to its own distribution on the selection window, because a raw pair is a different share of bars under each form. Three tail sizes are fitted rather than one, because the cut decides who is in `HEAVY` and a stratification read off a single unexamined cut is the cut's result -- `docs/roadmap.md` §M27.8.
- **`--volume-rolling-bars` and `--volume-baseline-sessions`** move the two windows every stored row holds at 30 and 20. **A rung is a cell and not an axis**, for the reason a regime lookback is: the window changes the ratio's distribution, so the threshold pair moves with it. The cell name already carries both windows (`volume.describe_key`), so a ladder lands beside the stored rows rather than on top of them. **`--volume-forms`** narrows which forms a pass runs, which keeps a rolling ladder from re-running the two forms that do not read the window. The series are built through `nqbt.volume.key`, which drops the rolling window from every form but `ROLLING`, and deduplicated after that drop so a ladder does not build one identical per-bar series per rung -- `docs/findings/m32-volume-windows.md`.
- **`--regime-quantiles`** replaces the regime stratum's raw thresholds with a pair fitted to the efficiency ratio's own distribution at each `(resolution, lookback)`, and splits the stratum into one cell per lookback -- `regime=DIRECTIONAL@n=20 q=0.20/0.80`. A cell rather than an axis because the thresholds move with the lookback and a sweep crosses its axes. The fit is taken on the selection window at every window, so a held-out run reads a cut it did not see. Why a raw pair cannot be swept against the lookback, and what the quantiles are chosen for: `docs/roadmap.md` §M27.5. **The cell size is in the name**, so two of them can live in one database -- the rows §M30 wrote carry the earlier bare `@n=20` and are the stated pair, which `docs/roadmap.md` §M31 re-ran under the name that says so.

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --strata volume-forms --split --volume-quantiles --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --strata volume-forms --split --volume-quantiles --volume-forms ROLLING --volume-rolling-bars 10 90 --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies OpeningRange --strata directional --split --regime-quantiles 0.10 0.90 --n-jobs 8
```

#### Variant sets

`--variants` picks the grid. `campaign` (the default) is what §M27 measured, per archetype, and **a re-sweep that changes an axis gets its own variant set** rather than an edit to that grid, where it would leave the stored rows and the code that produced them disagreeing. Most sets come with a `--strata` group of the same name holding the cells stated for them in advance. A variant the resolution cannot express is skipped rather than raising; only a session-anchored range does this, because its anchor and window must both be whole numbers of bars (a 5-minute range does not exist on 10-minute bars) -- `docs/roadmap.md` §M28.

| `--variants`          | what it runs                                                                                                                                                     | record                                                            |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `campaign`            | every archetype's campaign grid                                                                                                                                  | `docs/roadmap.md` §M27                                            |
| `narrow`              | InsideBar's entry held at what §M27 chose, its bracket pair crossed; each variant declares its own resolution, so `--resolutions` is not needed                  | `docs/roadmap.md` §M27.3                                          |
| `spec`                | EmaCrossover's moving-average trail, round-number avoidance and confluence count, each against a control in the same pass                                        | `docs/roadmap.md` § "The build spec's three loose ends, measured" |
| `orb`                 | OpeningRange's deferred anchors, entry mechanisms and stop levels                                                                                                | `docs/roadmap.md` §M28.2                                          |
| `orb-fade`            | §M28.2's parked fade, over the bracket it was parked for                                                                                                         | `docs/roadmap.md` §M28.5                                          |
| `orb-rejection`       | the fourth ORB entry over that same bracket, so the two reversion entries differ by their entry rule alone                                                       | `docs/roadmap.md` §M28.7                                          |
| `orb-geometry`        | the range's anchor crossed with its length, on all four entries, each at the bracket its own campaign swept                                                      | `docs/roadmap.md` §M28.8                                          |
| `orb-followthrough`   | the bracket denominated in the **trailing** follow-through rather than the session's own range width, against a control on the same bars                         | `docs/roadmap.md` §M28.10                                         |
| `orb-bracket`         | the stop fraction carried past `1.0`, crossed with the width target ladder                                                                                       | `docs/roadmap.md` §M28.11                                         |
| `elastic-shape`       | what the signal bar itself has to look like, over the VWAP source §M26.4 left standing, with the no-requirement control in the same pass                         | `docs/roadmap.md` §M26.5                                          |
| `elastic-volume`      | the shape §M26.5 carried forward crossed with the volume states, each cell cut on its own distribution (run with `--volume-quantiles`)                           | `docs/roadmap.md` §M26.9                                          |
| `elastic-channel`     | that shape pair crossed with the channel, over the same held bracket, so a volume cell's sign can be attributed to one of them                                   | `docs/roadmap.md` §M33                                            |
| `elastic-recovery`    | the bar that closes back inside once the run outside the band ends, against the shapes read on a bar still outside                                               | `docs/roadmap.md` §M26.6                                          |
| `elastic-band-stop`   | a stop on the channel the entry was measured against, beside the three that are a distance or a bar extreme                                                      | `docs/roadmap.md` §M26.8                                          |
| `hold`                | **every** archetype's stored campaign grid once per maximum hold time, the uncapped arm included                                                                 | `docs/findings/m29-maximum-hold-time.md`                          |
| `emapullback-trail`   | EmaPullback's stored grid with its stop fixed, and trailed on the slow average that placed it                                                                    | `docs/findings/m37-ema-pullback-trail-on-slow.md`                 |
| `emapullback-confirm` | EmaPullback's market entry against its confirmation entry at two order lifetimes, both kind axes held at `ema`                                                   | `docs/findings/m39-ema-pullback-confirmation-entry.md`            |
| `ibt-sizing`          | InsideBarTrailing's stored grid with its split held, crossed with a quantity axis, once per sizing arm, over the cuts `tools/campaign_sizing.py fit` wrote first | `docs/findings/m45-ibt-sizing-preregistration.md`                 |
| `confluence-sizing`   | the confluence size on every archetype: each stored grid once per arm, the regime and volume strata cut at the fit's own thresholds                              | `docs/findings/m47-confluence-sizing-preregistration.md`          |
| `early-exit`          | **every** archetype's stored campaign grid once per conditional early-exit arm, the control with every rule off included                                         | `docs/findings/m48-early-exit-preregistration.md`                 |

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants narrow --strata narrow --split --regime-quantiles --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants orb-fade --strata orb-fade --split
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants elastic-volume --split --strata elastic-volume --volume-quantiles
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants hold --split --strata hold
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants emapullback-confirm --split --strata emapullback-confirm --resolutions 2 5 10 15 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_sizing.py fit --resolutions 5
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies InsideBarTrailing --variants ibt-sizing --split --strata ibt-sizing --resolutions 5 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_sizing.py fit --strategy ElasticBand --resolutions 2 5 10 15
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies ElasticBand --variants confluence-sizing --split --strata confluence-sizing --resolutions 2 5 10 15
./.venv/Scripts/python.exe tools/campaign_sweep.py --variants early-exit --split --strata early-exit --resolutions 2 5 10 15 --n-jobs 12
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies InsideBarTrailing OpeningRange --variants early-exit --split --strata midday --resolutions 2 5 10 15 --n-jobs 12
```

#### Why the grids look the way they do

**A mode is a variant, not an axis.** Where one parameter is read only under some values of another -- a trail's period with the trail off, a rejection depth under a non-rejection shape -- crossing the two as axes runs identical combinations that `dead_axes` cannot see. So every such mode is a variant dimension, and each variant carries only the axes it reads -- `.claude/rules/sweep-and-context.md`. A tuple (a target ladder, for instance) is not sweepable either, so it too is one variant per value, and a stored ElasticBand ladder is read back off the variant name's `target=` token.

- **`campaign`.** EmaPullback sweeps both moving-average kinds and both periods, which no earlier campaign here did: its two averages are the level price returns to *and* the level the stop sits on, so this is where §M27's "the averages are nearly inert" reading was least safe. `touch_mode` and `require_turn` are axes because every value reads every other axis; the trail is held off -- `docs/findings/m34-ema-pullback-spec.md`. SqueezeBreakout is one variant per (stop, target) for OpeningRange's reason, with the squeeze form as an axis because both forms read the period, baseline and threshold -- `docs/findings/m19-2-squeeze-breakout-spec.md`.
- **`narrow`.** InsideBar's entry is held per resolution at the modal value of §M27's own DIRECTIONAL top twenty, so the re-sweep varies the bracket and nothing else. Where that twenty is tied, the NinjaScript default stands rather than a coin flip, which is the campaign's own finding that the moving-average axes barely matter. Chosen on profit factor because §M27 ranked that way; held, never re-tuned -- `docs/roadmap.md` §M27.3.
- **`spec`.** The shared axes are deliberately a coarse cut, with the moving-average kind dropped: §M27's gate 1 puts every kind axis below 0.04 eta-squared, and a large shared grid would bury the three new axes the set exists to ask about. The ATR and swing stops are variants because each one's axis is inert under the other. The trail is a variant with `trail=off` as the control in the same pass. Round numbers are tried at 5 and 25 points, the two spacings a discretionary NQ trader would name: the rule only ever moves a stop that lands exactly on one, so a denser ladder buys resolution the rule does not have, and every one of those cells needs raw prices. The confluence count is measured over the regime, volume and compression filters, all side-neutral; trend and higher-timeframe name a direction and would measure the long half rather than the count, and three is the smallest number that makes the count interesting (at two, the only legal count is the union).
- **`orb`.** The ranges add §M28's anchor axis, which §M28.1 never left: `overnight` is the session open through to the cash open (what "the overnight range" and FX's "London breakout" both name) and `london=60m` is the first hour of the European cash session. The three entry mechanisms are variants because `entry_offset_ticks` is inert for a retest and `retest_offset_ticks` for the other two; `tp_multiplier` is swept only under the R target, where it lives. The stop fraction `[0.25, 0.5, 0.75, 1.0]` is **one axis where §M28.1 had two modes**: `1.0` reproduces the opposite-extreme stop exactly, offset included, and `0.5` is the midpoint stop, so the axis contains the only stop that passed gate 1. The ATR stop is gone -- §M28.1's own deferral, 0 of 10 cells and half the runtime. The strata add the one trend cell §M28.1's gate 3 passed on both roots, as its own group so the re-sweep names its strata before it runs rather than picking them afterwards -- `docs/roadmap.md` §M28.2.
- **`orb-fade` and `orb-rejection`.** A fade's stop runs **outward** where a breakout's runs inward, because the extreme it enters at is the one it stops behind; §M28.2's axis never placed it anywhere tight. `[0.02, 0.05, 0.10, 0.25]` extends the same axis downward and keeps `0.25` as its endpoint, so new and parked rows share a cell exactly -- `docs/roadmap.md` §M28.5. `target=width+mid` adds the range **midpoint** as a first target, which is what a rejection trade aims at and the first target in the band-reversion convention §M26 records. The rejection's limit rests `[0, 1, 4, 8]` ticks inside the extreme: `0` is not the setup, since a limit on the extreme needs price to trade *through* it under `IsFillLimitOnTouch = false`; from one tick in, a fill measures "came this close and turned" -- `docs/roadmap.md` §M28.7. The rejection's bracket is held at exactly what §M28.5 swept, so the entry is the only thing that moved. Both reversion entries are asked about `unfiltered` and `regime=CONSOLIDATING`, stated before either ran: a range that holds is a range worth trading back from.
- **`orb-geometry`.** All four entries each carry the bracket their own campaign gave them rather than one shared grid, so the range is the only thing that moves; a single bracket would move two things at once on two of them. The windows are §M28's three, the hour most sources mean by "the ORB", and the lengths that bracket it, plus the overnight span because it reproduces §M28.2's `overnight` range and anchors the gradient to a stored measurement. Which (anchor, window) cells exist is derived from the session template -- a range must complete before the phase the forced flat falls in -- and whether a resolution can express one is computed, since both anchor and window must be whole bars. Range names carry `+` where stored ones carry `=`, so the two cannot collide -- `docs/roadmap.md` §M28.8.
- **`orb-followthrough` and `orb-bracket`.** Both run only the 15- and 30-minute cash ranges, the two §M28.8's gate 3 separated from a permuted range, so the question is asked where there is an edge to lose. The trailing median is taken over 20, 60 and 250 sessions (a month, a quarter, a year), because the lookback decides whether the scale tracks the regime or averages over it. The scale applies to the target, the stop or both, one arm each, since [#261] names both halves. The follow-through mode is a variant because `follow_through_sessions` is inert at `ORB_SCALE_NONE`, with the control on the same bars in the same pass -- `docs/roadmap.md` §M28.10. `orb-bracket` carries the stop fraction past `1.0`, where it sat on the boundary as the winner on both roots and windows ([#262]), built from the original axis so every stored cell re-runs at exactly its own fraction; past `1.0` the stop sits outside the range. Its width ladders include the parameter default (the ladder every ORB campaign ran without varying it), `target=runner` (no target, both legs to the forced flat) and the only two-distance scale-out. Names carry `cash-ft+` and `cash-br+` because the variant name is the only thing separating two runs in one database -- `docs/roadmap.md` §M28.11.
- **`elastic-shape`.** Of the four target ladders it keeps two, the midline and the one patience found, named out of the ladder dict rather than restated so the two campaigns cannot drift on what a ladder means. `shape=any` is the control: the same axes over the entry §M26.4 left, with no requirement on the bar -- `docs/roadmap.md` §M26.5.
- **`elastic-volume` and `elastic-channel`.** Both hold the same bracket (`entry_std`, `stop_mode`, `max_hold_bars`), named once so the two sets can be read against each other and copied into each variant so nothing can mutate both. Three of §M26.5's axes are held rather than swept, so the added cells are the volume strata and not a wider grid: `min_one_sided_bars` (a dead value at its low end and a cost at its high end), `min_bars_outside` (a duplicate of the reversal shape on 82.7% of cells) and the target ladder -- `docs/roadmap.md` §M26.9. §M26.9 and §M30 returned opposite answers from grids differing three ways at once, so `elastic-channel` moves only the channel and the shape; the channel is a variant because `band_period` is read only under Bollinger and `vwap_min_session_bars` only under VWAP, and the Bollinger period is pinned at 20 (its default and the middle of §M30's ladder), which costs that arm §M30's best-of-three -- `docs/findings/m33-channel-volume.md`.
- **`elastic-recovery`.** The trigger and its depth are one variant because the depth is inert under the extended trigger. There are two controls, because §M26.5 asked whether requiring a reaction beats requiring nothing and this asks whether waiting for it beats reading it off a bar still outside. A fourth depth, 0.5, was measured and left out: it leaves 140 signals in 1.66M MNQ bars. `min_one_sided_bars` is dropped for §M26.5's reason; `min_bars_outside` stays, because under the recovery trigger it is not a duplicate -- `docs/roadmap.md` §M26.6.
- **`elastic-band-stop`.** `stop_mode` becomes the arm, so a cell differs from its control only by where the stop went; the band depth is part of the arm because it is inert under the other three schemes, and the three existing stops are arms rather than stored rows because a stored row came from a different grid. The entry is held at `shape=any` and `shape=reversal` -- one with a measured excess and one without -- to tell a stop scheme being ranked from the bars under it -- `docs/roadmap.md` §M26.8.
- **`hold`.** The ladder `(0, 5, 10, 20, 40, 80)` is a **bar count, not a duration** -- 20 bars is 20 minutes at one resolution and five hours at fifteen -- so it is never read pooled across resolutions. Its top is deliberately past where the session flatten binds at coarse resolutions: an arm that cannot bind has to read as its control. The axes are otherwise §M27's, so every arm holds the same number of combinations and the comparison is paired, and the `hold=0` arm is also the check that generalising the cap moved nothing. `max_hold_bars` is dropped from the axes, because ElasticBand sweeps it at `[0, 30]` and an axis beats the base it is crossed with -- leaving it would run six identical arms and report the ladder as inert. Every name carries a `hold=` token no stored row has.
- **`emapullback-trail` and `emapullback-confirm`.** The `trail=off` arm is §M35's grid under a name no stored row carries, so it is both the control and the check that adding the mode moved no stored row. The confirmation run holds both kind axes at `ema`, since §M35 measured them as inert and inverting across the split, which keeps three arms inside §M35's run time.
- **`early-exit`.** Twenty-seven arms, one rule on in each: the control; the not-working exit at bars `(3, 5, 10, 20)` crossed with thresholds `(-0.5, 0, 0.25, 0.5)` R; losing inside `(15, 30, 60, 120)` minutes of the close; the regime exit; and the trend exit under both forms -- the last two with and without "only if losing". **Every stored axis is kept**, unlike `hold`: ElasticBand's `max_hold_bars` of `[0, 30]` sits past the ladder's top bar, so no combination is refused as unable to fire. Its stratum is unfiltered; the two #344 candidates' midday cell is a second pass named with `--strategies`, because `--strata midday` would otherwise run it for all nine. Every name carries an `exit=` token no stored row has -- `docs/findings/m48-early-exit-preregistration.md`.
- **`ibt-sizing`.** Every sizing arm crosses contract counts `[3, 4, 6, 8]`. Three is the floor because a quarter and a half both round up to one lot of two contracts, and every tier would run as its own control there -- `docs/nt8-fidelity.md` §M45.
- **`confluence-sizing`.** Each stored variant runs once per arm over its own axes -- the control, every kept label together, each alone, and the together arm symmetric where the base can shed a step -- so an arm and its control pair cell by cell. InsideBarTrailing's arms are §M45's nine and the new ones, on §M45's grid. The regime and volume cells take the fit's thresholds under names carrying the cut, and the sweep refuses the raw `volume` group, which would carry the fitted cut under the raw name -- `docs/findings/m47-confluence-sizing-preregistration.md`.

### rerun_sweeps.py

Clears the sweep database and re-runs the grids that still matter, stratified.

```bash
./.venv/Scripts/python.exe tools/rerun_sweeps.py            # drop, then re-run
./.venv/Scripts/python.exe tools/rerun_sweeps.py --n-jobs 8
```

**This deletes `sweeps`, `combos` and `trades`**, and the drop is not optional. Every row stored before it was computed against a continuous series with different roll dates, at a commission that is not the real one, and before the market-context labels existed, so those rows answer a different question and go rather than being appended to -- `docs/roadmap.md` § "Stored sweeps -- dropped and re-run, stratified".

**One dimension at a time, never crossed**: eleven strata per root -- unfiltered, once per regime, once per session phase -- rather than the 32 cells the product would give. The point is to tell "no edge anywhere" from "edge in one stratum, drowned by the others"; crossing them is what #48's guard refuses. Every stratum runs the same 96-combination grid, which is the dropped grid minus `ambiguity_policy`: that axis is fixed at `1`, what NT8 does, because `0` is a blanket worst case more pessimistic than NT8 and the two were measured 0.009 profit factor apart.

## Storing and re-running trade logs

### campaign_shortlist.py

Re-runs a campaign shortlist with its trade logs kept, and stores them beside the summary rows.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar --root MNQ
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --held-out
```

The sweep stores summary rows and nothing per trade, and turning `keep_trades` on there is not the fix: every combination's log is not a thing to store, and `keep_trades` changes what `sweep.run_combination` returns and never what it measures. A bootstrap, a permutation test and a time-of-day review each need a per-trade vector, so the logs are made here: rebuild a stored `combos` row, run that configuration again with its log kept, and save it under the `(sweep_id, combo_id)` the summary row already carries. A stored log replaces whatever sits under the same key, so a second run refreshes rather than doubles. `verify` refuses to file a log whose trade count or net P&L disagrees with the row it is filed against.

**`--held-out` logs the pair a gate should read** -- `docs/roadmap.md` §M28.13.

It is also the home of `rebuild`, `shortlist` and `best_row`, which every tool starting from a stored row needs; `tools/campaign_report.py`'s `load_trades` reads back what `store_logs` wrote. The dataset for a block of rows is built from them as a combination grid, so its context is `Grid.required_context`'s union rather than a second copy of it. `swept_series` cuts the archive back to where it stood when a campaign was stored, so `source` names the same window again; the control arm reproducing the stored figures is what says the earlier bars are unchanged too. `exit_on_close_seconds` moves the forced flat off the value every stored row was swept at, which only `tools/campaign_flatten.py` should pass.

### campaign_swept.py

Re-runs one stored shortlist's held-out logs on the bars it was swept on, and hands them to the caller instead of storing them. It is what `--rerun` does in the reading tools.

```bash
./.venv/Scripts/python.exe tools/campaign_exits.py --strategy InsideBarTrailing --rerun
./.venv/Scripts/python.exe tools/campaign_montecarlo.py --strategy InsideBarTrailing --rerun
```

Extending the archive leaves a gate-4 read of an older campaign with no log at all, because `campaign_shortlist.py`'s `verify` refuses to file one that disagrees with its row. Re-running here, over the archive cut back to where it stood when the row was swept, keeps that guard intact. **The agreement is reported rather than required** (`trades` and `net_pnl`, per root x resolution and never across resolutions, since one figure spanning two bar sizes would hide a root that reproduced at one of them and not the other): a decomposition or a bootstrap of one book does not rest on reproducing a figure measured months ago, while which bars it ran on is part of the reading either way -- `docs/findings/m41-flatten-timing.md` § "The stored rows no longer reproduce".

**Cutting back recovers one root and not the other**, so it is attempted rather than assumed, and `SWEPT_BARS` says per cell which window actually ran. An archive that only grew at the end is recovered by cutting it back; one that gained history earlier moves the 60/40 split and cannot be.

### campaign_annotate.py

Annotates a shortlist's stored trade logs and persists the annotation, so filtering trades is a query.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --root MNQ
./.venv/Scripts/python.exe tools/campaign_annotate.py  --strategy OpeningRange --root MNQ
```

`tools/campaign_review.py` annotates the same logs and discards the annotation. This stores it, keyed by `(sweep_id, combo_id, trade_id)`, and builds `nqbt.results.TRADE_VIEW` over the three tables -- after which "which trades were profitable, taken in an uptrend, by a configuration on a 20-period EMA" is one `SELECT`.

**Parameters come along as a filter and never as a ranking.** Two combinations differing in one axis share most of their entries, so grouping the view's rows by a parameter counts the same trade many times and would make `nqbt.guard`'s null far too tight; `tools/campaign_report.py`'s `axis_influence` is where that comparison belongs. A row that cannot honestly be joined to its bars is skipped, and that is not hypothetical -- see `nqbt.annotate.annotate_trades`' price check.

Every cut a configuration ran at is read off its stored row by name (`LabelThresholds`' fields and `ContextFilterParams`' threshold parameters are the same words). **A stored threshold is the configuration's cut, not a chosen one**: where its filter was inert the pair is the default nobody picked, and a raw pair is a different share of bars at every form and resolution -- `docs/roadmap.md` §M27.8. That is why `nqbt.results.save_annotation` stamps the pair onto every row it writes.

## Reading a campaign

### campaign_report.py

Reads the campaign databases and says which archetype is worth improving.

```bash
./.venv/Scripts/python.exe tools/campaign_report.py
./.venv/Scripts/python.exe tools/campaign_report.py --window selection holdout
```

**It reports distributions, not winners.** The best profit factor in a 300,000-row sweep is a statement about the size of the sweep; the median and the profitable share are statements about the strategy -- `docs/findings/m26-elastic-band.md` § "Selecting on one contract is worse than not selecting".

**Every stored stratum is read, one dimension at a time.** §M27 reported one pooled row per stratum, which is how session phase and relative volume went into the campaign and no finding about either came out -- `docs/roadmap.md` §M27.7 and §M27.8. A cell is only comparable within a resolution, so the dimension tables are cut by it rather than pooled over it. **Every table carries `session_close_share` and `ambiguous_share`**, because a result is read wrong without them: the final session phase holds the forced flat, so a stratification by the clock always shows it as anomalous -- `docs/roadmap.md` §M10.4 -- and `ambiguous_share` is the same obligation at a coarse resolution.

**Pooled over variants deliberately, which is why there is no `--variant`.** The dilution §M28.9 measured is a selection effect and this tool selects nothing; a variant is read on its own in the `by variant` table -- `docs/roadmap.md` §M28.9.

**The one table that ranks carries what its exits were worth**, wherever `tools/campaign_shortlist.py` has stored the log: legs, net P&L and median bars held per exit reason. A share says how often a leg left by one route and never what that route was worth, and on the opening range the two point opposite ways -- `docs/roadmap.md` §M28.9, "The bracket is a net cost, which `session_close_share` cannot say". The decomposition uses `stats.leg_summary` and defines no statistic of its own; an exit reason the log never took is absent rather than zero.

Notes on its helpers, which other tools import:

- **`ratio_to_drawdown`** (net-to-drawdown) is undefined rather than infinite at no drawdown, because an unbounded statistic wins a ranking it was never measured on -- the defect `docs/findings/m27-registry-campaign.md` § "Reading the per-contract tally" records against profit factor.
- **Rank with `rank`, never `DataFrame.nlargest` directly.** `nlargest` pads its result with undefined rows rather than returning fewer, which would hand the null test configurations whose ranking statistic was never measured; `tests/test_campaign_report.py` pins it.
- **Derived statistics are kept apart from `stats.Summary`'s fields**, and **run tags are kept apart from parameters**, so `parameter_columns` never calls a derived statistic or a tag an axis. The two cost fields are tags because they vary with the root and nothing else; reported as axes they would report the root twice.
- **`narrowing`** appends window, variant and resolution clauses to the query, so a database many campaigns deep is read for the rows asked about. A name holding a quote is refused rather than escaped; no stored variant carries one.
- **`load_trades` returns empty rather than raising** when no log is stored, and `stored_logs` serves a stored log and a re-run one through the same mapping, so a caller can name every row without a log instead of stopping at the first.

### campaign_holdout.py

Tests whether a shortlist chosen on the selection window survives the held-out one.

```bash
./.venv/Scripts/python.exe tools/campaign_sweep.py --split --n-jobs 8
./.venv/Scripts/python.exe tools/campaign_holdout.py
```

The question is the one that decides whether an archetype is worth more work: **does picking the best 20 on the first 60% of the series beat not picking at all on the last 40%?** On this project's own data it has come out *below* the median of every configuration -- `docs/findings/m26-elastic-band.md` § "Selecting on one contract is worse than not selecting".

**One row per root and stratum.** A stratum is its own held-out test, never pooled with the others: pooling lets the selection window pick the stratum as well as the parameters, and the twenty largest profit factors then come from whichever stratum has the fattest tail -- `docs/roadmap.md` §M27.4. Variant is not a group key, and the same argument applies to it, so a database holding more than one needs `--variant` -- `docs/roadmap.md` §M27.3. A stratum the split never ran simply has no row.

The windows are joined on `root, resolution, variant, stratum, combo_id`. `combo_id` is the position in a deterministic product and both windows run the same grids in the same order, so equal ids are equal parameters; the paired columns are checked rather than trusted. `held_out` returns rows shaped like `campaign_report.load`'s, so a tool reading stored logs can use it wherever it would use `campaign_shortlist.shortlist`. In `verdict`, a row the ranking statistic is undefined on is not shortlistable and is dropped, so `shortlisted` can come back below the target count and is reported rather than assumed.

### campaign_paired.py

Compares one variant against its control cell by cell, rather than distribution to distribution.

```bash
./.venv/Scripts/python.exe tools/campaign_paired.py --strategy EmaCrossover --control "stop=atr trail=off" --treatment "stop=atr trail=on"
```

`campaign_report.py` compares distributions and `campaign_holdout.py` compares shortlists. Neither answers what an A/B variant asks -- **does switching this one rule on help, holding everything else at the same value?** -- and both are biased when the arms are different sizes: the treatment's extra axes make its shortlist a best-of-more.

So this pairs instead. Every parameter the two arms agree about becomes part of the key, the treatment's own axes are collapsed to their **median** within each cell, and the report is the distribution of within-cell differences. The median is deliberate: the treatment's best in each cell is selection, reported beside the median only so the gap can be seen -- `docs/roadmap.md` § "The build spec's three loose ends, measured". **A cell needs both arms viable**: `load` drops rows under `MIN_TRADES`, so a rule that thins the sample loses cells rather than scoring badly in them, and the pair count is part of the reading.

- **What counts as the rule under test.** A column is under test only if one arm holds it constant while the other varies it, or if the two value sets are disjoint (a toggle). Set equality is *not* the test: `load` can drop a shared axis's value in one arm alone, and reading that as a difference would silently stop keying on the axis and collapse cells that are not the same cell.
- **Cells and rows.** A cell is root, resolution and stratum plus the shared parameters, within one window the caller names. A reported row pools over the stratum, because a variant set run unfiltered has only one. `cell_keys` widens the cell for a caller whose arms span several base variants (`campaign_hold.py`), since `variant` is a tag rather than a parameter.
- **The sign test** is an exact two-sided binomial against a fair coin, written out because it is four lines; a zero difference counts as not improved, the conservative direction. The division stays in integers until the last step, because `2.0 ** total` overflows above 1,023 pairs ([#292]).

### campaign_crossread.py

Reads every stored stratum against the same combination run unfiltered.

```bash
./.venv/Scripts/python.exe tools/campaign_crossread.py
./.venv/Scripts/python.exe tools/campaign_crossread.py --dimension phase --min-score 8
```

`campaign_holdout.py` asks whether a *shortlist* survives, which measures selection as much as the strategy. This asks **does pinning one context filter on beat leaving it off, for the same parameters?** Every filtered row has an unfiltered twin at identical parameters, root, resolution and variant, so the comparison is paired and free of the shortlist-size bias -- `docs/roadmap.md` § "The build spec's three loose ends, measured".

Each pair is scored in **both** windows independently and the cells are counted, never pooled -- `docs/roadmap.md` §M28.14. A cell is one root x resolution; the score is the cells the filter won in both windows minus the cells it lost in both, and a cell that wins one window and loses the other counts for neither. **A score is a consistency check and not a p-value**: the cells are two roots tracking one index at five overlapping bar sizes, nowhere near independent. `tools/campaign_null.py` is what carries evidence.

- **Parameter defaults are read off the archetype.** A sweep predating a parameter leaves its column null, and null is not the value it ran at, so every pair between a row stored before the column and one after would be dropped silently -- `docs/findings/m30-volume-regime-recut.md` is where this cost a campaign.
- **Only variants every plain filtered stratum holds are compared.** A stratum run by a later campaign carries that campaign's variants (OpeningRange's `regime=CONSOLIDATING` holds the fade and rejection arms), so reading it against a breakout-only stratum would report the entry mechanism under the regime's name. Re-cuts are left out of that intersection, not out of the pairing, because each was run over its own variants and would empty the set; a caller whose every filtered stratum is a re-cut states the variants outright.

### campaign_crossroot.py

Runs one root's shortlist on another root, to see whether a configuration travels.

```bash
./.venv/Scripts/python.exe tools/campaign_crossroot.py --top 200 --min-trades 500
```

Every other tool asks whether a configuration survives a different *window* of the same instrument; this asks whether it survives a different *instrument*, a stronger test of the same kind. **Roots are paired by size class** -- NQ to ES and GC, MNQ to MES and MGC -- so the round-turn commission is the same on both sides and only the market changes. The target root's commission is set explicitly rather than inherited from the stored row.

**The ranking floor is the point of the tool.** Ranked on profit factor at the campaign's `MIN_TRADES` of 30, the top of every archetype is small-sample noise -- the median top-200 row holds 43 trades and two thirds hold under 50, and the median profit factor falls from 3.77 to 1.44 as the floor rises to 500. `--min-trades` defaults high for that reason, and an infinite profit factor is dropped rather than ranked first. A variant swept into a stratum is excluded too, since it contaminates a later top-N -- `docs/roadmap.md` § "Standing traps".

**A shortlist also has to be readable.** A row whose fill assumption decided most of its legs is an artefact of `ambiguity_policy` and outranks everything real: OpeningRange's `entry=rejection` rows reach a stored profit factor of 3,955 on 613 trades with one loser, an `ambiguous_share` of 0.89 and trades held under one bar, and 0 of 20 keep a profit factor above 1.00 under the other policy. Rows above `disambiguate.MIN_AMBIGUOUS_SHARE` are dropped before ranking -- `docs/findings/m28-7-rejection-swept.md`. Nothing here is a gate, and no ranking of the output is printed.

### campaign_labels.py

Compares the raw context labels against the fitted ones over the same bars.

```bash
./.venv/Scripts/python.exe tools/campaign_labels.py --dimension regime
./.venv/Scripts/python.exe tools/campaign_labels.py --dimension volume --resolutions 5
./.venv/Scripts/python.exe tools/campaign_labels.py --dimension windows --volume-rolling-bars 10 90
```

A stratum is named for a state and cut by a threshold pair, so a result quoted under a label is a result about a cut. This measures how much of a label survives being re-cut: the share of bars each raw state keeps, and where the rest go. **No sweep and no database**: both cuts are computed here over the spliced series, so this says what two stratifications label differently and nothing about what either earns -- `docs/findings/m30-volume-regime-recut.md` reads it against the paired scores. The fit is taken on the selection window alone, exactly as `campaign_sweep.py` takes it.

### campaign_hold.py

Reads the maximum-hold-time ladder: what each cap is worth against the uncapped arm.

```bash
./.venv/Scripts/python.exe tools/campaign_hold.py --strategy InsideBar --window holdout
```

`campaign_sweep.py --variants hold` runs every archetype's stored grid once per rung, the uncapped `hold=0` arm included, so two rows differ by the cap alone. This pairs each capped arm against that control cell by cell, with `campaign_paired.py`'s machinery. **Never pooled across resolutions**: the cap is a bar count, so every row is one root x resolution with the minutes each rung means printed beside it. **A rung that cannot bind must read as its control**, which is what `bound` measures -- the share of paired cells whose average hold actually moved; a low `bound` with a p-value near 1 is an arm that never fired, not a cap that did nothing. The stratum stays in the pairing key once the ladder has been run inside one, since a pair only forms within a stratum -- `docs/roadmap.md` §M31.1.

### campaign_early_exit.py

Reads the conditional early exit: what each arm is worth against the control with every rule off.

```bash
./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBar --window holdout
./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBarTrailing --stratum phase=MIDDAY --picks
./.venv/Scripts/python.exe tools/campaign_early_exit.py --strategy InsideBar --reproduce
```

`campaign_sweep.py --variants early-exit` runs every archetype's stored grid once per arm, `exit=off` included, so the pairing is `campaign_hold.py`'s: keyed on the base variant, with the same `bound`, and never pooled across resolutions, because the not-working exit is a bar count. **One stratum at a time, unfiltered by default**, since the midday cells were swept beside the unfiltered ones and a row pooling them would mix two strategies. **Beside each arm are the columns the pre-registration reads**, each paired configuration by configuration and then the median taken: trades and commission as the arm's ratio to the control, win rate, average bars held and `session_close_share` as its difference. A ratio of the two arms' medians was the first form, and it can read 1.0 while most pairs lost trades. **`--picks` is §M48's pre-registered verdict**: on each root and bar size the selection window picks the bound arm with the highest median delta, and the pick pays where its held-out delta is positive with the sign test at p < 0.05; a bar size clears where it pays on every root. A root and bar size with no bound arm stays in the table with no pick, so an untested cell is counted rather than dropped. **`--reproduce` is the check that comes first**: every control row joined to its stored campaign twin on the costs and on every parameter the stored rows carry, counting the rows and the statistics that differ. A parameter the stored rows only hold as null was added after they were swept and is left out of the join, and a side holding two rows under one key is refused, because a control row would have two twins. The two reads are exclusive, and neither takes `--window` -- `docs/findings/m48-early-exit-result.md`.

## Testing a shortlist

### campaign_null.py

Places a shortlist's configurations against a matched random entry.

```bash
./.venv/Scripts/python.exe tools/campaign_null.py --strategy ElasticBand --root MNQ
./.venv/Scripts/python.exe tools/campaign_null.py --strategy InsideBar --variant narrow --top 12
./.venv/Scripts/python.exe tools/campaign_null.py --strategy OpeningRange --root MNQ NQ --stratum volume=THIN regime=DIRECTIONAL --draw levels
```

A sweep can say which configuration has the highest profit factor, not whether the **entry** earned it, because a bracket that suits the bars flatters a random entry just as much. The matched null holds the signal count and the time-of-session distribution fixed and randomises the day -- `docs/roadmap.md` §M7a and § "The method that does answer the question". The parameter set is rebuilt from the stored `combos` row, so what is tested is exactly what the sweep ranked. `--top` measures that many and reports **three rankings side by side** -- the observed statistic, the excess over each configuration's own null, and net-to-drawdown -- and where they part, the excess is the one to believe -- `docs/roadmap.md` §M27.3. `profit_factor` and `expectancy` are the verdict; `win_rate` is reported because a mean-reversion entry can beat the null on payoff while losing on frequency -- `docs/roadmap.md` §M26.

**Not every archetype has a matched null, and one that does not exits 2 rather than 0.** An entry whose trigger is a *level* fires on every bar the level exists, which leaves the draw nothing to randomise -- `docs/roadmap.md` §M28.1. That is a gate that could not run, not one that passed, so it gets its own status the way `formatting.cli`'s does. Over a shortlist the status is reached only when every row was refused; a row refused alongside rows that ran is reported as a refusal with no verdict.

**`--draw levels` is the second arm, and the one such an entry can use.** It permutes which session's range is traded instead of which day each signal lands on, so the signal itself is held fixed -- `docs/roadmap.md` §M28.2. The two arms ask different questions, so every measured row carries the `draw` it came from.

**Several roots and strata run as one stated family**, printed before the first cell. A p-value is only readable against how many tests it was one of, and a cell chosen after a consistency score has been looked at is the multiple-comparisons load -- `docs/roadmap.md` §M28.16. A family row is a range rather than a mean, because ten configurations of one cell are ten overlapping runs over the same bars.

**A re-run that is not on the stored row's bars is refused**, before the simulations rather than after, since an extended archive moves the split under every row at once. Each configuration is checked against what the **test window** stored for it -- the bars its sweep ran on, then its trade count and net P&L -- using `campaign_shortlist.py`'s `verify`, so the two tools agree on what reproducing means. A configuration the test window never swept is said out loud rather than taken for agreement. Every measured column is the test window's, including net-to-drawdown. The stored rows are read with their own query rather than `campaign_report.load`, for two reasons: that loader drops rows below `MIN_TRADES`, which a held-out row routinely is -- `docs/findings/m36-ema-pullback-volume-recut.md` § "Gate 3 -- 1 of 120, and it is in the wrong direction" -- and the bar range is neither a parameter nor a statistic, so `campaign_holdout.py`'s `paired` would call it a disagreement. Duplicate keys are refused rather than picked between.

### campaign_contracts.py

Runs one configuration per contract, each against its own matched null.

```bash
./.venv/Scripts/python.exe tools/campaign_contracts.py --strategy InsideBar
```

**Read the consistency across contracts, not the individual p-values**: with nineteen contracts and two roots, one cell clearing 0.05 is the expected output of that many comparisons, while every contract agreeing on the sign is not -- `docs/roadmap.md` §M26. Per contract rather than spliced, because ATR and the moving averages both step at a roll seam and a spliced series hides whether an edge is two good quarters wide. The tally is a sign count on `expectancy`, which is bounded where a profit factor is not -- `docs/findings/m27-registry-campaign.md` § "Reading the per-contract tally".

### campaign_montecarlo.py

Resamples a shortlist's trade sequences, to size the luck in their equity paths.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar
./.venv/Scripts/python.exe tools/campaign_montecarlo.py --strategy InsideBar
```

`nqbt.montecarlo.permutation_test` reorders the same trades, which moves only the path statistics and answers *was this drawdown the ordering's doing*; `bootstrap` resamples with replacement, which moves the values too and answers *how wide is the uncertainty around this figure*. An 87% win rate against a 5:1 loss size is exactly the shape a bootstrap exists to size -- `docs/roadmap.md` §M27.6.

**This is not the matched null and does not replace it.** Both tests take the entries as given, so neither can tell "worse than random" from "no better than random"; that is `campaign_null.py`'s question, and a figure quoted from here without it is half an argument. `nqbt/randomentry.py` drawing 200 samples per comparison makes it look like the same machinery; it is not -- it replaces the entry and holds the ordering. `--held-out` sizes the figure a gate actually reads.

### campaign_walkforward.py

Walks a shortlist forward through several folds rather than one hand-cut split.

```bash
./.venv/Scripts/python.exe tools/campaign_walkforward.py --strategy InsideBar
```

§M27's held-out gate is a single time cut at 60%, so it tests one regime transition. `nqbt.walkforward.walk_forward` re-selects on each training window and measures the winner on the window that follows, which asks whether **picking** survives rather than whether one choice did -- `docs/roadmap.md` §M27.6.

**The shortlist is the candidate pool, not the whole grid**: putting 760,960 combinations through several folds is unaffordable. The cost is that the pool was chosen on stored rows, so a fold result is only clean to the extent the pool did not see the folds -- rank on `--window selection`, or widen `--top` until the pool stops being a selection, before reading one as a verdict. **One walk-forward per resolution**, because candidates at different bar sizes are different frames and cannot be selected between. Every fold is prepared independently, so the warm-up prefix is the longest lookback the shortlist's context declares; **relative volume is the gap**, since its baseline is counted in sessions rather than bars, so raise `--warmup-bars` by hand for a volume-stratified shortlist.

### campaign_exits.py

Re-summarises a shortlist with one exit reason's legs removed, and says what survives.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --held-out
./.venv/Scripts/python.exe tools/campaign_exits.py --strategy OpeningRange
```

`campaign_report.py`'s ranked table says what each exit reason was worth, but not what is left without one: net P&L is additive and profit factor and drawdown are not, so "the flatten earned +57,256 against a bracket of −32,458" leaves unasked whether the rest of the book stands up. This drops one reason's legs and runs `nqbt.stats.summarise` over what remains -- `docs/roadmap.md` §M28.12 and §M28.15. Each half reports trades, profit factor, net P&L and drawdown; trades because a residual book below the trade floor is not a result at all. Both the residual profit factor and its net-to-drawdown have to clear 1.0, the thresholds `campaign_holdout.py` uses for the whole book.

**It is a decomposition and not a counterfactual.** A leg the clock closed is a leg the stop did not take, so nothing here supports "remove this half and keep the other"; what it supports is whether a configuration's result rests on one exit reason. **Every figure is `summarise`'s**, over subsets, so the whole-log column reproduces the stored row exactly and `verify` refuses a stored log where it does not. A re-run log (`--rerun`) is not held to that, because the archive can have moved under the row.

### campaign_ambiguity.py

Re-runs a shortlist under both ambiguity policies and reports the spread.

```bash
./.venv/Scripts/python.exe tools/campaign_ambiguity.py --strategy OpeningRange --root MNQ
./.venv/Scripts/python.exe tools/campaign_ambiguity.py --strategy OpeningRange --window holdout
```

Nothing in a profit-factor ranking stops it picking a configuration whose profit factor is an artefact of `ambiguity_policy`: where an archetype resolves many bars by assumption, that is where the largest profit factors are -- `docs/roadmap.md` §M28.2. `ambiguous_share` counts how often the assumption was invoked, not how much the answer depends on it, so this re-runs each row under the second arm too and reports the **spread** between the two profit factors, the band the bar data cannot narrow -- `docs/roadmap.md` §M28.3.

**The ranking policy stays what every stored row was measured under, and nothing here re-orders a shortlist or drops a row.** The policy is forced rather than read from the row, so a configuration carrying anything else fails `verify` instead of reporting a spread between two arms neither of which is NT8's. The second arm is deliberately more pessimistic than NT8, so selecting on it would select against a fill rule the prime directive rejects -- `docs/roadmap.md` § "Eleven strata per root, one dimension at a time". It is attribution, not selection.

Where the spread is wide enough to matter, a **third step settles it**: `nqbt.disambiguate` reads the minute bars inside each ambiguous bar and says which level price reached first, and the shortlist is re-summarised with every settled bar corrected. It runs only above `disambiguate.MIN_AMBIGUOUS_SHARE`, since below it the assumption cannot have decided the verdict, and it never touches the simulation -- `docs/roadmap.md` §M28.4. A third arm, every ambiguous bar resolved for the trade, exists only so a bar settled as target-first has an outcome to be taken from; it is never reported on its own -- `nqbt.disambiguate.ARM_FOR`. Each row re-runs on the bars its own `window` names, so the first arm reproduces the stored figure exactly.

### campaign_review.py

Reads a shortlist's realised trades by the clock, and guards what that turns up.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy InsideBar --window holdout
./.venv/Scripts/python.exe tools/campaign_review.py --strategy InsideBar --window holdout
```

Filtering entries to a phase and re-running the grid answers *does this strategy work if it only trades then*. The other question -- *when did these trades actually happen, and what was true when they did* -- is `nqbt.review`'s, and needs the per-trade logs the sweep discards -- `docs/roadmap.md` §M27.7. Two things come out of one annotation:

- `nqbt.review.time_of_day` in session order, with **both forms of volume beside it**: relative volume says whether an hour was unusually busy and absolute volume whether there was anything there to trade -- `docs/roadmap.md` §M27.8. `session_close_share` is in the same table, because the forced flat makes a poor late-session result the clock's until that column says otherwise.
- `nqbt.guard.guard` over the clock and the three volume labels together. A stratum picked by reading a table is the multiple-comparisons machine one level up, and `nqbt.guard.FAMILY_COLUMN` answers it. The family is named rather than taken from `nqbt.review.stratifiable`, which would add every moving-average gate and dilute the null with conditions nobody asked about.

**A simulated log is expected to land outside its bar by at most the run's slippage**, which is the default `--price-tolerance`, and on this project's own shortlists it does not: a profit target a bar gapped through fills at the target and lands further out. Widen it deliberately (the widening is printed), but not past the point where a back-adjusted series would still be caught -- `docs/roadmap.md` §M27.7.

### campaign_flatten.py

Re-runs a candidate at several `ExitOnSessionCloseSeconds` and says what the timing is worth.

```bash
./.venv/Scripts/python.exe tools/campaign_flatten.py --strategy InsideBarTrailing --root MNQ NQ --stratum phase=MIDDAY --variant trailing --resolution 1 2 5 10 15
```

In a backtest the property is inert -- NinjaTrader flattens on the session's last bar whatever the script sets, which is why `nqbt.sessions.EXIT_ON_CLOSE_SECONDS` is one default rather than a per-archetype field -- `docs/nt8-fidelity.md` §M22. **Live it is not inert**, so for a strategy whose P&L is carried by session-close legs the value the C# ships decides trades Strategy Analyzer can never show moving. The simulator takes the cutoff, so the same configurations run at the backtested value and the live one over the same bars.

The cutoffs are 30, 180, 300 and 900 seconds, control first. `30` is what every stored row was swept at and what both stop-market ports set; `180` is what `InsideBar.cs` and `InsideBarTrailing.cs` set, so it is what a live account does; `300` is a whole 5-minute bar, there because 180 cannot be expressed on a 5-minute series and the truth sits between those two rungs; `900` binds at every campaign resolution, which separates "the live cutoff is too small to see" from "this book does not care when it is flattened".

**The pairing is exact**: each rung re-runs the same configurations on the same bars, and `moved` says whether a rung fired at all (a cutoff shorter than the last bar reproduces the control, which above 2-minute bars is most of the ladder). **The control rung is reconciled against the stored row and the agreement is reported rather than required**: the ladder is a within-run comparison, but the levels are this run's rather than the registry's once that figure has moved, and `reconcile` says so. What it returned: `docs/findings/m41-flatten-timing.md`.

### campaign_sizing.py

Fits the cuts a confluence size runs at, on every archetype, and reads it against its own sizes shuffled.

```bash
./.venv/Scripts/python.exe tools/campaign_sizing.py fit --strategy ElasticBand --resolutions 2 5 10 15
./.venv/Scripts/python.exe tools/campaign_sweep.py --strategies ElasticBand --variants confluence-sizing --split --strata confluence-sizing --resolutions 2 5 10 15
./.venv/Scripts/python.exe tools/campaign_sizing.py null --strategy ElasticBand --root MNQ --resolution 5 --variant "target=0.0s size=confluence"
```

**Everything `fit` measures comes from the selection window**, so the held-out window reads cuts it had no part in. Each cut is taken per root, resolution and stored variant, at the variant's base configuration over its unfiltered signal, pooled over the sides the variant sweeps (a variant sweeping `direction` trades both sides of one signal, and a share read on one side alone would be the other's complement), and written before any sizing arm runs: the file is the pre-registration of every threshold the arms read -- `docs/findings/m47-confluence-sizing-preregistration.md`. **A cut already in the file is kept**, so the arms stored against it keep the cut they ran at; one stored before the fit read its symmetric labels gains them at its own thresholds, and nothing else in it moves. InsideBarTrailing is the default strategy, and there the null reads §M45's confluence arm unless `--variant` names another -- `docs/findings/m45-ibt-sizing-preregistration.md`. The regime and volume labels are cut at the 20% and 80% quantiles, the campaign's own regime pair and one of its volume tails, so a sizing label and a stratum mean the same thing -- `docs/roadmap.md` §M27.5 and §M27.8. A label favouring more than 90% (or fewer than 10%) of the fitted signals is dropped from the add-only count: near-constant at the signal, it adds the same contract to almost every trade and sorts nothing, as `above_ema_21` did for EmaCrossover -- `docs/findings/confluence-count-per-trade.md`. The symmetric arm keeps a label unless one step it moves the count by covers more than 90% of the same signals: up where it favours, down where it opposes, none where it does neither. The share of trades whose signal bar was early is counted over trades taken rather than signals, because a setup arriving while a position is open is never traded.

**The shuffled-size null is the control a confluence size needs**, and a matched random entry is not: the entries are the rule's own and only which size each signal took is permuted, so it measures whether the count put the larger sizes on the better trades. On InsideBarTrailing a size moves the trades, so each shuffle is re-simulated across the signals. Everywhere else it moves only the dollars -- `docs/findings/m46-registry-size-ladder.md` -- so each shuffle permutes the sizes across the trades actually taken and recomputes their money exactly, and both halves of that premise are checked on every configuration before a shuffle is drawn.

### geometry_contribution.py

Splits each bracket geometry's result into what the geometry does and what the entry adds.

```bash
./.venv/Scripts/python.exe tools/geometry_contribution.py out.csv
```

A sweep says which stop/target combination has the highest profit factor, not whether it *earned* it: a bracket that suits the bars flatters a random entry just as much, and on the elastic band observed profit factor correlates +0.71 with the matched null's across geometries. Ranking geometries on profit factor therefore ranks mostly the bars. This holds the entry fixed, varies only the exit geometry, and reports both terms: `null_median`, what the geometry yields with no entry edge, and `observed - null`, what the entry adds. The two can rank geometries in **opposite** orders, and where they disagree the excess is the one to believe -- `docs/findings/m26-elastic-band.md` § "The method that does answer the question".

Three of the four schemes are §M26's; `D-band` is the stop on the channel the entry was measured against. Its depth past `entry_std` sets the reward-to-risk directly -- its R is `entry_std / (entry_std + depth)` wherever the target is the basis -- rather than through two different volatility measures -- `docs/roadmap.md` §M26.8. The tool is archetype-agnostic in shape: rewrite `geometries` for another archetype, and **choose the entry settings before looking at any result**, or it measures the selection effect it exists to expose.

### campaign_gates.py

Runs every per-cell read of a swept variant set over every cell, from one load per archetype.

```bash
./.venv/Scripts/python.exe tools/campaign_gates.py --variants ibt-sizing --resolutions 5 --out <dir> --n-jobs 6
./.venv/Scripts/python.exe tools/campaign_gates.py --variants ibt-sizing --resolutions 5 --out <dir> --reads gate4 --cells <csv of strategy, root, resolution, variant and stratum>
```

It loads the variant set's rows once per archetype, re-runs each shortlisted configuration once on the bars it was swept on, and hands that one log to every read. **The reads are the per-cell tools' own functions**, given what their command lines give them for one arm, root, resolution and stratum, so a cell read here and read there agree wherever both run on the same bars:

- `gates`: gate 1, `campaign_report.profile` on the selection window, and gate 2, `campaign_holdout.verdict`;
- `paired`: `campaign_paired.paired` held out, stratum by stratum, over the pairs `controls` reads off the arms' names;
- `null`: `campaign_sizing.shuffled_null` on the held-out shortlist of every arm whose base sizes on a confluence count;
- `gate4`: `campaign_montecarlo.resample_row`, `campaign_exits.measure_row` and `campaign_walkforward.run_resolution`, on the cells `--gate4-strata` and `--cells` name;
- `prop`: `campaign_propaccount.replay_shortlist` over the four presets, on the cells `--prop-strata` names.

Every re-run also writes what it reproduced of its stored row, and on which bars, which is read before anything else -- `campaign_swept.reconciliation`. The archive is cut back at the newest bar the task's rows were swept on, where the per-cell tools cut at the newest their root stored anywhere: the same bars unless one database holds campaigns swept on archives of different lengths.

The tables land under `--out`, one file per archetype, root, resolution and arm, and each task records the strata every read has written. A run reads only what is missing, so an interrupted run resumes where it stopped and a later one adds reads or `--cells` without repeating any; one `--out` holds one set of settings and refuses a run asking for others. **Only this process opens a database**, and only once the sweep has stopped writing it, because `nqbt.results.connect` opens a file read-write. A worker that dies breaks its pool for good, so each archetype gets a pool of its own.

## Prop-firm accounts

### campaign_propaccount.py

Replays a shortlist's trade logs through a prop firm's account rules.

```bash
./.venv/Scripts/python.exe tools/campaign_shortlist.py --strategy OpeningRange --held-out
./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy OpeningRange
./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy InsideBarTrailing --stratum phase=MIDDAY --resolution 5 --quantities 3 4 6 8
```

`nqbt.propaccount` answers what no gate in §M27 or §M28 can express -- **not "is the edge real" but "would the account have survived it, and made more than it cost"** -- so a cell can be put through an account the way it is put through a null -- `docs/roadmap.md` §M28.13. The shortlist is always chosen on the selection window and replayed over the held-out one, which is why there is no `--window`. By default it reports four presets, Apex and TopStep at 50K and 150K, the four §M28.13 read the registry through; TakeProfitTrader ships as six presets covering two phases each, a table three times the size for a question about one cell.

**The attempt cap must not bind, and by default it cannot.** §M28.13's population run capped attempts at five, which bound on 98% of configurations and truncated their net figures badly enough to be wrong in sign: a blown account costs its fees and not its trading losses, so stopping early hides the wins that come after. `capped` says on every row whether the cap was reached.

**Nothing here is a ranking.** `net` rewards variance and can put a configuration that loses money as a strategy above one that makes it, because each blown account caps the loss at the fee -- `docs/roadmap.md` §M28.13, "The reset economics subsidise a losing strategy". Read it beside the profit factor and the pass rate. The verdict gives medians of the attempt counts and net, and *shares* for `ever_passed` and `profitable`, since both are yes-or-no per configuration and a median of a boolean says nothing. `pass_rate` is not printed because `passes` and `attempts` both are.

**`--quantities` re-runs the shortlist once per contract count** and replays each, because position size decides an account and a stored log holds only the size it was swept at -- `docs/findings/m28-13-account-read.md` § "The binding constraint is position size, not the strategy". Every rung is a re-run, since on InsideBarTrailing the size moves the trades themselves -- `docs/nt8-fidelity.md` §M45. The contracts each trade actually put on are reported: the trailing threshold divided by the dollar value of a point is the whole account's room to move. A row whose rules refuse a size -- InsideBarTrailing's 0.6 split leaves no second lot below three contracts, and a bracket with several targets needs a contract for each -- is named rather than dropped.

### campaign_propobjectives.py

Ranks a campaign's configurations by what a prop account is scored on, then reads them held out.

```bash
./.venv/Scripts/python.exe tools/campaign_propobjectives.py --strategy OpeningRange --root MNQ NQ
```

`campaign_propaccount.py` replays a shortlist chosen by profit factor. This chooses it by the account objective itself -- pass rate, fees per pass, time to the first payout and funded life -- and replays it on the held-out window beside the profit-factor shortlist it is measured against. **Every objective ranks on the selection window and is read on the holdout.** An objective whose event never happened takes the value that ranks it last (fees per pass and days to payout are infinite, funded life is zero); one the preset does not answer is `nan`. What each objective means and which presets answer which: `docs/findings/m40-prop-objectives.md` § "What each objective measures".

The pool it ranks is the top `--pool` distinct configurations by stored selection-window profit factor, because every configuration has to be re-run to be replayed. The maximum-hold arms are left out, a configuration stored under two variant names at one bar size enters once at its higher rank, and a row the fill assumption could have decided is left out entirely -- `docs/findings/m40-prop-objectives.md` § "The pool, and the archive it was re-run on". It re-runs every log on the archive as it stands and stores none of them.

## Reconciling against NinjaTrader

Reasoning, results and traps for every reconciliation are in `docs/nt8-fidelity.md`; these tools are the mechanism. Each takes an export from a NinjaTrader run and compares it against nqbt.

### reconcile_nt8.py

Compares a Strategy Analyzer Trades export against an nqbt run, leg for leg.

```bash
./.venv/Scripts/python.exe tools/reconcile_nt8.py <export.csv> <config> <contract> [from]
```

`config` is a key of `CONFIGS`: usually an archetype's name, but one archetype can have several reconciled configurations at different parameters and bar sizes. `from` is an optional ISO date that trims the export. It is needed whenever NT8 was asked for more history than the contract has, because NT8 then serves its *merged* series, which a per-contract archive cannot reproduce -- `docs/nt8-fidelity.md`, "Reconciliation result -- InsideBar". Both ends of the export are excluded from the comparison: NT8 warms indicators from bars before the export starts, and the export can stop before the backtest did.

The export is stamped in NinjaTrader's display time zone -- the machine's, `Europe/London` -- not UTC. That is set explicitly rather than inferred, because a wrong zone shifts every trade by a whole hour and still parses -- `docs/nt8-fidelity.md` § "Sessions".

### reconcile_higher_timeframe.py

Compares `NqbtHigherTimeframeProbe`'s export against nqbt's higher-timeframe projection.

```bash
./.venv/Scripts/python.exe tools/reconcile_higher_timeframe.py <..._primary.csv> <contract> [from]
```

The companion `_coarse.csv` is found beside it, and `from` trims the export for the reason `reconcile_nt8.py` gives. Four questions, reported separately because they fail for different reasons -- `docs/roadmap.md` § "Multi-timeframe moving averages":

1. **Anchoring** -- does NinjaTrader cut the coarse series where `resample.py` cuts it?
2. **Seeding** -- does `EMA(Closes[1], n)` match `indicators.nt8_ema` on a *secondary* series? Computed over NT8's own coarse closes, so a failure is seeding and not anchoring leaking in.
3. **Projection** -- which coarse bar does a 1-minute bar read? A trade list cannot answer this one.
4. **Warm-up** -- how long before the secondary series is readable, against nqbt's `UNDEFINED`. Counted over **the probe's own bars**, never the archive's: the two rarely start at the same minute, and reading the archive once compared 59 leading bars against 5 and called it a disagreement.

Where the two series stop disagreeing is named rather than counted, because a long disagreeing prefix followed by exact agreement is NT8's merge boundary, the expected shape. The projection runs the coarse stamps through `nqbt.higher_timeframe.project` itself, so NinjaTrader is compared against the shipped code path rather than a second implementation; it works in seconds because float64 carries 1.8e9 exactly and 1.8e18 does not, and it passes `dtype=` on both conversions because `read_csv` hands back microsecond stamps and reading those as nanoseconds puts every bar in 1970. The archive is clipped to the probe's span, so an archive running past where the export stopped is not reported as a disagreement.

### reconcile_order_lifetime.py

Reads an `NqbtOrderLifetimeProbe` run and answers the order-lifetime questions from it.

```bash
./.venv/Scripts/python.exe tools/reconcile_order_lifetime.py <..._events.csv>
```

The companion `_bars.csv` and `_config.csv` are found beside it. Each measurement is reported separately, and one the run carries no data for is reported as such rather than silently passing. **Nothing here assumes the callback lag; every run re-measures it.** A probe callback reports `CurrentBar`, which for an order resolved against the *next* bar's prices is one behind the bar it filled on, because Strategy Analyzer processes those fills before calling `OnBarUpdate`. The session-close exit does not lag. Reading one rule as the other moves every conclusion by a bar, so both are checked against price first. A one-bar lifetime is the whole finding for a three-argument entry, so offsets are printed exactly where the distribution is short and as a range where an until-cancelled order spreads over hundreds of values. Findings: `docs/nt8-fidelity.md`, "Order lifetime and the session edge".

### compare_exports.py

Diffs two folders of NT8 minute exports, contract by contract.

```bash
./.venv/Scripts/python.exe tools/compare_exports.py [baseline_dir] [candidate_dir]
```

Built to answer whether pulling bars through `BarsRequest` (the AddOn) returns anything the manual Tools -> Historical Data export does not. Manual exports gain and lose whole sessions between runs, so "different" is expected; what matters is which direction and where. Defaults to `data/minute` against `data/addon`, and is read-only. It tests for a whole-hour shift explicitly, because a time-zone mistake in an exporter moves every bar by whole hours and errors nowhere: undo the shift, and if the bars then agree the data is fine apart from one constant.

## The regression gate and CI

### capture_trade_logs.py

Captures every trade-log producer path to CSV, for comparison across a refactor. It is the regression gate for anything touching the simulation; the procedure is `CONTRIBUTING.md` § "The trade-log regression gate", and the traps are in `.claude/rules/regression-gate.md`.

```bash
./.venv/Scripts/python.exe tools/capture_trade_logs.py before
# ...make the change...
./.venv/Scripts/python.exe tools/capture_trade_logs.py after
./.venv/Scripts/python.exe tools/compare_trade_logs.py before after
```

It was written for M9, which moved validated code and had to prove it had not moved a number, and kept as a tool because M15 needed the same gate and a stronger one -- `docs/roadmap.md` under M9 and M15. The five paths cover what a single run does not:

1. the pinned MNQ 03-24 reconciliation window, under the two settings that reproduce the stored MNQ 03-24 reconciliation capture (see `verification/README.md`) -- do not "modernise" them;
2. the same contract at current fidelity settings, with costs applied;
3. the same bars through the NQ spec, which proves instrument scaling is untouched;
4. a real sweep over spliced continuous bars, serial *and* parallel, since the parallel path memmaps the dataset and could diverge on its own;
5. every other registered archetype on the same contract, at its defaults and `costs.LIVE`, one log each, since the first four run DeadCatBounce's loop alone (#376).

The fifth reads the registry rather than a list of names, so registering an archetype is what gates it. It stops with `EmptyCaptureError` when an archetype trades nothing at its defaults, because an empty log compares identical whatever the change. It runs before anything is written, and a capture first deletes the files an earlier one left in its directory, so a refusal leaves nothing to compare and an unregistered archetype's old log cannot pass as present.

**It deletes numba's `.nbi`/`.nbc` cache files before each capture.** `cache=True` does not track cross-module dependencies, so a change to `bracket.py` leaves every archetype's compiled loop holding the old inlined fill rules, and a capture over them compares new source against old machine code and passes because the change never ran. Measured on the ambiguity policy: identical source, caches deleted, different trade log.

Every frame is written with `float_format="%.17g"`, which is explicit but is *not* what makes the gate exact: `compare_trade_logs.py` reading with `float_precision="round_trip"` is, and either writer is exact against that reader. 17-digit text against pandas' *default* parser is worse than the default writer -- measured in #113. An earlier claim here, "4 of 1,664 `r_multiple` values", was measuring the reader and attributing it to the writer.

### compare_trade_logs.py

Compares two captures from `capture_trade_logs.py`, and exits non-zero on any difference so it can gate a script.

```bash
./.venv/Scripts/python.exe tools/compare_trade_logs.py before after [--added col ...]
```

With no `--added` it demands identity, the gate for a refactor meant to preserve behaviour exactly. A file missing from `after` fails; a file only in `after`, such as a newly registered archetype's log, is listed as new and not compared. `--added` names columns the change is expected to introduce; every other column must still match exactly, dtypes included (M9 used `--added source instrument direction`). It reads with `float_precision="round_trip"`, the other half of the `%.17g` the capture writes: pandas' default CSV parser is not correctly rounded and folds adjacent float64 values together, so a bare `read_csv` cannot see a one-ULP difference however many digits were written.

### trade_log_gate_ci.py

Decides whether a pull request runs the trade-log gate, and whether its result passes. Its caller is `.github/workflows/trade-log-gate.yaml`.

```bash
git diff --name-only --no-renames BASE HEAD | python tools/trade_log_gate_ci.py applies
python tools/trade_log_gate_ci.py verdict --status N --output compare.txt --labels '[...]'
```

### lint_commit_messages.py

Checks commit messages against `CONTRIBUTING.md` § "Commits". It exits 1 when any error-level rule fails; warnings never fail the run, and `--github` emits workflow annotations alongside the text. Two callers check different text:

```bash
# what GitHub squashes onto main -- the PR title, plus the suffix it appends
python tools/lint_commit_messages.py --subject-suffix " (#165)" --message-file pr.txt
# every commit on the branch, NUL-separated on stdin
git log --format=%B -z origin/main..HEAD | python tools/lint_commit_messages.py --stdin
```

### submodule_tree_payload.py

Builds the `POST /git/trees` body that moves submodule pointers to new commits. A submodule is a tree entry of mode 160000 holding a commit id rather than a blob, which is why the blob-only endpoints cannot move one; `.github/workflows/bump-submodules.yaml` has the rest of the reasoning.

### numba_tuple_probe.py

Asks whether a `NamedTuple` can carry a jitted loop's parameters without cost or losing the disk cache -- the question #59 turned on. The answer is a property of the installed numba rather than a language guarantee, so re-run it before relying on it, and **run it twice**: only the second run can report a cache *hit*. It checks three claims, one per section of its output:

1. a `NamedTuple` argument gives a bit-identical result at the same speed as loose scalars;
2. a blob carrying **arrays** compiles and caches too, which is what `bracket.Bars` is;
3. `cache=True` only *reuses* its cache when the blob type is importable -- a `NamedTuple` defined in `__main__` writes a cache and then misses it on every run, silently, which is why the blobs live in `nqbt.sim.bracket` and not beside the loop that reads them.

## Documentation

### findings_index.py

Generates the findings register's three index views from each file's front matter.

```bash
./.venv/Scripts/python.exe tools/findings_index.py
./.venv/Scripts/python.exe tools/findings_index.py --check
```

It reads the YAML front matter of each file in `docs/findings/` and writes `register.md`, `by-archetype.md` and `by-gate.md` beside them; the hand-written `README.md` is not touched. `--check` exits 1 when a generated file is out of date, which `tests/test_findings_index.py` runs. The views are generated rather than hand-maintained -- `docs/roadmap.md` § "Documentation must not carry a figure that goes stale".
