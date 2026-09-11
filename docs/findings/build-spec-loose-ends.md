---
title: "The build spec's three loose ends"
archetypes: [EmaCrossover]
issues: [74]
gates: []
outcome: spec
verdict: >-
  The trail is a ratchet over a different level, round numbers need a stated price basis, and the confluence count is refused at construction rather than gated by an axis.
---

# The build spec's three loose ends ([#74])

`docs/backtest_tool_spec.md` asks for three things nothing ever scheduled: a moving-average trailing stop as a per-run toggle, a stop that never sits exactly on a round number, and the confluence count — "at least 3 of 5 conditions" with the minimum itself swept — wired into an archetype rather than left as a tested primitive nobody calls. They are grouped because each is small, and they all land on **EmaCrossover**: it is the original archetype, so there is no NinjaScript to lose to and its trade log is nobody's reconciliation; it already carries a two-mode stop and it is the one archetype whose signal reads raw moving-average values. Every default is unchanged, and the trade-log gate is byte-for-byte identical across all fourteen files.

**None of the three has been measured.** They are axes an archetype can now be swept along, not findings, and §M27's rule applies: picking EmaCrossover back up needs a statement of what has changed since, and "it has three axes it did not have" is exactly such a statement — for that archetype and no other.

## The trail is a ratchet over a different level, and that is why it is not a third stop mode

The spec words it as two alternative stop-loss modes, structural or MA-trailing. Written that way it would have to replace `use_atr_stop` with a three-valued mode — renaming a swept axis in every stored results table and in the two shortlist arms `campaign_sweep.py` builds — or sit beside it as a second boolean, where the two on together is a cell in which one silently masks the other. That second shape is the **silent duplicate** `dead_axes` cannot see, the same one `ORB_STOP_OPPOSITE` under a fade was refused for.

So `trail_ma_stop` trails the stop the existing mode placed, rather than placing a different one: `(use_atr_stop, trail_ma_stop)` is a legal 2×2 and every cell is a distinct rule. A trailing stop starts somewhere and follows, so this is also the more faithful reading of the spec's own sentence, and it reaches the MA-trailing mode from the structural side in one combination.

**It advances at the close of every completed bar and never loosens**, which is DeadCatBounce's ratchet cadence rather than InsideBarTrailing's two-cadence one — and deliberately, because there is no C# here to inherit a cadence from and the ratchet is the cadence this codebase already establishes. `bracket.tightened_stop` is now the **one** ratchet: DeadCatBounce's candidate is a lagged bar's adverse extreme, EmaCrossover's is a moving average plus a cushion, and all either does with a candidate is refuse to loosen. A `nan` candidate — an average still inside its warm-up — leaves the stop alone, because every comparison against `nan` is false.

**The memory switch [#42] names was already on here, and what is gated is the third grid.** `needs_ma_values` is unconditional for EmaCrossover: its signal compares the raw fast and slow averages, so it has paid eight bytes an element per period since M18. What the trail adds is a *third* grid, and `crossover_context` builds it only where some combination in the sweep actually trails — the `ma_keys` set gains the `trail_ma` gate or it does not. `dead_axes` refuses `trail_ma_period`, `trail_ma_kind` and `trail_offset_ticks` as axes while nothing trails.

## Round numbers: an exact landing, and a price basis that has to be stated

**Only a stop that lands exactly on a multiple of `round_number_points` moves**, and it moves `round_number_offset_ticks` further from the entry. A zone around the level — "within n ticks of a round number" — is a second parameter the spec never asked for and a second thing to sweep; the spec says *never placed exactly at a round number*, and that is what is implemented. The rule reaches all three places a level is set: the ATR stop, the swing stop and the trailed stop. On the trail it runs **before** the ratchet, so pushing a candidate away from a round number can widen the candidate and never loosen the stop already in place.

**The hard part is not the arithmetic, it is that the rule is meaningless on the wrong bars.** Back-adjustment shifts every historical level by the accumulated roll offsets, so 20,000 on a back-adjusted series is not the 20,000 anyone traded, and a round-number rule run over one measures nothing while returning a perfectly ordinary-looking result. [#31] is what makes the rule testable at all: `dispersion.contract_frames` reloads each contract's bars raw, and a single-contract window contains no roll.

That is enforced rather than intended, and it **fails closed**. `context.prepare` takes a `price_basis`, `PriceBasis.UNKNOWN` is its default, and a combination setting `round_number_points` is refused on anything but `PriceBasis.RAW`. A caller who never said which series this is gets the refusal, not the benefit of the doubt — the shape `campaign_null.py` exits 2 for, where a check that could not run must not read as one that passed. Inferring the basis from the frame was rejected for the reason the reconciliation timezone was: an attribute that quietly fails to propagate is a guard that silently stops working, and the default would be the permissive one.

## The confluence count is refused at construction rather than gated by an axis

`conditions.count_true` has existed and been tested since M26 with no caller. `filters.context_gates` is what gives it one: the six context filters, as a list rather than a conjunction, so `apply_context_filters` ANDs them and `apply_confluence_filters` counts them. `confluence_required` is `REQUIRE_ALL` — zero — everywhere but EmaCrossover, and at `REQUIRE_ALL` the two functions are the same function, which is what keeps the pattern off the six archetypes that never asked for it.

**M is the number of *active* filters, and a gate at its everything value is not one of them.** That follows from the skip being a correctness rule rather than an optimisation: an efficiency-ratio warm-up bar, a session with no volume baseline and a bar no coarse bar has closed before each pass *no* mask, so an inactive gate entered as an all-true row would count on exactly the bars the skip exists for, and "2 of 3" would quietly become "2 of 6".

**A count of zero, or of the number of active gates, is the plain conjunction under another name**, and a count above that is unsatisfiable by construction — both are combinations a sweep would run identically to one it already has. Rather than add a case `dead_axes` cannot express, `validate_confluence` raises: legal values are `REQUIRE_ALL`, or 1 up to one below the number of filters the combination switches on, and fewer than two active filters admits nothing but `REQUIRE_ALL`. That puts the refusal at construction, where the message can say what the combination actually switched on.

[#31]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/31
[#42]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/42
[#74]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/74
