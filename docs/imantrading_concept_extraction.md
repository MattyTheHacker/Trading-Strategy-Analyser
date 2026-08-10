# ImanTrading — Concept Extraction for Automated NQ/MNQ Work

Reference notes synthesised from the nine transcribed videos (`master_transcript.txt`), my two earlier
note files on the "Super Scalping" / "Categorical Trading" videos, and imantrading.org (strategy page,
beginner guide, prop-firm guide) as of August 2026.

Companion to `ta_course_concepts_reference.md`. Same convention: what is directly codeable vs. what needs
numeric definition first, and what is specific to his style and shouldn't be force-fitted.

**Governing caution:** his trading is discretionary, manual, 20–30 second charts, hold times measured in
seconds to minutes, one to a few contracts. Almost none of the *specifics* transfer. Several of the
*framing devices* are unusually good and attack problems the project currently has open.

---

## 1. Source assessment

**In his favour:**

- Sells no course, mentorship, indicator, alerts, or private community, and says so consistently across
  four years of content. That's genuinely unusual in this space and removes the dominant incentive to
  overstate.
- Documented the entire journey publicly from day one on a second channel, including the losing years.
  Failures are on record, not just the wins.
- Explicit and repeated risk disclosure; describes himself as not a full-time trader making modest side
  income, and says so unprompted.
- Argues consistently *against* his own authority — separate the message from the messenger, test
  everything, follow everybody and nobody.

**Against, or at least to hold in mind:**

- The site's revenue model is prop-firm affiliate links plus a NinjaTrader affiliate link. **This means
  the firm rankings and reviews carry a direct conflict of interest.** The strategy and psychology
  content does not, which is the part worth reading. Worth keeping those two buckets separate.
- Track record is self-reported dashboard screenshots. Claims ~$34k cumulative payouts through end of
  2025, and one published funded account (Sept 2025 – Mar 2026): 57.6% win rate, average win $161.93,
  average loss $101.83. That works out to roughly **+$50/trade expectancy, profit factor ~2.16** — a
  genuinely healthy profile if real, but it's one account over ~6 months with no independent
  verification.
- **Note the internal discrepancy:** he repeatedly frames his approach as 1:1 reward-to-risk, but that
  published account has an average win 1.59× the average loss. Either the brackets aren't actually 1:1
  in practice, or winners get extended and losers scratched early. Don't take the "1:1" framing at face
  value.
- He is not operating at size, and says so.

**Net:** treat as a thoughtful source of framing ideas, not as a validated edge. Which is exactly how he
tells you to treat him.

---

## 2. The direct challenge to this project

This has to be dealt with first, because he makes it repeatedly and it's the strongest argument against
the whole automation premise:

> If a pattern or system genuinely worked on its own, you could code it into a NinjaScript strategy for
> free — and you'd end up with an unprofitable algorithm. Discretion is what makes a non-working system
> work. Anything sellable as a set of instructions is therefore worthless.

**Where he's right:** this is a good description of what happens when you automate publicly-taught
chart-pattern rules. It is also *exactly what nqbt has already measured* — 0 of 192 combinations of the
DeadCatBounce space clear a profit factor of 1.0 over 4.7 years once costs are applied, best PF 0.746.
His prediction and my measurement agree. That's worth taking seriously rather than explaining away.

**Where the argument overreaches:**

- It's unfalsifiable as stated, and he doesn't test it — he explicitly declines to run the experiment he
  proposes in the risk/reward video ("why don't you do the tests? because I don't want to").
- His own headline example undercuts him. Jim Simons is offered as proof that people keep working edges
  private; Simons ran a *purely systematic* fund. That's a counterexample to "codeable means worthless",
  not support for it.
- The defensible version of his claim is narrower: **simple, widely-taught, publicly-available rule sets
  do not survive transaction costs when automated.** That's a claim about the search space, not about
  automation.
- His own reasoning contains the rebuttal: *the only way to find out whether a pattern works is to code
  it and test it.* nqbt is that test. He recommends building it and then assumes the answer.

**How to hold this:** as a well-calibrated warning that the *category* of strategy currently being
tested — a handful of MA/VWAP gates on minute bars — is the category most likely to be already arbitraged
away. Not as a reason to stop. It argues for changing where the search happens, not for abandoning the
search.

---

## 3. What transfers — ranked by value to the project

### 3.1 Regime-conditioned evaluation (highest value)

His central argument, from the "huge discovery about price action" video:

Any fixed rule set implicitly requires a particular market character. On days without that character it
doesn't merely fail to fire — it bleeds. So the real question is not "is this profitable" but "how often
do its conditions occur, and does its performance during those windows offset the guaranteed cost of the
windows where they don't?"

**Why this matters here specifically.** nqbt currently ranks combinations by aggregate profit factor
across the entire 1.65M-bar continuous series, 2021-12 → 2026-08. That aggregate is a weighted average
across wildly different regimes — 2022's trending selloff, 2023-24's grind, whatever 2025-26 was. A rule
set that is PF 1.4 in one regime and PF 0.4 in another shows up as PF ~0.75 and gets discarded. **The
current "nothing survives" finding cannot distinguish between "no edge anywhere" and "edge in a subset of
conditions, drowned by the rest."**

**Concrete change:** tag every bar with a regime label during `runner.prepare`, carry the label onto each
trade record, and stratify `stats.summarise` by regime. Same sweep, same simulation, extra grouping
column. This is cheap — a precomputed 1D array plus a groupby — and it changes what the existing 192
combinations mean. Worth doing before anything else.

Second-order consequence: if a regime split does show structure, the natural next architecture is a
regime gate on entry rather than a new entry archetype. That's a single extra boolean in the condition
AND, not a new `@njit` function.

### 3.2 Categorical price action as the regime classifier

His actual strategy, reduced to its skeleton. Price action sits on a spectrum between two poles:

- **Consolidation** — expect price to stay within where it has recently been. Trade mean reversion: enter
  at the edges of the range, target *inside* the range, stop *outside* it. The high-probability loss is
  trying to time the break.
- **Direction** — expect price to reach new territory. Trade with momentum: target *outside* the recent
  range, stop *inside* it. The high-probability loss is fading it.
- **Third state: unclassifiable.** If it's too chaotic to categorise, don't trade. This is a distinct
  state, not a coin flip between the other two.

The stop/target *geometry inverts* between the two states. That's the actual content of the idea and it's
more specific than the usual "trend vs range" framing.

His stated failure mode is worth keeping: **a trade fails when the category changes while you're in it,**
not when you picked the wrong side. That's a coherent definition of trade invalidation and it maps onto a
stop rule.

**Codeable definitions to test** (none of these are his — he does it by eye):

| Classifier | Notes |
|---|---|
| Kaufman efficiency ratio: `abs(close[t]-close[t-n]) / sum(abs(diff(close)))` over n | Cleanest fit. Bounded 0–1. High = directional, low = consolidating. Not in TA-Lib, ~3 lines of numpy, fully vectorisable. |
| ADX | In TA-Lib. Familiar but laggier and less interpretable than ER. |
| Bollinger bandwidth, or rolling high−low range ÷ ATR | Cheap. Measures compression rather than direction. |
| Rolling realised-vol-of-ATR | His "is the ATR itself all over the place?" test — the unclassifiable state. Directly maps to a no-trade gate. |

Recommendation: implement efficiency ratio first, as a `conditions.py` 1D array with the lookback and the
two thresholds (direction-above, consolidation-below) as sweepable axes. The band between the thresholds
is the no-trade state, which gives the third category for free.

### 3.3 A random-entry null model (his best idea, unbuilt)

From the risk/reward video. His argument: without an edge, changing the reward-to-risk ratio changes
nothing — a wider target just lowers your win rate by exactly the amount that keeps expectancy flat.
Therefore the break-even win rate implied by a given R:R is an estimate of *the probability that trade
actually reaches target*. A 1:50 bracket isn't a clever asymmetry, it's a 98%-likely loss.

This is basically correct for a random-entry baseline, and it's directly relevant to my own diagnosed
problem. My trade history showed ~55% win rate with average losses more than double average wins. The
obvious fix is "widen targets, tighten stops until R:R clears 1." His point is that if the entries carry
no signal, that fix converts win rate downward and lands in the same place. **R:R and win rate aren't
independent knobs.** The only thing that moves expectancy is an entry whose *conditional* hit probability
beats the break-even rate for the bracket geometry being used.

**The build:** a random-entry control arm in nqbt. Same bars, same bracket geometry, same costs, same
`@njit` exit logic — entries drawn at random (matched for count, and ideally for time-of-day
distribution). Then compare each real combination's statistics against that null distribution.

This answers a question the current results cannot. Right now a PF of 0.746 has three very different
possible diagnoses:

1. Entries are **worse than random** → the signal is real but inverted. Investigate the inverse.
2. Entries are **indistinguishable from random** → the entry logic contributes nothing; all observed
   variation is bracket geometry and cost. Stop tuning this archetype.
3. Entries are **better than random but not by enough** → there is signal; costs are the binding
   constraint. Attack costs, hold time, or bracket size.

Note this is a *stronger* null than the M7 Monte Carlo as currently specced. Permuting an existing trade
sequence tests robustness of the equity path given those trades. A random-entry arm tests whether the
entry signal contributes anything at all. Both are worth having; this one is more informative and no
harder to build. I'd promote it ahead of M7 and above M8 entirely.

### 3.4 ATR-normalised brackets

His concrete rule: set targets slightly under half the size of recent average candles. He uses ATR with
**period 1** — which just reports each bar's own range — and internalises the typical range for the
session and timeframe he trades. Volatility up, brackets scale up; volatility down, brackets scale down.
For a mechanical version, ATR(n) on the working timeframe is the same quantity, averaged.

**Why this matters here more than it does for him.** A fixed tick-based stop optimised over 2021-12 →
2026-08 is fitted across enormous swings in NQ volatility. The optimiser is forced to return a value
that suits no single regime — and non-round optimised absolute values were already flagged as an
overfitting fingerprint in DeadCatBounce. Expressing stop and target as ATR multiples removes one
absolute-price parameter and replaces it with a scale-free one, which should be materially more stable
out of sample.

Concretely: replace fixed-tick stop/target fields in `DeadCatParams` with ATR-multiple fields, add ATR to
the precomputed indicator layer (TA-Lib `ATR`, or `NATR` if a percentage form is wanted), sweep the
multiplier. This composes with the existing round-number-avoidance rule — compute the ATR-derived level,
then apply the round-number offset.

**Cost floor — the caveat he never quantifies.** Friction is fixed per trade, so shrinking brackets in
quiet conditions raises the cost fraction non-linearly. Using my own MNQ assumptions ($0.74/RT commission,
1 tick slippage), for a 1:1 bracket:

| Bracket | Gross target | Break-even win rate |
|---|---|---|
| 2 pts | $4.00 | 71.8% |
| 4 pts | $8.00 | 60.9% |
| 6 pts | $12.00 | 57.2% |
| 10 pts | $20.00 | 54.4% |

His own published account ran 57.6%. Against a 4-point 1:1 MNQ bracket that is a *losing* system. So any
ATR-scaling rule needs a hard floor on minimum bracket size in dollar terms, below which the strategy sits
out — which is a codeable rule and a good one. NQ is broadly similar in proportional terms once slippage
is counted in ticks (both contracts share a 0.25 tick), so the dominant variable is bracket size in
points, not which contract is traded.

### 3.5 Prop-account constraints as the objective function

Scattered through the prop-firm guide, and directly relevant given the funded account:

- **Intraday trailing drawdown** trails the highest *unrealised* balance. It structurally punishes letting
  winners run and punishes leaving open profit on the table. He avoids firms that use it. If my firm does,
  the multi-leg staggered-target structure in DeadCatBounce interacts badly with it — every unrealised
  peak ratchets the threshold up. End-of-day trailing doesn't have this problem.
- **Consistency rules** (one day's profit capped at X% of total) penalise outlier days. A strategy whose
  P&L is concentrated in a few large days can be profitable and still unpayable.
- Framing evaluations as expenses and payouts as revenue, with pass rate and payout probability as
  modelled quantities rather than hopes.

**The concrete implication:** nqbt currently ranks by profit factor, expectancy, max drawdown — all
trade-level statistics. None of them is the objective I actually care about, which is *probability of
passing an evaluation and reaching payouts under a specific rule set.* A prop-account simulator is a pass
over the existing trade-by-trade output: replay the trade log with account start balance, trailing
threshold (intraday or EOD, toggleable), daily loss limit, profit target, and consistency ratio; report
pass rate, expected payouts, and failure mode. No changes to the `@njit` loop, no changes to the sweep.
It reranks the entire results table against the thing that actually pays.

This is probably the second-highest-value item after regime stratification, and it's the one no course
material covers at all.

### 3.6 Bar-type normalisation (interesting, but expensive — flag as Tier 2)

He manually swaps between 20/30/40-second charts until the ATR reads the candle size he wants — a hack to
hold bar volatility roughly constant as market speed changes. NinjaTrader does this structurally with
range, tick, or volume bars.

**Why not to rush at this.** The nqbt cache is minute bars, and the governing constraint of the whole tool
is fidelity parity with NT8's default behaviour. Constructing range or tick bars in Python from the tick
exports and matching NT8's construction *exactly* is genuinely fiddly — gap handling in particular — and
getting it subtly wrong breaks the Tier 1 / Tier 2 reconciliation that took real work to establish
(1143/1144 leg exits). The tick data is already cached and unused, so the raw material is there, but this
should be a deliberate, separately-validated project rather than a sweep axis.

Cheaper substitute that captures most of the benefit: ATR-normalised brackets (3.4) on existing minute
bars. Same goal — scale-free risk — without touching the bar construction.

---

## 4. What doesn't transfer

- **Hold times of seconds to a few minutes.** At MNQ bracket sizes that small, costs dominate — see the
  table in 3.4. His style survives partly because he is discretionary and skips most of the session.
- **Manual timeframe switching mid-session.** Not a rule; there's no stated criterion for when to switch.
- **"Take profits inside the range / stops outside it"** as literal geometry needs the range boundaries
  defined numerically before it means anything. He eyeballs them.
- **His anti-breakeven-stop position.** He argues against auto-breakeven in scalping because noise
  triggers it before the target. That's a claim about *his* bracket sizes on 20-second bars, not a
  general result. My own course material argues the opposite. This is exactly the kind of thing to settle
  with the sweep rather than by picking a side — it's already a toggleable axis.
- **Everything about which prop firm to use.** Affiliate-monetised. Read the mechanics (drawdown systems,
  consistency maths), ignore the rankings.
- **The "no indicators" stance.** He uses ATR only, and argues indicators reveal nothing not already in
  price. Philosophically fine, operationally irrelevant — an automated system needs *some* numeric
  encoding of price, and a moving average is one whether or not it's called an indicator.

---

## 5. Work items, in order

1. **Regime tagging + stratified stats.** Efficiency ratio in `conditions.py`; regime label onto each
   trade record; group `stats.summarise` by regime. Re-examine the existing 192 combinations through it
   before generating any new ones.
2. **Random-entry control arm.** Reuse the existing exit/bracket simulation with randomised entries.
   Compare real combinations against the null distribution. Promote ahead of M7 Monte Carlo.
3. **Prop-account simulator** over the existing trade log. Trailing threshold (both systems), daily loss
   limit, consistency ratio, profit target → pass rate and expected payout. Rerank by that.
4. **ATR-multiple brackets** replacing fixed-tick stop/target in `DeadCatParams`, with a hard dollar floor
   on minimum bracket size.
5. **Regime gate on entry** — only if (1) shows regime structure worth gating on.
6. Range/tick bar construction — deferred, and only as a separately validated piece of work.

Items 1–3 all operate on data that already exists and change what the current results *mean* rather than
generating more of them. Given that the current answer is "0 of 192 profitable", establishing *why* is
worth more than widening the grid.
