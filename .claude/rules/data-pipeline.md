---
paths:
  - "nqbt/ingest.py"
  - "nqbt/archive.py"
  - "nqbt/splice.py"
  - "nqbt/resample.py"
  - "nqbt/sessions.py"
  - "nqbt/paths.py"
  - "nqbt/cli.py"
  - "tools/**"
  - "tests/test_ingest.py"
  - "tests/test_archive.py"
  - "tests/test_splice.py"
  - "tests/test_sessions.py"
  - "tests/test_resample.py"
---

# Data, bars and contract rolls

## Sources

- **`data/archive/` is the durable union and the only thing ingestion reads.** Exports are
  moving windows, not snapshots: NT8 serves each contract for a limited period and drops the
  tail once it expires, so a folder of exports loses history over time. `archive.py` merges
  `data/minute/` (manual) and `data/addon/` (AddOn) into it. **Never point a real ingest at a
  source folder** — `ingest` mirrors its input exactly, so it would propagate the loss into the
  cache.
- **The two sources compound, and the order matters.** The AddOn reaches further back but stops
  at the turn of the expiry month; a manual export holds only the last few months through
  expiry. The AddOn's requests warm NinjaTrader's own local database, so **running the AddOn
  and then re-exporting manually** returns the full contract life from one source.
- **A manual export regenerates the file; it does not append.** Bars get revised between
  exports and occasionally withdrawn. Ingest hashes the **whole consumed byte range** to tell
  an append from a rewrite — a head-only hash calls a rewrite an append, which freezes stale
  bars and silently drops real ones.
- **The last bar of any export may be mid-formation**, with a high and close that have not
  happened yet. The archive merge lets a file's newest bar insert but never overwrite.
- **Every folder under `data/` uses the `.Last.txt` suffix**, including `data/tick/`, whose
  files are a different format and orders of magnitude larger. **Never glob across
  resolutions**; `parse_export` hard-fails on a tick file.

## Rolls

- **Handover ratios must be read against `shared_bars`.** A ratio computed off a 60-bar stub is
  not a session and has been mistaken for one.
- **A stub session cannot decide a roll.** Both roots hold only the Sunday 18:00-19:00 ET hour
  for one trading day a few days before most rolls, and that lands exactly where the crossover
  is judged. Sessions below half the median shared-bar count are marked `conclusive=False` and
  skipped.
- **Run the two roots against each other.** They roll identically almost everywhere, and the
  one disagreement was the stub bug above. It is the cheapest correctness check available and
  needs no NT8.
- **Correct roll dates cost bars.** The front contract now supplies days an early roll gave to
  the back contract, and NT8's data has holes there. They were always missing; an early roll
  hid them behind the wrong contract. **Do not fill them from the neighbouring contract** —
  that splices two different prices into one session.
- Volume-crossover rolls are no longer undetectable once the AddOn has warmed the database;
  `docs/nt8-fidelity.md` § "Contract data" has the current agreement figures.
- **A seam carries no contract basis, so anything that jumps there is a real move over a real
  gap** — usually the missing session above rather than the maintenance break.
  `splice.roll_seams` reports each seam with the gap it spans; `docs/nt8-fidelity.md`, "True
  Range at a roll boundary".

## Time and bars

- **A bar is labelled by the minute it covers, not the minute it is stamped at.** Timestamps
  are end-of-bar, so a bar stamped 09:30 is the pre-open and the first cash-open bar is stamped
  09:31. Invisible at 1 minute and wrong everywhere else. Bar timestamps in `data/archive/` are
  **end-of-bar, UTC**.
- **Bucket by minutes since the session open, never wall clock**, and note the usual
  justification is wrong: agreement with a midnight-anchored grid needs **N to divide 60**.
  Dividing 1,080 is not sufficient. `docs/roadmap.md` §M13.
- **Bar of session is clock-derived, never counted off the data** — an ordinal count renumbers
  everything after a hole, so index *k* would mean a different time of day in different
  sessions.
- **Resampling is exact, not approximate** — OHLC aggregation is associative, so a 5-minute bar
  built from five 1-minute bars is bit-identical to one NT8 builds from ticks. Do not reach for
  `data/tick/`; that is the more-precise-than-NT8 error.
- **Out-of-session stray prints are dropped where the cache becomes a bar frame.**
  `ingest.load_contract` filters, so a per-contract frame and a spliced one hold the same bars
  and `[n]` means the same thing in both. The Parquet cache itself stays lossless — it is the
  only place the raw export can be reconstructed from. Above `ingest.STRAY_SHARE_LIMIT` the
  load **raises**: that is a broken export or the wrong session template, not strays, and
  filtering it would hide the problem. `docs/nt8-fidelity.md` § "Sessions".

## Reconciling against NT8

- **NT8 trade-list exports are in the machine's display timezone (`Europe/London`), not UTC.**
  They only look like UTC over a winter window. Over a summer window the export is BST and
  every trade is an hour out. `tools/reconcile_nt8.py` handles it.
- **Annotate real trades against the raw series, never the back-adjusted one.** The lookup
  succeeds and every comparison is silently wrong. `docs/roadmap.md` §M11.
- **Do not check a reconciliation by leg count.** Leading history legitimately adds signals and
  `trade_id` shifts after any earlier removal, so join on `(entry_time, leg)`.
- `verification/nt8_reconciliation_MNQ_03-24.csv` is a **pre-fix** run despite its name; read
  `verification/README.md` first. The whole folder is **gitignored and exists only on this
  machine** (#91).
