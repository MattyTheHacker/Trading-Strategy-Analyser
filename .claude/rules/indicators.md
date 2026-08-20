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
- **ATR**: seeds with an *expanding simple average* of True Range before switching to Wilder.
- **StdDev**: *population* divisor over an expanding window, computed two-pass.
- **Bollinger**: `SMA ± k·StdDev`.
- **Keltner matches neither half of the usual definition** — its midline is an SMA of *typical
  price*, and its width is the mean *high−low range*, **not ATR**. ATR agreed on a handful of
  bars out of tens of thousands.
- **True Range does not reset at a session boundary.** It reads the previous bar's close across
  the maintenance break, so on many session opens the gap makes TR exceed `H−L`.

TA-Lib is left only for MACD and RSI, which no archetype reads and which carry the same problem
unfixed. Anything a new archetype reads must be pinned against NT8 first.
