# Technical Analysis Concept Reference

Synthesized notes from a purchased technical analysis training course: a 27-lesson core course (candlesticks, trend, support/resistance, indicators, chart patterns, Fibonacci), a supplementary "skill sharpening" drill series (candlesticks, chart patterns, support/resistance, trend identification — no indicators or Fibonacci in this part), a course on risk/reward-based trade planning with three entry-strategy archetypes, a fourth course built around one complete named strategy (a momentum/trend-stage classification system with its own step-by-step entry and trade-management process), a fifth course built around identifying and trading short squeezes, and a sixth course covering five named short-selling strategies built on standard technical analysis (unlike the short-squeeze course, this one's mechanics are generic and transfer to futures fine). This is a condensed, reworded summary of the underlying concepts for personal reference — not a transcript. Platform-setup content specific to the original courses' charting software has been dropped since it doesn't apply to NinjaTrader. Points sourced from the drill series are the more specific/refined ones below (golden cross detail, trend-aligned profit-taking, breakout-timeframe nuance, etc.) — it was otherwise mostly repeated application of the core course's rules on new chart examples, so it isn't reflected line-for-line here. The strategy/entry-archetype names below are my own generic labels, not the courses' original branded names.

## Core Philosophy & Process

- **Goal is probability, not certainty.** No signal, pattern, or indicator combination guarantees an outcome — the aim is to stack multiple independent factors so the odds lean one way. Trading off a single signal with no plan is explicitly framed as gambling.
- **Confirmation is required before acting on anything.** A single candle, single indicator reading, or single pattern is never sufficient alone — wait for a second, independent factor to align before treating a setup as valid.
- **Always establish the trend first.** Before applying any other tool, the first question is always "what is the trend doing right now" (higher highs/higher lows = uptrend, lower highs/lower lows = downtrend). Everything else is interpreted in that context.
- **Check trend across multiple timeframe layers, not just one.** Define short/medium/long-term trend separately (e.g., using different-period moving averages for each), and if a shorter-term signal disagrees with the longer-term picture, that disagreement itself is informative — it's a reason for lower confidence or no trade, not something to resolve by picking whichever layer supports the trade you want to take.
- **Support/resistance role reversal.** A broken resistance level tends to become new support, and a broken support level tends to become new resistance. This idea recurs constantly — in trendlines, moving averages, chart-pattern breakout levels, and Fibonacci levels alike.
- **Two foundational inputs: price action and volume.** Every other indicator (moving averages, MACD, RSI, Stochastics, CMF, MFI, Bollinger Bands) is a secondary, formula-derived layer built on top of those two. None of them is a "holy grail" — they're confirmation tools, not standalone systems.
- **Documentation/journaling matters.** Write down what you expect a setup to do, then review what actually happened. This is treated as core practice, not an optional extra.
- **Explicitly counting how many confluence criteria are met turns "confluence" into a usable dial.** One system defines a fixed checklist of independent yes/no criteria for a setup (e.g., five items: trend context, a consolidation period, volume expanding on the break, no nearby competing support/resistance, and a momentum-indicator reading) and treats the number of criteria satisfied — not just whether the setup "looks okay" — as the actual measure of conviction: all five in your favor is a strong setup, one or two is a trade that probably shouldn't be taken. This is a directly codeable generalization of "confirmation is required" — count satisfied conditions out of a fixed set, and gate (or size) the trade on that count rather than on a single pass/fail judgment.

## Candlesticks

Each candle encodes four prices: open, close, high, low.

- **Body** = the range between open and close. A larger body signals more conviction/force in that direction over the period.
- **Shadow/wick** = the range beyond the body (the high/low excursion). A longer shadow means more of a fight-back or reversal within the period; a short/absent shadow means one side controlled the whole period cleanly.

Three broad candle categories:
1. **Indecision** (e.g., doji — open and close nearly identical, tiny body). Signals uncertainty. A cluster of these forming together is a stronger indecision signal than one in isolation, especially after an extended directional run.
2. **Reversal** (hammer / hanging man — long shadow on one side, little-to-none on the other). The *same shape* means different things depending on what preceded it: appearing after a downtrend = potential bullish reversal (hammer); appearing after an uptrend = potential bearish reversal (hanging man). Location relative to the prior trend is what determines the read, not the shape alone.
3. **Authoritative/continuation** (large body, minimal shadow on both ends). Signals strong one-sided conviction; typically read as suggesting continuation in that direction.

Rule that repeats throughout: a candle pattern needs confirmation from what follows (the next candle continuing or validating the implied move) — never trade a single candle shape in isolation.

## Support & Resistance / Trendlines

- Support = a price zone where buying interest has previously shown up; resistance = a zone where selling interest has previously shown up. A breakout happens when buying demand overwhelms the supply sitting at a resistance level (or the reverse for a breakdown).
- **Trendline precision doesn't need to be exact.** When candle wicks disagree slightly on exactly where a line should sit, split the difference rather than obsessing over pixel-perfect placement — trendlines represent the general trend, not a precise mathematical boundary.
- **Stop-loss placement:** place stops *beyond* (not exactly at) a support/resistance level — e.g., slightly below support for a long, slightly above resistance for a short — since price sitting exactly on the level is expected to get tested.
- Multiple layers of support/resistance can exist stacked above/below each other; a "full" breakout isn't confirmed until price clears through the relevant layers, not just the first one.
- **Previous breakout points specifically** (not just previous highs/lows generally) are called out as one of the more reliable go-to markers for where future support/resistance will show up — when scanning a chart for likely S/R zones, prior breakout levels are one of the first places to look.

## Indicators — General Framework

- Indicators split roughly into two families:
  - **Trend/lagging indicators** (moving averages, MACD) — most useful when a market is actually trending; explicitly described as having little value in sideways/range-bound conditions.
  - **Momentum/oscillators** (RSI, Stochastics, CMF, MFI) — used for overbought/oversold conditions and divergence.
- Avoid stacking multiple indicators from the same family (redundant signal, more chart clutter than insight); one from each family is treated as sufficient.
- **Divergence** is the most consistently emphasized indicator signal across all of them:
  - *Positive divergence*: price makes a lower low, but the indicator makes a higher low (bullish warning).
  - *Negative divergence*: price makes a higher high, but the indicator makes a lower high (bearish warning).
  - Divergence is repeatedly flagged as meaningful but never sufficient alone — it needs to line up with trend context, candlestick behavior, and/or other confirmation before acting on it. MACD divergence is treated as carrying more weight than RSI/Stochastics/CMF/MFI divergence.

### Moving Averages
- Shorter-period MA above longer-period MA = bullish structure (and the reverse for bearish); a crossover alone is a lagging clue, not a guaranteed signal.
- EMA reacts faster to recent price than SMA (more weight on recent bars).
- More MAs stacked in clean order = more confidence in trend strength, at the cost of more visual clutter.
- The support/resistance role-reversal rule applies to MAs too — once price reclaims a broken MA, that MA can act as new support (and vice versa).
- **Golden cross / reverse golden cross**: named events where a 50-period MA crosses above (golden cross, bullish) or below (reverse golden cross, bearish) a 200-period MA. Explicitly flagged as a *confirmation* signal, not a leading indicator — since both MAs are built from past price, the cross confirms a trend that's already underway rather than predicting a new move. A common misconception the course pushes back on directly: a golden cross does not mean a breakout/explosion is imminent.
- **Golden cross strength has three tiers**, based on the slope of the longer (200-period) MA at the moment of crossover: weakest when the 200-period is still flat/declining as the 50-period barely crosses it; moderate when the 200-period is flattening out sideways; strongest when the 200-period is already sloping in the same direction as the cross (both MAs trending together). Same logic applies in reverse for a bearish/reverse golden cross.

### MACD
- Standard settings: 12/26 EMA for the MACD line, 9 EMA as the signal/trigger line.
- Bullish crossover = MACD line crosses above the signal line; bearish = crosses below.
- Zero-line crossover is a secondary bullish/bearish signal in its own right; a move that stays above zero throughout is read as healthier than one where the crossover happens below zero.
- Lagging by nature — not an overbought/oversold tool, it's a trend-momentum confirmation tool.
- **Variant use: the signal line itself (not the MACD line) crossing zero as a trend-stage gate.** One system built entirely around this: signal-line-above-zero is treated as a necessary gate for any bullish setup, checked *before* looking at anything else, and is explicitly treated as tending to lead a longer moving-average crossover rather than lag it — useful as an early screening filter distinct from the standard MACD-line/signal-line crossover described above. In that same system, a live negative divergence did not override the gate — as long as the signal line held above zero, the setup stayed valid despite the divergence, illustrating that confluence factors can be deliberately weighted rather than treated as equally important.

### Bollinger Bands
- Standard basis: 20-period.
- Used to gauge whether a trend is stretched and due to pause, not as an automatic reversal signal — price touching or piercing a band is a flag to watch, not an automatic trade trigger.
- A narrowing ("pinch") of the bands is watched as a setup for a potential volatility expansion.
- **Concrete overextension/complacency gauge**: how far price is trading beyond the outer band, combined with the count of same-direction candles over a recent lookback window (e.g., how many of the last 10 candles closed in the trend's direction), used together as a rough proxy for how stretched and one-sided a move has become — the more one-sided and the further beyond the band, the more a mean-reversion setup is favored. Both halves are simple, countable quantities.

### RSI
- 0–100 scale. Course's stated extreme thresholds: below 15 = oversold/overextended, above 85 = overbought/overextended (explicitly noted as adjustable/personal preference, not universal — a shorter period like RSI(5) was the instructor's personal preference for a faster read).
- 50-line crossover treated as a bullish/bearish momentum-shift signal.
- Divergence defined the same way as above, explicitly weighted as less powerful than MACD divergence.

### Stochastics
- %K (recent close relative to high/low range) and %D (a short SMA of %K, acting as the signal line). Default period referenced: 14.
- Below 20 = oversold, above 80 = overbought. 50-line crossover and divergence concepts mirror RSI.
- Explicitly flagged as prone to whipsaws/false signals — treated with more caution than RSI or MACD.

### Chaikin Money Flow (CMF)
- Volume-weighted, derived from an accumulation/distribution calculation.
- Used mainly for divergence detection; treated in the source material as one of the less reliable indicators overall — a secondary confirmation tool, not a primary signal generator.

### Money Flow Index (MFI)
- Volume-weighted version of RSI. Below 20 = oversold, above 80 = overbought.
- Also emphasized mainly for divergence; recommended more as a trade-management/confirmation tool once already in a position, rather than an entry trigger.

## Chart Patterns — Shared Rules

These rules repeat across every pattern type below:
- Always establish the prevailing trend first (same governing rule as everywhere else).
- Volume during pattern *formation* should be average-or-below (quiet, contracting).
- Volume on the actual *breakout/breakdown* should expand — bigger volume on the break = more confidence it's a real move, not a false breakout. That said, this is a confidence booster, not a strict requirement: price action is treated as the primary signal, and a breakout without strong volume isn't automatically invalidated.
- False breakouts are explicitly acknowledged as common; the pattern alone is never a guarantee — wait for follow-through (next candle, holding beyond the level, expanding volume) before trusting a break.
- **"True" vs "false" breakout is relative to your trading timeframe.** The same move can be a clean, valid breakout for a short-term trader while looking like a failed/false breakout to a longer-term trader watching the same chart — the pattern's outcome doesn't change, but which timeframe you're trading determines whether it counts as a win.
- **Measured-move price target**: measure the height/length of the initiating move and project that same distance from the breakout point — explicitly called a rough rule of thumb, not a precise calculation.
- **Breakout retests ("back tests") are common across pattern types generally, not just triangles** — price often revisits the broken level shortly after any pattern breakout before continuing, which can serve as a secondary, lower-risk entry if the original breakout was missed.

### Specific patterns
- **Pole pattern**: a sharp directional move (the pole) on above-average volume, followed by a lower-volume sideways pause, then continuation.
- **Wedge pattern**: converging trendlines; a rising wedge generally carries a bearish bias, a falling wedge a bullish bias. Volume should expand in the breakout direction.
- **Symmetrical triangle**: converging trendlines from both sides with no clear directional bias in the structure itself — breakout direction has to be confirmed by volume and price action rather than assumed from the pattern shape.
- **Channel**: two parallel trendlines (support and resistance sloped the same direction), defining a trending range; a break of either boundary signals a possible trend change.
- **Ascending triangle**: flat resistance + rising lows — generally bullish continuation bias.
- **Descending triangle**: flat support + falling highs — generally bearish continuation bias (mirror image of ascending triangle).

## Fibonacci

- **Retracements** (38.2%, 50%, 61.8% referenced): used to judge whether a pullback within an existing trend is "healthy," and as a reference for stop placement — e.g., entering near the 38.2% level with a stop just beyond the 50% level.
- **Extensions**: used to project potential target/resistance zones beyond a prior high, particularly useful when price moves into territory with no prior trading history to reference. Because there's no historical resistance to lean on in that situation, the source material stresses using tighter stops and being more willing to take profits quickly than usual.
- Explicitly **not** meant to be used alone — Fibonacci levels are treated as one more confluence factor to combine with candlestick confirmation, trend context, and indicator readings, not a standalone signal.

## Trade Plan Structure & Risk/Reward Framework

- **Every trade plan has exactly three numbers: entry, exit (target), and stop-loss.** They must be determined in that specific order — entry first, then exit, then stop-loss last. Working out the stop-loss before the exit is flagged as a specific self-deception risk: once you've seen a "minimum required exit" number, it unconsciously biases where you place the stop to make the math work, rather than basing the stop purely on chart structure.
- **Minimum reward-to-risk ratio as a hard filter**: a baseline of at least 3:1 (reward at least 3× the amount risked) is suggested, adjustable to personal risk tolerance. Mechanically: amount risked = entry − stop; minimum required reward = amount risked × the chosen ratio; minimum acceptable exit = entry + minimum required reward. If the realistic, chart-based exit doesn't clear that minimum, the plan fails the filter.
- **Only two levers may be used to fix a plan that fails the ratio test: lower the entry price, or use a different (still chart-logical) stop-loss location.** The exit/target must never be inflated just to force a passing ratio — that's treated as the one form of self-deception that invalidates the entire process, since the target is supposed to be a realistic, chart-derived number, not a free variable.
- **Partial profit-taking / breakeven discipline**: once unrealized gain reaches an amount equal to what was originally risked, a common rule is to take partial profit (e.g., a third of the position) and/or move the stop to breakeven. From there, continue tightening the stop as new structural support forms with each subsequent bar — this simultaneously reduces risk and, once the stop passes breakeven, effectively locks in gains without needing to predict the ultimate exit.
- **Two competing stop-loss philosophies, both valid, but pick one and apply it consistently**: a tight stop placed just beyond the nearest chart structure (lower risk per trade, higher chance of being stopped out on ordinary noise) versus a wider trailing stop referenced off a moving average (more room to breathe, larger risk per trade, fewer premature exits). Framed as a personal-risk-tolerance tradeoff, not a right/wrong question — the non-negotiable part is that some stop-loss is always in place and always honored.
- **Set the stop-loss the instant a fill happens, not after.** With a moving-average-based trailing stop, the mechanic is: take the MA's most recently completed value and offset it by a small fixed cushion (e.g., MA at 10.50 → stop at 10.44) rather than placing the stop exactly on the MA value itself, since price sitting exactly on a reference level is expected to get tested.
- **Work out the stop-loss reference before the trigger even fires, not after.** Since the entry trigger and the stop-loss logic are usually independent (the trigger is about price/volume/indicator conditions; the stop is about the nearest support/resistance or MA value), there's no need to wait until you're filled to know where the stop will go — precomputing it during the watch/scan phase means the "set the stop immediately on fill" rule above is trivial to execute instead of a scramble.
- **Avoid placing stops at round numbers** (whole dollars, quarters, etc.) — these levels tend to cluster with other traders' orders and are more likely to get tested precisely because of that clustering.
- **Distinguish per-trade dollar risk from account/portfolio-level risk.** A trade can pass the reward-to-risk filter on its own numbers and still represent too large a bet relative to overall account size — the ratio test and the position-sizing/account-risk check are two separate questions, both required.
- **A stop-loss that gets hit as planned is not a failure — it's the plan working correctly.** The actual failure mode is not honoring the stop (rationalizing "it'll come back" and holding anyway). This reframes discipline, not individual trade outcomes, as the real success metric.
- **Profit-taking aggressiveness is tied to trend alignment, drilled repeatedly as a standing decision rule**: if the trade goes *with* the larger trend context, a more moderate/patient profit-taking approach is reasonable. If the trade goes *against* the larger trend (e.g., a bullish setup inside a larger downtrend, or vice versa), take profits more aggressively and faster — counter-trend setups are explicitly treated as more prone to failing quickly.
- **A strategy can be net profitable with a low win rate, provided losses are kept small through consistent stop-loss discipline.** The material uses a ~25% win rate example that still worked because losers were cut small and stops were honored — the point being that win rate alone doesn't determine whether a system works; the loss side of the equation matters just as much.

### Entry archetypes
Four recurring entry patterns, each with a different risk posture:

- **Early-momentum-reversal entry**: bought as soon as a momentum indicator first turns bullish (e.g., a MACD signal-line zero-line cross) while the longer-term trend indicator (e.g., a 50-period MA) is still flat or only just leveling off — the earliest, riskiest point in a potential trend change, before the slower trend-following tools have confirmed anything. Higher chance of it being a false start (a "dead cat" that fails and resumes the prior trend) in exchange for the best entry price if it does turn into a real move. This is meaningfully earlier and riskier than the pullback-in-uptrend entry below, which waits for the trend to already be established.
- **Pullback-in-uptrend entry**: after a prior breakout, buy into a short-term pullback that shows signs of exhaustion/weakness (the pullback itself is on declining volume) while the larger trend stays bullish. Typically the smallest, tightest-defined monetary risk of the three since the stop sits close to a nearby support/structure reference, and — being aligned with the larger trend — allows more patience on profit-taking.
- **Breakout-momentum entry**: bought as the move is actively breaking out, i.e., after confirmation rather than in anticipation. Carries more psychological risk (chasing strength) and calls for faster, more aggressive profit-taking, since momentum reversals tend to be sharp. Comes with a specific caution: don't buy too far past the actual breakout reference level. The farther price has already extended before entry, the more oversized the resulting stop-loss has to be to stay below that reference — a useful codeable check is capping the allowed distance between current price and the breakout level (in ticks or an ATR multiple) before treating an entry as too extended to take.
- **Pre-breakout speculative entry**: bought near a support level in anticipation of a move that hasn't started yet — no breakout or confirmation is required first. This deliberately trades a lower hit-rate (the move may never happen, or the entry may be too early and get stopped before it does) for a very tightly controlled, well-defined risk and a strongly asymmetric payout shape when it does work.

One system pairs the first two archetypes with different partial-profit-taking sizing precisely because of their risk difference: the earlier/riskier entry uses a smaller first scale-out (e.g., a quarter of the position at the first profit-lock point), while the later/more-established entry uses a larger first scale-out (e.g., half the position) — the logic being that a more mature move has already proven itself and carries more reversal risk from that point on, so more urgency to bank gains, whereas an early-stage entry is given more room since the bulk of the move (if it happens) is still presumably ahead of it. That risk-tiered sizing is a reusable idea independent of the specific indicators used to define "early" vs. "established."

## Short-Squeeze Structural Pattern (Stock-Specific — Limited Futures Relevance)

A fifth course built an entire strategy around identifying and exploiting short squeezes. Flagging this one clearly: its core screening method is built on stock-borrow mechanics that don't exist for exchange-traded futures, so most of it doesn't transfer — but the underlying structural idea is worth keeping as a mental model.

- **The screening metrics are equity-specific and not usable for NQ.** Short interest, float, and "days to cover" (shares short ÷ average daily volume) all depend on data that only exists because shorting a stock means borrowing real shares from a lender who expects them back. Going short a futures contract involves no borrowing and no equivalent lender — there's no float, no short-interest data, and no margin-call-driven forced buyback for a futures short position the way there is for a stock. This entire screening layer (the source material's baseline filter was roughly: at least 5 days to cover, and at least 20% of the float sold short) has no futures equivalent and shouldn't be force-fit onto one.
- **The transferable idea underneath it: a four-phase model of a trapped, one-sided position being forced to unwind.** (1) *Building* — a directional position accumulates for some reason (the reason itself doesn't matter to the strategy). (2) *Transition* — the move stalls or consolidates; both sides turn cautious, but there's no forced exit yet. (3) *Trigger* — some event causes the trapped side to start exiting. (4) *Cascade* — the forced exits become self-reinforcing (each exit pushes price further against the remaining trapped positions, forcing more exits), producing a fast, outsized move. This is a generic pattern for any scenario where a population of leveraged positions can be mechanically forced to close, not just equity short squeezes — but for futures, the "why they're forced" mechanism would have to be something else entirely (e.g., a dense cluster of resting stop-losses at an obvious level), since there's no public, intraday-usable positioning dataset for futures equivalent to stock short-interest data.
- **The screening filter was treated as a priority-sort, not a strict requirement**, consistent with the same pattern seen elsewhere in this material: setups lacking the "favorable environment" data were still watch-list candidates on unusual volume/price action alone, just ranked lower than ones with confirmed heavy positioning data behind them.
- The actual trade-execution mechanics in this course (resistance-break entry with the same early-vs-confirmed tradeoff, support- or moving-average-based stop with a cushion, ratcheting the stop to each new candle's low, avoiding round-number stop placement) are the same mechanics already captured above — this course just applied them to a different setup-discovery method, not new execution logic.

## Adapting This to Futures / NinjaTrader Automation

- The original course's chart-setup content was specific to its own charting platform and isn't included here — NinjaTrader setup is a separate, unrelated process.
- **Volume-based tools need reinterpretation for futures.** CMF, MFI, and any volume-confirmation rule above were built around single equity listings. Futures volume is still meaningful, but continuous-contract construction, contract rollovers, and the RTH/Globex session split all shape volume differently than a single stock ticker does — treat volume thresholds/comparisons as needing recalibration to your instrument and session window, not a direct copy-over.
- **What's directly codeable as a fixed rule** (useful starting points for NinjaScript conditions): candlestick body/shadow ratios, MA order/crossover checks including golden-cross/reverse-golden-cross with slope-based strength tiers, MACD line vs. signal line and zero-line position (including a signal-line-only zero-cross gate as an earlier/alternate trigger), RSI/Stochastic threshold levels and 50-line crosses, S/R role-reversal checks, volume-relative-to-average comparisons, measured-move target projection, the reward-to-risk ratio filter (entry/exit/stop → minimum acceptable exit check), round-number stop avoidance, breakeven/partial-profit triggers once unrealized gain equals initial risk, risk-tiered scale-out sizing (smaller first scale-out for earlier/riskier entries, larger for later/more-established ones), an explicit multi-criteria checklist score (count satisfied conditions out of a fixed set rather than a single pass/fail judgment), and a consecutive-same-direction-candle count combined with distance beyond a Bollinger Band as an overextension gauge.
- **What's still a discretionary judgment call in the original material**, and would need a concrete numeric definition before it could be automated: "split the difference" trendline placement, pattern-recognition steps described visually (triangle/wedge/channel shapes) rather than with hard coordinates, the choice between a tight structural stop versus a wider moving-average trailing stop (fine as personal preference, but an automated system needs one fixed, consistent rule), the "too extended past the breakout" check for momentum-style entries (needs a concrete tick or ATR-multiple cutoff rather than an eyeballed judgment), and exactly how much more "aggressive" counter-trend profit-taking should mean in concrete terms (e.g., a smaller R-multiple target or a larger scale-out percentage) — these are the pieces that would need the most translation work to become fixed, backtestable rules.
