# Contributing to nqbt

This file is the working agreement: how code, tests, commits and pull requests are expected to look, and the few rules that are not negotiable.

Read [`README.md`](README.md) first for what the project is and the traps that have already cost real time. The two documents do not overlap: that one is about *this codebase*, this one is about *how to change it*.

## The prime directive

**Match NinjaTrader 8's default fidelity exactly — do not exceed it.** Being more precise than NT8 is as much a bug as being less precise, because it makes [Tier 1 and Tier 2](README.md#tier-1-and-tier-2) disagree in ways that cannot be attributed.

This governs `nqbt/sim/` and everything feeding it. Before changing anything there, read [`docs/nt8-fidelity.md`](docs/nt8-fidelity.md) — it records every NT8 rule the simulation implements and the evidence for it. When the C# and intuition disagree, the C# wins; when the C# and a real NT8 trade list disagree, the trade list wins.

## Where reasoning goes

**Reasoning belongs in `docs/`, not in the source.** ([#105])

Code should be readable on its own terms. Prefer a clearer name, a smaller function or an intermediate variable over a comment explaining an unclear one.

- **Docstrings say *what* a thing is or does and how to use it**, and stay short. One line is often enough; a paragraph is plenty.
- **A function's summary opens with an imperative verb** — `Return the row holding period`, not `The row holding period`. ruff's `D401` checks this, but only against words it recognises, so a summary opening `One`, `Every` or `Whether` passes it and still breaks the rule. Two kinds of function are exempt, as they are from `D401`: a `test_*` function's docstring states the claim the test makes, and a property's docstring names the value it holds.
- **Comments should be confined to unintuitive or unexpected behaviour** — a subtle index, a deliberate deviation from what a reader would expect, a workaround. Use them sparingly, and only where the code's behaviour departs from what a competent reader would predict.
- **Code should generally be self-documenting**, by using clear variable names and logical flow, comments and long explanations should be few and far between. A large quantity of comments or doc strings suggest the code is unreadable, unintuitive, or that the comments are not needed.
- **Arguments, justifications, measurements, decision records, history and traps go in `docs/`**, with at most a one-line pointer from the code.

Five homes, and they are not interchangeable:

| goes in                                        | what it holds                                                                                         |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [`docs/nt8-fidelity.md`](docs/nt8-fidelity.md) | every NT8 rule the simulation reproduces, and the evidence that established it                        |
| [`docs/findings/`](docs/findings/)             | one file per [campaign](README.md#campaign): what was measured, what it returned, and what it settles |
| [`docs/roadmap.md`](docs/roadmap.md)           | the standing constraints, the rubric, the traps and the decisions taken                               |
| [`tools/README.md`](tools/README.md)           | what each tool does, how to run it, and why its options, defaults and grids are what they are         |
| [`nqbt/README.md`](nqbt/README.md)             | the package's design notes that no campaign, NT8 rule or decision record covers                       |

A tool's module docstring is its summary line, its usage lines and a pointer to its section of `tools/README.md`.

A pointer must name a section that exists, in the form the source already uses:

```text
``docs/roadmap.md`` §M17
``docs/findings/m28-1-openingrange-swept.md`` § "Gate 3 -- the entry beats a random entry"
``docs/nt8-fidelity.md``, "Ambiguous bars resolve to whichever level is nearer the open"
```

A bare "see the docs" is not a pointer, and [`tests/test_doc_pointers.py`](tests/test_doc_pointers.py) fails on one that names a heading no longer there.

**Campaign results should go in `docs/findings/`.** Add a file with the front matter the others carry — `id`, `title`, `archetypes`, `issues`, `gates`, `outcome`, `verdict` — then run [`tools/findings_index.py`](tools/findings_index.py) to regenerate `register.md`, `by-archetype.md` and `by-gate.md`. Those three are generated and should not be edited by hand.

[`docs/findings/README.md`](docs/findings/README.md) is the opposite — it is the authored summary of what the evidence supports for a prop account and for a regular one, the tool never touches it, and **a campaign that changes which strategy is best is a campaign that has to update it**. Leave a stub under `## Milestone notes` in the roadmap carrying the `§Mxx` heading and a one-line verdict, so a `§Mxx` pointer still lands somewhere.

## Naming

**Variables must be named so their purpose is obvious at a glance.** A name that needs a comment to explain it is the wrong name. `handover_ratio` and `bars_required_to_trade` are right; `hr` and `n2` are not.

Two exceptions, both deliberate:

- **Inside an `@njit` loop**, short conventional indices (`i`, `j`, `leg`) are clearer than long ones and match the surrounding code.
- **Where a name mirrors a NinjaScript property**, keep NT8's word so the two can be diffed by eye — `tp_multiplier` for `TPMultiplier`.

Match the surrounding code's idiom. A module written one way should not acquire a second style because a new function arrived.

## Control flow

**Guard clauses are preferred to nesting.** Invert the condition and leave early, so the work a function exists to do sits at one indent level instead of inside an `if`.

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
- **No `else` after a branch that leaves.** ruff's `RET505`–`RET508` rules will usually catch this, but worth being aware of in terms of general code style.
- **Validate first, then work.** Every `raise` for a bad argument belongs above the first line of real work — `validate_thresholds` in `nqbt/regime.py` is the shape.
- **Indentation is a signal, not just a fault.** Deep indentation is usually indicative of a method or function doing too many things. Where possible repeated or reusable code should be extracted to helper functions.

Two exceptions, both deliberate:

- **Where inverting costs clarity, do not.** A single `if a and b:` reads better than two negated guards when neither half means anything on its own, and `if not disabled:` is worse than the nesting it removed.
- **Inside `@njit` code, reshaping control flow is a gated refactor.** numba also requires every return path to agree on type, so an added early `return` is not free. See ["The trade-log regression gate"](#the-trade-log-regression-gate).

## Numba

**Every `@njit` function takes `cache=True`**, so parallel [sweep](README.md#sweep) workers load the compiled code from disk rather than each compiling it again.

## Tests

**Everything (nqbt, tools, formatting etc...) is tested unless there is a very good reason not to**, and the reason must be clearly documented somewhere.

Aim to cover three kinds of case for anything non-trivial:

1. **Normal operation** — the input the function exists for.
2. **Unusual operation** — an empty series, a single [bar](README.md#bar), a session with a hole, a period longer than the data, a boundary where two conditions are exactly equal.
3. **Exception operation** — the inputs that must raise, asserted on the *specific* exception type and, where the message is the point, on its content.

These three cover most failure modes. When one turns up that they miss, add a test for it.

Further expectations:

- **A test must be able to fail.** Verifying the gate can fail is part of using it.
- **Pin the property, not the transcript.** Assert that deleting three bars from a session leaves every remaining bar's index unchanged, rather than asserting a list of numbers that happens to be today's output.
- **A timezone test must assert both halves.** "These bars carry the same Eastern minutes" is a tautology over a UTC implementation; it needs "and their UTC minutes differ" beside it.
- **Name the test after the claim** it makes. `test_the_two_summary_paths_agree_exactly` says what breaking it means; `test_summary_2` does not.

### Coverage

**At least 90% on new lines and 85% over `nqbt` as a whole.** Codecov gates both on the run with the JIT disabled ([`codecov.yaml`](codecov.yaml)). Check with the JIT disabled before concluding anything is untested:

```bash
NUMBA_DISABLE_JIT=1 uv run python -m pytest --cov=nqbt --cov-branch
```

`coverage.py` cannot see inside `@njit`-compiled functions — numba runs machine code, so the Python bytecode never executes and every line reads as missed. The raw figure reads much lower for that reason alone. CI runs both jobs: one with the JIT active, which is the real functional test, and one with it disabled, which is the accurate coverage measurement.

**Do not set `NUMBA_DISABLE_JIT=1` on the main test job** to make the number look better. That would stop CI ever exercising the compiled path, trading verification of fidelity-critical code for a metric.

Use `--cov=nqbt`, not a bare `--cov`, which includes `tests/` and inflates the total.

## Linting and typing

```bash
uv run python -m pytest
uv run ruff check nqbt formatting
uv run ruff format --check .
uv run mypy nqbt formatting
uv run python -m formatting.cli --check .
uv run pymarkdown scan $(git ls-files '*.md')
uv run mdformat --check .
```

CI runs `pymarkdown scan --recurse .`, which is fine on a clean checkout but usually noisy locally because it includes `.venv` and the gitignored notes under `docs/`. Scan the tracked files instead. `mdformat` takes a bare `.` in both places because its exclusions live in [`.mdformat.toml`](.mdformat.toml) rather than on the command line.

**`ruff` and `mypy` must report no errors.** CI gates `ruff check nqbt formatting`, `ruff format --check .` and `mypy nqbt formatting`, so either one failing fails the build. `tests/` and `tools/` are **not** at zero for either tool and are not gated, though where writing new code you should generally aim not to introduce any new errors or warnings to make future remediation works easier.

**Fix a `ruff` or `mypy` error rather than hiding it.** Ignore one only when it is a genuine misfire or there is a very good reason not to fix it. Every entry in `[tool.ruff.lint] ignore` and `per-file-ignores` should carry a one-line reason, along with every `# noqa` and every `# type: ignore`, unless the purpose is obvious or well documented elsewhere. Put the reason **after the pragma on the same line, however long that makes the line**, so that grepping for a bare `# noqa: X$` finds anything undocumented. `warn_unused_ignores` is on, so an ignore that stops being needed fails the build rather than lingering.

### The custom formatting rules

`formatting/` is a small LibCST formatter for two things `ruff format` has no opinion about, both of which are house style rather than anyone's convention:

1. **A blank line after an `if` block**, before whatever statement follows it in the same block.
2. **A blank line before the last `return` in a function**, so the value a function produces is visually separated from the work that produced it.

```bash
uv run python -m formatting.cli --check .      # what CI runs
uv run python -m formatting.cli .              # rewrite in place
```

**It is independent of `ruff format`, and the order you run them in does not matter.** That is a property of the rules rather than a coincidence: they only ever *insert* a blank line, never at the top of a block, and only where there were none. Anywhere `ruff format` demands two blank lines, a source with none was already unformatted — so going from none to one cannot break it. `tests/test_formatting.py` pins the two properties this rests on, and is the place to look if the two ever start fighting.

#### Where the blank line goes

**A comment belongs to the statement below it, so the blank line goes above the comment, not between the comment and its statement.** Both rules share one predicate for this in `formatting/_leading.py`.

```python
x = compute()

# why this is the fallback
return x
```

The one exception is a docstring: a return directly beneath one stays against it.

#### Scope, and the exit statuses

**CI checks the whole tree** — `nqbt`, `formatting/`, `tests/` and `tools/` alike.

A directory argument skips dot-directories beneath it, so `formatting.cli .` at the repository root does not walk into `.venv`. Naming one explicitly still works.

| status | meaning                                                             |
| ------ | ------------------------------------------------------------------- |
| 0      | every file checked is formatted                                     |
| 1      | `--check` found a file that would be reformatted                    |
| 2      | a path was missing or unparseable, so it was never actually checked |

**Status 2 is the one that matters for a gate**: without it, a typo in the checked path would pass as a clean run.

### Local variables carry their type too

**Annotate a local at its first binding**, with the same aliases the signatures use. A name can only be annotated once per scope, so that first binding is the declaration for the whole function; where a name is bound in two arms of a branch, declare it bare above the branch rather than typing one arm and not the other.

Leave a local bare where the type cannot be stated honestly: a `pd.Series` whose dtype belongs to the caller, `json.loads`, duckdb rows, joblib. `disallow_any_explicit` rejects those anyway, and **a `# type: ignore` per local to say "unknown" is worse than no annotation** — it is a pragma with nothing to fix. Leave it bare, too, where mypy's inference and the runtime disagree, and say which in a comment; numpy types `datetime64 + timedelta64` as `timedelta64`, and `nqbt/sessions.py` has the site.

`nqbt/arrays.py`'s `AnyArray` is **not** a wildcard. It is a concrete `dtype[generic[object]]`, so a local annotated with it type-checks at the assignment and then fails at every later use. Name the real dtype — the expression almost always states it — or leave the local bare.

### Dependencies are pinned exactly

Every entry in `dependencies` and the `dev` group is `==`, not `>=`, and `uv.lock` pins everything they pull in, so a local run and a CI run use the same versions and no upstream release reaches the build until someone chooses it; with `extend-select = ["ALL"]`, that includes every new ruff rule. CI installs with `uv sync --locked`, which fails when the lock no longer matches `pyproject.toml`: after changing a dependency, run `uv lock` and commit both files. Dependabot raises the bumps daily, grouped into one pull request that updates both. `uv run` syncs the local `.venv` to the lock before it runs, so pulling a bump to numpy, numba or pandas changes the versions your next run uses; while a campaign is running from `.venv`, start anything else with `uv run --no-sync`, so a sync cannot replace files the campaign has loaded. `uv` itself is pinned by `required-version` in `pyproject.toml`, which CI reads too. **Do not relax a pin to make an install resolve** — take the dependabot bump instead, or pin the version that works and say why.

**Treat a bump to numpy, numba, pandas or pyarrow as a change to `nqbt/sim/`**, because it is one: it reaches the simulation without touching a file in it, so nothing else will prompt you to check. CI carries the three pins that need no data — `tests/test_rng_stream_pins.py`, `tests/test_numeric_pins.py` and `tests/test_parquet_round_trip.py` — and a failure in any of them is a finding to explain, never a value to re-pin. They are canaries and not the gate: the trade-log gate runs on every dependency pull request in CI (["The trade-log regression gate"](#the-trade-log-regression-gate)), and the NT8 reconciliation still needs `verification/` and still runs locally. See [`docs/roadmap.md`](docs/roadmap.md) § "What CI can gate on a dependency bump".

### Lint changes are not exempt from review

An auto-fix can change logic as well as style, inside an `@njit` loop as easily as anywhere else, and reading the diff is not the gate.

**Read what an auto-fixer touched under `nqbt/sim/` before merging, not after**, and run the trade-log gate over it. A lint pull request is the last place anyone looks for a simulator change.

### Markdown

**Two tools run over the Markdown and they do different jobs.** `pymarkdown` is the linter — duplicate headings, bare URLs, a fence with no language, an empty link. `mdformat` is the formatter: it reparses each file and re-emits it canonically, which covers paragraph reflow, table padding, list markers and link-reference ordering. Neither substitutes for the other. `pymarkdown` **cannot** be configured to do `mdformat`'s job, because no rule exists for most of it — it has no table rules at all, and `MD013` measures line length without being able to fix it.

**When the Markdown job fails, run this and commit the result:**

```bash
uv run mdformat .
```

**Do not override either setting on the command line.** Both live in [`.mdformat.toml`](.mdformat.toml), which `mdformat` discovers from the repository root, and both replace a default that would rewrite every file: `wrap = "no"` is the house style — **prose is not hard-wrapped; one line per paragraph, blank line between** — where the default, `keep`, reflows nothing, and `number = true` keeps ordered lists at `1./2./3.` where the default flattens every item to `1.`. A flag beats the file, so one run with `--wrap keep` undoes the style for everything it touches.

`MD029` is set to `ordered` to catch that second case from the other side. Its default, `one_or_ordered`, accepts both numbering styles, so `pymarkdown` alone would pass a file whose ordered lists had all been flattened to `1.`.

**`mdformat-frontmatter` is what makes front matter safe, and it is a pin rather than a convenience.** Without it `mdformat` rewrites a `---` block into a thematic break and a heading, which silently destroys the metadata `docs/findings/` is indexed from.

**`.claude/rules/*.md` stay excluded even so.** The plugin now preserves their `paths:` front matter, but those files are hard-wrapped where everything else is not, so formatting them would reflow every one. Unexclude them only as a deliberate change with that reflow in the diff.

## The trade-log regression gate

**Anything touching `nqbt/` must prove it did not move a number** — not only `nqbt/sim/`, because an indicator, a session rule or an [archetype](README.md#archetype)'s signal reaches the trades just as surely.

```bash
uv run tools/capture_trade_logs.py before
# ...make the change...
uv run tools/capture_trade_logs.py after
uv run tools/compare_trade_logs.py before after
```

DeadCatBounce's four producer paths, and one log per other registered archetype at its defaults and live costs, so every archetype's loop runs. A refactor meant to preserve behaviour must reproduce every file; a change that adds a column must leave every other column identical (`--added <name>`). **An archetype's log sees only the rules on at its defaults**, so a change to a rule that is off by default — a filter, a sizing mode — comes back identical without having run.

Points that have each cost time:

- **Read "identical" as numerical, not textual.** Multiplying by `-1.0` sends `0.0` to `-0.0`, which is a different eight bytes and an equal number. `assert_frame_equal(check_exact=True)` is the right comparison and a file hash is too strict.
- **`sha256sum` is a cross-check, not the gate.** Use it to catch the gate itself being broken — it is code, and it has been wrong — but when the two disagree, find out which kind of difference it is before believing either.
- **A change that *should* move numbers still runs the gate.** The point is to see exactly which files moved and to be able to say why.

**CI runs the gate on every pull request that changes more than documentation.** [`.github/workflows/trade-log-gate.yaml`](.github/workflows/trade-log-gate.yaml) captures the base and the head, each in its own environment, over the two cache files the capture reads, and fails when the comparison does. A pull request touching only Markdown, `docs/` or the `Trading-Docs` pointer passes the check without running it; `is_documentation` in [`tools/trade_log_gate_ci.py`](tools/trade_log_gate_ci.py) is the rule. Run it locally while iterating; CI is the backstop, not the loop.

**A change meant to move a number takes the `expected-trade-log-change` label, then a re-run of the failed job**, because adding a label starts nothing. The label turns the failure into a warning and still writes what moved to the job summary — say in the pull request why. `--added` has no CI form, so a column addition takes the label too, proves its other columns locally with `--added`, and says so in the pull request. A comparison that did not finish fails whatever the labels say.

**CI's numbers are not your local numbers, and need not be.** The two cache files are a release asset on this repository, named in the workflow and pinned by hash, and they stay put while your own cache moves on; only base against head is compared. Refresh them only when the cached schema changes: upload both under a new tag, and update the workflow's URL and hashes in the same pull request.

## Commits

- **The subject begins with one of ten verbs.** `Add`, `Bump`, `Document`, `Fix`, `Move`, `Port`, `Reconcile`, `Refactor`, `Remove`, `Update` — and nothing else. A milestone tag, a filename or a bare capitalised word is not a prefix either: `M17.4 -- sweep_axes takes resolution`, `Docs: record the findings` and `instruments.py: route every figure` are all rejected.
- **Subject line at most 72 characters as it lands**, the space and `(#N)` GitHub appends included. That is where GitHub splits the subject and moves the remainder into the body, and a subject that has to be expanded to be read is a subject nobody reads. It leaves about 65 characters to write in.
- **Aim for 55, which the linter warns past.** The repository's file table clips the subject long before 72, and it clips on pixel width in a proportional font rather than on a character count — so a capital-heavy subject goes first, and no monitor is wide enough to help, because the page is capped at a fixed content width. Measured there: `Update the PR body rules for what lands on main (#174)` fits at 53 characters and `Add a commit-message linter and gate what lands on main (#165)` is clipped at 61. **The rule is a warning and never fails a run**, because the last few characters sometimes cost more in clarity than the clip costs in a table.
- **A body is for when the subject genuinely cannot carry it.** Leave a blank line after the subject and explain *why* rather than restating the diff.

**Body line length is deliberately not a rule.** **PR and issue bodies are never hard-wrapped here** — one line per paragraph, blank line between. The body that reaches `main` is the pull request description, and the squash merge wraps it on the way in, so a commit on `main` reading at about 70 columns is that automatic wrap and not a body someone hand-wrapped. Hard-wrapping the source of it would be wrapping twice. That is a rendering question, not a linting one.

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
echo "Add the phase filter to the sweep axes" | uv run tools/lint_commit_messages.py --stdin
```

Two things to know:

- **GitHub appends a space and `(#N)`, and it counts.** The check measures the subject as it lands.
- **Dependabot's titles are exempt from the length rule and the prefix warning.** It writes its own, they run past 72, and it could not act on either. They are no more ours to control than a `Merge` or `Revert` subject is.

**A Conventional Commits prefix is accepted but not recommended.** `fix(sim): derive the session end` passes and raises a warning; one of the ten verbs is the house style. Only the eleven types the spec names are recognised — `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. **The type stands in for the verb**, so the word after the colon is unconstrained; `fix(sim): derive the session end` is fine even though `derive` is not one of the ten. Anything else before a colon is not a prefix at all, it is a subject that fails to start with one of the ten.

## Pull requests

- **The body briefly explains the change**: what moved, and the reasoning a reviewer would otherwise have to reconstruct. Detailed argument still belongs in `docs/` — link to the section rather than duplicating it.
- **Pull requests and issues avoid jargon, or explain it in plain English** — a link to its [glossary](README.md#glossary) entry or a few words beside it. Skip the explanation where it would cost more length or clarity than it adds.
- **State how it was verified, and keep it to a line — but only what CI does not already show.** What the workflows run on every pull request — the test suite, the linters, the trade-log gate — is implicit in its checks, so it is not listed in the body. Name what you ran that CI cannot, and what it returned: `tools/reconcile_nt8.py` against the [MNQ](README.md#nq-and-mnq) 03-24 export: `RECONCILED`, or the trade-log gate's `ALL PRE-EXISTING COLUMNS IDENTICAL` under `--added`. A claim carries its number; it does not carry the transcript that produced it. **Raw output — a coverage table, a reconciliation's per-field agreement — belongs in `docs/` or nowhere**, because the body lands on `main` as the commit description and a pasted run cannot be re-checked from there anyway.
- **Repeat the closing keyword for every issue.** `Closes #1, #2` links only `#1`. Write `Closes #1. Closes #2.` and check `closingIssuesReferences` on the pull request before merging. Alternatively, link the issues manually via the GUI.
- **Do not quote figures that go stale.** Consider if the number is even needed in documentation or if it's better being generated or retrieved at the time it's needed. If it's definitely needed, point at the document that holds the live number.
- **Branch off `main` and never commit to it directly.** This is enforced by branch protection rules at the GitHub level.
- **All PRs should target `main` as the base.** Where one PR depends on another, this should be stated in a comment or the PR body.
- **One piece of work is one pull request, kept as small as that allows.** Do not split it because it grew; split it only when two changes are genuinely unrelated, and then each still targets `main`. Do not widen it to fix an unrelated problem, including one the documentation review below turns up — raise an issue for it instead.
- **Label it** as [Labels](#labels) describes.
- **PRs should have a linked issue in most cases**, so that additional reasonings and explanations can be placed there instead of in the PR body. This can be excepted though, for example simple version bumps or simple documentation updates.
- **A PR merges itself once approved.** Auto-merge (squash) switches on once it is open and out of draft, and the `sync` label it gets on opening keeps its branch up to date with `main`.

### Labels

**Every issue and pull request takes at least one `type:` label, and an `area:` label wherever one fits.** `type:` says what kind of work it is and `area:` which part of the code it touches. Use every one that is true — a campaign that adds a capability is both `type:feature` and `type:research`. `type:epic` is for a parent issue only.

**Three labels carry a requirement.** Applying one means the work meets it before it merges:

| label          | applies when                                                | needs                                                                                       |
| -------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `fidelity`     | the change touches NT8 parity                               | byte-identical trade logs, or a [leg](README.md#leg)-for-leg diff against an NT8 trade list |
| `perf`         | the change moves runtime or memory                          | a measurement, not an argument                                                              |
| `stats-hazard` | a result could be misread, or comes out of many comparisons | a stated guard against it                                                                   |

**Two labels plan the work, on issues.** `next-up` marks the front of the queue, and a workflow removes it when the issue closes. `needs-ninjatrader` marks work blocked on NinjaTrader time rather than code time — `docs/roadmap.md` § "Why the order is what it is".

**Four labels start or record a workflow:**

- `sync` — added when a pull request opens, and keeps its branch up to date with `main`. Remove it to stop that.
- `ready to merge` — approves the pull request so auto-merge finishes once checks pass. It acts only on the repository owner's pull requests, out of draft, and is removed when the pull request closes.
- `expected-trade-log-change` — turns a trade-log gate failure into a warning. See ["The trade-log regression gate"](#the-trade-log-regression-gate).
- `conflict` — added when `main` cannot be merged into a `sync` branch automatically. Resolve the conflict by hand.

**`dependencies`, `python:uv`, `github_actions` and `submodules` are never added by hand.** Dependabot and the submodule bump workflow add them.

### Keep the docs and issues current

Whenever a strategy or archetype changes, or a new sweep runs, review the findings documentation to make sure it is still accurate. This includes running the prop-account tools ([`tools/README.md`](tools/README.md) § "Prop-firm accounts") to see whether a strategy that loses on a normal account would still win on a prop account.

All PRs should undertake a review of all documentation, not just `docs/`, to ensure that the changes in that PR don't make any documentation go stale, out of date, inaccurate or misleading. Any respective documentation updates should be part of the same PR as the changes. This check should also include a check of open issues to confirm whether the PR may affect them. **Name every affected issue in the PR body**, which links the PR from the issue's timeline. **Comment on the issue only when the PR changes it substantially** — the problem it describes or the plan it lays out no longer holds as written — so that someone reading the issue alone can see that at a glance. Progress, a status change, or a detail that changes while the plan still holds is not a reason to comment; the link already records it.

## Data and generated files

Nothing under `data/`, `cache/` or `results/` is committed — they are raw exports and derived caches. `verification/` commits only its `README.md`, because that is hand-written and cannot be regenerated; the captures it explains exist only on the machine that produced them ([#91]).

**Name a file inside `results/` or `verification/` in words, not by its path** ([#368]) — "that archetype's campaign database", "the MNQ 03-24 reconciliation capture". Nobody else can follow the path, and it goes stale without anyone noticing when the file is replaced. Keep exact paths in a README inside the folder itself. The folders, the defaults the code writes to such as `results/campaign/` and `results/sweeps.duckdb`, and the committed `verification/README.md` can still be named. Findings files are exempt because they are dated records, and the register says so. [`tests/test_doc_pointers.py`](tests/test_doc_pointers.py) enforces it.

**The one published copy is what the trade-log gate's CI run downloads**: two files from `cache/`, attached to a release rather than committed so that refreshing them does not grow the history. [`.github/workflows/trade-log-gate.yaml`](.github/workflows/trade-log-gate.yaml) names the release.

Every folder under `data/` uses the `.Last.txt` suffix, including `data/tick/`, whose files are a different format and orders of magnitude larger. **Never glob across resolutions.**

## Adding an archetype

New archetypes are developed **in Python only** — no NinjaScript gets written until a candidate looks worth trading, because NinjaTrader time is the scarce resource. Consequences:

- **The prime directive still binds during development.** A Python archetype that drifts past NT8's fidelity cannot be reconciled when it is finally ported, so the exploration is wasted rather than merely unvalidated. Check each rule against what NT8 can express *while writing it*, using the expressibility checklist in [`docs/roadmap.md`](docs/roadmap.md) § "An original archetype has no C# to lose to".
- **Register with `nqbt/archetypes.py`; do not fork the sweep.** An `Archetype` needs `run`, `legs`, `signal` and `long_side` — all four are required, and an archetype registered without `legs` would silently be the slow path in a sweep. `long_side` is the side each bar would be entered on, which the confluence size's labels and its fit both read.
- **Registering it puts it under the trade-log gate.** Its defaults must trade on MNQ 03-24, or the capture stops. The pull request that registers it is not compared on it, because the base has no log to compare; the comparison lists the log as new.
- **Write the entry half only.** Stop, targets, ambiguity policy, limit-fill rule and leg writer all live in `nqbt/sim/bracket.py`, which carries the reconciliation evidence. **Do not fork it.**
- **Set `Tier2Status` honestly.** `TIER1_ONLY` until a real NT8 trade list has been diffed against it. The status reaches the results table so that a ranking cannot silently compare a measurement against an assumption.
- **Record every rule in `docs/nt8-fidelity.md`**, naming the NinjaScript each would be written as, even when there is no C# yet — that is what the eventual port gets checked against.

## Statistics and results

- **A number with no null is not a finding.** Report a spread against what resampling would produce, and an entry rule against the [matched random-entry arm](README.md#matched-null) (`nqbt/randomentry.py`).
- **Guard against multiple comparisons.** The best of nineteen contracts × N [combinations](README.md#configuration) is the *expected* output of noise. Test a combination chosen for a reason, not the best of two hundred.
- **Say what a statistic was computed over.** Per trade or per [leg](README.md#leg), whole window or a prefix. "The trigger cap binds on 50% of signals" was a prefix, not a rate; over the whole window it is about a third.
- **Read `session_close_share` and `ambiguous_share` before believing a result**, and always before believing a coarse [resolution](README.md#resolution).
- **The share is not the exposure.** `ambiguous_share` says how often the [fill](README.md#fill) assumption was invoked, not how much the result depends on it. Where an archetype's ambiguity varies across its own swept space, run `tools/campaign_ambiguity.py` over the [shortlist](README.md#shortlist): it reports the spread between the two policies, and above `disambiguate.MIN_AMBIGUOUS_SHARE` it settles what the minute bars can settle and re-summarises with the assumption corrected — [`docs/roadmap.md`](docs/roadmap.md) §M28.3 and §M28.4. **A resolved [profit factor](README.md#profit-factor) is a diagnostic and never a ranking**, and it never enters `nqbt/sim/`.

[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
[#368]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/368
[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
