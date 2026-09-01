"""t07 - move an account under a different parent.

The seed already contains 'Software Subscriptions' as a child of Expenses, so this task
does not depend on t01 having run. Tasks are independent by construction.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import accounts_by_name, open_book, parent_name
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, the expense account 'Software Subscriptions' currently sits directly "
    "under 'Expenses'.\n"
    "Move it so that it becomes a child of 'Expenses:Technology' instead.\n"
    "Keep the same account - do not delete it and create a new one.\n"
    "When it has been moved, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    matches = accounts_by_name(con, "Software Subscriptions")
    if not matches:
        return Verdict(False, "no account named 'Software Subscriptions' exists")
    if len(matches) > 1:
        return Verdict(False, f"{len(matches)} accounts named 'Software Subscriptions' exist")

    acct = matches[0]
    parent = parent_name(con, acct)
    if parent != "Technology":
        return Verdict(False, f"parent is {parent!r}, expected 'Technology'")

    if acct["account_type"] != "EXPENSE":
        return Verdict(False, f"account type changed to {acct['account_type']!r}")

    # Technology must still be where it was; moving the parent instead of the child
    # would also produce the right-looking path.
    tech = accounts_by_name(con, "Technology")
    if not tech or parent_name(con, tech[0]) != "Expenses":
        return Verdict(False, "'Technology' is no longer a child of 'Expenses'")

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError("record the coordinates from a live desktop first")


TASK = Task(
    task_id="t07",
    tier="medium",
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("t07"),
    grade=grade,
    oracle=oracle,
)
