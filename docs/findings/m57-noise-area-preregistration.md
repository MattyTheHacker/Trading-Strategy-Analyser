---
title: "M57 — pre-registration: the noise area, followed, against its pieces and its fade"
archetypes: [ElasticBand]
issues: [439]
gates: [1, 2, 3]
outcome: spec
verdict: >-
  Written and committed before the sweep started: ElasticBand on the noise area in four arms over one grid — the paper's rule, decided on the half hour and trailed on the band's edge or the VWAP; the same decided on every bar; the same without the trail; and the half-hour signals faded — in all 23 strata at 1, 2, 5, 10 and 15 minutes; an arm beats the rule at a resolution only where, on both roots, the paired median profit-factor delta is positive with a sign test at p < 0.05 in both windows — §M37's bar, over a family of 15 — and the rule runs through gates 1 and 2 and then gate 3, read family-wise as §M54 reads it.
---

# M57 — pre-registration: the noise area, followed, against its pieces and its fade ([#439])

[§M28](m28-opening-range-spec.md) listed the noise-area break, Zarattini, Aziz and Barbon's intraday momentum, among the opening-range family's named versions and deferred it to ElasticBand's thread: "a band around the open or the VWAP, scaled by recent daily movement". [§M28.2](m28-2-deferral-list.md) kept it deferred. Its nearly-free form, the VWAP channel traded with the break, is [§M26.7](m26-7-inverted-signal-preregistration.md)'s inverted arm. **This is the rule itself**: a band around the gap-adjusted cash open, as wide as the move from the open usually is by that time of day, decided on the half hour, trailed on the band's edge or the VWAP from the cash open, and flat at the cash close or the session close — `docs/nt8-fidelity.md`, "The noise area". The rule was read from public replications of the paper rather than the paper itself.

**What has changed since §M27**, as [`roadmap.md`](../roadmap.md) § "Parked is not abandoned" asks: a new band source and the three rules that come with it. ElasticBand's other axes, its costs and its windows are the campaign's own.

**This file was written and committed before the sweep started.** The arms, the grid, the strata, the bar below and the predictions were all chosen before any of it ran.

## What will be run

|                 |                                                                                                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Arms**        | 4, in one pass (below)                                                                                                                                                             |
| **Grid**        | `entry_std` at 1.0, 1.5 and 2.0 — the paper's multiple is 1.0 — × `exit_at_cash_close` off and on × `stop_mode` at the account stop and the ATR stop, 12 combinations in every arm |
| **Band**        | the noise area at the paper's 14 prior sessions, the extended trigger, one bar outside, no signal-bar shape                                                                        |
| **Strata**      | all 23, one context dimension at a time                                                                                                                                            |
| **Resolutions** | 1, 2, 5, 10 and 15 minutes, as every ElasticBand set ran                                                                                                                           |
| **Roots**       | MNQ and NQ, spliced continuous                                                                                                                                                     |
| **Costs**       | $1.50 per contract round trip on MNQ, $4.50 on NQ, plus one tick of slippage                                                                                                       |
| **Windows**     | selection on the first 60% of bars, holdout on the last 40%                                                                                                                        |
| **Size**        | 22,080 combinations, both windows counted                                                                                                                                          |

```bash
uv run tools/campaign_sweep.py --strategies ElasticBand --variants elastic-noise --split \
    --strata elastic-noise --resolutions 1 2 5 10 15
```

### The arms

| arm                             | side     | decided on    | the trail | targets                          |
| ------------------------------- | -------- | ------------- | --------- | -------------------------------- |
| `noise=rule target=runner`      | followed | the half hour | on        | one runner                       |
| `noise=every-bar target=runner` | followed | every bar     | on        | one runner                       |
| `noise=no-trail target=runner`  | followed | the half hour | off       | one runner                       |
| `noise=fade target=0.0s`        | faded    | the half hour | off       | the nearer anchor, then a runner |

**The momentum arms hold one runner**, as the paper sets no target: a trade leaves by the trail, the stop, the cash close or the session close. **The fade cannot take the trail**, which would close it at the first decided close, so it leaves at the nearer anchor or by the same stops: the pair compares the side and the exits that side needs, as §M26.7's does. Every name carries a `noise=` token no stored ElasticBand row has, and a `target=` token the shortlist rebuild reads the ladder back from. **The 16:00 exit is recorded as a session close**, so `session_close_share` counts it.

### Measured before the run: what the noise area leaves

The sweep rules ask for the signals a new entry leaves before it is crossed with anything. On MNQ's whole spliced series, 1,531 sessions, unfiltered, at the multiples swept; the rule's trades at the arm's base stop, the ATR stop, flat at the session close:

| bars | rule signals at 1.0 / 1.5 / 2.0 | rule trades at 1.0 / 1.5 / 2.0 | every-bar signals at 1.0 |
| ---- | ------------------------------- | ------------------------------ | ------------------------ |
| 1m   | 5,229 / 3,008 / 1,616           | 1,770 / 1,126 / 676            | 155,401                  |
| 2m   | 5,229 / 3,008 / 1,616           | 1,521 / 972 / 596              | 77,715                   |
| 5m   | 5,229 / 3,008 / 1,616           | 1,384 / 902 / 544              | 31,137                   |
| 10m  | 5,230 / 3,010 / 1,616           | 1,338 / 881 / 535              | 15,600                   |
| 15m  | 5,231 / 3,009 / 1,615           | 1,332 / 880 / 533              | 10,412                   |

**The half-hour signals are the same at every bar size**, as they should be: a close on the half hour is the same price whatever bars led to it. **The trades are not**, because the ATR stop is sized by the bar's own ATR, so a 1-minute stop is tighter and stops out more often. About one trade a session at the paper's multiple, and every cell of the rule is well above the 30-trade floor unfiltered. The no-trail and fade arms signal on the rule's bars exactly; the every-bar arm on 2 to 30 times as many.

## What will be read

1. **The effect is read paired, never off a shortlist.** `tools/campaign_paired.py`'s pairing on profit factor, each of `noise=every-bar target=runner`, `noise=no-trail target=runner` and `noise=fade target=0.0s` against `noise=rule target=runner` over the same grid, one row per root × resolution, **in the unfiltered stratum and in each window separately**. Beside it: trades, win rate, average bars held, `session_close_share` and mean R. The pair count is printed and nothing is concluded from zero.
2. **The verdict is §M37's bar.** An arm beats the rule at a resolution only where, **on both roots**, the median delta is positive **and** the sign test reaches p < 0.05 **in both windows**. Three pairs × five resolutions is a family of 15. The same pairing over the other 22 strata is reported beside it as description, not a test, because the strata share bars.
3. **Gates 1 and 2 are §M27's, per arm.** Gate 1 is the share of unfiltered configurations with a profit factor above 1 at 30 trades or more. Gate 2 is `tools/campaign_holdout.py`'s `passes` per root and stratum, run once per arm with `--variant`.
4. **Gate 3 runs on the rule alone, on every stratum where it clears gate 2 on both roots**, under §M54's protocol: both roots, 5-minute bars, the top ten configurations ranked on the selection window by profit factor, tested on the holdout, 400 draws, the over-bars draw. **The family is every one of those tests**, saved with `--out` and read with `--family-of`, as §M54 reads its families. If no stratum qualifies, gate 3 is not run, and that is the result.
5. **Nothing is added, dropped or re-cut after the first run.** A pass that stops part-way is resumed, not redesigned.

## Predicted before the run

- **The rule does not clear gate 3 family-wise on both roots in any stratum.** The outside evidence §M28 recorded is discouraging on this underlying: the replication of the same authors' QQQ opening-range study crossed zero at about 2¢ a share of slippage, and a falsification study of 5-minute MNQ rules found nothing passing.
- **Unfiltered, the rule fails gate 2 on at least one root.**
- **No arm clears §M37's bar against the rule at any resolution**: deciding on every bar, dropping the trail and fading the same bars each cost or do nothing.
- **The rule's unfiltered median profit factor under the account stop moves by less than 0.02 between 1 and 15 minutes on each root**, since its signals and its trail's decisions do not depend on the bar size.

## What this run is not

- **Not the paper's sizing.** It targets volatility; every arm here trades a fixed size.
- **Not its reversals.** The paper turns from one side to the other on a check; ElasticBand goes flat first.
- **Not the VWAP channel.** That is §M26.7, and no arm here is compared with it.
- **Not a port.** ElasticBand has no NinjaScript, and every row is `TIER1_ONLY`.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
