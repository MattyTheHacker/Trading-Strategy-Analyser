---
id: M64
title: "M64 — the new exits do not pay in the midday cells, and the confluence size clears its account null on TopStep only"
archetypes: [InsideBarTrailing, OpeningRange]
issues: [354, 449]
gates: [4]
outcome: negative
verdict: >-
  Read from stored outputs, with no new run. No exit clears either midday cell at 5 minutes under its own pre-registered bar, the late-day arms that gain held out all lose on the selection window, and their survival of the exclusion is the forced flat's legs relabelled as stops. So #344's Phase 2 is a negative result and the epic moves to Phase 3. The confluence size, matched against its own sizes shuffled for the first time through the accounts, raises the MNQ pass rate on TopStep 150K and median net on TopStep 50K and 150K, which is unregistered; on Apex it still loses money and on NQ it passes nothing more.
---

# M64 — the new exits do not pay in the midday cells, and the confluence size clears its account null on TopStep only ([#354])

## In plain terms

[#344]'s Phase 2 built new ways to leave a trade: early exits, stops that move, and a trail to structure. [#354] asked whether any of them improves the two midday candidates enough to change what gets ported.

**None does.** Each was tested under its own bar, and neither midday cell clears at 5 minutes. A few exits late in the day look better on the later data, but all of them look worse on the earlier data, so a selection made on the earlier data would never choose them. The epic moves to Phase 3.

Separately, the read that [#344]'s port was waiting on had been run and never written up. Adding contracts on favourable signals beats the same contracts placed at random on TopStep on MNQ. On Apex it still loses money, and on NQ it passes no more accounts.

## The exits under their own bars

Every campaign pre-registered its bar, the selection window's pick paying held out on both roots, except where noted. All figures are at 5 minutes, MNQ / NQ, on the October 2026 re-sweep.

| campaign                                                   | InsideBarTrailing, midday                                                                   | OpeningRange, midday       |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------- |
| [§M48](m48-early-exit-result.md), conditional market exits | pick costs −0.187 / −0.148 ([§M61](m61-registry-resweep-fill-fixes.md))                     | does not clear             |
| [§M50](m50-early-exit-tier-2-result.md), second tier       | does not clear (§M61)                                                                       | does not clear (§M61)      |
| [§M52](m52-early-exit-tier-3-result.md), third tier        | pick costs −0.050 / −0.148                                                                  | pick costs −0.017 / −0.017 |
| [§M49](m49-structure-trail-result.md), trail to structure  | 20 of 24 arms significantly down on both roots, none up on NQ (§M61); described, not tested | not swept                  |

## Gate 4, the accounts and the late-day arms

[#354] also asked for the exclusion, gate 4 and the prop reading with the new axes swept in. These reads were already stored, for the selection window's top 20 at 5 minutes. **The bar below is not pre-registered**: it was fixed in a local script before these tables were first read, after §M48 to §M52 had been. On both roots, against its own control, an arm has to raise the median profit factor, keep at least as many configurations surviving the exclusion and at least as many with a bootstrap 5th-percentile profit factor above 1.0, and pass the walk-forward.

The controls:

| cell                                                  | median PF, whole → without session-close legs | survive the exclusion | bootstrap floor above 1.0 | walk-forward, pooled |
| ----------------------------------------------------- | --------------------------------------------- | --------------------: | ------------------------: | -------------------: |
| InsideBarTrailing, MNQ                                | 1.358 → 0.747                                 |               0 of 20 |                  17 of 20 |                1.342 |
| InsideBarTrailing, NQ                                 | 1.363 → 0.585                                 |               0 of 20 |                  13 of 20 |                1.308 |
| OpeningRange `window=15m stop=opposite target=R`, MNQ | 1.338 → 0.382                                 |               0 of 20 |                  16 of 20 |                1.396 |
| OpeningRange `window=15m stop=opposite target=R`, NQ  | 1.337 → 0.392                                 |               0 of 20 |                  15 of 20 |                1.406 |

**On InsideBarTrailing 7 of 124 arms clear**: `bars10@-0.5R`, `close60m`, `close120m`, `late15m-entry`, `late30m-entry`, `late30m-bar-extreme` and `late60m-bar-extreme`. **On OpeningRange 209 of 1,200 clear, and most of that is the bar being too weak**: 133 clear with no gain in survivors or bootstrap floor on either root, because a count can tie with its control and a small profit factor gain then carries the arm. The other 76 are not read as a result either, for the reason below.

**The late-stop arms survive the exclusion on 18 to 20 of 20 configurations, and that is relabelling.** They move the stop to the bar's extreme 30 or 60 minutes before the close, so a leg the forced flat used to close now closes on the stop, and the exclusion no longer removes it. On InsideBarTrailing, session-close legs fall from a median 184 to 2 on MNQ at 60 minutes, and net over the whole book moves from $37,835 to $38,929. **OpeningRange shows the same thing across more arms**: in the 241 of 2,400 arm and root cells with more survivors than their control, session-close legs fall to a median 3% of the control's, and net falls by a median 47%.

**The late-day arms take the window's sign the other way from §M37 and §M39**: they lose on the selection window and gain held out, so the selection window cannot point at them. Median profit factor over every configuration in the cell, MNQ / NQ:

| arm                   |     selection |      held out |
| --------------------- | ------------: | ------------: |
| control               | 0.970 / 1.073 | 1.219 / 1.172 |
| `close30m`            | 0.966 / 1.066 | 1.252 / 1.207 |
| `close60m`            | 0.942 / 1.042 | 1.271 / 1.211 |
| `close120m`           | 0.911 / 0.981 | 1.235 / 1.138 |
| `late30m-bar-extreme` | 0.963 / 1.064 | 1.227 / 1.190 |
| `late60m-bar-extreme` | 0.930 / 1.027 | 1.247 / 1.206 |

**Through the accounts, on MNQ, no InsideBarTrailing arm beats its control on all four presets**, counting a higher profitable share, or an equal one with a higher median net: none of 124. Profitable share and median net:

| arm                   |    TopStep 50K | TopStep 150K |    Apex 50K |   Apex 150K |
| --------------------- | -------------: | -----------: | ----------: | ----------: |
| control               | 100% / +13,378 |   45% / −220 | 5% / −2,021 | 0% / −3,903 |
| `close30m`            | 100% / +15,091 |   60% / +798 | 5% / −2,080 | 0% / −3,903 |
| `close60m`            | 100% / +15,089 |     50% / −9 | 5% / −1,657 | 0% / −3,903 |
| `late30m-bar-extreme` | 100% / +15,154 |   50% / +181 | 5% / −2,269 | 0% / −3,903 |
| `late60m-bar-extreme` | 100% / +12,827 | 25% / −1,371 | 5% / −2,101 | 0% / −3,903 |

**On OpeningRange, 16 of 1,200 arm cells pay on more presets than their control, 459 on fewer and 725 on the same number**, by median net.

## The confluence size against its own sizes shuffled

[§M47.1](m47-1-confluence-sizing-5.md) raised the MNQ pass rate on all four presets and could not say how much of that was simply more contracts. [#449] built the read that can: each configuration's sizes shuffled across its signals and replayed through the same accounts, 200 draws each, with average contracts matched closely (6.55 against 6.62 on the arm below). It ran in the October 2026 reads and was not written up until now.

`size=confluence`, midday at 5 minutes on MNQ, pooled over the shortlist:

| account      | pass rate, own vs shuffled |     p | median net, own vs shuffled |     p |
| ------------ | -------------------------: | ----: | --------------------------: | ----: |
| TopStep 150K |             50.5% vs 39.9% | 0.005 |            +2,137 vs −1,300 | 0.005 |
| TopStep 50K  |             26.7% vs 26.7% |  0.50 |          +21,324 vs +14,918 | 0.005 |
| Apex 150K    |               1.5% vs 0.6% | 0.005 |            −3,645 vs −3,978 | 0.005 |
| Apex 50K     |               1.1% vs 1.5% |  0.99 |            −2,071 vs −2,171 |  0.24 |

**Across the six sizing arms, 12 of 24 MNQ tests clear p = 0.05 on pass rate and 6 on net; on NQ, none of 24 on pass rate and 1 on net.** 0.005 is the smallest p 200 draws can return. This is not pre-registered, and 48 tests were read. Apex 150K clears and still loses money. `size=volume`, the one label that clears §M47.1's profit factor null alone, clears nothing here.

## What this settles, and what it does not

- **[#344]'s Phase 2 is a negative result**, which parks this configuration space and retires nothing. By [#354]'s own terms the epic goes to Phase 3: [#355], [#356] and [#357].
- **The stop [#344] would port stays as it is.** No exit, moved stop or structure trail replaces it.
- **Closing or tightening 30 to 60 minutes before the close remains a lead and no more.** §M48 named it after reading; this adds that the selection window cannot pick it. It would need its own pre-registered test.
- **The confluence size stays `TIER1_ONLY`.** It now has a matched reason to be considered for a later port on TopStep, and none on Apex or on NQ.
- **Not read here**: 1 and 2 minutes, any stratum but midday, and §M49's or §M50's arms through a read of their own beyond these tables.

## How this was measured

Nothing was re-run. Every figure comes from the stored `tools/campaign_gates.py` outputs of the reads that followed the October 2026 re-sweep, for `early-exit`, `early-exit-2`, `early-exit-3`, `ibt-structure` and `confluence-sizing --reads prop-null`, compared by a local script. `campaign_sizing.prop_null_pooled` placed the account nulls. **Every re-run behind these tables reproduced its stored row**: all 49,856 midday rows at 5 minutes, on trades and on net to within a millionth, on the bars they were swept on. A profit factor in the pre-registered table is that campaign's, or §M61's where it re-read one.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#354]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/354
[#355]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/355
[#356]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/356
[#357]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/357
[#449]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/449
