---
id: M66
title: "M66 — FailedBreak: the sweep and recovery of an obvious level"
archetypes: [FailedBreak]
issues: [355]
gates: []
outcome: spec
verdict: >-
  A close back inside yesterday's, the overnight or the first-hour range after trading through it, entered at market on the next open, with the stop beyond the sweep's extreme and the targets on the levels; its signal is event-like enough for the bar draw, but a drawn bar has no sweep to stop behind, so the null carries each signal's geometry.
---

# M66 — FailedBreak: the sweep and recovery of an obvious level ([#355])

**Nothing here is a result.** This is the design, written before the Python and then built to; the rules and the NinjaScript each would be written as are in [`nt8-fidelity.md`](../nt8-fidelity.md) §M66. The one measurement is a count of signals and bracket distances on the selection window: no trade was simulated and no return was read.

The setup is `Trading-Docs/discretionary_trading_concepts.md` §7.1, and §7.2 is the same rule on one level. The archetype is called `FailedBreak` because "sweep" already means a parameter sweep in `nqbt/sweep.py`, every tool and the results tables.

## The rule

Long, and the short side is the same rule with one sign multiplier:

1. **The level.** A low from a fixed set: yesterday's, the overnight or the first hour's.
2. **It has to start inside.** A level cannot be swept until a bar has closed above it since it became readable, so a session that opens below yesterday's low has not swept it.
3. **The sweep.** A bar's low trades below the level. A low exactly on it is not through it.
4. **The trigger.** A bar closes above the level, on the sweep bar or within `max_sweep_minutes` after it. A close exactly on it is not back.
5. **The entry.** Market, on the next bar's open.
6. **The stop.** The lowest low from the start of the sweep to the trigger bar, `stop_offset_ticks` below that, then moved off a round number.
7. **The targets.** Prices from the levels, fixed at the trigger bar.
8. **The invalidation.** A close back below the level exits at market on the next open.

## The levels are fixed, not swept

§7.1 says what kills this setup is a minor level, so which levels count is a rule rather than an axis. All three come from bars and need no judgement:

| level        | range                     | `RangeKey`   | readable from                 |
| ------------ | ------------------------- | ------------ | ----------------------------- |
| `yesterday`  | the previous cash session | `(930, 390)` | this session's first bar      |
| `overnight`  | 18:00 to 09:30 ET         | `(0, 930)`   | the bar completing the window |
| `first-hour` | 09:30 to 10:30 ET         | `(930, 60)`  | the bar completing the window |

`sessionrange.range_grid` builds all three today. Yesterday's is the only new read, and it needs two rules:

- **It is not read across a roll.** The campaign runs on raw prices, so the first session of a new contract would otherwise read a low in the old contract's prices. That session has no `yesterday` level, which removes 14 sessions of about 919 from the selection window.
- **A previous session with a short cash window leaves no level**, which is what `range_grid` already does for a window short of bars. 42 to 49 of about 919 sessions have none, depending on the root and bar size, roll sessions aside. The first session after a half day is one of them.

The level is a variant dimension, one per configuration, so a result can say which level it came from. Group 1's other levels — opens, closes, gaps, last week's range and round numbers — are left out, as [#355] leaves them out, and so is trading all three at once.

## Why market on the next open and nothing else

§7.1 also allows "the first pullback that holds the reclaimed level". That is a limit order, and it is left out of this version because of what §M28.6 and §M28.7 found: **every profitable cell in 245,760 of the rejection's was one the fill assumption decided**, because a limit entry and its bracket share a bar under a rule that was never fitted to that case. A market order fills at the open, so the rule's starting point is the price the trade really started from.

The pullback entry is a natural second campaign. It should wait for the same-bar limit-entry trade list that §M28.7 asks for.

## Why this is not the parked fade again

§ "Parked is not abandoned" asks what has changed. Against OpeningRange's fade, §M28.2 and §M28.5, three things have:

- **The trigger.** A fade rests a stop at the level and fills during the bar that reclaims it, which is the wick §7.1 says not to take. This waits for the close.
- **The bar that decides the trade.** §M28.5 found the fade's stop sits inside the bar it fills on. Here the stop is already beyond everything the sweep traded, and the fill is on a later bar.
- **The stop's reference and one level.** The stop reads the sweep's extreme rather than a fraction of the range, and yesterday's range was never in the fade's grid.

It is an archetype rather than a fifth OpeningRange mode for §M34's reasons: the name is what results are keyed on, and OpeningRange's loop and signal assume an order resting on a level.

## The stop

**A cushion is required, so `stop_offset_ticks` starts above zero.** The axis is `[2, 4, 8, 16]`.

**Round-number avoidance reuses `bracket.avoid_round_number`**, as EmaCrossover's `round=on` does, at 50 points. The parameter defaults to off because it refuses bars not declared `PriceBasis.RAW`, and the campaign turns it on. It is a fixed rule in the campaign rather than an axis, since it only moves a stop landing exactly on a multiple, about one stop in 200 on a 50-point grid.

**There is no dollar floor and no maximum risk**, as with any structural stop. R is the distance from the fill to the stop, so a campaign has to read the distribution of `risk_points` and not just its mean. A stop already at or through the next open is refused by the usual minimum-risk check.

## The targets

Three schemes, each a variant, because a tuple cannot be an axis — §M28.11:

| scheme          | legs                                                        | from                       |
| --------------- | ----------------------------------------------------------- | -------------------------- |
| `opposite+next` | the opposite side of the range, then the next level past it | §7.1, and [#355]           |
| `mid+opposite`  | the range's midpoint, then the opposite side                | §7.2, without its VWAP leg |
| `R`             | the usual R ladder                                          | the control                |

**"The next stop cluster" is the nearest opposing level from the other two ranges, among those readable at the trigger bar, beyond the first target.** With none, that leg has no target and runs to the stop or the close.

A signal whose close is already at or past the first level target is refused. That is at most 2% of signals on the bars measured.

## The invalidation

**"Re-breaks the swept level" has to mean a close.** The stop sits beyond the sweep's extreme, so a stop on a mere trade through the level would sit inside it and the extreme stop could never be reached. A close also matches the trigger's own "the close, not the wick".

It is decided at the bar close and fills at the next open as `EXIT_SIGNAL`, the shape of ElasticBand's `exit_on_invalidation`. It also applies on the entry bar. **It is a paired on/off variant, not a fixed rule**, because §M48 found a conditional market exit costs wherever it can close a winner. [#355] names this rule as what §M29 said was missing, and that is the claim the pair tests.

## The axes

| name                      | values          | type    | why                                                     |
| ------------------------- | --------------- | ------- | ------------------------------------------------------- |
| level                     | the three above | variant | the thing being measured — rank within it, §M28.8       |
| target scheme             | the three above | variant | a tuple                                                 |
| invalidation              | on, off         | variant | a paired read                                           |
| `direction`               | long, short     | axis    | one side per configuration, as OpeningRange             |
| `max_sweep_minutes`       | 0, 30, 60, 120  | axis    | 0 is the same bar; §7.2 gives thirty minutes as a claim |
| `stop_offset_ticks`       | 2, 4, 8, 16     | axis    | the cushion                                             |
| `max_signals_per_session` | 1, 2            | axis    | the first signal against a second chance                |

That is 18 variants of 64 combinations, or 1,152 per root, bar size, window and stratum, before the usual context strata. [§M66.1](m66-1-failed-break-swept.md) records the run time. §7.1's "rotational or transitional conditions" is the existing regime strata rather than a rule, and how far the sweep went has no axis.

**The minutes are minutes rather than bars** so that one cut means the same at every bar size. All of `campaign_sweep.RESOLUTIONS` can express all three ranges.

## What the signal looks like on the bars

Selection window only, 2020-10-25 to 2024-05-10. MNQ, long side; NQ is close to this except where noted below, and the short side has stops a little tighter. `every` counts every recovery with no age cap and `first` the first per session. Stop and target distances are in points from the trigger bar's close, for `every`.

| bars | level        | every | first | freedom, every | freedom, first | same bar | median stop | median first target |
| ---- | ------------ | ----- | ----- | -------------- | -------------- | -------- | ----------- | ------------------- |
| 1    | `yesterday`  | 6,100 | 409   | 191.6          | 725.7          | 0.47     | 8.2         | 210.4               |
| 1    | `overnight`  | 5,024 | 503   | 77.7           | 344.1          | 0.50     | 10.8        | 131.8               |
| 1    | `first-hour` | 4,586 | 495   | 73.4           | 363.5          | 0.49     | 9.5         | 116.8               |
| 5    | `yesterday`  | 2,989 | 398   | 81.5           | 422.9          | 0.52     | 17.2        | 203.2               |
| 5    | `overnight`  | 2,379 | 487   | 32.5           | 139.3          | 0.55     | 22.0        | 125.0               |
| 5    | `first-hour` | 2,200 | 474   | 30.2           | 124.7          | 0.55     | 19.5        | 109.6               |
| 15   | `yesterday`  | 1,762 | 383   | 45.5           | 198.6          | 0.55     | 27.5        | 197.1               |
| 15   | `overnight`  | 1,394 | 460   | 18.0           | 54.8           | 0.58     | 35.0        | 113.9               |
| 15   | `first-hour` | 1,318 | 445   | 16.4           | 50.5           | 0.60     | 31.0        | 101.8               |
| 30   | `yesterday`  | 1,264 | 368   | 31.1           | 109.2          | 0.58     | 37.2        | 188.2               |
| 30   | `overnight`  | 1,023 | 431   | 12.0           | 30.0           | 0.63     | 47.8        | 107.2               |
| 30   | `first-hour` | 928   | 420   | 11.4           | 26.5           | 0.62     | 41.8        | 94.2                |

Four things to take from it:

- **[#355]'s reason for choosing this setup holds.** Across both roots, all six bar sizes, all levels and both sides, draw freedom is never below 11.4 spare bars per signal, against `MIN_DRAW_FREEDOM` of 1. It is only thinner once a context filter is added, so it still has to be read per stratum.
- **The first signal of a session is a different signal from the rest.** `every` runs 2 to 15 times `first`, widest at one minute, where price chops around the level. That is why `max_signals_per_session` is an axis.
- **The first target is far away.** Its median is 89 to 210 points against a median stop of 6 to 48, and it clears 2:1 on 54% to 98% of signals. So the bracket looks good on paper and many trades may never reach it. **Expect a high `session_close_share` under `opposite+next`, and read it first**, which is why the two nearer schemes are there.
- **One-minute overnight ranges are patchy on NQ.** A window missing a single minute has no range, which removes 120 of 916 NQ sessions at one minute against 44 of 919 on MNQ. At two minutes and above the two roots agree to within a few sessions.

## Gate 3 needs more than the bar draw

**[#355] says the event-like signal means gate 3 can be answered without `matched_random_ranges`. That is right about the signal, and it is not enough.** `matched_random_signal` moves a signal to another bar, and a bar that is not a sweep has no extreme to stop behind, no swept level to invalidate on and no range side chosen by a sweep. Left alone, nearly every drawn bar would be declined. §M26 has already measured a milder form of this: ElasticBand's excursion stop traded about 10,000 times against a null median near 1,900.

**So a drawn bar carries a real signal's geometry.** The loop reads per-bar prices for the stop, the targets and the invalidation level, all fixed at the signal bar. Under a drawn signal, `failedbreak_legs` pairs each drawn bar with a real signal at the same minute of session, in time order within that minute, and places those prices at the same distances from the drawn bar's close. Pairing in time order keeps a quiet year's distances on a quiet year's bars. `randomentry` does not change, and the null holds the count, the time of day, the side and the bracket's distances, and moves only where the trade happens.

**The cap counts signals rather than fills, and the null is why.** Capped on fills, a rule firing several times in each of 487 sessions trades 487 times while the same count of drawn bars lands in nearly every session and trades far more often. `max_signals_per_session` is applied to the signal itself, after the context filters, so a signal taken while a position is open still uses one up. A port counts the same way, at the bar close.

**That null tests the entry, and the setup's claim is about the level.** §7.1 says obvious levels are where the stops are. So the campaign also re-runs the whole rule against a level placed at random, with `randomentry`'s existing `kinds` draw from §M60, and against another session's level with its `levels` draw from §M28.2. Both work through `FailedBreakParams.range_key`. Under `yesterday` the level is placed around the close of the session it is read from. A level draw moves one range and leaves the other two where they were, so a second target can still sit on a real level.

## The expressibility checklist

| question                                             | answer for FailedBreak                                                                                                   |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| How long must an entry order rest?                   | Not at all: a market order at the next bar's open                                                                        |
| Does it need a true OCO pair?                        | No: one side per configuration, and market orders                                                                        |
| Does it need to reverse directly from long to short? | No: flat between trades                                                                                                  |
| Does it hold through the session close?              | No: flattened like every other archetype, so a far target may simply not be reached                                      |
| Does it need more than 4 entries per direction?      | No: one position at a time                                                                                               |
| Does it need an indicator NT8 computes differently?  | No indicator at all. The port tracks the cash window's high and low itself, then checks roll handling on a merged series |

The levels, the state per level and the exit are bar-close reads in `OnBarUpdate`, the stop is `SetStopLoss` and the targets are `SetProfitTarget`. Whether NT8's `PriorDayOHLC` would give the same yesterday is not measured, so the port should not assume it does.

## The build

- **A new loop in `nqbt/sim/failedbreak.py`, on `bracket.py`.** `simulate_crossover` is close, with a market entry and a level stop, but its targets are R multiples only and it is EmaCrossover's negative control, so a per-signal target price does not belong in it.
- **The signal is worked out before the loop**, one run per level, side and age cap.
- **`Tier2Status` is `TIER1_ONLY`**, every rule goes in `nt8-fidelity.md`, and its defaults have to trade on MNQ 03-24 for the trade-log gate.
- **The sweep is `campaign_sweep.py --strategies FailedBreak`**, [pre-registered](m66-failed-break-preregistration.md) and [run](m66-1-failed-break-swept.md).

## Not in this version

Each of these is a later campaign, and none is ruled out: the pullback entry, all three levels at once, Group 1's other levels, §8's reward-to-risk filter and a maximum risk. The order-flow confirmation and the book-flip read need depth data, which is [#120] and [#121].

[#120]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/120
[#121]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/121
[#355]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/355
