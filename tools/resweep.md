# Re-sweeping every stored campaign

The commands that rebuild the nine campaign databases from scratch, in the order they run. A change that moves stored rows, such as a fill fix, leaves every stored control unable to reproduce itself, so every stored campaign is re-swept before a new one runs ([#439]).

**The list matches what the databases held on 2026-10-16**, checked by a dry run of every command against them: every stored cell comes from a command, and no command makes a cell that was not stored. A campaign stored after that date needs its command added here. Sets found only in databases moved aside before §M44 are not here: the ES, MES, GC and MGC sweeps, §M30's regime re-cut and §M32's volume-window ladder. [#439] lists them.

## Before you start

1. **Move `results/campaign/` aside** under another name, as §M44 did. The sweep skips a cell already stored, and `tools/campaign_sizing.py fit` keeps a cut already written, so neither would run again. Keep the old folder: the new rows are compared with it.
2. **Sync once, then run everything with `--no-sync`**, so nothing can replace numpy or numba while the sweeps run.

```bash
uv sync --locked
```

## The commands

Save this as a script and run it unattended, with its output redirected to a log. Set `N_JOBS` for the machine; it applies only to sweep calls large enough to use workers (`tools/README.md` § "campaign_sweep.py").

**It is safe to run again.** After an interruption or a failure, a second run skips every cell already stored and every cut already fitted, so it carries on where the first stopped. `set -e` stops it at the first command that fails.

```bash
#!/usr/bin/env bash
set -euo pipefail
N_JOBS=8
sweep() { uv run --no-sync tools/campaign_sweep.py --n-jobs "$N_JOBS" "$@"; }

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
for strategy in DeadCatBounce PullBackAndGo InsideBar InsideBarTrailing EmaCrossover \
                EmaPullback ElasticBand OpeningRange SqueezeBreakout; do
    uv run --no-sync tools/campaign_sizing.py fit --strategy "$strategy" --resolutions 5 10 15
done
sweep --strategies InsideBarTrailing --variants ibt-sizing --split --strata ibt-sizing --resolutions 5
sweep --variants confluence-sizing --split --strata confluence-sizing --resolutions 5 10 15

# Exits: §M48, §M49, §M50, each midday pass on the two #344 candidates
sweep --variants early-exit --split --strata early-exit --resolutions 2 5 10 15
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit --split --strata midday --resolutions 2 5 10 15
sweep --variants ibt-structure --split --strata ibt-structure --resolutions 5 10 15
sweep --variants early-exit-2 --split --strata early-exit-2 --resolutions 10 15
sweep --strategies InsideBarTrailing OpeningRange --variants early-exit-2 --split --strata midday --resolutions 10 15
```

Every flag is as the stored rows ran, which is not always as the campaign that first ran the set did:

- **`orb-fade` runs with `--extend-stored`, after `orb`.** Its unfiltered fade cells share their names with `orb`'s and hold both sets' stops, 0.25 to 1.0 and 0.02 to 0.25, which §M28.5 reads as one axis. Without the flag the sweep would skip them as stored.
- **No set runs `--regime-quantiles`**, because §M44 stored none. §M27.3, §M28.1 and §M28.2 ran fitted regime cells as well.
- **`elastic-volume` and `elastic-channel` run without `--volume-quantiles`**, because §M44 stored them at the raw cut. §M26.9 and §M33 ran them fitted.
- **The bar sizes are the stored ones**, so the gaps [#439] lists at 1, 2 and 5 minutes stay gaps.
- **The sizing fit is new.** It reads the current archive, so its cuts, and the arms built from them, can differ from the stored ones. Compare the cut files before comparing rows.

## Then InsideBar's `narrow` set

`narrow` is not in the script, because its entries are hand-read from the campaign rows: `NARROW_ENTRY` in `tools/campaign_sweep.py`, by the rule in `tools/README.md` § "Why the grids look the way they do". Once the script has finished, re-read them from the new `regime=DIRECTIONAL` rows. If any entry moved, change `NARROW_ENTRY` in a pull request first. Then run:

```bash
uv run --no-sync tools/campaign_sweep.py --variants narrow --split --strata narrow --resolutions 5 10
```

The stored rows hold 5 and 10 minutes only. Without `--resolutions` it also runs 2 and 15, which is [#439]'s separate `narrow` item.

**The stored 10-minute rows ran an older entry** (`slow_sma_period` 200, now 100), so those rows differ for that reason as well as any fill fix.

## Afterwards

Compare the new rows with the old. Only a campaign whose rows changed needs its reads and findings redone ([#439]).

[#439]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/439
