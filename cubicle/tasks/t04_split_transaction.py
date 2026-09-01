"""t04 - a split transaction. One payment, two expense categories.

The first task that cannot be done in the simple two-column register view; the agent
has to open the split editor.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import check_split, check_split_count, exactly_one_txn
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, record a single utility bill paid from Assets:Checking, split across "
    "two expense accounts:\n"
    "  Description: Utilities March\n"
    "  Total paid:  $120.00 from Assets:Checking\n"
    "  $80.00 to Expenses:Utilities:Electric\n"
    "  $40.00 to Expenses:Utilities:Water\n"
    "This must be ONE transaction with three splits, not two separate transactions.\n"
    "When it is recorded, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    txn, bad = exactly_one_txn(con, "Utilities March")
    if bad:
        return bad

    for check in (
        check_split_count(con, txn["guid"], 3),
        check_split(con, txn["guid"], "Electric", 8000),
        check_split(con, txn["guid"], "Water", 4000),
        check_split(con, txn["guid"], "Checking", -12000),
    ):
        if check:
            return check

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError("record the coordinates from a live desktop first")


TASK = Task(
    task_id="t04",
    tier="medium",
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
