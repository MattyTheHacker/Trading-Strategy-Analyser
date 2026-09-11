---
id: M28.8
title: "M28.8 — the range as a cross: every anchor by every length, and the hour that was missing"
archetypes: [OpeningRange]
issues: [258]
gates: [2, 3]
outcome: mixed
verdict: >-
  The anchor and the length are one cell rather than two axes; the one-hour cash range sits on a plateau with no excess on it, and §M28's 5, 15 and 30 turn out to have been the right set.
---

# M28.8 — the range as a cross: every anchor by every length, and the hour that was missing ([#258])

[#258] found a gap in the swept space rather than in the code: the only 60-minute window ever run was anchored at the European open, so "the first hour of the New York session" — which is what most sources mean by an ORB — had never been measured. It asked three questions before the run and all three were answered the same way: **every entry, every length the session leaves room to trade, and the anchor crossed with the length rather than confounded with it.**

**The gap was real and what was in it is not.** The hour sits on a plateau the population statistics cannot tell apart from the 30-minute range, and the null separates them cleanly: the cash breakout's excess over a permuted range is confined to lengths of 30 minutes and under, and the hour is past the edge of it.

## The cross, and the cut that decides which cells exist

Six anchors by seven lengths, plus the overnight span, is 43 ranges. Neither list is written down:

- **The anchors are the session's own phase starts**, `sessionrange.anchor_for` over every `SessionPhase` — the ETH open, London, the pre-open, the cash open, midday and the afternoon.
- **A range must complete before the phase the forced flat falls in.** Every position must be flat before the session close and `CLOSE` is the phase that flatten lands in, so a range still open at 16:00 ET has only the anomalous phase to trade in. `anchor + window <= anchor_for(FORCED_EXIT_PHASE)` is the whole filter. It drops the `close` anchor entirely and caps the afternoon anchor at 120 minutes.

The lengths are §M28's three, the missing hour, and 45/90/120 bracketing it. **The overnight span is in the length axis too**, at 930 minutes, and only because it is the one window that reproduces §M28.2's `overnight` range — §M28.5's shared-endpoint argument, applied to a range rather than to a stop.

**Each entry keeps the bracket its own campaign swept it on.** The breakout and the retest carry §M28.2's `stop_range_fraction` over `[0.25, 0.5, 0.75, 1.0]`; the fade and the rejection carry §M28.5's `[0.02, 0.05, 0.10, 0.25]` crossed with `stop_offset_ticks`. A single bracket across all four would have moved two things at once on two of them, because a fade's stop runs outward from the extreme it enters at where a breakout's runs inward. **The range geometry is therefore the only thing that moved.**

`--variants orb-geometry --strata orb-geometry --split` is **907,904 combinations across 20 sweeps in 60.6 minutes**, both roots, at the real commission for the root and one tick of slippage, in the `unfiltered` stratum stated in advance. Re-derivable from `results/campaign/OpeningRange.duckdb` under the variant names `<anchor>+<length>m entry=<mode> target=<scheme>`, and a measurement of one dated run.

**The shared cells reproduce the stored runs exactly.** The five ranges §M28.2 named are all in the cross, and on the fade and the rejection — the two entries whose brackets are §M28.5's and §M28.7's — **81,920 rows pair one-to-one across both windows with identical trades, net P&L, gross profit and loss, profit factor and drawdown.** The new cells sit in the same table as the stored ones rather than beside them.

## Read the length at one bar size, because pooling over resolutions reports the mix

A 5-minute range exists at two of the five campaign resolutions and a 30-minute one at all five, so a length axis pooled over resolutions is partly a resolution axis. **Every length in the cross exists at one minute**, which is the bar size to read it at. Unfiltered, holdout, readable rows only (`ambiguous_share` below `disambiguate.MIN_AMBIGUOUS_SHARE`), cash anchor, median profit factor, MNQ / NQ:

| length  | breakout          | retest        | fade          | rejection     |
| ------- | ----------------- | ------------- | ------------- | ------------- |
| 5m      | 0.910 / 0.931     | 0.954 / 1.001 | 0.353 / 0.405 | 0.916 / 0.976 |
| **15m** | **1.026 / 1.044** | 1.022 / 1.051 | 0.442 / 0.460 | 0.824 / 0.849 |
| 30m     | 0.937 / 0.978     | 0.900 / 0.934 | 0.552 / 0.551 | 0.808 / 0.832 |
| 45m     | 0.917 / 0.978     | 0.926 / 0.947 | 0.748 / 0.726 | 0.922 / 0.945 |
| **60m** | 0.942 / 0.988     | 0.899 / 0.934 | 0.826 / 0.826 | 0.962 / 0.984 |
| 90m     | 0.924 / 0.970     | 0.917 / 0.966 | 0.800 / 0.795 | 0.866 / 0.906 |
| 120m    | 0.941 / 0.983     | 1.002 / 1.042 | 0.731 / 0.747 | 0.863 / 0.881 |

**Everything from 30 minutes upward sits inside 0.917–0.942 on MNQ and 0.970–0.988 on NQ** — a spread of 0.025 and 0.018 across four lengths with the missing hour among them. The 15-minute range is the only breakout cell whose population median clears 1.0, and it was already in the swept set. On the selection window the same plateau is 1.011–1.119 and 1.000–1.136, so the shape is not a holdout artefact; only its level is.

## The anchor and the length are one cell rather than two axes

Median profit factor, breakout, 1-minute bars, readable, holdout, MNQ:

| anchor     | 5m    | 15m       | 30m   | 45m   | 60m   | 90m   | 120m  |
| ---------- | ----- | --------- | ----- | ----- | ----- | ----- | ----- |
| overnight  | 0.823 | 0.835     | 0.836 | 0.871 | 0.853 | 0.881 | 0.862 |
| london     | 0.667 | 0.760     | 0.861 | 0.894 | 0.886 | 0.890 | 0.915 |
| pre-open   | 0.865 | 0.784     | 0.834 | 0.894 | 0.904 | 0.921 | 0.918 |
| cash-open  | 0.910 | **1.026** | 0.937 | 0.917 | 0.942 | 0.924 | 0.941 |
| midday     | 0.709 | 0.808     | 0.882 | 0.976 | 0.970 | 0.926 | 0.948 |
| afternoon  | 0.668 | 0.714     | 0.797 | 0.873 | 0.915 | 0.879 | 0.871 |
| **spread** | 0.243 | 0.312     | 0.140 | 0.104 | 0.117 | 0.047 | 0.087 |

**The anchors converge as the length grows, and the cash open is the one anchor the length barely moves.** Across anchors the spread falls from 0.243 at five minutes to 0.087 at two hours; across lengths the spread is 0.116 at the cash open against 0.247 at the afternoon, 0.248 at London and 0.267 at midday. NQ gives the same picture at 0.113 against 0.223 / 0.227 / 0.256.

Read together, the cross says one thing: **what a long range buys is what the cash open gives for free.** A two-hour range from any anchor is worth about what a five-minute range from the cash open is worth, and the cash open is first or second of the six at every length.

The variance decomposition agrees and carries its own caveat. At one minute, readable, holdout, MNQ / NQ:

| entry     | anchor        | length        | the cell      |
| --------- | ------------- | ------------- | ------------- |
| breakout  | 0.070 / 0.092 | 0.128 / 0.094 | 0.241 / 0.230 |
| retest    | 0.090 / 0.054 | 0.028 / 0.013 | 0.257 / 0.161 |
| fade      | 0.052 / 0.030 | 0.078 / 0.065 | 0.159 / 0.131 |
| rejection | 0.016 / 0.036 | 0.008 / 0.009 | 0.117 / 0.168 |

**The cell exceeds the sum of the two main effects on all four entries and both roots**, which is an interaction rather than two axes. The caveat is that eta-squared carries no degrees-of-freedom correction and the cell has 43 levels against the anchor's 6 and the length's 7, so part of the gap is arithmetic: the retest's 0.257 against a sum of 0.118 is more than that can account for and the rejection's is not. **The tables above are the evidence and this is a summary of them, not the other way round.**

For scale, `stop_range_fraction` runs 0.30–0.33 on the breakout and 0.57–0.60 on the fade in the same rows. **The bracket is still the largest lever on every entry that reads it**, exactly as §M28.5 and §M28.7 found; the range geometry is second.

## The forced flat is not what produces the level, and the cash anchor is the control

Every long range leaves less session behind it, so its trades increasingly end at the flatten rather than at a bracket level. At the cash anchor on one-minute bars the breakout's `session_close_share` runs **0.104 → 0.206 → 0.349 → 0.448 → 0.515 → 0.607 → 0.683** across the seven lengths, and pooled across all six anchors the profit factor rises monotonically with it — 0.794 below a tenth to 0.990 above seven tenths, with the profitable share going 0.098 to 0.469.

**That gradient is the anchor in disguise, and the cash anchor is what says so.** Along the cash row the close share rises 6.6× while the profit factor moves within 0.116 and is *highest* at the second-shortest length. A variable that sweeps that far while the statistic does not move is not what produces the statistic. `CONTRIBUTING.md`'s "read `session_close_share` before believing a result" is what turns the pooled table into a control instead of a finding.

## Gate 2 across the cross, and §M28.7's trap reappears on schedule

860 (root × variant) cells; 432 pass raw. **That number is the trap rather than the result** — confined to cells whose shortlist is readable in both windows, 489 remain, 90 pass and 34 variants pass on both roots. The sharpest single instance is `cash-open+60m entry=rejection target=R`, which returns a held-out shortlist profit factor of **128.8 on MNQ and 138.2 on NQ at an `ambiguous_share` of 0.84 to 0.91** — §M28.7's finding reproduced at a range it never ran.

Readable cells passing, per entry, MNQ / NQ:

| entry     | readable cells | passing     |
| --------- | -------------- | ----------- |
| breakout  | 86 / 86        | 19 / 27     |
| retest    | 24 / 23        | **13 / 12** |
| fade      | 123 / 123      | 5 / 7       |
| rejection | 13 / 11        | 3 / 4       |

**The retest passes gate 2 in about half its readable cells and the fade in about one in twenty**, on both roots. That ordering is the one §M28.2, §M28.5 and §M28.7 each reached separately, now measured in one pass over one grid.

## Gate 3 — the observed statistic cannot tell the lengths apart and the null can

`matched_random_ranges` — the null a level-based trigger needs — over the top twenty of the cash-anchored breakout at `target=width`, ranked on the selection window and tested on the held-out one, 100 draws each. Medians over the twenty, MNQ / NQ:

| length  | observed PF   | null PF       | excess              | p             | p < 0.05 of 20 | held-out trades |
| ------- | ------------- | ------------- | ------------------- | ------------- | -------------- | --------------- |
| **15m** | 1.090 / 1.106 | 0.917 / 0.921 | **+0.159 / +0.191** | 0.089 / 0.069 | **7 / 8**      | 363 / 355       |
| **30m** | 1.103 / 1.125 | 0.923 / 0.937 | **+0.195 / +0.191** | 0.069 / 0.040 | **8 / 12**     | 341 / 333       |
| 45m     | 1.024 / 1.048 | 0.919 / 0.933 | +0.079 / +0.111     | 0.475 / 0.228 | 0 / 0          | 321 / 313       |
| 60m     | 1.076 / 1.047 | 0.954 / 0.936 | +0.124 / +0.106     | 0.327 / 0.327 | 0 / 0          | 306 / 297       |

**The observed profit factor moves within 0.08 across the four lengths and the excess halves.** Fifteen of the forty configurations at 30 minutes clear p < 0.05 and **none of the forty at 45 minutes or an hour does**. The break sits between 30 and 45 minutes and it is sharp rather than a gradient.

**It is the observation that falls, not the null that rises.** The permuted-range arm holds at 0.917–0.923 on MNQ across 15/30/45 and only reaches 0.954 at the hour; on NQ it is flat at 0.921–0.937 across all four. And it is not the trade floor arriving: the shortlist's held-out trade count falls only from 363 to 306 across the four lengths, well clear of `MIN_TRADES`.

**This is the strongest gate-3 result the archetype has produced, and what produced it is the confinement rather than new data.** §M28.2 ran the same null on the same entry and reported an excess of +0.125 to +0.178 with "only one cell clears p < 0.05" — but its shortlist was ranked across every range and resolution it had swept, so it pooled the two lengths that separate with three that do not. **A shortlist drawn over a mixture of geometries dilutes the one that works**, which is a statement about how a shortlist is drawn rather than about the strategy, and it is the same lesson § "A shortlist is the wrong instrument for an A/B variant pair" records from the other direction.

The standing caution binds and is not small: twenty configurations chosen on the selection window are not twenty independent tests — they neighbour each other in one grid on one set of bars — and the smallest p of twenty is expected near 0.05 under any null. What is more than that is the *count*, seven to twelve of twenty against an expectation of one, on two roots, at exactly the two lengths and at neither of the others.

## The verdict, and what [#258] asked

- **The one-hour cash range is now swept and is not a finding.** It sits on the plateau, passes gate 2 on MNQ at both target schemes and on NQ only at `target=width`, and produces no configuration that separates from a permuted range on either root. The gap was real; the thing in it was the number the 30-minute range already gave, without the excess that goes with it.
- **The anchor was worth crossing and the length was worth extending, because the two interact.** They cannot be reported as separate axes, and §M28.2's `london=60m` was confounded with its length exactly as [#258] suspected — at the cash open the length is nearly inert, and at London it is worth as much as the anchor is.
- **§M28's "5, 15 and 30 are what every source means" turns out to have been the right set**, and this is the first measurement that could have said otherwise. Extending the length axis past 30 minutes found a plateau with no excess on it; the lengths the literature already names are the two that carry one.
- **Nothing here rehabilitates the fade or the rejection.** Both stay parked with §M28.5's and §M28.7's reasons: the fade passes gate 2 in 5 and 7 of 123 readable cells, and the rejection's profitable cells are still the ones the fill assumption decides.

**What would justify the next run.** Not another geometry — the cross is complete under the session's own cut and the two axes are now measured together. What the cross raises is why the excess stops between 30 and 45 minutes, and the candidates are separable: the range width itself, the hold time it implies, or the share of the session left after it. That is a question about one range's bracket and exit rather than about which range to measure, which is where § "Parked is not abandoned" would want the next OpeningRange run pointed.

[#258]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/258
