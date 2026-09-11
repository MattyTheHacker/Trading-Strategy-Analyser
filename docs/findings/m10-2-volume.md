---
id: M10.2
title: "M10.2 — volume: done"
archetypes: []
issues: [41]
gates: []
outcome: calibration
verdict: >-
  The volume label, and the choice of form and cut that §M27.8 later found to be what decides the answer.
---

# ~~M10.2~~ — volume: done ([#41])

`nqbt/volume.py`. **One quantity and its decomposition, not three conditions.** Absolute volume is the raw contract count, the time of day is its dominant systematic component, and relative volume is absolute with that component divided out. `VolumeForm` names the three absolute forms — per bar, a trailing *N*-bar sum, and session-cumulative-to-date — and each is divided by its own bar-of-session baseline to give the ratio the three `VolumeState` labels are cut from. `volume_filter` is a bitmask integer, for exactly the reason `phase_filter` and `regime_filter` are.

**The baseline is the median of the same bar of session over a trailing window of prior sessions, and that is the whole point of the module.** Measured on the run below, a plain trailing median over the 60 *adjacent* bars labels **82% of `CLOSE` bars thin and 57% of `CASH_OPEN` bars heavy** — a table that reads as a discovery and is a clock. Against the bar-of-session baseline the same data gives a heavy share of 16–31% and a thin share of 19–30% across all seven phases. It is not flat, and it should not be: the cash open is the hour whose volume is most predictable, so it is the hour that is least often extreme. What is gone is the part that was only the time of day. A test pins both halves — a series that is a pure function of the bar of session must produce **no state at all**, and the naive normalisation over the same series must manufacture both extremes.

**No bar contributes to its own baseline.** The window is the sessions strictly *before* this one, so a bar's whole session is excluded rather than merely the bar itself. A normalisation that reads the present is a lookahead that flatters every stratification taken through it, and it would be invisible in the output. Pinned as a property: rewriting the last session's volume leaves every earlier session's ratios untouched and scales that session's own ratios exactly.

**Absolute volume is carried and deliberately not filtered on.** It answers the one question relative volume cannot — *can this be traded here at all?* — and it carries when in history a bar happened, which is a cross-check on [#31] rather than a duplicate of it. But it is comparable neither across roots (NQ and MNQ trade different counts for the same exposure) nor across time, so there is no absolute threshold to sweep. Expressing one as a trailing percentile just makes it relative volume again, **which is the honest conclusion rather than a workaround** — and it is why the per-instrument scale in `instruments.py` that [#41] anticipated turned out not to be needed. Two tests state the pair: relative volume is unchanged by scaling the whole series by any positive constant, and a tenfold secular drift moves the absolute series by more than 4× while the relative one spans less than 1.5×. The residual there is worth knowing — a trailing median lags a rising trend, so a strongly trending series sits *above* 1 throughout. The level shifts; the shape is removed.

**It steps at every roll, and that is data rather than an event.** Prices are back-adjusted, volume is not and should not be. A step reaches relative volume for the length of the baseline window and then leaves, so a discontinuity there is dated by the roll rather than by the market. A test pins the arithmetic: an incoming contract ten times the size of the outgoing one reads exactly 10 on the roll session and exactly 1 a baseline window later.

**The warm-up is `UNDEFINED`, for the reason [#40]'s is.** A baseline needs `MIN_BASELINE_SESSIONS` observations before it means anything, so the first five sessions carry no label — 0.8% of the run below, out-of-session strays included. An undefined bar passes **no** mask, `ALL_STATES` included, so each signal skips the conjunction entirely at the default.

**Three forms, and they are three different statements rather than three views worth averaging.** The window a form does not read is dropped from its grid key, so sweeping `volume_rolling_bars` alongside the per-bar form builds one series rather than one per window. What `dead_axes` **cannot** catch is the other half of that: it understands one toggle per axis, so it knows the five volume axes are inert while `volume_filter` admits everything, and it does not know that `volume_rolling_bars` is inert at every form but `ROLLING`. Sweeping the window under a per-bar form runs identical combinations. Known, and not worth a second toggle mechanism for.

**Gated.** All 12 captured trade logs are byte-identical, `sha256` included; the two sweep summary tables differ by the six added parameter columns and are identical on every pre-existing column — `compare_trade_logs.py --added volume_filter volume_form volume_rolling_bars volume_baseline_sessions volume_thin_below volume_heavy_above` reports `ALL PRE-EXISTING COLUMNS IDENTICAL`.

**First stratification, and it is a stratification rather than a finding.** Costed MNQ continuous from 2024-01-01 (914,700 bars), stock `DeadCatParams`, $1.50 per contract and 1 tick, thresholds 0.7/1.5 over a 20-session baseline, one combination run once per state:

| form            | cell   | bar share | trades | profit factor | win rate | expectancy |
| --------------- | ------ | --------- | ------ | ------------- | -------- | ---------- |
| per bar         | THIN   | 27.5%     | 992    | 0.534         | 0.300    | −10.54     |
| per bar         | NORMAL | 44.3%     | 1,678  | 0.653         | 0.309    | −11.23     |
| per bar         | HEAVY  | 27.5%     | 942    | 0.686         | 0.346    | −12.27     |
| rolling 30      | THIN   | 18.1%     | 631    | 0.470         | 0.265    | −11.31     |
| rolling 30      | NORMAL | 61.3%     | 2,202  | 0.665         | 0.322    | −10.50     |
| rolling 30      | HEAVY  | 19.8%     | 775    | 0.659         | 0.342    | −13.57     |
| session to date | THIN   | 13.4%     | 513    | 0.526         | 0.263    | −10.27     |
| session to date | NORMAL | 69.8%     | 2,525  | 0.635         | 0.316    | −11.76     |
| session to date | HEAVY  | 16.0%     | 571    | 0.721         | 0.368    | −10.24     |
| any             | all    | 99.2%     | 3,639  | 0.640         | 0.316    | −11.28     |

**Read those nine rows as three, and then as one.** Profit factor and win rate rise with the volume state under all three forms, which looks like three confirmations and is one: the three forms are three views of the same quantity over the same bars, and the time of day has already been divided out of all of them. That is exactly the failure [#41]'s opening table exists to prevent, and quoting it as corroboration would be the mistake it names. No cell reaches a profit factor of 1, expectancy does **not** follow profit factor — HEAVY is the best per-bar cell on profit factor and the worst on expectancy — and [#48]'s guard applies with the usual force. What the table does say is that the three forms decompose the same 3,639 trades very differently: the per-bar form splits them 27/44/28 and the session-to-date form 13/70/16, so "an unusually busy bar" and "an unusually busy session so far" are not the same statement about the same trade.

**The signals partition exactly and the trade counts do not.** For every form the three single-state filters admit exactly the measured signal, bar for bar and in total — 4,841 of the unfiltered 4,889 for the per-bar form, the difference being the warm-up and the strays. The trade lists sum to 3,612 against 3,639. Same cause as [#40]'s and the same conclusion: the simulation holds one position at a time, so removing an entry moves which later signals are free, and the trade-level decomposition is approximate where the signal-level one is exact. **Stratify the signal, or accept the approximation** — and never read a count that moved as a filter having found trades.

**Cost, and it is the most expensive condition so far.** `prepare` pays about 0.2 s per series over 914,700 bars against `regime`'s 15 ms per lookback, because the baseline is a sliding median down each bar-of-session column of a `[session, bar of session]` grid rather than a pass along the series. Sixteen bytes per bar per series — 14.6 MB for one and 43.9 MB for all three, against a 37.5 MB dataset without them. The per-combination gate is 0.14 ms against 3.6 ms for the combination itself, so the filter is cheap and the preparation is what to watch when a sweep asks for several series at once.

**Smaller choices in `volume.py`, recorded here rather than in the module ([#105]):**

- **The median, not the mean.** The baseline window straddles roll dates and holiday sessions, and a mean would carry a half-empty session or a rolled contract straight into the normalisation. A median of twenty ignores one or two of them.
- **Out-of-session prints are not volume here, in any of the three forms.** NT8 building bars against an ETH template would never form them, so they read zero rather than entering a sum or a per-bar count. Their labels are `UNDEFINED` either way, because a bar in no session has no bar of session to be compared against.
- **The rolling window does not reset at the session open.** "Volume over the last thirty bars" reaches back across the maintenance break at the start of a session, which is what the words mean, and the bar-of-session baseline divides out the systematic part of it exactly — the first bars of a session are compared against the first bars of other sessions.
- **A one-bar rolling window is refused**, because it is the per-bar form under another name and would otherwise build the same series under a second key.
- **A zero baseline is undefined rather than infinite.** A bar of session whose prior sessions traded nothing has no scale to be relative to.
- **`MIN_BASELINE_SESSIONS` is a floor rather than a parameter**, and it is both the shortest legal window and the number of observations the window must actually hold. Holes mean the two are different questions.
- **The thresholds are conventional starting points, not a calibration.** 0.7 and 1.5 against a median put roughly a quarter of bars in each tail on this data; they are resolution-dependent the way [#40]'s are and will want different values at 15 and 30 minutes.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#31]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/31
[#40]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/40
[#41]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/41
[#48]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/48
