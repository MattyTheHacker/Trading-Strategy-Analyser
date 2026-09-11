---
id: M26.6
title: "M26.6 — the recovery entry: the reaction §M26.5 deferred, and the one the later window punishes"
archetypes: [ElasticBand]
issues: [278]
gates: [1, 2, 3]
outcome: negative
verdict: >-
  A well-powered negative rather than an underpowered one: the recovery entry wins the selection window, gives all of it back held out, and pays for the reaction out of both ends of the bracket at once.
---

# M26.6 — the recovery entry: the reaction §M26.5 deferred, and the one the later window punishes ([#278])

**What has changed since §M26.5, stated first**, because [#221] is a parked configuration space and § "Parked is not abandoned" requires it: **a condition that did not exist** — `entry_trigger`, which changes *which bar* of an extension schedules the entry rather than adding a requirement to it. Not a new range, not new data, not a re-seeded sweep. The rules and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) §M26.6.

**Why it is a trigger and not a fifth shape.** §M26.5 built three shapes and measured all of them on a bar that is **still beyond the threshold**, which is what made a reaction expensive to require and what killed the engulfing mode at 138 signals in 1.66M bars. The reaction `Trading-Docs` actually describes happens *after* the extension — "price exceeds the level, fails to hold, and returns inside" — so the trigger is the run of bars outside ending at *i−1* and bar *i* closing back **inside** the band. That is a different entry, and §M26.5 deferred it here rather than sweeping it as a fourth mode.

**Three things had to move with it, and two of them would have failed silently.** `min_bars_outside` counts the run to the bar *before* the signal rather than to the signal bar. `STOP_EXCURSION` and `exit_on_invalidation` both read the adverse extreme of the run being faded, and `run_extreme` is `nan` inside the band — a `nan` stop makes the risk check false and declines the entry, so every excursion-stop trade would have vanished without an error, and a `nan` comparison is false, so the invalidation exit would simply never have fired. `max_entry_std` gates the bar the extension was measured on, which under this trigger is not the signal bar; gating the signal bar would have left the ceiling inert at every value. All three are one-bar reads of what the previous bar carried, which is also how the NinjaScript expresses them.

## The depth is an axis with a floor, and the floor is the engulfing mode's

`recovery_fraction` is how far back inside counts, as a share of `entry_std` — `1.0` is the band edge itself and less is a depth. A share rather than an absolute level because `entry_std` is swept over three values, and an absolute 1.5σ is a different fraction of the distance travelled at each of them. Signals on the MNQ continuous series over the VWAP band at `entry_std` 2.0, against the unfiltered rule's own count:

| depth |   1 min |  2 min |  5 min | 10 min | 15 min |
| ----- | ------: | -----: | -----: | -----: | -----: |
| none  | 148,453 | 75,202 | 29,848 | 14,132 |  8,809 |
| 1.0   |  23,657 | 16,063 |  8,960 |  5,344 |  3,874 |
| 0.9   |   5,592 |  5,462 |  4,169 |  3,004 |  2,498 |
| 0.75  |   1,054 |  1,307 |  1,322 |  1,213 |  1,195 |
| 0.5   |     140 |    197 |    268 |    296 |    355 |

**0.5 was measured and left out of the grid.** 140 signals in 1.66M bars is the engulfing mode's failure to three significant figures, and §M26.5's own rule — *count the signals a new entry gate leaves before crossing it with anything* — is what caught it before `MIN_TRADES` could report it as a smaller shortlist. NQ agrees within 10% at every cell. The three depths above it are swept.

**Read those counts against this channel and not against §M26.5's table.** On the Bollinger band the same trigger at depth 1.0 leaves 99,054 of 196,816 signals — 50% against the VWAP band's 16% — because a period-20 σ is small enough that one bar crosses it easily and a session-anchored σ is not. That is §M26.9's warning arriving from the other direction.

**The matched null can be drawn on all of it.** Draw freedom is 67.6 spare bars per signal at depth 1.0 against the unfiltered rule's 9.96 and `MIN_DRAW_FREEDOM`'s 1.0, so gate 3 runs here rather than being refused as it is for a level-based trigger.

## The campaign, and the two controls that run beside it

**3,600 rows**: five arms — the two triggers, with the extended one carrying both `shape=any` and the `shape=reversal` §M26.5 carried forward, and the recovery one carrying its three depths — each crossing `entry_std` × `min_bars_outside` × `stop_mode` × `max_hold_bars` at 36 combinations, on both roots, resolutions 1/2/5/10/15, split 60/40 into a selection and a held-out window, at the root's own commission and one tick of slippage. **The VWAP source and the 0.0σ ladder alone**, both held for the reasons §M26.9 held them. 89.7% of rows clear 30 trades. `--variants elastic-recovery --strata elastic-recovery --split`.

**Two controls rather than one, and the second is the comparison that matters.** §M26.5 asked whether requiring a reaction beats requiring nothing; this asks whether *waiting* for the reaction beats reading it off a bar still outside. `shape=any` bounds the first question and `shape=reversal` answers the second, and both run in the same pass so every comparison below is paired.

**`min_bars_outside` is a live axis here for the first time.** §M26.5 measured it as an exact duplicate under `reclaim` on 100% of cells and under `reversal` on 82.7%, because those shapes imply the run. The recovery trigger reads the run at the bar before the signal, so it does not — its η² below is an order of magnitude above what §M26.5 could measure.

## Paired, cell by cell: it wins the selection window and gives all of it back

Median change in profit factor at the same root, resolution and axis values, both arms clearing 30 trades:

| window    | control  | root | recovery@1.0 | recovery@0.9 | recovery@0.75 |
| --------- | -------- | ---- | ------------ | ------------ | ------------- |
| selection | any      | MNQ  | +0.040       | +0.120       | +0.245        |
| selection | any      | NQ   | +0.059       | +0.131       | +0.156        |
| selection | reversal | MNQ  | +0.018       | +0.077       | +0.219        |
| selection | reversal | NQ   | +0.071       | +0.163       | +0.211        |
| holdout   | any      | MNQ  | −0.001       | −0.012       | −0.025        |
| holdout   | any      | NQ   | +0.007       | +0.007       | −0.016        |
| holdout   | reversal | MNQ  | **−0.143**   | **−0.142**   | **−0.215**    |
| holdout   | reversal | NQ   | **−0.085**   | **−0.094**   | **−0.117**    |

Share of paired cells the trigger wins, and the exact binomial against a fair coin:

| window    | control  | recovery@1.0        | recovery@0.9        | recovery@0.75       |
| --------- | -------- | ------------------- | ------------------- | ------------------- |
| selection | any      | 74–83%, *p* < 0.001 | 85–91%, *p* < 0.001 | 77–88%, *p* < 0.001 |
| selection | reversal | 58–82%, *p* ≤ 0.045 | 69–90%, *p* < 0.001 | 80–86%, *p* < 0.001 |
| holdout   | any      | 49–53%, *p* ≥ 0.40  | 46–52%, *p* ≥ 0.40  | 46–47%, *p* ≥ 0.36  |
| holdout   | reversal | 16–24%, *p* < 0.001 | 21–31%, *p* < 0.001 | 25–35%, *p* ≤ 0.002 |

**Deeper is better on the selection window and worse on the held-out one, monotonically, at every one of the eight rows.** That is one shape rather than eight numbers, which is what makes it worth more than any of the levels in it: the axis is ordered, and the order reverses with the window.

**This is the same instrument §M26.5 used, on the same two windows, pointing the other way.** There the shapes lost the selection window and won the holdout, and §M26.5 read that as *"a property of the period rather than of the rule, until something separates them"*. **This separates them.** If the later window simply rewarded reaction requirements, the recovery trigger — a stricter reaction requirement on the same channel and the same bracket — would be rewarded too, and it is the one thing in this archetype the later window punishes. What the holdout rewards is the reversal shape specifically, not waiting for a reaction; §M26.5's window caveat stands on its own row and no longer explains this one away.

## Held out, where no depth clears the drawdown check

Top twenty ranked on the selection window and read on the held-out one, per arm:

| arm                | root | sel top-20 PF | hold top-20 PF | hold all-cell median | profitable | passes | returns its drawdown |
| ------------------ | ---- | ------------- | -------------- | -------------------- | ---------- | ------ | -------------------- |
| extended, any      | MNQ  | 1.129         | 1.315          | 1.021                | 19/20      | yes    | **yes**              |
| extended, any      | NQ   | 1.071         | 1.134          | 1.041                | 20/20      | yes    | no                   |
| extended, reversal | MNQ  | 1.378         | 1.513          | 1.186                | 18/20      | yes    | **yes**              |
| extended, reversal | NQ   | 1.075         | 1.739          | 1.104                | 18/20      | yes    | **yes**              |
| recovery@1.0       | MNQ  | 1.254         | 1.098          | 1.026                | 13/20      | yes    | no                   |
| recovery@1.0       | NQ   | 1.227         | 1.065          | 1.050                | 13/20      | yes    | no                   |
| recovery@0.9       | MNQ  | 1.403         | 1.196          | 1.011                | 16/20      | yes    | no                   |
| recovery@0.9       | NQ   | 1.335         | 1.054          | 1.036                | 12/20      | yes    | no                   |
| recovery@0.75      | MNQ  | 1.650         | 1.196          | 0.998                | 16/20      | yes    | no                   |
| recovery@0.75      | NQ   | 1.343         | 0.977          | 1.004                | 9/20       | **no** | no                   |

**Every recovery arm ranks above the reversal control on the selection window and below it on the holdout**, and the deepest fails the held-out gate outright on NQ. The reversal control reproducing §M26.5's own result — the only arm clearing the drawdown check, on both roots — is what says this grid is measuring the same thing that campaign did rather than a different one.

## The matched null, on the cleanest trade-count match this archetype has produced

The same twenty, ranked on the selection window and run against `randomentry.compare` on the holdout — 200 draws, entry days randomised, geometry and direction held:

| root | arm           | median PF | median null PF | median excess | *p* < 0.05 on PF | on expectancy | median trades | null trades |
| ---- | ------------- | --------- | -------------- | ------------- | ---------------- | ------------- | ------------- | ----------- |
| MNQ  | any           | 1.277     | 0.954          | +0.315        | 7/20             | 13/20         | 275           | 454         |
| MNQ  | reversal      | 1.498     | 0.948          | +0.562        | 6/20             | 10/20         | 81            | 100         |
| MNQ  | recovery@1.0  | 1.091     | 0.883          | +0.263        | **0/20**         | 5/20          | 99            | 100         |
| MNQ  | recovery@0.9  | 1.124     | 0.905          | +0.212        | **0/20**         | 2/20          | 86            | 87          |
| MNQ  | recovery@0.75 | 1.226     | 0.887          | +0.358        | **0/20**         | **0/20**      | 53            | 53          |
| NQ   | any           | 1.097     | 0.959          | +0.153        | 5/20             | 8/20          | 459           | 693         |
| NQ   | reversal      | 1.325     | 0.938          | +0.378        | 10/20            | 14/20         | 134           | 184         |
| NQ   | recovery@1.0  | 1.095     | 0.932          | +0.172        | 3/20             | 6/20          | 402           | 397         |
| NQ   | recovery@0.9  | 1.011     | 0.917          | +0.094        | **0/20**         | **0/20**      | 238           | 236         |
| NQ   | recovery@0.75 | 0.990     | 0.920          | +0.075        | **0/20**         | **0/20**      | 152           | 156         |

**The recovery arms are the best-matched null this archetype has ever run and the worst result it has returned.** §M26.4 named a mismatched trade count as what makes a null comparison unclean, and both controls have one — 275 against 454 and 459 against 693 — while every recovery row matches its null to within 4%. So the arm with nothing to explain away is the arm that clears nothing: 0 of 20 on profit factor on MNQ at all three depths, and 0 of 20 on both statistics at the two deeper ones on NQ.

**The median excess is not the reading here, and this is the row that shows why.** `recovery@0.75` on MNQ carries a larger median excess than `recovery@1.0` (+0.358 against +0.263) and clears fewer of both gates, because 53 trades against 99 is a wider null to sit inside. `CONTRIBUTING.md` § "Statistics and results" — the verdict is the sign count, and a median can never carry it.

## Which axis moves the profit factor, and the entry rule is the one that swaps rank

η² on profit factor over the ranges swept, both roots pooled, cells clearing 30 trades:

| axis               | holdout    | selection  |
| ------------------ | ---------- | ---------- |
| `entry_std`        | **0.0947** | 0.0267     |
| resolution         | 0.0504     | 0.0181     |
| the arm            | 0.0349     | **0.1704** |
| `stop_mode`        | 0.0342     | 0.0001     |
| `min_bars_outside` | 0.0131     | 0.0022     |
| `max_hold_bars`    | 0.0030     | 0.0000     |

**The entry rule is the largest axis on the selection window by a factor of six and the third largest on the held-out one**, and no other axis moves rank between the two columns. `entry_std` at 0.0947 reproduces §M26.5's 0.0941 on a grid that shares neither its arms nor its axis set, which is the closest thing this campaign has to a control on its own arithmetic. **The depth threshold is still the large lever and which bar signals is still a small one** — the calibration §M26.5 asked to be read beside a paired table, holding on a second grid.

## Why: it pays for the reaction out of both ends of the bracket at once

Medians over the signal bars themselves, before any simulation — the move left to the basis, and the run the stop has to cover, both in standard deviations:

| arm                | 1 min: to basis | to run extreme |  ratio | 15 min: to basis | to run extreme |  ratio |
| ------------------ | --------------: | -------------: | -----: | ---------------: | -------------: | -----: |
| extended, any      |           2.255 |          0.150 | 14.744 |            2.281 |          0.196 | 11.633 |
| extended, reversal |           2.224 |          0.277 |  8.299 |            2.176 |          0.430 |  5.346 |
| recovery@1.0       |           1.906 |          0.363 |  5.102 |            1.697 |          0.609 |  2.379 |
| recovery@0.9       |           1.689 |          0.642 |  2.585 |            1.520 |          0.817 |  1.764 |
| recovery@0.75      |           1.357 |          1.080 |  1.223 |            1.222 |          1.161 |  1.014 |

**Both columns move the wrong way at once, monotonically, and the depth axis is the dial.** Waiting for the close to come back inside spends the part of the reversion the trade exists to capture — the target *is* the basis under this ladder — while the excursion the stop must sit beyond is still the whole run, which by then is further away. At depth 0.75 the two are equal: the archetype is risking one standard deviation to make one. The reversal shape asks for the same reaction on a bar that is still outside and costs 1.4% of the reward for it, which is why the same idea works as a shape and not as a trigger.

**This is the mechanism §M26.5 predicted from the other side.** It recorded that the extension threshold is defined on the close, so a bar that has turned has usually stopped being 2σ out — and read that as the *cost in signal count* of requiring a turn. It is the same fact, and its cost in geometry is the larger one: what a returning close gives up is not signals, it is the trade.

## What this rules out, and what it hands to [#279]

- **The recovery entry does not work, and this is a well-powered negative rather than an underpowered one.** Every previous verdict in this archetype has been bounded by sample size — §M26.5's shortlist had a median of 34 to 56 trades. Held out, this pass has a median of 140 to 843 trades per cell and 76–97% of cells clearing `MIN_TRADES` in every arm, and the answer is still no on all three depths, both roots, both windows' paired tests, the drawdown check and the null.
- **`reversal` is still the shape to carry forward and #278 does not displace it.** Paired on the holdout it beats every depth on both roots at *p* ≤ 0.002, and it is the only arm in the pass that returns its own drawdown.
- **§M26.5's window caveat is now separated from its rule**, which is the one thing this pass adds that the tracker did not ask for. A stricter reaction requirement on the same bars, channel and bracket is punished by the same window that rewards the reversal shape, so "the later regime rewards reaction requirements" is false as stated and the shape result has to stand or fall on its own.
- **The depth axis should not be swept again as it stands, and neither should the trigger.** Its whole range is dominated on the holdout and its ordering is a straight trade of reward for risk, so a wider range moves along the same line rather than off it. What would be a new question is a recovery entry whose *target* is re-denominated — the far band rather than the basis — since the objection measured above is that the basis is too close by the time the bar closes back inside. That is an exit-side change to answer an entry-side finding, which is what [#279] already owes.
- **Everything §M26.5 owed is still owed.** The VWAP basis is unpinned, and every number here is off the back-adjusted continuous series rather than per contract — §M26's first trap, that both σ and the basis step at every roll seam.

[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
[#278]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/278
[#279]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/279
