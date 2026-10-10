---
title: "M26.7 — pre-registration: ElasticBand's signal inverted"
archetypes: [ElasticBand]
issues: [279, 439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: the inverted signal against the fade on the same signal bars, in five arms — both sides on R targets, then each on its own stretch ladder — over §M26.5's channel, in all 23 strata at 1, 2, 5, 10 and 15 minutes; the inversion beats the fade at a resolution only where, on both roots, the paired median profit-factor delta is positive with a sign test at p < 0.05 in both windows — §M37's bar, over a family of 15 — and gate 3 is read over the strata where an inverted arm clears gate 2 on both roots, at most six, with its fade twin measured over the same family.
---

# M26.7 — pre-registration: ElasticBand's signal inverted ([#279])

[#279] asks whether the fade "may be more valuable inverted". [§M26](m26-elastic-band.md) measured the fade's win rate as worse than a matched random entry on 4 of 4 contracts while its profit factor was better: the entry selects for payoff size rather than frequency, so inverting it swaps the payoff distribution as well as the side. [#451] built the inversion: the same signal bars, traded on the other side, with the exit rules that read the fade's direction redefined — `docs/nt8-fidelity.md` §M26.7.

**What this adds over SqueezeBreakout and OpeningRange**, which #279 asks of it. Both already trade with a break, and neither can say what the same bars are worth faded. Here every inverted row has a fade twin on the same signal bars, grid and costs, so a difference belongs to the side and the target that side needs, not to a different entry rule. Neither archetype is compared against here.

**This file was written and committed before the sweep started.** The arms, the strata, the bar sizes, the bar below and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                                                                                                                            |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 5, the fade and the inverted signal in one pass (below)                                                                                                                                                                    |
| **Grid**        | §M26.5's VWAP channel, the extended trigger and no signal-bar shape; `entry_std` × `min_bars_outside` × `stop_mode` × `max_hold_bars`, 36 combinations in every arm — `tools/README.md` § "Variant sets", `elastic-invert` |
| **Strata**      | all 23, one context dimension at a time                                                                                                                                                                                    |
| **Resolutions** | 1, 2, 5, 10 and 15 minutes, as every ElasticBand set ran                                                                                                                                                                   |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                                                             |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                                                               |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                                                                |
| **Size**        | 82,800 combinations, both windows counted                                                                                                                                                                                  |

```bash
uv run tools/campaign_sweep.py --strategies ElasticBand --variants elastic-invert --split \
    --strata elastic-invert --resolutions 1 2 5 10 15
```

### The arms

| arm                      | side     | target                                                                       |
| ------------------------ | -------- | ---------------------------------------------------------------------------- |
| `invert=off target=R`    | fade     | 1, 1.5 and 2 R and a runner, each capped at the basis                        |
| `invert=on target=R`     | inverted | the same R ladder, uncapped                                                  |
| `invert=off target=0.0s` | fade     | the midline and a runner, the ladder every ElasticBand set since §M26.5 read |
| `invert=on target=+1.0s` | inverted | 1σ past the signal bar's close and a runner                                  |
| `invert=on target=+2.0s` | inverted | 2σ past the signal bar's close and a runner                                  |

**The R pair is the like-for-like one**: the same ladder in R on both sides, differing only by the fade's cap at the basis, which would put every inverted target behind the fill. A stretch ladder cannot be shared, because an inverted level is measured past the signal bar's close rather than from the basis and must be above 0, so each side runs its own.

**The three stops swept mean the same thing on both sides**: the ATR, swing and catastrophe stops are a distance or a bar extreme signed by the trade's direction. The excursion and band stops are redefined under the inversion and are not run here.

**No reproduction step.** The fade arms are the control, run in the same pass, so nothing is read against a stored row: [#451] and [#453] changed ElasticBand's fills after every stored ElasticBand row was swept.

## What will be read

1. **The effect is read paired, never off a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, one row per root × resolution, **in the unfiltered stratum and in each window separately**, for three pairs: the inverted signal on R against the fade on R, and each inverted ladder against the fade's midline. The pair count is printed and nothing is concluded from zero. Beside it: win rate, trades, average bars held, `session_close_share` and mean R.
2. **The verdict is §M37's bar.** The inversion beats the fade at a resolution only where, **on both roots**, the pair's median delta is positive **and** the sign test reaches p < 0.05 **in both windows**. Three pairs × five resolutions is a family of 15. The same pairing over the other 22 strata is reported beside it as description, not a test, because the strata share bars.
3. **Gates 1 and 2 are §M27's, per arm.** Gate 1 is the share of unfiltered configurations with a profit factor above 1 at 30 trades or more. Gate 2 is `tools/campaign_holdout.py`'s `passes` per root and stratum, run once per arm with `--variant`.
4. **Gate 3's family is chosen per inverted arm, as §M37's was**: the strata where that arm clears gate 2 on both roots, at most six; if more qualify, the six with the highest mean of the two roots' held-out shortlist profit factor. **Its fade twin is measured over the same family** — the fade on R for the inverted R arm, the fade's midline for either inverted ladder — on both roots, the best five configurations by selection-window profit factor, measured on the holdout, 400 draws, the over-bars draw. If no stratum qualifies, gate 3 is not run for that arm, and that is the result. The random entry substitutes the signal and never the side, so a drawn bar is traded on the inverted side too (§M26.7).
5. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The inverted signal wins more often than the fade**: its win rate is above its R twin's in a majority of the ten unfiltered held-out root × resolution cells, because §M26 found the fade's win rate below a random entry's on all four contracts.
- **It does not clear the bar in (2) for any pair at any resolution.** §M26 found the fade's profit factor above a random entry's on all four contracts, and the inversion trades the same bars against that.
- **Fewer strata clear gate 2 on both roots under each inverted arm than under its fade twin.**
- **At one minute every arm's median configuration loses on both roots**, as every archetype's does there.

## What this run is not

- **Not a comparison with SqueezeBreakout or OpeningRange**, above.
- **Not the redefined exits or the other entries.** The excursion and band stops are not run, nor is the recovery trigger, under which the inverted excursion stop is declined, nor a signal-bar shape, which inverted reads a breakout on a bar that has already turned against it — `docs/nt8-fidelity.md` §M26.7 says what each would measure instead.
- **Not the Bollinger channel**, which §M26.4 found does not survive a holdout.
- **Not a port.** Every row is `TIER1_ONLY` until a trade list is diffed against it.

[#279]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/279
[#451]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/451
[#453]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/pull/453
