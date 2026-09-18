"""Rank a campaign's configurations by what a prop account is scored on, then read them held out.

    ./.venv/Scripts/python.exe tools/campaign_propobjectives.py --strategy OpeningRange --root MNQ NQ

``tools/campaign_propaccount.py`` replays a shortlist chosen by profit factor. This one chooses
the shortlist by the account objective itself -- pass rate, fees per pass, time to the first
payout and funded life -- and replays it on the held-out window beside the profit-factor
shortlist it is measured against.

**Every objective ranks on the selection window and is read on the holdout.** The pool it
ranks is the top ``--pool`` distinct configurations by stored selection-window profit factor,
maximum-hold arms and rows the fill assumption could have decided excluded, because every
configuration has to be re-run to be replayed. What each objective means and which presets
answer which: ``docs/findings/m40-prop-objectives.md`` § "What each objective measures".

Re-runs every log it replays on the archive as it stands, and stores none of them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

# Run directly, ``sys.path[0]`` is ``tools/`` rather than the repository root, so the
# sibling imports below would fail; a test importing ``tools.campaign_*`` needs the same root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nqbt import archetypes, context, disambiguate, logsetup, propaccount, resample, sessions, splice
from tools.campaign_holdout import HELD_OUT_SUFFIX, JOIN_KEYS, SELECTION_SUFFIX, half, ranked_pairs
from tools.campaign_propaccount import labelled, uncapped
from tools.campaign_shortlist import TOP, rebuild, rerun_group, source
from tools.campaign_sweep import HOLD_VARIANTS

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Iterator

    from nqbt.arrays import DateArray

logger = logging.getLogger(__name__)

POOL = 500
"""How many configurations selection-window profit factor admits before an objective ranks them."""


class Objective(NamedTuple):
    """One figure a prop account can be optimised for."""

    name: str
    higher_is_better: bool
    funded: bool
    """Whether it describes the funded account rather than the evaluation."""


OBJECTIVES = (
    Objective("pass_rate", higher_is_better=True, funded=False),
    Objective("fees_per_pass", higher_is_better=False, funded=False),
    Objective("days_to_payout", higher_is_better=False, funded=False),
    Objective("funded_days", higher_is_better=True, funded=True),
)

CONTROL = "profit_factor"
"""The ranking every objective's shortlist is read against: the one the findings already use."""

SHARES = ("ambiguous_share", "session_close_share")
"""Read before believing any row of this -- ``CONTRIBUTING.md`` § "Statistics and results"."""

MEASURES = (
    "attempts",
    "passes",
    "pass_rate",
    "fees_paid",
    "fees_per_pass",
    "days_to_payout",
    "funded_days",
    "funded_accounts",
    "funded_censored",
    "net",
    "ever_passed",
    "paid_out",
)
"""What one configuration's replay through one rule set reports."""


def reads(account: propaccount.PropAccount, objective: Objective) -> bool:
    """Whether a preset's replay answers an objective.

    ``docs/roadmap.md`` § "A firm that changes its rules at the pass ships as two presets".
    """
    if objective.funded:
        return not account.fees.monthly_fee_ends_at_pass

    return account.rules.profit_target > 0.0


def calendar(bars: pd.DataFrame) -> DateArray:
    """Every trading day a window's bars hold a session bar on, in order."""
    info: sessions.SessionInfo = sessions.classify(pd.DatetimeIndex(bars.index))

    return np.unique(info.trading_day[info.in_session])


def sessions_between(days: DateArray, first: dt.date, last: dt.date) -> int:
    """Trading days from ``first`` to ``last``, both included."""
    start: int = int(np.searchsorted(days, np.datetime64(first, "D"), side="left"))
    end: int = int(np.searchsorted(days, np.datetime64(last, "D"), side="right"))

    return max(0, end - start)


def funded_lives(
    result: propaccount.PropReplay,
    account: propaccount.PropAccount,
    days: DateArray,
) -> list[tuple[int, bool]]:
    """Each funded account's life in trading days, and whether the window ended it.

    A preset with no profit target is funded from its first day; any other is funded from the
    day after its pass, and an attempt that never passed was never funded.
    """
    window_end: dt.date = pd.Timestamp(days[-1]).date()
    lives: list[tuple[int, bool]] = []
    for run in result.runs:
        censored: bool = run.outcome is propaccount.Outcome.SURVIVED
        end: dt.date = window_end if censored else run.last_day
        if account.rules.profit_target <= 0.0:
            lives.append((sessions_between(days, run.first_day, end), censored))
            continue

        if run.passed_on is None:
            continue

        lives.append((sessions_between(days, run.passed_on, end) - 1, censored))

    return lives


def days_to_payout(result: propaccount.PropReplay, days: DateArray) -> float:
    """Trading days from opening the first account to the first withdrawal. ``inf`` for none."""
    for run in result.runs:
        if run.first_withdrawal_on is None:
            continue

        return float(sessions_between(days, result.runs[0].first_day, run.first_withdrawal_on))

    return float("inf")


def measure(
    result: propaccount.PropReplay,
    account: propaccount.PropAccount,
    days: DateArray,
) -> dict[str, float | int | bool]:
    """Every :data:`MEASURES` figure for one replay.

    An objective whose event never happened takes the value that ranks it last: fees per pass
    and days to payout are ``inf`` and funded life is ``0``. One the preset does not answer is
    ``nan`` -- :func:`reads`.
    """
    lives: list[tuple[int, bool]] = funded_lives(result, account, days)
    measured: dict[str, float | int | bool] = {
        "attempts": result.attempts,
        "passes": result.passes,
        "pass_rate": result.pass_rate,
        "fees_paid": result.fees_paid,
        "fees_per_pass": result.fees_paid / result.passes if result.passes else float("inf"),
        "days_to_payout": days_to_payout(result, days),
        "funded_days": float(np.median([life for life, _ in lives])) if lives else 0.0,
        "funded_accounts": len(lives),
        "funded_censored": sum(censored for _, censored in lives),
        "net": result.net,
        "ever_passed": result.passes > 0,
        "paid_out": result.withdrawn > 0.0,
    }
    for objective in OBJECTIVES:
        if not reads(account, objective):
            measured[objective.name] = float("nan")

    return measured


def replay_configuration(
    row: pd.Series,  # type: ignore[type-arg]  # duckdb's dtypes
    summary: dict[str, object],
    log: pd.DataFrame,
    accounts: list[propaccount.PropAccount],
    days: DateArray,
) -> list[dict[str, object]]:
    """One configuration's re-run through every rule set it was asked for, one row each.

    ``trades`` and ``profit_factor`` are the re-run's, not the stored row's --
    ``docs/findings/m40-prop-objectives.md`` § "The pool, and the archive it was re-run on".
    """
    measured: list[dict[str, object]] = []
    for account in accounts:
        try:
            result: propaccount.PropReplay = propaccount.replay(log, account, max_accounts=uncapped(log))
        except propaccount.PropAccountError as refused:
            logger.warning("  %-26s combo %-6d refused: %s", account.name, int(row["combo_id"]), refused)
            continue

        measured.append(
            {
                **labelled(row),
                "window": row["window"],
                "trades": int(summary["trades"]),  # type: ignore[call-overload]  # an int by construction
                CONTROL: float(summary[CONTROL]),  # type: ignore[arg-type]  # a float by construction
                **{share: float(summary[share]) for share in SHARES},  # type: ignore[arg-type]  # floats
                "account_name": account.name,
                **measure(result, account, days),
            },
        )

    return measured


def rerun_logs(
    name: str,
    rows: pd.DataFrame,
    root: str,
    bars: pd.DataFrame,
) -> Iterator[tuple[pd.Series, dict[str, object], pd.DataFrame]]:  # type: ignore[type-arg]  # duckdb's dtypes
    """Every row of one window re-run with its summary and log, one resample per resolution."""
    archetype: archetypes.Archetype = archetypes.get(name)
    for minutes, block in rows.groupby("resolution", sort=False):
        frame: pd.DataFrame = resample.resample(bars, int(minutes))
        # ``splice.load_continuous`` is called without ``back_adjust``, so these are the prices
        # that traded and a rule reading an absolute level may run, exactly as in the sweep.
        yield from rerun_group(block, frame, archetype, root, int(minutes), context.PriceBasis.RAW)


def measure_window(
    name: str,
    rows: pd.DataFrame,
    root: str,
    bars: pd.DataFrame,
    wanted: dict[tuple[str, int, str, str, int], list[propaccount.PropAccount]],
    n_jobs: int,
) -> pd.DataFrame:
    """Replay one window's rows through the rule sets ``wanted`` names for each, in parallel."""
    days: DateArray = calendar(bars)
    batches: list[list[dict[str, object]]] = Parallel(n_jobs=n_jobs)(
        delayed(replay_configuration)(row, summary, log, wanted[key_of(row)], days)
        for row, summary, log in rerun_logs(name, rows, root, bars)
    )

    return pd.DataFrame([measured for batch in batches for measured in batch])


def key_of(row: pd.Series) -> tuple[str, int, str, str, int]:  # type: ignore[type-arg]  # duckdb's dtypes
    """The :data:`~tools.campaign_holdout.JOIN_KEYS` that name one configuration in both windows."""
    return (
        str(row["root"]),
        int(row["resolution"]),
        str(row["variant"]),
        str(row["stratum"]),
        int(row["combo_id"]),
    )


def ranking(measured: pd.DataFrame, by: str, *, higher_is_better: bool, top: int) -> pd.DataFrame:
    """The ``top`` rows ``by`` ranks highest, selection-window profit factor breaking ties."""
    return measured.sort_values(
        [by, CONTROL],
        ascending=[not higher_is_better, False],
        kind="stable",
    ).head(top)


def shortlists(
    selection: pd.DataFrame,
    accounts: list[propaccount.PropAccount],
    top: int,
) -> pd.DataFrame:
    """Each rule set's shortlist under every objective it answers and under the control.

    One row per configuration per shortlist, tagged ``ranked_by``.
    """
    if selection.empty:
        return pd.DataFrame()

    chosen: list[pd.DataFrame] = []
    for account in accounts:
        measured: pd.DataFrame = selection[selection["account_name"] == account.name]
        if measured.empty:
            continue

        control: pd.DataFrame = ranking(measured, CONTROL, higher_is_better=True, top=top)
        chosen.append(control.assign(ranked_by=CONTROL))
        for objective in OBJECTIVES:
            if not reads(account, objective):
                continue

            picked: pd.DataFrame = ranking(
                measured,
                objective.name,
                higher_is_better=objective.higher_is_better,
                top=top,
            )
            chosen.append(picked.assign(ranked_by=objective.name))

    if not chosen:
        return pd.DataFrame()

    return pd.concat(chosen, ignore_index=True)


def verdict(chosen: pd.DataFrame, held: pd.DataFrame) -> pd.DataFrame:
    """Each shortlist's medians on the window that chose it and on the held-out one."""
    if chosen.empty or held.empty:
        return pd.DataFrame()

    keys: list[str] = [*JOIN_KEYS, "account_name"]
    chosen_half: pd.DataFrame = (
        chosen.set_index([*keys, "ranked_by"]).add_suffix(SELECTION_SUFFIX).reset_index()
    )
    held_half: pd.DataFrame = held.set_index(keys).add_suffix(HELD_OUT_SUFFIX).reset_index()
    paired: pd.DataFrame = chosen_half.merge(held_half, on=keys, validate="many_to_one")
    rows: list[dict[str, object]] = []
    for (account_name, ranked_by), block in paired.groupby(["account_name", "ranked_by"], sort=False):
        row: dict[str, object] = {"account_name": account_name, "ranked_by": ranked_by, "n": len(block)}
        for objective in OBJECTIVES:
            row[f"{objective.name}{SELECTION_SUFFIX}"] = block[f"{objective.name}{SELECTION_SUFFIX}"].median()
            row[f"{objective.name}{HELD_OUT_SUFFIX}"] = block[f"{objective.name}{HELD_OUT_SUFFIX}"].median()

        for share in SHARES:
            row[f"{share}{HELD_OUT_SUFFIX}"] = block[f"{share}{HELD_OUT_SUFFIX}"].median()

        row["censored_share"] = _share(block["funded_censored_hold"], block["funded_accounts_hold"])
        row["ever_passed_%"] = 100.0 * block["ever_passed_hold"].mean()
        row["paid_out_%"] = 100.0 * block["paid_out_hold"].mean()
        row["net_hold"] = block["net_hold"].median()
        row["pf_hold"] = block[f"{CONTROL}{HELD_OUT_SUFFIX}"].median()
        rows.append(row)

    return pd.DataFrame(rows)


def _share(part: pd.Series, whole: pd.Series) -> float:  # type: ignore[type-arg]  # duckdb's dtypes
    """``part`` over ``whole`` summed, or ``nan`` when the whole is empty."""
    total: float = float(whole.sum())

    return float(part.sum()) / total if total else float("nan")


def show(title: str, frame: pd.DataFrame) -> None:
    """Print one table under a heading, or say that it is empty."""
    logger.info("")
    logger.info("--- %s ---", title)
    if frame.empty:
        logger.info("(nothing)")

        return

    with pd.option_context("display.width", 260, "display.max_columns", 60):
        logger.info("%s", frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def pool(name: str, root: str, args: argparse.Namespace) -> pd.DataFrame:
    """The ``args.pool`` distinct configurations stored selection-window profit factor ranks highest.

    The maximum-hold arms are left out, a configuration stored under two variant names at one bar
    size enters once at its higher rank, and a row the fill assumption could have decided is left
    out entirely -- ``docs/findings/m40-prop-objectives.md`` § "The pool, and the archive it was
    re-run on".
    """
    ranked: pd.DataFrame = ranked_pairs(
        name, root, CONTROL, None, args.stratum, args.resolution, args.variant
    )
    readable: pd.Series[bool] = (  # type: ignore[type-arg]  # duckdb's dtypes
        ranked[f"ambiguous_share{SELECTION_SUFFIX}"] <= disambiguate.MIN_AMBIGUOUS_SHARE
    )
    logger.info(
        "  %d of %d stored pairs are readable at an ambiguous share of %.2f or less",
        int(readable.sum()),
        len(ranked),
        disambiguate.MIN_AMBIGUOUS_SHARE,
    )
    ranked = ranked[readable]
    held_arms: set[str] = (
        {variant.name for variant in HOLD_VARIANTS[name](root)} if name in HOLD_VARIANTS else set()
    )
    ranked = ranked[~ranked["variant"].isin(held_arms)].reset_index(drop=True)

    archetype: archetypes.Archetype = archetypes.get(name)
    seen: set[tuple[int, str]] = set()
    kept: list[int] = []
    for position, row in half(ranked, SELECTION_SUFFIX).iterrows():
        if len(kept) == args.pool:
            break

        configuration: tuple[int, str] = (int(row["resolution"]), repr(rebuild(row, archetype)))
        if configuration in seen:
            continue

        seen.add(configuration)
        kept.append(int(position))

    return ranked.iloc[kept].reset_index(drop=True)


def run_cell(
    name: str,
    root: str,
    args: argparse.Namespace,
    accounts: list[propaccount.PropAccount],
    bars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One root's pool ranked on the selection window, and its shortlists read held out."""
    pairs: pd.DataFrame = pool(name, root, args)
    selection_rows: pd.DataFrame = half(pairs, SELECTION_SUFFIX)
    held_rows: pd.DataFrame = half(pairs, HELD_OUT_SUFFIX)
    logger.info("%s on %s: a pool of %d, through %d rule sets", name, root, len(pairs), len(accounts))

    everything: dict[tuple[str, int, str, str, int], list[propaccount.PropAccount]] = {
        key_of(row): accounts for _, row in selection_rows.iterrows()
    }
    selection: pd.DataFrame = measure_window(
        name,
        selection_rows,
        root,
        source(bars, "selection"),
        everything,
        args.n_jobs,
    )
    chosen: pd.DataFrame = shortlists(selection, accounts, args.top)
    if chosen.empty:
        return selection, pd.DataFrame()

    by_name: dict[str, propaccount.PropAccount] = {account.name: account for account in accounts}
    wanted: dict[tuple[str, int, str, str, int], list[propaccount.PropAccount]] = {}
    for _, picked in chosen.drop_duplicates([*JOIN_KEYS, "account_name"]).iterrows():
        wanted.setdefault(key_of(picked), []).append(by_name[str(picked["account_name"])])

    needed: pd.DataFrame = held_rows[[key_of(row) in wanted for _, row in held_rows.iterrows()]]
    held: pd.DataFrame = measure_window(name, needed, root, source(bars, "holdout"), wanted, args.n_jobs)
    measured: pd.DataFrame = pd.concat([selection, held], ignore_index=True)

    return measured, verdict(chosen, held)


def main(argv: list[str]) -> int:
    logsetup.configure(__name__)
    parser = argparse.ArgumentParser(
        description="Prop-account objectives ranked on selection, read held out."
    )
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--root", nargs="+", default=["MNQ"])
    parser.add_argument("--stratum", default="unfiltered", help="the stratum the pool is drawn from")
    parser.add_argument("--resolution", type=int, default=None, help="restrict the pool to one bar size")
    parser.add_argument("--variant", default=None, help="restrict the pool to one variant of the grid")
    parser.add_argument("--pool", type=int, default=POOL, help="configurations profit factor admits")
    parser.add_argument("--top", type=int, default=TOP, help="configurations each objective shortlists")
    parser.add_argument(
        "--preset",
        nargs="+",
        default=list(propaccount.PRESETS),
        help="which rule sets to replay; a name from nqbt.propaccount.PRESETS",
    )
    parser.add_argument("--n-jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None, help="write every replay row and the verdict here")
    args = parser.parse_args(argv[1:])

    accounts: list[propaccount.PropAccount] = [propaccount.preset(name) for name in args.preset]
    measured: list[pd.DataFrame] = []
    verdicts: list[pd.DataFrame] = []
    for root in args.root:
        bars: pd.DataFrame = splice.load_continuous(root)
        rows, table = run_cell(args.strategy, root, args, accounts, bars)
        cell: dict[str, str] = {"strategy": args.strategy, "root": root, "stratum": args.stratum}
        show(f"{args.strategy} {root} {args.stratum} -- each shortlist, selection and held out", table)
        measured.append(rows.assign(strategy=args.strategy))
        verdicts.append(table.assign(**cell))

    verdict_table: pd.DataFrame = pd.concat(verdicts, ignore_index=True)
    if verdict_table.empty:
        logger.warning("no shortlist was replayed on the holdout; nothing to report")

        return 1

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        pd.concat(measured, ignore_index=True).to_csv(args.out / "replays.csv", index=False)
        verdict_table.to_csv(args.out / "verdict.csv", index=False)
        logger.info("wrote %s", args.out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
