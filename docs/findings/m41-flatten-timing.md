---
id: M41
title: "M41 — the live flatten timing: the one divergence a backtest cannot show, measured"
archetypes: [InsideBarTrailing, OpeningRange]
issues: [346, 193]
gates: []
outcome: negative
verdict: >-
  At the candidate's bar size the live 180-second cutoff selects exactly the same bars as the backtested 30, so the divergence is zero by arithmetic rather than small by measurement; a whole bar earlier costs 1.4% of net on MNQ and gains 0.4% on NQ, and a whole 15-minute bar earlier moves held-out profit factor by at most 0.040 with the sign belonging to the archetype.
---

# M41 — the live flatten timing: the one divergence a backtest cannot show, measured ([#346])

**If the edge lives in the forced flat, the moment of the flatten is the strategy.** [#346] asked what it costs that a live account will flatten at a different moment from the one every stored result was measured at, and settled [#193] in the same pass. Both rest on the same fact: in a Strategy Analyzer backtest `ExitOnSessionCloseSeconds` is inert — [nt8-fidelity.md](../nt8-fidelity.md) § "`ExitOnSessionCloseSeconds` is honoured but inert at bar granularity" has the probe, and §M22 has the trade list that corroborates it. Live it is not, and `InsideBarTrailing.cs:46` sets 180 where the simulation runs every archetype at 30.

**The simulator is the only instrument that can see this move**, because `sessions.force_flat_mask` cuts the countdown at whatever `context.prepare` is told and NinjaTrader's backtest ignores the property entirely.

## What was run

`tools/campaign_flatten.py`, new here. Each of the two midday candidates' held-out shortlists — 20 configurations per root × resolution, chosen on the selection window, read on the holdout — re-run at four cutoffs over identical bars:

```bash
./.venv/Scripts/python.exe tools/campaign_flatten.py --strategy InsideBarTrailing \
    --root MNQ NQ --stratum phase=MIDDAY --variant trailing
./.venv/Scripts/python.exe tools/campaign_flatten.py --strategy OpeningRange \
    --root MNQ NQ --stratum phase=MIDDAY --variant "window=30m stop=opposite target=R"
```

| rung | what it is                                                                                         |
| ---- | -------------------------------------------------------------------------------------------------- |
| 30s  | the control — what every stored row was swept at, and what both stop-market ports set              |
| 180s | what `InsideBar.cs` and `InsideBarTrailing.cs` set, so what a live account does                    |
| 300s | a whole 5-minute bar, because the live flatten falls *inside* the last bar and cannot be expressed |
| 900s | a whole 15-minute bar, which binds at every resolution here                                        |

**The pairing is exact and that is the whole design.** Both arms are the same configurations on the same bars with the same code, one cutoff apart, so a difference is the cutoff's and nothing else. `moved` is the share of pairs whose net P&L changed at all — a cutoff that cannot reach past the last bar reproduces its control exactly, and reading that as "the cutoff did nothing" is the error the column exists to stop.

**900 seconds is here to separate two different nulls.** A ladder that reads flat at 180 could mean the live cutoff is too small to see, or that this book does not care when it is flattened. A rung that binds everywhere tells them apart.

## The 180-second rung is not small — at 5 minutes it is exactly nothing

The countdown is to a bar's **end**, so a cutoff inside the last bar cannot reach the bar before it. Bars in the mask over the held-out window, against 493 MNQ and 488 NQ sessions:

| resolution | 30s     | 180s    | 300s  | 900s  |
| ---------- | ------- | ------- | ----- | ----- |
| 1m         | 493     | 1,954   | 2,928 | 7,798 |
| 2m         | 493     | 986     | 1,473 | 3,908 |
| **5m**     | **493** | **493** | 980   | 1,954 |
| 10m        | 493     | 493     | 499   | 986   |
| 15m        | 493     | 493     | 493   | 980   |

MNQ. NQ has 488 sessions and the same shape throughout — 1,947 / 2,919 / 7,788 at one minute — with one difference that matters: at 10 minutes its 180-second mask is 489 rather than 488, so a single session moves.

**At 5 minutes — the bar size every candidate cell is at — the live value selects the identical set of bars as the backtested one, on both roots.** The two runs are byte-identical, `moved` is 0.000 in all four 5-minute cells across both archetypes and both roots, and no measurement is needed to say so.

**So the divergence #346 was raised about does not exist at the candidate's resolution.** It exists at 1 and 2 minutes, where the mask grows four- and two-fold, and that is where the rest of this reads.

## Where 180 does bind, it is worth nothing either

Median within-cell change against the 30-second control, held out, 20 pairs per cell:

| archetype         | root | res |    ΔPF |      Δ net | improved |
| ----------------- | ---- | --: | -----: | ---------: | -------: |
| InsideBarTrailing | MNQ  |  1m | −0.001 |   −$154.75 |     0/20 |
| InsideBarTrailing | MNQ  |  2m |  0.000 |    +$21.00 |    13/20 |
| InsideBarTrailing | NQ   |  1m | −0.002 | −$3,908.00 |     0/20 |
| InsideBarTrailing | NQ   |  2m | +0.001 | +$2,905.00 |    19/20 |
| OpeningRange      | MNQ  |  1m | −0.001 |    −$92.00 |     6/20 |
| OpeningRange      | MNQ  |  2m | −0.003 |   −$274.50 |     0/20 |
| OpeningRange      | NQ   |  1m |  0.000 |   −$392.50 |    12/20 |
| OpeningRange      | NQ   |  2m | −0.001 | −$1,547.50 |     2/20 |

**Eight cells, every one inside 0.003 of profit factor**, against holdout levels of 0.915 to 1.235. The largest net figure, −$3,908 on NQ at one minute, is 2.0% of a median net of −$194,703 — and that cell loses money at every rung, so it is not a cell anything would trade.

## The whole-bar bound: 1.4% of net on MNQ, and the sign is the archetype's

300 seconds is a whole 5-minute bar, so it moves the flatten from 17:00 to 16:55 where the live account moves it to 16:57. It therefore **over-states** the shift by two minutes and bounds it rather than measuring it — price is not monotone in time, so what it bounds is the size, not the sign.

At 5 minutes, medians over the 20 held-out configurations:

| archetype         | root | net at 30s | net at 300s | Δ net | ΔPF    | close share | net/drawdown |
| ----------------- | ---- | ---------: | ----------: | ----: | ------ | ----------: | -----------: |
| InsideBarTrailing | MNQ  |    $38,872 |     $38,341 | −1.4% | −0.006 | 0.244→0.252 |  3.546→3.440 |
| InsideBarTrailing | NQ   |   $326,740 |    $328,209 | +0.4% | +0.004 | 0.470→0.470 |  1.767→1.777 |
| OpeningRange      | MNQ  |    $19,006 |     $18,702 | −1.6% | −0.002 | 0.643→0.643 |  1.717→1.716 |
| OpeningRange      | NQ   |   $206,636 |    $200,598 | −2.9% | −0.006 | 0.658→0.660 |  1.470→1.440 |

**Three of the four are a cost and one is a gain**, and InsideBarTrailing's two roots disagree in sign — 2 of 20 configurations improved on MNQ against 17 of 20 on NQ, both at p ≤ 0.003. An effect whose sign is the root's is noise dressed as a finding, and at this size that is the honest reading of all four rows.

**The trade count never moves.** 298 trades at every rung on MNQ at 5 minutes, 242 for OpeningRange; the flatten changes how legs end, not how many are taken, so `block_entry_at_session_close` is not doing anything here.

## Moving it fifteen minutes does move it, and the two archetypes go opposite ways

The 900-second rung binds in all twenty cells. Median ΔPF:

| archetype             | 1m     | 2m     | 5m     | 10m    | 15m    |
| --------------------- | ------ | ------ | ------ | ------ | ------ |
| InsideBarTrailing MNQ | −0.008 | −0.016 | +0.006 | −0.040 | −0.024 |
| InsideBarTrailing NQ  | −0.003 | −0.007 | −0.001 | −0.013 | −0.009 |
| OpeningRange MNQ      | +0.020 | +0.008 | +0.020 | +0.010 | +0.020 |
| OpeningRange NQ       | +0.016 | +0.005 | +0.015 | +0.002 | +0.018 |

**OpeningRange gains in all ten cells** — 16 of 20 configurations improved in every one, p = 0.012 — and **InsideBarTrailing loses in nine of ten**. Same instrument, same window, same rule applied; opposite answers.

Two things follow. **The flatten timing is a real lever and a small one**: the largest move here is a quarter of an hour, twenty times the live shift, and it is worth at most 0.040 of profit factor. And **its sign belongs to the archetype**, so nothing general can be said about flattening earlier — which is the same shape as §M29's finding that an unconditional time cap knows nothing about price.

**This is not an argument for setting `ExitOnSessionCloseSeconds = 900`.** The rung is a probe, not a proposal: a live account flattening fifteen minutes early is a different strategy, it would have to be swept rather than read off a shortlist chosen under a different exit, and OpeningRange's +0.020 is a selection-window-free gain of about 1.6% of net on a cell §M28.15 already shows cannot survive without its flatten at all.

## What this settles about [#193]

`.claude/rules/simulator.md` asserted that `ExitOnSessionCloseSeconds` "lives on `Archetype` and `sweep.prepare_for` reads it". It never did, and the paragraph has been deleted rather than made true. **One default is correct**, and it is now named: `sessions.EXIT_ON_CLOSE_SECONDS`.

The argument for it is stronger than "a backtest ignores the difference", which was §M22's and is about NinjaTrader. The measured version is about the bars: **at 5 and 15 minutes the two values the ports actually set pick the same mask on both roots, and at 10 they differ by one NQ session**, so above 2-minute bars a per-archetype field would be a parameter that cannot change a result. At 1 and 2 minutes it can, and there it is worth under 0.003 of profit factor.

**What a per-archetype field would buy is a Tier-1/Tier-2 disagreement**, not fidelity: honouring the 180 in the simulation *lowered* agreement with NT8's own trade list from 99.64% to 98.42% (§M22).

## For going live

- **Setting `ExitOnSessionCloseSeconds` in the C# is a free choice at 5-minute bars**, which is where both candidates are. Leaving `InsideBarTrailing.cs` at 180 does not make the live account a different strategy from the backtested one.
- **The exposure is bounded at about 1.4% of net and 0.006 of profit factor** by the 300-second arm, which over-states the shift.
- **If a candidate is ever taken to 1- or 2-minute bars, this becomes live again** — the mask grows four-fold at one minute — though it is still worth under 0.003 of profit factor there.

## The stored rows no longer reproduce, and that is why the levels here are this run's

`reconcile` is the control rung read back against the row the sweep stored for it:

| archetype         | root | swept bars recovered | trade count reproduced | net P&L reproduced | largest gap |
| ----------------- | ---- | -------------------- | ---------------------: | -----------------: | ----------: |
| InsideBarTrailing | MNQ  | yes                  |                100/100 |              5/100 |        $131 |
| InsideBarTrailing | NQ   | **no**               |                  0/100 |              0/100 |     $78,075 |
| OpeningRange      | MNQ  | yes                  |                100/100 |             20/100 |         $82 |
| OpeningRange      | NQ   | **no**               |                  0/100 |              0/100 |     $11,128 |

**The archive was extended on 2026-09-16, after every campaign here was swept.** `campaign_shortlist.swept_series` cuts it back to where it stood, which recovers the window on MNQ exactly — every stored row's first and last held-out bar agree, and every trade count reproduces. On NQ it does not: that root gained history *earlier* than its tail, so the 60/40 split moved and no truncation recovers it. The MNQ net P&L still drifts — by up to $131 across the five resolutions, and by $83 at 5 minutes on a book of $38,872 — which is a handful of revised bars rather than a different book.

**This weakens nothing above and it is stated rather than worked around.** Every row of the ladder is a difference between two rungs of one run on identical bars, which does not depend on reproducing a figure measured in September. What it does mean is that the *levels* in these tables are this run's rather than §M28.16's or §M40's, and they should not be quoted as those campaigns' numbers. `tools/campaign_flatten.py` reports the reconciliation before the ladder for that reason, and `swept_bars` says per cell which window it ran on.

## What this cannot say

- **It is the simulation's flatten, not a live one.** The live account exits at market at 16:57:00 wall clock; the nearest things expressible here are the 16:55 and 17:00 bar closes. Nothing measures the slippage or the fill of a market order placed three minutes before the close, and no backtest can.
- **Two archetypes, one stratum, one shortlist each.** `phase=MIDDAY` is where both candidates live; the unfiltered cells, where session-close share runs much higher for InsideBarTrailing, are unmeasured.
- **The p-values are a sign test over 20 paired configurations of one strategy on one series**, which are 20 overlapping runs rather than 20 independent trials. They are reported because the instrument reports them; the effect sizes and the root agreement are what carry the reading.
- **The 900-second rung is a probe of the mechanism, not a configuration anyone ran a campaign on.** Its shortlist was chosen under the 30-second exit.

[#193]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/193
[#346]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/346
