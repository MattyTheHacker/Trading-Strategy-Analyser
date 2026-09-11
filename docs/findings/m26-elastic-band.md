---
id: M26
title: "M26 — the elastic band, the first mean-reversion archetype"
archetypes: [ElasticBand]
issues: [167, 168, 169]
gates: [1, 2, 3]
outcome: mixed
verdict: >-
  The first mean-reversion archetype: Bollinger as the band, three exit schemes as three grids, and a first measurement whose held-out behaviour does not survive the test it is put to.
---

# M26 — the elastic band, the first mean-reversion archetype ([#167])

Price mostly stays inside a band; when it closes far enough outside one, take the other side and target the middle. [#168] is the design and the indicator work, [#169] the Python, [#170] the port — and [#170] happens only if the Python clears the promotion criteria under "Decisions taken", not because the Python exists.

**Why build it, when the last four archetypes were continuation rules that did not work.** DeadCatBounce, PullBackAndGo and both InsideBar ports buy strength or sell weakness, and EmaCrossover follows a regime; every result the project holds is about one family. Mean reversion is the first genuinely different hypothesis, and the machinery already leans towards it — `regime.py`'s consolidating label exists to name the state this archetype wants and every other archetype wants to avoid, so it can be gated on from the first run rather than after a rewrite. It also inverts the bracket geometry, target inside the range and stop outside it, which is a shape nothing in `bracket.py` has been exercised on.

## The band is Bollinger, and the two alternatives are rejected for different reasons

**Decided: `nt8_sma` ± k · `nt8_stddev` on close**, which is the TradingView listing on [#167] line for line. It is the cheapest correct option and the best-evidenced: both halves were read out of NinjaTrader by `NqbtIndicatorProbe.cs` and agree with `indicators.py` on every bar of the probe window — [nt8-fidelity.md](../nt8-fidelity.md) §M16 holds the count. NT8 exposes `Bollinger(numStdDev, period)` natively, so the eventual port has no indicator to hand-roll and no seeding question to get wrong.

**Keltner is rejected even though it is already implemented.** Its width is `offset ×` the mean high−low range and *not* ATR — it agreed with `ATR(20)` on 20 bars out of 89,330 — so a band built on it is not the band anybody reading the result would picture. The cost of that is not fidelity, which is pinned either way; it is that a promising number could not be explained to anyone, ourselves included, six months later.

**VWAP ± k·σ is rejected for now and is the obvious second form.** It stopped being rejected in §M26.4 below, which also measured the second of these three costs running the other way; the paragraph is kept as written because the reasoning it records is still the reasoning that deferred it. Three costs, in order of size. It has **no pin**: `session_vwap` is reconciled, a standard-deviation band around it is not, so it needs `NqbtIndicatorProbe.cs` extended and re-run — NinjaTrader time, the scarce resource, spent before knowing whether the idea works at all. Its band width **shrinks monotonically through a session** as volume accumulates, so a fixed k is a different extremity threshold at 09:00 than at 15:00, and that confound lands on top of the session-phase artefact [#43] already records. And the anchor resets at 18:00 ET, so the first bars of every session have a band that is not yet a band. If the Bollinger form shows anything, this is the variant worth the probe; if it shows nothing, the probe was not worth booking.

## The reduction: one dimensionless series per period, and k for free

The entry test "close is at least k standard deviations from the basis" does not need the bands as objects. `indicators.band_stretch` is `(close − basis) / stddev`, which **depends only on the period**, so a grid holds one float array per period and *every* multiple in a sweep reads the same array. **`num_std` is therefore a free axis** — no memory, no precompute, nothing for `dead_axes` to gate — which is the opposite of how `regime_lookback` or `higher_timeframe_period` behave, and is worth knowing before [#169] designs the grid. It is also what makes the entry threshold and the stop threshold different multiples at no cost, which is what the geometry below needs.

**Measured, because the two forms are not obviously identical.** `stretch >= k` and `close >= upper` are the same test algebraically and floating point does not have to agree. Over 200,000 synthetic bars at periods 10/20/50 and k of 1/2/3 they disagree on **exactly one bar in every configuration: bar 0**, where `nt8_stddev` is 0 and the bands collapse onto the close. Rounding never separated them anywhere else. `tests/test_indicators.py::test_band_stretch_crosses_a_multiple_exactly_where_the_bollinger_band_does` pins it, including that bar 0 is the only flat window, so a silently widening exclusion fails the test. `bars_required_to_trade` excludes bar 0 regardless.

## The thesis has two axes, and [#168] added the primitive each one needed

[#167] says the reversion gets more likely the **further** and the **longer** price sits outside the band. Those are two separate quantities and both are now measurable:

| half of the thesis | quantity                                                               | added by |
| ------------------ | ---------------------------------------------------------------------- | -------- |
| further            | `indicators.band_stretch` — signed extension in standard deviations    | [#168]   |
| longer             | `conditions.consecutive_true` — unbroken run length ending at each bar | [#168]   |

`consecutive_true` is the other axis from `count_true`, which counts conditions on one bar where this counts bars for one condition; the confluence pattern had no way to say "for how long". Neither is an indicator in the fidelity sense — one is a division of two pinned series, the other is arithmetic on a boolean — so **nothing in this archetype needs a new NT8 pin**, which is the main reason the Bollinger form was chosen.

Both are entry *gates*, and both are worth carrying into the trade log as context as well, because "deeper extensions revert more often" is a claim the review side ([#47]) can test directly and an aggregate profit factor cannot.

## ATR is for the bracket, not for the signal — [#167]'s open question

**Not in the entry rule.** ATR and a standard deviation over the same window are two measures of the same per-bar movement, and the entry is already normalised by one of them. A second would add an axis that mostly duplicates `band_period` while making the rule harder to state.

**Yes in the stop, and it is not optional there.** Sizing off σ alone means a quiet window gives a near target *and* a near stop, which is the exact failure `min_bracket_dollars` exists to prevent — and mean reversion is the archetype most exposed to it, because it fires precisely when dispersion is low. `atr_bracket_distance` with the dollar floor is already the answer for a strategy with no structural swing to anchor to (§ "ATR-multiple brackets and the dollar floor") and it applies unchanged. Sweep it against a band-relative stop rather than choosing by argument.

## The geometry inverts, and that changes what R means for the third time

- **Entry**: market on the next open, which is EmaCrossover's mechanism and the one with no fill-rule risk attached. A limit at the band is the more natural execution and is the second form to try — it rests, so it dies after one bar and has to trade *through* to fill, both already implemented and reconciled.
- **Stop**: outside the band. Either `atr_bracket_distance` or `basis ∓ stop_std · σ`.
- **Target**: the **basis** — a level, not an R multiple. Legs scale out at fractions of the way back to it, so `legs.target[leg]` is `fill + d · (basis − fill) · fraction[leg]` rather than an R multiple of risk. `bracket.py` needs nothing new for this: the archetype has always written the target prices and the engine has always just resolved them.
- **R is therefore neither structure-scaled nor volatility-scaled.** With a σ stop and a basis target it is `entry_std / stop_std` by construction, identical on every combination sharing that ratio; with an ATR stop it is the ratio of two different volatility measures. **Elastic band results do not compare to any other archetype's at the same R**, which is the third distinct meaning R has taken — [nt8-fidelity.md](../nt8-fidelity.md) §M18's last paragraph is the second.

## Three exit schemes, and they are three grids rather than three archetypes

The entry rule is one hypothesis; **what to do once filled is a second one, and it is not settled by the first**. Three coherent schemes are worth sweeping, and `sweep_axes` already takes a *list of grids* as its strategy axis — so they are three grids over one `ElasticBandParams`, not three archetypes and certainly not a forked sweep. `combo_id` means the same parameters within a grid and nothing across grids, which is exactly the distinction these three need.

**Evidence classes, because they are not equal.** The project's own reconciled machinery comes first, `Trading-Docs` second as framing and as numeric definitions we lack, and the outside reading below **last** — it is a source of hypotheses for the sweep, never an input to it. It is recorded because two of its findings are specific enough to be wrong in a useful way.

### A — Band Rotation: levels, not multiples

- **Target ladder on chart levels.** TP1 is the basis; TP2 is the *opposite* band. This is the discretionary rotation trade written out — the `Trading-Docs` target sequence is POC then the far value-area edge, recorded there with the explicit caveat that the rotation is the whole trade rather than a launchpad — and it is where the practitioner literature lands too.
- **Stop beyond the excursion, plus a cushion.** The adverse extreme of the bars that were outside the band, offset by the usual ticks — never *at* the level, because price sitting on a reference level is expected to get tested. The elastic band's analogue of DeadCatBounce's swing stop, and the only one of the three whose stop is structural rather than a number.
- **A signal exit on invalidation**: price closing back outside the band beyond the excursion extreme means the range broke and held, which is `Trading-Docs`' definition of a failed trade — the conditions changed while you were in it, rather than you picking the wrong side.
- **Why it earns a slot**: the fewest fitted numbers of the three, and every level is derived from the chart rather than optimised. **Its weakness is the cost floor**: a shallow excursion gives a stop so close that the round trip dominates, and a deep one gives the fat tail.

### B — Volatility Bracket: the existing device, applied to a new entry

- **Stop is `atr_bracket_distance` off the fill**, with `min_bracket_dollars` underneath it. Nothing new: the same `@njit` device EmaCrossover and both InsideBar ports use, floor included.
- **Targets are the existing four-leg R ladder**, capped at the basis — a target beyond the mean is not a mean-reversion target.
- **Why it earns a slot**: it costs no new bracket code, it removes the absolute-price parameter that `Trading-Docs` flags as DeadCatBounce's overfitting fingerprint, and it is **the only scheme whose results are directly comparable with EmaCrossover's**, because the risk denominator is the same quantity. The outside reading lands in the same place from a different direction, recommending a stop roughly half to one-and-a-half ATR beyond the band that triggered the entry.
- **Its weakness is that it is the least like the strategy being tested** — an ATR distance has nothing to do with the band, so a stop can sit inside the range the trade is betting on.

### C — Time and Mean: no strategy stop at all

- **One target, the basis, for the whole position.** No ladder.
- **No price stop except a catastrophe limit** — `max_risk_ticks`, which is a prop-account rule rather than a strategy rule.
- **A time stop in bars**, on top of the session flatten every archetype already has.
- **Why it earns a slot, and it is the most interesting of the three.** The strongest outside finding for mean reversion is that a stop *hurts*: on a long SPY mean-reversion system over 2000–2026, adding a 5% stop to identical entries took the annual return from 8.22% to 1.05%, took the worst drawdown from −18.63% to −41.78%, and took the win rate from 66.71% to 49.05%. The mechanism is not mysterious — the stop realises exactly the adverse excursions the strategy exists to hold through — and it is the one hypothesis `nqbt` has never tested, because every archetype so far has been bracketed by construction.
- **The translation is not direct, and that is the point.** That result is a multi-day equity system with no session constraint. Here the position **must** be flat before the close, so a hold is bounded whether or not a stop exists: the session already plays the role "no stop" played there. C therefore tests the sharp version of the question — *does an explicit price stop add anything over the clock?* — which is answerable and which the SPY figure is not.
- The bar count is a real axis rather than a constant: the outside rules of thumb are "if it has not reverted in about fifteen bars it is a trend, leave", and the `Trading-Docs` claim that a failed break resolves within about thirty minutes. Both are specific enough to test and neither is evidence.

### What the three have in common, and the two predictions worth writing down first

**Stop and target are not independent knobs.** Leung and Li's optimal double-stopping solution for a mean-reverting price with transaction costs proves that **a higher stop-loss level always implies a lower optimal take-profit level** — the two co-move, and sweeping them as independent axes will find a downward-sloping ridge rather than a best corner. This is the analytic form of the same point `Trading-Docs` makes about R:R and win rate not being independent knobs, and it predicts the shape of the results surface before the sweep runs. Read the ridge; do not report the corner.

**The entry has a ceiling as well as a floor.** The same result characterises the optimal entry region as a *bounded* interval — it is optimal to wait when price is too far as well as when it is too near — and the practitioner literature reaches it from the other end, observing that the catastrophic mean-reversion losses are almost all trades taken while a trend was accelerating. Both say the naive reading of [#167], *further is always better*, is wrong beyond some point. **`max_entry_std` is therefore an axis in all three grids**, and a design change the exit research produced rather than the entry research.

**A time stop needs an exit reason and should reuse `EXIT_SIGNAL` rather than add one.** It is a strategy-decided market order at the next open, which is what that code already means, and a grid only ever enables one signal exit at a time so the scheme identifies the cause. Adding `EXIT_TIME` would move `trades.py` and therefore every stored log's schema, for a distinction the grid already carries. **If two signal exits are ever enabled together the log becomes ambiguous** — that is the cost of this choice, and it is the thing to check before enabling both.

**Build B and C first.** Between them they bracket the question that matters — whether a price stop helps at all — and neither needs new bracket code beyond a level target and a bar counter. A is third: its structural stop is a new device, and its stop distance is the least controlled of the three.

### Where the outside figures came from

Named so they can be checked, and so nothing here is quoted as ours. **None of it is evidence about NQ**, and the only claim below that carries a proof rather than a backtest is the first.

- Leung and Li, *Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit* ([arXiv:1411.5062](https://arxiv.org/abs/1411.5062)) — the analytic double-stopping result: a higher stop-loss level always implies a lower optimal take-profit level, and the optimal entry region is a bounded interval. Both predictions above are this paper's.
- [setup4alpha](https://setup4alpha.substack.com/p/stop-loss-mean-reversion-backtest) — the SPY figures. **One backtest, one instrument, daily bars, long only, no session constraint**, and a 5% stop is nothing like a bracket on 1-minute MNQ. It is quoted for the mechanism, not the numbers.
- The band-exit conventions — middle band as first target, opposite band as second, a stop half to one-and-a-half ATR beyond the triggering band, and a bar-count time stop — are practitioner consensus rather than a result, and are consistent across [LuxAlgo](https://www.luxalgo.com/blog/mean-reversion-playbook-fade-scale-exit/), [Babypips](https://www.babypips.com/trading/system-rules-short-term-bollinger-reversion-strategy) and [QuantifiedStrategies](https://www.quantifiedstrategies.com/mean-reversion-trading-strategy/).
- Mesfin, *Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures* ([arXiv:2605.04004](https://arxiv.org/abs/2605.04004)) — **the closest thing to a matched null that exists**: fourteen signal families on 5-minute MNQ over 947 days, none clearing a two-point friction assumption, with gross edge of roughly 0.07 to 1.50 points per trade. It is momentum rather than mean reversion, so it does not test this archetype — but it is the scale of edge to expect on this instrument, and it says the friction floor is the binding constraint, which is what this project already found.

## Expressibility checklist, run before building

| question                                | answer                                                    |
| --------------------------------------- | --------------------------------------------------------- |
| How long must an entry order rest?      | None on market-on-next-open; one bar on the limit form    |
| Does it need a true OCO pair?           | No — the breached side picks the direction, one at a time |
| Reverse directly from long to short?    | No — flat between trades, as EmaCrossover is              |
| Does it hold through the session close? | **No, and this binds harder here than anywhere**          |
| More than 4 entries per direction?      | No                                                        |
| An indicator NT8 computes differently?  | SMA and StdDev, both already pinned                       |

**The session-close row is the one to take seriously.** "Hold until price returns to the basis" is an unbounded hold, and the basis is moving while you wait. EmaCrossover took **1.0%** of its exits from the clock and the prediction that it would take many more was wrong — the mechanism there was that crosses are frequent, and that mechanism does not transfer, because nothing bounds a reversion. Expect `session_close_share` to be much higher, and read it before reading anything else: a high share means the archetype being measured is not the archetype the rules describe. Fixing it is then a design choice rather than a bug — a maximum hold in bars, a time stop, or accepting the clock as the third exit.

## Traps, in the order they are likely to bite

- **Both σ and ATR step at every roll seam.** Back-adjustment cancels the contract basis exactly at the seam, so the jump a seam carries is the price move over whatever break it spans — and a standard-deviation window spanning that bar inflates exactly as True Range does ([nt8-fidelity.md](../nt8-fidelity.md), "True Range at a roll boundary"). An archetype that fires on extension will therefore fire around every roll for a reason that is not a market event, and it will fade a move that never happened. **Judge it per contract** (`dispersion.py`, [#31]) before believing any continuous-series number.
- **The band contains the bar being tested, and that damps the signal.** A large move widens σ and drags the basis towards itself, reducing its own measured stretch. This is not lookahead — every input is a completed bar at or before *i* — but it is not neutral either, and the alternative is a band from bars up to *i−1* tested against `close[i]`, which is the `[1]` index in NinjaScript. Make it a toggle and measure it; do not assume either way.
- **Fading extension on an index future is structurally short-gamma.** Many small wins and rare large losses, which is the shape that flatters a profit factor over a short window and hides in an aggregate. The archetype will look best in exactly the sample where no trend happened. Walk-forward ([#50]) and the loss tail matter more here than anywhere; the aggregate profit factor matters less.
- **The band is a multi-parameter family and the temptation to search it is large.** `band_period × entry_std × stop_std × target fraction` is a large grid before any of the shared context filters are switched on, and the best cell of it is the expected output of noise. Test a combination chosen for a reason, and quote the random-entry arm ([#32]) beside any number — which for a bidirectional archetype means overriding the signal and *not* the side, exactly as EmaCrossover does.
- **`ambiguous_share` should fall rather than rise, and that is a prediction.** A near target with a far stop puts both inside one bar less often than the reverse does. Read it rather than assuming it; the mechanism is what the next decision gets made from.

## What [#169] built, and the first measurement against the null

`nqbt/bands.py` holds the grid, keyed by period alone: basis, standard deviation and stretch, one row each. `ElasticBandParams` carries all three exit schemes as parameters, `nqbt/sim/elasticband.py` is the entry half, and the registry entry is `TIER1_ONLY`. `sweep_axes` takes the three schemes as three grids, which is what the strategy axis is for.

**The band multiple really is free, and the archetype builds no moving-average grid at all** — the first one that does not, because the basis is the band's own.

**Two things `dead_axes` cannot see here.** The stop and target axes are inert at every `stop_mode` and `target_mode` but one, and it only knows how to compare a toggle against a single off value, so sweeping `atr_stop_multiple` under `STOP_EXCURSION` runs identical combinations silently. Same shape as `volume_rolling_bars`, recorded in `.claude/rules/sweep-and-context.md` rather than worked around.

**The invalidation exit and the time stop are guarded against each other rather than merely documented.** Both write `EXIT_SIGNAL`, so `__post_init__` refuses a combination with both on — a log carrying both cannot say which fired, and that was the cost this design accepted when it declined to add an exit code.

### The result: the entry beats the null on one scheme, and is still not profitable

Measured on **four MNQ front-month contracts — 03-24, 09-24, 03-25 and 09-25 — per contract rather than spliced**, because both σ and ATR step at every roll seam and this archetype fires on extension. One parameter set per scheme, not a sweep. Costs are the real ones: $1.50 round trip per contract and one tick of slippage. 200 null iterations, so the smallest reachable *p* is about 0.005.

| scheme           | profit factor     | expectancy    | win rate          |
| ---------------- | ----------------- | ------------- | ----------------- |
| A, rotation      | same on 4/4       | same on 4/4   | same on 4/4       |
| B, ATR bracket   | same on 4/4       | same on 4/4   | **better on 3/4** |
| C, time and mean | **better on 4/4** | better on 3/4 | **worse on 4/4**  |

**Read the consistency across contracts, not the individual p-values.** Thirty-six comparisons were run; a single one clearing 0.05 is the expected output of that many. Four contracts agreeing on the sign is the part that is hard to get by chance, and it is what the table reports.

**C is the finding, and its shape is the opposite of the usual mean-reversion story.** Its profit factor beats the matched null on every contract while its win rate is *worse* than the null on every contract. So the entry is not finding trades that win more often — it is finding trades whose payoff distribution is better, and the extension threshold is selecting for size rather than for frequency. Anything that tunes this archetype on win rate is tuning against the only thing it has.

**Every scheme is still unprofitable at realistic costs**, which is the same result DeadCatBounce reached and for the same reason: there is signal, and it does not cover the round trip. This is a measurement of three chosen configurations rather than of the archetype — nothing has been swept yet, and the promotion criteria under "Decisions taken" are not close to met.

**The null arm's trade counts do not match on two of the three schemes, and that bounds what the table can say.** The matched null holds the signal *count* fixed and randomises the day, but a drawn bar then meets a different stop geometry: under `STOP_EXCURSION` most draws fail the minimum-risk test, so A trades about 10,000 times against a null median near 1,900, and C trades about 5,800 against a null median near 8,600. **Only B is cleanly matched** — roughly 1,400 against 1,300 — which makes B's win-rate result the best-evidenced cell in the table and A's blanket "indistinguishable" the weakest. This is a property of pairing a *structural* stop with a day-randomising null, not a defect in either; it belongs on [#32]'s caveat list.

### The sweep, and why the exit geometry is not the deciding factor after all

The working expectation was that the TP/SL logic would decide this archetype's profitability more than anything else — it is the one whose geometry inverts, and three whole schemes were built for it. **Measured at one minute it is not true**, and the way it fails is more useful than the expectation was. **Read this whole subsection as one-minute-only**: the full sweep below adds bar size as an axis and finds it dominates everything here, which the η² table cannot show because it holds resolution fixed.

**The run.** 11,808 combinations per contract over the four MNQ front-months named above: `band_period × entry_std × min_bars_outside × max_entry_std × band_lag` crossed with each scheme's own exit axes, at $1.50 round trip and one tick. 40,672 of the 47,232 rows clear 30 trades. **6.3% of them are profitable**, and **7 of the 10,168 configurations present on all four contracts are profitable on all four**.

**Which axis moves the profit factor**, as the share of PF variance a single axis explains (η², within scheme, over the ranges swept):

| scheme           | entry axes | exit axes | largest single axis      |
| ---------------- | ---------- | --------- | ------------------------ |
| A, rotation      | 0.44       | 0.08      | `entry_std` 0.25         |
| B, ATR bracket   | 0.06       | 0.09      | `atr_stop_multiple` 0.06 |
| C, time and mean | 0.22       | 0.12      | `entry_std` 0.10         |

`entry_std` is the largest single axis in every scheme. **η² is a property of the ranges swept, not of the strategy** — a wider `tp_multiplier` range would raise the exit column — so read the table as "over ranges a person would actually try", not as a law.

**The surface only half replicates.** Spearman rank correlation of PF between contracts, over configurations present on all four: A **+0.51**, C **+0.50**, B **+0.07** (one pair negative). So B's geometry surface carries essentially no information that survives to another contract, and A's and C's carry some — most of it in the entry axes above.

**Selecting on one contract is worse than not selecting.** The best 20 configurations on 03-24 average PF 1.489 there and 1.320 on 03-25, but **0.760 and 0.832** on 09-24 and 09-25 — *below the median of every configuration* on those two contracts, which is 0.839 and 0.883. This is the multiple-comparisons trap producing exactly what the standing rubric says it produces, on this project's own data, and it is worth quoting whenever a sweep result is being read.

### The method that does answer the question: excess over the matched null

A sweep can say which geometry has the highest profit factor. It cannot say **whether that geometry earned it**, because a bracket that suits the bars flatters a random entry just as much. The random-entry arm splits the two, per geometry:

- **`null_median`** — what this TP/SL yields on these bars with no entry edge at all. The geometry's own contribution.
- **`observed − null_median`** — what the entry rule adds *at that geometry*. The excess.

Run with the entry **fixed** at the middle of every axis, chosen before looking at any result, varying only the exit geometry, 200 iterations, MNQ 03-24:

| scheme           | observed PF spread    | null PF spread        | excess spread   | verdicts                           |
| ---------------- | --------------------- | --------------------- | --------------- | ---------------------------------- |
| B, ATR bracket   | 0.638 → 0.990 (0.352) | 0.640 → 0.864 (0.224) | −0.003 → +0.125 | indistinguishable from random, 9/9 |
| C, time and mean | 0.724 → 0.825 (0.101) | 0.483 → 0.802 (0.319) | +0.023 → +0.252 | better than random, 11/12          |

**Observed PF correlates +0.71 with null PF across geometries.** Most of what a geometry sweep is ranking is what the geometry does to *any* entry.

**B is the pure case of the trap.** Widening the bracket takes observed PF from 0.638 to 0.990 and looks like tuning; roughly two thirds of that move is present in the random arm, the excess never clears significance, and the highest cell is still under 1. This is `Trading-Docs`' "R:R and win rate are not independent knobs" measured rather than argued.

**C is the finding, and it inverts the ranking.** Its observed PF barely moves across geometries while its null moves three times as much, so the excess is where all the information is — and **the excess is largest at the nearest target and smallest at the furthest**, which is the opposite order to the profit factor:

| C geometry   | observed PF   | null PF | excess            |
| ------------ | ------------- | ------- | ----------------- |
| target −0.5σ | 0.724 (worst) | 0.483   | **+0.241 (best)** |
| target +0.0σ | 0.740         | 0.637   | +0.103            |
| target +0.5σ | 0.755 (best)  | 0.709   | +0.047 (worst)    |

Picking the geometry on profit factor picks the one where the entry's advantage has been given away. The mechanism is that a near target is a *bad* geometry for a random entry — small wins against an unbounded stop — and a good one for an entry that genuinely reverts, so the near target is where the entry's information is worth most.

**The standing instruction that follows: rank exit geometries by excess over the matched null, never by profit factor.** The two agree on B, where neither is significant, and point in opposite directions on C, where one of them is — so the case that matters is the case where profit factor misleads, and nothing in a sweep table says so. `tools/geometry_contribution.py` runs the comparison and reports the two rankings side by side with the word DISAGREE when they part.

### Two axes that do nothing, and neither is visible to `dead_axes`

- **`max_entry_std` at 4.0 is inert** — mean PF moves by about 0.002 in every scheme, because the stretch rarely reaches 4 standard deviations. The ceiling from Leung and Li is a real idea and this parameterisation of it is not a test of that idea; it needs a value close to `entry_std` to bite at all.
- **`exit_on_invalidation` is structurally unreachable under `STOP_EXCURSION` at `stop_offset_ticks = 0`.** It changes the profit factor in **0%** of cells there, against 80% at two ticks and 88% at eight: the stop sits *at* the excursion extreme, so price reaching it intrabar exits the trade before any close beyond it can be observed. Two rules that look independent are one rule plus an offset.

Both are the same class as the ATR dollar floor collapsing `atr_stop_multiple`: whether an axis does anything is a property of the *data* and of another parameter, not of the grid, so `dead_axes` cannot see it and only a spread check on the realised numbers will.

### The full sweep: every contract, five resolutions, and a tight stop

**The sweep above was one minute only, and that made its headline wrong.** Resolution was not an axis in it, so "the exit geometry is not the deciding factor" was measured with the largest lever held fixed. Re-run properly — **both roots, all 19 contracts each, resolutions 1, 2, 5, 10 and 15 minutes, 1,026 combinations per point, 194,940 rows** — the picture changes and the earlier η² table should be read as a within-one-minute result rather than a general one.

**Bar size is the biggest lever there is.** Median profit factor, MNQ, over every combination at that resolution:

| resolution | ATR stop | tight stop |
| ---------- | -------- | ---------- |
| 1 min      | 0.861    | 0.791      |
| 5 min      | 0.922    | 0.884      |
| 15 min     | 0.955    | 0.955      |

Monotone in both columns, on both roots. **The mechanism is friction, and it was predicted before it was measured**: commission is a fixed sum per trade, so it is a shrinking share of a larger bar's range — median 7.6% of an average losing trade at 1 minute against 3.0% at 15. Nothing about the strategy improves with bar size; what improves is how much of it survives the round trip.

### A stop just beyond the signal candle: measured, and it does not help

The idea is a cheap repeated attempt — put the stop a tick or two past the candle that signalled, so a move that keeps going costs almost nothing and the next bar can try again. It is now `STOP_SWING` and `swing_lookback = 1` is exactly that stop.

**It makes no difference.** Median profit factor across the whole MNQ sweep, by how far beyond the extreme the stop sits and how many bars it looks back over:

| offset, ticks | lookback 1 | lookback 2 | lookback 3 |
| ------------- | ---------- | ---------- | ---------- |
| 0             | 0.858      | 0.859      | 0.858      |
| 2             | 0.866      | 0.866      | 0.866      |
| 8             | 0.869      | 0.869      | 0.869      |

Flat to three decimal places in every direction. **At one minute the tight stop is materially worse than the ATR bracket** (0.791 against 0.861) and it only pulls level by 10 minutes. The reason it cannot win is the one the cost floor already predicts: a tighter stop shrinks R while the round trip stays the same size, so it buys more attempts at a worse price each. It is a sound idea about *market* structure defeated by *cost* structure.

### Profit-taking: less aggressive is better, and it is the one exit axis that matters

Median profit factor by where the target sits, in standard deviations from the basis, signed towards the trade — −1.5 exits well before the mean, +2.0 holds through it to the far band:

| target | 1 min | 5 min | 15 min    | win rate at 15 min |
| ------ | ----- | ----- | --------- | ------------------ |
| −1.5σ  | 0.689 | 0.805 | 0.873     | 0.23               |
| −0.5σ  | 0.773 | 0.867 | 0.949     | 0.17               |
| +0.0σ  | 0.803 | 0.888 | 0.970     | 0.15               |
| +1.0σ  | 0.831 | 0.917 | 1.000     | 0.13               |
| +2.0σ  | 0.841 | 0.941 | **1.007** | 0.11               |

**Monotone across every resolution**, and the only cells in the whole table that reach 1.0 are the two most patient targets at 15 minutes. So the answer to "would more or less aggressive profit taking help" is **less**: take the win rate from 23% down to 11% and hold for the bigger move. That is the opposite of the usual mean-reversion instinct, and it is the same direction §M26's earlier null decomposition found for the *observed* profit factor — with the same warning attached, that observed profit factor and excess over the null rank geometries differently.

### Held out, and then the test it fails

Selecting on the oldest half of the contracts by expiry and confirming on the newest half:

| root | top 20 on the selection half | the same 20 on the held-out half | all configurations |
| ---- | ---------------------------- | -------------------------------- | ------------------ |
| MNQ  | 1.386                        | **1.022**                        | 0.903 / 0.882      |
| NQ   | 1.497                        | **1.202**                        | 0.970 / 0.938      |

Rank correlation between the halves is **+0.79** on both roots, so the surface genuinely replicates — mostly because resolution is in it and resolution replicates. **This is a real improvement on the one-minute result**, where selection landed below the median of everything.

**It still fails the null.** The configuration the split chose — 15 minutes, band period 20, entry at 3σ, stop one tick beyond the signal candle, target +0.5σ — run against a matched random entry on eight contracts per root, with trade counts matching closely enough to trust the comparison:

| root                  | observed PF | null PF | excess | profitable | **beats the null** |
| --------------------- | ----------- | ------- | ------ | ---------- | ------------------ |
| MNQ, $1.50 round trip | 1.180       | 0.954   | +0.226 | 4/8        | **2/8**            |
| NQ, $4.50 round trip  | 1.258       | 0.953   | +0.305 | 4/8        | **1/8**            |

The mean excess is positive and it is **two quarters carrying it** — 03-23 and 09-24 both show about +0.8, and the rest sit at or below zero. Per contract the chosen configuration is profitable through 2022 and 2023 and loses through 2024 to 2026, with a $16,204 drawdown on a single MNQ contract against $42,164 of profit summed over all nineteen. That is not an edge that decayed; it is an edge that was never separable from two good quarters.

### NQ beats MNQ on the same rules, and it is arithmetic rather than edge

Costed honestly — **$1.50 round trip on MNQ against $4.50 on NQ**, rather than the sweep's mistake of applying MNQ's figure to both — NQ still comes out ahead: 32.2% of combinations profitable against 21.0%, and a median profit factor above 1.0 at 15 minutes where MNQ reaches 0.955. Commission is three times larger and the point value is ten times larger, so the drag per point is about a third of MNQ's.

**It buys money, not edge**: NQ beats the matched null on *fewer* contracts than MNQ, not more. Any rule this marginal is worth more on the big contract, and that is a fact about the contract rather than about the rule. It also cuts the other way for a prop account, where the position size that clears the friction floor may exceed what the account permits.

**Build that grid once, because M19 reads it too.** The bandwidth form recommended above for the squeeze is `(upper − lower) / basis`, which is `2 · num_std · σ / basis` off the same two rows — so the two archetypes share one grid rather than each inventing a Bollinger of its own, which is the first item on the standing rubric.

**What [#170] would be checked against is already written down**: [nt8-fidelity.md](../nt8-fidelity.md) §M26 names the NinjaScript every rule becomes. **It is not earned.** The full sweep is the one the promotion criteria under "Decisions taken" asked for, and the archetype fails them: the configuration that survives held-out selection beats a matched random entry on two contracts out of eight, and its profit is two quarters wide.

[#167]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/167
[#168]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/168
[#169]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/169
[#170]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/170
[#31]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/31
[#32]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/32
[#43]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/43
[#47]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/47
[#50]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/50
