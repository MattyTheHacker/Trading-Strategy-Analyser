---
id: M43
title: "M43 — the two midday candidates ranked for a prop MNQ account, and the cell to port"
archetypes: [InsideBarTrailing, OpeningRange]
issues: [347]
gates: []
outcome: positive
verdict: >-
  InsideBarTrailing's midday cell is the one to port. The two objectives themselves split almost evenly on MNQ — 4–3 to it on time to the first payout and 4–3 against it on the cost of a pass — but everything they have to be read beside goes one way: held-out profit factor in all fourteen MNQ cells, net in eleven of them, and a session-close share a third of the fallback's on both roots. On NQ the objectives themselves go 9–1 to it, and neither candidate is tradeable there at these sizes. The named cell is combo 2035, the only one of the ten §M42 read that both survives the exclusion on all of gate 4's thresholds and leads an objective, and the two objectives disagree with each other inside the cell (rho −0.085) and with the exclusion in opposite directions.
---

# M43 — the two midday candidates ranked for a prop MNQ account, and the cell to port ([#347])

**No new sweep and no ingest.** [#344]'s Phase 0 ends by naming one archetype, stratum, variant and parameter set to port, on a prop MNQ account. The two candidates are InsideBarTrailing `phase=MIDDAY` at 5 minutes, which [#344] carries as the lead because it has a reconciled C# port, and OpeningRange `phase=MIDDAY` at 5 minutes, which is §M28.15's cell and has neither a port nor a trade-list diff.

**The scoring question is §M28.13's, not the regular account's** — not "did it survive" but "was the sequence of accounts worth more than it cost" — so the ranking is by `days_to_payout` and `fees_per_pass`, which §M40 measured as transferring held out where none of their levels does. Both candidates go through both instruments on the same footing: all ten presets in `nqbt/propaccount.py`, attempts uncapped, `PEAK_FIRST`, each archetype's own default size.

## What was run

```bash
./.venv/Scripts/python.exe tools/campaign_propaccount.py --strategy InsideBarTrailing \
    --root MNQ --stratum phase=MIDDAY --variant trailing --resolution 5 --rerun --preset <all ten>
./.venv/Scripts/python.exe tools/campaign_propobjectives.py --strategy InsideBarTrailing \
    --root MNQ NQ --stratum phase=MIDDAY --resolution 5 --variant trailing
```

and the same two for OpeningRange under `--variant "window=30m stop=opposite target=R"`, on both roots.

**`tools/campaign_propaccount.py` grew a `--rerun` flag here, and without it the lead candidate cannot be replayed at all.** `phase=MIDDAY` has no stored held-out logs: the archive was extended on 2026-09-16 after the campaign was swept, so `campaign_shortlist.py --held-out` refuses to file one, which is the trap §M42 hit and `tools/campaign_swept.py` is the answer to. The flag is the one `tools/campaign_exits.py` and `tools/campaign_montecarlo.py` already carry, wired to the same function.

**Two windows are in play and the tables below say which.** `campaign_propaccount.py --rerun` cuts the archive back to where each row was swept, which recovers MNQ's window exactly and NQ's not at all; `campaign_propobjectives.py` re-runs on today's 60/40 split. So the same configuration reads 300 held-out trades under the first and 314 under the second. Neither is wrong and they are not interchangeable.

**The control says the read is on the right bars.** OpeningRange MNQ reproduces §M28.15's four presets to the dollar — Apex 50K +17,718, Apex 150K +21,327, TopStep 50K +9,919 (9,918.5), TopStep 150K +26,982 — on 20 of 20 trade counts, with a largest net gap of $82 on a $19,000 book. InsideBarTrailing MNQ reproduces 20 of 20 trade counts at a largest gap of $83. Both NQ cells fail to recover their swept window, exactly as §M41 and §M42 record, so every NQ figure here is this run's.

**And the objective run reproduces §M40's exactly.** Re-running both cells on the unchanged archive returns `verdict.csv` files that differ from §M40's in no column at all — 76 rows each, zero absolute change. The levels below are therefore §M40's as well as this run's, which is the one place in this file where a figure is not merely one dated run.

## The objectives split; what they are read beside does not

Each candidate's own shortlist of 20, ranked by the objective on the selection window and read on the holdout, paired root × preset. Seven presets answer an evaluation objective; the three TakeProfitTrader PRO presets have no profit target and are left out of this table for that reason.

| ranked by        | root | objective itself | net held out | profit factor | session-close share |
| ---------------- | ---- | ---------------- | ------------ | ------------- | ------------------- |
| `days_to_payout` | MNQ  | **4 – 3**        | 5 – 2        | **7 – 0**     | **7 – 0**           |
| `days_to_payout` | NQ   | **4 – 1** (2 =)  | 4 – 3        | 5 – 2         | **7 – 0**           |
| `fees_per_pass`  | MNQ  | 3 – **4**        | 6 – 1        | **7 – 0**     | **7 – 0**           |
| `fees_per_pass`  | NQ   | **5 – 0** (2 =)  | 5 – 2        | **7 – 0**     | **7 – 0**           |

InsideBarTrailing's wins first, OpeningRange's second; a tie is both being `inf`, which is both never getting funded.

**On MNQ the two objectives are a dead heat, 7–7 over the fourteen cells.** InsideBarTrailing is paid sooner on Apex 50K (38 trading days against 74.5), on TakeProfitTrader 150K Test (101 against 122) and 50K Test (37 against 39); OpeningRange is paid sooner on TopStep 50K (45 against 120), TopStep 150K (122 against 244.5) and TakeProfitTrader 25K Test (21 against 25). The cost of a pass goes the other way by the same margin — InsideBarTrailing is cheaper on Apex 50K ($1,233 against $2,005), TakeProfitTrader 25K Test ($444 against $603) and 50K Test ($617 against $697), and dearer on the other four.

**Everything the objectives have to be read beside goes one way.** Held-out profit factor is InsideBarTrailing's in every one of the fourteen MNQ cells — 1.286 to 1.493 against a fallback that returns 1.214 to 1.232 in all fourteen — and net is its in eleven of fourteen. `session_close_share` is 0.09 to 0.49 against 0.65 to 0.66 in all twenty-eight cells on both roots. That is §M28.13's own trap applied to these two objectives rather than to `net`: a shortlist that is paid sooner while losing money as a strategy is the reset economics, and only one of these two candidates is clear of that reading.

**On NQ the objectives themselves go 9–1 to InsideBarTrailing**, with four ties in which neither candidate ever gets funded. It does not make NQ tradeable. At six contracts Apex 50K leaves 21 points of room and TopStep 50K 17, against 208 and 167 on MNQ; the profit-factor shortlist never passes a single account on either preset for either candidate, and only the three TakeProfitTrader Test presets return a positive median net — for OpeningRange, TopStep 150K as well. That is §M28.13's arithmetic at a larger position size rather than a new result.

## The fallback cannot really be ranked, and that is a finding about the comparison

**OpeningRange `phase=MIDDAY` holds 32 stored configurations per root; InsideBarTrailing's holds 432.** Each objective's shortlist of 20 is therefore 20 of 32 against 20 of 432, so "ranking the fallback by an objective" selects almost nothing — which is why its held-out profit factor reads 1.232 in nearly every cell of every ranking, the same overlapping rows arriving under four names.

It cuts both ways and both halves belong in the reading. The fallback's numbers are close to its whole cell's and carry almost no selection risk; the lead candidate's are a genuine choice from 432 rows and carry the corresponding risk. What it rules out is treating the 7–7 split as a like-for-like contest between two rankings — one of the two was barely ranked.

## The replay across all ten presets, on the profit-factor shortlist

`tools/campaign_propaccount.py --rerun`, medians over 20 held-out configurations, attempts uncapped. This is §M28.15's read extended to ten presets and to both candidates; it ranks on profit factor, so it is the context the section above is read against and not the ranking [#347] asked for.

| preset                     | IBT net |  OR net | IBT passed | OR passed |
| -------------------------- | ------: | ------: | ---------: | --------: |
| Apex 50K                   | +30,045 | +17,718 |       100% |      100% |
| Apex 150K                  | +24,396 | +21,327 |        80% |      100% |
| TopStep 50K                | +14,872 |  +9,919 |       100% |      100% |
| TopStep 150K               | +12,208 | +26,982 |       100% |      100% |
| TakeProfitTrader 25K Test  | +31,564 | +22,085 |       100% |      100% |
| TakeProfitTrader 25K PRO   |  +5,325 |  −5,624 |       100% |      100% |
| TakeProfitTrader 50K Test  | +29,223 | +17,601 |       100% |      100% |
| TakeProfitTrader 50K PRO   |  +8,416 |  +2,863 |       100% |      100% |
| TakeProfitTrader 150K Test | +21,856 | +19,945 |       100% |      100% |
| TakeProfitTrader 150K PRO  | +30,937 | +22,772 |       100% |      100% |

MNQ, six contracts against four. **InsideBarTrailing's median configuration nets more on nine of the ten presets**, on a median held-out profit factor of 1.487 against 1.217 and 298 trades against 242. The one it loses, TopStep 150K, is the one where its median configuration passes once against the fallback's twice.

Three readings this table needs beside it, all of which [#347] named. No pass rate here rests on a single attempt: the medians run 3 to 106.5 attempts for InsideBarTrailing and 7 to 109.5 for OpeningRange. `ever_passed` is 100% everywhere but InsideBarTrailing on Apex 150K, which funds 16 of 20. And `capped` is zero on every row of this table, so no net figure in it is truncated.

## The cell to port

**The choice rule, and it is this file's rather than a pre-registered one.** Among the ten configurations §M42 put through gate 4, take those that survive the exclusion on both of gate 4's thresholds, and rank those by `days_to_payout` on the selection window. Two constraints and one ranking: the port has to be a configuration gate 4 actually covered, it has to stand up without the forced flat because that is the standing doubt over everything in [`README.md`](README.md), and among what is left the objective decides.

`tools/campaign_exits.py --rerun --top 10` reproduces §M42's MNQ read exactly — 10 of 10 trade counts on the swept bars, 5 of 10 above a profit factor of 1.0 without their session-close legs, 2 of 10 clearing both thresholds, the median falling 1.482 → 0.975 — and names which is which:

| combo    | whole PF    | residual PF |     residual net | residual net/drawdown | survives |
| -------- | ----------- | ----------- | ---------------: | --------------------: | -------- |
| **2035** | 1.553       | **1.243**   |          +13,507 |             **1.465** | **yes**  |
| **2059** | 1.588       | **1.194**   |           +9,817 |             **1.182** | **yes**  |
| 2023     | 1.459       | 1.158       |           +9,460 |                 0.736 | no       |
| 1891     | 1.485       | 1.154       |           +9,205 |                 0.912 | no       |
| 1879     | 1.399       | 1.080       |           +5,128 |                 0.373 | no       |
| the rest | 1.412–1.554 | 0.786–0.870 | −8,489 – −15,648 |       −0.416 – −0.705 | no       |

All five that are profitable without the flatten carry `partial_take_profit_percentage = 0.6` and all five that are not carry 0.5, which is §M42's MNQ split confirmed at configuration granularity. Of the two that clear both thresholds, **2035 is the one the objective picks**: it leads `days_to_payout` on TakeProfitTrader 25K Test and has a mean rank of 3.6 across the seven presets against 2059's 6.6.

### InsideBarTrailing, `phase=MIDDAY`, 5-minute bars, MNQ, combo 2035

| what          | value                                                                                  |
| ------------- | -------------------------------------------------------------------------------------- |
| **archetype** | `InsideBarTrailing`, whose C# is `ninjatrader-scripts/Strategies/InsideBarTrailing.cs` |
| **stratum**   | `phase=MIDDAY` — entries only between 10:30 and 14:00 ET, the mask `phase_filter = 16` |
| **variant**   | `trailing`                                                                             |
| **bar size**  | 5 minutes                                                                              |
| **root**      | MNQ                                                                                    |
| **size**      | 6 contracts, this archetype's default and the minimum its split-lot exit allows        |
| **chosen on** | TakeProfitTrader 25K Test, by `days_to_payout` on the selection window                 |

Every parameter, so the port needs nothing else:

| parameter                        | value | parameter                       | value |
| -------------------------------- | ----- | ------------------------------- | ----- |
| `order_quantity`                 | 6     | `phase_filter`                  | 16    |
| `ema_period`                     | 44    | `ambiguity_policy`              | 1     |
| `ema_kind`                       | ema   | `fill_limit_on_touch`           | True  |
| `fast_sma_period`                | 20    | `block_entry_at_session_close`  | True  |
| `fast_sma_kind`                  | sma   | `round_targets`                 | True  |
| `slow_sma_period`                | 125   | `max_hold_bars`                 | 0     |
| `slow_sma_kind`                  | sma   | `commission_per_contract`       | 1.5   |
| `error_margin`                   | 0.05  | `slippage_ticks`                | 1.0   |
| `atr_length`                     | 14    | `position_update_loss_gate`     | 200.0 |
| `atr_multiplier`                 | 10.0  | `maximum_loss_per_trade`        | 0.0   |
| `tp_multiplier`                  | 1.0   | `bars_required_to_trade`        | 5     |
| `partial_take_profit_percentage` | 0.6   | `no_entry_minutes_before_close` | 0     |
| `trailing_stop_multiplier`       | 5.0   |                                 |       |

Every other filter is off. `regime_filter`, `volume_filter`, `compression_filter`, `trend_filter` and `higher_timeframe_filter` all read `7`, which is "off"; their threshold and period fields carry their defaults and are inert.

**Six of the twenty-three are the ones the grid varied** — `ema_period`, `fast_sma_period`, `error_margin`, `atr_length`, `partial_take_profit_percentage` and `trailing_stop_multiplier`. The rest are the archetype's own defaults, `sessions.EXIT_ON_CLOSE_SECONDS` governs the flatten, and §M41 settled that setting `ExitOnSessionCloseSeconds` in the C# is a free choice at this bar size.

What it did, on the two windows this file uses:

| held-out read                | trades | profit factor | session-close share | ambiguous share |
| ---------------------------- | -----: | ------------: | ------------------: | --------------: |
| swept bars, §M28.16's window |    300 |         1.553 |               0.243 |           0.000 |
| today's 60/40 split          |    314 |         1.505 |               0.247 |           0.000 |

On the swept-bar window it makes +$40,950 at a net-to-drawdown of 4.143 — third of the ten on both profit factor and net — and +$13,507 at 1.465 with its session-close legs removed, which is the highest residual net-to-drawdown of the ten.

**Through the accounts**, held out on today's split:

| preset                     | attempts | passes |  fees |     net | `days_to_payout` | `fees_per_pass` |
| -------------------------- | -------: | -----: | ----: | ------: | ---------------: | --------------: |
| TakeProfitTrader 25K Test  |       42 |     11 | 6,560 | +28,214 |           **26** |        **$596** |
| TakeProfitTrader 50K Test  |       31 |      9 | 6,066 | +26,876 |               61 |            $674 |
| Apex 50K                   |       22 |      3 | 7,905 | +25,266 |               61 |          $2,635 |
| TakeProfitTrader 150K Test |        6 |      3 | 6,222 | +22,060 |              130 |          $2,074 |
| Apex 150K                  |        2 |      1 | 7,555 | +26,755 |              374 |          $7,555 |
| TopStep 50K                |       68 |      6 | 5,010 | +14,653 |              125 |            $835 |
| TopStep 150K               |        8 |      1 | 4,619 | +11,498 |              364 |          $4,619 |

**Every one of the seven funds and every one is profitable after fees.** §M40's rule applies to the two objective columns and not to the rest: pick with them, do not quote them. The selection window promised 38 days and $566 on the preset this was chosen for.

### What pure objective ranking would have named instead

Dropping the exclusion constraint, `days_to_payout` names **combo 2023** — mean rank 1.9 across the seven presets, first on four of them, and identical to 2035 but for `atr_length` 3 rather than 14. Held out it returns a profit factor of 1.421 on 314 trades and is *profitable* without its session-close legs at 1.158 and +$9,460, but its residual net-to-drawdown is 0.736, so it fails the second of gate 4's two thresholds. It is the better choice for anyone who reads the exclusion as a decomposition and stops there, and it is worth carrying as the alternative because the two differ in one parameter.

Dropping the gate-4 constraint entirely widens it further: over the whole 432-row stratum, `fees_per_pass` puts configurations with a **selection-window profit factor of 0.909 and 0.952** at the top of two of the seven presets, and `days_to_payout` one at 0.959 at the top of a third. That is the reset economics at configuration granularity, one level below where §M40 found it, and it is why the pick carries a constraint at all.

## The two objectives disagree with each other, and with the exclusion in opposite directions

Over the gate-4 ten, each configuration's mean rank across the seven presets:

| rank correlation (Spearman, n = 10)        |    rho |
| ------------------------------------------ | -----: |
| `days_to_payout` vs `fees_per_pass`        | −0.085 |
| `days_to_payout` vs residual profit factor | −0.334 |
| `days_to_payout` vs residual net/drawdown  | −0.140 |
| `fees_per_pass` vs residual profit factor  | +0.383 |
| `fees_per_pass` vs residual net/drawdown   | +0.401 |

A lower mean rank is a better objective value, so a negative rho against a residual means the objective points *towards* the configurations that survive the exclusion.

**The two objectives barely agree with each other inside one cell** — rho −0.085 over ten configurations of one archetype at one bar size, where §M40 measured them as separately transferring across the registry. **And they point opposite ways at the exclusion**: being paid sooner goes weakly with a book that stands up without the forced flat, and a cheap pass goes weakly against it. The two configurations that clear both gate-4 thresholds are ranked 3rd and 6th by `days_to_payout` and **10th and 9th by `fees_per_pass`** — last and second to last.

**At n = 10 and |rho| under 0.41 these are directions and not findings.** What they are good for is the choice between the two objectives, which §M40 had already made on independent grounds: `days_to_payout` is the only one of the four that also raises net, and it is the one of the two that does not steer away from the configurations the exclusion leaves standing.

## What [#347] asked, answered

1. **InsideBarTrailing `phase=MIDDAY` is the candidate, and OpeningRange `phase=MIDDAY` is not.** The two objectives themselves are level on MNQ; held-out profit factor, net, session-close share and the exclusion are not, and neither is the size of the space each was ranked in. [#344]'s tie-breaker — a reconciled C# port against none — is not needed to decide it, which is the outcome that makes Phase 1 the cheap path rather than merely the preferred one.
2. **The cell is combo 2035**, stated above in full. Phase 1 needs the trading-window parameter [#349] describes and nothing else from the grid.
3. **The epic goes to Phase 1**, not Phase 2.
4. **MNQ, and not because of the entry.** At six contracts NQ leaves 12 to 42 points of room, and the profit-factor shortlist never passes an account on Apex 50K or TopStep 50K on either candidate.

## What this does not settle

- **Nothing here is a gate.** No matched null, no bootstrap, no walk-forward — those are §M28.16's and §M42's, measured on the bars they name. This ranks two cells that had already been through them.
- **The preset is a choice this file makes on the selection window and cannot make for anyone.** TakeProfitTrader 25K Test is the cheapest and fastest of the seven on the window that chose it; a different preset ranks a different configuration, and the per-preset tables above are there so that substitution is one row rather than a re-run.
- **`days_to_payout` is a floor.** The replay withdraws whenever a withdrawal is eligible, in full, and models no payout cadence or cap — `docs/roadmap.md` § "What is deliberately not modelled".
- **The 32-row fallback and the 432-row lead are not equally selected**, so the head-to-head counts are between one ranking and something closer to a whole cell.
- **The choice rule is this file's and was not pre-registered.** Constraining to §M42's ten and then to the exclusion survivors is two filters applied to a table that had already been read, which is the shape §M40 warns about; what it buys is that the named configuration is inside measured ground on every read the project has run, and what it costs is that "2035 leads `days_to_payout` among the survivors" is a description rather than a result.
- **Two configurations of ten survive the exclusion, and the median still does not.** §M42's reading is unchanged: this is the first cell where that question has a positive answer in it, not a settled one.
- **2026 is still the weakest year** (§M28.9, §M28.10), and none of this addresses it.
- **The three TakeProfitTrader PRO presets answer neither objective**, because a funded account has no target and no pass to time. They appear in the ten-preset replay and nowhere else.

Every figure here is one dated run over the archive as it stood on 2026-09-16, re-derivable from `results/campaign/*.duckdb` plus `tools/campaign_propaccount.py --rerun`, `tools/campaign_propobjectives.py` and `tools/campaign_exits.py --rerun` — not a standing property. The objective run's `verdict.csv` is the exception noted above: it reproduces §M40's in every column.

[#344]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/344
[#347]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/347
[#349]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/349
