---
id: M26.4
title: "M26.4 — the VWAP band: the second source, and the first thing to survive a holdout here"
archetypes: [ElasticBand]
issues: [221]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  `band_source` clears the holdout and not the matched null, so what it buys cannot be separated from the bracket; depth is the axis that separates the two sources and 2 sigma is not deep enough.
---

# M26.4 — the VWAP band: the second source, and the first thing to survive a holdout here ([#221])

**What has changed since §M27, stated first**, because "Parked is not abandoned" requires it before a parked configuration space is re-run: **a condition that did not exist** — `bands.VwapBand`, a session-anchored channel with no period axis. Not a new range, not new data, not a re-seeded sweep. The rules it adds and the NinjaScript each becomes: [nt8-fidelity.md](../nt8-fidelity.md) §M26.4.

## The prediction §M26 made about the band width is wrong, and in the interesting direction

§M26 deferred this form partly because its width "shrinks monotonically through a session as volume accumulates", making a fixed *k* a different threshold at 09:00 than at 15:00. **Measured over the MNQ continuous series, the width grows monotonically instead** — median σ by bars since the anchor: 7.6 points over bars 30–60, 9.7 over 60–120, 14.1 over 120–240, 18.0 over 240–480, 26.8 over 480–840, 56.5 over 840–1400.

The reasoning it came from confused a dispersion with a standard error. The *standard error* of the VWAP shrinks as observations accumulate; the dispersion of prices about it grows, because a session that has wandered further from its anchor has a wider sample. **The confound §M26 worried about is therefore real and points the other way**: the band is widest late in the session, and the share of bars beyond 2σ still rises with session age — 5.5% over bars 30–60 against 9.8% over 840–1400 — so a fixed *k* is a *looser* threshold in the US cash session, not a tighter one. Session age and RTH volatility are not separable on an anchored window, so this is the observable rather than a mechanism.

**Price does mostly stay inside the band, which is the observation [#221] started from.** Over the whole MNQ continuous series, past the warm-up, 9.1% of bars close at or beyond 2σ, 2.1% beyond 2.5σ and 0.36% beyond 3σ. Fatter-tailed than a normal distribution's 4.6% at 2σ, and the chart reading it came from holds.

## Held out, and the shape of the §M27 failure reverses

Both sources over one grid — entry depth, run length, three stop modes, a time stop, resolutions 1/5/15 — on both roots, split 60/40 into a selection and a holdout window, at the root's own commission and one tick of slippage.

| root | source    | median PF, selection | median PF, holdout | profitable on holdout |
| ---- | --------- | -------------------- | ------------------ | --------------------- |
| MNQ  | Bollinger | 0.903                | 0.895              | 10.4%                 |
| MNQ  | VWAP      | 0.883                | 0.958              | 39.6%                 |
| NQ   | Bollinger | 0.945                | 0.924              | 17.4%                 |
| NQ   | VWAP      | 0.921                | 0.989              | 46.5%                 |

**Read the holdout column against itself, not against the selection column.** The holdout window is easier for both sources, so the within-source improvement is the window; the comparison that means something is Bollinger against VWAP *on the same window*, where VWAP is ahead by about 0.06 median profit factor and by three to four times the share of profitable configurations, on both roots.

**Selecting the best configuration on the selection window then reading it on the holdout is where the two part company.** Averaged over the ten best selection-window configurations with at least 100 trades:

| root | source    | selection PF | holdout PF | profitable on holdout |
| ---- | --------- | ------------ | ---------- | --------------------- |
| MNQ  | Bollinger | 1.298        | 0.760      | 1 of 10               |
| MNQ  | VWAP      | 1.114        | 1.279      | 10 of 10              |
| NQ   | Bollinger | 1.438        | 0.789      | 2 of 10               |
| NQ   | VWAP      | 1.081        | 1.092      | 9 of 10               |

The Bollinger rows are §M27's 1.834-to-0.592 collapse reproduced on a different split. The VWAP rows do not collapse. **Note which source has the higher selection-window number** — Bollinger, on both roots — which is the same lesson §M27 drew from ElasticBand owning the campaign's best number and being eliminated first.

## Depth is the axis that separates them, and 2σ is not deep enough

Median holdout profit factor by entry threshold, both roots and all three resolutions pooled:

| `entry_std` | Bollinger | VWAP  | VWAP: share profitable | VWAP: median trades |
| ----------- | --------- | ----- | ---------------------- | ------------------- |
| 1.5         | 0.933     | 0.939 | 1.4%                   | 3,584               |
| 2.0         | 0.928     | 0.950 | 29.2%                  | 1,859               |
| 2.5         | 0.927     | 1.072 | 75.0%                  | 727                 |
| 3.0         | 0.797     | 1.087 | 66.7%                  | 173                 |

**The two sources respond to depth with opposite signs**, monotonically, which is a stronger claim than either median because it is a shape rather than a level. It is also §M26's own prediction from Leung and Li — a bounded optimal entry region — showing up as a floor the Bollinger form never had.

**The answer to [#221]'s question is 2.5, not 2.** At 2σ the VWAP source is barely better than the Bollinger one and fewer than a third of its configurations are profitable. At 2.5σ three quarters are, and it still takes about 700 trades on the holdout; 3.0σ is marginally better per trade and takes a quarter of the trades, which is a worse place to be measuring from.

## The matched null, which is what the result actually turns on

The best selection-window configuration per root and source, run against `randomentry.compare` on the holdout — 200 draws, entry days randomised, geometry and direction held:

| root | source    | observed PF | null median PF | verdict on PF                 | verdict on win rate |
| ---- | --------- | ----------- | -------------- | ----------------------------- | ------------------- |
| MNQ  | Bollinger | 0.585       | 0.844          | indistinguishable from random | worse (p = 0.01)    |
| NQ   | Bollinger | 0.595       | 0.887          | indistinguishable from random | worse (p = 0.01)    |
| MNQ  | VWAP      | 1.034       | 0.954          | indistinguishable from random | better (p = 0.04)   |
| NQ   | VWAP      | 1.042       | 0.966          | indistinguishable from random | worse (p = 0.01)    |

**This is an improved failure, not a pass.** The VWAP source stops being worse than random and turns profitable, which is where §M27 left the archetype and is a real change. It does **not** beat its null on profit factor or on expectancy on either root, and the two win-rate verdicts have opposite signs, so nothing about the win rate replicates. The MNQ VWAP row additionally has a badly mismatched trade count — 276 observed against a null median of 716 — which is the condition §M26 flagged as what makes a null comparison unclean, so it is the weakest row in the table.

**So the honest summary is: the entry rule is not yet shown to contribute anything the bracket did not.** A profit factor of 1.03 sitting inside its own null distribution is what "the geometry is doing the work" looks like.

## What is owed before any of this is quoted as a result

- **The matched null on a shortlist rather than on one configuration.** Four rows, each the best of 144, is the multiple-comparisons trap the standing rubric names. The distribution-level claims above are the trustworthy ones; the null table is the least trustworthy thing here.
- **Per contract, not the continuous series.** §M26's first trap is that both σ and the basis step at every roll seam, and an archetype that fires on extension fires around every roll for a reason that is not a market event. Every number above is off the back-adjusted continuous series and inherits that.
- **The VWAP pin.** [nt8-fidelity.md](../nt8-fidelity.md) §M26.4: the width is hand-rolled and so is ours by construction, but the basis under it has never been checked against NinjaTrader. [#170] cannot proceed on an unpinned basis.
- **`vwap_min_session_bars` has never been swept.** It was set to 30 by argument and held there for every number above.

[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#221]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/221
