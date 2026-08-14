# Order-Flow and Auction-Market Concepts

Alternative views to [trading_concepts.md](trading_concepts.md), drawn from a body of intraday futures
education organised around order flow, auction-market theory and session-anchored reference levels
rather than around indicators and named chart patterns. This is a second opinion, not a second
catalogue: read it for what it supplies that the companion document lacks, and for the places where the
two disagree.

Same conventions throughout: what is directly codeable, what needs a numeric definition first, what
belongs to a discretionary style and does not survive automation, and — the part that earns the document
its place — where this material contradicts what is already in the knowledge base. Section numbering is
kept stable so it can be cited.

**Priorities live in [roadmap.md](roadmap.md), not here.** These notes say what an idea is and what it
would take to test it. What gets built in what order is the roadmap's job, and duplicating it here just
creates two answers that drift apart.

**Coverage.** Read in depth, because it is genuinely new relative to Parts I and II of the companion
document: volume profile, TPO / market profile, VWAP and anchored VWAP, a five-key-levels framework,
initial balance, opening-range breakout, choppy and inside days, Wyckoff, traps and liquidity grabs,
failed breakouts, order flow and trapped traders, gamma exposure, and new-day opening gaps. Skipped as
restatements of Part I, restatements of the prop-firm mechanics already in Part II §3.5, or unstructured:
previous-day high/low, gap-and-go, generic breakouts and reversals, flags, trendlines, the
moving-average material, the beginner course, the prop-firm and psychology material, and the live-stream
recordings. Worth a second pass only if the previous-day-levels and gap material turns out to add level
definitions this document does not already cover. The source is video, so terminology below is
reconstructed rather than quoted; nothing here depends on a disputed word.

---

## 1. Source assessment

This material is commercially structured in a way Part II's source was not, and that changes how to read
it.

**Monetisation, stated openly in the material itself:**

- A paid multi-module video course, bundled with lifetime access to a private community and a set of
  proprietary charting indicators, promoted in-video with a discount code.
- A commercial NinjaTrader indicator package that automates exactly the levels this document treats as
  the useful part: prior week and prior day high/low/open/close, Globex levels, opening range, initial
  balance, plus a multi-timeframe "market conditions" panel, buy/sell/pullback signals with audible
  alerts, and a candle-recolouring trend overlay. A second order-flow product is referenced alongside it.
- Affiliate relationships: an options-analytics vendor supplying the gamma levels in §5.6, an order-flow
  platform, and broker and prop-firm links.
- Free daily live streams, which function as the top of the funnel.

**What this implies.** Every level, framework and "pro tip" below is also a feature list for a product
being sold. That is not disqualifying, but it inverts the incentive structure of Part II's source, whose
main credibility argument was that it sold nothing. Treat the *mechanics* as usable and treat any claim
of the form "this is underutilised / most traders don't know this / this gives you edge" as marketing
copy, because it is.

**In its favour, and it is not nothing:**

- The levels are repeatedly refused as signals. On gamma: a framework for what might happen at a level,
  not a prediction of where price goes. On volume profile, its two failure modes are named unprompted —
  it is discretionary, and used badly it encourages picking tops and bottoms. On anchored VWAP, stated
  twice that it is not to be used alone.
- The argument runs consistently against countertrend entries and against fading strength, which is the
  correct direction of caution for the entry archetypes already catalogued.
- The order-flow material is explicitly a correction of other educators: a single large aggressive order
  is not a directional signal, and what matters is the *response* to it. That is a genuinely better claim
  than the thing it corrects.

**Against:**

- Every worked example is retrospective, and the profitable path is drawn after the fact. Where this is
  pre-empted ("this isn't hindsight, it was called live"), the evidence offered is a chat screenshot.
- P&L appears only as isolated day figures — a few thousand dollars in one session, similar in another.
  There is no equity curve, no trade count, no losing-day accounting, no win rate. This is materially
  weaker evidence than Part II's source, which at least gave a win rate and average win/loss over six
  months.
- One loss is disclosed in detail — wrong-side a reversal and stopped out on a runner, the episode that
  motivates §5.4 — which is more honesty than the genre norm, but it is one instance used to motivate
  the lesson.

**Net:** a good source of *reference-level definitions* and one genuinely valuable regime framework. Not
a source of validated edge, and the strategy claims are less independently supported than Part II's.

---

## 2. Jargon glossary

The material is dense with terminology, much of it synonyms for the same underlying object under three
different naming traditions (auction-market theory, Wyckoff, and ICT/SMC). Definitions first; the synonym
problem is dealt with in §3, because it matters more than it looks.

### Auction / profile vocabulary

| Term | Definition |
|---|---|
| **POC** (point of control) | The price level with the greatest traded volume over the chosen window. Presented as "fair value" — the price both sides transacted at most. |
| **Value area** | The contiguous price range containing ~70% of the window's volume, built outward from the POC. |
| **VAH / VAL** | Value area high / low — the upper and lower edges of the above. |
| **HVN / LVN** (high/low volume node) | A local peak or trough in the volume-at-price histogram away from the POC. LVNs are prices traversed quickly with little transaction. |
| **TPO** (time price opportunity) | Market-profile unit: one letter = one 30-minute bracket in which price traded at that level. Builds a *time*-based profile rather than a volume-based one. |
| **Single print** | A price level touched in only one 30-minute bracket. The TPO equivalent of an LVN. |
| **D / P / B shape** | Profile silhouettes. D = balanced/rotational; P = top-heavy (volume built at the highs); B = bottom-heavy. Read jointly with where the session closed and where the next session opens. |
| **Initial balance (IBH / IBL)** | The high and low of the session's first hour (9:30–10:30 ET), fixed at 10:30. |
| **Failed auction** | Price trades beyond IBH or IBL and does not hold there, returning inside. |
| **Balance / imbalance** | Balance = two-sided rotation within a defined range. Imbalance = one-sided, directional. |
| **Rotation vs. expansion** | Rotation = trading between range edges. Expansion = accepted trade beyond them. |
| **Premium / discount** | Above VAH / below VAL respectively. Buy discount, sell premium. |

### Level and session vocabulary

| Term | Definition |
|---|---|
| **PDH / PDL / PDO / PDC** | Previous day high / low / open / close. |
| **Overnight high / low** ("Asia London high/low") | Extremes of the Globex session before the 9:30 ET cash open. |
| **NDOG** (new day opening gap) | Gap between the 5 p.m. ET Globex close and the 6 p.m. ET reopen. Small. |
| **Cash gap / settlement gap** | Gap between the 4 p.m. ET cash close and the 9:30 ET open. Large, and *invisible on a futures chart in ETH*, because futures traded through it. The most-repeated point in the corpus. |
| **RBS / SBR** | Resistance-becomes-support / support-becomes-resistance. Identical to the role-reversal rule already in Part I. |
| **Front side / back side of the move** | Above a rising VWAP (buy dips) vs. below a falling VWAP (sell rallies). |
| **"Zones"** | A branded EMA stack: three bands at 13/21, 34/50 and 72/89 periods. Ordinary EMA ribbons. |
| **Two-leg pullback** | A retracement in two visible legs before continuation. Never numerically defined. |

### Positioning / trap vocabulary

| Term | Definition |
|---|---|
| **Liquidity** | Resting stop orders, i.e. the orders that will fire if price reaches a level. Not the market-microstructure meaning of the word. |
| **Liquidity sweep / stop hunt / spring / shakeout** | Price briefly exceeding a level, triggering stops there, then reversing. Four names for one event. |
| **Look above and fail / look below and fail** | The same event described from the chart's point of view. |
| **Trap** | The same event described from the trapped participant's point of view. |
| **Absorption** | Large aggressive orders repeatedly hitting a level without price moving — inferred passive size on the other side. |
| **Composite man** | Wyckoff's device: treat all institutional activity as one actor. Often rebranded as "the algo". |
| **Order block / supply zone / demand zone** | ICT/SMC naming for a support or resistance area drawn from a specific candle. |
| **FVG / imbalance / fair value gap** | ICT naming for a price range crossed quickly. The material argues, correctly, that the profile-based LVN is the better-founded version of the same idea because it is measured rather than eyeballed. |
| **BOS / CHoCH** | Break of structure / change of character — a swing high or low being taken out against the prevailing sequence. |
| **Internal vs. external liquidity** | Stops inside the current range vs. beyond its extremes. |
| **"Strong low"** | The swing low that produced the most recent higher high; taking it out is what counts as a real trend change. |

### Options vocabulary

| Term | Definition |
|---|---|
| **Delta / gamma** | Delta = an option's sensitivity to the underlying. Gamma = the rate at which delta changes. The analogy offered — delta is speed, gamma is acceleration — is a fair one. |
| **Dealer hedging** | Options market makers hold the other side of customer flow and hedge with the underlying to stay directionally neutral. The rebalancing trade is what reaches the futures market. |
| **Positive / negative dealer gamma** | Positive: hedging is counter-cyclical (sell strength, buy weakness), damping volatility. Negative: hedging is pro-cyclical (buy strength, sell weakness), amplifying it. |
| **Gamma flip / zero gamma level** | The price at which aggregate dealer gamma changes sign; used as a regime boundary. |
| **Call wall / put wall** | Strikes with large concentrated exposure, read as potential resistance and support respectively, or as magnets. |
| **Pinning** | Price rotating around a large strike into expiry. |
| **Expected move** | Approximate one-standard-deviation session range implied by option prices; the quick version is the at-the-money straddle price. |
| **0DTE / OPEX** | Zero-days-to-expiry options / monthly options expiration. |
| **GEX** | Aggregate gamma exposure, as published by a vendor. |

### Terms that are noise

- **"Magnet zone", "the algo", "smart money", "where they want to take price"** — narrative, not definitions.
- **"True imbalance, not an ICT imbalance"** — a branding dispute; both name a low-participation price range.
- **"Quasimodo"** — a head-and-shoulders.
- **Branded "signature" setups** — proprietary names for setups already covered elsewhere; one, for instance,
  is an initial-balance failure reverting to VWAP, which is §5.3 with a nickname attached. No content beyond
  the underlying setup.
- **"Use hard stops"** — a recurring sign-off. Sound advice, no information.

---

## 3. The synonym problem, and why it matters here

The single most useful analytical observation about this corpus is that it names one event repeatedly and
then counts the names as independent confirmation.

A break of a swing low followed by a reclaim is, in this material: a liquidity sweep, a stop hunt, a
spring, a shakeout, a look-below-and-fail, a bear trap, a failed auction, a failed breakout, and the
phase-C transition of the Wyckoff schematic. One worked example stacks confirmations explicitly and counts
them off — previous-day close swept, gap unfilled, overnight low swept, Bollinger band tagged, order block
tapped — describing the count as "ticks" building conviction. Several of those are the same price event
observed through different tools.

This is exactly the failure mode Part III of `trading_concepts.md` already names: *indicators derived from
the same input are not independent confirmation.* The concrete consequence for nqbt is sharper than the
general principle, because the confluence-count parameter is a first-class sweepable axis in the spec. **If
a confluence count is built from levels that coincide by construction, the count is not measuring
conviction, it is measuring how many names one event has.** A gap edge that sits at the previous day's
close, an order block drawn around the same candle, and a Bollinger band touching the same price are one
condition, not three.

Practical rule for implementation: before adding any level to a confluence count, measure the pairwise
correlation of the boolean gates across the cached series. Levels that co-fire above some threshold get
merged into a single condition, or the count gets replaced by a count of *distinct* level families.

---

## 4. Where the levels come from, and the precision problem

Everything in §5 depends on levels being computable to a known tolerance. Two things in this material bear
directly on that, and both cut against the smaller bracket sizes.

**The material's own admission on profile precision.** One session is worked twice — a hand-drawn value
area against a free session-volume-profile indicator on the same bars — with the POC broadly agreeing
while VAL differs by one to two points and VAH by rather more. This is treated as acceptable. At MNQ cost
assumptions it is not: from the break-even table already in the notes, a 4-point 1:1 bracket needs a 60.9%
hit rate. **If the level itself is only defined to ±2 points, the ambiguity in the level is the same order
as the entire bracket.** Any levels-based rule set therefore needs either (a) a bracket floor comfortably
above level tolerance, or (b) a level definition that is exact by construction. Session extremes — PDH,
PDL, PDO, PDC, overnight high/low, IBH, IBL, gap edges — are exact from bar data. Profile-derived
levels — POC, VAH, VAL, HVN, LVN — are not, and depend on binning.

**The binning parameter.** The recommended settings are a row size of 1000 and a value area of 70%, with a
warning against changing them. Row size determines the price granularity of the histogram and therefore
where POC lands. This is a free parameter presented as a fixed convention, and it is an overfitting
surface: sweeping row size would almost certainly produce a "best" value with no out-of-sample meaning.
Fix it by a defensible rule — e.g. a bin width equal to a fixed number of ticks — and do not sweep it.

**Two corrections to the value-area description.** First, the material states that outside the value area
represents 15% of volume; it is 15% *per side*, 30% total. Second, the 70% figure is conventionally
described as one standard deviation, and that framing is inherited here. It is an approximation borrowed
from the normal distribution: the value area is produced by an expansion algorithm outward from the POC
until 70% of volume is enclosed, and intraday volume-at-price distributions are frequently bimodal. Treat
70% as a convention, not as a distributional statement, and note that the algorithm's tie-breaking rules
differ between platforms — another reason profile-derived levels will not reconcile cleanly between Python
and NT8.

**Splicing interacts badly with profiles.** `splice.py` builds a continuous series across quarterly rolls,
with optional back-adjustment. A volume-at-price profile computed across a roll boundary is meaningless —
it merges two contracts' volume at nominally identical prices — and a back-adjusted series shifts
historical prices without shifting the volume that was traded at them. Session-anchored levels are safe
because they are computed within a single session. **Any profile work must be computed per-contract on the
raw, non-adjusted series and only then mapped forward.** This is a real constraint on §5.5 and worth
recording in `docs/` rather than rediscovering later.

---

## 5. What transfers, ranked by value to the project

### 5.1 A session-relative level layer (highest value, lowest cost)

This is the substantive gap it fills. `nqbt`'s entire tested space is moving-average and VWAP gates on
minute bars — the category flagged in Part II §2 as most likely to be already arbitraged away.
Session-anchored reference levels are a genuinely different feature family, they are computable exactly
from bars already cached, and none of them currently exists in `conditions.py`.

The full set, all derivable from the existing Parquet cache:

- Previous day high, low, open, close (RTH-defined).
- Overnight high and low — the Globex range from the 6 p.m. ET reopen to the 9:30 ET open.
- Initial balance high and low, fixed at 10:30 ET.
- Previous day's initial balance high and low.
- Cash gap edges: prior RTH close to current RTH open.
- New-week opening gap: Friday RTH close to Monday RTH open.
- Prior week high, low, open, close.
- Round-number levels at fixed intervals.

Each becomes a distance-to-level array — signed, in ticks and in ATR multiples — plus boolean gates for
proximity, first-touch, break, and reclaim. Cheap to precompute in `context.prepare`, and the
ATR-normalised distance form composes directly with the ATR-multiple bracket work item already queued.

**One implementation decision to make explicitly, not by default:** the RTH session boundary. CME equity
index futures run Sunday 6 p.m. to Friday 5 p.m. ET with a daily maintenance halt from 5 to 6 p.m., and
the cash session is 9:30 a.m. to 4 p.m. ET. The entire cash-gap concept depends on measuring from the
4 p.m. cash close rather than the 5 p.m. Globex close, and index futures also observe a short halt shortly
after the cash close, so "the RTH close" has more than one defensible definition. `sessions.py` already
assigns trading days; whichever boundary it uses will silently define every level above, and it must match
whatever NT8 session template Tier 2 validation uses or the two tiers will disagree for reasons that look
like strategy differences.

### 5.2 Open-location as a categorical regime label (highest value for work already queued)

The regime work item currently plans a continuous classifier — Kaufman efficiency ratio with sweepable
thresholds. This corpus supplies a second regime axis that is categorical, computed once per day,
essentially free, and plausibly orthogonal to efficiency ratio:

> **Where the session opens relative to the previous day's range determines whether to expect rotation or
> expansion.** Opening inside the prior day's range implies an inside day and choppy two-way trade, because
> the stops that fuel a directional move sit at the prior day's extremes and have not yet been reached.
> Opening outside it implies expansion.

The same logic extends one level down — an initial balance nested inside the previous day's initial balance
signals an even tighter, more rotational day — and one level up, reading consecutive inside days as
compression that eventually resolves violently. The profile material arrives at the same idea by a
different route: the previous session's shape, combined with where it closed and where the next one opens,
is the whole framework for classifying the day before it starts.

**Why this is worth building before or alongside the efficiency ratio.** ER is a trailing window measure —
it tells you the regime you have been in. Open-location is knowable at 9:30 and constant for the session,
so it can gate entries from the first bar rather than after a lookback fills. It is also directly
interpretable, which matters when the current finding is "0 of 192 profitable" and the goal is diagnosis.
And it is one line of pandas: a categorical label per trading day with a small number of states (open above
prior range / inside upper half / inside lower half / below), carried onto every trade record exactly as
the ER label will be.

There is published support for regime-conditioning of intraday effects generally, though not for this
classifier specifically: Gao, Han, Li and Zhou (*Market Intraday Momentum*, JFE 2018) find the first
half-hour return predicts the last half-hour return on SPY over 1993–2013, with predictability concentrated
on volatile days, high-volume days and macro-release days. The effect size is small — a predictive R²
around 1.6% — which is worth internalising as a calibration for what a real intraday edge looks like before
costs.

### 5.3 Initial balance: a codeable regime plus two setups

The cleanest strategy content in the corpus, and it maps to `@njit` work with no discretionary residue.

- The IB is the first-hour range, fixed at 10:30 ET.
- **Inside the IB, expect rotation.** Trend trades inside it are explicitly declined; the edges are traded
  back toward VWAP instead.
- **Failed auction:** price exceeds IBH or IBL, fails to hold, and returns inside. Target sequence is VWAP
  first, then the opposite IB extreme.
- **Acceptance:** price exceeds an IB extreme, pulls back, holds it as support/resistance, and continues.
  The retest is taken, not the break.
- A specific, testable timing claim: a failed auction usually resolves within about thirty minutes, tied to
  the 11:00 ET hourly bar.

Three things make this attractive: the state (inside / above / below / returned) is a precomputed integer
array; the two setups are exact inverses, so a single simulation function covers both by sign; and the
"failed auction" case is the same object as §5.4, which means one implementation serves several sections of
this document.

The IB is also the 60-minute opening range, which connects it to the ORB literature. Zarattini, Barbon and
Aziz (2024) tested 5/15/30/60-minute opening ranges across more than 7,000 US stocks from 2016–2023 and
reported strong results — but with a critical qualifier for this project: the plain ORB was weak, and the
performance came from cross-sectionally selecting "stocks in play" by abnormal opening volume. **That
selection mechanism does not exist for a single futures contract.** The companion single-instrument study
on QQQ/TQQQ (Zarattini and Aziz) is closer in shape to NQ, but assumes no slippage and leans on leverage,
which is precisely the assumption nqbt exists to refuse. The honest reading: opening-range effects are real
enough to be worth testing on NQ, and the published Sharpe figures are not transferable evidence about NQ.

The material's own ORB guidance is unusually candid and should be recorded: opening-range breakouts are
stated plainly to be *not* high-probability, to be scouting trades, and that most of the position should be
taken at 1:1. That is a much weaker claim than the framing around it implies, and it is testable directly.

### 5.4 Failed breakouts as the inverse entry archetype (best-supported single setup)

The corpus's most-repeated setup, and the one with real microstructure support behind the mechanism.

The mechanism as described: buyers in a range place stops below the range low; breakout sellers place
entries in the same place; the two combine into a concentration of sell orders just under an obvious level;
a large buyer who needs size uses that concentration as the only place to get filled; price reclaims, and
the stopped-out longs plus the new shorts both become buyers. The order-flow material adds a second read —
repeated large aggressive sell orders producing no downward progress implies passive absorption.

**The external evidence is unusually good for the order-clustering half of this.** Osler (*Currency Orders
and Exchange Rate Dynamics*, Journal of Finance 2003; and *Stop-Loss Orders and Price Cascades in Currency
Markets*) obtained actual stop-loss and take-profit order records from a major FX dealing bank and found
that take-profit orders cluster at round numbers while stop-loss orders cluster *just beyond* them, and
that exchange rates move rapidly after reaching levels where stop orders cluster. That is direct evidence
for the two propositions this setup rests on: that predictable levels attract resting orders, and that
crossing them propagates the move. It is FX and it is round numbers rather than session levels, so it is
analogical support rather than proof for NQ.

For the order-flow half, Cont, Kukanov and Stoikov (*The Price Impact of Order Book Events*, Journal of
Financial Econometrics 2014) established a roughly linear relationship between order-flow imbalance and
short-horizon price change, with slope inversely proportional to depth — which is the formal version of
"aggressive selling into a thick passive bid does not move price". Two caveats the material does not
mention: displayed resting size can be cancelled before it trades, so a depth-map "wall" is not a
commitment; and the relation is strongest over horizons of seconds, not the minute bars nqbt runs on.

**Codeable form**, and note it needs no new machinery beyond §5.1:

```text
break     : low[t] < level - break_ticks          (for a downside sweep)
reclaim   : close[t+k] > level, for k <= reclaim_bars
entry     : long on reclaim confirmation
stop      : beyond the sweep extreme + cushion, round-number-avoided
target    : opposite side of the originating range
gates     : level family; regime label; time-of-day window
```

Parameters worth sweeping: `break_ticks` (how far past the level counts as a sweep rather than a break),
`reclaim_bars` (how quickly it must come back), and which level families qualify.

**Why this specifically deserves priority.** The random-entry null model in the queued work exists to
distinguish three diagnoses of the current PF 0.746, one of which is "entries are worse than random, so
investigate the inverse". The trap setup *is* the inverse of a breakout entry. If the DeadCatBounce space
is systematically buying breaks that fail, then a sweep-and-reclaim archetype tests that hypothesis
structurally rather than by sign-flipping an existing signal. Those two work items should be run together.

### 5.5 Volume profile levels (plausible, unvalidated, and the best use of the unused tick cache)

Market Profile is not folklore — it originated with J. Peter Steidlmayer at the CBOT, was published by the
exchange in the mid-1980s, and was explicitly built on the idea of organising trade through a
distributional lens. That is respectable provenance. What it lacks, as far as I can find, is peer-reviewed
evidence that POC, VAH or VAL carry predictive information beyond what generic support/resistance carries.
The absence of published tests is not evidence of absence, but it does mean this sits in a different
evidential class from §5.4 and §5.6: a hypothesis worth testing, not a documented effect.

What is testable and cheap: value-area levels are just more entries in the level layer of §5.1, and the
break/reclaim machinery of §5.4 applies unchanged. The distinctive claims worth isolating are (a) that the
previous session's VAH/VAL/POC act as next-session support and resistance, and (b) that LVNs are traversed
quickly, which is a directly measurable statement about conditional bar velocity and can be tested without
trading anything.

**This is also the strongest argument yet for using the cached tick data.** The README notes tick data is
present, deliberately unwired, and that its one high-value use is measuring how often the same-bar
stop/target assumption binds. A true volume-at-price profile is a second use of comparable value — and
unlike bar-derived approximations it is exact. Both are measurement tasks rather than simulation changes,
so neither threatens the Tier 1 / Tier 2 fidelity parity that the 1143/1144 reconciliation established. The
per-contract, non-adjusted constraint from §4 applies.

The TPO variant adds nothing that the volume profile does not, for automation purposes. It substitutes time
at price for volume at price, and the material concedes the two usually agree. The D/P/B shape taxonomy is
genuinely interesting as a daily regime label but is read visually; converting it into a numeric rule (skew
and kurtosis of the volume-at-price distribution, or the POC's position within the session range) is a
small research task in its own right and should not be assumed equivalent to what the discretionary version
does by eye.

### 5.6 Gamma regime (strongest external evidence in the corpus; blocked on data)

The options material is the most substantive in the set, and the underlying idea has the best academic
support of anything here.

The claim: dealer hedging of options positions produces different market character depending on the sign of
aggregate dealer gamma. Positive gamma implies counter-cyclical hedging, damped volatility, failed
breakouts and rotation between levels. Negative gamma implies pro-cyclical hedging, amplified moves,
shallow pullbacks and persistent trends. It is used to decide *which kind of trade to look for that day*
rather than direction — fade extremes in positive gamma, respect momentum in negative gamma.

**This is supported.** Baltussen, Da, Lammers and Martens (*Hedging Demand and Market Intraday Momentum*,
JFE 2021) link market intraday momentum to gamma hedging demand from options market makers and leveraged
ETFs, and find intraday momentum is present and strengthens as net gamma exposure becomes more negative. In
other words: the Gao et al. intraday momentum effect is not uniform across days — it concentrates in a
regime, and that regime is identifiable ex ante from options positioning. Related work finds negative gamma
imbalance associated with higher volatility and more frequent jumps.

**Why this matters more than it first appears.** The queued regime work asks "does this rule set have an
edge in some subset of conditions, drowned by the rest?" This is the same question, with a published
affirmative answer for a related effect and a named mechanism. It is the strongest available argument that
regime stratification is the right next move, and it suggests the regime variable with the best prior is a
volatility-and-positioning state rather than a pure price-derived one like efficiency ratio.

**Why it is nonetheless not the next thing to build.** It requires options data — open interest and gamma
by strike for NDX or QQQ — which is not derivable from the bar cache, means a paid vendor dependency, and
means point-in-time history to avoid look-ahead. A vendor's published level today is not the level that was
published that morning three years ago, and back-filling GEX from an aggregate series would quietly
contaminate a 2021–2026 backtest. Three defensible responses, in increasing cost: (1) treat it as
motivation for the cheap price-derived regime work already queued; (2) test a realised proxy — trailing
realised volatility, or the ratio of realised range to ATR — as a stand-in for the gamma state and see
whether it separates the results; (3) source point-in-time options data as a separate project.

The derived levels — call walls, put walls, gamma flip, expected move — are outside nqbt's data reach for
the same reason. The one piece that *is* immediately usable is the framing of the expected move as a
session range estimate: a straddle-implied range is unavailable, but an ATR-derived expected session range
is not, and "how far through the expected range has this session already travelled" is a precomputable
state variable that plausibly captures some of the same exhaustion information.

### 5.7 Wyckoff (no new content)

The four-phase accumulation / markup / distribution / markdown cycle, the composite man, and the three laws
(supply-demand, cause-and-effect, effort-versus-result) are the historical origin of most of the vocabulary
in §2 and, for this project, add nothing.

Two specific reasons. First, the transferable core — a range builds, a sweep traps one side, the reclaim
confirms, the pullback is the entry — is §5.4 exactly, and the material says so itself when it collapses
the full schematic into four steps. Second, the trapped-position cascade model is already in
`trading_concepts.md` in the squeeze section: build, transition, trigger, cascade. Wyckoff is the same
model with more names.

The "composite man" framing is unfalsifiable as stated and should not be imported. The cause-and-effect law
does contain one testable claim worth extracting — that the duration of a range predicts the size of the
subsequent move — which is a two-variable regression on cached data and needs no strategy at all to test.

---

## 6. Where this contradicts the existing notes

Following the Part III convention: these are testable disagreements, not choices to make by preference.

**Reward-to-risk minimums.** Part I sets a 3:1 minimum as a hard filter. This material targets 1:1 on
opening-range trades and takes the majority off there. Both cannot be a general rule. The resolution is
already computed in the notes: the break-even table shows a 4-point 1:1 MNQ bracket needs 60.9% and a
2-point needs 71.8%. A 1:1 approach is therefore a claim about hit rate, and a strong one. It is
measurable — and it is precisely what the random-entry control arm is designed to adjudicate, because a 1:1
bracket with random entries lands near 50% before costs and below break-even after them.

**"You can flip a coin and with the right risk-reward you'll come out on top."** Stated almost in passing.
This is simply false, and it is the clearest error in the corpus. It is also the exact proposition Part II
refutes correctly: widening the target lowers the hit rate by roughly enough to hold expectancy flat, so
bracket geometry cannot manufacture edge from a signal-free entry, and costs make the outcome strictly
negative. Note the internal contradiction — the surrounding argument spends twenty minutes insisting that
you need to know where participants are positioned, which is an argument that entry information matters.

**Breakout entries.** Part I's breakout-momentum archetype buys the break after confirmation. This material
prefers the retest, and argues the retest is strongest after long ranges because the trapped side covers at
break-even there. Not a contradiction so much as a refinement, and it is already parameterisable:
entry-on-break versus entry-on-retest is a toggle, and "length of preceding range" is a precomputable gate.

**Volume tools and futures.** Part III currently flags all volume-based tools as needing reinterpretation
for futures, on the grounds that CMF and MFI were built for single equity listings. **Volume profile is the
exception and should be recorded as such.** Volume-at-price within a defined futures session is
well-defined, natively available, and does not depend on any equity-specific construct. The
reinterpretation it needs is different in kind — the roll and back-adjustment problem in §4 — rather than
the equity-listing problem.

**"Indicators reveal nothing not already in price."** Part II's source used ATR only. This one uses moving
averages, VWAP, Bollinger bands, volume profile, options positioning and order flow. The dispute mostly
dissolves as Part III already argues, but note that the two sources land on opposite sides of a *specific*
question worth settling: whether session-anchored VWAP contributes anything beyond a moving average. That
is a direct test — VWAP is already implemented, and the gate can be swept against an MA gate of matched
responsiveness.

**On the "1:1" style claim generally.** Part II's source published an account showing a 57.6% win rate with
average win 1.59× average loss — internally inconsistent with its own stated 1:1 framing. This source
states 1:1 outright for one setup. Neither provides trade-level data. Both claims are hypotheses for the
sweep, not inputs to it.

---

## 7. What doesn't transfer

- **Order flow and depth-map reading.** The mechanism is real, but reading absorption from displayed
  passive size is discretionary, operates on horizons far shorter than minute bars, and depends on a data
  feed nqbt does not carry. It is also the part of the process most vulnerable to displayed-size games. Out
  of scope for Tier 1.
- **The options-derived levels (§5.6).** Data-blocked, as above.
- **Reading profile shape by eye.** D/P/B needs a numeric definition before it means anything.
- **The ETF cross-reference workflow.** Watching QQQ/SPY on a second monitor to see the cash gap is a
  workaround for a charting limitation. In a Python pipeline the RTH close and open are directly
  addressable; there is no reason to introduce an equity data dependency.
- **"Two-leg pullback", "look left", "let it prove itself".** Undefined.
- **Everything about the commercial products** — indicators, course, community and affiliate links.
- **The prop-firm material.** Not read; and per the existing convention, read the mechanics and ignore the
  rankings, since the affiliate structure is disclosed openly.

---

## 8. Candidate work items

Ordering belongs in `roadmap.md`, not here. These are the things this corpus turns into work, with an
indication of cost and what each depends on.

1. **Session-relative level layer** in `conditions.py` (§5.1). Prior-day and prior-week OHLC, overnight
   extremes, initial balance, cash and week gaps, round numbers. Distance arrays in ticks and ATR multiples
   plus proximity/break/reclaim gates. Requires an explicit RTH boundary decision in `sessions.py` matching
   the NT8 session template. Cheap, precomputed once, unblocks 2, 3 and 4.
2. **Open-location regime label** (§5.2). Categorical, one value per trading day, carried onto trade
   records alongside the planned efficiency-ratio label. Near-free; changes what the existing 192
   combinations mean.
3. **Initial-balance state array and the failed-auction / acceptance pair** (§5.3). One integer state per
   bar, two setups that are sign-inverses of each other.
4. **Sweep-and-reclaim archetype** (§5.4). New `@njit` function; `break_ticks` and `reclaim_bars` as axes;
   level family as a gate. Run alongside the random-entry null so the "entries are worse than random"
   branch is tested structurally rather than by sign flip.
5. **Level co-firing correlation matrix** (§3). Before any confluence count over levels, measure how often
   level families coincide. Diagnostic, not a strategy.
6. **Volume-at-price from the tick cache** (§5.5). Per-contract, non-adjusted. Pairs naturally with the
   same-bar-ambiguity measurement the README already identifies as the tick data's other high-value use.
7. **Realised-volatility regime proxy** (§5.6). A stand-in for the gamma state, testable now; point-in-time
   options data is a separate project with a vendor dependency.
8. **Range-duration versus subsequent-move-size regression** (§5.7). A two-variable test on cached data,
   requiring no strategy.

Items 1–3 and 5 operate on data that already exists and change what current results mean rather than
generating more of them — the same property that put the existing regime and null-model items ahead of grid
expansion.

---

## 9. Summary judgement

The strategy content is weaker than Part II's source and the commercial incentives are stronger. The
*definitional* content is more valuable than either, because it supplies a feature family — exact,
session-anchored reference levels — that the tool does not currently have and that is orthogonal to the
moving-average and VWAP gates whose failure is the project's current finding.

Two ideas in the corpus have real external support: that predictable levels accumulate resting orders and
that crossing them propagates moves (Osler), and that intraday momentum is regime-dependent with dealer
positioning as an identifiable mechanism (Baltussen et al., building on Gao et al.). Both point the same
way as the work already queued. The second is the strongest argument available that regime stratification
is the correct next move rather than a hedge against a disappointing result.

The rest is vocabulary, and the most useful thing to do with the vocabulary is to notice how much of it
names the same event.
