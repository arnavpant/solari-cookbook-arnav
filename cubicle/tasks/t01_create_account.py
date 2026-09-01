"""t01 - create an account. The simplest thing a bookkeeper does."""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import account_by_name, accounts_by_name, open_book, parent_name
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, create a new account named exactly 'Software Subscriptions'.\n"
    "It must be of type Expense, and it must be a child of the top-level "
    "'Expenses' account.\n"
    "When the account exists, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    matches = accounts_by_name(con, "Software Subscriptions")
    if not matches:
        return Verdict(False, "no account named 'Software Subscriptions' exists")
    if len(matches) > 1:
        return Verdict(False, f"{len(matches)} accounts named 'Software Subscriptions' exist")

    acct = matches[0]
    if acct["account_type"] != "EXPENSE":
        return Verdict(
            False, f"wrong account type {acct['account_type']!r}, expected 'EXPENSE'"
        )

    parent = parent_name(con, acct)
    if parent != "Expenses":
        return Verdict(False, f"wrong parent {parent!r}, expected 'Expenses'")

    # The agent should not have disturbed the rest of the chart of accounts.
    if account_by_name(con, "Checking") is None:
        return Verdict(False, "the 'Checking' account was destroyed")

    return Verdict(True)


def oracle(cd) -> None:
    """Scripted solution.

    Coordinates must come from screenshots taken against a live desktop, never
    guessed. Filled in during Task 7 Step 6.
    """
    raise NotImplementedError("record the coordinates from a live desktop first")


TASK = Task(
    task_id="t01",
    tier="easy",
    max_steps=15,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
