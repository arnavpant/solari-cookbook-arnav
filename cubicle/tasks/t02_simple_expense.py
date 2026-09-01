"""t02 - record a single expense. The most common bookkeeping action there is."""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import (
    check_date,
    check_split,
    check_split_count,
    exactly_one_txn,
    play,
)
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, record a new expense transaction with these exact details:\n"
    "  Date:        14 March 2026\n"
    "  Description: Printer paper\n"
    "  Amount:      $42.50\n"
    "  Expense account: Expenses:Office Supplies\n"
    "  Paid from:       Assets:Checking\n"
    "When the transaction is recorded, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    txn, bad = exactly_one_txn(con, "Printer paper")
    if bad:
        return bad

    for check in (
        check_date(txn, "2026-03-14"),
        check_split_count(con, txn["guid"], 2),
        check_split(con, txn["guid"], "Office Supplies", 4250),
        check_split(con, txn["guid"], "Checking", -4250),
    ):
        if check:
            return check

    return Verdict(True)


def oracle(cd) -> None:
    """Recorded 2026-09-01 at 1280x720, maximized.

    Note the TWO-digit year. GnuCash's register date field silently truncates a
    four-digit year: typing '03/14/2026' stores 2020-03-14 and displays '03/14/20',
    which looks entirely plausible on screen. The grader caught it; a screenshot judge
    would not have. Type '03/14/26'.

    Register tab order is Date -> Num -> Description -> Transfer -> Deposit ->
    Withdrawal, so an expense needs two tabs after the transfer account to skip past
    Deposit and land in Withdrawal.
    """
    from cubicle.types import Action

    play(cd, [
        (Action(kind="click", x=13, y=217), 1.2),          # expand Assets
        (Action(kind="double_click", x=75, y=241), 3.0),   # open the Checking register
        (Action(kind="type", text="03/14/26"), 0.6),       # date - two-digit year
        (Action(kind="key", text="Tab"), 0.3),             # -> Num
        (Action(kind="key", text="Tab"), 0.3),             # -> Description
        (Action(kind="type", text="Printer paper"), 0.6),
        (Action(kind="key", text="Tab"), 0.4),             # -> Transfer
        (Action(kind="type", text="Expenses:Office Supplies"), 0.8),
        (Action(kind="key", text="Tab"), 0.3),             # -> Deposit
        (Action(kind="key", text="Tab"), 0.3),             # -> Withdrawal
        (Action(kind="type", text="42.50"), 0.5),
        (Action(kind="key", text="Return"), 2.5),          # commit
    ])


TASK = Task(
    task_id="t02",
    tier="easy",
    max_steps=15,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
