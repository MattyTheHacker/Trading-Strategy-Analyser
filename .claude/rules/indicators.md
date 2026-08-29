---
paths:
  - "nqbt/indicators.py"
  - "tests/test_indicators.py"
  - "tests/test_indicators_nt8_parity.py"
---

# Indicators

**TA-Lib does not match NT8, and the divergences are not all in the same place.** Use
`indicators.nt8_*`. `docs/nt8-fidelity.md` § "Indicators" holds the bar counts and agreement
rates — quote it rather than any figure repeated elsewhere.

- **EMA**: different seeding. `indicators.py` hand-rolls NT8's recursion.
- **WMA and HMA are ported from `@WMA.cs`/`@HMA.cs`, not read out of a probe export** — a
  weaker class of evidence than everything else here, and the reason `docs/nt8-fidelity.md` §
  "WMA and HMA, ported from the NinjaScript rather than reconciled" says so out loud. `@WMA.cs`
  has two branches; the implemented one rebuilds the weighted sum every bar, which is what a
  time bar runs and is the exact one. **VWMA is absent on purpose** — its branches disagree
  during warm-up, so it needs NinjaTrader rather than a reading of the C#.
- **ATR**: seeds with an *expanding simple average* of True Range before switching to Wilder.
- **StdDev**: *population* divisor over an expanding window, computed two-pass.
- **Bollinger**: `SMA ± k·StdDev`.
- **Keltner matches neither half of the usual definition** — its midline is an SMA of *typical
  price*, and its width is the mean *high−low range*, **not ATR**. ATR agreed on a handful of
  bars out of tens of thousands.
- **True Range does not reset at a session boundary.** It reads the previous bar's close across
  the maintenance break, so on many session opens the gap makes TR exceed `H−L`.
- **Nor at a roll.** Back-adjustment cancels the contract basis *exactly* at a seam, so the step
  ATR takes there is the price move over the break the seam spans — and today that is usually a
  session the front contract's archive does not hold, not a market event. `splice.roll_seams`
  lists them; judge an ATR-sensitive rule per contract instead (`dispersion.py`).

TA-Lib is left only for MACD and RSI, which no archetype reads and which carry the same problem
unfixed. Anything a new archetype reads must be pinned against NT8 first.
