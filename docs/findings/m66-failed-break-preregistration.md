---
title: "M66 — pre-registration: FailedBreak's first campaign"
archetypes: [FailedBreak]
issues: [355]
gates: [1, 2, 3, 4]
outcome: spec
verdict: >-
  Written and committed before the sweep started: FailedBreak's 18 variants of 64 combinations in all 23 strata, at 1 to 30 minutes on both roots, through the four gates. The entry clears for a level and stratum where a configuration with at least 100 held-out trades beats a matched random entry at a family-wise p below 0.05 on each root; the setup's claim about its levels holds where the rule beats a same-width level placed at random, family-wise on each root, §M60's bar; the re-break exit earns its place on §M37's paired bar. FailedBreak is a candidate only if one level, bar size and stratum pass the entry, the level test and gate 4 together.
---

# M66 — pre-registration: FailedBreak's first campaign ([#355])

[§M66](m66-failed-break-spec.md) specified and built FailedBreak: a close back inside yesterday's, the overnight or the first-hour range after trading through it, entered at market on the next open. This is its first campaign. It runs the four [gates](../../README.md#gate), and two tests the setup's own claims need: whether its levels do better than levels placed at random, and whether the exit on a re-break earns its place.

**What has changed**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: this is a new archetype rather than a parked one, and [§M66](m66-failed-break-spec.md) § "Why this is not the parked fade again" says how it differs from the nearest thing already measured.

**This file was written and committed before the sweep started.** The arms, the strata, the bar sizes, the bars and the predictions were all chosen before any of it ran.

## What was already known

- **§M66's count of signals and bracket distances** on the selection window. No trade was simulated for it.
- **Trade counts on MNQ 03-24 at the defaults**, from [#513]'s check: 27, 31 and 47 trades at the three levels, against 26, 28 and 46 for one random draw. That contract is inside the selection window. No profit or loss was read, and nobody has opened the log the trade-log gate stores.
- **Every other archetype's results on the same holdout**, including [§M28.5](m28-5-fade-bracket.md)'s and [§M28.7](m28-7-rejection-swept.md)'s on the two OpeningRange reversal entries.

## What will be run

|                 |                                                                                                           |
| --------------- | --------------------------------------------------------------------------------------------------------- |
| **Arms**        | 18 variants: three levels × three target schemes × the re-break exit on and off                           |
| **Grid**        | 64 combinations each: `direction` × `max_sweep_minutes` × `stop_offset_ticks` × `max_signals_per_session` |
| **Strata**      | all 23, one context dimension at a time                                                                   |
| **Resolutions** | 1, 2, 5, 10, 15 and 30 minutes                                                                            |
| **Roots**       | MNQ and NQ, spliced continuous                                                                            |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                              |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                               |
| **Size**        | 635,904 combinations, both windows counted                                                                |

```bash
uv run tools/campaign_sweep.py --strategies FailedBreak --split --strata all --n-jobs <workers>
```

**Run time, scaled rather than measured.** No FailedBreak sweep has been timed. At the rates EmaCrossover, the other market entry, recorded in the October 2026 re-sweep on a 32-core VM, this sweep takes about 40 minutes there, most of it at 1 and 2 minutes, or about 8 hours on two workers at the 11.5× that VM measured. FailedBreak's own loop may run faster or slower, so read it as ±50%, a judgement rather than a measurement. The reads in items 5 and 6 come to at most 282,000 simulations, which §M60's timings on OpeningRange, 9 to 25 ms at 15 and 5 minutes, put at a few core-hours, more if the shortlists hold 1- and 2-minute rows. Gate 4, if it runs, took about an hour on two workers for two cells ([#439]). The prop replay in item 9 is the one wide figure: the project's own estimates run from under a second to over a minute per replay, so its 8,640 replays could take under an hour or about half a day on that VM. It runs last and decides nothing, so it can be cut without touching a verdict.

## What will be read

A level's arm is its six variant names, ranked as one pool, so a shortlist can say which level it came from without the selection window picking the level as well. `<the level's six names>` below means, for `yesterday`, each of `yesterday target=<scheme> rebreak=<on|off>`.

1. **`session_close_share` first, per variant, root and bar size**, on the selection window, from the read in item 2, as §M66 asks, before any return. A far target that is rarely reached turns the setup into a directional hold the clock closes.

2. **Gate 1, §M27's:** the share of unfiltered configurations with a profit factor above 1 at 30 trades or more, per variant, root and bar size on the selection window, with `tools/campaign_gates.py --variants campaign --strategies FailedBreak --resolutions 1 2 5 10 15 30 --reads gates --out <folder>`. A cell clears where a majority is profitable.

3. **The axes, as description:** eta-squared on held-out profit factor, unfiltered, per root and variant, with `campaign_report.eta_squared` over the stored rows: once over all bar sizes, and once within each of 15 and 30 minutes.

4. **Gate 2, per level:** `tools/campaign_holdout.py --strategies FailedBreak --variant <the level's six names>`, its `passes` per root and stratum. A level and stratum clears where it passes on both roots.

5. **Gate 3, the entry, per level.** Each level's family is the unfiltered stratum whatever gate 2 says, plus every stratum clearing gate 2 on both roots, at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. So at most 21 cells and 210 tests. Each root's best five by selection-window profit factor, measured on the holdout against the matched random entry over bars, 200 draws, where each drawn bar carries a real signal's stop and targets:

   ```bash
   uv run tools/campaign_null.py --strategy FailedBreak --root MNQ NQ --window selection --test-window holdout \
       --top 5 --iterations 200 --variant <the level's six names> --stratum <the family> --out <its table>
   ```

   **A cell passes where, on each root, at least one of its five configurations beats its null at p ≤ 0.05**, the bar earlier campaigns read, so the result can be set beside theirs. A configuration significantly worse than random does not count, and neither does one with under 100 held-out trades, because a cell cleared on 14 trades (§M35) or 31 (§M19.3) has settled nothing. **That bar passes about one cell in 21 by chance alone**, so **the verdict reads the whole family at once**, with `tools/campaign_null.py --family-of <the three levels' tables>` over at most 210 tests: **a cell clears where, on each root, a counted configuration reaches a family-wise p below 0.05** ([§M54](m54-family-wise-null-preregistration.md)). A draw `randomentry` refuses for too little room leaves the cell unanswered, and it is reported as that rather than as a fail.

6. **The level test, unfiltered.** The setup's claim is that obvious levels are where the stops are, and item 5 does not test that, because a drawn bar keeps the real level's geometry. So the whole rule is re-run against a moved level, per level and bar size at 2, 5, 10, 15 and 30 minutes, each root's top ten on the selection window, measured on the holdout, 400 draws, from seed 0 under each draw, as in [§M60](m60-level-kind-null-preregistration.md):

   ```bash
   uv run tools/campaign_null.py --strategy FailedBreak --root MNQ NQ --stratum unfiltered \
       --variant <the level's six names> --resolution <minutes> --window selection --test-window holdout \
       --top 10 --iterations 400 --draw <kinds|levels> --out <its table>
   uv run tools/campaign_null.py --family-of <that draw's 15 tables>
   ```

   That is 300 tests per draw, and 1 minute is left out because one-minute overnight ranges are patchy on NQ (§M66). `kinds` places a level of the same width at random around the price, and `levels` uses another session's. **A level and bar size clears a draw where, on each root, at least one of its ten configurations reaches a family-wise p below 0.05**, §M60's bar. **The claim holds where `kinds` clears**; `levels` is read beside it, and §M60's table says what each combination means. A refused draw leaves that level and bar size unanswered rather than failed, and an unanswered cell cannot make FailedBreak a candidate.

7. **The re-break exit, paired.** `tools/campaign_paired.py --strategy FailedBreak --control "<level> target=<scheme> rebreak=off" --treatment "<level> target=<scheme> rebreak=on" --stratum unfiltered --window <selection|holdout>`. **It earns its place at a level, scheme and bar size where, on both roots, the median profit-factor change is positive and the sign test reaches p < 0.05 in both windows**, §M37's bar. Nine pairs × six bar sizes is a family of 54. The size of each gain is reported beside it, because §M48 found a sign test over configurations sharing their trades calling gains under 0.005 significant.

8. **Gate 4, only on what passes item 5.** For each passing configuration, its variant, bar size and stratum **on both roots**, each root's selection-window top 20 re-run held out: `tools/campaign_gates.py --variants campaign --strategies FailedBreak --resolutions <minutes> --reads gate4 --gate4-strata <those strata> --out <folder>`. That command reads every arm at those bar sizes and strata, and only the named cells are read from its output. **A cell passes if, on both roots, all three of [§M63](m63-ema-pullback-confirmation-gate-4-preregistration.md)'s reads pass**: the walk-forward pools above a profit factor of 1.0, the median configuration's bootstrap 5th percentile is above 1.0, and without its session-close legs the median configuration keeps a profit factor and a net-to-drawdown above 1.0. If nothing passes item 5, gate 4 does not run, and the result says so.

9. **The prop replay, last, reported, deciding nothing:** `tools/campaign_gates.py --variants campaign --strategies FailedBreak --resolutions 5 10 15 --reads prop --prop-strata unfiltered --out <folder>`.

**Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## The verdict

**FailedBreak is a candidate only if one level, bar size and stratum pass together**: a configuration there clears item 5 family-wise, that level and bar size clears `kinds` in item 6, and its variant, bar size and stratum pass gate 4 in item 8. Item 6 is read unfiltered and does not run at 1 minute, so a 1-minute pass cannot make it a candidate. Clearing item 5 alone says the entry beats a random entry; it says nothing about stops resting at the level, which is the reason [#355] gave for building it. Anything less leaves it registered and parked, `TIER1_ONLY`.

## Predicted before the run

- **`session_close_share` is highest under `opposite+next` and lowest under `R`**, in every level, root and bar size on the selection window. §M66 measured a first target of 89 to 210 points against a stop of 6 to 48.
- **No cell clears gate 1 at 1 or 2 minutes**, where §M66 found price chopping around the level and the median stop is smallest.
- **Over all bar sizes, within each variant, bar size or `direction` is the largest axis on every root. At 15 and at 30 minutes `stop_offset_ticks` is the smallest of the four**, since 16 ticks is 4 points against a median stop of 27 to 48 there.
- **Item 5 fails unfiltered at all three levels**, at most one of the 21 possible cells passes, which is about chance, and none clears family-wise. Few cells in the registry clear this test on both roots, and most that do are OpeningRange's (§M28.16, §M61).
- **No level and bar size clears `kinds`**, as nothing did on OpeningRange (§M60), and at most one clears `levels`.
- **The re-break exit clears §M37's bar in none of the 54 cells**, because §M48 found a market exit costs wherever it can close a winner.
- **So FailedBreak is not a candidate.**

## What this cannot settle

- **The holdout is new to FailedBreak and not to the project.** Other archetypes' results on it shaped which setups were worth building, and [§M28.9](m28-9-survivor-tradeability.md) finds the most recent year different from the rest, so a pass is still partly a bet on that year's regime changing. Item 5's strata are also picked by a read of the holdout and then tested on it, as §M19.3's and §M35's were. That flatters their p-values, and it is why the unfiltered stratum stays in the family whatever gate 2 says.
- **The level test is unfiltered only.** A level that carries something in one stratum and not overall would read as a fail. Testing the strata as well would be a second family, and a later campaign can pre-register it.
- **Nothing here touches NinjaTrader.** Every row is `TIER1_ONLY`, and the yesterday level and its roll handling are unchecked against `PriorDayOHLC`, as §M66 notes.
- **The rest of §M66's "Not in this version"** stays out: the pullback entry, all three levels at once, Group 1's other levels, a reward-to-risk filter and a maximum risk.

[#355]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/355
[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
[#513]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/513
