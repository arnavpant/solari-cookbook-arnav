"""t07 - move an account under a different parent.

The seed already contains 'Software Subscriptions' as a child of Expenses, so this task
does not depend on t01 having run. Tasks are independent by construction.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import accounts_by_name, open_book, parent_name
from cubicle.tasks._common import play
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
    """Recorded 2026-09-01 at 1280x720.

    The Parent Account tree in the Edit dialog is only about three rows tall, so the
    target is almost always below the fold. Clicking the disclosure triangle to expand
    and then walking down with the arrow key is far more robust than trying to click a
    row that may not be visible - the tree auto-scrolls to keep the selection in view.
    """
    from cubicle.types import Action

    play(cd, [
        (Action(kind="click", x=13, y=241), 1.5),    # expand Expenses in the main tree
        (Action(kind="click", x=110, y=310), 1.0),   # select 'Software Subscriptions'
        (Action(kind="click", x=295, y=115), 2.5),   # Edit in the toolbar
        (Action(kind="click", x=352, y=643), 1.2),   # expand Expenses in the parent tree
        (Action(kind="key", text="Down"), 0.4),      # Misc
        (Action(kind="key", text="Down"), 0.4),      # Office Supplies
        (Action(kind="key", text="Down"), 0.4),      # Software Subscriptions
        (Action(kind="key", text="Down"), 0.6),      # Technology
        (Action(kind="click", x=559, y=692), 2.5),   # OK
    ])


TASK = Task(
    task_id="t07",
    tier="medium",
    # cap = max(3x the oracle's 9 actions, floor). The oracle solves this with
    # perfect foreknowledge; an agent has to look, decide and recover from mistakes,
    # so it gets three times the moves a perfect script needs.
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("t07"),
    grade=grade,
    oracle=oracle,
)
