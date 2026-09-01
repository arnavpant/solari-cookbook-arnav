"""t01 - create an account. The simplest thing a bookkeeper does."""

from __future__ import annotations

import time

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
    """Scripted solution, at 1280x720.

    Every coordinate below was read off a screenshot taken against a live desktop, not
    guessed. Recorded 2026-09-01; verified end to end - grade() returns passed=True
    against the book this produces.

    Note step 3: clicking the 'Expenses' parent makes GnuCash narrow the Account Type
    list from the full set down to Income/Expense, which is why the type is selected
    after the parent and not before.
    """
    from cubicle.types import Action

    steps = [
        (Action(kind="click", x=389, y=115), 2.5),   # 'New' in the toolbar
        (Action(kind="type", text="Software Subscriptions"), 1.0),
        (Action(kind="click", x=410, y=643), 1.5),   # parent tree -> Expenses
        (Action(kind="click", x=245, y=620), 1.0),   # account type -> Expense
        (Action(kind="click", x=559, y=692), 2.5),   # OK
    ]
    for action, pause in steps:
        cd.apply(action)
        time.sleep(pause)


TASK = Task(
    task_id="t01",
    tier="easy",
    # cap = max(3x the oracle's 5 actions, floor). The oracle solves this with
    # perfect foreknowledge; an agent has to look, decide and recover from mistakes,
    # so it gets three times the moves a perfect script needs.
    max_steps=15,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
