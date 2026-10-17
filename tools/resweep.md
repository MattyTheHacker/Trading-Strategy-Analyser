# Re-sweeping every campaign

The commands that rebuild the nine campaign databases from scratch and then sweep everything else the code can run, in the order they run. A change that moves stored rows, such as a fill fix, leaves every stored control unable to reproduce itself, so every stored campaign is re-swept before a new one runs ([#439]).

The script has four parts. **Part 1 is exactly what the databases held on 2026-10-16**, checked by a dry run of every command against them: every stored cell comes from a command, and no command makes a cell that was not stored. Its rows are the ones to compare with the old ones. Parts 2 to 4 add every sweep the stored campaigns never ran or no longer hold. Every command in them passes the tool's own checks. A campaign stored or pre-registered after that date needs its command added here.

| part  | what it sweeps                                                   | one F16as_v7           |
| ----- | ---------------------------------------------------------------- | ---------------------- |
| 1     | what the databases held on 2026-10-16                            | 13–19 h                |
| 2     | everything else at 2 to 15 minutes, on MNQ and NQ                | 49–73 h                |
| 3     | the campaign grids on ES, MES, GC, MGC and SI                    | 6–9 h                  |
| 4     | every set in parts 1 to 3 again at 1 minute, wherever it can run | 78–117 h               |
| total |                                                                  | 145–220 h, 6 to 9 days |

The estimates are for the machine chosen for the run: one Standard_F16as_v7, 16 cores on Linux. They apply each strategy's recorded seconds per combination and bar, at each bar size, to what each command plans, then take the machine as 6 to 9 times the development laptop at 2 workers: about 1.4 times for Linux, measured in PR #443, and the rest for its cores, which is assumed. Benchmark the machine before trusting them, by re-running PR #443's two passes on it. A machine with twice the cores takes about half the time. §M50 in every stratum is about half of part 2.

## Before you start

1. **Move `results/campaign/` aside** under another name, as §M44 did. The sweep skips a cell already stored, and `tools/campaign_sizing.py fit` keeps a cut already written, so neither would run again. Keep the old folder: part 1's rows are compared with it.
2. **Sync once, then run everything with `--no-sync`**, so nothing can replace numpy or numba while the sweeps run.

```bash
uv sync --locked
```

## The commands

Save this as a script and run it unattended, with its output redirected to a log. `N_JOBS` is one per core on an F16as_v7; change it with the machine. It applies only to sweep calls large enough to use workers (`tools/README.md` § "campaign_sweep.py").

**It is safe to run again.** After an interruption or a failure, a second run skips every cell already stored and every cut already fitted, so it carries on where the first stopped. `set -e` stops it at the first command that fails. Each part can also be stopped after, since nothing in a later part feeds an earlier one.

```bash
#!/usr/bin/env bash
set -euo pipefail
N_JOBS=16
STRATEGIES=(DeadCatBounce PullBackAndGo InsideBar InsideBarTrailing EmaCrossover
            EmaPullback ElasticBand OpeningRange SqueezeBreakout)
sweep() { uv run --no-sync tools/campaign_sweep.py --n-jobs "$N_JOBS" "$@"; }
fit() {
    for strategy in "${STRATEGIES[@]}"; do
        uv run --no-sync tools/campaign_sizing.py fit --strategy "$strategy" --resolutions "$@"
    done
}

# ---- Part 1: what the databases held on 2026-10-16 ----

# The campaign grids: the whole series, then both windows (§M44). Only the first runs 1 minute.
sweep --strata core
sweep --strata context --resolutions 2 5 10 15
sweep --split --strata core --resolutions 2 5 10 15
sweep --split --strata context --resolutions 2 5 10 15
sweep --split --strata volume-forms --volume-quantiles --resolutions 2 5 10 15

# Variant sets that need nothing but the campaign grids
for variants in hold spec emapullback-confirm emapullback-trail \
                elastic-shape elastic-volume elastic-channel elastic-recovery elastic-band-stop \
                orb orb-rejection orb-geometry orb-followthrough orb-bracket; do
    sweep --variants "$variants" --split --strata "$variants" --resolutions 2 5 10 15
done
# After orb: adds the tighter stops to the fade cells orb stored (§M28.5)
sweep --variants orb-fade --split --strata orb-fade --resolutions 2 5 10 15 --extend-stored

# Sizing: fit the cuts on the selection window first, then §M45, then §M47, which skips §M45's cells
fit 5 10 15
sweep --strategies InsideBarTrailing --variants ibt-sizing --split --strata ibt-sizing --resolutions 5
sweep --variants confluence-sizing --split --strata confluence-sizing --resolutions 5 10 15

# Exits: §M48, §M49, §M50, each midday pass on the two #344 candidates
sweep --variants early-exit --split --strata early-exit --resolutions 2 5 10 15
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit --split --strata midday --resolutions 2 5 10 15
sweep --variants ibt-structure --split --strata ibt-structure --resolutions 5 10 15
sweep --variants early-exit-2 --split --strata early-exit-2 --resolutions 10 15
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit-2 --split --strata midday --resolutions 10 15

# ---- Part 2: everything else at 2 to 15 minutes, on MNQ and NQ ----

# Campaigns pre-registered and never run: §M52, §M53, §M55, §M56, §M26.7, §M57, §M58
sweep --variants early-exit-3 --split --strata early-exit-3 --resolutions 5 10 15
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit-3 --split --strata midday --resolutions 5 10 15
sweep --variants emapullback-ma-trail --split --strata emapullback-ma-trail --resolutions 2 5 10 15
sweep --strategies EmaCrossover --variants side-count --split --strata side-count --resolutions 2 5 10 15
sweep --split --strata slot --resolutions 2 5 10 15
for variants in elastic-invert elastic-noise; do
    sweep --strategies ElasticBand --variants "$variants" --split --strata "$variants" --resolutions 2 5 10 15
done
sweep --strategies SqueezeBreakout --variants squeeze-latch --split --strata squeeze-latch --resolutions 2 5 10 15

# Passes the first campaigns ran that §M44 did not store
sweep --split --strata regime --regime-quantiles --resolutions 2 5 10 15                     # §M30, and §M38's open arms
for pair in "0.10 0.90" "0.33 0.67"; do                                                      # §M31
    sweep --strategies OpeningRange --split --strata directional --regime-quantiles $pair --resolutions 2 5 10 15
done
sweep --split --strata volume-forms --volume-quantiles --volume-forms ROLLING \
      --volume-rolling-bars 10 90 --resolutions 2 5 10 15                                    # §M32
sweep --split --strata volume-forms --volume-quantiles --volume-baseline-sessions 10 40 --resolutions 2 5 10 15
for variants in elastic-volume elastic-channel; do                                           # §M26.9, §M33
    sweep --variants "$variants" --split --strata "$variants" --volume-quantiles --resolutions 2 5 10 15
done
sweep --variants orb --strata orb --resolutions 2 5 10 15                                     # §M28.2, the whole series
for variants in orb orb-fade orb-rejection; do                                               # §M28.2, §M28.5, §M28.7
    sweep --variants "$variants" --split --strata "$variants" --regime-quantiles --resolutions 2 5 10 15
done

# Bar sizes, arms and strata the stored campaigns left out
sweep --variants early-exit-2 --split --strata early-exit-2 --resolutions 5                   # §M50 at 5
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit-2 --split --strata midday --resolutions 5
sweep --variants ibt-structure --split --strata ibt-structure --resolutions 2                 # §M49 at 2
sweep --variants ibt-structure-ends --split --strata ibt-structure-ends --resolutions 5 10 15 # §M49's ladder ends
sweep --strategies InsideBarTrailing --variants ibt-sizing-high --split \
      --strata ibt-sizing-high --resolutions 5                                               # §M45 above a half
fit 2
sweep --variants confluence-sizing --split --strata confluence-sizing --resolutions 2         # §M47 at 2
sweep --variants emapullback-trail --split --strata volume-forms --volume-quantiles \
      --resolutions 2 5 10 15                                                                # §M37 in §M36's cells
sweep --split --strata volume-forms --volume-quantiles --volume-forms ROLLING \
      --volume-rolling-bars 2 3 5 7 --resolutions 2 5 10 15                                  # §M32 below 10
sweep --variants early-exit-2 --split --strata all --resolutions 5 10 15                      # §M50 in every stratum

# ---- Part 3: the campaign grids on the other markets ----

sweep --roots ES MES GC MGC SI --strata all --resolutions 2 5 10 15
sweep --roots ES MES GC MGC SI --split --strata all --resolutions 2 5 10 15

# ---- Part 4: every set above again at 1 minute ----

one_minute() { sweep "$@" --resolutions 1; }
one_minute --strata context
for strata in core context; do one_minute --split --strata "$strata"; done
one_minute --split --strata volume-forms --volume-quantiles
for variants in hold spec emapullback-confirm emapullback-trail \
                elastic-shape elastic-volume elastic-channel elastic-recovery elastic-band-stop \
                orb orb-rejection orb-geometry orb-followthrough orb-bracket; do
    one_minute --variants "$variants" --split --strata "$variants"
done
one_minute --variants orb-fade --split --strata orb-fade --extend-stored
fit 1
one_minute --strategies InsideBarTrailing --variants ibt-sizing --split --strata ibt-sizing
one_minute --strategies InsideBarTrailing --variants ibt-sizing-high --split --strata ibt-sizing-high
one_minute --variants confluence-sizing --split --strata confluence-sizing
for variants in early-exit early-exit-2 early-exit-3; do
    one_minute --variants "$variants" --split --strata "$variants"
    one_minute --strategies InsideBarTrailing OpeningRange --variants "$variants" --split --strata midday
done
for variants in ibt-structure ibt-structure-ends emapullback-ma-trail; do
    one_minute --variants "$variants" --split --strata "$variants"
done
one_minute --strategies EmaCrossover --variants side-count --split --strata side-count
one_minute --split --strata slot
for variants in elastic-invert elastic-noise; do
    one_minute --strategies ElasticBand --variants "$variants" --split --strata "$variants"
done
one_minute --strategies SqueezeBreakout --variants squeeze-latch --split --strata squeeze-latch
one_minute --split --strata regime --regime-quantiles
for pair in "0.10 0.90" "0.33 0.67"; do
    one_minute --strategies OpeningRange --split --strata directional --regime-quantiles $pair
done
one_minute --split --strata volume-forms --volume-quantiles --volume-forms ROLLING --volume-rolling-bars 10 90
one_minute --split --strata volume-forms --volume-quantiles --volume-baseline-sessions 10 40
one_minute --split --strata volume-forms --volume-quantiles --volume-forms ROLLING --volume-rolling-bars 2 3 5 7
for variants in elastic-volume elastic-channel; do
    one_minute --variants "$variants" --split --strata "$variants" --volume-quantiles
done
one_minute --variants orb --strata orb
for variants in orb orb-fade orb-rejection; do
    one_minute --variants "$variants" --split --strata "$variants" --regime-quantiles
done
one_minute --variants emapullback-trail --split --strata volume-forms --volume-quantiles
one_minute --variants early-exit-2 --split --strata all
one_minute --roots ES MES GC MGC SI --strata all
one_minute --roots ES MES GC MGC SI --split --strata all
```

What to know about the flags:

- **Part 1 runs every set as the stored rows ran**, which is not always as the campaign that first ran it did. §M44 stored no `--regime-quantiles` cell and ran `elastic-volume` and `elastic-channel` at the raw cut. Part 2 adds the fitted passes.
- **`orb-fade` runs with `--extend-stored`, after `orb`.** Its unfiltered fade cells share their names with `orb`'s and hold both sets' stops, 0.25 to 1.0 and 0.02 to 0.25, which §M28.5 reads as one axis. Without the flag the sweep would skip them as stored.
- **The sizing fit is new.** It reads the current archive, so its cuts, and the arms built from them, can differ from the stored ones. Compare the cut files before comparing rows.
- **§M38's open arms need no command of their own.** Its 5-minute range under the ATR stop and the width target are in OpeningRange's campaign grid, so the §M30 pass sweeps them in the fitted cell §M38 read.
- **Three choices were made for this list on 2026-10-16:** the rolling window below 10 bars runs at 2, 3, 5 and 7; §M30's and §M32's passes run on all nine strategies, where they first covered seven; and every set runs at 1 minute.

Nothing here reads a campaign. Every gate, null and prop-account replay, §M54, §M59 and §M60 included, runs after its sweep.

## Then InsideBar's `narrow` set

`narrow` is not in the script, because its entries are hand-read from the campaign rows: `NARROW_ENTRY` in `tools/campaign_sweep.py`, by the rule in `tools/README.md` § "Why the grids look the way they do". Once part 1 has finished, re-read them from the new `regime=DIRECTIONAL` rows. If any entry moved, change `NARROW_ENTRY` in a pull request first. Then run:

```bash
uv run --no-sync tools/campaign_sweep.py --variants narrow --split --strata narrow --resolutions 2 5 10 15
uv run --no-sync tools/campaign_sweep.py --variants narrow --split --strata narrow --regime-quantiles --resolutions 2 5 10 15
```

The first reproduces the stored 5 and 10 minutes and adds 2 and 15. The second is §M27.3's fitted cell. There is no 1-minute entry to run.

**The stored 10-minute rows ran an older entry** (`slow_sma_period` 200, now 100), so those rows differ for that reason as well as any fill fix.

## Afterwards

Compare part 1's rows with the old ones, with OLD the folder moved aside before the run:

```bash
uv run --no-sync tools/campaign_compare.py OLD results/campaign/ --out cells.csv
```

It opens the databases read-only, so run it once the script has stopped, or against a copy taken when part 1 finished. Every stored cell comes back `identical`, `changed` or `old only`; `narrow`'s cells are `old only` until it runs, and any other is a stored cell part 1 did not reproduce. Cells the later parts added are `new only` and do not fail it. Only a campaign whose rows changed needs its reads and findings redone ([#439]). `tools/README.md` § "campaign_compare.py" says what is compared.

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
