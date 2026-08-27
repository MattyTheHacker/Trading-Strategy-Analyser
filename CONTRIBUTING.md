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

| goes in | what it holds |
|---|---|
| [`docs/nt8-fidelity.md`](docs/nt8-fidelity.md) | every NT8 rule the simulation reproduces, and the evidence that established it |
| [`docs/roadmap.md`](docs/roadmap.md) | planned work in dependency order, the reasoning behind it, and the standing traps |

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
```

CI runs `pymarkdown scan --recurse .`, which is fine on a clean checkout but usually noisy locally because it includes `.venv` and the gitignored notes under `docs/`. Scan the tracked files instead.

**`ruff` and `mypy` must report no errors.** CI gates `ruff check nqbt`, `ruff format --check .` and `mypy nqbt`, so either one failing fails the build. `tests/` and `tools/` are **not** at zero for either tool and are not gated; running them over the whole tree is still worth doing, but only the package's count has to stay at zero.

Every entry in `[tool.ruff.lint] ignore` and `per-file-ignores` carries a one-line reason, and so does every `# noqa`, every `# type: ignore` and the one `[tool.coverage]` exclusion. Add none of them without one. Put the reason **after the pragma on the same line** so that grepping for a bare `# noqa: X$` finds anything undocumented; only where 110 columns leave no room does it go on the line above. `warn_unused_ignores` is on, so an ignore that stops being needed fails the build rather than lingering.

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

- **Imperative mood**: "Add the phase filter", not "Added" or "Adds".
- **Subject line at most 72 characters as it lands**, the space and `(#N)` GitHub appends included. That is where GitHub truncates a subject with an ellipsis, and a subject that has to be expanded to be read is a subject nobody reads. It leaves about 65 characters to write in.
- **A body is for when the subject genuinely cannot carry it.** Leave a blank line after the subject and explain *why* rather than restating the diff.

**Body line length is deliberately not a rule.** The body that reaches `main` is the pull request description, and PR and issue bodies are never hard-wrapped here — one line per paragraph, blank line between, and GitHub wraps them. That is a rendering question, not a linting one. The 80-column convention was dropped rather than compromised, because holding both at once is impossible.

[`tools/lint_commit_messages.py`](tools/lint_commit_messages.py) enforces the rest, and CI runs it twice per pull request: once over every commit the branch adds, and once over the message GitHub will squash onto `main`. Check a message before you write it:

```bash
git log --format=%B -z origin/main..HEAD | ./.venv/Scripts/python.exe tools/lint_commit_messages.py --stdin
```

Three things the rules above do not say, each of which has already cost a commit:

- **The subject that lands on `main` is the pull request title**, because `main` takes squash merges only. The title is the thing to get right; the branch's commits are squashed away.
- **GitHub appends a space and `(#N)`, and it counts.** Two subjects on `main` were written to exactly 80 and pushed past it by the number. The check measures the subject as it lands.
- **Dependabot's titles are exempt from the length rule.** It writes its own, they run past 72, and they are no more ours to control than a `Merge` or `Revert` subject is.

**Conventional Commits (`feat:`, `fix:`, `chore:`) is deliberately not used.** Measured over the last 100 commits of 32 major repositories, adoption is bimodal and tracks tooling rather than quality: the JavaScript and TypeScript projects that generate changelogs and semver bumps from commit types sit at 91-100%, and everything else — Django, Rails, Go, Rust, NumPy, pandas, scikit-learn, Kafka, the kernel — sits at or near zero. `nqbt` publishes nothing and has no changelog, so the prefix would buy nothing. Imperative mood, by contrast, held at 0-8% violation in 31 of those 32 repositories, which is why it is the rule that is enforced.

## Pull requests

- **The body briefly explains the change**: what moved, and the reasoning a reviewer would otherwise have to reconstruct. Detailed argument still belongs in `docs/` — link to the section rather than duplicating it.
- **State how it was verified.** For anything under `nqbt/sim/`, that means the trade-log gate's output, not a description of it.
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

[#91]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/91
[#105]: https://github.com/MattyTheHacker/Trading-Strategy-Analyser/issues/105
