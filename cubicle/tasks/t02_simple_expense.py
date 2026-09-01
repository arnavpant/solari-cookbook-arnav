"""t02 - record a single expense. The most common bookkeeping action there is."""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import check_date, check_split, check_split_count, exactly_one_txn
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
    raise NotImplementedError("record the coordinates from a live desktop first")


TASK = Task(
    task_id="t02",
    tier="easy",
    max_steps=15,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
