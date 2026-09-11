---
title: "Counting the confluence a trade actually had"
archetypes: [EmaCrossover]
issues: [74]
gates: [3]
outcome: negative
verdict: >-
  The gradient in confluence is monotone and the matched null removes it, so the count sorts trades rather than adding edge.
---

# Counting the confluence a trade actually had ([#74])

**There are two confluence questions and only one of them needs a strategy.** [#74] asks for the *gating* half — "at least N of M filters", with the minimum sweepable — and § "The build spec's three loose ends" is what that measured. The other half asks what was true when the trades that already happened were taken, and it needs no rule change at all: annotate each trade with **how many of a named set of conditions held at its entry bar**, then stratify realised P&L by that count. **The second question is the more useful one**, and it is the one a person actually asks when they say "does more confluence help".

Almost all of it already existed. `nqbt/annotate.py` puts every condition the dataset holds on a row per trade, and `nqbt/review.py` groups realised P&L by any one of them. The missing piece was a single column, which is what finally gives `conditions.count_true` a caller on the review side: `annotate.confluence` adds the count, and `review.by_outcome` reads the same data backwards — mean confluence per outcome — because that is the phrasing the question usually arrives in.

**The denominator is named by the caller and never derived.** Counting whatever booleans an annotation happens to carry would change the number the moment a dataset is prepared with one more moving-average period, and nothing would say so. A condition that is false because it could not yet be computed counts as not true, as it does everywhere else here.

## The gradient is monotone, and on its own it is not a finding

MNQ, 5-minute, the long side of EmaCrossover at its defaults, $1.50 round trip and one tick, over the continuous series **after its first roll** — §M27.7's own recommended fix for the gapped-target case rather than a widened price guard. 6,904 trades, counted over five bullish conditions holding at 88.6%, 76.4%, 58.5%, 67.5% and 63.5% of entries, so no one of them is a tautology of the entry:

| confluences | trades | win rate | profit factor |
| ----------- | ------ | -------- | ------------- |
| 0           | 247    | 2.8%     | 0.055         |
| 1           | 555    | 17.7%    | 0.347         |
| 2           | 811    | 31.1%    | 0.778         |
| 3           | 1,215  | 36.0%    | 0.890         |
| 4           | 1,737  | 39.4%    | 1.086         |
| 5           | 2,339  | 46.9%    | 1.522         |

Read backwards, winners averaged 3.94 of the five and losers 3.31.

**And it holds out.** Split 60/40, the profit factors run 0.062 / 0.210 / 0.704 / 0.889 / 1.093 / 1.476 on the selection window against 0.046 / 0.463 / 0.853 / 0.890 / 1.082 / 1.558 on the held-out one — monotone in both, and within a hundredth of each other at 3, 4 and 5.

## What the matched null does to it, which is the whole point

A monotone gradient is what a trending market produces whether or not the entry rule contributes anything, so the standing rubric applies: **a number with no null is not a finding.** Placing the same count over a matched random entry — same trade count, same time-of-session profile, same bracket, 20 draws — the market's own gradient is not monotone at all. It is **U-shaped**: a random long returns a profit factor of 1.183 with none of the five true, falls to 0.665 at three, and recovers to 1.271 at five.

The excess is therefore the only honest column:

| confluences | rule  | matched null | excess     |
| ----------- | ----- | ------------ | ---------- |
| 0           | 0.055 | 1.183        | **−1.128** |
| 1           | 0.347 | 0.854        | −0.507     |
| 2           | 0.778 | 0.738        | +0.040     |
| 3           | 0.890 | 0.665        | +0.224     |
| 4           | 1.086 | 0.857        | +0.229     |
| 5           | 1.522 | 1.271        | +0.251     |

**The crossover entry beats a random one only where at least two of the five hold, and below that it is far worse than random** — at zero confluences it is more than a whole profit factor worse, which is a stronger statement than anything the archetype's pooled numbers contain. The excess plateaus at about +0.22 to +0.25 from three upward, so the last two confluences buy the *level* and not the *edge*.

**This sharpens §M27's gate 3 rather than contradicting it.** That campaign put EmaCrossover's excess over its null at about +0.03 and read it as "essentially nothing". It is now visible as a mixture: a badly negative low-confluence stratum averaged against a consistently positive high-confluence one. A pooled excess near zero is not evidence that an entry does nothing; it is evidence that nobody has asked which of its trades it does something on.

## What this is not

**Hypothesis-generating, exactly as `review.STATUS` says of everything that module prints.** One root, one resolution, one configuration, the long side alone, and five conditions chosen by hand — the multiple-comparisons machine `nqbt/guard.py` exists for. The holdout above is a split of one series rather than the shuffled-label null and second window a claim would need.

**The count is not independent of the entry.** `above_ema_21` holds at 88.6% of the entries of an EMA(9)/EMA(21) long, so the count and the signal share machinery; the four other conditions are what carry it. A set drawn from indicators the archetype does not read would be the cleaner test and has not been run.

**Ten legs in 390,720 across the twenty null draws exit outside their own bar**, every one a `target` a bar gapped through, worst 263.75 points — [#244]'s open question, hit harder by a random entry because it can be placed in front of an overnight gap. Those trades are dropped rather than admitted by a widened `price_tolerance`, because a guard widened past 260 points no longer catches the back-adjusted series it exists for.

[#244]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/244
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
