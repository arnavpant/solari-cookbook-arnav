"""t09 - reconcile against a statement with a line the book is missing.

Five of the six statement lines already exist in the book. The sixth does not, and the
task is unsolvable by pattern-matching alone: an agent that only ticks off what it can
find will clear five and stop, satisfied. It has to notice an absence.

The seed also holds one March transaction that is NOT on the statement, so clearing the
whole month - the fast wrong answer, and the one t06 already catches - fails here too.

The statement is delivered as plain text inside the prompt. No second window, no file
to open: the only thing on screen is GnuCash, and the only skill under test is reading
and operating it.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import account_by_name, open_book
from cubicle.tasks._common import check_date, check_split, check_split_count, exactly_one_txn
from cubicle.types import Task, Verdict

# Already in the seed and listed on the statement - these five must end up cleared.
ON_STATEMENT = (
    "March paper order",
    "Electric bill",
    "Water bill",
    "Laptop stand",
    "Stationery",
)

# In the seed, dated March, and deliberately absent from the statement. Clearing it is
# the "reconciled the whole month" failure.
OFF_STATEMENT = ("Cloud hosting",)

# On the statement, absent from the book. The agent has to add it, then clear it.
# (post date, description, expense account, amount in cents)
BANK_FEE = ("2026-03-31", "Bank fee", "Misc", 1500)

_STATEMENT_LINES = (
    ("2026-03-02", "March paper order", 6400),
    ("2026-03-06", "Electric bill", 8840),
    ("2026-03-11", "Water bill", 3120),
    ("2026-03-17", "Laptop stand", 5125),
    ("2026-03-23", "Stationery", 1299),
    (BANK_FEE[0], BANK_FEE[1], BANK_FEE[3]),
)


def _prompt() -> str:
    lines = "\n".join(
        f"  {day}   {desc:<20} ${cents / 100:.2f}" for day, desc, cents in _STATEMENT_LINES
    )
    return (
        "Here is the March 2026 bank statement for Assets:Checking:\n\n"
        f"{lines}\n\n"
        "In GnuCash, open the Assets:Checking register and make the register agree with\n"
        "this statement. One statement line has no matching transaction in the book -\n"
        f"add it as an expense to Expenses:{BANK_FEE[2]}, paid from Assets:Checking.\n"
        "Then mark all six statement lines as cleared, by clicking the 'R' column so it\n"
        "changes from 'n' to 'c'.\n"
        "Do NOT clear any transaction that is not on the statement above.\n"
        "When exactly those six are cleared, respond with the done action."
    )


PROMPT = _prompt()


def _cleared_by_description(con) -> dict[str, bool]:
    """reconcile_state of each transaction's Checking split, keyed by description."""
    checking = account_by_name(con, "Checking")
    if checking is None:
        return {}
    rows = con.execute(
        "SELECT t.description, s.reconcile_state "
        "FROM splits s JOIN transactions t ON t.guid = s.tx_guid "
        "WHERE s.account_guid = ?",
        (checking["guid"],),
    ).fetchall()
    return {r["description"]: r["reconcile_state"] in ("c", "y") for r in rows}


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)
    if account_by_name(con, "Checking") is None:
        return Verdict(False, "the 'Checking' account is missing")

    day, desc, account, cents = BANK_FEE
    txn, bad = exactly_one_txn(con, desc)
    if bad:
        return bad
    for check in (
        check_date(txn, day),
        check_split_count(con, txn["guid"], 2),
        check_split(con, txn["guid"], account, cents),
        check_split(con, txn["guid"], "Checking", -cents),
    ):
        if check:
            return Verdict(False, f"{desc}: {check.reason}")

    cleared = _cleared_by_description(con)

    missed = [d for d in list(ON_STATEMENT) + [desc] if not cleared.get(d)]
    if missed:
        return Verdict(False, "statement lines not cleared: " + ", ".join(sorted(missed)))

    overreached = [d for d in OFF_STATEMENT if cleared.get(d)]
    if overreached:
        return Verdict(
            False,
            "cleared a transaction that is not on the statement: " + ", ".join(sorted(overreached)),
        )

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError(
        "t09's oracle is not recorded yet. Every coordinate in this suite was read off a "
        "real screenshot at 1280x720 - none are guessed - so recording it needs a live "
        "desktop. See scripts/setup_desktop.py."
    )


TASK = Task(
    task_id="t09",
    tier="hard",
    # See t08: the 3x-oracle floor cannot be computed until the oracle is recorded.
    max_steps=60,
    prompt=PROMPT,
    seed=lambda: seed_bytes("t09"),
    grade=grade,
    oracle=oracle,
)
