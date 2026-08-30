# Contributing to nqbt

This file is the working agreement: how code, tests, commits and pull requests are expected to look, and the few rules that are not negotiable.

Read [`README.md`](README.md) first for what the project is and the traps that have already cost real time. The two documents do not overlap: that one is about *this codebase*, this one is about *how to change it*.

## The prime directive

**Match NinjaTrader 8's default fidelity exactly — do not exceed it.** Being more precise than NT8 is as much a bug as being less precise, because it makes Tier 1 and Tier 2 disagree in ways that cannot be attributed.

This governs `nqbt/sim/` and everything feeding it. Before changing anything there, read [`docs/nt8-fidelity.md`](docs/nt8-fidelity.md) — it records every NT8 rule the simulation implements and the evidence for it. When the C# and intuition disagree, the C# wins; when the C# and a real NT8 trade list disagree, the trade list wins.

## Where reasoning goes

**Reasoning belongs in `docs/`, not in the source.** ([#105])

Code should be readable on its own terms. Prefer a clearer name, a smaller function or an intermediate variable over a comment explaining an unclear one.

- **Docstrings say *what* a thing is and how to use it**, and stay short. One line is often enough; a paragraph is plenty.
- **A comment is fine where something is genuinely non-obvious** — a subtle index, a deliberate deviation from what a reader would expect, a workaround. Use them sparingly, and only where the code's behaviour departs from what a competent reader would predict.
- **Arguments, justifications, measurements, decision records, history and traps go in `docs/`**, with at most a one-line pointer from the code.

Two homes, and they are not interchangeable:

| goes in                                        | what it holds                                                                     |
| ---------------------------------------------- | --------------------------------------------------------------------------------- |
| [`docs/nt8-fidelity.md`](docs/nt8-fidelity.md) | every NT8 rule the simulation reproduces, and the evidence that established it    |
| [`docs/roadmap.md`](docs/roadmap.md)           | planned work in dependency order, the reasoning behind it, and the standing traps |

A pointer must name a section that exists, in the form the source already uses:

```text
``docs/roadmap.md`` §M17
``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the open"
```

A bare "see the docs" is not a pointer.

## Naming

**Variables must be named so their purpose is obvious at a glance.** A name that needs a comment to explain it is the wrong name. `handover_ratio` and `bars_required_to_trade` are right; `hr` and `n2` are not.

Two exceptions, both deliberate:

- **Inside an `@njit` loop**, short conventional indices (`i`, `j`, `leg`) are clearer than long ones and match the surrounding code.
- **Where a name mirrors a NinjaScript property**, keep NT8's word so the two can be diffed by eye — `tp_multiplier` for `TPMultiplier`, `ambiguity_policy` for a concept NT8 has no name for.

Match the surrounding code's idiom. A module written one way should not acquire a second style because a new function arrived.

## Control flow

**Guard clauses, not nesting.** Invert the condition and leave early, so the work a function exists to do sits at one indent level instead of inside an `if`.

```python
# not this                             # this
def annotate(trade, bars):             def annotate(trade, bars):
    if trade is not None:                  if trade is None:
        if trade.entry_bar in bars:            return None
            return context_at(trade)       if trade.entry_bar not in bars:
    return None                                return None
                                           return context_at(trade)
```

- **`return`, `continue`, `break` and `raise` are all guards.** Inside a loop, `if not leg_open[leg]: continue` beats wrapping the body in `if leg_open[leg]:`.
- **No `else` after a branch that leaves.** ruff's `RET505`–`RET508` catch this one form and report zero on `nqbt/` today; keep it that way. **They catch nothing else in this section** — a body wrapped in a positive `if` is invisible to every lint rule, so review is the only check on it.
- **Validate first, then work.** Every `raise` for a bad argument belongs above the first line of real work — `validate_thresholds` in `nqbt/regime.py` is the shape.
- **Depth is a signal, not only a fault.** Three levels usually means the function is doing two things, and extracting the inner one beats flipping conditions around it.

Two exceptions, both deliberate:

- **Where inverting costs clarity, do not.** A single `if a and b:` reads better than two negated guards when neither half means anything on its own, and `if not disabled:` is worse than the nesting it removed.
- **Inside `@njit` code, reshaping control flow is a gated refactor.** numba also requires every return path to agree on type, so an added early `return` is not free. See ["The trade-log regression gate"](#the-trade-log-regression-gate).

## Tests

**Everything is tested unless there is a good reason not to**, and the reason goes in the test file or the pull request, not left implicit.

Aim to cover three kinds of case for anything non-trivial:

1. **Normal operation** — the input the function exists for.
2. **Unusual operation** — an empty series, a single bar, a session with a hole, a period longer than the data, a boundary where two conditions are exactly equal.
3. **Exception operation** — the inputs that must raise, asserted on the *specific* exception type and, where the message is the point, on its content.

Further expectations:

- **A test must be able to fail.** Verifying the gate can fail is part of using it.
- **Pin the property, not the transcript.** Assert that deleting three bars from a session leaves every remaining bar's index unchanged, rather than asserting a list of numbers that happens to be today's output.
- **A timezone test must assert both halves.** "These bars carry the same Eastern minutes" is a tautology over a UTC implementation; it needs "and their UTC minutes differ" beside it.
- **Name the test after the claim** it makes. `test_the_two_summary_paths_agree_exactly` says what breaking it means; `test_summary_2` does not.

### Coverage

**At least 85%** on new work. Check with the JIT disabled before concluding anything is untested:

```bash
NUMBA_DISABLE_JIT=1 ./.venv/Scripts/python.exe -m pytest --cov=nqbt --cov-branch
```

`coverage.py` cannot see inside `@njit`-compiled functions — numba runs machine code, so the Python bytecode never executes and every line reads as missed. The raw figure runs roughly 14 points low for that reason alone. CI runs both jobs: one with the JIT active, which is the real functional test, and one with it disabled, which is the accurate coverage measurement.

**Do not set `NUMBA_DISABLE_JIT=1` on the main test job** to make the number look better. That would stop CI ever exercising the compiled path, trading verification of fidelity-critical code for a metric.

Use `--cov=nqbt`, not a bare `--cov`, which includes `tests/` and inflates the total.

## Linting and typing

```bash
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/ruff check .
./.venv/Scripts/ruff format --check .
./.venv/Scripts/mypy nqbt
./.venv/Scripts/pymarkdown scan $(git ls-files '*.md')
./.venv/Scripts/python.exe -m mdformat --check .
```

CI runs `pymarkdown scan --recurse .`, which is fine on a clean checkout but usually noisy locally because it includes `.venv` and the gitignored notes under `docs/`. Scan the tracked files instead. `mdformat` takes a bare `.` in both places because its exclusions live in [`.mdformat.toml`](.mdformat.toml) rather than on the command line.

**`ruff` and `mypy` must report no errors.** CI gates `ruff check nqbt`, `ruff format --check .` and `mypy nqbt`, so either one failing fails the build. `tests/` and `tools/` are **not** at zero for either tool and are not gated; running them over the whole tree is still worth doing, but only the package's count has to stay at zero.

Every entry in `[tool.ruff.lint] ignore` and `per-file-ignores` carries a one-line reason, and so does every `# noqa` and every `# type: ignore`. Add none of them without one. Put the reason **after the pragma on the same line, however long that makes the line**, so that grepping for a bare `# noqa: X$` finds anything undocumented. `warn_unused_ignores` is on, so an ignore that stops being needed fails the build rather than lingering.

### Local variables carry their type too

**Annotate a local at its first binding**, with the same aliases the signatures use. A name can only be annotated once per scope, so that first binding is the declaration for the whole function; where a name is bound in two arms of a branch, declare it bare above the branch rather than typing one arm and not the other.

Leave a local bare where the type cannot be stated honestly: a `pd.Series` whose dtype belongs to the caller, `json.loads`, duckdb rows, joblib. `disallow_any_explicit` rejects those anyway, and **a `# type: ignore` per local to say "unknown" is worse than no annotation** — it is a pragma with nothing to fix. Leave it bare, too, where mypy's inference and the runtime disagree, and say which in a comment; numpy types `datetime64 + timedelta64` as `timedelta64`, and `nqbt/sessions.py` has the site.

`nqbt/arrays.py`'s `AnyArray` is **not** a wildcard. It is a concrete `dtype[generic[object]]`, so a local annotated with it type-checks at the assignment and then fails at every later use. Name the real dtype — the expression almost always states it — or leave the local bare.

In almost all cases errors reported by either `ruff` or `mypy` should be fixed rather than hidden with ignore comments. Errors should only be ignored if they are a genuine misfire or there's an extremely good reason the issue shouldn't be fixed.

### Dependencies are pinned exactly

Every entry in `dependencies` and the `dev` extra is `==`, not `>=`. CI resolves a fresh environment on every run, so a range means an upstream release nobody chose decides whether the build passes — which is exactly how numpy 2.5 broke the mypy gate on the run after it landed, and `extend-select = ["ALL"]` gives ruff the same reach. Dependabot raises the bumps daily, grouped into one pull request. **Do not relax a pin to make an install resolve** — take the dependabot bump instead, or pin the version that works and say why.

**Treat a bump to numpy, numba, pandas or pyarrow as a change to `nqbt/sim/`**, because it is one: it reaches the simulation without touching a file in it, so nothing else will prompt you to check. CI carries the three pins that need no data — `tests/test_rng_stream_pins.py`, `tests/test_numeric_pins.py` and `tests/test_parquet_round_trip.py` — and a failure in any of them is a finding to explain, never a value to re-pin. They are canaries and not the gate: the trade-log gate and the NT8 reconciliation still need `data/` and `verification/` and still run locally. See [`docs/roadmap.md`](docs/roadmap.md) § "What CI can gate on a dependency bump".

### Lint changes are not exempt from review

A "ruff auto-fix" pull request once reached into an `@njit` loop and rewrote `simulate_deadcat`'s MAE/MFE tracking, and inverted the branch in `archive.py` implementing "the newest bar may insert but never overwrite". Both were equivalent on inspection — and inspection is not the gate.

**Read what an auto-fixer touched under `nqbt/sim/` before merging, not after**, and run the trade-log gate over it. A lint pull request is the last place anyone looks for a simulator change.

### Markdown

**Two tools run over the Markdown and they do different jobs.** `pymarkdown` is the linter — duplicate headings, bare URLs, a fence with no language, an empty link. `mdformat` is the formatter: it reparses each file and re-emits it canonically, which covers paragraph reflow, table padding, list markers and link-reference ordering. Neither substitutes for the other. `pymarkdown` **cannot** be configured to do `mdformat`'s job, because no rule exists for most of it — it has no table rules at all, and `MD013` measures line length without being able to fix it.

**When the Markdown job fails, run this and commit the result:**

```bash
./.venv/Scripts/python.exe -m mdformat .
```

**Do not override either setting on the command line.** Both live in [`.mdformat.toml`](.mdformat.toml), which `mdformat` discovers from the repository root, and both replace a default that would rewrite every file: `wrap = "no"` is the house style — **prose is not hard-wrapped; one line per paragraph, blank line between** — where the default, `keep`, reflows nothing, and `number = true` keeps ordered lists at `1./2./3.` where the default flattens every item to `1.`. A flag beats the file, so one run with `--wrap keep` undoes the style for everything it touches.

`MD029` is set to `ordered` to catch that second case from the other side. Its default, `one_or_ordered`, accepts both numbering styles, so `pymarkdown` alone would pass a file whose ordered lists had all been flattened to `1.`.

**`.claude/rules/*.md` are excluded and must stay excluded.** They carry `paths:` front matter, no front-matter plugin is installed, and formatting them rewrites the delimiters into a thematic break and a bullet list — after which the rules stop loading for the files they cover, and nothing reports it. That exclusion is why those files are still hard-wrapped while everything else is not.

## The trade-log regression gate

**Anything touching `nqbt/sim/`, `nqbt/context.py`, `nqbt/trades.py` or `nqbt/stats.py` must prove it did not move a number.**

```bash
./.venv/Scripts/python.exe tools/capture_trade_logs.py before
# ...make the change...
./.venv/Scripts/python.exe tools/capture_trade_logs.py after
./.venv/Scripts/python.exe tools/compare_trade_logs.py before after
```

Fourteen files across four producer paths. A refactor meant to preserve behaviour must reproduce every one of them; a change that adds a column must leave every other column identical (`--added <name>`).

Points that have each cost time:

- **Read "identical" as numerical, not textual.** Multiplying by `-1.0` sends `0.0` to `-0.0`, which is a different eight bytes and an equal number. `assert_frame_equal(check_exact=True)` is the right comparison and a file hash is too strict.
- **`sha256sum` is a cross-check, not the gate.** Use it to catch the gate itself being broken — it is code, and it has been wrong — but when the two disagree, find out which kind of difference it is before believing either.
- **A change that *should* move numbers still runs the gate.** The point is to see exactly which files moved and to be able to say why.

## Commits

- **The subject begins with one of ten verbs.** `Add`, `Bump`, `Document`, `Fix`, `Move`, `Port`, `Reconcile`, `Refactor`, `Remove`, `Update` — and nothing else. A milestone tag, a filename or a bare capitalised word is not a prefix either: `M17.4 -- sweep_axes takes resolution`, `Docs: record the findings` and `instruments.py: route every figure` are all rejected.
- **Subject line at most 72 characters as it lands**, the space and `(#N)` GitHub appends included. That is where GitHub splits the subject and moves the remainder into the body, and a subject that has to be expanded to be read is a subject nobody reads. It leaves about 65 characters to write in.
- **Aim for 55, which the linter warns past.** The repository's file table clips the subject long before 72, and it clips on pixel width in a proportional font rather than on a character count — so a capital-heavy subject goes first, and no monitor is wide enough to help, because the page is capped at a fixed content width. Measured there: `Update the PR body rules for what lands on main (#174)` fits at 53 characters and `Add a commit-message linter and gate what lands on main (#165)` is clipped at 61. **The rule is a warning and never fails a run**, because the last few characters sometimes cost more in clarity than the clip costs in a table.
- **A body is for when the subject genuinely cannot carry it.** Leave a blank line after the subject and explain *why* rather than restating the diff.

**Body line length is deliberately not a rule.** **PR and issue bodies are never hard-wrapped here** — one line per paragraph, blank line between. The body that reaches `main` is the pull request description, and the squash merge wraps it on the way in, so a commit on `main` reading at about 70 columns is that automatic wrap and not a body someone hand-wrapped. Hard-wrapping the source of it would be wrapping twice. That is a rendering question, not a linting one. The 80-column convention was dropped rather than compromised, because holding both at once is impossible.

### The ten verbs

| verb        | for                                                                                                                |
| ----------- | ------------------------------------------------------------------------------------------------------------------ |
| `Add`       | a new capability, file, test or guard — also what `implement`, `introduce`, `create`, `store` and `support` become |
| `Fix`       | a defect corrected, including one found against NT8                                                                |
| `Update`    | an existing thing changed — `change`, `modify`, `set`                                                              |
| `Remove`    | a deletion — `drop`, `delete`                                                                                      |
| `Refactor`  | structure changed, behaviour held — `simplify`, `clean up`, `reduce`                                               |
| `Move`      | relocated or renamed — `migrate`, `rename`                                                                         |
| `Document`  | docs, README, roadmap, decision records — `record`, `plan`, `note`                                                 |
| `Bump`      | a dependency version, which is mostly Dependabot's                                                                 |
| `Port`      | NinjaScript translated into Python — a Tier 1/Tier 2 term, not a synonym for `Add`                                 |
| `Reconcile` | checked against a real NT8 trade list — also `pin`, as in pinning an indicator against NT8                         |

`Port` and `Reconcile` are here because the prime directive needs them: "Port InsideBar.cs as the third C#-backed archetype" is not `Add`, and "Reconcile InsideBar against its NT8 trade list" is not `Fix`. The other eight are generic.

**Mood is settled by construction, not by a heuristic.** The vocabulary lists base forms only, so `Added`, `Adds`, `Adding`, `Built` and `Rewrote` fail because they are not in it — there is no stemmer, no wordlist of non-imperative forms, and no dependency on ruff. The measured cost: a precise but unlisted verb has to be rephrased, so `Gate dependency bumps in CI with three pins` becomes `Add three pins to gate dependency bumps in CI`. That is the trade — scannability bought with a little precision.

**Only the squashed result is checked.** `main` takes squash merges only, so the branch's own commits never land — the subject that reaches `main` is the pull request title. CI assembles the title and body the way GitHub will and runs [`tools/lint_commit_messages.py`](tools/lint_commit_messages.py) over that, and over nothing else. The rules above therefore bind the **pull request title**; a branch commit can say whatever gets you through the afternoon.

Check a title before you use it:

```bash
echo "Add the phase filter to the sweep axes" | ./.venv/Scripts/python.exe tools/lint_commit_messages.py --stdin
```

Two things the rules above do not say, each of which has already cost a commit:

- **GitHub appends a space and `(#N)`, and it counts.** Two subjects on `main` were written to exactly 80 and pushed past it by the number. The check measures the subject as it lands.
- **Dependabot's titles are exempt from the length rule and the prefix warning.** It writes its own, they run past 72, and it could not act on either. They are no more ours to control than a `Merge` or `Revert` subject is.

**A Conventional Commits prefix is accepted but not recommended.** `fix(sim): derive the session end` passes and raises a warning; one of the ten verbs is the house style. Only the eleven types the spec names are recognised — `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. **The type stands in for the verb**, so the word after the colon is unconstrained; `fix(sim): derive the session end` is fine even though `derive` is not one of the ten. Anything else before a colon is not a prefix at all, it is a subject that fails to start with one of the ten.

Why accepted rather than required: measured over the last 100 commits of 32 major repositories, adoption is bimodal and tracks tooling rather than quality. The JavaScript and TypeScript projects that generate changelogs and semver bumps from commit types sit at 91-100%; everything else — Django, Rails, Go, Rust, NumPy, pandas, scikit-learn, Kafka, the kernel — sits at or near zero. `nqbt` publishes nothing and has no changelog, so the prefix buys nothing here.

Why ten verbs rather than a mood check: mapping every subject in this repository's history onto a canonical set condensed 83% of them into these ten, and the residue was the milestone-tagged subjects that carry no verb at all. Five verbs — `Add`, `Document`, `Update`, `Bump`, `Refactor` — covered 70 of the 80 that mapped.

## Pull requests

- **The body briefly explains the change**: what moved, and the reasoning a reviewer would otherwise have to reconstruct. Detailed argument still belongs in `docs/` — link to the section rather than duplicating it.
- **State how it was verified, and keep it to a line.** Name what was run and what it returned — `trade-log gate: BYTE-FOR-BYTE IDENTICAL across all 14 files`, `tools/reconcile_nt8.py` against the MNQ 03-24 export: `RECONCILED`. A claim carries its number; it does not carry the transcript that produced it. **Raw output — the gate's fourteen lines, a coverage table, a reconciliation's per-field agreement — belongs in `docs/` or nowhere**, because the body lands on `main` as the commit description and a pasted run cannot be re-checked from there anyway.
- **Repeat the closing keyword for every issue.** `Closes #1, #2` links only `#1`. Write `Closes #1. Closes #2.` and check `closingIssuesReferences` on the pull request before merging. Alternatively, link the issues manually via the GUI.
- **Do not quote figures that go stale.** Consider if the number is even needed in documentation or if it's better being generated or retrieved at the time it's needed. If it's definitely needed, point at the document that holds the live number.
- **Branch off `main` and never commit to it directly.**
- **Use labels to accurately describe what areas the PR covers.**
- **PRs should ideally be as minimal as possible to make the review easier.**

## Data and generated files

Nothing under `data/`, `cache/`, `results/` or `verification/` is committed — they are raw exports and derived caches, and `verification/` exists only on the machine that produced it ([#91]).

Every folder under `data/` uses the `.Last.txt` suffix, including `data/tick/`, whose files are a different format and orders of magnitude larger. **Never glob across resolutions.**

## Adding an archetype

New archetypes are developed **in Python only** — no NinjaScript gets written until a candidate looks worth trading, because NinjaTrader time is the scarce resource. Consequences:

- **The prime directive still binds during development.** A Python archetype that drifts past NT8's fidelity cannot be reconciled when it is finally ported, so the exploration is wasted rather than merely unvalidated. Check each rule against what NT8 can express *while writing it*, using the expressibility checklist in [`docs/roadmap.md`](docs/roadmap.md).
- **Register with `nqbt/archetypes.py`; do not fork the sweep.** An `Archetype` needs `run`, `legs` and `signal` — all three are required, and an archetype registered without `legs` would silently be the slow path in a sweep.
- **Write the entry half only.** Stop, targets, ambiguity policy, limit-fill rule and leg writer all live in `nqbt/sim/bracket.py`, which carries the reconciliation evidence. **Do not fork it.**
- **Set `Tier2Status` honestly.** `TIER1_ONLY` until a real NT8 trade list has been diffed against it. The status reaches the results table so that a ranking cannot silently compare a measurement against an assumption.
- **Record every rule in `docs/nt8-fidelity.md`**, naming the NinjaScript each would be written as, even when there is no C# yet — that is what the eventual port gets checked against.

## Statistics and results

- **A number with no null is not a finding.** Report a spread against what resampling would produce, and an entry rule against the matched random-entry arm (`nqbt/randomentry.py`).
- **Guard against multiple comparisons.** The best of nineteen contracts × N combinations is the *expected* output of noise. Test a combination chosen for a reason, not the best of two hundred.
- **Say what a statistic was computed over.** Per trade or per leg, whole window or a prefix. "The trigger cap binds on 50% of signals" was a prefix, not a rate; over the whole window it is about a third.
- **Read `session_close_share` and `ambiguous_share` before believing a result**, and always before believing a coarse resolution.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
