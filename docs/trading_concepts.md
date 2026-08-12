# Trading Concepts Reference

Working notes on the trading concepts this project draws on, and what happens to each one when it has
to become a fixed, backtestable rule.

Three parts, deliberately kept distinct because they are read differently:

- **Part I — Technical analysis catalogue.** Reference material, organised by topic. Look things up in
  it. Stable: it does not change as the project moves.
- **Part II — Concepts from discretionary intraday practice.** A sustained argument rather than a
  catalogue, organised by value to this project. Read it through.
- **Part III — Translation.** What is directly codeable, what is still a judgement call, and — the part
  that only exists because Parts I and II sit together — **where the two disagree, and how to settle
  it.**

Two conventions throughout. Platform-specific chart-setup material is deliberately absent; it is not
conceptual and does not apply to NinjaTrader. Where names are needed for entry archetypes or classifiers
they are generic labels chosen here, not standard terminology.

**Priorities live in [roadmap.md](roadmap.md), not here.** These notes say what an idea is and what it
would take to test it. What gets built in what order is the roadmap's job, and duplicating it here just
creates two answers that drift apart.

---

## Part I — Technical analysis catalogue

### Core principles

- **Goal is probability, not certainty.** No signal, pattern, or indicator combination guarantees an
  outcome — the aim is to stack multiple independent factors so the odds lean one way. Trading off a
  single signal with no plan is gambling, not trading.
- **Confirmation is required before acting on anything.** A single candle, single indicator reading,
  or single pattern is never sufficient alone — wait for a second, independent factor to align before
  treating a setup as valid.
- **Always establish the trend first.** Before applying any other tool, the first question is always
  "what is the trend doing right now" (higher highs/higher lows = uptrend, lower highs/lower lows =
  downtrend). Everything else is interpreted in that context.
- **Check trend across multiple timeframe layers, not just one.** Define short/medium/long-term trend
  separately (e.g., using different-period moving averages for each), and if a shorter-term signal
  disagrees with the longer-term picture, that disagreement itself is informative — it is a reason for
  lower confidence or no trade, not something to resolve by picking whichever layer supports the trade
  you want to take.
- **Support/resistance role reversal.** A broken resistance level tends to become new support, and a
  broken support level tends to become new resistance. This idea recurs constantly — in trendlines,
  moving averages, chart-pattern breakout levels, and Fibonacci levels alike.
- **Two foundational inputs: price action and volume.** Every other indicator (moving averages, MACD,
  RSI, Stochastics, CMF, MFI, Bollinger Bands) is a secondary, formula-derived layer built on top of
  those two. None of them is a "holy grail" — they are confirmation tools, not standalone systems.
- **Documentation/journaling matters.** Write down what you expect a setup to do, then review what
  actually happened. Core practice, not an optional extra.
- **Explicitly counting how many confluence criteria are met turns "confluence" into a usable dial.**
  Fix a checklist of independent yes/no criteria for a setup (e.g., five items: trend context, a
  consolidation period, volume expanding on the break, no nearby competing support/resistance, and a
  momentum-indicator reading) and treat the number of criteria satisfied — not just whether the setup
  "looks okay" — as the actual measure of conviction: all five in your favour is a strong setup, one or
  two is a trade that probably should not be taken. This is a directly codeable generalisation of
  "confirmation is required" — count satisfied conditions out of a fixed set, and gate (or size) the
  trade on that count rather than on a single pass/fail judgement.

### Candlesticks

Each candle encodes four prices: open, close, high, low.

- **Body** = the range between open and close. A larger body signals more conviction/force in that
  direction over the period.
- **Shadow/wick** = the range beyond the body (the high/low excursion). A longer shadow means more of a
  fight-back or reversal within the period; a short/absent shadow means one side controlled the whole
  period cleanly.

Three broad candle categories:

1. **Indecision** (e.g., doji — open and close nearly identical, tiny body). Signals uncertainty. A
   cluster of these forming together is a stronger indecision signal than one in isolation, especially
   after an extended directional run.
2. **Reversal** (hammer / hanging man — long shadow on one side, little-to-none on the other). The
   *same shape* means different things depending on what preceded it: appearing after a downtrend =
   potential bullish reversal (hammer); appearing after an uptrend = potential bearish reversal
   (hanging man). Location relative to the prior trend is what determines the read, not the shape alone.
3. **Authoritative/continuation** (large body, minimal shadow on both ends). Signals strong one-sided
   conviction; typically read as suggesting continuation in that direction.

A rule that applies throughout: a candle pattern needs confirmation from what follows (the next candle
continuing or validating the implied move) — never trade a single candle shape in isolation.

### Support & resistance / trendlines

- Support = a price zone where buying interest has previously shown up; resistance = a zone where
  selling interest has previously shown up. A breakout happens when buying demand overwhelms the supply
  sitting at a resistance level (or the reverse for a breakdown).
- **Trendline precision does not need to be exact.** When candle wicks disagree slightly on exactly
  where a line should sit, split the difference rather than obsessing over pixel-perfect placement —
  trendlines represent the general trend, not a precise mathematical boundary.
- **Stop-loss placement:** place stops *beyond* (not exactly at) a support/resistance level — e.g.,
  slightly below support for a long, slightly above resistance for a short — since price sitting exactly
  on the level is expected to get tested.
- Multiple layers of support/resistance can exist stacked above/below each other; a "full" breakout is
  not confirmed until price clears through the relevant layers, not just the first one.
- **Previous breakout points specifically** (not just previous highs/lows generally) are one of the more
  reliable go-to markers for where future support/resistance will show up — when scanning a chart for
  likely S/R zones, prior breakout levels are one of the first places to look.

### Indicators — general framework

- Indicators split roughly into two families:
  - **Trend/lagging indicators** (moving averages, MACD) — most useful when a market is actually
    trending; little value in sideways/range-bound conditions.
  - **Momentum/oscillators** (RSI, Stochastics, CMF, MFI) — used for overbought/oversold conditions and
    divergence.
- Avoid stacking multiple indicators from the same family (redundant signal, more chart clutter than
  insight); one from each family is sufficient.
- **Divergence** is the most consistently useful indicator signal across all of them:
  - *Positive divergence*: price makes a lower low, but the indicator makes a higher low (bullish
    warning).
  - *Negative divergence*: price makes a higher high, but the indicator makes a lower high (bearish
    warning).
  - Divergence is meaningful but never sufficient alone — it needs to line up with trend context,
    candlestick behaviour, and/or other confirmation before acting on it. MACD divergence carries more
    weight than RSI/Stochastics/CMF/MFI divergence.

#### Moving averages

- Shorter-period MA above longer-period MA = bullish structure (and the reverse for bearish); a
  crossover alone is a lagging clue, not a guaranteed signal.
- EMA reacts faster to recent price than SMA (more weight on recent bars).
- More MAs stacked in clean order = more confidence in trend strength, at the cost of more visual
  clutter.
- The support/resistance role-reversal rule applies to MAs too — once price reclaims a broken MA, that
  MA can act as new support (and vice versa).
- **Golden cross / reverse golden cross**: named events where a 50-period MA crosses above (golden
  cross, bullish) or below (reverse golden cross, bearish) a 200-period MA. This is a *confirmation*
  signal, not a leading indicator — since both MAs are built from past price, the cross confirms a trend
  already underway rather than predicting a new move. Common misconception worth stating explicitly: a
  golden cross does not mean a breakout or explosion is imminent.
- **Golden cross strength has three tiers**, based on the slope of the longer (200-period) MA at the
  moment of crossover: weakest when the 200-period is still flat/declining as the 50-period barely
  crosses it; moderate when the 200-period is flattening out sideways; strongest when the 200-period is
  already sloping in the same direction as the cross (both MAs trending together). The same logic
  applies in reverse for a bearish/reverse golden cross.

#### MACD

- Standard settings: 12/26 EMA for the MACD line, 9 EMA as the signal/trigger line.
- Bullish crossover = MACD line crosses above the signal line; bearish = crosses below.
- Zero-line crossover is a secondary bullish/bearish signal in its own right; a move that stays above
  zero throughout is healthier than one where the crossover happens below zero.
- Lagging by nature — not an overbought/oversold tool, it is a trend-momentum confirmation tool.
- **Variant use: the signal line itself (not the MACD line) crossing zero as a trend-stage gate.** In
  this formulation, signal-line-above-zero is a necessary gate for any bullish setup, checked *before*
  looking at anything else, and it tends to *lead* a longer moving-average crossover rather than lag it
  — useful as an early screening filter distinct from the standard MACD-line/signal-line crossover
  above. In the same formulation a live negative divergence does not override the gate: as long as the
  signal line holds above zero the setup stays valid despite the divergence, which illustrates that
  confluence factors can be deliberately weighted rather than treated as equally important.

#### Bollinger Bands

- Standard basis: 20-period.
- Used to gauge whether a trend is stretched and due to pause, not as an automatic reversal signal —
  price touching or piercing a band is a flag to watch, not an automatic trade trigger.
- A narrowing ("pinch") of the bands is watched as a setup for a potential volatility expansion.
- **Concrete overextension/complacency gauge**: how far price is trading beyond the outer band, combined
  with the count of same-direction candles over a recent lookback window (e.g., how many of the last 10
  candles closed in the trend's direction), used together as a rough proxy for how stretched and
  one-sided a move has become — the more one-sided and the further beyond the band, the more a
  mean-reversion setup is favoured. Both halves are simple, countable quantities.

#### RSI

- 0–100 scale. Extreme thresholds used here: below 15 = oversold/overextended, above 85 =
  overbought/overextended. These are adjustable rather than universal; a shorter period such as RSI(5)
  gives a faster read.
- 50-line crossover treated as a bullish/bearish momentum-shift signal.
- Divergence defined the same way as above, and weaker than MACD divergence.

#### Stochastics

- %K (recent close relative to high/low range) and %D (a short SMA of %K, acting as the signal line).
  Default period referenced: 14.
- Below 20 = oversold, above 80 = overbought. 50-line crossover and divergence concepts mirror RSI.
- Prone to whipsaws and false signals — treat with more caution than RSI or MACD.

#### Chaikin Money Flow (CMF)

- Volume-weighted, derived from an accumulation/distribution calculation.
- Used mainly for divergence detection; one of the less reliable indicators overall — a secondary
  confirmation tool, not a primary signal generator.

#### Money Flow Index (MFI)

- Volume-weighted version of RSI. Below 20 = oversold, above 80 = overbought.
- Also mainly useful for divergence, and more useful as a trade-management/confirmation tool once
  already in a position than as an entry trigger.

### Chart patterns — shared rules

These rules apply across every pattern type below:

- Always establish the prevailing trend first (same governing rule as everywhere else).
- Volume during pattern *formation* should be average-or-below (quiet, contracting).
- Volume on the actual *breakout/breakdown* should expand — bigger volume on the break = more confidence
  it is a real move, not a false breakout. This is a confidence booster rather than a strict
  requirement: price action is the primary signal, and a breakout without strong volume is not
  automatically invalidated.
- False breakouts are common; the pattern alone is never a guarantee — wait for follow-through (next
  candle, holding beyond the level, expanding volume) before trusting a break.
- **"True" vs "false" breakout is relative to your trading timeframe.** The same move can be a clean,
  valid breakout for a short-term trader while looking like a failed breakout to a longer-term trader
  watching the same chart — the pattern's outcome does not change, but which timeframe you are trading
  determines whether it counts as a win.
- **Measured-move price target**: measure the height/length of the initiating move and project that same
  distance from the breakout point. A rough rule of thumb, not a precise calculation.
- **Breakout retests ("back tests") are common across pattern types generally, not just triangles** —
  price often revisits the broken level shortly after any pattern breakout before continuing, which can
  serve as a secondary, lower-risk entry if the original breakout was missed.

#### Specific patterns

- **Pole pattern**: a sharp directional move (the pole) on above-average volume, followed by a
  lower-volume sideways pause, then continuation.
- **Wedge pattern**: converging trendlines; a rising wedge generally carries a bearish bias, a falling
  wedge a bullish bias. Volume should expand in the breakout direction.
- **Symmetrical triangle**: converging trendlines from both sides with no clear directional bias in the
  structure itself — breakout direction has to be confirmed by volume and price action rather than
  assumed from the pattern shape.
- **Channel**: two parallel trendlines (support and resistance sloped the same direction), defining a
  trending range; a break of either boundary signals a possible trend change.
- **Ascending triangle**: flat resistance + rising lows — generally bullish continuation bias.
- **Descending triangle**: flat support + falling highs — generally bearish continuation bias (mirror
  image of ascending triangle).

### Fibonacci

- **Retracements** (38.2%, 50%, 61.8% referenced): used to judge whether a pullback within an existing
  trend is "healthy", and as a reference for stop placement — e.g., entering near the 38.2% level with a
  stop just beyond the 50% level.
- **Extensions**: used to project potential target/resistance zones beyond a prior high, particularly
  useful when price moves into territory with no prior trading history to reference. Because there is no
  historical resistance to lean on in that situation, use tighter stops and be more willing to take
  profits quickly than usual.
- **Not** to be used alone — Fibonacci levels are one more confluence factor to combine with candlestick
  confirmation, trend context, and indicator readings, not a standalone signal.

### Trade plan structure & risk/reward framework

- **Every trade plan has exactly three numbers: entry, exit (target), and stop-loss.** They must be
  determined in that specific order — entry first, then exit, then stop-loss last. Working out the
  stop-loss before the exit is a specific self-deception risk: once you have seen a "minimum required
  exit" number, it unconsciously biases where you place the stop to make the maths work, rather than
  basing the stop purely on chart structure.
- **Minimum reward-to-risk ratio as a hard filter**: a baseline of at least 3:1 (reward at least 3× the
  amount risked), adjustable to personal risk tolerance. Mechanically: amount risked = entry − stop;
  minimum required reward = amount risked × the chosen ratio; minimum acceptable exit = entry + minimum
  required reward. If the realistic, chart-based exit does not clear that minimum, the plan fails the
  filter.
- **Only two levers may be used to fix a plan that fails the ratio test: lower the entry price, or use a
  different (still chart-logical) stop-loss location.** The exit/target must never be inflated just to
  force a passing ratio — this is the one form of self-deception that invalidates the entire process,
  since the target is supposed to be a realistic, chart-derived number, not a free variable.
- **Partial profit-taking / breakeven discipline**: once unrealised gain reaches an amount equal to what
  was originally risked, take partial profit (e.g., a third of the position) and/or move the stop to
  breakeven. From there, continue tightening the stop as new structural support forms with each
  subsequent bar — this simultaneously reduces risk and, once the stop passes breakeven, effectively
  locks in gains without needing to predict the ultimate exit. (Part II disputes this for very small
  brackets — see Part III.)
- **Two competing stop-loss philosophies, both valid, but pick one and apply it consistently**: a tight
  stop placed just beyond the nearest chart structure (lower risk per trade, higher chance of being
  stopped out on ordinary noise) versus a wider trailing stop referenced off a moving average (more room
  to breathe, larger risk per trade, fewer premature exits). A personal-risk-tolerance tradeoff, not a
  right/wrong question — the non-negotiable part is that some stop-loss is always in place and always
  honoured.
- **Set the stop-loss the instant a fill happens, not after.** With a moving-average-based trailing
  stop, the mechanic is: take the MA's most recently completed value and offset it by a small fixed
  cushion (e.g., MA at 10.50 → stop at 10.44) rather than placing the stop exactly on the MA value
  itself, since price sitting exactly on a reference level is expected to get tested.
- **Work out the stop-loss reference before the trigger even fires, not after.** Since the entry trigger
  and the stop-loss logic are usually independent (the trigger is about price/volume/indicator
  conditions; the stop is about the nearest support/resistance or MA value), there is no need to wait
  until you are filled to know where the stop will go — precomputing it during the watch/scan phase
  makes the "set the stop immediately on fill" rule above trivial to execute instead of a scramble.
- **Avoid placing stops at round numbers** (whole dollars, quarters, etc.) — these levels tend to cluster
  with other traders' orders and are more likely to get tested precisely because of that clustering.
- **Distinguish per-trade dollar risk from account/portfolio-level risk.** A trade can pass the
  reward-to-risk filter on its own numbers and still represent too large a bet relative to overall
  account size — the ratio test and the position-sizing/account-risk check are two separate questions,
  both required.
- **A stop-loss that gets hit as planned is not a failure — it is the plan working correctly.** The
  actual failure mode is not honouring the stop (rationalising "it'll come back" and holding anyway).
  This reframes discipline, not individual trade outcomes, as the real success metric.
- **Profit-taking aggressiveness is tied to trend alignment**, as a standing decision rule: if the trade
  goes *with* the larger trend context, a more moderate/patient profit-taking approach is reasonable. If
  the trade goes *against* the larger trend (e.g., a bullish setup inside a larger downtrend, or vice
  versa), take profits more aggressively and faster — counter-trend setups are more prone to failing
  quickly.
- **A strategy can be net profitable with a low win rate, provided losses are kept small through
  consistent stop-loss discipline.** A ~25% win rate can still work if losers are cut small and stops are
  honoured — win rate alone does not determine whether a system works; the loss side of the equation
  matters just as much. (Part II sharpens this considerably — see Part III.)

#### Entry archetypes

Four recurring entry patterns, each with a different risk posture:

- **Early-momentum-reversal entry**: bought as soon as a momentum indicator first turns bullish (e.g., a
  MACD signal-line zero-line cross) while the longer-term trend indicator (e.g., a 50-period MA) is
  still flat or only just levelling off — the earliest, riskiest point in a potential trend change,
  before the slower trend-following tools have confirmed anything. Higher chance of it being a false
  start (a "dead cat" that fails and resumes the prior trend) in exchange for the best entry price if it
  does turn into a real move. Meaningfully earlier and riskier than the pullback-in-uptrend entry below,
  which waits for the trend to already be established.
- **Pullback-in-uptrend entry**: after a prior breakout, buy into a short-term pullback that shows signs
  of exhaustion/weakness (the pullback itself is on declining volume) while the larger trend stays
  bullish. Typically the smallest, tightest-defined monetary risk of the four since the stop sits close
  to a nearby support/structure reference, and — being aligned with the larger trend — allows more
  patience on profit-taking.
- **Breakout-momentum entry**: bought as the move is actively breaking out, i.e., after confirmation
  rather than in anticipation. Carries more psychological risk (chasing strength) and calls for faster,
  more aggressive profit-taking, since momentum reversals tend to be sharp. Comes with a specific
  caution: do not buy too far past the actual breakout reference level. The farther price has already
  extended before entry, the more oversized the resulting stop-loss has to be to stay below that
  reference — a useful codeable check is capping the allowed distance between current price and the
  breakout level (in ticks or an ATR multiple) before treating an entry as too extended to take.
- **Pre-breakout speculative entry**: bought near a support level in anticipation of a move that has not
  started yet — no breakout or confirmation is required first. This deliberately trades a lower hit-rate
  (the move may never happen, or the entry may be too early and get stopped before it does) for a very
  tightly controlled, well-defined risk and a strongly asymmetric payout shape when it does work.

Pairing the first two archetypes with different partial-profit sizing follows directly from their risk
difference: the earlier/riskier entry uses a smaller first scale-out (e.g., a quarter of the position at
the first profit-lock point), while the later/more-established entry uses a larger first scale-out (e.g.,
half the position). The logic is that a more mature move has already proven itself and carries more
reversal risk from that point on, so there is more urgency to bank gains, whereas an early-stage entry is
given more room since the bulk of the move (if it happens) is still presumably ahead of it. That
risk-tiered sizing is a reusable idea independent of the specific indicators used to define "early" vs.
"established".

### Squeeze / trapped-position structural pattern (equity-specific — limited futures relevance)

A complete strategy can be built around identifying and trading short squeezes. Flagging this one
clearly: the core screening method rests on stock-borrow mechanics that do not exist for
exchange-traded futures, so most of it does not transfer — but the underlying structural idea is worth
keeping as a mental model.

- **The screening metrics are equity-specific and not usable for NQ.** Short interest, float, and "days
  to cover" (shares short ÷ average daily volume) all depend on data that only exists because shorting a
  stock means borrowing real shares from a lender who expects them back. Going short a futures contract
  involves no borrowing and no equivalent lender — there is no float, no short-interest data, and no
  margin-call-driven forced buyback for a futures short position the way there is for a stock. A typical
  baseline filter here is roughly "at least 5 days to cover, and at least 20% of the float sold short",
  and it has no futures equivalent; it should not be force-fitted onto one.
- **The transferable idea underneath it: a four-phase model of a trapped, one-sided position being forced
  to unwind.** (1) *Building* — a directional position accumulates for some reason (the reason itself
  does not matter to the strategy). (2) *Transition* — the move stalls or consolidates; both sides turn
  cautious, but there is no forced exit yet. (3) *Trigger* — some event causes the trapped side to start
  exiting. (4) *Cascade* — the forced exits become self-reinforcing (each exit pushes price further
  against the remaining trapped positions, forcing more exits), producing a fast, outsized move. This is
  a generic pattern for any scenario where a population of leveraged positions can be mechanically
  forced to close, not just equity short squeezes — but for futures the "why they are forced" mechanism
  would have to be something else entirely (e.g., a dense cluster of resting stop-losses at an obvious
  level), since there is no public, intraday-usable positioning dataset for futures equivalent to stock
  short-interest data.
- **The screening filter works better as a priority-sort than a strict requirement**, consistent with the
  same pattern seen elsewhere in these notes: setups lacking the "favourable environment" data are still
  watch-list candidates on unusual volume/price action alone, just ranked lower than ones with confirmed
  heavy positioning data behind them.
- The trade-execution mechanics that go with this setup (resistance-break entry with the same
  early-vs-confirmed tradeoff, support- or moving-average-based stop with a cushion, ratcheting the stop
  to each new candle's low, avoiding round-number stop placement) are the same mechanics already captured
  above, applied to a different setup-discovery method rather than representing new execution logic.

---

## Part II — Concepts from discretionary intraday practice

Concepts drawn from discretionary intraday futures practice, assessed for what they contribute to an
automated system. Unlike Part I this is an argument rather than a catalogue, and the section numbering
is stable because [roadmap.md](roadmap.md) cites it.

### 1. Scope, and how to read this part

The practice these ideas come from is **discretionary and manual**: 20–30 second charts, hold times
measured in seconds to minutes, one to a few contracts, and a trader who simply sits out most of the
session. Almost none of the *specifics* transfer to a systematic tool running on minute bars.

Several of the *framing devices*, however, are unusually good, and they attack problems this project
currently has open. That asymmetry is the whole reason this part exists, and it sets how to read it:

- **Take the framing, not the parameters.** A rule expressed as "targets slightly under half the recent
  average candle" is a scale-free idea wearing a discretionary costume. The idea survives automation;
  the eyeballed calibration does not.
- **Treat everything here as hypothesis, not validated edge.** None of it is independently verified, and
  self-reported discretionary results are not evidence about a mechanical system's expectancy. The value
  is in what these ideas suggest testing, and this project already has the machinery to test them.
- **Separate mechanics from recommendations.** Where the source material touches commercial territory —
  prop-firm rankings especially — the mechanics (how drawdown systems work, how consistency rules are
  calculated) are useful and the rankings are not. Any published ranking of prop firms is typically
  affiliate-monetised and carries a direct conflict of interest.

### 2. The argument against automating rule sets

This has to be dealt with first, because it is the strongest argument against the whole automation
premise and it is made frequently:

> If a pattern or system genuinely worked on its own, it could be coded into a NinjaScript strategy for
> free — and the result would be an unprofitable algorithm. Discretion is what makes a non-working
> system work. Anything sellable as a set of instructions is therefore worthless.

**Where it is right:** this is a good description of what happens when you automate publicly-taught
chart-pattern rules. It is also *exactly what nqbt has already measured* — 0 of 192 combinations of the
DeadCatBounce space clear a profit factor of 1.0 over 4.7 years once costs are applied, best PF 0.746.
The prediction and the measurement agree, which is worth taking seriously rather than explaining away.

**Where the argument overreaches:**

- It is unfalsifiable as stated, and the people who make it generally decline to run the experiment it
  implies.
- The headline example usually offered alongside it undercuts it. "People with real edges keep them
  private" is typically illustrated with Renaissance Technologies — a *purely systematic* fund. That is a
  counterexample to "codeable means worthless", not support for it.
- The defensible version of the claim is much narrower: **simple, widely-taught, publicly available rule
  sets do not survive transaction costs when automated.** That is a claim about the search space, not
  about automation.
- The argument contains its own rebuttal: *the only way to find out whether a pattern works is to code it
  and test it.* nqbt is that test. The reasoning recommends building it and then assumes the answer.

**How to hold this:** as a well-calibrated warning that the *category* of strategy currently being
tested — a handful of MA/VWAP gates on minute bars — is the category most likely to be already
arbitraged away. Not as a reason to stop. It argues for changing where the search happens, not for
abandoning the search.

### 3. What transfers — ranked by value to the project

#### 3.1 Regime-conditioned evaluation (highest value)

The central argument, and the most valuable idea here:

Any fixed rule set implicitly requires a particular market character. On days without that character it
does not merely fail to fire — it bleeds. So the real question is not "is this profitable" but "how often
do its conditions occur, and does its performance during those windows offset the guaranteed cost of the
windows where they don't?"

**Why this matters here specifically.** nqbt currently ranks combinations by aggregate profit factor
across the entire 1.65M-bar continuous series, 2021-12 → 2026-08. That aggregate is a weighted average
across wildly different regimes — 2022's trending selloff, 2023-24's grind, whatever 2025-26 was. A rule
set that is PF 1.4 in one regime and PF 0.4 in another shows up as PF ~0.75 and gets discarded. **The
current "nothing survives" finding cannot distinguish between "no edge anywhere" and "edge in a subset of
conditions, drowned by the rest."**

**Concrete change:** tag every bar with a regime label during `context.prepare`, carry the label onto each
trade record, and stratify `stats.summarise` by regime. Same sweep, same simulation, extra grouping
column. This is cheap — a precomputed 1D array plus a groupby — and it changes what the existing 192
combinations mean.

Second-order consequence: if a regime split does show structure, the natural next architecture is a
regime gate on entry rather than a new entry archetype. That is a single extra boolean in the condition
AND, not a new `@njit` function.

#### 3.2 Categorical price action as the regime classifier

The underlying strategy, reduced to its skeleton. Price action sits on a spectrum between two poles:

- **Consolidation** — expect price to stay within where it has recently been. Trade mean reversion: enter
  at the edges of the range, target *inside* the range, stop *outside* it. The high-probability loss is
  trying to time the break.
- **Direction** — expect price to reach new territory. Trade with momentum: target *outside* the recent
  range, stop *inside* it. The high-probability loss is fading it.
- **Third state: unclassifiable.** If it is too chaotic to categorise, do not trade. This is a distinct
  state, not a coin flip between the other two.

The stop/target *geometry inverts* between the two states. That is the actual content of the idea and it
is more specific than the usual "trend vs range" framing.

The stated failure mode is worth keeping: **a trade fails when the category changes while you are in it,**
not when you picked the wrong side. That is a coherent definition of trade invalidation and it maps onto
a stop rule.

**Codeable definitions to test** (none of these come from the source practice, which does it by eye):

| Classifier | Notes |
|---|---|
| Kaufman efficiency ratio: `abs(close[t]-close[t-n]) / sum(abs(diff(close)))` over n | Cleanest fit. Bounded 0–1. High = directional, low = consolidating. Not in TA-Lib, ~3 lines of numpy, fully vectorisable. |
| ADX | In TA-Lib. Familiar but laggier and less interpretable than ER. |
| Bollinger bandwidth, or rolling high−low range ÷ ATR | Cheap. Measures compression rather than direction. Connects directly to Part I's band "pinch". |
| Rolling realised-vol-of-ATR | The "is the ATR itself all over the place?" test — the unclassifiable state. Directly maps to a no-trade gate. |

Recommendation: implement efficiency ratio first, as a `conditions.py` 1D array with the lookback and the
two thresholds (direction-above, consolidation-below) as sweepable axes. The band between the thresholds
is the no-trade state, which gives the third category for free.

#### 3.3 A random-entry null model (the strongest idea here, and unbuilt)

The argument: without an edge, changing the reward-to-risk ratio changes nothing — a wider target just
lowers the win rate by exactly the amount that keeps expectancy flat. Therefore the break-even win rate
implied by a given R:R is an estimate of *the probability that trade actually reaches target*. A 1:50
bracket is not a clever asymmetry, it is a 98%-likely loss.

This is basically correct for a random-entry baseline, and it is directly relevant to a problem already
visible in this project's own trading history: roughly a 55% win rate with average losses more than
double average wins. The obvious fix is "widen targets, tighten stops until R:R clears 1". The point is
that if the entries carry no signal, that fix converts win rate downward and lands in the same place.
**R:R and win rate are not independent knobs.** The only thing that moves expectancy is an entry whose
*conditional* hit probability beats the break-even rate for the bracket geometry being used.

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

Note this is a *stronger* null than a Monte Carlo over the trade sequence. Permuting an existing trade
sequence tests robustness of the equity path given those trades. A random-entry arm tests whether the
entry signal contributes anything at all. Both are worth having; this one is more informative and no
harder to build.

#### 3.4 ATR-normalised brackets

The concrete rule: set targets slightly under half the size of recent average candles, using ATR with
**period 1** — which just reports each bar's own range — against an internalised sense of the typical
range for the session and timeframe being traded. Volatility up, brackets scale up; volatility down,
brackets scale down. For a mechanical version, ATR(n) on the working timeframe is the same quantity,
averaged.

**Why this matters more in an automated context.** A fixed tick-based stop optimised over 2021-12 →
2026-08 is fitted across enormous swings in NQ volatility. The optimiser is forced to return a value that
suits no single regime — and non-round optimised absolute values were already flagged as an overfitting
fingerprint in DeadCatBounce. Expressing stop and target as ATR multiples removes one absolute-price
parameter and replaces it with a scale-free one, which should be materially more stable out of sample.

Concretely: replace fixed-tick stop/target fields in `DeadCatParams` with ATR-multiple fields, add ATR to
the precomputed indicator layer, sweep the multiplier. This composes with the existing
round-number-avoidance rule — compute the ATR-derived level, then apply the round-number offset. Note
that ATR must be NT8-parity rather than TA-Lib's, for the same seeding reason the moving averages needed
hand-rolling.

**Cost floor — the caveat the rule never quantifies.** Friction is fixed per trade, so shrinking brackets
in quiet conditions raises the cost fraction non-linearly. Using this project's MNQ assumptions
($0.74/RT commission, 1 tick slippage), for a 1:1 bracket:

| Bracket | Gross target | Break-even win rate |
|---|---|---|
| 2 pts | $4.00 | 71.8% |
| 4 pts | $8.00 | 60.9% |
| 6 pts | $12.00 | 57.2% |
| 10 pts | $20.00 | 54.4% |

A 57–58% win rate is a realistic figure for a well-run discretionary scalping approach, and against a
4-point 1:1 MNQ bracket it is a *losing* system. So any ATR-scaling rule needs a hard floor on minimum
bracket size in dollar terms, below which the strategy sits out — which is a codeable rule and a good
one. NQ is broadly similar in proportional terms once slippage is counted in ticks (both contracts share
a 0.25 tick), so the dominant variable is bracket size in points, not which contract is traded.

#### 3.5 Prop-account constraints as the objective function

Directly relevant to any funded-account context:

- **Intraday trailing drawdown** trails the highest *unrealised* balance. It structurally punishes letting
  winners run and punishes leaving open profit on the table. Worth avoiding where the choice exists.
  Where it applies, the multi-leg staggered-target structure in DeadCatBounce interacts badly with it —
  every unrealised peak ratchets the threshold up. End-of-day trailing does not have this problem.
- **Consistency rules** (one day's profit capped at X% of total) penalise outlier days. A strategy whose
  P&L is concentrated in a few large days can be profitable and still unpayable.
- **Flat before the session close** is a hard requirement, not a preference. It is already implemented in
  the simulation and is a genuine constraint on strategy design; the roadmap's "Flat before the session
  close" section carries the consequences.
- Framing evaluations as expenses and payouts as revenue, with pass rate and payout probability as
  modelled quantities rather than hopes.

**The concrete implication:** nqbt currently ranks by profit factor, expectancy, max drawdown — all
trade-level statistics. None of them is the objective that actually matters, which is *probability of
passing an evaluation and reaching payouts under a specific rule set.* A prop-account simulator is a pass
over the existing trade-by-trade output: replay the trade log with account start balance, trailing
threshold (intraday or EOD, toggleable), daily loss limit, profit target, and consistency ratio; report
pass rate, expected payouts, and failure mode. No changes to the `@njit` loop, no changes to the sweep.
It reranks the entire results table against the thing that actually pays.

This is probably the second-highest-value item after regime stratification, and it is the one Part I does
not cover at all.

#### 3.6 Bar-type normalisation (interesting, but expensive)

The manual version swaps between 20/30/40-second charts until ATR reads the candle size wanted — a hack
to hold bar volatility roughly constant as market speed changes. NinjaTrader does this structurally with
range, tick, or volume bars.

**Why not to rush at this.** The nqbt cache is minute bars, and the governing constraint of the whole tool
is fidelity parity with NT8's default behaviour. Constructing range or tick bars in Python from the tick
exports and matching NT8's construction *exactly* is genuinely fiddly — gap handling in particular — and
getting it subtly wrong breaks the Tier 1 / Tier 2 reconciliation that took real work to establish
(1143/1144 leg exits). The tick data is already cached and unused, so the raw material is there, but this
should be a deliberate, separately-validated project rather than a sweep axis.

Cheaper substitute that captures most of the benefit: ATR-normalised brackets (3.4) on existing minute
bars. Same goal — scale-free risk — without touching the bar construction.

### 4. What doesn't transfer

- **Hold times of seconds to a few minutes.** At MNQ bracket sizes that small, costs dominate — see the
  table in 3.4. The discretionary version survives partly by skipping most of the session, which a
  mechanical system running continuously does not.
- **Manual timeframe switching mid-session.** Not a rule; there is no stated criterion for when to switch.
- **"Take profits inside the range / stops outside it"** as literal geometry needs the range boundaries
  defined numerically before it means anything. The source practice eyeballs them.
- **Firm-specific recommendations.** Read the mechanics (drawdown systems, consistency maths); ignore any
  ranking of which firm to use.
- **The "no indicators" stance.** The source practice uses ATR only, and argues indicators reveal nothing
  not already in price. See Part III for why this mostly dissolves for an automated system, and for the
  narrower version of it that survives.

### 5. What this part suggests building

Not a priority list — [roadmap.md](roadmap.md) owns ordering, and duplicating it here would just create a
second answer that drifts. The ideas that turn into work:

regime tagging and stratified statistics (3.1); the efficiency-ratio classifier (3.2); a random-entry
control arm (3.3); ATR-multiple brackets with a hard dollar floor (3.4); a prop-account simulator over
the existing trade log (3.5); and, deferred, range/tick bar construction (3.6).

The common thread across the first three is worth stating: they **operate on data that already exists and
change what the current results mean, rather than generating more of them.** Given that the current answer
is "0 of 192 profitable", establishing *why* is worth more than widening the grid.

---

## Part III — Translation: from concept to backtestable rule

### Directly codeable as a fixed rule

Useful starting points for NinjaScript conditions and for `conditions.py`:

Candlestick body/shadow ratios; MA order/crossover checks including golden-cross/reverse-golden-cross with
slope-based strength tiers; MACD line vs. signal line and zero-line position (including a
signal-line-only zero-cross gate as an earlier/alternate trigger); RSI/Stochastic threshold levels and
50-line crosses; S/R role-reversal checks; volume-relative-to-average comparisons; measured-move target
projection; the reward-to-risk ratio filter (entry/exit/stop → minimum acceptable exit check);
round-number stop avoidance; breakeven/partial-profit triggers once unrealised gain equals initial risk;
risk-tiered scale-out sizing (smaller first scale-out for earlier/riskier entries, larger for
later/more-established ones); an explicit multi-criteria checklist score (count satisfied conditions out
of a fixed set rather than a single pass/fail judgement); and a consecutive-same-direction-candle count
combined with distance beyond a Bollinger Band as an overextension gauge.

From Part II, additionally: the Kaufman efficiency ratio as a regime label with sweepable thresholds;
ATR-multiple stops and targets with a hard dollar floor; a regime gate on entry; a random-entry null
model; and a prop-account rule replay over the trade log.

### Still a judgement call

Would need a concrete numeric definition before it could be automated:

"Split the difference" trendline placement; pattern-recognition steps described visually (triangle /
wedge / channel shapes) rather than with hard coordinates; the choice between a tight structural stop and
a wider moving-average trailing stop (fine as personal preference, but an automated system needs one
fixed, consistent rule); the "too extended past the breakout" check for momentum-style entries (needs a
concrete tick or ATR-multiple cutoff rather than an eyeballed judgement); exactly how much more
"aggressive" counter-trend profit-taking should mean (e.g., a smaller R-multiple target or a larger
scale-out percentage); the range boundaries that Part II's consolidation geometry depends on; and any
criterion for switching timeframe mid-session.

**Volume-based tools need reinterpretation for futures.** CMF, MFI, and any volume-confirmation rule in
Part I were built around single equity listings. Futures volume is still meaningful, but
continuous-contract construction, contract rollovers, and the RTH/Globex session split all shape volume
differently than a single stock ticker does — treat volume thresholds and comparisons as needing
recalibration to instrument and session window, not a direct copy-over.

### Where Parts I and II disagree

Four genuine conflicts. None resolves by picking a side, and all four are testable — which is the point
of having both parts in one document.

**Breakeven stops.** Part I moves the stop to breakeven once unrealised gain equals initial risk. Part II
argues auto-breakeven is actively harmful because noise triggers it before the target is reached. The
disagreement dissolves once bracket size is held fixed: Part II's claim is about very small brackets on
20-second bars, where the noise band is a large fraction of the target, and Part I's is about brackets
several times larger. The synthesis is that the breakeven trigger should be expressed **relative to
typical bar range rather than as a fixed policy** — an ATR-relative rule. It is already a toggleable
axis, so sweep it rather than choosing.

**Win rate versus reward-to-risk.** Part I says a ~25% win rate can be net profitable provided losses are
cut small. Part II says R:R and win rate are not independent knobs, because widening the target lowers
the hit rate by roughly enough to keep expectancy flat. Both are correct and they answer different
questions. Part I is about **loss discipline** — whether the stop is honoured — which is a behavioural
variable and genuinely free. Part II is about **bracket geometry**, which is not free and cannot
manufacture expectancy on its own. The combined statement is the one that matters here: a low win rate is
survivable, but only if the entry carries conditional edge; without one, widening the bracket relocates
the same negative expectancy rather than fixing it. This is exactly what the random-entry arm (3.3) is
built to measure.

**Fixed ratios versus scale-free brackets.** Part I sets a 3:1 minimum reward-to-risk as a hard filter.
Part II wants stops and targets as ATR multiples so they track volatility. These compose rather than
compete — a ratio is dimensionless and survives any scaling — but the **order of operations matters**:
derive the ATR-scaled stop first, then apply the ratio test, then apply round-number avoidance. Testing
the ratio against a fixed tick stop reintroduces exactly the absolute-price parameter that ATR scaling
exists to remove.

**Whether indicators earn their place.** Part I is indicator-dense. Part II holds that indicators reveal
nothing not already present in price and uses ATR alone. For an automated system this mostly dissolves:
any mechanical rule needs *some* numeric encoding of price, and a moving average is one whether or not it
is called an indicator. What survives is narrower and worth keeping — **indicators derived from the same
input are not independent confirmation.** Stacking three oscillators is one signal counted three times,
which is the same error the roadmap's volume decomposition warns about, and Part I's own "avoid stacking
multiple indicators from the same family" already half-concedes it.

**One structural tension underneath all four.** Part I organises around named setups; Part II argues that
what actually matters is market character, and that a fixed rule set bleeds whenever the character is
absent. If Part II is right, Part I's catalogue is not wrong but is **incomplete in a specific way**:
every pattern in it implicitly assumes a regime, and none of them says which. That converts into a
concrete research instruction rather than a philosophical position — when testing any Part I pattern,
stratify by the Part II regime label before concluding it does not work.
