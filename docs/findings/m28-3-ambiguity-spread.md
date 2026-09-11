---
id: M28.3
title: "M28.3 — the ambiguity spread: a shortlist's second arm"
archetypes: []
issues: [248]
gates: []
outcome: tooling
verdict: >-
  A ceiling on `ambiguous_share` is the wrong instrument; the spread between the two policies is reported rather than gated, and that is the decision.
---

# M28.3 — the ambiguity spread: a shortlist's second arm ([#248])

§M28.2's retest shortlist is the case: ranked on held-out profit factor, it selected almost exclusively configurations whose outcome the ambiguity assumption decides, at sixteen times its own population's `ambiguous_share`. Nothing in the campaign tools said so, and nothing in them would have said so on the next archetype either.

## A ceiling on `ambiguous_share` is the wrong instrument, for two separate reasons

**It is regime-dependent.** The share is an outcome statistic, and §M13 expects it to climb with bar size. A ceiling low enough to catch the retest's 0.34 would not be excluding unattributable results; it would be excluding coarse resolutions on every archetype in the registry.

**It measures the wrong thing.** The share counts how often the assumption was invoked. What a shortlist needs to know is how much the answer depends on it, and those come apart in both directions — a configuration resolving a third of its legs by assumption whose profit factor barely moves is safe to rank, and one resolving a twentieth whose profit factor moves by 1.5 is not.

## What the spread is, and why `AMBIGUITY_WORST_CASE` is the right arm to read it with

`tools/campaign_ambiguity.py` re-runs each shortlisted row under both policies and reports the two profit factors and the gap between them. The gap is **the width of the band the bar data cannot narrow**: one end is NT8's rule, the other is every ambiguous bar resolved against the trade, and the truth is somewhere inside. § "Eleven strata per root, one dimension at a time" dropped the worst case as a *sweep* axis because ranking on it would rank against a fill rule the prime directive rejects, and closed by saying re-add the axis to re-measure it. Re-running a shortlist under it is not ranking on it.

Each row is re-run on the bars its own `window` names, so the first arm reproduces the stored figure exactly and `campaign_shortlist.verify` refuses it otherwise. That is what makes the second number a band around a figure that was actually ranked rather than around a re-derivation of it.

**The spread is one-sided by construction.** Every ambiguous bar the worst case resolves is one the ranked arm may have given to the target, so gross profit can only fall and gross loss can only rise; `tests/test_campaign_ambiguity.py` pins that a negative spread means the two arms are not the same configuration. Cost is a shortlist re-run rather than a second sweep — the same shape as the null test.

## Reported, not gated, and that is the decision

**The ranking statistic stays `AMBIGUITY_NEAREST_TO_OPEN`**, and no row is dropped or re-ordered. The prime directive governs what the shortlist claims; the second arm is attribution.

Gating was considered and deferred rather than forgotten. Reporting the second arm beside each shortlist changes no stored comparison. **Gating on it changes every one** — §M27's and §M28.1's included, whose shortlists were selected without it and whose spreads are therefore unknown rather than small. If a gate follows it goes where `MIN_TRADES` is and it is stated the way `MIN_DRAW_FREEDOM` and `MIN_DONOR_SESSIONS` are, as a meaning: **the claimed edge must survive the assumption**. Not: the assumption must be rare. `campaign_ambiguity.STATEMENT` is that sentence, reported per shortlist so that the figures a gate would be calibrated against accumulate before the gate exists.

## What the spread bounds, and what would settle it

It bounds the risk; it does not resolve it. **Neither tier can say whether nearest-to-open is right**, because NT8 has the same blind spot — Tier 2 will re-validate an unattributable profit factor rather than contradict it. This is a live-trading risk rather than a tier-disagreement risk, which is why no amount of NT8 reconciliation touches it.

Finer bars settle it, and above one minute they are already in the archive: §M13 establishes that OHLC aggregation is associative, so a 5-minute bar is five 1-minute bars and the first sub-bar holding only the stop or only the target says which came first. Only the residue still ambiguous at one minute needs `data/tick/`. **That is built, in §M28.4**, and it must not reach `nqbt/sim/` — NT8 guesses on the same bars, so resolving a fill truthfully there would make the two tiers disagree on exactly those bars, which is the more-precise-than-NT8 error precisely. As a diagnostic it is the trade-review side's reasoning: nothing is being simulated, an assumption is being scored, and it would give nearest-to-open an empirical accuracy worth carrying in `docs/nt8-fidelity.md`. Its own issue rather than this one.

The narrower constraint §M28.2 named for the retest — restricting a shortlist to configurations whose stop and target do not both sit inside one bar — is not built here. It is a pre-trade geometric property rather than an outcome statistic, so it cannot delete a coarse resolution that was fine, but it does not generalise across the registry the way the spread does. **§M28.4 makes it unnecessary for the retest**, which is the case that asked for it: the minute bars settle the question the constraint existed to avoid asking.

[#248]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/248
